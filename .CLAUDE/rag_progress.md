# RAG Chatbot Progress (Step 4 / M6)

_Last updated: 2026-10-04_

## M6 — RAG Chatbot: COMPLETE

`rag/chatbot.py` — `ask(question, business_id, top_k=10)` returns `{"answer": str, "sources": [...]}`. Tested end-to-end against the live DB with real Groq calls, not mocked.

**`GROQ_API_KEY` is now set in `.env`.**

### Model substitution (spec is stale)

The spec's model name (`llama-3.3-70b-versatile`) **no longer exists** in Groq's catalog — confirmed live via `client.models.list()`, not assumed. Groq's hosted-model catalogs change over time; don't trust a model name from an older doc/spec without checking availability first.

Currently using **`openai/gpt-oss-120b`** (Groq's largest general-purpose chat model at time of writing). If this notebook/project is revisited later and chat calls start failing with `model_not_found`, re-run `client.models.list()` to see what's current and swap `GROQ_MODEL` in `rag/chatbot.py`.

**Non-obvious gotcha:** `gpt-oss` models do internal reasoning before producing the visible answer, and will silently return an **empty string** if `max_tokens` is too tight — confirmed directly: `max_tokens=20` → `''`, `max_tokens=200` → `'OK.'`. `rag/chatbot.py` uses `MAX_TOKENS = 1024` to leave headroom for this. If answers start coming back empty, check this first before assuming the prompt or retrieval is broken.

(`qwen/qwen3.8-27b` was also tested and works fine even at low token budgets, no reasoning-overhead issue — a viable faster/cheaper fallback if gpt-oss-120b's latency or cost becomes a problem.)

### pgvector gotcha (same pattern as nlp/embeddings.py)

Semantic search needs `pgvector.psycopg2.register_vector()` called on the **raw** DBAPI connection before querying with a numpy embedding as a bound parameter, or psycopg2 can't serialize it to the `vector` type correctly. Must unwrap SQLAlchemy's `_ConnectionFairy` proxy via `.dbapi_connection` first — `session.connection().connection` alone fails with a confusing `TypeError` deep inside psycopg2. See `rag/chatbot.py::search_reviews`.

### Real test results (not fabricated)

**Q: "What do customers love most about this pizza place?"** (business_id=1, Joe's Pizza Broadway)
- Similarity scores: 0.71-0.75 (strong — direct semantic match between question and review content)
- Answer correctly grounded in retrieved reviews: crispy crust, bold flavor, friendly staff
- Retrieval honestly included a 2★ and 3★ review alongside 5★s — not cherry-picking only positive content

**Q: "Why might my rating have dropped recently?"** (same business)
- Similarity scores: 0.24-0.40 (notably weaker — this is an abstract/meta question that doesn't map as directly onto review text via a lightweight general-purpose embedding model like MiniLM)
- Still functionally correct: retrieval surfaced genuinely relevant complaints (hour-long waits, cold/tasteless pizza, rude service, dirty environment) and the answer summarized them accurately
- **Takeaway for the dashboard:** direct factual questions ("what do people say about X") will have much higher-confidence retrieval than indirect/causal questions ("why did Y happen"). Worth keeping in mind if source-similarity scores are ever surfaced in the UI — a low score on a causal question isn't necessarily a failure.

### Data quality note carried over from M5

Some retrieved reviews show `review_rating = None` in the sources list — these are the 318 reviews (2.6%) with `NULL review_rating` from the scraper's occasional star-rating parse miss (see `.CLAUDE/ml_progress.md`). Handled gracefully (no crash), just displays as `None★`. Not fixed here; same root cause as before.

### Bug found during user testing of the M8 chatbot page, fixed 2026-10-05: irrelevant sources shown

**Symptom:** the "sources" panel sometimes showed reviews that were clearly unrelated to the question — e.g. a glowing 5★ review praising a server shown as a source for "What are customers complaining about most?"

**Root cause:** `search_reviews()` always returned the top-`K` (10) nearest reviews by raw cosine similarity, with every one of them surfaced to the frontend as a "source," regardless of whether the LLM actually used it. Cosine similarity on this embedding model captures *topical* overlap ("service", "server") but not *stance/sentiment* — a rave review and a complaint about the same topic (service) embed close together, so a complaints question pulls in praise too.

**A fixed similarity threshold doesn't work here** — tested empirically: a cutoff high enough to drop the irrelevant ~0.28-0.33-similarity reviews on a "complaints" question also wiped out every source on a "how has sentiment changed recently" question, whose *genuinely used, correct* sources scored only 0.15-0.20. Relevance-to-similarity-score mapping is query-type dependent; no single scalar threshold separates signal from noise across question types.

**Fix:** `build_prompt()` now numbers each retrieved review (`[1]`, `[2]`, ...) and instructs the model to end its answer with a machine-parseable `USED: 1,4,7` (or `USED: none`) line naming only the reviews it actually relied on. `parse_used_sources()` strips that line from the visible answer and resolves it back to the real review rows — only those become the returned `sources`. Falls back to a similarity-floor heuristic (`FALLBACK_MIN_SIMILARITY = 0.35`, top 3) only if the model doesn't follow the format (rare, not observed in testing). Also had to explicitly tell the model not to reference the bracket numbers inside the visible answer text — first version leaked "(reviews 1,3,4)" into the prose.

**Verified** against 4 real questions (complaints, sentiment-trend, parking/seating, fake-reviews): complaints question went from 10 sources (including an irrelevant rave review) to 5, all genuinely about complaints; sentiment-trend question correctly kept 9/10 low-similarity-but-actually-used sources (would have broken under a threshold-only fix); fake-reviews question now returns an honest "no clear evidence of fraud" answer with sources cited as evidence of genuineness, instead of the old version's speculative, under-evidenced fraud narrative.

## Not started yet
- M7 — FastAPI (`POST /api/chat` should call `rag.chatbot.ask()` directly)
- M8 — React dashboard
- M9 — GitHub Actions cron (note: `ml/` models are now notebook-only, see `.CLAUDE/ml_progress.md` structural note — will need rework for headless scheduling)

## Key files
- `rag/chatbot.py` — `ask(question, business_id, top_k=10)`. Also runnable standalone: `python -m rag.chatbot <business_id> "<question>"`.
- `.env` — `GROQ_API_KEY` now set.
