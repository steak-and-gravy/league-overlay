"""Auto-centering behavior controller for scrollable views.

This module provides a clean interface for managing auto-centering behavior
that respects manual user interactions.
"""

import time
from typing import Callable, Optional


class AutoCenterController:
    """Controls auto-centering behavior with manual override.

    This class manages the logic for automatically centering a view on a target
    while respecting manual user interactions. When a user manually interacts
    (e.g., scrolls), auto-centering is temporarily disabled for a configurable
    timeout period.

    Example:
        controller = AutoCenterController(timeout=5.0)

        # When user scrolls manually
        controller.on_manual_interaction()

        # In update loop
        if controller.should_auto_center():
            scroll_to_player()

    Features:
    - Configurable timeout period
    - Can be enabled/disabled globally
    - Testable (can inject time function for testing)
    - Clear API
    """

    def __init__(self, timeout: float = 5.0, time_func: Optional[Callable[[], float]] = None):
        """Initialize the auto-center controller.

        Args:
            timeout: Time in seconds to wait after manual interaction before
                    re-enabling auto-center (default: 5.0)
            time_func: Function to get current time (default: time.time)
                      Useful for testing with a mock time function
        """
        self.timeout = timeout
        self.last_manual_interaction = 0.0
        self.enabled = True
        self._time_func = time_func or time.time

    def on_manual_interaction(self) -> None:
        """Record that the user has manually interacted.

        This should be called whenever the user manually scrolls, clicks,
        or otherwise interacts with the view. Auto-centering will be
        disabled for the configured timeout period.
        """
        self.last_manual_interaction = self._time_func()

    def should_auto_center(self) -> bool:
        """Check if auto-centering should occur.

        Returns:
            True if auto-centering is enabled and the timeout period has
            elapsed since the last manual interaction, False otherwise
        """
        if not self.enabled:
            return False

        time_since_interaction = self._time_func() - self.last_manual_interaction
        return time_since_interaction >= self.timeout

    def enable(self) -> None:
        """Enable auto-centering.

        When enabled, auto-centering will occur if the timeout period
        has elapsed since the last manual interaction.
        """
        self.enabled = True

    def disable(self) -> None:
        """Disable auto-centering.

        When disabled, should_auto_center() will always return False
        regardless of manual interaction timing.
        """
        self.enabled = False

    def is_enabled(self) -> bool:
        """Check if auto-centering is enabled.

        Returns:
            True if enabled, False otherwise
        """
        return self.enabled

    def set_timeout(self, timeout: float) -> None:
        """Set the timeout period.

        Args:
            timeout: Time in seconds to wait after manual interaction
        """
        self.timeout = timeout

    def get_timeout(self) -> float:
        """Get the current timeout period.

        Returns:
            Timeout in seconds
        """
        return self.timeout

    def get_time_since_interaction(self) -> float:
        """Get the time elapsed since the last manual interaction.

        Returns:
            Time in seconds since last interaction
        """
        return self._time_func() - self.last_manual_interaction

    def reset(self) -> None:
        """Reset the controller to initial state.

        Clears the last interaction time and enables auto-centering.
        """
        self.last_manual_interaction = 0.0
        self.enabled = True
