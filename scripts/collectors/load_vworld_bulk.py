# -*- coding: utf-8 -*-
"""브이월드 전국 토지특성 일괄 CSV(zip) → parcel 테이블 적재

`load_vworld_land.py`(API raw JSONL → parcel)와 **채우는 자리는 똑같고 원천만 다르다**.
브이월드 국가중점데이터 포털에서 반기마다 내려받는 시도별 전체데이터(AL) zip 17개를
읽어 `parcel`의 5+1 칸(지목·면적·용도지역·도로접면·공시지가·기준연도)을 채운다.

왜 API 대신 CSV인가 (2026-08-10 실측):
  강남 교집합 12,261필지에서 **API값과 4개 항목(도로접면·공시지가·지목·용도지역)이
  100.00% 일치**했다. 즉 일괄 CSV는 API와 같은 원천이다. 전국 110만 필지를 API로
  받으면 218일이 걸리지만 CSV는 17파일이면 끝난다(`docs/decisions/0003`).

⚠️ 이 적재기의 규칙 (형제 `load_vworld_land.py`에서 그대로 승계):
  1. **parcel에 없는 PNU는 만들지 않는다.** 우리 대상은 상권정보에서 나온 필지다.
     그 밖의 PNU를 새로 만들면 화면·집계의 분모가 조용히 늘어난다. 건너뛰고 센다.
  2. **raw는 건드리지 않는다.** zip은 읽기만 하고 압축을 풀지도 않는다.
  3. **collect_progress를 쓰지 않는다.** 로컬 배치 + 멱등 재실행이라 이어받기가
     필요 없다(`load_sangkwon_snapshot.py`의 명시된 전례와 같다). 진행 상황은
     파일(시도) 단위 출력으로 대신한다.
  4. **덮어쓰기 안전.** 이미 값이 있는 필지도 최신 스냅샷 값으로 덮어쓴다 —
     위 교차검증 100% 일치가 근거이고, 반기 갱신 때 재실행하기 위함이다.

메모리: 파일(시도) 1개를 다 읽은 뒤 그 파일 몫만 배치 upsert 하고 버퍼를 비운다.
전국 시드(parcel 110만) 뒤에도 한 번에 들고 있는 것은 시도 1개분뿐이다.

사용법:
  python scripts/collectors/load_vworld_bulk.py --dry-run
  python scripts/collectors/load_vworld_bulk.py
  python scripts/collectors/load_vworld_bulk.py --raw-dir data/raw/vworld_bulk/202605
"""

import argparse
import csv
import io
import os
import sys
import zipfile
from collections import Counter

_COLLECTORS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_COLLECTORS_DIR)
for _p in (_SCRIPTS_DIR, _COLLECTORS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from check_data_quality import PNU_RE, raise_field_size_limit  # noqa: E402
from load_vworld_land import (  # noqa: E402
    clean_text,
    fetch_existing_parcels,
    get_supabase_config,
    to_float,
    to_int,
    upsert_batch,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(_COLLECTORS_DIR))
RAW_SUBDIR = "vworld_bulk"

# 파일명 규격: AL_D195_<시도코드>_<기준일>.zip (AL=전체데이터. 변동데이터 CH는 안 쓴다)
ZIP_PREFIX = "AL_D195_"

# 이 CSV는 cp949다(2026-08-10 서울 파일 실측). 상권정보 CSV(utf-8-sig)와 다르므로
# ENCODING_CANDIDATES 자동판별을 쓰지 않고 고정한다 — 원천이 하나뿐이라 후보가 없다.
CSV_ENCODING = "cp949"

# CSV 컬럼(26개) 중 우리가 쓰는 것만. 이름으로 찾는다 — 인덱스 하드코딩 금지.
COL_PNU = "고유번호"
COL_MAP = (
    # (parcel 컬럼, CSV 컬럼, 변환 함수)
    ("jimok", "지목명", clean_text),
    ("use_zone", "용도지역명1", clean_text),
    ("road_contact", "도로접면", clean_text),
    ("land_price", "공시지가", to_int),
    ("land_price_year", "기준연도", to_int),
    ("land_area_m2", "토지면적", to_float),
)
REQUIRED_COLS = (COL_PNU,) + tuple(src for _dst, src, _fn in COL_MAP)
FILLABLE_COLS = tuple(dst for dst, _src, _fn in COL_MAP)


class MissingColumnsError(Exception):
    """CSV 헤더에 REQUIRED_COLS 중 일부가 없음."""

    def __init__(self, missing_cols, filename):
        super().__init__("{}: 필요한 컬럼 없음 {}".format(filename, missing_cols))
        self.missing_cols = missing_cols
        self.filename = filename


class EmptyFileError(Exception):
    """CSV에 헤더 행조차 없음."""


# ── 순수 로직 (네트워크·DB 없음 — 테스트 대상) ─────────────────────────────────


def build_col_index(header, filename):
    """헤더 이름 -> 인덱스. REQUIRED_COLS 중 빠진 게 있으면 MissingColumnsError."""
    header = [h.strip().lstrip("﻿") for h in header]
    idx = {h: i for i, h in enumerate(header)}
    missing = [c for c in REQUIRED_COLS if c not in idx]
    if missing:
        raise MissingColumnsError(missing, filename)
    return idx


def build_parcel_update(pnu, row, idx):
    """CSV 1행 → parcel upsert용 dict.

    ⚠️ 값이 없어도 키를 빼지 않는다 — PostgREST 벌크 upsert는 배치 안에서 본 키들을
    대상 컬럼으로 삼기 때문에, 어떤 행에서만 키를 생략하면 매핑이 어긋난다
    (`load_vworld_land.build_parcel_update`와 같은 이유).

    `bjd_code`·`sigungu_code`는 NOT NULL이라 upsert의 INSERT 경로에 필요하다.
    CSV의 법정동코드에서 자르지 않고 **DB의 기존 값을 그대로 되돌려 넣는다**
    (호출부가 채운다) — 자릿수 규칙을 코드가 다시 가정하지 않기 위해서다.
    """
    rec = {"pnu": pnu}
    for dst, src, fn in COL_MAP:
        rec[dst] = fn(row[idx[src]])
    return rec


def discover_zip_files(raw_dir):
    """raw_dir 안의 AL_D195_*.zip 목록(정렬). 하위 폴더는 보지 않는다 — 시도 파일은
    회차 폴더 하나에 평면으로 놓인다."""
    if not os.path.isdir(raw_dir):
        return []
    return sorted(
        os.path.join(raw_dir, n)
        for n in os.listdir(raw_dir)
        if n.upper().startswith(ZIP_PREFIX) and n.lower().endswith(".zip")
    )


def scan_zip_file(zip_path, existing, encoding=CSV_ENCODING):
    """zip 1개(=시도 1개)를 스트리밍으로 훑어 parcel 갱신 후보를 만든다.

    압축을 풀지 않고 zip 안의 CSV를 그대로 흘려 읽는다(797MB × 17을 디스크에
    다시 쓰지 않기 위함).

    반환 dict:
      file     파일명
      stats    Counter(rows / col_mismatch / invalid_pnu / not_in_parcel / dup_in_file)
      updates  dict(pnu -> upsert용 rec)  — 갱신 대상만
      filled   Counter(parcel 컬럼 -> 값이 들어간 건수)
    """
    name = os.path.basename(zip_path)
    stats = Counter()
    updates = {}

    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError(
                "{}: zip 안 CSV가 1개가 아닙니다 ({}개) — 파일 구조가 바뀌었는지 확인하세요.".format(
                    name, len(csv_names))
            )
        with zf.open(csv_names[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding=encoding, newline=""))
            try:
                header = next(reader)
            except StopIteration:
                raise EmptyFileError("{}: 헤더 행조차 없습니다.".format(name))
            idx = build_col_index(header, name)
            n_cols = len(header)
            i_pnu = idx[COL_PNU]

            for row in reader:
                stats["rows"] += 1
                if len(row) != n_cols:
                    stats["col_mismatch"] += 1
                    continue
                pnu = row[i_pnu].strip()
                if not PNU_RE.match(pnu):
                    # 특수 블록 지번(`중`·`단`·`주` 등 문자 포함). 전국 33,276건(0.09%) 실측.
                    stats["invalid_pnu"] += 1
                    continue
                if pnu not in existing:
                    stats["not_in_parcel"] += 1
                    continue
                if pnu in updates:
                    # 파일 내 중복은 실측 0건(서울 889,017행 전부 고유 PNU)이지만,
                    # 나더라도 같은 원천의 재게재이므로 마지막 행이 이기게 둔다.
                    stats["dup_in_file"] += 1
                rec = build_parcel_update(pnu, row, idx)
                bjd_code, sigungu_code = existing[pnu]
                rec["bjd_code"] = bjd_code
                rec["sigungu_code"] = sigungu_code
                updates[pnu] = rec

    filled = Counter()
    for rec in updates.values():
        for col in FILLABLE_COLS:
            if rec[col] is not None:
                filled[col] += 1

    return {"file": name, "stats": stats, "updates": updates, "filled": filled}


# ── 메인 ─────────────────────────────────────────────────────────────────────


def latest_raw_dir():
    """data/raw/vworld_bulk 아래 가장 최근 회차 폴더. 없으면 None."""
    root = os.path.join(PROJECT_ROOT, "data", "raw", RAW_SUBDIR)
    if not os.path.isdir(root):
        return None
    dirs = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    return os.path.join(root, dirs[-1]) if dirs else None


def default_raw_dir(period_key):
    return os.path.join(PROJECT_ROOT, "data", "raw", RAW_SUBDIR, period_key)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="브이월드 전국 토지특성 일괄 CSV → parcel 적재")
    p.add_argument("--raw-dir", default=None, help="zip 폴더 (기본: 가장 최근 회차)")
    p.add_argument("--period-key", default=None, help="회차 키 YYYYMM (--raw-dir 대신)")
    p.add_argument("--dry-run", action="store_true", help="DB에 쓰지 않고 미리보기만")
    return p.parse_args(argv)


def print_report(args, raw_dir, zips, totals, filled, sample, sent):
    print("=" * 78)
    print("브이월드 전국 토지특성 일괄 적재 {}".format(
        "— dry-run (DB 쓰기 0)" if args.dry_run else ""))
    print("=" * 78)
    print("  zip 폴더        {}".format(raw_dir))
    print("  파일 수         {}개".format(len(zips)))
    print("  읽은 행         {:,}".format(totals["rows"]))
    print("  PNU 형식 위반   {:,} (특수 블록 지번 — 건너뜀)".format(totals["invalid_pnu"]))
    print("  parcel 미보유   {:,} (만들지 않는다 — 세기만)".format(totals["not_in_parcel"]))
    if totals["col_mismatch"]:
        print("  ⚠️ 칸 수 불일치  {:,} (건너뜀)".format(totals["col_mismatch"]))
    if totals["dup_in_file"]:
        print("  ⚠️ 파일 내 중복 PNU {:,} (마지막 행이 이김)".format(totals["dup_in_file"]))
    print("  갱신 대상       {:,}".format(totals["matched"]))
    for col in FILLABLE_COLS:
        print("    {:<18} 채움 {:>9,}".format(col, filled[col]))
    if sample:
        print("")
        print("  [ 표본 1건 ] {}".format(sample["pnu"]))
        for col in FILLABLE_COLS:
            print("    {:<18} {}".format(col, sample[col]))
    print("=" * 78)
    if args.dry_run:
        print("dry-run 이므로 DB에 쓰지 않았습니다.")
    else:
        print("parcel 갱신 완료: {:,}행".format(sent))


def main(argv=None):
    # 윈도우 콘솔(cp949)에서 한글·⚠️ 를 찍다 UnicodeEncodeError 로 죽지 않게
    # (`load_sangkwon_snapshot.main`과 같은 처리).
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    args = parse_args(argv)
    if args.raw_dir:
        raw_dir = args.raw_dir
    elif args.period_key:
        raw_dir = default_raw_dir(args.period_key)
    else:
        raw_dir = latest_raw_dir()
    if not raw_dir or not os.path.isdir(raw_dir):
        print("zip 폴더가 없습니다. 브이월드 포털에서 시도별 전체데이터(AL)를 먼저 받으세요.")
        return 1

    zips = discover_zip_files(raw_dir)
    if not zips:
        print("{} 안에 {}*.zip 이 없습니다.".format(raw_dir, ZIP_PREFIX))
        return 1

    raise_field_size_limit()

    # dry-run 이어도 parcel 목록은 읽어야 한다 — "갱신 대상"이 곧 parcel 보유 여부다.
    # (읽기만 한다. 쓰기는 --dry-run 이 아닐 때만.)
    base_url, sb_key = get_supabase_config()
    headers = {"apikey": sb_key, "Authorization": "Bearer {}".format(sb_key)}
    print("parcel PNU 목록 읽는 중...", flush=True)
    existing = fetch_existing_parcels(base_url, headers)
    print("  parcel 보유 PNU {:,}개".format(len(existing)), flush=True)

    totals = Counter()
    filled = Counter()
    sample = None
    sent = 0

    for path in zips:
        result = scan_zip_file(path, existing)
        stats = result["stats"]
        matched = len(result["updates"])
        totals.update(stats)
        totals["matched"] += matched
        filled.update(result["filled"])
        print("  {:<28} {:>10,}행  매칭 {:>8,}  특수지번 {:>6,}  미보유 {:>10,}".format(
            result["file"], stats["rows"], matched,
            stats["invalid_pnu"], stats["not_in_parcel"]), flush=True)

        if sample is None and result["updates"]:
            sample = next(iter(result["updates"].values()))
        if not args.dry_run and result["updates"]:
            # 파일 1개 몫만 보내고 버퍼를 비운다(전국 시드 후 메모리 폭주 방지).
            sent += upsert_batch(base_url, headers, "parcel",
                                 list(result["updates"].values()))

    print_report(args, raw_dir, zips, totals, filled, sample, sent)

    # 실적재 모드(dry-run 아님)인데 갱신 대상이 0건이면 조용히 성공하지 않는다.
    # [A] 전국 시드(load_sangkwon_snapshot.py) 전에 실수로 이 스크립트를 먼저
    # 돌리면 parcel에 PNU가 하나도 없어 전량이 "미보유"로 세어지고 exit 0으로
    # 끝난다 — 다음 사람이 원인을 모른 채 "성공했는데 왜 안 채워졌지" 헤맨다
    # (docs/decisions/0005 §[A] 결정 2 결함 3, 형제 load_sangkwon_snapshot.py의
    # "적재할 행이 없습니다" 가드와 같은 취지).
    if not args.dry_run and not totals["matched"]:
        print("")
        print("[에러] 갱신 대상이 0건입니다 — parcel에 이 CSV들의 PNU가 하나도 없습니다.")
        print("  [A] 전국 시드(load_sangkwon_snapshot.py)가 먼저 실행돼야 합니다"
              " (docs/decisions/0005 실행 순서 참조).")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
