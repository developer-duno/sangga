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
  7. 층 표기 절대규칙(CLAUDE.md #4) 위반 후보 — '0' 값·정규화 불가 값
  8. 파일 단위 스킵/실패 목록

실행:
  python D:\\sangga\\scripts\\check_data_quality.py
  python D:\\sangga\\scripts\\check_data_quality.py --dir D:\\sangga\\data\\raw\\sangkwon_backfill

표준 라이브러리만 사용 (pandas 불필요).
CSV 를 한 줄씩 흘려보내며(스트리밍) 세기 때문에 1.4GB 여도 메모리를 거의 안 먹는다.
"""

import csv
import os
import re
import sys
from collections import Counter

from normalize_floor import normalize_floor

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

# 프로젝트 루트 (scripts/의 부모) — 하드코딩된 절대경로 대신 __file__ 기준으로 계산.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 원본 CSV 폴더 기본값 (읽기 전용 — 이 스크립트는 절대 파일을 수정하지 않는다).
# --dir 인자로 다른 폴더(백필 zip 해제 결과 등)를 지정할 수 있다.
DEFAULT_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "sangkwon")

# 파일 인코딩 — 2026-08-07 실측 결과 현재 배포본은 BOM 없는 순수 UTF-8이 확정됐다
# ("BOM이 있어서 utf-8-sig" 주석은 사실과 다름, 정정함). 다만 과거 분기 백필
# zip(2015~2022)에는 옛 포털이 CP949로 내보낸 파일이 섞여 있을 수 있어, utf-8-sig
# (BOM 있어도/없어도 안전)를 먼저 시도하고 실패하면 cp949로 순차 폴백한다.
ENCODING_CANDIDATES = ("utf-8-sig", "cp949")

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


class _EmptyFileError(Exception):
    """CSV 파일에 헤더 행조차 없음(완전히 빈 파일)."""


class _MissingColumnsError(Exception):
    """필요한 컬럼(층정보/호정보/지번코드/법정동코드) 중 일부가 헤더에 없음."""

    def __init__(self, missing_cols):
        super().__init__("필요한 컬럼 없음: {}".format(missing_cols))
        self.missing_cols = missing_cols


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
    """--dir 인자를 파싱해 사용할 데이터 폴더 경로를 돌려준다. 없으면 기본값."""
    _reject_unknown_args(argv, bool_flags=(), value_flags=("--dir",))
    data_dir = DEFAULT_DATA_DIR
    if "--dir" in argv:
        idx = argv.index("--dir")
        if idx + 1 >= len(argv):
            raise ValueError("--dir 뒤에 폴더 경로를 적어야 합니다.")
        data_dir = argv[idx + 1]
    return data_dir


def collect_csv_files(data_dir):
    """data_dir 이하를 재귀적으로 훑어 .csv 파일 경로 목록(정렬됨)을 돌려준다.

    백필 zip은 분기에 따라 구조가 다르다 — 2015Q4는 평면 CSV 18개, 2018Q2~
    2022Q4는 "2018년2분기/" 같은 하위 폴더 + 중첩 zip 해제 결과이므로 os.walk로
    재귀 탐색해야 전부 잡힌다.
    """
    result = []
    for root, _dirs, filenames in os.walk(data_dir):
        for fn in filenames:
            if fn.lower().endswith(".csv"):
                result.append(os.path.join(root, fn))
    return sorted(result)


def _process_file_with_encoding(path, encoding):
    """파일 하나를 주어진 인코딩으로 끝까지 읽어 집계 결과를 돌려준다.

    빈 파일이면 _EmptyFileError, 필요한 컬럼이 없으면 _MissingColumnsError를
    던진다. 인코딩이 안 맞으면 UnicodeDecodeError가 그대로 전파된다(호출부에서
    다음 인코딩으로 재시도하거나 최종 실패 처리).
    """
    f_rows = 0
    f_skipped_short = 0  # 헤더보다 칸 수가 적은 비정상 행
    f_skipped_over = 0   # 헤더보다 칸 수가 많은 비정상 행
    floor_missing = 0
    unit_missing = 0
    pnu_valid = 0
    gu_counts = {p: 0 for p in GU_PREFIXES}
    floor_counter = Counter()

    with open(path, encoding=encoding, newline="") as fp:
        reader = csv.reader(fp)

        try:
            header = next(reader)
        except StopIteration:
            raise _EmptyFileError()

        # 헤더 이름 -> 인덱스 (앞뒤 공백/BOM 잔재 제거)
        header = [h.strip().lstrip("\ufeff") for h in header]
        col_index = {h: i for i, h in enumerate(header)}

        missing_cols = [
            c for c in (COL_FLOOR, COL_UNIT, COL_PNU, COL_BJD)
            if c not in col_index
        ]
        if missing_cols:
            raise _MissingColumnsError(missing_cols)

        i_floor = col_index[COL_FLOOR]
        i_unit = col_index[COL_UNIT]
        i_pnu = col_index[COL_PNU]
        i_bjd = col_index[COL_BJD]
        n_cols = len(header)

        for row in reader:
            # 헤더와 칸 수가 다른(부족/초과 모두) 깨진 행은 처리하지 않고 별도 집계만 한다.
            if len(row) < n_cols:
                f_skipped_short += 1
                continue
            if len(row) > n_cols:
                f_skipped_over += 1
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

    return {
        "f_rows": f_rows,
        "f_skipped_short": f_skipped_short,
        "f_skipped_over": f_skipped_over,
        "floor_missing": floor_missing,
        "unit_missing": unit_missing,
        "pnu_valid": pnu_valid,
        "gu_counts": gu_counts,
        "floor_counter": floor_counter,
    }


def process_file(path):
    """인코딩 폴백(utf-8-sig → cp949)까지 포함해 파일 하나를 처리한다.

    반환: (사용된 인코딩, 집계 결과 dict)
    전파되는 예외: _EmptyFileError, _MissingColumnsError, UnicodeDecodeError,
    csv.Error, OSError — 전부 호출부(main)에서 스킵/실패로 분류해 처리한다.
    """
    last_unicode_exc = None
    for encoding in ENCODING_CANDIDATES:
        try:
            result = _process_file_with_encoding(path, encoding)
            return encoding, result
        except UnicodeDecodeError as e:
            last_unicode_exc = e
            continue
    if last_unicode_exc is None:
        raise RuntimeError("인코딩 후보가 없습니다 (ENCODING_CANDIDATES가 비어 있음).")
    raise last_unicode_exc


def main():
    # 콘솔이 cp949여도 한글 출력이 죽지 않도록 UTF-8로 고정 (형제 스크립트와 동일 패턴).
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    limit = raise_field_size_limit()

    try:
        data_dir = parse_args(sys.argv[1:])
    except ValueError as e:
        print("[에러] {}".format(e))
        return 2

    if not os.path.isdir(data_dir):
        print("[에러] 폴더를 찾을 수 없습니다: {}".format(data_dir))
        return 1

    # 대상 파일 목록 (하위 폴더까지 재귀 탐색, 경로순 정렬)
    files = collect_csv_files(data_dir)
    if not files:
        print("[에러] CSV 파일이 없습니다: {}".format(data_dir))
        return 1

    print("=" * 78)
    print("소상공인 상권정보 데이터 품질 검증")
    print("=" * 78)
    print("대상 폴더 : {}".format(data_dir))
    print("대상 파일 : {}개 (하위 폴더 재귀 포함)".format(len(files)))
    print("CSV 필드 최대 길이 제한 : {:,}".format(limit))
    print("=" * 78)
    print("", flush=True)

    # ---- 전국 누적 집계 변수 ----
    total_rows = 0                # 정상 처리된 전체 행 수
    total_skipped_short = 0       # 헤더보다 짧아 스킵한 행 수
    total_skipped_over = 0        # 헤더보다 길어 스킵한 행 수
    total_bytes = 0                # 총 용량(바이트)

    floor_missing = 0              # 층정보 결측 건수
    unit_missing = 0                # 호정보 결측 건수
    pnu_valid = 0                    # PNU 19자리 유효 건수

    gu_counts = {p: 0 for p in GU_PREFIXES}   # 구별 행 수
    floor_counter = Counter()                  # 층정보 값별 빈도 (비어있지 않은 값만)

    per_file_rows = []             # (파일명, 행수, 스킵수, 용량MB, 사용인코딩)
    skipped_files = []             # 빈 파일 / 필요 컬럼 없음 -> 통째로 건너뛴 파일명
    failed_files = []              # (파일명, 예외 설명) -> 읽는 중 예외로 실패한 파일

    # ---- 파일별 처리 ----
    for idx, path in enumerate(files, start=1):
        name = os.path.relpath(path, data_dir)

        try:
            size = os.path.getsize(path)
        except OSError as e:
            print("  [에러] 파일 크기 조회 실패: {} ({})".format(name, e), flush=True)
            failed_files.append((name, str(e)))
            per_file_rows.append((name, 0, 0, 0.0, "-"))
            continue
        total_bytes += size

        try:
            encoding_used, result = process_file(path)
        except _EmptyFileError:
            print("  [경고] 빈 파일: {}".format(name), flush=True)
            skipped_files.append(name)
            per_file_rows.append((name, 0, 0, size / 1024.0 / 1024.0, "-"))
            continue
        except _MissingColumnsError as e:
            print("  [경고] 필요한 컬럼 없음 {} -> 파일 건너뜀: {}".format(
                e.missing_cols, name), flush=True)
            skipped_files.append(name)
            per_file_rows.append((name, 0, 0, size / 1024.0 / 1024.0, "-"))
            continue
        except (UnicodeDecodeError, csv.Error, OSError) as e:
            # 한 파일의 예외로 전체 집계가 증발하지 않게 — 이 파일만 실패 처리하고 계속 진행.
            print("  [에러] 파일 처리 실패: {} ({}: {})".format(
                name, type(e).__name__, e), flush=True)
            failed_files.append((name, "{}: {}".format(type(e).__name__, e)))
            per_file_rows.append((name, 0, 0, size / 1024.0 / 1024.0, "-"))
            continue

        f_rows = result["f_rows"]
        f_skipped = result["f_skipped_short"] + result["f_skipped_over"]

        floor_missing += result["floor_missing"]
        unit_missing += result["unit_missing"]
        pnu_valid += result["pnu_valid"]
        for p in GU_PREFIXES:
            gu_counts[p] += result["gu_counts"][p]
        floor_counter.update(result["floor_counter"])

        total_rows += f_rows
        total_skipped_short += result["f_skipped_short"]
        total_skipped_over += result["f_skipped_over"]
        mb = size / 1024.0 / 1024.0
        per_file_rows.append((name, f_rows, f_skipped, mb, encoding_used))

        print("[{:2d}/{:2d}] {} ({}) -> {:,}행 (스킵 {:,}행, {:,.1f}MB)".format(
            idx, len(files), name, encoding_used, f_rows, f_skipped, mb), flush=True)

    total_skipped = total_skipped_short + total_skipped_over
    total_rows_with_skipped = total_rows + total_skipped

    # ---- 결과 출력 ----
    print("")
    print("=" * 78)
    print("검증 결과 (전국)")
    print("=" * 78)

    print("")
    print("[ 1. 층정보 결측률 ] (정상 파싱 {:,}건 기준, 스킵 포함 전체 {:,}건)".format(
        total_rows, total_rows_with_skipped))
    print("  결측 {:,}건 / 전체 {:,}건  ->  {}".format(
        floor_missing, total_rows, fmt_pct(floor_missing, total_rows)))
    print("  (값이 있는 행: {:,}건, {})".format(
        total_rows - floor_missing,
        fmt_pct(total_rows - floor_missing, total_rows)))

    print("")
    print("[ 2. 호정보 결측률 ] (정상 파싱 {:,}건 기준, 스킵 포함 전체 {:,}건)".format(
        total_rows, total_rows_with_skipped))
    print("  결측 {:,}건 / 전체 {:,}건  ->  {}".format(
        unit_missing, total_rows, fmt_pct(unit_missing, total_rows)))
    print("  (값이 있는 행: {:,}건, {})".format(
        total_rows - unit_missing,
        fmt_pct(total_rows - unit_missing, total_rows)))

    print("")
    print("[ 3. PNU(지번코드) 19자리 형식 유효 비율 ] (정상 파싱 {:,}건 기준, 스킵 포함 전체 {:,}건)".format(
        total_rows, total_rows_with_skipped))
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
    print("  전체 행 수(정상 파싱) : {:,}건".format(total_rows))
    print("  스킵된 비정상 행      : {:,}건 (부족 {:,} + 초과 {:,})".format(
        total_skipped, total_skipped_short, total_skipped_over))
    print("  스킵 포함 전체        : {:,}건".format(total_rows_with_skipped))
    print("  총 용량               : {:,.1f}MB".format(total_bytes / 1024.0 / 1024.0))
    print("  파일 수               : {}개".format(len(files)))
    print("")
    print("  [파일별 행 수]")
    print("  {:<58} {:>12} {:>8} {:>10} {:>8}".format(
        "파일명", "행수", "스킵", "용량(MB)", "인코딩"))
    print("  " + "-" * 100)
    for name, rows, skipped, mb, encoding_used in per_file_rows:
        print("  {:<58} {:>12,} {:>8,} {:>10,.1f} {:>8}".format(
            name, rows, skipped, mb, encoding_used))

    print("")
    print("[ 7. 층 표기 절대규칙 위반 후보 ] (CLAUDE.md 절대규칙 4 — 0 금지, 지하=-n, 옥탑=99)")
    floor_zero_count = floor_counter.get("0", 0)
    # 자체 정규식 휴리스틱 대신 실제 정규화 함수(normalize_floor)를 기준으로
    # 판정한다 — 실측 결과 정규식 방식이 246종·5,075행에서 실제 결과와 어긋났다
    # (예: "101"·"B103"·"15015" 같은 100 이상 애매값은 숫자 패턴엔 걸려
    # "정규화 가능"으로 오분류됐지만 normalize_floor는 실제로 None을 반환한다).
    unnormalizable_values = [v for v in floor_counter if normalize_floor(v) is None]
    floor_unnormalizable_count = sum(floor_counter[v] for v in unnormalizable_values)
    print("  '0' 값 건수            : {:,}건".format(floor_zero_count))
    print("  정규화 불가 후보 건수  : {:,}건 ({}종, 예: {})".format(
        floor_unnormalizable_count,
        len(unnormalizable_values),
        ", ".join(unnormalizable_values[:5]) if unnormalizable_values else "-"))

    print("")
    print("[ 8. 스킵/실패 파일 ]")
    if skipped_files:
        print("  스킵된 파일 ({}개):".format(len(skipped_files)))
        for n in skipped_files:
            print("    - {}".format(n))
    else:
        print("  스킵된 파일 없음")
    if failed_files:
        print("  실패한 파일 ({}개):".format(len(failed_files)))
        for n, err in failed_files:
            print("    - {} : {}".format(n, err))
    else:
        print("  실패한 파일 없음")

    print("")
    print("=" * 78)
    print("검증 완료")
    print("=" * 78)

    problem_count = len(skipped_files) + len(failed_files)
    if problem_count > 0 or total_rows == 0:
        print("[종료] 스킵/실패 {}건 또는 총 행 수 0 -> 비정상 종료(exit 1)".format(problem_count))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
