#!/usr/bin/env python3
"""バックアップの最後の成功時刻を node_exporter の textfile へ書く。

成功したときだけ残るファイル（vzdump のアーカイブ、監視の履歴、Flint 3 の設定）の
更新時刻を「最後に成功した時刻」とみなす。週次の VM の対象は Proxmox のジョブから読む。
"""
import glob
import json
import os
import subprocess
import sys

DUMP = '/srv/bulk/backups/dump'
JOB_COMMENT = 'shake-cloud tier1 weekly'
DAY = 86400
# (種類, 対象, ファイルの型, 許す古さ)
OTHERS = [
    ('monitoring', 'tarakoserver', '/srv/bulk/backups/monitoring/monitoring-*', 2 * DAY),
    ('router', 'Flint 3', '/root/flint3-backups/flint3-*', 2 * DAY),
]


def newest(pattern):
    times = [os.path.getmtime(p) for p in glob.glob(pattern)]
    return max(times) if times else 0


def pvesh(*args):
    out = subprocess.run(['pvesh', 'get', *args, '--output-format', 'json'],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def vm_name(vmid):
    try:
        return pvesh(f'/nodes/localhost/qemu/{vmid}/config').get('name', vmid)
    except subprocess.CalledProcessError:
        return vmid


def quote(value):
    return str(value).replace('\\', '\\\\').replace('"', '\\"')


def main(out_dir):
    rows = []
    for job in pvesh('/cluster/backup'):
        if job.get('comment') != JOB_COMMENT:
            continue
        for vmid in str(job.get('vmid', '')).split(','):
            vmid = vmid.strip()
            if vmid:
                rows.append(('vm', vm_name(vmid), newest(f'{DUMP}/vzdump-qemu-{vmid}-*.vma.zst'), 8 * DAY))
    for kind, target, pattern, max_age in OTHERS:
        rows.append((kind, target, newest(pattern), max_age))

    lines = [
        '# HELP shakecloud_backup_last_success_timestamp_seconds Newest successful backup file (0 when none).',
        '# TYPE shakecloud_backup_last_success_timestamp_seconds gauge',
    ]
    for kind, target, ts, _ in rows:
        lines.append(f'shakecloud_backup_last_success_timestamp_seconds{{kind="{kind}",target="{quote(target)}"}} {ts:.0f}')
    lines += [
        '# HELP shakecloud_backup_max_age_seconds How old the newest backup may be before it is late.',
        '# TYPE shakecloud_backup_max_age_seconds gauge',
    ]
    for kind, target, _, max_age in rows:
        lines.append(f'shakecloud_backup_max_age_seconds{{kind="{kind}",target="{quote(target)}"}} {max_age}')
    path = os.path.join(out_dir, 'backup_status.prom')
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    os.replace(path + '.tmp', path)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '/var/lib/prometheus/node-exporter')
