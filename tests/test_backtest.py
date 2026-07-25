import numpy as np
import pandas as pd
import pytest

from melquantlab.backtest import BacktestConfig, run_backtest


def price_series(values: list[float]) -> pd.Series:
    return pd.Series(
        values,
        index=pd.bdate_range("2026-01-01", periods=len(values)),
        name="price",
    )


def test_config_rejects_invalid_windows() -> None:
    with pytest.raises(ValueError, match="greater than"):
        BacktestConfig(short_window=20, long_window=20)


def test_backtest_requires_enough_history() -> None:
    prices = price_series([100.0, 101.0, 102.0])

    with pytest.raises(ValueError, match="not enough observations"):
        run_backtest(prices, BacktestConfig(short_window=2, long_window=3))


def test_signal_is_lagged_before_return_is_earned() -> None:
    prices = price_series([10, 10, 10, 10, 11, 12, 13, 14])
    result = run_backtest(
        prices,
        BacktestConfig(short_window=2, long_window=3, transaction_cost_bps=0),
    )
    frame = result.frame

    first_signal_date = frame.index[frame["signal"].eq(1)][0]
    signal_position = frame.index.get_loc(first_signal_date)

    assert frame.loc[first_signal_date, "position"] == 0
    assert frame.iloc[signal_position + 1]["position"] == 1
    assert (
        frame.loc[first_signal_date, "strategy_return"] == 0
    ), "same-day signal must not earn the same-day return"


def test_transaction_cost_is_charged_on_position_change() -> None:
    prices = price_series([10, 10, 10, 10, 11, 12, 13, 14])
    result = run_backtest(
        prices,
        BacktestConfig(short_window=2, long_window=3, transaction_cost_bps=10),
    )
    frame = result.frame
    entry_rows = frame.loc[frame["turnover"].eq(1)]

    assert len(entry_rows) == 1
    assert entry_rows.iloc[0]["transaction_cost"] == pytest.approx(0.001)
    assert result.metrics["total_transaction_cost"] == pytest.approx(0.001)


def test_strategy_equity_matches_compounded_net_returns() -> None:
    values = list(np.linspace(100, 130, 80)) + list(np.linspace(130, 90, 40))
    result = run_backtest(
        price_series(values),
        BacktestConfig(short_window=5, long_window=20, transaction_cost_bps=5),
    )

    expected = (1 + result.frame["strategy_return"]).cumprod()
    pd.testing.assert_series_equal(
        result.frame["strategy_equity"],
        expected,
        check_names=False,
    )
    assert result.metrics["maximum_drawdown"] <= 0
    assert result.metrics["benchmark_maximum_drawdown"] <= 0
    assert 0 <= result.metrics["exposure"] <= 1
    assert 0 <= result.metrics["win_rate"] <= 1
    assert result.metrics["closed_trades"] == result.metrics["exits"]


def test_prices_must_be_positive() -> None:
    prices = price_series([100, 101, 0, 103, 104, 105])

    with pytest.raises(ValueError, match="strictly positive"):
        run_backtest(prices, BacktestConfig(short_window=2, long_window=3))
