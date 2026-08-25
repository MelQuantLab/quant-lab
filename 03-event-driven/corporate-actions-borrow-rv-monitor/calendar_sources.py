"""Structured free calendar adapter for a defined European equity universe."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable

import pandas as pd
import yfinance as yf


CALENDAR_COLUMNS = [
    "event_date",
    "days_remaining",
    "issuer",
    "ticker",
    "sector",
    "market",
    "event_type",
    "source_status",
    "source_url",
]


def _dates(value) -> list[date]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    result = []
    for item in values:
        if isinstance(item, datetime):
            result.append(item.date())
        elif isinstance(item, date):
            result.append(item)
        elif item:
            parsed = pd.to_datetime(item, errors="coerce")
            if not pd.isna(parsed):
                result.append(parsed.date())
    return result


def fetch_watchlist_calendar(
    watchlist: pd.DataFrame,
    as_of: date | None = None,
    horizon_days: int = 7,
    ticker_factory: Callable = yf.Ticker,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return upcoming earnings/ex-dividend dates plus ticker-level exceptions.

    Duplicate vendor tickers are removed before requests are made so the same
    security cannot appear twice merely because it was assigned to two baskets.
    """

    start = as_of or date.today()
    end = start + timedelta(days=horizon_days)
    rows, exceptions = [], []
    unique_universe = watchlist.drop_duplicates(subset=["yahoo_ticker"], keep="first")
    for item in unique_universe.itertuples(index=False):
        try:
            calendar = ticker_factory(item.yahoo_ticker).get_calendar() or {}
            candidates = {
                "Earnings & Guidance": calendar.get("Earnings Date"),
                "Ex-Dividend Date": calendar.get("Ex-Dividend Date"),
                "Dividend Date": calendar.get("Dividend Date"),
            }
            for event_type, raw_dates in candidates.items():
                for event_date in _dates(raw_dates):
                    if start <= event_date <= end:
                        rows.append(
                            {
                                "event_date": event_date,
                                "days_remaining": (event_date - start).days,
                                "issuer": item.issuer,
                                "ticker": item.ticker,
                                "sector": item.sector,
                                "market": item.market,
                                "event_type": event_type,
                                "source_status": "FREE CALENDAR — VERIFY WITH ISSUER",
                                "source_url": f"https://finance.yahoo.com/quote/{item.yahoo_ticker}/calendar/",
                            }
                        )
        except Exception as error:
            exceptions.append({"ticker": item.ticker, "exception": str(error)})
    frame = pd.DataFrame(rows, columns=CALENDAR_COLUMNS)
    if not frame.empty:
        frame = frame.drop_duplicates(subset=["event_date", "ticker", "event_type"]).sort_values(
            ["event_date", "sector", "ticker"]
        )
    return frame.reset_index(drop=True), pd.DataFrame(exceptions, columns=["ticker", "exception"])
