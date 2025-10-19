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
