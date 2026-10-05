# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-05b(서울 상권 개업·폐업 — 결정 0033 R1)의 불변식.

두 겹으로 본다.

  ① 글자 가드(언제나 돈다 · CI 포함)
     · 덩어리: `set lock_timeout` 이 begin **앞** · begin/commit · notify 는 commit 뒤
     · 표: 승인된 칸 13개 · 기본키 (quarter, district_id, svc_induty_cd) · 색인 (district_id, quarter) ·
       RLS · 만든 자리 revoke · 표에는 grant 0(공개키 읽기 금지)
     · 함수: 머리(`returns table`·`language sql`·`stable`·`security definer`·`set search_path`)와
       `comment` 가 정본(schema.sql)과 **글자 그대로** 같다(create or replace 는 머리를 덮어쓴다 —
       레포 CLAUDE.md ⛔ 세 번째 단락) · api 쌍둥이만 anon 에 열린다 · public 원본은 revoke
     · 셈 규칙: 비율의 분모는 **유사 업종 점포 수**(stor 아님) · 합산 단계에 유사 업종 점포 수 조건이
       없다(similr = 0 행도 분자에) · status 판정 순서 no_coord → not_seoul → outside_seoul_district
       — 탐지는 이 파일 안의 작은 함수이고, 가드와 양성 대조가 **같은 함수**를 지난다(2026-10-02 #190)
  ② 실행 가드(로컬 PostgreSQL 이 있을 때만 · CI 는 건너뛴다)
     PostGIS 없이 돌리려고 `geometry` 를 글자로, `st_contains` 를 "점 이름이 도형 글자에 들었나"로
     흉내 낸 빈 DB 를 임시 폴더에 띄우고, 마이그레이션의 **표·함수 문장 그대로**를 넣어 픽스처로
     부른다 — similr = 0 행 합산 · 표본 < 30 이면 비율 null · 최근 8분기 · 상위 10 + 그 밖 ·
     빈 상태 넷 · 좁은 상권 먼저. 변이(분모 stor · similr 조건 · status 순서)도 실제로 값이 바뀌는지 본다.
     ⚠️ 흉내 낸 st_contains 는 진짜 공간 판정이 아니다 — 공간 술어 자체는 list_building_districts 와
        같은 글자인지(①)로만 지킨다. 라이브 실행 확인은 메인이 dbx.py 로 한다.

ⓘ 도우미는 이 파일 안에서만 쓴다(시험 파일끼리 import 하지 않는 레포 관습).
"""

import os
import re
import shutil
import socket
import subprocess
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-05b_district_openclose.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
FN = "list_district_openclose"
DOLLAR = chr(36) * 2

TABLE_COLUMNS = (
    ("quarter", "char(5)"), ("district_id", "text"), ("svc_induty_cd", "text"),
    ("svc_induty_cd_nm", "text"), ("stor_co", "int"), ("similr_induty_stor_co", "int"),
    ("opbiz_rt", "numeric(6,2)"), ("opbiz_stor_co", "int"), ("clsbiz_rt", "numeric(6,2)"),
    ("clsbiz_stor_co", "int"), ("frc_stor_co", "int"), ("source_nm", "text"),
    ("loaded_at", "timestamptz"),
)
RETURN_COLUMNS = ("status", "district_id", "district_nm", "district_type", "latest_quarter",
                  "quarters", "industries", "other_industries", "window_quarters")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def statements(sql):
    """줄 전체가 `--` 주석인 줄을 걷는다(주석으로 죽인 문장을 '있다'고 보지 않게)."""
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


def strip_line_comments(body):
    return "\n".join(re.sub(r"--.*$", "", ln) for ln in body.splitlines())


@pytest.fixture(scope="module")
def mig():
    return read(MIGRATION)


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


def create_stmt(sql, name):
    """`create or replace function <name>(` 부터 그 `$$;` 까지 — 줄머리 고정(api. 와 안 섞이게)."""
    m = re.search(r"(?ms)^create\s+or\s+replace\s+function\s+" + re.escape(name) + r"\s*\(.*?"
                  + re.escape(DOLLAR) + r".*?" + re.escape(DOLLAR) + r"\s*;", sql)
    assert m, "{} 를 못 찾았습니다".format(name)
    return m.group(0)


def head_of(stmt):
    return stmt[: stmt.index(DOLLAR)]


def body_of(stmt):
    return stmt.split(DOLLAR)[1]


def comment_of(sql, name):
    m = re.search(r"(?ims)^comment\s+on\s+function\s+" + re.escape(name) + r"\s*\(\s*text\s*\)\s+is.*?;\s*$",
                  statements(sql))
    assert m, "{} 의 comment 를 못 찾았습니다".format(name)
    return m.group(0)


def table_stmt(sql):
    m = re.search(r"(?ms)^create table if not exists district_openclose \((.*?)\n\);", sql)
    assert m, "create table district_openclose 를 못 찾았습니다"
    return m.group(0)


# ── 탐지 함수(가드와 양성 대조가 같이 쓴다) ──────────────────────────────────


def rate_denominators(body):
    """`* 100.0 / <분모>` 의 분모 식들. 못 보는 것: 100.0 이 아닌 꼴(`* 100 /`)·나눗셈을 먼저 쓴 꼴."""
    return [d.strip() for d in re.findall(r"\*\s*100(?:\.0)?\s*/\s*([^,)\n]+?(?:\([^)]*\))?)\s*(?:,|\)|\n)",
                                          strip_line_comments(body))]


def denominator_problems(body):
    dens = rate_denominators(body)
    bad = []
    if len(dens) < 4:
        bad.append("비율 식을 {}개만 찾았습니다(4개여야 — 상권 합산 둘 + 그 밖 둘)".format(len(dens)))
    bad += ["분모가 유사 업종 점포 수가 아닙니다: {}".format(d) for d in dens
            if "similr" not in d or re.search(r"\bstor\b|stor_co\)", d.replace("similr_induty_stor_co", ""))]
    return bad


def sums_cte(body):
    m = re.search(r"(?is)\bsums\s+as\s*\((.*?)\n  \),", strip_line_comments(body))
    return m.group(1) if m else None


def sums_filter_problems(body):
    """합산 단계에 유사 업종 점포 수 조건(where·filter·having)이 있으면 문제.

    못 보는 것: 조건을 qs 단계나 조인 대상 하위쿼리로 옮긴 꼴 — 그건 실행 가드(②)가 값으로 본다.
    """
    s = sums_cte(body)
    if s is None:
        return ["sums 를 못 찾았습니다 — 판정기가 헛돕니다"]
    cond = re.split(r"(?i)\bselect\b", s, maxsplit=1)[-1]
    cond = cond[re.search(r"(?i)\bfrom\b", cond).end():]
    if re.search(r"(?i)similr", cond) or re.search(r"(?i)\bfilter\s*\(", s):
        return ["합산(sums)에 유사 업종 점포 수 조건이 있습니다 — similr = 0 인데 닫힌 가게가 분자에서 빠집니다"]
    return []


def status_order(body):
    """head 의 case 에서 상태 이름이 나오는 순서."""
    m = re.search(r"(?is)\bhead\s+as\s*\((.*?)\n  \),", strip_line_comments(body))
    return re.findall(r"then\s+'(\w+)'", m.group(1)) if m else []


# ── ① 글자 가드 ─────────────────────────────────────────────────────────────


class TestBlock:
    def test_lock_timeout_before_begin_and_notify_after_commit(self, mig):
        s = statements(mig)
        lock = re.search(r"(?m)^set lock_timeout = '\d+s';", s)
        begin = re.search(r"(?m)^begin;", s)
        commit = re.search(r"(?m)^commit;", s)
        notify = s.find("notify pgrst, 'reload schema';")
        assert lock and begin and commit and notify != -1
        assert lock.start() < begin.start() < commit.start() < notify
        assert len(re.findall(r"(?m)^begin;", s)) == 1 and len(re.findall(r"(?m)^commit;", s)) == 1

    def test_rollback_paragraph_is_written(self, mig):
        assert "되돌리기 = **새 마이그레이션 파일**" in mig
        assert "2026-10-01a" in mig and "drop table district_openclose" in mig


class TestTable:
    def test_columns_are_exactly_the_approved_ones(self, mig):
        t = table_stmt(mig)
        got = tuple(
            (ln.split()[0], ln.split()[1].rstrip(","))
            for ln in t.splitlines()[1:-1]
            if ln.strip() and not ln.strip().startswith(("--", "primary key")))
        assert got == TABLE_COLUMNS

    def test_primary_key_index_and_fk(self, mig):
        t = table_stmt(mig)
        assert "primary key (quarter, district_id, svc_induty_cd)" in t
        assert "references district(district_id)" in t
        assert re.search(r"(?m)^create index if not exists \w+ on district_openclose "
                         r"\(district_id, quarter\);", statements(mig))

    def test_anon_cannot_read_the_table(self, mig, schema):
        for sql in (mig, schema):
            s = statements(sql)
            assert "alter table district_openclose enable row level security;" in s
            assert "revoke all on district_openclose from public, anon, authenticated;" in s
            assert not re.search(r"(?is)\bgrant\b[^;]*\bon\s+(?:table\s+)?(?:public\.)?district_openclose\b", s)

    def test_schema_has_the_same_table_text(self, mig, schema):
        assert table_stmt(mig) == table_stmt(schema)


class TestFunctionHeadAndComment:
    @pytest.mark.parametrize("name", [FN, "api." + FN, "get_data_freshness"])
    def test_head_matches_the_schema(self, mig, schema, name):
        """⛔ 머리를 베끼다 한 줄(search_path·security definer)이 빠지면 라이브만 조용히 다르다."""
        assert head_of(create_stmt(mig, name)) == head_of(create_stmt(schema, name))

    @pytest.mark.parametrize("name", [FN, "api." + FN])
    def test_body_matches_the_schema(self, mig, schema, name):
        assert body_of(create_stmt(mig, name)) == body_of(create_stmt(schema, name))

    def test_comment_matches_the_schema(self, mig, schema):
        assert comment_of(mig, FN) == comment_of(schema, FN)

    def test_head_properties(self, mig):
        h = head_of(create_stmt(mig, FN))
        assert "security definer" in h and "set search_path = public" in h
        assert re.search(r"(?m)^stable\s*$", h) and "language sql" in h
        api = head_of(create_stmt(mig, "api." + FN))
        assert "set search_path = ''" in api and "security definer" in api

    def test_returned_columns_are_the_same_in_both(self, mig):
        for name in (FN, "api." + FN):
            m = re.search(r"(?is)returns\s+table\s*\((.*?)\)\s*language", create_stmt(mig, name))
            got = tuple(ln.split()[0] for ln in m.group(1).splitlines() if ln.strip())
            assert got == RETURN_COLUMNS, name

    def test_api_twin_passes_the_argument_through(self, mig):
        assert body_of(create_stmt(mig, "api." + FN)).strip() == \
            "select * from public.list_district_openclose(p_pnu)"


def grant_targets(sql):
    """`grant … on function <이름>(` 의 대상(소문자) — 들여쓰기·grant all 까지. 회수(revoke)는 안 센다."""
    found = []
    for stmt in re.findall(r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*?\bon\s+function\b([^;]*)",
                           statements(sql)):
        found += re.findall(r"(?i)(?<![\w.])((?:\w+\.)?" + FN + r")\s*\(", stmt)
    return [t.lower() for t in found]


class TestPermissions:
    def test_only_the_api_twin_is_granted(self, mig, schema):
        for sql in (mig, schema):
            assert grant_targets(sql) == ["api." + FN]
            assert "grant execute on function api.list_district_openclose(text) to anon, authenticated;" in sql

    def test_public_original_is_revoked(self, mig, schema):
        for sql in (mig, schema):
            assert "revoke all on function list_district_openclose(text) from public, anon, authenticated;" \
                in statements(sql)

    @pytest.mark.parametrize("bad", [
        "grant execute on function list_district_openclose(text) to anon;",
        "  grant all on function public.list_district_openclose(text) to anon;",
    ])
    def test_grant_detector_catches_the_public_original(self, bad):
        got = grant_targets("grant execute on function api.list_district_openclose(text) to anon;\n" + bad)
        assert [t for t in got if t != "api." + FN], got

    def test_mutation_removing_api_grant_is_noticed(self, mig):
        broken = mig.replace(
            "grant execute on function api.list_district_openclose(text) to anon, authenticated;", "", 1)
        assert grant_targets(broken) != ["api." + FN]


class TestCountingRules:
    def test_denominator_is_similr(self, mig):
        assert denominator_problems(body_of(create_stmt(mig, FN))) == []

    @pytest.mark.parametrize("old,new", [
        ("/ s.similr, 2)", "/ s.stor, 2)"),
        ("/ sum(r.similr_induty_stor_co), 2)", "/ sum(r.stor_co), 2)"),
    ])
    def test_mutation_stor_denominator_is_noticed(self, mig, old, new):
        body = body_of(create_stmt(mig, FN))
        assert old in body, "전제: 그 식이 본문에 있다"
        assert denominator_problems(body.replace(old, new, 1))

    def test_sums_has_no_similr_condition(self, mig):
        assert sums_filter_problems(body_of(create_stmt(mig, FN))) == []

    @pytest.mark.parametrize("cond", [
        "\n    where o.similr_induty_stor_co > 0",
        "\n      and o.similr_induty_stor_co <> 0",
    ])
    def test_mutation_dropping_similr_zero_rows_is_noticed(self, mig, cond):
        body = body_of(create_stmt(mig, FN))
        anchor = "and o.quarter = qs.quarter"
        assert anchor in body
        assert sums_filter_problems(body.replace(anchor, anchor + cond, 1))

    def test_status_order(self, mig):
        assert status_order(body_of(create_stmt(mig, FN))) == [
            "no_coord", "not_seoul", "outside_seoul_district"]

    def test_mutation_status_order_swap_is_noticed(self, mig):
        body = body_of(create_stmt(mig, FN))
        a = "when not exists (select 1 from me) then 'no_coord'"
        b = "when left(p_pnu::char(19), 2) <> '11' then 'not_seoul'"
        assert a in body and b in body
        swapped = body.replace(a, "@@A@@").replace(b, a).replace("@@A@@", b)
        assert status_order(swapped) != ["no_coord", "not_seoul", "outside_seoul_district"]

    def test_min_sample_is_written_once(self, mig):
        body = strip_line_comments(body_of(create_stmt(mig, FN)))
        assert len(re.findall(r"\b30\b", body)) == 1
        assert body.count("min_similr") >= 4


# ── 실행 가드(②)가 CI 에서 건너뛰어도 남는 글자 단언 넷 (2026-10-05 검사관 🟡1) ─────────
# 아래 넷은 원래 로컬 PostgreSQL 실행 시험만 지키던 성질이다 — CI 에는 그 시험이 없으므로
# 글자로도 못 박는다. 탐지 함수는 가드와 양성 대조(변이)가 같이 쓴다.


def window_problems(body):
    """창 크기 8 은 const 에 한 번만 · 재귀가 그 상수로 멈춘다 · 표 전체 max 로 시작한다."""
    b = strip_line_comments(body)
    bad = []
    if len(re.findall(r"\b8\b", b)) != 1 or "8 as n_quarters" not in b:
        bad.append("창 크기 8 이 const 의 `8 as n_quarters` 한 곳에만 있지 않습니다")
    if not re.search(r"where\s+w\.n\s*<\s*c\.n_quarters\b", b):
        bad.append("재귀가 `w.n < c.n_quarters` 로 멈추지 않습니다")
    if not re.search(r"select\s+max\(o\.quarter\),\s*1\s+from\s+district_openclose\s+o\s*\n", b):
        bad.append("창이 표 전체의 max(quarter) 로 시작하지 않습니다(상권별 창으로 되돌아갔나)")
    if not re.search(r"where\s+o\.quarter\s*<(?!=)\s*w\.quarter\b", b):
        bad.append("다음 분기를 `o.quarter < w.quarter`(등호 없이)로 짚지 않습니다 — <= 면 같은 분기를 되풀이한다")
    if not re.search(r"\bw\.n\s*\+\s*1\b", b):
        bad.append("재귀가 한 칸씩(`w.n + 1`) 세지 않습니다")
    if not re.search(r"<\s*c\.n_quarters\s+and\b", b):
        bad.append("멈춤 조건이 `w.n < c.n_quarters and …` 꼴이 아닙니다(c.n_quarters + 1 같은 꼴 금지)")
    return bad


def top_ten_problems(body):
    b = strip_line_comments(body)
    bad = []
    if b.count("r.rn <= 10") != 1:
        bad.append("상위 10 줄 조건 `r.rn <= 10` 이 한 번이 아닙니다")
    if b.count("r.rn > 10") != 1:
        bad.append("'그 밖' 조건 `r.rn > 10` 이 한 번이 아닙니다")
    if len(re.findall(r"\br\.rn\s*(?:<=|<|>=|>|=)\s*\d+", b)) != 2:
        bad.append("rn 비교가 두 개(<= 10 · > 10)가 아닙니다")
    if not re.search(r"order\s+by\s+o\.similr_induty_stor_co\s+desc\s*,\s*o\.svc_induty_cd\)", b):
        bad.append("상위 10 순위가 유사 업종 점포 수 내림차순(`o.similr_induty_stor_co desc, o.svc_induty_cd`)이 아닙니다")
    return bad


def min_sample_comparisons(body):
    """`<식> <연산자> c.min_similr` · `<식> <연산자> max(c.min_similr)` 의 연산자 목록."""
    return re.findall(r"(<=|>=|<>|=|<|>)\s*(?:max\(\s*)?c\.min_similr\b", strip_line_comments(body))


def narrow_first_problems(body):
    b = strip_line_comments(body)
    bad = []
    if not re.search(r"order\s+by\s+ro\.sort_area\s+asc\s*,\s*ro\.district_id\s*;\s*$", b.rstrip()):
        bad.append("맨 끝 정렬이 `order by ro.sort_area asc, ro.district_id` 가 아닙니다")
    if "h.area_m2\n" not in b:
        bad.append("상권 줄의 sort_area 가 h.area_m2 가 아닙니다")
    return bad


class TestTextGuardsForCI:
    def test_window_is_table_wide_eight(self, mig):
        assert window_problems(body_of(create_stmt(mig, FN))) == []

    @pytest.mark.parametrize("old,new", [
        ("8 as n_quarters", "12 as n_quarters"),
        ("where w.n < c.n_quarters", "where w.n < 12"),
        ("select max(o.quarter), 1 from district_openclose o\n",
         "select max(o.quarter), 1 from district_openclose o where o.district_id = 'x'\n"),
        # 재검사관 변이 M1~M3 (2026-10-05)
        ("o.quarter < w.quarter", "o.quarter <= w.quarter"),
        ("w.n + 1", "w.n + 2"),
        ("w.n < c.n_quarters and", "w.n < c.n_quarters + 1 and"),
    ])
    def test_mutation_window_is_noticed(self, mig, old, new):
        body = body_of(create_stmt(mig, FN))
        assert old in body
        assert window_problems(body.replace(old, new, 1))

    def test_top_ten(self, mig):
        assert top_ten_problems(body_of(create_stmt(mig, FN))) == []

    @pytest.mark.parametrize("old,new", [
        ("r.rn <= 10", "r.rn <= 5"), ("r.rn > 10", "r.rn >= 10"), ("r.rn <= 10", "r.rn < 10"),
        # 재검사관 변이 M4 — 상위 10 을 작은 업종부터 고르게 뒤집음
        ("order by o.similr_induty_stor_co desc, o.svc_induty_cd)",
         "order by o.similr_induty_stor_co asc, o.svc_induty_cd)"),
    ])
    def test_mutation_top_ten_is_noticed(self, mig, old, new):
        body = body_of(create_stmt(mig, FN))
        assert old in body
        assert top_ten_problems(body.replace(old, new, 1))

    def test_min_sample_direction_is_at_least(self, mig):
        """표본 30 '이상'일 때만 비율 — 네 자리 전부 `>=` 여야 한다(방향이 뒤집히면 작은 표본만 비율이 뜬다)."""
        assert min_sample_comparisons(body_of(create_stmt(mig, FN))) == [">="] * 4

    @pytest.mark.parametrize("new", [">", "<", "<="])
    def test_mutation_min_sample_direction_is_noticed(self, mig, new):
        body = body_of(create_stmt(mig, FN))
        old = "s.similr >= c.min_similr"
        assert body.count(old) == 2
        assert min_sample_comparisons(body.replace(old, "s.similr {} c.min_similr".format(new), 1)) \
            != [">="] * 4

    def test_narrow_district_first(self, mig):
        assert narrow_first_problems(body_of(create_stmt(mig, FN))) == []

    @pytest.mark.parametrize("old,new", [
        ("order by ro.sort_area asc, ro.district_id;", "order by ro.sort_area desc, ro.district_id;"),
        ("order by ro.sort_area asc, ro.district_id;", "order by ro.district_id;"),
        ("           h.area_m2\n", "           0::numeric\n"),
    ])
    def test_mutation_order_is_noticed(self, mig, old, new):
        body = body_of(create_stmt(mig, FN))
        assert old in body
        assert narrow_first_problems(body.replace(old, new, 1))


# ── ② 실행 가드 (로컬 PostgreSQL 이 있을 때만) ──────────────────────────────

SHIM = """
create table parcel (pnu char(19) primary key, geom text, updated_at timestamptz);
create table district (district_id text primary key, district_nm text, district_type text,
                       sigungu_code char(5), geom text, area_m2 numeric(14,2), computed_at timestamptz);
-- get_data_freshness 가 읽는 나머지 표 — 그 함수가 만들어지고 돌 만큼만.
create table unit_business (snapshot_ym text);
create table transaction (contract_ym text);
create table building (updated_at timestamptz);
create table lh_notice (collected_at timestamptz);
create table arch_permit (loaded_ym text);
create table nts_base_price (notice_date date);
create table rent_stat (quarter char(6));
create table price_gate_sigungu (loaded_at timestamptz);
-- 흉내 낸 공간 판정: 점 이름이 도형 글자 안에 '|이름|' 꼴로 들어 있으면 담긴 것.
create function st_contains(poly text, pt text) returns boolean language sql immutable
  as 'select position(''|'' || pt || ''|'' in poly) > 0';
create schema api;
"""

SEOUL_A = "1168010100100010000"   # 좁은 상권 D1 과 넓은 상권 D2 둘 다에 든다
SEOUL_OUT = "1168010100100020000"  # 서울인데 상권 밖
SEOUL_NOGEOM = "1168010100100030000"
DJ = "3017010100100010000"         # 대전 — 대전 상권 안
DJ_NOGEOM = "3017010100100020000"
SEOUL_B = "1168010100100040000"    # 상권 D4(창 안 옛 분기만)·D5(창 밖 분기만)

FIXTURE = """
insert into parcel values ('{sa}', 'PA'), ('{so}', 'PO'), ('{sn}', null), ('{dj}', 'PD'), ('{djn}', null),
  ('{sb}', 'PB');
insert into district values
  ('D1', '좁은 상권', '골목상권', '11680', '|PA|', 1000),
  ('D2', '넓은 상권', '발달상권', '11680', '|PA|PX|', 9000),
  ('DJ1', '대전 상권', '발달상권', '30170', '|PD|', 500),
  ('D4', '최신 분기에서 빠진 상권', '골목상권', '11680', '|PB|', 100),
  ('D5', '창 밖 분기만 가진 상권', '골목상권', '11680', '|PB|', 200);
""".format(sa=SEOUL_A, so=SEOUL_OUT, sn=SEOUL_NOGEOM, dj=DJ, djn=DJ_NOGEOM, sb=SEOUL_B)


def _openclose_rows():
    """D1 에 9분기 × 업종 12개. 최신 분기(20262)의 CS000 업종은 similr = 0 인데 폐업 2."""
    rows = []
    quarters = ["20242", "20243", "20244", "20251", "20252", "20253", "20254", "20261", "20262"]
    for q in quarters:
        for i in range(12):
            similr = 0 if (q == "20262" and i == 0) else 20 - i
            stor, frc = (similr - 1, 1) if similr else (0, 0)
            opb, clo = (1, 2) if i in (0, 1) else (0, 0)
            rows.append((q, "D1", "CS{:03d}".format(i), "업종{}".format(i), stor, similr,
                         0 if similr == 0 else round(opb * 100.0 / similr), opb,
                         0 if similr == 0 else round(clo * 100.0 / similr), clo, frc))
    return rows


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


def _load(conn, fn_sql):
    """흉내 판 위에 마이그레이션의 표 문장 + 주어진 함수 문장을 넣고 픽스처를 채운다."""
    cur = conn.cursor()
    cur.execute("drop schema if exists public cascade; drop schema if exists api cascade; "
                "create schema public;")
    cur.execute(SHIM)
    cur.execute(table_stmt(read(MIGRATION)))
    cur.execute(fn_sql)
    cur.execute(FIXTURE)
    cur.executemany("insert into district_openclose (quarter, district_id, svc_induty_cd, "
                    "svc_induty_cd_nm, stor_co, similr_induty_stor_co, opbiz_rt, opbiz_stor_co, "
                    "clsbiz_rt, clsbiz_stor_co, frc_stor_co) values "
                    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", _openclose_rows())
    # 표본 < 30 상권: D2 에 한 분기 한 업종만(similr 5)
    cur.execute("insert into district_openclose values "
                "('20262','D2','CS900','작은업종',4,5,20,1,0,0,1,null,now())")
    # 표 전체 창(최근 8분기 = 20243~20262) 기준: D4 는 창 안 20261 에만 · D5 는 창 밖 20231 에만 행이 있다.
    cur.execute("insert into district_openclose values "
                "('20261','D4','CS100','업종',40,40,5,2,3,1,0,null,now()),"
                "('20231','D5','CS100','업종',40,40,5,2,3,1,0,null,now())")
    return cur


def _call(cur, pnu):
    cur.execute("select status, district_id, latest_quarter, quarters, industries, other_industries "
                "from list_district_openclose(%s)", (pnu,))
    return cur.fetchall()


@pytest.fixture(scope="module")
def cur(pg):
    return _load(pg, create_stmt(read(MIGRATION), FN))


class TestRealRun:
    def test_building_level_states(self, cur):
        assert [r[0] for r in _call(cur, SEOUL_NOGEOM)] == ["no_coord"]
        assert [r[0] for r in _call(cur, DJ_NOGEOM)] == ["no_coord"]      # 좌표가 먼저다
        assert [r[0] for r in _call(cur, DJ)] == ["not_seoul"]            # 대전 상권 안이어도
        assert [r[0] for r in _call(cur, SEOUL_OUT)] == ["outside_seoul_district"]
        assert [r[1] for r in _call(cur, SEOUL_NOGEOM)] == [None]

    def test_narrow_district_first_and_ok_rows(self, cur):
        rows = _call(cur, SEOUL_A)
        assert [(r[0], r[1]) for r in rows] == [("ok", "D1"), ("ok", "D2")]

    def test_latest_eight_quarters_newest_first(self, cur):
        d1 = _call(cur, SEOUL_A)[0]
        qs = [q["quarter"] for q in d1[3]]
        assert d1[2] == "20262"
        assert qs == ["20262", "20261", "20254", "20253", "20252", "20251", "20244", "20243"]

    def test_similr_zero_row_is_in_the_numerator(self, cur):
        """20262 의 CS000(similr 0 · 폐업 2)도 폐업 합에 든다 — 분모에는 0."""
        q = _call(cur, SEOUL_A)[0][3][0]
        similr = sum(20 - i for i in range(1, 12))       # CS000 은 0
        assert q["similr_induty_stor_co"] == similr
        assert q["clsbiz_stor_co"] == 4                   # CS000 2 + CS001 2
        assert float(q["clsbiz_rt"]) == round(4 * 100.0 / similr, 2)
        assert float(q["opbiz_rt"]) == round(2 * 100.0 / similr, 2)

    def test_small_sample_hides_rates_but_keeps_counts(self, cur):
        d2 = _call(cur, SEOUL_A)[1][3][0]
        assert d2["similr_induty_stor_co"] == 5 and d2["opbiz_stor_co"] == 1
        assert d2["opbiz_rt"] is None and d2["clsbiz_rt"] is None

    def test_top_ten_and_the_rest(self, cur):
        d1 = _call(cur, SEOUL_A)[0]
        assert len(d1[4]) == 10
        assert d1[4][0]["svc_induty_cd"] == "CS001"        # similr 19 가 맨 위(CS000 은 0)
        assert d1[5]["industry_count"] == 2
        # 업종 행의 비율은 공표값 그대로
        assert float(d1[4][0]["clsbiz_rt"]) == round(2 * 100.0 / 19)

    def test_no_data_when_the_table_has_nothing(self, pg):
        c = _load(pg, create_stmt(read(MIGRATION), FN))
        c.execute("delete from district_openclose where district_id = 'D2'")
        rows = _call(c, SEOUL_A)
        assert [(r[0], r[1], r[3]) for r in rows][1] == ("no_data", "D2", None)
        _load(pg, create_stmt(read(MIGRATION), FN))      # 다른 시험을 위해 되돌린다


class TestRealRunMutations:
    """변이가 실제로 값을 바꾸는가 — 위 실행 가드가 그 변이를 빨강으로 잡는다는 근거."""

    def _mutated(self, pg, old, new):
        fn = create_stmt(read(MIGRATION), FN)
        assert old in fn
        c = _load(pg, fn.replace(old, new, 1))
        out = _call(c, SEOUL_A), _call(c, DJ_NOGEOM)
        _load(pg, fn)
        return out

    def test_stor_denominator_changes_the_rate(self, pg):
        (rows, _) = self._mutated(pg, "then round(s.clsbiz * 100.0 / s.similr, 2) end",
                                  "then round(s.clsbiz * 100.0 / s.stor, 2) end")
        similr = sum(20 - i for i in range(1, 12))
        assert float(rows[0][3][0]["clsbiz_rt"]) != round(4 * 100.0 / similr, 2)

    def test_dropping_similr_zero_rows_changes_the_count(self, pg):
        (rows, _) = self._mutated(pg, "and o.quarter = qs.quarter",
                                  "and o.quarter = qs.quarter and o.similr_induty_stor_co > 0")
        assert rows[0][3][0]["clsbiz_stor_co"] == 2

    def test_status_order_swap_changes_the_answer(self, pg):
        (_, dj_nogeom) = self._mutated(
            pg, "when not exists (select 1 from me) then 'no_coord'\n"
                "             when left(p_pnu::char(19), 2) <> '11' then 'not_seoul'",
            "when left(p_pnu::char(19), 2) <> '11' then 'not_seoul'\n"
            "             when not exists (select 1 from me) then 'no_coord'")
        assert [r[0] for r in dj_nogeom] == ["not_seoul"]


class TestRealRunFreshness:
    """신선도 11번째 줄 — 마이그레이션의 get_data_freshness 를 그대로 만들어 돌린다."""

    BRANCH = ("             when r.rule_kind = 'seoul_openclose' and r.basis ~ '^\\d{4}[1-4]$'\n"
              "               then left(r.basis, 4) || lpad((right(r.basis, 1)::int * 3)::text, 2, '0')\n")

    def _rows(self, pg, fn_sql):
        c = _load(pg, create_stmt(read(MIGRATION), FN))
        c.execute(fn_sql)
        c.execute("insert into unit_business values ('202606'); insert into rent_stat values ('2026Q2');")
        c.execute("select src, basis, next_expected from get_data_freshness()")
        return c.fetchall()

    def test_eleven_rows_and_20262_is_due_2026_10_31(self, pg):
        rows = self._rows(pg, create_stmt(read(MIGRATION), "get_data_freshness"))
        assert len(rows) == 11
        seoul = [r for r in rows if r[0] == "상권 개업·폐업 (서울시)"]
        assert seoul and seoul[0][1] == "20262"
        assert str(seoul[0][2]) == "2026-10-31"
        # 같은 분기를 말하는 상권정보·부동산원 줄과 같은 날이다.
        assert {str(r[2]) for r in rows if r[1] in ("202606", "2026Q2", "20262")} == {"2026-10-31"}

    def test_mutation_without_third_branch_goes_silent(self, pg):
        fn = create_stmt(read(MIGRATION), "get_data_freshness")
        assert self.BRANCH in fn, "전제: 셋째 갈래가 그 모양으로 있다"
        rows = self._rows(pg, fn.replace(self.BRANCH, "", 1))
        seoul = [r for r in rows if r[0] == "상권 개업·폐업 (서울시)"]
        assert seoul[0][2] is None       # 에러 없이 '정해진 주기 없음' — 그래서 이 가드가 있다


class TestRealRunTableWideWindow:
    """🟡2 — '최근 8분기'는 상권별이 아니라 **표 전체** 기준 창이다."""

    def test_district_missing_the_newest_quarter_is_ok_with_its_own_latest(self, cur):
        rows = _call(cur, SEOUL_B)
        d4 = [r for r in rows if r[1] == "D4"][0]
        assert d4[0] == "ok"
        assert d4[2] == "20261"                       # 표 전체 최신(20262)이 아니라 그 상권의 최신
        assert [q["quarter"] for q in d4[3]] == ["20261"]   # 창 안 빠진 분기는 채우지 않는다

    def test_district_with_only_quarters_outside_the_window_is_no_data(self, cur):
        rows = _call(cur, SEOUL_B)
        assert [(r[0], r[1]) for r in rows] == [("ok", "D4"), ("no_data", "D5")]
        d5 = rows[1]
        assert d5[2] is None and d5[3] is None and d5[4] is None

    def test_window_is_shared_by_all_districts(self, cur):
        """D1 은 9분기를 가졌지만 창(표 전체 최신 8분기) 밖 20242 는 안 나온다."""
        qs = [q["quarter"] for q in _call(cur, SEOUL_A)[0][3]]
        assert "20242" not in qs and len(qs) == 8

    def test_window_quarters_is_the_window_on_every_row(self, pg):
        """분기 3개뿐인 표 → 창 길이 3 · 최신 → 옛 순 · 상권 줄과 건물 단위 줄 모두 같은 값."""
        c = _load(pg, create_stmt(read(MIGRATION), FN))
        try:
            c.execute("delete from district_openclose where quarter not in ('20262', '20261', '20254')")
            for pnu in (SEOUL_A, DJ, SEOUL_NOGEOM, SEOUL_OUT):
                c.execute("select window_quarters from list_district_openclose(%s)", (pnu,))
                got = [r[0] for r in c.fetchall()]
                assert got and all(w == ["20262", "20261", "20254"] for w in got), (pnu, got)
            c.execute("delete from district_openclose")
            c.execute("select window_quarters from list_district_openclose(%s)", (SEOUL_A,))
            assert {tuple(r[0]) for r in c.fetchall()} == {()}      # 빈 표 → 빈 배열
        finally:
            _load(pg, create_stmt(read(MIGRATION), FN))             # 다른 시험을 위해 되돌린다


def test_window_quarters_text(mig):
    """글자 단언 — 창 목록은 win 을 최신 → 옛 순으로 모아 빈 표면 빈 배열, 모든 줄에 cross join 으로 싣는다."""
    b = strip_line_comments(body_of(create_stmt(mig, FN)))
    assert re.search(r"coalesce\(jsonb_agg\(w\.quarter::text order by w\.quarter desc\)\s*\n\s*"
                     r"filter \(where w\.quarter is not null\), '\[\]'::jsonb\) as window_quarters\s*\n\s*"
                     r"from win w", b)
    assert re.search(r"wq\.window_quarters\s*\n\s*from rows_out ro cross join wq", b)
