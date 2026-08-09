"""Independent numerical tests for Black-Scholes options analytics."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from database import connect, save_calculation
from options_analytics import (
    OptionInputs,
    analyse_option,
    implied_volatility,
    no_arbitrage_bounds,
    option_price,
    put_call_parity_gap,
    price_pair,
    scenario_analysis,
    scenario_surface,
)


class BlackScholesPricingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.call = OptionInputs("call", 100, 100, 1, 0.05, 0.20)
        self.put = OptionInputs("put", 100, 100, 1, 0.05, 0.20)

    def test_reference_call_price(self) -> None:
        self.assertAlmostEqual(option_price(self.call), 10.45058357, places=7)

    def test_reference_put_price(self) -> None:
        self.assertAlmostEqual(option_price(self.put), 5.57352602, places=7)

    def test_put_call_parity(self) -> None:
        gap = put_call_parity_gap(
            option_price(self.call), option_price(self.put), 100, 100, 1, 0.05
        )
        self.assertAlmostEqual(gap, 0, places=10)

    def test_no_arbitrage_bounds(self) -> None:
        lower, upper = no_arbitrage_bounds(self.call)
        self.assertLessEqual(lower, option_price(self.call))
        self.assertLessEqual(option_price(self.call), upper)


class GreeksTests(unittest.TestCase):
    def test_reference_call_greeks(self) -> None:
        result = analyse_option(OptionInputs("call", 100, 100, 1, 0.05, 0.20))
        self.assertAlmostEqual(result.delta, 0.63683065, places=7)
        self.assertAlmostEqual(result.gamma, 0.01876202, places=7)
        self.assertAlmostEqual(result.vega, 0.37524035, places=7)
        self.assertAlmostEqual(result.rho, 0.53232482, places=7)
        self.assertLess(result.theta_per_day, 0)

    def test_call_delta_increases_with_spot(self) -> None:
        low = analyse_option(OptionInputs("call", 90, 100, 1, 0.05, 0.20))
        high = analyse_option(OptionInputs("call", 110, 100, 1, 0.05, 0.20))
        self.assertLess(low.delta, high.delta)


class ImpliedVolatilityTests(unittest.TestCase):
    def test_solver_recovers_known_volatility(self) -> None:
        inputs = OptionInputs("call", 100, 105, 0.5, 0.03, 0.25, 0.01)
        market_price = option_price(inputs)
        result = implied_volatility(market_price, inputs)
        self.assertTrue(result.converged)
        self.assertAlmostEqual(result.volatility, 0.25, places=7)

    def test_impossible_market_price_is_rejected(self) -> None:
        inputs = OptionInputs("call", 100, 100, 1, 0.05, 0.20)
        with self.assertRaises(ValueError):
            implied_volatility(150, inputs)


class ScenarioTests(unittest.TestCase):
    def test_scenario_grid_has_every_valid_combination(self) -> None:
        inputs = OptionInputs("call", 100, 100, 1, 0.05, 0.20)
        results = scenario_analysis(inputs, [-5, 0, 5], [-5, 0, 5])
        self.assertEqual(len(results), 9)

    def test_call_gains_value_after_positive_spot_shock(self) -> None:
        inputs = OptionInputs("call", 100, 100, 1, 0.05, 0.20)
        result = scenario_analysis(inputs, [5], [0])[0]
        self.assertGreater(result.value_change, 0)

    def test_pair_pnl_is_model_value_less_purchase_price(self) -> None:
        result = price_pair(
            spot=100,
            strike=100,
            time_to_expiry=1,
            risk_free_rate=0.05,
            volatility=0.20,
            call_purchase_price=8,
            put_purchase_price=7,
        )
        self.assertAlmostEqual(result.call_pnl, result.call_value - 8)
        self.assertAlmostEqual(result.put_pnl, result.put_value - 7)

    def test_pair_surface_contains_every_combination(self) -> None:
        surface = scenario_surface(
            spot_prices=[90, 100, 110],
            volatilities=[0.15, 0.20],
            strike=100,
            time_to_expiry=1,
            risk_free_rate=0.05,
            call_purchase_price=8,
            put_purchase_price=7,
        )
        self.assertEqual(len(surface), 6)
        self.assertTrue(all(point.call_pnl == point.call_value - 8 for point in surface))


class DatabaseTests(unittest.TestCase):
    def test_run_saves_one_input_with_linked_outputs(self) -> None:
        surface = scenario_surface(
            spot_prices=[95, 105],
            volatilities=[0.15, 0.25],
            strike=100,
            time_to_expiry=1,
            risk_free_rate=0.05,
            call_purchase_price=8,
            put_purchase_price=7,
        )
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.db"
            calculation_id = save_calculation(
                database_path,
                stock_price=100,
                strike_price=100,
                volatility=0.20,
                time_to_expiry=1,
                risk_free_rate=0.05,
                call_purchase_price=8,
                put_purchase_price=7,
                surface=surface,
            )
            with connect(database_path) as connection:
                inputs_count = connection.execute("SELECT COUNT(*) FROM inputs").fetchone()[0]
                output_rows = connection.execute(
                    "SELECT * FROM outputs WHERE CalculationId = ?", (calculation_id,)
                ).fetchall()

        self.assertEqual(inputs_count, 1)
        self.assertEqual(len(output_rows), 4)
        self.assertAlmostEqual(output_rows[0]["CallPnL"], output_rows[0]["CallModelValue"] - 8)


class ValidationTests(unittest.TestCase):
    def test_invalid_contract_inputs_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            option_price(OptionInputs("swap", 100, 100, 1, 0.05, 0.20))  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            option_price(OptionInputs("call", 0, 100, 1, 0.05, 0.20))
        with self.assertRaises(ValueError):
            price_pair(
                spot=100,
                strike=100,
                time_to_expiry=1,
                risk_free_rate=0.05,
                volatility=0.20,
                call_purchase_price=-1,
            )


if __name__ == "__main__":
    unittest.main()
