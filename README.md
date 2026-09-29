# Fuel Route Planner

![CI](https://github.com/sonu-antony/fuel-route-planner/actions/workflows/ci.yml/badge.svg)

A Django REST API that takes a start and finish location in the USA, returns the driving
route, the cost-optimal fuel stops along it, and the total fuel cost. Given a maximum vehicle
range, it decides where to refuel and how much to buy so the total spend is minimized. It also
renders each planned trip as an interactive map.

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

The database is SQLite by default, so this runs with no extra setup. Setting `DATABASE_URL`
(e.g. `postgres://user:pass@host:5432/dbname`) switches to PostgreSQL instead.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

`ruff check .` and `ruff format --check .` run
alongside `pytest` in CI (`.github/workflows/ci.yml`).

## API reference

### `POST /api/v1/trips/plan/`

Request body:

```json
{ "start": "Chicago, IL", "finish": "Denver, CO", "start_fuel_gallons": 0 }
```

`start` and `finish` accept either a `"City, ST"` string or a raw `"lat,lng"` coordinate pair.
`start_fuel_gallons` is optional (0–50, default 0) and represents fuel already in the tank.

Response `200`:

```json
{
  "id": "5b1f2c3a-...-e9a4",
  "start": { "query": "Chicago, IL", "lat": 41.8781, "lng": -87.6298 },
  "finish": { "query": "Denver, CO", "lat": 39.7392, "lng": -104.9903 },
  "distance_miles": 1003.4,
  "total_gallons": 100.34,
  "total_cost": 338.12,
  "fuel_stops": [
    {
      "station_id": 105,
      "name": "PILOT #1243",
      "address": "I-8, EXIT 119 & SR-85",
      "city": "Gila Bend",
      "state": "AZ",
      "mile_marker": 0.0,
      "price_per_gallon": 3.269,
      "gallons": 50.0,
      "cost": 163.45
    }
  ],
  "route": {
    "type": "FeatureCollection",
    "features": ["... one route LineString, one Point per fuel stop ..."]
  },
  "map_url": "http://host/trips/5b1f2c3a-.../map/",
  "meta": { "routing_calls": 1, "cached": false, "elapsed_ms": 136.0 }
}
```

A repeated request (same start, finish and starting fuel) returns the same trip from cache,
with `meta.routing_calls: 0` and `meta.cached: true`.

### `GET /trips/<uuid>/map/`

Renders the saved trip on a Leaflet map — the route line and a numbered marker per fuel stop,
each with a popup showing name, price and gallons bought. Reads the saved `TripPlan`, so it
makes no routing call.

### Errors

Every error response has the shape `{"error": "<code>", "detail": "..."}`.

| Status | `error`                | Cause                                         |
| ------ | ---------------------- | ---------------------------------------------- |
| 400    | `validation_error`     | missing field, `start == finish`, fuel outside 0–50 |
| 404    | `location_not_found`   | start or finish could not be resolved          |
| 422    | `location_outside_usa` | resolved coordinates are outside the continental USA |
| 422    | `unreachable_route`    | a gap between stations exceeds the range, or the first station is beyond the starting fuel; `detail` says where, and how much `start_fuel_gallons` would fix it |
| 502    | `routing_unavailable`  | the routing provider timed out, errored, or returned no route |

## The approach: corridor search + dynamic-programming refueling

In one line: **ask the routing API once for the road, find every priced station within a
narrow corridor of that road, then pick the stops and gallons that minimize fuel spend plus a
small fixed cost per stop.**

1. **Resolve locations locally.** `start`/`finish` are parsed as `"lat,lng"` or looked up in a
   bundled US cities table (`stations/services/city_lookup.py`). No geocoding API is called.
2. **Check the cache.** Start, finish and starting fuel (case, spacing and comma spacing
   normalized) form the cache key. A hit returns the saved `TripPlan` with zero routing calls.
3. **One routing call.** On a miss, `trips/services/routing_client.py` calls OpenRouteService
   once for the route line, distance and duration.
4. **Corridor search.** The route is resampled every `ROUTE_SAMPLE_MILES` miles
   (`trips/services/geometry.py`). A KD-tree over all stations, built once per process
   (`stations/services/spatial_index.py`), returns every station within `CORRIDOR_MILES` of any
   sample point. Each station gets the mile marker of its nearest sample point. The station
   nearest the start is treated as the first fill-up at mile 0, but only if it is within
   `CORRIDOR_MILES` of the start.
5. **Refueling plan** (`trips/services/fuel_planner.py`). A dynamic program over
   (station, fuel on arrival). At each stop the truck either fills the tank or buys just
   enough to reach the next stop empty; for a fixed set of stops one of those two is always
   optimal, so the search is exact while only trying a handful of fuel levels per station.
   Each stop also costs `FUEL_STOP_COST` (default $5, standing in for the driver's time), so
   the plan skips "drive 2 miles to save 3 cents" stops. The destination counts as a free
   station, so the tank ends empty. `trips/tests/test_fuel_planner.py` checks the plan against
   a brute-force solver on 200 random routes, both with and without a stop cost.
6. **Save and cache.** Stops, totals and the route GeoJSON are saved as a `TripPlan` (which the
   map page reads) and cached for `TRIP_CACHE_SECONDS`.

## Design choices and tradeoffs

| Choice | Why | Tradeoff |
| --- | --- | --- |
| Geocode stations by city and state, offline, and commit the result | ~60% of addresses are highway exits (`I-44, EXIT 283`) that street geocoders miss; offline means zero geocoding calls per request | Station positions are accurate to a few miles, not to the exact pump |
| 10-mile corridor around the route | Compensates for city-level station positions | Stations up to 10 miles off the road count as "on the route"; detour distance is not charged |
| Mile marker = nearest resampled point (every 2 miles) | Simple and fast | Mile markers are approximate to about ±1 mile |
| Dynamic program with a $5 cost per stop | Pure cheapest-fuel planning (the classic greedy) is exact but produces impractical plans: Chicago → Denver had 9 stops, some buying 0.2 gal to reach a station 2 miles on. The stop cost cuts that to 4 stops for 92¢ more; LA → NY (50 gal at start) goes from 17 to 6 stops for $7 (1%) more | Adds about 0.2 s of planning on a 2,800-mile route. `total_cost` is fuel only; set `FUEL_STOP_COST=0` for the strictly cheapest plan. Optimal only among stations near *this* route |
| Plan to exactly 500 miles of range | Matches the assignment's stated range | No safety margin: a full-range leg plus a detour could run dry in reality |
| One routing call, cached, plus a saved plan for the map | Meets "call the routing API as little as possible"; the map costs nothing extra | The cache and the KD-tree live in each process's memory; several workers would need a shared cache and PostGIS |
| OpenRouteService `driving-hgv` (truck) profile, no fallback | Free, and truck-legal roads suit a fleet use case | A route beyond ORS's distance limit for this profile would fail with `routing_unavailable`; a 2,796-mile Los Angeles → New York route works |
| Full route line returned in the response | The client can draw the exact route | A cross-country response can be several hundred KB; simplifying the line would shrink it |
| KD-tree (scipy) for the station search | Standard, fast nearest-neighbour search over all 6,626 stations | Adds numpy/scipy; plain numpy distances would also be fast enough at this data size |

**Assumptions**

- The truck starts with an empty tank and fills up at the station nearest the start. If no
  station is within `CORRIDOR_MILES` of the start, the trip needs `start_fuel_gallons` to reach
  the first station, otherwise it returns `unreachable_route`. This matters in California: the
  price file has only 8 CA stations, all near the Mexican border, so a trip from Los Angeles
  needs at least 24.4 gallons to reach the first station, 244 miles away in Nevada.
- Fuel can be bought in any fractional amount.
- When a station ID appears more than once in the price file, the lowest price is kept.
- Canadian stations are excluded; the assignment is USA-only.
- Range, mpg, corridor width, sample spacing, per-stop cost, routing timeout and cache
  lifetime are configurable in `.env` (defaults: 500-mile range, 10 mpg, $5 per stop).

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
- **0** geocoding calls at request time — station geocoding is a one-time offline step, and
  start/finish resolution uses the same local city table.

## Measured response times

Against the full 6,626-station database, with a live OpenRouteService key:

| Trip | Distance | Stops | Cold | Cached |
| --- | --- | --- | --- | --- |
| Dallas → Houston | 240 mi | 1 | 1.1 s | < 10 ms |
| Chicago → Denver | 1,008 mi | 4 | 1.6 s | < 10 ms |
| Phoenix → Atlanta | 1,828 mi | 5 | 2.0 s | < 10 ms |
| Los Angeles → New York (25 gal at start) | 2,796 mi | 7 | 2.6 s | < 10 ms |

Most of a cold request is the OpenRouteService round trip. With that call mocked, this
service's own work on Los Angeles → New York (resampling the route, the KD-tree corridor
search, the fuel plan and the database write) takes about 260 ms, including building the
spatial index; a cached request takes about 5 ms.

## What I would do next

- Real street-level geocoding for the handful of stations currently resolved to a city
  centroid, and for all stations if a paid geocoder were available.
- Time-of-day fuel prices instead of a single static price per station.
- Factor detour distance (station off the route line) into the cost comparison, not just the
  corridor-inclusion radius, and keep a configurable fuel reserve instead of planning to an
  empty tank.
- Simplify the returned route line to shrink cross-country responses.
- A hard wall-clock deadline on the routing call. `ROUTING_TIMEOUT_SECONDS` bounds each
  socket read, not the whole request, and one live test stalled for minutes before returning
  `routing_unavailable`.
- PostGIS for the spatial index and a shared cache (e.g. Redis) instead of per-process memory,
  so it works correctly across multiple app workers.

## Data credits

- `data/fuel-prices-for-be-assessment.csv`: provided as part of the assessment.
- `data/us_cities.csv`: trimmed from the [US-Cities-Database](https://github.com/kelvins/US-Cities-Database)
  by Kelvin S. do Prado (MIT License), 29,880 US cities with state and coordinates.
- The handful of stations that dataset didn't cover were geocoded with
  [Nominatim](https://nominatim.openstreetmap.org/) (OpenStreetMap data, ODbL) via
  `geocode_stations --nominatim-fallback`, a one-time data-preparation step.
