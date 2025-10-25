"""
PositionCalculator - Calculates driver positions from iRacing telemetry

This class handles:
- Real-time position calculation based on track position (lap + lap distance %)
- Official position retrieval from iRacing's timing system
- Multi-class filtering to show only player's class
- Finding overall race leader across all classes
"""

from typing import Dict, List, Optional
import irsdk

from config.logging_config import get_logger

logger = get_logger(__name__)


class PositionCalculator:
    """Calculates real-time and official positions from iRacing telemetry."""

    def __init__(self, ir: irsdk.IRSDK):
        """Initialize the position calculator.

        Args:
            ir: iRacing SDK connection object
        """
        self.ir = ir
        self.player_car_idx: Optional[int] = None
        self.player_car_class_id: Optional[int] = None

    def reset(self) -> None:
        """Clear player identification."""
        self.player_car_idx = None
        self.player_car_class_id = None

    def identify_player(self, drivers: Dict[int, Dict]) -> None:
        """Identify player's car index and class.

        Updates self.player_car_idx and self.player_car_class_id.

        Args:
            drivers: Dict mapping CarIdx to driver info
        """
        if self.player_car_idx is None:
            try:
                self.player_car_idx = self.ir['PlayerCarIdx']
                logger.info(f"Player car index identified: {self.player_car_idx}")
            except (KeyError, TypeError):
                self.player_car_idx = None

        if self.player_car_idx is not None and self.player_car_class_id is None:
            try:
                driver = drivers.get(self.player_car_idx)
                if driver:
                    class_id = driver.get('CarClassID')
                    if class_id is not None:  # Only set if we actually got a valid class ID
                        self.player_car_class_id = class_id
                        logger.info(f"Player class ID identified: {self.player_car_class_id} for car {self.player_car_idx}")
                    else:
                        logger.warning(f"Found player car {self.player_car_idx} but CarClassID is None")
            except (KeyError, TypeError) as e:
                logger.warning(f"Error identifying player class: {e}")

    def calculate_real_time_positions(self, drivers: Dict[int, Dict]) -> List[Dict]:
        """Calculate real-time positions based on actual track position.

        Args:
            drivers: Dict mapping CarIdx to driver info

        Returns:
            List of driver dicts with position and track data
        """
        car_idx_lap = self.ir['CarIdxLap']
        car_idx_lap_dist_pct = self.ir['CarIdxLapDistPct']
        car_idx_class_position = self.ir['CarIdxClassPosition']

        if not car_idx_lap or not car_idx_lap_dist_pct or not car_idx_class_position:
            return []

        active_drivers = []

        for car_idx in range(len(car_idx_class_position)):
            # Position 0 means car is not active/participating
            if car_idx_class_position[car_idx] == 0:
                continue

            driver_info = drivers.get(car_idx)
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

    def get_official_positions(self, drivers: Dict[int, Dict]) -> List[Dict]:
        """Get positions from iRacing's official timing system (updates at start/finish line).

        Why this exists: Practice/qualifying don't need the complexity of real-time
        tracking. Official positions are sufficient and more stable.

        Args:
            drivers: Dict mapping CarIdx to driver info

        Returns:
            List of driver dicts with official positions
        """
        car_idx_class_position = self.ir['CarIdxClassPosition']

        if not car_idx_class_position:
            return []

        active_drivers = []

        for car_idx in range(len(car_idx_class_position)):
            # Position 0 means car is not active/participating
            if car_idx_class_position[car_idx] == 0:
                continue

            # O(1) lookup instead of O(n) loop
            driver_info = drivers.get(car_idx)

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

    def get_overall_race_leader_idx(self) -> Optional[int]:
        """Find the car index of the overall race leader (furthest ahead on track).

        This is the true P1 overall, regardless of class. Used for multi-class racing
        where the overall leader triggers when finish tracking can begin.

        Returns:
            car_idx of overall leader, or None if no leader found
        """
        car_idx_lap = self.ir['CarIdxLap']
        car_idx_lap_dist_pct = self.ir['CarIdxLapDistPct']

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