"""
Target list: 50 Manhattan restaurants across 6 categories.

Fill in `name` and `address` for each row in data/restaurants.csv (open it in
Excel/Sheets). The scraper searches Google Maps for "<name> <address>", which
reliably resolves straight to the business's listing page. Rows with a blank
name or address are skipped until filled in.
"""

import csv
import os

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "restaurants.csv")


def load_restaurants(csv_path=CSV_PATH):
    with open(csv_path, newline="", encoding="utf-8") as f:
        return [
            {"name": row["name"].strip(), "address": row["address"].strip(), "category": row["category"].strip()}
            for row in csv.DictReader(f)
        ]


RESTAURANTS = load_restaurants()


def get_pending_entries():
    """Restaurants that still need name/address filled in."""
    return [r for r in RESTAURANTS if not r["name"] or not r["address"]]


def get_ready_entries():
    """Restaurants ready to scrape."""
    return [r for r in RESTAURANTS if r["name"] and r["address"]]
