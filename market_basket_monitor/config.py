"""
Edit this file to define your basket, alert sensitivity, and delivery settings.
"""

# --- Your basket ---
# Autotrader Group plc (formerly Auto Trader Group) — FTSE 100 constituent, ticker AUTO on LSE.
# Add more Yahoo Finance symbols below if you want to track other FTSE 100 names too,
# e.g. "RR.L" (Rolls-Royce), "TSCO.L" (Tesco).
BASKET_NAME = "Autotrader Group (FTSE 100)"
TICKERS = [
    "AUTO.L",   # Autotrader Group plc
]

# --- Alerts ---
# Trigger an alert if a ticker moves by this % or more (either intraday vs prior close,
# or vs the price recorded at the last check).
ALERT_THRESHOLD_PCT = 3.0

# Send a macOS notification banner when an alert fires (in addition to email).
MACOS_NOTIFICATIONS = True

# --- News ---
# How many news headlines to pull per ticker for alerts / weekly digest.
NEWS_ITEMS_PER_TICKER = 3
# For the weekly digest, only include news from the last N days.
WEEKLY_NEWS_LOOKBACK_DAYS = 7

# --- Email delivery ---
# Server, credentials and addresses are read from environment variables.

# --- Excel dashboard ---
# A workbook written to this path every run, so you can just open it in Excel.
DASHBOARD_FILE = "basket_dashboard.xlsx"

# --- Files ---
STATE_FILE = "last_prices.json"
