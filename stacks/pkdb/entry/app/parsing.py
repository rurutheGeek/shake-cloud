# -*- coding: utf-8 -*-
"""画面から来た文字列の解釈と、履歴表示のための整形。DBに触らない純粋な関数だけ。"""
import re

from .labels import LANGUAGES, STATS


class InputError(Exception):
    """入力の間違い。画面にそのまま出してよい日本語のメッセージを持つ。"""


def split_aliases(text):
    """あだ名を「、」「,」「改行」で分けて、順番を保ったまま重複を除く。"""
    if not text:
        return []
    parts = re.split(r'[、,\n]', text)
    seen = []
    for part in parts:
        name = part.strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def parse_int(value, label, minimum=None, maximum=None, required=False, default=None):
    """空文字を許す整数の解釈。範囲外は InputError。"""
    text = (value or '').strip()
    if text == '':
        if required:
            raise InputError(f'{label}を入れてください')
        return default
    if not re.fullmatch(r'-?\d+', text):
        raise InputError(f'{label}は数字で入れてください')
    number = int(text)
    if minimum is not None and number < minimum:
        raise InputError(f'{label}は{minimum}以上で入れてください')
    if maximum is not None and number > maximum:
        raise InputError(f'{label}は{maximum}以下で入れてください')
    return number


def parse_rankings(text):
    """使用率順位の貼り付けを解釈する。

    1行は「順位 図鑑番号 [フォーム]」か「順位 名前」。
    返り値は (行の一覧, エラーの一覧)。名前は番号に直さず、呼んだ側でDBから引く。
    """
    rows = []
    errors = []
    for number, raw in enumerate((text or '').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = re.split(r'[\s,、\t]+', line)
        if len(parts) < 2:
            errors.append(f'{number}行目: 「順位 ポケモン」の形で入れてください: {line}')
            continue
        if not parts[0].isdigit():
            errors.append(f'{number}行目: 先頭は順位（数字）です: {line}')
            continue
        rank = int(parts[0])
        if not (1 <= rank <= 99999):
            errors.append(f'{number}行目: 順位は1〜99999です: {line}')
            continue
        rest = parts[1:]
        if re.fullmatch(r'\d{1,4}', rest[0]):
            if len(rest) >= 2 and re.fullmatch(r'\d{1,2}', rest[1]):
                rows.append({'rank': rank, 'ndex': rest[0].zfill(4), 'form': rest[1].zfill(2),
                             'name': ' '.join(rest[2:]) or None})
            else:
                rows.append({'rank': rank, 'ndex': rest[0].zfill(4), 'form': '00',
                             'name': ' '.join(rest[1:]) or None})
        else:
            rows.append({'rank': rank, 'ndex': '', 'form': '', 'name': ' '.join(rest)})
    return rows, errors


def parse_bulk_moves(text):
    """覚えわざの一括入力を解釈する。

    1行は「わざ名 [レベル]」。レベルは無くてもよい（レベルアップ以外は普通は無し）。
    """
    rows = []
    errors = []
    for number, raw in enumerate((text or '').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = [part for part in re.split(r'[\s,、\t]+', line) if part]
        if not parts:
            continue
        if len(parts) > 1 and re.fullmatch(r'\d{1,3}', parts[-1]):
            move_name = ' '.join(parts[:-1])
            level = int(parts[-1])
        else:
            move_name = ' '.join(parts)
            level = None
        if not move_name:
            errors.append(f'{number}行目: わざ名がありません: {line}')
            continue
        rows.append({'move_name': move_name, 'level': level})
    return rows, errors


def human_key(path):
    """履歴の JSON のキーを、画面に出す日本語へ直す。知らないキーはそのまま。"""
    if path.startswith('stats['):
        index = int(path[6:-1])
        if 1 <= index <= len(STATS):
            return STATS[index - 1][1]
    if path.startswith('languages.'):
        code = path.split('.', 1)[1]
        names = dict(LANGUAGES)
        return names.get(code, code)
    if path.startswith('abilities.'):
        return {'1': '特性1', '2': '特性2', 'H': '隠れ特性'}.get(path.split('.', 1)[1], path)
    labels = {
        'ndex_number': '図鑑番号', 'form_id': 'フォーム', 'name': '名前',
        'form_name': '姿の名前', 'gender': '性別', 'title_group_id': '作品',
        'type_1': 'タイプ1', 'type_2': 'タイプ2', 'english': '英語名',
        'before_ndex_number': '進化前', 'before_form_id': '進化前フォーム',
        'evolution_method': '進化方法', 'aliases': 'あだ名', 'jpn': '日本語',
        'move_id': 'わざID', 'move_name': 'わざ', 'method_name': '覚え方',
        'level': 'レベル', 'learn_order': '順序', 'source': '出典', 'notes': 'メモ',
        'english_name': '英語名', 'description': '説明', 'type': 'タイプ',
        'category': '分類', 'power': '威力', 'accuracy': '命中', 'pp': 'PP',
        'priority': '優先度', 'target': '対象', 'effect_chance': '追加効果',
        'title_name': '作品名', 'generation': '世代', 'region': '地方',
        'category_or': '分類', 'height': 'たかさ', 'weight': 'おもさ',
        'gender_ratio': '性別比', 'egg_group_1': 'タマゴグループ1',
        'egg_group_2': 'タマゴグループ2', 'leveling_rate': '経験値タイプ',
        'carch_rate': '被捕獲度', 'method_id': '進化方法ID',
        'battle_season': 'シーズン', 'battle_type': '形式',
        'rank': '順位', 'rows': '件数', 'release_year': '発売年',
        'release_month': '発売月', 'release_date': '発売日',
        'new_species': '新しいポケモン', 'new_form': '新しい姿',
        'from_form': '写し元フォーム', 'from_title': '写し元作品',
        'to_title': '写し先作品', 'forms': '対象フォーム', 'copied': '写した件数',
        'skipped': '飛ばしたフォーム',
    }
    if path.startswith('evyield_'):
        return '努力値（' + {'h': 'HP', 'a': 'こうげき', 'b': 'ぼうぎょ',
                            'c': 'とくこう', 'd': 'とくぼう', 's': 'すばやさ'}.get(path[-1], path[-1]) + '）'
    return labels.get(path, path)


def flatten(value, prefix=''):
    """入れ子の JSON を「キー: 値」の平らな一覧にする（履歴の表示用）。"""
    output = []
    if isinstance(value, dict):
        for key, child in value.items():
            output += flatten(child, f'{prefix}.{key}' if prefix else key)
    elif isinstance(value, list):
        # 種族値など、項目ごとに名前を付けたい配列は添字で分ける。
        if prefix.endswith('stats') or (value and any(isinstance(item, (dict, list)) for item in value)):
            for index, child in enumerate(value, 1):
                output += flatten(child, f'{prefix}[{index}]')
        else:
            output.append((prefix, '、'.join(str(item) for item in value)))
    else:
        output.append((prefix, value))
    return output


def diff_pairs(before, after):
    """before と after を突き合わせ、変わったところだけ (表示名, 前, 後) で返す。"""
    flat_before = dict(flatten(before)) if before is not None else {}
    flat_after = dict(flatten(after)) if after is not None else {}
    keys = list(flat_before)
    for key in flat_after:
        if key not in flat_before:
            keys.append(key)
    pairs = []
    for key in keys:
        old = flat_before.get(key)
        new = flat_after.get(key)
        if old != new:
            pairs.append((human_key(key), old, new))
    return pairs
