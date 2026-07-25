"""Moving-average crossover backtest engine."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class BacktestConfig:
    """Inputs that define one moving-average crossover test."""

    short_window: int = 50
    long_window: int = 200
    transaction_cost_bps: float = 5.0
    annual_risk_free_rate: float = 0.0

    def __post_init__(self) -> None:
        if self.short_window < 1:
            raise ValueError("short_window must be at least 1")
        if self.long_window <= self.short_window:
            raise ValueError("long_window must be greater than short_window")
        if self.transaction_cost_bps < 0:
            raise ValueError("transaction_cost_bps cannot be negative")
        if self.annual_risk_free_rate <= -1:
            raise ValueError("annual_risk_free_rate must be greater than -1")


@dataclass(frozen=True)
class BacktestResult:
    """Time series and summary statistics produced by a backtest."""

    frame: pd.DataFrame
    metrics: dict[str, float | int | str]
    config: BacktestConfig


def _validate_prices(prices: pd.Series) -> pd.Series:
    if not isinstance(prices, pd.Series):
        raise TypeError("prices must be a pandas Series")
    if prices.empty:
        raise ValueError("prices cannot be empty")
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise TypeError("prices must use a DatetimeIndex")

    clean = pd.to_numeric(prices, errors="coerce").dropna().sort_index()
    clean = clean[~clean.index.duplicated(keep="last")]
    if clean.empty:
        raise ValueError("prices contain no valid numeric observations")
    if (clean <= 0).any():
        raise ValueError("prices must be strictly positive")
    return clean.astype(float).rename("price")


def _annualised_return(returns: pd.Series) -> float:
    returns = returns.dropna()
    if returns.empty:
        return 0.0
    growth = float((1.0 + returns).prod())
    if growth <= 0:
        return -1.0
    return growth ** (TRADING_DAYS_PER_YEAR / len(returns)) - 1.0


def _annualised_volatility(returns: pd.Series) -> float:
    returns = returns.dropna()
    if len(returns) < 2:
        return 0.0
    return float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def _sharpe_ratio(returns: pd.Series, annual_risk_free_rate: float) -> float:
    returns = returns.dropna()
    if len(returns) < 2:
        return 0.0
    daily_risk_free = (1.0 + annual_risk_free_rate) ** (
        1.0 / TRADING_DAYS_PER_YEAR
    ) - 1.0
    excess = returns - daily_risk_free
    volatility = excess.std(ddof=1)
    if np.isclose(volatility, 0.0):
        return 0.0
    return float(excess.mean() / volatility * np.sqrt(TRADING_DAYS_PER_YEAR))


def _max_drawdown(equity: pd.Series) -> float:
    drawdown = equity / equity.cummax() - 1.0
    return float(drawdown.min())


def _closed_trade_returns(frame: pd.DataFrame) -> list[float]:
    """Return compounded net returns for completed long trades."""

    completed: list[float] = []
    active_returns: list[float] | None = None

    for position, previous_position, net_return in zip(
        frame["position"],
        frame["position"].shift(1).fillna(0.0),
        frame["strategy_return"],
        strict=True,
    ):
        if position == 1 and previous_position == 0:
            active_returns = [float(net_return)]
        elif position == 1 and active_returns is not None:
            active_returns.append(float(net_return))
        elif position == 0 and previous_position == 1 and active_returns is not None:
            # The exit-day net return contains the exit transaction cost.
            active_returns.append(float(net_return))
            completed.append(float(np.prod(1.0 + np.array(active_returns)) - 1.0))
            active_returns = None

    return completed


def run_backtest(
    prices: pd.Series,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Run a long-or-cash SMA crossover backtest.

    The raw signal is shifted by one trading day before it becomes a position.
    This prevents today's closing-price signal from earning today's return.
    """

    config = config or BacktestConfig()
    clean_prices = _validate_prices(prices)
    if len(clean_prices) < config.long_window + 2:
        raise ValueError(
            "not enough observations: at least long_window + 2 prices are required"
        )

    frame = clean_prices.to_frame()
    frame["short_sma"] = frame["price"].rolling(config.short_window).mean()
    frame["long_sma"] = frame["price"].rolling(config.long_window).mean()
    frame["signal"] = (
        frame["short_sma"].gt(frame["long_sma"])
        & frame["long_sma"].notna()
    ).astype(float)

    # Anti-look-ahead rule: a signal calculated at close t is held from t+1.
    frame["position"] = frame["signal"].shift(1).fillna(0.0)
    frame["benchmark_return"] = frame["price"].pct_change().fillna(0.0)
    frame["turnover"] = frame["position"].diff().abs().fillna(
        frame["position"].abs()
    )
    cost_rate = config.transaction_cost_bps / 10_000.0
    frame["transaction_cost"] = frame["turnover"] * cost_rate
    frame["gross_strategy_return"] = (
        frame["position"] * frame["benchmark_return"]
    )
    frame["strategy_return"] = (
        frame["gross_strategy_return"] - frame["transaction_cost"]
    )
    frame["benchmark_equity"] = (1.0 + frame["benchmark_return"]).cumprod()
    frame["strategy_equity"] = (1.0 + frame["strategy_return"]).cumprod()
    frame["drawdown"] = (
        frame["strategy_equity"] / frame["strategy_equity"].cummax() - 1.0
    )

    strategy = frame["strategy_return"]
    benchmark = frame["benchmark_return"]
    entries = int(((frame["position"] == 1) & (frame["position"].shift(1) == 0)).sum())
    exits = int(((frame["position"] == 0) & (frame["position"].shift(1) == 1)).sum())
    closed_trade_returns = _closed_trade_returns(frame)
    winning_trades = sum(trade_return > 0 for trade_return in closed_trade_returns)
    win_rate = (
        winning_trades / len(closed_trade_returns) if closed_trade_returns else 0.0
    )
    average_trade_return = (
        float(np.mean(closed_trade_returns)) if closed_trade_returns else 0.0
    )

    metrics: dict[str, float | int | str] = {
        "start_date": frame.index.min().date().isoformat(),
        "end_date": frame.index.max().date().isoformat(),
        "observations": int(len(frame)),
        "short_window": config.short_window,
        "long_window": config.long_window,
        "transaction_cost_bps": config.transaction_cost_bps,
        "strategy_total_return": float(frame["strategy_equity"].iloc[-1] - 1.0),
        "benchmark_total_return": float(frame["benchmark_equity"].iloc[-1] - 1.0),
        "strategy_annualised_return": _annualised_return(strategy),
        "benchmark_annualised_return": _annualised_return(benchmark),
        "strategy_annualised_volatility": _annualised_volatility(strategy),
        "benchmark_annualised_volatility": _annualised_volatility(benchmark),
        "strategy_sharpe_ratio": _sharpe_ratio(
            strategy, config.annual_risk_free_rate
        ),
        "benchmark_sharpe_ratio": _sharpe_ratio(
            benchmark, config.annual_risk_free_rate
        ),
        "maximum_drawdown": _max_drawdown(frame["strategy_equity"]),
        "benchmark_maximum_drawdown": _max_drawdown(frame["benchmark_equity"]),
        "entries": entries,
        "exits": exits,
        "closed_trades": len(closed_trade_returns),
        "open_trade": int(entries > exits),
        "win_rate": win_rate,
        "average_closed_trade_return": average_trade_return,
        "total_transaction_cost": float(frame["transaction_cost"].sum()),
        "exposure": float(frame["position"].mean()),
    }
    return BacktestResult(frame=frame, metrics=metrics, config=config)
