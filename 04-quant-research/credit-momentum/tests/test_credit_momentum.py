"""Protect financial timing, portfolio constraints and accounting identities."""

import numpy as np
import pandas as pd
import pytest

from credit_momentum import Config, metrics, run_backtest

WEIGHT_COLUMNS = ["weight_HYG", "weight_LQD", "weight_SHY"]


@pytest.fixture
def sample_prices() -> pd.DataFrame:
    """Create positive, nonconstant ETF histories without network access."""
    dates = pd.date_range("2006-01-31", periods=100, freq="BME")
    month_number = np.arange(len(dates))
    return pd.DataFrame(
        {
            "HYG": 100 * np.exp(0.008 * month_number + 0.012 * np.sin(month_number)),
            "LQD": 100 * np.exp(0.004 * month_number + 0.009 * np.cos(month_number)),
            "SHY": 100 * np.exp(0.001 * month_number),
        },
        index=dates,
    )


def test_future_prices_do_not_change_previous_allocations_or_returns(sample_prices):
    original, _ = run_backtest(sample_prices)
    altered_prices = sample_prices.copy()
    altered_prices.iloc[-10:, 0] *= 1.5
    altered, _ = run_backtest(altered_prices)

    pd.testing.assert_frame_equal(original.iloc[:-10], altered.iloc[:-10])
    # A new price can change this month's return, but not its lagged holding.
    pd.testing.assert_series_equal(
        original.iloc[-10][WEIGHT_COLUMNS], altered.iloc[-10][WEIGHT_COLUMNS]
    )


def test_weights_caps_and_costs(sample_prices):
    frame, _ = run_backtest(sample_prices)
    no_cost_frame, _ = run_backtest(sample_prices, Config(cost_bps=0))

    assert np.allclose(frame[WEIGHT_COLUMNS].sum(axis=1), 1)
    assert (frame[["weight_HYG", "weight_LQD"]] <= 0.6).all().all()
    assert (frame["strategy_return"] <= no_cost_frame["strategy_return"]).all()

    # Starting in SHY, purchasing credit sells SHY and buys credit.
    initial_credit_weight = 1 - frame["weight_SHY"].iloc[0]
    assert frame["turnover"].iloc[0] == pytest.approx(2 * initial_credit_weight)


def test_negative_momentum_moves_to_treasuries(sample_prices):
    month_number = np.arange(len(sample_prices))
    declining_prices = sample_prices.copy()
    declining_prices["HYG"] = 100 * np.exp(-0.01 * month_number)
    declining_prices["LQD"] = 100 * np.exp(-0.005 * month_number)
    frame, _ = run_backtest(declining_prices)

    assert (frame["weight_SHY"] == 1).all()
    assert np.allclose(frame["strategy_return"], frame["SHY_return"])


def test_drawdown_includes_initial_capital():
    returns = pd.Series([-0.1, 0.05])
    zero_cash_returns = returns * 0
    result = metrics(returns, zero_cash_returns)
    assert result["maximum_drawdown_month_end"] == pytest.approx(-0.1)


def test_missing_and_duplicate_data_rejected(sample_prices):
    incomplete_prices = sample_prices.copy()
    incomplete_prices.iloc[4, 0] = np.nan
    with pytest.raises(ValueError):
        run_backtest(incomplete_prices)
    with pytest.raises(ValueError):
        run_backtest(pd.concat([sample_prices, sample_prices]))


def test_first_month_cost_and_rebalance_drift_match_hand_calculation(sample_prices):
    frame, _ = run_backtest(sample_prices)
    asset_returns = sample_prices.pct_change().loc[frame.index]
    weights = frame[WEIGHT_COLUMNS].to_numpy()

    first_month_returns = asset_returns.iloc[0].to_numpy()
    first_gross_return = weights[0] @ first_month_returns
    first_trading_cost = frame["turnover"].iloc[0] * 0.001
    expected_net_return = (1 - first_trading_cost) * (1 + first_gross_return) - 1
    assert frame["strategy_return"].iloc[0] == pytest.approx(expected_net_return)

    drifted_weights = weights[0] * (1 + first_month_returns) / (1 + first_gross_return)
    expected_turnover = abs(weights[1] - drifted_weights).sum()
    assert frame["turnover"].iloc[1] == pytest.approx(expected_turnover)


def test_missing_month_rejected(sample_prices):
    missing_month_prices = sample_prices.drop(sample_prices.index[20])
    with pytest.raises(ValueError, match="contiguous"):
        run_backtest(missing_month_prices)
