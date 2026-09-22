import pandas as pd
def oil_betas(prices,oil="Brent",window=60):
 r=prices.pct_change(); var=r[oil].rolling(window).var(); return pd.DataFrame({c:r[c].rolling(window).cov(r[oil])/var for c in r.columns if c!=oil})
def lead_lag(prices,target,oil="Brent",max_lag=5):
 r=prices[[oil,target]].pct_change().dropna(); return pd.DataFrame([{"lag":lag,"corr":r[oil].shift(lag).corr(r[target])} for lag in range(-max_lag,max_lag+1)])
