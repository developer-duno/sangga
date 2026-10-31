# -*- coding: utf-8 -*-
"""가게 이력 결과표(로컬 빌드 csv) → DB store_history 통째 교체 (결정 0045 PR④ · 한 트랜잭션).

무엇을 넣나
-----------
`scripts/build_store_history.py` 가 로컬 zip 을 읽어 구운 `data/derived/store_history/<YYYYMMDD>.csv`
(+ 같은 이름 `.meta.json`)을 **그대로** 넣는다 — 가게(사슬)마다 한 줄:
  pnu,floor_no,biz_name,biz_no_last,first_ym,last_ym,seen_cnt,is_current,n_links,truncated
그리고 표지 store_history_release 한 줄(id = 1 · last_ym = 결과표의 마지막 분기 · 빌드 날 · 줄 수).
⛔ seen_cnt 는 「자료에 보인 분기 수」이지 영업 기간이 아니다 · 지금 안 보임 ≠ 폐업.

관문 (하나라도 걸리면 DB 는 손도 안 댄다 · exit 1)
--------------------------------------------------
  ⒜ csv · meta 둘 다 있다 · meta partial = false · sido = ["11","30"] · start_ym = 201712
  ⒝ 머리줄 = 위 열 칸 글자 그대로
  ⒞ 분기 꼴 YYYY(03|06|09|12) · first_ym ≤ last_ym · first_ym ≥ start_ym · last_ym ≤ end_ym ·
     is_current ⇔ last_ym = end_ym · truncated ⇔ first_ym = start_ym (t/f 만)
  ⒟ pnu 19자리 숫자 + 앞 두 자리 ∈ sido
  ⒠ seen_cnt 1 이상 · first_ym~last_ym 분기 수 이하 · n_links 0 이상 (정수)
  ⒡ (biz_no_last, first_ym) 중복 0 (표의 주 열쇠 · biz_no_last 빈 칸도 여기서 멈춘다)
  ⒢ 행수 범위 ROWS_RANGE · 지금 보이는 줄 수 CURRENT_RANGE
  ⒣ meta rows = csv 줄 수 · meta sha256 = csv 지문
  ⒤ floor_no = 빈 칸(층 모름) 또는 0 아닌 정수 -9~99 (절대 규칙 4)
  ⒥ biz_name 비어 있지 않음
  ⒦ (DB 안 · 실적재 SQL 안) meta end_ym = snapshot_release.loaded_ym — 아니면 raise → 통째 롤백.
     「최신 분기 = unit_business 에 적재된 최신 분기」를 **표지로** 읽는다 — 270만 행 max(snapshot_ym) 를 훑지 않고,
     결정 0035 가 「다 들어온 분기」로 정한 칸이 바로 그 값이다(전국 모드 적재 + 교차검증을 지나야 올라간다).

잠금
----
  TRUNCATE 는 ACCESS EXCLUSIVE 를 잡는다(PostgreSQL 문서 13.3 Explicit Locking: ACCESS EXCLUSIVE 는
  "Acquired by the DROP TABLE, TRUNCATE, REINDEX, …" · 2026-10-31 확인). 이 표를 읽는 건 함수 get_store_history 하나뿐이고 lock_timeout 5s 라
  못 잡으면 기다리지 않고 통째 롤백한다. delete 130만 줄보다 빠르고, 트랜잭션 안이라 실패하면 되돌아간다.

쓰는 법 (프로젝트 루트에서)
---------------------------
    python scripts/collectors/load_store_history.py --dry-run     # 관문 ⒜~⒥ + 요약 (DB·파일 쓰기 0)
    python scripts/collectors/load_store_history.py               # 실적재 (관문 ⒦ 는 DB 안에서)
    → python scripts/post_load.py   그리고   python scripts/post_load.py --check
  `--csv` 를 안 주면 data/derived/store_history/ 에서 이름(YYYYMMDD)이 가장 늦은 csv 를 쓴다.
  ⛔ 운영 순서(결정 0045): 상권 새 분기 전국 모드 적재 → build_store_history.py → 이 적재 → post_load.py.
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

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
DEFAULT_CSV_DIR = os.path.join(PROJECT_ROOT, "data", "derived", "store_history")
DEFAULT_STAGING_DIR = os.path.join(PROJECT_ROOT, "data", "staging", "store_history")

COLUMNS = ("pnu", "floor_no", "biz_name", "biz_no_last", "first_ym", "last_ym",
           "seen_cnt", "is_current", "n_links", "truncated")
RE_CSV_NAME = re.compile(r"^\d{8}\.csv$")
RE_YM = re.compile(r"^\d{4}(03|06|09|12)$")
RE_PNU = re.compile(r"^\d{19}$")
RE_INT = re.compile(r"^-?\d+$")

EXPECT_SIDO = ["11", "30"]
EXPECT_START_YM = "201712"
# 조사 C(2026-10-31): 오늘 가게 서울 554,092 + 대전 80,704 = 634,796 · DB 202606 서울 554,069 + 대전 80,701
ROWS_RANGE = (900_000, 2_000_000)
CURRENT_RANGE = (600_000, 680_000)
FLOOR_RANGE = (-9, 99)
EXAMPLES = 3


class GateError(ValueError):
    """관문에 걸림 — DB 에 아무것도 안 쓴다."""


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


def read_meta(csv_path):
    """⒜ — csv·meta 가 있고 partial false · sido · start_ym 이 기대대로. → meta dict."""
    if not csv_path or not os.path.isfile(csv_path):
        raise GateError("⒜ 결과표 csv 가 없습니다: {}".format(csv_path))
    mpath = meta_path_for(csv_path)
    if not os.path.isfile(mpath):
        raise GateError("⒜ 짝 meta 가 없습니다: {}".format(mpath))
    with io.open(mpath, encoding="utf-8") as f:
        meta = json.load(f)
    bad = []
    if meta.get("partial") is not False:
        bad.append("partial = {!r}(--limit-quarters 로 구운 판은 넣지 않는다)".format(meta.get("partial")))
    if meta.get("sido") != EXPECT_SIDO:
        bad.append("sido = {!r} (기대 {})".format(meta.get("sido"), EXPECT_SIDO))
    if meta.get("start_ym") != EXPECT_START_YM:
        bad.append("start_ym = {!r} (기대 {})".format(meta.get("start_ym"), EXPECT_START_YM))
    end_ym = meta.get("end_ym")
    if not isinstance(end_ym, str) or not RE_YM.match(end_ym):
        bad.append("end_ym = {!r} (YYYY03|06|09|12 꼴)".format(end_ym))
    for key in ("rows", "sha256", "built_on"):
        if key not in meta:
            bad.append("{} 칸이 없습니다".format(key))
    if not bad:
        try:
            datetime.date.fromisoformat(meta["built_on"])
        except (TypeError, ValueError):
            bad.append("built_on = {!r} (YYYY-MM-DD)".format(meta["built_on"]))
    if bad:
        raise GateError("⒜ meta 가 기대와 다릅니다 — " + " · ".join(bad))
    return meta


def quarter_span(first_ym, last_ym):
    """first~last 사이 분기 수(양끝 포함)."""
    def idx(ym):
        return int(ym[:4]) * 4 + int(ym[4:]) // 3
    return idx(last_ym) - idx(first_ym) + 1


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ── 관문 ─────────────────────────────────────────────────────────────────────


def row_problems(r, meta):
    """한 줄 → [(관문 글자, 문장)] (비면 통과). r = csv 칸 열 개."""
    pnu, floor_no, name, biz, first, last, seen, cur, links, trunc = r
    start, end, sido = meta["start_ym"], meta["end_ym"], meta["sido"]
    out = []
    if not (RE_YM.match(first) and RE_YM.match(last)):
        out.append(("⒞", "분기 꼴이 아닙니다 first={!r} last={!r}".format(first, last)))
    elif not (start <= first <= last <= end):
        out.append(("⒞", "분기 차례가 틀렸습니다 {}~{} (범위 {}~{})".format(first, last, start, end)))
    if cur not in ("t", "f") or trunc not in ("t", "f"):
        out.append(("⒞", "is_current·truncated 는 t/f: {!r} {!r}".format(cur, trunc)))
    else:
        if (cur == "t") != (last == end):
            out.append(("⒞", "is_current={} 인데 last_ym={} (end {})".format(cur, last, end)))
        if (trunc == "t") != (first == start):
            out.append(("⒞", "truncated={} 인데 first_ym={} (start {})".format(trunc, first, start)))
    if not RE_PNU.match(pnu) or pnu[:2] not in sido:
        out.append(("⒟", "pnu {!r} (19자리 숫자 · 앞 두 자리 ∈ {})".format(pnu, sido)))
    if not (RE_INT.match(seen) and RE_INT.match(links)):
        out.append(("⒠", "seen_cnt·n_links 가 정수가 아닙니다 {!r} {!r}".format(seen, links)))
    else:
        span = quarter_span(first, last) if RE_YM.match(first) and RE_YM.match(last) else None
        if int(seen) < 1 or (span is not None and int(seen) > span) or int(links) < 0:
            out.append(("⒠", "seen_cnt={} n_links={} (1 ≤ seen ≤ 분기 수 {} · links ≥ 0)".format(seen, links, span)))
    if not biz:
        out.append(("⒡", "biz_no_last 가 비었습니다"))
    if floor_no != "":
        if not RE_INT.match(floor_no) or int(floor_no) == 0 or not FLOOR_RANGE[0] <= int(floor_no) <= FLOOR_RANGE[1]:
            out.append(("⒤", "floor_no {!r} (빈 칸 또는 0 아닌 정수 {}~{})".format(floor_no, *FLOOR_RANGE)))
    if not name.strip():
        out.append(("⒥", "biz_name 이 비었습니다"))
    return out


def check_csv(csv_path, meta):
    """⒝~⒥ 를 한 번 훑어 본다. → (문제 문장 목록, 셈 dict). 줄은 메모리에 두지 않는다(열쇠만)."""
    problems = collections.OrderedDict()
    keys = set()
    stats = collections.Counter()
    per_end = collections.Counter()
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
            for code, msg in row_problems(r, meta):
                problems.setdefault(code, []).append("{}줄: {}".format(i, msg))
            key = (r[3], r[4])
            if key in keys:
                problems.setdefault("⒡", []).append("{}줄: (biz_no_last, first_ym) 중복 {}".format(i, key))
            keys.add(key)
            if r[7] == "t":
                stats["current"] += 1
            if r[1] == "":
                stats["floor_unknown"] += 1
            if r[9] == "t":
                stats["truncated"] += 1
            stats["n_links"] += int(r[8]) if RE_INT.match(r[8]) else 0
            per_end[r[5]] += 1
    lo, hi = ROWS_RANGE
    if not lo <= stats["rows"] <= hi:
        problems.setdefault("⒢", []).append("줄 수 {:,} 가 {:,}~{:,} 밖".format(stats["rows"], lo, hi))
    lo, hi = CURRENT_RANGE
    if not lo <= stats["current"] <= hi:
        problems.setdefault("⒢", []).append("지금 보이는 줄 {:,} 가 {:,}~{:,} 밖".format(stats["current"], lo, hi))
    if meta["rows"] != stats["rows"]:
        problems.setdefault("⒣", []).append("meta rows {} ≠ csv 줄 수 {}".format(meta["rows"], stats["rows"]))
    digest = file_sha256(csv_path)
    if meta["sha256"] != digest:
        problems.setdefault("⒣", []).append("meta sha256 ≠ csv 지문 {}".format(digest))
    out = []
    for code in sorted(problems):
        msgs = problems[code]
        out.append("{} {}건 — {}".format(code, len(msgs), " / ".join(msgs[:EXAMPLES])))
    stats["last_ym_max"] = max(per_end) if per_end else ""
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
    """적재 SQL — 한 트랜잭션. ⒦ 표지 대조 · 통째 교체 · 표지 upsert. 어긋나면 raise(psql 은 select 와 무관하게 0)."""
    cols = ", ".join(COLUMNS)
    return """begin;
set local statement_timeout = '600s';
set local lock_timeout = '5s';

create temp table stage_history (like store_history including defaults) on commit drop;

\\copy stage_history ({cols}) from '{path}' with (format csv, header true, encoding 'UTF8')

-- ── 행수 대조 — CSV 가 잘려도 \\copy 는 에러 없이 거기까지만 넣는다 ─────────────
do $$
begin
  if (select count(*) from stage_history) <> {rows} then
    raise exception '올린 행 수가 결과표 줄 수({rows})와 다릅니다 — 통째로 되돌립니다';
  end if;
end $$;

-- ── 관문 ⒦ — 결과표의 마지막 분기 = 점포 표에 다 들어온 분기(결정 0035 표지 loaded_ym) ─────
do $$
begin
  if (select loaded_ym from snapshot_release) is distinct from '{end_ym}' then
    raise exception '⒦ 결과표 마지막 분기 {end_ym} ≠ snapshot_release.loaded_ym — 새 분기를 다시 굽거나 점포 적재를 먼저 하세요(통째로 되돌립니다)';
  end if;
end $$;

-- 통째 교체 — 결과표는 매 분기 통째 다시 굽는다(결정 0045). 우리 표 · 읽는 곳은 함수 하나.
truncate store_history;
insert into store_history ({cols})
  select {cols} from stage_history;

insert into store_history_release (id, last_ym, built_on, row_cnt, loaded_at)
values (1, '{end_ym}', date '{built_on}', {rows}, now())
on conflict (id) do update set last_ym = excluded.last_ym, built_on = excluded.built_on,
                               row_cnt = excluded.row_cnt, loaded_at = excluded.loaded_at;

do $$
begin
  if (select count(*) from store_history) <> {rows} then
    raise exception '표에 든 행 수가 기대({rows})와 다릅니다 — 통째로 되돌립니다';
  end if;
end $$;

select count(*) as history_rows,
       count(*) filter (where is_current) as current_rows,
       max(last_ym) as last_ym_max,
       (select last_ym from store_history_release) as release_last_ym
  from store_history;

commit;
""".format(cols=cols, path=copy_path_literal(path), rows=int(rows), end_ym=meta["end_ym"],
           built_on=meta["built_on"])


# ── 메인 ─────────────────────────────────────────────────────────────────────


def main(argv=None):
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="가게 이력 결과표 → store_history 통째 교체", allow_abbrev=False)
    p.add_argument("--csv", default=None, help="결과표 csv(기본 = data/derived/store_history/ 의 가장 늦은 것)")
    p.add_argument("--staging-dir", default=DEFAULT_STAGING_DIR)
    p.add_argument("--dry-run", action="store_true", help="관문 ⒜~⒥ + 요약만 — DB·파일 쓰기 0")
    a = p.parse_args(argv)

    csv_path = a.csv or default_csv()
    try:
        meta = read_meta(csv_path)
        problems, stats = check_csv(csv_path, meta)
    except (GateError, OSError, ValueError) as e:
        print("실패 — DB 에는 아무것도 쓰지 않았습니다: {}".format(e), file=sys.stderr)
        return 1

    print("=" * 74)
    print("가게 이력 결과표 → store_history {}".format("(dry-run)" if a.dry_run else ""))
    print("=" * 74)
    print("  결과표 {} · 빌드 {} · {}~{} · {}분기 · 시·도 {}".format(
        os.path.basename(csv_path), meta["built_on"], meta["start_ym"], meta["end_ym"],
        meta.get("quarters"), meta["sido"]))
    print("  줄 {:,} · 지금 보임 {:,} · 층 모름 {:,} · truncated {:,} · n_links 합 {:,} · 가장 늦은 last_ym {}".format(
        stats["rows"], stats["current"], stats["floor_unknown"], stats["truncated"], stats["n_links"],
        stats["last_ym_max"]))

    if problems:
        print()
        print("관문에 걸렸습니다 — DB 에는 아무것도 쓰지 않았습니다:", file=sys.stderr)
        for m in problems:
            print("  " + m, file=sys.stderr)
        return 1
    print("  관문 통과 (⒜ · ⒝ · ⒞ · ⒟ · ⒠ · ⒡ · ⒢ · ⒣ · ⒤ · ⒥)")
    print("  ⒦ (마지막 분기 {} = snapshot_release.loaded_ym) 는 실적재 때 DB 안에서 본다".format(meta["end_ym"]))

    if a.dry_run:
        print()
        print("--dry-run — DB·파일에 아무것도 쓰지 않았습니다.")
        return 0

    staging = os.path.join(a.staging_dir, "store_history.csv")
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
    print("  적재 완료 ({}).".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    print("  다음: python scripts/post_load.py   그리고   python scripts/post_load.py --check")
    print("  디스크 전후를 pg_total_relation_size('store_history') 로 재어 PROGRESS 에 적는다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
