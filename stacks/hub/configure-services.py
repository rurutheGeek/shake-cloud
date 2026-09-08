#!/usr/bin/env python3
"""Apply native SSO and language settings. Secrets remain in ignored local files."""
import yaml
import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import stack

def occ(*args,**kw):
 return stack.occ(*args,capture_output=True,**kw)

def main():
 credentials=json.loads((ROOT/'hub/oidc-secrets.json').read_text())
 overlay=ROOT/'compose.integrations.yaml'
 data=yaml.safe_load(overlay.read_text()) if overlay.exists() else {'services':{},'networks':{}}
 data.setdefault('networks',{})['identity']={'external':True,'name':'media-hub_default'}
 services=data.setdefault('services',{})
 services.setdefault('nextcloud',{}).setdefault('networks',['backend','nextcloud','identity'])
 authority='https://login.localhost:9443' if (ROOT/'sso/trust/ca-bundle.pem').exists() else 'http://auth.localhost:9000'
 vw=credentials['vaultwarden']
 services.setdefault('vaultwarden',{}).setdefault('networks',['vaultwarden','identity'])
 services['vaultwarden'].setdefault('environment',{}).update({
  'SSO_ENABLED':'true','SSO_ONLY':'false','SSO_SIGNUPS_MATCH_EMAIL':'false',
  'SSO_AUTHORITY':authority+'/application/o/vaultwarden/',
  'SSO_CLIENT_ID':vw['client_id'],'SSO_CLIENT_SECRET':vw['client_secret'],
  'SSO_SCOPES':'email profile offline_access','SSO_PKCE':'true',
  'SSO_ALLOW_UNKNOWN_EMAIL_VERIFICATION':'false'})
 fd=os.open(overlay,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f:json.dump(data,f,indent=2)
 stack.compose('up','-d','--wait','--wait-timeout','300','nextcloud','vaultwarden','navidrome')
 for key,value in [('default_language','ja'),('default_locale','ja_JP')]:occ('config:system:set',key,'--value='+value)
 occ('config:system:set','allow_local_remote_servers','--type=boolean','--value=true')
 nc=credentials['nextcloud']
 os.environ['NEXTCLOUD_OIDC_CLIENT_SECRET']=nc['client_secret']
 stack.compose('exec','-T','--user','33:33','-e','NEXTCLOUD_OIDC_CLIENT_SECRET','nextcloud','php','occ',
  'user_oidc:provider','Authentik','--clientid='+nc['client_id'],'--clientsecret-env=NEXTCLOUD_OIDC_CLIENT_SECRET',
  '--discoveryuri='+authority+'/application/o/nextcloud/.well-known/openid-configuration',
  '--scope=openid email profile','--unique-uid=1','--mapping-uid=sub','--mapping-display-name=name',
  '--mapping-email=email','--mapping-groups=groups','--group-provisioning=1',
  '--group-whitelist-regex=^media-users$','--group-restrict-login-to-whitelist=1',capture_output=True)
 del os.environ['NEXTCLOUD_OIDC_CLIENT_SECRET']
 groups=json.loads(occ('group:list','--output=json').stdout)
 if 'media-users' not in groups:occ('group:add','media-users')
 mounts=json.loads(occ('files_external:list','--output=json').stdout)
 for mount in mounts:
  if mount.get('mount_point','').strip('/').lower() in ['books','music']:
   occ('files_external:applicable',str(mount['mount_id']),'--add-group=media-users')
 print('Nextcloud and Vaultwarden SSO configured; local accounts retained')
if __name__=='__main__':main()
