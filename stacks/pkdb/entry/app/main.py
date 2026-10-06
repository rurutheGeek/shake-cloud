# -*- coding: utf-8 -*-
"""ポケモンDBの登録画面（pkdb-entry）。

入口（tls-proxy の Caddy + Authentik forward auth）が付ける Remote-User を
信頼する。127.0.0.1 にしか公開しないので、直接アクセスは Caddy 経由に限られる。
書けるのは pokemondb の登録関数だけで、DBロール pkdb_entry は表へ直接書けない。
"""
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import db, queries, web
from .views_data import router as data_router
from .views_moves import router as moves_router
from .views_pokemon import router as pokemon_router

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s %(message)s')
log = logging.getLogger('pkdb-entry')

BASE = Path(__file__).resolve().parent
CSRF_COOKIE = web.CSRF_COOKIE
CSRF_PATTERN = web.CSRF_PATTERN
PUBLIC_PATHS = {'/healthz'}
# 本番は https の入口だけ。http で試すときは 0 にすると cookie を送れる。
COOKIE_SECURE = os.environ.get('PKDB_ENTRY_COOKIE_SECURE', '1') not in ('0', 'false', 'no')


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.open_pool()
    log.info('pkdb-entry started')
    yield
    db.close_pool()


app = FastAPI(title='pkdb-entry', docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=lifespan)
app.mount('/static', StaticFiles(directory=str(BASE / 'static')), name='static')
app.include_router(pokemon_router)
app.include_router(moves_router)
app.include_router(data_router)


@app.middleware('http')
async def security(request: Request, call_next):
    """入口が付ける Remote-User を確かめ、CSRFトークンのcookieを用意する。

    POSTのCSRF照合は、フォームを二重に読まないよう、各ルーターの依存性
    （app.web.require_csrf）がルートと同じ Request で行う。
    """
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith('/static/'):
        return await call_next(request)
    remote = request.headers.get('remote-user', '')
    if not remote.startswith('sso_'):
        return PlainTextResponse('Authentik の入口から開いてください', status_code=401)
    request.state.actor = remote[4:] or 'unknown'
    token = request.cookies.get(CSRF_COOKIE, '')
    if not CSRF_PATTERN.fullmatch(token):
        token = secrets.token_hex(16)
        request.state.new_token = token
    request.state.csrf = token
    response = await call_next(request)
    if getattr(request.state, 'new_token', None):
        response.set_cookie(CSRF_COOKIE, request.state.new_token, path='/',
                            secure=COOKIE_SECURE, httponly=True, samesite='strict')
    return response


@app.get('/healthz')
def healthz():
    if not db.healthy():
        return JSONResponse({'ok': False}, status_code=503)
    return {'ok': True}


@app.get('/api/search')
def api_search(q: str = ''):
    term = q.strip()
    if not term:
        return {'pokemon': [], 'moves': [], 'abilities': []}
    return {
        'pokemon': queries.species_search(term),
        'moves': queries.api_moves(term),
        'abilities': queries.api_abilities(term),
    }


@app.exception_handler(HTTPException)
async def http_error(request: Request, error: HTTPException):
    from .web import render
    return render(request, 'error.html', status=error.status_code, title='エラー',
                  detail=error.detail or '')


@app.exception_handler(Exception)
async def unhandled(request: Request, error: Exception):
    log.exception('pkdb-entry: unhandled error on %s', request.url.path)
    from .web import render
    return render(request, 'error.html', status=500, title='処理できませんでした',
                  detail='時間をおいて開き直してください')
