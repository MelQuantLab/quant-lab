"""Monthly, long-only credit ETF momentum with auditable allocations.

The engine takes adjusted prices and returns monthly holdings, net portfolio
returns and summary statistics. Downloads and chart generation live separately.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CREDIT_ASSETS = ["HYG", "LQD"]
DEFENSIVE_ASSET = "SHY"
ASSETS = [*CREDIT_ASSETS, DEFENSIVE_ASSET]
MONTHS_PER_YEAR = 12
BASIS_POINTS_PER_UNIT = 10_000
MIN_EVALUATION_MONTHS = 12
SUBPERIODS = [("2008-2015", "2008", "2015"), ("2016-2025", "2016", "2025")]

MetricValues = dict[str, int | float | None]


@dataclass(frozen=True)
class Config:
    """Fixed signal lookbacks, trading costs and per-ETF allocation cap."""

    momentum_months: int = 6
    volatility_months: int = 12
    cost_bps: float = 10.0
    max_credit_weight: float = 0.60

    def __post_init__(self) -> None:
        if self.momentum_months < 1 or self.volatility_months < 2:
            raise ValueError(
                "Lookbacks must be positive; volatility needs at least 2 months"
            )
        if not np.isfinite(self.cost_bps) or not 0 <= self.cost_bps < 5000:
            raise ValueError("Cost must be finite and between 0 and 5,000 bps")
        if not 0 < self.max_credit_weight <= 1:
            raise ValueError("Credit cap must be in (0, 1]")


def metrics(returns: pd.Series, cash: pd.Series) -> MetricValues:
    """Calculate monthly performance, using SHY as the excess-return reference.

    The initial capital of one is included in the drawdown peak. A portfolio
    identical to SHY has no excess-return volatility, so its Sharpe is undefined.
    """
    equity = (1 + returns).cumprod()
    peak = equity.cummax().clip(lower=1.0)
    excess_returns = returns - cash
    excess_volatility = excess_returns.std(ddof=1)
    sharpe = None
    if excess_volatility > 1e-12:
        sharpe = float(
            excess_returns.mean() / excess_volatility * np.sqrt(MONTHS_PER_YEAR)
        )

    return {
        "months": int(len(returns)),
        "total_return": float(equity.iloc[-1] - 1),
        "annualised_return": float(
            equity.iloc[-1] ** (MONTHS_PER_YEAR / len(returns)) - 1
        ),
        "annualised_volatility": float(returns.std(ddof=1) * np.sqrt(MONTHS_PER_YEAR)),
        "sharpe_vs_SHY": sharpe,
        "maximum_drawdown_month_end": float((equity / peak - 1).min()),
    }


def _monthly_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Validate aligned inputs and retain each month's final trading date."""
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("Prices require a DatetimeIndex")
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("Dates must be unique and sorted")
    if not set(ASSETS).issubset(prices.columns):
        raise ValueError("Prices must include HYG, LQD and SHY")

    aligned_prices = prices[ASSETS].copy()
    invalid_values = not np.isfinite(aligned_prices.to_numpy()).all()
    nonpositive_values = (aligned_prices <= 0).any().any()
    if aligned_prices.empty or invalid_values or nonpositive_values:
        raise ValueError(
            "Prices must be finite, positive and aligned without missing data"
        )

    monthly_prices = aligned_prices.groupby(prices.index.to_period("M")).tail(1)
    calendar_months = monthly_prices.index.to_period("M").astype("int64")
    if len(calendar_months) > 1 and not np.all(np.diff(calendar_months) == 1):
        raise ValueError("Monthly history must be contiguous")

    # This weekday calendar does not model exchange holidays. The published
    # input ends on 31 December 2025, which is a complete trading month.
    final_date = aligned_prices.index[-1]
    if final_date < final_date + pd.offsets.BMonthEnd(0):
        monthly_prices = monthly_prices.iloc[:-1]
    return monthly_prices


def _target_weights(
    monthly_prices: pd.DataFrame,
    asset_returns: pd.DataFrame,
    config: Config,
) -> tuple[pd.DataFrame, pd.Series]:
    """Build closing targets; the caller lags them before earning returns."""
    momentum = monthly_prices.pct_change(config.momentum_months, fill_method=None)
    volatility = asset_returns.rolling(config.volatility_months).std(ddof=1)
    excess_momentum = momentum[CREDIT_ASSETS].sub(momentum[DEFENSIVE_ASSET], axis=0)
    eligible = excess_momentum > 0

    # Ineligible or zero-volatility credit ETFs receive no allocation.
    credit_volatility = volatility[CREDIT_ASSETS].replace(0, np.nan)
    inverse_volatility = (1 / credit_volatility).where(eligible, 0).fillna(0)
    total_inverse_volatility = inverse_volatility.sum(axis=1).replace(0, np.nan)
    credit_weights = inverse_volatility.div(total_inverse_volatility, axis=0).fillna(0)

    # Caps leave a Treasury residual; capped weights are not renormalised.
    credit_weights = credit_weights.clip(upper=config.max_credit_weight)
    targets = credit_weights.assign(SHY=1 - credit_weights.sum(axis=1))
    history_ready = volatility.notna().all(axis=1) & momentum.notna().all(axis=1)
    return targets, history_ready


def _simulate_rebalances(
    weights: pd.DataFrame,
    asset_returns: pd.DataFrame,
    cost_bps: float,
) -> tuple[pd.Series, pd.Series]:
    """Apply costs before returns and carry drifted weights into each rebalance.

    Turnover counts dollars bought and sold. Starting from SHY, a full switch
    to credit trades two dollars per dollar of NAV. Costs reduce NAV uniformly,
    so they do not change the next period's relative asset weights.
    """
    drifted_weights = np.array([0.0, 0.0, 1.0])
    net_returns = []
    turnover = []
    cost_rate = cost_bps / BASIS_POINTS_PER_UNIT

    for target_weights, month_returns in zip(
        weights.to_numpy(), asset_returns.to_numpy(), strict=True
    ):
        traded_weight = float(np.abs(target_weights - drifted_weights).sum())
        gross_return = float(target_weights @ month_returns)
        trading_cost = traded_weight * cost_rate

        net_returns.append((1 - trading_cost) * (1 + gross_return) - 1)
        turnover.append(traded_weight)
        drifted_weights = target_weights * (1 + month_returns) / (1 + gross_return)

    return (
        pd.Series(net_returns, index=weights.index),
        pd.Series(turnover, index=weights.index),
    )


def _summarise_portfolios(
    frame: pd.DataFrame,
    config: Config,
) -> dict[str, Any]:
    """Report the continuous run and fixed descriptive subperiods."""
    summary = {
        "config": asdict(config),
        "start": str(frame.index[0].date()),
        "end": str(frame.index[-1].date()),
        "average_credit_weight": float(
            frame[["weight_HYG", "weight_LQD"]].sum(axis=1).mean()
        ),
        "annualised_turnover": float(frame["turnover"].mean() * MONTHS_PER_YEAR),
        "portfolios": {},
    }
    portfolio_returns = {
        "Credit momentum": frame["strategy_return"],
        "50/50 credit blend": frame["blend_return"],
        "HYG buy-and-hold": frame["HYG_return"],
    }
    defensive_returns = frame["SHY_return"]

    for name, returns in portfolio_returns.items():
        portfolio_metrics = {"full_sample": metrics(returns, defensive_returns)}
        for label, first_year, last_year in SUBPERIODS:
            period_returns = returns.loc[first_year:last_year]
            if len(period_returns) >= MIN_EVALUATION_MONTHS:
                portfolio_metrics[label] = metrics(
                    period_returns, defensive_returns.loc[period_returns.index]
                )
        summary["portfolios"][name] = portfolio_metrics
    return summary


def run_backtest(
    prices: pd.DataFrame,
    config: Config | None = None,
    start: str = "2008-05-01",
    end: str = "2025-12-31",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run the fixed monthly strategy and two cost-aware credit benchmarks.

    Price history before the evaluation window supplies the signal warm-up.
    A closing target earns only the following month's return. All portfolios
    begin in SHY and remain open at the end; no liquidation cost is imposed.
    """
    config = config or Config()
    monthly_prices = _monthly_prices(prices)
    monthly_returns = monthly_prices.pct_change(fill_method=None)
    targets, history_ready = _target_weights(monthly_prices, monthly_returns, config)

    evaluation_mask = (
        history_ready.shift(1, fill_value=False)
        & (monthly_prices.index >= pd.Timestamp(start))
        & (monthly_prices.index <= pd.Timestamp(end))
    )
    holdings = targets.shift(1).loc[evaluation_mask]
    asset_returns = monthly_returns.loc[evaluation_mask]
    if len(holdings) < MIN_EVALUATION_MONTHS:
        raise ValueError("Need at least 12 evaluation months after warm-up")

    strategy_returns, strategy_turnover = _simulate_rebalances(
        holdings, asset_returns, config.cost_bps
    )
    blend_weights = pd.DataFrame(
        np.tile([0.5, 0.5, 0.0], (len(holdings), 1)),
        index=holdings.index,
        columns=ASSETS,
    )
    blend_returns, blend_turnover = _simulate_rebalances(
        blend_weights, asset_returns, config.cost_bps
    )

    # Buy-and-hold pays only the initial SHY sale and HYG purchase.
    hyg_returns = asset_returns["HYG"].copy()
    entry_cost = 2 * config.cost_bps / BASIS_POINTS_PER_UNIT
    hyg_returns.iloc[0] = (1 - entry_cost) * (1 + hyg_returns.iloc[0]) - 1

    performance = pd.DataFrame(
        {
            "strategy_return": strategy_returns,
            "blend_return": blend_returns,
            "HYG_return": hyg_returns,
            "SHY_return": asset_returns[DEFENSIVE_ASSET],
            "turnover": strategy_turnover,
            "blend_turnover": blend_turnover,
        }
    )
    frame = holdings.add_prefix("weight_").join(performance)
    return frame, _summarise_portfolios(frame, config)


def main() -> None:
    """Read local prices and export an auditable backtest run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv", required=True, help="Adjusted daily prices: Date,HYG,LQD,SHY"
    )
    parser.add_argument("--output-dir", default="reports/default")
    parser.add_argument("--momentum-months", type=int, default=6)
    parser.add_argument("--cost-bps", type=float, default=10)
    args = parser.parse_args()

    prices = pd.read_csv(args.csv, index_col="Date", parse_dates=True)
    config = Config(momentum_months=args.momentum_months, cost_bps=args.cost_bps)
    frame, summary = run_backtest(prices, config)

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "monthly_allocations.csv", index_label="Date")
    summary_json = json.dumps(summary, indent=2, allow_nan=False)
    (output / "metrics.json").write_text(summary_json + "\n", encoding="utf-8")
    print(summary_json)


if __name__ == "__main__":
    main()
