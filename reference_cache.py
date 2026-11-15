"""Bounded local cache of SubDL reference subtitle downloads.

Only downloads made using the user's own API key are cached, scoped to that key.
The key itself, signed URLs, and provider response metadata are never written.
Cached payloads are used for the same authenticated SubDL reference on later runs.
The cache is local, temporary in lifetime, and may be cleared independently.
"""
import hashlib
import os
import time
import urllib.parse
from pathlib import Path

MAX_AGE_SECONDS = 30 * 24 * 60 * 60
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_ITEM_BYTES = 15 * 1024 * 1024
CACHE_DIRECTORY = "reference_cache"


def cache_dir():
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "MKVEpisodeManager" / CACHE_DIRECTORY
    return Path.home() / ".cache" / "MKVEpisodeManager" / CACHE_DIRECTORY


def _entry_path(link, api_key):
    """Make an opaque account-scoped key: never save URLs or API credentials."""
    if not api_key or not isinstance(link, str):
        raise ValueError("Missing user credentials or reference URL")
    parsed = urllib.parse.urlsplit(link)
    # Signed download URLs may contain api_key. URL path identifies the file.
    if parsed.scheme and parsed.hostname != "dl.subdl.com":
        raise ValueError("Unsupported reference host")
    canonical = parsed.path if parsed.scheme else link.split("?", 1)[0]
    if not canonical.startswith("/subtitle/"):
        raise ValueError("Invalid reference path")
    hashed = hashlib.sha256(
        (hashlib.sha256(api_key.encode("utf-8")).hexdigest() + "\\0" + canonical).encode("utf-8")
    ).hexdigest()
    return cache_dir() / (hashed + ".bin")


def load(link, api_key):
    try:
        path = _entry_path(link, api_key)
        if path.is_symlink() or not path.is_file():
            return None
        stat = path.stat()
        if (stat.st_size <= 0 or stat.st_size > MAX_ITEM_BYTES or
                time.time() - stat.st_mtime > MAX_AGE_SECONDS):
            return None
        return path.read_bytes()
    except (OSError, ValueError):
        return None


def store(link, api_key, payload):
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_ITEM_BYTES:
        return False
    try:
        path = _entry_path(link, api_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.is_symlink():
            return False
        temporary = path.with_suffix(".tmp")
        if temporary.is_symlink():
            return False
        temporary.write_bytes(payload)
        temporary.replace(path)
        prune()
        return True
    except (OSError, ValueError):
        return False


def prune():
    """Remove expired entries and keep the cache within a conservative size bound."""
    root = cache_dir()
    if not root.is_dir():
        return 0
    now = time.time()
    files = []
    removed = 0
    for path in root.glob("*.bin"):
        if path.is_symlink():
            continue
        try:
            st = path.stat()
            if now - st.st_mtime > MAX_AGE_SECONDS or st.st_size > MAX_ITEM_BYTES:
                path.unlink()
                removed += 1
            else:
                files.append((st.st_mtime, st.st_size, path))
        except OSError:
            continue
    total = sum(size for _, size, _ in files)
    for _, size, path in sorted(files):
        if total <= MAX_TOTAL_BYTES:
            break
        try:
            path.unlink()
            total -= size
            removed += 1
        except OSError:
            pass
    return removed


def clear():
    """Delete downloaded reference cache, not MKVs or the user's OCR cache."""
    root = cache_dir()
    if not root.is_dir():
        return 0
    removed = 0
    for path in root.glob("*.bin"):
        if path.is_symlink():
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed
