"""Tests for core.race_state_tracker module.

Tests cover:
- Initial state and reset functionality
- Checkered flag state transitions
- Driver finish tracking
- Leader finish tracking
- Snapshot management
- Finish gap calculations
- Division-based gap recalculation
"""

import pytest
from unittest.mock import Mock, MagicMock
from core.race_state_tracker import RaceStateTracker
from core.driver_state import DriverState


@pytest.fixture
def mock_ir():
    """Create a mock iRacing SDK object."""
    return Mock()


class TestInitialState:
    """Test cases for initial tracker state."""

    def test_initial_state_is_racing(self, mock_ir):
        """Test tracker starts in racing state."""
        tracker = RaceStateTracker(mock_ir)
        assert tracker.is_racing() is True
        assert tracker.is_checkered() is False

    def test_initial_no_finished_drivers(self, mock_ir):
        """Test no drivers are finished initially."""
        tracker = RaceStateTracker(mock_ir)
        assert len(tracker.finished_drivers) == 0
        assert tracker.has_leader_finished() is False

    def test_initial_leader_state(self, mock_ir):
        """Test initial leader tracking state."""
        tracker = RaceStateTracker(mock_ir)
        assert tracker.has_leader_finished() is False


class TestCheckeredFlag:
    """Test cases for checkered flag state."""

    def test_set_checkered_flag(self, mock_ir):
        """Test setting checkered flag transitions state."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()

        assert tracker.is_checkered() is True
        assert tracker.is_racing() is False

    def test_is_checkered_before_and_after(self, mock_ir):
        """Test is_checkered transitions correctly."""
        tracker = RaceStateTracker(mock_ir)
        assert tracker.is_checkered() is False

        tracker.set_checkered_flag()
        assert tracker.is_checkered() is True


class TestDriverFinish:
    """Test cases for marking drivers as finished."""

    def test_mark_driver_finished(self, mock_ir):
        """Test marking a driver as finished."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()

        tracker.mark_driver_finished(
            car_idx=2,
            official_position=2
        )

        assert tracker.is_driver_finished(2) is True
        assert 2 in tracker.finished_drivers

    def test_mark_multiple_drivers_finished(self, mock_ir):
        """Test marking multiple drivers as finished."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()

        tracker.mark_driver_finished(2, 1)
        tracker.mark_driver_finished(3, 2)
        tracker.mark_driver_finished(4, 3)

        assert len(tracker.finished_drivers) == 3
        assert tracker.is_driver_finished(2) is True
        assert tracker.is_driver_finished(3) is True
        assert tracker.is_driver_finished(4) is True

    def test_mark_same_driver_twice_idempotent(self, mock_ir):
        """Test marking same driver twice doesn't duplicate."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()

        tracker.mark_driver_finished(2, 1)
        tracker.mark_driver_finished(2, 1)

        assert len(tracker.finished_drivers) == 1
        # Driver should only be recorded once
        assert tracker.is_driver_finished(2) is True

    def test_is_driver_finished_for_unfinished(self, mock_ir):
        """Test is_driver_finished returns False for unfinished drivers."""
        tracker = RaceStateTracker(mock_ir)
        assert tracker.is_driver_finished(99) is False

    @pytest.mark.skip(reason="get_finish_time() method has been removed from API")
    def test_get_finish_time_for_unfinished(self, mock_ir):
        """Test get_finish_time returns None for unfinished drivers."""
        tracker = RaceStateTracker(mock_ir)
        assert tracker.get_finish_time(99) is None


class TestLeaderFinish:
    """Test cases for leader finish tracking."""

    def test_set_leader_finished_flag(self, mock_ir):
        """Test marking leader finished flag."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()

        tracker.set_leader_finished_flag()

        assert tracker.has_leader_finished() is True

    def test_leader_finished_flag_only_sets_boolean(self, mock_ir):
        """Test set_leader_finished_flag only sets flag, doesn't mark driver finished."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()

        tracker.set_leader_finished_flag()

        # Flag should be true, but no drivers marked as finished
        assert tracker.has_leader_finished() is True
        assert len(tracker.finished_drivers) == 0


@pytest.mark.skip(reason="get_finish_gap() method has been removed from API")
class TestFinishGaps:
    """Test cases for finish gap calculations."""

    def test_get_finish_gap_basic(self, mock_ir):
        """Test basic finish gap calculation."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()

        tracker.mark_driver_finished(1, 1)
        tracker.mark_driver_finished(2, 2)

        gap = tracker.get_finish_gap(car_ahead_idx=1, car_behind_idx=2)
        assert gap == 2.5

    def test_get_finish_gap_multiple_drivers(self, mock_ir):
        """Test finish gaps with multiple drivers."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()

        tracker.mark_driver_finished(1, 1)
        tracker.mark_driver_finished(2, 2)
        tracker.mark_driver_finished(3, 3)

        # Gap between P1 and P2
        assert tracker.get_finish_gap(1, 2) == 3.0

        # Gap between P2 and P3
        assert tracker.get_finish_gap(2, 3) == 5.5

        # Gap between P1 and P3
        assert tracker.get_finish_gap(1, 3) == 8.5

    def test_get_finish_gap_unfinished_drivers(self, mock_ir):
        """Test finish gap returns None for unfinished drivers."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()

        tracker.mark_driver_finished(1, 1)

        # Driver 2 hasn't finished
        gap = tracker.get_finish_gap(car_ahead_idx=1, car_behind_idx=2)
        assert gap is None

    def test_get_finish_gap_both_unfinished(self, mock_ir):
        """Test finish gap returns None when both drivers unfinished."""
        tracker = RaceStateTracker(mock_ir)
        gap = tracker.get_finish_gap(car_ahead_idx=1, car_behind_idx=2)
        assert gap is None


class TestSnapshots:
    """Test cases for snapshot management."""

    def test_update_snapshot(self, mock_ir):
        """Test creating and updating driver snapshot."""
        tracker = RaceStateTracker(mock_ir)

        driver_state = DriverState(
            car_idx=5,
            driver_info={'UserName': 'Test Driver', 'CarNumber': '1'},
            position=1,
            current_lap=50
        )

        tracker.update_snapshot(car_idx=5, driver_state=driver_state)
        retrieved = tracker.get_snapshot(car_idx=5)

        assert retrieved == driver_state
        assert retrieved.car_idx == 5
        assert retrieved.position == 1
        assert retrieved.current_lap == 50

    def test_get_snapshot_nonexistent(self, mock_ir):
        """Test getting snapshot for nonexistent driver returns None."""
        tracker = RaceStateTracker(mock_ir)
        assert tracker.get_snapshot(car_idx=99) is None

    def test_update_snapshot_overwrites(self, mock_ir):
        """Test updating snapshot overwrites previous data."""
        tracker = RaceStateTracker(mock_ir)

        state1 = DriverState(car_idx=5, position=1)
        tracker.update_snapshot(5, state1)

        state2 = DriverState(car_idx=5, position=2, gap_to_leader='1.5')
        tracker.update_snapshot(5, state2)

        retrieved = tracker.get_snapshot(5)
        assert retrieved == state2
        assert retrieved.position == 2
        assert retrieved.gap_to_leader == '1.5'

    def test_mark_finished_updates_snapshot_position(self, mock_ir):
        """Test marking driver finished updates snapshot with position."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()

        # Create snapshot first
        driver_state = DriverState(car_idx=2, position=2, driver_info={'UserName': 'Driver 2'})
        tracker.update_snapshot(2, driver_state)

        # Mark as finished
        tracker.mark_driver_finished(2, official_position=3)

        # Snapshot should be updated with position and marked as finished
        retrieved = tracker.get_snapshot(2)
        assert retrieved.position == 3
        assert retrieved.is_finished == True


class TestReset:
    """Test cases for reset functionality."""

    def test_reset_clears_all_state(self, mock_ir):
        """Test reset clears all tracking data."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()
        tracker.set_leader_finished_flag()
        tracker.mark_driver_finished(1, 1)
        tracker.mark_driver_finished(2, 2)
        tracker.update_snapshot(2, DriverState(car_idx=2, position=2))

        tracker.reset()

        # All state should be cleared
        assert tracker.is_racing() is True
        assert tracker.is_checkered() is False
        assert tracker.has_leader_finished() is False
        assert len(tracker.finished_drivers) == 0
        assert len(tracker.driver_snapshots) == 0

    def test_reset_allows_new_race(self, mock_ir):
        """Test reset allows tracking new race from clean state."""
        tracker = RaceStateTracker(mock_ir)

        # First race
        tracker.set_checkered_flag()
        tracker.mark_driver_finished(1, 1)

        # Reset for new race
        tracker.reset()

        # New race
        tracker.set_checkered_flag()
        tracker.mark_driver_finished(5, 1)

        assert tracker.is_driver_finished(5) is True
        assert tracker.is_driver_finished(1) is False  # Old race data cleared


@pytest.mark.skip(reason="recalculate_all_finish_gaps() method has been removed from API")
class TestRecalculateFinishGaps:
    """Test cases for division-based finish gap recalculation."""

    def test_recalculate_basic(self, mock_ir):
        """Test basic division gap recalculation."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()

        # Create mock session with results
        current_session = {
            'ResultsPositions': [
                {'CarIdx': 1, 'ClassPosition': 0},
                {'CarIdx': 2, 'ClassPosition': 1},
            ]
        }

        # Mock color function (all same division)
        def get_color(driver_info):
            return 'blue'

        # Create snapshots and mark as finished
        tracker.update_snapshot(1, DriverState(car_idx=1, driver_info={'UserName': 'Driver 1'}))
        tracker.update_snapshot(2, DriverState(car_idx=2, driver_info={'UserName': 'Driver 2'}))

        tracker.mark_driver_finished(1, 100.0, 1, 50)
        tracker.mark_driver_finished(2, 102.5, 2, 50)

        # Recalculate gaps
        tracker.recalculate_all_finish_gaps(current_session, get_color)

        # Check that positions were updated
        snap1 = tracker.get_snapshot(1)
        snap2 = tracker.get_snapshot(2)

        assert snap1.position == 1
        assert snap2.position == 2

    def test_recalculate_different_divisions(self, mock_ir):
        """Test gap recalculation with multiple divisions."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()

        current_session = {
            'ResultsPositions': [
                {'CarIdx': 1, 'ClassPosition': 0},  # Pro
                {'CarIdx': 2, 'ClassPosition': 1},  # Am
                {'CarIdx': 3, 'ClassPosition': 2},  # Pro
                {'CarIdx': 4, 'ClassPosition': 3},  # Am
            ]
        }

        # Mock color function for divisions
        def get_color(driver_info):
            car_num = driver_info.get('CarNumber', '0')
            return 'blue' if car_num in ['1', '3'] else 'red'

        # Create snapshots
        tracker.update_snapshot(1, DriverState(car_idx=1, driver_info={'CarNumber': '1'}))
        tracker.update_snapshot(2, DriverState(car_idx=2, driver_info={'CarNumber': '2'}))
        tracker.update_snapshot(3, DriverState(car_idx=3, driver_info={'CarNumber': '3'}))
        tracker.update_snapshot(4, DriverState(car_idx=4, driver_info={'CarNumber': '4'}))

        # Mark all as finished
        tracker.mark_driver_finished(1, 100.0, 1, 50)
        tracker.mark_driver_finished(2, 102.0, 2, 50)
        tracker.mark_driver_finished(3, 105.0, 3, 50)
        tracker.mark_driver_finished(4, 108.0, 4, 50)

        # Recalculate
        tracker.recalculate_all_finish_gaps(current_session, get_color)

        # Car 1 (Pro leader) should have no gap
        # Car 3 (Pro P2) should have gap to Car 1
        # Car 2 (Am leader) should have no gap
        # Car 4 (Am P2) should have gap to Car 2

        snap3 = tracker.get_snapshot(3)
        assert snap3.finish_gap == 5.0  # 105 - 100

        snap4 = tracker.get_snapshot(4)
        assert snap4.finish_gap == 6.0  # 108 - 102

    def test_recalculate_with_lap_gaps(self, mock_ir):
        """Test gap recalculation includes lap gaps."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()

        current_session = {
            'ResultsPositions': [
                {'CarIdx': 1, 'ClassPosition': 0},
                {'CarIdx': 2, 'ClassPosition': 1},
            ]
        }

        def get_color(driver_info):
            return 'blue'

        tracker.update_snapshot(1, DriverState(car_idx=1, driver_info={'UserName': 'D1'}))
        tracker.update_snapshot(2, DriverState(car_idx=2, driver_info={'UserName': 'D2'}))

        # Car 1 finishes on lap 50, Car 2 finishes on lap 48 (lapped)
        tracker.mark_driver_finished(1, 100.0, 1, finish_lap=50)
        tracker.mark_driver_finished(2, 102.5, 2, finish_lap=48)

        tracker.recalculate_all_finish_gaps(current_session, get_color)

        snap2 = tracker.get_snapshot(2)
        assert snap2.finish_lap_gap == 2  # 50 - 48

    def test_recalculate_handles_missing_session_data(self, mock_ir):
        """Test recalculation handles missing session data gracefully."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()

        # Empty session
        current_session = {}

        def get_color(driver_info):
            return 'blue'

        tracker.update_snapshot(1, DriverState(car_idx=1, driver_info={'UserName': 'Driver 1'}))
        tracker.mark_driver_finished(1, 100.0, 1, 50)

        # Should not crash
        tracker.recalculate_all_finish_gaps(current_session, get_color)

    def test_recalculate_handles_invalid_session_data(self, mock_ir):
        """Test recalculation handles invalid session data gracefully."""
        tracker = RaceStateTracker(mock_ir)
        tracker.set_checkered_flag()

        # Invalid session data
        current_session = {'ResultsPositions': None}

        def get_color(driver_info):
            return 'blue'

        tracker.update_snapshot(1, DriverState(car_idx=1, driver_info={'UserName': 'Driver 1'}))
        tracker.mark_driver_finished(1, 100.0, 1, 50)

        # Should not crash
        tracker.recalculate_all_finish_gaps(current_session, get_color)


class TestEdgeCases:
    """Test edge cases and unusual scenarios."""

    def test_mark_finished_before_checkered(self, mock_ir):
        """Test marking driver finished before checkered flag."""
        tracker = RaceStateTracker(mock_ir)

        # Mark finished without checkered flag
        tracker.mark_driver_finished(1, 1)

        # Should still work
        assert tracker.is_driver_finished(1) is True

    @pytest.mark.skip(reason="get_finish_time() method has been removed from API")
    def test_zero_finish_time(self, mock_ir):
        """Test handling zero finish time."""
        tracker = RaceStateTracker(mock_ir)
        tracker.mark_driver_finished(1, 1)

        assert tracker.get_finish_time(1) == 0.0

    @pytest.mark.skip(reason="get_finish_time() method has been removed from API")
    def test_negative_finish_time(self, mock_ir):
        """Test handling negative finish time (edge case)."""
        tracker = RaceStateTracker(mock_ir)
        tracker.mark_driver_finished(1, 1)

        assert tracker.get_finish_time(1) == -100.0

    def test_large_car_indices(self, mock_ir):
        """Test handling large car indices."""
        tracker = RaceStateTracker(mock_ir)
        tracker.mark_driver_finished(9999, 1)

        assert tracker.is_driver_finished(9999) is True


class TestStartingPositionsLoading:
    """Tests for loading and consuming qualifying starting positions."""

    def test_load_starting_positions_parses_string_values(self):
        """QualifyResultsInfo string values should still populate integer car indices."""
        mock_ir = MagicMock()
        tracker = RaceStateTracker(mock_ir)

        mock_ir.__getitem__.side_effect = lambda key: {
            'QualifyResultsInfo': {
                'Results': [
                    {'CarIdx': '1', 'ClassPosition': '0'},
                    {'CarIdx': '5', 'ClassPosition': '2'},
                ]
            }
        }.get(key)

        tracker.load_starting_positions_from_qualify()

        assert tracker.get_starting_position(1) == 1
        assert tracker.get_starting_position(5) == 3
        assert tracker.starting_positions_updated is True

    def test_load_starting_positions_finds_open_qualify_session(self):
        """SessionInfo fallback should match Open/Lone Qualify variants."""
        mock_ir = MagicMock()
        tracker = RaceStateTracker(mock_ir)

        mock_ir.__getitem__.side_effect = lambda key: {
            'QualifyResultsInfo': {'Results': []},
            'SessionInfo': {
                'Sessions': [
                    {
                        'SessionType': 'Open Qualify',
                        'ResultsPositions': [
                            {'CarIdx': 7, 'ClassPosition': 0},
                            {'CarIdx': 9, 'ClassPosition': 1},
                        ]
                    }
                ]
            }
        }.get(key)

        tracker.load_starting_positions_from_qualify()

        assert tracker.get_starting_position(7) == 1
        assert tracker.get_starting_position(9) == 2
        assert tracker.starting_positions_updated is True


@pytest.mark.skip(reason="recalculate_all_finish_gaps() method has been removed from API")
class TestFinishGapWithPositionSwaps:
    """Test cases for finish gap calculation when positions swap at finish line.

    Tests for bug fix (10/21/25): iRacing's ClassPosition can be inconsistent with
    actual finish times when cars cross close together. Need to sort by finish_times
    instead of position to avoid negative gaps.
    """

    def test_finish_gap_calculation_with_position_swap_at_finish(self, mock_ir):
        """Test finish gap when two cars swap positions near finish line.

        Scenario: Car B finishes first (SessionTime=1000.0) but iRacing initially
        reports worse ClassPosition. Car A finishes second (SessionTime=1002.0)
        but has better ClassPosition. Without the fix, this causes negative gaps.
        """
        tracker = RaceStateTracker(mock_ir)

        # Create mock session with ResultsPositions (will be used in recalculate)
        mock_session = {
            'ResultsPositions': [
                {'CarIdx': 10, 'ClassPosition': 0},  # Car A gets better position from iRacing
                {'CarIdx': 11, 'ClassPosition': 1},  # Car B gets worse position from iRacing
            ]
        }

        # Mock get_driver_color function (all same division for simplicity)
        def mock_get_color(driver_info):
            return '#FFFFFF'

        # Car B finishes FIRST (SessionTime=1000.0) but reports as P2
        tracker.mark_driver_finished(11, 1000.0, official_position=2, finish_lap=50)

        # Create snapshot for car B
        tracker.driver_snapshots[11] = DriverState(
            car_idx=11,
            driver_info={'UserName': 'Driver B'},
            position=2
        )

        # Car A finishes SECOND (SessionTime=1002.0) but reports as P1
        tracker.mark_driver_finished(10, 1002.0, official_position=1, finish_lap=50)

        # Create snapshot for car A
        tracker.driver_snapshots[10] = DriverState(
            car_idx=10,
            driver_info={'UserName': 'Driver A'},
            position=1
        )

        # Recalculate gaps - this should sort by finish_times, not position
        tracker.recalculate_all_finish_gaps(mock_session, mock_get_color)

        # Car B finished first, should be division P1 (no gap)
        assert tracker.driver_snapshots[11].finish_gap is None

        # Car A finished second, should have +2.0s gap to car B (NOT negative!)
        assert tracker.driver_snapshots[10].finish_gap is not None
        finish_gap = tracker.driver_snapshots[10].finish_gap
        assert finish_gap == pytest.approx(2.0, abs=0.01)
        assert finish_gap > 0, "Gap should be positive when sorted by finish times"

    def test_finish_gap_calculation_with_unstable_positions(self, mock_ir):
        """Test finish gap when positions change after drivers finish.

        Simulates real checkered flag behavior where ClassPosition continues
        updating as more cars finish. Finish times should remain stable.
        """
        tracker = RaceStateTracker(mock_ir)

        # Three cars finish in order A, B, C
        tracker.mark_driver_finished(1, 1000.0, official_position=1, finish_lap=50)
        tracker.mark_driver_finished(2, 1005.0, official_position=2, finish_lap=50)
        tracker.mark_driver_finished(3, 1010.0, official_position=3, finish_lap=50)

        # Create snapshots
        for car_idx in [1, 2, 3]:
            tracker.driver_snapshots[car_idx] = DriverState(
                car_idx=car_idx,
                driver_info={'UserName': f'Driver {car_idx}'},
                position=car_idx
            )

        mock_session = {
            'ResultsPositions': [
                {'CarIdx': 1, 'ClassPosition': 0},
                {'CarIdx': 2, 'ClassPosition': 1},
                {'CarIdx': 3, 'ClassPosition': 2},
            ]
        }

        def mock_get_color(driver_info):
            return '#FF0000'

        # First recalculation
        tracker.recalculate_all_finish_gaps(mock_session, mock_get_color)

        gap_2_first = tracker.driver_snapshots[2].finish_gap
        gap_3_first = tracker.driver_snapshots[3].finish_gap

        # Now simulate positions changing (Car 3 and Car 2 swap in official standings)
        tracker.driver_snapshots[2].position = 3
        tracker.driver_snapshots[3].position = 2

        mock_session['ResultsPositions'] = [
            {'CarIdx': 1, 'ClassPosition': 0},
            {'CarIdx': 3, 'ClassPosition': 1},  # Swapped!
            {'CarIdx': 2, 'ClassPosition': 2},  # Swapped!
        ]

        # Recalculate with new positions
        tracker.recalculate_all_finish_gaps(mock_session, mock_get_color)

        gap_2_second = tracker.driver_snapshots[2].finish_gap
        gap_3_second = tracker.driver_snapshots[3].finish_gap

        # Gaps should REMAIN THE SAME because finish_times don't change
        assert gap_2_second == gap_2_first == pytest.approx(5.0, abs=0.01)
        assert gap_3_second == gap_3_first == pytest.approx(5.0, abs=0.01)

        # All gaps should be positive
        assert gap_2_second > 0
        assert gap_3_second > 0

    def test_finished_with_divisions_sorting(self, mock_ir):
        """Test that finished_with_divisions list is sorted for consistent search order.

        Bug: finished_with_divisions was built from iterating a Set, so searching
        for "car ahead" happened in random order even with correct division positions.
        Fix: Sort finished_with_divisions by finish_times before Step 4.
        """
        tracker = RaceStateTracker(mock_ir)

        # Create 5 cars in same division, finish in non-sequential car_idx order
        # to simulate unordered set iteration
        finish_order = [
            (15, 1000.0, 1),  # Car 15 finishes first
            (3, 1005.0, 2),   # Car 3 finishes second
            (42, 1010.0, 3),  # Car 42 finishes third
            (7, 1015.0, 4),   # Car 7 finishes fourth
            (99, 1020.0, 5),  # Car 99 finishes fifth
        ]

        for car_idx, finish_time, position in finish_order:
            tracker.mark_driver_finished(car_idx, finish_time, official_position=position, finish_lap=50)
            tracker.driver_snapshots[car_idx] = DriverState(
                car_idx=car_idx,
                driver_info={'UserName': f'Driver {car_idx}'},
                position=position
            )

        mock_session = {
            'ResultsPositions': [
                {'CarIdx': 15, 'ClassPosition': 0},
                {'CarIdx': 3, 'ClassPosition': 1},
                {'CarIdx': 42, 'ClassPosition': 2},
                {'CarIdx': 7, 'ClassPosition': 3},
                {'CarIdx': 99, 'ClassPosition': 4},
            ]
        }

        def mock_get_color(driver_info):
            return '#00FF00'

        tracker.recalculate_all_finish_gaps(mock_session, mock_get_color)

        # Verify gaps are calculated correctly in finish time order
        # Car 15: division leader, no gap
        assert tracker.driver_snapshots[15].finish_gap is None

        # Car 3: +5s to car 15
        assert tracker.driver_snapshots[3].finish_gap == pytest.approx(5.0, abs=0.01)

        # Car 42: +5s to car 3
        assert tracker.driver_snapshots[42].finish_gap == pytest.approx(5.0, abs=0.01)

        # Car 7: +5s to car 42
        assert tracker.driver_snapshots[7].finish_gap == pytest.approx(5.0, abs=0.01)

        # Car 99: +5s to car 7
        assert tracker.driver_snapshots[99].finish_gap == pytest.approx(5.0, abs=0.01)

        # All gaps should be positive (no negative gaps from wrong search order)
        for car_idx in [3, 42, 7, 99]:
            assert tracker.driver_snapshots[car_idx].finish_gap > 0

    def test_finish_gap_with_multiple_divisions(self, mock_ir):
        """Test finish gap calculation with multiple divisions finishing interleaved.

        Ensures division positions are calculated correctly per division when
        cars from different divisions finish in alternating order.
        """
        tracker = RaceStateTracker(mock_ir)

        # Two divisions (Red and Blue), finish in interleaved order
        # Red: cars 1, 3, 5
        # Blue: cars 2, 4, 6
        finish_data = [
            (1, 1000.0, 1, 'red'),   # Red P1
            (2, 1005.0, 2, 'blue'),  # Blue P1
            (3, 1010.0, 3, 'red'),   # Red P2
            (4, 1015.0, 4, 'blue'),  # Blue P2
            (5, 1020.0, 5, 'red'),   # Red P3
            (6, 1025.0, 6, 'blue'),  # Blue P3
        ]

        for car_idx, finish_time, position, color in finish_data:
            tracker.mark_driver_finished(car_idx, finish_time, official_position=position, finish_lap=50)
            tracker.driver_snapshots[car_idx] = DriverState(
                car_idx=car_idx,
                driver_info={'UserName': f'Driver {car_idx}', 'color': color},
                position=position
            )

        mock_session = {
            'ResultsPositions': [
                {'CarIdx': i[0], 'ClassPosition': i[2] - 1} for i in finish_data
            ]
        }

        def mock_get_color(driver_info):
            return driver_info.get('color', '#FFFFFF')

        tracker.recalculate_all_finish_gaps(mock_session, mock_get_color)

        # Red division gaps
        assert tracker.driver_snapshots[1].finish_gap is None  # Leader
        assert tracker.driver_snapshots[3].finish_gap == pytest.approx(10.0, abs=0.01)  # +10s to car 1
        assert tracker.driver_snapshots[5].finish_gap == pytest.approx(10.0, abs=0.01)  # +10s to car 3

        # Blue division gaps
        assert tracker.driver_snapshots[2].finish_gap is None  # Leader
        assert tracker.driver_snapshots[4].finish_gap == pytest.approx(10.0, abs=0.01)  # +10s to car 2
        assert tracker.driver_snapshots[6].finish_gap == pytest.approx(10.0, abs=0.01)  # +10s to car 4

        # All gaps positive
        for car_idx in [3, 4, 5, 6]:
            assert tracker.driver_snapshots[car_idx].finish_gap > 0


class TestSessionStateFallback:
    """SessionState fallback behavior when iRacing reports transient None."""

    def test_update_finish_status_handles_none_session_state(self, mock_ir):
        """None SessionState should be treated as racing and not crash."""
        def mock_getitem(key):
            if key == 'SessionState':
                return None
            raise KeyError(key)

        mock_ir.__getitem__ = Mock(side_effect=mock_getitem)
        tracker = RaceStateTracker(mock_ir)

        tracker.update_finish_status(lambda: 0)

        assert tracker.is_checkered() is False

    def test_handle_disconnected_drivers_handles_none_session_state(self, mock_ir):
        """Disconnected restoration should not crash when SessionState is None."""
        def mock_getitem(key):
            if key == 'SessionState':
                return None
            if key == 'RaceLaps':
                return 0
            raise KeyError(key)

        mock_ir.__getitem__ = Mock(side_effect=mock_getitem)
        tracker = RaceStateTracker(mock_ir)
        tracker.update_snapshot(0, DriverState(
            car_idx=0,
            driver_info={'UserName': 'Driver 0', 'CarClassID': 1},
            position=1,
            current_lap=3,
            lap_pct=0.5,
        ))

        active_drivers = []
        tracker.handle_disconnected_drivers(
            active_drivers=active_drivers,
            session_data={},
            get_position_from_results_fn=lambda *_args: 1
        )

        assert len(active_drivers) == 1
        assert active_drivers[0]['car_idx'] == 0
        assert active_drivers[0]['disconnected'] is True
