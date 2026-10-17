# -*- coding: utf-8 -*-
"""참고 시세는 같은 용도 묶음끼리 — 마이그레이션 2026-10-18a 의 불변식 (결정 0040).

무엇을 막나
-----------
참고 시세 사다리(list_price_bands L2·L4·L5·L6)와 구 단위 두 표가 용도를 안 가려 상가 층 시세에
업무·숙박 거래가 섞였다(강남 3층+ 업무 834만 vs 2종근생 1,621만). 👤 결정 0040:
  · 층마다 대장 용도 묶음(price_floor_use_group)과 **같은 묶음** 거래만 센다 — 네 갈래 **모두**
  · 주거 층 = floor_resid · 오피스텔 층 = floor_officetel · 묶음 모름 = no_use (값 안 냄)
  · 구 층대 단가·동네 단가 흐름 = 상가 거래만

⛔ 어느 것이 어긋나도 **에러가 안 난다** — 갈래 하나만 빠지면 그 단계만 조용히 섞이고(지분 때와
   같은 병), 요약표에서 조건이 빠지면 제목만 「상가 거래 기준」인 채 업무·숙박이 섞인다.

여기서 보는 것
  1) 정본 정적 가드 — 갈래·요약표·묶음 함수마다 따로 판정(탐지 함수 = 아래 작은 함수 · 양성 대조가 같은 함수를 지난다)
  2) 마이그레이션 — lock_timeout 이 begin 앞 · 한 덩어리 · notify 는 commit 뒤 · api 먼저 지움 ·
     함수·요약표의 머리·본문·comment 가 정본과 글자 일치 · 권한
  3) 로컬 PostgreSQL 이 있으면 실제로 돌려 본다(없으면 건너뜀 — CI 는 1)~2)만)

ⓘ 도우미는 형제 시험(test_transaction_share_migration)에서 **복사**해 왔다(import 안 함 — 시험끼리 얽히면
  한쪽 고장이 다른 쪽을 가린다).
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
MIG = os.path.join(ROOT, "supabase", "migrations", "2026-10-18a_price_use_group.sql")
# 적용 **전** 라이브의 참고 시세 본문(9칸) — 지분 제외 판.
MIG_PREV = os.path.join(ROOT, "supabase", "migrations", "2026-10-08a_transaction_share_flag.sql")
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

LADDER = ("L2", "L4", "L5", "L6")
GROUP_FNS = ("price_use_group_cd", "price_use_group_nm")
NEW_FNS = GROUP_FNS + ("price_floor_use_group",)
NEW_FN_SIGS = {
    "price_use_group_cd": "price_use_group_cd(text)",
    "price_use_group_nm": "price_use_group_nm(text)",
    "price_floor_use_group": "price_floor_use_group(char(19), smallint)",
}
NEW_STATUS = ("no_use", "floor_resid", "floor_officetel")

RE_LINE_COMMENT = re.compile(r"--[^\n]*")
# '같은 묶음' 조건으로 인정하는 꼴 — 양쪽 순서 둘 다
RE_GROUP = re.compile(
    r"\bprice_use_group_nm\s*\(\s*t\.main_use\s*\)\s*=\s*v_grp\b"
    r"|\bv_grp\s*=\s*price_use_group_nm\s*\(\s*t\.main_use\s*\)", re.I)
RE_SHOP = re.compile(r"\bprice_use_group_nm\s*\(\s*t\.main_use\s*\)\s*=\s*'shop'", re.I)


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

    못 보는 것: 갈래를 `select 'L2' …` 꼴이 아니게 만들면 못 찾는다 → '못 찾았다'로 **빨강 쪽**으로 틀린다.
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


def ladder_group_problems(sql):
    """갈래마다 따로 — 같은 묶음 조건이 없는 갈래·아예 못 찾은 갈래."""
    br = ladder_branches(sql)
    probs = []
    for lvl in LADDER:
        if lvl not in br:
            probs.append("{} 갈래를 못 찾았다".format(lvl))
        elif not RE_GROUP.search(br[lvl]):
            probs.append("{} 갈래에 같은 묶음 조건이 없다".format(lvl))
    return probs


def status_order_problems(sql):
    """판정 순서: gate_fail → 1층 → 지하·옥탑·미상 → 묶음(no_use·floor_resid·floor_officetel) → 사다리.

    못 보는 것: 순서는 글자 위치로만 본다 — if 안의 조건 글자(예: `v_grp = 'resid'`)가 맞는지는
    아래 status_condition_problems 와 로컬 PG 실행이 본다.
    """
    body = code(fn_block("list_price_bands", sql))
    marks = [
        ("gate_fail", r"'gate_fail'::text"),
        ("floor_1f", r"'floor_1f'::text"),
        ("no_evidence", r"'no_evidence'::text"),
        ("묶음 판정", r"v_grp\s*:=\s*price_floor_use_group\s*\(\s*v_pnu\s*,\s*v_floor\s*\)"),
        ("no_use", r"'no_use'::text"),
        ("floor_resid", r"'floor_resid'::text"),
        ("floor_officetel", r"'floor_officetel'::text"),
        ("사다리", r"v_band\s*:=\s*price_floor_band"),
    ]
    pos = []
    probs = []
    for name, pat in marks:
        found = [m.start() for m in re.finditer(pat, body)]
        if len(found) != 1:
            probs.append("{} 가 정확히 한 번이 아니다({})".format(name, len(found)))
            pos.append(None)
        else:
            pos.append(found[0])
    known = [p for p in pos if p is not None]
    if not probs and known != sorted(known):
        probs.append("판정 순서가 어긋났다")
    return probs


def status_condition_problems(sql):
    """새 status 셋이 각자 맞는 조건 뒤에 있나 — if 조건과 그 바로 뒤 return 의 status 를 짝짓는다."""
    body = flat(fn_block("list_price_bands", sql))
    want = {
        "no_use": r"if v_grp is null then return query select v_floor, 'no_use'::text",
        "floor_resid": r"if v_grp = 'resid' then return query select v_floor, 'floor_resid'::text",
        "floor_officetel": r"if v_grp = 'officetel' then return query select v_floor, 'floor_officetel'::text",
    }
    return ["{} 의 조건이 다르다".format(k) for k, pat in want.items() if pat not in body]


def use_group_column_problems(sql):
    """반환 칸 끝 use_group · ok·no_estimate 줄은 v_grp · 그 밖의 줄은 null::text."""
    blk = fn_block("list_price_bands", sql)
    head = blk[:blk.index("$$")]
    probs = []
    cols = re.findall(r"(?m)^\s+(\w+)\s+\w", head[head.index("returns table"):])
    if not cols or cols[-1] != "use_group":
        probs.append("반환 칸 끝이 use_group 이 아니다: {}".format(cols[-1:] or cols))
    if not re.search(r"\buse_group\s+text\b", head):
        probs.append("use_group text 가 없다")
    body = flat(blk[blk.index("$$"):])
    rows = re.findall(r"return query select (.*?);", body)
    for r in rows:
        last = r.rsplit(",", 1)[-1].strip()
        status = re.search(r"'(\w+)'::text", r)
        st = status.group(1) if status else "?"
        if st in ("ok", "no_estimate"):
            if last != "v_grp":
                probs.append("{} 줄의 use_group 이 v_grp 가 아니다".format(st))
        elif last != "null::text":
            probs.append("{} 줄의 use_group 이 null 이 아니다".format(st))
    if len(rows) != 8:
        probs.append("return query 가 8개가 아니다({})".format(len(rows)))
    return probs


def mv_shop_problems(sql):
    """구 단위 두 표 — where 에 상가 조건. 동네 흐름은 filter 가 아니라 where 여야 한다(건수도 상가만)."""
    probs = []
    for mv in ("mv_sigungu_tx_stats", "mv_sigungu_tx_yearly"):
        body = flat(mv_select(mv, sql))
        if " where " not in body:
            probs.append("{} 에 where 가 없다".format(mv))
            continue
        where = body[body.index(" where "):]
        where = where[:where.index(" group by ")] if " group by " in where else where
        if not RE_SHOP.search(where):
            probs.append("{} 의 where 에 상가 조건이 없다".format(mv))
    return probs


def group_fn_problems(sql):
    """묶음 함수 둘 — 인라인되게: language sql · immutable · strict 아님 · search_path·definer 없음."""
    probs = []
    for name in GROUP_FNS:
        head = flat(fn_block(name, sql).split("$$")[0])
        if " language sql " not in " " + head + " ":
            probs.append("{} 가 language sql 이 아니다".format(name))
        if " immutable" not in head:
            probs.append("{} 가 immutable 이 아니다".format(name))
        for bad in ("strict", "returns null on null input", "security definer", "set search_path"):
            if bad in head:
                probs.append("{} 에 {} 가 있다 — 인라인이 막히거나 NULL 규칙이 바뀐다".format(name, bad))
    return probs


def floor_fn_problems(sql):
    """층 묶음 함수의 규칙 글자 — 제외 구획 다음 · 순서(NULL 맨 뒤 → resid 뒤 → 면적 큰 순) · 오피스텔."""
    body = flat(fn_block("price_floor_use_group", sql))
    want = {
        "제외 아닌 구획 먼저": "where not s.area_excluded or not exists (select 1 from seg x where not x.area_excluded)",
        "순서": "order by grp.g is null, grp.g = 'resid', grp.area desc, grp.g limit 1",
        "오피스텔 낱말": "where u.main_purps_nm ~ nm.officetel_re or coalesce(u.etc_purps, '') ~ nm.officetel_re",
        "상가 구획 있으면 오피스텔 아님": "and not exists (select 1 from grp where grp.g = 'shop') then 'officetel'",
        "char(19) 서명": "price_floor_use_group(p_pnu char(19), p_floor smallint)",
        "stable·search_path": "language sql stable set search_path = public",
    }
    return ["{} 가 다르다".format(k) for k, v in want.items() if v not in body]


# ── 1. 정본 정적 가드 ────────────────────────────────────────────────────────


def test_정본_사다리_네_갈래_모두_같은_묶음():
    assert ladder_group_problems(read(SCHEMA)) == []


def test_정본_판정_순서():
    assert status_order_problems(read(SCHEMA)) == []
    assert status_condition_problems(read(SCHEMA)) == []


def test_정본_use_group_칸():
    assert use_group_column_problems(read(SCHEMA)) == []
    api = fn_block("api.list_price_bands", read(SCHEMA))
    assert re.search(r"window_from\s+text,\n\s+use_group\s+text\n\)", api)
    assert "select * from public.list_price_bands(p_pnu)" in api


def test_정본_구_표_둘은_상가만():
    assert mv_shop_problems(read(SCHEMA)) == []


def test_정본_묶음_함수는_인라인되게():
    assert group_fn_problems(read(SCHEMA)) == []


def test_정본_층_묶음_함수_규칙():
    assert floor_fn_problems(read(SCHEMA)) == []


def test_정본_권한_새_함수는_닫히고_api_만_열린다():
    src = flat(read(SCHEMA))
    for sig in NEW_FN_SIGS.values():
        assert "revoke all on function {} from public, anon, authenticated;".format(sig) in src
        name = sig.split("(")[0]
        assert not re.search(r"grant [^;]*on function (public\.)?{}\(".format(name), src)
    assert "grant execute on function api.list_price_bands(text) to anon, authenticated;" in src


def test_정본_반경_이웃_표는_묶음을_안_건다():
    """mv_tx_parcel_geog 는 '거래가 한 건이라도 있는 필지' 상한만 — 묶음은 L4·L5 가 거래 쪽에서 건다."""
    assert "price_use_group" not in flat(mv_select("mv_tx_parcel_geog", read(SCHEMA)))


# ── 1-1. 양성 대조 — 하나만 빠진 변형도 잡는다 ──────────────────────────────


GROUP_LINE = "\n               and price_use_group_nm(t.main_use) = v_grp"


@pytest.mark.parametrize("lvl", LADDER)
def test_돌연변이_갈래_하나만_묶음_조건을_빼도_잡힌다(lvl):
    src = read(SCHEMA)
    body = fn_block("list_price_bands", src)
    m = re.search(r"select '{}'".format(lvl), body)
    nxt = body.find(GROUP_LINE, m.end())
    assert nxt != -1
    bad_body = body[:nxt] + body[nxt + len(GROUP_LINE):]
    assert ladder_group_problems(src.replace(body, bad_body, 1)) == [
        "{} 갈래에 같은 묶음 조건이 없다".format(lvl)]


def test_돌연변이_갈래의_묶음_조건을_주석으로_죽여도_잡힌다():
    src = read(SCHEMA)
    body = fn_block("list_price_bands", src)
    i = body.index("and price_use_group_nm(t.main_use) = v_grp", body.index("select 'L6'"))
    bad_body = body[:i] + "-- " + body[i:]
    assert "L6 갈래에 같은 묶음 조건이 없다" in ladder_group_problems(src.replace(body, bad_body, 1))


def test_변형_꼴_v_grp_가_앞이어도_인정한다():
    src = read(SCHEMA)
    body = fn_block("list_price_bands", src)
    i = body.index("and price_use_group_nm(t.main_use) = v_grp", body.index("select 'L4'"))
    old = "and price_use_group_nm(t.main_use) = v_grp"
    alt = body[:i] + "and v_grp = price_use_group_nm(t.main_use)" + body[i + len(old):]
    assert ladder_group_problems(src.replace(body, alt, 1)) == []


def test_돌연변이_다른_묶음과_견주면_잡힌다():
    """`= 'shop'` 처럼 층 묶음 대신 고정 묶음과 견주면 업무 층에 상가 거래가 들어간다."""
    src = read(SCHEMA)
    body = fn_block("list_price_bands", src)
    i = body.index("and price_use_group_nm(t.main_use) = v_grp", body.index("select 'L5'"))
    old = "and price_use_group_nm(t.main_use) = v_grp"
    bad = body[:i] + "and price_use_group_nm(t.main_use) = 'shop'" + body[i + len(old):]
    assert ladder_group_problems(src.replace(body, bad, 1)) == ["L5 갈래에 같은 묶음 조건이 없다"]


@pytest.mark.parametrize("status", NEW_STATUS)
def test_돌연변이_새_status_를_빼면_잡힌다(status):
    src = read(SCHEMA)
    body = fn_block("list_price_bands", src)
    bad = body.replace("'{}'::text".format(status), "'ok'::text", 1)
    assert bad != body
    assert status_order_problems(src.replace(body, bad, 1))


def test_돌연변이_묶음_판정을_1층_앞으로_옮기면_잡힌다():
    src = read(SCHEMA)
    body = fn_block("list_price_bands", src)
    stmt = "    v_grp := price_floor_use_group(v_pnu, v_floor);\n"
    assert stmt in body
    bad = body.replace(stmt, "", 1).replace("    if v_floor = 1 then\n", stmt + "    if v_floor = 1 then\n", 1)
    assert status_order_problems(src.replace(body, bad, 1)) == ["판정 순서가 어긋났다"]


def test_돌연변이_주거_조건을_바꾸면_잡힌다():
    src = read(SCHEMA)
    body = fn_block("list_price_bands", src)
    bad = body.replace("if v_grp = 'resid' then", "if v_grp = 'other' then", 1)
    assert bad != body
    assert status_condition_problems(src.replace(body, bad, 1)) == ["floor_resid 의 조건이 다르다"]


def test_돌연변이_ok_줄에_use_group_을_안_실으면_잡힌다():
    src = read(SCHEMA)
    body = fn_block("list_price_bands", src)
    old = "v_p25, v_med, v_p75, v_area, v_from::text,\n                          v_grp;"
    assert old in body
    bad = body.replace(old, "v_p25, v_med, v_p75, v_area, v_from::text,\n                          null::text;", 1)
    assert use_group_column_problems(src.replace(body, bad, 1)) == ["ok 줄의 use_group 이 v_grp 가 아니다"]


@pytest.mark.parametrize("mv", ["mv_sigungu_tx_stats", "mv_sigungu_tx_yearly"])
def test_돌연변이_구_표에서_상가_조건을_빼면_잡힌다(mv):
    src = read(SCHEMA)
    block = mv_select(mv, src)
    bad_block = block.replace("\n  and price_use_group_nm(t.main_use) = 'shop'", "", 1)
    assert bad_block != block
    assert mv_shop_problems(src.replace(block, bad_block, 1)) == [
        "{} 의 where 에 상가 조건이 없다".format(mv)]


def test_돌연변이_동네_흐름을_filter_로만_걸면_잡힌다():
    """건수(n_all)까지 상가만이어야 한다(D8) — filter 로 옮기면 where 에 없어 빨강."""
    src = read(SCHEMA)
    block = mv_select("mv_sigungu_tx_yearly", src)
    bad_block = block.replace("\n  and price_use_group_nm(t.main_use) = 'shop'", "", 1).replace(
        "count(*)::int ", "count(*) filter (where price_use_group_nm(t.main_use) = 'shop')::int ", 1)
    assert mv_shop_problems(src.replace(block, bad_block, 1)) == [
        "mv_sigungu_tx_yearly 의 where 에 상가 조건이 없다"]


@pytest.mark.parametrize("bad", ["security definer", "set search_path = public", "strict"])
def test_돌연변이_묶음_함수에_인라인_막는_머리를_붙이면_잡힌다(bad):
    src = read(SCHEMA)
    blk = fn_block("price_use_group_nm", src)
    tampered = blk.replace("immutable\n", "immutable\n{}\n".format(bad), 1)
    assert tampered != blk
    assert group_fn_problems(src.replace(blk, tampered, 1))


def test_돌연변이_주거를_뒤로_보내는_순서를_지우면_잡힌다():
    src = read(SCHEMA)
    blk = fn_block("price_floor_use_group", src)
    tampered = blk.replace("grp.g = 'resid', ", "", 1)
    assert tampered != blk
    assert floor_fn_problems(src.replace(blk, tampered, 1)) == ["순서 가 다르다"]


def test_돌연변이_오피스텔에_상가_예외를_지우면_잡힌다():
    src = read(SCHEMA)
    blk = fn_block("price_floor_use_group", src)
    tampered = blk.replace("\n            and not exists (select 1 from grp where grp.g = 'shop')", "", 1)
    assert tampered != blk
    assert floor_fn_problems(src.replace(blk, tampered, 1)) == ["상가 구획 있으면 오피스텔 아님 가 다르다"]


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


def test_마이그_참고_시세는_api_먼저_지우고_다시_만든다():
    src = code(read(MIG))
    a = src.index("drop function if exists api.list_price_bands(text);")
    p = src.index("drop function if exists public.list_price_bands(text);")
    mk = src.index("create or replace function list_price_bands(p_pnu text)")
    mk_api = src.index("create or replace function api.list_price_bands(p_pnu text)")
    assert a < p < mk < mk_api


def test_마이그_묶음_함수는_요약표보다_먼저_만든다():
    """요약표가 price_use_group_nm 을 부른다 — 함수가 없으면 create materialized view 가 실패한다."""
    src = code(read(MIG))
    for fn in NEW_FNS:
        assert src.index("create or replace function {}(".format(fn)) < src.index(
            "create materialized view mv_sigungu_tx_stats as")


@pytest.mark.parametrize("name", list(NEW_FNS) + ["list_price_bands", "api.list_price_bands"])
def test_마이그_함수가_정본과_글자_일치(name):
    """머리(security definer·search_path·stable)까지 — create or replace 는 머리를 덮어쓴다."""
    assert fn_block(name, read(MIG)) == fn_block(name, read(SCHEMA))


@pytest.mark.parametrize("pattern", [
    r"^comment on function price_use_group_cd\(text\) is",
    r"^comment on function price_use_group_nm\(text\) is",
    r"^comment on function price_floor_use_group\(char\(19\), smallint\) is",
    r"^comment on function list_price_bands\(text\) is",
    r"^comment on materialized view mv_sigungu_tx_stats is",
    r"^comment on materialized view mv_sigungu_tx_yearly is",
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


def test_마이그_권한_api_에만_열고_새_함수와_public_은_닫는다():
    src = flat(read(MIG))
    rv = src.index("revoke all on function api.list_price_bands(text) from public, anon, authenticated;")
    gr = src.index("grant execute on function api.list_price_bands(text) to anon, authenticated;")
    assert rv < gr
    assert "revoke all on function list_price_bands(text) from public, anon, authenticated;" in src
    for sig in NEW_FN_SIGS.values():
        assert "revoke all on function {} from public, anon, authenticated;".format(sig) in src
    grants = re.findall(r"grant execute on function ([\w.]+)\([^)]*\) to ([^;]+);", src)
    assert grants == [("api.list_price_bands", "anon, authenticated")]


def test_마이그_정적_가드도_통과한다():
    mig = read(MIG)
    assert ladder_group_problems(mig) == []
    assert status_order_problems(mig) == []
    assert status_condition_problems(mig) == []
    assert use_group_column_problems(mig) == []
    assert mv_shop_problems(mig) == []
    assert group_fn_problems(mig) == []
    assert floor_fn_problems(mig) == []


def test_마이그_머리말에_되돌리기_절과_의존_확인이_있다():
    raw = read(MIG)
    head = raw[:raw.index("\nset lock_timeout")]
    assert "② 되돌리기" in head
    assert "pg_depend" in head
    # 되돌리기 순서 — api → public → (요약표 둘) → 묶음 함수 셋. cascade 금지.
    order = [head.index(s) for s in (
        "drop function if exists api.list_price_bands(text);",
        "drop function if exists public.list_price_bands(text);",
        "drop function if exists price_floor_use_group(char(19), smallint);",
        "drop function if exists price_use_group_nm(text);",
        "drop function if exists price_use_group_cd(text);",
    )]
    assert order == sorted(order)
    assert "cascade;" not in head


def test_마이그_머리말에는_함수_정의_글자가_없다():
    """함수 드리프트 시험의 파서는 주석을 안 걷는다 — 머리말에 정의 글자가 있으면 다음 본문을 삼킨다."""
    raw = read(MIG)
    head = raw[:raw.index("\nset lock_timeout")]
    # 파서(test_schema_function_drift.FN_RE)와 같은 꼴 — 이름과 여는 괄호까지('CREATE FUNCTION · COMMENT'
    # 같은 문장 목록은 이름이 없어 안 걸린다).
    assert not re.search(r"create\s+(or\s+replace\s+)?function\s+[\w.]+\s*\(", head, re.I)


def test_check_의_용도_이름_점검은_ASCII_SQL_이고_7종을_다_싣는다():
    """query_one 은 psql -c 라 한글이 깨진다 — 16진수로 넣었나 · 이름이 7종 그대로인가."""
    sql = post_load.build_tx_main_use_unknown_sql()
    assert sql.isascii()
    hexes = re.findall(r"decode\('([0-9a-f]+)', 'hex'\)", sql)
    assert [bytes.fromhex(h).decode("utf-8") for h in hexes] == [
        "제1종근린생활", "제2종근린생활", "판매", "업무", "숙박", "교육연구", "기타"]
    assert "nullif(main_use, '') is null or main_use not in (" in sql
    with pytest.raises(ValueError):
        post_load.judge_tx_main_use_unknown("ERROR: x")
    assert post_load.judge_tx_main_use_unknown(" 3\n") == 3


def test_check_의_용도_이름_점검은_종료_코드에_안_넣는다():
    """[주의]까지만 — main() 의 return 식에 그 결과가 들어가면 안 된다."""
    src = read(os.path.join(SCRIPTS_DIR, "post_load.py"))
    assert "\n        report_tx_main_use_unknown()\n" in src
    ret = src[src.index("        return 1 if (stale or map_stale"):]
    ret = ret[:ret.index(" else 0")]
    assert "main_use" not in ret


def test_공개_호출_허용_목록은_그대로다():
    """새 함수 셋은 public 내부용이라 허용 목록에 없어야 한다 — api 쌍둥이만 그대로."""
    assert "api.list_price_bands" in post_load.ANON_CALLABLE_ALLOWLIST
    for fn in NEW_FNS:
        assert not any(fn in name for name in post_load.ANON_CALLABLE_ALLOWLIST)
    assert "mv_sigungu_tx_stats" in post_load.REFRESH_MVS
    assert "mv_sigungu_tx_yearly" in post_load.REFRESH_MVS


# ── 3. 로컬 PostgreSQL 로 실제 실행 (없으면 건너뜀 — 형제 test_transaction_share_migration 과 같은 방식) ──

# 흉내(PostGIS 없음 — geography 는 text 도메인으로, 좌표는 비워 반경 단계는 건너뛴다).
SHIM = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role; end if;
end $$;
create schema api;
create domain geography as text;
create table parcel (pnu char(19) primary key, geom text);
create table building_floor (pnu char(19), floor_no smallint, main_purps_cd text, main_purps_nm text,
                             etc_purps text, area_m2 numeric(12,2), area_excluded boolean not null default false);
create table price_gate_sigungu (sigungu_code text primary key, gate_pass boolean);
create table mv_open_sigungu (sigungu_code char(5), sigungu_nm text);
create materialized view mv_tx_parcel_geog as select pnu, geom::geography as geog from parcel;
"""


def _old_state(schema_sql):
    """적용 **전** 라이브와 같은 모양 — 지분 칸 있음 · 묶음 함수 없음 · 9칸 참고 시세 · 상가 조건 없는 요약표."""
    old = [stmt_at(r"^create table if not exists transaction \(", schema_sql),
           "alter table transaction add column if not exists is_share boolean not null default false;"]
    for mv in ("mv_sigungu_tx_stats", "mv_sigungu_tx_yearly"):
        body = mv_select(mv, schema_sql).replace("\n  and price_use_group_nm(t.main_use) = 'shop'", "")
        old.append("create materialized view {} as\n{}".format(mv, body))
    old.append(stmt_at(r"^create unique index if not exists idx_msts_key", schema_sql))
    old.append(stmt_at(r"^create unique index if not exists idx_msty_key", schema_sql))
    old.append(fn_block("price_floor_band", schema_sql))
    old.append(fn_block("get_sigungu_tx_stats", schema_sql))
    old.append(fn_block("get_sigungu_tx_yearly", schema_sql))
    old.append(fn_block("list_price_bands", read(MIG_PREV)))
    old.append(fn_block("api.list_price_bands", schema_sql).replace(",\n  use_group       text", ""))
    joined = "\n".join(old)
    assert "price_use_group" not in joined and "use_group" not in joined
    return joined


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    psycopg2 = pytest.importorskip("psycopg2")
    initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
    if not initdb or not pg_ctl:
        pytest.skip("로컬 PostgreSQL(initdb·pg_ctl)이 없다 — CI 는 글자 가드(1~2)만 본다")
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


PNU_A = "1168010100100010000"   # 강남 역삼동 1번지 — 층마다 다른 묶음
PNU_B = "1168010100100020000"   # 같은 법정동 2번지(L6 후보)
# 층 묶음 표본 — 필지마다 한 층(2층)에 구획을 깔고 price_floor_use_group 이 무엇을 돌려주나.
FLOOR_CASES = [
    # (pnu 끝 네 자리, [(코드, 이름, 기타용도, 면적, 제외)], 기대)
    ("0101", [("02001", "공동주택", "아파트", 900, False), ("04001", "제2종근린생활시설", "일반음식점", 100, False)], "shop"),
    ("0102", [("02001", "공동주택", "아파트", 500, False)], "resid"),
    ("0103", [("", "", "", 300, False)], None),
    ("0104", [("14001", "업무시설", "사무소", 300, False), ("15001", "숙박시설", "호텔", 200, False)], "office"),
    ("0105", [("14001", "업무시설", "오피스텔", 400, False)], "officetel"),
    ("0106", [("14001", "업무시설", "오피스텔", 100, False), ("03001", "제1종근린생활시설", "소매점", 300, False)], "shop"),
    ("0107", [("03001", "제1종근린생활시설", "계단실", 20, True)], "shop"),
    ("0108", [("14001", "업무시설", "사무소", 50, False), ("03001", "제1종근린생활시설", "계단실", 400, True)], "office"),
    ("0109", [("Z3", "기타근린생활시설", "", 80, False)], "shop"),
    ("0110", [("Z8", "교육연구및복지시설", "", 80, False)], "other"),
    ("0111", [("", "", "", 900, False), ("10001", "교육연구시설", "학원", 10, False)], "other"),
]


@pytest.fixture(scope="module")
def cur(pg):
    c = pg.cursor()
    c.execute(SHIM)
    c.execute(_old_state(read(SCHEMA)))
    ym = "to_char(now(), 'YYYYMM')"
    # 거래: PNU_A 2층 상가 3건(100·200·300만) + 업무 1건(1,000만) · 3층 업무 2건(800·900만) + 상가 1건(50만)
    #       · 4층(주거)·5층(오피스텔)·6층(코드 빈칸)에도 상가 거래 1건씩(값을 내면 안 된다)
    #       · 지분 상가 1건(2층 · 10만 — 묶음과 무관하게 빠진다) · PNU_B 7층 상가 1건(L6 후보 — 400만)
    c.execute("""
      insert into transaction (tx_id, pnu, sigungu_code, floor_no, bld_area_m2, price_won, contract_ym, tx_type, main_use)
      values ('s1', '{a}', '11680', 2, 10, 10000000, {ym}, '집합', '제2종근린생활'),
             ('s2', '{a}', '11680', 2, 10, 20000000, {ym}, '집합', '제1종근린생활'),
             ('s3', '{a}', '11680', 2, 10, 30000000, {ym}, '집합', '판매'),
             ('o1', '{a}', '11680', 2, 10, 100000000, {ym}, '집합', '업무'),
             ('o2', '{a}', '11680', 3, 10, 80000000, {ym}, '집합', '업무'),
             ('o3', '{a}', '11680', 3, 10, 90000000, {ym}, '집합', '업무'),
             ('s4', '{a}', '11680', 3, 10, 5000000, {ym}, '집합', '판매'),
             ('r1', '{a}', '11680', 4, 10, 10000000, {ym}, '집합', '판매'),
             ('t1', '{a}', '11680', 5, 10, 10000000, {ym}, '집합', '업무'),
             ('u1', '{a}', '11680', 6, 10, 10000000, {ym}, '집합', '판매'),
             ('sh', '{a}', '11680', 2, 10, 1000000, {ym}, '집합', '판매'),
             ('b7', '{b}', '11680', 7, 10, 40000000, {ym}, '집합', '제2종근린생활'),
             ('l1', null,  '11680', 3, 10, 70000000, {ym}, '집합', '숙박'),
             ('e1', null,  '11680', 3, 10, 60000000, {ym}, '집합', '교육연구');
      update transaction set is_share = true where tx_id = 'sh';
      insert into parcel values ('{a}', null), ('{b}', null);
      insert into building_floor (pnu, floor_no, main_purps_cd, main_purps_nm, etc_purps, area_m2) values
        ('{a}', 1, '03001', '제1종근린생활시설', '소매점', 100),
        ('{a}', 2, '04001', '제2종근린생활시설', '일반음식점', 100),
        ('{a}', 3, '14001', '업무시설', '사무소', 100),
        ('{a}', 4, '02001', '공동주택', '아파트', 100),
        ('{a}', 5, '14001', '업무시설', '오피스텔', 100),
        ('{a}', 6, '', '', '', 100),
        ('{a}', 7, '04001', '제2종근린생활시설', '일반음식점', 100);
      insert into price_gate_sigungu values ('11680', true);
      insert into mv_open_sigungu values ('11680', '강남구');
      refresh materialized view mv_sigungu_tx_stats;
      refresh materialized view mv_sigungu_tx_yearly;
    """.format(a=PNU_A, b=PNU_B, ym=ym))
    for tail, segs, _ in FLOOR_CASES:
        pnu = "116801010010" + "000" + tail
        for cd, nm, etc, area, excl in segs:
            c.execute("insert into building_floor values (%s, 2, %s, %s, %s, %s, %s)",
                      (pnu, cd, nm, etc, area, excl))
    c.execute("select sum(n_all) from mv_sigungu_tx_yearly")
    before = c.fetchone()[0]
    c.execute(read(MIG))   # 마이그레이션 원문 그대로(set · begin … commit · notify)
    return c, before


CD_CASES = [("03", "shop"), ("04", "shop"), ("07", "shop"), ("Z3", "shop"), ("Z6", "shop"),
            ("03001", "shop"), ("14", "office"), ("14999", "office"), ("15", "lodging"),
            ("01", "resid"), ("02", "resid"), (None, None), ("", None),
            ("10", "other"), ("Z8", "other"), ("05", "other")]
NM_CASES = [("제1종근린생활", "shop"), ("제2종근린생활", "shop"), ("판매", "shop"),
            ("업무", "office"), ("숙박", "lodging"), (None, None), ("", None),
            ("교육연구", "other"), ("기타", "other"), ("사무소", "other")]


class TestRealRun:
    @pytest.mark.parametrize("cd,want", CD_CASES)
    def test_코드_묶음(self, cur, cd, want):
        c, _ = cur
        c.execute("select price_use_group_cd(%s)", (cd,))
        assert c.fetchone()[0] == want

    @pytest.mark.parametrize("nm,want", NM_CASES)
    def test_이름_묶음(self, cur, nm, want):
        c, _ = cur
        c.execute("select price_use_group_nm(%s)", (nm,))
        assert c.fetchone()[0] == want

    @pytest.mark.parametrize("tail,segs,want", FLOOR_CASES, ids=[t for t, _, _ in FLOOR_CASES])
    def test_층_묶음(self, cur, tail, segs, want):
        c, _ = cur
        c.execute("select price_floor_use_group(%s::char(19), 2::smallint)", ("116801010010000" + tail,))
        assert c.fetchone()[0] == want

    def test_대장에_층이_없으면_NULL(self, cur):
        c, _ = cur
        c.execute("select price_floor_use_group(%s::char(19), 40::smallint)", (PNU_A,))
        assert c.fetchone()[0] is None

    def test_묶음_함수는_인라인된다(self, cur):
        """요약표 스캔에서 함수 이름이 계획에 안 남아야 한다(인라인 = case 식으로 펼쳐짐)."""
        c, _ = cur
        c.execute("explain (verbose) select count(*) from transaction t "
                  "where price_use_group_nm(t.main_use) = 'shop'")
        plan = "\n".join(r[0] for r in c.fetchall())
        assert "price_use_group_nm" not in plan

    def test_층마다_같은_묶음끼리_값을_낸다(self, cur):
        c, _ = cur
        c.execute("select floor_no, status, stage, n, median, use_group from api.list_price_bands(%s) "
                  "order by floor_no", (PNU_A,))
        assert c.fetchall() == [
            (1, "floor_1f", None, None, None, None),
            (2, "ok", "L2", 3, 2000000, "shop"),        # 업무 1,000만·지분 10만은 빠진다
            (3, "ok", "L2", 2, 8500000, "office"),      # 상가 50만은 빠진다
            (4, "floor_resid", None, None, None, None),
            (5, "floor_officetel", None, None, None, None),
            (6, "no_use", None, None, None, None),
            # 7층은 PNU_A 에 거래가 없어 L6(같은 법정동 3층+)로 — 상가 묶음만:
            # 3층 판매 50만 · 4층 판매 100만 · 6층 판매 100만 · PNU_B 7층 2종근생 400만 → 가운데 100만
            # (업무 800·900·100만은 빠진다)
            (7, "ok", "L6", 4, 1000000, "shop"),
        ]

    def test_L6_도_같은_묶음만(self, cur):
        """7층을 업무 층으로 바꾸면 L6 도 업무 거래만 — 3층 800·900만 + 5층 100만 → 가운데 800만."""
        c, _ = cur
        c.execute("update building_floor set main_purps_cd = '14001' where pnu = %s and floor_no = 7", (PNU_A,))
        try:
            c.execute("select status, stage, n, median, use_group from list_price_bands(%s) "
                      "where floor_no = 7", (PNU_A,))
            assert c.fetchall() == [("ok", "L6", 3, 8000000, "office")]
        finally:
            c.execute("update building_floor set main_purps_cd = '04001' where pnu = %s and floor_no = 7", (PNU_A,))

    def test_표본이_없으면_no_estimate_에도_묶음을_싣는다(self, cur):
        c, _ = cur
        c.execute("update building_floor set main_purps_cd = '15001' where pnu = %s and floor_no = 7", (PNU_A,))
        try:
            c.execute("select status, use_group from list_price_bands(%s) where floor_no = 7", (PNU_A,))
            assert c.fetchall() == [("no_estimate", "lodging")]
        finally:
            c.execute("update building_floor set main_purps_cd = '04001' where pnu = %s and floor_no = 7", (PNU_A,))

    def test_게이트_미달은_한_줄이고_묶음은_비어_있다(self, cur):
        c, _ = cur
        c.execute("update price_gate_sigungu set gate_pass = false")
        try:
            c.execute("select floor_no, status, use_group from list_price_bands(%s)", (PNU_A,))
            assert c.fetchall() == [(None, "gate_fail", None)]
        finally:
            c.execute("update price_gate_sigungu set gate_pass = true")

    def test_구_층대_단가는_상가만(self, cur):
        c, _ = cur
        c.execute("refresh materialized view concurrently mv_sigungu_tx_stats")
        c.execute("select floor_band, n from get_sigungu_tx_stats('11680') where n > 0 order by floor_band")
        # 2층 상가 3건(지분 제외) · 3층이상: 3층 상가 1 + 4·6층 판매 2 + 7층 상가 1 = 4 (업무·숙박·교육연구 빠짐)
        assert c.fetchall() == [("2층", 3), ("3층이상", 4)]

    def test_동네_흐름은_건수까지_상가만(self, cur):
        c, before = cur
        c.execute("refresh materialized view concurrently mv_sigungu_tx_yearly")
        c.execute("select sum(n_all), sum(n) from mv_sigungu_tx_yearly")
        n_all, n = c.fetchone()
        assert before == 14            # 적용 전 = 집합 전부(지분 포함)
        assert n_all == 8              # 상가 거래만(지분 상가 1건은 건수엔 센다): s1·s2·s3·s4·r1·u1·sh·b7
        assert n == 7                  # 단가 근거는 지분 빼고

    def test_check_용도_이름_점검이_실제로_센다(self, cur):
        """7종이면 0 · 모르는 글자·빈 값을 넣으면 그만큼(양성 대조)."""
        c, _ = cur
        c.execute(post_load.build_tx_main_use_unknown_sql())
        assert c.fetchone()[0] == 0
        c.execute("insert into transaction (tx_id, sigungu_code, price_won, contract_ym, tx_type, main_use) "
                  "values ('x1', '11680', 1, '200001', '집합', '근린생활'), ('x2', '11680', 1, '200001', '집합', ''),"
                  "       ('x3', '11680', 1, '200001', '집합', null)")
        try:
            c.execute(post_load.build_tx_main_use_unknown_sql())
            assert c.fetchone()[0] == 3
        finally:
            c.execute("delete from transaction where tx_id in ('x1', 'x2', 'x3')")

    def test_권한(self, cur):
        c, _ = cur
        c.execute("select has_function_privilege('anon', 'api.list_price_bands(text)', 'execute'),"
                  "       has_function_privilege('anon', 'public.list_price_bands(text)', 'execute'),"
                  "       has_function_privilege('anon', 'price_use_group_cd(text)', 'execute'),"
                  "       has_function_privilege('anon', 'price_use_group_nm(text)', 'execute'),"
                  "       has_function_privilege('anon', 'price_floor_use_group(char(19), smallint)', 'execute'),"
                  "       has_table_privilege('anon', 'mv_sigungu_tx_stats', 'select'),"
                  "       has_table_privilege('anon', 'mv_sigungu_tx_yearly', 'select')")
        assert c.fetchone() == (True, False, False, False, False, False, False)

    def test_두_번_돌려도_된다(self, cur):
        """함수는 create or replace · api·public 은 drop if exists 뒤 · 요약표는 drop if exists 뒤 다시 굽는다."""
        c, _ = cur
        c.execute(read(MIG))
        c.execute("select count(*) from api.list_price_bands(%s)", (PNU_A,))
        assert c.fetchone()[0] == 7
