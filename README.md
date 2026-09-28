# Fuel Route Planner

Django API that plans cost-optimal fuel stops along a US truck route.

## Data credits

- `data/fuel-prices-for-be-assessment.csv`: provided as part of the assessment.
- `data/us_cities.csv`: trimmed from the [US-Cities-Database](https://github.com/kelvins/US-Cities-Database)
  by Kelvin S. do Prado (MIT License), 29,880 US cities with state and coordinates.
- The handful of stations that dataset didn't cover were geocoded with
  [Nominatim](https://nominatim.openstreetmap.org/) (OpenStreetMap data, ODbL) via
  `geocode_stations --nominatim-fallback`, a one-time data-preparation step.
