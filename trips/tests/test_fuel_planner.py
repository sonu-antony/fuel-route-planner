import random
from decimal import Decimal
from functools import cache

import pytest

from trips.services.fuel_planner import FuelCandidate, UnreachableRoute, plan_fuel


def candidate(station, mile_marker, price, offset_miles=0.0):
    return FuelCandidate(
        station=station,
        mile_marker=mile_marker,
        price_per_gallon=Decimal(price),
        offset_miles=offset_miles,
    )


def test_a_trip_shorter_than_the_range_with_one_station_buys_exactly_distance_over_mpg():
    candidates = [candidate("A", 0.0, "3.000")]

    plan = plan_fuel(
        candidates, total_distance_miles=100, tank_capacity_gallons=50, miles_per_gallon=10
    )

    [stop] = plan.stops
    assert stop.gallons == pytest.approx(10.0)
    assert stop.cost == Decimal("30.000")


def test_when_a_cheaper_station_lies_ahead_within_range_it_buys_just_enough_to_reach_it():
    candidates = [candidate("A", 0.0, "3.50"), candidate("B", 200.0, "3.00")]

    plan = plan_fuel(
        candidates, total_distance_miles=400, tank_capacity_gallons=50, miles_per_gallon=10
    )

    first_stop = plan.stops[0]
    assert first_stop.station == "A"
    assert first_stop.gallons == pytest.approx(20.0)


def test_when_no_cheaper_station_is_within_range_it_fills_up_and_skips_to_the_cheapest():
    candidates = [
        candidate("A", 0.0, "3.00"),
        candidate("B", 100.0, "3.50"),
        candidate("C", 450.0, "3.10"),
    ]

    plan = plan_fuel(
        candidates, total_distance_miles=900, tank_capacity_gallons=50, miles_per_gallon=10
    )

    first_stop = plan.stops[0]
    assert first_stop.station == "A"
    assert first_stop.gallons == pytest.approx(50.0)
    assert plan.stops[1].station == "C"


def test_a_gap_between_stations_longer_than_the_range_raises_unreachable_route():
    candidates = [candidate("A", 0.0, "3.00"), candidate("B", 600.0, "3.00")]

    with pytest.raises(UnreachableRoute, match="between mile 0 and mile 600"):
        plan_fuel(
            candidates, total_distance_miles=700, tank_capacity_gallons=50, miles_per_gallon=10
        )


def test_starting_fuel_that_covers_the_whole_trip_gives_zero_stops_and_zero_cost():
    candidates = [candidate("A", 0.0, "3.00")]

    plan = plan_fuel(
        candidates,
        total_distance_miles=50,
        tank_capacity_gallons=50,
        miles_per_gallon=10,
        start_fuel_gallons=10,
    )

    assert plan.stops == []
    assert plan.total_gallons == 0
    assert plan.total_cost == Decimal("0")


def test_an_empty_tank_with_the_first_station_beyond_mile_zero_raises_unreachable_route():
    candidates = [candidate("A", 150.0, "3.00")]

    with pytest.raises(UnreachableRoute, match="mile 150.*start_fuel_gallons to at least 15.0"):
        plan_fuel(
            candidates, total_distance_miles=400, tank_capacity_gallons=50, miles_per_gallon=10
        )


def test_a_route_with_no_stations_and_an_empty_tank_says_how_much_starting_fuel_it_needs():
    with pytest.raises(UnreachableRoute, match="no fuel station.*at least 10.0"):
        plan_fuel([], total_distance_miles=100, tank_capacity_gallons=50, miles_per_gallon=10)


def test_starting_fuel_carries_the_truck_to_a_first_station_beyond_mile_zero():
    candidates = [candidate("A", 150.0, "3.00")]

    plan = plan_fuel(
        candidates,
        total_distance_miles=400,
        tank_capacity_gallons=50,
        miles_per_gallon=10,
        start_fuel_gallons=20,
    )

    [stop] = plan.stops
    assert stop.station == "A"
    assert stop.gallons == pytest.approx(20.0)


def test_a_cost_per_stop_skips_a_barely_cheaper_station_just_ahead():
    candidates = [candidate("A", 0.0, "3.00"), candidate("B", 2.0, "2.99")]

    plan = plan_fuel(
        candidates,
        total_distance_miles=100,
        tank_capacity_gallons=50,
        miles_per_gallon=10,
        cost_per_stop=5,
    )

    [stop] = plan.stops
    assert stop.station == "A"
    assert stop.gallons == pytest.approx(10.0)


def test_stations_at_the_same_mile_marker_are_reduced_to_the_cheapest():
    candidates = [candidate("A", 0.0, "3.20"), candidate("B", 0.0, "3.10")]

    plan = plan_fuel(
        candidates, total_distance_miles=100, tank_capacity_gallons=50, miles_per_gallon=10
    )

    [stop] = plan.stops
    assert stop.station == "B"


def test_a_station_off_the_route_costs_the_fuel_to_drive_there_and_back():
    candidates = [candidate("A", 0.0, "3.00"), candidate("B", 50.0, "2.00", offset_miles=5.0)]

    plan = plan_fuel(
        candidates, total_distance_miles=100, tank_capacity_gallons=50, miles_per_gallon=10
    )

    assert [stop.station for stop in plan.stops] == ["A", "B"]
    assert plan.stops[0].gallons == pytest.approx(5.5)
    assert plan.total_gallons == pytest.approx(11.0)


def test_a_leg_within_range_on_route_miles_but_not_with_its_detour_is_unreachable():
    candidates = [candidate("A", 0.0, "3.00"), candidate("B", 495.0, "3.00", offset_miles=10.0)]

    with pytest.raises(UnreachableRoute):
        plan_fuel(
            candidates, total_distance_miles=900, tank_capacity_gallons=50, miles_per_gallon=10
        )


def test_a_cheaper_station_off_the_route_at_the_start_is_reached_by_buying_fuel_first():
    candidates = [candidate("A", 0.0, "3.00"), candidate("B", 0.0, "2.50", offset_miles=8.0)]

    plan = plan_fuel(
        candidates, total_distance_miles=100, tank_capacity_gallons=50, miles_per_gallon=10
    )

    assert plan.stops[0].station == "A"
    assert plan.stops[0].gallons == pytest.approx(0.8)
    assert plan.stops[1].station == "B"


def test_starting_fuel_must_cover_the_approach_to_an_off_route_first_station():
    candidates = [candidate("A", 40.0, "3.00", offset_miles=3.0)]
    arguments = {"total_distance_miles": 100, "tank_capacity_gallons": 50, "miles_per_gallon": 10}

    with pytest.raises(UnreachableRoute, match="at least 4.3"):
        plan_fuel(candidates, start_fuel_gallons=4.2, **arguments)

    plan = plan_fuel(candidates, start_fuel_gallons=4.3, **arguments)
    [stop] = plan.stops
    assert stop.station == "A"
    assert stop.gallons == pytest.approx(6.3)


def brute_force_min_cost(stations, destination_mile, tank_capacity, start_fuel, cost_per_stop):
    @cache
    def min_cost_from(index, fuel):
        best = None
        mile, price, offset = stations[index]
        for buy in range(0, tank_capacity - fuel + 1):
            new_fuel = fuel + buy
            buy_cost = buy * price + (cost_per_stop if buy > 0 else 0)
            if destination_mile - mile + offset <= new_fuel and (best is None or buy_cost < best):
                best = buy_cost
            for j in range(index + 1, len(stations)):
                next_mile, _, next_offset = stations[j]
                needed = next_mile - mile + offset + next_offset
                if needed > new_fuel:
                    continue
                sub = min_cost_from(j, new_fuel - needed)
                if sub is not None:
                    total = buy_cost + sub
                    if best is None or total < best:
                        best = total
        return best

    return min_cost_from(0, start_fuel)


def generate_route(rng, tank_capacity):
    mile = 0
    stations = [(0, rng.randint(1, 9), 0)]
    for _ in range(rng.randint(0, 4)):
        mile += rng.randint(1, tank_capacity)
        stations.append((mile, rng.randint(1, 9), rng.randint(0, 2)))
    destination_mile = mile + rng.randint(1, tank_capacity)
    return stations, destination_mile


def replay_tank_levels(
    plan, total_distance_miles, tank_capacity_gallons, miles_per_gallon, start_fuel_gallons
):
    fuel = start_fuel_gallons
    position = 0.0
    offset = 0.0
    levels = []
    for stop in plan.stops:
        fuel -= (stop.mile_marker - position + offset + stop.offset_miles) / miles_per_gallon
        levels.append(fuel)
        fuel += stop.gallons
        levels.append(fuel)
        position = stop.mile_marker
        offset = stop.offset_miles
    fuel -= (total_distance_miles - position + offset) / miles_per_gallon
    levels.append(fuel)
    return levels


@pytest.mark.parametrize("cost_per_stop", [0, 3])
def test_plan_matches_brute_force_and_holds_its_invariants_on_random_routes(cost_per_stop):
    rng = random.Random(20260101)
    tank_capacity = 10

    for _ in range(200):
        stations, destination_mile = generate_route(rng, tank_capacity)
        candidates = [
            candidate(f"S{i}", float(mile), str(price), float(offset))
            for i, (mile, price, offset) in enumerate(stations)
        ]
        arguments = {
            "total_distance_miles": float(destination_mile),
            "tank_capacity_gallons": float(tank_capacity),
            "miles_per_gallon": 1.0,
            "cost_per_stop": cost_per_stop,
        }

        expected_cost = brute_force_min_cost(
            stations, destination_mile, tank_capacity, start_fuel=0, cost_per_stop=cost_per_stop
        )
        if expected_cost is None:
            with pytest.raises(UnreachableRoute):
                plan_fuel(candidates, **arguments)
            continue

        plan = plan_fuel(candidates, **arguments)
        assert plan.total_cost + cost_per_stop * len(plan.stops) == Decimal(expected_cost)

        detour_miles = sum(2 * stop.offset_miles for stop in plan.stops)
        assert plan.total_gallons == pytest.approx(destination_mile + detour_miles)
        assert plan.total_cost == sum((stop.cost for stop in plan.stops), Decimal("0"))

        levels = replay_tank_levels(plan, float(destination_mile), float(tank_capacity), 1.0, 0.0)
        assert all(level >= -1e-9 for level in levels)
        assert all(level <= tank_capacity + 1e-9 for level in levels)
