"""
Generates human-friendly display names for BERTopic's raw keyword labels.

BERTopic (topic_model.py) names topics by their top c-TF-IDF keywords, e.g.
"burger, burgers, fries, best" - accurate but not something you'd want in a
dashboard. This is a one-time (or re-run-after-retopic-modeling) batch job:
all distinct topics fit comfortably in a single Groq call, so one request
produces names for all of them at once, which also keeps naming style/length
consistent across topics (a per-topic call wouldn't guarantee that).

Writes to the topic_labels table (topic_id -> display_name), which
api/queries.py left-joins against. reviews_processed.topic_label (the raw
keyword string) is left untouched - this only adds a display layer.
"""

import json
import os

from dotenv import load_dotenv
from groq import Groq
from sqlalchemy import text

from db.session import get_session

load_dotenv()

GROQ_MODEL = "openai/gpt-oss-120b"
UNCATEGORIZED_TOPIC_ID = -1
UNCATEGORIZED_DISPLAY_NAME = "Other / Uncategorized"


def fetch_topics(session):
    rows = session.execute(
        text(
            """
            SELECT topic_id, topic_label, COUNT(*) AS review_count
            FROM reviews_processed
            WHERE topic_label IS NOT NULL
            GROUP BY topic_id, topic_label
            ORDER BY topic_id
            """
        )
    ).fetchall()
    return rows


def build_prompt(topics):
    lines = "\n".join(
        f"{t.topic_id}: {t.topic_label} ({t.review_count} reviews)"
        for t in topics
        if t.topic_id != UNCATEGORIZED_TOPIC_ID
    )
    return f"""You are naming topics for a restaurant-review analytics dashboard.

Each line below is a topic auto-discovered by BERTopic, shown as its id,
its top keywords (comma-separated, most important first), and how many
reviews fall under it. Some topics are about cuisine/dish type (e.g. "pizza,
slice, crust, nyc"), some are about a specific popular staff member the
keyword extraction surfaced (e.g. "roberto, amazing, server, attentive" -
reviews praising a server named Roberto), and a few are about a specific
restaurant feature (e.g. "gluten, gluten free, free, pizza" - gluten-free
options).

Topics:
{lines}

For each topic id, write a short (2-5 word) Title Case display name a
restaurant owner would immediately understand on a dashboard. For a
staff-member topic, name it like "Service: Roberto" or "Server: Luca" (keep
the real name - don't invent one). For a cuisine/dish topic, name the
dish/cuisine itself, not generic words like "great" or "amazing". For a
feature topic (gluten-free, vegan, delivery, etc.), name the feature.

Respond with ONLY a JSON object mapping each topic id (as a string) to its
display name, nothing else. Example shape:
{{"0": "Indian Cuisine & Service", "1": "Pizza & Crust Quality"}}"""


def generate_display_names(topics):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set in .env")
    client = Groq(api_key=api_key)

    prompt = build_prompt(topics)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content.strip()
    parsed = json.loads(raw)
    return {int(k): v.strip() for k, v in parsed.items()}


def upsert_labels(session, topics, display_names):
    rows = []
    for t in topics:
        if t.topic_id == UNCATEGORIZED_TOPIC_ID:
            display_name = UNCATEGORIZED_DISPLAY_NAME
        else:
            # Fall back to the raw label if the model skipped a topic id -
            # better than a missing/blank name in the UI.
            display_name = display_names.get(t.topic_id, t.topic_label)
        rows.append({"topic_id": t.topic_id, "raw_label": t.topic_label, "display_name": display_name})

    for row in rows:
        session.execute(
            text(
                """
                INSERT INTO topic_labels (topic_id, raw_label, display_name)
                VALUES (:topic_id, :raw_label, :display_name)
                ON CONFLICT (topic_id) DO UPDATE
                SET raw_label = EXCLUDED.raw_label, display_name = EXCLUDED.display_name
                """
            ),
            row,
        )
    session.commit()
    return rows


def run():
    session = get_session()
    try:
        topics = fetch_topics(session)
        print(f"{len(topics)} distinct topics found.")
        display_names = generate_display_names(topics)
        rows = upsert_labels(session, topics, display_names)
        print(f"Wrote {len(rows)} topic display names:")
        for r in rows:
            print(f"  [{r['topic_id']}] {r['raw_label'][:50]!r} -> {r['display_name']!r}")
    finally:
        session.close()


if __name__ == "__main__":
    run()
