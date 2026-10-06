# -*- coding: utf-8 -*-
"""画面の読み取りクエリ。書き込みは db.call から登録関数へ。"""
from . import db

# ---- 共通 ----------------------------------------------------------------

TITLES_SQL = """
SELECT title_group_id, title_name, generation, region
FROM title_group ORDER BY title_group_id
"""

STATUS_COLUMNS = """
  s.basestats_h AS h, s.basestats_a AS a, s.basestats_b AS b,
  s.basestats_c AS c, s.basestats_d AS d, s.basestats_s AS s
"""


def like(value):
    """ILIKE 用に % と _ を無効化した部分一致パターン。"""
    escaped = (value or '').replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


def titles():
    return db.query(TITLES_SQL)


def latest_title_id():
    row = db.query_one('SELECT max(title_group_id) AS id FROM title_group')
    return row['id'] if row and row['id'] else ''


def types():
    return db.query('SELECT type_id, name FROM type_data ORDER BY type_id')


def egg_groups():
    return db.query('SELECT egg_group_name FROM egg_group ORDER BY egg_group_id')


def ability_names():
    return db.query("""
        SELECT DISTINCT name FROM ability_data ORDER BY name
    """)


def evolution_methods():
    return db.query('SELECT method_id, method_name FROM evolution_method ORDER BY method_name')


def learn_methods():
    return db.query('SELECT method_id, method_name FROM move_learn_method ORDER BY method_id')


def next_ndex():
    row = db.query_one("SELECT coalesce(max(ndex_number::integer), 0) + 1 AS next FROM pokemon_name")
    return row['next'] if row else 1


def species(ndex):
    return db.query_one('SELECT ndex_number, name FROM pokemon_name WHERE ndex_number = %(ndex)s',
                        {'ndex': ndex})


def species_search(q, limit=12):
    pattern = like(q)
    return db.query("""
        SELECT n.ndex_number, n.name
        FROM pokemon_name n
        WHERE %(q)s = '' OR n.name ILIKE %(pattern)s ESCAPE '\\'
           OR n.ndex_number LIKE %(prefix)s
           OR EXISTS (SELECT 1 FROM pokemon_name_alias a
                      WHERE a.ndex_number = n.ndex_number
                        AND a.name_alias ILIKE %(pattern)s ESCAPE '\\')
        ORDER BY n.ndex_number LIMIT %(limit)s
    """, {'q': q, 'pattern': pattern, 'prefix': (q or '') + '%', 'limit': limit})


# ---- ダッシュボード --------------------------------------------------------

def dashboard_stats():
    return db.query_one("""
        SELECT (SELECT count(*) FROM pokemon_name) AS species,
               (SELECT count(*) FROM pokemon_name_form) AS forms,
               (SELECT count(*) FROM pokemon_status) AS status_rows,
               (SELECT count(DISTINCT move_id) FROM move_data) AS moves,
               (SELECT count(DISTINCT ability_id) FROM ability_data) AS abilities,
               (SELECT count(*) FROM pokemon_move_learn) AS learns,
               (SELECT count(*) FROM pokemon_pokedex) AS pokedex_rows,
               (SELECT count(*) FROM pokemon_evolution) AS evolutions,
               (SELECT count(*) FROM title_group) AS titles,
               (SELECT count(*) FROM pokemon_name_alias) AS aliases
    """)


def dashboard_missing():
    return db.query_one("""
        SELECT (SELECT count(*) FROM pokemon_name_form f
                WHERE NOT EXISTS (SELECT FROM pokemon_status s
                                  WHERE s.ndex_number = f.ndex_number AND s.form_id = f.form_id)) AS forms_without_status,
               (SELECT count(*) FROM pokemon_name n
                WHERE NOT EXISTS (SELECT FROM pokemon_pokedex p
                                  WHERE p.ndex_number = n.ndex_number)) AS species_without_pokedex,
               (SELECT count(DISTINCT m.move_id) FROM move_data m
                WHERE NOT EXISTS (SELECT FROM pokemon_move_learn l WHERE l.move_id = m.move_id)) AS moves_without_learns,
               (SELECT count(*) FROM pokemon_name_form f
                WHERE NOT EXISTS (SELECT FROM pokemon_name_alias a
                                  WHERE a.ndex_number = f.ndex_number AND a.form_id = f.form_id)) AS forms_without_alias
    """)


def recent_log(limit=12):
    return db.query("""
        SELECT id, created_at, actor, action, detail
        FROM entry_log ORDER BY id DESC LIMIT %(limit)s
    """, {'limit': limit})


# ---- ポケモン --------------------------------------------------------------

def pokemon_list(q, type_name, region, sort, limit, offset):
    order = {
        'ndex': 'x.ndex_number',
        'ndex_desc': 'x.ndex_number DESC',
        'total': 'x.total DESC, x.ndex_number',
        'name': 'x.name',
    }.get(sort, 'x.ndex_number')
    params = {
        'q': q, 'pattern': like(q), 'prefix': (q or '') + '%',
        'type': type_name, 'region': region, 'limit': limit, 'offset': offset,
    }
    where = """
        (%(q)s = '' OR n.name ILIKE %(pattern)s ESCAPE '\\'
         OR n.ndex_number LIKE %(prefix)s
         OR EXISTS (SELECT 1 FROM pokemon_name_alias a
                    WHERE a.ndex_number = n.ndex_number
                      AND a.name_alias ILIKE %(pattern)s ESCAPE '\\')
         OR EXISTS (SELECT 1 FROM pokemon_name_lang l
                    WHERE l.ndex_number = n.ndex_number
                      AND (l.eng ILIKE %(pattern)s ESCAPE '\\'
                           OR l.kor ILIKE %(pattern)s ESCAPE '\\'
                           OR l.romaji_hepburn ILIKE %(pattern)s ESCAPE '\\')))
        AND (%(type)s = '' OR %(type)s IN (x.type_1, x.type_2))
        AND (%(region)s = '' OR EXISTS (SELECT 1 FROM mv_quiz_status qv
                                        WHERE qv.ndex_number = n.ndex_number AND qv.form_id = '00'
                                          AND qv.region = %(region)s))
    """
    total = db.query_one(f"""
        SELECT count(*) AS count FROM pokemon_name n
        JOIN (SELECT DISTINCT ON (ndex_number) ndex_number, form_id, type_1, type_2
              FROM mv_latest_pokemon_status ORDER BY ndex_number, form_id) x
          ON x.ndex_number = n.ndex_number
        WHERE {where}
    """, params)['count']
    rows = db.query(f"""
        SELECT x.ndex_number, n.name, x.form_id, x.type_1, x.type_2,
               x.h + x.a + x.b + x.c + x.d + x.s AS total,
               (SELECT count(*) FROM pokemon_name_form f WHERE f.ndex_number = n.ndex_number) AS forms,
               (SELECT string_agg(a.name_alias, '、' ORDER BY a.name_alias)
                FROM pokemon_name_alias a WHERE a.ndex_number = n.ndex_number) AS aliases,
               (SELECT count(*) FROM pokemon_status s WHERE s.ndex_number = n.ndex_number) AS history_rows
        FROM pokemon_name n
        JOIN (SELECT DISTINCT ON (ndex_number) ndex_number, form_id, type_1, type_2,
                     basestats_h AS h, basestats_a AS a, basestats_b AS b,
                     basestats_c AS c, basestats_d AS d, basestats_s AS s
              FROM mv_latest_pokemon_status ORDER BY ndex_number, form_id) x
          ON x.ndex_number = n.ndex_number
        WHERE {where}
        ORDER BY {order}
        LIMIT %(limit)s OFFSET %(offset)s
    """, params)
    return rows, total


def pokemon_forms(ndex):
    return db.query("""
        SELECT f.form_id, f.form_name, f.gender,
               p.type_1, p.type_2, p.title_group_id AS latest_title,
               p.basestats_h AS h, p.basestats_a AS a, p.basestats_b AS b,
               p.basestats_c AS c, p.basestats_d AS d, p.basestats_s AS s,
               (SELECT count(*) FROM pokemon_status s
                WHERE s.ndex_number = f.ndex_number AND s.form_id = f.form_id) AS title_rows,
               (SELECT string_agg(a.name_alias, '、' ORDER BY a.name_alias)
                FROM pokemon_name_alias a
                WHERE a.ndex_number = f.ndex_number AND a.form_id = f.form_id) AS aliases,
               (SELECT count(*) FROM pokemon_move_learn l
                WHERE l.ndex_number = f.ndex_number AND l.form_id = f.form_id) AS learn_rows,
               (pk.ndex_number IS NOT NULL) AS has_pokedex
        FROM pokemon_name_form f
        LEFT JOIN mv_latest_pokemon_status p
          ON p.ndex_number = f.ndex_number AND p.form_id = f.form_id
        LEFT JOIN pokemon_pokedex pk
          ON pk.ndex_number = f.ndex_number AND pk.form_id = f.form_id
        WHERE f.ndex_number = %(ndex)s
        ORDER BY f.form_id
    """, {'ndex': ndex})


def pokemon_status_rows(ndex):
    return db.query(f"""
        SELECT s.form_id, s.title_group_id, g.title_name,
               t1.name AS type_1, t2.name AS type_2,
               {STATUS_COLUMNS},
               coalesce((SELECT jsonb_agg(jsonb_build_object('slot', a.slot, 'name', ad.name)
                                          ORDER BY a.slot)
                         FROM pokemon_ability a
                         JOIN ability_data ad ON ad.ability_id = a.ability_id
                                             AND ad.title_group_id = a.title_group_id
                         WHERE a.ndex_number = s.ndex_number AND a.form_id = s.form_id
                           AND a.title_group_id = s.title_group_id), '[]'::jsonb) AS abilities
        FROM pokemon_status s
        JOIN title_group g ON g.title_group_id = s.title_group_id
        JOIN type_data t1 ON t1.type_id = s.type_1_id
        LEFT JOIN type_data t2 ON t2.type_id = s.type_2_id
        WHERE s.ndex_number = %(ndex)s
        ORDER BY s.form_id, s.title_group_id DESC
    """, {'ndex': ndex})


def status_row(ndex, form, title):
    return db.query_one(f"""
        SELECT s.ndex_number, s.form_id, s.title_group_id, g.title_name,
               t1.name AS type_1, t2.name AS type_2,
               {STATUS_COLUMNS},
               (SELECT ad.name FROM pokemon_ability a
                JOIN ability_data ad ON ad.ability_id = a.ability_id
                                    AND ad.title_group_id = a.title_group_id
                WHERE a.ndex_number = s.ndex_number AND a.form_id = s.form_id
                  AND a.title_group_id = s.title_group_id AND a.slot = '1') AS ability_1,
               (SELECT ad.name FROM pokemon_ability a
                JOIN ability_data ad ON ad.ability_id = a.ability_id
                                    AND ad.title_group_id = a.title_group_id
                WHERE a.ndex_number = s.ndex_number AND a.form_id = s.form_id
                  AND a.title_group_id = s.title_group_id AND a.slot = '2') AS ability_2,
               (SELECT ad.name FROM pokemon_ability a
                JOIN ability_data ad ON ad.ability_id = a.ability_id
                                    AND ad.title_group_id = a.title_group_id
                WHERE a.ndex_number = s.ndex_number AND a.form_id = s.form_id
                  AND a.title_group_id = s.title_group_id AND a.slot = 'H') AS ability_h
        FROM pokemon_status s
        JOIN title_group g ON g.title_group_id = s.title_group_id
        JOIN type_data t1 ON t1.type_id = s.type_1_id
        LEFT JOIN type_data t2 ON t2.type_id = s.type_2_id
        WHERE s.ndex_number = %(ndex)s AND s.form_id = %(form)s AND s.title_group_id = %(title)s
    """, {'ndex': ndex, 'form': form, 'title': title})


def form_row(ndex, form):
    return db.query_one("""
        SELECT f.ndex_number, f.form_id, f.form_name, f.gender,
               (SELECT string_agg(a.name_alias, '、' ORDER BY a.name_alias)
                FROM pokemon_name_alias a
                WHERE a.ndex_number = f.ndex_number AND a.form_id = f.form_id) AS aliases
        FROM pokemon_name_form f
        WHERE f.ndex_number = %(ndex)s AND f.form_id = %(form)s
    """, {'ndex': ndex, 'form': form})


def lang_row(ndex, form='00'):
    return db.query_one("""
        SELECT * FROM pokemon_name_lang
        WHERE ndex_number = %(ndex)s AND form_id = %(form)s
    """, {'ndex': ndex, 'form': form})


def rdex_row(ndex, form='00'):
    stored = None if form == '00' else form
    return db.query_one("""
        SELECT * FROM pokemon_rdexnumber
        WHERE ndex_number = %(ndex)s AND coalesce(form_id, '') = coalesce(%(form)s, '')
    """, {'ndex': ndex, 'form': stored})


def pokedex_row(ndex, form='00'):
    return db.query_one("""
        SELECT * FROM pokemon_pokedex
        WHERE ndex_number = %(ndex)s AND form_id = %(form)s
    """, {'ndex': ndex, 'form': form})


def evolution_links(ndex):
    return db.query("""
        SELECT e.before_ndex_number, e.before_form_id, e.after_ndex_number, e.after_form_id,
               e.title_group_id, e.method_id, em.method_name,
               bn.name AS before_species, bf.form_name AS before_form_name,
               an.name AS after_species, af.form_name AS after_form_name,
               tg.title_name
        FROM pokemon_evolution e
        JOIN pokemon_name bn ON bn.ndex_number = e.before_ndex_number
        LEFT JOIN pokemon_name_form bf
          ON bf.ndex_number = e.before_ndex_number AND bf.form_id = e.before_form_id
        JOIN pokemon_name an ON an.ndex_number = e.after_ndex_number
        LEFT JOIN pokemon_name_form af
          ON af.ndex_number = e.after_ndex_number AND af.form_id = e.after_form_id
        LEFT JOIN evolution_method em ON em.method_id = e.method_id
        LEFT JOIN title_group tg ON tg.title_group_id = e.title_group_id
        WHERE e.before_ndex_number = %(ndex)s OR e.after_ndex_number = %(ndex)s
        ORDER BY e.before_ndex_number, e.before_form_id, e.after_ndex_number, e.after_form_id
    """, {'ndex': ndex})


def learnset_rows(ndex, form, title):
    return db.query("""
        SELECT l.learn_id, l.move_id,
               coalesce(m.name, (SELECT mx.name FROM move_data mx WHERE mx.move_id = l.move_id
                                 ORDER BY mx.title_group_id DESC LIMIT 1)) AS move_name,
               l.method_id, ml.method_name,
               l.level_learned_at AS level, l.learn_order,
               l.source_version_group_name AS source, l.notes
        FROM pokemon_move_learn l
        JOIN move_learn_method ml ON ml.method_id = l.method_id
        LEFT JOIN move_data m ON m.move_id = l.move_id AND m.title_group_id = l.title_group_id
        WHERE l.ndex_number = %(ndex)s AND l.form_id = %(form)s AND l.title_group_id = %(title)s
        ORDER BY ml.method_id, l.learn_order NULLS LAST, l.level_learned_at NULLS LAST, m.name
    """, {'ndex': ndex, 'form': form, 'title': title})


def learnset_titles(ndex, form):
    return db.query("""
        SELECT l.title_group_id, g.title_name, count(*) AS rows
        FROM pokemon_move_learn l
        JOIN title_group g ON g.title_group_id = l.title_group_id
        WHERE l.ndex_number = %(ndex)s AND l.form_id = %(form)s
        GROUP BY l.title_group_id, g.title_name
        ORDER BY l.title_group_id DESC
    """, {'ndex': ndex, 'form': form})


def learnset_count(ndex):
    row = db.query_one("""
        SELECT count(*) AS count FROM pokemon_move_learn WHERE ndex_number = %(ndex)s
    """, {'ndex': ndex})
    return row['count'] if row else 0


# ---- わざ ------------------------------------------------------------------

def move_list(q, type_name, category, limit, offset):
    params = {'q': q, 'pattern': like(q), 'type': type_name, 'category': category,
              'limit': limit, 'offset': offset}
    where = """
        (%(q)s = '' OR m.name ILIKE %(pattern)s ESCAPE '\\'
         OR m.english_name ILIKE %(pattern)s ESCAPE '\\')
        AND (%(type)s = '' OR m.type = %(type)s)
        AND (%(category)s = '' OR m.category = %(category)s)
    """
    total = db.query_one(f'SELECT count(DISTINCT m.move_id) AS count FROM move_data m WHERE {where}',
                         params)['count']
    rows = db.query(f"""
        SELECT x.*,
               (SELECT count(DISTINCT (l.ndex_number, l.form_id)) FROM pokemon_move_learn l
                WHERE l.move_id = x.move_id) AS learners,
               (SELECT count(*) FROM move_data m2 WHERE m2.move_id = x.move_id) AS title_rows
        FROM (SELECT DISTINCT ON (m.move_id)
                     m.move_id, m.name, m.english_name, m.type, m.category,
                     m.power, m.accuracy, m.pp, m.priority, m.target, m.effect_chance,
                     m.title_group_id
              FROM move_data m
              WHERE {where}
              ORDER BY m.move_id, m.title_group_id DESC) x
        ORDER BY x.move_id
        LIMIT %(limit)s OFFSET %(offset)s
    """, params)
    return rows, total


def move_detail(move_id):
    latest = db.query_one("""
        SELECT DISTINCT ON (move_id) * FROM move_data
        WHERE move_id = %(move_id)s ORDER BY move_id, title_group_id DESC
    """, {'move_id': move_id})
    if latest is None:
        return None, [], []
    rows = db.query("""
        SELECT m.*, g.title_name,
               (SELECT count(*) FROM pokemon_move_learn l
                WHERE l.move_id = m.move_id AND l.title_group_id = m.title_group_id) AS learners
        FROM move_data m
        LEFT JOIN title_group g ON g.title_group_id = m.title_group_id
        WHERE m.move_id = %(move_id)s
        ORDER BY m.title_group_id DESC
    """, {'move_id': move_id})
    holders = db.query("""
        SELECT DISTINCT l.title_group_id, l.ndex_number, n.name, l.form_id,
               coalesce(f.form_name, '') AS form_name
        FROM pokemon_move_learn l
        JOIN pokemon_name n ON n.ndex_number = l.ndex_number
        LEFT JOIN pokemon_name_form f
          ON f.ndex_number = l.ndex_number AND f.form_id = l.form_id
        WHERE l.move_id = %(move_id)s
        ORDER BY l.title_group_id DESC, l.ndex_number
    """, {'move_id': move_id})
    return latest, rows, holders


def move_row(move_id, title):
    return db.query_one("""
        SELECT m.*, g.title_name FROM move_data m
        LEFT JOIN title_group g ON g.title_group_id = m.title_group_id
        WHERE m.move_id = %(move_id)s AND m.title_group_id = %(title)s
    """, {'move_id': move_id, 'title': title})


# ---- 特性 ------------------------------------------------------------------

def ability_list(q, limit, offset):
    params = {'q': q, 'pattern': like(q), 'limit': limit, 'offset': offset}
    where = "%(q)s = '' OR a.name ILIKE %(pattern)s ESCAPE '\\' OR a.english_name ILIKE %(pattern)s ESCAPE '\\'"
    total = db.query_one(f'SELECT count(DISTINCT a.ability_id) AS count FROM ability_data a WHERE {where}',
                         params)['count']
    rows = db.query(f"""
        SELECT x.*,
               (SELECT count(DISTINCT (p.ndex_number, p.form_id)) FROM pokemon_ability p
                WHERE p.ability_id = x.ability_id) AS holders,
               (SELECT count(*) FROM ability_data a2 WHERE a2.ability_id = x.ability_id) AS title_rows
        FROM (SELECT DISTINCT ON (a.ability_id)
                     a.ability_id, a.name, a.english_name, a.description, a.title_group_id
              FROM ability_data a
              WHERE {where}
              ORDER BY a.ability_id, a.title_group_id DESC) x
        ORDER BY x.name
        LIMIT %(limit)s OFFSET %(offset)s
    """, params)
    return rows, total


def ability_detail(ability_id):
    latest = db.query_one("""
        SELECT DISTINCT ON (ability_id) * FROM ability_data
        WHERE ability_id = %(ability_id)s ORDER BY ability_id, title_group_id DESC
    """, {'ability_id': ability_id})
    if latest is None:
        return None, [], []
    rows = db.query("""
        SELECT a.*, g.title_name
        FROM ability_data a
        LEFT JOIN title_group g ON g.title_group_id = a.title_group_id
        WHERE a.ability_id = %(ability_id)s
        ORDER BY a.title_group_id DESC
    """, {'ability_id': ability_id})
    holders = db.query("""
        SELECT DISTINCT p.title_group_id, p.ndex_number, n.name, p.form_id, p.slot,
               coalesce(f.form_name, '') AS form_name
        FROM pokemon_ability p
        JOIN pokemon_name n ON n.ndex_number = p.ndex_number
        LEFT JOIN pokemon_name_form f
          ON f.ndex_number = p.ndex_number AND f.form_id = p.form_id
        WHERE p.ability_id = %(ability_id)s
        ORDER BY p.title_group_id DESC, p.ndex_number
    """, {'ability_id': ability_id})
    return latest, rows, holders


def ability_row(ability_id, title):
    return db.query_one("""
        SELECT a.*, g.title_name FROM ability_data a
        LEFT JOIN title_group g ON g.title_group_id = a.title_group_id
        WHERE a.ability_id = %(ability_id)s AND a.title_group_id = %(title)s
    """, {'ability_id': ability_id, 'title': title})


# ---- 図鑑情報 --------------------------------------------------------------

def pokedex_list(q, missing_only, limit, offset):
    params = {'q': q, 'pattern': like(q), 'missing': missing_only, 'limit': limit, 'offset': offset}
    where = """
        (%(q)s = '' OR n.name ILIKE %(pattern)s ESCAPE '\\'
         OR f.ndex_number LIKE %(prefix)s)
        AND (%(missing)s = false OR p.ndex_number IS NULL)
    """
    params['prefix'] = (q or '') + '%'
    total = db.query_one(f"""
        SELECT count(*) AS count
        FROM pokemon_name_form f
        JOIN pokemon_name n ON n.ndex_number = f.ndex_number
        LEFT JOIN pokemon_pokedex p ON p.ndex_number = f.ndex_number AND p.form_id = f.form_id
        WHERE {where}
    """, params)['count']
    rows = db.query(f"""
        SELECT f.ndex_number, f.form_id, f.form_name, n.name,
               (p.ndex_number IS NOT NULL) AS filled,
               p.title_group_id, p.category, p.height, p.weight,
               (SELECT count(*) FROM pokemon_status s
                WHERE s.ndex_number = f.ndex_number AND s.form_id = f.form_id) AS title_rows
        FROM pokemon_name_form f
        JOIN pokemon_name n ON n.ndex_number = f.ndex_number
        LEFT JOIN pokemon_pokedex p ON p.ndex_number = f.ndex_number AND p.form_id = f.form_id
        WHERE {where}
        ORDER BY f.ndex_number, f.form_id
        LIMIT %(limit)s OFFSET %(offset)s
    """, params)
    return rows, total


# ---- 作品 ------------------------------------------------------------------

def title_solo_list():
    return db.query("""
        SELECT t.title_id, t.title_name, t.title_group_id, g.title_name AS group_name,
               t.release_year, t.release_month, t.release_date
        FROM title_solo t
        LEFT JOIN title_group g ON g.title_group_id = t.title_group_id
        ORDER BY t.title_id
    """)


# ---- 順位 ------------------------------------------------------------------

def ranking_titles():
    return db.query("""
        SELECT DISTINCT r.title_group_id, g.title_name
        FROM battle_ratematch r
        LEFT JOIN title_group g ON g.title_group_id = r.title_group_id
        ORDER BY r.title_group_id DESC
    """)


def ranking_seasons(title):
    return db.query("""
        SELECT battle_season, battle_type, count(*) AS rows
        FROM battle_ratematch WHERE title_group_id = %(title)s
        GROUP BY battle_season, battle_type
        ORDER BY battle_season DESC, battle_type
    """, {'title': title})


def rankings(title, season, battle_type):
    return db.query("""
        SELECT r.battle_ranking, r.ndex_number, n.name, r.form_id,
               coalesce(f.form_name, '') AS form_name
        FROM battle_ratematch r
        JOIN pokemon_name n ON n.ndex_number = r.ndex_number
        LEFT JOIN pokemon_name_form f
          ON f.ndex_number = r.ndex_number AND f.form_id = r.form_id
        WHERE r.title_group_id = %(title)s AND r.battle_season = %(season)s
          AND r.battle_type = %(type)s
        ORDER BY r.battle_ranking
    """, {'title': title, 'season': season, 'type': battle_type})


def resolve_pokemon_name(name):
    """名前・あだ名から（図鑑番号, フォーム）を1つに決める。曖昧なら候補を返す。"""
    matches = db.query("""
        SELECT f.ndex_number, f.form_id, n.name, coalesce(f.form_name, '') AS form_name
        FROM pokemon_name n
        JOIN pokemon_name_form f ON f.ndex_number = n.ndex_number
        WHERE n.name = %(name)s
        UNION
        SELECT f.ndex_number, f.form_id, n.name, coalesce(f.form_name, '') AS form_name
        FROM pokemon_name_alias a
        JOIN pokemon_name_form f
          ON f.ndex_number = a.ndex_number AND f.form_id = a.form_id
        JOIN pokemon_name n ON n.ndex_number = f.ndex_number
        WHERE a.name_alias = %(name)s
    """, {'name': name})
    return matches


# ---- 履歴 ------------------------------------------------------------------

def history(action, actor, limit, offset):
    params = {'action': action, 'actor': actor, 'limit': limit, 'offset': offset}
    where = "(%(action)s = '' OR action = %(action)s) AND (%(actor)s = '' OR actor = %(actor)s)"
    total = db.query_one(f'SELECT count(*) AS count FROM entry_log WHERE {where}', params)['count']
    rows = db.query(f"""
        SELECT id, created_at, actor, action, detail
        FROM entry_log WHERE {where}
        ORDER BY id DESC LIMIT %(limit)s OFFSET %(offset)s
    """, params)
    return rows, total


def log_row(log_id):
    return db.query_one('SELECT * FROM entry_log WHERE id = %(id)s', {'id': log_id})


def log_actors():
    return db.query('SELECT DISTINCT actor FROM entry_log ORDER BY actor')


# ---- 検索 API --------------------------------------------------------------

def api_moves(q, limit=10):
    return db.query("""
        SELECT move_id, name FROM (
          SELECT DISTINCT ON (move_id) move_id, name FROM move_data
          WHERE (%(q)s = '' OR name ILIKE %(pattern)s ESCAPE '\\')
          ORDER BY move_id, title_group_id DESC) x
        ORDER BY name LIMIT %(limit)s
    """, {'q': q, 'pattern': like(q), 'limit': limit})


def api_abilities(q, limit=10):
    return db.query("""
        SELECT ability_id, name FROM (
          SELECT DISTINCT ON (ability_id) ability_id, name FROM ability_data
          WHERE (%(q)s = '' OR name ILIKE %(pattern)s ESCAPE '\\')
          ORDER BY ability_id, title_group_id DESC) x
        ORDER BY name LIMIT %(limit)s
    """, {'q': q, 'pattern': like(q), 'limit': limit})
