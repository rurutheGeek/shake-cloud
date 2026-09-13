#!/usr/bin/env python3
"""Tag API for the Nextcloud tag editor (music-tools on media-01).

The shake_tags Nextcloud app reads and writes audio tags through this small
API. It runs next to the library in the music-tools container, so mutagen can
work on /music directly, and it asks MusicBrainz for candidate metadata.

Configuration (compose environment):
  TAG_API_TOKEN   shared secret (SOPS)
  TAG_API_PORT    default 5810
  TAG_API_MUSIC   default /music
  TAG_API_STATE   default /state
"""
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ALLOWED_FIELDS = {
    'title', 'artist', 'album', 'albumartist', 'tracknumber',
    'discnumber', 'date', 'genre', 'composer',
}
ALLOWED_EXTENSIONS = {'.mp3'}
USER_AGENT = 'shake-cloud-music-tags/1.0 (+https://github.com/rurutheGeek/shake-cloud)'
MUSICBRAINZ = 'https://musicbrainz.org/ws/2/recording'


def normalize_path(raw, music_root):
    """Return a safe path relative to the music library.

    The Nextcloud controller may send the container path of its external
    storage ("/library/music/..."), the container-side library path
    ("/music/...") or a library-relative path. All are reduced to a relative
    path so the service always works inside its own /music.
    """
    value = urllib.parse.unquote(raw or '').replace('\\', '/').strip()
    prefixes = {str(music_root).rstrip('/'), '/library/music', '/music'}
    for prefix in prefixes:
        if prefix and value == prefix:
            value = ''
        elif prefix and value.startswith(prefix + '/'):
            value = value[len(prefix) + 1:]
    if not value:
        raise ValueError('path is required')
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('path must stay inside the music library')
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError('unsupported audio extension')
    return path


def clean_tags(values):
    """Keep the supported fields and turn every value into a list of strings."""
    if not isinstance(values, dict):
        raise ValueError('tags must be an object')
    clean = {}
    for key, value in values.items():
        if key not in ALLOWED_FIELDS:
            raise ValueError(f'unsupported tag field: {key}')
        items = value if isinstance(value, list) else [value]
        items = [str(item) for item in items if item is not None and str(item) != '']
        if items:
            clean[key] = items
    return clean


def read_tags(path):
    """Read the supported tags from an audio file (returns lists of values)."""
    import mutagen
    audio = mutagen.File(path, easy=True)
    if audio is None or audio.tags is None:
        return {}
    return {key: list(audio.tags[key])
            for key in audio.tags if key in ALLOWED_FIELDS}


def apply_tags(path, backup_dir, relative, values):
    """Write the given tags, keeping a copy of the original ID3 block."""
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3, ID3NoHeaderError
    clean = clean_tags(values)
    try:
        tags = EasyID3(path)
    except ID3NoHeaderError:
        tags = EasyID3()
    current = {key: list(tags[key]) for key in tags if key in ALLOWED_FIELDS}
    changes = {key: value for key, value in clean.items()
               if current.get(key) != value}
    if not changes:
        return {'changed': False}
    backup = Path(backup_dir) / (str(relative) + '.id3')
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        try:
            ID3(path).save(backup)
        except ID3NoHeaderError:
            backup.with_suffix('.no-id3').touch()
    for key, value in changes.items():
        tags[key] = value
    tags.save(path)
    os.utime(path, None)
    return {'changed': True, 'tags': clean}


def mb_query(artist, title, album):
    """Build the MusicBrainz search query from whatever fields are known."""
    parts = []
    if title:
        parts.append(f'recording:"{title}"')
    if artist:
        parts.append(f'artist:"{artist}"')
    if album:
        parts.append(f'release:"{album}"')
    return ' AND '.join(parts)


def mb_candidates(artist, title, album, limit=5, timeout=15):
    """Ask MusicBrainz for recording candidates."""
    query = mb_query(artist, title, album)
    if not query:
        return []
    url = (f'{MUSICBRAINZ}?query={urllib.parse.quote(query)}'
           f'&fmt=json&limit={int(limit)}')
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, ValueError, OSError) as error:
        raise RuntimeError(f'MusicBrainz lookup failed: {error}') from error
    candidates = []
    for recording in payload.get('recordings', []):
        credits = []
        for part in recording.get('artist-credit') or []:
            if isinstance(part, dict):
                credits.append(part.get('name')
                               or (part.get('artist') or {}).get('name') or '')
        release = (recording.get('releases') or [{}])[0]
        candidates.append({
            'title': recording.get('title') or '',
            'artist': ' & '.join(name for name in credits if name),
            'album': release.get('title') or '',
            'date': (release.get('date') or '')[:4],
            'musicbrainzId': recording.get('id') or '',
        })
    return candidates


def read_body(handler, length):
    """Read a fixed-length or chunked request body."""
    if handler.headers.get('Transfer-Encoding', '').lower() == 'chunked':
        chunks = []
        while True:
            size_line = handler.rfile.readline().split(b';')[0].strip()
            size = int(size_line or b'0', 16)
            if size == 0:
                handler.rfile.readline()
                break
            chunks.append(handler.rfile.read(size))
            handler.rfile.read(2)
        return b''.join(chunks)
    return handler.rfile.read(length) if length > 0 else b''


class TagHandler(BaseHTTPRequestHandler):
    server_version = 'music-tag-api/1.0'
    timeout = 120

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        header = self.headers.get('Authorization') or ''
        return hmac.compare_digest(header, 'Bearer ' + self.server.token)

    def _query(self):
        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

    def _content_length(self):
        try:
            return int(self.headers.get('Content-Length', '0') or 0)
        except ValueError:
            return 0

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/healthz':
            self._json(200, {'status': 'ok'})
            return
        if not self._authorized():
            self._json(401, {'error': 'unauthorized'})
            return
        if path == '/tags':
            query = self._query()
            try:
                relative = normalize_path((query.get('path') or [''])[0],
                                          self.server.music)
            except ValueError as error:
                self._json(400, {'error': str(error)})
                return
            absolute = self.server.music / relative
            if not absolute.is_file():
                self._json(404, {'error': 'file not found'})
                return
            try:
                tags = read_tags(str(absolute))
            except Exception as error:  # noqa: BLE001 - report mutagen failures
                self._json(500, {'error': str(error)})
                return
            self._json(200, {'path': str(relative), 'tags': tags})
            return
        if path == '/musicbrainz':
            query = self._query()
            try:
                candidates = mb_candidates(
                    (query.get('artist') or [''])[0],
                    (query.get('title') or [''])[0],
                    (query.get('album') or [''])[0])
            except RuntimeError as error:
                self._json(502, {'error': str(error)})
                return
            self._json(200, {'candidates': candidates})
            return
        self._json(404, {'error': 'not found'})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path != '/tags':
            self._json(404, {'error': 'not found'})
            return
        if not self._authorized():
            self._json(401, {'error': 'unauthorized'})
            return
        try:
            payload = json.loads(read_body(self, self._content_length()) or b'{}')
            relative = normalize_path(payload.get('path'), self.server.music)
        except ValueError as error:
            self._json(400, {'error': str(error)})
            return
        absolute = self.server.music / relative
        if not absolute.is_file():
            self._json(404, {'error': 'file not found'})
            return
        try:
            result = apply_tags(str(absolute),
                                self.server.state / 'tag-backups',
                                relative, payload.get('tags') or {})
        except ValueError as error:
            self._json(400, {'error': str(error)})
            return
        except Exception as error:  # noqa: BLE001 - report mutagen failures
            self._json(500, {'error': str(error)})
            return
        self._json(200, result)

    def log_message(self, fmt, *args):
        print(f'{self.address_string()} {fmt % args}', flush=True)


def main():
    server = ThreadingHTTPServer(
        ('0.0.0.0', int(os.environ.get('TAG_API_PORT', '5810'))), TagHandler)
    server.token = os.environ['TAG_API_TOKEN']
    server.music = Path(os.environ.get('TAG_API_MUSIC', '/music'))
    server.state = Path(os.environ.get('TAG_API_STATE', '/state'))
    server.serve_forever()


if __name__ == '__main__':
    main()
