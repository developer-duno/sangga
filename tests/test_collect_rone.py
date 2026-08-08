# -*- coding: utf-8 -*-
"""
scripts/collectors/collect_rone.py 단위 테스트

라이브 API·Supabase 없이 검증한다 (requests는 전부 흉내낸다):
  1. quarter_id / quarter_range  — 분기 시점 생성(연도 넘김·옛날→최근 순·1~4만 허용)
  2. 응답 파싱                   — read_result_code/read_total_count/extract_rows
                                    (정상/빈/이상 봉투 3케이스 — R-ONE은 리스트 기반 봉투)
  3. is_quiet_zero               — 형식 오류가 에러 없이 0건으로 오는 함정 가드
  4. floor_bucket_key            — 7구간 매핑 + 미지원 문자열 None
  5. mask_secret                 — 'KEY=' 파라미터를 로그·DB로 새지 않게
  6. fetch_page                  — 'INFO-000' 판정·재시도
  7. collect_one                 — raw 원자성, quiet-zero도 raw 쓰기 경로를 그대로 통과
  8. parse_args

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

import collect_rone as target  # noqa: E402


# ── 픽스처 (§1.2 문서화된 응답 필드 그대로: GRP_FULLNM·CLS_NM·ITM_NM·DTA_VAL 등) ──

ROW_FLOOR_UTIL = {
    "GRP_ID": "1168000000", "GRP_NM": "강남", "GRP_FULLNM": "서울>강남",
    "CLS_NM": "1층", "ITM_NM": "효용비율", "DTA_VAL": "100.0",
    "UI_NM": "%", "WRTTIME_DESC": "2026년 2분기",
}
ROW_REGION_RENT = {
    "GRP_ID": "1168000000", "GRP_NM": "강남", "CLS_NM": "강남",
    "ITM_NM": "임대료", "DTA_VAL": "54.11", "UI_NM": "천원/㎡", "WRTTIME_DESC": "2026년 2분기",
}


def envelope(rows, total_count=None, code="INFO-000", msg="정상 처리되었습니다."):
    """R-ONE 응답 봉투. rows=None이면 0건(quiet-zero) 형태를 흉내낸다."""
    if rows is None:
        row_list, total = [], 0
    else:
        row_list = rows
        total = total_count if total_count is not None else len(rows)
    return {
        "SttsApiTblData": [
            {"head": [{"list_total_count": total}, {"RESULT": {"CODE": code, "MESSAGE": msg}}]},
            {"row": row_list},
        ]
    }


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
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


# ── 1. quarter_id / quarter_range ────────────────────────────────────────────


@pytest.mark.parametrize("q,expected", [(1, "202601"), (2, "202602"), (3, "202603"), (4, "202604")])
def test_quarter_id_formats_two_digit_quarter(q, expected):
    assert target.quarter_id(2026, q) == expected


@pytest.mark.parametrize("bad", [0, 5, -1, 13])
def test_quarter_id_rejects_out_of_range(bad):
    with pytest.raises(ValueError):
        target.quarter_id(2026, bad)


def test_quarter_range_is_oldest_first():
    assert target.quarter_range("202602", 3) == ["202504", "202601", "202602"]


def test_quarter_range_crosses_year_boundary():
    assert target.quarter_range("202601", 2) == ["202504", "202601"]


def test_quarter_range_pilot_default_quarters():
    quarters = target.quarter_range("202602", target.DEFAULT_QUARTERS)
    assert len(quarters) == target.DEFAULT_QUARTERS
    assert quarters[-1] == "202602"


@pytest.mark.parametrize("bad", ["2026", "20260", "2026-2", "20265", "20260", "abcdef"])
def test_quarter_range_rejects_bad_qid(bad):
    with pytest.raises(ValueError):
        target.quarter_range(bad, 3)


def test_quarter_range_rejects_non_positive_count():
    with pytest.raises(ValueError):
        target.quarter_range("202602", 0)


# ── 2. 응답 파싱 (리스트 기반 봉투) ──────────────────────────────────────────


def test_read_result_code_and_total_count_normal_envelope():
    p = envelope([ROW_FLOOR_UTIL], total_count=48)
    assert target.read_result_code(p) == ("INFO-000", "정상 처리되었습니다.")
    assert target.read_total_count(p) == 48


def test_read_result_code_empty_envelope():
    """quiet-zero — 형식 오류가 에러 없이 0건으로 온다(§1.2 실측 함정)."""
    p = envelope([], total_count=0)
    assert target.read_result_code(p) == ("INFO-000", "정상 처리되었습니다.")
    assert target.read_total_count(p) == 0
    assert target.extract_rows(p) == []


@pytest.mark.parametrize("garbage", [
    None,
    {},
    {"SttsApiTblData": "이상함"},
    {"SttsApiTblData": [{"head": "이상함"}]},
    {"SttsApiTblData": [{"head": [{"list_total_count": "?"}]}]},
])
def test_read_result_code_handles_garbage_envelope(garbage):
    assert target.read_result_code(garbage) == ("", "")
    assert target.read_total_count(garbage) == 0
    assert target.extract_rows(garbage) == []


def test_read_result_code_falls_back_to_top_level_result():
    """head가 없어도 최상위에 RESULT가 바로 오는 오류 응답 관행을 방어한다."""
    p = {"RESULT": {"CODE": "ERROR-336", "MESSAGE": "데이터요청은 한번에 최대 1,000건을 넘을 수 없습니다."}}
    assert target.read_result_code(p) == ("ERROR-336", "데이터요청은 한번에 최대 1,000건을 넘을 수 없습니다.")


def test_extract_rows_normal():
    p = envelope([ROW_FLOOR_UTIL, ROW_REGION_RENT])
    assert target.extract_rows(p) == [ROW_FLOOR_UTIL, ROW_REGION_RENT]


# ── 3. is_quiet_zero ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("total,expected", [(0, True), (1, False), (100, False)])
def test_is_quiet_zero(total, expected):
    assert target.is_quiet_zero(total) is expected


# ── 4. floor_bucket_key ───────────────────────────────────────────────────────


@pytest.mark.parametrize("cls_nm,expected", [
    ("지하1층", "-1"), ("1층", "1"), ("2층", "2"), ("3층", "3"),
    ("4층", "4"), ("5층", "5"), ("6층이상", "6+"),
])
def test_floor_bucket_key_maps_seven_buckets(cls_nm, expected):
    assert target.floor_bucket_key(cls_nm) == expected


@pytest.mark.parametrize("bad", ["지하2층", "7층", "옥탑", "", None, "강남"])
def test_floor_bucket_key_unsupported_is_none(bad):
    assert target.floor_bucket_key(bad) is None


# ── 5. mask_secret ───────────────────────────────────────────────────────────


def test_mask_secret_hides_query_form():
    out = target.mask_secret("GET https://x?KEY=ABC123&STATBL_ID=T249023134703697")
    assert "ABC123" not in out
    assert target.SECRET_MASK in out


def test_mask_secret_hides_bare_key():
    key = "a+b/c=="
    out = target.mask_secret("키가 그냥 박힘: a+b/c==", key)
    assert "a+b/c==" not in out


def test_mask_secret_none_is_empty():
    assert target.mask_secret(None) == ""


def test_mask_secret_does_not_over_match_other_params():
    """'KEY'는 짧은 이름이라 다른 파라미터를 잘못 지우면 안 된다(STATBL_ID 등)."""
    out = target.mask_secret("STATBL_ID=T249023134703697&DTACYCLE_CD=QY")
    assert "T249023134703697" in out
    assert "QY" in out


# ── 6. fetch_page ────────────────────────────────────────────────────────────


def test_fetch_page_success_sends_expected_params():
    s = _FakeSession([_FakeResponse(200, envelope([ROW_FLOOR_UTIL]))])
    payload = target.fetch_page(s, "KEY", "T249023134703697", "202602", 1)
    assert target.extract_rows(payload) == [ROW_FLOOR_UTIL]
    p = s.calls[0]["params"]
    assert p["STATBL_ID"] == "T249023134703697"
    assert p["WRTTIME_IDTFR_ID"] == "202602"
    assert p["DTACYCLE_CD"] == "QY"
    assert p["Type"] == "json" and p["pSize"] == target.NUM_OF_ROWS


def test_fetch_page_accepts_info_000_code():
    """★ 이 API의 성공 코드는 'INFO-000'이다 — 숫자 3자리로 비교하면 전부 실패한다."""
    assert target.RESULT_CODE_OK == "INFO-000"
    s = _FakeSession([_FakeResponse(200, envelope([ROW_FLOOR_UTIL], code="INFO-000"))])
    assert target.extract_rows(target.fetch_page(s, "K", "T1", "202602", 1))


def test_fetch_page_raises_on_other_result_code():
    s = _FakeSession([_FakeResponse(200, envelope([], code="ERROR-336", msg="1,000건 초과"))])
    with pytest.raises(target.ApiError, match="CODE=ERROR-336"):
        target.fetch_page(s, "K", "T1", "202602", 1)


def test_fetch_page_retries_5xx_then_succeeds():
    s = _FakeSession([
        _FakeResponse(503, None, text="bad gateway"),
        _FakeResponse(200, envelope([ROW_FLOOR_UTIL])),
    ])
    slept = []
    payload = target.fetch_page(s, "K", "T1", "202602", 1, sleep=slept.append)
    assert target.extract_rows(payload) == [ROW_FLOOR_UTIL]
    assert len(s.calls) == 2 and slept == [2]


def test_fetch_page_masks_key_in_network_error():
    s = _FakeSession([requests.RequestException("https://x?KEY=SECRET")])
    with pytest.raises(target.ApiError) as e:
        target.fetch_page(s, "SECRET", "T1", "202602", 1, retry_count=1, sleep=lambda _s: None)
    assert "SECRET" not in str(e.value)


# ── 7. collect_one — raw 원자성 ───────────────────────────────────────────────


def test_collect_one_writes_raw_with_full_context(tmp_path):
    s = _FakeSession([_FakeResponse(200, envelope([ROW_FLOOR_UTIL]))])
    r = target.collect_one(s, "K", "집합상가", "floor_util", "202602", str(tmp_path))
    assert r["status"] == "done" and r["row_count"] == 1 and r["calls"] == 1

    path = target.raw_path(str(tmp_path), "집합상가", "floor_util")
    rows = [json.loads(x) for x in open(path, encoding="utf-8")]
    assert len(rows) == 1
    assert rows[0]["bld_type"] == "집합상가"
    assert rows[0]["metric"] == "floor_util"
    assert rows[0]["quarter_id"] == "202602"
    assert rows[0]["row"] == ROW_FLOOR_UTIL


def test_collect_one_flags_quiet_zero_but_still_writes_raw(tmp_path):
    """quiet-zero도 raw 쓰기 경로를 그대로 통과한다(조용히 건너뛰지 않는다)."""
    s = _FakeSession([_FakeResponse(200, envelope([], total_count=0))])
    r = target.collect_one(s, "K", "집합상가", "floor_util", "202403", str(tmp_path))
    assert r["status"] == "done"
    assert r["row_count"] == 0
    assert "0건" in r["error_msg"]
    path = target.raw_path(str(tmp_path), "집합상가", "floor_util")
    assert os.path.exists(path)


def test_collect_one_writes_nothing_when_it_fails(tmp_path):
    s = _FakeSession([_FakeResponse(200, envelope([], code="ERROR-500", msg="터짐"))])
    r = target.collect_one(s, "K", "집합상가", "floor_util", "202602", str(tmp_path),
                           retry_count=1, sleep=lambda _s: None)
    assert r["status"] == "failed" and r["calls"] == 1
    assert not os.path.exists(target.raw_path(str(tmp_path), "집합상가", "floor_util"))


# ── 8. parse_args ─────────────────────────────────────────────────────────────


def test_parse_args_defaults():
    o = target.parse_args([])
    assert o["bld_type"] is None and o["metric"] is None
    assert o["quarters"] == target.DEFAULT_QUARTERS
    assert o["dry_run"] is False and o["retry_failed"] is False
    assert o["raw_dir"].endswith(os.path.join("data", "raw", "rone"))
    # end_qid는 실행 시점 현재 분기로 자동 채워진다 (6자리 YYYYQQ 형식이어야 한다)
    assert len(o["end_qid"]) == 6 and o["end_qid"].isdigit()


def test_parse_args_overrides():
    o = target.parse_args(["--bld-type", "집합상가", "--metric", "floor_util",
                           "--quarters", "4", "--end-qid", "202602",
                           "--daily-budget", "100", "--limit", "3",
                           "--dry-run", "--retry-failed"])
    assert o["bld_type"] == "집합상가" and o["metric"] == "floor_util"
    assert o["quarters"] == 4 and o["end_qid"] == "202602"
    assert o["daily_budget"] == 100 and o["limit"] == 3
    assert o["dry_run"] and o["retry_failed"]


def test_parse_args_rejects_unknown_bld_type():
    with pytest.raises(ValueError, match="--bld-type"):
        target.parse_args(["--bld-type", "아파트"])


def test_parse_args_rejects_unknown_metric():
    with pytest.raises(ValueError, match="--metric"):
        target.parse_args(["--metric", "면적"])


def test_parse_args_rejects_unknown_flag_like_help():
    with pytest.raises(ValueError, match="알 수 없는 인자"):
        target.parse_args(["--help"])


def test_parse_args_rejects_typo_does_not_silently_set_dry_run():
    with pytest.raises(ValueError, match="알 수 없는 인자"):
        target.parse_args(["--dryrun"])


def test_parse_args_missing_value():
    with pytest.raises(ValueError, match="뒤에 값이 필요"):
        target.parse_args(["--quarters"])


# ── 부가: 상수 정합성 (STATBL_IDS·BLD_TYPE_SLUG가 BLD_TYPES/METRICS와 어긋나지 않게) ──


def test_statbl_ids_cover_every_bld_type_and_metric():
    for bt in target.BLD_TYPES:
        assert bt in target.STATBL_IDS, bt
        for metric in target.METRICS:
            assert metric in target.STATBL_IDS[bt], (bt, metric)


def test_bld_type_slug_covers_every_bld_type():
    for bt in target.BLD_TYPES:
        assert bt in target.BLD_TYPE_SLUG, bt


# ── budget_verdict (collect_transactions.py와 패리티 — 적대검증 지적 반영) ──


def test_budget_verdict_fits_when_budget_is_enough():
    v = target.budget_verdict(calls_used=100, planned_calls=96, budget=500)
    assert v["remaining"] == 400
    assert v["fits"] is True
    assert v["shortfall"] == 0


def test_budget_verdict_reports_shortfall_when_not_enough():
    v = target.budget_verdict(calls_used=450, planned_calls=96, budget=500)
    assert v["remaining"] == 50
    assert v["fits"] is False
    assert v["shortfall"] == 46


def test_budget_verdict_exact_fit_is_still_a_fit():
    v = target.budget_verdict(calls_used=404, planned_calls=96, budget=500)
    assert v["remaining"] == 96 and v["fits"] is True and v["shortfall"] == 0


def test_budget_verdict_never_reports_negative_remaining():
    v = target.budget_verdict(calls_used=99999, planned_calls=10, budget=500)
    assert v["remaining"] == 0 and v["fits"] is False and v["shortfall"] == 10
