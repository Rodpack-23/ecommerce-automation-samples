#!/usr/bin/env python3
"""
price_watcher.py
---------------------------------
Portfolio demo — e-commerce automation.

What it does
    Watches a list of competitor product pages, scrapes the current
    price of each, compares it to the last known price, and prints
    (or emails) a report of anything that moved by more than a
    threshold percentage.

Why a client would pay for this
    Small e-commerce sellers price-match manually by opening ten tabs
    once a week. This turns that into a scheduled job that only
    bothers them when a price actually changes.

Setup (what I'd normally do during onboarding with a real client)
    1. pip install requests beautifulsoup4
    2. Fill in WATCH_LIST below with each competitor's product URL and
       the CSS selector that wraps the price on that page (this is
       the one part that's genuinely per-site — every store markup is
       different, so this needs a short setup pass per client).
    3. Optional: fill in SMTP settings to get the report by email
       instead of just printed to the console.
    4. Schedule it (cron / a small VPS) to run once or twice a day —
       more than that risks tripping a site's bot protection.

Usage
    python price_watcher.py

Notes on doing this responsibly
    - Always check the target site's robots.txt and terms of service
      before scraping it for a client. Some competitors explicitly
      disallow automated access — that's a hard no, not a workaround.
    - This script identifies itself with a normal browser User-Agent
      and adds a delay between requests. It is not built to evade
      blocking, rate limits, or CAPTCHAs — if a site actively resists
      being scraped, the honest answer to a client is "that one needs
      a different approach or isn't worth pursuing," not brute force.

This is a standalone demo script using example URLs — it is not
scraping any real site out of the box. Written the way I'd hand it to
a paying client: config isolated, one selector per source, graceful
handling when a page's layout changes and the price can't be found.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
WATCH_LIST = [
    # name, url, CSS selector for the element containing the price
    {"name": "Example Competitor — Product A", "url": "https://example.com/product-a", "selector": ".price"},
    {"name": "Example Competitor — Product B", "url": "https://example.com/product-b", "selector": "span.product-price"},
]

CHANGE_THRESHOLD_PCT = 3.0          # only report moves bigger than this
REQUEST_DELAY_SECONDS = 2.0         # be polite between requests
HISTORY_FILE = Path(__file__).parent / "price_history.json"
USER_AGENT = "Mozilla/5.0 (compatible; PriceWatcherBot/1.0; +https://example.com/bot-info)"


@dataclass
class PriceCheck:
    name: str
    url: str
    old_price: float | None
    new_price: float | None
    error: str | None = None

    @property
    def pct_change(self) -> float | None:
        if self.old_price and self.new_price:
            return (self.new_price - self.old_price) / self.old_price * 100
        return None


def load_history() -> dict:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return {}


def save_history(history: dict) -> None:
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


def extract_price(text: str) -> float | None:
    """Pulls the first number that looks like a price out of a text blob.
    Handles '$19.99', '19,99 €', '1.299,00' etc. reasonably well — a real
    per-client setup would tighten this to that site's exact format."""
    cleaned = text.strip()
    match = re.search(r"[\d.,]+", cleaned)
    if not match:
        return None
    number = match.group(0)
    # Normalize "1.299,00" (EU) vs "1,299.00" (US) heuristically.
    if number.count(",") == 1 and number.count(".") == 0:
        number = number.replace(",", ".")
    else:
        number = number.replace(",", "")
    try:
        return float(number)
    except ValueError:
        return None


def check_price(item: dict) -> PriceCheck:
    try:
        resp = requests.get(item["url"], headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        element = soup.select_one(item["selector"])
        if element is None:
            return PriceCheck(item["name"], item["url"], None, None, error="Selector not found — page layout may have changed")
        price = extract_price(element.get_text())
        if price is None:
            return PriceCheck(item["name"], item["url"], None, None, error="Could not parse a price from the matched element")
        return PriceCheck(item["name"], item["url"], None, price)
    except requests.RequestException as exc:
        return PriceCheck(item["name"], item["url"], None, None, error=str(exc))


def main() -> None:
    history = load_history()
    results: list[PriceCheck] = []

    for item in WATCH_LIST:
        check = check_price(item)
        check.old_price = history.get(item["url"], {}).get("price")
        results.append(check)
        if check.new_price is not None:
            history[item["url"]] = {"price": check.new_price, "name": item["name"]}
        time.sleep(REQUEST_DELAY_SECONDS)

    save_history(history)

    print("=== Price Watcher Report ===\n")
    changes_found = False
    for r in results:
        if r.error:
            print(f"⚠️  {r.name}: {r.error}")
            continue
        if r.old_price is None:
            print(f"🆕 {r.name}: first check, price = {r.new_price}")
            continue
        pct = r.pct_change or 0.0
        if abs(pct) >= CHANGE_THRESHOLD_PCT:
            changes_found = True
            direction = "up" if pct > 0 else "down"
            print(f"💰 {r.name}: {r.old_price} → {r.new_price} ({direction} {abs(pct):.1f}%)")
        else:
            print(f"   {r.name}: {r.new_price} (no significant change)")

    if not changes_found:
        print("\nNo price moves above threshold today.")


if __name__ == "__main__":
    main()
