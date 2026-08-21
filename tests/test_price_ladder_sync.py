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
    """
    assert sql_ladder() == [("L2", 1, 1), ("L4", 2, 3), ("L5", 3, 5), ("L6", 4, 1)]


@pytest.mark.parametrize("lvl", ["L2", "L4", "L5", "L6"])
def test_모든_사다리_단계가_MIN_SAMPLES에_적혀_있다(lvl):
    """SQL 에만 있고 파이썬에는 없는 단계가 생기면, 대조 자체가 조용히 건너뛰어진다."""
    assert lvl in bt.MIN_SAMPLES, "MIN_SAMPLES 에 {} 가 없습니다".format(lvl)
