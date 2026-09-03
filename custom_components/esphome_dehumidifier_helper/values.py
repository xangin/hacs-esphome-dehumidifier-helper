"""Pure value conversion shared by the entity and offline checks."""

from collections.abc import Mapping
import math
from typing import Any

from .const import FALLBACK_MAX_HUMIDITY, FALLBACK_MIN_HUMIDITY


def finite_number(value: Any) -> float | None:
    """Reject unknown, unavailable, None, booleans, NaN and infinity."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def humidity_value(value: Any) -> float | None:
    """A humidity reading must be a finite percentage."""
    number = finite_number(value)
    return number if number is not None and 0 <= number <= 100 else None


def humidity_limits(attributes: Mapping[str, Any]) -> tuple[float, float, float | None]:
    """Use public number attributes, with fallbacks for missing/broken bounds."""
    low = humidity_value(attributes.get("min"))
    high = humidity_value(attributes.get("max"))
    low = FALLBACK_MIN_HUMIDITY if low is None else low
    high = FALLBACK_MAX_HUMIDITY if high is None else high
    if low >= high:
        low, high = FALLBACK_MIN_HUMIDITY, FALLBACK_MAX_HUMIDITY
    step = finite_number(attributes.get("step"))
    if step is not None and not 0 < step <= high - low:
        step = None
    return low, high, step


def valid_humidity_setting(
    humidity: Any, low: float, high: float, step: float | None
) -> bool:
    """Do not silently round a command to a different humidity."""
    value = humidity_value(humidity)
    if value is None or not low <= value <= high:
        return False
    if step is None:
        return True
    steps = (value - low) / step
    return math.isclose(steps, round(steps), rel_tol=0, abs_tol=1e-6)
