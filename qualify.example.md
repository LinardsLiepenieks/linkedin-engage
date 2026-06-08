# Post qualification & commenting rules

Claude reads this file every run to decide **which feed posts are worth engaging with**
and **how to draft a comment**. Edit it in plain English — there is no special syntax.
The clearer and more specific you are, the better the drafts.

> **Copy this file to `qualify.md` and make it yours.** Everything below is a template with
> placeholders. The skill itself is generic; *this* file is where you encode who you want to
> reach, how you score posts, and how your comments should sound.

> **Context for the model:** <one or two sentences on who you are and what you do, so comments
> sound like you. e.g. "I'm a founder building X; engagement is top-of-funnel relationship
> building with my audience, not selling — comments should sound like a sharp peer, never a
> vendor.">

> **Primary goal:** <state your goal and target volume per run, e.g. "roughly 15–20 thoughtful
> comments per run for reach", or "only a handful of perfect-fit posts". This decides whether
> the fit criteria below are a hard gate or just a priority booster.>

---

## 1. What I care about (engage when a post is about…)

List the themes/topics you want to engage with, highest priority first. Be concrete.
- **<theme A>** — <what it looks like in a post>
- **<theme B>** — <what it looks like in a post>

Adjacent (relevant, lower priority):
- <looser themes that still get a lighter comment>

## 2. People worth engaging with (author signals)

Strong fit (your ICP / audience):
- <titles, roles, or signals in the author's headline that mark a good fit>
- <e.g. founders, specific job titles, specific industries>

Geography (if relevant — who you actually want to reach, in priority order):
1. <region>
2. <region>

Infer geography from the author's stated location, company, or language. Drop the score for
posts clearly outside your target regions, unless the content is exceptionally on-theme.

## 3. Keywords that boost relevance

<keyword> · <keyword> · <keyword> · <keyword>

## 4. Hard skips (never comment if…)

- It's an obvious ad / promoted / sponsored post.
- It's a "we're hiring" or "open to work" post (unless it's a strong-fit author on-theme).
- Pure self-promotion / engagement-bait ("comment 'YES' for my free kit").
- Politics, religion, or anything controversial / off-topic.
- The post is in a language you don't write comfortably.
- Author is clearly outside your ICP **and** regions, with no thematic relevance.
- The post has near-zero substance (one-line platitudes, reposts with no take).

## 5. Comment style

- **Tone:** <how you want to sound — e.g. sharp, warm, peer-to-peer; casual but structured;
  lightly opinionated; never salesy, never fawning.>
- **Length:** <e.g. short, 1–2 sentences. No walls of text.>
- **Questions:** <e.g. end with a concrete question ~50% of the time, tied to the specific
  post; for the other half just make a sharp observation. Vary it so it doesn't look
  templated.>
- **Milestone / celebration posts** (launches, fundraises, new role): <e.g. a short 1–3 word
  genuine reaction is fine — "Huge. Congrats." — keep it genuine, not generic-spammy.>
- **Do:** add a genuine insight, name a specific tension in their post, or ask one concrete
  question that moves the conversation forward.
- **Don't:** generic praise on substantive posts ("Great post! 🙌"), hashtags, links, emojis
  (unless one feels truly natural), or restating what they already said.
- <any other personal style rules — banned opener phrases, punctuation preferences, how to
  phrase either/or questions, whether to ever pitch (usually: never), sign-off, etc.>

## 6. Scoring & how many to include

The score sets **priority and comment effort**. Rate each post 0–10:
- **Theme fit** (section 1) — on-theme posts score highest and get the most tailored comments.
- **Author fit** (section 2) — ICP title / region boosts the score.
- **Engagement size** — high reactions/comments boost the score (more reach per comment).

<State your inclusion rule clearly. Two common shapes:>
- **Volume:** target ~N includes per run; include the top N by score (skipping only the hard
  skips in §4); if a run has fewer candidates, lower the floor to hit ~N.
- **Selective:** include only posts at/above a threshold (e.g. score ≥ 7), even if that's few.

For everything not included → `include: false`, empty comment, one-line reason.

## 7. Optional actions (besides commenting)

- **Like** posts I comment on? <Yes / No>
- **Follow** the author? <e.g. only if score ≥ 9, or never>

## 8. Prospect collection (optional — delete this section if you don't want a lead list)

Separately from commenting, you can collect the **profiles of people who post about a specific
pain** into a growing lead list (`data/prospects.json` / `prospects.md`). Define the pains that
qualify, each with a short key. Mark a post `pain_match: true` ONLY when it genuinely expresses
one of these pains (not just adjacent chatter), and set `pain_tags` to the matching keys.

- **<pain-key-1>** — <what voicing this pain looks like in a post>
- **<pain-key-2>** — <what voicing this pain looks like in a post>

Be strict: a post must actually voice the pain or work in this space.

### 8a. Prospect tiers & personas (optional)

If you want to prioritise leads, define tiers and personas. When a post is a `pain_match`,
classify the author: set `prospect_tier`, `prospect_persona`, and `pain_magnitude` (1–5).
Leave them null if no taxonomy fits.

- **🟢 HOT / TARGET** (`prospect_persona: "<persona-key>"`) — <who your best, most reachable
  lead is, and the headline/content signals that identify them>
- **🟡 WARM** (`prospect_persona: "<persona-key>"`) — <decent fit, weaker signal>
- **⚪ OBSERVE** (`prospect_persona: "<persona-key>"`) — <high pain but wrong stage / out of
  reach now; record but don't prioritise>

If you don't want prospect collection at all, delete §8/§8a and the skill will skip it.
