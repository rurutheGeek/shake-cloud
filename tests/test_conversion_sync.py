import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'music-tools'))
import convert

class ConversionSyncTest(unittest.TestCase):
 def test_missing_source_needs_two_scans_and_keeps_unmanaged_files(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);out=root/'out';out.mkdir();state_dir=root/'state';state_dir.mkdir()
   (out/'managed.mp3').write_bytes(b'music');(out/'manual.mp3').write_bytes(b'manual')
   state={'files':{'source.bcstm':{'output':'managed.mp3'}}}
   convert.reconcile_deleted(state,{},out,state_dir)
   self.assertTrue((out/'managed.mp3').exists())
   convert.reconcile_deleted(state,{},out,state_dir)
   self.assertFalse((out/'managed.mp3').exists());self.assertEqual(state['files'],{})
   self.assertEqual((out/'manual.mp3').read_bytes(),b'manual')
   self.assertEqual(next((state_dir/'trash').glob('*/*.mp3')).read_bytes(),b'music')
 def test_returning_source_cancels_deletion(self):
  state={'files':{'source.bcstm':{'output':'managed.mp3','missing_scans':1}}}
  convert.reconcile_deleted(state,{'source.bcstm':True},Path('/unused'),Path('/unused'))
  self.assertEqual(state['files']['source.bcstm']['missing_scans'],0)
 def test_missing_or_changed_mount_identity_preserves_outputs(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);music=root/'music';music.mkdir();out=root/'out';out.mkdir();f=root/'state.json'
   (out/'managed.mp3').write_bytes(b'music')
   f.write_text(json.dumps({'version':2,'library_id':'original','files':{'x.bcstm':{'output':'managed.mp3','missing_scans':1}}}))
   with self.assertRaises(FileNotFoundError):convert.tick(music,out,f)
   (music/'.media-library-id').write_text('different')
   with self.assertRaises(ValueError):convert.tick(music,out,f)
   self.assertTrue((out/'managed.mp3').exists())
 def test_output_escape_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError):convert.safe_output(Path(d),'../outside.mp3')
