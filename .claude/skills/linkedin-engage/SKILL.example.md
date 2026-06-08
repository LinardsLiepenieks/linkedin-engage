---
name: linkedin-engage
description: Scrape recent LinkedIn feed posts from your real Chrome, score them against qualify.md, draft comments, open a local web UI to review/edit/approve, then post the approved comments (throttled). Use when the user wants to go through their LinkedIn feed and engage with relevant posts.
---

# LinkedIn engage

> **This is the template skill.** Copy it to `SKILL.md` in this same folder and customize as
> you like. All domain judgement (who's a good fit, how to score, comment style, any
> prospect/lead taxonomy) belongs in **`qualify.md`**, not here — this file is generic
> plumbing. Never hardcode a specific ICP, persona, or topic in the skill; read it from
> `qualify.md` every run.

Human-in-the-loop LinkedIn feed engagement. You (Claude) are the relevance engine: you read
scraped posts plus the user's `qualify.md`, score each post, and draft comments. The user
approves/edits in a web UI before anything is posted.

**Project root:** the directory containing `qualify.md` and `scripts/`. All paths below are
relative to it. Run python with the project root as the working directory.

## Preconditions (check, don't assume)

1. **Playwright installed.** If `python -c "import playwright"` fails, instruct:
   `pip install -r requirements.txt && python -m playwright install chromium`.
2. **`qualify.md` exists and is filled in.** If it's missing, tell the user to copy
   `qualify.example.md` to `qualify.md` and edit it. If it still has placeholder/template text
   and no real criteria, ask the user to fill it in first — the drafts are only as good as
   these rules.

## Steps

### 0 — Start debug Chrome
Run: `bash scripts/start_chrome.sh`
This launches (or reuses) a debug-enabled Chrome on port 9222 using a dedicated profile,
without disturbing the user's everyday Chrome, and opens the LinkedIn feed in it. The script
is idempotent — if Chrome is already up on the port it just confirms and exits.
- If the script reports "log into LinkedIn", the dedicated profile is fresh: tell the user to
  log in once in the window that opened, then continue. Don't scrape until they confirm.
- If the user prefers their already-logged-in everyday Chrome instead (closes their current
  tabs), run `bash scripts/start_chrome.sh --main-profile`.
- After it reports ready, sanity-check: `curl -s http://localhost:9222/json/version`.

### 1 — Scrape the feed
Run: `python scripts/scrape_feed.py --count 50`
(`--count` is a target/ceiling, not a minimum. Scrape a wide net so scoring has enough to pick
from after filtering out the "hard skips" defined in `qualify.md`. How many to ultimately
comment on is set by `qualify.md`, not here.)
This attaches to the user's Chrome, scrolls the feed, and writes `data/posts.json`. Each entry
is `{id, urn, permalink, text}` where **`text` is the post's raw visible text** (innerText) —
the scraper deliberately does NOT pre-parse fields, because the visible text is far more
stable than LinkedIn's CSS class names. It skips posts already in `data/history.json`
(commented via this tool). If it returns 0 posts, the post-container anchor may be stale —
tell the user and point at the SELECTORS note in `scrape_feed.py`. Don't fabricate posts.

### 2 — Score & draft (this is your job — you are the parser AND the dedup engine)
- Read `qualify.md`, `data/posts.json`, and `data/history.json` (if it exists).
- For EACH post, **parse the raw `text` yourself**: identify the author name/headline, the
  post body, and engagement counts (reactions / comments appear as numbers like "1,204" and
  "87 comments"). The text is messy — it includes context lines ("X likes this", "Suggested",
  "Promoted"), button labels ("Like Comment Repost"), and a relative timestamp ("3h •"). Use
  judgment; ignore the chrome.
- **Compute a stable `key`** for each post = lowercased `"<author> | <first ~60 chars of the
  post body>"` (exclude volatile bits like the timestamp and reaction counts). This is the
  dedup + match identity, since LinkedIn no longer exposes post URNs.
- **Drop duplicates and already-engaged posts** (do NOT put them in `review.json` at all):
  - if the post's `key` matches any entry in `history.json` (we already commented via the tool);
  - if the text shows a manual-engagement header like "You commented on this" / "You replied to…".
- For each remaining post, **apply the qualification rules from `qualify.md`**: assign a
  `score` 0–10 and a one-line `reason`. How many to include, the score threshold/floor, and
  whether fit is a hard gate or a priority booster are all defined in `qualify.md` — follow it.
  Exclude the "hard skips" listed there outright.
- For posts the rules say to engage with, write a `comment` following the style rules in
  `qualify.md` (length, tone, question ratio, what to avoid, etc.). Make it specific to the
  post. For posts you won't engage with, leave `comment` empty.
- Set `like` / `follow` per the "Optional actions" section of `qualify.md`.
- **Flag prospect signals if `qualify.md` defines a prospect/pain taxonomy.** Set
  `pain_match: true` only when the post genuinely expresses one of the pains defined there, and
  set `pain_tags` to the matching keys from that taxonomy. Carry over `author_profile` from
  `posts.json` unchanged. `pain_match` is independent of `include`/score. Be strict: only true
  pain talk that matches the user's definitions, not generic adjacent chatter. If `qualify.md`
  defines no prospect taxonomy, leave `pain_match: false`, `pain_tags: []`.
- **Classify prospect tier if `qualify.md` defines one.** When the file specifies prospect
  tiers/personas, set `prospect_tier`, `prospect_persona`, and `pain_magnitude` (1–5) per its
  definitions. Leave them null if no taxonomy is defined or none fit.
- Provide `match_author` and `match_text` — short, stable, verbatim substrings of the post's
  visible text (the author name, and ~60 chars of the body). `resolve_links.py` uses these to
  locate the post ONCE to capture its permalink. They MUST appear literally in the post text.
- Leave `permalink` empty (`""`) — it gets filled in by step 2.5.
- Write `data/review.json` as a JSON array, sorted by score descending, each item:
  ```json
  {
    "key": "<author> | <first ~60 chars of body>",
    "author": "Author Name", "headline": "their headline",
    "text": "full post body for the reviewer to read",
    "reactions": 1204, "comments": 87,
    "match_author": "Author Name",
    "match_text": "verbatim ~60-char substring of the body",
    "permalink": "",
    "author_profile": "https://www.linkedin.com/in/...",
    "pain_match": false, "pain_tags": [],
    "prospect_tier": null, "prospect_persona": null, "pain_magnitude": null,
    "score": 8, "reason": "why it qualified / was skipped",
    "comment": "drafted comment or empty string",
    "include": true,        // true only if the qualify.md rules say to engage
    "like": true, "follow": false
  }
  ```
  Include below-threshold (but non-duplicate) posts too, with `include: false` and empty
  `comment`, so the user can sanity-check skips. Keep `text` reasonably full for context.

### 2.5 — Resolve permalinks
Run: `python scripts/resolve_links.py`
For each included post, this locates it once (by `match_author` + `match_text`), opens the
"⋯" menu, clicks "Copy link to post", reads the link from the clipboard, verifies it against
the author, and writes `permalink` (+ `activity_id`) back into `review.json`. This is the only
place content-matching is used; the actual comment later navigates directly to this saved link.
Report how many resolved; any that fail verification stay blank and will be skipped at apply.

### 2.6 — Collect prospects (optional — only if qualify.md defines a prospect taxonomy)
Run: `python scripts/collect_prospects.py`
This reads `review.json`, takes every `pain_match: true` post with an `author_profile`, and
upserts that author into `data/prospects.json` (+ a readable `data/prospects.md`), deduped by
profile URL across all runs. Report how many new prospects were added. This is a growing lead
list of people who actively talk about the pains the user defined — independent of whether we
commented. Skip this step if `qualify.md` defines no prospect taxonomy.

### 3 — Review UI
Run in the background: `python scripts/serve_review.py`
It opens http://localhost:8765 where the user edits comments and toggles include/like/follow,
with a working "open ↗" link to each post (the resolved permalink). Tell the user to click
**Save approvals** when done (writes `data/approved.json`), then confirm before continuing.

### 4 — Apply (only after approval)
- First do a rehearsal: `python scripts/apply_comments.py --dry-run` and show the user what
  will be posted. The dry-run navigates to each saved permalink and reports.
- On their go-ahead, run: `python scripts/apply_comments.py` (default cap 22, randomized
  35–90s delays). It navigates DIRECTLY to each post's saved permalink and comments there —
  no content-matching. Items without a resolved permalink are skipped, never guessed.
- Report the results from `data/apply_results.json`.
- Stop the review server (it was backgrounded) once finished.

## Guardrails
- **No duplicate comments.** `data/history.json` records every post we've commented on (by
  content `key` and `activity_id`). At scoring time (step 2) drop any post whose `key` matches
  history; never re-draft or re-comment a post already in history. Apply appends after each
  successful comment.
- **Never guess a post.** Commenting only ever happens by navigating to a saved, verified
  permalink. If a post's link wasn't resolved, skip it — do not fall back to commenting on a
  content-matched feed block.
- Never post anything not present in `data/approved.json` with `include: true`.
- Never edit the user's approved comment text in step 4 — apply it verbatim.
- If the user seems to want fully autonomous mass-commenting, remind them: comments from
  detected automation get reduced visibility, and high-volume auto-engagement risks the
  account. The throttled, approved-only flow is the safe design — keep it that way.
