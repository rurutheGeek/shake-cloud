#!/usr/bin/env python3
"""Create MP3 listening copies and reconcile deletions of BCSTM originals."""
import json,os,shutil,subprocess,tempfile,time,uuid
from pathlib import Path
from bcstm_pcm import decode_pcm
ROOT=Path('/music');OUT=Path('/converted');STATE=Path('/state/converted.json')

def safe_output(root,name):
 path=root/name
 if path.is_symlink() or root.resolve() not in path.resolve().parents:
  raise ValueError('Output must be a regular path inside the managed output directory')
 return path

def save_state(path,state):
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=False));os.replace(temp,path)

def quarantine(path,state_dir):
 if not path.exists():return
 folder=state_dir/'trash'/f'{int(time.time())}-{uuid.uuid4().hex}'
 folder.mkdir(parents=True);os.replace(path,folder/path.name)

def scan_sources(root):
 result={}
 def failed(error):raise error
 for directory,dirs,files in os.walk(root,onerror=failed,followlinks=False):
  dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink() and d!='Converted']
  for name in files:
   src=Path(directory)/name
   if src.suffix.lower()=='.bcstm' and not src.is_symlink():result[str(src.relative_to(root))]=src
 return result

def reconcile_deleted(state,sources,output,state_dir):
 for name,entry in list(state['files'].items()):
  if name in sources:
   entry['missing_scans']=0;continue
  entry['missing_scans']=entry.get('missing_scans',0)+1
  if entry['missing_scans']<2:continue
  for relative in [entry.get('output'),entry.get('legacy_output')]:
   if relative:quarantine(safe_output(output,relative),state_dir)
  del state['files'][name]
  print('REMOVED listening copy for deleted source:',name,flush=True)

def duration(path):
 r=subprocess.run(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=duration','-of','json',str(path)],capture_output=True,text=True,check=True)
 return float(json.loads(r.stdout)['streams'][0]['duration'])

def decoded_duration(path):
 # MP3 container duration includes encoder delay/padding, especially at low sample rates.
 r=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-nostats',
  '-progress','pipe:1','-i',str(path),'-map','0:a:0','-f','null','-'],
  capture_output=True,text=True,check=True,timeout=1800)
 values=[int(line.split('=',1)[1]) for line in r.stdout.splitlines() if line.startswith('out_time_us=') and line.split('=',1)[1]!='N/A']
 if not values:raise ValueError('Unable to verify decoded MP3 duration')
 return values[-1]/1000000

def tick(root=ROOT,output=OUT,state_file=STATE):
 identity=(root/'.media-library-id').read_text().strip()
 if not identity:raise ValueError('Missing library identity; deletion reconciliation suspended')
 state=json.loads(state_file.read_text()) if state_file.exists() else {'version':2,'library_id':identity,'files':{}}
 if state.get('version')!=2:
  state={'version':2,'library_id':identity,'files':{name:{'source_signature':sig,'legacy_output':str(Path(name).with_suffix('.flac'))} for name,sig in state.items()}}
 if state['library_id']!=identity:raise ValueError('Library identity changed; reconciliation suspended')
 sources=scan_sources(root)  # A failed/incomplete traversal must never be interpreted as deletion.
 for name,src in sources.items():
  st=src.stat();signature=[st.st_size,st.st_mtime_ns];entry=state['files'].get(name,{})
  relative=str(Path(name).with_suffix('.mp3'));dest=safe_output(output,relative)
  if time.time()-st.st_mtime<60:continue
  if entry.get('source_signature')==signature and entry.get('output')==relative and dest.exists():continue
  if dest.exists() and entry.get('output')!=relative:
   print('SKIP unmanaged output:',relative,flush=True);continue
  if shutil.disk_usage(output).free<max(512*1024*1024,st.st_size*4):
   print('WAIT insufficient space:',name,flush=True);continue
  dest.parent.mkdir(parents=True,exist_ok=True)
  fd,tmp=tempfile.mkstemp(prefix='.converting-',suffix='.mp3',dir=dest.parent);os.close(fd);pcm_tmp=Path(tmp).with_suffix('.wav')
  try:
   (state_file.parent/'heartbeat').touch()
   input_path=pcm_tmp if decode_pcm(src,pcm_tmp) else src
   subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(input_path),'-map','0:a:0','-vn','-c:a','libmp3lame','-q:a','2','-metadata','title='+src.stem,'-metadata','album='+src.parent.name,tmp],capture_output=True,text=True,check=True,timeout=1800)
   expected,actual=duration(input_path),decoded_duration(tmp)
   if abs(expected-actual)>max(0.15,expected*0.01):raise ValueError('Converted duration does not match original')
   after=src.stat()
   if [after.st_size,after.st_mtime_ns]!=signature:continue
   os.chmod(tmp,0o640);os.replace(tmp,dest)
   if entry.get('legacy_output'):quarantine(safe_output(output,entry['legacy_output']),state_file.parent)
   state['files'][name]={'source_signature':signature,'output':relative,'missing_scans':0}
   save_state(state_file,state);print('CONVERTED to MP3:',name,flush=True)
  except Exception as exc:print('FAILED:',name,type(exc).__name__,str(exc),flush=True)
  finally:Path(tmp).unlink(missing_ok=True);pcm_tmp.unlink(missing_ok=True)
 if (root/'.media-library-id').read_text().strip()!=identity:
  raise ValueError('Library changed during scan; deletion reconciliation suspended')
 reconcile_deleted(state,sources,output,state_file.parent);save_state(state_file,state)
 trash=state_file.parent/'trash'
 if trash.exists():
  for folder in trash.iterdir():
   if folder.is_dir() and not folder.is_symlink() and folder.name.split('-')[0].isdigit() and time.time()-int(folder.name.split('-')[0])>7*86400:shutil.rmtree(folder)
 (state_file.parent/'heartbeat').touch()

if __name__=='__main__':
 while True:
  try:tick()
  except Exception as exc:print(type(exc).__name__,str(exc),flush=True)
  time.sleep(60)
