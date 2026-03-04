"""Tests for official league metadata parsing."""

from config.official_leagues import _leagues_from_dicts


class TestOfficialLeagueMetadata:
    """Validate optional title/logo handling for official leagues."""

    def test_parses_title_and_logo_fields(self):
        leagues = _leagues_from_dicts([
            {
                "name": "BWRL GT3 Sprint",
                "path": "bwrl/broken_wing_gt3.json",
                "title": "Broken Wing GT3 Sprint",
                "description": "Broken Wing Racing League Sunday Night GT3",
                "logo": "https://bwrl.net/_nuxt/bwrl-logo.DjQE3-f5.png",
                "cache_file": "cache_broken_wing_gt3.json"
            }
        ])

        assert len(leagues) == 1
        assert leagues[0].title == "Broken Wing GT3 Sprint"
        assert leagues[0].logo == "https://bwrl.net/_nuxt/bwrl-logo.DjQE3-f5.png"

    def test_missing_title_and_logo_remain_none(self):
        leagues = _leagues_from_dicts([
            {
                "name": "BWRL GT3 Sprint",
                "path": "bwrl/broken_wing_gt3.json",
                "description": "Broken Wing Racing League Sunday Night GT3",
                "cache_file": "cache_broken_wing_gt3.json"
            }
        ])

        assert len(leagues) == 1
        assert leagues[0].title is None
        assert leagues[0].logo is None
