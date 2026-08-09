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


def rest_select(base_url, headers, table, query, page_size=SELECT_PAGE_SIZE, order="pnu"):
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


def upsert_batch(base_url, headers, table, rows, batch_size=BATCH_SIZE):
    sent = 0
    for i in range(0, len(rows), batch_size):
        part = rows[i:i + batch_size]
        r = requests.post(
            "{}/rest/v1/{}".format(base_url, table),
            headers=dict(headers, **{
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            }),
            data=json.dumps(part, ensure_ascii=False).encode("utf-8"),
            timeout=REST_TIMEOUT_SEC,
        )
        if r.status_code >= 300:
            raise RuntimeError("{} 저장 실패 (HTTP {}): {}".format(
                table, r.status_code, r.text[:300]))
        sent += len(part)
    return sent


def fetch_existing_parcels(base_url, headers):
    """pnu -> (bjd_code, sigungu_code). upsert의 INSERT 경로가 NOT NULL을 요구한다."""
    rows = rest_select(base_url, headers, "parcel", "select=pnu,bjd_code,sigungu_code")
    return {r["pnu"]: (r["bjd_code"], r["sigungu_code"]) for r in rows}


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
    if not updates:
        print("갱신할 것이 없습니다.")
        return 0
    sent = upsert_batch(base_url, headers, "parcel", updates)
    print("parcel 갱신 완료: {:,}행".format(sent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
