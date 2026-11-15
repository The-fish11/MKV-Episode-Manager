"""Readable subtitle-analysis summary and full technical diagnostics.

Pure formatting helpers: do not mutate the report, original MKV or approvals.
"""


def summary(report):
    matches = report.get("top_matches") or []
    supported = [match for match in matches if match.get("supported")]
    best = supported[0] if supported else (matches[0] if matches else None)
    references = report.get("online_reference_count", 0)
    cues = report.get("ocr_cue_count", 0)
    if supported:
        heading = "Dialogue match found — review required"
        explanation = ("The extracted dialogue overlaps with an online subtitle reference. "
                       "This is supporting evidence, not proof of the movie or episode.")
    elif matches:
        heading = "Possible dialogue matches — not yet supported"
        explanation = ("Some reference dialogue overlaps, but the match does not meet the "
                       "current evidence threshold. Verify the content manually.")
    elif report.get("online_rate_limited") and not references:
        heading = "SubDL daily limit reached — comparison unavailable"
        explanation = ("English dialogue is ready, but SubDL blocked additional downloads. "
                       "The available reference cache had no suitable files. "
                       "Retry later without re-running OCR.")
    elif not references and report.get("online_listing_count"):
        heading = "Reference subtitles unavailable — comparison not run"
        explanation = report.get("online_reference_status") or "No references could be retrieved."
    else:
        heading = "No supported dialogue match"
        explanation = (report.get("online_reference_status") or
                       "No matching reference dialogue is available.")
    result = {
        "heading": heading,
        "explanation": explanation,
        "references": references,
        "cached_references": report.get("online_cached_reference_count", 0),
        "rate_limited": bool(report.get("online_rate_limited")),
        "cues": cues,
        "track_count": len(report.get("tracks") or []),
        "cached": bool(report.get("ocr_cached")),
        "match": None,
        "notice": "Manual review is required. No filename has been approved automatically.",
    }
    if best:
        result["match"] = {
            "name": best.get("name", "Unnamed subtitle reference"),
            "score": best.get("score", 0),
            "supported": bool(best.get("supported")),
            "windows": best.get("matching_windows", 0),
            "cues": best.get("matching_cues", 0),
        }
    return result


def diagnostics_text(report):
    """Retain all details previously displayed in Subtitle analysis results."""
    lines = [report.get("status", "Unknown analysis status"), "",
             f'Embedded subtitle streams: {len(report.get("tracks") or [])}']
    if "online_reference_status" in report:
        lines.extend(["Online subtitle reference search:",
                      report["online_reference_status"], ""])
        for attempt in report.get("online_reference_attempts", []):
            lines.append(" - " + attempt)
        if "online_download_attempt_count" in report:
            lines.append("Reference downloads attempted: " +
                         str(report["online_download_attempt_count"]))
            lines.append("Downloaded references reused from cache: " +
                         str(report.get("online_cached_reference_count", 0)))
            if report.get("online_rate_limited"):
                lines.append("SubDL rate limit reached — remaining downloads stopped")
            for reason, count in sorted(
                    report.get("online_download_diagnostics", {}).items()):
                lines.append(" - " + str(count) + " × " + reason)
    if "ocr_status" in report:
        lines.extend(["Image subtitle OCR:", report["ocr_status"],
                      "OCR dialogue cues: " + str(report.get("ocr_cue_count", 0)), ""])
    for track in report.get("tracks", []):
        lines.append(
            f'Stream {track["index"]}: {track["language"]} / {track["codec"]} '
            f'— {track["status"]} ({track.get("cue_count", 0)} dialogue cues)')
    if report.get("top_matches"):
        lines.extend(["", "Reference subtitle matches "
                      "(heuristic overlap, NOT probability of correctness):"])
        for match in report["top_matches"][:5]:
            lines.append(
                f'{match["name"]}: score {match["score"]}% | '
                f'{match["matching_windows"]} matching 5-word windows | '
                f'{match["matching_cues"]} matching cues | '
                f'{"supported" if match["supported"] else "insufficient evidence"}')
    else:
        lines.extend(["", "No supported content match. Movie/episode is unverified."])
    lines.extend(["", "Candidate matches require your review. "
                  "No filename has been approved automatically."])
    return "\n".join(lines)
