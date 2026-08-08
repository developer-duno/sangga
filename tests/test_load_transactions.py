# -*- coding: utf-8 -*-
"""
scripts/collectors/load_transactions.py 단위 테스트

라이브 API·Supabase 없이 검증한다:
  1. s / to_int / to_float   — 같은 필드가 str·int·float로 섞여 오는 실측 대응
  2. parse_deal_amount       — 만원 단위 콤마 문자열 -> 원 (틀리면 시세가 1만분의 1)
  3. normalize_floor         — 지하 음수 그대로, 0은 절대 안 만든다
  4. split_jibun / make_pnu  — 지번 -> PNU 19자리, 마스킹은 조립 불가
  5. build_emd_lookup        — 폐지 코드보다 현행 코드 우선
  6. make_tx_id              — 같은 raw면 같은 값, 같은 조합이 여럿이면 seq로 가른다
  7. build_transaction(s)    — 필드 매핑·해제 제외·조합 중복 처리
  8. latest_batch            — 재수집으로 쌓인 옛 배치 제거
  9. assert_* / parse_args

conftest.py를 새로 만들지 않기 위해 sys.path 조작은 이 파일 안에서만 한다.
"""

import json
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

import load_transactions as target  # noqa: E402


# ── 픽스처 (2026-08-08 라이브 실측 값 그대로) ────────────────────────────────

ITEM = {
    "buildYear": 1993, "buildingAr": 28.8, "buildingType": "집합",
    "buildingUse": "제1종근린생활", "cdealDay": " ", "cdealType": " ",
    "dealAmount": "136,000", "dealDay": 25, "dealMonth": 6, "dealYear": 2026,
    "floor": 1, "jibun": "716", "landUse": "제3종일반주거",
    "plottageAr": " ", "sggCd": 11680, "umdNm": "일원동",
}
EMD = {"일원동": "1168010800", "역삼동": "1168010100"}


def raw(item, deal_ym="202606", fetched_at="2026-08-08T00:00:00+09:00"):
    return {"sigungu_code": "11680", "deal_ym": deal_ym,
            "fetched_at": fetched_at, "item": item}


# ── 1. 타입 정규화 (JSON이 같은 필드를 str·int·float로 섞어 준다) ────────────


@pytest.mark.parametrize("raw_v,expected", [
    (716, "716"), ("716", "716"), (" 716 ", "716"), (None, ""), (28.8, "28.8"),
])
def test_s_normalizes_any_type(raw_v, expected):
    assert target.s(raw_v) == expected


def test_to_int_handles_str_int_and_commas():
    assert target.to_int("1,234") == 1234
    assert target.to_int(1234) == 1234
    assert target.to_int("28.8") == 28
    assert target.to_int("") is None and target.to_int(None) is None
    assert target.to_int("없음") is None


def test_to_float_handles_blank_and_text():
    assert target.to_float(28.8) == 28.8
    assert target.to_float("28.8") == 28.8
    assert target.to_float(" ") is None
    assert target.to_float("x") is None


# ── 2. 거래금액 ──────────────────────────────────────────────────────────────


def test_parse_deal_amount_converts_man_won_to_won():
    """'136,000'은 13.6억이다 — 만원을 안 곱하면 금액이 1만분의 1이 된다."""
    assert target.parse_deal_amount("136,000") == 1_360_000_000


def test_parse_deal_amount_accepts_int_form():
    """실측상 18건은 dealAmount가 int로 온다."""
    assert target.parse_deal_amount(350) == 3_500_000


def test_parse_deal_amount_blank_is_none():
    assert target.parse_deal_amount(" ") is None
    assert target.parse_deal_amount(None) is None


# ── 3. 층 ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw_v,expected", [
    (1, 1), ("1", 1), (-1, -1), ("-2", -2), ("-3", -3), (15, 15),
])
def test_normalize_floor_keeps_sign(raw_v, expected):
    """지하는 API가 이미 음수로 준다 — 우리 규칙과 그대로 일치한다."""
    assert target.normalize_floor(raw_v) == expected


@pytest.mark.parametrize("raw_v", ["", " ", None, 0, "0"])
def test_normalize_floor_never_returns_zero(raw_v):
    """0은 절대 만들지 않는다 (절대 규칙 4 / DB CHECK chk_tx_floor)."""
    assert target.normalize_floor(raw_v) is None


# ── 4. 지번 -> PNU ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("jibun,expected", [
    ("716", (False, 716, 0)),
    (716, (False, 716, 0)),          # int로 오는 실측 케이스
    ("14-1", (False, 14, 1)),
    ("산3-2", (True, 3, 2)),
])
def test_split_jibun_parses_forms(jibun, expected):
    assert target.split_jibun(jibun) == expected


@pytest.mark.parametrize("jibun", ["6**", "9*", "", " ", None, "1-2-3", "abc"])
def test_split_jibun_rejects_masked_and_bad(jibun):
    """마스킹('6**')은 2024-01 이전·통건물의 기본 형태다 — 조립 불가로 다뤄야 한다."""
    assert target.split_jibun(jibun) is None


def test_make_pnu_assembles_19_digits():
    pnu = target.make_pnu("1168010800", "716")
    assert pnu == "1168010800" + "1" + "0716" + "0000"
    assert len(pnu) == 19


def test_make_pnu_uses_2_for_san():
    assert target.make_pnu("1168010800", "산3-2")[10] == "2"


def test_make_pnu_none_when_masked_or_bad_code():
    assert target.make_pnu("1168010800", "6**") is None
    assert target.make_pnu(None, "716") is None
    assert target.make_pnu("116801", "716") is None


# ── 5. 법정동 룩업 ───────────────────────────────────────────────────────────


def test_build_emd_lookup_prefers_active_code():
    """폐지 코드도 테이블에 남아 있다 — 실거래는 현행 표기로 오므로 현행이 맞다."""
    rows = [
        {"bjd_code": "1168010799", "sigungu_code": "11680", "emd_nm": "일원동", "is_active": False},
        {"bjd_code": "1168010800", "sigungu_code": "11680", "emd_nm": "일원동", "is_active": True},
    ]
    assert target.build_emd_lookup(rows, "11680")["일원동"] == "1168010800"


def test_build_emd_lookup_skips_other_sigungu_and_blank():
    rows = [
        {"bjd_code": "1144012300", "sigungu_code": "11440", "emd_nm": "서교동", "is_active": True},
        {"bjd_code": "1168010800", "sigungu_code": "11680", "emd_nm": "", "is_active": True},
    ]
    assert target.build_emd_lookup(rows, "11680") == {}


# ── 6. tx_id ─────────────────────────────────────────────────────────────────


def test_make_tx_id_is_stable_across_runs():
    assert target.make_tx_id(ITEM, 0) == target.make_tx_id(dict(ITEM), 0)


def test_make_tx_id_is_stable_across_type_variants():
    """같은 값이 str로 오든 int로 오든 같은 거래다 — 다른 id가 되면 중복 적재된다."""
    a = target.make_tx_id(ITEM, 0)
    b = target.make_tx_id(dict(ITEM, jibun="716", dealDay="25", sggCd="11680", floor="1"), 0)
    assert a == b


def test_make_tx_id_separates_same_combination():
    """같은 날 같은 값 거래가 32건 실재한다 — seq가 없으면 한 건으로 뭉개진다."""
    ids = {target.make_tx_id(ITEM, i) for i in range(32)}
    assert len(ids) == 32


def test_make_tx_id_differs_when_a_field_differs():
    assert target.make_tx_id(ITEM, 0) != target.make_tx_id(dict(ITEM, dealAmount="200,000"), 0)


# ── 7. 변환 ──────────────────────────────────────────────────────────────────


def test_is_canceled_reads_cdeal_type():
    assert target.is_canceled(dict(ITEM, cdealType="O")) is True
    assert target.is_canceled(ITEM) is False


def test_contract_ym_zero_pads_month():
    assert target.contract_ym(ITEM) == "202606"
    assert target.contract_ym(dict(ITEM, dealMonth=12)) == "202612"
    assert target.contract_ym(dict(ITEM, dealMonth=13)) is None
    assert target.contract_ym(dict(ITEM, dealYear="")) is None


def test_build_transaction_maps_every_field():
    rec, why = target.build_transaction(ITEM, EMD, 0)
    assert why == "적재"
    assert rec["pnu"] == "1168010800" + "1" + "0716" + "0000"
    assert rec["sigungu_code"] == "11680"
    assert rec["emd_nm"] == "일원동"
    assert rec["floor_no"] == 1
    assert rec["bld_area_m2"] == 28.8
    assert rec["land_area_m2"] is None          # plottageAr이 공백
    assert rec["price_won"] == 1_360_000_000
    assert rec["contract_ym"] == "202606"
    assert rec["contract_day"] == 25
    assert rec["build_year"] == 1993
    assert rec["tx_type"] == "집합"
    assert rec["main_use"] == "제1종근린생활"
    assert rec["bld_id"] is None and rec["bld_nm"] is None


def test_build_transaction_keeps_row_when_pnu_unassemblable():
    """통건물은 PNU가 원천 불가지만 지역·금액·면적은 유효하다 — 버리지 않는다."""
    rec, why = target.build_transaction(dict(ITEM, buildingType="일반", jibun="6**"), EMD, 0)
    assert why == "적재" and rec["pnu"] is None
    assert rec["price_won"] == 1_360_000_000


def test_build_transaction_rejects_rows_without_price_or_ym():
    assert target.build_transaction(dict(ITEM, dealAmount=""), EMD, 0)[0] is None
    assert target.build_transaction(dict(ITEM, dealYear=""), EMD, 0)[0] is None
    assert target.build_transaction(dict(ITEM, sggCd="116"), EMD, 0)[0] is None


def test_build_transactions_excludes_canceled_by_default():
    rows = [raw(ITEM), raw(dict(ITEM, cdealType="O", dealDay=26))]
    recs, stats = target.build_transactions(rows, EMD)
    assert len(recs) == 1
    assert stats["counts"]["해제 거래 제외"] == 1


def test_build_transactions_can_include_canceled():
    rows = [raw(ITEM), raw(dict(ITEM, cdealType="O", dealDay=26))]
    recs, _ = target.build_transactions(rows, EMD, include_canceled=True)
    assert len(recs) == 2


def test_build_transactions_gives_unique_ids_to_identical_deals():
    """같은 조합 32건이 와도 32행으로 살아남아야 한다 (실측 사례)."""
    rows = [raw(ITEM) for _ in range(32)]
    recs, _ = target.build_transactions(rows, EMD)
    assert len(recs) == 32
    assert len({r["tx_id"] for r in recs}) == 32
    target.assert_unique(recs, "tx_id")


def test_build_transactions_id_order_does_not_depend_on_raw_order():
    """raw 줄 순서가 달라져도 같은 id 집합이 나와야 한다 — 재수집 때 중복 적재 방지."""
    a = [raw(ITEM), raw(dict(ITEM, dealDay=26)), raw(dict(ITEM, dealAmount="200,000"))]
    b = list(reversed(a))
    ida = {r["tx_id"] for r in target.build_transactions(a, EMD)[0]}
    idb = {r["tx_id"] for r in target.build_transactions(b, EMD)[0]}
    assert ida == idb


def test_build_transactions_counts_pnu_success_and_failure():
    rows = [raw(ITEM), raw(dict(ITEM, jibun="6**", dealDay=26))]
    _, stats = target.build_transactions(rows, EMD)
    assert stats["counts"]["PNU 조립 성공"] == 1
    assert stats["counts"]["PNU 조립 실패"] == 1


# ── 8. latest_batch ──────────────────────────────────────────────────────────


def test_latest_batch_drops_older_duplicate_batch():
    old = raw(ITEM, fetched_at="2026-08-01T00:00:00+09:00")
    new = raw(dict(ITEM, dealDay=26), fetched_at="2026-08-08T00:00:00+09:00")
    kept = target.latest_batch([old, new])
    assert kept == [new]


def test_latest_batch_keeps_all_rows_of_same_batch():
    a = raw(ITEM)
    b = raw(dict(ITEM, dealDay=26))
    assert len(target.latest_batch([a, b])) == 2


def test_latest_batch_is_per_month():
    """달이 다르면 서로 영향을 주지 않는다."""
    a = raw(ITEM, deal_ym="202605", fetched_at="2026-08-01T00:00:00+09:00")
    b = raw(ITEM, deal_ym="202606", fetched_at="2026-08-08T00:00:00+09:00")
    assert len(target.latest_batch([a, b])) == 2


# ── 9. 불변식 / CLI ──────────────────────────────────────────────────────────


def test_assert_no_zero_floor_raises():
    with pytest.raises(RuntimeError, match="층 0"):
        target.assert_no_zero_floor([{"floor_no": 0}])


def test_assert_unique_raises_on_duplicate():
    with pytest.raises(RuntimeError, match="중복"):
        target.assert_unique([{"tx_id": "A"}, {"tx_id": "A"}])


def test_read_jsonl_counts_broken_lines(tmp_path):
    p = os.path.join(str(tmp_path), "11680.jsonl")
    with open(p, "w", encoding="utf-8") as fp:
        fp.write(json.dumps(raw(ITEM), ensure_ascii=False) + "\n")
        fp.write("{깨진 줄\n")
        fp.write("\n")
    rows, broken = target.read_jsonl(p)
    assert len(rows) == 1 and broken == 1


def test_read_jsonl_missing_file_is_empty():
    assert target.read_jsonl("없는파일.jsonl") == ([], 0)


def test_parse_args_defaults_and_overrides():
    o = target.parse_args([])
    assert o["sigungu_code"] == target.DEFAULT_SIGUNGU_CODE
    assert o["dry_run"] is False and o["include_canceled"] is False
    o2 = target.parse_args(["--sigungu-code", "11440", "--dry-run", "--include-canceled"])
    assert o2["sigungu_code"] == "11440" and o2["dry_run"] and o2["include_canceled"]


def test_parse_args_missing_value():
    with pytest.raises(ValueError, match="뒤에 값이 필요"):
        target.parse_args(["--sigungu-code"])


def test_parse_args_rejects_unknown_flag_like_help():
    """--help 를 조용히 무시하면 dry_run=False 인 실제 실행이 되어버린다(2026-08-08 실사고)."""
    with pytest.raises(ValueError, match="알 수 없는 인자"):
        target.parse_args(["--help"])


def test_parse_args_rejects_typo_does_not_silently_set_dry_run():
    """--dryrun(오타)이 --dry-run으로 조용히 넘어가면 실제 실행이 되어버린다."""
    with pytest.raises(ValueError, match="알 수 없는 인자"):
        target.parse_args(["--dryrun"])
