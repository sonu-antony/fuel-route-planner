import csv
from pathlib import Path


def _normalize_city(city: str) -> str:
    text = " ".join(city.strip().upper().split())
    if text.startswith("ST. "):
        text = "SAINT " + text[4:]
    elif text.startswith("ST "):
        text = "SAINT " + text[3:]
    return text


def _normalize_state(state: str) -> str:
    return state.strip().upper()


class CityLookup:
    def __init__(self, entries: dict[tuple[str, str], tuple[float, float]]):
        self._entries = entries

    def find(self, city: str, state: str) -> tuple[float, float] | None:
        return self._entries.get((_normalize_city(city), _normalize_state(state)))


def load_city_lookup(path: str | Path) -> CityLookup:
    entries: dict[tuple[str, str], tuple[float, float]] = {}
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            key = (_normalize_city(row["city"]), _normalize_state(row["state_id"]))
            entries[key] = (float(row["lat"]), float(row["lng"]))
    return CityLookup(entries)
