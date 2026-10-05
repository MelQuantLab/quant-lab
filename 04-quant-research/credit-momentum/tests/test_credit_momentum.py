import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
import pytest
from credit_momentum import Config, run_backtest, metrics


def prices():
    index = pd.date_range("2006-01-31", periods=100, freq="BME")
    x = np.arange(len(index))
    return pd.DataFrame({"HYG": 100*np.exp(.008*x+.012*np.sin(x)),
                         "LQD": 100*np.exp(.004*x+.009*np.cos(x)),
                         "SHY": 100*np.exp(.001*x)}, index=index)


def test_future_prices_do_not_change_previous_allocations_or_returns():
    source = prices()
    original, _ = run_backtest(source)
    source.iloc[-10:, 0] *= 1.5
    altered, _ = run_backtest(source)
    pd.testing.assert_frame_equal(original.iloc[:-10], altered.iloc[:-10])
    pd.testing.assert_series_equal(original.iloc[-10][["weight_HYG", "weight_LQD", "weight_SHY"]], altered.iloc[-10][["weight_HYG", "weight_LQD", "weight_SHY"]])


def test_weights_caps_and_costs():
    frame, _ = run_backtest(prices())
    assert np.allclose(frame.filter(like="weight_").sum(axis=1), 1)
    assert (frame[["weight_HYG", "weight_LQD"]] <= .6).all().all()
    free, _ = run_backtest(prices(), Config(cost_bps=0))
    assert (frame.strategy_return <= free.strategy_return).all()
    # Starting in SHY, purchasing credit sells SHY and buys credit.
    assert frame.turnover.iloc[0] == pytest.approx(2*(1-frame.weight_SHY.iloc[0]))


def test_negative_momentum_moves_to_cash():
    p = prices()
    x = np.arange(len(p))
    p["HYG"] = 100*np.exp(-.01*x)
    p["LQD"] = 100*np.exp(-.005*x)
    frame, _ = run_backtest(p)
    assert (frame.weight_SHY == 1).all()
    assert np.allclose(frame.strategy_return, frame.SHY_return)


def test_drawdown_includes_initial_capital():
    r = pd.Series([-.1, .05])
    assert metrics(r, r*0)["maximum_drawdown_month_end"] == pytest.approx(-.1)


def test_missing_and_duplicate_data_rejected():
    p = prices()
    p.iloc[4, 0] = np.nan
    with pytest.raises(ValueError):
        run_backtest(p)
    with pytest.raises(ValueError):
        run_backtest(pd.concat([prices(), prices()]))


def test_first_month_cost_and_rebalance_drift_match_hand_calculation():
    p = prices()
    frame, _ = run_backtest(p)
    ret = p.pct_change().loc[frame.index]
    weights = frame.filter(like="weight_").to_numpy()
    first_gross = weights[0] @ ret.iloc[0].to_numpy()
    first_cost = frame.turnover.iloc[0] * .001
    assert frame.strategy_return.iloc[0] == pytest.approx((1-first_cost)*(1+first_gross)-1)
    drift = weights[0]*(1+ret.iloc[0].to_numpy())/(1+first_gross)
    assert frame.turnover.iloc[1] == pytest.approx(abs(weights[1]-drift).sum())


def test_missing_month_rejected():
    with pytest.raises(ValueError, match="contiguous"):
        run_backtest(prices().drop(prices().index[20]))
