# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-05a(호 목록 정렬 — 결정 0032 후속)의 불변식을 지킨다. DB 없이 SQL 글자만 본다.

이 판이 바꾸는 것은 public.list_floor_units 의 **정렬 하나**다. 그래서 지키는 것도 셋이다.

  ⓐ 정본(schema.sql)과 이 마이그레이션의 list_floor_units 머리·본문(라이브 prosrc 에 실리는 원문)·
     `comment on function` 이 글자 그대로 같은가 — 04b 의 같은 대조는 이 함수에 한해 여기로 옮겼다
     (tests/test_unit_table_migration.py 의 RECREATED_LATER). 이 판은 다른 함수를 만들지 않고
     grant 도 없다(api 쌍둥이는 통과라 그대로 새 정렬을 받는다).
  ⓑ 정렬 **밖**은 04b 와 같은가 — 층 종류 판정 블록(요약 함수와 글자 그대로)·거르기·쪽 나누기가
     조용히 바뀌지 않았는가. 같은 날 검토했다 뺀 'N세대' 갈래가 섞여 들지 않았는가.
  ⓒ 정렬 식의 모양 — 숫자 든 이름 먼저 · 끝 '호' 떼기 · 숫자/글자 덩어리로 나누기 · 숫자는 길이 세 자리
     접두 · 덩어리 배열을 collate "C" · 빈 배열은 NULL 로 맨 끝 · 마지막은 이름 → unit_id.
     그리고 예시 이름 표를 운영 PostgreSQL 이 실제로 이 정렬 식으로 세운 차례(PG_ORDER_TRUTH)와,
     같은 규칙을 파이썬으로 옮긴 거울이 그 차례를 그대로 내는지(엔진이 갈리면 거울이 헛말을 한다).
     바깥 정렬 열쇠는 **정확히 넷**이다(숫자 든 이름 · 덩어리 배열 · 이름 · unit_id) — 다섯째를 끼우면 빨강.
  ⓓ 적용된 04b 원장의 list_floor_units 블록·comment 는 SHA-256 못으로 지킨다 — 이 함수의 정본 대조가
     여기로 옮겨 온 뒤로는 04b 파일 속 그 글자를 아무 시험도 안 보기 때문이다(검사관 지적 2026-10-05).

⛔ 탐지는 이 파일 안의 작은 함수로 빼 두고 본체와 **양성 대조**(일부러 틀린 글)가 같은 함수를 지난다.
   양성 대조에는 흔한 꼴과 변형 꼴을 함께 넣는다(레포 CLAUDE.md 2026-10-02 #190).
ⓘ 도우미는 형제 test_unit_table_migration.py 에서 **복사**했다 — import 하지 않는다(시험 파일끼리 얽히면
   한쪽의 고장이 다른 쪽을 조용히 가린다).
⚠️ 한계: 라이브에 적용됐는지는 못 본다(CI 에 DB 가 없다). 정렬 식이 모양은 맞는데 PostgreSQL 이 다르게
   해석하는 꼴은 PG_ORDER_TRUTH(2026-10-05 운영 읽기 전용 실측)로만 지킨다 — 식을 바꾸면 그 표도 다시 잰다.
"""

import hashlib
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-05a_unit_order.sql")
PREVIOUS = os.path.join(ROOT, "supabase", "migrations", "2026-10-04b_unit_table.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

DOLLAR = re.escape(chr(36) * 2)
SUMMARY = "list_unit_floor_summary"
UNITS = "list_floor_units"
UNITS_SIG = "text, int, int, int"

# 적용된 2026-10-04b 의 list_floor_units 블록(`create or replace function list_floor_units(` 부터 `$$;` 앞까지)과
# `comment on function list_floor_units(…) is …;` 문장 원문(CRLF→LF)의 SHA-256.
# ⛔ 안 맞으면 "누군가 적용된 원장을 고쳤다"는 뜻이다 — 상수를 조용히 올리지 말고 파일을 되돌린다
#    (tests/test_search_gu_cast_migration.py 의 APPLIED_0910A_SHA 와 같은 관용구).
APPLIED_04B_UNITS_SHA = {
    "block": "6d1f64b722c168d88180698187aa4c2ca8caa40f474276b0eacc6df0f18451c7",
    "comment": "64f66b72e4a1a889c9ca4728912eb8fc14c9a04384a760d6ff565a8e1095986f",
}


def pub(name):
    return r"(?:public\.)?" + name


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


@pytest.fixture(scope="module")
def migration():
    return read(MIGRATION)


@pytest.fixture(scope="module")
def previous():
    return read(PREVIOUS)


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


# ── 탐지 함수 (형제 파일에서 복사 — 본체와 양성 대조가 같은 함수를 지난다) ──────────


def statements(sql):
    """줄 전체 주석(`--` 로 시작하는 줄)을 걷은 실제 문장."""
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


def code_only(text):
    """줄 끝 주석·블록 주석까지 걷는다. ⚠️ 작은따옴표 글 안의 `--` 도 자른다(이 본문엔 그런 글이 없다)."""
    text = re.sub(r"(?s)/\*.*?\*/", "", text)
    return "\n".join(re.sub(r"--.*$", "", ln) for ln in text.splitlines())


def flat(text):
    return re.sub(r"\s+", " ", text).strip()


def function_head(sql, name_re):
    """`create [or replace] function <이름>(` 부터 `$$` 직전까지. 없으면 None."""
    m = re.search(
        r"(?ims)^create\s+(?:or\s+replace\s+)?function\s+" + name_re + r"\s*\(.*?(?=" + DOLLAR + r")",
        statements(sql))
    return m.group(0) if m else None


def raw_function_body(sql, name_re):
    """`$$ … $$` 본문 원문(줄 전체 주석 그대로 — 라이브 pg_proc.prosrc 에 실리는 글자). 없으면 None."""
    m = re.search(
        r"(?ims)^create\s+(?:or\s+replace\s+)?function\s+" + name_re + r"\s*\(.*?"
        + DOLLAR + r"(.*?)" + DOLLAR + r"\s*;", sql)
    return m.group(1) if m else None


def function_comment(sql, name_re, sig):
    """`comment on function <이름>(<서명>) is '…';` 문장 전체. 없으면 None."""
    m = re.search(
        r"(?ims)^comment\s+on\s+function\s+" + name_re + r"\s*\(\s*" + re.escape(sig).replace(r"\ ", r"\s*")
        + r"\s*\)\s+is.*?';[ \t]*$",
        statements(sql))
    return m.group(0) if m else None


def created_functions(sql):
    """주석을 걷은 문장에서 `create [or replace] function <이름>(` 의 이름들(차례대로 · 소문자)."""
    return [m.group(1).lower() for m in re.finditer(
        r"(?im)^\s*create\s+(?:or\s+replace\s+)?function\s+([\w.]+)\s*\(", code_only(statements(sql)))]


def kind_block(raw_body):
    """본문 원문에서 층 종류 판정 블록 — `kind as (` 줄부터 `-- ▲ 층 종류 판정 끝` 줄 앞까지."""
    m = re.search(r"(?ms)^(\s*kind as \(\n.*?)^\s*-- ▲ 층 종류 판정 끝", raw_body or "")
    return m.group(1) if m else None


def grant_statements(sql):
    """주석을 걷은 뒤 `grant …;` 문장들(회수 `grant option for` 는 뺀다)."""
    return re.findall(r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*;", code_only(statements(sql)))


def order_problems(sql):
    """begin → DDL → commit → notify 순서 · drop 없음. 어긴 것의 목록(빈 목록 = 통과)."""
    low = statements(sql).lower()
    bad = []
    begin = re.search(r"(?m)^begin\s*;", low)
    commit = re.search(r"(?m)^commit\s*;", low)
    notify = re.search(r"(?m)^notify\s+pgrst\b", low)
    if not begin or not commit:
        return ["`begin;`/`commit;` 이 없습니다"]
    ddl = [m.start() for m in re.finditer(r"(?m)^(?:create|comment on|revoke|grant|drop|alter)\b", low)]
    if not ddl:
        return ["DDL 을 못 찾았습니다"]
    if any(not (begin.start() < p < commit.start()) for p in ddl):
        bad.append("begin…commit 밖에 DDL 이 있습니다")
    if not notify:
        bad.append("`notify pgrst` 가 없습니다")
    elif notify.start() < commit.start():
        bad.append("`notify pgrst` 가 `commit;` 앞에 있습니다")
    if re.search(r"(?m)^drop\b", low):
        bad.append("drop 이 있습니다 — 이 판은 다시 만들기만 한다")
    return bad


# ── 정렬 절 읽기 ─────────────────────────────────────────────────────────────────


def units_block(sql):
    """`create or replace function list_floor_units(` 부터 `$$;` 앞까지(머리 + 본문 원문 · 주석 포함)."""
    m = re.search(r"(?m)^create or replace function list_floor_units\(", sql)
    assert m, "list_floor_units 정의를 못 찾았습니다"
    return sql[m.start():sql.index(chr(36) * 2 + ";", m.start())]


def sha(text):
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def sort_clause(body):
    """목록 함수 본문(주석 걷고 공백 접음)에서 바깥 정렬 절 — `join kind` 뒤 첫 `order by` 부터 `limit`
    직전까지(앞뒤 공백 없이). 없으면 None.

    ⚠️ 못 보는 것: 정렬을 하위 질의로 옮기고 바깥을 다른 식으로 다시 정렬하는 꼴 · limit 가 없는 꼴(None).
    """
    code = flat(code_only(body or ""))
    m = re.search(r"(?i)\bjoin\s+kind\b.*?\border\s+by\s+(.*?)\s+limit\b", code)
    return m.group(1).strip() if m else None


# 정렬 열쇠 조각 — 대소문자·공백·별칭 이름과 무관하게. ⛔ collate 이름 "C" 만은 대소문자를 가린다
# (따옴표 이름이라 PostgreSQL 도 가린다 — "c" 는 다른 이름이다).
ALIAS_G = r"\w+\.g\[1\]"
STRIPPED = (r"coalesce\(\s*nullif\(\s*ltrim\(\s*" + ALIAS_G + r"\s*,\s*'0'\s*\)\s*,\s*''\s*\)\s*,\s*'0'\s*\)")
SORT_PARTS = {
    # 숫자가 든 이름이 먼저(맨 앞 열쇠)
    "digits_first": r"(?i)^coalesce\(\s*(?:\w+\.)?ho\s*~\s*'\[0-9\]'\s*,\s*false\s*\)\s+desc\s*,",
    # 이름 끝의 '호' 한 글자를 떼고 나눈다(안 떼면 '1층2호' 가 '1층2-3호' 뒤로 간다)
    "trim_ho": r"(?i)regexp_matches\(\s*regexp_replace\(\s*(?:\w+\.)?ho\s*,\s*'호\$'\s*,\s*''\s*\)\s*,",
    # 숫자 덩어리와 글자 덩어리 **둘 다** 꺼낸다(숫자만 꺼내면 옛 판처럼 가·나·다가 섞인다)
    "chunks": r"(?i)regexp_matches\(.*?,\s*'\[0-9\]\+\|\[\^0-9\]\+'\s*,\s*'g'\s*\)\s+with\s+ordinality\b",
    # 덩어리 차례대로
    "in_order": r"(?i)\border\s+by\s+\w+\.i\s*\)",
    # 숫자 덩어리 가지 — 길이 세 자리 접두 + 앞 0 뗀 숫자
    "length_prefix": (r"(?i)case\s+when\s+" + ALIAS_G + r"\s*~\s*'\^\[0-9\]'\s+then\s+lpad\(\s*length\(\s*"
                      + STRIPPED + r"\s*\)\s*::\s*text\s*,\s*3\s*,\s*'0'\s*\)\s*\|\|\s*" + STRIPPED
                      + r"\s+else\s+" + ALIAS_G + r"\s+end\b"),
    # 빈 배열(빈 이름·NULL) → NULL · 배열을 collate "C" 로 · 맨 끝으로
    "empty_last": r"(?i:nullif)\(\s*(?i:array)\(.*\)\s*,\s*'\{\}'\s*\)\s*(?i:collate)\s+\"C\"\s+(?i:(?:asc\s+)?nulls\s+last)\s*,",
    # 마지막 둘 — 이름(빈 글자도 NULL 과 같이 끝) → unit_id
    "tail": r"(?i),\s*nullif\(\s*(?:\w+\.)?ho\s*,\s*''\s*\)\s*(?:asc\s+)?nulls\s+last\s*,\s*(?:\w+\.)?unit_id$",
}


def sort_keys(clause):
    """정렬 절을 괄호 깊이 0 의 쉼표로 자른 바깥 열쇠들(작은따옴표 글 안의 괄호·쉼표는 세지 않는다).

    ⚠️ 못 보는 것: 큰따옴표 이름 안의 괄호·쉼표(지금 정렬 절엔 `"C"` 뿐이다) · `$$` 글.
    """
    keys, depth, quoted, cur = [], 0, False, ""
    for ch in clause or "":
        if ch == "'":
            quoted = not quoted
        elif not quoted and ch == "(":
            depth += 1
        elif not quoted and ch == ")":
            depth -= 1
        elif not quoted and depth == 0 and ch == ",":
            keys.append(cur.strip())
            cur = ""
            continue
        cur += ch
    if cur.strip():
        keys.append(cur.strip())
    return keys


def sort_shape(clause):
    """정렬 절 → {조각 이름: True/False} + 'no_numeric'(옛 판의 `::numeric` 이 안 남았나).

    four_keys = 바깥 열쇠(괄호 깊이 0 쉼표로 자른 것)가 정확히 넷 — 사이에 열쇠를 끼우면 False.
    ⚠️ 못 보는 것: 열쇠 수는 그대로 넷인데 가운데 두 열쇠(덩어리 배열 · 이름)의 **자리를 맞바꾼** 꼴은
       empty_last 의 뒤 쉼표·tail 의 앞 쉼표 조건으로만 일부 잡힌다 · 정규식이 PostgreSQL 에서 다르게
       읽히는 꼴(PG_ORDER_TRUTH 가 몫이다).
    """
    c = clause or ""
    out = {k: bool(re.search(p, c)) for k, p in SORT_PARTS.items()}
    out["no_numeric"] = bool(c) and not re.search(r"(?i)::\s*numeric\b", c)
    out["four_keys"] = len(sort_keys(c)) == 4
    return out


ALL_TRUE = {k: True for k in list(SORT_PARTS) + ["no_numeric", "four_keys"]}


# ── ⓐ 정본과 글자 대조 · 이 판이 만드는 것 ───────────────────────────────────────


def test_the_migration_recreates_only_list_floor_units(migration):
    assert created_functions(migration) == [UNITS], "이 판은 public.list_floor_units 하나만 다시 만든다"


def test_head_body_and_comment_match_the_schema(migration, schema):
    mh, sh = function_head(migration, pub(UNITS)), function_head(schema, pub(UNITS))
    assert mh is not None and sh is not None, "함수 머리를 못 찾았습니다 — 정규식이 헛돕니다"
    assert mh == sh, "마이그레이션의 함수 머리가 정본과 글자가 다릅니다"
    low = mh.lower()
    assert "language sql" in low and "security definer" in low and "set search_path = public" in low
    assert re.search(r"(?im)^stable\s*$", mh), "stable 한 줄이 없습니다"
    mb, sb = raw_function_body(migration, pub(UNITS)), raw_function_body(schema, pub(UNITS))
    assert mb is not None and mb == sb, "마이그레이션의 본문이 정본과 글자가 다릅니다(라이브 prosrc 가 갈린다)"
    mc, sc = function_comment(migration, pub(UNITS), UNITS_SIG), function_comment(schema, pub(UNITS), UNITS_SIG)
    assert mc is not None and mc == sc, "마이그레이션의 comment 가 정본과 글자가 다릅니다"
    assert "2026-10-05a" in mc and 'collate "C"' in mc and "결정 0032" in mc


def test_the_head_is_the_same_as_04b(migration, previous):
    """머리(서명·돌려주는 칸·권한 성질)는 안 바꾼다 — 바뀌면 api 쌍둥이의 통과가 깨진다."""
    assert function_head(migration, pub(UNITS)) == function_head(previous, pub(UNITS))


def test_no_grant_and_the_original_stays_closed(migration):
    assert grant_statements(migration) == []
    assert re.search(r"(?im)^revoke\s+all\s+on\s+function\s+list_floor_units\(" + re.escape(UNITS_SIG)
                     + r"\)\s+from\s+public,\s*anon,\s*authenticated;", statements(migration))


def test_the_migration_order_is_right(migration):
    assert order_problems(migration) == []


def test_detectors_catch_shapes(migration):
    """양성 대조 — 흔한 꼴(api 쌍둥이를 함께 다시 만듦 · grant 한 줄) · 변형(죽인 줄은 안 셈 · notify 를 앞으로)."""
    twin = migration.replace("\ncommit;\n", "\ncreate or replace function api.list_floor_units(p text)\n"
                             "returns int language sql as $$ select 1 $$;\ncommit;\n", 1)
    assert created_functions(twin) == [UNITS, "api.list_floor_units"]
    assert created_functions("-- create or replace function list_unit_floor_summary(p text)\n") == []
    assert grant_statements(migration + "\nGRANT EXECUTE ON FUNCTION public.list_floor_units(text, int, int, int)\n"
                            "  TO anon;\n")
    assert grant_statements("-- grant execute on function x(text) to anon;\n") == []
    moved = migration.replace("\nnotify pgrst, 'reload schema';", "", 1).replace(
        "\ncommit;\n", "\nnotify pgrst, 'reload schema';\ncommit;\n", 1)
    assert moved != migration and any("commit;` 앞" in p for p in order_problems(moved))


# ── ⓑ 정렬 밖은 04b 그대로 ─────────────────────────────────────────────────────


def without_sort(body):
    """주석 걷고 공백 접은 본문에서 바깥 정렬 절만 자리표시로 바꾼 것."""
    clause = sort_clause(body)
    assert clause is not None, "정렬 절을 못 찾았습니다"
    return flat(code_only(body)).replace(clause, "<SORT>", 1)


def test_only_the_sort_changed_since_04b(migration, previous):
    new_b, old_b = raw_function_body(migration, pub(UNITS)), raw_function_body(previous, pub(UNITS))
    assert sort_clause(new_b) != sort_clause(old_b), "정렬이 안 바뀌었습니다 — 이 판의 이유가 없다"
    assert without_sort(new_b) == without_sort(old_b), "정렬 밖(판정·거르기·쪽 나누기)이 04b 와 다릅니다"


def test_without_sort_detector_sees_a_change_outside_the_sort(migration, previous):
    """양성 대조 — 흔한 꼴(상한 200 → 300) · 변형(판정 블록 이름 목록에 갈래 하나 더)."""
    body = raw_function_body(migration, pub(UNITS))
    old = without_sort(raw_function_body(previous, pub(UNITS)))
    assert without_sort(body.replace("least(p_limit, 200)", "least(p_limit, 300)", 1)) != old
    assert without_sort(body.replace("|^공관$)'::text as home_re", "|^공관$|[0-9] *세대)'::text as home_re", 1)) != old


@pytest.mark.parametrize("which", ("migration", "schema"))
def test_the_kind_block_is_unchanged(migration, previous, schema, which):
    """판정 블록은 04b 그대로이고, 정본 요약 함수의 판정 블록과도 글자 그대로 같다(요약과 목록이 같은 말)."""
    sql = migration if which == "migration" else schema
    units = kind_block(raw_function_body(sql, pub(UNITS)))
    assert units is not None, "판정 블록을 못 찾았습니다"
    assert units == kind_block(raw_function_body(previous, pub(UNITS)))
    assert units == kind_block(raw_function_body(schema, pub(SUMMARY)))
    assert "세대)'::text as home_re" not in units, "같은 날 뺀 'N세대' 갈래가 섞여 들었습니다"


# ── ⓒ 정렬 식의 모양 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("which", ("migration", "schema"))
def test_the_sort_has_every_part(migration, schema, which):
    body = raw_function_body(migration if which == "migration" else schema, pub(UNITS))
    assert sort_shape(sort_clause(body)) == ALL_TRUE


def test_the_04b_sort_is_seen_as_the_old_shape(previous):
    """양성 대조(실물) — 옛 판 정렬은 덩어리·접두·collate·빈 배열 처리가 없고 `::numeric` 이 있다."""
    shape = sort_shape(sort_clause(raw_function_body(previous, pub(UNITS))))
    assert shape["digits_first"] and shape["tail"]
    for k in ("trim_ho", "chunks", "length_prefix", "empty_last", "no_numeric"):
        assert shape[k] is False, k
    assert shape["four_keys"] is True, "옛 판도 바깥 열쇠는 넷이었다"


def _mutate(text, old, new):
    assert text.count(old) == 1, "변이 자리를 못 찾았습니다 — 본문 모양이 바뀌었나: {!r}".format(old)
    return text.replace(old, new, 1)


PREFIX = "lpad(length(coalesce(nullif(ltrim(m.g[1], '0'), ''), '0'))::text, 3, '0')\n" \
         "                                         || "


@pytest.mark.parametrize("old,new,key", [
    # 흔한 꼴 — collate 를 지움(데이터베이스 기본 en_US 로 견준다)
    ("'{}') collate \"C\" asc nulls last", "'{}') asc nulls last", "empty_last"),
    # 변형 — collate 이름 대소문자 · nulls first · 빈 배열 처리 지움
    ("'{}') collate \"C\" asc nulls last", "'{}') collate \"c\" asc nulls last", "empty_last"),
    ("'{}') collate \"C\" asc nulls last", "'{}') collate \"C\" asc nulls first", "empty_last"),
    ("order by m.i), '{}') collate \"C\" asc nulls last", "order by m.i)) collate \"C\" asc nulls last",
     "empty_last"),
    # 길이 접두를 지움 · 고정 폭 채우기로 바꿈
    (PREFIX, "", "length_prefix"),
    (PREFIX + "coalesce(nullif(ltrim(m.g[1], '0'), ''), '0')", "lpad(m.g[1], 20, '0')", "length_prefix"),
    # 숫자 덩어리만 꺼냄(옛 판) · 끝 '호' 떼기를 지움
    ("'[0-9]+|[^0-9]+', 'g'", "'[0-9]+', 'g'", "chunks"),
    ("regexp_replace(u.ho, '호$', '')", "u.ho", "trim_ho"),
    # 덩어리 차례를 잃음
    ("order by m.i), '{}')", "), '{}')", "in_order"),
    # 숫자 든 이름 먼저를 뒤집음 · 마지막 unit_id 를 지움
    ("coalesce(u.ho ~ '[0-9]', false) desc,", "coalesce(u.ho ~ '[0-9]', false) asc,", "digits_first"),
    ("nulls last,   -- 빈 글자도 NULL 과 같이 맨 끝\n           u.unit_id", "nulls last", "tail"),
    # 열쇠를 하나 더 끼움 — 맨 앞 열쇠 뒤 · 이름 열쇠 앞(검사관 지적: 둘 다 시험 123개가 초록이었다)
    ("coalesce(u.ho ~ '[0-9]', false) desc,", "coalesce(u.ho ~ '[0-9]', false) desc, length(u.ho) desc,",
     "four_keys"),
    ("           nullif(u.ho, '') asc nulls last,", "           length(u.ho) desc,\n           nullif(u.ho, '') asc nulls last,",
     "four_keys"),
])
def test_sort_detector_catches_mutations(migration, old, new, key):
    body = raw_function_body(migration, pub(UNITS))
    assert sort_shape(sort_clause(_mutate(body, old, new)))[key] is False


def test_sort_detector_accepts_the_same_meaning_in_other_letters(migration):
    """양성 대조(통과 쪽) — 대문자 키워드 · asc 생략은 같은 뜻이다."""
    body = raw_function_body(migration, pub(UNITS))
    upper = _mutate(body, "'{}') collate \"C\" asc nulls last", "'{}') COLLATE \"C\" NULLS LAST")
    upper = _mutate(upper, "coalesce(u.ho ~ '[0-9]', false) desc,", "COALESCE(ho ~ '[0-9]', FALSE) DESC,")
    assert sort_shape(sort_clause(upper)) == ALL_TRUE


# 운영 PostgreSQL(17 · 기본 정렬 규칙 en_US.UTF-8)이 정본의 정렬 절을 **글자 그대로** 예시 표에 돌려 세운 차례
# (2026-10-05 읽기 전용 실측 · begin…rollback 임시 표). 숫자 든 이름 먼저 · 같은 글자 덩어리끼리 · 수는 수로
# (9층 < 10층 · 20자리 < 23자리) · 'N호' 가 'N-M호' 앞 · 대문자가 소문자 앞(바이트 순) · 빈 이름·NULL 맨 끝.
PG_ORDER_TRUTH = [
    "0", "00", "001호", "1호", "1층2호", "1층2-1호", "1층2-3호", "1층2호가", "1층10호",
    "3가001호", "3가002호", "3가010호", "3나001호", "3나002호", "3다001호",
    "9층101호", "10층101호", "101호", "101동901호", "101동1001호", "102동101호",
    "402-1-1", "402-1-2", "402-1-10", "402-1-가",
    "99999999999999999999호", "12345678901234567890123호",
    "A1", "A-1", "B1", "B1가001호", "B2가001호", "B2나001호", "B101호", "B102호", "a1", "지하101호",
    "관리사무소", "상가", "호", "", None,
]
# 실측 때 넣은 차례(unit_id = 1부터) — 동률 마지막 기준(unit_id)이 이 차례를 따른다.
EXAMPLE_INPUT = [
    "3나001호", "3가002호", "3가001호", "3다001호", "3가010호", "3나002호",
    "10층101호", "9층101호", "101동1001호", "101동901호", "102동101호",
    "B101호", "B102호", "101호", "지하101호", "1층2호", "1층2-1호", "1층2-3호", "1층10호", "1층2호가",
    "A1", "A-1", "001호", "1호", "상가", "관리사무소", "호", "", None,
    "a1", "B1", "0", "00", "12345678901234567890123호", "99999999999999999999호",
    "B2가001호", "B2나001호", "B1가001호", "402-1-가", "402-1-1", "402-1-10", "402-1-2",
]


def mirror_key(item, trim_ho=True, empty_last=True):
    """정렬 절을 파이썬으로 옮긴 거울 — (unit_id, ho) → 정렬 열쇠.

    collate "C" = UTF-8 바이트 순 · 배열 비교 = 원소별(앞이 같으면 짧은 쪽이 먼저) = 파이썬 튜플 비교.
    ⓘ 이름 동률 기준(nullif(ho, ''))은 운영에선 en_US 규칙이라 이 거울은 그걸 옮기지 못한다 — 예시 표의
       동률('0'·'00', '001호'·'1호')은 두 규칙의 답이 같은 꼴만 골랐다.
    """
    unit_id, ho = item
    has_digit = ho is not None and re.search(r"[0-9]", ho) is not None
    pieces = []
    for c in re.findall(r"[0-9]+|[^0-9]+", re.sub(r"호$", "", ho or "") if trim_ho else (ho or "")):
        if c[0].isdigit():
            t = c.lstrip("0") or "0"
            c = "{:03d}".format(len(t)) + t
        pieces.append(c.encode("utf-8"))
    key = tuple(pieces) or None
    name = ho or None
    return (not has_digit, empty_last and key is None, key or (), name is None, name or "", unit_id)


def mirror_sort(names, **kw):
    return [ho for _, ho in sorted(enumerate(names, start=1), key=lambda it: mirror_key(it, **kw))]


def test_the_python_mirror_gives_the_postgres_order():
    assert sorted(EXAMPLE_INPUT, key=lambda x: (x is None, x or "")) == \
        sorted(PG_ORDER_TRUTH, key=lambda x: (x is None, x or "")), "두 표의 원소가 다릅니다"
    assert mirror_sort(EXAMPLE_INPUT) == PG_ORDER_TRUTH


def test_the_order_says_what_the_owner_decided():
    """👤 2026-10-05 결정을 사람 말로 — 같은 글자 덩어리끼리 · 수는 수로 · 'N호' 먼저 · 빈 이름 끝."""
    order = PG_ORDER_TRUTH
    ga = [order.index(x) for x in ("3가001호", "3가002호", "3가010호")]
    assert ga == sorted(ga) and max(ga) < order.index("3나001호") < order.index("3다001호")
    assert order.index("9층101호") < order.index("10층101호")
    assert order.index("101동901호") < order.index("101동1001호") < order.index("102동101호")
    assert order.index("1층2호") < order.index("1층2-1호") < order.index("1층2-3호") < order.index("1층10호")
    assert order[-2:] == ["", None]
    assert all(order.index(x) < order.index("관리사무소") for x in order if x and re.search("[0-9]", x))


def test_the_mirror_detects_the_old_mistakes():
    """양성 대조 — 거울에서 '호' 떼기를 빼면 'N호' 가 'N-M호' 뒤로 · 빈 배열을 맨 끝으로 안 보내면 빈 이름이
    숫자 없는 이름 앞으로(이 두 결함이 실제로 표를 바꾸는지 — 바꾸지 않으면 표가 그 결함을 못 지킨다)."""
    no_trim = mirror_sort(EXAMPLE_INPUT, trim_ho=False)
    assert no_trim != PG_ORDER_TRUTH and no_trim.index("1층2-3호") < no_trim.index("1층2호")
    empty_first = mirror_sort(EXAMPLE_INPUT, empty_last=False)
    assert empty_first.index("") < empty_first.index("관리사무소")


# ── ⓓ 적용된 04b 원장 못 ──────────────────────────────────────────────────────


def test_the_applied_04b_units_block_and_comment_are_nailed(previous):
    """⛔ 적용된 마이그레이션 파일은 고치지 않는다(CLAUDE.md) — 이 함수의 정본 대조가 이 파일로 옮겨 온 뒤로는
    04b 속 정렬 절·주석·comment 를 다른 시험이 안 본다. dev·staging 을 재생으로 세우면 이 파일이 다시 돈다."""
    assert sha(units_block(previous)) == APPLIED_04B_UNITS_SHA["block"], (
        "적용된 2026-10-04b 의 list_floor_units 블록이 바뀌었습니다 — 되돌리세요(상수를 올리지 말 것)")
    assert sha(function_comment(previous, pub(UNITS), UNITS_SIG)) == APPLIED_04B_UNITS_SHA["comment"], (
        "적용된 2026-10-04b 의 list_floor_units comment 가 바뀌었습니다 — 되돌리세요(상수를 올리지 말 것)")


@pytest.mark.parametrize("old,new,which", [
    # 흔한 꼴 — 정렬 방향 한 군데 · 변형 — 주석 한 글자 · comment 한 구절
    ("order by m.i),", "order by m.i desc),", "block"),
    ("-- 자연 정렬: 숫자가 든 이름 먼저", "-- 자연 정렬: 숫자가 든 이름 먼져", "block"),
    ("자연 정렬(이름 안 숫자 덩어리 전부를 numeric 으로)", "자연 정렬(이름 안 숫자 덩어리를 numeric 으로)", "comment"),
])
def test_the_04b_nail_really_bites(previous, old, new, which):
    """⛔ 해시 못이 헛돌면(늘 같은 것을 해시) 적용된 판이 바뀌어도 초록이다 — 한 글자 바꾼 사본은 해시가 달라야 한다."""
    assert previous.count(old) == 1, "변이 자리를 못 찾았습니다: {!r}".format(old)
    tampered = previous.replace(old, new, 1)
    got = sha(units_block(tampered)) if which == "block" else sha(
        function_comment(tampered, pub(UNITS), UNITS_SIG))
    assert got != APPLIED_04B_UNITS_SHA[which]
