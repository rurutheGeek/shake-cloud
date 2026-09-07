#!/usr/bin/env python3
"""Apply explicitly listed MP3 tags, preserving a backup of the original ID3 block."""
import argparse,json,os
from pathlib import Path
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3,ID3NoHeaderError
p=argparse.ArgumentParser();p.add_argument('manifest');p.add_argument('--apply',action='store_true');args=p.parse_args()
root=Path('/music').resolve();manifest=json.loads(Path(args.manifest).read_text());allowed={'title','artist','album','albumartist','tracknumber','discnumber','date','genre','composer'}
plans=[]
for name,values in manifest.items():
 path=(root/name).resolve()
 if root not in path.parents or path.suffix.lower()!='.mp3' or not path.is_file():raise ValueError('Expected existing MP3 inside /music: '+name)
 if not isinstance(values,dict) or not set(values)<=allowed:raise ValueError('Unsupported tag fields: '+name)
 for value in values.values():
  if not isinstance(value,str) and not (isinstance(value,list) and all(isinstance(v,str) for v in value)):raise ValueError('Tag values must be strings or arrays of strings')
 plans.append((name,path,values))
for name,path,values in plans:
 try:tags=EasyID3(path)
 except ID3NoHeaderError:tags=EasyID3()
 changes={k:([v] if isinstance(v,str) else v) for k,v in values.items() if tags.get(k)!=([v] if isinstance(v,str) else v)}
 if not changes:print('OK:',name);continue
 print('APPLY:' if args.apply else 'PREVIEW:',name,','.join(changes))
 if not args.apply:continue
 backup=Path('/state/tag-backups')/(name+'.id3');backup.parent.mkdir(parents=True,exist_ok=True)
 if not backup.exists() and not backup.with_suffix('.no-id3').exists():
  try:ID3(path).save(backup)
  except ID3NoHeaderError:backup.with_suffix('.no-id3').touch()
 for key,value in changes.items():tags[key]=value
 tags.save(path)
 os.utime(path,None)
