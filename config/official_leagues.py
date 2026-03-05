"""Official league configurations."""

import json
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

# Configuration for fetching official leagues
OFFICIAL_LEAGUES_BASE_URL = "https://leagueoverlay.com/league_files/"
OFFICIAL_LEAGUES_JSON_URL = "https://leagueoverlay.com/league_files/official.json"
OFFICIAL_LEAGUES_CACHE_FILE = "cache_official_leagues.json"

# Hardcoded fallback league for offline use on first startup
FALLBACK_LEAGUES = [
    {
        "name": "BWRL GT3 Sprint",
        "path": "bwrl/broken_wing_gt3.json",
        "title": "Broken Wing GT3 Sprint",
        "description": "Broken Wing Racing League Sunday Night GT3",
        "logo": "https://bwrl.net/_nuxt/bwrl-logo.DjQE3-f5.png",
        "cache_file": "cache_broken_wing_gt3.json"
    }
]


@dataclass
class OfficialLeague:
    """Configuration for an official remotely-managed league."""
    name: str           # Display name in dropdown
    path: str           # Relative path (e.g., "bwrl/broken_wing_gt3.json")
    title: Optional[str]  # Optional broadcast header title
    description: str    # Tooltip/description
    logo: Optional[str]  # Optional broadcast header logo URL/path
    cache_file: str     # Local cache filename
    icon: str = "🏁"    # Fixed flag emoji for all official leagues


OFFICIAL_LEAGUES: List[OfficialLeague] = []


def _validate_league_dict(league_dict: dict) -> bool:
    """Validate a league dictionary has all required fields with non-empty values.

    Args:
        league_dict: Dictionary to validate

    Returns:
        True if valid, False if any required field is empty/null

    Raises:
        KeyError: If a required field is missing
    """
    required_fields = ["name", "path", "description", "cache_file"]
    for field in required_fields:
        value = league_dict.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            logger.warning(f"Invalid league entry: {field} is empty/null in {league_dict}")
            return False
    return True


def _parse_optional_string(value) -> Optional[str]:
    """Parse optional string field from league JSON."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value if value else None
    return None


def _build_official_league(league_dict: dict) -> OfficialLeague:
    """Build an OfficialLeague from a validated dictionary."""
    return OfficialLeague(
        name=league_dict["name"].strip(),
        path=league_dict["path"].strip(),
        title=_parse_optional_string(league_dict.get("title")),
        description=league_dict["description"].strip(),
        logo=_parse_optional_string(league_dict.get("logo")),
        cache_file=league_dict["cache_file"].strip()
    )


def load_official_leagues_from_json() -> List[OfficialLeague]:
    """Fetch and parse official leagues from remote JSON file.

    Attempts to fetch from OFFICIAL_LEAGUES_JSON_URL, validates entries,
    and constructs full URLs. Falls back to cache if network unavailable.
    If no cache exists, returns hardcoded fallback leagues.

    Returns:
        List of OfficialLeague objects

    Raises:
        Exception: Only on JSON parse errors (not on network errors)
    """
    # Try to load from cache first
    cache_path = os.path.join(os.path.dirname(__file__), "..", OFFICIAL_LEAGUES_CACHE_FILE)
    
    try:
        # Attempt to fetch from remote
        logger.info(f"Fetching official leagues from {OFFICIAL_LEAGUES_JSON_URL}")
        response = requests.get(OFFICIAL_LEAGUES_JSON_URL, timeout=10)
        response.raise_for_status()
        remote_data = response.json()
        
        if not isinstance(remote_data, list):
            logger.error("Official leagues JSON is not a list")
            remote_data = []
        
        # Validate and build league objects
        leagues = []
        for league_dict in remote_data:
            if _validate_league_dict(league_dict):
                league = _build_official_league(league_dict)
                leagues.append(league)
        
        if not leagues:
            logger.warning("No valid leagues in remote JSON, using fallback")
            leagues = _leagues_from_dicts(FALLBACK_LEAGUES)
        else:
            logger.info(f"Loaded {len(leagues)} official leagues from remote")
        
        # Cache the successful response
        try:
            with open(cache_path, 'w') as f:
                json.dump(remote_data, f, indent=2)
            logger.info(f"Cached official leagues to {cache_path}")
        except Exception as e:
            logger.warning(f"Failed to cache official leagues: {e}")
        
        return leagues
        
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch official leagues from remote: {e}")
        
        # Try to load from cache
        try:
            if os.path.exists(cache_path):
                with open(cache_path, 'r') as f:
                    cached_data = json.load(f)
                
                if isinstance(cached_data, list):
                    leagues = []
                    for league_dict in cached_data:
                        if _validate_league_dict(league_dict):
                            league = _build_official_league(league_dict)
                            leagues.append(league)
                    
                    if leagues:
                        logger.info(f"Loaded {len(leagues)} official leagues from cache")
                        return leagues
        except Exception as cache_error:
            logger.warning(f"Failed to load from cache: {cache_error}")
        
        # Fall back to hardcoded list
        logger.info("Using hardcoded fallback official leagues")
        return _leagues_from_dicts(FALLBACK_LEAGUES)
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse official leagues JSON: {e}")
        raise


def _leagues_from_dicts(league_dicts: List[dict]) -> List[OfficialLeague]:
    """Convert list of dictionaries to OfficialLeague objects.

    Args:
        league_dicts: List of league dictionaries

    Returns:
        List of OfficialLeague objects
    """
    leagues = []
    for league_dict in league_dicts:
        if _validate_league_dict(league_dict):
            league = _build_official_league(league_dict)
            leagues.append(league)
    return leagues


def get_official_league(name: str) -> OfficialLeague:
    """Get official league by name.

    Args:
        name: League name (without 'official:' prefix)

    Returns:
        OfficialLeague instance

    Raises:
        ValueError: If league not found
    """
    for league in OFFICIAL_LEAGUES:
        if league.name == name:
            return league
    raise ValueError(f"Official league not found: {name}")


def get_full_league_url(league: OfficialLeague) -> str:
    """Construct full URL for a league config.

    Args:
        league: OfficialLeague object

    Returns:
        Full URL string
    """
    return OFFICIAL_LEAGUES_BASE_URL + league.path
