"""Tests for combined column formatting methods in GapCalculator.

This test module covers the new combined formatting methods:
- format_combined_rating() - Combines iRating + Safety Rating
- format_pit_lap() - Combines Last Pit + Out Lap
- get_license_background_color() - Maps license level to background color
"""

import pytest
from core.gap_calculator import GapCalculator


class TestFormatCombinedRating:
    """Test cases for format_combined_rating() method."""

    def test_valid_a_class_rating(self):
        """Test A-class driver with valid iRating."""
        # A-class (level 18), sublevel 247 (2.47 → 2.4), iRating 6010 (→ 6.0k)
        result = GapCalculator.format_combined_rating(6010, 18, 247)
        assert result == "A2.4  6.0k"

    def test_valid_b_class_rating(self):
        """Test B-class driver with valid iRating."""
        # B-class (level 14), sublevel 350 (3.50 → 3.5), iRating 4523 (→ 4.5k)
        result = GapCalculator.format_combined_rating(4523, 14, 350)
        assert result == "B3.5  4.5k"

    def test_valid_rookie_rating(self):
        """Test Rookie driver with valid iRating."""
        # Rookie (level 2), sublevel 100 (1.00 → 1.0), iRating 847 (→ 0.8k)
        result = GapCalculator.format_combined_rating(847, 2, 100)
        assert result == "R1.0  0.8k"

    def test_valid_pro_rating(self):
        """Test Pro driver with valid iRating."""
        # Pro (level 22), sublevel 450 (4.50 → 4.5), iRating 12456 (→ 12.4k)
        result = GapCalculator.format_combined_rating(12456, 22, 450)
        assert result == "P4.5  12.4k"

    def test_valid_d_class_rating(self):
        """Test D-class driver with valid iRating."""
        # D-class (level 6), sublevel 200 (2.00 → 2.0), iRating 2100 (→ 2.1k)
        result = GapCalculator.format_combined_rating(2100, 6, 200)
        assert result == "D2.0  2.1k"

    def test_valid_c_class_rating(self):
        """Test C-class driver with valid iRating."""
        # C-class (level 10), sublevel 315 (3.15 → 3.1), iRating 3678 (→ 3.6k)
        result = GapCalculator.format_combined_rating(3678, 10, 315)
        assert result == "C3.1  3.6k"

    def test_invalid_license_level_zero(self):
        """Test invalid license level (0) returns dash."""
        result = GapCalculator.format_combined_rating(5000, 0, 200)
        assert result == "—"

    def test_invalid_license_level_negative(self):
        """Test invalid license level (negative) returns dash."""
        result = GapCalculator.format_combined_rating(5000, -1, 200)
        assert result == "—"

    def test_wc_license_level(self):
        """Test World Championship license level formats correctly."""
        result = GapCalculator.format_combined_rating(5000, 25, 200)
        assert result == "WC2.0  5.0k"

    def test_invalid_irating_zero(self):
        """Test invalid iRating (0) returns dash."""
        result = GapCalculator.format_combined_rating(0, 18, 200)
        assert result == "—"

    def test_invalid_irating_negative(self):
        """Test invalid iRating (negative) returns dash."""
        result = GapCalculator.format_combined_rating(-100, 18, 200)
        assert result == "—"

    def test_both_invalid(self):
        """Test both invalid returns dash."""
        result = GapCalculator.format_combined_rating(0, 0, 0)
        assert result == "—"

    def test_sublevel_rounding_up(self):
        """Test sublevel rounds down correctly (247 → 2.4)."""
        result = GapCalculator.format_combined_rating(5000, 18, 247)
        assert "A2.4" in result

    def test_sublevel_rounding_down(self):
        """Test sublevel rounds down correctly (243 → 2.4)."""
        result = GapCalculator.format_combined_rating(5000, 18, 243)
        assert "A2.4" in result

    def test_irating_rounding_to_hundreds(self):
        """Test iRating rounds to nearest hundred."""
        # 6010 → 6000 → 6.0k
        result = GapCalculator.format_combined_rating(6010, 18, 200)
        assert "6.0k" in result

        # 1523 → 1500 → 1.5k
        result = GapCalculator.format_combined_rating(1523, 18, 200)
        assert "1.5k" in result

        # 847 → 800 → 0.8k
        result = GapCalculator.format_combined_rating(847, 18, 200)
        assert "0.8k" in result

    def test_double_space_separator(self):
        """Test that combined rating uses double space separator."""
        result = GapCalculator.format_combined_rating(5000, 18, 200)
        assert "  " in result  # Double space between SR and iRating
        assert result == "A2.0  5.0k"


class TestFormatPitLap:
    """Test cases for format_pit_lap() method."""

    def test_not_pitted_yet(self):
        """Test driver who hasn't pitted returns dash."""
        result = GapCalculator.format_pit_lap(5, 0)
        assert result == "—"

    def test_on_out_lap(self):
        """Test driver on out lap (first lap after pitting) shows OUT."""
        # Pitted on lap 10, now on lap 10 (out lap)
        result = GapCalculator.format_pit_lap(10, 10)
        assert result == "OUT"

    def test_after_out_lap_completed(self):
        """Test driver after out lap shows last pit lap number."""
        # Pitted on lap 10, now on lap 12 (out lap completed)
        result = GapCalculator.format_pit_lap(12, 10)
        assert result == "L10"

    def test_many_laps_after_pit(self):
        """Test driver many laps after pit shows last pit lap number."""
        # Pitted on lap 5, now on lap 20
        result = GapCalculator.format_pit_lap(20, 5)
        assert result == "L5"

    def test_first_lap_pit(self):
        """Test driver who pitted on lap 1."""
        # Pitted on lap 1, now on lap 1 (out lap)
        result = GapCalculator.format_pit_lap(1, 1)
        assert result == "OUT"

        # After out lap
        result = GapCalculator.format_pit_lap(3, 1)
        assert result == "L1"

    def test_late_race_pit(self):
        """Test pit stop late in race."""
        # Pitted on lap 45, now on lap 45 (out lap)
        result = GapCalculator.format_pit_lap(45, 45)
        assert result == "OUT"

        # After out lap
        result = GapCalculator.format_pit_lap(47, 45)
        assert result == "L45"

    def test_negative_last_pit_lap(self):
        """Test invalid negative last pit lap returns PIT."""
        result = GapCalculator.format_pit_lap(5, -1)
        assert result == "PIT"

    def test_on_pit_road_flag_takes_priority(self):
        """Test explicit on-pit-road flag forces PIT display."""
        result = GapCalculator.format_pit_lap(25, 12, is_on_pit_road=True)
        assert result == "PIT"

    def test_explicit_out_lap_flag(self):
        """Test explicit out-lap flag shows OUT without lap equality."""
        result = GapCalculator.format_pit_lap(12, 10, is_out_lap=True)
        assert result == "OUT"

    def test_current_lap_before_pit(self):
        """Test edge case where current lap is before pit lap (should not happen)."""
        # This shouldn't happen in practice, but test defensive behavior
        result = GapCalculator.format_pit_lap(9, 10)
        assert result == "L10"  # Should still show pit lap


class TestGetLicenseBackgroundColor:
    """Test cases for get_license_background_color() method."""

    def test_rookie_level_1(self):
        """Test Rookie level 1 returns dark red."""
        result = GapCalculator.get_license_background_color(1)
        assert result == '#8B0000'

    def test_rookie_level_4(self):
        """Test Rookie level 4 (max) returns dark red."""
        result = GapCalculator.get_license_background_color(4)
        assert result == '#8B0000'

    def test_d_class_level_5(self):
        """Test D-class level 5 (min) returns dark orange."""
        result = GapCalculator.get_license_background_color(5)
        assert result == '#A55B00'

    def test_d_class_level_8(self):
        """Test D-class level 8 (max) returns dark orange."""
        result = GapCalculator.get_license_background_color(8)
        assert result == '#A55B00'

    def test_c_class_level_9(self):
        """Test C-class level 9 (min) returns goldenrod."""
        result = GapCalculator.get_license_background_color(9)
        assert result == '#DAA520'

    def test_c_class_level_12(self):
        """Test C-class level 12 (max) returns goldenrod."""
        result = GapCalculator.get_license_background_color(12)
        assert result == '#DAA520'

    def test_b_class_level_13(self):
        """Test B-class level 13 (min) returns dark green."""
        result = GapCalculator.get_license_background_color(13)
        assert result == '#006400'

    def test_b_class_level_16(self):
        """Test B-class level 16 (max) returns dark green."""
        result = GapCalculator.get_license_background_color(16)
        assert result == '#006400'

    def test_a_class_level_17(self):
        """Test A-class level 17 (min) returns dark blue."""
        result = GapCalculator.get_license_background_color(17)
        assert result == '#00008B'

    def test_a_class_level_20(self):
        """Test A-class level 20 (max) returns dark blue."""
        result = GapCalculator.get_license_background_color(20)
        assert result == '#00008B'

    def test_pro_level_21(self):
        """Test Pro level 21 (min) returns indigo."""
        result = GapCalculator.get_license_background_color(21)
        assert result == '#4B0082'

    def test_pro_level_24(self):
        """Test Pro level 24 (max) returns indigo."""
        result = GapCalculator.get_license_background_color(24)
        assert result == '#4B0082'

    def test_invalid_level_zero(self):
        """Test invalid level 0 returns black."""
        result = GapCalculator.get_license_background_color(0)
        assert result == '#000000'

    def test_invalid_level_negative(self):
        """Test invalid negative level returns black."""
        result = GapCalculator.get_license_background_color(-1)
        assert result == '#000000'

    def test_wc_level_25(self):
        """Test WC level 25 returns WC background color."""
        result = GapCalculator.get_license_background_color(25)
        assert result == '#800080'

    def test_wc_level_above_25(self):
        """Test WC levels above 25 still return WC background color."""
        result = GapCalculator.get_license_background_color(26)
        assert result == '#800080'

    def test_all_valid_levels(self):
        """Test that all 24 valid levels return a valid hex color."""
        for level in range(1, 25):
            color = GapCalculator.get_license_background_color(level)
            # Should be valid hex color format
            assert color.startswith('#')
            assert len(color) == 7
            # Should be one of the defined colors (not black)
            assert color != '#000000'
