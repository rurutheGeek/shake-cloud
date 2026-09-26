#!/usr/bin/env python3
"""Deploy the downloader and conversion worker from Compose."""
import argparse,datetime,hashlib,json,os,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def compose(*args,locked=True,**kw):
 cmd=['docker','compose','--env-file',str(ROOT/'.env'),'-f',str(ROOT/'compose.yaml')]
 if locked and (ROOT/'compose.lock.yaml').exists():cmd+=['-f',str(ROOT/'compose.lock.yaml')]
 env=dict(os.environ)
 env['CONVERTER_CODE_SHA']=hashlib.sha256((ROOT/'convert.py').read_bytes()+(ROOT/'bcstm_pcm.py').read_bytes()).hexdigest()
 env['TAG_API_CODE_SHA']=hashlib.sha256((ROOT/'tag_api.py').read_bytes()).hexdigest()
 # 辞書は単一ファイルの bind mount なので、置き換えても稼働中コンテナには
 # 反映されない（古い inode を見続ける）。内容をハッシュに含めて再作成させる。
 env['KHINSIDER_CODE_SHA']=hashlib.sha256((ROOT/'khinsider.py').read_bytes()+(ROOT/'khinsider-ja.json').read_bytes()).hexdigest()
 ports=ROOT.parent/'sso/ports.env'
 if ports.exists():
  for line in ports.read_text().splitlines():
   key,sep,value=line.partition('=')
   if sep and key=='METUBE_PORT':
    if not value.isdigit() or not 1<=int(value)<=65535:raise ValueError('Invalid MeTube internal port')
    env[key]=value
 return subprocess.run(cmd+list(args),cwd=ROOT,check=True,text=True,env=env,**kw)
def run(args):
 return subprocess.run(args,cwd=ROOT,check=True)
def backup(destination):
 if os.geteuid()!=0:raise PermissionError('Run backup with sudo to read all application state')
 state=ROOT/'storage';destination=Path(destination).resolve()
 if destination==state or state in destination.parents:raise ValueError('Backup destination must be outside the state directory')
 destination.mkdir(parents=True,exist_ok=True,mode=0o700)
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 target=destination/(stamp+'.incomplete');target.mkdir(mode=0o700)
 running=compose('ps','--services','--status','running',capture_output=True).stdout.split()
 try:
  # 冷間スナップショット: MeTube・変換・Picardを止めてから状態のみを固める。
  # finallyは開始時に動いていたサービスだけを再開する（tar失敗時も）。
  compose('stop','--timeout','120')
  run(['tar','--numeric-owner','-cpf',str(target/'state.tar'),'-C',str(state),'.'])
  run(['tar','--numeric-owner','-cpf',str(target/'deployment.tar'),'compose.yaml','compose.lock.yaml','.env','.env.example','manage.py'])
  (target/'manifest.json').write_text(json.dumps({'storage_root':str(state),'created_utc':stamp,'architecture':os.uname().machine,'format':1,'notes':'Cold backup of music-tools state only; the music library, including YouTube and Converted, is not included. Restore on the same CPU architecture, with services stopped, into a new or empty directory; do not overwrite a live one.'},indent=2)+'\n')
 finally:
  if running:compose('start',*running)
 complete=target.with_suffix('');target.rename(complete)
 print(f'Backup complete: {complete}')
def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['init','lock','up','status','down','backup']);p.add_argument('--library-root',default=str(ROOT.parent/'library'));p.add_argument('--services',help='カンマ区切りの対象サービス。未指定は全サービス');p.add_argument('--destination',default=str(ROOT/'backups'));a=p.parse_args()
 if a.action in ['init','up']:
  env=ROOT/'.env'
  if not env.exists():env.write_text('LIBRARY_ROOT='+str(Path(a.library_root).resolve())+'\n');env.chmod(0o600)
  lib=Path(dict(x.split('=',1) for x in env.read_text().splitlines() if '=' in x)['LIBRARY_ROOT'])
  for path in [lib/'music/YouTube',lib/'music/Converted']+[ROOT/'storage'/x for x in ['video','state','temp','convert','tags','khinsider']]:
   if not path.exists():path.mkdir(parents=True,mode=0o750);os.chown(path,33,33)
  if not (lib/'music/.media-library-id').exists():
   marker=lib/'music/.media-library-id';marker.write_text(str(uuid.uuid4()));os.chown(marker,33,33);marker.chmod(0o640)
 if a.action in ['lock','up'] and not (ROOT/'compose.lock.yaml').exists():
  compose('--profile','tools','pull',locked=False)
  c=json.loads(compose('--profile','tools','config','--format','json',locked=False,capture_output=True).stdout);lock={'services':{}}
  for name,s in c['services'].items():
   image=json.loads(subprocess.check_output(['docker','image','inspect',s['image']]))[0]['RepoDigests'][0];lock['services'][name]={'image':image}
  (ROOT/'compose.lock.yaml').write_text(json.dumps(lock,indent=2)+'\n')
 if a.action=='up':
  # --services はPicardだけの段階配備のため。未指定なら従来どおり全サービス。
  services=[x for x in (a.services or '').split(',') if x]
  # --remove-orphans で、compose から消えたサービス（例: 廃止した picard）の
  # コンテナも片付ける。
  compose('up','-d','--wait','--wait-timeout','120','--remove-orphans',*services)
 if a.action=='down':
  # A unit-level stop keeps Nextcloud/Kavita/Navidrome Compose projects alone.
  compose('down')
 if a.action=='backup':backup(a.destination)
 if a.action=='status':compose('ps')
if __name__=='__main__':
 try:main()
 except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as error:
  print(f'ERROR: {error}',file=sys.stderr);sys.exit(1)
