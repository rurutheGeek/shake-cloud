# -*- coding: utf-8 -*-
"""クイズログ（UBSLEEPY の quiz_log テーブル）の分析。

間違いやすい問題・よくある取り違え・書き間違いの候補・アカウントごとの
成績を、集計して返す。アカウントで絞ると、その人の苦手になる。
DBへは `query(sql) -> (header, rows)` を受け取って読むだけなので、
FastAPIにもdockerにも依存しない（テストは偽の query を渡す）。

quiz_log の列: quiz_name, at, judge, question, answer_input, recognized。
新しいBotは answer（正解の表記）・quiz_message_id・user_id（回答した人）も
書く。answer が無い古い行は、その問題で正答になった入力のうち最も多いものを
正解として扱う。user_id が無い古い行は、アカウントごとの集計に入らない。
judge は 正答／誤答／空（入力を認識できなかった）／ギブアップ／ヒント。
"""
import difflib
import re

TABLE = 'quiz_log'
QUIZ_LABELS = {
    'bq': '種族値クイズ',
    'acq': 'ACクイズ',
    'etojq': '英和翻訳クイズ',
    'jtoeq': '和英翻訳クイズ',
    'ctojq': '中日翻訳クイズ',
    'cryq': '鳴き声クイズ',
    'introq': 'イントロクイズ',
}
# 期間（日数）。0 は全期間。
PERIODS = (7, 30, 90, 0)
DEFAULT_DAYS = 0
DEFAULT_MIN_ANSWERS = 3
MAX_MIN_ANSWERS = 1000

HARD_LIMIT = 100
PAIR_LIMIT = 50
PAIR_FETCH = 3000
TYPO_FETCH = 1000
TYPO_LIMIT = 200
ACCOUNT_LIMIT = 100
# セーブデータ（save_user）の共通スコープ。UBSLEEPY の save.SAVE_SCOPE と同じ。
SAVE_SCOPE = 0
VOCABULARY_LIMIT = 5000
# これ以上似ていれば「書き間違い」とみなす（difflib の一致率）
SIMILAR = 0.6

CORRECT = "judge = '正答'"
WRONG = "judge = '誤答'"
GIVEUP = "judge = 'ギブアップ'"
HINT = "judge = 'ヒント'"
UNKNOWN = 'recognized IS NOT TRUE'

QUIZ_NAME_RE = re.compile(r'^[a-z0-9_]{1,32}$')
JST_DAY = "(at AT TIME ZONE 'Asia/Tokyo')::date"

# CSVに出す表: 種類 -> (ファイル名に使う名前, [(見出し, キー)])
EXPORTS = {
    'hard': ('hard', [
        ('問題', 'question'), ('正解', 'answer'), ('回答数', 'answers'),
        ('正答', 'correct'), ('誤答', 'wrong'), ('ギブアップ', 'giveup'),
        ('誤答・ギブ率', 'wrong_rate'), ('認識できず', 'unknown'),
        ('よくある誤答', 'wrong_answers_text')]),
    'pairs': ('pairs', [
        ('正解', 'answer'), ('問題', 'question'), ('誤答', 'answer_input'),
        ('回数', 'count'), ('相互', 'mutual_text')]),
    'typos': ('typos', [
        ('入力', 'answer_input'), ('回数', 'count'), ('近い名前', 'nearest'),
        ('一致率', 'similarity'), ('見立て', 'guess'),
        ('そのときの正解', 'answers_text'), ('最後に見た日', 'last_day')]),
    'accounts': ('accounts', [
        ('ユーザーID', 'user_id'), ('名前', 'user_name'), ('回答数', 'answers'),
        ('正答', 'correct'), ('誤答', 'wrong'), ('正答率', 'correct_rate'),
        ('ギブアップ', 'giveup'), ('ヒント', 'hint'), ('認識できず', 'unknown'),
        ('最後に答えた日', 'last_day')]),
}


def quote_literal(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def clean_days(days) -> int:
    try:
        days = int(days)
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return days if days in PERIODS else DEFAULT_DAYS


def clean_min_answers(value) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MIN_ANSWERS
    return min(max(value, 1), MAX_MIN_ANSWERS)


def clean_user(value) -> int | None:
    """絞り込むアカウント（DiscordのユーザーID）。数字でなければ絞らない。"""
    text = str(value or '').strip()
    return int(text) if text.isdigit() and len(text) <= 20 else None


def where(quiz: str = '', days: int = 0, extra: str = '', user: int | None = None) -> str:
    """絞り込みのWHERE句。quiz は QUIZ_NAME_RE に合うものだけ渡すこと。"""
    parts = []
    if user is not None:
        parts.append(f'user_id = {int(user)}')
    if quiz:
        if not QUIZ_NAME_RE.match(quiz):
            raise ValueError(f'bad quiz name: {quiz}')
        parts.append(f'quiz_name = {quote_literal(quiz)}')
    if days:
        parts.append(f"at >= now() - interval '{int(days)} days'")
    if extra:
        parts.append(extra)
    return (' WHERE ' + ' AND '.join(parts)) if parts else ''


def answer_sql(has_answer: bool) -> str:
    """問題ごとの正解の表記（GROUP BY question の中で使う集約式）。"""
    learned = f'mode() WITHIN GROUP (ORDER BY answer_input) FILTER (WHERE {CORRECT})'
    if has_answer:
        return f'COALESCE(max(answer), {learned})'
    return learned


def normalize(text: str) -> str:
    """表記ゆれをならす（ひらがな→カタカナ、空白・かっこ・記号を落とす）。"""
    text = ''.join(
        chr(ord(char) + 0x60) if 'ぁ' <= char <= 'ゖ' else char
        for char in str(text or ''))
    return re.sub(r'[\s　()（）・!！?？:：\-‐－]', '', text).upper()


def similarity(left: str, right: str) -> float:
    left, right = normalize(left), normalize(right)
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def _int(value) -> int:
    return int(value) if value not in (None, '') else 0


def columns(query) -> list:
    _, rows = query(
        'SELECT column_name FROM information_schema.columns '
        f"WHERE table_schema = 'public' AND table_name = {quote_literal(TABLE)} "
        'ORDER BY ordinal_position')
    return [row[0] for row in rows]


def summary(query, days: int, user: int | None = None) -> list:
    """クイズの種類ごとの件数と正答率。"""
    _, rows = query(
        'SELECT quiz_name, '
        f'count(*) FILTER (WHERE {CORRECT}), count(*) FILTER (WHERE {WRONG}), '
        f'count(*) FILTER (WHERE {UNKNOWN}), count(*) FILTER (WHERE {GIVEUP}), '
        f'count(*) FILTER (WHERE {HINT}), '
        f'min({JST_DAY}), max({JST_DAY}) '
        f'FROM {TABLE}{where(days=days, user=user)} GROUP BY quiz_name '
        'ORDER BY count(*) DESC, quiz_name')
    result = []
    for name, correct, wrong, unknown, giveup, hint, first, last in rows:
        correct, wrong = _int(correct), _int(wrong)
        answers = correct + wrong
        result.append({
            'quiz': name,
            'label': QUIZ_LABELS.get(name, name),
            'answers': answers,
            'correct': correct,
            'wrong': wrong,
            'unknown': _int(unknown),
            'giveup': _int(giveup),
            'hint': _int(hint),
            'correct_rate': round(100 * correct / answers, 1) if answers else None,
            'first_day': first,
            'last_day': last,
        })
    return result


def wrong_pairs(query, quiz: str, days: int, has_answer: bool,
                user: int | None = None) -> list:
    """（問題, 誤答）ごとの回数。多い順。"""
    scope = where(quiz, days, user=user)
    _, rows = query(
        'SELECT l.answer, w.question, w.answer_input, w.n FROM ('
        f'SELECT question, answer_input, count(*) AS n FROM {TABLE}'
        f'{where(quiz, days, WRONG, user)} GROUP BY question, answer_input) w '
        f'JOIN (SELECT question, {answer_sql(has_answer)} AS answer '
        f'FROM {TABLE}{scope} GROUP BY question) l USING (question) '
        f'ORDER BY w.n DESC, w.question, w.answer_input LIMIT {PAIR_FETCH}')
    return [{'answer': answer or '', 'question': question, 'answer_input': answer_input,
             'count': _int(count)} for answer, question, answer_input, count in rows]


def hard_questions(query, quiz: str, days: int, min_answers: int,
                   has_answer: bool, pairs: list, user: int | None = None) -> list:
    """間違い・ギブアップの割合が高い問題。

    割合は（誤答＋ギブアップ）÷（正答＋誤答＋ギブアップ）。分母が min_answers 以上のもの。
    """
    _, rows = query(
        'SELECT question, answer, ok, ng, giveup, unknown FROM ('
        f'SELECT question, {answer_sql(has_answer)} AS answer, '
        f'count(*) FILTER (WHERE {CORRECT}) AS ok, '
        f'count(*) FILTER (WHERE {WRONG}) AS ng, '
        f'count(*) FILTER (WHERE {GIVEUP}) AS giveup, '
        f'count(*) FILTER (WHERE {UNKNOWN}) AS unknown '
        f'FROM {TABLE}{where(quiz, days, user=user)} GROUP BY question) q '
        f'WHERE ok + ng + giveup >= {int(min_answers)} AND ng + giveup > 0 '
        'ORDER BY (ng + giveup)::float / (ok + ng + giveup) DESC, '
        'ng + giveup DESC, question '
        f'LIMIT {HARD_LIMIT}')
    by_question = {}
    for pair in pairs:
        by_question.setdefault(pair['question'], []).append(pair)
    result = []
    for question, answer, correct, wrong, giveup, unknown in rows:
        correct, wrong, giveup = _int(correct), _int(wrong), _int(giveup)
        tops = by_question.get(question, [])[:3]
        result.append({
            'question': question,
            'answer': answer or '',
            'answers': correct + wrong,
            'correct': correct,
            'wrong': wrong,
            'wrong_rate': round(100 * (wrong + giveup) / (correct + wrong + giveup), 1),
            'giveup': giveup,
            'unknown': _int(unknown),
            'wrong_answers': tops,
            'wrong_answers_text': '／'.join(
                f"{pair['answer_input']}×{pair['count']}" for pair in tops),
        })
    return result


def confusions(pairs: list) -> list:
    """よくある取り違え（正解 ← 誤答）。逆向きもあれば「相互」。"""
    seen = {(normalize(pair['answer']), normalize(pair['answer_input']))
            for pair in pairs if pair['answer']}
    result = []
    for pair in pairs[:PAIR_LIMIT]:
        mutual = bool(pair['answer']) and (
            normalize(pair['answer_input']), normalize(pair['answer'])) in seen
        result.append({**pair, 'mutual': mutual, 'mutual_text': '相互' if mutual else ''})
    return result


def vocabulary(query, quiz: str) -> list:
    """認識できた入力と正解の表記（書き間違いの照合先）。期間では絞らない。"""
    _, rows = query(
        f'SELECT answer_input, count(*) FROM {TABLE}'
        f"{where(quiz, 0, 'recognized IS TRUE AND (' + CORRECT + ' OR ' + WRONG + ')')} "
        'GROUP BY answer_input ORDER BY count(*) DESC, answer_input '
        f'LIMIT {VOCABULARY_LIMIT}')
    return [row[0] for row in rows if row[0]]


def nearest(text: str, words: dict) -> tuple:
    """最も近い語と一致率。words は {ならした表記: 元の表記}。"""
    key = normalize(text)
    if not key or not words:
        return '', 0.0
    close = difflib.get_close_matches(key, list(words), n=1, cutoff=SIMILAR)
    if not close:
        return '', 0.0
    return words[close[0]], difflib.SequenceMatcher(None, key, close[0]).ratio()


def accounts(query, quiz: str, days: int) -> list:
    """アカウントごとの成績（回答した人が残っている行だけ）。回答の多い順。"""
    _, rows = query(
        'SELECT a.user_id, u.user_name, a.ok, a.ng, a.giveup, a.hint, a.unknown, a.last '
        'FROM (SELECT user_id, '
        f'count(*) FILTER (WHERE {CORRECT}) AS ok, '
        f'count(*) FILTER (WHERE {WRONG}) AS ng, '
        f'count(*) FILTER (WHERE {GIVEUP}) AS giveup, '
        f'count(*) FILTER (WHERE {HINT}) AS hint, '
        f'count(*) FILTER (WHERE {UNKNOWN}) AS unknown, '
        f'max({JST_DAY}) AS last '
        f"FROM {TABLE}{where(quiz, days, 'user_id IS NOT NULL')} GROUP BY user_id) a "
        'LEFT JOIN save_user u '
        f'ON u.user_id = a.user_id AND u.guild_id = {SAVE_SCOPE} '
        f'ORDER BY a.ok + a.ng DESC, a.giveup DESC, a.user_id LIMIT {ACCOUNT_LIMIT}')
    result = []
    for user_id, user_name, correct, wrong, giveup, hint, unknown, last in rows:
        correct, wrong = _int(correct), _int(wrong)
        answers = correct + wrong
        result.append({
            'user_id': user_id,
            'user_name': user_name or '',
            'answers': answers,
            'correct': correct,
            'wrong': wrong,
            'correct_rate': round(100 * correct / answers, 1) if answers else None,
            'giveup': _int(giveup),
            'hint': _int(hint),
            'unknown': _int(unknown),
            'last_day': last,
        })
    return result


def user_name(query, user: int) -> str:
    _, rows = query(
        'SELECT user_name FROM save_user '
        f'WHERE user_id = {int(user)} AND guild_id = {SAVE_SCOPE}')
    return rows[0][0] if rows else ''


def typos(query, quiz: str, days: int, has_answer: bool, known: list,
          user: int | None = None) -> list:
    """認識できなかった入力。近い名前があれば書き間違いの候補として並べる。"""
    scope = where(quiz, days, user=user)
    _, rows = query(
        f'SELECT u.answer_input, l.answer, u.n, u.last FROM ('
        f'SELECT question, answer_input, count(*) AS n, max({JST_DAY}) AS last '
        f'FROM {TABLE}{where(quiz, days, UNKNOWN, user)} GROUP BY question, answer_input) u '
        f'JOIN (SELECT question, {answer_sql(has_answer)} AS answer '
        f'FROM {TABLE}{scope} GROUP BY question) l USING (question) '
        f'ORDER BY u.n DESC, u.answer_input LIMIT {TYPO_FETCH}')
    grouped = {}
    for answer_input, answer, count, last in rows:
        if not answer_input:
            continue
        item = grouped.setdefault(answer_input, {
            'answer_input': answer_input, 'count': 0, 'answers': [], 'last_day': ''})
        item['count'] += _int(count)
        if answer and answer not in item['answers']:
            item['answers'].append(answer)
        item['last_day'] = max(item['last_day'], last or '')

    words = {}
    for word in known:
        words.setdefault(normalize(word), word)
    words.pop('', None)

    result = []
    for item in grouped.values():
        # まず、そのとき出題されていた正解と比べる（正解を書き間違えたか）
        best_answer, best_ratio = '', 0.0
        for answer in item['answers']:
            ratio = similarity(item['answer_input'], answer)
            if ratio > best_ratio:
                best_answer, best_ratio = answer, ratio
        if best_ratio >= SIMILAR:
            name, ratio, guess = best_answer, best_ratio, '正解の書き間違い'
        else:
            name, ratio = nearest(item['answer_input'], words)
            guess = 'ほかの名前の書き間違い' if name else '近い名前なし（別名の候補・雑談）'
        result.append({
            **item,
            'nearest': name,
            'similarity': round(100 * ratio) if name else '',
            'guess': guess,
            'answers_text': '／'.join(item['answers'][:5]),
        })
    result.sort(key=lambda item: (-item['count'], -(item['similarity'] or 0),
                                  item['answer_input']))
    return result[:TYPO_LIMIT]


def empty_view(days=DEFAULT_DAYS, min_answers=DEFAULT_MIN_ANSWERS, user='') -> dict:
    return {'quiz': '', 'days': clean_days(days),
            'min_answers': clean_min_answers(min_answers), 'periods': PERIODS,
            'user': clean_user(user), 'user_name': '',
            'summary': [], 'hard': [], 'pairs': [], 'typos': [], 'accounts': [],
            'has_answer': False, 'has_user': False}


def report(query, quiz: str = '', days=DEFAULT_DAYS, min_answers=DEFAULT_MIN_ANSWERS,
           user='') -> dict:
    """分析ページ1枚ぶんの集計。user（ユーザーID）を渡すと、その人の回答だけで集計する。"""
    base = empty_view(days, min_answers, user)
    days, min_answers = base['days'], base['min_answers']
    names = columns(query)
    if not names:
        return {**base, 'error': f'{TABLE} テーブルがありません'}
    has_answer = 'answer' in names
    has_user = 'user_id' in names
    user = base['user'] if has_user else None
    base = {**base, 'user': user, 'has_user': has_user}
    if user is not None:
        base['user_name'] = user_name(query, user)
    rows = summary(query, days, user)
    known_quizzes = [row['quiz'] for row in rows if QUIZ_NAME_RE.match(row['quiz'])]
    if quiz not in known_quizzes:
        quiz = known_quizzes[0] if known_quizzes else ''
    result = {**base, 'quiz': quiz, 'summary': rows, 'has_answer': has_answer,
              'quiz_label': QUIZ_LABELS.get(quiz, quiz)}
    if not quiz:
        return result
    pairs = wrong_pairs(query, quiz, days, has_answer, user)
    known = vocabulary(query, quiz) + [pair['answer'] for pair in pairs if pair['answer']]
    result['hard'] = hard_questions(
        query, quiz, days, min_answers, has_answer, pairs, user)
    result['pairs'] = confusions(pairs)
    result['typos'] = typos(query, quiz, days, has_answer, known, user)
    if has_user and user is None:
        result['accounts'] = accounts(query, quiz, days)
    return result


def export(view: dict, kind: str) -> tuple:
    """CSV用の（見出し, 行）。kind は EXPORTS のキー。"""
    if kind not in EXPORTS:
        raise ValueError(f'unknown export: {kind}')
    _, fields = EXPORTS[kind]
    header = [label for label, _ in fields]
    rows = [[item.get(key, '') for _, key in fields] for item in view.get(kind, [])]
    return header, rows
