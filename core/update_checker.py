"""Update checking functionality for the League Overlay application.

This module provides a clean interface for checking for application updates from GitHub.
It handles version comparison and error handling, making it easy to integrate into any application.
"""

import json
import urllib.request
from typing import Dict, Any
from packaging import version

from config.logging_config import get_logger

logger = get_logger(__name__)


class UpdateChecker:
    """Checks for application updates from GitHub releases.

    This class encapsulates all update-checking logic, making it:
    - Testable (can mock GitHub API)
    - Reusable (can be used in other projects)
    - Extensible (can add other update sources)

    Example:
        checker = UpdateChecker(
            "https://api.github.com/repos/user/repo",
            "1.0.0"
        )
        result = checker.check_for_update()
        if result['update_available']:
            print(f"New version: {result['latest_version']}")
    """

    def __init__(self, repo_api_url: str, current_version: str, timeout: int = 5):
        """Initialize the update checker.

        Args:
            repo_api_url: GitHub API URL for the repository
                         (e.g., "https://api.github.com/repos/user/repo")
            current_version: Current version of the application (e.g., "1.0.0")
            timeout: Timeout in seconds for API requests (default: 5)
        """
        self.repo_api_url = repo_api_url.rstrip('/')
        self.current_version = current_version
        self.timeout = timeout

    def check_for_update(self) -> Dict[str, Any]:
        """Check if a newer version is available.

        Returns:
            Dictionary with update information:
            {
                'update_available': bool,
                'latest_version': str,
                'current_version': str,
                'download_url': str,
                'error': str (only present if an error occurred)
            }
        """
        try:
            latest_version = self._fetch_latest_version()
            download_url = self._fetch_download_url()

            update_available = version.parse(latest_version) > version.parse(self.current_version)

            if update_available:
                logger.info(f"Update available: {latest_version} (current: {self.current_version})")
            else:
                logger.info(f"No update available. Current version {self.current_version} is up to date")

            return {
                'update_available': update_available,
                'latest_version': latest_version,
                'current_version': self.current_version,
                'download_url': download_url
            }
        except Exception as e:
            logger.warning(f"Failed to check for updates: {e}")
            return {
                'update_available': False,
                'latest_version': self.current_version,
                'current_version': self.current_version,
                'download_url': '',
                'error': str(e)
            }

    def _fetch_latest_version(self) -> str:
        """Fetch the latest version from GitHub releases.

        Returns:
            Latest version string (e.g., "1.2.3")

        Raises:
            Exception: If API request fails or data is invalid
        """
        url = f"{self.repo_api_url}/releases/latest"
        data = self._fetch_github_data(url)

        # Remove 'v' prefix if present
        latest = data['tag_name'].lstrip('v')
        return latest

    def _fetch_download_url(self) -> str:
        """Fetch the download URL for the latest release.

        Returns:
            URL to the latest release page

        Raises:
            Exception: If API request fails or data is invalid
        """
        url = f"{self.repo_api_url}/releases/latest"
        data = self._fetch_github_data(url)
        return data.get('html_url', '')

    def _fetch_github_data(self, url: str) -> Dict[str, Any]:
        """Fetch and parse JSON data from GitHub API.

        Args:
            url: GitHub API URL to fetch

        Returns:
            Parsed JSON data as dictionary

        Raises:
            Exception: If request fails or response is not valid JSON
        """
        with urllib.request.urlopen(url, timeout=self.timeout) as response:
            data = json.loads(response.read().decode())
            return data

    def get_current_version(self) -> str:
        """Get the current version.

        Returns:
            Current version string
        """
        return self.current_version

    def set_timeout(self, timeout: int) -> None:
        """Set the timeout for API requests.

        Args:
            timeout: Timeout in seconds
        """
        self.timeout = timeout
