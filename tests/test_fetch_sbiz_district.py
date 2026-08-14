# -*- coding: utf-8 -*-
"""
scripts/collectors/fetch_sbiz_district.py 단위 테스트

네트워크 없이 순수 로직만 검증한다:
  1. parse_uddi               — 포털 화면이 바뀌면 **조용히 넘어가지 않는다**
  2. parse_file_download_args — ★ JSON 메타를 파일로 착각하지 않는다 (이 수집기 최대 함정)
  3. filename_from_disposition— 한글 이름 되살리기 + 경로 끼워넣기 차단
  4. assert_csv_shape         — 오류 페이지를 "받았다"고 착각하지 않는다
  5. main() 덮어쓰기 금지     — ★ raw 는 절대 덮어쓰지 않는다 (절대 규칙 6)

conftest.py를 새로 만들지 않기 위해 sys.path 조작은 이 파일 안에서만 한다.
"""

import json
import os
import sys
from urllib.parse import quote

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COLLECTORS_DIR = os.path.join(_ROOT, "scripts", "collectors")
if _COLLECTORS_DIR not in sys.path:
    sys.path.insert(0, _COLLECTORS_DIR)

import fetch_sbiz_district as F  # noqa: E402


# ── 1. 파일 식별자 추출 ───────────────────────────────────────────────────────

_UDDI = "uddi:11a2b3c4-5d6e-4f70-8901-23456789abcd_202401011200"
_PAGE = '''
<div class="file-list">
  <a onclick="fn_fileDataDown('15090955','{u}')">CSV 다운로드</a>
  <input type="hidden" name="publicDataDetailPk" value="{u}"/>
</div>
'''.format(u=_UDDI)


def test_parse_uddi_reads_real_page_shape():
    assert F.parse_uddi(_PAGE) == _UDDI


def test_parse_uddi_dedupes_and_keeps_first():
    """같은 식별자가 여러 번 박혀 있는 것이 정상이다 — 그걸 '여러 파일'로 오해하면 안 된다."""
    other = "uddi:99999999-8888-4777-6666-555544443333"
    assert F.parse_uddi(_PAGE + '<a data-pk="{}"></a>'.format(other)) == _UDDI


@pytest.mark.parametrize("broken", [
    "",
    "<html><body>일시적인 오류가 발생했습니다</body></html>",
    "uddi:짧은거",                                     # 형태만 흉내 낸 값
])
def test_parse_uddi_refuses_when_page_changed(broken):
    """못 찾으면 기본값으로 넘어가지 않는다 — 엉뚱한 파일을 받는 게 더 나쁘다."""
    with pytest.raises(ValueError):
        F.parse_uddi(broken)


# ── 2. ★ 다운로드 인자 (파일이 아니라 JSON 이 오는 자리) ─────────────────────


def test_parse_file_args_reads_json_meta():
    meta = json.dumps({"atchFileId": "FILE_000000000123456", "fileDetailSn": "1",
                       "publicDataPk": "15090955"})
    assert F.parse_file_download_args(meta) == {
        "atchFileId": "FILE_000000000123456", "fileDetailSn": "1"}


def test_parse_file_args_accepts_numeric_detail_sn():
    """fileDetailSn 이 문자열이 아니라 숫자로 와도 같은 뜻이다."""
    meta = json.dumps({"atchFileId": "FILE_1", "fileDetailSn": 1})
    assert F.parse_file_download_args(meta)["fileDetailSn"] == "1"


def test_parse_file_args_refuses_a_file_body():
    """★ 이 응답을 파일로 착각하는 것이 이 수집기의 가장 큰 함정이다.
    CSV 앞부분이 그대로 오면 '메타가 아니다'라고 멈춰야 한다."""
    with pytest.raises(ValueError) as e:
        F.parse_file_download_args("상권번호,상권명,유형구분\n1,강남역,주요상권 \n")
    assert "JSON" in str(e.value)


def test_parse_file_args_refuses_missing_keys():
    with pytest.raises(ValueError) as e:
        F.parse_file_download_args(json.dumps({"atchFileId": "FILE_1"}))
    assert "fileDetailSn" in str(e.value)


# ── 3. 저장할 이름 ────────────────────────────────────────────────────────────


def test_filename_reads_plain_name():
    assert F.filename_from_disposition(
        'attachment; filename="sbiz.csv"') == "sbiz.csv"


def test_filename_restores_percent_encoded_korean():
    """한글 이름이 %EC%86%8C… 로 온다. 안 되돌리면 다음 세션이 파일을 못 알아본다."""
    name = "소상공인시장진흥공단_주요상권현황_20240101.csv"
    disp = "attachment; filename=\"{}\"".format(quote(name))
    assert F.filename_from_disposition(disp) == name


def test_filename_strips_path_parts():
    """이름에 경로가 섞여 오면 엉뚱한 자리에 쓴다."""
    assert F.filename_from_disposition(
        'attachment; filename="../../etc/passwd"') == "passwd"


def test_filename_falls_back_when_header_missing():
    assert F.filename_from_disposition("") == F.FALLBACK_NAME


# ── 4. 받은 바이트 검사 ───────────────────────────────────────────────────────

_HEADER = ",".join(F.REQUIRED_HEADER)


def _csv_bytes(header=_HEADER, pad=2 * 1024 * 1024):
    body = header + "\n" + ("1,강남역,주요상권 ,11,서울,11680,강남구,3,"
                            "127.0,37.5|127.1,37.5|127.1,37.4,20240101\n")
    return body.encode(F.ENCODING) + b"x" * pad


def test_assert_csv_shape_accepts_the_real_header():
    info = F.assert_csv_shape(_csv_bytes())
    assert info["bytes"] > F.MIN_VALID_BYTES
    assert "상권좌표" in info["columns"]


def test_assert_csv_shape_rejects_tiny_response():
    """오류 페이지·JSON 메타는 작다. 그걸 '받았다'고 넘기면 빈 적재가 된다."""
    with pytest.raises(ValueError):
        F.assert_csv_shape(b'{"atchFileId":"FILE_1"}')


def test_assert_csv_shape_rejects_changed_header():
    with pytest.raises(ValueError) as e:
        F.assert_csv_shape(_csv_bytes(header="상권번호,상권명"))
    assert "상권좌표" in str(e.value)


# ── 5. ★ raw 덮어쓰기 금지 (절대 규칙 6) ─────────────────────────────────────

_NAME = "소상공인시장진흥공단_주요상권현황_20240101.csv"


def _info(size):
    return {"uddi": _UDDI, "args": {"atchFileId": "FILE_1", "fileDetailSn": "1"},
            "content_type": "application/octet-stream", "size": size, "filename": _NAME}


def _run_main(monkeypatch, tmp_path, content):
    monkeypatch.setattr(
        F, "fetch",
        lambda session=None, probe=False, max_mb=F.DEFAULT_MAX_MB: (
            (None, _info(None)) if probe else (content, _info(len(content)))))
    return F.main(["--out-dir", str(tmp_path)])


def test_first_download_saves(monkeypatch, tmp_path):
    assert _run_main(monkeypatch, tmp_path, _csv_bytes()) == 0
    assert (tmp_path / _NAME).exists()


def test_same_content_again_is_a_noop(monkeypatch, tmp_path):
    """같은 판을 다시 받는 건 흔하다 — 이건 조용히 넘어가도 된다."""
    same = _csv_bytes()
    assert _run_main(monkeypatch, tmp_path, same) == 0
    assert _run_main(monkeypatch, tmp_path, same) == 0


def test_different_content_refuses_to_overwrite(monkeypatch, tmp_path, capsys):
    """★ 갱신 주기가 정해져 있지 않아 같은 이름으로 다른 판이 올 수 있다. 덮어쓰면
    먼저 받은 원본이 **복구 불가로 사라진다**(절대 규칙 6). 멈추고 사람에게 알려야 한다."""
    first = _csv_bytes(pad=2 * 1024 * 1024)
    assert _run_main(monkeypatch, tmp_path, first) == 0

    second = _csv_bytes(pad=3 * 1024 * 1024)          # 내용이 다른 새 판
    assert _run_main(monkeypatch, tmp_path, second) == 1
    assert (tmp_path / _NAME).read_bytes() == first    # 원본이 그대로 살아 있다
    assert "덮어쓰지 않습니다" in capsys.readouterr().err


def test_no_force_option_exists():
    """우회 옵션을 만들지 않는다 — 있으면 결국 쓰게 되고, 그날 원본이 사라진다."""
    with pytest.raises(SystemExit):
        F.main(["--force"])


def test_probe_never_writes(monkeypatch, tmp_path):
    """--probe 는 확인만 한다 — 저장 0."""
    monkeypatch.setattr(
        F, "fetch",
        lambda session=None, probe=False, max_mb=F.DEFAULT_MAX_MB: (None, _info(31_981_568)))
    assert F.main(["--probe", "--out-dir", str(tmp_path)]) == 0
    assert not (tmp_path / _NAME).exists()
