#!/usr/bin/env python3
"""Read-only backup portal for the client backup unit on media-01.

The page shows the UrBackup clients' last backups, the Android backup button
(WebUSB/ADB from the browser, see portal-web/) and the last Android backups.
It reads the UrBackup web API with the admin password mounted at /run/secrets
and stores Android uploads under ANDROID_BACKUP_ROOT. The only entry point is
the Forward Auth protected https://backup.apextox.dpdns.org/.
"""
import binascii
import hashlib
import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.environ.get('PORT', '8080'))
BIND_ADDRESS = os.environ.get('BIND_ADDRESS', '0.0.0.0')
URBACKUP_API = os.environ.get('URBACKUP_API', 'http://urbackup:55414/x')
URBACKUP_USER = os.environ.get('URBACKUP_ADMIN_USER', 'admin')
URBACKUP_PASSWORD_FILE = os.environ.get(
    'URBACKUP_ADMIN_PASSWORD_FILE', '/run/secrets/urbackup_admin_password')
URBACKUP_WEB_URL = os.environ.get('URBACKUP_WEB_URL', 'https://urbackup.apextox.dpdns.org/')
SMART_SWITCH_URL = os.environ.get(
    'SMART_SWITCH_URL', 'https://www.samsung.com/jp/apps/smart-switch/')
ANDROID_BACKUP_ROOT = Path(os.environ.get('ANDROID_BACKUP_ROOT', '/data/android-backups'))
STATIC_FILE = Path(__file__).resolve().parent / 'portal-backup.js'
CACHE_SECONDS = int(os.environ.get('CACHE_SECONDS', '30'))
HTTP_TIMEOUT = 10
MAX_CHUNK = 32 * 1024 * 1024

DEVICE_RE = re.compile(r'^[A-Za-z0-9._-]{1,64}$')
REL_COMPONENT_RE = re.compile(r'^[^/\\]{1,255}$')
LOCK = threading.Lock()

# 端末ごとの手順。保存先やアプリの名前が変わったらここを直す。
DEVICES = [
    {
        'name': 'Windows PC',
        'method': 'UrBackup（LAN・自動）',
        'steps': [
            '初回だけ: UrBackup 管理画面の「Status」からクライアント（MSI）を入れる',
            '入れればファイルは毎時、システムイメージは定期で自動バックアップ',
            '復元は UrBackup 管理画面の「Backups」から（イメージ復元は復元メディア）',
        ],
        'links': [('UrBackup 管理画面', URBACKUP_WEB_URL)],
    },
    {
        'name': 'Galaxy（家族の全端末）',
        'method': 'USBでこのページから（WebUSB）',
        'steps': [
            '端末の「開発者向けオプション」→「USBデバッグ」をON（初回だけ）',
            'USBでPCへつなぎ、端末の「USBデバッグを許可」を押す（初回だけ）',
            '下のボタンを押して端末を選ぶ。写真・書類・APKをサーバーへ保存する',
        ],
        'links': [('Smart Switch（機種変更の引き継ぎ）', SMART_SWITCH_URL)],
    },
]

_cache = {'at': 0.0, 'value': None}


class Api:
    """Minimal UrBackup web API client (the /x JSON endpoints)."""

    def __init__(self, base, username, password):
        self.base = base.rstrip('/')
        self.username = username
        self.password = password
        self.session = ''
        self.logged_in = False

    def call(self, action, params=None):
        params = dict(params or {})
        if self.session:
            params['ses'] = self.session
        url = self.base + '?' + urllib.parse.urlencode({'a': action})
        request = urllib.request.Request(
            url, data=urllib.parse.urlencode(params).encode(), method='POST')
        request.add_header('Accept', 'application/json')
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            body = response.read().decode('utf-8', 'ignore')
        return json.loads(body)

    def login(self):
        salt = self.call('salt', {'username': self.username})
        if not isinstance(salt, dict) or 'ses' not in salt:
            return False
        self.session = salt['ses']
        digest = hashlib.md5((salt['salt'] + self.password).encode()).digest()
        password = binascii.hexlify(digest).decode()
        rounds = int(salt.get('pbkdf2_rounds', 0) or 0)
        if rounds > 0:
            password = binascii.hexlify(hashlib.pbkdf2_hmac(
                'sha256', digest, salt['salt'].encode(), rounds)).decode()
        password = hashlib.md5((salt['rnd'] + password).encode()).hexdigest()
        result = self.call('login', {'username': self.username, 'password': password})
        self.logged_in = bool(result) and bool(result.get('success'))
        return self.logged_in


def read_password():
    return Path(URBACKUP_PASSWORD_FILE).read_text().strip()


def fetch_status():
    """Return the UrBackup status dict, or None when the server is unreachable."""
    now = time.monotonic()
    if _cache['value'] is not None and now - _cache['at'] < CACHE_SECONDS:
        return _cache['value']
    try:
        api = Api(URBACKUP_API, URBACKUP_USER, read_password())
        status = api.call('status') if api.login() else None
    except (OSError, ValueError, urllib.error.URLError):
        status = None
    _cache['value'] = status
    _cache['at'] = now
    return status


def cell(value):
    value = '' if value in (None, '-', 0) else value
    return html.escape(str(value)) if value else '未取得'


def render_status(status):
    if status is None:
        return '<p class="bad">UrBackup に接続できません。時間をおいて再読み込みしてください。</p>'
    clients = status.get('status') or []
    if not clients:
        return (
            '<p class="muted">UrBackup にクライアントがまだ登録されていません。'
            f'<a href="{html.escape(URBACKUP_WEB_URL)}">管理画面</a>の「Status」から'
            ' Windows クライアントを入れてください。</p>')
    rows = []
    for client in clients:
        online = 'オンライン' if client.get('online') else 'オフライン'
        rows.append(
            '<tr>'
            f'<td>{html.escape(str(client.get("name", "?")))}</td>'
            f'<td>{online}</td>'
            f'<td>{cell(client.get("lastbackup"))}</td>'
            f'<td>{cell(client.get("lastbackup_image"))}</td>'
            '</tr>')
    return (
        '<table><thead><tr><th>端末</th><th>状態</th><th>最終ファイル</th>'
        '<th>最終イメージ</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>')


def android_manifests():
    """Return [(device, manifest dict)] for every Android backup on disk."""
    found = []
    if ANDROID_BACKUP_ROOT.is_dir():
        for path in sorted(ANDROID_BACKUP_ROOT.glob('*/manifest.json')):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            found.append((path.parent.name, data))
    found.sort(key=lambda item: str(item[1].get('updated', '')), reverse=True)
    return found


def render_android_status():
    runs = android_manifests()
    if not runs:
        return '<p class="muted">Android のバックアップはまだありません。上のボタンから始めてください。</p>'
    rows = []
    for device, data in runs:
        size = data.get('bytes', 0)
        if isinstance(size, (int, float)):
            size_text = f'{size / 1024 / 1024 / 1024:.2f} GiB' if size >= 1024 ** 3 \
                else f'{size / 1024 / 1024:.1f} MiB'
        else:
            size_text = str(size)
        rows.append(
            '<tr>'
            f'<td>{html.escape(str(data.get("model") or device))}</td>'
            f'<td>{html.escape(str(data.get("updated", "?")))}</td>'
            f'<td>{html.escape(str(data.get("files", "?")))}</td>'
            f'<td>{html.escape(size_text)}</td>'
            '</tr>')
    return (
        '<table><thead><tr><th>端末</th><th>最終</th><th>ファイル</th><th>サイズ</th>'
        '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table>')


def render_page(status):
    cards = []
    for device in DEVICES:
        steps = ''.join(f'<li>{html.escape(step)}</li>' for step in device['steps'])
        links = ' '.join(
            f'<a class="button" href="{html.escape(url)}">{html.escape(label)}</a>'
            for label, url in device['links'])
        cards.append(
            '<section class="card">'
            f'<h3>{html.escape(device["name"])}</h3>'
            f'<p class="method">{html.escape(device["method"])}</p>'
            f'<ol>{steps}</ol>'
            f'<p>{links}</p>'
            '</section>')
    return f'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>バックアップポータル</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, sans-serif; margin: 0 auto; max-width: 900px;
         padding: 1.5rem; line-height: 1.6; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
  h2 {{ font-size: 1.1rem; margin-top: 2rem; border-bottom: 1px solid #8884;
        padding-bottom: 0.25rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #8884; padding: 0.4rem 0.6rem; text-align: left; }}
  .card {{ border: 1px solid #8884; border-radius: 8px; padding: 0.8rem 1rem;
           margin: 0.8rem 0; }}
  .card h3 {{ margin: 0; font-size: 1rem; }}
  .method {{ margin: 0.2rem 0 0.4rem; color: #6b7280; font-size: 0.9rem; }}
  .muted {{ color: #6b7280; }}
  .bad {{ color: #b91c1c; }}
  .ok {{ color: #15803d; }}
  .button, button {{ display: inline-block; border: 1px solid #8884; border-radius: 6px;
             padding: 0.4rem 0.9rem; text-decoration: none; font-size: 1rem;
             background: #2563eb; color: #fff; cursor: pointer; }}
  button:disabled {{ opacity: 0.5; cursor: default; }}
  .targets label {{ margin-right: 1rem; }}
  pre.log {{ background: #0002; border-radius: 6px; padding: 0.6rem; max-height: 14rem;
             overflow: auto; font-size: 0.8rem; white-space: pre-wrap; }}
</style>
</head>
<body>
<h1>バックアップポータル</h1>
<p class="muted">media-01 の UrBackup と各端末のバックアップ入口です。SSO の内側にあります。</p>
<h2>いまの状態（UrBackup）</h2>
{render_status(status)}
<h2>Android をバックアップ（USB）</h2>
<section class="card">
  <p>スマホをこのPCにUSBでつないでボタンを押すだけです（Vivaldi・Chrome・Edge などのChromium系）。ファイルは
     media-01 のHDDへ保存されます。</p>
  <p class="targets">
    <label><input type="checkbox" class="android-target" value="photos" checked> 写真・動画</label>
    <label><input type="checkbox" class="android-target" value="docs" checked> ダウンロード・書類</label>
    <label><input type="checkbox" class="android-target" value="apps"> アプリ（APK）</label>
  </p>
  <p><button id="android-connect" type="button">スマホをバックアップ</button></p>
  <p id="android-status" class="muted">待機中</p>
  <p id="android-summary" class="muted"></p>
  <pre id="android-progress" class="log"></pre>
  <p class="muted">アプリの内部データ（ログイン状態・ゲームセーブ）は Android の制限で
     非rootでは取得できません。機種変更時の引き継ぎは Smart Switch を使ってください。</p>
</section>
<h3>Android の最終バックアップ</h3>
{render_android_status()}
<h2>端末ごとのやり方</h2>
{''.join(cards)}
<script type="module" src="/static/portal-backup.js"></script>
</body>
</html>
'''


def safe_device(value):
    if not value or not DEVICE_RE.match(value):
        raise ValueError('invalid device')
    return value


def safe_rel(value):
    if not value or value.startswith('/') or '\\' in value:
        raise ValueError('invalid path')
    parts = value.split('/')
    if len(parts) > 32 or not all(REL_COMPONENT_RE.match(part) for part in parts):
        raise ValueError('invalid path')
    if any(part in ('.', '..') for part in parts):
        raise ValueError('invalid path')
    return parts


def device_root(device):
    return ANDROID_BACKUP_ROOT / safe_device(device)


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def android_index(device):
    return read_json(device_root(device) / 'index.json', {})


def android_chunk(device, relative, offset, body):
    parts = safe_rel(relative)
    target = device_root(device) / 'files'
    for part in parts:
        target = target / part
    target.parent.mkdir(parents=True, exist_ok=True)
    with LOCK:
        current = target.stat().st_size if target.exists() else 0
        if offset == 0 and current:
            target.unlink()
            current = 0
        if offset != current:
            raise ValueError(f'offset mismatch ({offset} != {current})')
        with target.open('ab') as handle:
            handle.write(body)
    return target.stat().st_size


def android_finish(device, relative, size, mtime):
    parts = safe_rel(relative)
    target = device_root(device) / 'files'
    for part in parts:
        target = target / part
    if size == 0 and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    if not target.exists() or target.stat().st_size != size:
        raise ValueError('file size does not match the uploaded data')
    with LOCK:
        with (device_root(device) / 'pending.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps({'path': relative, 'size': size, 'mtime': mtime}) + '\n')


def android_manifest(device, payload):
    root = device_root(device)
    root.mkdir(parents=True, exist_ok=True)
    with LOCK:
        index = read_json(root / 'index.json', {})
        pending = root / 'pending.jsonl'
        if pending.exists():
            for line in pending.read_text(encoding='utf-8').splitlines():
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                index[entry['path']] = {'size': entry['size'], 'mtime': entry['mtime']}
            pending.unlink()
        temporary = root / 'index.json.tmp'
        temporary.write_text(json.dumps(index, ensure_ascii=False), encoding='utf-8')
        temporary.replace(root / 'index.json')
        manifest = {
            'updated': time.strftime('%Y-%m-%d %H:%M', time.localtime()),
            'model': str(payload.get('model', ''))[:120],
            'serial': str(payload.get('serial', ''))[:120],
            'files': int(payload.get('files', 0)),
            'bytes': int(payload.get('bytes', 0)),
            'skipped': int(payload.get('skipped', 0)),
        }
        (root / 'manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        return manifest


class Handler(BaseHTTPRequestHandler):
    server_version = 'backup-portal/1.0'

    def route(self):
        parsed = urllib.parse.urlparse(self.path)
        return parsed.path, urllib.parse.parse_qs(parsed.query)

    def do_GET(self):
        path, query = self.route()
        if path == '/healthz':
            self.json({'status': 'ok', 'urbackup': fetch_status() is not None})
        elif path == '/static/portal-backup.js':
            if not STATIC_FILE.is_file():
                self.json({'error': 'the portal bundle is missing'}, status=500)
                return
            self.respond(STATIC_FILE.read_bytes(), 'text/javascript; charset=utf-8')
        elif path == '/api/android/index':
            try:
                device = safe_device(query.get('device', [''])[0])
            except ValueError as error:
                self.json({'error': str(error)}, status=400)
                return
            self.json(android_index(device))
        elif path in ('/', '/index.html'):
            self.respond(render_page(fetch_status()).encode('utf-8'), 'text/html; charset=utf-8')
        else:
            self.respond(b'not found\n', 'text/plain; charset=utf-8', status=404)

    def do_POST(self):
        path, query = self.route()
        try:
            if path == '/api/android/chunk':
                self.handle_chunk(query)
            elif path == '/api/android/finish':
                payload = self.read_json_body()
                android_finish(payload['device'], payload['path'],
                               int(payload['size']), int(payload['mtime']))
                self.json({'ok': True})
            elif path == '/api/android/manifest':
                payload = self.read_json_body()
                device = safe_device(str(payload.get('device', '')))
                self.json(android_manifest(device, payload))
            else:
                self.respond(b'not found\n', 'text/plain; charset=utf-8', status=404)
        except (KeyError, ValueError) as error:
            self.json({'error': str(error)}, status=400)
        except OSError as error:
            self.json({'error': f'storage error: {error}'}, status=500)

    def handle_chunk(self, query):
        device = safe_device(query.get('device', [''])[0])
        relative = query.get('path', [''])[0]
        offset = int(query.get('offset', ['0'])[0])
        length = int(self.headers.get('Content-Length', '0'))
        if length <= 0 or length > MAX_CHUNK:
            raise ValueError('invalid chunk size')
        body = self.rfile.read(length)
        while len(body) < length:
            more = self.rfile.read(length - len(body))
            if not more:
                raise ValueError('short read')
            body += more
        size = android_chunk(device, relative, offset, body)
        self.json({'size': size})

    def read_json_body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length <= 0 or length > 1024 * 1024:
            raise ValueError('invalid body size')
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def do_HEAD(self):
        self.respond(b'', 'text/plain; charset=utf-8', head=True)

    def json(self, payload, status=200):
        self.respond(json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                     'application/json; charset=utf-8', status=status)

    def respond(self, body, content_type, status=200, head=False):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f'{self.address_string()} {fmt % args}', flush=True)


def main():
    server = ThreadingHTTPServer((BIND_ADDRESS, PORT), Handler)
    print(f'backup portal listening on {BIND_ADDRESS}:{PORT}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
