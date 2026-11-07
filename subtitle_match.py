"""Read-only MKV subtitle inventory, text extraction and evidence-based reference matching.

This module never edits the source MKV. References are user-supplied local subtitle
files (.srt/.vtt/.ass/.ssa/.txt); no copyrighted subtitles are redistributed.
Image-based DVD VobSub / Blu-ray PGS streams are flagged for optional future OCR.
"""
import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

TEXT_CODECS = {"subrip", "srt", "ass", "ssa", "webvtt", "text", "mov_text"}
REFERENCE_EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa", ".txt"}
WORD = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")
TIMESTAMP = re.compile(r"^\s*(?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{1,3}\s*-->")
ASS_PREFIX = re.compile(r"^Dialogue:\s*", re.I)
ASS_OVERRIDE = re.compile(r"\{\\[^}]*\}")
TAG = re.compile(r"<[^>]+>")

def probe_subtitles(path):
    """Return subtitle streams with absolute ffprobe indexes (0:<index> for ffmpeg)."""
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=35, check=True)
        obj = json.loads(p.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise RuntimeError("Cannot inspect subtitles; install FFmpeg/FFprobe and check the MKV.") from exc
    result = []
    for stream in obj.get("streams", []):
        if stream.get("codec_type") != "subtitle":
            continue
        codec = stream.get("codec_name", "").lower()
        tags = stream.get("tags") or {}
        disposition = stream.get("disposition") or {}
        result.append({
            "index": int(stream["index"]),
            "codec": codec,
            "language": tags.get("language", "und"),
            "title": tags.get("title", ""),
            "forced": bool(disposition.get("forced")),
            "hearing_impaired": bool(disposition.get("hearing_impaired")),
            "text_supported": codec in TEXT_CODECS,
            "needs_ocr": codec not in TEXT_CODECS,
        })
    return result

def extract_text_track(mkv, stream_index, destination):
    """Extract one already-detected text subtitle stream to a temporary SRT file."""
    out = Path(destination)
    if out.suffix.lower() != ".srt":
        raise ValueError("Extraction output must be .srt")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
           "-i", str(mkv), "-map", "0:" + str(int(stream_index)),
           "-vn", "-an", "-c:s", "srt", "-y", str(out)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Subtitle extraction unavailable; check FFmpeg installation.") from exc
    if result.returncode or not out.is_file() or not out.stat().st_size:
        raise RuntimeError("Could not extract this subtitle stream as text.")
    return out

def cues(text, extension=".srt"):
    """Normalize supported subtitle formats to dialogue lines; strip timing and markup."""
    ext = extension.lower()
    found = []
    for raw in text.lstrip("\ufeff").splitlines():
        line = raw.strip()
        if not line:
            continue
        if ext in (".ass", ".ssa"):
            if not ASS_PREFIX.match(line):
                continue
            parts = line.split(",", 9)
            if len(parts) != 10:
                continue
            line = parts[-1].replace("\\N", " ").replace("\\n", " ")
            line = ASS_OVERRIDE.sub("", line)
        else:
            if line.isdigit() or line.upper() in {"WEBVTT", "NOTE"} or TIMESTAMP.match(line):
                continue
            if line.startswith(("STYLE", "REGION", "Kind:", "Language:")):
                continue
            if "-->" in line:
                continue
        line = TAG.sub("", line)
        line = re.sub(r"\{\\[^}]+\}", "", line)
        line = re.sub(r"\[[^\]]{1,55}\]", " ", line)
        words = WORD.findall(line.lower())
        if len(words) >= 4:
            found.append(" ".join(words))
    return found

def read_reference(path):
    p = Path(path)
    if p.suffix.lower() not in REFERENCE_EXTENSIONS:
        raise ValueError("Not a supported subtitle reference file")
    if p.stat().st_size > 15 * 1024 * 1024:
        raise ValueError("Reference file exceeds 15 MB limit")
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    return cues(text, p.suffix)

def shingles(lines, width=5):
    """Five-word windows; use each cue individually to avoid crossing scene boundaries."""
    out = set()
    for line in lines:
        tokens = WORD.findall(line)
        for i in range(len(tokens) - width + 1):
            out.add(tuple(tokens[i:i + width]))
    return out

def compare_dialogue(source_lines, reference_lines):
    """A conservative overlap *score*, never a calibrated probability of correctness.

    Require at least three separately matching dialogue cues and 25 shared distinct
    5-word windows; reject short/common-phrase coincidences.
    """
    left = shingles(source_lines)
    right = shingles(reference_lines)
    shared = left & right
    matching_cues = sum(bool(shingles([line]) & shared) for line in source_lines)
    if len(shared) < 25 or matching_cues < 3 or not left or not right:
        return {"score": 0, "supported": False,
                "matching_cues": matching_cues, "matching_windows": len(shared)}
    coverage = len(shared) / max(1, min(len(left), len(right)))
    # A heuristic overlap measure, never label it "accuracy" or "confidence %".
    return {"score": round(coverage * 100, 1), "supported": True,
            "matching_cues": matching_cues, "matching_windows": len(shared)}

def rank_references(source_lines, folder):
    """Compare against .srt/.vtt/.ass/.ssa/.txt references in one selected folder."""
    root = Path(folder)
    if not root.is_dir():
        raise ValueError("Select an existing folder containing reference subtitles")
    paths = sorted(p for p in root.rglob("*") if p.is_file()
                   and p.suffix.lower() in REFERENCE_EXTENSIONS)[:300]
    results = []
    for p in paths:
        try:
            ref = read_reference(p)
            evidence = compare_dialogue(source_lines, ref)
            results.append({"reference": str(p), "name": p.stem, **evidence})
        except (OSError, ValueError):
            continue
    return sorted(results, key=lambda item: (item["supported"], item["score"],
                                               item["matching_windows"]), reverse=True)

def ocr_image_subtitles(mkv, folder):
    """Optional local OCR of MKV PGS/VobSub using Subtitle Edit seconv + Tesseract.

    The supported seconv CLI extracts MKV subtitle tracks and OCRs image tracks
    into temporary SRT files. This requires compatible tools installed on PATH.
    No source media is changed.
    """
    exe = shutil.which("seconv")
    tess = shutil.which("tesseract")
    if not exe or not tess:
        raise RuntimeError("Image subtitle OCR needs Subtitle Edit seconv and Tesseract installed on PATH")
    output = Path(folder)
    output.mkdir(parents=True, exist_ok=True)
    cmd = [exe, str(mkv), "subrip",
           "--ocr-engine:tesseract", "--ocr-language:eng",
           "--output-folder:" + str(output), "--overwrite"]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Subtitle OCR did not finish; check seconv and Tesseract installations") from exc
    files = sorted(output.glob("*.srt"))
    if run.returncode != 0 or not files:
        raise RuntimeError("Subtitle OCR could not read this disc's image subtitle tracks")
    return [p for p in files if p.stat().st_size <= 15 * 1024 * 1024]


def analyse_file(mkv, references_dir=None, online=None):
    """Inventory all streams; extract each supported track in a temporary folder."""
    tracks = probe_subtitles(mkv)
    report = {"source": str(mkv), "tracks": [], "top_matches": [],
              "status": "No usable text subtitle evidence", "verified": False}
    with tempfile.TemporaryDirectory(prefix="mkv_subtitles_") as temporary:
        if online:
            import online_subtitles
            online_folder = Path(temporary) / "references"
            online_folder.mkdir()
            try:
                downloaded = online_subtitles.download_references(
                    online["key"], online["title"], online["kind"], online_folder,
                    season=online.get("season"), tmdb_id=online.get("tmdb_id"))
                references_dir = online_folder
                report["online_reference_count"] = len(downloaded)
                report["online_reference_status"] = (
                    str(len(downloaded)) + " online subtitle files retrieved"
                    if downloaded else "No online subtitle references found")
            except (RuntimeError, ValueError) as exc:
                report["online_reference_count"] = 0
                report["online_reference_status"] = str(exc)
        for stream in tracks:
            current = dict(stream)
            if not stream["text_supported"]:
                current["status"] = "Image subtitle — OCR needed"
            else:
                try:
                    extracted = extract_text_track(
                        mkv, stream["index"],
                        Path(temporary) / ("subtitle_" + str(stream["index"]) + ".srt"))
                    lines = read_reference(extracted)
                    current["cue_count"] = len(lines)
                    current["status"] = "Text extracted" if lines else "No usable dialogue"
                    if lines and references_dir:
                        current["matches"] = rank_references(lines, references_dir)[:5]
                        for match in current["matches"]:
                            report["top_matches"].append({
                                "subtitle_index": stream["index"],
                                "language": stream["language"], **match})
                except RuntimeError:
                    current["status"] = "Text extraction failed"
            report["tracks"].append(current)
        if any(t.get("needs_ocr") for t in report["tracks"]):
            ocr_dir = Path(temporary) / "ocr"
            try:
                ocr_files = ocr_image_subtitles(mkv, ocr_dir)
                report["ocr_status"] = str(len(ocr_files)) + " OCR subtitle files produced"
                for ocr_file in ocr_files:
                    lines = read_reference(ocr_file)
                    if not lines:
                        continue
                    if references_dir:
                        for match in rank_references(lines, references_dir)[:5]:
                            report["top_matches"].append({
                                "subtitle_index": None, "language": "eng",
                                "extraction_method": "OCR", **match})
            except RuntimeError as exc:
                report["ocr_status"] = str(exc)
    report["top_matches"].sort(key=lambda m: (m["supported"], m["score"]), reverse=True)
    report["top_matches"] = report["top_matches"][:8]
    if report["top_matches"] and report["top_matches"][0]["supported"]:
        report["status"] = "Subtitle candidate match found — human review required"
    elif any(t.get("status") == "Text extracted" for t in report["tracks"]):
        report["status"] = "Dialogue extracted; no supported reference match"
    elif any(t["needs_ocr"] for t in report["tracks"]):
        report["status"] = "Image subtitles detected; see OCR status and reference-match evidence"
    return report
