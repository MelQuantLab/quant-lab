# 🛢️ Oil Shock Early Warning — European Auto HY

> **Macro shock → issuer vulnerability → credit repricing → relative value**

A quantitative research project testing whether oil-market regime changes can identify emerging risk in European automotive credit before that risk is fully reflected in market pricing.

## ⚡ Market pulse — 22 September 2026

| Signal | Current observation | Interpretation |
|---|---|---|
| 🟧 Brent | ~$98–100/bbl during the session | Elevated absolute price, but falling |
| 📉 Direction | Two-week low intraday | De-escalating price signal |
| 🚢 Saudi East–West pipeline | Restarted at reduced rate | Improving alternative supply route |
| ⚠️ Strait of Hormuz | Disruption remains material | Physical tail risk remains |
| 🕊️ Diplomacy | Iran signalled conditional reopening could occur within seven days | De-escalation catalyst |

**Research state:** 🟧 **ELEVATED / TRANSITION**

The interesting signal is the disagreement: **oil prices are de-escalating faster than physical/geopolitical risk.** The model is designed to test whether that gap contains useful information for downstream credit.

> Market snapshot is dated rather than presented as a live feed. The application layer will refresh market inputs programmatically.

## 🎯 The question

### Can changes in the oil regime identify vulnerable European HY credits before the full effect is reflected in spreads?

The project does **not** attempt to guess an exact Brent price five days from now. It estimates regime probabilities, tests transmission, measures issuer vulnerability and compares that vulnerability with market-implied stress.

```text
OIL SHOCK
   ↓
REGIME PROBABILITY
   ↓
FX / RATES / DEMAND / INPUT COSTS
   ↓
ISSUER FUNDAMENTALS
   ↓
CREDIT PRICING
   ↓
PRICING GAP
   ↓
RV RESEARCH CANDIDATE
```

## 🔮 Prediction engine

The forecast target is:

**P(oil regime in 5 trading days | information available today)**

Four regimes:

- 🟢 **NORMAL** — ordinary price/volatility conditions
- 🟡 **WATCH** — unusual momentum or volatility developing
- 🟧 **STRESS** — statistically extreme conditions with material transmission risk
- 🔴 **SHOCK** — severe price/volatility dislocation

Initial feature set:

`Brent level` · `1D/5D/20D return` · `realised volatility` · `drawdown` · `moving-average distance` · `curve structure` · `EURUSD` · `GBPUSD`

Event/supply variables are kept separate so the model can distinguish **price de-escalation** from **fundamental-risk de-escalation**.

## 🚗 Credit universe

**Forvia · JLR · Schaeffler · Renault · Gestamp · Volvo Treasury**

For each issuer the framework measures:

🟧 oil sensitivity · 🔵 FX sensitivity · 🟥 leverage · 🟡 margin resilience · 🟢 liquidity · 🟣 market-implied credit stress

## 🚨 Early-warning score

The model separates two things that are often conflated:

### 1. Fundamental / macro vulnerability
How exposed *should* the issuer be to the current shock?

### 2. Market-implied stress
How much of that risk does the market appear to price already?

Then:

**Pricing Gap = Model-implied vulnerability − Market-implied stress**

| Gap | Research interpretation |
|---|---|
| 🟥 Large positive | Investigate hedge / underweight / RV short leg |
| 🟩 Large negative | Investigate long / RV long leg |
| ⬜ Small | Market and model broadly aligned |

A signal creates a **research candidate**, not an automatic trade.

## 🧪 Tests

### Test 01 — Oil ≠ credit?

Do issuers with the highest measured Brent sensitivity subsequently experience the largest credit repricing?

**Status:** 🔬 Running

### Test 02 — Who moves first?

Test the lead/lag chain:

**🟧 Brent → 🔵 FX → 🟢 Equity → 🟣 Credit**

If upstream markets consistently lead credit out of sample, they may have value as an early-warning input.

**Status:** 🔬 Running

### Test 03 — Does regime matter?

Estimate issuer behaviour separately during Normal, Watch, Stress and Shock periods rather than assuming a constant linear oil beta.

**Status:** 🔬 Running

### Test 04 — Is the signal tradeable?

Any apparent relationship must survive:

- out-of-sample testing
- transaction-cost assumptions
- alternative regime definitions
- event-window sensitivity
- false-positive analysis

## 📊 Findings

**No findings are fabricated here.** This section will be populated directly from model output.

| Question | Result | So what? |
|---|---|---|
| Which credits have the largest oil beta? | `RUNNING` | Identifies exposure, not necessarily mispricing |
| Does Brent lead auto credit? | `RUNNING` | Determines whether an early-warning system is justified |
| Does sensitivity change in shock regimes? | `RUNNING` | Tests nonlinear transmission |
| Which issuers show the largest pricing gap? | `RUNNING` | Produces the RV research queue |

Negative findings will remain in the project.

## 🕸️ Vulnerability map

Each issuer will be displayed as a radar profile across:

`Oil` · `FX` · `Leverage` · `Margins` · `Liquidity` · `Pricing Power`

The purpose is explainability: **why should two credits exposed to the same macro shock behave differently?**

## 💥 Scenario engine

### 🟢 De-escalation
Oil risk premium falls → inflation/input-cost pressure eases → credit pressure should decline, all else equal.

### 🟡 Elevated oil
Oil remains structurally expensive → issuer differentiation becomes more important.

### 🔴 Renewed shock
Oil + volatility jump → inflation/FX/demand channels intensify → vulnerable balance sheets should experience greater stress.

The application will allow custom shocks rather than hard-coding these narratives.

## 💰 Relative-value layer

The final question is not:

> **“Should I sell European autos?”**

It is:

> **“Two issuers face the same macro shock. Why does the model imply materially different vulnerability from the risk currently priced by their credit?”**

That disagreement is where deeper research begins.

## 🛠️ Planned implementation

```text
oil-shock-early-warning/
├── README.md
├── app.py
├── requirements.txt
├── src/
│   ├── data.py
│   ├── regimes.py
│   ├── forecast.py
│   ├── transmission.py
│   ├── vulnerability.py
│   └── relative_value.py
├── tests/
└── assets/
```

**Python · pandas · NumPy · SciPy · scikit-learn · Plotly · Streamlit**

## 🔬 Research principles

1. Start with the market question, not the algorithm.
2. Separate narrative from evidence.
3. Use only information available at the forecast date.
4. Make every signal explainable.
5. Retain failed hypotheses.
6. End every analysis with: **So what?**

---

### 🧪 MelQuantLab

**Markets × Data × Code**

**Understand the story. Test the hypothesis. Find the edge.**

*Independent quantitative research and education. Nothing here is investment advice or a claim of future performance.*
