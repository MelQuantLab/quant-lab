# Systematic Credit Momentum & Portfolio Construction

Status: **Research implementation complete; historical results reproduced.**

**May 2008–December 2025: Sharpe versus SHY 0.70 versus HYG buy-and-hold 0.39.**
Annualised return was **4.23% versus 5.14%**; month-end maximum drawdown was
**−7.31% versus −29.92%**. The strategy reduced risk and sacrificed return.
In 2016–2025 its Sharpe was **0.37 versus HYG 0.54**, so the evidence does not
support a persistent advantage across periods.

> Can a fixed credit momentum rule improve portfolio resilience after costs,
> compared with passive credit exposure?

![Credit momentum, benchmarks, drawdown and portfolio allocations](docs/credit_momentum.png)

## 0. The Why

Connect systematic signal research with a PM decision: when should credit risk
be owned, how should it be sized, and what happens when both credit sleeves weaken?
Make the allocation, cost and benchmark evidence inspectable rather than merely
showing a trading signal.

## 1. What problem am I trying to solve?

Credit funds combine spread, carry and interest-rate risk. This project tests
a transparent long-only allocation between HYG (US high-yield credit), LQD
(US investment-grade credit) and SHY (short Treasury bonds).

This is **ETF total-return momentum**, not issuer-level spread momentum or a
duration-neutral credit strategy. SHY is a defensive Treasury proxy, not cash
or a risk-free instrument. Results are in USD without a GBP currency hedge.

## 2. Why does this matter in financial markets?

A credit portfolio can lose money from widening spreads, rising rates and
liquidity shocks. A PM needs to judge return alongside concentration, drawdown,
turnover and the opportunity cost of defensive allocations. Momentum may avoid
some prolonged losses but can react too slowly to a sudden crash or recovery.

## 3. How did I test it?

| Component | Fixed baseline |
| --- | --- |
| Universe | HYG, LQD, SHY; chosen retrospectively, no changing universe |
| Data | Yahoo Finance adjusted daily closes, distributions/splits included |
| Observation | Last available trading close each calendar month |
| Signal | Credit ETF trailing 6-month return must exceed SHY's 6-month return |
| Sizing | Inverse trailing 12-month monthly volatility among eligible credit ETFs |
| Constraint | Each credit ETF capped at 60%; residual allocated to SHY |
| Timing | Month-end signal sets the following month's holdings |
| Execution | Idealised month-end closing rebalance; next-session open/slippage not modelled |
| Cost | 10 bp per dollar bought or sold, including SHY; 100% switch incurs 20 bp |
| Rebalancing | Monthly, turnover measured against weights drifted by asset returns |
| Benchmark 1 | HYG purchased once; same initial trading cost; no forced final liquidation |
| Benchmark 2 | 50/50 HYG/LQD, monthly rebalanced with the same turnover/cost model |
| Sharpe | Monthly return minus realised SHY return, annualised with √12 |
| Drawdown | Month-end equity including initial capital of 1; intramonth losses not measured |

The aligned daily sample starts 11 April 2007. After 12 months of return history,
April 2008's signal sets May's allocation. Evaluation comprises **212 monthly
returns**, starting with the return from 30 April to 30 May 2008 and ending
31 December 2025. HYG launched in April 2007, so a 2005 start would require
a different dataset; earlier prices have not been fabricated or backfilled.

The rule and constraints are fixed for this implementation. This is a
retrospective study, **not a preregistered or untouched out-of-sample test**.
The split below checks period dependence; parameters are not tuned separately.

### Full-sample results after modelled trading costs

| Metric | Credit momentum | 50/50 credit blend | HYG buy-and-hold |
| --- | ---: | ---: | ---: |
| Annualised return | 4.23% | 4.70% | 5.14% |
| Annualised volatility | 4.21% | 8.72% | 10.43% |
| Sharpe versus SHY | 0.70 | 0.41 | 0.39 |
| Month-end maximum drawdown | −7.31% | −21.42% | −29.92% |
| Total return | 108.05% | 125.18% | 142.31% |

Average credit allocation was **68.08%**. Annualised two-sided turnover was
**3.67× NAV**, approximately 36.7 bp/year of additive modelled cost before
compounding. This is not a live audited track record.

### Period dependence

| Period | Momentum CAGR | HYG CAGR | Momentum Sharpe | HYG Sharpe |
| --- | ---: | ---: | ---: | ---: |
| May 2008–December 2015 | 5.91% | 4.76% | 1.06 | 0.31 |
| January 2016–December 2025 | 2.97% | 5.43% | 0.37 | 0.54 |

Period metrics use realised monthly returns from the continuous backtest;
the portfolios are not restarted or charged a new entry cost at the split.

[Machine-readable metrics](docs/metrics.json),
[monthly holdings, turnover and returns](docs/monthly_allocations.csv),
[3/6/12-month momentum × 0/10/25 bp sensitivity](docs/sensitivity.csv), and
[retrieval details and input checksum](docs/data_manifest.json) accompany the report.
Sensitivity is published in full; it is not used to replace the six-month baseline.
At 10 bp, three-month momentum has a Sharpe of **0.37** and twelve-month momentum
**0.51**. Raising baseline costs to 25 bp reduces its Sharpe to **0.55**.
The result depends materially on the lookback and trading assumptions.

## 4. What did I learn?

The full-sample result supports a historical risk-control benefit, with a
substantial return trade-off. The later-period Sharpe reversal challenges a
claim of stable superiority. A 50/50 blend also underperformed momentum on
full-sample Sharpe, but lower credit exposure itself can explain some risk
reduction. No regression or exposure-matched test establishes incremental alpha.

## 5. What would I improve next?

- Test with licensed credit-index total returns, spread duration and rate hedges
  to distinguish spread momentum from duration and carry.
- Add exposure-matched benchmarks, daily portfolio valuation and crash/recovery
  analysis; month-end drawdowns can conceal substantial intramonth losses.
- Validate next-session execution and crisis bid-offer costs, fund premiums/
  discounts, capacity and realistic Treasury trading costs.
- Freeze this version for prospective paper monitoring before making stronger
  claims. Selected ETFs introduce survivorship and universe-selection limitations.

## 6. What is the bigger picture?

The completed project connects hypothesis, signal, allocation, risk, costs and
an explicit PM conclusion: **a candidate defensive credit allocation process,
with insufficient evidence of persistent alpha**. Reject a persistent-superiority
claim when later-period Sharpe fails to exceed passive credit, as it does here.

## Reproduce

Python 3.11+:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python download_data.py
python credit_momentum.py --csv data/raw/adjusted_prices.csv --output-dir reports/baseline
python build_report.py
pytest -q tests
```

Raw downloads stay local and are excluded from Git. The committed `docs/` files
are a curated result snapshot. Data revisions can change the last decimals;
the manifest identifies the original download, and `environment.txt` records
the run's package versions. The downloader requires network access; the engine,
report builder and tests work offline with the local input.

Tests cover lagged holdings, future-data perturbation, allocation conservation,
caps, cash fallback, cost compounding, drift-aware turnover, initial-capital
drawdown, and rejection of missing/duplicate data or missing calendar months.

### Data sources

- [HYG fund details and inception](https://www.blackrock.com/us/financial-professionals/products/239565/)
- [iShares ETF universe and fund descriptions](https://www.ishares.com/us/products/etf-investments)
- [SHY: short Treasury bond exposure](https://www.ishares.com/us/products/239452/ishares-132024-treasury-bond-etf)
- [Yahoo Finance HYG historical data](https://finance.yahoo.com/quote/HYG/history/)

Public-data research and education, not a claim of future performance.
