#!/usr/bin/env python3
"""Print API for the Nextcloud print action (services-01). Standard library only.

The shake_print Nextcloud app POSTs the document to /print with a bearer token.
The service accepts only the configured client address, stores the body in a
temporary file and runs `lp` against the local CUPS queue.

systemd EnvironmentFile keys:
  PRINT_API_TOKEN      shared secret (SOPS)
  PRINT_API_ALLOWED    comma-separated client addresses (empty = no allowlist)
  PRINT_API_BIND       default 0.0.0.0
  PRINT_API_PORT       default 6320
  PRINT_QUEUE          default ts8430
  PRINT_API_MAX_BYTES  default 50 MiB
"""
import hmac
import json
import os
import re
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'txt'}
JOB_PATTERN = re.compile(r'request id is (\S+)')


def authorized(header, client, token, allowed):
    """Check the bearer token and, when configured, the client address."""
    if allowed and client not in allowed:
        return False
    return hmac.compare_digest(header or '', 'Bearer ' + token)


def printable_name(raw):
    """Reduce a client-supplied filename to a safe title and extension."""
    name = os.path.basename(unquote(raw or '')).replace('\x00', '').strip()
    if not name:
        name = 'document'
    extension = os.path.splitext(name)[1].lower().lstrip('.')
    return name, extension


def bounded(value, low, high, fallback):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


def lp_command(queue, name, copies, color, path):
    return ['lp', '-d', queue, '-t', name, '-n', str(copies),
            '-o', f'print-color-mode={color}', path]


def parse_job_id(output):
    match = JOB_PATTERN.search(output or '')
    return match.group(1) if match else None


class PrintHandler(BaseHTTPRequestHandler):
    server_version = 'shake-print/1.0'
    timeout = 60

    def _respond(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/healthz':
            self._respond(200, {'status': 'ok'})
        else:
            self._respond(404, {'error': 'not found'})

    def do_POST(self):
        if self.path != '/print':
            self._respond(404, {'error': 'not found'})
            return
        if not authorized(self.headers.get('Authorization'), self.client_address[0],
                          self.server.token, self.server.allowed):
            self._respond(401, {'error': 'unauthorized'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        if length <= 0 or length > self.server.max_bytes:
            self._respond(413, {'error': 'document size not allowed'})
            return
        name, extension = printable_name(self.headers.get('X-Print-Filename'))
        if extension not in ALLOWED_EXTENSIONS:
            self._respond(415, {'error': f'unsupported extension: {extension}'})
            return
        copies = bounded(self.headers.get('X-Print-Copies'), 1, 99, 1)
        color = 'monochrome' if self.headers.get('X-Print-Color') == 'monochrome' else 'color'

        handle = tempfile.NamedTemporaryFile(delete=False, suffix='.' + extension)
        try:
            remaining = length
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                handle.write(chunk)
                remaining -= len(chunk)
            handle.close()
            result = subprocess.run(
                lp_command(self.server.queue, name, copies, color, handle.name),
                capture_output=True, text=True, timeout=30)
        finally:
            os.unlink(handle.name)

        if result.returncode != 0:
            self._respond(502, {'error': result.stderr.strip() or 'lp failed'})
            return
        job = parse_job_id(result.stdout)
        if not job:
            self._respond(502, {'error': 'job id missing'})
            return
        self._respond(200, {'job': job})

    def log_message(self, fmt, *args):
        print(f'{self.address_string()} {fmt % args}', flush=True)


def main():
    server = ThreadingHTTPServer(
        (os.environ.get('PRINT_API_BIND', '0.0.0.0'),
         int(os.environ.get('PRINT_API_PORT', '6320'))),
        PrintHandler)
    server.token = os.environ['PRINT_API_TOKEN']
    server.allowed = {ip.strip() for ip in
                      os.environ.get('PRINT_API_ALLOWED', '').split(',') if ip.strip()}
    server.queue = os.environ.get('PRINT_QUEUE', 'ts8430')
    server.max_bytes = int(os.environ.get('PRINT_API_MAX_BYTES', str(50 * 1024 * 1024)))
    server.serve_forever()


if __name__ == '__main__':
    main()
