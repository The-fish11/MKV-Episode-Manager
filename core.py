"""Safety-focused, GUI-independent project and copy utilities."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

APP_VERSION = '0.4.0-test'
MODES = ('Complete TV Season', 'Incomplete TV Season', 'Movie')
BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

def clean_name(text):
    return BAD_CHARS.sub('_', str(text)).strip(' .')[:180]

def sha256(path, block=4 * 1024 * 1024):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(block), b''):
            h.update(chunk)
    return h.hexdigest()

def inspect(path):
    p = Path(path)
    data = {'size_bytes': p.stat().st_size, 'duration_seconds': None,
            'video_codec': None, 'width': None, 'height': None,
            'audio_tracks': 0, 'subtitle_tracks': 0, 'inspection_error': None}
    try:
        proc = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                               '-of', 'json', str(p)], capture_output=True, text=True,
                              timeout=30, check=True)
        info = json.loads(proc.stdout)
        duration = info.get('format', {}).get('duration')
        data['duration_seconds'] = round(float(duration), 1) if duration else None
        streams = info.get('streams', [])
        video = next((s for s in streams if s.get('codec_type') == 'video'), {})
        data.update(video_codec=video.get('codec_name'), width=video.get('width'),
                    height=video.get('height'),
                    audio_tracks=sum(s.get('codec_type') == 'audio' for s in streams),
                    subtitle_tracks=sum(s.get('codec_type') == 'subtitle' for s in streams))
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            ValueError, json.JSONDecodeError) as e:
        data['inspection_error'] = str(e)
    return data

def thumbnail(path, output):
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                    '-ss', '00:03:00', '-i', str(path), '-frames:v', '1', '-y',
                    str(output)], check=True, timeout=45)
    return output

def suggested_name(item, mode, series, season):
    if mode == 'Movie':
        title = clean_name(item.get('title') or series)
        year = str(item.get('year', '')).strip()
        return f'{title} ({year}).mkv' if title and re.fullmatch(r'\d{4}', year) else (f'{title}.mkv' if title else '')
    number = item.get('episode')
    try:
        ep = int(number)
        s = int(season)
        if ep < 1 or s < 0: return ''
    except (ValueError, TypeError):
        return ''
    title = clean_name(item.get('title', ''))
    show = clean_name(series)
    if not show: return ''
    return f'{show} - S{s:02d}E{ep:02d}' + (f' - {title}' if title else '') + '.mkv'

def ensure_safe_destination(source_paths, destination):
    dest = Path(destination).resolve()
    if not dest.is_dir(): raise ValueError('Destination must be an existing directory.')
    if dest.is_symlink(): raise ValueError('Symlink destination not allowed.')
    if not source_paths: raise ValueError('No source files.')
    for source in source_paths:
        p = Path(source).resolve(strict=True)
        if p.is_symlink(): raise ValueError('Symlink source not allowed.')
        if dest == p.parent or dest in p.parents:
            raise ValueError('Destination cannot be the source directory or one of its parents.')
        if p.parent == dest or p in dest.parents:
            raise ValueError('Destination cannot be inside the source file tree.')
        # Reject a destination inside the imported source folder (which may be a common parent).
    common = Path(os.path.commonpath([str(Path(x).resolve().parent) for x in source_paths]))
    if dest == common or common in dest.parents:
        raise ValueError('Destination must not be inside the imported source folder.')
    return dest

def verified_copy(source, dest_folder, filename):
    """Never overwrite, copy to exclusive .part, verify, then reserve final name exclusively."""
    source = Path(source).resolve(strict=True)
    dest_folder = Path(dest_folder).resolve(strict=True)
    if not source.is_file() or source.is_symlink(): raise ValueError('Invalid source.')
    if filename != clean_name(filename) or not filename.lower().endswith('.mkv'):
        raise ValueError('Unsafe output filename.')
    if filename in ('.', '..'): raise ValueError('Invalid output filename.')
    target = dest_folder / filename
    if target.exists() or target.is_symlink(): raise FileExistsError(f'Destination already exists: {target}')
    temp = dest_folder / (filename + '.part')
    # Exclusive creation ensures no existing partial transfer is overwritten.
    try:
        with open(source, 'rb') as inp, open(temp, 'xb') as out:
            shutil.copyfileobj(inp, out, 4 * 1024 * 1024)
            out.flush()
            os.fsync(out.fileno())
        source_hash = sha256(source)
        dest_hash = sha256(temp)
        if source_hash != dest_hash:
            raise IOError('SHA-256 mismatch; incomplete copy remains as .part.')
        # Hard link atomically claims the destination without overwriting; same filesystem.
        os.link(temp, target)
        temp.unlink()
        return {'source': str(source), 'destination': str(target),
                'sha256': source_hash, 'bytes': target.stat().st_size, 'verified': True}
    except Exception:
        # Leave any partial copy in place for diagnosis; never touch source.
        raise

def save_project(path, project):
    p = Path(path)
    payload = {'version': APP_VERSION, 'saved_at': time.strftime('%Y-%m-%dT%H:%M:%S'), **project}
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=p.parent,
                                     prefix='.mkv_project_', suffix='.tmp', delete=False) as f:
        tmp = Path(f.name)
        json.dump(payload, f, indent=2)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, p)

def load_project(path):
    with open(path, encoding='utf-8') as f: data = json.load(f)
    if data.get('mode') not in MODES: raise ValueError('Unknown project mode')
    return data

def duplicates(items):
    found, dup = {}, []
    for i, item in enumerate(items):
        p = item['path']
        h = sha256(p)
        if h in found: dup.append((found[h], i))
        else: found[h] = i
    return dup

def missing_episodes(items, mode):
    if mode != 'Complete TV Season': return []
    numbers = set()
    for item in items:
        try:
            n = int(item.get('episode', ''))
            if n > 0: numbers.add(n)
        except (ValueError, TypeError): pass
    if not numbers: return []
    return sorted(set(range(1, max(numbers) + 1)) - numbers)