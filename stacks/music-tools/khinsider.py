#!/usr/bin/env python3
"""Download every track of a KHInsider album page into the shared music library.

MeTube takes one media URL at a time. KHInsider wraps an album behind an album
page and a per-song page, so this small browser tool turns
``https://downloads.khinsider.com/game-soundtracks/album/<slug>`` into a folder
under ``music/Khinsider/<album>/``. Navidrome and organize.py pick that up like
any other import. It runs next to MeTube and sits behind the same Forward Auth.

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

SITE = 'downloads.khinsider.com'
# KHInsider の HTML には href に生の非ASCII（é など）が混ざる。urllib は
# ASCII 以外のURLを拒否するため、予約文字と %XX を保ったまま percent-encode する。
URL_SAFE = ":/?#[]@!$&'()*+,;=%~"


def ascii_url(url):
    return urllib.parse.quote(url or '', safe=URL_SAFE)
ALBUM_PREFIX = '/game-soundtracks/album/'
USER_AGENT = 'shake-cloud-khinsider/1.0 (+https://github.com/rurutheGeek/shake-cloud)'
MUSICBRAINZ = 'https://musicbrainz.org/ws/2/'
ITUNES_SEARCH = 'https://itunes.apple.com/search'
ITUNES_LOOKUP = 'https://itunes.apple.com/lookup'
DURATION_RE = re.compile(r'^\d{1,3}:[0-5]\d$')
# MusicBrainz asks for at most one request per second.
MUSICBRAINZ_INTERVAL = 1.0
JOBS = {}
JOBS_LOCK = threading.Lock()
WORK = queue.Queue()
DELAY = float(os.environ.get('KHINSIDER_DELAY', '0.4'))
JA_DICTIONARY = os.environ.get('KHINSIDER_JA', '/tools/khinsider-ja.json')
MUSICBRAINZ_LOCK = threading.Lock()
MUSICBRAINZ_LAST = [0.0]
MUSICBRAINZ_CACHE = {}


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


def http_get(url, timeout=60):
    request = urllib.request.Request(ascii_url(url), headers={
        'User-Agent': USER_AGENT, 'Referer': 'https://' + SITE + '/'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def http_download(url, destination, timeout=600):
    request = urllib.request.Request(ascii_url(url), headers={
        'User-Agent': USER_AGENT, 'Referer': 'https://' + SITE + '/'})
    with urllib.request.urlopen(request, timeout=timeout) as response, \
            open(destination, 'wb') as handle:
        shutil.copyfileobj(response, handle, length=64 * 1024)


def fetch_json(url, timeout=30):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
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


def reporter(job):
    def report(done, total, detail):
        with JOBS_LOCK:
            job.done, job.total, job.detail = done, total, detail
    return report


def worker(music_root):
    while True:
        job = WORK.get()
        try:
            with JOBS_LOCK:
                job.state, job.detail = 'running', 'アルバムページを取得中'
            download_album(job.url, music_root, reporter(job),
                           japanese=job.japanese, dictionary=load_dictionary())
            with JOBS_LOCK:
                job.state = 'done'
                job.detail = f'{job.total}曲を保存しました'
        except Exception as error:  # noqa: BLE001 - surface it on the job page
            with JOBS_LOCK:
                job.state, job.error = 'failed', f'{type(error).__name__}: {error}'
        finally:
            WORK.task_done()


def enqueue(url, japanese=False):
    job = Job(url, japanese)
    with JOBS_LOCK:
        JOBS[job.id] = job
    WORK.put(job)
    return job


def find_job(job_id):
    with JOBS_LOCK:
        return JOBS.get(job_id)


STYLE = '''<style>
 body{font-family:system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;color:#1f2937}
 h1{font-size:1.4rem} .muted{color:#6b7280} input[type=url]{width:100%;padding:.6rem;font-size:1rem;box-sizing:border-box}
 button{margin-top:.6rem;padding:.55rem 1.2rem;font-size:1rem;cursor:pointer}
 ul{list-style:none;padding:0} li{border-top:1px solid #e5e7eb;padding:.6rem 0}
 .bar{background:#e5e7eb;border-radius:4px;height:12px;overflow:hidden}
 .bar>span{display:block;height:100%;background:#2563eb}
 code{word-break:break-all} .error{color:#b91c1c} label{display:block;margin-top:.6rem}
</style>'''


def index_page():
    with JOBS_LOCK:
        jobs = sorted(JOBS.values(), key=lambda job: job.created, reverse=True)
    rows = []
    for job in jobs:
        tag = '・日本語' if job.japanese else ''
        rows.append(
            f'<li><a href="/jobs/{job.id}">{html.escape(job.url)}</a><br>'
            f'<span class="muted">{html.escape(job.state)}・{job.percent}%{tag}・'
            f'{html.escape(job.detail)}</span></li>')
    listing = ''.join(rows) or '<li class="muted">まだジョブはありません</li>'
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KHInsider 一括ダウンロード</title>{STYLE}</head><body>
<h1>KHInsider アルバム一括ダウンロード</h1>
<p class="muted">downloads.khinsider.com のアルバムURLを貼り付けると、収録MP3を
<code>music/Khinsider/&lt;アルバム名&gt;/</code> へ順に保存します。
ダウンロードできる権利のある音源だけを指定してください。</p>
<form method="post" action="/download">
<input type="url" name="url" required placeholder="https://downloads.khinsider.com/game-soundtracks/album/...">
<label><input type="checkbox" name="japanese" value="1">
日本語の曲名に戻す（MusicBrainz照合。見つからない曲は英語のまま）</label>
<button type="submit">すべてダウンロード</button>
</form>
<h2 style="font-size:1rem">実行履歴</h2>
<ul>{listing}</ul></body></html>'''


def job_page(job):
    if job is None:
        return None
    running = job.state in ('queued', 'running')
    refresh = '<meta http-equiv="refresh" content="3">' if running else ''
    error = (f'<p class="error">{html.escape(job.error)}</p>' if job.error else '')
    mode = '日本語の曲名' if job.japanese else '英語のまま'
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">{refresh}
<title>KHInsider: {html.escape(job.state)}</title>{STYLE}</head><body>
<h1>KHInsider 一括ダウンロード</h1>
<p><code>{html.escape(job.url)}</code>（{mode}）</p>
<div class="bar"><span style="width:{job.percent}%"></span></div>
<p>{job.done} / {job.total} 曲（{job.percent}%）</p>
<p>{html.escape(job.detail)}</p>{error}
<p><a href="/">戻る</a></p></body></html>'''


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
            self._send(400, f'<p class="error">{html.escape(str(error))}</p>'
                            '<p><a href="/">戻る</a></p>')
            return
        job = enqueue(url, japanese=bool(values.get('japanese')))
        self.send_response(303)
        self.send_header('Location', f'/jobs/{job.id}')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f'{self.address_string()} {fmt % args}', flush=True)


def main():
    music_root = Path(os.environ.get('KHINSIDER_MUSIC', '/music'))
    server = ThreadingHTTPServer(
        ('0.0.0.0', int(os.environ.get('KHINSIDER_PORT', '5820'))), Handler)
    threading.Thread(target=worker, args=(music_root,), daemon=True).start()
    server.serve_forever()


if __name__ == '__main__':
    main()
