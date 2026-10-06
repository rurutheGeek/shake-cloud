# -*- coding: utf-8 -*-
"""図鑑情報・作品・順位・履歴のページ。"""
from fastapi import APIRouter, Depends, Request

from . import db, queries, web
from .labels import ACTION_LABELS, BATTLE_TYPES
from .parsing import InputError, parse_int, parse_rankings

router = APIRouter(dependencies=[Depends(web.require_csrf)])

PAGE_SIZE = 50
POKEDEX_FIELDS = ['category', 'height', 'weight', 'gender_ratio', 'egg_group_1', 'egg_group_2',
                  'leveling_rate', 'carch_rate', 'evyield_h', 'evyield_a', 'evyield_b',
                  'evyield_c', 'evyield_d', 'evyield_s']


# ---- 図鑑情報 --------------------------------------------------------------

@router.get('/pokedex')
def pokedex_list(request: Request, q: str = '', missing: str = '1', page: int = 1):
    page = max(1, page)
    missing_only = missing == '1'
    rows, total = queries.pokedex_list(q.strip(), missing_only, PAGE_SIZE, (page - 1) * PAGE_SIZE)
    return web.render(request, 'pokedex_list.html', active='pokedex', rows=rows, total=total,
                      page=page, page_size=PAGE_SIZE, q=q, missing=missing)


def _pokedex_values(row, title=''):
    values = web.values_from(row, POKEDEX_FIELDS)
    values['title'] = (row or {}).get('title_group_id') or title or '000'
    return values


@router.get('/pokedex/{ndex}/{form}')
def pokedex_form(request: Request, ndex: str, form: str, restore: int = 0):
    ndex = ndex.zfill(4)
    form = form.zfill(2)
    species = queries.species(ndex)
    form_row = queries.form_row(ndex, form)
    if species is None or form_row is None:
        return web.redirect('/pokedex', err='そのポケモン・姿はありません')
    row = queries.pokedex_row(ndex, form)
    values = _pokedex_values(row)
    if restore:
        values.update(web.values_from(_restore_pokedex(restore), POKEDEX_FIELDS))
    return web.render(request, 'pokedex_form.html', active='pokedex', ndex=ndex, form=form,
                      species=species, form_row=form_row, values=values,
                      egg_groups=[r['egg_group_name'] for r in queries.egg_groups()],
                      titles=queries.titles(), restore=restore or None)


def _restore_pokedex(log_id):
    row = queries.log_row(log_id)
    detail = web.log_detail(row) if row else {}
    if detail.get('entity') != 'pokedex':
        return None
    return detail.get('before')


@router.post('/pokedex/{ndex}/{form}')
async def pokedex_post(request: Request, ndex: str, form: str):
    ndex, form = ndex.zfill(4), form.zfill(2)
    form_data = await request.form()
    value = lambda name: web.field(form_data, name)  # noqa: E731
    values = {key: value(key) for key in POKEDEX_FIELDS}
    values['title'] = value('title')
    try:
        message = db.call('save_pokedex', {
            'p_actor': request.state.actor, 'p_ndex_number': ndex, 'p_form_id': form,
            'p_title_group_id': value('title'), 'p_category': value('category'),
            'p_height': value('height'), 'p_weight': value('weight'),
            'p_gender_ratio': parse_int(value('gender_ratio'), '性別比', 0, 255),
            'p_egg_group_1': value('egg_group_1'), 'p_egg_group_2': value('egg_group_2'),
            'p_leveling_rate': parse_int(value('leveling_rate'), '経験値タイプ', 0, 99),
            'p_carch_rate': parse_int(value('carch_rate'), '被捕獲度', 0, 255),
            'p_ev_h': parse_int(value('evyield_h'), '努力値HP', 0, 255, default=0),
            'p_ev_a': parse_int(value('evyield_a'), '努力値こうげき', 0, 255, default=0),
            'p_ev_b': parse_int(value('evyield_b'), '努力値ぼうぎょ', 0, 255, default=0),
            'p_ev_c': parse_int(value('evyield_c'), '努力値とくこう', 0, 255, default=0),
            'p_ev_d': parse_int(value('evyield_d'), '努力値とくぼう', 0, 255, default=0),
            'p_ev_s': parse_int(value('evyield_s'), '努力値すばやさ', 0, 255, default=0),
        })
    except (InputError, db.DbError) as error:
        return web.render(request, 'pokedex_form.html', active='pokedex', ndex=ndex, form=form,
                          species=queries.species(ndex), form_row=queries.form_row(ndex, form),
                          values=values,
                          egg_groups=[r['egg_group_name'] for r in queries.egg_groups()],
                          titles=queries.titles(), err=str(error))
    return web.redirect('/pokedex', ok=message)


# ---- 作品 ------------------------------------------------------------------

@router.get('/titles')
def titles(request: Request):
    groups = queries.titles()
    return web.render(request, 'titles.html', active='titles', groups=groups,
                      solos=queries.title_solo_list(),
                      title_ids=[row['title_group_id'] for row in groups])


@router.post('/titles/new')
async def title_new(request: Request):
    form_data = await request.form()
    try:
        message = db.call('register_title', {
            'p_actor': request.state.actor,
            'p_title_group_id': web.field(form_data, 'title_group_id'),
            'p_title_name': web.field(form_data, 'title_name'),
            'p_generation': parse_int(web.field(form_data, 'generation'), '世代', 1, 99),
            'p_region': web.field(form_data, 'region'),
        })
    except (InputError, db.DbError) as error:
        return web.redirect('/titles', err=str(error))
    return web.redirect('/titles', ok=message)


@router.post('/titles/{title_id}/edit')
async def title_edit(request: Request, title_id: str):
    form_data = await request.form()
    try:
        message = db.call('update_title', {
            'p_actor': request.state.actor, 'p_title_group_id': title_id,
            'p_title_name': web.field(form_data, 'title_name'),
            'p_generation': parse_int(web.field(form_data, 'generation'), '世代', 1, 99),
            'p_region': web.field(form_data, 'region'),
        })
    except (InputError, db.DbError) as error:
        return web.redirect('/titles', err=str(error))
    return web.redirect('/titles', ok=message)


@router.post('/titles/solo')
async def title_solo_save(request: Request):
    form_data = await request.form()
    try:
        message = db.call('save_title_solo', {
            'p_actor': request.state.actor, 'p_title_id': web.field(form_data, 'title_id'),
            'p_title_name': web.field(form_data, 'title_name'),
            'p_title_group_id': web.field(form_data, 'title_group_id'),
            'p_release_year': parse_int(web.field(form_data, 'release_year'), '発売年', 1900, 2200),
            'p_release_month': parse_int(web.field(form_data, 'release_month'), '発売月', 1, 12),
            'p_release_date': parse_int(web.field(form_data, 'release_date'), '発売日', 1, 31),
        })
    except (InputError, db.DbError) as error:
        return web.redirect('/titles', err=str(error))
    return web.redirect('/titles', ok=message)


# ---- 順位 ------------------------------------------------------------------

@router.get('/rankings')
def rankings(request: Request, title: str = '', season: int = 0, type: str = ''):
    ranking_titles = queries.ranking_titles()
    title = title or (ranking_titles[0]['title_group_id'] if ranking_titles else '')
    seasons = queries.ranking_seasons(title) if title else []
    if not season and seasons:
        season = seasons[0]['battle_season']
        type = type or seasons[0]['battle_type']
    rows = queries.rankings(title, season, type) if title and season and type else []
    return web.render(request, 'rankings.html', active='rankings', ranking_titles=ranking_titles,
                      seasons=seasons, title=title, season=season, type=type, rows=rows)


@router.get('/rankings/import')
def rankings_import_form(request: Request, title: str = '', season: str = '', type: str = ''):
    return web.render(request, 'rankings_import.html', active='rankings',
                      titles=queries.titles(), battle_types=BATTLE_TYPES,
                      title=title or queries.latest_title_id(), season=season, type=type,
                      text='', errors=[], info='')


@router.post('/rankings/import')
async def rankings_import(request: Request):
    form_data = await request.form()
    value = lambda name: web.field(form_data, name)  # noqa: E731
    title, season_text, battle_type = value('title'), value('season'), value('type')
    text = str(form_data.get('text', ''))
    rows, errors = parse_rankings(text)
    if errors:
        return web.render(request, 'rankings_import.html', active='rankings',
                          titles=queries.titles(), battle_types=BATTLE_TYPES,
                          title=title, season=season_text, type=battle_type,
                          text=text, errors=errors, info='')
    # 名前で書かれた行を、図鑑番号とフォームに直す。
    for row in rows:
        if row['ndex']:
            continue
        matches = queries.resolve_pokemon_name(row['name'])
        if not matches:
            errors.append(f"「{row['name']}」が見つかりません")
        elif len({(m['ndex_number'], m['form_id']) for m in matches}) > 1:
            choices = '、'.join(f"{m['ndex_number']}（{m['form_name'] or m['form_id']}）" for m in matches)
            errors.append(f"「{row['name']}」は候補が複数あります: {choices}")
        else:
            row['ndex'], row['form'] = matches[0]['ndex_number'], matches[0]['form_id']
    if errors:
        return web.render(request, 'rankings_import.html', active='rankings',
                          titles=queries.titles(), battle_types=BATTLE_TYPES,
                          title=title, season=season_text, type=battle_type,
                          text=text, errors=errors, info='')
    try:
        season = parse_int(season_text, 'シーズン', 1, 999, required=True)
        message = db.call('import_rankings', {
            'p_actor': request.state.actor, 'p_title_group_id': title,
            'p_battle_season': season, 'p_battle_type': battle_type,
            'p_rows': db.jsonb([{'rank': row['rank'], 'ndex': row['ndex'], 'form': row['form']}
                                for row in rows]),
        })
    except (InputError, db.DbError) as error:
        return web.render(request, 'rankings_import.html', active='rankings',
                          titles=queries.titles(), battle_types=BATTLE_TYPES,
                          title=title, season=season_text, type=battle_type,
                          text=text, errors=[str(error)], info='')
    return web.redirect(f'/rankings?title={title}&season={season}&type={battle_type}', ok=message)


# ---- 履歴 ------------------------------------------------------------------

def _restore_link(item):
    detail = web.log_detail(item['row'])
    before = detail.get('before')
    if not before:
        return None
    log_id = item['row']['id']
    entity = item['entity']
    data = before or {}
    if entity == 'pokemon' and data.get('ndex_number') and data.get('title_group_id'):
        return f"/pokemon/{data['ndex_number']}/status/edit?form={data.get('form_id', '00')}" \
               f"&title={data['title_group_id']}&restore={log_id}"
    if entity == 'pokemon_names' and data.get('ndex_number'):
        return f"/pokemon/{data['ndex_number']}/names?form={data.get('form_id', '00')}&restore={log_id}"
    if entity == 'move' and data.get('move_id') and data.get('title_group_id'):
        return f"/moves/{data['move_id']}/edit?title={data['title_group_id']}&restore={log_id}"
    if entity == 'ability' and data.get('ability_id') and data.get('title_group_id'):
        return f"/abilities/{data['ability_id']}/edit?title={data['title_group_id']}&restore={log_id}"
    if entity == 'pokedex' and data.get('ndex_number'):
        return f"/pokedex/{data['ndex_number']}/{data.get('form_id', '00')}?restore={log_id}"
    if entity == 'rdex' and data.get('ndex_number'):
        return f"/pokemon/{data['ndex_number']}/rdex?form={data.get('form_id', '00')}&restore={log_id}"
    if entity == 'learnset' and detail.get('ndex_number'):
        return (f"/pokemon/{detail['ndex_number']}/learnsets?form={detail.get('form_id', '00')}"
                f"&title={detail.get('title_group_id')}&restore={log_id}")
    return None


@router.get('/history')
def history(request: Request, action: str = '', actor: str = '', page: int = 1):
    page = max(1, page)
    rows, total = queries.history(action, actor, 30, (page - 1) * 30)
    items = web.history_items(rows)
    for item in items:
        item['restore'] = _restore_link(item)
        item['action_label'] = ACTION_LABELS.get(item['row']['action'], item['row']['action'])
    actions = sorted({key for key in ACTION_LABELS} | {row['action'] for row in
                                                       db.query('SELECT DISTINCT action FROM entry_log')})
    return web.render(request, 'history.html', active='history', items=items, total=total,
                      page=page, page_size=30, action=action, actor=actor,
                      actions=actions, actors=[row['actor'] for row in queries.log_actors()])
