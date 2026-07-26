# Project 1: Systematic Moving-Average Crossover Backtester

Status: **Python MVP complete and verified**

Next stage: complete user testing of the Excel/VBA dashboard and weekly
PDF/email automation.

> **Can a simple trend-following rule deliver a better return-to-risk outcome
> or reduce losses compared with continuously holding SPY?**

## 0. The Why — in plain English

- Test whether a familiar investment rule actually improves the experience of
  owning the US equity market, rather than accepting the idea on intuition.
- Learn how to turn market data into a transparent, bias-aware and cost-aware
  research result.
- Build a reusable process that connects Python analysis with an Excel
  dashboard and a human-reviewed weekly report.

## 1. What problem am I trying to solve?

SPY is a US-listed exchange-traded fund designed to track the S&P 500. This
project compares two ways of gaining exposure to it:

1. **Buy-and-hold:** remain continuously invested in SPY.
2. **Trend-following strategy:** hold SPY only when its 50-day simple moving
   average (SMA) is above its 200-day SMA; otherwise, hold cash.

The 50-day SMA represents the more recent price trend. The 200-day SMA
represents the longer-term trend. When the faster average rises above the
slower average, the rule treats that as evidence of a positive trend.

The signal calculated at today's close is applied on the next trading day.
This prevents the backtest from using information before it would have been
available. A 5 basis point transaction cost is charged whenever the position
changes.

## 2. Why does this matter in financial markets?

A strategy should not be judged only by whether it makes money. It should be
compared with a realistic alternative and evaluated across return, volatility,
drawdown, transaction costs and time invested.

This project tests whether temporarily moving to cash during negative trends
reduces risk enough to justify missing part of SPY's long-term growth. A
negative result is still useful: it demonstrates that the hypothesis was
tested honestly and prevents a simple, familiar rule from being mistaken for
an investable edge without evidence.

The wider purpose is to create a reusable research workflow:

```text
Data → hypothesis → signal → lagged position → costs → returns → risk → decision
```

The same framework can later support momentum, relative-value, volatility and
credit-market research.

## 3. How did I test it?

- Downloaded adjusted daily SPY prices from Yahoo Finance.
- Calculated 50-day and 200-day simple moving averages.
- Applied each closing-price signal on the following trading day to prevent
  look-ahead bias.
- Charged a 5 basis point cost whenever the position changed.
- Compared strategy and buy-and-hold return, volatility, Sharpe ratio and
  drawdown over the same sample.
- Added automated tests for signal timing, costs, compounding, data validation
  and Yahoo Finance output formats.

## 4. What did I learn?

- The rule was understandable and reduced time invested, but it did not beat
  buy-and-hold on total return or Sharpe ratio in this sample.
- A plausible financial story is not evidence of an investable edge.
- Correct timing, transaction costs and honest benchmark comparison matter as
  much as the trading signal itself.
- A negative result can still improve a research process by eliminating an
  unsupported idea.

## 5. What would I improve next?

- Test parameter sensitivity without selecting a winner retrospectively.
- Add regime analysis and genuine out-of-sample validation.
- Compare more instruments and realistic cash returns.
- Complete user testing of the Excel/VBA weekly reporting workflow.
- Assess more realistic spreads, slippage and execution assumptions.

## 6. What is the bigger picture?

This project is the first complete research pipeline in MelQuantLab:

```text
Question → data → signal → bias control → costs → results → explanation
```

It develops the same habits required in quantitative research and portfolio
management: translating an investment idea into testable rules, challenging
the result and communicating the conclusion clearly enough for another person
to review.

### Who is this for?

The repository is intended for:

- Quantitative research, trading and portfolio-management teams assessing my
  research process.
- Recruiters and hiring managers who want evidence beyond a list of technical
  skills.
- Other learners who want a compact example of a bias-aware backtest.
- My own research library, so assumptions, failures and future improvements
  remain reproducible.

### Where does the data come from?

The demonstration downloads public daily SPY data from Yahoo Finance using the
Python `yfinance` library. With automatic adjustment enabled, the closing-price
series reflects corporate actions such as distributions and stock splits.

The current sample runs from 4 January 2010 through 23 July 2026. Yahoo Finance
is convenient for public learning and reproducibility, but it is not presented
as an institutional-grade source such as Bloomberg. The program can also read
a permitted local CSV containing `Date` and `Close` columns.

### What the project currently does

- Downloads adjusted daily prices or reads a permitted local CSV.
- Calculates configurable short and long SMAs.
- Shifts the signal by one trading day to prevent look-ahead bias.
- Applies configurable transaction costs whenever the position changes.
- Compares net strategy performance with buy-and-hold.
- Reports annualised return, volatility, Sharpe ratio and maximum drawdown.
  Annualised return is suppressed for samples shorter than 60 trading days,
  and samples shorter than one trading year carry an insufficient-history flag.
- Reports entries, exits, exposure and total modelled transaction costs.
- Reports win rate over completed trades only; any position still open at the
  end of the sample is identified separately.
- Exports an Excel-ready time-series CSV and metrics JSON.
- Generates a three-panel price, equity and drawdown chart.
- Tests signal timing, costs, compounding, invalid inputs and both flat and
  MultiIndex Yahoo Finance download formats without making network calls.

### Research design

| Component | Current assumption |
| --- | --- |
| Strategy | Long or cash |
| Signal | Short SMA greater than long SMA |
| Execution timing | Signal calculated at close *t*, position applied on *t+1* |
| Return convention | Adjusted-close percentage return |
| Benchmark | Buy-and-hold in the same instrument |
| Transaction cost | Applied in basis points to absolute position turnover |
| Annualisation | 252 trading days |
| Cash return | Zero, unless represented through the risk-free-rate assumption |

### Reproducible SPY demonstration

A 50/200-day demonstration was run on publicly downloaded adjusted SPY data
from 4 January 2010 through 23 July 2026 with a 5 bp cost per position change.

| Metric | SMA strategy | Buy-and-hold |
| --- | ---: | ---: |
| Total return | 323.24% | 772.77% |
| Annualised return | 9.13% | 14.01% |
| Annualised volatility | 13.97% | 17.10% |
| Sharpe ratio (0% risk-free rate) | 0.70 | 0.85 |
| Maximum drawdown | -33.72% | -33.72% |

The strategy underperformed buy-and-hold in both total return and Sharpe ratio
over this sample. It also spent approximately 79.77% of days invested. This is
a useful negative result: the rule is understandable and reproducible, but the
current evidence does not establish an investable edge.

### Plain-English report

The box at the top explains the purpose of the test, how to read each panel and
the current conclusion. The figures update automatically whenever a new report
is generated.

![SPY 50/200 SMA backtest with a plain-English explanation, equity comparison and drawdown](docs/images/SPY_50_200_overview.png)

These figures are a historical methodology demonstration, not investment
advice, live performance or a claim that the strategy will remain effective.
Results depend on data quality, assumptions, sample period and implementation.

## Installation

Python 3.11 or later is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Run the backtester

Using Yahoo Finance:

```bash
melquant-sma \
  --ticker SPY \
  --start 2010-01-01 \
  --end 2026-07-25 \
  --short-window 50 \
  --long-window 200 \
  --transaction-cost-bps 5 \
  --output-dir reports/spy_50_200
```

Using a CSV containing `Date` and `Close` columns:

```bash
melquant-sma \
  --csv data/raw/prices.csv \
  --short-window 50 \
  --long-window 200 \
  --output-dir reports/local_test
```

Generated reports are intentionally excluded from version control. This avoids
publishing stale data or presenting generated output as source code.

## Run the tests

```bash
pytest
```

## Repository structure

```text
moving-average-backtester/
├── data/raw/                  # Local inputs; contents are not committed
├── docs/images/               # Curated public research figures
├── excel-vba/                 # Dashboard template and automation modules
├── reports/                   # Generated CSV, JSON and PNG outputs
├── src/melquantlab/
│   ├── backtest.py            # Signal, returns, costs and metrics
│   ├── cli.py                 # Command-line workflow
│   ├── data.py                # CSV and Yahoo Finance loaders
│   └── reporting.py           # Excel-ready exports and charts
└── tests/                     # Automated correctness checks
```

## Known limitations and next steps

- Yahoo Finance is convenient public data, not an institutional data source.
- Taxes, bid-ask variation, market impact and execution slippage are simplified.
- Cash returns and dividends are represented only through adjusted prices and
  the configured assumptions.
- The current project tests one instrument and one parameter pair at a time.
- Parameter sensitivity, regime analysis and out-of-sample validation remain
  future extensions and must not be used to select a winner retrospectively.
- The Excel/VBA dashboard and weekly PDF/email workflow require final user
  testing in desktop Excel before being treated as complete.

## Research standard

Every MelQuantLab project should make the hypothesis, data, assumptions,
timing, costs, risks, limitations and rejection condition visible. Failed or
unconvincing results are retained because honest negative evidence is part of
the research process.
