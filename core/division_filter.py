"""
Division Filter - Manages division-based filtering of race data

This module handles filtering race data by division, supporting three modes:
1. Player mode: Toggle between "My Class" and "All Classes"
2. Spectator mode: Cycle through individual divisions (Pro, ProAm, Am, Rookie, All)
3. No filter: Show all drivers

Responsibilities:
- Track current filter state
- Apply division filters to race data
- Determine which divisions have active drivers
- Provide button state (text/color) for UI display
"""

from typing import Dict, List, Optional, Callable
from config.constants import UI_COLORS
from core.division_manager import DivisionManager
from core.driver_state import DriverState


class DivisionFilter:
    """Manages division-based filtering of race data.

    This class encapsulates all logic related to filtering drivers by division,
    including state management, filter application, and UI state determination.
    """

    def __init__(self, division_manager: DivisionManager):
        """Initialize the division filter.

        Args:
            division_manager: DivisionManager instance for accessing division colors and mappings
        """
        self.division_manager = division_manager
        self.show_only_my_division = False  # Filter to player's division only
        self.current_division_filter = None  # Active spectator division filter
        self.division_cycle_order = ["Pro", "ProAm", "Am", "Rookie", "All"]

    def cycle_filter(
        self,
        race_data: List[DriverState],
        player_car_idx: Optional[int],
        get_driver_color_fn: Callable[[Dict], str]
    ) -> None:
        """Cycle to the next division filter mode.

        Two modes:
        1. Player is on track: Toggle between "All Classes" and "My Class"
        2. Player spectating: Cycle through each division (Pro -> ProAm -> Am -> Rookie -> All)

        Args:
            race_data: Current race data (unfiltered)
            player_car_idx: Player's car index, or None if spectating
            get_driver_color_fn: Deprecated; retained for caller compatibility
        """
        player_on_track = player_car_idx is not None and any(
            d.car_idx == player_car_idx for d in race_data
        )

        if player_on_track:
            # Simple toggle for active racers: show my division or all
            self.show_only_my_division = not self.show_only_my_division
            self.current_division_filter = None
        else:
            # Spectator mode: cycle through divisions that have active drivers
            self.show_only_my_division = False

            # Build a list of divisions that currently have drivers in the session
            divisions_with_drivers = self._get_divisions_with_drivers(race_data, get_driver_color_fn)

            # Only show divisions that exist in this session, plus "All"
            available_options = [div for div in self.division_cycle_order
                               if div == "All" or div in divisions_with_drivers]

            # Cycle to the next division in order
            if self.current_division_filter is None:
                next_filter = available_options[0] if available_options else "All"
            else:
                try:
                    current_name = "All" if self.current_division_filter == "All" else self.current_division_filter
                    current_idx = available_options.index(current_name)
                    next_idx = (current_idx + 1) % len(available_options)  # Wrap around to start
                    next_filter = available_options[next_idx]
                except (ValueError, IndexError):
                    next_filter = available_options[0] if available_options else "All"

            if next_filter == "All":
                self.current_division_filter = None
            else:
                self.current_division_filter = next_filter

    def apply_filter(
        self,
        race_data: List[DriverState],
        player_car_idx: Optional[int],
        get_driver_color_fn: Callable[[Dict], str]
    ) -> List[DriverState]:
        """Apply current filter to race data.

        Handles three filtering modes:
        1. Show only player's division (if show_only_my_division is True)
        2. Show specific division (if current_division_filter is set)
        3. Show all divisions (default)

        Args:
            race_data: Full list of DriverState objects to filter
            player_car_idx: Player's car index, or None if spectating
            get_driver_color_fn: Deprecated; retained for caller compatibility

        Returns:
            Filtered list of DriverState objects
        """
        if not race_data:
            return race_data

        # Filter to player's division only
        if self.show_only_my_division and player_car_idx is not None:
            player_division_key = None
            for driver in race_data:
                if driver.car_idx == player_car_idx:
                    player_division_key = self._get_driver_division_key(driver)
                    break

            if player_division_key:
                return [
                    d for d in race_data
                    if self._get_driver_division_key(d) == player_division_key
                ]
            return race_data

        # Filter to specific division (spectator mode)
        if self.current_division_filter is not None:
            return [
                d for d in race_data
                if self._get_driver_division_key(d) == self.current_division_filter
            ]

        # No filter - show all
        return race_data

    def get_button_state(self) -> Dict[str, str]:
        """Get current button text and color for UI display.

        Returns:
            Dictionary with 'text' and 'color' keys for button styling
        """
        if self.show_only_my_division:
            return {
                'text': "My Class",
                'color': UI_COLORS.DIVISION_HIGHLIGHT_GREEN
            }
        elif self.current_division_filter is not None:
            return {
                'text': self.current_division_filter,
                'color': self.division_manager.division_colors[self.current_division_filter]
            }
        else:
            return {
                'text': "All Classes",
                'color': UI_COLORS.BUTTON_GRAY
            }

    def reset(self) -> None:
        """Reset filter state (useful on session change)."""
        self.show_only_my_division = False
        self.current_division_filter = None

    def _get_driver_division_key(self, driver: DriverState) -> str:
        """Return the stable division key for filtering a DriverState."""
        if driver.division_name is not None:
            return self.division_manager.normalize_division_name(driver.division_name)
        return self.division_manager.get_driver_division_key(driver.driver_info)

    def _get_divisions_with_drivers(
        self,
        race_data: List[DriverState],
        get_driver_color_fn: Callable[[Dict], str]
    ) -> set:
        """Get set of division names that have active drivers in the session.

        Args:
            race_data: Current race data
            get_driver_color_fn: Deprecated; retained for caller compatibility

        Returns:
            Set of division names with active drivers
        """
        divisions_with_drivers = set()
        for driver in race_data:
            division_key = self._get_driver_division_key(driver)
            if division_key not in ["Default", "All"]:
                divisions_with_drivers.add(division_key)
        return divisions_with_drivers
