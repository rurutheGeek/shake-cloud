#!/usr/bin/env python3
"""Set node firewall options the Terraform provider does not expose.

    python3 node-firewall-options.py --node apextox nf_conntrack_allow_invalid=1

Reads the same environment tools/tf gives the provider: PROXMOX_VE_ENDPOINT,
PROXMOX_VE_INSECURE, and either PROXMOX_VE_USERNAME/PROXMOX_VE_PASSWORD (ticket
authentication) or PROXMOX_VE_API_TOKEN. Idempotent: an option that already has
the wanted value is not written, and every value is read back afterwards, so a
run that exits 0 means the node really has them.

Only the standard library, so it runs wherever terraform does.
"""
import argparse
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--node', required=True)
    parser.add_argument('options', nargs='+', metavar='KEY=VALUE')
    args = parser.parse_args()
    wanted = dict(option.split('=', 1) for option in args.options)

    endpoint = os.environ['PROXMOX_VE_ENDPOINT'].rstrip('/')
    if endpoint.endswith('/api2/json'):
        endpoint = endpoint[:-len('/api2/json')]
    context = ssl.create_default_context()
    if os.environ.get('PROXMOX_VE_INSECURE', '').lower() in ('1', 'true', 'yes'):
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    headers = {}
    if os.environ.get('PROXMOX_VE_PASSWORD'):
        body = urllib.parse.urlencode({'username': os.environ['PROXMOX_VE_USERNAME'],
                                       'password': os.environ['PROXMOX_VE_PASSWORD']}).encode()
        with urllib.request.urlopen(f'{endpoint}/api2/json/access/ticket', body, context=context, timeout=30) as response:
            ticket = json.load(response)['data']
        headers = {'Cookie': f"PVEAuthCookie={urllib.parse.quote(ticket['ticket'])}",
                   'CSRFPreventionToken': ticket['CSRFPreventionToken']}
    else:
        headers = {'Authorization': f"PVEAPIToken={os.environ['PROXMOX_VE_API_TOKEN']}"}

    url = f'{endpoint}/api2/json/nodes/{urllib.parse.quote(args.node)}/firewall/options'

    def current():
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, context=context, timeout=30) as response:
            return json.load(response)['data']

    differing = {key: value for key, value in wanted.items() if str(current().get(key)) != value}
    if differing:
        request = urllib.request.Request(url, urllib.parse.urlencode(differing).encode(), headers=headers, method='PUT')
        with urllib.request.urlopen(request, context=context, timeout=30):
            pass
    after = current()
    wrong = {key: after.get(key) for key, value in wanted.items() if str(after.get(key)) != value}
    if wrong:
        sys.exit(f'node {args.node} firewall options did not take: {wrong}')
    print(f"node {args.node}: {'set' if differing else 'already'} {wanted}")


if __name__ == '__main__':
    main()
