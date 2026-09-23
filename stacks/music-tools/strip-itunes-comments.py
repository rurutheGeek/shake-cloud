#!/usr/bin/env python3
"""Remove iTunes junk COMM frames (iTunSMPB hex data) from MP3 files.

CD rippers and iTunes store gapless-playback data like
`00000000 000002a0 00000800 ...` in COMM frames, which shows up as a
mysterious comment in tag editors. Real comments are kept. The original ID3
is backed up under /state/organize/itunes-backups/.
"""
import os
import re
from pathlib import Path

from mutagen.id3 import ID3, ID3NoHeaderError

ROOT = Path(os.environ.get('ITUN_MUSIC', '/music'))
BACKUP = Path(os.environ.get('ITUN_BACKUP', '/state/organize/itunes-backups'))
HEX = re.compile(r'^\s*[0-9A-Fa-f]{2,8}(\s+[0-9A-Fa-f]+){2,}\s*$')


def main():
    removed = 0
    files = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        if 'Converted' in Path(dirpath).parts:
            continue
        for name in filenames:
            if not name.lower().endswith('.mp3'):
                continue
            path = Path(dirpath) / name
            try:
                tags = ID3(str(path))
            except ID3NoHeaderError:
                continue
            except Exception:  # noqa: BLE001
                continue
            junk = [frame for frame in tags.getall('COMM')
                    if HEX.match(frame.text[0] if frame.text else '')]
            if not junk:
                continue
            relative = str(path.relative_to(ROOT))
            backup = BACKUP / (relative + '.id3')
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                ID3(str(path)).save(str(backup))
            for frame in junk:
                tags.pop(frame.HashKey, None)
                removed += 1
            tags.save(str(path))
            os.utime(path, None)
            files += 1
    print(f'removed_comments={removed} files={files}')


if __name__ == '__main__':
    main()
