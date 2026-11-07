"""Private local OCR cache. Only derived subtitle text is cached, never original MKVs.

Entries are keyed by resolved source path, file size, modification time and a
sample from the start/end of the media. Cache can be cleared from the app.
"""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

MAX_SRT_SIZE = 15 * 1024 * 1024

def cache_root():
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
    if base:
        return Path(base) / "MKVEpisodeManager" / "subtitle_cache"
    return Path.home() / ".cache" / "MKVEpisodeManager" / "subtitle_cache"

def media_key(source, stream_index):
    path = Path(source).resolve(strict=True)
    stat = path.stat()
    h = hashlib.sha256()
    h.update(json.dumps([str(path), stat.st_size, stat.st_mtime_ns, int(stream_index)],
                        separators=(",", ":")).encode("utf-8"))
    with path.open("rb") as file:
        h.update(file.read(65536))
        if stat.st_size > 65536:
            file.seek(max(0, stat.st_size - 65536))
            h.update(file.read(65536))
    return h.hexdigest()

def load(source, stream_index, destination_root=None):
    root = Path(destination_root) if destination_root is not None else cache_root()
    key = media_key(source, stream_index)
    target = root / (key + ".srt")
    if target.is_symlink() or not target.is_file() or target.stat().st_size > MAX_SRT_SIZE:
        return None
    return target

def store(source, stream_index, srt_path, destination_root=None):
    original = Path(srt_path)
    if not original.is_file() or not 0 < original.stat().st_size <= MAX_SRT_SIZE:
        raise ValueError("OCR produced no usable text or an oversized subtitle")
    root = Path(destination_root) if destination_root is not None else cache_root()
    root.mkdir(parents=True, exist_ok=True)
    key = media_key(source, stream_index)
    target = root / (key + ".srt")
    data = original.read_bytes()
    with tempfile.NamedTemporaryFile(prefix="ocr_", suffix=".tmp", dir=root, delete=False) as f:
        tmp = Path(f.name)
        try:
            if os.name != "nt":
                os.chmod(tmp, 0o600)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return target

def clear(destination_root=None):
    root = Path(destination_root) if destination_root is not None else cache_root()
    if not root.is_dir():
        return 0
    count = 0
    for file in root.iterdir():
        if file.is_file() and not file.is_symlink() and re.fullmatch(r"[0-9a-f]{64}\\.srt", file.name):
            file.unlink()
            count += 1
    return count
