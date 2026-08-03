"""Fixed-rate bond pricing, yield and interest-rate risk analytics."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class BondInputs:
    """Contract and settlement inputs for a plain fixed-rate bond."""

    face_value: float
    coupon_rate: float
    years_to_maturity: float
    payments_per_year: int = 2
    settlement_fraction: float = 0.0


@dataclass(frozen=True)
class BondAnalytics:
    """Valuation and rate-risk measures at a specified yield."""

    clean_price: float
    dirty_price: float
    accrued_interest: float
    current_yield_percent: float
    macaulay_duration: float
    modified_duration: float
    convexity: float
    dv01: float


@dataclass(frozen=True)
class YieldResult:
    """Yield-to-maturity solver output."""

    yield_to_maturity: float
    repriced_clean_price: float
    market_clean_price: float
    iterations: int
    converged: bool


@dataclass(frozen=True)
class RateScenario:
    """Exact and duration-convexity price response to a yield shock."""

    shock_bps: float
    shocked_yield: float
    exact_clean_price: float
    exact_change_percent: float
    duration_convexity_change_percent: float
    approximation_error_bps: float


def _validate(bond: BondInputs) -> BondInputs:
    if min(bond.face_value, bond.years_to_maturity) <= 0:
        raise ValueError("Face value and maturity must be greater than zero.")
    if bond.coupon_rate < 0:
        raise ValueError("Coupon rate cannot be negative.")
    if bond.payments_per_year not in {1, 2, 4, 12}:
        raise ValueError("Payment frequency must be 1, 2, 4 or 12 per year.")
    if not 0 <= bond.settlement_fraction < 1:
        raise ValueError("Settlement fraction must be between 0 and 1.")
    periods = bond.years_to_maturity * bond.payments_per_year
    if abs(periods - round(periods)) > 1e-9:
        raise ValueError("Maturity must contain a whole number of coupon periods.")
    return bond


def cash_flows(bond: BondInputs) -> list[tuple[float, float]]:
    """Return time-from-settlement and cash amount for each remaining payment."""
    bond = _validate(bond)
    number_of_periods = round(bond.years_to_maturity * bond.payments_per_year)
    coupon = bond.face_value * bond.coupon_rate / bond.payments_per_year
    flows: list[tuple[float, float]] = []
    for period in range(1, number_of_periods + 1):
        time = (period - bond.settlement_fraction) / bond.payments_per_year
        amount = coupon + (bond.face_value if period == number_of_periods else 0.0)
        flows.append((time, amount))
    return flows


def accrued_interest(bond: BondInputs) -> float:
    """Return coupon accrued since the previous payment date."""
    bond = _validate(bond)
    coupon = bond.face_value * bond.coupon_rate / bond.payments_per_year
    return coupon * bond.settlement_fraction


def dirty_price(bond: BondInputs, yield_to_maturity: float) -> float:
    """Present value all remaining cash flows at a nominal annual yield."""
    bond = _validate(bond)
    if yield_to_maturity <= -bond.payments_per_year:
        raise ValueError("Yield is below the mathematically valid discount-rate bound.")
    periodic_yield = yield_to_maturity / bond.payments_per_year
    return sum(
        amount / (1 + periodic_yield) ** (time * bond.payments_per_year)
        for time, amount in cash_flows(bond)
    )


def clean_price(bond: BondInputs, yield_to_maturity: float) -> float:
    """Return quoted price excluding accrued interest."""
    return dirty_price(bond, yield_to_maturity) - accrued_interest(bond)


def analyse_bond(bond: BondInputs, yield_to_maturity: float) -> BondAnalytics:
    """Calculate price, duration, convexity and DV01."""
    bond = _validate(bond)
    dirty = dirty_price(bond, yield_to_maturity)
    clean = dirty - accrued_interest(bond)
    if clean <= 0:
        raise ValueError("Calculated clean price is not positive.")
    periodic_yield = yield_to_maturity / bond.payments_per_year
    discounted_flows = [
        (
            time,
            amount / (1 + periodic_yield) ** (time * bond.payments_per_year),
        )
        for time, amount in cash_flows(bond)
    ]
    macaulay = sum(time * present_value for time, present_value in discounted_flows) / dirty
    modified = macaulay / (1 + periodic_yield)

    frequency = bond.payments_per_year
    convexity_numerator = 0.0
    for time, present_value in discounted_flows:
        periods_from_settlement = time * frequency
        convexity_numerator += (
            present_value
            * periods_from_settlement
            * (periods_from_settlement + 1)
        )
    convexity = convexity_numerator / (dirty * frequency**2 * (1 + periodic_yield) ** 2)
    coupon_annual = bond.face_value * bond.coupon_rate

    return BondAnalytics(
        clean_price=clean,
        dirty_price=dirty,
        accrued_interest=accrued_interest(bond),
        current_yield_percent=coupon_annual / clean * 100,
        macaulay_duration=macaulay,
        modified_duration=modified,
        convexity=convexity,
        dv01=modified * dirty * 0.0001,
    )


def yield_to_maturity(
    bond: BondInputs,
    market_clean_price: float,
    *,
    tolerance: float = 1e-10,
    max_iterations: int = 250,
) -> YieldResult:
    """Solve nominal annual YTM from a clean market price using bisection."""
    bond = _validate(bond)
    if market_clean_price <= 0:
        raise ValueError("Market clean price must be greater than zero.")
    low, high = -0.95 * bond.payments_per_year, 5.0
    trial_yield = 0.0
    repriced = 0.0
    for iteration in range(1, max_iterations + 1):
        trial_yield = (low + high) / 2
        repriced = clean_price(bond, trial_yield)
        difference = repriced - market_clean_price
        if abs(difference) <= tolerance:
            return YieldResult(trial_yield, repriced, market_clean_price, iteration, True)
        if difference > 0:
            low = trial_yield
        else:
            high = trial_yield
    return YieldResult(trial_yield, repriced, market_clean_price, max_iterations, False)


def rate_scenarios(
    bond: BondInputs,
    yield_to_maturity: float,
    shocks_bps: list[float],
) -> list[RateScenario]:
    """Compare exact repricing with the duration-convexity approximation."""
    base = analyse_bond(bond, yield_to_maturity)
    scenarios: list[RateScenario] = []
    for shock_bps in shocks_bps:
        change_in_yield = shock_bps / 10_000
        shocked_yield = yield_to_maturity + change_in_yield
        exact_price = clean_price(bond, shocked_yield)
        exact_change = (exact_price - base.clean_price) / base.clean_price
        approximation = (
            -base.modified_duration * change_in_yield
            + 0.5 * base.convexity * change_in_yield**2
        )
        scenarios.append(
            RateScenario(
                shock_bps=shock_bps,
                shocked_yield=shocked_yield,
                exact_clean_price=exact_price,
                exact_change_percent=exact_change * 100,
                duration_convexity_change_percent=approximation * 100,
                approximation_error_bps=(approximation - exact_change) * 10_000,
            )
        )
    return scenarios


def read_number(prompt: str, *, allow_zero: bool = False) -> float:
    while True:
        try:
            value = float(input(prompt))
            if value < 0 or (value == 0 and not allow_zero):
                print("Please enter a valid non-negative number.")
                continue
            return value
        except ValueError:
            print("Please enter a valid number.")


def read_bond() -> BondInputs:
    return BondInputs(
        face_value=read_number("Face value: "),
        coupon_rate=read_number("Annual coupon rate (%): ", allow_zero=True) / 100,
        years_to_maturity=read_number("Years to maturity: "),
        payments_per_year=int(read_number("Payments per year (1/2/4/12): ")),
        settlement_fraction=read_number(
            "Fraction of coupon period accrued (0 to <1): ", allow_zero=True
        ),
    )


def print_analytics(analytics: BondAnalytics) -> None:
    print("\n--- Bond Valuation & Risk ---")
    print(f"Clean price:        {analytics.clean_price:,.4f}")
    print(f"Dirty price:        {analytics.dirty_price:,.4f}")
    print(f"Accrued interest:   {analytics.accrued_interest:,.4f}")
    print(f"Current yield:      {analytics.current_yield_percent:,.4f}%")
    print(f"Macaulay duration:  {analytics.macaulay_duration:,.4f} years")
    print(f"Modified duration:  {analytics.modified_duration:,.4f}")
    print(f"Convexity:          {analytics.convexity:,.4f}")
    print(f"DV01:               {analytics.dv01:,.6f}")


def run_price_and_risk() -> None:
    bond = read_bond()
    ytm = read_number("Yield to maturity (%): ", allow_zero=True) / 100
    print_analytics(analyse_bond(bond, ytm))


def run_yield_solver() -> None:
    bond = read_bond()
    market_price = read_number("Market clean price: ")
    result = yield_to_maturity(bond, market_price)
    print("\n--- Yield to Maturity ---")
    print(f"YTM:              {result.yield_to_maturity * 100:.6f}%")
    print(f"Repriced clean:   {result.repriced_clean_price:.6f}")
    print(f"Iterations:       {result.iterations}")
    print(f"Converged:        {'YES' if result.converged else 'NO'}")


def run_scenario_analysis() -> None:
    bond = read_bond()
    ytm = read_number("Yield to maturity (%): ", allow_zero=True) / 100
    scenarios = rate_scenarios(bond, ytm, [-200, -100, -50, 0, 50, 100, 200])
    print("\n--- Interest-Rate Shock Scenarios ---")
    print("Shock | New YTM | Exact price | Exact change | Dur+conv change | Error")
    print("------+---------+-------------+--------------+-----------------+------")
    for item in scenarios:
        print(
            f"{item.shock_bps:>+5.0f} | {item.shocked_yield * 100:>6.2f}% |"
            f" {item.exact_clean_price:>11.4f} | {item.exact_change_percent:>+11.3f}% |"
            f" {item.duration_convexity_change_percent:>+14.3f}% |"
            f" {item.approximation_error_bps:>+5.1f}bp"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fixed-rate bond analytics.")
    parser.parse_args()
    actions: dict[str, Callable[[], None]] = {
        "1": run_price_and_risk,
        "2": run_yield_solver,
        "3": run_scenario_analysis,
    }
    print("\nMelQuantLab — Bond Pricing, Yield & Duration")
    while True:
        print("\n1. Price, duration, convexity and DV01")
        print("2. Solve yield to maturity from market price")
        print("3. Interest-rate shock scenarios")
        print("4. Exit")
        choice = input("Choose an option: ").strip()
        if choice == "4":
            print("Session complete.")
            return
        action = actions.get(choice)
        if action is None:
            print("Please choose 1, 2, 3 or 4.")
            continue
        try:
            action()
        except ValueError as error:
            print(f"Unable to calculate: {error}")


if __name__ == "__main__":
    main()
