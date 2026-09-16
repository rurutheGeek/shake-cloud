#!/usr/bin/env python3
"""Second genre pass: make a genre consistent per album and fill blanks.

Uses the majority genre of the album; when the album has none, infers from
title/artist/album keywords. Writes /state/genres2-corrections.json for
organize.py plan --no-lookup --corrections.
"""
import collections
import json
import os
import unicodedata
from pathlib import Path

import mutagen

ROOT = Path(os.environ.get('GENRE_MUSIC', '/music'))
OUT = Path(os.environ.get('GENRE_OUT', '/state/genres2-corrections.json'))

ALIASES = {
    'jpop': 'J-Pop', 'j-pop': 'J-Pop', 'j pop': 'J-Pop', 'japanese pop': 'J-Pop',
    'vocaloid': 'Vocaloid', 'ボカロ': 'Vocaloid', 'electronic': 'Electronic',
    'classical': 'Classical', 'classic': 'Classical', 'soundtrack': 'Soundtrack',
    'game': 'Game', 'anime': 'Anime', 'jazz': 'Jazz', 'rock': 'Rock',
    'dance': 'Dance', 'pop': 'Pop', 'techno': 'Techno', 'hiphop': 'Hiphop',
    'hip hop': 'Hiphop', 'rap': 'Hiphop',
}
CLASSICAL = ['クラシック', 'ベートーヴェン', 'モーツァルト', 'リスト', 'ショパン', 'バッハ',
             'ドビュッシー', 'サティ', 'ヴェルディ', 'ホルスト', 'パッヘルベル', 'ビゼー',
             'ハチャトゥリアン', 'ドヴォルザーク', 'ショスタコーヴィチ', 'リムスキー',
             'アンダーソン', 'ラヴェル', 'グリーグ', 'スメタナ', 'シュトラウス']
TOUHOU = ['東方', 'Touhou', '上海アリス', 'ZUN', '幻想郷', 'IOSYS', 'COOL&CREATE']
VOCALOID = ['初音ミク', '鏡音', '巡音', 'GUMI', 'IA', 'flower', 'ボーカロイド',
            'VOCALOID', '重音テト', '唄音ウタ', 'MEIKO', 'KAITO', '可不', 'ずんだもん']
SOUNDTRACK = ['ポケモン', 'ドラゴンクエスト', 'マリオ', 'カービィ', 'ゼルダ', 'モンスターハンター',
              'モンハン', 'スマブラ', '大乱闘', 'メトロイド', 'ファイアーエムブレム',
              'スプラトゥーン', 'Splatoon', 'Minecraft', 'UNDERTALE', 'Undertale',
              'Deltarune', 'beatmania', 'jubeat', '太鼓の達人', 'ロックマン', 'Fallout',
              'ファイナルファンタジー', 'クロノ', '聖剣伝説', '不思議のダンジョン',
              'モンスターストライク', 'ブルーアーカイブ', 'Blue Archive', 'Deemo',
              'ドラガリア', 'サントラ', 'Original Soundtrack', 'ゲーム', 'テイルズ',
              'ゼノ', 'メタルギア', 'ぷよぷよ', '龍が如く', 'ペルソナ', '星の']
ANIME = ['BanG Dream', 'バンドリ', 'ラブライブ', 'アニソン', 'A応P', 'アニメ',
         'ハロー、ハッピーワールド', 'Poppin', 'Roselia', 'Afterglow', 'Pastel',
         'モーニング娘', '涼宮ハルヒ', 'けいおん', 'ガンダム', 'マクロス',
         '鋼の錬金術師', 'とある', 'アイドルマスター', 'THE IDOLM@STER',
         'プリキュア', 'セーラームーン', 'おそ松', 'ラブライブ']


def normalize(text):
    return unicodedata.normalize('NFKC', text or '').lower()


def canonical(genre):
    if not genre:
        return ''
    mapped = ALIASES.get(normalize(genre))
    if mapped:
        return mapped
    return genre if genre[:1].isupper() or not genre.isascii() else genre.title()


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


albums = collections.defaultdict(list)
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
            continue
        rel = str(path.relative_to(ROOT))
        albums[(tags.get('albumartist', ''), tags.get('album', ''))].append((rel, tags))

stats = collections.Counter()
corrections = {}
for (albumartist, album), tracks in albums.items():
    counts = collections.Counter(canonical(tags.get('genre', '')) for _, tags in tracks)
    counts.pop('', None)
    genre = counts.most_common(1)[0][0] if counts else ''
    if not genre:
        haystack = normalize(' '.join([album, albumartist] + [t.get('artist', '') + ' ' + t.get('title', '') for _, t in tracks]))
        genre = classify(haystack)
        if genre:
            stats['album_inferred'] += 1
    if not genre:
        stats['left_blank'] += 1
        continue
    for rel, tags in tracks:
        if canonical(tags.get('genre', '')) == genre:
            stats['kept'] += 1
            continue
        corrections[rel] = {'genre': genre}
        stats['changed'] += 1

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({'files': corrections}, ensure_ascii=False, indent=1))
print(dict(stats), 'corrections', len(corrections), 'albums', len(albums))
