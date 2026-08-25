from datetime import date

import pandas as pd

from calendar_sources import fetch_watchlist_calendar


class FakeTicker:
    calls = []

    def __init__(self, _ticker):
        self.ticker = _ticker
        self.calls.append(_ticker)

    def get_calendar(self):
        return {
            "Earnings Date": [date(2026, 8, 27)],
            "Ex-Dividend Date": date(2026, 9, 10),
        }


def test_calendar_only_keeps_events_inside_seven_day_window():
    watchlist = pd.DataFrame(
        [{"issuer": "Example plc", "ticker": "EXM", "yahoo_ticker": "EXM.L", "sector": "Industrials", "market": "United Kingdom"}]
    )
    events, exceptions = fetch_watchlist_calendar(
        watchlist, as_of=date(2026, 8, 24), ticker_factory=FakeTicker
    )
    assert exceptions.empty
    assert len(events) == 1
    assert events.iloc[0]["days_remaining"] == 3
    assert events.iloc[0]["event_type"] == "Earnings & Guidance"


def test_calendar_deduplicates_vendor_tickers_before_fetching():
    FakeTicker.calls = []
    duplicate_universe = pd.DataFrame(
        [
            {"issuer": "Example plc", "ticker": "EXM", "yahoo_ticker": "EXM.L", "sector": "Industrials", "market": "United Kingdom"},
            {"issuer": "Example plc", "ticker": "EXM", "yahoo_ticker": "EXM.L", "sector": "Industrials", "market": "United Kingdom"},
        ]
    )

    events, exceptions = fetch_watchlist_calendar(
        duplicate_universe, as_of=date(2026, 8, 24), ticker_factory=FakeTicker
    )

    assert exceptions.empty
    assert FakeTicker.calls == ["EXM.L"]
    assert len(events) == 1
