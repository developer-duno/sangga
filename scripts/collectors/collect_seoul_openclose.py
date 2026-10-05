# -*- coding: utf-8 -*-
"""서울시 상권분석서비스(점포-상권 · OA-15577) 열린 API → raw JSONL 수집 (결정 0033).

무엇을 받나
-----------
서울시가 **분기마다 공표하는** 상권 1,650개 × 서비스 업종 100종의 점포 수·유사 업종 점포 수·
개업 점포 수·개업률·폐업 점포 수·폐업률·프랜차이즈 점포 수(국세청 사업자등록 기반). 우리가
계산하지 않는다 — 공표값을 그대로 받아 그대로 나른다(결정 0033 결정 1).

공식 명세 (2026-10-05 확인 — data.seoul.go.kr/dataList/openApiView.do?infId=OA-15577)
------------------------------------------------------------------------------------
  · 주소 꼴 = http://openapi.seoul.go.kr:8088/(인증키)/json/VwsmTrdarStorQq/(시작)/(끝)/(STDR_YYQU_CD)
    — 분기 코드는 `YYYYQ` 다섯 자리(예: 20262 = 2026년 2분기 · Q 글자 없음).
  · **한 번에 최대 1,000건**(넘으면 ERROR-336) → 분기 약 76,000행 ÷ 1,000 ≈ 76회 · 22분기 ≈ 1,700회.
  · 성공 = INFO-000 · **자료 없음 = INFO-200**('해당하는 데이터가 없습니다' — 아직 게시 안 된
    분기가 이렇게 온다. 2026-10-05 샘플키로 20263 실측: `{"RESULT":{"CODE":"INFO-200",…}}`,
    `row` 도 `list_total_count` 도 없다) · 인증키 오류 = INFO-100 · 서버 오류 = ERROR-500·600·601.
  · 일 호출 한도: 위 명세 페이지에는 **적혀 있지 않다**. 인증키 발급 화면 실측(사장님 · 2026-10-05
    · 메모리 prep-open-close 33줄)은 "호출 횟수 제한 없음 — 실시간 지하철 API 만 1일 1,000회"다.
    이 수집기를 만든 사람은 그 화면을 직접 보지 못했다(**미확인**). 그래서 한 번 실행의 상한
    `--max-calls`(기본 2,000 = 22분기 한 벌 + 여유)를 둔다 — 한도에 걸리면 다음 날 이어받기.
  · 응답 칸 14개는 영문 대문자이고 숫자가 실수(`156.0`)로 온다 — 해석은 적재기 몫이고 여기서는
    **원본 그대로** 적는다(raw 는 덮어쓰지 않는다 · 절대 규칙 6 · 수집 규칙).

이어받기 — `collect_progress` 의 pending 만
--------------------------------------------
분기 하나 = 작업 하나(collector='seoul_openclose' · scope_key='seoul' · period_key='20262').
  · 한 분기를 **끝까지** 받아 `list_total_count` 와 받은 행 수가 같을 때만 파일을 쓰고 `done`.
    중간에 끊기거나(네트워크·서버 오류) 수가 안 맞으면 **파일을 하나도 안 남기고** pending 그대로
    (오류 문구만 적는다) — 그래서 반쪽 분기 파일이 생기지 않는다.
  · ⛔ **0건(INFO-200 또는 list_total_count 0) 분기는 `done` 으로 굳히지 않는다.** 아직 게시 안 된
    분기를 '다 걷었다'로 굳히면 나중에 판이 떠도 이어받기가 안 본다(collect_rone 의 같은 함정 ·
    레포 CLAUDE.md 수집 규칙). pending 유지 + 경고.
  · ⛔ **`--end-quarter YYYYQ` 는 의무다(기본값 없음).** '지금 분기'를 기본으로 두면 아직 없는
    분기까지 씨앗을 뿌린다. 게시된 분기를 먼저 `--dry-run --end-quarter <분기>` 로 확인한다.
  · 최신 분기부터 거슬러 받는다(최근 판이 화면에 먼저 필요하다).

파일 — `data/raw/seoul_openclose/api/<분기>_<받은날짜 YYYYMMDD>.jsonl`
-----------------------------------------------------------------------
한 줄 = `{"quarter": "20262", "fetched_at": "…KST", "row": {…원본 행…}}`. 같은 분기를 다른 날 다시
받으면 **새 날짜 파일**(개정판 대비 — 적재기는 가장 최근 날짜 하나만 쓴다). 같은 날 같은 분기
파일이 이미 있으면: 내용이 같으면 그대로 두고 done, 다르면 **덮어쓰지 않고** pending + 오류 문구
(사람이 본다).

쓰는 법 (프로젝트 루트에서)
---------------------------
    python scripts/collectors/collect_seoul_openclose.py --dry-run --end-quarter 20262 --quarters 22
    python scripts/collectors/collect_seoul_openclose.py --end-quarter 20262 --quarters 22
    python scripts/collectors/collect_seoul_openclose.py --end-quarter 20263          # 새 분기 하나

`--dry-run` = API 1회(그 끝 분기 첫 1행으로 `list_total_count` 만) + collect_progress **읽기만**
(씨앗을 안 뿌린다 — DB 쓰기 0). 인증키는 `.env` 의 `SEOUL_OPENAPI_KEY`.
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
from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from collect_rone import get_supabase_config, rest_select, upsert_batch  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
DEFAULT_RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "seoul_openclose", "api")

API_BASE = "http://openapi.seoul.go.kr:8088"
SERVICE = "VwsmTrdarStorQq"
PAGE_SIZE = 1000          # 공식 명세: 한 번에 최대 1,000건(ERROR-336)
MAX_PAGES = 100           # 분기당 약 76페이지 — 이보다 많으면 무언가 이상한 것이다(멈춘다)
DEFAULT_QUARTERS = 1
DEFAULT_MAX_CALLS = 2000

COLLECTOR = "seoul_openclose"
SCOPE_KEY = "seoul"

CODE_OK = "INFO-000"
CODE_NO_DATA = "INFO-200"
CODE_BAD_KEY = "INFO-100"
RETRY_CODES = ("ERROR-500", "ERROR-600", "ERROR-601")

API_TIMEOUT_SEC = 60
RETRY_COUNT = 3
RETRY_BACKOFF_BASE_SEC = 2

KST = ZoneInfo("Asia/Seoul")
RE_QUARTER = re.compile(r"^(\d{4})([1-4])$")
SECRET_MASK = "***"


class ServiceKeyError(Exception):
    """인증키 문제(INFO-100) — 다시 돌려도 똑같이 실패한다. 전체를 멈춘다."""


class ApiError(Exception):
    """그 밖의 API 오류 — 그 분기만 pending 으로 남긴다."""


# ── 순수 로직 ────────────────────────────────────────────────────────────────


def parse_quarter(text):
    """'20262' → (2026, 2). 꼴이 다르면 ValueError(조용히 0건으로 흘려보내지 않는다)."""
    m = RE_QUARTER.match(str(text or "").strip())
    if not m:
        raise ValueError("분기는 YYYYQ 다섯 자리여야 합니다(예: 20262): {!r}".format(text))
    return int(m.group(1)), int(m.group(2))


def quarter_range(end_quarter, count):
    """end_quarter 에서 과거로 count 개 — **최신 분기부터** 거슬러 간다."""
    if count <= 0:
        raise ValueError("--quarters 는 1 이상이어야 합니다: {}".format(count))
    y, q = parse_quarter(end_quarter)
    out = []
    for _ in range(count):
        out.append("{:04d}{}".format(y, q))
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return out


def mask_secret(text, key=None):
    """주소 경로 속 인증키를 지운다(이 API 는 키가 쿼리가 아니라 **경로**에 든다)."""
    s = "" if text is None else str(text)
    s = re.sub(r"(:8088/)[^/\s'\"]+(/)", r"\1" + SECRET_MASK + r"\2", s)
    if key:
        s = s.replace(str(key), SECRET_MASK)
    return s


def page_url(key, quarter, start, end):
    return "{}/{}/json/{}/{}/{}/{}".format(API_BASE, key, SERVICE, start, end, quarter)


def read_envelope(payload):
    """응답을 (코드, 메시지, 총건수, 행 목록) 으로 푼다.

    정상: {"VwsmTrdarStorQq": {"list_total_count": N, "RESULT": {...}, "row": [...]}}
    오류·자료 없음: {"RESULT": {"CODE": "INFO-200", "MESSAGE": "..."}} (2026-10-05 실측)
    모양이 이상하면 코드가 빈 글자로 나와 아래 판정이 ApiError 로 보낸다.
    """
    if not isinstance(payload, dict):
        return "", "", 0, []
    body = payload.get(SERVICE)
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


def raw_file(raw_dir, quarter, fetched_date):
    return os.path.join(raw_dir, "{}_{}.jsonl".format(quarter, fetched_date))


def jsonl_text(quarter, rows, fetched_at):
    return "".join(
        json.dumps({"quarter": quarter, "fetched_at": fetched_at, "row": r},
                   ensure_ascii=False) + "\n"
        for r in rows)


# ── API ──────────────────────────────────────────────────────────────────────


def fetch_page(session, key, quarter, start, end, sleep=time.sleep,
               retry_count=RETRY_COUNT, backoff_base=RETRY_BACKOFF_BASE_SEC):
    """한 페이지 → (코드, 총건수, 행). INFO-100 은 ServiceKeyError, 그 밖의 오류는 ApiError.

    네트워크 오류·HTTP 5xx·ERROR-500/600/601 만 재시도한다. INFO-200(자료 없음)은 오류가
    아니라 **0건**으로 돌려준다 — 판정은 부른 쪽(collect_quarter)이 한다.
    """
    url = page_url(key, quarter, start, end)
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
                code, msg, total, rows = read_envelope(payload)
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


def collect_quarter(session, key, quarter, raw_dir, fetched_date, fetched_at,
                    call_counter, max_calls=None, **kwargs):
    """분기 하나를 끝까지 받아 결과 dict(status·row_count·error_msg)를 돌려준다.

    status 는 'done' 또는 'pending' 둘뿐이다 — 0건·중간 끊김·수 어긋남은 전부 pending(파일 0).
    ServiceKeyError 는 위로 올린다(전체를 멈춘다).
    """
    rows = []
    total = None
    page = 1
    try:
        while True:
            if max_calls is not None and call_counter[0] >= max_calls:
                return {"status": "pending", "row_count": None,
                        "error_msg": "한 번 실행 상한 {:,}회에 닿아 이 분기를 끝까지 못 받음 — "
                                     "다음 실행이 이어받는다(파일 안 씀)".format(max_calls)}
            start = (page - 1) * PAGE_SIZE + 1
            call_counter[0] += 1
            code, page_total, part = fetch_page(
                session, key, quarter, start, start + PAGE_SIZE - 1, **kwargs)
            if page == 1:
                total = page_total
                if code == CODE_NO_DATA or total == 0:
                    return {"status": "pending", "row_count": 0,
                            "error_msg": "0건 응답({}) — 아직 게시 안 된 분기로 보인다. done 으로 "
                                         "굳히지 않는다(게시 뒤 다시 돌리면 받는다)".format(
                                             code or "list_total_count=0")}
                if -(-total // PAGE_SIZE) > MAX_PAGES:
                    return {"status": "pending", "row_count": None,
                            "error_msg": "총 {:,}행 — 페이지 상한 {}을 넘는다. 모양이 바뀐 것으로 "
                                         "보고 멈춘다(파일 안 씀)".format(total, MAX_PAGES)}
            bad = [r.get("STDR_YYQU_CD") for r in part
                   if str(r.get("STDR_YYQU_CD", "")).strip() != quarter]
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
                "error_msg": "{}페이지에서 끊김 — 파일 안 씀: {}".format(page, mask_secret(e, key))[:500]}

    if len(rows) != total:
        return {"status": "pending", "row_count": len(rows),
                "error_msg": "받은 행 {:,}개 ≠ list_total_count {:,} — 반쪽 분기라 파일 안 씀".format(
                    len(rows), total)}

    path = raw_file(raw_dir, quarter, fetched_date)
    text = jsonl_text(quarter, rows, fetched_at)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old_rows = [json.loads(line)["row"] for line in f if line.strip()]
        if old_rows == rows:
            return {"status": "done", "row_count": len(rows),
                    "error_msg": "같은 날 같은 내용의 파일이 이미 있어 그대로 둠"}
        return {"status": "pending", "row_count": len(rows),
                "error_msg": "같은 날 내용이 다른 파일이 이미 있다 — 덮어쓰지 않음(raw 는 복구 불가). "
                             "사람이 확인: {}".format(path)}
    os.makedirs(raw_dir, exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)
    return {"status": "done", "row_count": len(rows), "error_msg": None}


# ── collect_progress ─────────────────────────────────────────────────────────


def seed_progress(base_url, headers, quarters):
    """분기마다 pending 씨앗. 이미 있는 행은 그대로(ignore-duplicates)."""
    rows = [{"collector": COLLECTOR, "scope_key": SCOPE_KEY, "period_key": q, "status": "pending"}
            for q in quarters]
    return upsert_batch(base_url, headers, "collect_progress", rows, "ignore-duplicates")


def read_progress(base_url, headers):
    """{분기: (상태, attempts)} — 이 수집기 행 전부(읽기만)."""
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=period_key,status,attempts&collector=eq.{}&scope_key=eq.{}".format(
            COLLECTOR, SCOPE_KEY),
        order="period_key")
    return {r["period_key"]: (r["status"], r.get("attempts") or 0) for r in rows}


def pending_quarters(quarters, progress):
    """이번에 받을 분기 — 장부에 없거나(아직 씨앗 전) pending 인 것만, 최신부터."""
    return [q for q in quarters if progress.get(q, ("pending", 0))[0] == "pending"]


def save_progress(base_url, headers, quarter, result, attempts):
    upsert_batch(base_url, headers, "collect_progress", [{
        "collector": COLLECTOR, "scope_key": SCOPE_KEY, "period_key": quarter,
        "status": result["status"], "row_count": result.get("row_count"),
        "error_msg": result.get("error_msg"),
        "attempts": attempts + (0 if result["status"] == "done" else 1),
        "updated_at": datetime.datetime.now(KST).isoformat(),
    }], "merge-duplicates")


def get_api_key():
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    key = os.environ.get("SEOUL_OPENAPI_KEY", "").strip()
    if not key:
        raise RuntimeError(".env 에 SEOUL_OPENAPI_KEY(서울 열린데이터광장 인증키)가 필요합니다.")
    return key


# ── 메인 ─────────────────────────────────────────────────────────────────────


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="서울시 상권분석서비스(점포-상권) API → raw JSONL (결정 0033)",
        allow_abbrev=False)
    p.add_argument("--end-quarter", required=True,
                   help="받을 가장 최근 분기 YYYYQ (의무 — 게시된 분기를 먼저 확인한다)")
    p.add_argument("--quarters", type=int, default=DEFAULT_QUARTERS,
                   help="끝 분기에서 거슬러 몇 분기 (기본 1 · 전부 = 22)")
    p.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    p.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS,
                   help="한 번 실행의 API 호출 상한 (기본 2,000)")
    p.add_argument("--dry-run", action="store_true",
                   help="API 1회로 끝 분기 행수만 보고 장부는 읽기만 (DB 쓰기 0)")
    a = p.parse_args(argv)
    a.quarter_list = quarter_range(a.end_quarter, a.quarters)
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
    quarters = a.quarter_list
    session = requests.Session()

    print("=" * 72)
    print("서울시 상권분석서비스(점포-상권) 수집 — {} ~ {} ({}분기, 최신부터)".format(
        quarters[0], quarters[-1], len(quarters)))
    print("=" * 72)

    if a.dry_run:
        try:
            code, total, _ = fetch_page(session, key, quarters[0], 1, 1)
        except (ApiError, ServiceKeyError) as e:
            print("[에러] {}".format(e), file=sys.stderr)
            return 1
        progress = read_progress(base_url, headers)
        todo = pending_quarters(quarters, progress)
        print("  끝 분기 {} : {} · 행 {:,}".format(quarters[0], code, total))
        if not total:
            print("  ⚠️ 끝 분기가 0건입니다 — 아직 게시 안 된 분기일 수 있습니다. --end-quarter 를 확인하세요.")
        print("  장부: done {} · pending {} · 아직 씨앗 없음 {}".format(
            sum(1 for q in quarters if progress.get(q, ("",))[0] == "done"),
            sum(1 for q in quarters if progress.get(q, ("",))[0] == "pending"),
            sum(1 for q in quarters if q not in progress)))
        print("  이번에 받을 분기 {}개 · 예상 호출 ≈ {:,}회 (분기당 ≈ {}회 가정)".format(
            len(todo), len(todo) * max(1, -(-total // PAGE_SIZE)), max(1, -(-total // PAGE_SIZE))))
        print("--dry-run — 파일·DB 에 아무것도 쓰지 않았습니다.")
        return 0

    seed_progress(base_url, headers, quarters)
    progress = read_progress(base_url, headers)
    todo = pending_quarters(quarters, progress)
    if not todo:
        print("받을 pending 분기가 없습니다 — 전부 done 입니다.")
        return 0

    now = datetime.datetime.now(KST)
    fetched_date, fetched_at = now.strftime("%Y%m%d"), now.isoformat()
    calls = [0]
    done = zero = left = 0
    for q in todo:
        try:
            result = collect_quarter(session, key, q, a.raw_dir, fetched_date, fetched_at,
                                     calls, max_calls=a.max_calls)
        except ServiceKeyError as e:
            print("[멈춤] {} — 인증키·활용 신청을 확인하세요.".format(e), file=sys.stderr)
            return 1
        save_progress(base_url, headers, q, result, progress.get(q, ("", 0))[1])
        if result["status"] == "done":
            done += 1
            print("  {} done · {:,}행".format(q, result["row_count"]))
        else:
            if result.get("row_count") == 0:
                zero += 1
            left += 1
            print("  [경고] {} pending 유지 — {}".format(q, result["error_msg"]))
        if calls[0] >= a.max_calls:
            print("  호출 상한 {:,}회에 닿았습니다 — 나머지는 다음 실행이 이어받습니다.".format(a.max_calls))
            break
    print("=" * 72)
    print("  done {} · pending 유지 {} (그중 0건 {}) · 호출 {:,}회".format(done, left, zero, calls[0]))
    if done:
        print("  다음: python scripts/collectors/load_seoul_openclose.py --dry-run")
        print("  💾 원본이 늘었으니 python scripts/backup_raw.py 도 잊지 마세요.")
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main())
