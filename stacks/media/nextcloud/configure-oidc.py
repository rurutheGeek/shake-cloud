#!/usr/bin/env python3
"""Connect media-01's Nextcloud to the identity Authentik over native OIDC.

The client id, discovery URL and secret come from the environment so the secret
never lands in a command line: `docker compose exec -e` hands it to the
container and occ reads it by name with `--clientsecret-env`. Re-running the
script reconciles the same provider and keeps the trusted domains already set.
"""
import json
import os
from pathlib import Path
import subprocess
import urllib.parse

ROOT = Path(__file__).resolve().parent
PROVIDER = 'Authentik'
CLIENT_ENV = 'NEXTCLOUD_OIDC_CLIENT_ID'
SECRET_ENV = 'NEXTCLOUD_OIDC_CLIENT_SECRET'
DISCOVERY_ENV = 'NEXTCLOUD_OIDC_DISCOVERY_URL'
ZONE_ENV = 'MEDIA_ZONE'
TRUSTED_PROXY = '127.0.0.1'


def settings():
    """Read the literal KEY=value pairs Compose and this script share."""
    values = {}
    for line in (ROOT / '.env').read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if separator and key.replace('_', '').isalnum():
            values[key] = value
    return values


def media_zone(discovery_url, explicit=''):
    """Return the DNS zone the media names live in.

    `MEDIA_ZONE` wins when the operator sets it; otherwise the discovery URL's
    `auth.<zone>` host is unwrapped. Any other host is taken as the zone so a
    wrong URL cannot silently invent one.
    """
    if explicit.strip():
        return explicit.strip()
    host = urllib.parse.urlsplit(discovery_url).hostname or ''
    labels = host.split('.')
    if labels[0] == 'auth' and len(labels) > 1:
        return '.'.join(labels[1:])
    return host


def config_values(config, key):
    """Return one Nextcloud config array, whether it is list- or map-shaped.

    `occ config:list` renders a PHP array with sequential keys as a JSON list,
    but an array written at index 1 alone comes back as a JSON object with a
    "1" key. Both must compare the same way for the script to stay idempotent.
    """
    raw = config.get(key)
    if isinstance(raw, dict):
        return [str(value) for value in raw.values()]
    return [str(value) for value in (raw or [])]


def next_trusted_domain_index(config, domain):
    """Return the index to add `domain` at, or None when it is already trusted."""
    raw = config.get('trusted_domains')
    if isinstance(raw, dict):
        if domain in (str(value) for value in raw.values()):
            return None
        return max((int(key) for key in raw), default=-1) + 1
    domains = [str(value) for value in (raw or [])]
    return None if domain in domains else len(domains)


def compose(*args, env=None, capture_output=False):
    command = ['docker', 'compose', '--env-file', str(ROOT / '.env'),
               '-f', str(ROOT / 'compose.yaml')]
    if (ROOT / 'compose.lock.yaml').exists():
        command += ['-f', str(ROOT / 'compose.lock.yaml')]
    return subprocess.run(command + list(args), cwd=ROOT, check=True, text=True,
                          env=env, capture_output=capture_output)


def command_env(extra=None):
    environment = dict(os.environ)
    environment.update(settings())
    if extra:
        environment.update(extra)
    return environment


def occ(*args, capture_output=True):
    return compose('exec', '-T', '--user', '33:33', 'nextcloud', 'php', 'occ', *args,
                   env=command_env(), capture_output=capture_output)


def configure_provider(client_id, discovery_url, secret):
    # `-e NEXTCLOUD_OIDC_CLIENT_SECRET` without a value passes the variable from
    # this process environment, so the secret stays out of argv and any log.
    compose('exec', '-T', '--user', '33:33', '-e', SECRET_ENV,
            'nextcloud', 'php', 'occ', 'user_oidc:provider', PROVIDER,
            '--clientid=' + client_id,
            '--clientsecret-env=' + SECRET_ENV,
            '--discoveryuri=' + discovery_url,
            env=command_env({SECRET_ENV: secret}), capture_output=True)
    print(f'CHANGED: Nextcloud OIDC provider {PROVIDER} reconciled')


def configure_trusted(discovery_url, explicit_zone=''):
    """Trust the local TLS gateway and the public Nextcloud name."""
    domain = 'nextcloud.' + media_zone(discovery_url, explicit_zone)
    raw = occ('config:list', 'system', '--output=json').stdout
    config = json.loads(raw).get('system', {})
    proxies = config_values(config, 'trusted_proxies')
    if TRUSTED_PROXY in proxies:
        print(f'OK: trusted proxy {TRUSTED_PROXY}')
    else:
        occ('config:system:set', 'trusted_proxies', '1', '--value=' + TRUSTED_PROXY)
        print(f'CHANGED: trusted proxy {TRUSTED_PROXY}')
    index = next_trusted_domain_index(config, domain)
    if index is None:
        print(f'OK: trusted domain {domain}')
    else:
        occ('config:system:set', 'trusted_domains', str(index), '--value=' + domain)
        print(f'CHANGED: trusted domain added: {domain}')
    # Caddy terminates TLS and forwards http; without this Nextcloud redirects
    # browsers to an http:// URL (which Caddy then upgrades, but the first
    # redirect leaks the scheme and breaks clients that do not follow it).
    if config.get('overwriteprotocol') == 'https':
        print('OK: overwriteprotocol https')
    else:
        occ('config:system:set', 'overwriteprotocol', '--value=https')
        print('CHANGED: overwriteprotocol https')


def main():
    client_id = os.environ.get(CLIENT_ENV, '').strip()
    discovery_url = os.environ.get(DISCOVERY_ENV, '').strip()
    secret = os.environ.get(SECRET_ENV, '')
    if not client_id or not discovery_url or not secret:
        raise SystemExit(f'{CLIENT_ENV}, {DISCOVERY_ENV} and {SECRET_ENV} must be set')
    configure_provider(client_id, discovery_url, secret)
    configure_trusted(discovery_url, os.environ.get(ZONE_ENV, ''))


if __name__ == '__main__':
    main()
