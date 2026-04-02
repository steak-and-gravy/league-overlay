"""
Tests for DivisionFilter class

Tests the division filtering logic that handles:
- Cycling through filter modes (My Division, specific divisions, All)
- Applying filters to race data
- Button state management for UI display
- Active division detection
"""

import pytest
from unittest.mock import Mock
from core.division_filter import DivisionFilter
from core.division_manager import DivisionManager
from core.driver_state import DriverState


@pytest.fixture
def mock_division_manager():
    """Create a mock DivisionManager with standard division colors."""
    manager = Mock(spec=DivisionManager)
    manager.division_colors = {
        "Pro": "#FF0000",
        "ProAm": "#00FF00",
        "Am": "#0000FF",
        "Rookie": "#FFFF00",
        "Default": "#C5C5C5",
        "All": "#FFFFFF"
    }
    return manager


@pytest.fixture
def division_filter(mock_division_manager):
    """Create a DivisionFilter instance with mock division manager."""
    return DivisionFilter(mock_division_manager)


@pytest.fixture
def sample_race_data():
    """Create sample race data with multiple divisions."""
    return [
        DriverState(
            car_idx=0,
            position=1,
            driver_info={'UserID': '1', 'UserName': 'Driver1'}
        ),
        DriverState(
            car_idx=1,
            position=2,
            driver_info={'UserID': '2', 'UserName': 'Driver2'}
        ),
        DriverState(
            car_idx=2,
            position=3,
            driver_info={'UserID': '3', 'UserName': 'Driver3'}
        ),
        DriverState(
            car_idx=3,
            position=4,
            driver_info={'UserID': '4', 'UserName': 'Driver4'}
        )
    ]


def get_driver_color_mock(driver_info):
    """Mock function that returns division colors based on driver."""
    # Map drivers to divisions for testing
    driver_divisions = {
        '1': '#FF0000',  # Pro
        '2': '#00FF00',  # ProAm
        '3': '#0000FF',  # Am
        '4': '#FFFF00',  # Rookie
    }
    return driver_divisions.get(driver_info.get('UserID'), '#FFFFFF')


class TestInitialization:
    """Test DivisionFilter initialization."""

    def test_initialization(self, division_filter):
        """Test that DivisionFilter initializes with correct default state."""
        assert division_filter.show_only_my_division is False
        assert division_filter.current_division_filter is None
        assert division_filter.division_cycle_order == ["Pro", "ProAm", "Am", "Rookie", "All"]

    def test_division_manager_reference(self, division_filter, mock_division_manager):
        """Test that DivisionFilter stores reference to division manager."""
        assert division_filter.division_manager is mock_division_manager


class TestPlayerModeFilterCycling:
    """Test filter cycling when player is on track."""

    def test_toggle_to_my_division(self, division_filter, sample_race_data):
        """Test toggling from All to My Division."""
        division_filter.cycle_filter(sample_race_data, player_car_idx=0, get_driver_color_fn=get_driver_color_mock)

        assert division_filter.show_only_my_division is True
        assert division_filter.current_division_filter is None

    def test_toggle_back_to_all(self, division_filter, sample_race_data):
        """Test toggling from My Division back to All."""
        division_filter.show_only_my_division = True

        division_filter.cycle_filter(sample_race_data, player_car_idx=0, get_driver_color_fn=get_driver_color_mock)

        assert division_filter.show_only_my_division is False
        assert division_filter.current_division_filter is None

    def test_player_mode_clears_spectator_filter(self, division_filter, sample_race_data):
        """Test that player mode cycling clears any spectator filter."""
        division_filter.current_division_filter = "Pro"

        division_filter.cycle_filter(sample_race_data, player_car_idx=0, get_driver_color_fn=get_driver_color_mock)

        assert division_filter.current_division_filter is None
        assert division_filter.show_only_my_division is True


class TestSpectatorModeFilterCycling:
    """Test filter cycling in spectator mode."""

    def test_cycles_to_first_active_division(self, division_filter, sample_race_data):
        """Test cycling to first division with active drivers."""
        division_filter.cycle_filter(sample_race_data, player_car_idx=None, get_driver_color_fn=get_driver_color_mock)

        assert division_filter.current_division_filter == "Pro"
        assert division_filter.show_only_my_division is False

    def test_cycles_through_active_divisions(self, division_filter, sample_race_data):
        """Test cycling through all active divisions."""
        # First cycle: Pro
        division_filter.cycle_filter(sample_race_data, player_car_idx=None, get_driver_color_fn=get_driver_color_mock)
        assert division_filter.current_division_filter == "Pro"

        # Second cycle: ProAm
        division_filter.cycle_filter(sample_race_data, player_car_idx=None, get_driver_color_fn=get_driver_color_mock)
        assert division_filter.current_division_filter == "ProAm"

        # Third cycle: Am
        division_filter.cycle_filter(sample_race_data, player_car_idx=None, get_driver_color_fn=get_driver_color_mock)
        assert division_filter.current_division_filter == "Am"

        # Fourth cycle: Rookie
        division_filter.cycle_filter(sample_race_data, player_car_idx=None, get_driver_color_fn=get_driver_color_mock)
        assert division_filter.current_division_filter == "Rookie"

        # Fifth cycle: All
        division_filter.cycle_filter(sample_race_data, player_car_idx=None, get_driver_color_fn=get_driver_color_mock)
        assert division_filter.current_division_filter is None

    def test_wraps_around_to_first_division(self, division_filter, sample_race_data):
        """Test that cycling wraps around from All back to first division."""
        division_filter.current_division_filter = None  # All

        division_filter.cycle_filter(sample_race_data, player_car_idx=None, get_driver_color_fn=get_driver_color_mock)

        assert division_filter.current_division_filter == "Pro"

    def test_skips_divisions_with_no_drivers(self, division_filter):
        """Test that spectator mode only cycles through divisions with active drivers."""
        # Race data with only Pro and Am drivers (no ProAm or Rookie)
        race_data = [
            DriverState(car_idx=0, driver_info={'UserID': '1', 'UserName': 'Driver1'}),  # Pro
            DriverState(car_idx=1, driver_info={'UserID': '3', 'UserName': 'Driver3'}),  # Am
        ]

        # First cycle: Pro
        division_filter.cycle_filter(race_data, player_car_idx=None, get_driver_color_fn=get_driver_color_mock)
        assert division_filter.current_division_filter == "Pro"

        # Second cycle: Should skip to Am (no ProAm or Rookie)
        division_filter.cycle_filter(race_data, player_car_idx=None, get_driver_color_fn=get_driver_color_mock)
        assert division_filter.current_division_filter == "Am"

        # Third cycle: All
        division_filter.cycle_filter(race_data, player_car_idx=None, get_driver_color_fn=get_driver_color_mock)
        assert division_filter.current_division_filter is None


class TestApplyFilter:
    """Test applying division filters to race data."""

    def test_no_filter_returns_all_data(self, division_filter, sample_race_data):
        """Test that with no filter, all data is returned."""
        result = division_filter.apply_filter(sample_race_data, player_car_idx=0, get_driver_color_fn=get_driver_color_mock)

        assert len(result) == 4
        assert result == sample_race_data

    def test_my_division_filter_player_mode(self, division_filter, sample_race_data):
        """Test filtering to player's division."""
        division_filter.show_only_my_division = True

        # Player is car_idx 0, which is Pro (#FF0000)
        result = division_filter.apply_filter(sample_race_data, player_car_idx=0, get_driver_color_fn=get_driver_color_mock)

        assert len(result) == 1
        assert result[0].car_idx == 0

    def test_specific_division_filter_spectator_mode(self, division_filter, sample_race_data):
        """Test filtering to a specific division in spectator mode."""
        division_filter.current_division_filter = "ProAm"

        result = division_filter.apply_filter(sample_race_data, player_car_idx=None, get_driver_color_fn=get_driver_color_mock)

        assert len(result) == 1
        assert result[0].car_idx == 1  # Driver2 is ProAm

    def test_filter_with_multiple_drivers_same_division(self, division_filter):
        """Test filtering when multiple drivers are in the same division."""
        race_data = [
            DriverState(car_idx=0, driver_info={'UserID': '1', 'UserName': 'Driver1'}),  # Pro
            DriverState(car_idx=1, driver_info={'UserID': '1', 'UserName': 'Driver5'}),  # Pro (same color)
            DriverState(car_idx=2, driver_info={'UserID': '2', 'UserName': 'Driver2'}),  # ProAm
        ]

        def color_fn(info):
            if info.get('UserName') in ['Driver1', 'Driver5']:
                return '#FF0000'  # Pro
            return '#00FF00'  # ProAm

        division_filter.current_division_filter = "Pro"
        division_filter.division_manager.division_colors['Pro'] = '#FF0000'

        result = division_filter.apply_filter(race_data, player_car_idx=None, get_driver_color_fn=color_fn)

        assert len(result) == 2
        assert result[0].car_idx == 0
        assert result[1].car_idx == 1

    def test_empty_race_data_returns_empty(self, division_filter):
        """Test that empty race data returns empty list."""
        result = division_filter.apply_filter([], player_car_idx=0, get_driver_color_fn=get_driver_color_mock)

        assert result == []

    def test_player_not_in_race_data(self, division_filter, sample_race_data):
        """Test filtering when player car idx doesn't exist in race data."""
        division_filter.show_only_my_division = True

        # Player car_idx 99 doesn't exist
        result = division_filter.apply_filter(sample_race_data, player_car_idx=99, get_driver_color_fn=get_driver_color_mock)

        # Should return all data if player not found
        assert len(result) == 4


class TestGetButtonState:
    """Test button state determination for UI display."""

    def test_all_divisions_state(self, division_filter):
        """Test button state when showing all divisions."""
        state = division_filter.get_button_state()

        assert state['text'] == "All Divisions"
        assert state['color'] == "#555555"  # UI_COLORS.BUTTON_GRAY

    def test_my_division_state(self, division_filter):
        """Test button state when showing player's division."""
        division_filter.show_only_my_division = True

        state = division_filter.get_button_state()

        assert state['text'] == "My Division"
        assert state['color'] == "#0FC436"  # UI_COLORS.DIVISION_HIGHLIGHT_GREEN

    def test_specific_division_state(self, division_filter):
        """Test button state when showing specific division."""
        division_filter.current_division_filter = "ProAm"

        state = division_filter.get_button_state()

        assert state['text'] == "ProAm"
        assert state['color'] == "#00FF00"  # ProAm color


class TestReset:
    """Test filter state reset functionality."""

    def test_reset_clears_my_division_flag(self, division_filter):
        """Test that reset clears show_only_my_division."""
        division_filter.show_only_my_division = True

        division_filter.reset()

        assert division_filter.show_only_my_division is False

    def test_reset_clears_current_filter(self, division_filter):
        """Test that reset clears current_division_filter."""
        division_filter.current_division_filter = "Pro"

        division_filter.reset()

        assert division_filter.current_division_filter is None

    def test_reset_returns_to_default_state(self, division_filter):
        """Test that reset returns filter to initial state."""
        division_filter.show_only_my_division = True
        division_filter.current_division_filter = "Am"

        division_filter.reset()

        assert division_filter.show_only_my_division is False
        assert division_filter.current_division_filter is None


class TestGetDivisionsWithDrivers:
    """Test detection of active divisions."""

    def test_identifies_all_active_divisions(self, division_filter, sample_race_data):
        """Test that all divisions with active drivers are identified."""
        divisions = division_filter._get_divisions_with_drivers(sample_race_data, get_driver_color_mock)

        assert "Pro" in divisions
        assert "ProAm" in divisions
        assert "Am" in divisions
        assert "Rookie" in divisions

    def test_excludes_default_and_all(self, division_filter):
        """Test that Default and All are excluded from active divisions."""
        race_data = [
            DriverState(car_idx=0, driver_info={'UserID': '1', 'UserName': 'Driver1'})
        ]

        def color_fn(info):
            return '#FFFFFF'  # Default color

        division_filter.division_manager.division_colors['Default'] = '#FFFFFF'

        divisions = division_filter._get_divisions_with_drivers(race_data, color_fn)

        assert "Default" not in divisions
        assert "All" not in divisions

    def test_empty_race_data_returns_empty_set(self, division_filter):
        """Test that empty race data returns empty set."""
        divisions = division_filter._get_divisions_with_drivers([], get_driver_color_mock)

        assert divisions == set()

    def test_single_division_race(self, division_filter):
        """Test detection when all drivers are in one division."""
        race_data = [
            DriverState(car_idx=0, driver_info={'UserID': '1', 'UserName': 'Driver1'}),
            DriverState(car_idx=1, driver_info={'UserID': '1', 'UserName': 'Driver2'}),
        ]

        def color_fn(info):
            return '#FF0000'  # All Pro

        division_filter.division_manager.division_colors['Pro'] = '#FF0000'

        divisions = division_filter._get_divisions_with_drivers(race_data, color_fn)

        assert len(divisions) == 1
        assert "Pro" in divisions


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_none_player_car_idx(self, division_filter, sample_race_data):
        """Test that None player_car_idx is handled correctly."""
        # Should default to spectator mode
        division_filter.cycle_filter(sample_race_data, player_car_idx=None, get_driver_color_fn=get_driver_color_mock)

        assert division_filter.show_only_my_division is False
        assert division_filter.current_division_filter == "Pro"

    def test_invalid_current_filter_recovers(self, division_filter, sample_race_data):
        """Test that invalid current filter state recovers gracefully."""
        division_filter.current_division_filter = "NonExistentDivision"

        # Should recover and cycle to first active division
        division_filter.cycle_filter(sample_race_data, player_car_idx=None, get_driver_color_fn=get_driver_color_mock)

        assert division_filter.current_division_filter == "Pro"

    def test_filter_with_no_active_divisions(self, division_filter):
        """Test behavior when no divisions have active drivers."""
        race_data = []

        division_filter.cycle_filter(race_data, player_car_idx=None, get_driver_color_fn=get_driver_color_mock)

        # Should default to "All"
        assert division_filter.current_division_filter is None

    def test_apply_filter_preserves_original_data(self, division_filter, sample_race_data):
        """Test that applying filter doesn't modify original race data."""
        original_length = len(sample_race_data)

        division_filter.current_division_filter = "Pro"
        result = division_filter.apply_filter(sample_race_data, player_car_idx=None, get_driver_color_fn=get_driver_color_mock)

        # Original data should be unchanged
        assert len(sample_race_data) == original_length
        # Result should be filtered
        assert len(result) < original_length
