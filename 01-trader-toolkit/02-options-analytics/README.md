# Black-Scholes Options Analytics

A dependency-free Python workstation for European option valuation, Greeks,
implied volatility, scenario analysis and put-call parity.

## Research question

How do spot price, strike, time, interest rates, dividends and volatility combine
to determine a European option's theoretical value and risk sensitivities?

## Modules

- Black-Scholes-Merton pricing for European calls and puts
- Delta, gamma, vega, daily theta and rho
- Intrinsic and time-value decomposition
- Implied volatility solved by bisection with convergence evidence
- No-arbitrage price-bound validation
- Spot/volatility scenario grid
- Put-call parity diagnostic

## Run it

From the repository root:

```bash
python3 01-trader-toolkit/02-options-analytics/options_analytics.py
```

For the standard reference case—spot 100, strike 100, one year, 5% risk-free
rate, 20% volatility and no dividends—the model returns:

```text
European call: 10.4506
European put:   5.5735
Call delta:     0.6368
Call gamma:     0.0188
Call vega:      0.3752 per volatility point
```

## Test it

```bash
cd 01-trader-toolkit/02-options-analytics
python3 -m unittest -v
```

The numerical tests use published textbook reference values and also verify
put-call parity, implied-volatility recovery, arbitrage bounds, Greek behaviour,
scenario grids and invalid-input handling.

## Model assumptions

- The option is European and exercisable only at expiry.
- The underlying follows lognormal diffusion with constant volatility.
- Interest rates and continuous dividend yield are constant.
- Markets are frictionless and continuous; there are no transaction costs,
  liquidity constraints or discrete price jumps.
- Delta hedging can be performed continuously.

These assumptions make the model analytically useful but imperfect for observed
markets. Volatility smiles, jumps, early exercise and discrete dividends require
more advanced models.

This project is for education and historical analysis, not investment advice.
