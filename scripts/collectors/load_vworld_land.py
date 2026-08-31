# -*- coding: utf-8 -*-
"""브이월드 토지특성 raw JSONL → parcel 테이블 적재

`collect_vworld_land.py`가 받아둔 raw를 읽어 **필지당 1행**만 골라 `parcel`의
빈 칸(도로접면·개별공시지가·용도지역·지목·면적)을 채운다. 새 테이블을 만들지
않는다 — 컬럼은 `supabase/schema.sql`에 이미 정의돼 있고 지금까지 아무도 채우지
않던 자리다(2026-08-09 grep 확인).

⚠️ 이 적재기의 핵심 규칙 두 가지 (`docs/상세계획.md` §1.2 브이월드 박스):
  1. **같은 필지에 여러 행이 온다** — 연도별로 여러 개이고, 같은 연도 안에도
     2~3행이 온다(2023x2·2024x2·2025x3 실측). 그대로 넣으면 같은 필지가 여러 번
     반영된다. `pick_latest_row`로 **stdrYear 최대 → lastUpdtDt 최대 1행**만 쓴다.
     (`ladSn`으로 고르면 안 된다 — 전 행이 999999라 판별자가 못 된다.)
  2. **parcel에 없는 PNU는 만들지 않는다.** 우리 대상은 상권정보에서 나온 필지이고,
     그 밖의 PNU를 새로 만들면 화면·집계의 분모가 조용히 늘어난다. 없는 PNU는
     건너뛰고 그 수를 보고한다.

사용법:
  python scripts/collectors/load_vworld_land.py --dry-run
  python scripts/collectors/load_vworld_land.py
  python scripts/collectors/load_vworld_land.py --raw-dir data/raw/vworld_land/202608
"""

import argparse
import json
import os
import sys
import time
from collections import Counter

import requests
from dotenv import load_dotenv

_COLLECTORS_DIR = os.path.dirname(os.path.abspath(__file__))
if _COLLECTORS_DIR not in sys.path:
    sys.path.insert(0, _COLLECTORS_DIR)

from collect_vworld_land import (  # noqa: E402
    PROJECT_ROOT,
    RAW_SUBDIR,
    default_raw_dir,
    pick_latest_row,
    raw_path,
)

BATCH_SIZE = 500
SELECT_PAGE_SIZE = 1000
REST_TIMEOUT_SEC = 120

# 전국 시드(docs/decisions/0005 §[A] 결정 2 결함 1)와 같은 근거로, 배치 전송을
# collect_building_ledger.py의 fetch_page와 같은 패턴(RETRY_COUNT=3, 지수
# 백오프 2초·4초)으로 재시도한다.
RETRY_COUNT = 3
RETRY_BACKOFF_BASE_SEC = 2


# ── 순수 로직 (네트워크·DB 없음 — 테스트 대상) ─────────────────────────────────


def to_int(value):
    """정수로. 빈 값·숫자 아님이면 None (0을 None으로 만들지 않는다)."""
    s = str(value).strip() if value is not None else ""
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def to_float(value):
    s = str(value).strip() if value is not None else ""
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def clean_text(value):
    s = str(value).strip() if value is not None else ""
    return s or None


def build_parcel_update(pnu, row):
    """토지특성 1행 → parcel upsert용 dict.

    ⚠️ 키를 조건부로 빼지 않는다 — PostgREST 벌크 upsert는 배치 안에서 본 키들을
    대상 컬럼으로 삼기 때문에, 어떤 행에서만 키를 생략하면 매핑이 어긋난다
    (`load_sangkwon_snapshot.build_parcel_record`가 같은 이유로 값만 None으로 둔다).

    `bjd_code`·`sigungu_code`는 NOT NULL이라 upsert의 INSERT 경로에 필요하다.
    PNU에서 자르지 않고 **DB의 기존 값을 그대로 되돌려 넣는다**(호출부가 채운다) —
    자릿수 규칙을 코드가 다시 가정하지 않기 위해서다.
    """
    return {
        "pnu": pnu,
        "jimok": clean_text(row.get("lndcgrCodeNm")),
        "use_zone": clean_text(row.get("prposArea1Nm")),
        "road_contact": clean_text(row.get("roadSideCodeNm")),
        "land_price": to_int(row.get("pblntfPclnd")),
        "land_price_year": to_int(row.get("stdrYear")),
        "land_area_m2": to_float(row.get("lndpclAr")),
    }


def read_raw_records(path, counter=None):
    """raw JSONL을 (pnu, rows) 튜플로 흘려준다. 깨진 줄은 건너뛴다.

    수집 중 강제 종료로 반 줄이 남을 수 있다(append_jsonl이 한 줄씩 통째로 쓰지만
    파일시스템 수준에서 잘릴 가능성은 남는다). 한 줄이 깨졌다고 전체 적재를 포기하지
    않고, 몇 줄이 깨졌는지 보고한다.

    ⚠️ yield 되는 세 번째 값은 **그 줄까지의 누계**다. 마지막 정상 줄 뒤에 오는 깨진
    줄은 yield 할 기회가 없어 호출부에 전달되지 않는다 — 그런데 강제 종료로 잘리는
    것은 언제나 **마지막 줄**이라, 경고가 가장 필요한 상황에서 정확히 침묵했다
    (2026-08-09 재현 확인). 총수가 필요하면 `counter`(dict)를 넘긴다. 파일을 끝까지
    읽은 뒤 `counter["broken"]`에 총수가 들어간다.
    """
    broken = 0
    if counter is not None:
        counter["broken"] = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                broken += 1
                continue
            pnu = str(rec.get("pnu") or "").strip()
            rows = rec.get("rows")
            if not pnu or not isinstance(rows, list):
                broken += 1
                continue
            yield pnu, rows, broken
    if counter is not None:
        counter["broken"] = broken


def collapse_records(records):
    """raw 전체를 (pnu -> 최신 1행) 으로 접는다.

    같은 PNU가 raw에 두 번 이상 나올 수 있다(이어받기로 재수집했거나 회차가 겹칠 때).
    나중 줄이 더 최근 수집이므로, 같은 PNU면 `pick_latest_row`로 다시 한 번 겨룬다 —
    "나중 줄이 무조건 이긴다"로 하면 옛 연도만 담긴 재수집이 최신을 덮을 수 있다.
    """
    best = {}
    for pnu, rows in records:
        cand = pick_latest_row(rows)
        if cand is None:
            continue
        cur = best.get(pnu)
        best[pnu] = cand if cur is None else pick_latest_row([cur, cand])
    return best


# ── DB (Supabase REST) ───────────────────────────────────────────────────────


def get_supabase_config():
    load_dotenv()
    url = os.environ.get("SANGGA_SUPABASE_URL", "").strip().rstrip("/")
    key = (os.environ.get("SANGGA_SUPABASE_SERVICE_KEY")
           or os.environ.get("SANGGA_SUPABASE_ANON_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError(".env에 SANGGA_SUPABASE_URL과 키(SERVICE 또는 ANON)가 필요합니다.")
    return url, key


def _post_batch_with_retry(base_url, table, headers, data, batch_no, total_batches,
                           retry_count=RETRY_COUNT, backoff_base=RETRY_BACKOFF_BASE_SEC,
                           sleep=time.sleep):
    """배치 하나를 전송한다. 네트워크 오류·5xx는 지수 백오프로 재시도(최대
    retry_count회 시도), 4xx는 즉시 실패시킨다 — 요청 자체가 잘못된 것이라
    반복해도 같은 결과이기 때문이다(collect_building_ledger.py의 fetch_page와
    같은 구분).
    """
    last_err = None
    for attempt in range(1, retry_count + 1):
        try:
            r = requests.post(
                "{}/rest/v1/{}".format(base_url, table),
                headers=headers, data=data, timeout=REST_TIMEOUT_SEC,
            )
        except requests.RequestException as e:
            last_err = "네트워크 오류: {}".format(e)
        else:
            if r.status_code >= 500:
                last_err = "HTTP {}: {}".format(r.status_code, r.text[:300])
            elif r.status_code >= 300:
                raise RuntimeError("{} 저장 실패 (HTTP {}): {}".format(
                    table, r.status_code, r.text[:300]))
            else:
                return r
        if attempt < retry_count:
            wait = backoff_base ** attempt
            print("  [{}] 배치 {}/{} 전송 실패(시도 {}/{}) — {}초 뒤 재시도: {}".format(
                table, batch_no, total_batches, attempt, retry_count, wait, last_err),
                flush=True)
            sleep(wait)
    raise RuntimeError("{} 배치 {}/{} 저장 실패 — 재시도 {}회 소진: {}".format(
        table, batch_no, total_batches, retry_count, last_err))


def upsert_batch(base_url, headers, table, rows, batch_size=BATCH_SIZE, sleep=time.sleep):
    """rows를 batch_size 단위로 table에 upsert. 실제로 보낸 행 수를 돌려준다.

    배치 전송은 _post_batch_with_retry가 재시도한다(네트워크 오류·5xx만 — 4xx는
    즉시 실패). `sleep`은 테스트에서 실제로 기다리지 않도록 주입할 수 있다.
    """
    sent = 0
    total_batches = (len(rows) + batch_size - 1) // batch_size
    for i in range(0, len(rows), batch_size):
        part = rows[i:i + batch_size]
        batch_no = i // batch_size + 1
        req_headers = dict(headers, **{
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        })
        data = json.dumps(part, ensure_ascii=False).encode("utf-8")
        _post_batch_with_retry(
            base_url, table, req_headers, data, batch_no, total_batches, sleep=sleep,
        )
        sent += len(part)
    return sent


def fetch_existing_parcels(base_url, headers, page_size=SELECT_PAGE_SIZE):
    """pnu -> (bjd_code, sigungu_code) 전량. upsert의 INSERT 경로가 NOT NULL을 요구한다.

    ⚠️ limit/offset이 아니라 pnu 기준 **keyset** 페이지네이션을 쓴다
    (`pnu=gt.<직전 페이지 마지막 pnu>`). parcel이 전국 규모(110만 행)가 되면
    1,100페이지를 offset으로 넘기는 동안 다른 곳에서 INSERT가 일어날 수 있는데,
    offset 방식은 그 사이 앞쪽에 새 행이 끼어들면 뒤 페이지 전체가 밀려 일부
    행을 건너뛴다(docs/decisions/0005 §[A] 결정 2 결함 2). pnu는 PK(char(19))라
    정렬이 유일하게 결정되므로 "직전 페이지 마지막 pnu보다 큰 것"으로 다음
    페이지를 요청하면 밀림이 없다. 첫 페이지는 조건 없이 시작한다.
    """
    result = {}
    last_pnu = None
    while True:
        cursor = "&pnu=gt.{}".format(last_pnu) if last_pnu is not None else ""
        url = "{}/rest/v1/parcel?select=pnu,bjd_code,sigungu_code&order=pnu.asc&limit={}{}".format(
            base_url, page_size, cursor)
        r = requests.get(url, headers=headers, timeout=REST_TIMEOUT_SEC)
        if r.status_code >= 300:
            raise RuntimeError("parcel 조회 실패 (HTTP {}): {}".format(
                r.status_code, r.text[:300]))
        page = r.json()
        if not page:
            break
        for row in page:
            result[row["pnu"]] = (row["bjd_code"], row["sigungu_code"])
        last_pnu = page[-1]["pnu"]
        if len(page) < page_size:
            break
    return result


# ── 메인 ─────────────────────────────────────────────────────────────────────


def latest_raw_dir():
    """data/raw/vworld_land 아래 가장 최근 회차 폴더. 없으면 None."""
    root = os.path.join(PROJECT_ROOT, "data", "raw", RAW_SUBDIR)
    if not os.path.isdir(root):
        return None
    dirs = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    return os.path.join(root, dirs[-1]) if dirs else None


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="브이월드 토지특성 raw → parcel 적재")
    p.add_argument("--raw-dir", default=None, help="raw 폴더 (기본: 가장 최근 회차)")
    p.add_argument("--period-key", default=None, help="회차 키 YYYYMM (--raw-dir 대신)")
    p.add_argument("--dry-run", action="store_true", help="DB에 쓰지 않고 미리보기만")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.raw_dir:
        raw_dir = args.raw_dir
    elif args.period_key:
        raw_dir = default_raw_dir(args.period_key)
    else:
        raw_dir = latest_raw_dir()
    if not raw_dir or not os.path.isdir(raw_dir):
        print("raw 폴더가 없습니다. 먼저 collect_vworld_land.py 를 돌리세요.")
        return 1
    path = raw_path(raw_dir)
    if not os.path.isfile(path):
        print("raw 파일이 없습니다: {}".format(path))
        return 1

    records = []
    counter = {"broken": 0}
    for pnu, rows, _ in read_raw_records(path, counter):
        records.append((pnu, rows))
    broken = counter["broken"]
    best = collapse_records(records)

    base_url, sb_key = get_supabase_config()
    headers = {"apikey": sb_key, "Authorization": "Bearer {}".format(sb_key)}
    existing = fetch_existing_parcels(base_url, headers)

    updates = []
    stats = Counter()
    for pnu, row in sorted(best.items()):
        if pnu not in existing:
            stats["parcel에 없는 PNU(건너뜀)"] += 1
            continue
        rec = build_parcel_update(pnu, row)
        bjd, sgg = existing[pnu]
        rec["bjd_code"] = bjd
        rec["sigungu_code"] = sgg
        updates.append(rec)
        for col in ("road_contact", "land_price", "use_zone", "jimok", "land_area_m2"):
            if rec[col] is not None:
                stats["{} 채움".format(col)] += 1

    print("=" * 78)
    print("브이월드 토지특성 적재 {}".format("— dry-run (DB 쓰기 0)" if args.dry_run else ""))
    print("=" * 78)
    print("  raw 파일        {}".format(path))
    print("  raw 줄 수       {:,}".format(len(records)))
    if broken:
        print("  ⚠️ 깨진 줄      {:,} (건너뜀)".format(broken))
    print("  필지 수(중복 접은 뒤) {:,}".format(len(best)))
    print("  갱신 대상       {:,}".format(len(updates)))
    for k in sorted(stats):
        print("    {:<28} {:>7,}".format(k, stats[k]))
    if updates:
        s = updates[0]
        print("")
        print("  [ 표본 1건 ] {}".format(s["pnu"]))
        for col in ("jimok", "use_zone", "road_contact", "land_price",
                    "land_price_year", "land_area_m2"):
            print("    {:<16} {}".format(col, s[col]))
    print("=" * 78)

    if args.dry_run:
        print("dry-run 이므로 DB에 쓰지 않았습니다.")
        return 0
    # 실적재 모드인데 갱신 대상이 0건이면 **조용히 성공하지 않는다.**
    #
    # 이 적재기는 "바뀐 것만" 고르지 않는다 — raw 에 있고 parcel 에도 있는 PNU 를 전부 다시
    # 올린다. 그래서 0건은 "이미 다 채워서 할 일이 없다"가 아니라 **항상 이상 신호**다:
    # raw 가 비었거나(수집이 아무것도 못 받았다), raw 의 PNU 가 parcel 에 하나도 없거나
    # ([A] 전국 시드를 아직 안 돌렸다). 둘 다 사람이 손봐야 하는 상태인데, 종료코드 0 으로
    # 끝나면 자동화·다음 사람 눈에는 성공으로 보인다.
    # 형제 load_vworld_bulk.py 가 정확히 같은 경우를 1 로 막는다 — 규약을 맞춘다.
    if not updates:
        print("")
        print("[에러] 갱신 대상이 0건입니다.")
        if not best:
            print("  raw 파일에서 읽어낸 필지가 없습니다: {}".format(path))
            print("  → 수집(collect_vworld_land.py)이 실제로 받아 왔는지 먼저 확인하세요.")
        else:
            print("  raw 에는 필지 {:,}개가 있는데 그중 parcel 에 있는 것이 하나도 없습니다."
                  .format(len(best)))
            print("  → [A] 전국 시드(load_sangkwon_snapshot.py)가 먼저 실행돼야 합니다"
                  " (docs/decisions/0005 실행 순서 참조).")
        return 1
    sent = upsert_batch(base_url, headers, "parcel", updates)
    print("parcel 갱신 완료: {:,}행".format(sent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
