"""Transparent analytics for the Corporate Actions Borrow & RV Monitor.

The functions are intentionally simple and auditable. Scores are triage aids,
not forecasts, and sample borrow fields are illustrative rather than live data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

import numpy as np
import pandas as pd


EVENT_WEIGHTS = {
    "Earnings & Guidance": 12.0,
    "Equity Issuance": 16.0,
    "Takeover & Merger": 10.0,
    "Index Change": 13.0,
    "Dividend & Capital Return": 9.0,
    "Restructuring & Distress": 18.0,
    "Regulatory & Litigation": 11.0,
}


@dataclass(frozen=True)
class EventAssessment:
    borrow_pressure_score: float
    inventory_action: str
    net_expected_return_pct: float
    reward_to_stress: float
    decision: str
    decision_reason: str


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return float(max(lower, min(upper, value)))


def borrow_pressure_score(event: Mapping[str, float | str]) -> float:
    """Return a 0-100 transparent borrow-pressure triage score.

    Higher utilization, fee and lender concentration increase pressure, while
    greater availability reduces it. Event weights reflect research priors and
    must be validated before any real trading use.
    """

    event_weight = EVENT_WEIGHTS.get(str(event["event_type"]), 8.0)
    utilization = float(event["utilization_pct"])
    availability = float(event["availability_score"])
    concentration = float(event["lender_concentration_pct"])
    fee = float(event["borrow_fee_pct"])
    issuance = float(event.get("new_shares_pct", 0.0) or 0.0)

    demand_pressure = 0.34 * utilization + 0.18 * concentration
    scarcity = 0.24 * (100.0 - availability)
    fee_signal = min(fee, 20.0) * 1.2

    # Issuance can create hedging demand immediately, but the effect should not
    # dominate because settled shares may subsequently increase supply.
    issuance_pressure = min(issuance, 30.0) * 0.25
    return round(clamp(event_weight + demand_pressure + scarcity + fee_signal + issuance_pressure), 1)


def estimated_net_return_pct(event: Mapping[str, float | str], holding_days: int = 7) -> float:
    """Deduct simple borrow and execution assumptions from gross spread return."""

    gross = float(event["expected_gross_return_pct"])
    annual_fee = float(event["borrow_fee_pct"])
    borrow_cost = annual_fee * holding_days / 365.0
    liquidity = float(event["liquidity_score"])
    execution_cost = 0.12 + (100.0 - liquidity) * 0.006
    return round(gross - borrow_cost - execution_cost, 2)


def incremental_lending_revenue(
    market_value: float,
    current_fee_pct: float,
    improved_fee_pct: float,
    days_on_loan: int,
    revenue_share_pct: float = 100.0,
) -> dict[str, float]:
    """Estimate the gross and retained benefit of repricing lendable inventory.

    Fees are annualised and calculated on a simple ACT/365 basis. The result is
    an attribution aid, not an invoice or accounting valuation.
    """

    if market_value < 0 or days_on_loan < 0:
        raise ValueError("Market value and days on loan must be non-negative.")
    if not 0 <= revenue_share_pct <= 100:
        raise ValueError("Revenue share must be between 0 and 100 percent.")

    fee_improvement_pct = improved_fee_pct - current_fee_pct
    gross = market_value * (fee_improvement_pct / 100.0) * days_on_loan / 365.0
    retained = gross * revenue_share_pct / 100.0
    return {
        "fee_improvement_pct": round(fee_improvement_pct, 4),
        "gross_incremental_revenue": round(gross, 2),
        "retained_incremental_revenue": round(retained, 2),
    }


def assess_event(event: Mapping[str, float | str], holding_days: int = 7) -> EventAssessment:
    pressure = borrow_pressure_score(event)
    net_return = estimated_net_return_pct(event, holding_days)
    stress_loss = abs(float(event["stress_loss_pct"]))
    confidence = float(event["event_confidence"])
    availability = float(event["availability_score"])
    liquidity = float(event["liquidity_score"])

    if pressure >= 75:
        inventory_action = "Urgent inventory review"
    elif pressure >= 55:
        inventory_action = "Review inventory and pricing"
    else:
        inventory_action = "Monitor"

    reward_to_stress = round(net_return / stress_loss, 2) if stress_loss else np.inf

    if confidence < 85:
        decision, reason = "MANUAL REVIEW", "Event terms require human validation."
    elif availability < 20:
        decision, reason = "REJECT", "Illustrative locate availability is below the risk gate."
    elif liquidity < 55:
        decision, reason = "REJECT", "Liquidity is below the minimum research threshold."
    elif net_return <= 0.5:
        decision, reason = "REJECT", "Expected return does not clear estimated costs and hurdle."
    elif stress_loss > 10:
        decision, reason = "MANUAL REVIEW", "Event gap risk exceeds the automatic watchlist limit."
    elif reward_to_stress < 0.30:
        decision, reason = "MANUAL REVIEW", "Reward is insufficient relative to stressed loss."
    else:
        decision, reason = "WATCHLIST", "Research gates passed; trader validation is still required."

    return EventAssessment(
        borrow_pressure_score=pressure,
        inventory_action=inventory_action,
        net_expected_return_pct=net_return,
        reward_to_stress=reward_to_stress,
        decision=decision,
        decision_reason=reason,
    )


def enrich_events(events: pd.DataFrame, holding_days: int = 7) -> pd.DataFrame:
    """Append transparent assessment fields to an event DataFrame."""

    assessed = events.apply(lambda row: asdict(assess_event(row, holding_days)), axis=1)
    enriched = pd.concat([events.reset_index(drop=True), pd.DataFrame(list(assessed))], axis=1)
    enriched["risk_band"] = pd.cut(
        enriched["borrow_pressure_score"],
        bins=[-0.1, 49.9, 74.9, 100.0],
        labels=["LOW", "ELEVATED", "HIGH"],
    ).astype(str)
    enriched["horizon"] = np.where(enriched["days_to_catalyst"] <= 7, "7 day", "1 month")
    return enriched


def filter_horizon(events: pd.DataFrame, horizon: str) -> pd.DataFrame:
    """Filter events to a transparent catalyst horizon."""

    if horizon == "7 day":
        return events[events["days_to_catalyst"].between(0, 7)].copy()
    if horizon == "1 month":
        return events[events["days_to_catalyst"].between(0, 30)].copy()
    return events.copy()


def build_daily_brief(events: pd.DataFrame, as_of: str) -> str:
    """Build a deterministic, review-ready morning brief as plain text."""

    ordered = events.sort_values(
        ["borrow_pressure_score", "days_to_catalyst"], ascending=[False, True]
    )
    high = ordered[ordered["borrow_pressure_score"] >= 75]
    seven_day = ordered[ordered["days_to_catalyst"].between(0, 7)]
    month = ordered[ordered["days_to_catalyst"].between(8, 30)]

    def lines(frame: pd.DataFrame) -> list[str]:
        if frame.empty:
            return ["- None in the selected universe."]
        return [
            (
                f"- {row.ticker} | {row.event_type} | catalyst in "
                f"{int(row.days_to_catalyst)}d | pressure {row.borrow_pressure_score:.0f}/100 "
                f"| {row.decision}"
            )
            for row in frame.itertuples()
        ]

    sections = [
        f"CORPORATE ACTIONS, BORROW & RELATIVE-VALUE BRIEF | {as_of}",
        "",
        "REVIEW STATUS",
        "Draft generated for analyst/trader validation. Sources and terms must be checked before circulation.",
        "",
        "HIGH BORROW-PRESSURE WATCH",
        *lines(high),
        "",
        "NEXT 7 DAYS",
        *lines(seven_day),
        "",
        "8–30 DAY HORIZON",
        *lines(month),
        "",
        "CONTROL CHECKS",
        "- Confirm announcement terms, timestamp and security identifiers.",
        "- Recheck locate, fee, utilization, liquidity and recall assumptions.",
        "- Review dividend, corporate-action and execution-cost treatment.",
        "- Escalate ambiguous terms; this draft is not an execution instruction.",
    ]
    return "\n".join(sections)


def earnings_signal(event: Mapping[str, float | str]) -> dict[str, float | str]:
    """Describe an earnings event without treating surprise direction as a trade."""

    surprise = float(event.get("earnings_surprise_pct", 0.0) or 0.0)
    guidance = float(event.get("guidance_change_pct", 0.0) or 0.0)
    reaction = float(event.get("price_reaction_pct", 0.0) or 0.0)
    peer = float(event.get("peer_return_pct", 0.0) or 0.0)
    relative_move = reaction - peer

    if surprise < 0 and guidance < 0:
        interpretation = "Negative earnings and guidance revision"
    elif surprise > 0 and guidance > 0:
        interpretation = "Positive earnings and guidance revision"
    else:
        interpretation = "Mixed earnings signal"

    return {
        "interpretation": interpretation,
        "relative_move_pct": round(relative_move, 2),
        "reaction_multiple": round(abs(reaction) / max(abs(surprise), 0.1), 2),
    }


def scenario_grid(
    base_gross_return_pct: float,
    annual_borrow_fees: list[float],
    relative_moves: list[float],
    holding_days: int = 7,
    execution_cost_pct: float = 0.25,
) -> pd.DataFrame:
    """Return net P&L outcomes for borrow-fee and relative-move scenarios."""

    values = []
    for fee in annual_borrow_fees:
        row = []
        for move in relative_moves:
            borrow = fee * holding_days / 365.0
            row.append(round(base_gross_return_pct + move - borrow - execution_cost_pct, 2))
        values.append(row)
    return pd.DataFrame(values, index=annual_borrow_fees, columns=relative_moves)
