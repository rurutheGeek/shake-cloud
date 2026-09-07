#!/usr/bin/env python3
"""Reject instance state and known local secrets in the staged Git snapshot."""
import json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def git(*args):return subprocess.check_output(['git','-c',f'safe.directory={ROOT}',*args],cwd=ROOT)
secret_key=re.compile(r'password|secret|token|pepper|private.?key',re.I)
needles=set()
def walk(value,key=''):
 if isinstance(value,dict):
  for k,v in value.items():walk(v,k)
 elif isinstance(value,list):
  for v in value:walk(v,key)
 elif isinstance(value,str) and secret_key.search(key) and len(value)>=12:needles.add(value.encode())
for path in [ROOT/'.env',ROOT/'hub/.env',ROOT/'netbox/.env']:
 if path.exists():
  for line in path.read_text().splitlines():
   if '=' in line:
    k,v=line.split('=',1);walk(v.strip("'\""),k)
for path in [ROOT/'hub/oidc-secrets.json',ROOT/'runtime/access.json',ROOT/'runtime/accounts.json',ROOT/'runtime/user-bootstrap.json']:
 if path.exists():walk(json.loads(path.read_text()))
for folder in [ROOT/'secrets',ROOT/'netbox/secrets']:
 if folder.exists():
  for path in folder.iterdir():
   if path.is_file():
    value=path.read_bytes().strip()
    if path.suffix=='.json':walk(json.loads(value))
    elif len(value)>=12:needles.add(value)
cookies=ROOT/'music-tools/storage/state/cookies.txt'
if cookies.exists():
 for line in cookies.read_text().splitlines():
  fields=line.split('\t')
  if len(fields)==7 and len(fields[-1])>=12:needles.add(fields[-1].encode())
failures=[];files=[x for x in git('ls-files','-z').decode().split('\0') if x]
for name in files:
 parts=Path(name).parts
 if any(x in ['storage','library','backups','runtime','secrets','trust'] for x in parts) or Path(name).name in ['.env','RUNNING.md','oidc-secrets.json','cookies.txt','compose.integrations.yaml','compose.sso.yaml','ports.env']:
  failures.append((name,'instance file'))
 blob=git('show',':'+name)
 if any(needle in blob for needle in needles):failures.append((name,'known local secret'))
 if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}',blob):failures.append((name,'credential pattern'))
for name,reason in failures:print(f'REJECT: {name}: {reason}')
if failures:raise SystemExit(1)
print(f'PASS: {len(files)} staged files; no instance files or known local secrets detected')
