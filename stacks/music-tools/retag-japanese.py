#!/usr/bin/env python3
"""Retag downloaded KHInsider albums to their Japanese MusicBrainz release.

Albums downloaded before the "Japanese titles" option carry English titles/
album/composer. This one-off migration maps each local file by (disc, track)
to the Japanese release, verifies the duration, then renames files and writes
title/album/artist/composer/date. ALBUMS holds the folder name and the
MusicBrainz release ID of the Japanese edition.

  plan   print the diff and write /tmp/retag-japanese/manifest.json
  apply  journal the old names/tags, then write tags and rename

Run it inside the khinsider container (it needs khinsider.py, the MusicBrainz
network access and mutagen; none of it is deployed as a service):

  ssh debian@192.168.10.101 \
    'sudo docker exec -i media-music-tools-khinsider-1 python3 - plan' \
    < stacks/music-tools/retag-japanese.py

The journal and manifest stay in /tmp/retag-japanese in the container; copy
them to /srv/media-stack/storage/retag-japanese/ for the weekly backup.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, '/tools')
import khinsider  # noqa: E402
from mutagen.easyid3 import EasyID3  # noqa: E402
from mutagen.mp3 import MP3  # noqa: E402

MUSIC = Path(os.environ.get('KHINSIDER_MUSIC', '/music'))
STATE = Path('/tmp/retag-japanese')
JP = re.compile(r'[\u3040-\u30ff\u4e00-\u9fff]')

ALBUMS = [
    ('Pokémon Red·Green Super Music Collection',
     '2f882e31-50b3-4edd-9abb-5ee6184427b2', '2016-04-27'),
    ('Pokémon Black 2 & White 2_ Super Music Collection',
     'c7f34845-c91c-48a6-b0fc-1d706c4dad39', '2012-07-25'),
    ('Pokémon X & Pokémon Y_ Super Music Collection',
     '52ef04c8-5dd1-45a1-968b-16143355ef90', '2013-11-13'),
    ("Pokémon_ Let's Go, Pikachu!・Let's Go, Eevee! Super Music Complete",
     '4fb34845-d9f0-4a04-94bd-5d2fd8d54872', '2018-12-01'),
    ('Nintendo 3DS Pokémon Sun & Moon Super Music Complete',
     '85a72730-3b44-4df4-aedf-68de9219024f', '2016-11-30'),
    ('Nintendo DS Pokémon HeartGold & SoulSilver Music Super Complete',
     '3e7d01f2-e620-4847-8618-d0df85b7b188', '2009-10-28'),
    ('Pokémon Omega Ruby & Alpha Sapphire Super Music Complete',
     '4d979311-6d6b-49db-9b8b-ac06bac2480d', '2014-12-03'),
    ('Pokémon LEGENDS Arceus Super Music Collection',
     'cb66f950-30c4-4f61-b9c5-dffed05701ad', '2024-02-27'),
    ('Pokémon Ruby & Sapphire Music Super Complete',
     '1a798f86-7522-4dc4-bb0b-d4074ca4ac57', '2003-04-26'),
    ('Pokémon FireRed & Pokémon LeafGreen_ Super Music Collection',
     '3970388b-3bc1-4ec7-bedc-a8f40b44757c', '2004-05-26'),
]


def fetch_release(release_id):
    url = (f'https://musicbrainz.org/ws/2/release/{release_id}'
           '?inc=recordings+artist-credits&fmt=json')
    for attempt in range(5):
        try:
            return khinsider.fetch_json(url)
        except urllib.error.HTTPError as error:
            if error.code == 503:
                time.sleep(4 * (attempt + 1))
                continue
            raise


def credit_name(parts):
    return ' & '.join((part.get('name') or (part.get('artist') or {}).get('name') or '')
                      for part in parts or [])


def release_tracks(release):
    tracks = {}
    for medium in release.get('media', []):
        for track in medium.get('tracks', []):
            tracks[(medium.get('position'), track.get('position'))] = {
                'title': track.get('title') or '',
                'length': (track.get('length') or 0) / 1000,
                'artist': credit_name(track.get('artist-credit')),
            }
    return tracks


def local_tracks(folder):
    tracks = {}
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith('.mp3'):
            continue
        path = folder / name
        tags = EasyID3(str(path))
        disc = int((tags.get('discnumber') or ['1'])[0])
        track = int((tags.get('tracknumber') or ['0'])[0])
        if track <= 0:
            raise SystemExit(f'tracknumber が無い: {path}')
        tracks[(disc, track)] = {'name': name, 'length': MP3(str(path)).info.length}
    return tracks


def plan_album(folder, release_id, date, work):
    release = work.get(release_id) or fetch_release(release_id)
    work[release_id] = release
    remote = release_tracks(release)
    album = release.get('title') or ''
    albumartist = credit_name(release.get('artist-credit'))
    local = local_tracks(folder)
    items = []
    unmatched = []
    used = {}
    for key in sorted(local):
        if key not in remote:
            unmatched.append(local[key]['name'])
            continue
        target = remote[key]
        if abs(local[key]['length'] - target['length']) > max(2.5, target['length'] * 0.03):
            unmatched.append(f"{local[key]['name']} (尺不一致)")
            continue
        base = khinsider.title_filename(target['title'], key[1])
        if base.lower() in used:
            used[base.lower()] += 1
            base = f'{base[:-4]} ({used[base.lower()]}).mp3'
        else:
            used[base.lower()] = 1
        items.append({
            'old': local[key]['name'], 'new': base,
            'disc': key[0], 'track': key[1],
            'title': target['title'], 'artist': target['artist'],
            'album': album, 'albumartist': albumartist, 'date': date,
        })
    return {
        'folder': folder.name, 'release_id': release_id, 'album': album,
        'albumartist': albumartist, 'date': date, 'items': items,
        'unmatched': unmatched,
        'missing': len(set(remote) - set(local)),
    }


def apply_album(plan):
    folder = MUSIC / 'Khinsider' / plan['folder']
    journal = []
    for item in plan['items']:
        old = folder / item['old']
        new = folder / item['new']
        tags = EasyID3(str(old))
        journal.append({'old': item['old'], 'new': item['new'], 'tags': dict(tags)})
        tags['title'] = item['title']
        tags['album'] = item['album']
        tags['albumartist'] = item['albumartist']
        tags['artist'] = item['artist']
        tags['composer'] = item['artist']
        tags['discnumber'] = str(item['disc'])
        tags['tracknumber'] = str(item['track'])
        tags['date'] = item['date']
        tags.save(str(old))
        if old != new:
            if new.exists():
                raise SystemExit(f'移動先が存在する: {new}')
            os.rename(old, new)
    return journal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['plan', 'apply'])
    args = parser.parse_args()
    plans = []
    work = {}
    for folder_name, release_id, date in ALBUMS:
        folder = MUSIC / 'Khinsider' / folder_name
        if not folder.is_dir():
            print(f'SKIP (無い): {folder_name}')
            continue
        plans.append(plan_album(folder, release_id, date, work))
        time.sleep(2.0)

    if args.action == 'plan':
        STATE.mkdir(parents=True, exist_ok=True)
        for plan in plans:
            print(f"== {plan['folder']}")
            print(f"   アルバム: {plan['album']} / {plan['albumartist']} / {plan['date']}")
            print(f"   対象 {len(plan['items'])} 曲 / 未対応 {len(plan['unmatched'])} / 未取得 {plan['missing']}")
            for item in plan['items'][:3]:
                print(f"   {item['disc']}-{item['track']:02d} {item['old'][:34]} -> {item['new'][:40]} | {item['artist'][:30]}")
            if plan['unmatched']:
                print('   未対応:', plan['unmatched'][:5])
        (STATE / 'manifest.json').write_text(
            json.dumps(plans, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'manifest: {STATE / "manifest.json"}')
    else:
        STATE.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime('%Y%m%d-%H%M%S')
        journal_path = STATE / f'journal-{stamp}.json'
        journal = []
        for plan in plans:
            journal.append({'plan': plan, 'files': apply_album(plan)})
            journal_path.write_text(json.dumps(journal, ensure_ascii=False, indent=1),
                                    encoding='utf-8')
            print(f"== applied: {plan['folder']} ({len(plan['items'])}曲)")
        print(f'journal: {journal_path}')


if __name__ == '__main__':
    main()
