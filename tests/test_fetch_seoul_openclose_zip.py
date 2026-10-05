# -*- coding: utf-8 -*-
"""scripts/collectors/fetch_seoul_openclose_zip.py 단위 테스트 (결정 0033 · 수집기 1:1).

네트워크 없이 본다:
  1. ⛔ seq 는 **제목 ↔ seq 대응**으로 고른다 — "가장 큰 seq" 로 고르면 늘 최신 해만 받는다
  2. ⛔ infSeq 는 **frmFile 폼**의 값(3) — 앞의 frmApiDown(2)을 집지 않는다
  3. 구조가 바뀌면 조용히 넘어가지 않고 멈춘다
  4. zip 안 cp949 이름 되돌리기 · 오류 페이지를 '받았다'고 착각하지 않기
  5. ⛔ raw 덮어쓰기 금지 — 같은 내용이면 그대로, 다르면 멈춘다
  6. 연결부 — 진짜 fetch 에 HTTP 만 가짜로 두고 **보낸 폼 인자**를 단언
"""

import io
import os
import sys
import zipfile

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COLLECTORS_DIR = os.path.join(_ROOT, "scripts", "collectors")
if _COLLECTORS_DIR not in sys.path:
    sys.path.insert(0, _COLLECTORS_DIR)

import fetch_seoul_openclose_zip as F  # noqa: E402

# 2026-10-05 실제 페이지(OA-15577)의 꼴을 줄여 옮긴 것 — 폼 둘 · 해마다 파일 한 줄.
PAGE = '''
<form name="frmApiDown" id="frmApiDown"  action="#">
	<input type="hidden" name="infId" value="OA-15577" />
	<input type="hidden" name="infSeq" value="2" />
	<input type="hidden" name="srvType" value="A" />
</form>
<form name="frmFile" id="frmFile" >
	<input type="hidden" name="infId" value="OA-15577"/> <!-- 주석 -->
	<input type="hidden" name="seqNo" />
	<input type="hidden" name="seq" />
	<input type="hidden" name="infSeq" value="3"/>
</form>
<td><span title="서울시 상권분석서비스(점포-상권)_2025년.zip" onclick="javascript:downloadFile('20');">x</span></td>
<td><span title="서울시 상권분석서비스(점포-상권)_2024년.zip" onclick="javascript:downloadFile('19');">x</span></td>
<td><span title="서울시_상권분석서비스(점포-상권)_2021년.zip" onclick="javascript:downloadFile('16');">x</span></td>
'''


def test_seq_is_picked_by_title_not_by_max():
    p = F.parse_download_params(PAGE, 2021)
    assert p["seq"] == "16"            # "가장 큰 seq" 였다면 20
    assert p["title"].endswith("_2021년.zip")
    assert F.parse_download_params(PAGE, 2024)["seq"] == "19"


def test_inf_seq_comes_from_the_file_form():
    p = F.parse_download_params(PAGE, 2025)
    assert p["infSeq"] == "3"          # frmApiDown 의 2 를 집으면 엉뚱한 서비스
    assert p["infId"] == "OA-15577"


def test_missing_year_or_two_hits_stops():
    with pytest.raises(ValueError):
        F.parse_download_params(PAGE, 2023)
    # 같은 해 제목에 seq 가 둘(재발행 판이 나란히 걸린 꼴) — 어느 것인지 모르니 멈춘다.
    doubled = PAGE + ('<span title="서울시 상권분석서비스(점포-상권)_2025년.zip" '
                      'onclick="javascript:downloadFile(\'21\');">')
    with pytest.raises(ValueError):
        F.parse_download_params(doubled, 2025)


def test_missing_file_form_stops():
    with pytest.raises(ValueError):
        F.parse_download_params(PAGE.replace('name="frmFile"', 'name="frmOther"'), 2025)


def test_readable_member_restores_cp949_name():
    name = "서울시 상권분석서비스(점포-상권)_2024년.csv"
    garbled = name.encode("cp949").decode("cp437")
    assert garbled != name
    assert F.readable_member(garbled) == name
    assert F.readable_member(name) == name     # 이미 바른 이름은 그대로


def _zip_bytes(names=("a_2025년.csv",), size=600 * 1024):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for n in names:
            z.writestr(n, b"x" * size)
    return buf.getvalue()


def test_describe_zip_rejects_html_and_tiny_and_wrong_members():
    with pytest.raises(ValueError):
        F.describe_zip(b"<html>" + b" " * (600 * 1024))
    with pytest.raises(ValueError):
        F.describe_zip(_zip_bytes(size=10))
    with pytest.raises(ValueError):
        F.describe_zip(_zip_bytes(names=("a.csv", "b.csv")))
    assert F.describe_zip(_zip_bytes())["bytes"] > 500 * 1024


def test_save_never_overwrites(tmp_path):
    a = _zip_bytes()
    dest, how = F.save(a, str(tmp_path), 2025, "20261006")
    assert how == "new" and os.path.basename(dest) == "2025_20261006.zip"
    assert F.save(a, str(tmp_path), 2025, "20261006")[1] == "same"
    with pytest.raises(FileExistsError):
        F.save(_zip_bytes(size=700 * 1024), str(tmp_path), 2025, "20261006")
    with open(dest, "rb") as f:
        assert f.read() == a


class _Resp:
    def __init__(self, text="", content=b""):
        self.text, self.content = text, content

    def raise_for_status(self):
        return None


class _Session:
    def __init__(self, content):
        self.headers = {}
        self.content = content
        self.posts = []

    def get(self, url, timeout=None):
        assert url == F.DATASET_PAGE
        return _Resp(text=PAGE)

    def post(self, url, data=None, headers=None, timeout=None):
        self.posts.append((url, data))
        return _Resp(content=self.content)


def test_wiring_posts_the_chosen_year_form():
    s = _Session(_zip_bytes())
    content, params = F.fetch(2024, session=s)
    assert params["seq"] == "19"
    assert s.posts == [(F.DOWNLOAD_URL,
                        {"infId": "OA-15577", "infSeq": "3", "seq": "19", "seqNo": ""})]
    assert content == s.content
