"""ポケモン用語辞書（dictionary.json）を作る。

PokéAPI の多言語CSVから作る公式名に、Git 管理の ``custom-terms.json``
（俗称・対戦用語・除外語）を重ねる。照合と翻訳は ``core/poketr.js`` が行い、
翻訳サイトと拡張機能はこのモジュールが書き出した辞書を読むだけにする。
"""
import csv
import io
import unicodedata
import urllib.request

POKEAPI_CSV = 'https://raw.githubusercontent.com/PokeAPI/pokeapi/{ref}/data/v2/csv/{name}.csv'

# PokéAPI の local_language_id → このツールの言語コード。
# 日本語はかな表記（1）を正、漢字表記（11）を別名として扱う。
LANGUAGES = {1: 'ja', 11: 'ja', 9: 'en', 3: 'ko', 4: 'zh-TW', 12: 'zh-CN',
             5: 'fr', 6: 'de', 7: 'es', 8: 'it'}
# 種別の並びは poketr.js の KINDS（同名のときの優先順）と揃える。
KINDS = [('species', 'pokemon_species_names', 'pokemon_species_id'),
         ('move', 'move_names', 'move_id'),
         ('ability', 'ability_names', 'ability_id'),
         ('item', 'item_names', 'item_id'),
         ('type', 'type_names', 'type_id'),
         ('nature', 'nature_names', 'nature_id'),
         ('location', 'location_names', 'location_id'),
         ('form', 'pokemon_form_names', 'pokemon_form_id'),
         ('stat', 'stat_names', 'stat_id')]
# 名前以外に、海外サイト式のフォーム表記（Landorus-Therian）を作るための表。
EXTRA_TABLES = ['pokemon_forms', 'pokemon']
# 命中・回避などはステータス欄の略記として出てこないので取り込まない。
STATS = {'1', '2', '3', '4', '5', '6'}
TYPE_PHRASES = [(('immunity', 'immunities'), '無効'),
                (('resistance', 'resistances', 'resist', 'resists'), '耐性'),
                (('weakness', 'weaknesses'), '弱点'),
                (('move', 'moves', 'attack', 'attacks'), '技'),
                (('STAB',), 'タイプ一致技'),
                (('coverage',), '技の範囲')]


def _add(entries, key, language, name):
    name = name.strip()
    if not name:
        return
    names = entries.setdefault(key, {}).setdefault(language, [])
    # 「メガリザードンＸ」のような全角英数も半角の書き方で拾えるようにする。
    for variant in (name, unicodedata.normalize('NFKC', name)):
        if variant not in names:
            names.append(variant)


def _form_name(row):
    """フォームは「メガリザードンX」「Alolan Rattata」のような完全名だけを使う。

    日本語は pokemon_name が空で form_name に完全名が入る（メガ・ゲンシ）か、
    「アローラのすがた」のような部分名だけのことがある。部分名は拾わない。
    """
    if row.get('pokemon_name'):
        return row['pokemon_name']
    if row['form_name'].startswith(('メガ', 'ゲンシ')):
        return row['form_name']
    return ''


def parse_csvs(tables):
    """``{csv名: 本文}`` から ``{kind:id: {言語: [名前…]}}`` を作る。"""
    entries = {}
    for kind, table, column in KINDS:
        rows = sorted(csv.DictReader(io.StringIO(tables[table])),
                      # ja-Hrkt(1) を ja(11) より先にして、かなを正の表記にする。
                      key=lambda row: int(row['local_language_id']) != 1)
        for row in rows:
            language = LANGUAGES.get(int(row['local_language_id']))
            if kind == 'stat' and row[column] not in STATS:
                continue
            name = _form_name(row) if kind == 'form' else row['name']
            if language and name:
                _add(entries, f'{kind}:{row[column]}', language, name)
    # 「くさタイプ」→「Grass-type」。短いタイプ名は単独では照合しないため、
    # タイプを明示した言い方だけを拾う。海外サイトの複数形とテラスタイプも足す。
    for key, names in list(entries.items()):
        if key.startswith('type:') and 'ja' in names and 'en' in names:
            ja, en = names['ja'][0], names['en'][0]
            _add(entries, key + ':typed', 'ja', ja + 'タイプ')
            for english in (en + '-type', en + '-types', en + ' type', en + ' types'):
                _add(entries, key + ':typed', 'en', english)
            # 「Psychic immunity」のように、わざと同名のタイプも後ろの語で決まる。
            for suffix, japanese in TYPE_PHRASES:
                for english in suffix:
                    _add(entries, f'{key}:{japanese}', 'en', f'{en} {english}')
                _add(entries, f'{key}:{japanese}', 'ja', ja + japanese)
            _add(entries, key + ':tera', 'ja', ja + 'テラス')
            _add(entries, key + ':tera', 'en', 'Tera ' + en)
    # Showdown形式の「Jolly Nature」行。
    for key, names in list(entries.items()):
        if key.startswith('nature:') and 'ja' in names and 'en' in names:
            _add(entries, key + ':line', 'ja', '性格: ' + names['ja'][0])
            _add(entries, key + ':line', 'en', names['en'][0] + ' Nature')
    if 'pokemon_forms' in tables:
        _smogon_forms(entries, tables)
    return entries


def _smogon_forms(entries, tables):
    """``landorus-therian`` → 英「Landorus-Therian」／日「ランドロス（れいじゅうフォルム）」。

    海外の対戦サイトはフォームを「種族名-フォーム名」で書く。日本語は完全名が
    あればそれを、なければ種族名に括弧でフォーム名を添える。
    """
    species_of = {row['id']: row['species_id']
                  for row in csv.DictReader(io.StringIO(tables['pokemon']))}
    form_names = {}
    for row in csv.DictReader(io.StringIO(tables['pokemon_form_names'])):
        if row['local_language_id'] == '1':
            form_names[row['pokemon_form_id']] = row['form_name']
    for row in csv.DictReader(io.StringIO(tables['pokemon_forms'])):
        suffix = row['form_identifier']
        species = entries.get(f"species:{species_of.get(row['pokemon_id'])}")
        if not suffix or not species or 'en' not in species or 'ja' not in species:
            continue
        key = f"form:{row['id']}"
        english = species['en'][0] + '-' + '-'.join(
            part.capitalize() for part in suffix.split('-'))
        if 'ja' not in entries.get(key, {}):
            form = form_names.get(row['id'])
            _add(entries, key, 'ja', f"{species['ja'][0]}（{form}）" if form else species['ja'][0])
        _add(entries, key, 'en', english)


def fetch_pokeapi(ref, opener=urllib.request.urlopen):
    tables = {}
    for table in [table for _, table, _ in KINDS] + EXTRA_TABLES:
        with opener(POKEAPI_CSV.format(ref=ref, name=table), timeout=60) as response:
            tables[table] = response.read().decode('utf-8')
    return {'source': f'PokeAPI/pokeapi@{ref}', 'entries': parse_csvs(tables)}


def merge_custom(base, custom):
    """custom-terms.json を公式辞書へ重ねる。

    ``ref`` 付きの項目は既存項目へ別名を足し、``ref`` なしは新しい用語になる。
    各言語の最初の名前がその言語での出力表記。
    """
    entries = {key: {lang: list(names) for lang, names in value.items()}
               for key, value in base.get('entries', {}).items()}
    for number, term in enumerate(custom.get('terms', [])):
        names = {lang: value if isinstance(value, list) else [value]
                 for lang, value in term.items() if lang not in {'ref', 'note'}}
        key = term.get('ref') or f'custom:{number}'
        if term.get('ref') and key not in entries:
            raise ValueError(f'custom-terms.json: unknown ref {key}')
        for lang, values in names.items():
            for value in values:
                _add(entries, key, lang, value)
        if not term.get('ref'):
            entries[key]['_custom'] = True
    return entries


def build(base, custom):
    """poketr.js が読む最終形。照合に使う除外語・紛らわしい語も含める。"""
    return {'source': base.get('source', 'custom only'),
            'entries': merge_custom(base, custom),
            'exclude': custom.get('exclude', {}),
            'ambiguous': custom.get('ambiguous', {})}
