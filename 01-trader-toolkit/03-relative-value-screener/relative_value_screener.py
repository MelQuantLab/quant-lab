"""Explainable relative-value screening for corporate credit instruments."""

from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from dataclasses import dataclass, fields
from datetime import date, timedelta
from math import isfinite, sin, sqrt
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
    spread_type: str = "Z_SPREAD"
    issue_size_mm: float = 500.0
    average_daily_volume_mm: float = 2.0
    bid_offer_bps: float = 5.0
    carry_roll_3m_bps: float = 20.0
    downside_spread_widening_bps: float = 100.0
    catalyst_score: float = 0.0
    catalyst: str = "No identified catalyst"


@dataclass(frozen=True)
class SpreadObservation:
    """One historical spread observation used by the walk-forward diagnostics."""

    observation_date: date
    identifier: str
    spread_bps: float


@dataclass(frozen=True)
class RiskSettings:
    """Portfolio and implementation constraints used for position sizing."""

    portfolio_nav: float = 10_000_000.0
    risk_budget_percent: float = 0.25
    maximum_issue_percent: float = 1.0
    maximum_adv_multiple: float = 10.0
    minimum_issue_size_mm: float = 300.0
    minimum_adv_mm: float = 1.0
    maximum_bid_offer_bps: float = 10.0


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
    spread_type: str = "Z_SPREAD"
    issuer_curve_fair_spread_bps: float = 0.0
    issuer_curve_dislocation_bps: float = 0.0
    rolling_dislocation_zscore: float = 0.0
    relationship_stability: float = 0.0
    out_of_sample_hit_rate: float = 0.0
    historical_observations: int = 0
    issue_size_mm: float = 0.0
    average_daily_volume_mm: float = 0.0
    bid_offer_bps: float = 0.0
    carry_roll_3m_bps: float = 0.0
    net_carry_after_cost_bps: float = 0.0
    downside_price_change_percent: float = 0.0
    catalyst_score: float = 0.0
    catalyst: str = ""
    liquidity_pass: bool = False
    implementation_pass: bool = False
    spread_dv01_per_1mm: float = 0.0
    recommended_notional: float = 0.0
    signed_recommended_notional: float = 0.0
    decision: str = "WATCH"


@dataclass(frozen=True)
class SwitchCandidate:
    """Duration-aware long/short switch within one issuer curve."""

    issuer: str
    long_identifier: str
    short_identifier: str
    score_gap: float
    gross_spread_pickup_bps: float
    estimated_round_trip_cost_bps: float
    net_spread_pickup_bps: float
    short_notional_per_long: float
    implementation_pass: bool


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
        "issue size": instrument.issue_size_mm,
        "average daily volume": instrument.average_daily_volume_mm,
        "downside spread widening": instrument.downside_spread_widening_bps,
    }
    invalid = [
        name for name, value in positive_fields.items()
        if not isfinite(value) or value <= 0
    ]
    if invalid:
        raise ValueError(
            f"{instrument.identifier}: {', '.join(invalid)} must be greater than zero."
        )
    non_negative_fields = {
        "bid-offer": instrument.bid_offer_bps,
        "carry and roll": instrument.carry_roll_3m_bps,
    }
    if any(not isfinite(value) for value in non_negative_fields.values()):
        raise ValueError(f"{instrument.identifier}: numeric inputs must be finite.")
    if instrument.bid_offer_bps < 0:
        raise ValueError(f"{instrument.identifier}: bid-offer cannot be negative.")
    if not isfinite(instrument.catalyst_score) or not -1 <= instrument.catalyst_score <= 1:
        raise ValueError(f"{instrument.identifier}: catalyst score must be between -1 and 1.")
    spread_type = instrument.spread_type.strip().upper()
    if spread_type not in {"Z_SPREAD", "OAS"}:
        raise ValueError(f"{instrument.identifier}: spread type must be Z_SPREAD or OAS.")
    return instrument


def load_instruments(path: str | Path) -> list[CreditInstrument]:
    """Load and validate instruments from a CSV file."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Input file not found: {csv_path}")

    required = {
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
    }
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
                            spread_type=(row.get("spread_type") or "Z_SPREAD").strip().upper(),
                            issue_size_mm=float(row.get("issue_size_mm") or 500.0),
                            average_daily_volume_mm=float(
                                row.get("average_daily_volume_mm") or 2.0
                            ),
                            bid_offer_bps=float(row.get("bid_offer_bps") or 5.0),
                            carry_roll_3m_bps=float(row.get("carry_roll_3m_bps") or 20.0),
                            downside_spread_widening_bps=float(
                                row.get("downside_spread_widening_bps") or 100.0
                            ),
                            catalyst_score=float(row.get("catalyst_score") or 0.0),
                            catalyst=(row.get("catalyst") or "No identified catalyst").strip(),
                        )
                    )
                )
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid data on CSV row {row_number}: {error}") from error
    if len(instruments) < 3:
        raise ValueError("At least three instruments are required for comparison.")
    return instruments


def load_spread_history(path: str | Path) -> list[SpreadObservation]:
    """Load long-form historical spreads from CSV."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"History file not found: {csv_path}")
    observations: list[SpreadObservation] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "identifier", "spread_bps"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"History CSV is missing columns: {', '.join(sorted(missing))}")
        for row_number, row in enumerate(reader, start=2):
            try:
                spread = float(row["spread_bps"])
                if not isfinite(spread) or spread <= 0:
                    raise ValueError("spread must be finite and greater than zero")
                observations.append(
                    SpreadObservation(
                        observation_date=date.fromisoformat(row["date"].strip()),
                        identifier=row["identifier"].strip(),
                        spread_bps=spread,
                    )
                )
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid history data on CSV row {row_number}: {error}"
                ) from error
    if not observations:
        raise ValueError("Spread history cannot be empty.")
    return observations


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


def _validate_risk_settings(settings: RiskSettings) -> RiskSettings:
    values = {
        "portfolio NAV": settings.portfolio_nav,
        "risk budget": settings.risk_budget_percent,
        "maximum issue percentage": settings.maximum_issue_percent,
        "maximum ADV multiple": settings.maximum_adv_multiple,
        "minimum issue size": settings.minimum_issue_size_mm,
        "minimum ADV": settings.minimum_adv_mm,
        "maximum bid-offer": settings.maximum_bid_offer_bps,
    }
    if any(not isfinite(value) or value <= 0 for value in values.values()):
        raise ValueError("Risk settings must be finite and greater than zero.")
    if settings.risk_budget_percent > 10 or settings.maximum_issue_percent > 10:
        raise ValueError("Risk and issue-size percentages are implausibly high.")
    return settings


def _linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Return intercept and slope for a small ordinary-least-squares line."""
    if len(xs) != len(ys) or len(xs) < 2:
        raise ValueError("At least two paired observations are required.")
    average_x = mean(xs)
    average_y = mean(ys)
    denominator = sum((value - average_x) ** 2 for value in xs)
    if denominator <= 1e-12:
        return average_y, 0.0
    slope = sum(
        (x_value - average_x) * (y_value - average_y)
        for x_value, y_value in zip(xs, ys)
    ) / denominator
    return average_y - slope * average_x, slope


def _issuer_curve_value(
    instrument: CreditInstrument,
    universe: list[CreditInstrument],
) -> tuple[float, float]:
    """Fit an issuer spread curve and return the bond's curve residual."""
    curve_peers = [
        item for item in universe
        if item.issuer.casefold() == instrument.issuer.casefold()
        and item.spread_type.strip().upper() == instrument.spread_type.strip().upper()
    ]
    if len(curve_peers) < 3:
        return instrument.spread_bps, 0.0
    intercept, slope = _linear_fit(
        [item.duration for item in curve_peers],
        [item.spread_bps for item in curve_peers],
    )
    fair_spread = intercept + slope * instrument.duration
    return fair_spread, instrument.spread_bps - fair_spread


def _pearson(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 3:
        return 0.0
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right)
    )
    denominator = sqrt(
        sum((value - left_mean) ** 2 for value in left)
        * sum((value - right_mean) ** 2 for value in right)
    )
    return 0.0 if denominator <= 1e-12 else numerator / denominator


def generate_synthetic_history(
    instruments: list[CreditInstrument],
    *,
    periods: int = 80,
    seed: int = 17,
) -> list[SpreadObservation]:
    """Create deterministic demo history for the included synthetic universe.

    This supports a reproducible walk-forward demonstration. It is never presented
    as observed market data and should be replaced with vendor history in production.
    """
    if periods < 20:
        raise ValueError("At least 20 periods are required for the historical demo.")
    universe = [_validate(item) for item in instruments]
    rng = random.Random(seed)
    start = date(2026, 1, 5)
    issuer_states: dict[str, float] = defaultdict(float)
    idiosyncratic_states: dict[str, float] = defaultdict(float)
    generated: list[SpreadObservation] = []
    for period in range(periods):
        current_date = start + timedelta(days=7 * period)
        market_move = 20.0 * sin(period / 8)
        for issuer in sorted({item.issuer for item in universe}):
            issuer_states[issuer] = 0.82 * issuer_states[issuer] + rng.gauss(0, 2.0)
        for item in universe:
            idiosyncratic_states[item.identifier] = (
                0.60 * idiosyncratic_states[item.identifier] + rng.gauss(0, 2.5)
            )
            convergence_weight = (period + 1) / periods
            historical_level = item.spread_bps + (1 - convergence_weight) * rng.gauss(0, 4)
            spread = max(
                1.0,
                historical_level
                + market_move
                + issuer_states[item.issuer]
                + idiosyncratic_states[item.identifier],
            )
            if period == periods - 1:
                spread = item.spread_bps
            generated.append(SpreadObservation(current_date, item.identifier, spread))
    return generated


def _historical_diagnostics(
    instrument: CreditInstrument,
    universe: list[CreditInstrument],
    observations: list[SpreadObservation],
    *,
    minimum_peers: int,
    rolling_window: int,
    forward_horizon: int,
) -> tuple[float, float, float, int]:
    """Return rolling z-score, peer stability and walk-forward mean-reversion hit rate."""
    if rolling_window < 5 or forward_horizon < 1:
        raise ValueError("Rolling window must be at least five and horizon at least one.")
    _, peers = _peer_group(instrument, universe, minimum_peers)
    peer_ids = {item.identifier for item in peers if item.identifier != instrument.identifier}
    by_date: dict[date, dict[str, float]] = defaultdict(dict)
    for observation in observations:
        by_date[observation.observation_date][observation.identifier] = observation.spread_bps

    target_series: list[float] = []
    peer_series: list[float] = []
    dislocations: list[float] = []
    for observation_date in sorted(by_date):
        snapshot = by_date[observation_date]
        target = snapshot.get(instrument.identifier)
        peer_values = [snapshot[identifier] for identifier in peer_ids if identifier in snapshot]
        if target is None or len(peer_values) < max(1, minimum_peers - 1):
            continue
        peer_level = median(peer_values)
        target_series.append(target)
        peer_series.append(peer_level)
        dislocations.append(target - peer_level)

    observation_count = len(dislocations)
    if observation_count < 5:
        return 0.0, 0.0, 0.0, observation_count
    rolling_sample = dislocations[-rolling_window:]
    rolling_zscore = _zscore(dislocations[-1], rolling_sample)
    stability = _pearson(target_series, peer_series)

    successful = 0
    evaluated = 0
    for index in range(rolling_window, observation_count - forward_horizon):
        training_sample = dislocations[index - rolling_window:index]
        signal_zscore = _zscore(dislocations[index], training_sample)
        if abs(signal_zscore) < 1.0:
            continue
        future = dislocations[index + forward_horizon]
        successful += abs(future) < abs(dislocations[index])
        evaluated += 1
    hit_rate = successful / evaluated if evaluated else 0.0
    return rolling_zscore, stability, hit_rate, observation_count


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
            float(RATING_SCORES[item.rating.strip().upper()]),
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
    history: list[SpreadObservation] | None = None,
    risk_settings: RiskSettings | None = None,
    rolling_window: int = 20,
    forward_horizon: int = 5,
) -> list[RelativeValueResult]:
    """Rank instruments and apply implementation-aware escalation gates."""
    if len(instruments) < 3:
        raise ValueError("At least three instruments are required for comparison.")
    if minimum_peers < 2:
        raise ValueError("Minimum peer count must be at least two.")
    universe = [_validate(item) for item in instruments]
    identifiers = [item.identifier for item in universe]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Instrument identifiers must be unique.")
    settings = _validate_risk_settings(risk_settings or RiskSettings())
    residuals = _fair_spread_residuals(universe)
    spread_per_leverage = [item.spread_bps / item.leverage for item in universe]
    residual_zscores = [_zscore(value, residuals) for value in residuals]
    efficiency_zscores = [
        _zscore(value, spread_per_leverage) for value in spread_per_leverage
    ]
    curve_values = [_issuer_curve_value(item, universe) for item in universe]
    curve_dislocations = [value[1] for value in curve_values]
    curve_zscores = [_zscore(value, curve_dislocations) for value in curve_dislocations]

    unranked: list[dict[str, object]] = []
    for index, item in enumerate(universe):
        peer_label, peers = _peer_group(item, universe, minimum_peers)
        peer_spreads = [peer.spread_bps for peer in peers]
        peer_median = median(peer_spreads)
        peer_zscore = _zscore(item.spread_bps, peer_spreads)
        if history:
            rolling_zscore, stability, hit_rate, observation_count = (
                _historical_diagnostics(
                    item,
                    universe,
                    history,
                    minimum_peers=minimum_peers,
                    rolling_window=rolling_window,
                    forward_horizon=forward_horizon,
                )
            )
            composite = (
                0.30 * peer_zscore
                + 0.25 * residual_zscores[index]
                + 0.20 * curve_zscores[index]
                + 0.15 * rolling_zscore
                + 0.10 * efficiency_zscores[index]
            )
        else:
            rolling_zscore = 0.0
            stability = 0.0
            hit_rate = 0.0
            observation_count = 0
            composite = (
                0.50 * peer_zscore
                + 0.35 * residual_zscores[index]
                + 0.15 * efficiency_zscores[index]
            )

        liquidity_pass = (
            item.issue_size_mm >= settings.minimum_issue_size_mm
            and item.average_daily_volume_mm >= settings.minimum_adv_mm
            and item.bid_offer_bps <= settings.maximum_bid_offer_bps
        )
        spread_dv01 = item.duration * item.price * 1_000_000 / 100 * 0.0001
        downside_fraction = item.duration * item.downside_spread_widening_bps / 10_000
        downside_price_change_percent = -downside_fraction * 100
        risk_budget = settings.portfolio_nav * settings.risk_budget_percent / 100
        risk_limited_notional = risk_budget / max(downside_fraction, 1e-12)
        issue_cap = item.issue_size_mm * 1_000_000 * settings.maximum_issue_percent / 100
        liquidity_cap = (
            item.average_daily_volume_mm * 1_000_000 * settings.maximum_adv_multiple
        )
        recommended_notional = min(risk_limited_notional, issue_cap, liquidity_cap)
        net_carry = item.carry_roll_3m_bps - item.bid_offer_bps
        historical_pass = (
            not history
            or (
                observation_count >= rolling_window
                and stability >= 0.50
                and hit_rate >= 0.50
            )
        )
        signal = "CHEAP" if composite >= 0.75 else "RICH" if composite <= -0.75 else "FAIR"
        catalyst_pass = (
            signal == "FAIR"
            or (signal == "CHEAP" and item.catalyst_score >= 0)
            or (signal == "RICH" and item.catalyst_score <= 0)
        )
        carry_pass = signal != "CHEAP" or net_carry > 0
        implementation_pass = (
            signal != "FAIR"
            and liquidity_pass
            and historical_pass
            and catalyst_pass
            and carry_pass
        )
        decision = (
            "ESCALATE"
            if implementation_pass
            else "FILTERED"
            if signal != "FAIR" and not liquidity_pass
            else "WATCH"
        )
        signed_notional = (
            recommended_notional
            if signal == "CHEAP"
            else -recommended_notional
            if signal == "RICH"
            else 0.0
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
                "signal": signal,
                "spread_type": item.spread_type,
                "issuer_curve_fair_spread_bps": curve_values[index][0],
                "issuer_curve_dislocation_bps": curve_values[index][1],
                "rolling_dislocation_zscore": rolling_zscore,
                "relationship_stability": stability,
                "out_of_sample_hit_rate": hit_rate,
                "historical_observations": observation_count,
                "issue_size_mm": item.issue_size_mm,
                "average_daily_volume_mm": item.average_daily_volume_mm,
                "bid_offer_bps": item.bid_offer_bps,
                "carry_roll_3m_bps": item.carry_roll_3m_bps,
                "net_carry_after_cost_bps": net_carry,
                "downside_price_change_percent": downside_price_change_percent,
                "catalyst_score": item.catalyst_score,
                "catalyst": item.catalyst,
                "liquidity_pass": liquidity_pass,
                "implementation_pass": implementation_pass,
                "spread_dv01_per_1mm": spread_dv01,
                "recommended_notional": recommended_notional,
                "signed_recommended_notional": signed_notional,
                "decision": decision,
            }
        )

    unranked.sort(key=lambda row: float(row["composite_score"]), reverse=True)
    results: list[RelativeValueResult] = []
    for rank, row in enumerate(unranked, start=1):
        results.append(RelativeValueResult(rank=rank, **row))
    return results


def build_switch_candidates(
    results: list[RelativeValueResult],
    *,
    minimum_score_gap: float = 1.0,
) -> list[SwitchCandidate]:
    """Build same-issuer, duration-aware switch ideas from ranked results."""
    if minimum_score_gap <= 0:
        raise ValueError("Minimum score gap must be greater than zero.")
    by_issuer: dict[str, list[RelativeValueResult]] = defaultdict(list)
    for result in results:
        by_issuer[result.issuer].append(result)
    switches: list[SwitchCandidate] = []
    for issuer, issuer_results in by_issuer.items():
        if len(issuer_results) < 2:
            continue
        long_leg = max(issuer_results, key=lambda item: item.composite_score)
        short_leg = min(issuer_results, key=lambda item: item.composite_score)
        score_gap = long_leg.composite_score - short_leg.composite_score
        if score_gap < minimum_score_gap:
            continue
        gross_pickup = long_leg.spread_bps - short_leg.spread_bps
        costs = long_leg.bid_offer_bps + short_leg.bid_offer_bps
        switches.append(
            SwitchCandidate(
                issuer=issuer,
                long_identifier=long_leg.identifier,
                short_identifier=short_leg.identifier,
                score_gap=score_gap,
                gross_spread_pickup_bps=gross_pickup,
                estimated_round_trip_cost_bps=costs,
                net_spread_pickup_bps=gross_pickup - costs,
                short_notional_per_long=(
                    long_leg.spread_dv01_per_1mm / short_leg.spread_dv01_per_1mm
                    if short_leg.spread_dv01_per_1mm > 0
                    else 0.0
                ),
                implementation_pass=(
                    long_leg.liquidity_pass
                    and short_leg.liquidity_pass
                    and gross_pickup > costs
                ),
            )
        )
    return sorted(switches, key=lambda item: item.score_gap, reverse=True)


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


def export_decision_pack(
    results: list[RelativeValueResult],
    switches: list[SwitchCandidate],
    path: str | Path,
) -> Path:
    """Export a concise PM-style Markdown decision pack."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    escalated = [item for item in results if item.decision == "ESCALATE"]
    lines = [
        "# Corporate Credit Relative-Value Decision Pack",
        "",
        "## Executive summary",
        "",
        f"- Universe screened: **{len(results)} instruments**",
        f"- Candidates escalated: **{len(escalated)}**",
        f"- Same-issuer switches identified: **{len(switches)}**",
        "- Spread inputs are precomputed Z-spreads or OAS; the tool does not derive them from cash flows.",
        "",
        "## Escalated candidates",
        "",
        "| Instrument | Signal | Score | Peer gap | Curve gap | Rolling z | Stability | OOS hit | Net carry | Notional | Catalyst |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    if escalated:
        for item in escalated:
            lines.append(
                f"| {item.identifier} | {item.signal} | {item.composite_score:+.2f} | "
                f"{item.spread_vs_peers_bps:+.1f}bp | {item.issuer_curve_dislocation_bps:+.1f}bp | "
                f"{item.rolling_dislocation_zscore:+.2f} | {item.relationship_stability:.0%} | "
                f"{item.out_of_sample_hit_rate:.0%} | {item.net_carry_after_cost_bps:+.1f}bp | "
                f"{item.signed_recommended_notional:,.0f} | {item.catalyst} |"
            )
    else:
        lines.append("| No candidate cleared every implementation gate | | | | | | | | | | |")

    lines += [
        "",
        "## Same-issuer switch ideas",
        "",
        "| Issuer | Long | Short | Score gap | Net spread pickup | Short notional per 1 long | Implementable |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    if switches:
        for item in switches:
            lines.append(
                f"| {item.issuer} | {item.long_identifier} | {item.short_identifier} | "
                f"{item.score_gap:.2f} | {item.net_spread_pickup_bps:+.1f}bp | "
                f"{item.short_notional_per_long:.2f}x | {'YES' if item.implementation_pass else 'NO'} |"
            )
    else:
        lines.append("| No switch met the minimum score gap | | | | | | |")

    lines += [
        "",
        "## Escalation rules",
        "",
        "A candidate is escalated only when the cheap/rich score is material, liquidity passes, "
        "the historical relationship is stable, walk-forward mean reversion clears 50%, "
        "the catalyst aligns with the direction and long carry remains positive after bid-offer costs.",
        "",
        "## Downside and model risk",
        "",
        "Recommended notionals are capped by a portfolio risk budget, issue size and trading volume. "
        "Downside uses a duration approximation under the instrument-specific spread-widening shock. "
        "The model omits default timing, recovery uncertainty, jump risk and full scenario covariance.",
        "",
        "## Data warning",
        "",
        "The included demonstration universe and history are synthetic. Replace them with consistently "
        "sourced market spreads, liquidity measures and documented catalysts before investment use.",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def print_results(results: list[RelativeValueResult]) -> None:
    """Display a compact desk-style ranking."""
    print("\n--- Credit Relative Value Ranking ---")
    print("Rank | ID       | Sprd | Peer gap | Curve | Roll z | Score | Signal | Decision")
    print("-----+----------+------+----------+-------+--------+-------+--------+----------")
    for item in results:
        print(
            f"{item.rank:>4} | {item.identifier:<8} | {item.spread_bps:>4.0f} |"
            f" {item.spread_vs_peers_bps:>+7.1f} | {item.issuer_curve_dislocation_bps:>+5.1f} |"
            f" {item.rolling_dislocation_zscore:>+6.2f} | {item.composite_score:>+5.2f} |"
            f" {item.signal:<6} | {item.decision}"
        )
    print("\nPositive scores indicate wider/cheaper spreads; negative scores indicate richer spreads.")
    print("ESCALATE means the signal also cleared stability, catalyst, carry and liquidity gates.")


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
    history_group = parser.add_mutually_exclusive_group()
    history_group.add_argument(
        "--history",
        help="Optional long-form spread history CSV (date, identifier, spread_bps).",
    )
    history_group.add_argument(
        "--synthetic-history",
        action="store_true",
        help="Use deterministic synthetic history for a reproducible demonstration.",
    )
    parser.add_argument(
        "--decision-pack",
        default="relative_value_decision_pack.md",
        help="PM-style Markdown decision-pack output path.",
    )
    parser.add_argument("--portfolio-nav", type=float, default=10_000_000.0)
    parser.add_argument("--risk-budget-percent", type=float, default=0.25)
    args = parser.parse_args()
    try:
        instruments = load_instruments(args.input)
        history = (
            load_spread_history(args.history)
            if args.history
            else generate_synthetic_history(instruments)
            if args.synthetic_history
            else None
        )
        settings = RiskSettings(
            portfolio_nav=args.portfolio_nav,
            risk_budget_percent=args.risk_budget_percent,
        )
        results = screen_relative_value(
            instruments,
            minimum_peers=args.minimum_peers,
            history=history,
            risk_settings=settings,
        )
        switches = build_switch_candidates(results)
        print_results(results)
        output_path = export_results(results, args.output)
        decision_pack_path = export_decision_pack(results, switches, args.decision_pack)
        print(f"\nFull ranked report saved to: {output_path.resolve()}")
        print(f"Decision pack saved to: {decision_pack_path.resolve()}")
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
