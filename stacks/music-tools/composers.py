#!/usr/bin/env python3
"""Set composer from the album artist for soundtrack/classical albums.

Game and classical albums usually credit the composer as album artist, so this
fills an empty TCOM. Writes /state/composers-corrections.json for
organize.py plan --no-lookup --corrections.
"""
import collections
import json
import os
from pathlib import Path

import mutagen

ROOT = Path(os.environ.get('COMPOSER_MUSIC', '/music'))
OUT = Path(os.environ.get('COMPOSER_OUT', '/state/composers-corrections.json'))
SKIP = {'', 'various artists', 'various', 'unknown', 'unknown artist'}

stats = collections.Counter()
corrections = {}
for dirpath, dirnames, filenames in os.walk(ROOT):
    if 'Converted' in Path(dirpath).parts:
        continue
    for name in sorted(filenames):
        if not name.lower().endswith('.mp3'):
            continue
        path = Path(dirpath) / name
        tags = {}
        try:
            easy = mutagen.File(str(path), easy=True)
            if easy is not None and easy.tags is not None:
                for key in ('albumartist', 'genre', 'composer', 'artist'):
                    values = easy.tags.get(key)
                    if values:
                        tags[key] = str(values[0])
        except Exception:  # noqa: BLE001
            stats['unreadable'] += 1
            continue
        if tags.get('composer'):
            stats['has_composer'] += 1
            continue
        if tags.get('genre') not in ('Soundtrack', 'Game', 'Classical'):
            stats['skipped_genre'] += 1
            continue
        albumartist = tags.get('albumartist', '')
        if albumartist.strip().lower() in SKIP:
            stats['skipped_various'] += 1
            continue
        corrections[str(path.relative_to(ROOT))] = {'composer': albumartist}
        stats['set'] += 1

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({'files': corrections}, ensure_ascii=False, indent=1))
print(dict(stats), 'corrections', len(corrections))
