"""Numerical tests for fixed-rate bond analytics."""

import unittest

from bond_analytics import (
    BondInputs,
    accrued_interest,
    analyse_bond,
    cash_flows,
    clean_price,
    dirty_price,
    rate_scenarios,
    yield_to_maturity,
)


class PricingTests(unittest.TestCase):
    def test_par_bond_prices_at_par(self) -> None:
        bond = BondInputs(100, 0.05, 10, 2)
        self.assertAlmostEqual(clean_price(bond, 0.05), 100, places=10)

    def test_premium_bond_when_coupon_exceeds_yield(self) -> None:
        bond = BondInputs(100, 0.06, 5, 2)
        self.assertGreater(clean_price(bond, 0.04), 100)

    def test_discount_bond_when_coupon_is_below_yield(self) -> None:
        bond = BondInputs(100, 0.03, 5, 2)
        self.assertLess(clean_price(bond, 0.06), 100)

    def test_accrued_interest_reconciles_clean_and_dirty(self) -> None:
        bond = BondInputs(1_000, 0.06, 5, 2, settlement_fraction=0.4)
        self.assertAlmostEqual(accrued_interest(bond), 12)
        self.assertAlmostEqual(dirty_price(bond, 0.05) - clean_price(bond, 0.05), 12)

    def test_cash_flow_count_and_redemption(self) -> None:
        bond = BondInputs(100, 0.04, 2, 2)
        flows = cash_flows(bond)
        self.assertEqual(len(flows), 4)
        self.assertAlmostEqual(flows[-1][1], 102)


class YieldTests(unittest.TestCase):
    def test_solver_recovers_known_yield(self) -> None:
        bond = BondInputs(100, 0.045, 7, 2, settlement_fraction=0.3)
        market_price = clean_price(bond, 0.0575)
        result = yield_to_maturity(bond, market_price)
        self.assertTrue(result.converged)
        self.assertAlmostEqual(result.yield_to_maturity, 0.0575, places=9)


class RiskTests(unittest.TestCase):
    def test_zero_coupon_macaulay_duration_equals_maturity(self) -> None:
        bond = BondInputs(100, 0, 5, 2)
        analytics = analyse_bond(bond, 0.05)
        self.assertAlmostEqual(analytics.macaulay_duration, 5)

    def test_dv01_matches_small_exact_price_change(self) -> None:
        bond = BondInputs(100, 0.05, 10, 2)
        analytics = analyse_bond(bond, 0.05)
        exact_drop = dirty_price(bond, 0.05) - dirty_price(bond, 0.0501)
        self.assertAlmostEqual(analytics.dv01, exact_drop, places=4)

    def test_duration_convexity_approximates_rate_shock(self) -> None:
        bond = BondInputs(100, 0.05, 10, 2)
        scenario = rate_scenarios(bond, 0.05, [50])[0]
        self.assertLess(abs(scenario.approximation_error_bps), 1)


class ValidationTests(unittest.TestCase):
    def test_invalid_frequency_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            clean_price(BondInputs(100, 0.05, 5, 3), 0.05)

    def test_partial_coupon_period_maturity_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            clean_price(BondInputs(100, 0.05, 5.2, 2), 0.05)


if __name__ == "__main__":
    unittest.main()
