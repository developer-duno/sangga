# -*- coding: utf-8 -*-
"""
scripts/collectors/collect_transactions.py 단위 테스트

라이브 API·Supabase 없이 검증한다 (requests는 전부 흉내낸다):
  1. month_range        — 계약년월 목록 생성(연도 넘김·옛날→최근 순)
  2. 응답 파싱          — resultCode/totalCount/items(dict 1건·list N건·0건)
  3. page_count         — totalCount 기반 페이지네이션·절단 판정
  4. mask_secret        — 인증키가 로그·DB로 새지 않게
  5. 신호 감지          — 쿼터 초과 / 서비스키 오류를 갈라 본다
  6. append_jsonl       — raw append 모드(덮어쓰기 금지)
  7. fetch_page         — resultCode '000' 판정·재시도·쿼터/키 오류 분기
  8. fetch_all_pages    — 실패해도 보낸 호출 수를 센다(예산 과소집계 방지)
  9. collect_one_month  — raw 원자성(실패 시 무기록)
 10. parse_args / budget_verdict

conftest.py를 새로 만들지 않기 위해(다른 수집기 작업과 충돌 방지),
sys.path 조작은 이 파일 안에서만 한다.
"""

import json
import os
import sys

import pytest
import requests

_COLLECTORS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "collectors",
)
_SCRIPTS_DIR = os.path.dirname(_COLLECTORS_DIR)
for _p in (_SCRIPTS_DIR, _COLLECTORS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import collect_transactions as target  # noqa: E402


# ── 픽스처 (2026-08-08 라이브 실측 응답 형태 그대로) ──────────────────────────

ITEM_JIPHAP = {
    "buildYear": "1993", "buildingAr": "28.8", "buildingType": "집합",
    "buildingUse": "제1종근린생활", "cdealDay": " ", "cdealType": " ",
    "dealAmount": "136,000", "dealDay": "25", "dealMonth": "6", "dealYear": "2026",
    "floor": "1", "jibun": "716", "landUse": "제3종일반주거",
    "plottageAr": " ", "sggCd": "11680", "sggNm": "강남구", "umdNm": "일원동",
}
ITEM_ILBAN = dict(ITEM_JIPHAP, buildingType="일반", jibun="6**", floor=" ")


def envelope(items, total_count=None, code="000", msg="OK"):
    """포털 응답 봉투. items=None이면 0건 형태(items가 빈 문자열)를 흉내낸다."""
    if items is None:
        body = {"items": "", "totalCount": 0}
    else:
        body = {"items": {"item": items},
                "totalCount": total_count if total_count is not None else
                (len(items) if isinstance(items, list) else 1)}
    return {"response": {"header": {"resultCode": code, "resultMsg": msg}, "body": body}}


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text else (json.dumps(payload, ensure_ascii=False)
                                       if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _FakeSession:
    """get() 호출마다 준비된 응답을 차례로 돌려준다. 호출 기록도 남긴다."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


# ── 1. month_range ───────────────────────────────────────────────────────────


def test_month_range_is_oldest_first():
    """옛날→최근 순이어야 이어받기 구간이 연속으로 남는다."""
    assert target.month_range("202606", 3) == ["202604", "202605", "202606"]


def test_month_range_crosses_year_boundary():
    assert target.month_range("202601", 3) == ["202511", "202512", "202601"]


def test_month_range_pilot_is_240_months():
    """§5.3 1단계 파일럿 = 1개 구 x 20년."""
    months = target.month_range("202606", target.DEFAULT_MONTHS)
    assert len(months) == 240
    assert months[-1] == "202606"
    assert months[0] == "200607"


@pytest.mark.parametrize("bad", ["2026", "20260", "2026-06", "202613", "202600", "abcdef"])
def test_month_range_rejects_bad_ym(bad):
    with pytest.raises(ValueError):
        target.month_range(bad, 3)


def test_month_range_rejects_non_positive_months():
    with pytest.raises(ValueError):
        target.month_range("202606", 0)


# ── 2. 응답 파싱 ─────────────────────────────────────────────────────────────


def test_read_result_code_and_total_count():
    p = envelope([ITEM_JIPHAP], total_count=48)
    assert target.read_result_code(p) == ("000", "OK")
    assert target.read_total_count(p) == 48


def test_read_result_code_handles_garbage():
    assert target.read_result_code(None) == ("", "")
    assert target.read_result_code({"response": "이상함"}) == ("", "")
    assert target.read_total_count({"response": {"body": {"totalCount": "?"}}}) == 0


def test_extract_items_single_dict():
    assert target.extract_items(envelope(ITEM_JIPHAP)) == [ITEM_JIPHAP]


def test_extract_items_list():
    assert target.extract_items(envelope([ITEM_JIPHAP, ITEM_ILBAN])) == [ITEM_JIPHAP, ITEM_ILBAN]


def test_extract_items_empty_body():
    assert target.extract_items(envelope(None)) == []


# ── 3. 페이지네이션 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("total,expected", [(0, 1), (1, 1), (1000, 1), (1001, 2), (2500, 3)])
def test_page_count(total, expected):
    assert target.page_count(total) == expected


def test_page_count_clamps_to_max_pages():
    huge = target.NUM_OF_ROWS * target.MAX_PAGES * 5
    assert target.page_count(huge) == target.MAX_PAGES


def test_is_truncated_only_when_clamp_actually_hit():
    assert target.is_truncated(48) is False
    assert target.is_truncated(target.NUM_OF_ROWS * target.MAX_PAGES) is False
    assert target.is_truncated(target.NUM_OF_ROWS * target.MAX_PAGES + 1) is True


# ── 4. mask_secret ───────────────────────────────────────────────────────────


def test_mask_secret_hides_query_form():
    out = target.mask_secret("GET https://x?serviceKey=ABC123&LAWD_CD=11680")
    assert "ABC123" not in out
    assert target.SECRET_MASK in out


def test_mask_secret_hides_bare_and_urlencoded_key():
    key = "a+b/c=="
    out = target.mask_secret("키가 그냥 박힘: a+b/c== 그리고 a%2Bb%2Fc%3D%3D", key)
    assert "a+b/c==" not in out
    assert "a%2Bb%2Fc%3D%3D" not in out


def test_mask_secret_none_is_empty():
    assert target.mask_secret(None) == ""


# ── 5. 쿼터 / 서비스키 신호 ──────────────────────────────────────────────────


@pytest.mark.parametrize("text", [
    "LIMITED NUMBER OF SERVICE REQUESTS EXCEEDS ERROR",
    "limited_number_of_service_requests_exceeds_error",
    "LIMITED-NUMBER-OF-SERVICE-REQUESTS-EXCEEDS",
])
def test_is_quota_exceeded_tolerates_separator_variants(text):
    assert target.is_quota_exceeded(text) is True


def test_quota_and_service_key_signals_do_not_cross():
    """둘은 원인도 조치도 달라 반드시 갈라져야 한다 (쿼터는 내일, 키는 재발급)."""
    assert target.is_service_key_error("SERVICE_KEY_IS_NOT_REGISTERED_ERROR") is True
    assert target.is_quota_exceeded("SERVICE_KEY_IS_NOT_REGISTERED_ERROR") is False
    assert target.is_service_key_error("LIMITED NUMBER OF SERVICE REQUESTS EXCEEDS") is False


# ── 6. raw 기록 ──────────────────────────────────────────────────────────────


def test_raw_path_is_one_file_per_sigungu(tmp_path):
    p = target.raw_path(str(tmp_path), "11680")
    assert p.endswith("11680.jsonl")


def test_append_jsonl_appends_and_keeps_context(tmp_path):
    path = os.path.join(str(tmp_path), "11680.jsonl")
    target.append_jsonl(path, "11680", "202606", [ITEM_JIPHAP], "2026-08-08T00:00:00+09:00")
    target.append_jsonl(path, "11680", "202605", [ITEM_ILBAN], "2026-08-08T00:00:01+09:00")

    rows = [json.loads(x) for x in open(path, encoding="utf-8")]
    assert len(rows) == 2, "append여야 한다 — 덮어쓰면 앞 달치가 사라진다"
    assert [r["deal_ym"] for r in rows] == ["202606", "202605"]
    assert rows[0]["item"]["jibun"] == "716"
    assert rows[0]["sigungu_code"] == "11680"


def test_append_jsonl_creates_missing_dir(tmp_path):
    path = os.path.join(str(tmp_path), "없던폴더", "11680.jsonl")
    target.append_jsonl(path, "11680", "202606", [ITEM_JIPHAP], "t")
    assert os.path.exists(path)


# ── 7. fetch_page ────────────────────────────────────────────────────────────


def test_fetch_page_success_sends_expected_params():
    s = _FakeSession([_FakeResponse(200, envelope([ITEM_JIPHAP]))])
    payload = target.fetch_page(s, "KEY", "11680", "202606", 1)
    assert target.extract_items(payload) == [ITEM_JIPHAP]
    p = s.calls[0]["params"]
    assert p["LAWD_CD"] == "11680" and p["DEAL_YMD"] == "202606"
    assert p["_type"] == "json" and p["numOfRows"] == target.NUM_OF_ROWS


def test_fetch_page_accepts_three_digit_ok_code():
    """★ 이 API의 성공 코드는 '000'이다 — 건축HUB의 '00'으로 비교하면 전부 실패한다."""
    assert target.RESULT_CODE_OK == "000"
    s = _FakeSession([_FakeResponse(200, envelope([ITEM_JIPHAP], code="000"))])
    assert target.extract_items(target.fetch_page(s, "K", "11680", "202606", 1))


def test_fetch_page_raises_on_other_result_code():
    s = _FakeSession([_FakeResponse(200, envelope([], code="99", msg="이상"))])
    with pytest.raises(target.ApiError, match="resultCode=99"):
        target.fetch_page(s, "K", "11680", "202606", 1)


def test_fetch_page_quota_error_is_not_retried():
    s = _FakeSession([_FakeResponse(200, None, text="LIMITED NUMBER OF SERVICE REQUESTS EXCEEDS")])
    with pytest.raises(target.QuotaExceededError):
        target.fetch_page(s, "K", "11680", "202606", 1, sleep=lambda _s: None)
    assert len(s.calls) == 1, "쿼터 초과는 재시도하면 안 된다"


def test_fetch_page_service_key_error_is_not_retried():
    s = _FakeSession([_FakeResponse(200, None, text="SERVICE_KEY_IS_NOT_REGISTERED_ERROR")])
    with pytest.raises(target.ServiceKeyError):
        target.fetch_page(s, "K", "11680", "202606", 1, sleep=lambda _s: None)
    assert len(s.calls) == 1


def test_fetch_page_retries_5xx_then_succeeds():
    s = _FakeSession([
        _FakeResponse(503, None, text="bad gateway"),
        _FakeResponse(200, envelope([ITEM_JIPHAP])),
    ])
    slept = []
    payload = target.fetch_page(s, "K", "11680", "202606", 1, sleep=slept.append)
    assert target.extract_items(payload) == [ITEM_JIPHAP]
    assert len(s.calls) == 2 and slept == [2]


def test_fetch_page_masks_key_in_network_error():
    """requests 예외 문자열에는 요청 URL(=serviceKey)이 들어간다 — DB에 박제되면 안 된다."""
    s = _FakeSession([requests.RequestException("https://x?serviceKey=SECRET")])
    with pytest.raises(target.ApiError) as e:
        target.fetch_page(s, "SECRET", "11680", "202606", 1,
                          retry_count=1, sleep=lambda _s: None)
    assert "SECRET" not in str(e.value)


# ── 8. fetch_all_pages — 실패해도 호출 수를 센다 ─────────────────────────────


def test_fetch_all_pages_walks_every_page():
    s = _FakeSession([
        _FakeResponse(200, envelope([ITEM_JIPHAP] * 1000, total_count=1500)),
        _FakeResponse(200, envelope([ITEM_ILBAN] * 500, total_count=1500)),
    ])
    items, calls, truncated = target.fetch_all_pages(s, "K", "11680", "202606")
    assert len(items) == 1500 and calls == 2 and truncated is False


def test_fetch_all_pages_counts_calls_even_when_it_fails():
    """실패한 호출도 포털 한도를 먹는다 — 안 세면 예산이 남았다고 착각한다.

    2026-08-07 건축HUB에서 겪은 "잔여 예산은 상한이지 보장이 아니다"와 같은 결의
    과소집계를 막는 회귀 가드.
    """
    s = _FakeSession([
        _FakeResponse(200, envelope([ITEM_JIPHAP] * 1000, total_count=3000)),
        _FakeResponse(200, envelope([], code="99", msg="2페이지에서 터짐")),
    ])
    counter = [0]
    with pytest.raises(target.ApiError):
        target.fetch_all_pages(s, "K", "11680", "202606", call_counter=counter,
                               retry_count=1, sleep=lambda _s: None)
    assert counter[0] == 2, "터진 그 호출까지 세어야 한다"


# ── 9. collect_one_month — raw 원자성 ────────────────────────────────────────


def test_collect_one_month_writes_raw_and_reports(tmp_path):
    s = _FakeSession([_FakeResponse(200, envelope([ITEM_JIPHAP, ITEM_ILBAN]))])
    r = target.collect_one_month(s, "K", "11680", "202606", str(tmp_path))
    assert r["status"] == "done" and r["row_count"] == 2 and r["calls"] == 1
    rows = [json.loads(x) for x in open(target.raw_path(str(tmp_path), "11680"), encoding="utf-8")]
    assert len(rows) == 2


def test_collect_one_month_writes_nothing_when_it_fails(tmp_path):
    """중간 실패 시 raw에 한 줄도 남기지 않는다 — 재실행 때 이중 적재를 막는 불변식."""
    s = _FakeSession([_FakeResponse(200, envelope([], code="99", msg="터짐"))])
    r = target.collect_one_month(s, "K", "11680", "202606", str(tmp_path),
                                 retry_count=1, sleep=lambda _s: None)
    assert r["status"] == "failed" and r["calls"] == 1
    assert not os.path.exists(target.raw_path(str(tmp_path), "11680"))


def test_collect_one_month_lets_quota_error_through(tmp_path):
    """쿼터 초과는 잡지 않고 올려보낸다 — 안전 종료는 호출부 책임."""
    s = _FakeSession([_FakeResponse(200, None, text="LIMITED NUMBER OF SERVICE REQUESTS EXCEEDS")])
    with pytest.raises(target.QuotaExceededError):
        target.collect_one_month(s, "K", "11680", "202606", str(tmp_path),
                                 sleep=lambda _s: None)


def test_collect_one_month_flags_truncation(tmp_path):
    huge = target.NUM_OF_ROWS * target.MAX_PAGES + 1
    s = _FakeSession([_FakeResponse(200, envelope([ITEM_JIPHAP], total_count=huge))]
                     + [_FakeResponse(200, envelope([ITEM_JIPHAP], total_count=huge))]
                     * (target.MAX_PAGES - 1))
    r = target.collect_one_month(s, "K", "11680", "202606", str(tmp_path))
    assert r["status"] == "done"
    assert "절단" in (r["error_msg"] or "")


# ── 10. parse_args / budget_verdict ──────────────────────────────────────────


def test_parse_args_defaults_to_gangnam_pilot():
    o = target.parse_args([])
    assert o["sigungu_code"] == target.DEFAULT_SIGUNGU_CODE
    assert o["months"] == target.DEFAULT_MONTHS
    assert o["dry_run"] is False and o["retry_failed"] is False
    assert o["raw_dir"].endswith(os.path.join("data", "raw", "rtms"))


def test_parse_args_overrides():
    o = target.parse_args(["--sigungu-code", "11440", "--months", "6",
                           "--end-ym", "202512", "--daily-budget", "100",
                           "--limit", "3", "--dry-run", "--retry-failed"])
    assert o["sigungu_code"] == "11440" and o["months"] == 6
    assert o["end_ym"] == "202512" and o["daily_budget"] == 100
    assert o["limit"] == 3 and o["dry_run"] and o["retry_failed"]


def test_parse_args_missing_value():
    with pytest.raises(ValueError, match="뒤에 값이 필요"):
        target.parse_args(["--months"])


def test_parse_args_rejects_unknown_flag_like_help():
    """--help 를 조용히 무시하면 dry_run=False 인 실제 실행이 되어버린다(2026-08-08 실사고)."""
    with pytest.raises(ValueError, match="알 수 없는 인자"):
        target.parse_args(["--help"])


def test_parse_args_rejects_typo_does_not_silently_set_dry_run():
    """--dryrun(오타)이 --dry-run으로 조용히 넘어가면 실제 실행 + API 예산 소모로 이어진다."""
    with pytest.raises(ValueError, match="알 수 없는 인자"):
        target.parse_args(["--dryrun"])


def test_parse_args_rejects_typo_limit_flag():
    """--limitt(오타)를 무시하면 '소량 시험'이 전량 실행으로 바뀐다."""
    with pytest.raises(ValueError, match="알 수 없는 인자"):
        target.parse_args(["--limitt", "50"])


def test_budget_verdict_fits_when_budget_is_enough():
    v = target.budget_verdict(calls_used=100, planned_calls=240, budget=9500)
    assert v["remaining"] == 9400
    assert v["fits"] is True
    assert v["shortfall"] == 0


def test_budget_verdict_reports_shortfall_when_not_enough():
    v = target.budget_verdict(calls_used=9400, planned_calls=240, budget=9500)
    assert v["remaining"] == 100
    assert v["fits"] is False
    assert v["shortfall"] == 140


def test_budget_verdict_exact_fit_is_still_a_fit():
    v = target.budget_verdict(calls_used=9260, planned_calls=240, budget=9500)
    assert v["remaining"] == 240 and v["fits"] is True and v["shortfall"] == 0


def test_budget_verdict_never_reports_negative_remaining():
    v = target.budget_verdict(calls_used=99999, planned_calls=10, budget=9500)
    assert v["remaining"] == 0 and v["fits"] is False and v["shortfall"] == 10


# ── 11. 호출 수 주기 기록 (강제 종료 시 유실 방지) ───────────────────────────


def test_maybe_flush_does_not_write_before_interval(monkeypatch):
    """조합마다 DB를 두드리면 수집이 느려진다 — 주기에 도달했을 때만 적는다."""
    called = []
    monkeypatch.setattr(target, "flush_quota_log", lambda *a: called.append(a[-1]))
    assert target.maybe_flush_quota_log("u", {}, "2026-08-09", 0, 99, 0) == 0
    assert called == []


def _stub_main_deps(monkeypatch, months, flushed, flush_fail_first=0):
    """main()의 DB·API를 전부 흉내낸다. flushed에 flush_quota_log가 받은 session_calls를 쌓는다."""
    state = {"fails": flush_fail_first}
    processed = []

    monkeypatch.setattr(target, "get_supabase_config", lambda: ("https://x.supabase.co", "k"))
    monkeypatch.setattr(target, "get_api_key", lambda: "APIKEY")
    monkeypatch.setattr(target, "seed_progress", lambda *a, **kw: len(months))
    monkeypatch.setattr(target, "fetch_pending", lambda *a, **kw: [(ym, 0) for ym in months])
    monkeypatch.setattr(target, "progress_status_counts", lambda *a, **kw: target.Counter())
    monkeypatch.setattr(target, "read_quota_baseline", lambda *a, **kw: 0)
    monkeypatch.setattr(target, "save_progress", lambda *a, **kw: None)
    monkeypatch.setattr(target, "install_sigint_handler", lambda: None)

    def fake_collect_one_month(session, key, sigungu, deal_ym, raw_dir, **kw):  # noqa: ARG001
        processed.append(deal_ym)
        return {"status": "done", "row_count": 1, "error_msg": None, "calls": 1}

    def fake_flush(base_url, headers, log_date, baseline, session_calls):  # noqa: ARG001
        if state["fails"] > 0:
            state["fails"] -= 1
            raise RuntimeError("api_quota_log 저장 실패 (HTTP 503)")
        flushed.append(session_calls)

    monkeypatch.setattr(target, "collect_one_month", fake_collect_one_month)
    monkeypatch.setattr(target, "flush_quota_log", fake_flush)
    monkeypatch.setattr(sys, "argv", ["prog", "--months", "250", "--end-ym", "202607",
                                      "--daily-budget", "100000"])
    return processed


def test_main_flushes_quota_every_100_calls(monkeypatch):
    """★ finally에서만 적으면 강제 종료 시 그 세션 호출 수가 통째로 증발한다.

    2026-08-09 브이월드 실측: raw 10,000줄인데 api_quota_log는 6,952건 — 약 3,000건
    유실. 구조가 같은 이 수집기도 똑같이 뚫린다. 유실된 만큼 같은 날 재실행의
    baseline이 낮게 읽혀 일 예산 캡이 뚫린다.
    """
    flushed = []
    processed = _stub_main_deps(monkeypatch, target.month_range("202607", 250), flushed)

    assert target.main() == 0
    assert len(processed) == 250
    # 100·200에서 중간 기록 + finally 마지막 기록. 값은 누적치라 단조 증가한다.
    assert flushed == [100, 200, 250]


def test_main_continues_and_warns_when_interim_flush_fails(monkeypatch, capsys):
    """기록은 안전장치일 뿐이다 — 그것 때문에 수집이 죽으면 손해가 더 크다.

    단 조용히 넘어가지도 않는다(PR #32: 침묵하는 실패가 가장 위험하다).
    """
    flushed = []
    processed = _stub_main_deps(monkeypatch, target.month_range("202607", 250), flushed,
                                flush_fail_first=1)

    assert target.main() == 0
    assert len(processed) == 250          # 250개월 전부 계속 처리됐다
    out = capsys.readouterr().out
    assert "[경고]" in out and "중간 기록 실패" in out
    # 100에서 실패 → 기준점이 안 밀리므로 **다음 호출(101)에서 곧바로 재시도**한다.
    # 값이 누적치라 한 번만 성공해도 그때까지의 호출이 전부 장부에 들어간다(손실 0).
    assert flushed == [101, 201, 250]
