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
# 管理画面の言語一覧に日本語が無い（upstream の g.languages 漏れ）。ポータルを
# 一度開いたら管理画面も日本語になるよう、共通ドメインへ Cookie を置く。
LANG_COOKIE = os.environ.get(
    'URBACKUP_LANG_COOKIE',
    'urbackup_lang=ja; Domain=apextox.dpdns.org; Path=/; Max-Age=31536000; Secure; SameSite=Lax')
ANDROID_BACKUP_ROOT = Path(os.environ.get('ANDROID_BACKUP_ROOT', '/data/android-backups'))
STATIC_FILE = Path(__file__).resolve().parent / 'portal-backup.js'
CACHE_SECONDS = int(os.environ.get('CACHE_SECONDS', '30'))
PROGRESS_SECONDS = int(os.environ.get('PROGRESS_SECONDS', '5'))
HTTP_TIMEOUT = 10
MAX_CHUNK = 32 * 1024 * 1024

DEVICE_RE = re.compile(r'^[A-Za-z0-9._-]{1,64}$')
REL_COMPONENT_RE = re.compile(r'^[^/\\]{1,255}$')
BACKUP_KINDS = ('incr_file', 'full_file', 'incr_image', 'full_image')
PROGRESS_ACTIONS = {
    1: 'ファイル（増分）', 2: 'ファイル（フル）', 3: 'イメージ（増分）', 4: 'イメージ（フル）',
    5: 'ファイル（再開）', 6: 'ファイル（再開）', 8: '復元（ファイル）', 9: '復元（イメージ）',
    10: '開始中', 11: '初期化中',
}
LOCK = threading.Lock()

# 端末ごとの手順。保存先やアプリの名前が変わったらここを直す。
DEVICES = [
    {
        'name': 'Windows PC',
        'method': 'UrBackup（LAN・自動）',
        'steps': [
            '初回だけ: 下の「Windowsクライアントをダウンロード」からインストーラーを実行',
            '自動バックアップはオフ。上の表の「ファイル」「イメージ」を押した時だけ走る',
            '復元は UrBackup 管理画面の「Backups」から（イメージ復元は復元メディア）',
        ],
        'links': [
            ('Windowsクライアントをダウンロード', '/download/urbackup-client-windows'),
            ('UrBackup 管理画面', URBACKUP_WEB_URL),
        ],
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
_progress_cache = {'at': 0.0, 'value': None}


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


def fetch_progress():
    """Return the UrBackup running-backup dict, or None when unreachable."""
    now = time.monotonic()
    if _progress_cache['value'] is not None and now - _progress_cache['at'] < PROGRESS_SECONDS:
        return _progress_cache['value']
    try:
        api = Api(URBACKUP_API, URBACKUP_USER, read_password())
        progress = api.call('progress') if api.login() else None
    except (OSError, ValueError, urllib.error.URLError):
        progress = None
    _progress_cache['value'] = progress
    _progress_cache['at'] = now
    return progress


def client_download_params(session):
    """Parameters for the server's Windows client installer download."""
    return {'a': 'download_client', 'clientid': '-1', 'os': 'windows', 'ses': session}


def open_client_download():
    """Log in and open the UrBackup Windows client installer stream."""
    api = Api(URBACKUP_API, URBACKUP_USER, read_password())
    if not api.login():
        raise RuntimeError('the UrBackup login failed')
    url = URBACKUP_API + '?' + urllib.parse.urlencode(client_download_params(api.session))
    return urllib.request.urlopen(
        urllib.request.Request(url, method='GET'), timeout=HTTP_TIMEOUT)


def start_backup_params(client, kind):
    """Parameters for the server's manual backup action."""
    if kind not in BACKUP_KINDS:
        raise ValueError('invalid backup type')
    return {'start_type': kind, 'start_client': str(client)}


def start_backup(client, kind):
    """Ask the UrBackup server to start one manual backup for a client."""
    api = Api(URBACKUP_API, URBACKUP_USER, read_password())
    if not api.login():
        raise RuntimeError('the UrBackup login failed')
    return api.call('start_backup', start_backup_params(client, kind))


def cell(value):
    value = '' if value in (None, '-', 0) else value
    return html.escape(str(value)) if value else '未取得'


def backup_buttons(client_id):
    if not isinstance(client_id, int):
        return '未取得'
    return ''.join(
        f'<button type="button" class="backup" data-client="{client_id}" '
        f'data-kind="{kind}">{label}</button>'
        for kind, label in (('incr_file', 'ファイル'), ('incr_image', 'イメージ')))


def render_status(status):
    if status is None:
        return '<p class="bad">UrBackup に接続できません。時間をおいて再読み込みしてください。</p>'
    clients = status.get('status') or []
    if not clients:
        return (
            '<p class="muted">UrBackup にクライアントがまだ登録されていません。'
            '下の「Windows PC」からクライアントを入れてください。</p>')
    rows = []
    for client in clients:
        online = 'オンライン' if client.get('online') else 'オフライン'
        rows.append(
            '<tr>'
            f'<td>{html.escape(str(client.get("name", "?")))}</td>'
            f'<td>{online}</td>'
            f'<td>{cell(client.get("lastbackup"))}</td>'
            f'<td>{cell(client.get("lastbackup_image"))}</td>'
            f'<td>{backup_buttons(client.get("id"))}</td>'
            '</tr>')
    return (
        '<table><thead><tr><th>端末</th><th>状態</th><th>最終ファイル</th>'
        '<th>最終イメージ</th><th>手動バックアップ（自動はオフ）</th></tr></thead>'
        '<tbody>' + ''.join(rows) + '</tbody></table>'
        '<p id="backup-message" class="muted"></p>')


def render_progress(progress):
    entries = (progress or {}).get('progress') or []
    if not entries:
        return '<p class="muted">いま走っているバックアップはありません。</p>'
    blocks = []
    for entry in entries:
        done = entry.get('done_bytes') or 0
        total = entry.get('total_bytes') or 0
        pcdone = entry.get('pcdone') or 0
        queue = entry.get('queue') or 0
        speed = (entry.get('speed_bpms') or 0) * 1000 / 1024 ** 2
        action = PROGRESS_ACTIONS.get(entry.get('action'), 'バックアップ')
        name = html.escape(str(entry.get('name', '?')))
        if total <= 0:
            # ファイル一覧の作成中。転送量がまだ分からない。
            detail = f'{action}・準備中（ファイル一覧を作成中）'
            bar = '<div class="bar"><div class="bar-fill processing"></div></div>'
        elif pcdone >= 100 and queue > 0:
            # 転送は終わり、サーバーが索引とハッシュを確定している段階。
            detail = (f'{action} {done / 1024 ** 3:.1f} GiB・転送完了、'
                      f'後処理中（残り約{queue:,}件）')
            bar = '<div class="bar"><div class="bar-fill processing"></div></div>'
        else:
            percent = min(100.0, done / total * 100) if total else 0.0
            eta = entry.get('eta_ms') or -1
            if eta and eta > 0:
                minutes = eta / 60000
                eta_text = f'残り約{minutes / 60:.1f}時間' if minutes >= 60 else f'残り約{minutes:.0f}分'
            else:
                eta_text = '残り時間は計算中'
            detail = (f'{action} {done / 1024 ** 3:.1f} / {total / 1024 ** 3:.1f} GiB'
                      f'（{percent:.1f}%）・{speed:.1f} MiB/s・{eta_text}')
            bar = f'<div class="bar"><div class="bar-fill" style="width:{percent:.1f}%"></div></div>'
        blocks.append(
            '<div class="progress">'
            f'<div class="progress-head"><strong>{name}</strong> {detail}</div>'
            f'{bar}'
            '</div>')
    return ''.join(blocks)


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


def render_page(status, progress=None):
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
  button.backup {{ padding: 0.2rem 0.6rem; font-size: 0.9rem; margin-right: 0.3rem; }}
  button:disabled {{ opacity: 0.5; cursor: default; }}
  .progress {{ margin: 0.6rem 0; }}
  .progress-head {{ font-size: 0.9rem; margin-bottom: 0.2rem; }}
  .bar {{ background: #8883; border-radius: 999px; height: 0.9rem; overflow: hidden; }}
  .bar-fill {{ background: #2563eb; height: 100%; }}
  .bar-fill.processing {{ width: 100%;
    background: repeating-linear-gradient(45deg, #2563eb 0 8px, #60a5fa 8px 16px);
    animation: stripes 0.8s linear infinite; }}
  @keyframes stripes {{ from {{ background-position: 0 0; }}
    to {{ background-position: 32px 0; }} }}
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
<h3>走っているバックアップ</h3>
{render_progress(progress)}
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
<h2>復元のやり方</h2>
<section class="card">
  <h3>ファイル（書類・写真など）</h3>
  <ol>
    <li>「UrBackup 管理画面」を開く</li>
    <li>「Backups」で端末と世代（日時）を選び、必要なファイルをダウンロードする</li>
  </ol>
</section>
<section class="card">
  <h3>システムイメージ（Windowsが起動しないとき）</h3>
  <ol>
    <li>UrBackup の復元メディア（USB/CD）でPCを起動する</li>
    <li>サーバー 192.168.10.101 に接続し、戻す世代を選ぶ</li>
  </ol>
</section>
<section class="card">
  <h3>マルウェア感染が疑われるとき</h3>
  <ol>
    <li>戻すのは<strong>感染前の世代</strong>。感染後に取った世代は戻さない</li>
    <li>データだけ戻した場合も、戻した後にウイルススキャンしてから使う</li>
  </ol>
</section>
<script>
document.addEventListener('click', function (event) {{
  var button = event.target.closest('button.backup');
  if (!button) return;
  var message = document.getElementById('backup-message');
  button.disabled = true;
  fetch('/api/backup/start', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{client: Number(button.dataset.client),
                           kind: button.dataset.kind}})
  }}).then(function (response) {{ return response.json(); }}).then(function (data) {{
    message.textContent = data.ok
      ? 'バックアップを開始しました。上の「走っているバックアップ」に進捗が出ます（再読み込みで更新）。'
      : '開始できませんでした（' + (data.error || '不明なエラー') + '）';
  }}).catch(function (error) {{
    message.textContent = '開始できませんでした（' + error + '）';
  }}).finally(function () {{ button.disabled = false; }});
}});
</script>
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
        elif path == '/download/urbackup-client-windows':
            self.download_client_windows()
        elif path in ('/', '/index.html'):
            page = render_page(fetch_status(), fetch_progress()).encode('utf-8')
            self.respond(page, 'text/html; charset=utf-8',
                         extra_headers=[('Set-Cookie', LANG_COOKIE)])
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
            elif path == '/api/backup/start':
                self.handle_backup_start()
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

    def handle_backup_start(self):
        payload = self.read_json_body()
        client = int(payload['client'])
        if client < 0:
            raise ValueError('invalid client')
        try:
            result = start_backup(client, str(payload['kind']))
        except (OSError, urllib.error.URLError, RuntimeError) as error:
            self.json({'ok': False, 'error': str(error)}, status=502)
            return
        entries = result.get('result', []) if isinstance(result, dict) else []
        started = [entry for entry in entries
                   if isinstance(entry, dict) and entry.get('start_ok')]
        if not started:
            self.json({'ok': False, 'error': 'UrBackup が開始を受け付けませんでした',
                       'result': entries}, status=502)
            return
        self.json({'ok': True, 'result': entries})

    def read_json_body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length <= 0 or length > 1024 * 1024:
            raise ValueError('invalid body size')
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def download_client_windows(self):
        """Stream the server's Windows client installer (needs the admin session)."""
        try:
            upstream = open_client_download()
        except (OSError, ValueError, urllib.error.URLError, RuntimeError):
            self.json({'error': 'UrBackup からクライアントを取得できませんでした'}, status=502)
            return
        with upstream:
            first = upstream.read(64 * 1024)
            # ログインに失敗すると本文が ERROR テキストになる。実行ファイルだけ通す。
            if not first.startswith(b'MZ'):
                message = (first + upstream.read(4096)).decode('utf-8', 'ignore')[:200]
                self.json({'error': f'UrBackup did not return an installer: {message}'},
                          status=502)
                return
            length = upstream.headers.get('Content-Length')
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Disposition',
                             'attachment; filename="UrBackupClientSetup.exe"')
            if length:
                self.send_header('Content-Length', str(length))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            try:
                self.wfile.write(first)
                while True:
                    chunk = upstream.read(256 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_HEAD(self):
        self.respond(b'', 'text/plain; charset=utf-8', head=True)

    def json(self, payload, status=200):
        self.respond(json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                     'application/json; charset=utf-8', status=status)

    def respond(self, body, content_type, status=200, head=False, extra_headers=()):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for name, value in extra_headers:
            self.send_header(name, value)
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
