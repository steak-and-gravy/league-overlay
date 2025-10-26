"""Unit tests for session status formatting methods in LeagueOverlay."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from league_overlay import LeagueOverlay


class TestSessionStatusFormatting:
    """Test suite for session status text formatting methods."""

    @pytest.fixture
    def mock_app(self):
        """Create a mock LeagueOverlay instance for testing."""
        with patch('league_overlay.irsdk.IRSDK'):
            app = Mock(spec=LeagueOverlay)
            app.ir = Mock()
            # Bind the actual methods to the mock
            app._get_session_state_name = LeagueOverlay._get_session_state_name.__get__(app)
            app._format_time_duration = LeagueOverlay._format_time_duration.__get__(app)
            app._format_lap_based_status = LeagueOverlay._format_lap_based_status.__get__(app)
            app._format_time_based_status = LeagueOverlay._format_time_based_status.__get__(app)
            app._should_show_connection_message = LeagueOverlay._should_show_connection_message.__get__(app)
            return app

    # ═══════════════════════════════════════════════════════════════════
    # SESSION STATE NAME TESTS
    # ═══════════════════════════════════════════════════════════════════

    def test_get_session_state_name_practice(self, mock_app):
        """Practice session should return 'Practice' regardless of state."""
        assert mock_app._get_session_state_name("Practice", 4) == "Practice"
        assert mock_app._get_session_state_name("Practice", 2) == "Practice"

    def test_get_session_state_name_qualifying(self, mock_app):
        """Qualifying session should return 'Qualifying' regardless of state."""
        assert mock_app._get_session_state_name("Qualifying", 4) == "Qualifying"

    def test_get_session_state_name_race_warmup(self, mock_app):
        """Race in warmup state should return 'Warmup'."""
        assert mock_app._get_session_state_name("Race", 2) == "Warmup"

    def test_get_session_state_name_race_pacing(self, mock_app):
        """Race in parade laps state should return 'Pacing'."""
        assert mock_app._get_session_state_name("Race", 3) == "Pacing"

    def test_get_session_state_name_race_racing(self, mock_app):
        """Race in racing state should return 'Race'."""
        assert mock_app._get_session_state_name("Race", 4) == "Race"

    def test_get_session_state_name_race_checkered(self, mock_app):
        """Race in checkered state should return 'Checkered'."""
        assert mock_app._get_session_state_name("Race", 5) == "Checkered"

    def test_get_session_state_name_race_cooldown(self, mock_app):
        """Race in cool down state should return 'Cool Down'."""
        assert mock_app._get_session_state_name("Race", 6) == "Cool Down"

    def test_get_session_state_name_race_unknown_state(self, mock_app):
        """Race in unknown state should default to 'Race'."""
        assert mock_app._get_session_state_name("Race", 0) == "Race"
        assert mock_app._get_session_state_name("Race", 1) == "Race"
        assert mock_app._get_session_state_name("Race", 99) == "Race"

    # ═══════════════════════════════════════════════════════════════════
    # TIME DURATION FORMATTING TESTS
    # ═══════════════════════════════════════════════════════════════════

    def test_format_time_duration_seconds_only(self, mock_app):
        """Format times under 1 minute correctly."""
        assert mock_app._format_time_duration(30) == "0:30"
        assert mock_app._format_time_duration(59) == "0:59"

    def test_format_time_duration_minutes(self, mock_app):
        """Format times with minutes correctly."""
        assert mock_app._format_time_duration(90) == "1:30"
        assert mock_app._format_time_duration(600) == "10:00"
        assert mock_app._format_time_duration(3599) == "59:59"

    def test_format_time_duration_hours(self, mock_app):
        """Format times with hours correctly."""
        assert mock_app._format_time_duration(3600) == "1:00:00"
        assert mock_app._format_time_duration(3661) == "1:01:01"
        assert mock_app._format_time_duration(7200) == "2:00:00"
        assert mock_app._format_time_duration(14400) == "4:00:00"

    def test_format_time_duration_zero(self, mock_app):
        """Format zero seconds correctly."""
        assert mock_app._format_time_duration(0) == "0:00"

    # ═══════════════════════════════════════════════════════════════════
    # LAP-BASED STATUS FORMATTING TESTS
    # ═══════════════════════════════════════════════════════════════════

    def test_format_lap_based_status_before_start(self, mock_app):
        """Before race starts, show total laps scheduled."""
        mock_app.ir.__getitem__ = Mock(return_value=0)
        result = mock_app._format_lap_based_status("Race", 3, "20")
        assert result == "Race - 20 Laps"

    def test_format_lap_based_status_during_pacing(self, mock_app):
        """During pacing, show total laps scheduled."""
        mock_app.ir.__getitem__ = Mock(return_value=-1)
        result = mock_app._format_lap_based_status("Pacing", 3, "20")
        assert result == "Pacing - 20 Laps"

    def test_format_lap_based_status_single_lap(self, mock_app):
        """Single lap should not be pluralized."""
        mock_app.ir.__getitem__ = Mock(return_value=0)
        result = mock_app._format_lap_based_status("Race", 3, "1")
        assert result == "Race - 1 Lap"

    def test_format_lap_based_status_during_race(self, mock_app):
        """During race, show current/total laps."""
        mock_app.ir.__getitem__ = Mock(return_value=5)
        result = mock_app._format_lap_based_status("Race", 4, "20")
        assert result == "Race - Lap 5/20"

    def test_format_lap_based_status_final_lap(self, mock_app):
        """Final lap should show correctly."""
        mock_app.ir.__getitem__ = Mock(return_value=20)
        result = mock_app._format_lap_based_status("Checkered", 5, "20")
        assert result == "Checkered - Lap 20/20"

    def test_format_lap_based_status_invalid_laps(self, mock_app):
        """Invalid lap count should return state name only."""
        mock_app.ir.__getitem__ = Mock(return_value=0)
        result = mock_app._format_lap_based_status("Race", 3, "invalid")
        assert result == "Race"

    def test_format_lap_based_status_ir_error(self, mock_app):
        """iRacing data errors should be handled gracefully."""
        mock_app.ir.__getitem__ = Mock(side_effect=KeyError("RaceLaps"))
        result = mock_app._format_lap_based_status("Race", 4, "20")
        # Should still work with RaceLaps defaulting to 0
        assert result == "Race - 20 Laps"

    # ═══════════════════════════════════════════════════════════════════
    # TIME-BASED STATUS FORMATTING TESTS
    # ═══════════════════════════════════════════════════════════════════

    def test_format_time_based_status_during_pacing(self, mock_app):
        """During pacing, show scheduled session time."""
        mock_app.ir.__getitem__ = Mock(return_value=1800)
        current_session = {'SessionTime': '1800 sec'}
        result = mock_app._format_time_based_status("Pacing", 3, current_session)
        assert result == "Pacing - 30:00"

    def test_format_time_based_status_during_pacing_with_hours(self, mock_app):
        """During pacing with hours, show H:MM:SS format."""
        mock_app.ir.__getitem__ = Mock(return_value=7200)
        current_session = {'SessionTime': '7200 sec'}
        result = mock_app._format_time_based_status("Warmup", 2, current_session)
        assert result == "Warmup - 2:00:00"

    def test_format_time_based_status_unlimited_session(self, mock_app):
        """Unlimited session with remaining time should show remaining time."""
        mock_app.ir.__getitem__ = Mock(return_value=1800)
        current_session = {'SessionTime': 'unlimited'}
        result = mock_app._format_time_based_status("Practice", 4, current_session)
        # Even in unlimited sessions, we show remaining time if available
        assert result == "Practice - 30:00"

    def test_format_time_based_status_during_active_session(self, mock_app):
        """During active session, show remaining time."""
        mock_app.ir.__getitem__ = Mock(return_value=600)
        current_session = {'SessionTime': '1800 sec'}
        result = mock_app._format_time_based_status("Practice", 4, current_session)
        assert result == "Practice - 10:00"

    def test_format_time_based_status_active_session_with_hours(self, mock_app):
        """Active session with hours remaining."""
        mock_app.ir.__getitem__ = Mock(return_value=5400)
        current_session = {'SessionTime': '7200 sec'}
        result = mock_app._format_time_based_status("Race", 4, current_session)
        assert result == "Race - 1:30:00"

    def test_format_time_based_status_time_expired(self, mock_app):
        """When time expires, show state name only."""
        mock_app.ir.__getitem__ = Mock(return_value=0)
        current_session = {'SessionTime': '1800 sec'}
        result = mock_app._format_time_based_status("Checkered", 5, current_session)
        assert result == "Checkered"

    def test_format_time_based_status_negative_time(self, mock_app):
        """Negative time remaining should show state name only."""
        mock_app.ir.__getitem__ = Mock(return_value=-10)
        current_session = {'SessionTime': '1800 sec'}
        result = mock_app._format_time_based_status("Checkered", 5, current_session)
        assert result == "Checkered"

    # ═══════════════════════════════════════════════════════════════════
    # CONNECTION MESSAGE TESTS
    # ═══════════════════════════════════════════════════════════════════

    def test_should_show_connection_message_true(self, mock_app):
        """Should show message within 5 seconds of connection."""
        import time
        mock_app.connection_time = time.time() - 2.0  # 2 seconds ago
        assert mock_app._should_show_connection_message() is True

    def test_should_show_connection_message_false_after_timeout(self, mock_app):
        """Should not show message after 5 seconds."""
        import time
        mock_app.connection_time = time.time() - 6.0  # 6 seconds ago
        assert mock_app._should_show_connection_message() is False

    def test_should_show_connection_message_false_no_connection_time(self, mock_app):
        """Should not show message if never connected."""
        mock_app.connection_time = None
        # Returns None (falsy) when connection_time is None
        assert not mock_app._should_show_connection_message()

    def test_should_show_connection_message_edge_case(self, mock_app):
        """Test exactly at 5 second boundary."""
        import time
        mock_app.connection_time = time.time() - 5.0
        # Should be False (not <  5.0)
        assert mock_app._should_show_connection_message() is False
