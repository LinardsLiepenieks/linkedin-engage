#!/usr/bin/env python3
"""
apply_comments.py — Post the comments you APPROVED in the review UI.

Navigates DIRECTLY to each approved post's saved permalink (captured by resolve_links.py) and
comments on the post page. No content-matching at comment time — the link was resolved and
verified earlier, so we always comment on exactly the intended post.

Reads data/approved.json. For each item with include==true AND a permalink it:
  * navigates to the permalink,
  * opens the comment box, types the (possibly edited) comment, submits,
  * optionally likes,
  * records the post in data/history.json (by key + activity id) so it's never re-commented.

Items without a permalink are skipped (resolve_links.py couldn't get/verify a link) — we never
guess which post to comment on.

Safety: only include==true; --dry-run reports without clicking; randomized delays; --max cap.

Usage:
    python scripts/apply_comments.py --dry-run
    python scripts/apply_comments.py
    python scripts/apply_comments.py --max 8
"""

import argparse
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"  # 127.0.0.1, not localhost: newer Playwright resolves localhost to IPv6 ::1
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
APPROVED_FILE = DATA_DIR / "approved.json"
RESULTS_FILE = DATA_DIR / "apply_results.json"
HISTORY_FILE = DATA_DIR / "history.json"

EDITOR_SEL = 'div[role="textbox"][aria-label="Text editor for creating comment"]'
ACTIVITY_RE = re.compile(r"(\d{15,25})")


def load_history_keys():
    """Keys (and activity ids) of posts already commented on, for safe resume."""
    if not HISTORY_FILE.exists():
        return set()
    try:
        history = json.loads(HISTORY_FILE.read_text())
    except (json.JSONDecodeError, ValueError):
        return set()
    done = set()
    for h in history:
        if h.get("key"):
            done.add(h["key"])
        if h.get("activity_id"):
            done.add("act:" + h["activity_id"])
    return done


def already_done(item, done):
    return item.get("key") in done or ("act:" + (item.get("activity_id") or "")) in done


def record_history(item, comment_text):
    history = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            history = []
    key = item.get("key")
    if any(h.get("key") == key for h in history):
        return
    history.append({
        "key": key,
        "permalink": item.get("permalink", ""),
        "activity_id": item.get("activity_id", ""),
        "author": item.get("author", ""),
        "comment": comment_text,
        "commented_at": datetime.now(timezone.utc).isoformat(),
    })
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False))


def open_comment_box(page):
    """Click the post page's 'Comment' toggle to reveal the editor (idempotent-ish)."""
    return page.evaluate(r"""() => {
      if (document.querySelector('div[role="textbox"][aria-label="Text editor for creating comment"]')) return true;
      const btn = [...document.querySelectorAll('button')].find(b => /^\s*comment\s*$/i.test(b.innerText || ''));
      if (btn) { btn.click(); return true; }
      return false;
    }""")


def submit_comment(page):
    """Click the submit 'Comment' button that appears after the editor once text is present."""
    return page.evaluate(r"""() => {
      const ed = document.querySelector('div[role="textbox"][aria-label="Text editor for creating comment"]');
      const btns = [...document.querySelectorAll('button')].filter(b => /^\s*comment\s*$/i.test(b.innerText || ''));
      let submit = null;
      if (ed) {
        for (const b of btns) {
          if (ed.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) { submit = b; break; }
        }
      }
      submit = submit || btns[btns.length - 1];
      if (submit && !submit.disabled) { submit.click(); return true; }
      return false;
    }""")


def click_like(page):
    return page.evaluate(r"""() => {
      const b = document.querySelector('button[aria-label^="React Like"], button[aria-label="Reaction button state: no reaction"]');
      if (b) { b.click(); return 'liked'; }
      return 'like button not found';
    }""")


def post_comment(page, item, dry_run):
    text = (item.get("comment") or "").strip()
    if not text:
        return False, "empty comment"
    permalink = item.get("permalink")
    if not permalink:
        return False, "no permalink (link not resolved) — skipped"

    page.goto(permalink, wait_until="domcontentloaded")
    page.wait_for_timeout(random.randint(2500, 4200))

    if dry_run:
        return True, f"[dry-run] would comment at {permalink}: {text!r}"

    if not open_comment_box(page):
        return False, "comment toggle/editor not found on post page"
    page.wait_for_timeout(random.randint(700, 1400))

    editor = page.query_selector(EDITOR_SEL)
    if editor is None:
        return False, "comment editor not found"
    editor.click()
    page.keyboard.type(text, delay=random.randint(35, 80))
    page.wait_for_timeout(random.randint(700, 1400))

    if not submit_comment(page):
        return False, "submit button not found / disabled"
    page.wait_for_timeout(random.randint(1500, 2500))
    return True, "commented"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=22, help="max comments this run (daily cap)")
    ap.add_argument("--min-delay", type=float, default=35)
    ap.add_argument("--max-delay", type=float, default=90)
    ap.add_argument("--cdp", default=CDP_URL)
    args = ap.parse_args()

    if not APPROVED_FILE.exists():
        print(f"ERROR: {APPROVED_FILE} not found. Review & approve in the UI first.", file=sys.stderr)
        sys.exit(1)

    items = [it for it in json.loads(APPROVED_FILE.read_text()) if it.get("include")]
    if not items:
        print("Nothing approved (no items with include=true). Done.")
        return

    # Resume-safe: skip posts already commented on (recorded in history.json).
    done = load_history_keys()
    already = [it for it in items if already_done(it, done)]
    items = [it for it in items if not already_done(it, done)]
    if already:
        print(f"Skipping {len(already)} post(s) already commented on (history.json) — resuming.")
    if not items:
        print("All approved posts already commented on. Nothing to do.")
        return
    todo = items[: args.max]
    no_link = [it for it in todo if not it.get("permalink")]
    if no_link:
        print(f"Note: {len(no_link)} approved item(s) have no resolved permalink and will be "
              f"skipped. Run resolve_links.py to capture them.")
    print(f"{'DRY RUN — ' if args.dry_run else ''}{len(todo)} comment(s) to apply (cap {args.max}).\n")

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(args.cdp)
        except Exception as e:
            print(f"ERROR: could not connect to Chrome at {args.cdp}. See CHROME_SETUP.md ({e})", file=sys.stderr)
            sys.exit(1)
        context = browser.contexts[0]
        page = next((pg for pg in context.pages if "linkedin.com" in pg.url), None) or context.new_page()
        page.bring_to_front()

        results = []
        for i, item in enumerate(todo, 1):
            author = item.get("author", "?")
            print(f"[{i}/{len(todo)}] {author}")
            ok, msg = post_comment(page, item, args.dry_run)
            entry = {"key": item.get("key"), "author": author, "permalink": item.get("permalink", ""),
                     "comment_ok": ok, "comment_msg": msg}
            print(f"    comment: {msg}")

            if ok and not args.dry_run:
                record_history(item, (item.get("comment") or "").strip())
                if item.get("like"):
                    entry["like"] = click_like(page)
                    print(f"    like: {entry['like']}")
            results.append(entry)

            if i < len(todo) and not args.dry_run:
                delay = random.uniform(args.min_delay, args.max_delay)
                print(f"    …waiting {delay:.0f}s")
                time.sleep(delay)

        RESULTS_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"\nDone. Log -> {RESULTS_FILE}")


if __name__ == "__main__":
    main()
