"""Input checks, performance statistics and file exports for the backtester."""

import argparse
import calendar
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

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


def get_monthly_prices(prices, assets):
    """Validate aligned inputs and retain each month's final trading date."""
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("Prices require a DatetimeIndex")
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("Dates must be unique and sorted")
    missing = [asset for asset in assets if asset not in prices.columns]
    if missing:
        raise ValueError(f"Prices are missing columns: {missing}")

    aligned_prices = prices[assets].copy()
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


def get_summary(frame, config):
    """Report the continuous run and fixed descriptive subperiods."""
    credit_weight_columns = [f"weight_{asset}" for asset in config.credit_assets]
    benchmark = config.benchmark_asset
    summary = {
        "config": asdict(config),
        "start": str(frame.index[0].date()),
        "end": str(frame.index[-1].date()),
        "average_credit_weight": float(frame[credit_weight_columns].sum(axis=1).mean()),
        "annualised_turnover": float(frame["turnover"].mean() * MONTHS_PER_YEAR),
        "portfolios": {},
    }
    portfolio_returns = {
        "Credit momentum": frame["strategy_return"],
        "Equal-weight credit blend": frame["blend_return"],
        f"{benchmark} buy-and-hold": frame[f"{benchmark}_return"],
    }
    defensive_returns = frame[f"{config.defensive_asset}_return"]

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


def run_cli(run_backtest, config_class):
    """Read local prices and export an auditable backtest run."""
    defaults = config_class()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, help="Adjusted daily prices")
    parser.add_argument("--output-dir", default="reports/default")
    parser.add_argument("--credit-assets", nargs="+", default=defaults.credit_assets)
    parser.add_argument("--defensive-asset", default=defaults.defensive_asset)
    parser.add_argument("--benchmark-asset", default=defaults.benchmark_asset)
    parser.add_argument("--momentum-months", type=int, default=defaults.momentum_months)
    parser.add_argument(
        "--volatility-months", type=int, default=defaults.volatility_months
    )
    parser.add_argument("--cost-bps", type=float, default=defaults.cost_bps)
    parser.add_argument(
        "--max-credit-weight", type=float, default=defaults.max_credit_weight
    )
    args = parser.parse_args()

    config = config_class(
        credit_assets=tuple(args.credit_assets),
        defensive_asset=args.defensive_asset,
        benchmark_asset=args.benchmark_asset,
        momentum_months=args.momentum_months,
        volatility_months=args.volatility_months,
        cost_bps=args.cost_bps,
        max_credit_weight=args.max_credit_weight,
    )
    prices = pd.read_csv(args.csv, index_col="Date", parse_dates=True)
    frame, summary = run_backtest(prices, config)

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "monthly_allocations.csv", index_label="Date")
    summary_json = json.dumps(summary, indent=2, allow_nan=False)
    (output / "metrics.json").write_text(summary_json + "\n", encoding="utf-8")
    print(summary_json)
