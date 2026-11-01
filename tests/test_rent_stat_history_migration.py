# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-24b(상권 임대 동향의 8분기 흐름 · 결정 0038 C · V5)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙여 넣기 전에는 아무도 모르는 종류의 실수**다:

  1) 마이그레이션과 정본(schema.sql)의 글자가 갈린다 → 새 환경만 다른 모양으로 만들어진다.
     `create or replace` 는 머리 속성(security definer·search_path·stable)을 새 정의로 덮어쓰는데,
     드리프트 가드는 `$$` 안 본문만 본다 — 그래서 머리·comment 까지 여기서 글자로 대조한다
     (CLAUDE.md ⛔ 2026-10-01a · 본보기 tests/test_floor_industry_migration.py).
  2) 머리 속성 하나가 빠진다 → `set search_path` 가 빠지면 anon 경로가 `relation does not exist` 로 죽고,
     security definer 가 빠지면 닫힌 rent_stat 을 못 읽어 `permission denied` 다(화면에선 흐름만 조용히 빠진다).
  3) public 원본에 grant 를 준다 → security definer 원본이 밖에 열린다(🚪 grant 는 api 쌍둥이에만).
  4) **조사구역 찾는 길이 list_rent_stats 와 갈린다** — 술어(st_contains)·좌표 조건·이름 잇기 표가 다르면 카드의 값과
     흐름이 서로 다른 조사구역을 말한다(에러 없이). me·hit·pair 세 덩어리를 정본 list_rent_stats 와 **글자로** 견주고
     (글자 가드), 같은 흉내 판에서 두 함수를 불러 조사구역 집합이 같은지 본다(실행 가드).
  5) 층별효용비율(floor_util_ratio)이 새어 나간다 → 화면이 언젠가 곱한다(결정 0024 · 0031).
  6) 같은 이름에 서명이 둘 → PostgREST 가 못 고른다(PGRST203 · 결정 0038 §7) — 정의 개수 글자 가드 + 실행 가드 pg_proc 개수.
  7) list_rent_stats 가 바뀐다 → 임대 카드와 세 잣대가 나눠 쓰는 응답이 흔들린다 — 이 마이그레이션에 그 이름이 정의로 0번.

② 실행 가드(로컬 PostgreSQL 이 있을 때만)는 흉내 판(PostGIS 없음 — st_contains 를 글자 판정으로 흉내 낸다) 위에서
   두 함수를 실제로 만들고 불러 본다. CI 에는 PostgreSQL 이 없어 건너뛴다.
"""

import os
import re
import shutil
import socket
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-24b_rent_stat_history.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

FN = "list_rent_stat_history"
API_FN = "api.list_rent_stat_history"
OLD_FN = "list_rent_stats"
SIG = "(text)"

PUBLIC_HEAD = ("language sql", "stable", "security definer", "set search_path = public")
API_HEAD = ("language sql", "stable", "security definer", "set search_path = ''")

RETURNS = (
    "returns table (\n"
    "  rone_region_nm    text,\n"
    "  bld_type          text,\n"
    "  quarter           text,\n"
    "  vacancy_rate      numeric,\n"
    "  rent_per_m2       numeric,\n"
    "  yield_rate        numeric,\n"
    "  income_yield_rate numeric\n"
    ")\n"
)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


@pytest.fixture(scope="module")
def mig():
    return read(MIGRATION)


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


def statements(sql):
    """주석 줄을 걷어낸 실제 문장만 — 권한 가드는 이쪽을 본다(주석으로 죽인 문장을 '있다'로 보지 않게)."""
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


def fn_block(sql, name):
    """`create or replace function <name>(` 부터 `$$;` 까지 — 머리 + 본문 통째(줄머리 고정)."""
    m = re.search(r"(?ms)^create\s+or\s+replace\s+function\s+" + re.escape(name)
                  + r"\s*\(.*?\$\$\s*;", sql)
    assert m, "{} 의 정의를 못 찾았습니다 — 정규식이 헛돌면 아래 대조가 통째로 무의미해집니다".format(name)
    return m.group(0)


def fn_comment(sql, name):
    m = re.search(r"(?ms)^comment\s+on\s+function\s+" + re.escape(name) + r"\s*\(.*?';\s*$", sql)
    assert m, "{} 의 comment 를 못 찾았습니다".format(name)
    return m.group(0)


def head_of(block):
    return block[: block.index("$$")]


def body_of(block):
    return block[block.index("$$") + 2: block.rindex("$$")]


def head_problems(block, want):
    """머리에서 빠진 속성 목록(비면 정상). 가드 본체와 양성 대조가 이 같은 함수를 지난다.

    줄 단위로 본다(대소문자·줄 끝 공백 무시) — `stable` 이 `volatile` 로, `set search_path = public` 이
    다른 값으로 바뀐 꼴도 '빠짐'으로 잡힌다.
    ⚠️ 못 보는 것: 한 줄에 여러 속성을 이어 쓴 꼴(`stable security definer`) — 이 레포 정본은 쓰지 않는다.
    """
    lines = {ln.strip().lower() for ln in head_of(block).splitlines()}
    return [w for w in want if w not in lines]


def definitions(sql, name):
    """`create [or replace] function <name>(` 이 몇 번 나오나(주석 밖 · 대소문자 무시 · 스키마 그대로).

    ⚠️ 못 보는 것: 따옴표 이름 · 다른 스키마로 같은 이름(그건 다른 함수다).
    """
    return len(re.findall(r"(?im)^\s*create\s+(?:or\s+replace\s+)?function\s+" + re.escape(name) + r"\s*\(",
                          statements(sql)))


def grant_targets(sql):
    """`grant … on function <대상>(` 의 대상 이름 전부(소문자 · 스키마 그대로).

    ⓘ 가드 본체와 양성 대조가 이 **같은 함수**를 지난다(형제 tests/test_floor_industry_migration.py 와 같은 꼴).
    ⚠️ 못 보는 것: 인자 괄호 없는 `on function <이름> to …` · 따옴표 이름 · 일괄 grant(`all functions in schema`).
    """
    found = []
    for stmt in re.findall(r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*?"
                           r"\bon\s+(?:function|routine)\b([^;]*)", statements(sql)):
        found += re.findall(r"(?i)(?<![\w.])((?:\w+\.)?\w+)\s*\(", stmt)
    return [t.lower() for t in found]


def region_path(body):
    """본문에서 조사구역 찾는 길 — `with me as (` 부터 pair 덩어리의 닫는 괄호까지(글 그대로 · 줄바꿈 LF).

    ⓘ 가드 본체(새 함수 ↔ 정본 list_rent_stats)와 양성 대조가 이 **같은 함수**를 지난다.
    ⚠️ 못 보는 것: 세 덩어리 **밖**에서 조사구역을 다시 거르는 꼴(바깥 where 의 `pair` 조건은
       `outer_problems` 가 따로 본다) · 같은 글이지만 정본 함수 쪽이 바뀐 꼴(그땐 둘 다 같이 바뀌어 초록 — 의도된 일이다).
    """
    m = re.search(r"(?s)with me as \(.*?\n  pair as \(.*?\n  \)", body)
    assert m, "조사구역 찾는 길(me·hit·pair)을 못 찾았습니다 — 정규식이 헛돌면 대조가 무의미해집니다"
    return m.group(0)


def outer_problems(body):
    """바깥 select 가 pair 의 조사구역 **전부를 그대로** 읽는지 — 어긋난 까닭 목록(비면 정상). 양성 대조가 같은 함수를 지난다.

    ① rent_stat 을 pair 의 조사구역 이름으로만 거른다 ② 분기·종류를 거르지 않는다(전 분기 · 네 종류)
    ③ 층별효용비율·floor_rent 를 내보내지 않는다(주석 밖) ④ 집계(avg·sum·count·min·max)·나누기를 하지 않는다.
    ⚠️ 못 보는 것: 함수 이름으로 감싼 집계(사용자 함수) · 주석 줄 안의 글.
    """
    code = statements(body)
    path = region_path(code)
    tail = code[code.index(path) + len(path):]
    flat = re.sub(r"\s+", " ", tail).lower()
    out = []
    if "where r.region_nm in (select p.rone_region_nm from pair p)" not in flat:
        out.append("조사구역 조건이 pair 그대로가 아님")
    if re.search(r"\br\.quarter\s*(=|>|<|in\b|between\b)", flat) or re.search(r"\bdistinct\s+on\b", flat):
        out.append("분기를 거르거나 하나만 고름")
    if re.search(r"\br\.bld_type\s*(=|in\b)", flat):
        out.append("종류를 거름")
    if re.search(r"floor_util_ratio|floor_rent", flat):
        out.append("층별효용비율·층별 임대료를 내보냄")
    if re.search(r"\b(avg|sum|count|min|max)\s*\(", flat) or re.search(r"[a-z_)]\s*/\s*[a-z0-9_(]", flat):
        out.append("집계·나누기를 함")
    return out


# ── ① 글자 가드 ─────────────────────────────────────────────────────────────


class TestMirrorsTheSchema:
    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_head_and_body_are_the_same_text(self, mig, schema, name):
        assert fn_block(mig, name) == fn_block(schema, name), (
            "{} 가 정본과 글자가 다릅니다 — 새 환경만 다른 모양이 됩니다".format(name))

    def test_comment_is_the_same_text(self, mig, schema):
        assert fn_comment(mig, FN) == fn_comment(schema, FN)

    def test_mirror_detector_sees_a_head_only_change(self, mig, schema):
        """양성 대조 — 본문은 그대로 두고 머리 한 줄만 바꾼 사본이 정본과 어긋난다고 잡힌다."""
        block = fn_block(mig, FN)
        changed = mig.replace(block, block.replace("set search_path = public\nas $$", "as $$", 1), 1)
        assert changed != mig
        assert fn_block(changed, FN) != fn_block(schema, FN)

    def test_mirror_detector_sees_a_comment_only_change(self, mig, schema):
        changed = mig.replace("나가는 것은 조사구역 이름과 공표 통계값뿐이다", "나가는 것은 통계값뿐이다", 1)
        assert changed != mig
        assert fn_comment(changed, FN) != fn_comment(schema, FN)


class TestOneSignature:
    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_each_name_is_defined_once(self, mig, schema, name):
        """같은 이름 둘(기본값 인자를 더한 판 등)이면 PostgREST 가 `{p_pnu}` 를 못 고른다(PGRST203)."""
        assert definitions(mig, name) == 1
        assert definitions(schema, name) == 1

    def test_detector_counts_a_second_signature(self, mig):
        """양성 대조 — 인자를 하나 더 붙인 둘째 정의(흔한 꼴)와 대문자·들여쓴 변형 꼴이 센다."""
        extra = ("\ncreate or replace function list_rent_stat_history(p_pnu text, p_n int default 8)\n"
                 "returns int language sql as $$ select 1 $$;\n")
        assert definitions(mig + extra, FN) == 2
        extra2 = "\n  CREATE FUNCTION List_Rent_Stat_History (p text) returns int language sql as $$ select 1 $$;\n"
        assert definitions(mig + extra2, FN) == 2

    def test_list_rent_stats_is_untouched(self, mig):
        """옛 함수는 이 마이그레이션에서 정의·삭제·권한 변경 0 — 임대 카드와 세 잣대가 그 응답을 나눠 쓴다."""
        code = statements(mig)
        assert definitions(mig, OLD_FN) == 0 and definitions(mig, "api." + OLD_FN) == 0
        assert not re.search(r"(?i)\b(drop|revoke|grant|alter)\b[^;]*\blist_rent_stats\s*\(", code)


class TestHeads:
    def test_public_head(self, mig, schema):
        for sql in (mig, schema):
            assert head_problems(fn_block(sql, FN), PUBLIC_HEAD) == []

    def test_api_twin_head_and_body(self, mig, schema):
        for sql in (mig, schema):
            block = fn_block(sql, API_FN)
            assert head_problems(block, API_HEAD) == []
            assert body_of(block).strip() == "select * from public.list_rent_stat_history(p_pnu)"

    @pytest.mark.parametrize("old, new", (
        ("security definer\n", ""),
        ("set search_path = public\n", ""),
        ("stable\n", "volatile\n"),
        ("set search_path = public\n", "set search_path = pg_temp\n"),
    ))
    def test_head_detector_catches_a_missing_attribute(self, mig, old, new):
        block = fn_block(mig, FN)
        assert old in head_of(block)
        assert head_problems(block.replace(old, new, 1), PUBLIC_HEAD)

    @pytest.mark.parametrize("old, new", (
        ("security definer\n", ""),
        ("set search_path = ''\n", ""),
        ("stable\n", ""),
    ))
    def test_head_detector_catches_a_missing_attribute_on_the_twin(self, mig, old, new):
        block = fn_block(mig, API_FN)
        assert old in head_of(block)
        assert head_problems(block.replace(old, new, 1), API_HEAD)

    def test_returns_the_seven_columns(self, mig):
        """두 함수가 같은 칸 일곱을 같은 형으로 돌려준다(쌍둥이가 다르면 화면 검증기가 응답을 버린다)."""
        for name in (FN, API_FN):
            assert RETURNS in head_of(fn_block(mig, name)), name


class TestSameRegionPath:
    def test_path_is_the_text_of_list_rent_stats(self, mig, schema):
        """조사구역 찾는 길(me·hit·pair)이 정본 list_rent_stats 의 글 그대로 — 카드의 값과 흐름이 같은 조사구역을 말한다."""
        new = region_path(body_of(fn_block(mig, FN)))
        old = region_path(body_of(fn_block(schema, OLD_FN)))
        assert new == old

    @pytest.mark.parametrize("old, new", (
        # 술어를 바꾼다(흔한 꼴) — 경계에 닿기만 해도 든다
        ("where st_contains(d.geom, me.g)", "where st_intersects(d.geom, me.g)"),
        # 좌표 조건을 뺀다(변형 꼴) — 빈손이 '조사 대상 아님' 단정으로 샌다
        ("where p.pnu = p_pnu::char(19) and p.geom is not null", "where p.pnu = p_pnu::char(19)"),
        # 캐스트를 뺀다 — 색인이 죽는다
        ("p.pnu = p_pnu::char(19)", "p.pnu = p_pnu"),
        # 이름 잇기 표를 left join 으로 — 이을 근거 없는 상권이 null 조사구역으로 남는다
        ("    join district_rone_map m on", "    left join district_rone_map m on"),
    ))
    def test_path_detector_catches_variants(self, mig, schema, old, new):
        body = body_of(fn_block(mig, FN))
        assert old in body
        assert region_path(body.replace(old, new, 1)) != region_path(body_of(fn_block(schema, OLD_FN)))

    def test_outer_select_reads_every_quarter_and_type(self, mig):
        assert outer_problems(body_of(fn_block(mig, FN))) == []

    @pytest.mark.parametrize("old, new", (
        # 최신 한 줄만(흔한 꼴 — 옛 함수처럼)
        ("  select r.region_nm,", "  select distinct on (r.region_nm, r.bld_type) r.region_nm,"),
        # 분기를 자른다(변형 꼴)
        ("  where r.region_nm in (select p.rone_region_nm from pair p)",
         "  where r.region_nm in (select p.rone_region_nm from pair p) and r.quarter >= '2025Q1'"),
        # 종류를 거른다
        ("  where r.region_nm in (select p.rone_region_nm from pair p)",
         "  where r.region_nm in (select p.rone_region_nm from pair p) and r.bld_type = '집합상가'"),
        # 층별효용비율을 내보낸다
        ("         r.income_yield_rate\n", "         r.income_yield_rate,\n         r.floor_util_ratio\n"),
        # 종류끼리 평균
        ("         r.vacancy_rate,", "         avg(r.vacancy_rate) over (partition by r.region_nm, r.quarter),"),
        # 조사구역 조건을 바꾼다(다른 상권 하나로)
        ("  where r.region_nm in (select p.rone_region_nm from pair p)",
         "  where r.region_nm = (select min(p.rone_region_nm) from pair p)"),
    ))
    def test_outer_detector_catches_variants(self, mig, old, new):
        body = body_of(fn_block(mig, FN))
        assert old in body
        assert outer_problems(body.replace(old, new, 1))

    def test_reads_only_the_four_tables(self, mig):
        body = statements(body_of(fn_block(mig, FN)))
        assert re.findall(r"(?i)\b(?:from|join)\s+(\w+)", body) == [
            "parcel", "district", "me", "hit", "district_rone_map", "rent_stat", "pair"]


class TestPermissions:
    def test_only_the_api_twin_is_granted(self, mig, schema):
        assert grant_targets(mig) == [API_FN]
        assert [t for t in grant_targets(schema) if "rent_stat_history" in t] == [API_FN]

    @pytest.mark.parametrize("bad", (
        "grant execute on function list_rent_stat_history(text) to anon;",
        "grant all on function public.list_rent_stat_history(text) to anon;",
        "  GRANT EXECUTE\n  ON FUNCTION List_Rent_Stat_History ( text ) TO authenticated;",
    ))
    def test_grant_detector_catches_the_public_original(self, mig, bad):
        found = grant_targets(mig + "\n" + bad + "\n")
        assert [t for t in found if t != API_FN], found

    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_every_function_is_revoked_with_anon_named(self, mig, schema, name):
        for sql in (mig, schema):
            assert re.search(r"(?m)^revoke all on function " + re.escape(name + SIG)
                             + r" from public, anon, authenticated;", statements(sql)), name

    def test_revoke_before_grant(self, mig):
        code = statements(mig)
        assert (code.index("revoke all on function api.list_rent_stat_history(")
                < code.index("grant execute on function api.list_rent_stat_history("))

    def test_allowlist_has_the_api_twin_only(self):
        assert API_FN in post_load.ANON_CALLABLE_ALLOWLIST
        assert FN not in post_load.ANON_CALLABLE_ALLOWLIST
        assert "public." + FN not in post_load.ANON_CALLABLE_ALLOWLIST

    def test_allowlist_total_is_36(self):
        """읽기 4 + 부르기 32 = `--check` 총계 36(2026-10-24a 의 31 에 이 함수 하나 · 2026-10-25a V6 개업·폐업 전부 보기가 32 → 33 · 2026-10-29a 결정 0044 대전 동네 폐업이 33 → 34 ·
        2026-10-31a 결정 0045 서울 4종이 34 → 36 — 셋 다 이 마이그레이션 몫 아님)."""
        assert len(post_load.ANON_READABLE_ALLOWLIST) + len(post_load.ANON_CALLABLE_ALLOWLIST) == 38


class TestMigrationShape:
    def test_settings_before_begin_and_notify_after_commit(self, mig):
        code = statements(mig)
        begin = re.search(r"(?m)^begin;", code).start()
        commit = re.search(r"(?m)^commit;", code).start()
        notify = code.index("notify pgrst, 'reload schema';")
        assert code.index("set lock_timeout = ") < begin
        assert code.index("set statement_timeout = ") < begin
        assert begin < commit < notify
        assert len(re.findall(r"(?m)^begin;", code)) == 1 and len(re.findall(r"(?m)^commit;", code)) == 1
        for stmt in re.finditer(r"(?im)^(create|drop|alter|insert|revoke|grant|analyze|comment)\b", code):
            assert begin < stmt.start() < commit, "begin/commit 밖의 문장: " + stmt.group(0)

    def test_only_new_objects(self, mig):
        """기존 객체는 안 건드린다 — drop·alter 0, 만드는 함수는 새 이름 둘뿐."""
        code = statements(mig)
        assert not re.search(r"(?im)^\s*(drop|alter)\s", code)
        made = re.findall(r"(?im)^create\s+(?:or\s+replace\s+)?(\w+(?:\s+view)?)\s+([\w.]+)", code)
        assert made == [("function", FN), ("function", API_FN)]

    def test_rollback_paragraph_is_written(self, mig):
        assert "되돌리기" in mig and "drop function api.list_rent_stat_history(text)" in mig

    def test_no_banned_words(self, mig):
        for w in ("적정가격", "적정가", "감정가", "평가액"):
            assert w not in mig


# ── ② 실행 가드 (로컬 PostgreSQL 이 있을 때만) ──────────────────────────────

SHIM = """
create schema api;
create table parcel (pnu char(19) primary key, geom text);
create table district (district_id text primary key, district_nm text, area_m2 numeric, geom text);
create table district_rone_map (district_id text, rone_region_nm text, primary key (district_id, rone_region_nm));
create table rent_stat (
  quarter char(6) not null,
  region_code text not null,
  region_nm text,
  bld_type text not null,
  vacancy_rate numeric(5,2),
  rent_per_m2 numeric(10,2),
  yield_rate numeric(5,2),
  conversion_rate numeric(5,2),
  rent_price_index numeric(8,2),
  floor_util_ratio jsonb,
  floor_rent jsonb,
  income_yield_rate numeric(5,2),
  primary key (quarter, region_code, bld_type)
);
-- 흉내 낸 공간 판정: 점 이름이 도형 글자 안에 '|이름|' 꼴로 들어 있으면 담긴 것(형제 test_district_openclose_migration 과 같은 꼴).
create function st_contains(poly text, pt text) returns boolean language sql immutable
  as 'select position(''|'' || pt || ''|'' in poly) > 0';
"""

IN_BOTH = "1168010100100010000"    # 좁은 상권 D1(조사구역 R1) · 넓은 상권 D2(R1·R2) 둘 다에 든다
IN_UNMAPPED = "1168010100100020000"  # 이을 근거 없는 상권 D3 에만 든다
NO_GEOM = "1168010100100030000"
OUTSIDE = "1168010100100040000"

FIXTURE = """
insert into parcel values
  ('{both}', 'A'), ('{unmapped}', 'B'), ('{nogeom}', null), ('{outside}', 'Z');
insert into district values
  ('D1', '좁은상권', 100, '|A|'), ('D2', '넓은상권', 900, '|A|'), ('D3', '이을근거없음', 50, '|B|');
insert into district_rone_map values ('D1', 'R1'), ('D2', 'R1'), ('D2', 'R2');
insert into rent_stat (quarter, region_code, region_nm, bld_type, vacancy_rate, rent_per_m2, yield_rate,
                       floor_util_ratio, floor_rent, income_yield_rate) values
  ('2026Q1', 'c1', 'R1', '집합상가', 10.00, 70.00, 0.80, '{{"1":100}}', '{{"1":70}}', 0.90),
  ('2026Q2', 'c1', 'R1', '집합상가', 11.00, 71.00, -0.20, '{{"1":100}}', '{{"1":71}}', 0.00),
  ('2025Q4', 'c1', 'R1', '집합상가', null, 69.00, 0.70, null, null, null),
  ('2026Q2', 'c2', 'R1', '오피스', 5.00, 20.00, 1.10, null, null, 0.80),
  ('2026Q2', 'c3', 'R2', '중대형상가', 7.00, 30.00, 0.60, null, null, 0.50),
  ('2026Q2', 'c9', 'R9', '집합상가', 1.00, 1.00, 1.00, null, null, 1.00);
"""


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    psycopg2 = pytest.importorskip("psycopg2")
    initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
    if not initdb or not pg_ctl:
        pytest.skip("로컬 PostgreSQL(initdb·pg_ctl)이 없다 — CI 는 글자 가드(①)만 본다")
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


@pytest.fixture(scope="module")
def cur(pg):
    """흉내 판 위에 새 두 함수(마이그레이션 글 그대로)와 정본 list_rent_stats(정본 글 그대로)를 넣는다."""
    mig = read(MIGRATION)
    schema = read(SCHEMA)
    c = pg.cursor()
    c.execute("drop schema if exists api cascade; drop schema if exists public cascade; create schema public;")
    c.execute(SHIM)
    c.execute(FIXTURE.format(both=IN_BOTH, unmapped=IN_UNMAPPED, nogeom=NO_GEOM, outside=OUTSIDE))
    c.execute(fn_block(mig, FN))
    c.execute(fn_block(mig, API_FN))
    c.execute(fn_block(schema, OLD_FN))
    return c


def _rows(cur, fn, pnu):
    cur.execute("select rone_region_nm, bld_type, quarter, vacancy_rate, rent_per_m2, yield_rate, income_yield_rate "
                "from {}(%s)".format(fn), (pnu,))
    return [tuple(None if v is None else (float(v) if not isinstance(v, str) else v) for v in r)
            for r in cur.fetchall()]


class TestRealRun:
    @pytest.mark.parametrize("fn", (FN, API_FN))
    def test_every_quarter_and_type_of_the_regions(self, cur, fn):
        """조사구역 R1·R2 의 네 종류 × 전 분기 · 상권이 둘이어도 R1 은 한 벌 · 빈 값은 null 그대로 · 음수·0 그대로."""
        assert _rows(cur, fn, IN_BOTH) == [
            ("R1", "오피스", "2026Q2", 5.0, 20.0, 1.1, 0.8),
            ("R1", "집합상가", "2025Q4", None, 69.0, 0.7, None),
            ("R1", "집합상가", "2026Q1", 10.0, 70.0, 0.8, 0.9),
            ("R1", "집합상가", "2026Q2", 11.0, 71.0, -0.2, 0.0),
            ("R2", "중대형상가", "2026Q2", 7.0, 30.0, 0.6, 0.5),
        ]

    def test_same_regions_as_list_rent_stats(self, cur):
        """두 함수가 같은 조사구역 집합을 말한다 — 카드의 줄마다 흐름이 같은 조사구역 것이다."""
        cur.execute("select distinct rone_region_nm from list_rent_stats(%s) order by 1", (IN_BOTH,))
        old = [r[0] for r in cur.fetchall()]
        new = sorted({r[0] for r in _rows(cur, API_FN, IN_BOTH)})
        assert old == new == ["R1", "R2"]

    def test_latest_row_matches_list_rent_stats(self, cur):
        """옛 함수의 최신 한 줄 = 새 함수의 그 분기 줄(종류마다) — 화면이 이 일치를 짝짓기 대조에 쓴다."""
        cur.execute("select rone_region_nm, bld_type, quarter, vacancy_rate, rent_per_m2, yield_rate "
                    "from list_rent_stats(%s)", (IN_BOTH,))
        hist = {(r[0], r[1], r[2]): r[3:6] for r in _rows(cur, API_FN, IN_BOTH)}
        for region, typ, q, vac, rent, yld in cur.fetchall():
            assert hist[(region, typ, q)] == tuple(None if v is None else float(v) for v in (vac, rent, yld))

    @pytest.mark.parametrize("pnu", (IN_UNMAPPED, NO_GEOM, OUTSIDE, "0000000000000000000"))
    def test_no_rows_without_a_path(self, cur, pnu):
        """이을 근거 없음 · 좌표 없음 · 상권 밖 · 없는 필지 — 줄이 아예 없다(시·도 평균으로 안 메운다)."""
        assert _rows(cur, API_FN, pnu) == []

    def test_twin_works_with_an_empty_search_path(self, cur):
        cur.execute("set search_path to ''")
        try:
            assert len(_rows(cur, API_FN, IN_BOTH)) == 5
        finally:
            cur.execute("reset search_path")

    def test_return_types(self, cur):
        cur.execute("select pg_typeof(rone_region_nm)::text, pg_typeof(quarter)::text, pg_typeof(vacancy_rate)::text, "
                    "pg_typeof(income_yield_rate)::text from api.list_rent_stat_history(%s) limit 1", (IN_BOTH,))
        assert cur.fetchone() == ("text", "text", "numeric", "numeric")

    def test_one_signature_per_name(self, cur):
        """이름당 pg_proc 1 — 같은 이름 둘이면 PostgREST 가 못 고른다(PGRST203)."""
        cur.execute("select n.nspname, count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                    "where p.proname = %s group by 1 order by 1", (FN,))
        assert cur.fetchall() == [("api", 1), ("public", 1)]
