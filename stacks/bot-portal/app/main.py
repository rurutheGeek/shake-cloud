# -*- coding: utf-8 -*-
"""Botポータル: ログ閲覧・再起動・状態・定型操作。

Authentik の forward auth（tls-proxy の Caddy）が付ける Remote-User
ヘッダーを信頼する。127.0.0.1 にしか公開しないので、直接アクセスは
Caddy 経由に限られる。
"""
import csv
import datetime as dt
import io
import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from . import actions, quizlog

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
def detail(request: Request, name: str):
    user = current_user(request)
    service = find(name)
    return render_service(request, user, service)


def render_service(request: Request, user: str, service: actions.Service,
                   result: dict = None, status_code: int = 200):
    state = actions.container_state(service.container)
    return templates.TemplateResponse(
        request, 'service.html',
        {'user': user, 'service': service, 'state': state,
         'revision': actions.git_revision(service.source_dir),
         'buttons': service.action_buttons(),
         'result': result, 'active_tab': 'overview'},
        status_code=status_code)


@app.get('/service/{name}/logs', response_class=HTMLResponse)
def logs_view(request: Request, name: str, tail: int = 200):
    user = current_user(request)
    service = find(name)
    lines = min(max(tail, 10), 1000)
    code, logs = actions.run_command(
        ['docker', 'logs', '--tail', str(lines), '--timestamps', service.container],
        timeout=60)
    if code != 0:
        logs = logs or 'ログを取得できませんでした'
    return templates.TemplateResponse(
        request, 'logs.html',
        {'user': user, 'service': service, 'active_tab': 'logs',
         'state': actions.container_state(service.container),
         'logs': logs, 'tail': lines})


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


@app.get('/service/{name}/logs/download')
def download_logs(request: Request, name: str):
    current_user(request)
    service = find(name)
    code, logs = actions.run_command(
        ['docker', 'logs', '--timestamps', service.container], timeout=120)
    if code != 0:
        raise HTTPException(status_code=502, detail=logs or 'ログを取得できませんでした')
    filename = f'{name}-logs-{dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")}.log'
    return Response(
        content=logs, media_type='text/plain; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.get('/service/{name}/db', response_class=HTMLResponse)
def db_index(request: Request, name: str):
    user = current_user(request)
    service = find(name)
    if not service.db:
        raise HTTPException(status_code=404, detail=f'{name}: db not configured')
    view = actions.db_tables(service)
    return templates.TemplateResponse(
        request, 'db.html',
        {'user': user, 'service': service, 'view': view, 'table': None,
         'needle': '', 'limit': 50, 'offset': 0,
         'active_tab': 'db'})


@app.get('/service/{name}/db/{table}', response_class=HTMLResponse)
def db_table(request: Request, name: str, table: str,
             offset: int = 0, limit: int = 50, q: str = ''):
    user = current_user(request)
    service = find(name)
    if not service.db:
        raise HTTPException(status_code=404, detail=f'{name}: db not configured')
    try:
        view = actions.db_rows(service, table, offset=offset, limit=limit, needle=q)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (OSError, RuntimeError, sqlite3.Error) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return templates.TemplateResponse(
        request, 'db.html',
        {'user': user, 'service': service, 'view': view, 'table': table,
         'needle': q, 'limit': view['limit'], 'offset': view['offset'],
         'active_tab': 'db'})


@app.get('/service/{name}/db/{table}/csv')
def download_db_csv(request: Request, name: str, table: str, q: str = ''):
    current_user(request)
    service = find(name)
    if not service.db:
        raise HTTPException(status_code=404, detail=f'{name}: db not configured')
    try:
        view = actions.db_export(service, table, needle=q)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (OSError, RuntimeError, sqlite3.Error) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(view['header'])
    writer.writerows(view['rows'])
    filename = f'{name}-{table}-{dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")}.csv'
    # BOM付きUTF-8（Excelで開いても日本語が化けない）。
    return Response(
        content='\ufeff' + output.getvalue(), media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'})


def quiz_view(service: actions.Service, quiz: str, days: int, min_answers: int,
              account: str = '') -> dict:
    if not service.db or not service.db.get('quiz_log'):
        raise HTTPException(status_code=404, detail=f'{service.name}: quiz log not configured')
    try:
        return quizlog.report(
            actions.quiz_log_query(service), quiz=quiz, days=days,
            min_answers=min_answers, user=account)
    except (OSError, RuntimeError) as error:
        return {**quizlog.empty_view(days, min_answers, account), 'error': str(error)}


@app.get('/service/{name}/quiz', response_class=HTMLResponse)
def quiz_analysis(request: Request, name: str, quiz: str = '', days: int = quizlog.DEFAULT_DAYS,
                  min_answers: int = quizlog.DEFAULT_MIN_ANSWERS, account: str = ''):
    user = current_user(request)
    service = find(name)
    view = quiz_view(service, quiz, days, min_answers, account)
    return templates.TemplateResponse(
        request, 'quiz.html',
        {'user': user, 'service': service, 'view': view, 'active_tab': 'quiz'})


@app.get('/service/{name}/quiz/csv')
def download_quiz_csv(request: Request, name: str, kind: str, quiz: str = '',
                      days: int = quizlog.DEFAULT_DAYS,
                      min_answers: int = quizlog.DEFAULT_MIN_ANSWERS, account: str = ''):
    current_user(request)
    service = find(name)
    if kind not in quizlog.EXPORTS:
        raise HTTPException(status_code=404, detail=f'unknown export: {kind}')
    view = quiz_view(service, quiz, days, min_answers, account)
    if view.get('error'):
        raise HTTPException(status_code=502, detail=view['error'])
    header, rows = quizlog.export(view, kind)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)
    writer.writerows(rows)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')
    who = f"-{view['user']}" if view.get('user') is not None else ''
    filename = f"{name}-quiz-{view['quiz']}{who}-{quizlog.EXPORTS[kind][0]}-{stamp}.csv"
    return Response(
        content='\ufeff' + output.getvalue(), media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.get('/healthz')
def healthz():
    return {'status': 'ok', 'services': len(SERVICES)}


@app.get('/audit', response_class=HTMLResponse)
def audit_log(request: Request):
    user = current_user(request)
    text = AUDIT.read_text(encoding='utf-8')[-20000:] if AUDIT.exists() else ''
    return templates.TemplateResponse(
        request, 'audit.html', {'user': user, 'audit': text})
