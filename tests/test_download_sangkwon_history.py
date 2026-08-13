# -*- coding: utf-8 -*-
"""
scripts/download_sangkwon_history.py 1:1 단위 테스트.

네트워크 호출은 전부 monkeypatch로 대체한다(실제 포털에 접속하지 않음).
공용 설정 파일(conftest.py 등) 없이 이 파일 안에서 import 경로를 직접 해결한다.
"""

import io
import os
import sys
import zipfile

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import download_sangkwon_history as dsh  # noqa: E402


# ── 테스트용 zip 생성 도우미 ──────────────────────────────────────────────────


def _make_zip_bytes(entries=None):
    """유효한 zip 파일의 바이트열을 만든다."""
    if entries is None:
        entries = {"sample.csv": "층정보,호정보\n1,101\n"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, content in entries.items():
            zf.writestr(fname, content)
    return buf.getvalue()


class _FakeResponse:
    """urllib.request.urlopen()이 돌려주는 응답 객체를 흉내낸다."""

    def __init__(self, data: bytes, content_length=None):
        self._data = data
        self._pos = 0
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def read(self, n=-1):
        if n is None or n < 0:
            chunk = self._data[self._pos:]
            self._pos = len(self._data)
            return chunk
        chunk = self._data[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


# ── sanitize_filename ─────────────────────────────────────────────────────────


def test_sanitize_filename_unescapes_html_entities():
    assert dsh.sanitize_filename("상가&#40;상권&#41;정보_20250630") == "상가(상권)정보_20250630"


def test_sanitize_filename_strips_path_components():
    # 경로 구분자가 섞여 들어와도 basename만 남긴다.
    assert dsh.sanitize_filename("../../etc/passwd_20250630") == "passwd_20250630"
    assert dsh.sanitize_filename("..\\..\\windows\\evil_20250630") == "evil_20250630"


def test_sanitize_filename_removes_forbidden_windows_chars():
    result = dsh.sanitize_filename('bad<>:"|?*name_20250630')
    for ch in '<>:"|?*':
        assert ch not in result


def test_sanitize_filename_strips_trailing_dot_and_space():
    assert dsh.sanitize_filename("trailing_dot_20250630. ") == "trailing_dot_20250630"


def test_sanitize_filename_empty_result_falls_back_to_unnamed():
    assert dsh.sanitize_filename("///") == "unnamed"


# ── resolve_dest_path (SAVE_DIR 이탈 방지) ────────────────────────────────────


def test_resolve_dest_path_normal_case(tmp_path):
    save_dir = str(tmp_path / "sangkwon_zips")
    os.makedirs(save_dir, exist_ok=True)
    dest = dsh.resolve_dest_path(save_dir, "상가정보_20250630")
    assert dest == os.path.abspath(os.path.join(save_dir, "상가정보_20250630.zip"))


def test_resolve_dest_path_rejects_escape(tmp_path):
    save_dir = str(tmp_path / "sangkwon_zips")
    os.makedirs(save_dir, exist_ok=True)
    # sanitize_filename을 거치지 않은 악의적인 이름을 직접 넣어 이중 방어를 검증.
    with pytest.raises(ValueError):
        dsh.resolve_dest_path(save_dir, "..\\..\\evil")


# ── zip 완결성 검증 (_zip_is_valid / already_downloaded) ─────────────────────


def test_zip_is_valid_true_for_good_zip(tmp_path):
    path = tmp_path / "good.zip"
    path.write_bytes(_make_zip_bytes())
    assert dsh._zip_is_valid(str(path)) is True


def test_zip_is_valid_false_for_truncated_zip(tmp_path):
    good = _make_zip_bytes()
    path = tmp_path / "truncated.zip"
    # 잘린 zip: 뒤쪽 central directory가 잘려나가 열리지 않아야 한다.
    path.write_bytes(good[: len(good) // 2])
    assert dsh._zip_is_valid(str(path)) is False


def test_zip_is_valid_false_for_missing_file():
    assert dsh._zip_is_valid("이런파일없음.zip") is False


def test_already_downloaded_false_when_file_missing(tmp_path):
    assert dsh.already_downloaded(str(tmp_path / "nope.zip")) is False


def test_already_downloaded_false_when_too_small(tmp_path):
    path = tmp_path / "tiny.zip"
    path.write_bytes(_make_zip_bytes())  # 정상 zip이지만 1MB 미만
    assert os.path.getsize(path) < dsh.MIN_VALID_BYTES
    assert dsh.already_downloaded(str(path)) is False


def test_already_downloaded_false_when_zip_corrupted_despite_size(tmp_path, monkeypatch):
    # MIN_VALID_BYTES 관문은 통과하지만 zip 내용 자체는 깨진 경우.
    monkeypatch.setattr(dsh, "MIN_VALID_BYTES", 10)
    path = tmp_path / "corrupt.zip"
    path.write_bytes(dsh.ZIP_MAGIC + b"\x00" * 50)  # PK 매직은 있지만 유효한 zip 구조 아님
    assert dsh.already_downloaded(str(path)) is False


def test_already_downloaded_true_for_valid_zip(tmp_path, monkeypatch):
    monkeypatch.setattr(dsh, "MIN_VALID_BYTES", 10)
    path = tmp_path / "valid.zip"
    path.write_bytes(_make_zip_bytes())
    assert dsh.already_downloaded(str(path)) is True


# ── 목록 조회 재시도 (2026-08-10 CI 실패 재발 방지) ──────────────────────────

# 주간 감시가 `Errno 110 Connection timed out` 으로 죽었는데 이틀 전 같은 러너는 8초
# 만에 성공했다 = 간헐적 실패다. 재시도가 하나도 없던 곳은 목록 조회뿐이었다.


class _Flaky:
    """지정한 횟수만큼 실패한 뒤 성공하는 가짜 _post. 넘어온 timeout 도 기록한다."""

    def __init__(self, fail_times, payload=b"ok"):
        self.fail_times = fail_times
        self.payload = payload
        self.calls = 0
        self.timeouts = []

    def __call__(self, url, form, timeout=None):
        self.calls += 1
        self.timeouts.append(timeout)
        if self.calls <= self.fail_times:
            raise OSError("[Errno 110] Connection timed out")
        return self.payload


def test_post_with_retry_succeeds_first_try_without_sleeping(monkeypatch):
    fake = _Flaky(fail_times=0)
    monkeypatch.setattr(dsh, "_post", fake)
    waits = []
    assert dsh._post_with_retry("u", {}, sleep=waits.append) == b"ok"
    assert fake.calls == 1
    assert waits == []  # 멀쩡할 때 괜히 기다리지 않는다


def test_post_with_retry_recovers_after_transient_failure(monkeypatch):
    """한 번 실패했다고 포기하면 주 1회 감시가 일주일을 통째로 건너뛴다."""
    fake = _Flaky(fail_times=1)
    monkeypatch.setattr(dsh, "_post", fake)
    waits = []
    assert dsh._post_with_retry("u", {}, sleep=waits.append) == b"ok"
    assert fake.calls == 2
    assert waits == [dsh.LIST_RETRY_BACKOFF_SEC]


def test_post_with_retry_backoff_doubles(monkeypatch):
    fake = _Flaky(fail_times=2)
    monkeypatch.setattr(dsh, "_post", fake)
    waits = []
    dsh._post_with_retry("u", {}, attempts=3, sleep=waits.append)
    assert waits == [dsh.LIST_RETRY_BACKOFF_SEC, dsh.LIST_RETRY_BACKOFF_SEC * 2]


def test_post_with_retry_raises_after_all_attempts(monkeypatch):
    """무한 재시도로 CI 를 붙잡아 두지 않는다 — 결국 실패해야 실패 알림이 열린다."""
    fake = _Flaky(fail_times=99)
    monkeypatch.setattr(dsh, "_post", fake)
    waits = []
    with pytest.raises(OSError):
        dsh._post_with_retry("u", {}, attempts=3, sleep=waits.append)
    assert fake.calls == 3
    assert waits == [dsh.LIST_RETRY_BACKOFF_SEC, dsh.LIST_RETRY_BACKOFF_SEC * 2]


def test_history_list_uses_short_timeout_not_download_timeout(monkeypatch):
    """목록에 300초를 쓰면 리눅스가 130초에 먼저 연결을 포기해(Errno 110) 파이썬
    타임아웃이 영영 안 울린다 — 그게 2026-08-10 실패의 실제 모양이었다."""
    fake = _Flaky(fail_times=0, payload=b"")
    monkeypatch.setattr(dsh, "_post", fake)
    dsh.fetch_history_list()
    assert fake.timeouts == [dsh.LIST_TIMEOUT_SEC]
    assert dsh.LIST_TIMEOUT_SEC < dsh.TIMEOUT_SEC


# ── fetch_history_list (탈락 항목 로그용 분리 검증) ───────────────────────────

_SAMPLE_HTML = """
<a href="#" onclick="openFileDetailPopup('a')" data-public-pk="uddi:q1">상가(상권)정보_20250630</a>
<a href="#" onclick="openFileDetailPopup('b')" data-public-pk="uddi:q2">상가(상권)정보_20250331</a>
<a href="#" onclick="openFileDetailPopup('c')" data-public-pk="uddi:q2">상가(상권)정보_20250331</a>
<a href="#" onclick="openFileDetailPopup('d')" data-public-pk="uddi:x1">포천시 업소수 현황</a>
<a href="#" onclick="openFileDetailPopup('e')" data-public-pk="uddi:x2">단발성_통계자료</a>
"""


def test_fetch_history_list_separates_quarterly_and_excluded(monkeypatch):
    # 목록 조회는 _post_with_retry 를 거치므로 가짜도 timeout 인자를 받아야 한다.
    monkeypatch.setattr(
        dsh, "_post", lambda url, form, timeout=None: _SAMPLE_HTML.encode("utf-8")
    )
    items, excluded = dsh.fetch_history_list()

    # uddi:q2가 두 번 나오지만 분기 항목은 dedup되어 1개만 남는다.
    assert [it["name"] for it in items] == [
        "상가(상권)정보_20250630",
        "상가(상권)정보_20250331",
    ]
    assert excluded == ["포천시 업소수 현황", "단발성_통계자료"]


def test_fetch_history_list_all_quarterly_no_excluded(monkeypatch):
    html = '<a href="#" onclick="openFileDetailPopup(1)" data-public-pk="uddi:only">상가정보_20240101</a>'
    monkeypatch.setattr(dsh, "_post", lambda url, form, timeout=None: html.encode("utf-8"))
    items, excluded = dsh.fetch_history_list()
    assert len(items) == 1
    assert excluded == []


# ── fetch_file_id ──────────────────────────────────────────────────────────────


def test_fetch_file_id_success(monkeypatch):
    body = b'{"status": true, "atchFileId": "FILE123", "fileDetailSn": "2"}'
    monkeypatch.setattr(dsh, "_post", lambda url, form: body)
    atch_file_id, sn = dsh.fetch_file_id("uddi:abc")
    assert atch_file_id == "FILE123"
    assert sn == "2"


def test_fetch_file_id_status_false_raises(monkeypatch):
    body = b'{"status": false}'
    monkeypatch.setattr(dsh, "_post", lambda url, form: body)
    with pytest.raises(RuntimeError):
        dsh.fetch_file_id("uddi:abc")


def test_fetch_file_id_missing_atch_file_id_raises(monkeypatch):
    body = b'{"status": true}'
    monkeypatch.setattr(dsh, "_post", lambda url, form: body)
    with pytest.raises(RuntimeError):
        dsh.fetch_file_id("uddi:abc")


# ── download_zip (완결성 검증: Content-Length 대조 + testzip) ────────────────


def test_download_zip_success_writes_and_validates(tmp_path, monkeypatch):
    zip_bytes = _make_zip_bytes()
    monkeypatch.setattr(
        dsh.urllib.request,
        "urlopen",
        lambda req, timeout=None: _FakeResponse(zip_bytes, content_length=len(zip_bytes)),
    )
    dest = str(tmp_path / "out.zip")
    written = dsh.download_zip("FILE1", "1", "이름_20250630", dest)

    assert written == len(zip_bytes)
    assert os.path.exists(dest)
    assert not os.path.exists(dest + ".part")
    assert dsh._zip_is_valid(dest) is True


def test_download_zip_content_length_mismatch_raises(tmp_path, monkeypatch):
    zip_bytes = _make_zip_bytes()
    monkeypatch.setattr(
        dsh.urllib.request,
        "urlopen",
        # 실제보다 훨씬 큰 값을 예고해 불일치를 유도
        lambda req, timeout=None: _FakeResponse(zip_bytes, content_length=len(zip_bytes) + 999),
    )
    dest = str(tmp_path / "out.zip")
    with pytest.raises(RuntimeError, match="다운로드 불완전"):
        dsh.download_zip("FILE1", "1", "이름_20250630", dest)
    # 확정 전 상태 — 최종 파일로 rename되면 안 된다.
    assert not os.path.exists(dest)


def test_download_zip_corrupted_zip_content_raises(tmp_path, monkeypatch):
    # PK 매직으로 시작하지만 뒤가 깨진(=zip으로 안 열리는) 바이트열.
    broken = dsh.ZIP_MAGIC + b"\x00" * 100
    monkeypatch.setattr(
        dsh.urllib.request,
        "urlopen",
        lambda req, timeout=None: _FakeResponse(broken, content_length=len(broken)),
    )
    dest = str(tmp_path / "out.zip")
    with pytest.raises(RuntimeError, match="손상"):
        dsh.download_zip("FILE1", "1", "이름_20250630", dest)
    assert not os.path.exists(dest)


def test_download_zip_non_zip_response_raises(tmp_path, monkeypatch):
    html_body = "<html>다운로드 제한 안내</html>".encode("utf-8")
    monkeypatch.setattr(
        dsh.urllib.request,
        "urlopen",
        lambda req, timeout=None: _FakeResponse(html_body),
    )
    dest = str(tmp_path / "out.zip")
    with pytest.raises(RuntimeError, match="zip 아님"):
        dsh.download_zip("FILE1", "1", "이름_20250630", dest)


# ── _download_one (파일당 재시도 + 지수 백오프) ───────────────────────────────


def test_download_one_retries_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(dsh.time, "sleep", lambda s: None)
    monkeypatch.setattr(dsh, "fetch_file_id", lambda uddi: ("FILE1", "1"))

    calls = {"n": 0}

    def flaky_download_zip(atch_file_id, file_detail_sn, name, dest_path):
        calls["n"] += 1
        if calls["n"] < dsh.RETRY_COUNT:
            raise RuntimeError("일시적 실패")
        with open(dest_path, "wb") as f:
            f.write(b"ok")
        return 2

    monkeypatch.setattr(dsh, "download_zip", flaky_download_zip)

    dest = str(tmp_path / "out.zip")
    written = dsh._download_one({"name": "n", "uddi": "u"}, dest)

    assert written == 2
    assert calls["n"] == dsh.RETRY_COUNT


def test_download_one_exhausts_retries_and_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(dsh.time, "sleep", lambda s: None)
    monkeypatch.setattr(dsh, "fetch_file_id", lambda uddi: ("FILE1", "1"))

    calls = {"n": 0}

    def always_fails(atch_file_id, file_detail_sn, name, dest_path):
        calls["n"] += 1
        raise RuntimeError("영구 실패")

    monkeypatch.setattr(dsh, "download_zip", always_fails)

    dest = str(tmp_path / "out.zip")
    with pytest.raises(RuntimeError, match="영구 실패"):
        dsh._download_one({"name": "n", "uddi": "u"}, dest)

    assert calls["n"] == dsh.RETRY_COUNT


def test_download_one_cleans_up_part_file_between_retries(tmp_path, monkeypatch):
    monkeypatch.setattr(dsh.time, "sleep", lambda s: None)
    monkeypatch.setattr(dsh, "fetch_file_id", lambda uddi: ("FILE1", "1"))
    dest = str(tmp_path / "out.zip")
    part = dest + ".part"

    def fails_leaving_part(atch_file_id, file_detail_sn, name, dest_path):
        with open(dest_path + ".part", "wb") as f:
            f.write(b"junk")
        raise RuntimeError("실패")

    monkeypatch.setattr(dsh, "download_zip", fails_leaving_part)

    with pytest.raises(RuntimeError):
        dsh._download_one({"name": "n", "uddi": "u"}, dest)

    assert not os.path.exists(part)


# ── main() 인자 검증 (네트워크 무관 구간만) ───────────────────────────────────


def test_main_limit_without_value_returns_exit_code_2(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["download_sangkwon_history.py", "--limit"])
    assert dsh.main() == 2
