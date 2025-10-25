"""Tests for core.position_calculator module.

Tests cover:
- Player identification
- Real-time position calculation
- Official position retrieval
- Multi-class filtering
- Overall race leader detection
- Edge cases and error handling
"""

import pytest
from unittest.mock import Mock, MagicMock
from core.position_calculator import PositionCalculator


def make_drivers_dict(drivers_list):
    """Helper to convert drivers list to dict (matching new API)."""
    return {driver['CarIdx']: driver for driver in drivers_list}


class TestInitialization:
    """Test cases for PositionCalculator initialization."""

    def test_initialization(self):
        """Test PositionCalculator initializes correctly."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)
        assert calculator.ir == mock_ir
        assert calculator.player_car_idx is None
        assert calculator.player_car_class_id is None

    def test_reset(self):
        """Test reset clears player identification."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)
        calculator.player_car_idx = 5
        calculator.player_car_class_id = 2

        calculator.reset()

        assert calculator.player_car_idx is None
        assert calculator.player_car_class_id is None


class TestIdentifyPlayer:
    """Test cases for player identification."""

    def test_identifies_player_car_idx(self):
        """Test identifies player's car index."""
        mock_ir = MagicMock()
        mock_ir.__getitem__.return_value = 5  # PlayerCarIdx = 5

        calculator = PositionCalculator(mock_ir)
        drivers = [
            {'CarIdx': 5, 'UserID': '12345', 'CarClassID': 2}
        ]

        calculator.identify_player(make_drivers_dict(drivers))

        assert calculator.player_car_idx == 5

    def test_identifies_player_class_id(self):
        """Test identifies player's class ID."""
        mock_ir = MagicMock()
        mock_ir.__getitem__.return_value = 5

        calculator = PositionCalculator(mock_ir)
        drivers = [
            {'CarIdx': 5, 'UserID': '12345', 'CarClassID': 2}
        ]

        calculator.identify_player(make_drivers_dict(drivers))

        assert calculator.player_car_class_id == 2

    def test_handles_missing_player(self):
        """Test handles missing PlayerCarIdx."""
        mock_ir = MagicMock()
        mock_ir.__getitem__.side_effect = KeyError('PlayerCarIdx')

        calculator = PositionCalculator(mock_ir)
        drivers = []

        calculator.identify_player(make_drivers_dict(drivers))

        assert calculator.player_car_idx is None

    def test_handles_missing_class_id(self):
        """Test handles driver without CarClassID."""
        mock_ir = MagicMock()
        mock_ir.__getitem__.return_value = 5

        calculator = PositionCalculator(mock_ir)
        drivers = [
            {'CarIdx': 5, 'UserID': '12345'}  # Missing CarClassID
        ]

        calculator.identify_player(make_drivers_dict(drivers))

        assert calculator.player_car_idx == 5
        assert calculator.player_car_class_id is None

    def test_only_identifies_once(self):
        """Test player identification only happens once."""
        mock_ir = MagicMock()
        mock_ir.__getitem__.return_value = 5

        calculator = PositionCalculator(mock_ir)
        drivers = [
            {'CarIdx': 5, 'UserID': '12345', 'CarClassID': 2}
        ]

        calculator.identify_player(make_drivers_dict(drivers))
        assert calculator.player_car_idx == 5

        # Call again with different car index
        mock_ir.__getitem__.return_value = 10
        calculator.identify_player(make_drivers_dict(drivers))

        # Should still be 5 (not re-identified)
        assert calculator.player_car_idx == 5


class TestCalculateRealTimePositions:
    """Test cases for real-time position calculation."""

    def test_calculates_positions_by_track_position(self):
        """Test positions calculated by total track position."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        drivers = [
            {'CarIdx': 1, 'UserID': '101', 'CarClassID': 2},
            {'CarIdx': 2, 'UserID': '102', 'CarClassID': 2},
            {'CarIdx': 3, 'UserID': '103', 'CarClassID': 2}
        ]

        live_data = {
            'CarIdxLap': [0, 10, 10, 10],  # All on lap 10
            'CarIdxLapDistPct': [0, 0.9, 0.5, 0.3],  # Different positions through lap
            'CarIdxClassPosition': [0, 1, 2, 3]
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.calculate_real_time_positions(make_drivers_dict(drivers))

        # Should be sorted by total_track_position (lap + pct)
        assert len(result) == 3
        assert result[0]['car_idx'] == 1  # 10.9
        assert result[1]['car_idx'] == 2  # 10.5
        assert result[2]['car_idx'] == 3  # 10.3

    def test_assigns_real_time_position(self):
        """Test real-time position numbers assigned correctly."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        drivers = [
            {'CarIdx': 1, 'UserID': '101', 'CarClassID': 2},
            {'CarIdx': 2, 'UserID': '102', 'CarClassID': 2}
        ]

        live_data = {
            'CarIdxLap': [0, 10, 10],
            'CarIdxLapDistPct': [0, 0.9, 0.5],
            'CarIdxClassPosition': [0, 1, 2]
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.calculate_real_time_positions(make_drivers_dict(drivers))

        assert result[0]['real_time_position'] == 1
        assert result[1]['real_time_position'] == 2

    def test_filters_to_player_class(self):
        """Test only shows cars in player's class."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)
        calculator.player_car_class_id = 2  # GT4

        drivers = [
            {'CarIdx': 1, 'UserID': '101', 'CarClassID': 1},  # GT3
            {'CarIdx': 2, 'UserID': '102', 'CarClassID': 2},  # GT4
            {'CarIdx': 3, 'UserID': '103', 'CarClassID': 2}   # GT4
        ]

        live_data = {
            'CarIdxLap': [0, 10, 10, 10],
            'CarIdxLapDistPct': [0, 0.9, 0.8, 0.7],
            'CarIdxClassPosition': [0, 1, 1, 2]
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.calculate_real_time_positions(make_drivers_dict(drivers))

        # Should only include GT4 (class 2)
        assert len(result) == 2
        assert all(d['driver_info']['CarClassID'] == 2 for d in result)

    def test_handles_negative_laps(self):
        """Test skips cars with negative laps (not active)."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        drivers = [
            {'CarIdx': 1, 'UserID': '101', 'CarClassID': 2},
            {'CarIdx': 2, 'UserID': '102', 'CarClassID': 2}
        ]

        live_data = {
            'CarIdxLap': [0, -1, 10],  # Car 1 has negative lap
            'CarIdxLapDistPct': [0, 0.5, 0.5],
            'CarIdxClassPosition': [0, 0, 1]
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.calculate_real_time_positions(make_drivers_dict(drivers))

        # Should only include car 2
        assert len(result) == 1
        assert result[0]['car_idx'] == 2

    def test_handles_invalid_lap_percentage(self):
        """Test clamps invalid lap percentage to 0."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        drivers = [
            {'CarIdx': 1, 'UserID': '101', 'CarClassID': 2}
        ]

        live_data = {
            'CarIdxLap': [0, 10],
            'CarIdxLapDistPct': [0, -0.5],  # Invalid (negative)
            'CarIdxClassPosition': [0, 1]
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.calculate_real_time_positions(make_drivers_dict(drivers))

        assert result[0]['lap_pct'] == 0  # Clamped

    def test_handles_lap_percentage_over_one(self):
        """Test clamps lap percentage over 1.0 to 0."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        drivers = [
            {'CarIdx': 1, 'UserID': '101', 'CarClassID': 2}
        ]

        live_data = {
            'CarIdxLap': [0, 10],
            'CarIdxLapDistPct': [0, 1.5],  # Invalid (> 1.0)
            'CarIdxClassPosition': [0, 1]
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.calculate_real_time_positions(make_drivers_dict(drivers))

        assert result[0]['lap_pct'] == 0  # Clamped

    def test_skips_position_zero(self):
        """Test skips cars with position 0 (not participating)."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        drivers = [
            {'CarIdx': 1, 'UserID': '101', 'CarClassID': 2},
            {'CarIdx': 2, 'UserID': '102', 'CarClassID': 2}
        ]

        live_data = {
            'CarIdxLap': [0, 10, 10],
            'CarIdxLapDistPct': [0, 0.5, 0.3],
            'CarIdxClassPosition': [0, 0, 1]  # Car 1 has position 0
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.calculate_real_time_positions(make_drivers_dict(drivers))

        # Should only include car 2
        assert len(result) == 1
        assert result[0]['car_idx'] == 2

    def test_returns_empty_on_missing_data(self):
        """Test returns empty list if telemetry data missing."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        drivers = []
        live_data = {
            'CarIdxLap': None,  # Missing
            'CarIdxLapDistPct': None,
            'CarIdxClassPosition': None
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.calculate_real_time_positions(make_drivers_dict(drivers))

        assert result == []


class TestGetOfficialPositions:
    """Test cases for official position retrieval."""

    def test_gets_official_positions(self):
        """Test retrieves official positions from iRacing."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        drivers = [
            {'CarIdx': 1, 'UserID': '101', 'CarClassID': 2},
            {'CarIdx': 2, 'UserID': '102', 'CarClassID': 2}
        ]

        live_data = {
            'CarIdxClassPosition': [0, 2, 1]  # Car 2 is P1, Car 1 is P2
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.get_official_positions(make_drivers_dict(drivers))

        assert len(result) == 2
        assert result[0]['official_position'] == 1
        assert result[1]['official_position'] == 2

    def test_sorts_by_official_position(self):
        """Test results sorted by official position."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        drivers = [
            {'CarIdx': 1, 'UserID': '101', 'CarClassID': 2},
            {'CarIdx': 2, 'UserID': '102', 'CarClassID': 2},
            {'CarIdx': 3, 'UserID': '103', 'CarClassID': 2}
        ]

        live_data = {
            'CarIdxClassPosition': [0, 3, 1, 2]
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.get_official_positions(make_drivers_dict(drivers))

        assert result[0]['car_idx'] == 2  # P1
        assert result[1]['car_idx'] == 3  # P2
        assert result[2]['car_idx'] == 1  # P3

    def test_filters_to_player_class(self):
        """Test filters to player's class only."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)
        calculator.player_car_class_id = 2

        drivers = [
            {'CarIdx': 1, 'UserID': '101', 'CarClassID': 1},  # Different class
            {'CarIdx': 2, 'UserID': '102', 'CarClassID': 2}
        ]

        live_data = {
            'CarIdxClassPosition': [0, 1, 1]
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.get_official_positions(make_drivers_dict(drivers))

        assert len(result) == 1
        assert result[0]['car_idx'] == 2

    def test_skips_position_zero(self):
        """Test skips cars not participating (position 0)."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        drivers = [
            {'CarIdx': 1, 'UserID': '101', 'CarClassID': 2},
            {'CarIdx': 2, 'UserID': '102', 'CarClassID': 2}
        ]

        live_data = {
            'CarIdxClassPosition': [0, 0, 1]  # Car 1 not participating
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.get_official_positions(make_drivers_dict(drivers))

        assert len(result) == 1
        assert result[0]['car_idx'] == 2

    def test_returns_empty_on_missing_data(self):
        """Test returns empty if position data missing."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        drivers = []
        live_data = {
            'CarIdxClassPosition': None
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.get_official_positions(make_drivers_dict(drivers))

        assert result == []


class TestGetOverallRaceLeader:
    """Test cases for finding overall race leader."""

    def test_finds_leader_by_track_position(self):
        """Test finds leader with highest track position."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        live_data = {
            'CarIdxLap': [0, 10, 10, 10],
            'CarIdxLapDistPct': [0, 0.9, 0.5, 0.3]
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.get_overall_race_leader_idx()

        assert result == 1  # Car 1 at 10.9

    def test_handles_multiple_classes(self):
        """Test finds leader across multiple classes."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        live_data = {
            'CarIdxLap': [0, 10, 11, 10],  # Car 2 is ahead on laps
            'CarIdxLapDistPct': [0, 0.9, 0.1, 0.8]
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.get_overall_race_leader_idx()

        assert result == 2  # Car 2 at 11.1 (highest)

    def test_handles_no_active_cars(self):
        """Test returns None if no active cars."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        live_data = {
            'CarIdxLap': [-1, -1, -1],  # All inactive
            'CarIdxLapDistPct': [0, 0, 0]
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.get_overall_race_leader_idx()

        assert result is None

    def test_handles_missing_data(self):
        """Test returns None if telemetry data missing."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        live_data = {
            'CarIdxLap': None,
            'CarIdxLapDistPct': None
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.get_overall_race_leader_idx()

        assert result is None

    def test_handles_tie_in_track_position(self):
        """Test handles cars at same track position (returns first)."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        live_data = {
            'CarIdxLap': [0, 10, 10],
            'CarIdxLapDistPct': [0, 0.5, 0.5]  # Both at 10.5
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.get_overall_race_leader_idx()

        # Should return first one found
        assert result == 1


class TestIntegration:
    """Integration tests combining multiple methods."""

    def test_full_position_calculation_flow(self):
        """Test complete flow from player ID to positions."""
        mock_ir = MagicMock()
        mock_ir.__getitem__.return_value = 2  # Player is car 2

        calculator = PositionCalculator(mock_ir)

        drivers = [
            {'CarIdx': 1, 'UserID': '101', 'CarClassID': 2},
            {'CarIdx': 2, 'UserID': '102', 'CarClassID': 2},
            {'CarIdx': 3, 'UserID': '103', 'CarClassID': 1}  # Different class
        ]

        # Identify player
        calculator.identify_player(make_drivers_dict(drivers))
        assert calculator.player_car_idx == 2
        assert calculator.player_car_class_id == 2

        # Calculate positions (should filter to class 2 only)
        live_data = {
            'CarIdxLap': [0, 10, 10, 11],
            'CarIdxLapDistPct': [0, 0.8, 0.5, 0.2],
            'CarIdxClassPosition': [0, 1, 2, 1]
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.calculate_real_time_positions(make_drivers_dict(drivers))

        # Should only have cars 1 and 2 (class 2)
        assert len(result) == 2
        assert result[0]['car_idx'] == 1  # 10.8
        assert result[1]['car_idx'] == 2  # 10.5
