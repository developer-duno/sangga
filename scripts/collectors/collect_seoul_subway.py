# -*- coding: utf-8 -*-
"""서울 지하철 역사마스터(OA-21232) + 월별 시간대 승하차(OA-12252) 열린 API → raw JSON (결정 0045 PR⑥).

무엇을 받나
-----------
  · 역사마스터 `subwayStationMaster` — 수도권 역 784곳(2026-11-02 실측 · 서울 밖 279역 포함)의 역사 번호(BLDN_ID) · 역 이름 ·
    호선 · 좌표(LAT·LOT — WGS84 십진수 도). 장부 없이 **늘 다시** 받는다(호출 1회 · 1,000행 한 쪽).
  · 승하차 `CardSubwayTime` — 달마다 (호선, 역) 한 줄 · 승차·하차 24시간대 48칸(실수 꼴 `892.0`) · JOB_YMD(서울시 작업일).
    포털 원문 「교통카드(선후불교통카드 및 1회용 교통카드)를 이용한 지하철 호선별 역별 … 시간대별 승하차인원」 ·
    FAQ 「해당 정보는 환승객 여부와 상관없이 집계된 내용입니다」 · 공공누리 1유형. 한 달 604~623행(1쪽).
    우리는 계산하지 않는다 — **원본 그대로** 적는다(같은 (호선, 역)이 두 번 오는 달도 그대로 · 거르는 건 적재기 몫).

공식 명세 (data.seoul.go.kr — 결정 0033 확인과 같은 API 꼴)
-----------------------------------------------------------
  · 주소 = http://openapi.seoul.go.kr:8088/(인증키)/json/CardSubwayTime/(시작)/(끝)/(YYYYMM) — 달 인자는 주소 끝.
           http://openapi.seoul.go.kr:8088/(인증키)/json/subwayStationMaster/(시작)/(끝)/
  · 한 번에 최대 1,000건 · 성공 INFO-000 · **자료 없음 INFO-200**(아직 게시 안 된 달 — 2026-11-02 00:5x 202610 실측) ·
    인증키 오류 INFO-100 · 서버 오류 ERROR-500·600·601.
  · 게시 = 매월 5일 무렵 전월분(JOB_YMD 는 69달 내내 다음 달 3일 · 포털 「매월 5일 갱신」).

재사용 (같은 API · 같은 키 · 같은 규칙이라 개업·폐업 수집기에서 **import** 한다 — 글자 복사 아님)
-------------------------------------------------------------------------------------------
  collect_seoul_openclose 의 API_BASE · mask_secret · get_api_key(키 = .env 의 SEOUL_OPENAPI_KEY) · 코드 상수 · 오류 종류.
  봉투 읽기·한 쪽 받기는 서비스 이름이 들어가야 해서 여기서 같은 꼴로 다시 적었다(규칙 — INFO-200 은 0건 · INFO-100 은 멈춤 ·
  ERROR-500/600/601·HTTP 5xx 만 재시도 — 그대로). ⛔ 인증키는 주소 **경로**에 든다 — 오류 문구·로그는 전부 mask_secret 을 지난다.

이어받기 — `collect_progress` (collector 'seoul_subway' · scope_key 'seoul' · period_key 'YYYYMM')
-----------------------------------------------------------------------------------------------
  · 씨앗 = --start-month(기본 202101 — 서울시 「2021년 이후」) ~ --end-month 달 전부(pending · 있는 행 보존).
  · pending 만 받는다(--retry-failed 면 failed 도). 최신 달부터.
  · ⛔ **0건(INFO-200 · list_total_count 0) 달은 done 으로 굳히지 않는다** — pending 유지 + 경고(아직 게시 안 된 달).
  · 행의 USE_MM 이 그 달과 다르거나 받은 행 수 ≠ list_total_count 면 pending(파일 0).
  · 네트워크·서버 오류가 재시도 뒤에도 남으면 failed + 오류 문구(파일 0) — `--retry-failed` 로 다시.
  · ⛔ `--end-month YYYYMM` 은 의무다(기본값 없음 — 포털 게시를 먼저 `--dry-run --end-month <달>` 로 확인한다).

파일
----
  · 마스터: `data/raw/seoul_subway/master/<받은날짜 YYYYMMDD>.json` (같은 날 두 번이면 `_2`·`_3` 꼬리 — 덮어쓰기 0)
  · 승하차: `data/raw/seoul_subway/ridership/<YYYYMM>_<받은날짜>.json` (같은 날 같은 달이면 `_2` 꼬리)
  · 내용 = `{"service", "ym"(승하차만), "fetched_at"(KST ISO), "total", "rows"}` — rows 는 받은 그대로.

쓰는 법 (프로젝트 루트에서)
---------------------------
    python scripts/collectors/collect_seoul_subway.py --dry-run --end-month 202609     # 호출 1회 + 장부 읽기만
    python scripts/collectors/collect_seoul_subway.py --end-month 202609 --master-too  # 처음 한 벌(약 70 + 1회)
    python scripts/collectors/collect_seoul_subway.py --end-month 202610               # 매달 새 달 하나
    python scripts/collectors/collect_seoul_subway.py --master                         # 마스터만
  `--dry-run` = API 1회(그 끝 달 첫 1행으로 list_total_count 만) + collect_progress **읽기만**(씨앗 안 뿌림 · 파일 0).
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
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
DEFAULT_RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "seoul_subway")

MASTER_SERVICE = "subwayStationMaster"
RIDE_SERVICE = "CardSubwayTime"
PAGE_SIZE = 1000          # 공식 명세: 한 번에 최대 1,000건
MAX_PAGES = 2             # 마스터 784 · 한 달 604~623 — 2쪽 넘으면 모양이 바뀐 것으로 보고 멈춘다
DEFAULT_START = "202101"  # 서울시 「2021년 이후」
DEFAULT_MAX_CALLS = 300
CALL_SLEEP_SEC = 0.3

COLLECTOR = "seoul_subway"
SCOPE_KEY = "seoul"

KST = ZoneInfo("Asia/Seoul")
RE_MONTH = re.compile(r"^(\d{4})(0[1-9]|1[0-2])$")


# ── 순수 로직 ────────────────────────────────────────────────────────────────


def parse_month(text):
    """'202609' → '202609'. 꼴이 다르면 ValueError(조용히 0건으로 흘려보내지 않는다)."""
    s = str(text or "").strip()
    if not RE_MONTH.match(s):
        raise ValueError("달은 YYYYMM 여섯 자리여야 합니다(예: 202609): {!r}".format(text))
    return s


def month_range(start, end):
    """start ~ end 달 — **최신 달부터** 거슬러 간다."""
    s, e = parse_month(start), parse_month(end)
    if s > e:
        raise ValueError("--start-month {} 가 --end-month {} 보다 뒤입니다".format(s, e))
    out, y, m = [], int(e[:4]), int(e[4:])
    while "{:04d}{:02d}".format(y, m) >= s:
        out.append("{:04d}{:02d}".format(y, m))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out


def page_url(key, service, start, end, ym=None):
    """승하차는 끝에 달 · 마스터는 달 칸 없이 끝 빗금."""
    base = "{}/{}/json/{}/{}/{}/".format(API_BASE, key, service, start, end)
    return base + ym if ym else base


def read_envelope(payload, service):
    """응답 → (코드, 메시지, 총건수, 행). 꼴은 개업·폐업 수집기와 같다(서비스 이름 열쇠만 다르다)."""
    if not isinstance(payload, dict):
        return "", "", 0, []
    body = payload.get(service)
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


def free_path(path):
    """그 이름이 이미 있으면 `_2`·`_3` 꼬리를 붙인 첫 빈 이름(덮어쓰기 0)."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists("{}_{}{}".format(base, n, ext)):
        n += 1
    return "{}_{}{}".format(base, n, ext)


def master_file(raw_dir, fetched_date):
    return os.path.join(raw_dir, "master", "{}.json".format(fetched_date))


def ride_file(raw_dir, ym, fetched_date):
    return os.path.join(raw_dir, "ridership", "{}_{}.json".format(ym, fetched_date))


def write_new(path, obj):
    """`.part` 로 쓰고 바꿔 단다(반쪽 파일이 남지 않게). 이미 있는 이름이면 꼬리를 붙인다. → 실제 경로."""
    path = free_path(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)
    return path


# ── API ──────────────────────────────────────────────────────────────────────


def fetch_page(session, key, service, start, end, ym=None, sleep=time.sleep,
               retry_count=RETRY_COUNT, backoff_base=RETRY_BACKOFF_BASE_SEC):
    """한 쪽 → (코드, 총건수, 행). 규칙은 개업·폐업 수집기 fetch_page 와 같다(INFO-200 은 0건)."""
    url = page_url(key, service, start, end, ym)
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


def fetch_all(session, key, service, ym, call_counter, max_calls=None, between=time.sleep, **kwargs):
    """끝까지(최대 MAX_PAGES 쪽) 받아 (코드, 총건수, 행) 또는 문제 문장. → (결과 dict | None, 문제 문장 | None)."""
    rows, total, page, code = [], None, 1, None
    while True:
        if max_calls is not None and call_counter[0] >= max_calls:
            return None, "한 번 실행 상한 {:,}회에 닿아 끝까지 못 받음 — 다음 실행이 이어받는다(파일 안 씀)".format(max_calls)
        if call_counter[0]:
            between(CALL_SLEEP_SEC)
        start = (page - 1) * PAGE_SIZE + 1
        call_counter[0] += 1
        c, page_total, part = fetch_page(session, key, service, start, start + PAGE_SIZE - 1, ym, **kwargs)
        if page == 1:
            code, total = c, page_total
            if c == CODE_NO_DATA or total == 0:
                return {"code": c or "list_total_count=0", "total": 0, "rows": []}, None
            if -(-total // PAGE_SIZE) > MAX_PAGES:
                return None, "총 {:,}행 — 쪽 상한 {}을 넘는다. 모양이 바뀐 것으로 보고 멈춘다(파일 안 씀)".format(
                    total, MAX_PAGES)
        rows.extend(part)
        if len(rows) >= total or not part:
            break
        page += 1
    if len(rows) != total:
        return None, "받은 행 {:,}개 ≠ list_total_count {:,} — 반쪽이라 파일 안 씀".format(len(rows), total)
    return {"code": code, "total": total, "rows": rows}, None


def collect_master(session, key, raw_dir, fetched_date, fetched_at, call_counter, **kwargs):
    """마스터 한 벌 → 쓴 경로. 0건·반쪽이면 ApiError(파일 0)."""
    got, why = fetch_all(session, key, MASTER_SERVICE, None, call_counter, **kwargs)
    if why:
        raise ApiError("마스터: " + why)
    if not got["rows"]:
        raise ApiError("마스터가 0건입니다({}) — 파일 안 씀".format(got["code"]))
    return write_new(master_file(raw_dir, fetched_date),
                     {"service": MASTER_SERVICE, "fetched_at": fetched_at, "total": got["total"], "rows": got["rows"]})


def collect_month(session, key, ym, raw_dir, fetched_date, fetched_at, call_counter, max_calls=None, **kwargs):
    """한 달을 끝까지 받아 {status, row_count, error_msg}. done / pending(0건·어긋남) / failed(오류) 셋.

    ServiceKeyError 는 위로 올린다(전체를 멈춘다).
    """
    try:
        got, why = fetch_all(session, key, RIDE_SERVICE, ym, call_counter, max_calls=max_calls, **kwargs)
    except ApiError as e:
        return {"status": "failed", "row_count": None, "error_msg": mask_secret(e, key)[:500]}
    if why:
        return {"status": "pending", "row_count": None, "error_msg": why}
    if not got["rows"]:
        return {"status": "pending", "row_count": 0,
                "error_msg": "0건 응답({}) — 아직 게시 안 된 달로 보인다. done 으로 굳히지 않는다(게시 뒤 다시 돌리면 "
                             "받는다)".format(got["code"])}
    bad = [r.get("USE_MM") for r in got["rows"] if str(r.get("USE_MM", "")).strip() != ym]
    if bad:
        return {"status": "pending", "row_count": None,
                "error_msg": "{} 를 물었는데 다른 달 행 {}개({!r} 등)가 왔다 — 파일 안 씀".format(ym, len(bad), bad[0])}
    write_new(ride_file(raw_dir, ym, fetched_date),
              {"service": RIDE_SERVICE, "ym": ym, "fetched_at": fetched_at, "total": got["total"], "rows": got["rows"]})
    return {"status": "done", "row_count": len(got["rows"]), "error_msg": None}


# ── collect_progress ─────────────────────────────────────────────────────────


def seed_progress(base_url, headers, months):
    """달마다 pending 씨앗. 이미 있는 행은 그대로(ignore-duplicates)."""
    rows = [{"collector": COLLECTOR, "scope_key": SCOPE_KEY, "period_key": m, "status": "pending"} for m in months]
    return upsert_batch(base_url, headers, "collect_progress", rows, "ignore-duplicates")


def read_progress(base_url, headers):
    """{달: (상태, attempts)} — 이 수집기 행 전부(읽기만)."""
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=period_key,status,attempts&collector=eq.{}&scope_key=eq.{}".format(COLLECTOR, SCOPE_KEY),
        order="period_key")
    return {r["period_key"]: (r["status"], r.get("attempts") or 0) for r in rows}


def todo_months(months, progress, retry_failed=False):
    """이번에 받을 달 — 장부에 없거나 pending(--retry-failed 면 failed 도)인 것만, 최신부터."""
    want = ("pending", "failed") if retry_failed else ("pending",)
    return [m for m in months if progress.get(m, ("pending", 0))[0] in want]


def save_progress(base_url, headers, ym, result, attempts):
    upsert_batch(base_url, headers, "collect_progress", [{
        "collector": COLLECTOR, "scope_key": SCOPE_KEY, "period_key": ym,
        "status": result["status"], "row_count": result.get("row_count"),
        "error_msg": result.get("error_msg"),
        "attempts": attempts + (0 if result["status"] == "done" else 1),
        "updated_at": datetime.datetime.now(KST).isoformat(),
    }], "merge-duplicates")


# ── 메인 ─────────────────────────────────────────────────────────────────────


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="서울 지하철 역사마스터 + 월별 승하차 API → raw JSON (결정 0045 PR⑥)", allow_abbrev=False)
    p.add_argument("--master", action="store_true", help="역사마스터만 받는다(달 수집 없음 · --end-month 불필요)")
    p.add_argument("--end-month", default=None, help="받을 가장 최근 달 YYYYMM (의무 — 포털 게시를 먼저 확인한다)")
    p.add_argument("--start-month", default=DEFAULT_START, help="씨앗 첫 달 (기본 202101 — 서울시 「2021년 이후」)")
    p.add_argument("--master-too", action="store_true", help="달 수집과 함께 역사마스터도 한 번")
    p.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    p.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS, help="한 번 실행의 API 호출 상한 (기본 300)")
    p.add_argument("--retry-failed", action="store_true", help="failed 달도 다시 받는다")
    p.add_argument("--dry-run", action="store_true", help="API 1회로 끝 달 행수만 보고 장부는 읽기만 (DB·파일 쓰기 0)")
    a = p.parse_args(argv)
    if not a.master and not a.end_month:
        p.error("--end-month YYYYMM 은 의무입니다(기본값 없음 — 포털 게시를 먼저 확인한다) · 마스터만이면 --master")
    a.month_list = [] if a.master else month_range(a.start_month, a.end_month)
    return a


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
    months = a.month_list

    print("=" * 72)
    if a.master:
        print("서울 지하철 역사마스터 수집")
    else:
        print("서울 지하철 승하차 수집 — {} ~ {} ({}달, 최신부터){}".format(
            months[0], months[-1], len(months), " + 역사마스터" if a.master_too else ""))
    print("=" * 72)

    if a.dry_run:
        try:
            service, ym = (MASTER_SERVICE, None) if a.master else (RIDE_SERVICE, months[0])
            code, total, _ = fetch_page(session, key, service, 1, 1, ym)
        except (ApiError, ServiceKeyError) as e:
            print("[에러] {}".format(e), file=sys.stderr)
            return 1
        print("  {} {} : {} · 행 {:,} · {}쪽".format(service, ym or "", code, total, max(1, -(-total // PAGE_SIZE))))
        if a.master:
            print("--dry-run — 파일·DB 에 아무것도 쓰지 않았습니다.")
            return 0
        if not total:
            print("  ⚠️ 끝 달이 0건입니다 — 아직 게시 안 된 달일 수 있습니다. --end-month 를 확인하세요.")
        progress = read_progress(base_url, headers)
        todo = todo_months(months, progress, a.retry_failed)
        print("  장부: done {} · pending {} · failed {} · 아직 씨앗 없음 {}".format(
            *(sum(1 for m in months if progress.get(m, ("",))[0] == s) for s in ("done", "pending", "failed")),
            sum(1 for m in months if m not in progress)))
        print("  이번에 받을 달 {}개 · 예상 호출 ≈ {:,}회{}".format(
            len(todo), len(todo), " + 마스터 1" if a.master_too else ""))
        print("--dry-run — 파일·DB 에 아무것도 쓰지 않았습니다.")
        return 0

    now = datetime.datetime.now(KST)
    fetched_date, fetched_at = now.strftime("%Y%m%d"), now.isoformat()
    calls = [0]
    if a.master or a.master_too:
        try:
            path = collect_master(session, key, a.raw_dir, fetched_date, fetched_at, calls)
        except ServiceKeyError as e:
            print("[멈춤] {} — 인증키·활용 신청을 확인하세요.".format(mask_secret(e, key)), file=sys.stderr)
            return 1
        except ApiError as e:
            print("[경고] 역사마스터 못 받음 — {}".format(mask_secret(e, key)), file=sys.stderr)
            return 1
        print("  역사마스터 → {}".format(path))
        if a.master:
            print("  다음: python scripts/collectors/load_seoul_subway.py --dry-run → 실적재 → post_load.py · --check")
            return 0

    seed_progress(base_url, headers, months)
    progress = read_progress(base_url, headers)
    todo = todo_months(months, progress, a.retry_failed)
    if not todo:
        print("받을 달이 없습니다 — 전부 done 입니다.")
        return 0
    done = left = 0
    for ym in todo:
        if calls[0] >= a.max_calls:
            print("  호출 상한 {:,}회에 닿았습니다 — 나머지는 다음 실행이 이어받습니다.".format(a.max_calls))
            left += 1
            break
        try:
            result = collect_month(session, key, ym, a.raw_dir, fetched_date, fetched_at, calls,
                                   max_calls=a.max_calls)
        except ServiceKeyError as e:
            print("[멈춤] {} — 인증키·활용 신청을 확인하세요.".format(mask_secret(e, key)), file=sys.stderr)
            return 1
        save_progress(base_url, headers, ym, result, progress.get(ym, ("", 0))[1])
        if result["status"] == "done":
            done += 1
            print("  {} done · {:,}행".format(ym, result["row_count"]))
        else:
            left += 1
            print("  [경고] {} {} — {}".format(ym, result["status"], result["error_msg"]))
    print("=" * 72)
    print("  done {} · 남은 것 {} · 호출 {:,}회".format(done, left, calls[0]))
    if done:
        print("  다음: python scripts/collectors/load_seoul_subway.py --dry-run → 실적재 → post_load.py · --check")
        print("  💾 원본이 늘었으니 python scripts/backup_raw.py 도 잊지 마세요.")
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main())
