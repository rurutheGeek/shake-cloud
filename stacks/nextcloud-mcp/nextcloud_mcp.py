#!/usr/bin/env python3
"""Nextcloud MCP server for AI agents (media-01). Standard library only.

AIエージェント（opencode等）に、Nextcloudのファイル操作・MP3タグ編集・
圧縮/解凍をMCPツールとして渡す。呼び出し元の `Authorization` ヘッダーを
そのままNextcloudへ転送するので、権限はNextcloudのACL・共有・クォータに従う。
サーバーは資格情報を保存しない。

MCPはStreamable HTTP（`POST /mcp`、JSON-RPCを単一JSONで返す、セッションなし）。
`initialize`・`ping`・`tools/list`・`tools/call` だけを実装する。

Configuration (systemd EnvironmentFile):
  NEXTCLOUD_MCP_PORT              default 5811
  NEXTCLOUD_MCP_BIND              default 127.0.0.1
  NEXTCLOUD_MCP_BASE_URL          default http://127.0.0.1:8080
  NEXTCLOUD_MCP_TAG_API_URL       default http://127.0.0.1:5810
  NEXTCLOUD_MCP_TAG_API_TOKEN     shared secret (SOPS)
  NEXTCLOUD_MCP_TMP               default /var/tmp/nextcloud-mcp
  NEXTCLOUD_MCP_READ_ONLY         default 0 (1で書き込みツールを隠す)
  NEXTCLOUD_MCP_MAX_READ_BYTES    default 256 KiB
  NEXTCLOUD_MCP_MAX_WRITE_BYTES   default 8 MiB
  NEXTCLOUD_MCP_MAX_BODY_BYTES    default 32 MiB
  NEXTCLOUD_MCP_MAX_EXTRACT_FILES default 10000
  NEXTCLOUD_MCP_MAX_EXTRACT_BYTES default 4 GiB
  NEXTCLOUD_MCP_MAX_ZIP_BYTES     default 4 GiB
  NEXTCLOUD_MCP_TIMEOUT           default 120 (秒)
  NEXTCLOUD_MCP_ARCHIVE_TIMEOUT   default 1800 (秒)
"""
import base64
import json
import logging
import os
import posixpath
import shutil
import stat
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = '0.1.0'
SERVER_NAME = 'nextcloud'
USER_AGENT = ('shakecloud-nextcloud-mcp/' + VERSION +
              ' (+https://github.com/rurutheGeek/shake-cloud)')
DAV_NS = 'DAV:'
OC_NS = 'http://owncloud.org/ns'
SUPPORTED_PROTOCOLS = ('2025-06-18', '2025-03-26', '2024-11-05')
DEFAULT_PROTOCOL = SUPPORTED_PROTOCOLS[0]

# 変換原本。読み取りは許すが、書き込み系ツールはここを拒否する。
WRITE_DENY_PREFIXES = ('/music/Converted',)

# 読み取りツールがテキストとして返す拡張子（それ以外はbase64）。
TEXT_SUFFIXES = {
    '.txt', '.md', '.markdown', '.csv', '.tsv', '.json', '.jsonl', '.yaml', '.yml',
    '.toml', '.ini', '.cfg', '.conf', '.log', '.xml', '.html', '.htm', '.css',
    '.js', '.ts', '.py', '.sh', '.service', '.env', '.srt', '.vtt', '.lrc', '.nfo',
}

log = logging.getLogger('nextcloud-mcp')

PROPFIND_BODY = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns"'
    ' xmlns:nc="http://nextcloud.org/ns">'
    '<d:prop>'
    '<d:displayname/><d:getcontentlength/><d:getcontenttype/><d:getetag/>'
    '<d:getlastmodified/><d:resourcetype/><oc:fileid/><oc:permissions/><oc:size/>'
    '</d:prop></d:propfind>'
).encode('utf-8')

INSTRUCTIONS = (
    'Nextcloudのファイルを、接続したユーザー本人の権限で読み書きするツール。'
    'すべての操作はNextcloudのACL・共有・クォータに従う。'
    'MP3タグはnextcloud_read_music_tags/nextcloud_write_music_tags（/music配下の.mp3のみ）を使い、'
    'バックアップとMusicBrainz候補つきで更新される。'
    '圧縮・解凍はnextcloud_create_zip/nextcloud_extract_archive。'
    '改名・移動はnextcloud_move_file（Nextcloudのfileidと共有リンクが維持される）。'
    '削除はゴミ箱へ入る。パスはnextcloud_list_files等が返した値（先頭/の絶対パス）をそのまま使う。'
)


class ToolError(Exception):
    """利用者に見せてよいエラー。"""


class NextcloudError(ToolError):
    """Nextcloudが返したHTTPエラー。"""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Config:
    def __init__(self, env):
        self.port = int(env.get('NEXTCLOUD_MCP_PORT', '5811'))
        self.bind = env.get('NEXTCLOUD_MCP_BIND', '127.0.0.1')
        self.base_url = env.get('NEXTCLOUD_MCP_BASE_URL', 'http://127.0.0.1:8080').rstrip('/')
        self.tag_api_url = env.get('NEXTCLOUD_MCP_TAG_API_URL', 'http://127.0.0.1:5810').rstrip('/')
        self.tag_api_token = env.get('NEXTCLOUD_MCP_TAG_API_TOKEN', '').strip()
        self.tmp = Path(env.get('NEXTCLOUD_MCP_TMP', '/var/tmp/nextcloud-mcp'))
        self.read_only = env.get('NEXTCLOUD_MCP_READ_ONLY', '0').strip().lower() not in ('', '0', 'false', 'no')
        self.max_read_bytes = int(env.get('NEXTCLOUD_MCP_MAX_READ_BYTES', str(256 * 1024)))
        self.max_write_bytes = int(env.get('NEXTCLOUD_MCP_MAX_WRITE_BYTES', str(8 * 1024 * 1024)))
        self.max_body_bytes = int(env.get('NEXTCLOUD_MCP_MAX_BODY_BYTES', str(32 * 1024 * 1024)))
        self.max_extract_files = int(env.get('NEXTCLOUD_MCP_MAX_EXTRACT_FILES', '10000'))
        self.max_extract_bytes = int(env.get('NEXTCLOUD_MCP_MAX_EXTRACT_BYTES', str(4 * 1024 ** 3)))
        self.max_zip_bytes = int(env.get('NEXTCLOUD_MCP_MAX_ZIP_BYTES', str(4 * 1024 ** 3)))
        self.timeout = int(env.get('NEXTCLOUD_MCP_TIMEOUT', '120'))
        self.archive_timeout = int(env.get('NEXTCLOUD_MCP_ARCHIVE_TIMEOUT', '1800'))


# --------------------------------------------------------------------------
# パスの正規化
# --------------------------------------------------------------------------

def normalize_dav_path(raw, label='path'):
    """NextcloudのDAVパス（先頭/の絶対パス）へ正規化する。"""
    if not isinstance(raw, str) or not raw.strip():
        raise ToolError(f'{label}は必須です')
    value = raw.strip()
    if '\\' in value or '\x00' in value:
        raise ToolError(f'{label}に使えない文字が含まれています')
    if not value.startswith('/'):
        value = '/' + value
    parts = []
    for part in value.split('/'):
        if part in ('', '.'):
            continue
        if part == '..':
            raise ToolError(f'{label}に".."は使えません')
        parts.append(part)
    return '/' + '/'.join(parts) if parts else '/'


def ensure_write_allowed(path):
    """書き込み禁止の場所を拒否する（変換原本を守る）。"""
    lowered = path.lower()
    for prefix in WRITE_DENY_PREFIXES:
        if lowered == prefix.lower() or lowered.startswith(prefix.lower() + '/'):
            raise ToolError(f'{prefix} は変更できません（変換の原本）')


def ensure_music_mp3(path):
    if not path.lower().startswith('/music/') or not path.lower().endswith('.mp3'):
        raise ToolError('MP3タグの読み書きは /music 配下の .mp3 だけです')


def quote_path(path):
    return urllib.parse.quote(path, safe='/')


def archive_kind(name):
    """拡張子からアーカイブ形式を返す（zipまたはtar）。"""
    lowered = name.lower()
    if lowered.endswith('.zip'):
        return 'zip'
    if lowered.endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz')):
        return 'tar'
    raise ToolError('対応するのは .zip と .tar(.gz/.bz2/.xz) です')


def archive_stem(name):
    """アーカイブ名から展開先に使う名前を作る。"""
    base = posixpath.basename(name)
    lowered = base.lower()
    for suffix in ('.tar.gz', '.tar.bz2', '.tar.xz', '.tgz', '.tbz2', '.txz', '.tar', '.zip'):
        if lowered.endswith(suffix):
            return base[:len(base) - len(suffix)]
    return base


def safe_member_name(name):
    """展開するメンバー名を検証して相対パスへ正規化する。"""
    if not isinstance(name, str) or not name:
        raise ToolError('アーカイブに空のメンバー名があります')
    value = name.replace('\\', '/')
    if value.startswith('/') or value.startswith('~'):
        raise ToolError(f'絶対パスを含むアーカイブは展開しません: {name}')
    if '\x00' in value:
        raise ToolError('メンバー名にNUL文字があります')
    parts = []
    for part in value.split('/'):
        if part in ('', '.'):
            continue
        if part == '..':
            raise ToolError(f'".."を含むアーカイブは展開しません: {name}')
        parts.append(part)
    if not parts:
        raise ToolError(f'空のメンバー名です: {name}')
    return '/'.join(parts)


def copy_limited(source, target, limit):
    """limitバイトを超えたら止めながらコピーする（zip爆弾対策）。"""
    total = 0
    while True:
        chunk = source.read(1024 * 1024)
        if not chunk:
            return total
        total += len(chunk)
        if total > limit:
            raise ToolError('展開後のサイズが上限を超えました')
        target.write(chunk)


# --------------------------------------------------------------------------
# Nextcloudクライアント（呼び出し元のAuthorizationを転送する）
# --------------------------------------------------------------------------

class NextcloudClient:
    def __init__(self, authorization, config):
        self.authorization = authorization
        self.config = config
        self._user = None

    def request(self, method, path, body=None, headers=None, timeout=None):
        request = urllib.request.Request(self.config.base_url + path, data=body, method=method)
        request.add_header('Authorization', self.authorization)
        request.add_header('User-Agent', USER_AGENT)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            return urllib.request.urlopen(request, timeout=timeout or self.config.timeout)
        except urllib.error.HTTPError as error:
            detail = ''
            try:
                detail = error.read(2048).decode('utf-8', 'replace').strip()
            except Exception:  # noqa: BLE001 - 本文が無いエラーもある
                pass
            raise NextcloudError(error.code, f'{method} {path} -> HTTP {error.code}: {detail[:400]}') from error
        except urllib.error.URLError as error:
            raise ToolError(f'Nextcloudへ接続できません: {error.reason}') from error

    @property
    def user_id(self):
        if self._user is None:
            self._user = self.whoami()
        return self._user['id']

    def whoami(self):
        if self._user is None:
            data = self.ocs_json('/ocs/v2.php/cloud/user')
            user_id = str(data.get('id') or '')
            if not user_id:
                raise ToolError('NextcloudがユーザーIDを返しませんでした')
            self._user = {'id': user_id,
                          'displayname': str(data.get('displayname') or user_id)}
        return self._user

    def ocs_json(self, path, query=None):
        if query:
            path = path + '?' + urllib.parse.urlencode(query)
        with self.request('GET', path, headers={'OCS-APIRequest': 'true',
                                                'Accept': 'application/json'}) as response:
            payload = json.loads(response.read().decode('utf-8'))
        meta = payload.get('ocs', {}).get('meta', {})
        status = int(meta.get('statuscode') or 0)
        if status >= 400:
            raise ToolError(f"Nextcloud APIエラー ({status}): {meta.get('message') or 'unknown'}")
        return payload.get('ocs', {}).get('data', {})

    def dav_root(self):
        return f'/remote.php/dav/files/{urllib.parse.quote(self.user_id, safe="")}'

    def dav_path(self, path):
        return self.dav_root() + quote_path(path)

    def propfind(self, path, depth=1):
        with self.request('PROPFIND', self.dav_path(path), body=PROPFIND_BODY,
                          headers={'Depth': str(depth),
                                   'Content-Type': 'application/xml; charset=utf-8'}) as response:
            tree = ET.fromstring(response.read())
        prefix = self.dav_root()
        entries = []
        for node in tree.findall(f'{{{DAV_NS}}}response'):
            entry = parse_dav_response(node, prefix)
            if entry is not None:
                entries.append(entry)
        if not entries:
            raise NextcloudError(404, f'パスが見つかりません: {path}')
        entries.sort(key=lambda item: item['path'])
        return entries

    def stat(self, path):
        for entry in self.propfind(path, depth=0):
            if entry['path'] == path:
                return entry
        return self.propfind(path, depth=0)[0]

    def list_files(self, path):
        return self.propfind(path, depth=1)

    def walk(self, path):
        """フォルダ配下のファイルを再帰的に集める（Depth 1の繰り返し）。"""
        files = []
        queue = []
        for entry in self.propfind(path, depth=1):
            if entry['path'] == path:
                continue
            if entry['is_dir']:
                queue.append(entry['path'])
            else:
                files.append(entry)
        while queue:
            directory = queue.pop(0)
            for entry in self.propfind(directory, depth=1):
                if entry['path'] == directory:
                    continue
                if entry['is_dir']:
                    queue.append(entry['path'])
                else:
                    files.append(entry)
        return files

    def read_file(self, path, max_bytes):
        with self.request('GET', self.dav_path(path)) as response:
            content_type = response.headers.get('Content-Type') or ''
            etag = response.headers.get('OC-ETag') or response.headers.get('ETag') or ''
            data = response.read(max_bytes + 1)
        truncated = len(data) > max_bytes
        return (data[:max_bytes] if truncated else data, truncated, content_type, etag)

    def download_to(self, path, fileobj, timeout=None):
        with self.request('GET', self.dav_path(path), timeout=timeout) as response:
            shutil.copyfileobj(response, fileobj, 1024 * 1024)

    def put_file(self, path, data, size=None, if_match=None, create_only=False):
        headers = {'Content-Type': 'application/octet-stream'}
        if size is not None:
            headers['Content-Length'] = str(size)
        if if_match:
            headers['If-Match'] = if_match
        if create_only:
            headers['If-None-Match'] = '*'
        timeout = self.config.timeout if size is None else max(self.config.timeout, self.config.archive_timeout)
        with self.request('PUT', self.dav_path(path), body=data, headers=headers, timeout=timeout) as response:
            return {'etag': response.headers.get('OC-ETag') or response.headers.get('ETag') or ''}

    def create_folder(self, path):
        try:
            with self.request('MKCOL', self.dav_path(path)) as response:
                return {'created': response.status in (200, 201)}
        except NextcloudError as error:
            if error.status == 405:
                return {'created': False}
            raise

    def move(self, path, destination, overwrite=True):
        return self._copy_or_move('MOVE', path, destination, overwrite)

    def copy(self, path, destination, overwrite=True):
        return self._copy_or_move('COPY', path, destination, overwrite)

    def _copy_or_move(self, method, path, destination, overwrite):
        target = self.config.base_url + self.dav_path(destination)
        with self.request(method, self.dav_path(path),
                          headers={'Destination': target,
                                   'Overwrite': 'T' if overwrite else 'F'}) as response:
            return {'status': response.status}

    def delete(self, path):
        with self.request('DELETE', self.dav_path(path)) as response:
            return {'status': response.status}

    def search(self, term, limit=20):
        data = self.ocs_json('/ocs/v2.php/search/providers/files/search',
                             {'term': term, 'limit': max(1, min(int(limit), 100))})
        entries = data.get('entries') if isinstance(data, dict) else data
        results = []
        for entry in entries or []:
            attributes = entry.get('attributes') or {}
            results.append({
                'title': entry.get('title') or '',
                'subline': entry.get('subline') or '',
                'resource_url': entry.get('resourceUrl') or '',
                'path': attributes.get('path') or '',
                'fileid': attributes.get('fileid'),
                'size': attributes.get('size'),
            })
        return results


def parse_dav_response(node, prefix):
    prop = None
    for propstat in node.findall(f'{{{DAV_NS}}}propstat'):
        status = propstat.find(f'{{{DAV_NS}}}status')
        if status is not None and status.text and ' 200 ' in status.text:
            prop = propstat.find(f'{{{DAV_NS}}}prop')
            break
    if prop is None:
        return None

    def text(tag):
        element = prop.find(tag)
        return (element.text or '').strip() if element is not None and element.text else ''

    href = node.find(f'{{{DAV_NS}}}href')
    if href is None or not href.text:
        return None
    decoded = urllib.parse.unquote(href.text)
    if decoded == prefix:
        path = '/'
    elif decoded.startswith(prefix + '/'):
        path = '/' + decoded[len(prefix) + 1:]
    else:
        path = decoded

    permissions = text(f'{{{OC_NS}}}permissions')
    size = text(f'{{{OC_NS}}}size') or text(f'{{{DAV_NS}}}getcontentlength')
    return {
        'path': path,
        'name': text(f'{{{DAV_NS}}}displayname') or posixpath.basename(path.rstrip('/')),
        'is_dir': prop.find(f'{{{DAV_NS}}}resourcetype/{{{DAV_NS}}}collection') is not None,
        'size': int(size) if size.isdigit() else None,
        'etag': text(f'{{{DAV_NS}}}getetag').strip('"'),
        'fileid': text(f'{{{OC_NS}}}fileid'),
        'permissions': permissions,
        'writable': 'W' in permissions,
        'last_modified': text(f'{{{DAV_NS}}}getlastmodified'),
        'content_type': text(f'{{{DAV_NS}}}getcontenttype'),
    }


class TagApiClient:
    """music-toolsのtag-api（共有トークン）へのブリッジ。"""

    def __init__(self, config):
        self.config = config

    def _request(self, method, path, query=None, payload=None):
        if not self.config.tag_api_token:
            raise ToolError('NEXTCLOUD_MCP_TAG_API_TOKEN が設定されていません')
        url = self.config.tag_api_url + path
        if query:
            url += '?' + urllib.parse.urlencode(query)
        body = None
        headers = {'Authorization': 'Bearer ' + self.config.tag_api_token,
                   'User-Agent': USER_AGENT}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json; charset=utf-8'
        request = urllib.request.Request(url, data=body, method=method)
        for key, value in headers.items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as error:
            detail = error.read(2048).decode('utf-8', 'replace').strip()
            raise ToolError(f'タグAPIエラー (HTTP {error.code}): {detail[:400]}') from error
        except urllib.error.URLError as error:
            raise ToolError(f'タグAPIへ接続できません: {error.reason}') from error


# --------------------------------------------------------------------------
# 圧縮・解凍
# --------------------------------------------------------------------------

def list_archive_file(archive_path, kind, max_members):
    members = []
    if kind == 'zip':
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                members.append({'name': info.filename, 'size': info.file_size,
                                'is_dir': info.is_dir()})
                if len(members) >= max_members:
                    break
    else:
        with tarfile.open(archive_path) as archive:
            for member in archive:
                members.append({'name': member.name, 'size': member.size,
                                'is_dir': member.isdir()})
                if len(members) >= max_members:
                    break
    return members


def extract_archive_file(archive_path, kind, destination, config):
    """アーカイブを一時ディレクトリへ展開し、(ファイル一覧, 合計バイト) を返す。"""
    destination = Path(destination)
    extracted = []
    total = {'files': 0, 'bytes': 0}

    def reserve(size):
        total['files'] += 1
        if total['files'] > config.max_extract_files:
            raise ToolError('展開するファイル数が上限を超えました')
        if total['bytes'] + size > config.max_extract_bytes:
            raise ToolError('展開後の合計サイズが上限を超えました')

    def target_for(name):
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    if kind == 'zip':
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                name = safe_member_name(info.filename)
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ToolError(f'シンボリックリンクを含むアーカイブは展開しません: {name}')
                if info.is_dir():
                    (destination / name).mkdir(parents=True, exist_ok=True)
                    continue
                reserve(info.file_size)
                with archive.open(info) as source, open(target_for(name), 'wb') as out:
                    total['bytes'] += copy_limited(source, out, config.max_extract_bytes - total['bytes'])
                extracted.append(name)
    else:
        with tarfile.open(archive_path) as archive:
            for member in archive:
                name = safe_member_name(member.name)
                if member.issym() or member.islnk():
                    raise ToolError(f'リンクを含むアーカイブは展開しません: {name}')
                if member.isdir():
                    (destination / name).mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise ToolError(f'通常ファイル以外を含むアーカイブは展開しません: {name}')
                reserve(member.size)
                source = archive.extractfile(member)
                if source is None:
                    raise ToolError(f'メンバーを読めません: {name}')
                with source, open(target_for(name), 'wb') as out:
                    total['bytes'] += copy_limited(source, out, config.max_extract_bytes - total['bytes'])
                extracted.append(name)
    return extracted, total


def build_zip_file(files, target, max_bytes):
    """(アーカイブ内の名前, ローカルパス) の一覧からzipを作る。"""
    total = 0
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, local in files:
            size = os.path.getsize(local)
            total += size
            if total > max_bytes:
                raise ToolError('zipに入れる合計サイズが上限を超えました')
            archive.write(local, name)
    return total


# --------------------------------------------------------------------------
# ツール
# --------------------------------------------------------------------------

class Tool:
    def __init__(self, name, description, schema, handler, write=False, destructive=False):
        self.name = name
        self.description = description
        self.schema = schema
        self.handler = handler
        self.write = write
        self.destructive = destructive

    def definition(self):
        annotations = {'readOnlyHint': not self.write}
        if self.destructive:
            annotations['destructiveHint'] = True
        return {'name': self.name, 'description': self.description,
                'inputSchema': self.schema, 'annotations': annotations}


def schema(properties, required=()):
    return {'type': 'object', 'properties': properties,
            'required': list(required), 'additionalProperties': False}


PATH_PROP = {'type': 'string', 'description': 'Nextcloudの絶対パス（例: /inbox/foo.zip）'}


def entry_summary(entry):
    return {
        'path': entry['path'],
        'name': entry['name'],
        'type': 'directory' if entry['is_dir'] else 'file',
        'size': entry['size'],
        'fileid': entry['fileid'],
        'etag': entry['etag'],
        'last_modified': entry['last_modified'],
        'content_type': entry['content_type'],
        'writable': entry['writable'],
    }


def tool_whoami(client, config, args):
    return client.whoami()


def tool_list_files(client, config, args):
    path = normalize_dav_path(args.get('path'), 'path')
    entries = client.list_files(path)
    return {'path': path, 'count': len(entries),
            'entries': [entry_summary(item) for item in entries]}


def tool_file_info(client, config, args):
    path = normalize_dav_path(args.get('path'), 'path')
    return entry_summary(client.stat(path))


def tool_read_file(client, config, args):
    path = normalize_dav_path(args.get('path'), 'path')
    encoding = args.get('encoding') or 'auto'
    if encoding not in ('auto', 'text', 'base64'):
        raise ToolError('encodingは auto / text / base64 のいずれかです')
    max_bytes = min(int(args.get('max_bytes') or config.max_read_bytes), config.max_read_bytes)
    data, truncated, content_type, etag = client.read_file(path, max_bytes)
    if encoding == 'auto':
        suffix = posixpath.splitext(path)[1].lower()
        is_text = content_type.startswith('text/') or 'json' in content_type or suffix in TEXT_SUFFIXES
        encoding = 'text' if is_text else 'base64'
    if encoding == 'text':
        content = data.decode('utf-8', 'replace')
    else:
        content = base64.b64encode(data).decode('ascii')
    return {'path': path, 'encoding': encoding, 'bytes': len(data), 'truncated': truncated,
            'content_type': content_type, 'etag': etag, 'content': content}


def tool_search_files(client, config, args):
    term = str(args.get('term') or '').strip()
    if not term:
        raise ToolError('termは必須です')
    limit = min(int(args.get('limit') or 20), 100)
    return {'term': term, 'results': client.search(term, limit)}


def tool_read_music_tags(client, config, args):
    path = normalize_dav_path(args.get('path'), 'path')
    ensure_music_mp3(path)
    result = TagApiClient(config)._request('GET', '/tags', {'path': path})
    # tag-apiは/musicからの相対パス（先頭/無し）を返す。他のツールと形式を
    # 揃えるため、呼び出し元が渡した絶対パスへ差し替える。
    result['path'] = path
    return result


def tool_search_musicbrainz(client, config, args):
    query = {key: args.get(key) or '' for key in ('artist', 'title', 'album')}
    if not any(query.values()):
        raise ToolError('artist / title / album のどれかが必要です')
    return TagApiClient(config)._request('GET', '/musicbrainz', query)


def tool_list_archive(client, config, args):
    path = normalize_dav_path(args.get('path'), 'path')
    kind = archive_kind(path)
    workdir = Path(tempfile.mkdtemp(dir=config.tmp, prefix='list-'))
    try:
        local = workdir / 'archive'
        with open(local, 'wb') as out:
            client.download_to(path, out, timeout=config.archive_timeout)
        members = list_archive_file(local, kind, 1000)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return {'path': path, 'kind': kind, 'count': len(members), 'truncated': len(members) >= 1000,
            'members': members}


def tool_write_file(client, config, args):
    path = normalize_dav_path(args.get('path'), 'path')
    ensure_write_allowed(path)
    encoding = args.get('encoding') or 'text'
    content = args.get('content')
    if not isinstance(content, str):
        raise ToolError('contentは文字列で渡してください')
    if encoding == 'text':
        data = content.encode('utf-8')
    elif encoding == 'base64':
        try:
            data = base64.b64decode(content, validate=True)
        except ValueError as error:
            raise ToolError(f'base64を復号できません: {error}') from error
    else:
        raise ToolError('encodingは text / base64 のいずれかです')
    if len(data) > config.max_write_bytes:
        raise ToolError(f'1回に書けるのは{config.max_write_bytes}バイトまでです（大きい物は圧縮/解凍ツールで）')
    overwrite = args.get('overwrite')
    create_only = overwrite is False
    if create_only:
        try:
            client.stat(path)
            raise ToolError(f'既に存在します: {path}')
        except NextcloudError as error:
            if error.status != 404:
                raise
    result = client.put_file(path, data, size=len(data),
                             if_match=args.get('if_etag'), create_only=create_only)
    return {'path': path, 'bytes': len(data), 'etag': result['etag']}


def tool_create_folder(client, config, args):
    path = normalize_dav_path(args.get('path'), 'path')
    ensure_write_allowed(path)
    if path == '/':
        raise ToolError('ルートは作成できません')
    return {'path': path, **client.create_folder(path)}


def tool_move_file(client, config, args):
    path = normalize_dav_path(args.get('path'), 'path')
    destination = normalize_dav_path(args.get('destination'), 'destination')
    ensure_write_allowed(path)
    ensure_write_allowed(destination)
    if path == '/':
        raise ToolError('ルートは移動できません')
    return {'path': path, 'destination': destination,
            **client.move(path, destination, overwrite=args.get('overwrite') is not False)}


def tool_copy_file(client, config, args):
    path = normalize_dav_path(args.get('path'), 'path')
    destination = normalize_dav_path(args.get('destination'), 'destination')
    ensure_write_allowed(destination)
    return {'path': path, 'destination': destination,
            **client.copy(path, destination, overwrite=args.get('overwrite') is not False)}


def tool_delete_file(client, config, args):
    path = normalize_dav_path(args.get('path'), 'path')
    ensure_write_allowed(path)
    if path == '/':
        raise ToolError('ルートは削除できません')
    client.stat(path)
    return {'path': path, **client.delete(path),
            'note': 'Nextcloudのゴミ箱へ移動しました（完全削除はNextcloudから）'}


def tool_write_music_tags(client, config, args):
    path = normalize_dav_path(args.get('path'), 'path')
    ensure_music_mp3(path)
    tags = args.get('tags')
    if not isinstance(tags, dict) or not tags:
        raise ToolError('tagsに書き換える項目を渡してください')
    info = client.stat(path)
    if not info['writable']:
        raise ToolError(f'このユーザーでは書き換えられません: {path}')
    result = TagApiClient(config)._request('POST', '/tags', payload={'path': path, 'tags': tags})
    return {'path': path, **result}


def collect_zip_inputs(client, raw_paths):
    """(アーカイブ内の名前, パス) の一覧を作る。"""
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ToolError('pathsに1つ以上渡してください')
    items = []
    seen = set()
    for raw in raw_paths:
        path = normalize_dav_path(raw, 'paths')
        info = client.stat(path)
        if info['is_dir']:
            base = posixpath.basename(path.rstrip('/')) or 'root'
            for entry in client.walk(path):
                relative = entry['path'][len(path):].lstrip('/')
                items.append((posixpath.join(base, relative), entry['path']))
        else:
            items.append((posixpath.basename(path), path))
    deduped = []
    for name, path in items:
        if '/'.join([name, path]) in seen:
            continue
        seen.add('/'.join([name, path]))
        deduped.append((safe_member_name(name), path))
    return deduped


def tool_create_zip(client, config, args):
    target = normalize_dav_path(args.get('target'), 'target')
    ensure_write_allowed(target)
    if not target.lower().endswith('.zip'):
        raise ToolError('targetは .zip にしてください')
    overwrite = args.get('overwrite') is not False
    if not overwrite:
        try:
            client.stat(target)
            raise ToolError(f'既に存在します: {target}')
        except NextcloudError as error:
            if error.status != 404:
                raise
    items = collect_zip_inputs(client, args.get('paths'))
    workdir = Path(tempfile.mkdtemp(dir=config.tmp, prefix='zip-'))
    try:
        local_zip = workdir / 'archive.zip'
        local_files = []
        total = 0
        for name, remote in items:
            local = workdir / 'files' / name
            local.parent.mkdir(parents=True, exist_ok=True)
            with open(local, 'wb') as out:
                client.download_to(remote, out, timeout=config.archive_timeout)
            total += local.stat().st_size
            if total > config.max_zip_bytes:
                raise ToolError('zipに入れる合計サイズが上限を超えました')
            local_files.append((name, str(local)))
        build_zip_file(local_files, str(local_zip), config.max_zip_bytes)
        size = local_zip.stat().st_size
        with open(local_zip, 'rb') as body:
            result = client.put_file(target, body, size=size, create_only=not overwrite)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return {'target': target, 'entries': len(items), 'source_bytes': total,
            'zip_bytes': size, 'etag': result['etag']}


def tool_extract_archive(client, config, args):
    path = normalize_dav_path(args.get('path'), 'path')
    kind = archive_kind(path)
    default_target = posixpath.join(posixpath.dirname(path), archive_stem(path))
    target = normalize_dav_path(args.get('target') or default_target, 'target')
    ensure_write_allowed(target)
    if target == '/':
        raise ToolError('ルートへは展開できません')
    workdir = Path(tempfile.mkdtemp(dir=config.tmp, prefix='extract-'))
    try:
        local = workdir / 'archive'
        with open(local, 'wb') as out:
            client.download_to(path, out, timeout=config.archive_timeout)
        destination = workdir / 'out'
        destination.mkdir()
        extracted, total = extract_archive_file(local, kind, destination, config)
        client.create_folder(target)
        directories = set()
        files = []
        for name in extracted:
            parent = posixpath.dirname(name)
            while parent and parent not in directories:
                directories.add(parent)
                parent = posixpath.dirname(parent)
            files.append(name)
        for directory in sorted(directories):
            client.create_folder(posixpath.join(target, directory))
        for name in files:
            local_file = destination / name
            with open(local_file, 'rb') as body:
                client.put_file(posixpath.join(target, name), body,
                                size=local_file.stat().st_size)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if args.get('remove_archive'):
        client.delete(path)
    return {'path': path, 'target': target, 'kind': kind,
            'files': total['files'], 'bytes': total['bytes'],
            'removed_archive': bool(args.get('remove_archive'))}


TOOLS = [
    Tool('nextcloud_whoami',
         '接続しているNextcloudユーザー（ID・表示名）を返す。資格情報と疎通の確認用。',
         schema({}),
         tool_whoami),
    Tool('nextcloud_list_files',
         'フォルダ直下の一覧を返す（名前・種類・サイズ・etag・fileid・書込可否）。',
         schema({'path': PATH_PROP}, ['path']),
         tool_list_files),
    Tool('nextcloud_file_info',
         '1つのファイル/フォルダの情報（サイズ・etag・fileid・書込可否）を返す。',
         schema({'path': PATH_PROP}, ['path']),
         tool_file_info),
    Tool('nextcloud_read_file',
         'ファイルの中身を返す。テキストはそのまま、バイナリはbase64。上限で切り詰める。',
         schema({'path': PATH_PROP,
                 'encoding': {'type': 'string', 'enum': ['auto', 'text', 'base64'],
                              'description': '既定は拡張子とContent-Typeから自動判定'},
                 'max_bytes': {'type': 'integer', 'minimum': 1,
                               'description': '読み出す最大バイト数（サーバー上限まで）'}},
                ['path']),
         tool_read_file),
    Tool('nextcloud_search_files',
         'Nextcloudの統合検索でファイルを探す（ファイル名・中身）。',
         schema({'term': {'type': 'string', 'description': '検索語'},
                 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}},
                ['term']),
         tool_search_files),
    Tool('nextcloud_read_music_tags',
         'MP3のタグを返す（/music配下のみ）。MusicBrainz照合の前段に使う。',
         schema({'path': PATH_PROP}, ['path']),
         tool_read_music_tags),
    Tool('nextcloud_search_musicbrainz',
         'MusicBrainzで録音候補を検索する（artist/title/albumは分かるものだけでよい）。',
         schema({'artist': {'type': 'string'}, 'title': {'type': 'string'},
                 'album': {'type': 'string'}}),
         tool_search_musicbrainz),
    Tool('nextcloud_list_archive',
         'zip/tarを展開する前に中身を一覧する（サイズ・件数の確認用）。',
         schema({'path': PATH_PROP}, ['path']),
         tool_list_archive),
    Tool('nextcloud_write_file',
         'ファイルを新規作成/上書きする（テキストまたはbase64）。',
         schema({'path': PATH_PROP,
                 'content': {'type': 'string', 'description': '本文。encoding=base64ならbase64文字列'},
                 'encoding': {'type': 'string', 'enum': ['text', 'base64'],
                              'description': '既定はtext'},
                 'if_etag': {'type': 'string', 'description': 'このetagと一致するときだけ書く'},
                 'overwrite': {'type': 'boolean', 'description': 'falseなら既存を上書きしない'}},
                ['path', 'content']),
         tool_write_file, write=True, destructive=True),
    Tool('nextcloud_create_folder',
         'フォルダを作る（既にあれば作成済みとして返す）。',
         schema({'path': PATH_PROP}, ['path']),
         tool_create_folder, write=True),
    Tool('nextcloud_move_file',
         '移動または改名する。WebDAV MOVEなのでfileidと共有リンクが維持される。',
         schema({'path': PATH_PROP,
                 'destination': {'type': 'string', 'description': '移動先の絶対パス'},
                 'overwrite': {'type': 'boolean', 'description': 'falseなら既存を上書きしない'}},
                ['path', 'destination']),
         tool_move_file, write=True, destructive=True),
    Tool('nextcloud_copy_file',
         'ファイル/フォルダを複製する。',
         schema({'path': PATH_PROP,
                 'destination': {'type': 'string', 'description': '複製先の絶対パス'},
                 'overwrite': {'type': 'boolean'}},
                ['path', 'destination']),
         tool_copy_file, write=True),
    Tool('nextcloud_delete_file',
         'ファイル/フォルダを削除する（Nextcloudのゴミ箱へ入る）。',
         schema({'path': PATH_PROP}, ['path']),
         tool_delete_file, write=True, destructive=True),
    Tool('nextcloud_write_music_tags',
         'MP3のタグを書き換える（/music配下のみ）。バックアップが自動で残る。',
         schema({'path': PATH_PROP,
                 'tags': {'type': 'object', 'description':
                          'title/artist/album/albumartist/tracknumber/discnumber/date/genre/composer/comment',
                          'additionalProperties': {'type': ['string', 'array'],
                                                   'items': {'type': 'string'}}}},
                ['path', 'tags']),
         tool_write_music_tags, write=True, destructive=True),
    Tool('nextcloud_create_zip',
         '複数のファイル/フォルダを1つのzipにしてNextcloudへ置く。',
         schema({'paths': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1,
                           'description': 'zipに入れる絶対パスの一覧'},
                 'target': {'type': 'string', 'description': '作成するzipの絶対パス（.zip）'},
                 'overwrite': {'type': 'boolean'}},
                ['paths', 'target']),
         tool_create_zip, write=True, destructive=True),
    Tool('nextcloud_extract_archive',
         'zip/tarを指定フォルダへ展開する（ファイル数・展開サイズ・パス脱出を検査）。',
         schema({'path': PATH_PROP,
                 'target': {'type': 'string', 'description': '展開先フォルダ。既定はアーカイブと同じ場所の同名フォルダ'},
                 'remove_archive': {'type': 'boolean', 'description': 'trueなら展開後に元アーカイブをゴミ箱へ'}},
                ['path']),
         tool_extract_archive, write=True, destructive=True),
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


def available_tools(config):
    if config.read_only:
        return [tool.definition() for tool in TOOLS if not tool.write]
    return [tool.definition() for tool in TOOLS]


# --------------------------------------------------------------------------
# MCP (Streamable HTTP, JSON-RPC)
# --------------------------------------------------------------------------

def jsonrpc_result(message_id, result):
    return {'jsonrpc': '2.0', 'id': message_id, 'result': result}


def jsonrpc_error(message_id, code, message):
    return {'jsonrpc': '2.0', 'id': message_id, 'error': {'code': code, 'message': message}}


def tool_result(payload, is_error=False):
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return {'content': [{'type': 'text', 'text': text}], 'isError': is_error}


def call_tool(name, args, client, config):
    # 未知のツール名・読み取り専用での書き込み拒否・引数不正のToolErrorも、
    # tool.handler本体の失敗と同じくここで飲み込む。呼び出し元のHTTPハンドラ
    # (do_POST)はJSON-RPCエラーには変換しないため、ここで漏らすとサーバー
    # スレッドが未処理例外で落ちる（実測ではなく検証テストで判明）。
    started = time.monotonic()
    user = 'unknown'
    try:
        tool = TOOLS_BY_NAME.get(name)
        if tool is None:
            raise ToolError(f'未知のツールです: {name}')
        if config.read_only and tool.write:
            raise ToolError('このサーバーは読み取り専用です')
        if not isinstance(args, dict):
            raise ToolError('argumentsはオブジェクトで渡してください')
        try:
            user = client.whoami()['id']
        except Exception:  # noqa: BLE001 - ログ用なので失敗しても続行
            pass
        result = tool.handler(client, config, args)
    except ToolError as error:
        log.info('tool=%s user=%s error=%s duration=%.1fs', name, user, error, time.monotonic() - started)
        return tool_result(str(error), is_error=True)
    except Exception as error:  # noqa: BLE001 - 予期しない失敗は隠さずログへ
        log.exception('tool=%s user=%s failed', name, user)
        return tool_result(f'内部エラー: {error}', is_error=True)
    log.info('tool=%s user=%s ok duration=%.1fs', name, user, time.monotonic() - started)
    return tool_result(result)


def handle_message(message, client, config):
    """JSON-RPCメッセージ1件を処理する。通知はNoneを返す。"""
    if not isinstance(message, dict):
        return jsonrpc_error(None, -32600, 'Invalid Request')
    method = message.get('method')
    message_id = message.get('id')
    if not method:
        return None
    if message_id is None:
        return None
    if method == 'initialize':
        params = message.get('params') or {}
        requested = params.get('protocolVersion')
        protocol = requested if requested in SUPPORTED_PROTOCOLS else DEFAULT_PROTOCOL
        return jsonrpc_result(message_id, {
            'protocolVersion': protocol,
            'capabilities': {'tools': {'listChanged': False}},
            'serverInfo': {'name': SERVER_NAME, 'version': VERSION},
            'instructions': INSTRUCTIONS,
        })
    if method == 'ping':
        return jsonrpc_result(message_id, {})
    if method == 'tools/list':
        return jsonrpc_result(message_id, {'tools': available_tools(config)})
    if method == 'tools/call':
        params = message.get('params') or {}
        return jsonrpc_result(message_id,
                              call_tool(params.get('name') or '',
                                        params.get('arguments') or {}, client, config))
    return jsonrpc_error(message_id, -32601, f'Method not found: {method}')


class McpHandler(BaseHTTPRequestHandler):
    server_version = f'nextcloud-mcp/{VERSION}'
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        log.info('%s %s', self.address_string(), fmt % args)

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status):
        self.send_response(status)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def _authorization(self):
        return self.headers.get('Authorization') or ''

    def do_GET(self):
        route = urllib.parse.urlparse(self.path).path
        if route == '/healthz':
            self._send_json(200, {'status': 'ok', 'server': SERVER_NAME,
                                  'version': VERSION,
                                  'read_only': self.server.config.read_only})
            return
        if route == '/mcp':
            self.send_response(405)
            self.send_header('Allow', 'POST')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        self._send_json(404, {'error': 'not found'})

    def do_DELETE(self):
        if urllib.parse.urlparse(self.path).path == '/mcp':
            self._send_empty(405)
            return
        self._send_json(404, {'error': 'not found'})

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != '/mcp':
            self._send_json(404, {'error': 'not found'})
            return
        authorization = self._authorization()
        if not authorization:
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="nextcloud-mcp"')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            length = 0
        if length <= 0:
            self._send_json(400, jsonrpc_error(None, -32700, 'empty body'))
            return
        if length > self.server.config.max_body_bytes:
            self._send_json(413, jsonrpc_error(None, -32600, 'body too large'))
            return
        try:
            message = json.loads(self.rfile.read(length).decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, jsonrpc_error(None, -32700, 'parse error'))
            return
        if isinstance(message, list):
            self._send_json(400, jsonrpc_error(None, -32600, 'batch is not supported'))
            return
        client = self.server.client_factory(authorization)
        if isinstance(message, dict) and message.get('method') == 'initialize':
            try:
                client.whoami()
            except NextcloudError as error:
                if error.status in (401, 403):
                    self.send_response(401)
                    self.send_header('WWW-Authenticate', 'Basic realm="nextcloud-mcp"')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                log.warning('initialize: Nextcloudが応答しません: %s', error)
            except ToolError as error:
                # 接続不能（URLError由来）はNextcloudErrorではないので別に拾う。
                # 拾わないとinitializeの度にハンドラスレッドが例外で落ちる。
                log.warning('initialize: Nextcloudが応答しません: %s', error)
        response = handle_message(message, client, self.server.config)
        if response is None:
            self._send_empty(202)
            return
        self._send_json(200, response)


class McpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, config, client_factory):
        super().__init__(address, McpHandler)
        self.config = config
        self.client_factory = client_factory


def build_server(address, config, client_factory=None):
    if client_factory is None:
        client_factory = lambda authorization: NextcloudClient(authorization, config)  # noqa: E731
    return McpServer(address, config, client_factory)


def cleanup_tmp(tmp):
    tmp.mkdir(parents=True, exist_ok=True)
    for child in tmp.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except OSError:
                pass


def main():
    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    config = Config(os.environ)
    if not config.tag_api_token:
        log.warning('NEXTCLOUD_MCP_TAG_API_TOKEN が空です（タグ編集ツールは失敗します）')
    cleanup_tmp(config.tmp)
    server = build_server((config.bind, config.port), config)
    log.info('listening on %s:%s (Nextcloud %s, read_only=%s)',
             config.bind, config.port, config.base_url, config.read_only)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
