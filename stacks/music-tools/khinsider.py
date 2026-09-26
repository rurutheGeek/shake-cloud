#!/usr/bin/env python3
"""Download every track of a KHInsider album page into the shared music library.

MeTube takes one media URL at a time. KHInsider wraps an album behind an album
page and a per-song page, so this small browser tool turns
``https://downloads.khinsider.com/game-soundtracks/album/<slug>`` into a folder
under ``music/Khinsider/<album>/``. Navidrome and organize.py pick that up like
any other import. It runs next to MeTube and sits behind the same Forward Auth.

KHInsider sits behind Cloudflare and answers a plain HTTP client with a bot
challenge (403 ``cf-mitigated: challenge``). The service uses the curl_cffi
that ships with the MeTube image (via yt-dlp) for a Chrome TLS/HTTP2
fingerprint, keeps one session so the clearance cookie is reused across song
pages and downloads, and retries 403/429/503 with backoff before failing.

KHInsider lists track names in English even for Japanese games. When the
"Japanese titles" option is used the service looks the album up on MusicBrainz
(falling back to iTunes JP) and writes the official Japanese names into the
file names and the ID3 title/album tags, so Nextcloud's tag editor and
Navidrome show them. Albums without a matching release can be covered by the
manual dictionary (khinsider-ja.json).

File names are only the song title; the track/disc number is written to the
ID3 tags (tracknumber/discnumber) so players still order the album. A title
used twice gets a deterministic " (2)" counter.

Configuration (compose environment):
  KHINSIDER_PORT   default 5820
  KHINSIDER_MUSIC  default /music
  KHINSIDER_JA     manual dictionary path, default /tools/khinsider-ja.json
  KHINSIDER_DELAY  seconds between tracks, default 0.4
"""
import html
import json
import os
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import queue
import re
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

# metube イメージ（yt-dlp 経由）は curl_cffi を同梱する。KHInsider は
# Cloudflare のbot challengeを返すため、ブラウザのTLS/HTTP2指紋で接続する。
# 無い環境（テスト・最小構成）でも urllib で動くようにしておく。
try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - テスト環境には入っていない
    curl_requests = None

SITE = 'downloads.khinsider.com'
# KHInsider の HTML には href に生の非ASCII（é など）が混ざる。urllib は
# ASCII 以外のURLを拒否するため、予約文字と %XX を保ったまま percent-encode する。
URL_SAFE = ":/?#[]@!$&'()*+,;=%~"


def ascii_url(url):
    return urllib.parse.quote(url or '', safe=URL_SAFE)
ALBUM_PREFIX = '/game-soundtracks/album/'
# MusicBrainz はアプリ名を名乗るよう求めている。KHInsider本体へは下のブラウザ
# 偽装で接続する（Cloudflareのbot challenge対策）。
API_USER_AGENT = 'shake-cloud-khinsider/1.0 (+https://github.com/rurutheGeek/shake-cloud)'
# curl_cffi が無い環境用の保険。challengeはTLS/HTTP2の指紋も見るため urllib では
# 通りにくいが、ヘッダだけでもブラウザに寄せておく。
FALLBACK_USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
# Cloudflareがbot判定で返すコード。少し待ってやり直す。
CHALLENGE_CODES = (403, 429, 503)
CHALLENGE_WAITS = (5, 15, 30, 60)
# 再試行ではセッションを作り直し、指紋も切り替える。一度challengeされた
# セッションは待っても回復しないことがあるため（2026-09-23実測）。
IMPERSONATIONS = ('chrome', 'chrome131', 'firefox133')
MUSICBRAINZ = 'https://musicbrainz.org/ws/2/'
ITUNES_SEARCH = 'https://itunes.apple.com/search'
ITUNES_LOOKUP = 'https://itunes.apple.com/lookup'
DURATION_RE = re.compile(r'^\d{1,3}:[0-5]\d$')
# MusicBrainz asks for at most one request per second.
MUSICBRAINZ_INTERVAL = 1.0
JOBS = {}
JOBS_LOCK = threading.Lock()
WORK = queue.Queue()
DELAY = float(os.environ.get('KHINSIDER_DELAY', '0.8'))
JA_DICTIONARY = os.environ.get('KHINSIDER_JA', '/tools/khinsider-ja.json')
# ジョブ履歴はコンテナ再作成でも残す。どこまで終わったかを一覧で確認できる。
STATE_DIR = Path(os.environ.get('KHINSIDER_STATE', '/state'))
JOBS_FILE = STATE_DIR / 'jobs.json'
MUSIC_ROOT = Path(os.environ.get('KHINSIDER_MUSIC', '/music'))
JOBS_LIMIT = 100
STATE_LABELS = {'queued': '待機中', 'running': '実行中', 'done': '完了', 'failed': '失敗'}
MUSICBRAINZ_LOCK = threading.Lock()
MUSICBRAINZ_LAST = [0.0]
MUSICBRAINZ_CACHE = {}
# 並列はアルバム単位。同一アルバムは直列にして、上限は3ワーカー。
MAX_WORKERS = 3
# 全ワーカー合計のリクエスト間隔。並列でも叩きすぎないようにする。
REQUEST_INTERVAL = float(os.environ.get('KHINSIDER_REQUEST_INTERVAL', '0.4'))
REQUEST_LOCK = threading.Lock()
REQUEST_LAST = [0.0]
SAVE_LOCK = threading.Lock()
ALBUM_LOCKS = {}
ALBUM_LOCKS_LOCK = threading.Lock()


def validate_album_url(url):
    """Return the canonical album URL, refusing anything else.

    Only KHInsider album pages are fetched, so the page can never be used to
    probe the LAN. The canonical form drops the query and trailing slash.
    """
    parsed = urllib.parse.urlsplit((url or '').strip())
    if parsed.scheme != 'https' or parsed.hostname != SITE:
        raise ValueError('https://downloads.khinsider.com のアルバムURLを指定してください')
    if not parsed.path.startswith(ALBUM_PREFIX):
        raise ValueError('/game-soundtracks/album/... のアルバムURLを指定してください')
    path = parsed.path.rstrip('/')
    if path == ALBUM_PREFIX.rstrip('/'):
        raise ValueError('アルバムのURLを指定してください')
    return urllib.parse.urlunsplit(('https', SITE, path, '', ''))


def safe_component(value, fallback='album'):
    """Turn one site-provided name into a single safe path component."""
    name = urllib.parse.unquote(value or '').strip()
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name)
    name = name.strip(' .')
    return name[:120] or fallback


def track_filename(href, index):
    """Return the file name taken from the site's own link (fallback only)."""
    value = href.rsplit('/', 1)[-1]
    name = safe_component(urllib.parse.unquote(urllib.parse.unquote(value)),
                          f'{index:02d}.mp3')
    if not name.lower().endswith('.mp3'):
        name += '.mp3'
    return name


def title_filename(title, index):
    """Return ``<song title>.mp3``; the track number belongs in the ID3 tags."""
    name = safe_component(title, f'track {index}')
    return name if name.lower().endswith('.mp3') else name + '.mp3'


def track_position(href, index):
    """Return ``(disc, track)`` from the site's ``d-nn.`` prefix, else ``(1, index)``."""
    value = urllib.parse.unquote(urllib.parse.unquote(href.rsplit('/', 1)[-1]))
    match = re.match(r'^(\d+)-(\d+)[.\s]', value)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.match(r'^(\d+)[.\s]', value)
    if match:
        return 1, int(match.group(1))
    return 1, index


class AlbumParser(HTMLParser):
    """Collect the album title, alt titles and the MP3 links in ``#songlist``."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.album = ''
        self.entries = []
        self.alt_titles = ''
        self._songlist = 0
        self._heading = False
        self._alt = None
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'table' and attributes.get('id') == 'songlist':
            self._songlist += 1
        elif tag == 'a' and self._songlist:
            href = attributes.get('href') or ''
            # Each track row repeats the same MP3 link for name, duration and
            # size; the first one per href carries the song name.
            if href.lower().split('?')[0].endswith('.mp3'):
                self._href = href
                self._text = []
        elif tag == 'h2' and not self.album:
            self._heading = True
        elif tag == 'p' and 'albuminfoAlternativeTitles' in (attributes.get('class') or ''):
            self._alt = []
        elif tag == 'br' and self._alt is not None:
            self._alt.append('\n')

    def handle_data(self, data):
        if self._heading:
            self.album += data
        if self._alt is not None:
            self._alt.append(data)
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == 'table' and self._songlist:
            self._songlist -= 1
        elif tag == 'h2':
            self._heading = False
        elif tag == 'p' and self._alt is not None:
            self.alt_titles = ''.join(self._alt)
            self._alt = None
        elif tag == 'a' and self._href is not None:
            title = ' '.join(''.join(self._text).split())
            if title:
                self.entries.append((self._href, title))
            self._href = None


def parse_album(markup):
    """Return ``(album_title, [(href, title, duration), ...])``.

    The duration is the site's ``m:ss`` column and is used to align tracks with
    an official Japanese release.
    """
    parser = AlbumParser()
    parser.feed(markup)
    parser.close()
    tracks = {}
    for href, text in parser.entries:
        entry = tracks.setdefault(href, {'title': '', 'duration': None})
        if not entry['title']:
            entry['title'] = text
        elif entry['duration'] is None and DURATION_RE.match(text):
            entry['duration'] = text
    return parser.album.strip(), [(href, item['title'], item['duration'])
                                  for href, item in tracks.items()]


def parse_alt_titles(markup):
    parser = AlbumParser()
    parser.feed(markup)
    parser.close()
    return [' '.join(line.split())
            for line in parser.alt_titles.splitlines() if line.strip()]


class SongParser(HTMLParser):
    """Find the direct MP3 URL on one KHInsider song page.

    The player's ``<audio>``/``<source>`` src is preferred: some pages also link
    the song's own KHInsider path, which serves an HTML page rather than audio.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.audio = None
        self.link = None

    @staticmethod
    def _is_mp3(value):
        return (value or '').lower().split('?')[0].endswith('.mp3')

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in ('audio', 'source') and self.audio is None:
            if self._is_mp3(attributes.get('src')):
                self.audio = attributes['src']
        elif tag == 'a' and self.link is None:
            if self._is_mp3(attributes.get('href')):
                self.link = attributes['href']


def parse_mp3_url(markup):
    """Return the CDN MP3 URL found on a song page, or ``None``."""
    parser = SongParser()
    parser.feed(markup)
    parser.close()
    return parser.audio or parser.link


def worker_count():
    """How many album workers to start; 1..MAX_WORKERS (default 3)."""
    try:
        value = int(os.environ.get('KHINSIDER_WORKERS', str(MAX_WORKERS)))
    except ValueError:
        value = MAX_WORKERS
    return max(1, min(MAX_WORKERS, value))


def throttle_request():
    """Space KHInsider requests across all workers so 3 albums stay polite."""
    with REQUEST_LOCK:
        wait = REQUEST_INTERVAL - (time.time() - REQUEST_LAST[0])
        if wait > 0:
            time.sleep(wait)
        REQUEST_LAST[0] = time.time()


def album_lock(url):
    """One lock per album URL, so two workers never write the same folder."""
    with ALBUM_LOCKS_LOCK:
        lock = ALBUM_LOCKS.get(url)
        if lock is None:
            lock = threading.Lock()
            ALBUM_LOCKS[url] = lock
        return lock


_SESSIONS = threading.local()


def reset_sessions():
    """Drop this thread's session (used on retry and by the tests)."""
    if getattr(_SESSIONS, 'session', None) is not None:
        _SESSIONS.session = None


def browser_session(reset=False, impersonation='chrome'):
    """Return this worker's browser-impersonating session, or ``None`` without curl_cffi.

    ワーカーごとに別スレッドなので、セッションは thread-local に持つ。同じ
    ワーカー内では1つのセッションを使って cf_clearance を引き継ぎ、challenge
    されたら ``reset=True`` で作り直す（待つだけでは回復しないことがある）。
    """
    if curl_requests is None:
        return None
    session = getattr(_SESSIONS, 'session', None)
    if session is None or reset:
        session = curl_requests.Session(impersonate=impersonation)
        _SESSIONS.session = session
    return session


def site_headers():
    return {'Referer': 'https://' + SITE + '/'}


def urllib_request(url):
    return urllib.request.Request(ascii_url(url), headers={
        'User-Agent': FALLBACK_USER_AGENT, **site_headers()})


def attempts():
    """Return ``[(wait, impersonation), ...]`` for the first try and each retry."""
    plan = [(0, IMPERSONATIONS[0])]
    for position, wait in enumerate(CHALLENGE_WAITS):
        plan.append((wait, IMPERSONATIONS[(position + 1) % len(IMPERSONATIONS)]))
    return plan


def refresh_session(index, impersonation):
    """The first try reuses the warm session; every retry starts a fresh one."""
    return browser_session(reset=index > 0, impersonation=impersonation)


def retryable(error):
    """A network error is worth a retry; a definite 4xx (404 etc.) is not."""
    code = getattr(error, 'code', None) or getattr(
        getattr(error, 'response', None), 'status_code', None)
    return code is None or code in CHALLENGE_CODES


def http_get(url, timeout=60):
    """Fetch a page with a browser fingerprint, retrying Cloudflare challenges."""
    last = ''
    for index, (wait, impersonation) in enumerate(attempts()):
        if wait:
            time.sleep(wait)
        session = refresh_session(index, impersonation)
        throttle_request()
        if session is None:
            try:
                with urllib.request.urlopen(urllib_request(url), timeout=timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                if error.code in CHALLENGE_CODES:
                    last = 'HTTP %d' % error.code
                    continue
                raise
        try:
            response = session.get(ascii_url(url), timeout=timeout, headers=site_headers())
            if response.status_code in CHALLENGE_CODES:
                last = 'HTTP %d' % response.status_code
                response.close()
                continue
            response.raise_for_status()
            return response.content
        except Exception as error:  # noqa: BLE001 - retry network/curl failures
            if not retryable(error):
                raise
            last = '%s: %s' % (type(error).__name__, error)
            continue
    raise RuntimeError(
        'KHInsiderがbot判定で拒否しました（%s）。少し時間を置いて再試行してください: '
        '%s' % (last, url))


def http_download(url, destination, timeout=600):
    """Download a file with the same session, retrying Cloudflare challenges."""
    last = ''
    for index, (wait, impersonation) in enumerate(attempts()):
        if wait:
            time.sleep(wait)
        session = refresh_session(index, impersonation)
        throttle_request()
        if session is None:
            try:
                with urllib.request.urlopen(urllib_request(url), timeout=timeout) as response, \
                        open(destination, 'wb') as handle:
                    shutil.copyfileobj(response, handle, length=64 * 1024)
                return
            except urllib.error.HTTPError as error:
                if error.code in CHALLENGE_CODES:
                    last = 'HTTP %d' % error.code
                    continue
                raise
        response = None
        try:
            response = session.get(ascii_url(url), timeout=timeout,
                                   headers=site_headers(), stream=True)
            if response.status_code in CHALLENGE_CODES:
                last = 'HTTP %d' % response.status_code
                response.close()
                continue
            response.raise_for_status()
            with open(destination, 'wb') as handle:
                for chunk in response.iter_content(64 * 1024):
                    if chunk:
                        handle.write(chunk)
            return
        except Exception as error:  # noqa: BLE001 - retry network/curl failures
            if not retryable(error):
                raise
            last = '%s: %s' % (type(error).__name__, error)
            if response is not None:
                response.close()
            continue
    raise RuntimeError(
        'KHInsiderの配信元がbot判定で拒否しました（%s）。少し時間を置いて再試行して'
        'ください: %s' % (last, url))


def fetch_json(url, timeout=30):
    request = urllib.request.Request(url, headers={'User-Agent': API_USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def load_dictionary(path=JA_DICTIONARY):
    """Load the manual English-to-Japanese dictionary; a broken file is ignored."""
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def seconds(value):
    """Turn the site's ``m:ss`` into seconds, or ``None``."""
    if not value or ':' not in value:
        return None
    try:
        minutes, secs = value.split(':', 1)
        return int(minutes) * 60 + int(secs)
    except ValueError:
        return None


def itunes_albums(term):
    """Search the Japanese iTunes store for albums matching ``term``."""
    query = urllib.parse.urlencode(
        {'term': term, 'country': 'jp', 'entity': 'album', 'limit': 10})
    return fetch_json(f'{ITUNES_SEARCH}?{query}').get('results', [])


def itunes_tracks(collection_id):
    """Return ``[{number, title, seconds}]`` for one Japanese iTunes album."""
    query = urllib.parse.urlencode(
        {'id': collection_id, 'country': 'jp', 'entity': 'song', 'limit': 200})
    results = fetch_json(f'{ITUNES_LOOKUP}?{query}').get('results', [])
    return [{'number': row.get('trackNumber'), 'title': row.get('trackName'),
             'seconds': (row.get('trackTimeMillis') or 0) / 1000}
            for row in results if row.get('wrapperType') == 'track']


def duration_close(left, right):
    if left is None or not right:
        return False
    return abs(left - right) <= max(2.0, left * 0.03)


def japanese_only(value):
    return re.sub(r'[^\u3040-\u30ff\u4e00-\u9fff]', '', value or '')


def has_japanese(value):
    return bool(re.search(r'[\u3040-\u30ff\u4e00-\u9fff]', value or ''))


def musicbrainz_get(path, params, attempts=4):
    """Call the MusicBrainz web service, throttled, cached and retried on 429/503."""
    query = urllib.parse.urlencode(params)
    url = f'{MUSICBRAINZ}{path}?{query}'
    if url in MUSICBRAINZ_CACHE:
        return MUSICBRAINZ_CACHE[url]
    for attempt in range(attempts):
        with MUSICBRAINZ_LOCK:
            wait = MUSICBRAINZ_INTERVAL - (time.time() - MUSICBRAINZ_LAST[0])
            if wait > 0:
                time.sleep(wait)
            MUSICBRAINZ_LAST[0] = time.time()
        try:
            result = fetch_json(url)
            MUSICBRAINZ_CACHE[url] = result
            return result
        except urllib.error.HTTPError as error:
            if error.code not in (429, 503) or attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))
    return {}


def ordered_terms(terms, limit=3):
    """Deduplicate search terms and put Japanese ones first (strongest signal)."""
    seen = set()
    ordered = []
    for term in terms:
        text = (term or '').strip()
        if text and text not in seen:
            seen.add(text)
            ordered.append(text)
    ordered.sort(key=lambda text: 0 if has_japanese(text) else 1)
    return ordered[:limit]


def musicbrainz_releases(term):
    data = musicbrainz_get('release/', {'query': f'release:"{term}"',
                                        'fmt': 'json', 'limit': 5})
    return data.get('releases', [])


def musicbrainz_tracks(release_id):
    """Return ``[{number, title, seconds}]`` for one MusicBrainz release."""
    data = musicbrainz_get(f'release/{release_id}', {'inc': 'recordings', 'fmt': 'json'})
    tracks = []
    for medium in data.get('media', []):
        for track in medium.get('tracks', []):
            length = track.get('length') or (track.get('recording') or {}).get('length') or 0
            tracks.append({'number': track.get('number'), 'title': track.get('title'),
                           'seconds': length / 1000})
    return tracks


def musicbrainz_match(terms, kh_tracks):
    """Return ``(japanese_album, {track_index: title})`` from MusicBrainz.

    MusicBrainz carries the official Japanese track names for many game
    soundtracks. A release is only used when it has the same number of tracks,
    at least 70% of the durations align, and the matched names are mostly
    Japanese; anything else would put wrong titles on the files.
    """
    expected = len(kh_tracks)
    candidates = []
    seen = set()
    for term in ordered_terms(terms):
        try:
            releases = musicbrainz_releases(term)
        except Exception:  # noqa: BLE001 - a failed lookup just skips the term
            continue
        for release in releases:
            release_id = release.get('id')
            if not release_id or release_id in seen:
                continue
            count = release.get('track-count')
            # Filter before the recording lookup: one request per candidate.
            # 「Expanded & Complete」のような増補盤は曲数が違うため、ある程度の
            # 範囲なら許して録音の長さで照合する（2026-09-16 実機）。
            if count is not None and not (expected * 0.6 <= count <= expected * 1.6):
                continue
            seen.add(release_id)
            candidates.append(release)
            if len(candidates) >= 4:
                break
        if len(candidates) >= 4:
            break
    best = None
    for release in candidates:
        try:
            official = musicbrainz_tracks(release['id'])
        except Exception:  # noqa: BLE001
            continue
        if len(official) < max(3, int(expected * 0.5)):
            continue
        mapping = match_tracks(kh_tracks, official)
        titles = {index + 1: official[position]['title']
                  for index, position in enumerate(mapping)
                  if position is not None and official[position]['title']}
        japanese = sum(1 for title in titles.values() if has_japanese(title))
        if len(titles) < max(3, int(expected * 0.7)):
            continue
        if japanese < max(1, int(len(titles) * 0.5)):
            continue
        score = (len(titles), japanese)
        if best is None or score > best[0]:
            best = (score, release.get('title') or '', titles)
    return (best[1], best[2]) if best else ('', {})


def album_name_matches(term, name):
    """Is this iTunes result really the album we searched for?

    Japanese terms must share their Japanese part with the result; English
    terms need half of their non-generic words to appear in the name. Without
    this a search for an English title can return an unrelated pop album with a
    similar track count.
    """
    term_japanese = japanese_only(term)
    name_japanese = japanese_only(name)
    if term_japanese and name_japanese:
        return term_japanese in name_japanese or name_japanese in term_japanese
    stop = {'the', 'a', 'an', 'of', 'and', 'original', 'soundtrack', 'ost',
            'music', 'collection', 'edition', 'vol', 'from'}
    words = [word for word in re.findall(r'[a-z0-9]+', (term or '').lower())
             if word not in stop]
    if not words:
        return False
    lowered = (name or '').lower()
    return sum(1 for word in words if word in lowered) >= max(1, len(words) // 2)


def match_tracks(kh_tracks, it_tracks):
    """Align KHInsider tracks with an official release.

    Same-length albums are matched by position when the durations line up;
    otherwise each track is matched to the closest unused duration. Returns a
    list of iTunes indices, with ``None`` where nothing close was found.
    """
    mapping = [None] * len(kh_tracks)
    if len(kh_tracks) == len(it_tracks) and it_tracks:
        aligned = sum(duration_close(seconds(kh[2]), it_tracks[i]['seconds'])
                      for i, kh in enumerate(kh_tracks))
        if aligned >= max(1, int(len(kh_tracks) * 0.6)):
            return list(range(len(kh_tracks)))
    used = set()
    for index, kh in enumerate(kh_tracks):
        target = seconds(kh[2])
        if target is None:
            continue
        best = None
        for position, it in enumerate(it_tracks):
            if position in used or not it['seconds']:
                continue
            difference = abs(it['seconds'] - target)
            if duration_close(target, it['seconds']) and (best is None or difference < best[1]):
                best = (position, difference)
        if best:
            mapping[index] = best[0]
            used.add(best[0])
    return mapping


def itunes_match(terms, kh_tracks):
    """Return ``(japanese_album, {track_index: title})`` from the best release.

    Only a release with the same number of tracks and a name that matches the
    search term is considered, and at least 70% of the durations must line up.
    A wrong title is worse than an English one, so the checks stay strict.
    """
    expected = len(kh_tracks)
    best = None
    seen = set()
    fetched = 0
    for term in ordered_terms(terms):
        try:
            results = itunes_albums(term)
        except Exception:  # noqa: BLE001 - a lookup failure just skips the term
            continue
        for row in results:
            if row.get('collectionId') in seen:
                continue
            seen.add(row.get('collectionId'))
            if not album_name_matches(term, row.get('collectionName')):
                continue
            row_count = row.get('trackCount') or 0
            if not (expected * 0.6 <= row_count <= expected * 1.6):
                continue
            if fetched >= 4:
                break
            fetched += 1
            try:
                official = itunes_tracks(row['collectionId'])
            except Exception:  # noqa: BLE001
                continue
            mapping = match_tracks(kh_tracks, official)
            matched = sum(1 for position in mapping if position is not None)
            if matched < max(3, int(min(expected, len(official)) * 0.7)):
                continue
            titles = {index + 1: official[position]['title']
                      for index, position in enumerate(mapping)
                      if position is not None and official[position]['title']}
            score = (len(titles), row.get('collectionName') or '')
            if best is None or score[0] > best[0][0]:
                best = (score, row.get('collectionName') or '', titles)
    return (best[1], best[2]) if best else ('', {})


def resolve_japanese(album_url, album, alt_titles, tracks, dictionary):
    """Return ``(japanese_album, {1-based index: japanese_title})``.

    The manual dictionary wins; iTunes JP fills the gaps. Only tracks with a
    confident match are returned, so everything else keeps the English name.
    """
    slug = album_url.rstrip('/').rsplit('/', 1)[-1]
    entry = (dictionary.get('albums') or {}).get(slug) or {}
    manual = entry.get('tracks') or {}
    titles = {}
    for index, (href, title, _) in enumerate(tracks, start=1):
        filename = track_filename(href, index)
        for key in (str(index), f'{index:02d}', title, filename, Path(filename).stem):
            value = manual.get(key)
            if value:
                titles[index] = str(value)
                break
    terms = [entry.get('itunes_term'), *alt_titles, album]
    _, auto_titles = musicbrainz_match(terms, tracks)
    if not auto_titles:
        _, auto_titles = itunes_match(terms, tracks)
    for index, title in auto_titles.items():
        titles.setdefault(index, title)
    # The album is the game's Japanese title from the page's alternative titles.
    # A matched release only contributes track names, never the album name, so a
    # gamerip is not renamed after a different album (a concert, a remix, ...).
    game_title = next((name for name in alt_titles if has_japanese(name)), '')
    return (entry.get('album') or game_title or ''), titles


def write_tags(path, title='', album='', disc=None, track=None):
    """Write title/album and the track position; skip quietly without mutagen.

    The track number lives in the tags, not in the file name, so the player
    still orders the album while the file name stays just the song title.
    """
    try:
        from mutagen.easyid3 import EasyID3
        from mutagen.id3 import ID3NoHeaderError
    except ImportError:
        return False
    try:
        tags = EasyID3(str(path))
    except ID3NoHeaderError:
        tags = EasyID3()
    if title:
        tags['title'] = title
    if album:
        tags['album'] = album
    if disc:
        tags['discnumber'] = str(disc)
    if track:
        tags['tracknumber'] = str(track)
    tags.save(str(path))
    return True


def download_album(album_url, music_root, report, japanese=False, dictionary=None):
    """Download one album; ``report(done, total, detail)`` shows progress.

    Existing files are kept, so re-running an album only fetches what is
    missing. A track that fails aborts the album and leaves the completed files
    in place for the next attempt. With ``japanese`` the MusicBrainz/iTunes JP
    titles replace the English names in file names and ID3 tags; the track
    number always goes to the tags, never to the file name.
    """
    album_url = validate_album_url(album_url)
    markup = http_get(album_url).decode('utf-8', 'replace')
    album, tracks = parse_album(markup)
    if not tracks:
        raise ValueError('アルバムページからMP3を1件も見つけられませんでした')
    titles, japanese_album = {}, ''
    if japanese:
        report(0, len(tracks), '日本語の曲名を照合中')
        try:
            japanese_album, titles = resolve_japanese(
                album_url, album, parse_alt_titles(markup), tracks, dictionary or {})
        except Exception as error:  # noqa: BLE001 - fall back to English names
            report(0, len(tracks), f'日本語照合に失敗（英語のまま続行）: {error}')
    slug = album_url.rstrip('/').rsplit('/', 1)[-1]
    folder_name = safe_component(japanese_album or album or slug)
    folder = Path(music_root) / 'Khinsider' / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    # File names carry only the song title. The order is kept in the ID3 tags,
    # and a title used twice gets a deterministic " (2)" counter.
    counts = {}
    names = {}
    for index, (href, title, _) in enumerate(tracks, start=1):
        display = titles.get(index) or title
        name = title_filename(display, index) if display else track_filename(href, index)
        key = name.lower()
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > 1:
            name = f'{Path(name).stem} ({counts[key]}).mp3'
        names[index] = name
    report(0, len(tracks), f'{folder_name}（{len(tracks)}曲）')
    for index, (href, title, _) in enumerate(tracks, start=1):
        destination = folder / names[index]
        if destination.exists() and destination.stat().st_size > 0:
            report(index, len(tracks), f'スキップ {destination.name}')
            continue
        song = http_get(urllib.parse.urljoin(album_url, href)).decode('utf-8', 'replace')
        mp3 = parse_mp3_url(song)
        if mp3 is None:
            raise ValueError(f'MP3のURLを解決できませんでした: {title or destination.name}')
        disc, track = track_position(href, index)
        partial = destination.with_name('.' + destination.name + '.part')
        try:
            http_download(mp3, partial)
            write_tags(partial, titles.get(index, ''), japanese_album, disc, track)
            os.replace(partial, destination)
        finally:
            partial.unlink(missing_ok=True)
        report(index, len(tracks), destination.name)
        if index < len(tracks):
            time.sleep(DELAY)


class Job:
    def __init__(self, url, japanese=False):
        self.id = uuid.uuid4().hex[:12]
        self.url = url
        self.japanese = japanese
        self.state = 'queued'
        self.done = 0
        self.total = 0
        self.detail = '待機中'
        self.error = ''
        self.created = time.time()

    @property
    def percent(self):
        return int(self.done * 100 / self.total) if self.total else 0

    @property
    def label(self):
        return STATE_LABELS.get(self.state, self.state)

    def to_dict(self):
        return {'id': self.id, 'url': self.url, 'japanese': self.japanese,
                'state': self.state, 'done': self.done, 'total': self.total,
                'detail': self.detail, 'error': self.error, 'created': self.created}

    @classmethod
    def from_dict(cls, data):
        job = cls(str(data.get('url', '')), bool(data.get('japanese')))
        job.id = str(data.get('id') or job.id)
        job.state = str(data.get('state', 'queued'))
        job.done = int(data.get('done', 0) or 0)
        job.total = int(data.get('total', 0) or 0)
        job.detail = str(data.get('detail', ''))
        job.error = str(data.get('error', ''))
        job.created = float(data.get('created', time.time()) or time.time())
        return job


def save_jobs():
    """Write the job list so the history survives a container recreation.

    Several workers report progress at once, so the write is serialized.
    """
    with JOBS_LOCK:
        jobs = [job.to_dict() for job in JOBS.values()]
    jobs.sort(key=lambda item: item['created'], reverse=True)
    payload = json.dumps(jobs[:JOBS_LIMIT], ensure_ascii=False)
    with SAVE_LOCK:
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            temp = JOBS_FILE.with_name(JOBS_FILE.name + '.tmp')
            temp.write_text(payload)
            os.replace(temp, JOBS_FILE)
        except OSError:
            pass


def load_jobs():
    """Restore the history; an interrupted job becomes retryable, not lost."""
    try:
        data = json.loads(JOBS_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return
    if not isinstance(data, list):
        return
    with JOBS_LOCK:
        for item in data:
            if not isinstance(item, dict):
                continue
            job = Job.from_dict(item)
            if job.state in ('queued', 'running'):
                job.state = 'failed'
                job.error = '再起動で中断しました。「再試行」で続きから取得できます。'
            JOBS[job.id] = job


def reporter(job):
    def report(done, total, detail):
        with JOBS_LOCK:
            job.done, job.total, job.detail = done, total, detail
        save_jobs()
    return report


def worker(music_root):
    while True:
        job = WORK.get()
        try:
            with JOBS_LOCK:
                job.state, job.detail = 'running', 'アルバムページを取得中'
            save_jobs()
            # Albums run in parallel, but the same album never does.
            with album_lock(job.url):
                download_album(job.url, music_root, reporter(job),
                               japanese=job.japanese, dictionary=load_dictionary())
            with JOBS_LOCK:
                job.state = 'done'
                job.detail = f'{job.total}曲を保存しました'
        except Exception as error:  # noqa: BLE001 - surface it on the job page
            with JOBS_LOCK:
                job.state, job.error = 'failed', f'{type(error).__name__}: {error}'
        finally:
            save_jobs()
            WORK.task_done()


def enqueue(url, japanese=False):
    job = Job(url, japanese)
    with JOBS_LOCK:
        JOBS[job.id] = job
    WORK.put(job)
    save_jobs()
    return job


def find_job(job_id):
    with JOBS_LOCK:
        return JOBS.get(job_id)


STYLE = '''<style>
:root{--fg:#1f2937;--muted:#6b7280;--bg:#f9fafb;--card:#fff;--line:#e5e7eb;--accent:#2563eb;--ok:#15803d;--err:#b91c1c;--warn:#b45309}
@media(prefers-color-scheme:dark){:root{--fg:#e5e7eb;--muted:#9ca3af;--bg:#111827;--card:#1f2937;--line:#374151;--accent:#60a5fa;--ok:#4ade80;--err:#f87171;--warn:#fbbf24}}
*{box-sizing:border-box}
body{font-family:system-ui,sans-serif;max-width:760px;margin:0 auto;padding:1.5rem 1rem;color:var(--fg);background:var(--bg);line-height:1.6}
h1{font-size:1.3rem;margin:0 0 .8rem} h2{font-size:1rem;margin:1.6rem 0 .4rem}
a{color:var(--accent)} .muted{color:var(--muted);font-size:.9rem} .error{color:var(--err)}
code{word-break:break-all;font-size:.85em}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:1rem;margin:.8rem 0}
input[type=url]{width:100%;padding:.6rem;font-size:1rem;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}
label{display:block;margin-top:.6rem;font-size:.95rem}
button{margin-top:.8rem;padding:.55rem 1.2rem;font-size:1rem;cursor:pointer;border:0;border-radius:6px;background:var(--accent);color:#fff}
ul{list-style:none;padding:0;margin:0} li{border-top:1px solid var(--line);padding:.7rem 0} li:first-child{border-top:0}
.title{font-weight:600;text-decoration:none;word-break:break-all}
.bar{background:var(--line);border-radius:4px;height:8px;overflow:hidden;margin:.35rem 0}
.bar>span{display:block;height:100%;background:var(--accent)}
.badge{display:inline-block;font-size:.75rem;padding:0 .5rem;border-radius:99px;border:1px solid currentColor;margin-right:.4rem}
.s-running,.s-queued{color:var(--accent)} .s-done{color:var(--ok)} .s-failed{color:var(--err)}
.stats{display:flex;gap:1rem;font-size:.9rem}
.back{display:inline-block;margin-top:1rem}
</style>'''


# ブラウザタブ用。音符と下向き矢印のSVGをdata URIで埋め込み、追加の配信を不要にする。
ICON = ('<link rel="icon" href="data:image/svg+xml,'
        '%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 32 32%2'
        '7%3E%3Crect width=%2732%27 height=%2732%27 rx=%277%27 fill=%27%23256'
        '3eb%27/%3E%3Ccircle cx=%2711%27 cy=%2721%27 r=%273.5%27 fill=%27%23f'
        'ff%27/%3E%3Cpath d=%27M14.5 21V8h6v3.5h-4%27 stroke=%27%23fff%27 str'
        'oke-width=%272%27 fill=%27none%27/%3E%3Cpath d=%27M24 14v8m-3-3 3 3 '
        '3-3%27 stroke=%27%23fff%27 stroke-width=%272%27 fill=%27none%27 stro'
        'ke-linecap=%27round%27 stroke-linejoin=%27round%27/%3E%3C/svg%3E'
        '">')


def page(title, body, refresh=0):
    """Wrap a body in the shared page shell."""
    meta = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ''
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">{meta}
<title>{html.escape(title)}</title>{ICON}{STYLE}</head><body>{body}</body></html>'''


def album_slug(url):
    """A readable album name from the URL, for lists before tags exist."""
    return urllib.parse.unquote(url.rstrip('/').rsplit('/', 1)[-1]) or url


def badge(job):
    return f'<span class="badge s-{html.escape(job.state)}">{html.escape(job.label)}</span>'


def progress(job):
    return f'<div class="bar"><span style="width:{job.percent}%"></span></div>'


def album_folder(album_url, album, alt_titles, japanese, dictionary):
    """The folder this album would use, without the slow MusicBrainz lookup."""
    slug = album_url.rstrip('/').rsplit('/', 1)[-1]
    entry = (dictionary.get('albums') or {}).get(slug) or {}
    japanese_album = ''
    if japanese:
        japanese_album = entry.get('album') or next(
            (name for name in alt_titles if has_japanese(name)), '')
    return safe_component(japanese_album or album or slug)


def album_overview(album_url, japanese, dictionary):
    """Fetch the album page and report what is already in the library.

    Used before starting so the operator can see how far a previous run got
    when the job history is gone.
    """
    markup = http_get(album_url).decode('utf-8', 'replace')
    album, tracks = parse_album(markup)
    alt_titles = parse_alt_titles(markup)
    folder_name = album_folder(album_url, album, alt_titles, japanese, dictionary)
    folder = MUSIC_ROOT / 'Khinsider' / folder_name
    names = (sorted(path.name for path in folder.glob('*.mp3'))
             if folder.is_dir() else [])
    return folder_name, len(tracks), names


def confirm_page(url, japanese, folder_name, total, names):
    """Ask before re-running an album that already has files on disk."""
    existing = len(names)
    sample = ''.join(f'<li>{html.escape(name)}</li>' for name in names[:20])
    more = (f'<p class="muted">ほか {existing - 20} 件</p>' if existing > 20 else '')
    remaining = max(0, total - existing)
    state = ('すべて保存済みのようです（再実行してもスキップされます）'
             if total and existing >= total
             else f'未取得は {remaining} 曲です')
    japanese_field = '<input type="hidden" name="japanese" value="1">' if japanese else ''
    mode = '日本語の曲名' if japanese else '英語のまま'
    return page('KHInsider: 確認', f'''
<h1>このアルバムは既に一部保存されています</h1>
<div class="card">
<p><code>{html.escape(url)}</code>（{mode}）</p>
<p class="muted">保存先: <code>music/Khinsider/{html.escape(folder_name)}/</code></p>
<p><b>{existing} / {total} 曲</b>が保存済みです。{html.escape(state)}</p>
<ul class="muted">{sample}</ul>{more}
<form method="post" action="/download">
<input type="hidden" name="url" value="{html.escape(url, quote=True)}">{japanese_field}
<input type="hidden" name="confirm" value="1">
<button type="submit">続きからダウンロード</button>
</form></div>
<a class="back" href="/">キャンセル</a>''')


def index_page():
    with JOBS_LOCK:
        jobs = sorted(JOBS.values(), key=lambda job: job.created, reverse=True)
        running = sum(1 for job in jobs if job.state in ('queued', 'running'))
        done = sum(1 for job in jobs if job.state == 'done')
        failed = sum(1 for job in jobs if job.state == 'failed')
    rows = []
    for job in jobs:
        tag = '・日本語' if job.japanese else ''
        count = f'{job.done}/{job.total}曲・' if job.total else ''
        detail = html.escape(job.detail)
        if job.error:
            detail += f' <span class="error">{html.escape(job.error)}</span>'
        bar = progress(job) if job.state in ('queued', 'running') else ''
        rows.append(
            f'<li>{badge(job)}<a class="title" href="/jobs/{job.id}">'
            f'{html.escape(album_slug(job.url))}</a>{bar}'
            f'<div class="muted">{count}{job.percent}%{tag}・{detail}</div></li>')
    listing = ''.join(rows) or '<li class="muted">まだジョブはありません</li>'
    return page('KHInsider 一括ダウンロード', f'''
<h1>KHInsider アルバム一括ダウンロード</h1>
<form class="card" method="post" action="/download">
<input type="url" name="url" required autofocus placeholder="https://downloads.khinsider.com/game-soundtracks/album/...">
<label><input type="checkbox" name="japanese" value="1">
日本語の曲名に戻す<span class="muted">（MusicBrainz照合。見つからない曲は英語のまま）</span></label>
<button type="submit">すべてダウンロード</button>
<p class="muted">収録MP3を <code>music/Khinsider/&lt;アルバム名&gt;/</code> へ保存します。
ダウンロードできる権利のある音源だけを指定してください。</p>
</form>
<h2>実行履歴</h2>
<div class="stats"><span class="s-running">実行中 {running}</span>
<span class="s-done">完了 {done}</span><span class="s-failed">失敗 {failed}</span></div>
<div class="card"><ul>{listing}</ul></div>''', refresh=5 if running else 0)


def job_page(job):
    if job is None:
        return None
    running = job.state in ('queued', 'running')
    error = (f'<p class="error">{html.escape(job.error)}</p>' if job.error else '')
    mode = '日本語の曲名' if job.japanese else '英語のまま'
    retry = ''
    if job.state in ('failed', 'done'):
        # Same album, same option. Saved files are skipped, so a retry resumes.
        japanese = ('<input type="hidden" name="japanese" value="1">'
                    if job.japanese else '')
        retry = (f'<form method="post" action="/download">'
                 f'<input type="hidden" name="url" '
                 f'value="{html.escape(job.url, quote=True)}">{japanese}'
                 f'<button type="submit">再試行</button></form>')
    return page(f'KHInsider: {job.label}', f'''
<h1>{html.escape(album_slug(job.url))}</h1>
<div class="card">
<p>{badge(job)}<span class="muted">{mode}</span></p>
{progress(job)}
<p>{job.done} / {job.total} 曲（{job.percent}%）</p>
<p class="muted">{html.escape(job.detail)}</p>{error}{retry}
<p class="muted"><code>{html.escape(job.url)}</code></p></div>
<a class="back" href="/">戻る</a>''', refresh=3 if running else 0)


class Handler(BaseHTTPRequestHandler):
    server_version = 'shake-khinsider/1.0'
    timeout = 120

    def _send(self, status, body, content_type='text/html; charset=utf-8'):
        payload = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/healthz':
            self._send(200, '{"status":"ok"}', 'application/json')
        elif path == '/':
            self._send(200, index_page())
        elif path.startswith('/jobs/'):
            page = job_page(find_job(path.rsplit('/', 1)[-1]))
            self._send(200, page) if page else self._send(404, '<p>見つかりません</p>')
        else:
            self._send(404, '<p>見つかりません</p>')

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != '/download':
            self._send(404, '<p>見つかりません</p>')
            return
        length = int(self.headers.get('Content-Length', '0') or 0)
        if length <= 0 or length > 8192:
            self._send(400, '<p>URLを入力してください</p>')
            return
        values = urllib.parse.parse_qs(self.rfile.read(length).decode('utf-8', 'replace'))
        url = (values.get('url') or [''])[0]
        try:
            validate_album_url(url)
        except ValueError as error:
            self._send(400, page('KHInsider: 入力エラー',
                                f'<p class="error">{html.escape(str(error))}</p>'
                                '<a class="back" href="/">戻る</a>'))
            return
        japanese = bool(values.get('japanese'))
        # Before starting, check the library and ask if files already exist.
        if not values.get('confirm'):
            try:
                folder_name, total, names = album_overview(
                    url, japanese, load_dictionary())
            except Exception as error:  # noqa: BLE001 - show it and allow a forced run
                japanese_field = ('<input type="hidden" name="japanese" value="1">'
                                  if japanese else '')
                self._send(200, page('KHInsider: 確認できません', f'''
<h1>既存の確認ができませんでした</h1>
<div class="card">
<p class="error">{html.escape(type(error).__name__ + ': ' + str(error))}</p>
<p>そのまま実行しますか？</p>
<form method="post" action="/download">
<input type="hidden" name="url" value="{html.escape(url, quote=True)}">{japanese_field}
<input type="hidden" name="confirm" value="1">
<button type="submit">そのままダウンロード</button></form></div>
<a class="back" href="/">戻る</a>'''))
                return
            if names:
                self._send(200, confirm_page(url, japanese, folder_name, total, names))
                return
        job = enqueue(url, japanese=japanese)
        self.send_response(303)
        self.send_header('Location', f'/jobs/{job.id}')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f'{self.address_string()} {fmt % args}', flush=True)


def main():
    music_root = Path(os.environ.get('KHINSIDER_MUSIC', '/music'))
    load_jobs()
    server = ThreadingHTTPServer(
        ('0.0.0.0', int(os.environ.get('KHINSIDER_PORT', '5820'))), Handler)
    for _ in range(worker_count()):
        threading.Thread(target=worker, args=(music_root,), daemon=True).start()
    server.serve_forever()


if __name__ == '__main__':
    main()
