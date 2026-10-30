# -*- coding: utf-8 -*-
"""scripts/collectors/collect_seoul_trdar.py 단위 테스트 (결정 0045 PR② · 수집기 1:1).

라이브 API·Supabase 없이 본다(HTTP 는 가짜 세션 · 장부는 가짜 함수):
  1. 서비스 표 · 장부 이름이 서비스마다 갈린다
  2. 주소 — 분기 자료는 끝에 분기 · 연 1회 자료는 분기 칸 없이 끝 빗금
  3. 봉투 · 키 가림(오류 문구에 키 글자 0 — 양성 대조 포함)
  4. 분기 자료 — 0건 pending · 끝까지 받아 파일 · 다른 분기 행 거부
  5. 연 1회 자료 — 쪽 이어받기(done 쪽 건너뜀) · ⛔ **분기 나누기**(섞인 쪽 → 분기 파일 · 행수 보존 · 중복 0)
  6. 인자 — `--end-quarter`·`--service` 의무 · 모르는 서비스 exit 2 · dry-run 쓰기 0(장부 읽기만)
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

import collect_seoul_trdar as T  # noqa: E402

KEY = "abcd1234SECRET"
REAL_FETCH = T.fetch_page          # 재시도 대기만 끈 진짜 fetch_page 를 끼울 때 쓴다
FETCHED_AT = "2026-10-31T10:00:00+09:00"


def pop_row(quarter="20262", trdar="3110001", tot=171658.0):
    """2026-10-31 표본(VwsmTrdarRepopQq) 꼴 — 영문 대문자 · 숫자는 실수."""
    return {"STDR_YYQU_CD": quarter, "TRDAR_SE_CD": "A", "TRDAR_SE_CD_NM": "골목상권",
            "TRDAR_CD": trdar, "TRDAR_CD_NM": "이북5도청사", "TOT_REPOP_CO": tot}


def sales_row(quarter="20262", trdar="3120188", induty="CS100008"):
    return {"STDR_YYQU_CD": quarter, "TRDAR_SE_CD": "D", "TRDAR_SE_CD_NM": "발달상권",
            "TRDAR_CD": trdar, "TRDAR_CD_NM": "압구정역", "SVC_INDUTY_CD": induty,
            "SVC_INDUTY_CD_NM": "분식전문점", "THSMON_SELNG_AMT": 1880979478.0, "THSMON_SELNG_CO": 157199.0}


def ok_payload(service, total, rows):
    return {T.SERVICES[service]: {"list_total_count": total,
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


class FakeLedger:
    """collect_progress 흉내 — {(collector, scope): {period: (status, attempts)}}."""

    def __init__(self):
        self.rows = {}
        self.writes = 0

    def install(self, monkeypatch):
        monkeypatch.setattr(T, "seed_progress", self.seed)
        monkeypatch.setattr(T, "read_progress", self.read)
        monkeypatch.setattr(T, "save_progress", self.save)

    def seed(self, _b, _h, service, scope, keys):
        self.writes += 1
        book = self.rows.setdefault((T.collector_name(service), scope), {})
        for k in keys:
            book.setdefault(k, ("pending", 0))

    def read(self, _b, _h, service, scope):
        return dict(self.rows.get((T.collector_name(service), scope), {}))

    def save(self, _b, _h, service, scope, key, result, attempts):
        self.writes += 1
        self.rows.setdefault((T.collector_name(service), scope), {})[key] = (result["status"], attempts)


# ── 1. 서비스 표 ─────────────────────────────────────────────────────────────


def test_service_table_is_the_four_approved_ones():
    assert T.SERVICES == {"sales": "VwsmTrdarSelngQq", "flow": "VwsmTrdarFlpopQq",
                          "resident": "VwsmTrdarRepopQq", "worker": "VwsmTrdarWrcPopltnQq"}
    assert set(T.QUARTERLY) | set(T.YEARLY) == set(T.SERVICES)
    assert T.MAX_PAGES == {"sales": 30, "flow": 3, "resident": 60, "worker": 60}
    assert T.DEFAULT_QUARTERS == 22 and T.DEFAULT_MAX_CALLS == 2000


def test_ledger_names_do_not_mix_between_services():
    names = {T.collector_name(s) for s in T.SERVICES}
    assert names == {"seoul_trdar_sales", "seoul_trdar_flow", "seoul_trdar_resident", "seoul_trdar_worker"}
    assert "seoul_openclose" not in names
    assert T.page_scope("20262") == "seoul_20262"


def test_key_comes_from_the_openclose_collector():
    """키 읽기는 개업·폐업 수집기 것을 import 한다(같은 .env 열쇠 SEOUL_OPENAPI_KEY)."""
    import collect_seoul_openclose as C  # noqa: PLC0415
    assert T.get_api_key is C.get_api_key and T.mask_secret is C.mask_secret


# ── 2. 주소 ──────────────────────────────────────────────────────────────────


def test_url_with_quarter_for_quarterly_services():
    assert T.page_url(KEY, "sales", 1, 1000, "20262") == \
        "http://openapi.seoul.go.kr:8088/{}/json/VwsmTrdarSelngQq/1/1000/20262".format(KEY)
    assert T.page_url(KEY, "flow", 1001, 2000, "20211").endswith("/VwsmTrdarFlpopQq/1001/2000/20211")


def test_url_without_quarter_for_yearly_services():
    assert T.page_url(KEY, "resident", 1, 1000) == \
        "http://openapi.seoul.go.kr:8088/{}/json/VwsmTrdarRepopQq/1/1000/".format(KEY)
    assert T.page_url(KEY, "worker", 36001, 37000).endswith("/VwsmTrdarWrcPopltnQq/36001/37000/")


# ── 3. 봉투 · 키 가림 ────────────────────────────────────────────────────────


def test_read_envelope_normal_no_data_and_wrong_service():
    assert T.read_envelope(ok_payload("flow", 1649, [pop_row()]), "flow")[::2] == ("INFO-000", 1649)
    assert T.read_envelope(NO_DATA, "sales")[:3] == ("INFO-200", "해당하는 데이터가 없습니다.", 0)
    # 다른 서비스 열쇠로 온 봉투는 모양이 이상한 것 — 코드가 빈 글자
    assert T.read_envelope(ok_payload("flow", 1, [pop_row()]), "sales")[0] == ""


def test_error_text_never_holds_the_key():
    s = FakeSession([FakeResp({"RESULT": {"CODE": "ERROR-336", "MESSAGE": "1000건 " + KEY}})])
    with pytest.raises(T.ApiError) as e:
        T.fetch_page(s, KEY, "resident", 1, 5000, sleep=no_sleep)
    assert "ERROR-336" in str(e.value) and KEY not in str(e.value)
    s = FakeSession([FakeResp(BAD_KEY)])
    with pytest.raises(T.ServiceKeyError) as e:
        T.fetch_page(s, KEY, "sales", 1, 1000, "20262", sleep=no_sleep)
    assert KEY not in str(e.value)


def test_mask_positive_control():
    """양성 대조 — 가리지 않은 주소에는 키가 있다(위 '키 0' 단언이 빈 검사가 아니다)."""
    url = T.page_url(KEY, "worker", 1, 1000)
    assert KEY in url and KEY not in T.mask_secret(url) and T.SECRET_MASK in T.mask_secret(url)


def test_retry_only_server_errors():
    s = FakeSession([FakeResp({"RESULT": {"CODE": "ERROR-500", "MESSAGE": "서버"}}),
                     requests.ConnectionError("끊김 " + KEY),
                     FakeResp(ok_payload("flow", 1, [pop_row()]))])
    assert T.fetch_page(s, KEY, "flow", 1, 1000, "20262", sleep=no_sleep)[1] == 1
    assert len(s.urls) == 3


# ── 4. 분기 자료 ─────────────────────────────────────────────────────────────


def run_q(tmp_path, replies, service="sales", quarter="20262"):
    s = FakeSession(replies)
    calls = [0]
    res = T.collect_quarter(s, KEY, service, quarter, str(tmp_path), "20261031", FETCHED_AT, calls,
                            sleep=no_sleep)
    return res, s, calls


def test_quarter_full_is_written_under_its_service(tmp_path):
    rows = [sales_row(induty="CS1{:05d}".format(i)) for i in range(3)]
    res, s, calls = run_q(tmp_path, [FakeResp(ok_payload("sales", 3, rows))])
    assert res == {"status": "done", "row_count": 3, "error_msg": None}
    path = tmp_path / "sales" / "20262_20261031.jsonl"
    got = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert [g["row"] for g in got] == rows and {g["quarter"] for g in got} == {"20262"}
    assert s.urls[0].endswith("/VwsmTrdarSelngQq/1/1000/20262") and calls == [1]


@pytest.mark.parametrize("reply", [NO_DATA, ok_payload("flow", 0, [])], ids=["INFO-200", "total0"])
def test_info200_quarter_stays_pending(tmp_path, reply):
    res, _, _ = run_q(tmp_path, [FakeResp(reply)], service="flow", quarter="20263")
    assert res["status"] == "pending" and res["row_count"] == 0
    assert "done 으로 굳히지 않는다" in res["error_msg"]
    assert list(tmp_path.iterdir()) == []


def test_quarter_refuses_rows_of_another_quarter(tmp_path):
    res, _, _ = run_q(tmp_path, [FakeResp(ok_payload("flow", 1, [pop_row(quarter="20261")]))], service="flow")
    assert res["status"] == "pending" and list(tmp_path.iterdir()) == []


# ── 5. 연 1회 자료 — 쪽 이어받기 · 분기 나누기 ───────────────────────────────


def mixed_pages():
    """섞인 쪽 셋(20251·20244·20262 가 쪽마다 섞임) — 총 7행 · 쪽 크기를 3으로 줄여 본다."""
    rows = [pop_row("20251", "A"), pop_row("20244", "A"), pop_row("20262", "A"),
            pop_row("20262", "B"), pop_row("20251", "B"), pop_row("20244", "B"),
            pop_row("20251", "C")]
    return [rows[0:3], rows[3:6], rows[6:7]], rows


def write_pages(tmp_path, service, pages, total, date="20261031"):
    for i, part in enumerate(pages, 1):
        p = tmp_path / service / T.PAGES_DIR / "{}_{}.jsonl".format(T.page_key(i), date)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(json.dumps({"page": T.page_key(i), "total": total, "fetched_at": FETCHED_AT,
                                         "row": r}, ensure_ascii=False) + "\n" for r in part), encoding="utf-8")


def test_split_mixed_pages_into_quarter_files(tmp_path):
    pages, rows = mixed_pages()
    write_pages(tmp_path, "resident", pages, len(rows))
    written = T.split_pages(str(tmp_path), "resident", ["p0001", "p0002", "p0003"], "20261031", FETCHED_AT)
    assert written == {"20244": 2, "20251": 3, "20262": 2}
    assert sum(written.values()) == len(rows)                       # 행수 보존
    seen = []
    for q, n in written.items():
        lines = [json.loads(x) for x in
                 (tmp_path / "resident" / "{}_20261031.jsonl".format(q)).read_text(encoding="utf-8").splitlines()]
        assert len(lines) == n and {x["quarter"] for x in lines} == {q}
        assert all(x["row"]["STDR_YYQU_CD"] == q for x in lines)
        seen += [(q, x["row"]["TRDAR_CD"]) for x in lines]
    assert len(seen) == len(set(seen)) == len(rows)                 # 중복 0


def test_split_by_quarter_drops_nothing_positive_control():
    """양성 대조 — 한 분기 행을 빠뜨린 결과는 행수 합이 줄어 위 단언에 걸린다."""
    _, rows = mixed_pages()
    out = T.split_by_quarter(rows)
    assert sum(len(v) for v in out.values()) == len(rows)
    out.pop("20244")
    assert sum(len(v) for v in out.values()) != len(rows)


def test_split_refuses_duplicates_and_changed_totals(tmp_path):
    with pytest.raises(ValueError, match="겹칩니다"):
        T.split_by_quarter([pop_row("20262", "A"), pop_row("20262", "A")])
    pages, rows = mixed_pages()
    write_pages(tmp_path, "worker", pages[:2], len(rows))
    write_pages(tmp_path / "x", "worker", pages[2:], len(rows) + 1)  # 다른 총건수 쪽을 3쪽 자리로
    src = tmp_path / "x" / "worker" / T.PAGES_DIR / "p0001_20261031.jsonl"
    dst = tmp_path / "worker" / T.PAGES_DIR / "p0003_20261031.jsonl"
    dst.write_bytes(src.read_bytes())
    with pytest.raises(ValueError, match="총건수가 다릅니다"):
        T.split_pages(str(tmp_path), "worker", ["p0001", "p0002", "p0003"], "20261031", FETCHED_AT)
    assert not any(n.endswith(".jsonl") for n in os.listdir(tmp_path / "worker"))   # 분기 파일 0


def test_yearly_run_resumes_pages_and_splits(monkeypatch, tmp_path):
    """1쪽에서 총건수 → 쪽 씨앗 → 2·3쪽 → 다 끝나면 분기 파일. 두 번째 실행은 done 쪽을 다시 안 부른다."""
    monkeypatch.setattr(T, "PAGE_SIZE", 3)
    pages, rows = mixed_pages()
    ledger = FakeLedger()
    ledger.install(monkeypatch)
    a = T.parse_args(["--service", "resident", "--end-quarter", "20262", "--raw-dir", str(tmp_path)])
    s = FakeSession([FakeResp(ok_payload("resident", 7, pages[0])),
                     FakeResp(ok_payload("resident", 7, pages[1])),
                     requests.ConnectionError("x"), requests.ConnectionError("x"), requests.ConnectionError("x")])
    monkeypatch.setattr(T, "fetch_page", lambda *x, **k: REAL_FETCH(*x, sleep=no_sleep, **k))
    calls = [0]
    done, left = T._run_yearly(s, KEY, "b", {}, a, "resident", "20261031", FETCHED_AT, calls)
    assert (done, left) == (1, 1)              # 1쪽(씨앗 전 받은 것)은 save 로 done · 이어서 2쪽 done · 3쪽 끊김
    book = ledger.rows[("seoul_trdar_resident", "seoul_20262")]
    assert book == {"p0001": ("done", 0), "p0002": ("done", 0), "p0003": ("pending", 0)}
    assert s.urls[0].endswith("/VwsmTrdarRepopQq/1/3/") and s.urls[1].endswith("/4/6/")
    assert not os.path.exists(tmp_path / "resident" / "20262_20261031.jsonl")       # 다 받기 전엔 안 나눔
    s2 = FakeSession([FakeResp(ok_payload("resident", 7, pages[2]))])
    done, left = T._run_yearly(s2, KEY, "b", {}, a, "resident", "20261031", FETCHED_AT, [0])
    assert left == 0 and len(s2.urls) == 1 and s2.urls[0].endswith("/7/9/")       # done 쪽 건너뜀
    files = sorted(n for n in os.listdir(tmp_path / "resident") if n.endswith(".jsonl"))
    assert files == ["20244_20261031.jsonl", "20251_20261031.jsonl", "20262_20261031.jsonl"]


def test_yearly_end_quarter_mismatch_only_warns(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(T, "PAGE_SIZE", 3)
    pages, _ = mixed_pages()
    FakeLedger().install(monkeypatch)
    a = T.parse_args(["--service", "worker", "--end-quarter", "20263", "--raw-dir", str(tmp_path)])
    s = FakeSession([FakeResp(ok_payload("worker", 7, p)) for p in pages])
    monkeypatch.setattr(T, "fetch_page", lambda *x, **k: REAL_FETCH(*x, sleep=no_sleep, **k))
    done, left = T._run_yearly(s, KEY, "b", {}, a, "worker", "20261031", FETCHED_AT, [0])
    assert left == 0 and done == 2
    out = capsys.readouterr().out
    assert "20262 ≠ --end-quarter 20263" in out and "경고만" in out


# ── 6. 인자 · dry-run ────────────────────────────────────────────────────────


def test_end_quarter_and_service_are_mandatory():
    with pytest.raises(SystemExit):
        T.parse_args(["--service", "all"])
    with pytest.raises(SystemExit):
        T.parse_args(["--end-quarter", "20262"])
    with pytest.raises(ValueError):
        T.parse_args(["--service", "sales", "--end-quarter", "2026Q2"])
    a = T.parse_args(["--service", "all", "--end-quarter", "20262"])
    assert a.service_list == ["sales", "flow", "resident", "worker"]
    assert len(a.quarter_list) == 22 and a.quarter_list[-1] == "20211"


@pytest.mark.parametrize("argv", [["--end-quarter", "20262"], ["--service", "apt", "--end-quarter", "20262"]])
def test_main_exits_2_on_bad_args(argv):
    with pytest.raises(SystemExit) as e:
        T.main(argv)
    assert e.value.code == 2


def test_dry_run_writes_nothing(monkeypatch, tmp_path):
    """서비스마다 API 1회 · 장부 읽기만 — 씨앗·저장·파일 쓰기 0(개업·폐업 수집기와 같다 · 메인 결정 10-31)."""
    monkeypatch.setattr(T, "get_api_key", lambda: KEY)
    monkeypatch.setattr(T, "get_supabase_config", lambda: ("https://x", "k"))
    seen = []
    monkeypatch.setattr(T, "fetch_page", lambda _s, _k, svc, *a, **k: seen.append(svc) or ("INFO-000", 35908, []))
    monkeypatch.setattr(T, "read_progress", lambda *a, **k: {})

    def boom(*a, **k):
        raise AssertionError("dry-run 이 DB 에 쓰려 했습니다")

    monkeypatch.setattr(T, "upsert_batch", boom)
    monkeypatch.setattr(T, "seed_progress", boom)
    monkeypatch.setattr(T, "save_progress", boom)
    rc = T.main(["--dry-run", "--service", "all", "--end-quarter", "20262", "--raw-dir", str(tmp_path)])
    assert rc == 0 and seen == ["sales", "flow", "resident", "worker"]
    assert list(tmp_path.iterdir()) == []
