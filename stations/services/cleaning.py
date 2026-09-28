from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

US_STATES = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
    }
)

PRICE_QUANTUM = Decimal("0.001")


@dataclass(frozen=True)
class CleanedStation:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    rack_id: int
    price_per_gallon: Decimal


def clean_rows(rows: Iterable[dict[str, str]]) -> list[CleanedStation]:
    by_id: dict[int, CleanedStation] = {}
    for row in rows:
        state = row["State"].strip()
        if state not in US_STATES:
            continue
        station = CleanedStation(
            opis_id=int(row["OPIS Truckstop ID"].strip()),
            name=row["Truckstop Name"].strip(),
            address=row["Address"].strip(),
            city=row["City"].strip(),
            state=state,
            rack_id=int(row["Rack ID"].strip()),
            price_per_gallon=Decimal(row["Retail Price"].strip()).quantize(PRICE_QUANTUM),
        )
        existing = by_id.get(station.opis_id)
        if existing is None or station.price_per_gallon < existing.price_per_gallon:
            by_id[station.opis_id] = station
    return list(by_id.values())
