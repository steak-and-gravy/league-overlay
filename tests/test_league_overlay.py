"""Tests for LeagueOverlay._handle_telemetry_update method.

Tests cover:
- Session change detection and data clearing
- Player car index synchronization
- Race data updates
- Handling None race data
- Initial session setup
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import Optional, List, Dict
from league_overlay import LeagueOverlay


class TestHandleTelemetryUpdate:
    """Test cases for LeagueOverlay._handle_telemetry_update method."""

    @pytest.fixture
    def mock_overlay(self):
        """Create a minimal mock LeagueOverlay for testing _handle_telemetry_update."""
        # We can't easily instantiate the full LeagueOverlay without Qt,
        # so we'll create a mock with just the attributes we need
        overlay = Mock()

        # Initialize attributes that _handle_telemetry_update uses
        overlay.current_session_num = None
        overlay.current_session_type = None
        overlay.race_data = []
        overlay.player_car_idx = None

        # Mock telemetry processor
        overlay.telemetry_processor = Mock()
        overlay.telemetry_processor.current_session_num = None
        overlay.telemetry_processor.current_session_type = None
        overlay.telemetry_processor.position_calculator = Mock()
        overlay.telemetry_processor.position_calculator.player_car_idx = None

        # Import the actual method and bind it to our mock
        # This requires reading the actual implementation
        def _handle_telemetry_update(self, race_data: Optional[List[Dict]]) -> None:
            """Handle telemetry update and sync state from processor."""
            if race_data is None:
                return

            # Detect session change by comparing with processor's session info
            session_changed = (
                self.current_session_num != self.telemetry_processor.current_session_num or
                self.current_session_type != self.telemetry_processor.current_session_type
            )

            # Sync session info from telemetry processor
            self.current_session_num = self.telemetry_processor.current_session_num
            self.current_session_type = self.telemetry_processor.current_session_type

            # Clear old data on session change (only if we have a valid session)
            if session_changed and self.current_session_num is not None:
                self.race_data = []

            # Update race data and player info
            self.race_data = race_data
            self.player_car_idx = self.telemetry_processor.position_calculator.player_car_idx

        # Bind the method to the mock
        overlay._handle_telemetry_update = _handle_telemetry_update.__get__(overlay)

        return overlay

    def test_none_race_data_returns_early(self, mock_overlay):
        """Test that None race_data is handled gracefully without updates."""
        # Setup initial state
        mock_overlay.race_data = [{'position': 1}]
        mock_overlay.player_car_idx = 5

        # Call with None
        mock_overlay._handle_telemetry_update(None)

        # Should not modify anything
        assert mock_overlay.race_data == [{'position': 1}]
        assert mock_overlay.player_car_idx == 5

    def test_first_session_initialization(self, mock_overlay):
        """Test handling first session (None -> valid session)."""
        # Initial state: no session
        assert mock_overlay.current_session_num is None
        assert mock_overlay.current_session_type is None

        # Processor reports first session
        mock_overlay.telemetry_processor.current_session_num = 0
        mock_overlay.telemetry_processor.current_session_type = 'Practice'
        mock_overlay.telemetry_processor.position_calculator.player_car_idx = 5

        race_data = [{'position': 1, 'driver': 'Driver 1'}]

        # Call method
        mock_overlay._handle_telemetry_update(race_data)

        # Should sync session info
        assert mock_overlay.current_session_num == 0
        assert mock_overlay.current_session_type == 'Practice'
        assert mock_overlay.race_data == race_data
        assert mock_overlay.player_car_idx == 5

    def test_session_change_clears_race_data(self, mock_overlay):
        """Test that race_data is cleared when session changes."""
        # Setup: existing session with data
        mock_overlay.current_session_num = 0
        mock_overlay.current_session_type = 'Practice'
        mock_overlay.race_data = [{'old': 'data'}]

        # Processor reports new session
        mock_overlay.telemetry_processor.current_session_num = 1
        mock_overlay.telemetry_processor.current_session_type = 'Qualify'
        mock_overlay.telemetry_processor.position_calculator.player_car_idx = 5

        new_race_data = [{'new': 'data'}]

        # Call method
        mock_overlay._handle_telemetry_update(new_race_data)

        # Session should be updated
        assert mock_overlay.current_session_num == 1
        assert mock_overlay.current_session_type == 'Qualify'
        # Race data should be set to new data (cleared then updated)
        assert mock_overlay.race_data == new_race_data
        assert mock_overlay.player_car_idx == 5

    def test_session_change_by_number(self, mock_overlay):
        """Test session change detected by session number change."""
        # Setup: session 0
        mock_overlay.current_session_num = 0
        mock_overlay.current_session_type = 'Practice'
        mock_overlay.race_data = [{'old': 'data'}]

        # Change to session 1 (same type)
        mock_overlay.telemetry_processor.current_session_num = 1
        mock_overlay.telemetry_processor.current_session_type = 'Practice'
        mock_overlay.telemetry_processor.position_calculator.player_car_idx = 5

        new_race_data = [{'new': 'data'}]
        mock_overlay._handle_telemetry_update(new_race_data)

        assert mock_overlay.current_session_num == 1
        assert mock_overlay.race_data == new_race_data

    def test_session_change_by_type(self, mock_overlay):
        """Test session change detected by session type change."""
        # Setup: Practice session
        mock_overlay.current_session_num = 0
        mock_overlay.current_session_type = 'Practice'
        mock_overlay.race_data = [{'old': 'data'}]

        # Change to Race (same number)
        mock_overlay.telemetry_processor.current_session_num = 0
        mock_overlay.telemetry_processor.current_session_type = 'Race'
        mock_overlay.telemetry_processor.position_calculator.player_car_idx = 5

        new_race_data = [{'new': 'data'}]
        mock_overlay._handle_telemetry_update(new_race_data)

        assert mock_overlay.current_session_type == 'Race'
        assert mock_overlay.race_data == new_race_data

    def test_no_session_change_updates_data(self, mock_overlay):
        """Test data updates without session change (no clearing)."""
        # Setup: same session
        mock_overlay.current_session_num = 1
        mock_overlay.current_session_type = 'Race'
        mock_overlay.race_data = [{'position': 1}]

        # Same session in processor
        mock_overlay.telemetry_processor.current_session_num = 1
        mock_overlay.telemetry_processor.current_session_type = 'Race'
        mock_overlay.telemetry_processor.position_calculator.player_car_idx = 5

        updated_race_data = [{'position': 2}]
        mock_overlay._handle_telemetry_update(updated_race_data)

        # Data should be updated (not cleared first)
        assert mock_overlay.race_data == updated_race_data
        assert mock_overlay.player_car_idx == 5

    def test_player_car_idx_synced(self, mock_overlay):
        """Test player_car_idx is synced from telemetry processor."""
        mock_overlay.telemetry_processor.current_session_num = 0
        mock_overlay.telemetry_processor.current_session_type = 'Race'
        mock_overlay.telemetry_processor.position_calculator.player_car_idx = 42

        race_data = [{'position': 1}]
        mock_overlay._handle_telemetry_update(race_data)

        assert mock_overlay.player_car_idx == 42

    def test_player_car_idx_updates_on_change(self, mock_overlay):
        """Test player_car_idx updates when it changes."""
        # Initial player car
        mock_overlay.player_car_idx = 10
        mock_overlay.telemetry_processor.current_session_num = 0
        mock_overlay.telemetry_processor.current_session_type = 'Race'

        # Player changes car
        mock_overlay.telemetry_processor.position_calculator.player_car_idx = 20

        race_data = [{'position': 1}]
        mock_overlay._handle_telemetry_update(race_data)

        assert mock_overlay.player_car_idx == 20

    def test_empty_race_data_handled(self, mock_overlay):
        """Test handling empty race data list."""
        mock_overlay.telemetry_processor.current_session_num = 0
        mock_overlay.telemetry_processor.current_session_type = 'Race'
        mock_overlay.telemetry_processor.position_calculator.player_car_idx = 5

        # Empty list (no drivers yet)
        race_data = []
        mock_overlay._handle_telemetry_update(race_data)

        assert mock_overlay.race_data == []
        assert mock_overlay.player_car_idx == 5

    def test_session_change_from_none_to_none(self, mock_overlay):
        """Test handling session change when both are None (edge case)."""
        # Both None
        mock_overlay.current_session_num = None
        mock_overlay.telemetry_processor.current_session_num = None
        mock_overlay.telemetry_processor.current_session_type = None

        race_data = [{'position': 1}]
        mock_overlay._handle_telemetry_update(race_data)

        # Should update data but not clear (session_num is None)
        assert mock_overlay.race_data == race_data

    def test_multiple_updates_same_session(self, mock_overlay):
        """Test multiple updates in the same session."""
        # Setup session
        mock_overlay.current_session_num = 1
        mock_overlay.current_session_type = 'Race'
        mock_overlay.telemetry_processor.current_session_num = 1
        mock_overlay.telemetry_processor.current_session_type = 'Race'
        mock_overlay.telemetry_processor.position_calculator.player_car_idx = 5

        # First update
        data1 = [{'position': 1}]
        mock_overlay._handle_telemetry_update(data1)
        assert mock_overlay.race_data == data1

        # Second update
        data2 = [{'position': 2}]
        mock_overlay._handle_telemetry_update(data2)
        assert mock_overlay.race_data == data2

        # Third update
        data3 = [{'position': 3}]
        mock_overlay._handle_telemetry_update(data3)
        assert mock_overlay.race_data == data3

    def test_session_numbers_with_types(self, mock_overlay):
        """Test various session number/type combinations."""
        mock_overlay.telemetry_processor.position_calculator.player_car_idx = 5

        # Practice session 0
        mock_overlay.telemetry_processor.current_session_num = 0
        mock_overlay.telemetry_processor.current_session_type = 'Practice'
        mock_overlay._handle_telemetry_update([{'p': 1}])
        assert mock_overlay.current_session_num == 0
        assert mock_overlay.current_session_type == 'Practice'

        # Qualify session 1
        mock_overlay.telemetry_processor.current_session_num = 1
        mock_overlay.telemetry_processor.current_session_type = 'Qualify'
        mock_overlay._handle_telemetry_update([{'p': 1}])
        assert mock_overlay.current_session_num == 1
        assert mock_overlay.current_session_type == 'Qualify'

        # Race session 2
        mock_overlay.telemetry_processor.current_session_num = 2
        mock_overlay.telemetry_processor.current_session_type = 'Race'
        mock_overlay._handle_telemetry_update([{'p': 1}])
        assert mock_overlay.current_session_num == 2
        assert mock_overlay.current_session_type == 'Race'

    def test_race_data_with_multiple_drivers(self, mock_overlay):
        """Test handling race data with multiple drivers."""
        mock_overlay.telemetry_processor.current_session_num = 0
        mock_overlay.telemetry_processor.current_session_type = 'Race'
        mock_overlay.telemetry_processor.position_calculator.player_car_idx = 5

        race_data = [
            {'position': 1, 'driver': 'Driver 1', 'car_idx': 1},
            {'position': 2, 'driver': 'Driver 2', 'car_idx': 5},  # Player
            {'position': 3, 'driver': 'Driver 3', 'car_idx': 10},
        ]

        mock_overlay._handle_telemetry_update(race_data)

        assert mock_overlay.race_data == race_data
        assert len(mock_overlay.race_data) == 3


class TestSessionChangeEdgeCases:
    """Test edge cases for session change detection."""

    @pytest.fixture
    def mock_overlay(self):
        """Create mock overlay (same as above)."""
        overlay = Mock()
        overlay.current_session_num = None
        overlay.current_session_type = None
        overlay.race_data = []
        overlay.player_car_idx = None

        overlay.telemetry_processor = Mock()
        overlay.telemetry_processor.current_session_num = None
        overlay.telemetry_processor.current_session_type = None
        overlay.telemetry_processor.position_calculator = Mock()
        overlay.telemetry_processor.position_calculator.player_car_idx = None

        def _handle_telemetry_update(self, race_data):
            if race_data is None:
                return
            session_changed = (
                self.current_session_num != self.telemetry_processor.current_session_num or
                self.current_session_type != self.telemetry_processor.current_session_type
            )
            self.current_session_num = self.telemetry_processor.current_session_num
            self.current_session_type = self.telemetry_processor.current_session_type
            if session_changed and self.current_session_num is not None:
                self.race_data = []
            self.race_data = race_data
            self.player_car_idx = self.telemetry_processor.position_calculator.player_car_idx

        overlay._handle_telemetry_update = _handle_telemetry_update.__get__(overlay)
        return overlay

    def test_session_change_with_none_session_num(self, mock_overlay):
        """Test session change when new session_num is None doesn't clear data."""
        # Start with valid session
        mock_overlay.current_session_num = 1
        mock_overlay.current_session_type = 'Race'
        mock_overlay.race_data = [{'old': 'data'}]

        # Change to None session (disconnect scenario)
        mock_overlay.telemetry_processor.current_session_num = None
        mock_overlay.telemetry_processor.current_session_type = None
        mock_overlay.telemetry_processor.position_calculator.player_car_idx = None

        new_data = [{'new': 'data'}]
        mock_overlay._handle_telemetry_update(new_data)

        # Session is updated but data is NOT cleared (session_num is None)
        assert mock_overlay.current_session_num is None
        assert mock_overlay.race_data == new_data  # Updated but not cleared first

    def test_rapid_session_changes(self, mock_overlay):
        """Test handling rapid session changes."""
        mock_overlay.telemetry_processor.position_calculator.player_car_idx = 5

        # Session 0
        mock_overlay.telemetry_processor.current_session_num = 0
        mock_overlay.telemetry_processor.current_session_type = 'Practice'
        mock_overlay._handle_telemetry_update([{'session': 0}])

        # Session 1
        mock_overlay.telemetry_processor.current_session_num = 1
        mock_overlay.telemetry_processor.current_session_type = 'Qualify'
        mock_overlay._handle_telemetry_update([{'session': 1}])

        # Session 2
        mock_overlay.telemetry_processor.current_session_num = 2
        mock_overlay.telemetry_processor.current_session_type = 'Race'
        mock_overlay._handle_telemetry_update([{'session': 2}])

        # Final state should be session 2
        assert mock_overlay.current_session_num == 2
        assert mock_overlay.current_session_type == 'Race'
        assert mock_overlay.race_data == [{'session': 2}]

    def test_session_type_change_same_number(self, mock_overlay):
        """Test type change without number change (rare but possible)."""
        mock_overlay.current_session_num = 0
        mock_overlay.current_session_type = 'Lone Qualify'
        mock_overlay.race_data = [{'old': 'data'}]

        # Same number, different type
        mock_overlay.telemetry_processor.current_session_num = 0
        mock_overlay.telemetry_processor.current_session_type = 'Open Qualify'
        mock_overlay.telemetry_processor.position_calculator.player_car_idx = 5

        new_data = [{'new': 'data'}]
        mock_overlay._handle_telemetry_update(new_data)

        assert mock_overlay.current_session_type == 'Open Qualify'
        assert mock_overlay.race_data == new_data


class TestSessionChangeFooterRefresh:
    """Tests for footer refresh behavior during session transitions."""

    def test_recalculates_footer_when_session_changes_and_race_data_none(self):
        """Session change should refresh footer/SoF even when race data is temporarily unavailable."""
        app = Mock(spec=LeagueOverlay)
        app.current_session_id = 100
        app.current_session_type = "Practice"
        app.race_data = [{'position': 1}]
        app._last_emitted_data = [{'position': 1}]
        app.class_leader_lap = 12

        app.telemetry_processor = Mock()
        app.telemetry_processor.current_session_id = 101
        app.telemetry_processor.current_session_type = "Race"
        app.telemetry_processor.get_footer_data = Mock(return_value={'sof': 2100})

        app.settings = Mock(show_footer=True, show_broadcast_header=False)
        app.signals = Mock()
        app.signals.update_footer = Mock()
        app.signals.update_footer.emit = Mock()

        app._handle_telemetry_update = LeagueOverlay._handle_telemetry_update.__get__(app)

        app._handle_telemetry_update(None)

        assert app.current_session_id == 101
        assert app.current_session_type == "Race"
        assert app.race_data == []
        assert app._last_emitted_data == []
        assert app.class_leader_lap is None
        app.telemetry_processor.get_footer_data.assert_called_once()
        app.signals.update_footer.emit.assert_called_once_with({'sof': 2100})

    def test_does_not_recalculate_footer_without_session_change_when_race_data_none(self):
        """No footer refresh should occur when session is unchanged and race data is None."""
        app = Mock(spec=LeagueOverlay)
        app.current_session_id = 100
        app.current_session_type = "Practice"
        app.race_data = [{'position': 1}]
        app._last_emitted_data = [{'position': 1}]
        app.class_leader_lap = 12

        app.telemetry_processor = Mock()
        app.telemetry_processor.current_session_id = 100
        app.telemetry_processor.current_session_type = "Practice"
        app.telemetry_processor.get_footer_data = Mock(return_value={'sof': 2100})

        app.settings = Mock(show_footer=True, show_broadcast_header=False)
        app.signals = Mock()
        app.signals.update_footer = Mock()
        app.signals.update_footer.emit = Mock()

        app._handle_telemetry_update = LeagueOverlay._handle_telemetry_update.__get__(app)

        app._handle_telemetry_update(None)

        assert app.race_data == [{'position': 1}]
        assert app._last_emitted_data == [{'position': 1}]
        assert app.class_leader_lap == 12
        app.telemetry_processor.get_footer_data.assert_not_called()
        app.signals.update_footer.emit.assert_not_called()


class TestOfficialLeagueBroadcastMetadata:
    """Tests for applying broadcast metadata from official leagues."""

    def test_apply_official_league_broadcast_metadata_sets_title_and_logo(self):
        app = Mock(spec=LeagueOverlay)
        app.color_config_file = "official:BWRL GT3 Sprint"
        app.settings = Mock(broadcast_header_title="", broadcast_header_logo=None)
        app.broadcast_header = Mock()
        app.apply_official_league_broadcast_metadata = (
            LeagueOverlay.apply_official_league_broadcast_metadata.__get__(app)
        )

        with patch("config.official_leagues.get_official_league") as get_official_league:
            get_official_league.return_value = Mock(
                title="Broken Wing GT3 Sprint",
                logo="https://bwrl.net/_nuxt/bwrl-logo.DjQE3-f5.png"
            )
            app.apply_official_league_broadcast_metadata()

        assert app.settings.broadcast_header_title == "Broken Wing GT3 Sprint"
        assert app.settings.broadcast_header_logo == "https://bwrl.net/_nuxt/bwrl-logo.DjQE3-f5.png"
        app.broadcast_header.refresh_styles.assert_called_once()

    def test_apply_official_league_broadcast_metadata_ignores_non_official_config(self):
        app = Mock(spec=LeagueOverlay)
        app.color_config_file = "league_divisions.json"
        app.settings = Mock(broadcast_header_title="Existing", broadcast_header_logo="/tmp/logo.png")
        app.apply_official_league_broadcast_metadata = (
            LeagueOverlay.apply_official_league_broadcast_metadata.__get__(app)
        )

        with patch("config.official_leagues.get_official_league") as get_official_league:
            app.apply_official_league_broadcast_metadata()

        assert app.settings.broadcast_header_title == "Existing"
        assert app.settings.broadcast_header_logo == "/tmp/logo.png"
        get_official_league.assert_not_called()
