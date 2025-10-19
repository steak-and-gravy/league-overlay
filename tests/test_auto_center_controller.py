"""Tests for auto_center_controller module.

Tests cover:
- Initial state and default behavior
- Manual interaction handling
- Timeout behavior with fake time
- Enable/disable functionality
- Timeout configuration
- Reset functionality
- Time tracking
"""

import pytest
from ui.auto_center_controller import AutoCenterController


class TestInitialState:
    """Test cases for initial controller state."""

    def test_default_timeout(self):
        """Test default timeout is 5.0 seconds."""
        controller = AutoCenterController()
        assert controller.get_timeout() == 5.0

    def test_custom_timeout(self):
        """Test custom timeout is set correctly."""
        controller = AutoCenterController(timeout=10.0)
        assert controller.get_timeout() == 10.0

    def test_initially_enabled(self):
        """Test controller is enabled by default."""
        controller = AutoCenterController()
        assert controller.is_enabled() is True

    def test_initial_state_allows_centering(self):
        """Test that initial state allows auto-centering.

        No manual interaction yet and timeout elapsed (since last_interaction=0).
        """
        controller = AutoCenterController(timeout=5.0)
        assert controller.should_auto_center() is True


class TestManualInteraction:
    """Test cases for manual interaction handling."""

    def test_manual_interaction_disables_centering(self):
        """Test manual interaction temporarily disables centering."""
        fake_time = 0.0
        controller = AutoCenterController(
            timeout=5.0,
            time_func=lambda: fake_time
        )

        controller.on_manual_interaction()
        assert controller.should_auto_center() is False

    def test_multiple_interactions_update_timestamp(self):
        """Test multiple interactions update the timestamp."""
        fake_time = 0.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=5.0, time_func=get_time)

        # First interaction at t=0
        controller.on_manual_interaction()
        assert controller.last_manual_interaction == 0.0

        # Second interaction at t=10
        fake_time = 10.0
        controller.on_manual_interaction()
        assert controller.last_manual_interaction == 10.0

    def test_get_time_since_interaction(self):
        """Test tracking time since last interaction."""
        fake_time = 0.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=5.0, time_func=get_time)

        controller.on_manual_interaction()
        fake_time = 3.5
        assert controller.get_time_since_interaction() == 3.5


class TestTimeoutBehavior:
    """Test cases for timeout behavior with fake time."""

    def test_timeout_re_enables_centering(self):
        """Test centering re-enables after timeout."""
        fake_time = 0.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=5.0, time_func=get_time)

        controller.on_manual_interaction()
        assert controller.should_auto_center() is False

        # Advance time past timeout
        fake_time = 6.0
        assert controller.should_auto_center() is True

    def test_exactly_at_timeout(self):
        """Test behavior exactly at timeout threshold."""
        fake_time = 0.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=5.0, time_func=get_time)

        controller.on_manual_interaction()

        # Exactly at timeout (5.0 >= 5.0 is True)
        fake_time = 5.0
        assert controller.should_auto_center() is True

    def test_just_before_timeout(self):
        """Test behavior just before timeout expires."""
        fake_time = 0.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=5.0, time_func=get_time)

        controller.on_manual_interaction()

        # Just before timeout
        fake_time = 4.999
        assert controller.should_auto_center() is False

    def test_long_after_timeout(self):
        """Test behavior long after timeout expires."""
        fake_time = 0.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=5.0, time_func=get_time)

        controller.on_manual_interaction()

        # Long after timeout
        fake_time = 100.0
        assert controller.should_auto_center() is True


class TestEnableDisable:
    """Test cases for enable/disable functionality."""

    def test_disable_prevents_centering(self):
        """Test disable() prevents centering regardless of timeout."""
        controller = AutoCenterController(timeout=5.0)
        controller.disable()
        assert controller.should_auto_center() is False

    def test_disable_overrides_timeout(self):
        """Test disabled state overrides timeout expiration."""
        fake_time = 0.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=5.0, time_func=get_time)

        controller.on_manual_interaction()
        fake_time = 10.0  # Well past timeout
        controller.disable()

        assert controller.should_auto_center() is False

    def test_enable_allows_centering(self):
        """Test enable() allows centering after disable."""
        controller = AutoCenterController(timeout=5.0)
        controller.disable()
        assert controller.is_enabled() is False

        controller.enable()
        assert controller.is_enabled() is True
        assert controller.should_auto_center() is True

    def test_enable_respects_timeout(self):
        """Test enabling still respects timeout period."""
        fake_time = 0.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=5.0, time_func=get_time)

        controller.disable()
        controller.on_manual_interaction()
        controller.enable()

        # Still within timeout
        fake_time = 2.0
        assert controller.should_auto_center() is False

        # Past timeout
        fake_time = 6.0
        assert controller.should_auto_center() is True


class TestTimeoutConfiguration:
    """Test cases for timeout configuration."""

    def test_set_timeout(self):
        """Test setting timeout value."""
        controller = AutoCenterController(timeout=5.0)
        controller.set_timeout(10.0)
        assert controller.get_timeout() == 10.0

    def test_timeout_change_affects_behavior(self):
        """Test changing timeout affects centering behavior."""
        fake_time = 0.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=5.0, time_func=get_time)

        controller.on_manual_interaction()
        fake_time = 6.0

        # Should allow centering with 5s timeout
        assert controller.should_auto_center() is True

        # Change timeout to 10s
        controller.set_timeout(10.0)
        controller.on_manual_interaction()
        fake_time = 16.0

        # Reset interaction time
        fake_time = 0.0
        controller.on_manual_interaction()
        fake_time = 6.0

        # Should NOT allow centering with 10s timeout
        assert controller.should_auto_center() is False

        fake_time = 11.0
        assert controller.should_auto_center() is True

    def test_zero_timeout(self):
        """Test zero timeout (always allows centering)."""
        fake_time = 0.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=0.0, time_func=get_time)

        controller.on_manual_interaction()
        # Even immediately after interaction (0 >= 0 is True)
        assert controller.should_auto_center() is True

    def test_very_large_timeout(self):
        """Test very large timeout value."""
        fake_time = 0.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=1000.0, time_func=get_time)

        controller.on_manual_interaction()
        fake_time = 500.0

        # Still within timeout
        assert controller.should_auto_center() is False

        fake_time = 1001.0
        assert controller.should_auto_center() is True


class TestReset:
    """Test cases for reset functionality."""

    def test_reset_clears_interaction_time(self):
        """Test reset clears last interaction timestamp."""
        fake_time = 0.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=5.0, time_func=get_time)

        controller.on_manual_interaction()
        fake_time = 2.0

        assert controller.should_auto_center() is False

        controller.reset()
        assert controller.last_manual_interaction == 0.0

    def test_reset_enables_controller(self):
        """Test reset enables the controller."""
        controller = AutoCenterController(timeout=5.0)
        controller.disable()

        controller.reset()
        assert controller.is_enabled() is True

    def test_reset_allows_centering(self):
        """Test reset allows auto-centering."""
        fake_time = 0.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=5.0, time_func=get_time)

        controller.on_manual_interaction()
        controller.disable()

        controller.reset()
        # After reset, should allow centering (no recent interaction)
        fake_time = 10.0
        assert controller.should_auto_center() is True

    def test_reset_preserves_timeout(self):
        """Test reset does not change timeout value."""
        controller = AutoCenterController(timeout=7.5)
        controller.reset()
        assert controller.get_timeout() == 7.5


class TestEdgeCases:
    """Test edge cases and unusual scenarios."""

    def test_negative_time_difference(self):
        """Test handling of time going backwards (clock adjustments)."""
        fake_time = 100.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=5.0, time_func=get_time)

        controller.on_manual_interaction()

        # Time goes backwards (e.g., clock adjustment)
        fake_time = 50.0

        # Should not allow centering (negative time difference)
        assert controller.should_auto_center() is False

    def test_very_small_timeout_fractions(self):
        """Test very small fractional timeout values."""
        fake_time = 0.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=0.001, time_func=get_time)

        controller.on_manual_interaction()
        fake_time = 0.0005

        assert controller.should_auto_center() is False

        fake_time = 0.001
        assert controller.should_auto_center() is True

    def test_multiple_disable_enable_cycles(self):
        """Test multiple enable/disable cycles work correctly."""
        controller = AutoCenterController(timeout=5.0)

        for _ in range(5):
            controller.disable()
            assert controller.is_enabled() is False

            controller.enable()
            assert controller.is_enabled() is True

    def test_interaction_after_disable(self):
        """Test interaction recorded even when disabled."""
        fake_time = 0.0

        def get_time():
            return fake_time

        controller = AutoCenterController(timeout=5.0, time_func=get_time)

        controller.disable()
        controller.on_manual_interaction()

        # Interaction should be recorded
        assert controller.last_manual_interaction == 0.0

        # Enable and check timeout is respected
        controller.enable()
        fake_time = 3.0
        assert controller.should_auto_center() is False

        fake_time = 6.0
        assert controller.should_auto_center() is True
