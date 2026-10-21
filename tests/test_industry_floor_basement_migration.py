# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-14b·14c(숫자 없는 지하 '지'를 업종별 층 줄의 지하 칸에 · 물결 2-2c PR②)의 불변식.

무엇을 막나
-----------
  1) 정본(schema.sql)과 14b 의 글자가 갈린다 — `create or replace` 는 머리 속성(stable·security definer·
     search_path·immutable)을 새 정의로 덮어쓰는데 드리프트 가드는 `$$` 안 본문만 본다. 그래서 머리·comment·
     요약표 정의까지 여기서 글자로 대조한다(본보기 = test_data_freshness_migration.py).
  2) 14b 를 엉뚱한 때 돌린다 — 맨 앞 관문 DO 가 ① 칸(14a) ② 점포 색인 include(14c) ③ 표지 loaded = published
     셋을 본다. 셋째가 빠지면 적재 뒤·post_load 전에 돌린 날 층 줄 하나만 새 분기를 말한다(🟠5).
  3) 요약표 바꿔 끼우기에서 색인 이름을 안 되돌린다 → post_load --check 정본 색인 점검 [사고](🟡12).
  4) 옛 한 인자 판이 남는다 → 같은 이름 둘이라 --check 함수 대조 [사고](🟡11).
  5) 층 묶음 함수가 칸 false·NULL 인 층 미상 행까지 'b' 로 보낸다 → 지하 칸이 부푼다.
  6) 14c 의 include 차례가 정본과 다르다 → --check 정본 색인 점검 [사고].

로컬 PostgreSQL 이 있으면 14b 원문을 흉내 판(09b 를 그대로 적용한 판) 위에서 실제로 돌린다 — 없으면 건너뛴다
(CI 는 글자 가드만 · 형제 test_industry_floor_migration.py 와 같은 꼴).

ⓘ 탐지는 이 파일 안의 작은 함수로 빼서 가드 본체와 양성 대조가 **같은 함수**를 지난다(CLAUDE.md ⛔).
ⓘ 도우미는 형제 시험(test_industry_floor_migration.py · test_ub_basement_unknown_migration.py)에서 **복사**해 왔다.
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
MIG_DIR = os.path.join(ROOT, "supabase", "migrations")
B = os.path.join(MIG_DIR, "2026-10-14b_industry_floor_basement.sql")
C = os.path.join(MIG_DIR, "2026-10-14c_ub_pnu_cat_include_basement.sql")
OLD = os.path.join(MIG_DIR, "2026-10-09b_industry_floor.sql")
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
COL = "floor_basement_unknown"
COUNTED = "basement_unknown_counted"
UB_INCLUDE = ["cat_l_cd", "cat_l_nm", "cat_m_cd", "cat_m_nm", "floor_no", COL]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


@pytest.fixture(scope="module")
def mig():
    return read(B)


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


@pytest.fixture(scope="module")
def cmig():
    return read(C)


def statements(sql):
    """주석 줄을 걷어낸 실제 문장만(주석으로 죽인 문장을 '있다'로 보지 않게)."""
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


def fn_block(sql, name):
    """`create or replace function <name>(` 부터 `$$;` 까지 — 머리 + 본문 통째(줄머리 고정)."""
    m = re.search(r"(?ms)^create\s+or\s+replace\s+function\s+" + re.escape(name)
                  + r"\s*\(.*?\$\$\s*;", sql)
    assert m, "{} 의 정의를 못 찾았습니다".format(name)
    return m.group(0)


def fn_comment(sql, name):
    m = re.search(r"(?ms)^comment\s+on\s+function\s+" + re.escape(name) + r"\s*\(.*?';\s*$", sql)
    assert m, "{} 의 comment 를 못 찾았습니다".format(name)
    return m.group(0)


def mv_block(sql, name):
    """`create materialized view [if not exists] <name> as … ;` — 이름 뒤 꼴은 그대로 돌려준다."""
    m = re.search(r"(?ms)^create\s+materialized\s+view\s+(?:if\s+not\s+exists\s+)?" + re.escape(name)
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


# ── 탐지 함수 (가드 본체와 양성 대조가 같이 지난다) ─────────────────────────────


def gate_problems(sql):
    """14b 맨 앞 관문 DO 가 셋을 다 보나 · begin 바로 뒤 첫 문장인가 — 어긋난 까닭 목록(비면 정상).

    ⚠️ 못 보는 것: 관문을 함수로 빼서 부르는 꼴 · raise 대신 notice 로 바꾼 꼴의 의미(raise exception 글자만 센다).
    """
    code = statements(sql)
    out = []
    begin = re.search(r"(?mi)^begin\s*;", code)
    if not begin:
        return ["begin 없음"]
    rest = code[begin.end():].lstrip()
    if not re.match(r"(?i)do\s+\$\$", rest):
        out.append("begin 바로 뒤가 관문 DO 가 아님")
        return out
    do = rest[: rest.index("end $$;") + len("end $$;")] if "end $$;" in rest else rest
    flat = re.sub(r"\s+", " ", do)
    if not re.search(r"table_name = 'unit_business' and column_name = '" + COL + "'", flat):
        out.append("칸(14a) 확인 없음")
    if not (re.search(r"c\.relname = 'idx_ub_pnu_cat'", flat) and "like '%" + COL + "%'" in flat):
        out.append("점포 색인 include(14c) 확인 없음")
    if not re.search(r"r\.loaded_ym = r\.published_ym", flat):
        out.append("표지 loaded = published 확인 없음")
    if len(re.findall(r"raise exception", flat)) < 3:
        out.append("raise exception 이 셋이 아님")
    return out


def swap_problems(sql):
    """요약표 바꿔 끼우기 차례 — 어긋난 까닭 목록(비면 정상).

    본다: _next 굽기 < 유일 색인 _key_next < 옛 표 drop < 표 rename < 색인 rename < 회수 < comment < analyze < commit.
    ⚠️ 못 보는 것: 동적 SQL 안의 문장 · 들여쓴 문장(줄머리 고정).
    """
    code = statements(sql)
    out = []

    def at(pattern):
        m = re.search(pattern, code, re.M | re.I)
        return m.start() if m else None

    marks = [
        ("_next 굽기", at(r"^create\s+materialized\s+view\s+" + MV + r"_next\s+as\b")),
        ("유일 색인 _key_next", at(r"^create\s+unique\s+index\s+" + MV + r"_key_next\s+on\s+" + MV + r"_next\s*\(")),
        ("옛 표 drop", at(r"^drop\s+materialized\s+view\s+(?:if\s+exists\s+)?" + MV + r"\s*;")),
        ("표 rename", at(r"^alter\s+materialized\s+view\s+" + MV + r"_next\s+rename\s+to\s+" + MV + r"\s*;")),
        ("색인 rename", at(r"^alter\s+index\s+" + MV + r"_key_next\s+rename\s+to\s+" + MV + r"_key\s*;")),
        ("회수", at(r"^revoke\s+all\s+on\s+" + MV + r"\s+from\s+public,\s*anon,\s*authenticated\s*;")),
        ("comment", at(r"^comment\s+on\s+materialized\s+view\s+" + MV + r"\s+is")),
        ("analyze", at(r"^analyze\s+" + MV + r"\s*;")),
        ("commit", at(r"^commit\s*;")),
    ]
    for name, pos in marks:
        if pos is None:
            out.append("없음: " + name)
    seen = [(n, p) for n, p in marks if p is not None]
    for (n1, p1), (n2, p2) in zip(seen, seen[1:]):
        if not p1 < p2:
            out.append("순서: {} 가 {} 뒤에 있다".format(n1, n2))
    return out


def band_problems(block):
    """층 묶음 함수 — 칸 true 인 층 NULL 만 'b' 로 가나 · strict·immutable — 어긋난 까닭 목록."""
    head = head_of(block).lower()
    body = re.sub(r"\s+", " ", statements(body_of(block)))
    out = []
    if re.search(r"\bstrict\b", head) or "returns null on null input" in head:
        out.append("strict")
    if not re.search(r"(?m)^immutable\s*$", head):
        out.append("immutable 아님")
    first = "when p_floor is null and p_basement_unknown is true then 'b'"
    second = "when p_floor is null then 'na'"
    if first not in body:
        out.append("칸 true → b 갈래 없음")
    if second not in body:
        out.append("층 NULL → na 갈래 없음")
    if first in body and second in body and body.index(first) > body.index(second):
        out.append("na 갈래가 b 갈래보다 앞이라 b 가 안 나온다")
    if re.search(r"when\s+p_basement_unknown\s+(?:is\s+true|=\s*true|is\s+not\s+false)\s+then\s+'b'", body) or \
            re.search(r"when\s+p_floor\s+is\s+null\s+then\s+'b'", body):
        out.append("층을 안 보고(또는 칸을 안 보고) b 로 보낸다")
    return out


def ub_pnu_cat_include(sql, name="idx_ub_pnu_cat"):
    """`create index … <name> on unit_business (pnu, snapshot_ym) include (…)` 의 include 목록(순서 그대로)."""
    m = re.search(r"(?is)create\s+(?:unique\s+)?index\s+(?:concurrently\s+)?(?:if\s+not\s+exists\s+)?"
                  + re.escape(name) + r"\s+on\s+unit_business\s*\(\s*pnu\s*,\s*snapshot_ym\s*\)\s*"
                  r"include\s*\(([^)]*)\)", statements(sql))
    if not m:
        return None
    return [c.strip().lower() for c in m.group(1).split(",") if c.strip()]


# ── 1. 정본과 글자 대조 ────────────────────────────────────────────────────────


class TestMirrorsTheSchema:
    @pytest.mark.parametrize("name", (BAND_FN, LIST_FN))
    def test_head_and_body_are_the_same_text(self, mig, schema, name):
        assert fn_block(mig, name) == fn_block(schema, name), (
            "{} 가 정본과 글자가 다릅니다 — 새 환경만 다른 모양이 됩니다".format(name))

    @pytest.mark.parametrize("name", (BAND_FN, LIST_FN))
    def test_comment_is_the_same_text(self, mig, schema, name):
        assert fn_comment(mig, name) == fn_comment(schema, name), name

    def test_heads_are_kept(self, mig):
        """머리 속성 — create or replace 가 덮어쓰므로 빠지면 라이브에서 사라진다."""
        head = head_of(fn_block(mig, LIST_FN))
        assert re.search(r"(?m)^stable\s*$", head)
        assert re.search(r"(?m)^security definer\s*$", head)
        assert re.search(r"(?m)^set search_path = public\s*$", head)
        assert "(p_pnu text, p_cat_l text, p_cat_m text[] default null)" in head
        assert band_problems(fn_block(mig, BAND_FN)) == []

    def test_summary_table_is_the_same_text(self, mig, schema):
        """14b 는 _next 로 굽는다 — 이름만 정본 이름으로 바꾸면 정본(if not exists 꼴)과 글자가 같아야 한다."""
        got = mv_block(mig, MV + "_next").replace(
            "create materialized view {}_next as".format(MV),
            "create materialized view if not exists {} as".format(MV), 1)
        assert got == mv_block(schema, MV)
        assert mv_comment(mig, MV) == mv_comment(schema, MV)

    def test_unique_index_is_the_same_shape(self, mig, schema):
        assert re.search(r"(?m)^create unique index if not exists mv_district_industry_floor_key\n"
                         r"  on mv_district_industry_floor \(district_id, snapshot_ym, cat_m_cd, floor_band\);",
                         statements(schema))
        assert re.search(r"(?m)^create unique index mv_district_industry_floor_key_next\n"
                         r"  on mv_district_industry_floor_next \(district_id, snapshot_ym, cat_m_cd, floor_band\);",
                         statements(mig))

    def test_api_twin_is_left_as_it_was(self, schema):
        """api 쌍둥이는 jsonb 를 그대로 넘긴다 — 정본이 09b 글자 그대로여야 하고 14b 는 안 건드린다."""
        assert fn_block(schema, API_FN) == fn_block(read(OLD), API_FN)
        assert not re.search(r"(?im)^create\s+or\s+replace\s+function\s+api\.", statements(read(B)))


class TestOldOneArgIsGone:
    def test_schema_has_only_the_two_arg(self, schema):
        code = statements(schema)
        heads = re.findall(r"(?im)^create\s+or\s+replace\s+function\s+industry_floor_band\s*\(([^)]*)\)", code)
        assert heads == ["p_floor smallint, p_basement_unknown boolean"]
        assert "industry_floor_band(smallint)" not in code, "옛 판의 comment·revoke 줄이 남았습니다"
        assert "industry_floor_band(ub.floor_no)" not in code

    def test_migration_drops_the_old_after_replacing_users(self, mig):
        code = statements(mig)
        drop = code.index("drop function if exists industry_floor_band(smallint);")
        assert code.index("create or replace function list_industry_floors(") < drop
        assert code.index("drop materialized view mv_district_industry_floor;") < drop
        assert drop < re.search(r"(?m)^commit;", code).start()

    def test_detector_sees_a_leftover_one_arg(self, schema):
        """양성 대조 — 정본에 옛 판 revoke 한 줄이 되살아나면 걸린다."""
        bad = statements(schema) + "\nrevoke all on function industry_floor_band(smallint) from public;\n"
        assert "industry_floor_band(smallint)" in bad


class TestBandFunction:
    def test_band_is_fine(self, mig, schema):
        for sql in (mig, schema):
            assert band_problems(fn_block(sql, BAND_FN)) == []

    @pytest.mark.parametrize("old, new, want", [
        ("           when p_floor is null and p_basement_unknown is true then 'b'\n", "", "칸 true → b 갈래 없음"),
        ("when p_floor is null and p_basement_unknown is true then 'b'",
         "when p_floor is null and p_basement_unknown is not false then 'b'", "칸 true → b 갈래 없음"),
        ("when p_floor is null and p_basement_unknown is true then 'b'",
         "when p_floor is null then 'b'", "층을 안 보고(또는 칸을 안 보고) b 로 보낸다"),
        ("immutable\n", "immutable\nstrict\n", "strict"),
    ], ids=["b_갈래_빠짐", "칸_NULL_도_b", "칸_false_도_b", "strict"])
    def test_mutations_are_noticed(self, mig, old, new, want):
        block = fn_block(mig, BAND_FN)
        assert old in block
        assert want in band_problems(block.replace(old, new, 1))

    def test_both_scopes_use_the_two_arg(self, mig, schema):
        """요약표(상권)와 반경 집계가 같은 자로 묶어야 같은 카드 안 두 줄이 같은 말을 한다."""
        call = "public.industry_floor_band(ub.floor_no, ub.floor_basement_unknown) as floor_band"
        for sql in (mig, schema):
            assert call in mv_block(sql, MV + "_next" if sql is mig else MV)
            assert call in statements(body_of(fn_block(sql, LIST_FN)))


class TestCounted:
    def test_counted_is_one_pk_row_of_snap(self, mig):
        body = re.sub(r"\s+", " ", statements(body_of(fn_block(mig, LIST_FN))))
        assert ("select coalesce(( select ub.floor_basement_unknown is not null from unit_business ub "
                "where ub.snapshot_ym = (select ym from snap) order by ub.biz_no limit 1), false) as v") in body
        assert "'basement_unknown_counted', (select v from counted)," in body

    def test_counted_detector_sees_always_true(self, mig):
        """양성 대조 — counted 를 늘 true 로 박으면 위 대조가 깨진다(같은 정규화를 지난다)."""
        block = fn_block(mig, LIST_FN).replace("'basement_unknown_counted', (select v from counted),",
                                               "'basement_unknown_counted', true,", 1)
        body = re.sub(r"\s+", " ", statements(body_of(block)))
        assert "'basement_unknown_counted', (select v from counted)," not in body


# ── 2. 14b 덩어리 꼴 ─────────────────────────────────────────────────────────


class TestMigrationShape:
    def test_gate_is_first_and_checks_three(self, mig):
        assert gate_problems(mig) == []

    @pytest.mark.parametrize("old, new, want", [
        ("select 1 from snapshot_release r where r.loaded_ym = r.published_ym",
         "select 1 from snapshot_release r", "표지 loaded = published 확인 없음"),
        ("       and pg_get_indexdef(i.indexrelid) like '%floor_basement_unknown%'\n  ) then\n    raise exception 'idx_ub_pnu_cat",
         "  ) then\n    raise exception 'idx_ub_pnu_cat", "점포 색인 include(14c) 확인 없음"),
        ("       and column_name = 'floor_basement_unknown'\n", "\n", "칸(14a) 확인 없음"),
    ], ids=["loaded_published_가드_빠짐", "14c_가드_빠짐", "14a_가드_빠짐"])
    def test_gate_mutations_are_noticed(self, mig, old, new, want):
        assert old in mig
        assert want in gate_problems(mig.replace(old, new, 1))

    def test_gate_moved_after_work_is_noticed(self, mig):
        gate = mig[mig.index("do $$\nbegin\n  if not exists (\n    select 1 from information_schema.columns"):]
        gate = gate[: gate.index("end $$;") + len("end $$;")]
        moved = mig.replace(gate, "", 1).replace("\ncommit;\n", "\n" + gate + "\ncommit;\n", 1)
        assert "begin 바로 뒤가 관문 DO 가 아님" in gate_problems(moved)

    def test_swap_order(self, mig):
        assert swap_problems(mig) == []

    @pytest.mark.parametrize("old, want", [
        ("alter index mv_district_industry_floor_key_next rename to mv_district_industry_floor_key;\n",
         "없음: 색인 rename"),
        ("revoke all on mv_district_industry_floor from public, anon, authenticated;\n", "없음: 회수"),
        ("analyze mv_district_industry_floor;\n", "없음: analyze"),
    ], ids=["색인_rename_빠짐", "회수_빠짐", "analyze_빠짐"])
    def test_swap_mutations_are_noticed(self, mig, old, want):
        assert old in mig
        assert want in swap_problems(mig.replace(old, "", 1))

    def test_drop_before_build_is_noticed(self, mig):
        """양성 대조 — 굽기 앞에서 옛 표를 지우면(잠금이 굽는 30초 내내) 차례가 걸린다."""
        drop = "drop materialized view mv_district_industry_floor;\n"
        moved = mig.replace(drop, "", 1).replace(
            "create materialized view mv_district_industry_floor_next as", drop + "create materialized view mv_district_industry_floor_next as", 1)
        assert any(p.startswith("순서:") for p in swap_problems(moved))

    def test_settings_before_begin_and_notify_after_commit(self, mig):
        code = statements(mig)
        begin = re.search(r"(?m)^begin;", code).start()
        commit = re.search(r"(?m)^commit;", code).start()
        assert code.index("set lock_timeout = ") < begin
        assert code.index("set statement_timeout = '900s';") < begin
        assert begin < commit < code.index("notify pgrst, 'reload schema';")
        assert len(re.findall(r"(?m)^begin;", code)) == 1 and len(re.findall(r"(?m)^commit;", code)) == 1
        assert "concurrently" not in code
        for stmt in re.finditer(r"(?im)^(create|drop|alter|insert|revoke|grant|analyze|comment|do)\b", code):
            assert begin < stmt.start() < commit, "begin/commit 밖의 문장: " + stmt.group(0)

    def test_no_grant_and_everything_revoked(self, mig):
        code = statements(mig)
        assert not re.search(r"(?im)^\s*grant\b", code), "14b 는 새 공개 함수가 없다 — grant 0"
        for name in ("industry_floor_band(smallint, boolean)", "list_industry_floors(text, text, text[])"):
            assert re.search(r"(?m)^revoke all on function " + re.escape(name)
                             + r" from public, anon, authenticated;", code), name

    def test_allowlist_is_unchanged(self):
        assert API_FN in post_load.ANON_CALLABLE_ALLOWLIST
        assert not [n for n in post_load.ANON_CALLABLE_ALLOWLIST if BAND_FN in n]
        assert not [n for n in post_load.ANON_READABLE_ALLOWLIST if MV in n]

    def test_order_note_is_written(self, mig, cmig):
        """적용 순서 A → C → B 가 두 파일 머리말에 적혀 있다(🟠3)."""
        assert "2026-10-14a(칸) → 2026-10-14c(점포 색인 include) → 이 파일" in mig
        assert "2026-10-14a(칸) → 이 파일(14c) → 2026-10-14b" in cmig


# ── 3. 14c 점포 색인 include ──────────────────────────────────────────────────


class TestIndexC:
    def test_schema_and_migration_have_the_same_six(self, schema, cmig):
        assert ub_pnu_cat_include(schema) == UB_INCLUDE
        assert ub_pnu_cat_include(cmig, "idx_ub_pnu_cat_next") == UB_INCLUDE
        assert post_load.canonical_index_includes(schema)["idx_ub_pnu_cat"] == UB_INCLUDE

    @pytest.mark.parametrize("old, new", (
        ("floor_no, floor_basement_unknown)", "floor_no)"),
        ("floor_no, floor_basement_unknown)", "floor_basement_unknown, floor_no)"),
    ), ids=["빠짐", "순서"])
    def test_detector_catches_missing_or_reordered(self, cmig, old, new):
        assert old in cmig
        # 머리말 주석에도 같은 글자가 있어 전부 바꾼다 — 탐지는 주석을 걷어 내고 본다.
        assert ub_pnu_cat_include(cmig.replace(old, new), "idx_ub_pnu_cat_next") != UB_INCLUDE

    def test_not_wrapped_and_gate_before_drop_and_rename_last(self, cmig):
        code = statements(cmig)
        assert not re.search(r"(?im)^\s*(begin|commit)\s*;", code), "concurrently 는 트랜잭션 안에서 못 돈다"
        create = code.index("create index concurrently if not exists idx_ub_pnu_cat_next")
        gate = code.index("and pg_get_indexdef(i.indexrelid) like '%floor_basement_unknown%'")
        drop = code.index("drop index concurrently if exists idx_ub_pnu_cat;")
        lock = code.index("set lock_timeout = '2s';")
        rename = code.index("alter index idx_ub_pnu_cat_next rename to idx_ub_pnu_cat;")
        assert code.index("set statement_timeout = '900s';") < create < gate < drop < lock < rename
        assert "i.indisvalid" in code[create:drop]
        assert re.findall(r"(?im)^drop\s+index\s+concurrently\s+if\s+exists\s+(\w+)", code) == ["idx_ub_pnu_cat"]
        assert not re.search(r"(?im)^\s*(create|drop)\s+(materialized\s+view|view|function|table)\b", code)

    def test_disk_note_is_written(self, cmig):
        assert "85%" in cmig and "+300MB" in cmig and "dbx.py -f" in cmig


# ── 4. 로컬 PostgreSQL 로 실제 실행 (없으면 건너뜀) ────────────────────────────

SHIM = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated; end if;
end $$;
create schema api;
create domain geography as text;
create table parcel (pnu char(19) primary key, geom text);
create table district (district_id text primary key, district_nm text, area_m2 numeric(14,2), geom text);
create table unit_business (snapshot_ym char(6), biz_no text, pnu char(19), floor_no smallint,
                            cat_l_cd char(2), cat_l_nm text, cat_m_cd char(4), cat_m_nm text, geom text, biz_name text,
                            floor_basement_unknown boolean, primary key (snapshot_ym, biz_no));
create table snapshot_release (id int primary key, loaded_ym char(6), published_ym char(6));
create function st_contains(poly text, pt text) returns boolean language sql immutable
  as 'select position(''|'' || pt || ''|'' in poly) > 0';
create function st_dwithin(a geography, b geography, r integer, s boolean) returns boolean
  language sql immutable as 'select left(a::text, 1) = left(b::text, 1)';
"""

PNU = "1168010100100010000"

# 202606 = 옛 분기(칸 NULL — 👤 D1) · 202609 = 새 분기(칸 true/false). 202609 의 '지' 가게는 S2(층 NULL · 칸 true).
FIXTURE = """
insert into parcel values ('{p}', 'PA');
insert into district values ('D1', '상권', 1000, '|PA|S1|S2|S3|S4|S5|S6|S7|S8|S9|T1|T2|T3|');
insert into unit_business values
  ('202609', 'a1', '{p}', null, 'I2', '음식', 'I201', '한식', 'S1', '가', false),
  ('202609', 'a2', '{p}', null, 'I2', '음식', 'I201', '한식', 'S2', '나', true),
  ('202609', 'a3', '{p}', -1,   'I2', '음식', 'I201', '한식', 'S3', '다', false),
  ('202609', 'a4', '{p}', 1,    'I2', '음식', 'I212', '비알코올', 'S4', '라', false),
  ('202609', 'a5', '{p}', 2,    'I2', '음식', 'I201', '한식', 'S5', '마', false),
  ('202609', 'a6', '{p}', 99,   'I2', '음식', 'I212', '비알코올', 'S6', '바', false),
  ('202609', 'a7', '{p}', null, 'I2', '음식', 'I212', '비알코올', 'S7', '사', true),
  ('202606', 'b1', '{p}', null, 'I2', '음식', 'I201', '한식', 'T1', '아', null),
  ('202606', 'b2', '{p}', -1,   'I2', '음식', 'I201', '한식', 'T2', '자', null),
  ('202606', 'b3', '{p}', 1,    'I2', '음식', 'I212', '비알코올', 'T3', '차', null);
""".format(p=PNU)

INDEX_C = ("create index idx_ub_pnu_cat on unit_business (pnu, snapshot_ym) "
           "include (cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, floor_no, floor_basement_unknown);")


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    psycopg2 = pytest.importorskip("psycopg2")
    initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
    if not initdb or not pg_ctl:
        pytest.skip("로컬 PostgreSQL(initdb·pg_ctl)이 없다 — CI 는 글자 가드(1~3)만 본다")
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

    def connect(dbname):
        for _ in range(30):
            try:
                c = psycopg2.connect(host="127.0.0.1", port=port, user="postgres", dbname=dbname)
                c.autocommit = True
                return c
            except psycopg2.OperationalError:
                time.sleep(0.5)
        raise AssertionError("로컬 PostgreSQL 에 못 붙었다")

    try:
        yield psycopg2, connect
    finally:
        subprocess.run([pg_ctl, "-D", data, "-m", "fast", "-w", "stop"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)


def _old_state(pg, name, release=("202606", "202606"), index_c=True):
    """적용 **전** 라이브와 같은 모양 — 흉내 판 + 09b 원문 그대로 + 형제 업종 표(정본) + (14c 뒤라면) 점포 색인."""
    _psycopg2, connect = pg
    admin = connect("postgres")
    admin.cursor().execute("create database {}".format(name))
    admin.close()
    conn = connect(name)
    c = conn.cursor()
    c.execute(SHIM)
    c.execute(FIXTURE)
    c.execute("insert into snapshot_release values (1, %s, %s)", release)
    c.execute(read(OLD))
    c.execute(mv_block(read(SCHEMA), MIX))
    if index_c:
        c.execute(INDEX_C)
    return conn, c


def _call(cur, *args):
    cur.execute("select list_industry_floors(%s, %s, %s)", args)
    return cur.fetchone()[0]


@pytest.fixture(scope="module")
def applied(pg):
    conn, c = _old_state(pg, "applied")
    c.execute(read(B))    # 14b 원문 그대로(set · begin … commit · notify)
    yield c
    conn.close()


class TestRealRun:
    def test_band_function(self, applied):
        applied.execute("select industry_floor_band(f::smallint, u) from (values "
                        "(null, true), (null, false), (null, null), (-1, false), (1, null), (2, false), "
                        "(3, false), (99, false)) v(f, u)")
        assert [r[0] for r in applied.fetchall()] == ["b", "na", "na", "b", "1", "2", "3+", "3+"]

    def test_only_the_two_arg_remains(self, applied):
        applied.execute("select p.oid::regprocedure::text from pg_proc p where p.proname = 'industry_floor_band'")
        assert [r[0] for r in applied.fetchall()] == ["industry_floor_band(smallint,boolean)"]

    def test_unique_index_has_the_canonical_name(self, applied):
        applied.execute("select indexrelid::regclass::text from pg_index "
                        "where indrelid = 'mv_district_industry_floor'::regclass")
        assert [r[0] for r in applied.fetchall()] == ["mv_district_industry_floor_key"]
        applied.execute("select count(*) from pg_class where relname like '%industry_floor%next%'")
        assert applied.fetchone()[0] == 0

    def test_old_quarter_is_unchanged_and_not_counted(self, applied):
        """202606(칸 NULL)은 옛 판과 같은 묶음 — 층 NULL 은 na 그대로 · counted false(화면 옛 문구)."""
        got = _call(applied, PNU, "I2", None)
        want = {"b": 1, "1": 1, "2": 0, "3+": 0, "na": 1}
        assert got["snapshot_ym"] == "202606"
        assert got[COUNTED] is False
        assert got["districts"][0]["bands"] == want and got["radius"]["bands"] == want

    def test_closed_to_anon(self, applied):
        applied.execute("select has_function_privilege('anon', 'industry_floor_band(smallint, boolean)', 'execute'),"
                        "       has_function_privilege('anon', 'list_industry_floors(text, text, text[])', 'execute'),"
                        "       has_table_privilege('anon', 'mv_district_industry_floor', 'select')")
        assert applied.fetchone() == (False, False, False)

    def test_new_quarter_counts_ji_in_basement(self, applied):
        """표지를 202609 로 올리고 요약표를 다시 구우면 — '지'(층 NULL · 칸 true)는 b, 칸 false 인 층 NULL 은 na."""
        applied.execute("update snapshot_release set loaded_ym = '202609', published_ym = '202609'")
        applied.execute("refresh materialized view mv_district_industry_floor")
        applied.execute("refresh materialized view mv_district_industry_mix")
        got = _call(applied, PNU, "I2", None)
        want = {"b": 3, "1": 1, "2": 1, "3+": 1, "na": 1}
        assert got["snapshot_ym"] == "202609"
        assert got[COUNTED] is True
        assert got["districts"] == [{"district_id": "D1", "name": "상권", "total": 7, "bands": want}]
        assert got["radius"] == {"total": 7, "bands": want}
        chip = _call(applied, PNU, "I2", ["I212"])
        assert chip["radius"]["bands"] == {"b": 1, "1": 1, "2": 0, "3+": 1, "na": 0}
        # post_load --check 합 대조 — 층 묶음 합 = 업종 표 n(na → b 로 옮겼을 뿐) · 어긋남 0
        applied.execute(post_load.INDUSTRY_FLOOR_CONSISTENCY_SQL)
        mismatch, mix_rows, floor_rows = applied.fetchone()[0].split("|")
        assert (mismatch, mix_rows, floor_rows) == ("0", "2", "2")
        assert post_load.judge_industry_floor_consistency(mismatch, mix_rows, floor_rows) is False


@pytest.mark.parametrize("name, release, index_c, want", [
    ("gate_release", ("202609", "202606"), True, "loaded_ym 과 published_ym 이 다릅니다"),
    ("gate_index", ("202606", "202606"), False, "2026-10-14c 를 먼저"),
], ids=["loaded_ne_published", "14c_전"])
def test_gate_refuses_and_nothing_changes(pg, name, release, index_c, want):
    """관문이 막으면 덩어리째 되돌아간다 — 옛 한 인자 판·옛 요약표가 그대로 남는다."""
    psycopg2, _ = pg
    conn, c = _old_state(pg, name, release=release, index_c=index_c)
    try:
        with pytest.raises(psycopg2.errors.RaiseException) as e:
            c.execute(read(B))
        assert want in str(e.value)
        c.execute("rollback")   # 오류 난 덩어리를 닫는다(autocommit 연결에서 begin 으로 연 트랜잭션)
        c.execute("select p.oid::regprocedure::text from pg_proc p where p.proname = 'industry_floor_band'")
        assert [r[0] for r in c.fetchall()] == ["industry_floor_band(smallint)"]
        c.execute("select count(*) from pg_class where relname = 'mv_district_industry_floor_next'")
        assert c.fetchone()[0] == 0
    finally:
        conn.close()
