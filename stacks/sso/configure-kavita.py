#!/usr/bin/env python3
"""Trust the local CA and configure native Kavita OIDC without Development mode."""
import yaml
import json,subprocess,sys,time
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import stack
ca=ROOT/'sso/storage/data/caddy/pki/authorities/local/root.crt'
for _ in range(30):
 if ca.exists():break
 time.sleep(1)
if not ca.exists():raise RuntimeError('Gateway CA is not ready')
trust=ROOT/'sso/trust';trust.mkdir(exist_ok=True)
bundle=stack.compose('exec','-T','kavita','cat','/etc/ssl/certs/ca-certificates.crt',capture_output=True).stdout
(trust/'ca-bundle.pem').write_text(bundle+'\n'+ca.read_text())
public=ROOT/'docs/downloads';public.mkdir(exist_ok=True);(public/'local-ca.crt').write_bytes(ca.read_bytes())
overlay=ROOT/'compose.integrations.yaml';d=yaml.safe_load(overlay.read_text())
k=d['services'].setdefault('kavita',{});k.update(networks=['kavita','identity'])
k.setdefault('environment',{}).update(SSL_CERT_FILE='/run/certs/ca-bundle.pem',ASPNETCORE_FORWARDEDHEADERS_ENABLED='true')
volume='./sso/trust/ca-bundle.pem:/run/certs/ca-bundle.pem:ro'
if volume not in k.setdefault('volumes',[]):k['volumes'].append(volume)
overlay.write_text(json.dumps(d,indent=2));overlay.chmod(0o600)
stack.compose('up','-d','--wait','--wait-timeout','120','kavita')
a=json.loads((ROOT/'runtime/access.json').read_text())['kavita'];s=requests.Session()
for _ in range(30):
 try:
  r=s.post('http://localhost:5000/api/Account/login',json={key:a[key] for key in ['username','password']},timeout=5);r.raise_for_status();break
 except requests.RequestException:time.sleep(2)
else:raise RuntimeError('Kavita did not become available')
s.headers['Authorization']='Bearer '+r.json()['token'];base='http://localhost:5000/api/'
r=s.get(base+'Settings',timeout=30);r.raise_for_status();settings=r.json()
r=s.get(base+'Library/libraries',timeout=30);r.raise_for_status();libraries=r.json()
creds=json.loads((ROOT/'hub/oidc-secrets.json').read_text())['kavita']
settings['oidcConfig'].update(authority='https://login.localhost:9443/application/o/kavita/',
 clientId=creds['client_id'],secret=creds['client_secret'],provisionAccounts=True,
 requireVerifiedEmail=True,syncUserSettings=False,defaultRoles=['Pleb','Login','Download','Bookmark'],
 defaultLibraries=[x['id'] for x in libraries if x['name']=='Books'],defaultIncludeUnknowns=True)
r=s.post(base+'Settings',json=settings,timeout=60)
if not r.ok:raise RuntimeError(f'Kavita OIDC settings rejected (HTTP {r.status_code})')
stack.compose('restart','kavita')
print('Kavita OIDC configured with local HTTPS; client devices need the local CA')
