from src.data import load
from src.regimes import features,classify,forecast
from src.transmission import oil_betas,lead_lag
p=load(); x=features(p["Brent"].dropna()); r=classify(x); score,probs=forecast(x,r)
print("Latest Brent",round(float(p["Brent"].dropna().iloc[-1]),2)); print("Current regime",r.dropna().iloc[-1]); print("5-day probabilities",probs); print("Holdout balanced accuracy",round(score,3)); print(oil_betas(p).iloc[-1].sort_values(ascending=False))
for name in ["Forvia","Renault","Schaeffler","Gestamp","Volvo","JLR_parent"]:
 if name in p and p[name].notna().sum()>100:
  z=lead_lag(p,name); print(name,z.iloc[z["corr"].abs().argmax()].to_dict())
