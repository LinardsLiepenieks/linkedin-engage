#!/usr/bin/env python3
"""
scrape_feed.py — Attach to your real Chrome (over CDP) and collect recent LinkedIn feed posts
WITH their permalinks into data/posts.json.

Why links are captured here: LinkedIn's feed doesn't expose post permalinks in the DOM, and
the feed reorders/recycles constantly — so trying to re-find a post later (to get its link)
is unreliable. Instead we capture each post's link in the SAME moment we read its text, while
we're already on that exact post: open the post's "⋯" menu, click "Copy link to post", read
the clipboard. The link is then saved alongside the text, so nothing ever needs re-finding.

Promoted/ad posts are skipped (no link captured) since we never comment on them.

Does NOT launch a bot browser and does NOT touch credentials — connects to a Chrome started
with --remote-debugging-port=9222 (see CHROME_SETUP.md) and reuses your session.

Usage:
    python scripts/scrape_feed.py --count 30

Output: data/posts.json — list of {idx, permalink, activity_id, text}. Posts whose link
could not be captured are still included with an empty permalink (and get skipped at apply).
"""

import argparse
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CDP_URL = "http://localhost:9222"
FEED_URL = "https://www.linkedin.com/feed/"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_FILE = DATA_DIR / "posts.json"
MAX_TEXT_CHARS = 3000
ACTIVITY_RE = re.compile(r"(\d{15,25})")

# Return the next unseen feed post's text and stash the element on window.__cur.
# window.__seen persists across calls (same page session) so we don't reprocess.
NEXT_UNSEEN_JS = r"""
() => {
  window.__seen = window.__seen || new Set();
  const scope = document.querySelector('[data-testid="mainFeed"]') || document;
  const blocks = [...scope.querySelectorAll('div[data-display-contents="true"]')]
    .filter(d => (d.innerText || '').trim().startsWith('Feed post'));
  for (const c of blocks) {
    let text = (c.innerText || '')
      .replace(/^Feed post\s*/, '')
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
    const key = text.slice(0, 160);
    if (!text || window.__seen.has(key)) continue;
    window.__seen.add(key);
    window.__cur = c;
    // author profile = first person (/in/) link in the block, else company page
    let profile = '';
    const a = c.querySelector('a[href*="linkedin.com/in/"]') || c.querySelector('a[href*="linkedin.com/company/"]');
    if (a) profile = (a.getAttribute('href') || '').split('?')[0];
    return { text, profile };
  }
  return null;
}
"""

OPEN_MENU_JS = r"""
() => {
  const c = window.__cur;
  if (!c) return false;
  c.scrollIntoView({block: 'center'});
  const b = [...c.querySelectorAll('button')].find(x => /open control menu/i.test(x.getAttribute('aria-label') || ''));
  if (b) { b.click(); return true; }
  return false;
}
"""

CLICK_COPY_JS = r"""
() => {
  const els = [...document.querySelectorAll('[role="menuitem"], div[role="button"], button')];
  const el = els.find(e => /copy link to post/i.test(e.innerText || ''));
  if (el) { el.click(); return true; }
  return false;
}
"""

SCROLL_JS = r"""
() => {
  let best = null, bh = 0;
  document.querySelectorAll('*').forEach(el => {
    const st = getComputedStyle(el);
    if (/(auto|scroll)/.test(st.overflowY) && el.scrollHeight > el.clientHeight + 200 && el.scrollHeight > bh) {
      bh = el.scrollHeight; best = el;
    }
  });
  const t = best || document.scrollingElement || document.documentElement;
  t.scrollTop = t.scrollHeight;
}
"""


def capture_link(page):
    """With window.__cur set, open its ⋯ menu, click 'Copy link to post', read clipboard."""
    try:
        if not page.evaluate(OPEN_MENU_JS):
            return ""
        page.wait_for_timeout(800)
        if not page.evaluate(CLICK_COPY_JS):
            page.keyboard.press("Escape")
            return ""
        page.wait_for_timeout(700)
        url = page.evaluate("() => navigator.clipboard.readText()")
        page.keyboard.press("Escape")
        url = (url or "").split("?")[0].strip()
        if "linkedin.com/posts/" in url or "/feed/update/" in url:
            return url
        return ""
    except Exception:
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return ""


def find_feed_page(context):
    for page in context.pages:
        if "linkedin.com" in page.url:
            return page
    return context.pages[0] if context.pages else context.new_page()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=50, help="target number of posts (with links)")
    ap.add_argument("--max-scrolls", type=int, default=50)
    ap.add_argument("--cdp", default=CDP_URL)
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(args.cdp)
        except Exception as e:
            print(f"ERROR: could not connect to Chrome at {args.cdp}. See CHROME_SETUP.md", file=sys.stderr)
            print(f"({e})", file=sys.stderr)
            sys.exit(1)
        if not browser.contexts:
            print("ERROR: no browser context found.", file=sys.stderr)
            sys.exit(1)
        context = browser.contexts[0]
        try:
            context.grant_permissions(["clipboard-read", "clipboard-write"], origin="https://www.linkedin.com")
        except Exception as e:
            print(f"(clipboard permission note: {e})")
        page = find_feed_page(context)
        if "linkedin.com/feed" not in page.url:
            print("Navigating to LinkedIn feed…")
            page.goto(FEED_URL, wait_until="domcontentloaded")
        page.bring_to_front()
        page.wait_for_timeout(3000)
        page.evaluate("() => { window.__seen = new Set(); }")  # fresh run

        results = []
        scrolls = 0
        guard = 0
        while len(results) < args.count and scrolls < args.max_scrolls and guard < args.count * 8 + 60:
            guard += 1
            res = page.evaluate(NEXT_UNSEEN_JS)
            if res is None:
                page.evaluate(SCROLL_JS)
                page.wait_for_timeout(2300)
                scrolls += 1
                continue
            text = res.get("text", "")
            profile = res.get("profile", "")
            if "Promoted" in text or len(text) < 40:
                continue  # ad / non-post card: skip, no link
            link = capture_link(page)
            text = text[:MAX_TEXT_CHARS] + ("…" if len(text) > MAX_TEXT_CHARS else "")
            m = ACTIVITY_RE.search(link)
            results.append({
                "idx": len(results),
                "permalink": link,
                "activity_id": m.group(1) if m else "",
                "author_profile": profile,
                "text": text,
            })
            status = "✓ link" if link else "✗ no link"
            print(f"  [{len(results)}] {status}  {text.splitlines()[0][:50] if text.splitlines() else ''}")
            page.wait_for_timeout(500)

        OUT_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        with_link = sum(1 for r in results if r["permalink"])
        print(f"\nWrote {len(results)} posts ({with_link} with links) -> {OUT_FILE}")
        if not results:
            print("WARNING: 0 posts captured. The feed anchor may be stale.", file=sys.stderr)


if __name__ == "__main__":
    main()
