"""Calculate and format time/distance gaps between cars."""

from typing import Optional
import math


class GapCalculator:
    """Calculates and formats time/distance gaps and intervals between cars."""

    @staticmethod
    def calculate_interval_time(est_time_ahead: float, est_time_behind: float) -> Optional[float]:
        """Calculate time interval in seconds between current car and car ahead."""
        if est_time_ahead > 0 and est_time_behind > 0:
            gap = est_time_ahead - est_time_behind
            return gap if gap >= 0 else gap * -1
        return None

    @staticmethod
    def calculate_interval_lap(lap_ahead, lap_behind) -> int:
        """Calculate lap difference between current car and car ahead based on lap + possibly distance."""
        gap = lap_ahead - lap_behind
        return int(gap) if gap > 0 else 0

    @staticmethod
    def calculate_time_gap(est_time_ahead: float, est_time_behind: float) -> Optional[float]:
        """Calculate time gap in seconds between two cars. (Legacy, use calculate_interval_time)"""
        return GapCalculator.calculate_interval_time(est_time_ahead, est_time_behind)

    @staticmethod
    def calculate_lap_gap(lap_ahead, lap_behind) -> int:
        """Calculate lap difference between two cars. (Legacy, use calculate_interval_lap)"""
        return GapCalculator.calculate_interval_lap(lap_ahead, lap_behind)

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
            # Handle rounding: if seconds rounds to 60.00, increment minutes
            # This prevents displaying "1:60.00" for 119.999 seconds
            if seconds >= 59.995:  # Will round to 60.00 with .2f formatting
                minutes += 1
                seconds = 0.0
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

    @staticmethod
    def format_irating(irating: int) -> str:
        """Format iRating for display.

        Args:
            irating: Driver's iRating (e.g., 6010)

        Returns:
            Formatted iRating string:
            - "6.0k" for 6010 (rounded down to nearest hundred)
            - "1.5k" for 1523
            - "0.8k" for 847 (always use k format, even under 1000)
            - "—" if invalid (0 or negative)
        """
        if irating <= 0:
            return "—"

        # Round down to nearest hundred
        rounded = math.floor(irating / 100) * 100

        # Always format with k suffix
        return f"{rounded / 1000:.1f}k"

    @staticmethod
    def format_safety_rating(lic_level: int, lic_sublevel: int) -> str:
        """Format safety rating for display.

        Args:
            lic_level: License level (1-24 where R=1-4, D=5-8, C=9-12, B=13-16, A=17-20, P=21-24, WC=25+)
            lic_sublevel: License sublevel (0-399 representing x.xx, e.g., 247 = 2.47)

        Returns:
            Formatted safety rating string (e.g., "A2.5", "B3.2", "R1.0")
            - "—" if invalid (level <= 0)
        """
        if lic_level <= 0:
            return "—"

        # Map license level to letter
        if 1 <= lic_level <= 4:
            letter = "R"
        elif 5 <= lic_level <= 8:
            letter = "D"
        elif 9 <= lic_level <= 12:
            letter = "C"
        elif 13 <= lic_level <= 16:
            letter = "B"
        elif 17 <= lic_level <= 20:
            letter = "A"
        elif 21 <= lic_level <= 24:
            letter = "P"
        elif 25 <= lic_level:
            letter = "WC"
        else:
            return "—"  # Invalid level

        # Convert sublevel to decimal rounded down (247 → 2.47 → round to 2.4)
        # lic_sublevel is 0-399 representing x.xx
        decimal_value = lic_sublevel / 100.0

        # Round down to nearest 0.1
        rounded = math.floor(decimal_value * 10) / 10

        return f"{letter}{rounded:.1f}"

    @staticmethod
    def format_combined_rating(irating: int, lic_level: int, lic_sublevel: int) -> str:
        """Combine safety rating and iRating into single display string.

        Format: "A 2.5  3.0k" (license letter + sublevel + spaces + iRating with k suffix)

        Args:
            irating: Driver's iRating (e.g., 6010)
            lic_level: License level (1-24 where R=1-4, D=5-8, C=9-12, B=13-16, A=17-20, P=21-24, WC=25+)
            lic_sublevel: License sublevel (0-399 representing x.xx, e.g., 247 = 2.47)

        Returns:
            Formatted combined rating string (e.g., "A 2.5  3.0k")
            - "—" if invalid data
        """
        # Get safety rating component
        sr = GapCalculator.format_safety_rating(lic_level, lic_sublevel)
        if sr == "—":
            return "—"

        # Get iRating component (with k suffix)
        ir = GapCalculator.format_irating(irating)
        if ir == "—":
            return "—"

        # Combine with double space separator: "A 2.5  3.0k"
        return f"{sr}  {ir}"

    @staticmethod
    def format_pit_lap(
        current_lap: int,
        last_pit_lap: int,
        is_on_pit_road: bool = False,
        is_out_lap: bool = False
    ) -> str:
        """Format pit lap column (combines Last Pit and Out Lap).

        Shows "OUT" during out lap, otherwise shows last pit lap number.

        Args:
            current_lap: Driver's current lap number
            last_pit_lap: Lap number when driver last pitted (0 if haven't pitted)
            is_on_pit_road: True when driver is currently on pit road
            is_out_lap: True when driver is on out lap (post-exit, pre-complete)

        Returns:
            "OUT" if on out lap
            "L12" if pitted but not on out lap
            "—" if haven't pitted yet
        """
        # On pit road
        if is_on_pit_road:
            return "PIT"

        # Check if haven't pitted
        if last_pit_lap == 0:
            return "—"
        if last_pit_lap < 0:
            return "PIT"

        # Explicit out-lap flag is authoritative; equality check is legacy fallback.
        if is_out_lap or current_lap == last_pit_lap:
            return "OUT"

        # Show last pit lap number
        return f"L{last_pit_lap}"

    @staticmethod
    def get_license_background_color(lic_level: int) -> str:
        """Get background color for license class.

        Args:
            lic_level: License level (1-24)

        Returns:
            Hex color string for license class background
        """
        from config.constants import LICENSE_COLORS

        # Map license level to color
        if 1 <= lic_level <= 4:
            return LICENSE_COLORS.ROOKIE
        elif 5 <= lic_level <= 8:
            return LICENSE_COLORS.D_CLASS
        elif 9 <= lic_level <= 12:
            return LICENSE_COLORS.C_CLASS
        elif 13 <= lic_level <= 16:
            return LICENSE_COLORS.B_CLASS
        elif 17 <= lic_level <= 20:
            return LICENSE_COLORS.A_CLASS
        elif 21 <= lic_level <= 24:
            return LICENSE_COLORS.PRO
        elif lic_level <= 25:
            return LICENSE_COLORS.WC
        else:
            return '#000000'  # Black for invalid/unknown
