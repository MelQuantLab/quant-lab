"""Generate the baseline, fixed sensitivity comparisons and research figure."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import pandas as pd

# Use a noninteractive backend so report generation also works on a server.
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 - backend must be selected first

from credit_momentum import Config, run_backtest  # noqa: E402

MOMENTUM_LOOKBACKS = (3, 6, 12)
COST_SCENARIOS_BPS = (0, 10, 25)
PORTFOLIO_LABELS = {
    "strategy_return": "Credit momentum",
    "blend_return": "50/50 credit blend",
    "HYG_return": "HYG buy-and-hold",
}


def build_sensitivity(prices: pd.DataFrame) -> pd.DataFrame:
    """Keep every predefined scenario; do not select a winning parameter set."""
    scenarios = []
    for momentum_months in MOMENTUM_LOOKBACKS:
        for cost_bps in COST_SCENARIOS_BPS:
            config = Config(momentum_months=momentum_months, cost_bps=cost_bps)
            _, summary = run_backtest(prices, config)
            baseline_metrics = summary["portfolios"]["Credit momentum"]["full_sample"]
            scenarios.append(
                {
                    "momentum_months": momentum_months,
                    "cost_bps": cost_bps,
                    **baseline_metrics,
                }
            )
    return pd.DataFrame(scenarios)


def plot_performance(frame: pd.DataFrame, output_path: Path) -> None:
    """Plot equity, month-end drawdown and the baseline portfolio holdings."""
    figure, axes = plt.subplots(
        3,
        1,
        figsize=(11, 10),
        sharex=True,
        gridspec_kw={"height_ratios": [2, 1, 1]},
    )
    equity_axis, drawdown_axis, allocation_axis = axes

    for column, label in PORTFOLIO_LABELS.items():
        equity = (1 + frame[column]).cumprod()
        initial_capital_peak = equity.cummax().clip(lower=1)
        drawdown_percent = 100 * (equity / initial_capital_peak - 1)
        equity_axis.plot(equity.index, equity, label=label)
        drawdown_axis.plot(equity.index, drawdown_percent, label=label)

    equity_axis.set_ylabel("Growth of $1")
    equity_axis.legend()
    drawdown_axis.set_ylabel("Month-end drawdown (%)")
    allocation_axis.stackplot(
        frame.index,
        frame["weight_HYG"],
        frame["weight_LQD"],
        frame["weight_SHY"],
        labels=["HYG", "LQD", "SHY"],
        alpha=0.8,
    )
    allocation_axis.set_ylabel("Portfolio weight")
    allocation_axis.legend(loc="upper left", ncol=3)
    figure.suptitle(
        "MelQuantLab | Systematic Credit Momentum & Portfolio Construction\n"
        "May 2008–December 2025 · monthly returns · 10 bp per traded dollar"
    )
    for axis in axes:
        axis.grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def main() -> None:
    """Build the curated evidence bundle from previously downloaded prices."""
    project_dir = Path(__file__).parent
    raw_dir = project_dir / "data/raw"
    output_dir = project_dir / "docs"
    output_dir.mkdir(exist_ok=True)

    prices = pd.read_csv(
        raw_dir / "adjusted_prices.csv", index_col="Date", parse_dates=True
    )
    frame, summary = run_backtest(prices)
    frame.to_csv(output_dir / "monthly_allocations.csv", index_label="Date")
    summary_json = json.dumps(summary, indent=2, allow_nan=False)
    (output_dir / "metrics.json").write_text(summary_json + "\n", encoding="utf-8")

    build_sensitivity(prices).to_csv(output_dir / "sensitivity.csv", index=False)
    manifest = json.loads((raw_dir / "manifest.json").read_text(encoding="utf-8"))
    (output_dir / "data_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    plot_performance(frame, output_dir / "credit_momentum.png")
    print(summary_json)


if __name__ == "__main__":
    main()
