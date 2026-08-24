from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analytics import (
    build_daily_brief,
    earnings_signal,
    enrich_events,
    filter_horizon,
    incremental_lending_revenue,
    scenario_grid,
)


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "sample_events.csv"

NAVY = "#06182A"
PANEL = "#0B2638"
TEAL = "#14C8B7"
CYAN = "#43D9E7"
AMBER = "#F4B942"
RED = "#FF6B6B"
TEXT = "#EAF6F6"


st.set_page_config(page_title="Corporate Actions Borrow & RV Monitor", page_icon="◆", layout="wide")
st.markdown(
    f"""
    <style>
    .stApp {{background: radial-gradient(circle at 85% 5%, #103C52 0%, {NAVY} 35%, #04111F 100%); color:{TEXT};}}
    [data-testid="stSidebar"] {{background:{PANEL}; border-right:1px solid #1B5268;}}
    [data-testid="stMetric"] {{background:linear-gradient(145deg,#0A2A3D,#0B2233); border:1px solid #1C5368;
        padding:15px; border-radius:12px; box-shadow:0 8px 25px rgba(0,0,0,.18);}}
    div[data-testid="stMetricValue"] {{color:{TEAL};}}
    .hero {{padding:22px 26px; border:1px solid #1E6075; border-radius:16px;
        background:linear-gradient(120deg,rgba(11,38,56,.96),rgba(7,63,76,.74)); margin-bottom:18px;}}
    .eyebrow {{color:{TEAL}; font-weight:700; letter-spacing:.16em; font-size:.75rem;}}
    .hero h1 {{margin:.25rem 0 .35rem; color:white; font-size:2.25rem;}}
    .hero p {{color:#B8D5DE; margin:0; max-width:900px;}}
    .note {{border-left:4px solid {AMBER}; background:#102C3D; padding:11px 15px; border-radius:5px; color:#D9E8EC;}}
    .stTabs [data-baseweb="tab-list"] {{gap:8px;}}
    .stTabs [data-baseweb="tab"] {{background:#0A2638; border-radius:8px; padding:8px 14px;}}
    </style>
    <div class="hero">
      <div class="eyebrow">MELQUANTLAB · EVENT-DRIVEN RESEARCH</div>
      <h1>Corporate Actions Borrow & Relative Value Monitor</h1>
      <p>Turn earnings and corporate events into validated inventory alerts and borrow-adjusted research candidates—with explicit reasons to trade, review or reject.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_events() -> pd.DataFrame:
    frame = pd.read_csv(DATA_PATH, parse_dates=["published_at"])
    return enrich_events(frame)


events = load_events()

with st.sidebar:
    st.subheader("Morning controls")
    selected_types = st.multiselect("Event families", sorted(events.event_type.unique()), default=sorted(events.event_type.unique()))
    selected_sectors = st.multiselect("Sectors", sorted(events.sector.unique()), default=sorted(events.sector.unique()))
    selected_horizon = st.radio("Catalyst horizon", ["All", "7 day", "1 month"], horizontal=True)
    min_pressure = st.slider("Minimum borrow-pressure indicator", 0, 100, 0, 5)
    st.markdown("---")
    st.caption("All companies and borrow observations in this prototype are illustrative. No live trading recommendation is produced.")

filtered = events[
    events.event_type.isin(selected_types)
    & events.sector.isin(selected_sectors)
    & (events.borrow_pressure_score >= min_pressure)
].copy()
filtered = filter_horizon(filtered, selected_horizon)

urgent = int((filtered.borrow_pressure_score >= 75).sum())
review = int((filtered.decision == "MANUAL REVIEW").sum())
watchlist = int((filtered.decision == "WATCHLIST").sum())
rejected = int((filtered.decision == "REJECT").sum())

m1, m2, m3, m4 = st.columns(4)
m1.metric("Validated events", len(filtered))
m2.metric("Urgent inventory reviews", urgent)
m3.metric("Research watchlist", watchlist)
m4.metric("Review / reject", review + rejected)

tabs = st.tabs([
    "Morning monitor",
    "Heatmaps",
    "Event drilldown",
    "Earnings lab",
    "Relative-value scenarios",
    "Desk economics",
    "Daily email draft",
    "Integration roadmap",
    "Methodology",
])

with tabs[0]:
    st.subheader("Priority queue")
    display = filtered.sort_values(["borrow_pressure_score", "event_confidence"], ascending=False)[
        ["published_at", "ticker", "issuer", "sector", "event_type", "borrow_pressure_score", "inventory_action", "net_expected_return_pct", "stress_loss_pct", "decision"]
    ].copy()
    display.columns = ["Published", "Ticker", "Issuer", "Sector", "Event", "Borrow pressure", "Inventory action", "Net return %", "Stress loss %", "Decision"]
    st.dataframe(
        display,
        column_config={
            "Borrow pressure": st.column_config.ProgressColumn(
                "Borrow pressure", min_value=0, max_value=100, format="%d"
            ),
            "Net return %": st.column_config.NumberColumn(format="%.2f"),
            "Stress loss %": st.column_config.NumberColumn(format="%.2f"),
        },
        width="stretch",
        hide_index=True,
        height=355,
    )

    left, right = st.columns([1.15, 1])
    with left:
        fig = px.scatter(
            filtered,
            x="stress_loss_pct",
            y="net_expected_return_pct",
            size="borrow_pressure_score",
            color="event_type",
            hover_name="ticker",
            hover_data=["issuer", "decision"],
            title="Net return versus stressed loss",
            color_discrete_sequence=[TEAL, CYAN, AMBER, RED],
        )
        fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=PANEL, legend_title_text="Event")
        fig.add_hline(y=0.5, line_dash="dot", line_color=AMBER)
        st.plotly_chart(fig, width="stretch")
    with right:
        sector_counts = filtered.groupby(["sector", "decision"], as_index=False).size()
        fig = px.bar(sector_counts, x="sector", y="size", color="decision", title="Decision mix by sector", color_discrete_map={"WATCHLIST": TEAL, "MANUAL REVIEW": AMBER, "REJECT": RED})
        fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=PANEL, xaxis_title="", yaxis_title="Events", legend_title_text="")
        st.plotly_chart(fig, width="stretch")

with tabs[1]:
    st.subheader("Where attention is clustering")
    event_heat = pd.crosstab(filtered["sector"], filtered["event_type"])
    fig = px.imshow(
        event_heat,
        text_auto=True,
        aspect="auto",
        color_continuous_scale=[[0, PANEL], [0.55, TEAL], [1, AMBER]],
        title="Event concentration by sector",
    )
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=PANEL)
    st.plotly_chart(fig, width="stretch")

    pressure_heat = filtered.pivot_table(
        index="sector", columns="event_type", values="borrow_pressure_score", aggfunc="mean"
    ).fillna(0)
    fig = px.imshow(
        pressure_heat,
        text_auto=".0f",
        aspect="auto",
        color_continuous_scale=[[0, PANEL], [0.55, TEAL], [0.8, AMBER], [1, RED]],
        zmin=0,
        zmax=100,
        title="Average borrow-pressure indicator",
    )
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=PANEL)
    st.plotly_chart(fig, width="stretch")

with tabs[2]:
    ticker = st.selectbox("Select an event", filtered.ticker.tolist() if not filtered.empty else events.ticker.tolist())
    row = events.loc[events.ticker == ticker].iloc[0]
    st.markdown(f"### {row['issuer']} · {row['ticker']}")
    st.caption(f"{row['event_type']} · published {row['published_at']:%d %b %Y %H:%M}")
    st.info(row["headline"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Borrow pressure", f"{row['borrow_pressure_score']:.0f}/100")
    c2.metric("Utilization", f"{row['utilization_pct']:.0f}%")
    c3.metric("Illustrative fee", f"{row['borrow_fee_pct']:.1f}%")
    c4.metric("Availability", f"{row['availability_score']:.0f}/100")

    l, r = st.columns(2)
    with l:
        st.markdown("#### Inventory assessment")
        st.write(row["inventory_action"])
        st.progress(int(row["borrow_pressure_score"]))
        st.write(f"Lender concentration: **{row['lender_concentration_pct']:.0f}%**")
        st.write(f"Days to catalyst: **{int(row['days_to_catalyst'])}**")
    with r:
        st.markdown("#### Research decision")
        if row["decision"] == "WATCHLIST":
            st.success(row["decision"])
        elif row["decision"] == "REJECT":
            st.error(row["decision"])
        else:
            st.warning(row["decision"])
        st.write(row["decision_reason"])
        st.write(f"Expected net return: **{row['net_expected_return_pct']:.2f}%**")
        st.write(f"Reward/stress ratio: **{row['reward_to_stress']:.2f}**")

with tabs[3]:
    earnings = events[events.event_type == "Earnings & Guidance"].copy()
    selected = st.selectbox("Earnings event", earnings.ticker.tolist(), key="earnings_ticker")
    erow = earnings.loc[earnings.ticker == selected].iloc[0]
    signal = earnings_signal(erow)
    st.markdown(f"### {erow['issuer']} · {signal['interpretation']}")
    a, b, c, d = st.columns(4)
    a.metric("Earnings surprise", f"{erow['earnings_surprise_pct']:+.1f}%")
    b.metric("Guidance change", f"{erow['guidance_change_pct']:+.1f}%")
    c.metric("Stock reaction", f"{erow['price_reaction_pct']:+.1f}%")
    d.metric("Relative to peer", f"{signal['relative_move_pct']:+.1f}%")
    fig = go.Figure(go.Bar(
        x=["Earnings surprise", "Guidance change", "Stock reaction", f"Peer ({erow['peer_ticker']})"],
        y=[erow["earnings_surprise_pct"], erow["guidance_change_pct"], erow["price_reaction_pct"], erow["peer_return_pct"]],
        marker_color=[TEAL, CYAN, RED if erow["price_reaction_pct"] < 0 else TEAL, AMBER],
    ))
    fig.update_layout(title="Reported signal and market response", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=PANEL, yaxis_title="Percent")
    st.plotly_chart(fig, width="stretch")
    st.markdown('<div class="note">A miss is not automatically a short and a beat is not automatically a long. The reaction must be assessed against guidance, peers, valuation, positioning, borrow and downside.</div>', unsafe_allow_html=True)

with tabs[4]:
    st.subheader("Borrow-fee and relative-move sensitivity")
    c1, c2, c3 = st.columns(3)
    base = c1.number_input("Base gross spread return (%)", -10.0, 15.0, 2.5, 0.25)
    days = c2.slider("Holding period (days)", 1, 30, 7)
    execution = c3.number_input("Execution cost (%)", 0.0, 2.0, 0.25, 0.05)
    fees = [0.5, 2.5, 5.0, 10.0, 20.0]
    moves = [-4.0, -2.0, 0.0, 2.0, 4.0]
    grid = scenario_grid(base, fees, moves, days, execution)
    fig = px.imshow(
        grid,
        text_auto=".2f",
        aspect="auto",
        color_continuous_scale=[[0, RED], [0.5, PANEL], [1, TEAL]],
        labels={"x": "Additional relative move (%)", "y": "Annual borrow fee (%)", "color": "Net P&L %"},
        title="Net P&L sensitivity (%)",
    )
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=PANEL)
    st.plotly_chart(fig, width="stretch")

with tabs[5]:
    st.subheader("How the desk captures value")
    st.caption("Translate an early signal into measurable revenue or avoided loss. This calculator isolates fee repricing; it does not include every cost or revenue component.")

    role = st.radio(
        "Desk perspective",
        ["Sell-side securities finance", "Asset manager / beneficial owner"],
        horizontal=True,
    )
    if role == "Sell-side securities finance":
        st.markdown(
            "**Commercial levers:** reprice scarce inventory earlier, secure term supply, improve locate conversion, allocate balance sheet deliberately and reduce recall or settlement losses."
        )
    else:
        st.markdown(
            "**Commercial levers:** avoid lending valuable inventory too cheaply, negotiate improved fees, preserve voting/recall optionality and treat borrow demand as market intelligence."
        )

    e1, e2, e3, e4, e5 = st.columns(5)
    market_value = e1.number_input("Inventory market value (£)", 100_000.0, 500_000_000.0, 10_000_000.0, 100_000.0)
    current_fee = e2.number_input("Current fee (%)", 0.0, 100.0, 2.0, 0.25)
    improved_fee = e3.number_input("Repriced fee (%)", 0.0, 100.0, 7.0, 0.25)
    loan_days = e4.slider("Days on loan", 1, 365, 30)
    revenue_share = e5.slider("Revenue retained (%)", 0, 100, 100)
    economics = incremental_lending_revenue(
        market_value, current_fee, improved_fee, loan_days, revenue_share
    )

    v1, v2, v3 = st.columns(3)
    v1.metric("Fee improvement", f"{economics['fee_improvement_pct']:+.2f}%")
    v2.metric("Gross incremental revenue", f"£{economics['gross_incremental_revenue']:,.0f}")
    v3.metric("Retained incremental revenue", f"£{economics['retained_incremental_revenue']:,.0f}")
    st.code("Market value × fee improvement × days / 365 × revenue share")
    st.markdown(
        '<div class="note">Full desk attribution should also include matched-inventory spread, client revenue, balance-sheet cost, collateral economics, operational cost and avoided recall, buy-in or settlement loss.</div>',
        unsafe_allow_html=True,
    )

    st.markdown("#### From signal to money")
    st.dataframe(
        pd.DataFrame(
            [
                ["Demand likely to rise", "Secure supply and review client offers", "Capture a better fee or spread"],
                ["Inventory likely to tighten", "Preserve scarce stock and assess term", "Avoid lending too cheaply"],
                ["Fee may ease after issuance", "Avoid overpaying for future supply", "Protect financing margin"],
                ["Recall risk is rising", "Reduce fragile exposure and coordinate operations", "Avoid forced-close and fail costs"],
                ["Economics fail under stress", "Reject or resize", "Avoid a low-quality loss"],
            ],
            columns=["Signal", "Desk action", "Value mechanism"],
        ),
        hide_index=True,
        width="stretch",
    )

with tabs[6]:
    st.subheader("Review-ready daily briefing")
    st.caption("The application generates a draft only. A human validates sources, terms and recipients before circulation.")
    brief = build_daily_brief(filtered, pd.Timestamp.now(tz="Europe/London").strftime("%d %b %Y %H:%M %Z"))
    st.text_area("Email preview", brief, height=480)
    st.download_button(
        "Download draft as text",
        data=brief,
        file_name="corporate_actions_borrow_brief.txt",
        mime="text/plain",
    )
    st.markdown("#### Two operating modes")
    st.dataframe(
        pd.DataFrame(
            {
                "Authorised terminal environment": ["Licensed event/reference data", "Approved internal inventory and locate fields", "Firm communication controls"],
                "Accessible research environment": ["Issuer and regulatory announcements", "Clearly labelled sample/proxy borrow fields", "Downloadable draft for manual review"],
            }
        ),
        hide_index=True,
        width="stretch",
    )

with tabs[7]:
    st.subheader("Bloomberg, SQL, Excel/VBA and email operating model")
    st.caption("Architecture proposal only: no Bloomberg or internal desk connection is included in this public prototype.")

    st.markdown("#### What connects to what")
    st.code(
        "Bloomberg / RNS / issuer events\n"
        "            ↓\n"
        "Python validation and analytics ← internal inventory, fees and locates\n"
        "            ↓\n"
        "SQL event, signal and decision history\n"
        "            ↓\n"
        "Streamlit monitor + controlled Excel desk view\n"
        "            ↓\n"
        "VBA refresh/export controls → unsent email draft → trader approval"
    )

    mode = st.radio("Proposed data mode", ["Bloomberg Terminal / Desktop API", "Enterprise data feeds", "Public research prototype"], horizontal=True)
    mode_rows = {
        "Bloomberg Terminal / Desktop API": [
            ["Market and event data", "Authorised Bloomberg Desktop API session"],
            ["Inventory and client demand", "Approved internal securities-finance systems"],
            ["Use case", "Trader-side research and monitored workflow"],
        ],
        "Enterprise data feeds": [
            ["Market and event data", "Licensed enterprise feeds / controlled landing area"],
            ["Inventory and client demand", "Internal stock-loan platform"],
            ["Use case", "Scheduled, resilient multi-user production service"],
        ],
        "Public research prototype": [
            ["Market and event data", "Permitted issuer and regulatory sources"],
            ["Inventory and client demand", "Clearly labelled sample or proxy fields"],
            ["Use case", "Learning, demonstration and methodology testing"],
        ],
    }
    st.dataframe(
        pd.DataFrame(mode_rows[mode], columns=["Component", "Source / purpose"]),
        hide_index=True,
        width="stretch",
    )

    st.markdown("#### Why SQL and VBA are included")
    q1, q2 = st.columns(2)
    with q1:
        st.markdown("**SQL is the memory**")
        st.write("Stores events, amendments, identifiers, borrow snapshots, signals, decisions and realised outcomes so the desk can audit and backtest what was known at the time.")
        st.code(
            "SELECT ticker, event_type, borrow_fee_pct,\n"
            "       utilization_pct, decision\n"
            "FROM morning_priority_view\n"
            "ORDER BY priority_score DESC;",
            language="sql",
        )
    with q2:
        st.markdown("**Excel/VBA is the controlled hand-off**")
        st.write("Refreshes approved SQL views, flags stale inputs, records approvals and creates a formatted but unsent briefing. Core calculations remain visible and tested in Python.")
        st.code(
            "Refresh approved SQL data\n"
            "Validate mandatory fields\n"
            "Populate morning sheet\n"
            "Create unsent Outlook draft\n"
            "Record approval or rejection",
            language="text",
        )

    st.warning("Production controls: entitlements, data licensing, recipient restrictions, source timestamps, maker-checker approval, audit logging and no automatic execution or email release.")

with tabs[8]:
    st.subheader("What this prototype does")
    st.write("It demonstrates a controlled workflow: ingest → validate → assess → risk-gate → monitor → record outcome.")
    st.subheader("What it does not claim")
    st.write("It does not use live borrow data, licensed consensus, automatic execution or validated production forecasts.")
    st.subheader("Transparent borrow-pressure formula")
    st.code("event prior + 0.34×utilization + 0.18×lender concentration + 0.24×scarcity + fee signal + capped issuance effect")
    st.caption("The coefficients are research priors for demonstration and must be tested on point-in-time institutional data.")
