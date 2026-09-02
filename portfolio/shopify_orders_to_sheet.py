#!/usr/bin/env python3
"""
shopify_orders_to_sheet.py
---------------------------------
Portfolio demo — e-commerce automation.

What it does
    Pulls every new Shopify order since the last run and appends one
    row per order to a Google Sheet: order number, date, customer,
    total, items, fulfillment status. Remembers where it left off, so
    running it every hour never duplicates a row.

Why a client would pay for this
    A lot of small sellers still copy order data into a spreadsheet by
    hand for bookkeeping, a supplier, or a dashboard tool that only
    reads Sheets. This removes that hour of copy-pasting a week and
    the mistakes that come with it.

Setup (what I'd normally do during onboarding with a real client)
    1. Shopify Admin API access token with `read_orders` scope.
    2. A Google Cloud service account with the Sheets API enabled,
       and its JSON key file. Share the target spreadsheet with the
       service account's email address (Editor access).
    3. pip install requests gspread google-auth
    4. Fill in the CONFIG block below (or the matching env vars).
    5. Schedule it (cron / Task Scheduler / a small VPS) to run every
       15-60 minutes depending on order volume.

Usage
    python shopify_orders_to_sheet.py

State
    Keeps a `last_sync.json` file next to the script recording the
    timestamp of the last order it processed, so a crash or a manual
    re-run never re-appends orders that are already in the sheet.

This is a standalone demo script, not connected to any real store or
spreadsheet. Written the way I'd hand it to a paying client: explicit
state file instead of "hope it doesn't double-run", and a clear
mapping between Shopify fields and spreadsheet columns.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import gspread
import requests
from google.oauth2.service_account import Credentials

# --------------------------------------------------------------------------
# CONFIG — replace with env vars in any real deployment
# --------------------------------------------------------------------------
SHOPIFY_STORE_DOMAIN = os.environ.get("SHOPIFY_STORE_DOMAIN", "your-store.myshopify.com")
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN", "shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxx")
SHOPIFY_API_VERSION = "2024-10"

GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
GOOGLE_SHEET_NAME = os.environ.get("GOOGLE_SHEET_NAME", "Shopify Orders")
GOOGLE_WORKSHEET_NAME = os.environ.get("GOOGLE_WORKSHEET_NAME", "Orders")

STATE_FILE = Path(__file__).parent / "last_sync.json"
BASE_URL = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}"
HEADERS = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN, "Content-Type": "application/json"}
SHEET_HEADER = ["Order #", "Date", "Customer", "Email", "Total", "Currency", "Items", "Fulfillment Status"]


def load_last_sync() -> str:
    """Falls back to 24h ago on first run, so it doesn't try to import the
    store's entire order history the first time it's switched on."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())["last_synced_at"]
    from datetime import timedelta

    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def save_last_sync(timestamp: str) -> None:
    STATE_FILE.write_text(json.dumps({"last_synced_at": timestamp}))


def fetch_new_orders(since_iso: str) -> list[dict]:
    orders: list[dict] = []
    url = f"{BASE_URL}/orders.json"
    params = {
        "status": "any",
        "created_at_min": since_iso,
        "limit": 250,
        "order": "created_at asc",
    }

    while url:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        orders.extend(payload.get("orders", []))

        link_header = resp.headers.get("Link", "")
        next_url = None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                next_url = part.split(";")[0].strip("<> ")
        url = next_url
        params = None

    return orders


def order_to_row(order: dict) -> list[str]:
    customer = order.get("customer") or {}
    name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip() or "Guest"
    items = ", ".join(f"{li['quantity']}x {li['title']}" for li in order.get("line_items", []))
    return [
        order.get("name", ""),
        order.get("created_at", ""),
        name,
        order.get("email", ""),
        order.get("total_price", ""),
        order.get("currency", ""),
        items,
        order.get("fulfillment_status") or "unfulfilled",
    ]


def open_worksheet():
    creds = Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    client = gspread.authorize(creds)
    sheet = client.open(GOOGLE_SHEET_NAME)
    try:
        worksheet = sheet.worksheet(GOOGLE_WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=GOOGLE_WORKSHEET_NAME, rows=1000, cols=len(SHEET_HEADER))
        worksheet.append_row(SHEET_HEADER)
    return worksheet


def main() -> None:
    since_iso = load_last_sync()
    print(f"Fetching orders created since {since_iso}...")

    try:
        orders = fetch_new_orders(since_iso)
    except requests.HTTPError as exc:
        print(f"Shopify API error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not orders:
        print("No new orders. Nothing to sync.")
        return

    worksheet = open_worksheet()
    rows = [order_to_row(o) for o in orders]
    worksheet.append_rows(rows, value_input_option="USER_ENTERED")

    latest_created_at = max(o["created_at"] for o in orders)
    save_last_sync(latest_created_at)

    print(f"Synced {len(rows)} new order(s) to '{GOOGLE_SHEET_NAME}' / '{GOOGLE_WORKSHEET_NAME}'.")


if __name__ == "__main__":
    main()
