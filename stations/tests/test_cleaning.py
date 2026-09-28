from decimal import Decimal

from stations.services.cleaning import clean_rows


def make_row(
    opis_id="105",
    name="PILOT #1243",
    address="I-44, EXIT 283 & US-69",
    city="Big Cabin",
    state="OK",
    rack_id="307",
    price="3.269",
):
    return {
        "OPIS Truckstop ID": opis_id,
        "Truckstop Name": name,
        "Address": address,
        "City": city,
        "State": state,
        "Rack ID": rack_id,
        "Retail Price": price,
    }


def test_strips_whitespace_from_text_fields():
    row = make_row(
        name="  PILOT #1243  ",
        address="  I-44, EXIT 283 & US-69  ",
        city="  Big Cabin  ",
        state=" OK ",
    )

    [station] = clean_rows([row])

    assert station.name == "PILOT #1243"
    assert station.address == "I-44, EXIT 283 & US-69"
    assert station.city == "Big Cabin"
    assert station.state == "OK"


def test_drops_rows_outside_the_50_states_and_dc():
    rows = [make_row(opis_id="1", state="ON"), make_row(opis_id="2", state="TX")]

    stations = clean_rows(rows)

    assert [station.opis_id for station in stations] == [2]


def test_keeps_one_row_per_station_id_with_the_lowest_price():
    rows = [
        make_row(opis_id="105", price="3.269"),
        make_row(opis_id="105", price="3.339"),
        make_row(opis_id="105", price="3.429"),
        make_row(opis_id="105", price="3.289"),
    ]

    [station] = clean_rows(rows)

    assert station.price_per_gallon == Decimal("3.269")


def test_parses_price_as_decimal_with_three_places():
    row = make_row(price="3.00733333")

    [station] = clean_rows([row])

    assert station.price_per_gallon == Decimal("3.007")


def test_preserves_the_station_id_as_an_integer():
    row = make_row(opis_id="105")

    [station] = clean_rows([row])

    assert station.opis_id == 105
    assert isinstance(station.opis_id, int)
