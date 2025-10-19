"""Unit tests for TelemetryProcessor core logic.

These tests focus on specific methods and logic within TelemetryProcessor
without requiring full iRacing SDK mocking.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from core.telemetry_processor import TelemetryProcessor
from core.gap_calculator import GapCalculator
from core.race_state_tracker import RaceStateTracker
from core.division_manager import DivisionManager


class TestFinishedDriverSeparation:
    """Unit tests for Scenario #2 fix: Separating finished and racing drivers.

    These tests verify that finished drivers are not mixed with racing drivers
    during position calculations, preventing ghost position bugs when drivers
    finish and disconnect.

    Bug Scenario:
    - Driver A finishes P1 with frozen track position 25.8, then disconnects
    - Driver B crosses line at track position 25.95
    - BUG (before fix): Both sorted by track position → B shows ahead of A
    - FIX: Finished drivers sorted by results, racing by track position
    """

    @pytest.fixture
    def mock_dependencies(self):
        """Create minimal mock dependencies for TelemetryProcessor."""
        ir = MagicMock()
        division_manager = MagicMock(spec=DivisionManager)
        race_state_tracker = RaceStateTracker()
        gap_calculator = MagicMock(spec=GapCalculator)

        return {
            'ir': ir,
            'division_manager': division_manager,
            'race_state_tracker': race_state_tracker,
            'gap_calculator': gap_calculator
        }

    def test_finished_and_racing_drivers_are_separated(self, mock_dependencies):
        """Verify that finished drivers don't get mixed into racing driver position calculations."""
        processor = TelemetryProcessor(**mock_dependencies)
        race_state_tracker = mock_dependencies['race_state_tracker']

        # Simulate the scenario: 2 drivers finished, 2 still racing
        active_drivers = [
            {
                'car_idx': 1,
                'total_track_position': 25.8,  # Finished, frozen position
                'real_time_position': 1,
                'official_position': 1,
                'driver_info': {'UserID': 100, 'UserName': 'Driver A'},
            },
            {
                'car_idx': 2,
                'total_track_position': 25.95,  # Just finished, higher track position
                'real_time_position': 2,
                'official_position': 2,
                'driver_info': {'UserID': 200, 'UserName': 'Driver B'},
            },
            {
                'car_idx': 3,
                'total_track_position': 25.5,  # Still racing
                'real_time_position': 3,
                'official_position': 3,
                'driver_info': {'UserID': 300, 'UserName': 'Driver C'},
            },
            {
                'car_idx': 4,
                'total_track_position': 25.2,  # Still racing
                'real_time_position': 4,
                'official_position': 4,
                'driver_info': {'UserID': 400, 'UserName': 'Driver D'},
            },
        ]

        # Mark drivers 1 and 2 as finished
        race_state_tracker.mark_driver_finished(1, 1400.0, 1, 26)
        race_state_tracker.mark_driver_finished(2, 1405.0, 2, 26)

        # Test the separation logic (this is what happens in process_telemetry after our fix)
        finished_drivers = [d for d in active_drivers if race_state_tracker.is_driver_finished(d['car_idx'])]
        racing_drivers = [d for d in active_drivers if not race_state_tracker.is_driver_finished(d['car_idx'])]

        # ASSERTIONS: Verify separation worked
        assert len(finished_drivers) == 2, "Should have 2 finished drivers"
        assert len(racing_drivers) == 2, "Should have 2 racing drivers"

        assert finished_drivers[0]['car_idx'] == 1, "Driver A should be in finished list"
        assert finished_drivers[1]['car_idx'] == 2, "Driver B should be in finished list"

        assert racing_drivers[0]['car_idx'] == 3, "Driver C should be in racing list"
        assert racing_drivers[1]['car_idx'] == 4, "Driver D should be in racing list"

    def test_finished_drivers_sorted_by_results_position(self, mock_dependencies):
        """Verify finished drivers are sorted by their official results position, not track position."""
        processor = TelemetryProcessor(**mock_dependencies)
        race_state_tracker = mock_dependencies['race_state_tracker']

        # Create a mock current_session for get_position_from_results
        current_session = {
            'ResultsPositions': [
                {'CarIdx': 1, 'ClassPosition': 0},  # P1
                {'CarIdx': 2, 'ClassPosition': 1},  # P2
            ]
        }

        # Drivers with REVERSED track positions (simulate the bug scenario)
        finished_drivers = [
            {
                'car_idx': 2,
                'total_track_position': 25.95,  # HIGHER track position
                'official_position': 2,
                'driver_info': {'UserID': 200},
            },
            {
                'car_idx': 1,
                'total_track_position': 25.8,  # LOWER track position
                'official_position': 1,
                'driver_info': {'UserID': 100},
            },
        ]

        # Mark both as finished
        race_state_tracker.mark_driver_finished(1, 1400.0, 1, 26)
        race_state_tracker.mark_driver_finished(2, 1405.0, 2, 26)

        # Apply the fix logic: add final_position and sort by it
        for driver in finished_drivers:
            driver['final_position'] = processor.get_position_from_results(current_session, driver['car_idx'])

        finished_drivers.sort(key=lambda x: x.get('final_position', 999))

        # ASSERTIONS: Verify sorting is by results, NOT track position
        assert finished_drivers[0]['car_idx'] == 1, "Driver A (P1) should be first despite lower track position"
        assert finished_drivers[1]['car_idx'] == 2, "Driver B (P2) should be second despite higher track position"
        assert finished_drivers[0]['final_position'] == 1
        assert finished_drivers[1]['final_position'] == 2

    def test_racing_drivers_sorted_by_track_position(self, mock_dependencies):
        """Verify racing drivers are sorted by track position (real-time)."""
        processor = TelemetryProcessor(**mock_dependencies)
        race_state_tracker = mock_dependencies['race_state_tracker']

        racing_drivers = [
            {
                'car_idx': 4,
                'total_track_position': 25.2,  # Lower position
                'real_time_position': 4,
            },
            {
                'car_idx': 3,
                'total_track_position': 25.5,  # Higher position
                'real_time_position': 3,
            },
        ]

        # Neither is finished
        assert not race_state_tracker.is_driver_finished(3)
        assert not race_state_tracker.is_driver_finished(4)

        # Apply the fix logic: sort by track position
        racing_drivers.sort(key=lambda x: x['total_track_position'], reverse=True)
        for i, driver in enumerate(racing_drivers):
            driver['real_time_position'] = i + 1

        # ASSERTIONS: Verify sorting by track position
        assert racing_drivers[0]['car_idx'] == 3, "Driver with higher track position should be first"
        assert racing_drivers[1]['car_idx'] == 4, "Driver with lower track position should be second"
        assert racing_drivers[0]['real_time_position'] == 1
        assert racing_drivers[1]['real_time_position'] == 2

    def test_merged_list_preserves_correct_order(self, mock_dependencies):
        """Verify that merging finished + racing lists maintains correct overall order."""
        processor = TelemetryProcessor(**mock_dependencies)
        race_state_tracker = mock_dependencies['race_state_tracker']

        # Finished drivers (already in results order)
        finished_drivers = [
            {'car_idx': 1, 'final_position': 1, 'status': 'finished'},
            {'car_idx': 2, 'final_position': 2, 'status': 'finished'},
        ]

        # Racing drivers (in real-time order)
        racing_drivers = [
            {'car_idx': 3, 'real_time_position': 1, 'status': 'racing'},
            {'car_idx': 4, 'real_time_position': 2, 'status': 'racing'},
        ]

        # Apply the merge logic from our fix
        active_drivers = finished_drivers + racing_drivers

        # ASSERTIONS: Finished drivers come first, then racing
        assert len(active_drivers) == 4
        assert active_drivers[0]['car_idx'] == 1  # Finished P1
        assert active_drivers[1]['car_idx'] == 2  # Finished P2
        assert active_drivers[2]['car_idx'] == 3  # Racing P1
        assert active_drivers[3]['car_idx'] == 4  # Racing P2

        # Verify status
        assert active_drivers[0]['status'] == 'finished'
        assert active_drivers[1]['status'] == 'finished'
        assert active_drivers[2]['status'] == 'racing'
        assert active_drivers[3]['status'] == 'racing'

    def test_lapped_finished_drivers_dont_create_position_gaps(self, mock_dependencies):
        """Test that lapped drivers who finish don't create gaps in position numbers.

        Scenario: 5 lead lap drivers finished (P1-P5), 2 lapped drivers finished (P13-P14),
        7 lead lap drivers still racing (should be P6-P12).

        Bug (before fix): Racing drivers got positions 8, 9, 10... (offset by 7 total finished)
        creating a gap at P6-P7.

        Fix: "Fill the gaps" - racing drivers get available positions [6, 7, 8, 9, 10, 11, 12]
        """
        processor = TelemetryProcessor(**mock_dependencies)
        race_state_tracker = mock_dependencies['race_state_tracker']

        # Simulate: 5 lead lap finished + 2 lapped finished + 7 lead lap racing = 14 total
        active_drivers = []

        # Lead lap finished drivers (P1-P5)
        for i in range(1, 6):
            driver = {
                'car_idx': i,
                'total_track_position': 26.0 + (i * 0.1),  # Finished, frozen positions
                'driver_info': {'UserID': i * 100, 'UserName': f'Driver {i}'},
            }
            active_drivers.append(driver)
            race_state_tracker.mark_driver_finished(i, 1400.0 + i, i, 26)

        # Lapped drivers who finished (actual P13, P14)
        for idx, pos in [(13, 13), (14, 14)]:
            driver = {
                'car_idx': idx,
                'total_track_position': 25.0 + (idx * 0.1),  # 1 lap down, frozen
                'driver_info': {'UserID': idx * 100, 'UserName': f'Driver {idx}'},
            }
            active_drivers.append(driver)
            race_state_tracker.mark_driver_finished(idx, 1450.0, pos, 25)

        # Lead lap racing drivers (should be P6-P12)
        for i in range(20, 27):  # car_idx 20-26
            driver = {
                'car_idx': i,
                'total_track_position': 25.9 - ((i - 20) * 0.1),  # Still racing
                'driver_info': {'UserID': i * 100, 'UserName': f'Driver {i}'},
            }
            active_drivers.append(driver)

        # Create mock current_session with results
        current_session = {
            'ResultsPositions': [
                {'CarIdx': 1, 'ClassPosition': 0},   # P1
                {'CarIdx': 2, 'ClassPosition': 1},   # P2
                {'CarIdx': 3, 'ClassPosition': 2},   # P3
                {'CarIdx': 4, 'ClassPosition': 3},   # P4
                {'CarIdx': 5, 'ClassPosition': 4},   # P5
                {'CarIdx': 13, 'ClassPosition': 12}, # P13 (lapped)
                {'CarIdx': 14, 'ClassPosition': 13}, # P14 (lapped)
            ]
        }

        # Apply the gap-filling logic (simulate what process_telemetry does)
        finished_drivers = [d for d in active_drivers if race_state_tracker.is_driver_finished(d['car_idx'])]
        racing_drivers = [d for d in active_drivers if not race_state_tracker.is_driver_finished(d['car_idx'])]

        # Get finished positions
        for driver in finished_drivers:
            driver['final_position'] = processor.get_position_from_results(current_session, driver['car_idx'])
        finished_drivers.sort(key=lambda x: x.get('final_position', 999))

        # Sort racing by track position
        racing_drivers.sort(key=lambda x: x['total_track_position'], reverse=True)

        # Apply gap-filling algorithm
        taken_positions = {d.get('final_position') for d in finished_drivers if d.get('final_position', -1) > 0}
        total_drivers = len(finished_drivers) + len(racing_drivers)
        available_positions = [p for p in range(1, total_drivers + 1) if p not in taken_positions]

        for i, driver in enumerate(racing_drivers):
            if i < len(available_positions):
                driver['real_time_position'] = available_positions[i]

        # ASSERTIONS: Verify no gaps in positions
        assert len(finished_drivers) == 7, "Should have 7 finished drivers"
        assert len(racing_drivers) == 7, "Should have 7 racing drivers"

        # Check taken positions
        assert taken_positions == {1, 2, 3, 4, 5, 13, 14}, "Finished drivers should occupy these positions"

        # Check available positions (should fill the gaps)
        assert available_positions == [6, 7, 8, 9, 10, 11, 12], "Racing drivers should get these positions"

        # Verify racing drivers got consecutive positions P6-P12 (no gaps!)
        racing_positions = [d['real_time_position'] for d in racing_drivers]
        assert racing_positions == [6, 7, 8, 9, 10, 11, 12], "Racing drivers should have positions 6-12 with no gaps"

        # Verify finished drivers kept their correct positions
        finished_positions = sorted([d['final_position'] for d in finished_drivers])
        assert finished_positions == [1, 2, 3, 4, 5, 13, 14], "Finished drivers should keep their results positions"

        # Verify total: all positions 1-14 are assigned (no gaps, no duplicates)
        all_positions = set(racing_positions) | set(finished_positions)
        assert all_positions == set(range(1, 15)), "All positions 1-14 should be assigned exactly once"


class TestMultiClassFinishTracking:
    """Unit tests for multi-class race finish tracking.

    Tests the scenario where drivers in a slower class finish before their class
    leader has finished, but after the overall race leader has finished.
    """

    @pytest.fixture
    def mock_dependencies(self):
        """Create minimal mock dependencies."""
        ir = MagicMock()
        division_manager = MagicMock(spec=DivisionManager)
        race_state_tracker = RaceStateTracker()
        gap_calculator = MagicMock(spec=GapCalculator)

        return {
            'ir': ir,
            'division_manager': division_manager,
            'race_state_tracker': race_state_tracker,
            'gap_calculator': gap_calculator
        }

    def test_multiclass_drivers_finish_before_class_leader(self, mock_dependencies):
        """Test that drivers in slower class are marked finished even if they cross before their class leader.

        Scenario:
        - GT3 class (faster): P1-P7 overall
        - GT4 class (slower, our class): P8-P14 overall
        - GT3 P1 (overall P1) finishes first (lap 26)
        - GT4 P2 (overall P9) finishes BEFORE GT4 P1 (lap 26)
        - GT4 P1 (overall P8) finishes after (lap 26)

        BUG: GT4 P2 was NOT marked as finished because the code waited for GT4 P1 (class leader)
        to finish before tracking any GT4 drivers. In multi-class, the checkered flag is triggered
        by the overall leader (GT3 P1), so GT4 drivers can cross before their class leader.

        FIX: Track overall race leader (P1 overall, any class) using max total_track_position.
        Once overall leader finishes, start tracking ALL drivers in player's class as they cross,
        regardless of whether their class leader has finished.

        IMPLEMENTATION: Added get_overall_race_leader_idx() to find P1 overall. PHASE 2 now
        tracks overall leader's lap progression using snapshots, even if they're in different class.
        """
        processor = TelemetryProcessor(**mock_dependencies)
        race_state_tracker = mock_dependencies['race_state_tracker']

        # Set player class to GT4
        processor.player_car_class_id = 2  # GT4 = class ID 2

        # Mock iRacing data structure
        mock_ir = mock_dependencies['ir']

        # Setup driver info - GT3 and GT4 drivers
        drivers = [
            # GT3 drivers (class ID 1) - P1-P7 overall
            {'CarIdx': 1, 'UserID': 101, 'UserName': 'GT3 P1', 'CarClassID': 1},
            {'CarIdx': 2, 'UserID': 102, 'UserName': 'GT3 P2', 'CarClassID': 1},
            # ... (would have more, but 2 is enough for test)

            # GT4 drivers (class ID 2, our class) - P8-P10 overall
            {'CarIdx': 8, 'UserID': 108, 'UserName': 'GT4 P1', 'CarClassID': 2},  # Overall P8, Class P1
            {'CarIdx': 9, 'UserID': 109, 'UserName': 'GT4 P2', 'CarClassID': 2},  # Overall P9, Class P2
            {'CarIdx': 10, 'UserID': 110, 'UserName': 'GT4 P3', 'CarClassID': 2}, # Overall P10, Class P3
        ]

        # Create mock current_session
        current_session = {
            'ResultsPositions': [
                {'CarIdx': 1, 'ClassPosition': 0},   # GT3 P1 (class P1)
                {'CarIdx': 2, 'ClassPosition': 1},   # GT3 P2 (class P2)
                {'CarIdx': 8, 'ClassPosition': 0},   # GT4 P1 (class P1)
                {'CarIdx': 9, 'ClassPosition': 1},   # GT4 P2 (class P2)
                {'CarIdx': 10, 'ClassPosition': 2},  # GT4 P3 (class P3)
            ]
        }

        def get_driver_color(driver_info):
            return '#FF0000'

        # Initialize snapshots for all drivers (simulate they were racing)
        for driver in drivers:
            car_idx = driver['CarIdx']
            race_state_tracker.update_snapshot(car_idx, {
                'car_idx': car_idx,
                'current_lap': 25,
                'lap_pct': 0.5,
                'total_track_position': 25.5,
                'driver_info': driver,
            })

        # ===== CYCLE 1: Checkered flag waves, GT3 P1 approaching finish =====
        # Setup mock_ir to return proper values
        mock_ir.__getitem__.side_effect = lambda key: {
            'SessionState': 5,  # Checkered flag (>= 5)
            'DriverInfo': {'Drivers': drivers},
            'SessionTime': 1500.0,
        }.get(key)

        live_data = {
            'CarIdxLap': [0] * 64,
            'CarIdxLapDistPct': [0.0] * 64,
            'CarIdxClassPosition': [0] * 64,
        }

        # GT3 P1 at lap 25.95 (approaching finish)
        live_data['CarIdxLap'][1] = 25
        live_data['CarIdxLapDistPct'][1] = 0.95
        live_data['CarIdxClassPosition'][1] = 1  # P1 in GT3 class

        # GT4 drivers still at lap 25.5
        live_data['CarIdxLap'][8] = 25
        live_data['CarIdxLapDistPct'][8] = 0.5
        live_data['CarIdxClassPosition'][8] = 1  # P1 in GT4 class

        live_data['CarIdxLap'][9] = 25
        live_data['CarIdxLapDistPct'][9] = 0.6
        live_data['CarIdxClassPosition'][9] = 2  # P2 in GT4 class

        live_data['CarIdxLap'][10] = 25
        live_data['CarIdxLapDistPct'][10] = 0.4
        live_data['CarIdxClassPosition'][10] = 3  # P3 in GT4 class

        # Call update_finish_status - should not mark anyone finished yet
        processor.update_finish_status(live_data, current_session, get_driver_color)

        assert not race_state_tracker.is_driver_finished(1), "GT3 P1 not finished yet"
        assert not race_state_tracker.is_driver_finished(8), "GT4 P1 not finished yet"
        assert not race_state_tracker.is_driver_finished(9), "GT4 P2 not finished yet"

        # ===== CYCLE 2: GT3 P1 (overall leader) crosses finish line =====
        live_data['CarIdxLap'][1] = 26  # Lap incremented!
        live_data['CarIdxLapDistPct'][1] = 0.01

        # GT4 P2 also approaching finish (ahead of GT4 P1 on track)
        live_data['CarIdxLapDistPct'][9] = 0.95

        processor.update_finish_status(live_data, current_session, get_driver_color)

        # GT3 P1 should be marked finished (but we don't track other classes)
        # For this test, we just care that "overall leader finished" is now true

        # ===== CYCLE 3: GT4 P2 crosses finish line (BEFORE GT4 P1!) =====
        live_data['CarIdxLap'][9] = 26  # GT4 P2 lap incremented!
        live_data['CarIdxLapDistPct'][9] = 0.01

        # GT4 P1 still hasn't finished
        live_data['CarIdxLap'][8] = 25
        live_data['CarIdxLapDistPct'][8] = 0.8  # Still approaching

        processor.update_finish_status(live_data, current_session, get_driver_color)

        # KEY ASSERTION: GT4 P2 should be marked as finished
        # Even though GT4 P1 (class leader) hasn't finished yet
        # Because overall race leader finished, and GT4 P2 crossed the line
        assert race_state_tracker.is_driver_finished(9), \
            "GT4 P2 should be marked finished after crossing, even before class leader"

        assert not race_state_tracker.is_driver_finished(8), \
            "GT4 P1 should not be marked finished yet (hasn't crossed)"

        # ===== CYCLE 4: GT4 P1 crosses finish line =====
        live_data['CarIdxLap'][8] = 26  # GT4 P1 lap incremented
        live_data['CarIdxLapDistPct'][8] = 0.01

        processor.update_finish_status(live_data, current_session, get_driver_color)

        assert race_state_tracker.is_driver_finished(8), "GT4 P1 should be marked finished"

        # ===== CYCLE 5: GT4 P3 crosses finish line =====
        live_data['CarIdxLap'][10] = 26
        live_data['CarIdxLapDistPct'][10] = 0.01

        processor.update_finish_status(live_data, current_session, get_driver_color)

        assert race_state_tracker.is_driver_finished(10), "GT4 P3 should be marked finished"


class TestSessionTracking:
    """Unit tests for session change tracking using SessionID + session_type."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create minimal mock dependencies."""
        ir = MagicMock()
        division_manager = MagicMock(spec=DivisionManager)
        race_state_tracker = RaceStateTracker()
        gap_calculator = MagicMock(spec=GapCalculator)

        return {
            'ir': ir,
            'division_manager': division_manager,
            'race_state_tracker': race_state_tracker,
            'gap_calculator': gap_calculator
        }

    def test_session_change_detection_uses_session_id_and_type(self, mock_dependencies):
        """Verify session change detection uses SessionID from WeekendInfo + session_type."""
        processor = TelemetryProcessor(**mock_dependencies)

        # First session
        session_data_1 = {
            'session_id': 12345,
            'session_type': 'Practice',
        }

        # Detect change (first time, should be True)
        assert processor._detect_session_change(session_data_1) is True
        assert processor.current_session_id == 12345
        assert processor.current_session_type == 'Practice'

        # Same session (no change)
        assert processor._detect_session_change(session_data_1) is False

        # Different session type, same ID
        session_data_2 = {
            'session_id': 12345,
            'session_type': 'Race',
        }
        assert processor._detect_session_change(session_data_2) is True
        assert processor.current_session_type == 'Race'

        # Different session ID
        session_data_3 = {
            'session_id': 54321,
            'session_type': 'Race',
        }
        assert processor._detect_session_change(session_data_3) is True
        assert processor.current_session_id == 54321


class TestDriverInfoHandling:
    """Unit tests for robust DriverInfo data handling during session transitions."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create minimal mock dependencies."""
        ir = MagicMock()
        division_manager = MagicMock(spec=DivisionManager)
        race_state_tracker = RaceStateTracker()
        gap_calculator = MagicMock(spec=GapCalculator)

        return {
            'ir': ir,
            'division_manager': division_manager,
            'race_state_tracker': race_state_tracker,
            'gap_calculator': gap_calculator
        }

    def test_get_session_info_handles_none_driver_info(self, mock_dependencies):
        """Test that _get_session_info handles DriverInfo being None gracefully.

        This scenario occurs during session transitions when iRacing SDK returns
        incomplete data. Previously caused: 'NoneType' object is not subscriptable
        """
        processor = TelemetryProcessor(**mock_dependencies)

        # Simulate DriverInfo returning None (happens during session transitions)
        mock_dependencies['ir'].__getitem__.side_effect = lambda key: {
            'DriverInfo': None,  # This is the problematic case
            'SessionNum': 0,
            'SessionInfo': {'Sessions': [{'SessionType': 'Race'}]},
            'WeekendInfo': {'SessionID': 12345}
        }.get(key)

        # Should return None gracefully, not raise TypeError
        result = processor._get_session_info()

        assert result is None, "Should return None when DriverInfo is None"

    def test_get_session_info_handles_none_drivers_list(self, mock_dependencies):
        """Test that _get_session_info handles Drivers list being None.

        This is another variant where DriverInfo exists but Drivers is None.
        """
        processor = TelemetryProcessor(**mock_dependencies)

        # DriverInfo exists but Drivers is None
        mock_dependencies['ir'].__getitem__.side_effect = lambda key: {
            'DriverInfo': {'Drivers': None},  # Drivers list is None
            'SessionNum': 0,
            'SessionInfo': {'Sessions': [{'SessionType': 'Race'}]},
            'WeekendInfo': {'SessionID': 12345}
        }.get(key)

        result = processor._get_session_info()

        assert result is None, "Should return None when Drivers list is None"

    def test_get_session_info_handles_empty_drivers_list(self, mock_dependencies):
        """Test that _get_session_info handles empty Drivers list.

        Empty list is different from None - should also return None.
        """
        processor = TelemetryProcessor(**mock_dependencies)

        # Drivers list is empty
        mock_dependencies['ir'].__getitem__.side_effect = lambda key: {
            'DriverInfo': {'Drivers': []},  # Empty list
            'SessionNum': 0,
            'SessionInfo': {'Sessions': [{'SessionType': 'Race'}]},
            'WeekendInfo': {'SessionID': 12345}
        }.get(key)

        result = processor._get_session_info()

        assert result is None, "Should return None when Drivers list is empty"

    def test_get_session_info_handles_valid_driver_info(self, mock_dependencies):
        """Test that _get_session_info works correctly with valid data.

        Ensure our defensive changes didn't break the happy path.
        """
        processor = TelemetryProcessor(**mock_dependencies)

        # Valid complete data
        mock_drivers = [
            {'CarIdx': 1, 'UserID': 100, 'UserName': 'Driver 1'},
            {'CarIdx': 2, 'UserID': 200, 'UserName': 'Driver 2'}
        ]

        mock_dependencies['ir'].__getitem__.side_effect = lambda key: {
            'DriverInfo': {'Drivers': mock_drivers},
            'SessionNum': 0,
            'SessionInfo': {
                'Sessions': [
                    {'SessionType': 'Race', 'ResultsPositions': []}
                ]
            },
            'WeekendInfo': {'SessionID': 12345}
        }.get(key)

        result = processor._get_session_info()

        assert result is not None, "Should return valid data"
        drivers, session_data, is_race = result
        assert drivers == mock_drivers
        assert session_data['session_id'] == 12345
        assert session_data['session_type'] == 'Race'
        assert is_race is True

    def test_get_session_info_handles_missing_driver_info_key(self, mock_dependencies):
        """Test that _get_session_info handles missing DriverInfo key.

        KeyError should be caught and return None.
        """
        processor = TelemetryProcessor(**mock_dependencies)

        # DriverInfo key doesn't exist at all
        def mock_getitem(key):
            if key == 'DriverInfo':
                raise KeyError('DriverInfo')
            return {
                'SessionNum': 0,
                'SessionInfo': {'Sessions': [{'SessionType': 'Race'}]},
                'WeekendInfo': {'SessionID': 12345}
            }.get(key)

        mock_dependencies['ir'].__getitem__.side_effect = mock_getitem

        result = processor._get_session_info()

        assert result is None, "Should return None when DriverInfo key is missing"
