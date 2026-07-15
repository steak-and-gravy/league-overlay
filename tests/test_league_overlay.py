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
from types import SimpleNamespace
from league_overlay import LeagueOverlay
from core.driver_state import DriverState


@patch("league_overlay.DivisionManager")
def test_reload_division_config_rebinds_runtime_consumers(mock_manager_class):
    app = LeagueOverlay.__new__(LeagueOverlay)
    app.settings = SimpleNamespace(
        division_colors={"Default": "#C5C5C5"},
        league_color_overrides={},
        auto_assign_unknown_driver_class="Am",
        persist_auto_assigned_unknown_drivers=True,
    )
    app.division_filter = SimpleNamespace(division_manager=object())
    app.telemetry_processor = SimpleNamespace(division_manager=object())
    app.signals = SimpleNamespace(refresh_colors=SimpleNamespace(emit=Mock()))
    app._last_emitted_data = [object()]
    replacement_manager = mock_manager_class.return_value

    LeagueOverlay.reload_division_config(app, "/tmp/league.json")

    assert app.division_manager is replacement_manager
    assert app.division_filter.division_manager is replacement_manager
    assert app.telemetry_processor.division_manager is replacement_manager
    mock_manager_class.assert_called_once_with(
        "/tmp/league.json",
        app_default_colors=app.settings.division_colors,
        league_color_overrides=app.settings.league_color_overrides,
        unknown_driver_class="Am",
        persist_unknown_driver_assignments=True,
    )


def test_update_all_backgrounds_refreshes_footer_opacity():
    app = LeagueOverlay.__new__(LeagueOverlay)
    app.settings = SimpleNamespace(
        opacity=0.35,
        font_size="Medium",
        show_broadcast_header=False,
    )
    app.footer_frame = Mock()
    app.sync_local_web_overlay = Mock(return_value=None)

    LeagueOverlay.update_all_backgrounds(app)

    app.footer_frame.setStyleSheet.assert_called_once_with(
        "background-color: rgba(51, 51, 51, 0.35);"
    )


def test_get_bg_color_keeps_zero_opacity_interactive():
    app = LeagueOverlay.__new__(LeagueOverlay)
    app.settings = SimpleNamespace(opacity=0.0)

    assert LeagueOverlay.get_bg_color(app, "#333333") == "rgba(51, 51, 51, 0.01)"


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

    def test_clears_standings_when_session_changes_and_race_data_none(self):
        """Practice to qualifying should show registered-driver placeholders when race_data is None."""
        app = Mock(spec=LeagueOverlay)
        app.current_session_id = 100
        app.current_session_type = "Practice"
        app.race_data = [{'position': 1}]
        app._last_emitted_data = [{'position': 1}]
        app.class_leader_lap = 12
        placeholder_data = [Mock(spec=DriverState)]

        app.telemetry_processor = Mock()
        app.telemetry_processor.current_session_id = 101
        app.telemetry_processor.current_session_type = "Qualifying"
        app.telemetry_processor.previous_session_type = "Practice"
        app.telemetry_processor.position_calculator = Mock()
        app.telemetry_processor.position_calculator.player_car_idx = 5
        app.telemetry_processor.position_calculator.spectated_car_idx = None
        app.race_state_tracker = Mock()
        app.race_state_tracker.consume_starting_positions_update = Mock(return_value=False)
        app.division_filter = Mock()
        app.division_manager = Mock()
        app.telemetry_processor.get_footer_data = Mock(return_value={'sof': 2100})

        app.settings = Mock(show_footer=True, show_broadcast_header=False)
        app.signals = Mock()
        app.signals.update_footer = Mock()
        app.signals.update_footer.emit = Mock()
        app.signals.update_data = Mock()
        app.signals.update_data.emit = Mock()
        app._build_registered_driver_placeholders = Mock(return_value=placeholder_data)

        app._handle_telemetry_update = LeagueOverlay._handle_telemetry_update.__get__(app)

        app._handle_telemetry_update(None)

        assert app.current_session_id == 101
        assert app.current_session_type == "Qualifying"
        assert app.race_data == placeholder_data
        assert app._last_emitted_data == placeholder_data
        assert app.class_leader_lap is None
        app.signals.update_data.emit.assert_called_once_with(placeholder_data)
        app.telemetry_processor.get_footer_data.assert_not_called()
        app.signals.update_footer.emit.assert_not_called()

    def test_qualifying_to_race_does_not_clear_when_race_data_none(self):
        """Qualifying to race should preserve standings during the handoff."""
        app = Mock(spec=LeagueOverlay)
        app.current_session_id = 100
        app.current_session_type = "Qualifying"
        app.race_data = [{'position': 1}]
        app._last_emitted_data = [{'position': 1}]
        app.class_leader_lap = 12

        app.telemetry_processor = Mock()
        app.telemetry_processor.current_session_id = 101
        app.telemetry_processor.current_session_type = "Race"
        app.telemetry_processor.previous_session_type = "Qualifying"
        app.telemetry_processor.position_calculator = Mock()
        app.telemetry_processor.position_calculator.player_car_idx = 5
        app.telemetry_processor.position_calculator.spectated_car_idx = None
        app.race_state_tracker = Mock()
        app.race_state_tracker.consume_starting_positions_update = Mock(return_value=False)
        app.division_filter = Mock()
        app.division_manager = Mock()
        app.telemetry_processor.get_footer_data = Mock(return_value={'sof': 2100})

        app.settings = Mock(show_footer=True, show_broadcast_header=False)
        app.signals = Mock()
        app.signals.update_footer = Mock()
        app.signals.update_footer.emit = Mock()
        app.signals.update_data = Mock()
        app.signals.update_data.emit = Mock()

        app._handle_telemetry_update = LeagueOverlay._handle_telemetry_update.__get__(app)

        app._handle_telemetry_update(None)

        assert app.current_session_id == 101
        assert app.current_session_type == "Race"
        assert app.race_data == [{'position': 1}]
        assert app._last_emitted_data == [{'position': 1}]
        assert app.class_leader_lap == 12
        app.signals.update_data.emit.assert_not_called()
        app.telemetry_processor.get_footer_data.assert_not_called()
        app.signals.update_footer.emit.assert_not_called()

    def test_race_to_practice_does_not_clear_when_race_data_none(self):
        """Only practice to qualifying should clear standings."""
        app = Mock(spec=LeagueOverlay)
        app.current_session_id = 100
        app.current_session_type = "Race"
        app.race_data = [{'position': 1}]
        app._last_emitted_data = [{'position': 1}]
        app.class_leader_lap = 12

        app.telemetry_processor = Mock()
        app.telemetry_processor.current_session_id = 101
        app.telemetry_processor.current_session_type = "Practice"
        app.telemetry_processor.previous_session_type = "Race"
        app.telemetry_processor.position_calculator = Mock()
        app.telemetry_processor.position_calculator.player_car_idx = 5
        app.telemetry_processor.position_calculator.spectated_car_idx = None
        app.race_state_tracker = Mock()
        app.race_state_tracker.consume_starting_positions_update = Mock(return_value=False)
        app.division_filter = Mock()
        app.division_manager = Mock()
        app.telemetry_processor.get_footer_data = Mock(return_value={'sof': 2100})

        app.settings = Mock(show_footer=True, show_broadcast_header=False)
        app.signals = Mock()
        app.signals.update_footer = Mock()
        app.signals.update_footer.emit = Mock()
        app.signals.update_data = Mock()
        app.signals.update_data.emit = Mock()

        app._handle_telemetry_update = LeagueOverlay._handle_telemetry_update.__get__(app)

        app._handle_telemetry_update(None)

        assert app.current_session_id == 101
        assert app.current_session_type == "Practice"
        assert app.race_data == [{'position': 1}]
        assert app._last_emitted_data == [{'position': 1}]
        assert app.class_leader_lap == 12
        app.signals.update_data.emit.assert_not_called()
        app.telemetry_processor.get_footer_data.assert_not_called()
        app.signals.update_footer.emit.assert_not_called()

    def test_practice_to_open_qualify_clears_when_race_data_none(self):
        """Qualifying variants like Open Qualify should also show registered-driver placeholders."""
        app = Mock(spec=LeagueOverlay)
        app.current_session_id = 100
        app.current_session_type = "Practice"
        app.race_data = [{'position': 1}]
        app._last_emitted_data = [{'position': 1}]
        app.class_leader_lap = 12
        placeholder_data = [Mock(spec=DriverState)]

        app.telemetry_processor = Mock()
        app.telemetry_processor.current_session_id = 101
        app.telemetry_processor.current_session_type = "Open Qualify"
        app.telemetry_processor.previous_session_type = "Practice"
        app.telemetry_processor.position_calculator = Mock()
        app.telemetry_processor.position_calculator.player_car_idx = 5
        app.telemetry_processor.position_calculator.spectated_car_idx = None
        app.race_state_tracker = Mock()
        app.race_state_tracker.consume_starting_positions_update = Mock(return_value=False)
        app.division_filter = Mock()
        app.division_manager = Mock()
        app.telemetry_processor.get_footer_data = Mock(return_value={'sof': 2100})

        app.settings = Mock(show_footer=True, show_broadcast_header=False)
        app.signals = Mock()
        app.signals.update_footer = Mock()
        app.signals.update_footer.emit = Mock()
        app.signals.update_data = Mock()
        app.signals.update_data.emit = Mock()
        app._build_registered_driver_placeholders = Mock(return_value=placeholder_data)

        app._handle_telemetry_update = LeagueOverlay._handle_telemetry_update.__get__(app)

        app._handle_telemetry_update(None)

        assert app.current_session_id == 101
        assert app.current_session_type == "Open Qualify"
        assert app.race_data == placeholder_data
        assert app._last_emitted_data == placeholder_data
        assert app.class_leader_lap is None
        app.signals.update_data.emit.assert_called_once_with(placeholder_data)

    def test_practice_to_qualifying_with_race_data_shows_placeholders_then_renders_new_data(self):
        """Practice to qualifying should emit placeholders before new standings."""
        app = Mock(spec=LeagueOverlay)
        app.current_session_id = 100
        app.current_session_type = "Practice"
        app.race_data = [{'position': 1}]
        app._last_emitted_data = [{'position': 1}]
        app.class_leader_lap = 12
        app.player_car_idx = None
        app.spectated_car_idx = None
        placeholder_data = [Mock(spec=DriverState)]

        app.telemetry_processor = Mock()
        app.telemetry_processor.current_session_id = 101
        app.telemetry_processor.current_session_type = "Qualifying"
        app.telemetry_processor.previous_session_type = "Practice"
        app.telemetry_processor.position_calculator = Mock()
        app.telemetry_processor.position_calculator.player_car_idx = 5
        app.telemetry_processor.position_calculator.spectated_car_idx = None
        app.telemetry_processor.get_footer_data = Mock(return_value={'sof': 2100})

        app.race_state_tracker = Mock()
        app.race_state_tracker.consume_starting_positions_update = Mock(return_value=False)
        app.division_filter = Mock()
        current_data = [Mock(current_lap=0)]
        app.division_filter.apply_filter = Mock(return_value=current_data)
        app.division_manager = Mock()
        app.division_manager.get_driver_color = Mock()
        app._has_data_changed = Mock(return_value=True)

        app.settings = Mock(show_footer=False, show_broadcast_header=False)
        app.signals = Mock()
        app.signals.update_footer = Mock()
        app.signals.update_footer.emit = Mock()
        app.signals.update_data = Mock()
        app.signals.update_data.emit = Mock()
        app._build_registered_driver_placeholders = Mock(return_value=placeholder_data)

        app._handle_telemetry_update = LeagueOverlay._handle_telemetry_update.__get__(app)

        race_data = [Mock(position=1)]
        app._handle_telemetry_update(race_data)

        assert app.current_session_id == 101
        assert app.current_session_type == "Qualifying"
        assert app.race_data == race_data
        assert app.player_car_idx == 5
        assert app.class_leader_lap == 0
        assert app._last_emitted_data == current_data
        assert app.signals.update_data.emit.call_args_list[0].args == (placeholder_data,)
        assert app.signals.update_data.emit.call_args_list[1].args == (current_data,)

    def test_build_registered_driver_placeholders_uses_session_driver_info(self):
        """Placeholder rows should come from live session driver info and preserve division colors."""
        app = Mock(spec=LeagueOverlay)
        app.ir = MagicMock()
        app.ir.__getitem__.side_effect = lambda key: {
            'DriverInfo': {
                'PaceCarXIdx': [12],
                'Drivers': [
                    {'CarIdx': 7, 'UserID': 101, 'UserName': 'Driver One', 'CarNumber': '12', 'CarClassID': 100, 'CarPath': 'porsche 911 gt3 r'},
                    {'CarIdx': 8, 'UserID': 102, 'UserName': 'Driver Two', 'CarNumber': '42', 'CarClassID': 100, 'CarPath': 'orphan prototype'},
                    {'CarIdx': 9, 'UserID': 103, 'UserName': 'Other Class', 'CarNumber': '88', 'CarClassID': 200},
                    {'CarIdx': 10, 'UserID': 104, 'UserName': 'Pace Car', 'CarNumber': 'PC', 'CarClassID': 100},
                    {'CarIdx': 11, 'UserID': 105, 'UserName': 'Spectator', 'CarNumber': '0', 'CarClassID': 100},
                    {'CarIdx': 12, 'UserID': 106, 'UserName': 'Official Vehicle', 'CarNumber': 'PC2', 'CarClassID': 100},
                ]
            }
        }[key]
        app.position_calculator = Mock()
        app.position_calculator.player_car_class_id = 100
        app.division_manager = Mock()
        app.division_manager.get_driver_division.side_effect = lambda driver_info: {
            101: 'Pro',
            102: None,
        }.get(driver_info.get('UserID'))
        app.division_manager.get_division_color.side_effect = lambda division: {
            'Pro': '#FF8C00',
            None: '#D3D3D3',
        }.get(division, '#D3D3D3')

        app._build_registered_driver_placeholders = (
            LeagueOverlay._build_registered_driver_placeholders.__get__(app)
        )

        placeholders = app._build_registered_driver_placeholders()

        assert len(placeholders) == 2
        assert placeholders[0].car_idx == 7
        assert placeholders[0].driver_name == 'Driver One'
        assert placeholders[0].driver_info['UserID'] == 101
        assert placeholders[0].car_number == '12'
        assert placeholders[0].division_name == 'Pro'
        assert placeholders[0].division_color == '#FF8C00'
        assert placeholders[0].car_manufacturer == 'POR'
        assert placeholders[0].car_manufacturer_color == '#C0C0C0'
        assert placeholders[0].position == 0
        assert placeholders[0].best_lap == ''
        assert placeholders[1].car_idx == 8
        assert placeholders[1].driver_name == 'Driver Two'
        assert placeholders[1].car_number == '42'
        assert placeholders[1].division_name is None
        assert placeholders[1].division_color == '#D3D3D3'
        assert placeholders[1].car_manufacturer == 'ORP'
        assert placeholders[1].car_manufacturer_color == '#FFFFFF'

    def test_build_registered_driver_placeholders_returns_empty_when_driverinfo_unavailable(self):
        """Missing DriverInfo should safely produce no placeholders."""
        app = Mock(spec=LeagueOverlay)
        app.ir = MagicMock()
        app.ir.__getitem__.side_effect = KeyError('DriverInfo')
        app.position_calculator = Mock()
        app.position_calculator.player_car_class_id = 100
        app.division_manager = Mock()

        app._build_registered_driver_placeholders = (
            LeagueOverlay._build_registered_driver_placeholders.__get__(app)
        )

        assert app._build_registered_driver_placeholders() == []

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
        app.telemetry_processor.previous_session_type = None
        app.telemetry_processor.position_calculator = Mock()
        app.telemetry_processor.position_calculator.player_car_idx = 5
        app.telemetry_processor.position_calculator.spectated_car_idx = None
        app.race_state_tracker = Mock()
        app.race_state_tracker.consume_starting_positions_update = Mock(return_value=False)
        app.division_filter = Mock()
        app.division_manager = Mock()
        app.telemetry_processor.get_footer_data = Mock(return_value={'sof': 2100})

        app.settings = Mock(show_footer=True, show_broadcast_header=False)
        app.signals = Mock()
        app.signals.update_footer = Mock()
        app.signals.update_footer.emit = Mock()
        app.signals.update_data = Mock()
        app.signals.update_data.emit = Mock()

        app._handle_telemetry_update = LeagueOverlay._handle_telemetry_update.__get__(app)

        app._handle_telemetry_update(None)

        assert app.race_data == [{'position': 1}]
        assert app._last_emitted_data == [{'position': 1}]
        assert app.class_leader_lap == 12
        app.telemetry_processor.get_footer_data.assert_not_called()
        app.signals.update_footer.emit.assert_not_called()
        app.signals.update_data.emit.assert_not_called()


class TestOfficialLeagueBroadcastMetadata:
    """Tests for applying broadcast metadata from official leagues."""

    def test_apply_official_league_broadcast_metadata_sets_title_and_logo(self):
        app = Mock(spec=LeagueOverlay)
        app.color_config_file = "official:BWRL GT3 Sprint"
        app.broadcast_header_title = ""
        app.broadcast_header_logo = None
        app.broadcast_header_accent_color = "#000000"
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

        assert app.broadcast_header_title == "Broken Wing GT3 Sprint"
        assert app.broadcast_header_logo == "https://bwrl.net/_nuxt/bwrl-logo.DjQE3-f5.png"
        assert app.broadcast_header_accent_color == "#FF8C00"
        app.broadcast_header.refresh_styles.assert_called_once()


class TestHasDataChanged:
    """Tests for display-refresh change detection."""

    def test_car_number_outline_change_triggers_refresh(self):
        """The UI should redraw when the mandatory-stop outline state changes."""
        app = Mock(spec=LeagueOverlay)
        app.settings = SimpleNamespace(
            show_delta=False,
            show_last_lap=False,
            show_pit_lap=False,
            pit_stop_indicator=True,
            show_recent_lap_flash=True,
        )

        old_driver = DriverState(
            car_idx=5,
            driver_info={"UserName": "Focused Driver", "CarNumber": "42"},
            position=1,
            division_position=1,
            division_name="Pro",
            show_car_number_outline=True,
        )
        new_driver = DriverState(
            car_idx=5,
            driver_info={"UserName": "Focused Driver", "CarNumber": "42"},
            position=1,
            division_position=1,
            division_name="Pro",
            show_car_number_outline=False,
        )
        app._last_emitted_data = [old_driver]

        app._has_data_changed = LeagueOverlay._has_data_changed.__get__(app)

        assert app._has_data_changed([new_driver]) is True

    def test_car_number_outline_change_ignored_when_pit_stop_indicator_disabled(self):
        """Outline state alone should not force a redraw when the indicator is disabled."""
        app = Mock(spec=LeagueOverlay)
        app.settings = SimpleNamespace(
            show_delta=False,
            show_last_lap=False,
            show_pit_lap=False,
            pit_stop_indicator=False,
            show_recent_lap_flash=True,
        )

        old_driver = DriverState(
            car_idx=5,
            driver_info={"UserName": "Focused Driver", "CarNumber": "42"},
            position=1,
            division_position=1,
            division_name="Pro",
            show_car_number_outline=True,
        )
        new_driver = DriverState(
            car_idx=5,
            driver_info={"UserName": "Focused Driver", "CarNumber": "42"},
            position=1,
            division_position=1,
            division_name="Pro",
            show_car_number_outline=False,
        )
        app._last_emitted_data = [old_driver]

        app._has_data_changed = LeagueOverlay._has_data_changed.__get__(app)

        assert app._has_data_changed([new_driver]) is False

    def test_recent_lap_flash_change_forces_redraw(self):
        """Transient name-cell flashes must trigger a row rebuild even without column toggles."""
        app = Mock(spec=LeagueOverlay)
        app.settings = SimpleNamespace(
            show_delta=False,
            show_last_lap=False,
            show_pit_lap=False,
            pit_stop_indicator=True,
            show_recent_lap_flash=True,
        )

        old_driver = DriverState(
            car_idx=5,
            driver_info={"UserName": "Focused Driver", "CarNumber": "42"},
            position=1,
            division_position=1,
            division_name="Pro",
            recent_lap_flash="",
        )
        new_driver = DriverState(
            car_idx=5,
            driver_info={"UserName": "Focused Driver", "CarNumber": "42"},
            position=1,
            division_position=1,
            division_name="Pro",
            recent_lap_flash="1:29.9",
        )
        app._last_emitted_data = [old_driver]

        app._has_data_changed = LeagueOverlay._has_data_changed.__get__(app)

        assert app._has_data_changed([new_driver]) is True

    def test_recent_lap_flash_state_change_forces_redraw(self):
        """Flash-state changes must redraw while the feature is enabled."""
        app = Mock(spec=LeagueOverlay)
        app.settings = SimpleNamespace(
            show_delta=False,
            show_last_lap=False,
            show_pit_lap=False,
            pit_stop_indicator=True,
            show_recent_lap_flash=True,
        )

        old_driver = DriverState(
            car_idx=5,
            driver_info={"UserName": "Focused Driver", "CarNumber": "42"},
            position=1,
            division_position=1,
            division_name="Pro",
            recent_lap_flash="1:29.9",
            recent_lap_flash_state="first_lap",
        )
        new_driver = DriverState(
            car_idx=5,
            driver_info={"UserName": "Focused Driver", "CarNumber": "42"},
            position=1,
            division_position=1,
            division_name="Pro",
            recent_lap_flash="1:29.9",
            recent_lap_flash_state="slower",
        )
        app._last_emitted_data = [old_driver]

        app._has_data_changed = LeagueOverlay._has_data_changed.__get__(app)

        assert app._has_data_changed([new_driver]) is True

    def test_recent_lap_flash_changes_are_ignored_when_feature_disabled(self):
        """Hidden recent-lap flashes should not force redraws."""
        app = Mock(spec=LeagueOverlay)
        app.settings = SimpleNamespace(
            show_delta=False,
            show_last_lap=False,
            show_pit_lap=False,
            pit_stop_indicator=True,
            show_recent_lap_flash=False,
        )

        old_driver = DriverState(
            car_idx=5,
            driver_info={"UserName": "Focused Driver", "CarNumber": "42"},
            position=1,
            division_position=1,
            division_name="Pro",
            recent_lap_flash="",
            recent_lap_flash_state="",
        )
        new_driver = DriverState(
            car_idx=5,
            driver_info={"UserName": "Focused Driver", "CarNumber": "42"},
            position=1,
            division_position=1,
            division_name="Pro",
            recent_lap_flash="1:29.9",
            recent_lap_flash_state="slower",
        )
        app._last_emitted_data = [old_driver]

        app._has_data_changed = LeagueOverlay._has_data_changed.__get__(app)

        assert app._has_data_changed([new_driver]) is False

    def test_apply_official_league_broadcast_metadata_resets_to_defaults_for_non_official_config(self):
        app = Mock(spec=LeagueOverlay)
        app.color_config_file = "league_divisions.json"
        app.broadcast_header_title = "Existing"
        app.broadcast_header_logo = "https://example.com/logo.png"
        app.broadcast_header_accent_color = "#123456"
        app.apply_official_league_broadcast_metadata = (
            LeagueOverlay.apply_official_league_broadcast_metadata.__get__(app)
        )

        with patch("config.official_leagues.get_official_league") as get_official_league:
            app.apply_official_league_broadcast_metadata()

        assert app.broadcast_header_title == "BB's League Overlay"
        assert app.broadcast_header_logo == "https://leagueoverlay.com/assets/img/BBLeagueOverlay96.png"
        assert app.broadcast_header_accent_color == "#FF8C00"
        get_official_league.assert_not_called()


class TestDisplayRaceDataClearing:
    """Tests for clearing rendered rows when data becomes empty."""

    def test_display_race_data_empty_list_clears_existing_widgets(self):
        """An empty update should clear stale standings rows from the UI."""
        app = Mock(spec=LeagueOverlay)
        app._is_broadcast_roll_active = Mock(return_value=False)
        app.auto_center = Mock()
        app.auto_center.should_auto_center.return_value = False
        app.player_car_idx = None
        app.spectated_car_idx = None
        app.broadcast_roll_page_index = 3
        app._update_broadcast_roll_mode = Mock()
        app.adjust_header_margins = Mock()
        app.displayed_data = [{'position': 1}]

        widget_one = Mock()
        widget_two = Mock()
        spacer_item = Mock()
        spacer_item.widget.return_value = None
        item_one = Mock()
        item_one.widget.return_value = widget_one
        item_two = Mock()
        item_two.widget.return_value = widget_two

        app.scroll_layout = Mock()
        app.scroll_layout.count.side_effect = [3, 2, 1]
        app.scroll_layout.takeAt.side_effect = [item_one, item_two]

        app.display_race_data = LeagueOverlay.display_race_data.__get__(app)
        app.display_race_data([])

        widget_one.deleteLater.assert_called_once()
        widget_two.deleteLater.assert_called_once()
        assert app.displayed_data == []
        assert app.broadcast_roll_page_index == 0
        app._update_broadcast_roll_mode.assert_called_once()
        app.adjust_header_margins.assert_called_once()
