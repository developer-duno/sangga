# -*- coding: utf-8 -*-
"""실거래 지분 표시 칸 + 단가 계산에서만 제외 — 마이그레이션 2026-10-08a 의 불변식 (물결 0-2b PR①).

무엇을 막나
-----------
지분 거래(`transaction.is_share`)는 건물 일부 몫만 사고판 거래라 ㎡당 값이 일반 거래의 약 0.39배로
낮게 나온다(docs/research/share-deals-2026-10.md). 👤 결정(2026-10-08):
  · 실거래 목록(list_parcel_transactions)에는 **지우지 않고** 낸다 + is_share 칸
  · 참고 시세 사다리 L2·L4·L5·L6 · 구 층대 단가(mv_sigungu_tx_stats) · 동네 단가 흐름의
    단가·n·면적 중앙값에서는 **뺀다**
  · 동네 단가 흐름의 건수(n_all·floor_missing·ym_cnt·first_ym·last_ym)는 **그대로 센다**

⛔ 어느 것이 어긋나도 **에러가 안 난다** — 갈래 하나만 빠지면 그 단계의 밴드만 조용히 내려앉고,
   건수 칸에 조건이 붙으면 "그 해 N건"이 조용히 줄어든다. 그래서 글자로 못 박는다(CI 에 DB 없음).

여기서 보는 것
  1) 정본 정적 가드 — 갈래·칸마다 따로 판정한다(탐지 함수는 아래 작은 함수 · 양성 대조가 같은 함수를 지난다)
  2) 마이그레이션 — lock_timeout 이 begin 앞 · begin/commit · notify 는 commit 뒤 · api.transaction
     다시 만듦 · 다시 만든 함수·물질화뷰의 머리·본문·comment 가 정본과 글자 일치 · 권한
  3) backtest_price.py 의 TX_QUERY 도 지분을 뺀다(실행은 안 한다 — 성적표 v2 는 PR②)
  4) 로컬 PostgreSQL 이 있으면 실제로 돌려 본다(없으면 건너뜀 — CI 는 1)~3)만)

ⓘ 도우미는 형제 시험에서 **복사**해 왔다(import 안 함 — 시험끼리 얽히면 한쪽 고장이 다른 쪽을 가린다).
"""

import io
import os
import re
import shutil
import socket
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
MIG = os.path.join(ROOT, "supabase", "migrations", "2026-10-08a_transaction_share_flag.sql")
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import backtest_price  # noqa: E402
import post_load  # noqa: E402

LADDER = ("L2", "L4", "L5", "L6")
# 동네 단가 흐름 — 단가의 근거(지분 제외) / 건수(지분 포함)
YEARLY_EXCLUDE_SHARE = ("n", "median_unit_price", "p25_unit_price", "p75_unit_price", "median_area_m2")
YEARLY_COUNT_ALL = ("n_all", "floor_missing", "ym_cnt", "first_ym", "last_ym")

RE_LINE_COMMENT = re.compile(r"--[^\n]*")
# '지분 제외' 조건으로 인정하는 꼴 — `not t.is_share` · `t.is_share = false` · `t.is_share is false`
RE_SHARE_OUT = re.compile(r"\bnot\s+t\.is_share\b|\bt\.is_share\s*(?:=\s*false|is\s+false)\b", re.I)


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read().replace("\r\n", "\n")


def code(sql):
    """`--` 주석을 지운다 — 주석 속 글자(설명용)에 걸리면 가드가 거짓말을 한다."""
    return RE_LINE_COMMENT.sub("", sql)


def flat(sql):
    return re.sub(r"\s+", " ", code(sql)).strip()


def fn_block(name, sql):
    """`create or replace function <이름>(` 부터 `$$;` 까지(주석 포함 원문 — 머리 포함)."""
    m = re.search(r"(?im)^create\s+or\s+replace\s+function\s+{}\s*\(".format(re.escape(name)), sql)
    assert m, "함수 {} 를 못 찾았습니다".format(name)
    end = sql.index("$$;", sql.index("$$", m.end()) + 2)
    return sql[m.start():end + 3]


def stmt_at(pattern, sql):
    """줄머리 pattern 부터 작은따옴표 밖의 첫 `;` 까지(여러 줄 comment 문장도 통째로)."""
    m = re.search(pattern, sql, re.M)
    assert m, pattern
    i, quoted = m.start(), False
    while True:
        c = sql[i]
        if c == "'":
            quoted = not quoted
        elif c == ";" and not quoted:
            return sql[m.start():i + 1]
        i += 1


def mv_select(name, sql):
    """`create materialized view [if not exists] <name> as` 다음부터 `;` 까지(본문만)."""
    m = re.search(r"(?im)^create materialized view (?:if not exists )?{} as\n".format(name), sql)
    assert m, name
    return sql[m.end():sql.index(";", m.end()) + 1]


# ── 탐지 함수 (가드 본체와 양성 대조가 같은 함수를 지난다) ────────────────────


def ladder_branches(sql):
    """list_price_bands 본문에서 사다리 갈래별 select 문(주석 제거)을 {'L2': …} 로.

    못 보는 것: 갈래를 `select 'L2' …` 꼴이 아니게(변수·하위질의로) 만들면 갈래를 못 찾는다
    → 그때는 빈 갈래로 '없음' 판정이 나서 **빨강 쪽**으로 틀린다(빠뜨리는 쪽이 아니다).
    """
    body = code(fn_block("list_price_bands", sql))
    out = {}
    for lvl in LADDER:
        m = re.search(r"select\s+'{}'".format(lvl), body)
        if not m:
            continue
        nxt = re.search(r"\bunion\s+all\b|\)\s*c\b", body[m.end():])
        out[lvl] = body[m.start(): m.end() + (nxt.start() if nxt else len(body))]
    return out


def ladder_problems(sql):
    """갈래마다 따로 — 지분 제외가 없는 갈래·아예 못 찾은 갈래를 돌려준다."""
    br = ladder_branches(sql)
    probs = []
    for lvl in LADDER:
        if lvl not in br:
            probs.append("{} 갈래를 못 찾았다".format(lvl))
        elif not RE_SHARE_OUT.search(br[lvl]):
            probs.append("{} 갈래에 지분 제외가 없다".format(lvl))
    return probs


def split_top(select_list):
    """최상위 쉼표로 나눈다(괄호 안 쉼표는 안 나눈다)."""
    parts, depth, cur = [], 0, []
    for ch in select_list:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def yearly_columns(sql):
    """mv_sigungu_tx_yearly 의 select 목록 → {별칭: 식} 과 where 절(주석 제거·한 줄로)."""
    body = flat(mv_select("mv_sigungu_tx_yearly", sql))
    m = re.match(r"select (.*) from transaction t (.*)$", body)
    assert m, body[:120]
    cols = {}
    for item in split_top(m.group(1)):
        a = re.search(r"\bas\s+(\w+)$", item)
        cols[a.group(1) if a else item] = item
    return cols, m.group(2)


def yearly_problems(sql):
    cols, tail = yearly_columns(sql)
    probs = []
    for name in YEARLY_EXCLUDE_SHARE:
        if name not in cols:
            probs.append("{} 칸이 없다".format(name))
        elif not RE_SHARE_OUT.search(cols[name]):
            probs.append("{} 에 지분 제외가 없다".format(name))
    for name in YEARLY_COUNT_ALL:
        if name not in cols:
            probs.append("{} 칸이 없다".format(name))
        elif "is_share" in cols[name]:
            probs.append("{} 는 건수라 지분도 세야 한다".format(name))
    if "is_share" in tail:
        probs.append("where·group by 에 is_share 가 있다 — 건수까지 줄어든다")
    return probs


def stats_problems(sql):
    body = flat(mv_select("mv_sigungu_tx_stats", sql))
    where = body[body.index(" where "):]
    return [] if RE_SHARE_OUT.search(where) else ["mv_sigungu_tx_stats 에 지분 제외가 없다"]


def parcel_list_problems(sql):
    """목록은 지분도 그대로 낸다 — 거르면 안 되고, is_share 를 내야 한다."""
    body = code(fn_block("list_parcel_transactions", sql))
    probs = []
    head = body[:body.index("$$")]
    if not re.search(r"\bis_share\s+boolean\b", head):
        probs.append("반환 칸에 is_share boolean 이 없다")
    run = body[body.index("$$"):]
    if "t.is_share" not in run.split("from transaction t")[0]:
        probs.append("select 목록에 t.is_share 가 없다")
    if "is_share" in run.split("from transaction t", 1)[1]:
        probs.append("목록이 지분 거래를 거른다 — 지우지 않고 내야 한다")
    return probs


# ── 1. 정본 정적 가드 ────────────────────────────────────────────────────────


def test_정본_칸이_있다():
    src = flat(read(SCHEMA))
    assert "alter table transaction add column if not exists is_share boolean not null default false;" in src
    assert "comment on column transaction.is_share is" in src


def test_정본_사다리_네_갈래_모두_지분_제외():
    assert ladder_problems(read(SCHEMA)) == []


def test_정본_동네_단가_흐름은_단가만_빼고_건수는_센다():
    assert yearly_problems(read(SCHEMA)) == []


def test_정본_구_층대_단가는_지분_제외():
    assert stats_problems(read(SCHEMA)) == []


def test_정본_실거래_목록은_지분도_낸다():
    assert parcel_list_problems(read(SCHEMA)) == []
    api = fn_block("api.list_parcel_transactions", read(SCHEMA))
    assert re.search(r"\bis_share\s+boolean\b", api)
    assert "select * from public.list_parcel_transactions(pnu)" in api


def test_정본_반경_이웃_표는_거래_조건을_좁히지_않는다():
    """mv_tx_parcel_geog 는 바꾸지 않는다(L4·L5 가 거래 쪽에서 지분을 거른다)."""
    assert "is_share" not in flat(mv_select("mv_tx_parcel_geog", read(SCHEMA)))


# ── 1-1. 양성 대조 — 하나만 빠진 변형도 잡는다 ──────────────────────────────


@pytest.mark.parametrize("lvl", LADDER)
def test_돌연변이_갈래_하나만_지분_제외를_빼도_잡힌다(lvl):
    src = read(SCHEMA)
    body = fn_block("list_price_bands", src)
    m = re.search(r"select '{}'".format(lvl), body)
    nxt = body.find("and not t.is_share", m.end())
    assert nxt != -1
    bad_body = body[:nxt] + body[nxt + len("and not t.is_share"):]
    bad = src.replace(body, bad_body, 1)
    assert ladder_problems(bad) == ["{} 갈래에 지분 제외가 없다".format(lvl)]


def test_돌연변이_갈래의_조건을_주석으로_죽여도_잡힌다():
    src = read(SCHEMA)
    body = fn_block("list_price_bands", src)
    i = body.index("and not t.is_share", body.index("select 'L5'"))
    bad_body = body[:i] + "-- " + body[i:]
    assert "L5 갈래에 지분 제외가 없다" in ladder_problems(src.replace(body, bad_body, 1))


def test_변형_꼴_is_false_도_지분_제외로_인정한다():
    src = read(SCHEMA)
    body = fn_block("list_price_bands", src)
    i = body.index("and not t.is_share", body.index("select 'L4'"))
    alt = body[:i] + "and t.is_share is false" + body[i + len("and not t.is_share"):]
    assert ladder_problems(src.replace(body, alt, 1)) == []


@pytest.mark.parametrize("col", YEARLY_EXCLUDE_SHARE)
def test_돌연변이_동네_흐름_단가_칸_하나에서_지분_제외를_빼면_잡힌다(col):
    src = read(SCHEMA)
    block = mv_select("mv_sigungu_tx_yearly", src)
    lines = block.split("\n")
    # 그 칸의 filter 줄 = 별칭이 붙은 줄(같은 줄 또는 바로 윗줄 다음)
    idx = next(i for i, ln in enumerate(lines) if re.search(r"\bas {}\b".format(col), ln))
    j = idx if "not t.is_share" in lines[idx] else idx - 1
    assert "not t.is_share" in lines[j]
    lines[j] = lines[j].replace(" and not t.is_share", "", 1)
    bad = src.replace(block, "\n".join(lines), 1)
    assert yearly_problems(bad) == ["{} 에 지분 제외가 없다".format(col)]


@pytest.mark.parametrize("col", ["n_all", "floor_missing"])
def test_돌연변이_건수_칸에_지분_제외를_걸면_잡힌다(col):
    src = read(SCHEMA)
    block = mv_select("mv_sigungu_tx_yearly", src)
    if col == "n_all":
        bad_block = block.replace("count(*)::int ", "count(*) filter (where not t.is_share)::int ", 1)
    else:
        bad_block = block.replace("(where t.floor_no is null)", "(where t.floor_no is null and not t.is_share)", 1)
    assert bad_block != block
    assert yearly_problems(src.replace(block, bad_block, 1)) == [
        "{} 는 건수라 지분도 세야 한다".format(col)]


def test_돌연변이_동네_흐름_where_에_걸면_잡힌다():
    src = read(SCHEMA)
    block = mv_select("mv_sigungu_tx_yearly", src)
    bad_block = block.replace("where t.tx_type = '집합'", "where t.tx_type = '집합' and not t.is_share", 1)
    assert bad_block != block
    assert "where·group by 에 is_share 가 있다 — 건수까지 줄어든다" in yearly_problems(
        src.replace(block, bad_block, 1))


def test_돌연변이_구_층대_단가에서_빼면_잡힌다():
    src = read(SCHEMA)
    block = mv_select("mv_sigungu_tx_stats", src)
    bad = src.replace(block, block.replace("  and not t.is_share\n", "", 1), 1)
    assert stats_problems(bad)


def test_돌연변이_실거래_목록이_지분을_거르면_잡힌다():
    src = read(SCHEMA)
    body = fn_block("list_parcel_transactions", src)
    bad_body = body.replace("and t.contract_ym >= '202401'",
                            "and t.contract_ym >= '202401'\n    and not t.is_share", 1)
    assert bad_body != body
    assert parcel_list_problems(src.replace(body, bad_body, 1)) == [
        "목록이 지분 거래를 거른다 — 지우지 않고 내야 한다"]


# ── 2. 마이그레이션 ──────────────────────────────────────────────────────────


def _at(pattern, sql):
    m = re.search(pattern, sql, re.M)
    assert m, pattern
    return m.start()


def test_마이그_잠금_시간이_begin_앞이고_한_덩어리다():
    src = code(read(MIG))
    lt = _at(r"^set lock_timeout = '2s';", src)
    b = _at(r"^begin;", src)
    c = _at(r"^commit;", src)
    n = _at(r"^notify pgrst, 'reload schema';", src)
    assert lt < b < c < n
    assert len(re.findall(r"(?m)^begin;", src)) == 1 and len(re.findall(r"(?m)^commit;", src)) == 1
    first_ddl = _at(r"^(alter|drop|create|comment|grant|revoke|analyze) ", src)
    assert b < first_ddl
    assert "concurrently" not in src[b:c]
    last_ddl = max(m.start() for m in re.finditer(
        r"(?m)^(alter|drop|create|comment|grant|revoke|analyze) ", src))
    assert last_ddl < c


def test_마이그_칸_추가_다음에_api_거울_뷰를_다시_만든다():
    src = code(read(MIG))
    alter = src.index("alter table transaction\n  add column if not exists is_share boolean not null default false;")
    view = src.index("create or replace view api.transaction      as select * from public.transaction;")
    assert alter < view
    tail = flat(src[view:])
    assert "revoke all on api.transaction from public, anon, authenticated;" in tail
    assert "grant select, insert, update, delete on api.transaction to service_role;" in tail
    assert not re.search(r"grant [^;]*on api\.transaction to [^;]*\banon\b", flat(src))


def test_마이그_목록_함수는_api_먼저_지우고_다시_만든다():
    src = code(read(MIG))
    a = src.index("drop function if exists api.list_parcel_transactions(text);")
    p = src.index("drop function if exists public.list_parcel_transactions(text);")
    mk = src.index("create or replace function list_parcel_transactions(pnu text)")
    mk_api = src.index("create or replace function api.list_parcel_transactions(pnu text)")
    assert a < p < mk < mk_api


@pytest.mark.parametrize("name", ["list_parcel_transactions", "api.list_parcel_transactions",
                                  "list_price_bands"])
def test_마이그_다시_만든_함수가_정본과_글자_일치(name):
    """머리(security definer·search_path·stable)까지 — create or replace 는 머리를 덮어쓴다."""
    assert fn_block(name, read(MIG)) == fn_block(name, read(SCHEMA))


@pytest.mark.parametrize("pattern", [
    r"^comment on function list_parcel_transactions\(text\) is",
    r"^comment on function list_price_bands\(text\) is",
    r"^comment on materialized view mv_sigungu_tx_stats is",
    r"^comment on materialized view mv_sigungu_tx_yearly is",
    r"^comment on column transaction\.is_share is",
    r"^create unique index if not exists idx_msts_key",
    r"^create unique index if not exists idx_msty_key",
])
def test_마이그_comment_와_색인이_정본과_글자_일치(pattern):
    assert stmt_at(pattern, read(MIG)) == stmt_at(pattern, read(SCHEMA))


@pytest.mark.parametrize("mv", ["mv_sigungu_tx_stats", "mv_sigungu_tx_yearly"])
def test_마이그_물질화뷰는_떨어뜨린_뒤_정본과_같은_본문으로_굽는다(mv):
    mig = read(MIG)
    src = code(mig)
    drop = src.index("drop materialized view if exists {};".format(mv))
    make = src.index("create materialized view {} as".format(mv))
    assert drop < make
    assert "create materialized view if not exists {}".format(mv) not in src, (
        "다시 굽는 판에서 if not exists 는 아무 일도 안 한다")
    assert mv_select(mv, mig) == mv_select(mv, read(SCHEMA))
    after = flat(src[make:])
    assert "analyze {};".format(mv) in after
    assert "revoke all on {} from public, anon, authenticated;".format(mv) in after


def test_마이그_권한_api_에만_열고_public_은_닫는다():
    src = flat(read(MIG))
    rv = src.index("revoke all on function api.list_parcel_transactions(text) from public, anon, authenticated;")
    gr = src.index("grant execute on function api.list_parcel_transactions(text) to anon, authenticated;")
    assert rv < gr
    assert "revoke all on function list_parcel_transactions(text) from public, anon, authenticated;" in src
    assert "revoke all on function list_price_bands(text) from public, anon, authenticated;" in src
    grants = re.findall(r"grant execute on function ([\w.]+)\([^)]*\) to ([^;]+);", src)
    assert grants == [("api.list_parcel_transactions", "anon, authenticated")]


def test_마이그_정적_가드도_통과한다():
    mig = read(MIG)
    assert ladder_problems(mig) == []
    assert yearly_problems(mig) == []
    assert stats_problems(mig) == []
    assert parcel_list_problems(mig) == []


def test_공개_호출_허용_목록은_그대로다():
    """함수 이름·서명이 안 바뀌었다 — 허용 목록에 새 이름이 생기지 않는다."""
    assert "api.list_parcel_transactions" in post_load.ANON_CALLABLE_ALLOWLIST
    assert "api.list_price_bands" in post_load.ANON_CALLABLE_ALLOWLIST
    assert "mv_sigungu_tx_stats" in post_load.REFRESH_MVS
    assert "mv_sigungu_tx_yearly" in post_load.REFRESH_MVS


# ── 3. 성적표 코드 ───────────────────────────────────────────────────────────


def tx_query_problems(query):
    return [] if re.search(r"(?:^|&)is_share=(?:is|eq)\.false(?:&|$)", query) else [
        "TX_QUERY 가 지분 거래를 안 뺀다"]


def test_백테스트_조회가_지분을_뺀다():
    assert tx_query_problems(backtest_price.TX_QUERY) == []


def test_돌연변이_백테스트_조회에서_빼면_잡힌다():
    bad = backtest_price.TX_QUERY.replace("&is_share=is.false", "")
    assert bad != backtest_price.TX_QUERY
    assert tx_query_problems(bad)


# ── 4. 로컬 PostgreSQL 로 실제 실행 (없으면 건너뜀 — 형제 test_district_openclose_migration 과 같은 방식) ──

# 정본 표 정의 + 흉내(PostGIS 없음 — geography 는 text 도메인으로, 좌표는 비워 반경 단계는 건너뛴다).
SHIM = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role; end if;
end $$;
create schema api;
create domain geography as text;
create table parcel (pnu char(19) primary key, geom text);
create table building_floor (pnu char(19), floor_no smallint);
create table price_gate_sigungu (sigungu_code text primary key, gate_pass boolean);
create table mv_open_sigungu (sigungu_code char(5), sigungu_nm text);
create materialized view mv_tx_parcel_geog as select pnu, geom::geography as geog from parcel;
"""


def _old_state(schema_sql):
    """적용 **전** 라이브와 같은 모양 — 정본에서 is_share 를 걷어낸 표·뷰·함수."""
    table = stmt_at(r"^create table if not exists transaction \(", schema_sql)
    pfb = fn_block("price_floor_band", schema_sql)
    old = []
    old.append(table)
    old.append("create or replace view api.transaction as select * from public.transaction;")
    for mv in ("mv_sigungu_tx_stats", "mv_sigungu_tx_yearly"):
        body = mv_select(mv, schema_sql)
        body = body.replace("\n  and not t.is_share", "").replace(" and not t.is_share", "")
        old.append("create materialized view {} as\n{}".format(mv, body))
    old.append(stmt_at(r"^create unique index if not exists idx_msts_key", schema_sql))
    old.append(stmt_at(r"^create unique index if not exists idx_msty_key", schema_sql))
    old.append(pfb)
    old.append(fn_block("get_sigungu_tx_stats", schema_sql))
    old.append(fn_block("get_sigungu_tx_yearly", schema_sql))
    ptx = fn_block("list_parcel_transactions", schema_sql)
    ptx = ptx.replace(",\n  is_share     boolean", "").replace(",\n         t.is_share", "")
    old.append(ptx)
    api = fn_block("api.list_parcel_transactions", schema_sql).replace(",\n  is_share     boolean", "")
    old.append(api)
    joined = "\n".join(old)
    assert "is_share" not in joined
    return joined


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    psycopg2 = pytest.importorskip("psycopg2")
    initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
    if not initdb or not pg_ctl:
        pytest.skip("로컬 PostgreSQL(initdb·pg_ctl)이 없다 — CI 는 글자 가드(1~3)만 본다")
    data = str(tmp_path_factory.mktemp("pgdata"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    subprocess.run([initdb, "-D", data, "-U", "postgres", "-A", "trust", "-E", "UTF8",
                    "--no-locale"], check=True, capture_output=True)
    log = os.path.join(data, "log.txt")
    # ⛔ capture_output 금지 — 서버 자식이 파이프를 물려받아 run() 이 끝없이 기다린다(Windows 실측).
    subprocess.run([pg_ctl, "-D", data, "-l", log, "-w", "-t", "60", "-o",
                    "-p {} -c listen_addresses=127.0.0.1".format(port), "start"],
                   check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=120)
    try:
        conn = None
        for _ in range(30):
            try:
                conn = psycopg2.connect(host="127.0.0.1", port=port, user="postgres", dbname="postgres")
                break
            except psycopg2.OperationalError:
                time.sleep(0.5)
        assert conn is not None, "로컬 PostgreSQL 에 못 붙었다"
        conn.autocommit = True
        yield conn
        conn.close()
    finally:
        subprocess.run([pg_ctl, "-D", data, "-m", "fast", "-w", "stop"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)


PNU_A = "1168010100100010000"   # 강남 역삼동 1번지
PNU_B = "1168010100100020000"   # 같은 법정동 2번지(L6 후보)


@pytest.fixture(scope="module")
def cur(pg):
    c = pg.cursor()
    c.execute(SHIM)
    c.execute(_old_state(read(SCHEMA)))
    # 적용 전 거래 — 칸이 아직 없다. 집합 3건(단가 100·200·300만) + 지분이 될 1건(단가 10만).
    c.execute("""
      insert into transaction (tx_id, pnu, sigungu_code, floor_no, bld_area_m2, price_won, contract_ym, tx_type)
      values ('a', '{a}', '11680', 2, 10, 10000000, to_char(now(), 'YYYYMM'), '집합'),
             ('b', '{a}', '11680', 2, 10, 20000000, to_char(now(), 'YYYYMM'), '집합'),
             ('c', '{b}', '11680', 2, 10, 30000000, to_char(now(), 'YYYYMM'), '집합'),
             ('s', '{a}', '11680', 2, 50, 5000000,  to_char(now(), 'YYYYMM'), '집합'),
             ('m', null,  '11680', null, 10, 40000000, to_char(now(), 'YYYYMM'), '집합');
      insert into parcel values ('{a}', null), ('{b}', null);
      insert into building_floor values ('{a}', 2);
      insert into price_gate_sigungu values ('11680', true);
      insert into mv_open_sigungu values ('11680', '강남구');
      refresh materialized view mv_sigungu_tx_stats;
      refresh materialized view mv_sigungu_tx_yearly;
    """.format(a=PNU_A, b=PNU_B))
    c.execute("select sum(n_all), sum(n), sum(floor_missing) from mv_sigungu_tx_yearly")
    before = c.fetchone()
    c.execute(read(MIG))   # 마이그레이션 원문 그대로(set · begin … commit · notify)
    # 적재기가 다시 넣은 것처럼 지분 표시만 켠다(tx_id 그대로 = 같은 행 갱신).
    c.execute("update transaction set is_share = true where tx_id = 's'")
    c.execute("refresh materialized view concurrently mv_sigungu_tx_stats;"
              "refresh materialized view concurrently mv_sigungu_tx_yearly;")
    return c, before


class TestRealRun:
    def test_칸이_생기고_거울_뷰에도_보인다(self, cur):
        c, _ = cur
        c.execute("select table_schema, data_type, is_nullable, column_default from information_schema.columns "
                  "where table_name = 'transaction' and column_name = 'is_share' order by 1")
        assert c.fetchall() == [("api", "boolean", "YES", None),          # 뷰 칸은 늘 이렇게 보인다
                                ("public", "boolean", "NO", "false")]
        # 거울 뷰로 칸을 빼고 넣어도 표의 기본값(false)이 들어간다(옛 적재기 꼴의 upsert).
        c.execute("insert into api.transaction (tx_id, sigungu_code, price_won, contract_ym) "
                  "values ('v', '11680', 1, '200001')")
        c.execute("select is_share from transaction where tx_id = 'v'")
        assert c.fetchone() == (False,)
        c.execute("delete from transaction where tx_id = 'v'")

    def test_목록은_지분도_내고_칸을_붙인다(self, cur):
        c, _ = cur
        c.execute("select tx_type, is_share, price_won from api.list_parcel_transactions(%s) order by price_won",
                  (PNU_A,))
        assert c.fetchall() == [("집합", True, 5000000), ("집합", False, 10000000), ("집합", False, 20000000)]

    def test_구_층대_단가는_지분을_뺀다(self, cur):
        c, _ = cur
        c.execute("select n, median_unit_price from get_sigungu_tx_stats('11680') where floor_band = '2층'")
        assert c.fetchone() == (3, 2000000)

    def test_동네_흐름은_단가만_빼고_건수는_센다(self, cur):
        c, before = cur
        c.execute("select sum(n_all), sum(n), sum(floor_missing) from mv_sigungu_tx_yearly")
        after = c.fetchone()
        assert after[0] == before[0] == 5          # 건수 = 지분 포함 그대로
        assert after[2] == before[2] == 1          # 층 미상 그대로
        assert before[1] == 5 and after[1] == 4    # 단가 근거 수만 하나 준다
        # 단가 100·200·300·400만 + 지분 10만 → 지분을 빼면 가운데값 200만 → 250만
        c.execute("select median_unit_price, median_area_m2 from get_sigungu_tx_yearly('11680')")
        assert c.fetchone() == (2500000, 10)

    def test_사다리_L2_는_지분을_뺀다(self, cur):
        c, _ = cur
        c.execute("select status, stage, n, median from list_price_bands(%s)", (PNU_A,))
        assert c.fetchall() == [("ok", "L2", 2, 1500000)]

    def test_사다리_L6_도_지분을_뺀다(self, cur):
        """L2 후보를 없애면 L6(같은 법정동 · 같은 층대)으로 내려간다 — 거기서도 지분은 빠진다."""
        c, _ = cur
        c.execute("update transaction set floor_no = 3 where tx_id in ('a','b')")
        try:
            c.execute("select status, stage, n, median from list_price_bands(%s)", (PNU_A,))
            assert c.fetchall() == [("ok", "L6", 1, 3000000)]
        finally:
            c.execute("update transaction set floor_no = 2 where tx_id in ('a','b')")

    def test_권한_api_에만_열려_있다(self, cur):
        c, _ = cur
        c.execute("select has_function_privilege('anon', 'api.list_parcel_transactions(text)', 'execute'),"
                  "       has_function_privilege('anon', 'public.list_parcel_transactions(text)', 'execute'),"
                  "       has_function_privilege('anon', 'public.list_price_bands(text)', 'execute'),"
                  "       has_table_privilege('anon', 'api.transaction', 'select'),"
                  "       has_table_privilege('anon', 'mv_sigungu_tx_stats', 'select'),"
                  "       has_table_privilege('anon', 'mv_sigungu_tx_yearly', 'select')")
        assert c.fetchone() == (True, False, False, False, False, False)

    def test_두_번_돌려도_된다(self, cur):
        """칸 추가는 if not exists · 함수·뷰는 다시 만든다 — 끊긴 뒤 처음부터 다시 돌리는 길."""
        c, _ = cur
        c.execute(read(MIG))
        c.execute("select count(*) from transaction where is_share")
        assert c.fetchone()[0] == 1
