import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core

class SafetyTests(unittest.TestCase):
    def test_verified_copy_and_original_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); src=root/'source'; dst=root/'output';src.mkdir();dst.mkdir()
            original=src/'title_t00.mkv'; original.write_bytes(b'example test video data'*10000)
            h=core.sha256(original)
            result=core.verified_copy(original,dst,'Show - S01E01.mkv')
            self.assertTrue(result['verified']); self.assertEqual(core.sha256(original),h)
            self.assertEqual(core.sha256(dst/'Show - S01E01.mkv'),h)
            with self.assertRaises(FileExistsError):core.verified_copy(original,dst,'Show - S01E01.mkv')
            self.assertEqual(core.sha256(original),h)
    def test_source_folder_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'source';src.mkdir();p=src/'a.mkv';p.write_bytes(b'a')
            with self.assertRaises(ValueError):core.ensure_safe_destination([p],src)
            child=src/'output';child.mkdir()
            with self.assertRaises(ValueError):core.ensure_safe_destination([p],child)
    def test_filenames_and_missing(self):
        self.assertEqual(core.suggested_name({'episode':'2','title':'My: Episode'},'Complete TV Season','Blue Bloods',1),'Blue Bloods - S01E02 - My_ Episode.mkv')
        self.assertEqual(core.missing_episodes([{'episode':'1'},{'episode':'3'}],'Complete TV Season'),[2])
        self.assertEqual(core.missing_episodes([{'episode':'1'},{'episode':'3'}],'Incomplete TV Season'),[])
    def test_project_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'project.json'
            core.save_project(p,{'mode':'Movie','items':[]})
            self.assertEqual(core.load_project(p)['mode'],'Movie')

if __name__=='__main__':unittest.main()
