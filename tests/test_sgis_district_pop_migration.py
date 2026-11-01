# -*- coding: utf-8 -*-
"""마이그레이션 *_sgis_district_pop.sql(대전 「상권 인구 (통계청 집계구)」 — 결정 0045 PR⑤)의 불변식.

두 겹으로 본다.

  ① 글자 가드(언제나 돈다 · CI 포함)
     · 정본(schema.sql) ↔ 마이그 **글자 대조**: 표 둘 덩어리 · 함수 둘(머리 security definer·search_path·stable 까지) ·
       comment · 신선도 함수 덩어리(머리·본문·comment·revoke)
     · 상권 찾기·status(me·hit·head) = list_district_pop 글 그대로(서울 → 대전 치환) — 변형 양성 대조
     · 신선도 = 가게 이력 판(2026-11-01a) + 정한 갈래(17번 줄 · sgis 규칙 · comment 다섯 곳)만 — 그 밖의 차이는 빨강
     · 사업체 수(est)는 함수가 안 내보낸다 · grant 는 api 쌍둥이에만 · public 원본 revoke · 표 둘 RLS·revoke · check
     · post_load 허용 총계 38 · ANALYZE_TABLES 둘 · 그물 6호 힌트 열쇠·화면 CARD_SOURCES.census_pop = 정본 자료 이름
     · 덩어리: lock_timeout 이 begin 앞 · begin/commit 하나 · notify 는 commit 뒤 · 새 객체만
  ② 실행 가드(로컬 PostgreSQL 이 있을 때만 · CI 는 건너뛴다 — 형제 시험과 같은 빈 DB 흉내 판)
     PostGIS 없이 `geometry` 를 글자로, `st_contains` 를 "점 이름이 도형 글자에 들었나"로 흉내 낸 빈 DB 에 **마이그 파일을
     통째로** 돌린 뒤 가짜 줄로 부른다 — 표지 없음 0줄 · status 넷 · 좁은 상권 먼저 · no_data · est 안 나감 ·
     신선도 16줄과 예정일(받은 날 + 12개월 · 날짜 단언 둘) · 권한 · 두 번 적용 · check · 변이 셋.
     ⚠️ 흉내 낸 st_contains 는 진짜 공간 판정이 아니다 — 공간 술어는 ①의 글자 대조로 지킨다.

ⓘ 파일 이름의 날짜는 적용 예정일이다(메인이 적용 날에 맞춰 바꿀 수 있다) — 이름 끝 `_sgis_district_pop.sql` 로 찾는다.
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
FOUND = sorted(glob.glob(os.path.join(MIGRATIONS, "*_sgis_district_pop.sql")))
PREV_FRESH = (sorted(glob.glob(os.path.join(MIGRATIONS, "*_store_history.sql")))
              or [os.path.join(MIGRATIONS, "(없음)_store_history.sql")])[-1]
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
CARD_TS = os.path.join(ROOT, "src", "lib", "dataFreshness.ts")

for _p in (os.path.join(ROOT, "scripts"), os.path.join(ROOT, "scripts", "collectors")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import check_data_freshness as cdf  # noqa: E402
import post_load  # noqa: E402

TABLES = ("district_census_pop", "sgis_census_release")
FN = "get_district_census_pop"
API_FN = "api." + FN
SIG = "(text)"
POP_FN = "list_district_pop"
SRC = "상권 인구 (통계청 집계구)"
RETURNS = ("status", "district_id", "district_nm", "district_type", "area_m2", "n_overlap", "n_full", "cover_pct",
           "pop", "pop_lo", "pop_hi", "hh", "hh_lo", "hh_hi", "emp", "emp_lo", "emp_hi",
           "received_on", "base_year", "bnd_base_date")

ROW17 = (
    "    union all\n"
    "    -- 2026-11-01b(결정 0045 PR⑤) — SGIS 집계구 통계를 대전 상권에 나눠 담은 결과표의 받은 날(표지 sgis_census_release).\n"
    "    --   사람이 SGIS 자료제공에서 연 1회 신청해 받는다 — 받은 날 + 12개월(규칙 'sgis'). 표지가 비면 basis null(화면 '자료 없음').\n"
    "    select 17, '상권 인구 (통계청 집계구)', '받은 날',\n"
    "           (select r.received_on::text from sgis_census_release r),\n"
    "           'sgis',\n"
    "           '연 1회 (사람이 SGIS 자료제공에서 신청해 받음)'\n"
)
OLD_LAST_ROW = "           '분기마다 (새 분기 점포 자료를 적재한 뒤 다시 굽는다)'\n"
RULE_END = ("           when n.rule_kind = 'daejeon_closure' and n.basis ~ '^\\d{4}-\\d{2}-\\d{2}$'\n"
            "             then (n.basis::date + interval '3 months')::date\n")
RULE17 = ("           -- SGIS 상권 인구: 받은 날 + 12개월(연 1회 사람이 신청해 받는다 — 2026-11-01b · 결정 0045 PR⑤).\n"
          "           --   'YYYY-MM-DD' 일 때만 — 모양이 다르면 ::date 가 터져 표가 통째로 사라진다.\n"
          "           when n.rule_kind = 'sgis' and n.basis ~ '^\\d{4}-\\d{2}-\\d{2}$'\n"
          "             then (n.basis::date + interval '12 months')::date\n")
FRESH_CHANGES = (
    (OLD_LAST_ROW + "  ),", OLD_LAST_ROW + ROW17 + "  ),"),
    (RULE_END, RULE_END + RULE17),
    ("열다섯 갈래 자료", "열여섯 갈래 자료"),
    ("(열다섯 표가 전부 anon", "(열여섯 표가 전부 anon"),
    ("집계 도장 열다섯 개뿐", "집계 도장 열여섯 개뿐"),
    ("기준값이 YYYY-MM-DD 일 때만). 서울 상권 추정매출·길단위인구는 '",
     "기준값이 YYYY-MM-DD 일 때만), SGIS 상권 인구는 받은 날 + 12개월(연 1회 · 같은 모양일 때만). '\n"
     "  '서울 상권 추정매출·길단위인구는 '"),
    ("· 가게 이력 2026-11-01a(결정 0045 PR④)';",
     "· 가게 이력 2026-11-01a(결정 0045 PR④) · SGIS 상권 인구 2026-11-01b(결정 0045 PR⑤)';"),
)
# list_district_pop(서울) → 이 함수(대전) 치환 — me·hit·head 는 이것만 다르다.
TO_DAEJEON = (("'11'", "'30'"), ("'not_seoul'", "'not_daejeon'"),
              ("'outside_seoul_district'", "'outside_daejeon_district'"))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


@pytest.fixture(scope="module")
def mig():
    assert len(FOUND) == 1, "*_sgis_district_pop.sql 마이그가 정확히 하나여야 합니다: {}".format(FOUND)
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
    m = re.search(r"(?ms)^comment\s+on\s+function\s+" + FN + r"\s*\(\s*text\s*\)\s+is.*?';\s*$", sql)
    assert m, "comment 를 못 찾았습니다"
    return m.group(0)


def table_block(sql, name):
    """`create table if not exists <name> (` 부터 그 표의 revoke 줄까지(comment·RLS 포함)."""
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
    """주석(`--` 뒤)을 걷고 빈 줄을 뺀 줄 목록."""
    out = []
    for ln in text.splitlines():
        ln = re.sub(r"--.*$", "", ln).rstrip()
        if ln.strip():
            out.append(ln)
    return out


def cte(body, name):
    """본문에서 `<name> as (` … `\\n  ),` 덩어리(주석 밖 줄 목록). 못 찾으면 None."""
    m = re.search(r"(?s)\b" + re.escape(name) + r"\s+as\s*\((.*?)\n  \),", body)
    return code_lines(m.group(1)) if m else None


def shared_cte_problems(body, ref_body, names=("me", "hit", "head")):
    """body 의 CTE 들이 기준(list_district_pop) 본문을 대전으로 치환한 것과 주석 밖 글자가 같은가 — 문제 문장 목록.

    못 보는 것: CTE 이름을 바꾼 꼴(못 찾음으로 걸린다) · 치환 글자('11' 등)가 기준에 새로 생긴 다른 뜻의 자리.
    """
    for a, b in TO_DAEJEON:
        ref_body = ref_body.replace(a, b)
    bad = []
    for n in names:
        a, b = cte(body, n), cte(ref_body, n)
        if a is None or b is None or a != b:
            bad.append("{} 가 list_district_pop(대전 치환)과 다릅니다".format(n))
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
        bad.append("2026-11-01a 판 + 정한 갈래와 글자가 다릅니다")
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

    def test_freshness_block(self, mig):
        """ⓘ 2026-11-02a(결정 0045 PR⑥ — 지하철 18번 줄 · 서울시 세 줄 +6개월)부터 정본의 신선도 덩어리는 11-02a 와 같다
        (그 대조는 tests/test_seoul_subway_migration.py · tests/test_data_freshness_migration.py) — 이 원장(11-01b)은
        '11-01a 판 + SGIS 갈래' 글 그대로여야 한다."""
        assert fresh_derived_problems(fresh_block(mig), fresh_block(read(PREV_FRESH))) == []

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
        assert "$$ select * from public.get_district_census_pop(p_pnu) $$;" in block

    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_signature_and_returned_columns(self, mig, name):
        block = fn_block(mig, name)
        assert "function {}(p_pnu text)".format(name) in block
        m = re.search(r"(?is)returns\s+table\s*\((.*?)\)\s*language", block)
        assert tuple(ln.split()[0] for ln in m.group(1).splitlines() if ln.strip()) == RETURNS

    def test_business_count_is_not_returned(self, mig):
        """👤 ③-1 — 거주 인구·가구·총종사자 셋만. 사업체 수(est)는 표에만 있고 함수는 안 내보낸다."""
        block = fn_block(mig, FN)
        assert not any(c.startswith("est") for c in RETURNS)
        assert re.search(r"\best(_lo|_hi)?\b", "\n".join(code_lines(body_of(block)))) is None
        # 양성 대조 — 표에는 있다(탐지가 늘 '없음'을 말하는 것이 아니다).
        assert re.search(r"\best(_lo|_hi)?\b", "\n".join(code_lines(table_block(mig, TABLES[0]))))

    def test_one_signature_per_name(self, mig, schema):
        for name in (FN, API_FN):
            for sql in (mig, schema):
                assert len(re.findall(r"(?im)^\s*create\s+(?:or\s+replace\s+)?function\s+" + re.escape(name)
                                      + r"\s*\(", statements(sql))) == 1, name

    def test_pnu_cast(self, mig):
        body = body_of(fn_block(mig, FN))
        assert "p.pnu = p_pnu::char(19)" in body
        assert re.search(r"\bp\.pnu\s*=\s*p_pnu\s*(?:\)|and|$)", body, re.M) is None

    def test_release_first_and_zero_rows_without_it(self, mig):
        body = " ".join(" ".join(code_lines(body_of(fn_block(mig, FN)))).split())
        assert "select r.received_on, r.base_year, r.bnd_base_date from sgis_census_release r" in body
        assert "from rows_out ro cross join rel r" in body
        assert "left join district_census_pop c on c.district_id = h.district_id" in body


class TestSharedWithDistrictPop:
    """상권 찾기·빈 상태·차례는 list_district_pop 글 그대로(서울 → 대전) — 갈리면 카드끼리 다른 상권을 말한다."""

    def test_me_hit_head_are_the_pop_text(self, schema):
        assert shared_cte_problems(body_of(fn_block(schema, FN)), body_of(fn_block(schema, POP_FN))) == []

    @pytest.mark.parametrize("old,new", [
        ("st_contains(d.geom, me.geom)", "st_contains(me.geom, d.geom)"),                 # 변형: 인자 순서
        ("where left(p_pnu::char(19), 2) = '30'\n      and left(d.sigungu_code, 2) = '30'",
         "where left(p_pnu::char(19), 2) = '30'\n      and left(d.sigungu_code, 2) = '11'"),
        ("then 'no_coord'\n             when left(p_pnu::char(19), 2) <> '30' then 'not_daejeon'",
         "then 'no_coord'\n             when left(p_pnu::char(19), 2) <> '11' then 'not_daejeon'"),
    ])
    def test_detector_catches_variants(self, schema, old, new):
        body = body_of(fn_block(schema, FN))
        assert old in body, "전제: 그 글자가 지금 판에 있다"
        assert shared_cte_problems(body.replace(old, new, 1), body_of(fn_block(schema, POP_FN)))

    def test_narrow_district_first(self, schema):
        body = "\n".join(code_lines(body_of(fn_block(schema, FN))))
        assert body.rstrip().endswith("order by ro.sort_area asc, ro.district_id;")
        assert "h.area_m2" in body


class TestPermissions:
    def test_only_the_api_twin_is_granted(self, mig, schema):
        assert grant_targets(mig) == [API_FN]
        assert [t for t in grant_targets(schema) if t.endswith(FN)] == [API_FN]

    @pytest.mark.parametrize("bad", [
        "grant execute on function get_district_census_pop(text) to anon;",
        "  GRANT ALL\n  ON FUNCTION public.Get_District_Census_Pop ( text ) TO authenticated;",
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
        assert len(post_load.ANON_READABLE_ALLOWLIST) + len(post_load.ANON_CALLABLE_ALLOWLIST) == 39
        assert set(TABLES) <= set(post_load.ANALYZE_TABLES)


class TestTablesShape:
    def test_pop_table_columns_and_checks(self, mig):
        block = table_block(mig, "district_census_pop")
        assert re.search(r"(?m)^\s+district_id\s+text primary key,$", block)
        assert re.search(r"(?m)^\s+sigungu_code\s+char\(5\) not null,$", block)
        assert re.search(r"(?m)^\s+n_overlap\s+integer not null check \(n_overlap >= 1\),$", block)
        assert "check (0 <= n_full and n_full <= n_overlap)," in block
        for k in ("pop", "hh", "emp", "est"):
            assert "check (0 <= {0}_lo and {0}_lo <= {0} and {0} <= {0}_hi)".format(k) in block, k
            for s in ("", "_lo", "_hi"):
                assert re.search(r"(?m)^\s+" + k + s + r"\s+integer not null,$", block), k + s
        # 집계구 경계는 안 싣는다(👤 ③-1) — 도형 칸 0.
        assert "geom" not in "\n".join(code_lines(block))

    def test_release_table(self, mig):
        block = table_block(mig, "sgis_census_release")
        assert re.search(r"(?m)^\s+id\s+smallint primary key check \(id = 1\),$", block)
        for c, t in (("received_on", "date"), ("base_year", "smallint"), ("bnd_base_date", "date"),
                     ("n_oa_total", "integer"), ("rows_cnt", "integer"), ("built_at", "timestamptz"),
                     ("overlap_min_m2", "numeric"), ("full_ratio", "numeric")):
            assert re.search(r"(?m)^\s+" + c + r"\s+" + t + r" not null", block), c


class TestFreshness:
    def test_new_block_is_the_old_block_plus_the_changes(self, mig):
        assert fresh_derived_problems(fresh_block(mig), fresh_block(read(PREV_FRESH))) == []

    @pytest.mark.parametrize("old,new", [
        ("sgis_census_release r),\n           'sgis',", "sgis_census_release r),\n           'none',"),
        ("interval '12 months'", "interval '1 year 1 day'"),
        ("           '월 1회'\n", "           '월 2회'\n"),
        ("열여섯 갈래", "열다섯 갈래"),
    ])
    def test_detector_catches_variants(self, mig, old, new):
        block = fresh_block(mig)
        assert old in block
        assert fresh_derived_problems(block.replace(old, new, 1), fresh_block(read(PREV_FRESH)))

    def test_seventeenth_row_and_one_new_rule_kind(self, mig):
        block = fresh_block(mig)
        body = "\n".join(code_lines(body_of(block)))
        assert body.count("union all") == 15
        assert re.search(r"select 17, '상권 인구 \(통계청 집계구\)', '받은 날',\n\s+\(select r\.received_on::text from "
                         r"sgis_census_release r\),\n\s+'sgis',", body)
        assert rule_kinds(block) == rule_kinds(fresh_block(read(PREV_FRESH))) | {"sgis"}
        assert ("when n.rule_kind = 'sgis' and n.basis ~ '^\\d{4}-\\d{2}-\\d{2}$'\n"
                "             then (n.basis::date + interval '12 months')::date") in body

    def test_comment_says_sixteen_three_times(self, mig):
        m = re.search(r"(?ms)^comment\s+on\s+function\s+get_data_freshness\s*\(\)\s+is.*?';\s*$", mig)
        text = m.group(0)
        assert "열여섯 갈래" in text and "열여섯 표" in text and "집계 도장 열여섯 개" in text
        assert "열다섯" not in text
        assert "SGIS 상권 인구는 받은 날 + 12개월" in text

    def test_api_twin_is_not_recreated(self, mig):
        assert not re.search(r"(?im)^\s*create\s+(?:or\s+replace\s+)?function\s+api\.get_data_freshness",
                             statements(mig))

    def test_hint_key_and_card_source_are_the_server_label(self, schema):
        assert "'{}'".format(SRC) in schema
        assert SRC in cdf.SOURCE_HINTS
        hint = cdf.SOURCE_HINTS[SRC]
        assert hint.index("build_sgis_district_pop.py") < hint.index("load_sgis_district_pop.py --dry-run") \
            < hint.index("post_load.py")
        m = re.search(r"census_pop:\s*\{\s*src:\s*'([^']+)'", read(CARD_TS))
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

    def test_only_new_objects_and_the_freshness_function(self, mig):
        code = statements(mig)
        assert not re.search(r"(?im)^\s*(?:drop|insert|update|delete|truncate)\s", code)
        alters = re.findall(r"(?im)^alter\s+table\s+(\w+)\s+(.*);", code)
        assert alters == [(t, "enable row level security") for t in TABLES]
        made = re.findall(r"(?im)^create\s+(?:or\s+replace\s+)?(table|function|index)\s+(?:if\s+not\s+exists\s+)?([\w.]+)",
                          code)
        assert made == [("table", TABLES[0]), ("table", TABLES[1]), ("function", FN), ("function", API_FN),
                        ("function", "get_data_freshness")]
        assert not re.search(r"(?im)^comment\s+on\s+column\b", code)

    def test_rollback_paragraph_is_written(self, mig):
        for s in ("되돌리기", "2026-11-01a_store_history.sql", "drop function api.get_district_census_pop(text)",
                  "drop table sgis_census_release", "drop table district_census_pop", "38 → 37"):
            assert s in mig, s

    def test_no_banned_words(self, mig):
        for w in ("적정가격", "적정가", "감정가", "평가액", "가치평가"):
            assert w not in mig


# ── ② 실행 가드 (로컬 PostgreSQL 이 있을 때만) ──────────────────────────────

SHIM = """
create role anon;
create role authenticated;
create schema api;
create table parcel (pnu char(19) primary key, geom text, land_price_year smallint);
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
create table district_sales (quarter char(5));
create table district_pop_flow (quarter char(5));
create table seoul_trdar_release (tbl text, value_quarter char(5));
create table store_history_release (last_ym char(6));
"""

DJ_A = "3020010100100010000"      # 좁은 상권 DN(자료 있음)과 넓은 상권 DW(자료 없음) 둘 다
DJ_OUT = "3020010100100020000"    # 대전인데 상권 밖
DJ_NOGEOM = "3020010100100030000"
SEOUL = "1168010100100010000"     # 서울 — 좌표 있음
SEOUL_NOGEOM = "1168010100100020000"

FIXTURE = """
insert into parcel (pnu, geom) values ('{a}', 'PA'), ('{o}', 'PO'), ('{n}', null), ('{s}', 'PS'), ('{sn}', null);
insert into district values
  ('sbiz-1', '좁은 상권', '주요상권', '30200', '|PA|', 1000),
  ('sbiz-2', '넓은 상권', '주요상권', '30200', '|PA|PX|', 9000),
  ('3001', '서울 상권', '골목상권', '11680', '|PS|', 500);
insert into district_census_pop values
  ('sbiz-1', '좁은 상권', '주요상권', '30200', 163949.7, 13, 5, 99.995,
   4348, 2513, 6172, 3213, 1800, 4000, 5201, 2819, 12161, 640, 300, 900);
""".format(a=DJ_A, o=DJ_OUT, n=DJ_NOGEOM, s=SEOUL, sn=SEOUL_NOGEOM)
RELEASE = ("insert into sgis_census_release values "
           "(1, %s, 2024, '2025-06-30', 108510, 37, '2026-11-01 19:30:59+09', 100.0, 0.99)")


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


def _fresh(conn, migration_sql=None, release=datetime.date(2026, 10, 8)):
    """흉내 판을 새로 깔고 마이그 파일을 **통째로** 돌린 뒤 가짜 줄을 넣는다(release=None 이면 표지 0줄)."""
    cur = conn.cursor()
    cur.execute("drop schema if exists api cascade; drop schema if exists public cascade; create schema public;")
    cur.execute("drop role if exists anon; drop role if exists authenticated;")
    cur.execute(SHIM)
    cur.execute(migration_sql or read(FOUND[0]))
    cur.execute(FIXTURE)
    if release is not None:
        cur.execute(RELEASE, (release,))
    return cur


def _call(cur, pnu):
    cur.execute("select * from api.get_district_census_pop(%s)", (pnu,))
    cols = [d[0] for d in cur.description]
    return cols, [dict(zip(cols, r)) for r in cur.fetchall()]


def _fresh_rows(cur):
    cur.execute("select src, basis_kind, basis, next_expected, cadence from get_data_freshness()")
    rows = cur.fetchall()
    assert len(rows) == 16
    return {r[0]: r[1:] for r in rows}


@pytest.fixture(scope="module")
def cur(pg):
    return _fresh(pg)


class TestRealRunFunction:
    def test_no_release_gives_zero_rows(self, pg):
        c = _fresh(pg, release=None)
        try:
            for p in (DJ_A, DJ_OUT, DJ_NOGEOM, SEOUL):
                assert _call(c, p)[1] == [], p
        finally:
            _fresh(pg)

    def test_columns_are_the_twenty_and_no_business_count(self, cur):
        cols, _ = _call(cur, DJ_A)
        assert tuple(cols) == RETURNS
        assert not [c for c in cols if c.startswith("est")]

    def test_narrow_first_ok_then_no_data(self, cur):
        _, rows = _call(cur, DJ_A)
        assert [(r["status"], r["district_id"]) for r in rows] == [("ok", "sbiz-1"), ("no_data", "sbiz-2")]
        ok, nd = rows
        assert (ok["n_overlap"], ok["n_full"], ok["pop"], ok["pop_lo"], ok["pop_hi"]) == (13, 5, 4348, 2513, 6172)
        assert (ok["hh"], ok["emp"], ok["emp_lo"], ok["emp_hi"]) == (3213, 5201, 2819, 12161)
        assert float(ok["cover_pct"]) == pytest.approx(99.995) and float(ok["area_m2"]) == pytest.approx(163949.7)
        assert (ok["received_on"], ok["base_year"], ok["bnd_base_date"]) == \
            (datetime.date(2026, 10, 8), 2024, datetime.date(2025, 6, 30))
        # no_data 는 숫자 칸 전부 null(0 이 아니다) · 이름·표지는 있다.
        assert all(nd[c] is None for c in RETURNS[4:17])
        assert nd["district_nm"] == "넓은 상권" and nd["received_on"] == datetime.date(2026, 10, 8)

    @pytest.mark.parametrize("pnu,status", [
        (DJ_NOGEOM, "no_coord"), (SEOUL_NOGEOM, "no_coord"), (SEOUL, "not_daejeon"),
        (DJ_OUT, "outside_daejeon_district"),
    ])
    def test_building_level_status_is_one_row(self, cur, pnu, status):
        _, rows = _call(cur, pnu)
        assert [r["status"] for r in rows] == [status]
        assert rows[0]["district_id"] is None and rows[0]["pop"] is None
        assert rows[0]["received_on"] == datetime.date(2026, 10, 8)

    def test_checks_reject_bad_rows(self, pg):
        psycopg2 = pytest.importorskip("psycopg2")
        c = _fresh(pg)
        base = "insert into district_census_pop values ('sbiz-9', 'x', null, '30200', 1, {}, {}, 99, {}, 0, 0, 0, 0, 0, 0, 0, 0, 0)"
        try:
            for n_ov, n_full, pop in ((1, 2, "5, 0, 9"), (0, 0, "5, 0, 9"), (2, 1, "5, 6, 9"), (2, 1, "10, 0, 9")):
                with pytest.raises(psycopg2.errors.CheckViolation):
                    c.execute(base.format(n_ov, n_full, pop))
            c.execute(base.format(2, 1, "5, 0, 9"))      # 양성 대조 — 맞는 줄은 들어간다
        finally:
            _fresh(pg)


class TestRealRunFreshness:
    def test_row17_due_received_plus_twelve_months(self, cur):
        kind, basis, nxt, cadence = _fresh_rows(cur)[SRC]
        assert (kind, basis) == ("받은 날", "2026-10-08")
        assert nxt is not None and nxt == datetime.date(2027, 10, 8)
        assert "연 1회" in cadence

    def test_loading_today_is_not_overdue(self, pg):
        """적재 당일 안 지남 — 받은 날 = 오늘이면 예정일이 오늘보다 뒤다(오늘 기준 · 하드코딩 0)."""
        today = datetime.date.today()
        c = _fresh(pg, release=today)
        try:
            nxt = _fresh_rows(c)[SRC][2]
            assert nxt is not None and nxt > today
        finally:
            _fresh(pg)

    def test_empty_release_keeps_the_row(self, pg):
        c = _fresh(pg, release=None)
        try:
            assert _fresh_rows(c)[SRC][1:3] == (None, None)
        finally:
            _fresh(pg)

    def test_mutation_rule_none_loses_the_date(self, pg):
        """양성 대조 — 17 줄 규칙을 none 으로 바꾸면 예정일이 사라진다(위 날짜 단언이 빨강)."""
        sql = read(FOUND[0])
        old = "sgis_census_release r),\n           'sgis',"
        assert sql.count(old) == 1
        c = _fresh(pg, sql.replace(old, "sgis_census_release r),\n           'none',", 1))
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
                    ("public." + FN + SIG, API_FN + SIG, API_FN + SIG))
        assert cur.fetchone() == (False, True, True)

    def test_twin_works_with_an_empty_search_path(self, cur):
        cur.execute("set search_path to ''")
        try:
            assert _call(cur, DJ_A)[1][0]["pop"] == 4348
        finally:
            cur.execute("reset search_path")

    def test_one_signature_per_name(self, cur):
        cur.execute("select n.nspname, count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                    "where p.proname = %s group by 1 order by 1", (FN,))
        assert cur.fetchall() == [("api", 1), ("public", 1)]

    def test_applying_twice_gives_the_same_answer(self, pg):
        c = _fresh(pg)
        try:
            before = (_call(c, DJ_A), _call(c, SEOUL), _fresh_rows(c))
            c.execute(read(FOUND[0]))
            assert (_call(c, DJ_A), _call(c, SEOUL), _fresh_rows(c)) == before
        finally:
            _fresh(pg)

    def test_mutation_public_grant_opens_the_original(self, pg):
        """변이 — public 원본에도 grant 를 주면 anon 이 원본을 부를 수 있다(위 권한 단언이 빨강)."""
        line = "grant execute on function api.get_district_census_pop(text) to anon, authenticated;"
        sql = read(FOUND[0])
        assert sql.count(line) == 1
        c = _fresh(pg, sql.replace(line, line + "\ngrant execute on function get_district_census_pop(text) to anon;", 1))
        try:
            c.execute("select has_function_privilege('anon', 'public.get_district_census_pop(text)', 'execute')")
            assert c.fetchone() == (True,)
        finally:
            _fresh(pg)

    def test_mutation_seoul_districts_lose_the_daejeon_rows(self, pg):
        """변이 — hit 의 상권 시·도를 서울(11)로 바꾸면 대전 필지가 상권 밖으로 나온다(위 ok 단언이 빨강)."""
        old = "      and left(d.sigungu_code, 2) = '30'\n"
        sql = read(FOUND[0])
        assert sql.count(old) == 1
        c = _fresh(pg, sql.replace(old, "      and left(d.sigungu_code, 2) = '11'\n", 1))
        try:
            assert [r["status"] for r in _call(c, DJ_A)[1]] == ["outside_daejeon_district"]
        finally:
            _fresh(pg)
