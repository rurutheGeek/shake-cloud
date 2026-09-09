#!/usr/bin/env python3
"""Reconcile explicitly listed identities; initial passwords stay in a private file."""
import argparse,json,os,secrets
from pathlib import Path
import requests
from identity_attributes import attributes_for
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);args=p.parse_args()
entries=json.loads(args.manifest.read_text());allowed={'media-users','homarr-admins'}
for entry in entries:
 if not entry.get('username') or not entry.get('email') or '@' not in entry['email']:raise ValueError('Username and email are required')
 if not set(entry.get('groups',['media-users']))<=allowed:raise ValueError('Unsupported managed group')
v=dict(x.split('=',1) for x in (ROOT/'hub/.env').read_text().splitlines() if '=' in x and not x.startswith('#'))
s=requests.Session();s.headers['Authorization']='Bearer '+v['AUTHENTIK_BOOTSTRAP_TOKEN'];base='http://localhost:9000/api/v3/'
def api(method,path,**kw):
 r=s.request(method,base+path,timeout=30,**kw)
 if not r.ok:raise RuntimeError(f'Identity API: HTTP {r.status_code}')
 return r.json() if r.content else None
groups={x['name']:x['pk'] for x in api('GET','core/groups/?page_size=100')['results']}
private=ROOT/'runtime/user-bootstrap.json';passwords=json.loads(private.read_text()) if private.exists() else {}
for entry in entries:
 existing=api('GET','core/users/',params={'username':entry['username']})['results']
 user=next((x for x in existing if x['username']==entry['username']),None)
 desired=[groups[name] for name in entry.get('groups',['media-users'])]
 if user:desired=sorted(set(desired+[g for g in user['groups'] if g not in [groups[n] for n in allowed]]))
 data={'username':entry['username'],'name':entry.get('name',entry['username']),'email':entry['email'],
  'is_active':entry.get('active',True),'groups':desired,'attributes':attributes_for(entry,user)}
 updated=api('PATCH' if user else 'POST',f"core/users/{user['pk']}/" if user else 'core/users/',json=data)
 if not user:
  password=secrets.token_urlsafe(32)
  api('POST',f"core/users/{updated['pk']}/set_password/",json={'password':password})
  passwords[entry['username']]={'initial_password':password}
  fd=os.open(private,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
  with os.fdopen(fd,'w') as f:json.dump(passwords,f,indent=2)
 print('Identity reconciled:',entry['username'])
print('Initial passwords, when generated: runtime/user-bootstrap.json')
