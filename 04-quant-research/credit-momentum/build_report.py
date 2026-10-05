"""Generate baseline, fixed sensitivity comparisons and a curated research figure."""
from pathlib import Path
import json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from credit_momentum import Config, run_backtest


def main():
    root = Path(__file__).parent
    output = root / "docs"
    output.mkdir(exist_ok=True)
    prices = pd.read_csv(root / "data/raw/adjusted_prices.csv", index_col="Date", parse_dates=True)
    frame, summary = run_backtest(prices)
    frame.to_csv(output / "monthly_allocations.csv", index_label="Date")
    (output / "metrics.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    sensitivity = []
    for months in (3, 6, 12):
        for cost in (0, 10, 25):
            _, result = run_backtest(prices, Config(momentum_months=months, cost_bps=cost))
            sensitivity.append({"momentum_months": months, "cost_bps": cost,
                                **result["portfolios"]["Credit momentum"]["full_sample"]})
    pd.DataFrame(sensitivity).to_csv(output / "sensitivity.csv", index=False)
    manifest = json.loads((root / "data/raw/manifest.json").read_text())
    (output / "data_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True, gridspec_kw={"height_ratios": [2, 1, 1]})
    for col, label in [("strategy_return", "Credit momentum"), ("blend_return", "50/50 credit blend"), ("HYG_return", "HYG buy-and-hold")]:
        equity = (1 + frame[col]).cumprod()
        axes[0].plot(equity.index, equity, label=label)
        axes[1].plot(equity.index, 100*(equity/equity.cummax().clip(lower=1)-1), label=label)
    axes[0].set_ylabel("Growth of $1")
    axes[0].legend()
    axes[1].set_ylabel("Month-end drawdown (%)")
    axes[2].stackplot(frame.index, frame.weight_HYG, frame.weight_LQD, frame.weight_SHY, labels=["HYG", "LQD", "SHY"], alpha=.8)
    axes[2].set_ylabel("Portfolio weight")
    axes[2].legend(loc="upper left", ncol=3)
    fig.suptitle("MelQuantLab | Systematic Credit Momentum & Portfolio Construction\nMay 2008–December 2025 · monthly returns · 10 bp per traded dollar")
    for ax in axes:
        ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(output / "credit_momentum.png", dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
