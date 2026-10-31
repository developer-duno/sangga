# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-29a(대전 「동네 폐업 (대전시 공표)」 · 결정 0044)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙여 넣기 전에는 아무도 모르는 종류의 실수**다:

  1) 마이그레이션과 정본(schema.sql)의 글자가 갈린다 — 표 넷 · 함수 둘(머리·본문) · comment · 신선도 함수 덩어리.
     `create or replace` 는 머리 속성을 덮어쓰고 드리프트 가드는 `$$` 안 본문만 본다(CLAUDE.md ⛔ 2026-10-01a).
  2) 신선도 함수가 **12번 줄 말고 다른 것도** 바뀐다 → 2026-10-18a 판에 정한 갈래(줄 · 규칙 · comment)만 더한 글과 대조.
  3) 창이 결정과 다르다(최근 6개월을 안 뺀다 · 한 달만 걸쳐도 분기를 센다 · 8분기 상한) — 적재기 계산과 SQL 이 갈린다.
  4) public 원본에 grant · api 쌍둥이 grant 빠짐 · search_path 빠짐 · 서명 둘 · pnu 캐스트 빠짐.
  5) 표가 공개키에 열린다(RLS·revoke 빠짐).

② 실행 가드(로컬 PostgreSQL 이 있을 때만)는 흉내 판 위에 **마이그레이션 파일을 통째로** 돌려 예시값(지시서 #4·#5)을
   작은 가짜 행으로 재현한다. CI 에는 PostgreSQL 이 없어 건너뛴다.
"""

import datetime
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-29a_daejeon_dong_closure.sql")
PREV_FRESH = os.path.join(ROOT, "supabase", "migrations", "2026-10-18a_price_use_group.sql")  # 12번 줄 전 판
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

for _p in (os.path.join(ROOT, "scripts"), os.path.join(ROOT, "scripts", "collectors")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import load_daejeon8989_closure as L  # noqa: E402
import post_load  # noqa: E402

FN = "get_daejeon_dong_closure"
API_FN = "api.get_daejeon_dong_closure"
SIG = "(text)"
TABLES = ("daejeon_dong_closure", "daejeon_pnu_dong", "daejeon_bjd_dong", "daejeon_closure_release")

PUBLIC_HEAD = ("language sql", "stable", "security definer", "set search_path = public")
API_HEAD = ("language sql", "stable", "security definer", "set search_path = ''")

RETURNS = (
    "returns table (\n"
    "  status        text,\n"
    "  dong_nm       text,\n"
    "  received_on   date,\n"
    "  quarters      jsonb,\n"
    "  sum_quarters  jsonb,\n"
    "  clsbiz_sum    int,\n"
    "  industries    jsonb\n"
    ")\n"
)

CONST = "select date '2025-01-01' as start_month, 6 as lag_months, 8 as max_quarters, 4 as sum_quarters"

# 신선도 함수 = 2026-10-18a 판 + 이 갈래들(글자 그대로). 이 표 밖의 차이는 전부 '다른 것도 바뀌었다'다.
FRESH_ROW = (
    "    union all\n"
    "    -- 2026-10-29a(결정 0044) — 대전시 동네 폐업. 기준 = 사람이 대전시 사이트에서 받은 날(표지 한 줄)이다.\n"
    "    select 12, '동네 폐업 (대전시)', '받은 날',\n"
    "           (select r.received_on::text from daejeon_closure_release r),\n"
    "           'daejeon_closure',\n"
    "           '분기마다 (사람이 대전시 사이트에서 받음)'\n"
)
FRESH_BRANCH = (
    "           -- 대전시 동네 폐업: 받은 날 + 3개월(분기마다 사람이 받는다 — 2026-10-29a · 결정 0044).\n"
    "           --   'YYYY-MM-DD' 일 때만 — 모양이 다르면 ::date 가 터져 표가 통째로 사라진다.\n"
    "           when n.rule_kind = 'daejeon_closure' and n.basis ~ '^\\d{4}-\\d{2}-\\d{2}$'\n"
    "             then (n.basis::date + interval '3 months')::date\n"
)
FRESH_CHANGES = (
    ("           'seoul_openclose',\n           '분기마다'\n  ),",
     "           'seoul_openclose',\n           '분기마다'\n" + FRESH_ROW + "  ),"),
    ("             then make_date(n.basis::int + 1, 6, 30)\n",
     "             then make_date(n.basis::int + 1, 6, 30)\n" + FRESH_BRANCH),
    ("열 갈래 자료의 가장 최근 도장(분기·계약월·판·'\n  '계산일·수집일·기준월·고시일·공시 연도)",
     "열한 갈래 자료의 가장 최근 도장(분기·계약월·판·'\n  '계산일·수집일·기준월·고시일·공시 연도·받은 날)"),
    ("공시 연도의 다음 해 6월 30일(기준값이 네 자리 연도일 때만). '",
     "공시 연도의 다음 해 6월 30일(기준값이 네 자리 연도일 때만), 대전시 동네 폐업은 '\n"
     "  '받은 날 + 3개월(분기마다 사람이 받는다 · 기준값이 YYYY-MM-DD 일 때만). '"),
    ("(열 표가 전부 anon", "(열한 표가 전부 anon"),
    ("집계 도장 열 개뿐", "집계 도장 열한 개뿐"),
    ("성적표 줄 뺌 2026-10-18a(결정 0041)';",
     "성적표 줄 뺌 2026-10-18a(결정 0041) · 대전시 동네 폐업 2026-10-29a(결정 0044)';"),
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
    """줄 전체 주석을 걷은 실제 문장만 — 권한 가드는 이쪽을 본다(주석으로 죽인 문장을 '있다'로 보지 않게)."""
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


def fn_block(sql, name):
    """`create or replace function <name>(` 부터 `$$;` 까지 — 머리 + 본문 통째."""
    m = re.search(r"(?ms)^create\s+or\s+replace\s+function\s+" + re.escape(name) + r"\s*\(.*?\$\$\s*;", sql)
    assert m, "{} 의 정의를 못 찾았습니다 — 정규식이 헛돌면 아래 대조가 통째로 무의미해집니다".format(name)
    return m.group(0)


def fn_comment(sql, name):
    m = re.search(r"(?ms)^comment\s+on\s+function\s+" + re.escape(name) + r"\s*\(.*?';\s*$", sql)
    assert m, "{} 의 comment 를 못 찾았습니다".format(name)
    return m.group(0)


def table_block(sql, name):
    """`create table if not exists <name> (` 부터 그 표의 revoke 줄까지(comment·RLS 포함)."""
    m = re.search(r"(?ms)^create\s+table\s+if\s+not\s+exists\s+" + re.escape(name) + r"\s*\(.*?"
                  r"^revoke\s+all\s+on\s+" + re.escape(name) + r"\s+from[^\n]*;", sql)
    assert m, "{} 표 덩어리를 못 찾았습니다".format(name)
    return m.group(0)


def fresh_block(sql):
    """신선도 함수 — 정의 첫 줄부터 그 함수의 revoke 줄까지(머리·본문·comment)."""
    m = re.search(r"(?ms)^create\s+or\s+replace\s+function\s+get_data_freshness\s*\(\).*?"
                  r"^revoke\s+all\s+on\s+function\s+get_data_freshness\s*\(\)[^\n]*;", sql)
    assert m, "신선도 함수 덩어리를 못 찾았습니다"
    return m.group(0)


def head_of(block):
    return block[: block.index("$$")]


def head_problems(block, want):
    """머리에서 빠진 속성 목록(비면 정상). 가드 본체와 양성 대조가 같은 함수를 지난다.

    ⚠️ 못 보는 것: 한 줄에 여러 속성을 이어 쓴 꼴(`stable security definer`) — 이 레포 정본은 쓰지 않는다.
    """
    lines = {ln.strip().lower() for ln in head_of(block).splitlines()}
    return [w for w in want if w not in lines]


def definitions(sql, name):
    """`create [or replace] function <name>(` 이 몇 번 나오나(주석 밖 · 대소문자 무시)."""
    return len(re.findall(r"(?im)^\s*create\s+(?:or\s+replace\s+)?function\s+" + re.escape(name) + r"\s*\(",
                          statements(sql)))


def grant_targets(sql):
    """`grant … on function <대상>(` 의 대상 이름 전부(소문자 · 스키마 그대로).

    ⚠️ 못 보는 것: 인자 괄호 없는 `on function <이름> to …` · 따옴표 이름 · 일괄 grant(`all functions in schema`).
    """
    found = []
    for stmt in re.findall(r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*?"
                           r"\bon\s+(?:function|routine)\b([^;]*)", statements(sql)):
        found += re.findall(r"(?i)(?<![\w.])((?:\w+\.)?\w+)\s*\(", stmt)
    return [t.lower() for t in found]


def table_grants(sql):
    """표에 주는 grant(함수 아님) — 이 마이그레이션엔 0 이어야 한다.

    ⚠️ 못 보는 것: `grant … on all tables in schema` 꼴(그건 아래 문장 검사의 'all tables' 로 따로 잡는다).
    """
    return re.findall(r"(?is)(?<![\w.])grant\b[^;]*?\bon\s+(?:table\s+)?(?!function\b|routine\b)(\w+)\b[^;]*;",
                      statements(sql))


def fresh_derived_problems(new_block, old_block):
    """새 신선도 덩어리가 '2026-10-18a 덩어리 + FRESH_CHANGES' 와 글자로 같은가 — 어긋난 까닭(비면 정상)."""
    want, bad = old_block, []
    for a, b in FRESH_CHANGES:
        if want.count(a) != 1:
            bad.append("옛 덩어리에서 갈래 앞글을 한 번 찾지 못함: " + a.splitlines()[0])
            continue
        want = want.replace(a, b, 1)
    if new_block != want:
        w, g = want.splitlines(), new_block.splitlines()
        for i, (x, y) in enumerate(zip(w, g)):
            if x != y:
                bad.append("{}번째 줄이 다름: 기대 {!r} / 실제 {!r}".format(i + 1, x.strip(), y.strip()))
                break
        else:
            bad.append("줄 수가 다름: 기대 {} / 실제 {}".format(len(w), len(g)))
    return bad


# ── ① 글자 가드 ─────────────────────────────────────────────────────────────


class TestMirrorsTheSchema:
    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_function_head_and_body(self, mig, schema, name):
        assert fn_block(mig, name) == fn_block(schema, name)

    def test_comment(self, mig, schema):
        assert fn_comment(mig, FN) == fn_comment(schema, FN)

    @pytest.mark.parametrize("name", TABLES)
    def test_table_blocks(self, mig, schema, name):
        assert table_block(mig, name) == table_block(schema, name)

    def test_freshness_block(self, mig):
        """ⓘ 2026-10-31a(결정 0045 — 서울 4종 세 줄)부터 정본의 신선도 덩어리는 10-31a 와 같다(그 대조는
        tests/test_data_freshness_migration.py · tests/test_seoul_trdar_migration.py) — 이 원장(10-29a)은
        '10-18a 판 + 대전 갈래' 글 그대로여야 한다."""
        assert fresh_derived_problems(fresh_block(mig), fresh_block(read(PREV_FRESH))) == []

    def test_tables_come_before_the_freshness_function_in_schema(self, schema):
        """정본을 위에서부터 돌릴 때 sql 함수 본문 검사가 받은 날 표지를 찾아야 한다."""
        at = schema.index("create or replace function get_data_freshness()")
        for t in TABLES:
            assert schema.index("create table if not exists " + t) < at

    def test_mirror_detector_sees_a_head_only_change(self, mig, schema):
        bad = schema.replace(fn_block(schema, FN), fn_block(schema, FN).replace("stable\n", "volatile\n", 1), 1)
        assert fn_block(mig, FN) != fn_block(bad, FN)


class TestFreshnessOnlyGainsTheDaejeonRow:
    def test_new_block_is_the_old_block_plus_the_changes(self, mig):
        # ⓘ 2026-10-31a 부터 정본은 서울 4종 세 줄이 더 붙어 있어 원장(10-29a)을 본다.
        assert fresh_derived_problems(fresh_block(mig), fresh_block(read(PREV_FRESH))) == []

    @pytest.mark.parametrize("old,new", [
        ("           '월 1회'\n", "           '월 2회'\n"),                              # 다른 줄을 건드림
        ("interval '3 months')::date\n", "interval '4 months')::date\n"),              # 규칙 달 수
        ("'daejeon_closure',\n", "'none',\n"),                                         # 규칙 끔
        ("'^\\d{4}-\\d{2}-\\d{2}$'\n             then (n.basis::date", "'.*'\n             then (n.basis::date"),
    ])
    def test_detector_catches_variants(self, mig, old, new):
        block = fresh_block(mig)
        assert old in block, "전제: 그 글자가 지금 판에 있다"
        assert fresh_derived_problems(block.replace(old, new, 1), fresh_block(read(PREV_FRESH)))

    def test_api_twin_is_not_recreated(self, mig):
        """통과 함수라 본문이 그대로 — 다시 만들면 grant 를 다시 줘야 한다(2026-10-15a 와 같은 판단)."""
        assert definitions(mig, "api.get_data_freshness") == 0


class TestOneSignature:
    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_each_name_is_defined_once(self, mig, schema, name):
        assert definitions(mig, name) == 1
        assert definitions(schema, name) == 1

    def test_detector_counts_a_second_signature(self, mig):
        extra = "\ncreate or replace function get_daejeon_dong_closure(p_pnu text, p_x int)\n"
        assert definitions(mig + extra, FN) == 2


class TestHeads:
    def test_public_head(self, mig):
        assert head_problems(fn_block(mig, FN), PUBLIC_HEAD) == []
        assert RETURNS in head_of(fn_block(mig, FN))

    def test_api_twin_head_and_body(self, mig):
        block = fn_block(mig, API_FN)
        assert head_problems(block, API_HEAD) == []
        assert RETURNS in head_of(block)
        assert "$$ select * from public.get_daejeon_dong_closure(p_pnu) $$;" in block

    @pytest.mark.parametrize("old,new", [
        ("set search_path = public\n", ""),        # 변이 ⓔ
        ("security definer\n", ""),
        ("stable\n", "volatile\n"),
    ])
    def test_head_detector_catches_a_missing_attribute(self, mig, old, new):
        block = fn_block(mig, FN)
        assert head_problems(block.replace(old, new, 1), PUBLIC_HEAD)

    def test_pnu_cast_is_kept(self, mig):
        body = fn_block(mig, FN)
        assert "m.pnu = p_pnu::char(19)" in body
        assert "b.bjd_cd = left(p_pnu::char(19), 10)::char(10)" in body
        assert re.search(r"(?m)^\s+pnu\s+char\(19\)\s+primary key,", table_block(mig, "daejeon_pnu_dong"))

    def test_window_constants_match_the_loader(self, mig):
        """창의 수 넷은 적재기(dry-run·시험)와 SQL 이 같은 값이어야 한다 — 한쪽만 고치면 보고와 화면이 갈린다."""
        assert CONST in fn_block(mig, FN)
        assert (L.START_YM, L.LAG_MONTHS, L.MAX_QUARTERS, L.SUM_QUARTERS) == ("202501", 6, 8, 4)


class TestPermissions:
    def test_only_the_api_twin_is_granted(self, mig, schema):
        assert grant_targets(mig) == [API_FN]
        assert [t for t in grant_targets(schema) if t.endswith("daejeon_dong_closure")] == [API_FN]

    @pytest.mark.parametrize("bad", (
        "grant execute on function get_daejeon_dong_closure(text) to anon;",
        "grant all on function public.get_daejeon_dong_closure(text) to anon;",
        "  GRANT EXECUTE\n  ON FUNCTION Get_Daejeon_Dong_Closure ( text ) TO authenticated;",
    ))
    def test_grant_detector_catches_the_public_original(self, mig, bad):
        found = grant_targets(mig + "\n" + bad + "\n")
        assert [t for t in found if t != API_FN], found

    def test_grant_detector_sees_a_missing_twin_grant(self, mig):
        """변이 ⓓ — api 쌍둥이 grant 를 빼면 위 가드가 빨강(빈 목록)."""
        broken = mig.replace("grant execute on function api.get_daejeon_dong_closure(text) to anon, authenticated;",
                             "", 1)
        assert broken != mig and grant_targets(broken) == []

    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_every_function_is_revoked_with_anon_named(self, mig, schema, name):
        for sql in (mig, schema):
            assert re.search(r"(?m)^revoke all on function " + re.escape(name + SIG)
                             + r" from public, anon, authenticated;", statements(sql)), name

    def test_revoke_before_grant(self, mig):
        code = statements(mig)
        assert (code.index("revoke all on function api.get_daejeon_dong_closure(")
                < code.index("grant execute on function api.get_daejeon_dong_closure("))

    @pytest.mark.parametrize("name", TABLES)
    def test_tables_are_closed(self, mig, schema, name):
        for sql in (mig, schema):
            block = statements(table_block(sql, name))
            assert re.search(r"(?im)^alter\s+table\s+" + name + r"\s+enable\s+row\s+level\s+security\s*;", block)
            assert re.search(r"(?im)^revoke\s+all\s+on\s+" + name + r"\s+from\s+public,\s*anon,\s*authenticated\s*;",
                             block)

    def test_no_table_grant(self, mig):
        assert table_grants(mig) == []
        assert "all tables" not in statements(mig).lower()

    def test_table_grant_detector_sees_one(self, mig):
        assert table_grants(mig + "\ngrant select on daejeon_dong_closure to anon;\n") == ["daejeon_dong_closure"]
        assert table_grants(mig + "\ngrant select on table daejeon_pnu_dong to anon;\n") == ["daejeon_pnu_dong"]

    def test_allowlist_has_the_api_twin_only(self):
        assert API_FN in post_load.ANON_CALLABLE_ALLOWLIST
        assert FN not in post_load.ANON_CALLABLE_ALLOWLIST
        assert "public." + FN not in post_load.ANON_CALLABLE_ALLOWLIST
        for t in TABLES:
            assert t not in post_load.ANON_READABLE_ALLOWLIST

    def test_allowlist_total_is_36(self):
        """읽기 4 + 부르기 32 = `--check` 총계 36(2026-10-25a 의 33 에 이 함수 하나 → 34 ·
        2026-10-31a 결정 0045 서울 4종 34 → 36)."""
        assert len(post_load.ANON_READABLE_ALLOWLIST) + len(post_load.ANON_CALLABLE_ALLOWLIST) == 37


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

    def test_only_new_objects_and_the_freshness_function(self, mig):
        code = statements(mig)
        assert not re.search(r"(?im)^\s*drop\s", code)
        alters = re.findall(r"(?im)^alter\s+table\s+(\w+)\s+(.*);", code)
        assert alters == [(t, "enable row level security") for t in TABLES]
        made = re.findall(r"(?im)^create\s+(?:or\s+replace\s+)?(table|function)\s+(?:if\s+not\s+exists\s+)?([\w.]+)",
                          code)
        assert made == [("table", t) for t in TABLES] + [("function", FN), ("function", API_FN),
                                                          ("function", "get_data_freshness")]

    def test_tables_before_the_freshness_function(self, mig):
        code = statements(mig)
        assert code.index("create table if not exists daejeon_closure_release") < code.index(
            "create or replace function get_data_freshness()")

    def test_rollback_paragraph_is_written(self, mig):
        assert "되돌리기" in mig
        for s in ("drop function api.get_daejeon_dong_closure(text)", "drop table daejeon_closure_release",
                  "2026-10-18a_price_use_group.sql"):
            assert s in mig

    def test_no_banned_words(self, mig):
        for w in ("적정가격", "적정가", "감정가", "평가액"):
            assert w not in mig


# ── ② 실행 가드 (로컬 PostgreSQL 이 있을 때만) ──────────────────────────────

SHIM = """
create role anon;
create role authenticated;
create schema api;
create table snapshot_release (published_ym text);
create table transaction (contract_ym text);
create table ledger_release (release_ym text);
create table district (computed_at timestamptz);
create table lh_notice (collected_at timestamptz);
create table arch_permit (loaded_ym text);
create table nts_base_price (notice_date date);
create table rent_stat (quarter char(6));
create table parcel (pnu char(19) primary key, land_price_year smallint);
create table district_openclose (quarter text);
create table basis_override (v text);
"""

P_A = "3017010100100010000"     # ⓐ 지도에 있음 → 둔산2동
P_B = "3017010200100020000"     # ⓐ 없음 · 법정동 3017010200 이 ⓑ 에 → 가수원동
P_AB = "3017010200100030000"    # ⓐ 둔산2동 · ⓑ 가수원동 — ⓐ 가 이긴다
P_NONE = "3017010300100040000"  # 대전인데 지도 둘 다 없음 → no_dong
P_SEOUL = "1168010100107370000"

# (달, 동, 업종, 수) — 2024-12 줄은 적재기가 안 넣지만, 들어 있어도 창(2025-01~) 밖이라 안 센다.
CLOSURE = [
    ("202412", "둔산2동", "음식점업", 50),
    ("202501", "둔산2동", "음식점업", 2), ("202503", "둔산2동", "의원", 1),          # 20251 = 3
    ("202504", "둔산2동", "음식점업", 4), ("202506", "둔산2동", "병원", 3),          # 20252 = 7
    # 20253 = 0 (줄 없음)
    ("202510", "둔산2동", "의원", 2), ("202512", "둔산2동", "음식점업", 1),           # 20254 = 3
    ("202601", "둔산2동", "병원", 5), ("202603", "둔산2동", "음식점업", 1),           # 20261 = 6
    ("202604", "둔산2동", "음식점업", 9), ("202609", "둔산2동", "의원", 9),           # M(202604) 이 든 2분기는 아직 안 참 → 창 밖
    ("202601", "가수원동", "음식점업", 7),                                             # 다른 동
]
RECEIVED = datetime.date(2026, 10, 28)


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


def _fresh(conn, migration_sql=None, received=RECEIVED):
    """흉내 판을 새로 깔고 마이그레이션 글을 **통째로** 돌린 뒤 가짜 행을 넣는다(received None = 표지 0줄)."""
    cur = conn.cursor()
    cur.execute("drop schema if exists api cascade; drop schema if exists public cascade; create schema public;")
    cur.execute("drop role if exists anon; drop role if exists authenticated;")
    cur.execute(SHIM)
    cur.execute(migration_sql or read(MIGRATION))
    cur.executemany("insert into daejeon_dong_closure values (%s, %s, %s, %s)", CLOSURE)
    cur.execute("insert into daejeon_pnu_dong values (%s, '둔산2동'), (%s, '둔산2동')", (P_A, P_AB))
    cur.execute("insert into daejeon_bjd_dong values ('3017010200', '가수원동')")
    if received:
        cur.execute("insert into daejeon_closure_release (id, received_on) values (1, %s)", (received,))
    return cur


COLS = ("status", "dong_nm", "received_on", "quarters", "sum_quarters", "clsbiz_sum", "industries")


def _call(cur, pnu, fn=API_FN):
    cur.execute("select {} from {}(%s)".format(", ".join(COLS), fn), (pnu,))
    return [dict(zip(COLS, r)) for r in cur.fetchall()]


def _set_received(cur, day):
    cur.execute("update daejeon_closure_release set received_on = %s", (day,))


@pytest.fixture(scope="module")
def cur(pg):
    return _fresh(pg)


class TestRealRun:
    def test_ok_example(self, cur):
        rows = _call(cur, P_A)
        assert len(rows) == 1
        r = rows[0]
        assert (r["status"], r["dong_nm"], r["received_on"]) == ("ok", "둔산2동", RECEIVED)
        assert r["quarters"] == [{"quarter": "20251", "clsbiz_co": 3}, {"quarter": "20252", "clsbiz_co": 7},
                                 {"quarter": "20253", "clsbiz_co": 0}, {"quarter": "20254", "clsbiz_co": 3},
                                 {"quarter": "20261", "clsbiz_co": 6}]
        assert r["sum_quarters"] == ["20252", "20253", "20254", "20261"]
        assert r["clsbiz_sum"] == 16
        # 많은 순 · 같으면 이름 순(병원 8 · 음식점업 5 · 의원 2 — 202503 의원 1 은 20251 이라 4분기 밖)
        assert r["industries"] == [{"induty_nm": "병원", "clsbiz_co": 8}, {"induty_nm": "음식점업", "clsbiz_co": 6},
                                   {"induty_nm": "의원", "clsbiz_co": 2}]

    def test_ok_matches_the_loader_arithmetic(self, cur):
        """적재기의 dong_summary(dry-run 이 쓰는 셈)와 SQL 이 같은 수를 낸다 — 2024 줄은 적재기 걸러 내기 뒤."""
        rows = [r for r in CLOSURE if r[0] >= L.START_YM]
        per_q, total, top = L.dong_summary(rows, "둔산2동", L.window_quarters(RECEIVED))
        r = _call(cur, P_A)[0]
        assert [q["clsbiz_co"] for q in r["quarters"]] == per_q
        assert r["clsbiz_sum"] == total
        assert [(i["induty_nm"], i["clsbiz_co"]) for i in r["industries"]] == top

    @pytest.mark.parametrize("day", [
        datetime.date(2026, 10, 28), datetime.date(2026, 11, 30), datetime.date(2026, 12, 1),
        datetime.date(2025, 10, 1), datetime.date(2025, 9, 1), datetime.date(2029, 1, 15), datetime.date(2027, 3, 31),
    ])
    def test_window_is_the_same_as_the_loader(self, cur, day):
        _set_received(cur, day)
        try:
            r = _call(cur, P_A)[0]
            assert [q["quarter"] for q in r["quarters"]] == L.window_quarters(day)
            assert r["sum_quarters"] == L.window_quarters(day)[-L.SUM_QUARTERS:]
        finally:
            _set_received(cur, RECEIVED)

    def test_window_with_no_full_quarter_yet_is_empty(self, cur):
        _set_received(cur, datetime.date(2025, 8, 31))
        try:
            r = _call(cur, P_A)[0]
            assert (r["status"], r["quarters"], r["sum_quarters"], r["clsbiz_sum"], r["industries"]) == (
                "ok", [], [], 0, [])
        finally:
            _set_received(cur, RECEIVED)

    def test_bjd_fallback_and_pnu_wins(self, cur):
        assert _call(cur, P_B)[0]["dong_nm"] == "가수원동"
        assert _call(cur, P_AB)[0]["dong_nm"] == "둔산2동"
        gs = _call(cur, P_B)[0]
        assert gs["quarters"][-1] == {"quarter": "20261", "clsbiz_co": 7}

    @pytest.mark.parametrize("pnu,status", [(P_NONE, "no_dong"), (P_SEOUL, "not_daejeon"), ("", "not_daejeon")])
    def test_other_statuses_have_no_numbers(self, cur, pnu, status):
        r = _call(cur, pnu)
        assert len(r) == 1
        r = r[0]
        assert r["status"] == status
        assert (r["dong_nm"], r["quarters"], r["sum_quarters"], r["clsbiz_sum"], r["industries"]) == (
            None, None, None, None, None)

    def test_no_release_row_gives_no_rows(self, pg):
        c = _fresh(pg, received=None)
        try:
            assert _call(c, P_A) == []
        finally:
            _fresh(pg)

    def test_twin_works_with_an_empty_search_path(self, cur):
        cur.execute("set search_path to ''")
        try:
            assert _call(cur, P_A)[0]["clsbiz_sum"] == 16
        finally:
            cur.execute("reset search_path")

    def test_one_signature_per_name(self, cur):
        cur.execute("select n.nspname, count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                    "where p.proname = %s group by 1 order by 1", (FN,))
        assert cur.fetchall() == [("api", 1), ("public", 1)]

    def test_privileges(self, cur):
        for t in TABLES:
            cur.execute("select has_table_privilege('anon', %s, 'select'), "
                        "(select relrowsecurity from pg_class where relname = %s)", (t, t))
            assert cur.fetchone() == (False, True), t
        cur.execute("select has_function_privilege('anon', 'public.get_daejeon_dong_closure(text)', 'execute'), "
                    "has_function_privilege('anon', 'api.get_daejeon_dong_closure(text)', 'execute'), "
                    "has_function_privilege('authenticated', 'api.get_daejeon_dong_closure(text)', 'execute')")
        assert cur.fetchone() == (False, True, True)

    def test_answer_is_json_serialisable_like_the_screen_reads_it(self, cur):
        cur.execute("select json_agg(t) from api.get_daejeon_dong_closure(%s) t", (P_A,))
        row = json.loads(json.dumps(cur.fetchone()[0]))[0]
        assert row["received_on"] == "2026-10-28" and row["clsbiz_sum"] == 16


class TestFreshnessRealRun:
    def _rows(self, cur):
        cur.execute("select src, basis_kind, basis, next_expected::text, cadence from get_data_freshness()")
        rows = cur.fetchall()
        assert len(rows) == 11
        assert rows[-1][0] == "동네 폐업 (대전시)"         # ord 12 — 맨 끝
        return {r[0]: r[1:] for r in rows}

    def test_row(self, cur):
        assert self._rows(cur)["동네 폐업 (대전시)"] == (
            "받은 날", "2026-10-28", "2027-01-28", "분기마다 (사람이 대전시 사이트에서 받음)")

    def test_empty_release_keeps_the_row(self, pg):
        c = _fresh(pg, received=None)
        try:
            assert self._rows(c)["동네 폐업 (대전시)"][:3] == ("받은 날", None, None)
        finally:
            _fresh(pg)

    @pytest.mark.parametrize("v,expected", [("2026-11-30", "2027-02-28"), ("2026-10", None), ("20261028", None),
                                            (None, None)])
    def test_shapes_via_override(self, pg, v, expected):
        basis = "(select r.received_on::text from daejeon_closure_release r)"
        sql = read(MIGRATION)
        assert sql.count(basis) == 1
        c = _fresh(pg, sql.replace(basis, "(select v from basis_override)", 1))
        try:
            c.execute("insert into basis_override values (%s)", (v,))
            assert self._rows(c)["동네 폐업 (대전시)"][1:3] == (v, expected)
        finally:
            _fresh(pg)

    def test_other_rows_still_compute(self, cur):
        cur.execute("insert into transaction values ('202610')")
        try:
            assert self._rows(cur)["실거래 (매매)"][2] == "2026-11-30"
        finally:
            cur.execute("delete from transaction")


class TestRealRunMutations:
    """변이가 실제로 값을 바꾸는가 — 위 실행 가드가 그 변이를 빨강으로 잡는다는 근거."""

    def _quarters(self, pg, old, new):
        sql = read(MIGRATION)
        assert sql.count(old) == 1, old
        c = _fresh(pg, sql.replace(old, new, 1))
        try:
            return [q["quarter"] for q in _call(c, P_A)[0]["quarters"]]
        finally:
            _fresh(pg)

    def test_a_no_six_month_lag(self, pg):
        """변이 ⓐ — 6개월을 0개월로: 창에 20262·20263 이 붙는다."""
        got = self._quarters(pg, "6 as lag_months", "0 as lag_months")
        assert got != L.window_quarters(RECEIVED) and got[-1] == "20263"

    def test_b_one_month_is_enough(self, pg):
        """변이 ⓑ — 세 달 다가 아니라 한 달이라도: 202604 가 든 2분기가 창에 든다."""
        got = self._quarters(pg, "make_interval(months => c.lag_months + 2)", "make_interval(months => c.lag_months)")
        assert got[-1] == "20262"

    def test_e_no_search_path_breaks_the_twin(self, pg):
        """변이 ⓔ — public 원본의 search_path 를 빼면 화면 경로(빈 search_path)에서 표를 못 찾는다."""
        sql = read(MIGRATION)
        block = fn_block(sql, FN)
        c = _fresh(pg, sql.replace(block, block.replace("set search_path = public\n", "", 1), 1))
        psycopg2 = pytest.importorskip("psycopg2")
        try:
            c.execute("set search_path to ''")
            with pytest.raises(psycopg2.Error):
                _call(c, P_A)
        finally:
            c.execute("reset search_path")
            _fresh(pg)

    def test_d_no_twin_grant_closes_the_door(self, pg):
        """변이 ⓓ — api 쌍둥이 grant 를 빼면 anon 이 못 부른다."""
        sql = read(MIGRATION).replace(
            "grant execute on function api.get_daejeon_dong_closure(text) to anon, authenticated;", "", 1)
        c = _fresh(pg, sql)
        try:
            c.execute("select has_function_privilege('anon', 'api.get_daejeon_dong_closure(text)', 'execute')")
            assert c.fetchone() == (False,)
        finally:
            _fresh(pg)


# ── 보완 1 — 받은 날 앞으로만(적재기 SQL 의 관문을 실제로 돌린다) · 그물 6호 힌트 ──────────


def _forward_guard(received):
    """적재기 build_sql 에서 받은 날 앞으로만 관문(do 블록) 하나만 떼어 낸다 — \copy 는 psycopg2 로 못 돌린다."""
    sql = L.build_sql({"closure": "c.csv", "pnu": "p.csv", "bjd": "b.csv"}, {"closure": 0, "pnu": 0, "bjd": 0}, received)
    m = re.search(r"(?ms)^do \$\$\nbegin\n  if exists \(select 1 from daejeon_closure_release where received_on > .*?^end \$\$;", sql)
    assert m, "받은 날 관문을 못 찾았다"
    return m.group(0)


class TestForwardOnlyRealRun:
    def test_older_folder_is_refused_and_same_day_is_allowed(self, pg):
        psycopg2 = pytest.importorskip("psycopg2")
        c = _fresh(pg)   # 표지 = 2026-10-28
        try:
            with pytest.raises(psycopg2.Error, match="옛 판으로 되돌리지 않습니다"):
                c.execute(_forward_guard(datetime.date(2026, 10, 1)))
            c.execute(_forward_guard(datetime.date(2026, 10, 28)))     # 같은 날 = 다시 넣기
            c.execute(_forward_guard(datetime.date(2027, 1, 28)))      # 앞으로
        finally:
            _fresh(pg)

    def test_empty_release_lets_the_first_load_through(self, pg):
        c = _fresh(pg, received=None)
        try:
            c.execute(_forward_guard(datetime.date(2026, 10, 28)))
        finally:
            _fresh(pg)


def test_freshness_issue_hint_for_the_daejeon_row():
    """그물 6호 — 지난 대전 줄의 이슈 본문에 할 일 한 줄(전부 다시 받기 → 적재 순서) · 다른 줄엔 없다."""
    import check_data_freshness as cdf  # noqa: PLC0415

    rows = [
        {"src": "동네 폐업 (대전시)", "basis_kind": "받은 날", "basis": "2026-10-28", "next_expected": "2027-01-28"},
        {"src": "건축 인허가", "basis_kind": "기준월", "basis": "202608", "next_expected": "2026-10-31"},
    ]
    today = datetime.date(2027, 2, 1)
    bodies = {i["src"]: cdf.build_issue_body(i, today) for i in cdf.find_overdue(rows, today)}
    dj = bodies["동네 폐업 (대전시)"]
    assert "2025-01 부터 지난달까지 전부 다시 받기" in dj and "load_daejeon8989_closure.py" in dj
    assert dj.index("--dry-run") < dj.index("post_load.py") < dj.index("backup_raw.py")
    assert "load_daejeon8989_closure" not in bodies["건축 인허가"]
    assert cdf.find_overdue(rows, datetime.date(2027, 1, 28)) == [] or all(
        i["src"] != "동네 폐업 (대전시)" for i in cdf.find_overdue(rows, datetime.date(2027, 1, 28)))
