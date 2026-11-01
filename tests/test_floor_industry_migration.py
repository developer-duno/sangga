# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-24a(층 목록 업종 띠 · 결정 0038 D · V4)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙여 넣기 전에는 아무도 모르는 종류의 실수**다:

  1) 마이그레이션과 정본(schema.sql)의 글자가 갈린다 → 새 환경만 다른 모양으로 만들어진다.
     `create or replace` 는 머리 속성(security definer·search_path·stable)을 새 정의로 덮어쓰는데,
     드리프트 가드는 `$$` 안 본문만 본다 — 그래서 머리·comment 까지 여기서 글자로 대조한다
     (CLAUDE.md ⛔ 2026-10-01a · 본보기 tests/test_parcel_land_price_migration.py).
  2) 머리 속성 하나가 빠진다 → `set search_path` 가 빠지면 anon 경로가 `relation does not exist` 로 죽고,
     security definer 가 빠지면 닫힌 unit_business 를 못 읽어 `permission denied` 다(화면에선 띠만 조용히 빠진다).
  3) public 원본에 grant 를 준다 → security definer 원본이 밖에 열린다(🚪 grant 는 api 쌍둥이에만).
  4) 인자를 char(19) 로 받지 않는다 → 색인이 죽는다(char(19) 함정 — 2026-08-16b).
  5) **띠 합 ≠ 층 줄의 「점포 N」** — 분기 조건이나 층 조건이 v_floor_stack 의 store_cnt 와 다르면 띠와 글이 다른
     수를 말한다(에러 없이). 글자 가드(분기 조건이 v_floor_stack 과 같은 글)와 실행 가드(같은 흉내 판에서 v_floor_stack 의
     store_cnt 셈 **그 글 그대로**와 층마다 합을 견준다) 둘로 본다.
  6) 같은 이름에 서명이 둘 → PostgREST 가 못 고른다(PGRST203 · 결정 0038 §7) — 정의 개수 글자 가드 + 실행 가드 pg_proc 개수.

② 실행 가드(로컬 PostgreSQL 이 있을 때만)는 흉내 판 위에서 두 함수를 실제로 만들고 불러 본다.
   plpgsql 의 반환 칸 이름 충돌(column reference is ambiguous)은 만들 때가 아니라 **부를 때** 터지므로 이 실행만이 잡는다.
   CI 에는 PostgreSQL 이 없어 건너뛴다.
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
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-24a_floor_industry.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

FN = "list_floor_industry"
API_FN = "api.list_floor_industry"
SIG = "(text)"

PUBLIC_HEAD = ("language plpgsql", "stable", "security definer", "set search_path = public")
API_HEAD = ("language sql", "stable", "security definer", "set search_path = ''")

RETURNS = (
    "returns table (\n  floor_no  smallint,\n  cat_l_cd  text,\n  cat_l_nm  text,\n  store_cnt integer\n)\n"
)

# v_floor_stack 의 store_cnt 와 **같은 분기 조건**(별칭만 다르다 — 함수는 u., 뷰는 ub.).
SNAPSHOT_COND = "snapshot_ym = (select r.published_ym from snapshot_release r)"


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

    ⚠️ 못 보는 것: 따옴표 이름(`"list_floor_industry"`) · 다른 스키마로 같은 이름(그건 다른 함수다).
    """
    return len(re.findall(r"(?im)^\s*create\s+(?:or\s+replace\s+)?function\s+" + re.escape(name) + r"\s*\(",
                          statements(sql)))


def grant_targets(sql):
    """`grant … on function <대상>(` 의 대상 이름 전부(소문자 · 스키마 그대로).

    ⓘ 가드 본체와 양성 대조가 이 **같은 함수**를 지난다(형제 tests/test_parcel_land_price_migration.py 와 같은 꼴).
    ⚠️ 못 보는 것: 인자 괄호 없는 `on function <이름> to …` · 따옴표 이름 · 일괄 grant(`all functions in schema`).
    """
    found = []
    for stmt in re.findall(r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*?"
                           r"\bon\s+(?:function|routine)\b([^;]*)", statements(sql)):
        found += re.findall(r"(?i)(?<![\w.])((?:\w+\.)?\w+)\s*\(", stmt)
    return [t.lower() for t in found]


def char19_problems(block):
    """인자를 char(19) 로 받아 쓰는지 — 어긋난 까닭 목록(비면 정상). 양성 대조가 같은 함수를 지난다.

    ⚠️ 못 보는 것: 다른 변수 이름으로 받은 꼴(그땐 '받지 않음'으로 빨강 — 넓히지 말고 이름을 맞춘다).
    """
    body = statements(body_of(block))
    out = []
    if not re.search(r"(?m)^\s*v_pnu\s+char\(19\)\s*:=\s*p_pnu\s*;", body):
        out.append("v_pnu char(19) 로 받지 않음")
    if not re.search(r"\bu\.pnu\s*=\s*v_pnu\b", body):
        out.append("u.pnu = v_pnu 로 견주지 않음")
    rest = re.sub(r"(?m)^\s*v_pnu\s+char\(19\)\s*:=\s*p_pnu\s*;", "", body)
    if re.search(r"\bp_pnu\b", rest):
        out.append("p_pnu 를 그대로 씀")
    return out


def view_store_cnt_lateral(schema_sql):
    """정본 v_floor_stack 의 store_cnt 셈(`left join lateral ( … ) st on true`) 글 그대로."""
    view = re.search(r"(?ms)^create\s+or\s+replace\s+view\s+v_floor_stack\s+as\b.*?;\s*$", schema_sql)
    assert view, "정본에서 v_floor_stack 을 못 찾았습니다"
    lat = re.search(r"(?s)left join lateral \(\s*select\s+count\(\*\)::int as store_cnt,.*?\) st on true",
                    view.group(0))
    assert lat, "v_floor_stack 의 store_cnt 셈을 못 찾았습니다 — 이 시험의 대조가 헛돈다"
    return lat.group(0)


def same_rows_problems(fn_body, lateral):
    """띠가 층 줄 「점포 N」과 같은 행 집합을 세는지 — 어긋난 까닭 목록(비면 정상). 양성 대조가 같은 함수를 지난다.

    ① 분기 조건이 v_floor_stack 셈과 같은 글(별칭 빼고) ② 땅 조건 ③ 층 번호로 묶는다(층 null 을 걸러 내거나 0 등으로
    바꾸지 않는다 — 'na' 묶음은 floor_no null 줄) ④ 대분류로 묶는다.
    ⚠️ 못 보는 것: 같은 글이지만 다른 표를 보는 꼴(from 표 이름은 test_reads_only_unit_business_and_release 가 본다).
    """
    body = re.sub(r"\s+", " ", statements(fn_body)).lower()
    view = re.sub(r"\s+", " ", lateral).lower()
    out = []
    if "ub." + SNAPSHOT_COND not in view:
        out.append("v_floor_stack 쪽 분기 조건이 바뀌었다 — 이 시험의 기준을 먼저 맞출 것")
    if "u." + SNAPSHOT_COND not in body:
        out.append("분기 조건이 v_floor_stack 과 다름")
    if not re.search(r"\bwhere u\.pnu = v_pnu\b", body):
        out.append("땅 조건이 다름")
    if not re.search(r"\bgroup by u\.floor_no, u\.cat_l_cd, u\.cat_l_nm\b", body):
        out.append("층·대분류로 묶지 않음")
    if re.search(r"floor_no is not null|coalesce\(\s*u\.floor_no", body):
        out.append("층 null 을 걸러 내거나 다른 값으로 바꿈")
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
        changed = mig.replace("set search_path = public\nas $$", "as $$", 1)
        assert changed != mig
        assert fn_block(changed, FN) != fn_block(schema, FN)

    def test_mirror_detector_sees_a_comment_only_change(self, mig, schema):
        changed = mig.replace("나가는 것은 층·대분류·개수뿐이다", "나가는 것은 개수뿐이다", 1)
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
        extra = ("\ncreate or replace function list_floor_industry(p_pnu text, p_ym text default null)\n"
                 "returns int language sql as $$ select 1 $$;\n")
        assert definitions(mig + extra, FN) == 2
        extra2 = "\n  CREATE FUNCTION List_Floor_Industry (p text) returns int language sql as $$ select 1 $$;\n"
        assert definitions(mig + extra2, FN) == 2


class TestHeads:
    def test_public_head(self, mig, schema):
        for sql in (mig, schema):
            assert head_problems(fn_block(sql, FN), PUBLIC_HEAD) == []

    def test_api_twin_head_and_body(self, mig, schema):
        for sql in (mig, schema):
            block = fn_block(sql, API_FN)
            assert head_problems(block, API_HEAD) == []
            assert body_of(block).strip() == "select * from public.list_floor_industry(p_pnu)"

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

    def test_returns_the_four_columns(self, mig):
        """두 함수가 같은 칸 넷을 같은 형으로 돌려준다(쌍둥이가 다르면 화면 검증기가 응답을 버린다)."""
        for name in (FN, API_FN):
            assert RETURNS in head_of(fn_block(mig, name)), name


class TestBody:
    def test_takes_the_pnu_as_char19(self, mig):
        assert char19_problems(fn_block(mig, FN)) == []

    @pytest.mark.parametrize("old, new", (
        ("v_pnu char(19) := p_pnu;", "v_pnu text := p_pnu;"),
        ("where u.pnu = v_pnu", "where u.pnu = p_pnu"),
    ))
    def test_char19_detector_catches_variants(self, mig, old, new):
        block = fn_block(mig, FN)
        assert old in block
        assert char19_problems(block.replace(old, new, 1))

    def test_counts_the_same_rows_as_the_floor_list(self, mig, schema):
        """띠 합 = 층 줄의 「점포 N」 — 분기·땅·층 조건이 v_floor_stack 의 store_cnt 셈과 같다."""
        assert same_rows_problems(body_of(fn_block(mig, FN)), view_store_cnt_lateral(schema)) == []

    @pytest.mark.parametrize("old, new", (
        # 분기를 따로 고른다(흔한 꼴) — 표지가 아니라 가장 큰 분기
        ("u.snapshot_ym = (select r.published_ym from snapshot_release r)",
         "u.snapshot_ym = (select max(x.snapshot_ym) from unit_business x)"),
        # 표지의 다른 칸(변형 꼴) — 다 들어온 분기(loaded_ym)
        ("(select r.published_ym from snapshot_release r)", "(select r.loaded_ym from snapshot_release r)"),
        # 층 null 을 걸러 낸다 — 'na' 묶음이 사라진다
        ("       and u.snapshot_ym", "       and u.floor_no is not null\n       and u.snapshot_ym"),
        # 대분류로 안 묶는다
        ("group by u.floor_no, u.cat_l_cd, u.cat_l_nm", "group by u.floor_no"),
    ))
    def test_same_rows_detector_catches_variants(self, mig, schema, old, new):
        block = fn_block(mig, FN)
        assert old in block
        assert same_rows_problems(body_of(block.replace(old, new, 1)), view_store_cnt_lateral(schema))

    def test_reads_only_unit_business_and_release(self, mig):
        body = statements(body_of(fn_block(mig, FN)))
        assert re.findall(r"(?i)\bfrom\s+(\w+)", body) == ["unit_business", "snapshot_release"]

    def test_no_store_names_or_small_categories_leave(self, mig):
        """상호·소분류·biz_no·좌표는 한 글자도 안 나간다(대분류 개수뿐)."""
        body = statements(body_of(fn_block(mig, FN)))
        for col in ("biz_name", "biz_no", "cat_s_", "cat_m_", "lat", "lng", "geom"):
            assert not re.search(r"\b" + col, body), col


class TestPermissions:
    def test_only_the_api_twin_is_granted(self, mig, schema):
        assert grant_targets(mig) == [API_FN]
        assert [t for t in grant_targets(schema) if "floor_industry" in t] == [API_FN]

    @pytest.mark.parametrize("bad", (
        "grant execute on function list_floor_industry(text) to anon;",
        "grant all on function public.list_floor_industry(text) to anon;",
        "  GRANT EXECUTE\n  ON FUNCTION List_Floor_Industry ( text ) TO authenticated;",
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
        assert (code.index("revoke all on function api.list_floor_industry(")
                < code.index("grant execute on function api.list_floor_industry("))

    def test_allowlist_has_the_api_twin_only(self):
        assert API_FN in post_load.ANON_CALLABLE_ALLOWLIST
        assert FN not in post_load.ANON_CALLABLE_ALLOWLIST
        assert "public." + FN not in post_load.ANON_CALLABLE_ALLOWLIST

    def test_allowlist_total_is_36(self):
        """읽기 4 + 부르기 32 = `--check` 총계 36(이 마이그레이션이 30 → 31 · 결정 0038 §4 의 「지금 32」는 0041 로 둘이 빠지기 전 수 ·
        2026-10-24b V5 임대 8분기 흐름이 31 → 32 · 2026-10-25a V6 개업·폐업 전부 보기가 32 → 33 · 2026-10-29a 결정 0044 대전 동네 폐업이 33 → 34 ·
        2026-10-31a 결정 0045 서울 4종이 34 → 36 — 넷 다 이 마이그레이션 몫 아님)."""
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
        assert "되돌리기" in mig and "drop function api.list_floor_industry(text)" in mig

    def test_no_banned_words(self, mig):
        for w in ("적정가격", "적정가", "감정가", "평가액"):
            assert w not in mig


# ── ② 실행 가드 (로컬 PostgreSQL 이 있을 때만) ──────────────────────────────

SHIM = """
create schema api;
create table snapshot_release (loaded_ym char(6), published_ym char(6));
create table unit_business (
  snapshot_ym char(6) not null,
  biz_no text not null,
  pnu char(19),
  floor_no smallint,
  biz_name text,
  cat_l_cd char(2),
  cat_l_nm text,
  cat_s_nm text,
  floor_basement_unknown boolean,
  primary key (snapshot_ym, biz_no)
);
"""

PNU = "1168010100107370000"
OTHER = "1168010100107380000"
EMPTY = "1168010100107390000"

# (분기, 번호, 땅, 층, 대분류 코드, 대분류 이름, 지하 층 모름)
ROWS = [
    # 보여 주는 분기 202606 — 이 땅
    ("202606", "a1", PNU, 1, "I2", "음식", None),
    ("202606", "a2", PNU, 1, "I2", "음식", None),
    ("202606", "a3", PNU, 1, "G2", "소매", None),
    ("202606", "a4", PNU, 2, "M1", "과학·기술", None),
    ("202606", "a5", PNU, -1, "I2", "음식", None),
    ("202606", "a6", PNU, 7, "P1", "교육", None),        # 층 목록에 없는 층(화면이 「자리 없는 점포」로)
    ("202606", "a7", PNU, None, "I2", "음식", None),     # 층 모름
    ("202606", "a8", PNU, None, "S2", "수리·개인", None),
    ("202606", "a9", PNU, None, "I2", "음식", True),     # 숫자 없는 지하('지') — 층 번호는 null 그대로라 na 묶음
    ("202606", "a10", PNU, 2, None, None, None),         # 대분류 없음 — 그 줄도 센다(합이 어긋나지 않게)
    # 다른 분기 — 세지 않는다(다 들어왔지만 아직 안 보여 주는 분기)
    ("202609", "b1", PNU, 1, "I2", "음식", False),
    ("202609", "b2", PNU, 3, "G2", "소매", False),
    # 다른 땅 — 세지 않는다
    ("202606", "c1", OTHER, 1, "I2", "음식", None),
]

# 이 건물의 층 목록(층별개요) — 3층은 목록에 있지만 이 분기 점포 0 · 7층은 목록에 없다.
STACK_FLOORS = (3, 2, 1, -1)


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
    """흉내 판 위에 마이그레이션의 두 함수(정본과 같은 글)를 그대로 넣는다."""
    mig = read(MIGRATION)
    c = pg.cursor()
    c.execute("drop schema if exists api cascade; drop schema if exists public cascade; create schema public;")
    c.execute(SHIM)
    c.execute("insert into snapshot_release values ('202609', '202606')")
    c.executemany(
        "insert into unit_business (snapshot_ym, biz_no, pnu, floor_no, cat_l_cd, cat_l_nm, floor_basement_unknown) "
        "values (%s, %s, %s, %s, %s, %s, %s)", ROWS)
    c.execute(fn_block(mig, FN))
    c.execute(fn_block(mig, API_FN))
    return c


def _rows(cur, fn, pnu):
    cur.execute("select floor_no, cat_l_cd, cat_l_nm, store_cnt from {}(%s)".format(fn), (pnu,))
    return cur.fetchall()


def _view_store_cnt(cur, pnu, floors):
    """정본 v_floor_stack 의 store_cnt 셈을 **글 그대로** 같은 흉내 판에서 돌린다(층 목록 줄마다)."""
    lateral = view_store_cnt_lateral(read(SCHEMA))
    values = ", ".join("(%s::char(19), %s::smallint)" for _ in floors)
    args = []
    for f in floors:
        args += [pnu, f]
    cur.execute("select s.floor_no, st.store_cnt from (values {}) s(pnu, floor_no) {}".format(values, lateral), args)
    return dict(cur.fetchall())


class TestRealRun:
    @pytest.mark.parametrize("fn", (FN, API_FN))
    def test_counts_by_floor_and_category(self, cur, fn):
        assert _rows(cur, fn, PNU) == [
            (7, "P1", "교육", 1),
            (2, "M1", "과학·기술", 1),
            (2, None, None, 1),
            (1, "G2", "소매", 1),
            (1, "I2", "음식", 2),
            (-1, "I2", "음식", 1),
            (None, "I2", "음식", 2),
            (None, "S2", "수리·개인", 1),
        ]

    def test_band_sum_equals_the_floor_list_store_cnt(self, cur):
        """띠 합 = 그 층 store_cnt — v_floor_stack 의 셈(정본 글 그대로)과 층마다 견준다(점포 0 층 포함)."""
        view = _view_store_cnt(cur, PNU, STACK_FLOORS)
        band = {}
        for floor_no, _cd, _nm, n in _rows(cur, API_FN, PNU):
            if floor_no is not None:
                band[floor_no] = band.get(floor_no, 0) + n
        for f in STACK_FLOORS:
            assert band.get(f, 0) == view[f], f
        assert view[3] == 0 and 3 not in band

    def test_na_bucket_holds_every_store_without_a_floor(self, cur):
        """층 null 은 한 묶음(na) — 숫자 없는 지하('지')도 층 번호가 null 이라 여기 든다(층 목록 카드는 2-2c 범위 밖)."""
        na = sum(n for floor_no, _cd, _nm, n in _rows(cur, API_FN, PNU) if floor_no is None)
        assert na == 3

    def test_other_quarter_and_other_land_are_not_counted(self, cur):
        total = sum(r[3] for r in _rows(cur, API_FN, PNU))
        assert total == 10
        assert _rows(cur, API_FN, OTHER) == [(1, "I2", "음식", 1)]

    def test_empty_land_is_no_row(self, cur):
        assert _rows(cur, API_FN, EMPTY) == []

    def test_twin_works_with_an_empty_search_path(self, cur):
        cur.execute("set search_path to ''")
        try:
            assert len(_rows(cur, API_FN, PNU)) == 8
        finally:
            cur.execute("reset search_path")

    def test_return_types(self, cur):
        cur.execute("select pg_typeof(floor_no)::text, pg_typeof(cat_l_cd)::text, pg_typeof(cat_l_nm)::text, "
                    "pg_typeof(store_cnt)::text from api.list_floor_industry(%s) limit 1", (PNU,))
        assert cur.fetchone() == ("smallint", "text", "text", "integer")

    def test_one_signature_per_name(self, cur):
        """이름당 pg_proc 1 — 같은 이름 둘이면 PostgREST 가 못 고른다(PGRST203)."""
        cur.execute("select n.nspname, count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                    "where p.proname = %s group by 1 order by 1", (FN,))
        assert cur.fetchall() == [("api", 1), ("public", 1)]
