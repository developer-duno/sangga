# -*- coding: utf-8 -*-
"""
scripts/collectors/collect_building_ledger.py 단위 테스트

라이브 API·Supabase 없이 검증한다 (requests는 전부 흉내낸다):
  1. pnu_to_params      — PNU 분해, 산('2'->'1') 포함·이상 대지구분 스킵
  2. extract_items      — 응답 아이템이 dict 1건 / list N건 / 0건인 세 케이스
  3. page_count         — totalCount 기반 페이지네이션 계산
  4. is_quota_exceeded  — 쿼터 초과 신호 감지
  5. append_jsonl       — raw append 모드(덮어쓰기 금지)
  6. fetch_page         — 재시도·쿼터 초과·resultCode 오류 분기
  7. collect_one_pnu    — raw 원자성(중간 실패 시 무기록)·skipped 처리
  8. 진행상태/쿼터      — 이어받기 쿼리, upsert 충돌 해소 정책, 예산 판정
  9. main()             — --dry-run(API 0콜), 예산 도달 시 안전 종료

conftest.py를 새로 만들지 않기 위해(다른 수집기 작업과 충돌 방지),
sys.path 조작은 이 파일 안에서만 한다.
"""

import json
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

import collect_building_ledger as target  # noqa: E402


# ── 픽스처 도우미 (2026-08-07 실측 응답 형태 그대로) ──────────────────────────

PNU_LAND = "1168010100108230004"      # 강남구 역삼동 823-4 (대지)
PNU_MOUNTAIN = "1168010100208230004"  # 같은 지번의 산 표기 (대지구분 '2')

TITLE_ITEM = {
    "mgmBldrgstPk": "11680-100123",
    "bldNm": "테스트빌딩",
    "dongNm": "",
    "totArea": "12345.67",
    "grndFlrCnt": "15",
    "ugrndFlrCnt": "3",
    "useAprDay": "20050317",
    "mainPurpsCd": "14000",
    "mainPurpsCdNm": "업무시설",
    "bcRat": "59.87",
    "vlRat": "789.12",
    "regstrGbCd": "2",
    "regstrGbCdNm": "집합",
    "regstrKindCd": "3",
    "regstrKindCdNm": "일반",
    "mainAtchGbCd": "0",
    "mainAtchGbCdNm": "주건축물",
    "indrAutoUtcnt": "120",
    "indrMechUtcnt": "0",
    "oudrAutoUtcnt": "5",
    "oudrMechUtcnt": "0",
    "hoCnt": "88",
}


def make_payload(items, total_count=None, result_code="00", result_msg="NORMAL SERVICE."):
    """건축HUB 응답 JSON을 흉내낸다.

    items 가 dict면 1건 응답, list면 N건 응답, None이면 0건 응답(items가 빈 문자열).
    """
    if items is None:
        body_items = ""
        count = 0
    elif isinstance(items, dict):
        body_items = {"item": items}
        count = 1
    else:
        body_items = {"item": items}
        count = len(items)
    return {
        "response": {
            "header": {"resultCode": result_code, "resultMsg": result_msg},
            "body": {
                "items": body_items,
                "numOfRows": target.NUM_OF_ROWS,
                "pageNo": 1,
                "totalCount": count if total_count is None else total_count,
            },
        }
    }


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise ValueError("JSON 아님")
        return self._payload


class FakeSession:
    """미리 정해둔 응답을 순서대로 내주는 requests.Session 대역."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params})
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


# ── 1. pnu_to_params ─────────────────────────────────────────────────────────


def test_pnu_to_params_land():
    params, reason = target.pnu_to_params(PNU_LAND)
    assert reason is None
    assert params == {
        "sigunguCd": "11680",
        "bjdongCd": "10100",
        "platGbCd": "0",   # 대지구분 '1' -> '0'
        "bun": "0823",
        "ji": "0004",
    }


def test_pnu_to_params_mountain_maps_to_1():
    params, reason = target.pnu_to_params(PNU_MOUNTAIN)
    assert reason is None
    assert params["platGbCd"] == "1"  # 산 '2' -> '1'


def test_pnu_to_params_unknown_plat_gb_is_skipped():
    # 대지구분이 '1'/'2'가 아니면 요청을 만들 수 없다 -> None + 사유
    bad = PNU_LAND[:10] + "9" + PNU_LAND[11:]
    params, reason = target.pnu_to_params(bad)
    assert params is None
    assert "대지구분" in reason


def test_pnu_to_params_wrong_length():
    params, reason = target.pnu_to_params("116801")
    assert params is None
    assert "형식 이상" in reason


def test_pnu_to_params_non_digit():
    params, reason = target.pnu_to_params("116801010010823000X")
    assert params is None
    assert "형식 이상" in reason


def test_pnu_to_params_keeps_zero_padding():
    # 본번/부번의 앞 0을 잘라내면 다른 지번이 된다 — 문자열 그대로 유지해야 한다.
    pnu = "1168010100" + "1" + "0001" + "0002"
    params, _ = target.pnu_to_params(pnu)
    assert params["bun"] == "0001"
    assert params["ji"] == "0002"


# ── 2. extract_items / read_result_code / read_total_count ───────────────────


def test_extract_items_single_dict():
    assert target.extract_items(make_payload(TITLE_ITEM)) == [TITLE_ITEM]


def test_extract_items_list():
    items = [TITLE_ITEM, dict(TITLE_ITEM, dongNm="가동")]
    assert target.extract_items(make_payload(items)) == items


def test_extract_items_zero_rows():
    assert target.extract_items(make_payload(None)) == []


def test_extract_items_items_is_none():
    payload = {"response": {"header": {}, "body": {"items": None, "totalCount": 0}}}
    assert target.extract_items(payload) == []


def test_extract_items_garbage_payload():
    assert target.extract_items(None) == []
    assert target.extract_items({"response": None}) == []


def test_read_result_code():
    assert target.read_result_code(make_payload(None)) == ("00", "NORMAL SERVICE.")
    assert target.read_result_code({}) == ("", "")


def test_read_total_count():
    assert target.read_total_count(make_payload(None, total_count=257)) == 257
    assert target.read_total_count({"response": {"body": {"totalCount": "x"}}}) == 0


# ── 3. page_count ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("total,expected", [
    (0, 1), (1, 1), (100, 1), (101, 2), (257, 3), (1000, 10),
])
def test_page_count(total, expected):
    assert target.page_count(total) == expected


def test_page_count_capped_by_max_pages():
    assert target.page_count(10_000_000) == target.MAX_PAGES


def test_page_count_rejects_zero_rows():
    with pytest.raises(ValueError):
        target.page_count(10, num_of_rows=0)


# ── 3-b. is_truncated (10,000행 페이지 상한 절단 감지) ───────────────────────


def test_is_truncated_false_within_cap():
    assert target.is_truncated(target.NUM_OF_ROWS * target.MAX_PAGES) is False
    assert target.is_truncated(0) is False
    assert target.is_truncated(100) is False


def test_is_truncated_true_over_cap():
    assert target.is_truncated(target.NUM_OF_ROWS * target.MAX_PAGES + 1) is True
    assert target.is_truncated(10_000_000) is True


# ── 4. is_quota_exceeded ─────────────────────────────────────────────────────


def test_is_quota_exceeded_matches_exact_portal_token():
    # 상수에 박아둔 토큰 문자열 그대로가 매칭돼야 한다 (변형만 검증하면 오탐을 놓친다)
    for token in target.QUOTA_EXCEEDED_TOKENS:
        assert target.is_quota_exceeded(token)


def test_is_quota_exceeded_detects_portal_message():
    assert target.is_quota_exceeded(
        "<returnAuthMsg>LIMITED NUMBER OF SERVICE REQUESTS EXCEEDS ERROR.</returnAuthMsg>")


def test_is_quota_exceeded_normalizes_case_and_separators():
    assert target.is_quota_exceeded("limited number of service requests exceeds")
    assert target.is_quota_exceeded("LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR")
    assert target.is_quota_exceeded("LIMITED-NUMBER-OF-SERVICE-REQUESTS-EXCEEDS")


def test_is_quota_exceeded_false_on_normal_body():
    assert target.is_quota_exceeded("NORMAL SERVICE.") is False
    assert target.is_quota_exceeded("") is False
    assert target.is_quota_exceeded(None) is False


def test_service_key_error_is_not_treated_as_quota():
    """키 미등록(코드 30)은 쿼터 초과(코드 22)와 갈라야 한다.

    같이 묶으면 "내일 이어받으면 된다"고 잘못 보고하게 되는데, 실제로는 활용신청
    승인·키 재발급이 필요해서 기다려도 영원히 안 풀린다.
    """
    for token in target.SERVICE_KEY_ERROR_TOKENS:
        assert target.is_service_key_error(token)
        assert target.is_quota_exceeded(token) is False
    assert "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" not in target.QUOTA_EXCEEDED_TOKENS


def test_is_service_key_error_normalizes_separators():
    assert target.is_service_key_error("SERVICE KEY IS NOT REGISTERED ERROR.")
    assert target.is_service_key_error("service_key_is_not_registered_error")
    assert target.is_service_key_error("NORMAL SERVICE.") is False


# ── 4-b. mask_secret (인증키 유출 차단) ─────────────────────────────────────

FAKE_KEY = "AbCd1234%2FfakeSERVICEkey%3D%3D"


def test_mask_secret_removes_service_key_query():
    text = ("HTTPSConnectionPool(host='apis.data.go.kr'): Max retries exceeded with url: "
            "/1613000/BldRgstHubService/getBrTitleInfo?serviceKey={}&pageNo=1".format(FAKE_KEY))
    masked = target.mask_secret(text)
    assert FAKE_KEY not in masked
    assert "serviceKey=***" in masked
    assert "pageNo=1" in masked  # 나머지 진단 정보는 살아 있어야 한다


def test_mask_secret_removes_bare_key_literal():
    masked = target.mask_secret("키 값이 그냥 박혔다: {}".format(FAKE_KEY), FAKE_KEY)
    assert FAKE_KEY not in masked
    assert target.SECRET_MASK in masked


def test_mask_secret_removes_url_encoded_key():
    raw_key = "AbCd1234/fakeKEY=="
    text = "url: ...?serviceKey%3D{}".format(target.quote(raw_key, safe=""))
    masked = target.mask_secret(text, raw_key)
    assert target.quote(raw_key, safe="") not in masked


def test_mask_secret_handles_none():
    assert target.mask_secret(None) == ""


# ── 5. append_jsonl (raw append 모드) ────────────────────────────────────────


def test_append_jsonl_appends_and_keeps_previous_lines(tmp_path):
    path = os.path.join(str(tmp_path), "sub", "title.jsonl")
    n1 = target.append_jsonl(path, PNU_LAND, [TITLE_ITEM], "2026-08-07T10:00:00+09:00")
    n2 = target.append_jsonl(path, "1168010100108230005",
                             [TITLE_ITEM, TITLE_ITEM], "2026-08-07T10:00:01+09:00")
    assert (n1, n2) == (1, 2)

    with open(path, encoding="utf-8") as fp:
        lines = [json.loads(x) for x in fp if x.strip()]
    assert len(lines) == 3  # 두 번째 호출이 첫 줄을 덮어쓰지 않았다
    assert lines[0]["pnu"] == PNU_LAND
    assert lines[0]["item"] == TITLE_ITEM
    assert lines[0]["fetched_at"] == "2026-08-07T10:00:00+09:00"
    assert lines[2]["pnu"] == "1168010100108230005"


def test_append_jsonl_writes_korean_without_escaping(tmp_path):
    path = os.path.join(str(tmp_path), "title.jsonl")
    target.append_jsonl(path, PNU_LAND, [{"bldNm": "테스트빌딩"}], "t")
    with open(path, encoding="utf-8") as fp:
        raw_line = fp.read()
    assert "테스트빌딩" in raw_line  # ensure_ascii=False


def test_append_jsonl_no_items_writes_nothing(tmp_path):
    path = os.path.join(str(tmp_path), "title.jsonl")
    assert target.append_jsonl(path, PNU_LAND, [], "t") == 0
    assert not os.path.exists(path)


def test_raw_path_uses_period_key_folder():
    raw_dir = target.default_raw_dir("202608")
    assert raw_dir.endswith(os.path.join("data", "raw", "bldrgst", "202608"))
    assert target.raw_path(raw_dir, target.ENDPOINT_TITLE).endswith("title.jsonl")
    assert target.raw_path(raw_dir, target.ENDPOINT_FLR_OULN).endswith("flr_ouln.jsonl")
    assert target.raw_path(raw_dir, target.ENDPOINT_EXPOS_AREA).endswith("expos_area.jsonl")


# ── 6. fetch_page / fetch_all_pages ─────────────────────────────────────────


def _no_sleep(_sec):
    return None


def test_fetch_page_success_sends_expected_query():
    session = FakeSession([FakeResponse(200, make_payload(TITLE_ITEM))])
    payload = target.fetch_page(session, "KEY", target.ENDPOINT_TITLE,
                                {"sigunguCd": "11680"}, 1, sleep=_no_sleep)
    assert target.extract_items(payload) == [TITLE_ITEM]
    params = session.calls[0]["params"]
    assert params["numOfRows"] == target.NUM_OF_ROWS
    assert params["pageNo"] == 1
    assert params["_type"] == "json"
    assert params["serviceKey"] == "KEY"


def test_fetch_page_retries_on_5xx_then_succeeds():
    session = FakeSession([
        FakeResponse(503, text="upstream error"),
        FakeResponse(200, make_payload(TITLE_ITEM)),
    ])
    payload = target.fetch_page(session, "KEY", target.ENDPOINT_TITLE, {}, 1, sleep=_no_sleep)
    assert target.extract_items(payload) == [TITLE_ITEM]
    assert len(session.calls) == 2


def test_fetch_page_retries_on_network_error_then_gives_up():
    err = target.requests.exceptions.ConnectionError("연결 끊김")
    session = FakeSession([err, err, err])
    with pytest.raises(target.ApiError, match="재시도"):
        target.fetch_page(session, "KEY", target.ENDPOINT_TITLE, {}, 1, sleep=_no_sleep)
    assert len(session.calls) == target.RETRY_COUNT  # 최초 1 + 재시도 2


def test_fetch_page_network_error_message_hides_service_key():
    """requests 예외 문자열에는 요청 URL(=serviceKey)이 통째로 들어 있다.

    이 문자열이 마스킹 없이 ApiError로 흘러가면 그대로 collect_progress.error_msg에
    평문 저장된다(수정 1 회귀 테스트).
    """
    leaky = target.requests.exceptions.ConnectionError(
        "HTTPSConnectionPool(host='apis.data.go.kr', port=443): Max retries exceeded "
        "with url: /1613000/BldRgstHubService/getBrTitleInfo?serviceKey={}&pageNo=1 "
        "(Caused by NewConnectionError)".format(FAKE_KEY))
    session = FakeSession([leaky, leaky, leaky])

    with pytest.raises(target.ApiError) as exc_info:
        target.fetch_page(session, FAKE_KEY, target.ENDPOINT_TITLE, {}, 1, sleep=_no_sleep)

    message = str(exc_info.value)
    assert FAKE_KEY not in message
    assert "serviceKey=***" in message
    assert "Max retries exceeded" in message  # 진단에 필요한 부분은 남는다


def test_collect_one_pnu_error_msg_never_contains_service_key(tmp_path):
    """DB(collect_progress.error_msg)에 저장되는 문자열에 키가 남으면 안 된다."""
    leaky = target.requests.exceptions.ConnectionError(
        "url: /getBrTitleInfo?serviceKey={}&pageNo=1".format(FAKE_KEY))
    session = FakeSession([leaky] * (target.RETRY_COUNT + 3))

    result = target.collect_one_pnu(session, FAKE_KEY, PNU_LAND, str(tmp_path),
                                    sleep=_no_sleep)

    assert result["status"] == "failed"
    assert FAKE_KEY not in result["error_msg"]
    assert "***" in result["error_msg"]

    row = target.build_progress_row(PNU_LAND, "202608", result, attempts=0)
    assert FAKE_KEY not in (row["error_msg"] or "")


def test_fetch_page_service_key_error_raises_dedicated_exception():
    """키 미등록은 QuotaExceededError가 아니라 ServiceKeyError로 갈라져야 한다."""
    session = FakeSession([
        FakeResponse(200, text="<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"),
    ])
    with pytest.raises(target.ServiceKeyError):
        target.fetch_page(session, "KEY", target.ENDPOINT_TITLE, {}, 1, sleep=_no_sleep)
    assert len(session.calls) == 1  # 재시도하지 않는다


def test_fetch_page_service_key_error_in_result_msg():
    session = FakeSession([
        FakeResponse(200, make_payload(
            None, result_code="30", result_msg="SERVICE KEY IS NOT REGISTERED ERROR.")),
    ])
    with pytest.raises(target.ServiceKeyError):
        target.fetch_page(session, "KEY", target.ENDPOINT_TITLE, {}, 1, sleep=_no_sleep)


def test_collect_one_pnu_propagates_service_key_error(tmp_path, monkeypatch):
    def key_error(*a, **kw):
        raise target.ServiceKeyError("키 미등록")

    monkeypatch.setattr(target, "fetch_all_pages", key_error)
    with pytest.raises(target.ServiceKeyError):
        target.collect_one_pnu(None, "KEY", PNU_LAND, str(tmp_path))


def test_fetch_page_quota_exceeded_raises_immediately():
    session = FakeSession([
        FakeResponse(200, text="<cmmMsgHeader>LIMITED NUMBER OF SERVICE REQUESTS EXCEEDS</cmmMsgHeader>"),
        FakeResponse(200, make_payload(TITLE_ITEM)),
    ])
    with pytest.raises(target.QuotaExceededError):
        target.fetch_page(session, "KEY", target.ENDPOINT_TITLE, {}, 1, sleep=_no_sleep)
    assert len(session.calls) == 1  # 재시도하지 않는다


def test_fetch_page_bad_result_code_raises_api_error():
    # 쿼터·키 문제가 아닌 그 밖의 오류코드는 일반 ApiError로 떨어진다.
    session = FakeSession([
        FakeResponse(200, make_payload(None, result_code="99", result_msg="UNKNOWN ERROR")),
    ])
    with pytest.raises(target.ApiError, match="resultCode=99"):
        target.fetch_page(session, "KEY", target.ENDPOINT_TITLE, {}, 1, sleep=_no_sleep)


def test_fetch_all_pages_walks_every_page():
    page1 = make_payload([TITLE_ITEM] * 100, total_count=257)
    page2 = make_payload([TITLE_ITEM] * 100, total_count=257)
    page3 = make_payload([TITLE_ITEM] * 57, total_count=257)
    session = FakeSession([FakeResponse(200, p) for p in (page1, page2, page3)])

    items, calls, truncated = target.fetch_all_pages(session, "KEY", target.ENDPOINT_TITLE, {},
                                                      sleep=_no_sleep)
    assert len(items) == 257
    assert calls == 3
    assert truncated is False
    assert [c["params"]["pageNo"] for c in session.calls] == [1, 2, 3]


def test_fetch_all_pages_single_page_when_zero_rows():
    session = FakeSession([FakeResponse(200, make_payload(None))])
    items, calls, truncated = target.fetch_all_pages(session, "KEY", target.ENDPOINT_TITLE, {},
                                                      sleep=_no_sleep)
    assert items == []
    assert calls == 1
    assert truncated is False


def test_fetch_all_pages_flags_truncation_when_over_page_cap():
    """전유공용면적이 10,000행(NUM_OF_ROWS x MAX_PAGES) 상한에 걸리면 절단로 표시된다.

    실측 확정: `1168010300100120000` 등 4개 PNU가 이 상한에 실제로 걸렸다.
    """
    total = target.NUM_OF_ROWS * target.MAX_PAGES + 1  # 상한을 1건 넘김
    pages = [make_payload([TITLE_ITEM] * target.NUM_OF_ROWS, total_count=total)
             for _ in range(target.MAX_PAGES)]
    session = FakeSession([FakeResponse(200, p) for p in pages])

    items, calls, truncated = target.fetch_all_pages(
        session, "KEY", target.ENDPOINT_EXPOS_AREA, {}, sleep=_no_sleep)

    assert calls == target.MAX_PAGES
    assert truncated is True


# ── 7. collect_one_pnu (raw 원자성) ──────────────────────────────────────────


def test_collect_one_pnu_writes_three_raw_files(tmp_path, monkeypatch):
    monkeypatch.setattr(
        target, "fetch_all_pages",
        lambda session, key, endpoint, params, **kw: ([{"endpoint": endpoint}], 1, False),
    )
    result = target.collect_one_pnu(None, "KEY", PNU_LAND, str(tmp_path))

    assert result["status"] == "done"
    assert result["row_count"] == 3           # 엔드포인트 3종 x 1아이템
    assert result["error_msg"] is None
    assert sum(result["calls"].values()) == 3
    for endpoint in target.ENDPOINTS:
        with open(target.raw_path(str(tmp_path), endpoint), encoding="utf-8") as fp:
            line = json.loads(fp.readline())
        assert line["pnu"] == PNU_LAND
        assert line["item"] == {"endpoint": endpoint}


def test_collect_one_pnu_records_truncation_in_error_msg(tmp_path, monkeypatch):
    """절단된 엔드포인트가 있으면 status는 'done'이지만 error_msg에 흔적이 남는다.

    수정 C — 재수집 대상을 collect_progress.error_msg로 특정할 수 있게 한다.
    """
    def truncated_expos(session, key, endpoint, params, **kw):
        return ([{"endpoint": endpoint}], 1, endpoint == target.ENDPOINT_EXPOS_AREA)

    monkeypatch.setattr(target, "fetch_all_pages", truncated_expos)
    result = target.collect_one_pnu(None, "KEY", PNU_LAND, str(tmp_path))

    assert result["status"] == "done"
    assert "truncated" in result["error_msg"]
    assert target.ENDPOINT_EXPOS_AREA in result["error_msg"]


def test_collect_one_pnu_writes_nothing_when_later_endpoint_fails(tmp_path, monkeypatch):
    """표제부는 성공하고 층별개요에서 실패하면 raw에 한 줄도 안 남아야 한다.

    부분 기록을 허용하면 재실행 시 같은 PNU 표제부가 두 번 쌓여 면적·건수가 부풀어 오른다.
    """
    def flaky(session, key, endpoint, params, **kw):
        if endpoint == target.ENDPOINT_FLR_OULN:
            raise target.ApiError("층별개요 실패")
        return ([{"endpoint": endpoint}], 1, False)

    monkeypatch.setattr(target, "fetch_all_pages", flaky)
    result = target.collect_one_pnu(None, "KEY", PNU_LAND, str(tmp_path))

    assert result["status"] == "failed"
    assert result["row_count"] == 0
    assert "층별개요 실패" in result["error_msg"]
    for endpoint in target.ENDPOINTS:
        assert not os.path.exists(target.raw_path(str(tmp_path), endpoint))


def test_collect_one_pnu_skips_unsupported_plat_gb(tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("스킵 대상은 API를 호출하면 안 된다")

    monkeypatch.setattr(target, "fetch_all_pages", boom)
    bad = PNU_LAND[:10] + "9" + PNU_LAND[11:]
    result = target.collect_one_pnu(None, "KEY", bad, str(tmp_path))

    assert result["status"] == "skipped"
    assert sum(result["calls"].values()) == 0


def test_collect_one_pnu_propagates_quota_error(tmp_path, monkeypatch):
    def quota(*a, **kw):
        raise target.QuotaExceededError("쿼터 초과")

    monkeypatch.setattr(target, "fetch_all_pages", quota)
    with pytest.raises(target.QuotaExceededError):
        target.collect_one_pnu(None, "KEY", PNU_LAND, str(tmp_path))


# ── 8. 이어받기 · 쿼터 · upsert 정책 ────────────────────────────────────────


class _FakeRestResponse:
    def __init__(self, status_code=200, payload=None, text="ok", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._payload


def test_seed_progress_uses_ignore_duplicates(monkeypatch):
    """시드는 ignore-duplicates — 재실행해도 done이 pending으로 되돌아가면 안 된다."""
    seen = []

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.append({"url": url, "json": json, "headers": headers})
        return _FakeRestResponse(201)

    monkeypatch.setattr(target.requests, "post", fake_post)
    sent = target.seed_progress("https://x.supabase.co", {"apikey": "k"},
                                [PNU_LAND, PNU_MOUNTAIN], "202608")

    assert sent == 2
    assert seen[0]["headers"]["Prefer"] == "resolution=ignore-duplicates,return=minimal"
    assert seen[0]["url"].endswith("/rest/v1/collect_progress")
    assert seen[0]["json"][0] == {
        "collector": "bldrgst", "scope_key": PNU_LAND,
        "period_key": "202608", "status": "pending",
    }


def test_save_progress_uses_merge_duplicates(monkeypatch):
    seen = []
    monkeypatch.setattr(
        target.requests, "post",
        lambda url, json=None, headers=None, timeout=None: (
            seen.append(headers) or _FakeRestResponse(201)),
    )
    target.save_progress("https://x.supabase.co", {"apikey": "k"}, {"scope_key": PNU_LAND})
    assert seen[0]["Prefer"] == "resolution=merge-duplicates,return=minimal"


def test_upsert_batch_rejects_unknown_resolution():
    with pytest.raises(ValueError, match="충돌 해소 정책"):
        target.upsert_batch("https://x.supabase.co", {}, "collect_progress", [{}], "그냥덮어쓰기")


def test_retry_failed_patches_with_expected_filter(monkeypatch):
    """failed -> pending 되돌리기는 collector·period_key·status·attempts 조건이 모두 걸려야 한다."""
    seen = {}

    def fake_patch(url, json=None, headers=None, timeout=None):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        return _FakeRestResponse(200, payload=[{"scope_key": PNU_LAND}, {"scope_key": PNU_MOUNTAIN}])

    monkeypatch.setattr(target.requests, "patch", fake_patch)
    reverted = target.retry_failed("https://x.supabase.co", {"apikey": "k"}, "202608")

    assert reverted == 2
    assert "collector=eq.bldrgst" in seen["url"]
    assert "period_key=eq.202608" in seen["url"]
    assert "status=eq.failed" in seen["url"]
    assert "attempts=lt.{}".format(target.RETRY_FAILED_MAX_ATTEMPTS) in seen["url"]
    assert seen["json"] == {"status": "pending"}


def test_retry_failed_raises_on_bad_status(monkeypatch):
    monkeypatch.setattr(
        target.requests, "patch",
        lambda url, json=None, headers=None, timeout=None: _FakeRestResponse(500, text="boom"),
    )
    with pytest.raises(RuntimeError, match="되돌리기 실패"):
        target.retry_failed("https://x.supabase.co", {}, "202608")


def test_fetch_pending_queries_only_pending_rows(monkeypatch):
    """이어받기: done/failed 행은 아예 조회 대상이 아니다 (status=eq.pending)."""
    captured = {}

    def fake_select(base_url, headers, table, query, page_size=None):
        captured["table"] = table
        captured["query"] = query
        return [{"scope_key": PNU_LAND, "attempts": 2}, {"scope_key": PNU_MOUNTAIN, "attempts": None}]

    monkeypatch.setattr(target, "rest_select", fake_select)
    pending = target.fetch_pending("https://x.supabase.co", {}, "202608")

    assert captured["table"] == "collect_progress"
    assert "status=eq.pending" in captured["query"]
    assert "collector=eq.bldrgst" in captured["query"]
    assert "period_key=eq.202608" in captured["query"]
    assert pending == [(PNU_LAND, 2), (PNU_MOUNTAIN, 0)]


def test_build_progress_row_increments_attempts():
    result = {"status": "failed", "row_count": 0, "error_msg": "타임아웃"}
    row = target.build_progress_row(PNU_LAND, "202608", result, attempts=2)
    assert row["attempts"] == 3
    assert row["status"] == "failed"
    assert row["scope_key"] == PNU_LAND
    assert row["updated_at"].endswith("+09:00")  # KST 고정


def test_rest_select_paginates_until_short_page(monkeypatch):
    pages = [
        [{"pnu": str(i)} for i in range(target.SELECT_PAGE_SIZE)],
        [{"pnu": "last"}],
    ]
    urls = []

    def fake_get(url, headers=None, timeout=None):
        urls.append(url)
        return _FakeRestResponse(200, payload=pages[len(urls) - 1])

    monkeypatch.setattr(target.requests, "get", fake_get)
    rows = target.rest_select("https://x.supabase.co", {}, "parcel", "select=pnu")

    assert len(rows) == target.SELECT_PAGE_SIZE + 1
    assert "offset=0" in urls[0]
    assert "offset={}".format(target.SELECT_PAGE_SIZE) in urls[1]


def test_flush_quota_log_adds_baseline(monkeypatch):
    seen = []
    monkeypatch.setattr(
        target.requests, "post",
        lambda url, json=None, headers=None, timeout=None: (
            seen.append(json) or _FakeRestResponse(201)),
    )
    target.flush_quota_log(
        "https://x.supabase.co", {}, "2026-08-07",
        {target.ENDPOINT_TITLE: 100},
        {target.ENDPOINT_TITLE: 5, target.ENDPOINT_FLR_OULN: 5, target.ENDPOINT_EXPOS_AREA: 0},
    )
    rows = {r["api_name"]: r["call_count"] for r in seen[0]}
    assert rows[target.ENDPOINT_TITLE] == 105       # baseline 100 + 이번 5
    assert rows[target.ENDPOINT_FLR_OULN] == 5      # baseline 없음
    assert target.ENDPOINT_EXPOS_AREA not in rows   # 0건은 안 쓴다


def test_budget_verdict_fits_and_exceeds():
    planned = target.Counter({e: 1000 for e in target.ENDPOINTS})
    fits = target.budget_verdict(
        calls_used=target.Counter(), planned_calls=planned, budget_per_endpoint=9_500)
    assert fits["fits"] is True
    assert fits["remaining"][target.ENDPOINT_TITLE] == 9_500

    used = target.Counter({e: 9_000 for e in target.ENDPOINTS})
    over = target.budget_verdict(calls_used=used, planned_calls=planned, budget_per_endpoint=9_500)
    assert over["fits"] is False
    assert over["processable_pnu"] == 500


def test_budget_verdict_any_endpoint_over_marks_whole_thing_as_not_fitting():
    """엔드포인트 3종 중 하나만 예산을 넘어도 그 PNU를 더 처리할 수 없다."""
    planned = target.Counter({e: 100 for e in target.ENDPOINTS})
    used = target.Counter({target.ENDPOINT_EXPOS_AREA: 9_450})
    verdict = target.budget_verdict(calls_used=used, planned_calls=planned, budget_per_endpoint=9_500)
    assert verdict["fits"] is False   # 전유공용면적 잔여 50 < 예상 100


def test_estimate_calls():
    result = target.estimate_calls(12_274)  # 강남구 실측 PNU 규모
    assert result[target.ENDPOINT_TITLE] == 12_274
    assert result[target.ENDPOINT_FLR_OULN] == 12_274
    assert result[target.ENDPOINT_EXPOS_AREA] == int(12_274 * target.EXPOS_CALLS_MULTIPLIER)


# ── 9. parse_args ────────────────────────────────────────────────────────────


def test_parse_args_defaults():
    opts = target.parse_args([])
    assert opts["sigungu_code"] == "11680"
    assert opts["period_key"] == "202608"
    assert opts["daily_budget_per_endpoint"] == target.DEFAULT_DAILY_BUDGET_PER_ENDPOINT
    assert opts["limit"] is None
    assert opts["dry_run"] is False
    assert opts["retry_failed"] is False


def test_parse_args_overrides():
    opts = target.parse_args(
        ["--sigungu-code", "11440", "--period-key", "202609",
         "--daily-budget-per-endpoint", "1000", "--limit", "5", "--dry-run", "--retry-failed"])
    assert opts["sigungu_code"] == "11440"
    assert opts["period_key"] == "202609"
    assert opts["daily_budget_per_endpoint"] == 1000
    assert opts["limit"] == 5
    assert opts["dry_run"] is True
    assert opts["retry_failed"] is True


def test_parse_args_rejects_non_positive_limit():
    with pytest.raises(ValueError):
        target.parse_args(["--limit", "0"])


def test_parse_args_rejects_non_numeric_budget():
    with pytest.raises(ValueError):
        target.parse_args(["--daily-budget-per-endpoint", "많이"])


def test_parse_args_missing_value():
    with pytest.raises(ValueError, match="뒤에 값이 필요"):
        target.parse_args(["--limit"])


# ── 10. main() 통합 (API·DB 전부 흉내) ──────────────────────────────────────


def _stub_db(monkeypatch, pnus, pending=None, status_counts=None, baseline=None):
    monkeypatch.setattr(target, "get_supabase_config", lambda: ("https://x.supabase.co", "k"))
    monkeypatch.setattr(target, "get_api_key", lambda: "APIKEY")
    monkeypatch.setattr(target, "fetch_target_pnus", lambda *a, **kw: pnus)
    monkeypatch.setattr(
        target, "progress_status_counts",
        lambda *a, **kw: status_counts or {"pending": len(pnus), "done": 0,
                                           "failed": 0, "skipped": 0},
    )
    monkeypatch.setattr(target, "read_quota_baseline", lambda *a, **kw: baseline or {})
    monkeypatch.setattr(target, "seed_progress", lambda *a, **kw: len(pnus))
    monkeypatch.setattr(
        target, "fetch_pending",
        lambda *a, **kw: pending if pending is not None else [(p, 0) for p in pnus],
    )
    monkeypatch.setattr(target, "save_progress", lambda *a, **kw: 1)
    monkeypatch.setattr(target, "flush_quota_log", lambda *a, **kw: 0)


def test_main_retry_failed_flag_calls_retry_before_seeding(monkeypatch, capsys):
    _stub_db(monkeypatch, [PNU_LAND])
    monkeypatch.setattr(target, "collect_one_pnu",
                        lambda *a, **kw: {"status": "done", "row_count": 0,
                                          "error_msg": None, "calls": target.Counter()})
    calls = []
    monkeypatch.setattr(target, "retry_failed", lambda *a, **kw: (calls.append("retried") or 3))
    monkeypatch.setattr(sys, "argv", ["prog", "--retry-failed"])

    assert target.main() == 0
    assert calls == ["retried"]
    assert "되돌림: 3건" in capsys.readouterr().out


def test_main_without_retry_failed_flag_does_not_call_retry(monkeypatch):
    _stub_db(monkeypatch, [PNU_LAND])
    monkeypatch.setattr(target, "collect_one_pnu",
                        lambda *a, **kw: {"status": "done", "row_count": 0,
                                          "error_msg": None, "calls": target.Counter()})

    def boom(*a, **kw):
        raise AssertionError("--retry-failed 없이는 호출되면 안 된다")

    monkeypatch.setattr(target, "retry_failed", boom)
    monkeypatch.setattr(sys, "argv", ["prog"])

    assert target.main() == 0


def test_main_dry_run_makes_no_api_call(monkeypatch, capsys):
    _stub_db(monkeypatch, [PNU_LAND, PNU_MOUNTAIN])

    def boom(*a, **kw):
        raise AssertionError("--dry-run 은 API를 호출하면 안 된다")

    monkeypatch.setattr(target, "collect_one_pnu", boom)
    monkeypatch.setattr(target, "get_api_key", boom)
    monkeypatch.setattr(sys, "argv", ["prog", "--dry-run"])

    assert target.main() == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "예상 호출 수" in out


def test_main_stops_when_daily_budget_reached(monkeypatch, capsys):
    """엔드포인트별 예산이 PNU 2개분(엔드포인트당 2콜)이면 3번째 PNU는 손도 대지
    않고 안전 종료해야 한다."""
    pnus = [PNU_LAND, "1168010100108230005", "1168010100108230006", "1168010100108230007"]
    _stub_db(monkeypatch, pnus)

    processed = []

    def fake_collect(session, key, pnu, raw_dir, **kw):
        processed.append(pnu)
        return {
            "status": "done", "row_count": 3, "error_msg": None,
            "calls": target.Counter({e: 1 for e in target.ENDPOINTS}),
        }

    monkeypatch.setattr(target, "collect_one_pnu", fake_collect)
    monkeypatch.setattr(sys, "argv", ["prog", "--daily-budget-per-endpoint", "2"])

    assert target.main() == 0
    assert processed == pnus[:2]  # 엔드포인트당 2콜 = PNU 2개분에서 정확히 멈춘다
    assert "일 예산 도달" in capsys.readouterr().out


def test_main_stops_safely_on_quota_exceeded(monkeypatch, capsys):
    pnus = [PNU_LAND, "1168010100108230005"]
    _stub_db(monkeypatch, pnus)

    def quota(*a, **kw):
        raise target.QuotaExceededError("포털 한도 초과")

    monkeypatch.setattr(target, "collect_one_pnu", quota)
    monkeypatch.setattr(sys, "argv", ["prog"])

    assert target.main() == 0  # 오늘치를 다 쓴 것뿐 — 정상 종료
    out = capsys.readouterr().out
    assert "일 트래픽 초과" in out
    assert "내일 다시 실행하면 이어받는다" in out
    assert "활용신청" not in out  # 키 문제와 섞어 보고하지 않는다


def test_main_service_key_error_reports_distinct_reason(monkeypatch, capsys):
    """키 미등록은 쿼터 소진과 다른 사유·다른 종료코드로 보고돼야 한다(수정 2)."""
    pnus = [PNU_LAND, "1168010100108230005"]
    _stub_db(monkeypatch, pnus)

    def key_error(*a, **kw):
        raise target.ServiceKeyError("서비스키 미등록")

    monkeypatch.setattr(target, "collect_one_pnu", key_error)
    monkeypatch.setattr(sys, "argv", ["prog"])

    assert target.main() == 1  # 사람이 조치해야 하므로 실패로 끝낸다
    out = capsys.readouterr().out
    assert "활용신청" in out
    assert "BLDRGST_KEY" in out
    assert "내일 다시 실행하면 이어받는다" not in out


def test_main_service_key_error_does_not_leak_key(monkeypatch, capsys):
    _stub_db(monkeypatch, [PNU_LAND])
    monkeypatch.setattr(target, "get_api_key", lambda: FAKE_KEY)

    def key_error(*a, **kw):
        raise target.ServiceKeyError("url ...?serviceKey={}".format(FAKE_KEY))

    monkeypatch.setattr(target, "collect_one_pnu", key_error)
    monkeypatch.setattr(sys, "argv", ["prog"])

    target.main()
    assert FAKE_KEY not in capsys.readouterr().out


def test_main_limit_caps_processed_pnus(monkeypatch):
    pnus = ["11680101001082300{:02d}".format(i) for i in range(10)]
    _stub_db(monkeypatch, pnus)
    processed = []
    monkeypatch.setattr(
        target, "collect_one_pnu",
        lambda session, key, pnu, raw_dir, **kw: (
            processed.append(pnu) or {"status": "done", "row_count": 0,
                                      "error_msg": None, "calls": target.Counter()}),
    )
    monkeypatch.setattr(sys, "argv", ["prog", "--limit", "3"])

    assert target.main() == 0
    assert len(processed) == 3


def test_main_returns_1_when_no_target_pnu(monkeypatch):
    _stub_db(monkeypatch, [])
    monkeypatch.setattr(sys, "argv", ["prog", "--dry-run"])
    assert target.main() == 1


def test_main_returns_2_on_bad_args(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog", "--limit", "-1"])
    assert target.main() == 2
