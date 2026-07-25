"""Export backtest evidence for Excel, VBA and human review."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from .backtest import BacktestResult


def export_result(
    result: BacktestResult,
    output_dir: str | Path,
    *,
    label: str,
) -> dict[str, Path]:
    """Write machine-readable results and charts to one report directory."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    series_path = destination / f"{label}_timeseries.csv"
    metrics_path = destination / f"{label}_metrics.json"
    chart_path = destination / f"{label}_overview.png"

    result.frame.to_csv(series_path, index_label="date")
    metrics_path.write_text(
        json.dumps(result.metrics, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _save_overview_chart(result.frame, chart_path, label)

    return {
        "timeseries": series_path,
        "metrics": metrics_path,
        "chart": chart_path,
    }


def _save_overview_chart(
    frame: pd.DataFrame,
    destination: Path,
    label: str,
) -> None:
    fig, axes = plt.subplots(
        3,
        1,
        figsize=(12, 10),
        sharex=True,
        gridspec_kw={"height_ratios": [2, 2, 1]},
    )

    axes[0].plot(frame.index, frame["price"], label="Adjusted close", color="#17365D")
    axes[0].plot(frame.index, frame["short_sma"], label="Short SMA", color="#D9A441")
    axes[0].plot(frame.index, frame["long_sma"], label="Long SMA", color="#2878B5")
    axes[0].set_title(f"{label}: price and moving averages")
    axes[0].set_ylabel("Price")
    axes[0].legend(loc="upper left")
    axes[0].grid(alpha=0.2)

    axes[1].plot(
        frame.index,
        frame["benchmark_equity"],
        label="Buy and hold",
        color="#7A7A7A",
    )
    axes[1].plot(
        frame.index,
        frame["strategy_equity"],
        label="SMA strategy (net)",
        color="#2878B5",
    )
    axes[1].set_title("Growth of 1.00")
    axes[1].set_ylabel("Equity")
    axes[1].legend(loc="upper left")
    axes[1].grid(alpha=0.2)

    axes[2].fill_between(
        frame.index,
        frame["drawdown"],
        0,
        color="#B4443C",
        alpha=0.75,
    )
    axes[2].set_title("Strategy drawdown")
    axes[2].set_ylabel("Drawdown")
    axes[2].grid(alpha=0.2)

    fig.tight_layout()
    fig.savefig(destination, dpi=160, bbox_inches="tight")
    plt.close(fig)

