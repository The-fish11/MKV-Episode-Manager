import io
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import reference_cache
import online_subtitles
import subtitle_results


class ReferenceCacheTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.directory = Path(self.folder.name) / "reference_cache"
        self.patcher = patch("reference_cache.cache_dir",return_value=self.directory)
        self.patcher.start()
        self.link = "https://dl.subdl.com/subtitle/8-16.zip?api_key=NEVER_SAVE_THIS"
        self.payload = self._sample_zip()

    def tearDown(self):
        self.patcher.stop()
        self.folder.cleanup()

    @staticmethod
    def _sample_zip():
        output=io.BytesIO()
        with zipfile.ZipFile(output,"w") as archive:
            archive.writestr("FlashForward.S01E02.srt",
                "1\\n00:00:01,000 --> 00:00:05,000\\nThe next episode begins now.\\n")
        return output.getvalue()

    def test_cache_persists_without_exposing_credentials(self):
        self.assertTrue(reference_cache.store(self.link,"user-key",self.payload))
        self.assertEqual(reference_cache.load(self.link,"user-key"),self.payload)
        self.assertIsNone(reference_cache.load(self.link,"different-user-key"))
        paths=list(self.directory.iterdir())
        self.assertEqual(len(paths),1)
        self.assertNotIn("NEVER_SAVE_THIS",paths[0].name)
        self.assertNotIn("user-key",paths[0].name)

    @patch("online_subtitles.search_with_diagnostics")
    @patch("online_subtitles._download")
    def test_second_analysis_reuses_files_without_network_download(self,download,search):
        download.return_value=self.payload
        search.return_value={
            "subtitles":[{"name":"FlashForward.S01E02.zip","url":self.link}],
            "attempts":["TMDB ID: 1 title, 1 subtitle listing"],
            "status":"Listings found",
        }
        with tempfile.TemporaryDirectory() as folder:
            first=online_subtitles.download_references("user-key","FlashForward","tv",folder,season=1)
        with tempfile.TemporaryDirectory() as folder:
            second=online_subtitles.download_references("user-key","FlashForward","tv",folder,season=1)
        self.assertEqual(first["download_attempt_count"],1)
        self.assertEqual(first["cached_reference_count"],0)
        self.assertEqual(second["download_attempt_count"],0)
        self.assertEqual(second["cached_reference_count"],1)
        self.assertEqual(len(second["files"]),1)
        download.assert_called_once()

    @patch("online_subtitles.search_with_diagnostics")
    @patch("online_subtitles._download")
    def test_http429_stops_at_first_denied_download(self,download,search):
        search.return_value={
            "subtitles":[{"name":"Ep.zip","url":"/subtitle/%d-%d.zip"%(i,i+1)}
                         for i in range(8)],
            "attempts":[],"status":"Listings found"}
        download.side_effect=RuntimeError("HTTP 429: SubDL download rate limit")
        with tempfile.TemporaryDirectory() as folder:
            result=online_subtitles.download_references("user-key","FlashForward","movie",folder)
        self.assertTrue(result["rate_limited"])
        self.assertEqual(result["download_attempt_count"],1)
        download.assert_called_once()

    def test_expired_cache_entry_is_ignored(self):
        self.assertTrue(reference_cache.store(self.link,"user-key",self.payload))
        cached=reference_cache._entry_path(self.link,"user-key")
        import os,time
        timestamp=time.time()-reference_cache.MAX_AGE_SECONDS-60
        os.utime(cached,(timestamp,timestamp))
        self.assertIsNone(reference_cache.load(self.link,"user-key"))
        self.assertEqual(reference_cache.prune(),1)

    def test_clear_keeps_ocr_cache_and_unrelated_files(self):
        self.assertTrue(reference_cache.store(self.link,"user-key",self.payload))
        unrelated=self.directory.parent/"original.mkv"
        unrelated.write_bytes(b"Do not touch")
        self.assertEqual(reference_cache.clear(),1)
        self.assertIsNone(reference_cache.load(self.link,"user-key"))
        self.assertEqual(unrelated.read_bytes(),b"Do not touch")

    def test_quota_warning_does_not_claim_dialogue_mismatch(self):
        summary=subtitle_results.summary({
            "tracks":[],"top_matches":[],"ocr_cue_count":743,
            "online_reference_count":0,"online_listing_count":30,
            "online_rate_limited":True,
            "online_reference_status":"SubDL download limit reached"})
        self.assertIn("limit reached",summary["heading"])
        self.assertNotIn("No supported dialogue match",summary["heading"])


if __name__=="__main__":
    unittest.main()
