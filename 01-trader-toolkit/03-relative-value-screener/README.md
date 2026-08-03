# Credit Relative Value Screener

An explainable Python research workflow for ranking comparable corporate bonds,
identifying issuer-curve dislocations and escalating only the candidates that
survive implementation and risk checks.

The tool is designed to answer a practical question:

> Is this bond genuinely cheap or rich after accounting for its peers, credit
> risk, curve position, trading costs, liquidity and historical behaviour?

## What the screener does

For each bond, the workflow calculates:

1. **Peer relative value** — spread versus the median and spread z-score for the
   narrowest sufficiently populated sector/rating cohort.
2. **Risk-adjusted fair value** — a ridge-stabilised cross-sectional model using
   rating, leverage, duration and maturity, with the residual treated as an
   independent cheap/rich diagnostic.
3. **Issuer-curve dislocation** — observed spread versus a fitted spread curve
   for issuers with at least three bonds.
4. **Rolling standardisation** — the current peer dislocation compared with its
   own history, expressed as a rolling z-score.
5. **Relationship evidence** — historical correlation with the peer spread and
   a walk-forward mean-reversion hit rate.
6. **Implementation economics** — spread pickup, carry/roll after bid-offer
   costs, issue size, trading volume and catalyst alignment.
7. **Downside-aware sizing** — spread DV01, an instrument-specific widening
   shock, portfolio risk budget, issue-size cap and volume cap.

The composite score is transparent. With historical data it uses:

```text
30% peer spread z-score
25% fair-spread residual z-score
20% issuer-curve dislocation z-score
15% rolling dislocation z-score
10% spread-per-leverage z-score
```

Positive values are potentially cheap; negative values are potentially rich.
The score starts the investigation. It does not automatically create a trade.

## Escalation logic

A candidate is labelled `ESCALATE` only when all relevant gates pass:

- the cheap/rich score is material;
- liquidity and bid-offer cost are acceptable;
- historical relationship stability meets the threshold;
- the walk-forward mean-reversion hit rate is at least 50%;
- the supplied catalyst score supports the trade direction; and
- a long candidate retains positive carry after estimated entry cost.

Other securities are labelled `WATCH` or `FILTERED`, making rejected ideas as
visible as accepted ones.

## Run the full demonstration

From the repository root:

```bash
python3 01-trader-toolkit/03-relative-value-screener/relative_value_screener.py \
  --synthetic-history \
  --output relative_value_ranking.csv \
  --decision-pack relative_value_decision_pack.md
```

This prints the ranking and creates:

- `relative_value_ranking.csv` — full diagnostics, gates, risk sizing and final
  decision for every security;
- `relative_value_decision_pack.md` — executive summary, escalated candidates,
  same-issuer switch ideas, implementation rules and model-risk warnings.

The repository also includes a generated
[`sample_relative_value_decision_pack.md`](sample_relative_value_decision_pack.md)
to show the PM-style output.

## Use real market history

The universe CSV requires these core columns:

```text
identifier,issuer,sector,rating,price,yield_percent,spread_bps,
maturity_years,duration,leverage
```

Version 2 also accepts:

```text
spread_type,issue_size_mm,average_daily_volume_mm,bid_offer_bps,
carry_roll_3m_bps,downside_spread_widening_bps,catalyst_score,catalyst
```

Historical observations use a second CSV:

```text
date,identifier,spread_bps
2026-01-05,ATL-28,245
2026-01-12,ATL-28,251
```

Run it with:

```bash
python3 01-trader-toolkit/03-relative-value-screener/relative_value_screener.py \
  your_universe.csv \
  --history your_spread_history.csv \
  --portfolio-nav 10000000 \
  --risk-budget-percent 0.10 \
  --output your_ranking.csv \
  --decision-pack your_decision_pack.md
```

`--synthetic-history` is a deterministic demonstration mode. It must not be
presented as observed market history.

## Same-issuer switches

The switch builder pairs the richest and cheapest bonds from the same issuer,
then reports:

- score gap;
- net spread pickup after both bid-offer costs;
- duration/spread-DV01 hedge ratio; and
- whether both legs pass the implementation filters.

This turns a cross-sectional ranking into a reviewable long/short or bond-switch
idea while keeping the final investment judgement outside the model.

## Test it

```bash
cd 01-trader-toolkit/03-relative-value-screener
python3 -m unittest -v
```

The tests cover peer ranking, issuer-curve fitting, historical diagnostics,
liquidity filters, position sizing, CSV handling, switch construction and
decision-pack generation.

## Honest scope and limitations

- `spread_bps` must contain consistently sourced, **precomputed Z-spreads or
  OAS**. This tool does not derive spreads from bond cash flows.
- It does not contain a full callable-bond option model or default/recovery
  simulation.
- The issuer curve is a simple linear fit and needs enough comparable bonds.
- Downside P&L is a spread-duration approximation, not a full joint credit/rates
  revaluation.
- Liquidity and catalyst inputs are externally supplied and require human
  verification.
- A stable historical relationship can still break after a fundamental event.
- The included universe and demonstration history are synthetic.

This is a research and educational tool, not investment advice.
