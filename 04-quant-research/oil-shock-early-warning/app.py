import streamlit as st
import plotly.express as px
from src.data import load
from src.regimes import features,classify,forecast
from src.transmission import oil_betas
st.set_page_config(page_title="Oil Shock Early Warning",layout="wide"); st.title("🛢️ Oil Shock Early Warning"); st.caption("European Auto HY · Macro → Fundamentals → Credit")
p=load(); b=p["Brent"].dropna(); x=features(b); r=classify(x); score,probs=forecast(x,r)
a,c,d=st.columns(3); a.metric("Brent",f"${b.iloc[-1]:.2f}"); c.metric("Current regime",r.dropna().iloc[-1]); d.metric("Holdout balanced accuracy",f"{score:.1%}")
st.plotly_chart(px.line(b,title="Brent history"),use_container_width=True); st.plotly_chart(px.bar(x=list(probs),y=list(probs.values()),labels={"x":"5-day regime","y":"Probability"}),use_container_width=True)
beta=oil_betas(p).iloc[-1].dropna().sort_values(); st.subheader("60-day oil beta"); st.plotly_chart(px.bar(x=beta.values,y=beta.index,orientation="h"),use_container_width=True); st.info("Public equity betas are transmission proxies; single-name bond/CDS spreads plug into the credit-pricing layer separately.")
