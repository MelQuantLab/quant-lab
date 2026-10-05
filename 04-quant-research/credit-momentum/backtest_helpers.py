"""Input checks, performance statistics and file exports for the backtester."""

import argparse
import calendar
import json
from pathlib import Path

import numpy as np
import pandas as pd

ASSETS = ["HYG", "LQD", "SHY"]
CREDIT_ASSETS = ["HYG", "LQD"]
DEFENSIVE_ASSET = "SHY"
MONTHS_PER_YEAR = 12
BASIS_POINTS_PER_UNIT = 10_000
MIN_EVALUATION_MONTHS = 12
SUBPERIODS = [("2008-2015", "2008", "2015"), ("2016-2025", "2016", "2025")]


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


def get_summary(frame, settings):
    """Report the continuous run and fixed descriptive subperiods."""
    summary = {
        "config": settings,
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


def run_cli(run_backtest):
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
    frame, summary = run_backtest(
        prices, momentum_months=args.momentum_months, cost_bps=args.cost_bps
    )

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "monthly_allocations.csv", index_label="Date")
    summary_json = json.dumps(summary, indent=2, allow_nan=False)
    (output / "metrics.json").write_text(summary_json + "\n", encoding="utf-8")
    print(summary_json)


def get_settings(momentum_months, volatility_months, cost_bps, max_credit_weight):
    """Check the settings and record them for the results summary."""
    if momentum_months < 1 or volatility_months < 2:
        raise ValueError(
            "Lookbacks must be positive; volatility needs at least 2 months"
        )
    if not np.isfinite(cost_bps) or not 0 <= cost_bps < 5000:
        raise ValueError("Cost must be finite and between 0 and 5,000 bps")
    if not 0 < max_credit_weight <= 1:
        raise ValueError("Credit cap must be in (0, 1]")

    return {
        "momentum_months": momentum_months,
        "volatility_months": volatility_months,
        "cost_bps": cost_bps,
        "max_credit_weight": max_credit_weight,
    }
