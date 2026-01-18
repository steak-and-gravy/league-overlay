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

        # Lap time cache - preserves lap times even when drivers go inactive
        # Maps car_idx -> (best_lap, last_lap)
        self.lap_time_cache: Dict[int, Tuple[float, float]] = {}

        # Pit stop tracking - maps car_idx to last pit lap number
        self.pit_tracking: Dict[int, int] = {}
        self.temp_pit_tracking: Dict[int, int] = {}

    def reset_fields(self) -> None:
        """Clear all session-specific tracking data.

        All race state tracking now managed by RaceStateTracker.
        Player identification managed by PositionCalculator.
        """
        # Reset race state tracker (manages all finish tracking and snapshots)
        self.race_state_tracker.reset()

        # Clear player identification in position calculator
        self.position_calculator.reset()

        # Clear lap time cache on session change
        self.lap_time_cache.clear()

        # Clear pit tracking on session change
        self.pit_tracking.clear()

        # Reset prepopulation retry tracking
        self.prepopulate_retry_count = 0

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

        # Build O(1) lookup dict for results access (done once per telemetry tick)
        results_lookup = {}
        fastest_lap_time = float('inf')

        if 'ResultsPositions' in current_session and current_session['ResultsPositions'] is not None:
            for driver in current_session['ResultsPositions']:
                car_idx_key = driver.get('CarIdx')
                if car_idx_key is not None:
                    results_lookup[car_idx_key] = driver

                    # Also calculate fastest lap during this single pass
                    best_lap = driver.get('FastestTime', 0)
                    if 0 < best_lap < fastest_lap_time:
                        fastest_lap_time = best_lap

        session_data = {
            'session_id': session_id,
            'session_type': session_type,
            'current_session': current_session,
            'results_lookup': results_lookup,  # O(1) lookup dictionary
            'fastest_lap_time': (
                fastest_lap_time
                if fastest_lap_time != float('inf')
                else TIMING.DEFAULT_LAP_TIME_FALLBACK
            )
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

    def _populate_lap_time_cache_from_results(self, session_data: Dict) -> None:
        """Populate lap time cache from ResultsPositions.

        This allows the overlay to show lap times immediately when joining a session.

        Args:
            session_data: Session data dict containing results_lookup
        """
        results_lookup = session_data.get('results_lookup', {})
        if not results_lookup:
            return

        for car_idx, result_data in results_lookup.items():
            # Get lap times from ResultsPositions
            best_lap = result_data.get('FastestTime', 0.0)
            last_lap = result_data.get('LastTime', 0.0)

            # Only cache if we have at least one valid lap time
            if (best_lap > 0 and best_lap < 999) or (last_lap > 0 and last_lap < 999):
                valid_best = best_lap if (best_lap > 0 and best_lap < 999) else 0.0
                valid_last = last_lap if (last_lap > 0 and last_lap < 999) else 0.0
                self.lap_time_cache[car_idx] = (valid_best, valid_last)

    def _update_pit_tracking(self) -> None:
        """Update pit tracking by monitoring CarIdxOnPitRoad transitions.

        Detects when cars exit pit road (True → False transition) and records
        the current lap number. This is used for Last Pit Lap and Out Lap columns.
        """
        try:
            car_idx_on_pit_road = self.ir['CarIdxOnPitRoad']
            car_idx_track_surface = self.ir['CarIdxTrackSurface']
            car_idx_lap = self.ir['CarIdxLap']

            if not car_idx_on_pit_road or not car_idx_lap or not car_idx_track_surface:
                return
            
            for car_idx in range(min(len(car_idx_on_pit_road), len(car_idx_lap), len(car_idx_track_surface))):
                current_on_pit = car_idx_on_pit_road[car_idx]
                current_in_stall = car_idx_track_surface[car_idx]
                current_lap = car_idx_lap[car_idx]
                if self.pit_tracking.get(car_idx, -1) >= 0:
                    # hold last pit lap in case this is a drive-through
                    self.temp_pit_tracking[car_idx] = self.pit_tracking.get(car_idx)
                # Track when car exits pit road (transition from pit to track)
                # We use a sentinel value of -1 to indicate "on pit road currently"
                # Another value of -2 to indicate they stopped in the pit stall
                if current_in_stall == 1: # 1 = InPitStall
                    # Car is in pit stall - mark as -2 (sentinel)
                    # This is important as we will only park it as an out lap if they actually stopped in the stall
                    self.pit_tracking[car_idx] = -2
                elif current_on_pit:
                    # Car is on pit road - mark as -1 (sentinel) unless they have already been in the pit stall, then leave -2
                    if self.pit_tracking.get(car_idx) != -2:
                        self.pit_tracking[car_idx] = -1
                elif self.pit_tracking.get(car_idx, 0) < 0 and not current_on_pit:
                    # Car just exited pit road (was -1, now False)
                    # Record the lap they're now on (the out lap) if they stopped in the pit stall
                    if self.pit_tracking[car_idx] == -2:
                        self.pit_tracking[car_idx] = current_lap
                    else:
                        self.pit_tracking[car_idx] = self.temp_pit_tracking.get(car_idx, 0)
                # If car is not on pit road and we have no record, don't update
                # (haven't seen them pit yet this session)

        except (KeyError, TypeError, IndexError) as e:
            logger.debug(f"Error updating pit tracking: {e}")

    # ═══════════════════════════════════════════════════════════════════════════
    # SESSION RESULTS AND LAP TIMES
    # ═══════════════════════════════════════════════════════════════════════════

    def get_position_from_results(self, session_data: Dict, car_idx: int) -> int:
        """Look up a car's final position from session results.

        Args:
            session_data: Session data dict (includes results_lookup from _get_session_info)
            car_idx: Car index to look up

        Returns:
            Position (1-based) or -1 if not found

        Performance: O(1) hash lookup instead of O(n) linear search.
        """
        results_lookup = session_data.get('results_lookup', {})
        driver = results_lookup.get(car_idx)

        if driver and 'ClassPosition' in driver:
            return driver['ClassPosition'] + 1

        return -1

    def get_fastest_lap_time(self, session_data: Dict) -> float:
        """Get cached fastest lap time (pre-calculated in _get_session_info).

        Uses DEFAULT_LAP_TIME_FALLBACK when no laps recorded yet (session start).
        This prevents divide-by-zero and provides reasonable gap estimates.

        Args:
            session_data: Session data dict (includes fastest_lap_time)

        Returns:
            Fastest lap time in seconds (default from TIMING.DEFAULT_LAP_TIME_FALLBACK)

        Performance: O(1) cached value instead of O(n) iteration.
        """
        return session_data.get('fastest_lap_time', TIMING.DEFAULT_LAP_TIME_FALLBACK)

    def get_best_lap_from_session_info(self, session_data: Dict, car_idx: int) -> float:
        """Look up a specific car's fastest lap time from session results.

        Uses DEFAULT_LAP_TIME_FALLBACK as safe fallback when no data available.

        Args:
            session_data: Session data dict (includes results_lookup)
            car_idx: Car index to look up

        Returns:
            Best lap time in seconds (default from TIMING.DEFAULT_LAP_TIME_FALLBACK)

        Performance: O(1) hash lookup instead of O(n) linear search.
        """
        results_lookup = session_data.get('results_lookup', {})
        driver = results_lookup.get(car_idx)

        if driver and 'FastestTime' in driver:
            return driver['FastestTime']

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

    def _build_race_data_entry(self, driver: Dict, division_positions: Dict[int, int], interval: str, gap_to_leader: str, display_position: int, division_color: str, division_name: Optional[str], delta: str = "--", last_lap_time: float = 0.0, best_lap_time: float = 0.0, starting_position: int = 0, irating: int = 0, lic_level: int = 0, lic_sublevel: int = 0) -> DriverState:
        """Build a single race data entry for display.

        Args:
            driver: Driver data dict
            division_positions: Dict mapping car_idx to division position
            interval: Interval string to car ahead for display
            gap_to_leader: Gap string to division/overall leader for display
            display_position: The position to use for display/sorting
            division_color: Hex color code for driver's division
            division_name: Name of driver's division (Pro, ProAm, Am, Rookie, or None)
            delta: Delta lap time comparison string
            last_lap_time: Driver's last lap time
            best_lap_time: Driver's best lap time
            starting_position: Driver's starting grid position

        Returns:
            DriverState with formatted race data for this driver
        """
        car_idx = driver['car_idx']
        driver_info = driver['driver_info']
        current_color_position = division_positions.get(car_idx, display_position)
        is_player = (car_idx == self.position_calculator.player_car_idx)
        is_disconnected = driver.get('disconnected', False)
        is_finished = self.race_state_tracker.is_driver_finished(car_idx)

        # Format last lap time for display
        last_lap_display = GapCalculator.format_lap_time(last_lap_time)

        # Format best lap time for display
        best_lap_display = GapCalculator.format_lap_time(best_lap_time)

        # Format positions gained for display (compare overall positions)
        positions_gained_display = GapCalculator.format_positions_gained(display_position, starting_position)

        # Format new columns using GapCalculator
        irating_display = GapCalculator.format_irating(irating)
        safety_rating_display = GapCalculator.format_safety_rating(lic_level, lic_sublevel)
        combined_rating_display = GapCalculator.format_combined_rating(irating, lic_level, lic_sublevel)

        # Calculate last pit lap and out lap indicator
        last_pit_lap_num = self.pit_tracking.get(car_idx, 0)
        current_lap = driver.get('current_lap', 0)
        pit_lap_display = GapCalculator.format_pit_lap(current_lap, last_pit_lap_num)

        return DriverState(
            car_idx=car_idx,
            driver_info=driver_info,
            position=display_position,
            division_position=current_color_position,
            division_color=division_color,
            division_name=division_name,
            gap_to_leader=gap_to_leader if not (is_disconnected and not is_finished) else "(DC)",
            interval=interval if not (is_disconnected and not is_finished) else "(DC)",
            delta=delta,
            last_lap=last_lap_display,
            last_lap_time=last_lap_time,
            best_lap=best_lap_display,
            best_lap_time=best_lap_time,
            starting_position=starting_position,
            positions_gained=positions_gained_display,
            irating=irating_display,
            safety_rating=safety_rating_display,
            combined_rating=combined_rating_display,
            lic_level=lic_level,
            pit_lap=pit_lap_display,
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
    # DELTA CALCULATION
    # ═══════════════════════════════════════════════════════════════════════════

    def _is_driving_mode(self) -> bool:
        """Check if in driving mode (vs spectating mode).

        Returns:
            True if player is driving (player_car_idx is valid), False if spectating
        """
        player_car_idx = self.position_calculator.player_car_idx
        return player_car_idx is not None and player_car_idx < TELEMETRY_CONFIG.MAX_CARS

    def _calculate_delta(self, driver_lap_time: float, all_drivers_with_colors: List[Dict],
                        car_idx_last_lap: list, current_driver_color: str, car_idx: int) -> str:
        """Calculate delta lap time comparison.

        When driving: Compare to player's last lap time
        When spectating: Compare to division leader's last lap time

        Args:
            driver_lap_time: Current driver's last lap time
            all_drivers_with_colors: List of all drivers with division info
            car_idx_last_lap: Array of last lap times indexed by car_idx
            current_driver_color: Driver's division color
            car_idx: Current driver's car index

        Returns:
            Formatted delta string (e.g., "+0.5", "-0.3", "--")
        """
        # Determine reference lap time based on driving vs spectating
        is_driving = self._is_driving_mode()
        player_car_idx = self.position_calculator.player_car_idx
        reference_lap_time = 0.0
        reference_car_idx = None

        if is_driving:
            # DRIVING MODE: Compare to player's last lap
            reference_lap_time = car_idx_last_lap[player_car_idx]
            reference_car_idx = player_car_idx
            # If player hasn't completed a lap yet, don't show delta for anyone
            if reference_lap_time <= 0 or reference_lap_time >= 999:
                return "--"
        else:
            # SPECTATING MODE: Compare to division leader's last lap
            # Find division leader (position 1 in this division)
            division_drivers = [d for d in all_drivers_with_colors if d['color'] == current_driver_color]
            if division_drivers:
                division_drivers.sort(key=lambda x: x['position'])
                division_leader_idx = division_drivers[0]['car_idx']
                reference_lap_time = car_idx_last_lap[division_leader_idx]
                reference_car_idx = division_leader_idx

        # If this is the reference driver, show "--" instead of "+0.0"
        if car_idx == reference_car_idx:
            return "--"

        # Format the delta using GapCalculator
        # NOTE: We flip the argument order between driving and spectating modes to maintain
        # consistent color coding (green = faster, red = slower) from the viewer's perspective:
        # - DRIVING MODE: Normal order (driver, reference) shows how each driver compares to YOU
        # - SPECTATING MODE: Flipped order (reference, driver) shows how each driver compares to their leader
        if is_driving:
            # DRIVING MODE: Normal calculation (driver vs player)
            return GapCalculator.format_delta_display(driver_lap_time, reference_lap_time)
        else:
            # SPECTATING MODE: Flip the calculation (driver vs division leader)
            return GapCalculator.format_delta_display(reference_lap_time, driver_lap_time)

    # ═══════════════════════════════════════════════════════════════════════════
    # GAP CALCULATION
    # ═══════════════════════════════════════════════════════════════════════════

    def _calculate_interval(self, driver: Dict, current_color_position: int, current_driver_color: str,
                      active_drivers: List[Dict], all_drivers_with_colors: List[Dict],
                      is_race: bool, session_data: Dict,
                      get_driver_color_fn: Callable, show_division: bool = True) -> str:
        """Calculate interval for a driver to the car ahead.

        Handles all interval calculation scenarios:
        - Leaders (show "Leader" - division leader or overall leader depending on mode)
        - Finished drivers (use stored finish interval)
        - Live racing (calculate real-time interval)
        - Practice/Qualifying (use best lap times)

        Args:
            driver: Current driver data dict
            current_color_position: Driver's position within their division
            current_driver_color: Driver's division color
            active_drivers: List of all active drivers
            all_drivers_with_colors: List of drivers with color info
            is_race: True if in race session
            session_data: Session data dict (includes current_session and lookup caches)
            get_driver_color_fn: Function to get driver's division color
            show_division: If True, show interval to car ahead in same division. If False, show interval to any car ahead.

        Returns:
            Gap string for display (e.g., "2.5", "1L", "Leader", "")
        """
        car_idx = driver['car_idx']

        # Check if this driver is a leader
        if show_division:
            # Division leader shows "Leader"
            if current_color_position == 1:
                return GapCalculator.format_gap_display(is_leader=True)
        else:
            # Overall leader shows "Leader"
            if driver.get('position', 0) == 1:
                return GapCalculator.format_gap_display(is_leader=True)

        # Finished driver (non-leader)
        if self.race_state_tracker.is_driver_finished(car_idx):
            return self._calculate_finishing_interval_from_results(
                car_idx,
                current_driver_color,
                session_data,
                get_driver_color_fn,
                show_division
            )

        # Live racing - calculate real-time interval
        if is_race:
            return self._calculate_live_race_interval(driver, current_driver_color, active_drivers,
                                                session_data, get_driver_color_fn, show_division)

        # Practice/Qualifying - use best lap times
        return self._calculate_practice_interval(car_idx, current_color_position, current_driver_color,
                                           all_drivers_with_colors, session_data, show_division)

    def _calculate_live_race_interval(self, driver: Dict, current_driver_color: str,
                                active_drivers: List[Dict],
                                session_data: Dict, get_driver_color_fn: Callable,
                                show_division: bool = True) -> str:
        """Calculate live interval during a race.

        Args:
            driver: Current driver data
            current_driver_color: Driver's division color
            active_drivers: List of all active drivers
            session_data: Session data dict (includes current_session and lookup caches)
            get_driver_color_fn: Function to get driver's division color
            show_division: If True, compare to car ahead in same division. If False, compare to any car ahead.

        Returns:
            Interval string
        """
        car_idx = driver['car_idx']
        # Determine current driver's car class and filter to same class (always),
        # and same division when show_division is True
        drivers_info = self.ir['DriverInfo']['Drivers']
        current_info = drivers_info[car_idx] if car_idx < len(drivers_info) else {}
        current_car_class_id = current_info.get('CarClassID')

        comparison_drivers = []
        for temp_driver in active_drivers:
            temp_info = temp_driver['driver_info']
            if current_car_class_id is not None and temp_info.get('CarClassID') != current_car_class_id:
                continue
            if show_division and get_driver_color_fn(temp_info) != current_driver_color:
                continue
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

        # Get lap times with bounds checking
        normalize_lap_time_pct = 0
        ahead_lap_time = 0
        drivers = self.ir['DriverInfo']['Drivers']
        if car_ahead_idx < len(drivers) and car_idx < len(drivers):
            ahead_lap_time = drivers[car_ahead_idx]['CarClassEstLapTime']
            current_lap_time = drivers[car_idx]['CarClassEstLapTime']
            if (ahead_lap_time > 0 and current_lap_time > 0):
                # Normalize Car Ahead EstTime
                normalize_lap_time_pct = ahead_lap_time/current_lap_time
                ahead_est_time = ahead_est_time/normalize_lap_time_pct

        time_gap_raw = None

        # If both cars on same lap, use iRacing's estimated time
        if current_est_time > 0 and ahead_est_time > 0 and comparison_drivers[current_pos_index - 1]['current_lap'] == driver['current_lap']:
            time_gap_raw = GapCalculator.calculate_time_gap(ahead_est_time, current_est_time)
        elif current_est_time > 0 and ahead_est_time > 0 and comparison_drivers[current_pos_index - 1]['current_lap'] > driver['current_lap']:
            # If on different laps, add est lap time to get to best estimate
            if (normalize_lap_time_pct > 0):
                time_gap_raw = GapCalculator.calculate_time_gap(ahead_est_time + ahead_lap_time/normalize_lap_time_pct, current_est_time)
            else:
                time_gap_raw = GapCalculator.calculate_time_gap(ahead_est_time + ahead_lap_time, current_est_time)
        else:
            # Estimate gap based on track position difference as fallback
            position_diff = comparison_drivers[current_pos_index - 1]['total_track_position'] - driver['total_track_position']
            time_gap_raw = position_diff * self.get_fastest_lap_time(session_data)

        # Calculate exact lap distance difference for lap-based gaps
        lap_gap = GapCalculator.calculate_lap_gap(comparison_drivers[current_pos_index - 1]['total_track_position'], driver['total_track_position'])

        # Handle negative time gaps (shouldn't happen but be safe)
        if time_gap_raw is not None and time_gap_raw < 0:
            time_gap_raw = abs(time_gap_raw)

        # Format the interval
        interval = GapCalculator.format_gap_display(time_gap=time_gap_raw, lap_gap=lap_gap)

        # Store interval continuously in snapshot - used when driver finishes to freeze the display
        if interval and interval != "":
            driver_state = self.race_state_tracker.get_snapshot(car_idx)
            if driver_state:
                driver_state.interval = interval
                # No need to call update_snapshot - we're modifying the object in place

        return interval

    def _calculate_gap_to_leader(self, driver: Dict, position: int, current_color_position: int,
                           current_driver_color: str, active_drivers: List[Dict],
                           all_drivers_with_colors: List[Dict], is_race: bool, session_data: Dict,
                           get_driver_color_fn: Callable, show_division: bool = True) -> str:
        """Calculate gap for a driver to the division/overall leader.

        Args:
            driver: Current driver data dict
            position: Driver's overall position
            current_color_position: Driver's position within their division
            current_driver_color: Driver's division color
            active_drivers: List of all active drivers
            all_drivers_with_colors: List of drivers with color info
            is_race: True if in race session
            session_data: Session data dict
            get_driver_color_fn: Function to get driver's division color
            show_division: If True, gap to division leader. If False, gap to overall leader.

        Returns:
            Gap string for display (e.g., "2.5", "1L", "Leader", "")
        """
        car_idx = driver['car_idx']

        # If this driver is the leader in the chosen scope, show Leader
        if show_division:
            if current_color_position == 1:
                return GapCalculator.format_gap_display(is_leader=True)
        else:
            if position == 1:
                return GapCalculator.format_gap_display(is_leader=True)

        # Finished driver (non-leader) uses official results to get gap to leader
        if self.race_state_tracker.is_driver_finished(car_idx):
            return self._calculate_finishing_gap_to_leader_from_results(
                car_idx,
                current_driver_color,
                session_data,
                get_driver_color_fn,
                show_division
            )

        # Live race gap to leader
        if is_race:
            return self._calculate_live_gap_to_leader(
                driver,
                current_driver_color,
                active_drivers,
                session_data,
                get_driver_color_fn,
                show_division
            )

        # Practice/Qualifying gap to leader (best laps)
        return self._calculate_practice_gap_to_leader(
            driver['car_idx'],
            current_driver_color,
            all_drivers_with_colors,
            session_data,
            show_division
        )

    def _calculate_live_gap_to_leader(self, driver: Dict, current_driver_color: str,
                                active_drivers: List[Dict],
                                session_data: Dict, get_driver_color_fn: Callable,
                                show_division: bool = True) -> str:
        """Calculate live gap to leader during a race."""
        car_idx = driver['car_idx']

        # Build comparison list: same class always; same division when show_division
        drivers_info = self.ir['DriverInfo']['Drivers']
        current_info = drivers_info[car_idx] if car_idx < len(drivers_info) else {}
        current_car_class_id = current_info.get('CarClassID')

        comparison_drivers = []
        for temp_driver in active_drivers:
            temp_info = temp_driver['driver_info']
            if current_car_class_id is not None and temp_info.get('CarClassID') != current_car_class_id:
                continue
            if show_division and get_driver_color_fn(temp_info) != current_driver_color:
                continue
            comparison_drivers.append({
                'car_idx': temp_driver['car_idx'],
                'position': temp_driver.get('position', 0),
                'total_track_position': temp_driver['total_track_position'],
                'current_lap': temp_driver['current_lap'],
                'lap_pct': temp_driver['lap_pct']
            })

        if not comparison_drivers:
            return ""

        comparison_drivers.sort(key=lambda x: x['position'])

        # Find this driver's index
        current_pos_index = None
        for i, temp_driver in enumerate(comparison_drivers):
            if temp_driver['car_idx'] == car_idx:
                current_pos_index = i
                break

        # No valid index
        if current_pos_index is None:
            return ""

        # Leader entry is the first in the sorted list
        leader_entry = comparison_drivers[0]
        leader_idx = leader_entry['car_idx']

        # If somehow the driver is leader, return Leader (should already be handled)
        if leader_idx == car_idx:
            return GapCalculator.format_gap_display(is_leader=True)

        # If leader has finished (rare while others are racing), show placeholder
        if self.race_state_tracker.is_driver_finished(leader_idx):
            return "-"

        # Get estimated times
        car_idx_est_time = self.ir['CarIdxEstTime']
        current_est_time = car_idx_est_time[car_idx]
        leader_est_time = car_idx_est_time[leader_idx]

        normalize_lap_time_pct = 0
        leader_lap_time = 0
        drivers = self.ir['DriverInfo']['Drivers']
        if leader_idx < len(drivers) and car_idx < len(drivers):
            leader_lap_time = drivers[leader_idx]['CarClassEstLapTime']
            current_lap_time = drivers[car_idx]['CarClassEstLapTime']
            if leader_lap_time > 0 and current_lap_time > 0:
                normalize_lap_time_pct = leader_lap_time / current_lap_time
                leader_est_time = leader_est_time / normalize_lap_time_pct

        time_gap_raw = None

        # Same-lap comparison
        if current_est_time > 0 and leader_est_time > 0 and leader_entry['current_lap'] == driver['current_lap']:
            time_gap_raw = GapCalculator.calculate_time_gap(leader_est_time, current_est_time)
        elif current_est_time > 0 and leader_est_time > 0 and leader_entry['current_lap'] > driver['current_lap']:
            # Leader is ahead by laps, add lap time to estimate
            if normalize_lap_time_pct > 0:
                time_gap_raw = GapCalculator.calculate_time_gap(leader_est_time + leader_lap_time / normalize_lap_time_pct, current_est_time)
            else:
                time_gap_raw = GapCalculator.calculate_time_gap(leader_est_time + leader_lap_time, current_est_time)
        else:
            # Fallback based on track position difference
            position_diff = leader_entry['total_track_position'] - driver['total_track_position']
            time_gap_raw = position_diff * self.get_fastest_lap_time(session_data)

        # Lap gap calculation
        lap_gap = GapCalculator.calculate_lap_gap(leader_entry['total_track_position'], driver['total_track_position'])

        if time_gap_raw is not None and time_gap_raw < 0:
            time_gap_raw = abs(time_gap_raw)

        return GapCalculator.format_gap_display(time_gap=time_gap_raw, lap_gap=lap_gap)

    def _calculate_practice_gap_to_leader(self, car_idx: int, current_driver_color: str,
                                     all_drivers_with_colors: List[Dict],
                                     session_data: Dict, show_division: bool = True) -> str:
        """Gap to leader during practice/qualifying based on best laps."""
        # Build comparison group: same class always; optional same division
        drivers_info = self.ir['DriverInfo']['Drivers']
        current_info = drivers_info[car_idx] if car_idx < len(drivers_info) else {}
        current_car_class_id = current_info.get('CarClassID')

        pool = all_drivers_with_colors if not show_division else [d for d in all_drivers_with_colors if d['color'] == current_driver_color]

        comparison_drivers = []
        for d in pool:
            di = drivers_info[d['car_idx']] if d['car_idx'] < len(drivers_info) else {}
            if current_car_class_id is None or di.get('CarClassID') == current_car_class_id:
                comparison_drivers.append(d)

        if not comparison_drivers:
            return ""

        comparison_drivers.sort(key=lambda x: x['position'])

        # Find current driver and leader
        current_idx = None
        for i, d in enumerate(comparison_drivers):
            if d['car_idx'] == car_idx:
                current_idx = i
                break

        if current_idx is None:
            return ""

        leader_idx = comparison_drivers[0]['car_idx']

        # Leader shows Leader
        if leader_idx == car_idx:
            return GapCalculator.format_gap_display(is_leader=True)

        current_best = self.get_best_lap_from_session_info(session_data, car_idx)
        leader_best = self.get_best_lap_from_session_info(session_data, leader_idx)

        if current_best > 0 and leader_best > 0:
            time_gap_raw = current_best - leader_best
            return f"{time_gap_raw:.3f}"

        return ""

    def _calculate_finishing_gap_to_leader_from_results(self, car_idx: int, current_driver_color: str,
                                                   session_data: Dict, get_driver_color_fn: Callable,
                                                   show_division: bool = True) -> str:
        """Calculate finishing gap to the leader using official ResultsPositions data."""
        results_lookup = session_data.get('results_lookup', {})
        current_session = session_data.get('current_session', {})

        results_positions = current_session.get('ResultsPositions')
        if not results_positions:
            return ""

        sorted_results = sorted(results_positions, key=lambda x: x.get('Position', 999))

        current_result = results_lookup.get(car_idx)
        if not current_result:
            return ""

        # Stale data detection mirrors interval logic
        if self.race_state_tracker.is_driver_finished(car_idx):
            finish_lap = self.race_state_tracker.get_finish_lap(car_idx)
            results_laps = current_result.get('LapsComplete', 0)
            if finish_lap is not None and results_laps < finish_lap:
                logger.debug(f"STALE_CHECK - Car {car_idx}: Waiting for ResultsPositions sync (results_laps={results_laps} < finish_lap={finish_lap})")
                return ""
        else:
            try:
                results_laps = current_result.get('LapsComplete', 0)
                car_idx_lap = self.ir['CarIdxLap']
                live_laps = car_idx_lap[car_idx] if car_idx < len(car_idx_lap) else 0
                if results_laps < live_laps:
                    logger.debug(f"STALE_CHECK - Car {car_idx}: Racing data stale (results_laps={results_laps} < live_laps={live_laps})")
                    return ""
            except (KeyError, TypeError, IndexError) as e:
                logger.warning(f"STALE_CHECK - Car {car_idx}: Exception accessing telemetry ({type(e).__name__}), using ResultsPositions anyway")
                pass

        current_laps = current_result.get('LapsComplete', 0)
        current_time = current_result.get('Time', 0.0)

        if show_division:
            # Division leader = first car in same division/class
            current_driver_info = self.ir['DriverInfo']['Drivers'][car_idx] if car_idx < len(self.ir['DriverInfo']['Drivers']) else {}
            current_car_class_id = current_driver_info.get('CarClassID')

            division_results = []
            for result in sorted_results:
                result_car_idx = result.get('CarIdx')
                if result_car_idx is None:
                    continue

                driver_info = self.ir['DriverInfo']['Drivers'][result_car_idx] if result_car_idx < len(self.ir['DriverInfo']['Drivers']) else {}
                if not driver_info:
                    continue

                driver_division_color = get_driver_color_fn(driver_info)
                driver_car_class_id = driver_info.get('CarClassID')

                division_match = driver_division_color == current_driver_color
                class_match = (current_car_class_id is None and driver_car_class_id is None) or (driver_car_class_id == current_car_class_id)

                if division_match and class_match:
                    division_results.append(result)

            if not division_results:
                return ""

            division_leader = division_results[0]

            if division_leader.get('CarIdx') == car_idx:
                return GapCalculator.format_gap_display(is_leader=True)

            ahead_laps = division_leader.get('LapsComplete', 0)
            ahead_time = division_leader.get('Time', 0.0)
        else:
            # Overall mode: still compare within the same car class (class leader)
            current_driver_info = self.ir['DriverInfo']['Drivers'][car_idx] if car_idx < len(self.ir['DriverInfo']['Drivers']) else {}
            current_car_class_id = current_driver_info.get('CarClassID')

            class_results = []
            for result in sorted_results:
                result_car_idx = result.get('CarIdx')
                if result_car_idx is None:
                    continue
                driver_info = self.ir['DriverInfo']['Drivers'][result_car_idx] if result_car_idx < len(self.ir['DriverInfo']['Drivers']) else {}
                if not driver_info:
                    continue
                driver_car_class_id = driver_info.get('CarClassID')
                class_match = (current_car_class_id is None and driver_car_class_id is None) or (driver_car_class_id == current_car_class_id)
                if class_match:
                    class_results.append(result)

            if not class_results:
                return ""

            class_leader = class_results[0]
            if class_leader.get('CarIdx') == car_idx:
                return GapCalculator.format_gap_display(is_leader=True)

            ahead_laps = class_leader.get('LapsComplete', 0)
            ahead_time = class_leader.get('Time', 0.0)

        lap_gap = ahead_laps - current_laps

        if lap_gap > 0:
            return GapCalculator.format_gap_display(lap_gap=lap_gap)

        time_gap = current_time - ahead_time
        if time_gap < 0:
            time_gap = 0.0

        return GapCalculator.format_gap_display(time_gap=time_gap, lap_gap=0)

    def _calculate_practice_interval(self, car_idx: int, current_color_position: int,
                               current_driver_color: str, all_drivers_with_colors: List[Dict],
                               session_data: Dict, show_division: bool = True) -> str:
        """Calculate interval for practice/qualifying based on best lap times.

        Args:
            car_idx: Current car index
            current_color_position: Position within division
            current_driver_color: Division color
            all_drivers_with_colors: List of drivers with color info
            session_data: Session data dict (includes current_session and lookup caches)
            show_division: If True, compare to car ahead in same division. If False, compare to any car ahead.

        Returns:
            Interval string formatted to 3 decimal places
        """
        # Always compare within same car class; optionally scope to division
        drivers_info = self.ir['DriverInfo']['Drivers']
        current_info = drivers_info[car_idx] if car_idx < len(drivers_info) else {}
        current_car_class_id = current_info.get('CarClassID')

        if show_division:
            # Filter to same division and class
            comparison_drivers = []
            for d in all_drivers_with_colors:
                if d['color'] != current_driver_color:
                    continue
                di = drivers_info[d['car_idx']] if d['car_idx'] < len(drivers_info) else {}
                if current_car_class_id is not None and di.get('CarClassID') != current_car_class_id:
                    continue
                comparison_drivers.append(d)
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
            # Overall mode but still only same class
            filtered = []
            for d in all_drivers_with_colors:
                di = drivers_info[d['car_idx']] if d['car_idx'] < len(drivers_info) else {}
                if current_car_class_id is None or di.get('CarClassID') == current_car_class_id:
                    filtered.append(d)
            filtered.sort(key=lambda x: x['position'])

            current_idx = None
            for i, d in enumerate(filtered):
                if d['car_idx'] == car_idx:
                    current_idx = i
                    break

            # No car ahead
            if current_idx is None or current_idx == 0:
                return ""

            car_ahead_idx = filtered[current_idx - 1]['car_idx']
        current_best = self.get_best_lap_from_session_info(session_data, car_idx)
        ahead_best = self.get_best_lap_from_session_info(session_data, car_ahead_idx)

        if current_best > 0 and ahead_best > 0:
            # Calculate gap (current - ahead, so positive = behind)
            time_gap_raw = current_best - ahead_best
            # Format to 3 decimal places for practice/quali precision
            return f"{time_gap_raw:.3f}"

        return ""

    def _calculate_finishing_interval_from_results(self, car_idx: int, current_driver_color: str,
                                              session_data: Dict, get_driver_color_fn: Callable,
                                              show_division: bool = True) -> str:
        """Calculate finishing interval using official ResultsPositions data.

        This method is called for drivers who have crossed the finish line after checkered flag.
        It uses the official iRacing ResultsPositions data which includes:
        - Time: seconds behind the race winner
        - LapsComplete: total laps completed (used to determine lap deficits)

        IMPORTANT: Detects stale data by comparing ResultsPositions lap count to live telemetry.
        If ResultsPositions hasn't updated yet (common ~1 second delay after finish), returns
        empty string to avoid showing incorrect gaps.

        Args:
            car_idx: Current car index
            current_driver_color: Driver's division color
            session_data: Session data dict (includes results_lookup)
            get_driver_color_fn: Function to get driver's division color
            show_division: If True, compare to car ahead in same division. If False, compare to any car ahead.

        Returns:
            Gap string for display (e.g., "2.5", "1L", "Leader", "")
            Empty string if data is stale
        """
        results_lookup = session_data.get('results_lookup', {})
        current_session = session_data.get('current_session', {})

        # Get ResultsPositions list
        results_positions = current_session.get('ResultsPositions')
        if not results_positions:
            return ""

        # Sort by overall Position first (this maintains the official race order)
        # We'll filter by class/division later when needed
        sorted_results = sorted(results_positions, key=lambda x: x.get('Position', 999))

        # Find current driver's result
        current_result = results_lookup.get(car_idx)
        if not current_result:
            return ""

        # STALE DATA DETECTION: Check if ResultsPositions has caught up to the finish lap
        # When a driver finishes, their CarIdxLap increments immediately, but ResultsPositions
        # can take ~1 second to update. We only block display until ResultsPositions shows
        # the correct finish lap count.
        if self.race_state_tracker.is_driver_finished(car_idx):
            finish_lap = self.race_state_tracker.get_finish_lap(car_idx)
            results_laps = current_result.get('LapsComplete', 0)

            # Check if ResultsPositions has caught up to the finish lap
            if finish_lap is not None and results_laps < finish_lap:
                # Only log when actually blocking (this is the important case to track)
                logger.debug(f"STALE_CHECK - Car {car_idx}: Waiting for ResultsPositions sync (results_laps={results_laps} < finish_lap={finish_lap})")
                # ResultsPositions hasn't updated to finish lap yet - return blank
                return ""
        else:
            # For drivers not marked as finished, check if live telemetry is ahead of ResultsPositions
            try:
                results_laps = current_result.get('LapsComplete', 0)
                car_idx_lap = self.ir['CarIdxLap']
                live_laps = car_idx_lap[car_idx] if car_idx < len(car_idx_lap) else 0

                # If ResultsPositions lap count is behind live telemetry, data is stale
                if results_laps < live_laps:
                    # Only log when actually blocking
                    logger.debug(f"STALE_CHECK - Car {car_idx}: Racing data stale (results_laps={results_laps} < live_laps={live_laps})")
                    # Return empty string - will show blank briefly until data updates
                    return ""
            except (KeyError, TypeError, IndexError) as e:
                # Only log exceptions (these are unexpected)
                logger.warning(f"STALE_CHECK - Car {car_idx}: Exception accessing telemetry ({type(e).__name__}), using ResultsPositions anyway")
                pass

        current_laps = current_result.get('LapsComplete', 0)
        current_time = current_result.get('Time', 0.0)

        if show_division:
            # DIVISION GAP MODE: Find car ahead in same division/class

            # Use the division color that was already calculated and passed in
            # (don't recalculate - for disconnected/restored drivers the driver_info may differ)
            current_division_color = current_driver_color

            # Get current driver's car class for multi-class filtering
            current_driver_info = self.ir['DriverInfo']['Drivers'][car_idx] if car_idx < len(self.ir['DriverInfo']['Drivers']) else {}
            current_car_class_id = current_driver_info.get('CarClassID')

            # Build list of drivers in same division AND same car class, sorted by position
            division_results = []
            for result in sorted_results:
                result_car_idx = result.get('CarIdx')
                if result_car_idx is None:
                    continue

                # Get division color and car class for this driver
                driver_info = self.ir['DriverInfo']['Drivers'][result_car_idx] if result_car_idx < len(self.ir['DriverInfo']['Drivers']) else {}

                # Skip if driver_info is empty (driver not in current session - disconnected/invalid)
                if not driver_info:
                    continue

                driver_division_color = get_driver_color_fn(driver_info)
                driver_car_class_id = driver_info.get('CarClassID')

                # Filter by BOTH division color AND car class (for multi-class support)
                # This ensures we compare within the same class even if divisions aren't configured
                division_match = driver_division_color == current_division_color
                class_match = (current_car_class_id is None and driver_car_class_id is None) or (driver_car_class_id == current_car_class_id)

                if division_match and class_match:
                    division_results.append(result)

            # Find current driver's position within division
            current_div_index = None
            for i, result in enumerate(division_results):
                if result.get('CarIdx') == car_idx:
                    current_div_index = i
                    break

            # If first in division (division leader), show "Leader"
            if current_div_index == 0:
                logger.debug(f"FINISH_GAP - Car {car_idx} is DIVISION LEADER")
                return GapCalculator.format_gap_display(is_leader=True)

            # Get car ahead in division
            if current_div_index is None or current_div_index == 0:
                return ""

            ahead_result = division_results[current_div_index - 1]

        else:
            # OVERALL MODE: Compare within same class for car-ahead

            # Get current driver's car class
            current_driver_info = self.ir['DriverInfo']['Drivers'][car_idx] if car_idx < len(self.ir['DriverInfo']['Drivers']) else {}
            current_car_class_id = current_driver_info.get('CarClassID')

            # Build list of cars in same class
            class_results = []
            for result in sorted_results:
                result_car_idx = result.get('CarIdx')
                if result_car_idx is None:
                    continue
                driver_info = self.ir['DriverInfo']['Drivers'][result_car_idx] if result_car_idx < len(self.ir['DriverInfo']['Drivers']) else {}
                if not driver_info:
                    continue
                driver_car_class_id = driver_info.get('CarClassID')
                class_match = (current_car_class_id is None and driver_car_class_id is None) or (driver_car_class_id == current_car_class_id)
                if class_match:
                    class_results.append(result)

            # Find current driver's index within class
            current_index = None
            for i, result in enumerate(class_results):
                if result.get('CarIdx') == car_idx:
                    current_index = i
                    break

            # Class leader shows Leader
            if current_index == 0:
                logger.debug(f"FINISH_GAP_OVERALL - Car {car_idx} is CLASS LEADER")
                return GapCalculator.format_gap_display(is_leader=True)

            # No car ahead in class
            if current_index is None or current_index == 0:
                return ""

            ahead_result = class_results[current_index - 1]

        # Calculate gap to car ahead
        ahead_laps = ahead_result.get('LapsComplete', 0)
        ahead_time = ahead_result.get('Time', 0.0)

        # Check if laps down (lap deficit takes priority over time gap)
        lap_gap = ahead_laps - current_laps

        if lap_gap > 0:
            # Driver is laps down - show lap gap
            return GapCalculator.format_gap_display(lap_gap=lap_gap)
        else:
            # Same lap - show time gap
            time_gap = current_time - ahead_time

            # Handle edge case of negative time gap (shouldn't happen but be safe)
            if time_gap < 0:
                time_gap = 0.0

            return GapCalculator.format_gap_display(time_gap=time_gap, lap_gap=0)

    # ═══════════════════════════════════════════════════════════════════════════
    # MAIN PROCESSING METHOD
    # ═══════════════════════════════════════════════════════════════════════════

    def process_telemetry(self, get_driver_color_fn: Callable, show_division: bool = True) -> Optional[List[DriverState]]:
        """Process telemetry data - orchestrates telemetry processing using helper methods.

        Args:
            get_driver_color_fn: Function to get driver's division color
            show_division: If True, gap/interval scoped to division. If False, overall.

        Returns:
            List of DriverState objects or None if processing failed
        """
        try:
            # Get session info
            session_info = self._get_session_info()
            if not session_info:
                return None

            drivers, session_data, is_race = session_info

            # Handle session changes
            if self._detect_session_change(session_data):
                self.reset_fields()
                # Load starting positions if entering a race session
                if is_race:
                    self.race_state_tracker.load_starting_positions_from_qualify()

            # Update lap time cache
            self._populate_lap_time_cache_from_results(session_data)

            # Update pit tracking only during race sessions (practice/qualifying don't need pit tracking)
            if is_race:
                self._update_pit_tracking()

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
                        session_data,
                        self.get_position_from_results
                    )

                    # Update all finished drivers with official positions from ResultsPositions
                    # This ensures we always show correct final results, even for disconnected drivers
                    if self.race_state_tracker.is_checkered():
                        for car_idx in self.race_state_tracker.finished_drivers:
                            snapshot = self.race_state_tracker.get_snapshot(car_idx)
                            if snapshot:
                                official_position = self.get_position_from_results(session_data, car_idx)
                                if official_position > 0:
                                    snapshot.position = official_position

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
                            driver['final_position'] = self.get_position_from_results(session_data, driver['car_idx'])
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

            # Read lap time telemetry data
            try:
                car_idx_last_lap = self.ir['CarIdxLastLapTime']
                car_idx_best_lap = self.ir['CarIdxBestLapTime']
            except (KeyError, TypeError):
                # Fallback if telemetry not available (shouldn't happen but be safe)
                car_idx_last_lap = [0.0] * TELEMETRY_CONFIG.MAX_CARS
                car_idx_best_lap = [0.0] * TELEMETRY_CONFIG.MAX_CARS

            race_data = []

            for driver in active_drivers:
                car_idx = driver['car_idx']
                driver_info = driver['driver_info']

                if self.race_state_tracker.is_driver_finished(car_idx):
                    # Use pre-calculated final_position if available, otherwise fetch from results
                    position = driver.get('final_position', self.get_position_from_results(session_data, car_idx))
                else:
                    position = driver.get('position', 0)

                current_driver_color = get_driver_color_fn(driver_info)
                current_driver_division = self.division_manager.get_driver_division(driver_info)
                current_color_position = division_positions.get(car_idx, position)

                # Calculate interval using helper method
                interval = self._calculate_interval(
                    driver, current_color_position, current_driver_color,
                    active_drivers, all_drivers_with_colors,
                    is_race, session_data,
                    get_driver_color_fn, show_division
                )

                # Calculate gap to leader
                gap_to_leader = self._calculate_gap_to_leader(
                    driver, position, current_color_position, current_driver_color,
                    active_drivers, all_drivers_with_colors,
                    is_race, session_data,
                    get_driver_color_fn, show_division
                )

                # Get lap time data from cache (preserves times when driver goes inactive)
                # For restored drivers from ResultsPositions, use their lap times from the driver dict
                if 'best_lap_time' in driver and 'last_lap_time' in driver:
                    best_lap_time = driver['best_lap_time']
                    last_lap_time = driver['last_lap_time']
                else:
                    cached_times = self.lap_time_cache.get(car_idx, (0.0, 0.0))
                    best_lap_time = cached_times[0]
                    last_lap_time = cached_times[1]

                # Calculate delta lap time comparison
                delta = self._calculate_delta(
                    last_lap_time,
                    all_drivers_with_colors,
                    car_idx_last_lap,
                    current_driver_color,
                    car_idx
                )

                # Get starting position for positions gained calculation (only during race sessions)
                starting_position = self.race_state_tracker.get_starting_position(car_idx) if is_race else 0

                # Extract new column data from driver info (with fallback values)
                driver_info = drivers.get(car_idx, {})
                try:
                    irating = driver_info['IRating']
                except (KeyError, TypeError):
                    irating = 0

                try:
                    lic_level = driver_info['LicLevel']
                except (KeyError, TypeError):
                    lic_level = 0

                try:
                    lic_sublevel = driver_info['LicSubLevel']
                except (KeyError, TypeError):
                    lic_sublevel = 0

                # Build and append race data entry
                driver['position'] = position  # Ensure position is set for helper method (still needed for gap calculations)
                race_entry = self._build_race_data_entry(
                    driver, division_positions, interval, gap_to_leader, position,
                    current_driver_color, current_driver_division,
                    delta, last_lap_time, best_lap_time, starting_position,
                    irating, lic_level, lic_sublevel
                )
                race_data.append(race_entry)

            race_data.sort(key=lambda x: x.position)

            return race_data

        except Exception as e:
            logger.error(f"Processing error: {e}", exc_info=True)
            return None
