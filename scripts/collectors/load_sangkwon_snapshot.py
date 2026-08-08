# -*- coding: utf-8 -*-
"""
소상공인 상권정보 분기 스냅샷 CSV → Supabase 적재 (parcel + unit_business)

Phase 1 ③ 강남구 2026Q1 적재. `docs/상세계획.md` §5.6(품질 지표)·§4.2(PNU 조립)·
`anthropic-skills:budongsan-data` 규격을 따른다.

무엇을 하나:
  1. data/raw/sangkwon/*.csv (전국 17개 시도 파일)를 훑어 --sigungu-code(기본
     11680=강남구)에 해당하는 행만 추출한다. 상권정보에는 PNU(지번코드)가 이미
     있으므로 이걸 마스터로 삼는다(스킬 규격 "PNU 조립" 절).
  2. PNU 단위로 중복 제거해 parcel 테이블 행을 만든다 (공시지가·도로접면 등
     이 소스에 없는 필드는 비워두고 이후 수집기가 채운다 — upsert가 payload에
     없는 컬럼은 건드리지 않으므로 안전).
  3. 행 단위로 unit_business 테이블 행(분기 스냅샷, append only)을 만든다.
     §3.3 실측대로 이 소스의 호정보는 100% 결측이므로 unit_id는 항상 NULL —
     호실 축(unit/building)은 건축물대장 전유부가 있어야 채울 수 있다(§5.1
     의존순서). 그 규모 산정은 --dry-run 출력의 "건축물대장 다음 단계" 참고.
  4. 층정보는 scripts/normalize_floor.py의 normalize_floor()로 정규화한다
     (재구현 금지 — 이 프로젝트의 정본).

이어받기(collect_progress)를 쓰지 않는 이유:
  이 스크립트는 이미 로컬에 받아둔 CSV를 한 번 훑어 적재하는 로컬 배치 작업이라
  (API 호출이 아님) load_bjd_code.py와 동일하게 collect_progress가 필요 없다.
  upsert 자체가 멱등이라(parcel=merge-duplicates, unit_business=ignore-duplicates
  — 아래 TABLE_UPSERT_RESOLUTION 참조) 중간에 실패해도 재실행하면 안전하다.
  unit_business는 append-only 불변식(schema.sql "절대 UPDATE/DELETE 하지 않는다")
  때문에 재실행해도 기존 분기 스냅샷 행을 덮어쓰지 않고 신규 행만 추가된다.

사용법:
  python scripts/collectors/load_sangkwon_snapshot.py --dry-run
  python scripts/collectors/load_sangkwon_snapshot.py
  python scripts/collectors/load_sangkwon_snapshot.py --sigungu-code 11440 --gu-name 마포구
  python scripts/collectors/load_sangkwon_snapshot.py --dir data/raw/sangkwon_backfill/2015Q4 --snapshot-ym 201512
"""

import csv
import os
import re
import sys
from collections import Counter

import requests
from dotenv import load_dotenv

# scripts/ 를 sys.path에 넣어 normalize_floor를 import (재구현 금지 — 정본 재사용)
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from normalize_floor import normalize_floor  # noqa: E402
from check_data_quality import (  # noqa: E402
    ENCODING_CANDIDATES,
    PNU_RE,
    collect_csv_files,
    raise_field_size_limit,
)

# ── 설정 ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "sangkwon")

DEFAULT_SIGUNGU_CODE = "11680"  # 강남구
DEFAULT_GU_NAME = "강남구"

BATCH_SIZE = 1000
TIMEOUT_SEC = 120

# §5.6 목표선
PNU_MATCH_RATE_TARGET = 95.0

# 건축물대장(건축HUB) 건물 1개(=PNU 1개)당 예상 호출 수 — 표제부 + 층별개요 + 전유부
# (§3.1 항목 3·4. 각각 별도 엔드포인트). 페이지네이션 없이 1콜씩 든다고 가정한
# 보수적 추정치 — 실제 착수 시 재산정 필요.
BLDRGST_CALLS_PER_PNU = 3
DAILY_API_LIMIT = 10_000  # 공공데이터포털 API별 일 한도(개발계정, CLAUDE.md 수집 규칙)

# CSV 헤더에서 찾아야 하는 컬럼 이름 (인덱스 하드코딩 금지 — 이름으로 찾는다)
REQUIRED_COLS = (
    "상가업소번호", "상호명", "지점명",
    "상권업종대분류코드", "상권업종대분류명",
    "상권업종중분류코드", "상권업종중분류명",
    "상권업종소분류코드", "상권업종소분류명",
    "표준산업분류코드",
    "시도명", "시군구코드", "시군구명",
    "법정동코드", "법정동명",
    "지번코드", "지번본번지", "지번부번지",
    "도로명주소",
    "층정보", "호정보",
    "경도", "위도",
)

# 원본 파일명 끝의 "_YYYYMM.csv"에서 스냅샷 기준월을 뽑는다.
# 예: 소상공인시장진흥공단_상가(상권)정보_서울_202603.csv -> "202603"
RE_SNAPSHOT_YM = re.compile(r"_(\d{6})\.csv$", re.IGNORECASE)

# --snapshot-ym 으로 사용자가 직접 넣은 값은 파일명에서 뽑히는 게 아니라 검증
# 없이 그대로 쓰였다 — YYYYMM 6자리 숫자인지 실행 전에 확인한다.
SNAPSHOT_YM_RE = re.compile(r"^\d{6}$")

# upsert 시 테이블별 PostgREST 충돌 해소 정책 (Prefer: resolution=...).
#   parcel        merge-duplicates  — 공시지가·도로접면 등 후속 수집기가 같은
#                                      PNU 행을 채워나가므로 값 갱신을 허용한다.
#   unit_business ignore-duplicates — schema.sql "절대 UPDATE/DELETE 하지 않는다"
#                                      (append-only) 불변식. 기존 분기 스냅샷
#                                      행은 보존하고 신규 행만 추가한다(재실행해도
#                                      과거 스냅샷이 덮어써지지 않음).
TABLE_UPSERT_RESOLUTION = {
    "parcel": "merge-duplicates",
    "unit_business": "ignore-duplicates",
}


class MissingColumnsError(Exception):
    """CSV 헤더에 REQUIRED_COLS 중 일부가 없음."""

    def __init__(self, missing_cols, filename):
        super().__init__("{}: 필요한 컬럼 없음 {}".format(filename, missing_cols))
        self.missing_cols = missing_cols
        self.filename = filename


class EmptyFileError(Exception):
    """CSV 파일에 헤더 행조차 없음."""


# ── 순수 로직 (네트워크·DB 없음 — 테스트 대상) ─────────────────────────────────


def detect_snapshot_ym(filenames):
    """파일명 목록에서 스냅샷 기준월(YYYYMM)을 뽑는다.

    전부 같은 기준월이어야 한다 — 다르면 서로 다른 분기 파일이 섞인 것이므로
    에러를 낸다(추측으로 하나를 고르지 않는다).
    """
    yms = set()
    for name in filenames:
        m = RE_SNAPSHOT_YM.search(os.path.basename(name))
        if m:
            yms.add(m.group(1))
    if not yms:
        raise ValueError(
            "파일명에서 스냅샷 기준월(_YYYYMM.csv)을 찾지 못했습니다. "
            "--snapshot-ym 으로 직접 지정하세요."
        )
    if len(yms) > 1:
        raise ValueError(
            "파일명들의 스냅샷 기준월이 서로 다릅니다: {}. "
            "--dir 로 한 분기 폴더만 지정하거나 --snapshot-ym 으로 직접 지정하세요.".format(
                sorted(yms)
            )
        )
    return next(iter(yms))


def _to_float(raw):
    """빈 값/파싱 불가는 None. 그 외 float 변환."""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def format_jibun(bonbeon, bubeon):
    """지번본번지·지번부번지 -> '358-1' 형식 (스킬 규격 jibun = 본번-부번).

    부번이 없거나 '0'이면 부번 없이 본번만 돌려준다. 본번이 없으면 None.
    """
    bon = (bonbeon or "").strip()
    bu = (bubeon or "").strip()
    if not bon:
        return None
    if bu and bu != "0":
        return "{}-{}".format(bon, bu)
    return bon


def classify_invalid_pnu(raw_pnu):
    """PNU 무효 사유를 사람이 읽는 문자열로 분류한다 (§5.6 원인 상위 유형 보고용)."""
    s = (raw_pnu or "").strip()
    if not s:
        return "빈 값"
    if not s.isdigit():
        return "숫자가 아닌 문자 포함"
    if len(s) != 19:
        return "길이가 19자리가 아님 ({}자리)".format(len(s))
    return "기타"


def build_col_index(header, filename):
    """헤더 이름 -> 인덱스. REQUIRED_COLS 중 빠진 게 있으면 MissingColumnsError."""
    header = [h.strip().lstrip("﻿") for h in header]
    idx = {h: i for i, h in enumerate(header)}
    missing = [c for c in REQUIRED_COLS if c not in idx]
    if missing:
        raise MissingColumnsError(missing, filename)
    return idx


def build_parcel_record(row, idx):
    """행 하나에서 parcel 테이블 upsert용 dict를 만든다. PNU는 호출부에서 유효성 확인.

    lat/lng/geom은 값이 없어도 키 자체는 항상 유지하고 값만 None으로 둔다 — 배치
    안의 다른 행이 그 키를 갖고 있으면 PostgREST 벌크 insert는 배치 전체에서
    본 키 컬럼을 대상으로 삼으므로, 이 행에서만 키를 통째로 생략하면 예기치
    않은 매핑이 생길 수 있다.
    """
    pnu = row[idx["지번코드"]].strip()
    rec = {
        "pnu": pnu,
        "bjd_code": row[idx["법정동코드"]].strip() or None,
        "sigungu_code": row[idx["시군구코드"]].strip() or None,
        "sido_nm": row[idx["시도명"]].strip() or None,
        "sigungu_nm": row[idx["시군구명"]].strip() or None,
        "emd_nm": row[idx["법정동명"]].strip() or None,
        "jibun": format_jibun(row[idx["지번본번지"]], row[idx["지번부번지"]]),
        "road_addr": row[idx["도로명주소"]].strip() or None,
    }
    lat = _to_float(row[idx["위도"]])
    lng = _to_float(row[idx["경도"]])
    rec["lat"] = lat
    rec["lng"] = lng
    rec["geom"] = (
        "SRID=4326;POINT({} {})".format(lng, lat)
        if (lat is not None and lng is not None) else None
    )
    return rec


def build_unit_business_record(row, idx, snapshot_ym, floor_no):
    """행 하나에서 unit_business 테이블 insert용 dict를 만든다.

    unit_id는 이 단계에서 항상 None(건축물대장 전유부 매칭은 다음 단계).
    pnu는 19자리 형식일 때만 채우고, 아니면 None(스키마가 허용하는 매칭 실패).
    """
    raw_pnu = row[idx["지번코드"]].strip()
    pnu = raw_pnu if PNU_RE.match(raw_pnu) else None
    rec = {
        "snapshot_ym": snapshot_ym,
        "biz_no": row[idx["상가업소번호"]].strip(),
        "unit_id": None,
        "pnu": pnu,
        "floor_no": floor_no,
        "ho": row[idx["호정보"]].strip() or None,
        "biz_name": row[idx["상호명"]].strip() or None,
        "branch_nm": row[idx["지점명"]].strip() or None,
        "cat_l_cd": row[idx["상권업종대분류코드"]].strip() or None,
        "cat_l_nm": row[idx["상권업종대분류명"]].strip() or None,
        "cat_m_cd": row[idx["상권업종중분류코드"]].strip() or None,
        "cat_m_nm": row[idx["상권업종중분류명"]].strip() or None,
        "cat_s_cd": row[idx["상권업종소분류코드"]].strip() or None,
        "cat_s_nm": row[idx["상권업종소분류명"]].strip() or None,
        "ksic_cd": row[idx["표준산업분류코드"]].strip() or None,
        "road_addr": row[idx["도로명주소"]].strip() or None,
    }
    lat = _to_float(row[idx["위도"]])
    lng = _to_float(row[idx["경도"]])
    rec["lat"] = lat
    rec["lng"] = lng
    rec["geom"] = (
        "SRID=4326;POINT({} {})".format(lng, lat)
        if (lat is not None and lng is not None) else None
    )
    return rec


def estimate_bldrgst_scale(unique_pnu_count):
    """건축물대장 API 호출 규모를 추정한다 (실행하지 않음 — 산정만).

    반환: dict(unique_pnu, calls_per_pnu, total_calls, daily_limit,
               fits_in_one_day, days_needed)
    """
    total_calls = unique_pnu_count * BLDRGST_CALLS_PER_PNU
    fits = total_calls <= DAILY_API_LIMIT
    days_needed = 1 if fits else -(-total_calls // DAILY_API_LIMIT)  # ceil
    return {
        "unique_pnu": unique_pnu_count,
        "calls_per_pnu": BLDRGST_CALLS_PER_PNU,
        "total_calls": total_calls,
        "daily_limit": DAILY_API_LIMIT,
        "fits_in_one_day": fits,
        "days_needed": days_needed,
    }


# ── CSV 스캔 (파일 I/O — 네트워크·DB 없음) ─────────────────────────────────────


def _process_one_file(path, encoding, sigungu_code, snapshot_ym):
    """파일 하나를 스트리밍으로 읽어 대상 시군구 행만 반영한 결과를 돌려준다.

    결과는 이 호출 안에서만 쓰이는 로컬 컨테이너에 모은다(공유 컨테이너에 바로
    누적하지 않음). 인코딩이 안 맞아 중간에 UnicodeDecodeError 로 끊기면 그때까지
    쌓인 로컬 결과는 이 함수 밖으로 아예 안 나가고 통째로 버려진다 — 그래야
    호출부가 다음 인코딩으로 파일을 처음부터 재시도할 때 이미 읽었던 행이
    중복 축적되지 않는다 (check_data_quality._process_file_with_encoding의
    "성공 시에만 반환" 패턴과 동일).

    반환 dict: matched, col_mismatch_skipped, parcel_by_pnu(dict), unit_business_records
               (list), floor_counter(Counter), invalid_pnu_reasons(Counter).
    """
    name = os.path.basename(path)
    matched = 0
    col_mismatch_skipped = 0
    parcel_by_pnu = {}
    unit_business_records = []
    floor_counter = Counter()
    invalid_pnu_reasons = Counter()

    with open(path, encoding=encoding, newline="") as fp:
        reader = csv.reader(fp)
        try:
            header = next(reader)
        except StopIteration:
            raise EmptyFileError()
        idx = build_col_index(header, name)
        i_sgg = idx["시군구코드"]
        n_cols = len(header)

        for row in reader:
            if len(row) != n_cols:
                col_mismatch_skipped += 1  # 헤더와 칸 수 다른 비정상 행 — 리포트에 병기
                continue
            if row[i_sgg].strip() != sigungu_code:
                continue

            matched += 1
            floor_raw = row[idx["층정보"]]
            floor_no = normalize_floor(floor_raw)
            floor_counter[floor_raw.strip() if floor_raw and floor_raw.strip() else "(결측)"] += 1

            raw_pnu = row[idx["지번코드"]].strip()
            if PNU_RE.match(raw_pnu):
                if raw_pnu not in parcel_by_pnu:
                    parcel_by_pnu[raw_pnu] = build_parcel_record(row, idx)
            else:
                invalid_pnu_reasons[classify_invalid_pnu(raw_pnu)] += 1

            unit_business_records.append(
                build_unit_business_record(row, idx, snapshot_ym, floor_no)
            )

    return {
        "matched": matched,
        "col_mismatch_skipped": col_mismatch_skipped,
        "parcel_by_pnu": parcel_by_pnu,
        "unit_business_records": unit_business_records,
        "floor_counter": floor_counter,
        "invalid_pnu_reasons": invalid_pnu_reasons,
    }


def scan_and_build(data_dir, sigungu_code, snapshot_ym):
    """data_dir 이하 모든 CSV를 훑어 parcel/unit_business 적재 후보를 만든다.

    반환 dict:
      per_file        [(파일명, 매치행수), ...]
      total_matched   대상 시군구 매치 총 행수
      parcel_records  list[dict]  (PNU 유효한 행만, PNU 기준 중복 제거)
      unit_business_records  list[dict]  (매치된 모든 행 — PNU 무효도 포함)
      floor_counter   Counter(원본 층정보 값 -> 건수)
      invalid_pnu_reasons  Counter(사유 -> 건수)
      col_mismatch_skipped  int(헤더와 칸 수 달라 스킵한 행 총합)
    """
    limit = raise_field_size_limit()
    files = collect_csv_files(data_dir)
    if not files:
        raise RuntimeError("CSV 파일이 없습니다: {}".format(data_dir))

    parcel_by_pnu = {}
    unit_business_records = []
    floor_counter = Counter()
    invalid_pnu_reasons = Counter()
    per_file = []
    skipped_files = []
    col_mismatch_skipped = 0

    for path in files:
        name = os.path.relpath(path, data_dir)
        matched = 0
        last_exc = None
        processed = False
        for encoding in ENCODING_CANDIDATES:
            try:
                file_result = _process_one_file(path, encoding, sigungu_code, snapshot_ym)
                # 이 인코딩 시도가 끝까지 성공했을 때만 로컬 결과를 공유 컨테이너에
                # 병합한다 — 실패한 시도의 부분 결과는 위에서 이미 버려졌으므로
                # 여기서 합칠 게 없다(중복 축적 방지).
                matched = file_result["matched"]
                col_mismatch_skipped += file_result["col_mismatch_skipped"]
                for pnu, rec in file_result["parcel_by_pnu"].items():
                    parcel_by_pnu.setdefault(pnu, rec)
                unit_business_records.extend(file_result["unit_business_records"])
                floor_counter.update(file_result["floor_counter"])
                invalid_pnu_reasons.update(file_result["invalid_pnu_reasons"])
                processed = True
                break
            except UnicodeDecodeError as e:
                last_exc = e
                continue
            except EmptyFileError:
                skipped_files.append((name, "빈 파일"))
                processed = True
                break
            except MissingColumnsError as e:
                skipped_files.append((name, "필요한 컬럼 없음 {}".format(e.missing_cols)))
                processed = True
                break
        if not processed:
            raise RuntimeError("{}: 인코딩 판별 실패 ({})".format(name, last_exc))
        per_file.append((name, matched))

    return {
        "field_size_limit": limit,
        "files_total": len(files),
        "per_file": per_file,
        "skipped_files": skipped_files,
        "total_matched": sum(m for _n, m in per_file),
        "parcel_records": list(parcel_by_pnu.values()),
        "unit_business_records": unit_business_records,
        "floor_counter": floor_counter,
        "invalid_pnu_reasons": invalid_pnu_reasons,
        "col_mismatch_skipped": col_mismatch_skipped,
    }


# ── Supabase(PostgREST) 적재 ────────────────────────────────────────────────


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


def upsert_batch(base_url, headers, table, rows, batch_size=BATCH_SIZE):
    """rows를 batch_size 단위로 table에 upsert. 실제로 보낸 행 수를 돌려준다.

    충돌 해소 정책은 테이블마다 다르다 — TABLE_UPSERT_RESOLUTION 참조
    (parcel=merge-duplicates / unit_business=ignore-duplicates, append-only 불변식).
    """
    resolution = TABLE_UPSERT_RESOLUTION.get(table)
    if resolution is None:
        raise ValueError(
            "{}: TABLE_UPSERT_RESOLUTION에 정의되지 않은 테이블입니다 — "
            "충돌 해소 정책을 먼저 정의하세요.".format(table)
        )
    upsert_headers = dict(headers)
    upsert_headers["Content-Type"] = "application/json"
    upsert_headers["Prefer"] = "resolution={},return=minimal".format(resolution)

    sent = 0
    total_batches = (len(rows) + batch_size - 1) // batch_size
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        batch_no = i // batch_size + 1
        r = requests.post(
            "{}/rest/v1/{}".format(base_url, table),
            json=batch, headers=upsert_headers, timeout=TIMEOUT_SEC,
        )
        if r.status_code >= 300:
            raise RuntimeError(
                "{} 배치 {}/{} upsert 실패 (HTTP {}): {}".format(
                    table, batch_no, total_batches, r.status_code, r.text[:500]
                )
            )
        sent += len(batch)
        print("  [{}] {}/{} 배치 {}행 (누적 {:,}/{:,})".format(
            table, batch_no, total_batches, len(batch), sent, len(rows)), flush=True)
    return sent


def rest_count(base_url, headers, table, query):
    """PostgREST HEAD 요청으로 정확한 행 수를 돌려준다 (Content-Range 헤더)."""
    h = dict(headers)
    h["Prefer"] = "count=exact"
    r = requests.head(
        "{}/rest/v1/{}?{}".format(base_url, table, query), headers=h, timeout=60
    )
    if r.status_code not in (200, 206):
        raise RuntimeError("{} count 조회 실패 (HTTP {}): {}".format(table, r.status_code, r.text[:300]))
    content_range = r.headers.get("Content-Range", "")
    if "/" not in content_range:
        raise RuntimeError("{}: Content-Range 헤더 형식 이상: {!r}".format(table, content_range))
    return int(content_range.split("/")[-1])


# ── 보고 출력 ────────────────────────────────────────────────────────────────


def print_scan_report(result, sigungu_code, gu_name, snapshot_ym):
    print("=" * 78)
    print("소상공인 상권정보 스냅샷 스캔 결과 — {} ({}) / 기준월 {}".format(
        gu_name, sigungu_code, snapshot_ym))
    print("=" * 78)
    print("대상 파일: {}개 (CSV 필드 최대 길이 {:,})".format(
        result["files_total"], result["field_size_limit"]))
    for name, matched in result["per_file"]:
        if matched:
            print("  {} -> {:,}행 매치".format(name, matched))
    if result["skipped_files"]:
        print("  [경고] 스킵된 파일:")
        for name, reason in result["skipped_files"]:
            print("    - {}: {}".format(name, reason))
    if result["col_mismatch_skipped"]:
        print("  [경고] 헤더와 칸 수가 달라 스킵한 행: {:,}행".format(
            result["col_mismatch_skipped"]))

    total = result["total_matched"]
    unit_business_records = result["unit_business_records"]
    parcel_records = result["parcel_records"]
    invalid = sum(result["invalid_pnu_reasons"].values())
    valid = total - invalid
    rate = (valid * 100.0 / total) if total else 0.0

    print("")
    print("[ 매치 행 수 (would-insert unit_business) ] {:,}행".format(len(unit_business_records)))
    print("[ 고유 PNU 수 (would-upsert parcel) ]       {:,}행".format(len(parcel_records)))

    print("")
    print("[ §5.6 상권정보 → PNU 매칭률 ] 목표 {:.0f}%+".format(PNU_MATCH_RATE_TARGET))
    print("  유효 {:,} / 전체 {:,}  ->  {:.2f}%  [{}]".format(
        valid, total, rate,
        "달성" if rate >= PNU_MATCH_RATE_TARGET else "미달 — 원인 분석 필요"))
    if result["invalid_pnu_reasons"]:
        print("  무효 사유 상위:")
        for reason, cnt in result["invalid_pnu_reasons"].most_common():
            print("    - {}: {:,}건".format(reason, cnt))

    print("")
    print("[ 층정보 정규화 결과 분포 ] (원본 값 기준 상위 15종)")
    for value, cnt in result["floor_counter"].most_common(15):
        print("    {:<10} {:>10,}건".format(value, cnt))

    scale = estimate_bldrgst_scale(len(parcel_records))
    print("")
    print("[ 다음 단계 규모 추정 — 건축물대장(건축HUB) API, 이 스크립트는 실행하지 않음 ]")
    print("  대상 PNU(고유 건물) 수 : {:,}개".format(scale["unique_pnu"]))
    print("  건물당 예상 호출 수   : {} (표제부+층별개요+전유부, 페이지네이션 미고려 보수 추정)".format(
        scale["calls_per_pnu"]))
    print("  총 예상 호출 수       : {:,}건".format(scale["total_calls"]))
    print("  일 한도               : {:,}건".format(scale["daily_limit"]))
    if scale["fits_in_one_day"]:
        print("  판정: 일 한도 이내 — collect_progress 이어받기로 바로 진행 가능")
    else:
        print("  판정: 일 한도 초과 — 최소 {}일 분할 필요 (실행하지 않음, 분할 계획만 보고)".format(
            scale["days_needed"]))
        print("  분할 제안: PNU를 법정동코드 또는 앞자리 기준으로 나눠 하루 {:,}건씩 collect_progress 이어받기".format(
            scale["daily_limit"] // scale["calls_per_pnu"]))
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
        bool_flags=("--dry-run",),
        value_flags=("--dir", "--sigungu-code", "--gu-name", "--snapshot-ym"),
    )
    opts = {
        "dir": DEFAULT_DATA_DIR,
        "sigungu_code": DEFAULT_SIGUNGU_CODE,
        "gu_name": DEFAULT_GU_NAME,
        "snapshot_ym": None,
        "dry_run": "--dry-run" in argv,
    }
    for flag, key in (
        ("--dir", "dir"),
        ("--sigungu-code", "sigungu_code"),
        ("--gu-name", "gu_name"),
        ("--snapshot-ym", "snapshot_ym"),
    ):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise ValueError("{} 뒤에 값이 필요합니다.".format(flag))
            opts[key] = argv[i + 1]
    return opts


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

    if not os.path.isdir(opts["dir"]):
        print("[에러] 폴더를 찾을 수 없습니다: {}".format(opts["dir"]))
        return 1

    files_for_ym = collect_csv_files(opts["dir"])
    snapshot_ym = opts["snapshot_ym"]
    if not snapshot_ym:
        try:
            snapshot_ym = detect_snapshot_ym(files_for_ym)
        except ValueError as e:
            print("[에러] {}".format(e))
            return 2

    if not SNAPSHOT_YM_RE.match(snapshot_ym):
        print("[에러] --snapshot-ym 형식이 올바르지 않습니다 (YYYYMM 6자리 숫자): {!r}".format(
            snapshot_ym))
        return 2

    print("스캔 시작: {} (시군구코드={}, 기준월={})".format(
        opts["dir"], opts["sigungu_code"], snapshot_ym), flush=True)
    try:
        result = scan_and_build(opts["dir"], opts["sigungu_code"], snapshot_ym)
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1
    print_scan_report(result, opts["sigungu_code"], opts["gu_name"], snapshot_ym)

    if opts["dry_run"]:
        print("")
        print("--dry-run 지정 — DB 적재는 건너뜁니다.")
        return 0

    if not result["parcel_records"] and not result["unit_business_records"]:
        print("[에러] 적재할 행이 없습니다. --sigungu-code/--dir 를 확인하세요.")
        return 1

    print("")
    print("Supabase 연결 확인 중...", flush=True)
    try:
        base_url, key = get_supabase_config()
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1
    headers = {"apikey": key, "Authorization": "Bearer {}".format(key)}

    print("적재 시작...", flush=True)
    try:
        parcel_sent = upsert_batch(base_url, headers, "parcel", result["parcel_records"])
        ub_sent = upsert_batch(base_url, headers, "unit_business", result["unit_business_records"])
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1

    print("")
    print("=" * 78)
    print("적재 완료: parcel {:,}행 / unit_business {:,}행".format(parcel_sent, ub_sent))
    print("=" * 78)

    print("")
    print("REST 교차 확인 중...", flush=True)
    try:
        parcel_count = rest_count(
            base_url, headers, "parcel",
            "select=pnu&sigungu_code=eq.{}".format(opts["sigungu_code"]),
        )
        ub_count = rest_count(
            base_url, headers, "unit_business",
            "select=biz_no&snapshot_ym=eq.{}&pnu=like.{}*".format(
                snapshot_ym, opts["sigungu_code"]),
        )
    except RuntimeError as e:
        print("[에러] REST 교차 확인 실패: {}".format(e))
        return 1

    # unit_business REST count는 pnu=like 로 이 시군구만 좁혀 세므로(향후 다른
    # 시군구도 같은 테이블에 적재될 때 서로 섞여 오탐하는 것을 방지), 비교 대상도
    # 유효 PNU가 있는 행만으로 맞춘다. PNU 무효 행(시군구 귀속 불가)까지 포함한
    # 전체 would-insert 건수는 위 스캔 보고서에 이미 나와 있다.
    ub_records_with_pnu = [r for r in result["unit_business_records"] if r["pnu"]]

    parcel_ok = parcel_count == len(result["parcel_records"])
    ub_ok = ub_count == len(ub_records_with_pnu)

    print("  parcel        would-upsert {:,} vs REST count {:,}  [{}]".format(
        len(result["parcel_records"]), parcel_count,
        "일치" if parcel_ok else "불일치 — 확인 필요"))
    print("  unit_business would-insert(유효 PNU만) {:,} vs REST count {:,}  [{}]".format(
        len(ub_records_with_pnu), ub_count,
        "일치" if ub_ok else "불일치 — 확인 필요"))

    if not (parcel_ok and ub_ok):
        print("[에러] REST 교차검증 불일치 — 위 결과를 확인하세요.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
