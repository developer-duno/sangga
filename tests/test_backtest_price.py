# -*- coding: utf-8 -*-
"""
scripts/backtest_price.py 1:1 단위 테스트 — **순수 함수만** 검사한다.

네트워크·DB 는 한 번도 건드리지 않는다(REST 함수는 이 파일에서 호출하지 않는다).
날짜는 전부 고정 과거 문자열('202512' 등)이라 시간이 흘러도 깨지지 않는다
(글로벌 규칙: 테스트에 미래 날짜 하드코딩 금지).
"""

import math
import os
import sys

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import backtest_price as bt  # noqa: E402


# ── 층대 ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("floor_no,expected", [
    (-3, "지하"),
    (-1, "지하"),
    (1, "1층"),
    (2, "2층"),
    (3, "3층+"),
    (98, "3층+"),
    (99, "옥탑"),
    (100, "3층+"),   # 옥탑 표기(99)를 넘는 값은 3층+로 — 규격 한계는 문서에 박혀 있다
    (None, "층미상"),
])
def test_floor_band_경계(floor_no, expected):
    assert bt.floor_band(floor_no) == expected


def test_floor_band_0은_들어오지_않는다는_전제():
    """절대 규칙 4 — 0은 DB CHECK 로 막혀 있다. 들어와도 3층+로 새지 않는지만 확인."""
    assert bt.floor_band(0) == "3층+"  # 정의상 3~98 가지에 떨어진다(입력 자체가 규격 위반)


# ── 거리 ─────────────────────────────────────────────────────────────────────


def test_haversine_같은_점은_0():
    assert bt.haversine_m(37.5665, 126.9780, 37.5665, 126.9780) == pytest.approx(0.0, abs=1e-6)


def test_haversine_위도_1도는_약_111km():
    """구면 반지름 6371008.8m 기준 위도 1도 = 111,195m. 오차 1% 안."""
    got = bt.haversine_m(0.0, 0.0, 1.0, 0.0)
    assert got == pytest.approx(111_195.0, rel=0.01)


def test_haversine_경도는_위도가_높을수록_짧다():
    """북위 37.5665에서 경도 0.1도 ≒ 111,320 × 0.1 × cos(위도). 오차 1% 안."""
    expected = 111_320.0 * 0.1 * math.cos(math.radians(37.5665))
    got = bt.haversine_m(37.5665, 126.9780, 37.5665, 127.0780)
    assert got == pytest.approx(expected, rel=0.01)


def test_haversine_대칭():
    a = bt.haversine_m(37.5, 127.0, 37.51, 127.01)
    b = bt.haversine_m(37.51, 127.01, 37.5, 127.0)
    assert a == pytest.approx(b)


# ── 중앙값·분위수 ────────────────────────────────────────────────────────────


def test_median_홀수_짝수_빈목록():
    assert bt.median([3.0, 1.0, 2.0]) == 2.0
    assert bt.median([1.0, 2.0, 3.0, 4.0]) == 2.5
    assert bt.median([]) is None


def test_percentile_선형보간():
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert bt.percentile(values, 0.0) == 10.0
    assert bt.percentile(values, 0.5) == 30.0
    assert bt.percentile(values, 1.0) == 50.0
    assert bt.percentile(values, 0.25) == 20.0
    assert bt.percentile([], 0.5) is None
    assert bt.percentile([7.0], 0.99) == 7.0


# ── 오차 산식 ────────────────────────────────────────────────────────────────


def test_ape_기본():
    assert bt.ape(120.0, 100.0) == pytest.approx(0.2)
    assert bt.ape(80.0, 100.0) == pytest.approx(0.2)
    assert bt.ape(100.0, 100.0) == 0.0


def test_ape_셀_수_없는_경우는_None():
    assert bt.ape(None, 100.0) is None
    assert bt.ape(100.0, None) is None
    assert bt.ape(100.0, 0.0) is None       # 0으로 나눌 수 없다


def test_mdape_mape_적중률():
    apes = [0.05, 0.10, 0.30, 0.80]
    assert bt.mdape(apes) == pytest.approx(0.20)          # (0.10+0.30)/2
    assert bt.mape(apes) == pytest.approx(0.3125)
    assert bt.hit_rate(apes) == pytest.approx(0.5)        # 0.05·0.10 두 건이 ±20% 안
    assert bt.mdape([]) is None and bt.mape([]) is None and bt.hit_rate([]) is None


def test_적중률_경계는_이하_포함():
    assert bt.hit_rate([0.20]) == 1.0
    assert bt.hit_rate([0.2000001]) == 0.0


# ── 시간 분할 ────────────────────────────────────────────────────────────────


def _tx(tx_id, ym, pnu="1111011100100010000", floor_no=1, price=1000.0,
        sigungu="11110", lat=None, lng=None):
    return {"tx_id": tx_id, "contract_ym": ym, "pnu": pnu, "floor_no": floor_no,
            "unit_price": price, "sigungu_code": sigungu, "lat": lat, "lng": lng}


def test_split_경계_202512는_학습_202601은_검증():
    rows = [_tx("a", "202511"), _tx("b", "202512"), _tx("c", "202601"), _tx("d", "202602")]
    train, test, outside = bt.split_by_period(rows, "202512", "202601")
    assert [r["tx_id"] for r in train] == ["a", "b"]
    assert [r["tx_id"] for r in test] == ["c", "d"]
    assert outside == []


def test_split_빈틈과_결측은_범위밖():
    rows = [_tx("a", "202412"), _tx("b", "202509"), _tx("c", "202601"), _tx("d", None)]
    train, test, outside = bt.split_by_period(rows, "202506", "202601")
    assert [r["tx_id"] for r in train] == ["a"]
    assert [r["tx_id"] for r in test] == ["c"]
    assert sorted(r["tx_id"] for r in outside) == ["b", "d"]


def test_split_등식_학습더하기검증더하기범위밖은_전체():
    rows = [_tx(str(i), ym) for i, ym in enumerate(
        ["202401", "202512", "202601", None, "202508"])]
    train, test, outside = bt.split_by_period(rows, "202506", "202601")
    assert len(train) + len(test) + len(outside) == len(rows)


# ── PNU 배치 분할 ────────────────────────────────────────────────────────────


def test_chunked_100개씩():
    sizes = [len(c) for c in bt.chunked(range(250), 100)]
    assert sizes == [100, 100, 50]


def test_chunked_딱_떨어지면_한덩어리_남기지_않는다():
    assert [len(c) for c in bt.chunked(range(100), 100)] == [100]
    assert bt.chunked([], 100) == []


def test_chunked_기본값은_PNU_BATCH_100():
    assert bt.PNU_BATCH == 100
    assert [len(c) for c in bt.chunked(range(101))] == [100, 1]


def test_chunked_size가_0이면_거부():
    with pytest.raises(ValueError):
        bt.chunked([1, 2, 3], 0)


# ── 격자 ─────────────────────────────────────────────────────────────────────


def test_grid_key_같은_칸_다른_칸():
    assert bt.grid_key(37.5001, 127.0001, 0.005) == bt.grid_key(37.5020, 127.0020, 0.005)
    assert bt.grid_key(37.5001, 127.0001, 0.005) != bt.grid_key(37.5100, 127.0001, 0.005)


def test_grid_span_500m는_두칸_이상_훑는다():
    """북위 37.5에서 경도 한 칸(0.005도)은 442m뿐 — 500m를 한 칸으로는 못 덮는다."""
    assert bt.grid_span(500.0, 37.5, 0.005) >= 2
    assert bt.grid_span(100.0, 37.5, 0.005) == 1     # 100m는 한 칸이면 충분
    assert bt.grid_span(1.0, 37.5, 0.005) == 1       # 아무리 작아도 최소 1


# ── 단계 성립 최소 표본 ──────────────────────────────────────────────────────


def test_최소표본_상수가_설계대로():
    assert bt.MIN_SAMPLES == {"L2": 1, "L4": 3, "L5": 5, "L6": 1, "BASE": 1}
    assert bt.LADDER == ("L2", "L4", "L5", "L6")     # BASE 는 사다리에 없다


@pytest.mark.parametrize("stage,n_ok,n_bad", [("L2", 1, 0), ("L4", 3, 2), ("L5", 5, 4),
                                              ("L6", 1, 0), ("BASE", 1, 0)])
def test_estimate_from_최소표본_경계(stage, n_ok, n_bad):
    min_n = bt.MIN_SAMPLES[stage]
    bad = bt.estimate_from([100.0] * n_bad, min_n)
    ok = bt.estimate_from([100.0] * n_ok, min_n)
    assert bad["status"] == bt.ST_INSUFFICIENT and bad["estimate"] is None
    assert bad["n"] == n_bad
    assert ok["status"] == bt.ST_OK and ok["estimate"] == 100.0 and ok["n"] == n_ok


def test_estimate_from_추정은_중앙값():
    res = bt.estimate_from([100.0, 200.0, 900.0], 3)
    assert res["estimate"] == 200.0     # 평균(400)이 아니라 중앙값


# ── 사다리 걷기 ──────────────────────────────────────────────────────────────


def _ok(v, n=1):
    return {"status": bt.ST_OK, "estimate": v, "n": n}


def _bad(n=0):
    return {"status": bt.ST_INSUFFICIENT, "estimate": None, "n": n}


def test_사다리는_처음_성립하는_단계를_채택():
    res = {"L2": _ok(10.0), "L4": _ok(20.0), "L5": _ok(30.0), "L6": _ok(40.0)}
    assert bt.walk_ladder(res)[:2] == ("L2", 10.0)


def test_사다리는_미성립_단계를_건너뛴다():
    res = {"L2": _bad(), "L4": _bad(2), "L5": _ok(30.0, 7), "L6": _ok(40.0)}
    assert bt.walk_ladder(res) == ("L5", 30.0, 7)


def test_사다리는_좌표없음도_건너뛴다():
    res = {"L2": _bad(), "L4": bt.coords_missing_result(), "L5": bt.coords_missing_result(),
           "L6": _ok(40.0, 3)}
    assert bt.walk_ladder(res) == ("L6", 40.0, 3)


def test_사다리_전부_미성립이면_no_estimate():
    res = {"L2": _bad(), "L4": _bad(), "L5": _bad(), "L6": _bad()}
    assert bt.walk_ladder(res) == (bt.NO_ESTIMATE, None, 0)


def test_사다리는_BASE를_채택하지_않는다():
    res = {"L2": _bad(), "L4": _bad(), "L5": _bad(), "L6": _bad(), "BASE": _ok(99.0, 50)}
    assert bt.walk_ladder(res)[0] == bt.NO_ESTIMATE


# ── 학습 색인 + 단계 계산 (좌표 처리 포함) ──────────────────────────────────


PNU_A = "1168010100100010000"      # 강남구 역삼동 가정
PNU_B = "1168010100100020000"      # 같은 법정동, 다른 필지
PNU_C = "1168010600100010000"      # 같은 구, 다른 법정동


def _train_rows():
    return [
        _tx("t1", "202501", PNU_A, 1, 1000.0, "11680", 37.5000, 127.0000),
        _tx("t2", "202502", PNU_A, 1, 1200.0, "11680", 37.5000, 127.0000),
        _tx("t3", "202503", PNU_B, 1, 2000.0, "11680", 37.5005, 127.0005),   # 약 70m
        _tx("t4", "202504", PNU_C, 1, 3000.0, "11680", 37.5030, 127.0030),   # 약 420m
        _tx("t5", "202505", PNU_C, 5, 9000.0, "11680", 37.5000, 127.0000),   # 다른 층
    ]


def test_stage_results_좌표_있는_경우():
    index = bt.build_train_index(_train_rows())
    row = _tx("x", "202601", PNU_A, 1, 5000.0, "11680", 37.5000, 127.0000)
    res = bt.stage_results_for(row, index)

    assert res["L2"]["status"] == bt.ST_OK and res["L2"]["n"] == 2
    assert res["L2"]["estimate"] == 1100.0                       # 1000·1200 중앙값
    # 100m 안: t1·t2·t3 (t4는 420m라 밖) → 3건이라 L4 성립
    assert res["L4"]["status"] == bt.ST_OK and res["L4"]["n"] == 3
    assert res["L4"]["estimate"] == 1200.0
    # 500m 안: t1·t2·t3·t4 = 4건 → 최소 5건 미달로 L5 미성립
    assert res["L5"]["status"] == bt.ST_INSUFFICIENT and res["L5"]["n"] == 4
    # 같은 법정동(앞 10자리) 1층대: t1·t2·t3
    assert res["L6"]["status"] == bt.ST_OK and res["L6"]["n"] == 3
    # 같은 구 1층대: t1~t4 (t5는 5층이라 3층+ 층대)
    assert res["BASE"]["status"] == bt.ST_OK and res["BASE"]["n"] == 4


def test_stage_results_좌표_없으면_반경단계는_coords_missing():
    index = bt.build_train_index(_train_rows())
    row = _tx("x", "202601", PNU_A, 1, 5000.0, "11680", None, None)
    res = bt.stage_results_for(row, index)

    assert res["L4"]["status"] == bt.ST_COORDS_MISSING
    assert res["L5"]["status"] == bt.ST_COORDS_MISSING
    assert res["L4"]["estimate"] is None and res["L4"]["n"] == 0
    # 좌표가 없어도 좌표를 안 쓰는 단계는 그대로 돈다
    assert res["L2"]["status"] == bt.ST_OK
    assert res["L6"]["status"] == bt.ST_OK
    assert res["BASE"]["status"] == bt.ST_OK


def test_stage_results_학습에_없는_필지면_L2_미성립():
    index = bt.build_train_index(_train_rows())
    row = _tx("x", "202601", "1168010100109990000", 1, 5000.0, "11680", 37.9, 128.9)
    res = bt.stage_results_for(row, index)
    assert res["L2"]["status"] == bt.ST_INSUFFICIENT and res["L2"]["n"] == 0
    assert res["L5"]["status"] == bt.ST_INSUFFICIENT and res["L5"]["n"] == 0   # 멀어서 후보 0


def test_좌표없는_학습거래는_반경색인에서만_빠진다():
    rows = _train_rows() + [_tx("t6", "202506", PNU_A, 1, 8000.0, "11680", None, None)]
    index = bt.build_train_index(rows)
    row = _tx("x", "202601", PNU_A, 1, 5000.0, "11680", 37.5000, 127.0000)
    res = bt.stage_results_for(row, index)
    assert res["L2"]["n"] == 3          # 좌표 없어도 같은 필지 후보에는 들어간다
    assert res["L4"]["n"] == 3          # 반경 후보에는 안 들어간다


def test_neighbors_within_반경_밖은_버린다():
    index = bt.build_train_index(_train_rows())
    grid = index["floor_grid"].get(1)
    near_100 = bt.neighbors_within(grid, 37.5000, 127.0000, 100.0)
    near_500 = bt.neighbors_within(grid, 37.5000, 127.0000, 500.0)
    assert len(near_100) == 3
    assert len(near_500) == 4
    assert all(d <= 100.0 for d, _ in near_100)


def test_neighbors_within_빈_격자():
    assert bt.neighbors_within(None, 37.5, 127.0, 500.0) == []


# ── 집계 ─────────────────────────────────────────────────────────────────────


def _scored(*apes):
    return [{"a": a} for a in apes]


def test_cell_metrics_커버리지는_미성립까지_센다():
    rows = _scored(0.1, 0.3, None, None)
    m = bt.cell_metrics(rows, lambda r: r["a"])
    assert m["n_total"] == 4 and m["n_est"] == 2
    assert m["coverage"] == pytest.approx(0.5)
    assert m["mdape"] == pytest.approx(0.2)
    assert m["hit20"] == pytest.approx(0.5)


def test_cell_metrics_전부_미성립():
    m = bt.cell_metrics(_scored(None, None), lambda r: r["a"])
    assert m["n_est"] == 0 and m["coverage"] == 0.0
    assert m["mdape"] is None and m["hit20"] is None


def test_paired_metrics_둘다_성립한_거래만_남긴다():
    rows = [
        {"a": 0.10, "b": 0.50},
        {"a": 0.30, "b": 0.10},
        {"a": 0.05, "b": None},     # b 미성립 → 짝에서 빠진다
        {"a": None, "b": 0.05},     # a 미성립 → 짝에서 빠진다
    ]
    p = bt.paired_metrics(rows, lambda r: r["a"], lambda r: r["b"])
    assert p["n_pair"] == 2
    assert p["a_mdape"] == pytest.approx(0.20)
    assert p["b_mdape"] == pytest.approx(0.30)
    assert p["a_hit20"] == pytest.approx(0.5)
    assert p["b_hit20"] == pytest.approx(0.5)


def test_group_by_정렬된_묶음():
    rows = [{"k": "b"}, {"k": "a"}, {"k": "b"}]
    groups = bt.group_by(rows, lambda r: r["k"])
    assert [k for k, _ in groups] == ["a", "b"]
    assert [len(v) for _, v in groups] == [1, 2]


# ── 표기 규칙 (n<5 억제) ─────────────────────────────────────────────────────


def test_n5미만이면_수치를_감춘다():
    assert bt.is_suppressed(4) is True
    assert bt.is_suppressed(5) is False
    assert bt.is_suppressed(0) is True
    assert bt.fmt_metric(4, 0.123) == "표본 부족(4)"
    assert bt.fmt_metric(0, None) == "표본 부족(0)"


def test_n5이상이면_퍼센트로_적는다():
    assert bt.fmt_metric(5, 0.1234) == "12.3%"
    assert bt.fmt_metric(100, None) == "-"


def test_fmt_pct와_fmt_num():
    assert bt.fmt_pct(0.5) == "50.0%"
    assert bt.fmt_pct(None) == "-"
    assert bt.fmt_num(1234567.0) == "1,234,567"
    assert bt.fmt_num(None) == "-"


# ── 분포 보고 (버리지 않는다) ────────────────────────────────────────────────


def test_price_distribution_극단값을_세기만_한다():
    rows = [_tx(str(i), "202501", price=float(i)) for i in range(1, 101)]
    d = bt.price_distribution(rows)
    assert d["n"] == 100
    assert d["min"] == 1.0 and d["max"] == 100.0
    assert d["p50"] == pytest.approx(50.5)
    assert d["nonpositive"] == 0
    assert d["extreme"] >= 1          # p01 미만·p99 초과가 실제로 세어진다


def test_price_distribution_0이하도_보고만():
    rows = [_tx("a", "202501", price=0.0), _tx("b", "202501", price=5.0)]
    d = bt.price_distribution(rows)
    assert d["nonpositive"] == 1
    assert d["n"] == 2                # 버리지 않는다


# ── 금지 표현 (절대 규칙 2) ──────────────────────────────────────────────────


def test_스크립트에_금지표현이_없다():
    path = os.path.join(SCRIPTS_DIR, "backtest_price.py")
    with open(path, encoding="utf-8") as f:
        body = f.read()
    for banned in ("적정가격", "적정가", "평가액", "감정가", "가치평가"):
        assert banned not in body, "금지 표현 발견: {}".format(banned)
