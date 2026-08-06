# -*- coding: utf-8 -*-
"""
scripts/collectors/load_bjd_code.py 단위 테스트

네트워크·DB 없이 순수 로직만 검증한다:
  1. 법정동명 공백 분리 파싱 (_split_bjd_nm)
  2. zip(EUC-KR txt) 파싱 (parse_bjd_rows) — 픽스처 zip을 메모리에서 즉석 생성
  3. 원본 zip 유효성 판정 (already_downloaded)
  4. Supabase upsert 페이로드 구성 (upsert_rows) — requests.post를 흉내내 배치 크기·헤더만 검증
  5. 테이블 존재 여부 판정 (table_exists) — requests.get을 흉내내 404/200 분기 검증

conftest.py를 새로 만들지 않기 위해(병렬 작업 중인 다른 수집기와 충돌 방지),
sys.path 조작은 이 파일 안에서만 한다.
"""

import io
import os
import sys
import zipfile

import pytest

_COLLECTORS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "collectors",
)
if _COLLECTORS_DIR not in sys.path:
    sys.path.insert(0, _COLLECTORS_DIR)

import load_bjd_code as target  # noqa: E402


# ── 픽스처 도우미 ─────────────────────────────────────────────────────────────


def make_bjd_zip(rows_text: str, filename: str = "법정동코드 전체자료.txt") -> bytes:
    """실제 code.go.kr 응답과 같은 구조(zip 안에 EUC-KR 탭구분 txt 1개)의 픽스처를 만든다."""
    header = "법정동코드\t법정동명\t폐지여부\n"
    content = (header + rows_text).encode("euc-kr")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(filename, content)
    return buf.getvalue()


SAMPLE_ROWS_TEXT = (
    "1100000000\t서울특별시\t존재\n"
    "1111000000\t서울특별시 종로구\t존재\n"
    "1111010100\t서울특별시 종로구 청운동\t존재\n"
    # 5280042021(진리)의 상위 코드 행 3개 — 코드 계층 파생에 필요(실제 파일에도
    # 폐지 이력까지 전량 포함되어 상위 행이 항상 함께 존재한다).
    "5200000000\t전북특별자치도\t존재\n"
    "5280000000\t전북특별자치도 부안군\t존재\n"
    "5280042000\t전북특별자치도 부안군 위도면\t존재\n"
    "5280042021\t전북특별자치도 부안군 위도면 진리\t존재\n"
    "1111010200\t서울특별시 종로구 신교동\t폐지\n"
)


# ── 1. _split_bjd_nm (코드 계층 기반 파생 — 2026-08-07 HIGH 수정) ────────────
#
# 예전(공백 토큰 순서) 방식은 두 가지 실측 오매핑을 냈다:
#   ① 시 아래 구 — '경기도 용인시 처인구 포곡읍 삼계리'는 토큰이 5개라
#      시군구/읍면동/리가 한 칸씩 밀림 (읍면동 자리에 '처인구', 리 자리에
#      '포곡읍 삼계리'가 통째로 들어감)
#   ② 세종특별자치시 — 시도 전용 코드 행이 없어 '조치원읍'이 시군구 자리로 감
# 새 _split_bjd_nm(bjd_code, code_to_name)은 코드 자릿수로 상위 행을 직접
# 조회하므로, 테스트도 그 상위 행들을 code_to_name map에 함께 넣어줘야 한다
# (실제 파일에도 상위 코드 행이 항상 함께 존재한다 — 폐지 이력까지 전량 다운로드).


def test_split_bjd_nm_sido_level():
    code_to_name = {"1100000000": "서울특별시"}
    result = target._split_bjd_nm("1100000000", code_to_name)
    assert result == {
        "sido_nm": "서울특별시",
        "sigungu_nm": None,
        "emd_nm": None,
        "ri_nm": None,
    }


def test_split_bjd_nm_sigungu_level():
    code_to_name = {
        "1100000000": "서울특별시",
        "1111000000": "서울특별시 종로구",
    }
    result = target._split_bjd_nm("1111000000", code_to_name)
    assert result["sido_nm"] == "서울특별시"
    assert result["sigungu_nm"] == "종로구"
    assert result["emd_nm"] is None
    assert result["ri_nm"] is None


def test_split_bjd_nm_emd_level():
    code_to_name = {
        "1100000000": "서울특별시",
        "1111000000": "서울특별시 종로구",
        "1111010100": "서울특별시 종로구 청운동",
    }
    result = target._split_bjd_nm("1111010100", code_to_name)
    assert result["sido_nm"] == "서울특별시"
    assert result["sigungu_nm"] == "종로구"
    assert result["emd_nm"] == "청운동"
    assert result["ri_nm"] is None


def test_split_bjd_nm_ri_level():
    code_to_name = {
        "5200000000": "전북특별자치도",
        "5280000000": "전북특별자치도 부안군",
        "5280042000": "전북특별자치도 부안군 위도면",
        "5280042021": "전북특별자치도 부안군 위도면 진리",
    }
    result = target._split_bjd_nm("5280042021", code_to_name)
    assert result["sido_nm"] == "전북특별자치도"
    assert result["sigungu_nm"] == "부안군"
    assert result["emd_nm"] == "위도면"
    assert result["ri_nm"] == "진리"


def test_split_bjd_nm_si_under_gu_case_regression():
    """실측 오매핑 ① — 시 아래 구('경기도 용인시 처인구'). 토큰 방식이 깨졌던 사례.

    처인구는 코드 체계상 그 자체로 시군구 레벨 행(sigungu_code='41461')이므로
    sigungu_nm은 '용인시 처인구'(구까지 포함)가 맞다 — DB의 sigungu_code
    컬럼(실거래가 API 조회 키)과 정확히 같은 단위를 가리켜야 하기 때문이다.
    포곡읍(읍면동)·삼계리(리)는 각자 제 칸으로 들어가야 한다.
    """
    code_to_name = {
        "4100000000": "경기도",
        "4146100000": "경기도 용인시 처인구",
        "4146125000": "경기도 용인시 처인구 포곡읍",
        "4146125021": "경기도 용인시 처인구 포곡읍 삼계리",
    }
    result = target._split_bjd_nm("4146125021", code_to_name)
    assert result["sido_nm"] == "경기도"
    assert result["sigungu_nm"] == "용인시 처인구"
    assert result["emd_nm"] == "포곡읍"
    assert result["ri_nm"] == "삼계리"


def test_split_bjd_nm_sejong_no_sido_only_row_regression():
    """실측 오매핑 ② — 세종특별자치시는 시도 전용 코드 행(3600000000)이 아예 없다.

    사도 정체성이 시군구 코드 레벨 행(3611000000='세종특별자치시')에 직접
    들어있다. 조치원읍은 읍면동이지 시군구가 아니다.
    """
    code_to_name = {
        "3611000000": "세종특별자치시",
        "3611025000": "세종특별자치시 조치원읍",
        "3611025021": "세종특별자치시 조치원읍 원리",
    }

    top = target._split_bjd_nm("3611000000", code_to_name)
    assert top["sido_nm"] == "세종특별자치시"
    assert top["sigungu_nm"] is None

    emd = target._split_bjd_nm("3611025000", code_to_name)
    assert emd["sido_nm"] == "세종특별자치시"
    assert emd["sigungu_nm"] is None
    assert emd["emd_nm"] == "조치원읍"

    ri = target._split_bjd_nm("3611025021", code_to_name)
    assert ri["sido_nm"] == "세종특별자치시"
    assert ri["sigungu_nm"] is None
    assert ri["emd_nm"] == "조치원읍"
    assert ri["ri_nm"] == "원리"


# ── 2. parse_bjd_rows ─────────────────────────────────────────────────────────


def test_parse_bjd_rows_counts_and_fields():
    zip_bytes = make_bjd_zip(SAMPLE_ROWS_TEXT)
    rows = target.parse_bjd_rows(zip_bytes)

    assert len(rows) == 8

    by_code = {r["bjd_code"]: r for r in rows}

    seoul = by_code["1100000000"]
    assert seoul["sigungu_code"] == "11000"
    assert seoul["bjd_nm"] == "서울특별시"
    assert seoul["is_active"] is True
    assert seoul["sido_nm"] == "서울특별시"
    assert seoul["sigungu_nm"] is None

    jongno_gu = by_code["1111000000"]
    assert jongno_gu["sigungu_code"] == "11110"
    assert jongno_gu["sigungu_nm"] == "종로구"

    ri_row = by_code["5280042021"]
    assert ri_row["sido_nm"] == "전북특별자치도"
    assert ri_row["sigungu_nm"] == "부안군"
    assert ri_row["emd_nm"] == "위도면"
    assert ri_row["ri_nm"] == "진리"
    assert ri_row["sigungu_code"] == "52800"

    disused = by_code["1111010200"]
    assert disused["is_active"] is False


def test_parse_bjd_rows_skips_blank_lines():
    text_with_blank = SAMPLE_ROWS_TEXT + "\n\n"
    zip_bytes = make_bjd_zip(text_with_blank)
    rows = target.parse_bjd_rows(zip_bytes)
    assert len(rows) == 8  # 빈 줄은 무시되어야 함


def test_parse_bjd_rows_rejects_unexpected_header():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "bad.txt",
            "코드\t이름\n1100000000\t서울특별시\n".encode("euc-kr"),
        )
    with pytest.raises(RuntimeError, match="헤더 형식"):
        target.parse_bjd_rows(buf.getvalue())


def test_parse_bjd_rows_rejects_empty_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w"):
        pass
    with pytest.raises(RuntimeError, match="zip 안에 파일이 없습니다"):
        target.parse_bjd_rows(buf.getvalue())


# ── 3. already_downloaded ─────────────────────────────────────────────────────


def test_already_downloaded_false_when_missing(tmp_path):
    path = os.path.join(str(tmp_path), "no_such.zip")
    assert target.already_downloaded(path) is False


def test_already_downloaded_false_when_too_small(tmp_path):
    path = os.path.join(str(tmp_path), "tiny.zip")
    with open(path, "wb") as f:
        f.write(target.ZIP_MAGIC + b"\x00" * 10)  # MIN_VALID_ZIP_BYTES 미만
    assert target.already_downloaded(path) is False


def test_already_downloaded_false_when_not_zip_magic(tmp_path):
    path = os.path.join(str(tmp_path), "fake.zip")
    with open(path, "wb") as f:
        f.write(b"<html>not a zip</html>" + b"\x00" * target.MIN_VALID_ZIP_BYTES)
    assert target.already_downloaded(path) is False


def test_already_downloaded_false_when_zip_corrupted_despite_size_and_magic(tmp_path):
    """MEDIUM 3 회귀 방지 — PK 매직 + 크기 관문은 통과하지만 zip 구조 자체가 깨진 경우.

    형제 스크립트(download_sangkwon_history.py)의 _zip_is_valid와 같은 기준으로
    testzip()까지 확인해야 이런 '크기만 그럴듯한' 잘린 zip을 잡아낼 수 있다.
    """
    path = os.path.join(str(tmp_path), "corrupt.zip")
    with open(path, "wb") as f:
        f.write(target.ZIP_MAGIC + b"\x00" * target.MIN_VALID_ZIP_BYTES)
    assert target.already_downloaded(path) is False


def test_already_downloaded_true_when_valid(tmp_path):
    path = os.path.join(str(tmp_path), "valid.zip")
    with open(path, "wb") as f:
        # MIN_VALID_ZIP_BYTES를 넘도록 압축 없이(ZIP_STORED) 채워 넣은 실제
        # 유효한 zip — 매직/크기뿐 아니라 testzip()까지 통과해야 True가 된다.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("data.txt", "x" * (target.MIN_VALID_ZIP_BYTES + 1000))
        f.write(buf.getvalue())
    assert os.path.getsize(path) >= target.MIN_VALID_ZIP_BYTES
    assert target.already_downloaded(path) is True


# ── 4. upsert_rows (requests.post 흉내) ───────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code=201, text="ok"):
        self.status_code = status_code
        self.text = text


def test_upsert_rows_batches_correctly(monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse(status_code=201)

    monkeypatch.setattr(target.requests, "post", fake_post)

    rows = [{"bjd_code": f"{i:010d}"} for i in range(2500)]  # BATCH_SIZE=1000 → 3배치
    sent = target.upsert_rows("https://example.supabase.co", {"apikey": "x"}, rows)

    assert sent == 2500
    assert len(calls) == 3
    assert [len(c["json"]) for c in calls] == [1000, 1000, 500]
    for c in calls:
        assert c["url"] == "https://example.supabase.co/rest/v1/bjd_code"
        assert c["headers"]["Prefer"] == "resolution=merge-duplicates,return=minimal"
        assert c["headers"]["Content-Type"] == "application/json"
        # 원래 headers(apikey)가 보존되는지 — 새 dict라 원본 훼손 없어야 함
        assert c["headers"]["apikey"] == "x"


def test_upsert_rows_adds_utc_updated_at_to_every_row(monkeypatch):
    """L4 회귀 방지 — PostgREST upsert는 JSON에 없는 컬럼을 갱신하지 않으므로

    updated_at을 매 행에 명시적으로 실어 보내야 재실행(merge-duplicates) 시에도
    값이 갱신된다. 배치 전체가 같은 시각(UTC, 'T'와 시간대 오프셋 포함)을 써야 한다.
    """
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(json)
        return _FakeResponse(status_code=201)

    monkeypatch.setattr(target.requests, "post", fake_post)

    rows = [{"bjd_code": "1100000000"}, {"bjd_code": "1111000000"}]
    target.upsert_rows("https://example.supabase.co", {"apikey": "x"}, rows)

    assert len(calls) == 1
    batch = calls[0]
    assert len(batch) == 2
    stamps = {row["updated_at"] for row in batch}
    assert len(stamps) == 1  # 같은 배치는 같은 시각
    stamp = stamps.pop()
    parsed = target.datetime.datetime.fromisoformat(stamp)
    assert parsed.utcoffset() == target.datetime.timedelta(0)  # UTC 명시
    # 원본 rows는 훼손되지 않아야 함(새 dict로 복사해서 보냈는지 확인)
    assert "updated_at" not in rows[0]
    assert "updated_at" not in rows[1]


def test_upsert_rows_raises_on_http_error(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        return _FakeResponse(status_code=400, text="bad request")

    monkeypatch.setattr(target.requests, "post", fake_post)

    rows = [{"bjd_code": "1100000000"}]
    with pytest.raises(RuntimeError, match="upsert 실패"):
        target.upsert_rows("https://example.supabase.co", {"apikey": "x"}, rows)


# ── 5. table_exists (requests.get 흉내) ───────────────────────────────────────


def test_table_exists_true_on_200(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(status_code=200)

    monkeypatch.setattr(target.requests, "get", fake_get)
    assert target.table_exists("https://example.supabase.co", {}) is True


def test_table_exists_false_on_404(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(status_code=404)

    monkeypatch.setattr(target.requests, "get", fake_get)
    assert target.table_exists("https://example.supabase.co", {}) is False
