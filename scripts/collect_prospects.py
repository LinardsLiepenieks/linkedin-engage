#!/usr/bin/env python3
"""
collect_prospects.py — Grow a list of people who post about OUR pain.

Reads review.json (which Claude tagged during scoring) and, for every post flagged
`pain_match: true` with an author profile, upserts that author into a persistent prospect
list. These are the high-value leads: people actively talking about design↔engineering
alignment, legacy design tooling, design-in-code, etc.

Outputs (both in data/):
  * prospects.json — canonical, deduped by profile URL, with every matching post seen
  * prospects.md   — human-readable list to skim

Re-runnable: running again merges new matches into the existing list (no duplicates; a
profile seen again gets its new post appended and times_seen incremented).

Usage:
    python scripts/collect_prospects.py                 # from data/review.json
    python scripts/collect_prospects.py --file data/approved.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROSPECTS_JSON = DATA_DIR / "prospects.json"
PROSPECTS_MD = DATA_DIR / "prospects.md"


def today():
    return datetime.now(timezone.utc).date().isoformat()


def load_prospects():
    if not PROSPECTS_JSON.exists():
        return {}
    try:
        data = json.loads(PROSPECTS_JSON.read_text())
    except (json.JSONDecodeError, ValueError):
        return {}
    return {p["profile"]: p for p in data if p.get("profile")}


TIER_RANK = {"hot": 0, "warm": 1, "observe": 2, None: 3, "": 3}
TIER_EMOJI = {"hot": "🟢", "warm": "🟡", "observe": "⚪"}


def sort_key(p):
    # hot first; within a tier, higher pain magnitude, then seen more, then name
    return (TIER_RANK.get(p.get("tier"), 3), -p.get("pain_magnitude", 0),
            -p.get("times_seen", 1), p.get("name", ""))


def write_md(by_profile):
    rows = sorted(by_profile.values(), key=sort_key)
    hot = sum(1 for p in rows if p.get("tier") == "hot")
    warm = sum(1 for p in rows if p.get("tier") == "warm")
    obs = sum(1 for p in rows if p.get("tier") == "observe")
    lines = [
        "# Prospects — people posting about our pain",
        "",
        f"_{len(rows)} profiles · 🟢 {hot} hot · 🟡 {warm} warm · ⚪ {obs} observe · updated {today()}_",
        "",
    ]
    for p in rows:
        emoji = TIER_EMOJI.get(p.get("tier"), "")
        persona = f" · {p['persona']}" if p.get("persona") else ""
        tags = ", ".join(p.get("pain_tags", [])) or "—"
        mag = p.get("pain_magnitude", 0)
        lines.append(f"## {emoji} [{p.get('name', '(unknown)')}]({p['profile']}){persona}")
        if p.get("headline"):
            lines.append(f"*{p['headline']}*")
        lines.append("")
        lines.append(f"- **Pain:** {tags}" + (f" · magnitude {mag}/5" if mag else ""))
        lines.append(f"- **Seen:** {p.get('times_seen', 1)}x · first {p.get('first_seen', '?')}")
        for post in p.get("posts", []):
            snippet = (post.get("snippet") or "").replace("\n", " ")[:120]
            lines.append(f"- [{snippet or 'post'}]({post.get('permalink', '')})")
        lines.append("")
    PROSPECTS_MD.write_text("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(DATA_DIR / "review.json"))
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: {path} not found.", file=sys.stderr)
        sys.exit(1)
    items = json.loads(path.read_text())

    by_profile = load_prospects()
    new_count = 0
    updated_count = 0

    for it in items:
        if not it.get("pain_match"):
            continue
        profile = it.get("author_profile")
        if not profile:
            continue  # can't collect without a profile link
        post = {
            "permalink": it.get("permalink", ""),
            "snippet": (it.get("match_text") or it.get("text", "")[:120]),
        }
        tags = it.get("pain_tags", []) or []
        tier = it.get("prospect_tier") or None
        persona = it.get("prospect_persona") or ""
        magnitude = int(it.get("pain_magnitude") or 0)
        existing = by_profile.get(profile)
        if existing:
            # merge
            existing.setdefault("posts", [])
            if post["permalink"] and post["permalink"] not in [p.get("permalink") for p in existing["posts"]]:
                existing["posts"].append(post)
            existing["pain_tags"] = sorted(set(existing.get("pain_tags", [])) | set(tags))
            # upgrade tier: hot beats warm beats observe beats none
            if TIER_RANK.get(tier, 3) < TIER_RANK.get(existing.get("tier"), 3):
                existing["tier"] = tier
            if persona and not existing.get("persona"):
                existing["persona"] = persona
            existing["pain_magnitude"] = max(existing.get("pain_magnitude", 0), magnitude)
            existing["times_seen"] = existing.get("times_seen", 1) + 1
            updated_count += 1
        else:
            by_profile[profile] = {
                "profile": profile,
                "name": it.get("author", ""),
                "headline": it.get("headline", ""),
                "tier": tier,
                "persona": persona,
                "pain_magnitude": magnitude,
                "pain_tags": sorted(set(tags)),
                "posts": [post] if post["permalink"] or post["snippet"] else [],
                "first_seen": today(),
                "times_seen": 1,
            }
            new_count += 1

    out = sorted(by_profile.values(), key=sort_key)
    PROSPECTS_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    write_md(by_profile)
    hot = sum(1 for p in out if p.get("tier") == "hot")
    warm = sum(1 for p in out if p.get("tier") == "warm")
    print(f"Prospects: +{new_count} new, {updated_count} updated → {len(out)} total "
          f"(🟢 {hot} hot, 🟡 {warm} warm)")
    print(f"  {PROSPECTS_JSON}")
    print(f"  {PROSPECTS_MD}")


if __name__ == "__main__":
    main()
