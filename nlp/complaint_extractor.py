"""
Complaint keyword matching + food entity extraction over reviews_raw -> reviews_processed.

Two independent signals per review:
- complaints: keyword/phrase matches against a curated complaint taxonomy (substring
  match on lowercased text - simple and auditable, no ML needed for this part).
- entities: word-boundary matches against FOOD_GAZETTEER, not spaCy NER. The spec's
  original approach (spaCy en_core_web_sm, PRODUCT label) was tested first and
  rejected: en_core_web_sm is a small general-purpose model with no food-specific
  training and its PRODUCT label essentially never fires on dish names ("pizza",
  "sushi" tagged nothing). The gazetteer below was built from two sources: (1) a
  frequency analysis of actual nouns across all 12,043 reviews (see
  .CLAUDE/nlp_progress.md for the full top-150 list this was drawn from), filtered
  down to genuinely food/drink/dish terms; (2) a curated supplement of multi-word
  dish names for this dataset's 6 cuisines (pizza/sushi/burger/indian/italian/
  chinese) that single-noun frequency counting can't catch, e.g. "soup dumplings",
  "peking duck", "hand rolls".
"""

import re

from sqlalchemy import text
from tqdm import tqdm

from db.retry import bulk_upsert
from db.session import get_session

BATCH_SIZE = 1000

COMPLAINT_KEYWORDS = {
    "cold food": ["cold", "not hot", "lukewarm", "stone cold"],
    "slow service": ["slow", "took forever", "waited", "45 minutes", "an hour"],
    "rude staff": ["rude", "impolite", "attitude", "disrespectful", "unprofessional"],
    "wrong order": ["wrong order", "missing", "not what i ordered", "mixed up"],
    "overpriced": ["overpriced", "expensive", "not worth", "ripoff", "too much"],
    "bad packaging": ["spilled", "leaking", "broken", "bag was wet"],
    "small portions": ["small portion", "tiny", "not enough food", "barely any"],
    "dirty": ["dirty", "unclean", "gross", "disgusting", "cockroach"],
    "noisy": ["too loud", "noisy", "can't hear", "music too loud"],
}

FOOD_GAZETTEER = sorted(
    {
        # From frequency analysis of the actual corpus (top-150 nouns, filtered to food/drink)
        "pizza", "burger", "burgers", "sushi", "chicken", "slice", "slices", "dishes",
        "sauce", "meal", "fries", "fish", "cheese", "soup", "rice", "omakase",
        "dumplings", "crust", "pasta", "duck", "pork", "rolls", "roll", "beef",
        "salad", "meat", "dessert", "bread", "pepperoni", "shrimp", "vegan", "pie",
        "onion", "salmon", "egg", "toppings", "appetizer", "wine", "cocktails",
        "drinks",
        # Pizza
        "margherita", "mozzarella", "marinara", "calzone", "tie dye pizza",
        "grandma slice", "sicilian",
        # Sushi / Japanese
        "sashimi", "nigiri", "hand roll", "hand rolls", "maki", "tempura", "miso",
        "edamame", "unagi", "uni", "wasabi", "soy sauce",
        # Burger
        "cheeseburger", "bacon", "patty", "bun", "milkshake", "onion rings",
        # Indian
        "naan", "curry", "tikka", "tikka masala", "biryani", "samosa", "dal",
        "paneer", "tandoori", "masala", "chutney", "lassi", "butter chicken", "saag",
        # Italian
        "carbonara", "risotto", "tiramisu", "gelato", "bruschetta", "gnocchi",
        "lasagna", "ravioli", "parmesan", "prosciutto", "burrata", "cacio e pepe",
        # Chinese
        "soup dumplings", "xiao long bao", "dim sum", "wonton", "lo mein",
        "fried rice", "peking duck", "kung pao", "szechuan", "dan dan noodles",
        "bao", "scallion pancake", "noodles",
        # General
        "entree", "side dish", "cocktail", "beer", "sake",
    }
)

# Longest phrase first so e.g. "soup dumplings" is checked before "soup"/"dumplings" alone.
_FOOD_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(term) for term in sorted(FOOD_GAZETTEER, key=len, reverse=True)) + r")\b"
)


def extract_complaints(text_lower):
    found = []
    for complaint, keywords in COMPLAINT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(complaint)
    return found


def extract_entities(text_lower):
    return sorted(set(_FOOD_PATTERN.findall(text_lower)))


def fetch_pending(session, limit):
    return session.execute(
        text(
            """
            SELECT r.id, r.review_text
            FROM reviews_raw r
            JOIN reviews_processed rp ON rp.review_id = r.id
            WHERE rp.complaints IS NULL
            ORDER BY r.id
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).fetchall()


def upsert_complaints(session, payload):
    rows = [(p["review_id"], p["complaints"], p["entities"]) for p in payload]
    bulk_upsert(
        session,
        """
        INSERT INTO reviews_processed (review_id, complaints, entities)
        VALUES %s
        ON CONFLICT (review_id) DO UPDATE
        SET complaints = EXCLUDED.complaints,
            entities = EXCLUDED.entities
        """,
        rows,
    )


def run(batch_size=BATCH_SIZE):
    session = get_session()
    total = session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM reviews_raw r
            JOIN reviews_processed rp ON rp.review_id = r.id
            WHERE rp.complaints IS NULL
            """
        )
    ).scalar()

    if total == 0:
        print("No pending reviews — complaints/entities already up to date.")
        return

    print(f"{total} reviews pending.")

    with tqdm(total=total, desc="Complaints/Entities") as pbar:
        while True:
            rows = fetch_pending(session, batch_size)
            if not rows:
                break
            payload = []
            for r in rows:
                text_lower = (r.review_text or "").lower()
                payload.append(
                    {
                        "review_id": r.id,
                        "complaints": extract_complaints(text_lower),
                        "entities": extract_entities(text_lower),
                    }
                )
            upsert_complaints(session, payload)
            pbar.update(len(rows))

    session.close()
    print("Complaint/entity extraction complete.")


if __name__ == "__main__":
    run()
