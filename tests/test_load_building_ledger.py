# -*- coding: utf-8 -*-
"""
scripts/collectors/load_building_ledger.py 단위 테스트

라이브 API·Supabase 없이 순수 로직만 검증한다:
  1. make_bld_id / make_unit_id — 동명칭 빈값 -> MAIN, 층 불명 -> NA
  2. parse_use_apr_day          — YYYYMMDD 파싱 방어(빈값·0·달력에 없는 날짜)
  3. floor_from_codes           — 층 코드 매핑 (복수층 부호 보존·0이 절대 안 나옴)
  4. sum_parking                — 주차 4종 합·전부 결측
  5. build_building_record      — 표제부 item -> building 행
  6. build_buildings            — 대장PK(mgmBldrgstPk) 기반 2패스 bld_id 확정
  7. build_floor_use_lookup     — (건물, 층) -> 주용도
  8. resolve_bld_id / build_units — 대장PK 우선 귀속·전유만 집계·다층 호 분리·
     면적 합·호실 공백 정규화·귀속 실패 분류
  9. latest_batch_by_pnu        — 중복 수집 배치 방어
 10. classify_missing_pnu / join_rate / find_truncated_pnu — §5.6 보고 재료
 11. assert_unique              — 업서트 직전 PK 유일성 가드
 12. upsert_batch / rest_count / transform / main — 흉내낸 requests로 동작만 확인
 12-1. delete_stale_units       — 층 복원으로 unit_id가 바뀔 때 옛 행 정리·PNU 범위 한정

conftest.py를 새로 만들지 않기 위해(다른 수집기 작업과 충돌 방지),
sys.path 조작은 이 파일 안에서만 한다.
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

import load_building_ledger as target  # noqa: E402


# ── 픽스처 (2026-08-07 실측 응답 필드 그대로) ────────────────────────────────

PNU_A = "1168010100108230004"
PNU_B = "1168010100108230005"
PNU_MOUNTAIN = "1168010100208230004"

TITLE_ITEM = {
    "mgmBldrgstPk": "11680-100123",
    "bldNm": "테스트빌딩",
    "dongNm": "",
    "totArea": "12345.67",
    "grndFlrCnt": "15",
    "ugrndFlrCnt": "3",
    "useAprDay": "20050317",
    "mainPurpsCd": "14000",
    "mainPurpsCdNm": "업무시설",
    "bcRat": "59.87",
    "vlRat": "789.12",
    "regstrGbCd": "2",
    "regstrGbCdNm": "집합",
    "regstrKindCd": "3",
    "regstrKindCdNm": "일반",
    "mainAtchGbCd": "0",
    "mainAtchGbCdNm": "주건축물",
    "indrAutoUtcnt": "120",
    "indrMechUtcnt": "0",
    "oudrAutoUtcnt": "5",
    "oudrMechUtcnt": "0",
    "hoCnt": "88",
}


def raw_row(pnu, item, fetched_at="2026-08-07T10:00:00+09:00"):
    return {"pnu": pnu, "fetched_at": fetched_at, "item": item}


def flr_item(flr_gb_cd="20", flr_no="1", purpose="제1종근린생활시설", dong_nm="", area="500.5"):
    return {
        "dongNm": dong_nm,
        "flrGbCd": flr_gb_cd,
        "flrGbCdNm": "지상" if flr_gb_cd == "20" else "지하",
        "flrNo": flr_no,
        "flrNoNm": "{}층".format(flr_no),
        "area": area,
        "mainPurpsCd": "02000",
        "mainPurpsCdNm": purpose,
        "mgmBldrgstPk": "11680-100123",
    }


def expos_item(ho_nm="101호", flr_gb_cd="20", flr_no="1", area="59.9",
               gb_cd="1", dong_nm="", mgm_pk=None, bld_nm=None, regstr_gb_cd=None):
    return {
        "dongNm": dong_nm,
        "hoNm": ho_nm,
        "flrGbCd": flr_gb_cd,
        "flrGbCdNm": "지상" if flr_gb_cd == "20" else "지하",
        "flrNo": flr_no,
        "flrNoNm": "{}층".format(flr_no),
        "area": area,
        "exposPubuseGbCd": gb_cd,
        "exposPubuseGbCdNm": "전유" if gb_cd == "1" else "공용",
        "mainPurpsCdNm": "제2종근린생활시설",
        "regstrKindCdNm": "집합",
        "mgmBldrgstPk": mgm_pk,
        "bldNm": bld_nm,
        "regstrGbCd": regstr_gb_cd,
    }


# ── 1. make_bld_id / make_unit_id ────────────────────────────────────────────


def test_make_bld_id_with_dong():
    assert target.make_bld_id(PNU_A, "가동") == PNU_A + "_가동"


def test_make_bld_id_blank_dong_becomes_main():
    assert target.make_bld_id(PNU_A, "") == PNU_A + "_MAIN"
    assert target.make_bld_id(PNU_A, "   ") == PNU_A + "_MAIN"
    assert target.make_bld_id(PNU_A, None) == PNU_A + "_MAIN"


def test_make_unit_id_basic():
    assert target.make_unit_id(PNU_A + "_MAIN", 3, "301호") == PNU_A + "_MAIN_3_301호"


def test_make_unit_id_underground_keeps_sign():
    assert target.make_unit_id(PNU_A + "_MAIN", -2, "B201호") == PNU_A + "_MAIN_-2_B201호"


def test_make_unit_id_unknown_floor_is_na_not_zero():
    unit_id = target.make_unit_id(PNU_A + "_MAIN", None, "101호")
    assert "_NA_" in unit_id
    assert "_0_" not in unit_id  # 절대 규칙 4 — 층 0 금지


def test_make_unit_id_does_not_re_strip_ho():
    """ho 정규화는 build_units 책임(수정 4) — make_unit_id는 받은 값을 그대로 쓴다."""
    assert target.make_unit_id("B", 1, "101호") == "B_1_101호"
    assert target.make_unit_id("B", 1, " 101 호 ") == "B_1_ 101 호 "


def test_make_unit_id_blank_ho():
    assert target.make_unit_id("B", 1, None) == "B_1_"


# ── 2. parse_use_apr_day ─────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    ("20050317", "2005-03-17"),
    ("19741231", "1974-12-31"),
    ("", None),
    ("0", None),
    (0, None),
    (None, None),
    ("2005031", None),        # 7글자
    ("200503177", None),      # 9글자
    ("2005-03-17", None),     # 하이픈 포함
    ("20051350", None),       # 13월 50일 — 달력에 없는 날
    ("20260230", None),       # 2월 30일
    ("abcdefgh", None),
])
def test_parse_use_apr_day(raw, expected):
    assert target.parse_use_apr_day(raw) == expected


# ── 3. floor_from_codes (층 코드 매핑 — 0이 절대 안 나온다) ──────────────────


@pytest.mark.parametrize("gb,no,expected", [
    ("20", "1", 1),      # 지상 1층
    ("20", "15", 15),
    ("20", 7, 7),
    ("10", "1", -1),     # 지하 1층
    ("10", "3", -3),
    ("10", -2, -2),      # 이미 음수로 온 값도 지하로 유지
    ("30", "1", 99),     # 옥탑
    ("30", "", 99),      # 옥탑은 flrNo와 무관한 분류값
    ("21", "4", 4),      # 복수층(하층) — flrNo가 곧 그 행의 층
    ("22", 5, 5),        # 복수층(상층)
    ("21", "-1", -1),    # 복수층인데 지하 — 부호는 flrNo가 들고 있다
    ("22", -2, -2),
])
def test_floor_from_codes_maps_known_codes(gb, no, expected):
    assert target.floor_from_codes(gb, no) == expected


@pytest.mark.parametrize("gb,no", [
    ("20", "0"), ("10", "0"), ("20", 0),   # flrNo 0
    ("20", ""), ("10", None),              # flrNo 결측
    ("40", "1"), ("", "1"), (None, "1"),   # 미지 코드
    ("20", "층"),                          # 숫자 아님
    ("21", "0"), ("22", 0),                # 복수층인데 flrNo 0 -> 층수를 모른다
    ("21", None), ("22", ""), ("21", "층"),  # 복수층인데 결측·숫자 아님
])
def test_floor_from_codes_returns_none_not_zero(gb, no):
    assert target.floor_from_codes(gb, no) is None


def test_floor_from_codes_multi_floor_keeps_sign_unlike_ground_code():
    """복수층(21/22)은 flrNo 부호를 그대로 살린다 — 지상 코드와 처리가 다르다.

    지상 '20'은 코드가 방향을 정하므로 flrNo가 음수로 와도 abs()해서 지상으로
    올린다. 반면 복수층 '21'/'22'는 코드에 방향이 없고 flrNo 부호가 방향을
    들고 있어(2026-08-07 강남구 실측: flrNo=-1 행이 속한 건물에 실제 지하
    1층이 존재) 부호를 지우면 지하가 지상으로 뒤집힌다.
    """
    assert target.floor_from_codes("20", -3) == 3     # 지상 코드는 부호를 무시
    assert target.floor_from_codes("21", -3) == -3    # 복수층은 부호를 보존
    assert target.floor_from_codes("22", -3) == -3


def test_floor_from_codes_never_yields_zero_over_wide_input():
    """어떤 조합을 넣어도 0이 나오면 안 된다 (DB CHECK chk_floor_not_zero 사전 차단)."""
    codes = ["10", "20", "21", "22", "30", "40", "", None, "1", "2"]
    numbers = ["0", 0, "", None, "1", "-1", 1, -1, "99", "층", "0.0"]
    for gb in codes:
        for no in numbers:
            assert target.floor_from_codes(gb, no) != 0


# ── 4. sum_parking ───────────────────────────────────────────────────────────


def test_sum_parking_sums_four_fields():
    assert target.sum_parking(TITLE_ITEM) == 125  # 120 + 0 + 5 + 0


def test_sum_parking_partial_missing_uses_present_only():
    item = {"indrAutoUtcnt": "10", "oudrAutoUtcnt": ""}
    assert target.sum_parking(item) == 10


def test_sum_parking_all_missing_returns_none():
    assert target.sum_parking({}) is None
    assert target.sum_parking({f: "" for f in target.PARKING_FIELDS}) is None


# ── 5. build_building_record ─────────────────────────────────────────────────


def test_build_building_record_maps_every_field():
    rec = target.build_building_record(PNU_A, TITLE_ITEM)
    assert rec["bld_id"] == PNU_A + "_MAIN"
    assert rec["pnu"] == PNU_A
    assert rec["dong_nm"] is None          # 빈 동명칭은 NULL로 저장
    assert rec["bld_nm"] == "테스트빌딩"
    assert rec["total_area_m2"] == pytest.approx(12345.67)
    assert rec["ground_floors"] == 15
    assert rec["under_floors"] == 3
    assert rec["approve_date"] == "2005-03-17"
    assert rec["main_use"] == "업무시설"
    assert rec["bcr"] == pytest.approx(59.87)
    assert rec["far"] == pytest.approx(789.12)
    assert rec["parking_cnt"] == 125
    assert rec["is_jiphap"] is True


def test_build_building_record_ilban_is_not_jiphap():
    rec = target.build_building_record(PNU_A, dict(TITLE_ITEM, regstrGbCd="1"))
    assert rec["is_jiphap"] is False


def test_build_building_record_keeps_dong_name():
    rec = target.build_building_record(PNU_A, dict(TITLE_ITEM, dongNm=" 가동 "))
    assert rec["dong_nm"] == "가동"
    assert rec["bld_id"] == PNU_A + "_가동"


def test_build_building_record_blank_numbers_become_none():
    blank = dict(TITLE_ITEM, totArea="", grndFlrCnt="", bcRat="", useAprDay="")
    rec = target.build_building_record(PNU_A, blank)
    assert rec["total_area_m2"] is None
    assert rec["ground_floors"] is None
    assert rec["bcr"] is None
    assert rec["approve_date"] is None


# ── 6. build_buildings (대장PK를 bld_id에 직접 사용 — 크로스-런 안정성) ─────


def test_build_buildings_dedupes_true_duplicate_rows():
    """같은 (PNU, 대장PK)는 진짜 중복(raw에 같은 건물이 두 번 실림)."""
    rows = [
        raw_row(PNU_A, dict(TITLE_ITEM, bldNm="첫번째")),
        raw_row(PNU_A, dict(TITLE_ITEM, bldNm="두번째")),   # 같은 pnu, 같은 대장PK
        raw_row(PNU_A, dict(TITLE_ITEM, dongNm="나동", mgmBldrgstPk="11680-100124")),
    ]
    buildings, stats = target.build_buildings(rows)

    assert len(buildings) == 2
    assert buildings[PNU_A + "_11680-100123"]["bld_nm"] == "첫번째"  # 진짜 중복은 첫 행 유지
    assert stats["duplicated_bld_id"] == 1
    assert stats["pk_missing_fallback"] == 0
    assert sorted(stats["buildings_by_pnu"][PNU_A]) == sorted(
        [PNU_A + "_11680-100123", PNU_A + "_11680-100124"])
    assert stats["pnu_with_building"] == {PNU_A}


def test_build_buildings_splits_different_mgm_pk_into_separate_buildings():
    """같은 (PNU, 동명칭)이라도 관리건축물대장PK가 다르면 별개 건물로 갈라야 한다.

    수정 1 회귀 테스트 — 11 에이전트 적대검증에서 강남구 라이브 raw 23그룹·대장
    30건이 예전 로직(주건축물 우선 tiebreak)으로 사라지는 게 확인됐다.
    """
    rows = [
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="11680-100001", bldNm="첫동")),
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="11680-100002", bldNm="둘째동")),
    ]
    buildings, stats = target.build_buildings(rows)

    assert len(buildings) == 2
    assert stats["duplicated_bld_id"] == 0
    bld_id_1 = PNU_A + "_11680-100001"
    bld_id_2 = PNU_A + "_11680-100002"
    assert bld_id_1 in buildings and bld_id_2 in buildings
    assert buildings[bld_id_1]["bld_nm"] == "첫동"
    assert buildings[bld_id_2]["bld_nm"] == "둘째동"
    assert sorted(stats["buildings_by_pnu"][PNU_A]) == sorted([bld_id_1, bld_id_2])


def test_build_buildings_bld_id_stable_across_reruns_even_with_new_pk_added():
    """크로스-런 안정성 회귀 가드 — 적대검증 Critical 지적(확신도 85, 2026-08-08).

    구코드(정렬 순번 방식)는 같은 base_id 아래 새 대장PK가 재수집 때 섞여
    들어오면 문자열 정렬 순번이 흔들려, 기존 unit들이 참조하던 bld_id가
    다른 건물 데이터로 조용히 덮어써졌다(FK는 멀쩡한데 의미만 오염). 새
    코드는 bld_id = pnu + '_' + 대장PK라 다른 행이 무엇이든 항상 같다.

    새 PK를 일부러 문자열 정렬상 "앞서는" 값으로 잡는다 — 구코드였다면
    반드시 깨지는 조합.
    """
    # 1차 수집(202608): 대장PK "9-old"(문자열 정렬상 뒤) 하나만 잡힘
    run1_rows = [raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="9-old", dongNm=""))]
    buildings1, _stats1 = target.build_buildings(run1_rows)
    old_bld_id = list(buildings1)[0]
    assert old_bld_id == PNU_A + "_9-old"

    # 2차 수집(반년 뒤, §3.1 갱신 주기): 재건축 이력 등으로 "1-new"(정렬상 앞)가 추가됨
    run2_rows = [
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="9-old", dongNm="")),
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="1-new", dongNm="", bldNm="신축동")),
    ]
    buildings2, _stats2 = target.build_buildings(run2_rows)

    assert old_bld_id in buildings2                          # 기존 건물의 bld_id가 그대로 살아있다
    assert buildings2[old_bld_id]["bld_nm"] == TITLE_ITEM["bldNm"]  # 다른 건물로 덮이지 않았다
    assert len(buildings2) == 2                               # 새 PK는 별개 건물로 추가됐을 뿐
    assert buildings2[PNU_A + "_1-new"]["bld_nm"] == "신축동"


def test_build_buildings_falls_back_to_dong_name_when_pk_missing():
    """대장PK가 비어 있으면(현재 raw는 0행이지만 방어) 동명칭 폴백을 쓴다."""
    rows = [raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk=None, dongNm=""))]
    buildings, stats = target.build_buildings(rows)

    assert buildings[PNU_A + "_MAIN"]["bld_nm"] == TITLE_ITEM["bldNm"]
    assert stats["pk_missing_fallback"] == 1


def test_build_buildings_falls_back_when_pk_is_blank_string():
    rows = [raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="", dongNm=""))]
    buildings, stats = target.build_buildings(rows)

    assert PNU_A + "_MAIN" in buildings
    assert stats["pk_missing_fallback"] == 1


def test_build_buildings_handles_integer_pk():
    """실측(2026-08-08): 라이브 raw의 mgmBldrgstPk 타입은 항상 int였다."""
    rows = [raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk=1234567890))]
    buildings, stats = target.build_buildings(rows)

    assert buildings[PNU_A + "_1234567890"]["bld_nm"] == TITLE_ITEM["bldNm"]
    assert stats["pk_missing_fallback"] == 0


# ── 7. build_floor_use_lookup ────────────────────────────────────────────────


def _floor_use_for(rows, *building_specs):
    """build_floor_use_lookup을 building 맥락과 함께 호출하는 도우미."""
    buildings, bstats = _buildings_for(*(building_specs or ((PNU_A, ""),)))
    return target.build_floor_use_lookup(rows, buildings, bstats["buildings_by_pnu"])


def test_build_floor_use_lookup_keys_by_building_and_floor():
    rows = [
        raw_row(PNU_A, flr_item(flr_gb_cd="20", flr_no="1", purpose="제1종근린생활시설")),
        raw_row(PNU_A, flr_item(flr_gb_cd="10", flr_no="1", purpose="주차장")),
        raw_row(PNU_A, flr_item(flr_gb_cd="30", flr_no="1", purpose="옥탑")),
    ]
    lookup, stats = _floor_use_for(rows)
    bld_id = _bld_id_for(PNU_A, "")

    assert lookup[(bld_id, 1)] == "제1종근린생활시설"
    assert lookup[(bld_id, -1)] == "주차장"
    assert lookup[(bld_id, 99)] == "옥탑"
    assert stats["rows"] == 3
    assert sum(stats["floor_unmapped"].values()) == 0


def test_build_floor_use_lookup_keeps_first_value_per_floor():
    rows = [
        raw_row(PNU_A, flr_item(purpose="첫값")),
        raw_row(PNU_A, flr_item(purpose="둘째값")),
    ]
    lookup, _ = _floor_use_for(rows)
    assert lookup[(_bld_id_for(PNU_A, ""), 1)] == "첫값"


def test_build_floor_use_lookup_counts_unmapped_floor():
    rows = [raw_row(PNU_A, flr_item(flr_gb_cd="40", flr_no="0"))]
    lookup, stats = _floor_use_for(rows)
    assert lookup == {}
    assert sum(stats["floor_unmapped"].values()) == 1


def test_build_floor_use_lookup_uses_same_dong_fallback_as_units():
    """표제부 dongNm='' + 층별개요 dongNm='가동'이어도 같은 건물 키로 들어가야 한다.

    flr_item()의 mgmBldrgstPk는 building fixture의 실제 대장PK("PK-...")와
    다르므로 대장PK 매칭(①)은 실패하고, 동명칭 폴백(③)까지 내려가야 한다
    (수정 3 회귀 테스트: floor_use가 NULL로 새지 않고 실제로 채워져야 한다).
    """
    rows = [raw_row(PNU_A, flr_item(dong_nm="가동", purpose="제1종근린생활시설"))]
    lookup, stats = _floor_use_for(rows, (PNU_A, ""))

    assert lookup == {(_bld_id_for(PNU_A, ""), 1): "제1종근린생활시설"}
    assert stats["unresolved"] == 0
    assert stats["resolve_reasons"]["PNU 단일 건물로 귀속"] == 1


def test_build_floor_use_lookup_counts_unresolved_when_ambiguous():
    rows = [raw_row(PNU_A, flr_item(dong_nm="다동"))]
    lookup, stats = _floor_use_for(rows, (PNU_A, "가동"), (PNU_A, "나동"))

    assert lookup == {}
    assert stats["unresolved"] == 1


# ── 8. resolve_bld_id / build_units ─────────────────────────────────────────


def _buildings_for(*specs):
    """(pnu, dong) 목록으로 build_buildings 결과를 만든다.

    대장PK는 (pnu, dong) 조합별로 고유한 값을 부여한다 — 실제로도 서로 다른
    건물은 서로 다른 mgmBldrgstPk를 가지므로, 테스트 픽스처가 이를 재현하지
    않으면(같은 PK를 재사용하면) bld_id가 비현실적으로 충돌한다.
    """
    rows = [
        raw_row(pnu, dict(TITLE_ITEM, dongNm=dong, mgmBldrgstPk="PK-{}-{}".format(pnu, dong)))
        for pnu, dong in specs
    ]
    return target.build_buildings(rows)


def _bld_id_for(pnu, dong):
    """_buildings_for()가 만드는 건물의 bld_id를 예측 가능하게 계산한다(테스트 전용).

    bld_id는 이제 pnu + '_' + 대장PK이므로 '_MAIN' 같은 동명칭 폴백 문자열을
    더 이상 가정할 수 없다 — _buildings_for가 부여한 합성 PK를 그대로 재현한다.
    """
    return "{}_PK-{}-{}".format(pnu, pnu, dong)


def test_resolve_bld_id_single_candidate_shortcut_ignores_dong_name():
    """PNU에 건물이 하나뿐이면 동명칭이 일치하든 안 하든 그걸로 확정한다(모호성이 없다)."""
    rows = [raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk=None, dongNm=""))]
    buildings, stats = target.build_buildings(rows)
    bld_id, reason = target.resolve_bld_id(
        PNU_A, "전혀다른동", None, None, False, buildings, stats["buildings_by_pnu"])
    assert bld_id == PNU_A + "_MAIN"
    assert reason == "PNU 단일 건물로 귀속"


def test_resolve_bld_id_prefers_pk_match_and_is_stable_regardless_of_other_pks():
    """대장PK가 맞으면 다른 건물이 몇 개든, 어떤 PK를 갖든 항상 같은 bld_id로 귀속된다
    (수정 1의 핵심 — 정렬 순번에 의존하지 않는다)."""
    rows = [
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="PK-1", dongNm="")),
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="PK-2", dongNm="")),
    ]
    buildings, stats = target.build_buildings(rows)
    bld_id, reason = target.resolve_bld_id(
        PNU_A, "", "PK-2", None, False, buildings, stats["buildings_by_pnu"])
    assert bld_id == PNU_A + "_PK-2"
    assert reason == "대장PK 매칭"


def test_units_resolve_via_pk_even_when_dong_name_differs_from_title():
    """전유부 dongNm이 표제부와 달라도 mgm_pk만 맞으면 정확히 귀속돼야 한다."""
    title_rows = [raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="PK-1", dongNm=""))]
    buildings, bstats = target.build_buildings(title_rows)
    expos_rows = [
        raw_row(PNU_A, expos_item(dong_nm="가동", ho_nm="101호", area="30.0", mgm_pk="PK-1")),
    ]

    units, stats = target.build_units(expos_rows, buildings, bstats["buildings_by_pnu"], {})

    assert len(units) == 1
    assert units[0]["bld_id"] == PNU_A + "_PK-1"
    assert stats["resolve_reasons"]["대장PK 매칭"] == 1


def test_resolve_bld_id_falls_back_to_single_building():
    buildings, stats = _buildings_for((PNU_A, ""))
    bld_id, reason = target.resolve_bld_id(
        PNU_A, "가동", None, None, False, buildings, stats["buildings_by_pnu"])
    assert bld_id == _bld_id_for(PNU_A, "")
    assert "단일 건물" in reason


def test_resolve_bld_id_no_building_for_pnu():
    buildings, stats = _buildings_for((PNU_A, ""))
    bld_id, reason = target.resolve_bld_id(
        PNU_B, "", None, None, False, buildings, stats["buildings_by_pnu"])
    assert bld_id is None
    assert "건물 없음" in reason


# ── 8-a. resolve_bld_id 후보 좁히기 (2차 적대검증 Critical 회귀 가드) ───────
#
# 실측(2026-08-08, 강남구 라이브 raw): 표제부 기준 건물 2개 이상인 PNU 117개
# 중 동명칭만으로 못 가르는 23개·전유부 15,656행을 단계별로 좁힌 결과
# ① 동명칭 14,748행(94.2%) ② 대장구분 639행 ③ 건물명 0행 ④ 진짜 판정 불가
# 269행(전부 PNU 1168010100107020022 한 곳 — 집합건물 2개가 동명칭·건물명
# 모두 공란). 아래 테스트는 이 네 갈래를 각각 재현한다.


def test_resolve_bld_id_narrows_by_dong_name_with_two_named_buildings():
    """동명칭이 다른 건물 2개 — 각 행이 자기 동명칭으로 정확히 귀속된다."""
    buildings, bstats = _buildings_for((PNU_A, "가동"), (PNU_A, "나동"))
    rows = [
        raw_row(PNU_A, expos_item(dong_nm="가동", ho_nm="101호", area="30.0")),
        raw_row(PNU_A, expos_item(dong_nm="나동", ho_nm="101호", area="40.0")),
    ]
    units, stats = target.build_units(rows, buildings, bstats["buildings_by_pnu"], {})

    by_bld = {u["bld_id"]: u for u in units}
    assert by_bld[_bld_id_for(PNU_A, "가동")]["excl_area_m2"] == pytest.approx(30.0)
    assert by_bld[_bld_id_for(PNU_A, "나동")]["excl_area_m2"] == pytest.approx(40.0)
    assert stats["resolve_reasons"]["동명칭 일치"] == 2


def test_resolve_bld_id_narrows_by_registry_type_when_dong_name_blank_both():
    """동명칭이 둘 다 공란이면 ①로는 못 가른다 — 대장구분(집합/일반)으로 좁힌다."""
    rows = [
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="PK-JIPHAP", dongNm="", regstrGbCd="2")),
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="PK-ILBAN", dongNm="", regstrGbCd="1")),
    ]
    buildings, stats = target.build_buildings(rows)

    bld_id, reason = target.resolve_bld_id(
        PNU_A, "", None, None, True, buildings, stats["buildings_by_pnu"])  # 전유부=집합
    assert bld_id == PNU_A + "_PK-JIPHAP"
    assert reason == "대장구분(집합/일반) 일치"

    bld_id2, reason2 = target.resolve_bld_id(
        PNU_A, "", None, None, False, buildings, stats["buildings_by_pnu"])  # 전유부=일반
    assert bld_id2 == PNU_A + "_PK-ILBAN"
    assert reason2 == "대장구분(집합/일반) 일치"


def test_build_units_resolves_by_registry_type_end_to_end():
    """전유부 행 자신의 regstrGbCd 값으로 대장구분을 좁힌다(build_units 통합 경로)."""
    title_rows = [
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="PK-JIPHAP", dongNm="", regstrGbCd="2")),
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="PK-ILBAN", dongNm="", regstrGbCd="1")),
    ]
    buildings, bstats = target.build_buildings(title_rows)
    rows = [raw_row(PNU_A, expos_item(dong_nm="", ho_nm="101호", area="30.0", regstr_gb_cd="1"))]

    units, stats = target.build_units(rows, buildings, bstats["buildings_by_pnu"], {})

    assert len(units) == 1
    assert units[0]["bld_id"] == PNU_A + "_PK-ILBAN"
    assert stats["resolve_reasons"]["대장구분(집합/일반) 일치"] == 1


def test_resolve_bld_id_narrows_by_building_name_when_dong_and_registry_type_tie():
    """동명칭·대장구분이 같고 건물명만 다르면 건물명으로 좁힌다."""
    rows = [
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="PK-A", dongNm="", bldNm="가동빌딩")),
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="PK-B", dongNm="", bldNm="나동빌딩")),
    ]
    buildings, stats = target.build_buildings(rows)

    bld_id, reason = target.resolve_bld_id(
        PNU_A, "", None, "나동빌딩", True, buildings, stats["buildings_by_pnu"])
    assert bld_id == PNU_A + "_PK-B"
    assert reason == "건물명 일치"


def test_resolve_bld_id_skips_when_truly_indistinguishable():
    """동명칭·대장구분·건물명 전부 같아 끝까지 안 좁혀지면 임의 귀속하지 않고 스킵한다
    (2차 적대검증 Critical 회귀 가드 — 실측: 강남구 PNU 1168010100107020022 269행이
    이 케이스에 해당한다)."""
    rows = [
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="PK-A", dongNm="", bldNm="")),
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="PK-B", dongNm="", bldNm="")),
    ]
    buildings, stats = target.build_buildings(rows)

    bld_id, reason = target.resolve_bld_id(
        PNU_A, "", None, "", True, buildings, stats["buildings_by_pnu"])
    assert bld_id is None
    assert "귀속 불가" in reason


def test_build_units_skips_and_counts_when_truly_indistinguishable():
    title_rows = [
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="PK-A", dongNm="", bldNm="")),
        raw_row(PNU_A, dict(TITLE_ITEM, mgmBldrgstPk="PK-B", dongNm="", bldNm="")),
    ]
    buildings, bstats = target.build_buildings(title_rows)
    rows = [raw_row(PNU_A, expos_item(dong_nm="", ho_nm="101호"))]

    units, stats = target.build_units(rows, buildings, bstats["buildings_by_pnu"], {})

    assert units == []
    assert stats["counts"]["건물 귀속 실패로 스킵"] == 1
    assert stats["resolve_reasons"]["동명칭·대장구분·건물명으로도 유일하게 좁혀지지 않음(귀속 불가)"] == 1


def test_build_units_excludes_public_area_and_sums_private():
    buildings, bstats = _buildings_for((PNU_A, ""))
    lookup, _ = target.build_floor_use_lookup(
        [raw_row(PNU_A, flr_item())], buildings, bstats["buildings_by_pnu"])
    rows = [
        raw_row(PNU_A, expos_item(ho_nm="101호", area="40.0", gb_cd="1")),
        raw_row(PNU_A, expos_item(ho_nm="101호", area="19.9", gb_cd="1")),  # 같은 호 두 줄 -> 합산
        raw_row(PNU_A, expos_item(ho_nm="101호", area="999.0", gb_cd="2")),  # 공용 -> 제외
    ]
    units, stats = target.build_units(rows, buildings, bstats["buildings_by_pnu"], lookup)

    assert len(units) == 1
    assert units[0]["excl_area_m2"] == pytest.approx(59.9)
    assert units[0]["unit_id"] == _bld_id_for(PNU_A, "") + "_1_101호"
    assert units[0]["floor_no"] == 1
    assert units[0]["ho"] == "101호"
    assert units[0]["floor_use"] == "제1종근린생활시설"
    assert stats["counts"]["공용 등 제외"] == 1


def test_build_units_normalizes_ho_whitespace_into_one_group():
    """'101 호'와 '101호'는 내부 공백만 다를 뿐 같은 호실 — 하나로 합쳐야 한다.

    수정 4 회귀 테스트 — 예전엔 그룹 키(ho.strip())와 unit_id(공백 전부 제거)가
    서로 다른 정규화 강도를 써서, 내부 공백이 있는 hoNm이 섞이면 같은 unit_id를
    두 그룹이 만들면서도 면적은 나뉘어 저장되는 조용한 버그가 잠복해 있었다.
    """
    buildings, bstats = _buildings_for((PNU_A, ""))
    rows = [
        raw_row(PNU_A, expos_item(ho_nm="101 호", area="30.0")),
        raw_row(PNU_A, expos_item(ho_nm="101호", area="29.9")),
    ]
    units, stats = target.build_units(rows, buildings, bstats["buildings_by_pnu"], {})

    assert len(units) == 1
    assert units[0]["ho"] == "101호"
    assert units[0]["excl_area_m2"] == pytest.approx(59.9)
    assert units[0]["unit_id"] == _bld_id_for(PNU_A, "") + "_1_101호"
    assert stats["counts"]["면적 합산 행"] == 2


def test_build_units_splits_same_ho_across_floors():
    """'2동제지하1,2층1층호'처럼 한 호가 여러 층에 걸치면 층마다 별개 unit이 된다."""
    buildings, bstats = _buildings_for((PNU_A, ""))
    rows = [
        raw_row(PNU_A, expos_item(ho_nm="101호", flr_gb_cd="10", flr_no="1", area="30.0")),
        raw_row(PNU_A, expos_item(ho_nm="101호", flr_gb_cd="20", flr_no="1", area="40.0")),
    ]
    units, _ = target.build_units(rows, buildings, bstats["buildings_by_pnu"], {})

    by_floor = {u["floor_no"]: u for u in units}
    assert sorted(by_floor) == [-1, 1]
    assert by_floor[-1]["excl_area_m2"] == pytest.approx(30.0)
    assert by_floor[1]["excl_area_m2"] == pytest.approx(40.0)
    assert by_floor[-1]["unit_id"] != by_floor[1]["unit_id"]


def test_build_units_keeps_unit_when_floor_unmapped():
    buildings, bstats = _buildings_for((PNU_A, ""))
    rows = [raw_row(PNU_A, expos_item(flr_gb_cd="40", flr_no="0", area="10.0"))]
    units, stats = target.build_units(rows, buildings, bstats["buildings_by_pnu"], {})

    assert len(units) == 1
    assert units[0]["floor_no"] is None          # 0이 아니라 NULL
    assert units[0]["unit_id"].endswith("_NA_101호")
    assert sum(stats["floor_unmapped"].values()) == 1


def test_build_units_skips_when_building_ambiguous():
    """동명칭·대장구분·건물명 어느 것도 좁혀주지 못하는 dongNm(공란)이면 스킵한다."""
    buildings, bstats = _buildings_for((PNU_A, "가동"), (PNU_A, "나동"))
    rows = [raw_row(PNU_A, expos_item(dong_nm="다동"))]
    units, stats = target.build_units(rows, buildings, bstats["buildings_by_pnu"], {})

    assert units == []
    assert stats["counts"]["건물 귀속 실패로 스킵"] == 1
    assert stats["resolve_reasons"]["동명칭·대장구분·건물명으로도 유일하게 좁혀지지 않음(귀속 불가)"] == 1


def test_build_units_counts_missing_area():
    buildings, bstats = _buildings_for((PNU_A, ""))
    rows = [raw_row(PNU_A, expos_item(area=""))]
    units, stats = target.build_units(rows, buildings, bstats["buildings_by_pnu"], {})

    assert len(units) == 1
    assert units[0]["excl_area_m2"] is None
    assert stats["counts"]["area 결측"] == 1


def test_build_units_never_produces_zero_floor():
    buildings, bstats = _buildings_for((PNU_A, ""))
    rows = [
        raw_row(PNU_A, expos_item(ho_nm="A", flr_gb_cd="20", flr_no="0")),
        raw_row(PNU_A, expos_item(ho_nm="B", flr_gb_cd="10", flr_no="0")),
        raw_row(PNU_A, expos_item(ho_nm="C", flr_gb_cd="20", flr_no="1")),
    ]
    units, _ = target.build_units(rows, buildings, bstats["buildings_by_pnu"], {})
    assert all(u["floor_no"] != 0 for u in units)
    assert target.assert_no_zero_floor(units) == len(units)


def test_assert_no_zero_floor_raises_on_zero():
    with pytest.raises(RuntimeError, match="층 0"):
        target.assert_no_zero_floor([{"floor_no": 0}])


# ── 9. read_jsonl / latest_batch_by_pnu ─────────────────────────────────────


def test_read_jsonl_reads_and_counts_broken_lines(tmp_path):
    path = os.path.join(str(tmp_path), "title.jsonl")
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(json.dumps(raw_row(PNU_A, TITLE_ITEM), ensure_ascii=False) + "\n")
        fp.write("\n")                      # 빈 줄 — 무시
        fp.write("{깨진 JSON\n")            # 파싱 실패 — broken
        fp.write(json.dumps({"pnu": PNU_B}, ensure_ascii=False) + "\n")  # item 없음 — broken

    rows, broken = target.read_jsonl(path)
    assert len(rows) == 1
    assert rows[0]["item"] == TITLE_ITEM
    assert broken == 2


def test_read_jsonl_missing_file_is_empty():
    rows, broken = target.read_jsonl("존재하지_않는_파일.jsonl")
    assert rows == []
    assert broken == 0


def test_latest_batch_by_pnu_drops_older_duplicate_batch():
    """같은 PNU가 두 번 수집됐으면 늦은 배치만 남겨 면적 이중합산을 막는다."""
    rows = [
        raw_row(PNU_A, expos_item(area="10.0"), fetched_at="2026-08-07T10:00:00+09:00"),
        raw_row(PNU_A, expos_item(area="10.0"), fetched_at="2026-08-08T10:00:00+09:00"),
        raw_row(PNU_B, expos_item(area="20.0"), fetched_at="2026-08-07T10:00:00+09:00"),
    ]
    kept = target.latest_batch_by_pnu(rows)
    assert len(kept) == 2
    assert {r["pnu"] for r in kept} == {PNU_A, PNU_B}
    assert [r for r in kept if r["pnu"] == PNU_A][0]["fetched_at"].startswith("2026-08-08")


def test_latest_batch_by_pnu_keeps_all_rows_of_same_batch():
    rows = [
        raw_row(PNU_A, expos_item(ho_nm="101호"), fetched_at="t1"),
        raw_row(PNU_A, expos_item(ho_nm="102호"), fetched_at="t1"),
    ]
    assert len(target.latest_batch_by_pnu(rows)) == 2


# ── 10. §5.6 보고 재료 ──────────────────────────────────────────────────────


def test_classify_missing_pnu_mountain():
    reason = target.classify_missing_pnu(PNU_MOUNTAIN, set(), set(), set(), set())
    assert "산" in reason


def test_classify_missing_pnu_no_raw_item():
    reason = target.classify_missing_pnu(PNU_A, set(), set(), set(), set())
    assert "raw에 아이템 없음" in reason


def test_classify_missing_pnu_raw_present_but_no_building():
    reason = target.classify_missing_pnu(PNU_A, {PNU_A}, set(), set(), set())
    assert reason == "수집 완료했으나 API 무데이터"


def test_classify_missing_pnu_returns_none_when_matched():
    assert target.classify_missing_pnu(PNU_A, {PNU_A}, {PNU_A}, set(), set()) is None


def test_classify_missing_pnu_unsupported_plat_gb():
    weird = PNU_A[:10] + "9" + PNU_A[11:]
    assert "대지구분 코드 미지원" in target.classify_missing_pnu(weird, set(), set(), set(), set())


def test_classify_missing_pnu_pending_excluded_from_join_denominator():
    reason = target.classify_missing_pnu(PNU_A, set(), set(), {PNU_A}, set())
    assert reason == "미수집(pending)"


def test_classify_missing_pnu_failed_excluded_from_join_denominator():
    reason = target.classify_missing_pnu(PNU_A, set(), set(), set(), {PNU_A})
    assert reason == "수집 실패(failed, 재시도 대상)"


def test_join_rate():
    assert target.join_rate(9, 10) == pytest.approx(90.0)
    assert target.join_rate(0, 0) is None  # 분모 0은 0%가 아니라 측정 불가


def test_find_truncated_pnu_flags_pnu_at_cap():
    rows = [raw_row(PNU_A, expos_item(ho_nm=str(i))) for i in range(5)]
    rows.append(raw_row(PNU_B, expos_item()))
    assert target.find_truncated_pnu(rows, cap=5) == [PNU_A]
    assert target.find_truncated_pnu(rows, cap=6) == []


# ── 11. assert_unique ────────────────────────────────────────────────────────


def test_assert_unique_passes_when_all_distinct():
    assert target.assert_unique([{"bld_id": "a"}, {"bld_id": "b"}], "bld_id") == 2


def test_assert_unique_raises_on_duplicate():
    with pytest.raises(RuntimeError, match="중복"):
        target.assert_unique([{"bld_id": "a"}, {"bld_id": "a"}], "bld_id")


# ── 12. transform / upsert / main (파일·requests 흉내) ──────────────────────


def _write_raw(tmp_path, title=(), flr=(), expos=()):
    raw_dir = str(tmp_path)
    for filename, rows in (
        (target.RAW_TITLE, title),
        (target.RAW_FLR_OULN, flr),
        (target.RAW_EXPOS_AREA, expos),
    ):
        with open(os.path.join(raw_dir, filename), "w", encoding="utf-8") as fp:
            for row in rows:
                fp.write(json.dumps(row, ensure_ascii=False) + "\n")
    return raw_dir


def test_transform_end_to_end(tmp_path):
    raw_dir = _write_raw(
        tmp_path,
        title=[raw_row(PNU_A, TITLE_ITEM)],
        flr=[raw_row(PNU_A, flr_item(purpose="제1종근린생활시설"))],
        expos=[
            raw_row(PNU_A, expos_item(ho_nm="101호", area="30.0")),
            raw_row(PNU_A, expos_item(ho_nm="101호", area="29.9")),
            raw_row(PNU_A, expos_item(ho_nm="공용부", area="500.0", gb_cd="2")),
        ],
    )
    buildings, units, stats = target.transform(raw_dir)

    assert len(buildings) == 1
    assert buildings[0]["bld_id"] == PNU_A + "_" + TITLE_ITEM["mgmBldrgstPk"]
    assert len(units) == 1
    assert units[0]["excl_area_m2"] == pytest.approx(59.9)
    assert units[0]["floor_use"] == "제1종근린생활시설"
    assert stats["pnu_in_raw_title"] == {PNU_A}
    assert stats["truncated_pnus"] == []


def test_transform_fills_floor_use_despite_dong_name_mismatch(tmp_path):
    """표제부 dongNm='' / 층별개요·전유부 dongNm='가동' — 건물이 하나뿐이면 전부 귀속.

    수정 3 회귀 테스트: floor_use가 NULL로 새지 않고 실제로 채워져야 한다.
    """
    raw_dir = _write_raw(
        tmp_path,
        title=[raw_row(PNU_A, dict(TITLE_ITEM, dongNm=""))],
        flr=[raw_row(PNU_A, flr_item(dong_nm="가동", purpose="제2종근린생활시설"))],
        expos=[raw_row(PNU_A, expos_item(dong_nm="가동", ho_nm="101호", area="30.0"))],
    )
    _buildings, units, _stats = target.transform(raw_dir)

    assert len(units) == 1
    assert units[0]["bld_id"] == PNU_A + "_" + TITLE_ITEM["mgmBldrgstPk"]
    assert units[0]["floor_use"] == "제2종근린생활시설"


def test_transform_missing_files_yields_empty(tmp_path):
    buildings, units, _ = target.transform(str(tmp_path))
    assert buildings == []
    assert units == []


class _FakeResponse:
    def __init__(self, status_code=201, payload=None, text="ok", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._payload


def test_upsert_batch_uses_merge_duplicates(monkeypatch):
    seen = []
    monkeypatch.setattr(
        target.requests, "post",
        lambda url, json=None, headers=None, timeout=None: (
            seen.append({"url": url, "headers": headers, "json": json})
            or _FakeResponse(201)),
    )
    sent = target.upsert_batch("https://x.supabase.co", {"apikey": "k"}, "building",
                               [{"bld_id": "a"}])
    assert sent == 1
    assert seen[0]["headers"]["Prefer"] == "resolution=merge-duplicates,return=minimal"
    assert seen[0]["url"].endswith("/rest/v1/building")


def test_upsert_batch_unknown_table_raises():
    with pytest.raises(ValueError, match="TABLE_UPSERT_RESOLUTION"):
        target.upsert_batch("https://x.supabase.co", {}, "이상한_테이블", [{"x": 1}])


def test_upsert_batch_wraps_network_error(monkeypatch):
    def boom(url, json=None, headers=None, timeout=None):
        raise target.requests.exceptions.ConnectionError("연결 끊김")

    monkeypatch.setattr(target.requests, "post", boom)
    with pytest.raises(RuntimeError, match="다시 실행하면 이어서"):
        target.upsert_batch("https://x.supabase.co", {}, "building", [{"bld_id": "a"}])


def test_rest_count_parses_content_range(monkeypatch):
    monkeypatch.setattr(
        target.requests, "head",
        lambda url, headers=None, timeout=None: _FakeResponse(
            206, headers={"Content-Range": "0-999/64239"}),
    )
    assert target.rest_count("https://x.supabase.co", {}, "unit_business", "select=biz_no") == 64239


def test_rest_count_raises_on_bad_status(monkeypatch):
    monkeypatch.setattr(
        target.requests, "head",
        lambda url, headers=None, timeout=None: _FakeResponse(404, text="not found"),
    )
    with pytest.raises(RuntimeError, match="count 조회 실패"):
        target.rest_count("https://x.supabase.co", {}, "building", "select=pnu")


def test_rest_select_always_includes_order(monkeypatch):
    urls = []

    def fake_get(url, headers=None, timeout=None):
        urls.append(url)
        return _FakeResponse(200, payload=[])

    monkeypatch.setattr(target.requests, "get", fake_get)
    target.rest_select("https://x.supabase.co", {}, "parcel", "select=pnu")
    assert "order=pnu" in urls[0]

    target.rest_select("https://x.supabase.co", {}, "unit_business", "select=pnu",
                       order="snapshot_ym,biz_no")
    assert "order=snapshot_ym,biz_no" in urls[1]


# ── 12-1. delete_stale_units (층이 바뀌면 unit_id가 바뀌어 옛 행이 남는다) ────

PNU_1 = "1" * 19
PERIOD = "202608"


def _fake_delete(sink, status=204):
    def _delete(url, params=None, headers=None, timeout=None):
        sink.append(params)
        return _FakeResponse(status, text="err")
    return _delete


def _progress_says_complete(monkeypatch, counts):
    """collect_progress가 "이 PNU들은 done이고 row_count가 이렇다"고 답하게 만든다."""
    monkeypatch.setattr(target, "fetch_done_row_counts", lambda *a, **kw: dict(counts))


def _call(units, raw_counts, truncated=(), **kw):
    return target.delete_stale_units(
        "https://x.supabase.co", {}, units, PERIOD, raw_counts, truncated, **kw)


def test_delete_stale_units_deletes_only_ids_missing_from_new_set(monkeypatch):
    """복원 전 '_NA_' 행만 지우고, 이번에 계산된 행은 건드리지 않는다."""
    _progress_says_complete(monkeypatch, {PNU_1: 7})
    monkeypatch.setattr(target, "rest_select", lambda *a, **kw: [
        {"unit_id": "B_NA_501호"}, {"unit_id": "B_5_501호"}, {"unit_id": "B_3_101호"},
    ])
    sent = []
    monkeypatch.setattr(target.requests, "delete", _fake_delete(sent))

    units = [{"unit_id": "B_5_501호", "pnu": PNU_1},
             {"unit_id": "B_3_101호", "pnu": PNU_1}]
    assert _call(units, {PNU_1: 7}) == 1
    assert sent[0]["unit_id"] == 'in.("B_NA_501호")'


def test_delete_stale_units_scopes_lookup_to_pnus_in_records(monkeypatch):
    """조회 범위를 raw에 있는 PNU로 좁힌다 — 아직 수집 안 된 지역을 지우면 안 된다."""
    pnu_a, pnu_b = "1168010300100120000", "1168010300100130003"
    _progress_says_complete(monkeypatch, {pnu_a: 3, pnu_b: 4})
    queries = []

    def fake_select(base_url, headers, table, query, **kw):
        queries.append((table, query))
        return []

    monkeypatch.setattr(target, "rest_select", fake_select)
    units = [{"unit_id": "A_1_1호", "pnu": pnu_a}, {"unit_id": "B_1_1호", "pnu": pnu_b}]
    assert _call(units, {pnu_a: 3, pnu_b: 4}) == 0
    assert queries[0][0] == "unit"
    assert "select=unit_id" in queries[0][1]
    assert "pnu=in.({},{})".format(pnu_a, pnu_b) in queries[0][1]


def test_delete_stale_units_quotes_ids_so_commas_do_not_split(monkeypatch):
    """호실명에 콤마가 있어도 값 하나로 전달돼야 한다 (엉뚱한 행 삭제 방지)."""
    _progress_says_complete(monkeypatch, {PNU_1: 2})
    monkeypatch.setattr(target, "rest_select",
                        lambda *a, **kw: [{"unit_id": 'P_1_101,102호'}])
    sent = []
    monkeypatch.setattr(target.requests, "delete", _fake_delete(sent))

    units = [{"unit_id": "P_1_103호", "pnu": PNU_1}]
    assert _call(units, {PNU_1: 2}) == 1
    assert sent[0]["unit_id"] == 'in.("P_1_101,102호")'


def test_pgrst_in_list_escapes_quotes_and_backslashes():
    assert target._pgrst_in_list(['a"b']) == 'in.("a\\"b")'
    assert target._pgrst_in_list(["a\\b"]) == 'in.("a\\\\b")'
    assert target._pgrst_in_list(["a", "b"]) == 'in.("a","b")'


def test_delete_stale_units_sends_nothing_when_all_rows_still_exist(monkeypatch):
    _progress_says_complete(monkeypatch, {PNU_1: 1})
    monkeypatch.setattr(target, "rest_select", lambda *a, **kw: [{"unit_id": "A_1_1호"}])

    def boom(*a, **kw):
        raise AssertionError("지울 행이 없으면 DELETE를 보내면 안 된다")

    monkeypatch.setattr(target.requests, "delete", boom)
    units = [{"unit_id": "A_1_1호", "pnu": PNU_1}]
    assert _call(units, {PNU_1: 1}) == 0


def test_delete_stale_units_empty_records_touches_no_network(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("빈 입력에 네트워크를 건드리면 안 된다")

    monkeypatch.setattr(target, "fetch_done_row_counts", boom)
    monkeypatch.setattr(target, "rest_select", boom)
    monkeypatch.setattr(target.requests, "delete", boom)
    assert _call([], {}) == 0


def test_delete_stale_units_chunks_deletes(monkeypatch):
    _progress_says_complete(monkeypatch, {PNU_1: 1})
    monkeypatch.setattr(target, "rest_select",
                        lambda *a, **kw: [{"unit_id": "OLD{}".format(i)} for i in range(5)])
    sent = []
    monkeypatch.setattr(target.requests, "delete", _fake_delete(sent))

    units = [{"unit_id": "NEW", "pnu": PNU_1}]
    assert _call(units, {PNU_1: 1}, delete_chunk=2) == 5
    assert len(sent) == 3          # 2 + 2 + 1


def test_delete_stale_units_chunks_pnu_lookups(monkeypatch):
    counts = {str(i).zfill(19): 1 for i in range(5)}
    _progress_says_complete(monkeypatch, counts)
    queries = []
    monkeypatch.setattr(
        target, "rest_select",
        lambda base, h, table, query, **kw: (queries.append(query) or []))

    units = [{"unit_id": "U{}".format(i), "pnu": str(i).zfill(19)} for i in range(5)]
    assert _call(units, counts, pnu_chunk=2) == 0
    assert len(queries) == 3


def test_delete_stale_units_wraps_network_error(monkeypatch):
    _progress_says_complete(monkeypatch, {PNU_1: 1})
    monkeypatch.setattr(target, "rest_select", lambda *a, **kw: [{"unit_id": "OLD"}])

    def boom(url, params=None, headers=None, timeout=None):
        raise target.requests.exceptions.ConnectionError("연결 끊김")

    monkeypatch.setattr(target.requests, "delete", boom)
    with pytest.raises(RuntimeError, match="다시 실행하면"):
        _call([{"unit_id": "NEW", "pnu": PNU_1}], {PNU_1: 1})


def test_delete_stale_units_raises_on_bad_status(monkeypatch):
    _progress_says_complete(monkeypatch, {PNU_1: 1})
    monkeypatch.setattr(target, "rest_select", lambda *a, **kw: [{"unit_id": "OLD"}])
    monkeypatch.setattr(target.requests, "delete", _fake_delete([], status=400))
    with pytest.raises(RuntimeError, match="옛 행 삭제"):
        _call([{"unit_id": "NEW", "pnu": PNU_1}], {PNU_1: 1})


# 아래 4개는 독립 코드리뷰가 지적한 HIGH 결함(원본이 불완전한데도 삭제가 도는
# 경로)의 회귀 테스트다. 삭제는 "그 PNU를 이번에 온전히 다시 계산했다"가
# 증명될 때만 돌아야 한다.


def _explode_on_delete(monkeypatch, why):
    monkeypatch.setattr(target, "rest_select", lambda *a, **kw: [{"unit_id": "OLD"}])

    def boom(*a, **kw):
        raise AssertionError(why)

    monkeypatch.setattr(target.requests, "delete", boom)


def test_delete_stale_units_skips_pnu_when_raw_row_count_mismatches(monkeypatch):
    """raw가 잘렸거나 일부 손상돼 행 수가 모자라면 그 PNU는 손대지 않는다.

    read_jsonl이 깨진 줄을 건너뛰고 나머지를 처리하므로 "행은 있는데 일부만"
    인 상태가 실제로 만들어진다. 그때 옛 행을 지우면 멀쩡한 라이브 행이 사라진다.
    """
    _progress_says_complete(monkeypatch, {PNU_1: 10})     # 수집 당시 10행
    _explode_on_delete(monkeypatch, "원본이 불완전하면 삭제하면 안 된다")
    units = [{"unit_id": "NEW", "pnu": PNU_1}]
    assert _call(units, {PNU_1: 7}) == 0                  # 지금 raw엔 7행뿐


def test_delete_stale_units_skips_pnu_not_marked_done(monkeypatch):
    """collect_progress에 done으로 안 찍힌 PNU는 삭제 범위에서 뺀다."""
    _progress_says_complete(monkeypatch, {})              # done 목록이 비어 있음
    _explode_on_delete(monkeypatch, "done이 아닌 PNU를 삭제하면 안 된다")
    assert _call([{"unit_id": "NEW", "pnu": PNU_1}], {PNU_1: 3}) == 0


def test_delete_stale_units_skips_pnu_with_unknown_row_count(monkeypatch):
    """row_count를 모르면(NULL) 판정 근거가 없으므로 지우지 않는다."""
    _progress_says_complete(monkeypatch, {})              # fetch가 None 행을 걸러낸 결과
    _explode_on_delete(monkeypatch, "판정 근거가 없으면 삭제하면 안 된다")
    assert _call([{"unit_id": "NEW", "pnu": PNU_1}], {PNU_1: 0}) == 0


def test_delete_stale_units_skips_truncated_pnu(monkeypatch):
    """페이지 상한(10,000행)에 잘린 PNU는 행 수가 맞아떨어져도 손대지 않는다.

    잘린 응답은 재수집 때 API가 같은 부분집합을 준다는 보장이 없다. 게다가
    collect_progress.row_count도 잘린 값이 그대로 저장돼 있어 행 수 대조만으론
    걸러지지 않는다 — 그래서 절단 목록을 따로 받아 제외한다.
    """
    _progress_says_complete(monkeypatch, {PNU_1: 10_000})
    _explode_on_delete(monkeypatch, "절단된 PNU를 삭제하면 안 된다")
    units = [{"unit_id": "NEW", "pnu": PNU_1}]
    # 행 수는 정확히 일치하지만 절단 목록에 있으므로 제외돼야 한다
    assert _call(units, {PNU_1: 10_000}, truncated={PNU_1}) == 0


def test_delete_stale_units_subset_raw_dir_deletes_nothing(monkeypatch):
    """--raw-dir로 부분집합 폴더를 가리켜도 파괴적이지 않다.

    부분집합 폴더는 PNU마다 행 수가 원래보다 적으므로 전부 완전성 검사에 걸린다.
    """
    pnus = [str(i).zfill(19) for i in range(3)]
    _progress_says_complete(monkeypatch, {p: 100 for p in pnus})
    _explode_on_delete(monkeypatch, "부분집합 raw로는 삭제하면 안 된다")
    units = [{"unit_id": "U{}".format(i), "pnu": p} for i, p in enumerate(pnus)]
    assert _call(units, {p: 5 for p in pnus}) == 0


def test_fetch_done_row_counts_drops_null_row_count(monkeypatch):
    """row_count가 비어 있는 행은 아예 안 돌려준다 — 모르면 지우지 않기 위해서."""
    monkeypatch.setattr(target, "rest_select", lambda *a, **kw: [
        {"scope_key": "A", "row_count": 12},
        {"scope_key": "B", "row_count": None},
        {"scope_key": None, "row_count": 3},
    ])
    assert target.fetch_done_row_counts("https://x.supabase.co", {}, PERIOD) == {"A": 12}


def test_fetch_done_row_counts_filters_to_done_and_period(monkeypatch):
    queries = []
    monkeypatch.setattr(
        target, "rest_select",
        lambda base, h, table, query, **kw: (queries.append((table, query)) or []))
    target.fetch_done_row_counts("https://x.supabase.co", {}, "202609")
    table, query = queries[0]
    assert table == "collect_progress"
    assert "status=eq.done" in query
    assert "period_key=eq.202609" in query
    assert "collector=eq.{}".format(target.BLDRGST_COLLECTOR) in query


def test_count_raw_rows_by_pnu_sums_across_files():
    title = [{"pnu": "A"}, {"pnu": "B"}]
    flr = [{"pnu": "A"}, {"pnu": "A"}]
    expos = [{"pnu": "B"}, {"pnu": "C"}]
    assert target.count_raw_rows_by_pnu(title, flr, expos) == {"A": 3, "B": 2, "C": 1}


def test_report_join_rate_output(monkeypatch, capsys):
    monkeypatch.setattr(
        target, "fetch_pnu_set",
        lambda base_url, headers, table, query: (
            {PNU_A, PNU_B, PNU_MOUNTAIN} if table == "parcel" else {PNU_A}),
    )
    monkeypatch.setattr(target, "rest_count", lambda *a, **kw: 4)
    monkeypatch.setattr(
        target, "fetch_pnu_list",
        lambda *a, **kw: [PNU_A, PNU_A, PNU_B, PNU_MOUNTAIN],
    )
    monkeypatch.setattr(
        target, "fetch_progress_status_sets",
        lambda *a, **kw: {"done": {PNU_A, PNU_B, PNU_MOUNTAIN}, "pending": set(), "failed": set()},
    )

    target.report_join_rate("https://x.supabase.co", {}, "11680", "202603", "202608", {PNU_A, PNU_B})

    out = capsys.readouterr().out
    assert "33.33%" in out      # (b) done PNU 중 조인 1 / 3
    assert "50.00%" in out      # ②(a)(b) 점포행 — 이 시나리오는 done 커버리지 100%라 우연히 같은 값
    assert "산" in out          # 사유 분류에 산지가 나온다
    assert "잠정치" not in out  # 커버리지 100% — 보류 배너가 없어야 한다


def test_report_join_rate_ub_join_rate_excludes_non_done_pnus(monkeypatch, capsys):
    """②(b) 분모는 done PNU에 속한 점포 행만 — 미수집(pending) PNU의 행이 섞이면
    안 된다(2026-08-08 라이브 적재 후 발견된 수정 3 회귀 가드).

    PNU_A(done, building 있음) 행 2개 + PNU_B(pending, building 없음) 행 2개를
    섞어, ②(b) 분모가 4가 아니라 done 행만인 2여야 함을 확인한다.
    """
    monkeypatch.setattr(
        target, "fetch_pnu_set",
        lambda base_url, headers, table, query: (
            {PNU_A, PNU_B} if table == "parcel" else {PNU_A}),
    )
    monkeypatch.setattr(target, "rest_count", lambda *a, **kw: 4)
    monkeypatch.setattr(
        target, "fetch_pnu_list",
        lambda *a, **kw: [PNU_A, PNU_A, PNU_B, PNU_B],
    )
    monkeypatch.setattr(
        target, "fetch_progress_status_sets",
        lambda *a, **kw: {"done": {PNU_A}, "pending": {PNU_B}, "failed": set()},
    )

    target.report_join_rate("https://x.supabase.co", {}, "11680", "202603", "202608", {PNU_A})

    out = capsys.readouterr().out
    assert "    2 / 4  ->  50.00%" in out               # ②(a) 커버리지: done 행 2 / 전체 4
    assert "    2 / 2  ->  100.00%  [달성]" in out       # ②(b) 조인률: PNU_B의 미수집 행 2건이 분모에서 빠졌다


def test_report_join_rate_no_pending_banner_when_coverage_full(monkeypatch, capsys):
    """수집 커버리지가 100%면 ①·② 어디에도 '잠정치' 보류 배너가 뜨면 안 된다."""
    monkeypatch.setattr(
        target, "fetch_pnu_set",
        lambda base_url, headers, table, query: (
            {PNU_A, PNU_B} if table == "parcel" else {PNU_A, PNU_B}),
    )
    monkeypatch.setattr(target, "rest_count", lambda *a, **kw: 2)
    monkeypatch.setattr(target, "fetch_pnu_list", lambda *a, **kw: [PNU_A, PNU_B])
    monkeypatch.setattr(
        target, "fetch_progress_status_sets",
        lambda *a, **kw: {"done": {PNU_A, PNU_B}, "pending": set(), "failed": set()},
    )

    target.report_join_rate("https://x.supabase.co", {}, "11680", "202603", "202608", {PNU_A, PNU_B})

    out = capsys.readouterr().out
    assert "잠정치" not in out


def test_report_join_rate_shows_coverage_warning_when_not_all_done(monkeypatch, capsys):
    monkeypatch.setattr(
        target, "fetch_pnu_set",
        lambda base_url, headers, table, query: (
            {PNU_A, PNU_B} if table == "parcel" else {PNU_A}),
    )
    monkeypatch.setattr(target, "rest_count", lambda *a, **kw: 0)
    monkeypatch.setattr(target, "fetch_pnu_list", lambda *a, **kw: [])
    monkeypatch.setattr(
        target, "fetch_progress_status_sets",
        lambda *a, **kw: {"done": {PNU_A}, "pending": {PNU_B}, "failed": set()},
    )

    target.report_join_rate("https://x.supabase.co", {}, "11680", "202603", "202608", {PNU_A})

    out = capsys.readouterr().out
    assert "잠정치" in out            # 커버리지 미달 경고
    assert "미수집(pending)" in out   # PNU_B가 building 없는 이유는 pending — 정규화 결함이 아니다


def test_parse_args_defaults_and_overrides():
    opts = target.parse_args([])
    assert opts["sigungu_code"] == "11680"
    assert opts["snapshot_ym"] == "202603"
    assert opts["raw_dir"].endswith(os.path.join("bldrgst", "202608"))

    opts2 = target.parse_args(["--raw-dir", "X", "--snapshot-ym", "202606", "--dry-run"])
    assert opts2["raw_dir"] == "X"
    assert opts2["snapshot_ym"] == "202606"
    assert opts2["dry_run"] is True


def test_parse_args_missing_value():
    with pytest.raises(ValueError, match="뒤에 값이 필요"):
        target.parse_args(["--raw-dir"])


def test_main_dry_run_does_not_touch_db(tmp_path, monkeypatch, capsys):
    raw_dir = _write_raw(
        tmp_path,
        title=[raw_row(PNU_A, TITLE_ITEM)],
        flr=[raw_row(PNU_A, flr_item())],
        expos=[raw_row(PNU_A, expos_item())],
    )

    def boom(*a, **kw):
        raise AssertionError("--dry-run 은 DB에 손대면 안 된다")

    monkeypatch.setattr(target, "get_supabase_config", boom)
    monkeypatch.setattr(target, "upsert_batch", boom)
    monkeypatch.setattr(sys, "argv", ["prog", "--raw-dir", raw_dir, "--dry-run"])

    assert target.main() == 0
    out = capsys.readouterr().out
    assert "building" in out
    assert "DB 적재" in out


def test_main_returns_1_when_raw_dir_missing(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog", "--raw-dir", "없는폴더", "--dry-run"])
    assert target.main() == 1


def test_main_loads_and_reports(tmp_path, monkeypatch, capsys):
    raw_dir = _write_raw(
        tmp_path,
        title=[raw_row(PNU_A, TITLE_ITEM)],
        flr=[raw_row(PNU_A, flr_item())],
        expos=[raw_row(PNU_A, expos_item())],
    )
    sent = {}
    monkeypatch.setattr(target, "get_supabase_config", lambda: ("https://x.supabase.co", "k"))
    monkeypatch.setattr(
        target, "upsert_batch",
        lambda base_url, headers, table, rows, batch_size=target.BATCH_SIZE: (
            sent.__setitem__(table, len(rows)) or len(rows)),
    )
    monkeypatch.setattr(target, "report_join_rate", lambda *a, **kw: None)
    # 적재 뒤 옛 unit 행 정리가 DB를 조회한다 — 기존 행이 없는 상태로 흉내낸다.
    monkeypatch.setattr(target, "rest_select", lambda *a, **kw: [])
    monkeypatch.setattr(sys, "argv", ["prog", "--raw-dir", raw_dir])

    assert target.main() == 0
    assert sent == {"building": 1, "unit": 1}
    out = capsys.readouterr().out
    assert "적재 완료" in out
    assert "옛 unit 0행 정리" in out
