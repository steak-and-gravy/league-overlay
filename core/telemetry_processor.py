"""
TelemetryProcessor - Handles all telemetry data processing for iRacing overlay

This class encapsulates all logic for:
- Reading and processing iRacing telemetry data
- Calculating real-time and official positions
- Managing race finish tracking
- Computing gaps between drivers
- Filtering data by division
- Session state management (using SessionID from WeekendInfo)
- Separating finished and racing drivers to prevent position contamination

Position Contamination Fix (Solution 3 - Gap Filling):
When drivers finish and disconnect, their frozen track position data could cause
incorrect sorting when mixed with active racing data.

Solution: Separate finished and racing drivers, then "fill the gaps":
1. Finished drivers: sorted by official results position (gets actual positions like 1, 2, 3, 13, 14, 19)
2. Identify which positions are already taken by finished drivers
3. Racing drivers: sorted by track position, assigned to available (untaken) positions
   - Example: If finished have {1,2,3,5,13,14}, racing get {4,6,7,8,9,10,11,12,15,16...}
4. Merge: finished drivers first (in results order), then racing drivers

This handles lapped drivers who finish (e.g., P13, P14) without creating gaps or
duplicates in the overall standings. Prevents stale track data contamination.
"""

from typing import Dict, List, Optional, Tuple, Any, Callable
import irsdk

from config.constants import TELEMETRY_CONFIG, TIMING
from config.logging_config import get_logger
from core.gap_calculator import GapCalculator
from core.division_manager import DivisionManager
from core.race_state_tracker import RaceStateTracker
from core.position_calculator import PositionCalculator
from core.driver_state import DriverState

logger = get_logger(__name__)


class TelemetryProcessor:
    """Processes iRacing telemetry data and calculates race positions, gaps, and state."""

    def __init__(
        self,
        ir: irsdk.IRSDK,
        division_manager: DivisionManager,
        race_state_tracker: RaceStateTracker,
        gap_calculator: GapCalculator,
        position_calculator: PositionCalculator
    ):
        """Initialize the telemetry processor.

        Args:
            ir: iRacing SDK connection object
            division_manager: Manages driver division assignments
            race_state_tracker: Tracks race state and finish status
            gap_calculator: Calculates gaps between drivers
            position_calculator: Calculates driver positions from telemetry
        """
        self.ir = ir
        self.division_manager = division_manager
        self.race_state_tracker = race_state_tracker
        self.gap_calculator = gap_calculator
        self.position_calculator = position_calculator

        # Session tracking
        self.current_session_id: Optional[int] = None
        self.current_session_type: Optional[str] = None

    def reset_fields(self) -> None:
        """Clear all session-specific tracking data.

        All race state tracking now managed by RaceStateTracker.
        Player identification managed by PositionCalculator.
        """
        # Reset race state tracker (manages all finish tracking and snapshots)
        self.race_state_tracker.reset()

        # Clear player identification in position calculator
        self.position_calculator.reset()

    # ═══════════════════════════════════════════════════════════════════════════
    # SESSION INFO AND TRACKING
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_session_info(self) -> Optional[Tuple[Dict[int, Dict], Dict, bool]]:
        """Get session information from telemetry.

        Returns:
            Tuple of (drivers, session_data, is_race) or None if data unavailable
            - drivers: Dict mapping CarIdx to driver info (optimized for O(1) lookups)
            - session_data contains: {
                'session_id': int,
                'session_type': str,
                'current_session': dict
            }
        """
        try:
            driver_info = self.ir['DriverInfo']
            if driver_info is None:
                return None
            drivers_list = driver_info['Drivers']
            if not drivers_list:
                return None

            # Convert to dict for O(1) lookups instead of O(n) - significant performance gain with 40+ drivers
            drivers = {driver.get('CarIdx'): driver for driver in drivers_list}

        except (KeyError, TypeError) as e:
            logger.debug(f"Error getting driver info: {e}")
            return None

        try:
            session_num = self.ir['SessionNum']
            current_session = self.ir['SessionInfo']['Sessions'][session_num]
            session_type = current_session['SessionType']
            session_id = self.ir['WeekendInfo']['SessionID']
            is_race = session_type.lower() == 'race'
        except (KeyError, TypeError, IndexError):
            return None

        session_data = {
            'session_id': session_id,
            'session_type': session_type,
            'current_session': current_session
        }

        return (drivers, session_data, is_race)

    def _detect_session_change(self, session_data: Dict) -> bool:
        """Detect if session has changed and update tracking.

        Args:
            session_data: Dict with 'session_id' and 'session_type'

        Returns:
            True if session changed, False otherwise
        """
        session_id = session_data['session_id']
        session_type = session_data['session_type']

        if self.current_session_id != session_id or self.current_session_type != session_type:
            logger.info(f"Session changed: {session_type} (SessionID: {session_id})")
            self.current_session_id = session_id
            self.current_session_type = session_type
            return True

        return False


    # ═══════════════════════════════════════════════════════════════════════════
    # SESSION RESULTS AND LAP TIMES
    # ═══════════════════════════════════════════════════════════════════════════

    def get_position_from_results(self, current_session: Dict, car_idx: int) -> int:
        """Look up a car's final position from session results.

        Args:
            current_session: Current session data
            car_idx: Car index to look up

        Returns:
            Position (1-based) or -1 if not found
        """
        try:
            if 'ResultsPositions' in current_session:
                for driver in current_session['ResultsPositions']:
                    if driver.get('CarIdx') == car_idx and 'ClassPosition' in driver:
                        return driver['ClassPosition'] + 1  # ClassPosition is 0-based
        except (KeyError, TypeError, IndexError):
            pass
        return -1

    def get_fastest_lap_time(self, current_session: Dict) -> float:
        """Find the fastest lap time in the session for gap estimation.

        Uses DEFAULT_LAP_TIME_FALLBACK when no laps recorded yet (session start).
        This prevents divide-by-zero and provides reasonable gap estimates.

        Args:
            current_session: Current session data

        Returns:
            Fastest lap time in seconds (default from TIMING.DEFAULT_LAP_TIME_FALLBACK)
        """
        fastest_time = float('inf')

        # Check if ResultsPositions exists and is not None (can be None at race start)
        if 'ResultsPositions' in current_session and current_session['ResultsPositions'] is not None:
            for driver in current_session['ResultsPositions']:
                best_lap = driver['FastestTime']
                if 0 < best_lap < fastest_time:
                    fastest_time = best_lap

        return fastest_time if fastest_time != float('inf') else TIMING.DEFAULT_LAP_TIME_FALLBACK

    def get_best_lap_from_session_info(self, current_session: Dict, car_idx: int) -> float:
        """Look up a specific car's fastest lap time from session results.

        Uses DEFAULT_LAP_TIME_FALLBACK as safe fallback when no data available.

        Args:
            current_session: Current session data
            car_idx: Car index to look up

        Returns:
            Best lap time in seconds (default from TIMING.DEFAULT_LAP_TIME_FALLBACK)
        """
        try:
            if 'ResultsPositions' in current_session:
                for driver in current_session['ResultsPositions']:
                    if driver.get('CarIdx') == car_idx and 'FastestTime' in driver:
                        return driver['FastestTime']
        except (KeyError, TypeError, IndexError):
            pass
        return TIMING.DEFAULT_LAP_TIME_FALLBACK

    # ═══════════════════════════════════════════════════════════════════════════
    # DIVISION POSITION CALCULATION
    # ═══════════════════════════════════════════════════════════════════════════

    def _calculate_division_positions(self, active_drivers: List[Dict],
                                     get_driver_color_fn: Callable) -> Tuple[Dict[int, int], List[Dict]]:
        """Calculate division positions for all drivers.

        Args:
            active_drivers: List of driver data dicts
            get_driver_color_fn: Function to get driver's division color

        Returns:
            Tuple of (division_positions, all_drivers_with_colors):
            - division_positions: Dict mapping car_idx to division position (1-based)
            - all_drivers_with_colors: List of dicts with car_idx, position, color
        """
        all_drivers_with_colors = []
        for driver in active_drivers:
            driver_color = get_driver_color_fn(driver['driver_info'])
            all_drivers_with_colors.append({
                'car_idx': driver['car_idx'],
                'position': driver.get('position', 0),
                'color': driver_color,
            })

        division_positions = {}
        from collections import defaultdict
        grouped_by_color = defaultdict(list)  # Auto-creates empty list for new keys
        for driver in all_drivers_with_colors:
            grouped_by_color[driver['color']].append(driver)

        for drivers in grouped_by_color.values():
            sorted_drivers = sorted(drivers, key=lambda x: x['position'])
            for i, driver in enumerate(sorted_drivers):
                division_positions[driver['car_idx']] = i + 1

        return division_positions, all_drivers_with_colors

    # ═══════════════════════════════════════════════════════════════════════════
    # RACE DATA BUILDING
    # ═══════════════════════════════════════════════════════════════════════════

    def _build_race_data_entry(self, driver: Dict, division_positions: Dict[int, int], gap: str, display_position: int, division_color: str, division_name: Optional[str]) -> DriverState:
        """Build a single race data entry for display.

        Args:
            driver: Driver data dict
            division_positions: Dict mapping car_idx to division position
            gap: Gap string to display
            display_position: The position to use for display/sorting
            division_color: Hex color code for driver's division
            division_name: Name of driver's division (Pro, ProAm, Am, Rookie, or None)

        Returns:
            DriverState with formatted race data for this driver
        """
        car_idx = driver['car_idx']
        driver_info = driver['driver_info']
        current_color_position = division_positions.get(car_idx, display_position)
        is_player = (car_idx == self.position_calculator.player_car_idx)
        is_disconnected = driver.get('disconnected', False)

        return DriverState(
            car_idx=car_idx,
            driver_info=driver_info,
            position=display_position,
            division_position=current_color_position,
            division_color=division_color,
            division_name=division_name,
            gap=gap if not is_disconnected else "(DC)",
            is_player=is_player,
            is_disconnected=is_disconnected
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # SNAPSHOT MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    def _update_race_snapshots(self, active_drivers: List[Dict]) -> None:
        """Update snapshots for all actively racing cars.

        Creates or updates DriverState objects for each active driver.
        Preserves gap data from previous snapshots.

        Args:
            active_drivers: List of driver data dicts from telemetry (legacy format)
        """
        for driver_data in active_drivers:
            car_idx = driver_data['car_idx']
            if self.race_state_tracker.is_driver_finished(car_idx):
                continue  # Don't update finished drivers

            # Get existing state or create new one
            driver_state = self.race_state_tracker.get_snapshot(car_idx)

            if driver_state:
                # Update existing state - preserve gap
                driver_state.current_lap = driver_data.get('current_lap', 0)
                driver_state.lap_pct = driver_data.get('lap_pct', 0.0)
                driver_state.position = driver_data.get('position', 0)
                driver_state.is_disconnected = False
                # gap is preserved (not overwritten)
            else:
                # Create new state
                driver_info = driver_data['driver_info']
                division_name = self.division_manager.get_driver_division(driver_info)
                division_color = self.division_manager.get_division_color(division_name) if division_name else "#FFFFFF"

                driver_state = DriverState(
                    car_idx=car_idx,
                    driver_info=driver_info,
                    division_name=division_name,
                    division_color=division_color,
                    current_lap=driver_data.get('current_lap', 0),
                    lap_pct=driver_data.get('lap_pct', 0.0),
                    position=driver_data.get('position', 0),
                    is_disconnected=False,
                )

                self.race_state_tracker.update_snapshot(car_idx, driver_state)

    # ═══════════════════════════════════════════════════════════════════════════
    # GAP CALCULATION
    # ═══════════════════════════════════════════════════════════════════════════

    def _calculate_gap(self, driver: Dict, current_color_position: int, current_driver_color: str,
                      active_drivers: List[Dict], all_drivers_with_colors: List[Dict],
                      is_race: bool, current_session: Dict,
                      get_driver_color_fn: Callable, show_division_gap: bool = True) -> str:
        """Calculate gap for a driver to the car ahead.

        Handles all gap calculation scenarios:
        - Leaders (show "Leader" - division leader or overall leader depending on mode)
        - Finished drivers (use stored finish gap)
        - Live racing (calculate real-time gap)
        - Practice/Qualifying (use best lap times)

        Args:
            driver: Current driver data dict
            current_color_position: Driver's position within their division
            current_driver_color: Driver's division color
            active_drivers: List of all active drivers
            all_drivers_with_colors: List of drivers with color info
            is_race: True if in race session
            current_session: Current session data
            get_driver_color_fn: Function to get driver's division color
            show_division_gap: If True, show gap to car ahead in same division. If False, show gap to any car ahead.

        Returns:
            Gap string for display (e.g., "2.5", "1L", "Leader", "")
        """
        car_idx = driver['car_idx']

        # Check if this driver is a leader
        if show_division_gap:
            # Division leader shows "Leader"
            if current_color_position == 1:
                return GapCalculator.format_gap_display(is_leader=True)
        else:
            # Overall leader shows "Leader"
            if driver.get('position', 0) == 1:
                return GapCalculator.format_gap_display(is_leader=True)

        # Finished driver (non-leader)
        if self.race_state_tracker.is_driver_finished(car_idx):
            return ""

        # Live racing - calculate real-time gap
        if is_race:
            return self._calculate_live_race_gap(driver, current_driver_color, active_drivers,
                                                current_session, get_driver_color_fn, show_division_gap)

        # Practice/Qualifying - use best lap times
        return self._calculate_practice_gap(car_idx, current_color_position, current_driver_color,
                                           all_drivers_with_colors, current_session, show_division_gap)

    def _calculate_live_race_gap(self, driver: Dict, current_driver_color: str,
                                active_drivers: List[Dict],
                                current_session: Dict, get_driver_color_fn: Callable,
                                show_division_gap: bool = True) -> str:
        """Calculate live gap during a race.

        Args:
            driver: Current driver data
            current_driver_color: Driver's division color
            active_drivers: List of all active drivers
            current_session: Current session data
            get_driver_color_fn: Function to get driver's division color
            show_division_gap: If True, compare to car ahead in same division. If False, compare to any car ahead.

        Returns:
            Gap string
        """
        car_idx = driver['car_idx']

        # Find drivers to compare against
        if show_division_gap:
            # Find all drivers in the same division
            comparison_drivers = []
            for temp_driver in active_drivers:
                temp_color = get_driver_color_fn(temp_driver['driver_info'])
                if temp_color == current_driver_color:
                    comparison_drivers.append({
                        'car_idx': temp_driver['car_idx'],
                        'position': temp_driver.get('position', 0),
                        'total_track_position': temp_driver['total_track_position'],
                        'current_lap': temp_driver['current_lap'],
                        'lap_pct': temp_driver['lap_pct']
                    })
        else:
            # Find all drivers (overall gap)
            comparison_drivers = []
            for temp_driver in active_drivers:
                comparison_drivers.append({
                    'car_idx': temp_driver['car_idx'],
                    'position': temp_driver.get('position', 0),
                    'total_track_position': temp_driver['total_track_position'],
                    'current_lap': temp_driver['current_lap'],
                    'lap_pct': temp_driver['lap_pct']
                })

        comparison_drivers.sort(key=lambda x: x['position'])

        # Find this driver's position within the comparison group
        current_pos_index = None
        for i, temp_driver in enumerate(comparison_drivers):
            if temp_driver['car_idx'] == car_idx:
                current_pos_index = i
                break

        # No car ahead in comparison group
        if current_pos_index is None or current_pos_index == 0:
            return ""

        car_ahead_idx = comparison_drivers[current_pos_index - 1]['car_idx']

        # Car ahead has finished
        if self.race_state_tracker.is_driver_finished(car_ahead_idx):
            return "-"

        # Both cars still racing - calculate live time gap
        car_idx_est_time = self.ir['CarIdxEstTime']
        current_est_time = car_idx_est_time[car_idx]
        ahead_est_time = car_idx_est_time[car_ahead_idx]

        time_gap_raw = None

        # If both cars on same lap, use iRacing's estimated time
        if current_est_time > 0 and ahead_est_time > 0 and comparison_drivers[current_pos_index - 1]['current_lap'] == driver['current_lap']:
            time_gap_raw = GapCalculator.calculate_time_gap(ahead_est_time, current_est_time)
        elif current_est_time > 0 and ahead_est_time > 0 and comparison_drivers[current_pos_index - 1]['current_lap'] > driver['current_lap']:
            # If on different laps, add est lap time to get to best estimate
            est_lap_time = self.ir['DriverInfo']['Drivers'][car_ahead_idx]['CarClassEstLapTime']
            time_gap_raw = GapCalculator.calculate_time_gap(ahead_est_time + est_lap_time, current_est_time)
        else:
            # Estimate gap based on track position difference as fallback
            position_diff = comparison_drivers[current_pos_index - 1]['total_track_position'] - driver['total_track_position']
            time_gap_raw = position_diff * self.get_fastest_lap_time(current_session)

        # Calculate exact lap distance difference for lap-based gaps
        lap_gap = GapCalculator.calculate_lap_gap(comparison_drivers[current_pos_index - 1]['total_track_position'], driver['total_track_position'])

        # Handle negative time gaps (shouldn't happen but be safe)
        if time_gap_raw is not None and time_gap_raw < 0:
            time_gap_raw = abs(time_gap_raw)

        # Format the gap
        gap = GapCalculator.format_gap_display(time_gap=time_gap_raw, lap_gap=lap_gap)

        # Store gap continuously in snapshot - used when driver finishes to freeze the display
        if gap and gap != "":
            driver_state = self.race_state_tracker.get_snapshot(car_idx)
            if driver_state:
                driver_state.gap = gap
                # No need to call update_snapshot - we're modifying the object in place

        return gap

    def _calculate_practice_gap(self, car_idx: int, current_color_position: int,
                               current_driver_color: str, all_drivers_with_colors: List[Dict],
                               current_session: Dict, show_division_gap: bool = True) -> str:
        """Calculate gap for practice/qualifying based on best lap times.

        Args:
            car_idx: Current car index
            current_color_position: Position within division
            current_driver_color: Division color
            all_drivers_with_colors: List of drivers with color info
            current_session: Current session data
            show_division_gap: If True, compare to car ahead in same division. If False, compare to any car ahead.

        Returns:
            Gap string formatted to 3 decimal places
        """
        if show_division_gap:
            # Filter to same division
            comparison_drivers = [d for d in all_drivers_with_colors if d['color'] == current_driver_color]
            comparison_drivers.sort(key=lambda x: x['position'])

            # Find current driver's index
            current_idx = None
            for i, d in enumerate(comparison_drivers):
                if d['car_idx'] == car_idx:
                    current_idx = i
                    break

            # No car ahead
            if current_idx is None or current_idx == 0:
                return ""

            car_ahead_idx = comparison_drivers[current_idx - 1]['car_idx']
        else:
            # Overall gap - find car directly ahead by overall position
            all_drivers_with_colors.sort(key=lambda x: x['position'])

            current_idx = None
            for i, d in enumerate(all_drivers_with_colors):
                if d['car_idx'] == car_idx:
                    current_idx = i
                    break

            # No car ahead
            if current_idx is None or current_idx == 0:
                return ""

            car_ahead_idx = all_drivers_with_colors[current_idx - 1]['car_idx']
        current_best = self.get_best_lap_from_session_info(current_session, car_idx)
        ahead_best = self.get_best_lap_from_session_info(current_session, car_ahead_idx)

        if current_best > 0 and ahead_best > 0:
            # Calculate gap (current - ahead, so positive = behind)
            time_gap_raw = current_best - ahead_best
            # Format to 3 decimal places for practice/quali precision
            return f"{time_gap_raw:.3f}"

        return ""

    # ═══════════════════════════════════════════════════════════════════════════
    # MAIN PROCESSING METHOD
    # ═══════════════════════════════════════════════════════════════════════════

    def process_telemetry(self, get_driver_color_fn: Callable, show_division_gap: bool = True) -> Optional[List[DriverState]]:
        """Process telemetry data - orchestrates telemetry processing using helper methods.

        Args:
            get_driver_color_fn: Function to get driver's division color
            show_division_gap: If True, show gap to car ahead in same division. If False, show gap to any car ahead.

        Returns:
            List of DriverState objects or None if processing failed
        """
        try:
            # Get session info
            session_info = self._get_session_info()
            if not session_info:
                return None

            drivers, session_data, is_race = session_info
            current_session = session_data['current_session']

            # Handle session changes
            if self._detect_session_change(session_data):
                self.reset_fields()

            # Identify player
            self.position_calculator.identify_player(drivers)

            # Share player class ID with race state tracker for multi-class filtering
            self.race_state_tracker.set_player_class_id(self.position_calculator.player_car_class_id)

            if not self.ir:
                return None

            # Process positions (different logic for race vs practice/qualifying)
            if is_race:
                self.race_state_tracker.update_finish_status(self.position_calculator.get_overall_race_leader_idx)

                active_drivers = self.position_calculator.calculate_real_time_positions(drivers)

                if active_drivers:
                    # Update snapshots for active drivers
                    self._update_race_snapshots(active_drivers)

                    # Handle disconnected/retired drivers
                    self.race_state_tracker.handle_disconnected_drivers(
                        active_drivers,
                        current_session,
                        self.get_position_from_results
                    )

                    # Separate finished and racing drivers to prevent position contamination
                    finished_drivers = [d for d in active_drivers if self.race_state_tracker.is_driver_finished(d['car_idx'])]
                    racing_drivers = [d for d in active_drivers if not self.race_state_tracker.is_driver_finished(d['car_idx'])]

                    # Override finished driver positions with locked values from snapshots
                    # This prevents positions from shifting when drivers disconnect
                    for driver in finished_drivers:
                        snapshot = self.race_state_tracker.get_snapshot(driver['car_idx'])
                        if snapshot and snapshot.position > 0:
                            # Use locked position from when they finished
                            driver['position'] = snapshot.position
                            driver['final_position'] = snapshot.position
                        else:
                            # Fallback to live telemetry if no snapshot
                            driver['final_position'] = self.get_position_from_results(current_session, driver['car_idx'])
                            driver['position'] = driver['final_position']
                    finished_drivers.sort(key=lambda x: x.get('final_position', 999))

                    # Sort racing drivers by current track position
                    # Use .get() for safety: drivers restored from snapshots after checkered (via _handle_disconnected_drivers)
                    # might not have total_track_position if snapshot was created before this field was added
                    racing_drivers.sort(key=lambda x: x.get('total_track_position', -1), reverse=True)

                    # IMPORTANT: Assign positions to racing drivers by "filling the gaps"
                    # This handles lapped drivers who may have finished (e.g., P13, P14, P19)
                    # without creating duplicate positions or gaps in the overall standings

                    # Step 1: Collect positions already taken by finished drivers
                    taken_positions = {
                        d.get('final_position')
                        for d in finished_drivers
                        if d.get('final_position', -1) > 0
                    }

                    # Step 2: Calculate total drivers and find available positions
                    total_drivers = len(finished_drivers) + len(racing_drivers)
                    available_positions = [
                        p for p in range(1, total_drivers + 1)
                        if p not in taken_positions
                    ]

                    # Step 3: Assign available positions to racing drivers in track position order
                    for i, driver in enumerate(racing_drivers):
                        if i < len(available_positions):
                            driver['position'] = available_positions[i]
                        else:
                            # Fallback: if we run out of available positions (shouldn't happen)
                            # assign next number after highest
                            driver['position'] = total_drivers + (i - len(available_positions)) + 1

                    # Merge them back: finished drivers first (in order), then racing drivers
                    active_drivers = finished_drivers + racing_drivers
            else:
                active_drivers = self.position_calculator.get_official_positions(drivers)

            if not active_drivers:
                return None

            # Calculate division positions
            division_positions, all_drivers_with_colors = self._calculate_division_positions(
                active_drivers, get_driver_color_fn)

            race_data = []

            for driver in active_drivers:
                car_idx = driver['car_idx']
                driver_info = driver['driver_info']

                if self.race_state_tracker.is_driver_finished(car_idx):
                    # Use pre-calculated final_position if available, otherwise fetch from results
                    position = driver.get('final_position', self.get_position_from_results(current_session, car_idx))
                else:
                    position = driver.get('position', 0)

                current_driver_color = get_driver_color_fn(driver_info)
                current_driver_division = self.division_manager.get_driver_division(driver_info)
                current_color_position = division_positions.get(car_idx, position)

                # Calculate gap using helper method
                gap = self._calculate_gap(
                    driver, current_color_position, current_driver_color,
                    active_drivers, all_drivers_with_colors,
                    is_race, current_session,
                    get_driver_color_fn, show_division_gap
                )

                # Build and append race data entry
                driver['position'] = position  # Ensure position is set for helper method (still needed for gap calculations)
                race_entry = self._build_race_data_entry(driver, division_positions, gap, position, current_driver_color, current_driver_division)
                race_data.append(race_entry)

            race_data.sort(key=lambda x: x.position)

            return race_data

        except Exception as e:
            logger.error(f"Processing error: {e}", exc_info=True)
            return None
