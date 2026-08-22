# -*- coding: utf-8 -*-
"""정본(schema.sql)의 `grant/revoke ... on function` 서명이 **실재하는 함수**를 가리키는지 지킨다.

왜 이 테스트가 있나 (2026-08-22 적대검증에서 확정)
--------------------------------------------------
권한 문장은 함수 이름만으로는 대상을 못 고른다 — 반드시 **인자 타입까지** 적어야 한다.
그래서 함수의 인자를 하나 바꾸면 권한 문장도 같이 고쳐야 하는데, 안 고치면
`ERROR: function search_scope(text) does not exist` 로 **DB 재생이 통째로 실패**한다.
그런데 이 실패는 라이브에 붙여 넣기 전까지는 아무도 못 본다 — CI 에는 DB 가 없다.

기존 가드는 부분문자열 검사였다(`"grant execute on function search_scope(text, text) to anon" in flat`).
그건 "anon 에게 열려 있나"는 잘 보지만 **서명이 맞나**는 못 본다. 실제로 같은 grant 가
파일 안에 두 벌 있던 동안, 한쪽을 옛 서명으로 되돌려도 다른 쪽이 부분문자열 검사를
만족시켜 테스트가 초록인 채 DB 재생만 깨졌다(돌연변이 시험으로 실증).

그래서 여기서는 글자 비교가 아니라 **기계 대조**를 한다:
  1) `create or replace function <이름>(<인자>)` 정의를 전부 파싱해 이름 → 인자 타입 묶음을 만든다.
  2) 파일 안의 모든 `grant|revoke ... on function <이름>(<타입목록>)` 을 훑으며
     그 서명이 1)의 묶음에 실제로 있는지 본다.
타입은 정규화해서 비교한다(`int`↔`integer`, `char(19)`↔`character(19)`, 대소문자·공백).

⚠️ 한계 (일부러 이 정도만 본다)
  · schema.sql 한 파일만 본다. 마이그레이션은 그때그때 라이브에 붙여 실행하며 바로 실패가
    보이지만, 정본은 "새 환경을 만들 때"까지 실패가 안 보이는 파일이라 여기가 급소다.
  · 인자 이름이 SQL 타입 이름과 같은 경우(`date text` 같은 선언)는 타입으로 오해할 수 있다.
    이 레포에는 그런 선언이 없고, 생기면 이 테스트가 빨간불로 알려 준다.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

# 이름 앞에 붙을 수 있는 스키마 접두(2026-08-22e 부터 api 스키마가 정본에 들어왔다).
SCHEMA_PREFIX = r"(public\.|api\.)?"

RE_CREATE_FN = re.compile(
    r"(?im)^create\s+(?:or\s+replace\s+)?function\s+" + SCHEMA_PREFIX + r"([a-z_][a-z0-9_]*)\s*\("
)
# 권한 문장은 **줄 맨 앞**에서 시작하는 것만 본다 — 설명 주석(`--  … revoke execute on
# function ... from anon`) 안의 인용문과 섞이면 안 된다.
RE_GRANT_FN = re.compile(
    r"(?im)^(grant|revoke)\b[^;]*?\bon\s+function\s+"
    + SCHEMA_PREFIX
    + r"([a-z_][a-z0-9_]*)\s*\("
)

# 같은 타입의 다른 이름들. 왼쪽으로 적어도 오른쪽으로 적어도 DB 에는 같은 함수다.
TYPE_ALIAS = {
    "int": "integer",
    "int2": "smallint",
    "int4": "integer",
    "int8": "bigint",
    "bool": "boolean",
    "char": "character",
    "varchar": "character varying",
    "float4": "real",
    "float8": "double precision",
    "decimal": "numeric",
    "timestamptz": "timestamp with time zone",
    "timetz": "time with time zone",
}

# 인자 선언에서 "이름 없이 타입만" 적힌 경우를 가려내기 위한 목록.
# (`double precision` 처럼 타입 자체가 두 낱말인 것을 인자 이름으로 오해하지 않게 한다.)
TYPE_HEADS = {
    "anyarray", "anyelement", "bigint", "bit", "bool", "boolean", "box", "bytea",
    "char", "character", "cidr", "circle", "date", "decimal", "double", "float4",
    "float8", "geography", "geometry", "inet", "int", "int2", "int4", "int8",
    "integer", "interval", "json", "jsonb", "line", "lseg", "macaddr", "money",
    "numeric", "path", "point", "polygon", "real", "record", "smallint", "text",
    "time", "timestamp", "timestamptz", "timetz", "tsquery", "tsvector", "uuid",
    "varchar", "void", "xml",
}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def schema_sql():
    return read(SCHEMA)


def scan_parens(sql, open_idx):
    """`(` 자리(open_idx)에서 시작해 짝이 맞는 `)` 까지 읽어 속과 끝자리를 돌려준다.

    `char(19)` 처럼 인자 안에 괄호가 또 들어가므로 정규식 `[^)]*` 로는 못 자른다.
    """
    depth = 0
    for i in range(open_idx, len(sql)):
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
            if depth == 0:
                return sql[open_idx + 1 : i], i
    raise AssertionError("schema.sql: 닫히지 않은 괄호가 있습니다 (자리 {})".format(open_idx))


def split_top_level(s):
    """괄호 밖의 쉼표로만 자른다 (`numeric(10, 2)` 를 둘로 쪼개지 않게)."""
    parts, buf, depth = [], [], 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def norm_type(t):
    """타입 표기를 한 모양으로 맞춘다 — 대소문자·공백·별칭."""
    t = re.sub(r"\s+", " ", t.strip().lower())
    t = re.sub(r"\s*\(\s*", "(", t)
    t = re.sub(r"\s*\)", ")", t)
    t = re.sub(r"\s*,\s*", ",", t)
    t = re.sub(r"\s*\[\s*\]", "[]", t)
    m = re.match(r"^([a-z_][a-z0-9_ ]*?)(\([^)]*\))?((?:\[\])*)$", t)
    if not m:
        return t
    head = m.group(1).strip()
    return TYPE_ALIAS.get(head, head) + (m.group(2) or "") + m.group(3)


def param_type(param):
    """인자 선언 한 칸(`lim int default 25`)에서 타입만 뽑는다."""
    p = re.sub(r"\s+", " ", param.strip())
    p = re.sub(r"(?i)^(?:in|out|inout|variadic)\s+", "", p).strip()
    p = re.sub(r"(?i)\s+default\s+.*$", "", p).strip()
    p = re.sub(r"\s*=\s*.*$", "", p).strip()
    head = p.split(" ", 1)[0]
    base = re.split(r"[(\[]", head)[0].lower()
    if " " in p and base not in TYPE_HEADS:
        p = p.split(" ", 1)[1]  # 첫 낱말은 인자 이름이었다
    return norm_type(p)


def qualified(prefix, name):
    """`public.` 는 기본 스키마라 붙이나 안 붙이나 같은 함수다 — 떼고 맞춘다.

    반대로 `api.` 는 떼면 안 된다. 같은 이름의 래퍼가 두 스키마에 나란히 있어서
    (api.search_buildings ↔ search_buildings) 뭉개면 서로가 서로를 가려 준다.
    """
    prefix = (prefix or "").lower()
    if prefix == "public.":
        prefix = ""
    return prefix + name.lower()


def parse_definitions(sql):
    """{함수 이름: {인자 타입 튜플, ...}}. 같은 이름의 오버로드도 담긴다."""
    defs = {}
    for m in RE_CREATE_FN.finditer(sql):
        name = qualified(m.group(1), m.group(2))
        inner, _ = scan_parens(sql, m.end() - 1)
        sig = tuple(param_type(p) for p in split_top_level(inner))
        defs.setdefault(name, set()).add(sig)
    return defs


def parse_grants(sql):
    """[(줄번호, 원문, 이름, 인자 타입 튜플), ...]"""
    out = []
    for m in RE_GRANT_FN.finditer(sql):
        name = qualified(m.group(2), m.group(3))
        inner, close = scan_parens(sql, m.end() - 1)
        sig = tuple(norm_type(t) for t in split_top_level(inner))
        line = sql.count("\n", 0, m.start()) + 1
        raw = re.sub(r"\s+", " ", sql[m.start() : close + 1]).strip()
        out.append((line, raw, name, sig))
    return out


def fmt_sig(name, sig):
    return "{}({})".format(name, ", ".join(sig))


def test_parser_sees_enough_to_be_meaningful(schema_sql):
    """가드가 0건을 훑고도 초록이 되는 일(조용한 무력화)을 막는다."""
    defs = parse_definitions(schema_sql)
    grants = parse_grants(schema_sql)
    assert len(defs) >= 20, "schema.sql: 함수 정의를 {}개밖에 못 찾았습니다 — 파서가 낡았습니다".format(
        len(defs)
    )
    assert len(grants) >= 30, (
        "schema.sql: 권한 문장을 {}개밖에 못 찾았습니다 — 파서가 낡았거나 문장이 사라졌습니다".format(
            len(grants)
        )
    )


def test_every_grant_signature_matches_a_real_function(schema_sql):
    """모든 grant/revoke 서명이 실재하는 함수를 가리켜야 한다.

    어긋나면 `psql -v ON_ERROR_STOP=1 -f schema.sql` 이 그 줄에서 통째로 멈춘다.
    """
    defs = parse_definitions(schema_sql)
    problems = []
    for line, raw, name, sig in parse_grants(schema_sql):
        if name not in defs:
            problems.append(
                "{}행: {} — 그런 이름의 함수 정의가 schema.sql 에 없습니다\n    문장: {}".format(
                    line, fmt_sig(name, sig), raw
                )
            )
        elif sig not in defs[name]:
            known = " / ".join(sorted(fmt_sig(name, s) for s in defs[name]))
            problems.append(
                "{}행: {} — 서명이 정의와 다릅니다\n    정의된 서명: {}\n    문장: {}".format(
                    line, fmt_sig(name, sig), known, raw
                )
            )
    assert not problems, (
        "schema.sql: 권한 문장의 함수 서명이 정의와 어긋납니다 — 이대로면 새 환경을 만들 때 "
        "`function ... does not exist` 로 재생이 멈춥니다.\n  " + "\n  ".join(problems)
    )


def test_checker_actually_rejects_a_wrong_signature():
    """대조가 진짜로 판별력이 있는지 — 일부러 어긋난 SQL 로 확인한다.

    이 확인이 없으면 파서가 조용히 아무것도 안 잡는 상태(정규식이 낡아 0건)여도
    위 테스트가 초록이 된다.
    """
    good = "create or replace function f(q text, lim int default 25)\nreturns int\n"
    assert parse_definitions(good) == {"f": {("text", "integer")}}

    # 맞는 서명 — 별칭·대소문자·공백이 달라도 같은 것으로 본다.
    ok = good + "GRANT EXECUTE ON FUNCTION f( TEXT , INT ) to anon;\n"
    defs = parse_definitions(ok)
    assert all(sig in defs[name] for _, _, name, sig in parse_grants(ok))

    # 틀린 서명 — 인자 하나를 빠뜨렸다.
    bad = good + "grant execute on function f(text) to anon;\n"
    defs = parse_definitions(bad)
    assert any(sig not in defs[name] for _, _, name, sig in parse_grants(bad))

    # 이름 자체가 없는 경우.
    missing = good + "revoke all on function g(text) from public;\n"
    defs = parse_definitions(missing)
    assert any(name not in defs for _, _, name, _ in parse_grants(missing))


def test_comment_lines_are_not_read_as_statements():
    """설명 주석 안에 인용된 권한 문장을 진짜 문장으로 오해하면 안 된다."""
    sql = (
        "create or replace function f(q text)\nreturns int\n"
        "--    아니면 `revoke execute on function zzz(text) from anon`).\n"
    )
    assert parse_grants(sql) == []


def test_char19_argument_is_normalized():
    """`char(19)` ↔ `character(19)` — pnu 컬럼 타입이라 언제든 서명에 나타날 수 있다."""
    sql = (
        "create or replace function f(p_pnu char(19))\nreturns int\n"
        "grant execute on function f(character(19)) to anon;\n"
    )
    defs = parse_definitions(sql)
    assert defs == {"f": {("character(19)",)}}
    assert all(sig in defs[name] for _, _, name, sig in parse_grants(sql))
