"""SubDL v1 subtitle reference provider.

Searches by the DVD's user-provided movie/series title, not generic MKV filenames.
Downloads are temporary and limited; never include API keys in errors or logs.
The provider requires a user-obtained SubDL API key.
"""
import io
import json
import re
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

API_URL = "https://api.subdl.com/api/v1/subtitles"
DOWNLOAD_HOST = "dl.subdl.com"
MAX_DOWNLOAD = 15 * 1024 * 1024
MAX_UNPACKED = 20 * 1024 * 1024
EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa", ".txt"}

def search(api_key, title, kind, season=None, tmdb_id=None):
    """Search SubDL by title and optional TMDB ID/season, never filename."""
    if not api_key.strip():
        raise ValueError("Enter your own SubDL API key to fetch reference subtitles")
    if not title.strip():
        raise ValueError("Enter the movie or series title printed on the DVD")
    if kind not in {"movie", "tv"}:
        raise ValueError("Invalid media type")
    parameters = {
        "api_key": api_key.strip(), "film_name": title.strip(),
        "type": kind, "languages": "EN", "subs_per_page": 30,
        "unpack": 1,
    }
    if tmdb_id:
        # Prefer selected TMDB identity over ambiguous title, for better candidate selection.
        parameters.pop("film_name")
        parameters["tmdb_id"] = int(tmdb_id)
    if kind == "tv" and season is not None:
        parameters["season_number"] = int(season)
    url = API_URL + "?" + urllib.parse.urlencode(parameters)
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "MKVEpisodeManager/0.4.2"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            data = response.read(2 * 1024 * 1024 + 1)
    except Exception:
        raise RuntimeError("SubDL search failed. Check internet access, credentials and provider availability.") from None
    if len(data) > 2 * 1024 * 1024:
        raise RuntimeError("SubDL search response exceeded size limit")
    try:
        obj = json.loads(data)
    except ValueError:
        raise RuntimeError("SubDL returned an invalid search response") from None
    if obj.get("status") is False:
        raise RuntimeError("SubDL rejected the search. Check your API key and search terms.")
    return obj.get("subtitles", [])[:30]

def _download(path):
    """Allow only provider-relative paths from SubDL, never arbitrary URLs."""
    if not isinstance(path, str) or not path.startswith("/subtitle/"):
        raise ValueError("Untrusted subtitle download path")
    if any(c in path for c in "?#\\"):
        raise ValueError("Invalid subtitle download path")
    if not re.fullmatch(r"/subtitle/[a-zA-Z0-9._/-]+", path) or ".." in path:
        raise ValueError("Invalid subtitle download path")
    url = "https://" + DOWNLOAD_HOST + path
    req = urllib.request.Request(url, headers={"User-Agent": "MKVEpisodeManager/0.4.2"})
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            if urllib.parse.urlparse(response.geturl()).hostname != DOWNLOAD_HOST:
                raise ValueError("Unsafe subtitle download redirect")
            content = response.read(MAX_DOWNLOAD + 1)
    except Exception:
        raise RuntimeError("SubDL subtitle download failed or was blocked") from None
    if len(content) > MAX_DOWNLOAD:
        raise ValueError("Subtitle download exceeds safety limit")
    return content

def _write_reference(folder, prefix, filename, data):
    """Save text references with sanitized names, preventing path traversal."""
    suffix = Path(filename).suffix.lower()
    if suffix not in EXTENSIONS or len(data) > MAX_UNPACKED:
        return []
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", Path(filename).stem)[:65]
    target = folder / (prefix + "_" + safe + suffix)
    target.write_bytes(data)
    return [target]

def _save_payload(folder, prefix, name, payload):
    if not name.lower().endswith(".zip"):
        return _write_reference(folder, prefix, name, payload)
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except (zipfile.BadZipFile, ValueError):
        return []
    paths = []
    total = 0
    with archive:
        for member in archive.infolist():
            if member.is_dir() or Path(member.filename).suffix.lower() not in EXTENSIONS:
                continue
            total += member.file_size
            if total > MAX_UNPACKED or member.file_size > 5 * 1024 * 1024:
                break
            if len(paths) >= 30:
                break
            with archive.open(member) as file:
                data = file.read(member.file_size + 1)
            if len(data) > member.file_size:
                continue
            paths.extend(_write_reference(folder, prefix, member.filename, data))
    return paths

def download_references(api_key, title, kind, destination, season=None, tmdb_id=None):
    """Download a bounded number of candidate subtitle references to a temporary folder."""
    root = Path(destination)
    if not root.is_dir():
        raise ValueError("Temporary reference folder does not exist")
    results = search(api_key, title, kind, season=season, tmdb_id=tmdb_id)
    saved = []
    used = set()
    # TV: prefer separately indexed episode files from season packs.
    candidates = []
    for subtitle in results:
        for unpacked in subtitle.get("unpack_files") or []:
            candidates.append((
                unpacked.get("url"), unpacked.get("name") or "reference.srt",
                unpacked.get("season", subtitle.get("season")),
                unpacked.get("episode", subtitle.get("episode")),
            ))
        if not subtitle.get("unpack_files"):
            candidates.append((subtitle.get("url"), subtitle.get("name") or "reference.zip",
                               subtitle.get("season"), subtitle.get("episode")))
    for path, name, s, e in candidates:
        if not path or path in used or len(saved) >= 90:
            continue
        used.add(path)
        prefix = "S{:02d}E{:02d}".format(int(s or 0), int(e or 0)) if kind == "tv" else "movie"
        prefix = prefix + "_" + str(len(used)).zfill(3)
        try:
            payload = _download(path)
            saved.extend(_save_payload(root, prefix, name, payload))
        except (ValueError, OSError, RuntimeError, zipfile.BadZipFile):
            continue
        if len(used) >= 25:
            break
    return saved
