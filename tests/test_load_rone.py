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
