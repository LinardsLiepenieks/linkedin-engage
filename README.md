# LinkedIn engage

A local, human-in-the-loop tool to go through your LinkedIn feed and engage with relevant
posts. Claude reads your feed, scores posts against your own rules, drafts comments, and you
approve/edit them in a web UI before anything is posted.

> **How this stays safe-ish:** it attaches to *your real, logged-in Chrome* over the DevTools
> protocol (not a bot browser), acts only on posts you approved, and throttles with
> randomized delays. There is no fully-autonomous mode by design — LinkedIn reduces the
> visibility of comments it detects as automated, and high-volume auto-engagement risks your
> account. See `qualify.md` and `.claude/skills/linkedin-engage/SKILL.md`.

## The flow

```
Chrome (real, logged in)  ──CDP──▶  scrape_feed.py  ──▶  data/posts.json
                                                              │
                              Claude reads posts + qualify.md │  scores + drafts
                                                              ▼
                                                       data/review.json
                                                              │
                                  serve_review.py  ◀──────────┘   (web UI: edit/approve)
                                          │
                                          ▼
                                   data/approved.json
                                          │
                                          ▼
                              apply_comments.py  ──CDP──▶  Chrome  (posts, throttled)
```

## Setup (once)

```bash
pip install -r requirements.txt
python -m playwright install chromium

# Copy the templates, then make them yours (these copies are gitignored — personal, never pushed)
cp qualify.example.md qualify.md
cp .claude/skills/linkedin-engage/SKILL.example.md .claude/skills/linkedin-engage/SKILL.md
```

Then edit **`qualify.md`** with your real relevance rules and comment style — this is where all
the domain judgement lives (who to engage, how to score, your comment voice, any lead taxonomy).
The skill (`SKILL.md`) is generic plumbing; the `*.example.md` files are the shared templates,
and your filled-in `qualify.md` / `SKILL.md` stay local.

Starting debug Chrome is **automated** by the skill (`scripts/start_chrome.sh`) — you don't
do it by hand. See **[CHROME_SETUP.md](CHROME_SETUP.md)** for what it does and the manual
equivalent.

## Run

The easiest way is the skill: in Claude Code, from this directory, run **`/linkedin-engage`**.
It walks through scrape → score/draft → review → apply.

Or run the steps manually:

```bash
bash scripts/start_chrome.sh                  # 0. launch debug Chrome (dedicated profile)
python scripts/scrape_feed.py --count 100     # 1. scrape feed -> data/posts.json
# 2. have Claude write data/review.json (scores + draft comments)
python scripts/serve_review.py                # 3. review UI at http://localhost:8765
python scripts/apply_comments.py --dry-run    # 4a. rehearse
python scripts/apply_comments.py              # 4b. post approved comments (throttled)
```

## Maintenance

LinkedIn rotates its DOM class names, so the selectors in `scrape_feed.py` and
`apply_comments.py` will eventually break (you'll see 0 posts, or "editor not found"). Each
script has a SELECTORS block near the top with fallbacks — open the feed in your debug Chrome,
inspect the element, and update the list. This is normal upkeep for any LinkedIn DOM tool.
