#!/usr/bin/env python3
"""Queue an audio URL through MeTube without using its GUI."""
import argparse,json,urllib.request,urllib.parse
from pathlib import Path
ports=Path(__file__).resolve().parents[1]/'sso/ports.env'
internal=dict(x.split('=',1) for x in ports.read_text().splitlines() if '=' in x) if ports.exists() else {}
endpoint='http://localhost:'+internal.get('METUBE_PORT','8081')
p=argparse.ArgumentParser();p.add_argument('url');p.add_argument('--format',choices=['mp3','m4a','opus','flac','wav'],default='mp3');p.add_argument('--endpoint',default=endpoint);a=p.parse_args()
if urllib.parse.urlsplit(a.url).scheme not in ['https','http']:p.error('Use an HTTP(S) media URL')
request=urllib.request.Request(a.endpoint.rstrip('/')+'/add',data=json.dumps({'url':a.url,'quality':'best','format':a.format}).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(request,timeout=60) as r:result=json.load(r)
if result.get('status')!='ok':raise SystemExit('MeTube rejected the request: '+str(result.get('msg','unknown error')))
print('Queued in MeTube; completed audio will be imported automatically')
