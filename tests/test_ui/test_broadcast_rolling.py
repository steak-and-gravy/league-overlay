"""Tests for broadcast rolling standings calculations."""

from league_overlay import LeagueOverlay


class TestBroadcastRollingWindow:
    """Validate locked+rolling window behavior for broadcast mode."""

    def test_sample_scenario_53_drivers_20_rows(self):
        """Top 15 locked, bottom 5 rolling through the remainder."""
        first_page = LeagueOverlay._calculate_broadcast_roll_window(
            total_drivers=53,
            visible_rows=20,
            roll_rows=5,
            page_index=0
        )
        assert first_page['locked_count'] == 15
        assert first_page['roll_start'] == 15
        assert first_page['roll_end'] == 20
        assert first_page['blank_rows'] == 0
        assert first_page['total_pages'] == 8

        last_page = LeagueOverlay._calculate_broadcast_roll_window(
            total_drivers=53,
            visible_rows=20,
            roll_rows=5,
            page_index=7
        )
        assert last_page['locked_count'] == 15
        assert last_page['roll_start'] == 50
        assert last_page['roll_end'] == 53
        assert last_page['blank_rows'] == 2
        assert last_page['total_pages'] == 8

    def test_wraps_page_index(self):
        """Page index wraps after the final rolling group."""
        wrapped = LeagueOverlay._calculate_broadcast_roll_window(
            total_drivers=53,
            visible_rows=20,
            roll_rows=5,
            page_index=8
        )
        assert wrapped['roll_start'] == 15
        assert wrapped['roll_end'] == 20

    def test_no_rolling_when_everything_fits(self):
        """If all rows fit, no rolling group is created."""
        window = LeagueOverlay._calculate_broadcast_roll_window(
            total_drivers=10,
            visible_rows=20,
            roll_rows=5,
            page_index=0
        )
        assert window['locked_count'] == 10
        assert window['roll_start'] == 10
        assert window['roll_end'] == 10
        assert window['blank_rows'] == 0
        assert window['total_pages'] == 1

    def test_rolls_all_rows_when_visible_rows_is_five_or_less(self):
        """Small viewports should page through all rows instead of locking top rows."""
        first_page = LeagueOverlay._calculate_broadcast_roll_window(
            total_drivers=12,
            visible_rows=5,
            roll_rows=5,
            page_index=0
        )
        assert first_page['locked_count'] == 0
        assert first_page['roll_start'] == 0
        assert first_page['roll_end'] == 5
        assert first_page['total_pages'] == 3

        last_page = LeagueOverlay._calculate_broadcast_roll_window(
            total_drivers=12,
            visible_rows=5,
            roll_rows=5,
            page_index=2
        )
        assert last_page['locked_count'] == 0
        assert last_page['roll_start'] == 10
        assert last_page['roll_end'] == 12
        assert last_page['blank_rows'] == 3
        assert last_page['total_pages'] == 3
