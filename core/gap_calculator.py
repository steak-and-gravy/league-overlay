"""Calculate and format time/distance gaps between cars."""

from typing import Optional


class GapCalculator:
    """Calculates and formats time/distance gaps between cars."""

    @staticmethod
    def calculate_time_gap(est_time_ahead: float, est_time_behind: float) -> Optional[float]:
        """Calculate time gap in seconds between two cars."""
        if est_time_ahead > 0 and est_time_behind > 0:
            gap = est_time_ahead - est_time_behind
            return gap if gap >= 0 else gap * -1
        return None

    @staticmethod
    def calculate_lap_gap(lap_ahead, lap_behind) -> int:
        """Calculate lap difference between two cars based on lap + possibly distance."""
        gap = lap_ahead - lap_behind
        return int(gap) if gap > 0 else 0

    @staticmethod
    def format_gap_display(time_gap: Optional[float] = None,
                          lap_gap: int = 0,
                          is_leader: bool = False,
                          is_disconnected: bool = False) -> str:
        """Format gap for display in UI."""
        if is_disconnected:
            return "(DC)"

        if is_leader:
            return "Leader"

        if lap_gap > 0:
            return f"{lap_gap}L"

        if time_gap is not None:
            if time_gap < 60:
                return f"{time_gap:.1f}"
            else:
                minutes = int(time_gap // 60)
                seconds = time_gap % 60
                return f"{minutes}:{seconds:04.1f}"

        return "-"

    @staticmethod
    def format_delta_display(driver_lap_time: float, reference_lap_time: float) -> str:
        """Format delta lap time comparison for display.

        Args:
            driver_lap_time: Driver's last lap time
            reference_lap_time: Reference lap time (player or division leader)

        Returns:
            Formatted delta string:
            - Negative ("-0.5") means driver was faster than reference (green)
            - Positive ("+0.3") means driver was slower than reference (red)
            - "--" if no valid data
        """
        # Check for invalid lap times (no data, pit lap, invalid lap)
        if driver_lap_time <= 0 or driver_lap_time >= 999:
            return "--"

        if reference_lap_time <= 0 or reference_lap_time >= 999:
            return "--"

        # Calculate delta
        delta =  reference_lap_time - driver_lap_time

        # Format with sign and 1 decimal place
        if delta >= 0:
            return f"+{delta:.1f}"
        else:
            return f"{delta:.1f}"  # Already has negative sign

    @staticmethod
    def format_lap_time(lap_time: float) -> str:
        """Format lap time for display.

        Args:
            lap_time: Lap time in seconds

        Returns:
            Formatted lap time string:
            - "1:24.56" for times >= 60 seconds
            - "58.34" for times < 60 seconds
            - "--" if no valid data
        """
        # Check for invalid lap times (no data, pit lap, invalid lap)
        if lap_time <= 0 or lap_time >= 999:
            return "--"

        # Format based on duration
        if lap_time < 60:
            return f"{lap_time:.2f}"
        else:
            minutes = int(lap_time // 60)
            seconds = lap_time % 60
            return f"{minutes}:{seconds:05.2f}"

    @staticmethod
    def format_positions_gained(current_position: int, starting_position: int) -> str:
        """Format positions gained/lost for display.

        Args:
            current_position: Driver's current position
            starting_position: Driver's starting grid position

        Returns:
            Formatted positions gained string:
            - "↑5" if gained 5 positions (positive change)
            - "↓3" if lost 3 positions (negative change)
            - "—" if no change or invalid data
        """
        # Check for invalid positions
        if current_position <= 0 or starting_position <= 0:
            return "—"

        # Calculate positions gained (positive = moved up, negative = moved down)
        gained = starting_position - current_position

        if gained > 0:
            return f"↑{gained}"
        elif gained < 0:
            return f"↓{abs(gained)}"
        else:
            return "—"
