import pytest
from django.core.exceptions import ImproperlyConfigured

from config.env import non_negative_number, positive_number


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
