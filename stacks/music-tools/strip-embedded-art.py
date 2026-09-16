#!/usr/bin/env python3
"""Remove embedded APIC artwork from MP3s, keeping a copy under /state.

Used to enforce the "cover.jpg only" policy: Navidrome falls back to embedded
art when an album has no folder image, and some source files carry wrong
images. Originals are copied to /state/organize/apic-backups/.
"""
import os
from pathlib import Path

import mutagen

root = Path('/music')
backup = Path('/state/organize/apic-backups')
files = 0
frames_total = 0
for dirpath, dirnames, filenames in os.walk(root):
    if 'Converted' in Path(dirpath).parts:
        continue
    for name in filenames:
        if not name.lower().endswith('.mp3'):
            continue
        path = Path(dirpath) / name
        try:
            audio = mutagen.File(str(path))
        except Exception:  # noqa: BLE001
            continue
        if audio is None or audio.tags is None or not getattr(audio.tags, 'getall', None):
            continue
        frames = audio.tags.getall('APIC')
        if not frames:
            continue
        relative = path.relative_to(root)
        target = backup / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        for index, frame in enumerate(frames):
            suffix = 'png' if 'png' in (frame.mime or '') else 'jpg'
            target.with_name(f'{name}.{index}.{suffix}').write_bytes(frame.data)
        audio.tags.delall('APIC')
        audio.save()
        os.utime(path, None)
        files += 1
        frames_total += len(frames)
print(f'files={files} frames={frames_total} backup={backup}')
