#!/usr/bin/env python3
"""Home Assistant の eufy カメラが unavailable になったら config entry を reload する。

HA はライブ配信が長く失敗するとカメラエンティティを unavailable にすることがあり、
その状態では UI がライブを開始できない（キャッシュされた静止画だけが出る）。
このスクリプトは HA 自身の auth ストアから短期トークンを作って状態を見て、
unavailable のときだけ generic の config entry を reload する。

systemd の timer から root で動かす（auth ストアと API が読めればよい）。
"""

import base64
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CONFIG = Path('/srv/services/home-assistant/config')
ENTITY = 'camera.eufycam_s4_leo_rtc'
BASE = 'http://127.0.0.1:8123'


def make_token() -> str:
    data = json.loads((CONFIG / '.storage' / 'auth').read_text())['data']
    owner = next(u for u in data['users'] if u.get('is_owner'))
    token = [t for t in data['refresh_tokens'] if t['user_id'] == owner['id']][0]

    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj, separators=(',', ':')).encode()).rstrip(b'=')

    now = int(time.time())
    head = b64({'alg': 'HS256', 'typ': 'JWT'})
    body = b64({'iss': token['id'], 'iat': now, 'exp': now + 600, 'sub': owner['id']})
    sig = base64.urlsafe_b64encode(
        hmac.new(token['jwt_key'].encode(), head + b'.' + body, hashlib.sha256).digest()).rstrip(b'=')
    return (head + b'.' + body + b'.' + sig).decode()


def request(path: str, token: str, method: str = 'GET'):
    req = urllib.request.Request(BASE + path, method=method,
                                 headers={'Authorization': 'Bearer ' + token,
                                          'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def main() -> int:
    try:
        token = make_token()
        state = request(f'/api/states/{ENTITY}', token)['state']
    except (OSError, ValueError, KeyError, urllib.error.URLError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    if state != 'unavailable':
        return 0
    try:
        entries = request('/api/config/config_entries/entry', token)
        entry = next(e['entry_id'] for e in entries if e['domain'] == 'generic')
        request(f'/api/config/config_entries/entry/{entry}/reload', token, method='POST')
        print(f'RELOADED: {ENTITY} was {state}')
    except (OSError, ValueError, KeyError, urllib.error.URLError) as error:
        print(f'ERROR: reload failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
