#!/usr/bin/env python3
"""Fetch lyrics from LRCLIB and save them as .lrc sidecar files.

Navidrome reads sidecar lyrics next to the audio file. Existing .lrc files are
kept. Matching prefers the same duration (file length) and synced lyrics; when
only plain lyrics exist, they are saved without timestamps.

LYRICS_REFRESH_PLAIN=1 を付けると、タイムスタンプの無い .lrc だけを対象に
再取得し、同期歌詞が見つかったときだけ置き換える（Web UI は同期歌詞のみ
表示するため。2026-09-17）。

Run inside the tagger container:

  run --rm --entrypoint python3 tagger /tools/lyrics.py
"""
import collections
import concurrent.futures
import unicodedata
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


# media-01 のコンテナは IPv6 を先に試し、LRCLIB/iTunes などで 20 秒待たされる。
# IPv4 を優先して名前解決する（2026-09-15 実測）。
import socket as _socket

_getaddrinfo = _socket.getaddrinfo


def _getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return _getaddrinfo(host, port, _socket.AF_INET, type, proto, flags)


_socket.getaddrinfo = _getaddrinfo_ipv4


import mutagen

ROOT = Path(os.environ.get('LYRICS_MUSIC', '/music'))
REPORT = Path(os.environ.get('LYRICS_REPORT', '/state/lyrics-report.json'))
API = 'https://lrclib.net/api/search'
UA = 'shake-cloud-lyrics/1.0 (+https://github.com/rurutheGeek/shake-cloud)'
INTERVAL = 0.5
WORKERS = 3
REFRESH_PLAIN = os.environ.get('LYRICS_REFRESH_PLAIN') == '1'
TIMED = re.compile(r'\[\d+:\d+')


def read_track(path):
    tags = {}
    length = 0
    try:
        easy = mutagen.File(str(path), easy=True)
        if easy is not None and easy.tags is not None:
            for key in ('title', 'artist', 'album', 'genre'):
                values = easy.tags.get(key)
                if values:
                    tags[key] = str(values[0])
        audio = mutagen.File(str(path))
        if audio is not None:
            length = int(getattr(audio.info, 'length', 0) or 0)
    except Exception:  # noqa: BLE001
        return None, 0
    return tags, length


class Limiter:
    def __init__(self, interval):
        self.interval = interval
        self.lock = threading.Lock()
        self.next_time = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_time - now)
            self.next_time = max(now, self.next_time) + self.interval
        if delay:
            time.sleep(delay)


limiter = Limiter(INTERVAL)
stats = collections.Counter()
stats_lock = threading.Lock()


def bump(key):
    with stats_lock:
        stats[key] += 1


def search(title, artist):
    query = urllib.parse.urlencode({'track_name': title, 'artist_name': artist})
    request = urllib.request.Request(f'{API}?{query}', headers={'User-Agent': UA})
    limiter.wait()
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503, 504):
                time.sleep(1 + attempt)
                continue
            return []
        except (urllib.error.URLError, OSError):
            time.sleep(1 + attempt)
    return []


def normalize(text):
    return unicodedata.normalize('NFKC', text or '').strip().lower()


def choose_title_only(results, title, length):
    key = normalize(title)
    best = None
    for entry in results:
        if entry.get('instrumental'):
            continue
        if normalize(entry.get('trackName')) != key:
            continue
        duration = entry.get('duration') or 0
        delta = abs(duration - length) if (duration and length) else 999
        synced = bool(entry.get('syncedLyrics'))
        plain = bool(entry.get('plainLyrics'))
        if not synced and not plain:
            continue
        if delta > (15 if synced else 8):
            continue
        score = (0 if delta <= 3 else 1, 0 if synced else 1)
        if best is None or score < best[0]:
            best = (score, entry)
    return best[1] if best else None


def choose(results, length):
    best = None
    for entry in results:
        if entry.get('instrumental'):
            continue
        duration = entry.get('duration') or 0
        delta = abs(duration - length) if (duration and length) else 999
        synced = bool(entry.get('syncedLyrics'))
        plain = bool(entry.get('plainLyrics'))
        if not synced and not plain:
            continue
        if delta > 5:
            continue
        score = (0 if delta <= 2 else 1, 0 if synced else 1)
        if best is None or score < best[0]:
            best = (score, entry)
    return best[1] if best else None


SKIP_ALBUM = ('サウンドトラック', 'Original Soundtrack', 'OST', 'サントラ', 'スーパーミュージック',
              'ゲーム音源', 'ピアノ', 'オルゴール', 'ミュージックコレクション', 'Music Collection',
              'Soundtrack', 'クラシック')


def skip(tags):
    genre = (tags.get('genre') or '').strip()
    if genre == 'Classical':
        return True
    if genre in ('Soundtrack', 'Game'):
        album = (tags.get('album') or '').lower()
        if any(word.lower() in album for word in SKIP_ALBUM):
            return True
    return False


process_count = 0


def process(path):
    global process_count
    lrc = path.with_suffix('.lrc')
    existing_plain = False
    if lrc.exists():
        if not REFRESH_PLAIN:
            bump('exists')
            return
        existing_plain = not TIMED.search(lrc.read_text(encoding='utf-8', errors='replace'))
        if not existing_plain:
            bump('exists')
            return
    tags, length = read_track(path)
    if tags is None:
        bump('unreadable')
        return
    if skip(tags):
        bump('skipped')
        process_count += 1
        if process_count % 100 == 0:
            print(process_count, dict(stats), flush=True)
        return
    title = tags.get('title') or path.stem
    artist = tags.get('artist') or tags.get('albumartist') or ''
    results = search(title, artist)
    entry = choose(results, length)
    if entry is None and tags.get('albumartist') and tags['albumartist'] != artist:
        entry = choose(search(title, tags['albumartist']), length)
    if entry is None:
        entry = choose_title_only(search(title, ''), title, length)
    if entry is None:
        bump('not_found')
        process_count += 1
        if process_count % 100 == 0:
            print(process_count, dict(stats), flush=True)
        return
    text = entry.get('syncedLyrics') or entry.get('plainLyrics') or ''
    if not text.strip():
        bump('not_found')
        return
    if existing_plain and not entry.get('syncedLyrics'):
        bump('plain_kept')
        return
    lrc.write_text(text, encoding='utf-8')
    bump('synced' if entry.get('syncedLyrics') else 'plain')
    process_count += 1
    if process_count % 100 == 0:
        print(process_count, dict(stats), flush=True)


def main():
    paths = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        if 'Converted' in Path(dirpath).parts:
            continue
        for name in sorted(filenames):
            if name.lower().endswith('.mp3'):
                paths.append(Path(dirpath) / name)
    print(f'tracks={len(paths)}', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(process, paths))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(dict(stats), ensure_ascii=False, indent=1))
    print(dict(stats), flush=True)


if __name__ == '__main__':
    main()
