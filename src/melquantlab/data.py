"""Market-data loading and validation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_prices_from_csv(
    path: str | Path,
    *,
    date_column: str = "Date",
    price_column: str = "Close",
) -> pd.Series:
    """Load a price series from a CSV file."""

    frame = pd.read_csv(path)
    missing = {date_column, price_column} - set(frame.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")
    frame[date_column] = pd.to_datetime(frame[date_column], errors="raise")
    return frame.set_index(date_column)[price_column].rename("price")


def download_prices(
    ticker: str,
    start: str,
    end: str,
) -> pd.Series:
    """Download adjusted closing prices from Yahoo Finance."""

    if not ticker.strip():
        raise ValueError("ticker cannot be blank")

    import yfinance as yf

    frame = yf.download(
        ticker,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        actions=False,
    )
    if frame.empty:
        raise ValueError(f"no price data returned for {ticker}")

    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.rename("price")
