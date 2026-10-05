# -*- coding: utf-8 -*-
"""
scripts/backtest_openclose.py 1:1 단위 테스트 (결정 0033 R3 정답지 시험).

셈 규칙(셈법 A·B · 앞/뒤 좌표 귀속 · 비율 집계)은 **shapely 없이** 작은 픽스처로 본다.
shapely 가 필요한 시험(가게 → 상권 도형)만 `pytest.importorskip("shapely")` —
CI 에는 shapely 가 없다(pyshp 와 같은 취급).

DB·네트워크는 한 번도 건드리지 않는다.
"""

import json
import os
import sys

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import backtest_openclose as bo  # noqa: E402


def S(name, pnu, lng=127.0, lat=37.5):
    return bo.Store(name=name, pnu=pnu, lng=lng, lat=lat)


# ── 번호 생긴 연월 ───────────────────────────────────────────────────────────


def test_biz_ym_은_7에서_12자리():
    assert bo.biz_ym("MA0106202201A2069228") == "202201"
    assert bo.biz_ym("MA010120220800800619") == "202208"


# ── 셈법 A: 번호 그대로 ──────────────────────────────────────────────────────


def test_셈법A_앞에만_있으면_사라짐_뒤에만_있으면_새로보임():
    gone, new = bo.diff_by_number({"a", "b", "c"}, {"b", "c", "d", "e"})
    assert gone == ["a"]
    assert new == ["d", "e"]


def test_셈법A_양쪽에_다_있으면_아무데도_안_센다():
    gone, new = bo.diff_by_number({"a", "b"}, {"a", "b"})
    assert gone == [] and new == []
    # 양성 짝: 하나만 빠지면 잡힌다
    gone, new = bo.diff_by_number({"a", "b"}, {"a"})
    assert gone == ["b"] and new == []


# ── 셈법 B: (pnu, 상호명) 재매칭 ─────────────────────────────────────────────


def test_셈법B_pnu와_상호명이_같으면_한_짝():
    gone = {"MA0106202201A0000001": S("가게", "1111")}
    new = {"MA0101202201A0000009": S("가게", "1111")}
    assert bo.rematch(gone, new) == [("MA0106202201A0000001", "MA0101202201A0000009")]


def test_셈법B_pnu_가_다르거나_상호명이_다르면_짝_아님():
    gone = {"G1": S("가게", "1111"), "G2": S("다른가게", "2222")}
    new = {"N1": S("가게", "9999"), "N2": S("다른 가게", "2222")}
    assert bo.rematch(gone, new) == []
    # 양성 짝: 하나를 맞추면 잡힌다
    new["N3"] = S("다른가게", "2222")
    assert bo.rematch(gone, new) == [("G2", "N3")]


def test_셈법B_짝이_여럿이면_생긴_연월이_같은_것_우선():
    gone = {"MA0106202203A0000001": S("가게", "1111")}
    new = {
        "MA0101202201A0000001": S("가게", "1111"),   # 연월 다름 — 번호 순으로는 먼저
        "MA0101202203A0000002": S("가게", "1111"),   # 연월 같음
    }
    assert bo.rematch(gone, new) == [("MA0106202203A0000001", "MA0101202203A0000002")]


def test_셈법B_연월이_같은_것이_없으면_그래도_하나와_짝():
    gone = {"MA0106202203A0000001": S("가게", "1111")}
    new = {
        "MA0101202201A0000001": S("가게", "1111"),
        "MA0101202202A0000002": S("가게", "1111"),
    }
    pairs = bo.rematch(gone, new)
    assert len(pairs) == 1                       # 하나만
    assert pairs[0] == ("MA0106202203A0000001", "MA0101202201A0000001")  # 번호 순 첫째


def test_셈법B_한_가게는_한_번만_짝():
    """앞 2곳 · 뒤 3곳이 같은 (pnu, 상호명) → 짝 2개, 뒤 1곳은 새로 보임으로 남는다."""
    gone = {"MA0106202201A0000001": S("가게", "1111"), "MA0106202202A0000002": S("가게", "1111")}
    new = {
        "MA0101202202A0000001": S("가게", "1111"),
        "MA0101202201A0000002": S("가게", "1111"),
        "MA0101202305A0000003": S("가게", "1111"),
    }
    pairs = bo.rematch(gone, new)
    assert sorted(pairs) == [
        ("MA0106202201A0000001", "MA0101202201A0000002"),
        ("MA0106202202A0000002", "MA0101202202A0000001"),
    ]
    used_new = [n for _, n in pairs]
    assert len(used_new) == len(set(used_new))
    gone_b, new_b = bo.apply_rematch(list(gone), list(new), pairs)
    assert gone_b == []
    assert new_b == ["MA0101202305A0000003"]


def test_셈법B_2차_경로에서도_새로보임은_한_번만_쓰인다():
    """연월이 같은 짝이 없어 둘 다 2차(번호 순 첫째)로 가도, 새로 보임 하나는 한 번만 짝."""
    gone = {"MA0106202201A0000001": S("가게", "1111"), "MA0106202202A0000002": S("가게", "1111")}
    new = {"MA0101202305A0000003": S("가게", "1111")}
    assert bo.rematch(gone, new) == [("MA0106202201A0000001", "MA0101202305A0000003")]


def test_셈법B_1차_경로에서도_새로보임은_한_번만_쓰인다():
    """연월이 같은 사라짐이 둘이어도, 같은 연월 새로 보임 하나는 한 번만 짝."""
    gone = {"MA0106202201A0000001": S("가게", "1111"), "MA0106202201A0000002": S("가게", "1111")}
    new = {"MA0101202201A0000003": S("가게", "1111")}
    assert bo.rematch(gone, new) == [("MA0106202201A0000001", "MA0101202201A0000003")]


def test_셈법B_짝지은_가게는_양쪽에서_함께_제외():
    gone_ids = ["G1", "G2"]
    new_ids = ["N1", "N2"]
    gone_b, new_b = bo.apply_rematch(gone_ids, new_ids, [("G1", "N2")])
    assert gone_b == ["G2"]
    assert new_b == ["N1"]


# ── 좌표 귀속: 사라짐은 앞 사진 · 새로 보임은 뒤 사진 ────────────────────────


def test_parse_coord_는_빈값_숫자아님_0을_좌표없음으로():
    assert bo.parse_coord("127.1", "37.5") == (127.1, 37.5)
    assert bo.parse_coord("", "37.5") is None
    assert bo.parse_coord("abc", "37.5") is None
    assert bo.parse_coord("0", "0") is None


def test_count_by_district_는_배정된_상권마다_세고_겹치면_양쪽():
    assignment = {"a": ("D1",), "b": ("D1", "D2"), "c": ()}
    got = bo.count_by_district(["a", "b", "c", "zz"], assignment)
    assert got == {"D1": 2, "D2": 1}


def test_count_districts_사라짐은_앞사진_좌표_새로보임은_뒤사진_좌표():
    """같은 번호가 아니라도 셈은 각자의 사진 배정을 쓴다 — 배정표를 바꿔 끼우면 결과가 달라진다."""
    before_assign = {"G": ("앞상권",)}
    after_assign = {"N": ("뒤상권",), "G": ("엉뚱",)}
    gone_c, new_c = bo.count_gone_new(["G"], ["N"], before_assign, after_assign)
    assert gone_c == {"앞상권": 1}
    assert new_c == {"뒤상권": 1}


# ── 정답지 읽기 ──────────────────────────────────────────────────────────────


def test_load_official_은_상권별로_업종을_합친다(tmp_path):
    p = tmp_path / "20262_x.jsonl"
    rows = [
        {"TRDAR_CD": "D1", "SVC_INDUTY_CD": "CS1", "STOR_CO": 10.0, "SIMILR_INDUTY_STOR_CO": 12.0,
         "FRC_STOR_CO": 2.0, "OPBIZ_STOR_CO": 1.0, "CLSBIZ_STOR_CO": 2.0},
        {"TRDAR_CD": "D1", "SVC_INDUTY_CD": "CS2", "STOR_CO": 5.0, "SIMILR_INDUTY_STOR_CO": 5.0,
         "FRC_STOR_CO": 0.0, "OPBIZ_STOR_CO": 3.0, "CLSBIZ_STOR_CO": 0.0},
        {"TRDAR_CD": "D2", "SVC_INDUTY_CD": "CS1", "STOR_CO": 1.0, "SIMILR_INDUTY_STOR_CO": 1.0,
         "FRC_STOR_CO": 0.0, "OPBIZ_STOR_CO": 0.0, "CLSBIZ_STOR_CO": 0.0},
    ]
    p.write_text("\n".join(json.dumps({"quarter": "20262", "row": r}) for r in rows), encoding="utf-8")
    off, quarters = bo.load_official(str(p))
    assert quarters == {"20262"}
    assert off["D1"] == {"opbiz": 4, "clsbiz": 2, "stor": 15, "similr": 17}
    assert off["D2"] == {"opbiz": 0, "clsbiz": 0, "stor": 1, "similr": 1}


# ── 비율 집계 ────────────────────────────────────────────────────────────────


def test_ratio_metrics_공식0_상권은_비율에서_빼고_수를_센다():
    ids = ["A", "B", "C", "D"]
    ours = {"A": 10, "B": 5, "C": 7}          # D 는 0
    off = {"A": 10, "B": 10, "C": 0, "D": 4}  # C 는 공식 0
    m = bo.ratio_metrics(ours, off, ids)
    assert m["n_districts"] == 4
    assert m["n_zero_official"] == 1
    assert m["n_ratio"] == 3
    # 비율 = A 1.0 · B 0.5 · D 0.0 → 중앙값 0.5
    assert m["median"] == pytest.approx(0.5)
    assert m["q25"] == pytest.approx(0.25)
    assert m["q75"] == pytest.approx(0.75)
    assert m["within30"] == pytest.approx(1 / 3)
    assert m["total_ours"] == 22 and m["total_official"] == 24
    assert m["total_ratio"] == pytest.approx(22 / 24)


def test_ratio_metrics_공식0이_없으면_0개로_센다():
    m = bo.ratio_metrics({"A": 1}, {"A": 1}, ["A"])
    assert m["n_zero_official"] == 0
    # 양성 짝: 공식 0 상권을 넣으면 1로 잡힌다
    m = bo.ratio_metrics({"A": 1, "B": 3}, {"A": 1, "B": 0}, ["A", "B"])
    assert m["n_zero_official"] == 1
    assert m["n_ratio"] == 1


def test_ratio_metrics_30퍼센트_경계는_안에_든다():
    m = bo.ratio_metrics({"A": 7, "B": 13, "C": 6}, {"A": 10, "B": 10, "C": 10}, ["A", "B", "C"])
    assert m["within30"] == pytest.approx(2 / 3)


def test_ratio_metrics_스피어만은_공식0_상권까지_전부로():
    # 공식 0 인 C 를 빼면 순위가 완전히 같고(ρ=1), 넣으면 어긋난다.
    ours = {"A": 1, "B": 2, "C": 9}
    off = {"A": 1, "B": 2, "C": 0}
    m = bo.ratio_metrics(ours, off, ["A", "B", "C"])
    assert m["spearman"] == pytest.approx(bo.spearman([1, 2, 9], [1, 2, 0]))
    assert m["spearman"] < 0.99


def test_spearman_동순위는_평균순위():
    assert bo.spearman([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)
    assert bo.spearman([1, 2, 3], [30, 20, 10]) == pytest.approx(-1.0)
    # 동순위 — scipy.stats.spearmanr([1,2,2,3],[1,2,3,4]) = 0.9486832980505138
    assert bo.spearman([1, 2, 2, 3], [1, 2, 3, 4]) == pytest.approx(0.9486832980505138)
    assert bo.spearman([5, 5, 5], [1, 2, 3]) is None  # 한쪽이 상수면 정의 안 됨


# ── 성적표: 판정 문구 금지 ───────────────────────────────────────────────────


def test_판정어_찾기_함수는_실제로_잡는다():
    assert bo.find_verdict_words("이 상권은 통과") == ["통과"]
    assert bo.find_verdict_words("불합격입니다") == ["불합격"]
    assert bo.find_verdict_words("합격") == ["합격"]
    assert bo.find_verdict_words("성적만 적는다") == []


def test_성적표에_판정_문구가_없다():
    m = bo.ratio_metrics({"A": 1, "B": 2}, {"A": 2, "B": 2}, ["A", "B"])
    ctx = bo.sample_context_for_tests(m)
    md = bo.build_markdown(ctx)
    assert bo.find_verdict_words(md) == []
    # 머리말 필수 문장(항목 11)
    assert "분기 안 신고 수" in md
    assert "두 사진 사이 사라짐" in md
    assert "서울 화면에는 쓰지 않는다" in md


# ── shapely 가 필요한 시험 ───────────────────────────────────────────────────


def test_상권_배정은_경계_위_점을_빼고_겹치면_양쪽():
    pytest.importorskip("shapely")
    from shapely.geometry import box

    districts = [("D1", box(0, 0, 2, 2)), ("D2", box(1, 1, 3, 3))]
    stores = {
        "in1": S("x", "p", 0.5, 0.5),      # D1 만
        "both": S("x", "p", 1.5, 1.5),     # 겹침 → 양쪽
        "edge": S("x", "p", 2.0, 0.5),     # D1 경계 위 → 안 센다
        "out": S("x", "p", 5.0, 5.0),      # 어디에도 없음
        "nocoord": bo.Store(name="x", pnu="p", lng=None, lat=None),
    }
    assignment, n_no_coord = bo.assign_to_districts(stores, districts)
    assert n_no_coord == 1
    assert assignment["in1"] == ("D1",)
    assert assignment["both"] == ("D1", "D2")
    assert assignment.get("edge", ()) == ()
    assert assignment.get("out", ()) == ()
    assert "nocoord" not in assignment
