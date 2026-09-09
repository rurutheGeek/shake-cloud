#!/usr/bin/env python3
"""Enable NetBox native OIDC while retaining local administration and API tokens."""
import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,str(ROOT/'hub/configure-proxy.py')],check=True)
secret=json.loads((ROOT/'hub/oidc-secrets.json').read_text())['netbox']['client_secret']
service={'networks':['default','identity'],'environment':{
 'NETBOX_SSO_ENABLED':'true','NETBOX_OIDC_CLIENT_SECRET':secret,'REQUESTS_CA_BUNDLE':'/run/certs/ca-bundle.pem'},
 'volumes':['../sso/trust/ca-bundle.pem:/run/certs/ca-bundle.pem:ro']}
p=ROOT/'netbox/compose.sso.yaml';p.write_text(json.dumps({'services':{'netbox':service,'netbox-worker':service},
 'networks':{'identity':{'external':True,'name':'media-hub_default'}}},indent=2));p.chmod(0o600)
subprocess.run([sys.executable,str(ROOT/'netbox/manage.py'),'up'],check=True)
print('NetBox native OIDC enabled; application authorization is admin-group only')
