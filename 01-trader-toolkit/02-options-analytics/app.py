"""Interactive MelQuantLabs Black-Scholes scenario dashboard."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from database import recent_calculations, save_calculation
from options_analytics import price_pair, scenario_surface


APP_DIR = Path(__file__).resolve().parent
DATABASE_PATH = APP_DIR / "data" / "options_analytics.db"

st.set_page_config(
    page_title="MelQuantLabs | Options Lab",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """
    <style>
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #101f34, #0b1728);
        border: 1px solid #223752; border-radius: 12px; padding: 16px;
    }
    [data-testid="stMetricLabel"], [data-testid="stMetricValue"] {
        color: #eef4ff;
    }
    .eyebrow { color: #42d3b2; font-weight: 700; letter-spacing: .12em; }
    .subtle { color: #9cafc7; }
    </style>
    """,
    unsafe_allow_html=True,
)


def heatmap(frame: pd.DataFrame, value_column: str, title: str, pnl: bool) -> go.Figure:
    """Build an annotated scenario heatmap."""
    matrix = frame.pivot(index="Volatility", columns="Stock price", values=value_column)
    kwargs: dict[str, object] = {"colorscale": "RdYlGn" if pnl else "Viridis"}
    if pnl:
        bound = max(abs(float(matrix.min().min())), abs(float(matrix.max().max())), 0.01)
        kwargs.update(zmin=-bound, zmax=bound, zmid=0)
    figure = go.Figure(
        go.Heatmap(
            z=matrix.values,
            x=[f"{value:,.2f}" for value in matrix.columns],
            y=[f"{value:.1%}" for value in matrix.index],
            text=np.vectorize(lambda value: f"{value:+.2f}" if pnl else f"{value:.2f}")(
                matrix.values
            ),
            texttemplate="%{text}",
            hovertemplate="Spot: %{x}<br>Volatility: %{y}<br>Value: %{z:.4f}<extra></extra>",
            colorbar={"title": "P&L" if pnl else "Value"},
            **kwargs,
        )
    )
    figure.update_layout(
        title=title,
        xaxis_title="Shocked stock price",
        yaxis_title="Shocked volatility",
        height=470,
        margin={"l": 25, "r": 25, "t": 60, "b": 40},
        paper_bgcolor="#07111f",
        plot_bgcolor="#07111f",
        font={"color": "#dce8f8"},
    )
    return figure


def money(value: float) -> str:
    """Format signed currency with the sign before the currency symbol."""
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"


st.markdown('<div class="eyebrow">MELQUANTLABS · OPTIONS ANALYTICS</div>', unsafe_allow_html=True)
st.title("Black–Scholes Scenario Lab")
st.markdown(
    '<div class="subtle">Translate market assumptions into fair value, mark-to-model P&L, '
    "and an auditable scenario surface.</div>",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Contract & market")
    stock_price = st.number_input("Stock price", min_value=0.01, value=100.0, step=1.0)
    strike_price = st.number_input("Strike price", min_value=0.01, value=100.0, step=1.0)
    volatility_percent = st.number_input("Volatility (%)", min_value=0.01, value=20.0, step=1.0)
    time_to_expiry = st.number_input(
        "Time to expiry (years)", min_value=0.001, value=1.0, step=0.1, format="%.3f"
    )
    risk_free_percent = st.number_input("Risk-free rate (%)", value=5.0, step=0.25)
    st.header("Position cost")
    call_purchase_price = st.number_input(
        "Call purchase price", min_value=0.0, value=8.0, step=0.5
    )
    put_purchase_price = st.number_input(
        "Put purchase price", min_value=0.0, value=7.0, step=0.5
    )
    st.header("Scenario range")
    spot_range_percent = st.slider("Stock price range (±%)", 5, 50, 20, 5)
    vol_range_points = st.slider("Volatility range (± points)", 2, 30, 10, 1)
    grid_size = st.select_slider("Grid resolution", options=[5, 7, 9, 11], value=9)

volatility = volatility_percent / 100
risk_free_rate = risk_free_percent / 100
valuation = price_pair(
    spot=stock_price,
    strike=strike_price,
    volatility=volatility,
    time_to_expiry=time_to_expiry,
    risk_free_rate=risk_free_rate,
    call_purchase_price=call_purchase_price,
    put_purchase_price=put_purchase_price,
)

spot_axis = np.linspace(
    stock_price * (1 - spot_range_percent / 100),
    stock_price * (1 + spot_range_percent / 100),
    grid_size,
).tolist()
minimum_vol = max(0.001, volatility - vol_range_points / 100)
volatility_axis = np.linspace(
    minimum_vol, volatility + vol_range_points / 100, grid_size
).tolist()
surface = scenario_surface(
    spot_prices=spot_axis,
    volatilities=volatility_axis,
    strike=strike_price,
    time_to_expiry=time_to_expiry,
    risk_free_rate=risk_free_rate,
    call_purchase_price=call_purchase_price,
    put_purchase_price=put_purchase_price,
)
frame = pd.DataFrame(
    {
        "Stock price": [point.shocked_spot for point in surface],
        "Volatility": [point.shocked_volatility for point in surface],
        "Call value": [point.call_value for point in surface],
        "Put value": [point.put_value for point in surface],
        "Call P&L": [point.call_pnl for point in surface],
        "Put P&L": [point.put_pnl for point in surface],
    }
)

call_value, put_value, call_pnl, put_pnl = st.columns(4)
call_value.metric("Call fair value", money(valuation.call_value))
put_value.metric("Put fair value", money(valuation.put_value))
call_pnl.metric(f"Call P&L vs {money(call_purchase_price)} cost", money(valuation.call_pnl))
put_pnl.metric(f"Put P&L vs {money(put_purchase_price)} cost", money(valuation.put_pnl))

view = st.radio("Heatmap measure", ["Position P&L", "Model value"], horizontal=True)
left, right = st.columns(2)
if view == "Position P&L":
    left.plotly_chart(heatmap(frame, "Call P&L", "Call mark-to-model P&L", True), width="stretch")
    right.plotly_chart(heatmap(frame, "Put P&L", "Put mark-to-model P&L", True), width="stretch")
    st.caption("Green indicates positive P&L; red indicates negative P&L. Values are per option unit.")
else:
    left.plotly_chart(heatmap(frame, "Call value", "Call model value", False), width="stretch")
    right.plotly_chart(heatmap(frame, "Put value", "Put model value", False), width="stretch")

save_column, note_column = st.columns([1, 3])
if save_column.button("Save calculation run", type="primary", width="stretch"):
    calculation_id = save_calculation(
        DATABASE_PATH,
        stock_price=stock_price,
        strike_price=strike_price,
        volatility=volatility,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        call_purchase_price=call_purchase_price,
        put_purchase_price=put_purchase_price,
        surface=surface,
    )
    st.success(f"Saved calculation #{calculation_id} with {len(surface)} linked scenarios.")
note_column.caption(
    "Saving stores one base-input record and every shocked output in the local SQLite database."
)

with st.expander("Recent saved runs"):
    history = [dict(row) for row in recent_calculations(DATABASE_PATH)]
    if history:
        st.dataframe(pd.DataFrame(history), hide_index=True, width="stretch")
    else:
        st.info("No saved calculations yet.")

st.caption("European options · no dividends · educational analytics, not investment advice")
