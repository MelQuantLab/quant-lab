from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from analytics import TradeInputs, calculate_trade, economics_table, pnl_path, scenario_grid


st.set_page_config(page_title="Equity Borrow & Financing Lab", page_icon="◈", layout="wide")

st.markdown("""
<style>
:root { --navy:#07111f; --panel:#0d1b2a; --panel2:#102337; --teal:#2dd4bf; --muted:#8fa7ba; }
.stApp { background: radial-gradient(circle at 70% 0%, #102a3d 0%, #07111f 42%); color:#ecf6f8; }
[data-testid="stSidebar"] { background:#081522; border-right:1px solid #17364a; }
[data-testid="stMetric"] { background:linear-gradient(145deg,#102337,#0b1a29); border:1px solid #1a3a4c; padding:18px; border-radius:14px; }
[data-testid="stMetricValue"] { color:#e8fbf8; }
.eyebrow { color:#2dd4bf; letter-spacing:.16em; text-transform:uppercase; font-size:.72rem; font-weight:700; }
.hero { padding:1.2rem 0 .7rem; }
.hero h1 { font-size:2.35rem; margin:.25rem 0; letter-spacing:-.03em; }
.hero p { color:#a6bac8; max-width:850px; font-size:1.02rem; }
.chip { display:inline-block; padding:.22rem .55rem; border:1px solid #255067; color:#91dcd3; border-radius:99px; margin-right:.35rem; font-size:.75rem; }
.explain { background:#0d1b2a; border:1px solid #17364a; border-left:3px solid #2dd4bf; border-radius:12px; padding:1rem 1.15rem; color:#b9cbd6; }
.good { color:#2dd4bf; } .warn { color:#fbbf24; }
div[data-testid="stDataFrame"] { border:1px solid #17364a; border-radius:12px; overflow:hidden; }
#MainMenu, footer { visibility:hidden; }
</style>
""", unsafe_allow_html=True)

st.markdown("""<div class="hero"><div class="eyebrow">MelQuantLab · Interview Project</div>
<h1>Equity Borrow & Financing Scenario Lab</h1>
<p>Explore whether a short trade still makes economic sense after stock-borrow fees, collateral rebate, execution costs and recall risk. Built to make the mechanics visible—not to predict markets.</p>
<span class="chip">ACT/360</span><span class="chip">Auditable maths</span><span class="chip">Scenario analysis</span></div>""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Trade setup")
    ticker = st.selectbox("Sample security", ["NOVA", "APEX", "ORBIT", "Custom"])
    defaults = {"NOVA": (42.5, 3.25, 78, 18000, 8), "APEX": (118.0, 0.65, 42, 50000, 2), "ORBIT": (16.8, 12.0, 94, 7000, 22), "Custom": (50.0, 2.0, 60, 20000, 5)}
    d_price, d_fee, d_util, d_locate, d_recall = defaults[ticker]
    shares = st.number_input("Shares to borrow", 100, 1_000_000, 10_000, 100)
    price = st.number_input("Start price (£)", 0.10, 5_000.0, d_price, 0.10)
    holding = st.slider("Holding period (days)", 1, 180, 30)
    st.markdown("### Market & financing")
    move = st.slider("Expected stock move (%)", -30.0, 30.0, -4.0, 0.5, help="Negative is favourable for a short position.")
    fee = st.slider("Annualised borrow fee (%)", 0.0, 30.0, float(d_fee), 0.25)
    rebate = st.slider("Collateral rebate rate (%)", -5.0, 8.0, 1.5, 0.25)
    utilization = st.slider("Utilization (%)", 0, 100, int(d_util))
    locate = st.number_input("Locate availability (shares)", 0, 2_000_000, int(d_locate), 500)
    recall = st.slider("Recall probability (%)", 0.0, 50.0, float(d_recall), 1.0)
    with st.expander("Execution & recall assumptions"):
        cover_cost = st.slider("Cost if recalled (%)", 0.0, 10.0, 1.25, 0.25)
        execution_bps = st.slider("Transaction cost per side (bps)", 0.0, 50.0, 5.0, 1.0)

inputs = TradeInputs(ticker, shares, price, move, holding, fee, rebate, utilization, locate, recall, cover_cost, execution_bps)
r = calculate_trade(inputs)

cols = st.columns(5)
cols[0].metric("Expected net P&L", f"£{r['net_pnl']:,.0f}", f"{r['net_return_pct']:+.2f}% of notional")
cols[1].metric("Borrow cost", f"£{r['borrow_cost']:,.0f}", f"{fee:.2f}% annualised")
cols[2].metric("Break-even decline", f"{r['break_even_move_pct']:.2f}%", "required stock fall")
cols[3].metric("Locate coverage", f"{r['locate_coverage']:.2f}×", str(r["availability"]))
cols[4].metric("Crowding / recall", str(r["risk"]), f"{utilization}% utilized")

tab1, tab2, tab3 = st.tabs(["Trade economics", "Scenario heatmap", "Trader notes"])

with tab1:
    left, right = st.columns([1.35, 1])
    with left:
        st.subheader("Expected P&L through the holding period")
        path = pnl_path(inputs).melt("Day", var_name="Series", value_name="P&L")
        chart = alt.Chart(path).mark_line(strokeWidth=2.5).encode(
            x=alt.X("Day:Q", title="Holding day"), y=alt.Y("P&L:Q", title="P&L (£)"),
            color=alt.Color("Series:N", scale=alt.Scale(domain=["Net expected P&L", "Price P&L"], range=["#2dd4bf", "#6b86a0"])),
            tooltip=["Day:Q", "Series:N", alt.Tooltip("P&L:Q", format=",.0f")]
        ).properties(height=360)
        st.altair_chart(chart, width="stretch")
        st.caption("Illustrative linear price path. The final economics are unchanged; this chart shows how carry accumulates.")
    with right:
        st.subheader("Economics, line by line")
        table = economics_table(inputs).copy()
        st.dataframe(table, hide_index=True, width="stretch",
            column_config={"P&L": st.column_config.NumberColumn(format="£ %.2f")})
    st.markdown(f"""<div class="explain"><b>Plain-English read:</b> Borrowing {shares:,} {ticker} shares creates £{r['notional']:,.0f} of exposure. If the stock moves {move:+.1f}%, the short's price P&L is £{r['price_pnl']:,.0f}. Financing and risk adjustments change that to <b>£{r['net_pnl']:,.0f}</b>. A negative stock move helps the short; a positive move hurts it.</div>""", unsafe_allow_html=True)

with tab2:
    st.subheader("Where does the trade work?")
    price_moves = np.arange(-15, 16, 3)
    fees = np.array([0.5, 1, 2, 4, 8, 12, 16])
    grid = scenario_grid(inputs, price_moves, fees)
    long = grid.rename_axis("fee_pct").reset_index().melt("fee_pct", var_name="move_pct", value_name="net_pnl")
    long["move_pct"] = pd.to_numeric(long["move_pct"])
    heat = alt.Chart(long).mark_rect(cornerRadius=2).encode(
        x=alt.X("move_pct:O", title="Stock price move (%)"), y=alt.Y("fee_pct:O", title="Borrow fee (%)", sort="descending"),
        color=alt.Color("net_pnl:Q", title="Net P&L (£)", scale=alt.Scale(scheme="redblue", domainMid=0)),
        tooltip=[alt.Tooltip("move_pct:O", title="Move %"), alt.Tooltip("fee_pct:O", title="Fee %"), alt.Tooltip("net_pnl:Q", title="Net P&L", format=",.0f")]
    ).properties(height=430)
    text = alt.Chart(long).mark_text(fontSize=11).encode(
        x="move_pct:O", y=alt.Y("fee_pct:O", sort="descending"), text=alt.Text("net_pnl:Q", format=".2s"),
        color=alt.condition("abs(datum.net_pnl) > 10000", alt.value("white"), alt.value("#dce9ee"))
    )
    st.altair_chart(heat + text, width="stretch")
    st.info("Read across to test the stock view; read down to test financing pressure. Red cells lose money, blue cells make money. Hover for exact P&L.")

with tab3:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""#### What a financing trader watches
- **Borrow fee:** the annualized price of sourcing stock; specials can reprice quickly.
- **Rebate:** interest returned on cash collateral. It can be negative for hard-to-borrow names.
- **Utilization:** borrowed inventory divided by lendable supply; high levels signal crowding.
- **Locate:** confirmation that stock is reasonably available before a short sale.
- **Recall:** a lender asks for stock back, potentially forcing an expensive replacement or close-out.
""")
    with c2:
        st.markdown("""#### Questions to ask at the desk
- Is the borrow term firm or subject to daily repricing?
- Does locate inventory cover the order with a sensible buffer?
- What happens to P&L if the stock rallies while the fee widens?
- Is expected recall cost dominated by probability or close-out severity?
- Which assumption is observed, and which is a trader estimate?
""")
    st.warning("Educational model only. It excludes margin requirements, dividends/manufactured payments, corporate actions, tax, settlement fails, intraday marks and fee-path uncertainty.")

with st.expander("Model assumptions & formula audit"):
    st.code("""Price P&L = shares × (start price − end price)
Borrow cost = start notional × annual borrow fee × holding days / 360
Rebate income = start notional × annual rebate rate × holding days / 360
Expected recall cost = notional × recall probability × cover-cost severity
Net expected P&L = price P&L + rebate − borrow − execution − expected recall cost""")
