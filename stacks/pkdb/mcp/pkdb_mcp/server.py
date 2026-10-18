# -*- coding: utf-8 -*-
"""ポケモンDB（sleepy_pkdb）の MCP サーバ（pkdb-mcp）。

Streamable HTTP で /mcp を出し、認可は MCP の仕様どおり OAuth（Authentik）。
読むのは読み取り専用のトランザクション、書くのは登録画面と同じ pokemondb の関数
だけで、書き込みには出典（source）が要る。AI からの書き込みは pkdb.strict で、
名前で指定した特性・わざ・進化方法がその作品に無ければ写さず・足さず error にする。
"""
from contextlib import asynccontextmanager
from contextvars import ContextVar
import logging
import os
from typing import Annotated, Any, Literal

import anyio.to_thread
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from . import auth, db
from .db import Call

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s %(message)s')
log = logging.getLogger('pkdb-mcp')

PUBLIC_URL = os.environ.get('PKDB_MCP_PUBLIC_URL', 'http://127.0.0.1:8080').rstrip('/')
ISSUER = os.environ.get('PKDB_MCP_ISSUER', '')
CLIENT_ID = os.environ.get('PKDB_MCP_CLIENT_ID', 'pkdb-mcp')

INSTRUCTIONS = """\
ポケモンDB（sleepy_pkdb、スキーマ pokemondb）を調べ、新しいデータを入れるためのサーバ。

- まず describe_tables と query で、表の中身と既存の行を確かめる。表と列の意味は
  表・列のコメントにある。ID は文字列（図鑑番号 4 桁 '0025'、フォーム 2 桁 '00'、
  作品グループ 3 桁 '090'、作品 4 桁）。
- 書き込みはこのサーバのツールだけで行う。どのツールも source（値の出典。URL や
  資料名）が必須で、entry_log に残る。
- 名前で指定した特性・わざ・進化方法は、その作品に登録済みでなければ error になる。
  過去作から写さない。先に register_ability・register_move で、その作品の値を入れる。
- copy_* と inherit_* は過去作の値の流用。出典で確かめた作品にだけ使う。
- 多くの行を入れるときは batch で1つにまとめる（全部入るか、全部入らないか。
  ビューの作り直しも最後に1回）。
"""

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False,
                        openWorldHint=False)
UPSERT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                         openWorldHint=False)
DELETE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True,
                         openWorldHint=False)

# batch の間は、書き込みのツールが呼び出しをここへためるだけにする。
PLAN: ContextVar[list[Call] | None] = ContextVar('pkdb_mcp_plan', default=None)

Source = Annotated[str, Field(min_length=3, max_length=500,
                              description='値の出典（URL・資料名・ゲーム内の確認など）。entry_log に残る')]
Ndex = Annotated[str, Field(pattern=r'^\d{1,4}$', description='全国図鑑番号（例: 0025）')]
Form = Annotated[str, Field(pattern=r'^\d{1,2}$', description='フォームID（基本の姿は 00）')]
TitleGroup = Annotated[str, Field(pattern=r'^\d{3}$', description='作品グループID（3桁、例: 090）')]
Stat = Annotated[int, Field(ge=1, le=255)]
OptText = Annotated[str | None, Field(description='空なら null')]


@asynccontextmanager
async def lifespan(server):
    await anyio.to_thread.run_sync(db.open_pool)
    log.info('pkdb-mcp started (issuer %s)', ISSUER)
    try:
        yield {}
    finally:
        await anyio.to_thread.run_sync(db.close_pool)


def _auth():
    if not ISSUER:
        raise SystemExit('PKDB_MCP_ISSUER is required')
    return AuthSettings(issuer_url=ISSUER, resource_server_url=f'{PUBLIC_URL}/mcp',
                        validate_token_resource=False)


mcp = MCPServer(
    name='pkdb',
    title='ポケモンDB',
    instructions=INSTRUCTIONS,
    version='1.0.0',
    token_verifier=auth.AuthentikTokenVerifier(ISSUER, CLIENT_ID) if ISSUER else None,
    auth=_auth() if ISSUER else None,
    lifespan=lifespan,
)


async def _write(source, calls):
    plan = PLAN.get()
    if plan is not None:
        plan.extend(calls)
        return {'queued': [call.function for call in calls]}
    return await _execute(source, calls)


async def _execute(source, calls):
    actor = auth.actor(get_access_token())
    try:
        results = await anyio.to_thread.run_sync(db.execute, actor, source, True, calls)
    except db.DbError as error:
        raise ToolError(str(error)) from None
    return {'results': results}


# ---- 読む ------------------------------------------------------------------

@mcp.tool(annotations=READ)
async def describe_tables(
        table: Annotated[str | None, Field(description='表の名前。省くと表の一覧')] = None,
) -> dict[str, Any]:
    """pokemondb の表・マテリアライズドビューの一覧、または1つの表の列と説明を返す。"""
    if table:
        statement = """
            SELECT a.attname AS column, format_type(a.atttypid, a.atttypmod) AS type,
                   NOT a.attnotnull AS nullable, col_description(c.oid, a.attnum) AS comment
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
            WHERE n.nspname = 'pokemondb' AND c.relname = %(table)s
            ORDER BY a.attnum"""
    else:
        statement = """
            SELECT c.relname AS table, CASE c.relkind WHEN 'm' THEN 'view' ELSE 'table' END AS kind,
                   c.reltuples::bigint AS approx_rows, obj_description(c.oid) AS comment
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'pokemondb' AND c.relkind IN ('r', 'm')
            ORDER BY c.relname"""
    columns, rows, _ = await _read(statement, {'table': table})
    if table and not rows:
        raise ToolError(f'表 {table} はありません')
    return {'columns': columns, 'rows': rows}


@mcp.tool(annotations=READ)
async def query(
        sql: Annotated[str, Field(description='SELECT 文（読み取り専用。search_path は pokemondb）')],
        max_rows: Annotated[int, Field(ge=1, le=db.QUERY_MAX_ROWS)] = 200,
) -> dict[str, Any]:
    """読み取り専用のトランザクションで SQL を実行し、結果の行を返す（10秒・最大500行）。"""
    columns, rows, truncated = await _read(sql, None, max_rows)
    return {'columns': columns, 'rows': rows, 'truncated': truncated}


@mcp.tool(annotations=READ)
async def recent_changes(
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        actor: Annotated[str | None, Field(description='登録者で絞る（例: mcp:akadmin）')] = None,
) -> dict[str, Any]:
    """登録の記録（entry_log）を新しい順に返す。detail は before/after。"""
    columns, rows, _ = await _read(
        """SELECT id, created_at, actor, db_role, source, action, detail FROM entry_log
           WHERE %(actor)s::text IS NULL OR actor = %(actor)s
           ORDER BY id DESC LIMIT %(limit)s""", {'actor': actor, 'limit': limit})
    return {'columns': columns, 'rows': rows}


async def _read(statement, params, max_rows=db.QUERY_MAX_ROWS):
    try:
        columns, rows, truncated = await anyio.to_thread.run_sync(db.read, statement, params, max_rows)
    except db.DbError as error:
        raise ToolError(str(error)) from None
    return columns, [_plain(row) for row in rows], truncated


def _plain(row):
    return {key: value if isinstance(value, (str, int, float, bool, dict, list, type(None)))
            else str(value) for key, value in row.items()}


# ---- 作品 ------------------------------------------------------------------

@mcp.tool(annotations=WRITE)
async def register_title(source: Source, title_group_id: TitleGroup, title_name: str,
                         generation: Annotated[int, Field(ge=1, le=99)],
                         region: OptText = None) -> dict[str, Any]:
    """新しい作品グループ（世代の作品のまとまり）を足す。"""
    return await _write(source, [Call('register_title', [title_group_id, title_name, generation, region])])


@mcp.tool(annotations=UPSERT)
async def update_title(source: Source, title_group_id: TitleGroup, title_name: str,
                       generation: Annotated[int, Field(ge=1, le=99)],
                       region: OptText = None) -> dict[str, Any]:
    """作品グループの名前・世代・地方を直す。"""
    return await _write(source, [Call('update_title', [title_group_id, title_name, generation, region])])


@mcp.tool(annotations=UPSERT)
async def save_title_solo(source: Source,
                          title_id: Annotated[str, Field(pattern=r'^\d{4}$', description='作品ID（4桁）')],
                          title_name: str, title_group_id: TitleGroup,
                          release_year: int | None = None, release_month: int | None = None,
                          release_date: int | None = None) -> dict[str, Any]:
    """作品1本（発売年月日つき）を足す・直す。同じ4桁IDなら置き換える。"""
    return await _write(source, [Call('save_title_solo', [title_id, title_name, title_group_id,
                                                          release_year, release_month, release_date])])


# ---- ポケモン --------------------------------------------------------------

@mcp.tool(annotations=WRITE)
async def register_pokemon(
        source: Source, ndex_number: Ndex, name: str, form_id: Form, title_group_id: TitleGroup,
        type_1: str, h: Stat, a: Stat, b: Stat, c: Stat, d: Stat, s: Stat, ability_1: str,
        form_name: OptText = None,
        gender: Annotated[str | None, Field(description='性別で姿が分かれるときだけ（♂・♀）')] = None,
        type_2: OptText = None, ability_2: OptText = None, ability_h: OptText = None,
        english_name: OptText = None,
        before_ndex_number: Annotated[str | None, Field(description='進化前の図鑑番号')] = None,
        before_form_id: OptText = None, evolution_method: OptText = None,
        aliases: list[str] | None = None) -> dict[str, Any]:
    """新しいポケモン・新しい姿・既存ポケモンの新作での値（タイプ・種族値・特性）を入れる。

    既にある（図鑑番号・フォーム・作品）は error（直すのは update_pokemon）。
    特性は、その作品に登録済みの名前だけ。
    """
    return await _write(source, [Call('register_pokemon', [
        ndex_number, name, form_id, form_name, gender, title_group_id, type_1, type_2,
        h, a, b, c, d, s, ability_1, ability_2, ability_h, english_name,
        before_ndex_number, before_form_id, evolution_method, aliases or None])])


@mcp.tool(annotations=UPSERT)
async def update_pokemon(source: Source, ndex_number: Ndex, form_id: Form, title_group_id: TitleGroup,
                         type_1: str, h: Stat, a: Stat, b: Stat, c: Stat, d: Stat, s: Stat,
                         ability_1: str, type_2: OptText = None, ability_2: OptText = None,
                         ability_h: OptText = None) -> dict[str, Any]:
    """ある作品でのタイプ・種族値・特性を直す（直す前の値は entry_log に残る）。"""
    return await _write(source, [Call('update_pokemon', [
        ndex_number, form_id, title_group_id, type_1, type_2, h, a, b, c, d, s,
        ability_1, ability_2, ability_h])])


@mcp.tool(annotations=UPSERT)
async def update_pokemon_names(
        source: Source, ndex_number: Ndex, form_id: Form,
        jpn: OptText = None, eng: OptText = None, fra: OptText = None, ger: OptText = None,
        ita: OptText = None, kor: OptText = None, spa: OptText = None, chs: OptText = None,
        cht: OptText = None, romaji_trademarked: OptText = None, romaji_hepburn: OptText = None,
        form_name: OptText = None, gender: OptText = None,
        aliases: Annotated[list[str] | None, Field(description='あだ名の一覧（置き換え）')] = None,
) -> dict[str, Any]:
    """名前・各言語名・姿の名前・性別・あだ名を直す。言語名は基本の姿（00）にだけ持つ。"""
    return await _write(source, [Call('update_pokemon_names', [
        ndex_number, form_id, jpn, eng, fra, ger, ita, kor, spa, chs, cht,
        romaji_trademarked, romaji_hepburn, form_name, gender, aliases or None])])


@mcp.tool(annotations=WRITE)
async def copy_pokemon_status(source: Source, ndex_number: Ndex, from_form: Form,
                              from_title: TitleGroup, to_forms: list[str], to_title: TitleGroup,
                              overwrite: bool = False) -> dict[str, Any]:
    """ある姿・作品の値を、同じポケモンの複数の姿・作品へ写す。出典で同じと確かめたときだけ。"""
    return await _write(source, [Call('copy_pokemon_status', [
        ndex_number, from_form, from_title, to_forms, to_title, overwrite])])


# ---- わざ・特性 ------------------------------------------------------------

Category = Literal['物理', '特殊', '変化']


@mcp.tool(annotations=WRITE)
async def register_move(source: Source, name: str, title_group_id: TitleGroup, type: str,
                        category: Category, pp: Annotated[int, Field(ge=1, le=64)],
                        power: int | None = None, accuracy: int | None = None,
                        priority: Annotated[int, Field(ge=-7, le=5)] = 0,
                        move_id: Annotated[str | None, Field(description='既存のわざIDを指定して、その作品の行を足す')] = None,
                        english_name: OptText = None, target: OptText = None,
                        effect_chance: int | None = None, description: OptText = None,
                        notes: OptText = None) -> dict[str, Any]:
    """わざの、ある作品での値を足す。新しい名前なら新しいわざID を採る。"""
    return await _write(source, [Call('register_move', [
        move_id or '', name, title_group_id, english_name, type, category, power, accuracy,
        pp, priority, target, effect_chance, description, notes])])


@mcp.tool(annotations=UPSERT)
async def update_move(source: Source, move_id: str, title_group_id: TitleGroup, name: str,
                      type: str, category: Category, pp: Annotated[int, Field(ge=1, le=64)],
                      power: int | None = None, accuracy: int | None = None,
                      priority: Annotated[int, Field(ge=-7, le=5)] = 0,
                      english_name: OptText = None, target: OptText = None,
                      effect_chance: int | None = None, description: OptText = None,
                      notes: OptText = None) -> dict[str, Any]:
    """わざの1作品ぶんの行を直す。"""
    return await _write(source, [Call('update_move', [
        move_id, title_group_id, name, english_name, type, category, power, accuracy,
        pp, priority, target, effect_chance, description, notes])])


@mcp.tool(annotations=DELETE)
async def delete_move_title(source: Source, move_id: str, title_group_id: TitleGroup) -> dict[str, Any]:
    """わざの1作品ぶんの行を消す（覚えるポケモンがいれば消せない）。"""
    return await _write(source, [Call('delete_move_title', [move_id, title_group_id])])


@mcp.tool(annotations=WRITE)
async def inherit_moves(source: Source, from_title: TitleGroup, to_title: TitleGroup,
                        overwrite: bool = False) -> dict[str, Any]:
    """ある作品のわざを、まとめて別の作品へ写す（新作で値が同じと確かめたときだけ）。"""
    return await _write(source, [Call('inherit_moves', [from_title, to_title, overwrite])])


@mcp.tool(annotations=WRITE)
async def register_ability(source: Source, name: str, title_group_id: TitleGroup,
                           ability_id: Annotated[str | None, Field(description='既存の特性IDを指定して、その作品の行を足す')] = None,
                           english_name: OptText = None, description: OptText = None) -> dict[str, Any]:
    """特性の、ある作品での行を足す。新しい名前なら新しい特性ID を採る。"""
    return await _write(source, [Call('register_ability', [
        ability_id or '', name, title_group_id, english_name, description])])


@mcp.tool(annotations=UPSERT)
async def update_ability(source: Source, ability_id: str, title_group_id: TitleGroup, name: str,
                         english_name: OptText = None, description: OptText = None) -> dict[str, Any]:
    """特性の1作品ぶんの行（名前・英語名・説明）を直す。"""
    return await _write(source, [Call('update_ability', [
        ability_id, title_group_id, name, english_name, description])])


@mcp.tool(annotations=WRITE)
async def inherit_abilities(source: Source, from_title: TitleGroup, to_title: TitleGroup,
                            overwrite: bool = False) -> dict[str, Any]:
    """ある作品の特性を、まとめて別の作品へ写す（新作で値が同じと確かめたときだけ）。"""
    return await _write(source, [Call('inherit_abilities', [from_title, to_title, overwrite])])


# ---- 覚えわざ --------------------------------------------------------------

class LearnRow(BaseModel):
    move_name: str
    method_name: str = Field(description='覚え方（レベルアップ・わざマシン・タマゴわざ など）')
    level: int | None = None
    learn_order: int | None = None
    source: str | None = Field(None, description='わざマシンの番号など、覚え方の補足')
    notes: str | None = None
    learn_id: int | None = Field(None, description='既存の行を直すときだけ')


@mcp.tool(annotations=UPSERT)
async def save_learnset(source: Source, ndex_number: Ndex, form_id: Form, title_group_id: TitleGroup,
                        rows: list[LearnRow],
                        delete_ids: Annotated[list[int] | None, Field(description='消す行の learn_id')] = None,
                        ) -> dict[str, Any]:
    """1匹・1姿・1作品の覚えわざをまとめて足す・直す・消す。わざはその作品に登録済みの名前だけ。"""
    return await _write(source, [Call('save_learnset', [
        ndex_number, form_id, title_group_id,
        db.jsonb([row.model_dump(exclude_none=True) for row in rows]), delete_ids or None])])


@mcp.tool(annotations=WRITE)
async def copy_learnset(source: Source, ndex_number: Ndex, form_id: Form, from_title: TitleGroup,
                        to_title: TitleGroup, overwrite: bool = False) -> dict[str, Any]:
    """ある作品の覚えわざを、同じポケモンの別の作品へ写す（同じと確かめたときだけ）。"""
    return await _write(source, [Call('copy_learnset', [
        ndex_number, form_id, from_title, to_title, overwrite])])


# ---- 進化・図鑑・順位 ------------------------------------------------------

@mcp.tool(annotations=UPSERT)
async def set_evolution(source: Source, before_ndex_number: Ndex, before_form_id: Form,
                        after_ndex_number: Ndex, after_form_id: Form, method_name: str,
                        title_group_id: Annotated[str | None, Field(description='どの作品で分かるか')] = None,
                        ) -> dict[str, Any]:
    """進化の1段（進化前 → 進化後）を保存する。進化方法は登録済みの名前だけ。"""
    return await _write(source, [Call('set_evolution', [
        before_ndex_number, before_form_id, after_ndex_number, after_form_id,
        method_name, title_group_id])])


@mcp.tool(annotations=DELETE)
async def delete_evolution(source: Source, before_ndex_number: Ndex, before_form_id: Form,
                           after_ndex_number: Ndex, after_form_id: Form) -> dict[str, Any]:
    """進化の1段を消す。"""
    return await _write(source, [Call('delete_evolution', [
        before_ndex_number, before_form_id, after_ndex_number, after_form_id])])


@mcp.tool(annotations=UPSERT)
async def save_pokedex(source: Source, ndex_number: Ndex, form_id: Form, title_group_id: TitleGroup,
                       category: OptText = None,
                       height: Annotated[str | None, Field(description='m（例: 0.4）')] = None,
                       weight: Annotated[str | None, Field(description='kg（例: 6.0）')] = None,
                       gender_ratio: Annotated[int | None, Field(description='♀の割合（ゲーム内の値）')] = None,
                       egg_group_1: OptText = None, egg_group_2: OptText = None,
                       leveling_rate: int | None = None, catch_rate: int | None = None,
                       ev_h: int | None = None, ev_a: int | None = None, ev_b: int | None = None,
                       ev_c: int | None = None, ev_d: int | None = None, ev_s: int | None = None,
                       ) -> dict[str, Any]:
    """1つの姿の図鑑情報（分類・たかさ・おもさ・性別比・タマゴグループ・経験値タイプ・捕獲率・努力値）。"""
    return await _write(source, [Call('save_pokedex', [
        ndex_number, form_id, title_group_id, category, height, weight, gender_ratio,
        egg_group_1, egg_group_2, leveling_rate, catch_rate, ev_h, ev_a, ev_b, ev_c, ev_d, ev_s])])


@mcp.tool(annotations=UPSERT)
async def update_rdex(source: Source, ndex_number: Ndex, form_id: Form,
                      values: Annotated[dict[str, str | None], Field(description='{"地方の列名": "3桁の番号"}。渡した列だけ直す')],
                      ) -> dict[str, Any]:
    """地方図鑑番号を保存する。"""
    return await _write(source, [Call('update_rdex', [ndex_number, form_id, db.jsonb(values)])])


class RankRow(BaseModel):
    rank: int = Field(ge=1, le=99999)
    ndex: str = Field(pattern=r'^\d{1,4}$')
    form: str = Field('00', pattern=r'^\d{1,2}$')


@mcp.tool(annotations=UPSERT)
async def import_rankings(source: Source, title_group_id: TitleGroup,
                          battle_season: Annotated[int, Field(ge=1)],
                          battle_type: Annotated[str, Field(description='シングル・ダブル など')],
                          rows: list[RankRow]) -> dict[str, Any]:
    """1シーズンの使用率順位を取り込む（同じ作品・シーズン・形式の行は置き換え）。"""
    return await _write(source, [Call('import_rankings', [
        title_group_id, battle_season, battle_type, db.jsonb([row.model_dump() for row in rows])])])


# ---- まとめて --------------------------------------------------------------

class BatchCall(BaseModel):
    tool: str = Field(description='書き込みのツール名（register_move など）')
    arguments: dict[str, Any] = Field(description='そのツールの引数（source は省いてよい）')


# batch から呼べるツール（書き込みだけ）。
WRITE_TOOLS = frozenset({
    'register_title', 'update_title', 'save_title_solo',
    'register_pokemon', 'update_pokemon', 'update_pokemon_names', 'copy_pokemon_status',
    'register_move', 'update_move', 'delete_move_title', 'inherit_moves',
    'register_ability', 'update_ability', 'inherit_abilities',
    'save_learnset', 'copy_learnset', 'set_evolution', 'delete_evolution',
    'save_pokedex', 'update_rdex', 'import_rankings',
})


@mcp.tool(annotations=WRITE)
async def batch(source: Source, calls: Annotated[list[BatchCall], Field(min_length=1, max_length=500)],
                ) -> dict[str, Any]:
    """書き込みのツールを順に、1つのトランザクションで呼ぶ。1件でも失敗すれば全部取り消す。"""
    plan = []
    token = PLAN.set(plan)
    try:
        for index, call in enumerate(calls):
            if call.tool not in WRITE_TOOLS:
                raise ToolError(f'{index + 1}件目: {call.tool} は書き込みのツールではありません')
            result = await mcp.call_tool(call.tool, {'source': source, **call.arguments})
            if getattr(result, 'is_error', False) or getattr(result, 'isError', False):
                text = ' '.join(getattr(block, 'text', '') for block in result.content)
                raise ToolError(f'{index + 1}件目（{call.tool}）: {text}')
    finally:
        PLAN.reset(token)
    return await _execute(source, plan)



@mcp.custom_route('/healthz', methods=['GET'])
async def healthz(request: Request):
    # プロセスが応答すれば 200（コンテナの healthcheck）。DB につながるかは db で返し、
    # 配備は db が true になるまで待つ。
    return JSONResponse({'ok': True, 'db': await anyio.to_thread.run_sync(db.healthy)})


def app():
    host = os.environ.get('PKDB_MCP_ALLOWED_HOST', '')
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(host),
        allowed_hosts=[host, '127.0.0.1:8080', 'localhost:8080'] if host else [],
        allowed_origins=[f'https://{host}'] if host else [])
    return mcp.streamable_http_app(transport_security=security, host='0.0.0.0')
