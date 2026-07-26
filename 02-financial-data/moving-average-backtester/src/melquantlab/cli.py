"""Command-line entry point for the SMA backtester."""

from __future__ import annotations

import argparse
from pathlib import Path

from .backtest import BacktestConfig, run_backtest
from .data import download_prices, load_prices_from_csv
from .reporting import export_result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a long-or-cash SMA crossover backtest."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--ticker", help="Yahoo Finance ticker, for example SPY")
    source.add_argument("--csv", type=Path, help="CSV with Date and Close columns")
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end", default="2026-07-25")
    parser.add_argument("--short-window", type=int, default=50)
    parser.add_argument("--long-window", type=int, default=200)
    parser.add_argument("--transaction-cost-bps", type=float, default=5.0)
    parser.add_argument("--risk-free-rate", type=float, default=0.0)
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    parser.add_argument("--label", help="Output filename label")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.csv:
        prices = load_prices_from_csv(args.csv)
        default_label = args.csv.stem
    else:
        prices = download_prices(args.ticker, args.start, args.end)
        default_label = args.ticker.upper().replace("^", "")

    config = BacktestConfig(
        short_window=args.short_window,
        long_window=args.long_window,
        transaction_cost_bps=args.transaction_cost_bps,
        annual_risk_free_rate=args.risk_free_rate,
    )
    result = run_backtest(prices, config)
    paths = export_result(
        result,
        args.output_dir,
        label=args.label or default_label,
    )

    print("Backtest complete")
    for name, value in result.metrics.items():
        print(f"{name}: {value}")
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
