import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import subtitle_cache
import subtitle_match
import online_subtitles

class CacheTests(unittest.TestCase):
    def test_cache_round_trip_invalidation_and_clear(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            media=root/"title_t00.mkv"
            media.write_bytes(b"fake source mkv content")
            srt=root/"C1_t00.eng.srt"
            srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nLong enough dialogue is visible here.\n")
            cache=root/"cache"
            self.assertIsNone(subtitle_cache.load(media, 4, cache))
            stored=subtitle_cache.store(media, 4, srt, cache)
            self.assertEqual(subtitle_cache.load(media, 4, cache), stored)
            self.assertIsNone(subtitle_cache.load(media, 9, cache))
            self.assertEqual(subtitle_cache.clear(cache),1)
            self.assertIsNone(subtitle_cache.load(media,4,cache))
            subtitle_cache.store(media,4,srt,cache)
            media.write_bytes(b"different source content")
            self.assertIsNone(subtitle_cache.load(media,4,cache))

    @patch("subtitle_match.probe_subtitles")
    @patch("subtitle_match.ocr_image_subtitles")
    def test_cached_ocr_is_reused_without_reprocessing(self, ocr, probe):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            media=root/"disc.mkv"
            media.write_bytes(b"the originally ripped file")
            source=root/"eng.srt"
            source.write_text("1\n00:00:01,000 --> 00:00:04,000\n"
                              "This long opening conversation is present in the movie.\n")
            with patch("subtitle_cache.cache_root",return_value=root/"cache"):
                subtitle_cache.store(media,4,source)
                probe.return_value=[{"index":4,"codec":"dvd_subtitle","language":"eng",
                                     "needs_ocr":True,"text_supported":False,"forced":False}]
                r=subtitle_match.analyse_file(media)
                self.assertTrue(r["ocr_cached"])
                self.assertGreater(r["ocr_cue_count"],0)
                ocr.assert_not_called()

class ProviderFallbackTests(unittest.TestCase):
    @patch("online_subtitles._search_once")
    def test_exact_tmdb_empty_then_title_finds_subs(self, call):
        call.side_effect=[
            {"results":[{"name":"Flight"}],"subtitles":[]},
            {"results":[{"name":"Flight"}],"subtitles":[{"url":"/subtitle/111.zip"}]}
        ]
        r=online_subtitles.search_with_diagnostics("test-key","Flight","movie",tmdb_id=9999)
        self.assertEqual(len(r["subtitles"]),1)
        self.assertEqual(len(r["attempts"]),2)
        self.assertEqual(call.call_args_list[0].args[-1],9999)
        self.assertIsNone(call.call_args_list[1].args[-1])

    @patch("online_subtitles._search_once",return_value={"results":[{"name":"Flight"}],"subtitles":[]})
    def test_empty_listing_explained(self,_):
        r=online_subtitles.search_with_diagnostics("test-key","Flight","movie")
        self.assertIn("no English subtitle",r["status"])

if __name__=="__main__":
    unittest.main()
