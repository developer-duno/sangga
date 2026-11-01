# -*- coding: utf-8 -*-
"""scripts/collectors/collect_seoul_subway.py 단위 테스트 (결정 0045 PR⑥ · 수집기 1:1).

라이브 API·Supabase 없이 본다(HTTP 는 가짜 세션 · 장부는 가짜 함수):
  1. 주소 — 승하차는 끝에 달 · 마스터는 달 칸 없이 끝 빗금 · 키는 개업·폐업 수집기 것을 import
  2. 봉투 — 정상 · INFO-200(0건) · INFO-100(멈춤) · 이상한 모양
  3. 씨앗 범위 · pending 만 받기 · --retry-failed
  4. 한 달 받기 — done(파일) · 0건 pending · USE_MM 어긋남 pending · 총건수 어긋남 pending · 오류 failed · 2쪽 넘음 멈춤
  5. 마스터 파일 이름 · 같은 날 두 번이면 꼬리(덮어쓰기 0)
  6. 인자 — `--end-month` 의무(exit 2) · dry-run 쓰기 0 · 키 가림(양성 대조) · 호출 상한
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

import collect_seoul_subway as T  # noqa: E402

KEY = "abcd1234SECRET"
REAL_FETCH = T.fetch_page
FETCHED_AT = "2026-11-02T10:00:00+09:00"


def ride_row(ym="202609", line="2호선", sttn="강남"):
    """2026-11-02 표본(CardSubwayTime) 꼴 — 영문 대문자 · 숫자는 실수(일부 칸만)."""
    return {"USE_MM": ym, "SBWY_ROUT_LN_NM": line, "STTN": sttn, "HR_4_GET_ON_NOPE": 892.0,
            "HR_4_GET_OFF_NOPE": 10.0, "JOB_YMD": "20261003"}


def master_row(i=150):
    return {"BLDN_ID": "{:04d}".format(i), "BLDN_NM": "서울역", "ROUTE": "1호선", "LAT": "37.556228", "LOT": "126.972135"}


def ok_payload(service, total, rows):
    return {service: {"list_total_count": total, "RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다"},
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


def month(session, ym, raw, calls=None, max_calls=None):
    return T.collect_month(session, KEY, ym, str(raw), "20261102", FETCHED_AT, calls or [0], max_calls=max_calls,
                           between=no_sleep, sleep=no_sleep)


# ── 1. 주소 ──────────────────────────────────────────────────────────────────


def test_urls():
    assert T.page_url(KEY, T.RIDE_SERVICE, 1, 1000, "202609") == \
        "http://openapi.seoul.go.kr:8088/{}/json/CardSubwayTime/1/1000/202609".format(KEY)
    assert T.page_url(KEY, T.MASTER_SERVICE, 1, 1000) == \
        "http://openapi.seoul.go.kr:8088/{}/json/subwayStationMaster/1/1000/".format(KEY)


def test_key_and_mask_come_from_the_openclose_collector():
    import collect_seoul_openclose as C  # noqa: PLC0415
    assert T.get_api_key is C.get_api_key and T.mask_secret is C.mask_secret and T.API_BASE == C.API_BASE
    assert (T.COLLECTOR, T.SCOPE_KEY, T.DEFAULT_START, T.DEFAULT_MAX_CALLS) == ("seoul_subway", "seoul", "202101", 300)


# ── 2. 봉투 ──────────────────────────────────────────────────────────────────


def test_envelope_ok_and_no_data_and_odd_shape():
    assert T.read_envelope(ok_payload(T.RIDE_SERVICE, 2, [ride_row(), "x"]), T.RIDE_SERVICE)[:3] == \
        ("INFO-000", "정상 처리되었습니다", 2)
    assert len(T.read_envelope(ok_payload(T.RIDE_SERVICE, 2, [ride_row(), "x"]), T.RIDE_SERVICE)[3]) == 1
    assert T.read_envelope(NO_DATA, T.RIDE_SERVICE) == ("INFO-200", "해당하는 데이터가 없습니다.", 0, [])
    assert T.read_envelope([1, 2], T.RIDE_SERVICE) == ("", "", 0, [])
    # 다른 서비스 열쇠로 온 봉투는 그 서비스로 읽지 않는다.
    assert T.read_envelope(ok_payload(T.MASTER_SERVICE, 1, [master_row()]), T.RIDE_SERVICE)[0] == ""


def test_info_200_is_zero_rows_and_info_100_stops():
    s = FakeSession([FakeResp(NO_DATA)])
    assert T.fetch_page(s, KEY, T.RIDE_SERVICE, 1, 1000, "202610", sleep=no_sleep) == ("INFO-200", 0, [])
    with pytest.raises(T.ServiceKeyError):
        T.fetch_page(FakeSession([FakeResp(BAD_KEY)]), KEY, T.RIDE_SERVICE, 1, 1000, "202609", sleep=no_sleep)


def test_odd_shape_is_an_api_error():
    with pytest.raises(T.ApiError):
        T.fetch_page(FakeSession([FakeResp({"what": 1})]), KEY, T.RIDE_SERVICE, 1, 1000, "202609", sleep=no_sleep)


def test_retries_only_server_errors():
    s = FakeSession([FakeResp({}, 503), FakeResp(ok_payload(T.RIDE_SERVICE, 1, [ride_row()]))])
    assert T.fetch_page(s, KEY, T.RIDE_SERVICE, 1, 1000, "202609", sleep=no_sleep)[1] == 1
    assert len(s.urls) == 2
    with pytest.raises(T.ApiError):
        T.fetch_page(FakeSession([FakeResp({}, 404)]), KEY, T.RIDE_SERVICE, 1, 1000, "202609", sleep=no_sleep)


# ── 3. 씨앗 범위 · pending 만 ────────────────────────────────────────────────


def test_month_range_newest_first_and_bad_input():
    got = T.month_range("202101", "202609")
    assert got[0] == "202609" and got[-1] == "202101" and len(got) == 69
    assert T.month_range("202512", "202602") == ["202602", "202601", "202512"]
    for bad in ("2026-09", "202613", "20269", ""):
        with pytest.raises(ValueError):
            T.month_range("202101", bad)
    with pytest.raises(ValueError):
        T.month_range("202610", "202609")


def test_todo_is_pending_and_unseeded_only_unless_retry_failed():
    months = ["202609", "202608", "202607", "202606"]
    progress = {"202609": ("pending", 0), "202608": ("done", 0), "202607": ("failed", 2)}
    assert T.todo_months(months, progress) == ["202609", "202606"]
    assert T.todo_months(months, progress, retry_failed=True) == ["202609", "202607", "202606"]


def test_seed_keeps_existing_rows(monkeypatch):
    got = {}
    monkeypatch.setattr(T, "upsert_batch", lambda _b, _h, tbl, rows, how: got.update(tbl=tbl, rows=rows, how=how))
    T.seed_progress("https://x", {}, ["202609", "202608"])
    assert got["tbl"] == "collect_progress" and got["how"] == "ignore-duplicates"
    assert [r["period_key"] for r in got["rows"]] == ["202609", "202608"]
    assert {r["status"] for r in got["rows"]} == {"pending"}


# ── 4. 한 달 받기 ────────────────────────────────────────────────────────────


def test_month_done_writes_the_rows_as_received(tmp_path):
    rows = [ride_row(), ride_row(), ride_row(sttn="역삼")]          # 같은 줄 두 번도 그대로(거르는 건 적재기)
    s = FakeSession([FakeResp(ok_payload(T.RIDE_SERVICE, 3, rows))])
    r = month(s, "202609", tmp_path)
    assert r == {"status": "done", "row_count": 3, "error_msg": None}
    path = tmp_path / "ridership" / "202609_20261102.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    assert obj == {"service": "CardSubwayTime", "ym": "202609", "fetched_at": FETCHED_AT, "total": 3, "rows": rows}


def test_month_info_200_stays_pending_without_a_file(tmp_path):
    r = month(FakeSession([FakeResp(NO_DATA)]), "202610", tmp_path)
    assert r["status"] == "pending" and r["row_count"] == 0 and "done 으로 굳히지 않는다" in r["error_msg"]
    assert not (tmp_path / "ridership").exists()


def test_month_other_use_mm_stays_pending(tmp_path):
    s = FakeSession([FakeResp(ok_payload(T.RIDE_SERVICE, 2, [ride_row(), ride_row(ym="202608")]))])
    r = month(s, "202609", tmp_path)
    assert r["status"] == "pending" and "다른 달 행" in r["error_msg"]
    assert not (tmp_path / "ridership").exists()


def test_month_total_mismatch_stays_pending(tmp_path):
    s = FakeSession([FakeResp(ok_payload(T.RIDE_SERVICE, 5, [ride_row()])),
                     FakeResp(ok_payload(T.RIDE_SERVICE, 5, []))])         # 둘째 쪽이 비어 온다
    r = month(s, "202609", tmp_path)
    assert r["status"] == "pending" and "≠ list_total_count" in r["error_msg"]
    assert not (tmp_path / "ridership").exists()


def test_month_api_error_is_failed(tmp_path):
    s = FakeSession([FakeResp({}, 404)])
    r = month(s, "202609", tmp_path)
    assert r["status"] == "failed" and "HTTP 404" in r["error_msg"]


def test_month_over_two_pages_stops(tmp_path):
    s = FakeSession([FakeResp(ok_payload(T.RIDE_SERVICE, 2001, [ride_row()]))])
    r = month(s, "202609", tmp_path)
    assert r["status"] == "pending" and "쪽 상한" in r["error_msg"]
    assert len(s.urls) == 1


def test_month_two_pages_are_joined(tmp_path):
    a = [ride_row(sttn="역{}".format(i)) for i in range(1000)]
    s = FakeSession([FakeResp(ok_payload(T.RIDE_SERVICE, 1001, a)),
                     FakeResp(ok_payload(T.RIDE_SERVICE, 1001, [ride_row(sttn="끝")]))])
    assert month(s, "202609", tmp_path)["row_count"] == 1001
    assert s.urls[1].endswith("/CardSubwayTime/1001/2000/202609")


def test_call_cap_stops_before_calling(tmp_path):
    s = FakeSession([])
    r = month(s, "202609", tmp_path, calls=[300], max_calls=300)
    assert r["status"] == "pending" and "상한" in r["error_msg"] and s.urls == []


# ── 5. 마스터 파일 ───────────────────────────────────────────────────────────


def test_master_file_name_and_no_overwrite(tmp_path):
    def run():
        s = FakeSession([FakeResp(ok_payload(T.MASTER_SERVICE, 1, [master_row()]))])
        return T.collect_master(s, KEY, str(tmp_path), "20261102", FETCHED_AT, [0], between=no_sleep, sleep=no_sleep)

    first, second, third = run(), run(), run()
    assert [os.path.basename(p) for p in (first, second, third)] == ["20261102.json", "20261102_2.json",
                                                                     "20261102_3.json"]
    obj = json.loads(open(first, encoding="utf-8").read())
    assert obj["service"] == "subwayStationMaster" and obj["total"] == 1 and obj["rows"] == [master_row()]
    assert "ym" not in obj


def test_master_zero_rows_is_an_error(tmp_path):
    with pytest.raises(T.ApiError):
        T.collect_master(FakeSession([FakeResp(NO_DATA)]), KEY, str(tmp_path), "20261102", FETCHED_AT, [0],
                         between=no_sleep, sleep=no_sleep)
    assert not (tmp_path / "master").exists()


# ── 6. 인자 · dry-run · 키 가림 ──────────────────────────────────────────────


def test_end_month_is_required():
    with pytest.raises(SystemExit) as e:
        T.parse_args([])
    assert e.value.code == 2
    assert T.parse_args(["--master"]).month_list == []
    assert len(T.parse_args(["--end-month", "202609"]).month_list) == 69


def test_bad_end_month_is_exit_2(monkeypatch):
    monkeypatch.setattr(T, "get_api_key", lambda: KEY)
    monkeypatch.setattr(T, "get_supabase_config", lambda: ("https://x", "k"))
    assert T.main(["--end-month", "2026-09"]) == 2


def test_dry_run_writes_nothing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(T, "get_api_key", lambda: KEY)
    monkeypatch.setattr(T, "get_supabase_config", lambda: ("https://x", "k"))
    seen = []
    monkeypatch.setattr(T, "fetch_page", lambda _s, _k, svc, *a, **k: seen.append((svc, a)) or ("INFO-000", 621, []))
    monkeypatch.setattr(T, "read_progress", lambda *a, **k: {"202609": ("done", 0)})

    def boom(*a, **k):
        raise AssertionError("dry-run 이 DB·파일에 쓰려 했습니다")

    for name in ("seed_progress", "save_progress", "upsert_batch", "write_new"):
        monkeypatch.setattr(T, name, boom)
    rc = T.main(["--dry-run", "--end-month", "202609", "--raw-dir", str(tmp_path)])
    assert rc == 0 and seen == [("CardSubwayTime", (1, 1, "202609"))]
    assert os.listdir(tmp_path) == []
    out = capsys.readouterr().out
    assert "이번에 받을 달 68개" in out and "아무것도 쓰지 않았습니다" in out


class RaisingSession:
    def get(self, url, timeout=None):
        raise requests.ConnectionError("Max retries exceeded with url: {}".format(url))


def _dry_run_said_on_network_error(monkeypatch, capsys, key, mask=None):
    monkeypatch.setattr(T, "get_api_key", lambda: key)
    monkeypatch.setattr(T, "get_supabase_config", lambda: ("https://x", "k"))
    monkeypatch.setattr(T, "read_progress", lambda *a, **k: {})
    monkeypatch.setattr(T.requests, "Session", RaisingSession)
    monkeypatch.setattr(T, "fetch_page", lambda *x, **k: REAL_FETCH(*x, sleep=no_sleep, **k))
    if mask is not None:
        monkeypatch.setattr(T, "mask_secret", mask)
    rc = T.main(["--dry-run", "--end-month", "202609"])
    out = capsys.readouterr()
    return rc, out.out + out.err


def test_dry_run_error_output_never_holds_the_key(monkeypatch, capsys):
    key = "TESTKEY1234567890"
    rc, said = _dry_run_said_on_network_error(monkeypatch, capsys, key)
    assert rc == 1 and "[에러]" in said
    assert key not in said and T.SECRET_MASK in said


def test_dry_run_error_masking_positive_control(monkeypatch, capsys):
    """양성 대조 — 가림을 끈 흉내 함수로는 같은 길에서 키가 찍힌다(위 '키 0' 이 빈 검사가 아니다)."""
    key = "TESTKEY1234567890"
    rc, said = _dry_run_said_on_network_error(monkeypatch, capsys, key, mask=lambda text, key=None: str(text))
    assert rc == 1 and key in said


def test_failed_month_error_never_holds_the_key(tmp_path):
    key = "TESTKEY1234567890"
    r = T.collect_month(RaisingSession(), key, "202609", str(tmp_path), "20261102", FETCHED_AT, [0],
                        between=no_sleep, sleep=no_sleep)
    assert r["status"] == "failed" and key not in r["error_msg"] and T.SECRET_MASK in r["error_msg"]
