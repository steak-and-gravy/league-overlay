"""Race finish state tracking and snapshot management."""

from typing import Dict, Set, Optional, Any, Callable


class RaceStateTracker:
    """Tracks race finish state machine and completed laps after checkered flag."""

    def __init__(self):
        """Initialize race state tracker."""
        self.reset()

    def reset(self) -> None:
        """Reset all finish tracking state (called on session change)."""
        self.leader_finished: bool = False
        self.finished_drivers: Set[int] = set()
        self.checkered_flag_shown: bool = False
        self.finish_times: Dict[int, float] = {}
        self.finish_laps: Dict[int, int] = {}  # Store lap count when each driver finished
        self.driver_snapshots: Dict[int, Dict[str, Any]] = {}

    def is_racing(self) -> bool:
        """Check if race is still in progress (checkered not shown yet)."""
        return not self.checkered_flag_shown

    def set_checkered_flag(self) -> None:
        """Mark checkered flag as waved."""
        self.checkered_flag_shown = True

    def is_checkered(self) -> bool:
        """Check if checkered flag has shown."""
        return self.checkered_flag_shown

    def mark_driver_finished(self, car_idx: int, finish_time: float, official_position: int, finish_lap: int = 0) -> None:
        """Mark a driver as having completed their finish lap.

        Args:
            car_idx: Car index of the finishing driver
            finish_time: SessionTime when driver crossed finish line
            official_position: Official finishing position
            finish_lap: Lap number when driver finished
        """
        if car_idx not in self.finished_drivers:
            self.finished_drivers.add(car_idx)
            self.finish_times[car_idx] = finish_time
            self.finish_laps[car_idx] = finish_lap

            # Store final position in snapshot
            if car_idx in self.driver_snapshots:
                self.driver_snapshots[car_idx]['official_position'] = official_position

    def recalculate_all_finish_gaps(self, current_session, get_driver_color_func: Callable) -> None:
        """Recalculate division positions and finish gaps for all finished drivers.

        This should be called after marking a new driver as finished, to ensure all
        division-based gaps are updated based on the latest finishing order.

        Args:
            current_session: Current session data with ResultsPositions
            get_driver_color_func: Function to get division color for a driver
        """
        # Step 1: Update official positions from ResultsPositions for all finished drivers
        try:
            if 'ResultsPositions' in current_session:
                for driver in current_session['ResultsPositions']:
                    car_idx = driver.get('CarIdx')
                    if car_idx is not None and car_idx in self.finished_drivers:
                        if 'ClassPosition' in driver:
                            official_position = driver['ClassPosition'] + 1  # ClassPosition is 0-based
                            if car_idx in self.driver_snapshots:
                                self.driver_snapshots[car_idx]['official_position'] = official_position
        except (KeyError, TypeError, IndexError):
            pass

        # Step 2: Build list of all finished drivers with their divisions
        finished_with_divisions = []
        for car_idx in self.finished_drivers:
            snapshot = self.driver_snapshots.get(car_idx)
            if snapshot and 'driver_info' in snapshot:
                driver_color = get_driver_color_func(snapshot['driver_info'])
                official_position = snapshot.get('official_position', 999)
                finished_with_divisions.append({
                    'car_idx': car_idx,
                    'color': driver_color,
                    'official_position': official_position
                })

        # Step 3: Calculate division positions for finished drivers
        division_positions = {}
        for color in set(d['color'] for d in finished_with_divisions):
            same_division = [d for d in finished_with_divisions if d['color'] == color]
            same_division.sort(key=lambda x: x['official_position'])
            for i, driver in enumerate(same_division):
                division_positions[driver['car_idx']] = i + 1

        # Step 4: Calculate finish gaps within divisions
        for car_idx in self.finished_drivers:
            snapshot = self.driver_snapshots.get(car_idx)
            if not snapshot or 'driver_info' not in snapshot:
                continue

            driver_color = get_driver_color_func(snapshot['driver_info'])
            division_position = division_positions.get(car_idx, 1)

            # Clear existing finish gaps
            if 'finish_gap' in snapshot:
                del snapshot['finish_gap']
            if 'finish_lap_gap' in snapshot:
                del snapshot['finish_lap_gap']

            # If not division leader, find car ahead in same division
            if division_position > 1:
                car_ahead_idx = None
                for d in finished_with_divisions:
                    if d['color'] == driver_color and division_positions.get(d['car_idx']) == division_position - 1:
                        car_ahead_idx = d['car_idx']
                        break

                if car_ahead_idx is not None:
                    # Calculate time gap based on SessionTime
                    finish_gap_seconds = self.get_finish_gap(car_ahead_idx, car_idx)
                    if finish_gap_seconds is not None:
                        snapshot['finish_gap'] = finish_gap_seconds

                    # Calculate lap gap
                    car_ahead_lap = self.finish_laps.get(car_ahead_idx, 0)
                    current_car_lap = self.finish_laps.get(car_idx, 0)
                    lap_gap = car_ahead_lap - current_car_lap
                    if lap_gap > 0:
                        snapshot['finish_lap_gap'] = lap_gap

    def is_driver_finished(self, car_idx: int) -> bool:
        """Check if a driver has finished their race."""
        return car_idx in self.finished_drivers

    def get_finish_time(self, car_idx: int) -> Optional[float]:
        """Get the finish time for a finished driver."""
        return self.finish_times.get(car_idx)

    def get_finish_gap(self, car_ahead_idx: int, car_behind_idx: int) -> Optional[float]:
        """Get the final gap between two drivers."""
        time_ahead = self.finish_times.get(car_ahead_idx)
        time_behind = self.finish_times.get(car_behind_idx)
        if time_ahead is not None and time_behind is not None:
            return time_behind - time_ahead
        return None

    def update_snapshot(self, car_idx: int, snapshot_data: Dict[str, Any]) -> None:
        """Update or create driver snapshot with current state."""
        self.driver_snapshots[car_idx] = snapshot_data

    def get_snapshot(self, car_idx: int) -> Optional[Dict[str, Any]]:
        """Get stored snapshot for a driver."""
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
