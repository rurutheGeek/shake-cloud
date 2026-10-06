# -*- coding: utf-8 -*-
"""わざと特性のページ。どちらも作品ごとの行を持ち、IDは名前から裏で決まる。"""
from fastapi import APIRouter, Depends, Request

from . import db, queries, web
from .parsing import InputError, parse_int

router = APIRouter(dependencies=[Depends(web.require_csrf)])

PAGE_SIZE = 60
MOVE_FIELDS = ['name', 'english_name', 'type', 'category', 'power', 'accuracy', 'pp',
               'priority', 'target', 'effect_chance', 'description', 'notes']
ABILITY_FIELDS = ['name', 'english_name', 'description']


def _move_values(row):
    return web.values_from(row, MOVE_FIELDS)


def _render_move(request, values, mode, move_id='', error='', restore_id=None, title=''):
    return web.render(request, 'move_form.html', active='moves', mode=mode, values=values,
                      move_id=move_id, title=title, titles=queries.titles(),
                      types=queries.types(), restore_id=restore_id,
                      err=error or request.query_params.get('err'))


def _render_ability(request, values, mode, ability_id='', error='', restore_id=None, title=''):
    return web.render(request, 'ability_form.html', active='abilities', mode=mode,
                      values=values, ability_id=ability_id, title=title,
                      titles=queries.titles(), restore_id=restore_id,
                      err=error or request.query_params.get('err'))


# ---- わざ ------------------------------------------------------------------

@router.get('/moves')
def move_list(request: Request, q: str = '', type: str = '', category: str = '', page: int = 1):
    page = max(1, page)
    rows, total = queries.move_list(q.strip(), type, category, PAGE_SIZE, (page - 1) * PAGE_SIZE)
    return web.render(request, 'moves.html', active='moves', rows=rows, total=total,
                      page=page, page_size=PAGE_SIZE, q=q, type=type, category=category,
                      types=queries.types(), latest_title=queries.latest_title_id())


@router.get('/moves/new')
def move_new(request: Request, name: str = '', type: str = '', category: str = '',
             power: str = '', accuracy: str = '', pp: str = '', title: str = '',
             copy_move: str = '', copy_title: str = '', restore: int = 0):
    title = title or queries.latest_title_id()
    values = {key: '' for key in MOVE_FIELDS}
    values.update({'name': name, 'type': type, 'category': category, 'power': power,
                   'accuracy': accuracy, 'pp': pp})
    if copy_move and copy_title:
        row = queries.move_row(copy_move, copy_title)
        if row:
            values.update(_move_values(row))
            values['name'] = name or values.get('name', '')
    if restore:
        before = queries.log_row(restore)
        detail = web.log_detail(before) if before else {}
        if detail.get('entity') == 'move' and detail.get('before'):
            values.update(web.values_from(detail['before'], MOVE_FIELDS))
    return _render_move(request, values, 'new', restore_id=restore or None)


@router.post('/moves/new')
async def move_new_post(request: Request):
    form_data = await request.form()
    value = lambda name: web.field(form_data, name)  # noqa: E731
    title = value('title')
    values = {key: value(key) for key in MOVE_FIELDS}
    try:
        message = db.call('register_move', {
            'p_actor': request.state.actor, 'p_move_id': '', 'p_name': value('name'),
            'p_title_group_id': title, 'p_english_name': value('english_name'),
            'p_type': value('type'), 'p_category': value('category'),
            'p_power': parse_int(value('power'), '威力', 0, 999),
            'p_accuracy': parse_int(value('accuracy'), '命中率', 0, 999),
            'p_pp': parse_int(value('pp'), 'PP', 0, 999),
            'p_priority': parse_int(value('priority'), '優先度', -10, 10),
            'p_target': value('target'),
            'p_effect_chance': parse_int(value('effect_chance'), '追加効果', 0, 100),
            'p_description': value('description'), 'p_notes': value('notes'),
        })
    except (InputError, db.DbError) as error:
        return _render_move(request, values, 'new', error=str(error))
    return web.redirect('/moves', ok=message)


@router.get('/moves/inherit')
def move_inherit_form(request: Request):
    return web.render(request, 'inherit.html', active='moves', kind='わざ',
                      action='/moves/inherit',
                      titles=queries.titles(), from_title=queries.latest_title_id())


@router.post('/moves/inherit')
async def move_inherit(request: Request):
    form_data = await request.form()
    try:
        message = db.call('inherit_moves', {
            'p_actor': request.state.actor,
            'p_from_title': web.field(form_data, 'from_title'),
            'p_to_title': web.field(form_data, 'to_title'),
            'p_overwrite': web.checkbox(form_data, 'overwrite'),
        })
    except db.DbError as error:
        return web.redirect('/moves/inherit', err=str(error))
    return web.redirect('/moves', ok=message)


@router.get('/moves/{move_id}')
def move_detail(request: Request, move_id: int):
    latest, rows, holders = queries.move_detail(move_id)
    if latest is None:
        return web.redirect('/moves', err=f'わざID {move_id} はありません')
    return web.render(request, 'move_detail.html', active='moves', latest=latest, rows=rows,
                      holders=holders, latest_title=queries.latest_title_id())


@router.get('/moves/{move_id}/edit')
def move_edit(request: Request, move_id: int, title: str = '', copy_title: str = '',
              restore: int = 0):
    row = queries.move_row(move_id, title)
    if row is None:
        return web.redirect('/moves', err=f'わざID {move_id}・作品 {title} の行がありません')
    values = _move_values(row)
    if copy_title:
        source = queries.move_row(move_id, copy_title)
        if source:
            values.update(_move_values(source))
    if restore:
        before = queries.log_row(restore)
        detail = web.log_detail(before) if before else {}
        if detail.get('entity') == 'move' and detail.get('before'):
            values.update(web.values_from(detail['before'], MOVE_FIELDS))
    return _render_move(request, values, 'edit', move_id=str(move_id), title=title,
                        restore_id=restore or None)


@router.post('/moves/{move_id}/edit')
async def move_edit_post(request: Request, move_id: int):
    form_data = await request.form()
    value = lambda name: web.field(form_data, name)  # noqa: E731
    title = value('title')
    values = {key: value(key) for key in MOVE_FIELDS}
    try:
        message = db.call('update_move', {
            'p_actor': request.state.actor, 'p_move_id': str(move_id),
            'p_title_group_id': title, 'p_name': value('name'),
            'p_english_name': value('english_name'), 'p_type': value('type'),
            'p_category': value('category'),
            'p_power': parse_int(value('power'), '威力', 0, 999),
            'p_accuracy': parse_int(value('accuracy'), '命中率', 0, 999),
            'p_pp': parse_int(value('pp'), 'PP', 0, 999),
            'p_priority': parse_int(value('priority'), '優先度', -10, 10),
            'p_target': value('target'),
            'p_effect_chance': parse_int(value('effect_chance'), '追加効果', 0, 100),
            'p_description': value('description'), 'p_notes': value('notes'),
        })
    except (InputError, db.DbError) as error:
        return _render_move(request, values, 'edit', move_id=str(move_id), title=title,
                            error=str(error))
    return web.redirect(f'/moves/{move_id}', ok=message)


@router.post('/moves/{move_id}/delete')
async def move_delete(request: Request, move_id: int):
    form_data = await request.form()
    title = web.field(form_data, 'title')
    try:
        message = db.call('delete_move_title', {
            'p_actor': request.state.actor, 'p_move_id': str(move_id),
            'p_title_group_id': title,
        })
    except db.DbError as error:
        return web.redirect(f'/moves/{move_id}', err=str(error))
    return web.redirect(f'/moves/{move_id}', ok=message)


# ---- 特性 ------------------------------------------------------------------

@router.get('/abilities')
def ability_list(request: Request, q: str = '', page: int = 1):
    page = max(1, page)
    rows, total = queries.ability_list(q.strip(), PAGE_SIZE, (page - 1) * PAGE_SIZE)
    return web.render(request, 'abilities.html', active='abilities', rows=rows, total=total,
                      page=page, page_size=PAGE_SIZE, q=q,
                      latest_title=queries.latest_title_id())


@router.get('/abilities/new')
def ability_new(request: Request, name: str = '', english_name: str = '',
                description: str = '', title: str = '', copy_ability: str = '',
                copy_title: str = '', restore: int = 0):
    title = title or queries.latest_title_id()
    values = {key: '' for key in ABILITY_FIELDS}
    values.update({'name': name, 'english_name': english_name, 'description': description})
    if copy_ability and copy_title:
        row = queries.ability_row(copy_ability, copy_title)
        if row:
            values.update(web.values_from(row, ABILITY_FIELDS))
            values['name'] = name or values.get('name', '')
            values['description'] = description or values.get('description', '')
    if restore:
        row = queries.log_row(restore)
        detail = web.log_detail(row) if row else {}
        if detail.get('entity') == 'ability' and detail.get('before'):
            values.update(web.values_from(detail['before'], ABILITY_FIELDS))
    return _render_ability(request, values, 'new', restore_id=restore or None)


@router.post('/abilities/new')
async def ability_new_post(request: Request):
    form_data = await request.form()
    value = lambda name: web.field(form_data, name)  # noqa: E731
    title = value('title')
    values = {key: value(key) for key in ABILITY_FIELDS}
    try:
        message = db.call('register_ability', {
            'p_actor': request.state.actor, 'p_ability_id': '', 'p_name': value('name'),
            'p_title_group_id': title, 'p_english_name': value('english_name'),
            'p_description': value('description'),
        })
    except db.DbError as error:
        return _render_ability(request, values, 'new', error=str(error))
    return web.redirect('/abilities', ok=message)


@router.get('/abilities/inherit')
def ability_inherit_form(request: Request):
    return web.render(request, 'inherit.html', active='abilities', kind='特性',
                      action='/abilities/inherit',
                      titles=queries.titles(), from_title=queries.latest_title_id())


@router.post('/abilities/inherit')
async def ability_inherit(request: Request):
    form_data = await request.form()
    try:
        message = db.call('inherit_abilities', {
            'p_actor': request.state.actor,
            'p_from_title': web.field(form_data, 'from_title'),
            'p_to_title': web.field(form_data, 'to_title'),
            'p_overwrite': web.checkbox(form_data, 'overwrite'),
        })
    except db.DbError as error:
        return web.redirect('/abilities/inherit', err=str(error))
    return web.redirect('/abilities', ok=message)


@router.get('/abilities/{ability_id}')
def ability_detail(request: Request, ability_id: int):
    latest, rows, holders = queries.ability_detail(ability_id)
    if latest is None:
        return web.redirect('/abilities', err=f'特性ID {ability_id} はありません')
    return web.render(request, 'ability_detail.html', active='abilities', latest=latest,
                      rows=rows, holders=holders, latest_title=queries.latest_title_id())


@router.get('/abilities/{ability_id}/edit')
def ability_edit(request: Request, ability_id: int, title: str = '', restore: int = 0):
    row = queries.ability_row(ability_id, title)
    if row is None:
        return web.redirect('/abilities', err=f'特性ID {ability_id}・作品 {title} の行がありません')
    values = web.values_from(row, ABILITY_FIELDS)
    if restore:
        log = queries.log_row(restore)
        detail = web.log_detail(log) if log else {}
        if detail.get('entity') == 'ability' and detail.get('before'):
            values.update(web.values_from(detail['before'], ABILITY_FIELDS))
    return _render_ability(request, values, 'edit', ability_id=str(ability_id), title=title,
                           restore_id=restore or None)


@router.post('/abilities/{ability_id}/edit')
async def ability_edit_post(request: Request, ability_id: int):
    form_data = await request.form()
    value = lambda name: web.field(form_data, name)  # noqa: E731
    title = value('title')
    values = {key: value(key) for key in ABILITY_FIELDS}
    try:
        message = db.call('update_ability', {
            'p_actor': request.state.actor, 'p_ability_id': str(ability_id),
            'p_title_group_id': title, 'p_name': value('name'),
            'p_english_name': value('english_name'), 'p_description': value('description'),
        })
    except db.DbError as error:
        return _render_ability(request, values, 'edit', ability_id=str(ability_id), title=title,
                               error=str(error))
    return web.redirect(f'/abilities/{ability_id}', ok=message)
