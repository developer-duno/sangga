# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-31a(서울 상권 4종 — 결정 0045 PR②)의 불변식.

두 겹으로 본다.

  ① 글자 가드(언제나 돈다 · CI 포함)
     · 정본(schema.sql) ↔ 마이그 **글자 대조**: 표 다섯 덩어리 · 함수 넷(머리 security definer·search_path·stable 까지) ·
       comment 둘 · 신선도 함수 덩어리(머리·본문·comment·revoke)
     · 신선도 = 2026-10-29a 판 + 정한 갈래(13·14·15 줄 · comment 네 곳)만 — 그 밖의 차이는 빨강 · 새 rule_kind 0
     · 상권 찾기(me·hit)·status(head)·창(win)·차례가 list_district_openclose 본문과 **주석 밖 글자가 같다** + 변형 양성 대조
     · grant 는 api 쌍둥이 둘에만 · public 원본 revoke · 표 다섯 RLS·revoke · 색인 넷 · 기본키
     · post_load 허용 총계 36 · ANALYZE_TABLES 넷 · 그물 6호 힌트 열쇠 = 정본 자료 이름
     · 덩어리: lock_timeout 이 begin 앞 · begin/commit 하나 · notify 는 commit 뒤 · 새 객체만
  ② 실행 가드(로컬 PostgreSQL 이 있을 때만 · CI 는 건너뛴다 — 0033 시험과 같은 흉내 판)
     PostGIS 없이 `geometry` 를 글자로, `st_contains` 를 "점 이름이 도형 글자에 들었나"로 흉내 낸 빈 DB 에 **마이그 파일을
     통째로** 돌리고 가짜 행으로 부른다 — 상위 5·그 밖 합·창 합·업종 전부·좁은 상권 먼저 · 인구 셋(최신 분기 · 표지 기준 ·
     하나 없으면 그 칸만 null · 셋 다 없으면 no_data) · 빈 상태 넷 · 신선도 14줄과 예정일 · 권한 · 두 번 적용.
     ⚠️ 흉내 낸 st_contains 는 진짜 공간 판정이 아니다 — 공간 술어는 ①의 글자 대조로 지킨다.

ⓘ 도우미는 이 파일 안에서만 쓴다(시험 파일끼리 import 하지 않는 레포 관습).
"""

import datetime
import os
import re
import shutil
import socket
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-31a_seoul_trdar.sql")
PREV_FRESH = os.path.join(ROOT, "supabase", "migrations", "2026-10-29a_daejeon_dong_closure.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

for _p in (os.path.join(ROOT, "scripts"), os.path.join(ROOT, "scripts", "collectors")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import check_data_freshness as cdf  # noqa: E402
import post_load  # noqa: E402

TABLES = ("district_sales", "district_pop_flow", "district_pop_resident", "district_pop_worker")
RELEASE = "seoul_trdar_release"
ALL_TABLES = TABLES + (RELEASE,)
FNS = ("list_district_sales", "list_district_pop")
API_FNS = tuple("api." + f for f in FNS)
OPENCLOSE = "list_district_openclose"

SALES_RETURNS = ("status", "district_id", "district_nm", "district_type", "latest_quarter", "window_quarters",
                 "trend", "top", "rest_cnt", "rest_amt", "rest_co", "industries")
POP_RETURNS = ("status", "district_id", "district_nm", "district_type", "flow_table_quarter", "flow_quarter", "flow",
               "resident_value_quarter", "resident_last_quarter", "resident",
               "worker_value_quarter", "worker_last_quarter", "worker")

# 신선도 = 2026-10-29a 판 + 이 갈래들(글자 그대로). 이 표 밖의 차이는 전부 '다른 것도 바뀌었다'다.
FRESH_ROWS = (
    "    union all\n"
    "    -- 2026-10-31a(결정 0045) — 서울시 상권분석서비스 추정매출·길단위인구. 분기 꼴은 개업·폐업과 같은 'YYYYQ' 라\n"
    "    --   같은 규칙(seoul_openclose — 분기말 + 5개월 - 하루)을 쓴다.\n"
    "    select 13, '상권 추정매출 (서울시)', '분기',\n"
    "           (select max(t.quarter)::text from district_sales t),\n"
    "           'seoul_openclose',\n"
    "           '분기마다'\n"
    "    union all\n"
    "    select 14, '상권 길단위인구 (서울시)', '분기',\n"
    "           (select max(t.quarter)::text from district_pop_flow t),\n"
    "           'seoul_openclose',\n"
    "           '분기마다'\n"
    "    union all\n"
    "    -- 2026-10-31a(결정 0045 · 사장님 결정 10-31 「다음 예정 없음」) — 상주·직장인구는 한 줄. 기준 = 값이 마지막으로\n"
    "    --   바뀐 분기 둘을 글로 합친다(표지 seoul_trdar_release). 서울시 공지는 연 1회지만 실제 갱신이 불규칙(상주\n"
    "    --   2024·2025 건너뜀)이라 예정일을 계산하지 않는다('none' → null). 표지가 비면 basis 도 null(화면 '자료 없음').\n"
    "    select 15, '상권 상주·직장인구 (서울시)', '값이 바뀐 분기',\n"
    "           (select '상주 ' || left(a.value_quarter, 4) || '년 ' || right(a.value_quarter, 1) || '분기, 직장 '\n"
    "                   || left(b.value_quarter, 4) || '년 ' || right(b.value_quarter, 1) || '분기'\n"
    "              from seoul_trdar_release a, seoul_trdar_release b\n"
    "             where a.tbl = 'district_pop_resident' and b.tbl = 'district_pop_worker'),\n"
    "           'none',\n"
    "           '연 1회 (서울시 공지) · 실제는 불규칙 — 예정일 계산 안 함'\n"
)
OLD_LAST_ROW = "           'daejeon_closure',\n           '분기마다 (사람이 대전시 사이트에서 받음)'\n"
FRESH_CHANGES = (
    (OLD_LAST_ROW + "  ),", OLD_LAST_ROW + FRESH_ROWS + "  ),"),
    ("열한 갈래 자료의 가장 최근 도장(분기·계약월·판·'\n  '계산일·수집일·기준월·고시일·공시 연도·받은 날)",
     "열넷 갈래 자료의 가장 최근 도장(분기·계약월·판·'\n  '계산일·수집일·기준월·고시일·공시 연도·받은 날·값이 바뀐 분기)"),
    ("받은 날 + 3개월(분기마다 사람이 받는다 · 기준값이 YYYY-MM-DD 일 때만). '",
     "받은 날 + 3개월(분기마다 사람이 받는다 · 기준값이 YYYY-MM-DD 일 때만). 서울 상권 추정매출·길단위인구는 '\n"
     "  '개업·폐업과 같은 분기 규칙이고, 서울 상권 상주·직장인구는 실제 갱신이 불규칙해 예정일을 계산하지 않는다'\n"
     "  '(기준 = 값이 마지막으로 바뀐 분기 둘을 글로 합침). '"),
    ("(열한 표가 전부 anon", "(열넷 표가 전부 anon"),
    ("집계 도장 열한 개뿐", "집계 도장 열네 개뿐"),
    ("대전시 동네 폐업 2026-10-29a(결정 0044)';",
     "대전시 동네 폐업 2026-10-29a(결정 0044) · 서울 상권 4종 세 줄 2026-10-31a(결정 0045)';"),
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


def fn_comment(sql, name):
    m = re.search(r"(?ms)^comment\s+on\s+function\s+" + re.escape(name) + r"\s*\(\s*text\s*\)\s+is.*?';\s*$", sql)
    assert m, "{} 의 comment 를 못 찾았습니다".format(name)
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


def code_lines(text):
    """주석(`--` 뒤)을 걷고 빈 줄을 뺀 줄 목록 — 「주석 밖 글자」 대조용."""
    out = []
    for ln in text.splitlines():
        ln = re.sub(r"--.*$", "", ln).rstrip()
        if ln.strip():
            out.append(ln)
    return out


def cte(body, name):
    """본문에서 `<name> as (` … `\\n  ),` 덩어리(주석 밖 줄 목록). 못 찾으면 None."""
    m = re.search(r"(?s)\b" + re.escape(name) + r"(?:\s*\([^)]*\))?\s+as\s*\((.*?)\n  \),", body)
    return code_lines(m.group(1)) if m else None


def shared_cte_problems(body, ref_body, names=("me", "hit", "head"), table=None):
    """body 의 CTE 들이 기준(list_district_openclose) 본문과 주석 밖 글자가 같은가 — 문제 문장 목록(비면 정상).

    table 을 주면 win 도 견준다(기준의 `district_openclose` 를 그 표 이름으로 바꿔서).
    못 보는 것: CTE 이름을 바꾼 꼴(못 찾음으로 걸린다) · 공백 수만 다른 꼴(rstrip 만 한다 — 그것도 다름으로 본다).
    """
    bad = []
    for n in names:
        a, b = cte(body, n), cte(ref_body, n)
        if a is None or b is None or a != b:
            bad.append("{} 가 list_district_openclose 와 다릅니다".format(n))
    if table:
        ref = cte(ref_body.replace("district_openclose", table), "win")
        if cte(body, "win") is None or cte(body, "win") != ref:
            bad.append("win 이 list_district_openclose 의 창과 다릅니다")
    return bad


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
        bad.append("2026-10-29a 판 + 정한 갈래와 글자가 다릅니다")
    return bad


# ── ① 글자 가드 ─────────────────────────────────────────────────────────────


class TestMirrorsTheSchema:
    @pytest.mark.parametrize("name", ALL_TABLES)
    def test_table_blocks(self, mig, schema, name):
        assert table_block(mig, name) == table_block(schema, name)

    @pytest.mark.parametrize("name", FNS + API_FNS)
    def test_function_head_and_body(self, mig, schema, name):
        assert fn_block(mig, name) == fn_block(schema, name)

    @pytest.mark.parametrize("name", FNS)
    def test_comment(self, mig, schema, name):
        assert fn_comment(mig, name) == fn_comment(schema, name)

    def test_freshness_block(self, mig):
        """ⓘ 2026-11-01a(결정 0045 PR④ — 가게 이력 16번 줄)부터 정본의 신선도 덩어리는 11-01a 와 같다(그 대조는
        tests/test_data_freshness_migration.py · tests/test_store_history_migration.py) — 이 원장(10-31a)은
        '10-29a 판 + 서울 4종 갈래' 글 그대로여야 한다."""
        assert fresh_derived_problems(fresh_block(mig), fresh_block(read(PREV_FRESH))) == []

    def test_mirror_detector_sees_a_head_only_change(self, mig, schema):
        bad = schema.replace(fn_block(schema, FNS[0]),
                             fn_block(schema, FNS[0]).replace("set search_path = public\n", "", 1), 1)
        assert fn_block(mig, FNS[0]) != fn_block(bad, FNS[0])

    def test_tables_come_before_the_freshness_function_in_schema(self, schema):
        at = schema.index("create or replace function get_data_freshness()")
        for t in ALL_TABLES:
            assert schema.index("create table if not exists " + t + " (") < at


class TestHeadsAndReturns:
    @pytest.mark.parametrize("name", FNS)
    def test_public_head(self, mig, name):
        lines = {ln.strip() for ln in head_of(fn_block(mig, name)).splitlines()}
        for w in ("language sql", "stable", "security definer", "set search_path = public"):
            assert w in lines, (name, w)

    @pytest.mark.parametrize("name", API_FNS)
    def test_api_head_and_pass_through(self, mig, name):
        block = fn_block(mig, name)
        lines = {ln.strip() for ln in head_of(block).splitlines()}
        assert {"language sql", "stable", "security definer", "set search_path = ''"} <= lines
        assert "$$ select * from public.{}(p_pnu) $$;".format(name[4:]) in block

    @pytest.mark.parametrize("name,want", [(FNS[0], SALES_RETURNS), (API_FNS[0], SALES_RETURNS),
                                           (FNS[1], POP_RETURNS), (API_FNS[1], POP_RETURNS)])
    def test_returned_columns(self, mig, name, want):
        m = re.search(r"(?is)returns\s+table\s*\((.*?)\)\s*language", fn_block(mig, name))
        assert tuple(ln.split()[0] for ln in m.group(1).splitlines() if ln.strip()) == want

    def test_one_signature_per_name(self, mig, schema):
        for name in FNS + API_FNS:
            for sql in (mig, schema):
                assert len(re.findall(r"(?im)^\s*create\s+(?:or\s+replace\s+)?function\s+" + re.escape(name)
                                      + r"\s*\(", statements(sql))) == 1, name

    def test_pnu_cast(self, mig):
        for f in FNS:
            body = body_of(fn_block(mig, f))
            assert "p.pnu = p_pnu::char(19)" in body
            assert re.search(r"\bp\.pnu\s*=\s*p_pnu\s*(?:\)|and|$)", body) is None


class TestSharedWithOpenclose:
    """상권 찾기·빈 상태·창·차례는 list_district_openclose 글 그대로 — 갈리면 카드끼리 다른 상권을 말한다."""

    def test_sales_shares_me_hit_head_and_window(self, schema):
        ref = body_of(fn_block(schema, OPENCLOSE))
        assert shared_cte_problems(body_of(fn_block(schema, FNS[0])), ref, table="district_sales") == []

    def test_pop_shares_me_hit_head(self, schema):
        ref = body_of(fn_block(schema, OPENCLOSE))
        assert shared_cte_problems(body_of(fn_block(schema, FNS[1])), ref) == []

    @pytest.mark.parametrize("old,new", [
        ("st_contains(d.geom, me.geom)", "st_contains(me.geom, d.geom)"),                # 변형: 인자 순서
        ("then 'no_coord'\n             when left(p_pnu::char(19), 2) <> '11' then 'not_seoul'",
         "then 'no_coord'\n             when left(p_pnu::char(19), 2) <> '30' then 'not_seoul'"),
        ("where w.n < c.n_quarters and w.quarter is not null", "where w.n <= c.n_quarters and w.quarter is not null"),
    ])
    def test_detector_catches_variants(self, schema, old, new):
        body = body_of(fn_block(schema, FNS[0]))
        assert old in body, "전제: 그 글자가 지금 판에 있다"
        ref = body_of(fn_block(schema, OPENCLOSE))
        assert shared_cte_problems(body.replace(old, new, 1), ref, table="district_sales")

    @pytest.mark.parametrize("name", FNS)
    def test_narrow_district_first(self, schema, name):
        body = "\n".join(code_lines(body_of(fn_block(schema, name))))
        assert body.rstrip().endswith("order by ro.sort_area asc, ro.district_id;")
        assert "h.area_m2" in body

    def test_constants_written_once(self, schema):
        body = body_of(fn_block(schema, FNS[0]))
        assert "select 8 as n_quarters, 5 as n_top, 100 as n_industries" in body
        assert body.count("r.rn <= c.n_top") == 1 and body.count("r.rn > c.n_top") == 1
        assert body.count("r.rn <= c.n_industries") == 1
        assert "order by o.thsmon_selng_amt desc, o.svc_induty_cd" in body


class TestPermissions:
    def test_only_the_api_twins_are_granted(self, mig, schema):
        assert sorted(grant_targets(mig)) == sorted(API_FNS)
        assert sorted(t for t in grant_targets(schema) if t.endswith(FNS)) == sorted(API_FNS)

    @pytest.mark.parametrize("bad", [
        "grant execute on function list_district_sales(text) to anon;",
        "  GRANT ALL\n  ON FUNCTION public.List_District_Pop ( text ) TO authenticated;",
    ])
    def test_grant_detector_catches_the_public_original(self, mig, bad):
        assert [t for t in grant_targets(mig + "\n" + bad + "\n") if not t.startswith("api.")]

    @pytest.mark.parametrize("name", FNS + API_FNS)
    def test_every_function_is_revoked_with_anon_named(self, mig, schema, name):
        for sql in (mig, schema):
            assert re.search(r"(?m)^revoke all on function " + re.escape(name)
                             + r"\(text\) from public, anon, authenticated;", statements(sql)), name

    @pytest.mark.parametrize("name", ALL_TABLES)
    def test_tables_are_closed(self, mig, schema, name):
        for sql in (mig, schema):
            block = statements(table_block(sql, name))
            assert "alter table {} enable row level security;".format(name) in block
            assert "revoke all on {} from public, anon, authenticated;".format(name) in block
            assert not re.search(r"(?is)\bgrant\b[^;]*\bon\s+(?:table\s+)?(?:public\.)?" + name + r"\b",
                                 statements(sql))

    def test_post_load_allowlist(self):
        for f in API_FNS:
            assert f in post_load.ANON_CALLABLE_ALLOWLIST
        for f in FNS:
            assert f not in post_load.ANON_CALLABLE_ALLOWLIST and "public." + f not in post_load.ANON_CALLABLE_ALLOWLIST
        for t in ALL_TABLES:
            assert t not in post_load.ANON_READABLE_ALLOWLIST
        assert len(post_load.ANON_READABLE_ALLOWLIST) + len(post_load.ANON_CALLABLE_ALLOWLIST) == 38
        assert set(TABLES) <= set(post_load.ANALYZE_TABLES)


class TestTablesShape:
    @pytest.mark.parametrize("name,pk", [
        ("district_sales", "primary key (quarter, district_id, svc_induty_cd)"),
        ("district_pop_flow", "primary key (quarter, district_id)"),
        ("district_pop_resident", "primary key (quarter, district_id)"),
        ("district_pop_worker", "primary key (quarter, district_id)"),
    ])
    def test_pk_quarter_fk_and_index(self, mig, name, pk):
        block = table_block(mig, name)
        assert pk in block and "references district(district_id)" in block
        assert re.search(r"(?m)^\s+quarter\s+char\(5\) not null,", block)
        assert "create index if not exists idx_{0}_district on {0} (district_id, quarter);".format(name) in block

    def test_release_table(self, mig):
        block = table_block(mig, RELEASE)
        assert re.search(r"(?m)^\s+tbl\s+text\s+primary key,", block)
        assert "check (value_quarter <= max_quarter)" in block
        assert re.search(r"(?m)^\s+loaded_at\s+timestamptz not null default now\(\),", block)

    def test_no_dropped_labels_kept(self, mig):
        """상권 구분·이름은 싣지 않는다(district 표에 있다 — 0033 과 같다)."""
        for t in TABLES:
            block = table_block(mig, t)
            for c in ("trdar_se_cd", "trdar_se_cd_nm", "trdar_cd_nm"):
                assert not re.search(r"(?m)^\s+" + c + r"\s", block), (t, c)


class TestFreshness:
    def test_new_block_is_the_old_block_plus_the_changes(self, mig):
        assert fresh_derived_problems(fresh_block(mig), fresh_block(read(PREV_FRESH))) == []

    @pytest.mark.parametrize("old,new", [
        ("           'none',\n           '연 1회 (서울시 공지)", "           'seoul_openclose',\n           '연 1회 (서울시 공지)"),
        ("           '월 1회'\n", "           '월 2회'\n"),
        ("열넷 갈래", "열네 갈래"),
    ])
    def test_detector_catches_variants(self, mig, old, new):
        block = fresh_block(mig)
        assert old in block
        assert fresh_derived_problems(block.replace(old, new, 1), fresh_block(read(PREV_FRESH)))

    def test_fourteen_rows_and_no_new_rule_kind(self, mig):
        block = fresh_block(mig)
        body = "\n".join(code_lines(body_of(block)))
        assert body.count("union all") == 13
        for n in (13, 14, 15):
            assert re.search(r"select {}, '".format(n), body)
        assert rule_kinds(block) == rule_kinds(fresh_block(read(PREV_FRESH)))

    def test_row_rules(self, mig):
        body = "\n".join(code_lines(body_of(fresh_block(mig))))
        assert re.search(r"select 13, '상권 추정매출 \(서울시\)', '분기',\n\s+\(select max\(t\.quarter\)::text from "
                         r"district_sales t\),\n\s+'seoul_openclose',", body)
        assert re.search(r"select 14, '상권 길단위인구 \(서울시\)', '분기',\n\s+\(select max\(t\.quarter\)::text from "
                         r"district_pop_flow t\),\n\s+'seoul_openclose',", body)
        m = re.search(r"select 15, '상권 상주·직장인구 \(서울시\)', '값이 바뀐 분기',(.*?)'none',\n", body, re.S)
        assert m and "seoul_trdar_release a, seoul_trdar_release b" in m.group(1)

    def test_api_twin_is_not_recreated(self, mig):
        assert not re.search(r"(?im)^\s*create\s+(?:or\s+replace\s+)?function\s+api\.get_data_freshness",
                             statements(mig))

    def test_hint_keys_are_the_server_labels(self, schema):
        for src in ("상권 추정매출 (서울시)", "상권 길단위인구 (서울시)"):
            assert src in cdf.SOURCE_HINTS and "'{}'".format(src) in schema
        assert "상권 상주·직장인구 (서울시)" not in cdf.SOURCE_HINTS


class TestMigrationShape:
    def test_settings_before_begin_and_notify_after_commit(self, mig):
        code = statements(mig)
        begin = re.search(r"(?m)^begin;", code).start()
        commit = re.search(r"(?m)^commit;", code).start()
        assert code.index("set lock_timeout = '2s';") < begin < commit < code.index("notify pgrst, 'reload schema';")
        assert len(re.findall(r"(?m)^begin;", code)) == 1 and len(re.findall(r"(?m)^commit;", code)) == 1
        for stmt in re.finditer(r"(?im)^(create|drop|alter|insert|revoke|grant|comment)\b", code):
            assert begin < stmt.start() < commit, "begin/commit 밖의 문장: " + stmt.group(0)

    def test_only_new_objects_and_the_freshness_function(self, mig):
        code = statements(mig)
        assert not re.search(r"(?im)^\s*drop\s", code)
        alters = re.findall(r"(?im)^alter\s+table\s+(\w+)\s+(.*);", code)
        assert alters == [(t, "enable row level security") for t in ALL_TABLES]
        made = re.findall(r"(?im)^create\s+(?:or\s+replace\s+)?(table|function)\s+(?:if\s+not\s+exists\s+)?([\w.]+)",
                          code)
        assert made == ([("table", t) for t in ALL_TABLES]
                        + [("function", FNS[0]), ("function", API_FNS[0]),
                           ("function", FNS[1]), ("function", API_FNS[1]), ("function", "get_data_freshness")])

    def test_rollback_paragraph_is_written(self, mig):
        for s in ("되돌리기", "2026-10-29a_daejeon_dong_closure.sql", "drop function api.list_district_sales(text)",
                  "drop table seoul_trdar_release", "36 → 34"):
            assert s in mig, s

    def test_no_banned_words(self, mig):
        for w in ("적정가격", "적정가", "감정가", "평가액", "가치평가"):
            assert w not in mig


# ── ② 실행 가드 (로컬 PostgreSQL 이 있을 때만) ──────────────────────────────

SHIM = """
create role anon;
create role authenticated;
create schema api;
create table parcel (pnu char(19) primary key, geom text, land_price_year smallint, updated_at timestamptz);
create table district (district_id text primary key, district_nm text, district_type text,
                       sigungu_code char(5), geom text, area_m2 numeric(14,2), computed_at timestamptz);
create function st_contains(poly text, pt text) returns boolean language sql immutable
  as 'select position(''|'' || pt || ''|'' in poly) > 0';
-- get_data_freshness 가 읽는 나머지 표 — 그 함수가 만들어지고 돌 만큼만.
create table snapshot_release (published_ym text);
create table transaction (contract_ym text);
create table ledger_release (release_ym text);
create table lh_notice (collected_at timestamptz);
create table arch_permit (loaded_ym text);
create table nts_base_price (notice_date date);
create table rent_stat (quarter char(6));
create table district_openclose (quarter text);
create table daejeon_closure_release (received_on date);
"""

SEOUL_A = "1168010100100010000"    # 좁은 상권 D1 과 넓은 상권 D2 둘 다
SEOUL_OUT = "1168010100100020000"
SEOUL_NOGEOM = "1168010100100030000"
DJ = "3017010100100010000"
SEOUL_B = "1168010100100040000"    # 상권 D4(자료 없음)
SEOUL_C = "1168010100100050000"    # 상권 D5(상주가 옛 분기 20231 에서 끊김 · 길단위는 있음 — 보완 1 F1)

FIXTURE = """
insert into parcel (pnu, geom) values ('{sa}', 'PA'), ('{so}', 'PO'), ('{sn}', null), ('{dj}', 'PD'), ('{sb}', 'PB'),
  ('{sc}', 'PC');
insert into district values
  ('D1', '좁은 상권', '골목상권', '11680', '|PA|', 1000),
  ('D2', '넓은 상권', '발달상권', '11680', '|PA|PX|', 9000),
  ('DJ1', '대전 상권', '발달상권', '30170', '|PD|', 500),
  ('D4', '자료 없는 상권', '골목상권', '11680', '|PB|', 100),
  ('D5', '옛 분기에서 끊긴 상권', '골목상권', '11680', '|PC|', 300);
""".format(sa=SEOUL_A, so=SEOUL_OUT, sn=SEOUL_NOGEOM, dj=DJ, sb=SEOUL_B, sc=SEOUL_C)

SALES_COLS = None   # 첫 호출 때 마이그에서 읽는다


def _sales_insert(cur, quarter, district, cd, amt, co, mdwk=0, wkend=0):
    cur.execute("insert into district_sales (quarter, district_id, svc_induty_cd, svc_induty_cd_nm, "
                "thsmon_selng_amt, thsmon_selng_co, mdwk_selng_amt, wkend_selng_amt) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s)", (quarter, district, cd, "업종" + cd, amt, co, mdwk, wkend))


def _fill(cur):
    cur.execute(FIXTURE)
    # D1: 20261·20262 각 7업종(상위 5 + 그 밖 2) · D2: 20262 한 업종 · D4: 없음
    for q, bump in (("20261", 0), ("20262", 1000)):
        for i in range(7):
            _sales_insert(cur, q, "D1", "CS10000{}".format(i), 10_000_000_000 - i * 1_000_000_000 + bump, 100 + i,
                          mdwk=7, wkend=3)
    _sales_insert(cur, "20262", "D2", "CS200001", 5, 1)
    # 인구: D1 은 길단위 두 분기 + 상주 · 직장 없음 / D2 는 직장만 / D4 는 셋 다 없음
    for q, tot in (("20261", 100), ("20262", 200)):
        cur.execute("insert into district_pop_flow (quarter, district_id, tot_flpop_co, mon_flpop_co) "
                    "values (%s, 'D1', %s, 30)", (q, tot))
    cur.execute("insert into district_pop_resident (quarter, district_id, tot_repop_co, tot_hshld_co, "
                "non_apt_hshld_co) values ('20262', 'D1', 1269, 882, 882)")
    cur.execute("insert into district_pop_worker (quarter, district_id, tot_wrc_popltn_co) values ('20262', 'D2', 55)")
    # D5: 길단위 20261 만 · 상주는 20231 에서 끊김(10-31 raw 실측 꼴 — 상주 4곳 · 직장 2곳)
    cur.execute("insert into district_pop_flow (quarter, district_id, tot_flpop_co) values ('20261', 'D5', 70)")
    cur.execute("insert into district_pop_resident (quarter, district_id, tot_repop_co) values ('20231', 'D5', 999)")
    cur.execute("insert into seoul_trdar_release (tbl, max_quarter, value_quarter) values "
                "('district_sales', '20262', '20262'), ('district_pop_flow', '20262', '20262'), "
                "('district_pop_resident', '20262', '20234'), ('district_pop_worker', '20262', '20244')")


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
    """흉내 판을 새로 깔고 마이그 파일을 **통째로** 돌린 뒤 가짜 행을 넣는다."""
    cur = conn.cursor()
    cur.execute("drop schema if exists api cascade; drop schema if exists public cascade; create schema public;")
    cur.execute("drop role if exists anon; drop role if exists authenticated;")
    cur.execute(SHIM)
    cur.execute(migration_sql or read(MIGRATION))
    if fill:
        _fill(cur)
    return cur


def _sales(cur, pnu):
    cur.execute("select {} from api.list_district_sales(%s)".format(", ".join(SALES_RETURNS)), (pnu,))
    return [dict(zip(SALES_RETURNS, r)) for r in cur.fetchall()]


def _pop(cur, pnu):
    cur.execute("select {} from api.list_district_pop(%s)".format(", ".join(POP_RETURNS)), (pnu,))
    return [dict(zip(POP_RETURNS, r)) for r in cur.fetchall()]


@pytest.fixture(scope="module")
def cur(pg):
    return _fresh(pg)


class TestRealRunSales:
    def test_narrow_first_and_window(self, cur):
        rows = _sales(cur, SEOUL_A)
        assert [(r["status"], r["district_id"]) for r in rows] == [("ok", "D1"), ("ok", "D2")]
        assert all(r["window_quarters"] == ["20262", "20261"] for r in rows)
        assert rows[0]["latest_quarter"] == "20262" and rows[1]["latest_quarter"] == "20262"

    def test_trend_is_the_sum_of_all_industries(self, cur):
        d1 = _sales(cur, SEOUL_A)[0]
        want = {q: (sum(10_000_000_000 - i * 1_000_000_000 + b for i in range(7)), sum(100 + i for i in range(7)))
                for q, b in (("20262", 1000), ("20261", 0))}
        assert [(t["quarter"], t["amt"], t["co"]) for t in d1["trend"]] == \
            [("20262",) + want["20262"], ("20261",) + want["20261"]]

    def test_top_five_rest_and_all_industries(self, cur):
        d1 = _sales(cur, SEOUL_A)[0]
        assert [t["cd"] for t in d1["top"]] == ["CS10000{}".format(i) for i in range(5)]
        assert set(d1["top"][0]) == {"cd", "nm", "amt", "co", "mdwk_amt", "wkend_amt"}
        assert (d1["top"][0]["mdwk_amt"], d1["top"][0]["wkend_amt"]) == (7, 3)
        assert d1["rest_cnt"] == 2
        assert d1["rest_amt"] == sum(10_000_000_000 - i * 1_000_000_000 + 1000 for i in (5, 6))
        assert d1["rest_co"] == 105 + 106
        assert [i["cd"] for i in d1["industries"]] == ["CS10000{}".format(i) for i in range(7)]
        assert set(d1["industries"][0]) == {"cd", "nm", "amt", "co"}

    def test_no_rest_is_zero_not_null(self, cur):
        d2 = _sales(cur, SEOUL_A)[1]
        assert (d2["rest_cnt"], d2["rest_amt"], d2["rest_co"]) == (0, 0, 0)

    @pytest.mark.parametrize("pnu,status", [(SEOUL_NOGEOM, "no_coord"), (DJ, "not_seoul"),
                                            (SEOUL_OUT, "outside_seoul_district")])
    def test_building_level_states(self, cur, pnu, status):
        rows = _sales(cur, pnu)
        assert [r["status"] for r in rows] == [status]
        assert all(rows[0][k] is None for k in SALES_RETURNS if k not in ("status", "window_quarters"))

    def test_no_data_row(self, cur):
        rows = _sales(cur, SEOUL_B)
        assert [(r["status"], r["district_id"]) for r in rows] == [("no_data", "D4")]
        assert all(rows[0][k] is None for k in ("latest_quarter", "trend", "top", "rest_cnt", "rest_amt",
                                                  "rest_co", "industries"))


class TestRealRunPop:
    def test_flow_latest_resident_and_missing_worker(self, cur):
        d1 = _pop(cur, SEOUL_A)[0]
        assert (d1["status"], d1["district_id"], d1["flow_quarter"]) == ("ok", "D1", "20262")
        assert d1["flow"]["tot"] == 200 and d1["flow"]["mon"] == 30 and len(d1["flow"]) == 22
        assert d1["resident_value_quarter"] == "20234" and d1["resident"]["tot"] == 1269
        assert d1["resident"]["non_apt_hshld"] == 882 and len(d1["resident"]) == 24
        assert d1["worker"] is None and d1["worker_value_quarter"] is None
        assert (d1["flow_table_quarter"], d1["resident_last_quarter"], d1["worker_last_quarter"]) == \
            ("20262", "20262", None)

    def test_only_worker_is_still_ok(self, cur):
        d2 = _pop(cur, SEOUL_A)[1]
        assert (d2["status"], d2["flow"], d2["resident"]) == ("ok", None, None)
        assert d2["worker_value_quarter"] == "20244" and d2["worker"]["tot"] == 55 and len(d2["worker"]) == 21
        assert d2["flow_table_quarter"] == "20262" and d2["flow_quarter"] is None     # 표 전체 최신은 늘 싣는다

    def test_district_cut_at_an_old_quarter_gives_no_old_value(self, cur):
        """F1 — 상주가 20231 에서 끊긴 상권: 옛 값을 「2023년 기준」으로 내보내지 않고 그 칸 null · 마지막 분기는 따로."""
        d5 = _pop(cur, SEOUL_C)[0]
        assert (d5["status"], d5["district_id"]) == ("ok", "D5")                       # 길단위가 있으니 ok
        assert (d5["resident"], d5["resident_value_quarter"], d5["resident_last_quarter"]) == (None, None, "20231")
        assert (d5["flow_quarter"], d5["flow_table_quarter"]) == ("20261", "20262")    # 화면이 「20261 까지」를 쓸 수 있다

    def test_none_of_three_is_no_data(self, cur):
        assert [(r["status"], r["district_id"], r["flow"]) for r in _pop(cur, SEOUL_B)] == [("no_data", "D4", None)]

    @pytest.mark.parametrize("pnu,status", [(SEOUL_NOGEOM, "no_coord"), (DJ, "not_seoul"),
                                            (SEOUL_OUT, "outside_seoul_district")])
    def test_building_level_states(self, cur, pnu, status):
        assert [r["status"] for r in _pop(cur, pnu)] == [status]


class TestRealRunFreshness:
    def _rows(self, cur):
        cur.execute("select src, basis_kind, basis, next_expected, cadence from get_data_freshness()")
        rows = cur.fetchall()
        assert len(rows) == 14
        return {r[0]: r[1:] for r in rows}

    def test_sales_and_flow_rows_due_2026_10_31(self, cur):
        """20262 → 202606 + 5개월 − 하루 = 2026-10-31(개업·폐업 11번 줄과 같은 규칙·같은 날 · 지시서의 11-30 은 착오).

        ⓘ 「적재 당일 안 지남」은 같은 날까지만 — 20262 를 11월에 넣으면 그날부터 지났다(11번 줄과 같은 처지).
        """
        rows = self._rows(cur)
        for src in ("상권 추정매출 (서울시)", "상권 길단위인구 (서울시)"):
            kind, basis, nxt, _ = rows[src]
            assert (kind, basis) == ("분기", "20262")
            assert nxt == datetime.date(2026, 10, 31)                     # 예정일 null 아님
            assert not nxt < datetime.date(2026, 10, 31)                  # 같은 날(10-31) 적재면 안 지남
        assert rows["상권 개업·폐업 (서울시)"][2] is None or rows["상권 개업·폐업 (서울시)"][2] == nxt

    def test_people_row_text_and_no_date(self, cur):
        kind, basis, nxt, cadence = self._rows(cur)["상권 상주·직장인구 (서울시)"]
        assert (kind, basis, nxt) == ("값이 바뀐 분기", "상주 2023년 4분기, 직장 2024년 4분기", None)
        assert "불규칙" in cadence

    def test_empty_release_keeps_the_row(self, pg):
        c = _fresh(pg, fill=False)
        try:
            rows = self._rows(c)
            assert rows["상권 상주·직장인구 (서울시)"][1:3] == (None, None)
            assert rows["상권 추정매출 (서울시)"][1:3] == (None, None)
        finally:
            _fresh(pg)

    def test_mutation_row13_rule_none_loses_the_date(self, pg):
        """양성 대조 — 13 줄 규칙을 none 으로 바꾸면 예정일이 사라진다(위 날짜 단언이 빨강)."""
        sql = read(MIGRATION)
        old = "district_sales t),\n           'seoul_openclose',"
        assert sql.count(old) == 1
        c = _fresh(pg, sql.replace(old, "district_sales t),\n           'none',", 1))
        try:
            assert self._rows(c)["상권 추정매출 (서울시)"][2] is None
        finally:
            _fresh(pg)


class TestRealRunPrivilegesAndReplay:
    def test_privileges(self, cur):
        for t in ALL_TABLES:
            cur.execute("select has_table_privilege('anon', %s, 'select'), "
                        "(select relrowsecurity from pg_class where relname = %s)", (t, t))
            assert cur.fetchone() == (False, True), t
        for f in FNS:
            cur.execute("select has_function_privilege('anon', %s, 'execute'), "
                        "has_function_privilege('anon', %s, 'execute'), "
                        "has_function_privilege('authenticated', %s, 'execute')",
                        ("public.{}(text)".format(f), "api.{}(text)".format(f), "api.{}(text)".format(f)))
            assert cur.fetchone() == (False, True, True), f

    def test_twins_work_with_an_empty_search_path(self, cur):
        cur.execute("set search_path to ''")
        try:
            assert _sales(cur, SEOUL_A)[0]["rest_cnt"] == 2
            assert _pop(cur, SEOUL_A)[0]["flow_quarter"] == "20262"
        finally:
            cur.execute("reset search_path")

    def test_one_signature_per_name(self, cur):
        for f in FNS:
            cur.execute("select n.nspname, count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                        "where p.proname = %s group by 1 order by 1", (f,))
            assert cur.fetchall() == [("api", 1), ("public", 1)]

    def test_applying_twice_gives_the_same_answer(self, pg):
        c = _fresh(pg)
        try:
            before = (_sales(c, SEOUL_A), _pop(c, SEOUL_A))
            c.execute(read(MIGRATION))
            assert (_sales(c, SEOUL_A), _pop(c, SEOUL_A)) == before
        finally:
            _fresh(pg)

    def test_mutation_public_grant_opens_the_original(self, pg):
        """변이 — public 원본에도 grant 를 주면 anon 이 원본을 부를 수 있다(위 권한 단언이 빨강)."""
        sql = read(MIGRATION).replace(
            "grant execute on function api.list_district_sales(text) to anon, authenticated;",
            "grant execute on function api.list_district_sales(text) to anon, authenticated;\n"
            "grant execute on function list_district_sales(text) to anon;", 1)
        c = _fresh(pg, sql)
        try:
            c.execute("select has_function_privilege('anon', 'public.list_district_sales(text)', 'execute')")
            assert c.fetchone() == (True,)
        finally:
            _fresh(pg)
