#!/usr/bin/env python3
"""
resolve_links.py — Capture the real permalink for each PROPOSED post and save it.

Two ways to get a post's permalink, tried in this order:

1. PRIMARY — backfill from the scrape. scrape_feed.py reads each post's permalink straight off
   its DOM block (anchored to the same element as the post text), so data/posts.json usually
   already has the canonical link. We match each included post to its scraped entry by exact
   post text and copy the permalink over. This is the most reliable path — no re-matching
   against a live feed that has since scrolled and changed.

2. FALLBACK — live-feed lookup. For any included post the scrape didn't capture a link for, we
   locate it in the feed (by author + text snippet), open its "⋯" control menu, click
   "Copy link to post", and read the link off the clipboard. This is fragile (the feed reorders
   between scrape and resolve), so it's only used to fill the gaps the scrape left behind.

Fallback links are verified: the copied URL must look like a post permalink and loosely match
the author, otherwise it's left blank (and that post is skipped at apply time rather than
risking a comment on the wrong post). Scrape-captured links need no such check — exact-text
identity is far stronger than a name-token slug match.

Usage:
    python scripts/resolve_links.py                 # resolve links for includes in review.json
    python scripts/resolve_links.py --file data/approved.json

Run AFTER review.json is written and BEFORE serving the review UI.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"  # 127.0.0.1, not localhost: newer Playwright resolves localhost to IPv6 ::1
FEED_URL = "https://www.linkedin.com/feed/"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ACTIVITY_RE = re.compile(r"(\d{15,25})")  # the long numeric id inside a post URL

FIND_JS = r"""
([author, snippet]) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').toLowerCase();
  const a = norm(author), s = norm(snippet);
  const scope = document.querySelector('[data-testid="mainFeed"]') || document;
  const blocks = Array.from(scope.querySelectorAll('div[data-display-contents="true"]'))
    .filter(d => (d.innerText || '').trim().startsWith('Feed post'));
  for (const c of blocks) {
    const t = norm(c.innerText);
    if ((!a || t.includes(a)) && s && t.includes(s)) { window.__match = c; return true; }
  }
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

OPEN_MENU_JS = r"""
() => {
  const c = window.__match;
  if (!c) return false;
  c.scrollIntoView({block: 'center'});
  const btn = [...c.querySelectorAll('button')].find(b => /open control menu/i.test(b.getAttribute('aria-label') || ''));
  if (btn) { btn.click(); return true; }
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


def name_tokens(author):
    return [t for t in re.split(r"\W+", (author or "").lower()) if len(t) > 2]


def verify_link(url, author):
    if not url or "linkedin.com/" not in url:
        return False
    if "/posts/" not in url and "/feed/update/" not in url:
        return False
    toks = name_tokens(author)
    if not toks:
        return True  # nothing to check against
    u = url.lower()
    # at least one name token should appear in the URL slug
    return any(t in u for t in toks)


def looks_like_post_url(url):
    return bool(url) and "linkedin.com/" in url and ("/posts/" in url or "/feed/update/" in url)


def backfill_from_scrape(items, posts_path):
    """Fill permalinks from scrape_feed.py output (data/posts.json) by exact post-text match.

    Returns the count filled. The scraper reads each permalink off the same DOM block as the
    post text, so an exact text match is a trustworthy identity — no author-slug check needed.
    """
    if not posts_path.exists():
        return 0
    try:
        posts = json.loads(posts_path.read_text())
    except Exception:
        return 0
    by_text = {p.get("text"): p for p in posts if p.get("text")}
    filled = 0
    for it in items:
        if not it.get("include") or it.get("permalink"):
            continue
        p = by_text.get(it.get("text"))
        if p and looks_like_post_url(p.get("permalink")):
            it["permalink"] = p["permalink"].split("?")[0]
            if p.get("activity_id"):
                it["activity_id"] = p["activity_id"]
            else:
                m = ACTIVITY_RE.search(it["permalink"])
                if m:
                    it["activity_id"] = m.group(1)
            filled += 1
    return filled


def find_in_feed(page, author, snippet, max_scrolls=40):
    for _ in range(max_scrolls):
        if page.evaluate(FIND_JS, [author, snippet[:80]]):
            return True
        page.evaluate(SCROLL_JS)
        page.wait_for_timeout(1700)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(DATA_DIR / "review.json"))
    ap.add_argument("--cdp", default=CDP_URL)
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: {path} not found.", file=sys.stderr)
        sys.exit(1)
    items = json.loads(path.read_text())

    # PRIMARY path: backfill permalinks the scrape already captured (exact text match).
    filled = backfill_from_scrape(items, DATA_DIR / "posts.json")
    if filled:
        path.write_text(json.dumps(items, indent=2, ensure_ascii=False))
        print(f"Backfilled {filled} permalink(s) from the scrape (data/posts.json).")

    todo = [it for it in items if it.get("include") and not it.get("permalink")]
    print(f"Live-feed lookup needed for {len(todo)} remaining post(s)…\n")
    if not todo:
        print("Nothing to resolve (all includes already have permalinks).")
        return

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(args.cdp)
        except Exception as e:
            print(f"ERROR: could not connect to Chrome at {args.cdp}. See CHROME_SETUP.md ({e})", file=sys.stderr)
            sys.exit(1)
        context = browser.contexts[0]
        try:
            context.grant_permissions(["clipboard-read", "clipboard-write"], origin="https://www.linkedin.com")
        except Exception as e:
            print(f"(clipboard permission note: {e})")
        page = next((pg for pg in context.pages if "linkedin.com" in pg.url), None) or context.new_page()
        if "linkedin.com/feed" not in page.url:
            page.goto(FEED_URL, wait_until="domcontentloaded")
        page.bring_to_front()
        page.wait_for_timeout(2500)

        resolved = 0
        for i, item in enumerate(todo, 1):
            author = item.get("match_author") or item.get("author") or ""
            snippet = item.get("match_text") or ""
            print(f"[{i}/{len(todo)}] {author}")
            if not find_in_feed(page, author, snippet):
                print("    not found in feed — leaving link blank (will be skipped at apply)")
                continue
            if not page.evaluate(OPEN_MENU_JS):
                print("    control menu button not found")
                continue
            page.wait_for_timeout(900)
            if not page.evaluate(CLICK_COPY_JS):
                print("    'Copy link to post' not found")
                page.keyboard.press("Escape")
                continue
            page.wait_for_timeout(800)
            try:
                url = page.evaluate("() => navigator.clipboard.readText()")
            except Exception as e:
                print(f"    clipboard read failed: {e}")
                page.keyboard.press("Escape")
                continue
            url = (url or "").split("?")[0]  # drop tracking query params
            if verify_link(url, item.get("author", "")):
                item["permalink"] = url
                m = ACTIVITY_RE.search(url)
                if m:
                    item["activity_id"] = m.group(1)
                resolved += 1
                print(f"    saved: {url}")
            else:
                print(f"    link failed verification (got {url!r}) — leaving blank")
            page.keyboard.press("Escape")
            page.wait_for_timeout(600)

        path.write_text(json.dumps(items, indent=2, ensure_ascii=False))
        print(f"\nResolved {resolved}/{len(todo)} links -> {path}")


if __name__ == "__main__":
    main()
