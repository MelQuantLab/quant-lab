import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import balanced_accuracy_score
REGIMES=["NORMAL","WATCH","STRESS","SHOCK"]
def features(close):
 r=close.pct_change(); x=pd.DataFrame(index=close.index); x["ret_1d"]=r; x["ret_5d"]=close.pct_change(5); x["ret_20d"]=close.pct_change(20); x["rv_20d"]=r.rolling(20).std()*np.sqrt(252); x["ma_gap_20d"]=close/close.rolling(20).mean()-1; x["drawdown_60d"]=close/close.rolling(60).max()-1; return x
def classify(x):
 vol=x["rv_20d"].expanding(252).rank(pct=True); move=x["ret_5d"].abs().expanding(252).rank(pct=True); score=pd.concat([vol,move],axis=1).max(axis=1); return pd.cut(score,[-np.inf,.70,.85,.95,np.inf],labels=REGIMES).astype("object")
def forecast(x,regime,horizon=5):
 y=regime.shift(-horizon); d=x.join(y.rename("target")).dropna(); split=int(len(d)*.75); tr,te=d.iloc[:split],d.iloc[split:]; m=RandomForestClassifier(n_estimators=500,min_samples_leaf=10,class_weight="balanced",random_state=42); m.fit(tr[x.columns],tr["target"]); score=balanced_accuracy_score(te["target"],m.predict(te[x.columns])); p=dict(zip(m.classes_,m.predict_proba(x.dropna().iloc[[-1]])[0])); return score,{r:float(p.get(r,0)) for r in REGIMES}
