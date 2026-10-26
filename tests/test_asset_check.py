import contextlib,hashlib,io,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from PIL import Image,PngImagePlugin
sys.path.insert(0,str(Path(__file__).parents[1]))
from asset_check import scan,name_problems,render_html

class ScanTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.root=self.base/'assets';self.root.mkdir()
 def tearDown(self):self.temp.cleanup()
 def image(self,name='ok.png',size=(16,16),color=(40,100,150,128),fmt='PNG',**kwargs):
  path=self.root/name;Image.new('RGBA',size,color).save(path,format=fmt,**kwargs);return path
 def codes(self,report):return {i['code'] for i in report['issues']}
 def test_content_and_pixel_duplicates(self):
  a=self.image();(self.root/'copy.png').write_bytes(a.read_bytes())
  metadata=PngImagePlugin.PngInfo();metadata.add_text('note','different encoded file')
  self.image('other.png',pnginfo=metadata)
  r=scan(self.root,pixel_duplicates=True)
  self.assertEqual({g['kind'] for g in r['duplicateGroups']},{'byte-identical','decoded-rgba-identical'})
  self.assertFalse(r['summary']['incomplete'])
 def test_corrupt_format_and_dimensions(self):
  (self.root/'broken.png').write_bytes(b'not a PNG')
  self.image('wrong.jpg');self.image('large.png',size=(128,32))
  r=scan(self.root,max_dimension=64)
  self.assertTrue({'unreadable_image','extension_mismatch','oversized_texture'}<=self.codes(r))
 def test_sources_are_unchanged(self):
  self.image();(self.root/'text.txt').write_text('hello')
  before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.root.iterdir()}
  scan(self.root,pixel_duplicates=True)
  self.assertEqual(before,{p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.root.iterdir()})
 def test_reports_do_not_expose_absolute_source_path(self):
  (self.root/'broken.png').write_bytes(b'invalid')
  r=scan(self.root)
  self.assertNotIn(str(self.root),json.dumps(r))
  self.assertNotIn(repr(str(self.root))[1:-1],json.dumps(r))
 def test_case_collisions(self):
  if os.name=='nt':self.skipTest('Case-sensitive filenames required; covered on Linux CI.')
  self.image('Hero.png');self.image('hero.png')
  self.assertIn('case_collision',self.codes(scan(self.root)))
 def test_portable_names(self):
  for name in ['CON.png','folder/AUX.txt','bad?.png','tail.png.','tail.png ']:self.assertTrue(name_problems(name))
  self.assertFalse(name_problems('folder/hero jump-01.png'))
 def test_symlink_not_followed(self):
  target=self.base/'outside.png';Image.new('RGB',(16,16)).save(target)
  try:(self.root/'linked.png').symlink_to(target)
  except OSError:self.skipTest('Symlink permission unavailable; covered on Linux CI.')
  r=scan(self.root);self.assertEqual(r['summary']['scannedFiles'],0);self.assertTrue(r['skipped'])
 def test_limits_are_reported_as_incomplete(self):
  self.image('one.png');self.image('two.png')
  self.assertTrue(scan(self.root,max_files=1)['summary']['incomplete'])
  self.assertTrue(scan(self.root,max_file_bytes=1)['summary']['incomplete'])
  self.assertTrue(scan(self.root,max_image_pixels=1)['summary']['incomplete'])
 def test_npot_is_opt_in(self):
  self.image(size=(17,19))
  self.assertNotIn('non_power_of_two',self.codes(scan(self.root)))
  self.assertIn('non_power_of_two',self.codes(scan(self.root,require_power_of_two=True)))
 def test_html_escapes_filenames(self):
  r=scan(self.root);r['issues']=[{'severity':'warning','path':'<script>alert(1)</script>.png','code':'test','message':'x & y'}]
  page=render_html(r);self.assertNotIn('<script>',page);self.assertIn('&lt;script&gt;',page);self.assertIn('x &amp; y',page)
 def test_report_writes_outside_only_and_never_overwrites(self):
  self.image();script=str(Path(__file__).parents[1]/'asset_check.py')
  inside=self.root/'report.json'
  r=subprocess.run([sys.executable,script,str(self.root),'--format','json','-o',str(inside)],capture_output=True,text=True)
  self.assertEqual(r.returncode,2);self.assertFalse(inside.exists())
  outside=self.base/'report.json'
  r=subprocess.run([sys.executable,script,str(self.root),'--format','json','-o',str(outside)],capture_output=True,text=True)
  self.assertEqual(r.returncode,0);self.assertEqual(json.loads(outside.read_text())['summary']['errors'],0)
  before=outside.read_bytes();r=subprocess.run([sys.executable,script,str(self.root),'--format','json','-o',str(outside)],capture_output=True)
  self.assertEqual(r.returncode,2);self.assertEqual(outside.read_bytes(),before)
 def test_exit_codes(self):
  self.image();self.image('copy.png');script=str(Path(__file__).parents[1]/'asset_check.py')
  for options,expected in [([],0),(['--fail-on','warning'],1),(['--max-files','1'],2)]:
   r=subprocess.run([sys.executable,script,str(self.root),*options],capture_output=True);self.assertEqual(r.returncode,expected)
 def test_generated_directories_are_excluded(self):
  folder=self.root/'.git';folder.mkdir();(folder/'broken.png').write_bytes(b'invalid')
  r=scan(self.root);self.assertEqual(r['summary']['scannedFiles'],0);self.assertFalse(r['summary']['incomplete'])

if __name__=='__main__':unittest.main()
