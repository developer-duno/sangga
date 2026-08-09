# -*- coding: utf-8 -*-
"""
한국부동산원 R-ONE 임대동향조사 API → raw JSONL 수집

`docs/상세계획.md` §1.2(R-ONE API 스펙 박스)·§6.1(층별효용비율 제약)·§5.6과
`scripts/collectors/collect_transactions.py`의 이어받기·안전종료·raw 원자성
구조를 답습한다. 새로 발명한 패턴은 없다.

무엇을 하나:
  1. (건물유형, 지표, 분기) 조합을 collect_progress에 시드한다.
     scope_key='{건물유형}:{지표}' / period_key='{분기 YYYYQQ}' — 4개 건물유형 x
     6개 지표 = 24개 scope, 분기 수만큼 period.
  2. 조합 하나마다 SttsApiTblData.do를 호출해 row 원본을 그대로 raw JSONL에
     append 한다 (CLAUDE.md 수집 규칙: raw는 절대 덮어쓰지 않는다).
     지역 매칭·층 버킷 해석·rent_stat 병합은 전부 다음 단계 load_rone.py 소관 —
     이 스크립트는 아무것도 해석하지 않는다.
  3. api_quota_log로 일 예산을 추적하고, 예산 도달·중단 요청·쿼터 초과 어느
     쪽이든 현재 조합을 마무리한 뒤 진행 상태를 저장하고 안전 종료한다.

⚠️ collect_transactions.py(국토부)와 다른 점 — 복사할 때 반드시 확인:
  - **응답 봉투가 리스트 기반이다.** `{"SttsApiTblData": [{"head":[...]}, {"row":[...]}]}`
    형태라 MOLIT의 `response.header/body` 구조를 그대로 못 쓴다 — 새 파서
    (read_result_code/read_total_count/extract_rows)를 이 파일에 새로 둔다.
  - **성공 코드가 'INFO-000'이다** (숫자 3자리가 아니다).
  - **인증키 파라미터 이름이 'KEY'다** (serviceKey가 아니다) — mask_secret도
    이 파일 전용으로 다시 둔다.
  - **조회 단위가 (건물유형, 지표, 분기) 3축**이다. scope_key에 유형과 지표를
    함께 넣어 4x6=24개로 쪼갠다.
  - **분기 시점 형식이 'YYYYQQ'다**(월이 아니라 분기). `20243`·`2024Q3`처럼
    사람이 손으로 잘못 적은 형식은 에러 없이 조용히 0건으로 온다(§1.2 실측
    확정) — 그래서 WRTTIME_IDTFR_ID는 항상 quarter_id()가 코드로 만들고,
    사람이 문자열을 직접 입력하지 않는다(형식 오류 원천 차단).
  - **pSize 상한 1,000**은 MOLIT의 numOfRows 관행과 같지만, R-ONE은 초과 시
    'ERROR-336'을 明시적으로 준다(§1.2 실측). 우리는 애초에 1,000을 넘기지
    않으므로 걸릴 일이 없다.

사용법:
  python scripts/collectors/collect_rone.py --dry-run
  python scripts/collectors/collect_rone.py --bld-type 집합상가 --metric floor_util --quarters 1
  python scripts/collectors/collect_rone.py                      # 파일럿: 4유형x6지표x12분기
  python scripts/collectors/collect_rone.py --retry-failed
"""

import json
import os
import re
import signal
import sys
import time
from collections import Counter
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

from collect_transactions import is_truncated as _is_truncated_base
from collect_transactions import page_count as _page_count_base

# ── 설정 ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 부동산원 R-ONE 임대동향조사 (포털 ID 15134761, 별도 R-ONE 발급).
# `docs/상세계획.md` §1.2 라이브 실호출로 확정 — 다시 조사하지 말 것.
API_BASE_URL = "https://www.reb.or.kr/r-one/openapi"
ENDPOINT = "SttsApiTblData.do"
DTACYCLE_CD = "QY"   # 우리가 쓰는 4개 표는 전부 분기(QY) 주기다(§1.2 표).

COLLECTOR = "rone_rent"
RAW_SUBDIR = "rone"

BLD_TYPES = ("오피스", "중대형상가", "소규모상가", "집합상가")   # rent_stat.bld_type 리터럴 그대로(공백 없음)
BLD_TYPE_SLUG = {"오피스": "office", "중대형상가": "mid", "소규모상가": "small", "집합상가": "jiphap"}  # raw 폴더명(한글 경로 이식성 회피)

# "2024년3분기~" 시리즈만 쓴다(§1.2 조사 범위가 이미 이 시리즈로 한정됨) —
# STATBL_ID는 통계표 목록 API로만 찾을 수 있어 하드코딩한다(§1.2 실측 확정값).
STATBL_IDS = {
    "집합상가":   {"floor_util": "T249023134703697", "region_rent": "T244913134948657",
                  "vacancy": "T243283134931290", "rent_price_index": "T242433134965708",
                  "yield": "T246393134978815", "conversion": "T243133134985812"},
    "중대형상가": {"floor_util": "T241873134863890", "region_rent": "T244363134858603",
                  "vacancy": "T249633134845544", "rent_price_index": "T249863134832916",
                  "yield": "T242083134887473", "conversion": "T241883134877452"},
    "소규모상가": {"floor_util": "T246233134891629", "region_rent": "T248223134698125",
                  "vacancy": "T241833134686576", "rent_price_index": "T241273134677393",
                  "yield": "T246253134913401", "conversion": "T246253134905233"},
    "오피스":     {"floor_util": "TT242293134242089", "region_rent": "TT249843134237374",
                  "vacancy": "TT244763134428698", "rent_price_index": "TT244233134228593",
                  "yield": "T245883135037859", "conversion": "TT243613134435838"},
}
METRICS = ("floor_util", "region_rent", "vacancy", "rent_price_index", "yield", "conversion")

# 이 STATBL_ID 시리즈가 실제로 시작하는 분기. ⚠️ 그 이전 분기는 quiet-zero가
# 아니라 'CODE=INFO-200 해당하는 데이터가 없습니다' 에러로 온다(2026-08-09 본
# 수집 288조합 실측) — 장부에 failed로 남지만 원천 무데이터라 재시도 무의미.
# 예외: rent_price_index만 2024Q2부터 존재(지수는 전분기 대비라 한 분기 이름).
SERIES_START_QID = "202403"
# 파일럿 기본값: 2024Q3~현재(2026-08 기준 9분기)를 넉넉히 덮는 고정 상수.
# 시리즈 시작 이전 분기까지 몇 개 더 물어도 INFO-200 failed 기록만 남고 해가
# 없다 (collect_transactions.py의 DEFAULT_MONTHS=240처럼 고정 파일럿 상수 —
# 매번 동적으로 재계산하지 않는다).
DEFAULT_QUARTERS = 12

# 공식 가이드에 일일 호출 한도가 명시돼 있지 않다(§1.2 — WebFetch로 부재 확인).
# 남의 것을 베끼지 않고 우리 실제 필요량으로 역산: 24 scope x 분기당 최대
# 4페이지 ≈ 이번 분기 한 번 갱신에 40~90콜, 2024Q3~현재 8~9개 분기 백필까지
# 합쳐도 대략 400~600콜 선. 500이면 대부분 하루 안에 끝나고, 모자라면
# 이어받기가 이미 있어 다음날 자동 재개된다. 실제 쿼터 초과가 관측되면 이
# 상수와 아래 QUOTA_EXCEEDED_TOKENS를 함께 재조정할 것(열린 질문).
DEFAULT_DAILY_BUDGET = 500

# pSize 상한이 1,000이다(§1.2 실측, 초과 시 ERROR-336). 지금까지 관측된 가장
# 큰 표가 3,514건(4페이지)이라 10이면 넉넉하다.
NUM_OF_ROWS = 1000
MAX_PAGES = 10

API_TIMEOUT_SEC = 30
REST_TIMEOUT_SEC = 120

RETRY_COUNT = 3
RETRY_BACKOFF_BASE_SEC = 2

# 성공 코드가 'INFO-000'이다 (MOLIT '000'과 다르다 — §1.2 실측).
RESULT_CODE_OK = "INFO-000"

# 쿼터·서비스키 오류의 정확한 문구를 아직 한 번도 실측하지 못했다(15회 호출
# 무사고). 억지로 추측한 토큰을 넣지 않는다 — 실제로 걸릴 때 그 문구를 보고
# 채운다. TODO: 쿼터 초과 또는 키 오류를 실측하면 아래 두 튜플을 채울 것.
QUOTA_EXCEEDED_TOKENS = ()
SERVICE_KEY_ERROR_TOKENS = ()

_SIGNAL_STRIP_RE = re.compile(r"[^A-Z0-9]+")
# R-ONE의 인증키 파라미터는 'KEY'다(serviceKey가 아니다) — 쿼리 파라미터
# 위치([?&]로 시작)에서만 매칭해 다른 파라미터명 안의 우연한 부분일치를 피한다.
_SERVICE_KEY_QUERY_RE = re.compile(r"([?&]KEY=)[^&\s'\"]+", re.IGNORECASE)
SECRET_MASK = "***"

KST = ZoneInfo("Asia/Seoul")

BATCH_SIZE = 1000
SELECT_PAGE_SIZE = 1000

_STOP_REQUESTED = {"value": False}


class QuotaExceededError(Exception):
    """포털 일 한도 초과 — 내일 이어받기가 답이다."""


class ServiceKeyError(Exception):
    """서비스키 미등록·미승인 — 내일 다시 돌려도 똑같이 실패한다."""


class ApiError(Exception):
    """그 외 API 오류."""


# ── 순수 로직 (네트워크·DB 없음 — 테스트 대상) ─────────────────────────────────


def quarter_id(year, q):
    """(year, 분기)를 'YYYYQQ' 문자열로 만든다. 예: quarter_id(2026, 2) -> '202602'."""
    if q not in (1, 2, 3, 4):
        raise ValueError("분기는 1~4여야 합니다: {!r}".format(q))
    return "{:04d}{:02d}".format(int(year), int(q))


def quarter_range(end_qid, count):
    """end_qid에서 과거로 count개 분기 'YYYYQQ' 목록을 옛날→최근 순으로 만든다.

    month_range()와 같은 결 — 옛날부터 채우면 이어받기가 연속 구간으로 남는다.
    """
    if count <= 0:
        raise ValueError("count는 1 이상이어야 합니다: {}".format(count))
    s = str(end_qid).strip()
    if len(s) != 6 or not s.isdigit():
        raise ValueError("분기 시점은 YYYYQQ 6자리여야 합니다: {!r}".format(end_qid))
    y, q = int(s[:4]), int(s[4:])
    if q not in (1, 2, 3, 4):
        raise ValueError("분기는 1~4여야 합니다: {!r}".format(end_qid))
    out = []
    for _ in range(count):
        out.append(quarter_id(y, q))
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return list(reversed(out))


def _sttsapitbldata(payload):
    if not isinstance(payload, dict):
        return []
    d = payload.get("SttsApiTblData")
    return d if isinstance(d, list) else []


def _section_list(payload, idx, key):
    """SttsApiTblData[idx][key]를 list로 꺼낸다. 형태가 이상하면 None.

    R-ONE 봉투는 리스트 기반이라(MOLIT의 dict 기반과 다르다) 새 파서가 필요하다.
    어느 단계든 기대한 타입이 아니면 조용히 None을 돌려준다 — 응답이 이상할 때
    수집기가 죽는 게 아니라 "코드 없음"으로 흘러가야 재시도·보고가 돈다
    (collect_transactions.py의 _section()과 같은 방어 원칙).
    """
    d = _sttsapitbldata(payload)
    if len(d) <= idx or not isinstance(d[idx], dict):
        return None
    v = d[idx].get(key)
    return v if isinstance(v, list) else None


def read_result_code(payload):
    """응답에서 (CODE, MESSAGE)를 뽑는다.

    정상 경로: SttsApiTblData[0]['head']는 [{list_total_count:…}, {RESULT:{…}}]
    두 dict의 리스트다 — 그중 'RESULT' 키를 가진 쪽을 찾는다.
    방어 경로: head가 없거나 이상해도 최상위에 RESULT가 바로 올 수 있다(포털
    오류 응답 관행) — 그 경우도 본다. 둘 다 없으면 ('', '').
    """
    head = _section_list(payload, 0, "head")
    if head:
        for item in head:
            if isinstance(item, dict) and isinstance(item.get("RESULT"), dict):
                r = item["RESULT"]
                return str(r.get("CODE", "")).strip(), str(r.get("MESSAGE", "")).strip()
    if isinstance(payload, dict) and isinstance(payload.get("RESULT"), dict):
        r = payload["RESULT"]
        return str(r.get("CODE", "")).strip(), str(r.get("MESSAGE", "")).strip()
    return "", ""


def read_total_count(payload):
    """응답에서 list_total_count(int)를 뽑는다. 없거나 이상하면 0."""
    head = _section_list(payload, 0, "head")
    if head:
        for item in head:
            if isinstance(item, dict) and "list_total_count" in item:
                try:
                    return int(item["list_total_count"])
                except (TypeError, ValueError):
                    return 0
    return 0


def extract_rows(payload):
    """응답에서 SttsApiTblData[1]['row'] 목록을 꺼낸다. 없으면 []."""
    row = _section_list(payload, 1, "row")
    if row is None:
        return []
    return [x for x in row if isinstance(x, dict)]


def is_quiet_zero(total_count):
    """형식 오류가 에러 없이 0건으로 온다는 §1.2 실측 함정에 대한 가드."""
    return total_count == 0


_FLOOR_BUCKET_MAP = {
    "지하1층": "-1",
    "1층": "1",
    "2층": "2",
    "3층": "3",
    "4층": "4",
    "5층": "5",
    "6층이상": "6+",   # 정수 "6"이 아니다 — 6층 하나가 아니라 6층 이상 전체를 뭉친 값이다.
}


def floor_bucket_key(cls_nm):
    """R-ONE의 CLS_NM(층 구간 7종)을 floor_util_ratio jsonb 키로 바꾼다.

    R-ONE은 층을 7구간으로만 준다(지하1층·1~5층·6층이상) — 우리 building_floor의
    지하2층 이하·옥탑에 대응하는 구간이 아예 없다(§6.1 실측, 13.3% 계수 없음).
    그 외 문자열은 None(무시) — 억지로 추측하지 않는다.
    """
    return _FLOOR_BUCKET_MAP.get(str(cls_nm or "").strip())


def mask_secret(text, key=None):
    """문자열에서 인증키를 지운다. 로그·예외·DB 저장 전에 반드시 통과시킨다."""
    if text is None:
        return ""
    s = _SERVICE_KEY_QUERY_RE.sub(r"\1" + SECRET_MASK, str(text))
    if key:
        for variant in (key, quote(str(key), safe="")):
            if variant:
                s = s.replace(variant, SECRET_MASK)
    return s


def _normalize_signal(text):
    return _SIGNAL_STRIP_RE.sub("", str(text or "").upper())


def _matches_any_token(text, tokens):
    norm = _normalize_signal(text)
    return any(_normalize_signal(t) in norm for t in tokens)


def is_quota_exceeded(text):
    return _matches_any_token(text, QUOTA_EXCEEDED_TOKENS)


def is_service_key_error(text):
    return _matches_any_token(text, SERVICE_KEY_ERROR_TOKENS)


def page_count(total_count, num_of_rows=NUM_OF_ROWS, max_pages=MAX_PAGES):
    """collect_transactions.py의 page_count를 이 파일의 NUM_OF_ROWS/MAX_PAGES로 재사용."""
    return _page_count_base(total_count, num_of_rows=num_of_rows, max_pages=max_pages)


def is_truncated(total_count, num_of_rows=NUM_OF_ROWS, max_pages=MAX_PAGES):
    """collect_transactions.py의 is_truncated를 이 파일의 상수로 재사용."""
    return _is_truncated_base(total_count, num_of_rows=num_of_rows, max_pages=max_pages)


def now_kst_iso():
    return datetime.now(KST).isoformat()


def today_kst():
    """일 예산의 기준 날짜 — KST 자정에 포털 한도가 초기화된다(timezone-consistency.md)."""
    return datetime.now(KST).date().isoformat()


def current_quarter_id(now=None):
    n = now or datetime.now(KST)
    return quarter_id(n.year, (n.month - 1) // 3 + 1)


def default_raw_dir():
    return os.path.join(PROJECT_ROOT, "data", "raw", RAW_SUBDIR)


def raw_path(raw_dir, bld_type, metric):
    """건물유형x지표별로 한 파일 (24개). 분기는 줄 안에 기록한다."""
    return os.path.join(raw_dir, BLD_TYPE_SLUG[bld_type], "{}.jsonl".format(metric))


def append_jsonl(path, bld_type, metric, quarter_id_, rows, fetched_at):
    """raw에 append. 한 줄 = row 원본 하나 + 어느 조회에서 나온 것인지."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps({
                "bld_type": bld_type,
                "metric": metric,
                "quarter_id": quarter_id_,
                "fetched_at": fetched_at,
                "row": row,
            }, ensure_ascii=False) + "\n")


def budget_verdict(calls_used, planned_calls, budget):
    """오늘 예산으로 계획한 호출을 다 할 수 있는지 (dry-run 보고용).

    ⚠️ 잔여 예산은 상한이지 보장이 아니다 — collect_transactions.py와 같은 이유
    (2026-08-07 건축HUB 실측: 우리 계수기보다 포털 집계가 앞설 수 있다).
    """
    remaining = max(0, budget - calls_used)
    return {
        "remaining": remaining,
        "planned": planned_calls,
        "fits": planned_calls <= remaining,
        "shortfall": max(0, planned_calls - remaining),
    }


# ── API 호출 ─────────────────────────────────────────────────────────────────


def fetch_page(session, key, statbl_id, quarter_id_, page_no,
               retry_count=RETRY_COUNT, backoff_base=RETRY_BACKOFF_BASE_SEC,
               sleep=time.sleep):
    """한 페이지를 받아 JSON(dict)을 돌려준다.

    네트워크 오류·5xx는 지수 백오프로 재시도. 쿼터 초과는 QuotaExceededError,
    서비스키 문제는 ServiceKeyError, 그 외는 ApiError. 모든 예외 문자열은
    mask_secret()을 통과시킨다.
    """
    query = {
        "KEY": key,
        "STATBL_ID": statbl_id,
        "DTACYCLE_CD": DTACYCLE_CD,
        "WRTTIME_IDTFR_ID": quarter_id_,
        "Type": "json",
        "pIndex": page_no,
        "pSize": NUM_OF_ROWS,
    }
    url = "{}/{}".format(API_BASE_URL, ENDPOINT)

    def clean(text):
        return mask_secret(text, key)

    last_err = None
    for attempt in range(1, retry_count + 1):
        try:
            r = session.get(url, params=query, timeout=API_TIMEOUT_SEC)
        except requests.RequestException as e:
            last_err = clean("네트워크 오류: {}".format(e))
        else:
            if is_service_key_error(r.text):
                raise ServiceKeyError("서비스키 미등록·미승인 응답")
            if is_quota_exceeded(r.text):
                raise QuotaExceededError("쿼터 초과 응답")
            if r.status_code >= 500:
                last_err = "HTTP {}".format(r.status_code)
            elif r.status_code >= 300:
                raise ApiError("HTTP {}: {}".format(r.status_code, clean(r.text[:200])))
            else:
                try:
                    payload = r.json()
                except ValueError:
                    raise ApiError("JSON 파싱 실패: {}".format(clean(r.text[:200])))
                code, msg = read_result_code(payload)
                if is_service_key_error(msg):
                    raise ServiceKeyError("서비스키 미등록·미승인 응답: {}".format(clean(msg)))
                if is_quota_exceeded(msg):
                    raise QuotaExceededError("쿼터 초과 응답: {}".format(clean(msg)))
                if code != RESULT_CODE_OK:
                    raise ApiError("CODE={} {}".format(code, clean(msg)))
                return payload

        if attempt < retry_count:
            sleep(backoff_base ** attempt)

    raise ApiError("재시도 {}회 소진: {}".format(retry_count, last_err))


def fetch_all_pages(session, key, statbl_id, quarter_id_, call_counter=None, **kwargs):
    """totalCount 기준으로 끝까지 돌아 (row 목록, 호출 수, 절단 여부, total_count).

    call_counter를 넘기면 예외로 중단되더라도 그때까지 보낸 호출 수가 남는다
    (collect_transactions.py의 fetch_all_pages와 같은 이유 — 실패한 호출도
    포털 한도를 먹는다).
    """
    rows = []
    page_no = 1
    truncated = False
    total_count = 0
    counter = call_counter if call_counter is not None else [0]
    while True:
        counter[0] += 1
        payload = fetch_page(session, key, statbl_id, quarter_id_, page_no, **kwargs)
        rows.extend(extract_rows(payload))
        total_count = read_total_count(payload)
        if is_truncated(total_count):
            truncated = True
        if page_no >= page_count(total_count):
            break
        page_no += 1
    return rows, counter[0], truncated, total_count


def collect_one(session, key, bld_type, metric, quarter_id_, raw_dir, **kwargs):
    """(건물유형, 지표, 분기) 하나를 받아 raw에 append 한다.

    반환 dict: status/row_count/error_msg/calls. quiet-zero(0건)는 status를
    'done'으로 두되(CHECK 제약이 이미 4개 값으로 고정돼 있어 새 상태값을
    만들지 않는다) error_msg에 의심 사유를 남겨 사람이 보게 한다.
    raw 원자성: 끝까지 받은 뒤에 한 번에 쓴다(중간 실패 시 raw 무기록).
    """
    statbl_id = STATBL_IDS[bld_type][metric]
    counter = [0]
    try:
        rows, calls, truncated, total_count = fetch_all_pages(
            session, key, statbl_id, quarter_id_, call_counter=counter, **kwargs)
    except (QuotaExceededError, ServiceKeyError):
        raise
    except ApiError as e:
        return {"status": "failed", "row_count": None,
                "error_msg": mask_secret(str(e), key)[:500],
                "calls": counter[0]}

    append_jsonl(raw_path(raw_dir, bld_type, metric), bld_type, metric, quarter_id_,
                 rows, now_kst_iso())

    error_msg = None
    if is_quiet_zero(total_count):
        error_msg = "0건 응답 — 미공표 분기이거나 지표 없음 의심"
    elif truncated:
        error_msg = "페이지 상한 도달 — 절단 의심"

    return {"status": "done", "row_count": len(rows), "error_msg": error_msg, "calls": calls}


# ── Supabase(PostgREST) ──────────────────────────────────────────────────────


def get_supabase_config():
    load_dotenv()
    url = os.environ.get("SANGGA_SUPABASE_URL", "").strip().rstrip("/")
    key = (os.environ.get("SANGGA_SUPABASE_SERVICE_KEY")
           or os.environ.get("SANGGA_SUPABASE_ANON_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError(
            ".env에 SANGGA_SUPABASE_URL과 키(SERVICE 또는 ANON)가 필요합니다.")
    return url, key


def get_api_key():
    load_dotenv()
    key = os.environ.get("REB_KEY", "").strip()
    if not key:
        raise RuntimeError(
            ".env에 REB_KEY(한국부동산원 R-ONE 인증키)가 필요합니다.")
    return key


def rest_select(base_url, headers, table, query, page_size=SELECT_PAGE_SIZE, order="scope_key"):
    """PostgREST는 기본 1,000행만 준다 — 반드시 페이지네이션한다."""
    rows = []
    offset = 0
    while True:
        url = "{}/rest/v1/{}?{}order={}&limit={}&offset={}".format(
            base_url, table, (query + "&") if query else "", order, page_size, offset)
        r = requests.get(url, headers=headers, timeout=REST_TIMEOUT_SEC)
        if r.status_code >= 300:
            raise RuntimeError("{} 조회 실패 (HTTP {}): {}".format(
                table, r.status_code, r.text[:300]))
        part = r.json()
        rows.extend(part)
        if len(part) < page_size:
            return rows
        offset += page_size


def upsert_batch(base_url, headers, table, rows, resolution, batch_size=BATCH_SIZE):
    sent = 0
    for i in range(0, len(rows), batch_size):
        part = rows[i:i + batch_size]
        r = requests.post(
            "{}/rest/v1/{}".format(base_url, table),
            headers=dict(headers, **{
                "Content-Type": "application/json",
                "Prefer": "resolution={},return=minimal".format(resolution),
            }),
            data=json.dumps(part, ensure_ascii=False).encode("utf-8"),
            timeout=REST_TIMEOUT_SEC,
        )
        if r.status_code >= 300:
            raise RuntimeError("{} 저장 실패 (HTTP {}): {}".format(
                table, r.status_code, r.text[:300]))
        sent += len(part)
    return sent


def seed_progress(base_url, headers, bld_types, metrics, quarters):
    """(건물유형:지표, 각 분기)를 pending으로 시드한다. 이미 있는 행은 보존."""
    rows = [
        {"collector": COLLECTOR, "scope_key": "{}:{}".format(bt, mt),
         "period_key": q, "status": "pending"}
        for bt in bld_types for mt in metrics for q in quarters
    ]
    return upsert_batch(base_url, headers, "collect_progress", rows, "ignore-duplicates")


def fetch_pending(base_url, headers, bld_type=None, metric=None):
    """pending 행을 (건물유형, 지표, 분기, attempts) 튜플로 돌려준다.

    bld_type/metric을 주면 scope_key를 그 값으로 좁힌다(파일럿 축소용).
    """
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=scope_key,period_key,attempts&collector=eq.{}&status=eq.pending".format(
            COLLECTOR),
        order="scope_key,period_key")
    out = []
    for r in rows:
        bt, _, mt = str(r["scope_key"]).partition(":")
        if bld_type and bt != bld_type:
            continue
        if metric and mt != metric:
            continue
        out.append((bt, mt, r["period_key"], r.get("attempts") or 0))
    return out


def progress_status_counts(base_url, headers):
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=status&collector=eq.{}".format(COLLECTOR),
        order="scope_key")
    return Counter(r["status"] for r in rows)


def save_progress(base_url, headers, bld_type, metric, quarter_id_, result, attempts):
    row = {
        "collector": COLLECTOR,
        "scope_key": "{}:{}".format(bld_type, metric),
        "period_key": quarter_id_,
        "status": result["status"],
        "row_count": result.get("row_count"),
        "error_msg": result.get("error_msg"),
        "attempts": attempts + (1 if result["status"] == "failed" else 0),
        "updated_at": datetime.now(KST).isoformat(),
    }
    upsert_batch(base_url, headers, "collect_progress", [row], "merge-duplicates")


def retry_failed(base_url, headers, bld_type=None, metric=None, max_attempts=5):
    """failed를 pending으로 되돌린다 (attempts가 상한 미만인 것만 — 무한 재시도 방지)."""
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=scope_key,period_key,attempts&collector=eq.{}&status=eq.failed".format(
            COLLECTOR),
        order="scope_key,period_key")
    targets = []
    for r in rows:
        bt, _, mt = str(r["scope_key"]).partition(":")
        if bld_type and bt != bld_type:
            continue
        if metric and mt != metric:
            continue
        if (r.get("attempts") or 0) < max_attempts:
            targets.append(r)
    if not targets:
        return 0
    upsert_batch(base_url, headers, "collect_progress", [
        {"collector": COLLECTOR, "scope_key": r["scope_key"],
         "period_key": r["period_key"], "status": "pending", "error_msg": None}
        for r in targets], "merge-duplicates")
    return len(targets)


def read_quota_baseline(base_url, headers, log_date):
    rows = rest_select(
        base_url, headers, "api_quota_log",
        "select=call_count&log_date=eq.{}&collector=eq.{}&api_name=eq.{}".format(
            log_date, COLLECTOR, ENDPOINT),
        order="api_name")
    return rows[0]["call_count"] if rows else 0


def flush_quota_log(base_url, headers, log_date, baseline, session_calls):
    if not session_calls:
        return
    upsert_batch(base_url, headers, "api_quota_log", [{
        "log_date": log_date, "collector": COLLECTOR, "api_name": ENDPOINT,
        "call_count": baseline + session_calls,
    }], "merge-duplicates")


# ── 보고 ─────────────────────────────────────────────────────────────────────


def print_dry_run_report(bld_type, metric, quarters, raw_dir, pending, counts, verdict, budget):
    print("=" * 78)
    print("R-ONE 임대동향조사 수집 — dry-run")
    print("=" * 78)
    print("  건물유형        {}".format(bld_type or "전체 4종"))
    print("  지표            {}".format(metric or "전체 6종"))
    print("  대상 분기       {} ~ {} ({}개)".format(quarters[0], quarters[-1], len(quarters)))
    print("  raw 폴더        {}".format(raw_dir))
    print("")
    print("  [ collect_progress 현황 (collector 전체) ]")
    for st in ("done", "pending", "failed", "skipped"):
        print("    {:<9} {:>6,}".format(st, counts.get(st, 0)))
    print("")
    print("  [ 오늘 예산 ] 일 {:,}건 (공식 한도 미명시 — 필요량으로 역산)".format(budget))
    print("    남은 예산     {:>6,}건".format(verdict["remaining"]))
    print("    계획 호출     {:>6,}건 (pending {:,}개 조합 x 1콜 가정, 대부분 1페이지)".format(
        verdict["planned"], len(pending)))
    if verdict["fits"]:
        print("    -> 오늘 안에 끝날 것으로 보입니다.")
    else:
        print("    -> {:,}건 모자랍니다. 오늘 가능한 만큼만 하고 안전 종료합니다.".format(
            verdict["shortfall"]))
    print("=" * 78)


def print_run_report(processed, status_counter, session_calls, elapsed_sec, stop_reason, rows):
    print("")
    print("=" * 78)
    print("수집 종료 — {}".format(stop_reason))
    print("=" * 78)
    print("  처리한 (건물유형, 지표, 분기) 조합 {:,}개 / 받은 행 {:,}건".format(processed, rows))
    for st in ("done", "failed", "skipped"):
        if status_counter.get(st):
            print("    {:<9} {:>6,}".format(st, status_counter[st]))
    print("  API 호출 {:,}건 / 소요 {:.1f}분".format(session_calls, elapsed_sec / 60))
    print("=" * 78)


# ── 메인 ─────────────────────────────────────────────────────────────────────


def _reject_unknown_args(argv, bool_flags, value_flags):
    """모르는 인자를 만나면 즉시 멈춘다 (collect_transactions.py와 같은 이유 —
    조용한 무시가 --dry-run 오타를 실제 실행으로 바꾼 사고가 있었다, 2026-08-08)."""
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in value_flags:
            i += 2
            continue
        if a in bool_flags:
            i += 1
            continue
        raise ValueError(
            "알 수 없는 인자: {!r}\n  쓸 수 있는 인자: {}".format(
                a, " ".join(sorted(set(bool_flags) | set(value_flags)))
            )
        )


def parse_args(argv):
    _reject_unknown_args(
        argv,
        bool_flags=("--dry-run", "--retry-failed"),
        value_flags=("--bld-type", "--metric", "--quarters", "--end-qid",
                      "--raw-dir", "--daily-budget", "--limit"),
    )
    opts = {
        "bld_type": None,
        "metric": None,
        "quarters": DEFAULT_QUARTERS,
        "end_qid": None,
        "raw_dir": None,
        "daily_budget": DEFAULT_DAILY_BUDGET,
        "dry_run": "--dry-run" in argv,
        "retry_failed": "--retry-failed" in argv,
        "limit": None,
    }
    for flag, key, cast in (
        ("--bld-type", "bld_type", str),
        ("--metric", "metric", str),
        ("--quarters", "quarters", int),
        ("--end-qid", "end_qid", str),
        ("--raw-dir", "raw_dir", str),
        ("--daily-budget", "daily_budget", int),
        ("--limit", "limit", int),
    ):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise ValueError("{} 뒤에 값이 필요합니다.".format(flag))
            opts[key] = cast(argv[i + 1])
    if opts["bld_type"] is not None and opts["bld_type"] not in BLD_TYPES:
        raise ValueError("--bld-type은 {} 중 하나여야 합니다: {!r}".format(
            BLD_TYPES, opts["bld_type"]))
    if opts["metric"] is not None and opts["metric"] not in METRICS:
        raise ValueError("--metric은 {} 중 하나여야 합니다: {!r}".format(
            METRICS, opts["metric"]))
    if opts["raw_dir"] is None:
        opts["raw_dir"] = default_raw_dir()
    if opts["end_qid"] is None:
        opts["end_qid"] = current_quarter_id()
    return opts


def install_sigint_handler():
    def handler(_signum, _frame):
        if _STOP_REQUESTED["value"]:
            print("\n[중단] 두 번째 요청 — 즉시 종료합니다.", flush=True)
            sys.exit(130)
        _STOP_REQUESTED["value"] = True
        print("\n[중단 요청] 현재 조합을 마치고 안전 종료합니다. (한 번 더 누르면 즉시 종료)",
              flush=True)
    try:
        signal.signal(signal.SIGINT, handler)
    except (ValueError, OSError):
        pass


def main():
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    try:
        opts = parse_args(sys.argv[1:])
    except ValueError as e:
        print("[에러] {}".format(e))
        return 2

    try:
        quarters = quarter_range(opts["end_qid"], opts["quarters"])
        base_url, key = get_supabase_config()
        service_key = get_api_key()
    except (RuntimeError, ValueError) as e:
        print("[에러] {}".format(e))
        return 1
    headers = {"apikey": key, "Authorization": "Bearer {}".format(key)}

    bld_types = (opts["bld_type"],) if opts["bld_type"] else BLD_TYPES
    metrics = (opts["metric"],) if opts["metric"] else METRICS

    if opts["retry_failed"]:
        print("--retry-failed 지정 — failed 상태를 pending으로 되돌리는 중...", flush=True)
        n = retry_failed(base_url, headers, opts["bld_type"], opts["metric"])
        print("  되돌림: {}건".format(n))

    print("collect_progress 시드 중... ({}유형 x {}지표 x {}분기, 이미 있는 행은 보존)".format(
        len(bld_types), len(metrics), len(quarters)), flush=True)
    seed_progress(base_url, headers, bld_types, metrics, quarters)

    quarter_set = set(quarters)
    pending = [(bt, mt, q, at) for bt, mt, q, at in
               fetch_pending(base_url, headers, opts["bld_type"], opts["metric"])
               if q in quarter_set]
    counts = progress_status_counts(base_url, headers)
    log_date = today_kst()
    baseline = read_quota_baseline(base_url, headers, log_date)
    verdict = budget_verdict(baseline, len(pending), opts["daily_budget"])

    if opts["dry_run"]:
        print_dry_run_report(opts["bld_type"], opts["metric"], quarters, opts["raw_dir"],
                             pending, counts, verdict, opts["daily_budget"])
        return 0

    if not pending:
        print("처리할 pending이 없습니다 — 이미 다 걷었습니다.")
        return 0

    if opts["limit"]:
        pending = pending[:opts["limit"]]

    print("처리 대상 {:,}개 조합 (오늘 사용 합계 {:,}건 / 예산 {:,}건)".format(
        len(pending), baseline, opts["daily_budget"]), flush=True)

    install_sigint_handler()
    session = requests.Session()
    started = time.time()
    session_calls = 0
    processed = 0
    rows_total = 0
    status_counter = Counter()
    stop_reason = "전량 완료"

    try:
        for idx, (bld_type, metric, quarter_id_, attempts) in enumerate(pending, 1):
            if _STOP_REQUESTED["value"]:
                stop_reason = "사용자 중단 요청"
                break
            if baseline + session_calls >= opts["daily_budget"]:
                stop_reason = "일 예산 도달 — 내일 이어받기"
                break
            try:
                result = collect_one(
                    session, service_key, bld_type, metric, quarter_id_, opts["raw_dir"])
            except QuotaExceededError as e:
                stop_reason = "포털 쿼터 초과 — 자정(KST) 리셋 후 이어받기 ({})".format(e)
                session_calls += 1
                break
            except ServiceKeyError as e:
                stop_reason = "서비스키 문제 — 활용신청·키를 확인하세요 ({})".format(e)
                session_calls += 1
                break

            session_calls += result["calls"]
            processed += 1
            rows_total += result.get("row_count") or 0
            status_counter[result["status"]] += 1
            save_progress(base_url, headers, bld_type, metric, quarter_id_, result, attempts)

            if idx % 20 == 0 or idx == len(pending):
                print("  진행 {:,}/{:,} ({}:{} {} / 행 {:,}건 / 누적 호출 {:,})".format(
                    idx, len(pending), bld_type, metric, quarter_id_, rows_total, session_calls),
                    flush=True)
    finally:
        flush_quota_log(base_url, headers, log_date, baseline, session_calls)

    print_run_report(processed, status_counter, session_calls,
                     time.time() - started, stop_reason, rows_total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
