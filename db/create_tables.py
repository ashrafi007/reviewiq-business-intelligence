"""Create the ReviewIQ schema: pgvector extension, core tables, weekly_stats view."""

from sqlalchemy import text

from db.models import Base
from db.session import engine

WEEKLY_STATS_SQL = """
CREATE MATERIALIZED VIEW IF NOT EXISTS weekly_stats AS
SELECT
    r.business_id,
    DATE_TRUNC('week', r.review_date)   AS week,
    COUNT(r.id)                         AS review_count,
    AVG(r.review_rating)                AS avg_rating,
    AVG(rp.sentiment_score)             AS avg_sentiment
FROM reviews_raw r
JOIN reviews_processed rp ON rp.review_id = r.id
GROUP BY 1, 2;
"""


def run():
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(WEEKLY_STATS_SQL))
    print("Schema created: businesses, reviews_raw, reviews_processed, weekly_stats")


if __name__ == "__main__":
    run()
