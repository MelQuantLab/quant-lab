#!/usr/bin/env python3
"""Build and optionally email a daily FTSE 100 and automotive-sector briefing."""

from __future__ import annotations

import argparse
import base64
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
LOGO_PATH = BASE_DIR / "assets" / "melquantlab-logo.jpg"
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


def _move_colour(value) -> str:
    if pd.isna(value):
        return "#9FB0C5"
    if value > 0:
        return "#34D6A2"
    if value < 0:
        return "#FF6B7A"
    return "#F7FAFC"


def _table(
    frame: pd.DataFrame,
    columns: list[tuple[str, str]],
    limit=None,
    emphasise_first: bool = False,
) -> str:
    if frame.empty:
        return '<p style="color:#9FB0C5;margin:12px 0 22px;">No usable market data was returned.</p>'
    shown = frame.head(limit) if limit else frame
    header = "".join(
        '<th style="background:#17395F;color:#D9E6F3;font-size:11px;letter-spacing:.5px;'
        f'text-transform:uppercase;padding:10px 9px;text-align:left;border-bottom:1px solid #31567E;">{html.escape(label)}</th>'
        for _, label in columns
    )
    rows = []
    for row_number, (ticker, row) in enumerate(shown.iterrows()):
        cells = []
        for column, _ in columns:
            cell_colour = "#ECF4FC"
            weight = "800" if emphasise_first and row_number == 0 else "500"
            if column == "ticker":
                value = ticker
            elif column in {"day_pct", "week_pct", "month_pct"}:
                raw_value = row.get(column)
                value = _format_pct(raw_value)
                cell_colour = _move_colour(raw_value)
                weight = "800" if emphasise_first and row_number == 0 else "700"
            elif column == "volume_ratio":
                ratio = row.get(column)
                value = "—" if pd.isna(ratio) else f"{ratio:.1f}x"
                if not pd.isna(ratio) and ratio >= 2:
                    cell_colour = "#F6BD4A"
                    weight = "800" if emphasise_first and row_number == 0 else "700"
            elif column == "price":
                value = f"{row.get(column):.2f}"
            else:
                value = str(row.get(column, ""))
            background = "#102A47" if row_number % 2 == 0 else "#0D243E"
            cells.append(
                f'<td style="background:{background};color:{cell_colour};font-size:13px;'
                f'font-weight:{weight};padding:10px 9px;border-bottom:1px solid #274766;">'
                f'{html.escape(value)}</td>'
            )
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<table class="data-table" role="presentation" cellspacing="0" cellpadding="0" width="100%" '
        'style="width:100%;table-layout:fixed;border-collapse:separate;border-spacing:0;margin:10px 0 24px;border:1px solid #274766;'
        f'border-radius:10px;overflow:hidden;"><thead><tr>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
    )


def _metric_card(label: str, value: str, colour: str, note: str = "") -> str:
    return f"""
    <td class="metric-cell" width="25%" valign="top" style="padding:5px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#112C4A;border:1px solid #2B4F73;border-radius:12px;">
        <tr><td style="padding:14px 14px 4px;color:#8EA5BD;font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;">{html.escape(label)}</td></tr>
        <tr><td style="padding:0 14px;color:{colour};font-size:24px;font-weight:700;line-height:1.2;">{html.escape(value)}</td></tr>
        <tr><td style="padding:5px 14px 14px;color:#8EA5BD;font-size:10px;">{html.escape(note)}</td></tr>
      </table>
    </td>"""


def _section_title(kicker: str, title: str) -> str:
    return f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:28px;">
      <tr><td style="color:#F6BD4A;font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;padding-bottom:5px;">{html.escape(kicker)}</td></tr>
      <tr><td style="color:#F7FAFC;font-size:23px;font-weight:700;line-height:1.2;padding-bottom:9px;border-bottom:1px solid #345675;">{html.escape(title)}</td></tr>
    </table>"""


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
        f"""
        <tr>
          <td width="42" valign="top" style="padding:12px 0;">
            <div style="width:30px;height:30px;line-height:30px;text-align:center;background:#F6BD4A;color:#07121F;border-radius:15px;font-size:12px;font-weight:800;">{number:02d}</div>
          </td>
          <td valign="top" style="padding:12px 0;border-bottom:1px solid #294B6B;">
            <div style="color:#F7FAFC;font-size:15px;font-weight:700;line-height:1.35;">{html.escape(story["title"])}</div>
            <div style="color:#9FB0C5;font-size:12px;line-height:1.45;margin-top:5px;">Potential market or automotive-sector catalyst. Verify the detail and timing at source.</div>
            <a href="{html.escape(story["link"], quote=True)}" style="display:inline-block;color:#46CFF5;font-size:12px;font-weight:700;text-decoration:none;margin-top:7px;">READ SOURCE →</a>
          </td>
        </tr>"""
        for number, story in enumerate(news, start=1)
    ) or '<tr><td style="color:#9FB0C5;padding:16px 0;">No qualifying recent stories were returned.</td></tr>'

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
    ftse_move = ftse_index_move
    advancers = int((ftse["day_pct"] > 0).sum())
    decliners = int((ftse["day_pct"] < 0).sum())
    leader_name = str(gainers.iloc[0]["company"]) if not gainers.empty else "—"
    leader_move = gainers.iloc[0]["day_pct"] if not gainers.empty else None
    laggard_name = str(fallers.iloc[0]["company"]) if not fallers.empty else "—"
    laggard_move = fallers.iloc[0]["day_pct"] if not fallers.empty else None
    brent_move = drivers.loc["BZ=F", "day_pct"] if "BZ=F" in drivers.index else None
    auto_week = auto_row.iloc[0]["week_pct"] if not auto_row.empty else None
    auto_month = auto_row.iloc[0]["month_pct"] if not auto_row.empty else None
    auto_volume = auto_row.iloc[0]["volume_ratio"] if not auto_row.empty else None
    auto_price = auto_row.iloc[0]["price"] if not auto_row.empty else None
    sector_display = pd.concat([sector_moves.head(4), sector_moves.tail(4)]).drop_duplicates()
    logo_data = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    logo_src = f"data:image/jpeg;base64,{logo_data}"

    document = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
@media only screen and (max-width:620px) {{
  .shell {{ width:100% !important; border-radius:0 !important; }}
  .content-pad {{ padding:18px 12px 8px !important; }}
  .header-pad {{ padding:20px 16px !important; }}
  .footer-pad {{ padding:18px 16px !important; }}
  .metric-cell {{ display:block !important; width:100% !important; box-sizing:border-box !important; }}
  .data-table {{ table-layout:fixed !important; }}
  .data-table th, .data-table td {{ padding:8px 4px !important; font-size:10px !important; overflow-wrap:anywhere !important; }}
  .headline {{ font-size:23px !important; }}
}}
</style></head>
<body style="margin:0;padding:0;background:#050D17;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:#F7FAFC;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#050D17;"><tr><td align="center" style="padding:22px 10px;">
<table class="shell" role="presentation" width="100%" cellspacing="0" cellpadding="0" style="width:100%;max-width:760px;background:#091827;border:1px solid #1D3C5C;border-radius:20px;overflow:hidden;">
  <tr><td class="header-pad" style="background:#07121F;padding:24px 30px;border-bottom:1px solid #254A6B;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>
      <td width="92" valign="middle"><img src="{logo_src}" alt="Melquant Labs" width="76" height="76" style="display:block;border-radius:38px;border:1px solid #F6BD4A;"></td>
      <td valign="middle">
        <div style="color:#F6BD4A;font-size:10px;font-weight:800;letter-spacing:2px;text-transform:uppercase;">Closing Bell · Autos Intelligence</div>
        <div class="headline" style="color:#F7FAFC;font-size:28px;font-weight:700;line-height:1.15;margin-top:5px;">Daily Autos &amp; FTSE Close</div>
        <div style="color:#8EA5BD;font-size:12px;margin-top:7px;">{html.escape(generated)} · ANALYZE <span style="color:#F6BD4A;">•</span> MODEL <span style="color:#46CFF5;">•</span> ALPHA</div>
      </td>
    </tr></table>
  </td></tr>
  <tr><td class="content-pad" style="padding:22px 25px 10px;">
    <div style="color:#8EA5BD;font-size:10px;font-weight:800;letter-spacing:1.4px;text-transform:uppercase;margin:0 5px 5px;">Market pulse</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>
      {_metric_card('FTSE 100', _format_pct(ftse_move), _move_colour(ftse_move), f'{advancers} up / {decliners} down')}
      {_metric_card('Auto Trader', _format_pct(auto_move), _move_colour(auto_move), f'{_format_pct(relative)} vs FTSE')}
      {_metric_card('Brent', _format_pct(brent_move), _move_colour(brent_move), 'autos input signal')}
      {_metric_card('Notable moves', str(len(notable)), '#F6BD4A', 'price or volume flags')}
    </tr></table>

    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#102A47;border-left:4px solid #F6BD4A;border-radius:10px;margin:14px 5px 0;">
      <tr><td style="padding:15px 18px;color:#DCE8F4;font-size:14px;line-height:1.5;"><strong style="color:#FFFFFF;">Desk read:</strong> {html.escape(auto_summary)} <strong style="color:#34D6A2;">Leader:</strong> {html.escape(leader_name)} {_format_pct(leader_move)}. <strong style="color:#FF6B7A;">Laggard:</strong> {html.escape(laggard_name)} {_format_pct(laggard_move)}.</td></tr>
    </table>

    {_section_title('Priority coverage', 'Auto Trader spotlight')}
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:10px 0 5px;"><tr>
      {_metric_card('Price', '—' if auto_price is None else f'{auto_price:.2f}', '#F7FAFC', 'latest close')}
      {_metric_card('1 day', _format_pct(auto_move), _move_colour(auto_move), 'absolute move')}
      {_metric_card('5 days', _format_pct(auto_week), _move_colour(auto_week), 'weekly trend')}
      {_metric_card('1 month', _format_pct(auto_month), _move_colour(auto_month), 'medium trend')}
    </tr></table>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>
      <td width="50%" style="padding:5px;"><div style="background:#112C4A;border:1px solid #2B4F73;border-radius:10px;padding:13px;color:#9FB0C5;font-size:11px;">RELATIVE TO FTSE 100<br><strong style="color:{_move_colour(relative)};font-size:20px;">{_format_pct(relative)}</strong></div></td>
      <td width="50%" style="padding:5px;"><div style="background:#112C4A;border:1px solid #2B4F73;border-radius:10px;padding:13px;color:#9FB0C5;font-size:11px;">VOLUME VS 20-DAY<br><strong style="color:#46CFF5;font-size:20px;">{'—' if pd.isna(auto_volume) else f'{auto_volume:.1f}x'}</strong></div></td>
    </tr></table>

    {_section_title('FTSE 100 tape', 'Leaders')}
    {_table(gainers, columns, emphasise_first=True)}
    {_section_title('FTSE 100 tape', 'Laggards')}
    {_table(fallers, columns, emphasise_first=True)}
    {_section_title('Catalyst radar', 'Three stories that matter')}
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:7px 0 18px;">{news_html}</table>
    {_section_title('Signal monitor', 'Notable FTSE 100 moves')}
    {_table(notable, columns)}
    {_section_title('UK autos', 'Domestic automotive tape')}
    {_table(uk_autos.sort_values('day_pct', ascending=False), columns)}
    {_section_title('Global autos', 'OEM and peer pulse')}
    {_table(global_autos.sort_values('day_pct', ascending=False), columns)}
    {_section_title('Cross-market context', 'Sector leadership')}
    {_table(sector_display, [('ticker','Sector'),('day_pct','Average move')])}
    {_section_title('Cross-market context', 'Drivers dashboard')}
    {_table(drivers, columns)}
  </td></tr>
  <tr><td class="footer-pad" style="background:#07121F;padding:22px 30px;border-top:1px solid #254A6B;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>
      <td valign="middle" style="color:#F6BD4A;font-size:12px;font-weight:800;letter-spacing:1px;">MELQUANT LABS</td>
      <td align="right" style="color:#71869C;font-size:10px;line-height:1.5;">Public-data research aid only.<br>Verify prices and headlines at source. Not investment advice.</td>
    </tr></table>
  </td></tr>
</table></td></tr></table></body></html>"""
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
        email_document = document.replace(
            f"data:image/jpeg;base64,{base64.b64encode(LOGO_PATH.read_bytes()).decode('ascii')}",
            "cid:melquantlabs-logo",
        )
        send_email(
            f"Melquant Labs Closing Bell | Autos & FTSE | {subject_date}",
            email_document,
            inline_images={"melquantlabs-logo": LOGO_PATH},
        )


if __name__ == "__main__":
    main()
