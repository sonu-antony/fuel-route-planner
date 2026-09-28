# Fuel Route Planner

![CI](https://github.com/silentwraith7/fuel-route-planner/actions/workflows/ci.yml/badge.svg)

A Django REST API that takes a start and finish location in the USA, returns the driving
route, the cost-optimal fuel stops along it, and the total fuel cost. Given a maximum vehicle
range, it decides where to refuel and how much to buy so the total spend is minimized. It also
renders each planned trip as an interactive map.

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
| 422    | `unreachable_route`    | a gap between fuel stops exceeds vehicle range |
| 502    | `routing_unavailable`  | the routing provider timed out, errored, or returned no route |

## How it works

1. **Resolution** — `start`/`finish` are parsed as raw coordinates or resolved to a city
   centroid via a local lookup table (`stations/services/city_lookup.py`), so this step never
   makes a network call.
2. **Caching** — the (start, finish, starting fuel) triple is hashed into a cache key. A hit
   returns the previously saved `TripPlan` with zero routing calls.
3. **One routing call** — on a cache miss, `trips/services/routing_client.py` makes exactly
   one call to OpenRouteService for the route geometry, distance and duration.
4. **Corridor search** — the route is resampled every `ROUTE_SAMPLE_MILES` miles
   (`trips/services/geometry.py`), and a KD-tree built once per process over all stations'
   3D unit-sphere coordinates (`stations/services/spatial_index.py`) finds every station within
   `CORRIDOR_MILES` of the route in one query. Chord distance on the unit sphere maps exactly
   to great-circle distance, so this is an exact radius search, not an approximation.
5. **Greedy fuel planner** — `trips/services/fuel_planner.py` walks the corridor stations in
   order. At each stop: if a cheaper station lies within one tank's range, buy just enough to
   reach it; otherwise fill the tank and jump to the cheapest station within range. This is the
   classic "gas station problem" greedy strategy, and it is provably cost-optimal for a fixed
   route and fixed tank capacity — a station is only skipped when a full tank guarantees
   reaching something cheaper or equally reachable, so no purchase is ever made at a price that
   a cheaper, reachable alternative could have avoided. `trips/tests/test_fuel_planner.py`
   checks this directly: on 200 random small routes, the greedy cost is compared against a
   brute-force dynamic-programming solver over every (station, fuel-level) state, and the two
   always agree.
6. **Save and cache** — the resulting stops, totals and route GeoJSON are saved as a
   `TripPlan` and the cache is populated for `TRIP_CACHE_SECONDS`.

## Assumptions

- The truck starts with an empty tank and buys fuel at the station nearest the trip's start
  point (the optional `start_fuel_gallons` field overrides this).
- Fuel is bought in any fractional amount.
- When the same station ID appears more than once in the source price file, the lowest price
  is kept.
- Stations in Canadian provinces are excluded (the assignment is USA-only).
- Station coordinates are city-level centroids, not exact addresses (see below) — the
  `CORRIDOR_MILES` search radius is sized to compensate.
- Vehicle range, mpg, corridor width, sample spacing, routing timeout and cache lifetime are
  all environment-configurable (see `.env.example`); the defaults are a 500-mile range at
  10 mpg.

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

Measured against the full 6,626-station database (Los Angeles → New York, 2,800 miles, 18
fuel stops), with the OpenRouteService call mocked so the number reflects this service's own
processing — resampling the route, the KD-tree corridor search, the greedy fuel plan and the
database write:

| Request               | Time      | Target  |
| ---------------------- | --------- | ------- |
| Cold (builds the spatial index) | 136 ms | < 1.5 s |
| Cached                 | 1.0 ms    | < 50 ms |

In production, the cold-request time is dominated by the OpenRouteService network round trip,
which this measurement excludes.

## What I would do next

- Real street-level geocoding for the handful of stations currently resolved to a city
  centroid, and for all stations if a paid geocoder were available.
- Time-of-day fuel prices instead of a single static price per station.
- Factor detour distance (station off the route line) into the cost comparison, not just the
  corridor-inclusion radius.
- PostGIS for the spatial index instead of an in-process KD-tree, so it scales past what fits
  in one process's memory and works correctly across multiple app workers.

## Data credits

- `data/fuel-prices-for-be-assessment.csv`: provided as part of the assessment.
- `data/us_cities.csv`: trimmed from the [US-Cities-Database](https://github.com/kelvins/US-Cities-Database)
  by Kelvin S. do Prado (MIT License), 29,880 US cities with state and coordinates.
- The handful of stations that dataset didn't cover were geocoded with
  [Nominatim](https://nominatim.openstreetmap.org/) (OpenStreetMap data, ODbL) via
  `geocode_stations --nominatim-fallback`, a one-time data-preparation step.
