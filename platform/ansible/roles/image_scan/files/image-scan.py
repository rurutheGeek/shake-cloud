#!/usr/bin/env python3
"""Scan the pinned container images for known vulnerabilities.

`collect` runs on the Ansible controller and lists every image the repository
pins (compose.lock.yaml digests and Dockerfile FROM lines). `run` runs daily on
the scanning host and writes node_exporter textfile metrics:

- Trivy reports CRITICAL vulnerabilities that already have a fixed version in
  the OS packages and language libraries. The package list (SBOM) is made once
  per image digest; later runs only re-match it against the updated database,
  so the registry is contacted only for new digests.
- Official images build PHP/Node.js/Python from source, so those runtimes are
  not packages Trivy can see. Their version is read from the image config
  (PHP_VERSION etc.) and compared with the upstream release list.

Standard library only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
LOCK_IMAGE = re.compile(r'"?image"?\s*:\s*"?([^"\s,]+@sha256:[0-9a-f]{64})"?')
FROM_LINE = re.compile(r'^\s*FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?', re.I | re.M)
MANIFEST_TYPES = ', '.join((
    'application/vnd.oci.image.index.v1+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
    'application/vnd.oci.image.manifest.v1+json',
    'application/vnd.docker.distribution.manifest.v2+json',
))
USER_AGENT = 'shakecloud-image-scan'

# Runtimes the official images install from source. The release lists are the
# projects' own, so a security release shows up the day it is announced.
RUNTIMES = {
    'php': {'env': 'PHP_VERSION', 'url': 'https://www.php.net/releases/active.php'},
    'node': {'env': 'NODE_VERSION', 'url': 'https://nodejs.org/dist/index.json'},
    'python': {'env': 'PYTHON_VERSION', 'url': 'https://endoflife.date/api/python.json'},
}


# --- collect (controller) -------------------------------------------------

def collect(root):
    """Return [{image, sources}] for every pinned image under the repository."""
    root = Path(root)
    found = {}
    for path in sorted(root.glob('**/compose.lock.yaml')):
        if '.git' in path.parts:
            continue
        for image in LOCK_IMAGE.findall(path.read_text(encoding='utf-8')):
            found.setdefault(image, set()).add(str(path.relative_to(root)))
    for path in sorted(root.glob('**/Dockerfile')):
        if '.git' in path.parts:
            continue
        # A named stage (`AS build`) only builds; the unnamed last stage ships.
        for image, stage in FROM_LINE.findall(path.read_text(encoding='utf-8')):
            if not stage and image != 'scratch' and '$' not in image and (':' in image or '@' in image):
                found.setdefault(image, set()).add(str(path.relative_to(root)))
    return [{'image': image, 'sources': sorted(sources)}
            for image, sources in sorted(found.items())]


# --- registry ---------------------------------------------------------------

def parse_ref(ref):
    """Split an image reference into (registry, repository, tag-or-digest)."""
    name, digest = (ref.split('@', 1) + [None])[:2]
    tag = None
    if ':' in name.rsplit('/', 1)[-1]:
        name, tag = name.rsplit(':', 1)
    first = name.split('/', 1)[0]
    if '/' in name and ('.' in first or ':' in first or first == 'localhost'):
        registry, repository = name.split('/', 1)
    else:
        registry, repository = 'registry-1.docker.io', name
        if '/' not in repository:
            repository = 'library/' + repository
    if registry == 'docker.io':
        registry = 'registry-1.docker.io'
    return registry, repository, digest or tag or 'latest'


class Registry:
    """Anonymous pull access through the standard bearer-token challenge."""

    def __init__(self):
        self.tokens = {}

    def get(self, registry, repository, path, accept='*/*'):
        url = f'https://{registry}/v2/{repository}/{path}'
        headers = {'Accept': accept, 'User-Agent': USER_AGENT}
        key = (registry, repository)
        if key in self.tokens:
            headers['Authorization'] = f'Bearer {self.tokens[key]}'
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60)
        except urllib.error.HTTPError as error:
            challenge = error.headers.get('WWW-Authenticate', '')
            if error.code != 401 or key in self.tokens or not challenge.startswith('Bearer '):
                raise
            params = dict(re.findall(r'(\w+)="([^"]*)"', challenge))
            query = {'service': params.get('service', ''),
                     'scope': params.get('scope', f'repository:{repository}:pull')}
            token_url = params['realm'] + '?' + urllib.parse.urlencode(query)
            request = urllib.request.Request(token_url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.load(response)
            self.tokens[key] = data.get('token') or data['access_token']
            return self.get(registry, repository, path, accept)

    def image(self, ref, platform):
        """Return (manifest digest for the platform, image config) of a reference."""
        registry, repository, reference = parse_ref(ref)
        with self.get(registry, repository, f'manifests/{reference}', MANIFEST_TYPES) as response:
            manifest = json.load(response)
            digest = response.headers.get('Docker-Content-Digest')
        if 'manifests' in manifest:
            entry = pick_platform(manifest['manifests'], platform)
            digest = entry['digest']
            with self.get(registry, repository, f'manifests/{digest}', MANIFEST_TYPES) as response:
                manifest = json.load(response)
        with self.get(registry, repository, f"blobs/{manifest['config']['digest']}") as response:
            config = json.load(response)
        return digest, config


def pick_platform(manifests, platform):
    """Choose the wanted os/arch, falling back to the first real image."""
    os_name, arch = platform.split('/')
    usable = [m for m in manifests
              if m.get('platform', {}).get('os') not in (None, 'unknown')]
    for entry in usable:
        if entry['platform'].get('os') == os_name and entry['platform'].get('architecture') == arch:
            return entry
    if not usable:
        raise ValueError('no usable platform in the image index')
    return usable[0]


# --- runtimes -----------------------------------------------------------------

def version_tuple(text):
    return tuple(int(part) for part in re.findall(r'\d+', text)[:3])


def runtime_status(runtime, installed, feed):
    """Return (status, latest) for one runtime version against its release feed.

    status: current, update (a newer patch exists), security (a newer patch is a
    security release), eol (the branch is no longer supported) or unknown.
    """
    mine = version_tuple(installed)
    if len(mine) < 2:
        return 'unknown', ''
    if runtime == 'php':
        branches = {branch: info for group in feed.values() for branch, info in group.items()}
        info = branches.get(f'{mine[0]}.{mine[1]}')
        if info is None:
            return ('eol', '') if mine < max(version_tuple(b) for b in branches) else ('unknown', '')
        latest = info['version']
        if version_tuple(latest) <= mine:
            return 'current', latest
        return ('security' if 'security' in info.get('tags', []) else 'update'), latest
    if runtime == 'node':
        same = [r for r in feed if version_tuple(r['version'])[:1] == mine[:1]]
        if not same:
            return 'unknown', ''
        latest = max(same, key=lambda r: version_tuple(r['version']))['version'].lstrip('v')
        newer = [r for r in same if version_tuple(r['version']) > mine]
        if not newer:
            return 'current', latest
        return ('security' if any(r.get('security') for r in newer) else 'update'), latest
    if runtime == 'python':
        cycle = next((c for c in feed if c['cycle'] == f'{mine[0]}.{mine[1]}'), None)
        if cycle is None:
            return 'unknown', ''
        latest = cycle['latest']
        eol = cycle.get('eol')
        if isinstance(eol, str) and eol <= time.strftime('%Y-%m-%d'):
            return 'eol', latest
        # Python does not tag releases as security-only; a newer patch is an update.
        return ('update' if version_tuple(latest) > mine else 'current'), latest
    return 'unknown', ''


def fetch_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def runtimes_of(config):
    """{runtime: version} from the image config's environment."""
    env = dict(item.split('=', 1) for item in config.get('config', {}).get('Env') or [] if '=' in item)
    return {name: env[spec['env']] for name, spec in RUNTIMES.items() if env.get(spec['env'])}


# --- trivy ----------------------------------------------------------------------

def trivy(binary, cache, *args):
    return subprocess.run([binary, '--quiet', '--cache-dir', str(cache), *args],
                          check=True, capture_output=True, text=True)


def critical_findings(report):
    """[(id, package, installed, fixed)] of CRITICAL, already-fixed vulnerabilities."""
    rows = set()
    for result in report.get('Results') or []:
        for vuln in result.get('Vulnerabilities') or []:
            if vuln.get('Severity') == 'CRITICAL' and vuln.get('FixedVersion'):
                rows.add((vuln['VulnerabilityID'], vuln['PkgName'],
                          vuln.get('InstalledVersion', ''), vuln['FixedVersion']))
    return sorted(rows)


# --- metrics --------------------------------------------------------------------

def label(value):
    return str(value).replace('\\', '\\\\').replace('\n', ' ').replace('"', '\\"')


def short(ref):
    """A readable image name: the repository plus a short digest."""
    name, _, digest = ref.partition('@')
    return f'{name}@{digest[7:19]}' if digest else name


def render(images, started, finished):
    lines = [
        '# HELP shakecloud_image_scan_last_success_timestamp_seconds End of the last image scan.',
        '# TYPE shakecloud_image_scan_last_success_timestamp_seconds gauge',
        f'shakecloud_image_scan_last_success_timestamp_seconds {finished:.0f}',
        '# TYPE shakecloud_image_scan_duration_seconds gauge',
        f'shakecloud_image_scan_duration_seconds {finished - started:.0f}',
        '# TYPE shakecloud_image_scan_images gauge',
        f'shakecloud_image_scan_images {len(images)}',
        '# HELP shakecloud_image_scan_error 1 when an image could not be scanned.',
        '# TYPE shakecloud_image_scan_error gauge',
        '# HELP shakecloud_image_critical_vulnerabilities CRITICAL vulnerabilities with a fixed version.',
        '# TYPE shakecloud_image_critical_vulnerabilities gauge',
        '# HELP shakecloud_image_vulnerability One CRITICAL vulnerability with a fixed version.',
        '# TYPE shakecloud_image_vulnerability gauge',
        '# HELP shakecloud_image_runtime A runtime built into the image and its update status.',
        '# TYPE shakecloud_image_runtime gauge',
    ]
    for item in images:
        base = f'image="{label(short(item["image"]))}",source="{label(item["sources"][0])}"'
        if item.get('error'):
            lines.append(f'shakecloud_image_scan_error{{{base},reason="{label(item["error"])}"}} 1')
            continue
        lines.append(f'shakecloud_image_critical_vulnerabilities{{{base}}} {len(item["critical"])}')
        for vid, pkg, installed, fixed in item['critical']:
            lines.append(f'shakecloud_image_vulnerability{{{base},id="{label(vid)}",package="{label(pkg)}",'
                         f'installed="{label(installed)}",fixed="{label(fixed)}"}} 1')
        for runtime, (installed, status, latest) in sorted(item['runtimes'].items()):
            lines.append(f'shakecloud_image_runtime{{{base},runtime="{runtime}",installed="{label(installed)}",'
                         f'latest="{label(latest)}",status="{status}"}} 1')
    return '\n'.join(lines) + '\n'


def cache_key(ref, platform):
    return hashlib.sha256(f'{ref}|{platform}'.encode()).hexdigest()[:32]


def write_atomic(path, text):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)


# --- run ------------------------------------------------------------------------

def run(config_path):
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    state = Path(config['state_dir'])
    cache = state / 'cache'
    for sub in ('sbom', 'config'):
        (state / sub).mkdir(parents=True, exist_ok=True)
    images = json.loads(Path(config['images']).read_text(encoding='utf-8'))
    platform = config.get('platform', 'linux/amd64')
    binary = config.get('trivy', 'trivy')
    started = time.time()

    trivy(binary, cache, 'image', '--download-db-only', '--skip-version-check')
    feeds = {}
    for name, spec in RUNTIMES.items():
        try:
            feeds[name] = fetch_json(spec['url'])
        except (OSError, ValueError) as error:
            print(f'WARN: release list for {name} unavailable: {error}', file=sys.stderr)
    registry = Registry()

    for item in images:
        ref = item['image']
        try:
            # A pinned digest never changes, so its config and SBOM are kept.
            config_file = state / 'config' / f'{cache_key(ref, platform)}.json'
            if DIGEST.search(ref) and config_file.exists():
                image_config = json.loads(config_file.read_text(encoding='utf-8'))
            else:
                digest, image_config = registry.image(ref, platform)
                image_config['_digest'] = digest
                write_atomic(config_file, json.dumps(image_config))
            registry_name, repository, _ = parse_ref(ref)
            if registry_name == 'registry-1.docker.io':
                registry_name = 'docker.io'
            target = f"{registry_name}/{repository}@{image_config['_digest']}"
            sbom = state / 'sbom' / f"{image_config['_digest'][7:]}.cdx.json"
            if not sbom.exists():
                trivy(binary, cache, 'image', '--skip-db-update', '--skip-version-check',
                      '--image-src', 'remote', '--platform', platform,
                      '--format', 'cyclonedx', '--output', str(sbom), target)
            report = json.loads(trivy(binary, cache, 'sbom', '--skip-db-update', '--skip-java-db-update',
                                      '--skip-version-check', '--scanners', 'vuln',
                                      '--severity', 'CRITICAL', '--ignore-unfixed',
                                      '--format', 'json', str(sbom)).stdout)
            item['critical'] = critical_findings(report)
            item['runtimes'] = {}
            for runtime, installed in runtimes_of(image_config).items():
                status, latest = (runtime_status(runtime, installed, feeds[runtime])
                                  if runtime in feeds else ('unknown', ''))
                item['runtimes'][runtime] = (installed, status, latest)
        except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
            detail = getattr(error, 'stderr', None) or str(error)
            item['error'] = type(error).__name__
            print(f'ERROR: {ref}: {detail.strip()[-500:]}', file=sys.stderr)

    write_atomic(config['textfile'], render(images, started, time.time()))
    # Images no longer pinned in the repository drop out of the cache.
    current = {cache_key(item['image'], platform) for item in images}
    for old in (state / 'config').glob('*.json'):
        if old.stem not in current:
            old.unlink()
    keep = {f"{json.loads(p.read_text())['_digest'][7:]}.cdx.json"
            for p in (state / 'config').glob('*.json')}
    for old in (state / 'sbom').glob('*.cdx.json'):
        if old.name not in keep:
            old.unlink()
    failed = sum(1 for item in images if item.get('error'))
    print(f'OK: scanned {len(images) - failed} images, {failed} failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('collect').add_argument('--root', required=True)
    sub.add_parser('run').add_argument('--config', required=True)
    args = parser.parse_args()
    if args.action == 'collect':
        print(json.dumps(collect(args.root), indent=1))
    else:
        run(args.config)


if __name__ == '__main__':
    main()
