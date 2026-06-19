"""Shared display-name helpers for driver rows."""

from typing import Any

from core.driver_state import DriverState


def driver_display_name(driver: DriverState, settings: Any) -> str:
    """Return the name text shown in the overlay driver-name cell."""
    if getattr(settings, "always_use_driver_name", False):
        return driver.driver_name
    return driver.team_name if driver.team_name > "" else driver.driver_name
