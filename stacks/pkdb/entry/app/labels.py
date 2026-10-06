# -*- coding: utf-8 -*-
"""画面で使う固定のラベルと選択肢。DBに入っている値の名前はここに揃える。"""

STATS = [
    ('h', 'HP'),
    ('a', 'こうげき'),
    ('b', 'ぼうぎょ'),
    ('c', 'とくこう'),
    ('d', 'とくぼう'),
    ('s', 'すばやさ'),
]

# タイプ名（日本語）→ CSS のクラス名。表示色は app.css の .type-* で決める。
TYPE_SLUGS = {
    'ノーマル': 'normal', 'ほのお': 'fire', 'みず': 'water', 'でんき': 'electric',
    'くさ': 'grass', 'こおり': 'ice', 'かくとう': 'fighting', 'どく': 'poison',
    'じめん': 'ground', 'ひこう': 'flying', 'エスパー': 'psychic', 'むし': 'bug',
    'いわ': 'rock', 'ゴースト': 'ghost', 'ドラゴン': 'dragon', 'あく': 'dark',
    'はがね': 'steel', 'フェアリー': 'fairy',
}

MOVE_CATEGORIES = ['物理', '特殊', '変化']

MOVE_TARGETS = [
    '1体選択', 'おたがい全員', 'ひんし状態のポケモン', 'ランダム1体', '全体の場',
    '味方1体', '味方の場', '味方全体', '特定のわざ', '相手の場', '相手全体',
    '自分', '自分か味方', '自分以外',
]

LANGUAGES = [
    ('jpn', '日本語'), ('eng', '英語'), ('fra', 'フランス語'), ('ger', 'ドイツ語'),
    ('ita', 'イタリア語'), ('kor', '韓国語'), ('spa', 'スペイン語'),
    ('chs', '中国語（簡体字）'), ('cht', '中国語（繁体字）'),
]

GENDERS = [('', '指定なし'), ('m', '♂のみ'), ('f', '♀のみ')]

# 性別比は0〜255。よく使う値だけ選択肢にし、細かい値は自由入力。
GENDER_RATIOS = [
    (0, '♂のみ'), (31, '♂7 : ♀1'), (63, '♂3 : ♀1'), (127, '♂1 : ♀1'),
    (191, '♂1 : ♀3'), (223, '♂1 : ♀7'), (254, '♀のみ'), (255, '性別なし'),
]

# 経験値タイプ。1〜6 は本編の経験値曲線の番号。
LEVELING_RATES = [
    (1, '1（早い）'), (2, '2（普通）'), (3, '3（遅い）'), (4, '4（やや遅い）'),
    (5, '5（おかしな）'), (6, '6（でこぼこ）'),
]

# 地方図鑑の列と表示名（世代順）。update_rdex のホワイトリストと同じ並び。
RDEX_REGIONS = [
    ('kanto', 'カントー（RGBP）'),
    ('new', '新図鑑（GS）'),
    ('johto', 'ジョウト（HGSS）'),
    ('hoenn', 'ホウエン（RSE）'),
    ('hoenn_oras', 'ホウエン（ORAS）'),
    ('sinnoh', 'シンオウ（DP）'),
    ('enhanced_sinnoh', 'シンオウ（Pt）'),
    ('unova', 'イッシュ（BW）'),
    ('unova_b2w2', 'イッシュ（B2W2）'),
    ('central_kalos', 'セントラルカロス（XY）'),
    ('coastal_kalos', 'コーストカロス（XY）'),
    ('mountain_kalos', 'マウンテンカロス（XY）'),
    ('alola', 'アローラ（SM）'),
    ('melemele', 'メレメレ（SM）'),
    ('akala', 'アーカラ（SM）'),
    ('ulaula', 'ウラウラ（SM）'),
    ('poni', 'ポニ（SM）'),
    ('alola_usum', 'アローラ（USUM）'),
    ('melemele_usum', 'メレメレ（USUM）'),
    ('akala_usum', 'アーカラ（USUM）'),
    ('ulaula_usum', 'ウラウラ（USUM）'),
    ('poni_usum', 'ポニ（USUM）'),
    ('kanto_pe', 'カントー（LPLE）'),
    ('galar', 'ガラル（SWSH）'),
    ('isle_of_armor', '鎧の孤島'),
    ('crown_tundra', '冠の雪原'),
    ('hisui', 'ヒスイ（PLA）'),
    ('paldea', 'パルデア（SV）'),
    ('kitakami', 'キタカミ（碧の仮面）'),
    ('blueberry', 'ブルーベリー（藍の円盤）'),
    ('kalos', 'カロス（PLZA）'),
    ('hyperspace', 'ハイパースペース（M次元ラッシュ）'),
    ('champions', 'チャンピオンズ'),
]

BATTLE_TYPES = ['シングル', 'ダブル']

LEARN_METHODS = ['レベルアップ', 'わざマシン', 'タマゴ技', '技教え', 'イベント', '技思い出し']

# 履歴ページで使うアクションの日本語名。
ACTION_LABELS = {
    'register_pokemon': 'ポケモン登録',
    'update_pokemon': 'ポケモンの値を修正',
    'update_pokemon_names': '名前を修正',
    'copy_pokemon_status': '値をまとめて写す',
    'register_title': '作品を追加',
    'update_title': '作品を修正',
    'register_title_solo': '作品1本を追加',
    'update_title_solo': '作品1本を修正',
    'register_move': 'わざを追加',
    'update_move': 'わざを修正',
    'delete_move_title': 'わざの行を削除',
    'inherit_moves': 'わざをまとめて写す',
    'register_ability': '特性を追加',
    'update_ability': '特性を修正',
    'inherit_abilities': '特性をまとめて写す',
    'save_pokedex': '図鑑情報を保存',
    'update_rdex': '地方図鑑番号を保存',
    'set_evolution': '進化を保存',
    'delete_evolution': '進化を削除',
    'save_learnset': '覚えわざを保存',
    'copy_learnset': '覚えわざを写す',
    'import_rankings': '順位を取り込み',
}

ENTITY_LABELS = {
    'pokemon': 'ポケモン',
    'pokemon_names': '名前',
    'title': '作品',
    'title_solo': '作品1本',
    'move': 'わざ',
    'ability': '特性',
    'pokedex': '図鑑情報',
    'rdex': '地方図鑑番号',
    'evolution': '進化',
    'learnset': '覚えわざ',
    'rankings': '順位',
}
