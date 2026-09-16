#!/usr/bin/env python3
"""LocalSend sender for the Nextcloud "send" action (media-01). Standard library only.

The localsend-hub on media-01 can only receive. This service implements the
other half of LocalSend protocol v2: it discovers devices on the LAN, then
sends a file to the chosen device's LocalSend app (prepare-upload + upload).

The Nextcloud shake_localsend app calls this API:
  GET  /devices                   -> discovered devices (alias, fingerprint, address)
  POST /send                      -> headers: X-Send-To (fingerprint),
                                     X-Send-Filename, X-Send-User;
                                     body: the file bytes
  POST /api/localsend/v2/register -> discovery replies from LocalSend devices
  GET  /healthz

Configuration (systemd EnvironmentFile):
  LOCALSEND_SEND_TOKEN        shared secret (SOPS)
  LOCALSEND_SEND_FINGERPRINT  stable device fingerprint (SOPS or generated once)
  LOCALSEND_SEND_PORT         default 53200
  LOCALSEND_SEND_ALIAS        default media-01
  LOCALSEND_SEND_TIMEOUT      discovery wait in seconds, default 3
  LOCALSEND_SEND_MAX_BYTES    default 2 GiB
"""
import json
import mimetypes
import os
import socket
import ssl
import threading
import time
from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPSConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

MULTICAST = ('224.0.0.167', 53317)
BROADCAST = ('255.255.255.255', 53317)
PROTOCOL_VERSION = '2.2'


def device_is_self(device, fingerprint):
    return (device.get('fingerprint') or '').lower() == fingerprint.lower()


def device_address(device, source_ip):
    """Return (scheme, host, port) for a discovered device."""
    scheme = 'https' if (device.get('protocol') or 'https') == 'https' else 'http'
    port = int(device.get('port') or 53317)
    return scheme, source_ip, port


def prepare_body(alias, fingerprint, port, filename, size, modified):
    mime, _ = mimetypes.guess_type(filename)
    file_id = 'file0'
    return {
        'info': {
            'alias': alias,
            'version': PROTOCOL_VERSION,
            'deviceModel': 'media-01',
            'deviceType': 'server',
            'fingerprint': fingerprint,
            'port': port,
            'protocol': 'http',
            'download': False,
        },
        'files': {
            file_id: {
                'id': file_id,
                'fileName': filename,
                'size': size,
                'fileType': mime or 'application/octet-stream',
                'sha256': None,
                'metadata': {'modified': modified},
            },
        },
    }, file_id


def parse_upload_ticket(payload, file_id):
    """Pull the session and token out of the prepare-upload response."""
    session = payload.get('sessionId')
    tokens = payload.get('files') or {}
    token = tokens.get(file_id)
    if not session or not token:
        raise ValueError('prepare-upload did not return a session and token')
    return session, token


def modified_time(path=None):
    when = datetime.fromtimestamp(
        os.path.getmtime(path), tz=timezone.utc) if path else datetime.now(timezone.utc)
    return when.strftime('%Y-%m-%dT%H:%M:%SZ')


def http_client(scheme, host, port, timeout):
    if scheme == 'https':
        # LocalSend devices use self-signed certificates and trust each other
        # by fingerprint, so certificate verification is off here as well.
        context = ssl._create_unverified_context()
        return HTTPSConnection(host, port, context=context, timeout=timeout)
    return HTTPConnection(host, port, timeout=timeout)


def send_file(device, source_ip, filename, content, alias, fingerprint, api_port,
              timeout=120):
    """Run the LocalSend v2 upload flow and return the receiving device's answer."""
    scheme, host, port = device_address(device, source_ip)
    body, file_id = prepare_body(alias, fingerprint, api_port, filename,
                                 len(content), modified_time())
    client = http_client(scheme, host, port, timeout)
    try:
        client.request('POST', '/api/localsend/v2/prepare-upload',
                       body=json.dumps(body).encode(),
                       headers={'Content-Type': 'application/json'})
        response = client.getresponse()
        payload = response.read()
        if response.status == 204:
            return {'status': 'skipped', 'device': device.get('alias')}
        if response.status != 200:
            raise RuntimeError(f'prepare-upload failed: {response.status} '
                               f'{payload[:200].decode(errors="replace")}')
        session, token = parse_upload_ticket(json.loads(payload), file_id)
        client.request('POST',
                       f'/api/localsend/v2/upload?sessionId={session}'
                       f'&fileId={file_id}&token={token}',
                       body=content,
                       headers={'Content-Type': 'application/octet-stream'})
        response = client.getresponse()
        response.read()
        if response.status != 200:
            raise RuntimeError(f'upload failed: {response.status}')
        return {'status': 'sent', 'device': device.get('alias'),
                'session': session, 'bytes': len(content)}
    finally:
        client.close()


class DeviceBook:
    """Recently discovered devices, keyed by fingerprint and by source address."""

    def __init__(self):
        self.lock = threading.Lock()
        self.devices = {}

    def remember(self, info, source_ip):
        fingerprint = (info.get('fingerprint') or '').lower()
        if not fingerprint:
            return
        with self.lock:
            self.devices[fingerprint] = dict(info, source_ip=source_ip)

    def find(self, fingerprint):
        with self.lock:
            return self.devices.get((fingerprint or '').lower())

    def all(self):
        with self.lock:
            return list(self.devices.values())


def announce_message(fingerprint, alias, api_port):
    return json.dumps({
        'alias': alias,
        'version': PROTOCOL_VERSION,
        'deviceModel': 'media-01',
        'deviceType': 'server',
        'fingerprint': fingerprint,
        'port': api_port,
        'protocol': 'http',
        'download': False,
        'announce': True,
    }).encode()


def discover(book, fingerprint, alias, api_port, timeout):
    """Announce ourselves on the LAN and collect LocalSend replies."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(('', 0))
    sock.settimeout(0.5)
    message = announce_message(fingerprint, alias, api_port)
    for _ in range(2):
        for target in (MULTICAST, BROADCAST):
            try:
                sock.sendto(message, target)
            except OSError:
                pass
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            payload, address = sock.recvfrom(65535)
        except socket.timeout:
            continue
        try:
            info = json.loads(payload)
        except ValueError:
            continue
        if not isinstance(info, dict) or device_is_self(info, fingerprint):
            continue
        book.remember(info, address[0])
    sock.close()
    return book.all()


def public_device(record):
    return {
        'alias': record.get('alias') or record.get('fingerprint'),
        'fingerprint': record.get('fingerprint'),
        'address': record.get('source_ip'),
        'port': record.get('port') or 53317,
        'protocol': record.get('protocol') or 'https',
        'deviceType': record.get('deviceType') or 'desktop',
    }


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


class SendHandler(BaseHTTPRequestHandler):
    server_version = 'localsend-send/1.0'
    timeout = 120

    def _respond(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        header = self.headers.get('Authorization') or ''
        return header == 'Bearer ' + self.server.token

    def do_GET(self):
        if self.path == '/healthz':
            self._respond(200, {'status': 'ok'})
            return
        if self.path.startswith('/devices'):
            if not self._authorized():
                self._respond(401, {'error': 'unauthorized'})
                return
            devices = discover(self.server.book, self.server.fingerprint,
                               self.server.alias, self.server.port,
                               self.server.discovery_timeout)
            self._respond(200, {'devices': [public_device(d) for d in devices]})
            return
        self._respond(404, {'error': 'not found'})

    def do_POST(self):
        if self.path.startswith('/api/localsend/v2/register'):
            try:
                info = json.loads(read_body(self, self._content_length()) or b'{}')
            except ValueError:
                self._respond(400, {'error': 'invalid json'})
                return
            if isinstance(info, dict) and not device_is_self(
                    info, self.server.fingerprint):
                self.server.book.remember(info, self.client_address[0])
            self._respond(200, {
                'alias': self.server.alias,
                'version': PROTOCOL_VERSION,
                'deviceModel': 'media-01',
                'deviceType': 'server',
                'fingerprint': self.server.fingerprint,
                'download': False,
            })
            return
        if self.path.startswith('/send'):
            if not self._authorized():
                self._respond(401, {'error': 'unauthorized'})
                return
            self._handle_send()
            return
        self._respond(404, {'error': 'not found'})

    def _content_length(self):
        try:
            return int(self.headers.get('Content-Length', '0') or 0)
        except ValueError:
            return 0

    def _handle_send(self):
        target = (self.headers.get('X-Send-To') or '').lower()
        filename = unquote(self.headers.get('X-Send-Filename') or 'file')
        username = unquote(self.headers.get('X-Send-User') or '')
        length = self._content_length()
        if length <= 0 and self.headers.get('Transfer-Encoding', '').lower() != 'chunked':
            self._respond(400, {'error': 'missing body'})
            return
        if length > self.server.max_bytes:
            self._respond(413, {'error': 'file size not allowed'})
            return
        device = self.server.book.find(target)
        if device is None:
            # まだ見つかっていなければ、その場で探す。
            discover(self.server.book, self.server.fingerprint, self.server.alias,
                     self.server.port, self.server.discovery_timeout)
            device = self.server.book.find(target)
        if device is None:
            self._respond(404, {'error': 'device not found on the LAN'})
            return
        content = read_body(self, length)
        prefix = f'{username} ' if username else ''
        try:
            result = send_file(device, device['source_ip'], prefix + filename, content,
                               self.server.alias, self.server.fingerprint,
                               self.server.port)
        except Exception as error:  # noqa: BLE001 - report any protocol failure
            self._respond(502, {'error': str(error)})
            return
        self._respond(200, result)

    def log_message(self, fmt, *args):
        print(f'{self.address_string()} {fmt % args}', flush=True)


def main():
    server = ThreadingHTTPServer(
        ('0.0.0.0', int(os.environ.get('LOCALSEND_SEND_PORT', '53200'))), SendHandler)
    server.token = os.environ['LOCALSEND_SEND_TOKEN']
    server.port = int(os.environ.get('LOCALSEND_SEND_PORT', '53200'))
    server.alias = os.environ.get('LOCALSEND_SEND_ALIAS', 'media-01')
    server.discovery_timeout = float(os.environ.get('LOCALSEND_SEND_TIMEOUT', '3'))
    server.max_bytes = int(os.environ.get('LOCALSEND_SEND_MAX_BYTES',
                                          str(2 * 1024 * 1024 * 1024)))
    server.fingerprint = os.environ['LOCALSEND_SEND_FINGERPRINT']
    server.book = DeviceBook()
    server.serve_forever()


if __name__ == '__main__':
    main()
