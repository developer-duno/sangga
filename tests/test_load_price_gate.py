# -*- coding: utf-8 -*-
"""
scripts/load_price_gate.py 단위 테스트

DB 없이 검증한다:
  1. 값 검사      — 구 코드 5자리·참거짓·비율. 모호한 값이 통과로 읽히면 안 된다
  2. ★ 관문 ①    — 모든 구 코드가 mv_open_sigungu 에 실존하는지 **DB 안에서** 본다
  3. ★ 관문 ②    — 통과 구가 0개면 아예 넣지 않는다(화면이 통째로 꺼진다)
  4. ★ 관문 ③    — 넣은 뒤 DB 의 통과 구 수가 CSV 와 같은지 본다(유령 통과 구 차단)
  5. 유령 감지    — CSV 에서 사라진 구는 **지우지 않고 세어서** 보여준다
  6. SQL 조립     — 한 트랜잭션, 배치, upsert, 작은따옴표 escape
  7. 레포 실물    — 백테스트가 만든 통과구.csv 가 스스로 통과하는가 (결정 0013 §2 못 박기)

conftest.py를 새로 만들지 않기 위해 sys.path 조작은 이 파일 안에서만 한다.
"""

import io
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.join(_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import load_price_gate as L  # noqa: E402

# 결정 0013 §2 가 확정한 통과 구 14곳(서울 10 + 대전 4). 성적표 v1 기준.
DECISION_0013_PASSED = {
    "11140", "11170", "11260", "11350", "11380", "11440", "11470", "11500",
    "11650", "11680", "30110", "30170", "30200", "30230",
}


def row(code="11680", nm="강남구", n=262, ladder=0.283166, base=0.491653, ok=True):
    return {"sigungu_code": code, "sigungu_nm": nm, "n_paired": n,
            "ladder_mdape": ladder, "base_mdape": base, "gate_pass": ok}


def rec(code="11680", nm="강남구", n="262", ladder="0.28", base="0.49", ok="true"):
    return {"sigungu_code": code, "sigungu_nm": nm, "n_paired": n,
            "ladder_mdape": ladder, "base_mdape": base, "gate_pass": ok}


# ── 1. 값 검사 ───────────────────────────────────────────────────────────────


def test_required_columns():
    with pytest.raises(ValueError) as e:
        L.assert_required_columns(["sigungu_code", "gate_pass"])
    assert "n_paired" in str(e.value)


def test_머리글_BOM은_벗겨_읽는다():
    """CSV 는 엑셀 대응으로 utf-8-sig 로 쓰인다 — BOM 을 못 벗기면 첫 칸이 통째로 안 읽힌다."""
    assert L.assert_required_columns(["﻿sigungu_code", "sigungu_nm", "n_paired",
                                      "ladder_mdape", "base_mdape", "gate_pass"]) is True


@pytest.mark.parametrize("bad", ["1168", "116800", "1168A", ""])
def test_구코드는_5자리_숫자라야_한다(bad):
    with pytest.raises(ValueError) as e:
        L.record_to_row(rec(code=bad), "3행")
    assert "3행" in str(e.value)


def test_모호한_참거짓은_거부한다():
    """★ 'maybe' 가 조용히 거짓(또는 참)으로 읽히면 켜지 말아야 할 구가 켜진다."""
    with pytest.raises(ValueError) as e:
        L.record_to_row(rec(ok="maybe"), "3행")
    assert "gate_pass" in str(e.value)


@pytest.mark.parametrize("word,expected", [("true", True), ("TRUE", True),
                                           ("false", False), ("False", False)])
def test_참거짓_표기_흔들림은_받아준다(word, expected):
    assert L.record_to_row(rec(ok=word), "3행")["gate_pass"] is expected


def test_빈_오차는_모른다는_뜻이라_None():
    """0 으로 바꾸면 '오차가 0'이라는 거짓말이 된다."""
    got = L.record_to_row(rec(ladder="", base=""), "3행")
    assert got["ladder_mdape"] is None and got["base_mdape"] is None


def test_음수_오차는_거부한다():
    with pytest.raises(ValueError):
        L.record_to_row(rec(ladder="-0.1"), "3행")


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "Infinity"])
def test_nan_inf는_거부한다(bad):
    """★ float() 는 이것들을 **통과시킨다.** nan 은 어떤 비교에도 거짓이라 판정이 조용히 뒤집힌다."""
    with pytest.raises(ValueError) as e:
        L.record_to_row(rec(ladder=bad), "3행")
    assert "특수값" in str(e.value) or "음수" in str(e.value)


def test_퍼센트_값을_넣으면_거부한다():
    """비율(0.29)이 아니라 퍼센트(29)를 넣은 CSV — 근거 칸이 조용히 거짓말을 한다."""
    with pytest.raises(ValueError) as e:
        L.record_to_row(rec(ladder="29"), "3행")
    assert "퍼센트" in str(e.value)


def test_1을_조금_넘으면_경고만_하고_받는다(capsys):
    """오차율 100% 초과는 실제로 있을 수 있다(구로구 BASE 70.5%처럼 큰 값도 있다).
    막지는 않되 눈에 띄게 한다."""
    got = L.record_to_row(rec(ladder="1.5", base="1.6", ok="false"), "3행")
    assert got["ladder_mdape"] == 1.5
    assert "경고" in capsys.readouterr().err


def test_record_to_row_trims():
    got = L.record_to_row(rec(code=" 11680 ", nm=" 강남구 "), "3행")
    assert got["sigungu_code"] == "11680" and got["sigungu_nm"] == "강남구"


def test_같은_구가_두번이면_멈춘다():
    with pytest.raises(ValueError) as e:
        L.assert_unique([row(), row()])
    assert "11680" in str(e.value)


# ── 2~5. ★ 관문 ─────────────────────────────────────────────────────────────


def test_구코드_관문은_SQL_안에서_예외를_던진다():
    """★ select 로 세기만 하면 psql 종료코드가 0 이라 그대로 commit 된다."""
    sql = L.build_sigungu_gate([row(code="11680")])
    assert "raise exception" in sql
    assert "mv_open_sigungu" in sql
    assert "('11680')" in sql


def test_통과구가_0개면_넣지_않는다():
    """★ 관문 ② — 전부 false 인 표를 넣으면 참고 시세가 전 지역에서 사라진다.

    숫자도 탈락에 맞춘다(0.6 > 0.30) — 안 그러면 판정 재검증에 먼저 걸려 다른 이유로 멈춘다.
    """
    fail = dict(ladder=0.6, base=0.5, ok=False)
    with pytest.raises(ValueError) as e:
        L.build_sql([row(**fail), row(code="11110", nm="종로구", **fail)])
    assert "통과한 구가 한 곳도 없습니다" in str(e.value)


def test_판정칸을_손으로_고치면_적재기가_막는다():
    """★ P1-3 — 금천구 숫자에 gate_pass=true 로 고쳐 넣어도 적재기가 스스로 잡는다.

    CSV 는 사람이 엑셀로 열어 고칠 수 있는 파일이고, **적재는 CI 가 아니라 사람이 로컬에서**
    돌린다. 그래서 이 방어선은 테스트가 아니라 적재기 안에 있어야 한다.
    """
    with pytest.raises(ValueError) as e:
        L.build_sql([row(code="11545", nm="금천구", n=99,
                         ladder=0.259708, base=0.175917, ok=True)])
    msg = str(e.value)
    assert "금천구(11545)" in msg and "기준선 규칙과 어긋납니다" in msg


def test_통과인데_false로_적힌_것도_잡는다():
    """반대 방향도 막는다 — 켜져야 할 구가 조용히 꺼지는 것도 사고다."""
    with pytest.raises(ValueError):
        L.build_sql([row(ladder=0.13, base=0.54, ok=False)])


def test_판정_재검증이_규칙과_같은_함수를_쓴다():
    """★ 규칙 사본을 여기서 새로 짜면 정본이 둘이 된다 — 같은 함수인지 확인한다."""
    import backtest_price as bt  # noqa: PLC0415
    assert L.assert_gate_matches_rule(
        [row(ladder=0.10, base=0.40, ok=bt.gate_pass(0.10, 0.40))]) is True


def test_통과구_수_관문이_예외를_던진다():
    """★ 관문 ③ — upsert 는 사라진 구를 지우지 않는다. 수가 어긋나면 통째로 되돌린다."""
    sql = L.build_pass_count_gate([row(), row(code="11140", nm="중구"),
                                   row(code="11110", nm="종로구", ok=False)])
    assert "raise exception" in sql
    assert "select count(*) into got from price_gate_sigungu where gate_pass;" in sql
    assert "if got <> 2 then" in sql


def test_유령은_세기만_하고_지우지_않는다():
    sql = L.build_ghost_probe([row(code="11680")])
    assert sql.lstrip().startswith("select count(*)")
    assert "delete" not in sql.lower()
    assert "'11680'" in sql


def test_관문_순서_구코드는_insert_앞_수대조는_뒤():
    """관문이 insert 뒤에 오면 오타가 든 행이 먼저 들어갔다 되돌려진다. 수 대조는 반대다 —
    넣은 뒤라야 표에 실제로 든 것을 센다."""
    sql = L.build_sql([row()])
    i_insert = sql.index("insert into price_gate_sigungu")
    assert sql.index("mv_open_sigungu") < i_insert
    assert i_insert < sql.index("select count(*) into got")


# ── 6. SQL 조립 ──────────────────────────────────────────────────────────────


def test_sql_is_one_transaction():
    sql = L.build_sql([row()])
    assert sql.startswith("begin;")
    assert sql.rstrip().endswith("commit;")


def test_sql_batches():
    rows = [row(code="1{:04d}".format(i)) for i in range(250)]
    sql = L.build_sql(rows, batch_rows=100)
    assert sql.count("insert into price_gate_sigungu") == 3


def test_upsert_는_판정과_근거를_함께_갱신한다():
    """참·거짓만 갱신하면 "왜 꺼졌나"의 근거가 옛 판에 머문다."""
    sql = L.build_sql([row()])
    assert "on conflict (sigungu_code) do update set" in sql
    for col in ("sigungu_nm", "n_paired", "ladder_mdape", "base_mdape", "gate_pass"):
        assert "{} = excluded.{}".format(col, col) in sql
    assert "loaded_at = now()" in sql


def test_값_리터럴():
    assert L.sql_str("a'b") == "'a''b'"
    assert L.sql_str("") == "null"
    assert L.sql_num(None) == "null"
    assert L.sql_num(0.5) == "0.5"
    assert L.sql_bool(True) == "true" and L.sql_bool(False) == "false"


def test_잴_수_없던_구는_null로_들어간다():
    sql = L.build_sql([row(), row(code="11110", nm="종로구", n=0,
                                  ladder=None, base=None, ok=False)])
    assert "('11110', '종로구', 0, null, null, false)" in sql


def test_build_sql_refuses_empty():
    with pytest.raises(ValueError):
        L.build_sql([])


# ── 7. 레포에 든 산출물 자체를 검사한다 ──────────────────────────────────────


def test_레포_통과구_CSV가_읽히고_SQL이_된다():
    rows = L.read_gate_csv(L.DEFAULT_CSV)
    assert len(rows) > 20, "구가 너무 적습니다 — 성적표를 다시 뽑아야 할 수 있습니다"
    sql = L.build_sql(rows)
    assert sql.startswith("begin;") and sql.rstrip().endswith("commit;")


def test_레포_통과구_CSV가_결정0013과_같은_14곳이다():
    """★ 결정 0013 §2 가 확정한 목록. 손으로 구를 넣고 빼면 여기서 걸린다.

    성적표 v2 를 뽑아 목록이 정당하게 바뀌는 날에는 이 기대값도 같이 바꾼다 —
    그때 "왜 바뀌었나"를 사람이 한 번은 보게 하는 것이 이 테스트의 목적이다.
    """
    rows = L.read_gate_csv(L.DEFAULT_CSV)
    passed = {r["sigungu_code"] for r in rows if r["gate_pass"]}
    assert passed == DECISION_0013_PASSED


def test_레포_통과구_CSV에서_금천구는_탈락이다():
    """★ 금천구(11545)는 오차 26.0% 로 조건 ①을 통과하지만 구 평균(17.6%)에 진다.

    결정 0013 §2 가 "목록 갱신 때 실수로 되살리지 말 것"이라고 못 박은 유일한 사례다.
    """
    by_code = {r["sigungu_code"]: r for r in L.read_gate_csv(L.DEFAULT_CSV)}
    gunchon = by_code["11545"]
    assert gunchon["gate_pass"] is False
    assert gunchon["ladder_mdape"] <= 0.30          # 조건 ①은 통과했다
    assert gunchon["ladder_mdape"] > gunchon["base_mdape"]   # 조건 ②에서 졌다


def test_레포_통과구_CSV의_판정이_기준선과_일치한다():
    """★ CSV 의 gate_pass 칸이 그 줄의 숫자와 어긋나면(손으로 고쳤다면) 여기서 걸린다."""
    import backtest_price as bt  # noqa: PLC0415  (백테스트 판정 함수가 정본이다)
    bad = [r["sigungu_code"] for r in L.read_gate_csv(L.DEFAULT_CSV)
           if r["gate_pass"] != bt.gate_pass(r["ladder_mdape"], r["base_mdape"])]
    assert not bad, "판정 칸이 숫자와 어긋난 구: {}".format(bad)


# ── 절대 규칙 2 (금지 표현) ─────────────────────────────────────────────────


def test_스크립트와_마이그레이션에_금지표현이_없다():
    paths = [os.path.join(_SCRIPTS_DIR, "load_price_gate.py"),
             os.path.join(_ROOT, "supabase", "migrations",
                          "2026-08-16a_stage_b_price_band.sql"),
             # 정본에도 같은 잣대를 댄다 — 마이그레이션 내용을 손으로 옮기다 금칙어가
             # 딸려 들어갈 수 있고, 새 환경을 만드는 파일은 이쪽이다.
             os.path.join(_ROOT, "supabase", "schema.sql")]
    for path in paths:
        with io.open(path, encoding="utf-8") as f:
            body = f.read()
        for banned in ("적정가격", "적정가", "평가액", "감정가", "가치평가"):
            assert banned not in body, "금지 표현 발견: {} ({})".format(banned, path)
