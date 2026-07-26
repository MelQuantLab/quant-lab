# MelQuantLab

**Analyze. Model. Alpha.**

MelQuantLab is my growing portfolio of quantitative research, financial-data
analysis and systematic-investing projects. The repository is deliberately
organised as a learning and research journey: foundational programming first,
then market-data analysis, followed by deeper investment research.

## Research philosophy

```text
Observe → Question → Test → Measure → Reflect → Improve
```

Every project must answer the same six questions:

0. **The Why:** Why are we doing this?
1. **What problem am I trying to solve?**
2. **Why does this matter in financial markets?**
3. **How did I test it?**
4. **What did I learn?**
5. **What would I improve next?**
6. **What is the bigger picture?**

This structure keeps the work understandable to humans while preserving the
technical evidence needed for reproducibility.

## Repository roadmap

```text
quant-lab/
├── README.md
├── 01-python-foundations/
├── 02-financial-data/
│   └── moving-average-backtester/
├── 03-quant-research/
├── white-papers/
└── datasets/
```

Folders will be added as completed work becomes ready to publish. Empty
categories are shown here as the intended roadmap rather than being populated
with placeholder projects.

## Published projects

### 02 — Financial Data

- [Project 1: SPY 50/200 Moving-Average Backtester](02-financial-data/moving-average-backtester/)
  — a bias-aware, cost-aware comparison of a simple trend-following rule with
  continuously holding SPY.

## Standards

- Research questions and assumptions are stated before conclusions.
- Signals are implemented without look-ahead bias.
- Transaction costs and limitations are made visible.
- Automated tests protect important calculations.
- Negative results are retained when they are informative.
- Plain-English explanations accompany technical outputs.

The material in this repository is historical research and education, not
investment advice or a claim of future performance.
