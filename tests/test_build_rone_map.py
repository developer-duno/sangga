# -*- coding: utf-8 -*-
"""
scripts/build_rone_map.py 단위 테스트

DB 없이 검증한다:
  1. 정규화        — 꼬리 시설어를 **반복해서** 뗀다 / 너무 짧아지면 안 뗀다
  2. 별칭 분해     — 괄호·쉼표·점 안에 든 별칭을 잃지 않는다 (방산시장이 실제로 그랬다)
  3. `/` 분리      — "용문/한민시장" 은 두 상권이다
  4. ★ 서울 권역 관문 — 도심>동대문 이 **동대문구** 기관을 끌어오지 못하게 막는다
                        (이 관문을 빼면 후보가 오염된다 — 사보타주 테스트로 확인)
  5. 앞말 겹침     — ★ "포함"이 아니라 "앞말". 면목동우체국 ↛ 목동
  6. 후보 선별     — 비긴 짝은 자동 확정하지 않는다 / 점수 낮은 앞말은 사람 대기
  7. 귀무가설      — 글자를 섞으면 매칭이 줄어야 한다 (판별력 확인)

conftest.py를 새로 만들지 않기 위해 sys.path 조작은 이 파일 안에서만 한다.
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.join(_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import build_rone_map as B  # noqa: E402


def d(did, nm, gu):
    return {"district_id": did, "district_nm": nm, "district_type": "골목상권",
            "sigungu_code": gu}


def leaf(path):
    leaves, _ = B.parse_rone_paths([path])
    return leaves[0]


# ── 1. 정규화 ────────────────────────────────────────────────────────────────


def test_normalize_strips_repeated_tail_words():
    """★ 한 번만 떼면 '네거리'가 남는다. 반복해서 떼야 목원대가 된다."""
    assert B.normalize("목원대네거리 정류장") == "목원대"


def test_normalize_strips_exit_number():
    assert B.normalize("노은역3번 출구") == "노은"


def test_normalize_keeps_name_when_stripping_would_gut_it():
    """다 떼면 아무것도 안 남는 이름은 그대로 둔다 (한 글자는 아무 데나 걸린다)."""
    assert B.normalize("정류장") == "정류장"
    assert B.normalize("공원") == "공원"


def test_normalize_known_overstrip_is_documented():
    """★ 알려진 과잉 제거: "대전역" → "대전".

    "노은역" → "노은" 과 글자 수가 같아 규칙으로는 못 가른다(지명 사전이 필요하다).
    해가 없는 이유는 **R-ONE 대전 이름 중 "대전"으로 시작하는 표준형이 없기** 때문이다
    (대전원도심·대전동구청은 시도 접두를 떼어 원도심·동구청이 된다). 이 전제가 깨지면
    이 테스트가 먼저 눈에 띄라고 남겨 둔다.
    """
    assert B.normalize("대전역") == "대전"
    for leaf_nm in ("대전원도심", "대전동구청", "둔산", "가수원"):
        assert not B.normalize(leaf_nm, "대전").startswith("대전")


def test_normalize_strips_sido_prefix_only_for_that_sido():
    """대전 자료는 이름에 시도를 달고 온다. R-ONE 은 '둔산' 이라 떼야 이어진다."""
    assert B.normalize("대전둔산초등학교", "대전") == "둔산"
    assert B.normalize("대전둔산초등학교") == "대전둔산"


def test_normalize_does_not_strip_market():
    """★ '시장' 은 이름의 일부다(한민시장·중리전통시장). 떼면 다른 상권이 된다."""
    assert B.normalize("한민시장") == "한민시장"


# ── 2. 별칭 분해 ─────────────────────────────────────────────────────────────


def test_alias_keeps_parenthesized_alias():
    """★ 괄호를 버리면 R-ONE 과 **정확히 같은 이름**을 잃는다 (방산시장 실제 사례)."""
    assert "방산시장" in B.alias_names("방산종합시장(방산시장)")


def test_alias_splits_comma_inside_parens():
    got = B.alias_names("수유전통시장(수유시장, 수유골목시장)")
    assert "수유시장" in got and "수유골목시장" in got


def test_alias_splits_dot():
    assert "가수원시장 정류장" in B.alias_names("가수원육교.가수원시장 정류장")


# ── 3. `/` 분리 ──────────────────────────────────────────────────────────────


def test_rone_alt_names_splits_slash_and_keeps_whole():
    got = B.rone_alt_names("용문/한민시장")
    assert got[0] == "용문/한민시장"
    assert "용문" in got and "한민시장" in got


# ── 4. ★ 서울 권역 관문 ──────────────────────────────────────────────────────


def test_gate_blocks_other_gu_for_dosim():
    """★ 도심 상권은 종로·중구다. 동대문**구**(11230)의 기관을 끌어오면 안 된다."""
    assert B.passes_gate(leaf("서울>도심>동대문"), "11230") is False
    assert B.passes_gate(leaf("서울>도심>동대문"), "11110") is True


def test_gate_allows_seocho_under_gangnam_region():
    """★ '강남' 은 구가 아니라 **권역**이다. 교대역·서래마을은 서초구(11650)다 —
    구로 걸었으면 통째로 걸러졌다."""
    assert B.passes_gate(leaf("서울>강남>교대역"), "11650") is True


def test_gate_is_open_for_etc_region():
    """'기타' 는 서울 전역을 담는 자루라 관문을 걸지 않는다."""
    assert B.allowed_sigungu(leaf("서울>기타>수유")) is None
    assert B.passes_gate(leaf("서울>기타>수유"), "11740") is True


def test_gate_blocks_other_sido():
    assert B.passes_gate(leaf("대전>둔산"), "11680") is False
    assert B.passes_gate(leaf("서울>도심>종로"), "30170") is False


def test_gu_table_matches_the_data_we_feed():
    with pytest.raises(ValueError) as e:
        B.assert_gu_table_matches_data([d("x", "어딘가", "11999")])
    assert "11999" in str(e.value)


def test_gu_table_has_25_seoul_gu():
    assert len(B.SEOUL_GU_CODE) == 25
    assert len(set(B.SEOUL_GU_CODE.values())) == 25


def test_region_gu_names_are_real_gu():
    """권역 표가 오타로 죽은 이름을 들고 있으면 관문이 KeyError 로 죽는다."""
    for gus in B.SEOUL_REGION_GU.values():
        for g in gus or ():
            assert g in B.SEOUL_GU_CODE, g


# ── 5. ★ 앞말 겹침 (포함이 아니다) ───────────────────────────────────────────


def test_prefix_not_substring():
    """★ '포함'으로 열면 면목동우체국이 목동에 걸린다 (2026-08-14 실측)."""
    assert B.score_pair("면목동우체국", "목동") is None


def test_prefix_matches_forward():
    got = B.score_pair("수유북부시장", "수유")
    assert got[0] == "token" and got[1] == pytest.approx(2 / 6.0, abs=1e-4)


def test_prefix_matches_backward():
    """R-ONE 쪽이 더 긴 경우도 이어야 한다 ('혜화역' ↔ '혜화동')."""
    got = B.score_pair("혜화역 1번", "혜화동")
    assert got[0] == "token"


def test_exact_beats_normalized():
    assert B.score_pair("약수역", "약수역") == ("exact", 1.0)
    assert B.score_pair("약수역 7번", "약수역")[0] == "normalized"


def test_one_letter_names_never_match():
    """한 글자는 아무 데나 걸린다 — 짝짓기에 쓰지 않는다."""
    assert B.score_pair("가", "가나다") is None


# ── 6. 후보 선별 ─────────────────────────────────────────────────────────────


def test_same_leaf_in_two_regions_confirms_both_paths():
    """★ 잎 이름은 같은데 권역만 다르면 **둘 다** 확정한다 (고르는 문제가 아니다).

    부동산원이 bld_type 마다 서울 권역 분할을 달리해 오피스는 여의도마포, 상가는
    영등포신촌에 같은 상권이 있다(라이브 실측 2026-08-14). 하나만 고르면 나머지 종류의
    통계가 통째로 사라진다 — district_rone_map 의 PK 가 복합인 이유다.
    """
    districts = [d("D1", "공덕역", "11440")]
    leaves, _ = B.parse_rone_paths(["서울>여의도마포>공덕역", "서울>영등포신촌>공덕역"])
    got = B.build_candidates(districts, leaves)
    assert got["ambiguous"] == []
    assert sorted(r["rone_region_nm"] for r in got["confirmed"]) == [
        "서울>여의도마포>공덕역", "서울>영등포신촌>공덕역"]
    assert all(r["note"] for r in got["confirmed"]), "이중 권역이라는 표시가 없습니다"


def test_tie_between_different_leaves_still_waits_for_a_human():
    """★ 잎 **이름이 다른** 비김은 여전히 사람이 골라야 한다(강남대로 vs 학동/강남구청역)."""
    districts = [d("D1", "강남역", "11650")]
    leaves, _ = B.parse_rone_paths(["서울>강남>강남대로", "서울>강남>학동/강남구청역"])
    got = B.build_candidates(districts, leaves)
    assert got["confirmed"] == []
    assert len(got["ambiguous"]) == 1
    assert "비김" in got["ambiguous"][0]["reason"]


def test_low_score_prefix_waits_for_a_human():
    districts = [d("D1", "명동 남대문 북창동 다동 무교동 관광특구", "11140")]
    leaves, _ = B.parse_rone_paths(["서울>도심>명동"])
    got = B.build_candidates(districts, leaves)
    assert got["confirmed"] == []
    assert len(got["ambiguous"]) == 1


def test_confirmed_carries_method_and_evidence():
    districts = [d("D1", "노은역3번 출구", "30200")]
    leaves, _ = B.parse_rone_paths(["대전>노은"])
    got = B.build_candidates(districts, leaves)
    assert len(got["confirmed"]) == 1
    assert got["confirmed"][0]["rone_region_nm"] == "대전>노은"
    assert got["confirmed"][0]["evidence"]


def test_unmatched_leaves_are_reported():
    districts = [d("D1", "노은역3번 출구", "30200")]
    leaves, _ = B.parse_rone_paths(["대전>노은", "대전>관평동"])
    got = B.build_candidates(districts, leaves)
    assert got["unmatched"] == ["대전>관평동"]


def test_parse_rone_paths_keeps_parents_out_of_leaves():
    """서울 2단계(권역)는 상위 근사용이라 매핑 대상이 아니다."""
    leaves, parents = B.parse_rone_paths(["서울>도심", "서울>도심>명동", "대전>둔산", "서울"])
    assert [x["path"] for x in leaves] == ["서울>도심>명동", "대전>둔산"]
    assert parents == ["서울>도심", "서울"]


# ── 7. ★ 가드 사보타주 — 관문을 빼면 후보가 오염되나 ─────────────────────────


def test_removing_the_region_gate_pollutes_candidates(monkeypatch):
    """★ 이 테스트가 없으면 관문이 헛돌아도 아무도 모른다.

    권역 관문을 없앤 것처럼 꾸미고(모든 권역을 '전역'으로) 같은 자료를 돌리면,
    도심>동대문 이 동대문**구**의 구청·경찰서를 후보로 끌어와야 한다.
    """
    districts = [d("D1", "동대문구청", "11230"), d("D2", "동대문경찰서", "11230")]
    leaves, _ = B.parse_rone_paths(["서울>도심>동대문"])

    with_gate = B.build_candidates(districts, leaves)
    assert with_gate["confirmed"] == [] and with_gate["ambiguous"] == []

    monkeypatch.setattr(B, "SEOUL_REGION_GU", {k: None for k in B.SEOUL_REGION_GU})
    without_gate = B.build_candidates(districts, leaves)
    assert len(without_gate["confirmed"]) + len(without_gate["ambiguous"]) == 2, (
        "관문을 빼도 후보가 안 늘었습니다 — 관문이 애초에 아무것도 안 거르고 있습니다")


# ── 7-b. 동명이인 짚기 (기타 권역은 관문이 없어 이것이 유일한 그물이다) ──────


def test_minority_gu_is_flagged():
    """★ 실제로 잡힌 오염: 홍대부중(성북구)은 마포구 홍대 상권이 아니다."""
    conf = [
        {"district_id": "A", "district_nm": "홍대입구역", "sigungu_code": "11440",
         "rone_region_nm": "서울>기타>홍대/합정", "match_method": "exact", "score": 1.0},
        {"district_id": "B", "district_nm": "홍대땡땡거리", "sigungu_code": "11440",
         "rone_region_nm": "서울>기타>홍대/합정", "match_method": "token", "score": 0.4},
        {"district_id": "C", "district_nm": "홍대부중", "sigungu_code": "11290",
         "rone_region_nm": "서울>기타>홍대/합정", "match_method": "token", "score": 0.5},
    ]
    got = B.flag_minority_gu(conf)
    assert [r["district_id"] for r in got] == ["C"]


def test_minority_gu_needs_a_real_majority():
    """★ 구가 전부 하나씩이면 '다수'가 없다 — 아무나 지목하면 헛경보다(장안동 사례)."""
    conf = [
        {"district_id": "A", "district_nm": "장안초등학교", "sigungu_code": "11215",
         "rone_region_nm": "서울>기타>장안동", "match_method": "token", "score": 0.6},
        {"district_id": "B", "district_nm": "장안중학교", "sigungu_code": "11260",
         "rone_region_nm": "서울>기타>장안동", "match_method": "token", "score": 0.6},
        {"district_id": "C", "district_nm": "장안동사거리", "sigungu_code": "11230",
         "rone_region_nm": "서울>기타>장안동", "match_method": "normalized", "score": 1.0},
    ]
    assert B.flag_minority_gu(conf) == []


def test_minority_gu_ignores_single_row_leaves():
    """붙은 상권이 하나뿐이면 비교할 다수가 없다 — 짚을 근거가 없다."""
    conf = [{"district_id": "A", "district_nm": "한티역", "sigungu_code": "11680",
             "rone_region_nm": "서울>강남>한티역", "match_method": "exact", "score": 1.0}]
    assert B.flag_minority_gu(conf) == []


# ── 7-c. ★ 경고를 눈으로 넘기는 것을 기계가 막는다 ───────────────────────────


def _flagged(did="3110223", nm="군자초등학교", path="서울>기타>군자"):
    return [{"district_id": did, "district_nm": nm, "sigungu_code": "11230",
             "rone_region_nm": path, "match_method": "normalized", "score": 1.0,
             "reason": "이 상권에서 혼자만 11230 (나머지 다수는 11215)"}]


def test_unreviewed_minority_catches_a_warning_left_in_the_seed():
    """★ 실제 사고: ②-b 가 군자초등학교를 경고했는데 사람이 넘기고 확정했다."""
    got = B.unreviewed_minority(_flagged(), {("3110223", "서울>기타>군자"): ""})
    assert [r["district_id"] for r in got] == ["3110223"]


def test_unreviewed_minority_passes_when_a_reason_is_written():
    """경계에 걸친 정당한 예외는 근거를 적으면 통과한다."""
    notes = {("3110223", "서울>기타>군자"): "구 경계 확인 — 경계에 걸친다"}
    assert B.unreviewed_minority(_flagged(), notes) == []


def test_unreviewed_minority_ignores_rows_already_dropped():
    """확정본에 아예 없으면 사람이 이미 뺀 것이다 — 막을 이유가 없다."""
    assert B.unreviewed_minority(_flagged(), {}) == []


def test_gu_review_mark_is_not_a_word_that_shows_up_by_accident():
    """표시가 흔한 말이면 아무 note 나 통과한다."""
    notes = {("3110223", "서울>기타>군자"): "앞말 겹침 0.5 (군자초등학교 ≈ 군자)"}
    assert len(B.unreviewed_minority(_flagged(), notes)) == 1


def test_low_score_dual_path_row_says_it_was_promoted():
    """★ 이중 권역 규칙은 점수 관문을 건너뛴다 — method 만 보고 오판하지 않게 적어 둔다."""
    districts = [d("D1", "홍대소상공인상점가", "11440")]
    leaves, _ = B.parse_rone_paths(["서울>기타>홍대/합정", "서울>영등포신촌>홍대/합정"])
    got = B.build_candidates(districts, leaves)
    assert len(got["confirmed"]) == 2
    for r in got["confirmed"]:
        assert r["match_method"] == "token" and r["score"] < B.TOKEN_CONFIRM_MIN
        assert "승격" in r["note"], r["note"]


# ── 8. 귀무가설 ──────────────────────────────────────────────────────────────


def test_scrambled_names_match_much_less():
    """그럴듯한 일치율이 판별력 0 일 수 있다 — 글자를 섞으면 줄어야 한다."""
    districts = [d("D1", "노은역3번 출구", "30200"), d("D2", "대전둔산초등학교", "30170"),
                 d("D3", "목원대네거리 정류장", "30170"),
                 d("D4", "유성온천역6번 출구", "30200")]
    leaves, _ = B.parse_rone_paths(["대전>노은", "대전>둔산", "대전>목원대", "대전>유성온천역"])
    real = B.build_candidates(districts, leaves)
    real_n = len(real["confirmed"]) + len(real["ambiguous"])
    fake_n = B.null_by_scrambled_names(districts, leaves, trials=5)
    assert real_n == 4
    assert fake_n < real_n, "글자를 섞어도 그대로 걸립니다 — 이름을 안 보고 있습니다"


def test_shuffle_leaf_chars_keeps_length():
    got = B.shuffle_leaf_chars("테헤란로", __import__("random").Random(1))
    assert len(got) == 4 and sorted(got) == sorted("테헤란로")
