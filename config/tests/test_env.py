import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.env import non_negative_integer, non_negative_number, positive_number


def test_an_unset_variable_uses_the_default(monkeypatch):
    monkeypatch.delenv("FUEL_TEST_VALUE", raising=False)

    assert positive_number("FUEL_TEST_VALUE", 2.5) == 2.5


def test_a_set_variable_is_parsed_as_a_number(monkeypatch):
    monkeypatch.setenv("FUEL_TEST_VALUE", "7.5")

    assert positive_number("FUEL_TEST_VALUE", 1) == 7.5


@pytest.mark.parametrize("value", ["0", "-3", "abc", "nan", "inf"])
def test_a_positive_setting_rejects_zero_negative_and_non_numbers(monkeypatch, value):
    monkeypatch.setenv("FUEL_TEST_VALUE", value)

    with pytest.raises(ImproperlyConfigured, match="FUEL_TEST_VALUE"):
        positive_number("FUEL_TEST_VALUE", 1)


def test_a_non_negative_setting_accepts_zero_and_rejects_negatives(monkeypatch):
    monkeypatch.setenv("FUEL_TEST_VALUE", "0")
    assert non_negative_number("FUEL_TEST_VALUE", 1) == 0

    monkeypatch.setenv("FUEL_TEST_VALUE", "-1")
    with pytest.raises(ImproperlyConfigured, match="FUEL_TEST_VALUE"):
        non_negative_number("FUEL_TEST_VALUE", 1)


@pytest.mark.parametrize("value", ["0.5", "-1", "abc"])
def test_a_non_negative_integer_setting_rejects_fractions_negatives_and_non_numbers(
    monkeypatch, value
):
    monkeypatch.setenv("FUEL_TEST_VALUE", value)

    with pytest.raises(ImproperlyConfigured, match="FUEL_TEST_VALUE"):
        non_negative_integer("FUEL_TEST_VALUE", 1)


def test_a_non_negative_integer_setting_parses_whole_numbers(monkeypatch):
    monkeypatch.setenv("FUEL_TEST_VALUE", "3600")

    assert non_negative_integer("FUEL_TEST_VALUE", 1) == 3600


@pytest.mark.parametrize("reserve", ["50", "60"])
def test_a_fuel_reserve_as_large_as_the_tank_stops_the_server_starting(reserve):
    environment = {**os.environ, "FUEL_RESERVE_GALLONS": reserve}

    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "FUEL_RESERVE_GALLONS" in result.stderr
