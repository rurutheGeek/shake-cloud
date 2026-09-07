#!/usr/bin/env python3
"""Refresh Nextcloud's cache and Navidrome only after the music tree changes."""
import fcntl,hashlib,json,os,secrets,subprocess,urllib.parse,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
lock = (ROOT/'runtime/music-sync.lock').open('w')
try:
 fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
 print('OK: another music sync is running');raise SystemExit(0)
import stack
env=stack.settings()
music=(ROOT/env.get('LIBRARY_ROOT','./library')/'music').resolve()
manifest=[]
for p in sorted(music.rglob('*')):
 if p.is_symlink() or not p.is_file() or p.name.startswith('.') or p.suffix in ['.part','.ytdl','.tmp']:continue
 st=p.stat();manifest.append((str(p.relative_to(music)),st.st_size,st.st_mtime_ns))
fingerprint=hashlib.sha256(json.dumps(manifest,ensure_ascii=False).encode()).hexdigest()
state=ROOT/'runtime/music-fingerprint'
if state.exists() and state.read_text()==fingerprint:
 print('OK: music unchanged');raise SystemExit(0)
cmd=['docker','compose','--env-file',str(ROOT/'.env'),'-f',str(ROOT/'compose.yaml')]
if (ROOT/'compose.lock.yaml').exists():cmd+=['-f',str(ROOT/'compose.lock.yaml')]
scan=subprocess.run(cmd+['exec','-T','-u','www-data','nextcloud','php','occ','files:scan','--path',env.get('NEXTCLOUD_ADMIN_USER','admin')+'/files/music'],check=True,cwd=ROOT,capture_output=True,text=True)
print(scan.stdout)
if 'Another process is already scanning' in scan.stdout + scan.stderr:
 raise RuntimeError('Nextcloud is busy; retry on next timer run')
a=json.loads((ROOT/'runtime/access.json').read_text())['navidrome'];salt=secrets.token_hex(12)
query={'u':a['username'],'t':hashlib.md5((a['password']+salt).encode()).hexdigest(),'s':salt,'v':'1.16.1','c':'media-stack-sync','f':'json'}
url='http://localhost:'+env.get('NAVIDROME_PORT','4533')+'/rest/startScan.view?'+urllib.parse.urlencode(query)
with urllib.request.urlopen(url,timeout=30) as r:result=json.load(r)['subsonic-response']
if result['status']!='ok':raise RuntimeError('Navidrome scan request failed')
state.write_text(fingerprint);os.chmod(state,0o600)
print('CHANGED: Nextcloud music cache refreshed; Navidrome scan requested')
