"""HTTP validator metadata for remotely managed JSON cache files."""

import json
import os
import tempfile
from typing import Any, Mapping


METADATA_SUFFIX = ".metadata.json"


def get_cache_metadata_path(cache_path: str) -> str:
    """Return the sidecar path used for remote HTTP validators."""
    return f"{cache_path}{METADATA_SUFFIX}"


def load_conditional_headers(cache_path: str, url: str) -> dict[str, str]:
    """Load conditional request headers for a cache known to match ``url``."""
    if not os.path.exists(cache_path):
        return {}

    try:
        with open(get_cache_metadata_path(cache_path), 'r', encoding='utf-8') as metadata_file:
            metadata = json.load(metadata_file)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}

    if not isinstance(metadata, dict) or metadata.get('url') != url:
        return {}

    headers: dict[str, str] = {}
    etag = metadata.get('etag')
    last_modified = metadata.get('last_modified')
    if isinstance(etag, str) and etag:
        headers['If-None-Match'] = etag
    if isinstance(last_modified, str) and last_modified:
        headers['If-Modified-Since'] = last_modified
    return headers


def save_response_metadata(
    cache_path: str,
    url: str,
    response_headers: Mapping[str, Any],
) -> bool:
    """Atomically persist the remote validators from a successful response."""
    metadata = {'url': url}
    etag = response_headers.get('ETag')
    last_modified = response_headers.get('Last-Modified')
    if isinstance(etag, str) and etag:
        metadata['etag'] = etag
    if isinstance(last_modified, str) and last_modified:
        metadata['last_modified'] = last_modified
    return _atomic_write_json(get_cache_metadata_path(cache_path), metadata)


def _atomic_write_json(target_file: str, data: Any) -> bool:
    """Write JSON through a same-directory temporary file and replace atomically."""
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
    except (OSError, TypeError, ValueError):
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        return False
