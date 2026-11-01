# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-25a(개업·폐업 「전부 보기」 · 결정 0038 H · V6)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙여 넣기 전에는 아무도 모르는 종류의 실수**다:

  1) 마이그레이션과 정본(schema.sql)의 글자가 갈린다 → 새 환경만 다른 모양으로 만들어진다. `create or replace` 는
     머리 속성을 새 정의로 덮어쓰고 드리프트 가드는 `$$` 안 본문만 본다 — 머리·comment 까지 글자로 대조한다
     (CLAUDE.md ⛔ 2026-10-01a · 본보기 tests/test_rent_stat_history_migration.py).
  2) **창 말고 다른 것이 갈린다** — 화면은 두 함수의 응답을 같은 모양 검사기로 받고 같은 그림으로 그린다. 상권 찾기 ·
     status 다섯 · 합산 · 표본 30 · 상위 10 · 정렬 가운데 하나라도 갈리면 「전부 보기」를 누르는 순간 같은 상권의
     숫자가 다른 규칙으로 바뀐다(에러 없이). → 새 본문 = 정본 list_district_openclose 본문 + 정한 갈래 넷(주석 밖 글자 그대로).
  3) total_quarters 가 표 전체 분기 수가 아니다(창 수 8 · null 줄까지 센 수) → 단추 「전부 보기 (N분기)」가 거짓말을 한다.
  4) 옛 함수 list_district_openclose 가 바뀐다 / 같은 이름에 서명이 둘 → PGRST203 로 운영 카드가 즉시 사라진다(결정 0038 §7).
  5) public 원본에 grant 를 준다 → security definer 원본이 밖에 열린다(🚪 grant 는 api 쌍둥이에만).

② 실행 가드(로컬 PostgreSQL 이 있을 때만)는 흉내 판(PostGIS 없음 — st_contains 를 글자 판정으로 흉내 낸다) 위에서
   옛 함수(정본 글)와 새 함수(마이그레이션 글)를 같이 만들고 불러 본다. CI 에는 PostgreSQL 이 없어 건너뛴다.
"""

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
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-25a_district_openclose_all.sql")
OLD_MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-05b_district_openclose.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

FN = "list_district_openclose_all"
API_FN = "api.list_district_openclose_all"
OLD_FN = "list_district_openclose"
SIG = "(text)"

PUBLIC_HEAD = ("language sql", "stable", "security definer", "set search_path = public")
API_HEAD = ("language sql", "stable", "security definer", "set search_path = ''")

# 새 본문 = 옛 본문(주석 밖 글) + 이 갈래 넷. 이 표 밖의 차이는 전부 '창 말고 다른 것이 갈렸다'다.
CODE_CHANGES = (
    # ① 창의 크기 상수를 없앤다 — 표 전체 분기 전부.
    ("select 30 as min_similr, 8 as n_quarters", "select 30 as min_similr"),
    # ② 재귀를 더 옛 분기가 없을 때(max 가 null)까지.
    ("    from win w cross join const c\n    where w.n < c.n_quarters and w.quarter is not null",
     "    from win w\n    where w.quarter is not null"),
    # ③ 창의 개수 — null 줄은 count(칸) 이 안 센다.
    ("'[]'::jsonb) as window_quarters\n    from win w",
     "'[]'::jsonb) as window_quarters,\n           count(w.quarter)::int as total_quarters\n    from win w"),
    # ④ 맨 끝 칸으로 내보낸다.
    ("wq.window_quarters\n  from rows_out ro cross join wq",
     "wq.window_quarters, wq.total_quarters\n  from rows_out ro cross join wq"),
)

RETURNS = (
    "returns table (\n"
    "  status           text,\n"
    "  district_id      text,\n"
    "  district_nm      text,\n"
    "  district_type    text,\n"
    "  latest_quarter   text,\n"
    "  quarters         jsonb,\n"
    "  industries       jsonb,\n"
    "  other_industries jsonb,\n"
    "  window_quarters  jsonb,\n"
    "  total_quarters   int\n"
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
    """`create or replace function <name>(` 부터 `$$;` 까지 — 머리 + 본문 통째(줄머리 고정 · `_all` 과 안 섞이게 `(` 까지)."""
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
    """`grant … on function <대상>(` 의 대상 이름 전부(소문자 · 스키마 그대로). 가드 본체와 양성 대조가 같이 쓴다.

    ⚠️ 못 보는 것: 인자 괄호 없는 `on function <이름> to …` · 따옴표 이름 · 일괄 grant(`all functions in schema`).
    """
    found = []
    for stmt in re.findall(r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*?"
                           r"\bon\s+(?:function|routine)\b([^;]*)", statements(sql)):
        found += re.findall(r"(?i)(?<![\w.])((?:\w+\.)?\w+)\s*\(", stmt)
    return [t.lower() for t in found]


def code_of(body):
    """본문의 주석 밖 글 — 줄 끝 `--` 주석을 걷고, 비게 된 줄을 빼고, 줄 끝 공백을 걷는다(줄 안 글자는 그대로)."""
    out = []
    for ln in body.splitlines():
        ln = re.sub(r"--.*$", "", ln).rstrip()
        if ln:
            out.append(ln)
    return "\n".join(out)


def derived_problems(new_body, old_body):
    """새 본문이 '옛 본문 + CODE_CHANGES' 와 주석 밖 글자로 같은가 — 어긋난 까닭 목록(비면 정상).

    ⓘ 가드 본체와 양성 대조가 이 **같은 함수**를 지난다.
    ⚠️ 못 보는 것: 주석 안의 글(뜻 없음) · 옛 본문 쪽이 바뀐 꼴(그땐 새 본문도 같이 바뀌어야 초록 — 의도된 일이다 ·
       옛 본문의 글자 고정은 test_old_function_is_the_2026_10_05b_text 가 따로 본다).
    """
    want = code_of(old_body)
    bad = []
    for a, b in CODE_CHANGES:
        if want.count(a) != 1:
            bad.append("옛 본문에서 갈래 앞글을 한 번 찾지 못함: " + a.splitlines()[0])
            continue
        want = want.replace(a, b, 1)
    got = code_of(new_body)
    if got != want:
        w, g = want.splitlines(), got.splitlines()
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
        changed = mig.replace("나가는 것은 상권 이름·종류와 서울시 공표 수·비율뿐이다", "나가는 것은 수뿐이다", 1)
        assert changed != mig
        assert fn_comment(changed, FN) != fn_comment(schema, FN)


class TestOldFunctionUntouched:
    def test_old_function_is_the_2026_10_05b_text(self, schema):
        """옛 함수는 머리·본문·comment 까지 2026-10-05b 의 글 그대로다(창 8 · 칸 아홉) — 운영 카드가 그 응답을 쓴다."""
        old_mig = read(OLD_MIGRATION)
        assert fn_block(schema, OLD_FN) == fn_block(old_mig, OLD_FN)
        assert fn_block(schema, "api." + OLD_FN) == fn_block(old_mig, "api." + OLD_FN)
        assert fn_comment(schema, OLD_FN) == fn_comment(old_mig, OLD_FN)

    def test_this_migration_does_not_touch_the_old_name(self, mig):
        """정의·삭제·권한 변경 0 — `(` 까지 봐서 `_all` 과 섞지 않는다."""
        code = statements(mig)
        assert definitions(mig, OLD_FN) == 0 and definitions(mig, "api." + OLD_FN) == 0
        assert not re.search(r"(?i)\b(drop|revoke|grant|alter|comment)\b[^;]*\blist_district_openclose\s*\(", code)

    def test_detector_sees_a_redefined_old_function(self, mig):
        """양성 대조 — 옛 이름에 인자를 하나 더 붙인 정의(흔한 꼴 · PGRST203 의 원인)와 들여쓴 대문자 꼴이 센다."""
        extra = ("\ncreate or replace function list_district_openclose(p_pnu text, p_all boolean default false)\n"
                 "returns int language sql as $$ select 1 $$;\n")
        assert definitions(mig + extra, OLD_FN) == 1
        extra2 = "\n  CREATE FUNCTION List_District_Openclose (p text) returns int language sql as $$ select 1 $$;\n"
        assert definitions(mig + extra2, OLD_FN) == 1


class TestOneSignature:
    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_each_name_is_defined_once(self, mig, schema, name):
        """같은 이름 둘(기본값 인자를 더한 판 등)이면 PostgREST 가 `{p_pnu}` 를 못 고른다(PGRST203)."""
        assert definitions(mig, name) == 1
        assert definitions(schema, name) == 1

    def test_detector_counts_a_second_signature(self, mig):
        extra = ("\ncreate or replace function list_district_openclose_all(p_pnu text, p_n int default 8)\n"
                 "returns int language sql as $$ select 1 $$;\n")
        assert definitions(mig + extra, FN) == 2


class TestHeads:
    def test_public_head(self, mig, schema):
        for sql in (mig, schema):
            assert head_problems(fn_block(sql, FN), PUBLIC_HEAD) == []

    def test_api_twin_head_and_body(self, mig, schema):
        for sql in (mig, schema):
            block = fn_block(sql, API_FN)
            assert head_problems(block, API_HEAD) == []
            assert body_of(block).strip() == "select * from public.list_district_openclose_all(p_pnu)"

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

    def test_returns_the_old_nine_columns_plus_total_quarters(self, mig, schema):
        """두 함수가 같은 칸 열 개 — 옛 함수의 아홉 칸 그대로(같은 순서·같은 형) + 맨 끝 total_quarters int."""
        old_head = head_of(fn_block(schema, OLD_FN))
        want = old_head.replace("  window_quarters  jsonb\n)\n", "  window_quarters  jsonb,\n  total_quarters   int\n)\n", 1)
        want = want.replace("function list_district_openclose(", "function list_district_openclose_all(", 1)
        assert want == head_of(fn_block(mig, FN))
        for name in (FN, API_FN):
            assert RETURNS in head_of(fn_block(mig, name)), name


class TestOnlyTheWindowDiffers:
    def test_body_is_the_old_body_plus_the_window_changes(self, mig, schema):
        assert derived_problems(body_of(fn_block(mig, FN)), body_of(fn_block(schema, OLD_FN))) == []

    @pytest.mark.parametrize("old, new", (
        # 표본 기준을 바꾼다(흔한 꼴)
        ("select 30 as min_similr", "select 20 as min_similr"),
        # 창을 상권마다로(변형 꼴 — 자료가 끊긴 상권이 옛 숫자를 최근처럼)
        ("    select max(o.quarter), 1 from district_openclose o\n",
         "    select max(o.quarter), 1 from district_openclose o where o.district_id in (select district_id from hit)\n"),
        # 창 크기를 다시 박는다
        ("    where w.quarter is not null\n  ),", "    where w.n < 22 and w.quarter is not null\n  ),"),
        # total_quarters 가 null 줄까지 센다
        ("count(w.quarter)::int as total_quarters", "count(*)::int as total_quarters"),
        # total_quarters 를 창 수 8 로
        ("count(w.quarter)::int as total_quarters", "8 as total_quarters"),
        # 상위 10 을 바꾼다
        ("r.rn <= 10", "r.rn <= 12"),
        # 상권 술어를 바꾼다
        ("and st_contains(d.geom, me.geom)", "and st_intersects(d.geom, me.geom)"),
        # 정렬을 바꾼다
        ("order by ro.sort_area asc, ro.district_id;", "order by ro.district_id;"),
    ))
    def test_derived_detector_catches_variants(self, mig, schema, old, new):
        body = body_of(fn_block(mig, FN))
        assert old in body, old
        assert derived_problems(body.replace(old, new, 1), body_of(fn_block(schema, OLD_FN)))

    def test_derived_detector_ignores_comment_only_changes(self, mig, schema):
        body = body_of(fn_block(mig, FN))
        changed = body.replace("-- 좁은 상권이 더 구체적인 설명이라 먼저 온다", "-- 좁은 상권 먼저", 1)
        assert changed != body
        assert derived_problems(changed, body_of(fn_block(schema, OLD_FN))) == []


class TestPermissions:
    def test_only_the_api_twin_is_granted(self, mig, schema):
        assert grant_targets(mig) == [API_FN]
        assert [t for t in grant_targets(schema) if t.endswith("openclose_all")] == [API_FN]

    @pytest.mark.parametrize("bad", (
        "grant execute on function list_district_openclose_all(text) to anon;",
        "grant all on function public.list_district_openclose_all(text) to anon;",
        "  GRANT EXECUTE\n  ON FUNCTION List_District_Openclose_All ( text ) TO authenticated;",
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
        assert (code.index("revoke all on function api.list_district_openclose_all(")
                < code.index("grant execute on function api.list_district_openclose_all("))

    def test_allowlist_has_the_api_twin_only(self):
        assert API_FN in post_load.ANON_CALLABLE_ALLOWLIST
        assert FN not in post_load.ANON_CALLABLE_ALLOWLIST
        assert "public." + FN not in post_load.ANON_CALLABLE_ALLOWLIST

    def test_allowlist_total_is_36(self):
        """읽기 4 + 부르기 32 = `--check` 총계 36(2026-10-24b 의 32 에 이 함수 하나 → 33 · 2026-10-29a 결정 0044 대전 동네 폐업이 33 → 34 ·
        2026-10-31a 결정 0045 서울 4종이 34 → 36 — 둘 다 이 마이그레이션 몫 아님)."""
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
        assert "되돌리기" in mig and "drop function api.list_district_openclose_all(text)" in mig

    def test_no_banned_words(self, mig):
        for w in ("적정가격", "적정가", "감정가", "평가액"):
            assert w not in mig


# ── ② 실행 가드 (로컬 PostgreSQL 이 있을 때만) ──────────────────────────────

SHIM = """
create schema api;
create table parcel (pnu char(19) primary key, geom text);
create table district (district_id text primary key, district_nm text, district_type text,
                       sigungu_code char(5), geom text, area_m2 numeric(14,2));
-- 흉내 낸 공간 판정: 점 이름이 도형 글자 안에 '|이름|' 꼴로 들어 있으면 담긴 것(형제 test_district_openclose_migration 과 같은 꼴).
create function st_contains(poly text, pt text) returns boolean language sql immutable
  as 'select position(''|'' || pt || ''|'' in poly) > 0';
"""

SEOUL_A = "1168010100100010000"    # 좁은 상권 D1 과 넓은 상권 D2 둘 다에 든다
SEOUL_B = "1168010100100040000"    # 상권 D4(8분기 창 안 옛 분기만) · D5(8분기 창 밖 분기만)
SEOUL_OUT = "1168010100100020000"  # 서울인데 상권 밖
SEOUL_NOGEOM = "1168010100100030000"
DJ = "3017010100100010000"         # 대전 — 대전 상권 안

FIXTURE = """
insert into parcel values ('{sa}', 'PA'), ('{so}', 'PO'), ('{sn}', null), ('{dj}', 'PD'), ('{sb}', 'PB');
insert into district values
  ('D1', '좁은 상권', '골목상권', '11680', '|PA|', 1000),
  ('D2', '넓은 상권', '발달상권', '11680', '|PA|PX|', 9000),
  ('DJ1', '대전 상권', '발달상권', '30170', '|PD|', 500),
  ('D4', '최신 분기에서 빠진 상권', '골목상권', '11680', '|PB|', 100),
  ('D5', '8분기 창 밖 분기만 가진 상권', '골목상권', '11680', '|PB|', 200);
""".format(sa=SEOUL_A, so=SEOUL_OUT, sn=SEOUL_NOGEOM, dj=DJ, sb=SEOUL_B)

# D1 = 11분기(20234~20262) × 업종 12개 · D5 = 20231 하나 → 표 전체 분기 12개 · 8분기 창 = 20243~20262.
D1_QUARTERS = ["20234", "20241", "20242", "20243", "20244", "20251", "20252", "20253", "20254", "20261", "20262"]
ALL_QUARTERS = sorted(D1_QUARTERS + ["20231"], reverse=True)


def _openclose_rows():
    rows = []
    for k, q in enumerate(D1_QUARTERS):
        for i in range(12):
            similr = 20 - i + k          # 분기마다 조금씩 늘어 비율이 분기마다 다르다
            opb, clo = (1 + k % 3, 2) if i in (0, 1) else (0, 0)
            rows.append((q, "D1", "CS{:03d}".format(i), "업종{}".format(i), similr - 1, similr,
                         round(opb * 100.0 / similr), opb, round(clo * 100.0 / similr), clo, 1))
    return rows


def _table_stmt():
    m = re.search(r"(?ms)^create table if not exists district_openclose \((.*?)\n\);", read(OLD_MIGRATION))
    assert m, "create table district_openclose 를 못 찾았습니다"
    return m.group(0)


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


def _load(conn, new_fn_sql=None):
    """흉내 판 위에 표 + 옛 함수(정본 글) + 새 함수 둘(마이그레이션 글 · 또는 주어진 변이)을 넣고 픽스처를 채운다."""
    mig, schema = read(MIGRATION), read(SCHEMA)
    c = conn.cursor()
    c.execute("drop schema if exists api cascade; drop schema if exists public cascade; create schema public;")
    c.execute(SHIM)
    c.execute(_table_stmt())
    c.execute(fn_block(schema, OLD_FN))
    c.execute(new_fn_sql or fn_block(mig, FN))
    c.execute(fn_block(mig, API_FN))
    c.execute(FIXTURE)
    c.executemany("insert into district_openclose (quarter, district_id, svc_induty_cd, "
                  "svc_induty_cd_nm, stor_co, similr_induty_stor_co, opbiz_rt, opbiz_stor_co, "
                  "clsbiz_rt, clsbiz_stor_co, frc_stor_co) values "
                  "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", _openclose_rows())
    # 표본 < 30 상권: D2 에 한 분기 한 업종만(similr 5)
    c.execute("insert into district_openclose values "
              "('20262','D2','CS900','작은업종',4,5,20,1,0,0,1,null,now())")
    # D4 는 8분기 창 안 20261 에만 · D5 는 8분기 창 밖 20231 에만 행이 있다.
    c.execute("insert into district_openclose values "
              "('20261','D4','CS100','업종',40,40,5,2,3,1,0,null,now()),"
              "('20231','D5','CS100','업종',40,40,5,2,3,1,0,null,now())")
    return c


COLS = ("status", "district_id", "district_nm", "district_type", "latest_quarter", "quarters", "industries",
        "other_industries", "window_quarters")


def _call(cur, fn, pnu, extra=""):
    cur.execute("select {}{} from {}(%s)".format(", ".join(COLS), extra, fn), (pnu,))
    return [dict(zip(COLS + (("total_quarters",) if extra else ()), r)) for r in cur.fetchall()]


@pytest.fixture(scope="module")
def cur(pg):
    return _load(pg)


class TestRealRun:
    @pytest.mark.parametrize("pnu", (SEOUL_A, SEOUL_B, SEOUL_OUT, SEOUL_NOGEOM, DJ))
    def test_window_is_every_quarter_and_total_is_its_count_on_every_row(self, cur, pnu):
        rows = _call(cur, API_FN, pnu, ", total_quarters")
        assert rows
        for r in rows:
            assert r["window_quarters"] == ALL_QUARTERS
            assert r["total_quarters"] == len(ALL_QUARTERS) == 12

    def test_total_quarters_is_an_integer(self, cur):
        cur.execute("select pg_typeof(total_quarters)::text from api.list_district_openclose_all(%s) limit 1", (SEOUL_A,))
        assert cur.fetchone() == ("integer",)

    def test_district_quarters_are_its_own_without_filling(self, cur):
        """D1 은 11분기만 가졌다 — 표 전체 12분기 가운데 빠진 20231 은 빠진 채(0 으로 안 메운다)."""
        d1 = _call(cur, API_FN, SEOUL_A)[0]
        assert d1["district_id"] == "D1" and d1["latest_quarter"] == "20262"
        assert [q["quarter"] for q in d1["quarters"]] == sorted(D1_QUARTERS, reverse=True)

    def test_no_data_in_eight_becomes_ok_with_its_old_latest(self, cur):
        """D5(20231 하나뿐) — 8분기 창에서는 no_data, 전부 창에서는 ok · latest_quarter 20231(화면이 '…까지' 를 적는다)."""
        old = {r["district_id"]: r for r in _call(cur, OLD_FN, SEOUL_B)}
        new = {r["district_id"]: r for r in _call(cur, API_FN, SEOUL_B)}
        assert old["D5"]["status"] == "no_data" and old["D5"]["latest_quarter"] is None
        assert new["D5"]["status"] == "ok" and new["D5"]["latest_quarter"] == "20231"
        assert [q["quarter"] for q in new["D5"]["quarters"]] == ["20231"]

    @pytest.mark.parametrize("pnu", (SEOUL_A, SEOUL_B, SEOUL_OUT, SEOUL_NOGEOM, DJ))
    def test_same_shape_as_the_old_function_inside_its_window(self, cur, pnu):
        """옛 창 안에서는 같은 답이다 — 상태·상권·순서·이름 · ok 상권의 최신 분기·업종 표·그 밖 · 분기 합(옛 창으로 자른 것)."""
        old, new = _call(cur, OLD_FN, pnu), _call(cur, API_FN, pnu)
        assert [r["district_id"] for r in old] == [r["district_id"] for r in new]
        for o, n in zip(old, new):
            assert (o["district_nm"], o["district_type"]) == (n["district_nm"], n["district_type"])
            if o["status"] != "no_data":      # 옛 창의 no_data 는 전부 창에서 ok 가 될 수 있다(D5) — 나머지 상태는 같다
                assert o["status"] == n["status"]
            if o["status"] != "ok":
                continue
            assert (o["latest_quarter"], o["industries"], o["other_industries"]) == \
                (n["latest_quarter"], n["industries"], n["other_industries"])
            win = set(o["window_quarters"])
            assert o["quarters"] == [q for q in n["quarters"] if q["quarter"] in win]

    def test_small_sample_still_hides_rates(self, cur):
        d2 = _call(cur, API_FN, SEOUL_A)[1]
        assert d2["district_id"] == "D2"
        assert d2["quarters"][0]["opbiz_rt"] is None and d2["quarters"][0]["similr_induty_stor_co"] == 5

    def test_empty_table_gives_an_empty_window_and_zero(self, pg):
        c = _load(pg)
        try:
            c.execute("delete from district_openclose")
            rows = _call(c, API_FN, SEOUL_A, ", total_quarters")
            assert [(r["status"], r["window_quarters"], r["total_quarters"]) for r in rows] == \
                [("no_data", [], 0), ("no_data", [], 0)]
        finally:
            _load(pg)

    def test_twin_works_with_an_empty_search_path(self, cur):
        cur.execute("set search_path to ''")
        try:
            assert len(_call(cur, API_FN, SEOUL_A)) == 2
        finally:
            cur.execute("reset search_path")

    def test_one_signature_per_name(self, cur):
        """이름당 pg_proc 1 — 같은 이름 둘이면 PostgREST 가 못 고른다(PGRST203)."""
        cur.execute("select n.nspname, count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                    "where p.proname in (%s, %s) group by p.proname, 1 order by p.proname, 1", (FN, OLD_FN))
        assert cur.fetchall() == [("public", 1), ("api", 1), ("public", 1)]

    def test_answer_is_json_serialisable_like_the_screen_reads_it(self, cur):
        """PostgREST 가 내보내는 꼴(jsonb 칸 + int 칸)로 한 번 굴려 본다 — 화면 모양 검사기가 받는 모양."""
        cur.execute("select json_agg(t) from api.list_district_openclose_all(%s) t", (SEOUL_B,))
        rows = cur.fetchone()[0]
        assert json.loads(json.dumps(rows))[0]["total_quarters"] == 12


class TestRealRunMutations:
    """변이가 실제로 값을 바꾸는가 — 위 실행 가드가 그 변이를 빨강으로 잡는다는 근거."""

    def _total(self, pg, old, new):
        fn = fn_block(read(MIGRATION), FN)
        assert old in fn
        c = _load(pg, fn.replace(old, new, 1))
        try:
            return {r["total_quarters"] for r in _call(c, FN, SEOUL_A, ", total_quarters")}
        finally:
            _load(pg)

    def test_counting_the_null_row_is_off_by_one(self, pg):
        assert self._total(pg, "count(w.quarter)::int", "count(*)::int") == {13}

    def test_eight_window_total_is_eight(self, pg):
        assert self._total(pg, "    where w.quarter is not null\n  ),",
                           "    where w.n < 8 and w.quarter is not null\n  ),") == {8}
