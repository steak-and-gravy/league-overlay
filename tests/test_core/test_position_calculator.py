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
    """Helper to convert drivers list to dict (matching new API).

    Also adds default CarNumber and UserName if not present to support
    the pace car/spectator filtering logic.
    """
    result = {}
    for driver in drivers_list:
        # Add default CarNumber if not present (use CarIdx as default)
        if 'CarNumber' not in driver:
            driver['CarNumber'] = str(driver['CarIdx'])
        # Add default UserName if not present
        if 'UserName' not in driver:
            driver['UserName'] = f"Driver {driver['CarIdx']}"
        result[driver['CarIdx']] = driver
    return result


class TestInitialization:
    """Test cases for PositionCalculator initialization."""

    def test_initialization(self):
        """Test PositionCalculator initializes correctly."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)
        assert calculator.ir == mock_ir
        assert calculator.player_car_idx is None
        assert calculator.player_car_class_id is None
        assert calculator.spectated_car_idx is None

    def test_reset(self):
        """Test reset clears player identification."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)
        calculator.player_car_idx = 5
        calculator.player_car_class_id = 2
        calculator.spectated_car_idx = 3

        calculator.reset()

        assert calculator.player_car_idx is None
        assert calculator.player_car_class_id is None
        assert calculator.spectated_car_idx is None


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

    def test_reidentifies_when_player_car_idx_changes(self):
        """Player identity is cached and does not refresh once identified."""
        mock_ir = MagicMock()
        mock_ir.__getitem__.return_value = 5

        calculator = PositionCalculator(mock_ir)
        drivers = [
            {'CarIdx': 5, 'UserID': '12345', 'CarClassID': 2},
            {'CarIdx': 10, 'UserID': '67890', 'CarClassID': 3}
        ]

        calculator.identify_player(make_drivers_dict(drivers))
        assert calculator.player_car_idx == 5
        assert calculator.player_car_class_id == 2

        # Call again with different car index
        mock_ir.__getitem__.return_value = 10
        calculator.identify_player(make_drivers_dict(drivers))

        assert calculator.player_car_idx == 5
        assert calculator.player_car_class_id == 2

    def test_updates_player_class_id_when_same_player_idx_changes_class(self):
        """Class cache remains stable once identified."""
        mock_ir = MagicMock()
        mock_ir.__getitem__.return_value = 5

        calculator = PositionCalculator(mock_ir)

        drivers_class_2 = [{'CarIdx': 5, 'UserID': '12345', 'CarClassID': 2}]
        calculator.identify_player(make_drivers_dict(drivers_class_2))
        assert calculator.player_car_class_id == 2

        drivers_class_3 = [{'CarIdx': 5, 'UserID': '12345', 'CarClassID': 3}]
        calculator.identify_player(make_drivers_dict(drivers_class_3))
        assert calculator.player_car_class_id == 2

    def test_clears_player_class_id_when_player_not_in_driver_list(self):
        """Class cache remains when player temporarily disappears from drivers."""
        mock_ir = MagicMock()
        mock_ir.__getitem__.return_value = 5

        calculator = PositionCalculator(mock_ir)
        drivers = [{'CarIdx': 5, 'UserID': '12345', 'CarClassID': 2}]
        calculator.identify_player(make_drivers_dict(drivers))
        assert calculator.player_car_class_id == 2

        calculator.identify_player(make_drivers_dict([]))
        assert calculator.player_car_idx == 5
        assert calculator.player_car_class_id == 2


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

    def test_assigns_position(self):
        """Test position numbers assigned correctly."""
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

        assert result[0]['position'] == 1
        assert result[1]['position'] == 2

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

    def test_includes_active_cars_when_class_position_zero(self):
        """Cars with class position zero are treated as inactive and filtered out."""
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

        assert len(result) == 1
        assert [d['car_idx'] for d in result] == [2]

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

    def test_gets_positions(self):
        """Test retrieves positions from iRacing."""
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
        assert result[0]['position'] == 1
        assert result[1]['position'] == 2

    def test_sorts_by_position(self):
        """Test results sorted by position."""
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


class TestPaceCarAndSpectatorFiltering:
    """Test cases for pace car and spectator filtering."""

    def test_filters_pace_car_by_name(self):
        """Test pace car filtered out by name."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        drivers = [
            {'CarIdx': 0, 'UserName': 'Pace Car', 'CarNumber': '0', 'CarClassID': 11},
            {'CarIdx': 1, 'UserID': '101', 'UserName': 'Driver 1', 'CarNumber': '1', 'CarClassID': 2}
        ]

        live_data = {
            'CarIdxLap': [10, 10],
            'CarIdxLapDistPct': [0.5, 0.5],
            'CarIdxClassPosition': [-1, 1]  # Pace car has -1
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.calculate_real_time_positions(make_drivers_dict(drivers))

        # Should only include real driver, not pace car
        assert len(result) == 1
        assert result[0]['car_idx'] == 1

    def test_filters_spectator_by_missing_car_number(self):
        """Test spectators filtered by missing car number."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        drivers = [
            {'CarIdx': 0, 'UserID': '999', 'UserName': 'Spectator', 'CarNumber': '', 'CarClassID': 2},
            {'CarIdx': 1, 'UserID': '101', 'UserName': 'Driver 1', 'CarNumber': '1', 'CarClassID': 2}
        ]

        live_data = {
            'CarIdxLap': [10, 10],
            'CarIdxLapDistPct': [0.5, 0.5],
            'CarIdxClassPosition': [-1, 1]
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.calculate_real_time_positions(make_drivers_dict(drivers))

        # Should only include real driver, not spectator
        assert len(result) == 1
        assert result[0]['car_idx'] == 1

    def test_filters_spectator_by_zero_car_number(self):
        """Test spectators filtered by car number '0'."""
        mock_ir = MagicMock()
        calculator = PositionCalculator(mock_ir)

        drivers = [
            {'CarIdx': 0, 'UserID': '999', 'UserName': 'Spectator', 'CarNumber': '0', 'CarClassID': 2},
            {'CarIdx': 1, 'UserID': '101', 'UserName': 'Driver 1', 'CarNumber': '1', 'CarClassID': 2}
        ]

        live_data = {
            'CarIdxLap': [10, 10],
            'CarIdxLapDistPct': [0.5, 0.5],
            'CarIdxClassPosition': [-1, 1]
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.calculate_real_time_positions(make_drivers_dict(drivers))

        # Should only include real driver, not spectator with car number '0'
        assert len(result) == 1
        assert result[0]['car_idx'] == 1

    def test_spectator_class_filtering_multiclass(self):
        """Test spectator sees only selected class in multi-class race."""
        mock_ir = MagicMock()
        mock_ir.__getitem__.return_value = 0  # Spectator is car 0

        calculator = PositionCalculator(mock_ir)

        drivers = [
            {'CarIdx': 0, 'UserID': '999', 'UserName': 'Spectator', 'CarNumber': '', 'CarClassID': 2},  # GT4 spectator
            {'CarIdx': 1, 'UserID': '101', 'UserName': 'Driver 1', 'CarNumber': '1', 'CarClassID': 1},  # GT3
            {'CarIdx': 2, 'UserID': '102', 'UserName': 'Driver 2', 'CarNumber': '2', 'CarClassID': 2},  # GT4
            {'CarIdx': 3, 'UserID': '103', 'UserName': 'Driver 3', 'CarNumber': '3', 'CarClassID': 2}   # GT4
        ]

        # Identify player (spectator with GT4 class)
        calculator.identify_player(make_drivers_dict(drivers))
        assert calculator.player_car_idx == 0
        assert calculator.player_car_class_id == 2  # GT4

        # Calculate positions
        live_data = {
            'CarIdxLap': [10, 10, 10, 10],
            'CarIdxLapDistPct': [0.5, 0.9, 0.8, 0.7],
            'CarIdxClassPosition': [-1, 1, 1, 2]
        }

        mock_ir.__getitem__.side_effect = lambda key: live_data[key]

        result = calculator.calculate_real_time_positions(make_drivers_dict(drivers))

        # Should only include GT4 cars (class 2), not spectator or GT3
        assert len(result) == 2
        assert all(d['driver_info']['CarClassID'] == 2 for d in result)
        assert result[0]['car_idx'] == 2
        assert result[1]['car_idx'] == 3


class TestUpdateSpectatedCar:
    """Test cases for spectated car tracking via CamCarIdx."""

    def test_spectated_car_set_from_cam_car_idx(self):
        """CamCarIdx value is stored as spectated_car_idx."""
        mock_ir = MagicMock()
        mock_ir.__getitem__ = Mock(side_effect=lambda key: {
            'CamCarIdx': 5,
            'CamCameraState': 0,
        }[key])
        calculator = PositionCalculator(mock_ir)
        calculator.update_spectated_car()
        assert calculator.spectated_car_idx == 5

    def test_spectated_car_none_when_scenic_camera(self):
        """Scenic camera (bit 0x0002) should not track a specific car."""
        mock_ir = MagicMock()
        mock_ir.__getitem__ = Mock(side_effect=lambda key: {
            'CamCarIdx': 5,
            'CamCameraState': 0x0002,
        }[key])
        calculator = PositionCalculator(mock_ir)
        calculator.update_spectated_car()
        assert calculator.spectated_car_idx is None

    def test_spectated_car_none_when_cam_car_idx_negative(self):
        """Negative CamCarIdx means no car is being spectated."""
        mock_ir = MagicMock()
        mock_ir.__getitem__ = Mock(side_effect=lambda key: {
            'CamCarIdx': -1,
            'CamCameraState': 0,
        }[key])
        calculator = PositionCalculator(mock_ir)
        calculator.update_spectated_car()
        assert calculator.spectated_car_idx is None

    def test_spectated_car_none_when_cam_car_idx_missing(self):
        """Missing CamCarIdx telemetry field results in None."""
        mock_ir = MagicMock()
        mock_ir.__getitem__ = Mock(side_effect=KeyError('CamCarIdx'))
        calculator = PositionCalculator(mock_ir)
        calculator.update_spectated_car()
        assert calculator.spectated_car_idx is None

    def test_spectated_car_updates_each_call(self):
        """Spectated car changes as spectator switches cameras."""
        mock_ir = MagicMock()
        cam_values = [5, 10]
        call_count = [0]

        def get_item(key):
            if key == 'CamCarIdx':
                val = cam_values[call_count[0]]
                call_count[0] += 1
                return val
            if key == 'CamCameraState':
                return 0
            raise KeyError(key)

        mock_ir.__getitem__ = Mock(side_effect=get_item)
        calculator = PositionCalculator(mock_ir)

        calculator.update_spectated_car()
        assert calculator.spectated_car_idx == 5

        calculator.update_spectated_car()
        assert calculator.spectated_car_idx == 10

    def test_spectated_car_with_non_scenic_camera_state_bits(self):
        """Other CamCameraState bits (e.g., 0x0001, 0x0051) don't affect tracking."""
        mock_ir = MagicMock()
        mock_ir.__getitem__ = Mock(side_effect=lambda key: {
            'CamCarIdx': 22,
            'CamCameraState': 81,  # 0x51 — has bits set but NOT 0x0002
        }[key])
        calculator = PositionCalculator(mock_ir)
        calculator.update_spectated_car()
        assert calculator.spectated_car_idx == 22

    def test_spectated_car_none_when_cam_camera_state_missing(self):
        """Missing CamCameraState defaults to 0 (not scenic)."""
        mock_ir = MagicMock()

        def get_item(key):
            if key == 'CamCarIdx':
                return 5
            raise KeyError(key)

        mock_ir.__getitem__ = Mock(side_effect=get_item)
        calculator = PositionCalculator(mock_ir)
        calculator.update_spectated_car()
        assert calculator.spectated_car_idx == 5
