# Credit Relative Value Screener

An explainable Python screener that compares corporate bonds or loans with
relevant peers and ranks them from cheapest to richest.

## The why

A wider spread is not automatically cheap. It may compensate investors for a
weaker rating, higher leverage or greater duration. This tool asks a more useful
question:

> Is this instrument's spread unusually wide or tight after considering its
> peer group and observable risk characteristics?

## Methodology

Each instrument receives four diagnostics:

1. **Spread versus peer median** — the instrument's spread minus the median for
   the narrowest sufficiently populated sector/rating cohort.
2. **Peer spread z-score** — how unusual the spread is within that peer group.
3. **Model residual** — observed spread minus a ridge-stabilised fair-spread
   estimate using rating, leverage, duration and maturity.
4. **Spread per turn of leverage** — compensation received for each unit of
   reported leverage.

The composite score is deliberately transparent:

```text
50% peer spread z-score
35% fair-spread residual z-score
15% spread-per-leverage z-score
```

Positive scores indicate potentially cheaper securities; negative scores
indicate potentially richer securities. This is a screening signal, not a trade
recommendation.

## Run the sample universe

From the repository root:

```bash
python3 01-trader-toolkit/03-relative-value-screener/relative_value_screener.py
```

The ranked results appear in the terminal and are exported to
`relative_value_ranking.csv`.

## Screen another CSV

```bash
python3 01-trader-toolkit/03-relative-value-screener/relative_value_screener.py your_data.csv --output your_ranking.csv
```

Required columns:

```text
identifier, issuer, sector, rating, price, yield_percent, spread_bps,
maturity_years, duration, leverage
```

The included sample data is synthetic and exists only to demonstrate the
workflow.

## Test it

```bash
cd 01-trader-toolkit/03-relative-value-screener
python3 -m unittest -v
```

## Limitations

- Reported spread and leverage measures must be comparable across instruments.
- Ratings are simplified into broad buckets and may lag fundamental changes.
- The regression is cross-sectional and intentionally small; it is not a full
  credit-pricing model.
- Liquidity, issue size, seniority, covenants, recovery, event risk and curve
  shape are not yet modelled.
- A cheap signal may reflect genuine deterioration that is absent from the
  supplied data.

This project is for education and historical analysis, not investment advice.
