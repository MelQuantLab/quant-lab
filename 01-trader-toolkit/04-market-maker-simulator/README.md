# Market Maker Simulator

An interactive trading game that teaches two-sided quoting, spread capture,
inventory management and adverse selection.

## The objective

Quote competitive bid and ask prices around a changing fair value. Client orders
may generate spread revenue, but some clients are informed and trade immediately
before the fair value moves against the market maker.

Your score rewards marked-to-market P&L and penalises excessive inventory and
risk-limit breaches.

## Market mechanics

- Tighter quotes increase the probability of receiving a client trade.
- A client buy hits the ask and leaves the market maker short.
- A client sell hits the bid and leaves the market maker long.
- Informed flow moves fair value against the resulting dealer position.
- Inventory-aware quotes shift the midpoint to encourage risk-reducing flow.
- Every round marks cash and inventory to the updated fair value.

## Play interactively

From the repository root:

```bash
python3 01-trader-toolkit/04-market-maker-simulator/market_maker_simulator.py
```

Press Return at the bid or ask prompt to accept the model's suggested quote, or
enter your own prices.

## Watch the model play

```bash
python3 01-trader-toolkit/04-market-maker-simulator/market_maker_simulator.py --auto --rounds 20 --seed 42
```

The seed makes the simulated order flow reproducible for comparison.

## Test it

```bash
cd 01-trader-toolkit/04-market-maker-simulator
python3 -m unittest -v
```

## Limitations

- The fair-value process and order flow are deliberately simplified.
- The simulator has one asset, fixed trade size and no exchange queue position.
- Hedging, latency, rebates, fees and multi-level order books are excluded.
- Marked P&L is a training score, not evidence of a deployable strategy.

This project is for education and simulation, not investment advice.
