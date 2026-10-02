#!/usr/bin/env python3
"""全曲レビュー（いいね・指摘・試聴）ボード。

media-01 の music-tools で動き、Caddy の Forward Auth（navidrome の /review/）
の後ろから使う。ページ遷移なしで試聴でき、正しい曲は「いいね」、間違いは
項目・正しい値・メモ付きの「指摘」としてサーバ側へ保存する。指摘は
/state/events.jsonl に追記するだけなので、AI や運用が読んでタグを直せる。

索引は Navidrome の SQLite（media_file）から作る。タグの正本はファイルだが、
一覧は Navidrome が見ている内容と揃え、NFS 上の全曲読み直しを避ける。

  REVIEW_PORT   待ち受けポート（既定 5830）
  REVIEW_MUSIC  音楽ライブラリ（既定 /music）
  REVIEW_STATE  状態の置き場（既定 /state）
  NAVIDROME_DB  Navidrome の DB（既定 /navidrome/navidrome.db）
"""
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

PORT = int(os.environ.get('REVIEW_PORT', '5830'))
MUSIC = Path(os.environ.get('REVIEW_MUSIC', '/music')).resolve()
STATE = Path(os.environ.get('REVIEW_STATE', '/state'))
NAVIDROME_DB = Path(os.environ.get('NAVIDROME_DB', '/navidrome/navidrome.db'))
EVENTS_FILE = STATE / 'events.jsonl'
INDEX_FILE = STATE / 'index.json'
USER_HEADERS = ('Remote-User', 'X-Authentik-Username')
MAX_BODY = 64 * 1024
VOTE_FIELDS = ('title', 'artist', 'album', 'albumartist', 'composer',
               'tracknumber', 'discnumber', 'genre', 'other')

INDEX = []
INDEX_LOCK = threading.Lock()
STATUS = {'building': False, 'built_at': 0.0, 'error': ''}
VOTES = {}
VOTES_LOCK = threading.Lock()


def participants_of(raw, role):
    """Navidrome の participants JSON から指定ロールの名前を返す。"""
    try:
        data = json.loads(raw or '{}')
    except ValueError:
        return ''
    if not isinstance(data, dict):
        return ''
    names = []
    for entry in data.get(role) or []:
        name = entry.get('name') if isinstance(entry, dict) else entry
        if name and str(name).strip():
            names.append(str(name).strip())
    return ', '.join(names)


def read_navidrome(db_path):
    """Navidrome の media_file 表から索引の行を作る。"""
    con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    try:
        rows = con.execute(
            'SELECT path, title, album, artist, album_artist, track_number,'
            ' disc_number, genre, duration, participants'
            ' FROM media_file WHERE missing = 0').fetchall()
    finally:
        con.close()
    tracks = []
    for (path, title, album, artist, album_artist, track, disc, genre,
         duration, participants) in rows:
        if not path:
            continue
        tracks.append({
            'path': path,
            'title': title or Path(path).stem,
            'artist': artist or '',
            'album': album or '',
            'albumartist': album_artist or '',
            'composer': participants_of(participants, 'composer'),
            'genre': genre or '',
            'disc': str(disc) if disc else '',
            'track': str(track) if track else '',
            'length': round(float(duration or 0), 1),
        })
    return tracks


def build_index():
    STATUS['building'] = True
    STATUS['error'] = ''
    try:
        tracks = read_navidrome(NAVIDROME_DB)
        tracks.sort(key=lambda row: (
            (row['albumartist'] or row['artist'] or '不明').casefold(),
            (row['album'] or '不明').casefold(),
            int(row['disc'] or 1) if str(row['disc'] or '1').isdigit() else 1,
            int(row['track'] or 0) if str(row['track'] or '0').isdigit() else 0,
            row['title'].casefold()))
        with INDEX_LOCK:
            INDEX[:] = tracks
        STATUS['built_at'] = time.time()
        save_index()
    except Exception as error:  # noqa: BLE001 - 画面に出す
        STATUS['error'] = f'{type(error).__name__}: {error}'
    finally:
        STATUS['building'] = False


def save_index():
    payload = {'built_at': STATUS['built_at'], 'tracks': INDEX}
    tmp = INDEX_FILE.with_name(INDEX_FILE.name + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, INDEX_FILE)


def load_index():
    try:
        payload = json.loads(INDEX_FILE.read_text(encoding='utf-8'))
        with INDEX_LOCK:
            INDEX[:] = payload.get('tracks') or []
        STATUS['built_at'] = float(payload.get('built_at') or 0)
    except (OSError, ValueError):
        pass


def load_events():
    try:
        lines = EVENTS_FILE.read_text(encoding='utf-8').splitlines()
    except OSError:
        return
    with VOTES_LOCK:
        for line in lines:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get('path') and event.get('user'):
                VOTES[(event['user'], event['path'])] = event


def append_event(event):
    STATE.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False) + '\n'
    with open(EVENTS_FILE, 'a', encoding='utf-8') as handle:
        handle.write(line)


def vote_for(user, path):
    with VOTES_LOCK:
        return VOTES.get((user, path))


def index_snapshot():
    with INDEX_LOCK:
        return list(INDEX)


def artist_of(row):
    return row['albumartist'] or row['artist'] or '不明'


def album_of(row):
    return row['album'] or '不明'


def summarize(user):
    tracks = index_snapshot()
    artists = {}
    albums = {}
    checked = 0
    for row in tracks:
        vote = vote_for(user, row['path'])
        done = vote is not None
        checked += 1 if done else 0
        artist = artists.setdefault(artist_of(row), {'name': artist_of(row), 'tracks': 0, 'checked': 0, 'albums': {}})
        artist['tracks'] += 1
        artist['checked'] += 1 if done else 0
        album = artist['albums'].setdefault(album_of(row), {'name': album_of(row), 'tracks': 0, 'checked': 0})
        album['tracks'] += 1
        album['checked'] += 1 if done else 0
        albums[(artist_of(row), album_of(row))] = album
    for artist in artists.values():
        artist['complete'] = artist['tracks'] > 0 and artist['checked'] == artist['tracks']
        for album in artist['albums'].values():
            album['complete'] = album['tracks'] > 0 and album['checked'] == album['tracks']
    return tracks, artists, albums, checked


def current_user(headers):
    for header in USER_HEADERS:
        value = (headers.get(header) or '').strip()
        if value:
            return value.removeprefix('sso_')[:64]
    return 'local'


def clean_corrections(payload):
    """Accept several fields per flag (legacy single field/value still works)."""
    raw = payload.get('corrections')
    if raw is None:
        field = str(payload.get('field') or '')[:32]
        value = str(payload.get('value') or '')[:500]
        raw = [{'field': field, 'value': value}] if field or value else []
    if not isinstance(raw, list):
        raise ValueError('corrections must be a list')
    corrections = []
    for item in raw[:20]:
        if not isinstance(item, dict):
            raise ValueError('corrections must be objects')
        field = str(item.get('field') or '')[:32]
        value = str(item.get('value') or '')[:500]
        if field and field not in VOTE_FIELDS:
            raise ValueError(f'unknown field: {field}')
        if field or value:
            corrections.append({'field': field, 'value': value})
    return corrections


def safe_media(relative):
    """Resolve a library-relative path and refuse anything outside /music."""
    value = unquote(relative or '').lstrip('/')
    path = (MUSIC / value).resolve()
    if not str(path).startswith(str(MUSIC) + os.sep):
        return None
    if path.suffix.lower() != '.mp3' or not path.is_file():
        return None
    return path


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = 'music-review/1.0'

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _html(self):
        body = PAGE.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get('Content-Length', '0') or 0)
        if length <= 0 or length > MAX_BODY:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode('utf-8', 'replace'))
        except ValueError:
            return {}

    def _media(self, relative):
        path = safe_media(relative)
        if path is None:
            self.send_error(404)
            return
        size = path.stat().st_size
        start, end = 0, size - 1
        status = 200
        header = self.headers.get('Range') or ''
        if header.startswith('bytes='):
            spec = header[6:].split(',')[0].strip()
            first, _, last = spec.partition('-')
            try:
                if first:
                    start = int(first)
                if last:
                    end = min(int(last), size - 1)
            except ValueError:
                start, end = 0, size - 1
            if start > end or start >= size:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.end_headers()
                return
            status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header('Content-Type', 'audio/mpeg')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(length))
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        with open(path, 'rb') as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(65536, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                remaining -= len(chunk)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path.rstrip('/') or '/'
        user = current_user(self.headers)
        if path == '/':
            self._html()
            return
        if path == '/healthz':
            self._json(200, {'status': 'ok', 'building': STATUS['building']})
            return
        if path == '/api/state':
            tracks, artists, _, checked = summarize(user)
            self._json(200, {
                'user': user,
                'building': STATUS['building'],
                'built_at': STATUS['built_at'],
                'error': STATUS['error'],
                'total': len(tracks),
                'checked': checked,
                'artists': sorted(artists.values(),
                                  key=lambda item: item['name'].casefold()),
            })
            return
        if path == '/api/albums':
            artist = (query.get('artist') or [''])[0]
            _, _, albums, _ = summarize(user)
            rows = [album for (owner, _), album in albums.items() if owner == artist]
            self._json(200, {'albums': sorted(rows, key=lambda item: item['name'].casefold())})
            return
        if path == '/api/tracks':
            artist = (query.get('artist') or [''])[0]
            album = (query.get('album') or [''])[0]
            rows = []
            for row in index_snapshot():
                if artist_of(row) != artist or album_of(row) != album:
                    continue
                vote = vote_for(user, row['path'])
                rows.append({**row, 'vote': vote, 'checked': vote is not None})
            self._json(200, {'tracks': rows})
            return
        if path == '/api/reports':
            reports = []
            with VOTES_LOCK:
                for event in VOTES.values():
                    if event.get('vote') != 'flag':
                        continue
                    reports.append(event)
            reports.sort(key=lambda item: item.get('ts', ''), reverse=True)
            self._json(200, {'reports': reports})
            return
        if path.startswith('/media/'):
            self._media(self.path[len('/media/'):].split('?', 1)[0])
            return
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        user = current_user(self.headers)
        if path == '/api/refresh':
            if not STATUS['building']:
                threading.Thread(target=build_index, daemon=True).start()
            self._json(200, {'building': True})
            return
        if path != '/api/vote':
            self.send_error(404)
            return
        payload = self._body()
        relative = str(payload.get('path') or '')
        if safe_media(relative) is None:
            self._json(400, {'error': 'unknown track'})
            return
        vote = payload.get('vote') or ''
        if vote not in ('', 'like', 'flag'):
            self._json(400, {'error': 'vote must be like, flag or empty'})
            return
        try:
            corrections = clean_corrections(payload) if vote == 'flag' else []
        except ValueError as error:
            self._json(400, {'error': str(error)})
            return
        event = {
            'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'user': user,
            'path': relative,
            'vote': vote,
            'field': corrections[0]['field'] if corrections else '',
            'value': corrections[0]['value'] if corrections else '',
            'corrections': corrections,
            'note': str(payload.get('note') or '')[:1000],
        }
        append_event(event)
        with VOTES_LOCK:
            if vote:
                VOTES[(user, relative)] = event
            else:
                VOTES.pop((user, relative), None)
        self._json(200, {'ok': True, 'vote': event if vote else None})

    def log_message(self, fmt, *args):
        print(f'{self.address_string()} {fmt % args}', flush=True)


PAGE = r'''<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>全曲レビュー</title>
<style>
:root{color-scheme:dark}
body{font-family:sans-serif;font-size:13px;margin:0;background:#141414;color:#d8d8d8}
header{position:sticky;top:0;z-index:5;display:flex;gap:12px;align-items:center;
  padding:8px 12px;background:#1d1d1d;border-bottom:1px solid #333}
header h1{font-size:15px;margin:0;white-space:nowrap}
header .grow{flex:1}
header input{background:#111;color:#eee;border:1px solid #444;border-radius:4px;padding:4px 8px;width:220px}
header button{background:#2b2b2b;color:#ddd;border:1px solid #444;border-radius:4px;padding:4px 8px;cursor:pointer}
main{display:grid;grid-template-columns:260px 220px 1fr;gap:0;min-height:calc(100vh - 96px)}
body.no-aside main{grid-template-columns:220px 1fr}
body.no-aside aside{display:none}
body.no-albums main{grid-template-columns:260px 1fr}
body.no-albums #albums-section{display:none}
body.no-aside.no-albums main{grid-template-columns:1fr}
aside,section{border-right:1px solid #2a2a2a;padding:8px;overflow:auto;max-height:calc(100vh - 150px)}
aside h2,section h2{font-size:12px;color:#999;margin:4px 0 8px}
.item{padding:3px 6px;border-radius:4px;cursor:pointer;display:flex;justify-content:space-between;gap:6px}
.item:hover{background:#242424}
.item.active{background:#333}
.item .done{color:#6f6}
.item .count{color:#888;font-size:11px;white-space:nowrap}
.chip{display:inline-block;margin:2px;padding:3px 8px;border:1px solid #3a3a3a;border-radius:12px;cursor:pointer}
.chip.active{background:#333;border-color:#666}
.chip .done{color:#6f6}
table{border-collapse:collapse;width:100%;background:#191919}
th,td{border-bottom:1px solid #2a2a2a;padding:3px 6px;text-align:left;vertical-align:top}
th{background:#222;position:sticky;top:0;font-size:11px;color:#999}
tr.flag td{background:#2a1f1f}
tr.like td{background:#1c241c}
td.num{color:#888;font-size:11px;white-space:nowrap}
td.path{font-family:monospace;font-size:10px;color:#777;max-width:280px;word-break:break-all}
button.play,button.vote{background:none;border:none;color:#ccc;cursor:pointer;font-size:14px;padding:0 2px}
button.play:hover,button.vote:hover{color:#fff}
form.editor{background:#222;padding:6px;display:flex;flex-direction:column;gap:4px}
.corrections{display:flex;flex-direction:column;gap:4px}
.correction,.actions{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
form.editor select,form.editor input{background:#111;color:#eee;border:1px solid #444;border-radius:4px;padding:3px 6px}
.fix{color:#f9a;font-size:11px}
footer{position:sticky;bottom:0;display:flex;gap:10px;align-items:center;
  padding:8px 12px;background:#1d1d1d;border-top:1px solid #333}
footer .title{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
footer button{background:#2b2b2b;color:#ddd;border:1px solid #444;border-radius:4px;padding:4px 8px;cursor:pointer}
.building{color:#fc6}
.muted{color:#777}
</style></head><body>
<header>
  <h1>全曲レビュー</h1>
  <span id="user" class="muted"></span>
  <span id="progress"></span>
  <span class="grow"></span>
  <button id="aside-toggle" title="アーティスト一覧をたたむ (Ctrl+B)">◧</button>
  <button id="albums-toggle" title="アルバム一覧をたたむ (Ctrl+Alt+B)">▤</button>
  <input id="search" placeholder="アーティストで絞り込み">
  <button id="refresh" title="タグを読み直す">再読込</button>
</header>
<main>
  <aside><h2>アーティスト <span id="artist-count" class="muted"></span></h2><div id="artists"></div></aside>
  <section id="albums-section"><h2 id="album-head">アルバム</h2><div id="albums" class="muted">アーティストを選んでください</div></section>
  <section><h2 id="track-head">曲</h2><div id="tracks"></div></section>
</main>
<footer>
  <button id="prev">◀</button><button id="toggle">▶</button><button id="next">▶</button>
  <span class="title" id="now">—</span>
  <audio id="audio" preload="none"></audio>
</footer>
<script>
const $ = (sel) => document.querySelector(sel);
const encPath = (p) => p.split('/').map(encodeURIComponent).join('/');
const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const FIELD_LABELS = {title:'曲名', artist:'アーティスト', album:'アルバム',
  albumartist:'アルバムアーティスト', composer:'作曲', tracknumber:'曲番',
  discnumber:'ディスク', genre:'ジャンル', other:'その他'};
const voteCorrections = (vote) => (vote && vote.corrections)
  || (vote && (vote.field || vote.value) ? [{field: vote.field, value: vote.value}] : []);
const correctionText = (vote) => voteCorrections(vote)
  .map(item => `${FIELD_LABELS[item.field] || item.field || 'その他'}→${item.value || '?'}`)
  .join(' / ');
let STATE = {user:'', total:0, checked:0, artists:[]};
let VIEW = {artist:null, album:null, albums:[], tracks:[]};
let PLAY = {list:[], index:-1};

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
function post(path, body) {
  return api(path, {method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify(body)});
}

async function loadState() {
  STATE = await api('api/state');
  $('#user').textContent = STATE.user ? `👤 ${STATE.user}` : '';
  renderHeader(); renderArtists();
}

function renderHeader() {
  $('#progress').textContent = `確認済み ${STATE.checked} / ${STATE.total} 曲`;
  $('#progress').className = STATE.building ? 'building' : '';
  if (STATE.building) $('#progress').textContent += '（タグ読み込み中…）';
}

function renderArtists() {
  const query = $('#search').value.trim().toLowerCase();
  const box = $('#artists'); box.textContent = '';
  const rows = STATE.artists.filter(a => !query || a.name.toLowerCase().includes(query));
  $('#artist-count').textContent = `${rows.length}/${STATE.artists.length}`;
  for (const artist of rows) {
    const div = document.createElement('div');
    div.className = 'item' + (VIEW.artist === artist.name ? ' active' : '');
    div.innerHTML = `<span>${artist.complete ? '<span class="done">✓ </span>' : ''}${esc(artist.name)}</span>`
      + `<span class="count">${artist.checked}/${artist.tracks}</span>`;
    div.onclick = () => openArtist(artist.name);
    box.appendChild(div);
  }
}

async function openArtist(name) {
  VIEW.artist = name; VIEW.album = null; VIEW.tracks = [];
  renderArtists();
  const data = await api('api/albums?artist=' + encodeURIComponent(name));
  VIEW.albums = data.albums;
  renderAlbums(); $('#tracks').textContent = ''; $('#track-head').textContent = '曲';
}

function renderAlbums() {
  const box = $('#albums'); box.textContent = ''; box.className = '';
  $('#album-head').textContent = VIEW.artist ? `${VIEW.artist} のアルバム` : 'アルバム';
  for (const album of VIEW.albums) {
    const chip = document.createElement('span');
    chip.className = 'chip' + (VIEW.album === album.name ? ' active' : '');
    chip.innerHTML = `${album.complete ? '<span class="done">✓ </span>' : ''}${esc(album.name)}`
      + ` <span class="count">${album.checked}/${album.tracks}</span>`;
    chip.onclick = () => openAlbum(album.name);
    box.appendChild(chip);
  }
}

async function openAlbum(album) {
  if (!album) return;
  VIEW.album = album;
  renderAlbums();
  const url = 'api/tracks?artist=' + encodeURIComponent(VIEW.artist)
            + '&album=' + encodeURIComponent(album);
  const data = await api(url);
  VIEW.tracks = data.tracks;
  PLAY.list = data.tracks;
  $('#track-head').textContent = `${album}（${data.tracks.length}曲）`;
  renderTracks();
}

function applyRowState(tr, track) {
  tr.className = track.checked ? (track.vote.vote === 'flag' ? 'flag' : 'like') : '';
  const hint = track.vote && track.vote.vote === 'flag'
    ? `<div class="fix">⚠ ${esc(correctionText(track.vote))}</div>` : '';
  tr.children[2].innerHTML = esc(track.title) + hint;
}

function trackRow(track, index) {
  const tr = document.createElement('tr');
  tr.innerHTML = `<td><button class="play" title="再生">▶</button></td>`
    + `<td class="num">${esc(track.disc || 1)}-${esc(track.track || '?')}</td>`
    + `<td></td><td>${esc(track.artist)}</td><td>${esc(track.composer)}</td>`
    + `<td><button class="vote" data-v="like" title="正しい">👍</button>`
    + `<button class="vote" data-v="flag" title="指摘">⚠</button></td>`;
  applyRowState(tr, track);
  tr.querySelector('.play').onclick = () => play(track.path, index);
  tr.querySelectorAll('.vote').forEach(button => {
    button.onclick = () => {
      if (button.dataset.v === 'like' && track.vote && track.vote.vote === 'like') {
        vote(track, '', {}, tr);
      } else if (button.dataset.v === 'flag') {
        toggleEditor(tr, track);
      } else {
        vote(track, 'like', {}, tr);
      }
    };
  });
  return tr;
}

function renderTracks() {
  const box = $('#tracks'); box.textContent = '';
  const table = document.createElement('table');
  table.innerHTML = '<thead><tr><th></th><th>#</th><th>曲名</th><th>アーティスト</th>'
    + '<th>作曲</th><th>投票</th></tr></thead>';
  const body = document.createElement('tbody');
  VIEW.tracks.forEach((track, index) => body.appendChild(trackRow(track, index)));
  table.appendChild(body);
  box.appendChild(table);
}

function editorRow(track) {
  const tr = document.createElement('tr');
  tr.className = 'editor';
  const cell = document.createElement('td');
  cell.colSpan = 6;
  const form = document.createElement('form');
  form.className = 'editor';
  const list = document.createElement('div');
  list.className = 'corrections';
  const addCorrection = (field, value) => {
    const row = document.createElement('div');
    row.className = 'correction';
    row.innerHTML = `<select name="field">`
      + Object.entries(FIELD_LABELS).map(([v, label]) =>
          `<option value="${v}"${field === v ? ' selected' : ''}>${label}</option>`).join('')
      + `</select><input name="value" placeholder="正しい値" value="${esc(value)}">`
      + `<button type="button" class="remove" title="この項目を外す">×</button>`;
    row.querySelector('.remove').onclick = () => row.remove();
    list.appendChild(row);
  };
  const existing = voteCorrections(track.vote);
  (existing.length ? existing : [{field: 'title', value: ''}])
    .forEach(item => addCorrection(item.field, item.value));
  const actions = document.createElement('div');
  actions.className = 'actions';
  actions.innerHTML = `<button type="button" class="add">＋項目を追加</button>`
    + `<input name="note" placeholder="メモ" size="24" value="${esc(track.vote && track.vote.note || '')}">`
    + `<button type="submit">保存</button><button type="button" class="cancel">閉じる</button>`;
  actions.querySelector('.add').onclick = () => addCorrection('', '');
  actions.querySelector('.cancel').onclick = () => tr.remove();
  form.appendChild(list);
  form.appendChild(actions);
  form.onsubmit = (event) => {
    event.preventDefault();
    const corrections = [...list.querySelectorAll('.correction')].map(row => ({
      field: row.querySelector('select').value,
      value: row.querySelector('input').value,
    })).filter(item => item.field || item.value);
    vote(track, 'flag', {corrections, note: actions.querySelector('[name=note]').value},
         tr.previousElementSibling);
  };
  cell.appendChild(form);
  tr.appendChild(cell);
  return tr;
}

function toggleEditor(tr, track) {
  const next = tr.nextElementSibling;
  if (next && next.classList.contains('editor')) { next.remove(); return; }
  tr.after(editorRow(track));
}

async function refreshCounts() {
  await loadState();
  if (VIEW.artist) {
    const data = await api('api/albums?artist=' + encodeURIComponent(VIEW.artist));
    VIEW.albums = data.albums;
    renderAlbums();
  }
}

async function vote(track, value, extra = {}, tr = null) {
  const result = await post('api/vote', {path: track.path, vote: value, ...extra});
  track.vote = result.vote; track.checked = !!result.vote;
  if (tr) {
    applyRowState(tr, track);
    const next = tr.nextElementSibling;
    if (next && next.classList.contains('editor')) next.remove();
  }
  await refreshCounts();
}

function play(path, index) {
  PLAY.index = index;
  const audio = $('#audio');
  audio.src = 'media/' + encPath(path);
  audio.play().catch(() => {});
  $('#now').textContent = VIEW.tracks[index] ? VIEW.tracks[index].title : '';
  $('#toggle').textContent = '❚❚';
}

function step(delta) {
  if (!PLAY.list.length) return;
  const next = PLAY.index + delta;
  if (next < 0 || next >= PLAY.list.length) return;
  play(PLAY.list[next].path, next);
}

$('#toggle').onclick = () => {
  const audio = $('#audio');
  if (audio.paused) { audio.play(); $('#toggle').textContent = '❚❚'; }
  else { audio.pause(); $('#toggle').textContent = '▶'; }
};
$('#prev').onclick = () => step(-1);
$('#next').onclick = () => step(1);
$('#audio').onended = () => step(1);
$('#search').oninput = renderArtists;
$('#refresh').onclick = async () => { await post('api/refresh', {}); await loadState(); };
function setAside(collapsed) {
  document.body.classList.toggle('no-aside', collapsed);
  $('#aside-toggle').textContent = collapsed ? '◨' : '◧';
  $('#aside-toggle').title = collapsed ? 'アーティスト一覧を開く (Ctrl+B)' : 'アーティスト一覧をたたむ (Ctrl+B)';
  try { localStorage.setItem('review-aside', collapsed ? '1' : ''); } catch (error) {}
}
$('#aside-toggle').onclick = () => setAside(!document.body.classList.contains('no-aside'));
function setAlbums(collapsed) {
  document.body.classList.toggle('no-albums', collapsed);
  $('#albums-toggle').textContent = collapsed ? '▥' : '▤';
  $('#albums-toggle').title = collapsed ? 'アルバム一覧を開く (Ctrl+Alt+B)' : 'アルバム一覧をたたむ (Ctrl+Alt+B)';
  try { localStorage.setItem('review-albums', collapsed ? '1' : ''); } catch (error) {}
}
$('#albums-toggle').onclick = () => setAlbums(!document.body.classList.contains('no-albums'));
document.addEventListener('keydown', (event) => {
  const key = (event.key || '').toLowerCase();
  if ((event.ctrlKey || event.metaKey) && event.altKey && key === 'b') {
    event.preventDefault();
    setAlbums(!document.body.classList.contains('no-albums'));
  } else if ((event.ctrlKey || event.metaKey) && !event.altKey && key === 'b') {
    event.preventDefault();
    setAside(!document.body.classList.contains('no-aside'));
  }
});
try { setAside(localStorage.getItem('review-aside') === '1'); } catch (error) { setAside(false); }
try { setAlbums(localStorage.getItem('review-albums') === '1'); } catch (error) { setAlbums(false); }
loadState();
setInterval(async () => {
  if (!STATE.building) return;
  const before = STATE.building;
  await loadState();
  if (before && !STATE.building && VIEW.artist) {
    const album = VIEW.album;
    await refreshCounts();
    if (album) await openAlbum(album);
  }
}, 4000);
</script></body></html>'''


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    load_index()
    load_events()
    threading.Thread(target=build_index, daemon=True).start()
    server = ThreadingHTTPServer(('0.0.0.0', PORT), ReviewHandler)
    server.daemon_threads = True
    print(f'music-review listening on {PORT} ({MUSIC})', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
