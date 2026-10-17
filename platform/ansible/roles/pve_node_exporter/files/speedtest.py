#!/usr/bin/env python3
"""回線の速さを 1 日 1 回測り、node_exporter の textfile へ書く。

timer は毎時起動するが、測るのは「1970 年からの日数 ÷ 24 の余り」の時だけ。
測る時刻が毎日 1 時間ずつずれ、24 日で全時間帯が一巡する。時間帯ごとの最新値を
残すので、Prometheus の avg_over_time で時間帯ごとの傾向が出せる。

  speedtest.py <textfile のディレクトリ> [--now]   # --now は時刻に関係なく測る
"""
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

DOWN_URL = 'https://speed.cloudflare.com/__down?bytes=50000000'
UP_URL = 'https://speed.cloudflare.com/__up'
DOWN_STREAMS, DOWN_BYTES = 8, 50_000_000
UP_STREAMS, UP_BYTES = 4, 25_000_000
STATE = '/var/lib/shakecloud-speedtest.json'


def download():
    out = subprocess.run(['curl', '-s', '-4', '--max-time', '60', '-o', '/dev/null', '-w', '%{http_code}', DOWN_URL],
                         capture_output=True, text=True)
    return out.stdout == '200'


def upload():
    out = subprocess.run(['curl', '-s', '-4', '--max-time', '60', '-o', '/dev/null', '-w', '%{http_code}',
                          '--data-binary', '@-', UP_URL],
                         input=b'\0' * UP_BYTES, capture_output=True)
    return out.stdout == b'200'


def measure(job, streams, size):
    """同時に streams 本流し、合計の bit/s を返す。1 本でも失敗したら 0。"""
    start = time.monotonic()
    with ThreadPoolExecutor(streams) as pool:
        ok = list(pool.map(lambda _: job(), range(streams)))
    elapsed = time.monotonic() - start
    return streams * size * 8 / elapsed if all(ok) else 0.0


def load_state():
    try:
        with open(STATE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'hours': {}}


def write_textfile(out_dir, state):
    lines = [
        '# HELP shakecloud_speedtest_bps Latest measured line speed (bit/s).',
        '# TYPE shakecloud_speedtest_bps gauge',
    ]
    last = state.get('last')
    if last:
        lines.append(f'shakecloud_speedtest_bps{{direction="down"}} {last["down"]:.0f}')
        lines.append(f'shakecloud_speedtest_bps{{direction="up"}} {last["up"]:.0f}')
        lines += ['# TYPE shakecloud_speedtest_timestamp_seconds gauge',
                  f'shakecloud_speedtest_timestamp_seconds {last["time"]:.0f}']
    lines += ['# HELP shakecloud_speedtest_by_hour_bps Latest measurement taken in each hour of the day.',
              '# TYPE shakecloud_speedtest_by_hour_bps gauge']
    for hour, v in sorted(state['hours'].items(), key=lambda kv: int(kv[0])):
        lines.append(f'shakecloud_speedtest_by_hour_bps{{hour="{int(hour):02d}",direction="down"}} {v["down"]:.0f}')
        lines.append(f'shakecloud_speedtest_by_hour_bps{{hour="{int(hour):02d}",direction="up"}} {v["up"]:.0f}')
    path = os.path.join(out_dir, 'speedtest.prom')
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    os.replace(path + '.tmp', path)


def main(argv):
    out_dir = argv[1] if len(argv) > 1 else '/var/lib/prometheus/node-exporter'
    state = load_state()
    now = time.time()
    hour = time.localtime(now).tm_hour
    due = int(now // 86400) % 24 == hour
    if due or '--now' in argv:
        down = measure(download, DOWN_STREAMS, DOWN_BYTES)
        up = measure(upload, UP_STREAMS, UP_BYTES)
        if down and up:
            state['last'] = {'time': now, 'down': down, 'up': up}
            state['hours'][str(hour)] = {'down': down, 'up': up}
            with open(STATE + '.tmp', 'w', encoding='utf-8') as f:
                json.dump(state, f)
            os.replace(STATE + '.tmp', STATE)
    write_textfile(out_dir, state)


if __name__ == '__main__':
    main(sys.argv)
