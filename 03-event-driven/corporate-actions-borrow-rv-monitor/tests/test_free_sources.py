import pandas as pd

import free_sources
from free_sources import classify_headline, combine_inbox, fetch_companies_house_filings, fetch_gdelt_news, fetch_google_news


def test_headline_classifier_covers_core_event_families():
    assert classify_headline("Company announces accelerated placing") == "Equity Issuance"
    assert classify_headline("Board recommends cash takeover") == "Takeover & Merger"
    assert classify_headline("Full-year results and guidance update") == "Earnings & Guidance"
    assert classify_headline("Tesco launches café takeover promotion") == "Other corporate event"


def test_gdelt_adapter_retains_source_and_requires_verification(monkeypatch):
    monkeypatch.setattr(
        free_sources,
        "_get_json",
        lambda *_args, **_kwargs: {
            "articles": [{"title": "Example profit warning", "url": "https://example.com/a", "domain": "example.com", "seendate": "20260824T080000Z"}]
        },
    )
    result = fetch_gdelt_news("Example")
    assert result.iloc[0]["source_url"] == "https://example.com/a"
    assert result.iloc[0]["event_family"] == "Earnings & Guidance"
    assert "PRIMARY-SOURCE" in result.iloc[0]["verification_status"]


def test_companies_house_adapter_marks_official_metadata(monkeypatch):
    monkeypatch.setattr(
        free_sources,
        "_get_json",
        lambda *_args, **_kwargs: {
            "items": [{"date": "2026-08-24", "description": "resolution", "category": "capital", "transaction_id": "ABC123"}]
        },
    )
    result = fetch_companies_house_filings({"Example plc": "01234567"}, "free-key")
    assert result.iloc[0]["source_type"] == "OFFICIAL FILING"
    assert "01234567" in result.iloc[0]["source_url"]


def test_google_news_adapter_marks_results_as_discovery(monkeypatch):
    sample = pd.DataFrame(
        [{
            "published_at": "2026-08-24",
            "issuer_query": "feed",
            "headline": "Example trading update",
            "event_family": "Earnings & Guidance",
            "source_name": "News",
            "source_type": "RSS / ATOM",
            "source_url": "https://example.com/item",
            "verification_status": "REQUIRES PRIMARY-SOURCE CHECK",
        }]
    )
    monkeypatch.setattr(free_sources, "fetch_rss_feeds", lambda _urls: sample.copy())
    result = fetch_google_news("Example")
    assert result.iloc[0]["issuer_query"] == "Example"
    assert result.iloc[0]["source_type"] == "NEWS DISCOVERY"


def test_combined_inbox_deduplicates_links():
    row = {
        "published_at": "2026-08-24",
        "issuer_query": "Example",
        "headline": "Example results",
        "event_family": "Earnings & Guidance",
        "source_name": "Example",
        "source_type": "RSS / ATOM",
        "source_url": "https://example.com/results",
        "verification_status": "REQUIRES PRIMARY-SOURCE CHECK",
    }
    result = combine_inbox(pd.DataFrame([row]), pd.DataFrame([row]))
    assert len(result) == 1
