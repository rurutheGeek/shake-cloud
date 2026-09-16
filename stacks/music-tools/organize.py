#!/usr/bin/env python3
"""Plan and apply library organization for Navidrome (music-tools on media-01).

The shared music library is edited from several sides (MeTube writes to
music/YouTube, the BCSTM converter writes to music/Converted, the tag API
rewrites tags). This tool only touches .mp3 files outside Converted and never
deletes audio. It works in three steps:

  plan   scan /music, match releases/tracks against MusicBrainz, fall back to
         existing tags and filenames, fetch cover art candidates, then write
         manifest.json and report.md (nothing in /music changes).
  apply  execute a reviewed manifest: back up ID3, write tags, move files,
         place cover.jpg, remove WMP leftovers in emptied folders.
  undo   reverse one apply run using its journal.

Usage (tagger service on media-01):

  sudo docker compose --env-file music-tools/.env -f music-tools/compose.yaml \\
    -f music-tools/compose.lock.yaml run --rm --entrypoint python3 tagger \\
    /tools/organize.py plan --out /state/organize

  sudo docker compose ... run --rm --entrypoint python3 tagger \\
    /tools/organize.py apply --manifest /state/organize/manifest.json
"""
import argparse
import collections
import dataclasses
import difflib
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
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


USER_AGENT = 'shake-cloud-music-organize/1.0 (+https://github.com/rurutheGeek/shake-cloud)'
MB_API = 'https://musicbrainz.org/ws/2'
CAA_API = 'https://coverartarchive.org'
ITUNES_API = 'https://itunes.apple.com/search'
DEEZER_API = 'https://api.deezer.com/search/album'
DEFAULT_ROOT = '/music'
DEFAULT_STATE = '/state'
EXCLUDED_DIRS = {'Converted'}
AUDIO_SUFFIX = '.mp3'
TAG_FIELDS = ('title', 'artist', 'album', 'albumartist', 'tracknumber',
              'discnumber', 'date', 'genre', 'composer')
INVALID_TAG_VALUES = {'', 'none', 'null', 'unknown', 'unknown artist', 'various'}
JUNK_IMAGE_NAMES = re.compile(
    r'^(albumart(small)?|folder|cover|front|back|disc|cd)(\s*\(\d+\))?(\.(jpe?g|png|bmp|gif))?$', re.I)
WMP_JUNK = re.compile(r'^(albumartsmall|folder)(\s*\([^)]*\))?\.(jpe?g|png)$', re.I)
JUNK_DELETE = re.compile(
    r'^(albumartsmall|folder|cover|front)(\s*\([^)]*\))?\.(jpe?g|png|bmp|gif)$', re.I)
COVER_JUNK_ARTISTS = re.compile(
    r'(cover|tribute|piano|orgel|lullaby|music box|8-?bit|chiptune|arcade|karaoke|'
    r'カバー|オルゴール|ピアノ|弾いてみた|アレンジ|作業用|勉強|睡眠)', re.I)
RELEASE_MIN_SCORE = 0.86
TRACK_MIN_SCORE = 0.84
RECORDING_MIN_SCORE = 0.90
RECORDING_TITLE_SCORE = 0.95
COVER_MIN_SCORE = 0.76
COVER_MIN_BYTES = 8000


def bump(stats, key, step=1):
    stats[key] = stats.get(key, 0) + step


def normalize(text):
    """NFKC + lowercase + punctuation collapse, for comparisons."""
    text = unicodedata.normalize('NFKC', text or '').lower()
    text = re.sub(r'[\[\]【】()（）「」『』~〜\-–—_:：/／.,、。!！?？\'"’“”]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def similarity(a, b):
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def has_cjk(text):
    return bool(re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', text or ''))


def valid_tag(value):
    return bool(value) and str(value).strip().lower() not in INVALID_TAG_VALUES


def strip_title_prefix(raw):
    """'時闇空「やみのかこう」' -> 'やみのかこう', '【MV】...' -> '...'."""
    text = (raw or '').strip()
    for pattern in (r'^[^「『]{0,16}[「『](.+?)[」』]$',
                    r'^[^「『]{0,16}[「『](.+)$',
                    r'^【[^】]{0,20}】\s*(.+)$',
                    r'^\[[^\]]{0,20}\]\s*(.+)$'):
        match = re.match(pattern, text)
        if match and match.group(1).strip():
            text = match.group(1).strip()
    return text


def clean_for_search(raw):
    """Drop video-site decorations so MusicBrainz has a chance to match."""
    text = unicodedata.normalize('NFKC', raw or '')
    text = re.sub(r'[【\[（(][^】\]）)]*?(mv|pv|公式|高音質|高画質|音源|素材|'
                  r'full\s*size|full|op|ed|ost|bgm|off\s*vocal)[^】\]）)]*?[】\]）)]',
                  ' ', text, flags=re.I)
    text = re.sub(r'高音質[^\s]*|高画質[^\s]*|音源|素材|フルバージョン|off\s*vocal',
                  ' ', text, flags=re.I)
    text = re.sub(r'&fmt=\d+|\d{3,4}p\d*|\.mp4|\.mp3', ' ', text, flags=re.I)
    text = re.sub(r'\b(HD|HQ|full|ver\.?)\b', ' ', text, flags=re.I)
    text = re.sub(r'[\s　]+', ' ', text).strip(' -–—_')
    return text or raw


def filename_to_title(stem):
    text = stem.replace('_', ' ').strip()
    text = re.sub(r'\s+', ' ', text)
    return strip_title_prefix(text)


def filename_album_hint(stem):
    """'Title – Album_ Original Soundtrack OST' -> (title, album hint)."""
    match = re.match(r'^(?P<title>.+?)\s+[–—-]\s+(?P<rest>.+)$', stem)
    if not match:
        return stem, ''
    rest = match.group('rest')
    if not re.search(r'(original\s*sound ?track|sound ?track|ost|サウンドトラック)', rest, re.I):
        return stem, ''
    album = re.sub(r'[_ ]*(original\s*)?sound ?track.*$', '', rest, flags=re.I)
    album = re.sub(r'[_ ]*ost.*$', '', album, flags=re.I).strip(' _-')
    return match.group('title').strip(), album


def filename_track_number(stem):
    match = re.match(r'^\s*(\d{1,3})[\s._\-]', stem)
    return int(match.group(1)) if match else None


def sanitize_component(text, fallback='_'):
    text = unicodedata.normalize('NFC', (text or '').strip())
    text = re.sub(r'[\x00-\x1f\x7f]', '', text)
    text = text.replace('/', '／').replace('\\', '＼')
    text = text.strip().strip('. ')
    if len(text) > 120:
        text = text[:120].rstrip()
    return text or fallback


def natural_key(text):
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r'(\d+)', text or '')]


def read_track(path):
    """Return ({tags}, seconds). Mutagen is imported lazily for testability."""
    import mutagen
    tags = {}
    length = 0
    audio = mutagen.File(str(path))
    if audio is not None:
        length = int(getattr(audio.info, 'length', 0) or 0)
    easy = mutagen.File(str(path), easy=True)
    if easy is not None and easy.tags is not None:
        for key in TAG_FIELDS + ('composer',):
            values = easy.tags.get(key)
            if values:
                tags[key] = str(values[0])
    return tags, length


@dataclasses.dataclass
class Track:
    source: str
    folder: str
    size: int
    tags: dict = dataclasses.field(default_factory=dict)
    length: int = 0
    title: str = ''
    artist: str = ''
    albumartist: str = ''
    album: str = ''
    composer: str = ''
    date: str = ''
    genre: str = ''
    tracknumber: str = ''
    discnumber: str = ''
    album_hint: str = ''
    search_title: str = ''
    reason: str = ''
    mb_recording: str = ''
    release: str = ''
    disc: int = 1
    position: int = 0
    target: str = ''
    action: str = 'keep'

    @property
    def stem(self):
        return Path(self.source).stem


@dataclasses.dataclass
class Cover:
    staged: str = ''
    source: str = ''
    status: str = 'missing'


@dataclasses.dataclass
class Album:
    album: str
    albumartist: str
    date: str = ''
    genre: str = ''
    mb_release: str = ''
    mb_release_group: str = ''
    source: str = 'fallback'
    tracks: list = dataclasses.field(default_factory=list)
    cover: Cover = dataclasses.field(default_factory=Cover)

    @property
    def id(self):
        return f'{self.albumartist}/{self.album}'


def release_queries(album, artist):
    """MusicBrainz release search queries, from strict to loose."""
    queries = [f'release:"{album}"' + (f' AND artist:"{artist}"' if artist else '')]
    if len(album) > 12:
        head = re.split(r'[\s\-–—:：~〜]', album)[0]
        if len(head) >= 4 and head != album:
            queries.append(f'release:"{head}"' +
                           (f' AND artist:"{artist}"' if artist else ''))
    if artist and len(album) <= 12:
        queries.append(f'release:{album} AND artist:"{artist}"')
    return queries


def recording_query(title, artist):
    return f'recording:"{title}"' + (f' AND artist:"{artist}"' if artist else '')


class MusicBrainz:
    def __init__(self, cache_dir, interval=1.1, timeout=30):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.interval = interval
        self.timeout = timeout
        self.last = 0.0
        self.requests = 0

    def _cache_path(self, url):
        return self.cache_dir / (hashlib.md5(url.encode()).hexdigest() + '.json')

    def get(self, url):
        cached = self._cache_path(url)
        if cached.exists():
            return json.loads(cached.read_text())
        wait = self.interval - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        payload = None
        for attempt in range(6):
            self.last = time.time()
            self.requests += 1
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read())
                break
            except urllib.error.HTTPError as error:
                if error.code in (429, 503) and attempt < 5:
                    # 長い待機は全体を遅くするだけだった。レート制限の窓は
                    # 1秒なので、短く待ってやり直す（2026-09-13 実測）。
                    time.sleep(min(8, 1.1 + attempt))
                    continue
                raise RuntimeError(f'lookup failed: HTTP {error.code}') from error
            except (urllib.error.URLError, OSError) as error:
                if attempt < 5:
                    time.sleep(min(30, 2 ** attempt))
                    continue
                raise RuntimeError(f'lookup failed: {error}') from error
        if payload is None:
            raise RuntimeError(f'lookup failed: {url}')
        temporary = cached.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload, ensure_ascii=False))
        os.replace(temporary, cached)
        return payload

    def release_search(self, album, artist, limit=8):
        seen = set()
        results = []
        for query in release_queries(album, artist):
            url = (f'{MB_API}/release?query={urllib.parse.quote(query)}'
                   f'&fmt=json&limit={limit}')
            data = self.get(url)
            for release in data.get('releases', []):
                if release.get('id') not in seen:
                    seen.add(release.get('id'))
                    results.append(release)
        return results

    def release(self, mbid):
        url = (f'{MB_API}/release/{mbid}'
               '?inc=recordings+artist-credits+release-groups&fmt=json')
        return self.get(url)

    def recording_search(self, title, artist, limit=6):
        query = recording_query(title, artist)
        url = f'{MB_API}/recording?query={urllib.parse.quote(query)}&fmt=json&limit={limit}'
        return self.get(url).get('recordings', [])


def credit_names(credits):
    names = []
    for part in credits or []:
        if not isinstance(part, dict):
            continue
        name = part.get('name') or (part.get('artist') or {}).get('name') or ''
        if name:
            names.append(name)
    return names


def credit_string(credits):
    text = ''
    for part in credits or []:
        if not isinstance(part, dict):
            continue
        text += (part.get('name') or (part.get('artist') or {}).get('name') or '')
        text += part.get('joinphrase') or ' '
    return text.strip()


def release_tracks(release):
    tracks = []
    for medium in release.get('media', []):
        disc = int(medium.get('position') or 1)
        for track in medium.get('tracks', []):
            position = track.get('position') or 0
            if not isinstance(position, int):
                digits = re.match(r'(\d+)', str(position))
                position = int(digits.group(1)) if digits else 0
            recording = track.get('recording')
            recording_id = (recording.get('id') if isinstance(recording, dict)
                            else recording) or ''
            tracks.append({
                'title': track.get('title') or '',
                'disc': disc,
                'position': position,
                'length': (track.get('length') or 0) // 1000,
                'recording': recording_id,
            })
    return tracks


def score_release(release, album, artist, track_count):
    title = release.get('title') or ''
    names = credit_names(release.get('artist-credit'))
    score = similarity(album, title)
    if artist:
        best = max((similarity(artist, name) for name in names), default=0.0)
        score = score * 0.75 + best * 0.25
    count = release.get('track-count') or 0
    if count and track_count:
        ratio = min(count, track_count) / max(count, track_count)
        score = score * 0.95 + ratio * 0.05
    return score


def match_tracks(tracks, mb_tracks):
    """Greedy match by normalized title, then duration. Returns {source: mbtrack}."""
    remaining = list(mb_tracks)
    matches = {}
    for track in sorted(tracks, key=lambda t: -t.length):
        best, best_score = None, 0.0
        for candidate in remaining:
            title = track.title
            key_source = normalize(strip_title_prefix(title))
            key_target = normalize(candidate['title'])
            score = difflib.SequenceMatcher(None, key_source, key_target).ratio()
            if candidate['length'] and track.length:
                delta = abs(candidate['length'] - track.length)
                if delta <= 3:
                    score += 0.06
                elif delta <= 8:
                    score += 0.02
                elif delta > 25:
                    score -= 0.05
            if score > best_score:
                best, best_score = candidate, score
        if best is not None and best_score >= TRACK_MIN_SCORE:
            matches[track.source] = best
            remaining.remove(best)
    return matches


def choose_recording_release(recording, preferred_album='', preferred_artist=''):
    releases = recording.get('releases') or []
    scored = []
    for release in releases:
        title = release.get('title') or ''
        group = release.get('release-group') or {}
        secondary = [str(x).lower() for x in (group.get('secondary-types') or [])]
        score = 0.0
        if preferred_album:
            score += similarity(preferred_album, title) * 2.0
        if 'compilation' in secondary:
            score -= 1.0
        if group.get('primary-type') == 'Album':
            score += 0.1
        date = release.get('date') or ''
        if re.match(r'^\d{4}', date):
            score += max(0.0, 0.2 - int(date[:4]) / 10000.0)
        scored.append((score, release))
    if not scored:
        return None
    scored.sort(key=lambda pair: -pair[0])
    return scored[0][1]


def score_recording(recording, title, artist):
    names = credit_names(recording.get('artist-credit'))
    title_score = difflib.SequenceMatcher(
        None, normalize(strip_title_prefix(title)),
        normalize(recording.get('title') or '')).ratio()
    if artist:
        artist_score = max((similarity(artist, name) for name in names), default=0.0)
        if artist_score < 0.4:
            return 0.0
        return title_score * 0.75 + artist_score * 0.25
    return title_score


def majority(values):
    counts = collections.Counter(value for value in values if value)
    return counts.most_common(1)[0][0] if counts else ''


def group_tracks(tracks):
    groups = collections.defaultdict(list)
    for track in tracks:
        album = track.album if valid_tag(track.album) else ''
        if not album and valid_tag(track.album_hint):
            album = track.album_hint
        key = ('album', album) if album else ('folder', track.folder)
        groups[key].append(track)
    return groups


def load_aliases(path):
    if not path or not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text())


def load_corrections(path):
    """Per-file tag fixes recorded after a manual review (files map)."""
    if not path or not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text()).get('files', {})


def apply_corrections(tracks, corrections):
    for track in tracks:
        fix = corrections.get(track.source)
        if not fix:
            continue
        for field in ('title', 'artist', 'albumartist', 'album', 'genre', 'date',
                      'composer'):
            value = fix.get(field)
            if value:
                setattr(track, field, value)
        track.search_title = clean_for_search(track.title)


def alias_for(aliases, album, folder):
    if album and album in aliases.get('albums', {}):
        return aliases['albums'][album]
    for key in (folder, album):
        if key and key in aliases.get('folders', {}):
            return aliases['folders'][key]
    return {}


def apply_alias(tracks, alias):
    if not alias:
        return
    for track in tracks:
        if alias.get('album'):
            track.album = alias['album']
        if alias.get('albumartist'):
            track.albumartist = alias['albumartist']
        if alias.get('genre'):
            track.genre = alias['genre']
        if alias.get('title_prefix') and track.title.startswith(alias['title_prefix']):
            track.title = track.title[len(alias['title_prefix']):].strip('「」 ')


def resolve_release_group(mb, tracks, alias):
    album = alias.get('album') or next(
        (t.album for t in tracks if valid_tag(t.album)), '')
    albumartist = alias.get('albumartist') or next(
        (t.albumartist for t in tracks if valid_tag(t.albumartist)), '')
    artist = albumartist or next((t.artist for t in tracks if valid_tag(t.artist)), '')
    if alias.get('mb_release'):
        try:
            release = mb.release(alias['mb_release'])
        except RuntimeError:
            return None
        score = 1.0
    elif valid_tag(album):
        scored = []
        artists = [artist, ''] if artist else ['']
        for search_artist in artists:
            try:
                candidates = mb.release_search(album, search_artist)
            except RuntimeError:
                return None
            scored = sorted(((score_release(r, album, artist, len(tracks)), r)
                             for r in candidates), key=lambda pair: -pair[0])
            if scored and scored[0][0] >= RELEASE_MIN_SCORE:
                break
        if not scored or scored[0][0] < RELEASE_MIN_SCORE:
            return None
        score, summary = scored[0]
        try:
            release = mb.release(summary['id'])
        except RuntimeError:
            return None
    else:
        return None
    mb_tracks = release_tracks(release)
    if not mb_tracks:
        return None
    matches = match_tracks(tracks, mb_tracks)
    if not matches and not alias.get('mb_release'):
        return None
    names = credit_names(release.get('artist-credit'))
    release_artist = alias.get('albumartist') or (
        names[0] if len(names) == 1 else ' & '.join(names))
    release_album = alias.get('album') or release.get('title') or album
    if has_cjk(album) and not has_cjk(release_album) and alias.get('album') is None:
        release_album = album
    if has_cjk(albumartist) and not has_cjk(release_artist) and alias.get('albumartist') is None:
        release_artist = albumartist
    year = (release.get('date') or '')[:4]
    group = release.get('release-group') or {}
    for track in tracks:
        match = matches.get(track.source)
        if not match:
            continue
        track.reason = 'mb-release'
        track.release = release.get('id') or ''
        track.mb_recording = match['recording']
        track.disc = match['disc']
        track.position = match['position']
        track.title = match['title'] or track.title
        track.album = release_album
        track.albumartist = release_artist
        if year:
            track.date = year
        if names and not track.artist:
            track.artist = ' & '.join(names)
    return {
        'album': release_album,
        'albumartist': release_artist,
        'date': year,
        'mb_release': release.get('id') or '',
        'mb_release_group': group.get('id') or '',
        'matched': sum(1 for t in tracks if t.reason == 'mb-release'),
    }


def recording_artists(track, alias):
    """Artist names to try for a recording lookup, best first."""
    values = []
    for value in (alias.get('albumartist'), track.albumartist, track.artist):
        if valid_tag(value) and value not in values:
            values.append(value)
    values.append('')
    return values


def resolve_by_recording(mb, track, alias):
    titles = [t for t in (track.title, track.search_title,
                          strip_title_prefix(track.stem)) if t]
    for title in titles:
        variants = []
        for candidate in (title, clean_for_search(title)):
            if len(candidate) >= 2 and candidate not in variants:
                variants.append(candidate)
        for candidate_title in variants:
            for artist in recording_artists(track, alias):
                try:
                    recordings = mb.recording_search(candidate_title, artist)
                except RuntimeError:
                    return False
                scored = sorted(
                    ((score_recording(r, candidate_title, artist), r)
                     for r in recordings), key=lambda pair: -pair[0])
                threshold = RECORDING_MIN_SCORE if artist else RECORDING_TITLE_SCORE
                if not scored or scored[0][0] < threshold:
                    continue
                score, recording = scored[0]
                if not artist and any(COVER_JUNK_ARTISTS.search(name) for name in
                                      credit_names(recording.get('artist-credit'))):
                    continue
                release = choose_recording_release(recording, track.album, artist)
                if release is None:
                    continue
                names = credit_names(release.get('artist-credit')) or credit_names(
                    recording.get('artist-credit'))
                release_album = release.get('title') or track.album
                release_artist = names[0] if names else (track.albumartist or track.artist)
                try:
                    full = mb.release(release['id'])
                except RuntimeError:
                    return False
                position = 0
                disc = 1
                for mb_track in release_tracks(full):
                    if mb_track['recording'] == recording.get('id'):
                        position, disc = mb_track['position'], mb_track['disc']
                        break
                track.reason = 'mb-recording'
                track.release = release['id']
                track.mb_recording = recording.get('id') or ''
                track.album = release_album
                track.albumartist = release_artist
                track.title = recording.get('title') or track.title
                track.date = (release.get('date') or track.date or '')[:4]
                track.position = position
                track.disc = disc
                return True
    return False


def fallback_group(track):
    album = track.album if valid_tag(track.album) else track.album_hint
    albumartist = track.albumartist if valid_tag(track.albumartist) else track.artist
    if not album and not albumartist:
        return None
    if not album:
        album = 'Singles'
    if not albumartist:
        albumartist = 'Various Artists'
    return album, albumartist


def plan_tracks(mb, tracks, aliases, stats):
    groups = group_tracks(tracks)
    unresolved = []
    albums = collections.OrderedDict()
    for key, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        album_key = key[1] if key[0] == 'album' else ''
        folder_key = key[1] if key[0] == 'folder' else members[0].folder
        albumartist = majority([t.albumartist for t in members])
        artist = majority([t.artist for t in members])
        for track in members:
            if not valid_tag(track.albumartist):
                track.albumartist = albumartist
            if not valid_tag(track.artist):
                track.artist = artist
        alias = alias_for(aliases, album_key, folder_key)
        apply_alias(members, alias)
        skip_lookup = bool(alias.get('skip_lookup')) or getattr(mb, 'disabled', False)
        if skip_lookup:
            # 検索しても見つからない塊（YouTubeの英語列挙など）は、エイリアスで
            # 決めたアルバム/アーティストへそのまま入れる。
            result = {}
            resolved, leftover = [], list(members)
        else:
            result = resolve_release_group(mb, members, alias)
            if result:
                bump(stats, 'mb_release')
            else:
                result = {}
            resolved = [t for t in members if t.reason == 'mb-release']
            leftover = [t for t in members if t.reason != 'mb-release']
        album_locked = bool(alias.get('mb_release') and result.get('mb_release'))
        for track in leftover:
            if not skip_lookup and not album_locked and resolve_by_recording(
                    mb, track, alias):
                bump(stats, 'mb_recording')
                resolved.append(track)
                continue
            fallback = fallback_group(track)
            if fallback:
                track.album, track.albumartist = fallback
                track.reason = 'fallback'
                bump(stats, 'fallback')
                resolved.append(track)
            else:
                track.reason = 'unresolved'
                bump(stats, 'unresolved')
                unresolved.append(track)
        for track in resolved:
            key2 = (track.album, track.albumartist)
            if key2 not in albums:
                albums[key2] = Album(album=track.album, albumartist=track.albumartist,
                                     date=result.get('date') or track.date,
                                     mb_release=(result.get('mb_release')
                                                 or track.release),
                                     mb_release_group=result.get('mb_release_group', ''),
                                     source='fallback')
            albums[key2].tracks.append(track)
    for album in albums.values():
        if any(track.reason.startswith('mb-') for track in album.tracks):
            album.source = 'mb'
    return list(albums.values()), unresolved


def sequence_tracks(album):
    ordered = sorted(album.tracks, key=lambda t: (
        t.disc or 1,
        t.position or 0 or filename_track_number(t.stem) or 999,
        natural_key(Path(t.source).name)))
    # 手動補正で別リリースから合流した曲はトラック番号が重なる。最初の
    # 1曲だけ元の番号を残し、重複・欠番はファイル名順に後ろへ回す。
    taken = collections.defaultdict(set)
    for track in ordered:
        disc = track.disc or 1
        if track.position:
            if track.position in taken[disc]:
                track.position = 0
            else:
                taken[disc].add(track.position)
    for disc in sorted({track.disc or 1 for track in ordered}):
        next_position = max(taken[disc] or {0}) + 1
        for track in ordered:
            if (track.disc or 1) != disc or track.position:
                continue
            while next_position in taken[disc]:
                next_position += 1
            track.position = next_position
            taken[disc].add(next_position)
            next_position += 1
    return ordered


def assign_targets(root, albums):
    used = set()
    for album in albums:
        tracks = sequence_tracks(album)
        max_disc = max((t.disc or 1 for t in tracks), default=1)
        width = 3 if max((t.position or 0 for t in tracks), default=0) > 99 else 2
        for track in tracks:
            if track.reason == 'unresolved':
                track.target = track.source
                track.action = 'keep'
                continue
            number = f'{track.position or 0:0{width}d}'
            title = sanitize_component(track.title or filename_to_title(track.stem))
            parts = [sanitize_component(album.albumartist, 'Unknown Artist'),
                     sanitize_component(album.album, 'Unknown Album')]
            if max_disc > 1:
                parts.append(f'Disc {track.disc or 1}')
            parts.append(f'{number} - {title}{AUDIO_SUFFIX}')
            target = '/'.join(parts)
            candidate = target
            counter = 2
            while candidate.lower() in used or (
                    candidate != track.source and (Path(root) / candidate).exists()):
                stem = Path(target).stem
                candidate = str(Path(target).with_name(f'{stem} ({counter}){AUDIO_SUFFIX}'))
                counter += 1
            used.add(candidate.lower())
            track.target = candidate
            track.action = 'move' if candidate != track.source else 'keep'


def unique_target(target):
    if not target.exists():
        return target
    counter = 2
    while True:
        candidate = target.with_name(f'{target.stem} ({counter}){target.suffix}')
        if not candidate.exists():
            return candidate
        counter += 1


def fetch_url(url, timeout=30):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.headers.get('Content-Type', ''), response.read()


def image_bytes(payload):
    return payload[:2] == b'\xff\xd8' or payload[:8] == b'\x89PNG\r\n\x1a\n'


def cover_from_caa(album):
    mbid = album.mb_release
    if not mbid:
        return None
    for url in (f'{CAA_API}/release/{mbid}/front-500',
                f'{CAA_API}/release-group/{album.mb_release_group}/front-500'
                if album.mb_release_group else ''):
        if not url:
            continue
        try:
            content_type, payload = fetch_url(url)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            continue
        if 'image' in content_type and image_bytes(payload) and len(payload) >= COVER_MIN_BYTES:
            return payload, f'caa:{mbid}'
    return None


def cover_from_itunes(album, term):
    query = urllib.parse.urlencode({'term': term or album.album,
                                    'media': 'music', 'entity': 'album',
                                    'limit': 6, 'country': 'jp'})
    try:
        with urllib.request.urlopen(
                urllib.request.Request(f'{ITUNES_API}?{query}',
                                       headers={'User-Agent': USER_AGENT}),
                timeout=30) as response:
            results = json.loads(response.read()).get('results', [])
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
        return None
    best = None
    for result in results:
        name = result.get('collectionName') or ''
        artist = result.get('artistName') or ''
        if COVER_JUNK_ARTISTS.search(name + ' ' + artist):
            continue
        score = similarity(album.album, name)
        if album.albumartist:
            score = score * 0.85 + min(1.0, similarity(album.albumartist, artist)) * 0.15
        url = (result.get('artworkUrl100') or '').replace('100x100', '600x600')
        if not url:
            continue
        if best is None or score > best[0]:
            best = (score, url)
    if best is None or best[0] < COVER_MIN_SCORE:
        return None
    try:
        content_type, payload = fetch_url(best[1])
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None
    if image_bytes(payload) and len(payload) >= COVER_MIN_BYTES:
        return payload, 'itunes'
    return None


def cover_from_deezer(album, term):
    url = f'{DEEZER_API}?q={urllib.parse.quote(term or album.album)}&limit=6'
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers={'User-Agent': USER_AGENT}),
                timeout=30) as response:
            results = json.loads(response.read()).get('data', [])
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
        return None
    best = None
    for result in results:
        name = result.get('title') or ''
        artist = (result.get('artist') or {}).get('name') or ''
        if COVER_JUNK_ARTISTS.search(name + ' ' + artist):
            continue
        score = similarity(album.album, name)
        if album.albumartist:
            score = score * 0.85 + min(1.0, similarity(album.albumartist, artist)) * 0.15
        cover = result.get('cover_xl') or result.get('cover_big') or ''
        if cover and (best is None or score > best[0]):
            best = (score, cover)
    if best is None or best[0] < COVER_MIN_SCORE:
        return None
    try:
        content_type, payload = fetch_url(best[1])
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None
    if image_bytes(payload) and len(payload) >= COVER_MIN_BYTES:
        return payload, 'deezer'
    return None


def legacy_cover(root, folders):
    """Largest WMP-style image in the given folders, if any."""
    best = None
    for folder in folders:
        folder = Path(folder)
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.is_file() or not JUNK_IMAGE_NAMES.match(path.stem):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size >= COVER_MIN_BYTES and (best is None or size > best[0]):
                best = (size, path)
    if best is None:
        return None
    try:
        payload = best[1].read_bytes()
    except OSError:
        return None
    if image_bytes(payload):
        return payload, f'legacy:{best[1].name}'
    return None


def cover_from_legacy(album, root):
    folders = [Path(root) / track.folder for track in album.tracks]
    return legacy_cover(root, folders)


def plan_covers(mb, albums, aliases, root, staging, stats, offline=False):
    staging = Path(staging)
    staging.mkdir(parents=True, exist_ok=True)
    for album in albums:
        if album.albumartist == '_未解決':
            continue
        digest = hashlib.md5(album.id.encode()).hexdigest()
        staged = staging / f'{digest}.jpg'
        existing = existing_cover(Path(root) / sanitize_component(album.albumartist, 'Unknown Artist')
                                  / sanitize_component(album.album, 'Unknown Album'))
        if existing:
            album.cover = Cover(staged=str(existing), source=f'existing:{existing.name}',
                                status='existing')
            bump(stats, 'cover_existing')
            continue
        if offline:
            continue
        alias = alias_for(aliases, album.album, '')
        term = alias.get('itunes_term') or f'{album.album} {album.albumartist}'.strip()
        result = cover_from_caa(album) or cover_from_itunes(album, term) \
            or cover_from_deezer(album, term) or cover_from_legacy(album, root)
        if result:
            payload, source = result
            staged.write_bytes(payload)
            album.cover = Cover(staged=staged.name, source=source, status='found')
            bump(stats, 'cover_found')
            bump(stats, f'cover_{source.split(":")[0]}')
        else:
            album.cover = Cover(source='none', status='missing')
            bump(stats, 'cover_missing')


def existing_cover(folder):
    if not folder.is_dir():
        return None
    for path in sorted(folder.iterdir()):
        if path.is_file() and JUNK_IMAGE_NAMES.match(path.stem) and path.suffix.lower() in (
                '.jpg', '.jpeg', '.png'):
            return path
    return None


def write_report(path, manifest, stats, mb=None):
    lines = ['# 音楽整理レポート', '',
             f"- 対象MP3: {stats['files']}",
             f"- MusicBrainzリリース一致: {stats['mb_release']}",
             f"- MusicBrainz録音一致: {stats['mb_recording']}",
             f"- 既存タグ/ファイル名で整理: {stats['fallback']}",
             f"- 未解決（そのまま）: {stats['unresolved']}",
             f"- カバー: 新規 {stats['cover_found']} / 既存流用 {stats['cover_existing']} / 未取得 {stats['cover_missing']}",
             '']
    if mb is not None:
        lines.append(f"MusicBrainz問い合わせ回数: {mb.requests}")
        lines.append('')
    lines.append('## アルバム')
    lines.append('')
    lines.append('| 曲数 | アルバム | アルバムアーティスト | 由来 | カバー |')
    lines.append('| --- | --- | --- | --- | --- |')
    for album in manifest['albums']:
        lines.append(f"| {len(album['tracks'])} | {album['album']} | "
                     f"{album['albumartist']} | {album['source']} | "
                     f"{album['cover']['status']} {album['cover']['source']} |")
    lines.append('')
    unresolved = [t for album in manifest['albums'] for t in album['tracks']
                  if t['reason'] == 'unresolved']
    if unresolved:
        lines.append('## 未解決（移動していません）')
        lines.append('')
        for track in unresolved:
            lines.append(f"- `{track['source']}`")
        lines.append('')
    Path(path).write_text('\n'.join(lines) + '\n')


def build_manifest(albums, root):
    return {
        'version': 1,
        'created': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'root': str(root),
        'albums': [{
            'album': album.album,
            'albumartist': album.albumartist,
            'date': album.date,
            'mb_release': album.mb_release,
            'mb_release_group': album.mb_release_group,
            'source': album.source,
            'cover': dataclasses.asdict(album.cover),
            'tracks': [{
                'source': t.source,
                'target': t.target,
                'action': t.action,
                'title': t.title,
                'artist': t.artist,
                'album': t.album,
                'albumartist': t.albumartist,
                'date': t.date,
                'genre': t.genre,
                'composer': t.composer,
                'tracknumber': str(t.position or ''),
                'discnumber': str(t.disc or 1),
                'reason': t.reason,
                'mb_recording': t.mb_recording,
                'release': t.release,
            } for t in sequence_tracks(album)],
        } for album in albums],
    }


def command_plan(args):
    root = Path(args.root)
    state = Path(args.state)
    tracks = []
    for dirpath, dirnames, filenames in os.walk(root):
        relative = Path(dirpath).relative_to(root)
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith('.')]
        for name in sorted(filenames):
            if not name.lower().endswith(AUDIO_SUFFIX):
                continue
            source = str(relative / name) if str(relative) != '.' else name
            if args.only and not source.startswith(args.only):
                continue
            path = Path(dirpath) / name
            tags, length = read_track(path)
            track = Track(source=source, folder=str(relative) if str(relative) != '.' else '',
                          size=path.stat().st_size, tags=tags, length=length)
            track.title = tags.get('title') or filename_to_title(path.stem)
            track.artist = tags.get('artist', '')
            track.albumartist = tags.get('albumartist', '')
            track.album = tags.get('album', '')
            track.composer = tags.get('composer', '')
            track.date = tags.get('date', '')
            track.genre = tags.get('genre', '')
            track.tracknumber = tags.get('tracknumber', '')
            track.discnumber = tags.get('discnumber', '')
            parsed_title, album_hint = filename_album_hint(path.stem)
            if album_hint and not valid_tag(track.album):
                track.album_hint = album_hint
                track.title = parsed_title
            track.search_title = clean_for_search(track.title)
            tracks.append(track)
    apply_corrections(tracks, load_corrections(getattr(args, 'corrections', None)))
    stats = collections.Counter({'files': len(tracks)})
    mb = MusicBrainz(state / 'cache', interval=args.interval)
    mb.disabled = args.no_lookup
    albums, unresolved = plan_tracks(mb, tracks, load_aliases(args.aliases), stats)
    if unresolved:
        albums.append(Album(album='_未解決', albumartist='_未解決', tracks=unresolved))
    plan_covers(mb, albums, load_aliases(args.aliases), root, state / 'covers',
                stats, offline=args.no_covers)
    assign_targets(root, albums)
    manifest = build_manifest(albums, root)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    write_report(out / 'report.md', manifest, stats, mb)
    print(f"files={stats['files']} mb_release={stats['mb_release']} "
          f"mb_recording={stats['mb_recording']} fallback={stats['fallback']} "
          f"unresolved={stats['unresolved']} "
          f"covers={stats['cover_found']}/{stats['cover_existing']}/{stats['cover_missing']}")
    print(f'manifest: {out / "manifest.json"}')
    print(f'report:   {out / "report.md"}')


def write_tags(path, values, backup_dir, relative):
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3, ID3NoHeaderError
    try:
        tags = EasyID3(str(path))
    except ID3NoHeaderError:
        tags = EasyID3()
    changes = {}
    for key, value in values.items():
        if value is None or value == '':
            continue
        existing = tags.get(key)
        if existing != [str(value)]:
            changes[key] = str(value)
    if not changes:
        return False
    backup = Path(backup_dir) / (relative + '.id3')
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        try:
            ID3(str(path)).save(str(backup))
        except ID3NoHeaderError:
            backup.with_suffix('.no-id3').touch()
    for key, value in changes.items():
        tags[key] = value
    tags.save(str(path))
    os.utime(path, None)
    return True


def command_apply(args):
    manifest = json.loads(Path(args.manifest).read_text())
    root = Path(manifest['root'])
    state = Path(args.state)
    backups = state / 'tag-backups'
    journal = {'created': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'entries': []}
    covers_done = set()
    moved_dirs = set()
    counts = collections.Counter()
    for album in manifest['albums']:
        cover = album.get('cover') or {}
        album_dir = root / sanitize_component(album['albumartist'], 'Unknown Artist') \
            / sanitize_component(album['album'], 'Unknown Album')
        for track in album['tracks']:
            source = root / track['source']
            target = root / track['target']
            if track['action'] == 'move' and not source.exists():
                counts['skipped'] += 1
                continue
            values = {'title': track['title'], 'artist': track['artist'],
                      'album': track['album'], 'albumartist': track['albumartist'],
                      'date': track['date'], 'genre': track['genre'],
                      'composer': track.get('composer', ''),
                      'tracknumber': track['tracknumber'],
                      'discnumber': track['discnumber']}
            try:
                changed = write_tags(source, values, backups, track['source'])
                if changed:
                    journal['entries'].append(
                        {'type': 'tags', 'source': track['source']})
                    counts['tagged'] += 1
            except Exception as error:  # noqa: BLE001 - keep going per file
                print(f'WARN tag failed: {track["source"]}: {error}')
                counts['tag_failed'] += 1
                continue
            if track['action'] == 'move':
                target.parent.mkdir(parents=True, exist_ok=True)
                target = unique_target(target)
                os.replace(source, target)
                journal['entries'].append(
                    {'type': 'move', 'source': track['source'],
                     'target': str(target.relative_to(root))})
                counts['moved'] += 1
                moved_dirs.add(str(Path(track['source']).parent))
            else:
                counts['kept'] += 1
        if album_dir.is_dir() and not existing_cover(album_dir):
            staged = Path(cover.get('staged') or '')
            if staged and cover.get('status') == 'found' and not staged.is_absolute():
                staged = state / 'covers' / staged
            payload = staged.read_bytes() if staged.is_file() else None
            if payload is None:
                # ネットワークで取れなくても、元フォルダのFolder.jpgを流用する。
                result = legacy_cover(root, [
                    str((root / track['source']).parent) for track in album['tracks']])
                if result:
                    payload, cover['source'] = result
                    cover['status'] = 'found'
            if payload:
                destination = album_dir / 'cover.jpg'
                destination.write_bytes(payload)
                journal['entries'].append({'type': 'cover', 'path': str(destination)})
                counts['cover'] += 1
    if args.cleanup:
        for relative in sorted(moved_dirs, key=len, reverse=True):
            folder = root / relative
            if not folder.is_dir():
                continue
            leftovers = list(folder.iterdir())
            only_junk = leftovers and all(
                path.is_file() and JUNK_DELETE.match(path.name) for path in leftovers)
            if only_junk:
                for path in leftovers:
                    path.unlink()
                    journal['entries'].append({'type': 'remove', 'path': str(path)})
                    counts['removed'] += 1
            try:
                folder.rmdir()
                journal['entries'].append({'type': 'rmdir', 'path': str(folder)})
                counts['rmdir'] += 1
            except OSError:
                pass
    journal_path = state / f'journal-{time.strftime("%Y%m%d-%H%M%S")}.json'
    journal_path.write_text(json.dumps(journal, ensure_ascii=False, indent=1))
    print(dict(counts))
    print(f'journal: {journal_path}')


def command_undo(args):
    journal = json.loads(Path(args.journal).read_text())
    root = Path(args.root)
    state = Path(args.state)
    counts = collections.Counter()
    for entry in reversed(journal['entries']):
        kind = entry['type']
        if kind == 'cover':
            path = Path(entry['path'])
            if path.exists():
                path.unlink()
                counts['cover_removed'] += 1
        elif kind == 'rmdir':
            path = Path(entry['path'])
            path.mkdir(parents=True, exist_ok=True)
            counts['rmdir'] += 1
        elif kind == 'remove':
            counts['remove_skipped'] += 1
        elif kind == 'move':
            source = root / entry['source']
            target = root / entry['target']
            if target.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, source)
                counts['moved_back'] += 1
        elif kind == 'tags':
            source = root / entry['source']
            backup = state / 'tag-backups' / (entry['source'] + '.id3')
            empty = state / 'tag-backups' / (entry['source'] + '.no-id3')
            if backup.exists() and source.exists():
                from mutagen.id3 import ID3
                ID3(str(backup)).save(str(source))
                counts['tags_restored'] += 1
            elif empty.exists() and source.exists():
                from mutagen.id3 import ID3, ID3NoHeaderError
                try:
                    ID3(str(source)).delete()
                except ID3NoHeaderError:
                    pass
                counts['tags_deleted'] += 1
    print(dict(counts))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=os.environ.get('ORGANIZE_MUSIC', DEFAULT_ROOT))
    parser.add_argument('--state',
                        default=os.environ.get('ORGANIZE_STATE',
                                               os.path.join(DEFAULT_STATE, 'organize')))
    sub = parser.add_subparsers(dest='command', required=True)
    plan = sub.add_parser('plan')
    plan.add_argument('--out', default=None)
    plan.add_argument('--aliases', default=None)
    plan.add_argument('--only', default=None)
    plan.add_argument('--interval', type=float, default=1.1)
    plan.add_argument('--no-covers', action='store_true')
    plan.add_argument('--no-lookup', action='store_true')
    plan.add_argument('--corrections', default=None)
    plan.set_defaults(func=command_plan)
    apply = sub.add_parser('apply')
    apply.add_argument('--manifest', required=True)
    apply.add_argument('--cleanup', action='store_true')
    apply.set_defaults(func=command_apply)
    undo = sub.add_parser('undo')
    undo.add_argument('--journal', required=True)
    undo.set_defaults(func=command_undo)
    args = parser.parse_args(argv)
    if getattr(args, 'out', None) is None:
        args.out = args.state
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
