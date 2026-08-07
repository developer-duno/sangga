# -*- coding: utf-8 -*-
"""
상업업무용 부동산 매매 실거래가(국토교통부) API → raw JSONL 수집

`docs/상세계획.md` §5.1 [3]·§5.3(호출 3단계)·§5.6(품질 지표)과
`anthropic-skills:budongsan-data` 규격을 따른다.

무엇을 하나:
  1. 대상 (시군구코드, 계약년월) 조합을 collect_progress에 시드한다.
     scope_key=시군구코드 / period_key=계약년월 — schema.sql의 collect_progress
     주석이 처음부터 이 수집기를 상정해 둔 그 구조다(collector='rtms_commercial').
  2. 조합 하나마다 getRTMSDataSvcNrgTrade를 호출해 응답 원본(item)을 그대로
     raw JSONL에 append 한다 (CLAUDE.md 수집 규칙: raw는 절대 덮어쓰지 않는다).
     PNU 조립·금액 변환·층 정규화는 전부 다음 단계 load_transactions.py 소관 —
     이 스크립트는 아무것도 해석하지 않는다.
  3. api_quota_log로 일 예산을 추적하고, 예산 도달·중단 요청·쿼터 초과 어느
     쪽이든 현재 조합을 마무리한 뒤 진행 상태를 저장하고 안전 종료한다.

⚠️ 건축물대장 수집기(collect_building_ledger.py)와 다른 점 — 복사할 때 반드시 확인:
  - **성공 resultCode가 '000'이다** (건축HUB는 '00'). 2자리로 비교하면 정상 응답이
    전부 실패로 판정된다. 2026-08-08 라이브 프로브로 확정.
  - 한도가 별개다. 건축HUB와 다른 API라 동시에 돌려도 서로의 예산을 먹지 않는다
    (`MOLIT_KEY` / `BLDRGST_KEY`도 별개).
  - 조회 단위가 PNU가 아니라 (시군구, 계약년월)이다. 그래서 raw도 시군구별 한 파일에
    쌓고 각 줄에 어느 달치인지 함께 남긴다.

라이브 실측 (2026-08-08, 강남구 24개월 2,151건):
  - **집합(구분상가)만 지번이 정상으로 온다.** 일반(통건물)은 `jibun`이 '6**'처럼
    마스킹돼 100% PNU 조립 불가 — §5.6 "통건물 조립 성공률은 낮을 것"의 답은
    "낮은 게 아니라 0%"다. 집합은 반대로 1,518건 전부 조립 성공(100%).
  - 층(`floor`)은 집합 69.2%만 채워지고 일반은 1.9%뿐이다.
  - `cdealType='O'`(해제) 거래가 9.9% 섞여 있다. 시세 추정에서 반드시 빼야 한다.
  - `dealAmount`는 **만원 단위 + 콤마 문자열**('136,000' = 13.6억).
  - numOfRows=1000이 정상 동작한다(100으로 깎이지 않음).

사용법:
  python scripts/collectors/collect_transactions.py --dry-run
  python scripts/collectors/collect_transactions.py --months 6        # 최근 6개월만
  python scripts/collectors/collect_transactions.py                   # 파일럿: 강남 20년
  python scripts/collectors/collect_transactions.py --sigungu-code 11440
  python scripts/collectors/collect_transactions.py --retry-failed
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

# ── 설정 ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 국토교통부 상업업무용 부동산 매매 실거래가 (포털 ID 15126463).
# 2026-08-08 라이브 프로브로 확정 — 포털 상세 페이지에는 엔드포인트가 없고
# 기술문서(hwp) 첨부에만 있어, 검색으로 주소를 찾아 실호출로 검증했다.
API_BASE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcNrgTrade"
ENDPOINT = "getRTMSDataSvcNrgTrade"

COLLECTOR = "rtms_commercial"      # schema.sql collect_progress 주석의 그 이름
RAW_SUBDIR = "rtms"
DEFAULT_SIGUNGU_CODE = "11680"     # 강남구 (§0.2 파일럿)
DEFAULT_MONTHS = 240               # §5.3 1단계 파일럿 = 1개 구 x 20년 = 240 호출

# 한도는 API(오퍼레이션)별 일 10,000건. 여유를 두고 9,500으로 잡는다
# (건축HUB에서 9,208콜에 실제로 차단된 실측 근거 — §5.3 참조).
DEFAULT_DAILY_BUDGET = 9_500

RETRY_FAILED_MAX_ATTEMPTS = 5

# 한 달치가 1,000건을 넘는 시군구는 거의 없다(강남 최다 월 81건 실측). 넉넉히 잡아
# 대부분의 달을 1콜로 끝낸다 — §5.3의 "240 호출" 계산이 이 값을 전제로 한다.
NUM_OF_ROWS = 1000
MAX_PAGES = 100

API_TIMEOUT_SEC = 30
REST_TIMEOUT_SEC = 120

RETRY_COUNT = 3
RETRY_BACKOFF_BASE_SEC = 2

# ⚠️ 건축HUB('00')와 다르다 — 이 API는 3자리 '000'이다 (2026-08-08 실측).
RESULT_CODE_OK = "000"

QUOTA_EXCEEDED_TOKENS = (
    "LIMITED NUMBER OF SERVICE REQUESTS EXCEEDS",
)
SERVICE_KEY_ERROR_TOKENS = (
    "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
    "SERVICE KEY IS NOT REGISTERED",
)

_SIGNAL_STRIP_RE = re.compile(r"[^A-Z0-9]+")
_SERVICE_KEY_QUERY_RE = re.compile(r"(serviceKey=)[^&\s'\"]+", re.IGNORECASE)
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


def month_range(end_ym, months):
    """end_ym에서 과거로 months개월치 'YYYYMM' 목록을 옛날→최근 순으로 만든다.

    실거래는 과거가 안 변하므로 옛날부터 채우는 편이 이어받기에 유리하다
    (중간에 멈춰도 "어디까지 채웠나"가 연속 구간으로 남는다).
    """
    if months <= 0:
        raise ValueError("months는 1 이상이어야 합니다: {}".format(months))
    s = str(end_ym).strip()
    if len(s) != 6 or not s.isdigit():
        raise ValueError("계약년월은 YYYYMM 6자리여야 합니다: {!r}".format(end_ym))
    y, m = int(s[:4]), int(s[4:])
    if not 1 <= m <= 12:
        raise ValueError("월은 1~12여야 합니다: {!r}".format(end_ym))
    out = []
    for _ in range(months):
        out.append("{:04d}{:02d}".format(y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def _section(payload, name):
    """payload['response'][name]을 dict로 꺼낸다. 어느 단계든 dict가 아니면 {}.

    포털은 오류 시 `response`가 dict가 아니라 문자열인 봉투를 내려주기도 한다.
    한 단계라도 그냥 .get()을 부르면 AttributeError로 터진다 — 응답이 이상할 때
    수집기가 죽는 게 아니라 "코드 없음"으로 조용히 흘러가야 재시도·보고가 돈다.
    (단위 테스트가 실제로 잡아낸 결함이다.)
    """
    if not isinstance(payload, dict):
        return {}
    resp = payload.get("response")
    if not isinstance(resp, dict):
        return {}
    sec = resp.get(name)
    return sec if isinstance(sec, dict) else {}


def read_result_code(payload):
    """응답 JSON에서 (resultCode, resultMsg)를 뽑는다. 형태가 이상하면 ('', '')."""
    header = _section(payload, "header")
    return str(header.get("resultCode", "")).strip(), str(header.get("resultMsg", "")).strip()


def read_total_count(payload):
    """응답 JSON에서 totalCount(int)를 뽑는다. 없거나 이상하면 0."""
    try:
        return int(str(_section(payload, "body").get("totalCount", "")).strip())
    except (TypeError, ValueError):
        return 0


def extract_items(payload):
    """응답 JSON에서 items.item 목록을 꺼낸다.

    건수에 따라 형태가 세 갈래인 것은 포털 공통이다 (1건 dict / N건 list /
    0건 빈 문자열·None). 세 케이스 모두 방어한다.
    """
    body = _section(payload, "body")
    items = body.get("items")
    if not isinstance(items, dict):
        return []
    item = items.get("item")
    if isinstance(item, dict):
        return [item]
    if isinstance(item, list):
        return [x for x in item if isinstance(x, dict)]
    return []


def page_count(total_count, num_of_rows=NUM_OF_ROWS, max_pages=MAX_PAGES):
    """totalCount로 읽어야 할 페이지 수 (0건이면 1 — 이미 받은 그 페이지)."""
    if num_of_rows <= 0:
        raise ValueError("numOfRows는 1 이상이어야 합니다: {}".format(num_of_rows))
    if total_count <= 0:
        return 1
    return min(-(-int(total_count) // num_of_rows), max_pages)


def is_truncated(total_count, num_of_rows=NUM_OF_ROWS, max_pages=MAX_PAGES):
    """페이지 상한에 실제로 걸렸는지 — 걸렸으면 error_msg에 경고를 남긴다."""
    if total_count <= 0:
        return False
    return -(-int(total_count) // num_of_rows) > max_pages


def mask_secret(text, service_key=None):
    """문자열에서 인증키를 지운다. 로그·예외·DB 저장 전에 반드시 통과시킨다.

    requests 예외 문자열에는 요청 URL이 통째로 들어가고 거기에 serviceKey가 붙어
    있다. 그대로 collect_progress.error_msg로 흘러가면 키가 DB에 평문으로 박제된다.
    """
    if text is None:
        return ""
    s = _SERVICE_KEY_QUERY_RE.sub(r"\1" + SECRET_MASK, str(text))
    if service_key:
        for variant in (service_key, quote(str(service_key), safe="")):
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


def now_kst_iso():
    return datetime.now(KST).isoformat()


def today_kst():
    """일 예산의 기준 날짜. 서버(UTC)가 아니라 KST 기준으로 센다.

    한국 시간 자정에 포털 한도가 초기화되므로 예산도 같은 축이어야 한다
    (~/.claude/rules/timezone-consistency.md).
    """
    return datetime.now(KST).date().isoformat()


def default_raw_dir():
    return os.path.join(PROJECT_ROOT, "data", "raw", RAW_SUBDIR)


def raw_path(raw_dir, sigungu_code):
    """시군구별로 한 파일. 계약년월은 줄 안에 기록한다(폴더 240개를 만들지 않는다)."""
    return os.path.join(raw_dir, "{}.jsonl".format(sigungu_code))


def append_jsonl(path, sigungu_code, deal_ym, items, fetched_at):
    """raw에 append. 한 줄 = 응답 아이템 하나 + 어느 조회에서 나온 것인지."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fp:
        for item in items:
            fp.write(json.dumps({
                "sigungu_code": sigungu_code,
                "deal_ym": deal_ym,
                "fetched_at": fetched_at,
                "item": item,
            }, ensure_ascii=False) + "\n")


def budget_verdict(calls_used, planned_calls, budget):
    """오늘 예산으로 계획한 호출을 다 할 수 있는지 (dry-run 보고용).

    ⚠️ 잔여 예산은 **상한이지 보장이 아니다** — 우리 계수기는 우리가 보낸 횟수만
    세는데 포털 집계가 앞설 수 있다(2026-08-07 건축HUB 실측: dry-run이 292건
    남았다고 했으나 실제 호출은 이미 쿼터 초과로 거절됐다). 잔여가 적으면
    소진으로 보고 자정 리셋을 기다리는 편이 낫다.
    """
    remaining = max(0, budget - calls_used)
    return {
        "remaining": remaining,
        "planned": planned_calls,
        "fits": planned_calls <= remaining,
        "shortfall": max(0, planned_calls - remaining),
    }


# ── API 호출 ─────────────────────────────────────────────────────────────────


def fetch_page(session, service_key, sigungu_code, deal_ym, page_no,
               retry_count=RETRY_COUNT, backoff_base=RETRY_BACKOFF_BASE_SEC,
               sleep=time.sleep):
    """한 페이지를 받아 JSON(dict)을 돌려준다.

    네트워크 오류·5xx는 지수 백오프로 재시도. 쿼터 초과는 QuotaExceededError,
    서비스키 문제는 ServiceKeyError(둘은 종료 보고가 달라 갈라 놓는다),
    그 외는 ApiError. 모든 예외 문자열은 mask_secret()을 통과시킨다.
    """
    query = {
        "serviceKey": service_key,
        "LAWD_CD": sigungu_code,
        "DEAL_YMD": deal_ym,
        "pageNo": page_no,
        "numOfRows": NUM_OF_ROWS,
        "_type": "json",
    }
    url = "{}/{}".format(API_BASE_URL, ENDPOINT)

    def clean(text):
        return mask_secret(text, service_key)

    last_err = None
    for attempt in range(1, retry_count + 1):
        try:
            r = session.get(url, params=query, timeout=API_TIMEOUT_SEC)
        except requests.RequestException as e:
            last_err = clean("네트워크 오류: {}".format(e))
        else:
            # 키·쿼터 오류는 JSON이 아니라 XML 에러 봉투로 오는 경우가 있어 본문에서 먼저 본다.
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
                    raise ApiError("resultCode={} {}".format(code, clean(msg)))
                return payload

        if attempt < retry_count:
            sleep(backoff_base ** attempt)

    raise ApiError("재시도 {}회 소진: {}".format(retry_count, last_err))


def fetch_all_pages(session, service_key, sigungu_code, deal_ym, call_counter=None, **kwargs):
    """totalCount 기준으로 끝까지 돌아 (아이템 목록, 호출 수, 절단 여부).

    call_counter(list[int], 길이 1)를 넘기면 **예외로 중단되더라도** 그때까지 보낸
    호출 수가 거기에 남는다. 실패한 호출도 포털 한도를 먹기 때문에, 이걸 안 세면
    우리 계수기가 실제보다 적게 잡혀 "예산이 남았다"고 착각하게 된다
    (2026-08-07 건축HUB에서 겪은 "잔여는 상한이지 보장이 아니다"와 같은 결).
    """
    items = []
    page_no = 1
    truncated = False
    counter = call_counter if call_counter is not None else [0]
    while True:
        counter[0] += 1   # 보내기 직전에 센다 — 실패해도 한도는 이미 소모된다
        payload = fetch_page(session, service_key, sigungu_code, deal_ym, page_no, **kwargs)
        items.extend(extract_items(payload))
        total_count = read_total_count(payload)
        if is_truncated(total_count):
            truncated = True
        if page_no >= page_count(total_count):
            break
        page_no += 1
    return items, counter[0], truncated


def collect_one_month(session, service_key, sigungu_code, deal_ym, raw_dir, **kwargs):
    """(시군구, 계약년월) 하나를 받아 raw에 append 한다.

    반환 dict: status/row_count/error_msg/calls.
    raw 원자성: 그 달을 끝까지 받은 뒤에 한 번에 쓴다(중간 실패 시 raw 무기록).
    QuotaExceededError·ServiceKeyError는 잡지 않고 올려보낸다 — 안전 종료는 호출부 책임.
    """
    counter = [0]
    try:
        items, calls, truncated = fetch_all_pages(
            session, service_key, sigungu_code, deal_ym, call_counter=counter, **kwargs)
    except (QuotaExceededError, ServiceKeyError):
        raise
    except ApiError as e:
        return {"status": "failed", "row_count": None,
                "error_msg": mask_secret(str(e), service_key)[:500],
                "calls": counter[0]}

    append_jsonl(raw_path(raw_dir, sigungu_code), sigungu_code, deal_ym,
                 items, now_kst_iso())
    return {
        "status": "done",
        "row_count": len(items),
        "error_msg": ("페이지 상한 도달 — 절단 의심" if truncated else None),
        "calls": calls,
    }


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
    key = os.environ.get("MOLIT_KEY", "").strip()
    if not key:
        raise RuntimeError(
            ".env에 MOLIT_KEY(공공데이터포털 국토부 실거래가 인증키)가 필요합니다.")
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


def seed_progress(base_url, headers, sigungu_code, months):
    """(시군구, 각 계약년월)을 pending으로 시드한다. 이미 있는 행은 보존."""
    rows = [{"collector": COLLECTOR, "scope_key": sigungu_code,
             "period_key": ym, "status": "pending"} for ym in months]
    return upsert_batch(base_url, headers, "collect_progress", rows, "ignore-duplicates")


def fetch_pending(base_url, headers, sigungu_code):
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=period_key,attempts&collector=eq.{}&scope_key=eq.{}&status=eq.pending".format(
            COLLECTOR, sigungu_code),
        order="period_key")
    return [(r["period_key"], r.get("attempts") or 0) for r in rows]


def progress_status_counts(base_url, headers, sigungu_code):
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=status&collector=eq.{}&scope_key=eq.{}".format(COLLECTOR, sigungu_code),
        order="period_key")
    return Counter(r["status"] for r in rows)


def save_progress(base_url, headers, sigungu_code, deal_ym, result, attempts):
    row = {
        "collector": COLLECTOR,
        "scope_key": sigungu_code,
        "period_key": deal_ym,
        "status": result["status"],
        "row_count": result.get("row_count"),
        "error_msg": result.get("error_msg"),
        "attempts": attempts + (1 if result["status"] == "failed" else 0),
        "updated_at": datetime.now(KST).isoformat(),
    }
    upsert_batch(base_url, headers, "collect_progress", [row], "merge-duplicates")


def retry_failed(base_url, headers, sigungu_code, max_attempts=RETRY_FAILED_MAX_ATTEMPTS):
    """failed를 pending으로 되돌린다 (attempts가 상한 미만인 것만 — 무한 재시도 방지)."""
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=period_key,attempts&collector=eq.{}&scope_key=eq.{}&status=eq.failed".format(
            COLLECTOR, sigungu_code),
        order="period_key")
    targets = [r for r in rows if (r.get("attempts") or 0) < max_attempts]
    if not targets:
        return 0
    upsert_batch(base_url, headers, "collect_progress", [
        {"collector": COLLECTOR, "scope_key": sigungu_code,
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


def print_dry_run_report(sigungu_code, months, raw_dir, pending, counts, verdict, budget):
    print("=" * 78)
    print("상업업무용 실거래가 수집 — dry-run")
    print("=" * 78)
    print("  시군구코드      {}".format(sigungu_code))
    print("  대상 기간       {} ~ {} ({}개월)".format(months[0], months[-1], len(months)))
    print("  raw 파일        {}".format(raw_path(raw_dir, sigungu_code)))
    print("")
    print("  [ collect_progress 현황 ]")
    for st in ("done", "pending", "failed", "skipped"):
        print("    {:<9} {:>6,}".format(st, counts.get(st, 0)))
    print("")
    print("  [ 오늘 예산 ] 일 {:,}건 (API별 한도 10,000 - 여유)".format(budget))
    print("    남은 예산     {:>6,}건".format(verdict["remaining"]))
    print("    계획 호출     {:>6,}건 (pending {:,}개월 x 1콜 가정)".format(
        verdict["planned"], len(pending)))
    if verdict["fits"]:
        print("    -> 오늘 안에 끝날 것으로 보입니다.")
    else:
        print("    -> {:,}건 모자랍니다. 오늘 가능한 만큼만 하고 안전 종료합니다.".format(
            verdict["shortfall"]))
    print("")
    print("  ⚠️ 남은 예산은 상한이지 보장이 아닙니다 — 우리 계수기는 우리가 보낸 횟수만")
    print("     세는데 포털 집계가 앞설 수 있습니다(2026-08-07 실측). 잔여가 적으면")
    print("     소진으로 보고 자정(KST) 리셋을 기다리는 편이 낫습니다.")
    print("=" * 78)


def print_run_report(processed, status_counter, session_calls, elapsed_sec, stop_reason, rows):
    print("")
    print("=" * 78)
    print("수집 종료 — {}".format(stop_reason))
    print("=" * 78)
    print("  처리한 (시군구, 년월) 조합 {:,}개 / 받은 거래 {:,}건".format(processed, rows))
    for st in ("done", "failed", "skipped"):
        if status_counter.get(st):
            print("    {:<9} {:>6,}".format(st, status_counter[st]))
    print("  API 호출 {:,}건 / 소요 {:.1f}분".format(session_calls, elapsed_sec / 60))
    print("=" * 78)


# ── 메인 ─────────────────────────────────────────────────────────────────────


def parse_args(argv):
    opts = {
        "sigungu_code": DEFAULT_SIGUNGU_CODE,
        "months": DEFAULT_MONTHS,
        "end_ym": None,
        "raw_dir": None,
        "daily_budget": DEFAULT_DAILY_BUDGET,
        "dry_run": "--dry-run" in argv,
        "retry_failed": "--retry-failed" in argv,
        "limit": None,
    }
    for flag, key, cast in (
        ("--sigungu-code", "sigungu_code", str),
        ("--months", "months", int),
        ("--end-ym", "end_ym", str),
        ("--raw-dir", "raw_dir", str),
        ("--daily-budget", "daily_budget", int),
        ("--limit", "limit", int),
    ):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise ValueError("{} 뒤에 값이 필요합니다.".format(flag))
            opts[key] = cast(argv[i + 1])
    if opts["raw_dir"] is None:
        opts["raw_dir"] = default_raw_dir()
    if opts["end_ym"] is None:
        # 실거래는 신고 기한(계약일로부터 30일)이 있어 최근 달은 아직 덜 찬다.
        # 그래도 받아 두고 나중에 재수집하는 편이 낫다 — raw는 append이므로
        # 적재기가 최신 배치만 채택한다.
        now = datetime.now(KST)
        opts["end_ym"] = "{:04d}{:02d}".format(now.year, now.month)
    return opts


def install_sigint_handler():
    def handler(_signum, _frame):
        if _STOP_REQUESTED["value"]:
            print("\n[중단] 두 번째 요청 — 즉시 종료합니다.", flush=True)
            sys.exit(130)
        _STOP_REQUESTED["value"] = True
        print("\n[중단 요청] 현재 달을 마치고 안전 종료합니다. (한 번 더 누르면 즉시 종료)",
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
        months = month_range(opts["end_ym"], opts["months"])
        base_url, key = get_supabase_config()
        service_key = get_api_key()
    except (RuntimeError, ValueError) as e:
        print("[에러] {}".format(e))
        return 1
    headers = {"apikey": key, "Authorization": "Bearer {}".format(key)}
    sigungu = opts["sigungu_code"]

    if opts["retry_failed"]:
        print("--retry-failed 지정 — failed 상태를 pending으로 되돌리는 중...", flush=True)
        n = retry_failed(base_url, headers, sigungu)
        print("  되돌림: {}건 (attempts < {} 인 failed만)".format(n, RETRY_FAILED_MAX_ATTEMPTS))

    print("collect_progress 시드 중... ({}개월, 이미 있는 행은 보존)".format(len(months)),
          flush=True)
    seed_progress(base_url, headers, sigungu, months)

    pending = [(ym, at) for ym, at in fetch_pending(base_url, headers, sigungu)
               if ym in set(months)]
    counts = progress_status_counts(base_url, headers, sigungu)
    log_date = today_kst()
    baseline = read_quota_baseline(base_url, headers, log_date)
    verdict = budget_verdict(baseline, len(pending), opts["daily_budget"])

    if opts["dry_run"]:
        print_dry_run_report(sigungu, months, opts["raw_dir"], pending, counts,
                             verdict, opts["daily_budget"])
        return 0

    if not pending:
        print("처리할 pending이 없습니다 — 이미 다 걷었습니다.")
        return 0

    if opts["limit"]:
        pending = pending[:opts["limit"]]

    print("처리 대상 {:,}개월 (오늘 사용 합계 {:,}건 / 예산 {:,}건)".format(
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
        for idx, (deal_ym, attempts) in enumerate(pending, 1):
            if _STOP_REQUESTED["value"]:
                stop_reason = "사용자 중단 요청"
                break
            if baseline + session_calls >= opts["daily_budget"]:
                stop_reason = "일 예산 도달 — 내일 이어받기"
                break
            try:
                result = collect_one_month(
                    session, service_key, sigungu, deal_ym, opts["raw_dir"])
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
            save_progress(base_url, headers, sigungu, deal_ym, result, attempts)

            if idx % 20 == 0 or idx == len(pending):
                print("  진행 {:,}/{:,} ({} / 거래 {:,}건 / 누적 호출 {:,})".format(
                    idx, len(pending), deal_ym, rows_total, session_calls), flush=True)
    finally:
        flush_quota_log(base_url, headers, log_date, baseline, session_calls)

    print_run_report(processed, status_counter, session_calls,
                     time.time() - started, stop_reason, rows_total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
