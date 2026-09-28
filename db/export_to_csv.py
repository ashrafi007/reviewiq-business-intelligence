"""Export the current businesses and reviews_raw tables to CSV for review."""

import csv
import os

from sqlalchemy import text

from db.session import engine

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

BUSINESSES_SQL = """
SELECT id, name, category, address, city, overall_rating, total_reviews, listing_url, scraped_at
FROM businesses
ORDER BY id;
"""

REVIEWS_SQL = """
SELECT r.id, r.business_id, b.name AS business_name, r.review_rating, r.review_text,
       r.review_date, r.reviewer_name, r.has_owner_response, r.scraped_at
FROM reviews_raw r
JOIN businesses b ON b.id = r.business_id
ORDER BY r.business_id, r.review_date DESC;
"""


def export_query(sql, out_path):
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = result.fetchall()
        columns = result.keys()
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
    return len(rows)


def run():
    os.makedirs(OUT_DIR, exist_ok=True)
    b_count = export_query(BUSINESSES_SQL, os.path.join(OUT_DIR, "scraped_businesses.csv"))
    r_count = export_query(REVIEWS_SQL, os.path.join(OUT_DIR, "scraped_reviews.csv"))
    print(f"Exported {b_count} businesses -> data/scraped_businesses.csv")
    print(f"Exported {r_count} reviews -> data/scraped_reviews.csv")


if __name__ == "__main__":
    run()
