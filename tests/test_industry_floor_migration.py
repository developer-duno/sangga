# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-09b(업종별 층 분포 · 물결 2-2)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙여 넣기 전에는 아무도 모르는 종류의 실수**다:

  1) 마이그레이션과 정본(schema.sql)의 글자가 갈린다 → 새 환경만 다른 모양으로 만들어진다.
     `create or replace` 는 머리 속성(security definer·search_path·stable·immutable)을 새 정의로
     덮어쓰는데, 드리프트 가드는 `$$` 안 본문만 본다 — 그래서 머리·comment 까지 여기서 글자로 대조한다.
  2) 요약표를 published_ym 으로 굽는다 → 표지를 올린 순간 이 표만 옛 분기를 말한다(결정 0035 —
     요약표는 loaded, 실시간은 published).
  3) public 원본에 grant 를 준다 → security definer 원본이 밖에 열린다(🚪 grant 는 api 쌍둥이에만).
  4) bands 열쇠 다섯 중 하나가 빠진다 → 화면 검증기가 그 응답을 통째로 버려 층 줄이 조용히 사라진다.
  5) 층 묶음 함수에 `strict` 가 붙는다 → 층 미상(NULL)이 'na' 가 아니라 이름 없는 묶음이 된다.

② 실행 가드(로컬 PostgreSQL 이 있을 때만)는 흉내 판 위에서 세 문장(층 묶음·요약표·함수)을 실제로
   돌려 가짜 점포 여섯(층 NULL·−1·1·2·3·99)이 b:1 · 1:1 · 2:1 · 3+:2 · na:1 로 묶이는지 본다.
   CI 에는 PostgreSQL 이 없어 건너뛴다(형제 tests/test_district_openclose_migration.py 와 같은 꼴).
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
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-09b_industry_floor.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

BAND_FN = "industry_floor_band"
LIST_FN = "list_industry_floors"
API_FN = "api.list_industry_floors"
MV = "mv_district_industry_floor"
MIX = "mv_district_industry_mix"
BAND_KEYS = ("b", "1", "2", "3+", "na")


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


def mv_block(sql, name):
    m = re.search(r"(?ms)^create\s+materialized\s+view\s+if\s+not\s+exists\s+" + re.escape(name)
                  + r"\s+as\b.*?;", sql)
    assert m, "{} 의 정의를 못 찾았습니다".format(name)
    return m.group(0)


def mv_comment(sql, name):
    m = re.search(r"(?ms)^comment\s+on\s+materialized\s+view\s+" + re.escape(name) + r"\s+is.*?';\s*$", sql)
    assert m, "{} 의 comment 를 못 찾았습니다".format(name)
    return m.group(0)


def head_of(block):
    return block[: block.index("$$")]


def body_of(block):
    return block[block.index("$$") + 2: block.rindex("$$")]


def grant_targets(sql):
    """`grant … on function <대상>(` 의 대상 이름 전부(소문자 · 스키마 그대로).

    권한 종류(execute·all)·받는 역할·들여쓰기·줄바꿈·대소문자와 무관하게 본다.
    ⓘ 가드 본체와 양성 대조가 이 **같은 함수**를 지난다.
    ⚠️ 못 보는 것: 인자 괄호 없는 `on function <이름> to …` · 따옴표 이름 · 일괄 grant(`all functions in schema`).
    """
    found = []
    for stmt in re.findall(r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*?"
                           r"\bon\s+(?:function|routine)\b([^;]*)", statements(sql)):
        found += re.findall(r"(?i)(?<![\w.])((?:\w+\.)?\w+)\s*\(", stmt)
    return [t.lower() for t in found]


def mv_snapshot_problems(block):
    """요약표가 어느 칸으로 굽는지 — 어긋난 까닭 목록(비면 정상). 가드 본체와 양성 대조가 같은 함수를 지난다.

    ⚠️ 못 보는 것: 표지를 함수·뷰를 거쳐 간접으로 읽는 꼴.
    """
    code = statements(block)
    out = []
    if not re.search(r"ub\.snapshot_ym\s*=\s*\(\s*select\s+r\.loaded_ym\s+from\s+snapshot_release\s+r\s*\)", code):
        out.append("loaded_ym 으로 굽지 않음")
    if "published_ym" in code:
        out.append("published_ym 을 읽음")
    if re.search(r"max\s*\(\s*(?:\w+\.)?snapshot_ym\s*\)", code):
        out.append("max(snapshot_ym) 을 읽음")
    return out


def strict_problems(block):
    """층 묶음 함수의 머리 — strict(또는 같은 뜻의 returns null on null input)면 문제."""
    head = head_of(block).lower()
    out = []
    if re.search(r"\bstrict\b", head) or "returns null on null input" in head:
        out.append("strict")
    if not re.search(r"(?m)^immutable\s*$", head):
        out.append("immutable 아님")
    return out


# ── ① 글자 가드 ─────────────────────────────────────────────────────────────


class TestMirrorsTheSchema:
    @pytest.mark.parametrize("name", (BAND_FN, LIST_FN, API_FN))
    def test_head_and_body_are_the_same_text(self, mig, schema, name):
        assert fn_block(mig, name) == fn_block(schema, name), (
            "{} 가 정본과 글자가 다릅니다 — 새 환경만 다른 모양이 됩니다".format(name))

    @pytest.mark.parametrize("name", (BAND_FN, LIST_FN))
    def test_comment_is_the_same_text(self, mig, schema, name):
        assert fn_comment(mig, name) == fn_comment(schema, name), name

    def test_summary_table_is_the_same_text(self, mig, schema):
        assert mv_block(mig, MV) == mv_block(schema, MV)
        assert mv_comment(mig, MV) == mv_comment(schema, MV)

    def test_summary_table_is_the_sibling_plus_one_column(self, schema):
        """형제 정의 그대로 + 층 묶음 칸 하나 + group by 일곱 칸 — 그래야 합 대조가 성립한다."""
        mix = mv_block(schema, MIX).replace(MIX, MV, 1)
        expected = (mix.replace(
            "       ub.cat_m_cd, ub.cat_m_nm,\n",
            "       ub.cat_m_cd, ub.cat_m_nm,\n"
            "       public.industry_floor_band(ub.floor_no) as floor_band,\n", 1)
            .replace("group by 1, 2, 3, 4, 5, 6;", "group by 1, 2, 3, 4, 5, 6, 7;", 1))
        assert mv_block(schema, MV) == expected

    def test_unique_index_has_the_floor_band(self, mig, schema):
        for sql in (mig, schema):
            assert re.search(r"(?m)^create unique index if not exists mv_district_industry_floor_key\n"
                             r"  on mv_district_industry_floor \(district_id, snapshot_ym, cat_m_cd, floor_band\);",
                             statements(sql)), "유일 색인이 없으면 refresh concurrently 가 멈춥니다"
        assert "mv_district_industry_floor_key" in post_load_canonical_index_names(schema)


def post_load_canonical_index_names(schema_sql):
    """정본의 `create [unique] index … <이름>` 이름들 — post_load --check 의 정본 색인 점검이 이 표를 본다."""
    return set(re.findall(r"(?im)^create\s+(?:unique\s+)?index\s+(?:if\s+not\s+exists\s+)?(\w+)", schema_sql))


class TestHeads:
    def test_band_function_is_immutable_and_not_strict(self, mig):
        assert strict_problems(fn_block(mig, BAND_FN)) == []

    @pytest.mark.parametrize("bad", (
        "immutable\nstrict\n", "immutable strict\n", "immutable\nreturns null on null input\n", "stable\n"))
    def test_strict_detector_catches_variants(self, mig, bad):
        """양성 대조 — strict 를 붙인 꼴·한 줄 꼴·같은 뜻의 긴 꼴·immutable 이 빠진 꼴이 걸린다."""
        block = fn_block(mig, BAND_FN).replace("immutable\n", bad, 1)
        assert strict_problems(block), bad

    def test_band_cases(self, mig):
        body = statements(body_of(fn_block(mig, BAND_FN)))
        for piece in ("when p_floor is null then 'na'", "when p_floor < 0     then 'b'",
                      "when p_floor = 1     then '1'", "when p_floor = 2     then '2'", "else '3+'"):
            assert piece in body, piece
        # 옥탑 99 는 따로 가르지 않는다 — else 로 3+.
        assert "99" not in body

    def test_list_function_head(self, mig):
        head = head_of(fn_block(mig, LIST_FN))
        assert "security definer" in head and "set search_path = public" in head
        assert re.search(r"(?m)^stable\s*$", head)
        assert "p_cat_m text[] default null" in head

    def test_api_twin_head_and_body(self, mig):
        block = fn_block(mig, API_FN)
        head = head_of(block)
        assert "security definer" in head and "set search_path = ''" in head
        assert re.search(r"(?m)^stable\s*$", head)
        assert body_of(block).strip() == "select public.list_industry_floors(p_pnu, p_cat_l, p_cat_m)"


class TestSnapshot:
    def test_summary_table_reads_loaded_not_published(self, mig, schema):
        for sql in (mig, schema):
            assert mv_snapshot_problems(mv_block(sql, MV)) == []

    @pytest.mark.parametrize("old, new", (
        ("select r.loaded_ym from snapshot_release r", "select r.published_ym from snapshot_release r"),
        ("(select r.loaded_ym from snapshot_release r)", "(select max(u.snapshot_ym) from unit_business u)"),
    ))
    def test_mutation_published_or_max_is_noticed(self, mig, old, new):
        block = mv_block(mig, MV)
        assert old in block
        assert mv_snapshot_problems(block.replace(old, new, 1))

    def test_list_function_reads_the_same_snap_as_the_sibling(self, schema):
        """두 함수가 같은 분기를 말해야 한다 — snap 의 2순위는 published, 1순위는 이 요약표."""
        body = statements(body_of(fn_block(schema, LIST_FN)))
        assert "(select max(m.snapshot_ym) from mv_district_industry_floor m)," in body
        assert "(select r.published_ym from snapshot_release r)) as ym" in body

    @pytest.mark.parametrize("cte", ("me", "hit", "near"))
    def test_me_hit_near_are_the_sibling_text(self, schema, cte):
        """반경·상권을 형제와 다른 자로 재면 같은 카드 안 두 숫자가 서로 다른 동네를 센다."""
        def grab(name):
            body = body_of(fn_block(schema, name))
            m = re.search(r"(?ms)^  " + cte + r" as \(\n.*?^  \),?\n", body)
            assert m, (name, cte)
            return statements(m.group(0)).rstrip(",\n")
        assert grab(LIST_FN) == grab("list_industry_detail")


class TestBands:
    def test_all_five_keys_are_in_the_body(self, mig):
        body = statements(body_of(fn_block(mig, LIST_FN)))
        values = re.search(r"values\s*(\(.*?\))\s*as\s+v\(k\)", body, re.S)
        assert values, "열쇠 다섯 values 목록을 못 찾았습니다"
        keys = re.findall(r"\('([^']*)'\)", values.group(1))
        assert tuple(keys) == BAND_KEYS

    def test_both_scopes_take_bands_from_the_five(self, mig):
        body = statements(body_of(fn_block(mig, LIST_FN)))
        assert body.count("jsonb_object_agg(b.k, coalesce(s.n, 0))") == 2
        assert body.count("from band b") == 2

    def test_cast_char_types_are_kept(self, mig):
        body = statements(body_of(fn_block(mig, LIST_FN)))
        assert body.count("p_cat_l::char(2)") == 2
        assert body.count("p_cat_m::char(4)[]") == 2
        assert "p_pnu::char(19)" in body

    def test_echoes_the_question(self, mig):
        body = statements(body_of(fn_block(mig, LIST_FN)))
        assert "'cat_l_cd', p_cat_l," in body and "'cat_m_cds', p_cat_m," in body

    def test_no_store_name_leaves(self, mig):
        assert "biz_name" not in statements(body_of(fn_block(mig, LIST_FN)))


class TestPermissions:
    def test_only_the_api_twin_is_granted(self, mig, schema):
        assert grant_targets(mig) == [API_FN]
        assert [t for t in grant_targets(schema) if "industry_floor" in t] == [API_FN]

    @pytest.mark.parametrize("bad", (
        "grant execute on function list_industry_floors(text, text, text[]) to anon;",
        "grant all on function public.list_industry_floors(text, text, text[]) to anon;",
        "  GRANT EXECUTE\n  ON FUNCTION industry_floor_band ( smallint ) TO authenticated;",
    ))
    def test_grant_detector_catches_the_public_original(self, mig, bad):
        """양성 대조 — public 원본에 grant 를 주는 사본이 걸린다(흔한 꼴 + 들여쓴·대문자 변형 꼴)."""
        found = grant_targets(mig + "\n" + bad + "\n")
        assert [t for t in found if t != API_FN], found

    @pytest.mark.parametrize("name", ("industry_floor_band(smallint)", "list_industry_floors(text, text, text[])",
                                      "api.list_industry_floors(text, text, text[])"))
    def test_every_function_is_revoked_with_anon_named(self, mig, name):
        assert re.search(r"(?m)^revoke all on function " + re.escape(name)
                         + r" from public, anon, authenticated;", statements(mig)), name

    def test_revoke_before_grant(self, mig):
        code = statements(mig)
        assert (code.index("revoke all on function api.list_industry_floors(")
                < code.index("grant execute on function api.list_industry_floors("))

    def test_summary_table_is_closed(self, mig, schema):
        for sql in (mig, schema):
            assert re.search(r"(?m)^revoke all on mv_district_industry_floor from public, anon, authenticated;",
                             statements(sql))

    def test_allowlist_has_the_api_twin_only(self):
        assert API_FN in post_load.ANON_CALLABLE_ALLOWLIST
        assert "list_industry_floors" not in post_load.ANON_CALLABLE_ALLOWLIST
        assert not [n for n in post_load.ANON_READABLE_ALLOWLIST if MV in n]


class TestMigrationShape:
    def test_settings_before_begin_and_notify_after_commit(self, mig):
        code = statements(mig)
        begin = re.search(r"(?m)^begin;", code).start()
        commit = re.search(r"(?m)^commit;", code).start()
        notify = code.index("notify pgrst, 'reload schema';")
        assert code.index("set lock_timeout = ") < begin
        assert code.index("set statement_timeout = '900s';") < begin
        assert begin < commit < notify
        assert len(re.findall(r"(?m)^begin;", code)) == 1 and len(re.findall(r"(?m)^commit;", code)) == 1
        for stmt in re.finditer(r"(?im)^(create|drop|alter|insert|revoke|grant|analyze|comment)\b", code):
            assert begin < stmt.start() < commit, "begin/commit 밖의 문장: " + stmt.group(0)

    def test_only_new_objects(self, mig):
        """기존 객체는 안 건드린다 — drop·alter 0, 다시 만드는 함수는 새 이름 셋뿐."""
        code = statements(mig)
        assert not re.search(r"(?im)^\s*(drop|alter)\s", code)
        made = re.findall(r"(?im)^create\s+(?:or\s+replace\s+)?function\s+([\w.]+)\s*\(", code)
        assert made == [BAND_FN, LIST_FN, API_FN]

    def test_rollback_paragraph_is_written(self, mig):
        assert "되돌리기" in mig and "drop materialized view mv_district_industry_floor" in mig


# ── ①-2 점포 색인 include 에 층 (2026-10-09c) ─────────────────────────────────
# 반경 층 집계(rsub)가 floor_no 를 꺼내는데 idx_ub_pnu_cat include 에 없어 Index Scan → 힙 방문이었다
# (적용 전 실측 찬 캐시 3,292ms · read 4,539쪽 / 더운 12ms). 정본과 마이그레이션의 include 가 **순서까지**
# 같아야 post_load --check 의 정본 색인 점검(INCLUDE 순서 대조)이 [정상]이다.

INDEX_MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-09c_ub_pnu_cat_include_floor.sql")
UB_INCLUDE = ["cat_l_cd", "cat_l_nm", "cat_m_cd", "cat_m_nm", "floor_no"]


@pytest.fixture(scope="module")
def index_mig():
    return read(INDEX_MIGRATION)


def ub_pnu_cat_include(sql, name="idx_ub_pnu_cat"):
    """`create [unique] index [concurrently] [if not exists] <name> on unit_business (pnu, snapshot_ym)
    include (…)` 의 include 칸 목록(순서 그대로 · 소문자). 없으면 None.

    ⓘ 가드 본체와 양성 대조가 이 같은 함수를 지난다. 주석 줄은 걷어 낸다(되돌리기 주석의 네 칸 꼴에 안 속게).
    ⚠️ 못 보는 것: 따옴표 칸 이름 · 색인 열이 (pnu, snapshot_ym) 가 아닌 꼴(그건 다른 색인이다).
    """
    m = re.search(r"(?is)create\s+(?:unique\s+)?index\s+(?:concurrently\s+)?(?:if\s+not\s+exists\s+)?"
                  + re.escape(name) + r"\s+on\s+unit_business\s*\(\s*pnu\s*,\s*snapshot_ym\s*\)\s*"
                  r"include\s*\(([^)]*)\)", statements(sql))
    if not m:
        return None
    return [c.strip().lower() for c in m.group(1).split(",") if c.strip()]


class TestUbPnuCatInclude:
    def test_schema_and_migration_have_floor_no_in_the_same_order(self, schema, index_mig):
        assert ub_pnu_cat_include(schema) == UB_INCLUDE
        assert ub_pnu_cat_include(index_mig, "idx_ub_pnu_cat_next") == UB_INCLUDE
        # post_load 의 정본 색인 해석기로도 같은 답이어야 한다(--check 가 실제로 쓰는 쪽).
        assert post_load.canonical_index_includes(schema)["idx_ub_pnu_cat"] == UB_INCLUDE

    @pytest.mark.parametrize("old, new", (
        ("cat_m_nm, floor_no)", "cat_m_nm)"),                       # floor_no 빠짐
        ("(cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, floor_no)",
         "(floor_no, cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm)"),     # 순서 바뀜
    ))
    def test_detector_catches_missing_or_reordered(self, schema, old, new):
        """양성 대조 — floor_no 가 빠지거나 순서가 바뀐 정본 사본이 걸린다."""
        assert old in schema
        assert ub_pnu_cat_include(schema.replace(old, new, 1)) != UB_INCLUDE

    def test_detector_sees_the_concurrent_uppercase_form(self):
        sql = ("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ub_pnu_cat ON unit_business (pnu, snapshot_ym)\n"
               "  INCLUDE (Cat_L_Cd, cat_l_nm, cat_m_cd, cat_m_nm, floor_no);")
        assert ub_pnu_cat_include(sql) == UB_INCLUDE

    def test_not_wrapped_in_a_transaction(self, index_mig):
        code = statements(index_mig)
        assert not re.search(r"(?im)^\s*(begin|commit)\s*;", code), "concurrently 는 트랜잭션 안에서 못 돈다"
        assert code.index("set statement_timeout = '900s';") < code.index("create index concurrently")

    def test_gate_before_drop_and_rename_last(self, index_mig):
        code = statements(index_mig)
        create = code.index("create index concurrently if not exists idx_ub_pnu_cat_next")
        gate = code.index("and pg_get_indexdef(i.indexrelid) like '%floor_no%'")
        drop = code.index("drop index concurrently if exists idx_ub_pnu_cat;")
        lock = code.index("set lock_timeout = '2s';")
        rename = code.index("alter index idx_ub_pnu_cat_next rename to idx_ub_pnu_cat;")
        assert create < gate < drop < lock < rename
        assert "i.indisvalid" in code[create:drop]

    def test_only_this_index_is_touched(self, index_mig):
        code = statements(index_mig)
        assert re.findall(r"(?im)^drop\s+index\s+concurrently\s+if\s+exists\s+(\w+)", code) == ["idx_ub_pnu_cat"]
        assert not re.search(r"(?im)^\s*(create|drop)\s+(materialized\s+view|view|function|table)\b", code)


# ── ② 실행 가드 (로컬 PostgreSQL 이 있을 때만) ──────────────────────────────

SHIM = """
create domain geography as text;
create table parcel (pnu char(19) primary key, geom text);
create table district (district_id text primary key, district_nm text, area_m2 numeric(14,2), geom text);
create table unit_business (snapshot_ym char(6), pnu char(19), floor_no smallint, cat_l_cd char(2),
                            cat_l_nm text, cat_m_cd char(4), cat_m_nm text, geom text, biz_name text);
create table snapshot_release (id int primary key, loaded_ym char(6), published_ym char(6));
-- 흉내 낸 공간 판정: 점 이름이 도형 글자 안에 '|이름|' 꼴로 들어 있으면 담긴 것.
create function st_contains(poly text, pt text) returns boolean language sql immutable
  as 'select position(''|'' || pt || ''|'' in poly) > 0';
-- 반경은 '같은 첫 글자'면 500m 안으로 본다(P* 필지끼리 이웃).
create function st_dwithin(a geography, b geography, r integer, s boolean) returns boolean
  language sql immutable as 'select left(a::text, 1) = left(b::text, 1)';
"""

PNU = "1168010100100010000"
PNU_NOGEOM = "1168010100100020000"

FIXTURE = """
insert into parcel values ('{p}', 'PA'), ('{n}', null);
insert into district values ('D1', '상권', 1000, '|PA|S1|S2|S3|S4|S5|S6|S7|S8|');
insert into snapshot_release values (1, '202606', '202606');
insert into unit_business values
  ('202606', '{p}', null, 'I2', '음식', 'I201', '한식', 'S1', '가'),
  ('202606', '{p}', -1,   'I2', '음식', 'I201', '한식', 'S2', '나'),
  ('202606', '{p}', 1,    'I2', '음식', 'I212', '비알코올', 'S3', '다'),
  ('202606', '{p}', 2,    'I2', '음식', 'I201', '한식', 'S4', '라'),
  ('202606', '{p}', 3,    'I2', '음식', 'I201', '한식', 'S5', '마'),
  ('202606', '{p}', 99,   'I2', '음식', 'I212', '비알코올', 'S6', '바'),
  ('202606', '{p}', 1,    'G2', '소매', 'G204', '종합 소매', 'S7', '사'),
  ('202603', '{p}', 1,    'I2', '음식', 'I201', '한식', 'S8', '아');
""".format(p=PNU, n=PNU_NOGEOM)


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
    """흉내 판 위에 마이그레이션의 세 문장(층 묶음·요약표·함수) + 형제 업종 표(정본)를 넣는다."""
    mig, schema = read(MIGRATION), read(SCHEMA)
    c = pg.cursor()
    c.execute("drop schema if exists public cascade; create schema public;")
    c.execute(SHIM)
    c.execute(FIXTURE)
    c.execute(fn_block(mig, BAND_FN))
    c.execute(mv_block(mig, MV))
    c.execute(mv_block(schema, MIX))
    c.execute(fn_block(mig, LIST_FN))
    return c


def _call(cur, *args):
    cur.execute("select list_industry_floors(%s, %s, %s)", args)
    return cur.fetchone()[0]


class TestRealRun:
    def test_band_function(self, cur):
        cur.execute("select industry_floor_band(x::smallint) from (values (null), (-2), (1), (2), (3), (99)) v(x)")
        assert [r[0] for r in cur.fetchall()] == ["na", "b", "1", "2", "3+", "3+"]

    def test_summary_table_counts_six_stores_in_five_bands(self, cur):
        cur.execute("select floor_band, sum(n) from mv_district_industry_floor where cat_l_cd = 'I2' "
                    "group by 1 order by 1")
        assert dict(cur.fetchall()) == {"b": 1, "1": 1, "2": 1, "3+": 2, "na": 1}
        cur.execute("select distinct snapshot_ym from mv_district_industry_floor")
        assert [r[0] for r in cur.fetchall()] == ["202606"], "loaded_ym 분기 하나만 굽는다"

    def test_district_and_radius_bands(self, cur):
        got = _call(cur, PNU, "I2", None)
        want = {"b": 1, "1": 1, "2": 1, "3+": 2, "na": 1}
        assert got["snapshot_ym"] == "202606" and got["radius_m"] == 500
        assert got["cat_l_cd"] == "I2" and got["cat_m_cds"] is None
        assert got["districts"] == [{"district_id": "D1", "name": "상권", "total": 6, "bands": want}]
        assert got["radius"] == {"total": 6, "bands": want}

    def test_chip_pair_narrows_to_middle_codes(self, cur):
        got = _call(cur, PNU, "I2", ["I212"])
        want = {"b": 0, "1": 1, "2": 0, "3+": 1, "na": 0}
        assert got["cat_m_cds"] == ["I212"]
        assert got["districts"][0]["total"] == 2 and got["districts"][0]["bands"] == want
        assert got["radius"] == {"total": 2, "bands": want}

    def test_empty_category_still_has_five_keys(self, cur):
        got = _call(cur, PNU, "Z9", None)
        zero = dict.fromkeys(BAND_KEYS, 0)
        assert got["districts"][0]["bands"] == zero and got["districts"][0]["total"] == 0
        assert got["radius"] == {"total": 0, "bands": zero}

    def test_no_coord_is_null_radius_and_no_district(self, cur):
        got = _call(cur, PNU_NOGEOM, "I2", None)
        assert got["radius"] is None and got["districts"] == []

    def test_post_load_consistency_sql_runs_and_agrees(self, cur):
        """post_load --check 의 합 대조 문장을 진짜 PostgreSQL 에 — 같은 판에서 어긋남 0."""
        cur.execute(post_load.INDUSTRY_FLOOR_CONSISTENCY_SQL)
        mismatch, mix_rows, floor_rows = cur.fetchone()[0].split("|")
        # 202606 의 (상권·중분류) = I201 · I212 · G204 셋 — 202603 행은 두 표 다 안 굽는다.
        assert (mismatch, mix_rows, floor_rows) == ("0", "3", "3")
        assert post_load.judge_industry_floor_consistency(mismatch, mix_rows, floor_rows) is False

    @pytest.mark.parametrize("mix_rows, floor_rows, want", [
        # 음성 사례 — 층 표에 I212 열쇠가 없다(한쪽에만 있는 열쇠) → 어긋남 1.
        ([("D1", "202606", "I201", 5), ("D1", "202606", "I212", 2)],
         [("D1", "202606", "I201", "1", 5)],
         ("1", "2", "1")),
        # 빈 중분류(NULL) 열쇠가 양쪽에 같은 합으로 있다 → 짝을 찾아 어긋남 0
        # (using/= 로 견주면 NULL 끼리 짝을 못 찾아 양쪽 한 줄씩 어긋남 2 로 늘 [낡음]).
        ([("D1", "202606", None, 3)],
         [("D1", "202606", None, "na", 1), ("D1", "202606", None, "1", 2)],
         ("0", "1", "1")),
        # 같은 NULL 열쇠라도 합이 다르면 잡는다.
        ([("D1", "202606", None, 3)],
         [("D1", "202606", None, "na", 1)],
         ("1", "1", "1")),
    ])
    def test_post_load_consistency_sql_on_hand_made_tables(self, pg, mix_rows, floor_rows, want):
        """합 대조 문장을 손으로 만든 두 표에 — 요약표에는 행을 못 넣으므로 같은 이름의 표를 다른 스키마에 둔다."""
        c = pg.cursor()
        c.execute("drop schema if exists consistency_case cascade; create schema consistency_case;"
                  " set search_path to consistency_case;"
                  " create table mv_district_industry_mix (district_id text, snapshot_ym char(6),"
                  " cat_m_cd char(4), n int);"
                  " create table mv_district_industry_floor (district_id text, snapshot_ym char(6),"
                  " cat_m_cd char(4), floor_band text, n int);")
        try:
            c.executemany("insert into mv_district_industry_mix values (%s, %s, %s, %s)", mix_rows)
            c.executemany("insert into mv_district_industry_floor values (%s, %s, %s, %s, %s)", floor_rows)
            c.execute(post_load.INDUSTRY_FLOOR_CONSISTENCY_SQL)
            got = tuple(c.fetchone()[0].split("|"))
        finally:
            c.execute("reset search_path; drop schema consistency_case cascade;")
        assert got == want
        assert post_load.judge_industry_floor_consistency(*got) is (got[0] != "0")
