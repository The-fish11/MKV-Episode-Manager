import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import subtitle_match

class OcrIntegrationTests(unittest.TestCase):
    @patch("subtitle_match.shutil.which", side_effect=lambda x: "C:/tools/"+x+".exe")
    @patch("subtitle_match.subprocess.run")
    def test_select_english_ocr_stream_and_long_timeout(self, runner, which):
        def fake_run(args, **kwargs):
            folder = Path(next(x.split(":",1)[1] for x in args if x.startswith("--output-folder:")))
            (folder/"C1_t00.eng.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nSample dialogue for testing the converter", encoding="utf-8")
            return Mock(returncode=0)
        runner.side_effect=fake_run
        tracks=[{"index":3,"language":"dan","needs_ocr":True},
                {"index":4,"language":"eng","needs_ocr":True,"forced":False},
                {"index":9,"language":"eng","needs_ocr":True,"forced":True}]
        with tempfile.TemporaryDirectory() as folder:
            files=subtitle_match.ocr_image_subtitles("source.mkv",folder,tracks)
            args=runner.call_args.args[0]
            self.assertIn("--track-number:5",args)
            self.assertEqual(runner.call_args.kwargs["timeout"],2400)
            self.assertEqual(len(files),1)
    @patch("subtitle_match.shutil.which", return_value="tool.exe")
    def test_no_english_stream_skips_ocr(self, _):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError,"No English"):
                subtitle_match.ocr_image_subtitles("source.mkv",folder,[{"index":3,"language":"dan","needs_ocr":True}])
if __name__=="__main__":
    unittest.main()
