# -*- coding: utf-8 -*-
"""Botポータル: ログ閲覧・再起動・状態・定型操作。

Authentik の forward auth（tls-proxy の Caddy）が付ける Remote-User
ヘッダーを信頼する。127.0.0.1 にしか公開しないので、直接アクセスは
Caddy 経由に限られる。
"""
import datetime as dt
import os
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import actions

BASE = Path(__file__).resolve().parent
REGISTRY = os.environ.get('PORTAL_REGISTRY', str(BASE.parent / 'services.yaml'))
STATE = Path(os.environ.get('PORTAL_STATE', '/app/state'))
AUDIT = STATE / 'audit.log'

app = FastAPI(title='bot-portal')
templates = Jinja2Templates(directory=str(BASE / 'templates'))
SERVICES = {service.name: service for service in actions.load_services(REGISTRY)}


def current_user(request: Request) -> str:
    user = request.headers.get('Remote-User', '')
    if not user.startswith('sso_'):
        raise HTTPException(status_code=401, detail='Authentik forward auth required')
    return user


def audit(user: str, service: str, action: str, code: int):
    STATE.mkdir(parents=True, exist_ok=True)
    line = f'{dt.datetime.now(dt.timezone.utc).isoformat()} {user} {service} {action} rc={code}\n'
    with open(AUDIT, 'a', encoding='utf-8') as file:
        file.write(line)


def find(name: str) -> actions.Service:
    service = SERVICES.get(name)
    if service is None:
        raise HTTPException(status_code=404, detail=f'unknown service: {name}')
    return service


@app.get('/', response_class=HTMLResponse)
def index(request: Request):
    user = current_user(request)
    rows = []
    for service in SERVICES.values():
        rows.append({
            'service': service,
            'state': actions.container_state(service.container),
            'revision': actions.git_revision(service.source_dir),
        })
    return templates.TemplateResponse(
        request, 'index.html', {'user': user, 'rows': rows})


@app.get('/service/{name}', response_class=HTMLResponse)
def detail(request: Request, name: str, tail: int = 200):
    user = current_user(request)
    service = find(name)
    return render_service(request, user, service, tail=tail)


def render_service(request: Request, user: str, service: actions.Service,
                   tail: int = 200, result: dict = None, status_code: int = 200):
    state = actions.container_state(service.container)
    lines = min(max(tail, 10), 1000)
    code, logs = actions.run_command(
        ['docker', 'logs', '--tail', str(lines), '--timestamps', service.container],
        timeout=60)
    if code != 0:
        logs = logs or 'ログを取得できませんでした'
    files = [actions.read_file_view(spec) for spec in service.files]
    return templates.TemplateResponse(
        request, 'service.html',
        {'user': user, 'service': service, 'state': state,
         'revision': actions.git_revision(service.source_dir),
         'buttons': service.action_buttons(), 'files': files,
         'logs': logs, 'tail': lines, 'result': result},
        status_code=status_code)


@app.post('/service/{name}/action', response_class=HTMLResponse)
def do_action(request: Request, name: str, action: str = Form(...), confirm: str = Form('')):
    user = current_user(request)
    service = find(name)
    try:
        command = actions.command_for(service, action)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if action in actions.DANGEROUS_ACTIONS and confirm != 'yes':
        return render_service(request, user, service, result={
            'action': action, 'code': 1,
            'output': '確認チェックが必要です（実行しませんでした）'})

    code, output = actions.run_command(command)
    audit(user, name, action, code)
    return render_service(request, user, service, result={
        'action': action, 'code': code, 'output': output[-4000:]})


@app.post('/service/{name}/debug', response_class=HTMLResponse)
def do_debug(request: Request, name: str, command: str = Form(''), save: str = Form('')):
    user = current_user(request)
    service = find(name)
    if not service.debug:
        raise HTTPException(status_code=400, detail=f'{name}: debug not allowed')
    text = command.strip()
    if not text:
        return render_service(request, user, service, result={
            'action': 'debug', 'code': 1, 'output': 'コマンドが空です'})
    code, output = actions.run_command(
        actions.debug_command(service, save=save == 'yes'),
        timeout=120, stdin=text + '\n')
    audit(user, name, 'debug', code)
    return render_service(request, user, service, result={
        'action': 'debug', 'code': code, 'output': output[-8000:]})


@app.get('/healthz')
def healthz():
    return {'status': 'ok', 'services': len(SERVICES)}


@app.get('/audit', response_class=HTMLResponse)
def audit_log(request: Request):
    user = current_user(request)
    text = AUDIT.read_text(encoding='utf-8')[-20000:] if AUDIT.exists() else ''
    return templates.TemplateResponse(
        request, 'audit.html', {'user': user, 'audit': text})
