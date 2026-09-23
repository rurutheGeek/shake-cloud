"""Embed .lrc sidecar lyrics as SYLT (synced) into the MP3.

Navidrome 0.64 の Web プレイヤーは、曲レコードの歌詞のうち `synced: true` の
項目だけを LRC に変換して表示する。外部 .lrc は API では同期で返るが DB の
lyrics 列には非同期として入るため、SYLT として埋め込んで再スキャンさせる。
タイムスタンプ付きの .lrc のみ対象（プレーンテキストは対象外）。
元の ID3 は /state/organize/sylt-backups/ に保存する。
"""
import os
import re
from pathlib import Path

from mutagen.id3 import ID3, ID3NoHeaderError, SYLT

STAMP = re.compile(r'^\[(\d+):(\d+)(?:[.:](\d+))?\]\s*(.*)$')
ROOT = Path('/music')
BACKUP = Path('/state/organize/sylt-backups')


def parse_lrc(text):
    entries = []
    for line in text.splitlines():
        m = STAMP.match(line.strip())
        if not m:
            continue
        minutes, seconds, frac, value = m.groups()
        ms = int(minutes) * 60000 + int(seconds) * 1000
        if frac:
            ms += int(frac.ljust(3, '0')[:3]) if len(frac) >= 3 else int(frac) * 10
        entries.append((value, ms))
    return entries


changed = 0
for dirpath, dirnames, filenames in os.walk(ROOT):
    if 'Converted' in Path(dirpath).parts:
        continue
    for name in filenames:
        if not name.lower().endswith('.mp3'):
            continue
        path = Path(dirpath) / name
        lrc = path.with_suffix('.lrc')
        if not lrc.exists():
            continue
        entries = parse_lrc(lrc.read_text(encoding='utf-8', errors='replace'))
        if not entries:
            continue
        try:
            tags = ID3(str(path))
        except ID3NoHeaderError:
            tags = ID3()
        backup = BACKUP / (str(path.relative_to(ROOT)) + '.id3')
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            try:
                ID3(str(path)).save(str(backup))
            except ID3NoHeaderError:
                backup.with_suffix('.no-id3').touch()
        tags.delall('USLT')
        tags.delall('SYLT')
        tags.add(SYLT(encoding=3, lang='jpn', format=2, type=1, desc='',
                      text=[(value, ms) for value, ms in entries]))
        tags.save(str(path))
        os.utime(path, None)
        changed += 1
print('embedded SYLT:', changed)
