# Scraping Progress — Step 1 (Google Maps Reviews)

_Last updated: 2026-09-29_

## Status: 50 / 50 restaurants scraped — COMPLETE. Pizza re-pass complete. Sushi re-pass complete (all 8 under-scraped spots re-harvested from 10 to 210-319 each). 12,043 reviews in DB

**All restaurants done, including both re-passes.** Next up (not yet started): NLP/ML pipeline, RAG chatbot, FastAPI, React dashboard — see `.claude/ProjectOverview.md`.

| Category | Restaurant | Reviews in DB |
|---|---|---|
| Pizza | Joe's Pizza Broadway | 338 |
| Pizza | Rubirosa | 250 |
| Pizza | SIMÒ PIZZA - MIDTOWN | 270 |
| Pizza | John's of Bleecker Street | 270 |
| Pizza | Vito's Slices and Ices | 279 |
| Pizza | NY Pizza Suprema | 370 |
| Pizza | Roma Pizza & Restaurant | 233 |
| Pizza | Square Pizza NYC Times Square | 220 |
| Sushi | Sushi & Co Midtown | 238 |
| Sushi | Sushi Blossoms Chelsea NYC | 230 |
| Sushi | Sushi Nakazawa | 280 |
| Sushi | SUGARFISH by sushi nozawa | 250 |
| Sushi | Sushi Yasaka | 210 |
| Sushi | Sushi & Co Broadway | 269 |
| Sushi | KazuNori The Original Hand Roll Bar | 300 |
| Sushi | Tanoshi Sushi Sake Bar | 319 |
| Burger | Au Cheval | 226 |
| Burger | Black Iron Burger | 261 |
| Burger | Fat Ronnie's Burger Bar | 250 |
| Burger | 5 Napkin Burger | 200 |
| Burger | 7th Street Burger | 290 |
| Burger | Bareburger | 260 |
| Burger | Minetta Tavern | 230 |
| Burger | Handcraft Burgers and Brew | 200 |

**Burger category: complete (12/12).**

| Indian | Cloves Indian Cuisine | 200 |
| Indian | Bombay Chowk | 220 |
| Indian | Bengal Tiger | 210 |
| Indian | Patiala Indian Grill & Bar | 230 |
| Indian | Mughlai Indian Cuisine | 270 |
| Indian | Muna | 210 |
| Indian | Junoon | 220 |
| Indian | Spice Symphony Times Square | 210 |

**Indian category: complete (8/8).**

| Italian | Osteria La Baia | 260 |
| Italian | Marea | 160 |
| Italian | Osteria Nonnino | 240 |
| Italian | Carmine's 44th Street NYC | 210 |
| Italian | Sicily Osteria | 240 |
| Italian | Da Andrea Greenwich Village | 230 |
| Italian | Osteria Barocca | 220 |
| Italian | Felice 56 | 180 |
| Italian | Il Corso | 170 |

**Italian category: complete (9/9).**

**Note:** hit a Google "Server error. Please try again later." mid-scroll on Marea (stopped scroll progress at 160/3,174 reviews). Not a detection block — pace scrolling a bit more conservatively if it recurs. Also saw one transient Supabase connection timeout during insert (Osteria Nonnino) — DB insert isn't committed until the whole batch succeeds, so a failed run doesn't leave partial/duplicate rows; just retry the same insert command.

| Chinese | Jiang Nan NYC | 210 |
| Chinese | The Best Sichuan 21 | 210 |
| Chinese | Nan Xiang Xiao Long Bao | 260 |
| Chinese | The Best Sichuan | 270 |
| Chinese | Chi Restaurant & Bar | 230 |
| Chinese | Mountain House Times Square | 280 |
| Chinese | Tipsy Shanghai | 250 |
| Chinese | Chef Huang | 190 |
| Chinese | Dim Sum Sam | 220 |

**Chinese category: complete (9/9). All 50 restaurants across all 6 categories (pizza, sushi, burger, indian, italian, chinese) are now scraped.**

## How scraping is being done — the "hybrid" method

Fully automated (headless Playwright) scraping of Google Maps reviews is **100% blocked** by Google — confirmed both from this machine and from a fresh GitHub Actions IP. Google detects and throttles automation-driven clicks, specifically on the "Reviews" tab. The workaround in active use:

1. Navigate to `https://www.google.com/maps/search/<name>%20<address>` in the user's own logged-in real Chrome (via the `claude-in-chrome` browser extension/tool), not a headless browser.
2. **The user manually clicks the "Reviews" tab themselves.** This one manual click is what avoids detection — everything else can be automated.
3. A JS snippet is run repeatedly (via the browser tool) that reads currently-rendered review cards (selector `div.jftiEf.fontBodyMedium`, with sub-selectors for reviewer name `.al6Kxe`, rating `[aria-label$="star(s)"]`, date `.rsqaWe`, text `.wiI7pd`) and merges new ones into a persistent `window.__scraped` object on the page, keyed by `reviewer_name + '|' + date_text`, so reviews aren't lost as Google Maps virtualizes/recycles the DOM during scrolling.
4. The user scrolls the reviews panel down; the harvest JS is re-run every few seconds, and the accumulated count is watched (e.g. 30 → 70 → 140 → 200...).
5. Once scrolling is done, a JS snippet builds a `Blob` from `Object.values(window.__scraped)` and triggers a synthetic `<a download>` click to save the JSON to `~/Downloads/`.
6. Overall rating and total review count are grabbed from the page via a small JS query (looks for text nodes matching `\d.\d` for stars and `\d[\d,]* reviews?` for count).
7. The JSON is inserted into Postgres/Supabase via a reusable script (`insert_from_json.py`, currently in the session scratchpad — should be moved into `scraper/` for permanence) which calls `upsert_business()` and `insert_reviews()` from `scraper/google_maps_scraper.py`. Both functions dedupe safely (`ON CONFLICT` on `listing_url` for businesses; uniqueness check on `(business_id, review_text, review_date)` for reviews), so re-uploading a bigger superset after more scrolling only adds the new ones.
8. The downloaded JSON file is deleted after a successful insert.

**Important process note (user correction from earlier in this project):** don't finalize/insert a restaurant's reviews while the user is still actively scrolling for more — confirm they're done first, or keep re-harvesting/re-inserting supersets. The user prefers to scroll far past the initial ~10-30 reviews Google shows by default, often past the 200-review spec target.

**Autonomy note:** once a scraping session is underway, proceed automatically batch-to-batch without re-asking permission each time — only stop to ask if something errors out or gets blocked.

## Key files
- `scraper/google_maps_scraper.py` — selectors + helper functions (`build_search_url`, `parse_relative_date`, `parse_star_rating`, `upsert_business`, `insert_reviews`) reused by the hybrid workflow. Also contains the original fully-automated Playwright flow, which is unreliable for bulk unattended use.
- `db/models.py`, `db/session.py`, `db/create_tables.py` — schema (businesses, reviews_raw, reviews_processed, weekly_stats) already live in Supabase Postgres + pgvector.
- `db/export_to_csv.py` — exports current DB state to `data/scraped_businesses.csv` / `data/scraped_reviews.csv`. **Run as `python -m db.export_to_csv`** (not `python db/export_to_csv.py`) — it imports `db.session`, which only resolves as a package-relative import under `-m`.
- `data/restaurants.csv` — full target list of 50 Manhattan restaurants across 6 categories.
- `scraper/insert_from_json.py` — now permanent in the repo (moved from scratchpad). CLI: `python -m scraper.insert_from_json <json_path> --name "..." --address "..." --category "..." --rating <float> --total-reviews <int> --listing-url "..."` (run with `venv` activated).

## Not started yet
NLP/ML pipeline, RAG chatbot, FastAPI, React dashboard (all later steps in `.claude/ProjectOverview.md`). `GROQ_API_KEY` in `.env` is still empty — needed before the RAG chatbot step.
