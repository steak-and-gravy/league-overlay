"""Driver state dataclass for unified driver data management.

This module provides a single source of truth for driver data during a session,
eliminating the need for multiple parallel data structures (active_drivers,
driver_snapshots, all_drivers_with_colors, etc.).
"""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class DriverState:
    """Single source of truth for all driver data during a session.

    This dataclass consolidates what was previously spread across multiple
    data structures:
    - active_drivers (List[Dict]) - telemetry and position data
    - driver_snapshots (Dict) - race state tracking
    - all_drivers_with_colors (List[Dict]) - division color mapping
    - comparison_drivers (List[Dict]) - temporary gap calculation data

    Benefits:
    - Single state container instead of 6+ different lists/dicts
    - Update in place, no copying or rebuilding
    - Clear type hints for all fields
    - Easy querying: drivers[car_idx].is_finished
    """

    # ═══════════════════════════════════════════════════════════════════════════
    # IDENTITY
    # ═══════════════════════════════════════════════════════════════════════════

    car_idx: int
    """iRacing car index (0-63)"""

    driver_info: Dict = field(default_factory=dict)
    """Raw driver info from iRacing SDK.

    Contains: UserID, UserName, CarNumber, CarClassID, etc.
    Kept as dict because many systems (division_manager) expect this format.
    """

    # ═══════════════════════════════════════════════════════════════════════════
    # DIVISION
    # ═══════════════════════════════════════════════════════════════════════════

    division_name: Optional[str] = None
    """Division name: "Pro", "ProAm", "Am", "Rookie", or None for default"""

    division_color: str = "#FFFFFF"
    """Hex color code for division (e.g., "#FF0000" for red)"""

    # ═══════════════════════════════════════════════════════════════════════════
    # TELEMETRY (updated every frame)
    # ═══════════════════════════════════════════════════════════════════════════

    current_lap: int = 0
    """Current lap number (from CarIdxLap)"""

    lap_pct: float = 0.0
    """Progress through current lap, 0.0 to 1.0 (from CarIdxLapDistPct)"""

    # ═══════════════════════════════════════════════════════════════════════════
    # POSITIONS (calculated)
    # ═══════════════════════════════════════════════════════════════════════════

    position: int = 0
    """Driver's position (real-time during race, final after finish, best lap in practice/qual)"""

    division_position: int = 0
    """Position within driver's division (1 = division leader)"""

    starting_position: int = 0
    """Driver's starting grid position (captured at race start)"""

    # ═══════════════════════════════════════════════════════════════════════════
    # STATE FLAGS
    # ═══════════════════════════════════════════════════════════════════════════

    is_finished: bool = False
    """True if driver has completed the race (crossed line after checkered)"""

    is_disconnected: bool = False
    """True if driver has disconnected or retired from the race"""

    is_player: bool = False
    """True if this is the player's car"""

    # ═══════════════════════════════════════════════════════════════════════════
    # LAP TIMES
    # ═══════════════════════════════════════════════════════════════════════════

    last_lap_time: float = 0.0
    """Driver's most recent completed lap time in seconds (from CarIdxLastLapTime)"""

    best_lap_time: float = 0.0
    """Driver's best lap time this session in seconds (from CarIdxBestLapTime)"""

    # ═══════════════════════════════════════════════════════════════════════════
    # GAP AND INTERVAL DISPLAY
    # ═══════════════════════════════════════════════════════════════════════════

    gap_to_leader: str = ""
    """Formatted gap string to leader for display (e.g., "2.5s", "1L", "Leader")"""

    interval: str = ""
    """Formatted interval string to car ahead for display (e.g., "2.5s", "1L", "Leader")"""

    delta: str = ""
    """Formatted delta lap time comparison for display (e.g., "+0.5", "-0.3", "--")"""

    last_lap: str = ""
    """Formatted last lap time for display (e.g., "1:24.5", "--")"""

    best_lap: str = ""
    """Formatted best lap time for display (e.g., "1:24.5", "--")"""

    positions_gained: str = ""
    """Formatted positions gained/lost for display (e.g., "↑5", "↓3", "—")"""

    irating: str = ""
    """Formatted iRating for display (e.g., "6.0k", "1.5k", "0.8k")"""

    safety_rating: str = ""
    """Formatted safety rating for display (e.g., "A2.5", "B3.2")"""

    combined_rating: str = ""
    """Formatted combined rating for display (e.g., "A 2.5  3.0k")"""

    lic_level: int = 0
    """License level (1-24) for background color lookup"""

    pit_lap: str = ""
    """Formatted combined pit lap (shows OUT during out lap, L12 otherwise)"""

    is_towing: bool = False
    """True if driver appears to be in tow (teleported to pits)"""

    # ═══════════════════════════════════════════════════════════════════════════
    # COMPUTED PROPERTIES
    # ═══════════════════════════════════════════════════════════════════════════

    @property
    def total_track_position(self) -> float:
        """Total track position for sorting (lap + progress through current lap).

        Example: Lap 25, 50% through = 25.5
        Higher value = further ahead on track
        """
        return self.current_lap + self.lap_pct

    @property
    def car_number(self) -> str:
        """Car number from driver info."""
        return self.driver_info.get('CarNumber', '')

    @property
    def driver_name(self) -> str:
        """Driver name from driver info."""
        return self.driver_info.get('UserName', '')
    
    @property
    def team_name(self) -> str:
        """Team name from driver info."""
        return self.driver_info.get('TeamName', '')

    @property
    def car_class_id(self) -> Optional[int]:
        """Car class ID from driver info (for multi-class filtering)."""
        return self.driver_info.get('CarClassID')

    # ═══════════════════════════════════════════════════════════════════════════
    # UTILITY METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    def update_telemetry(self, current_lap: int, lap_pct: float, position: int) -> None:
        """Update telemetry data from iRacing SDK.

        Args:
            current_lap: Current lap number
            lap_pct: Progress through current lap (0.0 to 1.0)
            position: Current position
        """
        self.current_lap = current_lap
        self.lap_pct = lap_pct
        self.position = position
