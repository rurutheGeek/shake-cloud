#!/usr/bin/env python3
"""Use one trusted HTTPS identity endpoint for all browser SSO sessions."""
import yaml
import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
trust=ROOT/'sso/trust'
(trust/'oidc.ini').write_text('openssl.cafile=/run/certs/ca-bundle.pem\ncurl.cainfo=/run/certs/ca-bundle.pem\n')
p=ROOT/'compose.integrations.yaml';d=yaml.safe_load(p.read_text())
d['services']['vaultwarden']['networks']={'vaultwarden':{},'identity':{},'sso':{'ipv4_address':'172.30.80.5'}}
d['services']['vaultwarden'].setdefault('environment',{})['DOMAIN']='https://vault.localhost:8243'
for name in ['nextcloud','vaultwarden']:
 s=d['services'][name];volumes=s.setdefault('volumes',[])
 v='./sso/trust/ca-bundle.pem:/run/certs/ca-bundle.pem:ro'
 if v not in volumes:volumes.append(v)
 if name=='nextcloud':
  v='./sso/trust/oidc.ini:/usr/local/etc/php/conf.d/zz-sso-ca.ini:ro'
  if v not in volumes:volumes.append(v)
 else:s.setdefault('environment',{})['SSL_CERT_FILE']='/run/certs/ca-bundle.pem'
image=json.loads((ROOT/'hub/compose.lock.yaml').read_text())['services']['docs']['image']
d['services']['oidc-loopback']={'image':image,'restart':'unless-stopped','user':'101:101',
 'entrypoint':['nginx','-c','/etc/nginx/oidc.conf','-g','daemon off;'],
 'network_mode':'service:nextcloud','depends_on':{'nextcloud':{'condition':'service_healthy'}},
 'read_only':True,'tmpfs':['/tmp'],'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],
 'volumes':['./sso/loopback-nginx.conf:/etc/nginx/oidc.conf:ro']}
d['services']['vault-oidc-loopback']={**d['services']['oidc-loopback'], 'network_mode':'service:vaultwarden','depends_on':{'vaultwarden':{'condition':'service_healthy'}}}
v='./docs/downloads/local-ca.crt:/run/certs/local-ca.crt:ro'
if v not in d['services']['nextcloud']['volumes']:d['services']['nextcloud']['volumes'].append(v)
p.write_text(json.dumps(d,indent=2));p.chmod(0o600)
p=ROOT/'hub/compose.sso.yaml'
p.write_text(json.dumps({'services':{'homarr':{'environment':{
 'AUTH_OIDC_ISSUER':'https://login.localhost:9443/application/o/homarr/',
 'NODE_EXTRA_CA_CERTS':'/run/certs/ca-bundle.pem','LOCAL_CERTIFICATE_PATH':'/run/certs'},'volumes':['../sso/trust/ca-bundle.pem:/run/certs/ca-bundle.pem:ro']}}},indent=2))
hd=yaml.safe_load(p.read_text())
for service in ['server','worker']:
 hd['services'][service]={'environment':{'SSL_CERT_FILE':'/run/certs/ca-bundle.pem','REQUESTS_CA_BUNDLE':'/run/certs/ca-bundle.pem'},'volumes':['../sso/trust/ca-bundle.pem:/run/certs/ca-bundle.pem:ro']}
p.write_text(json.dumps(hd,indent=2))
subprocess.run(['docker','compose','--env-file','hub/.env','-f','hub/compose.yaml','-f','hub/compose.sso.yaml','-f','hub/compose.lock.yaml','up','-d','--wait','--wait-timeout','300','server','worker'],check=True,cwd=ROOT)
for script in ['hub/configure-services.py','hub/configure-proxy.py']:
 subprocess.run([sys.executable,str(ROOT/script)],check=True,cwd=ROOT)
subprocess.run([sys.executable,str(ROOT/'hub/manage.py'),'configure'],check=True,cwd=ROOT)
sys.path.insert(0,str(ROOT/'scripts'))
import stack
stack.compose('up','-d','oidc-loopback','vault-oidc-loopback')
stack.occ('security:certificates:import','/run/certs/local-ca.crt',capture_output=True)
print('All media SSO uses https://login.localhost:9443')
