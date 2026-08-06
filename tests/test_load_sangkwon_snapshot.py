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

    def boom(data_dir, sigungu_code, snapshot_ym):
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
