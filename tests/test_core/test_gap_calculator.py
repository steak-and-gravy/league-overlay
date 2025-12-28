"""Tests for core.gap_calculator module.

Tests cover:
- Time gap calculation (normal, negative, invalid)
- Lap gap calculation (normal, negative, zero)
- Gap display formatting (leader, lap gaps, time gaps, disconnected)
- Edge cases (None, zero, large values)
"""

import pytest
from core.gap_calculator import GapCalculator


class TestCalculateTimeGap:
    """Test cases for calculate_time_gap method."""

    def test_normal_positive_gap(self):
        """Test normal time gap calculation where ahead car is ahead."""
        gap = GapCalculator.calculate_time_gap(
            est_time_ahead=100.5,
            est_time_behind=98.2
        )
        assert gap == pytest.approx(2.3, rel=0.01)

    def test_negative_gap_returns_absolute_value(self):
        """Test gap when behind car is actually ahead (returns absolute value)."""
        gap = GapCalculator.calculate_time_gap(
            est_time_ahead=98.2,
            est_time_behind=100.5
        )
        # Should return absolute value
        assert gap == pytest.approx(2.3, rel=0.01)

    def test_zero_ahead_time_returns_none(self):
        """Test with zero est_time_ahead returns None."""
        gap = GapCalculator.calculate_time_gap(
            est_time_ahead=0,
            est_time_behind=100.5
        )
        assert gap is None

    def test_zero_behind_time_returns_none(self):
        """Test with zero est_time_behind returns None."""
        gap = GapCalculator.calculate_time_gap(
            est_time_ahead=100.5,
            est_time_behind=0
        )
        assert gap is None

    def test_both_zero_returns_none(self):
        """Test with both times zero returns None."""
        gap = GapCalculator.calculate_time_gap(
            est_time_ahead=0,
            est_time_behind=0
        )
        assert gap is None

    def test_negative_times_return_none(self):
        """Test with negative times returns None."""
        gap = GapCalculator.calculate_time_gap(
            est_time_ahead=-10.0,
            est_time_behind=100.5
        )
        assert gap is None

    def test_very_small_gap(self):
        """Test with very small time gap (milliseconds)."""
        gap = GapCalculator.calculate_time_gap(
            est_time_ahead=100.005,
            est_time_behind=100.002
        )
        assert gap == pytest.approx(0.003, rel=0.0001)

    def test_large_gap(self):
        """Test with large time gap (multiple laps)."""
        gap = GapCalculator.calculate_time_gap(
            est_time_ahead=500.0,
            est_time_behind=100.0
        )
        assert gap == pytest.approx(400.0, rel=0.01)


class TestCalculateLapGap:
    """Test cases for calculate_lap_gap method."""

    def test_normal_lap_gap(self):
        """Test normal lap gap calculation."""
        gap = GapCalculator.calculate_lap_gap(
            lap_ahead=10,
            lap_behind=8
        )
        assert gap == 2

    def test_one_lap_gap(self):
        """Test single lap gap."""
        gap = GapCalculator.calculate_lap_gap(
            lap_ahead=5,
            lap_behind=4
        )
        assert gap == 1

    def test_same_lap_returns_zero(self):
        """Test same lap returns zero gap."""
        gap = GapCalculator.calculate_lap_gap(
            lap_ahead=10,
            lap_behind=10
        )
        assert gap == 0

    def test_negative_gap_returns_zero(self):
        """Test negative lap gap (behind is ahead) returns zero."""
        gap = GapCalculator.calculate_lap_gap(
            lap_ahead=8,
            lap_behind=10
        )
        assert gap == 0

    def test_large_lap_gap(self):
        """Test large lap gap (getting lapped multiple times)."""
        gap = GapCalculator.calculate_lap_gap(
            lap_ahead=50,
            lap_behind=40
        )
        assert gap == 10

    def test_float_laps_truncated(self):
        """Test that float lap values are truncated to int."""
        gap = GapCalculator.calculate_lap_gap(
            lap_ahead=10.9,
            lap_behind=8.1
        )
        # 10.9 - 8.1 = 2.8, truncated to 2
        assert gap == 2

    def test_zero_laps(self):
        """Test with zero lap values."""
        gap = GapCalculator.calculate_lap_gap(
            lap_ahead=0,
            lap_behind=0
        )
        assert gap == 0


class TestFormatGapDisplay:
    """Test cases for format_gap_display method."""

    # Leader tests
    def test_leader_display(self):
        """Test leader shows 'Leader'."""
        display = GapCalculator.format_gap_display(is_leader=True)
        assert display == "Leader"

    def test_leader_overrides_gap(self):
        """Test leader status overrides time/lap gap."""
        display = GapCalculator.format_gap_display(
            time_gap=5.5,
            lap_gap=2,
            is_leader=True
        )
        assert display == "Leader"

    # Disconnected tests
    def test_disconnected_display(self):
        """Test disconnected shows '(DC)'."""
        display = GapCalculator.format_gap_display(is_disconnected=True)
        assert display == "(DC)"

    def test_disconnected_overrides_all(self):
        """Test disconnected overrides leader and gaps."""
        display = GapCalculator.format_gap_display(
            time_gap=5.5,
            lap_gap=2,
            is_leader=True,
            is_disconnected=True
        )
        assert display == "(DC)"

    # Lap gap tests
    def test_one_lap_gap_display(self):
        """Test single lap gap shows '1L'."""
        display = GapCalculator.format_gap_display(lap_gap=1)
        assert display == "1L"

    def test_multiple_lap_gap_display(self):
        """Test multiple lap gap shows 'NL'."""
        display = GapCalculator.format_gap_display(lap_gap=3)
        assert display == "3L"

    def test_lap_gap_overrides_time_gap(self):
        """Test lap gap takes priority over time gap."""
        display = GapCalculator.format_gap_display(
            time_gap=2.5,
            lap_gap=1
        )
        assert display == "1L"

    # Time gap tests - under 60 seconds
    def test_small_time_gap_single_decimal(self):
        """Test time gap under 60s shows single decimal."""
        display = GapCalculator.format_gap_display(time_gap=2.567)
        assert display == "2.6"

    def test_zero_time_gap(self):
        """Test zero time gap displays as '0.0'."""
        display = GapCalculator.format_gap_display(time_gap=0.0)
        assert display == "0.0"

    def test_very_small_time_gap(self):
        """Test very small time gap rounds correctly."""
        display = GapCalculator.format_gap_display(time_gap=0.04)
        assert display == "0.0"

    def test_time_gap_rounds_correctly(self):
        """Test time gap rounding (0.1s precision)."""
        display = GapCalculator.format_gap_display(time_gap=5.49)
        assert display == "5.5"

    def test_time_gap_at_59_seconds(self):
        """Test time gap just under 60s still uses simple format."""
        display = GapCalculator.format_gap_display(time_gap=59.9)
        assert display == "59.9"

    # Time gap tests - over 60 seconds (minutes)
    def test_time_gap_exactly_60_seconds(self):
        """Test exactly 60 seconds shows as minutes:seconds."""
        display = GapCalculator.format_gap_display(time_gap=60.0)
        assert display == "1:00.0"

    def test_time_gap_over_60_seconds(self):
        """Test time gap over 60s shows minutes:seconds format."""
        display = GapCalculator.format_gap_display(time_gap=75.3)
        assert display == "1:15.3"

    def test_time_gap_multiple_minutes(self):
        """Test multiple minutes gap formatting."""
        display = GapCalculator.format_gap_display(time_gap=185.7)
        assert display == "3:05.7"

    def test_time_gap_large_value(self):
        """Test large time gap (multiple laps behind)."""
        display = GapCalculator.format_gap_display(time_gap=400.5)
        assert display == "6:40.5"

    # No gap tests
    def test_no_gap_shows_dash(self):
        """Test no gap data shows '-'."""
        display = GapCalculator.format_gap_display()
        assert display == "-"

    def test_none_time_gap_shows_dash(self):
        """Test None time_gap with zero lap_gap shows '-'."""
        display = GapCalculator.format_gap_display(time_gap=None, lap_gap=0)
        assert display == "-"

    # Priority tests
    def test_priority_order_disconnected_first(self):
        """Test disconnected has highest priority."""
        # Disconnected > Leader > Lap gap > Time gap
        display = GapCalculator.format_gap_display(
            time_gap=5.0,
            lap_gap=1,
            is_leader=True,
            is_disconnected=True
        )
        assert display == "(DC)"

    def test_priority_order_leader_second(self):
        """Test leader has second priority."""
        # Leader > Lap gap > Time gap
        display = GapCalculator.format_gap_display(
            time_gap=5.0,
            lap_gap=1,
            is_leader=True,
            is_disconnected=False
        )
        assert display == "Leader"

    def test_priority_order_lap_gap_third(self):
        """Test lap gap has third priority."""
        # Lap gap > Time gap
        display = GapCalculator.format_gap_display(
            time_gap=5.0,
            lap_gap=2,
            is_leader=False,
            is_disconnected=False
        )
        assert display == "2L"


class TestFormatDeltaDisplay:
    """Test cases for format_delta_display method."""

    def test_positive_delta_driver_slower(self):
        """Test positive delta (driver slower than reference)."""
        delta = GapCalculator.format_delta_display(
            driver_lap_time=85.5,
            reference_lap_time=85.0
        )
        assert delta == "-0.5"

    def test_negative_delta_driver_faster(self):
        """Test negative delta (driver faster than reference)."""
        delta = GapCalculator.format_delta_display(
            driver_lap_time=84.7,
            reference_lap_time=85.0
        )
        assert delta == "+0.3"

    def test_large_positive_delta(self):
        """Test large positive delta."""
        delta = GapCalculator.format_delta_display(
            driver_lap_time=90.0,
            reference_lap_time=85.0
        )
        assert delta == "-5.0"

    def test_large_negative_delta(self):
        """Test large negative delta."""
        delta = GapCalculator.format_delta_display(
            driver_lap_time=80.0,
            reference_lap_time=85.0
        )
        assert delta == "+5.0"

    def test_very_small_positive_delta(self):
        """Test very small positive delta rounds correctly."""
        delta = GapCalculator.format_delta_display(
            driver_lap_time=85.04,
            reference_lap_time=85.0
        )
        assert delta == "-0.0"

    def test_very_small_negative_delta(self):
        """Test very small negative delta rounds correctly."""
        delta = GapCalculator.format_delta_display(
            driver_lap_time=84.96,
            reference_lap_time=85.0
        )
        assert delta == "+0.0"

    def test_invalid_driver_lap_time_zero(self):
        """Test invalid driver lap time (zero) returns '--'."""
        delta = GapCalculator.format_delta_display(
            driver_lap_time=0.0,
            reference_lap_time=85.0
        )
        assert delta == "--"

    def test_invalid_driver_lap_time_negative(self):
        """Test invalid driver lap time (negative) returns '--'."""
        delta = GapCalculator.format_delta_display(
            driver_lap_time=-1.0,
            reference_lap_time=85.0
        )
        assert delta == "--"

    def test_invalid_driver_lap_time_pit_lap(self):
        """Test pit lap (999+) returns '--'."""
        delta = GapCalculator.format_delta_display(
            driver_lap_time=999.9,
            reference_lap_time=85.0
        )
        assert delta == "--"

    def test_invalid_reference_lap_time_zero(self):
        """Test invalid reference lap time (zero) returns '--'."""
        delta = GapCalculator.format_delta_display(
            driver_lap_time=85.0,
            reference_lap_time=0.0
        )
        assert delta == "--"

    def test_invalid_reference_lap_time_negative(self):
        """Test invalid reference lap time (negative) returns '--'."""
        delta = GapCalculator.format_delta_display(
            driver_lap_time=85.0,
            reference_lap_time=-1.0
        )
        assert delta == "--"

    def test_invalid_reference_lap_time_pit_lap(self):
        """Test reference pit lap (999+) returns '--'."""
        delta = GapCalculator.format_delta_display(
            driver_lap_time=85.0,
            reference_lap_time=999.9
        )
        assert delta == "--"

    def test_both_invalid_returns_dash(self):
        """Test both lap times invalid returns '--'."""
        delta = GapCalculator.format_delta_display(
            driver_lap_time=0.0,
            reference_lap_time=0.0
        )
        assert delta == "--"

    def test_rounding_to_one_decimal(self):
        """Test delta rounds to 1 decimal place."""
        delta = GapCalculator.format_delta_display(
            driver_lap_time=85.567,
            reference_lap_time=85.0
        )
        assert delta == "-0.6"


class TestFormatLapTime:
    """Test cases for format_lap_time method."""

    def test_lap_time_under_60_seconds(self):
        """Test lap time under 60 seconds shows seconds with 2 decimals."""
        lap_time = GapCalculator.format_lap_time(45.67)
        assert lap_time == "45.67"

    def test_lap_time_exactly_60_seconds(self):
        """Test exactly 60 seconds shows as minutes:seconds."""
        lap_time = GapCalculator.format_lap_time(60.0)
        assert lap_time == "1:00.00"

    def test_lap_time_over_60_seconds(self):
        """Test lap time over 60 seconds shows minutes:seconds."""
        lap_time = GapCalculator.format_lap_time(84.56)
        assert lap_time == "1:24.56"

    def test_lap_time_multiple_minutes(self):
        """Test lap time with multiple minutes."""
        lap_time = GapCalculator.format_lap_time(145.78)
        assert lap_time == "2:25.78"

    def test_lap_time_very_short(self):
        """Test very short lap time (under 10 seconds)."""
        lap_time = GapCalculator.format_lap_time(8.34)
        assert lap_time == "8.34"

    def test_lap_time_just_under_60(self):
        """Test lap time just under 60 seconds."""
        lap_time = GapCalculator.format_lap_time(59.99)
        assert lap_time == "59.99"

    def test_lap_time_just_over_60(self):
        """Test lap time just over 60 seconds."""
        lap_time = GapCalculator.format_lap_time(60.01)
        assert lap_time == "1:00.01"

    def test_invalid_lap_time_zero(self):
        """Test zero lap time returns '--'."""
        lap_time = GapCalculator.format_lap_time(0.0)
        assert lap_time == "--"

    def test_invalid_lap_time_negative(self):
        """Test negative lap time returns '--'."""
        lap_time = GapCalculator.format_lap_time(-1.0)
        assert lap_time == "--"

    def test_invalid_lap_time_pit_lap(self):
        """Test pit lap (999+) returns '--'."""
        lap_time = GapCalculator.format_lap_time(999.9)
        assert lap_time == "--"

    def test_invalid_lap_time_threshold(self):
        """Test lap time at 999 boundary returns '--'."""
        lap_time = GapCalculator.format_lap_time(999.0)
        assert lap_time == "--"

    def test_valid_lap_time_just_below_threshold(self):
        """Test valid lap time just below 999 threshold."""
        lap_time = GapCalculator.format_lap_time(998.9)
        assert lap_time == "16:38.90"

    def test_lap_time_rounding_two_decimals(self):
        """Test lap time rounds to 2 decimal places."""
        lap_time = GapCalculator.format_lap_time(45.6789)
        assert lap_time == "45.68"

    def test_lap_time_padding_seconds(self):
        """Test seconds are padded with leading zero."""
        lap_time = GapCalculator.format_lap_time(65.34)
        assert lap_time == "1:05.34"

    def test_lap_time_padding_decimals(self):
        """Test decimals are padded correctly."""
        lap_time = GapCalculator.format_lap_time(85.1)
        assert lap_time == "1:25.10"


class TestFormatPositionsGained:
    """Test cases for format_positions_gained method."""

    def test_positions_gained_positive(self):
        """Test positions gained shows up arrow."""
        result = GapCalculator.format_positions_gained(
            current_position=5,
            starting_position=10
        )
        assert result == "↑5"

    def test_positions_gained_single(self):
        """Test single position gained."""
        result = GapCalculator.format_positions_gained(
            current_position=9,
            starting_position=10
        )
        assert result == "↑1"

    def test_positions_lost_negative(self):
        """Test positions lost shows down arrow."""
        result = GapCalculator.format_positions_gained(
            current_position=10,
            starting_position=5
        )
        assert result == "↓5"

    def test_positions_lost_single(self):
        """Test single position lost."""
        result = GapCalculator.format_positions_gained(
            current_position=10,
            starting_position=9
        )
        assert result == "↓1"

    def test_no_change_returns_dash(self):
        """Test no position change returns em dash."""
        result = GapCalculator.format_positions_gained(
            current_position=5,
            starting_position=5
        )
        assert result == "—"

    def test_invalid_current_position_zero(self):
        """Test zero current position returns em dash."""
        result = GapCalculator.format_positions_gained(
            current_position=0,
            starting_position=10
        )
        assert result == "—"

    def test_invalid_current_position_negative(self):
        """Test negative current position returns em dash."""
        result = GapCalculator.format_positions_gained(
            current_position=-1,
            starting_position=10
        )
        assert result == "—"

    def test_invalid_starting_position_zero(self):
        """Test zero starting position returns em dash."""
        result = GapCalculator.format_positions_gained(
            current_position=5,
            starting_position=0
        )
        assert result == "—"

    def test_invalid_starting_position_negative(self):
        """Test negative starting position returns em dash."""
        result = GapCalculator.format_positions_gained(
            current_position=5,
            starting_position=-1
        )
        assert result == "—"

    def test_both_positions_invalid(self):
        """Test both invalid positions returns em dash."""
        result = GapCalculator.format_positions_gained(
            current_position=0,
            starting_position=0
        )
        assert result == "—"

    def test_large_gains(self):
        """Test large position gains."""
        result = GapCalculator.format_positions_gained(
            current_position=1,
            starting_position=20
        )
        assert result == "↑19"

    def test_large_losses(self):
        """Test large position losses."""
        result = GapCalculator.format_positions_gained(
            current_position=20,
            starting_position=1
        )
        assert result == "↓19"
