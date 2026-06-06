"""Shared helpers for iRacing DriverInfo access."""

from typing import Any, Dict, Iterable, Optional, Set


def coerce_car_idx(value: Any) -> Optional[int]:
    """Return a non-negative CarIdx integer, or None for invalid values."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            car_idx = int(stripped)
        except ValueError:
            return None
        return car_idx if car_idx >= 0 else None
    return None


def build_driver_lookup(drivers: Iterable[Dict]) -> Dict[int, Dict]:
    """Build an O(1) DriverInfo lookup keyed by CarIdx."""
    lookup: Dict[int, Dict] = {}
    for driver in drivers:
        if not isinstance(driver, dict):
            continue
        car_idx = coerce_car_idx(driver.get('CarIdx'))
        if car_idx is not None:
            lookup[car_idx] = driver
    return lookup


def _collect_car_indices(value: Any) -> Set[int]:
    """Collect CarIdx values from scalar or iterable DriverInfo fields."""
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = (value,)

    car_indices: Set[int] = set()
    for item in values:
        car_idx = coerce_car_idx(item)
        if car_idx is not None:
            car_indices.add(car_idx)
    return car_indices


def get_pace_car_indices(driver_info: Dict) -> Set[int]:
    """Return all pace-car indices advertised by DriverInfo."""
    pace_car_indices: Set[int] = set()
    if not isinstance(driver_info, dict):
        return pace_car_indices

    pace_car_indices.update(_collect_car_indices(driver_info.get('PaceCarXIdx')))
    pace_car_indices.update(_collect_car_indices(driver_info.get('PaceCarIdx')))
    return pace_car_indices


def is_pace_car(driver: Dict, pace_car_indices: Optional[Set[int]] = None) -> bool:
    """Return True when DriverInfo identifies a pace car."""
    if not isinstance(driver, dict):
        return False

    car_idx = coerce_car_idx(driver.get('CarIdx'))
    if pace_car_indices and car_idx in pace_car_indices:
        return True

    driver_name = str(driver.get('UserName', ''))
    return 'pace car' in driver_name.lower()
