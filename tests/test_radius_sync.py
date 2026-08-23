# -*- coding: utf-8 -*-
"""화면 함수(schema.sql)와 성적표(백테스트)가 **같은 반경**으로 재는지 지킨다.

왜 이 테스트가 있나
-------------------
`scripts/backtest_price.py` 에는 반경이 이렇게 적혀 있다:

    RADIUS_M = {"L4": 100.0, "L5": 500.0}

같은 숫자가 `supabase/schema.sql` 에도 **네 군데** 더 적혀 있다 — 사다리 함수의 두 단계
(L4=100m · L5=500m)와, 둘레의 업종 분포 함수 둘(반경 500m). 한쪽만 고쳐도 양쪽 다 잘
돌고 어디서도 에러가 안 난다. 그런데 뜻은 조용히 갈라진다:

  · 사다리 — 성적표에 적힌 "MdAPE 29.1%" 는 100m·500m 로 잰 성적이다. 화면이 다른
    반경으로 재기 시작하면, 사장님이 결재한 기준선(결정 0013)이 다른 물건에 붙는다.
  · 업종 분포 — 화면은 "반경 500m 안"이라고 **서버가 준 값**(`radius_m`)으로 적는다.
    그래서 재는 반경과 알리는 반경이 어긋나면 화면이 정직하게 거짓말을 한다.

형제 테스트(tests/test_price_ladder_sync.py)가 사다리의 **단계·최소 표본**을 지키고,
여기서는 **반경**을 지킨다. 둘이 한 쌍이다.

⚠️ 숫자를 이 파일에 또 적어 사본을 세 개로 만들지 않는다 — 파이썬 상수를 읽어 와
   그 값을 기준으로 schema.sql 을 대조한다(아래 `test_가드가_헛돌지_않는다` 만 예외이고,
   그건 "정규식이 아무것도 못 잡았는데 초록"이 되는 것을 막는 자리다).

🔬 사보타주 확인 (2026-08-22, 이 테스트를 만든 자리에서 2회)
   ① schema.sql 사본에서 업종 분포 함수의 `'radius_m', 500` 을 `'radius_m', 400` 으로,
      사다리의 `st_dwithin(…, 100, false)` 를 `…, 250, false)` 로 각각 바꿔 아래 함수들을
      호출했더니 실제로 빨간불이 났다(각각 "알리는 반경 400 ≠ 재는 반경 500",
      "사다리 반경 [250.0, 500.0] ≠ [100.0, 500.0]").
   ② 인구조사(아래 test_전체_sql의_반경_리터럴이…)는 supabase/ 를 임시 폴더로 통째로
      복사해 마이그레이션 한 곳(2026-08-16a_stage_b_price_band.sql)의 `500` 을 `750` 으로
      바꾼 뒤 SUPABASE_DIR 만 그 사본으로 돌려 **그 테스트 함수를 실제로 호출**했다 —
      허용 집합 {100.0, 500.0} 밖이라 파일 이름·값을 짚으며 빨간불이 났다.
   두 번 다 **사본**으로만 했고 레포 파일은 한 글자도 손대지 않았다.
"""

import glob
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
SUPABASE_DIR = os.path.join(ROOT, "supabase")
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import backtest_price as bt  # noqa: E402

# 반경을 쓰는 함수들. 사다리 하나 + 업종 분포 둘.
LADDER_FN = "list_price_bands"
INDUSTRY_FNS = ("list_industry_mix", "list_industry_detail")

# `st_dwithin(p.geom::geography, v_geog, 100, false)` 의 셋째 인자(미터)만 집어낸다.
# 인자 안에 괄호가 없으므로 `[^()]` 로 함수 호출 하나를 안전하게 가둔다.
RE_DWITHIN = re.compile(
    r"st_dwithin\([^()]*?,\s*(?P<m>\d+(?:\.\d+)?)\s*,\s*(?:true|false)\s*\)",
    re.IGNORECASE,
)
# 화면에 알리는 반경 — `'radius_m', 500`.
RE_ANNOUNCED = re.compile(r"'radius_m'\s*,\s*(?P<m>\d+(?:\.\d+)?)")

RE_LINE_COMMENT = re.compile(r"--[^\n]*")
RE_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
RE_FN_HEAD = re.compile(r"create\s+or\s+replace\s+function\s", re.IGNORECASE)


def strip_sql_comments(sql):
    """주석을 지운다 — **주석 속 숫자에 걸리면 가드가 거짓말을 한다.**

    이 레포의 SQL 은 주석이 아주 길고 그 안에 실측 수치가 많다(예: "500m 에서 1mm
    미만이라 무시한다"). 지우지 않으면 죽은 글자를 살아 있는 리터럴로 오해한다.
    """
    return RE_LINE_COMMENT.sub("", RE_BLOCK_COMMENT.sub("", sql))


def read_schema():
    with open(SCHEMA, encoding="utf-8") as f:
        return f.read()


def function_body(name, schema=None):
    """schema.sql 에서 함수 하나의 본문만 오려 낸다 (주석은 지운 뒤).

    ⚠️ **스코프를 좁히는 것이 이 함수의 존재 이유다.** 파일 전체에서 500 을 찾으면
       반경과 아무 상관없는 숫자(타임아웃·상한·주석의 실측값)까지 걸려 가드가 헛돈다.

    ⛔ 끝을 `$$;` 로만 찾으면 **다음 함수를 통째로 삼킨다** — 그 함수가 언어에 따라
       `$$;` 대신 다른 종결자를 쓰거나 종결자가 없으면, 오려 낸 덩어리에 남의 반경이
       섞여 들어와 엉뚱한 곳을 대조하게 된다. 그래서 **다음 `create or replace
       function` 을 상한**으로 함께 건다(둘 중 먼저 나오는 것에서 끊는다).
    """
    src = strip_sql_comments(read_schema() if schema is None else schema)
    m = re.search(
        r"create\s+or\s+replace\s+function\s+{}\s*\(".format(re.escape(name)),
        src, re.IGNORECASE,
    )
    assert m, (
        "schema.sql 에서 함수 {} 를 못 찾았습니다.\n"
        "→ 이름을 바꿨다면 이 테스트의 목록도 같이 고치세요. 못 찾은 채로 통과시키면 "
        "가드가 헛돕니다.".format(name)
    )
    end = src.find("\n$$;", m.end())
    if end == -1:
        end = len(src)
    nxt = RE_FN_HEAD.search(src, m.end())
    if nxt and nxt.start() < end:
        end = nxt.start()
    body = src[m.start():end]
    assert body.strip(), "함수 {} 의 본문이 비었습니다".format(name)
    return body


def dwithin_radii(name, schema=None):
    """그 함수가 **실제로 재는** 반경들을 적힌 순서대로."""
    got = [float(x.group("m")) for x in RE_DWITHIN.finditer(function_body(name, schema))]
    assert got, (
        "함수 {} 안에서 st_dwithin 반경을 하나도 못 읽었습니다 — 정규식이 헛돕니다.".format(name)
    )
    return got


def announced_radii(name, schema=None):
    """그 함수가 **화면에 알리는** 반경들(`'radius_m', N`)."""
    return [float(x.group("m")) for x in RE_ANNOUNCED.finditer(function_body(name, schema))]


# ── 사다리 (Stage B · 결정 0013) ─────────────────────────────────────────────


def test_사다리_반경이_백테스트와_같다():
    """L4=100m · L5=500m 가 성적표를 뽑은 자와 같아야 한다.

    적힌 순서가 곧 (L4, L5) 다 — 100m 는 500m 안을 훑은 결과에서 걸러 쓰는 구조라
    바깥(500m)보다 먼저 나온다. 순서가 뒤집히면 두 단계가 서로 바뀐 것이니 그것도 잡는다.
    """
    got = dwithin_radii(LADDER_FN)
    want = [bt.RADIUS_M["L4"], bt.RADIUS_M["L5"]]
    assert got == want, (
        "화면 사다리와 백테스트의 반경이 갈라졌습니다.\n"
        "  schema.sql {} : {}\n"
        "  backtest_price.RADIUS_M : {}\n"
        "→ 한쪽만 고치면 성적표의 숫자가 화면이 쓰는 방법의 성적이 아니게 됩니다.".format(
            LADDER_FN, got, want
        )
    )


# ── 둘레의 업종 분포 (결정 0014) ─────────────────────────────────────────────
#
# 여기 500m 는 사다리 L5 와 **뜻이 다른 반경**이다(하나는 값의 근거, 하나는 가게 세는
# 범위). 다만 자는 하나만 쓰기로 했다 — 한 화면에서 "500m 안"이 두 가지를 뜻하면
# 사람이 읽을 수 없다. 그래서 같은 상수에 묶어 둔다.


@pytest.mark.parametrize("fn", INDUSTRY_FNS)
def test_업종분포_반경이_사다리와_같은_자를_쓴다(fn):
    want = bt.RADIUS_M["L5"]
    for got in dwithin_radii(fn):
        assert got == want, (
            "{} 의 반경 {}m 가 backtest_price.RADIUS_M['L5']({}m)와 다릅니다.\n"
            "→ 한 화면에서 '500m 안'이 두 가지를 뜻하게 됩니다.".format(fn, got, want)
        )


@pytest.mark.parametrize("fn", INDUSTRY_FNS)
def test_알리는_반경과_재는_반경이_같다(fn):
    """화면은 `radius_m` 을 그대로 글자로 적는다 — 재는 값과 다르면 정직한 거짓말이 된다."""
    announced = announced_radii(fn)
    assert announced, (
        "{} 가 화면에 알리는 반경('radius_m')을 못 찾았습니다 — 정규식이 헛돕니다.".format(fn)
    )
    measured = set(dwithin_radii(fn))
    for said in announced:
        assert {said} == measured, (
            "{} 가 알리는 반경({}m)과 실제로 잰 반경({})이 다릅니다.\n"
            "→ 화면은 서버가 준 값을 그대로 적으므로, 어긋나면 화면이 사실이 아닌 말을 "
            "합니다.".format(fn, said, sorted(measured))
        )


# ── 가드의 가드 ──────────────────────────────────────────────────────────────


def test_가드가_헛돌지_않는다():
    """정규식이 아무것도 못 잡아도 위 테스트들이 초록이 되지 않는지.

    실제 값(사다리 100·500 / 업종 분포 500 둘)을 한 번 못 박아, 파싱이 빈 결과를 내거나
    스코프가 통째로 어긋나면 여기서 먼저 빨간불이 나게 한다.

    ⚠️ 그래서 이 테스트는 **정당한 반경 변경에도 터진다.** 그게 의도다 — 기대값이 박혀
       있어야 "파싱이 아무것도 못 잡는 상태"와 "값이 실제로 바뀐 상태"를 가를 수 있다.
       반경을 정말 바꿨다면 backtest_price.RADIUS_M · schema.sql · 여기를 **셋 다** 고친다.
    """
    assert dwithin_radii(LADDER_FN) == [100.0, 500.0]
    for fn in INDUSTRY_FNS:
        assert dwithin_radii(fn) == [500.0], fn
        assert announced_radii(fn) == [500.0], fn


@pytest.mark.parametrize("fn", (LADDER_FN,) + INDUSTRY_FNS)
def test_스코프가_함수_안으로_좁혀져_있다(fn):
    """파일 전체를 훑으면 반경과 무관한 숫자까지 걸려 가드가 헛돈다.

    ⛔ 오려 낸 덩어리에 `create or replace function` 이 **한 번만** 나와야 한다. 두 번
       나오면 다음 함수를 삼킨 것이고, 그러면 남의 반경을 내 것인 양 대조하게 된다.
    """
    body = function_body(fn)
    assert len(RE_FN_HEAD.findall(body)) == 1, (
        "{} 본문에 함수 머리가 여러 개입니다 — 다음 함수를 삼켰습니다.".format(fn)
    )
    assert len(body) < len(read_schema()), "함수 본문이 파일 전체와 같습니다 — 못 오려 냈습니다"


# ── 인구조사: supabase/**/*.sql 전체의 반경 리터럴 ───────────────────────────
#
# 위 테스트들은 **아는 함수 세 개**만 본다. 그러면 두 가지를 못 본다:
#  · 마이그레이션 파일에 들어 있는 **같은 함수의 사본**(라이브에 실제로 적용되는 것은
#    이쪽이다 — schema.sql 은 정본 기록이고 손으로 맞춰 둔 사본이다).
#  · 앞으로 **새로 생길 함수**의 반경(목록에 이름을 더하는 것을 잊으면 무방비다).
# 그래서 파일 전체에서 st_dwithin 리터럴을 전수로 세어, 우리가 쓰기로 한 자(RADIUS_M)
# 밖의 값이 하나라도 있으면 잡는다.


def sql_files():
    return sorted(glob.glob(os.path.join(SUPABASE_DIR, "**", "*.sql"), recursive=True))


def test_supabase_sql_파일을_실제로_찾는다():
    """glob 이 빈 목록을 돌려주면 아래 인구조사가 **아무것도 안 보고 초록**이 된다."""
    files = sql_files()
    assert len(files) > 1, "supabase/ 아래 .sql 을 못 찾았습니다 — 인구조사가 헛돕니다"
    assert any(os.path.basename(f) == "schema.sql" for f in files)
    assert any(os.sep + "migrations" + os.sep in f for f in files), "마이그레이션도 봐야 한다"


def test_전체_sql의_반경_리터럴이_전부_RADIUS_M_안에_있다():
    """schema.sql·마이그레이션을 통틀어 st_dwithin 반경은 우리가 정한 자뿐이어야 한다."""
    allowed = set(bt.RADIUS_M.values())
    strays = []
    for path in sql_files():
        with open(path, encoding="utf-8") as f:
            body = strip_sql_comments(f.read())
        for m in RE_DWITHIN.finditer(body):
            if float(m.group("m")) not in allowed:
                # 파일 이름만 적는다 — 이 레포에서 .sql 이름은 서로 겹치지 않고,
                # 경로를 계산하면 사보타주를 다른 드라이브에서 돌릴 때 거기서 죽는다.
                strays.append((os.path.basename(path), float(m.group("m"))))
    assert not strays, (
        "backtest_price.RADIUS_M({}) 밖의 반경이 SQL 에 있습니다: {}\n"
        "→ 새 반경을 정말 쓰기로 했다면 RADIUS_M 부터 고치고 성적표를 다시 뽑으세요 "
        "(화면과 성적표가 서로 다른 자를 쓰면 결재한 기준선이 다른 물건에 붙습니다).".format(
            sorted(allowed), strays
        )
    )


def test_인구조사가_실제로_리터럴을_세고_있다():
    """한 건도 못 세고 있으면 위 테스트는 영원히 초록이다 — 가드의 가드."""
    found = 0
    for path in sql_files():
        with open(path, encoding="utf-8") as f:
            found += len(RE_DWITHIN.findall(strip_sql_comments(f.read())))
    assert found >= 6, "st_dwithin 리터럴을 {}개밖에 못 셌습니다 — 정규식이 헛돕니다".format(found)
