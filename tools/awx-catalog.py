#!/usr/bin/env python3
"""List the playbooks for AWX and for docs/operations/playbooks.md.

Each playbook's leading comment is the source: its first line becomes the name
and the rest (without the example command lines) becomes the description, so
the AWX job templates and the document cannot drift from the playbooks.

  python3 tools/awx-catalog.py --json      # what platform/awx/configure.yml registers
  python3 tools/awx-catalog.py             # write docs/operations/playbooks.md
  python3 tools/awx-catalog.py --check     # fail if the document is out of date
"""
import datetime
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PLAYBOOKS = ROOT / 'platform' / 'ansible'
DOC = ROOT / 'docs' / 'operations' / 'playbooks.md'

# 種類（AWX のラベル）。上から順に最初に合ったものを使う。
CATEGORIES = [
    ('Proxmox', lambda name, hosts: name.startswith('pve-') or name == 'survey-pve'),
    ('Kubernetes', lambda name, hosts: name == 'kubernetes'),
    ('メディア', lambda name, hosts: hosts <= {'media'} and bool(hosts)),
    ('アプリ', lambda name, hosts: hosts == {'apps'}),
    ('監視', lambda name, hosts: 'monitoring' in hosts or name in ('node-exporter', 'storage-health')),
    ('認証・入口', lambda name, hosts: name in ('identity', 'edge')),
    ('クラウド', lambda name, hosts: name in ('cloud', 'garage', 'verify-cloud')),
    ('共通', lambda name, hosts: True),
]

# 基盤を変えるもの。AWX では既定を「確認だけ」（check）にする。
CAREFUL = {'site', 'guests', 'identity', 'edge', 'cloud', 'garage', 'kubernetes', 'storage-health'}

# AWX のインベントリ（NetBox と Proxmox 本体）に居ないホストへ流すもの。
# 理由を一覧に出し、AWX には登録しない。
LOCAL_ONLY = {
    'deploy': '旧来の一括配備（stacks/compose.yaml）。いまは media-*.yml を個別に流す',
    'minecraft': 'Minecraft サーバは NetBox の台帳に無い（minecraft 群）',
    'netbox': 'NetBox 自身を作る。NetBox より前に流すので seed.ini を使う',
    'public-monitor': '外部の監視点（outpost.ini）',
    'raspberry-pi': 'Raspberry Pi は NetBox の台帳に無い（raspberry_pi 群）',
    'relay': '中継サーバは NetBox の台帳に無い（relay 群）',
    'shake-web': '公開サイトのサーバは NetBox の台帳に無い（web 群）',
}


def header(path):
    lines = []
    for line in path.read_text().splitlines():
        if line.startswith('---') and not lines:
            continue
        if not line.startswith('#'):
            break
        lines.append(line[1:].removeprefix(' '))
    return lines


def is_command(line):
    return bool(re.search(r'ansible-playbook|sops exec-env|^\s+\.\.\.|\\$|^\s+[\'"]', line))


def hosts_of(plays):
    found = set()
    for play in plays:
        if isinstance(play, dict) and 'hosts' in play:
            for part in re.split(r'[:,]', str(play['hosts'])):
                part = part.strip()
                if part and '{{' not in part:
                    found.add(part)
    return found


def playbooks():
    items = []
    for path in sorted(PLAYBOOKS.glob('*.yml')):
        plays = yaml.safe_load(path.read_text())
        if not isinstance(plays, list) or not any(
                isinstance(play, dict) and ('hosts' in play or 'ansible.builtin.import_playbook' in play
                                            or 'import_playbook' in play) for play in plays):
            continue
        name = path.stem
        lines = header(path)
        text = [line for line in lines if not is_command(line)]
        # 最初の段落の最初の文を題名にする（1文が2行にまたがるものがある）。
        paragraph = []
        for line in text:
            if not line.strip():
                break
            paragraph.append(line.strip())
        first = ''.join(paragraph)
        title = (first.split('。')[0] if '。' in first else first).strip() or name
        description = '\n'.join(text).strip()
        hosts = hosts_of(plays)
        category = next(label for label, test in CATEGORIES if test(name, hosts))
        items.append({
            'file': path.name,
            'name': name,
            'title': title,
            'description': description,
            'hosts': sorted(hosts),
            'category': category,
            'job_type': 'check' if name in CAREFUL or category == 'Proxmox' else 'run',
            'local_only': LOCAL_ONLY.get(name, ''),
        })
    return items


def markdown(items, updated):
    out = ['---', 'title: Playbook の一覧', f'updated: {updated}', 'section: 運用手順', 'audience: 管理者',
           'tags:', '  - ops', '  - awx', '---', '', '# Playbook の一覧', '',
           f'> **更新日** {updated} ・ **区分** 運用手順 ・ **読む人** 管理者', '',
           '<!-- python3 tools/awx-catalog.py が platform/ansible/*.yml の先頭コメントから生成する。直接編集しない。 -->', '']
    for category in [label for label, _ in CATEGORIES]:
        rows = [item for item in items if item['category'] == category]
        if not rows:
            continue
        out += [f'## {category}', '', '| Playbook | 何をするか | 対象 | AWX |', '| --- | --- | --- | --- |']
        for item in rows:
            if item['local_only']:
                awx = f"手元専用（{item['local_only']}）"
            elif item['job_type'] == 'check':
                awx = '既定は確認だけ'
            else:
                awx = '実行'
            hosts = '・'.join(f'`{host}`' for host in item['hosts']) or '—'
            out.append(f"| `{item['file']}` | {item['title']} | {hosts} | {awx} |")
        out.append('')
    return '\n'.join(out)


def main():
    items = playbooks()
    if '--json' in sys.argv:
        print(json.dumps(items, ensure_ascii=False))
        return
    # 更新日は中身が変わったときだけ今日にする（--check を日付で落とさない）。
    current = DOC.read_text() if DOC.exists() else ''
    found = re.search(r'^updated: (\S+)$', current, re.M)
    kept = found.group(1) if found else ''
    if kept and current == markdown(items, kept):
        return
    if '--check' in sys.argv:
        sys.exit('docs/operations/playbooks.md is out of date: run python3 tools/awx-catalog.py')
    DOC.write_text(markdown(items, datetime.date.today().isoformat()))


if __name__ == '__main__':
    main()
