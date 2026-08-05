#!/usr/bin/env python3
"""Build and optionally email a daily FTSE 100 and automotive-sector briefing."""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import feedparser
import pandas as pd
import requests
import yfinance as yf
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from market_monitor import fetch_news, send_email


BASE_DIR = Path(__file__).resolve().parent
CONSTITUENT_CACHE = BASE_DIR / "ftse100_constituents.json"
HTML_OUTPUT = BASE_DIR / "daily_ftse_digest.html"
WORKBOOK_OUTPUT = BASE_DIR / "daily_ftse_dashboard.xlsx"
FTSE_SOURCE = "https://en.wikipedia.org/wiki/FTSE_100_Index"

UK_AUTOS = {
    "AUTO.L": "Auto Trader",
    "INCH.L": "Inchcape",
    "MOTR.L": "Motorpoint",
    "PINE.L": "Pinewood Technologies",
    "AML.L": "Aston Martin Lagonda",
}

GLOBAL_AUTOS = {
    "BMW.DE": "BMW",
    "MBG.DE": "Mercedes-Benz",
    "VOW3.DE": "Volkswagen",
    "STLAM.MI": "Stellantis",
    "RNO.PA": "Renault",
    "RACE.MI": "Ferrari",
    "VOLCAR-B.ST": "Volvo Cars",
    "TSLA": "Tesla",
    "GM": "General Motors",
    "F": "Ford",
}

MARKET_DRIVERS = {
    "^FTSE": "FTSE 100",
    "GBPUSD=X": "GBP/USD",
    "GBPEUR=X": "GBP/EUR",
    "BZ=F": "Brent crude",
    "IGLT.L": "UK gilts ETF",
    "^VIX": "VIX",
}


def yahoo_lse_ticker(epic: str) -> str:
    """Convert a London Stock Exchange EPIC into Yahoo Finance format."""
    symbol = str(epic).strip().upper()
    if symbol.endswith("."):
        symbol = symbol[:-1]
    symbol = symbol.replace(".", "-")
    return f"{symbol}.L"


def _flatten_column(column) -> str:
    if isinstance(column, tuple):
        return " ".join(str(part) for part in column if str(part) != "nan").strip()
    return str(column).strip()


def load_ftse100_constituents() -> list[dict[str, str]]:
    """Load the current FTSE 100 table and retain a local fallback cache."""
    try:
        response = requests.get(
            FTSE_SOURCE,
            timeout=20,
            headers={"User-Agent": "MelquantLabsMarketMonitor/1.0"},
        )
        response.raise_for_status()
        tables = pd.read_html(StringIO(response.text))
        selected = None
        for table in tables:
            table = table.copy()
            table.columns = [_flatten_column(column) for column in table.columns]
            ticker_column = next(
                (column for column in table.columns if column.lower() in {"ticker", "epic"}),
                None,
            )
            company_column = next(
                (column for column in table.columns if column.lower() == "company"),
                None,
            )
            if ticker_column and company_column and len(table) >= 90:
                selected = (table, ticker_column, company_column)
                break
        if selected is None:
            raise ValueError("FTSE 100 constituent table was not found")

        table, ticker_column, company_column = selected
        sector_column = next(
            (column for column in table.columns if "sector" in column.lower()),
            None,
        )
        constituents = []
        for _, row in table.iterrows():
            epic = str(row[ticker_column]).strip()
            company = str(row[company_column]).strip()
            if not epic or epic.lower() == "nan":
                continue
            constituents.append(
                {
                    "ticker": yahoo_lse_ticker(epic),
                    "epic": epic,
                    "company": company,
                    "sector": (
                        str(row[sector_column]).strip()
                        if sector_column and pd.notna(row[sector_column])
                        else "Unclassified"
                    ),
                }
            )
        if len(constituents) < 90:
            raise ValueError("FTSE 100 source returned too few constituents")
        CONSTITUENT_CACHE.write_text(json.dumps(constituents, indent=2), encoding="utf-8")
        return constituents
    except Exception:
        if CONSTITUENT_CACHE.exists():
            return json.loads(CONSTITUENT_CACHE.read_text(encoding="utf-8"))
        raise


def fetch_snapshot(tickers: list[str]) -> pd.DataFrame:
    """Download a batch and calculate daily, weekly and volume measures."""
    unique_tickers = list(dict.fromkeys(tickers))
    data = yf.download(
        unique_tickers,
        period="2mo",
        interval="1d",
        auto_adjust=True,
        actions=False,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    rows = []
    for ticker in unique_tickers:
        try:
            frame = data[ticker] if isinstance(data.columns, pd.MultiIndex) else data
            close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
            if len(close) < 2:
                continue
            volume = pd.to_numeric(frame.get("Volume"), errors="coerce").dropna()
            average_volume = float(volume.tail(20).mean()) if not volume.empty else 0.0
            latest_volume = float(volume.iloc[-1]) if not volume.empty else 0.0
            rows.append(
                {
                    "ticker": ticker,
                    "price": float(close.iloc[-1]),
                    "day_pct": float((close.iloc[-1] / close.iloc[-2] - 1) * 100),
                    "week_pct": (
                        float((close.iloc[-1] / close.iloc[-6] - 1) * 100)
                        if len(close) >= 6
                        else None
                    ),
                    "month_pct": (
                        float((close.iloc[-1] / close.iloc[-22] - 1) * 100)
                        if len(close) >= 22
                        else None
                    ),
                    "volume_ratio": (
                        latest_volume / average_volume if average_volume > 0 else None
                    ),
                    "as_of": close.index[-1].date().isoformat(),
                }
            )
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    return pd.DataFrame(rows).set_index("ticker") if rows else pd.DataFrame()


def attach_names(snapshot: pd.DataFrame, names: dict[str, str]) -> pd.DataFrame:
    result = snapshot.copy()
    result["company"] = [names.get(ticker, ticker) for ticker in result.index]
    return result


def notable_moves(snapshot: pd.DataFrame) -> pd.DataFrame:
    if snapshot.empty:
        return snapshot
    volume = snapshot["volume_ratio"].fillna(0)
    return snapshot[(snapshot["day_pct"].abs() >= 3.0) | (volume >= 2.0)].copy()


def collect_ranked_news(company_names: list[str], limit: int = 3) -> list[dict]:
    """Collect distinct, recent headlines for the market and notable movers."""
    queries = ["FTSE 100 earnings CEO trading update"]
    queries.extend(company_names[:5])
    queries.append("Auto Trader UK automotive market")
    stories = []
    seen = set()
    for query in queries:
        for story in fetch_news(query, max_items=3, days_back=2):
            key = story["title"].lower().strip()
            if key in seen:
                continue
            seen.add(key)
            stories.append(story)
            if len(stories) >= limit:
                return stories
    return stories


def _format_pct(value) -> str:
    return "—" if pd.isna(value) else f"{value:+.2f}%"


def _table(frame: pd.DataFrame, columns: list[tuple[str, str]], limit=None) -> str:
    if frame.empty:
        return "<p>No usable market data was returned.</p>"
    shown = frame.head(limit) if limit else frame
    header = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
    rows = []
    for ticker, row in shown.iterrows():
        cells = []
        for column, _ in columns:
            if column == "ticker":
                value = ticker
            elif column in {"day_pct", "week_pct", "month_pct"}:
                value = _format_pct(row.get(column))
            elif column == "volume_ratio":
                ratio = row.get(column)
                value = "—" if pd.isna(ratio) else f"{ratio:.1f}x"
            elif column == "price":
                value = f"{row.get(column):.2f}"
            else:
                value = str(row.get(column, ""))
            cells.append(f"<td>{html.escape(value)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def build_digest() -> tuple[str, dict[str, pd.DataFrame], list[dict]]:
    constituents = load_ftse100_constituents()
    ftse_names = {item["ticker"]: item["company"] for item in constituents}
    sectors = {item["ticker"]: item["sector"] for item in constituents}

    all_tickers = (
        list(ftse_names)
        + list(UK_AUTOS)
        + list(GLOBAL_AUTOS)
        + list(MARKET_DRIVERS)
    )
    snapshot = fetch_snapshot(all_tickers)
    ftse = attach_names(snapshot.loc[snapshot.index.intersection(ftse_names)], ftse_names)
    ftse["sector"] = [sectors.get(ticker, "Unclassified") for ticker in ftse.index]
    uk_autos = attach_names(snapshot.loc[snapshot.index.intersection(UK_AUTOS)], UK_AUTOS)
    global_autos = attach_names(
        snapshot.loc[snapshot.index.intersection(GLOBAL_AUTOS)], GLOBAL_AUTOS
    )
    drivers = attach_names(
        snapshot.loc[snapshot.index.intersection(MARKET_DRIVERS)], MARKET_DRIVERS
    )

    gainers = ftse.sort_values("day_pct", ascending=False).head(5)
    fallers = ftse.sort_values("day_pct").head(5)
    notable = notable_moves(ftse).sort_values("day_pct", ascending=False)
    sector_moves = (
        ftse.groupby("sector", dropna=False)["day_pct"]
        .mean()
        .sort_values(ascending=False)
        .to_frame("day_pct")
    )
    news_names = notable["company"].tolist() if not notable.empty else gainers["company"].tolist()
    news = collect_ranked_news(news_names)

    auto_row = uk_autos.loc[["AUTO.L"]] if "AUTO.L" in uk_autos.index else pd.DataFrame()
    ftse_index_move = drivers.loc["^FTSE", "day_pct"] if "^FTSE" in drivers.index else None
    auto_move = auto_row.iloc[0]["day_pct"] if not auto_row.empty else None
    relative = auto_move - ftse_index_move if auto_move is not None and ftse_index_move is not None else None

    news_html = "".join(
        "<li><strong>"
        + html.escape(story["title"])
        + "</strong><br><span>Why it matters: potential market or automotive-sector catalyst.</span> "
        + f'<a href="{html.escape(story["link"], quote=True)}">Source</a></li>'
        for story in news
    ) or "<li>No qualifying recent stories were returned.</li>"

    columns = [
        ("company", "Company"),
        ("ticker", "Ticker"),
        ("day_pct", "1 day"),
        ("week_pct", "5 days"),
        ("volume_ratio", "Volume / 20d"),
    ]
    generated = datetime.now().astimezone().strftime("%A %d %B %Y, %H:%M %Z")
    auto_summary = (
        f"Auto Trader moved {_format_pct(auto_move)} and "
        f"{_format_pct(relative)} relative to the FTSE 100 today."
        if auto_move is not None
        else "Auto Trader data was unavailable."
    )
    document = f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
body{{font-family:Arial,sans-serif;color:#17263c;max-width:1000px;margin:auto;padding:24px}}
h1{{color:#17365d}} h2{{border-bottom:2px solid #d9a441;padding-bottom:6px}}
table{{border-collapse:collapse;width:100%;margin:12px 0 24px}} th{{background:#17365d;color:white}}
th,td{{padding:8px;border:1px solid #d8dee8;text-align:left}} tr:nth-child(even){{background:#f4f7fa}}
.card{{background:#eef4f8;border-left:5px solid #2878b5;padding:14px;margin:12px 0}}
.small{{font-size:12px;color:#5f6875}}</style></head><body>
<h1>Melquant Labs Daily Autos &amp; FTSE Close</h1>
<p class="small">Generated {html.escape(generated)}</p>
<div class="card"><strong>Auto Trader:</strong> {html.escape(auto_summary)}</div>
<h2>FTSE 100 top five gainers</h2>{_table(gainers, columns)}
<h2>FTSE 100 top five fallers</h2>{_table(fallers, columns)}
<h2>Notable FTSE 100 moves</h2>{_table(notable, columns)}
<h2>Three notable stories</h2><ol>{news_html}</ol>
<h2>Auto Trader</h2>{_table(auto_row, columns)}
<h2>UK automotive basket</h2>{_table(uk_autos.sort_values('day_pct', ascending=False), columns)}
<h2>Global automotive peers</h2>{_table(global_autos.sort_values('day_pct', ascending=False), columns)}
<h2>FTSE sector heatmap</h2>{_table(sector_moves, [('ticker','Sector'),('day_pct','Average move')])}
<h2>Market drivers</h2>{_table(drivers, columns)}
<p class="small">Public-data research aid only. Prices may be delayed or revised. Headlines are automatically selected and should be verified at source. This is not investment advice.</p>
</body></html>"""
    frames = {
        "FTSE 100": ftse,
        "UK Autos": uk_autos,
        "Global Autos": global_autos,
        "Market Drivers": drivers,
        "Sector Moves": sector_moves,
    }
    return document, frames, news


def write_workbook(frames: dict[str, pd.DataFrame], news: list[dict]) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, frame in frames.items():
        sheet = workbook.create_sheet(name[:31])
        output = frame.reset_index(names="ticker")
        sheet.append(list(output.columns))
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="17365D")
        for row in output.itertuples(index=False, name=None):
            sheet.append(list(row))
    sheet = workbook.create_sheet("News")
    sheet.append(["Headline", "Link", "Published"])
    for story in news:
        published = story["published"].isoformat() if story.get("published") else ""
        sheet.append([story["title"], story["link"], published])
    workbook.save(WORKBOOK_OUTPUT)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Build files without emailing")
    args = parser.parse_args()

    document, frames, news = build_digest()
    HTML_OUTPUT.write_text(document, encoding="utf-8")
    write_workbook(frames, news)
    print(f"[ok] HTML briefing written: {HTML_OUTPUT}")
    print(f"[ok] Excel dashboard written: {WORKBOOK_OUTPUT}")
    if not args.dry_run:
        subject_date = datetime.now().strftime("%d %b %Y")
        send_email(f"Melquant Labs Daily Autos & FTSE Close | {subject_date}", document)


if __name__ == "__main__":
    main()
