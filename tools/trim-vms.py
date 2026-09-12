#!/usr/bin/env python3
"""Reclaim rebuildable space on the service VMs (I01).

Docker build cache and apt archives grow back on every deployment and neither
is data, so they are safe to drop. Unused Docker images and old journals can be
someone's work or evidence, so they are removed only when asked for.

The default is a dry run that only reports what is reclaimable. With --apply
the script runs the reclamation, then shows the disk before and after.

    python3 tools/trim-vms.py                       # report only
    python3 tools/trim-vms.py --apply               # build cache + apt
    python3 tools/trim-vms.py --apply --images --journal-max 100M
    python3 tools/trim-vms.py --apply --only cloud-01,services-01
    python3 tools/trim-vms.py --apply --include-dev # dev-a / dev-b too

Run it from dev-b (or the admin machine) where ~/.ssh/id_ed25519_pve opens the
VMs. Keep the default hosts and dev VMs apart: the dev VMs are two people's
working machines, so they are opt-in and their tagged images are never removed
unless --all-images is given. Exit status is non-zero if a host was unreachable
or a command failed, so an unattended runner can gate on it.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

# Addresses match docs/operations/handover.md, the deployment ledger. The
# management VMs are the ones the automation owns; the dev VMs belong to their
# users (--include-dev).
VMS = [
    {'name': 'services-01', 'address': '192.168.10.200', 'user_vm': False},
    {'name': 'identity', 'address': '192.168.10.204', 'user_vm': False},
    {'name': 'cloud-01', 'address': '192.168.10.205', 'user_vm': False},
    {'name': 'storage-s3', 'address': '192.168.10.206', 'user_vm': False},
    {'name': 'dev-a', 'address': '192.168.10.202', 'user_vm': True},
    {'name': 'dev-b', 'address': '192.168.10.203', 'user_vm': True},
]
SSH_KEY = Path.home() / '.ssh/id_ed25519_pve'
SSH_OPTIONS = [
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=accept-new',
    '-o', 'ConnectTimeout=8',
]
# systemd prints journal sizes in 1024s, Docker in 1000s.
JOURNAL_RE = re.compile(r'([0-9.]+)\s*([KMGT]?)', re.IGNORECASE)


def parse_size(text, base=1000):
    """'10.53GB (81%)' or '111.6M' -> bytes.

    Docker counts in 1000s (units.HumanSize), systemd in 1024s; the caller
    picks the base so a report never mixes the two silently.
    """
    token = text.strip().split(' ')[0] if text.strip() else ''
    number = ''
    for char in token:
        if char.isdigit() or char == '.':
            number += char
        else:
            break
    if not number:
        return 0
    suffix = token[len(number):].strip().upper().rstrip('B')
    scale = {'': 1, 'K': base, 'M': base ** 2, 'G': base ** 3, 'T': base ** 4}.get(suffix)
    if scale is None:
        return 0
    return int(float(number) * scale)


def docker_reclaimable(output):
    """'Type' -> reclaimable bytes from `docker system df --format '{{json .}}'`."""
    seen = {}
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        seen[row.get('Type', '?')] = parse_size(row.get('Reclaimable', '0B'))
    return seen


def journal_bytes(output):
    match = JOURNAL_RE.search(output)
    if not match:
        return 0
    scale = {'': 1, 'K': 1024, 'M': 1024 ** 2, 'G': 1024 ** 3, 'T': 1024 ** 4}.get(
        match.group(2).upper())
    if scale is None:
        return 0
    return int(float(match.group(1)) * scale)


def plan_commands(snapshot, options):
    """The commands --apply will run on one host.

    Kept apart from the calls so what is about to be touched can be read and
    tested without a VM (tests/test_trim_vms.py). Nothing here runs in the
    default dry-run mode.
    """
    commands = []
    if snapshot.get('docker'):
        commands.append('sudo docker builder prune -f')
        if options.get('all_images'):
            commands.append('sudo docker image prune -af')
        elif options.get('images'):
            commands.append('sudo docker image prune -f')
    if snapshot.get('apt'):
        commands.append('sudo apt-get clean')
    if options.get('journal_max'):
        commands.append(f"sudo journalctl --vacuum-size={options['journal_max']}")
    return commands


def select_vms(only, include_dev):
    wanted = {name.strip() for name in only.split(',') if name.strip()} if only else None
    selected = [vm for vm in VMS if wanted is None or vm['name'] in wanted]
    if wanted is not None:
        missing = wanted - {vm['name'] for vm in selected}
        if missing:
            raise SystemExit(f'trim-vms: unknown host(s): {", ".join(sorted(missing))}')
    if wanted is None and not include_dev:
        selected = [vm for vm in selected if not vm['user_vm']]
    return selected


def size_text(value, base=1024):
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if abs(value) < base or unit == 'TiB':
            return f'{value:.1f}{unit}' if unit != 'B' else f'{int(value)}B'
        value /= base


def docker_size_text(value):
    """Docker reports in 1000s; print the same way so numbers match its own."""
    for unit in ('B', 'kB', 'MB', 'GB', 'TB'):
        if abs(value) < 1000 or unit == 'TB':
            return f'{value:.1f}{unit}' if unit != 'B' else f'{int(value)}B'
        value /= 1000


class Remote:
    def __init__(self, host, key):
        self.host = host
        self.target = f'debian@{host["address"]}'
        self.key = key

    def run(self, command, timeout=180):
        return subprocess.run(
            ['ssh', '-i', str(self.key), *SSH_OPTIONS, self.target, command],
            capture_output=True, text=True, timeout=timeout,
        )


def read_snapshot(remote):
    """One host's disk, Docker and cache state. Errors land in 'errors'."""
    snapshot = {'errors': []}

    def read(command):
        result = remote.run(command)
        if result.returncode != 0:
            snapshot['errors'].append(f'{command!r}: {result.stderr.strip() or result.returncode}')
            return ''
        return result.stdout.strip()

    disk = read("df -B1 --output=used,avail / | tail -1")
    if not disk:
        snapshot['reachable'] = False
        return snapshot
    used, avail = (int(part) for part in disk.split())
    snapshot['reachable'] = True
    snapshot['disk'] = {'used': used, 'avail': avail}

    snapshot['docker'] = read("command -v docker >/dev/null 2>&1 && echo yes || echo no") == 'yes'
    snapshot['docker_reclaimable'] = {}
    if snapshot['docker']:
        snapshot['docker_reclaimable'] = docker_reclaimable(
            read("sudo docker system df --format '{{json .}}'"))

    snapshot['apt'] = read("command -v apt-get >/dev/null 2>&1 && echo yes || echo no") == 'yes'
    snapshot['apt_bytes'] = parse_size(
        read("sudo du -sb /var/cache/apt 2>/dev/null | cut -f1") or '0B')
    snapshot['journal_bytes'] = journal_bytes(read('journalctl --disk-usage 2>/dev/null'))

    snapshot['reclaimable'] = sum(snapshot['docker_reclaimable'].values()) + snapshot['apt_bytes']
    return snapshot


def apply_commands(remote, commands):
    outcomes = []
    for command in commands:
        result = remote.run(command)
        outcomes.append({
            'command': command,
            'ok': result.returncode == 0,
            'output': (result.stdout or result.stderr).strip().splitlines()[-1:] or [''],
        })
    return outcomes


def render(vm, snapshot, outcomes, after):
    lines = [f"== {vm['name']} {vm['address']}"]
    if not snapshot.get('reachable'):
        lines.append(f"   UNREACHABLE: {'; '.join(snapshot['errors']) or 'no answer'}")
        return lines
    disk = snapshot['disk']
    lines.append(f"   disk: {size_text(disk['used'])} used, {size_text(disk['avail'])} free")
    if snapshot['docker']:
        parts = [f'{name.lower()} {docker_size_text(value)}'
                 for name, value in sorted(snapshot['docker_reclaimable'].items())]
        lines.append(f"   docker reclaimable: {', '.join(parts) if parts else 'none'}")
    if snapshot['apt']:
        lines.append(f"   apt cache: {size_text(snapshot['apt_bytes'])}"
                     f"   journal: {size_text(snapshot['journal_bytes'])}")
    if not outcomes:
        lines.append(f"   dry run: {docker_size_text(snapshot['reclaimable'])} reclaimable"
                     f" (pass --apply to reclaim)")
        return lines
    for outcome in outcomes:
        mark = 'ok' if outcome['ok'] else 'FAILED'
        lines.append(f"   {mark}: {outcome['command']} ({outcome['output'][0]})")
    if after and after.get('reachable'):
        freed = disk['used'] - after['disk']['used']
        lines.append(f"   freed {size_text(freed)}:"
                     f" {size_text(disk['used'])} -> {size_text(after['disk']['used'])} used,"
                     f" {size_text(after['disk']['avail'])} free")
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--apply', action='store_true',
                        help='run the reclamation (default: report only)')
    parser.add_argument('--images', action='store_true',
                        help='also remove dangling Docker images')
    parser.add_argument('--all-images', action='store_true',
                        help='also remove every unused Docker image (tagged ones too)')
    parser.add_argument('--journal-max', metavar='SIZE',
                        help='vacuum journals to this size (e.g. 100M)')
    parser.add_argument('--only', metavar='NAMES',
                        help='comma-separated subset of the known hosts')
    parser.add_argument('--include-dev', action='store_true',
                        help="include the dev VMs (users' machines)")
    parser.add_argument('--json', action='store_true', help='print the report as JSON')
    parser.add_argument('--ssh-key', default=str(SSH_KEY), help='private key for the VMs')
    args = parser.parse_args()

    key = Path(args.ssh_key).expanduser()
    if not key.exists():
        raise SystemExit(f'trim-vms: no SSH key at {key}')
    if args.all_images:
        args.images = False
    options = args.__dict__

    reports = []
    failed = False
    for vm in select_vms(args.only, args.include_dev):
        remote = Remote(vm, key)
        snapshot = read_snapshot(remote)
        outcomes, after = [], None
        if not snapshot.get('reachable') or snapshot.get('errors'):
            failed = True
        if args.apply and snapshot.get('reachable'):
            outcomes = apply_commands(remote, plan_commands(snapshot, options))
            if any(not outcome['ok'] for outcome in outcomes):
                failed = True
            after = read_snapshot(remote)
            if not after.get('reachable') or after.get('errors'):
                failed = True
        reports.append({'vm': vm, 'snapshot': snapshot, 'outcomes': outcomes, 'after': after})
        if not args.json:
            for line in render(vm, snapshot, outcomes, after):
                print(line)

    if args.json:
        print(json.dumps([
            {'name': report['vm']['name'],
             'address': report['vm']['address'],
             'reachable': report['snapshot'].get('reachable', False),
             'reclaimable_bytes': report['snapshot'].get('reclaimable', 0),
             'freed_bytes': (report['snapshot']['disk']['used'] - report['after']['disk']['used'])
                            if report['after'] and report['after'].get('reachable') else 0,
             'errors': report['snapshot'].get('errors', [])}
            for report in reports], ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
