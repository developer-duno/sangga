# -*- coding: utf-8 -*-
"""
건축물대장(건축HUB) API → raw JSONL 수집 (표제부 · 층별개요 · 전유공용면적)

Phase 1 ④ 건축물대장 수집. `docs/상세계획.md` §3.1(데이터 소스)·§5.1(의존순서)·
§5.6(품질 지표)과 `anthropic-skills:budongsan-data` 규격을 따른다.

무엇을 하나:
  1. Supabase `parcel` 테이블에서 대상 시군구(기본 11680=강남구)의 PNU를 전량 읽는다.
     상권정보 적재(load_sangkwon_snapshot.py)로 이미 채워진 PNU가 마스터다.
  2. PNU 하나마다 건축HUB 엔드포인트 3종을 순서대로 호출한다.
       getBrTitleInfo            표제부         -> building 재료
       getBrFlrOulnInfo          층별개요       -> unit.floor_use 재료
       getBrExposPubuseAreaInfo  전유공용면적   -> unit(호별 전용면적) 재료
     getBrExposInfo(전유부)는 area 필드가 없어 쓰지 않는다 (2026-08-07 실측 확인).
  3. 응답 원본(item)을 그대로 raw JSONL에 append 한다 (CLAUDE.md 수집 규칙:
     "raw는 절대 덮어쓰지 않는다"). 정제·매핑은 전부 다음 단계
     load_building_ledger.py 소관 — 이 스크립트는 층 정규화조차 하지 않는다.
  4. collect_progress(collector='bldrgst')로 이어받기, api_quota_log로 일 예산을
     추적한다. 예산 도달·중단 요청·쿼터 초과 응답 어느 쪽이든 현재 PNU를 마무리한
     뒤 진행 상태를 저장하고 안전 종료한다.

raw 원자성 (중복 적재 방지):
  한 PNU의 3개 엔드포인트를 전부 성공한 뒤에야 3개 파일에 한꺼번에 append 한다.
  중간에 실패하면 그 PNU는 raw에 한 줄도 남기지 않고 status='failed'로만 기록되므로,
  재실행 시 같은 PNU를 다시 받아도 raw가 이중으로 쌓이지 않는다. (그럼에도 이중
  적재가 생겼을 경우를 대비해 load_building_ledger.py가 PNU별 최신 fetched_at
  배치만 채택하는 2차 방어선을 둔다.)

이어받기 (collect_progress):
  scope_key=PNU 단위로 시드한다. 시드는 resolution=ignore-duplicates 라서 몇 번을
  다시 돌려도 이미 done 인 행을 pending 으로 되돌리지 않는다. 처리 대상은 항상
  status='pending' 인 행뿐이다.
    done     3개 엔드포인트 전부 성공 (row_count = 세 응답 아이템 수의 합)
    failed   하나라도 실패 (error_msg 기록, attempts +1)
    skipped  PNU 대지구분이 '1'(대지)·'2'(산)이 아니라 요청을 만들 수 없음

사용법:
  python scripts/collectors/collect_building_ledger.py --dry-run
  python scripts/collectors/collect_building_ledger.py --limit 20      # 파일럿
  python scripts/collectors/collect_building_ledger.py
  python scripts/collectors/collect_building_ledger.py --retry-failed  # failed를 pending으로 되돌린 뒤 이어서 수집
  python scripts/collectors/collect_building_ledger.py --sigungu-code 11440 --period-key 202609
  python scripts/collectors/collect_building_ledger.py --daily-budget-per-endpoint 8000
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

# 건축HUB (국토교통부 건축물대장정보 서비스). 2026-08-07 라이브 프로브로 확정.
API_BASE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService"

ENDPOINT_TITLE = "getBrTitleInfo"                 # 표제부
ENDPOINT_FLR_OULN = "getBrFlrOulnInfo"            # 층별개요
ENDPOINT_EXPOS_AREA = "getBrExposPubuseAreaInfo"  # 전유공용면적

# 호출 순서 = raw 파일 순서. getBrExposInfo(전유부)는 area 필드가 없어 제외(실측).
ENDPOINTS = (ENDPOINT_TITLE, ENDPOINT_FLR_OULN, ENDPOINT_EXPOS_AREA)

RAW_FILENAME = {
    ENDPOINT_TITLE: "title.jsonl",
    ENDPOINT_FLR_OULN: "flr_ouln.jsonl",
    ENDPOINT_EXPOS_AREA: "expos_area.jsonl",
}

COLLECTOR = "bldrgst"
DEFAULT_PERIOD_KEY = "202608"
DEFAULT_SIGUNGU_CODE = "11680"  # 강남구 (§0.2 파일럿)

# 한도는 총합이 아니라 "엔드포인트당 일 10,000건"이다 (2026-08-07 실측 확정 —
# getBrExposPubuseAreaInfo 단독으로 9,208콜에서 실제로 차단됨. 나머지 2종은
# 그날 5,6xx콜로 여유가 있었다). 여유를 두고 9,500으로 잡는다.
DEFAULT_DAILY_BUDGET_PER_ENDPOINT = 9_500

# failed 행을 --retry-failed로 되돌릴 때 attempts가 이 값 미만인 것만 되돌린다
# (attempts는 이미 누적되므로 계속 실패하는 PNU가 매 실행마다 무한 재시도되는
# 것을 막는 안전선).
RETRY_FAILED_MAX_ATTEMPTS = 5

NUM_OF_ROWS = 100   # 페이지당 아이템 수 (건축HUB 권장 최대치)
MAX_PAGES = 100     # 안전장치 — totalCount가 비정상적으로 크게 와도 무한루프 금지

# 전유공용면적은 페이지네이션으로 PNU당 여러 콜이 드는 경우가 많다(다수 PNU가
# 100건을 넘는 전유부를 가짐). 표제부·층별개요는 거의 항상 1콜. 예산·규모 추정에
# 쓰는 근사 배수 — 최소치가 아니라 실측(2026-08-07) 기반 근사치다.
EXPOS_CALLS_MULTIPLIER = 1.7

API_TIMEOUT_SEC = 30     # 호출당 타임아웃 (사장님 지정)
REST_TIMEOUT_SEC = 120   # Supabase(PostgREST) 타임아웃

RETRY_COUNT = 3              # 페이지 1개당 최대 시도 횟수(최초 1 + 재시도 2)
RETRY_BACKOFF_BASE_SEC = 2   # 지수 백오프 밑값 (2초, 4초)

RESULT_CODE_OK = "00"

# 쿼터 초과(포털 응답코드 22) 신호. 오늘 한도를 다 쓴 것이므로 "내일 이어받기"가 답이다.
QUOTA_EXCEEDED_TOKENS = (
    "LIMITED NUMBER OF SERVICE REQUESTS EXCEEDS",
)

# 서비스키 미등록(포털 응답코드 30) 신호. 쿼터 초과와 겉모습은 비슷하지만 원인이
# 전혀 다르다 — 활용신청이 아직 승인 안 됐거나 키가 잘못된 것이라 내일 다시 돌려도
# 똑같이 실패한다. 그래서 별도 예외로 갈라 "쿼터 소진"으로 오판하지 않게 한다.
SERVICE_KEY_ERROR_TOKENS = (
    "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
    "SERVICE KEY IS NOT REGISTERED",
)

# 위 토큰 매칭 전 정규화용 — 포털이 같은 메시지를 언더스코어/공백/하이픈 섞어
# 내려주기 때문에 영문·숫자만 남겨 비교한다 (대소문자도 무시).
_SIGNAL_STRIP_RE = re.compile(r"[^A-Z0-9]+")

# 로그·DB에 남기기 전에 지워야 하는 인증키 (URL 쿼리 형태).
_SERVICE_KEY_QUERY_RE = re.compile(r"(serviceKey=)[^&\s'\"]+", re.IGNORECASE)
SECRET_MASK = "***"

# PNU 11번째 글자(대지구분) -> 건축HUB platGbCd. 그 외 값은 요청을 만들 수 없다.
PLAT_GB_CD_MAP = {
    "1": "0",  # 대지
    "2": "1",  # 산
}

BATCH_SIZE = 1000        # PostgREST upsert 배치 크기
SELECT_PAGE_SIZE = 1000  # PostgREST select 페이지 크기

# 호출 수를 api_quota_log에 중간 기록하는 주기(콜 단위 — PNU 단위가 아니다).
# 이 수집기는 호출 수를 엔드포인트별 Counter로 다루므로 주기는 sum(session_calls.values())
# 총합을 기준으로 센다. ⛔ 예전에는 "50 PNU마다"였는데, PNU 하나가 3~10콜+(전유공용은
# 페이지네이션으로 가변)이라 유실 창의 크기가 전혀 보장되지 않았다 — 같은 50 PNU가
# 150콜일 수도 500콜일 수도 있다. 콜 총합 기준으로 세야 유실 창이 "주기(100콜) + 진행 중
# PNU 1개분"으로 묶인다. 전유 하드캡에 걸린 PNU(실측 4개 — is_truncated 주석)는 한 PNU가
# title 1 + 층별 1 + 전유 100 = 최대 ~102콜을 한 번에 더하므로 최악 상한은 ~200콜이다.
# PNU 단위 주기였다면 이 상한 자체가 없었다.
# 강제 종료 시 호출 수가 통째로 증발한 실측이 근거다(2026-08-09 브이월드: raw 10,000줄인데
# 장부는 6,952건 — 약 3,000건 유실). 유실된 만큼 같은 날 재실행의 baseline이 낮게 읽혀
# 일 예산 캡이 뚫린다. 중단·종료 시엔 항상 마지막에 한 번 더 쓴다.
QUOTA_FLUSH_EVERY = 100

# 진행 상황을 몇 PNU마다 출력할지 (기존 동작 유지 — flush 주기와 분리한다).
PROGRESS_EVERY = 50

# 시간축은 KST 고정 (환경마다 로컬 시간대가 달라지는 것 방지 — 글로벌 룰
# timezone-consistency). api_quota_log.log_date 서버 기본값(current_date, UTC)에
# 맡기지 않고 항상 KST 날짜를 명시해 넣는다.
KST = ZoneInfo("Asia/Seoul")

# 중단 요청 플래그 (SIGINT 핸들러가 세운다 — 현재 PNU를 마무리한 뒤 확인)
_SHUTDOWN = {"requested": False}


class QuotaExceededError(Exception):
    """포털 일 트래픽 초과 응답(코드 22) — 오늘은 끝, 내일 이어받기."""


class ServiceKeyError(Exception):
    """서비스키 미등록·미승인 응답(코드 30) — 내일 다시 돌려도 똑같이 실패한다.

    QuotaExceededError와 반드시 갈라놔야 한다. 쿼터 소진으로 오판하면 "내일 이어서
    하면 된다"고 잘못 보고하게 되고, 실제로 필요한 조치(포털 활용신청 승인 확인·
    키 재발급)를 며칠 늦추게 된다.
    """


class ApiError(Exception):
    """resultCode가 '00'이 아니거나 4xx — 재시도해도 같은 결과인 응답 오류."""


# ── 순수 로직 (네트워크·DB 없음 — 테스트 대상) ─────────────────────────────────


def pnu_to_params(pnu):
    """PNU 19글자 -> 건축HUB 요청 파라미터 dict.

    분해 불가면 (None, 사유문자열). 성공이면 (dict, None).

    PNU 구성 = 법정동코드(10) + 대지구분(1) + 본번(4) + 부번(4)
      sigunguCd = 앞 5글자 / bjdongCd = 그다음 5글자
      platGbCd  = 대지구분 '1'(대지)->'0', '2'(산)->'1'  (PLAT_GB_CD_MAP)
      bun / ji  = 본번 4글자 / 부번 4글자 (0 패딩 유지 — API가 그대로 받는다)
    """
    s = (pnu or "").strip()
    if len(s) != 19 or not s.isdigit():
        return None, "PNU 형식 이상(19글자 숫자 아님): {!r}".format(pnu)

    plat_gb_cd = PLAT_GB_CD_MAP.get(s[10])
    if plat_gb_cd is None:
        return None, "대지구분 코드 미지원: PNU 11번째 글자={!r}".format(s[10])

    return {
        "sigunguCd": s[0:5],
        "bjdongCd": s[5:10],
        "platGbCd": plat_gb_cd,
        "bun": s[11:15],
        "ji": s[15:19],
    }, None


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

    포털 응답은 건수에 따라 형태가 세 갈래다 (2026-08-07 실측):
      1건    items.item 이 dict        -> [dict]
      N건    items.item 이 list        -> 그대로
      0건    items 가 빈 문자열/None   -> []
    세 케이스 모두 방어한다.
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
    """totalCount로 읽어야 할 페이지 수를 구한다 (0건이면 1 — 이미 받은 그 페이지)."""
    if num_of_rows <= 0:
        raise ValueError("numOfRows는 1 이상이어야 합니다: {}".format(num_of_rows))
    if total_count <= 0:
        return 1
    pages = -(-int(total_count) // num_of_rows)  # ceil
    return min(pages, max_pages)


def is_truncated(total_count, num_of_rows=NUM_OF_ROWS, max_pages=MAX_PAGES):
    """totalCount가 MAX_PAGES x num_of_rows 상한을 넘어 클램프가 실제로 걸렸는지.

    page_count()는 안전을 위해 pages를 max_pages로 자르기만 하고 잘렸다는
    사실 자체는 알려주지 않는다 — 호출부(fetch_all_pages)가 이 함수로 별도
    확인해야 collect_progress.error_msg에 절단 경고를 남길 수 있다(실측 확정:
    전유행 10,000행 하드캡에 걸린 PNU 4개 확인됨).
    """
    if total_count <= 0:
        return False
    pages = -(-int(total_count) // num_of_rows)
    return pages > max_pages


def mask_secret(text, service_key=None):
    """문자열에서 인증키를 지운다. 로그·예외 메시지·DB 저장 전에 반드시 통과시킨다.

    왜 필요한가: requests/urllib3 예외 문자열에는 요청 URL이 통째로 들어가고, 그
    URL에는 serviceKey 쿼리가 붙어 있다. 이 문자열이 그대로 ApiError -> error_msg ->
    collect_progress.error_msg 로 흘러가면 인증키가 DB에 평문으로 박제된다.

    두 겹으로 지운다:
      1) 'serviceKey=...' 쿼리 형태 (URL이 통째로 들어온 경우)
      2) 실제 키 값 리터럴 — 원문과 URL 인코딩된 형태 둘 다 (쿼리 밖에 노출된 경우)
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
    """토큰 매칭용 정규화 — 영문·숫자만 남긴다.

    포털이 같은 뜻의 메시지를 'SERVICE_KEY_IS_NOT_REGISTERED_ERROR'로도,
    'SERVICE KEY IS NOT REGISTERED'로도 내려주기 때문에 구분자(언더스코어·공백·
    하이픈)와 대소문자 차이를 없앤 뒤 비교해야 놓치지 않는다.
    """
    return _SIGNAL_STRIP_RE.sub("", str(text).upper())


def _matches_any_token(text, tokens):
    if not text:
        return False
    normalized = _normalize_signal(text)
    return any(_normalize_signal(token) in normalized for token in tokens)


def is_quota_exceeded(text):
    """응답 본문/메시지에 쿼터 초과(코드 22) 신호가 있는지."""
    return _matches_any_token(text, QUOTA_EXCEEDED_TOKENS)


def is_service_key_error(text):
    """응답 본문/메시지에 서비스키 미등록·미승인(코드 30) 신호가 있는지."""
    return _matches_any_token(text, SERVICE_KEY_ERROR_TOKENS)


def now_kst_iso():
    """수집 시각 (KST 고정 ISO8601)."""
    return datetime.now(KST).isoformat()


def today_kst():
    """오늘 날짜 (KST 고정, 'YYYY-MM-DD')."""
    return datetime.now(KST).date().isoformat()


def default_raw_dir(period_key):
    return os.path.join(PROJECT_ROOT, "data", "raw", "bldrgst", period_key)


def raw_path(raw_dir, endpoint):
    return os.path.join(raw_dir, RAW_FILENAME[endpoint])


def append_jsonl(path, pnu, items, fetched_at):
    """items를 한 줄 = 한 아이템으로 append 한다 (덮어쓰기 금지 — 'a' 모드 고정).

    한 줄 형식: {"pnu": ..., "fetched_at": ISO8601(KST), "item": {원본 그대로}}
    반환: 실제로 쓴 줄 수.
    """
    if not items:
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fp:
        for item in items:
            fp.write(json.dumps(
                {"pnu": pnu, "fetched_at": fetched_at, "item": item},
                ensure_ascii=False,
            ) + "\n")
    return len(items)


def estimate_calls(pnu_count, endpoints=ENDPOINTS):
    """엔드포인트별 예상 호출 수(Counter).

    표제부·층별개요는 PNU당 1콜 가정(페이지네이션 거의 없음), 전유공용면적은
    실측 배수(EXPOS_CALLS_MULTIPLIER, 약 1.7배 — 다수 PNU가 100건 초과)를
    반영한 근사치다. 최소치가 아니라 근사치이므로 실제로는 더 들 수 있다.
    """
    counts = Counter()
    for e in endpoints:
        if e == ENDPOINT_EXPOS_AREA:
            counts[e] = int(pnu_count * EXPOS_CALLS_MULTIPLIER)
        else:
            counts[e] = pnu_count
    return counts


def budget_verdict(calls_used, planned_calls, budget_per_endpoint):
    """엔드포인트별 예산 판정 dict. 실행 전 안내와 --dry-run 출력에 같이 쓴다.

    calls_used/planned_calls는 둘 다 Counter(엔드포인트 -> 호출 수). 하나의
    엔드포인트라도 예산을 넘으면 전체가 넘친 것으로 본다(any/all) —
    collect_one_pnu가 PNU 하나마다 엔드포인트 3종을 원자적으로 다 써야 하므로,
    셋 중 하나만 막혀도 그 이후 PNU를 더 처리할 수 없기 때문이다.
    """
    remaining = {e: max(budget_per_endpoint - calls_used.get(e, 0), 0) for e in ENDPOINTS}
    fits = all(planned_calls.get(e, 0) <= remaining[e] for e in ENDPOINTS)
    processable_pnu = min(remaining.values()) if remaining else 0
    return {
        "calls_used": dict(calls_used),
        "planned_calls": dict(planned_calls),
        "budget_per_endpoint": budget_per_endpoint,
        "remaining": remaining,
        "fits": fits,
        "processable_pnu": processable_pnu,
    }


# ── 건축HUB 호출 ──────────────────────────────────────────────────────────────


def fetch_page(session, service_key, endpoint, params, page_no,
               retry_count=RETRY_COUNT, backoff_base=RETRY_BACKOFF_BASE_SEC,
               sleep=time.sleep):
    """엔드포인트 한 페이지를 받아 JSON(dict)을 돌려준다.

    네트워크 오류·5xx는 지수 백오프로 재시도(총 retry_count회 시도).
    쿼터 초과는 QuotaExceededError, 서비스키 미등록은 ServiceKeyError(둘 다 재시도
    안 함 — 원인이 달라 종료 보고도 갈린다), 그 외 응답 오류는 ApiError.

    이 함수가 만드는 모든 예외 문자열은 mask_secret()을 통과시킨다 — 특히
    requests 예외는 요청 URL(=serviceKey 포함)을 문자열에 담고 있다.
    """
    query = dict(params)
    query["serviceKey"] = service_key
    query["numOfRows"] = NUM_OF_ROWS
    query["pageNo"] = page_no
    query["_type"] = "json"
    url = "{}/{}".format(API_BASE_URL, endpoint)

    def clean(text):
        return mask_secret(text, service_key)

    last_err = None
    for attempt in range(1, retry_count + 1):
        try:
            r = session.get(url, params=query, timeout=API_TIMEOUT_SEC)
        except requests.RequestException as e:
            # 예외 문자열에 요청 URL(=serviceKey)이 들어 있다 — 반드시 마스킹.
            last_err = clean("네트워크 오류: {}".format(e))
        else:
            # 키·쿼터 오류는 JSON이 아니라 XML 에러 봉투로 오는 경우가 있어 본문에서 먼저 본다.
            # 키 미등록을 먼저 본다 — 더 구체적인 원인이고 조치 방법이 다르다.
            if is_service_key_error(r.text):
                raise ServiceKeyError("{} 서비스키 미등록·미승인 응답".format(endpoint))
            if is_quota_exceeded(r.text):
                raise QuotaExceededError("{} 쿼터 초과 응답".format(endpoint))
            if r.status_code >= 500:
                last_err = "HTTP {}".format(r.status_code)
            elif r.status_code >= 300:
                raise ApiError("{} HTTP {}: {}".format(
                    endpoint, r.status_code, clean(r.text[:200])))
            else:
                try:
                    payload = r.json()
                except ValueError:
                    raise ApiError("{} JSON 파싱 실패: {}".format(endpoint, clean(r.text[:200])))
                code, msg = read_result_code(payload)
                if is_service_key_error(msg):
                    raise ServiceKeyError("{} 서비스키 미등록·미승인 응답: {}".format(
                        endpoint, clean(msg)))
                if is_quota_exceeded(msg):
                    raise QuotaExceededError("{} 쿼터 초과 응답: {}".format(endpoint, clean(msg)))
                if code != RESULT_CODE_OK:
                    raise ApiError("{} resultCode={} {}".format(endpoint, code, clean(msg)))
                return payload

        if attempt < retry_count:
            sleep(backoff_base ** attempt)

    raise ApiError("{} 재시도 {}회 소진: {}".format(endpoint, retry_count, last_err))


def fetch_all_pages(session, service_key, endpoint, params, **kwargs):
    """totalCount 기준으로 끝까지 페이지를 돌아 (아이템 목록, 호출 수, 절단 여부)를 돌려준다.

    절단 여부(truncated)는 MAX_PAGES x NUM_OF_ROWS 상한에 실제로 걸렸는지를
    뜻한다 — 호출부(collect_one_pnu)가 collect_progress.error_msg에 경고를
    남기는 데 쓴다.
    """
    items = []
    calls = 0
    page_no = 1
    truncated = False
    while True:
        payload = fetch_page(session, service_key, endpoint, params, page_no, **kwargs)
        calls += 1
        items.extend(extract_items(payload))
        total_count = read_total_count(payload)
        if is_truncated(total_count):
            truncated = True
        pages = page_count(total_count)
        if page_no >= pages:
            break
        page_no += 1
    return items, calls, truncated


def collect_one_pnu(session, service_key, pnu, raw_dir, **kwargs):
    """PNU 하나의 엔드포인트 3종을 받아 raw에 append 한다.

    반환 dict: status('done'/'failed'/'skipped'), row_count, error_msg,
               calls(Counter: 엔드포인트 -> 호출 수)

    raw 원자성: 3종이 모두 성공한 뒤에야 파일에 쓴다 (중간 실패 시 raw 무기록).
    QuotaExceededError·ServiceKeyError는 잡지 않고 위로 올려보낸다 (안전 종료는
    호출부 책임 — 둘은 종료 사유가 다르다).

    error_msg는 DB(collect_progress)에 그대로 저장되므로 한 번 더 마스킹한다
    (fetch_page에서 이미 지웠더라도 이중 방어 — 인증키가 DB에 남으면 회수 불가).
    """
    calls = Counter()
    params, reason = pnu_to_params(pnu)
    if params is None:
        return {"status": "skipped", "row_count": 0, "error_msg": reason, "calls": calls}

    buffered = {}
    truncated_endpoints = []
    for endpoint in ENDPOINTS:
        try:
            items, n_calls, truncated = fetch_all_pages(
                session, service_key, endpoint, params, **kwargs)
        except (QuotaExceededError, ServiceKeyError):
            raise
        except ApiError as e:
            calls[endpoint] += 1  # 실패한 호출도 트래픽은 소모된다
            return {
                "status": "failed",
                "row_count": 0,
                "error_msg": mask_secret(e, service_key)[:500],
                "calls": calls,
            }
        calls[endpoint] += n_calls
        buffered[endpoint] = items
        if truncated:
            truncated_endpoints.append(endpoint)

    fetched_at = now_kst_iso()
    row_count = 0
    for endpoint in ENDPOINTS:
        row_count += append_jsonl(
            raw_path(raw_dir, endpoint), pnu, buffered[endpoint], fetched_at
        )
    error_msg = None
    if truncated_endpoints:
        # collect_progress.error_msg에 'truncated' 흔적을 남긴다 — status는 여전히
        # 'done'이다(3종 모두 성공은 했다). 재수집 대상 특정은 load_building_ledger.py의
        # find_truncated_pnu()가 raw 행 수로 다시 확인한다.
        error_msg = "truncated: {} ({}건/페이지 x {}페이지 상한 도달 — 일부 행 누락 가능)".format(
            ", ".join(truncated_endpoints), NUM_OF_ROWS, MAX_PAGES)
    return {"status": "done", "row_count": row_count, "error_msg": error_msg, "calls": calls}


# ── Supabase(PostgREST) ──────────────────────────────────────────────────────


def get_supabase_config():
    """env에서 URL/서비스키를 읽는다. 값은 절대 print하지 않는다."""
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    url = os.environ.get("SANGGA_SUPABASE_URL")
    key = os.environ.get("SANGGA_SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SANGGA_SUPABASE_URL / SANGGA_SUPABASE_SERVICE_KEY가 .env에 없습니다."
        )
    return url.rstrip("/"), key


def get_api_key():
    """env에서 건축HUB 서비스키를 읽는다. 값은 절대 print하지 않는다."""
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    key = os.environ.get("BLDRGST_KEY")
    if not key:
        raise RuntimeError("BLDRGST_KEY가 .env에 없습니다.")
    return key


def rest_select(base_url, headers, table, query, page_size=SELECT_PAGE_SIZE):
    """PostgREST select를 offset/limit로 끝까지 훑어 dict 목록을 돌려준다.

    PostgREST는 요청당 반환 행 수에 상한이 있으므로 한 번에 다 못 받는다 —
    12,000행대 parcel·collect_progress를 통째로 받으려면 페이지네이션이 필수다.
    """
    rows = []
    offset = 0
    while True:
        url = "{}/rest/v1/{}?{}&limit={}&offset={}".format(
            base_url, table, query, page_size, offset)
        r = requests.get(url, headers=headers, timeout=REST_TIMEOUT_SEC)
        if r.status_code >= 300:
            raise RuntimeError("{} 조회 실패 (HTTP {}): {}".format(
                table, r.status_code, r.text[:300]))
        chunk = r.json()
        if not isinstance(chunk, list):
            raise RuntimeError("{} 조회 응답 형식 이상: {!r}".format(table, str(chunk)[:200]))
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        offset += page_size
    return rows


def upsert_batch(base_url, headers, table, rows, resolution, batch_size=BATCH_SIZE):
    """rows를 batch_size 단위로 table에 upsert. 실제로 보낸 행 수를 돌려준다.

    형제 스크립트(load_sangkwon_snapshot.py)는 테이블별 고정 정책 표를 쓰지만,
    이 스크립트는 같은 collect_progress 테이블에 두 정책을 번갈아 쓴다 —
    시드는 ignore-duplicates(재실행해도 done을 pending으로 되돌리지 않음),
    결과 기록은 merge-duplicates(상태를 실제로 갱신). 그래서 정책을 인자로 받는다.
    """
    if resolution not in ("merge-duplicates", "ignore-duplicates"):
        raise ValueError("지원하지 않는 충돌 해소 정책입니다: {!r}".format(resolution))
    upsert_headers = dict(headers)
    upsert_headers["Content-Type"] = "application/json"
    upsert_headers["Prefer"] = "resolution={},return=minimal".format(resolution)

    sent = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        r = requests.post(
            "{}/rest/v1/{}".format(base_url, table),
            json=batch, headers=upsert_headers, timeout=REST_TIMEOUT_SEC,
        )
        if r.status_code >= 300:
            raise RuntimeError("{} upsert 실패 (HTTP {}): {}".format(
                table, r.status_code, r.text[:500]))
        sent += len(batch)
    return sent


def rest_count(base_url, headers, table, query):
    """PostgREST HEAD 요청으로 정확한 행 수를 돌려준다 (Content-Range 헤더)."""
    h = dict(headers)
    h["Prefer"] = "count=exact"
    r = requests.head(
        "{}/rest/v1/{}?{}".format(base_url, table, query), headers=h, timeout=60
    )
    if r.status_code not in (200, 206):
        raise RuntimeError("{} count 조회 실패 (HTTP {}): {}".format(
            table, r.status_code, r.text[:300]))
    content_range = r.headers.get("Content-Range", "")
    if "/" not in content_range:
        raise RuntimeError("{}: Content-Range 헤더 형식 이상: {!r}".format(table, content_range))
    return int(content_range.split("/")[-1])


def fetch_target_pnus(base_url, headers, sigungu_code):
    """parcel에서 대상 시군구 PNU를 전량 읽어 정렬된 목록으로 돌려준다."""
    rows = rest_select(
        base_url, headers, "parcel",
        "select=pnu&pnu=like.{}*&order=pnu".format(sigungu_code),
    )
    return [r["pnu"] for r in rows if r.get("pnu")]


def seed_progress(base_url, headers, pnus, period_key):
    """collect_progress에 PNU를 pending으로 시드한다 (ignore-duplicates).

    이미 있는 행(done/failed 포함)은 그대로 둔다 — 재실행해도 done이 리셋되지 않는다.
    """
    rows = [
        {
            "collector": COLLECTOR,
            "scope_key": pnu,
            "period_key": period_key,
            "status": "pending",
        }
        for pnu in pnus
    ]
    return upsert_batch(base_url, headers, "collect_progress", rows, "ignore-duplicates")


def fetch_pending(base_url, headers, period_key):
    """처리 대상(status='pending') PNU를 [(pnu, attempts), ...]로 돌려준다."""
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=scope_key,attempts&collector=eq.{}&period_key=eq.{}"
        "&status=eq.pending&order=scope_key".format(COLLECTOR, period_key),
    )
    return [(r["scope_key"], r.get("attempts") or 0) for r in rows]


def progress_status_counts(base_url, headers, period_key):
    """status별 행 수 (dry-run 보고용)."""
    counts = {}
    for status in ("pending", "done", "failed", "skipped"):
        counts[status] = rest_count(
            base_url, headers, "collect_progress",
            "select=scope_key&collector=eq.{}&period_key=eq.{}&status=eq.{}".format(
                COLLECTOR, period_key, status),
        )
    return counts


def build_progress_row(pnu, period_key, result, attempts):
    """collect_one_pnu 결과 -> collect_progress upsert 행."""
    return {
        "collector": COLLECTOR,
        "scope_key": pnu,
        "period_key": period_key,
        "status": result["status"],
        "row_count": result["row_count"],
        "error_msg": result["error_msg"],
        "attempts": attempts + 1,
        "updated_at": now_kst_iso(),
    }


def save_progress(base_url, headers, row):
    return upsert_batch(base_url, headers, "collect_progress", [row], "merge-duplicates")


def retry_failed(base_url, headers, period_key, max_attempts=RETRY_FAILED_MAX_ATTEMPTS):
    """failed 상태를 pending으로 되돌린다 (attempts < max_attempts 인 것만).

    attempts는 이미 누적되므로 이 문턱을 넘은 행은 되돌리지 않는다 — 계속
    실패하는(예: 그 PNU 자체가 API에서 영구히 오류를 내는) 행이 매 실행마다
    무한히 재시도되는 것을 막는 안전선이다. 되돌린 행 수를 반환한다.
    """
    url = ("{}/rest/v1/collect_progress?collector=eq.{}&period_key=eq.{}"
           "&status=eq.failed&attempts=lt.{}").format(
        base_url, COLLECTOR, period_key, max_attempts)
    h = dict(headers)
    h["Content-Type"] = "application/json"
    h["Prefer"] = "return=representation"
    try:
        r = requests.patch(url, json={"status": "pending"}, headers=h, timeout=REST_TIMEOUT_SEC)
    except requests.RequestException as e:
        raise RuntimeError("failed -> pending 되돌리기 중 네트워크 오류: {}".format(e))
    if r.status_code >= 300:
        raise RuntimeError("failed -> pending 되돌리기 실패 (HTTP {}): {}".format(
            r.status_code, r.text[:300]))
    body = r.json()
    return len(body) if isinstance(body, list) else 0


def read_quota_baseline(base_url, headers, log_date):
    """오늘(KST) 이미 기록된 엔드포인트별 누적 호출 수."""
    rows = rest_select(
        base_url, headers, "api_quota_log",
        "select=api_name,call_count&log_date=eq.{}&collector=eq.{}".format(log_date, COLLECTOR),
    )
    return {r["api_name"]: (r.get("call_count") or 0) for r in rows}


def flush_quota_log(base_url, headers, log_date, baseline, session_calls):
    """baseline + 이번 실행 누적을 api_quota_log에 반영한다 (merge-duplicates)."""
    rows = [
        {
            "log_date": log_date,
            "collector": COLLECTOR,
            "api_name": api_name,
            "call_count": baseline.get(api_name, 0) + n,
        }
        for api_name, n in sorted(session_calls.items()) if n
    ]
    if not rows:
        return 0
    return upsert_batch(base_url, headers, "api_quota_log", rows, "merge-duplicates")


def maybe_flush_quota_log(base_url, headers, log_date, baseline, session_calls,
                          last_flushed_calls, every=QUOTA_FLUSH_EVERY):
    """호출 수를 주기적으로(기본 100콜마다) 장부에 미리 적는다. 새 '마지막 기록 시점'을 돌려준다.

    session_calls는 엔드포인트별 Counter라 주기는 총합(sum)으로 센다. upsert가
    엔드포인트마다 `call_count = baseline + 누적`을 merge-duplicates로 덮어쓰므로
    중간에 몇 번을 적어도 값은 단조 증가한다 — 같은 호출을 두 번 세지 않는다.

    실패해도 수집을 죽이지 않는다. 기록은 안전장치일 뿐이라 그것 때문에 몇 시간짜리
    수집이 멈추면 손해가 더 크다. 대신 **조용히 넘어가지 않는다** — 경고를 찍고
    last_flushed_calls를 그대로 돌려줘 다음 PNU에서 곧바로 다시 시도한다(PR #32의
    교훈: 침묵하는 실패가 가장 위험하다). 그래서 유실 창은 최대 1 PNU다
    (콜로는 최대 ~200콜 — 전유 하드캡 대형 PNU 1개가 ~102콜을 한 번에 더할 수 있다).
    """
    total = sum(session_calls.values())
    if total - last_flushed_calls < every:
        return last_flushed_calls
    try:
        flush_quota_log(base_url, headers, log_date, baseline, session_calls)
    except Exception as e:   # noqa: BLE001 — 어떤 이유든 수집은 계속돼야 한다
        print("  [경고] 호출 수 중간 기록 실패 (수집은 계속합니다): {}".format(e), flush=True)
        return last_flushed_calls
    return total


# ── 보고 출력 ────────────────────────────────────────────────────────────────


def print_dry_run_report(sigungu_code, period_key, raw_dir, pnu_count,
                         status_counts, verdict, limit):
    print("=" * 78)
    print("건축물대장(건축HUB) 수집 — DRY RUN (API 0콜, DB 읽기만)")
    print("=" * 78)
    print("대상 시군구 : {}".format(sigungu_code))
    print("기간 키     : {}".format(period_key))
    print("raw 저장 위치: {}".format(raw_dir))
    print("엔드포인트  : {}".format(", ".join(ENDPOINTS)))
    print("")
    print("[ 대상 PNU (parcel) ] {:,}개".format(pnu_count))
    print("[ collect_progress 현황 ]")
    total_progress = sum(status_counts.values())
    for status in ("pending", "done", "failed", "skipped"):
        print("    {:<8} {:>8,}행".format(status, status_counts[status]))
    print("    {:<8} {:>8,}행".format("합계", total_progress))
    not_seeded = max(pnu_count - total_progress, 0)
    if not_seeded:
        print("    (아직 시드 안 된 PNU {:,}개 — 실제 실행 시 pending으로 시드됨)".format(
            not_seeded))

    to_process = status_counts["pending"] + not_seeded
    if limit is not None:
        to_process = min(to_process, limit)
        print("    --limit {} 적용 -> 이번 실행 처리 대상 {:,}개".format(limit, to_process))

    print("")
    print("[ 예상 호출 수 ] (엔드포인트별 — 전유공용면적은 실측 배수 x{} 반영 근사치)".format(
        EXPOS_CALLS_MULTIPLIER))
    for e in ENDPOINTS:
        print("    {:<26} {:>10,}건".format(e, verdict["planned_calls"].get(e, 0)))
    print("    {:<26} {:>10,}건".format("합계", sum(verdict["planned_calls"].values())))
    print("")
    print("[ 일 예산 판정 ] (엔드포인트별, api_quota_log 기준 오늘 KST)")
    print("    엔드포인트별 예산: {:,}건".format(verdict["budget_per_endpoint"]))
    for e in ENDPOINTS:
        print("    {:<26} 사용 {:>8,}건 / 잔여 {:>8,}건".format(
            e, verdict["calls_used"].get(e, 0), verdict["remaining"][e]))
    print("    처리 가능 PNU(잔여 최소 엔드포인트 기준): {:,}개".format(verdict["processable_pnu"]))
    print("    판정        : {}".format(
        "예산 이내 — 1회 실행으로 완결 가능" if verdict["fits"]
        else "예산 초과 — 이어받기로 분할 필요"))
    print("=" * 78)


def print_run_report(processed, status_counter, session_calls, elapsed_sec, stop_reason):
    print("")
    print("=" * 78)
    print("수집 종료 — 처리 {:,}개 PNU / {:.1f}분 소요".format(processed, elapsed_sec / 60.0))
    print("=" * 78)
    print("[ 상태별 ]")
    for status in ("done", "failed", "skipped"):
        print("    {:<8} {:>8,}개".format(status, status_counter[status]))
    print("[ 엔드포인트별 호출 수 ]")
    for endpoint in ENDPOINTS:
        print("    {:<26} {:>8,}건".format(endpoint, session_calls[endpoint]))
    print("    {:<26} {:>8,}건".format("합계", sum(session_calls.values())))
    print("[ 종료 사유 ] {}".format(stop_reason))
    print("=" * 78)


# ── 메인 ──────────────────────────────────────────────────────────────────────


def _reject_unknown_args(argv, bool_flags, value_flags):
    """모르는 인자를 만나면 즉시 멈춘다.

    왜: 예전에는 인식 못 하는 인자를 조용히 무시하고 실행을 계속했다. 그래서
    `--help` 를 붙이면 dry_run=False 인 **실제 실행**이 되어 라이브 DB 쓰기가
    나갔고(2026-08-08 실제 발생), `--dryrun`·`--limitt 50` 같은 오타는
    "소량 시험"이 "전량 실행"으로 바뀐다. 조용한 오작동보다 시끄러운 중단이 낫다.
    """
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in value_flags:
            i += 2          # 값 하나를 건너뛴다 (값 누락은 기존 검사가 잡는다)
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
        value_flags=("--sigungu-code", "--period-key", "--daily-budget-per-endpoint", "--limit"),
    )
    opts = {
        "sigungu_code": DEFAULT_SIGUNGU_CODE,
        "period_key": DEFAULT_PERIOD_KEY,
        "daily_budget_per_endpoint": DEFAULT_DAILY_BUDGET_PER_ENDPOINT,
        "limit": None,
        "dry_run": "--dry-run" in argv,
        "retry_failed": "--retry-failed" in argv,
    }
    for flag, key, cast in (
        ("--sigungu-code", "sigungu_code", str),
        ("--period-key", "period_key", str),
        ("--daily-budget-per-endpoint", "daily_budget_per_endpoint", int),
        ("--limit", "limit", int),
    ):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise ValueError("{} 뒤에 값이 필요합니다.".format(flag))
            try:
                opts[key] = cast(argv[i + 1])
            except ValueError:
                raise ValueError("{} 값이 올바르지 않습니다: {!r}".format(flag, argv[i + 1]))
    if opts["limit"] is not None and opts["limit"] <= 0:
        raise ValueError("--limit 은 1 이상이어야 합니다.")
    if opts["daily_budget_per_endpoint"] <= 0:
        raise ValueError("--daily-budget-per-endpoint 은 1 이상이어야 합니다.")
    return opts


def install_sigint_handler():
    """Ctrl+C를 받으면 즉시 죽지 않고 현재 PNU를 마무리한 뒤 종료하도록 플래그만 세운다."""
    def handler(_signum, _frame):
        if _SHUTDOWN["requested"]:
            return
        _SHUTDOWN["requested"] = True
        print("\n[중단 요청] 현재 PNU를 마무리하고 진행 상태를 저장한 뒤 종료합니다...",
              flush=True)
    signal.signal(signal.SIGINT, handler)


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

    period_key = opts["period_key"]
    raw_dir = default_raw_dir(period_key)

    try:
        base_url, service_role_key = get_supabase_config()
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1
    headers = {
        "apikey": service_role_key,
        "Authorization": "Bearer {}".format(service_role_key),
    }

    log_date = today_kst()
    print("대상 PNU 조회 중... (parcel, 시군구={})".format(opts["sigungu_code"]), flush=True)
    try:
        pnus = fetch_target_pnus(base_url, headers, opts["sigungu_code"])
        status_counts = progress_status_counts(base_url, headers, period_key)
        baseline = read_quota_baseline(base_url, headers, log_date)
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1

    if not pnus:
        print("[에러] parcel에 대상 PNU가 없습니다. --sigungu-code를 확인하세요 "
              "(상권정보 적재가 선행돼야 합니다).")
        return 1

    calls_used = Counter(baseline)

    if opts["dry_run"]:
        not_seeded = max(len(pnus) - sum(status_counts.values()), 0)
        to_process = status_counts["pending"] + not_seeded
        if opts["limit"] is not None:
            to_process = min(to_process, opts["limit"])
        verdict = budget_verdict(
            calls_used, estimate_calls(to_process), opts["daily_budget_per_endpoint"])
        print_dry_run_report(opts["sigungu_code"], period_key, raw_dir, len(pnus),
                             status_counts, verdict, opts["limit"])
        print("")
        print("--dry-run 지정 — API 호출·DB 쓰기를 건너뜁니다.")
        return 0

    try:
        api_key = get_api_key()
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1

    if opts["retry_failed"]:
        print("--retry-failed 지정 — failed 상태를 pending으로 되돌리는 중...", flush=True)
        try:
            reverted = retry_failed(base_url, headers, period_key)
        except RuntimeError as e:
            print("[에러] {}".format(e))
            return 1
        print("  되돌림: {:,}건 (attempts < {} 인 failed만)".format(
            reverted, RETRY_FAILED_MAX_ATTEMPTS), flush=True)

    print("collect_progress 시드 중... (PNU {:,}개, 이미 있는 행은 보존)".format(len(pnus)),
          flush=True)
    try:
        seed_progress(base_url, headers, pnus, period_key)
        pending = fetch_pending(base_url, headers, period_key)
    except RuntimeError as e:
        # api_key가 이미 메모리에 있는 구간 — 이후 이 자리에 키를 실은 호출이
        # 추가되더라도 새지 않도록 마스킹을 기본으로 깔아둔다.
        print("[에러] {}".format(mask_secret(e, api_key)))
        return 1

    if opts["limit"] is not None:
        pending = pending[:opts["limit"]]
    if not pending:
        print("처리할 pending PNU가 없습니다 — 이미 전량 완료 상태입니다.")
        return 0

    budget_per_endpoint = opts["daily_budget_per_endpoint"]
    print("처리 대상 {:,}개 PNU (오늘 사용 합계 {:,}건 / 엔드포인트별 예산 {:,}건)".format(
        len(pending), sum(calls_used.values()), budget_per_endpoint), flush=True)

    install_sigint_handler()
    session = requests.Session()
    session_calls = Counter({e: 0 for e in ENDPOINTS})
    status_counter = Counter({"done": 0, "failed": 0, "skipped": 0})
    started = time.time()
    processed = 0
    stop_reason = "전량 처리 완료"
    exit_code = 0
    last_flushed_calls = 0   # 호출 수를 장부에 마지막으로 적은 시점(주기 flush용)

    try:
        for pnu, attempts in pending:
            if _SHUTDOWN["requested"]:
                stop_reason = "사용자 중단 요청(SIGINT)"
                break
            if any(calls_used[e] >= budget_per_endpoint for e in ENDPOINTS):
                stop_reason = "일 예산 도달(엔드포인트별) — 다음 실행에서 이어받기"
                break

            try:
                result = collect_one_pnu(session, api_key, pnu, raw_dir)
            except QuotaExceededError as e:
                stop_reason = "포털 일 트래픽 초과 — 안전 종료. 내일 다시 실행하면 이어받는다 ({})".format(
                    mask_secret(e, api_key))
                break
            except ServiceKeyError as e:
                # 쿼터 소진과 절대 섞어 보고하지 않는다 — 기다린다고 풀리지 않는다.
                stop_reason = (
                    "서비스키 미등록·미승인 — 안전 종료. 기다려도 풀리지 않는다: "
                    "공공데이터포털에서 건축HUB 활용신청 승인 상태와 BLDRGST_KEY 등록/재발급을 "
                    "확인해야 한다 ({})".format(mask_secret(e, api_key))
                )
                exit_code = 1
                break

            session_calls.update(result["calls"])
            calls_used.update(result["calls"])
            status_counter[result["status"]] += 1
            processed += 1

            try:
                save_progress(base_url, headers,
                              build_progress_row(pnu, period_key, result, attempts))
            except RuntimeError as e:
                stop_reason = "진행 상태 저장 실패 — 중단 ({})".format(mask_secret(e, api_key))
                exit_code = 1
                break

            last_flushed_calls = maybe_flush_quota_log(
                base_url, headers, log_date, baseline, session_calls, last_flushed_calls)

            if processed % PROGRESS_EVERY == 0:
                print("  진행 {:,}/{:,} (done {:,} / failed {:,} / skipped {:,}, 누적 호출 {:,}건)".format(
                    processed, len(pending), status_counter["done"], status_counter["failed"],
                    status_counter["skipped"], sum(calls_used.values())), flush=True)
    finally:
        # 루프가 어떤 이유로 죽든(위에서 안 잡는 OSError·KeyError 등) 마지막 기록은 남긴다.
        # 이게 없으면 미분류 예외 경로에서 최대 주기(100콜)+진행 중 PNU 1개분이 통째로
        # 증발한다 — 이 수집기가 막으려던 바로 그 유형이다(적대검증 발견, 2026-08-09).
        try:
            flush_quota_log(base_url, headers, log_date, baseline, session_calls)
        except Exception as e:   # noqa: BLE001 — 마지막 기록 실패로 보고까지 죽이지 않는다
            print("[경고] 종료 시 api_quota_log 기록 실패: {}".format(mask_secret(e, api_key)))

    print_run_report(processed, status_counter, session_calls, time.time() - started, stop_reason)
    if status_counter["failed"]:
        print("failed {:,}개는 collect_progress에 남아 있습니다 — "
              "status를 'pending'으로 되돌리면 재시도됩니다.".format(status_counter["failed"]))
    print("다음 단계: python scripts/collectors/load_building_ledger.py --dry-run")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
