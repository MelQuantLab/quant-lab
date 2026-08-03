# Trade & Risk Analytics Calculator

A tested command-line risk workstation for analysing completed trades,
sizing new positions, measuring strategy edge and checking portfolio risk.

## The why

P&L alone does not tell a trader whether a decision was well-sized, efficiently
executed or supported by a repeatable edge. This project connects four stages
of the decision process:

```text
Strategy edge → Position sizing → Portfolio risk check → P&L attribution
```

## Analytics modules

### 1. Execution and P&L attribution

- Long and short gross P&L
- Fees, slippage and fixed commissions
- Gross and net returns
- Price movement and execution-cost drag in basis points

### 2. Risk-based position sizing

- Account-level risk budget
- Stop-loss risk per unit
- Risk-limited recommended quantity
- Maximum notional cap
- Loss at stop and profit at target
- Risk/reward and implied break-even win rate

### 3. Strategy edge

- Probability-weighted expected value per trade
- Expectancy measured in R
- Profit factor
- Actual win-rate edge over break-even
- Full- and half-Kelly sizing estimates

### 4. Portfolio pre-trade check

- Gross exposure after the proposed trade
- Total open risk as cash and percentage of account value
- Pass/breach decision against an open-risk limit
- Remaining risk capacity

## Run it

From the repository root:

```bash
python3 01-trader-toolkit/01-trade-calculator/trade_calculator.py
```

## Position-sizing example

For a £50,000 account, 1% trade-risk budget, entry at £100, stop at £95 and
target at £115:

```text
Recommended quantity: 100
Position notional:     10,000.00 (20.00%)
Maximum loss at stop:     500.00
Profit at target:       1,500.00
Risk/reward:               1:3.00
Break-even win rate:       25.00%
```

## Test it

```bash
cd 01-trader-toolkit/01-trade-calculator
python3 -m unittest -v
```

The test suite covers long and short attribution, trading costs, position-size
constraints, invalid trade structures, expectancy, profit factor, Kelly sizing
and portfolio risk-limit decisions.

## Assumptions and limitations

- P&L uses price multiplied by quantity and excludes FX translation and tax.
- Fee and slippage estimates apply to both entry and exit notional.
- Position sizing assumes execution at the stated entry and stop prices.
- Portfolio open risk is the sum of stated stop losses; correlations and gap
  risk are not modelled.
- Kelly estimates are highly sensitive to historical inputs and are displayed
  for analysis, not as a recommendation.
- Past trade statistics do not guarantee future performance.

This project is for education and historical analysis, not investment advice.
