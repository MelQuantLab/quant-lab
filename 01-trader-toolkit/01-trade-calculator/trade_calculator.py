"""Trade, position-sizing and strategy analytics for discretionary traders."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Callable, Literal


Side = Literal["long", "short"]


@dataclass(frozen=True)
class TradeResult:
    """Performance attribution for one completed trade."""

    side: Side
    entry_price: float
    exit_price: float
    quantity: float
    entry_notional: float
    gross_pnl: float
    trading_costs: float
    net_pnl: float
    gross_return_percent: float
    net_return_percent: float
    price_move_bps: float
    cost_drag_bps: float

    @property
    def transaction_costs(self) -> float:
        """Backwards-compatible name used by the first project version."""
        return self.trading_costs

    @property
    def return_percent(self) -> float:
        """Backwards-compatible alias for net return."""
        return self.net_return_percent


@dataclass(frozen=True)
class PositionPlan:
    """Risk-budgeted position size and payoff profile."""

    side: Side
    account_value: float
    risk_budget: float
    risk_per_unit: float
    quantity: int
    position_notional: float
    notional_percent: float
    maximum_loss: float
    potential_profit: float
    risk_reward_ratio: float
    break_even_win_rate: float


@dataclass(frozen=True)
class StrategyMetrics:
    """Probability-weighted metrics for a trading strategy."""

    win_rate_percent: float
    expected_value_per_trade: float
    expected_value_in_r: float
    profit_factor: float
    break_even_win_rate: float
    kelly_percent: float
    half_kelly_percent: float
    edge_percent: float


@dataclass(frozen=True)
class PortfolioRisk:
    """Simple pre-trade portfolio risk checks."""

    gross_exposure: float
    gross_exposure_percent: float
    existing_risk: float
    proposed_risk: float
    total_risk: float
    total_risk_percent: float
    remaining_risk_capacity: float
    within_risk_limit: bool


def _normalise_side(side: str) -> Side:
    normalised = side.strip().lower()
    if normalised not in {"long", "short"}:
        raise ValueError("Side must be 'long' or 'short'.")
    return normalised  # type: ignore[return-value]


def _require_positive(**values: float) -> None:
    invalid = [name.replace("_", " ") for name, value in values.items() if value <= 0]
    if invalid:
        raise ValueError(f"{', '.join(invalid).title()} must be greater than zero.")


def calculate_trade(
    side: Side,
    entry_price: float,
    exit_price: float,
    quantity: float,
    cost_bps: float = 0.0,
    *,
    slippage_bps: float = 0.0,
    commission: float = 0.0,
) -> TradeResult:
    """Attribute completed-trade P&L after round-trip execution costs.

    ``cost_bps`` and ``slippage_bps`` apply to entry and exit notional.
    ``commission`` is the total fixed commission for the completed trade.
    """
    clean_side = _normalise_side(side)
    _require_positive(entry_price=entry_price, exit_price=exit_price, quantity=quantity)
    if min(cost_bps, slippage_bps, commission) < 0:
        raise ValueError("Costs, slippage and commission cannot be negative.")

    direction = 1 if clean_side == "long" else -1
    entry_notional = entry_price * quantity
    gross_pnl = direction * (exit_price - entry_price) * quantity
    round_trip_notional = (entry_price + exit_price) * quantity
    variable_costs = round_trip_notional * (cost_bps + slippage_bps) / 10_000
    trading_costs = variable_costs + commission
    net_pnl = gross_pnl - trading_costs

    return TradeResult(
        side=clean_side,
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        entry_notional=entry_notional,
        gross_pnl=gross_pnl,
        trading_costs=trading_costs,
        net_pnl=net_pnl,
        gross_return_percent=gross_pnl / entry_notional * 100,
        net_return_percent=net_pnl / entry_notional * 100,
        price_move_bps=direction * (exit_price - entry_price) / entry_price * 10_000,
        cost_drag_bps=trading_costs / entry_notional * 10_000,
    )


def calculate_risk_reward(entry_price: float, stop_price: float, target_price: float) -> float:
    """Return potential reward per unit of risk."""
    _require_positive(
        entry_price=entry_price, stop_price=stop_price, target_price=target_price
    )
    risk = abs(entry_price - stop_price)
    reward = abs(target_price - entry_price)
    if risk == 0 or reward == 0:
        raise ValueError("Stop and target must both differ from entry price.")
    return reward / risk


def calculate_break_even_win_rate(average_win: float, average_loss: float) -> float:
    """Return the minimum win rate needed to break even."""
    _require_positive(average_win=average_win, average_loss=average_loss)
    return average_loss / (average_win + average_loss) * 100


def calculate_position_size(
    side: Side,
    account_value: float,
    risk_percent: float,
    entry_price: float,
    stop_price: float,
    target_price: float,
    *,
    maximum_notional_percent: float = 100.0,
) -> PositionPlan:
    """Size a trade from its stop loss and an account-level risk budget."""
    clean_side = _normalise_side(side)
    _require_positive(
        account_value=account_value,
        risk_percent=risk_percent,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        maximum_notional_percent=maximum_notional_percent,
    )
    if risk_percent > 100 or maximum_notional_percent > 1_000:
        raise ValueError("Risk or maximum-notional percentage is implausibly high.")
    if clean_side == "long" and not stop_price < entry_price < target_price:
        raise ValueError("A long plan requires stop < entry < target.")
    if clean_side == "short" and not target_price < entry_price < stop_price:
        raise ValueError("A short plan requires target < entry < stop.")

    risk_budget = account_value * risk_percent / 100
    risk_per_unit = abs(entry_price - stop_price)
    risk_limited_quantity = floor(risk_budget / risk_per_unit)
    notional_limit = account_value * maximum_notional_percent / 100
    notional_limited_quantity = floor(notional_limit / entry_price)
    quantity = min(risk_limited_quantity, notional_limited_quantity)
    if quantity < 1:
        raise ValueError("Risk budget is too small to purchase one unit.")

    maximum_loss = quantity * risk_per_unit
    potential_profit = quantity * abs(target_price - entry_price)
    position_notional = quantity * entry_price
    ratio = potential_profit / maximum_loss

    return PositionPlan(
        side=clean_side,
        account_value=account_value,
        risk_budget=risk_budget,
        risk_per_unit=risk_per_unit,
        quantity=quantity,
        position_notional=position_notional,
        notional_percent=position_notional / account_value * 100,
        maximum_loss=maximum_loss,
        potential_profit=potential_profit,
        risk_reward_ratio=ratio,
        break_even_win_rate=1 / (1 + ratio) * 100,
    )


def analyse_strategy(
    win_rate_percent: float,
    average_win: float,
    average_loss: float,
) -> StrategyMetrics:
    """Calculate expectancy, profit factor and Kelly sizing from trade statistics."""
    _require_positive(average_win=average_win, average_loss=average_loss)
    if not 0 <= win_rate_percent <= 100:
        raise ValueError("Win rate must be between 0 and 100.")

    probability_win = win_rate_percent / 100
    probability_loss = 1 - probability_win
    payoff_ratio = average_win / average_loss
    expected_value = probability_win * average_win - probability_loss * average_loss
    profit_factor = (
        float("inf")
        if probability_loss == 0
        else probability_win * average_win / (probability_loss * average_loss)
    )
    kelly_fraction = probability_win - probability_loss / payoff_ratio
    break_even = calculate_break_even_win_rate(average_win, average_loss)

    return StrategyMetrics(
        win_rate_percent=win_rate_percent,
        expected_value_per_trade=expected_value,
        expected_value_in_r=expected_value / average_loss,
        profit_factor=profit_factor,
        break_even_win_rate=break_even,
        kelly_percent=max(0.0, kelly_fraction * 100),
        half_kelly_percent=max(0.0, kelly_fraction * 50),
        edge_percent=win_rate_percent - break_even,
    )


def assess_portfolio_risk(
    account_value: float,
    existing_exposure: float,
    existing_risk: float,
    proposed_notional: float,
    proposed_risk: float,
    portfolio_risk_limit_percent: float,
) -> PortfolioRisk:
    """Check a proposed trade against a total open-risk limit."""
    _require_positive(
        account_value=account_value,
        portfolio_risk_limit_percent=portfolio_risk_limit_percent,
    )
    if min(existing_exposure, existing_risk, proposed_notional, proposed_risk) < 0:
        raise ValueError("Exposure and risk inputs cannot be negative.")

    gross_exposure = existing_exposure + proposed_notional
    total_risk = existing_risk + proposed_risk
    risk_limit = account_value * portfolio_risk_limit_percent / 100
    return PortfolioRisk(
        gross_exposure=gross_exposure,
        gross_exposure_percent=gross_exposure / account_value * 100,
        existing_risk=existing_risk,
        proposed_risk=proposed_risk,
        total_risk=total_risk,
        total_risk_percent=total_risk / account_value * 100,
        remaining_risk_capacity=max(0.0, risk_limit - total_risk),
        within_risk_limit=total_risk <= risk_limit,
    )


def read_number(prompt: str, *, allow_zero: bool = False) -> float:
    """Read and validate a number from the terminal."""
    while True:
        try:
            value = float(input(prompt))
            if value < 0 or (value == 0 and not allow_zero):
                qualifier = "zero or greater" if allow_zero else "greater than zero"
                print(f"Please enter a number {qualifier}.")
                continue
            return value
        except ValueError:
            print("Please enter a valid number.")


def read_side() -> Side:
    """Read a valid position side."""
    while True:
        try:
            return _normalise_side(input("Position side (long/short): "))
        except ValueError as error:
            print(error)


def run_trade_analysis() -> None:
    result = calculate_trade(
        side=read_side(),
        entry_price=read_number("Entry price: "),
        exit_price=read_number("Exit price: "),
        quantity=read_number("Quantity: "),
        cost_bps=read_number("Fees (bps per leg, 0 if none): ", allow_zero=True),
        slippage_bps=read_number("Slippage (bps per leg, 0 if none): ", allow_zero=True),
        commission=read_number("Total fixed commission (0 if none): ", allow_zero=True),
    )
    outcome = "PROFIT" if result.net_pnl > 0 else "LOSS" if result.net_pnl < 0 else "FLAT"
    print("\n--- Execution & P&L Attribution ---")
    print(f"Side / notional:   {result.side.upper()} / {result.entry_notional:,.2f}")
    print(f"Gross P&L:         {result.gross_pnl:,.2f}")
    print(f"Trading costs:     {result.trading_costs:,.2f}")
    print(f"Net P&L:           {result.net_pnl:,.2f} ({outcome})")
    print(f"Gross / net return:{result.gross_return_percent:>8.2f}% / {result.net_return_percent:.2f}%")
    print(f"Price move:        {result.price_move_bps:,.2f} bps")
    print(f"Cost drag:         {result.cost_drag_bps:,.2f} bps")


def run_position_sizing() -> None:
    plan = calculate_position_size(
        side=read_side(),
        account_value=read_number("Account value: "),
        risk_percent=read_number("Maximum risk on this trade (%): "),
        entry_price=read_number("Entry price: "),
        stop_price=read_number("Stop price: "),
        target_price=read_number("Target price: "),
        maximum_notional_percent=read_number("Maximum position size (% of account): "),
    )
    print("\n--- Risk-Budgeted Position Plan ---")
    print(f"Recommended quantity: {plan.quantity:,}")
    print(f"Position notional:    {plan.position_notional:,.2f} ({plan.notional_percent:.2f}%)")
    print(f"Risk budget:          {plan.risk_budget:,.2f}")
    print(f"Maximum loss at stop: {plan.maximum_loss:,.2f}")
    print(f"Profit at target:     {plan.potential_profit:,.2f}")
    print(f"Risk/reward:          1:{plan.risk_reward_ratio:.2f}")
    print(f"Break-even win rate:  {plan.break_even_win_rate:.2f}%")


def run_strategy_analysis() -> None:
    metrics = analyse_strategy(
        win_rate_percent=read_number("Historical win rate (%): ", allow_zero=True),
        average_win=read_number("Average winning trade: "),
        average_loss=read_number("Average losing trade (positive number): "),
    )
    verdict = "POSITIVE EDGE" if metrics.expected_value_per_trade > 0 else "NO DEMONSTRATED EDGE"
    print("\n--- Strategy Edge Analysis ---")
    print(f"Expected value/trade: {metrics.expected_value_per_trade:,.2f} ({verdict})")
    print(f"Expectancy:           {metrics.expected_value_in_r:.3f}R")
    print(f"Profit factor:        {metrics.profit_factor:.2f}")
    print(f"Break-even win rate:  {metrics.break_even_win_rate:.2f}%")
    print(f"Win-rate edge:        {metrics.edge_percent:+.2f} percentage points")
    print(f"Full Kelly estimate:  {metrics.kelly_percent:.2f}%")
    print(f"Half-Kelly estimate:  {metrics.half_kelly_percent:.2f}%")


def run_portfolio_check() -> None:
    result = assess_portfolio_risk(
        account_value=read_number("Account value: "),
        existing_exposure=read_number("Existing gross exposure: ", allow_zero=True),
        existing_risk=read_number("Existing open risk: ", allow_zero=True),
        proposed_notional=read_number("Proposed trade notional: ", allow_zero=True),
        proposed_risk=read_number("Proposed trade risk at stop: ", allow_zero=True),
        portfolio_risk_limit_percent=read_number("Portfolio open-risk limit (%): "),
    )
    verdict = "PASS" if result.within_risk_limit else "BREACH"
    print("\n--- Portfolio Pre-Trade Check ---")
    print(f"Gross exposure:       {result.gross_exposure:,.2f} ({result.gross_exposure_percent:.2f}%)")
    print(f"Total open risk:      {result.total_risk:,.2f} ({result.total_risk_percent:.2f}%)")
    print(f"Remaining capacity:   {result.remaining_risk_capacity:,.2f}")
    print(f"Risk-limit decision:  {verdict}")


def main() -> None:
    """Run the interactive analytics menu."""
    actions: dict[str, Callable[[], None]] = {
        "1": run_trade_analysis,
        "2": run_position_sizing,
        "3": run_strategy_analysis,
        "4": run_portfolio_check,
    }
    print("\nMelQuantLab — Trade & Risk Analytics")
    while True:
        print("\n1. Completed trade: execution and P&L")
        print("2. New trade: risk-based position sizing")
        print("3. Strategy: expectancy, profit factor and Kelly")
        print("4. Portfolio: pre-trade risk-limit check")
        print("5. Exit")
        choice = input("Choose an option: ").strip()
        if choice == "5":
            print("Session complete.")
            return
        action = actions.get(choice)
        if action is None:
            print("Please choose 1, 2, 3, 4 or 5.")
            continue
        try:
            action()
        except ValueError as error:
            print(f"Unable to calculate: {error}")


if __name__ == "__main__":
    main()
