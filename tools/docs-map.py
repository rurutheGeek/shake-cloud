#!/usr/bin/env python3
"""Regenerate the page list in docs/map.md from each page's own front matter.

The map is the one place that claims to list every page, so it has to be
derived rather than maintained by hand: a page added without touching the map
would otherwise be invisible in Obsidian's graph and in the site's index.

    python3 tools/docs-map.py          # rewrite docs/map.md
    python3 tools/docs-map.py --check  # fail if it is out of date (used by tests)
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
MAP = DOCS / 'map.md'
START, END = '<!-- pages:start -->', '<!-- pages:end -->'

# Section order on the page. Anything else is appended under その他.
ORDER = ['入口', '利用ガイド', '開発計画', '運用手順', '設計', 'リファレンス', '記録']
SKIP = {'map.md', 'assets/js/README.md'}


def front_matter(path):
    text = path.read_text(encoding='utf-8')
    if not text.startswith('---\n'):
        return None
    block = text.split('\n---\n', 1)[0][4:]
    meta = {}
    key = None
    for line in block.split('\n'):
        if line.startswith('  - ') and key:
            meta.setdefault(key, []).append(line[4:].strip())
        elif ':' in line:
            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip()
            if value:
                meta[key] = value
    return meta


def collect():
    pages = {}
    for path in sorted(DOCS.rglob('*.md')):
        rel = path.relative_to(DOCS).as_posix()
        if rel in SKIP:
            continue
        meta = front_matter(path)
        if not meta:
            continue
        pages.setdefault(meta.get('section', 'その他'), []).append((rel, meta))
    return pages


def render(pages):
    lines = []
    sections = [s for s in ORDER if s in pages] + [s for s in pages if s not in ORDER]
    for section in sections:
        rows = sorted(pages[section], key=lambda item: item[0])
        lines.append(f'### {section}')
        lines.append('')
        lines.append('| ページ | 更新日 | タグ |')
        lines.append('| --- | --- | --- |')
        for rel, meta in rows:
            tags = ' '.join(f'`{t}`' for t in meta.get('tags', []))
            lines.append(f"| [{meta.get('title', rel)}]({rel}) | {meta.get('updated', '—')} | {tags} |")
        lines.append('')
    lines.append(f'全 {sum(len(v) for v in pages.values())} ページ。この表は `tools/docs-map.py` が各ページの front matter から生成します。')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()

    text = MAP.read_text(encoding='utf-8')
    body = render(collect())
    new = re.sub(
        re.escape(START) + r'.*?' + re.escape(END),
        f'{START}\n\n{body}\n\n{END}',
        text,
        flags=re.S,
    )
    if args.check:
        if new != text:
            print('docs/map.md is out of date: run python3 tools/docs-map.py', file=sys.stderr)
            return 1
        return 0
    if new != text:
        MAP.write_text(new, encoding='utf-8')
        print('updated docs/map.md')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
