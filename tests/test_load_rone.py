# -*- coding: utf-8 -*-
"""
scripts/collectors/load_rone.py 단위 테스트

라이브 Supabase 없이 검증한다:
  1. build_name_lookup            — {GRP_NM: GRP_ID} 조회표 + 이름 충돌 감지
  2. api_quarter_to_db_quarter    — '202602' -> '2026Q2', 이상 형식은 None
  3. build_floor_util_ratio       — null 키 생략 / '임대료' 행 배제
  4. resolve_region_code          — 이름 매칭·미매칭
  5. build_metric_by_region       — yield는 '투자수익률'만 채택
  6. merge_metrics                — 부분 병합(일부 지표 없어도 나머지는 채워짐)
  7. assert_unique                — rent_stat 복합 PK 중복 방지
  8. parse_args

conftest.py를 새로 만들지 않기 위해 sys.path 조작은 이 파일 안에서만 한다.
"""

import os
import sys

import pytest

_COLLECTORS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "collectors",
)
_SCRIPTS_DIR = os.path.dirname(_COLLECTORS_DIR)
for _p in (_SCRIPTS_DIR, _COLLECTORS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import load_rone as target  # noqa: E402


# ── 픽스처 ────────────────────────────────────────────────────────────────────

FU_GANGNAM_1F = {"GRP_ID": "1168000000", "GRP_NM": "강남", "GRP_FULLNM": "서울>강남",
                 "CLS_NM": "1층", "ITM_NM": "효용비율", "DTA_VAL": "100.0"}
FU_GANGNAM_B1 = {"GRP_ID": "1168000000", "GRP_NM": "강남", "GRP_FULLNM": "서울>강남",
                 "CLS_NM": "지하1층", "ITM_NM": "효용비율", "DTA_VAL": "40.9"}
FU_GANGNAM_RENT_1F = {"GRP_ID": "1168000000", "GRP_NM": "강남", "GRP_FULLNM": "서울>강남",
                      "CLS_NM": "1층", "ITM_NM": "임대료", "DTA_VAL": "54.11"}
FU_GANGNAM_NULLVAL = {"GRP_ID": "1168000000", "GRP_NM": "강남", "GRP_FULLNM": "서울>강남",
                      "CLS_NM": "3층", "ITM_NM": "효용비율", "DTA_VAL": None}

FU_TEHERAN_1F = {"GRP_ID": "1168000001", "GRP_NM": "테헤란로", "GRP_FULLNM": "서울>강남>테헤란로",
                 "CLS_NM": "1층", "ITM_NM": "효용비율", "DTA_VAL": "74.6"}

REGION_RENT_GANGNAM = {"CLS_NM": "강남", "ITM_NM": "임대료", "DTA_VAL": "54.11"}
VACANCY_GANGNAM = {"CLS_NM": "강남", "ITM_NM": "공실률", "DTA_VAL": "3.2"}
YIELD_GANGNAM_OK = {"CLS_NM": "강남", "ITM_NM": "투자수익률", "DTA_VAL": "4.5"}
YIELD_GANGNAM_OTHER = {"CLS_NM": "강남", "ITM_NM": "소득수익률", "DTA_VAL": "99.9"}
REGION_RENT_UNKNOWN = {"CLS_NM": "존재하지않는상권", "ITM_NM": "임대료", "DTA_VAL": "10.0"}


# ── 1. build_name_lookup ─────────────────────────────────────────────────────


def test_build_name_lookup_maps_name_to_id():
    lookup, conflicts = target.build_name_lookup([FU_GANGNAM_1F, FU_TEHERAN_1F])
    assert lookup == {"강남": "1168000000", "테헤란로": "1168000001"}
    assert not conflicts


def test_build_name_lookup_flags_conflicting_ids_without_crashing():
    """같은 이름·다른 GRP_ID가 나오면 죽이지 않고 conflicts에 기록만 한다."""
    conflicting = dict(FU_GANGNAM_1F, GRP_ID="9999999999")
    lookup, conflicts = target.build_name_lookup([FU_GANGNAM_1F, conflicting])
    assert lookup["강남"] == "1168000000", "먼저 온 값을 유지한다"
    assert conflicts["강남"] == 1


def test_build_name_lookup_skips_blank_name_or_id():
    rows = [dict(FU_GANGNAM_1F, GRP_NM=""), dict(FU_GANGNAM_1F, GRP_ID=None)]
    lookup, _ = target.build_name_lookup(rows)
    assert lookup == {}


# ── 2. api_quarter_to_db_quarter ─────────────────────────────────────────────


@pytest.mark.parametrize("api_qid,expected", [
    ("202602", "2026Q2"), ("202403", "2024Q3"), ("202601", "2026Q1"), ("202604", "2026Q4"),
])
def test_api_quarter_to_db_quarter_normal(api_qid, expected):
    assert target.api_quarter_to_db_quarter(api_qid) == expected


@pytest.mark.parametrize("bad", ["2026", "2026-02", "202600", "202605", "abcdef", None, ""])
def test_api_quarter_to_db_quarter_bad_format_is_none(bad):
    assert target.api_quarter_to_db_quarter(bad) is None


# ── 3. build_floor_util_ratio ────────────────────────────────────────────────


def test_build_floor_util_ratio_maps_buckets():
    out = target.build_floor_util_ratio([FU_GANGNAM_1F, FU_GANGNAM_B1])
    assert out == {"1": 100.0, "-1": 40.9}


def test_build_floor_util_ratio_excludes_rent_rows():
    """ITM_NM='임대료' 행은 버린다 — floor_util_ratio 컬럼은 비율 전용이다."""
    out = target.build_floor_util_ratio([FU_GANGNAM_1F, FU_GANGNAM_RENT_1F])
    assert out == {"1": 100.0}


def test_build_floor_util_ratio_omits_null_value_key():
    """DTA_VAL이 null이면 그 층 키 자체를 만들지 않는다(0도 None 키도 아니고 부재)."""
    out = target.build_floor_util_ratio([FU_GANGNAM_1F, FU_GANGNAM_NULLVAL])
    assert out == {"1": 100.0}
    assert "3" not in out


def test_build_floor_util_ratio_empty_when_no_matching_rows():
    assert target.build_floor_util_ratio([]) == {}


# ── 4. resolve_region_code / build_floor_util_by_region ─────────────────────


def test_resolve_region_code_matches_by_name():
    lookup, _ = target.build_name_lookup([FU_GANGNAM_1F])
    assert target.resolve_region_code("강남", lookup) == "1168000000"


def test_resolve_region_code_unmatched_is_none():
    lookup, _ = target.build_name_lookup([FU_GANGNAM_1F])
    assert target.resolve_region_code("존재하지않는상권", lookup) is None


def test_build_floor_util_by_region_groups_by_grp_id():
    out = target.build_floor_util_by_region([FU_GANGNAM_1F, FU_GANGNAM_B1, FU_TEHERAN_1F])
    assert set(out.keys()) == {"1168000000", "1168000001"}
    assert out["1168000000"]["region_nm"] == "서울>강남"
    assert out["1168000000"]["floor_util_ratio"] == {"1": 100.0, "-1": 40.9}
    assert out["1168000001"]["floor_util_ratio"] == {"1": 74.6}


# ── 5. build_metric_by_region — yield는 '투자수익률'만 채택 ─────────────────


def test_build_metric_by_region_resolves_named_regions():
    lookup, _ = target.build_name_lookup([FU_GANGNAM_1F])
    by_region, unmatched = target.build_metric_by_region([REGION_RENT_GANGNAM], lookup)
    assert by_region == {"1168000000": 54.11}
    assert not unmatched


def test_build_metric_by_region_counts_unmatched_names():
    lookup, _ = target.build_name_lookup([FU_GANGNAM_1F])
    by_region, unmatched = target.build_metric_by_region([REGION_RENT_UNKNOWN], lookup)
    assert by_region == {}
    assert unmatched["존재하지않는상권"] == 1


def test_build_metric_by_region_yield_accepts_only_investment_return_item():
    """yield 표에 다른 지표(소득수익률 등)가 섞여도 '투자수익률'만 채택한다."""
    lookup, _ = target.build_name_lookup([FU_GANGNAM_1F])
    by_region, _ = target.build_metric_by_region(
        [YIELD_GANGNAM_OK, YIELD_GANGNAM_OTHER], lookup, item_name=target.YIELD_ITEM_NAME)
    assert by_region == {"1168000000": 4.5}


def test_extract_metric_value_filters_by_item_name():
    assert target.extract_metric_value(YIELD_GANGNAM_OK, item_name="투자수익률") == 4.5
    assert target.extract_metric_value(YIELD_GANGNAM_OTHER, item_name="투자수익률") is None
    assert target.extract_metric_value(REGION_RENT_GANGNAM) == 54.11  # 필터 없으면 그대로


# ── 6. merge_metrics — 부분 병합 ─────────────────────────────────────────────


def test_merge_metrics_combines_all_metrics_for_a_region():
    per_metric = {
        "floor_util": {"1168000000": {"region_nm": "서울>강남", "floor_util_ratio": {"1": 100.0}}},
        "region_rent": {"1168000000": 54.11},
        "vacancy": {"1168000000": 3.2},
        "rent_price_index": {"1168000000": 101.5},
        "yield": {"1168000000": 4.5},
        "conversion": {"1168000000": 5.1},
    }
    records = target.merge_metrics("202602", "집합상가", per_metric)
    assert len(records) == 1
    r = records[0]
    assert r["quarter"] == "2026Q2" and r["region_code"] == "1168000000"
    assert r["bld_type"] == "집합상가" and r["region_nm"] == "서울>강남"
    assert r["rent_per_m2"] == 54.11 and r["vacancy_rate"] == 3.2
    assert r["rent_price_index"] == 101.5 and r["yield_rate"] == 4.5
    assert r["conversion_rate"] == 5.1
    assert r["floor_util_ratio"] == {"1": 100.0}


def test_merge_metrics_allows_partial_data_missing_metric_becomes_null():
    """일부 지표가 없어도(quiet-zero·미매칭) 그 컬럼만 NULL, 나머지는 채워진다."""
    per_metric = {
        "floor_util": {"1168000000": {"region_nm": "서울>강남", "floor_util_ratio": {"1": 100.0}}},
        "region_rent": {"1168000000": 54.11},
        "vacancy": {},          # 이번 분기는 공실률 quiet-zero
        "rent_price_index": {},
        "yield": {},
        "conversion": {},
    }
    records = target.merge_metrics("202602", "집합상가", per_metric)
    r = records[0]
    assert r["rent_per_m2"] == 54.11
    assert r["vacancy_rate"] is None
    assert r["rent_price_index"] is None
    assert r["yield_rate"] is None
    assert r["conversion_rate"] is None


def test_merge_metrics_includes_region_only_present_in_non_floor_metric():
    """floor_util에 없는 지역이 다른 지표에만 있어도 행을 만든다(region_nm만 None)."""
    per_metric = {
        "floor_util": {},
        "region_rent": {"9999999999": 10.0},
        "vacancy": {}, "rent_price_index": {}, "yield": {}, "conversion": {},
    }
    records = target.merge_metrics("202602", "집합상가", per_metric)
    assert len(records) == 1
    assert records[0]["region_code"] == "9999999999"
    assert records[0]["region_nm"] is None
    assert records[0]["floor_util_ratio"] is None


def test_merge_metrics_bad_quarter_format_returns_empty():
    records = target.merge_metrics("2026Q2", "집합상가", {"floor_util": {"X": {}}})
    assert records == []


def test_merge_metrics_empty_floor_util_ratio_becomes_null_not_empty_dict():
    per_metric = {
        "floor_util": {"1168000000": {"region_nm": "서울>강남", "floor_util_ratio": {}}},
        "region_rent": {}, "vacancy": {}, "rent_price_index": {}, "yield": {}, "conversion": {},
    }
    records = target.merge_metrics("202602", "집합상가", per_metric)
    assert records[0]["floor_util_ratio"] is None


# ── 7. assert_unique ─────────────────────────────────────────────────────────


def test_assert_unique_passes_when_all_distinct():
    records = [
        {"quarter": "2026Q2", "region_code": "A", "bld_type": "집합상가"},
        {"quarter": "2026Q2", "region_code": "B", "bld_type": "집합상가"},
        {"quarter": "2026Q2", "region_code": "A", "bld_type": "오피스"},
    ]
    assert target.assert_unique(records) == 3


def test_assert_unique_raises_on_pk_collision():
    records = [
        {"quarter": "2026Q2", "region_code": "A", "bld_type": "집합상가"},
        {"quarter": "2026Q2", "region_code": "A", "bld_type": "집합상가"},
    ]
    with pytest.raises(RuntimeError, match="중복"):
        target.assert_unique(records)


# ── 8. latest_batch / read_jsonl / raw_path ─────────────────────────────────


def test_raw_path_matches_collect_rone_layout(tmp_path):
    p = target.raw_path(str(tmp_path), "집합상가", "floor_util")
    assert p.endswith(os.path.join("jiphap", "floor_util.jsonl"))


def test_latest_batch_keeps_newest_per_combo():
    rows = [
        {"bld_type": "집합상가", "metric": "floor_util", "quarter_id": "202602",
         "fetched_at": "2026-08-01T00:00:00", "row": {"DTA_VAL": "old"}},
        {"bld_type": "집합상가", "metric": "floor_util", "quarter_id": "202602",
         "fetched_at": "2026-08-08T00:00:00", "row": {"DTA_VAL": "new"}},
    ]
    out = target.latest_batch(rows)
    assert len(out) == 1 and out[0]["row"]["DTA_VAL"] == "new"


def test_read_jsonl_missing_file_returns_empty(tmp_path):
    rows, broken = target.read_jsonl(str(tmp_path / "없음.jsonl"))
    assert rows == [] and broken == 0


def test_read_jsonl_skips_broken_lines(tmp_path):
    path = tmp_path / "x.jsonl"
    path.write_text('{"a":1}\n이건 json이 아님\n{"b":2}\n', encoding="utf-8")
    rows, broken = target.read_jsonl(str(path))
    assert len(rows) == 2 and broken == 1


# ── 9. parse_args ─────────────────────────────────────────────────────────────


def test_parse_args_defaults():
    o = target.parse_args([])
    assert o["bld_type"] is None and o["dry_run"] is False
    assert o["raw_dir"].endswith(os.path.join("data", "raw", "rone"))


def test_parse_args_overrides():
    o = target.parse_args(["--bld-type", "오피스", "--dry-run"])
    assert o["bld_type"] == "오피스" and o["dry_run"] is True


def test_parse_args_rejects_unknown_bld_type():
    with pytest.raises(ValueError, match="--bld-type"):
        target.parse_args(["--bld-type", "아파트"])


def test_parse_args_rejects_unknown_flag():
    with pytest.raises(ValueError, match="알 수 없는 인자"):
        target.parse_args(["--help"])


def test_parse_args_missing_value():
    with pytest.raises(ValueError, match="뒤에 값이 필요"):
        target.parse_args(["--bld-type"])


# ── 10. 층별 임대료·소득수익률 (결정 0031) ──────────────────────────────────────
#
# floor_util 원본의 '임대료' 줄을 floor_rent 로, yield 원본의 '소득수익률' 줄을
# income_yield_rate 로 담는다. ⛔ 효용비율(floor_util_ratio)은 글자 그대로 불변이어야 한다.


def _fu(cls_nm, itm_nm, val, gid="1168000001", nm="테헤란로", full="서울>강남>테헤란로"):
    return {"GRP_ID": gid, "GRP_NM": nm, "GRP_FULLNM": full,
            "CLS_NM": cls_nm, "ITM_NM": itm_nm, "DTA_VAL": val}


def test_build_floor_rent_takes_rent_rows_only_and_rounds_to_two_places():
    rows = [
        _fu("지하1층", "임대료", 16.9512),
        _fu("1층", "임대료", 74.596956),
        _fu("6층이상", "임대료", "22.7"),
        _fu("1층", "효용비율", 100.0),        # 효용비율 줄은 floor_rent 에 안 들어온다
    ]
    out = target.build_floor_rent(rows)
    assert out == {"-1": 16.95, "1": 74.6, "6+": 22.7}


@pytest.mark.parametrize("bad", [0, 0.0, "0", -3.2, "-0.01", None, "", "  ", "abc", "nan", "inf"])
def test_build_floor_rent_makes_no_key_for_zero_negative_blank_or_non_number(bad):
    """0 은 임대료가 아니라 '조사값 없음'이다 — 열쇠 자체를 만들지 않는다(소규모 지하1층 66행)."""
    out = target.build_floor_rent([_fu("1층", "임대료", 52.46), _fu("지하1층", "임대료", bad)])
    assert out == {"1": 52.46}
    assert "-1" not in out


def test_build_floor_rent_empty_when_every_value_is_missing():
    assert target.build_floor_rent([_fu("지하1층", "임대료", 0), _fu("1층", "임대료", None)]) == {}


def test_build_floor_rent_keeps_the_two_office_buckets():
    rows = [_fu("5층", "임대료", 26.51), _fu("6-10층", "임대료", 26.73), _fu("11층이상", "임대료", 28.62)]
    assert target.build_floor_rent(rows) == {"5": 26.51, "6-10": 26.73, "11+": 28.62}


def test_floor_rent_bucket_key_unknown_is_none():
    assert target.floor_rent_bucket_key("지하2층") is None
    assert target.floor_rent_bucket_key("옥탑") is None
    assert target.floor_rent_bucket_key(None) is None


def test_the_ratio_bucket_map_was_not_widened():
    """⛔ 오피스 두 구간은 임대료 쪽에만 있다 — 효용비율 대응표가 넓어지면 floor_util_ratio 가 바뀐다."""
    from collect_rone import floor_bucket_key
    assert floor_bucket_key("6-10층") is None
    assert floor_bucket_key("11층이상") is None
    rows = [_fu("1층", "효용비율", 100.0), _fu("6-10층", "효용비율", 68.5), _fu("11층이상", "효용비율", 73.4)]
    assert target.build_floor_util_ratio(rows) == {"1": 100.0}


def test_build_floor_util_by_region_carries_rent_without_touching_the_ratio():
    rows = [_fu("1층", "효용비율", 100.0), _fu("2층", "효용비율", 43.5),
            _fu("1층", "임대료", 74.6), _fu("2층", "임대료", 32.48)]
    out = target.build_floor_util_by_region(rows)["1168000001"]
    assert out["floor_util_ratio"] == {"1": 100.0, "2": 43.5}
    assert out["floor_rent"] == {"1": 74.6, "2": 32.48}
    # 임대료 줄이 없을 때와 효용비율 결과가 같다(글자 그대로 불변).
    ratio_only = target.build_floor_util_by_region(rows[:2])["1168000001"]["floor_util_ratio"]
    assert out["floor_util_ratio"] == ratio_only


def test_income_and_investment_yield_go_to_different_columns():
    lookup, _ = target.build_name_lookup([FU_GANGNAM_1F])
    rows = [YIELD_GANGNAM_OK, YIELD_GANGNAM_OTHER]
    invest, _ = target.build_metric_by_region(rows, lookup, item_name=target.YIELD_ITEM_NAME)
    income, _ = target.build_metric_by_region(rows, lookup, item_name=target.INCOME_YIELD_ITEM_NAME)
    assert invest == {"1168000000": 4.5}
    assert income == {"1168000000": 99.9}

    per_metric = {
        "floor_util": {"1168000000": {"region_nm": "서울>강남", "floor_util_ratio": {"1": 100.0},
                                      "floor_rent": {"1": 54.11}}},
        "region_rent": {}, "vacancy": {}, "rent_price_index": {}, "conversion": {},
        "yield": invest,
        target.INCOME_YIELD_METRIC: income,
    }
    r = target.merge_metrics("202602", "집합상가", per_metric)[0]
    assert r["yield_rate"] == 4.5
    assert r["income_yield_rate"] == 99.9
    assert r["floor_rent"] == {"1": 54.11}


def test_merge_metrics_every_record_has_the_same_keys():
    """묶음 upsert 는 줄마다 칸이 다르면 실패한다 — 값이 없어도 열쇠는 있어야 한다(None)."""
    per_metric = {
        "floor_util": {
            "A": {"region_nm": "a", "floor_util_ratio": {"1": 100.0}, "floor_rent": {"1": 50.0}},
            "B": {"region_nm": "b", "floor_util_ratio": {}, "floor_rent": {}},
        },
        "region_rent": {"C": 10.0},       # floor_util 에 없는 지역
        "vacancy": {}, "rent_price_index": {}, "yield": {}, "conversion": {},
        target.INCOME_YIELD_METRIC: {"A": 0.9, "D": 0.4},   # 소득수익률에만 있는 지역도 행을 만든다
    }
    records = target.merge_metrics("202602", "집합상가", per_metric)
    assert [r["region_code"] for r in records] == ["A", "B", "C", "D"]
    assert len({tuple(sorted(r)) for r in records}) == 1
    assert {"floor_rent", "income_yield_rate"} <= set(records[0])
    by = {r["region_code"]: r for r in records}
    assert by["B"]["floor_rent"] is None, "빈 사전은 None — 빈 jsonb 를 싣지 않는다"
    assert by["C"]["floor_rent"] is None and by["C"]["income_yield_rate"] is None
    assert by["D"]["income_yield_rate"] == 0.4


def test_merge_metrics_without_income_slice_still_has_the_column():
    """옛 호출(소득수익률 조각 없음)도 깨지지 않고 칸은 None 으로 선다."""
    per_metric = {
        "floor_util": {"A": {"region_nm": "a", "floor_util_ratio": {"1": 100.0}}},
        "region_rent": {}, "vacancy": {}, "rent_price_index": {}, "yield": {}, "conversion": {},
    }
    r = target.merge_metrics("202602", "집합상가", per_metric)[0]
    assert r["floor_rent"] is None and r["income_yield_rate"] is None


def test_fill_counts():
    records = [
        {"floor_rent": {"1": 1.0}, "income_yield_rate": 0.5},
        {"floor_rent": None, "income_yield_rate": None},
        {"floor_rent": None, "income_yield_rate": 0.0},     # 0.0 도 '채움'이다(값이 있다)
    ]
    assert target.fill_counts(records) == (1, 2)


# ── 11. main — 새 칸이 비면 종료코드 1 ─────────────────────────────────────────


def _write_raw(raw_dir, bld_type, metric, rows, quarter="202602"):
    import json
    path = target.raw_path(str(raw_dir), bld_type, metric)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps({"bld_type": bld_type, "metric": metric, "quarter_id": quarter,
                                 "fetched_at": "2026-08-09T00:00:00", "row": row},
                                ensure_ascii=False) + "\n")


def _run_main(monkeypatch, raw_dir):
    monkeypatch.setattr(sys, "argv", ["load_rone.py", "--dry-run", "--bld-type", "집합상가",
                                      "--raw-dir", str(raw_dir)])
    return target.main()


def _seed(raw_dir, rent_item="임대료", income_item="소득수익률"):
    _write_raw(raw_dir, "집합상가", "floor_util",
               [_fu("1층", "효용비율", 100.0), _fu("1층", rent_item, 74.6)])
    _write_raw(raw_dir, "집합상가", "yield",
               [{"CLS_NM": "테헤란로", "ITM_NM": "투자수익률", "DTA_VAL": 1.9},
                {"CLS_NM": "테헤란로", "ITM_NM": income_item, "DTA_VAL": 0.9}])


def test_main_returns_0_when_both_new_columns_are_filled(monkeypatch, tmp_path, capsys):
    """양성 대조 — 아래 두 시험의 1 이 '무조건 1'이 아님을 보인다."""
    _seed(tmp_path)
    assert _run_main(monkeypatch, tmp_path) == 0
    assert "층별 임대료 채움 1행 · 소득수익률 채움 1행" in capsys.readouterr().out


def test_main_returns_1_when_floor_rent_is_empty(monkeypatch, tmp_path):
    """항목 이름 철자가 틀리면 그 칸이 통째로 빈다 — 미리보기에서도 멈춰야 한다."""
    _seed(tmp_path, rent_item="임대료(오타)")
    assert _run_main(monkeypatch, tmp_path) == 1


def test_main_returns_1_when_income_yield_is_empty(monkeypatch, tmp_path):
    _seed(tmp_path, income_item="소득 수익률")
    assert _run_main(monkeypatch, tmp_path) == 1


def test_process_bld_type_puts_each_yield_in_its_own_column(tmp_path):
    """원본 → 레코드 끝까지: 투자수익률은 yield_rate, 소득수익률은 income_yield_rate(서로 바뀌지 않는다)."""
    _seed(tmp_path)
    records, stats, _ = target.process_bld_type(str(tmp_path), "집합상가")
    assert len(records) == 1
    r = records[0]
    assert r["yield_rate"] == 1.9
    assert r["income_yield_rate"] == 0.9
    assert r["floor_rent"] == {"1": 74.6}
    assert r["floor_util_ratio"] == {"1": 100.0}
    assert (stats["floor_rent_filled"], stats["income_yield_filled"]) == (1, 1)
