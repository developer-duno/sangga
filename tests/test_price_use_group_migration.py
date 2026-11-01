# -*- coding: utf-8 -*-
"""구 표 둘은 상가 거래만 · 참고 시세 밴드와 게이트·성적표 줄을 내린다 — 마이그레이션 2026-10-18a 의 불변식
(결정 0040 D3·D8 + 결정 0041 E1 · 👤 2026-10-18).

무엇을 막나
-----------
  · 구 층대 단가(mv_sigungu_tx_stats)·동네 단가 흐름(mv_sigungu_tx_yearly)은 **상가(근생·판매) 거래만** 센다 —
    조건이 빠지면 제목만 「상가 거래 기준」인 채 업무·숙박이 섞인다(에러 0).
  · 결정 0041 로 지우는 일곱(api.list_price_bands · list_price_bands · price_floor_use_group · price_floor_band ·
    mv_tx_parcel_geog · api.list_price_gate · list_price_gate)과 표 price_gate_sigungu 는 **의존 역순**으로
    지운다 — 순서가 틀리면 적용이 "다른 객체가 기대고 있다"로 통째 되돌아간다.
  · 신선도 표(get_data_freshness)는 표를 지우기 **전에** 9번 줄(게이트 표의 적재일) 없이 다시 만든다 —
    순서가 틀리면 적용 뒤 신선도 표가 "그런 표 없음"으로 통째 사라진다(화면 맨 아래 · 에러 0 처럼 보인다).

여기서 보는 것
  1) 정본 정적 가드 — 남는 객체(묶음 함수 둘 · 요약표 둘) · 지운 객체 부재 · 신선도 9번 줄 부재(양성 대조 짝)
  2) 마이그레이션 — lock_timeout 이 begin 앞 · 한 덩어리 · notify 는 commit 뒤 · drop 목록과 순서 ·
     함수·요약표·comment 가 정본과 글자 일치 · 권한 · 머리말(되돌리기·의존 확인·정의 글자 없음)
  3) 로컬 PostgreSQL 이 있으면 옛 라이브 모양 위에 실제로 돌려 본다(없으면 건너뜀 — CI 는 1)~2)만)

ⓘ 도우미는 형제 시험(test_transaction_share_migration)에서 **복사**해 왔다(import 안 함 — 시험끼리 얽히면
  한쪽 고장이 다른 쪽을 가린다).
"""

import io
import glob
import os
import re
import shutil
import socket
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
MIGS = os.path.join(ROOT, "supabase", "migrations")
MIG = os.path.join(MIGS, "2026-10-18a_price_use_group.sql")
# 2026-10-29a(결정 0044) — 신선도 함수를 12번 줄(대전시 동네 폐업)을 더해 다시 만든 판. 정본과 그 함수 글자가 같아야 하는
# 쪽은 이제 이 파일이다(10-18a 는 원장 · 10-18a 판에 그 줄만 더했는지는 tests/test_daejeon_dong_closure_migration.py 가 본다).
# → 2026-10-31a(결정 0045)가 13·14·15 줄(서울 상권 4종)을 더해 다시 만들었다 — 이제 그 판과 대조한다(10-29a 도 원장 ·
#   10-29a 판에 그 줄만 더했는지는 tests/test_seoul_trdar_migration.py 가 본다).
# → 2026-11-01a(결정 0045 PR④)가 16번 줄(가게 이력)을 더해 다시 만들었다 — 이제 그 판과 대조한다(10-31a 도 원장 ·
#   그 줄만 더했는지는 tests/test_store_history_migration.py 가 본다 · 적용 날에 따라 이름이 바뀔 수 있어 이름 끝으로 찾는다).
# → 2026-11-01b(결정 0045 PR⑤)가 17번 줄(대전 상권 인구)을 더해 다시 만들었다 — 이제 그 판과 대조한다(11-01a 도 원장 ·
#   그 줄만 더했는지는 tests/test_sgis_district_pop_migration.py 가 본다).
FRESH_LATER = (sorted(glob.glob(os.path.join(MIGS, "*_sgis_district_pop.sql")))
                 or [os.path.join(MIGS, "(없음)_sgis_district_pop.sql")])[-1]
# 적용 **전** 라이브 모양을 흉내 낼 때 쓰는 원장들(글자 그대로 꺼낸다).
MIG_LADDER = os.path.join(MIGS, "2026-10-08a_transaction_share_flag.sql")     # list_price_bands 9칸 · 지분 제외 판
MIG_STAGE_B = os.path.join(MIGS, "2026-08-16a_stage_b_price_band.sql")        # price_floor_band · 게이트 표
MIG_GATE_READ = os.path.join(MIGS, "2026-09-05e_price_gate_read.sql")         # list_price_gate + api
MIG_FRESH_OLD = os.path.join(MIGS, "2026-10-15a_freshness_monthly_rules.sql")  # 9번 줄이 든 신선도 함수
MIG_FRESH_API = os.path.join(MIGS, "2026-09-05d_data_freshness.sql")           # api.get_data_freshness
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

GROUP_FNS = ("price_use_group_cd", "price_use_group_nm")
GROUP_FN_SIGS = {"price_use_group_cd": "price_use_group_cd(text)", "price_use_group_nm": "price_use_group_nm(text)"}
# 지우는 순서(결정 0041 §4-4) — get_data_freshness 재생성은 끝에서 둘째, 표는 맨 끝.
DROP_ORDER = (
    "drop function if exists api.list_price_bands(text);",
    "drop function if exists public.list_price_bands(text);",
    "drop function if exists price_floor_use_group(char(19), smallint);",
    "drop function if exists price_floor_band(smallint);",
    "drop materialized view if exists mv_tx_parcel_geog;",
    "drop function if exists api.list_price_gate();",
    "drop function if exists public.list_price_gate();",
    "create or replace function get_data_freshness()",
    "drop table if exists price_gate_sigungu;",
)
# 정본에서 사라져야 하는 정의 머리(지운 객체).
GONE = {
    "list_price_bands": r"(?im)^create\s+or\s+replace\s+function\s+(?:public\.)?list_price_bands\s*\(",
    "api.list_price_bands": r"(?im)^create\s+or\s+replace\s+function\s+api\.list_price_bands\s*\(",
    "price_floor_use_group": r"(?im)^create\s+or\s+replace\s+function\s+price_floor_use_group\s*\(",
    "price_floor_band": r"(?im)^create\s+or\s+replace\s+function\s+price_floor_band\s*\(",
    "mv_tx_parcel_geog": r"(?im)^create\s+materialized\s+view\s+(?:if\s+not\s+exists\s+)?mv_tx_parcel_geog\b",
    "list_price_gate": r"(?im)^create\s+or\s+replace\s+function\s+(?:public\.)?list_price_gate\s*\(",
    "api.list_price_gate": r"(?im)^create\s+or\s+replace\s+function\s+api\.list_price_gate\s*\(",
    "price_gate_sigungu": r"(?im)^create\s+table\s+(?:if\s+not\s+exists\s+)?price_gate_sigungu\b",
}
GATE_ROW_SRC = "참고 시세 성적표"

RE_LINE_COMMENT = re.compile(r"--[^\n]*")
RE_SHOP = re.compile(r"\bprice_use_group_nm\s*\(\s*t\.main_use\s*\)\s*=\s*'shop'", re.I)


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read().replace("\r\n", "\n")


def code(sql):
    """`--` 주석을 지운다 — 주석 속 글자(설명용)에 걸리면 가드가 거짓말을 한다."""
    return RE_LINE_COMMENT.sub("", sql)


def flat(sql):
    return re.sub(r"\s+", " ", code(sql)).strip()


def fn_block(name, sql):
    """`create or replace function <이름>(` 부터 `$$;` 까지(주석 포함 원문 — 머리 포함)."""
    m = re.search(r"(?im)^create\s+or\s+replace\s+function\s+{}\s*\(".format(re.escape(name)), sql)
    assert m, "함수 {} 를 못 찾았습니다".format(name)
    end = sql.index("$$;", sql.index("$$", m.end()) + 2)
    return sql[m.start():end + 3]


def stmt_at(pattern, sql):
    """줄머리 pattern 부터 작은따옴표 밖의 첫 `;` 까지(여러 줄 comment 문장도 통째로)."""
    m = re.search(pattern, sql, re.M)
    assert m, pattern
    i, quoted = m.start(), False
    while True:
        c = sql[i]
        if c == "'":
            quoted = not quoted
        elif c == ";" and not quoted:
            return sql[m.start():i + 1]
        i += 1


def mv_select(name, sql):
    """`create materialized view [if not exists] <name> as` 다음부터 `;` 까지(본문만)."""
    m = re.search(r"(?im)^create materialized view (?:if not exists )?{} as\n".format(name), sql)
    assert m, name
    return sql[m.end():sql.index(";", m.end()) + 1]


# ── 탐지 함수 (가드 본체와 양성 대조가 같은 함수를 지난다) ────────────────────


def mv_shop_problems(sql):
    """구 단위 두 표 — where 에 상가 조건. 동네 흐름은 filter 가 아니라 where 여야 한다(건수도 상가만)."""
    probs = []
    for mv in ("mv_sigungu_tx_stats", "mv_sigungu_tx_yearly"):
        body = flat(mv_select(mv, sql))
        if " where " not in body:
            probs.append("{} 에 where 가 없다".format(mv))
            continue
        where = body[body.index(" where "):]
        where = where[:where.index(" group by ")] if " group by " in where else where
        if not RE_SHOP.search(where):
            probs.append("{} 의 where 에 상가 조건이 없다".format(mv))
    return probs


def group_fn_problems(sql):
    """묶음 함수 둘 — 인라인되게: language sql · immutable · strict 아님 · search_path·definer 없음."""
    probs = []
    for name in GROUP_FNS:
        head = flat(fn_block(name, sql).split("$$")[0])
        if " language sql " not in " " + head + " ":
            probs.append("{} 가 language sql 이 아니다".format(name))
        if " immutable" not in head:
            probs.append("{} 가 immutable 이 아니다".format(name))
        for bad in ("strict", "returns null on null input", "security definer", "set search_path"):
            if bad in head:
                probs.append("{} 에 {} 가 있다 — 인라인이 막히거나 NULL 규칙이 바뀐다".format(name, bad))
    return probs


def gone_problems(sql):
    """지운 객체의 정의 머리가 남아 있나(주석은 걷고 본다 — 머리말·설명 글자에는 안 걸린다)."""
    src = code(sql)
    return [name for name, pat in GONE.items() if re.search(pat, src)]


def freshness_gate_row_problems(sql):
    """get_data_freshness 본문(주석 제거)에 9번 줄(게이트 표·성적표 줄)이 남았나.

    못 보는 것: 자료 이름을 문자열 잇기로 만드는 꼴(지금 정본에 없다) — 그래도 표 이름(price_gate_sigungu)을 따로 본다.
    """
    body = code(fn_block("get_data_freshness", sql))
    probs = []
    if GATE_ROW_SRC in body:
        probs.append("성적표 줄 이름이 남았다")
    if re.search(r"\bprice_gate_sigungu\b", body):
        probs.append("게이트 표를 읽는다")
    if re.search(r"\bselect\s+9\s*,", body):
        probs.append("9번 줄이 남았다")
    return probs


def freshness_ords(sql):
    """get_data_freshness 본문의 순서 칸(ord) 숫자 — 뒤 번호(10·11)는 그대로여야 한다."""
    body = code(fn_block("get_data_freshness", sql))
    return [int(x) for x in re.findall(r"\bselect\s+(\d+)\s*(?:as\s+ord\s*)?,", body)]


def drop_order_problems(sql):
    """drop 목록이 다 있고 의존 역순(DROP_ORDER)인가 — `cascade` 는 금지."""
    src = code(sql)
    probs = []
    pos = []
    for s in DROP_ORDER:
        i = src.find(s)
        if i < 0:
            probs.append("없다: {}".format(s))
        pos.append(i)
    if not probs and pos != sorted(pos):
        probs.append("지우는 순서가 어긋났다")
    if re.search(r"\bcascade\b", src, re.I):
        probs.append("cascade 가 있다")
    return probs


# ── 1. 정본 정적 가드 ────────────────────────────────────────────────────────


def test_정본_구_표_둘은_상가만():
    assert mv_shop_problems(read(SCHEMA)) == []


def test_정본_묶음_함수는_인라인되게():
    assert group_fn_problems(read(SCHEMA)) == []


def test_정본_권한_묶음_함수는_닫혀_있다():
    src = flat(read(SCHEMA))
    for sig in GROUP_FN_SIGS.values():
        assert "revoke all on function {} from public, anon, authenticated;".format(sig) in src
        name = sig.split("(")[0]
        assert not re.search(r"grant [^;]*on function (public\.)?{}\(".format(name), src)


def test_정본에서_지운_객체가_없다():
    assert gone_problems(read(SCHEMA)) == []


def test_정본_신선도_9번_줄이_없고_뒤_번호는_그대로다():
    src = read(SCHEMA)
    assert freshness_gate_row_problems(src) == []
    # 2026-10-29a(결정 0044) — 대전시 동네 폐업이 12번으로 붙었다(9번은 여전히 비어 있다).
    # 2026-10-31a(결정 0045) — 서울 상권 4종 세 줄이 13·14·15 로 붙었다.
    # 2026-11-01a(결정 0045 PR④) — 가게 이력 줄이 16 으로 붙었다.
    # 2026-11-01b(결정 0045 PR⑤) — 대전 상권 인구 줄이 17 로 붙었다.
    assert freshness_ords(src) == [1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17]


def test_정본_권한_목록에_지운_api_가_없다():
    src = flat(read(SCHEMA))
    for name in ("api.list_price_bands", "api.list_price_gate"):
        assert name + "(" not in src


# ── 1-1. 양성 대조 — 하나만 빠진·되살린 변형도 잡는다 ─────────────────────────


@pytest.mark.parametrize("mv", ["mv_sigungu_tx_stats", "mv_sigungu_tx_yearly"])
def test_돌연변이_구_표에서_상가_조건을_빼면_잡힌다(mv):
    src = read(SCHEMA)
    block = mv_select(mv, src)
    bad_block = block.replace("\n  and price_use_group_nm(t.main_use) = 'shop'", "", 1)
    assert bad_block != block
    assert mv_shop_problems(src.replace(block, bad_block, 1)) == [
        "{} 의 where 에 상가 조건이 없다".format(mv)]


def test_돌연변이_동네_흐름을_filter_로만_걸면_잡힌다():
    """건수(n_all)까지 상가만이어야 한다(D8) — filter 로 옮기면 where 에 없어 빨강."""
    src = read(SCHEMA)
    block = mv_select("mv_sigungu_tx_yearly", src)
    bad_block = block.replace("\n  and price_use_group_nm(t.main_use) = 'shop'", "", 1).replace(
        "count(*)::int ", "count(*) filter (where price_use_group_nm(t.main_use) = 'shop')::int ", 1)
    assert mv_shop_problems(src.replace(block, bad_block, 1)) == [
        "mv_sigungu_tx_yearly 의 where 에 상가 조건이 없다"]


@pytest.mark.parametrize("bad", ["security definer", "set search_path = public", "strict"])
def test_돌연변이_묶음_함수에_인라인_막는_머리를_붙이면_잡힌다(bad):
    src = read(SCHEMA)
    blk = fn_block("price_use_group_nm", src)
    tampered = blk.replace("immutable\n", "immutable\n{}\n".format(bad), 1)
    assert tampered != blk
    assert group_fn_problems(src.replace(blk, tampered, 1))


def test_돌연변이_9번_줄을_되살리면_잡힌다():
    """흔한 꼴(옛 줄 글자 그대로)과 변형 꼴(이름만 바꾸고 표는 그대로 읽음) 둘 다."""
    src = read(SCHEMA)
    body = fn_block("get_data_freshness", src)
    anchor = "    union all\n    -- ⓘ 9번(옛 성적표 줄)"
    assert anchor in body
    old_row = ("    union all\n    select 9, '참고 시세 성적표', '적재일',\n"
               "           (select (max(t.loaded_at) at time zone 'Asia/Seoul')::date::text\n"
               "              from price_gate_sigungu t),\n           'none',\n           '재생성 때 (결재 사항)'\n")
    bad = src.replace(body, body.replace(anchor, old_row + anchor, 1), 1)
    assert freshness_gate_row_problems(bad) == ["성적표 줄 이름이 남았다", "게이트 표를 읽는다", "9번 줄이 남았다"]
    alt = old_row.replace("select 9, '참고 시세 성적표'", "select 12, '통과 구 판정'")
    bad2 = src.replace(body, body.replace(anchor, alt + anchor, 1), 1)
    assert freshness_gate_row_problems(bad2) == ["게이트 표를 읽는다"]
    # 주석에만 남은 글자는 안 잡는다(주석을 걷고 본다).
    assert freshness_gate_row_problems(src.replace(body, body.replace(anchor, anchor + " 참고 시세 성적표", 1), 1)) == []


def test_돌연변이_지운_객체를_되살리면_잡힌다():
    src = read(SCHEMA)
    revived = src + ("\ncreate or replace function price_floor_band(p_floor smallint)\nreturns text\n"
                     "language sql\nimmutable\nas $$ select null::text $$;\n"
                     "create materialized view if not exists mv_tx_parcel_geog as select 1;\n")
    assert gone_problems(revived) == ["price_floor_band", "mv_tx_parcel_geog"]
    # 주석 속 글자는 안 잡는다.
    assert gone_problems(src + "\n-- create table if not exists price_gate_sigungu (x int);\n") == []


# ── 2. 마이그레이션 ──────────────────────────────────────────────────────────


def _at(pattern, sql):
    m = re.search(pattern, sql, re.M)
    assert m, pattern
    return m.start()


def test_마이그_잠금_시간이_begin_앞이고_한_덩어리다():
    src = code(read(MIG))
    lt = _at(r"^set lock_timeout = '2s';", src)
    b = _at(r"^begin;", src)
    c = _at(r"^commit;", src)
    n = _at(r"^notify pgrst, 'reload schema';", src)
    assert lt < b < c < n
    assert len(re.findall(r"(?m)^begin;", src)) == 1 and len(re.findall(r"(?m)^commit;", src)) == 1
    first_ddl = _at(r"^(alter|drop|create|comment|grant|revoke|analyze) ", src)
    assert b < first_ddl
    assert "concurrently" not in src[b:c]
    last_ddl = max(m.start() for m in re.finditer(
        r"(?m)^(alter|drop|create|comment|grant|revoke|analyze) ", src))
    assert last_ddl < c


def test_마이그_지우기는_의존_역순이고_cascade_가_없다():
    assert drop_order_problems(read(MIG)) == []


def test_돌연변이_지우는_순서를_바꾸면_잡힌다():
    """표를 신선도 함수보다 먼저 지우는 변형 · 이웃 표를 사다리보다 먼저 지우는 변형 · cascade."""
    mig = read(MIG)
    table = "drop table if exists price_gate_sigungu;\n"
    early = mig.replace(table, "", 1).replace("drop function if exists api.list_price_bands(text);\n",
                                              table + "drop function if exists api.list_price_bands(text);\n", 1)
    assert drop_order_problems(early) == ["지우는 순서가 어긋났다"]
    geog = "drop materialized view if exists mv_tx_parcel_geog;\n"
    early2 = mig.replace(geog, "", 1).replace("drop function if exists api.list_price_bands(text);\n",
                                              geog + "drop function if exists api.list_price_bands(text);\n", 1)
    assert drop_order_problems(early2) == ["지우는 순서가 어긋났다"]
    assert "cascade 가 있다" in drop_order_problems(mig.replace(table, "drop table if exists price_gate_sigungu cascade;\n", 1))
    assert drop_order_problems(mig.replace(geog, "", 1)) == ["없다: " + geog.strip()]


def test_마이그_묶음_함수는_요약표보다_먼저_만든다():
    """요약표가 price_use_group_nm 을 부른다 — 함수가 없으면 create materialized view 가 실패한다."""
    src = code(read(MIG))
    for fn in GROUP_FNS:
        assert src.index("create or replace function {}(".format(fn)) < src.index(
            "create materialized view mv_sigungu_tx_stats as")


@pytest.mark.parametrize("name", list(GROUP_FNS) + ["get_data_freshness", "api.get_data_freshness"])
def test_마이그_함수가_정본과_글자_일치(name):
    """머리(security definer·search_path·stable)까지 — create or replace 는 머리를 덮어쓴다.

    ⓘ get_data_freshness 는 2026-10-29a(결정 0044) → 2026-10-31a(결정 0045)가 다시 만들어 마지막 판(FRESH_LATER)과
      대조한다(10-18a·10-29a 는 원장).
    """
    src = FRESH_LATER if name == "get_data_freshness" else MIG
    assert fn_block(name, read(src)) == fn_block(name, read(SCHEMA))


@pytest.mark.parametrize("pattern", [
    r"^comment on function price_use_group_cd\(text\) is",
    r"^comment on function price_use_group_nm\(text\) is",
    r"^comment on function get_data_freshness\(\) is",
    r"^comment on function get_sigungu_tx_stats\(text\) is",
    r"^comment on function get_sigungu_tx_yearly\(text\) is",
    r"^comment on materialized view mv_sigungu_tx_stats is",
    r"^comment on materialized view mv_sigungu_tx_yearly is",
    r"^create unique index if not exists idx_msts_key",
    r"^create unique index if not exists idx_msty_key",
])
def test_마이그_comment_와_색인이_정본과_글자_일치(pattern):
    # get_data_freshness comment 는 2026-10-29a(결정 0044) → 2026-10-31a(결정 0045)가 다시 썼다 — 마지막 판(FRESH_LATER)과
    # 대조한다(10-18a·10-29a 는 원장).
    src = FRESH_LATER if "get_data_freshness" in pattern else MIG
    assert stmt_at(pattern, read(src)) == stmt_at(pattern, read(SCHEMA))


@pytest.mark.parametrize("mv", ["mv_sigungu_tx_stats", "mv_sigungu_tx_yearly"])
def test_마이그_물질화뷰는_떨어뜨린_뒤_정본과_같은_본문으로_굽는다(mv):
    mig = read(MIG)
    src = code(mig)
    drop = src.index("drop materialized view if exists {};".format(mv))
    make = src.index("create materialized view {} as".format(mv))
    assert drop < make
    assert "create materialized view if not exists {}".format(mv) not in src, (
        "다시 굽는 판에서 if not exists 는 아무 일도 안 한다")
    assert mv_select(mv, mig) == mv_select(mv, read(SCHEMA))
    after = flat(src[make:])
    assert "analyze {};".format(mv) in after
    assert "revoke all on {} from public, anon, authenticated;".format(mv) in after


@pytest.mark.parametrize("fn", ["get_sigungu_tx_stats", "get_sigungu_tx_yearly"])
def test_구_표_함수_설명에_상가_거래만이_있다(fn):
    """보완 1차 B5 — 구 표 둘을 읽는 함수의 설명에도 「상가(근생·판매) 거래만」(정본·마이그 같은 글 — 위 글자 대조)."""
    for path in (SCHEMA, MIG):
        stmt = stmt_at(r"^comment on function {}\(text\) is".format(fn), read(path))
        assert "상가(근생·판매) 거래만 — 결정 0040 D3·D8" in stmt, (fn, path)


def test_마이그_권한_신선도_api_만_열고_나머지는_닫는다():
    src = flat(read(MIG))
    for sig in GROUP_FN_SIGS.values():
        assert "revoke all on function {} from public, anon, authenticated;".format(sig) in src
    assert "revoke all on function get_data_freshness() from public, anon, authenticated;" in src
    rv = src.index("revoke all on function api.get_data_freshness() from public, anon, authenticated;")
    gr = src.index("grant execute on function api.get_data_freshness() to anon, authenticated;")
    assert rv < gr
    grants = re.findall(r"grant execute on function ([\w.]+)\([^)]*\) to ([^;]+);", src)
    assert grants == [("api.get_data_freshness", "anon, authenticated")]


def test_마이그_정적_가드도_통과한다():
    mig = read(MIG)
    assert mv_shop_problems(mig) == []
    assert group_fn_problems(mig) == []
    assert freshness_gate_row_problems(mig) == []
    assert freshness_ords(mig) == [1, 2, 3, 4, 5, 6, 7, 8, 10, 11]


def test_마이그_머리말에_되돌리기_절과_의존_확인이_있다():
    raw = read(MIG)
    head = raw[:raw.index("\nset lock_timeout")]
    assert "② 되돌리기" in head
    assert "pg_depend" in head
    assert rollback_problems(head) == []


def rollback_problems(head):
    """머리말 「② 되돌리기」 절 — 목표 = 700a254(운영 10-08a 판 · 보완 1차 B4).

    ① 글자 그대로 옮겨 올 원장 다섯 + 700a254 가 다 적혀 있다 ② squash 뒤 이력에 없는 f75cbc5 를 가리키지 않는다
    ③ 요약표 둘(용도 불문 판)을 다시 굽는 줄이 묶음 함수 drop **앞**이다(뒤면 의존에 막힌다) ④ cascade 0
    ⑤ (9) 구 표 함수 둘의 comment 를 700a254 판 글자로 되돌리는 줄이 있다(보완 2차 C2 — ⑦ 이 덧붙인 구절을 걷는다).
    못 보는 것: 적힌 행 번호가 그 파일의 실제 블록과 맞는지(사람이 본다).
    """
    sec = head[head.index("② 되돌리기"):] if "② 되돌리기" in head else ""
    probs = []
    for f in ("2026-08-16a", "2026-09-27c", "2026-10-08a", "2026-09-05e", "2026-10-15a", "700a254"):
        if f not in sec:
            probs.append("없다: " + f)
    if "f75cbc5" in sec:
        probs.append("f75cbc5 를 가리킨다")
    mv = sec.find("요약표 둘(용도 불문")
    drop = sec.find("drop function if exists price_use_group_nm(text);")
    if mv < 0 or drop < 0 or not mv < drop:
        probs.append("요약표 재생성이 묶음 함수 drop 앞이 아니다")
    if "cascade;" in sec:
        probs.append("cascade")
    c9 = sec.find("-- (9)")
    need9 = ("2306-2311", "2403-2408", "get_sigungu_tx_stats", "get_sigungu_tx_yearly", "comment")
    if c9 < 0 or not all(s in sec[c9:] for s in need9):
        probs.append("구 표 함수 설명 되돌리기(9)가 없다")
    return probs


def test_돌연변이_되돌리기_절이_틀리면_잡힌다():
    raw = read(MIG)
    head = raw[:raw.index("\nset lock_timeout")]
    assert rollback_problems(head.replace("700a254", "f75cbc5")) == ["없다: 700a254", "f75cbc5 를 가리킨다"]
    i = head.index("--   -- (8)")
    j = head.index("--   commit;", i)
    moved = head[:head.index("--   -- (1)")] + head[i:j] + head[head.index("--   -- (1)"):i] + head[j:]
    assert "요약표 재생성이 묶음 함수 drop 앞이 아니다" in rollback_problems(moved)
    # (9) 를 빼면 잡힌다(보완 2차 C2).
    k = head.index("--   -- (9)")
    no9 = head[:k] + head[head.index("--   commit;", k):]
    assert rollback_problems(no9) == ["구 표 함수 설명 되돌리기(9)가 없다"]


def test_마이그_머리말에는_함수_정의_글자가_없다():
    """함수 드리프트 시험의 파서는 주석을 안 걷는다 — 머리말에 정의 글자가 있으면 다음 본문을 삼킨다."""
    raw = read(MIG)
    head = raw[:raw.index("\nset lock_timeout")]
    assert not re.search(r"create\s+(or\s+replace\s+)?function\s+[\w.]+\s*\(", head, re.I)


def test_check_의_용도_이름_점검은_ASCII_SQL_이고_7종을_다_싣는다():
    """query_one 은 psql -c 라 한글이 깨진다 — 16진수로 넣었나 · 이름이 7종 그대로인가."""
    sql = post_load.build_tx_main_use_unknown_sql()
    assert sql.isascii()
    hexes = re.findall(r"decode\('([0-9a-f]+)', 'hex'\)", sql)
    assert [bytes.fromhex(h).decode("utf-8") for h in hexes] == [
        "제1종근린생활", "제2종근린생활", "판매", "업무", "숙박", "교육연구", "기타"]
    assert "nullif(main_use, '') is null or main_use not in (" in sql
    with pytest.raises(ValueError):
        post_load.judge_tx_main_use_unknown("ERROR: x")
    assert post_load.judge_tx_main_use_unknown(" 3\n") == 3


def test_check_의_용도_이름_점검은_종료_코드에_안_넣는다():
    """[주의]까지만 — main() 의 return 식에 그 결과가 들어가면 안 된다."""
    src = read(os.path.join(SCRIPTS_DIR, "post_load.py"))
    assert "\n        report_tx_main_use_unknown()\n" in src
    ret = src[src.index("        return 1 if (stale or map_stale"):]
    ret = ret[:ret.index(" else 0")]
    assert "main_use" not in ret


def test_post_load_허용_목록과_요약표_목록에서_지운_것이_빠졌다():
    """공개 호출 허용 목록 −2 · REFRESH_MVS −1 · 이웃 표 신선도 점검 함수 삭제(결정 0041 §4-4)."""
    allow = post_load.ANON_CALLABLE_ALLOWLIST
    assert "api.list_price_bands" not in allow and "api.list_price_gate" not in allow
    assert "api.get_data_freshness" in allow
    for fn in GROUP_FNS:
        assert not any(fn in name for name in allow)
    assert "mv_tx_parcel_geog" not in post_load.REFRESH_MVS
    assert "mv_sigungu_tx_stats" in post_load.REFRESH_MVS
    assert "mv_sigungu_tx_yearly" in post_load.REFRESH_MVS
    assert not hasattr(post_load, "report_tx_geog_freshness")
    # 7종 밖 용도 이름 점검은 남는다(구 표 둘의 상가 묶음표가 쓴다).
    assert hasattr(post_load, "report_tx_main_use_unknown")


# ── 3. 로컬 PostgreSQL 로 실제 실행 (없으면 건너뜀 — 형제 test_transaction_share_migration 과 같은 방식) ──

# 옛 라이브(2026-10-18a 적용 전) 흉내 — PostGIS 없음(geography 는 text 도메인 · 좌표는 비워 반경 단계는 건너뛴다).
SHIM = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role; end if;
end $$;
create schema api;
create domain geography as text;
create table parcel (pnu char(19) primary key, geom text, land_price_year smallint);
create table building_floor (pnu char(19), floor_no smallint);
create table mv_open_sigungu (sigungu_code char(5), sigungu_nm text);
create materialized view mv_tx_parcel_geog as select pnu, geom::geography as geog from parcel;
create table snapshot_release (published_ym text);
create table ledger_release (id int primary key default 1, release_ym char(6), loaded_at timestamptz default now());
create table district (computed_at timestamptz);
create table lh_notice (collected_at timestamptz);
create table arch_permit (loaded_ym text);
create table nts_base_price (notice_date date);
create table rent_stat (quarter char(6));
create table district_openclose (quarter text);
"""

# 옛 api.list_price_bands(9칸) — 2026-09-05a 판의 꼴(정본에서 지워 원장 글자 대신 여기 적는다).
OLD_API_BANDS = """
create or replace function api.list_price_bands(p_pnu text)
returns table (floor_no smallint, status text, stage text, n int, p25 numeric, median numeric,
               p75 numeric, median_area_m2 numeric, window_from text)
language sql stable security definer set search_path = ''
as $$ select * from public.list_price_bands(p_pnu) $$;
grant execute on function api.list_price_bands(text) to anon, authenticated;
"""


def _old_state(schema_sql):
    """적용 **전** 라이브와 같은 모양 — 지분 칸 있음 · 묶음 함수 없음 · 9칸 참고 시세 · 게이트 표 · 이웃 표 ·
    성적표 함수 · 9번 줄이 든 신선도 함수 · 상가 조건 없는 요약표."""
    old = [stmt_at(r"^create table if not exists transaction \(", schema_sql),
           "alter table transaction add column if not exists is_share boolean not null default false;"]
    stage_b = read(MIG_STAGE_B)
    old.append(stmt_at(r"^create table if not exists price_gate_sigungu \(", stage_b))
    old.append("alter table price_gate_sigungu add column if not exists loaded_at timestamptz;")
    for mv in ("mv_sigungu_tx_stats", "mv_sigungu_tx_yearly"):
        body = mv_select(mv, schema_sql).replace("\n  and price_use_group_nm(t.main_use) = 'shop'", "")
        old.append("create materialized view {} as\n{}".format(mv, body))
    old.append(stmt_at(r"^create unique index if not exists idx_msts_key", schema_sql))
    old.append(stmt_at(r"^create unique index if not exists idx_msty_key", schema_sql))
    old.append(fn_block("price_floor_band", stage_b))
    old.append(fn_block("get_sigungu_tx_stats", schema_sql))
    old.append(fn_block("get_sigungu_tx_yearly", schema_sql))
    old.append(fn_block("list_price_bands", read(MIG_LADDER)))
    old.append(OLD_API_BANDS)
    gate = read(MIG_GATE_READ)
    old.append(fn_block("list_price_gate", gate))
    old.append(fn_block("api.list_price_gate", gate))
    old.append(fn_block("get_data_freshness", read(MIG_FRESH_OLD)))
    old.append(fn_block("api.get_data_freshness", read(MIG_FRESH_API)))
    joined = "\n".join(old)
    assert "price_use_group" not in joined and "use_group" not in joined
    assert GATE_ROW_SRC in joined   # 옛 신선도 함수에 9번 줄이 든 판인지
    return joined


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    psycopg2 = pytest.importorskip("psycopg2")
    initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
    if not initdb or not pg_ctl:
        pytest.skip("로컬 PostgreSQL(initdb·pg_ctl)이 없다 — CI 는 글자 가드(1~2)만 본다")
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
    try:
        conn = None
        for _ in range(30):
            try:
                conn = psycopg2.connect(host="127.0.0.1", port=port, user="postgres", dbname="postgres")
                break
            except psycopg2.OperationalError:
                time.sleep(0.5)
        assert conn is not None, "로컬 PostgreSQL 에 못 붙었다"
        conn.autocommit = True
        yield conn
        conn.close()
    finally:
        subprocess.run([pg_ctl, "-D", data, "-m", "fast", "-w", "stop"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)


PNU_A = "1168010100100010000"   # 강남 역삼동 1번지
PNU_B = "1168010100100020000"   # 같은 법정동 2번지


@pytest.fixture(scope="module")
def cur(pg):
    c = pg.cursor()
    c.execute(SHIM)
    c.execute(_old_state(read(SCHEMA)))
    ym = "to_char(now(), 'YYYYMM')"
    # 거래: 2층 상가 3건(100·200·300만) + 업무 1건 · 3층 업무 2건 + 판매 1건 · 4·6층 판매 1건씩 · 지분 판매 1건(2층)
    #       · PNU_B 7층 2종근생 1건 · 숙박·교육연구 각 1건(구 표에서 빠진다)
    c.execute("""
      insert into transaction (tx_id, pnu, sigungu_code, floor_no, bld_area_m2, price_won, contract_ym, tx_type, main_use)
      values ('s1', '{a}', '11680', 2, 10, 10000000, {ym}, '집합', '제2종근린생활'),
             ('s2', '{a}', '11680', 2, 10, 20000000, {ym}, '집합', '제1종근린생활'),
             ('s3', '{a}', '11680', 2, 10, 30000000, {ym}, '집합', '판매'),
             ('o1', '{a}', '11680', 2, 10, 100000000, {ym}, '집합', '업무'),
             ('o2', '{a}', '11680', 3, 10, 80000000, {ym}, '집합', '업무'),
             ('o3', '{a}', '11680', 3, 10, 90000000, {ym}, '집합', '업무'),
             ('s4', '{a}', '11680', 3, 10, 5000000, {ym}, '집합', '판매'),
             ('r1', '{a}', '11680', 4, 10, 10000000, {ym}, '집합', '판매'),
             ('u1', '{a}', '11680', 6, 10, 10000000, {ym}, '집합', '판매'),
             ('sh', '{a}', '11680', 2, 10, 1000000, {ym}, '집합', '판매'),
             ('b7', '{b}', '11680', 7, 10, 40000000, {ym}, '집합', '제2종근린생활'),
             ('l1', null,  '11680', 3, 10, 70000000, {ym}, '집합', '숙박'),
             ('e1', null,  '11680', 3, 10, 60000000, {ym}, '집합', '교육연구');
      update transaction set is_share = true where tx_id = 'sh';
      insert into parcel (pnu, geom, land_price_year) values ('{a}', null, 2026), ('{b}', null, 2026);
      insert into building_floor values ('{a}', 2);
      insert into price_gate_sigungu (sigungu_code, gate_pass, loaded_at) values ('11680', true, now());
      insert into mv_open_sigungu values ('11680', '강남구');
      insert into snapshot_release values ('202606');
      insert into ledger_release (release_ym) values ('202608');
      refresh materialized view mv_sigungu_tx_stats;
      refresh materialized view mv_sigungu_tx_yearly;
      refresh materialized view mv_tx_parcel_geog;
    """.format(a=PNU_A, b=PNU_B, ym=ym))
    c.execute("select sum(n_all) from mv_sigungu_tx_yearly")
    before = c.fetchone()[0]
    c.execute("select count(*) from get_data_freshness()")
    fresh_before = c.fetchone()[0]
    c.execute(read(MIG))   # 마이그레이션 원문 그대로(set · begin … commit · notify)
    return c, before, fresh_before


CD_CASES = [("03", "shop"), ("04", "shop"), ("07", "shop"), ("Z3", "shop"), ("Z6", "shop"),
            ("03001", "shop"), ("14", "office"), ("14999", "office"), ("15", "lodging"),
            ("01", "resid"), ("02", "resid"), (None, None), ("", None),
            ("10", "other"), ("Z8", "other"), ("05", "other")]
NM_CASES = [("제1종근린생활", "shop"), ("제2종근린생활", "shop"), ("판매", "shop"),
            ("업무", "office"), ("숙박", "lodging"), (None, None), ("", None),
            ("교육연구", "other"), ("기타", "other"), ("사무소", "other")]


class TestRealRun:
    @pytest.mark.parametrize("cd,want", CD_CASES)
    def test_코드_묶음(self, cur, cd, want):
        c = cur[0]
        c.execute("select price_use_group_cd(%s)", (cd,))
        assert c.fetchone()[0] == want

    @pytest.mark.parametrize("nm,want", NM_CASES)
    def test_이름_묶음(self, cur, nm, want):
        c = cur[0]
        c.execute("select price_use_group_nm(%s)", (nm,))
        assert c.fetchone()[0] == want

    def test_묶음_함수는_인라인된다(self, cur):
        """요약표 스캔에서 함수 이름이 계획에 안 남아야 한다(인라인 = case 식으로 펼쳐짐)."""
        c = cur[0]
        c.execute("explain (verbose) select count(*) from transaction t "
                  "where price_use_group_nm(t.main_use) = 'shop'")
        plan = "\n".join(r[0] for r in c.fetchall())
        assert "price_use_group_nm" not in plan

    def test_지운_객체가_다_없다(self, cur):
        c = cur[0]
        c.execute("select to_regprocedure('public.list_price_bands(text)'), to_regprocedure('api.list_price_bands(text)'),"
                  "       to_regprocedure('price_floor_use_group(char(19), smallint)'),"
                  "       to_regprocedure('price_floor_band(smallint)'),"
                  "       to_regclass('mv_tx_parcel_geog'),"
                  "       to_regprocedure('public.list_price_gate()'), to_regprocedure('api.list_price_gate()'),"
                  "       to_regclass('price_gate_sigungu')")
        assert c.fetchone() == (None,) * 8

    def test_신선도_표는_열_줄이고_성적표_줄이_없다(self, cur):
        c, _, fresh_before = cur
        assert fresh_before == 11                          # 적용 전 = 열한 줄(9번 = 성적표)
        c.execute("select src from api.get_data_freshness()")
        srcs = [r[0] for r in c.fetchall()]
        assert len(srcs) == 10
        assert GATE_ROW_SRC not in srcs
        # 순서는 그대로 — 9번만 빠지고 10·11번(필지 · 서울 개업·폐업)이 끝에 그대로.
        assert srcs[-2:] == ["필지 (토지 특성)", "상권 개업·폐업 (서울시)"]
        assert srcs[0] == "점포·업종 (상권정보)"

    def test_구_층대_단가는_상가만(self, cur):
        c = cur[0]
        c.execute("refresh materialized view concurrently mv_sigungu_tx_stats")
        c.execute("select floor_band, n from get_sigungu_tx_stats('11680') where n > 0 order by floor_band")
        # 2층 상가 3건(지분 제외) · 3층이상: 3층 판매 1 + 4·6층 판매 2 + 7층 2종근생 1 = 4 (업무·숙박·교육연구 빠짐)
        assert c.fetchall() == [("2층", 3), ("3층이상", 4)]

    def test_동네_흐름은_건수까지_상가만(self, cur):
        c, before, _ = cur
        c.execute("refresh materialized view concurrently mv_sigungu_tx_yearly")
        c.execute("select sum(n_all), sum(n) from mv_sigungu_tx_yearly")
        n_all, n = c.fetchone()
        assert before == 13            # 적용 전 = 집합 전부(지분 포함)
        assert n_all == 8              # 상가 거래만(지분 상가 1건은 건수엔 센다): s1·s2·s3·s4·r1·u1·sh·b7
        assert n == 7                  # 단가 근거는 지분 빼고

    def test_check_용도_이름_점검이_실제로_센다(self, cur):
        """7종이면 0 · 모르는 글자·빈 값을 넣으면 그만큼(양성 대조)."""
        c = cur[0]
        c.execute(post_load.build_tx_main_use_unknown_sql())
        assert c.fetchone()[0] == 0
        c.execute("insert into transaction (tx_id, sigungu_code, price_won, contract_ym, tx_type, main_use) "
                  "values ('x1', '11680', 1, '200001', '집합', '근린생활'), ('x2', '11680', 1, '200001', '집합', ''),"
                  "       ('x3', '11680', 1, '200001', '집합', null)")
        try:
            c.execute(post_load.build_tx_main_use_unknown_sql())
            assert c.fetchone()[0] == 3
        finally:
            c.execute("delete from transaction where tx_id in ('x1', 'x2', 'x3')")

    def test_권한(self, cur):
        c = cur[0]
        c.execute("select has_function_privilege('anon', 'api.get_data_freshness()', 'execute'),"
                  "       has_function_privilege('anon', 'public.get_data_freshness()', 'execute'),"
                  "       has_function_privilege('anon', 'price_use_group_cd(text)', 'execute'),"
                  "       has_function_privilege('anon', 'price_use_group_nm(text)', 'execute'),"
                  "       has_table_privilege('anon', 'mv_sigungu_tx_stats', 'select'),"
                  "       has_table_privilege('anon', 'mv_sigungu_tx_yearly', 'select')")
        assert c.fetchone() == (True, False, False, False, False, False)

    def test_두_번_돌려도_된다(self, cur):
        """함수는 create or replace · 지우기는 if exists · 요약표는 drop if exists 뒤 다시 굽는다."""
        c = cur[0]
        c.execute(read(MIG))
        c.execute("select count(*) from api.get_data_freshness()")
        assert c.fetchone()[0] == 10
        c.execute("select count(*) from get_sigungu_tx_stats('11680')")
        assert c.fetchone()[0] == 5
