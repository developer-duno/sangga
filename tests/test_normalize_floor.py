# -*- coding: utf-8 -*-
"""
scripts/normalize_floor.py 1:1 단위 테스트.

공용 설정 파일(conftest.py 등) 없이 이 파일 안에서 import 경로를 직접 해결한다
(tests/test_download_sangkwon_history.py와 동일한 방식).
"""

import os
import sys

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from normalize_floor import ROOFTOP, floor_label, normalize_floor  # noqa: E402


# ── 1. 규격 기본 케이스 (지상 / 지하 / 옥탑 / 불명) ──────────────────────────


class TestSpecBasics:
    def test_ground_floor_plain_number(self):
        assert normalize_floor("1") == 1
        assert normalize_floor("3층") == 3
        assert normalize_floor("지상3층") == 3

    def test_basement_with_digeuk_prefix(self):
        assert normalize_floor("지하1층") == -1
        assert normalize_floor("지하2층") == -2
        assert normalize_floor("지하 1 층") == -1  # 공백 섞인 표기

    def test_basement_ji_abbreviation(self):
        """'지1층'은 지하1층 약칭 — 지상으로 읽으면 부호가 뒤집힌다.

        건축물대장 전유공용면적의 flrNoNm에서 '지1층'·'지4-지3' 형태로 실제
        관측된다(2026-08-07 강남구 실측). '지상'은 걸리지 않아야 한다.
        """
        assert normalize_floor("지1층") == -1
        assert normalize_floor("지2층") == -2
        assert normalize_floor("지 3 층") == -3
        assert normalize_floor("지4") == -4
        # '지상'은 지하 약칭이 아니다 (회귀 방지)
        assert normalize_floor("지상2층") == 2
        assert normalize_floor("지상10층") == 10

    def test_basement_ji_abbreviation_ranges(self):
        """약칭이 범위로 올 때도 지하로 읽고 대표층은 가장 깊은 층."""
        assert normalize_floor("지4-지3") == -4
        assert normalize_floor("지5~지3, 지1") == -5
        assert normalize_floor("지8-지1") == -8

    def test_basement_b_prefix(self):
        assert normalize_floor("B1") == -1
        assert normalize_floor("B2") == -2
        assert normalize_floor("B9") == -9
        assert normalize_floor("b3") == -3  # 소문자도 인식

    def test_basement_leading_minus(self):
        assert normalize_floor("-1") == -1
        assert normalize_floor("-2") == -2

    def test_rooftop(self):
        assert normalize_floor("옥탑") == ROOFTOP
        assert normalize_floor("옥상") == ROOFTOP
        assert normalize_floor("R") == ROOFTOP
        assert normalize_floor("옥탑1") == ROOFTOP
        assert ROOFTOP == 99

    def test_floor_with_f_suffix(self):
        assert normalize_floor("1F") == 1
        assert normalize_floor("2f") == 2

    def test_unknown_returns_none(self):
        assert normalize_floor(None) is None
        assert normalize_floor("") is None
        assert normalize_floor("   ") is None
        assert normalize_floor("-") is None
        assert normalize_floor("없음") is None
        assert normalize_floor("nan") is None
        assert normalize_floor("None") is None


# ── 2. 0 절대 금지 (프로젝트 CLAUDE.md 절대 규칙 + DB CHECK 제약) ───────────


class TestZeroForbidden:
    def test_literal_zero_is_none_not_zero(self):
        assert normalize_floor("0") is None
        assert normalize_floor("00") is None
        assert normalize_floor(0) is None

    def test_no_input_ever_produces_zero_property_style(self):
        """어떤 입력을 넣어도 0이 나오면 안 된다 — 규격 절대 규칙의 핵심.

        실측 345종 원시값 + 대표 케이스 + 경계값을 전부 모아 한 번에 검증한다
        (특정 값 하나만 통과시키는 whack-a-mole 방지).
        """
        candidates = [
            "0", "00", "000", 0, "-0", "지하0층", "B0", "0층", "0F",
            "1", "2", "10", "99", "100", "101", "지", "반", "반지층",
            "B1", "B103", "옥탑", None, "", "-", "1,2층", "1~3층",
            "지하1~3층", "15015", "8106", "1230",
        ]
        for c in candidates:
            result = normalize_floor(c)
            assert result != 0, "normalize_floor({!r}) == 0 이면 절대 규칙 위반".format(c)


# ── 3. 실데이터 대표 유형 (2026Q1 상권정보 345종 실측 기반) ────────────────


class TestRealDataRepresentativeTypes:
    """scripts/floor_values_2026q1.txt 실측(2026-08-07)에서 뽑은 대표 유형.

    빈도 상위 값(순수 숫자 '1'~'46' 등)과 특이 유형('지', '반', 'B1'~'B9',
    '01' 같은 zero-pad, '101'/'B103'/'15015' 같은 3자리+ 애매값)을 모두
    실측 원시 문자열 그대로 검증한다.
    """

    @pytest.mark.parametrize(
        "raw,expected",
        [
            # 순수 숫자 (빈도 최상위 10종, floor_values_2026q1.txt 기준)
            ("1", 1), ("2", 2), ("3", 3), ("4", 4), ("5", 5),
            ("6", 6), ("7", 7), ("8", 8), ("9", 9), ("10", 10),
            ("11", 11), ("20", 20), ("46", 46), ("98", 98),
            # zero-pad 두 자리 (int() 변환 시 앞자리 0 자동 제거)
            ("01", 1), ("02", 2), ("09", 9),
            # B + 한 자리 지하
            ("B1", -1), ("B2", -2), ("B3", -3), ("B4", -4), ("B9", -9),
        ],
    )
    def test_mapped_values(self, raw, expected):
        assert normalize_floor(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "지",  # 지하/지상 방향만 있고 숫자가 없어 판정 불가 (실측 13,358건 — 최다 미커버)
            "0",  # 절대 규칙: 0 금지
            "101", "102", "201", "202", "301", "401", "501", "601", "701",  # 층+호 복합 의심 (100 이상)
            "B103", "B120", "B105",  # 지하 + 3자리 (지하103층은 물리적으로 불가능)
            "15015", "8106", "6137", "4559",  # 명백한 이상값
            "1230", "1801", "1901",  # 4자리 (역시 100 이상)
        ],
    )
    def test_ambiguous_values_return_none(self, raw):
        assert normalize_floor(raw) is None

    def test_banjiha_semi_basement_mapped_to_b1(self):
        """반지하/반지층은 규격에 없는 케이스라 이 파일의 판단(-1)을 명시적으로 검증.

        국토교통부·한국부동산원 자료에서도 반지하를 지하로 분류하는 관행을 따름
        (근거는 scripts/normalize_floor.py의 BANJIHA_FLOOR 주석 참고).
        """
        assert normalize_floor("반") == -1
        assert normalize_floor("반지층") == -1
        assert normalize_floor("반지하") == -1


# ── 4. 경계값 (빈 문자열 · 공백 · 숫자만 · 음수 문자열) ─────────────────────


class TestBoundaryValues:
    def test_empty_and_whitespace(self):
        assert normalize_floor("") is None
        assert normalize_floor(" ") is None
        assert normalize_floor("\t") is None
        assert normalize_floor("  \n ") is None

    def test_digits_only_no_unit(self):
        assert normalize_floor("5") == 5
        assert normalize_floor("-5") == -5

    def test_negative_number_strings(self):
        assert normalize_floor("-1") == -1
        assert normalize_floor("-10") == -10
        # 음수 100 이상도 애매값 규칙 적용 (절대값 기준)
        assert normalize_floor("-101") is None

    def test_non_numeric_garbage(self):
        assert normalize_floor("abc") is None
        assert normalize_floor("층") is None
        assert normalize_floor("!!!") is None

    def test_huge_number_treated_as_ambiguous(self):
        # 실측 최댓값급 이상치 — 물리적으로 불가능한 층수는 None
        assert normalize_floor("15015") is None
        assert normalize_floor("999999") is None

    def test_none_and_non_string_types(self):
        assert normalize_floor(None) is None
        assert normalize_floor(1) == 1
        assert normalize_floor(-1) == -1


# ── 5. 복합 표기 ("1,2층" · "1~3층" 등, 스킬 규격 외 — 대표층=최저층 판단) ──


class TestCompoundNotation:
    def test_comma_separated_picks_lowest(self):
        assert normalize_floor("1,2층") == 1
        assert normalize_floor("1,2,3") == 1

    def test_tilde_range_picks_lowest(self):
        assert normalize_floor("1~3층") == 1

    def test_basement_range_context_carries_forward(self):
        """'지하1~3층'은 뒷조각(3층)에도 지하 문맥이 적용돼 지하3층까지 포함.

        대표층 선택 시 더 깊은 지하(-3)가 '최저층'이 된다.
        """
        assert normalize_floor("지하1~3층") == -3

    def test_compound_with_unmappable_fragment_falls_back(self):
        # 한쪽 조각이 판정 불가(예: 101)여도 나머지 조각으로 판정
        assert normalize_floor("1,101") == 1

    def test_comma_does_not_propagate_basement_context_regression(self):
        """MEDIUM 2 회귀 방지 — ','·'/'(열거)로 이어진 조각은 지하 문맥을

        물려받지 않는다. "지하1층,2층"은 지하1층과 2층(지상) 두 곳을 나열한
        것이지 지하1층·지하2층이 아니다(수정 전에는 -2가 나왔음).
        """
        assert normalize_floor("지하1층,2층") == -1
        assert normalize_floor("B1,2") == -1

    def test_tilde_still_propagates_basement_context(self):
        """','와 달리 '~'(범위)는 여전히 지하 문맥을 뒷조각까지 물려준다."""
        assert normalize_floor("지하1~3층") == -3


# ── 6. floor_label 보조 함수 (사람이 읽는 표기 역변환) ──────────────────────


class TestFloorLabel:
    def test_labels(self):
        assert floor_label(None) == "층 정보 없음"
        assert floor_label(1) == "1층"
        assert floor_label(-1) == "지하 1층"
        assert floor_label(ROOFTOP) == "옥탑"
