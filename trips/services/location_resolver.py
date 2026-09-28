from stations.services.city_lookup import CityLookup
from trips.exceptions import LocationNotFound, LocationOutsideUSA

CONTINENTAL_US_LAT_RANGE = (24.396308, 49.384358)
CONTINENTAL_US_LNG_RANGE = (-125.0, -66.93457)


def _within_continental_usa(latitude: float, longitude: float) -> bool:
    lat_min, lat_max = CONTINENTAL_US_LAT_RANGE
    lng_min, lng_max = CONTINENTAL_US_LNG_RANGE
    return lat_min <= latitude <= lat_max and lng_min <= longitude <= lng_max


def _try_parse_coordinates(text: str) -> tuple[float, float] | None:
    parts = text.split(",")
    if len(parts) != 2:
        return None
    try:
        return float(parts[0].strip()), float(parts[1].strip())
    except ValueError:
        return None


def _try_city_state(text: str, city_lookup: CityLookup) -> tuple[float, float] | None:
    parts = text.split(",")
    if len(parts) != 2:
        return None
    city, state = parts[0].strip(), parts[1].strip()
    if not city or not state:
        return None
    return city_lookup.find(city, state)


def resolve_location(query: str, city_lookup: CityLookup) -> tuple[float, float]:
    text = query.strip()

    coordinates = _try_parse_coordinates(text)
    if coordinates is None:
        coordinates = _try_city_state(text, city_lookup)
    if coordinates is None:
        raise LocationNotFound(query)

    latitude, longitude = coordinates
    if not _within_continental_usa(latitude, longitude):
        raise LocationOutsideUSA(query)

    return coordinates
