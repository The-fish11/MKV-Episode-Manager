import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,metadata
class Tests(unittest.TestCase):
 def test_name(self):
  self.assertEqual(core.suggest({'title':"A Knight's Tale",'year':'2001'},'Movie','',1),"A Knight's Tale (2001).mkv")
  self.assertEqual(core.suggest({'episode':'3','title':'Test: Pilot'},'Complete TV Season','Blue Bloods',1),'Blue Bloods - S01E03 - Test_ Pilot.mkv')
 def test_copy(self):
  with tempfile.TemporaryDirectory() as t:
   a=Path(t)/'source';b=Path(t)/'output';a.mkdir();b.mkdir();f=a/'title_t00.mkv';f.write_bytes(b'ABC'*100000)
   original=core.digest(f);core.validate_destination([f],b)
   result=core.verified_copy(f,b,'Film (2001).mkv')
   self.assertTrue(result['verified']);self.assertEqual(core.digest(f),original)
   self.assertEqual(core.digest(b/'Film (2001).mkv'),original)
   with self.assertRaises(FileExistsError):core.verified_copy(f,b,'Film (2001).mkv')
   with self.assertRaises(ValueError):core.validate_destination([f],a)
 def test_project(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'x.json';core.save(p,{'mode':'Movie','items':[]});self.assertEqual(__import__('json').loads(p.read_text())['version'],'0.4.1')
 def test_guess(self):self.assertEqual(metadata.guess_title('Blue_Bloods_t00.mkv'),'Blue Bloods')
 def test_import_title_requires_explicit_dvd_title(self):
  # Generic source names are never used to populate the movie/series field.
  for filename in ('C1_t00.mkv','title_t00.mkv','MKV.00.mkv','Blue_Bloods_t00.mkv','Flight (2012).mkv'):
   with self.subTest(filename=filename):
    self.assertEqual(metadata.title_for_import('',filename),'')
    self.assertEqual(metadata.title_for_import('Flight',filename),'Flight')
  self.assertEqual(metadata.title_for_import('  Blue Bloods  ','title_t00.mkv'),'Blue Bloods')
if __name__=='__main__':unittest.main()
