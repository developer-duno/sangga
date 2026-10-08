# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-09a(건물 검색 결과에 소유 구조 세 칸 — 물결 1-A1 · 결정 0036 결정 5)의
불변식을 지킨다.

무엇을 막나
-----------
`search_buildings` 의 결과 칸을 13 → 16칸으로 늘렸다. 반환 꼴이 바뀌므로 `create or replace` 가
안 되고 **drop → 재생성 → 권한 재부여**를 했다. 이 일은 아래 실수가 전부 **에러 없이** 나는 자리다:

  1) 새 칸을 기존 13칸 **앞이나 사이에** 끼운다 → 칸은 이름이 아니라 **자리**로 맞춰져
     api 쌍둥이(`select *`)·화면이 칸을 엇갈려 읽는다. 끝 셋의 이름·형·순서를 못 박는다.
  2) 정본과 마이그레이션의 머리(security definer · set search_path · stable · plpgsql ·
     plan_cache_mode)나 comment 가 한 글자라도 다르다 → `create` 는 머리를 **새 정의로 덮어쓴다**.
     드리프트 가드는 `$$` 안 본문만 보므로 머리·comment 는 여기서 **블록 통째로** 대조한다.
     (2026-10-01a 적대검증: `set search_path` 가 빠지면 anon 경로가 죽는데 시험 1,130개가 초록이었다.)
  3) api 쌍둥이의 머리(security definer · `set search_path = ''`)·`public.` 완전수식이 빠진다.
  4) drop 으로 사라진 권한을 api 쌍둥이에 다시 안 준다 → 화면 검색이 permission denied
     (2026-08-13 401 전례). 반대로 public 원본을 연다 → 닫아 둔 문이 다시 열린다(CLAUDE.md 🚪).
  5) 세 칸을 검색 가지(addr·nm·hit)에 실어 나른다 → 이 함수는 가지에 민감하다
     (가지 2→3 에 763→1,550ms). 그래서 **마지막 select 앞까지는 27a 와 글자 그대로**이고,
     세 칸은 마지막 select 에서 building 을 기본키로 한 번 더 읽어 붙이는지 본다.
  6) 순서 — `set lock_timeout` 이 begin 앞 · 부르는 쪽(api)부터 drop · begin 안에서 drop·create ·
     grant 뒤 commit · commit 뒤 notify.

DB 없이 SQL 글자만 본다(CI 에는 DB 가 없다). 판정은 이 파일 안 작은 함수로 빼서 가드 본체와
양성 대조(사본 변조 → 빨간불)가 **같은 함수를 지난다**(CLAUDE.md ⛔ 「없음」 단언엔 양성 대조).

⚠️ 못 보는 것: 라이브에 이 파일이 실제로 적용됐는지(사람이 `dbx.py -f` 뒤 확인) · 세 칸의 값이
   맞는지(운영 읽기 실측으로 확인 — PR 본문) · 두 판 모두 같은 방향으로 틀린 머리(정본과 마이그를
   함께 바꾸면 블록 대조는 초록 — 그래서 머리 속성 몇 개는 §3 에서 따로 못 박는다) ·
   select 식의 형 ↔ 반환 칸 형(둘 다 `bo.parking_cnt::text` 처럼 고치면 초록인데 라이브는 처음
   부를 때 "structure of query does not match" 로 검색이 죽는다 — 운영 읽기 pg_temp 실행만 잡는다) ·
   `join` 이 `left join` 으로 바뀐 것(부분 문자열로 맞는다 — 기본키 조인이라 해는 없다).
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIG_DIR = os.path.join(ROOT, "supabase", "migrations")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
MIG = os.path.join(MIG_DIR, "2026-10-09a_search_ownership_cols.sql")
PREV = os.path.join(MIG_DIR, "2026-09-27a_search_fns_plpgsql.sql")

DOLLAR = chr(36) * 2

OLD_COLS = [
    ("bld_id", "text"), ("pnu", "char(19)"), ("bld_nm", "text"), ("road_addr", "text"),
    ("jibun_addr", "text"), ("lat", "double precision"), ("lng", "double precision"),
    ("bld_cnt_in_pnu", "int"), ("floor_cnt", "int"), ("min_floor", "smallint"),
    ("max_floor", "smallint"), ("has_roof", "boolean"), ("total_cnt", "bigint"),
]
NEW_TAIL = [("is_jiphap", "boolean"), ("approve_date", "date"), ("parking_cnt", "integer")]
WANT_COLS = OLD_COLS + NEW_TAIL

ARGS = "text, int, text"
API_GRANT = ("grant execute on function api.search_buildings(text, int, text) "
             "to anon, authenticated;")
PUBLIC_REVOKE = ("revoke all on function search_buildings(text, int, text) "
                 "from public, anon, authenticated;")
API_REVOKE = ("revoke all on function api.search_buildings(text, int, text) "
              "from public, anon, authenticated;")

# 세 칸을 붙이는 자리 — 마지막 select 의 조인(기본키) 한 줄과 select 목록 한 줄.
OWNERSHIP_JOIN = "join building bo on bo.bld_id = t.bld_id"
OWNERSHIP_SELECT = "bo.is_jiphap, bo.approve_date, bo.parking_cnt"
# 마지막 select 가 시작되는 본문 주석 — 이 줄 앞까지는 27a 와 글자 그대로여야 한다.
FINAL_SELECT_MARK = "  -- ② 지번주소 조립·좌표 뽑기는 여기서 처음 한다"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def statements(sql):
    """주석 줄(`--` 로 시작)을 걷어낸 실제 SQL 문장만."""
    return "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def flat(sql):
    return re.sub(r"\s+", " ", statements(sql)).strip()


def fn_block(sql, qualified):
    """`create [or replace] function <qualified>(` 부터 `$$;` 까지(머리 + 본문 + 닫는 `$$;`).

    `qualified` 가 `search_buildings` 면 api 쌍둥이는 뺀다(`(?!api\\.)`).
    """
    if qualified.startswith("api."):
        head = r"(?im)^create\s+(?:or\s+replace\s+)?function\s+api\.search_buildings\s*\("
    else:
        head = (r"(?im)^create\s+(?:or\s+replace\s+)?function\s+(?!api\.)(?:public\.)?"
                r"search_buildings\s*\(")
    m = re.search(head, sql)
    assert m, "{} 정의를 못 찾았습니다".format(qualified)
    end = sql.index(DOLLAR + ";", m.start()) + len(DOLLAR + ";")
    return sql[m.start():end]


def comment_stmt(sql):
    """`comment on function search_buildings(text, int, text) is '…';` 한 문장(없으면 None)."""
    m = re.search(r"(?ims)^comment\s+on\s+function\s+(?:public\.)?search_buildings\s*\("
                  r"text,\s*int,\s*text\)\s+is\b.*?';\s*$", sql)
    return m.group(0) if m else None


# ── 판정 함수 — 가드 본체와 양성 대조가 같은 함수를 지난다 ─────────────────────


def returns_cols(block):
    """`returns table ( … )` 의 (이름, 형) 목록 — 주석 걷고 소문자, 형의 공백은 한 칸."""
    m = re.search(r"(?is)returns\s+table\s*\(", block)
    assert m, "returns table 을 못 찾았습니다"
    depth, i = 1, m.end()
    while depth:
        depth += {"(": 1, ")": -1}.get(block[i], 0)
        i += 1
    inner = re.sub(r"--[^\n]*", "", block[m.end():i - 1])
    out = []
    # 최상위 쉼표로 자른다(`char(19)` 안 괄호는 쉼표가 없지만 안전하게 깊이를 센다).
    depth, cur, items = 0, [], []
    for ch in inner:
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
    for item in items:
        words = item.split()
        if words:
            out.append((words[0].lower(), " ".join(words[1:]).lower()))
    return out


def column_defects(block):
    """16칸이고, 앞 13칸은 옛 그대로, 끝 셋은 이름·형·순서 그대로인가."""
    cols = returns_cols(block)
    bad = []
    if len(cols) != len(WANT_COLS):
        bad.append("결과 칸이 {}개입니다({}개여야 합니다)".format(len(cols), len(WANT_COLS)))
    if cols[:len(OLD_COLS)] != OLD_COLS:
        bad.append("기존 13칸의 이름·형·순서가 바뀌었습니다: {}".format(cols[:len(OLD_COLS)]))
    if cols[len(OLD_COLS):] != NEW_TAIL:
        bad.append("끝 세 칸이 {} 입니다(기대 {})".format(cols[len(OLD_COLS):], NEW_TAIL))
    return bad


def head_of(block):
    """여는 `$$` 앞 머리 — 줄 주석 걷고 공백 접고 소문자."""
    head = block[:block.index(DOLLAR)]
    return re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", head)).strip().lower()


PUBLIC_HEAD_MUST = ("language plpgsql", "stable", "security definer",
                    "set search_path = public", "set plan_cache_mode = force_custom_plan")
API_HEAD_MUST = ("language sql", "stable", "security definer", "set search_path = ''")


def head_defects(block, must):
    head = head_of(block)
    return ["머리에 `{}` 가 없습니다".format(w) for w in must if w not in head]


def api_body_defects(block):
    body = flat(block[block.index(DOLLAR) + 2:block.rindex(DOLLAR)])
    want = "select * from public.search_buildings(q, lim, sigungu)"
    return [] if body == want else ["api 쌍둥이 본문이 `{}` 가 아닙니다: `{}`".format(want, body)]


def body_shape_defects(new_block, prev_block):
    """마지막 select 앞까지는 27a 와 글자 그대로 · 세 칸은 마지막 select 에서 기본키로."""
    bad = []
    for name, blk in (("새 판", new_block), ("27a", prev_block)):
        if blk.count(FINAL_SELECT_MARK) != 1:
            bad.append("{} 에서 마지막 select 표시 줄을 못 찾았습니다".format(name))
    if bad:
        return bad
    new_body = new_block[new_block.index(DOLLAR):]
    prev_body = prev_block[prev_block.index(DOLLAR):]
    if (new_body[:new_body.index(FINAL_SELECT_MARK)]
            != prev_body[:prev_body.index(FINAL_SELECT_MARK)]):
        bad.append("마지막 select 앞(검색 가지·정렬·limit)이 27a 와 다릅니다 — 가지를 건드리지 말 것")
    tail = statements(new_body[new_body.index(FINAL_SELECT_MARK):])
    flat_tail = re.sub(r"\s+", " ", tail)
    if flat_tail.count(OWNERSHIP_JOIN) != 1:
        bad.append("마지막 select 에 `{}` 가 한 번 없습니다".format(OWNERSHIP_JOIN))
    if flat_tail.count(OWNERSHIP_SELECT) != 1:
        bad.append("마지막 select 목록에 `{}` 가 한 번 없습니다".format(OWNERSHIP_SELECT))
    elif flat_tail.index(OWNERSHIP_SELECT) > flat_tail.find(" from top t"):
        bad.append("세 칸이 select 목록이 아니라 from 뒤에 있습니다")
    # select 목록에서 세 칸은 total_cnt **뒤**(칸 순서 = 결과 칸 순서).
    if "t.total_cnt, " + OWNERSHIP_SELECT not in flat_tail:
        bad.append("select 목록에서 세 칸이 total_cnt 바로 뒤가 아닙니다")
    return bad


def file_order_defects(sql):
    """파일 단위 순서 — 주석 걷은 문장 위치로 본다."""
    code = statements(sql).lower()

    def pos(pattern):
        m = re.search(pattern, code, re.M)
        return m.start() if m else None

    lock = pos(r"^set lock_timeout\b")
    begin = pos(r"^begin;")
    drop_api = pos(r"^drop function if exists api\.search_buildings\(text, int, text\);")
    drop_pub = pos(r"^drop function if exists (?:public\.)?search_buildings\(text, int, text\);")
    create_pub = pos(r"^create (?:or replace )?function (?:public\.)?search_buildings\(")
    create_api = pos(r"^create (?:or replace )?function api\.search_buildings\(")
    grant = pos(r"^grant execute on function api\.search_buildings\(")
    commit = pos(r"^commit;")
    notify = pos(r"^notify pgrst\b")
    named = dict(lock=lock, begin=begin, drop_api=drop_api, drop_pub=drop_pub,
                 create_pub=create_pub, create_api=create_api, grant=grant,
                 commit=commit, notify=notify)
    missing = [k for k, v in named.items() if v is None]
    if missing:
        return ["문장을 못 찾았습니다: {}".format(missing)]
    chain = ["lock", "begin", "drop_api", "drop_pub", "create_pub", "create_api", "grant",
             "commit", "notify"]
    bad = []
    for a, b in zip(chain, chain[1:]):
        if not named[a] < named[b]:
            bad.append("`{}` 가 `{}` 보다 앞이어야 합니다".format(a, b))
    if len(re.findall(r"(?m)^commit;", code)) != 1 or len(re.findall(r"(?m)^begin;", code)) != 1:
        bad.append("begin/commit 이 한 쌍이 아닙니다 — 한 파일 = 한 덩어리")
    return bad


RE_GRANT = re.compile(r"(?is)\bgrant\b[^;]*;")


def grant_defects(sql):
    """grant 는 api 쌍둥이에 주는 한 줄뿐 · public 원본은 revoke 만 · api 도 revoke 뒤 grant."""
    code = flat(re.sub(r"(?ims)^comment\s+on\s+.*?';\s*$", "", sql))
    bad = []
    grants = [g.strip() for g in RE_GRANT.findall(code)]
    if grants != [API_GRANT]:
        bad.append("grant 가 `{}` 한 줄이 아닙니다: {}".format(API_GRANT, grants))
    if PUBLIC_REVOKE not in code:
        bad.append("public 원본을 닫는 `{}` 가 없습니다".format(PUBLIC_REVOKE))
    if API_REVOKE not in code:
        bad.append("api 쌍둥이를 먼저 회수하는 `{}` 가 없습니다".format(API_REVOKE))
    elif API_GRANT in code and code.index(API_REVOKE) > code.index(API_GRANT):
        bad.append("api 회수가 grant 뒤에 있습니다 — 준 것을 도로 걷습니다")
    return bad


# ── 1. 결과 칸 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", [MIG, SCHEMA], ids=["migration", "schema"])
@pytest.mark.parametrize("which", ["search_buildings", "api.search_buildings"])
def test_sixteen_columns_with_the_three_at_the_end(path, which):
    bad = column_defects(fn_block(read(path), which))
    assert not bad, "{} 의 {}: {}".format(os.path.basename(path), which, " / ".join(bad))


def test_the_old_thirteen_match_the_previous_version():
    """전제 — OLD_COLS 상수가 27a 의 실제 13칸과 같다(상수만 맞추고 판을 못 읽는 가짜 초록 방지)."""
    assert returns_cols(fn_block(read(PREV), "search_buildings")) == OLD_COLS


# ── 2. 정본 ↔ 마이그레이션: 블록·comment 통째로 ─────────────────────────────


@pytest.mark.parametrize("which", ["search_buildings", "api.search_buildings"])
def test_function_block_is_the_schema_letter_for_letter(which):
    """머리 속성·본문·닫는 `$$;` 까지 — `create` 는 머리를 새 정의로 덮어쓴다."""
    assert fn_block(read(MIG), which) == fn_block(read(SCHEMA), which)


def test_comment_is_the_schema_letter_for_letter():
    """drop 으로 comment 도 사라진다 — 다시 단 글이 정본과 같아야 한다."""
    mine, canon = comment_stmt(read(MIG)), comment_stmt(read(SCHEMA))
    assert mine is not None, "마이그레이션에 comment 가 없습니다 — drop 으로 사라진 채 남습니다"
    assert mine == canon
    assert "is_jiphap" in canon, "전제: 정본 comment 가 새 세 칸을 말한다"


# ── 3. 머리 속성 (두 판이 함께 틀린 경우까지) ───────────────────────────────


@pytest.mark.parametrize("path", [MIG, SCHEMA], ids=["migration", "schema"])
def test_public_head(path):
    bad = head_defects(fn_block(read(path), "search_buildings"), PUBLIC_HEAD_MUST)
    assert not bad, " / ".join(bad)


@pytest.mark.parametrize("path", [MIG, SCHEMA], ids=["migration", "schema"])
def test_api_twin_head_and_body(path):
    block = fn_block(read(path), "api.search_buildings")
    bad = head_defects(block, API_HEAD_MUST) + api_body_defects(block)
    assert not bad, " / ".join(bad)


# ── 4. 본문 모양 — 가지는 27a 그대로, 세 칸은 마지막에 기본키로 ──────────────


@pytest.mark.parametrize("path", [MIG, SCHEMA], ids=["migration", "schema"])
def test_branches_untouched_and_columns_joined_last(path):
    bad = body_shape_defects(fn_block(read(path), "search_buildings"),
                             fn_block(read(PREV), "search_buildings"))
    assert not bad, " / ".join(bad)


# ── 5. 파일 단위 — 순서 · 권한 ───────────────────────────────────────────────


def test_file_order():
    bad = file_order_defects(read(MIG))
    assert not bad, " / ".join(bad)


def test_grants():
    bad = grant_defects(read(MIG))
    assert not bad, " / ".join(bad)


def test_schema_grants_only_the_api_twin():
    """정본 쪽 — public 원본에 grant 0줄 · api 쌍둥이에 anon grant 1줄."""
    code = flat(read(SCHEMA))
    pub = re.findall(r"(?i)\bgrant\s+execute\s+on\s+function\s+(?:public\.)?search_buildings\s*\(",
                     code)
    api = code.count(API_GRANT)
    assert pub == [], pub
    assert api == 1, api


# ── 6. 양성 대조 — 판정이 진짜 무는가 (파일은 안 건드린다, 사본만) ────────────


def _mig():
    return read(MIG)


COLUMN_MUTANTS = (
    ("tail_column_dropped", lambda b: b.replace(
        "  approve_date   date,\n  parking_cnt    integer\n)", "  approve_date   date\n)", 1)),
    ("tail_type_changed", lambda b: b.replace("  parking_cnt    integer\n)",
                                              "  parking_cnt    bigint\n)", 1)),
    ("tail_reordered", lambda b: b.replace(
        "  is_jiphap      boolean,\n  approve_date   date,",
        "  approve_date   date,\n  is_jiphap      boolean,", 1)),
    # 변형 꼴 — 새 칸을 앞에 끼운다(끝 셋은 그대로 길이도 16 이 아니다 → 앞 13칸 판정)
    ("inserted_in_front", lambda b: b.replace(
        "returns table (\n  bld_id         text,",
        "returns table (\n  is_jiphap      boolean,\n  bld_id         text,", 1)),
)


@pytest.mark.parametrize("which", ["search_buildings", "api.search_buildings"])
@pytest.mark.parametrize("name,mutate", COLUMN_MUTANTS, ids=[m[0] for m in COLUMN_MUTANTS])
def test_mutation_columns(which, name, mutate):
    block = fn_block(_mig(), which)
    assert not column_defects(block), "전제: 원문은 정상"
    broken = mutate(block)
    assert broken != block, "전제: 사본이 달라야 한다({})".format(name)
    assert column_defects(broken), "{} — 그런데도 '정상'이라 합니다".format(name)


HEAD_MUTANTS = (
    ("search_path_gone", "search_buildings", PUBLIC_HEAD_MUST,
     lambda b: b.replace("set search_path = public\n", "", 1)),
    ("not_definer", "search_buildings", PUBLIC_HEAD_MUST,
     lambda b: b.replace("security definer\n", "", 1)),
    ("plan_cache_as_comment", "search_buildings", PUBLIC_HEAD_MUST,
     lambda b: b.replace("set plan_cache_mode = force_custom_plan\n",
                         "-- set plan_cache_mode = force_custom_plan\n", 1)),
    ("api_search_path_gone", "api.search_buildings", API_HEAD_MUST,
     lambda b: b.replace("set search_path = ''\n", "", 1)),
    ("api_volatile", "api.search_buildings", API_HEAD_MUST,
     lambda b: b.replace("stable\n", "volatile\n", 1)),
)


@pytest.mark.parametrize("name,which,must,mutate", HEAD_MUTANTS,
                         ids=[m[0] for m in HEAD_MUTANTS])
def test_mutation_head(name, which, must, mutate):
    block = fn_block(_mig(), which)
    assert not head_defects(block, must), "전제: 원문은 정상"
    broken = mutate(block)
    assert broken != block, "전제: 사본이 달라야 한다({})".format(name)
    assert head_defects(broken, must), "{} — 그런데도 '정상'이라 합니다".format(name)
    # 정본과의 블록 대조도 같은 변조를 잡는다(한쪽만 바꾼 경우).
    assert broken != fn_block(read(SCHEMA), which)


@pytest.mark.parametrize("name,mutate", (
    ("unqualified", lambda b: b.replace("from public.search_buildings(", "from search_buildings(", 1)),
    ("other_function", lambda b: b.replace("public.search_buildings(", "public.search_stores(", 1)),
), ids=["unqualified", "other_function"])
def test_mutation_api_body(name, mutate):
    block = fn_block(_mig(), "api.search_buildings")
    assert not api_body_defects(block), "전제: 원문은 정상"
    assert api_body_defects(mutate(block)), "{} — 그런데도 '정상'이라 합니다".format(name)


BODY_MUTANTS = (
    # 흔한 꼴 — 조인 줄 제거
    ("join_removed", lambda b: b.replace("  " + OWNERSHIP_JOIN + "\n", "", 1)),
    # 변형 꼴 — 세 칸을 검색 가지(hit)에 실어 나른다
    ("carried_in_branch", lambda b: b.replace(
        "    select b.bld_id, b.pnu, b.nm_key, b.display_nm as bld_nm,\n           a.road_addr",
        "    select b.bld_id, b.pnu, b.nm_key, b.display_nm as bld_nm, b.is_jiphap,\n"
        "           a.road_addr", 1)),
    # 세 칸을 total_cnt 앞으로
    ("selected_before_total", lambda b: b.replace(
        "    t.total_cnt,\n    " + OWNERSHIP_SELECT + "\n",
        "    " + OWNERSHIP_SELECT + ",\n    t.total_cnt\n", 1)),
    # 조인을 기본키가 아니라 pnu 로(같은 땅 다른 동이 섞인다)
    ("joined_by_pnu", lambda b: b.replace(OWNERSHIP_JOIN, "join building bo on bo.pnu = t.pnu", 1)),
)


@pytest.mark.parametrize("name,mutate", BODY_MUTANTS, ids=[m[0] for m in BODY_MUTANTS])
def test_mutation_body_shape(name, mutate):
    prev = fn_block(read(PREV), "search_buildings")
    block = fn_block(_mig(), "search_buildings")
    assert not body_shape_defects(block, prev), "전제: 원문은 정상"
    broken = mutate(block)
    assert broken != block, "전제: 사본이 달라야 한다({})".format(name)
    assert body_shape_defects(broken, prev), "{} — 그런데도 '정상'이라 합니다".format(name)


FILE_MUTANTS = (
    ("lock_after_begin", lambda s: s.replace("set lock_timeout = '5s';\n\nbegin;\n",
                                             "begin;\nset lock_timeout = '5s';\n", 1)),
    ("public_dropped_first", lambda s: s.replace(
        "drop function if exists api.search_buildings(text, int, text);\n"
        "drop function if exists search_buildings(text, int, text);\n",
        "drop function if exists search_buildings(text, int, text);\n"
        "drop function if exists api.search_buildings(text, int, text);\n", 1)),
    ("notify_before_commit", lambda s: s.replace("notify pgrst, 'reload schema';\n", "", 1)
     .replace("\ncommit;\n", "\nnotify pgrst, 'reload schema';\ncommit;\n", 1)),
    ("second_commit", lambda s: s.replace(
        "\n" + PUBLIC_REVOKE + "\n", "\n" + PUBLIC_REVOKE + "\ncommit;\nbegin;\n", 1)),
)


@pytest.mark.parametrize("name,mutate", FILE_MUTANTS, ids=[m[0] for m in FILE_MUTANTS])
def test_mutation_file_order(name, mutate):
    text = _mig()
    assert not file_order_defects(text), "전제: 원문은 정상"
    broken = mutate(text)
    assert broken != text, "전제: 사본이 달라야 한다({})".format(name)
    assert file_order_defects(broken), "{} — 그런데도 '정상'이라 합니다".format(name)


API_GRANT_RAW = ("grant execute on function api.search_buildings(text, int, text)  "
                 "to anon, authenticated;")
GRANT_MUTANTS = (
    ("api_grant_removed", lambda s: s.replace(API_GRANT_RAW, "", 1)),
    ("public_grant_added", lambda s: s.replace(
        "\ncommit;\n", "\ngrant execute on function search_buildings(text, int, text) to anon;\n"
        "commit;\n", 1)),
    # 변형 꼴 — public. 수식 + 대문자
    ("public_grant_qualified_upper", lambda s: s.replace(
        "\ncommit;\n", "\nGRANT EXECUTE ON FUNCTION public.search_buildings(text, int, text) "
        "TO anon;\ncommit;\n", 1)),
    ("public_revoke_removed", lambda s: s.replace(PUBLIC_REVOKE, "", 1)),
    ("api_revoke_after_grant", lambda s: s.replace(
        "revoke all on function api.search_buildings(text, int, text)  from public, anon, "
        "authenticated;\n", "", 1).replace(
        API_GRANT_RAW + "\n", API_GRANT_RAW + "\n" + API_REVOKE + "\n", 1)),
)


@pytest.mark.parametrize("name,mutate", GRANT_MUTANTS, ids=[m[0] for m in GRANT_MUTANTS])
def test_mutation_grants(name, mutate):
    text = _mig()
    assert not grant_defects(text), "전제: 원문은 정상"
    broken = mutate(text)
    assert broken != text, "전제: 사본이 달라야 한다({})".format(name)
    assert grant_defects(broken), "{} — 그런데도 '정상'이라 합니다".format(name)


def test_a_commented_grant_is_not_a_grant():
    """반대 방향 — 주석으로 적은 grant 는 grant 가 아니다(헛것을 잡으면 사람이 가드를 느슨하게 고친다)."""
    text = _mig().replace(
        "\ncommit;\n",
        "\n-- grant execute on function search_buildings(text, int, text) to anon;\ncommit;\n", 1)
    assert "-- grant execute on function search_buildings" in text
    assert not grant_defects(text)


def test_comment_mutation_is_noticed():
    """comment 한 글자만 바꿔도 정본 대조가 빨갛다 · comment 를 지우면 None."""
    text = _mig()
    assert comment_stmt(text.replace("'§8.1 건물 검색.", "'§8.1 건물검색.", 1)) != \
        comment_stmt(read(SCHEMA))
    no_comment = re.sub(r"(?ims)^comment\s+on\s+function\s+search_buildings.*?';\s*$", "", text)
    assert comment_stmt(no_comment) is None
