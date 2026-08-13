# -*- coding: utf-8 -*-
"""
scripts/collectors/load_sangkwon_snapshot.py 단위 테스트

네트워크·Supabase 없이 순수 로직만 검증한다:
  1. detect_snapshot_ym — 파일명에서 기준월(YYYYMM) 추출
  2. format_jibun — 본번/부번 -> '358-1' 형식
  3. classify_invalid_pnu — PNU 무효 사유 분류
  4. build_col_index — 필요한 컬럼 누락 감지
  5. build_parcel_record / build_unit_business_record — 행 -> dict 변환
  6. scan_and_build — CSV 픽스처로 시군구 필터·PNU 중복제거·층 정규화 통합 동작
  7. estimate_bldrgst_scale — 건축물대장 API 호출 규모 산정(일 한도 분기)
  8. upsert_batch / rest_count — requests 흉내내어 배치·count 파싱만 검증

conftest.py를 새로 만들지 않기 위해(다른 수집기 작업과 충돌 방지),
sys.path 조작은 이 파일 안에서만 한다.
"""

import csv
import io
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

import load_sangkwon_snapshot as target  # noqa: E402


# ── 픽스처 도우미 ─────────────────────────────────────────────────────────────

HEADER = [
    "상가업소번호", "상호명", "지점명",
    "상권업종대분류코드", "상권업종대분류명",
    "상권업종중분류코드", "상권업종중분류명",
    "상권업종소분류코드", "상권업종소분류명",
    "표준산업분류코드",
    "시도명", "시군구코드", "시군구명",
    "법정동코드", "법정동명",
    "지번코드", "지번본번지", "지번부번지",
    "도로명주소",
    "층정보", "호정보",
    "경도", "위도",
]


def make_row(**overrides):
    """HEADER 순서에 맞는 기본값 행(list)을 만들고 overrides로 일부만 바꾼다."""
    base = {
        "상가업소번호": "MA0101202208008", "상호명": "테스트상회", "지점명": "",
        "상권업종대분류코드": "L1", "상권업종대분류명": "부동산",
        "상권업종중분류코드": "L102", "상권업종중분류명": "부동산 서비스",
        "상권업종소분류코드": "L10203", "상권업종소분류명": "부동산 중개/대리업",
        "표준산업분류코드": "L68221",
        "시도명": "서울특별시", "시군구코드": "11680", "시군구명": "강남구",
        "법정동코드": "1168010100", "법정동명": "역삼동",
        "지번코드": "1168010100108230004", "지번본번지": "823", "지번부번지": "4",
        "도로명주소": "서울특별시 강남구 테헤란로 1",
        "층정보": "3층", "호정보": "",
        "경도": "127.0365", "위도": "37.5008",
    }
    base.update(overrides)
    return [base[h] for h in HEADER]


def make_csv_bytes(rows, header=HEADER):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8-sig")


def write_csv(tmp_path, filename, rows, header=HEADER):
    path = os.path.join(str(tmp_path), filename)
    with open(path, "wb") as f:
        f.write(make_csv_bytes(rows, header))
    return path


# ── 1. detect_snapshot_ym ────────────────────────────────────────────────────


def test_detect_snapshot_ym_single_value():
    names = [
        "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv",
        "소상공인시장진흥공단_상가(상권)정보_경기_202603.csv",
    ]
    assert target.detect_snapshot_ym(names) == "202603"


def test_detect_snapshot_ym_no_match_raises():
    with pytest.raises(ValueError, match="스냅샷 기준월"):
        target.detect_snapshot_ym(["아무파일.csv"])


def test_detect_snapshot_ym_mismatch_raises():
    names = ["a_202603.csv", "b_202512.csv"]
    with pytest.raises(ValueError, match="서로 다릅니다"):
        target.detect_snapshot_ym(names)


# ── 2. format_jibun ───────────────────────────────────────────────────────────


def test_format_jibun_with_bubeon():
    assert target.format_jibun("358", "1") == "358-1"


def test_format_jibun_without_bubeon_blank():
    assert target.format_jibun("358", "") == "358"


def test_format_jibun_bubeon_zero_dropped():
    assert target.format_jibun("358", "0") == "358"


def test_format_jibun_no_bonbeon_returns_none():
    assert target.format_jibun("", "1") is None


# ── 3. classify_invalid_pnu ──────────────────────────────────────────────────


def test_classify_invalid_pnu_blank():
    assert target.classify_invalid_pnu("") == "빈 값"


def test_classify_invalid_pnu_wrong_length():
    assert "19자리가 아님" in target.classify_invalid_pnu("123")


def test_classify_invalid_pnu_non_digit():
    assert target.classify_invalid_pnu("116801010010823000X") == "숫자가 아닌 문자 포함"


def test_classify_invalid_pnu_valid_returns_etc_when_called_on_valid():
    # 이 함수는 무효로 판정된 값에 대해서만 호출되는 게 정상 흐름이지만,
    # 우연히 유효한 19자리 숫자가 들어와도 예외 없이 "기타"를 돌려줘야 한다.
    assert target.classify_invalid_pnu("1168010100108230004") == "기타"


# ── 4. build_col_index ───────────────────────────────────────────────────────


def test_build_col_index_ok():
    idx = target.build_col_index(HEADER, "test.csv")
    assert idx["지번코드"] == HEADER.index("지번코드")


def test_build_col_index_missing_raises():
    bad_header = [h for h in HEADER if h != "지번코드"]
    with pytest.raises(target.MissingColumnsError) as exc_info:
        target.build_col_index(bad_header, "test.csv")
    assert "지번코드" in exc_info.value.missing_cols


def test_build_col_index_strips_bom():
    header_with_bom = list(HEADER)
    header_with_bom[0] = "﻿" + header_with_bom[0]
    idx = target.build_col_index(header_with_bom, "test.csv")
    assert "상가업소번호" in idx


# ── 5. build_parcel_record / build_unit_business_record ─────────────────────


def test_build_parcel_record_basic():
    row = make_row()
    idx = target.build_col_index(HEADER, "t.csv")
    rec = target.build_parcel_record(row, idx)
    assert rec["pnu"] == "1168010100108230004"
    assert rec["sigungu_code"] == "11680"
    assert rec["jibun"] == "823-4"
    assert rec["lat"] == pytest.approx(37.5008)
    assert rec["lng"] == pytest.approx(127.0365)
    assert rec["geom"] == "SRID=4326;POINT(127.0365 37.5008)"


def test_build_parcel_record_missing_latlng_keeps_none_keys():
    # PostgREST 벌크 insert는 배치 안 다른 행이 갖는 키를 기준으로 컬럼을 잡으므로,
    # 좌표가 없어도 lat/lng/geom 키 자체는 유지하고 값만 None이어야 한다.
    row = make_row(경도="", 위도="")
    idx = target.build_col_index(HEADER, "t.csv")
    rec = target.build_parcel_record(row, idx)
    assert rec["lat"] is None
    assert rec["lng"] is None
    assert rec["geom"] is None


def test_build_unit_business_record_valid_pnu():
    row = make_row()
    idx = target.build_col_index(HEADER, "t.csv")
    rec = target.build_unit_business_record(row, idx, "202603", 3)
    assert rec["pnu"] == "1168010100108230004"
    assert rec["floor_no"] == 3
    assert rec["unit_id"] is None
    assert rec["ho"] is None
    assert rec["biz_name"] == "테스트상회"
    assert rec["cat_l_cd"] == "L1"


def test_build_unit_business_record_invalid_pnu_becomes_none():
    row = make_row(지번코드="짧은값")
    idx = target.build_col_index(HEADER, "t.csv")
    rec = target.build_unit_business_record(row, idx, "202603", 3)
    assert rec["pnu"] is None


def test_build_unit_business_record_missing_latlng_keeps_none_keys():
    row = make_row(경도="", 위도="")
    idx = target.build_col_index(HEADER, "t.csv")
    rec = target.build_unit_business_record(row, idx, "202603", 3)
    assert rec["lat"] is None
    assert rec["lng"] is None
    assert rec["geom"] is None


# ── 6. scan_and_build (파일 I/O, 네트워크·DB 없음) ───────────────────────────


def test_scan_and_build_filters_by_sigungu_and_dedupes_pnu(tmp_path):
    rows = [
        make_row(상가업소번호="A1", 시군구코드="11680", 지번코드="1168010100108230004", 층정보="3층"),
        make_row(상가업소번호="A2", 시군구코드="11680", 지번코드="1168010100108230004", 층정보="지하1층"),
        make_row(상가업소번호="B1", 시군구코드="11440", 지번코드="1144012300103580001", 층정보="1층"),
    ]
    write_csv(tmp_path, "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv", rows)

    result = target.scan_and_build(str(tmp_path), "11680", "202603")

    assert result["total_matched"] == 2  # 강남구(11680) 2건만, 마포구(11440) 제외
    assert len(result["unit_business_records"]) == 2
    assert len(result["parcel_records"]) == 1  # 같은 PNU 2건 -> parcel은 1건으로 중복제거
    floors = sorted(r["floor_no"] for r in result["unit_business_records"])
    assert floors == [-1, 3]


def test_scan_and_build_invalid_pnu_excluded_from_parcel_but_kept_in_unit_business(tmp_path):
    rows = [
        make_row(상가업소번호="C1", 시군구코드="11680", 지번코드=""),
    ]
    write_csv(tmp_path, "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv", rows)

    result = target.scan_and_build(str(tmp_path), "11680", "202603")

    assert len(result["parcel_records"]) == 0  # 빈 PNU -> parcel 후보 아님
    assert len(result["unit_business_records"]) == 1  # unit_business는 매칭실패 NULL 허용
    assert result["unit_business_records"][0]["pnu"] is None
    assert result["invalid_pnu_reasons"]["빈 값"] == 1


def test_scan_and_build_skips_file_with_missing_columns(tmp_path):
    bad_header = [h for h in HEADER if h != "지번코드"]
    row = [v for h, v in zip(HEADER, make_row()) if h != "지번코드"]
    write_csv(tmp_path, "이상한_202603.csv", [row], header=bad_header)

    result = target.scan_and_build(str(tmp_path), "11680", "202603")

    assert result["total_matched"] == 0
    assert len(result["skipped_files"]) == 1
    assert "지번코드" in result["skipped_files"][0][1]


def test_scan_and_build_raises_on_empty_dir(tmp_path):
    with pytest.raises(RuntimeError, match="CSV 파일이 없습니다"):
        target.scan_and_build(str(tmp_path), "11680", "202603")


def test_scan_and_build_counts_col_mismatch_skipped_rows(tmp_path):
    header_line = ",".join(HEADER)
    good_row = ",".join(make_row(상가업소번호="G1", 시군구코드="11680"))
    short_row = "너무짧은행,칸수부족"
    path = os.path.join(str(tmp_path), "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(header_line + "\n" + good_row + "\n" + short_row + "\n")

    result = target.scan_and_build(str(tmp_path), "11680", "202603")

    assert result["total_matched"] == 1
    assert result["col_mismatch_skipped"] == 1


def test_scan_and_build_no_duplicate_accumulation_on_mid_file_encoding_retry(tmp_path, monkeypatch):
    """utf-8-sig 시도가 헤더+1행만 읽은 뒤 중간에 UnicodeDecodeError로 끊기고
    cp949 재시도가 파일 전체를 처음부터 성공적으로 읽으면, utf-8-sig에서 이미
    읽었던 행이 남아 중복 축적되면 안 된다 (check_data_quality의
    "성공 시에만 반환" 패턴을 이 스크립트에도 적용한 것의 회귀 테스트).

    실제 인코딩 불일치로 진짜 디코딩 에러를 유도하면 어느 지점에서 끊길지
    제어할 수 없으므로, csv.reader 자체를 흉내내 끊기는 지점을 고정한다
    (파일 바이트 내용은 이 테스트에서 쓰이지 않음).
    """
    row1 = make_row(상가업소번호="D1", 시군구코드="11680", 지번코드="1168010100108230004")
    row2 = make_row(상가업소번호="D2", 시군구코드="11680", 지번코드="1168010100108230005")
    path = os.path.join(str(tmp_path), "cp949파일_202603.csv")
    with open(path, "wb") as f:
        f.write(b"")  # 내용은 안 쓰임 — csv.reader를 통째로 흉내낸다

    class _CannedIter:
        """rows_iter를 순서대로 내주다가 fail_after번째 호출부터 끊는다."""

        def __init__(self, rows, fail_after=None):
            self._it = iter(rows)
            self._n = 0
            self._fail_after = fail_after

        def __iter__(self):
            return self

        def __next__(self):
            if self._fail_after is not None and self._n >= self._fail_after:
                raise UnicodeDecodeError("utf-8-sig", b"\xff", 0, 1, "테스트 주입 실패")
            self._n += 1
            return next(self._it)

    def flaky_reader(fp):
        if getattr(fp, "encoding", None) == "utf-8-sig":
            return _CannedIter([HEADER, row1, row2], fail_after=2)  # 헤더+1행만
        return _CannedIter([HEADER, row1, row2])  # cp949는 끝까지 정상

    monkeypatch.setattr(target.csv, "reader", flaky_reader)

    result = target.scan_and_build(str(tmp_path), "11680", "202603")

    # cp949 재시도가 2행 전부를 정상 처리 — utf-8-sig에서 이미 읽은 1행이
    # 남아 있었다면 3행(중복)이 됐을 것.
    assert result["total_matched"] == 2
    assert len(result["unit_business_records"]) == 2
    assert len(result["parcel_records"]) == 2


# ── 6.5 전국 모드(--sigungu-code all) · 파일 단위 스트리밍 ──────────────────


@pytest.mark.parametrize("raw,expected", [
    ("all", True), ("ALL", True), (" all ", True),
    ("11680", False), ("", False), (None, False),
])
def test_is_all_sigungu(raw, expected):
    assert target.is_all_sigungu(raw) is expected


def test_scan_and_build_all_mode_takes_every_sigungu(tmp_path):
    rows = [
        make_row(상가업소번호="A1", 시군구코드="11680", 지번코드="1168010100108230004"),
        make_row(상가업소번호="B1", 시군구코드="11440", 지번코드="1144012300103580001"),
        make_row(상가업소번호="C1", 시군구코드="41135", 지번코드="4113512300103580001"),
    ]
    write_csv(tmp_path, "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv", rows)

    result = target.scan_and_build(str(tmp_path), "all", "202603")

    assert result["total_matched"] == 3          # 필터 없음 — 전부 통과
    assert result["parcel_count"] == 3
    assert result["unit_business_count"] == 3
    assert result["ub_with_pnu_count"] == 3


def test_scan_and_build_default_mode_still_filters(tmp_path):
    """전국 모드를 넣었다고 기본(시군구 필터) 동작이 흔들리면 안 된다."""
    rows = [
        make_row(상가업소번호="A1", 시군구코드="11680", 지번코드="1168010100108230004"),
        make_row(상가업소번호="B1", 시군구코드="11440", 지번코드="1144012300103580001"),
    ]
    write_csv(tmp_path, "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv", rows)

    result = target.scan_and_build(str(tmp_path), "11680", "202603")

    assert result["total_matched"] == 1
    assert result["parcel_count"] == 1
    assert len(result["parcel_records"]) == 1     # 콜백 없으면 예전처럼 다 모아준다


# ── 6.6 범위 지정(시도·복수 지역) — parse_scope / rest_scope_filter ──────────
#
# 1단계 서비스 범위가 "서울+대전"이라 기존의 '시군구 1개 아니면 전국' 두 갈래로는
# 표현이 안 됐다. 시군구코드 앞 2자리가 시도이므로 접두사 일치 하나로 통일한다.


@pytest.mark.parametrize("raw,expected", [
    ("11680", ("11680",)),            # 강남구 하나 (기존 동작)
    ("11,30", ("11", "30")),          # 서울 + 대전
    ("11", ("11",)),                  # 서울 전체
    (" 11 , 30 ", ("11", "30")),      # 공백 허용
    ("30,11", ("11", "30")),          # 순서 무관(정렬)
    ("all", ()),                      # 전국 = 필터 없음
    ("ALL", ()),
])
def test_parse_scope(raw, expected):
    assert target.parse_scope(raw) == expected


def test_parse_scope_drops_prefix_covered_entries():
    """'11'이 이미 서울 전체라 '11680'을 따로 두면 같은 행을 두 번 세게 된다."""
    assert target.parse_scope("11,11680") == ("11",)


@pytest.mark.parametrize("raw", ["", "  ", ",", "1", "116801", "11a", "서울"])
def test_parse_scope_rejects_bad_values(raw):
    with pytest.raises(ValueError):
        target.parse_scope(raw)


@pytest.mark.parametrize("prefixes,expected", [
    ((), "전국"),
    (("11",), "서울"),
    (("11", "30"), "서울+대전"),
    (("11680",), "11680"),            # 시군구 5자리는 이름표가 없으니 코드 그대로
])
def test_scope_label(prefixes, expected):
    assert target.scope_label(prefixes) == expected


def test_rest_scope_filter_uses_eq_only_when_length_matches():
    """★ pnu(19자리)에 5자리 eq를 쓰면 아무 행도 안 맞는다 — 그 실수를 막는 가드."""
    # sigungu_code 는 값 전체가 5자리라 eq 가 맞다(인덱스를 그대로 탄다)
    assert target.rest_scope_filter("sigungu_code", ("11680",), exact_len=5) == \
        "sigungu_code=eq.11680"
    # pnu 는 19자리다 — exact_len 을 안 주므로 like 여야 한다
    assert target.rest_scope_filter("pnu", ("11680",)) == "pnu=like.11680*"
    # 시도(2자리)는 5자리가 아니므로 eq 가 되면 안 된다
    assert target.rest_scope_filter("sigungu_code", ("11",), exact_len=5) == \
        "sigungu_code=like.11*"


def test_rest_scope_filter_multi_uses_or():
    assert target.rest_scope_filter("pnu", ("11", "30")) == \
        "or=(pnu.like.11*,pnu.like.30*)"
    assert target.rest_scope_filter("sigungu_code", ("11", "30"), exact_len=5) == \
        "or=(sigungu_code.like.11*,sigungu_code.like.30*)"


def test_rest_scope_filter_empty_scope_has_no_filter():
    assert target.rest_scope_filter("pnu", ()) == ""


def test_scan_and_build_two_sido_scope_takes_both(tmp_path):
    """서울(11)+대전(30)만 걸리고 경기(41)는 빠진다."""
    rows = [
        make_row(상가업소번호="A1", 시군구코드="11680", 지번코드="1168010100108230004"),
        make_row(상가업소번호="A2", 시군구코드="11440", 지번코드="1144012300103580001"),
        make_row(상가업소번호="D1", 시군구코드="30170", 지번코드="3017010100108230004"),
        make_row(상가업소번호="G1", 시군구코드="41135", 지번코드="4113512300103580001"),
    ]
    write_csv(tmp_path, "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv", rows)

    result = target.scan_and_build(str(tmp_path), "11,30", "202603")

    assert result["total_matched"] == 3          # 서울 2 + 대전 1, 경기 제외
    assert result["parcel_count"] == 3
    assert result["ub_with_pnu_count"] == 3


def test_scan_and_build_sido_scope_takes_whole_sido(tmp_path):
    """'11'은 서울 안의 모든 구를 잡는다(강남만이 아니라)."""
    rows = [
        make_row(상가업소번호="A1", 시군구코드="11680", 지번코드="1168010100108230004"),
        make_row(상가업소번호="A2", 시군구코드="11110", 지번코드="1111010100108230004"),
        make_row(상가업소번호="G1", 시군구코드="41135", 지번코드="4113512300103580001"),
    ]
    write_csv(tmp_path, "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv", rows)

    result = target.scan_and_build(str(tmp_path), "11", "202603")

    assert result["total_matched"] == 2


def test_parse_args_labels_multi_sido_scope():
    """보고서 라벨이 기본값 '강남구'로 남으면 거짓말이 된다."""
    opts = target.parse_args(["--sigungu-code", "11,30"])
    assert opts["gu_name"] == "서울+대전"
    # --gu-name 을 직접 주면 그걸 존중한다
    opts2 = target.parse_args(["--sigungu-code", "11,30", "--gu-name", "1단계"])
    assert opts2["gu_name"] == "1단계"
    # 기본값(강남구)은 그대로
    assert target.parse_args([])["gu_name"] == target.DEFAULT_GU_NAME


def test_scan_and_build_streams_per_file_and_dedupes_pnu_across_files(tmp_path):
    """★ 파일 1개마다 콜백이 한 번씩 오고, 파일 사이에 겹치는 PNU는 parcel 1회만.

    (parcel은 PNU가 기본키라 두 번 보내도 DB는 멀쩡하지만, would-upsert 수가
    부풀어 마지막 REST 교차검증이 거짓 불일치를 낸다.)
    """
    same_pnu = "1168010100108230004"
    write_csv(tmp_path, "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv",
              [make_row(상가업소번호="A1", 지번코드=same_pnu),
               make_row(상가업소번호="A2", 지번코드="1168010100108230009")])
    write_csv(tmp_path, "소상공인시장진흥공단_상가(상권)정보_경기_202603.csv",
              [make_row(상가업소번호="B1", 지번코드=same_pnu),
               make_row(상가업소번호="B2", 지번코드="1168010100108230011")])

    calls = []

    def sink(parcel_records, ub_records):
        calls.append((len(parcel_records), len(ub_records)))

    result = target.scan_and_build(str(tmp_path), "11680", "202603", on_file_done=sink)

    assert len(calls) == 2                      # 파일(시도) 1개당 한 번
    # 먼저 읽힌 파일이 2개(겹친 PNU 포함), 나중 파일은 겹친 것을 빼고 1개
    assert [c[0] for c in calls] == [2, 1]
    assert [c[1] for c in calls] == [2, 2]      # unit_business 는 행마다 그대로
    assert result["parcel_count"] == 3          # 고유 PNU 3개 — 겹친 것은 한 번만
    assert result["unit_business_count"] == 4
    # 콜백에 넘긴 뒤 버퍼는 비운다 — 전국 적재 때 메모리가 터지지 않는 이유
    assert result["parcel_records"] == []
    assert result["unit_business_records"] == []


def test_scan_and_build_ub_with_pnu_count_excludes_invalid(tmp_path):
    write_csv(tmp_path, "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv",
              [make_row(상가업소번호="A1", 지번코드="1168010100108230004"),
               make_row(상가업소번호="A2", 지번코드="")])
    result = target.scan_and_build(str(tmp_path), "11680", "202603")
    assert result["unit_business_count"] == 2
    assert result["ub_with_pnu_count"] == 1


def test_parse_args_all_mode_labels_gu_name_as_전국():
    opts = target.parse_args(["--sigungu-code", "all"])
    assert opts["gu_name"] == target.ALL_GU_NAME
    # --gu-name 을 직접 준 경우엔 그 값을 존중한다
    opts2 = target.parse_args(["--sigungu-code", "all", "--gu-name", "우리동네"])
    assert opts2["gu_name"] == "우리동네"


def test_main_all_mode_cross_check_query_has_no_sigungu_filter(tmp_path, monkeypatch):
    write_csv(
        tmp_path, "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv",
        [make_row(상가업소번호="M1", 시군구코드="41135", 지번코드="4113512300103580001"),
         # PNU 무효 행 — 전국 모드 기준값이 unit_business_count(2)인지
         # ub_with_pnu_count(1)인지를 실제로 가른다(라이브 격차 2,039건 대응)
         make_row(상가업소번호="M2", 시군구코드="41135", 지번코드="")],
    )
    monkeypatch.setattr(sys, "argv", ["prog", "--dir", str(tmp_path), "--sigungu-code", "all"])
    monkeypatch.setattr(target, "get_supabase_config", lambda: ("https://x.supabase.co", "key"))
    monkeypatch.setattr(
        target, "upsert_batch",
        lambda base_url, headers, table, rows, batch_size=target.BATCH_SIZE: len(rows),
    )

    queries = {}

    def fake_rest_count(base_url, headers, table, query):
        queries[table] = query
        return {"parcel": 1, "unit_business": 2}[table]   # parcel 고유 PNU 1 / ub 전체 2

    monkeypatch.setattr(target, "rest_count", fake_rest_count)

    assert target.main() == 0
    # 전국 모드 기준값 = unit_business_count(무효 PNU 포함 2). ub_with_pnu_count(1)로
    # 바꾸면 REST count 2와 어긋나 main() 이 1을 돌려주므로 위 assert 가 깨진다.
    assert queries["parcel"] == "select=pnu"          # 시군구로 좁히지 않는다
    assert "pnu=like" not in queries["unit_business"]
    assert "snapshot_ym=eq.202603" in queries["unit_business"]


def test_main_streams_upserts_per_file(tmp_path, monkeypatch):
    """파일 2개면 parcel/unit_business 적재도 파일마다 나뉘어 나간다."""
    write_csv(tmp_path, "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv",
              [make_row(상가업소번호="A1", 지번코드="1168010100108230004")])
    write_csv(tmp_path, "소상공인시장진흥공단_상가(상권)정보_경기_202603.csv",
              [make_row(상가업소번호="B1", 지번코드="1168010100108230009")])
    monkeypatch.setattr(sys, "argv", ["prog", "--dir", str(tmp_path), "--sigungu-code", "11680"])
    monkeypatch.setattr(target, "get_supabase_config", lambda: ("https://x.supabase.co", "key"))

    calls = []

    def fake_upsert(base_url, headers, table, rows, batch_size=target.BATCH_SIZE):
        calls.append((table, len(rows)))
        return len(rows)

    monkeypatch.setattr(target, "upsert_batch", fake_upsert)
    monkeypatch.setattr(target, "rest_count", lambda base_url, headers, table, query: 2)

    assert target.main() == 0
    assert calls == [("parcel", 1), ("unit_business", 1),
                     ("parcel", 1), ("unit_business", 1)]


def test_main_dry_run_never_upserts(tmp_path, monkeypatch):
    write_csv(tmp_path, "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv",
              [make_row(상가업소번호="A1", 지번코드="1168010100108230004")])
    monkeypatch.setattr(
        sys, "argv", ["prog", "--dir", str(tmp_path), "--sigungu-code", "all", "--dry-run"])

    def boom_config():
        raise AssertionError("dry-run 은 Supabase 연결조차 하지 않아야 한다")

    monkeypatch.setattr(target, "get_supabase_config", boom_config)
    monkeypatch.setattr(
        target, "upsert_batch",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("dry-run 이 DB에 썼다")),
    )
    assert target.main() == 0


# ── 7. estimate_bldrgst_scale ────────────────────────────────────────────────


def test_estimate_bldrgst_scale_fits_in_one_day():
    scale = target.estimate_bldrgst_scale(1000)
    assert scale["total_calls"] == 3000
    assert scale["fits_in_one_day"] is True
    assert scale["days_needed"] == 1


def test_estimate_bldrgst_scale_exceeds_daily_limit():
    scale = target.estimate_bldrgst_scale(12274)  # 강남구 2026Q1 실측 고유 PNU 규모
    assert scale["total_calls"] == 36822
    assert scale["fits_in_one_day"] is False
    assert scale["days_needed"] == 4  # ceil(36822 / 10000)


# ── 8. upsert_batch / rest_count (requests 흉내) ─────────────────────────────


class _FakeResponse:
    def __init__(self, status_code=201, text="ok", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


def test_upsert_batch_batches_and_headers(monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse(status_code=201)

    monkeypatch.setattr(target.requests, "post", fake_post)

    rows = [{"pnu": str(i)} for i in range(1500)]
    sent = target.upsert_batch("https://x.supabase.co", {"apikey": "k"}, "parcel", rows)

    assert sent == 1500
    assert len(calls) == 2
    assert [len(c["json"]) for c in calls] == [1000, 500]
    assert calls[0]["url"] == "https://x.supabase.co/rest/v1/parcel"
    assert calls[0]["headers"]["Prefer"] == "resolution=merge-duplicates,return=minimal"


def test_upsert_batch_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(
        target.requests, "post",
        lambda url, json=None, headers=None, timeout=None: _FakeResponse(400, "bad"),
    )
    with pytest.raises(RuntimeError, match="upsert 실패"):
        target.upsert_batch("https://x.supabase.co", {"apikey": "k"}, "parcel", [{"pnu": "1"}])


# ── 8.1 재시도 (결함 1 — docs/decisions/0005 §[A] 결정 2) ────────────────────
# ⚠️ 아래 테스트들은 고치기 전 코드(재시도 없이 즉시 예외)로 되돌리면 전부
# 빨간불이 된다: 실패 응답이 1번만 오고(calls == 1) 재시도가 없으므로 성공
# 케이스는 애초에 성공하지 못하고, "재시도 N회 소진" 문구도 없다.


def test_upsert_batch_5xx는_재시도_후_성공한다(monkeypatch):
    responses = [_FakeResponse(503, "unavailable"), _FakeResponse(201, "ok")]
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(target.requests, "post", fake_post)
    sleeps = []
    sent = target.upsert_batch(
        "https://x.supabase.co", {"apikey": "k"}, "parcel", [{"pnu": "1"}],
        sleep=sleeps.append,
    )
    assert sent == 1
    assert len(calls) == 2                # 1회 실패 + 1회 성공
    assert sleeps == [2]                  # 지수 백오프 밑값 2초(1회차 대기)


def test_upsert_batch_네트워크_오류는_재시도_후_성공한다(monkeypatch):
    state = {"n": 0}

    def fake_post(url, json=None, headers=None, timeout=None):
        state["n"] += 1
        if state["n"] == 1:
            raise target.requests.exceptions.ConnectionError("boom")
        return _FakeResponse(201, "ok")

    monkeypatch.setattr(target.requests, "post", fake_post)
    sent = target.upsert_batch(
        "https://x.supabase.co", {"apikey": "k"}, "parcel", [{"pnu": "1"}],
        sleep=lambda s: None,
    )
    assert sent == 1
    assert state["n"] == 2


def test_upsert_batch_5xx_재시도_소진하면_예외(monkeypatch):
    monkeypatch.setattr(
        target.requests, "post",
        lambda url, json=None, headers=None, timeout=None: _FakeResponse(500, "boom"),
    )
    sleeps = []
    with pytest.raises(RuntimeError, match="재시도 3회 소진"):
        target.upsert_batch(
            "https://x.supabase.co", {"apikey": "k"}, "parcel", [{"pnu": "1"}],
            sleep=sleeps.append,
        )
    assert sleeps == [2, 4]               # 지수 백오프: 2초, 4초 (총 3회 시도)


def test_upsert_batch_4xx는_재시도_없이_즉시_실패(monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(url)
        return _FakeResponse(400, "bad")

    monkeypatch.setattr(target.requests, "post", fake_post)
    with pytest.raises(RuntimeError, match="upsert 실패"):
        target.upsert_batch(
            "https://x.supabase.co", {"apikey": "k"}, "parcel", [{"pnu": "1"}],
            sleep=lambda s: None,
        )
    assert len(calls) == 1                # 재시도 없음 — 요청 자체가 잘못된 것


def test_upsert_batch_unit_business_uses_ignore_duplicates(monkeypatch):
    # unit_business는 append-only 불변식(schema.sql "절대 UPDATE/DELETE 하지
    # 않는다") — 재실행 시 기존 분기 스냅샷 행을 덮어쓰면 안 되므로
    # resolution=ignore-duplicates(ON CONFLICT DO NOTHING)를 써야 한다.
    # parcel의 merge-duplicates와 혼용 금지.
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(headers)
        return _FakeResponse(status_code=201)

    monkeypatch.setattr(target.requests, "post", fake_post)
    target.upsert_batch("https://x.supabase.co", {"apikey": "k"}, "unit_business", [{"biz_no": "1"}])

    assert calls[0]["Prefer"] == "resolution=ignore-duplicates,return=minimal"


def test_upsert_batch_parcel_still_uses_merge_duplicates(monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(headers)
        return _FakeResponse(status_code=201)

    monkeypatch.setattr(target.requests, "post", fake_post)
    target.upsert_batch("https://x.supabase.co", {"apikey": "k"}, "parcel", [{"pnu": "1"}])

    assert calls[0]["Prefer"] == "resolution=merge-duplicates,return=minimal"


def test_upsert_batch_unknown_table_raises():
    with pytest.raises(ValueError, match="TABLE_UPSERT_RESOLUTION"):
        target.upsert_batch("https://x.supabase.co", {"apikey": "k"}, "이상한_테이블", [{"x": 1}])


def test_rest_count_parses_content_range(monkeypatch):
    def fake_head(url, headers=None, timeout=None):
        return _FakeResponse(206, headers={"Content-Range": "0-999/12345"})

    monkeypatch.setattr(target.requests, "head", fake_head)
    n = target.rest_count("https://x.supabase.co", {"apikey": "k"}, "parcel", "select=pnu")
    assert n == 12345


def test_rest_count_raises_on_bad_status(monkeypatch):
    monkeypatch.setattr(
        target.requests, "head",
        lambda url, headers=None, timeout=None: _FakeResponse(404, "not found"),
    )
    with pytest.raises(RuntimeError, match="count 조회 실패"):
        target.rest_count("https://x.supabase.co", {"apikey": "k"}, "parcel", "select=pnu")


# ── 8.5 parse_args ───────────────────────────────────────────────────────────


def test_parse_args_defaults_and_overrides():
    opts = target.parse_args([])
    assert opts["dir"] == target.DEFAULT_DATA_DIR
    assert opts["sigungu_code"] == target.DEFAULT_SIGUNGU_CODE
    assert opts["dry_run"] is False

    opts2 = target.parse_args(["--dir", "X", "--snapshot-ym", "202606", "--dry-run"])
    assert opts2["dir"] == "X"
    assert opts2["snapshot_ym"] == "202606"
    assert opts2["dry_run"] is True


def test_parse_args_missing_value():
    with pytest.raises(ValueError, match="뒤에 값이 필요"):
        target.parse_args(["--dir"])


def test_parse_args_rejects_unknown_flag_like_help():
    """--help 를 조용히 무시하면 dry_run=False 인 실제 실행이 되어버린다(2026-08-08 실사고)."""
    with pytest.raises(ValueError, match="알 수 없는 인자"):
        target.parse_args(["--help"])


def test_parse_args_rejects_typo_does_not_silently_set_dry_run():
    """--dryrun(오타)이 --dry-run으로 조용히 넘어가면 실제 실행이 되어버린다."""
    with pytest.raises(ValueError, match="알 수 없는 인자"):
        target.parse_args(["--dryrun"])


# ── 9. main() 통합 동작 (RuntimeError 래핑·--snapshot-ym 검증·REST 교차검증) ──


def test_main_invalid_snapshot_ym_returns_2(tmp_path, monkeypatch):
    write_csv(tmp_path, "아무거나.csv", [make_row()])
    monkeypatch.setattr(
        sys, "argv",
        ["prog", "--dir", str(tmp_path), "--snapshot-ym", "2026-03", "--dry-run"],
    )
    assert target.main() == 2


def test_main_wraps_scan_and_build_runtime_error_returns_1(tmp_path, monkeypatch):
    write_csv(tmp_path, "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv", [make_row()])
    monkeypatch.setattr(sys, "argv", ["prog", "--dir", str(tmp_path)])
    # 연결 정보 확인이 스캔보다 앞으로 옮겨졌다(긴 스캔 뒤에 .env 없어 실패하는 낭비 방지)
    # — 이 테스트가 실제 .env 를 읽지 않도록 흉내낸다.
    monkeypatch.setattr(target, "get_supabase_config", lambda: ("https://x.supabase.co", "key"))
    # parcel baseline 측정도 연결 확인 직후·스캔 전으로 옮겨졌다 — 실제 네트워크를
    # 타지 않도록 흉내낸다(F1: 누적 parcel 테이블 baseline).
    monkeypatch.setattr(target, "rest_count", lambda base_url, headers, table, query: 0)

    def boom(data_dir, sigungu_code, snapshot_ym, on_file_done=None):
        raise RuntimeError("스캔 실패 테스트")

    monkeypatch.setattr(target, "scan_and_build", boom)
    assert target.main() == 1


def test_main_unit_business_cross_check_uses_sigungu_filter_and_returns_1_on_mismatch(
    tmp_path, monkeypatch,
):
    write_csv(
        tmp_path, "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv",
        [make_row(상가업소번호="M1", 시군구코드="11680", 지번코드="1168010100108230004")],
    )
    monkeypatch.setattr(sys, "argv", ["prog", "--dir", str(tmp_path), "--sigungu-code", "11680"])
    monkeypatch.setattr(target, "get_supabase_config", lambda: ("https://x.supabase.co", "key"))
    monkeypatch.setattr(
        target, "upsert_batch",
        lambda base_url, headers, table, rows, batch_size=target.BATCH_SIZE: len(rows),
    )

    queries = {}

    def fake_rest_count(base_url, headers, table, query):
        queries[table] = query
        if table == "parcel":
            return 1  # would-upsert와 일치
        return 999  # unit_business는 의도적으로 불일치시켜 MEDIUM-1 회귀 확인

    monkeypatch.setattr(target, "rest_count", fake_rest_count)

    assert target.main() == 1
    assert "pnu=like.11680" in queries["unit_business"]
    assert "snapshot_ym=eq.202603" in queries["unit_business"]


def test_main_parcel_cross_check_survives_prior_quarter_rows_in_cumulative_table(
    tmp_path, monkeypatch,
):
    """★ F1 회귀 가드 — parcel은 분기 축 없는 누적 테이블(schema.sql: snapshot_ym
    컬럼 없음)이라, 이전 분기·이전 시군구가 남긴 행 때문에 적재 후 총행수가
    이번 스캔 고유 PNU 수보다 커지는 게 정상이다. 예전 코드
    (parcel_count == result['parcel_count'] 단순 등호)는 이 상황에서 적재가
    성공했는데도 거짓 불일치로 return 1을 냈다. 새 코드는 baseline(적재 전
    카운트)을 미리 재서 증가분만 비교하므로 return 0이어야 한다.
    """
    write_csv(
        tmp_path, "소상공인시장진흥공단_상가(상권)정보_서울_202603.csv",
        [make_row(상가업소번호="M1", 시군구코드="11680", 지번코드="1168010100108230004")],
    )
    monkeypatch.setattr(sys, "argv", ["prog", "--dir", str(tmp_path), "--sigungu-code", "11680"])
    monkeypatch.setattr(target, "get_supabase_config", lambda: ("https://x.supabase.co", "key"))
    monkeypatch.setattr(
        target, "upsert_batch",
        lambda base_url, headers, table, rows, batch_size=target.BATCH_SIZE: len(rows),
    )

    # parcel 테이블에는 이전 분기(예: 201512 백필)가 남긴 행 5개가 이미 있다고
    # 가정한다 — baseline(적재 전) 5, 적재 후 6(이번 스캔 신규 PNU 1개 추가).
    # 옛 등호 비교라면 6 != result['parcel_count'](1)이라 불일치로 판정됐을 상황.
    parcel_calls = []

    def fake_rest_count(base_url, headers, table, query):
        if table == "parcel":
            parcel_calls.append(query)
            return 5 if len(parcel_calls) == 1 else 6
        return 1  # unit_business는 유효 PNU 1건과 일치

    monkeypatch.setattr(target, "rest_count", fake_rest_count)

    assert target.main() == 0
    assert len(parcel_calls) == 2  # baseline 1회 + 적재 후 최종 교차검증 1회
