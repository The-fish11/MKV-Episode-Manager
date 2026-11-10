import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import online_subtitles


class OnlineSubtitleTests(unittest.TestCase):
    @patch("online_subtitles.urllib.request.urlopen")
    def test_search_by_title_and_season(self, call):
        class Fake:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, n): return json.dumps({"status": True, "subtitles": [
                {"name": "Episode 01", "url": "/subtitle/5-6.zip"}]}).encode()
        call.return_value = Fake()
        result = online_subtitles.search("fake-secret", "Blue Bloods", "tv", season=1)
        self.assertEqual(len(result), 1)
        req = call.call_args.args[0]
        self.assertIn("film_name=Blue+Bloods", req.full_url)
        self.assertIn("season_number=1", req.full_url)
        self.assertNotIn("title_t00.mkv", req.full_url)

    def test_reject_unsafe_urls(self):
        for name in ("https://evil.example/subtitle/x", "//evil.example/steal",
                     "/subtitle/../../etc/passwd", "/subtitle/12?other=secret"):
            with self.assertRaises(ValueError):
                online_subtitles._normalise_subdl_url(name)

    def test_unpacks_safe_text(self):
        buff = io.BytesIO()
        with zipfile.ZipFile(buff, "w") as archive:
            archive.writestr("../danger.srt", "A short subtitle text")
            archive.writestr("image.exe", "NOT A SUBTITLE")
        with tempfile.TemporaryDirectory() as temp:
            files = online_subtitles._save_payload(Path(temp), "movie_1",
                                                    "bundle.zip", buff.getvalue())
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].parent, Path(temp))
            self.assertFalse((Path(temp).parent / "danger.srt").exists())

    @patch("online_subtitles._download", return_value=b"1\\n00:00:01,000 --> 00:00:02,000\\nDistinctive dialogue from the film\\n")
    @patch("online_subtitles.search_with_diagnostics")
    def test_season_pack_expands_episodes(self, search, download):
        search.return_value = {"subtitles": [
            {"name": "Season Pack.zip", "season": 1, "full_season": True,
             "unpack_files": [
                {"name": "Pilot.srt", "episode": 1, "season": 1,
                 "url": "/subtitle/12/file01"},
                {"name": "Second.srt", "episode": 2, "season": 1,
                 "url": "/subtitle/12/file02"}
            ]}
        ], "results": [], "status": "Listings found", "attempts": ["DVD-cover title: listings"]}
        with tempfile.TemporaryDirectory() as temp:
            found = online_subtitles.download_references(
                "fake-secret", "Blue Bloods", "tv", temp, season=1)
            self.assertEqual(len(found["files"]), 2)
            self.assertIn("S01E01", found["files"][0].name)
            self.assertIn("S01E02", found["files"][1].name)
            self.assertTrue(all(p.is_file() for p in found["files"]))


if __name__ == "__main__":
    unittest.main()
