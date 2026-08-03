"""Tests for the credit relative-value screener."""

import csv
import tempfile
import unittest
from pathlib import Path

from relative_value_screener import (
    CreditInstrument,
    export_results,
    load_instruments,
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


if __name__ == "__main__":
    unittest.main()
