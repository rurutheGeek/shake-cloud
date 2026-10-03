#!/usr/bin/env python3
"""leo_rtc ライブ配信の稼働確認。

VM（カメラと同じ LAN）で実行し、スーパーバイザ・Mediamtx・直近セッションをまとめて見る。

  python3 tools/leo_health.py [--out /var/tmp/live] [--api http://127.0.0.1:9997]

出力の見方:
- sessions: 直近 10 セッションの「パケット数・秒数・前の間隔」。パケット数が数千なら
  映像が取れている。100 未満が続くときはカメラが眠っている（時間帯の影響が大きい）。
- paths: Mediamtx が publish を受けているパス（`eufy` は映像のみ、`eufy_av` は音声付き）。
- snapshot: HA の still_image_url が読む JPEG の更新時刻と大きさ。
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request


def read_sessions(out: str, limit: int = 10):
    path = os.path.join(out, 'sessions.csv')
    try:
        with open(path) as handle:
            rows = [line.strip().split(',') for line in handle if line.strip()]
    except OSError:
        return []
    return rows[-limit:]


def probe_api(api: str) -> str:
    try:
        with urllib.request.urlopen(api + '/v3/paths/list', timeout=5) as response:
            data = json.load(response)
    except Exception as error:  # noqa: BLE001 - health tool prints the reason
        return f'API に接続できません: {error}'
    if not data.get('items'):
        return 'publish なし（セッションの合間）'
    return ', '.join(f"{item['name']}{'(ready)' if item.get('ready') else ''}" for item in data['items'])


def supervisor_pids() -> list[int]:
    try:
        found = subprocess.run(['pgrep', '-f', 'live_supervisor.sh'], capture_output=True, text=True, check=False)
    except OSError:
        return []
    return [int(line) for line in found.stdout.split() if line.isdigit()]


def snapshot_status(out: str) -> str:
    path = os.path.join(out, 'snapshot.jpg')
    try:
        info = os.stat(path)
    except OSError:
        return 'まだありません'
    age = time.time() - info.st_mtime
    return f'{info.st_size} バイト・{age:.0f} 秒前に更新'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default=os.environ.get('LEO_OUT', '/var/tmp/live'))
    parser.add_argument('--api', default='http://127.0.0.1:9997')
    args = parser.parse_args(argv)

    pids = supervisor_pids()
    print('supervisor:', '稼働中 pid=' + ','.join(map(str, pids)) if pids else '停止（pkill -f live_supervisor.sh で止められる）')
    print('paths:', probe_api(args.api))
    print('snapshot:', snapshot_status(args.out))
    rows = read_sessions(args.out)
    if not rows:
        print('sessions: 記録なし')
    else:
        print('sessions (直近):')
        for row in rows:
            if len(row) == 4:
                print(f'  {row[0]}  パケット {row[1]:>6}  {row[2]:>3}秒  間隔 {row[3]}秒')
    return 0


if __name__ == '__main__':
    sys.exit(main())
