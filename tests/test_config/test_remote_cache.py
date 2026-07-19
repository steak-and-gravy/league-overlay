"""Tests for HTTP validator sidecars used by remote JSON caches."""

import json

from config.remote_cache import (
    get_cache_metadata_path,
    load_conditional_headers,
    save_response_metadata,
)


def test_response_metadata_round_trip_builds_conditional_headers(tmp_path):
    cache_file = tmp_path / "league.json"
    cache_file.write_text(json.dumps({'drivers': []}))
    url = "https://leagueoverlay.com/league_files/test/league.json"

    assert save_response_metadata(
        str(cache_file),
        url,
        {
            'ETag': '"remote-v1"',
            'Last-Modified': 'Sun, 12 Jul 2026 01:00:00 GMT',
        },
    ) is True

    assert load_conditional_headers(str(cache_file), url) == {
        'If-None-Match': '"remote-v1"',
        'If-Modified-Since': 'Sun, 12 Jul 2026 01:00:00 GMT',
    }


def test_conditional_headers_require_matching_url_and_existing_cache(tmp_path):
    cache_file = tmp_path / "league.json"
    metadata_file = get_cache_metadata_path(str(cache_file))
    with open(metadata_file, 'w', encoding='utf-8') as file_obj:
        json.dump({
            'url': 'https://leagueoverlay.com/league_files/test/league.json',
            'etag': '"remote-v1"',
        }, file_obj)

    assert load_conditional_headers(
        str(cache_file),
        'https://leagueoverlay.com/league_files/test/league.json',
    ) == {}

    cache_file.write_text(json.dumps({'drivers': []}))
    assert load_conditional_headers(
        str(cache_file),
        'https://leagueoverlay.com/league_files/different.json',
    ) == {}


def test_invalid_metadata_is_ignored(tmp_path):
    cache_file = tmp_path / "league.json"
    cache_file.write_text(json.dumps({'drivers': []}))
    metadata_file = get_cache_metadata_path(str(cache_file))
    with open(metadata_file, 'w', encoding='utf-8') as file_obj:
        file_obj.write("{invalid json")

    assert load_conditional_headers(
        str(cache_file),
        'https://leagueoverlay.com/league_files/test/league.json',
    ) == {}
