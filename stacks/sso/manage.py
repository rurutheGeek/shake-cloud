#!/usr/bin/env python3
"""Deploy the SSO gateway after the base, hub and music tool stacks."""
import yaml
import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import stack

def run(*args,**kw):return subprocess.run(list(args),cwd=ROOT,check=True,text=True,**kw)
def env_set(path,key,value):
 lines=path.read_text().splitlines();lines=[line for line in lines if not line.startswith(key+'=')];lines.append(key+'='+value)
 path.write_text('\n'.join(lines)+'\n');path.chmod(0o600)
def compose(*args):
 return run('docker','compose','-f','sso/compose.yaml','-f','sso/compose.lock.yaml',*args)
def main():
 (ROOT/'sso/ports.env').write_text('NAVIDROME_PORT=14533\nMETUBE_PORT=18081\n')
 lock=ROOT/'sso/compose.lock.yaml'
 if not lock.exists():
  run('docker','pull','caddy:2-alpine')
  digest=json.loads(run('docker','image','inspect','caddy:2-alpine',capture_output=True).stdout)[0]['RepoDigests'][0]
  lock.write_text(json.dumps({'services':{'gateway':{'image':digest}}},indent=2))
 run(sys.executable,'hub/configure-proxy.py')
 run(sys.executable,'hub/invitations.py','configure')
 run(sys.executable,'hub/configure-services.py')
 compose('create') # Create the dedicated proxy network before connecting Navidrome.
 overlay=ROOT/'compose.integrations.yaml';data=yaml.safe_load(overlay.read_text())
 data.setdefault('networks',{})['sso']={'external':True,'name':'media-sso_trusted'}
 data.setdefault('services',{})['navidrome']={
  'networks':{'navidrome':{},'sso':{'ipv4_address':'172.30.80.3'}},
  'environment':{'ND_EXTAUTH_USERHEADER':'Remote-User','ND_EXTAUTH_TRUSTEDSOURCES':'172.30.80.2/32'}}
 data['services']['nextcloud']['networks']={'backend':{},'nextcloud':{},'identity':{},'sso':{'ipv4_address':'172.30.80.4'}}
 overlay.write_text(json.dumps(data,indent=2));overlay.chmod(0o600)
 stack.compose('up','-d','--wait','--wait-timeout','300','navidrome','nextcloud')
 run(sys.executable,'music-tools/manage.py','up')
 compose('up','-d','--wait','--wait-timeout','120')
 compose('exec','-T','gateway','caddy','reload','--config','/etc/caddy/Caddyfile')
 run(sys.executable,'sso/configure-nextcloud.py')
 run(sys.executable,'sso/configure-kavita.py')
 run(sys.executable,'sso/configure-identity-tls.py')
 if (ROOT/'netbox/.env').exists():run(sys.executable,'sso/configure-netbox.py')
 run(sys.executable,'hub/manage.py','build')
 print('SSO gateway deployed; emergency/API Navidrome port is localhost:14533')
if __name__=='__main__':main()
