"""Download adjusted ETF prices and record their provenance; raw data stays local."""
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone
import yfinance as yf


def main():
    output = Path(__file__).parent / "data/raw"
    output.mkdir(parents=True, exist_ok=True)
    data = yf.download(["HYG", "LQD", "SHY"], start="2007-01-01", end="2026-01-01",
                       auto_adjust=True, progress=False)["Close"]
    data = data[["HYG", "LQD", "SHY"]].dropna()
    if data.empty:
        raise RuntimeError("No aligned ETF data downloaded")
    path = output / "adjusted_prices.csv"
    data.to_csv(path, index_label="Date")
    manifest = {"provider": "Yahoo Finance via yfinance", "auto_adjust": True,
                "start_inclusive": "2007-01-01", "end_exclusive": "2026-01-01",
                "tickers": list(data.columns), "rows": len(data),
                "first_date": str(data.index[0].date()), "last_date": str(data.index[-1].date()),
                "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                "yfinance_version": yf.__version__,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
