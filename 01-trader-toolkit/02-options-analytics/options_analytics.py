"""Black-Scholes pricing, Greeks and implied-volatility analytics."""

from __future__ import annotations

from dataclasses import dataclass
from math import erf, exp, log, pi, sqrt
from typing import Callable, Literal


OptionType = Literal["call", "put"]


@dataclass(frozen=True)
class OptionInputs:
    """Market and contract inputs for one European option."""

    option_type: OptionType
    spot: float
    strike: float
    time_to_expiry: float
    risk_free_rate: float
    volatility: float
    dividend_yield: float = 0.0


@dataclass(frozen=True)
class OptionAnalytics:
    """Black-Scholes fair value and first/second-order Greeks."""

    theoretical_value: float
    intrinsic_value: float
    time_value: float
    delta: float
    gamma: float
    vega: float
    theta_per_day: float
    rho: float
    d1: float
    d2: float


@dataclass(frozen=True)
class ImpliedVolatilityResult:
    """Implied-volatility solver output and convergence evidence."""

    volatility: float
    model_price: float
    market_price: float
    iterations: int
    converged: bool


@dataclass(frozen=True)
class ScenarioResult:
    """Revaluation of an option under a spot/volatility shock."""

    spot_change_percent: float
    volatility_change_points: float
    shocked_spot: float
    shocked_volatility: float
    option_value: float
    value_change: float
    value_change_percent: float


@dataclass(frozen=True)
class PairedValuation:
    """Call and put fair values with mark-to-model P&L."""

    call_value: float
    put_value: float
    call_purchase_price: float
    put_purchase_price: float
    call_pnl: float
    put_pnl: float


@dataclass(frozen=True)
class SurfacePoint:
    """One spot/volatility point on a paired call and put scenario surface."""

    shocked_spot: float
    shocked_volatility: float
    call_value: float
    put_value: float
    call_pnl: float
    put_pnl: float


def normal_cdf(value: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1 + erf(value / sqrt(2)))


def normal_pdf(value: float) -> float:
    """Standard normal probability density function."""
    return exp(-0.5 * value**2) / sqrt(2 * pi)


def _normalise_option_type(option_type: str) -> OptionType:
    clean_type = option_type.strip().lower()
    if clean_type not in {"call", "put"}:
        raise ValueError("Option type must be 'call' or 'put'.")
    return clean_type  # type: ignore[return-value]


def _validate(inputs: OptionInputs) -> OptionInputs:
    option_type = _normalise_option_type(inputs.option_type)
    if min(inputs.spot, inputs.strike, inputs.time_to_expiry, inputs.volatility) <= 0:
        raise ValueError("Spot, strike, time and volatility must be greater than zero.")
    if inputs.volatility > 10:
        raise ValueError("Volatility must be supplied as a decimal (20% = 0.20).")
    return OptionInputs(
        option_type=option_type,
        spot=inputs.spot,
        strike=inputs.strike,
        time_to_expiry=inputs.time_to_expiry,
        risk_free_rate=inputs.risk_free_rate,
        volatility=inputs.volatility,
        dividend_yield=inputs.dividend_yield,
    )


def _d1_d2(inputs: OptionInputs) -> tuple[float, float]:
    numerator = log(inputs.spot / inputs.strike) + (
        inputs.risk_free_rate - inputs.dividend_yield + 0.5 * inputs.volatility**2
    ) * inputs.time_to_expiry
    denominator = inputs.volatility * sqrt(inputs.time_to_expiry)
    d1 = numerator / denominator
    return d1, d1 - denominator


def option_price(inputs: OptionInputs) -> float:
    """Return the Black-Scholes-Merton value of a European option."""
    inputs = _validate(inputs)
    d1, d2 = _d1_d2(inputs)
    discounted_spot = inputs.spot * exp(-inputs.dividend_yield * inputs.time_to_expiry)
    discounted_strike = inputs.strike * exp(-inputs.risk_free_rate * inputs.time_to_expiry)
    if inputs.option_type == "call":
        return discounted_spot * normal_cdf(d1) - discounted_strike * normal_cdf(d2)
    return discounted_strike * normal_cdf(-d2) - discounted_spot * normal_cdf(-d1)


def price_pair(
    *,
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    call_purchase_price: float = 0.0,
    put_purchase_price: float = 0.0,
) -> PairedValuation:
    """Value matching European call/put contracts and mark each to purchase price."""
    if call_purchase_price < 0 or put_purchase_price < 0:
        raise ValueError("Purchase prices cannot be negative.")
    common = (spot, strike, time_to_expiry, risk_free_rate, volatility)
    call_value = option_price(OptionInputs("call", *common))
    put_value = option_price(OptionInputs("put", *common))
    return PairedValuation(
        call_value=call_value,
        put_value=put_value,
        call_purchase_price=call_purchase_price,
        put_purchase_price=put_purchase_price,
        call_pnl=call_value - call_purchase_price,
        put_pnl=put_value - put_purchase_price,
    )


def scenario_surface(
    *,
    spot_prices: list[float],
    volatilities: list[float],
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    call_purchase_price: float,
    put_purchase_price: float,
) -> list[SurfacePoint]:
    """Return paired valuations for every spot/volatility combination."""
    if not spot_prices or not volatilities:
        raise ValueError("Scenario axes cannot be empty.")
    points: list[SurfacePoint] = []
    for shocked_spot in spot_prices:
        for shocked_volatility in volatilities:
            values = price_pair(
                spot=shocked_spot,
                strike=strike,
                time_to_expiry=time_to_expiry,
                risk_free_rate=risk_free_rate,
                volatility=shocked_volatility,
                call_purchase_price=call_purchase_price,
                put_purchase_price=put_purchase_price,
            )
            points.append(
                SurfacePoint(
                    shocked_spot=shocked_spot,
                    shocked_volatility=shocked_volatility,
                    call_value=values.call_value,
                    put_value=values.put_value,
                    call_pnl=values.call_pnl,
                    put_pnl=values.put_pnl,
                )
            )
    return points


def analyse_option(inputs: OptionInputs) -> OptionAnalytics:
    """Return price, intrinsic/time value and Black-Scholes Greeks.

    Vega and rho represent a one-percentage-point change. Theta is per calendar day.
    """
    inputs = _validate(inputs)
    d1, d2 = _d1_d2(inputs)
    value = option_price(inputs)
    discount_q = exp(-inputs.dividend_yield * inputs.time_to_expiry)
    discount_r = exp(-inputs.risk_free_rate * inputs.time_to_expiry)
    density = normal_pdf(d1)
    root_time = sqrt(inputs.time_to_expiry)

    gamma = discount_q * density / (inputs.spot * inputs.volatility * root_time)
    vega = inputs.spot * discount_q * density * root_time / 100
    common_theta = -(
        inputs.spot * discount_q * density * inputs.volatility / (2 * root_time)
    )

    if inputs.option_type == "call":
        intrinsic = max(0.0, inputs.spot - inputs.strike)
        delta = discount_q * normal_cdf(d1)
        theta_annual = (
            common_theta
            - inputs.risk_free_rate * inputs.strike * discount_r * normal_cdf(d2)
            + inputs.dividend_yield * inputs.spot * discount_q * normal_cdf(d1)
        )
        rho = inputs.strike * inputs.time_to_expiry * discount_r * normal_cdf(d2) / 100
    else:
        intrinsic = max(0.0, inputs.strike - inputs.spot)
        delta = discount_q * (normal_cdf(d1) - 1)
        theta_annual = (
            common_theta
            + inputs.risk_free_rate * inputs.strike * discount_r * normal_cdf(-d2)
            - inputs.dividend_yield * inputs.spot * discount_q * normal_cdf(-d1)
        )
        rho = -inputs.strike * inputs.time_to_expiry * discount_r * normal_cdf(-d2) / 100

    return OptionAnalytics(
        theoretical_value=value,
        intrinsic_value=intrinsic,
        time_value=value - intrinsic,
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta_per_day=theta_annual / 365,
        rho=rho,
        d1=d1,
        d2=d2,
    )


def no_arbitrage_bounds(inputs: OptionInputs) -> tuple[float, float]:
    """Return lower and upper European option price bounds."""
    inputs = _validate(inputs)
    discounted_spot = inputs.spot * exp(-inputs.dividend_yield * inputs.time_to_expiry)
    discounted_strike = inputs.strike * exp(-inputs.risk_free_rate * inputs.time_to_expiry)
    if inputs.option_type == "call":
        return max(0.0, discounted_spot - discounted_strike), discounted_spot
    return max(0.0, discounted_strike - discounted_spot), discounted_strike


def implied_volatility(
    market_price: float,
    inputs: OptionInputs,
    *,
    tolerance: float = 1e-8,
    max_iterations: int = 200,
) -> ImpliedVolatilityResult:
    """Solve implied volatility using a robust bisection search."""
    if market_price <= 0:
        raise ValueError("Market price must be greater than zero.")
    checked = _validate(inputs)
    lower_bound, upper_bound = no_arbitrage_bounds(checked)
    if not lower_bound <= market_price <= upper_bound:
        raise ValueError(
            f"Market price violates no-arbitrage bounds [{lower_bound:.4f}, {upper_bound:.4f}]."
        )

    low_vol, high_vol = 1e-6, 5.0
    model_price = 0.0
    volatility = checked.volatility
    for iteration in range(1, max_iterations + 1):
        volatility = (low_vol + high_vol) / 2
        trial = OptionInputs(
            option_type=checked.option_type,
            spot=checked.spot,
            strike=checked.strike,
            time_to_expiry=checked.time_to_expiry,
            risk_free_rate=checked.risk_free_rate,
            volatility=volatility,
            dividend_yield=checked.dividend_yield,
        )
        model_price = option_price(trial)
        difference = model_price - market_price
        if abs(difference) <= tolerance:
            return ImpliedVolatilityResult(
                volatility, model_price, market_price, iteration, True
            )
        if difference > 0:
            high_vol = volatility
        else:
            low_vol = volatility

    return ImpliedVolatilityResult(
        volatility, model_price, market_price, max_iterations, False
    )


def put_call_parity_gap(
    call_price: float,
    put_price: float,
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    dividend_yield: float = 0.0,
) -> float:
    """Return observed minus theoretical call-minus-put value."""
    if min(call_price, put_price) < 0 or min(spot, strike, time_to_expiry) <= 0:
        raise ValueError("Prices cannot be negative; spot, strike and time must be positive.")
    observed = call_price - put_price
    theoretical = spot * exp(-dividend_yield * time_to_expiry) - strike * exp(
        -risk_free_rate * time_to_expiry
    )
    return observed - theoretical


def scenario_analysis(
    inputs: OptionInputs,
    spot_changes_percent: list[float],
    volatility_changes_points: list[float],
) -> list[ScenarioResult]:
    """Reprice an option across spot and volatility shocks."""
    inputs = _validate(inputs)
    base_value = option_price(inputs)
    results: list[ScenarioResult] = []
    for spot_change in spot_changes_percent:
        for volatility_change in volatility_changes_points:
            shocked_spot = inputs.spot * (1 + spot_change / 100)
            shocked_volatility = inputs.volatility + volatility_change / 100
            if shocked_spot <= 0 or shocked_volatility <= 0:
                continue
            shocked_inputs = OptionInputs(
                option_type=inputs.option_type,
                spot=shocked_spot,
                strike=inputs.strike,
                time_to_expiry=inputs.time_to_expiry,
                risk_free_rate=inputs.risk_free_rate,
                volatility=shocked_volatility,
                dividend_yield=inputs.dividend_yield,
            )
            shocked_value = option_price(shocked_inputs)
            value_change = shocked_value - base_value
            results.append(
                ScenarioResult(
                    spot_change,
                    volatility_change,
                    shocked_spot,
                    shocked_volatility,
                    shocked_value,
                    value_change,
                    value_change / base_value * 100,
                )
            )
    return results


def read_number(prompt: str, *, allow_zero: bool = False) -> float:
    while True:
        try:
            value = float(input(prompt))
            if value < 0 or (value == 0 and not allow_zero):
                print("Please enter a valid non-negative value.")
                continue
            return value
        except ValueError:
            print("Please enter a valid number.")


def read_option_inputs(*, volatility_required: bool = True) -> OptionInputs:
    while True:
        try:
            option_type = _normalise_option_type(input("Option type (call/put): "))
            break
        except ValueError as error:
            print(error)
    volatility_percent = read_number(
        "Volatility (%): " if volatility_required else "Initial volatility guess (%): "
    )
    return OptionInputs(
        option_type=option_type,
        spot=read_number("Spot price: "),
        strike=read_number("Strike price: "),
        time_to_expiry=read_number("Time to expiry (years): "),
        risk_free_rate=read_number("Risk-free rate (%): ", allow_zero=True) / 100,
        volatility=volatility_percent / 100,
        dividend_yield=read_number("Dividend yield (%): ", allow_zero=True) / 100,
    )


def run_price_and_greeks() -> None:
    analytics = analyse_option(read_option_inputs())
    print("\n--- Black-Scholes Valuation ---")
    print(f"Theoretical value: {analytics.theoretical_value:,.4f}")
    print(f"Intrinsic value:   {analytics.intrinsic_value:,.4f}")
    print(f"Time value:        {analytics.time_value:,.4f}")
    print("\n--- Greeks ---")
    print(f"Delta:             {analytics.delta:,.6f}")
    print(f"Gamma:             {analytics.gamma:,.6f}")
    print(f"Vega (1 vol point):{analytics.vega:>10,.6f}")
    print(f"Theta (per day):   {analytics.theta_per_day:,.6f}")
    print(f"Rho (1 rate point):{analytics.rho:>10,.6f}")


def run_implied_volatility() -> None:
    market_price = read_number("Observed market price: ")
    result = implied_volatility(market_price, read_option_inputs(volatility_required=False))
    print("\n--- Implied Volatility ---")
    print(f"Implied volatility: {result.volatility * 100:.4f}%")
    print(f"Repriced value:     {result.model_price:.6f}")
    print(f"Iterations:         {result.iterations}")
    print(f"Converged:          {'YES' if result.converged else 'NO'}")


def run_scenarios() -> None:
    inputs = read_option_inputs()
    scenarios = scenario_analysis(inputs, [-10, -5, 0, 5, 10], [-5, 0, 5])
    print("\n--- Spot / Volatility Scenario Grid ---")
    print("Spot shock | Vol shock | Option value | Value change")
    print("-----------+-----------+--------------+-------------")
    for item in scenarios:
        print(
            f"{item.spot_change_percent:>+9.1f}% | {item.volatility_change_points:>+8.1f}pt |"
            f" {item.option_value:>12.4f} | {item.value_change_percent:>+10.2f}%"
        )


def run_parity_check() -> None:
    call_price = read_number("Call market price: ", allow_zero=True)
    put_price = read_number("Put market price: ", allow_zero=True)
    gap = put_call_parity_gap(
        call_price,
        put_price,
        read_number("Spot price: "),
        read_number("Strike price: "),
        read_number("Time to expiry (years): "),
        read_number("Risk-free rate (%): ", allow_zero=True) / 100,
        read_number("Dividend yield (%): ", allow_zero=True) / 100,
    )
    print("\n--- Put-Call Parity ---")
    print(f"Parity gap: {gap:+.6f}")
    print("Interpretation: near zero is consistent with parity before trading costs.")


def main() -> None:
    actions: dict[str, Callable[[], None]] = {
        "1": run_price_and_greeks,
        "2": run_implied_volatility,
        "3": run_scenarios,
        "4": run_parity_check,
    }
    print("\nMelQuantLab — Black-Scholes Options Analytics")
    while True:
        print("\n1. Theoretical value and Greeks")
        print("2. Implied volatility")
        print("3. Spot/volatility scenario grid")
        print("4. Put-call parity check")
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
