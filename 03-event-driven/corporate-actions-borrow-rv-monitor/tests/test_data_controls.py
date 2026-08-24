from io import BytesIO

import pandas as pd

from data_store import build_store, joined_event_view
from reporting import build_excel_report
from validation import freshness_status, validate_events


def valid_event():
    return {
        "event_id": "EVT001",
        "published_at": "2026-08-24 07:00:00",
        "issuer": "Example plc",
        "ticker": "EXM",
        "sector": "Industrials",
        "event_type": "Earnings & Guidance",
        "headline": "Example announcement",
        "borrow_fee_pct": 2.0,
        "utilization_pct": 70.0,
        "availability_score": 50.0,
        "lender_concentration_pct": 40.0,
        "event_confidence": 95.0,
        "days_to_catalyst": 5,
        "liquidity_score": 80.0,
    }


def test_validation_routes_invalid_utilization_to_exceptions():
    bad = valid_event() | {"utilization_pct": 140.0}
    valid, exceptions = validate_events(pd.DataFrame([valid_event(), bad]))
    assert len(valid) == 1
    assert len(exceptions) == 1
    assert "utilization_pct" in exceptions.iloc[0]["exception"]


def test_freshness_status_has_three_control_bands():
    published = pd.Series(pd.to_datetime(["2026-08-24 10:00", "2026-08-24 00:00", "2026-08-20 00:00"]))
    result = freshness_status(published, pd.Timestamp("2026-08-24 12:00"))
    assert result.tolist() == ["CURRENT", "AGING", "STALE"]


def test_duckdb_view_joins_security_master_without_duplicates():
    events = pd.DataFrame([valid_event()])
    master = pd.DataFrame(
        [
            {
                "ticker": "EXM",
                "security_id": "SEC1",
                "isin": "GB00DEMO",
                "sedol": "DEMO001",
                "country": "United Kingdom",
                "currency": "GBP",
                "exchange": "London Stock Exchange",
                "market_cap_segment": "Mid Cap",
                "primary_universe": "FTSE 250",
                "ftse_100_member": False,
                "ftse_250_member": True,
                "euro_stoxx_50_member": False,
                "stoxx_europe_600_member": True,
                "effective_from": "2026-01-01",
                "effective_to": None,
                "data_mode": "DEMONSTRATION",
            }
        ]
    )
    result = joined_event_view(build_store(events, master))
    assert len(result) == 1
    assert result.iloc[0]["primary_universe"] == "FTSE 250"


def test_excel_report_contains_controlled_sheets():
    content = build_excel_report(pd.DataFrame([valid_event()]), pd.DataFrame(), pd.DataFrame())
    workbook = pd.ExcelFile(BytesIO(content))
    assert workbook.sheet_names == ["Morning Monitor", "Data Exceptions", "Decision Audit", "Control Checklist"]
