# -*- coding: utf-8 -*-
"""사다리(화면 함수)와 성적표(백테스트)가 **같은 규칙**을 쓰는지 지킨다.

왜 이 테스트가 있나
-------------------
`supabase/schema.sql` 의 `list_price_bands` 는 사다리를 이렇게 적어 둔다:

    join (values ('L2', 1, 1), ('L4', 2, 3), ('L5', 3, 5), ('L6', 4, 1))
           as s(lvl, ord, min_n) on s.lvl = a.lvl

세 칸의 뜻은 (단계 이름, 걷는 순서, 최소 표본)이다. 같은 값이 파이썬 쪽
`scripts/backtest_price.py` 의 `LADDER` · `MIN_SAMPLES` 에도 있다. 정본에는
이렇게 적혀 있다(schema.sql):

    ⛔ 이 최소 표본은 `scripts/backtest_price.py` 의 `MIN_SAMPLES` 와 **같은 값이라야 한다.**
       갈라지면 화면과 성적표가 서로 다른 방법이 되는데 어디서도 에러가 안 난다.

말로만 적힌 약속은 못 지킨다 — **한쪽만 고쳐도 양쪽 다 잘 돌고 테스트도 초록**이다.
성적표에 "MdAPE 29.1%" 라고 적힌 그 방법과 화면이 실제로 쓰는 방법이 조용히
갈라지면, 사장님이 결재한 기준선(결정 0013)이 다른 물건에 붙어 버린다.
그래서 기계가 대조하게 한다.

⚠️ 여기서 지키는 것은 **사다리 규칙과 최소 표본까지**다. 후보를 고르는 창은 일부러
   다르다(백테스트는 학습 구간, 함수는 롤링 24개월 — schema.sql 주석 참조).
"""

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import backtest_price as bt  # noqa: E402

# `join (values ('L2', 1, 1), ('L4', 2, 3), …)` 의 괄호 묶음만 하나씩 집어낸다.
RE_LADDER_JOIN = re.compile(
    r"join\s*\(values\s*(?P<rows>\([^)]*\)(?:\s*,\s*\([^)]*\))*)\s*\)\s*"
    r"as\s+s\s*\(\s*lvl\s*,\s*ord\s*,\s*min_n\s*\)",
    re.IGNORECASE,
)
RE_ROW = re.compile(r"\(\s*'(?P<lvl>[^']+)'\s*,\s*(?P<ord>\d+)\s*,\s*(?P<min_n>\d+)\s*\)")


def sql_ladder():
    """정본에서 사다리 표를 읽어 [(단계, 순서, 최소표본), …] 로 돌려준다."""
    with open(SCHEMA, encoding="utf-8") as f:
        schema = f.read()
    m = RE_LADDER_JOIN.search(schema)
    assert m, (
        "schema.sql 에서 사다리 표(join (values …) as s(lvl, ord, min_n))를 못 찾았습니다.\n"
        "→ 표 모양을 바꿨다면 이 테스트의 정규식도 같이 고치세요. "
        "못 찾은 채로 통과시키면 가드가 헛돕니다."
    )
    rows = [
        (r.group("lvl"), int(r.group("ord")), int(r.group("min_n")))
        for r in RE_ROW.finditer(m.group("rows"))
    ]
    assert rows, "사다리 표는 찾았는데 줄을 하나도 못 읽었습니다"
    return rows


def test_사다리_단계와_순서가_백테스트와_같다():
    """단계 이름도, 걷는 순서도 같아야 한다."""
    rows = sql_ladder()
    sql_stages = tuple(lvl for lvl, _, _ in sorted(rows, key=lambda r: r[1]))
    assert sql_stages == tuple(bt.LADDER), (
        "화면 함수와 백테스트의 사다리가 갈라졌습니다.\n"
        "  schema.sql list_price_bands : {}\n"
        "  backtest_price.LADDER       : {}\n"
        "→ 한쪽만 고치면 성적표의 숫자가 화면이 쓰는 방법의 성적이 아니게 됩니다.".format(
            sql_stages, tuple(bt.LADDER)
        )
    )


def test_최소표본이_백테스트와_같다():
    """`(lvl, ord, min_n)` 의 min_n 이 MIN_SAMPLES 와 한 칸도 어긋나면 안 된다."""
    rows = sql_ladder()
    mismatched = [
        (lvl, min_n, bt.MIN_SAMPLES.get(lvl))
        for lvl, _, min_n in rows
        if bt.MIN_SAMPLES.get(lvl) != min_n
    ]
    assert not mismatched, (
        "최소 표본이 갈라졌습니다 (단계, schema.sql, backtest_price.MIN_SAMPLES): {}\n"
        "→ schema.sql 의 ⛔ 주석대로 두 값은 같아야 합니다.".format(mismatched)
    )


def test_백테스트에만_있는_단계는_사다리에_없다():
    """MIN_SAMPLES 에는 L7·BASE 도 있지만 그건 **사다리 칸이 아니다**.

    BASE(구 평균)는 대조군이고 L7(유형축)은 검증용이다 — 실수로 사다리에 섞여 들어가면
    화면이 결재받지 않은 단계로 값을 내게 된다(결정 0013 §1).
    """
    sql_stages = {lvl for lvl, _, _ in sql_ladder()}
    for extra in ("BASE", "L7"):
        assert extra not in sql_stages, (
            "{} 가 화면 사다리에 들어갔습니다 — 대조군·검증용이라 사다리 칸이 아닙니다.".format(extra)
        )


def test_가드가_헛돌지_않는다():
    """정규식이 아무것도 못 잡아도 위 테스트가 초록이 되지 않는지 — 가드의 가드.

    실제 값(L2=1 · L4=3 · L5=5 · L6=1)을 한 번 못 박아, 파싱이 빈 결과를 내면
    여기서 먼저 빨간불이 나게 한다.

    ⚠️ 그래서 이 테스트는 **정당한 사다리 변경에도 터진다.** 그게 의도다 — 기대값이
       박혀 있어야 "파싱이 아무것도 못 잡는 상태"와 "값이 실제로 바뀐 상태"를 가를 수 있다.
    """
    expected = [("L2", 1, 1), ("L4", 2, 3), ("L5", 3, 5), ("L6", 4, 1)]
    assert sql_ladder() == expected, (
        "사다리 값이 여기 박아 둔 기대값과 다릅니다.\n"
        "  · **일부러 바꾼 것이라면** — schema.sql 과 backtest_price.MIN_SAMPLES 를 양쪽 다\n"
        "    바꿨는지 먼저 확인하고(위 두 테스트가 그걸 봅니다), 맞다면 **이 테스트의\n"
        "    `expected` 줄도 같이 갱신**하세요. 여기만 남겨 두면 진짜 드리프트를 못 잡습니다.\n"
        "  · **바꾼 적이 없다면** — 정규식이 표를 잘못 읽고 있다는 뜻입니다(가드가 헛도는 상태).\n"
        "  ⛔ 사다리 값 자체를 바꾸는 것은 결재 사항입니다(결정 0013 — 기준선은 성적표로만 갱신)."
    )


@pytest.mark.parametrize("lvl", ["L2", "L4", "L5", "L6"])
def test_모든_사다리_단계가_MIN_SAMPLES에_적혀_있다(lvl):
    """SQL 에만 있고 파이썬에는 없는 단계가 생기면, 대조 자체가 조용히 건너뛰어진다."""
    assert lvl in bt.MIN_SAMPLES, "MIN_SAMPLES 에 {} 가 없습니다".format(lvl)


# ── 오피스텔 낱말 — 참고 시세 층 묶음 ↔ 호실 구성표 (결정 0040 D9) ─────────────
# 오피스텔 층을 가르는 낱말은 호실 구성표(list_unit_floor_summary)의 officetel_re 와 **글자 같아야** 한다.
# 갈라지면 같은 층이 구성표에서는 오피스텔인데 참고 시세는 업무 값을 내는(또는 거꾸로) 일이 조용히 생긴다.

RE_OFFICETEL = re.compile(r"('[^']*'::text)\s+as\s+officetel_re")


def _schema():
    with open(SCHEMA, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def _fn(name, sql):
    m = re.search(r"(?im)^create\s+or\s+replace\s+function\s+{}\s*\(".format(re.escape(name)), sql)
    assert m, name
    end = sql.index("$$;", sql.index("$$", m.end()) + 2)
    return sql[m.start():end + 3]


def officetel_literals(sql):
    """함수마다 officetel_re 낱말 → {함수: [글자…]} (못 찾으면 빈 목록 — 아래 대조가 빨강)."""
    return {name: RE_OFFICETEL.findall(_fn(name, sql))
            for name in ("price_floor_use_group", "list_unit_floor_summary")}


def officetel_problems(sql):
    lits = officetel_literals(sql)
    probs = []
    if len(lits["price_floor_use_group"]) != 1:
        probs.append("층 묶음 함수의 officetel_re 가 정확히 하나가 아니다: {}".format(lits["price_floor_use_group"]))
    if not lits["list_unit_floor_summary"]:
        probs.append("호실 구성표의 officetel_re 를 못 찾았다")
    if set(lits["price_floor_use_group"]) != set(lits["list_unit_floor_summary"]):
        probs.append("오피스텔 낱말이 갈라졌다: {}".format(lits))
    return probs


def test_오피스텔_낱말이_호실_구성표와_같다():
    assert officetel_problems(_schema()) == []


# ── 용도 묶음표 — SQL 함수 ↔ 백테스트 파이썬 표 (결정 0040 ㉠) ──────────────────
# 묶음표의 정본은 DB 함수 둘이다. 백테스트의 USE_GROUP_CD·USE_GROUP_NM 이 한 글자라도 다르면
# 성적표가 화면과 다른 묶음으로 채점한 것이 된다(에러 0).

RE_WHEN_IN = re.compile(r"when\s+(left\(p_cd,\s*2\)|p_nm)\s+in\s*\(([^)]*)\)\s+then\s+'(\w+)'")
RE_ELSE = re.compile(r"else\s+'(\w+)'")


def sql_group_table(sql, name):
    """묶음 함수 하나 → ({글자: 묶음}, else 묶음, 빈 값 갈래가 null 인가)."""
    body = _fn(name, sql)
    body = re.sub(r"--[^\n]*", "", body)
    table = {}
    for _, items, grp in RE_WHEN_IN.findall(body):
        for item in re.findall(r"'([^']*)'", items):
            table[item] = grp
    other = RE_ELSE.findall(body)
    null_first = bool(re.search(r"when\s+nullif\(p_(?:cd|nm),\s*''\)\s+is\s+null\s+then\s+null", body))
    return table, (other[0] if len(other) == 1 else None), null_first


def group_table_problems(sql):
    probs = []
    for name, py in (("price_use_group_cd", bt.USE_GROUP_CD), ("price_use_group_nm", bt.USE_GROUP_NM)):
        table, other, null_first = sql_group_table(sql, name)
        if not table:
            probs.append("{} 의 표를 못 읽었다".format(name))
        if table != py:
            probs.append("{} 과 파이썬 표가 다르다: SQL {} / 파이썬 {}".format(name, table, py))
        if other != bt.USE_GROUP_OTHER:
            probs.append("{} 의 그 밖 묶음이 다르다: {}".format(name, other))
        if not null_first:
            probs.append("{} 의 빈 값 → NULL 갈래가 없다".format(name))
    return probs


def test_묶음표가_백테스트와_같다():
    assert group_table_problems(_schema()) == []


def test_돌연변이_묶음표_한_칸을_바꾸면_잡힌다():
    src = _schema()
    blk = _fn("price_use_group_cd", src)
    bad = blk.replace("in ('14')", "in ('14', '10')", 1)
    assert bad != blk
    probs = group_table_problems(src.replace(blk, bad, 1))
    assert len(probs) == 1 and probs[0].startswith("price_use_group_cd 과 파이썬 표가 다르다")


def test_돌연변이_이름_묶음에서_판매를_빼면_잡힌다():
    src = _schema()
    blk = _fn("price_use_group_nm", src)
    bad = blk.replace(", '판매')", ")", 1)
    assert bad != blk
    probs = group_table_problems(src.replace(blk, bad, 1))
    assert len(probs) == 1 and probs[0].startswith("price_use_group_nm 과 파이썬 표가 다르다")


def test_백테스트_pg_temp_판은_정본_글자_그대로다():
    """결정 0040 ㉧ — 백테스트가 psql 세션에 만드는 함수 둘의 본문이 정본과 같아야 한다(이름 앞 pg_temp. 만 다름)."""
    src = _schema()
    made = bt.pg_temp_floor_group_sql(src)
    assert "create or replace function pg_temp.price_use_group_cd(" in made
    assert "create or replace function pg_temp.price_floor_use_group(" in made
    assert "pg_temp.price_use_group_cd(u.main_purps_cd)" in made
    back = made.replace("pg_temp.", "")
    assert back == _fn("price_use_group_cd", src) + "\n\n" + _fn("price_floor_use_group", src) + "\n"


def test_돌연변이_pg_temp_를_안_붙이면_세션_함수가_아니다():
    """양성 대조 — 본문 안 호출에 pg_temp. 가 없으면 운영(public)에 아직 없는 함수를 부르게 된다."""
    src = _schema()
    made = bt.pg_temp_floor_group_sql(src)
    calls = re.findall(r"(?<![\w.])price_use_group_cd\(", made)
    assert calls == []
    bad = made.replace("pg_temp.price_use_group_cd(u.", "price_use_group_cd(u.")
    assert re.findall(r"(?<![\w.])price_use_group_cd\(", bad)


def test_돌연변이_오피스텔_낱말을_바꾸면_잡힌다():
    src = _schema()
    blk = _fn("price_floor_use_group", src)
    bad = blk.replace("'오피스텔'::text as officetel_re", "'오피스텔|주거용'::text as officetel_re", 1)
    assert bad != blk
    assert officetel_problems(src.replace(blk, bad, 1)) == [
        "오피스텔 낱말이 갈라졌다: {}".format(officetel_literals(src.replace(blk, bad, 1)))]
