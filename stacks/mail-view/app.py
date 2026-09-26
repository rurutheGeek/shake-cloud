#!/usr/bin/env python3
r"""Read-only Gmail mailbox viewer for the home LAN. Standard library only.

The mailbox is the notification account (shake.notify@gmail.com): Authentik
invitations and alerts arrive there. The app signs in over IMAP with the same
Gmail app password as SMTP and selects the mailbox read-only (EXAMINE), so
opening a message never changes the \Seen flag. HTML mail is reduced to text,
remote images are never loaded, and the page is only reachable through the
Caddy Forward Auth entry on services-01.
"""
import argparse
import contextlib
import datetime
import email
import email.header
import email.utils
import html
import html.parser
import http.server
import imaplib
import json
import os
import re
import threading
import time
import traceback
import urllib.parse
from pathlib import Path

URL_PATTERN = re.compile(r'https?://[^\s<>"\'）】]+')
UID_PATTERN = re.compile(r'/m/(\d+)')
LIST_CACHE = {}
CACHE_LOCK = threading.Lock()

STYLE = """
:root { color-scheme: light dark; }
body { margin: 0 auto; max-width: 62rem; padding: 1rem;
       font-family: system-ui, -apple-system, "Noto Sans JP", sans-serif; line-height: 1.6; }
header { border-bottom: 1px solid #8884; padding-bottom: .5rem; margin-bottom: 1rem; }
h1 { font-size: 1.15rem; margin: 0; }
h1 a { color: inherit; text-decoration: none; }
h2.subject { font-size: 1.05rem; margin: 1rem 0 .3rem; overflow-wrap: anywhere; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: .4rem .5rem; border-bottom: 1px solid #8883; vertical-align: top; }
th { font-size: .8rem; color: #777; font-weight: 600; }
td.date { white-space: nowrap; color: #777; font-size: .85rem; }
td.from { max-width: 14rem; overflow-wrap: anywhere; }
tr.unread td.subject { font-weight: 700; }
tr.unread td.subject::before { content: "●"; color: #d33; font-size: .7rem; margin-right: .35rem; }
tr.read td.subject::before { content: "○"; color: #aaa; font-size: .7rem; margin-right: .35rem; }
.meta { color: #777; font-size: .85rem; }
.meta dt { font-weight: 600; }
.meta dd { margin: 0 0 .3rem; overflow-wrap: anywhere; }
pre.body { white-space: pre-wrap; overflow-wrap: anywhere; background: #8881;
           padding: 1rem; border-radius: .4rem; }
a { color: #06c; }
.notice { background: #ffd8; padding: .5rem .7rem; border-radius: .4rem; }
.empty { padding: 2rem 0; color: #777; }
"""


class MailViewError(Exception):
    """A user-facing failure: IMAP is unreachable, login failed, and so on."""


def decode_header_value(value):
    """Decode an RFC 2047 header (ISO-2022-JP subjects, and so on)."""
    if not value:
        return ''
    try:
        return str(email.header.make_header(email.header.decode_header(value)))
    except (LookupError, UnicodeDecodeError, ValueError):
        return value


def format_date(value, offset_hours):
    """Format a Date header in local time; fall back to the raw string."""
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return (value or '').strip()[:40]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    offset = datetime.timezone(datetime.timedelta(hours=offset_hours))
    return parsed.astimezone(offset).strftime('%Y-%m-%d %H:%M')


def human_size(size):
    value = float(size)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if value < 1024 or unit == 'GB':
            return f'{value:.0f} {unit}' if unit == 'B' else f'{value:.1f} {unit}'
        value /= 1024


class HtmlText(html.parser.HTMLParser):
    """Reduce HTML mail to text, collecting the links it would have hidden."""

    SKIPPED = {'script', 'style', 'head', 'title'}
    BLOCKS = {'p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'h4',
              'table', 'ul', 'ol', 'dl', 'dt', 'dd', 'hr', 'section', 'article',
              'blockquote', 'pre'}
    # 表のセルは改行ではなく空白で区切る。ラベルと値が1行に残る。
    CELLS = {'td', 'th'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.links = []
        self.skipped = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIPPED:
            self.skipped += 1
            return
        if tag == 'a':
            href = dict(attrs).get('href', '')
            if href.startswith(('http://', 'https://')):
                self.links.append(href)
        if tag in self.BLOCKS:
            self.parts.append('\n')
        elif tag in self.CELLS:
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in self.SKIPPED:
            self.skipped = max(0, self.skipped - 1)
        elif tag in self.BLOCKS:
            self.parts.append('\n')
        elif tag in self.CELLS:
            self.parts.append(' ')

    def handle_data(self, data):
        if not self.skipped:
            self.parts.append(data)


def strip_html(source):
    """Reduce HTML mail to tidy text.

    Table-based mail (Alertmanager, for one) is indented and full of markup, so
    lines are trimmed and runs of blank lines collapse to one. Without this the
    body arrives as indented fragments with rows of empty lines.
    """
    parser = HtmlText()
    parser.feed(source)
    parser.close()
    lines = []
    for line in ''.join(parser.parts).splitlines():
        line = ' '.join(line.split())
        if line:
            lines.append(line)
        elif lines and lines[-1] != '':
            lines.append('')
    text = '\n'.join(lines).strip()
    links = []
    for link in parser.links:
        if link not in links:
            links.append(link)
    if links:
        text += '\n\nリンク:\n' + '\n'.join(links[:20])
    return text


def extract_body(message):
    """Return the visible text and the attachment list for one message."""
    texts, htmls, attachments = [], [], []
    for part in message.walk():
        if part.get_content_maintype() == 'multipart':
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True)
        if filename:
            attachments.append((decode_header_value(filename),
                                len(payload or b'')))
            continue
        if payload is None:
            continue
        charset = part.get_content_charset() or 'utf-8'
        text = payload.decode(charset, 'replace').replace('\r\n', '\n')
        if part.get_content_type() == 'text/plain':
            texts.append(text)
        elif part.get_content_type() == 'text/html':
            htmls.append(text)
    if texts:
        body = '\n\n'.join(text.strip('\n') for text in texts)
    elif htmls:
        body = '\n\n'.join(strip_html(text) for text in htmls)
    else:
        body = '（表示できるテキスト本文がありません。添付ファイルのみのメールです。）'
    return body.strip(), attachments


def render_text(text):
    """Escape plain text and turn http(s) URLs into links, and nothing else."""
    pieces, last = [], 0
    for match in URL_PATTERN.finditer(text):
        raw = match.group(0)
        url = raw.rstrip('.,;:!?)]}）」』、。')
        pieces.append(html.escape(text[last:match.start()]))
        pieces.append(f'<a href="{html.escape(url)}" rel="noreferrer noopener" '
                      f'target="_blank">{html.escape(url)}</a>')
        pieces.append(html.escape(raw[len(url):]))
        last = match.end()
    pieces.append(html.escape(text[last:]))
    return ''.join(pieces)


def settings():
    """Build the runtime configuration from the environment."""
    def number(name, default, low, high):
        raw = os.environ.get(name, str(default))
        try:
            value = int(raw)
        except ValueError:
            raise SystemExit(f'{name} must be a number: {raw}')
        if not low <= value <= high:
            raise SystemExit(f'{name} is out of range: {raw}')
        return value

    password_file = os.environ.get('IMAP_PASSWORD_FILE', '').strip()
    if password_file:
        password = Path(password_file).read_text(encoding='utf-8').strip()
    else:
        password = os.environ.get('IMAP_PASSWORD', '').strip()
    return {
        'imap_host': os.environ.get('IMAP_HOST', 'imap.gmail.com').strip(),
        'imap_port': number('IMAP_PORT', 993, 1, 65535),
        'imap_username': os.environ.get('IMAP_USERNAME', '').strip(),
        'imap_password': password,
        'mailbox': os.environ.get('MAILBOX', 'INBOX').strip(),
        'message_limit': number('MESSAGE_LIMIT', 50, 1, 500),
        'cache_seconds': number('CACHE_SECONDS', 30, 0, 3600),
        'max_bytes': number('MAX_BYTES', 524288, 65536, 20971520),
        'offset_hours': number('TZ_OFFSET_HOURS', 9, -12, 14),
        'bind_address': os.environ.get('BIND_ADDRESS', '0.0.0.0').strip(),
        'port': number('PORT', 8080, 1, 65535),
    }


@contextlib.contextmanager
def connection(config):
    """Log in and select the mailbox read-only, so no flag ever changes."""
    try:
        client = imaplib.IMAP4_SSL(host=config['imap_host'],
                                   port=config['imap_port'], timeout=30)
    except (OSError, imaplib.IMAP4.error) as error:
        raise MailViewError(
            f'IMAP へ接続できません（{config["imap_host"]}:{config["imap_port"]}）。') from error
    try:
        try:
            client.login(config['imap_username'], config['imap_password'])
        except imaplib.IMAP4.error as error:
            raise MailViewError(
                'IMAP のログインに失敗しました。Gmail のアプリパスワードと、'
                'Gmail 設定の「IMAP アクセスを有効にする」を確認してください。') from error
        except OSError as error:
            raise MailViewError(
                'IMAP への接続がタイムアウトしました。時間をおいて再読み込みしてください。') from error
        status, _ = client.select(config['mailbox'], readonly=True)
        if status != 'OK':
            raise MailViewError(f'メールボックス {config["mailbox"]} を開けませんでした。')
        yield client
    finally:
        with contextlib.suppress(OSError, imaplib.IMAP4.error):
            client.logout()


def list_messages(client, limit, offset_hours):
    """Fetch the newest messages: envelope fields and flags only.

    limit of zero or less means the whole mailbox; the caller also gets the
    total so the page can say whether it is showing everything.
    """
    status, data = client.uid('search', None, 'ALL')
    if status != 'OK':
        raise MailViewError(f'IMAP の検索に失敗しました（{status}）。')
    uids = (data[0] or b'').split()
    total = len(uids)
    selected = uids if limit <= 0 else uids[-limit:]
    selected = selected[::-1]
    if not selected:
        return [], total
    status, data = client.uid(
        'fetch', b','.join(selected),
        '(FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])')
    if status != 'OK':
        raise MailViewError(f'IMAP のヘッダー取得に失敗しました（{status}）。')
    found = {}
    for item in data:
        if not isinstance(item, tuple):
            continue
        meta, raw = item[0] or b'', item[1] or b''
        uid = re.search(rb'UID (\d+)', meta)
        if not uid:
            continue
        flags = re.search(rb'FLAGS \(([^)]*)\)', meta)
        size = re.search(rb'RFC822\.SIZE (\d+)', meta)
        header = email.message_from_bytes(raw)
        subject = decode_header_value(header.get('Subject')) or '(件名なし)'
        found[uid.group(1).decode()] = {
            'uid': uid.group(1).decode(),
            'from': decode_header_value(header.get('From')) or '(差出人なし)',
            # 件名に折り返しの改行が混ざるメールがある（Alertmanager）。1行に均す。
            'subject': ' '.join(subject.split()),
            'date': format_date(header.get('Date'), offset_hours),
            'unread': b'\\Seen' not in (flags.group(1) if flags else b''),
            'size': int(size.group(1)) if size else 0,
        }
    return [found[uid.decode()] for uid in selected if uid.decode() in found], total


def fetch_message(client, uid, max_bytes):
    """Fetch one message; large ones are cut after max_bytes."""
    status, data = client.uid('fetch', uid, f'(RFC822.SIZE BODY.PEEK[]<0.{max_bytes}>)')
    if status != 'OK':
        raise MailViewError(f'IMAP のメッセージ取得に失敗しました（{status}）。')
    raw, size = None, 0
    for item in data:
        if not isinstance(item, tuple):
            continue
        meta, raw = item[0] or b'', item[1] or b''
        match = re.search(rb'RFC822\.SIZE (\d+)', meta)
        if match:
            size = int(match.group(1))
        break
    if raw is None:
        raise MailViewError('メッセージを取得できませんでした。')
    message = email.message_from_bytes(raw)
    body, attachments = extract_body(message)
    return {
        'uid': uid,
        'from': decode_header_value(message.get('From')) or '(差出人なし)',
        'to': decode_header_value(message.get('To')) or '(宛先なし)',
        'subject': ' '.join(
            (decode_header_value(message.get('Subject')) or '(件名なし)').split()),
        'date': decode_header_value(message.get('Date')),
        'body': body,
        'attachments': attachments,
        'truncated': bool(size and size > len(raw)),
    }


def cached_list(config, limit, force=False):
    """Keep the inbox listing for a few seconds so paging stays quick.

    limit of zero means every message. Returns rows, total, fetch time and
    whether this came from the cache.
    """
    key = (config['imap_host'], config['mailbox'], limit)
    now = time.monotonic()
    with CACHE_LOCK:
        entry = LIST_CACHE.get(key)
        if entry and entry[0] > now and not force:
            return entry[1], entry[2], entry[3], True
    with connection(config) as client:
        rows, total = list_messages(client, limit, config['offset_hours'])
    fetched = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=config['offset_hours']))
    ).strftime('%Y-%m-%d %H:%M:%S')
    with CACHE_LOCK:
        LIST_CACHE[key] = (now + config['cache_seconds'], rows, total, fetched)
    return rows, total, fetched, False


def requested_limit(config, query):
    """Read the ?limit= override: 'all' shows every message, capped at 2000."""
    raw = (query.get('limit') or [''])[0]
    if raw == 'all':
        return 0
    if raw.isdigit():
        return min(int(raw), 2000)
    return config['message_limit']


def page(title, body):
    return f'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>{html.escape(title)}</title>
<style>{STYLE}</style>
</head>
<body>
<header><h1><a href="/">通知メール</a></h1></header>
<main>
{body}
</main>
</body>
</html>
'''


def index_page(config, limit=None, force=False):
    if limit is None:
        limit = config['message_limit']
    rows, total, fetched, from_cache = cached_list(config, limit, force)
    shown = f'全 {total} 件' if limit <= 0 else f'全 {total} 件中 {len(rows)} 件'
    links = []
    if 0 < limit and total > len(rows):
        links.append('<a href="/?limit=all">全件を表示</a>')
    if limit != config['message_limit']:
        links.append(f'<a href="/">最新{config["message_limit"]}件</a>')
    links.append('<a href="/?limit=all&refresh=1">再読み込み</a>'
                 if limit <= 0 else '<a href="/?refresh=1">再読み込み</a>')
    head = (
        f'<p class="meta">{html.escape(config["imap_username"])} ・ '
        f'{shown} ・ 読み取り専用 ・ 取得 {html.escape(fetched)}'
        f'{"（キャッシュ）" if from_cache else ""} ・ ' + ' ・ '.join(links) + '</p>')
    if not rows:
        return page('通知メール', head + '<p class="empty">受信トレイは空です。</p>')
    body = [head, '<table>', '<thead><tr><th></th><th>差出人</th><th>件名</th>'
                      '<th>日時</th></tr></thead>', '<tbody>']
    for row in rows:
        state = 'unread' if row['unread'] else 'read'
        body.append(
            f'<tr class="{state}">'
            f'<td></td>'
            f'<td class="from">{html.escape(row["from"])}</td>'
            f'<td class="subject"><a href="/m/{html.escape(row["uid"])}">'
            f'{html.escape(row["subject"])}</a></td>'
            f'<td class="date">{html.escape(row["date"])}</td>'
            f'</tr>')
    body += ['</tbody>', '</table>']
    return page('通知メール', '\n'.join(body))


def message_page(config, uid):
    with connection(config) as client:
        message = fetch_message(client, uid, config['max_bytes'])
    details = [
        ('差出人', message['from']),
        ('宛先', message['to']),
        ('日時', message['date']),
    ]
    definition = ''.join(
        f'<dt>{label}</dt><dd>{html.escape(value)}</dd>' for label, value in details)
    body = [f'<p class="meta"><a href="/">← 一覧へ</a></p>',
            f'<h2 class="subject">{html.escape(message["subject"])}</h2>',
            f'<dl class="meta">{definition}</dl>']
    if message['truncated']:
        body.append('<p class="notice">本文が大きいため、先頭のみ表示しています。</p>')
    body.append(f'<pre class="body">{render_text(message["body"])}</pre>')
    if message['attachments']:
        items = '、'.join(
            f'{html.escape(name)}（{human_size(size)}）'
            for name, size in message['attachments'])
        body.append(f'<p class="meta">添付ファイル: {items}（この画面では開けません）</p>')
    return page(f'通知メール: {message["subject"]}', '\n'.join(body))


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'mail-view'
    sys_version = ''

    def respond(self, status, document, content_type='text/html; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(document)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header(
            'Content-Security-Policy',
            "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'")
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(document)

    def do_GET(self):
        config = self.server.config
        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if parsed.path == '/healthz':
                document = json.dumps({
                    'status': 'ok',
                    'mailbox': config['mailbox'],
                    'username': config['imap_username'],
                }).encode('utf-8')
                return self.respond(200, document, 'application/json; charset=utf-8')
            if parsed.path == '/favicon.ico':
                return self.respond(204, b'', 'image/x-icon')
            if parsed.path == '/':
                document = index_page(config, requested_limit(config, query),
                                      'refresh' in query).encode('utf-8')
                return self.respond(200, document)
            match = UID_PATTERN.fullmatch(parsed.path)
            if match:
                document = message_page(config, match.group(1)).encode('utf-8')
                return self.respond(200, document)
            document = page('見つかりません', '<p class="empty">ページがありません。</p>')
            return self.respond(404, document.encode('utf-8'))
        except MailViewError as error:
            document = page('メールを取得できません',
                            f'<p class="notice">{html.escape(str(error))}</p>')
            return self.respond(502, document.encode('utf-8'))
        except OSError:
            traceback.print_exc()
            document = page('メールを取得できません',
                            '<p class="notice">IMAP との通信がタイムアウトしました。'
                            '時間をおいて再読み込みしてください。</p>')
            return self.respond(502, document.encode('utf-8'))
        except Exception:
            traceback.print_exc()
            document = page('エラー', '<p class="notice">内部エラーが発生しました。'
                                     'コンテナのログを確認してください。</p>')
            return self.respond(500, document.encode('utf-8'))

    def log_message(self, format, *args):
        print(f'{self.address_string()} [{self.log_date_time_string()}] {format % args}',
              flush=True)


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, config):
        self.config = config
        super().__init__(address, Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    config = settings()
    if not config['imap_username'] or not config['imap_password']:
        raise SystemExit('IMAP_USERNAME and IMAP_PASSWORD are required')
    server = Server((config['bind_address'], config['port']), config)
    print(f'mail-view listening on {config["bind_address"]}:{config["port"]} '
          f'for {config["imap_username"]} ({config["mailbox"]})', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
