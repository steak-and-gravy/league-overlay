"""Shared helpers for deriving manufacturer display data from driver info."""

from typing import Dict, Tuple

from config.constants import MANUFACTURER_MAP


def extract_manufacturer(driver_info: Dict) -> Tuple[str, str]:
    """Extract manufacturer abbreviation and color from driver's CarPath."""
    car_path = driver_info.get('CarPath', '')
    if not car_path:
        return ('', '#FFFFFF')

    first_word = car_path.split()[0].lower() if car_path.split() else ''

    if first_word in MANUFACTURER_MAP:
        return MANUFACTURER_MAP[first_word]

    abbrev = first_word[:3].upper() if first_word else ''
    return (abbrev, '#FFFFFF')
