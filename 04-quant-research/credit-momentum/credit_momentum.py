"""Monthly, long-only credit ETF momentum with auditable allocations.

The engine takes adjusted prices and returns monthly holdings, net portfolio
returns and summary statistics. Downloads and chart generation live separately.
"""

import argparse
import calendar
import json
from pathlib import Path

import numpy as np
import pandas as pd

CREDIT_ASSETS = ["HYG", "LQD"]
DEFENSIVE_ASSET = "SHY"
ASSETS = ["HYG", "LQD", "SHY"]
MONTHS_PER_YEAR = 12
BASIS_POINTS_PER_UNIT = 10_000
MIN_EVALUATION_MONTHS = 12
SUBPERIODS = [("2008-2015", "2008", "2015"), ("2016-2025", "2016", "2025")]


class Config:
    """Settings for the momentum rule and trading costs."""

    def __init__(
        self,
        momentum_months=6,
        volatility_months=12,
        cost_bps=10.0,
        max_credit_weight=0.60,
    ):
        if momentum_months < 1 or volatility_months < 2:
            raise ValueError(
                "Lookbacks must be positive; volatility needs at least 2 months"
            )
        if not np.isfinite(cost_bps) or not 0 <= cost_bps < 5000:
            raise ValueError("Cost must be finite and between 0 and 5,000 bps")
        if not 0 < max_credit_weight <= 1:
            raise ValueError("Credit cap must be in (0, 1]")

        self.momentum_months = momentum_months
        self.volatility_months = volatility_months
        self.cost_bps = cost_bps
        self.max_credit_weight = max_credit_weight


def metrics(returns, shy_returns):
    """Calculate monthly performance, using SHY as the excess-return reference.

    The initial capital of one is included in the drawdown peak. A portfolio
    identical to SHY has no excess-return volatility, so its Sharpe is undefined.
    """
    equity = (1 + returns).cumprod()
    peak = equity.cummax().clip(lower=1.0)
    excess_returns = returns - shy_returns
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


def get_monthly_prices(prices):
    """Validate aligned inputs and retain each month's final trading date."""
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("Prices require a DatetimeIndex")
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("Dates must be unique and sorted")
    for asset in ASSETS:
        if asset not in prices.columns:
            raise ValueError("Prices must include HYG, LQD and SHY")

    aligned_prices = prices[ASSETS].copy()
    invalid_values = not np.isfinite(aligned_prices.to_numpy()).all()
    nonpositive_values = (aligned_prices <= 0).any().any()
    if aligned_prices.empty or invalid_values or nonpositive_values:
        raise ValueError(
            "Prices must be finite, positive and aligned without missing data"
        )

    # Updating the same month replaces its earlier row with the latest row.
    last_row_in_month = {}
    for row, date in enumerate(aligned_prices.index):
        month = (date.year, date.month)
        last_row_in_month[month] = row
    monthly_prices = aligned_prices.iloc[list(last_row_in_month.values())]

    previous_month = None
    for date in monthly_prices.index:
        month_number = date.year * 12 + date.month
        if previous_month is not None and month_number != previous_month + 1:
            raise ValueError("Monthly history must be contiguous")
        previous_month = month_number

    # Find the final weekday of the input's last month. Exchange holidays
    # are not modelled; the published input ends on 31 December 2025.
    final_date = aligned_prices.index[-1]
    days_in_month = calendar.monthrange(final_date.year, final_date.month)[1]
    last_weekday = final_date.replace(day=days_in_month)
    while last_weekday.weekday() >= 5:
        last_weekday = last_weekday - pd.Timedelta(days=1)
    if final_date < last_weekday:
        monthly_prices = monthly_prices.iloc[:-1]
    return monthly_prices


def get_target_weights(monthly_prices, asset_returns, config):
    """Build closing targets; the caller lags them before earning returns."""
    momentum = monthly_prices.pct_change(config.momentum_months, fill_method=None)
    volatility = asset_returns.rolling(config.volatility_months).std(ddof=1)
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
                targets.loc[date, asset] = min(weight, config.max_credit_weight)

        # Any amount left after the credit allocations goes into SHY.
        credit_weight = targets.loc[date, "HYG"] + targets.loc[date, "LQD"]
        targets.loc[date, "SHY"] = 1 - credit_weight
    return targets, history_ready


def calculate_portfolio_returns(weights, asset_returns, cost_bps):
    """Apply costs before returns and carry drifted weights into each rebalance.

    Turnover counts dollars bought and sold. Starting from SHY, a full switch
    to credit trades two dollars per dollar of NAV. Costs reduce NAV uniformly,
    so they do not change the next period's relative asset weights.
    """
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


def get_summary(frame, config):
    """Report the continuous run and fixed descriptive subperiods."""
    summary = {
        "config": {
            "momentum_months": config.momentum_months,
            "volatility_months": config.volatility_months,
            "cost_bps": config.cost_bps,
            "max_credit_weight": config.max_credit_weight,
        },
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
    prices,
    config=None,
    start="2008-05-01",
    end="2025-12-31",
):
    """Run the fixed monthly strategy and two cost-aware credit benchmarks.

    Price history before the evaluation window supplies the signal warm-up.
    A closing target earns only the following month's return. All portfolios
    begin in SHY and remain open at the end; no liquidation cost is imposed.
    """
    if config is None:
        config = Config()
    monthly_prices = get_monthly_prices(prices)
    monthly_returns = monthly_prices.pct_change(fill_method=None)
    targets, history_ready = get_target_weights(monthly_prices, monthly_returns, config)

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
        holdings, asset_returns, config.cost_bps
    )
    blend_weights = pd.DataFrame(
        {"HYG": 0.5, "LQD": 0.5, "SHY": 0.0},
        index=holdings.index,
        columns=ASSETS,
    )
    blend_returns, blend_turnover = calculate_portfolio_returns(
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
    return frame, get_summary(frame, config)


def main():
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
