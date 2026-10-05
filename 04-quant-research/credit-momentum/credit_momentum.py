"""Monthly credit momentum strategy; checks and exports are in backtest_helpers."""

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from backtest_helpers import (
    BASIS_POINTS_PER_UNIT,
    MIN_EVALUATION_MONTHS,
    get_monthly_prices,
    get_summary,
    run_cli,
)
from backtest_helpers import metrics as metrics


@dataclass(frozen=True)
class StrategyConfig:
    """Every choice the strategy makes, kept in one place."""

    credit_assets: tuple = ("HYG", "LQD")
    defensive_asset: str = "SHY"
    benchmark_asset: str = "HYG"
    momentum_months: int = 6
    volatility_months: int = 12
    cost_bps: float = 10.0
    max_credit_weight: float = 0.60
    start: str = "2008-05-01"
    end: str = "2025-12-31"

    def __post_init__(self):
        if len(self.credit_assets) == 0:
            raise ValueError("Need at least one credit asset")
        if self.defensive_asset in self.credit_assets:
            raise ValueError("Defensive asset cannot also be a credit asset")
        if self.benchmark_asset not in self.credit_assets:
            raise ValueError("Benchmark must be one of the credit assets")
        if self.momentum_months < 1 or self.volatility_months < 2:
            raise ValueError(
                "Lookbacks must be positive; volatility needs at least 2 months"
            )
        if not np.isfinite(self.cost_bps) or not 0 <= self.cost_bps < 5000:
            raise ValueError("Cost must be finite and between 0 and 5,000 bps")
        if not 0 < self.max_credit_weight <= 1:
            raise ValueError("Credit cap must be in (0, 1]")

    @property
    def assets(self):
        return list(self.credit_assets) + [self.defensive_asset]


def get_target_weights(monthly_prices, monthly_returns, config):
    """Build closing targets for all months at once; the caller lags them."""
    credit = list(config.credit_assets)
    defensive = config.defensive_asset

    momentum = monthly_prices.pct_change(config.momentum_months, fill_method=None)
    volatility = monthly_returns.rolling(config.volatility_months).std(ddof=1)

    # A month is usable only when every asset has both lookbacks filled in.
    history_ready = momentum.notna().all(axis=1) & volatility.notna().all(axis=1)

    # Credit qualifies when it beats the defensive asset and has positive vol.
    beats_defensive = momentum[credit].gt(momentum[defensive], axis=0)
    has_volatility = volatility[credit] > 0
    scores = (1 / volatility[credit]).where(beats_defensive & has_volatility, 0.0)

    # Turn scores into weights, cap each one, and park the rest in defensive.
    total_score = scores.sum(axis=1)
    credit_weights = scores.div(total_score.where(total_score > 0), axis=0)
    credit_weights = credit_weights.fillna(0.0).clip(upper=config.max_credit_weight)

    targets = credit_weights.copy()
    targets[defensive] = 1 - credit_weights.sum(axis=1)
    return targets[config.assets], history_ready


def calculate_portfolio_returns(weights, asset_returns, cost_bps, start_asset):
    """Charge two-sided turnover costs, then carry drifted weights forward."""
    # Start fully invested in the starting asset (e.g. 100% SHY).
    drifted_weights = (weights.columns == start_asset).astype(float)
    net_returns = []
    turnover = []
    cost_rate = cost_bps / BASIS_POINTS_PER_UNIT

    for month in range(len(weights)):
        target_weights = weights.iloc[month].to_numpy()
        month_returns = asset_returns.iloc[month].to_numpy()
        traded_weight = float(np.abs(target_weights - drifted_weights).sum())
        gross_return = float((target_weights * month_returns).sum())
        trading_cost = traded_weight * cost_rate

        net_returns.append((1 - trading_cost) * (1 + gross_return) - 1)
        turnover.append(traded_weight)
        drifted_weights = target_weights * (1 + month_returns) / (1 + gross_return)

    return (
        pd.Series(net_returns, index=weights.index),
        pd.Series(turnover, index=weights.index),
    )


def run_backtest(prices, config=None, **changes):
    """Use prior-month signals; compare net returns without final liquidation.

    Pass a StrategyConfig, or change single settings by name,
    e.g. run_backtest(prices, cost_bps=25).
    """
    config = replace(config or StrategyConfig(), **changes)
    credit = list(config.credit_assets)
    defensive = config.defensive_asset
    benchmark = config.benchmark_asset

    monthly_prices = get_monthly_prices(prices, config.assets)
    monthly_returns = monthly_prices.pct_change(fill_method=None)
    targets, history_ready = get_target_weights(monthly_prices, monthly_returns, config)

    evaluation_mask = (
        history_ready.shift(1, fill_value=False)
        & (monthly_prices.index >= pd.Timestamp(config.start))
        & (monthly_prices.index <= pd.Timestamp(config.end))
    )
    holdings = targets.shift(1).loc[evaluation_mask]
    asset_returns = monthly_returns.loc[evaluation_mask]
    if len(holdings) < MIN_EVALUATION_MONTHS:
        raise ValueError("Need at least 12 evaluation months after warm-up")

    strategy_returns, strategy_turnover = calculate_portfolio_returns(
        holdings, asset_returns, config.cost_bps, defensive
    )

    # Equal-weight blend of all credit assets, rebalanced monthly.
    blend_weights = pd.DataFrame(0.0, index=holdings.index, columns=config.assets)
    blend_weights[credit] = 1 / len(credit)
    blend_returns, blend_turnover = calculate_portfolio_returns(
        blend_weights, asset_returns, config.cost_bps, defensive
    )

    # Buy-and-hold pays only the initial defensive sale and benchmark purchase.
    benchmark_returns = asset_returns[benchmark].copy()
    entry_cost = 2 * config.cost_bps / BASIS_POINTS_PER_UNIT
    benchmark_returns.iloc[0] = (1 - entry_cost) * (1 + benchmark_returns.iloc[0]) - 1

    performance = pd.DataFrame(
        {
            "strategy_return": strategy_returns,
            "blend_return": blend_returns,
            f"{benchmark}_return": benchmark_returns,
            f"{defensive}_return": asset_returns[defensive],
            "turnover": strategy_turnover,
            "blend_turnover": blend_turnover,
        }
    )
    frame = holdings.add_prefix("weight_").join(performance)
    return frame, get_summary(frame, config)


def main():
    run_cli(run_backtest, StrategyConfig)


if __name__ == "__main__":
    main()
