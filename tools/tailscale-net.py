#!/usr/bin/env python3
"""Declare the tailnet's control-plane state in the Tailscale console.

The router's own configuration -- the auth key, the advertised route, IP
forwarding -- is the OpenWrt image's job (platform/openwrt/rootfs/; the
subnet router runs on router-01 since 2026-10-03). Two settings that make the
subnet router useful live only in the Tailscale admin console, where a click
leaves no review and no history:

* approving the advertised LAN route, and
* pointing the tailnet's DNS at AdGuard Home, so every device that uses
  Tailscale DNS -- a phone at home or on mobile data -- gets the same ad
  blocking as a LAN client.

So does what decides who may reach whom: the policy file and the tags on the
servers. Both are declared in platform/tailscale/policy.yaml. A server that
loses its tag becomes a person's device again and may reach the whole tailnet
and the LAN behind the subnet router, so a missing tag is reported as loudly
as a changed rule.

This tool reads the current state first, prints what it sees, and on `apply`
writes only the difference. It touches four things: the enabled routes on the
device (add the prefix site.yaml declares), the tailnet DNS configuration
(AdGuard Home at the LAN gateway is the only global resolver and
`overrideLocalDNS` is true; MagicDNS, split DNS and search paths are sent back
unchanged), the policy file (replaced whole, after Tailscale has run the
policy's own `tests`), and the tags of the devices policy.yaml names. Split DNS
is deliberately not used: with the resolver behind the subnet route, no suffix
mapping is needed.

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
import json
import os
from pathlib import Path
import sys

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'platform/terraform/site.yaml'
POLICY = ROOT / 'platform/tailscale/policy.yaml'
API = 'https://api.tailscale.com/api/v2'
TAILNET = '-'  # the tailnet that owns the API token
# subnet router の端末名。管理画面の名前を変えた場合はここを直す
HOSTNAME = os.environ.get('TAILSCALE_DEVICE', 'router-01')


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


def load_declaration(path=POLICY):
    """The declared policy and the tags each named device must carry."""
    declared = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    return declared['policy'], declared.get('devices') or {}


def policy_changes(current, declared):
    """The top-level sections that differ, or [] when the policy matches.

    Only the names are reported: the sections are short enough to read in the
    console, and the point here is to notice that someone edited them there.
    """
    return sorted(key for key in set(current) | set(declared)
                  if (current.get(key) or None) != (declared.get(key) or None))


def tag_changes(devices, declared):
    """[(device, current tags, wanted tags)] for every device that differs.

    A declared device that is missing or duplicated is an error rather than a
    skip: its rules would silently apply to nothing, or to the wrong copy.
    """
    changes = []
    for hostname, wanted in sorted(declared.items()):
        device = find_device(devices, hostname)
        current = sorted(device.get('tags') or [])
        if current != sorted(wanted):
            changes.append((device, current, sorted(wanted)))
    return changes


def undeclared_tags(devices, declared):
    """Tagged devices policy.yaml does not name: someone tagged them by hand."""
    return sorted(device.get('hostname', '?') for device in devices
                  if device.get('tags') and device.get('hostname') not in declared)


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

    def devices(self):
        return self.request('GET', f'/tailnet/{TAILNET}/devices')['devices']

    def set_tags(self, device_id, tags):
        return self.request('POST', f'/device/{device_id}/tags', {'tags': tags})

    def routes(self, device_id):
        return self.request('GET', f'/device/{device_id}/routes')

    def set_routes(self, device_id, routes):
        return self.request('POST', f'/device/{device_id}/routes', {'routes': routes})

    def configuration(self):
        return self.request('GET', f'/tailnet/{TAILNET}/dns/configuration')

    def set_configuration(self, configuration):
        return self.request('POST', f'/tailnet/{TAILNET}/dns/configuration', configuration)

    def policy(self):
        # Accept: application/json returns the policy without its comments,
        # so it compares with the declaration as plain data.
        response = self.session.get(f'{API}/tailnet/{TAILNET}/acl',
                                    headers={'Accept': 'application/json'}, timeout=30)
        if response.status_code >= 400:
            raise TailscaleError(f'GET acl HTTP {response.status_code}: {response.text[:300]}')
        return response.json(), response.headers.get('ETag', '')

    def validate_policy(self, policy):
        """Run the policy's own `tests` on Tailscale's side without applying it."""
        answer = self.request('POST', f'/tailnet/{TAILNET}/acl/validate', policy)
        if answer.get('message') or answer.get('data'):
            raise TailscaleError(
                'ポリシーの検査に失敗しました: ' + json.dumps(answer, ensure_ascii=False)[:1000])

    def set_policy(self, policy, etag):
        # If-Match: 読んだあとに管理画面で編集されていたら上書きしない
        response = self.session.post(f'{API}/tailnet/{TAILNET}/acl', json=policy,
                                     headers={'If-Match': etag} if etag else {}, timeout=30)
        if response.status_code >= 400:
            raise TailscaleError(f'POST acl HTTP {response.status_code}: {response.text[:600]}')


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

    declared_policy, declared_tags = load_declaration()

    client = Tailscale(token)
    devices = client.devices()
    device = find_device(devices, HOSTNAME)
    routes = client.routes(device_id(device))
    advertised = sorted(routes.get('advertisedRoutes') or [])
    enabled = sorted(routes.get('enabledRoutes') or [])
    configuration = client.configuration()
    nameservers = [entry.get('address') for entry in configuration.get('nameservers') or []]
    preferences = configuration.get('preferences') or {}
    policy, etag = client.policy()
    sections = policy_changes(policy, declared_policy)
    tags = tag_changes(devices, declared_tags)

    label = device.get('hostname') or HOSTNAME
    print(f"{label}: {device_id(device)}  {', '.join(device.get('addresses') or [])}")
    print(f"advertised routes: {', '.join(advertised) or '(none)'}")
    print(f"enabled routes:    {', '.join(enabled) or '(none)'}")
    print(f"nameservers:       {', '.join(filter(None, nameservers)) or '(none)'}")
    print(f"overrideLocalDNS:  {preferences.get('overrideLocalDNS')}")
    print(f"magicDNS:          {preferences.get('magicDNS')}")
    print(f"policy file:       {'宣言と違う: ' + ', '.join(sections) if sections else '宣言どおり'}")
    for tagged, current, wanted in tags:
        print(f"tags:              {tagged.get('hostname')}: {current or '(なし)'} -> {wanted}")
    if not tags:
        print('tags:              宣言どおり')
    for hostname in undeclared_tags(devices, declared_tags):
        print(f'tags:              {hostname} は policy.yaml に無いのにタグが付いています')

    if args.command == 'status':
        return 0

    changes = []
    # ポリシーが先。タグは tagOwners に載ってからでないと付けられない。
    if sections:
        client.validate_policy(declared_policy)
        client.set_policy(declared_policy, etag)
        changes.append(f"policy file -> platform/tailscale/policy.yaml（{', '.join(sections)}）")
    for tagged, current, wanted in tags:
        client.set_tags(device_id(tagged), wanted)
        changes.append(f"{tagged.get('hostname')} tags -> {wanted}")
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
