import pytest

from analytics import TradeInputs, calculate_trade, scenario_grid


def test_zero_move_still_pays_carry_and_costs():
    result = calculate_trade(TradeInputs(price_move_pct=0))
    expected = result["rebate_income"] - result["borrow_cost"] - result["transaction_cost"] - result["expected_recall_cost"]
    assert result["net_pnl"] == pytest.approx(expected)


def test_falling_price_helps_short():
    down = calculate_trade(TradeInputs(price_move_pct=-10))["net_pnl"]
    up = calculate_trade(TradeInputs(price_move_pct=10))["net_pnl"]
    assert down > up


def test_borrow_fee_increase_reduces_pnl():
    grid = scenario_grid(TradeInputs(), [-5], [1, 10])
    assert grid.loc[1, -5] > grid.loc[10, -5]


def test_locate_shortfall_is_flagged():
    result = calculate_trade(TradeInputs(shares=10_000, locate_available=9_000))
    assert result["availability"] == "Insufficient"


def test_act_360_borrow_cost():
    result = calculate_trade(TradeInputs(shares=1_000, start_price=100, holding_days=36, borrow_fee_pct=5))
    assert result["borrow_cost"] == pytest.approx(500.0)
