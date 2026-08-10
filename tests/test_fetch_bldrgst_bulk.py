# -*- coding: utf-8 -*-
"""
scripts/collectors/fetch_bldrgst_bulk.py 단위 테스트

네트워크 없이 순수 로직만 검증한다:
  1. open_list — CSRF 토큰을 meta 태그에서 뽑는다 (JS 전역이 아니다)
  2. parse_entries — 목록 HTML -> (opnTaskCd, 서비스명, 파일ID)
  3. pick — 원하는 종류의 최신 항목 고르기
  4. filename_from — Content-Disposition 파싱
  5. human — 바이트 -> 사람이 읽는 크기
  6. download — 크기 상한·HTML 응답 방어

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

import fetch_bldrgst_bulk as target  # noqa: E402


# ── 픽스처 ────────────────────────────────────────────────────────────────────

# 실제 페이지(2026-08-10 실측)의 형태를 줄인 것. 토큰은 meta 태그에 있고,
# 목록은 fnDownloadPop(구분, 종류, 파일ID) 로 박혀 있다.
LIST_HTML = """
<html><head>
<meta name="_csrf_parameter" content="_csrf" />
<meta name="_csrf_header" content="X-CSRF-TOKEN" />
<meta name="_csrf" content="cd3bd678-b2fe-4159-b937-4a56c49dbbb3" />
</head><body>
<ul>
<li><p class="tit">층별개요 (2026년 06월)</p>
    <button onclick="fnDownloadPop('03','0304','OPN_FLR_202606')">전체</button></li>
<li><p class="tit">표제부 (2026년 06월)</p>
    <button onclick="fnDownloadPop('03','0303','OPN_TITLE_202606')">전체</button></li>
<li><p class="tit">표제부 (2026년 05월)</p>
    <button onclick="fnDownloadPop('03','0303','OPN_TITLE_202605')">전체</button></li>
</ul></body></html>
"""


class FakeResponse:
    def __init__(self, text="", headers=None, status_code=200):
        self.text = text
        self.headers = headers or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP {}".format(self.status_code))

    def close(self):
        pass

    def iter_content(self, _chunk):
        return iter(())


class FakeSession:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        return self._response

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return self._response


# ── 1. open_list ──────────────────────────────────────────────────────────────


def test_open_list_reads_csrf_from_meta_tags():
    """★ 토큰은 meta 태그에 있다. JS 전역(csrfToken=...)만 찾으면 못 잡는다."""
    s = FakeSession(FakeResponse(text=LIST_HTML))
    html, name, token = target.open_list(s)

    assert name == "_csrf"
    assert token == "cd3bd678-b2fe-4159-b937-4a56c49dbbb3"
    assert html == LIST_HTML


def test_open_list_raises_when_token_missing():
    s = FakeSession(FakeResponse(text="<html><body>없음</body></html>"))
    with pytest.raises(target.BulkError):
        target.open_list(s)


# ── 2. parse_entries ──────────────────────────────────────────────────────────


def test_parse_entries_pairs_titles_with_file_ids():
    entries = target.parse_entries(LIST_HTML)

    assert len(entries) == 3
    assert entries[0]["opnTaskCd"] == "0304"
    assert entries[0]["srvcNm"] == "층별개요 (2026년 06월)"
    assert entries[0]["srvrFileNm"] == "OPN_FLR_202606"
    assert entries[1]["srvrFileNm"] == "OPN_TITLE_202606"


def test_parse_entries_empty_html():
    assert target.parse_entries("<html></html>") == []


# ── 3. pick ───────────────────────────────────────────────────────────────────


def test_pick_takes_first_match_which_is_newest():
    """목록은 최신이 위다 — 같은 종류가 여러 달 있으면 맨 위(최신)를 쓴다."""
    entries = target.parse_entries(LIST_HTML)
    got = target.pick(entries, "0303")
    assert got["srvrFileNm"] == "OPN_TITLE_202606"


def test_pick_raises_when_absent():
    with pytest.raises(target.BulkError):
        target.pick(target.parse_entries(LIST_HTML), "0306")


# ── 4. filename_from ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("disp,expected", [
    ('attachment; filename="표제부.zip"', "표제부.zip"),
    ("attachment; filename=표제부.zip", "표제부.zip"),
    ("attachment; filename*=UTF-8''%ED%91%9C%EC%A0%9C%EB%B6%80.zip", "표제부.zip"),
])
def test_filename_from_parses_disposition(disp, expected):
    r = FakeResponse(headers={"content-disposition": disp})
    assert target.filename_from(r, "fallback") == expected


def test_filename_from_falls_back_when_header_absent():
    assert target.filename_from(FakeResponse(), "OPN123") == "OPN123"


# ── 5. human ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("n,expected", [
    (None, "알 수 없음"),
    (0, "0.00 B"),
    (1536, "1.50 KB"),
    (678117376, "646.70 MB"),
])
def test_human(n, expected):
    assert target.human(n) == expected


# ── 6. download 방어 ──────────────────────────────────────────────────────────


def test_download_refuses_when_over_max_gb(tmp_path):
    """상한을 넘으면 본문을 받기 전에 멈춘다 — 디스크를 지키는 가드."""
    resp = FakeResponse(headers={"content-length": str(20 * 1024 ** 3),
                                 "content-type": "application/zip"})
    s = FakeSession(resp)
    with pytest.raises(target.BulkError) as e:
        target.download(s, {"srvrFileNm": "X"}, "_csrf", "tok",
                        str(tmp_path), max_gb=12)
    assert "상한" in str(e.value)
    assert os.listdir(str(tmp_path)) == []  # 아무것도 안 만들었다


def test_download_refuses_html_response(tmp_path):
    """로그인 페이지가 오면 zip 인 척 저장하지 않는다."""
    resp = FakeResponse(headers={"content-type": "text/html; charset=UTF-8"})
    s = FakeSession(resp)
    with pytest.raises(target.BulkError) as e:
        target.download(s, {"srvrFileNm": "X"}, "_csrf", "tok", str(tmp_path))
    assert "HTML" in str(e.value)


def test_download_probe_stops_before_writing(tmp_path):
    resp = FakeResponse(headers={"content-length": "1024",
                                 "content-type": "application/zip"})
    s = FakeSession(resp)
    assert target.download(s, {"srvrFileNm": "X"}, "_csrf", "tok",
                           str(tmp_path), probe=True) is None
    assert os.listdir(str(tmp_path)) == []


def test_download_raises_on_http_error(tmp_path):
    resp = FakeResponse(text="서버 오류", status_code=500)
    s = FakeSession(resp)
    with pytest.raises(target.BulkError):
        target.download(s, {"srvrFileNm": "X"}, "_csrf", "tok", str(tmp_path))


# ── 7. 상수 ───────────────────────────────────────────────────────────────────


def test_kinds_cover_the_three_we_use():
    """표제부·층별개요·전유공용면적 3종이 우리가 API로 받던 것과 짝이다."""
    assert set(target.KINDS) == {"title", "flr_ouln", "expos_area"}
    assert target.KINDS["title"][0] == "0303"
    assert target.KINDS["flr_ouln"][0] == "0304"
    assert target.KINDS["expos_area"][0] == "0306"
