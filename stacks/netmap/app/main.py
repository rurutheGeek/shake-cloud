"""ネットワーク図。開くたびに実機の設定を読み、図と表にする。書き込みは一切しない。"""
import datetime
import ipaddress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import urllib3

from . import checks, model, sources

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HERE = Path(__file__).parent
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount('/static', StaticFiles(directory=HERE / 'static'), name='static')
templates = Jinja2Templates(directory=HERE / 'templates')
SOURCE_LABELS = {'flint': 'Flint 3', 'pve': 'Proxmox', 'netbox': 'NetBox', 'tailscale': 'Tailscale'}


def zone_hosts(state, netbox):
    """Machines per zone: the ledger's names, plus leases the ledger does not know."""
    nets = {z['name']: [ipaddress.ip_network(s) for s in z['subnets']] for z in state['zones']}
    known = {h['address'] for h in netbox.get('hosts', [])}
    entries = [dict(h, source='台帳') for h in netbox.get('hosts', [])]
    entries += [{'address': l['address'], 'name': l['name'] or l['mac'], 'kind': 'lease', 'source': 'DHCP'}
                for l in state['leases'] if l['address'] not in known]
    placed = {name: [] for name in nets}
    for entry in entries:
        try:
            ip = ipaddress.ip_address(entry['address'])
        except ValueError:
            continue
        for name, networks in nets.items():
            if any(ip in n for n in networks):
                placed[name].append(entry)
    for hosts in placed.values():
        hosts.sort(key=lambda h: ipaddress.ip_address(h['address']))
    return placed


@app.get('/healthz', response_class=PlainTextResponse)
def healthz():
    return 'ok'


@app.get('/', response_class=HTMLResponse)
def index(request: Request):
    results, errors = sources.read_all()
    netbox = results.get('netbox', {})
    pve = results.get('pve', {})
    state = model.router(results['flint']) if 'flint' in results else None
    context = {
        'request': request,
        'now': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'errors': {SOURCE_LABELS[k]: v for k, v in errors.items()},
        'state': state,
        'pve': pve,
        'tailscale': results.get('tailscale'),
    }
    if state:
        context.update({
            'hosts': zone_hosts(state, netbox),
            'matrix': model.matrix(state),
            'segments': model.segment_diagram(state),
            'physical': model.physical_diagram(state, netbox.get('cables', []),
                                               pve.get('bridges', []), pve.get('vms', [])),
            'describe_rule': model.describe_rule,
        })
    return templates.TemplateResponse(request, 'index.html', context)


@app.get('/checks', response_class=PlainTextResponse)
def router_checks():
    """Prometheus text for the textfile collector. No answer from the router: no metrics."""
    try:
        dump = sources.flint()
    except Exception as error:  # noqa: BLE001 — the timer leaves the old file and the alert fires on age
        return PlainTextResponse(f'# flint: {type(error).__name__}: {error}'[:300] + '\n', status_code=503)
    return checks.metrics(checks.run(dump))
