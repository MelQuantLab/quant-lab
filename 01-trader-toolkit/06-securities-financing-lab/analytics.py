"""Auditable analytics for the Securities Financing Scenario Lab.

All rates are entered as percentages and converted to decimals here.  The lab
uses an ACT/360 day-count convention, common in money-market calculations.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TradeInputs:
    ticker: str = "NOVA"
    shares: int = 10_000
    start_price: float = 42.50
    price_move_pct: float = -4.0
    holding_days: int = 30
    borrow_fee_pct: float = 3.25
    rebate_rate_pct: float = 1.50
    utilization_pct: float = 78.0
    locate_available: int = 18_000
    recall_probability_pct: float = 8.0
    recall_cover_cost_pct: float = 1.25
    transaction_cost_bps: float = 5.0


def calculate_trade(inputs: TradeInputs) -> dict[str, float | str]:
    """Calculate short-borrow economics with explicit, independently auditable legs."""
    notional = inputs.shares * inputs.start_price
    end_price = inputs.start_price * (1 + inputs.price_move_pct / 100)
    day_fraction = inputs.holding_days / 360

    price_pnl = inputs.shares * (inputs.start_price - end_price)
    borrow_cost = notional * (inputs.borrow_fee_pct / 100) * day_fraction
    rebate_income = notional * (inputs.rebate_rate_pct / 100) * day_fraction
    transaction_cost = notional * (inputs.transaction_cost_bps / 10_000) * 2
    expected_recall_cost = (
        notional
        * (inputs.recall_probability_pct / 100)
        * (inputs.recall_cover_cost_pct / 100)
    )
    net_pnl = price_pnl + rebate_income - borrow_cost - transaction_cost - expected_recall_cost
    net_return_pct = net_pnl / notional * 100 if notional else 0.0
    break_even_move_pct = (
        (borrow_cost + transaction_cost + expected_recall_cost - rebate_income) / notional * 100
        if notional
        else 0.0
    )
    coverage = inputs.locate_available / inputs.shares if inputs.shares else np.inf

    return {
        "ticker": inputs.ticker,
        "notional": notional,
        "end_price": end_price,
        "price_pnl": price_pnl,
        "borrow_cost": borrow_cost,
        "rebate_income": rebate_income,
        "transaction_cost": transaction_cost,
        "expected_recall_cost": expected_recall_cost,
        "net_pnl": net_pnl,
        "net_return_pct": net_return_pct,
        "break_even_move_pct": break_even_move_pct,
        "locate_coverage": coverage,
        "availability": availability_label(coverage, inputs.utilization_pct),
        "risk": risk_label(inputs.utilization_pct, inputs.recall_probability_pct, coverage),
    }


def availability_label(coverage: float, utilization_pct: float) -> str:
    if coverage < 1:
        return "Insufficient"
    if coverage < 1.25 or utilization_pct >= 90:
        return "Tight"
    if utilization_pct >= 75:
        return "Limited"
    return "Available"


def risk_label(utilization_pct: float, recall_pct: float, coverage: float) -> str:
    score = int(utilization_pct >= 75) + int(utilization_pct >= 90)
    score += int(recall_pct >= 10) + int(coverage < 1.25)
    return "High" if score >= 3 else "Medium" if score >= 1 else "Low"


def economics_table(inputs: TradeInputs) -> pd.DataFrame:
    r = calculate_trade(inputs)
    rows = [
        ("Short-sale price P&L", r["price_pnl"], "Shares × (start price − end price)"),
        ("Collateral rebate", r["rebate_income"], "Notional × rebate rate × days / 360"),
        ("Stock-borrow fee", -r["borrow_cost"], "Notional × borrow fee × days / 360"),
        ("Round-trip execution", -r["transaction_cost"], "Notional × cost in bps × 2"),
        ("Expected recall cost", -r["expected_recall_cost"], "Notional × recall probability × cover cost"),
        ("Net expected P&L", r["net_pnl"], "Sum of all economics above"),
    ]
    return pd.DataFrame(rows, columns=["Economics leg", "P&L", "Calculation"])


def scenario_grid(
    inputs: TradeInputs,
    price_moves: list[float] | np.ndarray,
    borrow_fees: list[float] | np.ndarray,
) -> pd.DataFrame:
    values = []
    base = asdict(inputs)
    for fee in borrow_fees:
        row = []
        for move in price_moves:
            scenario = TradeInputs(**{**base, "borrow_fee_pct": float(fee), "price_move_pct": float(move)})
            row.append(float(calculate_trade(scenario)["net_pnl"]))
        values.append(row)
    return pd.DataFrame(values, index=np.asarray(borrow_fees), columns=np.asarray(price_moves))


def pnl_path(inputs: TradeInputs) -> pd.DataFrame:
    """Illustrative linear path to make each P&L component visible through time."""
    days = np.arange(inputs.holding_days + 1)
    fraction = days / max(inputs.holding_days, 1)
    prices = inputs.start_price * (1 + inputs.price_move_pct / 100 * fraction)
    notional = inputs.shares * inputs.start_price
    price_pnl = inputs.shares * (inputs.start_price - prices)
    borrow = notional * inputs.borrow_fee_pct / 100 * days / 360
    rebate = notional * inputs.rebate_rate_pct / 100 * days / 360
    execution = np.full_like(days, notional * inputs.transaction_cost_bps / 10_000, dtype=float)
    recall = notional * inputs.recall_probability_pct / 100 * inputs.recall_cover_cost_pct / 100 * fraction
    net = price_pnl + rebate - borrow - execution - recall
    return pd.DataFrame({"Day": days, "Price P&L": price_pnl, "Net expected P&L": net})
