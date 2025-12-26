"""Official league configurations."""

from dataclasses import dataclass


@dataclass
class OfficialLeague:
    """Configuration for an official remotely-managed league."""
    name: str           # Display name in dropdown
    icon: str          # Emoji or path to icon
    url: str           # Remote URL to fetch config from
    description: str   # Tooltip/description
    cache_file: str    # Local cache filename


OFFICIAL_LEAGUES = [
    OfficialLeague(
        name="BWRL GT3 Sprint",
        icon="🏁",
        url="https://leagueoverlay.com/league_files/bwrl/broken_wing_gt3.json",
        description="Broken Wing Racing League Sunday Night GT3",
        cache_file="cache_broken_wing_gt3.json"
    )
]


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
