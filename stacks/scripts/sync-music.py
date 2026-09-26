#!/usr/bin/env python3
"""Refresh Nextcloud's cache and Navidrome only after the music tree changes.

Works with both layouts: the split media stack (<root>/media/<unit>, current
media-01) and the old all-in-one stack (<root>/compose.yaml). Navidrome is
rescanned with its own CLI, so no stored admin password is needed. The runtime
directory is created here; it was missing on media-01 and made every timer
run fail (fixed 2026-09-24).
"""
import fcntl,hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
(ROOT/'runtime').mkdir(exist_ok=True,mode=0o700)
lock = (ROOT/'runtime/music-sync.lock').open('w')
try:
 fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
 print('OK: another music sync is running');raise SystemExit(0)


def read_env(path):
 values={}
 if path.exists():
  for line in path.read_text().splitlines():
   key,sep,value=line.partition('=')
   if sep and not line.startswith('#'):values[key.strip()]=value.strip()
 return values


def unit(name):
 """Return (directory, compose command) for a service in either layout."""
 split=ROOT/'media'/name
 directory=split if (split/'compose.yaml').exists() else ROOT
 if not (directory/'compose.yaml').exists():
  raise RuntimeError(f'no compose.yaml for {name} under {ROOT}')
 cmd=['docker','compose','--env-file',str(directory/'.env'),'-f',str(directory/'compose.yaml')]
 lockfile=directory/'compose.lock.yaml'
 if lockfile.exists():cmd+=['-f',str(lockfile)]
 return directory,cmd


nc_dir,nc_cmd=unit('nextcloud')
nav_dir,nav_cmd=unit('navidrome')
env={**read_env(ROOT/'.env'),**read_env(nc_dir/'.env'),**read_env(nav_dir/'.env')}
music=(Path(env.get('LIBRARY_ROOT','/srv/media-stack/library'))/'music').resolve()
manifest=[]
for p in sorted(music.rglob('*')):
 if p.is_symlink() or not p.is_file() or p.name.startswith('.') or p.suffix in ['.part','.ytdl','.tmp']:continue
 st=p.stat();manifest.append((str(p.relative_to(music)),st.st_size,st.st_mtime_ns))
fingerprint=hashlib.sha256(json.dumps(manifest,ensure_ascii=False).encode()).hexdigest()
state=ROOT/'runtime/music-fingerprint'
if state.exists() and state.read_text()==fingerprint:
 print('OK: music unchanged');raise SystemExit(0)
scan=subprocess.run(nc_cmd+['exec','-T','-u','www-data','nextcloud','php','occ','files:scan','--path',env.get('NEXTCLOUD_ADMIN_USER','admin')+'/files/music'],check=True,capture_output=True,text=True)
print(scan.stdout)
if 'Another process is already scanning' in scan.stdout + scan.stderr:
 raise RuntimeError('Nextcloud is busy; retry on next timer run')
rescan=subprocess.run(nav_cmd+['exec','-T','navidrome','navidrome','scan'],check=True,capture_output=True,text=True)
tail=(rescan.stderr or rescan.stdout).strip().splitlines()
if tail:print(tail[-1])
state.write_text(fingerprint);os.chmod(state,0o600)
print('CHANGED: Nextcloud music cache refreshed; Navidrome scan finished')
