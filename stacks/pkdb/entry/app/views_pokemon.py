# -*- coding: utf-8 -*-
"""ポケモンのページ（一覧・詳細・登録・修正・覚えわざ・進化）。"""
from fastapi import APIRouter, Depends, HTTPException, Request

from . import db, queries, web
from .labels import RDEX_REGIONS
from .parsing import InputError, parse_int, split_aliases

router = APIRouter(dependencies=[Depends(web.require_csrf)])

PAGE_SIZE = 60
STATUS_FIELDS = ['type_1', 'type_2', 'h', 'a', 'b', 'c', 'd', 's',
                 'ability_1', 'ability_2', 'ability_h']
NAME_FIELDS = ['form_id', 'jpn', 'eng', 'fra', 'ger', 'ita', 'kor', 'spa', 'chs', 'cht',
               'romaji_trademarked', 'romaji_hepburn', 'form_name', 'gender', 'aliases']
NEW_FIELDS = ['ndex', 'name', 'form_id', 'form_name', 'gender', 'title', 'english', 'aliases',
              'before', 'before_form', 'evolution_method'] + STATUS_FIELDS


def _ndex(value):
    if not (value or '').isdigit() or not (1 <= int(value) <= 9999):
        raise HTTPException(status_code=404, detail='図鑑番号が不正です')
    return value.zfill(4)


def _form(value):
    if not (value or '').isdigit() or not (0 <= int(value) <= 99):
        raise HTTPException(status_code=404, detail='フォーム番号が不正です')
    return value.zfill(2)


def _blank_status():
    return {key: '' for key in STATUS_FIELDS}


def _status_values(row):
    return web.values_from(row, STATUS_FIELDS)


def _apply_status_snapshot(values, before):
    """履歴の before（種族値・タイプ・特性）を入力欄へ戻す。"""
    if not before:
        return
    for key, value in zip(('h', 'a', 'b', 'c', 'd', 's'), before.get('stats') or []):
        values[key] = '' if value is None else str(value)
    for key in ('type_1', 'type_2'):
        if before.get(key) is not None:
            values[key] = str(before[key])
    abilities = before.get('abilities')
    if isinstance(abilities, dict):
        for slot, key in (('1', 'ability_1'), ('2', 'ability_2'), ('H', 'ability_h')):
            values[key] = abilities.get(slot) or ''
    elif isinstance(abilities, list):
        for key, value in zip(('ability_1', 'ability_2', 'ability_h'), abilities):
            values[key] = value or ''


def _apply_names_snapshot(values, before):
    if not before:
        return
    for key in ('jpn', 'form_name', 'gender'):
        if before.get(key) is not None:
            values[key] = str(before[key])
    for key, value in (before.get('languages') or {}).items():
        if value is not None:
            values[key] = str(value)
    values['aliases'] = '、'.join(before.get('aliases') or [])


def _restore_before(log_id, entity):
    """履歴の before を取り出す。別の種類の履歴なら None。"""
    row = queries.log_row(log_id)
    if row is None:
        return None
    detail = web.log_detail(row)
    if detail.get('entity') != entity:
        return None
    return detail.get('before')


# ---- ダッシュボード --------------------------------------------------------

@router.get('/')
def dashboard(request: Request):
    return web.render(request, 'dashboard.html', active='home',
                      stats=queries.dashboard_stats(),
                      missing=queries.dashboard_missing(),
                      recent=web.history_items(queries.recent_log(15)))


# ---- 一覧 ------------------------------------------------------------------

@router.get('/pokemon')
def pokemon_list(request: Request, q: str = '', type: str = '', region: str = '',
                 sort: str = 'ndex', page: int = 1):
    page = max(1, page)
    rows, total = queries.pokemon_list(q.strip(), type, region, sort,
                                       PAGE_SIZE, (page - 1) * PAGE_SIZE)
    regions = db.query(
        "SELECT DISTINCT region FROM mv_quiz_status WHERE region IS NOT NULL AND region <> '' "
        "ORDER BY region")
    return web.render(request, 'pokemon_list.html', active='pokemon',
                      rows=rows, total=total, page=page, page_size=PAGE_SIZE,
                      q=q, type=type, region=region, sort=sort,
                      types=queries.types(), regions=[r['region'] for r in regions])


# ---- 登録（新しいポケモン・姿・作品の値） ----------------------------------

def _species_form_values(ndex, form, title):
    row = queries.status_row(ndex, form, title)
    values = {key: '' for key in NEW_FIELDS}
    values['ndex'] = ndex
    values['form_id'] = form
    values['title'] = title
    if row:
        values.update(_status_values(row))
    form_row = queries.form_row(ndex, form)
    if form_row:
        values['form_name'] = form_row['form_name'] or ''
        values['gender'] = form_row['gender'] or ''
        values['aliases'] = form_row['aliases'] or ''
    lang = queries.lang_row(ndex, form)
    if lang:
        values['english'] = lang['eng'] or ''
    species = queries.species(ndex)
    if species:
        values['name'] = species['name']
    return values


def _new_mode(ndex, form):
    if queries.species(ndex) is None:
        return 'species'
    if queries.form_row(ndex, form) is None:
        return 'form'
    return 'status'


def _render_new(request, ndex, form, title, values, error='', restore_id=None):
    return web.render(request, 'pokemon_new.html', active='pokemon',
                      mode=_new_mode(ndex, form), values=values,
                      species=queries.species(ndex), titles=queries.titles(),
                      types=queries.types(),
                      ability_names=[row['name'] for row in queries.ability_names()],
                      evolution_methods=queries.evolution_methods(),
                      pokemon=queries.species_search('', 2000),
                      next_ndex=queries.next_ndex(), error=error,
                      restore_id=restore_id, err=error or request.query_params.get('err'))


@router.get('/pokemon/new')
def pokemon_new(request: Request, ndex: str = '', form: str = '', title: str = '',
                copy_ndex: str = '', copy_form: str = '', copy_title: str = '',
                restore: int = 0):
    title = title or queries.latest_title_id()
    ndex = ndex or str(queries.next_ndex())
    form = form or '00'
    if copy_ndex:
        values = _species_form_values(copy_ndex.zfill(4), (copy_form or '00').zfill(2),
                                      copy_title or title)
        values['ndex'] = ndex
        values['form_id'] = form
        values['title'] = title
        values['name'] = ''
        values['english'] = ''
        values['aliases'] = ''
        values['before'] = ''
        values['evolution_method'] = ''
        if ndex == copy_ndex:
            values['name'] = (queries.species(ndex) or {}).get('name', '')
    else:
        values = _species_form_values(ndex, form, title)
    restore_id = None
    if restore:
        before = _restore_before(restore, 'pokemon')
        if before:
            restore_id = restore
            _apply_status_snapshot(values, before)
            for key in ('name', 'form_name', 'gender', 'english'):
                if before.get(key) is not None:
                    values[key] = str(before[key])
            values['aliases'] = '、'.join(before.get('aliases') or [])
    return _render_new(request, ndex, form, title, values, restore_id=restore_id)


@router.post('/pokemon/new')
async def pokemon_new_post(request: Request):
    form_data = await request.form()
    value = lambda name: web.field(form_data, name)  # noqa: E731
    ndex = value('ndex').zfill(4)
    form = value('form_id').zfill(2) or '00'
    title, values = value('title'), {}
    for name in NEW_FIELDS:
        values[name] = value(name)
    values['ndex'], values['form_id'], values['title'] = ndex, form, title
    try:
        stats = {key: parse_int(value(key), {'h': 'HP', 'a': 'こうげき', 'b': 'ぼうぎょ',
                                             'c': 'とくこう', 'd': 'とくぼう',
                                             's': 'すばやさ'}[key], 1, 255, required=True)
                 for key in ('h', 'a', 'b', 'c', 'd', 's')}
        message = db.call('register_pokemon', {
            'p_actor': request.state.actor,
            'p_ndex_number': ndex, 'p_name': value('name'), 'p_form_id': form,
            'p_form_name': value('form_name'), 'p_gender': value('gender'),
            'p_title_group_id': title, 'p_type_1': value('type_1'), 'p_type_2': value('type_2'),
            'p_h': stats['h'], 'p_a': stats['a'], 'p_b': stats['b'],
            'p_c': stats['c'], 'p_d': stats['d'], 'p_s': stats['s'],
            'p_ability_1': value('ability_1'), 'p_ability_2': value('ability_2'),
            'p_ability_h': value('ability_h'), 'p_english_name': value('english'),
            'p_before_ndex_number': value('before'), 'p_before_form_id': value('before_form') or '00',
            'p_evolution_method': value('evolution_method'),
            'p_aliases': split_aliases(value('aliases')),
        })
    except (InputError, db.DbError) as error:
        return _render_new(request, ndex, form, title, values, error=str(error))
    return web.redirect(f'/pokemon/{ndex}', ok=message)


# ---- 詳細 ------------------------------------------------------------------

@router.get('/pokemon/{ndex}')
def pokemon_detail(request: Request, ndex: str):
    ndex = _ndex(ndex)
    species = queries.species(ndex)
    if species is None:
        return web.redirect('/pokemon', err=f'図鑑番号 {ndex} は登録されていません')
    order = {row['form_id']: row for row in queries.pokemon_forms(ndex)}
    statuses = []
    for row in queries.pokemon_status_rows(ndex):
        row = dict(row)
        for ability in row['abilities']:
            row[f"ability_{'H' if ability['slot'] == 'H' else ability['slot']}"] = ability['name']
        statuses.append(row)
    aliases = {}
    alias_rows = db.query(
        'SELECT form_id, name_alias FROM pokemon_name_alias WHERE ndex_number = %(ndex)s '
        'ORDER BY form_id, name_alias', {'ndex': ndex})
    for row in alias_rows:
        aliases.setdefault(row['form_id'], []).append(row['name_alias'])
    languages = queries.lang_row(ndex, '00')
    evolution = queries.evolution_links(ndex)
    pokedex = db.query('SELECT * FROM pokemon_pokedex WHERE ndex_number = %(ndex)s '
                       'ORDER BY form_id', {'ndex': ndex})
    learn_counts = queries.learnset_titles(ndex, '00')
    next_form = max((int(form_id) for form_id in order), default=-1) + 1
    return web.render(request, 'pokemon_detail.html', active='pokemon',
                      ndex=ndex, species=species, forms=list(order.values()),
                      statuses=statuses, aliases=aliases, languages=languages,
                      evolution=evolution, pokedex=pokedex, learn_counts=learn_counts,
                      evolution_methods=queries.evolution_methods(),
                      pokemon=queries.species_search('', 2000),
                      next_form=f'{next_form:02d}',
                      titles=queries.titles(), types=queries.types(),
                      stat_keys=['h', 'a', 'b', 'c', 'd', 's'])


# ---- 作品ごとの値（登録・修正） ------------------------------------------

@router.get('/pokemon/{ndex}/status/new')
def status_new(request: Request, ndex: str, form: str = '00', title: str = '',
               copy_form: str = '', copy_title: str = '', restore: int = 0):
    ndex, form = _ndex(ndex), _form(form or '00')
    species = queries.species(ndex)
    if species is None:
        return web.redirect('/pokemon', err=f'図鑑番号 {ndex} は登録されていません')
    title = title or queries.latest_title_id()
    if queries.status_row(ndex, form, title) is not None:
        return web.redirect(f'/pokemon/{ndex}/status/edit?form={form}&title={title}',
                            err='その作品の値はすでにあります')
    values = _status_values(queries.status_row(ndex, copy_form, copy_title)) if copy_form else _blank_status()
    if restore:
        _apply_status_snapshot(values, _restore_before(restore, 'pokemon'))
    return web.render(request, 'status_form.html', active='pokemon', mode='new',
                      ndex=ndex, species=species, form=form,
                      form_row=queries.form_row(ndex, form), title=title,
                      values=values, titles=queries.titles(), types=queries.types(),
                      ability_names=[row['name'] for row in queries.ability_names()],
                      copy_form=copy_form, copy_title=copy_title, restore=restore or None)


@router.post('/pokemon/{ndex}/status/new')
async def status_new_post(request: Request, ndex: str):
    ndex = _ndex(ndex)
    form_data = await request.form()
    value = lambda name: web.field(form_data, name)  # noqa: E731
    form = value('form_id').zfill(2) or '00'
    title = value('title')
    values = {key: value(key) for key in STATUS_FIELDS}
    species = queries.species(ndex)
    try:
        stats = {key: parse_int(value(key), {'h': 'HP', 'a': 'こうげき', 'b': 'ぼうぎょ',
                                             'c': 'とくこう', 'd': 'とくぼう',
                                             's': 'すばやさ'}[key], 1, 255, required=True)
                 for key in ('h', 'a', 'b', 'c', 'd', 's')}
        message = db.call('register_pokemon', {
            'p_actor': request.state.actor, 'p_ndex_number': ndex,
            'p_name': species['name'] if species else '', 'p_form_id': form,
            'p_form_name': value('form_name'), 'p_gender': value('gender'),
            'p_title_group_id': title, 'p_type_1': value('type_1'), 'p_type_2': value('type_2'),
            'p_h': stats['h'], 'p_a': stats['a'], 'p_b': stats['b'],
            'p_c': stats['c'], 'p_d': stats['d'], 'p_s': stats['s'],
            'p_ability_1': value('ability_1'), 'p_ability_2': value('ability_2'),
            'p_ability_h': value('ability_h'), 'p_english_name': value('english'),
            'p_before_ndex_number': '', 'p_before_form_id': '00', 'p_evolution_method': '',
            'p_aliases': [],
        })
    except (InputError, db.DbError) as error:
        return web.render(request, 'status_form.html', active='pokemon', mode='new',
                          ndex=ndex, species=species, form=form,
                          form_row=queries.form_row(ndex, form), title=title,
                          values=values, titles=queries.titles(), types=queries.types(),
                          ability_names=[row['name'] for row in queries.ability_names()],
                          copy_form='', copy_title='', learn_title=None, err=str(error))
    return web.redirect(f'/pokemon/{ndex}', ok=message)


@router.get('/pokemon/{ndex}/status/edit')
def status_edit(request: Request, ndex: str, form: str = '00', title: str = '',
                restore: int = 0):
    ndex, form = _ndex(ndex), _form(form or '00')
    species = queries.species(ndex)
    row = queries.status_row(ndex, form, title)
    if species is None or row is None:
        return web.redirect(f'/pokemon/{ndex}', err='その作品の値が見つかりません')
    values = _status_values(row)
    if restore:
        _apply_status_snapshot(values, _restore_before(restore, 'pokemon'))
    return web.render(request, 'status_form.html', active='pokemon', mode='edit',
                      ndex=ndex, species=species, form=form,
                      form_row=queries.form_row(ndex, form), title=title,
                      values=values, titles=queries.titles(), types=queries.types(),
                      ability_names=[row['name'] for row in queries.ability_names()],
                      copy_form='', copy_title='', learn_title=row, restore=restore or None)


@router.post('/pokemon/{ndex}/status/edit')
async def status_edit_post(request: Request, ndex: str):
    ndex = _ndex(ndex)
    form_data = await request.form()
    value = lambda name: web.field(form_data, name)  # noqa: E731
    form = value('form_id').zfill(2) or '00'
    title = value('title')
    values = {key: value(key) for key in STATUS_FIELDS}
    species = queries.species(ndex)
    try:
        stats = {key: parse_int(value(key), {'h': 'HP', 'a': 'こうげき', 'b': 'ぼうぎょ',
                                             'c': 'とくこう', 'd': 'とくぼう',
                                             's': 'すばやさ'}[key], 1, 255, required=True)
                 for key in ('h', 'a', 'b', 'c', 'd', 's')}
        message = db.call('update_pokemon', {
            'p_actor': request.state.actor, 'p_ndex_number': ndex, 'p_form_id': form,
            'p_title_group_id': title, 'p_type_1': value('type_1'), 'p_type_2': value('type_2'),
            'p_h': stats['h'], 'p_a': stats['a'], 'p_b': stats['b'],
            'p_c': stats['c'], 'p_d': stats['d'], 'p_s': stats['s'],
            'p_ability_1': value('ability_1'), 'p_ability_2': value('ability_2'),
            'p_ability_h': value('ability_h'),
        })
    except (InputError, db.DbError) as error:
        return web.render(request, 'status_form.html', active='pokemon', mode='edit',
                          ndex=ndex, species=species, form=form,
                          form_row=queries.form_row(ndex, form), title=title,
                          values=values, titles=queries.titles(), types=queries.types(),
                          ability_names=[row['name'] for row in queries.ability_names()],
                          copy_form='', copy_title='', learn_title=None, err=str(error))
    return web.redirect(f'/pokemon/{ndex}', ok=message)


# ---- 名前・各言語名 --------------------------------------------------------

@router.get('/pokemon/{ndex}/names')
def names_form(request: Request, ndex: str, form: str = '00', restore: int = 0):
    ndex, form = _ndex(ndex), _form(form or '00')
    species = queries.species(ndex)
    form_row = queries.form_row(ndex, form)
    if species is None or form_row is None:
        return web.redirect(f'/pokemon/{ndex}', err='その姿が見つかりません')
    lang = queries.lang_row(ndex, form) or {}
    values = web.values_from({**form_row, **lang}, NAME_FIELDS)
    values['jpn'] = species['name']
    values['form_id'] = form
    values['aliases'] = form_row['aliases'] or ''
    if restore:
        _apply_names_snapshot(values, _restore_before(restore, 'pokemon_names'))
    return web.render(request, 'names_form.html', active='pokemon', ndex=ndex, form=form,
                      species=species, form_row=form_row, values=values,
                      restore=restore or None)


@router.post('/pokemon/{ndex}/names')
async def names_post(request: Request, ndex: str):
    ndex = _ndex(ndex)
    form_data = await request.form()
    value = lambda name: web.field(form_data, name)  # noqa: E731
    form = value('form_id').zfill(2) or '00'
    values = {key: value(key) for key in NAME_FIELDS}
    values['aliases'] = value('aliases')
    try:
        message = db.call('update_pokemon_names', {
            'p_actor': request.state.actor, 'p_ndex_number': ndex, 'p_form_id': form,
            'p_jpn': value('jpn'), 'p_eng': value('eng'), 'p_fra': value('fra'),
            'p_ger': value('ger'), 'p_ita': value('ita'), 'p_kor': value('kor'),
            'p_spa': value('spa'), 'p_chs': value('chs'), 'p_cht': value('cht'),
            'p_romaji_trademarked': value('romaji_trademarked'),
            'p_romaji_hepburn': value('romaji_hepburn'),
            'p_form_name': value('form_name'), 'p_gender': value('gender'),
            'p_aliases': split_aliases(value('aliases')),
        })
    except (InputError, db.DbError) as error:
        species = queries.species(ndex)
        return web.render(request, 'names_form.html', active='pokemon', ndex=ndex, form=form,
                          species=species, form_row=queries.form_row(ndex, form),
                          values=values, err=str(error))
    return web.redirect(f'/pokemon/{ndex}', ok=message)


# ---- 地方図鑑番号 ----------------------------------------------------------

@router.get('/pokemon/{ndex}/rdex')
def rdex_form(request: Request, ndex: str, form: str = '00', restore: int = 0):
    ndex, form = _ndex(ndex), _form(form or '00')
    species = queries.species(ndex)
    form_row = queries.form_row(ndex, form)
    if species is None or form_row is None:
        return web.redirect(f'/pokemon/{ndex}', err='その姿が見つかりません')
    row = queries.rdex_row(ndex, form) or {}
    values = web.values_from(row, [key for key, _ in RDEX_REGIONS])
    if restore:
        before = _restore_before(restore, 'rdex')
        if before:
            values.update({key: '' if before.get(key) is None else str(before.get(key))
                           for key in values})
    return web.render(request, 'rdex_form.html', active='pokemon', ndex=ndex, form=form,
                      species=species, form_row=form_row, values=values,
                      restore=restore or None)


@router.post('/pokemon/{ndex}/rdex')
async def rdex_post(request: Request, ndex: str):
    ndex = _ndex(ndex)
    form_data = await request.form()
    form = web.field(form_data, 'form_id').zfill(2) or '00'
    payload = {}
    for key, _ in RDEX_REGIONS:
        text = web.field(form_data, key)
        if text:
            payload[key] = text
    try:
        message = db.call('update_rdex', {
            'p_actor': request.state.actor, 'p_ndex_number': ndex, 'p_form_id': form,
            'p_values': db.jsonb(payload),
        })
    except db.DbError as error:
        species = queries.species(ndex)
        return web.render(request, 'rdex_form.html', active='pokemon', ndex=ndex, form=form,
                          species=species, form_row=queries.form_row(ndex, form),
                          values={key: web.field(form_data, key) for key, _ in RDEX_REGIONS},
                          err=str(error))
    return web.redirect(f'/pokemon/{ndex}', ok=message)


# ---- 覚えわざ --------------------------------------------------------------

def _learnset_rows(form_data):
    indices = set()
    for key in form_data.keys():
        if key.startswith('move_name_'):
            indices.add(key[len('move_name_'):])
    rows, delete_ids = [], []
    for index in sorted(indices):
        learn_id = web.field(form_data, f'learn_id_{index}')
        if web.checkbox(form_data, f'delete_{index}'):
            if learn_id:
                delete_ids.append(int(learn_id))
            continue
        rows.append({
            'learn_id': learn_id,
            'move_name': web.field(form_data, f'move_name_{index}'),
            'method_name': web.field(form_data, f'method_name_{index}'),
            'level': web.field(form_data, f'level_{index}'),
            'learn_order': web.field(form_data, f'learn_order_{index}'),
            'source': web.field(form_data, f'source_{index}'),
            'notes': web.field(form_data, f'notes_{index}'),
        })
    return rows, delete_ids


@router.get('/pokemon/{ndex}/learnsets')
def learnsets(request: Request, ndex: str, form: str = '00', title: str = '',
              restore: int = 0):
    ndex, form = _ndex(ndex), _form(form or '00')
    species = queries.species(ndex)
    if species is None:
        return web.redirect('/pokemon', err=f'図鑑番号 {ndex} は登録されていません')
    title = title or queries.latest_title_id()
    rows = queries.learnset_rows(ndex, form, title)
    if restore:
        before = _restore_before(restore, 'learnset')
        if before:
            rows = before
    return web.render(request, 'learnset.html', active='pokemon', ndex=ndex, species=species,
                      form=form, title=title, rows=rows,
                      titles=queries.titles(), forms=queries.pokemon_forms(ndex),
                      title_rows=queries.learnset_titles(ndex, form),
                      move_names=[row['name'] for row in queries.api_moves('', 2000)],
                      restore=restore or None)


@router.post('/pokemon/{ndex}/learnsets/save')
async def learnsets_save(request: Request, ndex: str):
    ndex = _ndex(ndex)
    form_data = await request.form()
    form = web.field(form_data, 'form_id').zfill(2) or '00'
    title = web.field(form_data, 'title')
    rows, delete_ids = _learnset_rows(form_data)
    try:
        message = db.call('save_learnset', {
            'p_actor': request.state.actor, 'p_ndex_number': ndex, 'p_form_id': form,
            'p_title_group_id': title, 'p_rows': db.jsonb(rows),
            'p_delete_ids': delete_ids,
        })
    except db.DbError as error:
        species = queries.species(ndex)
        return web.render(request, 'learnset.html', active='pokemon', ndex=ndex, species=species,
                          form=form, title=title, rows=rows,
                          titles=queries.titles(), forms=queries.pokemon_forms(ndex),
                          title_rows=queries.learnset_titles(ndex, form),
                          move_names=[row['name'] for row in queries.api_moves('', 2000)],
                          err=str(error))
    return web.redirect(f'/pokemon/{ndex}/learnsets?form={form}&title={title}', ok=message)


@router.post('/pokemon/{ndex}/learnsets/copy')
async def learnsets_copy(request: Request, ndex: str):
    ndex = _ndex(ndex)
    form_data = await request.form()
    form = web.field(form_data, 'form_id').zfill(2) or '00'
    from_title = web.field(form_data, 'from_title')
    to_title = web.field(form_data, 'title')
    overwrite = web.checkbox(form_data, 'overwrite')
    try:
        message = db.call('copy_learnset', {
            'p_actor': request.state.actor, 'p_ndex_number': ndex, 'p_form_id': form,
            'p_from_title': from_title, 'p_to_title': to_title, 'p_overwrite': overwrite,
        })
    except db.DbError as error:
        return web.redirect(f'/pokemon/{ndex}/learnsets?form={form}&title={to_title}',
                            err=str(error))
    return web.redirect(f'/pokemon/{ndex}/learnsets?form={form}&title={to_title}', ok=message)


# ---- 値をまとめて写す ------------------------------------------------------

@router.post('/pokemon/{ndex}/copy-status')
async def copy_status(request: Request, ndex: str):
    ndex = _ndex(ndex)
    form_data = await request.form()
    from_form = web.field(form_data, 'from_form').zfill(2)
    from_title = web.field(form_data, 'from_title')
    to_title = web.field(form_data, 'to_title') or from_title
    to_forms = [value.zfill(2) for value in form_data.getlist('to_forms')]
    overwrite = web.checkbox(form_data, 'overwrite')
    try:
        message = db.call('copy_pokemon_status', {
            'p_actor': request.state.actor, 'p_ndex_number': ndex,
            'p_from_form': from_form, 'p_from_title': from_title,
            'p_to_forms': to_forms, 'p_to_title': to_title, 'p_overwrite': overwrite,
        })
    except db.DbError as error:
        return web.redirect(f'/pokemon/{ndex}', err=str(error))
    return web.redirect(f'/pokemon/{ndex}', ok=message)


# ---- 進化 ------------------------------------------------------------------

@router.post('/pokemon/{ndex}/evolution/set')
async def evolution_set(request: Request, ndex: str):
    ndex = _ndex(ndex)
    form_data = await request.form()
    try:
        message = db.call('set_evolution', {
            'p_actor': request.state.actor,
            'p_before_ndex_number': web.field(form_data, 'before_ndex') or ndex,
            'p_before_form_id': web.field(form_data, 'before_form') or '00',
            'p_after_ndex_number': web.field(form_data, 'after_ndex'),
            'p_after_form_id': web.field(form_data, 'after_form') or '00',
            'p_method_name': web.field(form_data, 'method_name'),
            'p_title_group_id': web.field(form_data, 'title'),
        })
    except db.DbError as error:
        return web.redirect(f'/pokemon/{ndex}', err=str(error))
    return web.redirect(f'/pokemon/{ndex}', ok=message)


@router.post('/pokemon/{ndex}/evolution/delete')
async def evolution_delete(request: Request, ndex: str):
    ndex = _ndex(ndex)
    form_data = await request.form()
    try:
        message = db.call('delete_evolution', {
            'p_actor': request.state.actor,
            'p_before_ndex_number': web.field(form_data, 'before_ndex'),
            'p_before_form_id': web.field(form_data, 'before_form') or '00',
            'p_after_ndex_number': web.field(form_data, 'after_ndex'),
            'p_after_form_id': web.field(form_data, 'after_form') or '00',
        })
    except db.DbError as error:
        return web.redirect(f'/pokemon/{ndex}', err=str(error))
    return web.redirect(f'/pokemon/{ndex}', ok=message)
