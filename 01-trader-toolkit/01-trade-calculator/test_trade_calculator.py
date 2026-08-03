"""Tests for the Trade & Risk Analytics Calculator."""

import unittest

from trade_calculator import (
    analyse_strategy,
    assess_portfolio_risk,
    calculate_break_even_win_rate,
    calculate_position_size,
    calculate_risk_reward,
    calculate_trade,
)


class CompletedTradeTests(unittest.TestCase):
    def test_long_trade_attributes_fees_slippage_and_commission(self) -> None:
        result = calculate_trade(
            "long", 100, 110, 10, cost_bps=5, slippage_bps=3, commission=2
        )
        self.assertAlmostEqual(result.gross_pnl, 100)
        self.assertAlmostEqual(result.trading_costs, 3.68)
        self.assertAlmostEqual(result.net_pnl, 96.32)
        self.assertAlmostEqual(result.net_return_percent, 9.632)
        self.assertAlmostEqual(result.price_move_bps, 1_000)
        self.assertAlmostEqual(result.cost_drag_bps, 36.8)

    def test_profitable_short_trade(self) -> None:
        result = calculate_trade("short", 100, 90, 20)
        self.assertAlmostEqual(result.net_pnl, 200)
        self.assertAlmostEqual(result.return_percent, 10)
        self.assertAlmostEqual(result.price_move_bps, 1_000)

    def test_losing_short_trade(self) -> None:
        result = calculate_trade("short", 100, 105, 10)
        self.assertAlmostEqual(result.net_pnl, -50)
        self.assertAlmostEqual(result.price_move_bps, -500)

    def test_invalid_trade_inputs_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            calculate_trade("buy", 100, 110, 10)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            calculate_trade("long", 0, 110, 10)
        with self.assertRaises(ValueError):
            calculate_trade("long", 100, 110, 1, slippage_bps=-1)


class PositionSizingTests(unittest.TestCase):
    def test_long_position_is_limited_by_risk_budget(self) -> None:
        plan = calculate_position_size("long", 50_000, 1, 100, 95, 115)
        self.assertEqual(plan.quantity, 100)
        self.assertAlmostEqual(plan.maximum_loss, 500)
        self.assertAlmostEqual(plan.potential_profit, 1_500)
        self.assertAlmostEqual(plan.risk_reward_ratio, 3)
        self.assertAlmostEqual(plan.break_even_win_rate, 25)

    def test_position_is_capped_by_maximum_notional(self) -> None:
        plan = calculate_position_size(
            "long", 50_000, 5, 100, 99, 110, maximum_notional_percent=20
        )
        self.assertEqual(plan.quantity, 100)
        self.assertAlmostEqual(plan.position_notional, 10_000)

    def test_short_trade_requires_correct_price_order(self) -> None:
        with self.assertRaises(ValueError):
            calculate_position_size("short", 50_000, 1, 100, 95, 115)


class StrategyAnalyticsTests(unittest.TestCase):
    def test_positive_edge_strategy(self) -> None:
        metrics = analyse_strategy(45, 200, 100)
        self.assertAlmostEqual(metrics.expected_value_per_trade, 35)
        self.assertAlmostEqual(metrics.expected_value_in_r, 0.35)
        self.assertAlmostEqual(metrics.profit_factor, 1.6363636)
        self.assertAlmostEqual(metrics.kelly_percent, 17.5)
        self.assertAlmostEqual(metrics.half_kelly_percent, 8.75)

    def test_negative_kelly_is_floored_at_zero(self) -> None:
        metrics = analyse_strategy(30, 100, 100)
        self.assertEqual(metrics.kelly_percent, 0)

    def test_break_even_and_risk_reward_helpers(self) -> None:
        self.assertAlmostEqual(calculate_break_even_win_rate(150, 100), 40)
        self.assertAlmostEqual(calculate_risk_reward(100, 95, 115), 3)


class PortfolioRiskTests(unittest.TestCase):
    def test_proposed_trade_within_limit(self) -> None:
        risk = assess_portfolio_risk(50_000, 20_000, 500, 10_000, 400, 2)
        self.assertTrue(risk.within_risk_limit)
        self.assertAlmostEqual(risk.total_risk, 900)
        self.assertAlmostEqual(risk.remaining_risk_capacity, 100)

    def test_proposed_trade_breaches_limit(self) -> None:
        risk = assess_portfolio_risk(50_000, 20_000, 700, 10_000, 400, 2)
        self.assertFalse(risk.within_risk_limit)
        self.assertEqual(risk.remaining_risk_capacity, 0)


if __name__ == "__main__":
    unittest.main()
