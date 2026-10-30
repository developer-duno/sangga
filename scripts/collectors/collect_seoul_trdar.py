# -*- coding: utf-8 -*-
"""서울시 상권분석서비스 4종(추정매출 · 길단위인구 · 상주인구 · 직장인구) 열린 API → raw JSONL (결정 0045 PR②).

무엇을 받나
-----------
서울시가 공표하는 상권 1,650개 단위 네 자료를 **공표값 그대로** 받는다(우리가 계산하지 않는다):
  · sales    = 추정매출(OA-15572 · VwsmTrdarSelngQq) — (분기, 상권, 서비스 업종 100종) 한 줄 · 숫자 48칸
  · flow     = 길단위인구(OA-15568 · VwsmTrdarFlpopQq) — (분기, 상권) 한 줄 · 숫자 22칸(서울시 칸 이름 「유동인구」)
  · resident = 상주인구(OA-15584 · VwsmTrdarRepopQq) — (분기, 상권) 한 줄 · 숫자 24칸
  · worker   = 직장인구(OA-15569 · VwsmTrdarWrcPopltnQq) — (분기, 상권) 한 줄 · 숫자 21칸

두 갈래 — 분기 자료와 연 1회 자료 (2026-10-31 전수 실측 — D:/tmp/sangga-wave3/probe_yearly.out)
-------------------------------------------------------------------------------------------
  ① sales·flow — 주소 끝 분기 인자가 먹는다. 개업·폐업 수집기(collect_seoul_openclose.py · 결정 0033)와 같은
     **분기 이어받기**: 분기 하나 = 작업 하나(collector='seoul_trdar_<service>' · scope_key='seoul' ·
     period_key='20262') · 최신 분기부터 · 끝까지 받아 수가 맞을 때만 파일을 쓰고 done.
  ② resident·worker — ⛔ **서울시가 분기 인자를 무시하고 22분기를 섞어 한꺼번에 준다**(상주 35,908행 = 36쪽 ·
     직장 36,027행 = 37쪽). 그래서 **분기 없는 주소 + 쪽 이어받기**:
       · 첫 호출(1쪽)의 list_total_count 로 쪽 수(올림 total ÷ 1,000)를 알고 쪽마다 씨앗 p0001… 을 뿌린다.
       · 쪽 장부 scope_key = 'seoul_<--end-quarter>' — **끝 분기마다 새 장부**다. 다음 해 값이 올라오면 새 끝
         분기로 돌려 36·37회 처음부터 다시 받는다(같은 끝 분기로 다시 돌리면 done 쪽은 건너뛴다).
       · 쪽마다 `<raw>/<service>/_pages/p0001_<받은날짜>.jsonl` 로 저장(이어받기 단위 · 한 줄 = {"page","total",
         "fetched_at","row"}).
       · 모든 쪽이 done 이면 쪽 파일을 **분기별로 나눠** `<raw>/<service>/<분기>_<받은날짜>.jsonl`(①과 같은 줄 모양
         {"quarter","fetched_at","row"} · 행의 STDR_YYQU_CD 가 그 행의 분기)로 쓴다 — 적재기는 이 분기 파일만 읽는다.
         쪽 파일들의 총건수가 서로 다르거나 합이 안 맞거나 (분기, 상권)이 겹치면 나누지 않는다(서울시가 받는 도중
         자료를 바꾼 것 — 처음부터 다시).
       · `--end-quarter` 는 여기서도 의무다 — 받은 전체의 가장 최근 분기가 그 값과 다르면 **경고만** 한다
         (서울시가 분기 인자를 무시하므로 우리가 고를 수 없다).

공식 명세 (data.seoul.go.kr — 결정 0033 확인과 같은 API 꼴)
-----------------------------------------------------------
  · 주소 = http://openapi.seoul.go.kr:8088/(인증키)/json/(서비스)/(시작)/(끝)/[(STDR_YYQU_CD)]
  · 한 번에 최대 1,000건 · 성공 INFO-000 · 자료 없음 INFO-200 · 인증키 오류 INFO-100 · 서버 오류 ERROR-500·600·601.
  · 일 호출 한도는 명세에 없다 — 한 번 실행의 상한 `--max-calls`(기본 2,000)를 둔다. 4종 22분기 한 벌 ≈ 600회
    (sales 22 × 약 22쪽 + flow 22 × 2 + resident 36 + worker 37).
  · 숫자는 실수 꼴(157199.0)로 온다 — 해석은 적재기 몫, 여기서는 **원본 그대로** 적는다(raw 는 덮어쓰지 않는다).

재사용 (같은 API · 같은 키 · 같은 규칙이라 개업·폐업 수집기에서 **import** 한다 — 글자 복사 아님)
-------------------------------------------------------------------------------------------
  collect_seoul_openclose 의 parse_quarter · quarter_range · mask_secret · get_api_key(키 = .env 의
  SEOUL_OPENAPI_KEY) · 코드 상수 · 오류 종류. 봉투 읽기·한 쪽 받기·분기 받기는 서비스 이름이 들어가야 해서 여기서
  같은 꼴로 다시 적었다(규칙 — INFO-200 은 0건 · INFO-100 은 멈춤 · ERROR-500/600/601·HTTP 5xx 만 재시도 — 그대로).
  ⛔ 인증키는 주소 **경로**에 든다 — 오류 문구·로그는 전부 mask_secret 을 지난다.

⛔ 0건(INFO-200 또는 list_total_count 0)은 done 으로 굳히지 않는다(아직 게시 안 된 분기 — pending 유지 + 경고).
⛔ `--end-quarter YYYYQ` 는 의무다(기본값 없음 — 게시된 분기를 먼저 `--dry-run` 으로 확인한다).

쓰는 법 (프로젝트 루트에서)
---------------------------
    python scripts/collectors/collect_seoul_trdar.py --service all --dry-run --end-quarter 20262 --quarters 22
    python scripts/collectors/collect_seoul_trdar.py --service all --end-quarter 20262 --quarters 22
    python scripts/collectors/collect_seoul_trdar.py --service sales --end-quarter 20263 --quarters 1

`--dry-run` = 서비스마다 API 1회(행 1개로 list_total_count 만) + collect_progress **읽기만**(씨앗을 안 뿌린다 —
DB 쓰기 0 · 파일 쓰기 0 · 개업·폐업 수집기와 같다).
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
from zoneinfo import ZoneInfo

import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from collect_rone import get_supabase_config, rest_select, upsert_batch  # noqa: E402
from collect_seoul_openclose import (  # noqa: E402
    API_BASE,
    API_TIMEOUT_SEC,
    CODE_BAD_KEY,
    CODE_NO_DATA,
    CODE_OK,
    RETRY_BACKOFF_BASE_SEC,
    RETRY_CODES,
    RETRY_COUNT,
    SECRET_MASK,  # noqa: F401  (시험이 이 모듈에서 가림 글자를 꺼내 본다)
    ApiError,
    ServiceKeyError,
    get_api_key,
    mask_secret,
    parse_quarter,
    quarter_range,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
DEFAULT_RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "seoul_trdar")

SERVICES = {
    "sales": "VwsmTrdarSelngQq",
    "flow": "VwsmTrdarFlpopQq",
    "resident": "VwsmTrdarRepopQq",
    "worker": "VwsmTrdarWrcPopltnQq",
}
QUARTERLY = ("sales", "flow")          # 분기 인자가 먹는다
YEARLY = ("resident", "worker")        # 분기 인자를 무시하고 전부 섞어 준다(10-31 실측)
PAGE_SIZE = 1000                       # 공식 명세: 한 번에 최대 1,000건(ERROR-336)
# 받을 쪽 수가 이보다 많으면 모양이 바뀐 것으로 보고 멈춘다(sales 분기당 약 22쪽 · flow 2쪽 · 연 1회 36·37쪽).
MAX_PAGES = {"sales": 30, "flow": 3, "resident": 60, "worker": 60}
DEFAULT_QUARTERS = 22
DEFAULT_MAX_CALLS = 2000

COLLECTOR_PREFIX = "seoul_trdar_"
SCOPE_KEY = "seoul"
PAGES_DIR = "_pages"

KST = ZoneInfo("Asia/Seoul")
RE_PAGE_FILE = re.compile(r"^(p\d{4})_(\d{8})\.jsonl$")


def collector_name(service):
    """장부의 collector 이름 — 네 서비스가 서로 섞이지 않게(seoul_trdar_sales …)."""
    return COLLECTOR_PREFIX + service


def page_scope(end_quarter):
    """연 1회 자료의 쪽 장부 scope_key — 끝 분기마다 새 장부(다음 해 값이 올라오면 새 끝 분기로 처음부터)."""
    return "{}_{}".format(SCOPE_KEY, end_quarter)


def page_key(n):
    return "p{:04d}".format(n)


def service_dir(raw_dir, service):
    return os.path.join(raw_dir, service)


# ── 순수 로직 ────────────────────────────────────────────────────────────────


def page_url(key, service, start, end, quarter=None):
    """분기 자료는 끝에 분기 · 연 1회 자료(분기 인자를 무시)는 분기 칸 없이 끝 빗금."""
    base = "{}/{}/json/{}/{}/{}/".format(API_BASE, key, SERVICES[service], start, end)
    return base + quarter if quarter else base


def read_envelope(payload, service):
    """응답 → (코드, 메시지, 총건수, 행). 꼴은 개업·폐업 수집기와 같다(서비스 이름 열쇠만 다르다)."""
    if not isinstance(payload, dict):
        return "", "", 0, []
    body = payload.get(SERVICES[service])
    if isinstance(body, dict):
        result = body.get("RESULT") if isinstance(body.get("RESULT"), dict) else {}
        try:
            total = int(body.get("list_total_count") or 0)
        except (TypeError, ValueError):
            total = 0
        rows = body.get("row") if isinstance(body.get("row"), list) else []
        return (str(result.get("CODE", "")).strip(), str(result.get("MESSAGE", "")).strip(),
                total, [r for r in rows if isinstance(r, dict)])
    result = payload.get("RESULT") if isinstance(payload.get("RESULT"), dict) else {}
    return str(result.get("CODE", "")).strip(), str(result.get("MESSAGE", "")).strip(), 0, []


def raw_file(raw_dir, service, quarter, fetched_date):
    return os.path.join(service_dir(raw_dir, service), "{}_{}.jsonl".format(quarter, fetched_date))


def page_file(raw_dir, service, page, fetched_date):
    return os.path.join(service_dir(raw_dir, service), PAGES_DIR, "{}_{}.jsonl".format(page, fetched_date))


def jsonl_text(quarter, rows, fetched_at):
    return "".join(
        json.dumps({"quarter": quarter, "fetched_at": fetched_at, "row": r}, ensure_ascii=False) + "\n"
        for r in rows)


def write_once(path, text, rows, key_of):
    """같은 날 같은 파일이 있으면: 내용이 같으면 그대로(True) · 다르면 덮어쓰지 않음(False).

    없으면 `.part` 로 쓰고 바꿔 단다(반쪽 파일이 남지 않게). key_of(줄 dict) → 견줄 값.
    """
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = [key_of(json.loads(line)) for line in f if line.strip()]
        return old == rows
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)
    return True


def split_by_quarter(page_rows):
    """여러 쪽의 행 → {분기: 행 목록}(행의 STDR_YYQU_CD 가 분기 · 쪽 차례·쪽 안 차례 유지).

    분기 꼴(YYYYQ)이 아닌 행이나 (분기, 상권)이 겹치는 행이 있으면 ValueError — 나누지 않는다.
    """
    out = {}
    seen = set()
    for r in page_rows:
        q = str(r.get("STDR_YYQU_CD", "")).strip()
        parse_quarter(q)                     # 꼴이 다르면 ValueError
        k = (q, str(r.get("TRDAR_CD", "")).strip())
        if k in seen:
            raise ValueError("(분기, 상권) 이 겹칩니다: {} — 서울시가 받는 도중 자료를 바꿨을 수 있습니다".format(k))
        seen.add(k)
        out.setdefault(q, []).append(r)
    return out


# ── API ──────────────────────────────────────────────────────────────────────


def fetch_page(session, key, service, start, end, quarter=None, sleep=time.sleep,
               retry_count=RETRY_COUNT, backoff_base=RETRY_BACKOFF_BASE_SEC):
    """한 쪽 → (코드, 총건수, 행). 규칙은 개업·폐업 수집기 fetch_page 와 같다(INFO-200 은 0건)."""
    url = page_url(key, service, start, end, quarter)
    last = None
    for attempt in range(1, retry_count + 1):
        try:
            r = session.get(url, timeout=API_TIMEOUT_SEC)
        except requests.RequestException as e:
            last = mask_secret("네트워크 오류: {}".format(e), key)
        else:
            if r.status_code >= 500:
                last = "HTTP {}".format(r.status_code)
            elif r.status_code >= 300:
                raise ApiError("HTTP {}: {}".format(r.status_code, mask_secret(r.text[:200], key)))
            else:
                try:
                    payload = r.json()
                except ValueError:
                    raise ApiError("JSON 이 아닙니다: {}".format(mask_secret(r.text[:200], key)))
                code, msg, total, rows = read_envelope(payload, service)
                if code == CODE_BAD_KEY:
                    raise ServiceKeyError("인증키 오류(INFO-100): {}".format(mask_secret(msg, key)))
                if code == CODE_NO_DATA:
                    return code, 0, []
                if code == CODE_OK:
                    return code, total, rows
                if code not in RETRY_CODES:
                    raise ApiError("CODE={} {}".format(code or "(없음)", mask_secret(msg, key)))
                last = "CODE={} {}".format(code, mask_secret(msg, key))
        if attempt < retry_count:
            sleep(backoff_base ** attempt)
    raise ApiError("재시도 {}회 소진: {}".format(retry_count, last))


def collect_quarter(session, key, service, quarter, raw_dir, fetched_date, fetched_at,
                    call_counter, max_calls=None, **kwargs):
    """분기 자료(sales·flow) 한 분기를 끝까지 받아 {status, row_count, error_msg}.

    개업·폐업 수집기 collect_quarter 와 같은 규칙 — 0건·중간 끊김·수 어긋남·다른 분기 행은 전부 pending(파일 0).
    """
    rows, total, page = [], None, 1
    try:
        while True:
            if max_calls is not None and call_counter[0] >= max_calls:
                return {"status": "pending", "row_count": None,
                        "error_msg": "한 번 실행 상한 {:,}회에 닿아 이 분기를 끝까지 못 받음 — "
                                     "다음 실행이 이어받는다(파일 안 씀)".format(max_calls)}
            start = (page - 1) * PAGE_SIZE + 1
            call_counter[0] += 1
            code, page_total, part = fetch_page(session, key, service, start, start + PAGE_SIZE - 1,
                                                quarter, **kwargs)
            if page == 1:
                total = page_total
                if code == CODE_NO_DATA or total == 0:
                    return {"status": "pending", "row_count": 0,
                            "error_msg": "0건 응답({}) — 아직 게시 안 된 분기로 보인다. done 으로 "
                                         "굳히지 않는다(게시 뒤 다시 돌리면 받는다)".format(
                                             code or "list_total_count=0")}
                if -(-total // PAGE_SIZE) > MAX_PAGES[service]:
                    return {"status": "pending", "row_count": None,
                            "error_msg": "총 {:,}행 — 쪽 상한 {}을 넘는다. 모양이 바뀐 것으로 보고 멈춘다"
                                         "(파일 안 씀)".format(total, MAX_PAGES[service])}
            bad = [r.get("STDR_YYQU_CD") for r in part if str(r.get("STDR_YYQU_CD", "")).strip() != quarter]
            if bad:
                return {"status": "pending", "row_count": None,
                        "error_msg": "{} 를 물었는데 다른 분기 행 {}개({!r} 등)가 왔다 — 파일 안 씀".format(
                            quarter, len(bad), bad[0])}
            rows.extend(part)
            if len(rows) >= total or not part:
                break
            page += 1
    except ApiError as e:
        return {"status": "pending", "row_count": None,
                "error_msg": "{}쪽에서 끊김 — 파일 안 씀: {}".format(page, mask_secret(e, key))[:500]}

    if len(rows) != total:
        return {"status": "pending", "row_count": len(rows),
                "error_msg": "받은 행 {:,}개 ≠ list_total_count {:,} — 반쪽 분기라 파일 안 씀".format(
                    len(rows), total)}
    path = raw_file(raw_dir, service, quarter, fetched_date)
    if not write_once(path, jsonl_text(quarter, rows, fetched_at), rows, lambda o: o["row"]):
        return {"status": "pending", "row_count": len(rows),
                "error_msg": "같은 날 내용이 다른 파일이 이미 있다 — 덮어쓰지 않음(raw 는 복구 불가). "
                             "사람이 확인: {}".format(path)}
    return {"status": "done", "row_count": len(rows), "error_msg": None}


def collect_page(session, key, service, n, raw_dir, fetched_date, fetched_at, call_counter, **kwargs):
    """연 1회 자료의 n쪽 하나 → ({status, row_count, error_msg}, 총건수). 쪽 파일 하나를 쓴다.

    1쪽 밖에서 총건수가 1쪽 때와 다르면 부른 쪽(main)이 가른다(여기서는 총건수만 돌려준다).
    """
    start = (n - 1) * PAGE_SIZE + 1
    call_counter[0] += 1
    try:
        code, total, part = fetch_page(session, key, service, start, start + PAGE_SIZE - 1, None, **kwargs)
    except ApiError as e:
        return {"status": "pending", "row_count": None,
                "error_msg": "{} 에서 끊김 — 파일 안 씀: {}".format(page_key(n), mask_secret(e, key))[:500]}, None
    if code == CODE_NO_DATA or total == 0:
        return {"status": "pending", "row_count": 0,
                "error_msg": "0건 응답({}) — done 으로 굳히지 않는다".format(code or "list_total_count=0")}, 0
    want = min(PAGE_SIZE, total - start + 1)
    if len(part) != want:
        return {"status": "pending", "row_count": len(part),
                "error_msg": "{} 받은 행 {}개 ≠ 기대 {}개(총 {:,}) — 파일 안 씀".format(
                    page_key(n), len(part), want, total)}, total
    page = page_key(n)
    text = "".join(json.dumps({"page": page, "total": total, "fetched_at": fetched_at, "row": r},
                              ensure_ascii=False) + "\n" for r in part)
    path = page_file(raw_dir, service, page, fetched_date)
    if not write_once(path, text, part, lambda o: o["row"]):
        return {"status": "pending", "row_count": len(part),
                "error_msg": "같은 날 내용이 다른 쪽 파일이 이미 있다 — 덮어쓰지 않음: {}".format(path)}, total
    return {"status": "done", "row_count": len(part), "error_msg": None}, total


def latest_page_files(raw_dir, service):
    """{쪽 열쇠: 경로} — 쪽마다 가장 최근 받은 날 파일 하나."""
    d = os.path.join(service_dir(raw_dir, service), PAGES_DIR)
    out = {}
    if os.path.isdir(d):
        for n in sorted(os.listdir(d)):
            m = RE_PAGE_FILE.match(n)
            if m and (m.group(1) not in out or m.group(2) > out[m.group(1)][0]):
                out[m.group(1)] = (m.group(2), os.path.join(d, n))
    return {k: p for k, (_, p) in out.items()}


def split_pages(raw_dir, service, pages, fetched_date, fetched_at):
    """done 인 쪽 파일 전부 → 분기 파일들. 돌려줌 = {분기: 행 수}. 문제가 있으면 ValueError(파일 0).

    pages = 받아야 할 쪽 열쇠 목록(p0001…). 쪽 파일이 하나라도 없거나 총건수가 서로 다르거나 행 합 ≠ 총건수면 멈춘다.
    """
    files = latest_page_files(raw_dir, service)
    missing = [p for p in pages if p not in files]
    if missing:
        raise ValueError("쪽 파일이 없습니다: {}".format(missing[:5]))
    rows, totals = [], set()
    for p in pages:
        with open(files[p], encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    o = json.loads(line)
                    totals.add(o["total"])
                    rows.append(o["row"])
    if len(totals) != 1:
        raise ValueError("쪽마다 총건수가 다릅니다 {} — 받는 도중 서울시 자료가 바뀌었다. 끝 분기를 새로 주고 "
                         "처음부터 다시 받는다".format(sorted(totals)))
    total = totals.pop()
    if len(rows) != total:
        raise ValueError("쪽 행 합 {:,} ≠ 총건수 {:,}".format(len(rows), total))
    by_q = split_by_quarter(rows)
    written = {}
    for q in sorted(by_q):
        path = raw_file(raw_dir, service, q, fetched_date)
        if not write_once(path, jsonl_text(q, by_q[q], fetched_at), by_q[q], lambda o: o["row"]):
            raise ValueError("같은 날 내용이 다른 분기 파일이 이미 있다 — 덮어쓰지 않음: {}".format(path))
        written[q] = len(by_q[q])
    return written


# ── collect_progress ─────────────────────────────────────────────────────────


def seed_progress(base_url, headers, service, scope, keys):
    """pending 씨앗. 이미 있는 행은 그대로(ignore-duplicates)."""
    rows = [{"collector": collector_name(service), "scope_key": scope, "period_key": k, "status": "pending"}
            for k in keys]
    return upsert_batch(base_url, headers, "collect_progress", rows, "ignore-duplicates")


def read_progress(base_url, headers, service, scope):
    """{period_key: (상태, attempts)} — 이 서비스·scope 행 전부(읽기만)."""
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=period_key,status,attempts&collector=eq.{}&scope_key=eq.{}".format(collector_name(service), scope),
        order="period_key")
    return {r["period_key"]: (r["status"], r.get("attempts") or 0) for r in rows}


def pending_keys(keys, progress):
    """장부에 없거나 pending 인 것만(차례 유지)."""
    return [k for k in keys if progress.get(k, ("pending", 0))[0] == "pending"]


def save_progress(base_url, headers, service, scope, key, result, attempts):
    upsert_batch(base_url, headers, "collect_progress", [{
        "collector": collector_name(service), "scope_key": scope, "period_key": key,
        "status": result["status"], "row_count": result.get("row_count"),
        "error_msg": result.get("error_msg"),
        "attempts": attempts + (0 if result["status"] == "done" else 1),
        "updated_at": datetime.datetime.now(KST).isoformat(),
    }], "merge-duplicates")


# ── 메인 ─────────────────────────────────────────────────────────────────────


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="서울시 상권분석서비스 4종(추정매출·길단위인구·상주인구·직장인구) API → raw JSONL (결정 0045)",
        allow_abbrev=False)
    p.add_argument("--service", required=True, choices=sorted(SERVICES) + ["all"],
                   help="sales · flow · resident · worker · all(네 개 차례로)")
    p.add_argument("--end-quarter", required=True,
                   help="받을 가장 최근 분기 YYYYQ (의무 — 게시된 분기를 먼저 확인한다)")
    p.add_argument("--quarters", type=int, default=DEFAULT_QUARTERS,
                   help="분기 자료(sales·flow)를 끝 분기에서 거슬러 몇 분기 (기본 22 = 20211 부터)")
    p.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    p.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS,
                   help="한 번 실행의 API 호출 상한 (기본 2,000 · 네 서비스 합)")
    p.add_argument("--dry-run", action="store_true",
                   help="서비스마다 API 1회로 총건수만 보고 장부는 읽기만 (DB·파일 쓰기 0)")
    a = p.parse_args(argv)
    a.quarter_list = quarter_range(a.end_quarter, a.quarters)
    a.service_list = list(SERVICES) if a.service == "all" else [a.service]
    return a


def _dry_run(session, key, base_url, headers, a):
    for svc in a.service_list:
        quarterly = svc in QUARTERLY
        try:
            code, total, _ = fetch_page(session, key, svc, 1, 1, a.quarter_list[0] if quarterly else None)
        except (ApiError, ServiceKeyError) as e:
            print("[에러] {}: {}".format(svc, e), file=sys.stderr)
            return 1
        pages = max(1, -(-total // PAGE_SIZE))
        if quarterly:
            progress = read_progress(base_url, headers, svc, SCOPE_KEY)
            todo = pending_keys(a.quarter_list, progress)
            print("  {:<8} 끝 분기 {} : {} · 행 {:,} · 분기당 ≈ {}쪽 · 받을 분기 {}개 · 예상 호출 ≈ {:,}회".format(
                svc, a.quarter_list[0], code, total, pages, len(todo), len(todo) * pages))
            if not total:
                print("  ⚠️ {} 끝 분기가 0건입니다 — 아직 게시 안 된 분기일 수 있습니다.".format(svc))
        else:
            progress = read_progress(base_url, headers, svc, page_scope(a.end_quarter))
            keys = [page_key(n) for n in range(1, pages + 1)]
            todo = pending_keys(keys, progress)
            print("  {:<8} 분기 무시(전부 섞임) : {} · 행 {:,} · {}쪽 · 받을 쪽 {}개 (장부 {})".format(
                svc, code, total, pages, len(todo), page_scope(a.end_quarter)))
    print("--dry-run — 파일·DB 에 아무것도 쓰지 않았습니다.")
    return 0


def _run_quarterly(session, key, base_url, headers, a, svc, fetched_date, fetched_at, calls):
    seed_progress(base_url, headers, svc, SCOPE_KEY, a.quarter_list)
    progress = read_progress(base_url, headers, svc, SCOPE_KEY)
    done = left = 0
    for q in pending_keys(a.quarter_list, progress):
        if calls[0] >= a.max_calls:
            print("  호출 상한 {:,}회에 닿았습니다 — 나머지는 다음 실행이 이어받습니다.".format(a.max_calls))
            left += 1
            break
        result = collect_quarter(session, key, svc, q, a.raw_dir, fetched_date, fetched_at, calls,
                                 max_calls=a.max_calls)
        save_progress(base_url, headers, svc, SCOPE_KEY, q, result, progress.get(q, ("", 0))[1])
        if result["status"] == "done":
            done += 1
            print("  {} {} done · {:,}행".format(svc, q, result["row_count"]))
        else:
            left += 1
            print("  [경고] {} {} pending 유지 — {}".format(svc, q, result["error_msg"]))
    return done, left


def _run_yearly(session, key, base_url, headers, a, svc, fetched_date, fetched_at, calls):
    scope = page_scope(a.end_quarter)
    progress = read_progress(base_url, headers, svc, scope)
    total = None
    if not progress:
        # 첫 쪽을 받아 쪽 수를 안다 — 그 호출의 행도 버리지 않고 쪽 파일로 쓴다.
        result, total = collect_page(session, key, svc, 1, a.raw_dir, fetched_date, fetched_at, calls)
        if not total:
            print("  [경고] {} 1쪽 — {}".format(svc, result["error_msg"]))
            return 0, 1
        pages = -(-total // PAGE_SIZE)
        if pages > MAX_PAGES[svc]:
            print("  [경고] {} 총 {:,}행 — 쪽 상한 {}을 넘어 멈춘다(모양이 바뀐 것으로 본다)".format(
                svc, total, MAX_PAGES[svc]))
            return 0, 1
        keys = [page_key(n) for n in range(1, pages + 1)]
        seed_progress(base_url, headers, svc, scope, keys)
        save_progress(base_url, headers, svc, scope, keys[0], result, 0)
        progress = read_progress(base_url, headers, svc, scope)
    keys = sorted(progress)
    done = left = 0
    for k in pending_keys(keys, progress):
        if calls[0] >= a.max_calls:
            print("  호출 상한 {:,}회에 닿았습니다 — 나머지 쪽은 다음 실행이 이어받습니다.".format(a.max_calls))
            left += 1
            break
        result, t = collect_page(session, key, svc, int(k[1:]), a.raw_dir, fetched_date, fetched_at, calls)
        if t and total and t != total:
            result = {"status": "pending", "row_count": result.get("row_count"),
                      "error_msg": "총건수가 {:,} → {:,} 로 바뀌었다 — 서울시가 받는 도중 자료를 바꿨다".format(total, t)}
        total = total or t
        save_progress(base_url, headers, svc, scope, k, result, progress.get(k, ("", 0))[1])
        if result["status"] == "done":
            done += 1
        else:
            left += 1
            print("  [경고] {} {} pending 유지 — {}".format(svc, k, result["error_msg"]))
    progress = read_progress(base_url, headers, svc, scope)
    if any(progress.get(k, ("",))[0] != "done" for k in keys):
        print("  {} 쪽 {}/{} done — 다 받은 뒤 분기로 나눈다".format(
            svc, sum(1 for k in keys if progress.get(k, ("",))[0] == "done"), len(keys)))
        return done, max(left, 1)
    try:
        written = split_pages(a.raw_dir, svc, keys, fetched_date, fetched_at)
    except ValueError as e:
        print("  [경고] {} 분기로 나누지 못함 — {}".format(svc, e))
        return done, max(left, 1)
    newest = max(written)
    print("  {} 분기 {}개로 나눔 ({} ~ {} · 합 {:,}행)".format(
        svc, len(written), min(written), newest, sum(written.values())))
    if newest != a.end_quarter:
        print("  ⚠️ {} 받은 자료의 가장 최근 분기 {} ≠ --end-quarter {} — 서울시가 분기 인자를 무시하므로 "
              "경고만 한다(그대로 둔다)".format(svc, newest, a.end_quarter))
    return done, left


def main(argv=None):
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    try:
        a = parse_args(sys.argv[1:] if argv is None else argv)
        key = get_api_key()
        base_url, db_key = get_supabase_config()
    except (ValueError, RuntimeError) as e:
        print("[에러] {}".format(e), file=sys.stderr)
        return 2
    headers = {"apikey": db_key, "Authorization": "Bearer {}".format(db_key)}
    session = requests.Session()

    print("=" * 72)
    print("서울시 상권분석서비스 4종 수집 — {} · 끝 분기 {} · 분기 자료 {}분기".format(
        ",".join(a.service_list), a.end_quarter, len(a.quarter_list)))
    print("=" * 72)

    if a.dry_run:
        return _dry_run(session, key, base_url, headers, a)

    now = datetime.datetime.now(KST)
    fetched_date, fetched_at = now.strftime("%Y%m%d"), now.isoformat()
    calls = [0]
    done = left = 0
    for svc in a.service_list:
        run = _run_quarterly if svc in QUARTERLY else _run_yearly
        try:
            d, lf = run(session, key, base_url, headers, a, svc, fetched_date, fetched_at, calls)
        except ServiceKeyError as e:
            print("[멈춤] {} — 인증키·활용 신청을 확인하세요.".format(mask_secret(e, key)), file=sys.stderr)
            return 1
        done += d
        left += lf
    print("=" * 72)
    print("  done {} · 남은 것 {} · 호출 {:,}회".format(done, left, calls[0]))
    if done:
        print("  다음: 4종이 다 끝나면 python scripts/collectors/load_seoul_trdar.py --dry-run")
        print("  💾 원본이 늘었으니 python scripts/backup_raw.py 도 잊지 마세요.")
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main())
