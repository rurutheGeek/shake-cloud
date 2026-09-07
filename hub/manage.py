#!/usr/bin/env python3
"""Reproducible local hub deployment. Run with the project's Python environment."""
import argparse,datetime,json,os,secrets,subprocess,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
KEYS=['PG_PASS','AUTHENTIK_SECRET_KEY','AUTHENTIK_BOOTSTRAP_PASSWORD','AUTHENTIK_BOOTSTRAP_TOKEN','HOMARR_SECRET_ENCRYPTION_KEY']
def run(cmd,**kw):return subprocess.run(cmd,cwd=ROOT,check=True,text=True,**kw)
def compose(*args,locked=True,**kw):
 cmd=['docker','compose','--env-file',str(ROOT/'.env'),'-f',str(ROOT/'compose.yaml')]
 if (ROOT/'compose.sso.yaml').exists():cmd+=['-f',str(ROOT/'compose.sso.yaml')]
 if (ROOT/'compose.smtp.yaml').exists():cmd+=['-f',str(ROOT/'compose.smtp.yaml')]
 if locked and (ROOT/'compose.lock.yaml').exists():cmd+=['-f',str(ROOT/'compose.lock.yaml')]
 return run(cmd+list(args),**kw)
def init():
 path=ROOT/'.env';v=dict(x.split('=',1) for x in path.read_text().splitlines() if '=' in x and not x.startswith('#')) if path.exists() else {}
 for key in KEYS:
  if not v.get(key):v[key]=secrets.token_hex(32)
 if not v.get('HOMARR_OIDC_CLIENT_SECRET'):v['HOMARR_OIDC_CLIENT_SECRET']=secrets.token_hex(32)
 path.write_text(''.join(k+'='+value+'\n' for k,value in v.items()));path.chmod(0o600)
 for d in ['site','templates']:(ROOT/d).mkdir(exist_ok=True)
 access=ROOT.parent/'runtime/access.json';access.parent.mkdir(exist_ok=True,mode=0o700)
 a=json.loads(access.read_text()) if access.exists() else {}
 if 'authentik' not in a:
  a['authentik']={'url':'http://localhost:9000','username':'akadmin','password':v['AUTHENTIK_BOOTSTRAP_PASSWORD']};access.write_text(json.dumps(a,indent=2));access.chmod(0o600)
def lock():
 if (ROOT/'compose.lock.yaml').exists():print('OK: existing image lock retained');return
 compose('pull',locked=False)
 c=json.loads(compose('config','--format','json',locked=False,capture_output=True).stdout)
 result={'services':{}}
 for name,s in c['services'].items():
  image=json.loads(run(['docker','image','inspect',s['image']],capture_output=True).stdout)[0]['RepoDigests'][0]
  result['services'][name]={'image':image}
 (ROOT/'compose.lock.yaml').write_text(json.dumps(result,indent=2))
def build():run([sys.executable,'-m','mkdocs','build','--strict','-f',str(ROOT.parent/'mkdocs.yml')])
def configure():
 run([sys.executable,str(ROOT/'configure-oidc.py')])
 v=dict(x.split('=',1) for x in (ROOT/'.env').read_text().splitlines() if '=' in x)
 v['HOMARR_OIDC_CLIENT_SECRET']=json.loads((ROOT/'oidc-secrets.json').read_text())['homarr']['client_secret']
 (ROOT/'.env').write_text(''.join(k+'='+value+'\n' for k,value in v.items()))
 compose('up','-d','--wait','--wait-timeout','300','homarr')
 import time,urllib.request
 for _ in range(60):
  try:urllib.request.urlopen('http://localhost:7575/api/auth/csrf',timeout=5);break
  except Exception:time.sleep(2)
 run([sys.executable,str(ROOT/'configure-homarr.py')])
def backup(destination):
 target=Path(destination).resolve()/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');target.mkdir(parents=True,mode=0o700)
 if ROOT==target or ROOT/'storage' in target.parents:raise ValueError('Backup must be outside storage')
 compose('stop')
 try:
  with tarfile.open(target/'hub.tar.gz','w:gz') as out:
   for name in ['storage','.env','oidc-secrets.json','compose.yaml','compose.lock.yaml','compose.smtp.yaml','compose.sso.yaml','apps.json']:
    if (ROOT/name).exists():out.add(ROOT/name,arcname=name)
   if (ROOT.parent/'runtime/access.json').exists():out.add(ROOT.parent/'runtime/access.json',arcname='runtime/access.json')
 finally:compose('start')
 print('Backup:',target)
p=argparse.ArgumentParser();p.add_argument('action',choices=['init','lock','up','configure','build','backup','status']);p.add_argument('--destination',default=str(ROOT.parent/'backups/hub'));a=p.parse_args()
if a.action=='init':init()
elif a.action=='lock':lock()
elif a.action=='build':build()
elif a.action=='up':init();lock();build();compose('up','-d','--wait','--wait-timeout','600');configure()
elif a.action=='configure':configure()
elif a.action=='status':compose('ps')
else:backup(a.destination)
