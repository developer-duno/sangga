# -*- coding: utf-8 -*-
"""브이월드 토지특성정보 API → raw JSONL 수집 (필지 단위)

`docs/상세계획.md` §1.2(브이월드 API 스펙 박스)에서 라이브 실호출로 확정한 스펙을
그대로 쓴다. 이어받기·일 예산·안전 종료·raw 원자성 구조는
`collect_building_ledger.py`(필지 단위 scope_key)와 `collect_rone.py`를 답습한다.
새로 발명한 패턴은 없다.

무엇을 하나:
  1. parcel 테이블의 PNU를 collect_progress에 pending으로 시드한다
     (collector='vworld_land', scope_key=PNU, period_key=수집 회차 'YYYYMM').
  2. PNU 하나마다 getLandCharacteristics를 1콜 호출해 응답 행을 그대로 raw JSONL에
     append 한다. 최신 행 선택·parcel 갱신은 전부 load_vworld_land.py 소관 —
     이 스크립트는 아무것도 해석하지 않는다(raw는 절대 덮어쓰지 않는다).
  3. api_quota_log로 일 예산을 추적하고, 예산 도달·중단 요청 어느 쪽이든 현재
     PNU를 마무리한 뒤 진행 상태를 저장하고 안전 종료한다.

⚠️ 다른 수집기와 다른 점 — 복사할 때 반드시 확인:
  - **`domain` 파라미터가 필수다.** 키에 등록된 서비스 URL과 일치해야 하며, 안 맞으면
    `resultCode=INCORRECT_KEY`가 온다. **권한 오류처럼 보이지만 도메인 불일치다**
    (2026-08-09 실측: localhost 계열 6종 전부 실패 → 등록값으로 즉시 통과).
  - **성공일 때 `resultCode`가 빈 문자열이다.** MOLIT의 '00'·R-ONE의 'INFO-000'과
    다르다 — 코드값이 있으면 오히려 오류다. 성공 판정은 코드가 아니라 응답 형태로 한다.
  - **1콜이면 그 필지의 전 연도가 다 온다**(2013~2026, 표본 3필지 전부 totalCount=18).
    numOfRows=100이면 페이징이 필요 없다 → 필지당 1콜로 설계한다.
  - **같은 연도에 행이 여러 개 온다**(2023x2·2024x2·2025x3 실측). `ladSn`은 전 행이
    999999라 판별자가 못 된다 — 구분되는 값은 `lastUpdtDt`뿐이다.

사용법:
  python scripts/collectors/collect_vworld_land.py --dry-run
  python scripts/collectors/collect_vworld_land.py --limit 50
  python scripts/collectors/collect_vworld_land.py
  python scripts/collectors/collect_vworld_land.py --retry-failed
"""

import argparse
import json
import os
import re
import signal
import sys
import time
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

# ── 설정 ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 브이월드 국가중점데이터(구 NSDI — 2024-01-01 폐쇄, 기능 통합).
# `docs/상세계획.md` §1.2 브이월드 박스가 정본 — 다시 조사하지 말 것.
API_BASE_URL = "https://api.vworld.kr/ned/data"
ENDPOINT = "getLandCharacteristics"

COLLECTOR = "vworld_land"
RAW_SUBDIR = "vworld_land"

# ⛔ 키에 등록된 서비스 URL. 호출 시 domain이 이 값과 맞아야 한다(호스트 수준이면 통과).
# 콘솔 [오픈API > 인증키관리]에서 서비스URL을 바꾸면 이 상수도 함께 바꿔야 한다.
# .env의 VWORLD_DOMAIN으로 덮어쓸 수 있다(레포를 옮기거나 URL을 바꿀 때 코드 수정 없이).
DEFAULT_DOMAIN = "https://github.com/developer-duno/sangga"

# 필지당 전 연도가 1콜에 다 오므로 페이징이 필요 없다(실측 totalCount=18).
# 100이면 어떤 필지든 한 번에 덮는다 — 넘치면 is_truncated가 잡아 경고한다.
NUM_OF_ROWS = 100

# 공식 문서에 ned/data 계열 일일 한도가 명시돼 있지 않다(콘솔은 지오코딩 40,000건/일만
# 표시하고 국가중점 계열 계기판이 없다 — 2026-08-09 확인). 남의 수치를 베끼지 않고
# 보수적으로 시작한다: 강남 12,274필지를 3일에 나눠 받는 속도다. 쿼터 초과가 한 번도
# 관측되지 않으면 이 상수만 올리면 된다(이어받기가 이미 있어 중단·재개가 안전하다).
DEFAULT_DAILY_BUDGET = 5_000

API_TIMEOUT_SEC = 30
REST_TIMEOUT_SEC = 120

RETRY_COUNT = 3
RETRY_BACKOFF_BASE_SEC = 2
RETRY_FAILED_MAX_ATTEMPTS = 5

# 호출 간 최소 간격(초). 한도가 미확정이라 서버에 부담을 주지 않도록 둔다.
# 형제 레포(naver-estate-web/crawler/public_data_base.py)가 공공데이터 API에 쓰는
# 0.3초를 그대로 답습한다 — 임의로 더 짧게 잡는 것보다 검증된 값이 낫다.
# 일 예산 5,000건 기준 약 25분이면 끝난다.
SLEEP_BETWEEN_CALLS_SEC = 0.3

# 설정이 틀린 것이라 내일 다시 돌려도 똑같이 실패한다 — 즉시 멈추고 사람에게 알린다.
CONFIG_ERROR_CODES = ("INCORRECT_KEY", "NOT_EXISTS_KEY", "UNAUTHENTICATED_KEY", "INVALID_KEY")

# 오류가 아닌 resultCode 값. getLandCharacteristics는 성공 시 **빈 문자열**을 주지만
# (2026-08-09 실측), 같은 ned/data 계열의 getEBOfficeInfo는 'NORMAL_SERVICE'를 준다
# (형제 레포 naver-estate-web/crawler/vworld_client.py 실측). 오퍼레이션마다 다르므로
# "코드가 있으면 오류"로 단정하면 안 된다 — 아래 fetch_land는 행 존재를 우선 본다.
OK_RESULT_CODES = ("", "NORMAL_SERVICE")

BATCH_SIZE = 1000
SELECT_PAGE_SIZE = 1000

KST = ZoneInfo("Asia/Seoul")

_SERVICE_KEY_QUERY_RE = re.compile(r"([?&]key=)[^&\s'\"]+", re.IGNORECASE)
SECRET_MASK = "***"

_STOP_REQUESTED = {"value": False}


class ConfigError(Exception):
    """인증키·도메인 등 설정 오류 — 재시도해도 똑같이 실패한다."""


class ApiError(Exception):
    """그 외 API 오류 — 재시도 대상."""


# ── 순수 로직 (네트워크·DB 없음 — 테스트 대상) ─────────────────────────────────


def mask_secret(text, key=None):
    """로그·에러 메시지에서 인증키를 가린다.

    쿼리 파라미터 위치(`?key=`·`&key=`)만 지운다 — 다른 파라미터 이름 안의 우연한
    부분일치(예: `monkey=`)를 건드리지 않기 위해서다.
    """
    s = "" if text is None else str(text)
    if key:
        s = s.replace(str(key), SECRET_MASK)
    return _SERVICE_KEY_QUERY_RE.sub(r"\1" + SECRET_MASK, s)


def envelope(payload):
    """응답의 봉투(dict)를 꺼낸다. 봉투 이름은 `landCharacteristicss`(s 두 개)다.

    이름을 하드코딩하지 않고 "최상위 키가 하나뿐인 dict"에서 꺼낸다 — 다른 ned/data
    오퍼레이션도 같은 모양이라 이 함수를 그대로 재사용할 수 있고, 브이월드가 봉투
    이름을 바꿔도(오타 수정 등) 깨지지 않는다.
    """
    if not isinstance(payload, dict) or len(payload) != 1:
        return None
    inner = next(iter(payload.values()))
    return inner if isinstance(inner, dict) else None


def read_result_code(payload):
    """(resultCode, resultMsg)를 돌려준다. 봉투가 이상하면 ('', '').

    ⚠️ **정상 응답에서 resultCode는 빈 문자열이다**(2026-08-09 실측). 코드가 채워져
    있으면 오히려 오류라는 뜻 — MOLIT('00')·R-ONE('INFO-000')과 정반대다.
    """
    env = envelope(payload)
    if env is None:
        return "", ""
    return str(env.get("resultCode") or "").strip(), str(env.get("resultMsg") or "").strip()


def extract_rows(payload):
    """봉투 안 `field`를 행 리스트로 돌려준다. 없으면 빈 리스트.

    ⛔ **행이 1개일 때 `field`가 리스트가 아니라 dict로 온다.** 리스트만 받으면 그
    필지가 통째로 빈 결과가 되어 **에러 없이 조용히 누락**된다. 형제 레포
    `naver-estate-web/backend/crawler/vworld_client.py`가 같은 브이월드 API에서 이미
    이 방어를 하고 있어(`if isinstance(fields, dict): fields = [fields]`) 그대로 답습한다.
    우리 실측 표본(강남 3필지)은 전부 18행이라 이 경우를 못 봤다 — 표본으로 못 본 것을
    "없다"고 단정하지 않는다.
    """
    env = envelope(payload)
    if env is None:
        return []
    rows = env.get("field")
    if isinstance(rows, dict):
        return [rows]
    return rows if isinstance(rows, list) else []


def read_total_count(payload):
    """봉투의 totalCount를 int로. 없거나 숫자가 아니면 None."""
    env = envelope(payload)
    if env is None:
        return None
    try:
        return int(str(env.get("totalCount")).strip())
    except (TypeError, ValueError):
        return None


def is_config_error(code):
    """설정 오류(키·도메인)인가. 대소문자·공백 차이를 흡수한다."""
    c = str(code or "").strip().upper()
    return bool(c) and c in CONFIG_ERROR_CODES


def is_ok_code(code):
    """오류가 아닌 resultCode인가(빈 값 또는 NORMAL_SERVICE)."""
    return str(code or "").strip().upper() in OK_RESULT_CODES


def is_truncated(total_count, num_of_rows=NUM_OF_ROWS):
    """한 번의 호출로 다 못 받은 필지인가(페이징이 필요한가).

    지금까지 실측한 최대 totalCount는 18이라 걸릴 일이 없지만, 조용히 잘리는 것이
    가장 위험하므로(건축HUB numOfRows 사고와 같은 결) 명시적으로 감시한다.
    """
    if total_count is None:
        return False
    return int(total_count) > int(num_of_rows)


def pick_latest_row(rows):
    """같은 필지의 여러 행 중 '지금의 값' 1행을 고른다.

    규칙: `stdrYear` 최대 → 그 안에서 `lastUpdtDt` 최대.

    ⚠️ `ladSn`으로 고르면 안 된다 — 실측상 전 행이 `999999`라 판별자가 못 된다
    (직전 세션 메모의 "ladSn으로 최신 1행" 지침은 틀렸다). 실제로 구분되는 값은
    `lastUpdtDt`뿐이다. 같은 연도에 행이 2~3개씩 오므로(2023x2·2024x2·2025x3 실측)
    이 규칙 없이 적재하면 같은 필지가 여러 번 반영된다.
    """
    if not rows:
        return None

    def sort_key(r):
        year = str(r.get("stdrYear") or "").strip()
        upd = str(r.get("lastUpdtDt") or "").strip()
        # 연도가 비었으면 가장 옛것으로 취급한다(정상 행에 밀리게).
        return (year if year.isdigit() else "", upd)

    return max(rows, key=sort_key)


def now_kst_iso():
    return datetime.now(KST).isoformat()


def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def current_period_key(now=None):
    """수집 회차 키 'YYYYMM'. 토지특성은 반기 갱신이라 회차만 구분하면 된다."""
    return (now or datetime.now(KST)).strftime("%Y%m")


def default_raw_dir(period_key):
    return os.path.join(PROJECT_ROOT, "data", "raw", RAW_SUBDIR, period_key)


def raw_path(raw_dir):
    return os.path.join(raw_dir, "land_characteristics.jsonl")


def append_jsonl(path, pnu, rows, fetched_at):
    """raw 한 줄 = 한 필지의 응답 전체. 해석하지 않고 그대로 남긴다.

    한 줄을 통째로 만들어 한 번에 write 한다 — 중간에 죽어도 반 줄이 남지 않는다.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps({"pnu": pnu, "fetched_at": fetched_at, "rows": rows},
                      ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
    return 1


def budget_verdict(calls_used, planned_calls, budget):
    """오늘 남은 예산으로 계획한 호출이 다 들어가나."""
    remaining = max(0, int(budget) - int(calls_used))
    planned = int(planned_calls)
    return {
        "remaining": remaining,
        "planned": planned,
        "fits": planned <= remaining,
        "shortfall": max(0, planned - remaining),
    }


# ── 네트워크 ─────────────────────────────────────────────────────────────────


def fetch_land(session, key, pnu, domain, call_counter=None, sleep_sec=SLEEP_BETWEEN_CALLS_SEC):
    """PNU 1개의 토지특성을 받는다(1콜). 성공하면 (rows, total_count).

    5xx·네트워크 오류만 재시도한다. 설정 오류(키·도메인)는 재시도해도 같으므로
    ConfigError로 즉시 올린다.

    ⚠️ 재시도가 실제로 나가는 요청도 호출로 세어야 우리 장부가 포털 집계와 덜 어긋난다
    (건축물대장 수집에서 드리프트로 확인된 함정 — PROGRESS.md '다음 단계' 1번).
    """
    params = {
        "key": key, "domain": domain, "pnu": pnu,
        "format": "json", "numOfRows": NUM_OF_ROWS, "pageNo": 1,
    }
    last_err = None
    for attempt in range(RETRY_COUNT):
        if call_counter is not None:
            call_counter["calls"] += 1
        try:
            r = session.get("{}/{}".format(API_BASE_URL, ENDPOINT),
                            params=params, timeout=API_TIMEOUT_SEC)
        except requests.RequestException as e:
            last_err = "요청 실패: {}".format(type(e).__name__)
        else:
            if r.status_code == 429:
                # 한도가 미확정이라 429가 언제 오는지 모른다. 형제 레포
                # (naver-estate-web/crawler/public_data_base.py)가 공공데이터 API에서
                # 쓰는 방식대로 점진 대기 후 재시도한다 — 실패로 처리하면 그 필지가
                # 억울하게 failed로 남는다.
                last_err = "HTTP 429 (호출 제한)"
            elif r.status_code >= 500:
                last_err = "HTTP {}".format(r.status_code)
            elif r.status_code >= 400:
                raise ApiError("HTTP {}: {}".format(
                    r.status_code, mask_secret(r.text[:200], key)))
            else:
                try:
                    payload = r.json()
                except ValueError:
                    raise ApiError("JSON 아님: {}".format(
                        mask_secret(r.text[:200], key)))
                code, msg = read_result_code(payload)
                rows = extract_rows(payload)
                # 행이 왔으면 코드와 무관하게 성공이다 — 오퍼레이션마다 성공 코드가
                # 달라(빈 값 / NORMAL_SERVICE) 코드로 판정하면 언젠가 전량 실패한다.
                if not rows:
                    if is_config_error(code):
                        raise ConfigError(
                            "{} — {}. 인증키 또는 domain('{}')이 콘솔 등록값과 다릅니다. "
                            "브이월드 [오픈API > 인증키관리]의 서비스URL을 확인하세요.".format(
                                code, msg or "메시지 없음", domain))
                    if not is_ok_code(code):
                        raise ApiError("{} — {}".format(code, msg or "메시지 없음"))
                if sleep_sec:
                    time.sleep(sleep_sec)
                return rows, read_total_count(payload)
        if attempt < RETRY_COUNT - 1:
            time.sleep(RETRY_BACKOFF_BASE_SEC * (2 ** attempt))
    raise ApiError(last_err or "알 수 없는 오류")


def collect_one(session, key, pnu, domain, raw_dir, call_counter=None,
                sleep_sec=SLEEP_BETWEEN_CALLS_SEC):
    """PNU 하나를 받아 raw에 적는다. 진행 상태로 쓸 dict를 돌려준다.

    행이 0건인 것은 실패가 아니다 — 그 필지의 토지특성이 아직 없을 수 있다.
    'skipped'로 남겨 다음 회차에 다시 묻지 않게 하되, 실패로 세지도 않는다.
    """
    rows, total = fetch_land(session, key, pnu, domain,
                             call_counter=call_counter, sleep_sec=sleep_sec)
    if not rows:
        return {"status": "skipped", "row_count": 0,
                "error_msg": "응답에 행 없음(토지특성 미보유 필지)"}
    append_jsonl(raw_path(raw_dir), pnu, rows, now_kst_iso())
    result = {"status": "done", "row_count": len(rows), "error_msg": None}
    if is_truncated(total):
        # 지금까지 관측된 적 없지만, 조용히 잘리면 값이 통째로 낡는다.
        result["error_msg"] = "절단 의심: totalCount={} > numOfRows={}".format(
            total, NUM_OF_ROWS)
    return result


# ── DB (Supabase REST) ───────────────────────────────────────────────────────


def get_supabase_config():
    load_dotenv()
    url = os.environ.get("SANGGA_SUPABASE_URL", "").strip().rstrip("/")
    key = (os.environ.get("SANGGA_SUPABASE_SERVICE_KEY")
           or os.environ.get("SANGGA_SUPABASE_ANON_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError(".env에 SANGGA_SUPABASE_URL과 키(SERVICE 또는 ANON)가 필요합니다.")
    return url, key


def get_api_key():
    """브이월드 인증키. 이 레포는 `VWORLD_KEY`를 쓴다.

    ⚠️ 형제 레포 naver-estate-web은 같은 값을 **`VWORLD_API_KEY`**라는 이름으로 쓴다
    (키 자체는 서로 다른 별도 발급분이다). 한 PC에서 두 레포를 오가다 이름을 헷갈려
    ".env에 넣었는데 왜 안 되지"로 헤매기 쉬워, 그 이름도 폴백으로 받아준다.
    """
    load_dotenv()
    key = (os.environ.get("VWORLD_KEY", "").strip()
           or os.environ.get("VWORLD_API_KEY", "").strip())
    if not key:
        raise RuntimeError(
            ".env에 VWORLD_KEY(브이월드 인증키)가 필요합니다. "
            "(naver-estate-web 관행인 VWORLD_API_KEY 이름도 받습니다)")
    return key


def get_domain():
    load_dotenv()
    return (os.environ.get("VWORLD_DOMAIN", "").strip() or DEFAULT_DOMAIN)


def rest_select(base_url, headers, table, query, page_size=SELECT_PAGE_SIZE, order="pnu"):
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


def fetch_target_pnus(base_url, headers, sigungu_code=None):
    """parcel에서 대상 PNU를 가져온다(시군구로 좁힐 수 있다)."""
    query = "select=pnu"
    if sigungu_code:
        query += "&sigungu_code=eq.{}".format(sigungu_code)
    return [r["pnu"] for r in rest_select(base_url, headers, "parcel", query)]


def seed_progress(base_url, headers, pnus, period_key):
    """PNU를 pending으로 시드한다. ignore-duplicates라 몇 번을 돌려도 진행분이 안 지워진다."""
    rows = [{"collector": COLLECTOR, "scope_key": pnu,
             "period_key": period_key, "status": "pending"} for pnu in pnus]
    return upsert_batch(base_url, headers, "collect_progress", rows, "ignore-duplicates")


def fetch_pending(base_url, headers, period_key):
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=scope_key,attempts&collector=eq.{}&period_key=eq.{}&status=eq.pending".format(
            COLLECTOR, period_key),
        order="scope_key")
    return [(r["scope_key"], r.get("attempts") or 0) for r in rows]


def progress_status_counts(base_url, headers, period_key):
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=status&collector=eq.{}&period_key=eq.{}".format(COLLECTOR, period_key),
        order="scope_key")
    return Counter(r["status"] for r in rows)


def build_progress_row(pnu, period_key, result, attempts):
    return {
        "collector": COLLECTOR,
        "scope_key": pnu,
        "period_key": period_key,
        "status": result["status"],
        "row_count": result.get("row_count"),
        "error_msg": result.get("error_msg"),
        "attempts": attempts + (1 if result["status"] == "failed" else 0),
        "updated_at": now_kst_iso(),
    }


def save_progress(base_url, headers, rows):
    if rows:
        upsert_batch(base_url, headers, "collect_progress", rows, "merge-duplicates")


def retry_failed(base_url, headers, period_key, max_attempts=RETRY_FAILED_MAX_ATTEMPTS):
    """failed를 pending으로 되돌린다(attempts 상한 미만만 — 무한 재시도 방지)."""
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=scope_key,attempts&collector=eq.{}&period_key=eq.{}&status=eq.failed".format(
            COLLECTOR, period_key),
        order="scope_key")
    targets = [r for r in rows if (r.get("attempts") or 0) < max_attempts]
    if not targets:
        return 0
    upsert_batch(base_url, headers, "collect_progress", [
        {"collector": COLLECTOR, "scope_key": r["scope_key"], "period_key": period_key,
         "status": "pending", "error_msg": None} for r in targets], "merge-duplicates")
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


def print_dry_run_report(period_key, sigungu_code, raw_dir, domain,
                         pnu_count, pending_count, counts, verdict, budget):
    print("=" * 78)
    print("브이월드 토지특성 수집 — dry-run (API 호출 0건)")
    print("=" * 78)
    print("  수집 회차       {}".format(period_key))
    print("  시군구          {}".format(sigungu_code or "전체"))
    print("  raw 파일        {}".format(raw_path(raw_dir)))
    print("  domain          {}".format(domain))
    print("  parcel 총 필지  {:,}개".format(pnu_count))
    print("")
    print("  [ collect_progress 현황 ]")
    for st in ("done", "pending", "failed", "skipped"):
        print("    {:<9} {:>7,}".format(st, counts.get(st, 0)))
    print("")
    print("  [ 오늘 예산 ] 일 {:,}건 (공식 한도 미명시 — 보수적 자체 캡)".format(budget))
    print("    남은 예산     {:>7,}건".format(verdict["remaining"]))
    print("    계획 호출     {:>7,}건 (pending {:,}개 x 1콜)".format(
        verdict["planned"], pending_count))
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
    print("  처리한 필지 {:,}개 / 받은 행 {:,}건".format(processed, rows))
    for st in ("done", "failed", "skipped"):
        if status_counter.get(st):
            print("    {:<9} {:>7,}".format(st, status_counter[st]))
    print("  API 호출 {:,}건 / 소요 {:.1f}분".format(session_calls, elapsed_sec / 60))
    print("=" * 78)


# ── 메인 ─────────────────────────────────────────────────────────────────────


def _install_signal_handler():
    def handler(signum, frame):  # noqa: ARG001
        _STOP_REQUESTED["value"] = True
        print("\n중단 요청을 받았습니다. 지금 필지를 마치고 안전하게 종료합니다…")
    try:
        signal.signal(signal.SIGINT, handler)
    except (ValueError, OSError):
        pass  # 스레드·서비스 환경에서는 핸들러를 못 걸 수 있다 — 치명적이지 않다.


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="브이월드 토지특성 수집기")
    p.add_argument("--dry-run", action="store_true", help="API 호출 없이 예산·대상만 확인")
    p.add_argument("--limit", type=int, default=None, help="이번 실행에서 처리할 최대 필지 수")
    p.add_argument("--sigungu", default=None, help="시군구 코드 5자리로 대상 좁히기 (예: 11680)")
    p.add_argument("--period-key", default=None, help="수집 회차 키 YYYYMM (기본: 이번 달)")
    p.add_argument("--daily-budget", type=int, default=DEFAULT_DAILY_BUDGET,
                   help="오늘 쓸 최대 호출 수 (기본 {:,})".format(DEFAULT_DAILY_BUDGET))
    p.add_argument("--retry-failed", action="store_true", help="failed를 pending으로 되돌리고 종료")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    period_key = args.period_key or current_period_key()
    raw_dir = default_raw_dir(period_key)

    base_url, sb_key = get_supabase_config()
    headers = {"apikey": sb_key, "Authorization": "Bearer {}".format(sb_key)}

    if args.retry_failed:
        n = retry_failed(base_url, headers, period_key)
        print("failed -> pending 되돌림: {:,}건".format(n))
        return 0

    pnus = fetch_target_pnus(base_url, headers, args.sigungu)
    if not pnus:
        print("대상 필지가 없습니다. parcel 테이블을 먼저 채우세요.")
        return 1
    seed_progress(base_url, headers, pnus, period_key)

    target = set(pnus)
    pending = [(p, a) for p, a in fetch_pending(base_url, headers, period_key) if p in target]
    if args.limit is not None:
        pending = pending[:args.limit]

    log_date = today_kst()
    baseline = read_quota_baseline(base_url, headers, log_date)
    verdict = budget_verdict(baseline, len(pending), args.daily_budget)

    if args.dry_run:
        counts = progress_status_counts(base_url, headers, period_key)
        print_dry_run_report(period_key, args.sigungu, raw_dir, get_domain(),
                             len(pnus), len(pending), counts, verdict, args.daily_budget)
        return 0

    if not pending:
        print("pending이 없습니다 — 이번 회차({})는 이미 끝났습니다.".format(period_key))
        return 0

    api_key = get_api_key()
    domain = get_domain()
    _install_signal_handler()

    session = requests.Session()
    call_counter = {"calls": 0}
    status_counter = Counter()
    progress_rows = []
    processed = row_total = 0
    stop_reason = "pending 소진"
    started = time.time()

    try:
        for pnu, attempts in pending:
            if _STOP_REQUESTED["value"]:
                stop_reason = "사용자 중단 요청"
                break
            if baseline + call_counter["calls"] >= args.daily_budget:
                stop_reason = "일 예산 도달 ({:,}건)".format(args.daily_budget)
                break
            try:
                result = collect_one(session, api_key, pnu, domain, raw_dir,
                                     call_counter=call_counter)
            except ConfigError as e:
                stop_reason = "설정 오류로 중단 — {}".format(e)
                break
            except ApiError as e:
                result = {"status": "failed", "row_count": None,
                          "error_msg": mask_secret(str(e), api_key)[:500]}
            processed += 1
            row_total += result.get("row_count") or 0
            status_counter[result["status"]] += 1
            progress_rows.append(build_progress_row(pnu, period_key, result, attempts))
            if len(progress_rows) >= 200:
                save_progress(base_url, headers, progress_rows)
                progress_rows = []
    finally:
        save_progress(base_url, headers, progress_rows)
        flush_quota_log(base_url, headers, log_date, baseline, call_counter["calls"])

    print_run_report(processed, status_counter, call_counter["calls"],
                     time.time() - started, stop_reason, row_total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
