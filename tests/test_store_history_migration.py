# -*- coding: utf-8 -*-
"""마이그레이션 *_store_history.sql(이 자리 가게 이력 — 결정 0045 PR④)의 불변식.

두 겹으로 본다.

  ① 글자 가드(언제나 돈다 · CI 포함)
     · 정본(schema.sql) ↔ 마이그 **글자 대조**: 표 둘 덩어리 · 함수 둘(머리 security definer·search_path·stable 까지) ·
       comment · 신선도 함수 덩어리(머리·본문·comment·revoke) · unit_business.biz_no 칸 설명
     · 신선도 = 2026-10-31a 판 + 정한 갈래(16번 줄 · comment 네 곳)만 — 그 밖의 차이는 빨강 · 새 rule_kind 0
     · grant 는 api 쌍둥이에만 · public 원본 revoke · 표 둘 RLS·revoke · 색인 이름·칸 차례 · 기본키 · check
     · post_load 허용 총계 37 · ANALYZE_TABLES 둘 · 그물 6호 힌트 열쇠·화면 CARD_SOURCES.history = 정본 자료 이름
     · 덩어리: lock_timeout 이 begin 앞 · begin/commit 하나 · notify 는 commit 뒤 · 새 객체만
  ② 실행 가드(로컬 PostgreSQL 이 있을 때만 · CI 는 건너뛴다 — 형제 시험과 같은 빈 DB 흉내 판)
     빈 DB 에 신선도 함수가 읽는 표만 깔고 **마이그 파일을 통째로** 돌린 뒤 가짜 줄로 부른다 — 표지 없음 0줄 ·
     정렬 · 넘기기 · total_cnt · no_data · 인자 자르기 · 신선도 16줄과 예정일 · 권한 · 두 번 적용 · 변이.

ⓘ 파일 이름의 날짜는 적용 예정일이다(메인이 적용 날에 맞춰 바꿀 수 있다) — 이름 끝 `_store_history.sql` 로 찾는다.
ⓘ 도우미는 이 파일 안에서만 쓴다(시험 파일끼리 import 하지 않는 레포 관습).
"""

import datetime
import glob
import os
import re
import shutil
import socket
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS = os.path.join(ROOT, "supabase", "migrations")
FOUND = sorted(glob.glob(os.path.join(MIGRATIONS, "*_store_history.sql")))
PREV_FRESH = os.path.join(MIGRATIONS, "2026-10-31a_seoul_trdar.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
CARD_TS = os.path.join(ROOT, "src", "lib", "dataFreshness.ts")

for _p in (os.path.join(ROOT, "scripts"), os.path.join(ROOT, "scripts", "collectors")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import check_data_freshness as cdf  # noqa: E402
import post_load  # noqa: E402

TABLES = ("store_history", "store_history_release")
FN = "get_store_history"
API_FN = "api." + FN
SIG = "(text, integer, integer)"
SRC = "가게 이력 (점포 자료 누적)"
RETURNS = ("status", "floor_no", "biz_name", "first_ym", "last_ym", "seen_cnt", "is_current", "truncated",
           "total_cnt", "current_cnt", "history_first_ym", "history_last_ym")

ROW16 = (
    "    union all\n"
    "    -- 2026-11-01a(결정 0045 PR④) — 가게 이력 결과표의 마지막 분기. 점포 줄(ord 1)과 같은 `sangkwon` 규칙 — 같은 분기면\n"
    "    --   같은 날 「지났습니다」가 뜬다(정상 · 새 분기 적재 → 빌드 → 적재 순서). 표지가 비면 basis null(화면 '자료 없음').\n"
    "    select 16, '가게 이력 (점포 자료 누적)', '분기',\n"
    "           (select r.last_ym::text from store_history_release r),\n"
    "           'sangkwon',\n"
    "           '분기마다 (새 분기 점포 자료를 적재한 뒤 다시 굽는다)'\n"
)
OLD_LAST_ROW = "           '연 1회 (서울시 공지) · 실제는 불규칙 — 예정일 계산 안 함'\n"
FRESH_CHANGES = (
    (OLD_LAST_ROW + "  ),", OLD_LAST_ROW + ROW16 + "  ),"),
    ("열넷 갈래 자료", "열다섯 갈래 자료"),
    ("(열넷 표가 전부 anon", "(열다섯 표가 전부 anon"),
    ("집계 도장 열네 개뿐", "집계 도장 열다섯 개뿐"),
    ("서울 상권 4종 세 줄 2026-10-31a(결정 0045)';",
     "서울 상권 4종 세 줄 2026-10-31a(결정 0045) · 가게 이력 2026-11-01a(결정 0045 PR④)';"),
)
BIZ_NO_OLD = "업종분류 개편(837→247) 시 번호가 새로 생성되어 과거와 연계 불가. 주소+상호명 재매칭 필요"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


@pytest.fixture(scope="module")
def mig():
    assert len(FOUND) == 1, "*_store_history.sql 마이그가 정확히 하나여야 합니다: {}".format(FOUND)
    return read(FOUND[0])


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


def statements(sql):
    """줄 전체 주석을 걷은 실제 문장만(주석으로 죽인 문장을 '있다'로 보지 않게)."""
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


def fn_block(sql, name):
    """`create or replace function <name>(` 부터 그 `$$;` 까지 — 줄머리 고정(api. 와 안 섞이게)."""
    m = re.search(r"(?ms)^create\s+or\s+replace\s+function\s+" + re.escape(name) + r"\s*\(.*?\$\$\s*;", sql)
    assert m, "{} 의 정의를 못 찾았습니다".format(name)
    return m.group(0)


def head_of(block):
    return block[: block.index("$$")]


def body_of(block):
    return block.split("$$")[1]


def fn_comment(sql):
    m = re.search(r"(?ms)^comment\s+on\s+function\s+" + FN + r"\s*\(\s*text\s*,\s*integer\s*,\s*integer\s*\)\s+is"
                  r".*?';\s*$", sql)
    assert m, "comment 를 못 찾았습니다"
    return m.group(0)


def table_block(sql, name):
    """`create table if not exists <name> (` 부터 그 표의 revoke 줄까지(comment·색인·RLS 포함)."""
    m = re.search(r"(?ms)^create\s+table\s+if\s+not\s+exists\s+" + re.escape(name) + r"\s*\(.*?"
                  r"^revoke\s+all\s+on\s+" + re.escape(name) + r"\s+from[^\n]*;", sql)
    assert m, "{} 표 덩어리를 못 찾았습니다".format(name)
    return m.group(0)


def fresh_block(sql):
    m = re.search(r"(?ms)^create\s+or\s+replace\s+function\s+get_data_freshness\s*\(\).*?"
                  r"^revoke\s+all\s+on\s+function\s+get_data_freshness\s*\(\)[^\n]*;", sql)
    assert m, "신선도 함수 덩어리를 못 찾았습니다"
    return m.group(0)


def biz_no_comment(sql):
    m = re.search(r"(?m)^comment on column unit_business\.biz_no is '[^\n]*';$", statements(sql))
    assert m, "unit_business.biz_no 칸 설명을 못 찾았습니다"
    return m.group(0)


def code_lines(text):
    """주석(`--` 뒤)을 걷고 빈 줄을 뺀 줄 목록."""
    out = []
    for ln in text.splitlines():
        ln = re.sub(r"--.*$", "", ln).rstrip()
        if ln.strip():
            out.append(ln)
    return out


def grant_targets(sql):
    """`grant … on function <대상>(` 의 대상 이름 전부(소문자 · 스키마 그대로) — 회수는 안 센다."""
    found = []
    for stmt in re.findall(r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*?\bon\s+(?:function|routine)\b([^;]*)",
                           statements(sql)):
        found += re.findall(r"(?i)(?<![\w.])((?:\w+\.)?\w+)\s*\(", stmt)
    return [t.lower() for t in found]


def rule_kinds(block):
    """신선도 raw 의 rule_kind 글자 모음(주석 밖)."""
    code = "\n".join(code_lines(body_of(block)))
    raw = code[: code.index("norm as")]
    return set(re.findall(r"^\s+'([a-z_]+)',\s*$", raw, re.M)) | set(
        re.findall(r"'([a-z_]+)'::text\s+as\s+rule_kind", raw))


def fresh_derived_problems(new_block, old_block):
    want, bad = old_block, []
    for a, b in FRESH_CHANGES:
        if want.count(a) != 1:
            bad.append("옛 덩어리에서 갈래 앞글을 한 번 찾지 못함: " + a.splitlines()[0])
            continue
        want = want.replace(a, b, 1)
    if new_block != want:
        bad.append("2026-10-31a 판 + 정한 갈래와 글자가 다릅니다")
    return bad


# ── ① 글자 가드 ─────────────────────────────────────────────────────────────


class TestMirrorsTheSchema:
    @pytest.mark.parametrize("name", TABLES)
    def test_table_blocks(self, mig, schema, name):
        assert table_block(mig, name) == table_block(schema, name)

    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_function_head_and_body(self, mig, schema, name):
        assert fn_block(mig, name) == fn_block(schema, name)

    def test_comment(self, mig, schema):
        assert fn_comment(mig) == fn_comment(schema)

    def test_freshness_block(self, mig, schema):
        assert fresh_block(mig) == fresh_block(schema)

    def test_biz_no_comment(self, mig, schema):
        assert biz_no_comment(mig) == biz_no_comment(schema)

    def test_mirror_detector_sees_a_head_only_change(self, mig, schema):
        bad = schema.replace(fn_block(schema, FN), fn_block(schema, FN).replace("set search_path = public\n", "", 1), 1)
        assert fn_block(mig, FN) != fn_block(bad, FN)

    def test_tables_come_before_the_freshness_function_in_schema(self, schema):
        at = schema.index("create or replace function get_data_freshness()")
        for t in TABLES:
            assert schema.index("create table if not exists " + t + " (") < at


class TestHeadsAndReturns:
    def test_public_head(self, mig):
        lines = {ln.strip() for ln in head_of(fn_block(mig, FN)).splitlines()}
        for w in ("language sql", "stable", "security definer", "set search_path = public"):
            assert w in lines, w

    def test_api_head_and_pass_through(self, mig):
        block = fn_block(mig, API_FN)
        lines = {ln.strip() for ln in head_of(block).splitlines()}
        assert {"language sql", "stable", "security definer", "set search_path = ''"} <= lines
        assert "$$ select * from public.get_store_history(p_pnu, p_limit, p_offset) $$;" in block

    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_signature_and_returned_columns(self, mig, name):
        block = fn_block(mig, name)
        assert "(p_pnu text, p_limit int default 20, p_offset int default 0)" in block
        m = re.search(r"(?is)returns\s+table\s*\((.*?)\)\s*language", block)
        assert tuple(ln.split()[0] for ln in m.group(1).splitlines() if ln.strip()) == RETURNS

    def test_one_signature_per_name(self, mig, schema):
        for name in (FN, API_FN):
            for sql in (mig, schema):
                assert len(re.findall(r"(?im)^\s*create\s+(?:or\s+replace\s+)?function\s+" + re.escape(name)
                                      + r"\s*\(", statements(sql))) == 1, name

    def test_pnu_cast(self, mig):
        body = body_of(fn_block(mig, FN))
        assert "where h.pnu = p_pnu::char(19)" in body
        assert re.search(r"\bh\.pnu\s*=\s*p_pnu\s*(?:\)|and|$)", body, re.M) is None

    def test_sort_and_paging_clamp(self, mig):
        body = " ".join(" ".join(code_lines(body_of(fn_block(mig, FN)))).split())
        assert ("order by h.is_current desc, h.seen_cnt desc, h.floor_no asc nulls last, h.biz_name, h.biz_no_last, "
                "h.last_ym) as rn" in body)
        assert "least(greatest(coalesce(p_limit, 20), 1), 100)" in body
        # 보완 2 G-2 — offset 상한(정수 넘침 막기) · 셈은 bigint.
        assert "least(greatest(coalesce(p_offset, 0), 0), 2000000)" in body
        assert "m.rn <= pa.off::bigint + pa.lim" in body
        assert "biz_no_last" not in body.split("row_number()")[0].split("select h.")[1]   # 번호는 안 나간다


class TestPermissions:
    def test_only_the_api_twin_is_granted(self, mig, schema):
        assert grant_targets(mig) == [API_FN]
        assert [t for t in grant_targets(schema) if t.endswith(FN)] == [API_FN]

    @pytest.mark.parametrize("bad", [
        "grant execute on function get_store_history(text, integer, integer) to anon;",
        "  GRANT ALL\n  ON FUNCTION public.Get_Store_History ( text, int, int ) TO authenticated;",
    ])
    def test_grant_detector_catches_the_public_original(self, mig, bad):
        assert [t for t in grant_targets(mig + "\n" + bad + "\n") if not t.startswith("api.")]

    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_every_function_is_revoked_with_anon_named(self, mig, schema, name):
        for sql in (mig, schema):
            assert re.search(r"(?m)^revoke all on function " + re.escape(name + SIG)
                             + r" from public, anon, authenticated;", statements(sql)), name

    @pytest.mark.parametrize("name", TABLES)
    def test_tables_are_closed(self, mig, schema, name):
        for sql in (mig, schema):
            block = statements(table_block(sql, name))
            assert "alter table {} enable row level security;".format(name) in block
            assert "revoke all on {} from public, anon, authenticated;".format(name) in block
            assert not re.search(r"(?is)\bgrant\b[^;]*\bon\s+(?:table\s+)?(?:public\.)?" + name + r"\b",
                                 statements(sql))

    def test_post_load_allowlist(self):
        assert API_FN in post_load.ANON_CALLABLE_ALLOWLIST
        assert FN not in post_load.ANON_CALLABLE_ALLOWLIST and "public." + FN not in post_load.ANON_CALLABLE_ALLOWLIST
        for t in TABLES:
            assert t not in post_load.ANON_READABLE_ALLOWLIST
        assert len(post_load.ANON_READABLE_ALLOWLIST) + len(post_load.ANON_CALLABLE_ALLOWLIST) == 37
        assert set(TABLES) <= set(post_load.ANALYZE_TABLES)


class TestTablesShape:
    def test_history_columns_pk_and_checks(self, mig):
        block = table_block(mig, "store_history")
        assert "primary key (biz_no_last, last_ym)," in block
        assert "primary key (biz_no_last, first_ym)" not in block
        assert "check (first_ym <= last_ym)" in block
        assert re.search(r"(?m)^\s+floor_no\s+smallint check \(floor_no is null or floor_no <> 0\),$", block)
        for c in ("first_ym", "last_ym"):
            assert re.search(r"(?m)^\s+" + c + r"\s+char\(6\) not null check \(" + c
                             + r" ~ '\^\\d\{4\}\(03\|06\|09\|12\)\$'\),$", block), c
        assert re.search(r"(?m)^\s+seen_cnt\s+smallint not null check \(seen_cnt >= 1\),$", block)
        assert re.search(r"(?m)^\s+n_links\s+smallint not null default 0 check \(n_links >= 0\),$", block)
        assert re.search(r"(?m)^\s+pnu\s+char\(19\) not null,$", block)

    def test_index_name_and_column_order(self, mig):
        assert ("create index if not exists idx_store_history_pnu on store_history "
                "(pnu, is_current desc, seen_cnt desc);") in table_block(mig, "store_history")

    def test_release_table(self, mig):
        block = table_block(mig, "store_history_release")
        assert re.search(r"(?m)^\s+id\s+smallint primary key check \(id = 1\),$", block)
        assert re.search(r"(?m)^\s+first_ym\s+char\(6\) not null check \(first_ym ~ ", block)
        assert re.search(r"(?m)^\s+last_ym\s+char\(6\) not null check", block)
        assert re.search(r"(?m)^\s+loaded_at\s+timestamptz not null default now\(\),$", block)
        assert re.search(r"(?m)^\s+check \(first_ym <= last_ym\)$", block)

    def test_function_counts_current_and_reads_release_first(self, mig):
        body = " ".join(" ".join(code_lines(body_of(fn_block(mig, FN)))).split())
        assert "(count(*) filter (where mine.is_current))::int as n_cur" in body
        assert "select r.first_ym, r.last_ym from store_history_release r" in body
        assert "c.n, c.n_cur, r.first_ym, r.last_ym from rel r" in body

    def test_biz_no_comment_is_corrected(self, mig, schema):
        for sql in (mig, schema):
            line = biz_no_comment(sql)
            assert "95~99%" in line and "store_history" in line and "2017Q3" in line
            # 보완 1 F-7 — 끊긴 분기는 2024Q4 · 20220806 은 발급일 도장(끊기는 자리라고 쓰지 않는다).
            assert "2024Q4 대량 재발급" in line and "발급일 도장" in line and "2022-08 일괄" not in line
            assert BIZ_NO_OLD not in statements(sql)


class TestFreshness:
    def test_new_block_is_the_old_block_plus_the_changes(self, mig):
        assert fresh_derived_problems(fresh_block(mig), fresh_block(read(PREV_FRESH))) == []

    @pytest.mark.parametrize("old,new", [
        ("store_history_release r),\n           'sangkwon',", "store_history_release r),\n           'none',"),
        ("           '월 1회'\n", "           '월 2회'\n"),
        ("열다섯 갈래", "열넷 갈래"),
    ])
    def test_detector_catches_variants(self, mig, old, new):
        block = fresh_block(mig)
        assert old in block
        assert fresh_derived_problems(block.replace(old, new, 1), fresh_block(read(PREV_FRESH)))

    def test_sixteen_rows_and_no_new_rule_kind(self, mig):
        block = fresh_block(mig)
        body = "\n".join(code_lines(body_of(block)))
        assert body.count("union all") == 14
        assert re.search(r"select 16, '가게 이력 \(점포 자료 누적\)', '분기',\n\s+\(select r\.last_ym::text from "
                         r"store_history_release r\),\n\s+'sangkwon',", body)
        assert rule_kinds(block) == rule_kinds(fresh_block(read(PREV_FRESH)))

    def test_comment_says_fifteen_three_times(self, mig):
        m = re.search(r"(?ms)^comment\s+on\s+function\s+get_data_freshness\s*\(\)\s+is.*?';\s*$", mig)
        text = m.group(0)
        assert "열다섯 갈래" in text and "열다섯 표" in text and "집계 도장 열다섯 개" in text
        assert "열넷" not in text and "열네 개" not in text

    def test_api_twin_is_not_recreated(self, mig):
        assert not re.search(r"(?im)^\s*create\s+(?:or\s+replace\s+)?function\s+api\.get_data_freshness",
                             statements(mig))

    def test_hint_key_and_card_source_are_the_server_label(self, schema):
        assert "'{}'".format(SRC) in schema
        assert SRC in cdf.SOURCE_HINTS
        m = re.search(r"history:\s*\{\s*src:\s*'([^']+)'", read(CARD_TS))
        assert m and m.group(1) == SRC


class TestMigrationShape:
    def test_settings_before_begin_and_notify_after_commit(self, mig):
        code = statements(mig)
        begin = re.search(r"(?m)^begin;", code).start()
        commit = re.search(r"(?m)^commit;", code).start()
        assert code.index("set lock_timeout = '5s';") < begin < commit < code.index("notify pgrst, 'reload schema';")
        assert len(re.findall(r"(?m)^begin;", code)) == 1 and len(re.findall(r"(?m)^commit;", code)) == 1
        for stmt in re.finditer(r"(?im)^(create|drop|alter|insert|revoke|grant|comment)\b", code):
            assert begin < stmt.start() < commit, "begin/commit 밖의 문장: " + stmt.group(0)

    def test_only_new_objects_the_comment_and_the_freshness_function(self, mig):
        code = statements(mig)
        assert not re.search(r"(?im)^\s*(?:drop|insert|update|delete|truncate)\s", code)
        alters = re.findall(r"(?im)^alter\s+table\s+(\w+)\s+(.*);", code)
        assert alters == [(t, "enable row level security") for t in TABLES]
        made = re.findall(r"(?im)^create\s+(?:or\s+replace\s+)?(table|function|index)\s+(?:if\s+not\s+exists\s+)?([\w.]+)",
                          code)
        assert made == [("table", "store_history"), ("index", "idx_store_history_pnu"),
                        ("table", "store_history_release"), ("function", FN), ("function", API_FN),
                        ("function", "get_data_freshness")]
        cols = re.findall(r"(?im)^comment\s+on\s+column\s+(\w+)\.", code)
        assert set(cols) == {"store_history", "unit_business"}

    def test_rollback_paragraph_is_written(self, mig):
        for s in ("되돌리기", "2026-10-31a_seoul_trdar.sql", "drop function api.get_store_history(text, integer, integer)",
                  "drop table store_history_release", "37 → 36", BIZ_NO_OLD):
            assert s in mig, s

    def test_no_banned_words(self, mig):
        for w in ("적정가격", "적정가", "감정가", "평가액", "가치평가"):
            assert w not in mig


# ── ② 실행 가드 (로컬 PostgreSQL 이 있을 때만) ──────────────────────────────

SHIM = """
create role anon;
create role authenticated;
create schema api;
create table unit_business (biz_no text);
-- get_data_freshness 가 읽는 나머지 표 — 그 함수가 만들어지고 돌 만큼만.
create table snapshot_release (published_ym text);
create table transaction (contract_ym text);
create table ledger_release (release_ym text);
create table district (computed_at timestamptz);
create table lh_notice (collected_at timestamptz);
create table arch_permit (loaded_ym text);
create table nts_base_price (notice_date date);
create table rent_stat (quarter char(6));
create table parcel (land_price_year smallint);
create table district_openclose (quarter text);
create table daejeon_closure_release (received_on date);
create table district_sales (quarter char(5));
create table district_pop_flow (quarter char(5));
create table seoul_trdar_release (tbl text, value_quarter char(5));
"""

PA = "1168010100100010000"
PB = "1168010100100020000"     # 줄 없는 땅
PC = "3017010100100010000"     # 한 줄만 있는 다른 땅

# (pnu, floor, 상호, 번호, 처음, 마지막, 보인 분기 수, 지금 보임, 이은 수, 첫 분기부터)
ROWS = (
    (PA, 1, "가", "B1", "201712", "202606", 35, True, 0, True),
    (PA, 2, "나", "B2", "202003", "202606", 26, True, 1, False),
    (PA, None, "다", "B3", "202403", "202606", 10, True, 0, False),
    (PA, 1, "라", "B4", "201803", "202312", 24, False, 0, False),
    (PA, -1, "마", "B5", "201906", "202112", 11, False, 0, False),
    (PA, 3, "바", "B6", "202006", "202203", 8, False, 0, False),
    (PA, 2, "사", "B7", "202106", "202312", 11, False, 0, False),
    (PC, 1, "아", "C1", "202606", "202606", 1, True, 0, False),
)
ORDER_A = ["B1", "B2", "B3", "B4", "B5", "B7", "B6"]    # 지금 보임 → 보인 분기 수 ↓ → 층(모름 끝)


def _fill(cur, last_ym="202606"):
    for r in ROWS:
        cur.execute("insert into store_history (pnu, floor_no, biz_name, biz_no_last, first_ym, last_ym, seen_cnt, "
                    "is_current, n_links, truncated) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", r)
    cur.execute("insert into store_history_release (id, first_ym, last_ym, built_on, row_cnt) "
                "values (1, '201712', %s, %s, %s)", (last_ym, datetime.date(2026, 11, 1), len(ROWS)))


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


def _fresh(conn, migration_sql=None, fill=True):
    """흉내 판을 새로 깔고 마이그 파일을 **통째로** 돌린 뒤 가짜 줄을 넣는다."""
    cur = conn.cursor()
    cur.execute("drop schema if exists api cascade; drop schema if exists public cascade; create schema public;")
    cur.execute("drop role if exists anon; drop role if exists authenticated;")
    cur.execute(SHIM)
    cur.execute(migration_sql or read(FOUND[0]))
    if fill:
        _fill(cur)
    return cur


def _call(cur, pnu, *args):
    holes = ", ".join(["%s"] * (1 + len(args)))
    cur.execute("select {} from api.get_store_history({})".format(", ".join(RETURNS), holes), (pnu,) + args)
    return [dict(zip(RETURNS, r)) for r in cur.fetchall()]


def _fresh_rows(cur):
    cur.execute("select src, basis_kind, basis, next_expected, cadence from get_data_freshness()")
    rows = cur.fetchall()
    assert len(rows) == 15
    return {r[0]: r[1:] for r in rows}


@pytest.fixture(scope="module")
def cur(pg):
    return _fresh(pg)


class TestRealRunHistory:
    def test_no_release_gives_zero_rows(self, pg):
        c = _fresh(pg, fill=False)
        try:
            assert _call(c, PA) == [] and _call(c, PB) == []
        finally:
            _fresh(pg)

    def test_sort_total_and_release(self, cur):
        rows = _call(cur, PA, 100, 0)
        assert [r["biz_name"] for r in rows] == ["가", "나", "다", "라", "마", "사", "바"]
        assert {(r["status"], r["total_cnt"], r["current_cnt"], r["history_first_ym"], r["history_last_ym"])
                for r in rows} == {("ok", 7, 3, "201712", "202606")}
        assert [r["is_current"] for r in rows] == [True] * 3 + [False] * 4
        assert rows[2]["floor_no"] is None and rows[0]["truncated"] is True

    def test_default_limit_is_twenty(self, cur):
        assert len(_call(cur, PA)) == 7

    def test_paging(self, cur):
        names = {"가": "B1", "나": "B2", "다": "B3", "라": "B4", "마": "B5", "바": "B6", "사": "B7"}
        got = [[names[r["biz_name"]] for r in _call(cur, PA, 3, off)] for off in (0, 3, 6)]
        assert got == [ORDER_A[:3], ORDER_A[3:6], ORDER_A[6:]]
        assert all((r["total_cnt"], r["current_cnt"]) == (7, 3) for r in _call(cur, PA, 3, 3))

    def test_offset_past_the_end_gives_zero_rows(self, cur):
        assert _call(cur, PA, 3, 7) == []

    def test_other_land_is_no_data_one_row(self, cur):
        assert _call(cur, PB) == [{"status": "no_data", "floor_no": None, "biz_name": None, "first_ym": None,
                                   "last_ym": None, "seen_cnt": None, "is_current": None, "truncated": None,
                                   "total_cnt": 0, "current_cnt": 0, "history_first_ym": "201712",
                                   "history_last_ym": "202606"}]
        assert [(r["status"], r["biz_name"], r["total_cnt"], r["current_cnt"]) for r in _call(cur, PC)] == \
            [("ok", "아", 1, 1)]

    def test_huge_offset_gives_zero_rows_not_an_error(self, pg):
        """보완 2 G-2 — p_offset 2147483647 에서 정수 넘침(22003)이 나지 않고 0줄.

        ⚠️ 옛 코드의 넘침은 계획에 달렸다 — 앞 시험들이 같은 표를 오래 쓴 뒤(통계·캐시)에는 넘침 식을 안 거치는 계획이 골라져
        옛 코드도 통과했다(변이 실측). 그래서 방금 만든 판(새 표 · 첫 호출)에서 본다 — 글자 쪽은 위
        test_sort_and_paging_clamp 가 상한·bigint 를 따로 지킨다.
        """
        c = _fresh(pg)
        try:
            c.execute("discard plans")
            assert _call(c, PA, 100, 2147483647) == []
            assert [r["status"] for r in _call(c, PB, 100, 2147483647)] == ["no_data"]   # 줄 없는 땅은 넘기기와 무관하게 한 줄
            assert _call(c, PA, 100, 2000000) == []
        finally:
            _fresh(pg)

    @pytest.mark.parametrize("limit,offset,n", [(0, 0, 1), (-5, 0, 1), (1000, 0, 7), (3, -4, 3)])
    def test_arguments_are_clamped(self, cur, limit, offset, n):
        rows = _call(cur, PA, limit, offset)
        assert len(rows) == n and rows[0]["biz_name"] == "가"

    def test_limit_is_capped_at_one_hundred(self, pg):
        c = _fresh(pg)
        try:
            for i in range(120):
                c.execute("insert into store_history (pnu, floor_no, biz_name, biz_no_last, first_ym, last_ym, "
                          "seen_cnt, is_current, n_links, truncated) values (%s, 1, %s, %s, '202606', '202606', 1, "
                          "true, 0, false)", (PB, "x{:03d}".format(i), "X{:03d}".format(i)))
            rows = _call(c, PB, 1000, 0)
            assert len(rows) == 100 and rows[0]["total_cnt"] == 120
        finally:
            _fresh(pg)

    def test_same_number_and_first_quarter_twice_is_allowed(self, pg):
        """자료 성질(10-31 빌드 17건) — 같은 번호 · 같은 first_ym · 다른 last_ym 두 줄은 들어가고, 같은 last_ym 이면 막힌다."""
        psycopg2 = pytest.importorskip("psycopg2")
        c = _fresh(pg)
        sql = ("insert into store_history (pnu, floor_no, biz_name, biz_no_last, first_ym, last_ym, seen_cnt, "
               "is_current, n_links, truncated) values (%s, 1, '바고', 'X1', '201712', %s, %s, %s, %s, true)")
        try:
            c.execute(sql, (PB, "202212", 21, False, 0))
            c.execute(sql, (PB, "202606", 35, True, 1))
            assert [r["seen_cnt"] for r in _call(c, PB)] == [35, 21]
            with pytest.raises(psycopg2.errors.UniqueViolation):
                c.execute(sql, (PB, "202606", 1, True, 0))
        finally:
            _fresh(pg)

    @pytest.mark.parametrize("col,val", [("floor_no", 0), ("first_ym", "201711"), ("seen_cnt", 0)])
    def test_checks_reject_bad_rows(self, pg, col, val):
        psycopg2 = pytest.importorskip("psycopg2")
        c = _fresh(pg)
        row = dict(zip(("pnu", "floor_no", "biz_name", "biz_no_last", "first_ym", "last_ym", "seen_cnt",
                        "is_current", "n_links", "truncated"), (PB, 1, "z", "Z1", "201712", "202606", 35, True, 0, True)))
        row[col] = val
        try:
            with pytest.raises(psycopg2.errors.CheckViolation):
                c.execute("insert into store_history ({}) values ({})".format(
                    ", ".join(row), ", ".join(["%s"] * len(row))), tuple(row.values()))
        finally:
            _fresh(pg)


class TestRealRunFreshness:
    def test_history_row_due_2026_10_31(self, cur):
        """202606 → 분기말 + 5개월 − 하루 = 2026-10-31(점포 줄 1번과 같은 규칙 · 같은 날)."""
        kind, basis, nxt, cadence = _fresh_rows(cur)[SRC]
        assert (kind, basis) == ("분기", "202606")
        assert nxt == datetime.date(2026, 10, 31) and nxt is not None
        assert "다시 굽는다" in cadence

    def test_loading_the_current_quarter_is_not_overdue(self, pg):
        """적재 당일 안 지남 — 오늘이 든 분기 코드를 넣으면 예정일이 오늘보다 뒤다(오늘 기준으로 계산 · 하드코딩 0)."""
        today = datetime.date.today()
        qm = ((today.month - 1) // 3 + 1) * 3
        ym = "{:04d}{:02d}".format(today.year, qm)
        c = _fresh(pg, fill=False)
        try:
            _fill(c, last_ym=ym)
            nxt = _fresh_rows(c)[SRC][2]
            assert nxt is not None and nxt >= today
        finally:
            _fresh(pg)

    def test_empty_release_keeps_the_row(self, pg):
        c = _fresh(pg, fill=False)
        try:
            assert _fresh_rows(c)[SRC][1:3] == (None, None)
        finally:
            _fresh(pg)

    def test_mutation_row16_rule_none_loses_the_date(self, pg):
        """양성 대조 — 16 줄 규칙을 none 으로 바꾸면 예정일이 사라진다(위 날짜 단언이 빨강)."""
        sql = read(FOUND[0])
        old = "store_history_release r),\n           'sangkwon',"
        assert sql.count(old) == 1
        c = _fresh(pg, sql.replace(old, "store_history_release r),\n           'none',", 1))
        try:
            assert _fresh_rows(c)[SRC][2] is None
        finally:
            _fresh(pg)


class TestRealRunPrivilegesAndReplay:
    def test_privileges(self, cur):
        for t in TABLES:
            cur.execute("select has_table_privilege('anon', %s, 'select'), "
                        "(select relrowsecurity from pg_class where relname = %s)", (t, t))
            assert cur.fetchone() == (False, True), t
        cur.execute("select has_function_privilege('anon', %s, 'execute'), "
                    "has_function_privilege('anon', %s, 'execute'), "
                    "has_function_privilege('authenticated', %s, 'execute')",
                    ("public.get_store_history" + SIG, API_FN + SIG, API_FN + SIG))
        assert cur.fetchone() == (False, True, True)

    def test_twin_works_with_an_empty_search_path(self, cur):
        cur.execute("set search_path to ''")
        try:
            assert _call(cur, PA, 1, 0)[0]["biz_name"] == "가"
        finally:
            cur.execute("reset search_path")

    def test_one_signature_per_name(self, cur):
        cur.execute("select n.nspname, count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                    "where p.proname = %s group by 1 order by 1", (FN,))
        assert cur.fetchall() == [("api", 1), ("public", 1)]

    def test_biz_no_comment_is_applied(self, cur):
        cur.execute("select col_description('unit_business'::regclass, 1)")
        assert "95~99%" in cur.fetchone()[0]

    def test_applying_twice_gives_the_same_answer(self, pg):
        c = _fresh(pg)
        try:
            before = (_call(c, PA, 100, 0), _call(c, PB), _fresh_rows(c))
            c.execute(read(FOUND[0]))
            assert (_call(c, PA, 100, 0), _call(c, PB), _fresh_rows(c)) == before
        finally:
            _fresh(pg)

    def test_mutation_public_grant_opens_the_original(self, pg):
        """변이 — public 원본에도 grant 를 주면 anon 이 원본을 부를 수 있다(위 권한 단언이 빨강)."""
        line = "grant execute on function api.get_store_history(text, integer, integer) to anon, authenticated;"
        sql = read(FOUND[0])
        assert sql.count(line) == 1
        c = _fresh(pg, sql.replace(line, line + "\ngrant execute on function get_store_history(text, integer, integer) "
                                   "to anon;", 1))
        try:
            c.execute("select has_function_privilege('anon', 'public.get_store_history(text, integer, integer)', "
                      "'execute')")
            assert c.fetchone() == (True,)
        finally:
            _fresh(pg)


# ── ③ 적재 SQL 실행 가드 (보완 2 G-7 · 로컬 PostgreSQL + psql 이 있을 때만) ───────────────────
# 적재기 build_sql 은 `\copy` 를 쓰므로 psycopg2 로는 못 돌린다 — 같은 흉내 판에 psql 로 파일을 통째로 보낸다.
# 정상 적재 · ⒦ 어긋남 롤백 · ⒧ 어긋남 롤백 셋을 본다(글자 대조만으로는 raise 가 실제로 통째 되돌리는지 모른다).

LOAD_ROWS = [
    ["1168010100100010000", "1", "가", "B1", "201712", "201803", "2", "t", "0", "t"],
    ["3017010100100010000", "", "나", "B2", "201803", "201803", "1", "t", "0", "f"],
    ["1168010100100010000", "-1", "다", "B3", "201712", "201712", "1", "f", "0", "t"],
]
LOAD_META = {"built_on": "2026-11-01", "start_ym": "201712", "end_ym": "201803", "sido": ["11", "30"]}


def _load_setup(pg, loaded_ym, ub_rows):
    """흉내 판 + 적재기가 읽는 칸(snapshot_release.loaded_ym · unit_business 분기·pnu) + 앞서 들어 있던 한 줄."""
    c = _fresh(pg, fill=False)
    c.execute("alter table snapshot_release add column loaded_ym char(6)")
    c.execute("insert into snapshot_release (published_ym, loaded_ym) values (%s, %s)", (loaded_ym, loaded_ym))
    c.execute("alter table unit_business add column snapshot_ym char(6), add column pnu char(19)")
    c.execute("insert into unit_business (biz_no, snapshot_ym, pnu) "
              "select 'U' || g, '201803', case when g %% 2 = 1 then '1168010100100010000' else '3017010100100010000' end "
              "from generate_series(0, %s - 1) g", (ub_rows,))
    c.execute("insert into store_history values ('1168010100199990000', 1, '옛가게', 'OLD', '201712', '201712', 1, "
              "false, 0, true)")
    c.execute("insert into store_history_release (id, first_ym, last_ym, built_on, row_cnt) "
              "values (1, '201712', '201712', '2026-08-01', 1)")
    return c


def _run_load_sql(pg, tmp_path, rows=LOAD_ROWS):
    """적재기의 사본 쓰기 + build_sql 그대로 → psql -f. → psql 종료 코드."""
    psql = shutil.which("psql")
    if not psql:
        pytest.skip("psql 이 없다 — 적재 SQL(\\copy) 실행 시험은 psql 이 있을 때만")
    import load_store_history as lsh  # noqa: PLC0415
    src = tmp_path / "result.csv"
    with open(src, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(lsh.COLUMNS) + "\n" + "".join(",".join(r) + "\n" for r in rows))
    staging = str(tmp_path / "staging" / "store_history.csv")
    n = lsh.write_staging(str(src), staging)
    sql_path = tmp_path / "load.sql"
    sql_path.write_text(lsh.build_sql(staging, n, LOAD_META), encoding="utf-8")
    env = dict(os.environ, PGCLIENTENCODING="UTF8")
    r = subprocess.run([psql, "-h", "127.0.0.1", "-p", str(pg.info.port), "-U", "postgres", "-d", "postgres",
                        "-v", "ON_ERROR_STOP=1", "-q", "-f", str(sql_path)],
                       env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=120)
    return r.returncode, r.stderr.decode("utf-8", "replace")


def _state(c):
    c.execute("select count(*), count(*) filter (where is_current), string_agg(biz_no_last, ',' order by biz_no_last) "
              "from store_history")
    hist = c.fetchone()
    c.execute("select first_ym, last_ym, row_cnt from store_history_release")
    return hist, c.fetchall()


class TestRealRunLoadSql:
    def test_normal_load_replaces_everything_and_writes_the_release(self, pg, tmp_path):
        c = _load_setup(pg, "201803", ub_rows=2)
        try:
            rc, err = _run_load_sql(pg, tmp_path)
            assert rc == 0, err
            hist, rel = _state(c)
            assert hist == (3, 2, "B1,B2,B3")              # 옛 줄(OLD)은 통째 교체로 사라졌다
            assert rel == [("201712", "201803", 3)]
        finally:
            _fresh(pg)

    def test_k_mismatch_rolls_back_everything(self, pg, tmp_path):
        """⒦ — 결과표 마지막 분기(201803) ≠ snapshot_release.loaded_ym(201712) → raise → 옛 줄·옛 표지 그대로."""
        c = _load_setup(pg, "201712", ub_rows=2)
        try:
            rc, err = _run_load_sql(pg, tmp_path)
            assert rc != 0 and "⒦" in err
            hist, rel = _state(c)
            assert hist == (1, 0, "OLD") and rel == [("201712", "201712", 1)]
        finally:
            _fresh(pg)

    def test_l_mismatch_rolls_back_everything(self, pg, tmp_path):
        """⒧ — 지금 보이는 줄 2 vs 점포 표 그 분기·두 시·도 줄 10(0.5% 넘게 다름) → raise → 옛 줄·옛 표지 그대로."""
        c = _load_setup(pg, "201803", ub_rows=10)
        try:
            rc, err = _run_load_sql(pg, tmp_path)
            assert rc != 0 and "⒧" in err
            hist, rel = _state(c)
            assert hist == (1, 0, "OLD") and rel == [("201712", "201712", 1)]
        finally:
            _fresh(pg)

    @staticmethod
    def _current_rows(n):
        """지금 보이는 줄 n 개(마지막 분기 201803 · ⒦ 통과) — 두 시·도에 번갈아."""
        return [["1168010100100010000" if i % 2 else "3017010100100010000", "1", "가", "C{}".format(i),
                 "201803", "201803", "1", "t", "0", "f"] for i in range(n)]

    @pytest.mark.parametrize("current, passes", [(1004, True), (1006, False)])
    def test_l_boundary_half_percent(self, pg, tmp_path, current, passes):
        """⒧ 경계(보완 3 H-5) — 점포 표 1,000줄 · 허용 0.5% = 5줄. 지금 보이는 줄 1,004(차 4) 통과 · 1,006(차 6) raise·롤백.
        적재기 코드 그대로(build_sql 이 받는 수치) — 허용치를 바꾸면 한쪽이 빨강."""
        c = _load_setup(pg, "201803", ub_rows=1000)
        try:
            rc, err = _run_load_sql(pg, tmp_path, self._current_rows(current))
            hist, rel = _state(c)
            if passes:
                assert rc == 0, err
                # 표지 첫 분기는 빌드 정보(LOAD_META start_ym)에서 온다.
                assert hist[:2] == (current, current) and rel == [("201712", "201803", current)]
            else:
                assert rc != 0 and "⒧" in err
                assert hist == (1, 0, "OLD") and rel == [("201712", "201712", 1)]
        finally:
            _fresh(pg)
