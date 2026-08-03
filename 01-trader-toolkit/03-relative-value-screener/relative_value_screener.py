"""Explainable relative-value screening for corporate credit instruments."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, fields
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Iterable


RATING_SCORES = {
    "AAA": 1,
    "AA+": 2,
    "AA": 3,
    "AA-": 4,
    "A+": 5,
    "A": 6,
    "A-": 7,
    "BBB+": 8,
    "BBB": 9,
    "BBB-": 10,
    "BB+": 11,
    "BB": 12,
    "BB-": 13,
    "B+": 14,
    "B": 15,
    "B-": 16,
    "CCC+": 17,
    "CCC": 18,
    "CCC-": 19,
    "CC": 20,
    "C": 21,
}


@dataclass(frozen=True)
class CreditInstrument:
    """Observable features for one bond or loan."""

    identifier: str
    issuer: str
    sector: str
    rating: str
    price: float
    yield_percent: float
    spread_bps: float
    maturity_years: float
    duration: float
    leverage: float


@dataclass(frozen=True)
class RelativeValueResult:
    """Peer-relative diagnostics and ranking for one instrument."""

    rank: int
    identifier: str
    issuer: str
    sector: str
    rating: str
    peer_group: str
    peer_count: int
    price: float
    yield_percent: float
    spread_bps: float
    peer_median_spread_bps: float
    spread_vs_peers_bps: float
    peer_spread_zscore: float
    spread_per_turn_leverage: float
    residual_spread_bps: float
    composite_score: float
    signal: str


def rating_bucket(rating: str) -> str:
    """Map a letter rating to a broad investment-grade/high-yield cohort."""
    clean_rating = rating.strip().upper()
    if clean_rating not in RATING_SCORES:
        raise ValueError(f"Unsupported rating: {rating}")
    score = RATING_SCORES[clean_rating]
    if score <= 4:
        return "AA"
    if score <= 7:
        return "A"
    if score <= 10:
        return "BBB"
    if score <= 13:
        return "BB"
    if score <= 16:
        return "B"
    return "CCC"


def _validate(instrument: CreditInstrument) -> CreditInstrument:
    if not instrument.identifier.strip() or not instrument.issuer.strip():
        raise ValueError("Identifier and issuer cannot be blank.")
    if not instrument.sector.strip():
        raise ValueError(f"Sector is missing for {instrument.identifier}.")
    rating_bucket(instrument.rating)
    positive_fields = {
        "price": instrument.price,
        "yield": instrument.yield_percent,
        "spread": instrument.spread_bps,
        "maturity": instrument.maturity_years,
        "duration": instrument.duration,
        "leverage": instrument.leverage,
    }
    invalid = [name for name, value in positive_fields.items() if value <= 0]
    if invalid:
        raise ValueError(
            f"{instrument.identifier}: {', '.join(invalid)} must be greater than zero."
        )
    return instrument


def load_instruments(path: str | Path) -> list[CreditInstrument]:
    """Load and validate instruments from a CSV file."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Input file not found: {csv_path}")

    required = {field.name for field in fields(CreditInstrument)}
    instruments: list[CreditInstrument] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing columns: {', '.join(sorted(missing))}")
        for row_number, row in enumerate(reader, start=2):
            try:
                instruments.append(
                    _validate(
                        CreditInstrument(
                            identifier=row["identifier"].strip(),
                            issuer=row["issuer"].strip(),
                            sector=row["sector"].strip(),
                            rating=row["rating"].strip().upper(),
                            price=float(row["price"]),
                            yield_percent=float(row["yield_percent"]),
                            spread_bps=float(row["spread_bps"]),
                            maturity_years=float(row["maturity_years"]),
                            duration=float(row["duration"]),
                            leverage=float(row["leverage"]),
                        )
                    )
                )
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid data on CSV row {row_number}: {error}") from error
    if len(instruments) < 3:
        raise ValueError("At least three instruments are required for comparison.")
    return instruments


def _zscore(value: float, population: Iterable[float]) -> float:
    values = list(population)
    standard_deviation = pstdev(values)
    return 0.0 if standard_deviation == 0 else (value - mean(values)) / standard_deviation


def _peer_group(
    instrument: CreditInstrument,
    universe: list[CreditInstrument],
    minimum_peers: int,
) -> tuple[str, list[CreditInstrument]]:
    """Select the narrowest sufficiently populated, explainable peer group."""
    sector = instrument.sector.casefold()
    bucket = rating_bucket(instrument.rating)
    same_sector_rating = [
        item
        for item in universe
        if item.sector.casefold() == sector and rating_bucket(item.rating) == bucket
    ]
    if len(same_sector_rating) >= minimum_peers:
        return f"{instrument.sector}/{bucket}", same_sector_rating

    same_rating = [item for item in universe if rating_bucket(item.rating) == bucket]
    if len(same_rating) >= minimum_peers:
        return f"All sectors/{bucket}", same_rating

    same_sector = [item for item in universe if item.sector.casefold() == sector]
    if len(same_sector) >= minimum_peers:
        return f"{instrument.sector}/All ratings", same_sector

    return "Full universe", universe


def _standardise_feature(values: list[float]) -> list[float]:
    standard_deviation = pstdev(values)
    if standard_deviation == 0:
        return [0.0 for _ in values]
    average = mean(values)
    return [(value - average) / standard_deviation for value in values]


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Solve a small linear system with Gaussian elimination and pivoting."""
    size = len(vector)
    augmented = [row[:] + [value] for row, value in zip(matrix, vector)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("Regression inputs are collinear.")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        pivot_value = augmented[column][column]
        augmented[column] = [value / pivot_value for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                current - factor * pivot_current
                for current, pivot_current in zip(augmented[row], augmented[column])
            ]
    return [augmented[row][-1] for row in range(size)]


def _fair_spread_residuals(universe: list[CreditInstrument]) -> list[float]:
    """Estimate spread residuals from rating, leverage, duration and maturity.

    Features are standardised and a tiny ridge penalty stabilises correlated inputs.
    A positive residual means the observed spread is wider than model fair value.
    """
    raw_features = [
        [
            float(RATING_SCORES[item.rating]),
            item.leverage,
            item.duration,
            item.maturity_years,
        ]
        for item in universe
    ]
    columns = list(zip(*raw_features))
    standardised_columns = [_standardise_feature(list(column)) for column in columns]
    design = [
        [1.0] + [standardised_columns[column][row] for column in range(4)]
        for row in range(len(universe))
    ]
    targets = [item.spread_bps for item in universe]
    parameter_count = len(design[0])
    xtx = [
        [sum(row[i] * row[j] for row in design) for j in range(parameter_count)]
        for i in range(parameter_count)
    ]
    xty = [sum(row[i] * target for row, target in zip(design, targets)) for i in range(parameter_count)]
    for index in range(1, parameter_count):
        xtx[index][index] += 1e-6
    coefficients = _solve_linear_system(xtx, xty)
    fitted = [sum(value * coefficient for value, coefficient in zip(row, coefficients)) for row in design]
    return [actual - estimate for actual, estimate in zip(targets, fitted)]


def screen_relative_value(
    instruments: list[CreditInstrument],
    *,
    minimum_peers: int = 3,
) -> list[RelativeValueResult]:
    """Rank instruments from cheapest to richest on an explainable composite."""
    if len(instruments) < 3:
        raise ValueError("At least three instruments are required for comparison.")
    if minimum_peers < 2:
        raise ValueError("Minimum peer count must be at least two.")
    universe = [_validate(item) for item in instruments]
    residuals = _fair_spread_residuals(universe)
    spread_per_leverage = [item.spread_bps / item.leverage for item in universe]
    residual_zscores = [_zscore(value, residuals) for value in residuals]
    efficiency_zscores = [
        _zscore(value, spread_per_leverage) for value in spread_per_leverage
    ]

    unranked: list[dict[str, object]] = []
    for index, item in enumerate(universe):
        peer_label, peers = _peer_group(item, universe, minimum_peers)
        peer_spreads = [peer.spread_bps for peer in peers]
        peer_median = median(peer_spreads)
        peer_zscore = _zscore(item.spread_bps, peer_spreads)
        composite = (
            0.50 * peer_zscore
            + 0.35 * residual_zscores[index]
            + 0.15 * efficiency_zscores[index]
        )
        unranked.append(
            {
                "identifier": item.identifier,
                "issuer": item.issuer,
                "sector": item.sector,
                "rating": item.rating,
                "peer_group": peer_label,
                "peer_count": len(peers),
                "price": item.price,
                "yield_percent": item.yield_percent,
                "spread_bps": item.spread_bps,
                "peer_median_spread_bps": peer_median,
                "spread_vs_peers_bps": item.spread_bps - peer_median,
                "peer_spread_zscore": peer_zscore,
                "spread_per_turn_leverage": spread_per_leverage[index],
                "residual_spread_bps": residuals[index],
                "composite_score": composite,
            }
        )

    unranked.sort(key=lambda row: float(row["composite_score"]), reverse=True)
    results: list[RelativeValueResult] = []
    for rank, row in enumerate(unranked, start=1):
        score = float(row["composite_score"])
        signal = "CHEAP" if score >= 0.75 else "RICH" if score <= -0.75 else "FAIR"
        results.append(RelativeValueResult(rank=rank, signal=signal, **row))
    return results


def export_results(results: list[RelativeValueResult], path: str | Path) -> Path:
    """Export ranked results to CSV."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [field.name for field in fields(RelativeValueResult)]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow({name: getattr(result, name) for name in fieldnames})
    return output_path


def print_results(results: list[RelativeValueResult]) -> None:
    """Display a compact desk-style ranking."""
    print("\n--- Credit Relative Value Ranking ---")
    print("Rank | ID       | Rtng | Spread | vs peers | Residual | Score | Signal")
    print("-----+----------+------+--------+----------+----------+-------+-------")
    for item in results:
        print(
            f"{item.rank:>4} | {item.identifier:<8} | {item.rating:<4} |"
            f" {item.spread_bps:>5.0f}bp | {item.spread_vs_peers_bps:>+7.1f}bp |"
            f" {item.residual_spread_bps:>+7.1f}bp | {item.composite_score:>+5.2f} |"
            f" {item.signal}"
        )
    print("\nPositive scores indicate wider/cheaper spreads; negative scores indicate richer spreads.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Screen corporate credit relative value.")
    parser.add_argument(
        "input",
        nargs="?",
        default=str(Path(__file__).with_name("sample_credit_universe.csv")),
        help="Input CSV path (defaults to the included sample universe).",
    )
    parser.add_argument(
        "--output",
        default="relative_value_ranking.csv",
        help="Output CSV path.",
    )
    parser.add_argument(
        "--minimum-peers",
        type=int,
        default=3,
        help="Minimum instruments in a peer group.",
    )
    args = parser.parse_args()
    try:
        instruments = load_instruments(args.input)
        results = screen_relative_value(instruments, minimum_peers=args.minimum_peers)
        print_results(results)
        output_path = export_results(results, args.output)
        print(f"\nFull ranked report saved to: {output_path.resolve()}")
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
