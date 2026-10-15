"""Compare the router's live config with what apply-segments sets.

GL.iNet's own scripts rewrite parts of the config whenever Tailscale restarts
(gl_tailscale runs `tailscale up --reset`, firewall.tailscale.sh deletes the
forwardings its UI does not know) and firmware updates replace them again.
Each check is one line of Prometheus text so a drift raises an alert.
"""
import json

from . import model, uci

ROUTES = ('192.168.10.0/24', '192.168.40.0/24')


def forwarding(firewall, src, dest):
    return any(f.get('src') == src and f.get('dest') == dest and f.get('enabled') != '0'
               for f in uci.of_type(firewall, 'forwarding'))


def advertised(text):
    """The AdvertiseRoutes list (a JSON array) that netmap-dump prints."""
    try:
        return set(json.loads(text or '[]') or [])
    except ValueError:
        return set()


def run(dump):
    parts = model.split_dump(dump)
    configs = uci.parse(parts.get('uci', ''))
    firewall = configs.get('firewall', {})
    settings = configs.get('tailscale', {}).get('settings', {})
    routes = advertised(parts.get('tailscale-routes'))
    return {
        'tailscale_to_lan': forwarding(firewall, 'tailscale', 'lan'),
        'tailscale_to_personal': forwarding(firewall, 'tailscale', 'personal'),
        'tailscale_lan_enabled': settings.get('lan_enabled') == '1',
        **{f'advertise_{route}': route in routes for route in ROUTES},
    }


def metrics(results):
    lines = ['# HELP shakecloud_router_check 1 when the Flint 3 setting matches apply-segments.',
             '# TYPE shakecloud_router_check gauge']
    lines += [f'shakecloud_router_check{{check="{name}"}} {int(ok)}' for name, ok in sorted(results.items())]
    return '\n'.join(lines) + '\n'
