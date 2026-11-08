import io
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import online_subtitles

class DownloadDiagnosticsTests(unittest.TestCase):
    def test_official_absolute_or_relative_download_link(self):
        self.assertEqual(
            online_subtitles._normalise_subdl_url("/subtitle/3197651-3213944.zip"),
            "https://dl.subdl.com/subtitle/3197651-3213944.zip")
        self.assertEqual(
            online_subtitles._normalise_subdl_url(
                "https://dl.subdl.com/subtitle/3197651-3213944.zip"),
            "https://dl.subdl.com/subtitle/3197651-3213944.zip")
        for link in [
            "https://evil.example/subtitle/123.zip",
            "http://dl.subdl.com/subtitle/123.zip",
            "https://dl.subdl.com.evil.example/subtitle/123.zip",
            "https://dl.subdl.com/subtitle/../other.zip",
            "https://dl.subdl.com/subtitle/%2e%2e/other.zip",
            "https://dl.subdl.com/subtitle/123.zip?api_key=secret",
            "//evil.example/subtitle/123.zip",
        ]:
            with self.subTest(link=link), self.assertRaises(ValueError):
                online_subtitles._normalise_subdl_url(link)


    def test_format_diagnostics_are_safe(self):
        for link,expected in [
            ("https://example.org/subtitle/abc.zip","unexpected host"),
            ("http://dl.subdl.com/subtitle/abc.zip","unexpected scheme"),
            ("https://dl.subdl.com/other/abc.zip","unexpected download path"),
            ("https://dl.subdl.com/subtitle/abc.zip?key=secret","unexpected query/fragment")
        ]:
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError,expected) as ctx:
                online_subtitles._normalise_subdl_url(link)
            self.assertNotIn("secret",str(ctx.exception))

    @patch("online_subtitles.urllib.request.urlopen",side_effect=urllib.error.HTTPError("redacted",429,"rate limit",{},None))
    def test_http429_is_explained_without_url(self, _):
        with self.assertRaisesRegex(RuntimeError,"HTTP 429"):
            online_subtitles._download("/subtitle/123-456.zip")

    @patch("online_subtitles.search_with_diagnostics")
    @patch("online_subtitles._download")
    def test_download_errors_counted(self, download, search):
        search.return_value={
            "subtitles":[{"name":"Flight.2012.zip","url":"/subtitle/100-200.zip"}],
            "attempts":["DVD-cover title: 1 title, 1 subtitle listing"],
            "status":"Listings found"}
        download.side_effect=RuntimeError("HTTP 403: SubDL download access denied or quota")
        with tempfile.TemporaryDirectory() as folder:
            result=online_subtitles.download_references("fake","Flight","movie",folder)
        self.assertEqual(result["download_attempt_count"],1)
        self.assertEqual(result["listing_count"],1)
        self.assertFalse(result["files"])
        self.assertEqual(result["download_diagnostics"].get(
            "HTTP 403: SubDL download access denied or quota"),1)

    @patch("online_subtitles.search_with_diagnostics")
    @patch("online_subtitles._download")
    def test_movie_archive_extraction(self,download,search):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,"w") as zip:
            zip.writestr("Flight.2012.srt","1\n00:00:01,000 --> 00:00:03,000\nWelcome to this test.")
        download.return_value=buf.getvalue()
        search.return_value={"subtitles":[{"name":"Flight.zip","url":"/subtitle/100-200.zip"}],
                             "attempts":[],"status":"Listings found"}
        with tempfile.TemporaryDirectory() as folder:
            result=online_subtitles.download_references("fake","Flight","movie",folder)
            self.assertEqual(len(result["files"]),1)
            self.assertTrue(result["files"][0].is_file())
            self.assertEqual(result["download_diagnostics"]["Downloaded"],1)

if __name__=="__main__":
    unittest.main()
