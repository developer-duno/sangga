# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-07a(분기 표지 snapshot_release · 결정 0035)와 정본의 불변식.

왜 (결정 0035)
--------------
화면은 점포 분기를 `max(snapshot_ym) from unit_business` 로 골랐다. 분기 적재기는 한 트랜잭션이
아니라 약 2시간 동안 1,000행씩 올리므로, 첫 1,000행이 들어가는 순간부터 손님이 **반쯤 찬 새 분기**를
봤다. 이제 분기는 표지 두 칸에서 읽는다 — 요약표 셋은 loaded_ym(다 들어온 분기)으로 굽고, 실시간
셋은 published_ym(화면 기준)을 본다. post_load.py 가 굽고 확인한 뒤 published 를 올린다.

여기서 막는 것 — 전부 **에러 없이** 틀리는 종류다(DB 없이 글자만 본다)
  1) 누가 `max(snapshot_ym) from unit_business` 를 되살린다 → 적재 2시간 동안 반쪽이 다시 샌다.
  2) 요약표를 published 로 굽는다 → post_load 가 새 분기로 구울 수 없어 표지를 올린 순간
     요약표만 옛 분기를 말한다(실시간을 loaded 로 읽으면 반대로 적재 직후 화면이 먼저 바뀐다).
  3) RPC 를 anon 에게 연다 → 누구나 표지를 올릴 수 있다.
  4) `p_ym <= loaded_ym` 가드가 빠지거나 published 로 느슨해진다 → 옛 분기 백필·이미 들어온 분기가
     표지(loaded)를 끌어내린다(앞으로만 — loaded ≥ published 불변식이 깨진다).
  5) seed 가 빠진다 → 표지 0줄 = 화면 가게 칸이 조용히 빈다.
  6) `set lock_timeout` 이 begin 뒤로 간다 → 옛 요약표를 쥔 검색 뒤에 화면 전체가 줄을 선다.
  7) 함수 머리(security definer·search_path·stable)·comment 가 정본과 갈린다 → `create or replace`
     가 라이브 속성을 조용히 바꾼다(CLAUDE.md ⛔ 2026-10-01a 사고).
  8) 느린 굽기를 화면 객체 잠금 **뒤**에 둔다 → 굽는 2~3분 내내 화면 읽기가 줄을 선다.

ⓘ 도우미는 이 파일 안에서만 쓴다(시험 파일끼리 import 하지 않는 레포 관습).
⚠️ 라이브에서 실제로 그렇게 도는지는 마이그레이션 머리말 「적용 뒤 확인」을 사람이(Claude 가) 돌린다.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
MIG_DIR = os.path.join(ROOT, "supabase", "migrations")
MIGRATION = os.path.join(MIG_DIR, "2026-10-07a_snapshot_release.sql")

RPC = "mark_snapshot_loaded"
# 실시간(화면이 바로 읽는) 셋 — published_ym
LIVE_FNS = ("list_district_buildings", "get_data_freshness")
LIVE_VIEW = "v_floor_stack"
# 요약표 셋 — loaded_ym (post_load 가 새 분기로 먼저 굽고 나서 published 를 올린다)
SUMMARY_MVS = ("mv_parcel_store_names", "mv_coverage_stats", "mv_district_industry_mix")
# 2순위만 published 인 둘 — 1순위는 요약표(max(m.snapshot_ym))
SECOND_FNS = ("list_industry_mix", "list_industry_detail")
# 마이그레이션이 다시 만드는 함수 넷 — 머리·comment·본문이 정본과 글자 그대로
REBUILT_FNS = SECOND_FNS + LIVE_FNS
RENAMED_INDEXES = ("idx_mpsn_pnu", "idx_mpsn_sigungu", "idx_mpsn_names",
                   "idx_mcs_snapshot_ym", "mv_district_industry_mix_key")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


@pytest.fixture(scope="module")
def mig():
    return read(MIGRATION)


def statements(sql):
    """줄 전체 주석을 걷은 것(줄 구조는 그대로)."""
    return "\n".join(ln for ln in sql.split("\n") if not ln.lstrip().startswith("--"))


RE_COMMENT_STMT = re.compile(r"(?ims)^comment\s+on\s+.*?';\s*$")


def code_only(sql):
    """줄 주석 · `comment on … is '…';` 글 · 줄 끝 `--` 주석까지 걷은 코드만."""
    text = RE_COMMENT_STMT.sub("", statements(sql))
    return "\n".join(ln.split("--")[0] for ln in text.split("\n"))


# ── 탐지 함수 — 가드 본체와 양성 대조가 **같은 함수**를 지난다 ──────────────────

RE_MAX_FROM_UB = re.compile(
    r"(?i)max\s*\(\s*(?:\w+\.)?snapshot_ym\s*\)(?:\s*::\s*\w+)?(?:\s+as\s+\w+)?"
    r"\s+from\s+(?:public\.)?unit_business\b")


def max_from_unit_business(sql):
    """코드에 남은 `max(… snapshot_ym) from unit_business` 꼴을 전부 돌려준다.

    잡는 꼴: `max(snapshot_ym) from unit_business` · 별칭 `max(u.snapshot_ym) from unit_business u` ·
    캐스트 `max(t.snapshot_ym)::text from unit_business t` · 열 별칭 `max(u.snapshot_ym) as ym from unit_business u`
    (PR 전 mv_parcel_store_names 의 원래 꼴 — 2026-10-07 적대 검사관 🟠② 뒤 보탬) · `public.unit_business` ·
    대소문자·공백 변형.
    ⚠️ 못 보는 것: `as` 없이 붙인 열 별칭(`max(snapshot_ym) ym from …`) · 따옴표 열 별칭(`as "ym"`) ·
       줄을 넘겨 쪼갠 꼴 중 `--` 를 품은 글 뒤의 같은 줄(주석으로 잘려 안 본다 — `\\s` 는 줄바꿈을 먹으므로
       `max(snapshot_ym)\\n from` · `max(\\nsnapshot_ym)` 은 잡는다) · 동적 SQL(`execute '…'`) 안 ·
       `greatest(...)`·`order by … limit 1` 같은 다른 꼴의 '가장 새 분기'.
    ⓘ `max(t.store_snapshot_ym)`(요약표 칸 집계)·`max(m.snapshot_ym) from mv_…`(요약표)는 대상이 아니다.
    """
    return RE_MAX_FROM_UB.findall(code_only(sql))


RE_RELEASE_COL = re.compile(
    r"(?i)\br\.(loaded|published)_ym(?:\s*::\s*\w+)?(?:\s+as\s+\w+)?\s+from\s+snapshot_release\s+r\b")


def release_columns(block):
    """블록이 표지에서 읽는 칸 이름들(집합 — 'loaded' · 'published')."""
    return {m.lower() for m in RE_RELEASE_COL.findall(code_only(block))}


def sql_block(text, header_re):
    """줄머리가 header_re 인 문장 하나(주석을 뗀 부분이 `;` 로 끝나는 첫 줄까지)."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if re.match(header_re, line, re.I):
            for j in range(i, len(lines)):
                if lines[j].split("--")[0].rstrip().endswith(";"):
                    return "\n".join(lines[i:j + 1])
            raise AssertionError("문장이 안 끝납니다: " + header_re)
    raise AssertionError("못 찾았습니다: " + header_re)


def fn_block(text, name):
    """`create or replace function <name>(` 부터 `$$;` 까지(줄머리 고정 — api 쌍둥이는 안 집는다)."""
    m = re.search(r"(?ms)^create\s+or\s+replace\s+function\s+{}\s*\(.*?^\$\$;".format(re.escape(name)), text)
    assert m, "함수 {} 를 못 찾았습니다".format(name)
    return m.group(0)


def fn_comment(text, name):
    m = re.search(r"(?ims)^comment\s+on\s+function\s+{}\s*\(.*?';\s*$".format(re.escape(name)), text)
    assert m, "함수 {} 의 comment 를 못 찾았습니다".format(name)
    return m.group(0)


RE_RELEASE_COMMENT = re.compile(
    r"(?ims)^comment\s+on\s+(?:table\s+snapshot_release|column\s+snapshot_release\.\w+)\s+is.*?';\s*$")


def release_comments(text):
    """표지 표·칸의 `comment on … is '…';` 문장들(나온 순서 그대로 · 글자 그대로).

    ⚠️ 못 보는 것: `public.snapshot_release` 처럼 스키마를 붙인 꼴 · 글 안에 `';` + 줄끝이 들어간 comment
       (첫 `';` 줄끝에서 끊는다) — 둘 다 지금 두 파일에 없다.
    """
    return [m.group(0) for m in RE_RELEASE_COMMENT.finditer(text)]


def mv_block(text, name, next_suffix=False):
    if next_suffix:
        return sql_block(text, r"^create materialized view {}_next as\b".format(name))
    return sql_block(text, r"^create materialized view if not exists {} as\b".format(name))


def view_block(text, name):
    return sql_block(text, r"^create or replace view {} as\b".format(name))


def grant_receivers(sql, name):
    """`grant … on function [api.]<name>(…) to …;` 의 받는 쪽(소문자 집합). 줄머리·들여쓰기 무관."""
    out = set()
    for m in re.finditer(
            r"(?is)\bgrant\s+(?:execute|all(?:\s+privileges)?)\s+on\s+function\s+(?:\w+\.)?"
            + re.escape(name) + r"\s*\([^)]*\)\s+to\s+([^;]+);",
            code_only(sql)):
        out |= {w.strip().lower() for w in m.group(1).split(",")}
    return out


# ── 1. 표 · seed · RPC 가 있다 ───────────────────────────────────────────────


class TestTableAndSeed:
    @pytest.mark.parametrize("which", ["schema", "mig"])
    def test_the_table_is_one_row_with_two_quarters(self, which, request):
        text = request.getfixturevalue(which)
        block = sql_block(text, r"^create table if not exists snapshot_release\b")
        flat = re.sub(r"\s+", " ", block)
        for piece in ("id int primary key default 1 check (id = 1)",
                      "loaded_ym char(6) not null check (loaded_ym ~ '^\\d{6}$')",
                      "loaded_at timestamptz not null default now()",
                      "loaded_rows int,",
                      "published_ym char(6) not null check (published_ym ~ '^\\d{6}$')",
                      "published_at timestamptz not null default now()"):
            assert piece in flat, piece

    @pytest.mark.parametrize("which", ["schema", "mig"])
    def test_closed_rls_and_no_policy(self, which, request):
        code = code_only(request.getfixturevalue(which))
        assert re.search(r"(?im)^alter table snapshot_release enable row level security;", code)
        assert re.search(r"(?im)^revoke all on snapshot_release from public, anon, authenticated;", code)
        assert not re.search(r"(?i)create\s+policy\b[^;]*\bon\s+(?:public\.)?snapshot_release\b", code)
        assert not re.search(r"(?i)grant\b[^;]*\bon\s+(?:table\s+)?(?:public\.)?snapshot_release\b", code)

    @pytest.mark.parametrize("which", ["schema", "mig"])
    def test_seed_is_the_live_state_and_never_overwrites(self, which, request):
        """⛔ seed 가 빠지면 표지 0줄 = 화면 가게 칸이 조용히 빈다."""
        flat = re.sub(r"\s+", " ", code_only(request.getfixturevalue(which)))
        assert ("insert into snapshot_release (id, loaded_ym, loaded_at, loaded_rows, published_ym, "
                "published_at) values (1, '202606', now(), 2772484, '202606', now()) "
                "on conflict (id) do nothing;") in flat

    def test_table_block_is_the_same_in_schema_and_migration(self, schema, mig):
        a = sql_block(schema, r"^create table if not exists snapshot_release\b")
        b = sql_block(mig, r"^create table if not exists snapshot_release\b")
        assert a == b

    def test_table_and_column_comments_are_the_same(self, schema, mig):
        """표·칸 comment 넷이 정본과 글자 그대로(2026-10-07 적대 검사관 🟡③ — 함수 comment 대조와 같은 꼴)."""
        a, b = release_comments(schema), release_comments(mig)
        assert len(a) == 4, a
        assert a == b

    def test_mutation_one_letter_in_a_migration_comment_is_red(self, schema, mig):
        """양성 대조 — 마이그레이션 칸 comment 한 글자를 바꾸면 위 대조(같은 함수)가 다르다고 본다."""
        target = "comment on column snapshot_release.loaded_rows is\n  '표지를"
        assert mig.count(target) == 1
        bad = mig.replace(target, target.replace("표지를", "표지가"), 1)
        assert release_comments(bad) != release_comments(schema)


class TestRpc:
    @pytest.mark.parametrize("which", ["schema", "mig"])
    def test_head_is_definer_with_empty_search_path(self, which, request):
        block = fn_block(request.getfixturevalue(which), "api." + RPC)
        head = block[: block.index("$$")]
        assert "security definer" in head
        assert re.search(r"(?m)^set search_path = ''$", head)
        assert "returns jsonb" in head and "language plpgsql" in head

    @pytest.mark.parametrize("which", ["schema", "mig"])
    def test_body_guards(self, which, request):
        body = code_only(fn_block(request.getfixturevalue(which), "api." + RPC))
        assert "p_ym !~ '^\\d{6}$'" in body, "분기 모양 검사가 없습니다"
        assert re.search(r"not exists \(select 1 from public\.unit_business u where u\.snapshot_ym = p_ym::char\(6\)\)", body)
        assert "if p_ym <= v_cur.loaded_ym::text then" in body, (
            "앞으로만 가드(loaded_ym 이하 무변화)가 없습니다 — 옛 분기 백필이 표지를 끌어내립니다")
        assert "p_ym <= v_cur.published_ym" not in body, "가드가 published 로 느슨해졌습니다"
        assert re.search(r"set loaded_ym = p_ym, loaded_at = now\(\), loaded_rows = p_rows", body)
        assert "published_ym =" not in body, "RPC 가 화면 기준(published_ym)을 건드립니다"
        # search_path '' 이므로 표는 전부 public. 으로 한정한다.
        for bare in re.findall(r"(?i)\b(?:from|update|into)\s+(\w+)\b(?!\.)", body):
            assert bare.lower() in ("public", "v_cur"), "한정 안 된 이름: {}".format(bare)

    @pytest.mark.parametrize("which", ["schema", "mig"])
    def test_granted_to_service_role_only_after_revoke(self, which, request):
        text = request.getfixturevalue(which)
        code = code_only(text)
        assert grant_receivers(text, RPC) == {"service_role"}
        rv = code.find("revoke all on function api.{}(text, int) from public, anon, authenticated;".format(RPC))
        gr = code.find("grant execute on function api.{}(text, int) to service_role;".format(RPC))
        assert -1 < rv < gr, "회수를 먼저 하고 줘야 합니다"

    @pytest.mark.parametrize("bad", [
        "grant execute on function api.mark_snapshot_loaded(text, int) to anon;",              # 흔한 꼴
        "  GRANT ALL ON FUNCTION mark_snapshot_loaded (text,int)\n TO service_role, authenticated;",  # 변형 꼴
    ])
    def test_receiver_detector_sees_an_opened_rpc(self, bad):
        got = grant_receivers("select 1;\n" + bad, RPC)
        assert got and got != {"service_role"}, got

    def test_receiver_detector_leaves_comments_alone(self):
        assert grant_receivers("-- grant execute on function api.mark_snapshot_loaded(text, int) to anon;", RPC) == set()

    def test_rpc_block_is_the_same_in_schema_and_migration(self, schema, mig):
        assert fn_block(schema, "api." + RPC) == fn_block(mig, "api." + RPC)
        assert fn_comment(schema, "api." + RPC) == fn_comment(mig, "api." + RPC)


# ── 2. 어느 칸을 읽나 — 요약표 = loaded · 실시간 = published ───────────────────


class TestWhichColumn:
    @pytest.mark.parametrize("name", SUMMARY_MVS)
    def test_summary_tables_bake_from_loaded(self, schema, mig, name):
        assert release_columns(mv_block(schema, name)) == {"loaded"}, name
        assert release_columns(mv_block(mig, name, next_suffix=True)) == {"loaded"}, name

    def test_floor_stack_reads_published(self, schema, mig):
        assert release_columns(view_block(schema, LIVE_VIEW)) == {"published"}
        assert release_columns(view_block(mig, LIVE_VIEW)) == {"published"}

    @pytest.mark.parametrize("name", LIVE_FNS)
    def test_live_functions_read_published(self, schema, mig, name):
        assert release_columns(fn_block(schema, name)) == {"published"}, name
        assert release_columns(fn_block(mig, name)) == {"published"}, name

    @pytest.mark.parametrize("name", SECOND_FNS)
    def test_second_choice_is_published_and_first_is_the_summary(self, schema, mig, name):
        for text in (schema, mig):
            flat = re.sub(r"\s+", " ", code_only(fn_block(text, name)))
            assert ("select coalesce( (select max(m.snapshot_ym) from mv_district_industry_mix m), "
                    "(select r.published_ym from snapshot_release r)) as ym") in flat, name

    @pytest.mark.parametrize("swap", [
        ("mv_coverage_stats", "r.loaded_ym from snapshot_release r", "r.published_ym from snapshot_release r"),
        ("mv_parcel_store_names", "r.loaded_ym as ym from snapshot_release r", "r.published_ym as ym from snapshot_release r"),
    ])
    def test_mutation_summary_to_published_is_red(self, schema, swap):
        """양성 대조 — 요약표를 published 로 바꾼 정본 사본은 이 시험의 판정에 걸려야 한다."""
        name, old, new = swap
        block = mv_block(schema, name)
        assert old in block
        assert release_columns(block.replace(old, new)) != {"loaded"}

    def test_mutation_live_to_loaded_is_red(self, schema):
        block = view_block(schema, LIVE_VIEW)
        bad = block.replace("r.published_ym from snapshot_release r", "r.loaded_ym from snapshot_release r")
        assert bad != block and release_columns(bad) != {"published"}


# ── 3. max(… snapshot_ym) from unit_business 가 코드에 0건 ─────────────────────


class TestNoMaxFromUnitBusiness:
    def test_schema_code_has_none(self, schema):
        assert max_from_unit_business(schema) == []

    def test_migration_code_has_none(self, mig):
        assert max_from_unit_business(mig) == []

    @pytest.mark.parametrize("bad", [
        "and ub.snapshot_ym = (select max(snapshot_ym) from unit_business)",              # 흔한 꼴
        "where ub.snapshot_ym = (select max(u.snapshot_ym) from unit_business u)",        # 별칭 꼴
        "(select max(t.snapshot_ym)::text from unit_business t) as basis,",               # 캐스트 꼴
        "(SELECT MAX( u.snapshot_ym )\n   FROM public.unit_business u)",                  # 대소문자·줄바꿈
        "  select max(u.snapshot_ym) as ym from unit_business u",                         # PR 전 원래 꼴(열 별칭)
        "(select max(t.snapshot_ym)::text AS basis\n from unit_business t)",               # 캐스트 + 열 별칭 변형
    ])
    def test_detector_catches(self, bad):
        assert len(max_from_unit_business("select 1;\n" + bad)) == 1

    @pytest.mark.parametrize("harmless", [
        "-- (1) 점포 분기를 (select max(snapshot_ym) from unit_business)로 고른다",       # 설명 주석
        "comment on view x is\n  '예전엔 max(snapshot_ym) from unit_business 였다';",    # comment 글
        "             max(t.store_snapshot_ym) as store_snapshot_ym",                    # 요약표 칸 집계
        "(select max(m.snapshot_ym) from mv_district_industry_mix m),",                  # 요약표 1순위
        "select r.published_ym from snapshot_release r  -- 예전 max(snapshot_ym) from unit_business",
    ])
    def test_detector_leaves_the_rest_alone(self, harmless):
        assert max_from_unit_business("select 1;\n" + harmless) == []

    def test_mutation_putting_one_back_into_the_schema_is_red(self, schema):
        bad = schema.replace(
            "and ub.snapshot_ym = (select r.published_ym from snapshot_release r)",
            "and ub.snapshot_ym = (select max(snapshot_ym) from unit_business)", 1)
        assert bad != schema and len(max_from_unit_business(bad)) == 1

    def test_mutation_putting_the_original_aliased_form_back_is_red(self, schema):
        """적대 검사관 🟠② — PR 전 mv_parcel_store_names 의 원래 꼴(`… as ym from unit_business u`)을 되돌려도 잡는다."""
        bad = schema.replace(
            "  select r.loaded_ym as ym from snapshot_release r\n",
            "  select max(u.snapshot_ym) as ym from unit_business u\n", 1)
        assert bad != schema and len(max_from_unit_business(bad)) == 1


# ── 4. 다시 만드는 함수 넷 · 뷰 · 요약표 셋은 정본과 글자 그대로 ───────────────


class TestMirrorsTheSchema:
    @pytest.mark.parametrize("name", REBUILT_FNS)
    def test_function_head_and_body(self, schema, mig, name):
        """⛔ `create or replace` 는 머리 속성을 새 정의로 덮어쓴다 — 한 글자라도 다르면 라이브가 조용히 바뀐다."""
        a, b = fn_block(schema, name), fn_block(mig, name)
        assert a == b, name
        head = b[: b.index("$$")]
        for needle in ("security definer", "set search_path = public"):
            assert needle in head, (name, needle)
        assert re.search(r"(?m)^stable$", head), name

    @pytest.mark.parametrize("name", REBUILT_FNS)
    def test_function_comment(self, schema, mig, name):
        assert fn_comment(schema, name) == fn_comment(mig, name), name

    @pytest.mark.parametrize("name", REBUILT_FNS)
    def test_function_is_revoked_again(self, mig, name):
        assert re.search(r"(?im)^revoke all on function {}\([^)]*\) from public, anon, authenticated;".format(name),
                         code_only(mig)), name
        assert grant_receivers(mig, name) == set(), "{} 의 public 원본을 열었습니다".format(name)

    def test_floor_stack_view(self, schema, mig):
        assert view_block(schema, LIVE_VIEW) == view_block(mig, LIVE_VIEW)

    @pytest.mark.parametrize("name", SUMMARY_MVS)
    def test_summary_table_body(self, schema, mig, name):
        canon = mv_block(schema, name)
        rebuilt = mv_block(mig, name, next_suffix=True).replace(
            "create materialized view {}_next as".format(name),
            "create materialized view if not exists {} as".format(name), 1)
        assert rebuilt == canon, name

    @pytest.mark.parametrize("name", SUMMARY_MVS + ("v_coverage_stats",))
    def test_summary_comments(self, schema, mig, name):
        kind = "view" if name.startswith("v_") else "materialized view"
        pat = r"(?ims)^comment\s+on\s+{}\s+{}\s+is.*?';\s*$".format(kind, name)
        a, b = re.search(pat, schema), re.search(pat, mig)
        assert a and b, name
        assert a.group(0) == b.group(0), name


# ── 5. 바꿔 끼우기 · 잠금 · 원자성 ───────────────────────────────────────────


def session_settings_problems(sql):
    """세션 설정(lock_timeout·statement_timeout)이 첫 begin 앞에 있는지 — 어긋난 까닭 목록(비면 정상).

    가드 본체와 양성 대조가 **같은 함수**를 지난다(2026-10-07 적대 검사관 🟡⑥).
    ⚠️ 못 보는 것: 값이 다른 꼴(`'3s'`·`'900s'` 밖의 값은 '없음'으로 본다) · 들여쓴 `set`·`begin`(줄머리 고정).
    """
    code = code_only(sql)
    begin = re.search(r"(?m)^begin;", code)
    lt = re.search(r"(?m)^set lock_timeout = '2s';", code)
    st = re.search(r"(?m)^set statement_timeout = '900s';", code)
    out = []
    if not begin:
        out.append("begin 없음")
    if not lt or not st:
        out.append("set lock_timeout / statement_timeout 없음")
    if begin and lt and lt.start() > begin.start():
        out.append("lock_timeout 이 begin 뒤")
    if begin and st and st.start() > begin.start():
        out.append("statement_timeout 이 begin 뒤")
    if re.search(r"(?im)^set\s+local\b", code):
        out.append("set local 있음")
    return out


class TestSwapAndLocks:
    def test_lock_timeout_and_statement_timeout_before_the_first_begin(self, mig):
        assert session_settings_problems(mig) == []

    def test_begin_commit_notify_order(self, mig):
        code = code_only(mig)
        begin = re.search(r"(?m)^begin;", code).start()
        commit = re.search(r"(?m)^commit;", code).start()
        notify = code.find("notify pgrst, 'reload schema';")
        assert begin < commit < notify
        assert len(re.findall(r"(?m)^begin;", code)) == 1 and len(re.findall(r"(?m)^commit;", code)) == 1
        for stmt in re.finditer(r"(?im)^(create|drop|alter|insert|revoke|grant|analyze|comment)\b", code):
            assert begin < stmt.start() < commit, "begin/commit 밖의 문장: " + stmt.group(0)
        assert "concurrently" not in code.lower()

    def test_slow_builds_come_before_any_screen_object_is_touched(self, mig):
        """⛔ 한 트랜잭션의 잠금은 commit 까지 — 화면 객체를 먼저 잠그면 굽는 2~3분 내내 화면이 선다."""
        code = code_only(mig)
        last_build = max(code.find("create materialized view {}_next as".format(n)) for n in SUMMARY_MVS)
        first_touch = min(
            code.find("create or replace view v_floor_stack as"),
            code.find("drop materialized view"),
            *(code.find("create or replace function {}(".format(n)) for n in REBUILT_FNS))
        assert -1 < last_build < first_touch

    def test_coverage_view_is_repointed_before_the_old_table_is_dropped(self, mig):
        code = code_only(mig)
        repoint = code.find("create or replace view v_coverage_stats as select * from mv_coverage_stats_next;")
        drop = code.find("drop materialized view mv_coverage_stats;")
        assert -1 < repoint < drop
        assert not re.search(r"(?im)^drop\s+view\b", code), "뷰를 drop 하면 anon 권한이 날아갑니다"

    @pytest.mark.parametrize("name", SUMMARY_MVS)
    def test_each_next_table_is_renamed_back(self, mig, name):
        code = code_only(mig)
        drop = code.find("drop materialized view {};".format(name))
        ren = code.find("alter materialized view {}_next rename to {};".format(name, name))
        assert -1 < drop < ren, name
        assert re.search(r"(?im)^revoke all on {}\s+from public, anon, authenticated;".format(name), code)
        assert re.search(r"(?im)^revoke all on {}_next from public, anon, authenticated;".format(name), code)

    @pytest.mark.parametrize("name", RENAMED_INDEXES)
    def test_each_index_gets_its_canonical_name(self, mig, schema, name):
        code = code_only(mig)
        assert re.search(r"(?im)^create (?:unique )?index {}_next\b".format(name), code), name
        assert re.search(r"(?im)^alter index {}_next\s+rename to {};".format(name, name), code), name
        assert re.search(r"(?im)^create (?:unique )?index if not exists {}\b".format(name), schema), name

    @pytest.mark.parametrize("view", ["v_floor_stack", "v_coverage_stats"])
    def test_security_invoker_is_written_again_after_replace(self, mig, view):
        """`create or replace view` 는 뷰 옵션을 새 정의로 갈아 끼운다 — 정본과 같게 다시 적는다."""
        code = code_only(mig)
        last_replace = code.rfind("create or replace view {} as".format(view))
        opt = code.find("alter view {} set (security_invoker = false);".format(view), last_replace)
        assert -1 < last_replace < opt

    def test_mutation_lock_timeout_after_begin_is_red(self, mig):
        """양성 대조 — lock_timeout 을 begin 뒤로 옮긴 사본은 위 판정에 걸린다."""
        bad = mig.replace("set lock_timeout = '2s';\n\nbegin;", "begin;\nset lock_timeout = '2s';", 1)
        assert bad != mig
        assert session_settings_problems(bad) == ["lock_timeout 이 begin 뒤"]


# ── 6. 머리말 — 적용 뒤 확인 목록 ────────────────────────────────────────────


def test_header_lists_the_after_apply_checks(mig):
    head = mig[: mig.index("set statement_timeout")]
    for needle in ("select * from snapshot_release;", "post_load.py --check",
                   "GET  /rest/v1/v_coverage_stats", "GET  /rest/v1/v_floor_stack",
                   "POST /rest/v1/rpc/list_industry_mix", "POST /rest/v1/rpc/get_data_freshness",
                   "POST /rest/v1/rpc/mark_snapshot_loaded", "401/403", "412px",
                   "되돌리기 = **새 마이그레이션 파일**"):
        assert needle in head, needle
