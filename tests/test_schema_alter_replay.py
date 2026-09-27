# -*- coding: utf-8 -*-
"""마이그레이션을 **순서대로 되짚은 최종 상태**가 정본(schema.sql)과 같은가 — ALTER 로만 바뀐 성질.

왜 이 파일이 필요했나 (2026-09-27)
----------------------------------
2026-09-23 에 라이브의 두 가지가 **ALTER 문으로만** 바뀌었다(마이그레이션 `2026-09-23a/b/c`).

  · 확장 `pg_trgm` 을 `public` → `extensions` 스키마로 옮김(`ALTER EXTENSION … SET SCHEMA`)
  · 헬퍼 함수 7개에 `search_path` 고정(`ALTER FUNCTION … SET search_path = …`),
    그중 `search_key`·`price_floor_band` 는 속도 때문에 다시 해제(`… RESET search_path`)

그런데 정본 `supabase/schema.sql` 은 **4일 동안 옛 상태**를 말했고, 사람이 손으로 찾아
고쳤다(PR #155). 기존 드리프트 가드 `tests/test_schema_function_drift.py` 는 `$$` **안쪽
본문**만 맞춘다 — 그 함수들을 처음 만든 8월 판에는 `set search_path` 절이 없었으므로 그
가드는 **원리적으로** 이 드리프트를 볼 수 없었다(본문은 한 글자도 안 바뀌었다).

무엇을 보나
-----------
마이그레이션을 파일 이름순(= 시간순, `YYYY-MM-DD?_설명.sql`)으로 한 문장씩 되짚는다.

  · 함수 = (스키마.이름, 인자 **타입** 목록) 마다 "설정 절(GUC 이름 → 값)" 상태를 만든다.
    `create [or replace] function` 은 그 머리의 `set` 절로 상태를 **덮어쓴다**(PostgreSQL 도
    `create or replace` 가 설정을 통째로 갈아 끼운다). `ALTER FUNCTION … SET/RESET` 은 그 위에
    차례로 적용한다. `drop function` 은 상태를 지운다.
  · 확장 = 이름마다 스키마. `create extension … [with] schema X`(없으면 `public`)와
    `ALTER EXTENSION … SET SCHEMA X` 를 차례로 적용한다.
  · **ALTER 가 한 번이라도 닿은 함수·확장은 전부** 정본의 같은 대상과 대조한다. 정본 쪽도
    같은 엔진으로 되짚는다(지금 정본엔 ALTER 가 없어 create 머리만 보는 것과 같다).

값은 대소문자·공백·따옴표만 접는다. **순서는 보존한다** — `search_path` 는 순서가 의미다.

⛔ 조용히 넘기지 않는 것
  · 이 가드가 모르는 `ALTER FUNCTION` 형태(이름 바꾸기·소유자·스키마 옮기기·security·
    휘발성·인자 목록 없음 등) → **빨강**. 처리 규칙을 먼저 더하라는 뜻이다. 모르는 형태를
    넘기면 "되짚은 상태"가 그 순간부터 거짓이 된다.
  · `ALTER EXTENSION` 은 `SET SCHEMA` 와 버전 올리기(`UPDATE`)만 안다. 그 밖은 빨강.
  · `ALTER ROUTINE`(함수에도 `SET` 을 걸 수 있는 별명 문장)도 빨강 — 이 가드를 옆으로 돌아가는 길이다.
  · 대조 대상이 0개면 빨강(빈 대조가 초록이 되는 길을 막는다).

주석·인용에 안 속는 법
  문장을 자르기 전에 `--`·`/* */` 주석을 걷고, `'…'`·`"…"`·`$$…$$` 는 통째로 한 덩어리로
  다룬다(달러 본문은 자리표시로 바꾼다). 그런 뒤 **문장 머리에 앵커**를 둔다. 그래서 23a 머리말의
  ROLLBACK 주석(`-- ALTER FUNCTION … RESET search_path;` 7줄)이나 `comment on … is '…'` 안의
  글자는 상태를 바꾸지 못한다.

⚠️ 한계 (정직하게 적어 둔다)
  · **글자만 본다.** 라이브에 그 마이그레이션이 실제로 적용됐는지는 안 본다(CI 에 DB 가 없다).
  · 동적 SQL(`execute 'alter function …'`)은 달러 본문 안이라 안 보인다.
  · 역할(롤) 단위 설정(`alter role … set search_path`)은 함수 성질이 아니라 대상이 아니다.
  · ALTER 가 한 번도 닿지 않은 함수의 create 머리 `set` 절 드리프트는 여기서 안 본다(대조 범위는
    'ALTER 가 닿은 것'으로 좁게 잡았다 — 넓히려면 먼저 전수 실측).
"""

import io
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIG_DIR = os.path.join(ROOT, "supabase", "migrations")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

BODY = "__BODY__"          # 달러 본문 자리표시(문장 분리·머리 파싱에서 본문 글자를 치운다)
DOLLAR_TAG_RE = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")

# 9/23 에 ALTER 로만 바뀐 함수 7개 — 파서가 이것들을 못 찾으면 대조가 헛돈 것이다.
KNOWN_0923_TARGETS = {
    "public.building_display_nm(text,text)",
    "public.mask_person_name(text)",
    "public.parcel_jibun_addr(text,text,text,text)",
    "public.search_scope_limit()",
    "public.unit_business_append_only()",
    "public.search_key(text)",
    "public.price_floor_band(smallint)",
}


# ---------------------------------------------------------------------------
# 1. 문장 자르기 (주석 걷기 · 인용 덩어리 · 달러 본문 자리표시)
# ---------------------------------------------------------------------------

def split_statements(sql):
    """SQL 을 `;` 로 자른다. 주석은 공백으로, 달러 본문은 `__BODY__` 로 바꾼다.

    `'…'`·`"…"` 안의 `;`·`--` 는 자르지 않는다. 블록 주석은 PostgreSQL 처럼 겹쳐 쓸 수 있다.
    """
    out, buf = [], []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j
            buf.append(" ")
        elif sql.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if sql.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif sql.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            if depth:
                raise ValueError("닫히지 않은 블록 주석")
            buf.append(" ")
            i = j
        elif c in ("'", '"'):
            j = i + 1
            while True:
                j = sql.find(c, j)
                if j < 0:
                    raise ValueError("닫히지 않은 인용({})".format(c))
                if sql.startswith(c * 2, j):      # '' / "" = 이스케이프
                    j += 2
                    continue
                break
            buf.append(sql[i:j + 1])
            i = j + 1
        elif c == "$":
            m = DOLLAR_TAG_RE.match(sql, i)
            if m:
                end = sql.find(m.group(0), m.end())
                if end < 0:
                    raise ValueError("닫히지 않은 달러 인용 {}".format(m.group(0)))
                buf.append(" {} ".format(BODY))
                i = end + len(m.group(0))
            else:
                buf.append(c)
                i += 1
        elif c == ";":
            out.append("".join(buf))
            buf = []
            i += 1
        else:
            buf.append(c)
            i += 1
    if "".join(buf).strip():
        out.append("".join(buf))
    return [s.strip() for s in out if s.strip()]


TOKEN_RE = re.compile(
    r"\s*(?:"
    r"('(?:[^']|'')*')"                       # 1 문자열
    r"|(\"(?:[^\"]|\"\")*\")"                 # 2 따옴표 식별자
    r"|([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)*|[\d][\w.]*)"   # 3 단어(점 이름 포함)·숫자
    r"|(\S)"                                  # 4 기호 한 글자
    r")"
)


def tokenize(stmt):
    toks, pos = [], 0
    stmt = stmt.rstrip()
    while pos < len(stmt):
        m = TOKEN_RE.match(stmt, pos)
        if not m or m.end() == pos:
            break
        toks.append(m.group(m.lastindex))
        pos = m.end()
    return toks


def low(tok):
    return tok.lower()


def unquote_ident(tok):
    if tok.startswith('"') and tok.endswith('"'):
        return tok[1:-1].replace('""', '"')
    return tok.lower()


# ---------------------------------------------------------------------------
# 2. 함수 서명 (이름 + 인자 타입 — 인자 이름·기본값 제외)
# ---------------------------------------------------------------------------

TYPE_ALIASES = {
    "int": "integer", "int4": "integer", "integer": "integer",
    "int2": "smallint", "smallint": "smallint",
    "int8": "bigint", "bigint": "bigint",
    "bool": "boolean", "boolean": "boolean",
    "varchar": "varchar", "character varying": "varchar",
    "char": "bpchar", "character": "bpchar", "bpchar": "bpchar",
    "float8": "float8", "double precision": "float8",
    "float4": "float4", "real": "float4",
    "decimal": "numeric", "numeric": "numeric",
    "timestamptz": "timestamptz", "timestamp with time zone": "timestamptz",
    "timestamp": "timestamp", "timestamp without time zone": "timestamp",
    "timetz": "timetz", "time with time zone": "timetz",
    "time": "time", "time without time zone": "time",
}
# 두 단어 이상으로 된 타입의 첫 단어 — 이것으로 시작하면 인자 이름이 없는 것으로 본다.
MULTIWORD_TYPE_STARTS = {"double", "character", "timestamp", "time", "bit", "national", "interval"}
ARG_MODES = {"in", "out", "inout", "variadic"}


def split_top_level(tokens, sep=","):
    parts, cur, depth = [], [], 0
    for t in tokens:
        if t in ("(", "["):
            depth += 1
        elif t in (")", "]"):
            depth -= 1
        if t == sep and depth == 0:
            parts.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        parts.append(cur)
    return parts


def norm_type(tokens):
    # 타입 수식어 `(19)` 는 함수 서명에서 버려진다(PostgreSQL 규칙) — 괄호 묶음을 걷는다.
    words, depth, arr = [], 0, ""
    for t in tokens:
        if t == "(":
            depth += 1
        elif t == ")":
            depth -= 1
        elif depth == 0:
            if t == "[":
                arr += "[]"
            elif t == "]":
                pass
            else:
                words.append(low(t))
    base = " ".join(words)
    for pre in ("pg_catalog.", "public."):
        if base.startswith(pre):
            base = base[len(pre):]
    return TYPE_ALIASES.get(base, base) + arr


def arg_types(arg_tokens):
    """괄호 안 토큰 → 입력 인자 타입 튜플(OUT 인자는 서명에서 빠진다)."""
    types = []
    for arg in split_top_level(arg_tokens):
        cut = len(arg)
        for k, t in enumerate(arg):
            if low(t) == "default" or t == "=":
                cut = k
                break
        arg = arg[:cut]
        if not arg:
            continue
        if low(arg[0]) in ARG_MODES and len(arg) > 1:
            if low(arg[0]) == "out":
                continue
            arg = arg[1:]
        if (len(arg) >= 2 and low(arg[0]) not in MULTIWORD_TYPE_STARTS
                and arg[1] not in ("(", "[", ".", "%")):
            arg = arg[1:]            # 첫 단어는 인자 이름
        types.append(norm_type(arg))
    return tuple(types)


def qualify(name_tok):
    parts = [unquote_ident(p) for p in name_tok.split(".")]
    if len(parts) == 1:
        parts = ["public"] + parts
    return ".".join(parts)


def fn_key(name, types):
    return "{}({})".format(name, ",".join(types))


def take_paren_group(tokens, k):
    """tokens[k] == '(' 일 때 짝 괄호까지의 안쪽 토큰과 그 다음 위치."""
    assert tokens[k] == "("
    depth, j = 0, k
    while j < len(tokens):
        if tokens[j] == "(":
            depth += 1
        elif tokens[j] == ")":
            depth -= 1
            if depth == 0:
                return tokens[k + 1:j], j + 1
        j += 1
    raise ValueError("닫히지 않은 괄호")


# ---------------------------------------------------------------------------
# 3. 설정 절(GUC) 읽기
# ---------------------------------------------------------------------------

def norm_value_item(tok):
    if tok[0] in ("'", '"'):
        tok = tok[1:-1]
    return tok.strip().lower()


def read_value_list(tokens, k):
    """`a, b, c` 목록을 읽어 정규화한 문자열과 다음 위치를 돌려준다(순서 보존)."""
    items = []
    if k >= len(tokens):
        raise ValueError("값이 없음")
    items.append(norm_value_item(tokens[k]))
    k += 1
    while k + 1 < len(tokens) and tokens[k] == ",":
        items.append(norm_value_item(tokens[k + 1]))
        k += 2
    return ", ".join(items), k


def read_set_clause(tokens, k):
    """tokens[k] == 'set' 일 때 (guc, 값, 다음 위치). 모르는 모양이면 None."""
    if k + 2 >= len(tokens):
        return None
    guc = tokens[k + 1]
    op = low(tokens[k + 2])
    if not re.match(r"^[A-Za-z_][\w.]*$", guc) or op not in ("=", "to"):
        return None           # `set schema x` · `set … from current` 등
    value, nxt = read_value_list(tokens, k + 3)
    return low(guc), value, nxt


class UnknownForm(Exception):
    pass


def create_head_settings(attr_tokens):
    """create function 의 `)` 뒤 속성 토큰에서 `set` 절을 모은다(괄호 안은 건너뜀)."""
    cfg, depth, k = {}, 0, 0
    while k < len(attr_tokens):
        t = attr_tokens[k]
        if t == "(":
            depth += 1
        elif t == ")":
            depth -= 1
        elif depth == 0 and low(t) == "set":
            got = read_set_clause(attr_tokens, k)
            if got is None:
                raise UnknownForm("create function 머리의 set 절을 읽지 못함: "
                                  + " ".join(attr_tokens[k:k + 6]))
            guc, value, k = got
            cfg[guc] = value
            continue
        k += 1
    return cfg


def alter_actions(tokens, k):
    """ALTER FUNCTION 서명 뒤 동작 목록. 아는 것은 SET <guc> =|TO … · RESET <guc>|ALL · 끝의 RESTRICT."""
    acts = []
    while k < len(tokens):
        t = low(tokens[k])
        if t == "set":
            got = read_set_clause(tokens, k)
            if got is None:
                raise UnknownForm(" ".join(tokens[k:k + 4]))
            guc, value, k = got
            acts.append(("set", guc, value))
        elif t == "reset" and k + 1 < len(tokens):
            acts.append(("reset", low(tokens[k + 1]), None))
            k += 2
        elif t == "restrict" and k == len(tokens) - 1:
            k += 1
        else:
            raise UnknownForm(" ".join(tokens[k:k + 4]))
    if not acts:
        raise UnknownForm("(동작 없음)")
    return acts


# ---------------------------------------------------------------------------
# 4. 되짚기
# ---------------------------------------------------------------------------

class Replay(object):
    def __init__(self):
        self.fn = {}                 # fn_key → {guc: 값}
        self.ext = {}                # 확장 이름 → 스키마
        self.fn_touched = []         # ALTER FUNCTION 이 닿은 fn_key (순서대로, 중복 제거)
        self.ext_touched = []
        self.problems = []
        self.n_alter_fn = 0
        self.n_alter_ext = 0

    def touch(self, lst, key):
        if key not in lst:
            lst.append(key)

    def feed(self, source, sql):
        for stmt in split_statements(sql.replace("\r\n", "\n")):
            toks = tokenize(stmt)
            if not toks:
                continue
            try:
                self.statement(source, toks)
            except UnknownForm as e:
                self.problems.append(
                    "[{}] 이 가드가 모르는 형태 — 처리 규칙을 먼저 더하라: {} ▶ {}".format(
                        source, " ".join(toks[:8]), e))

    def statement(self, source, toks):
        w = [low(t) for t in toks[:4]]
        if w[:1] == ["create"]:
            k = 1
            if w[1:3] == ["or", "replace"]:
                k = 3
            if k < len(toks) and low(toks[k]) == "function":
                self.create_function(toks, k + 1)
            elif k < len(toks) and low(toks[k]) == "extension":
                self.create_extension(toks, k + 1)
        elif w[:2] == ["alter", "function"]:
            self.n_alter_fn += 1
            self.alter_function(toks)
        elif w[:2] == ["alter", "routine"]:
            raise UnknownForm("ALTER ROUTINE 은 이 가드가 되짚지 않는다 — ALTER FUNCTION 으로 쓰거나 규칙을 더하라")
        elif w[:2] == ["alter", "extension"]:
            self.n_alter_ext += 1
            self.alter_extension(toks)
        elif w[:2] == ["drop", "function"]:
            self.drop_function(toks)
        elif w[:2] == ["drop", "extension"]:
            k = 4 if w[2:4] == ["if", "exists"] else 2
            for part in split_top_level(toks[k:]):
                if part:
                    self.ext.pop(unquote_ident(part[0]), None)

    def signature(self, toks, k):
        name = qualify(toks[k])
        if k + 1 >= len(toks) or toks[k + 1] != "(":
            raise UnknownForm("인자 목록 없는 서명 " + toks[k])
        inner, nxt = take_paren_group(toks, k + 1)
        return fn_key(name, arg_types(inner)), nxt

    def create_function(self, toks, k):
        key, nxt = self.signature(toks, k)
        self.fn[key] = create_head_settings(toks[nxt:])

    def alter_function(self, toks):
        key, nxt = self.signature(toks, 2)
        acts = alter_actions(toks, nxt)
        state = self.fn.setdefault(key, {})
        for op, guc, value in acts:
            if op == "set":
                state[guc] = value
            elif guc == "all":
                state.clear()
            else:
                state.pop(guc, None)
        self.touch(self.fn_touched, key)

    def drop_function(self, toks):
        k = 4 if [low(t) for t in toks[2:4]] == ["if", "exists"] else 2
        for part in split_top_level(toks[k:]):
            part = [t for t in part if low(t) not in ("cascade", "restrict")]
            if not part:
                continue
            name = qualify(part[0])
            if len(part) > 1 and part[1] == "(":
                inner, _ = take_paren_group(part, 1)
                self.fn.pop(fn_key(name, arg_types(inner)), None)
            else:
                for key in [x for x in self.fn if x.startswith(name + "(")]:
                    self.fn.pop(key)

    def create_extension(self, toks, k):
        if [low(t) for t in toks[k:k + 3]] == ["if", "not", "exists"]:
            k += 3
            if_not_exists = True
        else:
            if_not_exists = False
        name = unquote_ident(toks[k])
        schema = "public"
        rest = [low(t) for t in toks[k + 1:]]
        for j, t in enumerate(rest):
            if t == "schema" and j + 1 < len(rest):
                schema = unquote_ident(toks[k + 1 + j + 1])
        if if_not_exists and name in self.ext:
            return                   # 이미 있으면 아무것도 안 바뀐다
        self.ext[name] = schema

    def alter_extension(self, toks):
        name = unquote_ident(toks[2])
        rest = [low(t) for t in toks[3:]]
        if rest[:2] == ["set", "schema"] and len(rest) == 3:
            self.ext[name] = unquote_ident(toks[5])
        elif rest[:1] == ["update"] and (len(rest) == 1 or (rest[1] == "to" and len(rest) == 3)):
            pass                     # 버전 올리기는 위치와 무관 — 명시적으로 허용
        else:
            raise UnknownForm("ALTER EXTENSION " + " ".join(toks[2:6]))
        self.touch(self.ext_touched, name)


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def load_migrations():
    return [(name, read(os.path.join(MIG_DIR, name)))
            for name in sorted(os.listdir(MIG_DIR)) if name.endswith(".sql")]


def replay_all(migrations):
    r = Replay()
    for name, sql in migrations:        # 이름순 = 시간순
        r.feed(name, sql)
    return r


def check(migrations, schema_sql):
    """문제 목록을 돌려준다(빈 목록 = 초록)."""
    mig = replay_all(migrations)
    canon = Replay()
    canon.feed("schema.sql", schema_sql)
    problems = list(mig.problems) + list(canon.problems)

    if not mig.fn_touched and not mig.ext_touched:
        problems.append("대조 대상이 0개입니다 — 파서가 ALTER 를 하나도 못 찾았습니다(빈 대조는 초록이 아닙니다).")

    for key in mig.fn_touched:
        want = mig.fn.get(key)
        got = canon.fn.get(key)
        if want is None:
            if got is not None:
                problems.append("{}: 마이그레이션에서 지워졌는데 정본엔 있습니다".format(key))
            continue
        if got is None:
            problems.append("{}: 정본에 이 서명의 create function 이 없습니다".format(key))
            continue
        if want != got:
            problems.append("{}: 설정 절이 다릅니다 — 마이그레이션 되짚기 {} ≠ 정본 {}".format(key, want, got))

    for name in mig.ext_touched:
        want = mig.ext.get(name)
        got = canon.ext.get(name)
        if got is None:
            problems.append("확장 {}: 정본에 create extension 이 없습니다".format(name))
        elif want != got:
            problems.append("확장 {}: 스키마가 다릅니다 — 마이그레이션 되짚기 {} ≠ 정본 {}".format(name, want, got))
    return problems


# ---------------------------------------------------------------------------
# 5. 시험
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def migrations():
    return load_migrations()


@pytest.fixture(scope="module")
def schema_sql():
    return read(SCHEMA)


def _fmt(problems):
    return "\n  · " + "\n  · ".join(problems)


class TestParserSeesEverything:
    def test_every_alter_statement_is_parsed(self, migrations):
        """⛔ 파서가 ALTER 를 **놓치면** 되짚은 상태가 조용히 옛 상태로 남는다.

        다른 눈(줄머리 정규식, 주석 줄은 `--` 가 앞에 있어 안 걸림)으로 센 개수와 대조한다.
        """
        head_fn = re.compile(r"(?im)^\s*alter\s+function\b")
        head_ext = re.compile(r"(?im)^\s*alter\s+extension\b")
        raw_fn = sum(len(head_fn.findall(sql)) for _, sql in migrations)
        raw_ext = sum(len(head_ext.findall(sql)) for _, sql in migrations)
        r = replay_all(migrations)
        assert raw_fn > 0 and raw_ext > 0, "ALTER 문을 하나도 못 셌습니다 — 정규식이 헛돕니다."
        assert r.n_alter_fn == raw_fn, (
            "ALTER FUNCTION 이 줄머리로 {}개인데 {}개만 되짚었습니다".format(raw_fn, r.n_alter_fn))
        assert r.n_alter_ext == raw_ext, (
            "ALTER EXTENSION 이 줄머리로 {}개인데 {}개만 되짚었습니다".format(raw_ext, r.n_alter_ext))

    def test_the_0923_targets_are_all_compared(self, migrations):
        """9/23 에 ALTER 로만 바뀐 함수 7개가 전부 대조 대상에 들어가야 한다."""
        r = replay_all(migrations)
        missing = KNOWN_0923_TARGETS - set(r.fn_touched)
        assert not missing, "대조 대상에서 빠졌습니다(서명 파싱 결함): {}".format(sorted(missing))
        assert "pg_trgm" in r.ext_touched


class TestReplayMatchesCanonical:
    def test_alter_touched_functions_and_extensions_match(self, migrations, schema_sql):
        """⛔ 마이그레이션을 되짚은 최종 설정 == 정본. 다르면 정본이 라이브와 다른 것을 말한다.

        고치는 법: 마이그레이션 쪽이 라이브에 실린 것이다. 정본의 그 함수 머리에 `set …` 절을
        더하거나 빼고(값·순서 그대로), 확장이면 `create extension … with schema …` 를 맞춘다.
        """
        problems = check(migrations, schema_sql)
        assert not problems, "정본이 마이그레이션 되짚기와 다릅니다:" + _fmt(problems)

    def test_the_expected_final_states(self, migrations):
        """되짚기 결과 자체의 기대값(9/23a 고정 7 → 23b·23c 가 둘을 해제)."""
        r = replay_all(migrations)
        pinned = {"search_path": "public, extensions, pg_temp"}
        for key in KNOWN_0923_TARGETS:
            if key.startswith(("public.search_key(", "public.price_floor_band(")):
                assert r.fn[key] == {}, key
            else:
                assert r.fn[key] == pinned, key
        assert r.ext["pg_trgm"] == "extensions"


# --- B5 돌연변이: 사본 문자열만 바꾼다(원본 파일 무변경) -------------------------

def _mutate_once(text, old, new):
    assert text.count(old) >= 1, "돌연변이 대상 문자열을 못 찾았습니다(돌연변이가 헛돎): " + old[:60]
    return text.replace(old, new, 1)


def _replace_migration(migrations, name, fn):
    out, hit = [], False
    for n, sql in migrations:
        if n == name:
            new = fn(sql)
            assert new != sql, "돌연변이가 아무것도 안 바꿨습니다: " + name
            out.append((n, new))
            hit = True
        else:
            out.append((n, sql))
    assert hit, name
    return out


M23A = "2026-09-23a_security_advisor_trgm_search_path.sql"
M23C = "2026-09-23c_price_floor_band_keep_inline.sql"


class TestMutationsTurnRed:
    def test_1_drop_pin_from_mask_person_name(self, migrations, schema_sql):
        s = schema_sql.replace("\r\n", "\n")
        head = "create or replace function mask_person_name(nm text)\n"
        i = s.index(head)
        j = s.index("set search_path = public, extensions, pg_temp\n", i)
        assert j - i < 200, "mask_person_name 머리 바로 아래의 고정 줄이 아닙니다"
        mutated = s[:j] + s[j + len("set search_path = public, extensions, pg_temp\n"):]
        problems = check(migrations, mutated)
        assert any(p.startswith("public.mask_person_name(text)") for p in problems), problems
        assert len(problems) == 1, problems

    def test_2_add_pin_to_search_key(self, migrations, schema_sql):
        s = schema_sql.replace("\r\n", "\n")
        old = ("create or replace function search_key(t text)\nreturns text\nlanguage sql\n"
               "immutable\nparallel safe\nas $$")
        new = old.replace("parallel safe\n", "parallel safe\nset search_path = public, extensions, pg_temp\n")
        problems = check(migrations, _mutate_once(s, old, new))
        assert any(p.startswith("public.search_key(text)") for p in problems), problems
        assert len(problems) == 1, problems

    def test_3_pg_trgm_back_to_public(self, migrations, schema_sql):
        mutated = _mutate_once(schema_sql,
                               "create extension if not exists pg_trgm with schema extensions;",
                               "create extension if not exists pg_trgm;")
        problems = check(migrations, mutated)
        assert any("pg_trgm" in p and "public" in p for p in problems), problems
        assert len(problems) == 1, problems

    def test_4_unknown_alter_owner_is_red(self, migrations, schema_sql):
        muts = _replace_migration(
            migrations, M23C,
            lambda sql: sql + "\nALTER FUNCTION public.search_key(text) OWNER TO postgres;\n")
        problems = check(muts, schema_sql)
        assert any("모르는 형태" in p and M23C in p for p in problems), problems

    @pytest.mark.parametrize("line", [
        "ALTER FUNCTION public.search_key(text) RENAME TO search_key2;",
        "ALTER FUNCTION public.search_key(text) SET SCHEMA extensions;",
        "ALTER FUNCTION public.search_key(text) SECURITY DEFINER;",
        "ALTER FUNCTION public.search_key(text) STABLE;",
        "ALTER FUNCTION public.search_key(text) SET search_path FROM CURRENT;",
        "ALTER FUNCTION public.search_key SET search_path = public;",
        "ALTER FUNCTION public.search_key(text) DEPENDS ON EXTENSION pg_trgm;",
        "ALTER ROUTINE public.search_key(text) SET search_path = public;",
        "ALTER EXTENSION pg_trgm ADD FUNCTION public.search_key(text);",
    ])
    def test_4b_other_unknown_forms_are_red(self, migrations, schema_sql, line):
        muts = _replace_migration(migrations, M23C, lambda sql: sql + "\n" + line + "\n")
        problems = check(muts, schema_sql)
        assert any("모르는 형태" in p for p in problems), problems

    @pytest.mark.parametrize("line", [
        "ALTER EXTENSION pg_trgm UPDATE;",
        "ALTER EXTENSION pg_trgm UPDATE TO '1.6';",
    ])
    def test_4c_extension_update_is_allowed(self, migrations, schema_sql, line):
        muts = _replace_migration(migrations, M23C, lambda sql: sql + "\n" + line + "\n")
        assert check(muts, schema_sql) == []

    def test_4d_known_form_with_multiple_actions_is_replayed(self, migrations, schema_sql):
        """아는 형태를 여러 개 이은 문장은 되짚고, 그 결과가 정본과 다르면 빨강."""
        muts = _replace_migration(
            migrations, M23C,
            lambda sql: sql + "\nALTER FUNCTION public.search_key(text) "
                              "SET search_path TO 'public' SET work_mem = '64MB' RESET work_mem RESTRICT;\n")
        problems = check(muts, schema_sql)
        assert problems == ["public.search_key(text): 설정 절이 다릅니다 — 마이그레이션 되짚기 "
                            "{'search_path': 'public'} ≠ 정본 {}"], problems

    def test_5_indented_rollback_comments_are_still_ignored(self, migrations, schema_sql):
        """23a 머리말의 ROLLBACK 주석(`-- ALTER …`)을 들여써도, 블록 주석으로 감싸도 상태를 못 바꾼다."""
        base = replay_all(migrations)

        def indent(sql):
            return sql.replace("\n-- ALTER ", "\n      -- ALTER ")

        def block(sql):
            return sql.replace("-- ROLLBACK:\n", "/* ROLLBACK:\n").replace(
                "-- ALTER FUNCTION public.unit_business_append_only() RESET search_path;",
                "   ALTER FUNCTION public.unit_business_append_only() RESET search_path; */")

        for fn in (indent, block):
            muts = _replace_migration(migrations, M23A, fn)
            assert muts != migrations
            r = replay_all(muts)
            assert r.fn == base.fn and r.ext == base.ext, fn.__name__
            assert r.n_alter_fn == base.n_alter_fn, fn.__name__
            assert check(muts, schema_sql) == [], fn.__name__

    def test_6_zero_targets_is_red(self, migrations, schema_sql):
        """⛔ ALTER 를 하나도 못 찾으면(파서가 헛돌면) 초록이 아니라 빨강이다."""
        strip = re.compile(r"(?im)^\s*alter\s+(function|extension)\b[^;]*;")
        muts = [(n, strip.sub("", sql)) for n, sql in migrations]
        assert replay_all(muts).n_alter_fn == 0
        problems = check(muts, schema_sql)
        assert any("대조 대상이 0개" in p for p in problems), problems


class TestStatementSplitter:
    def test_quotes_and_comments_do_not_split_or_leak(self):
        sql = ("comment on function f(text) is 'a; ALTER FUNCTION x() OWNER TO y; -- z';\n"
               "/* ALTER FUNCTION a() OWNER TO b; /* 겹친 */ */\n"
               "create function g(p text) returns text language sql as $$ select 'ALTER FUNCTION'; $$;\n"
               "ALTER FUNCTION g(text) SET search_path = \"$user\", Public;\n")
        r = Replay()
        r.feed("t", sql)
        assert r.problems == []
        assert r.n_alter_fn == 1
        assert r.fn == {"public.g(text)": {"search_path": "$user, public"}}

    def test_signature_ignores_arg_names_defaults_typmods(self):
        r = Replay()
        r.feed("t", "create function public.h(in p_a char(19), b double precision default 1, "
                    "out c int) returns record language sql as $$ select 1 $$ set work_mem = '1MB';\n"
                    "ALTER FUNCTION h(character, float8) RESET ALL;")
        assert r.problems == []
        assert r.fn == {"public.h(bpchar,float8)": {}}
