from bisect import bisect_right
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from trips.exceptions import UnreachableRoute

__all__ = ["FuelCandidate", "FuelPlan", "FuelStop", "UnreachableRoute", "plan_fuel"]

NO_FUEL_FOR_SALE = Decimal("Infinity")
EPSILON_GALLONS = 1e-9


@dataclass(frozen=True)
class FuelCandidate:
    station: Any
    mile_marker: float
    price_per_gallon: Decimal
    offset_miles: float = 0.0


@dataclass(frozen=True)
class FuelStop:
    station: Any
    mile_marker: float
    gallons: float
    price_per_gallon: Decimal
    cost: Decimal
    offset_miles: float = 0.0


@dataclass(frozen=True)
class FuelPlan:
    stops: list[FuelStop]
    total_gallons: float
    total_cost: Decimal


def _undominated_candidates(candidates: list[FuelCandidate]) -> list[FuelCandidate]:
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            candidate.mile_marker,
            candidate.offset_miles,
            candidate.price_per_gallon,
        ),
    )
    kept: list[FuelCandidate] = []
    group_mile: float | None = None
    group_best_price: Decimal | None = None
    for candidate in ordered:
        if candidate.mile_marker != group_mile:
            group_mile, group_best_price = candidate.mile_marker, None
        if group_best_price is not None and group_best_price <= candidate.price_per_gallon:
            continue
        kept.append(candidate)
        group_best_price = candidate.price_per_gallon
    return kept


def _check_reachable(
    nodes: list[FuelCandidate],
    usable_miles: float,
    miles_per_gallon: float,
    usable_start_gallons: float,
    fuel_reserve_gallons: float,
) -> None:
    reserve_note = (
        f" above the {fuel_reserve_gallons:g}-gallon reserve" if fuel_reserve_gallons else ""
    )
    for previous, current in zip(nodes, nodes[1:], strict=False):
        if current.mile_marker - previous.mile_marker > usable_miles:
            raise UnreachableRoute(
                f"no fuel station between mile {previous.mile_marker:.0f} and mile "
                f"{current.mile_marker:.0f}, a gap longer than the "
                f"{usable_miles:.0f}-mile range{reserve_note}"
            )

    if nodes[0].price_per_gallon != NO_FUEL_FOR_SALE:
        return
    first = min(nodes[1:], key=lambda node: node.mile_marker + node.offset_miles)
    first_miles = first.mile_marker + first.offset_miles
    if first_miles > usable_start_gallons * miles_per_gallon:
        place = (
            "the route has no fuel station"
            if first is nodes[-1]
            else f"the first fuel station is at mile {first.mile_marker:.0f}"
        )
        needed_gallons = first_miles / miles_per_gallon + fuel_reserve_gallons
        raise UnreachableRoute(f"{place}; set start_fuel_gallons to at least {needed_gallons:.1f}")


def _offer(
    bucket: dict[float, tuple[float, int, float, float]],
    remaining: float,
    cost: float,
    move: tuple[int, float, float],
) -> None:
    key = round(remaining, 6)
    best = bucket.get(key)
    if best is None or cost < best[0]:
        bucket[key] = (cost, *move)


def plan_fuel(
    candidates: list[FuelCandidate],
    total_distance_miles: float,
    tank_capacity_gallons: float,
    miles_per_gallon: float,
    start_fuel_gallons: float = 0.0,
    cost_per_stop: float = 0.0,
    fuel_reserve_gallons: float = 0.0,
) -> FuelPlan:
    usable_gallons = tank_capacity_gallons - fuel_reserve_gallons
    usable_start_gallons = start_fuel_gallons - fuel_reserve_gallons
    usable_miles = usable_gallons * miles_per_gallon
    nodes = _undominated_candidates(candidates)
    if not nodes or nodes[0].mile_marker > 0 or nodes[0].offset_miles > 0:
        start = FuelCandidate(station=None, mile_marker=0.0, price_per_gallon=NO_FUEL_FOR_SALE)
        nodes.insert(0, start)
    destination = FuelCandidate(
        station=None, mile_marker=total_distance_miles, price_per_gallon=Decimal("0")
    )
    nodes.append(destination)
    _check_reachable(
        nodes, usable_miles, miles_per_gallon, usable_start_gallons, fuel_reserve_gallons
    )

    miles = [node.mile_marker for node in nodes]
    offsets = [node.offset_miles for node in nodes]
    prices = [float(node.price_per_gallon) for node in nodes]
    last = len(nodes) - 1
    states: list[dict[float, tuple[float, int, float, float]]] = [{} for _ in nodes]
    states[0][usable_start_gallons] = (0.0, -1, 0.0, 0.0)

    for index in range(last):
        price = prices[index]
        sells_fuel = price != float("inf")
        legs = []
        for target in range(index + 1, bisect_right(miles, miles[index] + usable_miles)):
            leg_miles = miles[target] - miles[index] + offsets[index] + offsets[target]
            if leg_miles <= usable_miles + EPSILON_GALLONS:
                legs.append((states[target], leg_miles / miles_per_gallon, target < last))
        for arrival, (cost, *_) in states[index].items():
            fill = usable_gallons - arrival
            fill_cost = cost + fill * price + cost_per_stop
            can_fill = sells_fuel and fill > EPSILON_GALLONS
            for bucket, needed, before_destination in legs:
                shortfall = needed - arrival
                if shortfall > EPSILON_GALLONS:
                    if sells_fuel:
                        _offer(
                            bucket,
                            0.0,
                            cost + shortfall * price + cost_per_stop,
                            (index, arrival, shortfall),
                        )
                elif shortfall >= -EPSILON_GALLONS or index == 0:
                    _offer(bucket, max(-shortfall, 0.0), cost, (index, arrival, 0.0))
                if can_fill and before_destination:
                    _offer(bucket, usable_gallons - needed, fill_cost, (index, arrival, fill))

    if not states[last]:
        raise UnreachableRoute(
            "no fuel plan reaches the destination once detours to off-route stations are counted"
        )

    key = min(states[last], key=lambda fuel: states[last][fuel][0])
    purchases: list[tuple[int, float]] = []
    index = last
    while True:
        _, previous_index, previous_key, bought = states[index][key]
        if previous_index < 0:
            break
        if bought > EPSILON_GALLONS:
            purchases.append((previous_index, bought))
        index, key = previous_index, previous_key

    stops: list[FuelStop] = []
    for node_index, bought in reversed(purchases):
        node = nodes[node_index]
        gallons = round(bought, 6)
        stops.append(
            FuelStop(
                station=node.station,
                mile_marker=node.mile_marker,
                gallons=gallons,
                price_per_gallon=node.price_per_gallon,
                cost=Decimal(str(gallons)) * node.price_per_gallon,
                offset_miles=node.offset_miles,
            )
        )

    total_gallons = sum(stop.gallons for stop in stops)
    total_cost = sum((stop.cost for stop in stops), Decimal("0"))
    return FuelPlan(stops=stops, total_gallons=total_gallons, total_cost=total_cost)
