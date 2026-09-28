from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from trips.exceptions import UnreachableRoute

__all__ = ["FuelCandidate", "FuelPlan", "FuelStop", "UnreachableRoute", "plan_fuel"]

NO_FUEL_FOR_SALE = Decimal("Infinity")


@dataclass(frozen=True)
class FuelCandidate:
    station: Any
    mile_marker: float
    price_per_gallon: Decimal


@dataclass(frozen=True)
class FuelStop:
    station: Any
    mile_marker: float
    gallons: float
    price_per_gallon: Decimal
    cost: Decimal


@dataclass(frozen=True)
class FuelPlan:
    stops: list[FuelStop]
    total_gallons: float
    total_cost: Decimal


def plan_fuel(
    candidates: list[FuelCandidate],
    total_distance_miles: float,
    tank_capacity_gallons: float,
    miles_per_gallon: float,
    start_fuel_gallons: float = 0.0,
) -> FuelPlan:
    tank_capacity_miles = tank_capacity_gallons * miles_per_gallon
    destination = FuelCandidate(
        station=None, mile_marker=total_distance_miles, price_per_gallon=Decimal("0")
    )
    nodes = sorted(candidates, key=lambda candidate: candidate.mile_marker)
    if not nodes or nodes[0].mile_marker > 0:
        start = FuelCandidate(station=None, mile_marker=0.0, price_per_gallon=NO_FUEL_FOR_SALE)
        nodes.insert(0, start)
    nodes.append(destination)

    current_fuel = start_fuel_gallons
    stops: list[FuelStop] = []
    index = 0

    while index < len(nodes) - 1:
        node = nodes[index]
        horizon = node.mile_marker + tank_capacity_miles
        reachable = [(i, n) for i, n in enumerate(nodes) if i > index and n.mile_marker <= horizon]
        if not reachable:
            raise UnreachableRoute(f"no station reachable from mile {node.mile_marker}")

        cheaper_ahead = [
            pair for pair in reachable if pair[1].price_per_gallon < node.price_per_gallon
        ]
        if cheaper_ahead:
            target_index, target = cheaper_ahead[0]
            needed = (target.mile_marker - node.mile_marker) / miles_per_gallon
            buy = max(0.0, needed - current_fuel)
        else:
            target_index, target = min(reachable, key=lambda pair: pair[1].price_per_gallon)
            buy = tank_capacity_gallons - current_fuel

        if buy > 0 and node.price_per_gallon == NO_FUEL_FOR_SALE:
            raise UnreachableRoute("not enough starting fuel to reach the first station")
        if buy > 0:
            gallons = round(buy, 6)
            cost = Decimal(str(gallons)) * node.price_per_gallon
            stops.append(
                FuelStop(
                    station=node.station,
                    mile_marker=node.mile_marker,
                    gallons=gallons,
                    price_per_gallon=node.price_per_gallon,
                    cost=cost,
                )
            )
            current_fuel += gallons

        distance = target.mile_marker - node.mile_marker
        current_fuel -= distance / miles_per_gallon
        index = target_index

    total_gallons = sum(stop.gallons for stop in stops)
    total_cost = sum((stop.cost for stop in stops), Decimal("0"))
    return FuelPlan(stops=stops, total_gallons=total_gallons, total_cost=total_cost)
