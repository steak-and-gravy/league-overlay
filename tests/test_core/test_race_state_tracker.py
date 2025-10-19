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
from unittest.mock import Mock
from core.race_state_tracker import RaceStateTracker


class TestInitialState:
    """Test cases for initial tracker state."""

    def test_initial_state_is_racing(self):
        """Test tracker starts in racing state."""
        tracker = RaceStateTracker()
        assert tracker.is_racing() is True
        assert tracker.is_checkered() is False

    def test_initial_no_finished_drivers(self):
        """Test no drivers are finished initially."""
        tracker = RaceStateTracker()
        assert len(tracker.finished_drivers) == 0
        assert tracker.has_leader_finished() is False

    def test_initial_leader_state(self):
        """Test initial leader tracking state."""
        tracker = RaceStateTracker()
        assert tracker.has_leader_finished() is False


class TestCheckeredFlag:
    """Test cases for checkered flag state."""

    def test_set_checkered_flag(self):
        """Test setting checkered flag transitions state."""
        tracker = RaceStateTracker()
        tracker.set_checkered_flag()

        assert tracker.is_checkered() is True
        assert tracker.is_racing() is False

    def test_is_checkered_before_and_after(self):
        """Test is_checkered transitions correctly."""
        tracker = RaceStateTracker()
        assert tracker.is_checkered() is False

        tracker.set_checkered_flag()
        assert tracker.is_checkered() is True


class TestDriverFinish:
    """Test cases for marking drivers as finished."""

    def test_mark_driver_finished(self):
        """Test marking a driver as finished."""
        tracker = RaceStateTracker()
        tracker.set_checkered_flag()

        tracker.mark_driver_finished(
            car_idx=2,
            finish_time=123.45,
            official_position=2,
            finish_lap=50
        )

        assert tracker.is_driver_finished(2) is True
        assert tracker.get_finish_time(2) == 123.45
        assert 2 in tracker.finished_drivers

    def test_mark_multiple_drivers_finished(self):
        """Test marking multiple drivers as finished."""
        tracker = RaceStateTracker()
        tracker.set_checkered_flag()

        tracker.mark_driver_finished(2, 100.0, 1, 50)
        tracker.mark_driver_finished(3, 102.5, 2, 50)
        tracker.mark_driver_finished(4, 105.0, 3, 50)

        assert len(tracker.finished_drivers) == 3
        assert tracker.is_driver_finished(2) is True
        assert tracker.is_driver_finished(3) is True
        assert tracker.is_driver_finished(4) is True

    def test_mark_same_driver_twice_idempotent(self):
        """Test marking same driver twice doesn't duplicate."""
        tracker = RaceStateTracker()
        tracker.set_checkered_flag()

        tracker.mark_driver_finished(2, 100.0, 1, 50)
        tracker.mark_driver_finished(2, 105.0, 1, 50)

        assert len(tracker.finished_drivers) == 1
        # First time should be recorded
        assert tracker.get_finish_time(2) == 100.0

    def test_is_driver_finished_for_unfinished(self):
        """Test is_driver_finished returns False for unfinished drivers."""
        tracker = RaceStateTracker()
        assert tracker.is_driver_finished(99) is False

    def test_get_finish_time_for_unfinished(self):
        """Test get_finish_time returns None for unfinished drivers."""
        tracker = RaceStateTracker()
        assert tracker.get_finish_time(99) is None


class TestLeaderFinish:
    """Test cases for leader finish tracking."""

    def test_set_leader_finished_flag(self):
        """Test marking leader finished flag."""
        tracker = RaceStateTracker()
        tracker.set_checkered_flag()

        tracker.set_leader_finished_flag()

        assert tracker.has_leader_finished() is True

    def test_leader_finished_flag_only_sets_boolean(self):
        """Test set_leader_finished_flag only sets flag, doesn't mark driver finished."""
        tracker = RaceStateTracker()
        tracker.set_checkered_flag()

        tracker.set_leader_finished_flag()

        # Flag should be true, but no drivers marked as finished
        assert tracker.has_leader_finished() is True
        assert len(tracker.finished_drivers) == 0


class TestFinishGaps:
    """Test cases for finish gap calculations."""

    def test_get_finish_gap_basic(self):
        """Test basic finish gap calculation."""
        tracker = RaceStateTracker()
        tracker.set_checkered_flag()

        tracker.mark_driver_finished(1, 100.0, 1, 50)
        tracker.mark_driver_finished(2, 102.5, 2, 50)

        gap = tracker.get_finish_gap(car_ahead_idx=1, car_behind_idx=2)
        assert gap == 2.5

    def test_get_finish_gap_multiple_drivers(self):
        """Test finish gaps with multiple drivers."""
        tracker = RaceStateTracker()
        tracker.set_checkered_flag()

        tracker.mark_driver_finished(1, 100.0, 1, 50)
        tracker.mark_driver_finished(2, 103.0, 2, 50)
        tracker.mark_driver_finished(3, 108.5, 3, 50)

        # Gap between P1 and P2
        assert tracker.get_finish_gap(1, 2) == 3.0

        # Gap between P2 and P3
        assert tracker.get_finish_gap(2, 3) == 5.5

        # Gap between P1 and P3
        assert tracker.get_finish_gap(1, 3) == 8.5

    def test_get_finish_gap_unfinished_drivers(self):
        """Test finish gap returns None for unfinished drivers."""
        tracker = RaceStateTracker()
        tracker.set_checkered_flag()

        tracker.mark_driver_finished(1, 100.0, 1, 50)

        # Driver 2 hasn't finished
        gap = tracker.get_finish_gap(car_ahead_idx=1, car_behind_idx=2)
        assert gap is None

    def test_get_finish_gap_both_unfinished(self):
        """Test finish gap returns None when both drivers unfinished."""
        tracker = RaceStateTracker()
        gap = tracker.get_finish_gap(car_ahead_idx=1, car_behind_idx=2)
        assert gap is None


class TestSnapshots:
    """Test cases for snapshot management."""

    def test_update_snapshot(self):
        """Test creating and updating driver snapshot."""
        tracker = RaceStateTracker()

        snapshot_data = {
            'position': 1,
            'gap': None,
            'laps_completed': 50,
            'driver_info': {'UserName': 'Test Driver', 'CarNumber': '1'}
        }

        tracker.update_snapshot(car_idx=5, snapshot_data=snapshot_data)
        retrieved = tracker.get_snapshot(car_idx=5)

        assert retrieved == snapshot_data

    def test_get_snapshot_nonexistent(self):
        """Test getting snapshot for nonexistent driver returns None."""
        tracker = RaceStateTracker()
        assert tracker.get_snapshot(car_idx=99) is None

    def test_update_snapshot_overwrites(self):
        """Test updating snapshot overwrites previous data."""
        tracker = RaceStateTracker()

        tracker.update_snapshot(5, {'position': 1})
        tracker.update_snapshot(5, {'position': 2, 'gap': '1.5'})

        retrieved = tracker.get_snapshot(5)
        assert retrieved == {'position': 2, 'gap': '1.5'}

    def test_mark_finished_updates_snapshot_position(self):
        """Test marking driver finished updates snapshot with official position."""
        tracker = RaceStateTracker()
        tracker.set_checkered_flag()

        # Create snapshot first
        snapshot = {'position': 2, 'driver_info': {'UserName': 'Driver 2'}}
        tracker.update_snapshot(2, snapshot)

        # Mark as finished
        tracker.mark_driver_finished(2, 100.0, official_position=3, finish_lap=50)

        # Snapshot should be updated with official position
        retrieved = tracker.get_snapshot(2)
        assert retrieved['official_position'] == 3


class TestReset:
    """Test cases for reset functionality."""

    def test_reset_clears_all_state(self):
        """Test reset clears all tracking data."""
        tracker = RaceStateTracker()
        tracker.set_checkered_flag()
        tracker.set_leader_finished_flag()
        tracker.mark_driver_finished(1, 100.0, 1, 50)
        tracker.mark_driver_finished(2, 102.5, 2, 50)
        tracker.update_snapshot(2, {'position': 2})

        tracker.reset()

        # All state should be cleared
        assert tracker.is_racing() is True
        assert tracker.is_checkered() is False
        assert tracker.has_leader_finished() is False
        assert len(tracker.finished_drivers) == 0
        assert len(tracker.finish_times) == 0
        assert len(tracker.driver_snapshots) == 0

    def test_reset_allows_new_race(self):
        """Test reset allows tracking new race from clean state."""
        tracker = RaceStateTracker()

        # First race
        tracker.set_checkered_flag()
        tracker.mark_driver_finished(1, 100.0, 1, 50)

        # Reset for new race
        tracker.reset()

        # New race
        tracker.set_checkered_flag()
        tracker.mark_driver_finished(5, 200.0, 1, 60)

        assert tracker.is_driver_finished(5) is True
        assert tracker.is_driver_finished(1) is False  # Old race data cleared


class TestRecalculateFinishGaps:
    """Test cases for division-based finish gap recalculation."""

    def test_recalculate_basic(self):
        """Test basic division gap recalculation."""
        tracker = RaceStateTracker()
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
        tracker.update_snapshot(1, {'driver_info': {'UserName': 'Driver 1'}})
        tracker.update_snapshot(2, {'driver_info': {'UserName': 'Driver 2'}})

        tracker.mark_driver_finished(1, 100.0, 1, 50)
        tracker.mark_driver_finished(2, 102.5, 2, 50)

        # Recalculate gaps
        tracker.recalculate_all_finish_gaps(current_session, get_color)

        # Check that official positions were updated
        snap1 = tracker.get_snapshot(1)
        snap2 = tracker.get_snapshot(2)

        assert snap1['official_position'] == 1
        assert snap2['official_position'] == 2

    def test_recalculate_different_divisions(self):
        """Test gap recalculation with multiple divisions."""
        tracker = RaceStateTracker()
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
        tracker.update_snapshot(1, {'driver_info': {'CarNumber': '1'}})
        tracker.update_snapshot(2, {'driver_info': {'CarNumber': '2'}})
        tracker.update_snapshot(3, {'driver_info': {'CarNumber': '3'}})
        tracker.update_snapshot(4, {'driver_info': {'CarNumber': '4'}})

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
        assert snap3.get('finish_gap') == 5.0  # 105 - 100

        snap4 = tracker.get_snapshot(4)
        assert snap4.get('finish_gap') == 6.0  # 108 - 102

    def test_recalculate_with_lap_gaps(self):
        """Test gap recalculation includes lap gaps."""
        tracker = RaceStateTracker()
        tracker.set_checkered_flag()

        current_session = {
            'ResultsPositions': [
                {'CarIdx': 1, 'ClassPosition': 0},
                {'CarIdx': 2, 'ClassPosition': 1},
            ]
        }

        def get_color(driver_info):
            return 'blue'

        tracker.update_snapshot(1, {'driver_info': {'UserName': 'D1'}})
        tracker.update_snapshot(2, {'driver_info': {'UserName': 'D2'}})

        # Car 1 finishes on lap 50, Car 2 finishes on lap 48 (lapped)
        tracker.mark_driver_finished(1, 100.0, 1, finish_lap=50)
        tracker.mark_driver_finished(2, 102.5, 2, finish_lap=48)

        tracker.recalculate_all_finish_gaps(current_session, get_color)

        snap2 = tracker.get_snapshot(2)
        assert snap2.get('finish_lap_gap') == 2  # 50 - 48

    def test_recalculate_handles_missing_session_data(self):
        """Test recalculation handles missing session data gracefully."""
        tracker = RaceStateTracker()
        tracker.set_checkered_flag()

        # Empty session
        current_session = {}

        def get_color(driver_info):
            return 'blue'

        tracker.update_snapshot(1, {'driver_info': {'UserName': 'Driver 1'}})
        tracker.mark_driver_finished(1, 100.0, 1, 50)

        # Should not crash
        tracker.recalculate_all_finish_gaps(current_session, get_color)

    def test_recalculate_handles_invalid_session_data(self):
        """Test recalculation handles invalid session data gracefully."""
        tracker = RaceStateTracker()
        tracker.set_checkered_flag()

        # Invalid session data
        current_session = {'ResultsPositions': None}

        def get_color(driver_info):
            return 'blue'

        tracker.update_snapshot(1, {'driver_info': {'UserName': 'Driver 1'}})
        tracker.mark_driver_finished(1, 100.0, 1, 50)

        # Should not crash
        tracker.recalculate_all_finish_gaps(current_session, get_color)


class TestEdgeCases:
    """Test edge cases and unusual scenarios."""

    def test_mark_finished_before_checkered(self):
        """Test marking driver finished before checkered flag."""
        tracker = RaceStateTracker()

        # Mark finished without checkered flag
        tracker.mark_driver_finished(1, 100.0, 1, 50)

        # Should still work
        assert tracker.is_driver_finished(1) is True

    def test_zero_finish_time(self):
        """Test handling zero finish time."""
        tracker = RaceStateTracker()
        tracker.mark_driver_finished(1, 0.0, 1, 50)

        assert tracker.get_finish_time(1) == 0.0

    def test_negative_finish_time(self):
        """Test handling negative finish time (edge case)."""
        tracker = RaceStateTracker()
        tracker.mark_driver_finished(1, -100.0, 1, 50)

        assert tracker.get_finish_time(1) == -100.0

    def test_large_car_indices(self):
        """Test handling large car indices."""
        tracker = RaceStateTracker()
        tracker.mark_driver_finished(9999, 100.0, 1, 50)

        assert tracker.is_driver_finished(9999) is True
