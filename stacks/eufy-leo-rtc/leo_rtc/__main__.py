"""Development CLI for the native leo_rtc client.

Examples:
  EUFY_DID=... EUFY_LICENSE=... python3 -m leo_rtc discover
  EUFY_DID=... EUFY_LICENSE=... python3 -m leo_rtc wake --boot-action 1 --wait 45
  EUFY_DID=... EUFY_LICENSE=... python3 -m leo_rtc wake --keep-alive 60

Values come from the environment (or a local .env) and must never be
committed. See README.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from .client import LeoRtcClient, LeoRtcError
from .protocol import CALL_PRIV1
from .sdpinfo import build_sdp_info


def load_env(path: str) -> None:
    if not path or not os.path.exists(path):
        return
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key, value)


def client_from_env(args) -> LeoRtcClient:
    load_env(args.env)
    missing = [name for name in ('EUFY_DID', 'EUFY_LICENSE') if not os.environ.get(name)]
    if missing:
        raise SystemExit(f'ERROR: missing environment values: {", ".join(missing)}')
    return LeoRtcClient(
        sn=args.sn or os.environ.get('EUFY_SN', ''),
        did=os.environ['EUFY_DID'],
        license=os.environ['EUFY_LICENSE'],
        account=os.environ.get('EUFY_ACCOUNT', ''),
        host=args.host or os.environ.get('EUFY_SIGNAL_HOST') or None,
        port=int(args.port or os.environ.get('EUFY_SIGNAL_PORT', 5062)),
        timeout=args.timeout,
    )


def mask(value: str) -> str:
    if not value:
        return ''
    return value[:4] + '***'


def cmd_discover(args) -> int:
    with client_from_env(args) as client:
        payload = client.discover()
        session = client.login()
        print(json.dumps({
            'discover': payload,
            'login': {'server_addr': session.server_addr, 'contact': mask(session.contact)},
        }, indent=2, ensure_ascii=False))
    return 0


def cmd_wake(args) -> int:
    with client_from_env(args) as client:
        session = client.login()
        print(f'login ok: server={session.server_addr} contact={mask(session.contact)}')
        sdp_info = build_sdp_info()
        started = time.time()
        uuid = client.call(
            CALL_PRIV1, boot_action=args.boot_action, wakeup_type=args.wakeup_type, sdp_info=sdp_info)
        print(f'sent priv1 scall uuid={uuid} boot_action={args.boot_action} wakeup_type={args.wakeup_type}')
        end = time.time() + args.wait
        answered = False
        while time.time() < end:
            message = client.recv(timeout=max(0.5, end - time.time()))
            if message is None:
                continue
            elapsed = time.time() - started
            print(f'[{elapsed:5.1f}s] type={message.type_name} code={message.code} body_type={message.body_type} '
                  f'reserved={message.reserved} attach={len(message.attach)}B')
            if message.attach_json:
                print('        ' + json.dumps(message.attach_json, ensure_ascii=False)[:600])
            if message.type == 2 and message.code == 200:
                answered = True
                if not args.keep_alive:
                    break
            if answered and time.time() > started + args.keep_alive:
                break
        if not answered:
            print('no 200 answer (camera stayed asleep or rejected the call)', file=sys.stderr)
            return 1
        if args.keep_alive:
            time.sleep(max(0, started + args.keep_alive - time.time()))
        client.hangup(uuid)
        print('sent hangup')
    return 0


def cmd_listen(args) -> int:
    with client_from_env(args) as client:
        session = client.login()
        print(f'login ok: server={session.server_addr} contact={mask(session.contact)}')
        end = time.time() + args.wait
        while time.time() < end:
            message = client.recv(timeout=max(0.5, end - time.time()))
            if message is None:
                continue
            print(f'type={message.type_name} code={message.code} body_type={message.body_type} '
                  f'reserved={message.reserved} attach={len(message.attach)}B')
            if message.attach_json:
                print('  ' + json.dumps(message.attach_json, ensure_ascii=False)[:600])
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sn', help='camera serial (or EUFY_SN)')
    parser.add_argument('--host', help='signaling host (default: from discover)')
    parser.add_argument('--port', type=int, help='signaling port (default 5062)')
    parser.add_argument('--timeout', type=float, default=5.0)
    parser.add_argument('--env', default=os.path.join(os.path.dirname(__file__), '..', '.env'))
    sub = parser.add_subparsers(dest='action', required=True)

    sub.add_parser('discover', help='discover + login and print the servers')

    wake = sub.add_parser('wake', help='send the priv1 wake call and print replies')
    wake.add_argument('--boot-action', type=int, default=1)
    wake.add_argument('--wakeup-type', type=int, default=1)
    wake.add_argument('--wait', type=float, default=45.0)
    wake.add_argument('--keep-alive', type=float, default=0.0,
                      help='keep the session open for N seconds after the 200')

    listen = sub.add_parser('listen', help='login and print incoming signaling messages')
    listen.add_argument('--wait', type=float, default=60.0)

    args = parser.parse_args(argv)
    try:
        return {'discover': cmd_discover, 'wake': cmd_wake, 'listen': cmd_listen}[args.action](args)
    except (LeoRtcError, OSError, ValueError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
