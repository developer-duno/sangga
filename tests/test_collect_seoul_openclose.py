# -*- coding: utf-8 -*-
"""scripts/collectors/collect_seoul_openclose.py 단위 테스트 (결정 0033 · 수집기 1:1).

라이브 API·Supabase 없이 본다(HTTP 는 가짜 세션):
  1. 분기 꼴(YYYYQ)·최신부터 거슬러 가기
  2. 응답 봉투 — 정상 / INFO-200(자료 없음 — `row` 도 총건수도 없다, 2026-10-05 실측) / 이상한 꼴
  3. 인증키가 로그로 새지 않는다(키가 주소 **경로**에 든다)
  4. fetch_page — INFO-100 은 멈춤, ERROR-500 은 재시도, 모르는 코드는 오류
  5. ⛔ collect_quarter — 0건 분기는 done 금지 · 중간에 끊기면 파일 0 · 수 어긋나면 파일 0 ·
     같은 날 다른 내용이면 덮어쓰지 않음
  6. 연결부 — 진짜 collect_quarter 에 HTTP 받기만 가짜로 두고 **부른 주소·페이지**를 단언
  7. `--end-quarter` 없으면 거부 · `--dry-run` 은 DB 에 안 쓴다
"""

import json
import os
import sys

import pytest
import requests

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COLLECTORS_DIR = os.path.join(_ROOT, "scripts", "collectors")
if _COLLECTORS_DIR not in sys.path:
    sys.path.insert(0, _COLLECTORS_DIR)

import collect_seoul_openclose as C  # noqa: E402

KEY = "abcd1234SECRET"


def api_row(quarter="20262", trdar="3001491", induty="CS100001", similr=156.0):
    """2026-10-05 샘플키 실측 응답의 한 행 모양 그대로(영문 대문자 · 숫자는 실수)."""
    return {"STDR_YYQU_CD": quarter, "TRDAR_SE_CD": "U", "TRDAR_SE_CD_NM": "관광특구",
            "TRDAR_CD": trdar, "TRDAR_CD_NM": "이태원 관광특구",
            "SVC_INDUTY_CD": induty, "SVC_INDUTY_CD_NM": "한식음식점",
            "SIMILR_INDUTY_STOR_CO": similr, "STOR_CO": similr - 14.0, "FRC_STOR_CO": 14.0,
            "OPBIZ_RT": 4.0, "OPBIZ_STOR_CO": 6.0, "CLSBIZ_RT": 4.0, "CLSBIZ_STOR_CO": 6.0}


def ok_payload(total, rows):
    return {C.SERVICE: {"list_total_count": total,
                        "RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다"},
                        "row": rows}}


NO_DATA = {"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}
BAD_KEY = {"RESULT": {"CODE": "INFO-100", "MESSAGE": "인증키가 유효하지 않습니다."}}


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload


class FakeSession:
    """부른 주소를 적어 두고, 미리 정한 응답(또는 예외)을 차례로 돌려준다."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.urls = []

    def get(self, url, timeout=None):
        self.urls.append(url)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def no_sleep(_s):
    return None


def run_quarter(tmp_path, replies, quarter="20262", date="20261006", max_calls=None):
    s = FakeSession(replies)
    calls = [0]
    res = C.collect_quarter(s, KEY, quarter, str(tmp_path), date, "2026-10-06T10:00:00+09:00",
                            calls, max_calls=max_calls, sleep=no_sleep)
    return res, s, calls


# ── 1. 분기 꼴 ───────────────────────────────────────────────────────────────


def test_parse_quarter_accepts_only_five_digits():
    assert C.parse_quarter("20262") == (2026, 2)
    for bad in ("2026Q2", "202606", "20265", "20260", "", None, "2026"):
        with pytest.raises(ValueError):
            C.parse_quarter(bad)


def test_quarter_range_goes_back_from_the_newest_across_years():
    assert C.quarter_range("20262", 3) == ["20262", "20261", "20254"]
    assert C.quarter_range("20262", 22)[-1] == "20211"
    with pytest.raises(ValueError):
        C.quarter_range("20262", 0)


# ── 2. 봉투 ──────────────────────────────────────────────────────────────────


def test_read_envelope_normal_no_data_and_odd():
    code, msg, total, rows = C.read_envelope(ok_payload(75912, [api_row()]))
    assert (code, total, len(rows)) == ("INFO-000", 75912, 1)
    assert C.read_envelope(NO_DATA)[:3] == ("INFO-200", "해당하는 데이터가 없습니다.", 0)
    assert C.read_envelope([])[0] == ""
    assert C.read_envelope({"x": 1})[0] == ""


# ── 3. 비밀 ──────────────────────────────────────────────────────────────────


def test_mask_secret_hides_key_in_path():
    url = C.page_url(KEY, "20262", 1, 1000)
    assert KEY in url
    assert KEY not in C.mask_secret(url)
    assert KEY not in C.mask_secret("오류 " + url, KEY)
    assert C.SECRET_MASK in C.mask_secret(url)


# ── 4. fetch_page ────────────────────────────────────────────────────────────


def test_fetch_page_no_data_is_zero_not_error():
    s = FakeSession([FakeResp(NO_DATA)])
    assert C.fetch_page(s, KEY, "20263", 1, 1000, sleep=no_sleep) == ("INFO-200", 0, [])


def test_fetch_page_bad_key_stops():
    s = FakeSession([FakeResp(BAD_KEY)])
    with pytest.raises(C.ServiceKeyError) as e:
        C.fetch_page(s, KEY, "20262", 1, 1000, sleep=no_sleep)
    assert KEY not in str(e.value)


def test_fetch_page_retries_server_error_then_succeeds():
    s = FakeSession([FakeResp({"RESULT": {"CODE": "ERROR-500", "MESSAGE": "서버"}}),
                     requests.ConnectionError("끊김 " + KEY),
                     FakeResp(ok_payload(1, [api_row()]))])
    assert C.fetch_page(s, KEY, "20262", 1, 1000, sleep=no_sleep)[1] == 1
    assert len(s.urls) == 3


def test_fetch_page_unknown_code_is_error_without_key():
    s = FakeSession([FakeResp({"RESULT": {"CODE": "ERROR-336", "MESSAGE": "1000건 " + KEY}})])
    with pytest.raises(C.ApiError) as e:
        C.fetch_page(s, KEY, "20262", 1, 5000, sleep=no_sleep)
    assert "ERROR-336" in str(e.value) and KEY not in str(e.value)


# ── 5. collect_quarter ───────────────────────────────────────────────────────


def test_full_quarter_is_written_and_done(tmp_path):
    rows = [api_row(induty="CS1{:05d}".format(i)) for i in range(3)]
    res, _, calls = run_quarter(tmp_path, [FakeResp(ok_payload(3, rows))])
    assert res["status"] == "done" and res["row_count"] == 3
    path = tmp_path / "20262_20261006.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["row"] for x in lines] == rows
    assert all(json.loads(x)["quarter"] == "20262" for x in lines)
    assert calls == [1]


@pytest.mark.parametrize("reply", [NO_DATA, ok_payload(0, [])], ids=["INFO-200", "total0"])
def test_zero_row_quarter_is_never_done(tmp_path, reply):
    """⛔ 아직 게시 안 된 분기를 done 으로 굳히면 판이 떠도 이어받기가 안 본다."""
    res, _, _ = run_quarter(tmp_path, [FakeResp(reply)], quarter="20263")
    assert res["status"] == "pending"
    assert res["row_count"] == 0
    assert "done 으로 굳히지 않는다" in res["error_msg"]
    assert list(tmp_path.iterdir()) == []


def test_break_in_the_middle_leaves_no_file(tmp_path):
    page1 = [api_row(induty="A{:04d}".format(i)) for i in range(1000)]
    replies = [FakeResp(ok_payload(1500, page1))] + [requests.ConnectionError("x")] * C.RETRY_COUNT
    res, _, _ = run_quarter(tmp_path, replies)
    assert res["status"] == "pending"
    assert "2페이지에서 끊김" in res["error_msg"]
    assert list(tmp_path.iterdir()) == []


def test_count_mismatch_leaves_no_file(tmp_path):
    # 총 3이라 했는데 2행만 오고 다음 페이지는 빈손
    res, _, _ = run_quarter(tmp_path, [FakeResp(ok_payload(3, [api_row(), api_row(induty="X")])),
                                       FakeResp(ok_payload(3, []))])
    assert res["status"] == "pending"
    assert "반쪽 분기" in res["error_msg"]
    assert list(tmp_path.iterdir()) == []


def test_other_quarter_rows_are_refused(tmp_path):
    res, _, _ = run_quarter(tmp_path, [FakeResp(ok_payload(1, [api_row(quarter="20261")]))])
    assert res["status"] == "pending" and list(tmp_path.iterdir()) == []


def test_same_day_different_content_is_not_overwritten(tmp_path):
    path = tmp_path / "20262_20261006.jsonl"
    bad ='{"quarter": "20262", "fetched_at": "x", "row": {"a": 1}}\n'
    path.write_text(bad, encoding="utf-8")
    old = path.read_bytes()
    res, _, _ = run_quarter(tmp_path, [FakeResp(ok_payload(1, [api_row()]))])
    assert res["status"] == "pending" and "덮어쓰지 않음" in res["error_msg"]
    assert path.read_bytes() == old


def test_same_day_same_content_is_done_untouched(tmp_path):
    run_quarter(tmp_path, [FakeResp(ok_payload(1, [api_row()]))])
    path = tmp_path / "20262_20261006.jsonl"
    before = path.read_bytes()
    res, _, _ = run_quarter(tmp_path, [FakeResp(ok_payload(1, [api_row()]))])
    assert res["status"] == "done" and path.read_bytes() == before


def test_max_calls_stops_without_file(tmp_path):
    page1 = [api_row(induty="A{:04d}".format(i)) for i in range(1000)]
    res, s, calls = run_quarter(tmp_path, [FakeResp(ok_payload(1500, page1))], max_calls=1)
    assert res["status"] == "pending" and calls == [1] and len(s.urls) == 1
    assert list(tmp_path.iterdir()) == []


# ── 6. 연결부 — 부른 주소·페이지 ─────────────────────────────────────────────


def test_wiring_calls_the_documented_url_pages(tmp_path):
    page1 = [api_row(induty="A{:04d}".format(i)) for i in range(1000)]
    page2 = [api_row(induty="B{:04d}".format(i)) for i in range(500)]
    res, s, calls = run_quarter(tmp_path, [FakeResp(ok_payload(1500, page1)),
                                           FakeResp(ok_payload(1500, page2))])
    assert res == {"status": "done", "row_count": 1500, "error_msg": None}
    assert s.urls == [
        "http://openapi.seoul.go.kr:8088/{}/json/VwsmTrdarStorQq/1/1000/20262".format(KEY),
        "http://openapi.seoul.go.kr:8088/{}/json/VwsmTrdarStorQq/1001/2000/20262".format(KEY),
    ]
    assert calls == [2]
    assert len((tmp_path / "20262_20261006.jsonl").read_text(encoding="utf-8").splitlines()) == 1500


# ── 7. 인자·장부 ─────────────────────────────────────────────────────────────


def test_end_quarter_is_mandatory():
    with pytest.raises(SystemExit):
        C.parse_args(["--quarters", "2"])
    with pytest.raises(ValueError):
        C.parse_args(["--end-quarter", "2026Q2"])
    a = C.parse_args(["--end-quarter", "20262", "--quarters", "2"])
    assert a.quarter_list == ["20262", "20261"]


def test_abbreviated_flags_are_refused():
    """`--dry` 같은 줄임이 다른 인자로 풀리지 않게(allow_abbrev=False)."""
    with pytest.raises(SystemExit):
        C.parse_args(["--end-quarter", "20262", "--dry"])


def test_pending_quarters_keeps_newest_first_and_skips_done():
    prog = {"20262": ("done", 0), "20261": ("pending", 2)}
    assert C.pending_quarters(["20262", "20261", "20254"], prog) == ["20261", "20254"]


def test_dry_run_writes_nothing_to_db(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "get_api_key", lambda: KEY)
    monkeypatch.setattr(C, "get_supabase_config", lambda: ("https://x", "k"))
    monkeypatch.setattr(C, "fetch_page", lambda *a, **k: ("INFO-000", 75912, []))
    monkeypatch.setattr(C, "read_progress", lambda *a, **k: {})

    def boom(*a, **k):
        raise AssertionError("dry-run 이 DB 에 쓰려 했습니다")

    monkeypatch.setattr(C, "upsert_batch", boom)
    monkeypatch.setattr(C, "seed_progress", boom)
    monkeypatch.setattr(C, "save_progress", boom)
    rc = C.main(["--dry-run", "--end-quarter", "20262", "--quarters", "22",
                 "--raw-dir", str(tmp_path)])
    assert rc == 0
    assert list(tmp_path.iterdir()) == []
