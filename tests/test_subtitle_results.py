import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import subtitle_results


class SubtitleResultsTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "status": "Supported subtitle comparison candidate — manual review required",
            "tracks": [
                {"index": 4, "language": "eng", "codec": "dvd_subtitle",
                 "status": "Image subtitle — OCR needed", "cue_count": 0},
            ],
            "online_reference_status": "17 reference file(s) downloaded",
            "online_reference_count": 17,
            "online_reference_attempts": ["TMDB ID: 1 title, 30 subtitle listings"],
            "online_download_attempt_count": 15,
            "online_download_diagnostics": {"Downloaded": 17},
            "ocr_status": "Cached English OCR transcript reused — no new OCR",
            "ocr_cached": True,
            "ocr_cue_count": 1974,
            "top_matches": [
                {"name": "Flight_2012_1080p", "score": 89.4,
                 "matching_windows": 2514, "matching_cues": 1282,
                 "supported": True}
            ]
        }

    def test_compact_summary_shows_supported_match(self):
        summary = subtitle_results.summary(self.report)
        self.assertIn("match found", summary["heading"])
        self.assertEqual(summary["cues"], 1974)
        self.assertEqual(summary["references"], 17)
        self.assertTrue(summary["cached"])
        self.assertEqual(summary["match"]["score"], 89.4)
        self.assertIn("not proof", summary["explanation"])
        self.assertIn("No filename has been approved", summary["notice"])

    def test_full_diagnostics_preserves_technical_details(self):
        details = subtitle_results.diagnostics_text(self.report)
        self.assertIn("Reference downloads attempted: 15", details)
        self.assertIn("17 × Downloaded", details)
        self.assertIn("Stream 4: eng / dvd_subtitle", details)
        self.assertIn("score 89.4%", details)
        self.assertIn("2514 matching 5-word windows", details)
        self.assertIn("Cached English OCR transcript reused", details)

    def test_unverified_result_is_clear(self):
        self.report["top_matches"] = []
        self.report["online_reference_count"] = 0
        self.report["online_reference_status"] = "No references downloaded"
        summary = subtitle_results.summary(self.report)
        self.assertIn("No supported", summary["heading"])
        self.assertIsNone(summary["match"])
        self.assertIn("No references downloaded", summary["explanation"])

    def test_weak_match_is_not_reported_as_supported(self):
        self.report["top_matches"][0]["supported"] = False
        summary = subtitle_results.summary(self.report)
        self.assertIn("not yet supported", summary["heading"])
        self.assertFalse(summary["match"]["supported"])

if __name__ == "__main__":
    unittest.main()
