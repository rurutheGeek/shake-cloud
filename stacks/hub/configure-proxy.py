#!/usr/bin/env python3
"""Configure Authentik's embedded forward-auth outpost and media access group."""
import runpy
from pathlib import Path
ctx=runpy.run_path(str(Path(__file__).with_name('configure-oidc.py')))
api,rows,flows=ctx['api'],ctx['rows'],ctx['flows']
groups=rows('core/groups/?name=media-users')
group=groups[0] if groups else api('POST','core/groups/',json={'name':'media-users'})
admin=rows('core/users/?username=akadmin')[0]
if group['pk'] not in admin['groups']:
 api('PATCH',f"core/users/{admin['pk']}/",json={'groups':admin['groups']+[group['pk']]})
providers={x['name']:x for x in rows('providers/proxy/')};ids=[]
for name,port in [('navidrome',4533),('metube',8081)]:
 data={'name':name,'authorization_flow':flows['default-provider-authorization-implicit-consent'],
       'invalidation_flow':flows['default-provider-invalidation-flow'],
       'mode':'forward_single','external_host':f'http://localhost:{port}'}
 old=providers.get(name)
 provider=api('PATCH' if old else 'POST',f"providers/proxy/{old['pk']}/" if old else 'providers/proxy/',json=data)
 ids.append(provider['pk']);apps={x['slug']:x for x in rows('core/applications/')}
 api('PATCH' if name in apps else 'POST',f'core/applications/{name}/' if name in apps else 'core/applications/',json={
  'name':name.title(),'slug':name,'provider':provider['pk'],'meta_launch_url':data['external_host']})
outpost=next(x for x in rows('outposts/instances/') if x['name']=='authentik Embedded Outpost')
config=outpost['config'];identity_url='https://login.localhost:9443' if (Path(__file__).resolve().parents[1]/'sso/trust/ca-bundle.pem').exists() else 'http://auth.localhost:9000'
config.update(authentik_host=identity_url,authentik_host_browser=identity_url)
api('PATCH',f"outposts/instances/{outpost['pk']}/",json={'providers':sorted(set(outpost['providers']+ids)),'config':config})
# Grant the managed media group; never grant this group administrator privileges.
bindings=rows('policies/bindings/')
for app in rows('core/applications/'):
 if app['slug'] not in ['homarr','nextcloud','kavita','vaultwarden','navidrome','metube']:continue
 if not any(x['target']==app['pk'] and x.get('group')==group['pk'] for x in bindings):
  api('POST','policies/bindings/',json={'target':app['pk'],'group':group['pk'],'order':10})
print('Media access and embedded proxy providers reconciled')

admin_group=rows('core/groups/?name=homarr-admins')[0]
app=next(x for x in rows('core/applications/') if x['slug']=='netbox')
if not any(x['target']==app['pk'] and x.get('group')==admin_group['pk'] for x in rows('policies/bindings/')):
 api('POST','policies/bindings/',json={'target':app['pk'],'group':admin_group['pk'],'order':10})
print('NetBox SSO restricted to the administrator group')
