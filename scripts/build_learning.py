#!/usr/bin/env python3
"""
build_learning.py — Assemble a clean before/after dataset for end-of-run learning.

After a run, this joins (by post `key`):
  * data/review.json       — your ORIGINAL draft + score + reason (what Claude wrote)
  * data/approved.json     — the FINAL comment + include/like/follow + 👍/👎 rating (what you did)
  * data/apply_results.json — whether it actually posted

and writes data/learning.json: one record per drafted post plus a summary. Claude reads this
in step 5 to spot recurring patterns in your edits and ratings, then distills them into the
auto-maintained "Learned from your edits & ratings" section of qualify.md.

This script does NO analysis and writes NO rules — it only lays out the evidence. The pattern
finding is Claude's job (it needs judgment), per the skill's step 5.

Usage:
    python scripts/build_learning.py
"""

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REVIEW_FILE = DATA_DIR / "review.json"
APPROVED_FILE = DATA_DIR / "approved.json"
RESULTS_FILE = DATA_DIR / "apply_results.json"
OUT_FILE = DATA_DIR / "learning.json"


def load(path):
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, ValueError):
        return []


def norm(s):
    """Normalize for comparison: collapse whitespace, strip, lowercase."""
    return re.sub(r"\s+", " ", (s or "")).strip()


def by_key(rows):
    out = {}
    for r in rows:
        k = r.get("key")
        if k:
            out[k] = r
    return out


def main():
    review = load(REVIEW_FILE)
    approved = by_key(load(APPROVED_FILE))
    results = by_key(load(RESULTS_FILE))

    records = []
    for r in review:
        key = r.get("key")
        draft = r.get("comment") or ""
        # only posts Claude actually drafted a comment for carry an edit signal
        if not norm(draft) and not (approved.get(key, {}).get("comment")):
            continue
        a = approved.get(key, {})
        final = a.get("comment") or ""
        res = results.get(key, {})

        drafted_include = bool(r.get("include"))
        final_include = bool(a.get("include")) if key in approved else drafted_include
        edited = norm(draft) != norm(final) and bool(norm(final))

        records.append({
            "key": key,
            "author": r.get("author", ""),
            "headline": r.get("headline", ""),
            "score": r.get("score"),
            "reason": r.get("reason", ""),
            "pain_tags": r.get("pain_tags", []),
            "draft_comment": draft,          # what Claude wrote
            "final_comment": final,          # what the user approved (possibly edited)
            "edited": edited,                # final differs from draft
            "rating": a.get("rating"),       # "up" | "down" | None  (draft-quality feedback)
            "drafted_include": drafted_include,
            "final_include": final_include,
            "rejected": drafted_include and not final_include,  # Claude included, user dropped
            "posted_ok": bool(res.get("comment_ok")),
            "post_msg": res.get("comment_msg", ""),
        })

    rated_up = [r for r in records if r["rating"] == "up"]
    rated_down = [r for r in records if r["rating"] == "down"]
    edits = [r for r in records if r["edited"]]
    rejected = [r for r in records if r["rejected"]]
    kept_verbatim = [r for r in records if r["final_include"] and not r["edited"]]

    summary = {
        "drafted": len(records),
        "included_final": sum(1 for r in records if r["final_include"]),
        "edited": len(edits),
        "kept_verbatim": len(kept_verbatim),
        "rejected_after_draft": len(rejected),
        "rated_up": len(rated_up),
        "rated_down": len(rated_down),
        "posted_ok": sum(1 for r in records if r["posted_ok"]),
    }

    OUT_FILE.write_text(json.dumps({"summary": summary, "records": records},
                                   indent=2, ensure_ascii=False))

    print(f"Wrote {OUT_FILE}")
    print(f"  drafted={summary['drafted']}  edited={summary['edited']}  "
          f"kept_verbatim={summary['kept_verbatim']}  rejected={summary['rejected_after_draft']}")
    print(f"  👍 {summary['rated_up']}   👎 {summary['rated_down']}   posted_ok={summary['posted_ok']}")
    if summary["edited"] == 0 and summary["rated_up"] == 0 and summary["rated_down"] == 0:
        print("  (no edits and no ratings this run — little to learn from; that's fine.)")


if __name__ == "__main__":
    main()
