"""Free public-source discovery adapters.

These adapters collect announcement candidates, not trading-ready records. Every
item retains its source URL and starts with a REQUIRES REVIEW status.
"""

from __future__ import annotations

import base64
import json
import ssl
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

import feedparser
import certifi
import pandas as pd


INBOX_COLUMNS = [
    "published_at",
    "issuer_query",
    "headline",
    "event_family",
    "source_name",
    "source_type",
    "source_url",
    "verification_status",
]

EVENT_KEYWORDS = {
    "Earnings & Guidance": ("earnings", "results", "profit warning", "guidance", "trading update"),
    "Equity Issuance": ("placing", "rights issue", "share issue", "equity raise", "offering"),
    "Takeover & Merger": (
        "takeover bid",
        "takeover offer",
        "takeover approach",
        "recommended takeover",
        "cash takeover",
        "acquisition",
        "merger",
        "offer for",
        "scheme of arrangement",
    ),
    "Dividend & Capital Return": ("dividend", "buyback", "tender offer", "capital return"),
    "Restructuring & Distress": ("restructuring", "insolvency", "administration", "liquidation", "default"),
    "Index Change": ("index inclusion", "index deletion", "index review", "rebalance"),
}


def classify_headline(headline: str) -> str:
    text = headline.lower()
    for family, terms in EVENT_KEYWORDS.items():
        if any(term in text for term in terms):
            return family
    return "Other corporate event"


def _get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> dict:
    request = Request(url, headers={"User-Agent": "MelQuantLab-FreeSourceMonitor/1.0", **(headers or {})})
    with urlopen(request, timeout=timeout, context=ssl.create_default_context(cafile=certifi.where())) as response:
        return json.loads(response.read().decode("utf-8"))


def _as_frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=INBOX_COLUMNS)
    if not frame.empty:
        frame["published_at"] = pd.to_datetime(frame["published_at"], utc=True, errors="coerce")
        frame = frame.drop_duplicates(subset=["headline", "source_url"]).sort_values(
            "published_at", ascending=False, na_position="last"
        )
    return frame.reset_index(drop=True)


def fetch_gdelt_news(query: str, max_records: int = 30, timespan: str = "3d") -> pd.DataFrame:
    """Fetch free news-discovery results from GDELT's DOC 2.0 API."""

    query = query.strip()
    if not query:
        return _as_frame([])
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc?"
        f"query={quote_plus(query)}&mode=ArtList&format=json&maxrecords={int(max_records)}"
        f"&timespan={quote_plus(timespan)}&sort=HybridRel"
    )
    payload = _get_json(url)
    rows = []
    for article in payload.get("articles", []):
        headline = str(article.get("title", "")).strip()
        if not headline:
            continue
        rows.append(
            {
                "published_at": article.get("seendate"),
                "issuer_query": query,
                "headline": headline,
                "event_family": classify_headline(headline),
                "source_name": article.get("domain") or "GDELT discovery",
                "source_type": "NEWS DISCOVERY",
                "source_url": article.get("url", ""),
                "verification_status": "REQUIRES PRIMARY-SOURCE CHECK",
            }
        )
    return _as_frame(rows)


def fetch_rss_feeds(urls: list[str]) -> pd.DataFrame:
    """Read user-selected public RSS/Atom feeds while retaining source links."""

    rows = []
    for url in (item.strip() for item in urls if item.strip()):
        request = Request(url, headers={"User-Agent": "MelQuantLab-FreeSourceMonitor/1.0"})
        with urlopen(
            request, timeout=15, context=ssl.create_default_context(cafile=certifi.where())
        ) as response:
            parsed = feedparser.parse(response.read())
        feed_name = parsed.feed.get("title", url)
        for entry in parsed.entries:
            headline = str(entry.get("title", "")).strip()
            if not headline:
                continue
            published = entry.get("published") or entry.get("updated")
            try:
                published_at = parsedate_to_datetime(published) if published else datetime.now(timezone.utc)
            except (TypeError, ValueError):
                published_at = datetime.now(timezone.utc)
            rows.append(
                {
                    "published_at": published_at,
                    "issuer_query": feed_name,
                    "headline": headline,
                    "event_family": classify_headline(headline),
                    "source_name": feed_name,
                    "source_type": "RSS / ATOM",
                    "source_url": entry.get("link", ""),
                    "verification_status": "REQUIRES PRIMARY-SOURCE CHECK",
                }
            )
    return _as_frame(rows)


def fetch_google_news(query: str, lookback_days: int = 7) -> pd.DataFrame:
    """Use Google's free UK news RSS search as a resilient discovery source."""

    query = query.strip()
    if not query:
        return _as_frame([])
    dated_query = query if "when:" in query.lower() else f"{query} when:{int(lookback_days)}d"
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(dated_query)}&hl=en-GB&gl=GB&ceid=GB:en"
    )
    result = fetch_rss_feeds([url])
    if not result.empty:
        result["issuer_query"] = query
        result["source_type"] = "NEWS DISCOVERY"
        result["verification_status"] = "REQUIRES PRIMARY-SOURCE CHECK"
        result["source_name"] = result["headline"].str.rsplit(" - ", n=1).str[-1]
        result["published_at"] = pd.to_datetime(result["published_at"], utc=True, errors="coerce")
        cutoff = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=int(lookback_days))
        result = result[
            (result["published_at"] >= cutoff)
            & (result["event_family"] != "Other corporate event")
        ].reset_index(drop=True)
    return result


def fetch_companies_house_filings(
    company_numbers: dict[str, str], api_key: str, items_per_company: int = 15
) -> pd.DataFrame:
    """Fetch official UK company filing metadata using a free API key."""

    if not api_key.strip():
        raise ValueError("A Companies House API key is required.")
    token = base64.b64encode(f"{api_key.strip()}:".encode()).decode()
    rows = []
    for issuer, company_number in company_numbers.items():
        number = company_number.strip()
        if not number:
            continue
        url = (
            "https://api.company-information.service.gov.uk/company/"
            f"{quote_plus(number)}/filing-history?items_per_page={int(items_per_company)}"
        )
        payload = _get_json(url, {"Authorization": f"Basic {token}"})
        for item in payload.get("items", []):
            description = str(item.get("description", "Company filing")).replace("-", " ").title()
            category = str(item.get("category", "filing")).replace("-", " ").title()
            headline = f"{issuer}: {description} ({category})"
            transaction_id = item.get("transaction_id", "")
            rows.append(
                {
                    "published_at": item.get("date"),
                    "issuer_query": issuer,
                    "headline": headline,
                    "event_family": classify_headline(headline),
                    "source_name": "Companies House",
                    "source_type": "OFFICIAL FILING",
                    "source_url": f"https://find-and-update.company-information.service.gov.uk/company/{number}/filing-history/{transaction_id}",
                    "verification_status": "OFFICIAL METADATA — REVIEW DOCUMENT",
                }
            )
    return _as_frame(rows)


def combine_inbox(*frames: pd.DataFrame) -> pd.DataFrame:
    populated = [frame for frame in frames if frame is not None and not frame.empty]
    return _as_frame(pd.concat(populated, ignore_index=True).to_dict("records")) if populated else _as_frame([])
