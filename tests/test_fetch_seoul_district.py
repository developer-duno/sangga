# -*- coding: utf-8 -*-
"""
scripts/collectors/fetch_seoul_district.py 단위 테스트

네트워크 없이 순수 로직만 검증한다:
  1. parse_download_params — 포털 HTML 구조가 바뀌면 **조용히 넘어가지 않는다**
  2. describe_zip         — 오류 페이지를 "받았다"고 착각하지 않는다
  3. summarize_prj        — 좌표계를 사람이 눈으로 확인할 수 있게
  4. readable_member      — zip 안 한글 파일명(cp949)이 깨져 보이지 않게
  5. main() 덮어쓰기 금지 — ★ raw 는 절대 덮어쓰지 않는다 (절대 규칙 6)

conftest.py를 새로 만들지 않기 위해 sys.path 조작은 이 파일 안에서만 한다.
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

import fetch_seoul_district as F  # noqa: E402


# ── 1. 다운로드 인자 추출 ─────────────────────────────────────────────────────

_PAGE = '''
<form name="frmFile" id="frmFile">
  <input type="hidden" name="infId" value="OA-15560"/>
  <input type="hidden" name="seqNo" />
  <input type="hidden" name="seq" />
  <input type="hidden" name="infSeq" value="3"/>
</form>
<a href="#" onclick="downloadFile('5')">받기</a>
'''


def test_parse_params_reads_real_page_shape():
    assert F.parse_download_params(_PAGE) == {
        "infId": "OA-15560", "infSeq": "3", "seq": "5"}


def test_parse_params_picks_largest_seq():
    """파일이 여러 개면 가장 큰 seq = 가장 최근 등록분으로 본다."""
    page = _PAGE + "<a onclick=\"downloadFile('12')\">x</a><a onclick=\"downloadFile('7')\">y</a>"
    assert F.parse_download_params(page)["seq"] == "12"   # 문자열 정렬이면 '7'이 됐을 것


@pytest.mark.parametrize("broken", [
    "",                                        # 통째로 빈 페이지
    '<input name="infId" value="OA-15560"/>',  # seq 호출이 없다
    "<a onclick=\"downloadFile('5')\">x</a>",  # 숨은 폼이 없다
])
def test_parse_params_refuses_when_page_changed(broken):
    """못 찾으면 기본값으로 넘어가지 않는다 — 엉뚱한 파일을 받는 게 더 나쁘다."""
    with pytest.raises(ValueError):
        F.parse_download_params(broken)


# ── 2. 받은 바이트 검사 ───────────────────────────────────────────────────────


def _zip_bytes(names=("a.shp", "a.dbf", "a.prj"), pad=600 * 1024, prj="PROJCS[\"x\"]"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in names:
            z.writestr(n, prj if n.endswith(".prj") else b"\0" * pad)
    return buf.getvalue()


def test_describe_zip_reads_prj_and_members():
    info = F.describe_zip(_zip_bytes(prj='PROJCS["Korea"],PARAMETER["False_Northing",500000.0]'))
    assert info["bytes"] > F.MIN_VALID_BYTES
    assert "False_Northing" in info["prj"]
    assert len(info["members"]) == 3


def test_describe_zip_rejects_tiny_response():
    """로그인·오류 페이지는 작다. 그걸 '받았다'고 넘기면 빈 적재가 된다."""
    with pytest.raises(ValueError):
        F.describe_zip(b"<html>error</html>")


def test_describe_zip_rejects_non_zip():
    with pytest.raises(ValueError):
        F.describe_zip(b"<html>" + b"x" * (600 * 1024))


def test_describe_zip_rejects_missing_shapefile_parts():
    """.prj 가 없으면 좌표계를 확인할 방법이 없다 — 그대로 적재하면 안 된다."""
    with pytest.raises(ValueError):
        F.describe_zip(_zip_bytes(names=("a.shp", "a.dbf")))


# ── 3~4. 사람이 읽는 출력 ─────────────────────────────────────────────────────


def test_summarize_prj_shows_false_northing():
    """5181(500000) vs 5186(600000) 을 눈으로 가를 수 있어야 한다."""
    s = F.summarize_prj('PROJCS["Korea_2000_Korea_Central_Belt"],'
                        'PARAMETER["False_Northing",500000.0]')
    assert "Korea_2000_Korea_Central_Belt" in s
    assert "500000" in s


def test_readable_member_restores_korean_name():
    """zip 이 파일명을 cp949 로 저장했는데 UTF-8 플래그가 없어 cp437 로 풀린다.
    되돌리지 않으면 목록이 깨져 보여 다운로드가 실패한 줄 오해한다."""
    mangled = "서울시".encode("cp949").decode("cp437")
    assert F.readable_member(mangled) == "서울시"


def test_readable_member_passes_through_plain_ascii():
    assert F.readable_member("plain.shp") == "plain.shp"


# ── 5. ★ raw 덮어쓰기 금지 (절대 규칙 6) ─────────────────────────────────────


def _run_main(monkeypatch, tmp_path, content):
    monkeypatch.setattr(
        F, "fetch",
        lambda session=None: (content, {"infId": "OA-15560", "infSeq": "3", "seq": "5"}))
    return F.main(["--out-dir", str(tmp_path), "--ym", "202608"])


def test_first_download_saves(monkeypatch, tmp_path):
    assert _run_main(monkeypatch, tmp_path, _zip_bytes()) == 0
    assert (tmp_path / "202608" / "seoul_district_area.zip").exists()


def test_same_content_again_is_a_noop(monkeypatch, tmp_path):
    """같은 판을 다시 받는 건 흔하다 — 이건 조용히 넘어가도 된다."""
    same = _zip_bytes()
    assert _run_main(monkeypatch, tmp_path, same) == 0
    assert _run_main(monkeypatch, tmp_path, same) == 0


def test_different_content_refuses_to_overwrite(monkeypatch, tmp_path, capsys):
    """★ 갱신이 '비정기'라 같은 달에 두 판이 올 수 있다. 덮어쓰면 먼저 받은 원본이
    **복구 불가로 사라진다**(절대 규칙 6). 멈추고 사람에게 알려야 한다."""
    dest = tmp_path / "202608" / "seoul_district_area.zip"
    first = _zip_bytes(pad=600 * 1024)
    assert _run_main(monkeypatch, tmp_path, first) == 0

    second = _zip_bytes(pad=700 * 1024)          # 내용이 다른 새 판
    assert _run_main(monkeypatch, tmp_path, second) == 1      # 실패로 끝나야 한다
    assert dest.read_bytes() == first                          # 원본이 그대로 살아 있다
    assert "덮어쓰지 않습니다" in capsys.readouterr().err


def test_probe_never_writes(monkeypatch, tmp_path):
    """--probe 는 확인만 한다 — 저장 0."""
    monkeypatch.setattr(
        F, "fetch",
        lambda session=None: (_zip_bytes(), {"infId": "x", "infSeq": "1", "seq": "1"}))
    assert F.main(["--probe", "--out-dir", str(tmp_path), "--ym", "202608"]) == 0
    assert not (tmp_path / "202608").exists()
