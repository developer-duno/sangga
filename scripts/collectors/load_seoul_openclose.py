# -*- coding: utf-8 -*-
"""서울시 상권분석서비스(점포-상권 · OA-15577) raw → `district_openclose` 적재 (결정 0033 · 한 트랜잭션).

무엇을 넣나
-----------
수집기 둘이 받은 raw — 열린 API jsonl(`data/raw/seoul_openclose/api/<분기>_<받은날짜>.jsonl`)과
연도 zip(`data/raw/seoul_openclose/zip/<연도>_<받은날짜>.zip`) — 을 (분기, 상권, 업종) 한 줄씩
**공표값 그대로** 넣는다. 우리가 계산하는 값은 없다(합산은 함수 몫 · 결정 0033 결정 1).

어느 파일을 쓰나 (분기마다 하나)
--------------------------------
  · 그 분기의 API jsonl 이 있으면 **API 가 이긴다**(분기마다 갱신 · zip 은 연 1회 대비책).
  · 같은 종류가 여럿이면 **가장 최근에 받은 날짜** 하나(지난 판이 다시 발행되기도 한다 — 2021~2024
    zip 이 2025-06-04 에 다시 써졌다 · 결정 0033 실측표). 날짜는 파일 이름에서 읽는다.
  · 분기 단위 **교체** — 그 분기 행을 지우고 새로 넣는다(개정판 대비 · 행이 남아 섞이지 않게).

⚠️ 머리말이 세 벌이다 (2026-10-05 실측 — 결정 0033)
-----------------------------------------------------
  · 2025년 zip: 영문 소문자(`stdr_yyqu_cd` …) · 2021~2024년 zip: 한글(`기준_년분기_코드` …
    ⚠️ `개업_율`·`폐업_률` — 율/률이 섞여 있다) · 열린 API: 영문 대문자(`STDR_YYQU_CD` …, 숫자가 실수
    `156.0`). zip 은 전부 cp949 · BOM 없음.
  · 셋을 아래 `HEADER_MAP` 한 표로 같은 이름에 잇는다. **표에 없는 칸이 오면 시끄럽게 멈춘다** —
    서울시가 칸을 바꾼 날 조용히 버리거나 엉뚱한 칸에 넣지 않게.
  · 개수 칸의 `3.0` 은 정수로 옮기되, 소수부가 0 이 아니면(`3.5`) 멈춘다.

관문 여섯 (결정 0033 설계 칸 2 — 하나라도 걸리면 DB 는 손도 안 댄다)
-------------------------------------------------------------------
  ⒜ 상권 코드가 `district` 에 있다 — 적재 SQL 안에서 DB 가 마지막으로 확인한다(raise → 통째 롤백).
     `--dry-run` 은 DB 를 안 열므로 커밋된 `public/districts.geojson`(district 를 구운 파일)로 미리 본다.
     특정 분기만 걸리면 `--skip-quarter <분기>` 로 그 분기만 빼고 넣는다(빠진 분기는 PROGRESS 에 적는다).
  ⒝ 분기 코드 꼴 `YYYYQ`(다섯 자리 · 분기 1~4).
  ⒞ 산식 재현(개업·폐업 둘 다): 행마다 |공표 비율 − round(수 ÷ 유사 업종 점포 수 × 100)| ≤ 1
     (유사 업종 점포 수 0 이면 공표 비율 0 이 기대값). 어긋난 행이 분기의 **0.1% 를 넘으면** 멈춘다
     (실측 0행 — 분모를 점포 수(stor)로 잘못 잡으면 2.3~2.5% 가 걸린다).
  ⒟ (분기, 상권, 업종) 중복 0.
  ⒠ 분기당 행수 70,000~82,000(2021Q1~2026Q2 실측 75,891~77,056).
  ⒡ 유사 업종 점포 수 = 점포 수 + 프랜차이즈 점포 수 — 전 행.
  ⒢ 들어온 분기들의 처음~끝 사이에 **빠진 분기**가 없다(`--skip-quarter` 로 일부러 뺀 분기는 예외) —
     raw 하나를 빠뜨린 채 넣으면 그 분기만 구멍 난 채 화면 8분기 막대가 조용히 이가 빠진다.

⛔ 분할 적재 금지 — 있는 raw 를 **한 번에** 넣는다
--------------------------------------------------
신선도 표(get_data_freshness)는 `max(quarter)` 를 본다. 옛 분기만 먼저 넣으면 그날 바로 '지났습니다'가
뜨고 그물 6호가 이슈를 연다. 그래서 이 적재기는 분기를 골라 넣는 인자를 두지 않는다(빼는 것만 있다).

쓰는 법 (프로젝트 루트에서)
---------------------------
    python scripts/collectors/load_seoul_openclose.py --dry-run          # 관문 리포트 · DB 쓰기 0 · 파일 쓰기 0
    python scripts/collectors/load_seoul_openclose.py                    # 적재(한 트랜잭션) → post_load.py → --check
    python scripts/collectors/load_seoul_openclose.py --skip-quarter 20262
"""

import argparse
import csv
import datetime
import decimal
import io
import json
import os
import re
import sys
import zipfile

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
DEFAULT_RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "seoul_openclose")
DEFAULT_STAGING_DIR = os.path.join(PROJECT_ROOT, "data", "staging", "seoul_openclose")
DISTRICTS_GEOJSON = os.path.join(PROJECT_ROOT, "public", "districts.geojson")

TABLE = "district_openclose"

# 원본 칸 → 우리 이름. 세 벌(영문 소문자 · 한글 · 영문 대문자)이 모두 이 표 하나로 간다.
CANON = (
    "stdr_yyqu_cd", "trdar_se_cd", "trdar_se_cd_nm", "trdar_cd", "trdar_cd_nm",
    "svc_induty_cd", "svc_induty_cd_nm", "stor_co", "similr_induty_stor_co",
    "opbiz_rt", "opbiz_stor_co", "clsbiz_rt", "clsbiz_stor_co", "frc_stor_co",
)
KOREAN = {
    "기준_년분기_코드": "stdr_yyqu_cd", "상권_구분_코드": "trdar_se_cd",
    "상권_구분_코드_명": "trdar_se_cd_nm", "상권_코드": "trdar_cd", "상권_코드_명": "trdar_cd_nm",
    "서비스_업종_코드": "svc_induty_cd", "서비스_업종_코드_명": "svc_induty_cd_nm",
    "점포_수": "stor_co", "유사_업종_점포_수": "similr_induty_stor_co",
    "개업_율": "opbiz_rt", "개업_점포_수": "opbiz_stor_co",
    "폐업_률": "clsbiz_rt", "폐업_점포_수": "clsbiz_stor_co", "프랜차이즈_점포_수": "frc_stor_co",
}
HEADER_MAP = dict(KOREAN)
HEADER_MAP.update({c: c for c in CANON})
HEADER_MAP.update({c.upper(): c for c in CANON})

COUNT_COLS = ("stor_co", "similr_induty_stor_co", "opbiz_stor_co", "clsbiz_stor_co", "frc_stor_co")
RATE_COLS = ("opbiz_rt", "clsbiz_rt")

# 표에 넣는 칸(순서 = staging CSV 순서). loaded_at 은 기본값(now()).
CSV_COLUMNS = (
    "quarter", "district_id", "svc_induty_cd", "svc_induty_cd_nm", "stor_co",
    "similr_induty_stor_co", "opbiz_rt", "opbiz_stor_co", "clsbiz_rt", "clsbiz_stor_co",
    "frc_stor_co", "source_nm",
)

RE_QUARTER = re.compile(r"^\d{4}[1-4]$")
RE_API_FILE = re.compile(r"^(\d{4}[1-4])_(\d{8})\.jsonl$")
RE_ZIP_FILE = re.compile(r"^(\d{4})_(\d{8})\.zip$")

ROWS_PER_QUARTER = (70_000, 82_000)
FORMULA_TOLERANCE = 1          # 공표 비율과 재현값의 차이 허용(정수 반올림 1포인트)
FORMULA_MAX_BAD_SHARE = 0.001  # 분기의 0.1%


class GateError(ValueError):
    """관문에 걸림 — DB 에 아무것도 안 쓴다."""


# ── 순수 함수 ────────────────────────────────────────────────────────────────


def map_header(header, where):
    """원본 머리말 → 우리 이름 목록. 모르는 칸·빠진 칸·겹친 칸은 멈춘다."""
    names = [str(h).strip().lstrip("\ufeff") for h in header]
    unknown = [h for h in names if h not in HEADER_MAP]
    if unknown:
        raise GateError("{}: 매핑표에 없는 칸 {} — 서울시가 칸을 바꿨을 수 있습니다. "
                        "HEADER_MAP 을 사람이 고친 뒤 다시 돌리세요.".format(where, unknown))
    mapped = [HEADER_MAP[h] for h in names]
    missing = [c for c in CANON if c not in mapped]
    if missing or len(set(mapped)) != len(mapped):
        raise GateError("{}: 칸이 빠졌거나 겹칩니다(빠짐 {} · 머리말 {})".format(where, missing, names))
    return mapped


def to_int(value, col, where):
    """'12' · '12.0' · 12.0 → 12. 소수부가 있거나 음수·빈 값이면 멈춘다."""
    try:
        d = decimal.Decimal(str(value).strip())
    except (decimal.InvalidOperation, ValueError):
        raise GateError("{}: {} 가 수가 아닙니다: {!r}".format(where, col, value))
    if d != d.to_integral_value() or d < 0:
        raise GateError("{}: {} 가 0 이상 정수가 아닙니다: {!r}".format(where, col, value))
    return int(d)


def to_rate(value, col, where):
    """공표 비율(%) — 그대로 두 자리까지. numeric(6,2) 를 넘거나 음수면 멈춘다."""
    try:
        d = decimal.Decimal(str(value).strip())
    except (decimal.InvalidOperation, ValueError):
        raise GateError("{}: {} 가 수가 아닙니다: {!r}".format(where, col, value))
    if d < 0 or d >= 10000:
        raise GateError("{}: {} 가 범위(0~9999.99) 밖입니다: {!r}".format(where, col, value))
    return d.quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP)


def normalize(rec, source_nm, where):
    """원본 dict(우리 이름) → 표 한 줄 dict."""
    row = {
        "quarter": str(rec["stdr_yyqu_cd"]).strip(),
        "district_id": str(rec["trdar_cd"]).strip(),
        "svc_induty_cd": str(rec["svc_induty_cd"]).strip(),
        "svc_induty_cd_nm": (str(rec["svc_induty_cd_nm"]).strip() or None),
        "source_nm": source_nm,
    }
    for c in COUNT_COLS:
        row[c] = to_int(rec[c], c, where)
    for c in RATE_COLS:
        row[c] = to_rate(rec[c], c, where)
    return row


def expected_rate(count, similr):
    """서울시 산식 재현 — 수 ÷ 유사 업종 점포 수 × 100 을 정수로 반올림(분모 0 이면 0)."""
    if similr == 0:
        return decimal.Decimal(0)
    return (decimal.Decimal(count) * 100 / decimal.Decimal(similr)).quantize(
        decimal.Decimal(1), rounding=decimal.ROUND_HALF_UP)


def formula_mismatch(row, denominator="similr_induty_stor_co"):
    """⒞ 이 행의 개업·폐업 공표 비율이 산식과 1포인트 넘게 어긋나는가.

    `denominator` 는 시험이 '분모를 점포 수로 바꾼 변이'를 흉내 낼 때만 바꾼다.
    """
    den = row[denominator]
    for cnt, rt in (("opbiz_stor_co", "opbiz_rt"), ("clsbiz_stor_co", "clsbiz_rt")):
        if abs(row[rt] - expected_rate(row[cnt], den)) > FORMULA_TOLERANCE:
            return True
    return False


def gate_problems(rows_by_quarter, known_districts=None, denominator="similr_induty_stor_co"):
    """관문 ⒜~⒡ — {분기: [문제 문장…]}(빈 dict = 통과). ⒜ 는 known_districts 를 줄 때만 본다."""
    out = {}
    for q, rows in sorted(rows_by_quarter.items()):
        bad = []
        if not RE_QUARTER.match(q):
            bad.append("⒝ 분기 코드 꼴이 YYYYQ 가 아닙니다: {!r}".format(q))
        other = [r["quarter"] for r in rows if r["quarter"] != q]
        if other:
            bad.append("⒝ 다른 분기 행 {}개가 섞였습니다(예 {!r})".format(len(other), other[0]))
        if known_districts is not None:
            missing = sorted({r["district_id"] for r in rows} - known_districts)
            if missing:
                bad.append("⒜ district 에 없는 상권 코드 {}개(예 {})".format(len(missing), missing[:5]))
        n_bad = sum(1 for r in rows if formula_mismatch(r, denominator))
        if rows and n_bad / len(rows) > FORMULA_MAX_BAD_SHARE:
            bad.append("⒞ 산식과 1포인트 넘게 어긋난 행 {:,}개({:.2%}) — 0.1% 초과".format(
                n_bad, n_bad / len(rows)))
        keys = [(r["district_id"], r["svc_induty_cd"]) for r in rows]
        if len(set(keys)) != len(keys):
            bad.append("⒟ (분기·상권·업종) 중복 {:,}개".format(len(keys) - len(set(keys))))
        lo, hi = ROWS_PER_QUARTER
        if not lo <= len(rows) <= hi:
            bad.append("⒠ 행수 {:,} — {:,}~{:,} 밖".format(len(rows), lo, hi))
        n_sum = sum(1 for r in rows
                    if r["similr_induty_stor_co"] != r["stor_co"] + r["frc_stor_co"])
        if n_sum:
            bad.append("⒡ 유사 업종 점포 수 ≠ 점포 수 + 프랜차이즈 인 행 {:,}개".format(n_sum))
        if bad:
            out[q] = bad
    return out


def missing_quarters(quarters, skip=()):
    """⒢ 처음~끝 분기 사이에서 빠진 분기(뺀 분기 skip 은 빼고) — 옛것부터."""
    qs = sorted(q for q in quarters if RE_QUARTER.match(q))
    if not qs:
        return []
    y, q = int(qs[0][:4]), int(qs[0][4])
    have, out = set(qs), []
    while True:
        cur = "{}{}".format(y, q)
        if cur > qs[-1]:
            return out
        if cur not in have and cur not in skip:
            out.append(cur)
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)


def pick_sources(api_files, zip_files):
    """{분기: (종류, 경로)} 와 zip 이 맡는 연도 — API 가 이기고, 같은 종류는 가장 최근 날짜.

    api_files: [(분기, 받은날짜, 경로)] · zip_files: [(연도, 받은날짜, 경로)].
    zip 은 연도 단위라 그 해 네 분기 중 API 가 없는 분기만 맡는다.
    """
    api = {}
    for q, ymd, path in api_files:
        if q not in api or ymd > api[q][0]:
            api[q] = (ymd, path)
    zips = {}
    for y, ymd, path in zip_files:
        if y not in zips or ymd > zips[y][0]:
            zips[y] = (ymd, path)
    chosen = {q: ("api", p) for q, (_, p) in api.items()}
    zip_years = {}
    for y, (_, path) in zips.items():
        quarters = [q for q in ("{}{}".format(y, i) for i in range(1, 5)) if q not in chosen]
        if quarters:
            zip_years[path] = quarters
    return chosen, zip_years


def list_raw(raw_dir):
    api_dir, zip_dir = os.path.join(raw_dir, "api"), os.path.join(raw_dir, "zip")
    api_files, zip_files = [], []
    if os.path.isdir(api_dir):
        for n in sorted(os.listdir(api_dir)):
            m = RE_API_FILE.match(n)
            if m:
                api_files.append((m.group(1), m.group(2), os.path.join(api_dir, n)))
    if os.path.isdir(zip_dir):
        for n in sorted(os.listdir(zip_dir)):
            m = RE_ZIP_FILE.match(n)
            if m:
                zip_files.append((m.group(1), m.group(2), os.path.join(zip_dir, n)))
    return api_files, zip_files


# ── 파일 읽기 ────────────────────────────────────────────────────────────────


def read_api_file(path, quarter):
    """API jsonl → 표 줄 목록. 줄의 quarter·행의 분기가 파일 이름 분기와 다르면 멈춘다."""
    name = os.path.basename(path)
    out = []
    mapped_once = None
    with io.open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            where = "{}:{}".format(name, i)
            if str(obj.get("quarter")) != quarter:
                raise GateError("{}: 줄의 quarter {!r} ≠ 파일 분기 {}".format(where, obj.get("quarter"), quarter))
            raw = obj["row"]
            keys = list(raw.keys())
            if mapped_once is None or keys != mapped_once[0]:
                mapped_once = (keys, map_header(keys, where))
            rec = {mapped_once[1][k]: raw[key] for k, key in enumerate(keys)}
            out.append(normalize(rec, name, where))
    return out


def read_zip_file(path, quarters):
    """연도 zip → {분기: 줄 목록} — quarters 에 든 분기만(API 가 맡은 분기는 버린다)."""
    name = os.path.basename(path)
    with zipfile.ZipFile(path) as z:
        csvs = [i.filename for i in z.infolist() if i.filename.lower().endswith(".csv")]
        if len(csvs) != 1:
            raise GateError("{}: 안에 csv 가 {}개입니다(1개여야 한다)".format(name, len(csvs)))
        text = z.read(csvs[0]).decode("cp949")
    reader = csv.reader(io.StringIO(text))
    cols = map_header(next(reader), name)
    want = set(quarters)
    out = {q: [] for q in quarters}
    for i, cells in enumerate(reader, 2):
        if not cells:
            continue
        rec = dict(zip(cols, cells))
        q = str(rec["stdr_yyqu_cd"]).strip()
        if q not in want:
            continue
        out[q].append(normalize(rec, name, "{}:{}".format(name, i)))
    return out


def seoul_district_ids(path=DISTRICTS_GEOJSON):
    """커밋된 지도 파일의 상권 코드(⒜ 미리보기용). 없으면 None — DB 관문이 대신 본다."""
    if not os.path.exists(path):
        return None
    with io.open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {str(ft["properties"]["district_id"]) for ft in data.get("features", [])}


def collect(raw_dir, skip=()):
    """raw 를 골라 읽어 {분기: 줄 목록} 과 {분기: 출처 파일 이름} 을 돌려준다."""
    api_files, zip_files = list_raw(raw_dir)
    chosen, zip_years = pick_sources(api_files, zip_files)
    rows, src = {}, {}
    for q, (_, path) in sorted(chosen.items()):
        if q in skip:
            continue
        rows[q] = read_api_file(path, q)
        src[q] = os.path.basename(path)
    for path, quarters in sorted(zip_years.items()):
        quarters = [q for q in quarters if q not in skip]
        if not quarters:
            continue
        got = read_zip_file(path, quarters)
        for q, part in got.items():
            if part:
                rows[q] = part
                src[q] = os.path.basename(path)
    return rows, src


# ── SQL ──────────────────────────────────────────────────────────────────────


def copy_path_literal(path):
    return path.replace("\\", "/").replace("'", "''")


def write_csv(rows_by_quarter, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = 0
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        for q in sorted(rows_by_quarter):
            for r in rows_by_quarter[q]:
                w.writerow([r[c] for c in CSV_COLUMNS])
                n += 1
    return n


def build_sql(csv_path, quarters, expected_rows):
    """적재 SQL — 한 트랜잭션. 관문은 전부 raise exception(psql 은 select 결과와 무관하게 0 으로 끝난다)."""
    qs = ", ".join("'{}'".format(q) for q in sorted(quarters))
    return """begin;
set local statement_timeout = '1800s';

create temp table stage_openclose (like {table} including defaults) on commit drop;

\\copy stage_openclose ({cols}) from '{csv}' with (format csv, encoding 'UTF8')

-- ── 행수 대조 — CSV 가 잘려도 \\copy 는 에러 없이 거기까지만 넣는다 ─────────────
do $$
declare cnt bigint;
begin
  select count(*) into cnt from stage_openclose;
  if cnt <> {expected} then
    raise exception '올린 행이 %개인데 원본에서 읽은 것은 {expected}개입니다 — 통째로 되돌립니다', cnt;
  end if;
end $$;

-- ── 관문 ⒜ 상권 코드가 district 에 있나 (DB 가 마지막으로 확인) ─────────────────
do $$
declare bad text;
begin
  select string_agg(s.quarter || ':' || s.n, ', ' order by s.quarter) into bad
    from (select st.quarter, count(distinct st.district_id) as n
            from stage_openclose st
           where not exists (select 1 from district d where d.district_id = st.district_id)
           group by st.quarter) s;
  if bad is not null then
    raise exception '관문 ⒜ district 에 없는 상권 코드가 있는 분기(분기:코드 수) = % — 통째로 되돌립니다. 그 분기만 --skip-quarter 로 빼고 다시 돌리세요', bad;
  end if;
end $$;

-- 분기 단위 교체 — 그 분기 행을 지우고 새로(개정판 대비). 위 관문에 걸리면 이 삭제까지 되돌아간다.
delete from {table} where quarter in ({qs});

insert into {table} ({cols}) select {cols} from stage_openclose;

do $$
declare cnt bigint;
begin
  select count(*) into cnt from {table} where quarter in ({qs});
  if cnt <> {expected} then
    raise exception '표에 든 행이 %개인데 {expected}개여야 합니다 — 통째로 되돌립니다', cnt;
  end if;
end $$;

select quarter as "분기", count(*) as "행" from {table} where quarter in ({qs}) group by quarter order by quarter;

commit;
""".format(table=TABLE, cols=", ".join(CSV_COLUMNS), csv=copy_path_literal(csv_path),
           expected=expected_rows, qs=qs)


# ── 메인 ─────────────────────────────────────────────────────────────────────


def parse_skip(values):
    out = set()
    for v in values or ():
        for q in str(v).split(","):
            q = q.strip()
            if not q:
                continue
            if not RE_QUARTER.match(q):
                raise ValueError("--skip-quarter 는 YYYYQ 다섯 자리여야 합니다: {!r}".format(q))
            out.add(q)
    return out


def main(argv=None):
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="서울 개업·폐업 raw → district_openclose 적재",
                                allow_abbrev=False)
    p.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    p.add_argument("--staging-dir", default=DEFAULT_STAGING_DIR)
    p.add_argument("--skip-quarter", action="append",
                   help="이 분기는 빼고 넣는다(관문 ⒜ 에 그 분기만 걸릴 때 · 쉼표로 여럿)")
    p.add_argument("--dry-run", action="store_true", help="관문 리포트만 — DB·파일 쓰기 0")
    a = p.parse_args(argv)

    try:
        skip = parse_skip(a.skip_quarter)
        rows, src = collect(a.raw_dir, skip)
    except (ValueError, OSError) as e:
        print("실패: {}".format(e), file=sys.stderr)
        return 1
    if not rows:
        print("raw 가 없습니다: {} (api/·zip/)".format(a.raw_dir), file=sys.stderr)
        return 1

    print("=" * 74)
    print("서울 개업·폐업 → {} {}".format(TABLE, "(dry-run)" if a.dry_run else ""))
    print("=" * 74)
    for q in sorted(rows):
        print("  {}  {:>7,}행  ← {}".format(q, len(rows[q]), src[q]))
    if skip:
        print("  빼는 분기: {}".format(", ".join(sorted(skip))))
    total = sum(len(v) for v in rows.values())
    print("  합계 {}분기 · {:,}행".format(len(rows), total))

    gaps = missing_quarters(rows.keys(), skip)
    print("  빠진 분기(⒢): {}".format(", ".join(gaps) if gaps else "없음"))

    known = seoul_district_ids()
    problems = gate_problems(rows, known)
    if gaps:
        problems["⒢"] = ["⒢ 처음~끝 사이에 빠진 분기 {} — 그 분기 raw 를 받거나, 일부러 빼는 것이면 "
                         "--skip-quarter 로 적는다".format(", ".join(gaps))]
    if known is None:
        print("  ⓘ public/districts.geojson 이 없어 관문 ⒜ 미리보기를 건너뜁니다 — 적재 SQL 이 DB 에서 본다.")
    if problems:
        print()
        print("관문에 걸렸습니다 — DB 에는 아무것도 쓰지 않았습니다:", file=sys.stderr)
        for q, msgs in problems.items():
            for m in msgs:
                print("  {}  {}".format(q, m), file=sys.stderr)
        print("  (⒜ 만 특정 분기에 걸렸으면 --skip-quarter <분기> 로 그 분기만 빼고 넣을 수 있다)",
              file=sys.stderr)
        return 1
    print("  관문 통과 (⒜{} · ⒝ · ⒞ · ⒟ · ⒠ · ⒡ · ⒢)".format("" if known is not None else " DB 에서"))

    if a.dry_run:
        print()
        print("--dry-run — DB·파일에 아무것도 쓰지 않았습니다.")
        return 0

    csv_path = os.path.join(a.staging_dir, "district_openclose.csv")
    written = write_csv(rows, csv_path)
    sql = build_sql(csv_path, rows.keys(), written)

    import dbx  # noqa: PLC0415  (dry-run 은 DB 설정 없이도 돌아야 한다)
    rc = dbx.run_sql(sql)
    if rc != 0:
        print("적재 실패 (psql 종료코드 {}). 트랜잭션이라 아무것도 안 들어갔습니다.".format(rc),
              file=sys.stderr)
        return rc
    print()
    print("  적재 완료 ({}).".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    print("  다음: python scripts/post_load.py   그리고   python scripts/post_load.py --check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
