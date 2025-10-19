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

from config.constants import TELEMETRY_CONFIG
from config.logging_config import get_logger
from core.gap_calculator import GapCalculator
from core.division_manager import DivisionManager
from core.race_state_tracker import RaceStateTracker

logger = get_logger(__name__)


class TelemetryProcessor:
    """Processes iRacing telemetry data and calculates race positions, gaps, and state."""

    def __init__(
        self,
        ir: irsdk.IRSDK,
        division_manager: DivisionManager,
        race_state_tracker: RaceStateTracker,
        gap_calculator: GapCalculator
    ):
        """Initialize the telemetry processor.

        Args:
            ir: iRacing SDK connection object
            division_manager: Manages driver division assignments
            race_state_tracker: Tracks race state and finish status
            gap_calculator: Calculates gaps between drivers
        """
        self.ir = ir
        self.division_manager = division_manager
        self.race_state_tracker = race_state_tracker
        self.gap_calculator = gap_calculator

        # Session tracking
        self.current_session_id: Optional[int] = None
        self.current_session_type: Optional[str] = None
        self.player_car_idx: Optional[int] = None
        self.player_car_class_id: Optional[int] = None

    def reset_fields(self) -> None:
        """Clear all session-specific tracking data.

        All race state tracking now managed by RaceStateTracker.
        """
        # Reset race state tracker (manages all finish tracking and snapshots)
        self.race_state_tracker.reset()

        # Clear player identification
        self.player_car_idx = None
        self.player_car_class_id = None

    # ═══════════════════════════════════════════════════════════════════════════
    # SESSION INFO AND TRACKING
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_session_info(self) -> Optional[Tuple[List, Dict, bool]]:
        """Get session information from telemetry.

        Returns:
            Tuple of (drivers, session_data, is_race) or None if data unavailable
            session_data contains: {
                'session_id': int,
                'session_type': str,
                'current_session': dict
            }
        """
        try:
            driver_info = self.ir['DriverInfo']
            if driver_info is None:
                return None
            drivers = driver_info['Drivers']
            if not drivers:
                return None
        except (KeyError, TypeError) as e:
            logger.debug(f"Error getting driver info: {e}")
            print(f"Error getting driver info: {e}")
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

    def _identify_player(self, drivers: List[Dict]) -> None:
        """Identify player's car index and class.

        Updates self.player_car_idx and self.player_car_class_id.

        Args:
            drivers: List of driver dictionaries from telemetry
        """
        if self.player_car_idx is None:
            try:
                self.player_car_idx = self.ir['PlayerCarIdx']
                logger.info(f"Player car index identified: {self.player_car_idx}")
            except (KeyError, TypeError):
                self.player_car_idx = None

        if self.player_car_idx is not None and self.player_car_class_id is None:
            try:
                for driver in drivers:
                    if driver.get('CarIdx') == self.player_car_idx:
                        class_id = driver.get('CarClassID')
                        if class_id is not None:  # Only set if we actually got a valid class ID
                            self.player_car_class_id = class_id
                            logger.info(f"Player class ID identified: {self.player_car_class_id} for car {self.player_car_idx}")
                        else:
                            logger.warning(f"Found player car {self.player_car_idx} but CarClassID is None")
                        break
            except (KeyError, TypeError) as e:
                logger.warning(f"Error identifying player class: {e}")

    # ═══════════════════════════════════════════════════════════════════════════
    # POSITION CALCULATION
    # ═══════════════════════════════════════════════════════════════════════════

    def calculate_real_time_positions(self, drivers: List[Dict], live_data: irsdk.IRSDK) -> List[Dict]:
        """Calculate real-time positions based on actual track position.

        Args:
            drivers: List of driver info from telemetry
            live_data: Live telemetry data

        Returns:
            List of driver dicts with position and track data
        """
        car_idx_lap = live_data['CarIdxLap']
        car_idx_lap_dist_pct = live_data['CarIdxLapDistPct']
        car_idx_class_position = live_data['CarIdxClassPosition']

        if not car_idx_lap or not car_idx_lap_dist_pct or not car_idx_class_position:
            return []

        active_drivers = []

        for car_idx in range(len(car_idx_class_position)):
            # Position 0 means car is not active/participating
            if car_idx_class_position[car_idx] == 0:
                continue

            driver_info = None
            for driver in drivers:
                if driver.get('CarIdx') == car_idx:
                    driver_info = driver
                    break

            if not driver_info:
                continue

            # Multi-class support: only show cars in the player's class
            if self.player_car_class_id is not None:
                if driver_info.get('CarClassID') != self.player_car_class_id:
                    continue

            current_lap = car_idx_lap[car_idx]
            lap_pct = car_idx_lap_dist_pct[car_idx]

            if current_lap < 0:
                continue

            # Sanity check - percentage should be 0.0 to 1.0
            if lap_pct < 0 or lap_pct > 1:
                lap_pct = 0

            # Total track position: lap number + progress through current lap
            total_track_position = current_lap + lap_pct

            active_drivers.append({
                'car_idx': car_idx,
                'driver_info': driver_info,
                'total_track_position': total_track_position,
                'current_lap': current_lap,
                'lap_pct': lap_pct,
                'official_position': car_idx_class_position[car_idx]
            })

        # Sort by track position (highest first = furthest ahead)
        active_drivers.sort(key=lambda x: x['total_track_position'], reverse=True)

        # Assign real-time positions based on sorted order
        for i, driver in enumerate(active_drivers):
            driver['real_time_position'] = i + 1

        return active_drivers

    def get_official_positions(self, drivers: List[Dict], live_data: irsdk.IRSDK) -> List[Dict]:
        """Get positions from iRacing's official timing system (updates at start/finish line).

        Why this exists: Practice/qualifying don't need the complexity of real-time
        tracking. Official positions are sufficient and more stable.

        Args:
            drivers: List of driver info from telemetry
            live_data: Live telemetry data

        Returns:
            List of driver dicts with official positions
        """
        car_idx_class_position = live_data['CarIdxClassPosition']

        if not car_idx_class_position:
            return []

        active_drivers = []

        for car_idx in range(len(car_idx_class_position)):
            # Position 0 means car is not active/participating
            if car_idx_class_position[car_idx] == 0:
                continue

            driver_info = None
            for driver in drivers:
                if driver.get('CarIdx') == car_idx:
                    driver_info = driver
                    break

            if not driver_info:
                continue

            if self.player_car_class_id is not None:
                if driver_info.get('CarClassID') != self.player_car_class_id:
                    continue

            active_drivers.append({
                'car_idx': car_idx,
                'driver_info': driver_info,
                'official_position': car_idx_class_position[car_idx]
            })

        active_drivers.sort(key=lambda x: x['official_position'])

        return active_drivers

    # ═══════════════════════════════════════════════════════════════════════════
    # FINISH STATUS TRACKING
    # ═══════════════════════════════════════════════════════════════════════════

    def get_overall_race_leader_idx(self, live_data: irsdk.IRSDK) -> Optional[int]:
        """Find the car index of the overall race leader (furthest ahead on track).

        This is the true P1 overall, regardless of class. Used for multi-class racing
        where the overall leader triggers when finish tracking can begin.

        Args:
            live_data: Live telemetry data containing lap and distance info

        Returns:
            car_idx of overall leader, or None if no leader found
        """
        car_idx_lap = live_data['CarIdxLap']
        car_idx_lap_dist_pct = live_data['CarIdxLapDistPct']

        if not car_idx_lap or not car_idx_lap_dist_pct:
            return None

        overall_leader_idx = None
        max_track_position = -1

        for car_idx in range(len(car_idx_lap)):
            if car_idx_lap[car_idx] < 0:  # Not active
                continue

            total_track_position = car_idx_lap[car_idx] + car_idx_lap_dist_pct[car_idx]

            if total_track_position > max_track_position:
                max_track_position = total_track_position
                overall_leader_idx = car_idx

        return overall_leader_idx

    def update_finish_status(self, live_data: irsdk.IRSDK, current_session: Dict, get_driver_color_fn: Callable) -> None:
        """Track which drivers have finished the race after the checkered flag.

        IMPORTANT: iRacing shows the checkered flag BEFORE the leader crosses the
        line. We need to track when each driver completes their current lap after
        the checkered and after the leader finishes to know their final position.

        This method:
        1. Identifies what lap the leader is on when checkered waves
        2. Waits for the leader to complete that lap (true finish)
        3. Tracks each subsequent driver as they finish their current lap
        4. Stores their official position at the moment they finish

        Now delegates to RaceStateTracker for all state management.

        Args:
            live_data: Live telemetry data
            current_session: Current session data
            get_driver_color_fn: Function to get driver's division color
        """
        # SessionState < 5 means race hasn't reached checkered flag yet
        if self.ir['SessionState'] < 5:
            return

        car_idx_lap = live_data['CarIdxLap']
        car_idx_class_position = live_data['CarIdxClassPosition']

        # PHASE 1: Mark checkered flag as shown (enables finish tracking)
        if self.race_state_tracker.is_racing():
            # First time after checkered - flip to finish tracking mode
            self.race_state_tracker.set_checkered_flag()

        # PHASE 2: Wait for the OVERALL race leader (P1 overall, any class) to finish
        # This allows multi-class racing where slower class drivers can finish before their class leader
        if not self.race_state_tracker.is_racing() and not self.race_state_tracker.has_leader_finished():
            # Find the overall race leader (furthest ahead on track, regardless of class)
            overall_leader_idx = self.get_overall_race_leader_idx(live_data)

            # Check if the overall leader has finished using their snapshot
            if overall_leader_idx is not None:
                snapshot = self.race_state_tracker.get_snapshot(overall_leader_idx)

                # If no snapshot exists (overall leader might be in different class), create minimal snapshot
                if not snapshot:
                    current_lap = car_idx_lap[overall_leader_idx] if overall_leader_idx < len(car_idx_lap) else 0
                    self.race_state_tracker.update_snapshot(overall_leader_idx, {
                        'car_idx': overall_leader_idx,
                        'current_lap': current_lap,
                    })
                    snapshot = self.race_state_tracker.get_snapshot(overall_leader_idx)

                if snapshot:
                    prev_lap = snapshot.get('current_lap', 0)
                    current_lap = car_idx_lap[overall_leader_idx] if overall_leader_idx < len(car_idx_lap) else 0

                    # Did the overall leader just cross the finish line?
                    if current_lap > prev_lap:
                        # Overall leader finished - now we can start tracking our class drivers
                        self.race_state_tracker.set_leader_finished_flag()
                    else:
                        # Update their lap for next cycle
                        snapshot['current_lap'] = current_lap
                        self.race_state_tracker.update_snapshot(overall_leader_idx, snapshot)

        # PHASE 3: Once leader is done, track all other drivers as they complete their laps
        if self.race_state_tracker.has_leader_finished():
            for car_idx in range(len(car_idx_lap)):
                if self.race_state_tracker.is_driver_finished(car_idx):
                    continue

                if self.player_car_class_id is not None:
                    try:
                        drivers = self.ir['DriverInfo']['Drivers']
                        driver_class_id = None
                        for d in drivers:
                            if d.get('CarIdx') == car_idx:
                                driver_class_id = d.get('CarClassID')
                                break

                        if driver_class_id != self.player_car_class_id:
                            continue
                    except (KeyError, TypeError):
                        continue

                snapshot = self.race_state_tracker.get_snapshot(car_idx)
                if snapshot is None:
                    continue

                prev_lap = snapshot.get('current_lap', 0)
                current_lap = car_idx_lap[car_idx]

                # When lap counter increments, driver has crossed finish line and completed race
                if current_lap > prev_lap:
                    # Capture the official position at the moment they finish
                    official_position = car_idx_class_position[car_idx] if car_idx < len(car_idx_class_position) else 0
                    finish_time = self.ir['SessionTime']
                    self.race_state_tracker.mark_driver_finished(car_idx, finish_time, official_position, current_lap)

                    # Recalculate division positions and gaps for ALL finished drivers
                    self.race_state_tracker.recalculate_all_finish_gaps(current_session, get_driver_color_fn)

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

        Why 90 seconds: Fallback for when no laps recorded yet (session start).
        90s is a reasonable default that won't cause divide-by-zero or absurd gaps.

        Args:
            current_session: Current session data

        Returns:
            Fastest lap time in seconds (default 90.0)
        """
        fastest_time = float('inf')

        # Check if ResultsPositions exists and is not None (can be None at race start)
        if 'ResultsPositions' in current_session and current_session['ResultsPositions'] is not None:
            for driver in current_session['ResultsPositions']:
                best_lap = driver['FastestTime']
                if 0 < best_lap < fastest_time:
                    fastest_time = best_lap

        return fastest_time if fastest_time != float('inf') else 90

    def get_best_lap_from_session_info(self, current_session: Dict, car_idx: int) -> float:
        """Look up a specific car's fastest lap time from session results.

        Why 90 seconds: Same reason as get_fastest_lap_time() - safe fallback.

        Args:
            current_session: Current session data
            car_idx: Car index to look up

        Returns:
            Best lap time in seconds (default 90.0)
        """
        try:
            if 'ResultsPositions' in current_session:
                for driver in current_session['ResultsPositions']:
                    if driver.get('CarIdx') == car_idx and 'FastestTime' in driver:
                        return driver['FastestTime']
        except (KeyError, TypeError, IndexError):
            pass
        return 90

    # ═══════════════════════════════════════════════════════════════════════════
    # DIVISION POSITION CALCULATION
    # ═══════════════════════════════════════════════════════════════════════════

    def _calculate_division_positions(self, active_drivers: List[Dict], position_key: str,
                                     get_driver_color_fn: Callable) -> Tuple[Dict[int, int], List[Dict]]:
        """Calculate division positions for all drivers.

        Args:
            active_drivers: List of driver data dicts
            position_key: Key to use for position ('real_time_position' or 'official_position')
            get_driver_color_fn: Function to get driver's division color

        Returns:
            Tuple of (division_positions, all_drivers_with_colors):
            - division_positions: Dict mapping car_idx to division position (1-based)
            - all_drivers_with_colors: List of dicts with car_idx, position, color, official_position
        """
        all_drivers_with_colors = []
        for driver in active_drivers:
            driver_color = get_driver_color_fn(driver['driver_info'])
            all_drivers_with_colors.append({
                'car_idx': driver['car_idx'],
                'position': driver[position_key] if position_key == 'official_position' or not self.race_state_tracker.is_driver_finished(driver['car_idx']) else driver['official_position'],
                'color': driver_color,
                'official_position': driver.get('official_position', driver[position_key])
            })

        division_positions = {}
        for color in set(d['color'] for d in all_drivers_with_colors):
            same_color = [d for d in all_drivers_with_colors if d['color'] == color]
            same_color.sort(key=lambda x: x['position'])
            for i, driver in enumerate(same_color):
                division_positions[driver['car_idx']] = i + 1

        return division_positions, all_drivers_with_colors

    # ═══════════════════════════════════════════════════════════════════════════
    # RACE DATA BUILDING
    # ═══════════════════════════════════════════════════════════════════════════

    def _build_race_data_entry(self, driver: Dict, division_positions: Dict[int, int], gap: str) -> Dict:
        """Build a single race data entry for display.

        Args:
            driver: Driver data dict
            division_positions: Dict mapping car_idx to division position
            gap: Gap string to display

        Returns:
            Dict with formatted race data for this driver
        """
        car_idx = driver['car_idx']
        driver_info = driver['driver_info']
        position = driver.get('position', driver.get('real_time_position', driver.get('official_position', 0)))
        current_color_position = division_positions.get(car_idx, position)
        is_player = (car_idx == self.player_car_idx)

        return {
            'position': position,
            'division_position': current_color_position,
            'car_number': driver_info.get('CarNumber', ''),
            'driver_name': driver_info.get('UserName', ''),
            'driver_info': {
                'UserID': driver_info.get('UserID', ''),
                'UserName': driver_info.get('UserName', '')
            },
            'gap': gap if not driver.get('disconnected', False) else "(DC)",
            'car_idx': car_idx,
            'is_player': is_player
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # SNAPSHOT MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    def _update_race_snapshots(self, active_drivers: List[Dict]) -> None:
        """Update snapshots for all actively racing cars.

        Preserves gap and finish_gap data from previous snapshots while
        updating with current driver data.

        Args:
            active_drivers: List of driver data dicts from telemetry
        """
        for driver_data in active_drivers:
            if self.race_state_tracker.is_driver_finished(driver_data['car_idx']):
                continue  # Don't update finished drivers
            snapshot = self.race_state_tracker.get_snapshot(driver_data['car_idx'])
            gap = snapshot['gap'] if snapshot else ''
            finish_gap = snapshot['finish_gap'] if snapshot and 'finish_gap' in snapshot else None

            snapshot = driver_data.copy()
            snapshot['disconnected'] = False
            snapshot['gap'] = gap
            if finish_gap:
                snapshot['finish_gap'] = finish_gap

            self.race_state_tracker.update_snapshot(driver_data['car_idx'], snapshot)

    def _handle_disconnected_drivers(self, active_drivers: List[Dict], current_session: Dict) -> None:
        """Handle drivers who have disconnected or retired from the race.

        Finds drivers in snapshots who are no longer in active_drivers and adds
        them back with disconnected status. Modifies active_drivers in place.

        Args:
            active_drivers: List of active driver data (modified in place)
            current_session: Current session data from telemetry
        """
        active_car_indices = {d['car_idx'] for d in active_drivers}

        for car_idx in range(TELEMETRY_CONFIG.MAX_CARS):
            snapshot = self.race_state_tracker.get_snapshot(car_idx)
            if snapshot and car_idx not in active_car_indices:
                # This driver disconnected or retired
                if self.ir['SessionState'] < 5:
                    # Still racing - mark as DC, position unknown
                    snapshot['official_position'] = -1
                else:
                    # After checkered - get their final position from results
                    snapshot['official_position'] = self.get_position_from_results(current_session, car_idx)

                # Update the snapshot in tracker
                self.race_state_tracker.update_snapshot(car_idx, snapshot)

                disconnected_driver = snapshot.copy()

                # Skip if snapshot is missing critical fields (corrupted, very old, or minimal snapshot for different class)
                if 'driver_info' not in disconnected_driver or 'car_idx' not in disconnected_driver:
                    continue

                # Multi-class support: only restore drivers in player's class
                if self.player_car_class_id is not None:
                    driver_class_id = disconnected_driver['driver_info'].get('CarClassID')
                    if driver_class_id != self.player_car_class_id:
                        continue

                if self.ir['SessionState'] < 5:
                    disconnected_driver['disconnected'] = True  # Shows "(DC)" in gap column

                # Ensure total_track_position exists for sorting (use stored values or default to 0)
                if 'total_track_position' not in disconnected_driver:
                    current_lap = disconnected_driver.get('current_lap', 0)
                    lap_pct = disconnected_driver.get('lap_pct', 0)
                    disconnected_driver['total_track_position'] = current_lap + lap_pct

                # Only show disconnected drivers if they have a valid position or race is ongoing
                if self.ir['SessionState'] < 5 or disconnected_driver.get('official_position', -1) >= 0:
                    active_drivers.append(disconnected_driver)

    # ═══════════════════════════════════════════════════════════════════════════
    # GAP CALCULATION
    # ═══════════════════════════════════════════════════════════════════════════

    def _calculate_gap(self, driver: Dict, current_color_position: int, current_driver_color: str,
                      active_drivers: List[Dict], all_drivers_with_colors: List[Dict],
                      is_race: bool, position_key: str, live_data: irsdk.IRSDK, current_session: Dict,
                      get_driver_color_fn: Callable) -> str:
        """Calculate gap for a driver to the car ahead in their division.

        Handles all gap calculation scenarios:
        - Division leaders (show "Leader")
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
            position_key: 'real_time_position' or 'official_position'
            live_data: Live telemetry data
            current_session: Current session data
            get_driver_color_fn: Function to get driver's division color

        Returns:
            Gap string for display (e.g., "2.5", "1L", "Leader", "")
        """
        car_idx = driver['car_idx']

        # Division leader shows "Leader"
        if current_color_position == 1:
            return GapCalculator.format_gap_display(is_leader=True)

        # Finished driver - use stored finish gap
        if self.race_state_tracker.is_driver_finished(car_idx):
            snapshot = self.race_state_tracker.get_snapshot(car_idx)
            if snapshot and ('finish_gap' in snapshot or 'finish_lap_gap' in snapshot):
                finish_gap_seconds = snapshot.get('finish_gap')
                finish_lap_gap = snapshot.get('finish_lap_gap', 0)
                return GapCalculator.format_gap_display(time_gap=finish_gap_seconds, lap_gap=finish_lap_gap)
            return ""

        # Live racing - calculate real-time gap
        if is_race:
            return self._calculate_live_race_gap(driver, current_driver_color, active_drivers,
                                                position_key, live_data, current_session, get_driver_color_fn)

        # Practice/Qualifying - use best lap times
        return self._calculate_practice_gap(car_idx, current_color_position, current_driver_color,
                                           all_drivers_with_colors, current_session)

    def _calculate_live_race_gap(self, driver: Dict, current_driver_color: str,
                                active_drivers: List[Dict], position_key: str,
                                live_data: irsdk.IRSDK, current_session: Dict,
                                get_driver_color_fn: Callable) -> str:
        """Calculate live gap during a race.

        Args:
            driver: Current driver data
            current_driver_color: Driver's division color
            active_drivers: List of all active drivers
            position_key: Position key to use
            live_data: Live telemetry data
            current_session: Current session data
            get_driver_color_fn: Function to get driver's division color

        Returns:
            Gap string
        """
        car_idx = driver['car_idx']

        # Find all drivers in the same division
        same_color_drivers = []
        for temp_driver in active_drivers:
            temp_color = get_driver_color_fn(temp_driver['driver_info'])
            if temp_color == current_driver_color:
                same_color_drivers.append({
                    'car_idx': temp_driver['car_idx'],
                    'position': temp_driver[position_key],
                    'total_track_position': temp_driver['total_track_position'],
                    'current_lap': temp_driver['current_lap'],
                    'lap_pct': temp_driver['lap_pct']
                })

        same_color_drivers.sort(key=lambda x: x['position'])

        # Find this driver's position within their division
        current_pos_index = None
        for i, temp_driver in enumerate(same_color_drivers):
            if temp_driver['car_idx'] == car_idx:
                current_pos_index = i
                break

        # No car ahead in division
        if current_pos_index is None or current_pos_index == 0:
            return ""

        car_ahead_idx = same_color_drivers[current_pos_index - 1]['car_idx']

        # Car ahead has finished, use snapshot gap
        if self.race_state_tracker.is_driver_finished(car_ahead_idx):
            snapshot = self.race_state_tracker.get_snapshot(car_idx)
            return snapshot.get('gap', '') if snapshot else ""

        # Both cars still racing - calculate live time gap
        car_idx_est_time = live_data['CarIdxEstTime']
        current_est_time = car_idx_est_time[car_idx]
        ahead_est_time = car_idx_est_time[car_ahead_idx]

        time_gap_raw = None

        # If both cars on same lap, use iRacing's estimated time (most accurate)
        if current_est_time > 0 and ahead_est_time > 0 and same_color_drivers[current_pos_index - 1]['current_lap'] == driver['current_lap']:
            time_gap_raw = GapCalculator.calculate_time_gap(ahead_est_time, current_est_time)
        else:
            # Different laps - estimate gap based on track position difference
            position_diff = same_color_drivers[current_pos_index - 1]['total_track_position'] - driver['total_track_position']
            time_gap_raw = position_diff * self.get_fastest_lap_time(current_session)

        # Calculate exact lap distance difference for lap-based gaps
        lap_gap = GapCalculator.calculate_lap_gap(same_color_drivers[current_pos_index - 1]['total_track_position'], driver['total_track_position'])

        # Handle negative time gaps (shouldn't happen but be safe)
        if time_gap_raw is not None and time_gap_raw < 0:
            time_gap_raw = abs(time_gap_raw)

        # Format the gap
        gap = GapCalculator.format_gap_display(time_gap=time_gap_raw, lap_gap=lap_gap)

        # Store gap continuously in snapshot - used when driver finishes to freeze the display
        if gap and gap != "":
            snapshot = self.race_state_tracker.get_snapshot(car_idx)
            if snapshot:
                snapshot['gap'] = gap
                self.race_state_tracker.update_snapshot(car_idx, snapshot)

        return gap

    def _calculate_practice_gap(self, car_idx: int, current_color_position: int,
                               current_driver_color: str, all_drivers_with_colors: List[Dict],
                               current_session: Dict) -> str:
        """Calculate gap for practice/qualifying based on best lap times.

        Args:
            car_idx: Current car index
            current_color_position: Position within division
            current_driver_color: Division color
            all_drivers_with_colors: List of drivers with color info
            current_session: Current session data

        Returns:
            Gap string formatted to 3 decimal places
        """
        same_color_drivers = [d for d in all_drivers_with_colors if d['color'] == current_driver_color]
        same_color_drivers.sort(key=lambda x: x['position'])

        if len(same_color_drivers) < current_color_position - 1:
            return ""

        car_ahead_idx = same_color_drivers[current_color_position - 2]['car_idx']
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

    def process_telemetry(self, get_driver_color_fn: Callable) -> Optional[List[Dict]]:
        """Process telemetry data - orchestrates telemetry processing using helper methods.

        Args:
            get_driver_color_fn: Function to get driver's division color

        Returns:
            List of race data dicts or None if processing failed
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
            self._identify_player(drivers)

            live_data = self.ir
            if not live_data:
                return None

            # Process positions (different logic for race vs practice/qualifying)
            if is_race:
                self.update_finish_status(live_data, current_session, get_driver_color_fn)
                active_drivers = self.calculate_real_time_positions(drivers, live_data)
                position_key = 'real_time_position'

                if active_drivers:
                    # Update snapshots for active drivers
                    self._update_race_snapshots(active_drivers)

                    # Handle disconnected/retired drivers
                    self._handle_disconnected_drivers(active_drivers, current_session)

                    # Separate finished and racing drivers to prevent position contamination
                    finished_drivers = [d for d in active_drivers if self.race_state_tracker.is_driver_finished(d['car_idx'])]
                    racing_drivers = [d for d in active_drivers if not self.race_state_tracker.is_driver_finished(d['car_idx'])]

                    # Sort finished drivers by their official results position
                    for driver in finished_drivers:
                        driver['final_position'] = self.get_position_from_results(current_session, driver['car_idx'])
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
                            driver['real_time_position'] = available_positions[i]
                        else:
                            # Fallback: if we run out of available positions (shouldn't happen)
                            # assign next number after highest
                            driver['real_time_position'] = total_drivers + (i - len(available_positions)) + 1

                    # Merge them back: finished drivers first (in order), then racing drivers
                    active_drivers = finished_drivers + racing_drivers
            else:
                active_drivers = self.get_official_positions(drivers, live_data)
                position_key = 'official_position'

            if not active_drivers:
                return None

            # Calculate division positions
            division_positions, all_drivers_with_colors = self._calculate_division_positions(
                active_drivers, position_key, get_driver_color_fn
            )

            race_data = []

            for driver in active_drivers:
                car_idx = driver['car_idx']
                driver_info = driver['driver_info']

                if self.race_state_tracker.is_driver_finished(car_idx):
                    # Use pre-calculated final_position if available (from Solution 3), otherwise fetch from results
                    position = driver.get('final_position', self.get_position_from_results(current_session, car_idx))
                else:
                    position = driver[position_key]

                current_driver_color = get_driver_color_fn(driver_info)
                current_color_position = division_positions.get(car_idx, position)

                # Calculate gap using helper method
                gap = self._calculate_gap(
                    driver, current_color_position, current_driver_color,
                    active_drivers, all_drivers_with_colors,
                    is_race, position_key, live_data, current_session,
                    get_driver_color_fn
                )

                # Build and append race data entry
                driver['position'] = position  # Ensure position is set for helper method
                race_entry = self._build_race_data_entry(driver, division_positions, gap)
                race_data.append(race_entry)

            race_data.sort(key=lambda x: x['position'])

            return race_data

        except Exception as e:
            logger.error(f"Processing error: {e}", exc_info=True)
            print(f"Processing error: {e}")
            return None
