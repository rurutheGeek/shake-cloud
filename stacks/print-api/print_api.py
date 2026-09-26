#!/usr/bin/env python3
"""CUPS print relay for the cups_print Nextcloud app. Standard library only.

The Nextcloud app POSTs the document to /print with a bearer token. This
service accepts only the configured client addresses, stores the body in a
temporary file and runs `lp` against the configured CUPS queue.

Accepted documents: PDF, PNG, JPEG, plain text and Markdown (Markdown is
handed to the CUPS text filter). Optional headers: X-Print-Copies (1-99),
X-Print-Color (color|monochrome), X-Print-Ranges ("1-3,5").

It can also be called by anything else that can speak HTTP (scripts, Home
Assistant, ...) as long as it sends the shared token.

Environment:
  PRINT_API_TOKEN      shared secret (required)
  PRINT_QUEUE          CUPS queue name (required)
  PRINT_API_ALLOWED    comma-separated client addresses (empty = any client
                       that knows the token)
  PRINT_API_BIND       default 0.0.0.0
  PRINT_API_PORT       default 6320
  PRINT_API_MAX_BYTES  default 50 MiB
  CUPS_SERVER          passed through to `lp`, e.g. cups.example.net:631
                       (unset = the local CUPS)
"""
import hmac
import json
import os
import re
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'txt', 'md'}
# Markdown has no CUPS filter; hand it to the text filter instead.
TEMP_SUFFIX = {'md': 'txt'}
JOB_PATTERN = re.compile(r'request id is (\S+)')
RANGES_PATTERN = re.compile(r'[0-9,\- ]{1,64}')


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


def lp_command(queue, name, copies, color, path, ranges=None):
    command = ['lp', '-d', queue, '-t', name, '-n', str(copies),
               '-o', f'print-color-mode={color}']
    if ranges:
        command += ['-o', f'page-ranges={ranges}']
    return command + [path]


def parse_ranges(value):
    """Accept '1-3,5' style CUPS page ranges; reject anything else."""
    ranges = (value or '').strip()
    if not ranges:
        return None
    if not RANGES_PATTERN.fullmatch(ranges):
        return None
    return ranges


def parse_job_id(output):
    match = JOB_PATTERN.search(output or '')
    return match.group(1) if match else None


class PrintHandler(BaseHTTPRequestHandler):
    server_version = 'cups-print-relay/1.0'
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
        ranges = parse_ranges(self.headers.get('X-Print-Ranges'))
        if self.headers.get('X-Print-Ranges') and ranges is None:
            self._respond(400, {'error': 'invalid page range'})
            return

        suffix = TEMP_SUFFIX.get(extension, extension)
        handle = tempfile.NamedTemporaryFile(delete=False, suffix='.' + suffix)
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
                lp_command(self.server.queue, name, copies, color, handle.name, ranges),
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


def env_required(name):
    value = os.environ.get(name, '').strip()
    if not value:
        raise SystemExit(f'{name} is not set')
    return value


def main():
    server = ThreadingHTTPServer(
        (os.environ.get('PRINT_API_BIND', '0.0.0.0'),
         int(os.environ.get('PRINT_API_PORT', '6320'))),
        PrintHandler)
    server.token = env_required('PRINT_API_TOKEN')
    server.queue = env_required('PRINT_QUEUE')
    server.allowed = {ip.strip() for ip in
                      os.environ.get('PRINT_API_ALLOWED', '').split(',') if ip.strip()}
    server.max_bytes = int(os.environ.get('PRINT_API_MAX_BYTES', str(50 * 1024 * 1024)))
    server.serve_forever()


if __name__ == '__main__':
    main()
