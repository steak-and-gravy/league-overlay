"""Tests for startup update notification prompts."""

from unittest.mock import Mock, patch

from PySide6.QtWidgets import QMessageBox

from league_overlay import LeagueOverlay


def _mock_overlay():
    app = Mock(spec=LeagueOverlay)
    app.prompt_for_update = LeagueOverlay.prompt_for_update.__get__(app)
    app.latest_version = None
    return app


def test_prompt_for_update_opens_download_page_on_yes(qapp):
    """Accepting the update prompt should open the supplied download URL."""
    app = _mock_overlay()
    update_info = {
        "latest_version": "1.2.3",
        "download_url": "https://leagueoverlay.com/download.php",
    }

    with (
        patch("league_overlay.QMessageBox.question", return_value=QMessageBox.Yes) as question,
        patch("league_overlay.QDesktopServices.openUrl", return_value=True) as open_url,
    ):
        app.prompt_for_update(update_info)

    assert question.call_args.args[1] == "Update Available"
    assert "v1.2.3 is available" in question.call_args.args[2]
    assert open_url.call_args.args[0].toString() == "https://leagueoverlay.com/download.php"


def test_prompt_for_update_does_not_open_download_page_on_no(qapp):
    """Declining the update prompt should leave the browser alone."""
    app = _mock_overlay()
    update_info = {
        "latest_version": "1.2.3",
        "download_url": "https://leagueoverlay.com/download.php",
    }

    with (
        patch("league_overlay.QMessageBox.question", return_value=QMessageBox.No),
        patch("league_overlay.QDesktopServices.openUrl", return_value=True) as open_url,
    ):
        app.prompt_for_update(update_info)

    open_url.assert_not_called()
