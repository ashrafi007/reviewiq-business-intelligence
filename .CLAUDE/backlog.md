# Known issues / backlog

_Last updated: 2026-10-05_

## 1. Fake-review detector (`is_suspicious`) — UI reframed 2026-10-05, model itself untouched

Deployed (`ml/models/fake_review_model_v2.pkl`), flags 315/12,043 reviews (2.6%), precision ~0.077 at its tuned threshold — most flags are likely false positives. Full detail in `.CLAUDE/ml_progress.md`.

**Done:** dashboard copy reframed to stop implying a confident fraud detector — "Suspicious reviews" → "Unusual-style reviews" stat card (Overview), "⚠️ flagged" (red) → "⚠️ unusual style" (amber) badge + filter label (Review Feed), both now carry a hover tooltip stating the real ~8% precision. No model/backend change — purely a copy/color fix in `frontend/src/pages/Overview.jsx`, `frontend/src/pages/ReviewFeed.jsx`, `frontend/src/components/StatCard.jsx` (added a `title` prop).

**Still open, real model-quality improvements, roughly by effort:**
- Hand-label a small sample to get a real precision number (current metric is measured against a heuristic label, not verified fraud) — cheapest, most informative next step.
- Add reviewer-level features (posting frequency, duplicate/near-duplicate text across reviews, burst-posting patterns) — not used at all currently; probably the strongest real fraud signal available.

## 2. Topic labels — FIXED 2026-10-05

Topics used to show as BERTopic's raw auto c-TF-IDF output, e.g. `"burger, burgers, fries, best"`. Flagged originally in `.CLAUDE/nlp_progress.md` during M3.

**Fix:** new `nlp/topic_labels.py` — one batch Groq call sends all 35 distinct topics (id, keyword label, review count) and gets back a clean 2-5 word display name for each (e.g. `"Best Burgers & Fries"`, staff-driven clusters named `"Server: Roberto"`). Stored in a new `topic_labels` table (`db/models.py::TopicLabel`, topic_id PK). `api/queries.py` left-joins against it everywhere `topic_label` is returned (`get_overview`'s topic_distribution, `get_reviews`, `get_trends`'s topic_trends) via `COALESCE(tl.display_name, rp.topic_label)`, so the raw keyword string stays as a fallback and the underlying `reviews_processed.topic_label` column is untouched (lineage preserved). Frontend needed no prop/shape changes since the API returns the clean name under the same `topic_label` key — only removed two now-unnecessary `.split(',')[0]` truncation hacks (`ReviewFeed.jsx`, `Trends.jsx`) that existed to shorten the old comma-joined raw labels.

Re-run `python -m nlp.topic_labels` any time `nlp/topic_model.py` is re-run and topic ids/keywords change — it's an upsert, safe to re-run.

**Still open / structural, not addressed by this fix:** because topic discovery was fully unsupervised across 6 cuisines, most discovered topics are **cuisine identity** (pizza/sushi/burger/...) or even specific-staff-member clusters (Roberto, Luca) rather than aspect-based (service/price/ambiance) categories, and a few small clusters surfaced a specific restaurant's name as a top keyword (e.g. "Rubirosa Tie Dye", "Mountain House Authentic") because that cluster happened to be dominated by one restaurant's reviews — the LLM named these as best it could from the keywords given, but they're inherently odder topics than the cuisine ones. This is a topic-modeling-granularity issue, not a labeling bug.
