#!/usr/bin/env python3
"""Reconcile the managed Homarr board from apps.json through authenticated APIs."""
import json,secrets,os,html,urllib.parse
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parent
access=ROOT.parent/'runtime/access.json'
all_access=json.loads(access.read_text()) if access.exists() else {}
if 'homarr' not in all_access:
 all_access['homarr']={'url':'http://localhost:7575','username':'admin','password':'Aa1!'+secrets.token_urlsafe(30)}
 access.parent.mkdir(exist_ok=True,mode=0o700);access.write_text(json.dumps(all_access,indent=2));access.chmod(0o600)
v=all_access['homarr'];s=requests.Session();base=v['url']
def bootstrap_call(path,data=None):
 r=s.post(base+'/api/trpc/'+path,json={'json':data},timeout=30);r.raise_for_status()
for _ in range(8):
 r=s.get(base+'/api/trpc/onboard.currentStep',timeout=30);r.raise_for_status();step=r.json()['result']['data']['json']['current']
 if step=='finish':break
 if step=='user':bootstrap_call('user.initUser',{'username':v['username'],'password':v['password'],'confirmPassword':v['password']})
 elif step in ['start','group','settings','integrations']:bootstrap_call('onboard.nextStep',{})
 else:raise RuntimeError('Unexpected onboarding step: '+step)
csrf=s.get(base+'/api/auth/csrf',timeout=30).json()['csrfToken']
r=s.post(base+'/api/auth/callback/credentials',data={'csrfToken':csrf,'name':v['username'],'password':v['password'],'callbackUrl':base,'json':'true'},timeout=30);r.raise_for_status()
assert s.get(base+'/api/auth/session',timeout=30).json().get('user'), 'Homarr authentication failed'
def call(path,data=None,post=False):
 kw={'json':{'json':data}} if post else ({'params':{'input':json.dumps({'json':data})}} if data is not None else {})
 r=s.request('POST' if post else 'GET',base+'/api/trpc/'+path,timeout=30,**kw)
 if not r.ok:raise RuntimeError(f'{path}: {r.status_code} {r.text[:500]}')
 return r.json()['result']['data'].get('json')
call('serverSettings.saveSettings',{'settingsKey':'culture','value':{'defaultLocale':'ja'}},True)
boards=call('board.getAllBoards');board=next((x for x in boards if x['name']=='home'),None)
if board is None:board={'id':call('board.createBoard',{'name':'home','columnCount':8,'isPublic':False},True)['boardId']}
call('board.savePartialBoardSettings',{'id':board['id'],'pageTitle':'セルフホスト・ハブ','metaTitle':'セルフホスト・ハブ','disableStatus':True},True)
apps={x['name']:x for x in call('app.all')}
current=call('board.getBoardByName',{'name':'home'})
existing_items=current.get('items',[])
for app in json.loads((ROOT/'apps.json').read_text()):
 label=html.escape(app.get('iconText','APP'));color=html.escape(app.get('iconColor','#475569'),quote=True)
 svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><rect x="8" y="8" width="112" height="112" rx="24" fill="{color}"/><text x="64" y="73" text-anchor="middle" fill="white" font-family="sans-serif" font-size="28" font-weight="700">{label}</text></svg>'
 data={k:app[k] for k in ['name','description','href']}
 data.update(iconUrl='data:image/svg+xml,'+urllib.parse.quote(svg),pingUrl=None)
 if app['name'] in apps:
  a=apps[app['name']];call('app.update',{**data,'id':a['id']},True);app_id=a['id']
 else:app_id=call('app.create',data,True)['appId']
 def options(item):
  value=item.get('options',{})
  if isinstance(value,str):value=json.loads(value)
  return value.get('json',value)
 if not any(options(x).get('appId')==app_id for x in existing_items):
  call('board.addItem',{'boardId':board['id'],'kind':'app','options':{'appId':app_id}},True)
groups=call('group.getAll')
everyone=next(x for x in groups if x['name']=='everyone')
call('group.savePartialSettings',{'id':everyone['id'],'settings':{'homeBoardId':board['id']}},True)
call('board.saveGroupBoardPermissions',{'entityId':board['id'],'permissions':[{'principalId':everyone['id'],'permission':'view'}]},True)
group=next((x for x in groups if x['name']=='homarr-admins'),None)
if group is None:
 call('group.createGroup',{'name':'homarr-admins'},True);group=next(x for x in call('group.getAll') if x['name']=='homarr-admins')
call('group.savePermissions',{'groupId':group['id'],'permissions':['admin']},True)
print('Homarr board and OIDC administrator group reconciled')
