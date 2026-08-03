"""Tests for the market maker simulator."""

import unittest

from market_maker_simulator import (
    MarketMakerGame,
    Quote,
    SimulationConfig,
    inventory_adjusted_quote,
    validate_quote,
)


class QuoteTests(unittest.TestCase):
    def test_quote_properties(self) -> None:
        quote = Quote(99.8, 100.2)
        self.assertAlmostEqual(quote.midpoint, 100)
        self.assertAlmostEqual(quote.spread, 0.4)

    def test_crossed_quote_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_quote(Quote(100.2, 100.1), 100, 0, 50)

    def test_long_inventory_skews_quote_lower(self) -> None:
        flat = inventory_adjusted_quote(100, 0)
        long = inventory_adjusted_quote(100, 40)
        self.assertLess(long.midpoint, flat.midpoint)

    def test_short_inventory_skews_quote_higher(self) -> None:
        flat = inventory_adjusted_quote(100, 0)
        short = inventory_adjusted_quote(100, -40)
        self.assertGreater(short.midpoint, flat.midpoint)


class SimulationTests(unittest.TestCase):
    def test_seed_makes_game_reproducible(self) -> None:
        config = SimulationConfig(rounds=5)
        first = MarketMakerGame(config, seed=7)
        second = MarketMakerGame(config, seed=7)
        for _ in range(5):
            first_result = first.play_round(inventory_adjusted_quote(first.fair_value, first.inventory))
            second_result = second.play_round(inventory_adjusted_quote(second.fair_value, second.inventory))
            self.assertEqual(first_result, second_result)

    def test_client_buy_reduces_inventory(self) -> None:
        config = SimulationConfig(
            rounds=1,
            informed_probability=1,
            base_trade_probability=1,
            volatility_bps=1,
        )
        found_buy = False
        for seed in range(100):
            game = MarketMakerGame(config, seed=seed)
            result = game.play_round(Quote(99.8, 100.2))
            if result.trade_side == "client_buy":
                self.assertEqual(result.inventory, -config.trade_size)
                self.assertGreater(result.cash, 0)
                found_buy = True
                break
        self.assertTrue(found_buy)

    def test_summary_counts_rounds_and_trades(self) -> None:
        config = SimulationConfig(rounds=3, base_trade_probability=1)
        game = MarketMakerGame(config, seed=4)
        for _ in range(3):
            game.play_round(inventory_adjusted_quote(game.fair_value, game.inventory))
        summary = game.summary()
        self.assertEqual(summary.rounds, 3)
        self.assertEqual(summary.trades, 3)
        self.assertEqual(summary.client_buys + summary.client_sells, 3)

    def test_marked_pnl_reconciles_cash_and_inventory(self) -> None:
        game = MarketMakerGame(SimulationConfig(rounds=1), seed=2)
        result = game.play_round(Quote(99.8, 100.2))
        self.assertAlmostEqual(result.marked_pnl, result.cash + result.inventory * result.fair_value_after)

    def test_invalid_probability_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            MarketMakerGame(SimulationConfig(informed_probability=1.5))


if __name__ == "__main__":
    unittest.main()
