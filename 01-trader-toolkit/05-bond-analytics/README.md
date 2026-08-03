# Bond Pricing, Yield & Duration

A dependency-free fixed-income calculator for valuing plain fixed-rate bonds and
measuring their sensitivity to interest-rate changes.

## Analytics

- Coupon cash-flow schedule
- Clean price, dirty price and accrued interest
- Current yield
- Yield to maturity solved from market clean price
- Macaulay and modified duration
- Convexity
- DV01: cash price change for a one-basis-point yield move
- Exact rate-shock repricing versus duration-convexity approximation

## Run it

From the repository root:

```bash
python3 01-trader-toolkit/05-bond-analytics/bond_analytics.py
```

For a par bond example, enter face value 100, coupon 5%, maturity 10 years,
semiannual payments, zero accrued fraction and YTM 5%. The clean price should
equal 100.

## Settlement fraction

The settlement fraction is the portion of the current coupon period that has
already elapsed. For example, `0.4` means 40% of the coupon has accrued since
the previous payment date.

## Test it

```bash
cd 01-trader-toolkit/05-bond-analytics
python3 -m unittest -v
```

## Assumptions and limitations

- Cash flows are fixed and paid at a regular frequency.
- Yield is a single nominal discount rate, not a term-structure valuation.
- Day-count conventions are represented by a simplified coupon-period fraction.
- Credit spread, default probability, recovery, callability, tax and liquidity
  are not modelled.
- Duration and convexity are local approximations; exact repricing is preferred
  for large yield moves.

This project is for education and historical analysis, not investment advice.
