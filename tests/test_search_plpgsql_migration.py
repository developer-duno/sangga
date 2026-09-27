# -*- coding: utf-8 -*-
"""마이그레이션 2026-09-27a(검색 함수 3개를 plpgsql 로 — 결정 0029)의 불변식을 지킨다.

무엇을 막나
-----------
결정 0029 의 본론은 **플래너가 검색어 값을 보게** 하는 것이다. 그 효과는 함수 머리·본문의
낱말 다섯에 달려 있는데, 하나만 빠져도 **에러 없이** 옛 병(2글자 검색이 trigram 색인을
골라 수백 ms 를 버리는 것)으로 조용히 돌아간다:

  · `language plpgsql` + `return query` — SQL 함수의 파라미터는 계획 시점에 상수가 아니다.
  · `set plan_cache_mode = force_custom_plan` — `auto` 로 두면 다섯 번 뒤 generic 계획으로
    돌아가 **정확히 지금의 병**이 된다.
  · `with pat as not materialized (` — 전처리 CTE 가 실체화되면 그 안쪽이 여전히 불투명하다.
  · `#variable_conflict use_column` — `returns table` 칸 이름이 plpgsql 변수가 되어 본문의
    같은 이름 컬럼과 부딪힌다(없으면 실행이 터진다 — 이것만은 시끄럽다).

그리고 이 판은 **서명·결과 칸을 한 글자도 안 바꾼다**(바꾸면 `create or replace` 가 거부하고,
api 쌍둥이·화면이 함께 흔들린다) · 권한을 열지 않는다(api 쌍둥이가 security definer 라 원본을
부르는 주체는 소유자다 — SECURITY DEFINER 자체는 호출자의 EXECUTE 검사를 면제하지 않는다).

여기서 보는 것 (DB 없이 SQL 글자만 — CI 에는 DB 가 없다)
  1) 핀 파일(2026-09-27a)과 정본(schema.sql) **양쪽**, 세 함수 각각에 위 다섯 낱말.
  2) 서명(인자)·`returns table` 칸이 직전 판(09-10a·09-10b)과 **글자 동일**(주석 걷고
     공백 접고 소문자로 맞춘 뒤).
  3) 파일 단위: 첫 `create` 앞 `begin;` · `commit;` 뒤 `notify pgrst` · `grant … to anon` 0 ·
     revoke ×3 · api 쌍둥이 재정의 0.
  4) 단언마다 돌연변이(사본 변조 → 빨간불) 증명 — 판정 함수를 그대로 태운다.
  5) 낱말은 **제자리에서만**(2026-09-27): `language`·`set plan_cache_mode` 는 머리(여는 `$$`
     앞, 줄 끝·블록 주석 걷고), 나머지 셋은 본문(`$$` 안)에서만 찾는다.
  6) use_column 전제: 정본의 표·뷰에 q·lim·sigungu·p_offset 이라는 칸이 0개(2026-09-27).

ⓘ 도우미는 형제 test_search_gu_cast_migration.py·test_search_stores_migration.py 에서
  **복사**해 왔다 — import 하지 않는다(시험 파일끼리 얽히면 한쪽 고장이 다른 쪽을 가린다).
ⓘ 정본↔마이그레이션 **본문** 글자 대조는 형제 둘과 tests/test_schema_function_drift.py 가
  본다 — 여기서는 되풀이하지 않는다.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIG_DIR = os.path.join(ROOT, "supabase", "migrations")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
PIN = os.path.join(MIG_DIR, "2026-09-27a_search_fns_plpgsql.sql")

BOTH = [PIN, SCHEMA]
LABEL = {PIN: "마이그레이션 2026-09-27a", SCHEMA: "정본 schema.sql"}

# (함수 이름, revoke 에 적히는 인자 타입, 직전 판 파일)
FUNCS = (
    ("search_scope", "text, text", "2026-09-10a_search_gu_index_cond.sql"),
    ("search_buildings", "text, int, text", "2026-09-10a_search_gu_index_cond.sql"),
    ("search_stores", "text, int, text, int",
     "2026-09-10b_search_stores_names_after_limit.sql"),
)
FN_NAMES = [f for f, _, _ in FUNCS]

# 결정 0029 가 기대는 낱말 다섯 — 주석 걷고 공백 한 칸으로 접은 뒤, **있어야 할 자리에서만**
# 찾는다(2026-09-27 검사관 A — 파일 전체에서 찾으면 줄 끝 주석
# `set search_path = public -- set plan_cache_mode = force_custom_plan` 이나 본문 안의
# `set plan_cache_mode …;` **문장**으로 옮겨도 초록이었다. 본문 안 SET 은 함수 옵션이 아니라
# 실행 중 세션 값을 바꾸는 문장이라, 그 호출의 계획 캐시 방식을 정하지 못한다).
#   머리 = `create … function` 부터 여는 `$$` 직전 — 함수 **옵션**이 사는 곳.
#   본문 = `$$` 안 — plpgsql 코드가 사는 곳.
HEAD_MARKERS = (
    "language plpgsql",
    "set plan_cache_mode = force_custom_plan",
)
BODY_MARKERS = (
    "with pat as not materialized (",
    "#variable_conflict use_column",
    "return query",
)
MARKERS = HEAD_MARKERS + BODY_MARKERS

DOLLAR = chr(36) * 2


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def norm(text):
    """줄바꿈 표기(CRLF/LF)만 통일한다."""
    return text.replace("\r\n", "\n")


def statements(sql):
    """주석 줄(`--` 로 시작)을 걷어낸 **실제 SQL 문장만** (줄바꿈은 그대로)."""
    return "\n".join(
        line for line in norm(sql).splitlines() if not line.lstrip().startswith("--")
    )


# `comment on … is '…';` 한 문장. 여러 줄에 걸치고, 끝은 항상 `';` 다.
RE_COMMENT_STMT = re.compile(r"(?ims)^comment\s+on\s+.*?';\s*$")


def code_only(sql):
    """주석 **그리고 `comment on … is '…'` 문장까지** 걷어낸 것."""
    return RE_COMMENT_STMT.sub("", statements(sql))


def flat(sql):
    """주석을 걷고 **공백을 한 칸으로** 접은 것."""
    return re.sub(r"\s+", " ", statements(sql))


def fn_block(sql, name):
    """`create [or replace] function [public.]<name>(` 부터 `$$;` 앞까지 (머리 + 본문).

    ⛔ `(?!api\\.)` — api 쌍둥이(본문 한 줄)를 잡으면 낱말 검사가 전부 빨개지거나, 반대로
       쌍둥이만 보고 통과하는 가짜 초록이 된다.
    """
    sql = norm(sql)
    m = re.search(
        r"(?im)^create\s+(?:or\s+replace\s+)?function\s+(?!api\.)(?:public\.)?"
        + name + r"\s*\(",
        sql,
    )
    assert m, "{} 정의를 못 찾았습니다".format(name)
    end = sql.index(DOLLAR + ";", m.start())
    return sql[m.start():end]


def signature(block):
    """함수 **서명과 결과 칸** — `create … (` 부터 `language` 앞까지를 정규화한 것.

    주석(줄 주석·줄 끝 주석)을 걷고 공백을 한 칸으로 접고 소문자로 맞춘다. 머리의 주석은
    라이브(`pg_proc`)에 안 실리므로 그 차이는 보지 않는다 — 남는 것은 인자 이름·타입·
    기본값과 `returns table` 칸 이름·타입·순서다.
    """
    m = re.search(r"(?im)^\s*language\s", block)
    assert m, "language 절을 못 찾았습니다 — 머리를 못 잘랐습니다"
    head = re.sub(r"--[^\n]*", "", norm(block[:m.start()]))
    head = re.sub(r"\s+", " ", head).strip().lower()
    assert "returns table (" in head, "returns table 을 못 찾았습니다: " + head[:80]
    return head


# ── 판정 한 벌 — 아래 시험과 돌연변이 시험이 **같은** 함수를 태운다 ─────────────


RE_LINE_COMMENT = re.compile(r"--[^\n]*")
RE_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def decomment(text):
    """`/* … */` 와 `--` 부터 줄 끝까지(줄 **끝** 주석 포함)를 걷는다.

    ⓘ 문자열 안의 `--`·`/*` 는 가리지 않는다 — 이 판의 세 함수 본문에 그런 문자열은
      0건이다(2026-09-27 grep). 생겨도 판정은 낱말을 **잃는** 쪽(빨강)으로 틀린다.
    """
    return RE_LINE_COMMENT.sub("", RE_BLOCK_COMMENT.sub("", norm(text)))


def head_and_body(block):
    """함수 블록을 (머리, 본문)으로 — 주석을 **먼저** 걷고 첫 `$$` 에서 자른다
    (머리 주석에 `$$` 가 적혀 있어도 엉뚱한 곳에서 자르지 않게)."""
    code = decomment(block)
    i = code.find(DOLLAR)
    assert i != -1, "여는 `$$` 를 못 찾았습니다 — 머리·본문을 못 갈랐습니다"
    fold = lambda s: re.sub(r"\s+", " ", s)  # noqa: E731
    return fold(code[:i]), fold(code[i + len(DOLLAR):])


def marker_defects(block):
    """함수 블록 하나에서 빠진 낱말 목록(비었으면 정상) — 머리 낱말은 머리에서만,
    본문 낱말은 본문에서만 찾는다."""
    head, body = head_and_body(block)
    return ([mk for mk in HEAD_MARKERS if mk not in head]
            + [mk for mk in BODY_MARKERS if mk not in body])


RE_ANON_GRANT = re.compile(r"(?i)\bgrant\s+execute\s+on\s+function\b[^;]*\bto\b[^;]*\banon\b")
RE_API_DEF = re.compile(r"(?im)^create\s+(?:or\s+replace\s+)?function\s+api\.")


def file_defects(sql):
    """마이그레이션 파일 하나의 어긋난 점 목록(비었으면 정상)."""
    code = statements(sql)
    low = code.lower()
    bad = []
    begin = re.search(r"(?m)^begin;", low)
    create = re.search(r"(?m)^create\s", low)
    commit = re.search(r"(?m)^commit;", low)
    notify = re.search(r"(?m)^notify\s+pgrst\b", low)
    if begin is None or create is None or begin.start() > create.start():
        bad.append("첫 `create` 앞에 `begin;` 이 없습니다")
    if commit is None or notify is None or notify.start() < commit.start():
        bad.append("`commit;` 뒤에 `notify pgrst` 가 없습니다")
    grants = RE_ANON_GRANT.findall(flat(sql))
    if grants:
        bad.append("anon 에게 실행 권한을 주는 grant 가 {}줄 있습니다".format(len(grants)))
    for fn, args, _ in FUNCS:
        line = "revoke all on function {}({}) from public, anon, authenticated;".format(
            fn, args)
        if line not in flat(sql):
            bad.append("`{}` 가 없습니다".format(line))
    if RE_API_DEF.search(code_only(sql)):
        bad.append("api 쌍둥이를 다시 정의합니다 — 이 판의 범위 밖입니다")
    return bad


# ── 1. 다섯 낱말 ──────────────────────────────────────────────────────────────


class TestTheFiveWords:
    @pytest.mark.parametrize("path", BOTH)
    @pytest.mark.parametrize("fn", FN_NAMES)
    def test_every_function_carries_them(self, path, fn):
        """⛔ 하나만 빠져도 **에러 없이** 옛 병으로 돌아간다(결정 0029 ⓐ~ⓔ)."""
        bad = marker_defects(fn_block(read(path), fn))
        assert not bad, "{} 의 {}: 빠진 낱말 {}".format(LABEL[path], fn, bad)

    @pytest.mark.parametrize("path", BOTH)
    @pytest.mark.parametrize("fn", FN_NAMES)
    def test_the_block_is_the_real_body(self, path, fn):
        """⛔ 파서가 엉뚱한 것을 뜯으면(api 쌍둥이·빈 블록) 위 시험이 무의미해진다."""
        block = fn_block(read(path), fn)
        assert "search_key(q)" in block, "{} 의 {}: 본문이 아닙니다".format(LABEL[path], fn)
        assert not re.match(r"(?i)create\s+(or\s+replace\s+)?function\s+api\.", block)


# ── 2. 서명·결과 칸은 직전 판 그대로 ─────────────────────────────────────────


class TestTheSignatureDidNotMove:
    @pytest.mark.parametrize("path", BOTH)
    @pytest.mark.parametrize("fn,args,prev", FUNCS)
    def test_same_as_the_previous_version(self, path, fn, args, prev):
        """⛔ `returns table` 칸은 OUT 파라미터라 한 글자만 바뀌어도 `create or replace` 가
        거부하거나(라이브에서 판이 통째로 실패), 순서가 바뀌면 PostgreSQL 이 **자리**로 맞춰
        api 쌍둥이·화면이 칸을 엇갈려 읽는다."""
        before = signature(fn_block(read(os.path.join(MIG_DIR, prev)), fn))
        after = signature(fn_block(read(path), fn))
        assert after == before, "{} 의 {}: 서명·결과 칸이 {} 와 다릅니다".format(
            LABEL[path], fn, prev)


# ── 3. 파일 단위 ──────────────────────────────────────────────────────────────


def test_the_pinned_file_is_clean():
    """begin 앞 · notify 는 commit 뒤 · anon grant 0 · revoke ×3 · api 쌍둥이 재정의 0."""
    bad = file_defects(read(PIN))
    assert not bad, " / ".join(bad)


def test_the_pinned_file_revokes_exactly_three():
    """⛔ revoke 는 셋이다 — 함수 셋을 다시 만들었으니 셋 다 다시 닫는다."""
    n = len(re.findall(r"(?im)^revoke\s+all\s+on\s+function\s+search_",
                       statements(read(PIN))))
    assert n == 3, n


# ── 4. 돌연변이 — 판정이 진짜 무는가 (파일은 안 건드린다, 사본만) ─────────────


@pytest.mark.parametrize("path", BOTH)
@pytest.mark.parametrize("fn", FN_NAMES)
@pytest.mark.parametrize("marker", MARKERS)
def test_mutation_a_missing_word_is_noticed(path, fn, marker):
    """다섯 낱말 각각을 지운 사본 → 빨간불이 나야 한다."""
    block = fn_block(read(path), fn)
    assert not marker_defects(block), "전제: 원문은 정상이다"
    # 낱말은 여러 줄에 걸치지 않으므로 날 글자에서 바로 지운다(한 번만).
    raw_marker = {
        "language plpgsql": "language plpgsql",
        "set plan_cache_mode = force_custom_plan": "set plan_cache_mode = force_custom_plan",
        "with pat as not materialized (": "not materialized ",
        "#variable_conflict use_column": "#variable_conflict use_column",
        "return query": "return query",
    }[marker]
    assert raw_marker in block, "전제: 원문에 `{}` 가 있다".format(raw_marker)
    tampered = block.replace(raw_marker, "", 1)
    assert marker in marker_defects(tampered), (
        "`{}` 를 지웠는데도 '정상'이라 합니다".format(marker))


@pytest.mark.parametrize("path", BOTH)
def test_mutation_b_auto_plan_cache_is_noticed(path):
    """`force_custom_plan` → `auto` — 겉으로는 그럴듯하지만 다섯 번 뒤 옛 병이다."""
    block = fn_block(read(path), "search_stores")
    tampered = block.replace("force_custom_plan", "auto", 1)
    assert marker_defects(tampered), "auto 로 바꿨는데도 '정상'이라 합니다"


@pytest.mark.parametrize("path", BOTH)
@pytest.mark.parametrize("fn,args,prev", FUNCS)
def test_mutation_c_a_moved_signature_is_noticed(path, fn, args, prev):
    """인자 기본값 하나 · 결과 칸 이름 하나를 바꾼 사본 → 서명 대조가 뒤집혀야 한다."""
    before = signature(fn_block(read(os.path.join(MIG_DIR, prev)), fn))
    block = fn_block(read(path), fn)
    assert signature(block) == before, "전제: 원문은 같다"
    # 결과 칸의 첫 이름을 바꾼다(`returns table (` 바로 뒤의 낱말).
    m = re.search(r"returns table \(\s*(\w+)", block)
    assert m, "전제: returns table 첫 칸"
    renamed = block[:m.start(1)] + m.group(1) + "_x" + block[m.end(1):]
    assert signature(renamed) != before, "결과 칸 이름을 바꿨는데도 같다고 합니다"
    # 인자의 첫 기본값(`default null`·`default 25`·`default 50`)을 바꾼다.
    d = re.search(r"default\s+(\w+)", block)
    assert d and d.start() < block.index("returns table"), "전제: 인자에 기본값이 있다"
    redefaulted = block[:d.start(1)] + "7" + block[d.end(1):]
    assert signature(redefaulted) != before, "인자 기본값을 바꿨는데도 같다고 합니다"


FILE_MUTANTS = (
    ("begin_after_create",
     lambda s: s.replace("\nbegin;\n", "\n", 1).replace(
         "\ncommit;\n", "\nbegin;\ncommit;\n", 1)),
    ("notify_removed",
     lambda s: s.replace("notify pgrst, 'reload schema';", "", 1)),
    ("notify_before_commit",
     lambda s: s.replace("notify pgrst, 'reload schema';", "", 1).replace(
         "\ncommit;\n", "\nnotify pgrst, 'reload schema';\ncommit;\n", 1)),
    ("anon_grant_added",
     lambda s: s.replace(
         "\ncommit;\n",
         "\ngrant execute on function search_scope(text, text) to anon;\ncommit;\n", 1)),
    ("one_revoke_removed",
     lambda s: s.replace(
         "revoke all on function search_stores(text, int, text, int) "
         "from public, anon, authenticated;", "", 1)),
    ("api_twin_redefined",
     lambda s: s.replace(
         "\ncommit;\n",
         "\ncreate or replace function api.search_scope(q text, sigungu text default null)\n"
         "returns table (too_broad boolean, match_cnt int) language sql as "
         + DOLLAR + " select 1 " + DOLLAR + ";\ncommit;\n", 1)),
)


@pytest.mark.parametrize("name,mutate", FILE_MUTANTS, ids=[m[0] for m in FILE_MUTANTS])
def test_mutation_d_file_level_breakage_is_noticed(name, mutate):
    """파일 단위 판정의 각 단언을 하나씩 깨뜨린 사본 → 빨간불."""
    text = norm(read(PIN))
    assert not file_defects(text), "전제: 원문은 정상이다"
    broken = mutate(text)
    assert broken != text, "전제: 사본이 실제로 달라야 한다({})".format(name)
    assert file_defects(broken), "{} — 그런데도 '정상'이라 합니다".format(name)


def test_mutation_e_a_commented_grant_is_not_a_grant():
    """⛔ 반대 방향 — 주석으로 적은 grant 는 grant 가 아니다(헛것을 잡으면 사람이 가드를
    느슨하게 고친다). 주석 제거가 살아 있는지도 함께 본다."""
    text = norm(read(PIN)).replace(
        "\ncommit;\n",
        "\n-- grant execute on function search_scope(text, text) to anon;\ncommit;\n", 1)
    assert "-- grant execute" in text, "전제: 끼워 넣기가 됐다"
    assert not file_defects(text), file_defects(text)


# ── 5. 낱말은 제자리에서만 (2026-09-27 검사관 A 의 가짜 초록 두 가지) ─────────────
#
# 파일(27a·정본) **전체**를 변조한 사본에서 세 함수 블록을 다시 뜯어 판정한다 — 머리의
# `set plan_cache_mode` 줄은 세 함수 모두 `set search_path = public` 바로 뒤에 있다.

HEAD_PAIR = "set search_path = public\nset plan_cache_mode = force_custom_plan\n"
BODY_OPEN = "#variable_conflict use_column\nbegin\n"

PLACEMENT_MUTANTS = (
    # ① 머리의 옵션을 줄 끝 주석으로 — 글자는 파일에 남지만 함수 옵션은 사라진다.
    ("head_option_as_line_end_comment",
     lambda s: s.replace(
         HEAD_PAIR,
         "set search_path = public -- set plan_cache_mode = force_custom_plan\n")),
    # ①' 같은 것을 블록 주석으로.
    ("head_option_as_block_comment",
     lambda s: s.replace(
         HEAD_PAIR,
         "set search_path = public\n/* set plan_cache_mode = force_custom_plan */\n")),
    # ② 머리에서 지우고 본문 첫 줄에 SET **문장**으로 — 실행 중 세션 값이지 함수 옵션이 아니다.
    ("head_option_moved_into_body",
     lambda s: s.replace(HEAD_PAIR, "set search_path = public\n").replace(
         BODY_OPEN, BODY_OPEN + "  set plan_cache_mode = force_custom_plan;\n")),
)


@pytest.mark.parametrize("path", BOTH)
@pytest.mark.parametrize("name,mutate", PLACEMENT_MUTANTS,
                         ids=[m[0] for m in PLACEMENT_MUTANTS])
def test_mutation_f_the_head_option_must_stay_in_the_head(path, name, mutate):
    """머리의 plan_cache_mode 를 주석·본문으로 옮긴 사본 → 세 함수 모두 빨간불."""
    text = norm(read(path))
    assert text.count(HEAD_PAIR) == 3, "전제: 세 함수 머리에 그 두 줄이 붙어 있다"
    assert text.count(BODY_OPEN) >= 3, "전제: 세 함수 본문이 그 두 줄로 시작한다"
    broken = mutate(text)
    assert "set plan_cache_mode = force_custom_plan" in broken, (
        "전제: 낱말 자체는 파일에 남아 있다(그래서 옛 판정은 초록이었다)")
    for fn in FN_NAMES:
        bad = marker_defects(fn_block(broken, fn))
        assert "set plan_cache_mode = force_custom_plan" in bad, (
            "{} 의 {}: {} — 그런데도 '정상'이라 합니다".format(LABEL[path], fn, name))


@pytest.mark.parametrize("path", BOTH)
def test_mutation_g_body_words_are_not_read_from_the_head(path):
    """반대 방향 — 본문 낱말(`return query`)을 머리 주석에만 남기면 빨간불."""
    text = norm(read(path))
    block = fn_block(text, "search_scope")
    assert "  return query\n" in block, "전제: 본문에 return query 가 있다"
    tampered = block.replace("  return query\n", "  \n", 1).replace(
        "language plpgsql\n", "language plpgsql -- return query\n", 1)
    assert "return query" in marker_defects(tampered)


# ── 6. use_column 전제 — 정본 어디에도 q·lim·sigungu·p_offset 칸이 없다 ────────────
#
# `#variable_conflict use_column` 은 이름이 부딪히면 **칸이 이긴다**. 지금 세 함수의
# 파라미터 이름(q·lim·sigungu·p_offset)과 같은 이름의 칸이 본문이 읽는 표·뷰에 생기면,
# 그 자리의 `q` 가 검색어가 아니라 그 칸으로 **에러 없이** 바뀐다(검색이 조용히 헛돈다).
# 라이브는 2026-09-27 pg_attribute 로 0 을 확인했다(27a 머리말 ⓔ) — 여기서는 정본이 그
# 상태를 벗어나는 순간을 잡는다.
#
# ⚠️ 한계: 뷰는 `as select …` 안의 **별칭** `… as <이름>` 만 본다. 별칭 없이 넘어온 칸
#    (`select t.sigungu`)은 그 칸이 원래 있는 표 쪽에서 잡히고, 함수 결과로 넘어온 칸은 못 본다.

USE_COLUMN_NAMES = ("q", "lim", "sigungu", "p_offset")
_CONSTRAINT_HEADS = ("constraint", "primary", "unique", "check", "foreign", "exclude", "like")

RE_CREATE_TABLE = re.compile(
    r"(?is)\bcreate\s+(?:unlogged\s+)?table\s+(?:if\s+not\s+exists\s+)?([\w.\"]+)\s*\(")
RE_ADD_COLUMN = re.compile(
    r"(?is)\badd\s+column\s+(?:if\s+not\s+exists\s+)?\"?(\w+)\"?")
RE_CREATE_VIEW = re.compile(
    r"(?is)\bcreate\s+(?:or\s+replace\s+)?(?:materialized\s+)?view\s+"
    r"(?:if\s+not\s+exists\s+)?([\w.\"]+)\s+as\b(.*?);")
RE_ALIAS = re.compile(r"(?i)\bas\s+\"?(\w+)\"?")


def _paren_body(text, open_at):
    """`(` 위치부터 짝이 맞는 `)` 앞까지."""
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_at + 1:i]
    raise AssertionError("괄호 짝이 안 맞습니다")


def _top_level_items(text):
    items, depth, cur = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            items.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    items.append("".join(cur))
    return [i.strip() for i in items if i.strip()]


def relation_columns(sql):
    """정본에서 (관계 이름, 칸 이름 목록) — 표(create table + add column)와 뷰(별칭)."""
    code = decomment(sql)
    out = []
    for m in RE_CREATE_TABLE.finditer(code):
        cols = []
        for item in _top_level_items(_paren_body(code, m.end() - 1)):
            first = item.split()[0].strip('"').lower()
            if first not in _CONSTRAINT_HEADS:
                cols.append(first)
        out.append(("table " + m.group(1), cols))
    adds = [a.group(1).lower() for a in RE_ADD_COLUMN.finditer(code)]
    if adds:
        out.append(("alter table … add column", adds))
    for m in RE_CREATE_VIEW.finditer(code):
        out.append(("view " + m.group(1),
                    [a.group(1).lower() for a in RE_ALIAS.finditer(m.group(2))]))
    return out


def use_column_clashes(sql):
    return [(rel, c) for rel, cols in relation_columns(sql)
            for c in cols if c in USE_COLUMN_NAMES]


class TestUseColumnHasNothingToGrab:
    def test_no_relation_has_a_parameter_named_column(self):
        """⛔ 부딪히면 **칸이 이긴다** — 검색어 자리에 칸 값이 들어가도 에러는 없다."""
        assert use_column_clashes(read(SCHEMA)) == []

    def test_the_parser_really_found_tables_and_views(self):
        """⛔ 표를 0개 찾으면 가드가 있는 척만 한다(가짜 초록)."""
        rels = dict(relation_columns(read(SCHEMA)))
        tables = [r for r in rels if r.startswith("table ")]
        views = [r for r in rels if r.startswith("view ")]
        assert len(tables) >= 10, tables
        assert len(views) >= 5, views
        assert "pnu" in rels["table parcel"], rels["table parcel"]
        assert "sigungu_code" in rels["view mv_search_parcel"], (
            "뷰 별칭을 못 읽었습니다 — `as sigungu_code` 가 있어야 합니다")


@pytest.mark.parametrize("name,mutate", (
    ("table_column",
     lambda s: s.replace("create table if not exists parcel (",
                         "create table if not exists parcel (\n  sigungu text,", 1)),
    ("added_column",
     lambda s: s.replace("add column if not exists source_nm text;",
                         "add column if not exists q text;", 1)),
    ("view_alias",
     lambda s: s.replace("::char(5) as sigungu_code,", "::char(5) as sigungu,", 1)),
), ids=["table_column", "added_column", "view_alias"])
def test_mutation_h_a_clashing_column_is_noticed(name, mutate):
    """가짜 정본에 파라미터와 같은 이름의 칸 → 빨간불."""
    text = norm(read(SCHEMA))
    assert use_column_clashes(text) == [], "전제: 원문은 깨끗하다"
    broken = mutate(text)
    assert broken != text, "전제: 사본이 실제로 달라야 한다({})".format(name)
    assert use_column_clashes(broken), "{} — 그런데도 '정상'이라 합니다".format(name)
