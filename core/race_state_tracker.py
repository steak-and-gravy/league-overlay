"""Race finish state tracking and snapshot management."""

from typing import Dict, Set, Optional, Callable, List
import irsdk

from config.constants import TELEMETRY_CONFIG
from config.logging_config import get_logger
from core.driver_state import DriverState

logger = get_logger(__name__)


class RaceStateTracker:
    """Tracks race finish state machine and completed laps after checkered flag."""

    def __init__(self, ir: irsdk.IRSDK):
        """Initialize race state tracker.

        Args:
            ir: iRacing SDK connection object
        """
        self.ir = ir
        self.player_car_class_id: Optional[int] = None
        self.player_class_car_indices: Optional[Set[int]] = None
        self.reset()

    def reset(self) -> None:
        """Reset all finish tracking state (called on session change)."""
        self.leader_finished: bool = False
        self.finished_drivers: Set[int] = set()
        self.checkered_flag_shown: bool = False
        self.driver_snapshots: Dict[int, DriverState] = {}  # Changed from Dict to DriverState
        self.player_class_car_indices: Optional[Set[int]] = None
        self.starting_positions: Dict[int, int] = {}  # Maps car_idx to starting grid position
        self.starting_positions_loaded: bool = False  # Track if we've attempted to load starting positions

    def is_racing(self) -> bool:
        """Check if race is still in progress (checkered not shown yet)."""
        return not self.checkered_flag_shown

    def set_checkered_flag(self) -> None:
        """Mark checkered flag as waved."""
        if not self.checkered_flag_shown:
            logger.debug("Checkered flag shown - finish tracking active")
        self.checkered_flag_shown = True

    def is_checkered(self) -> bool:
        """Check if checkered flag has shown."""
        return self.checkered_flag_shown

    def mark_driver_finished(self, car_idx: int, official_position: int) -> None:
        """Mark a driver as having completed their finish lap.

        Args:
            car_idx: Car index of the finishing driver
            official_position: Official finishing position
        """
        if car_idx not in self.finished_drivers:
            logger.debug(f"MARK_FINISHED - Car {car_idx} marked as finished: position={official_position}")
            self.finished_drivers.add(car_idx)

            # Store final position in snapshot and mark as finished
            if car_idx in self.driver_snapshots:
                driver_state = self.driver_snapshots[car_idx]
                driver_state.position = official_position
                driver_state.is_finished = True

    def is_driver_finished(self, car_idx: int) -> bool:
        """Check if a driver has finished their race."""
        return car_idx in self.finished_drivers

    def update_snapshot(self, car_idx: int, driver_state: DriverState) -> None:
        """Update or create driver snapshot with current state.

        Args:
            car_idx: Car index
            driver_state: DriverState object to store
        """
        self.driver_snapshots[car_idx] = driver_state

    def get_snapshot(self, car_idx: int) -> Optional[DriverState]:
        """Get stored snapshot for a driver.

        Args:
            car_idx: Car index

        Returns:
            DriverState object or None if not found
        """
        return self.driver_snapshots.get(car_idx)

    def has_leader_finished(self) -> bool:
        """Check if the race leader has finished their race."""
        return self.leader_finished

    def set_leader_finished_flag(self) -> None:
        """Mark that the overall race leader has finished.

        This enables tracking of class drivers finishing, but does NOT
        add the leader to finished_drivers (they may be in a different class).
        Use mark_driver_finished() to actually mark class drivers as finished.
        """
        self.leader_finished = True

    def set_player_class_id(self, player_car_class_id: Optional[int]) -> None:
        """Set the player's car class ID for multi-class filtering.

        Args:
            player_car_class_id: The player's car class ID
        """
        self.player_car_class_id = player_car_class_id

    def _cache_player_class_cars(self) -> None:
        """Cache which cars are in player's class to avoid repeated lookups during finish tracking."""
        if self.player_car_class_id is None:
            self.player_class_car_indices = None
            return

        self.player_class_car_indices = set()
        try:
            drivers = self.ir['DriverInfo']['Drivers']
            for d in drivers:
                if d.get('CarClassID') == self.player_car_class_id:
                    car_idx = d.get('CarIdx')
                    if car_idx is not None:
                        self.player_class_car_indices.add(car_idx)
            logger.debug(f"FINISH_TRACKING - Cached {len(self.player_class_car_indices)} cars in player's class")
        except (KeyError, TypeError):
            logger.warning("FINISH_TRACKING - Failed to cache player class cars")
            self.player_class_car_indices = None

    def load_starting_positions_from_qualify(self) -> None:
        """Load starting grid positions from QualifyResultsInfo.

        This method retrieves the official starting positions from qualifying results
        stored in the SessionInfo YAML. This is more reliable than capturing positions
        at race start and works even if the overlay connects mid-race.

        Only loads positions during race sessions. Does nothing for practice/qualifying.
        """
        # Mark that we've attempted to load (prevents infinite retries)
        self.starting_positions_loaded = True

        # Clear any existing starting positions
        self.starting_positions.clear()

        try:
            # First try QualifyResultsInfo (most reliable source)
            try:
                qualify_info = self.ir['QualifyResultsInfo']
                if qualify_info and 'Results' in qualify_info and qualify_info['Results']:
                    for result in qualify_info['Results']:
                        car_idx = result.get('CarIdx')
                        # Use ClassPosition for multi-class support (0-based, so add 1)
                        class_position = result.get('ClassPosition')
                        if car_idx is not None and class_position is not None:
                            self.starting_positions[car_idx] = class_position + 1

                    if self.starting_positions:
                        logger.debug(f"STARTING_POSITIONS - Loaded {len(self.starting_positions)} starting positions from QualifyResultsInfo")
                        return
            except (KeyError, TypeError):
                pass  # QualifyResultsInfo not available, try SessionInfo fallback

            # Fallback: Look for qualifying session in SessionInfo
            session_info = self.ir['SessionInfo']
            if session_info and 'Sessions' in session_info:
                sessions = session_info['Sessions']

                # Find qualifying session (search backwards for most recent qualifying)
                qualify_session = None
                for session in reversed(sessions):
                    if session.get('SessionType', '').lower() == 'qualify':
                        qualify_session = session
                        break

                # If no qualifying session, use practice as fallback
                if not qualify_session:
                    for session in reversed(sessions):
                        if session.get('SessionType', '').lower() == 'practice':
                            qualify_session = session
                            break

                if qualify_session and 'ResultsPositions' in qualify_session:
                    results = qualify_session['ResultsPositions']
                    if results:
                        for result in results:
                            car_idx = result.get('CarIdx')
                            # Use ClassPosition for multi-class support (0-based, so add 1)
                            class_position = result.get('ClassPosition')
                            if car_idx is not None and class_position is not None:
                                self.starting_positions[car_idx] = class_position + 1

                        if self.starting_positions:
                            session_type = qualify_session.get('SessionType', 'unknown')
                            logger.debug(f"STARTING_POSITIONS - Loaded {len(self.starting_positions)} starting positions from {session_type} session")
                            return

            # If we get here and have no starting positions, log a warning
            if not self.starting_positions:
                logger.warning("STARTING_POSITIONS - Could not load starting positions from QualifyResultsInfo or session results")

        except (KeyError, TypeError, IndexError) as e:
            logger.warning(f"STARTING_POSITIONS - Error loading starting positions: {e}")

    def get_starting_position(self, car_idx: int) -> int:
        """Get starting grid position for a driver.

        Starting positions should be loaded at session change via load_starting_positions_from_qualify().
        This method just returns from the cache.

        Args:
            car_idx: Car index

        Returns:
            Starting position (0 if not found or not available)
        """
        return self.starting_positions.get(car_idx, 0)

    # ═══════════════════════════════════════════════════════════════════════════
    # FINISH STATUS TRACKING
    # ═══════════════════════════════════════════════════════════════════════════

    def update_finish_status(self, get_overall_leader_fn: Callable) -> None:
        """Track which drivers have finished the race after the checkered flag.

        IMPORTANT: iRacing shows the checkered flag BEFORE the leader crosses the
        line. We need to track when each driver completes their current lap after
        the checkered and after the leader finishes to know their final position.

        This method:
        1. Identifies what lap the leader is on when checkered waves
        2. Waits for the leader to complete that lap (true finish)
        3. Tracks each subsequent driver as they finish their current lap
        4. Stores their official position at the moment they finish

        Args:
            get_overall_leader_fn: Function to get overall race leader car_idx
        """
        # SessionState < 5 means race hasn't reached checkered flag yet
        if self.ir['SessionState'] < 5:
            return

        car_idx_lap = self.ir['CarIdxLap']
        car_idx_class_position = self.ir['CarIdxClassPosition']

        # PHASE 1: Mark checkered flag as shown (enables finish tracking)
        if self.is_racing():
            # First time after checkered - flip to finish tracking mode
            logger.debug("FINISH_TRACKING - Checkered flag detected, entering finish tracking mode")
            self.set_checkered_flag()
            # Cache player's class car indices once to avoid repeated lookups
            self._cache_player_class_cars()

        # PHASE 2: Wait for the OVERALL race leader (P1 overall, any class) to finish
        # This allows multi-class racing where slower class drivers can finish before their class leader
        if not self.is_racing() and not self.has_leader_finished():
            # Find the overall race leader (furthest ahead on track, regardless of class)
            overall_leader_idx = get_overall_leader_fn()
            logger.debug(f"FINISH_TRACKING - Waiting for overall leader (car {overall_leader_idx}) to finish")

            # Check if the overall leader has finished using their snapshot
            if overall_leader_idx is not None:
                driver_state = self.get_snapshot(overall_leader_idx)

                # If no snapshot exists (overall leader might be in different class), create minimal snapshot
                if not driver_state:
                    current_lap = car_idx_lap[overall_leader_idx] if overall_leader_idx < len(car_idx_lap) else 0
                    logger.debug(f"FINISH_TRACKING - Overall leader car {overall_leader_idx} has no snapshot, creating one with lap={current_lap}")
                    # Create minimal DriverState for tracking
                    driver_state = DriverState(
                        car_idx=overall_leader_idx,
                        current_lap=current_lap
                    )
                    self.update_snapshot(overall_leader_idx, driver_state)

                if driver_state:
                    prev_lap = driver_state.current_lap
                    current_lap = car_idx_lap[overall_leader_idx] if overall_leader_idx < len(car_idx_lap) else 0

                    # Did the overall leader just cross the finish line?
                    if current_lap > prev_lap:
                        # Overall leader finished - now we can start tracking our class drivers
                        logger.debug(f"FINISH_TRACKING - Overall leader car {overall_leader_idx} finished! Lap {prev_lap} -> {current_lap}. Now tracking class finishes.")
                        self.set_leader_finished_flag()
                    else:
                        # Update their lap for next cycle
                        driver_state.current_lap = current_lap
                        # No need to call update_snapshot - we're modifying the object in place

        # PHASE 3: Once leader is done, track all other drivers as they complete their laps
        if self.has_leader_finished():
            logger.debug(f"FINISH_TRACKING - Leader has finished, tracking class driver finishes. Currently {len(self.finished_drivers)} drivers finished.")
            for car_idx in range(len(car_idx_lap)):
                if self.is_driver_finished(car_idx):
                    continue

                # Use cached class car indices for quick filtering
                if self.player_class_car_indices is not None and car_idx not in self.player_class_car_indices:
                    continue

                driver_state = self.get_snapshot(car_idx)
                if driver_state is None:
                    continue

                prev_lap = driver_state.current_lap
                current_lap = car_idx_lap[car_idx]

                # When lap counter increments, driver has crossed finish line and completed race
                if current_lap > prev_lap:
                    # Capture the official position at the moment they finish
                    official_position = car_idx_class_position[car_idx] if car_idx < len(car_idx_class_position) else 0
                    self.mark_driver_finished(car_idx, official_position)

    def handle_disconnected_drivers(self, active_drivers: List[Dict], session_data: Dict,
                                   get_position_from_results_fn: Callable) -> None:
        """Handle drivers who have disconnected or retired from the race.

        Finds drivers in snapshots who are no longer in active_drivers and adds
        them back with disconnected status. Modifies active_drivers in place.

        Args:
            active_drivers: List of active driver data (modified in place)
            session_data: Session data dict from telemetry processor
            get_position_from_results_fn: Function to get position from session results
        """
        active_car_indices = {d['car_idx'] for d in active_drivers}

        # Get race lap count for retirement detection
        try:
            race_laps = self.ir['RaceLaps']
        except (KeyError, TypeError):
            race_laps = 0

        for car_idx in range(TELEMETRY_CONFIG.MAX_CARS):
            driver_state = self.get_snapshot(car_idx)
            if driver_state and car_idx not in active_car_indices:
                # This driver disconnected or retired
                if self.ir['SessionState'] < 5:
                    # Still racing - mark as DC, position unknown
                    driver_state.position = -1
                    # Mark as disconnected
                    driver_state.is_disconnected = True
                else:
                    # After checkered - get their final position from results, do this every cycle as things can change
                    driver_state.position = get_position_from_results_fn(session_data, car_idx)

                    # After leader has finished, mark ALL disconnected drivers as finished
                    # This ensures they use ResultsPositions and don't participate in gap-filling
                    if self.has_leader_finished():
                        driver_state.is_finished = True
                        self.finished_drivers.add(car_idx)
                        logger.debug(f"DISCONNECT - Car {car_idx} marked as finished after leader finished, position={driver_state.position}")

                # Skip if snapshot is missing critical fields (minimal snapshot for different class)
                if not driver_state.driver_info:
                    continue

                # Multi-class support: only restore drivers in player's class
                if self.player_car_class_id is not None:
                    driver_class_id = driver_state.driver_info.get('CarClassID')
                    if driver_class_id != self.player_car_class_id:
                        continue

                # Create dict for PositionCalculator's expected format
                disconnected_driver = {
                    'car_idx': driver_state.car_idx,
                    'driver_info': driver_state.driver_info,
                    'position': driver_state.position,
                    'current_lap': driver_state.current_lap,
                    'lap_pct': driver_state.lap_pct,
                    'total_track_position': driver_state.total_track_position,
                    'disconnected': driver_state.is_disconnected,
                }

                # Only show disconnected drivers if they have a valid position or race is ongoing
                if self.ir['SessionState'] < 5 or driver_state.position >= 0:
                    active_drivers.append(disconnected_driver)
