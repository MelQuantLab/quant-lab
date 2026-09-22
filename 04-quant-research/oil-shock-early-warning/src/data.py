import yfinance as yf
TICKERS={"Brent":"BZ=F","EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","Forvia":"FRVIA.PA","Renault":"RNO.PA","Schaeffler":"SHA0.DE","Gestamp":"GEST.MC","Volvo":"VOLV-B.ST","JLR_parent":"TTM"}
def load(start="2015-01-01"):
 raw=yf.download(list(TICKERS.values()),start=start,auto_adjust=True,progress=False,group_by="column")
 return raw["Close"].rename(columns={v:k for k,v in TICKERS.items()}).dropna(how="all")
