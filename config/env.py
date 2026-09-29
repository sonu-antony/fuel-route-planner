import math
import os

from django.core.exceptions import ImproperlyConfigured


def _number(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return float(default)
    try:
        value = float(raw)
    except ValueError as error:
        raise ImproperlyConfigured(f"{name} must be a number, got {raw!r}") from error
    if not math.isfinite(value):
        raise ImproperlyConfigured(f"{name} must be finite, got {raw!r}")
    return value


def positive_number(name: str, default: float) -> float:
    value = _number(name, default)
    if value <= 0:
        raise ImproperlyConfigured(f"{name} must be greater than 0, got {value}")
    return value


def non_negative_number(name: str, default: float) -> float:
    value = _number(name, default)
    if value < 0:
        raise ImproperlyConfigured(f"{name} must be 0 or more, got {value}")
    return value


def non_negative_integer(name: str, default: int) -> int:
    value = non_negative_number(name, default)
    if not value.is_integer():
        raise ImproperlyConfigured(f"{name} must be a whole number, got {value}")
    return int(value)
