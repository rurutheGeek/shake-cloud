#!/usr/bin/env python3
"""Reconcile Authentik OIDC clients without exposing credentials."""
import json,os,secrets
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parent
v=dict(line.split('=',1) for line in (ROOT/'.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
s=requests.Session();s.headers['Authorization']='Bearer '+v['AUTHENTIK_BOOTSTRAP_TOKEN']
def api(method,path,**kwargs):
 r=s.request(method,'http://localhost:9000/api/v3/'+path,timeout=30,**kwargs)
 if not r.ok:raise RuntimeError(f'{method} {path}: HTTP {r.status_code}; fields: {list(r.json())}')
 return r.json() if r.content else None
def rows(path):return api('GET',path)['results']
flows={x['slug']:x['pk'] for x in rows('flows/instances/')}
scope_rows=rows('propertymappings/provider/scope/')
email_mapping=next((x for x in scope_rows if x['name']=='media-stack verified email'),None)
email_data={'name':'media-stack verified email','scope_name':'email','expression':'return {"email": request.user.email, "email_verified": request.user.attributes.get("email_verified", False) is True}'}
email_mapping=api('PATCH' if email_mapping else 'POST',f"propertymappings/provider/scope/{email_mapping['pk']}/" if email_mapping else 'propertymappings/provider/scope/',json=email_data)
mappings=[x['pk'] for x in scope_rows if x['scope_name'] in ['openid','profile','offline_access']]+[email_mapping['pk']]
key=rows('crypto/certificatekeypairs/')[0]['pk']
existing={x['name']:x for x in rows('providers/oauth2/')}
credsfile=ROOT/'oidc-secrets.json'
if not credsfile.exists():
 fd=os.open(credsfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w') as f:json.dump({},f)
creds=json.loads(credsfile.read_text())
clients={'netbox':'http://localhost:8000/oauth/complete/oidc/','homarr':'http://localhost:7575/api/auth/callback/oidc','nextcloud':'https://nextcloud.localhost:8443/apps/user_oidc/code','kavita':'https://kavita.localhost:5443/signin-oidc','vaultwarden':'https://vault.localhost:8243/identity/connect/oidc-signin'}
for name,redirect in clients.items():
 if name not in creds:
  creds[name]={'client_id':name,'client_secret':secrets.token_hex(32)}
  credsfile.write_text(json.dumps(creds,indent=2))
 data=dict(name=name,authorization_flow=flows['default-provider-authorization-implicit-consent'],invalidation_flow=flows['default-provider-invalidation-flow'],client_type='confidential',grant_types=['authorization_code','refresh_token'],redirect_uris=[{'matching_mode':'strict','url':redirect}],property_mappings=mappings,signing_key=key,sub_mode='hashed_user_id',**creds[name])
 old=existing.get(name)
 provider=api('PATCH' if old else 'POST',f"providers/oauth2/{old['pk']}/" if old else 'providers/oauth2/',json=data)
 apps={x['slug']:x for x in rows('core/applications/')};data={'name':name.title(),'slug':name,'provider':provider['pk'],'meta_launch_url':'/'.join(redirect.split('/')[:3])}
 api('PATCH' if name in apps else 'POST',f'core/applications/{name}/' if name in apps else 'core/applications/',json=data)
 print('OIDC provider reconciled:',name)
groups=rows('core/groups/?name=homarr-admins')
if not groups:group=api('POST','core/groups/',json={'name':'homarr-admins'})
else:group=groups[0]
user=rows('core/users/?username=akadmin')[0]
if group['pk'] not in user['groups']:api('PATCH',f"core/users/{user['pk']}/",json={'groups':user['groups']+[group['pk']]})
print('Homarr administrator group reconciled')
