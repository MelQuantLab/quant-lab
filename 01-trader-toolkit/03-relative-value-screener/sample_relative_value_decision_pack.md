# Corporate Credit Relative-Value Decision Pack

## Executive summary

- Universe screened: **12 instruments**
- Candidates escalated: **1**
- Same-issuer switches identified: **4**
- Spread inputs are precomputed Z-spreads or OAS; the tool does not derive them from cash flows.

## Escalated candidates

| Instrument | Signal | Score | Peer gap | Curve gap | Rolling z | Stability | OOS hit | Net carry | Notional | Catalyst |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ALB-32 | CHEAP | +0.85 | +15.0bp | +37.1bp | +0.86 | 94% | 50% | +19.0bp | 534,188 | Margin recovery programme |

## Same-issuer switch ideas

| Issuer | Long | Short | Score gap | Net spread pickup | Short notional per 1 long | Implementable |
|---|---|---|---:|---:|---:|---:|
| Borealis Mobile | BOR-34 | BOR-31 | 2.03 | +118.0bp | 1.26x | YES |
| Albion Motors | ALB-32 | ALB-29 | 1.68 | +95.0bp | 1.76x | YES |
| Apex Media | APX-31 | APX-28 | 1.68 | +110.0bp | 1.86x | NO |
| Atlas Telecom | ATL-31 | ATL-28 | 1.60 | +121.0bp | 2.09x | YES |

## Escalation rules

A candidate is escalated only when the cheap/rich score is material, liquidity
passes, the historical relationship is stable, walk-forward mean reversion
clears 50%, the catalyst aligns with the direction and long carry remains
positive after bid-offer costs.

## Downside and model risk

Recommended notionals are capped by a portfolio risk budget, issue size and
trading volume. Downside uses a duration approximation under the
instrument-specific spread-widening shock. The model omits default timing,
recovery uncertainty, jump risk and full scenario covariance.

## Data warning

The included demonstration universe and history are synthetic. Replace them
with consistently sourced market spreads, liquidity measures and documented
catalysts before investment use.
