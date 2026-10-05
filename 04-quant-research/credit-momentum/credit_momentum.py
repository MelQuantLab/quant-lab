"""Monthly credit momentum strategy; checks and exports are in backtest_helpers."""

import numpy as np
import pandas as pd

from backtest_helpers import (
    ASSETS,
    BASIS_POINTS_PER_UNIT,
    CREDIT_ASSETS,
    DEFENSIVE_ASSET,
    MIN_EVALUATION_MONTHS,
    get_monthly_prices,
    get_settings,
    get_summary,
    run_cli,
)
from backtest_helpers import metrics as metrics


def get_target_weights(
    monthly_prices, asset_returns, momentum_months, volatility_months, max_credit_weight
):
    """Build closing targets; the caller lags them before earning returns."""
    momentum = monthly_prices.pct_change(momentum_months, fill_method=None)
    volatility = asset_returns.rolling(volatility_months).std(ddof=1)
    targets = pd.DataFrame(0.0, index=monthly_prices.index, columns=ASSETS)
    history_ready = pd.Series(False, index=monthly_prices.index)

    for date in monthly_prices.index:
        # Wait until both lookbacks are available for every ETF.
        ready = True
        for asset in ASSETS:
            if pd.isna(momentum.loc[date, asset]):
                ready = False
            if pd.isna(volatility.loc[date, asset]):
                ready = False
        history_ready.loc[date] = ready

        scores = {"HYG": 0.0, "LQD": 0.0}
        for asset in CREDIT_ASSETS:
            asset_momentum = momentum.loc[date, asset]
            shy_momentum = momentum.loc[date, "SHY"]
            asset_volatility = volatility.loc[date, asset]
            if asset_momentum > shy_momentum and asset_volatility > 0:
                scores[asset] = 1 / asset_volatility

        total_score = scores["HYG"] + scores["LQD"]
        if total_score > 0:
            for asset in CREDIT_ASSETS:
                weight = scores[asset] / total_score
                targets.loc[date, asset] = min(weight, max_credit_weight)

        # Any amount left after the credit allocations goes into SHY.
        credit_weight = targets.loc[date, "HYG"] + targets.loc[date, "LQD"]
        targets.loc[date, "SHY"] = 1 - credit_weight
    return targets, history_ready


def calculate_portfolio_returns(weights, asset_returns, cost_bps):
    """Charge two-sided turnover costs, then carry drifted weights forward."""
    drifted_weights = np.array([0.0, 0.0, 1.0])
    net_returns = []
    turnover = []
    cost_rate = cost_bps / BASIS_POINTS_PER_UNIT

    for month in range(len(weights)):
        target_weights = weights.iloc[month].to_numpy()
        month_returns = asset_returns.iloc[month].to_numpy()
        traded_weight = float(np.abs(target_weights - drifted_weights).sum())
        weighted_returns = target_weights * month_returns
        gross_return = float(weighted_returns.sum())
        trading_cost = traded_weight * cost_rate

        net_returns.append((1 - trading_cost) * (1 + gross_return) - 1)
        turnover.append(traded_weight)
        end_values = target_weights * (1 + month_returns)
        portfolio_value = 1 + gross_return
        drifted_weights = end_values / portfolio_value

    return (
        pd.Series(net_returns, index=weights.index),
        pd.Series(turnover, index=weights.index),
    )


def run_backtest(
    prices,
    momentum_months=6,
    volatility_months=12,
    cost_bps=10.0,
    max_credit_weight=0.60,
    start="2008-05-01",
    end="2025-12-31",
):
    """Use prior-month signals; compare net returns without final liquidation."""
    settings = get_settings(
        momentum_months, volatility_months, cost_bps, max_credit_weight
    )
    monthly_prices = get_monthly_prices(prices)
    monthly_returns = monthly_prices.pct_change(fill_method=None)
    targets, history_ready = get_target_weights(
        monthly_prices,
        monthly_returns,
        momentum_months,
        volatility_months,
        max_credit_weight,
    )

    evaluation_mask = (
        history_ready.shift(1, fill_value=False)
        & (monthly_prices.index >= pd.Timestamp(start))
        & (monthly_prices.index <= pd.Timestamp(end))
    )
    holdings = targets.shift(1).loc[evaluation_mask]
    asset_returns = monthly_returns.loc[evaluation_mask]
    if len(holdings) < MIN_EVALUATION_MONTHS:
        raise ValueError("Need at least 12 evaluation months after warm-up")

    strategy_returns, strategy_turnover = calculate_portfolio_returns(
        holdings, asset_returns, cost_bps
    )
    blend_weights = pd.DataFrame(
        {"HYG": 0.5, "LQD": 0.5, "SHY": 0.0},
        index=holdings.index,
        columns=ASSETS,
    )
    blend_returns, blend_turnover = calculate_portfolio_returns(
        blend_weights, asset_returns, cost_bps
    )

    # Buy-and-hold pays only the initial SHY sale and HYG purchase.
    hyg_returns = asset_returns["HYG"].copy()
    entry_cost = 2 * cost_bps / BASIS_POINTS_PER_UNIT
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
    return frame, get_summary(frame, settings)


def main():
    run_cli(run_backtest)


if __name__ == "__main__":
    main()
