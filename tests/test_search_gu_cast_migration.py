# -*- coding: utf-8 -*-
"""구 비교를 색인이 타게(2026-09-10a) + 이름 가지의 PNU 구 범위(2026-09-27a, 결정 0029)
— 두 검색 함수(`search_scope`·`search_buildings`)의 불변식을 지킨다.

무엇을 막나
-----------
`mv_search_parcel.sigungu_code` 는 `char(5)` 인데 `pat.gu` 는 `text` 다. 그냥 견주면
PostgreSQL 이 **컬럼 쪽**을 text 로 올려 맞춰 `idx_msp_sigungu` 를 못 탄다 — 구를 골라도
표를 통째로 훑는다(라이브 실측 2026-09-10: Parallel Seq Scan 188,442행·116ms →
Index Scan 12,138행·8ms). 그래서 함수마다 두 곳에 `::char(5)` 를 붙였다(2026-09-10a).
그 위에 2026-09-27a 가 이름 가지에 **PNU 구 범위** 한 절을 더했다 — `building` 에는 구
칸이 없어 PNU 앞 5자리로 범위를 자른다.

⛔ 이 결함들은 **에러가 안 난다.** 캐스트가 빠지면 답은 같고 느리기만 하고, 전국 가지가
   빠지면 구를 안 고른 검색이 조용히 0건이 된다 — 사람 눈으로는 영영 안 잡히는 종류다.
   그것이 이 파일의 존재 이유다.

여기서 보는 것 (DB 없이 SQL 글자만 — CI 에는 DB 가 없다)
  0) 최신 판을 **찾아서** 보고, 그 결과가 핀(`PIN`)과 같은지 확인한다(형제
     test_search_stores_migration.py 의 "핀 + 자동 탐색 + 일치 확인" 관습). 새 판이
     들어오면 핀 대조가 시끄럽게 터진다 — 핀을 올리는 것이 곧 "새 판을 사람이 봤다"다.
     ⓘ 2026-10-09a(물결 1-A1)부터 두 함수의 최신 판이 **갈린다** — `search_buildings` 만
       결과 칸 셋을 더해 다시 만들었다. 그래서 핀은 함수마다 하나다.
     이미 적용된 옛 판(2026-09-10a)의 두 함수 블록은 **SHA-256 못**으로 고정한다
     ("적용된 마이그레이션 파일은 고치지 않는다"를 기계가 지킨다).
  1) 두 함수 본문에 `pc.sigungu_code = pat.gu::char(5)` 가 **정확히 두 번씩**,
     캐스트 없는 `= pat.gu)` 는 **0번**.
  2) 전국 가지(`pat.gu is null or`)를 **모양별로** 센다 — 구 코드 비교 옆 2번 +
     PNU 범위 옆 1번 = 함수마다 3번. 총계는 두 모양의 합과 같아야 한다(다르면 낯선 모양의
     전국 가지가 생긴 것이다 — 숫자를 올리지 말고 그 모양을 못 박을 것).
     그리고 각 절이 전국 가지와 **한 괄호 안**에 있는지(위치)를 따로 본다.
  3) 최신 판의 함수 블록이 정본(schema.sql)과 **글자 그대로** 같다 — 함수 본문
     주석은 `pg_proc.prosrc` 에 실려 라이브의 일부가 되므로, 한쪽만 다듬는 것이 곧
     정본↔라이브 드리프트다(2026-09-01 2차 적대검증).
  4) 원자성 — `begin;` 이 첫 DDL 앞, `commit;` 이 마지막 DDL 뒤, `notify pgrst` 는
     commit **뒤**, `concurrently` 는 없다(트랜잭션 안에서 못 돈다).
  5) 다시 만든 곳에서 다시 닫는다(이 파일이 보는 두 함수의 revoke — 2026-09-27a 는
     `search_stores` 까지 revoke ×3 이고 그 셋째는 tests/test_search_plpgsql_migration.py 가
     본다) · public 을 여는 `grant` 는 0개 · api 쌍둥이는 안 건드린다 — 단 결과 칸이
     바뀌어 쌍둥이를 다시 세워야 했던 판(`API_TWIN_REBUILT`)만은 쌍둥이가 정본과 글자
     그대로이고 grant 가 **api 쌍둥이에만** 있는지 본다.
  6) 가드 자신의 시험 — 한 군데를 망가뜨린 **사본**에 판정을 돌려 빨간불이 나는지 본다.

ⓘ 도우미(read·norm·statements·fn_block)는 형제 test_search_stores_migration.py 에서
  **복사**해 왔다 — import 하지 않는다. 시험 파일끼리 얽히면 한쪽의 고장이 다른 쪽을
  조용히 가린다.
"""

import hashlib
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIG_DIR = os.path.join(ROOT, "supabase", "migrations")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

# 함수마다 그 함수를 **마지막으로 다시 만든** 판. ⛔ 새 판을 넣는 사람은 여기도 함께
#    올린다 — 안 올리면 아래 `test_the_finder_agrees_with_the_pin` 이 시끄럽게 터진다
#    (그 시끄러움이 이 상수의 존재 이유다).
#    search_scope = 2026-09-27a(결정 0029) · search_buildings = 2026-10-09a(결과 칸 셋 —
#    물결 1-A1. 본문의 검색 가지·캐스트·PNU 범위는 27a 그대로다).
PIN = {
    "search_scope": os.path.join(MIG_DIR, "2026-09-27a_search_fns_plpgsql.sql"),
    "search_buildings": os.path.join(MIG_DIR, "2026-10-09a_search_ownership_cols.sql"),
}

# 결과 칸이 바뀌어 api 쌍둥이까지 다시 세운 판 — `create or replace` 가 거부하므로 drop →
# 재생성 → grant 가 불가피하다(2026-08-14e 머리말). 이 판들만 쌍둥이·grant 를 허락하되,
# 쌍둥이가 정본과 글자 그대로이고 grant 가 api 쌍둥이에만 있는지 본다(§4).
API_TWIN_REBUILT = (PIN["search_buildings"],)

# 이미 라이브에 적용된 옛 판 — 고치지 않는다. 아래 SHA 못이 그것을 지킨다.
APPLIED_0910A = os.path.join(MIG_DIR, "2026-09-10a_search_gu_index_cond.sql")

# 2026-09-10a 의 함수 블록(`create … function <이름>(` 부터 `$$;` 앞까지, CRLF→LF) 원문의
# SHA-256. ⛔ 안 맞으면 "누군가 적용된 파일을 고쳤다"는 뜻이다 — 상수를 조용히 갱신하지
#    말 것(형제 CANON_STATEMENT_SHA 와 같은 관용구). 파일을 되돌리는 것이 답이다.
APPLIED_0910A_SHA = {
    "search_scope":
        "f4b5b2f072dfd9a3e005e8e5d9e2fc0e22e89c4ee4932a495cac18c3e84a2518",
    "search_buildings":
        "d8c8c29ec321028b65b335e907de43c763013be23b848ca20f5cee43431d1c70",
}

# (함수 이름, revoke 에 적히는 인자 타입) — 철자가 갈리면 권한 가드가 헛돈다.
FUNCS = (
    ("search_scope", "text, text"),
    ("search_buildings", "text, int, text"),
)

CAST = "pc.sigungu_code = pat.gu::char(5)"
BARE = "= pat.gu)"           # 캐스트가 빠진 옛 모양
NATIONWIDE = "pat.gu is null or"

# 전국 가지가 붙는 **아는 모양** 두 가지. ⛔ 총계(`pat.gu is null or` 몇 번)로만 세지 말 것 —
#    절이 하나 더 붙는 날 숫자만 올리게 되고, 그러다 보면 '3'·'4' 가 무엇을 뜻하는지
#    아무도 모르는 채 대조가 형식만 남는다.
# ① 구 코드 비교(2026-09-10a) — 함수마다 2번.
GU_CLAUSE = "({} {})".format(NATIONWIDE, CAST)
# ② 이름 가지의 PNU 구 범위(2026-09-27a) — 함수마다 1번. 통짜 한 줄 대신 **부분 조건 셋**을
#    각각 센다(의미를 지키는 줄바꿈·들여쓰기 변화에 덜 부서진다). 셋 다 `flat()` 기준.
#    ⛔ 구를 안 고르면 `pat.gu::char(19)` 가 NULL 이고 `b.pnu >= NULL` 도 NULL 이라
#       전국 가지가 없으면 **이름 가지가 통째로 0건**이 된다(에러 0).
PNU_NATIONWIDE = "({} (b.pnu".format(NATIONWIDE)
PNU_LOWER = "b.pnu >= pat.gu::char(19)"
# ⛔ `repeat('9',14)` 의 14 는 PNU 19자 − 구 코드 5자다. 13 이면 구의 마지막 필지
#    몇 개가 조용히 빠진다. `::char(19)` 가 빠지면 text 비교가 되어 색인이 죽는다.
PNU_UPPER = "b.pnu <= (pat.gu || repeat('9',14))::char(19)"
PNU_PARTS = (PNU_NATIONWIDE, PNU_LOWER, PNU_UPPER)

DOLLAR = chr(36) * 2


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def norm(text):
    """줄바꿈 표기(CRLF/LF)만 통일한다 — 공백·주석은 일부러 안 건드린다."""
    return text.replace("\r\n", "\n")


def statements(sql):
    """주석을 걷어낸 **실제 SQL 문장만**.

    설명 주석에 적어 둔 말이 문장으로 오해되면 코드가 망가져도 초록이 된다. 이 파일은
    특히 그렇다 — ⛔ 주석에 `pat.gu is null or` 라는 말이 **글로** 적혀 있어서,
    주석을 안 걷으면 개수 세기가 통째로 헛돈다.
    """
    return "\n".join(
        line for line in norm(sql).splitlines() if not line.lstrip().startswith("--")
    )


# `comment on … is '…';` 한 문장. 여러 줄에 걸치고, 끝은 항상 `';` 다.
RE_COMMENT_STMT = re.compile(r"(?ims)^comment\s+on\s+.*?';\s*$")


def code_only(sql):
    """주석 **그리고 `comment on … is '…'` 문장까지** 걷어낸 것(형제 파일과 같은 규칙)."""
    return RE_COMMENT_STMT.sub("", statements(sql))


def flat(sql):
    """주석을 걷고 **공백을 한 칸으로** 접은 것 — 개수·권한 단언은 전부 이것을 본다.

    ⛔ 한 가지 정규화로 통일한다 — 개수마다 다른 정규화(공백 보존 vs 접기)를 쓰고 그
       합을 견주면, 한 절이 줄바꿈되는 날 합 검사가 흔들린다.
    """
    return re.sub(r"\s+", " ", statements(sql))


def fn_head_re(name):
    """`create [or replace] function [public.]<name>(` — api 쌍둥이는 뺀다.

    ⛔ `or replace` 는 **선택**이다 — `create function …` 으로 쓴 판이 조용히 빠지면
       더 낡은 것과 비교되며 초록이 된다. 탐색기와 `fn_block` 이 **같은** 규칙을 쓴다
       (두 정규식이 다르면 '찾았는데 못 뜯는' 거짓 메시지가 남는다).
    ⛔ `(?!api\\.)` 로 api 쌍둥이를 배제한다 — 통과 함수라 본문이 한 줄뿐이고, 그걸 잡으면
       아래 개수 세기가 전부 0 이 되어 **가짜 초록**이 된다.
    """
    return re.compile(
        r"(?im)^create\s+(?:or\s+replace\s+)?function\s+(?!api\.)(?:public\.)?"
        + name + r"\s*\(")


def fn_block(sql, name):
    """`create [or replace] function <name>(` 부터 `$$;` 까지 (머리 + 본문)."""
    sql = norm(sql)
    m = fn_head_re(name).search(sql)
    assert m, "{} 정의를 못 찾았습니다".format(name)
    end = sql.index(DOLLAR + ";", m.start())
    return sql[m.start():end]


def sha(text):
    return hashlib.sha256(norm(text).encode("utf-8")).hexdigest()


def at(pattern, sql, last=False):
    """줄머리 정규식이 처음(또는 마지막) 나오는 **위치**."""
    found = [m.start() for m in re.finditer(pattern, sql)]
    assert found, pattern
    return found[-1] if last else found[0]


def latest_migration_defining(fn, mig_dir=MIG_DIR):
    """public 쪽 `fn` 을 **마지막으로 다시 만든** 마이그레이션 경로.

    파일명 정렬이 곧 적용 순서라 뒤가 이긴다(형제 test_schema_function_drift.py 와 같은 규칙).
    ⛔ 주석(과 `comment on` 글)을 걷은 뒤 찾는다 — 머리말에 인용된 `create … function`
       한 줄이 판정을 가로채면 엉뚱한 파일을 대조하며 초록이 된다.
    """
    head = fn_head_re(fn)
    found = None
    for name in sorted(os.listdir(mig_dir)):
        if not name.endswith(".sql"):
            continue
        path = os.path.join(mig_dir, name)
        if head.search(code_only(read(path))):
            found = path
    assert found, "{} 를 정의하는 마이그레이션이 하나도 없습니다".format(fn)
    return found


MIG_OF = dict((fn, latest_migration_defining(fn)) for fn, _ in FUNCS)
MIGRATIONS = sorted(set(MIG_OF.values()))
# ⛔ 빈 parametrize 는 실패가 아니라 **skip** 이다 — 탐색이 헛돌면 아래 파일 단위 시험이
#    통째로 조용히 사라진다. 그래서 산문이 아니라 코드로 못 박는다.
assert MIGRATIONS, "최신 마이그레이션을 한 개도 못 찾았습니다 — 파일 단위 시험이 안 돕니다"

LABEL = dict((p, "마이그레이션 " + os.path.basename(p)) for p in MIGRATIONS)
LABEL[SCHEMA] = "정본 schema.sql"

# (경로, 함수) 짝 — 함수마다 **그 함수를 정의한** 최신 판 + 정본. ⛔ 판 × 함수 곱으로 돌리면
#    판이 갈린 날(2026-10-09a 는 search_buildings 만 정의한다) 남의 함수를 못 찾아 빨개진다.
SITES = [(MIG_OF[fn], fn) for fn, _ in FUNCS] + [(SCHEMA, fn) for fn, _ in FUNCS]
SITE_IDS = ["{}-{}".format(os.path.basename(p)[:11], fn) for p, fn in SITES]


# 아래 시험들이 쓰는 **판정 한 벌**. 돌연변이 시험(§6)이 이걸 그대로 태워서
# "가드가 진짜 무는지"를 증명한다 — 시험 안에서 조건을 다시 쓰면 돌연변이가 그 사본만
# 통과시켜 아무것도 증명하지 못한다.
def cast_defects(block):
    """함수 블록 하나를 보고 **어긋난 점 목록**을 돌려준다(비었으면 정상)."""
    code = flat(block)
    bad = []
    n_cast = code.count(CAST)
    if n_cast != 2:
        bad.append("`{}` 가 {}번입니다(2번이어야 합니다)".format(CAST, n_cast))
    n_bare = code.count(BARE)
    if n_bare:
        bad.append("캐스트 없는 `{}` 가 {}군데 남았습니다".format(BARE, n_bare))
    n_gu = code.count(GU_CLAUSE)
    if n_gu != 2:
        bad.append("구 코드 비교의 전국 가지(`{}`)가 {}번입니다(2번이어야 합니다)"
                   .format(GU_CLAUSE, n_gu))
    for part in PNU_PARTS:
        n = code.count(part)
        if n != 1:
            bad.append("PNU 구 범위의 `{}` 가 {}번입니다(1번이어야 합니다 — 2026-09-27a)"
                       .format(part, n))
    n_wide = code.count(NATIONWIDE)
    n_known = n_gu + code.count(PNU_NATIONWIDE)
    if n_wide != n_known:
        bad.append("`{}` 가 {}번인데 아는 모양(구 코드 비교 + PNU 범위)은 {}번입니다 — "
                   "낯선 모양의 전국 가지가 생겼습니다. 숫자를 올리지 말고 그 모양을 "
                   "위 상수에 못 박으세요".format(NATIONWIDE, n_wide, n_known))
    return bad


def enclosing_group(text, pos):
    """`pos` 를 감싸는 **가장 안쪽 괄호**의 (여는 위치, 닫는 위치). 없으면 None."""
    depth = 0
    for i in range(pos - 1, -1, -1):
        if text[i] == ")":
            depth += 1
        elif text[i] == "(":
            if depth == 0:
                close_depth = 0
                for j in range(i, len(text)):
                    if text[j] == "(":
                        close_depth += 1
                    elif text[j] == ")":
                        close_depth -= 1
                        if close_depth == 0:
                            return i, j
                return None
            depth -= 1
    return None


def placement_defects(block):
    """절마다 전국 가지와 **한 괄호 안**에 있는지(위치) — 어긋난 점 목록.

    `is null` 가지와 비교가 따로 떨어지면(예: `and pat.gu is null` 을 위로 올리면) 구를
    고른 검색이 통째로 0건이 된다 — 개수는 맞아도 에러 없이 조용하다.
    """
    code = flat(block)
    bad = []
    # ① 구 코드 비교: 캐스트를 감싸는 괄호가 곧 `(pat.gu is null or …)` 여야 한다.
    for m in re.finditer(re.escape(CAST), code):
        g = enclosing_group(code, m.start())
        if g is None or not code[g[0] + 1:].startswith(NATIONWIDE):
            bad.append("캐스트 비교(위치 {})가 전국 가지와 한 괄호 안에 없습니다"
                       .format(m.start()))
    # ② PNU 범위: 아래·위 경계가 **같은** 괄호에 있고, 그 괄호를 감싸는 괄호가
    #    `(pat.gu is null or …)` 여야 한다.
    for m in re.finditer(re.escape(PNU_LOWER), code):
        inner = enclosing_group(code, m.start())
        if inner is None or PNU_UPPER not in code[inner[0]:inner[1] + 1]:
            bad.append("PNU 아래·위 경계가 한 괄호 안에 없습니다(위치 {})".format(m.start()))
            continue
        outer = enclosing_group(code, inner[0])
        if outer is None or not code[outer[0] + 1:].startswith(NATIONWIDE):
            bad.append("PNU 범위(위치 {})가 전국 가지와 한 괄호 안에 없습니다"
                       .format(m.start()))
    return bad


RE_GRANT_STMT = re.compile(r"(?is)\bgrant\b[^;]*;")
RE_API_TWIN_HEAD = re.compile(
    r"(?im)^create\s+(?:or\s+replace\s+)?function\s+api\.(\w+)\s*\(")


def grant_defects(sql, twin_rebuilt):
    """grant 문을 하나씩 본다(주석 걷고 공백 접은 뒤) — 어긋난 점 목록.

    · 쌍둥이를 다시 세운 판이 아니면 grant 는 0줄이어야 한다.
    · 다시 세운 판이면 grant 는 전부 `on function api.<이름>(…)` 이어야 한다 — public 원본을
      여는 grant 는 0줄. 그리고 다시 세운 쌍둥이마다 anon 에게 주는 grant 가 있어야 한다
      (drop 으로 권한이 사라진다 — 없으면 화면이 permission denied).
    ⚠️ 못 보는 것: `grant all on all functions in schema …` 같은 묶음 grant 는 대상 이름이
       없으므로 '이름 없는 grant' 로 빨강이 된다(무는 쪽으로 틀린다).
    """
    code = flat(code_only(sql))
    grants = RE_GRANT_STMT.findall(code)
    if not twin_rebuilt:
        return ["grant 가 {}줄 있습니다 — 이 판은 권한을 열지 않습니다".format(len(grants))
                ] if grants else []
    bad = []
    for g in grants:
        m = re.search(r"(?i)\bon\s+function\s+([\w.]+)\s*\(", g)
        if m is None or not m.group(1).lower().startswith("api."):
            bad.append("api 쌍둥이가 아닌 대상에 grant 가 있습니다: `{}`".format(g.strip()))
    for name in RE_API_TWIN_HEAD.findall(code_only(sql)):
        want = re.compile(r"(?i)\bgrant\s+execute\s+on\s+function\s+api\." + name
                          + r"\s*\([^)]*\)\s+to\b[^;]*\banon\b")
        if not any(want.search(g) for g in grants):
            bad.append("다시 세운 api.{} 에 anon 실행 권한을 다시 주지 않습니다".format(name))
    return bad


def api_twin_block(sql, name):
    """`create [or replace] function api.<name>(` 부터 `$$;` 까지 — 첫 줄의 `or replace` 는
    접는다(마이그레이션은 drop 뒤 `create`, 정본은 `create or replace` 로 쓴다)."""
    sql = norm(sql)
    m = re.search(r"(?im)^create\s+(?:or\s+replace\s+)?function\s+api\." + name
                  + r"\s*\(", sql)
    if m is None:
        return None
    end = sql.index(DOLLAR + ";", m.start())
    return re.sub(r"(?i)^create\s+or\s+replace\s+function", "create function",
                  sql[m.start():end])


def api_twin_defects(sql, twin_rebuilt, schema_sql):
    """api 쌍둥이를 건드리는지 — 다시 세운 판이면 정본과 글자 그대로인지."""
    code = code_only(sql)
    if not twin_rebuilt:
        return ["마이그레이션이 api.* 를 건드립니다 — 이 판의 범위 밖입니다"
                ] if "api." in code else []
    bad = []
    names = RE_API_TWIN_HEAD.findall(code)
    if not names:
        bad.append("쌍둥이를 다시 세운 판이라는데 api 쌍둥이 정의가 없습니다")
    for name in names:
        mine, canon = api_twin_block(sql, name), api_twin_block(schema_sql, name)
        if canon is None or mine != canon:
            bad.append("api.{} 가 정본과 글자 그대로가 아닙니다".format(name))
    return bad


# ── 0. 핀 · 적용된 옛 판 ─────────────────────────────────────────────────────


def test_the_finder_agrees_with_the_pin():
    """⛔ 탐색기가 옛 파일로 미끄러지면 파일 단위 시험이 **이미 검증 끝난 판**을 다시
    보며 초록이 된다 — 새 판의 grant·notify 는 한 번도 안 읽힌다."""
    for fn, _ in FUNCS:
        assert MIG_OF[fn] == PIN[fn], (
            "{} 의 최신 판이 {} 로 잡혔습니다 — 기대는 {} 입니다. 새 판이면 PIN 을 올리고 "
            "그 판을 사람이 한 번 읽으세요".format(
                fn, os.path.basename(MIG_OF[fn]), os.path.basename(PIN[fn])))
    assert MIGRATIONS == sorted(set(PIN.values()))


@pytest.mark.parametrize("fn", sorted(APPLIED_0910A_SHA))
def test_the_applied_0910a_blocks_are_nailed(fn):
    """⛔ 적용된 마이그레이션 파일은 고치지 않는다(CLAUDE.md) — 규칙만으로는 가드가 아니다.
    dev·staging 을 마이그레이션 재생으로 세우면 이 파일이 다시 실행된다."""
    assert sha(fn_block(read(APPLIED_0910A), fn)) == APPLIED_0910A_SHA[fn], (
        "적용된 2026-09-10a 의 {} 블록이 바뀌었습니다 — 되돌리세요(상수를 올리지 말 것)"
        .format(fn))


def test_the_sha_nail_really_bites():
    """⛔ 해시 못이 헛돌면(예: 늘 같은 것을 해시) 적용된 판이 바뀌어도 초록이다."""
    block = fn_block(read(APPLIED_0910A), "search_scope")
    assert sha(block) == APPLIED_0910A_SHA["search_scope"], "전제: 원문은 맞는다"
    tampered = block.replace(CAST, "pc.sigungu_code = pat.gu", 1)
    assert tampered != block, "전제: 사본이 실제로 달라야 한다"
    assert sha(tampered) != APPLIED_0910A_SHA["search_scope"]


# ── 1. 캐스트·전국 가지·PNU 범위가 제 모양·제 개수인가 ─────────────────────────


class TestTheCastIsThere:
    @pytest.mark.parametrize("path,fn", SITES, ids=SITE_IDS)
    def test_both_sites_compare_as_char5(self, path, fn):
        """⛔ 캐스트가 빠지면 색인이 Index Cond → Filter 로 떨어진다 — **에러 0**,
        답도 같고 느리기만 하다(그래서 사람이 못 잡는다)."""
        bad = cast_defects(fn_block(read(path), fn))
        assert not bad, "{} 의 {}: {}".format(LABEL[path], fn, " / ".join(bad))

    @pytest.mark.parametrize("path,fn", SITES, ids=SITE_IDS)
    def test_the_finder_really_finds_a_body(self, path, fn):
        """⛔ **파서가 헛돌면 위 시험이 조용히 초록이 된다** — 이 레포가 가장 여러 번
        데인 '가짜 초록'이다. 블록이 진짜 그 함수의 본문인지 못 박아 둔다."""
        block = fn_block(read(path), fn)
        assert "mv_search_parcel" in block, (
            "{} 의 {} 블록에 mv_search_parcel 이 없습니다 — 엉뚱한 것을 뜯었습니다"
            .format(LABEL[path], fn))
        assert not re.match(r"(?i)create\s+(or\s+replace\s+)?function\s+api\.",
                            block.lstrip()), (
            "api 쌍둥이를 잡았습니다 — 통과 함수라 본문이 한 줄이고, 그러면 개수 "
            "세기가 전부 0 이 되어 가드가 있는 척만 합니다")


# ── 2. 전국 검색 절반은 그대로 · 한 괄호 안에 ─────────────────────────────────


class TestNationwideSearchSurvives:
    @pytest.mark.parametrize("path,fn", SITES, ids=SITE_IDS)
    def test_the_null_branch_is_untouched(self, path, fn):
        """⛔ 이 둘은 구를 **안 고른 전국 검색을 일부러 허용**한다(결정 0028 에서 구를
        필수로 둔 `search_stores` 와 다른 점이다). 전국 가지를 지우면 **전국 검색이
        조용히 막힌다** — 에러가 아니라 0건이 된다. 모양별로 센다(구 코드 비교 2 +
        PNU 범위 1), 총계는 그 합이어야 한다."""
        code = flat(fn_block(read(path), fn))
        assert code.count(GU_CLAUSE) == 2, (
            "{} 의 {}: 구 코드 비교의 전국 가지가 2번이 아닙니다"
            .format(LABEL[path], fn))
        assert code.count(PNU_NATIONWIDE) == 1, (
            "{} 의 {}: PNU 범위의 전국 가지가 1번이 아닙니다 — 구를 안 고르면 "
            "이름 가지가 통째로 0건이 됩니다".format(LABEL[path], fn))
        assert code.count(NATIONWIDE) == (
            code.count(GU_CLAUSE) + code.count(PNU_NATIONWIDE)), (
            "{} 의 {}: 아는 모양에 안 맞는 `{}` 가 있습니다".format(
                LABEL[path], fn, NATIONWIDE))

    @pytest.mark.parametrize("path,fn", SITES, ids=SITE_IDS)
    def test_the_two_halves_sit_in_the_same_condition(self, path, fn):
        """`is null` 가지와 비교가 **한 괄호 안**에 있어야 옛 동작과 같다(개수가 아니라 위치).

        따로 떨어지면(예: `and pat.gu is null` 을 위로 올리면) 구를 고른 검색이 통째로
        0건이 된다 — 이것도 에러 없이 조용하다.
        """
        bad = placement_defects(fn_block(read(path), fn))
        assert not bad, "{} 의 {}: {}".format(LABEL[path], fn, " / ".join(bad))


# ── 3. 정본과 최신 판이 글자 그대로 같은가 ────────────────────────────────────


class TestSchemaMirrorsTheMigration:
    @pytest.mark.parametrize("fn", [f for f, _ in FUNCS])
    def test_function_blocks_letter_for_letter(self, fn):
        """⛔ 정본만 살짝 다듬는 것이 곧 정본↔라이브 불일치다(2026-09-01 2차 적대검증).
        함수 본문 주석은 `pg_proc.prosrc` 에 실려 **라이브의 일부**가 되기 때문이다.

        ⓘ 전 함수를 훑는 형제 가드가 따로 있다(tests/test_schema_function_drift.py).
          여기서는 이 둘을 못 박아 두어, 실패 메시지가 무엇 때문인지 바로 보이게 한다.
        """
        assert fn_block(read(MIG_OF[fn]), fn) == fn_block(read(SCHEMA), fn), (
            "{} 의 본문이 정본과 다릅니다(최신 판 {}) — 마이그레이션을 이미 적용했다면 "
            "그쪽이 라이브입니다. 설명을 늘리고 싶으면 `create` 문 **바깥** 머리말에 "
            "적으세요.".format(fn, os.path.basename(MIG_OF[fn])))


# ── 4. 전부 아니면 전무 · 다시 만든 곳에서 다시 닫는가 ───────────────────────


@pytest.mark.parametrize("path", MIGRATIONS)
class TestAtomicity:
    def test_begin_comes_before_the_first_ddl(self, path):
        """⛔ `dbx.py` 는 자동커밋이다 — 감싸지 않고 중간에 끊기면 **한 함수만 새 것**인
        상태가 남는다(에러 0 · 한쪽만 느린, 찾기 어려운 어긋남)."""
        code = statements(read(path))
        assert at(r"(?m)^begin;", code) < at(
            r"(?im)^create\s+(?:or\s+replace\s+)?function\b", code), (
            "첫 DDL 이 begin; 보다 앞에 있습니다")

    def test_commit_comes_after_the_last_ddl(self, path):
        code = statements(read(path))
        last_ddl = max(
            at(r"(?im)^create\s+(?:or\s+replace\s+)?function\b", code, last=True),
            at(r"(?im)^revoke\b", code, last=True),
        )
        assert last_ddl < at(r"(?m)^commit;", code), (
            "마지막 문장이 commit; 뒤에 있습니다 — 덩어리 밖으로 새어 나갔습니다")

    def test_notify_comes_after_commit(self, path):
        """⛔ 커밋 **뒤**여야 한다 — 롤백된 판에서 PostgREST 에 헛알림이 가면 안 된다
        (09-09b 선례). 빠지면 DB 에는 함수가 멀쩡한데 화면은 옛 캐시를 쓴다."""
        code = statements(read(path))
        assert at(r"(?m)^commit;", code) < at(r"(?im)^notify\s+pgrst\b", code)

    def test_no_concurrently(self, path):
        """⛔ `concurrently` 만은 트랜잭션 안에서 못 돈다 — 있으면 판이 통째로 실패한다."""
        assert "concurrently" not in statements(read(path)).lower()


class TestItClosesTheDoorAgain:
    @pytest.mark.parametrize("fn,args", FUNCS)
    def test_revoke_is_restated(self, fn, args):
        """다시 만든 곳에서 다시 닫는다(2026-09-01d·2026-08-16b 관습).

        `create or replace` 가 권한을 보존하므로 기능상 필수는 아니다 — 그래도 대시보드가
        같은 함수를 다시 만드는 날 anon 기본권한이 조용히 붙어도 여기서 걷힌다.
        ⓘ 함수와 **그 함수의 판**을 짝지어 본다 — 판이 둘로 갈리는 날 남의 함수 revoke 를
          요구하지 않게.
        """
        line = "revoke all on function {}({}) from public, anon, authenticated;".format(
            fn, args)
        assert line in flat(read(MIG_OF[fn])), (
            "{} 에 `{}` 가 없습니다".format(os.path.basename(MIG_OF[fn]), line))

    @pytest.mark.parametrize("path", MIGRATIONS)
    def test_it_never_opens_the_public_original(self, path):
        """⛔ 화면이 부르는 문은 api 쌍둥이 하나뿐이다 — public 원본은 2026-09-05a 로
        닫아 둔 그대로여야 한다. grant 가 한 줄이라도 있으면 그 문이 다시 열린다 —
        쌍둥이를 다시 세운 판(`API_TWIN_REBUILT`)만은 api 쌍둥이에 주는 grant 를 허락한다.
        (api 쌍둥이가 security definer 라 원본을 부르는 주체는 소유자다 — SECURITY DEFINER
         자체는 호출자의 EXECUTE 검사를 면제하지 않는다.)"""
        bad = grant_defects(read(path), path in API_TWIN_REBUILT)
        assert not bad, " / ".join(bad)

    @pytest.mark.parametrize("path", MIGRATIONS)
    def test_it_does_not_touch_the_api_twins(self, path):
        """⛔ api 쌍둥이는 본체를 통째로 넘기는 통과 함수라 본문이 안 바뀐다. 여기서
        다시 만들면 거기 붙은 grant 를 다시 적어야 하는 일이 딸려 온다.
        결과 칸이 바뀐 판(`API_TWIN_REBUILT`)만은 다시 세운다 — 그때는 쌍둥이가 정본과
        글자 그대로인지 본다(`create`/`create or replace` 차이만 접는다)."""
        bad = api_twin_defects(read(path), path in API_TWIN_REBUILT, read(SCHEMA))
        assert not bad, " / ".join(bad)


# ── 6. 가드 자신의 시험 — 죽은 줄을 **진짜로** 잡는가 ────────────────────────
#
# ⓘ 아래는 파일을 **안 건드린다** — 원문을 문자열로 읽어 한 군데를 망가뜨린 **사본**을
#   만들고 그 사본에 판정을 돌린다. 그래서 "복원"이 따로 필요 없다(디스크는 처음부터
#   그대로다). 시험이 중간에 죽어도 레포에 부서진 파일이 남지 않는다.


@pytest.mark.parametrize("path,fn", SITES, ids=SITE_IDS)
def test_the_guard_catches_a_removed_cast(path, fn):
    """⛔ **가드가 진짜 무는지**를 시험 안에서 확인한다.

    캐스트를 하나만 떼면 그곳만 조용히 느려진다 — 답은 같으므로 다른 어떤 시험도
    안 잡는다. 그래서 '하나만 뗀' 사본으로 실제 판정 경로를 태운다.
    """
    block = fn_block(read(path), fn)
    assert not cast_defects(block), "전제: 원문은 정상이어야 한다"
    tampered = block.replace(CAST, "pc.sigungu_code = pat.gu", 1)
    assert tampered != block, "전제: 사본이 실제로 달라야 한다"
    assert cast_defects(tampered), (
        "캐스트를 하나 뗐는데도 '정상'이라 합니다 — 이 파일이 아무것도 안 막고 있습니다")


@pytest.mark.parametrize("path,fn", SITES, ids=SITE_IDS)
def test_the_guard_catches_a_removed_nationwide_branch(path, fn):
    """전국 검색 가지를 지우는 반대 방향도 잡아야 한다 — 이쪽은 0건이 되는 쪽이다."""
    block = fn_block(read(path), fn)
    tampered = block.replace(GU_CLAUSE, CAST, 1)
    assert tampered != block, "전제: 사본이 실제로 달라야 한다"
    assert cast_defects(tampered), (
        "전국 검색 가지를 뗐는데도 '정상'이라 합니다")


# PNU 구 범위(2026-09-27a)의 돌연변이 — (원문 조각, 바꿀 글자, 무엇이 깨지나).
# 원문 조각은 `fn_block` 의 **날 글자**(줄바꿈·들여쓰기 그대로)에서 찾는다.
PNU_MUTANTS = (
    ("(pat.gu is null or (b.pnu", "((b.pnu",
     "PNU 전국 가지 제거 — 구를 안 고르면 이름 가지가 0건"),
    ("repeat('9',14)", "repeat('9',13)",
     "9 반복 14→13 — 구의 마지막 필지 몇 개가 조용히 빠진다"),
    ("b.pnu >= pat.gu::char(19)", "b.pnu >= pat.gu",
     "아래 경계의 ::char(19) 제거 — text 비교로 색인이 죽는다"),
    ("repeat('9',14))::char(19)", "repeat('9',14))",
     "위 경계의 ::char(19) 제거 — text 비교로 색인이 죽는다"),
)


@pytest.mark.parametrize("path,fn", SITES, ids=SITE_IDS)
@pytest.mark.parametrize("old,new,why", PNU_MUTANTS,
                         ids=["pnu_nationwide", "nines_13", "lower_cast", "upper_cast"])
def test_the_guard_catches_a_broken_pnu_range(path, fn, old, new, why):
    """⛔ PNU 범위 절이 망가져도 **에러가 안 난다** — 0건이 되거나 느려지기만 한다."""
    block = fn_block(read(path), fn)
    assert not cast_defects(block), "전제: 원문은 정상이어야 한다"
    assert block.count(old) == 1, "전제: 원문에 `{}` 가 한 번 있다".format(old)
    tampered = block.replace(old, new, 1)
    assert cast_defects(tampered), "{} — 그런데도 '정상'이라 합니다".format(why)


@pytest.mark.parametrize("path,fn", SITES, ids=SITE_IDS)
def test_the_placement_guard_catches_split_halves(path, fn):
    """개수는 그럴듯해도 전국 가지가 비교와 **다른 괄호**로 떨어지면 위치 판정이 물어야 한다."""
    block = fn_block(read(path), fn)
    assert not placement_defects(block), "전제: 원문은 정상이어야 한다"
    tampered = block.replace(
        GU_CLAUSE, "({} true) and ({})".format(NATIONWIDE, CAST), 1)
    assert tampered != block, "전제: 사본이 실제로 달라야 한다"
    assert placement_defects(tampered), "두 절반을 갈랐는데도 '정상'이라 합니다"


@pytest.mark.parametrize("path,fn", SITES, ids=SITE_IDS)
def test_the_placement_guard_catches_split_pnu_bounds(path, fn):
    """PNU 아래·위 경계를 다른 괄호로 떼어 내도 위치 판정이 물어야 한다."""
    code = flat(fn_block(read(path), fn))
    assert not placement_defects(code), "전제: 원문은 정상이어야 한다"
    joined = "({} (b.pnu >= pat.gu::char(19) and ".format(NATIONWIDE)
    assert code.count(joined) == 1, "전제: 두 경계가 한 괄호에 이어져 있다"
    tampered = code.replace(
        joined, "({} (b.pnu >= pat.gu::char(19))) and (".format(NATIONWIDE), 1)
    assert placement_defects(tampered), "PNU 경계를 갈랐는데도 '정상'이라 합니다"


def test_the_finder_skips_comments_and_api_twins(tmp_path):
    """⛔ 탐색기가 머리말 인용이나 api 쌍둥이를 집으면 엉뚱한 판을 대조하며 초록이 된다.

    가짜 판 셋: 옛 public 정의 · 새 public 정의(`create function`, `or replace` 없음) ·
    가장 새 파일은 **주석 인용과 api 쌍둥이뿐** → 둘째를 집어야 한다.
    """
    body = "returns int language sql as {d} select 1 {d};\n".format(d=DOLLAR)
    (tmp_path / "2026-01-01a_old.sql").write_text(
        "create or replace function search_scope(q text)\n" + body, encoding="utf-8")
    (tmp_path / "2026-02-02b_new.sql").write_text(
        "create function public.search_scope(q text)\n" + body, encoding="utf-8")
    (tmp_path / "2026-03-03c_api_only.sql").write_text(
        "-- 되돌리기:\n-- create or replace function search_scope(q text)\n"
        "create or replace function api.search_scope(q text)\n" + body,
        encoding="utf-8")
    got = latest_migration_defining("search_scope", mig_dir=str(tmp_path))
    assert os.path.basename(got) == "2026-02-02b_new.sql"


def test_statements_really_strips_comments():
    """⛔ **주석 제거기가 헛돌면 위 시험들이 조용히 가짜 초록이 된다** — 이 파일은 특히
    그렇다. 정본·마이그레이션의 ⛔ 주석에 `pat.gu is null or` 가 **글로** 적혀 있어서,
    안 걷으면 개수 세기가 전부 어긋난다."""
    text = read(PIN["search_scope"])
    line = "revoke all on function search_scope(text, text) from public, anon, authenticated;"
    assert line in flat(text), "전제: 원문에는 그 문장이 살아 있다"
    assert line not in flat(text.replace(line, "-- " + line)), (
        "주석으로 죽인 revoke 가 여전히 '있다'고 읽힙니다 — 주석 제거가 헛돕니다")


# ── 7. 쌍둥이를 다시 세운 판(2026-10-09a~)의 grant·쌍둥이 판정 — 양성 대조 ─────────

REBUILT = PIN["search_buildings"]
API_GRANT = ("grant execute on function api.search_buildings(text, int, text)  "
             "to anon, authenticated;")


def test_the_rebuilt_file_is_clean_as_written():
    """전제: 다시 세운 판 원문은 두 판정 모두 정상이다(아래 변조가 의미를 갖게)."""
    assert REBUILT in API_TWIN_REBUILT
    text = norm(read(REBUILT))
    assert not grant_defects(text, True)
    assert not api_twin_defects(text, True, read(SCHEMA))


@pytest.mark.parametrize("name,mutate", (
    # 흔한 꼴 — public 원본을 여는 grant 한 줄
    ("public_grant", lambda s: s.replace(
        "\ncommit;\n",
        "\ngrant execute on function search_buildings(text, int, text) to anon;\ncommit;\n", 1)),
    # 변형 꼴 — `public.` 으로 수식하고 대문자로
    ("public_grant_qualified", lambda s: s.replace(
        "\ncommit;\n",
        "\nGRANT EXECUTE ON FUNCTION public.search_buildings(text, int, text) TO anon;\n"
        "commit;\n", 1)),
    # 쌍둥이 권한을 다시 안 준다(drop 으로 사라진 채)
    ("api_grant_removed", lambda s: s.replace(API_GRANT, "", 1)),
    # anon 을 빼고 authenticated 에만
    ("api_grant_without_anon", lambda s: s.replace(
        API_GRANT, API_GRANT.replace("to anon, authenticated", "to authenticated"), 1)),
), ids=["public_grant", "public_grant_qualified", "api_grant_removed",
        "api_grant_without_anon"])
def test_the_grant_guard_bites(name, mutate):
    text = norm(read(REBUILT))
    broken = mutate(text)
    assert broken != text, "전제: 사본이 실제로 달라야 한다({})".format(name)
    assert grant_defects(broken, True), "{} — 그런데도 '정상'이라 합니다".format(name)


def test_a_commented_grant_is_not_a_grant():
    """반대 방향 — 주석으로 적은 public grant 는 grant 가 아니다."""
    text = norm(read(REBUILT)).replace(
        "\ncommit;\n",
        "\n-- grant execute on function search_buildings(text, int, text) to anon;\n"
        "commit;\n", 1)
    assert "-- grant execute on function search_buildings" in text
    assert not grant_defects(text, True)


@pytest.mark.parametrize("name,mutate", (
    ("search_path_removed", lambda s: s.replace(
        "security definer\nset search_path = ''\nas $$ select * from public.search_buildings",
        "security definer\nas $$ select * from public.search_buildings", 1)),
    ("unqualified_body", lambda s: s.replace(
        "select * from public.search_buildings(", "select * from search_buildings(", 1)),
    ("column_dropped", lambda s: s.replace(
        "  approve_date   date,\n  parking_cnt    integer\n)\nlanguage sql",
        "  approve_date   date\n)\nlanguage sql", 1)),
), ids=["search_path_removed", "unqualified_body", "column_dropped"])
def test_the_api_twin_guard_bites(name, mutate):
    """쌍둥이만 바꾼 사본(정본은 그대로) → 빨간불."""
    text = norm(read(REBUILT))
    broken = mutate(text)
    assert broken != text, "전제: 사본이 실제로 달라야 한다({})".format(name)
    assert api_twin_defects(broken, True, read(SCHEMA)), (
        "{} — 그런데도 '정상'이라 합니다".format(name))


def test_an_untouched_file_must_not_mention_api():
    """다시 세운 판이 아닌 파일에 api.* 정의가 끼면 옛 단언 그대로 빨갛다."""
    text = norm(read(PIN["search_scope"]))
    assert not api_twin_defects(text, False, read(SCHEMA)), "전제: 27a 는 api 를 안 건드린다"
    broken = text.replace("\ncommit;\n", "\n" + API_GRANT + "\ncommit;\n", 1)
    assert api_twin_defects(broken, False, read(SCHEMA))
    assert grant_defects(broken, False)
