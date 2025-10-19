"""Driver division management and color configuration."""

import json
import os
from typing import Dict, Optional

from config.constants import UI_CONFIG, FILE_CONFIG
from config.logging_config import get_logger

logger = get_logger(__name__)


class DivisionManager:
    """Manages driver-to-division assignments and color configuration."""

    def __init__(self, config_file: str = FILE_CONFIG.DIVISIONS_FILE, settings_file: str = FILE_CONFIG.SETTINGS_FILE):
        """Initialize division manager.

        Args:
            config_file: Path to JSON file containing driver-division mappings
            settings_file: Path to settings file for division colors
        """
        self.config_file = config_file
        self.settings_file = settings_file
        self.driver_colors: dict[str, list] = {'drivers': []}
        self.division_colors: dict[str, str] = UI_CONFIG.DEFAULT_COLORS.copy()
        self.load_driver_config()
        self.load_division_config()

    def load_driver_config(self) -> None:
        """Load driver-division mappings from config file."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    if 'drivers' in data:
                        self.driver_colors = data
                        logger.info(f"Loaded {len(data['drivers'])} driver division assignments from {self.config_file}")
                    else:
                        self.driver_colors = {'drivers': []}
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading division config: {e}", exc_info=True)
                print(f"Error loading division config: {e}")
                self.driver_colors = {'drivers': []}
        else:
            self.driver_colors = {'drivers': []}

    def load_division_config(self) -> None:
        """Load division colors from settings file."""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                    division_colors = data.get('division_colors', {})
                    self.division_colors.update(division_colors)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading division colors: {e}", exc_info=True)
                print(f"Error loading division colors: {e}")
                self.division_colors = UI_CONFIG.DEFAULT_COLORS.copy()
        else:
            self.division_colors = UI_CONFIG.DEFAULT_COLORS.copy()

    def save_config(self) -> None:
        """Save driver-division mappings to config file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.driver_colors, f, indent=2)
            logger.debug(f"Saved division config to {self.config_file}")
        except IOError as e:
            logger.error(f"Error saving division config: {e}", exc_info=True)
            print(f"Error saving division config: {e}")

    def get_driver_division(self, driver_info: Dict[str, str]) -> Optional[str]:
        """Get the division assigned to a driver.

        Args:
            driver_info: Dictionary containing driver information (UserID, UserName)

        Returns:
            Division name if assigned, None otherwise
        """
        user_id = driver_info.get('UserID', '')
        user_name = driver_info.get('UserName', '')

        for driver in self.driver_colors['drivers']:
            driver_id = driver.get('id', '')
            if driver_id and driver_id == user_id:
                return driver.get('division')
            if driver.get('name') == user_name:
                return driver.get('division')

        return None

    def set_driver_division(self, driver_info: Dict[str, str], division: str) -> None:
        """Assign a driver to a division or remove assignment.

        Args:
            driver_info: Dictionary containing driver information (UserID, UserName)
            division: Division name to assign ("Default" removes assignment)

        Note:
            Setting division to "Default" removes the driver from the config,
            causing them to display with the default white color.
        """
        user_id = driver_info.get('UserID', '')
        user_name = driver_info.get('UserName', '')

        if 'drivers' not in self.driver_colors:
            self.driver_colors['drivers'] = []

        # Check if driver already has an entry
        existing_entry = None
        for i, driver in enumerate(self.driver_colors['drivers']):
            driver_id = driver.get('id', '')
            driver_name = driver.get('name', '')

            if (user_id and driver_id == user_id) or (user_name and driver_name == user_name):
                existing_entry = i
                break

        if division == "Default":
            # Remove driver from config (they'll get default white color)
            if existing_entry is not None:
                self.driver_colors['drivers'].pop(existing_entry)
        else:
            # Add or update driver's division assignment
            entry = {'division': division}
            if user_id:
                entry['id'] = user_id
            if user_name:
                entry['name'] = user_name

            if existing_entry is not None:
                old_entry = self.driver_colors['drivers'][existing_entry]
                if not user_id and 'id' in old_entry:
                    entry['id'] = old_entry['id']
                if not user_name and 'name' in old_entry:
                    entry['name'] = old_entry['name']
                self.driver_colors['drivers'][existing_entry] = entry
            else:
                self.driver_colors['drivers'].append(entry)

            self.save_config()

    def get_division_color(self, division: Optional[str]) -> str:
        """Get the color hex code for a division.

        Args:
            division: Division name

        Returns:
            Hex color string for the division
        """
        if division and division in self.division_colors:
            return self.division_colors[division]
        return self.division_colors.get("Default", "#FFFFFF")
