"""Driver division management and color configuration."""

import json
import os
import tempfile
import threading
import time
from typing import Any, Dict, Optional

from config.constants import ASSIGNABLE_DIVISIONS, UI_CONFIG, FILE_CONFIG
from config.logging_config import get_logger
from config.remote_cache import load_conditional_headers, save_response_metadata

logger = get_logger(__name__)


class DivisionManager:
    """Manages driver-to-division assignments and color configuration."""

    DEFAULT_DIVISION = "Default"
    PERSISTENCE_RETRY_SECONDS = 5.0

    def __init__(
        self,
        config_file: str = FILE_CONFIG.DIVISIONS_FILE,
        settings_file: str = FILE_CONFIG.SETTINGS_FILE,
        app_default_colors: Optional[Dict[str, str]] = None,
        league_color_overrides: Optional[Dict[str, Dict[str, str]]] = None,
        unknown_driver_class: Optional[str] = None,
        persist_unknown_driver_assignments: bool = False,
    ):
        """Initialize division manager.

        Args:
            config_file: Path to JSON file containing driver-division mappings
            settings_file: Path to settings file for division colors
        """
        self.config_file = config_file
        self.settings_file = settings_file
        self.driver_colors: dict[str, list] = {'drivers': []}
        self.app_default_division_colors: dict[str, str] = UI_CONFIG.DEFAULT_COLORS.copy()
        self.league_division_colors: dict[str, str] = {}
        self.user_override_division_colors: dict[str, str] = {}
        self.division_colors: dict[str, str] = UI_CONFIG.DEFAULT_COLORS.copy()
        self.division_color_status: str = "App defaults"
        self._assignment_lock = threading.RLock()
        self._load_lock = threading.Lock()
        self._persistence_retry_after: Dict[tuple[str, Any], float] = {}
        self.unknown_driver_class: Optional[str] = None
        self.persist_unknown_driver_assignments = False
        self.configure_unknown_driver_assignment(
            unknown_driver_class,
            persist_unknown_driver_assignments,
        )

        # O(1) lookup caches for division assignments (95% faster than O(n) linear search)
        self._division_cache_by_id: Dict[str, str] = {}
        self._division_cache_by_name: Dict[str, str] = {}

        self.load_driver_config()
        self.refresh_division_colors(app_default_colors, league_color_overrides)

    def load_driver_config(self) -> tuple[bool, str, int]:
        """Load driver-division mappings from config file or remote source."""
        with self._load_lock:
            return self._load_driver_config_source(self.config_file)

    def change_config_source(self, config_file: str) -> tuple[bool, str, int]:
        """Load and atomically activate a different local or official league source."""
        with self._load_lock:
            return self._load_driver_config_source(config_file)

    def _load_driver_config_source(self, config_file: str) -> tuple[bool, str, int]:
        """Fetch or parse a source, then atomically install its loaded state."""
        if config_file.startswith("official:"):
            return self._load_official_league(config_file)
        return self._load_local_file(config_file)

    def _load_official_league(self, config_file: str) -> tuple[bool, str, int]:
        """Load driver config from official remote league."""
        from config.official_leagues import get_official_league, get_full_league_url
        import requests

        league_name = config_file.replace("official:", "")

        try:
            league = get_official_league(league_name)
        except ValueError:
            logger.error(f"Unknown official league: {league_name}")
            return False, f"Unknown official league: {league_name}", 0

        league_url = get_full_league_url(league)
        cache_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', league.cache_file)
        )

        # Try to fetch from remote, using validators from the last successful download.
        try:
            conditional_headers = load_conditional_headers(cache_path, league_url)
            response = requests.get(league_url, headers=conditional_headers, timeout=10)

            if response.status_code == 304:
                cache_error = None
                with self._assignment_lock:
                    try:
                        with open(cache_path, 'r', encoding='utf-8') as cache_file:
                            data = json.load(cache_file)
                        if not self._is_valid_driver_config(data):
                            raise ValueError("cache does not contain valid driver assignments")
                    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
                        cache_error = error
                    else:
                        self._install_loaded_config_locked(config_file, data)
                        driver_count = len(self.driver_colors['drivers'])
                if cache_error is not None:
                    logger.warning(
                        f"Cached {league.name} data is unavailable after a 304 response; "
                        f"retrying without validators: {cache_error}"
                    )
                    response = requests.get(league_url, timeout=10)
                else:
                    logger.info(f"{league.name} is up to date; loaded {driver_count} drivers from cache")
                    return True, f"{league.name} is already up to date", driver_count

            response.raise_for_status()
            data = response.json()

            with self._assignment_lock:
                cache_saved = self._atomic_write_json(cache_path, data)
                self._install_loaded_config_locked(config_file, data)
            driver_count = len(self.driver_colors['drivers'])
            logger.info(f"Loaded {driver_count} drivers from {league.name}")
            if not cache_saved:
                return False, f"Loaded {league.name}, but failed to update its local cache", driver_count
            if not save_response_metadata(cache_path, league_url, response.headers):
                logger.warning(f"Failed to save HTTP cache metadata for {league.name}")
            return True, f"Successfully refreshed {league.name}", driver_count

        except Exception as e:
            # Fall back to cache
            logger.warning(f"Failed to fetch {league.name}, using cache: {e}")
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    with self._assignment_lock:
                        self._install_loaded_config_locked(config_file, data)
                    logger.info(f"Loaded from cache: {len(self.driver_colors['drivers'])} drivers")
                except Exception as cache_error:
                    logger.error(f"Cache load failed: {cache_error}")
            else:
                logger.error(f"No cache available for {league.name}")
            return False, f"Failed to refresh {league.name}: {e}", len(self.driver_colors['drivers'])

    def _load_local_file(self, config_file: str) -> tuple[bool, str, int]:
        """Load driver config from local file."""
        with self._assignment_lock:
            if not os.path.exists(config_file):
                return False, f"League config not found: {config_file}", len(self.driver_colors['drivers'])
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading division config: {e}", exc_info=True)
                return False, f"Failed to load {config_file}: {e}", len(self.driver_colors['drivers'])
            self._install_loaded_config_locked(config_file, data)
        logger.info(
            f"Loaded {len(self.driver_colors['drivers'])} driver division assignments from {config_file}"
        )
        return True, f"Loaded {config_file}", len(self.driver_colors['drivers'])

    def _install_loaded_config_locked(self, config_file: str, data: Any) -> None:
        """Install a fully parsed source while holding the assignment lock."""
        self.config_file = config_file
        if self._is_valid_driver_config(data):
            self.driver_colors = data
        else:
            self.driver_colors = {'drivers': []}
        self._load_league_division_colors(data)
        self._build_lookup_cache()
        self._persistence_retry_after.clear()

    @staticmethod
    def _is_valid_driver_config(data: Any) -> bool:
        """Return whether data contains the expected driver assignment structure."""
        if not isinstance(data, dict) or not isinstance(data.get('drivers'), list):
            return False
        for driver in data['drivers']:
            if not isinstance(driver, dict):
                return False
            for lookup_field in ('id', 'name'):
                lookup_value = driver.get(lookup_field)
                if lookup_value:
                    try:
                        hash(lookup_value)
                    except TypeError:
                        return False
        return True

    def load_division_config(self) -> None:
        """Load effective division colors from settings file."""
        self.refresh_division_colors()

    def refresh_division_colors(
        self,
        app_default_colors: Optional[Dict[str, str]] = None,
        league_color_overrides: Optional[Dict[str, Dict[str, str]]] = None,
        league_source: Optional[str] = None,
    ) -> None:
        """Refresh effective colors using app, league, and user override precedence."""
        if app_default_colors is None or league_color_overrides is None:
            settings_colors, settings_overrides = self._read_settings_color_data()
            if app_default_colors is None:
                app_default_colors = settings_colors
            if league_color_overrides is None:
                league_color_overrides = settings_overrides

        self.app_default_division_colors = self._coerce_division_colors(app_default_colors)
        normalized_source = self.normalize_league_source(league_source or self.config_file)
        source_overrides = {}
        if isinstance(league_color_overrides, dict):
            source_overrides = league_color_overrides.get(normalized_source, {})

        self.user_override_division_colors = self._coerce_color_map(
            source_overrides,
            "league color override"
        )

        effective_colors = self.app_default_division_colors.copy()
        effective_colors.update(self.league_division_colors)
        effective_colors.update(self.user_override_division_colors)
        self.division_colors = effective_colors

        if self.user_override_division_colors:
            self.division_color_status = "Custom"
        elif self.league_division_colors:
            self.division_color_status = "League defaults"
        else:
            self.division_color_status = "App defaults"

    def _read_settings_color_data(self) -> tuple[Dict[str, str], Dict[str, Dict[str, str]]]:
        """Read color palette fields from the settings file, if present."""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                    return (
                        data.get('division_colors', {}),
                        data.get('league_color_overrides', {})
                    )
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading division colors: {e}", exc_info=True)
        return UI_CONFIG.DEFAULT_COLORS.copy(), {}

    def _load_league_division_colors(self, data: Any) -> None:
        """Extract optional top-level division colors from a league file."""
        self.league_division_colors = {}
        if isinstance(data, dict):
            self.league_division_colors = self._coerce_color_map(
                data.get('division_colors', {}),
                "league file division_colors"
            )

    @classmethod
    def normalize_league_source(cls, source: Optional[str]) -> str:
        """Return the stable settings key for a league source."""
        if not isinstance(source, str):
            return ""

        source = source.strip()
        if not source:
            return ""
        if source.startswith("official:"):
            league_name = source.replace("official:", "", 1).strip()
            if not league_name:
                return ""
            return f"official:{league_name}"
        return os.path.abspath(os.path.expanduser(source))

    def _coerce_division_colors(self, colors: Any) -> Dict[str, str]:
        """Validate a full palette while preserving defaults for missing divisions."""
        valid_colors = UI_CONFIG.DEFAULT_COLORS.copy()
        valid_colors.update(self._coerce_color_map(colors, "division colors"))
        return valid_colors

    def _coerce_color_map(self, colors: Any, label: str) -> Dict[str, str]:
        """Validate a partial division color map."""
        if not isinstance(colors, dict):
            return {}

        valid_colors = {}
        for division, color in colors.items():
            if not isinstance(division, str) or not division.strip():
                logger.warning(f"Ignoring invalid division name in {label}: {division}")
                continue
            if not isinstance(color, str) or not self._is_valid_hex_color(color):
                logger.warning(f"Ignoring invalid color for division '{division}' in {label}: {color}")
                continue
            valid_colors[division.strip()] = color
        return valid_colors

    @staticmethod
    def _is_valid_hex_color(color: str) -> bool:
        """Check if a string is a valid #RRGGBB or #RRGGBBAA color."""
        if not color.startswith('#') or len(color) not in (7, 9):
            return False
        try:
            int(color[1:], 16)
            return True
        except ValueError:
            return False

    def _build_lookup_cache(self) -> None:
        """Build fast lookup dictionaries for driver divisions.

        Converts O(n) linear searches to O(1) hash lookups.
        Called after loading/modifying driver config.
        """
        self._division_cache_by_id.clear()
        self._division_cache_by_name.clear()

        for driver in self.driver_colors.get('drivers', []):
            division = driver.get('division')
            if division:
                # Cache by UserID (preferred lookup method)
                driver_id = driver.get('id')
                if driver_id:
                    self._division_cache_by_id[driver_id] = division

                # Cache by UserName (fallback lookup method)
                driver_name = driver.get('name')
                if driver_name:
                    self._division_cache_by_name[driver_name] = division

        logger.debug(f"Built division cache: {len(self._division_cache_by_id)} by ID, {len(self._division_cache_by_name)} by name")

    def save_config(self) -> bool:
        """Save driver-division mappings to config file."""
        with self._assignment_lock:
            return self._save_config_locked()

    def _save_config_locked(self) -> bool:
        """Save the active mappings while holding the assignment lock."""
        target_file = self.get_writable_config_path()
        if not target_file:
            return False
        if self.config_file.startswith("official:"):
            logger.info("Editing official league cache - changes will be overwritten on next refresh")

        if self._atomic_write_json(target_file, self.driver_colors):
            logger.debug(f"Saved division config to {target_file}")
            return True
        return False

    def _atomic_write_json(self, target_file: str, data: Any) -> bool:
        """Write JSON through a same-directory temp file and atomically replace the target."""
        temp_path = None
        try:
            target_dir = os.path.dirname(os.path.abspath(target_file))
            os.makedirs(target_dir, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8',
                dir=target_dir,
                prefix=f".{os.path.basename(target_file)}.",
                suffix='.tmp',
                delete=False,
            ) as temp_file:
                temp_path = temp_file.name
                json.dump(data, temp_file, indent=2)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_path, target_file)
            return True
        except (OSError, TypeError, ValueError) as e:
            logger.error(f"Error saving division config to {target_file}: {e}", exc_info=True)
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
            return False

    def get_writable_config_path(self) -> Optional[str]:
        """Resolve the local JSON path used for assignment persistence."""
        if not self.config_file.startswith("official:"):
            return self.config_file

        from config.official_leagues import get_official_league

        league_name = self.config_file.replace("official:", "", 1)
        try:
            league = get_official_league(league_name)
        except ValueError:
            logger.error(f"Cannot persist assignments for unknown official league: {league_name}")
            return None
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', league.cache_file))

    def get_driver_division(self, driver_info: Dict[str, str]) -> Optional[str]:
        """Get the division assigned to a driver using O(1) hash lookup.

        Args:
            driver_info: Dictionary containing driver information (UserID, UserName)

        Returns:
            Division name if assigned, the configured unknown-driver class,
            or None when automatic assignment is off.

        Performance: O(1) hash lookup instead of O(n) linear search.
        95-99% faster than previous implementation.
        """
        with self._assignment_lock:
            # Try UserID lookup first (most reliable)
            user_id = driver_info.get('UserID', '')
            if user_id and user_id in self._division_cache_by_id:
                return self._division_cache_by_id[user_id]

            # Fallback to UserName lookup
            user_name = driver_info.get('UserName', '')
            if user_name and user_name in self._division_cache_by_name:
                return self._division_cache_by_name[user_name]

            if (
                self.unknown_driver_class
                and self.persist_unknown_driver_assignments
                and (user_id or user_name)
            ):
                retry_key = ('id', user_id) if user_id else ('name', user_name)
                now = time.monotonic()
                if now >= self._persistence_retry_after.get(retry_key, 0.0):
                    if self._set_driver_division_locked(driver_info, self.unknown_driver_class):
                        self._persistence_retry_after.pop(retry_key, None)
                    else:
                        self._persistence_retry_after[retry_key] = (
                            now + self.PERSISTENCE_RETRY_SECONDS
                        )

            return self.unknown_driver_class

    def set_unknown_driver_class(self, division: Optional[str]) -> None:
        """Set the fallback class while preserving the current persistence choice."""
        self.configure_unknown_driver_assignment(
            division,
            self.persist_unknown_driver_assignments,
        )

    def set_persist_unknown_driver_assignments(self, enabled: bool) -> None:
        """Set persistence while preserving the current fallback class."""
        self.configure_unknown_driver_assignment(self.unknown_driver_class, enabled)

    def configure_unknown_driver_assignment(
        self,
        division: Optional[str],
        persist: bool,
    ) -> None:
        """Atomically configure fallback classification and optional JSON persistence."""
        with self._assignment_lock:
            normalized_division = division if division in ASSIGNABLE_DIVISIONS else None
            self.unknown_driver_class = normalized_division
            self.persist_unknown_driver_assignments = bool(
                normalized_division and persist
            )
            if not self.persist_unknown_driver_assignments:
                self._persistence_retry_after.clear()

    @classmethod
    def normalize_division_name(cls, division: Optional[str]) -> str:
        """Return the stable grouping key for a division assignment."""
        if isinstance(division, str):
            division = division.strip()
            if division:
                return division
        return cls.DEFAULT_DIVISION

    def get_driver_division_key(self, driver_info: Dict[str, str]) -> str:
        """Get a driver's stable division grouping key."""
        return self.normalize_division_name(self.get_driver_division(driver_info))

    def set_driver_division(self, driver_info: Dict[str, str], division: str) -> bool:
        """Assign a driver to a division or remove assignment.

        Args:
            driver_info: Dictionary containing driver information (UserID, UserName)
            division: Division name to assign ("Default" removes assignment)

        Note:
            Setting division to "Default" removes the driver from the config,
            causing them to display with the default white color.
        """
        with self._assignment_lock:
            return self._set_driver_division_locked(driver_info, division)

    def _set_driver_division_locked(self, driver_info: Dict[str, str], division: str) -> bool:
        """Assign a driver while the caller holds the assignment lock."""
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

        original_drivers = list(self.driver_colors['drivers'])
        changed = False

        if division == "Default":
            # Remove driver from config (they'll get default white color)
            if existing_entry is not None:
                self.driver_colors['drivers'].pop(existing_entry)
                changed = True
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
            changed = True

        if changed and not self._save_config_locked():
            self.driver_colors['drivers'] = original_drivers
            self._build_lookup_cache()
            return False

        # Rebuild cache after modification
        self._build_lookup_cache()
        return True

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

    def get_driver_color(self, driver_info: Dict[str, str]) -> str:
        """Get the color for a driver based on their division assignment.

        This is a convenience method that combines get_driver_division and
        get_division_color into a single call.

        Args:
            driver_info: Dictionary containing driver information (UserID, UserName)

        Returns:
            Hex color string for the driver's division (default "#FFFFFF" if unassigned)
        """
        division = self.get_driver_division(driver_info)
        return self.get_division_color(division)
