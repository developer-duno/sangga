# -*- coding: utf-8 -*-
"""정본 함수의 필지번호(pnu) 인자가 text 로 들어오면 본문에서 char(19) 로 옮겨 쓰는가 — 전 함수 가드.

왜 (2026-08-16b · 2026-09-27c — "char(19) 함정")
  `pnu` 칸은 `char(19)` 다. 함수 인자를 `text` 로 받아 그대로 `t.pnu = p_pnu` 로 견주면
  PostgreSQL 은 **칸 쪽**을 text 로 캐스트해 견주고, 그러면 그 칸의 색인을 못 탄다(라이브 실측
  459.8ms ↔ 0.060ms). 서명(`p_pnu text`)은 화면과의 약속이라 그대로 두고, 본문에서
  `v_pnu char(19) := p_pnu` 로 옮기거나 `p_pnu::char(19)` 로 캐스트한다(배열이면 `char(19)[]`).
  2026-09-27 에 `list_parcel_transactions` 가 이 함정의 마지막 생존자로 고쳐졌다 — 그 전까지
  이 규칙은 함수마다의 개별 시험(test_search_gu_cast_migration · test_p6_cold_cache_migration 등)과
  메모에만 있었다. 이 시험은 `supabase/schema.sql` 의 **모든 함수**를 훑는다.

무엇을 보나
  ① 함수마다(인자가 여러 줄에 걸쳐도) 이름에 `pnu` 가 든 인자 중 형이 `text`·`text[]`·`varchar`
     인 것을 고른다.
  ② 그 인자가 본문(주석·문자열 걷은 뒤)에 나올 **때마다** 둘 중 하나여야 한다:
       · `<인자>::char(19)` 캐스트(배열 인자는 `::char(19)[]`) — `함수이름.<인자>` 꼴 포함
       · `<변수> char(19) := <인자>` (또는 `= `·`default `) — char(19) 변수로 옮기는 선언
     캐스트 하나가 있어도 다른 자리에 맨 인자가 남아 있으면 빨강이다(함정은 그 맨 자리에서 난다).
  ③ 예외 하나 — **api 쌍둥이**: 본문 전체가 `select [* from] public.<같은 이름>(…)` 한 줄이고
     인자를 그대로 넘기면, 그 쌍둥이는 표를 안 만지고 public 원본이 견준다. 대신 그 public 원본이
     정본에 **있고 이 가드를 통과해야** 한다(원본이 없거나 걸리면 쌍둥이도 빨강).

⚠️ 글자만 본다 — 라이브 함수가 정본과 같은지는 test_schema_function_drift·`post_load.py --check` 몫.
ⓘ 도우미는 이 파일 안에서만 쓴다(시험 파일끼리 import 하지 않는 레포 관습).
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

RE_CREATE_FN = re.compile(r"(?i)\bcreate\s+(?:or\s+replace\s+)?function\s+([\w.\"]+)\s*\(")
RE_BODY_START = re.compile(r"(?is)\bas\s+(\$(?:[A-Za-z_]\w*)?\$)")
RE_PNU_TYPE = re.compile(
    r"^(?:text|varchar|character varying)(?:\s*\(\s*\d+\s*\))?\s*(\[\s*\])?$")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def strip_comments_and_strings(body):
    """`--`·`/* */` 주석을 걷고 작은따옴표 문자열을 `''` 로 비운다(`''` 이스케이프만 안다).

    못 보는 것: `E'…\\''` 처럼 백슬래시로 따옴표를 감춘 문자열 · 본문 안 중첩 `$x$` 문자열.
    """
    out, i, n = [], 0, len(body)
    while i < n:
        if body.startswith("--", i):
            j = body.find("\n", i)
            i = n if j < 0 else j
            continue
        if body.startswith("/*", i):
            j = body.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
            continue
        if body[i] == "'":
            j = i + 1
            while True:
                k = body.find("'", j)
                if k < 0:
                    j = n
                    break
                if body.startswith("''", k):
                    j = k + 2
                    continue
                j = k + 1
                break
            out.append("''")
            i = j
            continue
        out.append(body[i])
        i += 1
    return "".join(out)


def split_top(text):
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [" ".join(p.split()) for p in parts if p.strip()]


def functions(sql):
    """정본의 함수들: [(이름, [(인자 이름, 형), …], 본문), …].

    못 보는 것: 본문이 `$…$` 가 아니라 작은따옴표 문자열인 옛 꼴 · `create procedure` ·
      `begin atomic … end` 꼴(SQL 표준 본문) — 지금 정본에는 셋 다 0건이라 그런 함수는 아예 안 나온다.
    """
    out = []
    for m in RE_CREATE_FN.finditer(sql):
        i, depth = m.end(), 1
        while depth:
            depth += {"(": 1, ")": -1}.get(sql[i], 0)
            i += 1
        args = []
        for a in split_top(strip_comments_and_strings(sql[m.end():i - 1])):
            words = a.split(" ")
            if words[0].lower() in ("in", "out", "inout", "variadic"):
                words = words[1:]
            if len(words) < 2:
                continue
            typ = re.split(r"(?i)\s+(?:default\b|=)", " ".join(words[1:]), 1)[0].strip()
            args.append((words[0].replace('"', ""), typ.lower()))
        b = RE_BODY_START.search(sql, i)
        if not b:
            continue
        end = sql.find(b.group(1), b.end())
        out.append((m.group(1).replace('"', "").lower(), args, sql[b.end():end]))
    return out


def pnu_text_args(args):
    """이름에 pnu 가 들고 형이 text 계열인 인자: [(이름, 배열인가), …]."""
    out = []
    for name, typ in args:
        if "pnu" not in name.lower():
            continue
        m = RE_PNU_TYPE.match(typ)
        if m:
            out.append((name.lower(), bool(m.group(1))))
    return out


def bare_uses(fn_name, arg, is_array, body):
    """본문에서 그 인자가 char(19) 로 옮겨지지 **않고** 쓰인 자리 목록(앞뒤 글자). 비면 통과.
    인자가 본문에 한 번도 안 나오면 그것도 문제로 돌려준다(헛통과 막기).

    못 보는 것:
      · 위치 인자 `$1` 로 쓰는 꼴 — 이름으로만 찾는다(지금 정본의 pnu 함수 16개는 전부 이름).
      · `cast(<인자> as char(19))` 꼴은 캐스트로 안 친다(걸리는 쪽 — 놓치는 쪽이 아니다).
      · 캐스트한 값을 다시 text 와 견주는 것 · 캐스트가 **맞는 칸**과 견주는지 — 글자 위치만 본다.
      · 인자 이름이 아니라 다른 이름(`p_parcel` 등)으로 필지번호를 받는 함수 — 이름에 pnu 가
        없으면 고르지 않는다.
    """
    short = fn_name.split(".")[-1]
    arr = r"\s*\[\s*\]" if is_array else r"(?!\s*\[)"
    cast = re.compile(r"\s*::\s*char(?:acter)?\s*\(\s*19\s*\)" + arr, re.I)
    decl_before = re.compile(
        r"(?i)\b\w+\s+char(?:acter)?\s*\(\s*19\s*\)" + arr.replace(r"(?!\s*\[)", "")
        + r"\s*(?::=|=|\bdefault\b)\s*$")
    use = re.compile(r"(?i)(?<![\w.$])(?:" + re.escape(short) + r"\.)?" + re.escape(arg) + r"\b")
    clean = strip_comments_and_strings(body)
    bad, total = [], 0
    for m in use.finditer(clean):
        total += 1
        if cast.match(clean, m.end()):
            continue
        if decl_before.search(clean[max(0, m.start() - 80):m.start()]):
            continue
        bad.append(" ".join(clean[max(0, m.start() - 30):m.end() + 20].split()))
    if total == 0:
        # 인자를 한 번도 못 찾으면 '맨 자리 0' 이 헛통과가 된다($1 로 쓰거나 이름이 바뀐 경우).
        bad.append("(인자를 본문에서 한 번도 못 찾았습니다 — 위치 인자 $1 로 쓰나요?)")
    return bad


def forwards_to_public(fn_name, body):
    """api 쌍둥이 꼴: 본문 전체가 `select [* from] public.<같은 이름>(인자…)` 한 줄인가."""
    if not fn_name.startswith("api."):
        return False
    short = fn_name.split(".", 1)[1]
    clean = " ".join(strip_comments_and_strings(body).split()).lower().rstrip(";").strip()
    return bool(re.fullmatch(
        r"select (?:\* from )?public\." + re.escape(short) + r" ?\([\w ,]*\)", clean))


def pnu_problems(sql):
    """정본 하나의 문제 목록. 비면 통과."""
    fns = functions(sql)
    by_name = {}
    for name, args, body in fns:
        by_name.setdefault(name, []).append((args, body))

    def own_problems(name, args, body):
        out = []
        for arg, is_array in pnu_text_args(args):
            for snippet in bare_uses(name, arg, is_array, body):
                out.append("{}({}): `{}` 가 char(19) 로 안 옮겨진 채 쓰였습니다 — {}".format(
                    name, arg, arg, snippet))
        return out

    bad = []
    for name, args, body in fns:
        if not pnu_text_args(args):
            continue
        if forwards_to_public(name, body):
            target = name.split(".", 1)[1]
            if target not in by_name:
                bad.append("{}: 넘겨받을 public.{} 가 정본에 없습니다".format(name, target))
            elif any(own_problems(target, a, b) for a, b in by_name[target]):
                bad.append("{}: 넘겨받는 public.{} 가 char(19) 규칙에 걸립니다".format(name, target))
            continue
        bad.extend(own_problems(name, args, body))
    return bad


# ---------------------------------------------------------------- 본 가드

def test_schema_functions_are_read():
    fns = functions(read(SCHEMA))
    assert len(fns) >= 50, "정본 함수를 {}개밖에 못 읽었습니다".format(len(fns))
    with_pnu = [n for n, a, _ in fns if pnu_text_args(a)]
    assert len(with_pnu) >= 16, with_pnu


def test_schema_pnu_text_args_are_moved_to_char19():
    bad = pnu_problems(read(SCHEMA))
    assert not bad, "\n".join(bad)


def test_both_moves_are_present_in_schema():
    """정본에 두 방식(캐스트 · char(19) 변수)이 실제로 있고 둘 다 통과로 읽힌다(헛통과 아님)."""
    fns = {n: (a, b) for n, a, b in functions(read(SCHEMA))}
    assert "::char(19)" in strip_comments_and_strings(fns["list_industry_mix"][1])
    assert re.search(r"v_pnu\s+char\(19\)\s*:=\s*p_pnu", fns["list_price_bands"][1])
    for name in ("list_industry_mix", "list_price_bands", "list_parcel_transactions"):
        args, body = fns[name]
        arg = pnu_text_args(args)[0][0]
        assert bare_uses(name, arg, False, body) == [], name


# ---------------------------------------------------------------- 양성 대조(같은 함수를 지난다)

def fn(sig, body, name="f"):
    return "create or replace function {}({})\nreturns int\nlanguage sql\nas $$\n{}\n$$;\n".format(
        name, sig, body)


@pytest.mark.parametrize("sql", [
    fn("p_pnu text", "select 1 from parcel p where p.pnu = p_pnu::char(19)"),
    # 변형: 인자 여러 줄 · 다른 인자 섞임
    fn("\n  p_cat text,\n  p_pnu text default null\n",
       "select 1 from parcel p where p.pnu = p_pnu :: CHAR( 19 )"),
    # char(19) 변수로 옮기기(plpgsql)
    "create function g(p_pnu text) returns int language plpgsql as $f$\ndeclare\n"
    "  v_pnu char(19) := p_pnu;\nbegin\n  return (select 1 from parcel where pnu = v_pnu);\n"
    "end $f$;\n",
    # 배열
    fn("pnus text[]", "select 1 from parcel p where p.pnu = any(pnus::char(19)[])"),
    # 함수이름.인자 꼴
    fn("pnu text", "select 1 from transaction t where t.pnu = f.pnu::char(19)"),
    # 주석·문자열 안 맨 인자는 쓰임이 아니다
    fn("p_pnu text", "-- where pnu = p_pnu\nselect 'p_pnu' from parcel where pnu = p_pnu::char(19)"),
    # pnu 가 이름에 없는 인자는 안 본다
    fn("p_bld_id text", "select 1 from building where bld_id = p_bld_id"),
    # 이미 char(19) 로 받는 인자는 안 본다
    fn("p_pnu char(19)", "select 1 from parcel where pnu = p_pnu"),
    # api 쌍둥이 → 통과하는 public 원본
    fn("p_pnu text", "select 1 from parcel where pnu = p_pnu::char(19)", name="h")
    + fn("p_pnu text", "select * from public.h(p_pnu)", name="api.h"),
])
def test_detector_passes(sql):
    assert pnu_problems(sql) == []


@pytest.mark.parametrize("sql", [
    # 흔한 꼴: 캐스트 없음
    fn("p_pnu text", "select 1 from parcel p where p.pnu = p_pnu"),
    # 변형: 인자 여러 줄 + 대문자 TEXT
    fn("\n  p_cat text,\n  p_pnu TEXT\n", "select 1 from parcel p where p.pnu = p_pnu"),
    # 변형: 배열인데 char(19) 로만 캐스트(배열 아님) · 배열 그대로
    fn("pnus text[]", "select 1 from parcel p where p.pnu = any(pnus)"),
    fn("p_pnus text[]", "select 1 from parcel p where p.pnu = any(p_pnus::char(19))"),
    # 캐스트 하나 + 맨 자리 하나
    fn("p_pnu text", "select 1 from parcel where pnu = p_pnu::char(19)\n"
       "union all select 1 from transaction where pnu = p_pnu"),
    # 함수이름.인자 꼴 맨 자리
    fn("pnu text", "select 1 from transaction t where t.pnu = f.pnu"),
    # varchar 도 같은 함정
    fn("p_pnu varchar", "select 1 from parcel where pnu = p_pnu"),
    # char(19) 가 아닌 char(10) 으로 옮김
    fn("p_pnu text", "select 1 from transaction where pnu10 = p_pnu::char(10)"),
    # 주석에만 캐스트가 있다
    fn("p_pnu text", "-- p_pnu::char(19)\nselect 1 from parcel where pnu = p_pnu"),
    # 위치 인자로 써서 이름이 본문에 없다(헛통과 막기)
    fn("p_pnu text", "select 1 from parcel where pnu = $1"),
    # api 쌍둥이인데 public 원본이 걸린다
    fn("p_pnu text", "select 1 from parcel where pnu = p_pnu", name="h")
    + fn("p_pnu text", "select * from public.h(p_pnu)", name="api.h"),
    # api 쌍둥이인데 public 원본이 없다
    fn("p_pnu text", "select * from public.nowhere(p_pnu)", name="api.nowhere"),
    # api 인데 한 줄 넘기기가 아니다(직접 견준다)
    fn("p_pnu text", "select 1 from public.parcel where pnu = p_pnu", name="api.k"),
    # 다른 이름으로 넘긴다
    fn("p_pnu text", "select 1 from parcel where pnu = p_pnu::char(19)", name="h")
    + fn("p_pnu text", "select * from public.other(p_pnu)", name="api.h"),
])
def test_detector_catches(sql):
    assert pnu_problems(sql), sql


def _drop_first(text, needle):
    assert needle in text, "전제: 정본에 {!r} 가 있다".format(needle)
    return text.replace(needle, needle.replace("::char(19)", ""), 1)


def test_mutation_schema_cast_removed_is_red():
    """정본 함수 하나(list_industry_mix)의 `::char(19)` 를 지우면 빨강 — 원본은 그대로."""
    text = read(SCHEMA)
    broken = _drop_first(text, "where p.pnu = p_pnu::char(19) and p.geom is not null")
    assert any("list_industry_mix" in b for b in pnu_problems(broken))


def test_mutation_schema_qualified_cast_removed_is_red():
    """`함수이름.인자::char(19)` 꼴(list_parcel_transactions)의 캐스트를 지워도 빨강."""
    text = read(SCHEMA)
    broken = _drop_first(text, "where t.pnu = list_parcel_transactions.pnu::char(19)")
    found = pnu_problems(broken)
    assert any(b.startswith("list_parcel_transactions(") for b in found), found
    assert any(b.startswith("api.list_parcel_transactions:") for b in found), found


def test_mutation_schema_char19_variable_retyped_is_red():
    """`v_pnu char(19) := p_pnu` 를 text 변수로 바꾸면 빨강(list_price_bands)."""
    text = read(SCHEMA)
    broken, n = re.subn(r"v_pnu(\s+)char\(19\)(\s*):= p_pnu;", r"v_pnu\1text\2:= p_pnu;", text, 1)
    assert n == 1, "전제: list_price_bands 의 char(19) 변수"
    assert any("list_price_bands" in b for b in pnu_problems(broken))
