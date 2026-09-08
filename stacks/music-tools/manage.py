#!/usr/bin/env python3
"""Deploy the downloader and conversion worker from Compose."""
import argparse,hashlib,json,os,subprocess,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('action',choices=['init','lock','up','status']);p.add_argument('--library-root',default=str(ROOT.parent/'library'));a=p.parse_args()
def compose(*args,locked=True,**kw):
 cmd=['docker','compose','--env-file',str(ROOT/'.env'),'-f',str(ROOT/'compose.yaml')]
 if locked and (ROOT/'compose.lock.yaml').exists():cmd+=['-f',str(ROOT/'compose.lock.yaml')]
 env=dict(os.environ)
 env['CONVERTER_CODE_SHA']=hashlib.sha256((ROOT/'convert.py').read_bytes()+(ROOT/'bcstm_pcm.py').read_bytes()).hexdigest()
 ports=ROOT.parent/'sso/ports.env'
 if ports.exists():
  for line in ports.read_text().splitlines():
   key,sep,value=line.partition('=')
   if sep and key=='METUBE_PORT':
    if not value.isdigit() or not 1<=int(value)<=65535:raise ValueError('Invalid MeTube internal port')
    env[key]=value
 return subprocess.run(cmd+list(args),cwd=ROOT,check=True,text=True,env=env,**kw)
if a.action in ['init','up']:
 env=ROOT/'.env'
 if not env.exists():env.write_text('LIBRARY_ROOT='+str(Path(a.library_root).resolve())+'\n');env.chmod(0o600)
 lib=Path(dict(x.split('=',1) for x in env.read_text().splitlines() if '=' in x)['LIBRARY_ROOT'])
 for path in [lib/'music/YouTube',lib/'music/Converted']+[ROOT/'storage'/x for x in ['video','state','temp','convert']]:
  if not path.exists():path.mkdir(parents=True,mode=0o750);os.chown(path,33,33)
 if not (lib/'music/.media-library-id').exists():
  marker=lib/'music/.media-library-id';marker.write_text(str(uuid.uuid4()));os.chown(marker,33,33);marker.chmod(0o640)
if a.action in ['lock','up'] and not (ROOT/'compose.lock.yaml').exists():
 compose('--profile','tools','pull',locked=False)
 c=json.loads(compose('--profile','tools','config','--format','json',locked=False,capture_output=True).stdout);lock={'services':{}}
 for name,s in c['services'].items():
  image=json.loads(subprocess.check_output(['docker','image','inspect',s['image']]))[0]['RepoDigests'][0];lock['services'][name]={'image':image}
 (ROOT/'compose.lock.yaml').write_text(json.dumps(lock,indent=2))
if a.action=='up':compose('up','-d','--wait','--wait-timeout','120')
if a.action=='status':compose('ps')
