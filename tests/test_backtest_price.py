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
    assert bt.MIN_SAMPLES == {"L2": 1, "L4": 3, "L5": 5, "L6": 1, "L7": 5, "BASE": 1}
    assert bt.LADDER == ("L2", "L4", "L5", "L6")     # BASE 도 L7 도 기본 사다리엔 없다
    # 유형축 모드의 사다리 — L7 은 L5 뒤·L6 앞이다(가까운 근거 먼저, 동네 평균보다는 앞)
    assert bt.LADDER_PLACE == ("L2", "L4", "L5", "L7", "L6")
    assert bt.ALL_STAGES == ("L2", "L4", "L5", "L6", "BASE")   # v1 산출물 칸은 그대로다


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


# ── 출시 기준선 (결정 0013) ──────────────────────────────────────────────────


def test_기준선_상수는_30퍼센트():
    """결정 0013 §2 의 기준선. 바꾸는 것은 사장님 재결재 사항이라 값을 못 박아 둔다."""
    assert bt.GATE_MAX_MDAPE == 0.30


def test_오차가_30퍼센트를_넘으면_탈락():
    """조건 ① 위반 — BASE 를 크게 이겨도 통과가 아니다(예: 구로구 58.7% vs 70.5%)."""
    assert bt.gate_pass(0.587, 0.705) is False
    assert bt.gate_pass(0.3001, 0.9) is False


def test_금천구_케이스_BASE에_지면_탈락():
    """★ 조건 ② — 금천구(11545)는 26.0% 로 ①을 통과하지만 구 평균이 17.6% 로 더 정확하다.

    이미 화면에 있는 구 평균보다 못한 값을 "추정"이라며 얹으면 후퇴다(결정 0013 §2).
    이 한 건이 조건 ②가 존재하는 유일한 이유이므로, 여기서 못을 박아 둔다.
    """
    assert bt.gate_pass(0.259708, 0.175917) is False


def test_둘다_만족하면_통과():
    """중구(11140) 13.7% vs 54.3% · 강서구(11500) 18.0% vs 19.0%(아슬아슬하게 이김)."""
    assert bt.gate_pass(0.136618, 0.542567) is True
    assert bt.gate_pass(0.179945, 0.189993) is True
    assert bt.gate_pass(0.30, 0.31) is True          # 경계 30% 는 "이하"라 통과


def test_비긴_경우는_통과가_아니다():
    """같으면 새 방식을 얹을 이유가 없다 — '이긴다'는 엄격한 부등호다."""
    assert bt.gate_pass(0.25, 0.25) is False


def test_잴_수_없으면_통과가_아니다():
    """짝지은 거래가 0건이면 두 값이 None 이다. 모르면 안 낸다."""
    assert bt.gate_pass(None, 0.2) is False
    assert bt.gate_pass(0.2, None) is False
    assert bt.gate_pass(None, None) is False


def _gate_scored(sigungu_code, ladder_ape, base_ape):
    return {"sigungu_code": sigungu_code, "ladder_ape": ladder_ape,
            "stage_ape": {"BASE": base_ape}}


def test_gate_rows_는_4_1표와_같은_짝짓기를_쓴다():
    """★ 한쪽만 성립한 거래는 짝에서 빠진다 — 표의 n 과 판정의 n 이 같아야 한다."""
    scored = [
        _gate_scored("11680", 0.10, 0.40),
        _gate_scored("11680", 0.20, 0.50),
        _gate_scored("11680", 0.01, None),   # BASE 미성립 → 짝에서 빠진다
        _gate_scored("11545", 0.30, 0.10),
    ]
    rows = bt.gate_rows(scored, {"11680": "강남구"})
    by_code = {r["sigungu_code"]: r for r in rows}
    assert by_code["11680"]["n_paired"] == 2
    assert by_code["11680"]["ladder_mdape"] == pytest.approx(0.15)
    assert by_code["11680"]["base_mdape"] == pytest.approx(0.45)
    assert by_code["11680"]["gate_pass"] is True
    assert by_code["11680"]["sigungu_nm"] == "강남구"
    # 이름표를 못 읽어도 판정은 그대로 나온다(이름은 사람이 읽는 칸일 뿐이다).
    assert by_code["11545"]["sigungu_nm"] == ""
    assert by_code["11545"]["gate_pass"] is False


def test_통과구_CSV_구조(tmp_path):
    path = str(tmp_path / "통과구.csv")
    bt.write_gate_csv(path, [_gate_scored("11680", 0.10, 0.40)], {"11680": "강남구"})
    with open(path, encoding="utf-8-sig") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    assert lines[0] == ("sigungu_code,sigungu_nm,n_paired,"
                        "ladder_mdape,base_mdape,gate_pass")
    assert lines[1].startswith("11680,강남구,1,")
    # 참·거짓은 SQL 리터럴 그대로 적는다(적재기가 그대로 읽는다).
    assert lines[1].endswith(",true")


def test_통과구_CSV_는_판정없는_구도_적는다(tmp_path):
    """탈락 구를 빼 버리면 "왜 안 나오나"를 다음 사람이 성적표를 다시 뽑아야 안다."""
    path = str(tmp_path / "통과구.csv")
    bt.write_gate_csv(path, [_gate_scored("11110", None, None)], {})
    with open(path, encoding="utf-8-sig") as f:
        body = f.read()
    assert "11110,,0,,,false" in body


# ── 금지 표현 (절대 규칙 2) ──────────────────────────────────────────────────


def test_스크립트에_금지표현이_없다():
    path = os.path.join(SCRIPTS_DIR, "backtest_price.py")
    with open(path, encoding="utf-8") as f:
        body = f.read()
    for banned in ("적정가격", "적정가", "평가액", "감정가", "가치평가"):
        assert banned not in body, "금지 표현 발견: {}".format(banned)


# ── 유형축(L7) — 도로등급 · 상권등급 · 9칸 ──────────────────────────────────


@pytest.mark.parametrize("value,expected", [
    # 라이브 실측(2026-08-19) 채점 대상 필지에 실제로 있는 12종
    ("광대로한면", "큰길"),
    ("광대소각", "큰길"),
    ("광대세각", "큰길"),
    ("중로한면", "중간"),
    ("중로각지", "중간"),
    ("소로한면", "중간"),
    ("소로각지", "중간"),
    ("세로한면(가)", "골목길"),
    ("세로한면(불)", "골목길"),
    ("세로각지(가)", "골목길"),
    ("세로각지(불)", "골목길"),
    # 모름으로 두는 것들 — 맹지를 골목길에 밀어 넣으면 그 칸의 성적이 오염된다
    ("맹지", None),
    ("지정되지않음", None),
    ("", None),
    (None, None),
    ("  광대소각  ", "큰길"),      # 앞뒤 공백은 다듬는다
])
def test_road_grade_실제값_전부(value, expected):
    assert bt.road_grade(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("발달상권", "밀집"),
    ("관광특구", "밀집"),
    ("전통시장", "밀집"),
    ("골목상권", "일반상권"),
    ("주요상권", "일반상권"),
    ("역세권", "일반상권"),        # 처음 보는 종류라도 '상권 안'인 것은 참이다
    (None, "상권밖"),
    ("", "상권밖"),
])
def test_district_class_경계(value, expected):
    assert bt.district_class(value) == expected


def test_pick_district_type_겹치면_밀집이_이긴다():
    """관광특구가 발달상권을 덮는 조합은 실재한다 — 더 강한 신호를 고른다."""
    assert bt.pick_district_type(["골목상권", "관광특구"]) == "관광특구"
    assert bt.pick_district_type(["발달상권", "관광특구"]) == "발달상권"   # 순서 고정
    assert bt.pick_district_type(["골목상권", "주요상권"]) == "골목상권"   # 이름 순
    assert bt.pick_district_type([]) is None
    assert bt.pick_district_type(["", None]) is None


@pytest.mark.parametrize("road,dtype,expected", [
    ("광대소각", "발달상권", "큰길·밀집"),
    ("광대소각", "골목상권", "큰길·일반상권"),
    ("광대소각", None, "큰길·상권밖"),
    ("중로각지", "전통시장", "중간·밀집"),
    ("세로한면(가)", None, "골목길·상권밖"),
    ("맹지", "발달상권", None),          # 도로등급을 모르면 칸을 못 정한다
    (None, "발달상권", None),
])
def test_place_type_9칸(road, dtype, expected):
    assert bt.place_type(road, dtype) == expected


def test_place_types_상수는_9칸이고_중복이_없다():
    assert len(bt.PLACE_TYPES) == 9
    assert len(set(bt.PLACE_TYPES)) == 9
    assert bt.PLACE_TYPES[0] == "큰길·밀집"
    assert bt.PLACE_TYPES[-1] == "골목길·상권밖"


# ── 유형축 — 색인·단계·사다리 ───────────────────────────────────────────────


def _ptx(tx_id, ym, pnu, floor_no, price, sigungu, place):
    row = _tx(tx_id, ym, pnu, floor_no, price, sigungu)
    row["place_type"] = place
    return row


def test_L7_색인은_유형없는_학습거래를_뺀다():
    rows = [
        _ptx("t1", "202501", PNU_A, 1, 1000.0, "11680", "큰길·밀집"),
        _ptx("t2", "202502", PNU_B, 1, 2000.0, "11680", "큰길·밀집"),
        _ptx("t3", "202503", PNU_C, 1, 3000.0, "11680", None),      # 유형 모름
    ]
    index = bt.build_train_index(rows)
    assert index["sigungu_place_band"][("11680", "큰길·밀집", "1층")] == [1000.0, 2000.0]
    # 유형을 모르는 거래도 나머지 색인에는 그대로 있다
    assert len(index["sigungu_band"][("11680", "1층")]) == 3


def _l7_train(n, place="큰길·밀집", price=1000.0, band_floor=1):
    return [_ptx("t{}".format(i), "20250{}".format(i % 9 + 1), PNU_A, band_floor,
                 price + i, "11680", place) for i in range(n)]


def test_L7_최소표본_5건_경계():
    row = _ptx("x", "202601", PNU_C, 1, 9999.0, "11680", "큰길·밀집")
    res4 = bt.stage_results_for(row, bt.build_train_index(_l7_train(4)))
    res5 = bt.stage_results_for(row, bt.build_train_index(_l7_train(5)))
    assert res4["L7"]["status"] == bt.ST_INSUFFICIENT and res4["L7"]["n"] == 4
    assert res5["L7"]["status"] == bt.ST_OK and res5["L7"]["n"] == 5
    assert res5["L7"]["estimate"] == 1002.0        # 1000~1004 중앙값


def test_L7_유형을_모르면_place_missing():
    row = _ptx("x", "202601", PNU_C, 1, 9999.0, "11680", None)
    res = bt.stage_results_for(row, bt.build_train_index(_l7_train(5)))
    assert res["L7"]["status"] == bt.ST_PLACE_MISSING
    assert res["L7"]["estimate"] is None and res["L7"]["n"] == 0


def test_L7_다른_유형_다른_층대는_후보가_아니다():
    index = bt.build_train_index(_l7_train(5))
    다른유형 = bt.stage_results_for(
        _ptx("x", "202601", PNU_C, 1, 9999.0, "11680", "골목길·상권밖"), index)
    다른층대 = bt.stage_results_for(
        _ptx("y", "202601", PNU_C, 3, 9999.0, "11680", "큰길·밀집"), index)
    다른구 = bt.stage_results_for(
        _ptx("z", "202601", PNU_C, 1, 9999.0, "11545", "큰길·밀집"), index)
    for res in (다른유형, 다른층대, 다른구):
        assert res["L7"]["status"] == bt.ST_INSUFFICIENT and res["L7"]["n"] == 0


def test_유형_자료를_안_주면_L7은_성립하지_않는다():
    """기본 모드(v1)의 성적이 이 변경 때문에 달라지지 않는다는 보장."""
    raw = [{"tx_id": "a", "contract_ym": "202501", "pnu": PNU_A, "floor_no": 1,
            "unit_price": 1000.0, "sigungu_code": "11680"}]
    rows = bt.normalize_rows(raw, {})
    assert rows[0]["place_type"] is None
    assert rows[0]["road_grade"] is None
    index = bt.build_train_index(rows * 6)
    assert index["sigungu_place_band"] == {}
    res = bt.stage_results_for(rows[0], index)
    assert res["L7"]["status"] == bt.ST_PLACE_MISSING
    assert bt.walk_ladder(res, bt.LADDER_PLACE)[0] == bt.walk_ladder(res, bt.LADDER)[0]


def test_새_사다리는_L5가_되면_L7을_안_쓴다():
    res = {"L2": _bad(), "L4": _bad(), "L5": _ok(30.0, 7), "L7": _ok(70.0, 9), "L6": _ok(40.0)}
    assert bt.walk_ladder(res, bt.LADDER_PLACE) == ("L5", 30.0, 7)


def test_새_사다리는_L5가_안되면_L7을_L6보다_먼저_쓴다():
    res = {"L2": _bad(), "L4": _bad(), "L5": _bad(3), "L7": _ok(70.0, 9), "L6": _ok(40.0)}
    assert bt.walk_ladder(res, bt.LADDER_PLACE) == ("L7", 70.0, 9)
    # 기존 사다리는 같은 재료에서 L6 를 쓴다 — 두 사다리가 갈리는 지점이 여기뿐이다
    assert bt.walk_ladder(res, bt.LADDER) == ("L6", 40.0, 1)


def test_새_사다리도_L7이_안되면_L6으로_내려간다():
    res = {"L2": _bad(), "L4": _bad(), "L5": _bad(), "L7": _bad(2), "L6": _ok(40.0, 3)}
    assert bt.walk_ladder(res, bt.LADDER_PLACE) == ("L6", 40.0, 3)


def test_add_place_ladder_가_두번째_사다리를_붙인다():
    scored = [{
        "unit_price": 100.0, "floor_no": 1,
        "stages": {"L2": _bad(), "L4": _bad(), "L5": _bad(),
                   "L7": _ok(120.0, 6), "L6": _ok(200.0, 3)},
    }]
    bt.add_place_ladder(scored)
    assert scored[0]["place_stage"] == "L7"
    assert scored[0]["place_estimate"] == 120.0 and scored[0]["place_n"] == 6
    assert scored[0]["place_ape"] == pytest.approx(0.20)


def test_add_place_ladder_전부_미성립이면_APE는_None():
    scored = [{"unit_price": 100.0, "floor_no": 1,
               "stages": {"L2": _bad(), "L4": _bad(), "L5": _bad(),
                          "L7": bt.place_missing_result(), "L6": _bad()}}]
    bt.add_place_ladder(scored)
    assert scored[0]["place_stage"] == bt.NO_ESTIMATE
    assert scored[0]["place_estimate"] is None and scored[0]["place_ape"] is None


# ── 유형축 — DB 읽기용 순수 함수 (네트워크 없음) ────────────────────────────


def test_place_context_sql_모양():
    sql = bt.place_context_sql([PNU_A, PNU_B])
    assert "('{}')".format(PNU_A) in sql and "('{}')".format(PNU_B) in sql
    # ⚠️ 캐스트 방향 — 문자 리터럴을 char(19) 로 올려야 기본키 인덱스가 산다
    assert "p.pnu = want.pnu::char(19)" in sql
    # 상권에 안 든 필지도 '상권밖'이라는 정보라 left join 이어야 한다
    assert "left join district" in sql
    assert "st_contains(d.geom, p.geom)" in sql
    assert sql.strip().lower().startswith("with want")


def test_PNU_모양_검사는_19자리_숫자만():
    assert bt.PNU_RE.match(PNU_A)
    assert not bt.PNU_RE.match("111101110010001000")        # 18자리
    assert not bt.PNU_RE.match("1168010100100010000-")      # 기호 섞임
    assert not bt.PNU_RE.match("116801010010001000x")


def test_parse_place_rows_기본():
    got = bt.parse_place_rows([
        [PNU_A, "광대소각", "발달상권|관광특구"],
        [PNU_B, "", ""],
        ["짧은줄"],                                          # 칸이 모자라면 버린다
    ])
    assert got[PNU_A] == {"road_contact": "광대소각",
                          "district_types": ["관광특구", "발달상권"]}
    assert got[PNU_B] == {"road_contact": None, "district_types": []}
    assert len(got) == 2


def test_normalize_rows_유형을_붙인다():
    raw = [{"tx_id": "a", "contract_ym": "202601", "pnu": PNU_A, "floor_no": 1,
            "unit_price": 1000.0, "sigungu_code": "11680"}]
    ctx = {PNU_A: {"road_contact": "광대소각", "district_types": ["골목상권", "관광특구"]}}
    row = bt.normalize_rows(raw, {PNU_A: (37.5, 127.0)}, ctx)[0]
    assert row["road_grade"] == "큰길"
    assert row["district_type"] == "관광특구"      # 겹치면 밀집이 이긴다
    assert row["district_class"] == "밀집"
    assert row["place_type"] == "큰길·밀집"
    assert row["lat"] == 37.5


# ── 유형축 — 집계·산출물 ────────────────────────────────────────────────────


def _scored_place(band_floor, ladder_ape, place_ape, l7_ape=None, base_ape=None,
                  place="큰길·밀집"):
    return {
        "floor_no": band_floor, "unit_price": 100.0,
        "place_type": place, "road_grade": "큰길", "district_class": "밀집",
        "district_types": ["발달상권"], "road_contact": "광대소각",
        "ladder_ape": ladder_ape, "place_ape": place_ape,
        "stage_ape": {"L7": l7_ape, "BASE": base_ape},
        "ladder_stage": "L6", "place_stage": "L7",
    }


def test_place_cell_빈_목록도_죽지_않는다():
    cell = bt.place_cell([])
    assert cell["n_total"] == 0
    assert cell["old"]["mdape"] is None and cell["new"]["mdape"] is None
    assert cell["pair_old"]["n_pair"] == 0


def test_place_cell_기존과_새를_같은_행에서_잰다():
    rows = [_scored_place(1, 0.50, 0.20, l7_ape=0.20, base_ape=0.40),
            _scored_place(1, 0.30, 0.10, l7_ape=0.10, base_ape=0.20),
            _scored_place(1, None, 0.60, l7_ape=0.60, base_ape=None)]
    cell = bt.place_cell(rows)
    assert cell["n_total"] == 3
    assert cell["old"]["n_est"] == 2 and cell["old"]["mdape"] == pytest.approx(0.40)
    assert cell["new"]["n_est"] == 3 and cell["new"]["mdape"] == pytest.approx(0.20)
    # 짝지은 비교는 둘 다 성립한 2건만 본다
    assert cell["pair_old"]["n_pair"] == 2
    assert cell["pair_old"]["a_mdape"] == pytest.approx(0.15)   # 새
    assert cell["pair_old"]["b_mdape"] == pytest.approx(0.40)   # 기존
    assert cell["pair_base"]["n_pair"] == 2


def test_place_key_유형없으면_한_칸으로_모은다():
    assert bt.place_key({"place_type": "큰길·밀집"}) == "큰길·밀집"
    assert bt.place_key({"place_type": None}) == bt.PLACE_NONE_LABEL
    assert bt.place_key({}) == bt.PLACE_NONE_LABEL


def test_place_rows_for_층대와_유형으로_고른다():
    rows = [_scored_place(1, 0.1, 0.1), _scored_place(3, 0.1, 0.1),
            _scored_place(1, 0.1, 0.1, place=None)]
    assert len(bt.place_rows_for(rows, band="1층")) == 2
    assert len(bt.place_rows_for(rows, band="1층", key="큰길·밀집")) == 1
    assert len(bt.place_rows_for(rows, band="1층", key=bt.PLACE_NONE_LABEL)) == 1
    assert len(bt.place_rows_for(rows)) == 3


def test_place_context_stats_이유별로_가른다():
    rows = [
        _scored_place(1, 0.1, 0.1),                                   # 유형 있음
        dict(_scored_place(1, 0.1, 0.1), place_type=None, road_grade=None,
             road_contact="맹지", district_class="상권밖"),           # 필지는 있는데 도로 모름
        dict(_scored_place(1, 0.1, 0.1), place_type=None, road_grade=None,
             road_contact=None, district_class=None, district_types=[]),  # 필지 자체가 없음
    ]
    stats = bt.place_context_stats(rows)
    assert stats == {"n": 3, "typed": 1, "no_parcel": 1, "no_road": 1}


def test_유형별_CSV_구조(tmp_path):
    path = str(tmp_path / "1층유형별지표.csv")
    rows = [_scored_place(1, 0.50, 0.20, l7_ape=0.20, base_ape=0.40)] * 2
    bt.write_place_csv(path, rows)
    with open(path, encoding="utf-8-sig") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    assert lines[0].split(",")[:5] == ["층대", "유형", "도로등급", "상권등급", "검증거래수"]
    assert any(ln.startswith("1층,큰길·밀집,큰길,밀집,2,") for ln in lines)
    # 합계 줄은 축 칸을 비워 둔다(엑셀에서 도로등급으로 거를 때 섞이면 안 된다)
    assert any(ln.startswith("전체,합계,,,2,") for ln in lines)


def test_유형축_문서가_렌더된다():
    """서식 문자열이 깨지지 않는지 — 작은 표본으로 한 번 돌려 본다."""
    raw = [{"tx_id": "t{}".format(i), "contract_ym": "202505", "pnu": PNU_A,
            "floor_no": 1, "unit_price": 1000.0 + i, "sigungu_code": "11680"}
           for i in range(6)]
    raw.append({"tx_id": "x", "contract_ym": "202601", "pnu": PNU_C, "floor_no": 1,
                "unit_price": 1500.0, "sigungu_code": "11680"})
    ctx_place = {PNU_A: {"road_contact": "광대소각", "district_types": ["발달상권"]},
                 PNU_C: {"road_contact": "광대소각", "district_types": ["발달상권"]}}
    rows = bt.normalize_rows(raw, {}, ctx_place)
    train, test, _ = bt.split_by_period(rows, "202512", "202601")
    scored = bt.add_place_ladder(
        bt.score_test_rows(test, bt.build_train_index(train)))
    md = bt.build_place_markdown({
        "scored": scored,
        "stats": bt.place_context_stats(test),
        "facts": bt.build_place_facts(scored),
        "one_line": bt.place_one_line(scored),
        "train_until": "202512", "test_from": "202601",
        "generated_at": "2026-08-19 12:00",
    })
    assert "L7" in md and "큰길·밀집" in md
    assert "1층" in md and "판단 재료" in md
    # 채택 단계가 L7 이어야 한다(같은 필지가 아니고 좌표가 없어 L2·L4·L5 가 다 미성립).
    # 법정동까지 다르므로 L6 도 안 되던 거래다 — 기존 사다리는 값을 아예 못 냈다.
    assert scored[0]["place_stage"] == "L7"
    assert scored[0]["ladder_stage"] == bt.NO_ESTIMATE
