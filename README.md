# E-commerce Automation — Portfolio Samples

Three standalone scripts built to demonstrate the kind of small,
well-scoped automation work that sells well on Upwork in the Shopify /
e-commerce niche. None of them are connected to a real store — they're
written exactly the way a paying client would receive them: isolated
config, defensive error handling, and comments that explain the *why*,
not just the *what*.

## What's here

| Script | What it solves | Client pitch |
|---|---|---|
| `shopify_low_stock_alert.py` | Nobody's watching inventory levels | "A Slack message every morning instead of an angry customer email" |
| `shopify_orders_to_sheet.py` | Orders get copy-pasted into a spreadsheet by hand | "Your bookkeeping spreadsheet fills itself in" |
| `price_watcher.py` | Competitor prices get checked manually, if at all | "Know the same day a competitor drops their price" |

## How to use this as a portfolio

1. Create a public GitHub repository (e.g. `ecommerce-automation-samples`).
2. Push this folder as-is.
3. Add a short screen recording or GIF of one script running in
   dry-run mode — seeing it actually work matters more than reading
   the code.
4. Link the repo from your Upwork profile's Portfolio section, one
   entry per script, with the "client pitch" line above as the
   portfolio item description.

## Honesty note

These are demonstration projects, not delivered client work — nothing
here claims otherwise. On Upwork, say exactly that: "sample project
built to show the approach" is a completely normal and credible thing
to have in a new portfolio. Claiming fake client history is the one
thing that gets accounts suspended for cause.

## Setup (for whichever script you're demoing live)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Each script's own docstring has its specific setup steps (API tokens,
service accounts, etc.) and a `--dry-run` or safe default mode where
applicable, so nothing sends a real alert or writes a real row until
you're ready.
