import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import subtitle_match


def test_lines():
    return [
        "The following morning we traveled toward the mountains before sunrise",
        "I recognized the faded blue sign standing beside the empty bridge",
        "The captain told everyone to abandon the northern railway station",
        "Nobody remembered who had hidden the silver key beneath the staircase",
        "They finally discovered a letter inside the old abandoned lighthouse",
        "The children waited until the last train crossed the river",
        "A storm was approaching and the wooden door refused to close",
        "We cannot leave without checking the lantern inside the tower",
    ]


class SubtitleTests(unittest.TestCase):
    def test_srt_parsing_strips_index_time_and_html(self):
        text = ("1\n00:00:01,100 --> 00:00:04,300\n"
                "<i>The following morning we traveled toward the mountains before sunrise</i>\n\n"
                "2\n00:00:05,100 --> 00:00:07,500\n[Music]\n"
                "A storm was approaching and the wooden door refused to close")
        cues = subtitle_match.cues(text)
        self.assertEqual(len(cues), 2)
        self.assertTrue(cues[0].startswith("the following morning"))
        self.assertNotIn("00", cues[0])

    def test_vtt_and_ass(self):
        vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.500\nA storm was approaching and the wooden door refused to close"
        self.assertEqual(len(subtitle_match.cues(vtt, ".vtt")), 1)
        ass = ("[Events]\n"
               "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,"
               "{\\i1}Nobody remembered who had hidden the silver key beneath the staircase")
        self.assertEqual(len(subtitle_match.cues(ass, ".ass")), 1)

    def test_multiline_matching_and_unrelated(self):
        expected = test_lines()
        observed = expected + ["This additional scene is not present in the reference"]
        matched = subtitle_match.compare_dialogue(observed, expected)
        self.assertTrue(matched["supported"])
        self.assertGreaterEqual(matched["matching_windows"], 25)
        unrelated = [
            "A telescope was fixed inside the small museum building near the harbour",
            "The artist quietly rearranged the paintings along the western corridor",
            "Our teacher decided to purchase a collection of ancient musical instruments",
        ]
        self.assertFalse(subtitle_match.compare_dialogue(unrelated, expected)["supported"])
        self.assertFalse(subtitle_match.compare_dialogue(
            ["I don't know what you mean", "I don't know what you mean", "I don't know what you mean"],
            expected)["supported"])

    def test_candidate_ranking(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            def write(name, lines):
                content = "\n\n".join(
                    f"{i}\n00:00:{i:02},000 --> 00:00:{i:02},900\n{line}"
                    for i, line in enumerate(lines))
                (p / name).write_text(content, encoding="utf-8")
            write("correct.srt", test_lines())
            write("other.srt", [
                "The starship arrived near a distant planet during the evening",
                "The engineer calculated the temperature inside the damaged engine",
                "I found a strange object hidden among the scattered metal parts",
            ])
            results = subtitle_match.rank_references(test_lines(), p)
            self.assertEqual(results[0]["name"], "correct")
            self.assertTrue(results[0]["supported"])
            self.assertFalse(results[-1]["supported"])

    @patch("subtitle_match.subprocess.run")
    def test_probe_image_based_streams_are_flagged(self, fake):
        fake.return_value.stdout = json.dumps({"streams": [
            {"index": 0, "codec_type": "video", "codec_name": "mpeg2video"},
            {"index": 2, "codec_type": "subtitle", "codec_name": "dvd_subtitle",
             "tags": {"language": "eng"}, "disposition": {"forced": 0}},
            {"index": 3, "codec_type": "subtitle", "codec_name": "subrip",
             "tags": {"language": "eng"}, "disposition": {"forced": 0}},
        ]})
        tracks = subtitle_match.probe_subtitles("title_t00.mkv")
        self.assertEqual(len(tracks), 2)
        self.assertTrue(tracks[0]["needs_ocr"])
        self.assertFalse(tracks[1]["needs_ocr"])
        self.assertEqual(tracks[1]["index"], 3)

    @patch("subtitle_match.probe_subtitles")
    def test_image_only_video_is_unverified(self, fake):
        fake.return_value = [{"index": 2, "codec": "dvd_subtitle", "language": "eng",
                              "text_supported": False, "needs_ocr": True}]
        outcome = subtitle_match.analyse_file("title_t00.mkv")
        self.assertIn("OCR", outcome["status"])
        self.assertFalse(outcome["verified"])
        self.assertEqual(outcome["top_matches"], [])


if __name__ == "__main__":
    unittest.main()
