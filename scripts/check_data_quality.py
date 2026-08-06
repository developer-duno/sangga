# -*- coding: utf-8 -*-
"""
소상공인 상권정보 2026-03 분기 스냅샷 CSV 데이터 품질 검증 스크립트

무엇을 확인하나:
  1. 층정보 결측률
  2. 호정보 결측률
  3. PNU(지번코드) 19자리 형식 유효 비율
  4. 마포구(법정동코드 11440~) / 강남구(법정동코드 11680~) 행 수
  5. 층정보 실제 값 상위 20종 빈도
  6. 보조 정보 (전체 행 수, 파일별 행 수, 총 용량, 스킵된 비정상 행 수)

실행:
  PYTHONIOENCODING=utf-8 python D:\\sangga\\scripts\\check_data_quality.py

표준 라이브러리만 사용 (pandas 불필요).
CSV 를 한 줄씩 흘려보내며(스트리밍) 세기 때문에 1.4GB 여도 메모리를 거의 안 먹는다.
"""

import csv
import os
import re
import sys
from collections import Counter

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

# 원본 CSV 폴더 (읽기 전용 — 이 스크립트는 절대 파일을 수정하지 않는다)
DATA_DIR = os.path.join("D:", os.sep, "sangga", "data", "raw", "sangkwon")

# 파일 인코딩 — BOM(파일 맨 앞 보이지 않는 표식) 이 있어서 utf-8-sig
ENCODING = "utf-8-sig"

# 필요한 컬럼 이름 (인덱스 하드코딩 금지 — 파일마다 헤더 이름으로 찾는다)
COL_FLOOR = "층정보"
COL_UNIT = "호정보"
COL_PNU = "지번코드"      # PNU 19자리
COL_BJD = "법정동코드"     # 10자리

# 구별 집계 대상 (법정동코드 앞 5자리 = 시군구 코드)
GU_PREFIXES = {
    "11440": "마포구",
    "11680": "강남구",
}

# PNU 형식: 숫자 19자리
PNU_RE = re.compile(r"^\d{19}$")

# 층정보 값 상위 몇 종을 보여줄지
TOP_N_FLOOR = 20


def raise_field_size_limit():
    """CSV 한 칸(field)의 최대 길이 제한을 최대한 올린다.

    sys.maxsize 를 그대로 넣으면 윈도우에서 OverflowError 가 나므로
    성공할 때까지 절반씩 줄여가며 시도한다.
    """
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return limit
        except OverflowError:
            limit = int(limit / 10)


def fmt_pct(part, total):
    """비율을 % 문자열로. 분모가 0이면 'N/A'."""
    if total == 0:
        return "N/A"
    return "{:.2f}%".format(part * 100.0 / total)


def is_blank(value):
    """빈 문자열이거나 공백만 있으면 결측으로 본다."""
    return value is None or value.strip() == ""


def main():
    limit = raise_field_size_limit()

    if not os.path.isdir(DATA_DIR):
        print("[에러] 폴더를 찾을 수 없습니다: {}".format(DATA_DIR))
        return 1

    # 대상 파일 목록 (이름순)
    files = sorted(
        f for f in os.listdir(DATA_DIR)
        if f.lower().endswith(".csv")
    )
    if not files:
        print("[에러] CSV 파일이 없습니다: {}".format(DATA_DIR))
        return 1

    print("=" * 78)
    print("소상공인 상권정보 데이터 품질 검증")
    print("=" * 78)
    print("대상 폴더 : {}".format(DATA_DIR))
    print("대상 파일 : {}개".format(len(files)))
    print("CSV 필드 최대 길이 제한 : {:,}".format(limit))
    print("=" * 78)
    print("", flush=True)

    # ---- 전국 누적 집계 변수 ----
    total_rows = 0             # 정상 처리된 전체 행 수
    total_skipped = 0          # 헤더보다 짧아 스킵한 비정상 행 수
    total_bytes = 0            # 총 용량(바이트)

    floor_missing = 0          # 층정보 결측 건수
    unit_missing = 0           # 호정보 결측 건수
    pnu_valid = 0              # PNU 19자리 유효 건수

    gu_counts = {p: 0 for p in GU_PREFIXES}   # 구별 행 수
    floor_counter = Counter()                  # 층정보 값별 빈도 (비어있지 않은 값만)

    per_file_rows = []         # (파일명, 행수, 스킵수, 용량MB)

    # ---- 파일별 처리 ----
    for idx, name in enumerate(files, start=1):
        path = os.path.join(DATA_DIR, name)
        size = os.path.getsize(path)
        total_bytes += size

        f_rows = 0
        f_skipped = 0

        with open(path, encoding=ENCODING, newline="") as fp:
            reader = csv.reader(fp)

            try:
                header = next(reader)
            except StopIteration:
                print("  [경고] 빈 파일: {}".format(name), flush=True)
                per_file_rows.append((name, 0, 0, size / 1024.0 / 1024.0))
                continue

            # 헤더 이름 -> 인덱스 (앞뒤 공백/BOM 잔재 제거)
            header = [h.strip().lstrip("\ufeff") for h in header]
            col_index = {h: i for i, h in enumerate(header)}

            missing_cols = [
                c for c in (COL_FLOOR, COL_UNIT, COL_PNU, COL_BJD)
                if c not in col_index
            ]
            if missing_cols:
                print("  [경고] 필요한 컬럼 없음 {} -> 파일 건너뜀: {}".format(
                    missing_cols, name), flush=True)
                per_file_rows.append((name, 0, 0, size / 1024.0 / 1024.0))
                continue

            i_floor = col_index[COL_FLOOR]
            i_unit = col_index[COL_UNIT]
            i_pnu = col_index[COL_PNU]
            i_bjd = col_index[COL_BJD]
            n_cols = len(header)

            for row in reader:
                # 헤더보다 칸 수가 적은 깨진 행은 스킵하고 개수만 센다
                if len(row) < n_cols:
                    f_skipped += 1
                    continue

                f_rows += 1

                # 1) 층정보
                floor = row[i_floor]
                if is_blank(floor):
                    floor_missing += 1
                else:
                    floor_counter[floor.strip()] += 1

                # 2) 호정보
                if is_blank(row[i_unit]):
                    unit_missing += 1

                # 3) PNU 19자리 형식
                if PNU_RE.match(row[i_pnu].strip()):
                    pnu_valid += 1

                # 4) 구별 행 수 (법정동코드 앞 5자리)
                bjd = row[i_bjd].strip()
                prefix = bjd[:5]
                if prefix in gu_counts:
                    gu_counts[prefix] += 1

        total_rows += f_rows
        total_skipped += f_skipped
        mb = size / 1024.0 / 1024.0
        per_file_rows.append((name, f_rows, f_skipped, mb))

        print("[{:2d}/{:2d}] {} -> {:,}행 (스킵 {:,}행, {:,.1f}MB)".format(
            idx, len(files), name, f_rows, f_skipped, mb), flush=True)

    # ---- 결과 출력 ----
    print("")
    print("=" * 78)
    print("검증 결과 (전국)")
    print("=" * 78)

    print("")
    print("[ 1. 층정보 결측률 ]")
    print("  결측 {:,}건 / 전체 {:,}건  ->  {}".format(
        floor_missing, total_rows, fmt_pct(floor_missing, total_rows)))
    print("  (값이 있는 행: {:,}건, {})".format(
        total_rows - floor_missing,
        fmt_pct(total_rows - floor_missing, total_rows)))

    print("")
    print("[ 2. 호정보 결측률 ]")
    print("  결측 {:,}건 / 전체 {:,}건  ->  {}".format(
        unit_missing, total_rows, fmt_pct(unit_missing, total_rows)))
    print("  (값이 있는 행: {:,}건, {})".format(
        total_rows - unit_missing,
        fmt_pct(total_rows - unit_missing, total_rows)))

    print("")
    print("[ 3. PNU(지번코드) 19자리 형식 유효 비율 ]")
    print("  유효 {:,}건 / 전체 {:,}건  ->  {}".format(
        pnu_valid, total_rows, fmt_pct(pnu_valid, total_rows)))
    print("  무효(빈 값 포함) {:,}건  ->  {}".format(
        total_rows - pnu_valid,
        fmt_pct(total_rows - pnu_valid, total_rows)))

    print("")
    print("[ 4. 파일럿 대상 구별 행 수 ]")
    for prefix, gu_name in GU_PREFIXES.items():
        cnt = gu_counts[prefix]
        print("  {} (법정동코드 {}~) : {:,}건  ({})".format(
            gu_name, prefix, cnt, fmt_pct(cnt, total_rows)))

    print("")
    print("[ 5. 층정보 실제 값 상위 {}종 ]".format(TOP_N_FLOOR))
    nonblank_floor = total_rows - floor_missing
    print("  (비어있지 않은 층정보 {:,}건 기준 / 값 종류 총 {:,}종)".format(
        nonblank_floor, len(floor_counter)))
    print("  {:<4} {:<14} {:>14} {:>10} {:>10}".format(
        "순위", "층정보 값", "건수", "값기준비율", "전체비율"))
    print("  " + "-" * 56)
    for rank, (value, cnt) in enumerate(floor_counter.most_common(TOP_N_FLOOR), start=1):
        print("  {:<4} {:<14} {:>14,} {:>10} {:>10}".format(
            rank, value, cnt,
            fmt_pct(cnt, nonblank_floor),
            fmt_pct(cnt, total_rows)))

    print("")
    print("[ 6. 보조 정보 ]")
    print("  전체 행 수      : {:,}건".format(total_rows))
    print("  스킵된 비정상 행: {:,}건".format(total_skipped))
    print("  총 용량         : {:,.1f}MB".format(total_bytes / 1024.0 / 1024.0))
    print("  파일 수         : {}개".format(len(files)))
    print("")
    print("  [파일별 행 수]")
    print("  {:<58} {:>12} {:>8} {:>10}".format("파일명", "행수", "스킵", "용량(MB)"))
    print("  " + "-" * 92)
    for name, rows, skipped, mb in per_file_rows:
        print("  {:<58} {:>12,} {:>8,} {:>10,.1f}".format(name, rows, skipped, mb))

    print("")
    print("=" * 78)
    print("검증 완료")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
