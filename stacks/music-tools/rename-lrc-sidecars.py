#!/usr/bin/env python3
"""Match orphaned .lrc sidecars to their renamed MP3 and rename them.

organize.py は 2026-09-18 以前、音声ファイルのリネーム時に .lrc を追従させて
いなかった。まず同じフォルダで、次にライブラリ全体で、曲名部分が一致し
.lrc を持たない MP3 が1つだけあるとき、その名前へ .lrc を移動して修復する。
既定はドライラン、--apply で実行し
/state/organize/lrc-rename-<timestamp>.json にジャーナルを残す。
"""
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(os.environ.get('LRC_MUSIC', '/music'))
STATE = Path(os.environ.get('LRC_STATE', '/state/organize'))


def title_key(stem):
    return re.sub(r'^\d+\s*-\s*', '', stem).strip().lower()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    mp3s = defaultdict(list)
    lrcs = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        if 'Converted' in Path(dirpath).parts:
            continue
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if name.lower().endswith('.mp3'):
                mp3s[title_key(path.stem)].append(path)
            elif name.lower().endswith('.lrc'):
                lrcs.append(path)

    def has_lrc(mp3):
        return mp3.with_suffix('.lrc').exists()

    renames = []
    ambiguous = []
    unmatched = []
    for lrc in sorted(lrcs):
        if lrc.with_suffix('.mp3').exists():
            continue
        candidates = [p for p in mp3s.get(title_key(lrc.stem), []) if not has_lrc(p)]
        if len(candidates) == 1:
            renames.append((lrc, candidates[0].with_suffix('.lrc')))
        elif len(candidates) > 1:
            ambiguous.append((lrc, candidates))
        else:
            unmatched.append(lrc)

    print(f'rename={len(renames)} ambiguous={len(ambiguous)} unmatched={len(unmatched)}')
    for source, target in renames[:40]:
        print(f'  {source.relative_to(ROOT)} -> {target.relative_to(ROOT)}')
    for path, candidates in ambiguous[:10]:
        print(f'  AMBIGUOUS {path.relative_to(ROOT)}: '
              f'{[str(c.relative_to(ROOT)) for c in candidates]}')
    for path in unmatched[:20]:
        print(f'  UNMATCHED {path.relative_to(ROOT)}')

    if args.apply and renames:
        journal = {'created': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                   'entries': []}
        for source, target in renames:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
            journal['entries'].append({'source': str(source.relative_to(ROOT)),
                                       'target': str(target.relative_to(ROOT))})
        for directory in sorted({str(lrc.parent) for lrc, _ in renames},
                                key=len, reverse=True):
            try:
                Path(directory).rmdir()
                journal['entries'].append(
                    {'rmdir': str(Path(directory).relative_to(ROOT))})
            except OSError:
                pass
        STATE.mkdir(parents=True, exist_ok=True)
        path = STATE / f'lrc-rename-{time.strftime("%Y%m%d-%H%M%S")}.json'
        path.write_text(json.dumps(journal, ensure_ascii=False, indent=1))
        print(f'journal: {path}')


if __name__ == '__main__':
    main()
