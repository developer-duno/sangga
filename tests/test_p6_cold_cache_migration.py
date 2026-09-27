# -*- coding: utf-8 -*-
"""첫 방문(찬 캐시) 속도 — 층별 화면 함수 두 곳의 불변식 (마이그레이션 2026-09-27c · 로드맵 속도 P6).

무엇을 막나
-----------
① `list_parcel_transactions(pnu text)` 가 `transaction.pnu`(char(19))를 text 와 견주면
   PostgreSQL 이 **칸 쪽**을 text 로 올려 `idx_tx_pnu` 를 못 탄다. 라이브 실측(2026-09-27):
   거래 0건 필지가 idx_tx_pnu10_ym 으로 2024년 이후 거래 2.8만 행을 훑어 1,876쪽 ↔
   `::char(19)` 로 견주면 2쪽. 형제 함수들은 이미 이 처방(2026-08-16b)을 받았고 이것만 남았었다.
② `list_price_bands` 의 반경 100m·500m 이웃을 **parcel(전국 111만 행)** 에서 찾으면 찬 캐시
   첫 호출마다 GiST·힙 수백 쪽을 창고에서 꺼낸다. 이웃 배열은 L4·L5 의 `t.pnu = any(…)` 에만
   쓰이므로 거래 있는 필지만 모은 요약표 `mv_tx_parcel_geog`(4,384곳)에서 찾아도 결과가 같다
   (라이브 md5 대조 450곳 diff 0 · 이웃 문장 194~1,996쪽 → 16~27쪽).

⛔ 둘 다 **에러가 안 난다** — 되돌아가도 답은 같고 느리기만 하다. 사람 눈으로는 영영 안 잡힌다.

여기서 보는 것 (DB 없이 SQL 글자만 — CI 에는 DB 가 없다)
  1) 정본 list_parcel_transactions 본문에 `t.pnu = list_parcel_transactions.pnu::char(19)` 가
     있고, 캐스트 없는 옛 모양은 없다.
  2) 정본 list_price_bands 의 이웃 문장(`into v_near100, v_near500 from …`)이 새 표를 본다.
  3) 새 표의 정의가 "좌표 있음 + 거래가 한 건이라도 있음" 그대로다(거래 조건을 좁히면
     L4·L5 와 같은 규칙을 두 곳이 따로 들게 된다) · 유일 색인·GiST·revoke 가 있다.
  4) post_load.py 가 갱신한다(빠지면 새 거래 필지가 이웃에서 조용히 빠진다).
  5) 마이그레이션이 begin/commit 으로 감싸였고 두 함수 블록이 정본과 글자 그대로 같다.
  6) 가드 자신의 시험 — 고친 부분을 옛 글자로 되돌린 **사본**에 판정을 돌려 빨간불이 나는지.

ⓘ 도우미는 형제 시험에서 **복사**해 왔다(import 안 함 — 시험끼리 얽히면 한쪽 고장이 다른
  쪽을 조용히 가린다).
"""

import io
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
MIG = os.path.join(ROOT, "supabase", "migrations", "2026-09-27c_p6_cold_cache.sql")
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

NEW_MV = "mv_tx_parcel_geog"
TX_CAST = "t.pnu = list_parcel_transactions.pnu::char(19)"

RE_LINE_COMMENT = re.compile(r"--[^\n]*")
RE_FN_HEAD = re.compile(r"create\s+or\s+replace\s+function\s", re.IGNORECASE)
RE_NEAR_FROM = re.compile(
    r"into\s+v_near100\s*,\s*v_near500\s+from\s+([\w.]+)", re.IGNORECASE)


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read().replace("\r\n", "\n")


def code(sql):
    """주석을 지운다 — 주석 속 옛 글자(설명용)에 걸리면 가드가 거짓말을 한다."""
    return RE_LINE_COMMENT.sub("", sql)


def fn_block(name, sql):
    """`create or replace function <이름>(` 부터 `$$;` 까지(주석 포함 원문)."""
    m = re.search(r"create\s+or\s+replace\s+function\s+{}\s*\(".format(re.escape(name)),
                  sql, re.IGNORECASE)
    assert m, "함수 {} 를 못 찾았습니다 — 이름을 바꿨다면 이 시험도 고칠 것".format(name)
    end = sql.find("\n$$;", m.end())
    assert end != -1, "함수 {} 의 끝($$;)을 못 찾았습니다".format(name)
    nxt = RE_FN_HEAD.search(sql, m.end())
    assert nxt is None or nxt.start() > end, "함수 {} 가 다음 함수를 삼켰습니다".format(name)
    return sql[m.start():end + len("\n$$;")]


# ── 판정 함수(사본에도 똑같이 돌린다 — §6) ─────────────────────────────────


def tx_cast_problems(sql):
    body = code(fn_block("list_parcel_transactions", sql))
    probs = []
    if body.count(TX_CAST) != 1:
        probs.append("char(19) 비교가 정확히 한 번이 아니다({})".format(body.count(TX_CAST)))
    bare = re.findall(r"=\s*list_parcel_transactions\.pnu(?!::char\(19\))", body)
    if bare:
        probs.append("캐스트 없는 비교가 남아 있다: {}".format(bare))
    return probs


def near_source(sql):
    body = code(fn_block("list_price_bands", sql))
    found = RE_NEAR_FROM.findall(body)
    assert len(found) == 1, "이웃 문장이 정확히 하나가 아니다: {}".format(found)
    return found[0]


def mv_problems(sql):
    src = code(sql)
    probs = []
    m = re.search(r"create materialized view if not exists {} as\n(.*?);".format(NEW_MV),
                  src, re.S)
    if not m:
        return ["새 표 정의가 없다"]
    flat = " ".join(m.group(1).split())
    want = ("select p.pnu, p.geom::geography as geog from parcel p where p.geom is not null "
            "and exists (select 1 from transaction t where t.pnu = p.pnu)")
    if flat != want:
        probs.append("새 표 정의가 달라졌다: {}".format(flat))
    if not re.search(r"create unique index if not exists \w+\s+on {} \(pnu\);".format(NEW_MV), src):
        probs.append("유일 색인(pnu)이 없다 — refresh concurrently 가 멈춘다")
    if not re.search(r"create index if not exists \w+\s+on {} using gist \(geog\);".format(NEW_MV), src):
        probs.append("GiST(geog) 색인이 없다 — 반경 조회가 표를 통째로 훑는다")
    if not re.search(r"revoke all on {} from public, anon, authenticated;".format(NEW_MV), src):
        probs.append("anon 에게 닫는 revoke 가 없다")
    return probs


# ── 1)~4) 정본 ───────────────────────────────────────────────────────────────


def test_실거래_함수가_char19로_견준다():
    assert tx_cast_problems(read(SCHEMA)) == []


def test_참고시세_이웃이_새_요약표를_본다():
    assert near_source(read(SCHEMA)) == NEW_MV


def test_새_요약표_정의_색인_권한():
    assert mv_problems(read(SCHEMA)) == []


def test_post_load_가_새_요약표를_갱신한다():
    assert NEW_MV in post_load.REFRESH_MVS
    assert ("refresh materialized view concurrently {};".format(NEW_MV)
            in post_load.build_refresh_sql())


# ── 5) 마이그레이션 ──────────────────────────────────────────────────────────


def test_마이그레이션이_한_트랜잭션이고_notify_는_뒤():
    src = code(read(MIG))
    b, c, n = src.find("\nbegin;"), src.rfind("\ncommit;"), src.find("notify pgrst")
    assert b != -1 and c != -1 and b < c, "begin/commit 으로 감쌀 것"
    assert src.find("create materialized view") > b
    assert src.rfind("$$;") < c
    assert n > c, "notify 는 commit 뒤(커밋돼야 전달된다)"
    assert "concurrently" not in src, "트랜잭션 안에서 concurrently 는 못 돈다"


@pytest.mark.parametrize("name", ["list_parcel_transactions", "list_price_bands"])
def test_마이그레이션_함수_블록이_정본과_같다(name):
    assert fn_block(name, read(MIG)) == fn_block(name, read(SCHEMA))


def test_마이그레이션도_같은_불변식을_지킨다():
    mig = read(MIG)
    assert tx_cast_problems(mig) == []
    assert near_source(mig) == NEW_MV
    assert mv_problems(mig) == []


# ── 6) 가드 자신의 시험 — 옛 글자로 되돌린 사본은 빨간불이어야 한다 ──────────


def test_돌연변이_캐스트를_빼면_잡힌다():
    bad = read(SCHEMA).replace(TX_CAST, "t.pnu = list_parcel_transactions.pnu", 1)
    assert tx_cast_problems(bad)


def test_돌연변이_이웃을_parcel_로_되돌리면_잡힌다():
    src = read(SCHEMA)
    old = ("      from mv_tx_parcel_geog p\n"
           "     where st_dwithin(p.geog, v_geog, 500, false);")
    assert src.count(old) == 1
    bad = src.replace(old, "      from parcel p\n     where p.geom is not null\n"
                           "       and st_dwithin(p.geom::geography, v_geog, 500, false);")
    assert near_source(bad) == "parcel"


def test_돌연변이_주석_속_옛_글자는_통과로_세지_않는다():
    """캐스트를 뺀 뒤 설명 주석에 옛 글자를 적어 두어도 '있다'로 세면 안 된다."""
    src = read(SCHEMA)
    bad = src.replace(TX_CAST, "t.pnu = list_parcel_transactions.pnu -- " + TX_CAST, 1)
    assert tx_cast_problems(bad)


def test_돌연변이_거래_조건을_좁히면_잡힌다():
    src = read(SCHEMA)
    old = "and exists (select 1 from transaction t where t.pnu = p.pnu);"
    assert src.count(old) == 1
    bad = src.replace(old, "and exists (select 1 from transaction t where t.pnu = p.pnu "
                           "and t.tx_type = '집합');")
    assert mv_problems(bad)


def test_돌연변이_유일_색인을_빼면_잡힌다():
    src = read(SCHEMA)
    bad = re.sub(r"create unique index if not exists idx_mtpg_pnu[^\n]*\n", "", src)
    assert bad != src
    assert mv_problems(bad)
