"""Reproduce the fixed-period SPY demonstration using the existing engine."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

# Allow this standalone script to run directly from an uninstalled checkout.
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

from melquantlab.backtest import BacktestConfig, run_backtest
from melquantlab.data import download_prices, load_prices_from_csv

DOWNLOAD_START = "2005-01-01"
DOWNLOAD_END_EXCLUSIVE = "2026-01-01"


def write_json(path: Path, content: dict[str, Any]) -> None:
    """Write readable JSON and reject nonfinite performance values."""
    path.write_text(
        json.dumps(content, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def load_or_download_prices(csv_path: Path) -> pd.Series:
    """Reuse local prices, preserving their original retrieval metadata."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if not csv_path.exists():
        prices = download_prices("SPY", DOWNLOAD_START, DOWNLOAD_END_EXCLUSIVE)
        prices.rename("Close").to_csv(csv_path, index_label="Date")
        write_json(
            csv_path.with_suffix(".json"),
            {
                "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                "yfinance_version": yf.__version__,
            },
        )
    return load_prices_from_csv(csv_path)


def build_manifest(csv_path: Path) -> dict[str, Any]:
    """Unknown retrieval details remain null for externally supplied caches."""
    manifest = {
        "provider": "Yahoo Finance via yfinance",
        "ticker": "SPY",
        "auto_adjust": True,
        "start_inclusive": DOWNLOAD_START,
        "end_exclusive": DOWNLOAD_END_EXCLUSIVE,
        "retrieved_utc": None,
        "yfinance_version": None,
        "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
    }
    retrieval_path = csv_path.with_suffix(".json")
    if retrieval_path.exists():
        manifest.update(json.loads(retrieval_path.read_text(encoding="utf-8")))
    return manifest


def main() -> None:
    csv_path = PROJECT_DIR / "data/raw/spy_2005_2025.csv"
    prices = load_or_download_prices(csv_path)
    result = run_backtest(prices, BacktestConfig())

    output_dir = PROJECT_DIR / "docs/results_2005_2025"
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "metrics.json", result.metrics)
    write_json(output_dir / "data_manifest.json", build_manifest(csv_path))
    print(json.dumps(result.metrics, indent=2))


if __name__ == "__main__":
    main()
