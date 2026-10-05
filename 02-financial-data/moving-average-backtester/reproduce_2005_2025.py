"""Reproduce a fixed-period SPY demonstration using the existing engine."""
from pathlib import Path
import hashlib
import json
import sys
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).parent / "src"))
from melquantlab.data import download_prices, load_prices_from_csv
from melquantlab.backtest import BacktestConfig, run_backtest


def main():
    import yfinance as yf
    root = Path(__file__).parent
    raw = root / "data/raw/spy_2005_2025.csv"
    raw_manifest = raw.with_suffix(".json")
    raw.parent.mkdir(parents=True, exist_ok=True)
    if not raw.exists():
        prices = download_prices("SPY", "2005-01-01", "2026-01-01")
        prices.rename("Close").to_csv(raw, index_label="Date")
        raw_manifest.write_text(json.dumps({
            "retrieved_utc": datetime.now(timezone.utc).isoformat(),
            "yfinance_version": yf.__version__}, indent=2) + "\n")
    prices = load_prices_from_csv(raw)
    result = run_backtest(prices, BacktestConfig())
    output = root / "docs/results_2005_2025"
    output.mkdir(parents=True, exist_ok=True)
    (output / "metrics.json").write_text(json.dumps(result.metrics, indent=2, allow_nan=False) + "\n")
    manifest = {"provider": "Yahoo Finance via yfinance", "ticker": "SPY", "auto_adjust": True,
                "start_inclusive": "2005-01-01", "end_exclusive": "2026-01-01",
                "retrieved_utc": None, "yfinance_version": None,
                "sha256": hashlib.sha256(raw.read_bytes()).hexdigest()}
    if raw_manifest.exists():
        manifest.update(json.loads(raw_manifest.read_text()))
    (output / "data_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(result.metrics, indent=2))


if __name__ == "__main__":
    main()
