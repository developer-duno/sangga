# -*- coding: utf-8 -*-
"""대전 상권 안 인구 결과표(로컬 빌드 csv) → DB district_census_pop 통째 교체 (결정 0045 PR⑤ · 한 트랜잭션).

무엇을 넣나
-----------
`scripts/build_sgis_district_pop.py` 가 구운 `data/derived/sgis_district_pop/<받은 날 YYYYMMDD>.csv`
(+ 같은 이름 `.meta.json`)를 **그대로** 넣는다 — 대전 상권마다 한 줄:
  district_id,district_nm,district_type,sigungu_code,area_m2,n_overlap,n_full,cover_pct,
  pop,pop_lo,pop_hi,hh,hh_lo,hh_hi,emp,emp_lo,emp_hi,est,est_lo,est_hi
그리고 표지 sgis_census_release 한 줄(id = 1 · 받은 날 · 통계 기준 연도 · 경계 기준일 · 집계구 수 · 줄 수 · 빌드 시각 ·
겹침 하한 · 통째 비율). 신선도 17번 줄(받은 날 + 12개월)이 이 표지를 읽는다.
⛔ 값은 어림(C) — 집계구 통계를 겹친 면적 비율로 나눈 **상권 안 합계**이지 건물 값이 아니다(👤 0045 ③-3).

관문 (하나라도 걸리면 DB 는 손도 안 댄다 · exit 1)
--------------------------------------------------
  ⒜ csv · meta 둘 다 있다 · meta partial = false · sido = ["30"] · base_year 정수 · bnd_base_date·received_on 날짜 ·
     rows·sha256·built_at·n_oa_total·overlap_min_m2·full_ratio 칸이 있다
  ⒝ 머리줄 = 위 스무 칸 글자 그대로
  ⒞ district_id·district_nm 비어 있지 않음 · 중복 0 · 줄이 하나 이상 · sigungu_code 5자리 숫자 + 앞 두 자리 ∈ sido
  ⒟ 숫자 칸 전부 0 이상 정수(area_m2·cover_pct 는 소수) · 항목마다 lo ≤ 값 ≤ hi
  ⒠ n_overlap ≥ 1 · 0 ≤ n_full ≤ n_overlap
  ⒡ cover_pct 95.0~100.5(대전 2024 실측 99.975~100 · 집계구가 상권을 거의 다 덮어야 한다)
  ⒢ meta rows = csv 줄 수 · meta sha256 = csv 지문
  ⒣ 받은 날 ≤ 오늘(KST) — 폴더 이름 오타 막기
  ⒤ (DB 안 · 실적재 SQL 안) csv 의 district_id 집합 = district 의 sigungu_code 앞 두 자리 ∈ sido 집합 — 다르면 raise → 롤백
  ⒥ (DB 안) 받은 날이 표지의 받은 날보다 이르면 raise(같은 날 허용 — 다시 넣기 · 0044 꼴)

잠금
----
  TRUNCATE 는 ACCESS EXCLUSIVE 를 잡는다(PostgreSQL 문서 13.3 Explicit Locking: "Acquired by the DROP TABLE,
  TRUNCATE, REINDEX, …"). 이 표를 읽는 건 함수 get_district_census_pop 하나뿐 · lock_timeout 5s 를 **begin 앞**(세션 설정)에
  둬서 못 잡으면 기다리지 않고 멈춘다(트랜잭션 안이라 되돌아간다).

쓰는 법 (프로젝트 루트에서)
---------------------------
    python scripts/collectors/load_sgis_district_pop.py --dry-run     # 관문 ⒜~⒣ + 요약 (DB·파일 쓰기 0)
    python scripts/collectors/load_sgis_district_pop.py               # 실적재 (관문 ⒤⒥ 는 DB 안에서)
    → python scripts/post_load.py   그리고   python scripts/post_load.py --check
  `--csv` 를 안 주면 data/derived/sgis_district_pop/ 에서 이름(YYYYMMDD)이 가장 늦은 csv 를 쓴다.
  ⛔ 운영 순서(0044 꼴): 마이그 2026-11-01b → build_sgis_district_pop.py → 이 적재 → post_load.py · --check.
"""

import argparse
import collections
import csv
import datetime
import hashlib
import io
import json
import os
import re
import sys
from zoneinfo import ZoneInfo

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
DEFAULT_CSV_DIR = os.path.join(PROJECT_ROOT, "data", "derived", "sgis_district_pop")
DEFAULT_STAGING_DIR = os.path.join(PROJECT_ROOT, "data", "staging", "sgis_district_pop")
KST = ZoneInfo("Asia/Seoul")

COLUMNS = ("district_id", "district_nm", "district_type", "sigungu_code", "area_m2", "n_overlap", "n_full",
           "cover_pct", "pop", "pop_lo", "pop_hi", "hh", "hh_lo", "hh_hi", "emp", "emp_lo", "emp_hi",
           "est", "est_lo", "est_hi")
ITEM_KEYS = ("pop", "hh", "emp", "est")
INT_COLUMNS = ("n_overlap", "n_full") + tuple(k + s for k in ITEM_KEYS for s in ("", "_lo", "_hi"))
EXPECT_SIDO = ["30"]
COVER_RANGE = (95.0, 100.5)
META_KEYS = ("received_on", "base_year", "bnd_base_date", "n_oa_total", "rows", "sha256", "built_at",
             "overlap_min_m2", "full_ratio")
RE_CSV_NAME = re.compile(r"^\d{8}\.csv$")
RE_INT = re.compile(r"^\d+$")
RE_DEC = re.compile(r"^\d+(\.\d+)?$")
RE_SGG = re.compile(r"^\d{5}$")
RE_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EXAMPLES = 3


class GateError(ValueError):
    """관문에 걸림 — DB 에 아무것도 안 쓴다."""


def today_kst():
    return datetime.datetime.now(KST).date()


# ── 파일 고르기 · meta ───────────────────────────────────────────────────────


def default_csv(csv_dir=DEFAULT_CSV_DIR):
    """이름(YYYYMMDD.csv)이 가장 늦은 결과표. 없으면 None."""
    if not os.path.isdir(csv_dir):
        return None
    names = sorted(n for n in os.listdir(csv_dir) if RE_CSV_NAME.match(n))
    return os.path.join(csv_dir, names[-1]) if names else None


def meta_path_for(csv_path):
    base, _ext = os.path.splitext(csv_path)
    return base + ".meta.json"


def _date(v):
    """'YYYY-MM-DD' 만 — ⚠️ 파이썬 3.11 의 fromisoformat 은 '20250630' 도 받아 꼴 검사가 안 된다."""
    if not isinstance(v, str) or not RE_ISO_DATE.match(v):
        raise ValueError(v)
    return datetime.date.fromisoformat(v)


def read_meta(csv_path):
    """⒜ — csv·meta 가 있고 칸이 기대대로. → meta dict."""
    if not csv_path or not os.path.isfile(csv_path):
        raise GateError("⒜ 결과표 csv 가 없습니다: {}".format(csv_path))
    mpath = meta_path_for(csv_path)
    if not os.path.isfile(mpath):
        raise GateError("⒜ 짝 meta 가 없습니다: {}".format(mpath))
    with io.open(mpath, encoding="utf-8") as f:
        meta = json.load(f)
    bad = ["{} 칸이 없습니다".format(k) for k in META_KEYS if k not in meta]
    if meta.get("partial") is not False:
        bad.append("partial = {!r}".format(meta.get("partial")))
    if meta.get("sido") != EXPECT_SIDO:
        bad.append("sido = {!r} (기대 {})".format(meta.get("sido"), EXPECT_SIDO))
    if not bad:
        if not isinstance(meta["base_year"], int) or isinstance(meta["base_year"], bool) \
                or not 2000 <= meta["base_year"] <= 2100:
            bad.append("base_year = {!r} (정수 연도)".format(meta["base_year"]))
        for key in ("received_on", "bnd_base_date"):
            try:
                _date(meta[key])
            except (TypeError, ValueError):
                bad.append("{} = {!r} (YYYY-MM-DD)".format(key, meta[key]))
        try:
            datetime.datetime.fromisoformat(meta["built_at"])
        except (TypeError, ValueError):
            bad.append("built_at = {!r} (ISO 시각)".format(meta["built_at"]))
        for key in ("n_oa_total", "rows"):
            if not isinstance(meta[key], int) or isinstance(meta[key], bool) or meta[key] < 0:
                bad.append("{} = {!r} (0 이상 정수)".format(key, meta[key]))
        for key in ("overlap_min_m2", "full_ratio"):
            if not isinstance(meta[key], (int, float)) or isinstance(meta[key], bool):
                bad.append("{} = {!r} (수)".format(key, meta[key]))
    if bad:
        raise GateError("⒜ meta 가 기대와 다릅니다 — " + " · ".join(bad))
    return meta


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ── 관문 ─────────────────────────────────────────────────────────────────────


def row_problems(rec, sido):
    """한 줄(칸 이름 → 글자) → [(관문 글자, 문장)] (비면 통과)."""
    out = []
    if not rec["district_id"].strip():
        out.append(("⒞", "district_id 가 비었습니다"))
    # 표 칸이 not null 이라 COPY 가 롤백으로 멈추긴 하지만, 관문에서 먼저 문장으로 멈춘다(검사관 🟡 · 11-01).
    if not rec["district_nm"].strip():
        out.append(("⒞", "district_nm 이 비었습니다"))
    sgg = rec["sigungu_code"]
    if not RE_SGG.match(sgg) or sgg[:2] not in sido:
        out.append(("⒞", "sigungu_code {!r} (5자리 숫자 · 앞 두 자리 ∈ {})".format(sgg, sido)))
    bad_int = [c for c in INT_COLUMNS if not RE_INT.match(rec[c])]
    bad_dec = [c for c in ("area_m2", "cover_pct") if not RE_DEC.match(rec[c])]
    if bad_int or bad_dec:
        out.append(("⒟", "0 이상 정수/소수가 아닌 칸 {}".format(
            ", ".join("{}={!r}".format(c, rec[c]) for c in bad_int + bad_dec))))
        return out
    for k in ITEM_KEYS:
        lo, v, hi = int(rec[k + "_lo"]), int(rec[k]), int(rec[k + "_hi"])
        if not lo <= v <= hi:
            out.append(("⒟", "{} 하한 {} ≤ 값 {} ≤ 상한 {} 가 아닙니다".format(k, lo, v, hi)))
    n_ov, n_full = int(rec["n_overlap"]), int(rec["n_full"])
    if n_ov < 1 or not 0 <= n_full <= n_ov:
        out.append(("⒠", "n_overlap={} n_full={} (n_overlap ≥ 1 · 0 ≤ n_full ≤ n_overlap)".format(n_ov, n_full)))
    cov = float(rec["cover_pct"])
    if not COVER_RANGE[0] <= cov <= COVER_RANGE[1]:
        out.append(("⒡", "cover_pct {} 가 {}~{} 밖".format(cov, *COVER_RANGE)))
    return out


def check_csv(csv_path, meta, today=None):
    """⒝~⒣ 를 한 번 훑어 본다. → (문제 문장 목록, 셈 dict)."""
    problems = collections.OrderedDict()
    ids = set()
    stats = collections.Counter()
    with io.open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        head = tuple(next(reader, ()))
        if head != COLUMNS:
            raise GateError("⒝ 머리줄이 다릅니다 — {} (기대 {})".format(list(head), list(COLUMNS)))
        for i, r in enumerate(reader, 2):
            stats["rows"] += 1
            if len(r) != len(COLUMNS):
                problems.setdefault("⒝", []).append("{}줄: 칸 수 {}".format(i, len(r)))
                continue
            rec = dict(zip(COLUMNS, r))
            for code, msg in row_problems(rec, meta["sido"]):
                problems.setdefault(code, []).append("{}줄: {}".format(i, msg))
            if rec["district_id"] in ids:
                problems.setdefault("⒞", []).append("{}줄: district_id 중복 {!r}".format(i, rec["district_id"]))
            ids.add(rec["district_id"])
            if RE_INT.match(rec["n_full"]) and int(rec["n_full"]) == 0:
                stats["zero_full"] += 1
            if RE_INT.match(rec["pop"]):
                stats["pop_sum"] += int(rec["pop"])
    if stats["rows"] == 0:
        problems.setdefault("⒞", []).append("줄이 하나도 없습니다")
    if meta["rows"] != stats["rows"]:
        problems.setdefault("⒢", []).append("meta rows {} ≠ csv 줄 수 {}".format(meta["rows"], stats["rows"]))
    digest = file_sha256(csv_path)
    if meta["sha256"] != digest:
        problems.setdefault("⒢", []).append("meta sha256 ≠ csv 지문 {}".format(digest))
    today = today or today_kst()
    received = _date(meta["received_on"])
    if received > today:
        problems.setdefault("⒣", []).append("받은 날 {} 이 오늘 {} 보다 뒤입니다 — 폴더 이름을 확인하세요".format(
            received, today))
    out = []
    for code in sorted(problems):
        msgs = problems[code]
        out.append("{} {}건 — {}".format(code, len(msgs), " / ".join(msgs[:EXAMPLES])))
    return out, stats


# ── SQL ──────────────────────────────────────────────────────────────────────


def copy_path_literal(path):
    return path.replace("\\", "/").replace("'", "''")


def write_staging(csv_path, path):
    """관문을 지난 입력을 \\copy 용 사본으로 다시 쓴다(머리줄 포함). → 데이터 줄 수."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = 0
    with io.open(csv_path, encoding="utf-8", newline="") as src, \
            io.open(path, "w", encoding="utf-8", newline="") as dst:
        reader = csv.reader(src)
        w = csv.writer(dst, lineterminator="\n")
        w.writerow(next(reader))
        for r in reader:
            w.writerow(r)
            n += 1
    return n


def build_sql(path, rows, meta):
    """적재 SQL — 한 트랜잭션. ⒤ 상권 집합 대조 · ⒥ 받은 날 앞으로만 · 통째 교체 · 표지 upsert.
    어긋나면 raise(psql 은 select 결과와 무관하게 0). ⛔ RAISE 글의 % 는 자리표시자다(글자 % 는 %%)."""
    cols = ", ".join(COLUMNS)
    return """set lock_timeout = '5s';
begin;
set local statement_timeout = '120s';

create temp table stage_census_pop (like district_census_pop including defaults) on commit drop;

\\copy stage_census_pop ({cols}) from '{path}' with (format csv, header true, encoding 'UTF8')

-- ── 행수 대조 — CSV 가 잘려도 \\copy 는 에러 없이 거기까지만 넣는다 ─────────────
do $$
begin
  if (select count(*) from stage_census_pop) <> {rows} then
    raise exception '올린 행 수가 결과표 줄 수({rows})와 다릅니다 — 통째로 되돌립니다';
  end if;
end $$;

-- ── 관문 ⒤ — 결과표의 상권 = district 의 그 시·도 상권(빠짐도 남음도 0) ─────────────
do $$
declare
  v_missing int;
  v_extra   int;
begin
  select count(*) into v_missing from district d
   where left(d.sigungu_code, 2) in ({sido_list})
     and not exists (select 1 from stage_census_pop s where s.district_id = d.district_id);
  select count(*) into v_extra from stage_census_pop s
   where not exists (select 1 from district d
                      where d.district_id = s.district_id and left(d.sigungu_code, 2) in ({sido_list}));
  if v_missing > 0 or v_extra > 0 then
    raise exception '⒤ 결과표 상권이 district 와 다릅니다 — 결과표에 빠진 상권 % · district 에 없는 줄 % (상권을 다시 적재했으면 다시 굽으세요 · 통째로 되돌립니다)', v_missing, v_extra;
  end if;
end $$;

-- ── 관문 ⒥ — 받은 날 앞으로만(같은 날이면 다시 넣기 허용) ─────────────
do $$
begin
  if exists (select 1 from sgis_census_release where received_on > date '{received_on}') then
    raise exception '⒥ 지금 DB 의 받은 날이 {received_on} 보다 뒤입니다 — 옛 판으로 되돌리지 않습니다(통째로 되돌립니다)';
  end if;
end $$;

-- 통째 교체 — 결과표는 받은 판마다 통째 다시 굽는다. 우리 표 · 읽는 곳은 함수 하나.
truncate district_census_pop;
insert into district_census_pop ({cols})
  select {cols} from stage_census_pop;

insert into sgis_census_release (id, received_on, base_year, bnd_base_date, n_oa_total, rows_cnt, built_at,
                                 overlap_min_m2, full_ratio)
values (1, date '{received_on}', {base_year}, date '{bnd_base_date}', {n_oa_total}, {rows},
        timestamptz '{built_at}', {overlap_min_m2}, {full_ratio})
on conflict (id) do update set received_on = excluded.received_on, base_year = excluded.base_year,
                               bnd_base_date = excluded.bnd_base_date, n_oa_total = excluded.n_oa_total,
                               rows_cnt = excluded.rows_cnt, built_at = excluded.built_at,
                               overlap_min_m2 = excluded.overlap_min_m2, full_ratio = excluded.full_ratio;

do $$
begin
  if (select count(*) from district_census_pop) <> {rows} then
    raise exception '표에 든 행 수가 기대({rows})와 다릅니다 — 통째로 되돌립니다';
  end if;
end $$;

select count(*) as census_pop_rows,
       sum(pop) as pop_sum,
       count(*) filter (where n_full = 0) as zero_full,
       (select received_on from sgis_census_release) as received_on
  from district_census_pop;

commit;
""".format(cols=cols, path=copy_path_literal(path), rows=int(rows),
           sido_list=", ".join("'{}'".format(s) for s in meta["sido"]),
           received_on=_date(meta["received_on"]).isoformat(), base_year=int(meta["base_year"]),
           bnd_base_date=_date(meta["bnd_base_date"]).isoformat(), n_oa_total=int(meta["n_oa_total"]),
           built_at=datetime.datetime.fromisoformat(meta["built_at"]).isoformat(),
           overlap_min_m2=float(meta["overlap_min_m2"]), full_ratio=float(meta["full_ratio"]))


# ── 메인 ─────────────────────────────────────────────────────────────────────


def main(argv=None, today=None):
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="대전 상권 안 인구 결과표 → district_census_pop 통째 교체",
                                allow_abbrev=False)
    p.add_argument("--csv", default=None, help="결과표 csv(기본 = data/derived/sgis_district_pop/ 의 가장 늦은 것)")
    p.add_argument("--staging-dir", default=DEFAULT_STAGING_DIR)
    p.add_argument("--dry-run", action="store_true", help="관문 ⒜~⒣ + 요약만 — DB·파일 쓰기 0")
    a = p.parse_args(argv)

    csv_path = a.csv or default_csv()
    try:
        meta = read_meta(csv_path)
        problems, stats = check_csv(csv_path, meta, today=today)
    except (GateError, OSError, ValueError) as e:
        print("실패 — DB 에는 아무것도 쓰지 않았습니다: {}".format(e), file=sys.stderr)
        return 1

    print("=" * 74)
    print("대전 상권 안 인구 결과표 → district_census_pop {}".format("(dry-run)" if a.dry_run else ""))
    print("=" * 74)
    print("  결과표 {} · 받은 날 {} · 통계 {}년 · 경계 {} · 시·도 {}".format(
        os.path.basename(csv_path), meta["received_on"], meta["base_year"], meta["bnd_base_date"], meta["sido"]))
    print("  줄 {:,} · 통째 0 인 상권 {:,} · 거주 인구 배분 합 {:,}".format(
        stats["rows"], stats["zero_full"], stats["pop_sum"]))

    if problems:
        print()
        print("관문에 걸렸습니다 — DB 에는 아무것도 쓰지 않았습니다:", file=sys.stderr)
        for m in problems:
            print("  " + m, file=sys.stderr)
        return 1
    print("  관문 통과 (⒜ · ⒝ · ⒞ · ⒟ · ⒠ · ⒡ · ⒢ · ⒣)")
    print("  ⒤ (상권 집합 = district 의 시·도 {}) · ⒥ (받은 날 앞으로만) 는 실적재 때 DB 안에서 본다".format(meta["sido"]))

    if a.dry_run:
        print()
        print("--dry-run — DB·파일에 아무것도 쓰지 않았습니다.")
        return 0

    staging = os.path.join(a.staging_dir, "district_census_pop.csv")
    n = write_staging(csv_path, staging)
    if n != stats["rows"]:
        print("사본 줄 수 {} ≠ 관문에서 센 {} — 멈춥니다(DB 쓰기 0).".format(n, stats["rows"]), file=sys.stderr)
        return 1
    sql = build_sql(staging, n, meta)

    import dbx  # noqa: PLC0415  (dry-run 은 DB 설정 없이도 돌아야 한다)
    rc = dbx.run_sql(sql)
    if rc != 0:
        print("적재 실패 (psql 종료코드 {}). 트랜잭션이라 아무것도 안 들어갔습니다.".format(rc), file=sys.stderr)
        return rc
    print()
    print("  적재 완료 ({}).".format(datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")))
    print("  다음: python scripts/post_load.py   그리고   python scripts/post_load.py --check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
