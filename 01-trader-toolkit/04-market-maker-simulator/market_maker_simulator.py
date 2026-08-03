"""Interactive market-making simulator with inventory and adverse selection."""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from typing import Literal


TradeSide = Literal["client_buy", "client_sell", "none"]


@dataclass(frozen=True)
class Quote:
    """A market maker's two-sided price."""

    bid: float
    ask: float

    @property
    def midpoint(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True)
class RoundResult:
    """State transition and attribution for one quoting round."""

    round_number: int
    fair_value_before: float
    fair_value_after: float
    bid: float
    ask: float
    trade_side: TradeSide
    trade_price: float | None
    trade_size: int
    informed_trade: bool
    inventory: int
    cash: float
    marked_pnl: float
    inventory_risk: float


@dataclass(frozen=True)
class GameSummary:
    """Final scorecard for a market-making session."""

    rounds: int
    trades: int
    client_buys: int
    client_sells: int
    informed_trades: int
    final_inventory: int
    final_fair_value: float
    final_pnl: float
    maximum_absolute_inventory: int
    inventory_breaches: int
    score: float


@dataclass(frozen=True)
class SimulationConfig:
    """Market dynamics and risk constraints."""

    starting_fair_value: float = 100.0
    rounds: int = 20
    volatility_bps: float = 35.0
    informed_probability: float = 0.25
    base_trade_probability: float = 0.65
    trade_size: int = 10
    inventory_limit: int = 50
    inventory_penalty: float = 0.02


def validate_quote(quote: Quote, fair_value: float, inventory: int, inventory_limit: int) -> None:
    """Reject crossed, implausible or risk-increasing quotes."""
    if quote.bid <= 0 or quote.ask <= 0:
        raise ValueError("Bid and ask must be greater than zero.")
    if quote.bid >= quote.ask:
        raise ValueError("Bid must be below ask.")
    if quote.spread > fair_value * 0.10:
        raise ValueError("Quote spread cannot exceed 10% of fair value.")
    if abs(quote.midpoint - fair_value) > fair_value * 0.10:
        raise ValueError("Quote midpoint is too far from fair value.")
    if inventory >= inventory_limit and quote.bid >= fair_value:
        raise ValueError("At the long limit, lower the bid to discourage more buying.")
    if inventory <= -inventory_limit and quote.ask <= fair_value:
        raise ValueError("At the short limit, raise the ask to discourage more selling.")


def inventory_adjusted_quote(
    fair_value: float,
    inventory: int,
    *,
    half_spread_bps: float = 20.0,
    skew_bps_per_unit: float = 0.35,
) -> Quote:
    """Generate a symmetric quote shifted to reduce inventory exposure."""
    if fair_value <= 0 or half_spread_bps <= 0 or skew_bps_per_unit < 0:
        raise ValueError("Fair value and spread must be positive; skew cannot be negative.")
    half_spread = fair_value * half_spread_bps / 10_000
    inventory_skew = fair_value * inventory * skew_bps_per_unit / 10_000
    reservation_price = fair_value - inventory_skew
    return Quote(
        bid=round(reservation_price - half_spread, 4),
        ask=round(reservation_price + half_spread, 4),
    )


class MarketMakerGame:
    """Stateful simulator for repeated two-sided quoting decisions."""

    def __init__(self, config: SimulationConfig, *, seed: int | None = None) -> None:
        if config.starting_fair_value <= 0 or config.rounds <= 0:
            raise ValueError("Starting fair value and rounds must be greater than zero.")
        if not 0 <= config.informed_probability <= 1:
            raise ValueError("Informed probability must be between zero and one.")
        if not 0 <= config.base_trade_probability <= 1:
            raise ValueError("Trade probability must be between zero and one.")
        if min(config.trade_size, config.inventory_limit) <= 0:
            raise ValueError("Trade size and inventory limit must be greater than zero.")
        self.config = config
        self.rng = random.Random(seed)
        self.fair_value = config.starting_fair_value
        self.inventory = 0
        self.cash = 0.0
        self.history: list[RoundResult] = []
        self.inventory_breaches = 0

    @property
    def marked_pnl(self) -> float:
        return self.cash + self.inventory * self.fair_value

    def _next_fair_value(self, informed_direction: int = 0) -> float:
        random_move_bps = self.rng.gauss(0, self.config.volatility_bps)
        information_move_bps = informed_direction * self.config.volatility_bps * 1.75
        move = (random_move_bps + information_move_bps) / 10_000
        return max(0.01, self.fair_value * (1 + move))

    def _trade_probability(self, quote: Quote) -> float:
        half_spread_bps = quote.spread / 2 / self.fair_value * 10_000
        competitiveness = max(0.10, min(1.35, 30 / max(half_spread_bps, 1)))
        return min(0.95, self.config.base_trade_probability * competitiveness)

    def play_round(self, quote: Quote) -> RoundResult:
        """Simulate client flow, a fair-value move and inventory attribution."""
        validate_quote(quote, self.fair_value, self.inventory, self.config.inventory_limit)
        fair_before = self.fair_value
        informed = self.rng.random() < self.config.informed_probability
        trade_occurs = self.rng.random() < self._trade_probability(quote)
        trade_side: TradeSide = "none"
        trade_price: float | None = None
        informed_direction = 0

        if trade_occurs:
            if informed:
                informed_direction = 1 if self.rng.random() < 0.5 else -1
                trade_side = "client_buy" if informed_direction > 0 else "client_sell"
            else:
                buy_attractiveness = max(0.05, quote.midpoint - quote.bid)
                sell_attractiveness = max(0.05, quote.ask - quote.midpoint)
                probability_client_buy = buy_attractiveness / (
                    buy_attractiveness + sell_attractiveness
                )
                trade_side = (
                    "client_buy" if self.rng.random() < probability_client_buy else "client_sell"
                )

            size = self.config.trade_size
            if trade_side == "client_buy":
                trade_price = quote.ask
                self.inventory -= size
                self.cash += trade_price * size
            else:
                trade_price = quote.bid
                self.inventory += size
                self.cash -= trade_price * size

        self.fair_value = self._next_fair_value(informed_direction)
        if abs(self.inventory) > self.config.inventory_limit:
            self.inventory_breaches += 1
        inventory_risk = abs(self.inventory) * self.config.inventory_penalty
        result = RoundResult(
            round_number=len(self.history) + 1,
            fair_value_before=fair_before,
            fair_value_after=self.fair_value,
            bid=quote.bid,
            ask=quote.ask,
            trade_side=trade_side,
            trade_price=trade_price,
            trade_size=self.config.trade_size if trade_occurs else 0,
            informed_trade=informed and trade_occurs,
            inventory=self.inventory,
            cash=self.cash,
            marked_pnl=self.marked_pnl,
            inventory_risk=inventory_risk,
        )
        self.history.append(result)
        return result

    def summary(self) -> GameSummary:
        """Return a risk-adjusted final scorecard."""
        trades = [result for result in self.history if result.trade_side != "none"]
        maximum_inventory = max((abs(result.inventory) for result in self.history), default=0)
        risk_penalty = maximum_inventory * self.config.inventory_penalty
        breach_penalty = self.inventory_breaches * 5.0
        score = self.marked_pnl - risk_penalty - breach_penalty
        return GameSummary(
            rounds=len(self.history),
            trades=len(trades),
            client_buys=sum(result.trade_side == "client_buy" for result in trades),
            client_sells=sum(result.trade_side == "client_sell" for result in trades),
            informed_trades=sum(result.informed_trade for result in trades),
            final_inventory=self.inventory,
            final_fair_value=self.fair_value,
            final_pnl=self.marked_pnl,
            maximum_absolute_inventory=maximum_inventory,
            inventory_breaches=self.inventory_breaches,
            score=score,
        )


def print_round(result: RoundResult) -> None:
    trade_description = "NO TRADE"
    if result.trade_side == "client_buy":
        trade_description = f"CLIENT BOUGHT {result.trade_size} @ {result.trade_price:.4f}"
    elif result.trade_side == "client_sell":
        trade_description = f"CLIENT SOLD {result.trade_size} @ {result.trade_price:.4f}"
    informed = " | INFORMED FLOW" if result.informed_trade else ""
    print(f"\nRound {result.round_number}: {trade_description}{informed}")
    print(f"Fair value: {result.fair_value_before:.4f} → {result.fair_value_after:.4f}")
    print(f"Inventory:  {result.inventory:+d}")
    print(f"Marked P&L: {result.marked_pnl:+.2f}")


def print_summary(summary: GameSummary) -> None:
    print("\n=== Market Maker Scorecard ===")
    print(f"Rounds / trades:       {summary.rounds} / {summary.trades}")
    print(f"Client buys / sells:   {summary.client_buys} / {summary.client_sells}")
    print(f"Informed trades:       {summary.informed_trades}")
    print(f"Final inventory:       {summary.final_inventory:+d}")
    print(f"Maximum |inventory|:   {summary.maximum_absolute_inventory}")
    print(f"Inventory breaches:    {summary.inventory_breaches}")
    print(f"Final fair value:      {summary.final_fair_value:.4f}")
    print(f"Final marked P&L:      {summary.final_pnl:+.2f}")
    print(f"Risk-adjusted score:   {summary.score:+.2f}")


def run_game(*, rounds: int, seed: int | None, automatic: bool) -> GameSummary:
    config = SimulationConfig(rounds=rounds)
    game = MarketMakerGame(config, seed=seed)
    print("\nMelQuantLab — Market Maker Simulator")
    print("Quote a bid and ask around fair value while controlling inventory risk.")

    for round_number in range(1, rounds + 1):
        print(f"\n--- Round {round_number}/{rounds} ---")
        print(f"Fair value: {game.fair_value:.4f} | Inventory: {game.inventory:+d} | P&L: {game.marked_pnl:+.2f}")
        suggested = inventory_adjusted_quote(game.fair_value, game.inventory)
        print(f"Model quote: {suggested.bid:.4f} / {suggested.ask:.4f}")

        if automatic:
            quote = suggested
        else:
            while True:
                try:
                    bid = float(input("Your bid (or press Return for model quote): ") or suggested.bid)
                    ask = float(input("Your ask (or press Return for model quote): ") or suggested.ask)
                    quote = Quote(bid, ask)
                    validate_quote(quote, game.fair_value, game.inventory, config.inventory_limit)
                    break
                except ValueError as error:
                    print(f"Invalid quote: {error}")
        print_round(game.play_round(quote))

    summary = game.summary()
    print_summary(summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Play the MelQuantLab market-making game.")
    parser.add_argument("--rounds", type=int, default=20, help="Number of quoting rounds.")
    parser.add_argument("--seed", type=int, help="Optional reproducible random seed.")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Let the inventory-aware model quote automatically.",
    )
    args = parser.parse_args()
    run_game(rounds=args.rounds, seed=args.seed, automatic=args.auto)


if __name__ == "__main__":
    main()
