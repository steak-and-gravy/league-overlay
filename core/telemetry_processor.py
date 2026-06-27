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

from typing import Dict, List, Optional, Tuple, Any, Callable, Set
import time
import irsdk

from config.constants import TIMING
from config.logging_config import get_logger
from core.gap_calculator import GapCalculator
from core.division_manager import DivisionManager
from core.race_state_tracker import RaceStateTracker
from core.position_calculator import PositionCalculator
from core.driver_state import DriverState
from core.manufacturer import extract_manufacturer
from core.driver_info import build_driver_lookup, get_pace_car_indices, is_pace_car

logger = get_logger(__name__)


class TelemetryProcessor:
    """Processes iRacing telemetry data and calculates race positions, gaps, and state."""

    RECENT_LAP_FLASH_DURATION_SECONDS = 5.0
    RECENT_LAP_FLASH_FIRST_LAP = "first_lap"
    RECENT_LAP_FLASH_FASTER = "faster"
    RECENT_LAP_FLASH_SLOWER = "slower"

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
        self.current_subsession_id: Optional[int] = None
        self.current_session_type: Optional[str] = None
        self.previous_session_type: Optional[str] = None

        # Lap time cache - preserves lap times even when drivers go inactive
        # Maps car_idx -> (best_lap, last_lap)
        self.lap_time_cache: Dict[int, Tuple[float, float]] = {}
        self.recent_lap_flashes: Dict[int, Dict[str, Any]] = {}
        self.last_lap_observations: Dict[int, Tuple[int, float, float]] = {}
        self.pending_lap_completions: Dict[int, int] = {}

        # Pit stop tracking - maps car_idx to last pit lap number
        self.pit_tracking: Dict[int, int] = {}
        self.pit_state: Dict[int, Dict[str, Any]] = {}
        self.pit_on_road: Dict[int, bool] = {}
        self.pit_exit_out_lap: Dict[int, int] = {}

        # Tow tracking - maps car_idx to towing status (best-effort heuristic)
        self.tow_tracking: Dict[int, bool] = {}
        self.tow_last_surface: Dict[int, int] = {}
        self.tow_last_on_pit_road: Dict[int, bool] = {}
        self.tow_last_track_position: Dict[int, float] = {}
        self.tow_last_update_time: Dict[int, float] = {}
        self.tow_last_valid_track_position: Dict[int, float] = {}
        self.tow_last_valid_time: Dict[int, float] = {}
        self.tow_end_time: Dict[int, float] = {}
        self.tow_frozen_track_position: Dict[int, float] = {}
        self.tow_last_live_track_position: Dict[int, float] = {}
        self.tow_last_wait_log_time: Dict[int, float] = {}
        self.cooldown_final_position_dedup_complete: bool = False

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
        self.recent_lap_flashes.clear()
        self.last_lap_observations.clear()
        self.pending_lap_completions.clear()

        # Clear pit tracking on session change
        self.pit_tracking.clear()
        self.pit_state.clear()
        self.pit_on_road.clear()
        self.pit_exit_out_lap.clear()

        # Clear tow tracking on session change
        self.tow_tracking.clear()
        self.tow_last_surface.clear()
        self.tow_last_on_pit_road.clear()
        self.tow_last_track_position.clear()
        self.tow_last_update_time.clear()
        self.tow_last_valid_track_position.clear()
        self.tow_last_valid_time.clear()
        self.tow_end_time.clear()
        self.tow_frozen_track_position.clear()
        self.tow_last_live_track_position.clear()
        self.tow_last_wait_log_time.clear()

        self.cooldown_final_position_dedup_complete = False

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

            pace_car_indices = get_pace_car_indices(driver_info)

            # Convert to dict for O(1) lookups instead of O(n) - significant performance gain with 40+ drivers
            drivers = build_driver_lookup(
                driver for driver in drivers_list
                if not is_pace_car(driver, pace_car_indices)
            )

        except (KeyError, TypeError) as e:
            logger.debug(f"Error getting driver info: {e}")
            return None

        try:
            session_num = self.ir['SessionNum']
            current_session = self.ir['SessionInfo']['Sessions'][session_num]
            session_type = current_session['SessionType']
            weekend_info = self.ir['WeekendInfo']
            session_id = weekend_info['SessionID']
            try:
                subsession_id = weekend_info['SubSessionID']
            except (KeyError, TypeError):
                subsession_id = None
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
            'subsession_id': subsession_id,
            'session_type': session_type,
            'current_session': current_session,
            'results_lookup': results_lookup,  # O(1) lookup dictionary
            'drivers': drivers,
            'pace_car_indices': pace_car_indices,
            'fastest_lap_time': (
                fastest_lap_time
                if fastest_lap_time != float('inf')
                else TIMING.DEFAULT_LAP_TIME_FALLBACK
            )
        }

        return (drivers, session_data, is_race)

    def _get_car_idx_array_length(self, *field_names: str, minimum: int = 0) -> int:
        """Return the largest available live CarIdx array length."""
        max_len = minimum
        for field_name in field_names:
            try:
                values = self.ir[field_name]
            except (KeyError, TypeError):
                continue

            try:
                max_len = max(max_len, len(values))
            except TypeError:
                continue

        return max_len

    @staticmethod
    def _get_driver_lookup_capacity(drivers: Dict[int, Dict]) -> int:
        """Return the array size needed to safely index known DriverInfo entries."""
        valid_indices = [
            car_idx for car_idx in drivers.keys()
            if isinstance(car_idx, int) and car_idx >= 0
        ]
        if not valid_indices:
            return 0
        return max(valid_indices) + 1

    def _get_driver_lookup(self, session_data: Dict) -> Dict[int, Dict]:
        """Return DriverInfo lookup from session data or current telemetry."""
        driver_lookup = session_data.get('drivers', {})
        if driver_lookup:
            return driver_lookup

        try:
            driver_info = self.ir['DriverInfo']
            drivers_info = driver_info['Drivers']
        except (KeyError, TypeError):
            return {}

        pace_car_indices = get_pace_car_indices(driver_info)
        return build_driver_lookup(
            driver for driver in drivers_info
            if not is_pace_car(driver, pace_car_indices)
        )

    def _detect_session_change(self, session_data: Dict) -> bool:
        """Detect if session has changed and update tracking.

        Args:
            session_data: Dict with 'session_id', 'subsession_id', and 'session_type'

        Returns:
            True if session changed, False otherwise
        """
        session_id = session_data['session_id']
        subsession_id = session_data.get('subsession_id')
        session_type = session_data['session_type']

        # SubSessionID can be transiently unavailable during transitions.
        # Treat None as "unknown" and avoid false session resets unless both are known.
        subsession_changed = (
            subsession_id is not None
            and self.current_subsession_id is not None
            and self.current_subsession_id != subsession_id
        )

        if (self.current_session_id != session_id
                or subsession_changed
                or self.current_session_type != session_type):
            logger.info(
                f"Session changed: {session_type} "
                f"(SessionID: {session_id}, SubSessionID: {subsession_id})"
            )
            self.previous_session_type = self.current_session_type
            self.current_session_id = session_id
            if subsession_id is not None:
                self.current_subsession_id = subsession_id
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

    @staticmethod
    def _coerce_lap_time(lap_time: Any) -> float:
        """Return a numeric lap time or 0.0 when telemetry data is missing."""
        return float(lap_time) if isinstance(lap_time, (int, float)) else 0.0

    @staticmethod
    def _is_valid_display_lap_time(lap_time: float) -> bool:
        """Return True when the lap time is valid for display and flash behavior."""
        return 0 < lap_time < 999

    @staticmethod
    def _is_qualifying_session(session_type: Optional[str]) -> bool:
        """Return True when session behavior should use qualifying lap rules."""
        return bool(session_type and "qual" in session_type.lower())

    def _is_best_lap_flash_session(self, session_type: Optional[str]) -> bool:
        """Return True when recent-lap color should compare against session best."""
        if session_type is None:
            return False

        normalized_session_type = session_type.lower()
        return "practice" in normalized_session_type or "qual" in normalized_session_type

    def _is_recent_lap_flash_session(self, session_type: Optional[str]) -> bool:
        """Return True when recent-lap flashes are enabled for this session type."""
        if session_type is None:
            return True

        normalized_session_type = session_type.lower()
        return "practice" in normalized_session_type or "qual" in normalized_session_type

    def _resolve_observed_best_lap(
        self,
        last_lap_time: float,
        best_lap_time: float,
        previous_best_lap_time: float = 0.0,
    ) -> float:
        """Return the best lap known from telemetry and observed last-lap changes."""
        observed_best_lap = best_lap_time
        if self._is_valid_display_lap_time(last_lap_time):
            if self._is_valid_display_lap_time(observed_best_lap):
                observed_best_lap = min(observed_best_lap, last_lap_time)
            elif self._is_valid_display_lap_time(previous_best_lap_time):
                observed_best_lap = min(previous_best_lap_time, last_lap_time)
            else:
                observed_best_lap = last_lap_time
        elif (
            not self._is_valid_display_lap_time(observed_best_lap)
            and self._is_valid_display_lap_time(previous_best_lap_time)
        ):
            observed_best_lap = previous_best_lap_time

        return observed_best_lap

    def _prune_recent_lap_flashes(self, now: float) -> None:
        """Drop expired last-lap flash entries."""
        expired_car_idxs = [
            car_idx for car_idx, flash_state in self.recent_lap_flashes.items()
            if flash_state['expires_at'] <= now
        ]
        for car_idx in expired_car_idxs:
            self.recent_lap_flashes.pop(car_idx, None)

    def _classify_recent_lap_flash_state(
        self,
        lap_time: float,
        previous_lap_time: float,
        previous_best_lap_time: float = 0.0,
        session_type: Optional[str] = None,
    ) -> str:
        """Return the semantic state for a newly completed lap flash."""
        if self._is_best_lap_flash_session(session_type):
            if not self._is_valid_display_lap_time(previous_best_lap_time):
                if self._is_qualifying_session(session_type):
                    return self.RECENT_LAP_FLASH_FASTER
                return self.RECENT_LAP_FLASH_FIRST_LAP
            if lap_time < previous_best_lap_time - 1e-6:
                return self.RECENT_LAP_FLASH_FASTER
            return self.RECENT_LAP_FLASH_SLOWER

        if not self._is_valid_display_lap_time(previous_lap_time):
            return self.RECENT_LAP_FLASH_FIRST_LAP

        if lap_time > previous_lap_time + 1e-6:
            return self.RECENT_LAP_FLASH_SLOWER
        return self.RECENT_LAP_FLASH_FASTER

    def _activate_recent_lap_flash(self, car_idx: int, lap_time: float, now: float, flash_state: str) -> None:
        """Store a temporary flash entry for a newly completed lap."""
        if not self._is_valid_display_lap_time(lap_time):
            return

        flash_text = GapCalculator.format_lap_time(lap_time)
        if flash_text in ("", "--"):
            return

        self.recent_lap_flashes[car_idx] = {
            'text': flash_text,
            'state': flash_state,
            'expires_at': now + self.RECENT_LAP_FLASH_DURATION_SECONDS
        }

    def _get_active_recent_lap_flash(self, car_idx: int, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Return active recent-lap flash state for a car or None."""
        current_time = time.monotonic() if now is None else now
        flash_state = self.recent_lap_flashes.get(car_idx)
        if flash_state is None:
            return None
        if flash_state['expires_at'] <= current_time:
            self.recent_lap_flashes.pop(car_idx, None)
            return None
        return flash_state

    def _get_recent_lap_flash_text(self, car_idx: int, now: Optional[float] = None) -> str:
        """Return active recent-lap flash text for a car or an empty string."""
        flash_state = self._get_active_recent_lap_flash(car_idx, now=now)
        if flash_state is None:
            return ""
        return flash_state['text']

    def _get_recent_lap_flash_state(self, car_idx: int, now: Optional[float] = None) -> str:
        """Return active recent-lap flash state for a car or an empty string."""
        flash_state = self._get_active_recent_lap_flash(car_idx, now=now)
        if flash_state is None:
            return ""
        return flash_state.get('state', self.RECENT_LAP_FLASH_FASTER)

    def _update_recent_lap_flashes(
        self,
        car_idx_lap: Any,
        car_idx_last_lap: Any,
        car_idx_best_lap: Any = None,
        session_type: Optional[str] = None,
    ) -> None:
        """Track newly completed laps and expose a 5-second flash string per car."""
        now = time.monotonic()
        self._prune_recent_lap_flashes(now)

        flash_session_enabled = self._is_recent_lap_flash_session(session_type)

        if not car_idx_lap or not car_idx_last_lap:
            return

        max_len = min(len(car_idx_lap), len(car_idx_last_lap))
        if car_idx_best_lap:
            max_len = min(max_len, len(car_idx_best_lap))

        for car_idx in range(max_len):
            current_lap = car_idx_lap[car_idx]
            current_last_lap = self._coerce_lap_time(car_idx_last_lap[car_idx])
            current_best_lap = self._coerce_lap_time(car_idx_best_lap[car_idx]) if car_idx_best_lap else 0.0
            previous_observation = self.last_lap_observations.get(car_idx)

            if previous_observation is None:
                observed_best_lap = self._resolve_observed_best_lap(current_last_lap, current_best_lap)
                self.last_lap_observations[car_idx] = (current_lap, current_last_lap, observed_best_lap)
                continue

            previous_lap, previous_last_lap, previous_best_lap = previous_observation
            observed_best_lap = self._resolve_observed_best_lap(
                current_last_lap,
                current_best_lap,
                previous_best_lap,
            )

            if current_lap < 0:
                self.pending_lap_completions.pop(car_idx, None)
                self.last_lap_observations[car_idx] = (current_lap, current_last_lap, observed_best_lap)
                continue

            if previous_lap < 0 <= current_lap:
                self.pending_lap_completions.pop(car_idx, None)
                self.last_lap_observations[car_idx] = (current_lap, current_last_lap, observed_best_lap)
                continue

            if current_lap < previous_lap:
                self.pending_lap_completions.pop(car_idx, None)
            elif current_lap > previous_lap:
                self.pending_lap_completions[car_idx] = current_lap - 1

            last_lap_changed = (
                self._is_valid_display_lap_time(current_last_lap)
                and abs(current_last_lap - previous_last_lap) > 1e-6
            )
            pending_lap_completion = self.pending_lap_completions.get(car_idx) is not None

            if pending_lap_completion and not last_lap_changed:
                observed_best_lap = previous_best_lap

            if pending_lap_completion and last_lap_changed:
                flash_state = self._classify_recent_lap_flash_state(
                    current_last_lap,
                    previous_last_lap,
                    previous_best_lap,
                    session_type=session_type,
                )
                if flash_session_enabled and flash_state != self.RECENT_LAP_FLASH_FIRST_LAP:
                    self._activate_recent_lap_flash(car_idx, current_last_lap, now, flash_state)
                self.pending_lap_completions.pop(car_idx, None)

            self.last_lap_observations[car_idx] = (current_lap, current_last_lap, observed_best_lap)

    def _update_pit_tracking(self) -> None:
        """Update pit tracking by monitoring pit-road enter/exit transitions.

        A pit stop is only considered valid when a car enters pit road and
        reaches the pit stall before exiting. Last-pit-lap uses the lap when
        pit road was entered. Out-lap uses corrected exit-lap semantics to
        handle start/finish edge cases.
        """
        TRACK_SURFACE_IN_PIT_STALL = 1
        try:
            car_idx_on_pit_road = self.ir['CarIdxOnPitRoad']
            car_idx_track_surface = self.ir['CarIdxTrackSurface']
            car_idx_lap = self.ir['CarIdxLap']
            car_idx_lap_pct = self.ir['CarIdxLapDistPct']
            car_idx_class_position = self.ir['CarIdxClassPosition']

            if (not car_idx_on_pit_road or not car_idx_lap
                    or not car_idx_track_surface or not car_idx_lap_pct
                    or not car_idx_class_position):
                return

            max_len = min(
                len(car_idx_on_pit_road),
                len(car_idx_track_surface),
                len(car_idx_lap),
                len(car_idx_lap_pct),
                len(car_idx_class_position)
            )

            for car_idx in range(max_len):
                current_on_pit = bool(car_idx_on_pit_road[car_idx])
                current_in_stall = (car_idx_track_surface[car_idx] == TRACK_SURFACE_IN_PIT_STALL)
                current_lap = car_idx_lap[car_idx]
                current_lap_pct = car_idx_lap_pct[car_idx]
                current_class_position = car_idx_class_position[car_idx]

                # When a car temporarily goes inactive (e.g., team driver swap), telemetry can
                # briefly report out-of-race values. Preserve last known pit state in this case
                # instead of treating it like a true pit exit.
                if current_class_position == 0 or current_lap < 0:
                    continue

                state = self.pit_state.setdefault(
                    car_idx,
                    {
                        'in_pit_road_prev': False,
                        'entry_lap': 0,
                        'saw_stall': False
                    }
                )

                was_on_pit = bool(state['in_pit_road_prev'])

                # Pit-road entry transition: capture lap baseline for this stop.
                if current_on_pit and not was_on_pit:
                    state['entry_lap'] = current_lap
                    state['saw_stall'] = False

                if current_on_pit and current_in_stall:
                    state['saw_stall'] = True

                # Pit-road exit transition: only commit a pit stop if stall was visited.
                if not current_on_pit and was_on_pit:
                    if state['saw_stall']:
                        entry_lap = int(state['entry_lap']) if state['entry_lap'] > 0 else current_lap
                        self.pit_tracking[car_idx] = entry_lap

                        out_lap = current_lap + (1 if current_lap_pct > 0.5 else 0)
                        self.pit_exit_out_lap[car_idx] = out_lap

                    state['entry_lap'] = 0
                    state['saw_stall'] = False

                self.pit_on_road[car_idx] = current_on_pit
                state['in_pit_road_prev'] = current_on_pit

        except (KeyError, TypeError, IndexError) as e:
            logger.debug(f"Error updating pit tracking: {e}")

    @staticmethod
    def _estimate_tow_duration_to_pit(
        tow_start_position: Optional[float],
        current_track_position: float,
        track_length_m: float
    ) -> Tuple[Optional[float], Optional[float]]:
        """Estimate tow duration from an on-track position to the current pit position."""
        if tow_start_position is None or tow_start_position < 0:
            return None, None
        if current_track_position < 0 or track_length_m <= 0:
            return None, None

        if current_track_position < tow_start_position:
            # Must continue around track to pit.
            delta_pos = 1.0 - tow_start_position + current_track_position
        else:
            delta_pos = current_track_position - tow_start_position

        tow_length_m = delta_pos * track_length_m
        tow_speed_ms = 30.0
        tow_time_fixed_s = 50.0
        estimated_tow_seconds = (tow_length_m / tow_speed_ms) + tow_time_fixed_s
        return estimated_tow_seconds, tow_length_m

    def _update_tow_tracking(self) -> None:
        """Update tow tracking using pit-stall transitions and tow end timers.

        Player car uses explicit PlayerCarTowTime when available.
        Other cars use transition-based tow detection with a teleport speed check.
        """
        TRACK_SURFACE_IN_PIT_STALL = 1
        TELEPORT_SPEED_THRESHOLD_KPH = 500.0
        TOW_VALID_SNAPSHOT_MAX_AGE_SECONDS = 20.0

        try:
            now = float(self.ir['SessionTime'])
            has_session_time = True
        except (KeyError, TypeError, ValueError):
            now = time.monotonic()
            has_session_time = False

        try:
            car_idx_track_surface = self.ir['CarIdxTrackSurface']
            car_idx_on_pit_road = self.ir['CarIdxOnPitRoad']
            car_idx_lap = self.ir['CarIdxLap']
            car_idx_lap_pct = self.ir['CarIdxLapDistPct']
        except (KeyError, TypeError):
            if has_session_time:
                self._sync_disconnected_tow_snapshots_by_timer(now)
            return

        try:
            player_tow_time = float(self.ir['PlayerCarTowTime'])
        except (KeyError, TypeError, ValueError):
            player_tow_time = 0.0

        try:
            drivers_info = self.ir['DriverInfo']['Drivers']
        except (KeyError, TypeError):
            drivers_info = []
        driver_lookup = build_driver_lookup(drivers_info)

        track_length_m = 0.0
        try:
            track_length_raw = self.ir['WeekendInfo']['TrackLength']
            if isinstance(track_length_raw, (int, float)):
                track_length_m = float(track_length_raw)
            elif isinstance(track_length_raw, str):
                parts = track_length_raw.strip().split()
                if parts:
                    value = float(parts[0])
                    unit = parts[1].lower() if len(parts) > 1 else "m"
                    if unit.startswith("km"):
                        track_length_m = value * 1000.0
                    elif unit.startswith("mi"):
                        track_length_m = value * 1609.34
                    else:
                        track_length_m = value
        except (KeyError, TypeError, ValueError):
            track_length_m = 0.0

        if (not car_idx_track_surface or not car_idx_on_pit_road
                or not car_idx_lap or not car_idx_lap_pct):
            if has_session_time:
                self._sync_disconnected_tow_snapshots_by_timer(now)
            return

        player_car_idx = self.position_calculator.player_car_idx

        max_len = min(
            len(car_idx_track_surface),
            len(car_idx_on_pit_road),
            len(car_idx_lap),
            len(car_idx_lap_pct)
        )

        for car_idx in range(max_len):
            current_surface = car_idx_track_surface[car_idx]
            current_on_pit = car_idx_on_pit_road[car_idx]
            current_track_position = car_idx_lap[car_idx] + car_idx_lap_pct[car_idx]
            current_lap = car_idx_lap[car_idx]
            car_number = ""
            driver_info = driver_lookup.get(car_idx, {})
            car_number = str(driver_info.get('CarNumber', '')).strip()
            is_debug_car_number_8 = (car_number == "8")

            prev_surface = self.tow_last_surface.get(car_idx)
            prev_track_position = self.tow_last_track_position.get(car_idx)
            prev_update_time = self.tow_last_update_time.get(car_idx)
            prev_valid_track_position = self.tow_last_valid_track_position.get(car_idx)
            prev_valid_time = self.tow_last_valid_time.get(car_idx)
            snapshot = self.race_state_tracker.get_snapshot(car_idx)

            current_invalid = (current_lap < 0 or current_track_position < 0)
            prev_invalid = (prev_track_position is None or prev_track_position < 0)

            # Player tow timer is authoritative when available.
            if car_idx == player_car_idx and player_tow_time > 0:
                if not self.tow_tracking.get(car_idx, False):
                    logger.debug(
                        f"TOW_START player car_idx={car_idx} "
                        f"player_tow_time={player_tow_time:.1f}s on_pit={current_on_pit} "
                        f"surface={current_surface}"
                    )
                self.tow_tracking[car_idx] = True
                if car_idx not in self.tow_frozen_track_position:
                    frozen_position = self.tow_last_live_track_position.get(car_idx)
                    if frozen_position is None:
                        if prev_track_position is not None and prev_track_position >= 0:
                            frozen_position = prev_track_position
                        elif prev_valid_track_position is not None and prev_valid_track_position >= 0:
                            frozen_position = prev_valid_track_position
                        else:
                            frozen_position = current_track_position
                    self.tow_frozen_track_position[car_idx] = frozen_position
                if has_session_time:
                    self.tow_end_time[car_idx] = now + player_tow_time

            # A car that was previously restored as disconnected can reappear
            # directly in pit lane or the stall. If the car was on track before
            # the disconnect, treat that reconnect as a tow/freeze so the pit
            # placement cannot temporarily promote the car in the standings.
            snapshot_track_position = None
            if snapshot is not None:
                snapshot_track_position = snapshot.total_track_position

            was_in_pit_before_disconnect = (
                prev_surface == TRACK_SURFACE_IN_PIT_STALL
                or bool(self.tow_last_on_pit_road.get(car_idx, False))
            )
            in_pit_location = current_on_pit or current_surface == TRACK_SURFACE_IN_PIT_STALL
            started_reconnect_tow_this_frame = False

            reconnected_into_pit = (
                not current_invalid
                and snapshot is not None
                and snapshot.is_disconnected
                and not self.race_state_tracker.is_driver_finished(car_idx)
                and in_pit_location
                and not was_in_pit_before_disconnect
                and snapshot_track_position is not None
                and snapshot_track_position >= 0
            )

            if reconnected_into_pit and not self.tow_tracking.get(car_idx, False):
                self.tow_tracking[car_idx] = True
                self.tow_frozen_track_position[car_idx] = snapshot_track_position
                started_reconnect_tow_this_frame = True
                existing_end_time = self.tow_end_time.get(car_idx, 0.0)
                timer_source = "existing"
                estimated_tow_seconds = None
                tow_length_m = None
                if has_session_time and existing_end_time > now:
                    self.tow_end_time[car_idx] = existing_end_time
                else:
                    timer_source = "estimated"
                    estimated_tow_seconds, tow_length_m = self._estimate_tow_duration_to_pit(
                        snapshot_track_position,
                        current_track_position,
                        track_length_m
                    )
                    if estimated_tow_seconds is not None and has_session_time:
                        self.tow_end_time[car_idx] = now + estimated_tow_seconds
                    else:
                        timer_source = "missing"
                        # No estimate available: keep TOW until movement or pit exit clears it.
                        self.tow_end_time[car_idx] = 0.0
                logger.info(
                    f"TOW_START reconnect car_idx={car_idx} car_num={car_number} "
                    f"snapshot_track_pos={snapshot_track_position:.4f} "
                    f"current_track_pos={current_track_position:.4f} "
                    f"existing_end_time={existing_end_time:.1f} "
                    f"timer_source={timer_source} "
                    f"tow_length_m={tow_length_m} "
                    f"estimated_tow_seconds={estimated_tow_seconds} "
                    f"session_time={now:.1f} "
                    f"end_time={self.tow_end_time.get(car_idx, 0.0):.1f} "
                    f"end_time_set={self.tow_end_time.get(car_idx, 0.0) > 0} "
                    f"on_pit={current_on_pit} surface={current_surface} "
                    f"was_in_pit_before_disconnect={was_in_pit_before_disconnect} "
                    f"has_session_time={has_session_time}"
                )

            # Clear tow state when tow timer expires or car leaves pit road/stall.
            if self.tow_tracking.get(car_idx, False):
                end_time = self.tow_end_time.get(car_idx, 0.0)
                player_tow_done = (car_idx == player_car_idx and player_tow_time <= 0)
                non_player_tow_done = (
                    has_session_time
                    and car_idx != player_car_idx
                    and end_time > 0
                    and now >= end_time
                )
                moving_forward = False
                if (not started_reconnect_tow_this_frame
                        and not current_invalid and not prev_invalid and track_length_m > 0):
                    small_distance_pct = 0.05 / track_length_m
                    moving_forward = current_track_position > (prev_track_position + small_distance_pct)

                left_pit_and_stall = (
                    not current_invalid
                    and not current_on_pit
                    and current_surface != TRACK_SURFACE_IN_PIT_STALL
                )
                if (player_tow_done
                        or non_player_tow_done
                        or moving_forward
                        or left_pit_and_stall):
                    clear_reasons = []
                    if player_tow_done:
                        clear_reasons.append("player_timer_done")
                    if non_player_tow_done:
                        clear_reasons.append("estimated_tow_end")
                    if moving_forward:
                        clear_reasons.append("moving_forward")
                    if left_pit_and_stall:
                        clear_reasons.append("left_pit_and_stall")
                    logger.debug(
                        f"TOW_END car_idx={car_idx} car_num={car_number} reasons={','.join(clear_reasons)} "
                        f"on_pit={current_on_pit} surface={current_surface} "
                        f"track_pos={current_track_position:.4f}"
                    )
                    self.tow_tracking[car_idx] = False
                    self.tow_end_time[car_idx] = 0.0
                    if car_idx in self.tow_frozen_track_position:
                        del self.tow_frozen_track_position[car_idx]
                    self._sync_disconnected_tow_snapshot_after_tow_end(
                        car_idx,
                        current_track_position,
                        current_invalid
                    )

            # Detect tow-like teleport into pit stall.
            entered_stall = (prev_surface is not None
                             and prev_surface != TRACK_SURFACE_IN_PIT_STALL
                             and current_surface == TRACK_SURFACE_IN_PIT_STALL)
            if entered_stall and current_on_pit and not self.tow_tracking.get(car_idx, False):
                avg_speed_kph = 0.0
                speed_calc_valid = (not current_invalid and not prev_invalid)
                used_valid_snapshot_fallback = False
                if (speed_calc_valid and track_length_m > 0
                        and prev_update_time is not None and now > prev_update_time):
                    delta_pos = abs(current_track_position - prev_track_position)
                    delta_m = delta_pos * track_length_m
                    delta_t_s = now - prev_update_time
                    avg_speed_kph = (delta_m / 1000.0) / (delta_t_s / 3600.0)
                elif (not current_invalid and track_length_m > 0
                      and prev_valid_track_position is not None
                      and prev_valid_time is not None
                      and now > prev_valid_time):
                    snapshot_age = now - prev_valid_time
                    if snapshot_age <= TOW_VALID_SNAPSHOT_MAX_AGE_SECONDS:
                        delta_pos = abs(current_track_position - prev_valid_track_position)
                        delta_m = delta_pos * track_length_m
                        delta_t_s = now - prev_valid_time
                        avg_speed_kph = (delta_m / 1000.0) / (delta_t_s / 3600.0)
                        used_valid_snapshot_fallback = True
                        speed_calc_valid = True
                teleporting_to_pit = (avg_speed_kph > TELEPORT_SPEED_THRESHOLD_KPH)
                logger.debug(
                    f"TOW_CHECK car_idx={car_idx} car_num={car_number} entered_stall={entered_stall} "
                    f"on_pit={current_on_pit} "
                    f"avg_speed_kph={avg_speed_kph:.1f} teleport={teleporting_to_pit} "
                    f"speed_calc_valid={speed_calc_valid} "
                    f"used_valid_snapshot_fallback={used_valid_snapshot_fallback}"
                )

                if is_debug_car_number_8 and not teleporting_to_pit:
                    logger.debug(
                        f"TOW_NOT_STARTED car_num=8 car_idx={car_idx} "
                        f"cond_teleport={teleporting_to_pit} "
                        f"cond_speed_calc_valid={speed_calc_valid} "
                        f"used_valid_snapshot_fallback={used_valid_snapshot_fallback}"
                    )

                if teleporting_to_pit:
                    self.tow_tracking[car_idx] = True
                    frozen_position = self.tow_frozen_track_position.get(car_idx)
                    if frozen_position is None:
                        frozen_position = self.tow_last_live_track_position.get(car_idx)
                        if frozen_position is None:
                            if prev_track_position is not None and prev_track_position >= 0:
                                frozen_position = prev_track_position
                            elif prev_valid_track_position is not None and prev_valid_track_position >= 0:
                                frozen_position = prev_valid_track_position
                            else:
                                frozen_position = current_track_position
                        self.tow_frozen_track_position[car_idx] = frozen_position
                    # Estimate non-player tow duration using bo2-style tow model:
                    # tow_time = tow_length / tow_speed + fixed_offset.
                    estimated_tow_seconds = None
                    tow_length_m = None
                    tow_start_position = prev_track_position
                    if tow_start_position is None or tow_start_position < 0:
                        if (used_valid_snapshot_fallback
                                and prev_valid_track_position is not None
                                and prev_valid_track_position >= 0):
                            tow_start_position = prev_valid_track_position
                        else:
                            tow_start_position = frozen_position

                    estimated_tow_seconds, tow_length_m = self._estimate_tow_duration_to_pit(
                        tow_start_position,
                        current_track_position,
                        track_length_m
                    )

                    if estimated_tow_seconds is not None and has_session_time:
                        self.tow_end_time[car_idx] = now + estimated_tow_seconds
                    else:
                        # No estimate available: keep TOW until the car exits pit road/stall.
                        self.tow_end_time[car_idx] = 0.0
                    logger.info(
                        f"TOW_START non_player car_idx={car_idx} car_num={car_number} "
                        f"avg_speed_kph={avg_speed_kph:.1f} "
                        f"tow_length_m={tow_length_m} "
                        f"estimated_tow_seconds={estimated_tow_seconds} "
                        f"session_time={now:.1f} "
                        f"end_time={self.tow_end_time.get(car_idx, 0.0):.1f} "
                        f"end_time_set={self.tow_end_time.get(car_idx, 0.0) > 0} "
                        f"tow_start_position={tow_start_position} "
                        f"current_track_position={current_track_position:.4f} "
                        f"prev_track_position={prev_track_position} "
                        f"prev_valid_track_position={prev_valid_track_position} "
                        f"frozen_position={frozen_position} "
                        f"used_valid_snapshot_fallback={used_valid_snapshot_fallback} "
                        f"has_session_time={has_session_time}"
                    )

            if not self.tow_tracking.get(car_idx, False) and not current_invalid:
                self.tow_last_live_track_position[car_idx] = current_track_position

            # Update last-known values
            if not current_invalid:
                self.tow_last_surface[car_idx] = current_surface
                self.tow_last_on_pit_road[car_idx] = current_on_pit
                self.tow_last_track_position[car_idx] = current_track_position
                self.tow_last_update_time[car_idx] = now
            if not current_invalid:
                self.tow_last_valid_track_position[car_idx] = current_track_position
                self.tow_last_valid_time[car_idx] = now

        if has_session_time:
            self._sync_disconnected_tow_snapshots_by_timer(now)

    def _update_tow_sort_freeze_state(self, active_drivers: List[Dict]) -> None:
        """Track frozen sort position for cars while towing.

        This keeps raw telemetry position untouched and only affects race-order sorting.
        """
        for driver in active_drivers:
            car_idx = driver['car_idx']
            if self.race_state_tracker.is_driver_finished(car_idx):
                continue

            current_track_position = driver.get('total_track_position', 0.0)
            is_towing = self.tow_tracking.get(car_idx, False)

            if is_towing:
                if car_idx not in self.tow_frozen_track_position:
                    frozen_position = self.tow_last_live_track_position.get(
                        car_idx,
                        current_track_position
                    )
                    self.tow_frozen_track_position[car_idx] = frozen_position
            else:
                self.tow_last_live_track_position[car_idx] = current_track_position
                if car_idx in self.tow_frozen_track_position:
                    del self.tow_frozen_track_position[car_idx]

    def _get_tow_aware_sort_track_position(self, driver: Dict) -> float:
        """Return tow-frozen sort key when towing, otherwise live track position."""
        car_idx = driver.get('car_idx')
        if car_idx is None:
            return driver.get('total_track_position', -1)

        if self.tow_tracking.get(car_idx, False):
            return self.tow_frozen_track_position.get(
                car_idx,
                driver.get('total_track_position', -1)
            )

        return driver.get('total_track_position', -1)

    def _sync_disconnected_tow_snapshot_after_tow_end(
        self,
        car_idx: int,
        current_track_position: float,
        current_invalid: bool
    ) -> None:
        """Move a disconnected tow snapshot to its best-known pit position."""
        snapshot = self.race_state_tracker.get_snapshot(car_idx)
        if snapshot is None or not snapshot.is_disconnected:
            return

        if not snapshot.is_towing and snapshot.pit_lap != "TOW":
            return

        release_position = None
        last_track_position = self.tow_last_track_position.get(car_idx)
        if last_track_position is not None and last_track_position >= 0:
            release_position = last_track_position
        else:
            last_valid_position = self.tow_last_valid_track_position.get(car_idx)
            if last_valid_position is not None and last_valid_position >= 0:
                release_position = last_valid_position
            elif not current_invalid and current_track_position >= 0:
                release_position = current_track_position

        if release_position is not None:
            snapshot.current_lap = int(release_position)
            snapshot.lap_pct = release_position - snapshot.current_lap
            if snapshot.lap_pct < 0 or snapshot.lap_pct > 1:
                snapshot.lap_pct = 0.0

        snapshot.is_towing = False
        snapshot.preserve_disconnected_position = True
        snapshot.pit_lap = "PIT"

    def _log_disconnected_tow_timer_wait(
        self,
        car_idx: int,
        snapshot: DriverState,
        now: float,
        end_time: float,
        reason: str
    ) -> None:
        """Log a throttled INFO breadcrumb while a disconnected TOW row is waiting."""
        last_log_time = self.tow_last_wait_log_time.get(car_idx)
        if last_log_time is not None and (now - last_log_time) < 30.0:
            return

        self.tow_last_wait_log_time[car_idx] = now
        remaining = end_time - now if end_time > 0 else None
        logger.info(
            f"TOW_WAIT disconnected car_idx={car_idx} car_num={snapshot.car_number} "
            f"reason={reason} session_time={now:.1f} end_time={end_time:.1f} "
            f"remaining_seconds={remaining} pit_lap={snapshot.pit_lap} "
            f"is_towing={snapshot.is_towing} "
            f"preserve_position={snapshot.preserve_disconnected_position} "
            f"position={snapshot.position} track_pos={snapshot.total_track_position:.4f}"
        )

    def _sync_disconnected_tow_snapshots_by_timer(self, now: float) -> None:
        """Expire disconnected TOW snapshots even if live tow tracking was lost."""
        snapshots = getattr(self.race_state_tracker, 'driver_snapshots', {})
        for car_idx, snapshot in list(snapshots.items()):
            if not self.race_state_tracker.is_disconnected_tow_state(snapshot):
                continue

            end_time = self.tow_end_time.get(car_idx, 0.0)
            if end_time <= 0:
                self._log_disconnected_tow_timer_wait(
                    car_idx,
                    snapshot,
                    now,
                    end_time,
                    "missing_end_time"
                )
                continue
            if now < end_time:
                self._log_disconnected_tow_timer_wait(
                    car_idx,
                    snapshot,
                    now,
                    end_time,
                    "timer_pending"
                )
                continue

            logger.info(
                f"TOW_END car_idx={car_idx} car_num={snapshot.car_number} "
                f"reasons=disconnected_timer_expired session_time={now:.1f} "
                f"end_time={end_time:.1f}"
            )
            self.tow_tracking[car_idx] = False
            self.tow_end_time[car_idx] = 0.0
            self.tow_last_wait_log_time.pop(car_idx, None)
            if car_idx in self.tow_frozen_track_position:
                del self.tow_frozen_track_position[car_idx]
            self._sync_disconnected_tow_snapshot_after_tow_end(car_idx, 0.0, True)

    def get_tow_aware_overall_leader_idx(self) -> Optional[int]:
        """Find overall race leader using tow-frozen positions when towing.

        This prevents tow teleports (for example, pit stalls past start/finish)
        from becoming the temporary overall leader during finish tracking.
        """
        try:
            car_idx_lap = self.ir['CarIdxLap']
            car_idx_lap_dist_pct = self.ir['CarIdxLapDistPct']
        except (KeyError, TypeError):
            return None

        if not car_idx_lap or not car_idx_lap_dist_pct:
            return None

        overall_leader_idx = None
        max_track_position = -1.0
        max_len = min(len(car_idx_lap), len(car_idx_lap_dist_pct))
        driver_lookup = self._get_driver_lookup({})
        should_filter_driver_lookup = bool(driver_lookup)

        for car_idx in range(max_len):
            if should_filter_driver_lookup and car_idx not in driver_lookup:
                continue

            if car_idx_lap[car_idx] < 0:
                continue

            lap_pct = car_idx_lap_dist_pct[car_idx]
            if lap_pct < 0 or lap_pct > 1:
                lap_pct = 0

            total_track_position = car_idx_lap[car_idx] + lap_pct
            if self.tow_tracking.get(car_idx, False):
                total_track_position = self.tow_frozen_track_position.get(
                    car_idx,
                    self.tow_last_live_track_position.get(
                        car_idx,
                        total_track_position
                    )
                )

            if total_track_position > max_track_position:
                max_track_position = total_track_position
                overall_leader_idx = car_idx

        return overall_leader_idx

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
                'driver_info': driver['driver_info'],
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

    def _get_live_pit_display(self, car_idx: int, current_lap: int) -> str:
        """Return the authoritative live pit/tow display for a driver."""
        if self.tow_tracking.get(car_idx, False):
            return "TOW"

        last_pit_lap_num = self.pit_tracking.get(car_idx, 0)
        is_on_pit_road = self.pit_on_road.get(car_idx, False)
        exit_out_lap = self.pit_exit_out_lap.get(car_idx, -1)
        is_on_out_lap = (not is_on_pit_road) and exit_out_lap >= current_lap and exit_out_lap >= 0
        return GapCalculator.format_pit_lap(
            current_lap,
            last_pit_lap_num,
            is_on_pit_road=is_on_pit_road,
            is_out_lap=is_on_out_lap
        )

    def _has_completed_mandatory_pit_stop(self, car_idx: int) -> bool:
        """Return True once a valid pit stop has been completed after lap 1."""
        last_pit_lap_num = self.pit_tracking.get(car_idx, 0)
        return last_pit_lap_num > 1

    def _should_show_car_number_outline(self, car_idx: int, is_race: bool) -> bool:
        """Return True when the mandatory-stop indicator should be shown."""
        if not is_race:
            return True

        return not self._has_completed_mandatory_pit_stop(car_idx)

    def _get_snapshot_track_components(self, driver: Dict) -> Tuple[int, float]:
        """Return track-position components for snapshot storage.

        While towing, snapshots must preserve the tow-frozen sort position so a
        later disconnect restore does not reintroduce the pit-stall teleport.
        """
        snapshot_track_position = self._get_tow_aware_sort_track_position(driver)
        if snapshot_track_position < 0:
            current_lap = driver.get('current_lap', 0)
            lap_pct = driver.get('lap_pct', 0.0)
            return current_lap, lap_pct

        current_lap = int(snapshot_track_position)
        lap_pct = snapshot_track_position - current_lap
        if lap_pct < 0 or lap_pct > 1:
            lap_pct = 0.0

        return current_lap, lap_pct

    # ═══════════════════════════════════════════════════════════════════════════
    # RACE DATA BUILDING
    # ═══════════════════════════════════════════════════════════════════════════

    def _extract_manufacturer(self, driver_info: dict) -> tuple:
        """Extract manufacturer abbreviation and color from driver's CarPath.

        Args:
            driver_info: Driver info dict from iRacing SDK

        Returns:
            Tuple of (abbreviation, color_hex)
        """
        return extract_manufacturer(driver_info)

    def _build_race_data_entry(self, driver: Dict, division_positions: Dict[int, int], interval: str, gap_to_leader: str, division_interval: str, division_gap_to_leader: str, display_position: int, division_color: str, division_name: Optional[str], is_race: bool, delta: str = "--", last_lap_time: float = 0.0, best_lap_time: float = 0.0, starting_position: int = 0, irating: int = 0, lic_level: int = 0, lic_sublevel: int = 0) -> DriverState:
        """Build a single race data entry for display.

        Args:
            driver: Driver data dict
            division_positions: Dict mapping car_idx to division position
            interval: Overall interval string to car ahead for display
            gap_to_leader: Overall gap string to leader for display
            division_interval: Division interval string to car ahead in division for display
            division_gap_to_leader: Division gap string to division leader for display
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
        is_spectated = (car_idx == self.position_calculator.spectated_car_idx)
        is_disconnected = driver.get('disconnected', False)
        is_finished = self.race_state_tracker.is_driver_finished(car_idx)
        snapshot = self.race_state_tracker.get_snapshot(car_idx) if (is_disconnected and not is_finished) else None
        snapshot_is_towing = bool(snapshot.is_towing) if snapshot else False
        is_towing = (
            self.tow_tracking.get(car_idx, False) or snapshot_is_towing
        ) if not is_finished else False

        # Format last lap time for display
        last_lap_display = GapCalculator.format_lap_time(last_lap_time)

        recent_lap_flash = self._get_recent_lap_flash_text(car_idx)
        recent_lap_flash_state = self._get_recent_lap_flash_state(car_idx)

        # Format best lap time for display
        best_lap_display = GapCalculator.format_lap_time(best_lap_time)

        # Format positions gained for display (compare overall positions)
        positions_gained_display = GapCalculator.format_positions_gained(display_position, starting_position)

        # Format new columns using GapCalculator
        irating_display = GapCalculator.format_irating(irating)
        safety_rating_display = GapCalculator.format_safety_rating(lic_level, lic_sublevel)
        combined_rating_display = GapCalculator.format_combined_rating(irating, lic_level, lic_sublevel)

        # Calculate last pit lap and out lap indicator
        current_lap = driver.get('current_lap', 0)
        pit_lap_display = self._get_live_pit_display(car_idx, current_lap)
        show_car_number_outline = self._should_show_car_number_outline(car_idx, is_race)
        if is_disconnected and not is_finished:
            # Preserve last known pit/status text while disconnected (team swaps, reconnects).
            if snapshot and snapshot.pit_lap:
                pit_lap_display = snapshot.pit_lap

        # Extract manufacturer info
        mfr_abbrev, mfr_color = self._extract_manufacturer(driver_info)

        return DriverState(
            car_idx=car_idx,
            driver_info=driver_info,
            position=display_position,
            division_position=current_color_position,
            division_color=division_color,
            division_name=division_name,
            current_lap=current_lap,
            gap_to_leader=gap_to_leader if not (is_disconnected and not is_finished) else "(DC)",
            division_gap_to_leader=division_gap_to_leader if not (is_disconnected and not is_finished) else "(DC)",
            interval=interval if not (is_disconnected and not is_finished) else "(DC)",
            division_interval=division_interval if not (is_disconnected and not is_finished) else "(DC)",
            delta=delta,
            last_lap=last_lap_display,
            recent_lap_flash=recent_lap_flash,
            recent_lap_flash_state=recent_lap_flash_state,
            last_lap_time=last_lap_time,
            best_lap=best_lap_display,
            best_lap_time=best_lap_time,
            starting_position=starting_position,
            positions_gained=positions_gained_display,
            car_manufacturer=mfr_abbrev,
            car_manufacturer_color=mfr_color,
            irating=irating_display,
            safety_rating=safety_rating_display,
            combined_rating=combined_rating_display,
            lic_level=lic_level,
            pit_lap=pit_lap_display,
            is_towing=is_towing,
            show_car_number_outline=show_car_number_outline,
            is_player=is_player,
            is_spectated=is_spectated,
            is_disconnected=is_disconnected
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # SNAPSHOT MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    def _update_race_snapshots(self, active_drivers: List[Dict]) -> None:
        """Update snapshots for all actively racing cars.

        Creates or updates DriverState objects for each active driver.
        Preserves gap data from previous snapshots and stores the authoritative
        pit/tow display plus tow-aware sort position for disconnect restoration.

        Args:
            active_drivers: List of driver data dicts from telemetry (legacy format)
        """
        for driver_data in active_drivers:
            car_idx = driver_data['car_idx']
            if self.race_state_tracker.is_driver_finished(car_idx):
                continue  # Don't update finished drivers

            snapshot_current_lap, snapshot_lap_pct = self._get_snapshot_track_components(driver_data)
            snapshot_pit_lap = self._get_live_pit_display(
                car_idx,
                driver_data.get('current_lap', 0)
            )
            snapshot_is_towing = self.tow_tracking.get(car_idx, False)
            show_car_number_outline = self._should_show_car_number_outline(car_idx, True)

            # Get existing state or create new one
            driver_state = self.race_state_tracker.get_snapshot(car_idx)

            if driver_state:
                # Update existing state - preserve gap
                driver_state.current_lap = snapshot_current_lap
                driver_state.lap_pct = snapshot_lap_pct
                driver_state.position = driver_data.get('position', 0)
                driver_state.is_disconnected = False
                driver_state.pit_lap = snapshot_pit_lap
                driver_state.is_towing = snapshot_is_towing
                driver_state.preserve_disconnected_position = False
                driver_state.show_car_number_outline = show_car_number_outline
                # gap is preserved (not overwritten)
            else:
                # Create new state
                driver_info = driver_data['driver_info']
                division_name = self.division_manager.get_driver_division(driver_info)
                division_color = self.division_manager.get_division_color(division_name) if division_name else "#FFFFFF"

                mfr_abbrev, mfr_color = self._extract_manufacturer(driver_info)

                driver_state = DriverState(
                    car_idx=car_idx,
                    driver_info=driver_info,
                    division_name=division_name,
                    division_color=division_color,
                    current_lap=snapshot_current_lap,
                    lap_pct=snapshot_lap_pct,
                    position=driver_data.get('position', 0),
                    is_disconnected=False,
                    pit_lap=snapshot_pit_lap,
                    is_towing=snapshot_is_towing,
                    show_car_number_outline=show_car_number_outline,
                    car_manufacturer=mfr_abbrev,
                    car_manufacturer_color=mfr_color,
                )

                self.race_state_tracker.update_snapshot(car_idx, driver_state)

    def _remember_disconnected_tow_display_position(self, driver: Dict) -> None:
        """Record the worst displayed position for disconnected TOW rows."""
        if not driver.get('disconnected', False):
            return

        car_idx = driver.get('car_idx')
        if car_idx is None:
            return

        snapshot = self.race_state_tracker.get_snapshot(car_idx)
        if snapshot is None or not self.race_state_tracker.is_disconnected_tow_state(snapshot):
            return

        position = driver.get('position', 0)
        if position <= 0:
            return

        if snapshot.position > 0:
            snapshot.position = max(snapshot.position, position)
        else:
            snapshot.position = position

    def _restore_disconnected_tow_protected_position(self, driver: Dict) -> None:
        """Keep protected disconnected tow rows from improving during gap filling."""
        if not driver.get('disconnected', False):
            return

        car_idx = driver.get('car_idx')
        if car_idx is None:
            return

        snapshot = self.race_state_tracker.get_snapshot(car_idx)
        if (snapshot is not None
                and self.race_state_tracker.is_disconnected_tow_state(snapshot)
                and snapshot.position > 0):
            driver['position'] = snapshot.position

    def _get_session_state(self) -> int:
        """Return the current iRacing session state with a racing fallback."""
        try:
            return self.ir['SessionState']
        except (KeyError, TypeError):
            return 4

    @staticmethod
    def _get_final_display_position(driver: Dict) -> int:
        """Return the positive display position used for final standings."""
        final_position = driver.get('final_position')
        if isinstance(final_position, int) and final_position > 0:
            return final_position

        position = driver.get('position', 0)
        return position if isinstance(position, int) else 0

    @staticmethod
    def _get_driver_class_key(driver: Dict) -> Any:
        """Return the car class key used for class-scoped final standings."""
        driver_info = driver.get('driver_info', {})
        return driver_info.get('CarClassID')

    def _get_duplicate_final_positions_by_class(self, active_drivers: List[Dict]) -> Dict[Any, Set[int]]:
        """Return positive final/display positions used by more than one driver per class."""
        seen_by_class: Dict[Any, Set[int]] = {}
        duplicates_by_class: Dict[Any, Set[int]] = {}

        for driver in active_drivers:
            class_key = self._get_driver_class_key(driver)
            seen_positions = seen_by_class.setdefault(class_key, set())
            duplicate_positions = duplicates_by_class.setdefault(class_key, set())
            position = self._get_final_display_position(driver)
            if position <= 0:
                continue
            if position in seen_positions:
                duplicate_positions.add(position)
            else:
                seen_positions.add(position)

        return {
            class_key: duplicate_positions
            for class_key, duplicate_positions in duplicates_by_class.items()
            if duplicate_positions
        }

    def _all_final_positions_positive(self, active_drivers: List[Dict]) -> bool:
        """Return True when every active row has a positive final/display position."""
        if not active_drivers:
            return False

        for driver in active_drivers:
            if self._get_final_display_position(driver) <= 0:
                return False

        return True

    def _get_duplicate_final_positions(self, active_drivers: List[Dict]) -> Set[int]:
        """Return positive final/display positions used by more than one driver.

        Kept as a compatibility wrapper for tests and local diagnostics. Production
        cooldown reconciliation uses class-scoped duplicates.
        """
        seen_positions: Set[int] = set()
        duplicate_positions: Set[int] = set()

        for driver in active_drivers:
            position = self._get_final_display_position(driver)
            if position <= 0:
                continue
            if position in seen_positions:
                duplicate_positions.add(position)
            else:
                seen_positions.add(position)

        return duplicate_positions

    def _set_driver_final_position(self, driver: Dict, position: int) -> bool:
        """Set a driver's cooldown-final display position and snapshot."""
        if position <= 0:
            return False

        changed = False
        current_position = driver.get('position')
        if current_position != position:
            driver['position'] = position
            changed = True

        car_idx = driver.get('car_idx')
        is_finished = False
        if car_idx is not None:
            is_finished = self.race_state_tracker.is_driver_finished(car_idx)

        current_final_position = driver.get('final_position')
        if (is_finished or 'final_position' in driver) and current_final_position != position:
            driver['final_position'] = position
            changed = True

        if car_idx is not None:
            snapshot = self.race_state_tracker.get_snapshot(car_idx)
            if snapshot is not None and snapshot.position != position:
                snapshot.position = position
                changed = True

        return changed

    def _dedupe_cooldown_final_positions(self, active_drivers: List[Dict], session_data: Dict) -> None:
        """Repair duplicate final positions once the session reaches Cool Down."""
        if self.cooldown_final_position_dedup_complete:
            return

        session_state = self._get_session_state()
        try:
            if session_state < 6:
                return
        except TypeError:
            return

        max_passes = max(len(active_drivers), 1)
        for pass_number in range(max_passes):
            duplicates_by_class = self._get_duplicate_final_positions_by_class(active_drivers)
            if not duplicates_by_class:
                if self._all_final_positions_positive(active_drivers):
                    self.cooldown_final_position_dedup_complete = True
                    logger.info("COOLDOWN_DEDUP - Final displayed standings are unique; dedupe complete")
                else:
                    logger.info(
                        "COOLDOWN_DEDUP - No duplicate final positions, "
                        "but waiting for all active rows to have positive positions"
                    )
                return

            changed = False
            repaired_car_indices: List[int] = []
            for driver in active_drivers:
                class_key = self._get_driver_class_key(driver)
                current_position = self._get_final_display_position(driver)
                duplicate_positions = duplicates_by_class.get(class_key, set())
                if current_position not in duplicate_positions:
                    continue

                car_idx = driver.get('car_idx')
                if car_idx is None:
                    continue

                result_position = self.get_position_from_results(session_data, car_idx)
                if result_position <= 0:
                    continue

                if self._set_driver_final_position(driver, result_position):
                    changed = True
                    repaired_car_indices.append(car_idx)

            if repaired_car_indices:
                logger.info(
                    "COOLDOWN_DEDUP - Repaired duplicate final positions "
                    f"pass={pass_number + 1} cars={repaired_car_indices}"
                )

            if not changed:
                logger.warning(
                    "COOLDOWN_DEDUP - Duplicate final positions remain but "
                    "ResultsPositions did not change any affected rows"
                )
                return

        logger.warning("COOLDOWN_DEDUP - Duplicate final positions remain after max repair passes")

    # ═══════════════════════════════════════════════════════════════════════════
    # DELTA CALCULATION
    # ═══════════════════════════════════════════════════════════════════════════

    def _is_driving_mode(self) -> bool:
        """Check if in driving mode (vs spectating mode).

        Returns:
            True if player is driving (player_car_idx is valid), False if spectating
        """
        player_car_idx = self.position_calculator.player_car_idx
        if player_car_idx is None or player_car_idx < 0:
            return False

        live_array_length = self._get_car_idx_array_length(
            'CarIdxLap',
            'CarIdxClassPosition',
            'CarIdxLapDistPct',
            'CarIdxEstTime'
        )
        return live_array_length == 0 or player_car_idx < live_array_length

    def _calculate_delta(self, driver_lap_time: float, all_drivers_with_colors: List[Dict],
                        car_idx_last_lap: list, current_driver_color: str, car_idx: int) -> str:
        """Calculate delta lap time comparison.

        When driving: Compare to player's last lap time
        When spectating: Compare to overall leader's last lap time

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
            if player_car_idx is None or player_car_idx >= len(car_idx_last_lap):
                return "--"
            reference_lap_time = car_idx_last_lap[player_car_idx]
            reference_car_idx = player_car_idx
            # If player hasn't completed a lap yet, don't show delta for anyone
            if reference_lap_time <= 0 or reference_lap_time >= 999:
                return "--"
        else:
            # SPECTATING MODE: Compare to overall leader's last lap
            leaders = [d for d in all_drivers_with_colors if d.get('position', 0) > 0]
            if leaders:
                leaders.sort(key=lambda x: x.get('position', 0))
                overall_leader_idx = leaders[0]['car_idx']
                if overall_leader_idx >= len(car_idx_last_lap):
                    return "--"
                reference_lap_time = car_idx_last_lap[overall_leader_idx]
                reference_car_idx = overall_leader_idx

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
        current_info = driver.get('driver_info', {})
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
                'lap_pct': temp_driver['lap_pct'],
                'driver_info': temp_info
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
        if car_idx >= len(car_idx_est_time) or car_ahead_idx >= len(car_idx_est_time):
            current_est_time = 0
            ahead_est_time = 0
        else:
            current_est_time = car_idx_est_time[car_idx]
            ahead_est_time = car_idx_est_time[car_ahead_idx]

        # Get lap times with bounds checking
        normalize_lap_time_pct = 0
        ahead_lap_time = 0
        ahead_info = comparison_drivers[current_pos_index - 1].get('driver_info', {})
        ahead_lap_time = ahead_info.get('CarClassEstLapTime', 0)
        current_lap_time = current_info.get('CarClassEstLapTime', 0)
        if ahead_lap_time > 0 and current_lap_time > 0:
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
        current_info = driver.get('driver_info', {})
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
                'lap_pct': temp_driver['lap_pct'],
                'driver_info': temp_info
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
        if car_idx >= len(car_idx_est_time) or leader_idx >= len(car_idx_est_time):
            current_est_time = 0
            leader_est_time = 0
        else:
            current_est_time = car_idx_est_time[car_idx]
            leader_est_time = car_idx_est_time[leader_idx]

        normalize_lap_time_pct = 0
        leader_lap_time = 0
        leader_info = leader_entry.get('driver_info', {})
        leader_lap_time = leader_info.get('CarClassEstLapTime', 0)
        current_lap_time = current_info.get('CarClassEstLapTime', 0)
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
        driver_lookup = self._get_driver_lookup(session_data)
        current_info = driver_lookup.get(car_idx, {})
        current_car_class_id = current_info.get('CarClassID')

        pool = all_drivers_with_colors if not show_division else [d for d in all_drivers_with_colors if d['color'] == current_driver_color]

        comparison_drivers = []
        for d in pool:
            di = d.get('driver_info') or driver_lookup.get(d['car_idx'], {})
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
            driver_lookup = self._get_driver_lookup(session_data)
            current_driver_info = driver_lookup.get(car_idx, {})
            current_car_class_id = current_driver_info.get('CarClassID')

            division_results = []
            for result in sorted_results:
                result_car_idx = result.get('CarIdx')
                if result_car_idx is None:
                    continue

                driver_info = driver_lookup.get(result_car_idx, {})
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
            driver_lookup = self._get_driver_lookup(session_data)
            current_driver_info = driver_lookup.get(car_idx, {})
            current_car_class_id = current_driver_info.get('CarClassID')

            class_results = []
            for result in sorted_results:
                result_car_idx = result.get('CarIdx')
                if result_car_idx is None:
                    continue
                driver_info = driver_lookup.get(result_car_idx, {})
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
        driver_lookup = self._get_driver_lookup(session_data)
        current_info = driver_lookup.get(car_idx, {})
        current_car_class_id = current_info.get('CarClassID')

        if show_division:
            # Filter to same division and class
            comparison_drivers = []
            for d in all_drivers_with_colors:
                if d['color'] != current_driver_color:
                    continue
                di = d.get('driver_info') or driver_lookup.get(d['car_idx'], {})
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
                di = d.get('driver_info') or driver_lookup.get(d['car_idx'], {})
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
            driver_lookup = self._get_driver_lookup(session_data)
            current_driver_info = driver_lookup.get(car_idx, {})
            current_car_class_id = current_driver_info.get('CarClassID')

            # Build list of drivers in same division AND same car class, sorted by position
            division_results = []
            for result in sorted_results:
                result_car_idx = result.get('CarIdx')
                if result_car_idx is None:
                    continue

                # Get division color and car class for this driver
                driver_info = driver_lookup.get(result_car_idx, {})

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
            driver_lookup = self._get_driver_lookup(session_data)
            current_driver_info = driver_lookup.get(car_idx, {})
            current_car_class_id = current_driver_info.get('CarClassID')

            # Build list of cars in same class
            class_results = []
            for result in sorted_results:
                result_car_idx = result.get('CarIdx')
                if result_car_idx is None:
                    continue
                driver_info = driver_lookup.get(result_car_idx, {})
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

    def process_telemetry(self, get_driver_color_fn: Callable) -> Optional[List[DriverState]]:
        """Process telemetry data - orchestrates telemetry processing using helper methods.

        Args:
            get_driver_color_fn: Function to get driver's division color

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
                self._update_tow_tracking()

            # Identify player
            self.position_calculator.identify_player(drivers)

            # Update spectated car (changes every frame as spectator switches cameras)
            self.position_calculator.update_spectated_car()

            # Share player class ID with race state tracker for multi-class filtering
            self.race_state_tracker.set_player_class_id(self.position_calculator.player_car_class_id)

            if not self.ir:
                return None

            # Process positions (different logic for race vs practice/qualifying)
            if is_race:
                self.race_state_tracker.update_finish_status(self.get_tow_aware_overall_leader_idx)

                active_drivers = self.position_calculator.calculate_real_time_positions(drivers)

                if active_drivers:
                    # Maintain tow-freeze state for sorting without mutating live telemetry track position.
                    self._update_tow_sort_freeze_state(active_drivers)

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
                                    snapshot.position = self.race_state_tracker.constrain_disconnected_tow_position(
                                        snapshot,
                                        official_position
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
                            driver['final_position'] = self.get_position_from_results(session_data, driver['car_idx'])
                            driver['position'] = driver['final_position']
                    finished_drivers.sort(key=lambda x: x.get('final_position', 999))

                    # Sort racing drivers by current track position
                    # Use .get() for safety: drivers restored from snapshots after checkered (via _handle_disconnected_drivers)
                    # might not have total_track_position if snapshot was created before this field was added
                    racing_drivers.sort(key=self._get_tow_aware_sort_track_position, reverse=True)

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

                        self._remember_disconnected_tow_display_position(driver)
                        self._restore_disconnected_tow_protected_position(driver)

                    # Merge them back: finished drivers first (in order), then racing drivers
                    active_drivers = finished_drivers + racing_drivers
            else:
                active_drivers = self.position_calculator.get_official_positions(drivers)

            if not active_drivers:
                return None

            if is_race:
                self._dedupe_cooldown_final_positions(active_drivers, session_data)

            # Calculate division positions
            division_positions, all_drivers_with_colors = self._calculate_division_positions(
                active_drivers, get_driver_color_fn)

            # Read lap time telemetry data
            fallback_car_count = self._get_car_idx_array_length(
                'CarIdxLap',
                'CarIdxClassPosition',
                'CarIdxLapDistPct',
                'CarIdxEstTime',
                minimum=self._get_driver_lookup_capacity(drivers)
            )
            try:
                car_idx_last_lap = self.ir['CarIdxLastLapTime']
            except (KeyError, TypeError):
                car_idx_last_lap = [0.0] * fallback_car_count

            try:
                car_idx_best_lap = self.ir['CarIdxBestLapTime']
            except (KeyError, TypeError):
                car_idx_best_lap = [0.0] * fallback_car_count

            lap_telemetry_available = True
            try:
                car_idx_lap = self.ir['CarIdxLap']
            except (KeyError, TypeError):
                # Skip flash-event tracking if lap counters are unavailable, but preserve
                # any valid last/best lap telemetry for the rest of the row build.
                lap_telemetry_available = False
                car_idx_lap = None

            if lap_telemetry_available:
                self._update_recent_lap_flashes(
                    car_idx_lap,
                    car_idx_last_lap,
                    car_idx_best_lap,
                    session_data.get('session_type')
                )

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

                # Calculate overall interval (show_division=False)
                interval = self._calculate_interval(
                    driver, current_color_position, current_driver_color,
                    active_drivers, all_drivers_with_colors,
                    is_race, session_data,
                    get_driver_color_fn, show_division=False
                )

                # Calculate division interval (show_division=True)
                division_interval = self._calculate_interval(
                    driver, current_color_position, current_driver_color,
                    active_drivers, all_drivers_with_colors,
                    is_race, session_data,
                    get_driver_color_fn, show_division=True
                )

                # Calculate overall gap to leader (show_division=False)
                gap_to_leader = self._calculate_gap_to_leader(
                    driver, position, current_color_position, current_driver_color,
                    active_drivers, all_drivers_with_colors,
                    is_race, session_data,
                    get_driver_color_fn, show_division=False
                )

                # Calculate division gap to leader (show_division=True)
                division_gap_to_leader = self._calculate_gap_to_leader(
                    driver, position, current_color_position, current_driver_color,
                    active_drivers, all_drivers_with_colors,
                    is_race, session_data,
                    get_driver_color_fn, show_division=True
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
                    driver, division_positions, interval, gap_to_leader,
                    division_interval, division_gap_to_leader, position,
                    current_driver_color, current_driver_division, is_race,
                    delta, last_lap_time, best_lap_time, starting_position,
                    irating, lic_level, lic_sublevel
                )
                race_data.append(race_entry)

            race_data.sort(key=lambda x: x.position)

            return race_data

        except Exception as e:
            logger.error(f"Processing error: {e}", exc_info=True)
            return None

    def get_footer_data(self) -> Dict[str, Any]:
        """Get footer data: track temperature, incidents, incident limit, and SoF.

        Returns:
            Dictionary with keys:
                - track_temp: Track surface temperature in Celsius (float or None)
                - incidents: Player's current incident count (int or None)
                - incident_limit: Session incident limit (int or None, None = unlimited)
                - sof: Strength of Field (average iRating, int or None)
        """
        footer_data: Dict[str, Any] = {}

        # Track temperature (Celsius)
        try:
            footer_data['track_temp'] = self.ir['TrackTemp']
        except (KeyError, TypeError):
            footer_data['track_temp'] = None

        # Incidents (player only)
        try:
            footer_data['incidents'] = self.ir['PlayerCarMyIncidentCount']
        except (KeyError, TypeError):
            footer_data['incidents'] = None

        # Incident limit from WeekendOptions
        try:
            footer_data['incident_limit'] = self.ir['WeekendInfo']['WeekendOptions']['IncidentLimit']
        except (KeyError, TypeError):
            footer_data['incident_limit'] = None

        # Calculate SoF from DriverInfo (average of non-zero iRatings in player's class)
        try:
            driver_info = self.ir['DriverInfo']
            drivers = driver_info['Drivers']
            pace_car_indices = get_pace_car_indices(driver_info)

            # Get player's car class ID from position calculator (already cached)
            player_car_class_id = self.position_calculator.player_car_class_id
            
            # Only calculate if we have the player's class
            if player_car_class_id is not None:
                iratings = [
                    d.get('IRating', 0)
                    for d in drivers
                    if (
                        d.get('CarClassID') == player_car_class_id
                        and d.get('IRating', 0) > 0
                        and not is_pace_car(d, pace_car_indices)
                    )
                ]
                footer_data['sof'] = sum(iratings) // len(iratings) if iratings else None
            else:
                footer_data['sof'] = None
        except (KeyError, TypeError, ZeroDivisionError):
            footer_data['sof'] = None

        return footer_data

    def get_session_metadata(self) -> Dict[str, Any]:
        """Get session metadata for the broadcast header.

        Returns:
            Dictionary with keys:
                - track_display_name: Track display name from WeekendInfo (str or None)
        """
        metadata: Dict[str, Any] = {}

        try:
            metadata['track_display_name'] = self.ir['WeekendInfo']['TrackDisplayName']
        except (KeyError, TypeError):
            metadata['track_display_name'] = None

        return metadata
