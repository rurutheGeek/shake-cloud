#!/usr/bin/env python3
"""Assign genres from existing tags and keyword rules, as an organize correction.

Writes /state/genres-corrections.json for:

  organize.py plan --no-lookup --corrections /tools/genres-corrections.json
"""
import collections
import json
import os
import unicodedata
from pathlib import Path

import mutagen

ROOT = Path(os.environ.get('GENRE_MUSIC', '/music'))
OUT = Path(os.environ.get('GENRE_OUT', '/state/genres-corrections.json'))

ALIASES = {
    'jpop': 'J-Pop', 'j-pop': 'J-Pop', 'j pop': 'J-Pop', 'japanese pop': 'J-Pop',
    'vocaloid': 'Vocaloid', 'ボカロ': 'Vocaloid', 'electronic': 'Electronic',
    'classical': 'Classical', 'classic': 'Classical', 'soundtrack': 'Soundtrack',
    'game': 'Game', 'anime': 'Anime', 'jazz': 'Jazz', 'rock': 'Rock',
    'dance': 'Dance', 'pop': 'Pop', 'techno': 'Techno',
}
CLASSICAL = ['クラシック', 'ベートーヴェン', 'モーツァルト', 'リスト', 'ショパン', 'バッハ',
             'ドビュッシー', 'サティ', 'ヴェルディ', 'ホルスト', 'パッヘルベル', 'ビゼー',
             'ハチャトゥリアン', 'ドヴォルザーク', 'ショスタコーヴィチ', 'リムスキー',
             'アンダーソン', 'ラヴェル', 'グリーグ', 'スメタナ', 'シュトラウス',
             '怒りの日', 'ディエス・イレ', '月の光', '熊蜂の飛行', '愛の夢']
TOUHOU = ['東方', 'Touhou', '上海アリス', 'ZUN', '幻想郷', 'IOSYS', 'COOL&CREATE']
VOCALOID = ['初音ミク', '鏡音', '巡音', 'GUMI', 'IA', 'flower', 'ボーカロイド',
            'VOCALOID', '重音テト', '唄音ウタ', 'MEIKO', 'KAITO', '可不', 'ずんだもん']
SOUNDTRACK = ['ポケモン', 'ドラゴンクエスト', 'マリオ', 'カービィ', 'ゼルダ', 'モンスターハンター',
              'モンハン', 'スマブラ', '大乱闘', 'メトロイド', 'ファイアーエムブレム',
              'スプラトゥーン', 'Splatoon', 'Minecraft', 'UNDERTALE', 'Undertale',
              'Deltarune', 'beatmania', 'jubeat', '太鼓の達人', 'ロックマン', 'バイオハザード',
              'ファイナルファンタジー', 'クロノ', '聖剣伝説', '不思議のダンジョン',
              'モンスターストライク', 'ブルーアーカイブ', 'Blue Archive', 'Deemo',
              'ドラガリア', 'Fallout', '星のカービィ', 'サントラ', 'Original Soundtrack',
              'ゲーム', 'ぶちやぶれ', 'テイルズ', 'ゼノ', 'メタルギア', 'ぷよぷよ',
              '龍が如く', 'ペルソナ', 'Splatoon2', '星の', 'マリオ', 'F-ZERO']
ANIME = ['BanG Dream', 'バンドリ', 'ラブライブ', 'アニソン', 'A応P', 'アニメ',
         'ハロー、ハッピーワールド', 'Poppin', 'Roselia', 'Afterglow', 'Pastel',
         'モーニング娘', 'μ\'s', '涼宮ハルヒ', 'けいおん', 'ガンダム', 'マクロス',
         '鋼の錬金術師', '化物語', 'とある', 'ラブライブ', 'アイドルマスター',
         'THE IDOLM@STER', 'ドリーム', 'プリキュア', 'セーラームーン']


def normalize(text):
    return unicodedata.normalize('NFKC', text or '').lower()


def classify(text):
    if any(word.lower() in text for word in CLASSICAL):
        return 'Classical'
    if any(word.lower() in text for word in TOUHOU):
        return 'Game'
    if any(word.lower() in text for word in VOCALOID):
        return 'Vocaloid'
    if any(word.lower() in text for word in SOUNDTRACK):
        return 'Soundtrack'
    if any(word.lower() in text for word in ANIME):
        return 'Anime'
    return ''


stats = collections.Counter()
corrections = {}
for dirpath, dirnames, filenames in os.walk(ROOT):
    if 'Converted' in Path(dirpath).parts:
        continue
    for name in sorted(filenames):
        if not name.lower().endswith('.mp3'):
            continue
        path = Path(dirpath) / name
        tags = {}
        try:
            easy = mutagen.File(str(path), easy=True)
            if easy is not None and easy.tags is not None:
                for key in ('title', 'artist', 'album', 'albumartist', 'genre'):
                    values = easy.tags.get(key)
                    if values:
                        tags[key] = str(values[0])
        except Exception:  # noqa: BLE001
            stats['unreadable'] += 1
            continue
        current = tags.get('genre', '').strip()
        canonical = ALIASES.get(normalize(current), '')
        if not canonical and current:
            canonical = current if current[:1].isupper() or not current.isascii() else current.title()
        if not canonical:
            haystack = ' '.join(tags.get(key, '') for key in
                                ('title', 'artist', 'album', 'albumartist'))
            canonical = classify(normalize(haystack))
        if not canonical:
            stats['left_blank'] += 1
            continue
        if current == canonical:
            stats['kept'] += 1
            continue
        corrections[str(path.relative_to(ROOT))] = {'genre': canonical}
        stats['changed'] += 1

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({'files': corrections}, ensure_ascii=False, indent=1))
print(dict(stats), 'corrections', len(corrections))
