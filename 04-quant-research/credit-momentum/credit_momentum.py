"""Monthly, long-only credit ETF momentum research with auditable allocations."""
from dataclasses import dataclass, asdict
from pathlib import Path
import argparse
import json

import numpy as np
import pandas as pd

ASSETS = ["HYG", "LQD", "SHY"]


@dataclass(frozen=True)
class Config:
    momentum_months: int = 6
    volatility_months: int = 12
    cost_bps: float = 10.0
    max_credit_weight: float = 0.60

    def __post_init__(self):
        if self.momentum_months < 1 or self.volatility_months < 2:
            raise ValueError("Lookbacks must be positive; volatility needs at least 2 months")
        if not np.isfinite(self.cost_bps) or not 0 <= self.cost_bps < 5000:
            raise ValueError("Cost must be finite and between 0 and 5,000 bps")
        if not 0 < self.max_credit_weight <= 1:
            raise ValueError("Credit cap must be in (0, 1]")


def metrics(returns, cash):
    """Monthly CAGR, volatility and Sharpe relative to realised SHY returns."""
    equity = (1 + returns).cumprod()
    peak = equity.cummax().clip(lower=1.0)
    excess = returns - cash
    sd = excess.std(ddof=1)
    return {
        "months": int(len(returns)),
        "total_return": float(equity.iloc[-1] - 1),
        "annualised_return": float(equity.iloc[-1] ** (12 / len(returns)) - 1),
        "annualised_volatility": float(returns.std(ddof=1) * np.sqrt(12)),
        "sharpe_vs_SHY": float(excess.mean() / sd * np.sqrt(12)) if sd > 1e-12 else None,
        "maximum_drawdown_month_end": float((equity / peak - 1).min()),
    }


def run_backtest(prices, config=None, start="2008-05-01", end="2025-12-31"):
    config = config or Config()
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("Prices require a DatetimeIndex")
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("Dates must be unique and sorted")
    if not set(ASSETS).issubset(prices.columns):
        raise ValueError("Prices must include HYG, LQD and SHY")
    prices = prices[ASSETS].copy()
    if prices.empty or not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError("Prices must be finite, positive and aligned without missing data")
    # Retain actual final trading dates; discard a trailing partial calendar month.
    monthly = prices.groupby(prices.index.to_period("M")).tail(1)
    periods = monthly.index.to_period("M")
    if len(periods) > 1 and not np.all(np.diff(periods.astype("int64")) == 1):
        raise ValueError("Monthly history must be contiguous")
    last = prices.index[-1]
    if last < (last + pd.offsets.BMonthEnd(0)):
        monthly = monthly.iloc[:-1]
    returns = monthly.pct_change(fill_method=None)
    momentum = monthly.pct_change(config.momentum_months, fill_method=None)
    volatility = returns.rolling(config.volatility_months).std(ddof=1)
    eligible = (momentum[["HYG", "LQD"]].sub(momentum["SHY"], axis=0) > 0)
    inverse = (1 / volatility[["HYG", "LQD"]].replace(0, np.nan)).where(eligible, 0).fillna(0)
    credit = inverse.div(inverse.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    credit = credit.clip(upper=config.max_credit_weight)
    targets = credit.assign(SHY=1 - credit.sum(axis=1))
    # Previous month's close determines this month's holding; warm-up is excluded.
    ready = volatility.notna().all(axis=1) & momentum.notna().all(axis=1)
    mask = ready.shift(1, fill_value=False) & (monthly.index >= pd.Timestamp(start)) & (monthly.index <= pd.Timestamp(end))
    holdings = targets.shift(1).loc[mask]
    asset_returns = returns.loc[mask]
    if len(holdings) < 12:
        raise ValueError("Need at least 12 evaluation months after warm-up")
    # Turnover includes drift of weights between rebalances, starting from cash.
    def simulate(weights):
        previous = np.array([0., 0., 1.])
        net, turnover = [], []
        for weight, ret in zip(weights.to_numpy(), asset_returns.to_numpy(), strict=True):
            traded = float(np.abs(weight - previous).sum())
            gross = float(weight @ ret)
            cost = traded * config.cost_bps / 10000
            net.append((1 - cost) * (1 + gross) - 1)
            turnover.append(traded)
            previous = weight * (1 + ret) / (1 + gross)
        return pd.Series(net, index=weights.index), pd.Series(turnover, index=weights.index)
    strategy, turnover = simulate(holdings)
    blend_weights = pd.DataFrame(np.tile([.5, .5, 0.], (len(holdings), 1)), index=holdings.index, columns=ASSETS)
    blend, blend_turnover = simulate(blend_weights)
    # Passive HYG is purchased once; no terminal liquidation for any portfolio.
    hyg = asset_returns.HYG.copy()
    hyg.iloc[0] = (1 - 2 * config.cost_bps / 10000) * (1 + hyg.iloc[0]) - 1
    cash = asset_returns.SHY
    frame = holdings.add_prefix("weight_").join(pd.DataFrame({
        "strategy_return": strategy, "blend_return": blend, "HYG_return": hyg,
        "SHY_return": cash, "turnover": turnover, "blend_turnover": blend_turnover,
    }))
    summary = {"config": asdict(config), "start": str(frame.index[0].date()),
               "end": str(frame.index[-1].date()),
               "average_credit_weight": float(holdings[["HYG", "LQD"]].sum(axis=1).mean()),
               "annualised_turnover": float(turnover.mean() * 12), "portfolios": {}}
    for name, series in {"Credit momentum": strategy, "50/50 credit blend": blend, "HYG buy-and-hold": hyg}.items():
        summary["portfolios"][name] = {"full_sample": metrics(series, cash)}
        for label, lo, hi in [("2008-2015", "2008", "2015"), ("2016-2025", "2016", "2025")]:
            subset = series.loc[lo:hi]
            if len(subset) >= 12:
                summary["portfolios"][name][label] = metrics(subset, cash.loc[subset.index])
    return frame, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, help="Adjusted daily prices: Date,HYG,LQD,SHY")
    parser.add_argument("--output-dir", default="reports/default")
    parser.add_argument("--momentum-months", type=int, default=6)
    parser.add_argument("--cost-bps", type=float, default=10)
    args = parser.parse_args()
    prices = pd.read_csv(args.csv, index_col="Date", parse_dates=True)
    frame, summary = run_backtest(prices, Config(momentum_months=args.momentum_months, cost_bps=args.cost_bps))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "monthly_allocations.csv", index_label="Date")
    (output / "metrics.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
