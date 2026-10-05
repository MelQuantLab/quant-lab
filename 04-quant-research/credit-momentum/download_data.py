"""Download adjusted ETF prices and record provenance; raw data stays local."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from credit_momentum import ASSETS

DOWNLOAD_START = "2007-01-01"
DOWNLOAD_END_EXCLUSIVE = "2026-01-01"


def download_adjusted_prices() -> pd.DataFrame:
    """Retain dates where all three ETFs have an adjusted closing price."""
    downloaded = yf.download(
        ASSETS,
        start=DOWNLOAD_START,
        end=DOWNLOAD_END_EXCLUSIVE,
        auto_adjust=True,
        progress=False,
    )
    prices = downloaded["Close"][ASSETS].dropna()
    if prices.empty:
        raise RuntimeError("No aligned ETF data downloaded")
    return prices


def build_manifest(prices: pd.DataFrame, csv_path: Path) -> dict[str, Any]:
    """Identify the downloaded sample and exact local CSV used in the run."""
    return {
        "provider": "Yahoo Finance via yfinance",
        "auto_adjust": True,
        "start_inclusive": DOWNLOAD_START,
        "end_exclusive": DOWNLOAD_END_EXCLUSIVE,
        "tickers": list(prices.columns),
        "rows": len(prices),
        "first_date": str(prices.index[0].date()),
        "last_date": str(prices.index[-1].date()),
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "yfinance_version": yf.__version__,
        "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
    }


def main() -> None:
    output_dir = Path(__file__).parent / "data/raw"
    output_dir.mkdir(parents=True, exist_ok=True)

    prices = download_adjusted_prices()
    csv_path = output_dir / "adjusted_prices.csv"
    prices.to_csv(csv_path, index_label="Date")

    manifest = build_manifest(prices, csv_path)
    manifest_json = json.dumps(manifest, indent=2)
    (output_dir / "manifest.json").write_text(manifest_json + "\n", encoding="utf-8")
    print(manifest_json)


if __name__ == "__main__":
    main()
