import pandas as pd

from analytics import (
    assess_event,
    borrow_pressure_score,
    build_daily_brief,
    earnings_signal,
    enrich_events,
    filter_horizon,
    scenario_grid,
)


def base_event(**overrides):
    event = {
        "event_type": "Earnings & Guidance",
        "utilization_pct": 75.0,
        "availability_score": 50.0,
        "lender_concentration_pct": 40.0,
        "borrow_fee_pct": 5.0,
        "new_shares_pct": 0.0,
        "expected_gross_return_pct": 2.5,
        "stress_loss_pct": -4.0,
        "event_confidence": 95.0,
        "liquidity_score": 80.0,
        "days_to_catalyst": 7,
        "earnings_surprise_pct": -5.0,
        "guidance_change_pct": -8.0,
        "price_reaction_pct": -10.0,
        "peer_return_pct": -2.0,
    }
    event.update(overrides)
    return event


def test_pressure_rises_when_availability_falls():
    abundant = borrow_pressure_score(base_event(availability_score=90.0))
    scarce = borrow_pressure_score(base_event(availability_score=10.0))
    assert scarce > abundant


def test_pressure_is_bounded():
    score = borrow_pressure_score(base_event(utilization_pct=500, borrow_fee_pct=999, availability_score=-100))
    assert 0 <= score <= 100


def test_low_availability_rejects_candidate():
    assessment = assess_event(base_event(availability_score=10.0))
    assert assessment.decision == "REJECT"


def test_low_confidence_requires_review_before_other_gates():
    assessment = assess_event(base_event(event_confidence=70.0, availability_score=10.0))
    assert assessment.decision == "MANUAL REVIEW"


def test_earnings_signal_calculates_relative_move():
    signal = earnings_signal(base_event())
    assert signal["interpretation"] == "Negative earnings and guidance revision"
    assert signal["relative_move_pct"] == -8.0


def test_scenario_grid_deducts_more_for_higher_fee():
    grid = scenario_grid(2.0, [1.0, 20.0], [0.0], holding_days=7, execution_cost_pct=0.2)
    assert grid.loc[20.0, 0.0] < grid.loc[1.0, 0.0]


def test_enrich_events_adds_decision_fields():
    enriched = enrich_events(pd.DataFrame([base_event()]))
    assert {"borrow_pressure_score", "decision", "net_expected_return_pct"}.issubset(enriched.columns)


def test_horizon_filters_are_auditable():
    frame = pd.DataFrame([base_event(days_to_catalyst=4), base_event(days_to_catalyst=20)])
    assert len(filter_horizon(frame, "7 day")) == 1
    assert len(filter_horizon(frame, "1 month")) == 2


def test_daily_brief_contains_controls_and_ticker():
    enriched = enrich_events(pd.DataFrame([dict(base_event(), ticker="TEST")]))
    brief = build_daily_brief(enriched, "24 Aug 2026")
    assert "TEST" in brief
    assert "CONTROL CHECKS" in brief
    assert "not an execution instruction" in brief
