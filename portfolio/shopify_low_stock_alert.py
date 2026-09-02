#!/usr/bin/env python3
"""
shopify_low_stock_alert.py
---------------------------------
Portfolio demo — e-commerce automation.

What it does
    Checks every product variant in a Shopify store and sends a Slack
    message listing anything at or below a stock threshold, so nobody
    finds out they're sold out from an angry customer instead of a
    dashboard.

Why a client would pay for this
    Small Shopify stores rarely have someone watching inventory all
    day. This turns a manual "let me go check the admin panel" habit
    into a 6am Slack message that already has the answer.

Setup (what I'd normally do during onboarding with a real client)
    1. Shopify Admin API access token with `read_products` and
       `read_inventory` scopes (Settings > Apps > Develop apps).
    2. A Slack Incoming Webhook URL for the channel that should get
       the alert (api.slack.com/messaging/webhooks).
    3. pip install requests
    4. Fill in the CONFIG block below, or set the equivalent
       environment variables (recommended for anything client-facing —
       never hardcode a real token in a file you hand over).
    5. Run once by hand, then schedule it (cron, a small VPS, or a
       platform like Render/Railway) to run every morning.

Usage
    python shopify_low_stock_alert.py            # sends the real alert
    python shopify_low_stock_alert.py --dry-run   # prints instead of sending

This is a standalone demo script, not connected to any real store.
It is written the way I'd hand it to a paying client: config isolated
at the top, defensive error handling, rate-limit awareness, and a
dry-run mode so nobody has to trust it blind on the first run.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass

import requests

# --------------------------------------------------------------------------
# CONFIG — replace with env vars in any real deployment
# --------------------------------------------------------------------------
SHOPIFY_STORE_DOMAIN = os.environ.get("SHOPIFY_STORE_DOMAIN", "your-store.myshopify.com")
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN", "shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxx")
SHOPIFY_API_VERSION = "2024-10"
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/XXX/YYY/ZZZ")
LOW_STOCK_THRESHOLD = int(os.environ.get("LOW_STOCK_THRESHOLD", "5"))

BASE_URL = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}"
HEADERS = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN, "Content-Type": "application/json"}


@dataclass
class LowStockItem:
    product_title: str
    variant_title: str
    sku: str
    quantity: int


def _get_with_retries(url: str, params: dict | None = None, max_retries: int = 5) -> requests.Response:
    """Shopify enforces a strict rate limit (2 req/sec on standard plans).
    A 429 comes with a Retry-After header — respect it instead of hammering."""
    for attempt in range(max_retries):
        resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
        if resp.status_code == 429:
            wait = float(resp.headers.get("Retry-After", 2))
            print(f"  Rate limited, waiting {wait}s...", file=sys.stderr)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError(f"Gave up after {max_retries} retries on {url}")


def fetch_variants_with_inventory() -> list[LowStockItem]:
    """Walks every product, pulls each variant's inventory quantity,
    and returns the ones at or below the threshold."""
    low_stock: list[LowStockItem] = []
    url = f"{BASE_URL}/products.json"
    params = {"limit": 250, "fields": "id,title,variants"}

    while url:
        resp = _get_with_retries(url, params=params)
        payload = resp.json()
        for product in payload.get("products", []):
            for variant in product.get("variants", []):
                qty = variant.get("inventory_quantity")
                if qty is not None and qty <= LOW_STOCK_THRESHOLD:
                    low_stock.append(
                        LowStockItem(
                            product_title=product["title"],
                            variant_title=variant.get("title", "Default"),
                            sku=variant.get("sku") or "(no SKU)",
                            quantity=qty,
                        )
                    )

        # Shopify paginates via the Link header, not a page number.
        link_header = resp.headers.get("Link", "")
        next_url = None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                next_url = part.split(";")[0].strip("<> ")
        url = next_url
        params = None  # the next_url already carries its own query params

    return sorted(low_stock, key=lambda item: item.quantity)


def build_slack_message(items: list[LowStockItem]) -> dict:
    if not items:
        text = "✅ Inventory check complete — nothing at or below threshold today."
    else:
        lines = [f"⚠️ *{len(items)} variant(s) at or below {LOW_STOCK_THRESHOLD} units:*", ""]
        for item in items:
            lines.append(f"• *{item.product_title}* — {item.variant_title} (SKU {item.sku}): *{item.quantity}* left")
        text = "\n".join(lines)
    return {"text": text}


def send_to_slack(message: dict) -> None:
    resp = requests.post(SLACK_WEBHOOK_URL, json=message, timeout=10)
    resp.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Shopify inventory and alert Slack on low stock.")
    parser.add_argument("--dry-run", action="store_true", help="Print the alert instead of sending it to Slack.")
    args = parser.parse_args()

    print(f"Checking inventory for {SHOPIFY_STORE_DOMAIN} (threshold: {LOW_STOCK_THRESHOLD} units)...")
    try:
        low_stock_items = fetch_variants_with_inventory()
    except requests.HTTPError as exc:
        print(f"Shopify API error: {exc}", file=sys.stderr)
        sys.exit(1)

    message = build_slack_message(low_stock_items)

    if args.dry_run:
        print("\n--- DRY RUN — message that would be sent ---")
        print(message["text"])
    else:
        send_to_slack(message)
        print(f"Sent Slack alert: {len(low_stock_items)} low-stock variant(s).")


if __name__ == "__main__":
    main()
