#!/usr/bin/env python3
"""Reject instance state and known local secrets in the staged Git snapshot."""
import json,re,subprocess
import yaml
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
def collect_needles():
 for path in [ROOT/'stacks/.env',ROOT/'stacks/netbox/.env']:
  if path.exists():
   for line in path.read_text().splitlines():
    if '=' in line:
     k,v=line.split('=',1);walk(v.strip("'\""),k)
 for path in [ROOT/'stacks/runtime/access.json',ROOT/'stacks/runtime/accounts.json',ROOT/'stacks/runtime/user-bootstrap.json']:
  if path.exists():walk(json.loads(path.read_text()))
 for folder in [ROOT/'stacks/secrets',ROOT/'stacks/netbox/secrets']:
  if folder.exists():
   for path in folder.iterdir():
    if path.is_file():
     value=path.read_bytes().strip()
     if path.suffix=='.json':walk(json.loads(value))
     elif len(value)>=12:needles.add(value)
 cookies=ROOT/'stacks/music-tools/storage/state/cookies.txt'
 if cookies.exists():
  for line in cookies.read_text().splitlines():
   fields=line.split('\t')
   if len(fields)==7 and len(fields[-1])>=12:needles.add(fields[-1].encode())
# 認証情報らしい文字列。URLのパスワードはプレースホルダ・例を除く。
CREDENTIAL=re.compile(rb'|'.join([
 rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
 rb'gh[pousr]_[A-Za-z0-9]{30,}',
 rb'github_pat_[A-Za-z0-9_]{22,}',
 rb'AGE-SECRET-KEY-1[0-9A-Z]{50,}',
 rb'PVEAPIToken=[^\s]+=[0-9a-f]{8}-[0-9a-f-]{27}',
 rb'tskey-(?:auth|api|client)-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?',
 rb'sca_[a-z2-7]{20}\.[A-Za-z0-9_-]{43}',
 rb'discord(?:app)?\.com/api/webhooks/[0-9]{15,}/[A-Za-z0-9_-]{30,}',
 rb'[MNO][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}',
 rb'xox[abprs]-[A-Za-z0-9-]{10,}',
 rb'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b',
 rb'[a-z][a-z0-9+.-]*://[^\s:/@\'"]+:(?!(?:[^@\s]*)(?:example|changeme|password|postgres|secret|xxx|dummy|placeholder|\$|\{|<|%|\*|\.\.\.))[^\s:/@\'"]{8,}@[^\s/\'"]+',
]))
def sops_plaintext(text):
 """`*.sops.yaml` で ENC[ で始まらない値を返す（`sops:` 以外の全リーフ文字列。空文字は許す）。"""
 data=yaml.safe_load(text)
 if not isinstance(data,dict):return ['(not a mapping)']
 bad=[]
 def check(v,path):
  if isinstance(v,dict):
   for k,x in v.items():check(x,f'{path}.{k}')
  elif isinstance(v,list):
   for i,x in enumerate(v):check(x,f'{path}[{i}]')
  elif isinstance(v,str) and v and not v.startswith('ENC['):bad.append(path)
 for k,v in data.items():
  if k!='sops':check(v,k)
 return bad
def main():
 collect_needles()
 failures=[];files=[x for x in git('ls-files','-z').decode().split('\0') if x]
 state_suffix=('.tfstate','.tfstate.backup','.tfvars','.tfplan','.kubeconfig','.agekey')
 for name in files:
  parts=Path(name).parts
  if any(x in ['storage','library','backups','runtime','secrets','trust','.terraform'] for x in parts) or Path(name).name in ['.env','RUNNING.md','oidc-secrets.json','cookies.txt','compose.integrations.yaml','compose.sso.yaml','ports.env','kubeconfig','talosconfig','age-key.txt']:
   failures.append((name,'instance file'))
  elif name.endswith(state_suffix):failures.append((name,'infrastructure state or variables'))
  elif name.endswith('.sops.yaml') and Path(name).name!='.sops.yaml' and sops_plaintext(git('show',':'+name).decode()):failures.append((name,'sops file with plaintext values'))
  blob=git('show',':'+name)
  if any(needle in blob for needle in needles):failures.append((name,'known local secret'))
  if CREDENTIAL.search(blob):failures.append((name,'credential pattern'))
 for name,reason in failures:print(f'REJECT: {name}: {reason}')
 if failures:raise SystemExit(1)
 print(f'PASS: {len(files)} staged files; no instance files or known local secrets detected')
if __name__=='__main__':main()
