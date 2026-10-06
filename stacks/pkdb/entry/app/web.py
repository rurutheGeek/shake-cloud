# -*- coding: utf-8 -*-
"""テンプレートの共通設定と、画面まわりの小物。"""
import os
import re
import secrets
from pathlib import Path
from urllib.parse import urlencode

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from . import labels
from .parsing import diff_pairs, flatten

CSRF_COOKIE = 'pkdb_csrf'
CSRF_PATTERN = re.compile(r'^[0-9a-f]{32}$')
# Adminer（DBを直接いじる管理者向け画面）。入口ごとに名前が変わるので環境変数で受ける。
ADMINER_URL = os.environ.get('PKDB_ENTRY_ADMINER_URL', '')


async def require_csrf(request: Request):
    """POSTのCSRFを確かめる（各ルーターの依存性として付ける）。

    フォームはここで一度だけ読み、Starlette がキャッシュするので、ルートが
    あとから読んでも同じ内容になる。
    """
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    token = request.cookies.get(CSRF_COOKIE, '')
    if not CSRF_PATTERN.fullmatch(token):
        raise HTTPException(status_code=400, detail='ページを開き直してから、もう一度送ってください')
    form = await request.form()
    if not secrets.compare_digest(token, str(form.get('csrf', ''))):
        raise HTTPException(status_code=400, detail='ページを開き直してから、もう一度送ってください')

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / 'templates'))
templates.env.finalize = lambda value: '' if value is None else value


def _stat_total(row):
    return sum(int(row[key] or 0) for key in ('h', 'a', 'b', 'c', 'd', 's'))


def _stat_pct(value):
    try:
        return max(0, min(100, round(int(value or 0) * 100 / 255)))
    except (TypeError, ValueError):
        return 0


def page_url(request: Request, page: int) -> str:
    """ページャのリンク。入口の名前やスキームに依存しない相対URLにする。"""
    params = dict(request.query_params)
    params['page'] = str(page)
    return '?' + urlencode(params)


templates.env.globals.update(
    STATS=labels.STATS,
    MOVE_CATEGORIES=labels.MOVE_CATEGORIES,
    MOVE_TARGETS=labels.MOVE_TARGETS,
    LEARN_METHODS=labels.LEARN_METHODS,
    LANGUAGES=labels.LANGUAGES,
    GENDERS=labels.GENDERS,
    GENDER_RATIOS=labels.GENDER_RATIOS,
    LEVELING_RATES=labels.LEVELING_RATES,
    RDEX_REGIONS=labels.RDEX_REGIONS,
    BATTLE_TYPES=labels.BATTLE_TYPES,
    ACTION_LABELS=labels.ACTION_LABELS,
    ENTITY_LABELS=labels.ENTITY_LABELS,
    stat_total=_stat_total,
    stat_pct=_stat_pct,
    page_url=page_url,
    type_slug=lambda name: labels.TYPE_SLUGS.get(name, 'unknown'),
    stat_keys=[key for key, _ in labels.STATS],
)


def render(request: Request, name: str, active: str = '', status: int = 200, **context):
    context.setdefault('actor', getattr(request.state, 'actor', ''))
    context.setdefault('ok', request.query_params.get('ok'))
    context.setdefault('err', request.query_params.get('err'))
    context.setdefault('active', active)
    context.setdefault('adminer_url', ADMINER_URL)
    return templates.TemplateResponse(request, name, context, status_code=status)


def redirect(path: str, ok: str | None = None, err: str | None = None):
    params = {}
    if ok:
        params['ok'] = ok
    if err:
        params['err'] = err
    if not params:
        return RedirectResponse(path, status_code=303)
    separator = '&' if '?' in path else '?'
    return RedirectResponse(path + separator + urlencode(params), status_code=303)


def field(form, name: str) -> str:
    return str(form.get(name, '')).strip()


def checkbox(form, name: str) -> bool:
    return form.get(name) in ('1', 'on', 'true')


def values_from(row, fields, prefix=''):
    """DBの行を、入力欄に戻せる文字列の辞書へ。無い項目は空文字。"""
    row = row or {}
    return {name: '' if row.get(name) is None else str(row.get(name)) for name in fields}


def log_detail(row):
    detail = row.get('detail') or {}
    return detail if isinstance(detail, dict) else {}


def summarize_log(row):
    """履歴1行を、一覧に出す短い文にする。"""
    detail = log_detail(row)
    entity = detail.get('entity', '')
    action = row.get('action', '')
    after = detail.get('after')
    before = detail.get('before')
    # learnset の before/after は行の配列なので、要約には使わない。
    data = after if isinstance(after, dict) and after else (before if isinstance(before, dict) else {})
    if action in ('inherit_moves', 'inherit_abilities'):
        return (f"作品 {detail.get('from_title', '')} → {detail.get('to_title', '')}"
                f"（{detail.get('rows', 0)} 件）")
    if action == 'copy_learnset':
        return (f"{detail.get('ndex_number', '')}（フォーム {detail.get('form_id', '')}）"
                f" / 作品 {detail.get('from_title', '')} → {detail.get('to_title', '')}"
                f"（{detail.get('rows', 0)} 件）")
    if action == 'copy_pokemon_status':
        return (f"{detail.get('ndex_number', '')} のフォーム {detail.get('from_form', '')}"
                f"（作品 {detail.get('from_title', '')}）をフォーム "
                f"{'、'.join(detail.get('forms') or []) or '—'}（作品 {detail.get('to_title', '')}）へ"
                f"（{detail.get('copied', 0)} 件）")
    if entity == 'pokemon':
        name = data.get('name') or data.get('ndex_number') or ''
        form = data.get('form_id')
        title = data.get('title_group_id')
        parts = [f"{data.get('ndex_number', '')} {name}".strip()]
        if form:
            parts.append(f'フォーム {form}')
        if title:
            parts.append(f'作品 {title}')
        return ' / '.join(parts)
    if entity == 'pokemon_names':
        return f"{data.get('ndex_number', '')} {data.get('jpn', '')}".strip()
    if entity == 'move':
        return f"わざ {data.get('name', '')}（ID {data.get('move_id', '')}） / 作品 {data.get('title_group_id', '')}"
    if entity == 'ability':
        return f"特性 {data.get('name', '')}（ID {data.get('ability_id', '')}） / 作品 {data.get('title_group_id', '')}"
    if entity == 'title':
        return f"作品 {data.get('title_name', '')}（{data.get('title_group_id', '')}）"
    if entity == 'title_solo':
        return f"作品 {data.get('title_name', '')}（{data.get('title_id', '')}）"
    if entity == 'pokedex':
        return f"{data.get('ndex_number', '')}（フォーム {data.get('form_id', '')}）の図鑑情報"
    if entity == 'rdex':
        return f"{data.get('ndex_number', '')}（フォーム {data.get('form_id', '')}）の地方図鑑番号"
    if entity == 'evolution':
        return (f"{data.get('before_ndex_number', '')}（{data.get('before_form_id', '')}）"
                f" → {data.get('after_ndex_number', '')}（{data.get('after_form_id', '')}）")
    if entity == 'learnset':
        ndex = data.get('ndex_number') or detail.get('ndex_number') or ''
        form = data.get('form_id') or detail.get('form_id') or ''
        title = data.get('title_group_id') or detail.get('title_group_id') or ''
        return f"{ndex}（フォーム {form}） / 作品 {title}"
    if entity == 'rankings':
        return (f"作品 {data.get('title_group_id', '')} シーズン {data.get('battle_season', '')}"
                f"（{data.get('battle_type', '')}）")
    return action


def history_items(rows):
    items = []
    for row in rows:
        detail = log_detail(row)
        pairs = diff_pairs(detail.get('before'), detail.get('after'))
        items.append({
            'row': row,
            'summary': summarize_log(row),
            'entity': detail.get('entity', ''),
            'pairs': pairs,
            'created': row.get('created_at'),
        })
    return items


def flatten_snapshot(value):
    return flatten(value)
