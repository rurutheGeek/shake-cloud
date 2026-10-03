#!/usr/bin/env python3
"""Declare the subnet router's control-plane state in the Tailscale console.

The router's own configuration -- the auth key, the advertised route, IP
forwarding -- is the OpenWrt image's job (platform/openwrt/rootfs/; the
subnet router runs on router-01 since 2026-10-03). Two settings that make the
subnet router useful live only in the Tailscale admin console, where a click
leaves no review and no history:

* approving the advertised LAN route, and
* pointing the tailnet's DNS at AdGuard Home, so every device that uses
  Tailscale DNS -- a phone at home or on mobile data -- gets the same ad
  blocking as a LAN client.

This tool reads the current state first, prints what it sees, and on `apply`
writes only the difference. It touches exactly two things: the enabled routes
on the device (add the prefix site.yaml declares) and the tailnet DNS
configuration: AdGuard Home at the LAN gateway is the only global resolver and
`overrideLocalDNS` is true. MagicDNS, split DNS and search paths are sent back
unchanged; it never writes the policy file (`status` summarises it so the admin
can confirm devices may reach the resolver). Split DNS is deliberately not
used: with the resolver behind the subnet route, no suffix mapping is needed.

The DNS preferences endpoint and the configuration endpoint disagree: the
legacy `POST /dns/preferences` silently drops `overrideLocalDNS` and resets
MagicDNS to false when it is omitted. This tool reads and writes the whole
configuration at `/dns/configuration`, which is the shape the admin console
uses.

    sops exec-env platform/sops/tailscale.sops.yaml \
      'python3 tools/tailscale-net.py status'
    sops exec-env platform/sops/tailscale.sops.yaml \
      'python3 tools/tailscale-net.py apply'

After `apply`, a device with accept-dns (Tailscale DNS on) should resolve
public names and internal names alike; `tailscale dns status` shows the
resolver it received.
"""
import argparse
import os
from pathlib import Path
import sys

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'platform/terraform/site.yaml'
API = 'https://api.tailscale.com/api/v2'
TAILNET = '-'  # the tailnet that owns the API token
# 端末の名前。router-01 へ移すときに管理画面の名前を変えた場合はここを直す
HOSTNAME = os.environ.get('TAILSCALE_DEVICE', 'net-01')


class TailscaleError(SystemExit):
    """Any answer that makes the declared state impossible to reach."""


def find_device(devices, hostname):
    """The one device with this hostname, or an error naming the problem.

    Rebuilding the VM creates a second device until the old one is removed;
    enabling routes on the wrong copy would look successful and route nothing.
    """
    matches = [device for device in devices if device.get('hostname') == hostname]
    if not matches:
        raise TailscaleError(f'{hostname} は tailnet に居ません')
    if len(matches) > 1:
        raise TailscaleError(f'{hostname} が{len(matches)}台あります。管理画面で古い端末を消してください')
    return matches[0]


def routes_to_enable(advertised, enabled, prefix):
    """The enabled-route list with the LAN prefix added, or None if it is there.

    The API replaces the whole list, so existing entries are kept. A prefix
    the device does not advertise cannot be enabled: configure it first.
    """
    if prefix not in advertised:
        raise TailscaleError(
            f'端末は {prefix} を広告していません（advertised={advertised}）。'
            ' docs/operations/net.md の手順で先に設定してください')
    if prefix in enabled:
        return None
    return sorted(set(enabled) | {prefix})


def configuration_plan(current, resolver, override=True):
    """The declared DNS configuration, or None when it already matches.

    The tailnet's DNS is one object (global nameservers, split DNS, search
    paths, preferences) and POST replaces all of it, so the parts this tool
    does not own are sent back unchanged. AdGuard is declared as the only
    global resolver: keeping another in the list would let queries escape its
    blocking. Replacement rather than addition is the point.
    """
    desired = dict(current)
    desired['nameservers'] = [{'address': resolver}]
    preferences = dict(current.get('preferences') or {})
    preferences['overrideLocalDNS'] = override
    desired['preferences'] = preferences
    return None if current == desired else desired


def acl_summary(policy):
    """A one-line answer to "may devices reach the resolver?".

    The console now writes the default policy in the `grants` form
    (`{"src": ["*"], "dst": ["*"], "ip": ["*"]}`), older files use `acls` with
    `"*:*"`; both are allow-all. Anything else is left for the admin to read.
    """
    if '*:*' in policy or ('"dst": ["*"]' in policy and '"ip": ["*"]' in policy):
        return 'allow all（既定のポリシー。DNS も許可されている）'
    if ':53' in policy:
        return '宛先 :53 の記述あり（DNS を許可しているか目視で確認）'
    return 'allow all でも :53 でもない（DNS が ACL で止まる可能性）'


class Tailscale:
    def __init__(self, token):
        self.session = requests.Session()
        self.session.headers['Authorization'] = f'Bearer {token}'

    def request(self, method, path, body=None, raw=False):
        response = self.session.request(method, API + path, json=body, timeout=30)
        if response.status_code == 401:
            raise TailscaleError('API トークンが無効か期限切れです（401）。SOPS の値を入れ替えてください')
        if response.status_code >= 400:
            raise TailscaleError(f'{method} {path} HTTP {response.status_code}: {response.text[:300]}')
        return response.text if raw else (response.json() if response.content else {})

    def device(self, hostname=HOSTNAME):
        devices = self.request('GET', f'/tailnet/{TAILNET}/devices')['devices']
        return find_device(devices, hostname)

    def routes(self, device_id):
        return self.request('GET', f'/device/{device_id}/routes')

    def set_routes(self, device_id, routes):
        return self.request('POST', f'/device/{device_id}/routes', {'routes': routes})

    def configuration(self):
        return self.request('GET', f'/tailnet/{TAILNET}/dns/configuration')

    def set_configuration(self, configuration):
        return self.request('POST', f'/tailnet/{TAILNET}/dns/configuration', configuration)

    def policy(self):
        return self.request('GET', f'/tailnet/{TAILNET}/acl', raw=True)


def device_id(device):
    return device.get('nodeId') or device['id']


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('status', 'apply'),
                        help='status は読むだけ、apply は宣言どおりへ寄せる')
    args = parser.parse_args()

    token = os.environ.get('TAILSCALE_API_TOKEN', '')
    if not token:
        raise SystemExit('TAILSCALE_API_TOKEN を環境変数で渡してください（SOPS の .example 参照）')

    site = yaml.safe_load(SITE.read_text(encoding='utf-8'))
    prefix = str(site['network']['prefix'])
    resolver = str(site['network']['gateway'])

    client = Tailscale(token)
    device = client.device()
    routes = client.routes(device_id(device))
    advertised = sorted(routes.get('advertisedRoutes') or [])
    enabled = sorted(routes.get('enabledRoutes') or [])
    configuration = client.configuration()
    nameservers = [entry.get('address') for entry in configuration.get('nameservers') or []]
    preferences = configuration.get('preferences') or {}
    policy = client.policy()

    label = device.get('hostname') or HOSTNAME
    print(f"{label}: {device_id(device)}  {', '.join(device.get('addresses') or [])}")
    print(f"advertised routes: {', '.join(advertised) or '(none)'}")
    print(f"enabled routes:    {', '.join(enabled) or '(none)'}")
    print(f"nameservers:       {', '.join(filter(None, nameservers)) or '(none)'}")
    print(f"overrideLocalDNS:  {preferences.get('overrideLocalDNS')}")
    print(f"magicDNS:          {preferences.get('magicDNS')}")
    print(f"policy file:       {len(policy)} bytes — {acl_summary(policy)}")

    if args.command == 'status':
        return 0

    changes = []
    wanted_routes = routes_to_enable(advertised, enabled, prefix)
    if wanted_routes:
        client.set_routes(device_id(device), wanted_routes)
        changes.append(f'enabled routes -> {wanted_routes}')
    wanted_configuration = configuration_plan(configuration, resolver)
    if wanted_configuration:
        client.set_configuration(wanted_configuration)
        changes.append(f'nameservers -> [{resolver}], overrideLocalDNS -> true（MagicDNS は維持）')

    if changes:
        print('CHANGED:')
        for change in changes:
            print(f'  - {change}')
        print('確認: accept-dns の端末で `tailscale dns status` と '
              '`dig @100.100.100.100 example.com`。スマホは Tailscale を入れ直す')
    else:
        print('OK: すでに宣言どおりです')
    return 0


if __name__ == '__main__':
    sys.exit(main())
