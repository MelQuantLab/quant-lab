"""Tests for the credit relative-value screener."""

import csv
import math
import tempfile
import unittest
from datetime import date
from pathlib import Path

from relative_value_screener import (
    CreditInstrument,
    RiskSettings,
    build_switch_candidates,
    export_decision_pack,
    export_results,
    generate_synthetic_history,
    load_instruments,
    load_spread_history,
    rating_bucket,
    screen_relative_value,
)


def instrument(
    identifier: str,
    spread: float,
    leverage: float,
    *,
    sector: str = "Telecom",
    rating: str = "BB",
) -> CreditInstrument:
    return CreditInstrument(
        identifier=identifier,
        issuer=f"Issuer {identifier}",
        sector=sector,
        rating=rating,
        price=100,
        yield_percent=7,
        spread_bps=spread,
        maturity_years=5,
        duration=4,
        leverage=leverage,
    )


class RatingTests(unittest.TestCase):
    def test_rating_buckets(self) -> None:
        self.assertEqual(rating_bucket("BBB-"), "BBB")
        self.assertEqual(rating_bucket("bb+"), "BB")
        self.assertEqual(rating_bucket("B-"), "B")

    def test_unknown_rating_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            rating_bucket("NR")


class ScreeningTests(unittest.TestCase):
    def test_widest_comparable_spread_ranks_cheapest(self) -> None:
        universe = [
            instrument("A", 300, 4),
            instrument("B", 330, 4),
            instrument("C", 450, 4),
            instrument("D", 280, 4),
        ]
        results = screen_relative_value(universe)
        self.assertEqual(results[0].identifier, "C")
        self.assertEqual(results[0].signal, "CHEAP")
        self.assertGreater(results[0].spread_vs_peers_bps, 0)

    def test_tightest_comparable_spread_ranks_richest(self) -> None:
        universe = [
            instrument("A", 300, 4),
            instrument("B", 330, 4),
            instrument("C", 450, 4),
            instrument("D", 220, 4),
        ]
        results = screen_relative_value(universe)
        self.assertEqual(results[-1].identifier, "D")
        self.assertEqual(results[-1].signal, "RICH")

    def test_peer_fallback_uses_rating_bucket(self) -> None:
        universe = [
            instrument("A", 300, 4, sector="Telecom"),
            instrument("B", 330, 4, sector="Media"),
            instrument("C", 360, 4, sector="Automotive"),
        ]
        results = screen_relative_value(universe)
        self.assertTrue(all(item.peer_group == "All sectors/BB" for item in results))

    def test_invalid_values_are_rejected(self) -> None:
        universe = [instrument("A", 300, 4), instrument("B", 330, 4), instrument("C", 0, 4)]
        with self.assertRaises(ValueError):
            screen_relative_value(universe)

    def test_non_finite_values_are_rejected(self) -> None:
        universe = [
            instrument("A", 300, 4),
            instrument("B", 330, 4),
            instrument("C", math.nan, 4),
        ]
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            screen_relative_value(universe)

    def test_issuer_curve_dislocation_uses_fitted_issuer_curve(self) -> None:
        universe = [
            CreditInstrument("A-2", "Issuer A", "Telecom", "BB", 100, 7, 300, 2, 2, 4),
            CreditInstrument("A-5", "Issuer A", "Telecom", "BB", 100, 8, 450, 5, 5, 4),
            CreditInstrument("A-8", "Issuer A", "Telecom", "BB", 100, 8, 420, 8, 8, 4),
            instrument("B", 330, 4),
        ]
        results = screen_relative_value(universe)
        middle = next(item for item in results if item.identifier == "A-5")
        self.assertAlmostEqual(middle.issuer_curve_fair_spread_bps, 390)
        self.assertAlmostEqual(middle.issuer_curve_dislocation_bps, 60)

    def test_history_adds_rolling_stability_and_walk_forward_evidence(self) -> None:
        universe = [
            instrument("A", 390, 4),
            instrument("B", 330, 4),
            instrument("C", 350, 4),
        ]
        history = generate_synthetic_history(universe, periods=50, seed=4)
        results = screen_relative_value(
            universe,
            history=history,
            rolling_window=10,
            forward_horizon=2,
        )
        self.assertTrue(all(item.historical_observations == 50 for item in results))
        self.assertTrue(all(-1 <= item.relationship_stability <= 1 for item in results))
        self.assertTrue(all(0 <= item.out_of_sample_hit_rate <= 1 for item in results))

    def test_liquidity_filter_blocks_an_otherwise_cheap_candidate(self) -> None:
        illiquid = CreditInstrument(
            "C", "Issuer C", "Telecom", "BB", 100, 9, 500, 5, 4, 4,
            issue_size_mm=100, average_daily_volume_mm=0.2, bid_offer_bps=25,
        )
        universe = [instrument("A", 300, 4), instrument("B", 330, 4), illiquid]
        results = screen_relative_value(universe)
        candidate = next(item for item in results if item.identifier == "C")
        self.assertEqual(candidate.signal, "CHEAP")
        self.assertFalse(candidate.liquidity_pass)
        self.assertEqual(candidate.decision, "FILTERED")

    def test_position_size_is_capped_by_risk_and_liquidity(self) -> None:
        universe = [instrument("A", 300, 4), instrument("B", 330, 4), instrument("C", 450, 4)]
        results = screen_relative_value(
            universe,
            risk_settings=RiskSettings(portfolio_nav=5_000_000, risk_budget_percent=0.10),
        )
        self.assertTrue(all(item.recommended_notional > 0 for item in results))
        self.assertTrue(all(item.spread_dv01_per_1mm > 0 for item in results))

    def test_lowercase_rating_is_supported_for_direct_inputs(self) -> None:
        universe = [
            instrument("A", 300, 4, rating="bb"),
            instrument("B", 330, 4, rating="bb"),
            instrument("C", 450, 4, rating="bb"),
        ]
        self.assertEqual(len(screen_relative_value(universe)), 3)

    def test_duplicate_identifiers_are_rejected(self) -> None:
        universe = [
            instrument("A", 300, 4),
            instrument("A", 330, 4),
            instrument("C", 450, 4),
        ]
        with self.assertRaisesRegex(ValueError, "identifiers must be unique"):
            screen_relative_value(universe)


class FileTests(unittest.TestCase):
    def test_load_and_export_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "universe.csv"
            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "identifier",
                        "issuer",
                        "sector",
                        "rating",
                        "price",
                        "yield_percent",
                        "spread_bps",
                        "maturity_years",
                        "duration",
                        "leverage",
                    ]
                )
                writer.writerows(
                    [
                        ["A", "Issuer A", "Telecom", "BB", 100, 7, 300, 5, 4, 4],
                        ["B", "Issuer B", "Telecom", "BB", 100, 7, 330, 5, 4, 4],
                        ["C", "Issuer C", "Telecom", "BB", 100, 7, 360, 5, 4, 4],
                    ]
                )
            instruments = load_instruments(source)
            results = screen_relative_value(instruments)
            output = export_results(results, Path(temporary_directory) / "ranking.csv")
            self.assertEqual(len(instruments), 3)
            self.assertTrue(output.exists())
            self.assertIn("composite_score", output.read_text(encoding="utf-8"))

    def test_missing_columns_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "bad.csv"
            source.write_text("identifier,issuer\nA,Issuer A\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing columns"):
                load_instruments(source)

    def test_load_spread_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "history.csv"
            source.write_text(
                "date,identifier,spread_bps\n2026-01-05,A,300\n2026-01-12,A,310\n",
                encoding="utf-8",
            )
            observations = load_spread_history(source)
            self.assertEqual(len(observations), 2)
            self.assertEqual(observations[0].observation_date, date(2026, 1, 5))

    def test_decision_pack_and_switch_export(self) -> None:
        universe = [
            CreditInstrument("A-2", "Issuer A", "Telecom", "BB", 100, 7, 280, 2, 2, 4),
            CreditInstrument("A-5", "Issuer A", "Telecom", "BB", 100, 8, 450, 5, 5, 4),
            CreditInstrument("A-8", "Issuer A", "Telecom", "BB", 100, 8, 380, 8, 8, 4),
        ]
        results = screen_relative_value(universe)
        switches = build_switch_candidates(results, minimum_score_gap=0.25)
        self.assertGreaterEqual(len(switches), 1)
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = export_decision_pack(
                results,
                switches,
                Path(temporary_directory) / "decision_pack.md",
            )
            content = output.read_text(encoding="utf-8")
            self.assertIn("Executive summary", content)
            self.assertIn("Same-issuer switch ideas", content)


if __name__ == "__main__":
    unittest.main()
