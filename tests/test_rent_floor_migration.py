# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-04a(층별 임대료·소득수익률 — 결정 0031)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙이기 전에는 아무도 모르는** 실수다. DB 없이 SQL 글자만 본다.

  ⓐ 함수 머리(`returns table`·`language sql`·`stable`·`security definer`·`set search_path`)와
     `comment on function` 이 정본(schema.sql)과 글자 그대로 같은가 — `create … function` 은 머리
     속성을 새 정의로 덮어쓰는데, 기존 드리프트 가드는 `$$` 안 본문만 본다(2026-10-01a 교훈:
     `set search_path` 가 빠지면 anon 경로가 죽어 카드가 사라지는데 시험은 초록이었다).
  ⓑ 두 함수의 돌려주는 칸 목록이 정본과 같고 새 두 칸(income_yield_rate·floor_rent)을 품는가 —
     화면 검증기는 칸 이름으로 고른다. 칸 하나가 빠지면 에러 없이 그 표만 사라진다.
  ⓒ 정본에 rent_stat 의 새 두 칸이 있는가(표 뒤 `alter table … add column` — 마이그레이션과 같은
     문장) · 그 문장이 표 정의 뒤, api.rent_stat 뷰 앞에 있는가(뷰가 먼저면 새 환경의 뷰에 칸이 없다).
  ⓓ 두 함수 본문 어디에도 floor_util_ratio 가 없는가 — 효용비율 미반출(결정 0024 유지)을 지키는
     **유일한** 시험이다(드리프트 가드는 정본과 같기만 하면 초록이다).
  ⓔ `set lock_timeout` 이 `begin;` 앞 · `begin;`/`commit;` 이 칸 추가·뷰·함수를 감싸고 ·
     `notify pgrst` 는 commit 뒤인가.
  ⓕ api.rent_stat 뷰를 칸 추가 **뒤에** 다시 만들고 권한을 다시 적는가 — `select *` 뷰는 만든
     날의 칸으로 굳어, 안 다시 만들면 적재기(REST = 이 뷰)가 새 두 칸을 못 넣는다.

⛔ 탐지는 이 파일 안의 작은 함수로 빼 두고, 가드 본체와 **양성 대조**(일부러 틀린 글)가 같은
   함수를 지나게 한다(레포 CLAUDE.md 2026-10-02 #190 규칙 — "없음" 단언만 있는 가드는 죽어도
   초록이다). 양성 대조에는 흔한 꼴과 변형 꼴을 함께 넣는다.
⚠️ 한계: 라이브에 적용됐는지·실제로 값이 오는지는 못 본다(CI 에 DB 가 없다). 그건 라이브 단계에서
   공개키로 `api.list_rent_stats` 를 실제로 불러 확인한다(결정 0031 PR-R1 #4).
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-04a_rent_floor_rent.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

DOLLAR = re.escape(chr(36) * 2)

# 함수 이름 — 탐지 정규식에 넣는 꼴. public 은 접두가 있어도 없어도 같은 함수다.
PUBLIC_FN = r"(?:public\.)?list_rent_stats"
API_FN = r"api\.list_rent_stats"

OLD_COLUMNS = ("district_nm", "rone_region_nm", "bld_type", "quarter",
               "vacancy_rate", "rent_per_m2", "yield_rate")
NEW_COLUMNS = ("income_yield_rate", "floor_rent")
NEW_TABLE_COLUMNS = {"floor_rent": "jsonb", "income_yield_rate": "numeric(5,2)"}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


@pytest.fixture(scope="module")
def migration():
    return read(MIGRATION)


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


# ── 탐지 함수 (본체와 양성 대조가 같은 함수를 지난다) ─────────────────────────


def statements(sql):
    """줄 전체 주석(`--` 로 시작하는 줄)을 걷은 실제 문장.

    ⛔ 원문을 보면 문장을 `--` 로 죽여도 글자가 남아 "있다"고 판정한다.
    """
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


def code_only(text):
    """줄 끝 주석까지 걷는다(`--` 부터 줄 끝).

    ⚠️ 못 보는 것: 작은따옴표 글 안의 `--` 도 주석으로 보고 자른다(이 두 함수 본문에는 그런 글이
       없다). 블록 주석(`/* … */`)도 걷는다.
    """
    text = re.sub(r"(?s)/\*.*?\*/", "", text)
    return "\n".join(re.sub(r"--.*$", "", ln) for ln in text.splitlines())


def function_head(sql, name_re):
    """`create [or replace] function <이름>(` 부터 `$$` 직전까지(머리). 없으면 None.

    줄머리(`^`)에 고정한다 — public 이름 정규식이 `api.list_rent_stats` 의 뒤쪽을 집지 않게.
    """
    m = re.search(
        r"(?ims)^create\s+(?:or\s+replace\s+)?function\s+" + name_re + r"\s*\(.*?(?=" + DOLLAR + r")",
        statements(sql))
    return m.group(0) if m else None


def function_body(sql, name_re):
    """머리 뒤 `$$ … $$` 본문(주석 포함 원문). 없으면 None."""
    m = re.search(
        r"(?ims)^create\s+(?:or\s+replace\s+)?function\s+" + name_re + r"\s*\(.*?"
        + DOLLAR + r"(.*?)" + DOLLAR + r"\s*;",
        statements(sql))
    return m.group(1) if m else None


def function_comment(sql, name_re):
    """`comment on function <이름>(text) is '…';` 문장 전체. 없으면 None."""
    m = re.search(
        r"(?ims)^comment\s+on\s+function\s+" + name_re + r"\s*\(\s*text\s*\)\s+is.*?';[ \t]*$",
        statements(sql))
    return m.group(0) if m else None


def returns_columns(head):
    """머리의 `returns table ( … )` → [(칸 이름, 타입)] (소문자·공백 하나로 접는다)."""
    m = re.search(r"(?is)returns\s+table\s*\((.*?)\)\s*language\b", head or "")
    if not m:
        return None
    out = []
    for part in m.group(1).split(","):
        words = part.split()
        if not words:
            continue
        out.append((words[0].lower(), " ".join(words[1:]).lower()))
    return out


def ratio_leaks(body):
    """본문(주석 걷음)이 효용비율을 내보낼 수 있는 꼴을 찾아 목록으로 돌려준다.

    잡는 것: `floor_util_ratio` 이름(대소문자·따옴표 무관) · 줄 통째(`r.*`) · 줄을 jsonb/json 으로
    통째 싣기(`to_jsonb(`·`row_to_json(`·`to_json(`).
    ⚠️ 못 보는 것: 동적 SQL(`execute format(…)`) 안에서 이름을 이어 붙이는 꼴 · 다른 함수를 불러
       그 안에서 내보내는 꼴(api 쌍둥이는 public 을 부르므로 public 본문 검사가 그 몫이다).
    """
    code = code_only(body or "")
    found = []
    if re.search(r"(?i)floor_util_ratio", code):
        found.append("floor_util_ratio")
    if re.search(r"\b\w+\s*\.\s*\*", code):
        found.append("줄 통째(별표)")
    if re.search(r"(?i)\b(?:to_jsonb|row_to_json|to_json)\s*\(", code):
        found.append("줄을 json 으로 통째")
    return found


def table_add_columns(sql):
    """`alter table [public.]rent_stat add column [if not exists] <이름> <타입>` → {이름: 타입}.

    한 alter 문장 안의 여러 `add column` 을 모두 본다(쉼표로 이어 쓴 꼴).
    """
    out = {}
    for stmt in re.findall(r"(?is)^\s*alter\s+table\s+(?:public\.)?rent_stat\b([^;]*);",
                           statements(sql), re.MULTILINE):
        for name, typ in re.findall(
                r"(?i)\badd\s+(?:column\s+)?(?:if\s+not\s+exists\s+)?(\w+)\s+([a-z]+(?:\s*\([^)]*\))?)",
                stmt):
            out[name.lower()] = re.sub(r"\s+", "", typ.lower())
    return out


def column_comments(sql):
    """`comment on column [public.]rent_stat.<칸> is '…';` → {칸: 문장 전체(공백 접음)}."""
    out = {}
    for m in re.finditer(
            r"(?ims)^comment\s+on\s+column\s+(?:public\.)?rent_stat\.(\w+)\s+is\s+.*?';[ \t]*$",
            statements(sql)):
        out[m.group(1).lower()] = re.sub(r"\s+", " ", m.group(0))
    return out


def _pos(pattern, text):
    m = re.search(pattern, text)
    return m.start() if m else None


RE_ALTER = r"(?im)^\s*alter\s+table\s+(?:public\.)?rent_stat\b"
RE_VIEW = (r"(?im)^\s*create\s+or\s+replace\s+view\s+api\.rent_stat\s+as\s+select\s+\*\s+"
           r"from\s+public\.rent_stat\s*;")
RE_VIEW_REVOKE = (r"(?im)^\s*revoke\s+all\s+on\s+(?:table\s+)?api\.rent_stat\s+from\s+"
                  r"public\s*,\s*anon\s*,\s*authenticated\s*;")


def order_problems(sql):
    """ⓔ·ⓕ 순서 판정 — 어긴 것을 사람이 읽을 문장의 목록으로(빈 목록 = 통과)."""
    low = statements(sql).lower()
    bad = []
    lock = _pos(r"(?m)^\s*set\s+lock_timeout\b", low)
    begin = _pos(r"(?m)^\s*begin\s*;", low)
    commit = _pos(r"(?m)^\s*commit\s*;", low)
    notify = _pos(r"(?m)^\s*notify\s+pgrst\b", low)
    alter = _pos(RE_ALTER, low)
    view = _pos(RE_VIEW, low)
    view_revoke = _pos(RE_VIEW_REVOKE, low)
    drops = [m.start() for m in re.finditer(r"(?m)^\s*drop\s+function\b", low)]
    creates = [m.start() for m in re.finditer(r"(?m)^\s*create\s+(?:or\s+replace\s+)?function\b", low)]

    if lock is None:
        bad.append("`set lock_timeout` 이 없습니다")
    if begin is None or commit is None:
        bad.append("`begin;`/`commit;` 이 없습니다")
        return bad
    if lock is not None and lock > begin:
        bad.append("`set lock_timeout` 이 `begin;` 뒤에 있습니다 — 세션 설정이라 앞에 둡니다")
    if alter is None:
        bad.append("rent_stat 칸 추가(alter table)가 없습니다")
    if view is None:
        bad.append("api.rent_stat 뷰를 다시 만들지 않습니다")
    if view_revoke is None:
        bad.append("api.rent_stat 뷰의 revoke 를 다시 적지 않습니다")
    if len(drops) < 2 or len(creates) < 2:
        bad.append("두 함수를 지우고 다시 만들지 않습니다")
    for label, pos in (("alter table", alter), ("뷰", view), ("뷰 revoke", view_revoke)):
        if pos is not None and not (begin < pos < commit):
            bad.append("{} 이(가) begin…commit 밖에 있습니다".format(label))
    for pos in drops + creates:
        if not (begin < pos < commit):
            bad.append("함수 drop/create 가 begin…commit 밖에 있습니다")
            break
    if alter is not None and view is not None and view < alter:
        bad.append("뷰를 칸 추가 **앞에** 다시 만듭니다 — 새 칸이 뷰에 안 실립니다")
    if notify is None:
        bad.append("`notify pgrst` 가 없습니다")
    elif notify < commit:
        bad.append("`notify pgrst` 가 `commit;` 앞에 있습니다")
    return bad


def grant_targets(sql):
    """`grant … on function <이름>(` 의 대상 이름(소문자) 목록 — list_rent_stats 만.

    ⚠️ 못 보는 것: 인자 괄호 없는 꼴 · 따옴표 이름 · `on all functions in schema`.
    """
    found = []
    for stmt in re.findall(r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*?\bon\s+function\b([^;]*)",
                           statements(sql)):
        found += re.findall(r"(?i)(?<![\w.])((?:\w+\.)?list_rent_stats)\s*\(", stmt)
    return [t.lower() for t in found]


# ── ⓐ 머리·comment 글자 대조 ──────────────────────────────────────────────────


@pytest.mark.parametrize("name_re", (PUBLIC_FN, API_FN), ids=("public", "api"))
def test_function_head_matches_the_schema(migration, schema, name_re):
    mh, sh = function_head(migration, name_re), function_head(schema, name_re)
    assert mh is not None and sh is not None, "함수 머리를 못 찾았습니다 — 정규식이 헛돕니다"
    assert mh == sh, "마이그레이션의 함수 머리가 정본과 글자가 다릅니다"
    low = mh.lower()
    assert "security definer" in low
    assert "language sql" in low
    assert re.search(r"(?im)^stable\s*$", mh), "stable 한 줄이 없습니다"
    expected_path = "set search_path = public" if name_re == PUBLIC_FN else "set search_path = ''"
    assert expected_path in low


def test_public_comment_matches_the_schema(migration, schema):
    mc, sc = function_comment(migration, PUBLIC_FN), function_comment(schema, PUBLIC_FN)
    assert mc is not None and sc is not None, "comment on function 을 못 찾았습니다"
    assert mc == sc, "마이그레이션의 comment 가 정본과 글자가 다릅니다"
    for word in ("소득수익률", "층별 ㎡당 임대료", "층별효용비율은 안 나간다"):
        assert word in mc, "comment 에 {!r} 이(가) 없습니다".format(word)


def test_head_and_comment_detectors_catch_a_one_letter_change(migration):
    """양성 대조 — 한 글자만 바꿔도 대조가 갈라지는가(흔한 꼴: search_path · 변형: comment 한 글자)."""
    bad_head = migration.replace("set search_path = public", "set search_path = pub1ic", 1)
    assert function_head(bad_head, PUBLIC_FN) != function_head(migration, PUBLIC_FN)
    no_definer = migration.replace("security definer\nset search_path = public", "set search_path = public", 1)
    assert "security definer" not in function_head(no_definer, PUBLIC_FN).lower()
    bad_comment = migration.replace("결정 0024·0031 이 필지가", "결정 0024·0031 이 필지기", 1)
    assert function_comment(bad_comment, PUBLIC_FN) != function_comment(migration, PUBLIC_FN)
    # 주석으로 죽인 문장은 "있다"로 세지 않는다.
    dead = re.sub(r"(?m)^comment on function list_rent_stats", "-- comment on function list_rent_stats",
                  migration)
    assert function_comment(dead, PUBLIC_FN) is None


def test_public_head_does_not_pick_the_api_twin():
    sql = ("create or replace function api.list_rent_stats(p_pnu text)\nreturns table (a text)\n"
           "language sql\nstable\nsecurity definer\nset search_path = ''\nas $$ select 1 $$;\n")
    assert function_head(sql, PUBLIC_FN) is None
    assert function_head(sql, API_FN) is not None


# ── ⓑ 돌려주는 칸 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name_re", (PUBLIC_FN, API_FN), ids=("public", "api"))
def test_returned_columns_match_and_include_the_new_two(migration, schema, name_re):
    mc = returns_columns(function_head(migration, name_re))
    sc = returns_columns(function_head(schema, name_re))
    assert mc and sc, "returns table 을 못 읽었습니다"
    assert mc == sc, "돌려주는 칸이 정본과 다릅니다: {} vs {}".format(mc, sc)
    names = [c for c, _ in mc]
    assert names == list(OLD_COLUMNS + NEW_COLUMNS), "칸 순서·구성이 다릅니다: {}".format(names)
    assert dict(mc)["floor_rent"] == "jsonb"
    assert dict(mc)["income_yield_rate"] == "numeric"
    assert "floor_util_ratio" not in names


def test_returns_columns_detector_sees_a_missing_or_renamed_column():
    good = ("create function list_rent_stats(p_pnu text)\nreturns table (\n  a text,\n"
            "  floor_rent jsonb\n)\nlanguage sql\nas $$ select 1 $$;\n")
    assert returns_columns(function_head(good, PUBLIC_FN)) == [("a", "text"), ("floor_rent", "jsonb")]
    renamed = good.replace("floor_rent jsonb", "FLOOR_RENTS   JSONB")
    assert returns_columns(function_head(renamed, PUBLIC_FN)) == [("a", "text"), ("floor_rents", "jsonb")]
    missing = good.replace(",\n  floor_rent jsonb", "")
    assert returns_columns(function_head(missing, PUBLIC_FN)) == [("a", "text")]


# ── ⓒ 정본의 새 칸 ───────────────────────────────────────────────────────────


def test_schema_and_migration_add_the_same_two_columns(migration, schema):
    assert table_add_columns(schema) == NEW_TABLE_COLUMNS
    assert table_add_columns(migration) == NEW_TABLE_COLUMNS


def test_schema_adds_the_columns_between_the_table_and_the_api_view(schema):
    """새 환경은 정본을 위에서부터 돈다 — 뷰가 칸 추가보다 먼저면 뷰에 새 칸이 없다."""
    code = statements(schema).lower()
    create_table = _pos(r"(?m)^create\s+table\s+if\s+not\s+exists\s+rent_stat\b", code)
    alter = _pos(RE_ALTER, code)
    view = _pos(RE_VIEW, code)
    assert None not in (create_table, alter, view)
    assert create_table < alter < view


def test_column_comments_match_and_the_old_claim_is_gone(migration, schema):
    mc, sc = column_comments(migration), column_comments(schema)
    for col in ("floor_rent", "income_yield_rate", "floor_util_ratio", "yield_rate"):
        assert col in mc, "마이그레이션에 {} 칸 주석이 없습니다".format(col)
        assert mc[col] == sc.get(col), "{} 칸 주석이 정본과 다릅니다".format(col)
    assert "유일한 공식 근거" not in sc["floor_util_ratio"]
    assert "분기 값" in sc["yield_rate"] and "투자수익률" in sc["yield_rate"]


def test_add_column_detector_catches_shapes():
    """양성 대조 — 흔한 꼴(쉼표로 이은 두 칸) · 변형(접두·대문자·if not exists 없음) · 죽인 줄."""
    common = ("alter table rent_stat\n  add column if not exists floor_rent jsonb,\n"
              "  add column if not exists income_yield_rate numeric(5,2);\n")
    assert table_add_columns(common) == NEW_TABLE_COLUMNS
    variant = "ALTER TABLE public.rent_stat ADD COLUMN floor_rent JSONB, ADD income_yield_rate NUMERIC (5, 2);\n"
    assert table_add_columns(variant) == NEW_TABLE_COLUMNS
    wrong_type = common.replace("numeric(5,2)", "numeric(8,2)")
    assert table_add_columns(wrong_type) != NEW_TABLE_COLUMNS
    dead = "-- alter table rent_stat add column floor_rent jsonb;\n"
    assert table_add_columns(dead) == {}


# ── ⓓ 효용비율 미반출 ────────────────────────────────────────────────────────


@pytest.mark.parametrize("which", ("migration", "schema"))
@pytest.mark.parametrize("name_re", (PUBLIC_FN, API_FN), ids=("public", "api"))
def test_no_function_body_exports_the_ratio(migration, schema, which, name_re):
    sql = migration if which == "migration" else schema
    body = function_body(sql, name_re)
    assert body is not None, "본문을 못 찾았습니다 — 정규식이 헛돕니다"
    assert ratio_leaks(body) == [], "효용비율을 내보낼 수 있는 꼴: {}".format(ratio_leaks(body))


@pytest.mark.parametrize("bad", [
    "select r.floor_util_ratio from rent_stat r",          # 흔한 꼴
    'select r."FLOOR_UTIL_RATIO" from rent_stat r',        # 변형: 따옴표·대문자
    "select r.* from rent_stat r",                          # 줄 통째
    "select to_jsonb(r) from rent_stat r",                  # json 으로 통째
    "select row_to_json (r) from rent_stat r",
])
def test_ratio_leak_detector_catches_shapes(bad):
    assert ratio_leaks(bad), "탐지가 {!r} 를 놓쳤습니다".format(bad)


def test_ratio_leak_detector_ignores_comments_only():
    assert ratio_leaks("  -- ⛔ floor_util_ratio 는 넣지 않는다\n  select r.floor_rent from rent_stat r") == []
    assert ratio_leaks("select 1 /* floor_util_ratio */") == []
    assert ratio_leaks(" select * from public.list_rent_stats(p_pnu) ") == []


# ── ⓔ·ⓕ 순서와 뷰 ───────────────────────────────────────────────────────────


def test_the_migration_order_is_right(migration):
    assert order_problems(migration) == []


@pytest.mark.parametrize("mutate,expect", [
    (lambda s: s.replace("set lock_timeout = '2s';\n\nbegin;", "begin;\nset lock_timeout = '2s';", 1),
     "begin;` 뒤에"),
    (lambda s: s.replace("set lock_timeout = '2s';", "", 1), "lock_timeout` 이 없습니다"),
    (lambda s: s.replace("\ncommit;\n", "\n", 1), "commit;` 이 없습니다"),
    (lambda s: s.replace("create or replace view api.rent_stat        as select * from public.rent_stat;",
                         "-- (뷰 없음)", 1), "뷰를 다시 만들지 않습니다"),
    (lambda s: s.replace("revoke all on api.rent_stat        from public, anon, authenticated;",
                         "", 1), "revoke 를 다시 적지 않습니다"),
    (lambda s: s.replace("\nnotify pgrst, 'reload schema';", "", 1).replace(
        "\ncommit;\n", "\nnotify pgrst, 'reload schema';\ncommit;\n", 1), "notify pgrst` 가 `commit;` 앞"),
])
def test_order_detector_catches_mutations(migration, mutate, expect):
    bad = mutate(migration)
    assert bad != migration, "변이가 적용되지 않았습니다 — 대조가 헛돕니다"
    problems = order_problems(bad)
    assert any(expect in p for p in problems), "탐지가 놓쳤습니다: {}".format(problems)


def test_order_detector_catches_a_view_rebuilt_before_the_columns():
    sql = ("set lock_timeout = '2s';\nbegin;\n"
           "create or replace view api.rent_stat as select * from public.rent_stat;\n"
           "revoke all on api.rent_stat from public, anon, authenticated;\n"
           "alter table rent_stat add column if not exists floor_rent jsonb;\n"
           "drop function if exists api.list_rent_stats(text);\n"
           "drop function if exists public.list_rent_stats(text);\n"
           "create or replace function list_rent_stats(p_pnu text) returns int language sql as $$ select 1 $$;\n"
           "create or replace function api.list_rent_stats(p_pnu text) returns int language sql as $$ select 1 $$;\n"
           "commit;\nnotify pgrst, 'reload schema';\n")
    assert any("칸 추가 **앞에**" in p for p in order_problems(sql))


# ── 권한 — api 만 열고 public 원본은 닫는다 ───────────────────────────────────


def test_only_the_api_twin_is_granted(migration):
    assert grant_targets(migration) == ["api.list_rent_stats"]
    assert re.search(r"(?im)^revoke\s+all\s+on\s+function\s+list_rent_stats\(text\)\s+from\s+"
                     r"public,\s*anon,\s*authenticated;", statements(migration))


@pytest.mark.parametrize("bad", [
    "grant execute on function list_rent_stats(text) to anon;",              # 흔한 꼴
    "  GRANT ALL ON FUNCTION public.list_rent_stats (text) TO anon;",          # 변형: 들여쓰기·all·접두
])
def test_grant_detector_catches_public_opening(bad):
    targets = grant_targets(bad)
    assert targets and targets != ["api.list_rent_stats"]
