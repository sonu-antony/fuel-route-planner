# Fuel Route Planner

![CI](https://github.com/sonu-antony/fuel-route-planner/actions/workflows/ci.yml/badge.svg)

A Django REST API that takes a start and finish location in the continental USA (a city name
or coordinates) and returns the driving route, the cost-optimal fuel stops along it, and the
total fuel cost. Given the vehicle's 500-mile range, it decides where to refuel and how much to
buy so the total spend is minimized, counting the fuel burned on detours to each station and
never letting the tank drop below a 5-gallon reserve. It also renders each trip as an
interactive map, with the detours drawn in.

The approach is **corridor search + dynamic-programming refueling**, with one routing API call
per new trip. See [The approach](#the-approach-corridor-search--dynamic-programming-refueling)
and [Design choices and tradeoffs](#design-choices-and-tradeoffs).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your OpenRouteService key to ORS_API_KEY
python manage.py migrate
python manage.py load_stations
python manage.py runserver
```

`load_stations` loads the already-geocoded `data/stations_geocoded.csv` (committed in the
repo) and requires no network access. `geocode_stations`, which produced that file from the
raw price list, is a one-time data-preparation command; you do not need to run it.

The database is SQLite, so this runs with no extra setup.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

`ruff check .` and `ruff format --check .` run alongside `pytest` in CI
(`.github/workflows/ci.yml`).

## API reference

### `POST /api/v1/trips/plan/`

Request body:

```json
{ "start": "Chicago, IL", "finish": "Denver, CO", "start_fuel_gallons": 0 }
```

`start` and `finish` accept either a `"City, ST"` string or a raw `"lat,lng"` coordinate pair.
`start_fuel_gallons` is optional (0–50, default 0) and represents fuel already in the tank.
With an empty tank the trip begins at the station nearest the start, so it needs a station
within 10 miles of the start; otherwise the fuel must cover the drive to the first station
plus the 5-gallon reserve (see **Assumptions**).

Response `200` (Chicago → Denver, trimmed to two of its five stops):

```json
{
  "id": "5b1f2c3a-...-e9a4",
  "start": { "query": "Chicago, IL", "lat": 41.8781, "lng": -87.6298 },
  "finish": { "query": "Denver, CO", "lat": 39.7392, "lng": -104.9903 },
  "distance_miles": 1007.5,
  "gallons_purchased": 107.623,
  "total_cost": 317.96,
  "fuel_stops": [
    {
      "station_id": 73127,
      "name": "Gas N Wash",
      "address": "I-55, EXIT 285",
      "city": "Chicago",
      "state": "IL",
      "mile_marker": 0.0,
      "off_route_miles": 0.0,
      "price_per_gallon": 3.399,
      "gallons": 6.484,
      "cost": 22.04
    },
    {
      "station_id": 68368,
      "name": "AKAL TRAVEL CENTER",
      "address": "I-80 EX 360",
      "city": "Waco",
      "state": "NE",
      "mile_marker": 560.0,
      "off_route_miles": 6.8,
      "price_per_gallon": 2.799,
      "gallons": 45.0,
      "cost": 125.96
    }
  ],
  "route": {
    "type": "FeatureCollection",
    "features": ["... the route LineString, a Point per fuel stop, a detour LineString per off-route stop ..."]
  },
  "map_url": "http://host/trips/5b1f2c3a-.../map/",
  "meta": { "routing_calls": 1, "cached": false, "elapsed_ms": 1581.8 }
}
```

- `station_id` is the station's OPIS ID from the price file.
- `mile_marker` is how far along the route the station sits; `off_route_miles` is its
  one-way, straight-line distance from the route. The plan charges the round trip, so a stop
  0.9 miles off the route costs 1.8 miles of fuel.
- `gallons_purchased` and `total_cost` cover fuel bought on the trip, including the fuel
  burned on detours to stations and the reserve the truck still carries at the finish. Fuel
  already in the tank (`start_fuel_gallons`) is not counted.
- Each stop reads like a pump receipt: gallons to 3 decimals, cost to the cent. The totals are
  the sum of those receipts, so they always add up, and a cached response reports exactly
  the same figures.

A repeated request (same start, finish and starting fuel, under the same planning settings)
returns the same trip from cache, with `meta.routing_calls: 0` and `meta.cached: true`.

### `GET /trips/<uuid>/map/`

Renders the saved trip on a Leaflet map over OpenStreetMap tiles: the route line, green (S)
and red (F) pins for start and finish, and a numbered pin per fuel stop. A dashed line runs
from each off-route stop to the route point its offset was measured from, and the stop's popup
gives both figures (e.g. "0.9 mi off route · 1.8 mi round-trip detour"). The route itself is
not re-drawn through the stops, since that would take a second routing call. Pins mark the
station's town, not the exact pump, because stations are geocoded by city (see
[Data preparation](#data-preparation)); a station whose address names a highway exit can
appear a mile or so from the road it actually sits on.

A side panel shows the distance, gallons bought and total cost, and lists each stop with what
to buy there; clicking a stop in the list zooms to its pin. The page reads the saved
`TripPlan`, so it makes no routing call.

### Errors

Every error response has the shape `{"error": "<code>", "detail": "..."}`.

| Status | `error`                | Cause                                         |
| ------ | ---------------------- | ---------------------------------------------- |
| 400    | `validation_error`     | missing field, fuel outside 0–50, or start and finish resolve to the same point |
| 404    | `location_not_found`   | start or finish could not be resolved          |
| 422    | `location_outside_usa` | resolved coordinates are outside the continental USA |
| 422    | `unreachable_route`    | a gap between stations exceeds the range left above the fuel reserve, or the first station is beyond the starting fuel; `detail` says where, and how much `start_fuel_gallons` would fix it |
| 502    | `routing_unavailable`  | the routing provider timed out, returned an error status (e.g. 429), returned a malformed payload, or `ORS_API_KEY` is not set; `detail` says which |

## The approach: corridor search + dynamic-programming refueling

In one line: **ask the routing API once for the road, find every priced station within a
narrow corridor of that road, then pick the stops and gallons that minimize the money spent on
fuel, including the fuel burned driving off the road to each station, while always keeping a
5-gallon reserve in the tank.**

1. **Resolve locations locally.** `start`/`finish` are parsed as `"lat,lng"` or looked up in a
   bundled US cities table (`stations/services/city_lookup.py`). No geocoding API is called.
2. **Check the cache.** Start, finish and starting fuel (case, spacing and comma spacing
   normalized) plus the planning settings form the cache key. A hit returns the saved
   `TripPlan` with zero routing calls.
3. **One routing call.** On a miss, `trips/services/routing_client.py` calls OpenRouteService
   (`api.heigit.org`) once for the route line, distance and duration. A malformed or failed
   response becomes a 502; there is no retry, since a retry would spend a second call.
4. **Corridor search.** The route is resampled every `ROUTE_SAMPLE_MILES` miles
   (`trips/services/geometry.py`). A KD-tree over all stations, built once per process
   (`stations/services/spatial_index.py`), returns every station within `CORRIDOR_MILES` of any
   sample point. Each station gets the mile marker of its nearest sample point and its
   off-route distance from that point. If a station is within `CORRIDOR_MILES` of the start,
   the trip begins at that station (the cheapest one if several share the nearest location,
   as stations geocoded to the same city do), placed at mile 0 with no off-route distance.
   Otherwise the trip begins at the requested start point (see **Assumptions** below).
5. **Refueling plan** (`trips/services/fuel_planner.py`). A dynamic program over
   (station, fuel on arrival). Driving from stop A to stop B costs the route miles between
   them plus A's and B's off-route distances. The truck never lets the tank fall below
   `FUEL_RESERVE_GALLONS` (default 5), so the planner works with the fuel above the reserve:
   45 usable gallons, 450 miles per leg. At each stop the truck either fills the tank or buys
   just enough to reach the next stop with only the reserve left; for a fixed set of stops one
   of those two is always optimal, so the search is exact while only trying a handful of fuel
   levels per station. The destination counts as a free station, so the truck arrives with
   exactly the reserve.
   `trips/tests/test_fuel_planner.py` checks the plan against a brute-force solver on 200
   random routes with off-route stations, with and without a reserve. The plan is optimal
   under this corridor model: the stations it knows about, their mile markers and
   straight-line detours. It is not a road-level optimum across alternative routes.
6. **Save and cache.** Stops, totals and the route GeoJSON are saved as a `TripPlan` (which the
   map page reads) and cached for `TRIP_CACHE_SECONDS`.

## Design choices and tradeoffs

| Choice | Why | Tradeoff |
| --- | --- | --- |
| Geocode stations by city and state once, ahead of time, and commit the result | ~60% of addresses are highway exits (`I-44, EXIT 283`) that street geocoders miss; doing it ahead of time means zero geocoding calls per request | Station positions are accurate to a few miles, not to the exact pump |
| 10-mile corridor around the route, with the detour charged | Compensates for city-level station positions, while a station 8 miles off the road still costs 16 miles of fuel to use, so it is only chosen when it pays for itself | The detour is straight-line distance to the nearest sample point, not road distance; the truck is assumed to rejoin the route where it left it |
| Mile marker = nearest resampled point (every 2 miles) | Simple and fast | Mile markers are approximate to about ±1 mile |
| Dynamic program over (station, fuel on arrival) instead of the classic greedy | The greedy is exact only when stations sit on the route. Once detours cost fuel it is not, and the DP stays exact (verified against brute force). Ignoring detours also produced impractical plans: Chicago → Denver had 9 stops, some buying 0.2 gal to reach a station 2 miles on; with detours charged it has 4 (5 with the fuel reserve, which forces one top-up) | About 0.3 s of planning on a 2,800-mile route. Optimal only among stations near *this* route. `FUEL_STOP_COST` (default 0) can add a fixed cost per stop if fewer stops matter more than cents |
| Keep a 5-gallon reserve at every stop and at the finish | Arriving at a pump with exactly zero is unrealistic, and the detours are straight-line and station positions city-level, so a buffer covers the difference | Each leg is at most 450 miles, which sometimes forces a small top-up: Chicago → Denver buys 0.5 gal at Brighton because Waco → Denver is 454 miles. `total_cost` includes buying the reserve, which is still in the tank at the end |
| One routing call, cached, plus a saved plan for the map | Meets "call the routing API as little as possible"; the map costs nothing extra | The cache and the KD-tree live in each process's memory; several workers would need a shared cache and PostGIS |
| OpenRouteService `driving-hgv` (truck) profile, one call, no retry or fallback | Free, and truck-legal roads suit a fleet use case; a retry or fallback would spend a second call | A transient provider failure returns a 502; the service does not retry, so the caller must. ORS caps driving routes at 6,000 km; the longest continental US routes (Los Angeles → New York is 4,500 km) fit |
| Full route line returned in the response | The client can draw the exact route | A cross-country response can be several hundred KB; simplifying the line would shrink it |
| KD-tree (scipy) for the station search | Standard, fast nearest-neighbour search over all 6,626 stations | Adds numpy/scipy; plain numpy distances would also be fast enough at this data size |

**Assumptions**

- Where the trip begins depends on whether a station is near the start:
  - **A station within `CORRIDOR_MILES` of the start:** the truck begins *at* that station
    with `start_fuel_gallons` in the tank (default: empty), so it can fill up before leaving.
    The drive from the requested point to that station is not charged; with station positions
    at city level, that distance is mostly geocoding noise.
  - **No station within `CORRIDOR_MILES`:** the truck begins at the requested point, and
    `start_fuel_gallons` must cover the drive to the first station, including its off-route
    distance. Otherwise the API returns `unreachable_route` and says how many gallons are
    needed. This matters in California: the price file has only 8 CA stations, all near the
    Mexican border, so a trip from Los Angeles needs at least 30.3 gallons: 25.3 to reach the
    first station, 244 miles along the route and 9 miles off it in Nevada, plus the 5-gallon
    reserve.
- Fuel can be bought in any fractional amount.
- When a station ID appears more than once in the price file, the lowest price is kept.
- Canadian stations are excluded; the assignment is USA-only.
- Range, mpg, fuel reserve, corridor width, sample spacing, per-stop cost, routing timeout and
  cache lifetime are configurable in `.env` (defaults: 500-mile range, 10 mpg, 5-gallon
  reserve, no per-stop cost).
  They are checked at startup: a zero, negative or non-numeric value, or a reserve as large
  as the tank, stops the server with an error naming the setting (`config/env.py`).

## Data preparation

The raw `fuel-prices-for-be-assessment.csv` (8,151 rows) has ~60% highway-exit style
addresses (e.g. `I-44, EXIT 283 & US-69`) that street geocoders handle badly, so stations are
geocoded by **city and state** instead, against a trimmed 29,880-row US cities table (see
[Data credits](#data-credits)).

Running `geocode_stations` against the full file: **6,626** of **6,626** cleaned, deduplicated,
US-only stations matched — **6,620** against the local city table and the remaining
**6** (small towns absent from that table: Brookpark OH, Elizabethport NJ, Evergreen AL,
Henrico VA, Port Wentworth GA, University Park IL) via the one-time
`--nominatim-fallback` flag. The output is committed as `data/stations_geocoded.csv`, so
reviewers only need to run `load_stations`, which touches no network.

## External call budget

- **1** routing API call per new trip.
- **0** routing API calls per cached trip (identical start/finish/starting-fuel).
- **0** routing API calls for the map view (reads the saved trip).
- **0** geocoding calls at request time — station geocoding is a one-time preparation step,
  and start/finish resolution uses the same local city table.

## Measured response times

Against the full 6,626-station database, with a live OpenRouteService key:

| Trip | Distance | Stops | Cold | Cached |
| --- | --- | --- | --- | --- |
| Dallas → Houston | 240 mi | 2 | 1.0 s | < 10 ms |
| Chicago → Denver | 1,008 mi | 5 | 1.4 s | < 10 ms |
| Phoenix → Atlanta | 1,828 mi | 6 | 1.9 s | < 10 ms |
| Los Angeles → New York (40 gal at start) | 2,796 mi | 9 | 2.1 s | < 10 ms |

Most of a cold request is the OpenRouteService round trip. With that call mocked, this
service's own work on Los Angeles → New York (resampling the route, the KD-tree corridor
search, the fuel plan and the database write) takes about 320 ms, including building the
spatial index; a cached request takes about 5 ms.

## What I would do next

- Road-distance detours to stations (one matrix call per trip) instead of straight-line
  distance.
- Street-level geocoding for stations, which would also allow a narrower corridor.
- A hard wall-clock deadline on the routing call. `ROUTING_TIMEOUT_SECONDS` bounds each
  socket read, not the whole request, and one live test stalled for minutes before returning
  `routing_unavailable`.
- Invalidate cached trips when station prices change. The cache key includes the planning
  settings, but not a data version; it works today because the cache lives in the server's
  memory and a `load_stations` reload needs a server restart, which clears it. A shared cache
  would need a data version in the key.
- Coalesce identical requests that miss the cache at the same moment; today each makes its
  own routing call.
- Production settings. The current ones are local-development defaults (`DEBUG` on, a fallback
  `SECRET_KEY`, no HTTPS headers, so `manage.py check --deploy` warns). Production needs those
  fixed, plus a shared cache and PostGIS so several app workers share one index.
- Simplify the returned route line to shrink cross-country responses.

## Data credits

- `data/fuel-prices-for-be-assessment.csv`: provided as part of the assessment.
- `data/us_cities.csv`: trimmed from the [US-Cities-Database](https://github.com/kelvins/US-Cities-Database)
  by Kelvin S. do Prado (MIT License), 29,880 US cities with state and coordinates.
- The handful of stations that dataset didn't cover were geocoded with
  [Nominatim](https://nominatim.openstreetmap.org/) (OpenStreetMap data, ODbL) via
  `geocode_stations --nominatim-fallback`, a one-time data-preparation step.
