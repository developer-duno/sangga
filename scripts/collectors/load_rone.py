# -*- coding: utf-8 -*-
"""
R-ONE 임대동향조사 raw JSONL → Supabase 적재 (rent_stat)

collect_rone.py가 받아둔 raw(24개 파일: 4건물유형 x 6지표)를 읽어 rent_stat
테이블을 채운다. raw는 읽기만 한다 (CLAUDE.md 수집 규칙: raw 불변).

무엇을 하나:
  1. 지역 매칭 — R-ONE의 지역 축은 시군구가 아니라 상권이다(§1.2). floor_util
     표만 GRP_ID(지역 식별자)를 직접 준다고 보고, 나머지 5개 표는 CLS_NM(지역
     이름 텍스트)만 있다고 보아 floor_util의 이름→GRP_ID 조회표로 되짚는다.
  2. 층별효용비율 — floor_util 표의 CLS_NM(층 7구간)을 floor_bucket_key()로
     jsonb 키("-1"·"1".."5"·"6+")로 바꾼다. ITM_NM='효용비율'인 행만 채택하고
     ('임대료' 행은 버림), 값이 없는 층은 키 자체를 만들지 않는다(0 금지 —
     CLAUDE.md 절대 규칙 4를 jsonb 레벨로 확장).
  3. 6개 지표를 (분기, 지역, 건물유형) 키로 병합한다 — 일부 지표가 없어도
     (quiet-zero·이름 미매칭) 그 컬럼만 NULL, 나머지는 채운다(부분 병합).
  4. 적재 후 지역 매칭 성공/실패·층별효용비율 채움 비율을 실측 보고한다.

⚠️ 알려진 한계 (설계 단계에서 이미 드러난 것 — 재조사 불필요):
  - **jsonb만 봐서는 "R-ONE에 애초에 없는 층"과 "이번 분기 값이 빈 층"을 못
    구분한다.** 둘 다 그냥 키가 없는 걸로 보인다. §6.1의 13.3%(지하2층 이하·
    옥탑) 결측은 이 한계 때문에 화면 쪽에서 별도로 안내해야 한다.
  - **지역 매칭은 이름 문자열 일치에 의존한다.** floor_util 표에 없는 지역
    이름이 다른 표에만 나오면 그 행은 통째로 스킵된다(unmatched로 카운트).

사용법:
  python scripts/collectors/load_rone.py --dry-run
  python scripts/collectors/load_rone.py
  python scripts/collectors/load_rone.py --bld-type 집합상가
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict

import requests
from dotenv import load_dotenv

from collect_rone import BLD_TYPE_SLUG, BLD_TYPES, METRICS

# ── 설정 ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW_SUBDIR = "rone"

# collect_rone.floor_bucket_key()가 만드는 층 구간 수(지하1층·1~5층·6층이상=7).
# 채움 비율 보고용 — floor_bucket_key 자체를 import하지 않고 개수만 고정값으로 둔다.
FLOOR_BUCKET_COUNT = 7

# yield(수익률) 표는 다른 지표가 섞여 나올 수 있어 ITM_NM으로 골라야 한다(설계 요구사항).
YIELD_ITEM_NAME = "투자수익률"
FLOOR_UTIL_RATIO_ITEM_NAME = "효용비율"

# 지표 -> rent_stat 컬럼명. floor_util은 컬럼 2개(region_nm은 공용, floor_util_ratio
# 전용)를 만들어 별도 처리하므로 이 표에는 없다.
METRIC_TO_COLUMN = {
    "region_rent": "rent_per_m2",
    "vacancy": "vacancy_rate",
    "rent_price_index": "rent_price_index",
    "yield": "yield_rate",
    "conversion": "conversion_rate",
}

BATCH_SIZE = 1000
TIMEOUT_SEC = 120

_API_QUARTER_RE = re.compile(r"^(\d{4})(0[1-4])$")


# ── 순수 로직 (네트워크·DB 없음 — 테스트 대상) ─────────────────────────────────


def s(value):
    """어떤 타입으로 오든 문자열로 정규화한다 (load_transactions.py의 s()와 같은 이유)."""
    return "" if value is None else str(value).strip()


def to_float(raw):
    t = s(raw).replace(",", "")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def api_quarter_to_db_quarter(api_qid):
    """R-ONE 분기 시점('202602') -> rent_stat.quarter 표기('2026Q2'). 형식이 이상하면 None."""
    m = _API_QUARTER_RE.match(s(api_qid))
    if not m:
        return None
    year, q = m.group(1), int(m.group(2))
    return "{}Q{}".format(year, q)


def build_name_lookup(floor_util_rows):
    """floor_util raw 행들(한 건물유형 x 한 분기 스코프)에서 {GRP_NM: GRP_ID}를 만든다.

    같은 이름에 다른 GRP_ID가 나오면(상권 계층 재편 등) 자동으로 죽이지 않고
    conflicts Counter에 기록만 한다 — 사람이 보고 판단한다.
    반환: (lookup dict, conflicts Counter)
    """
    lookup = {}
    conflicts = Counter()
    for row in floor_util_rows:
        name = s(row.get("GRP_NM"))
        gid = s(row.get("GRP_ID"))
        if not name or not gid:
            continue
        if name in lookup and lookup[name] != gid:
            conflicts[name] += 1
            continue
        lookup[name] = gid
    return lookup, conflicts


def resolve_region_code(cls_nm, name_lookup):
    """CLS_NM(지역명 텍스트) -> GRP_ID(str). 못 찾으면 None(스킵 — 조용히 죽이지 않는다)."""
    return name_lookup.get(s(cls_nm)) or None


def build_floor_util_ratio(rows):
    """floor_util raw 행(한 지역 x 한 분기 스코프) -> {floor_bucket_key: DTA_VAL} dict.

    ITM_NM=='효용비율'인 행만 채택한다('임대료' 행은 버림 — floor_util_ratio
    컬럼은 비율 전용, schema.sql 주석과 일치). DTA_VAL이 null/파싱불가인 행은
    키 자체를 만들지 않는다(0도 아니고 null 키도 아니고 부재).
    """
    # 지연 임포트가 아니라 함수 밖에서 import하면 순환참조 위험이 없어 상단에 둔다.
    from collect_rone import floor_bucket_key

    out = {}
    for row in rows:
        if s(row.get("ITM_NM")) != FLOOR_UTIL_RATIO_ITEM_NAME:
            continue
        key = floor_bucket_key(row.get("CLS_NM"))
        if key is None:
            continue
        val = to_float(row.get("DTA_VAL"))
        if val is None:
            continue
        out[key] = val
    return out


def build_floor_util_by_region(floor_util_rows):
    """floor_util raw 행(한 건물유형 x 한 분기 스코프) -> {GRP_ID: {region_nm, floor_util_ratio}}."""
    grouped = defaultdict(list)
    for row in floor_util_rows:
        gid = s(row.get("GRP_ID"))
        if not gid:
            continue
        grouped[gid].append(row)

    out = {}
    for gid, rows in grouped.items():
        region_nm = s(rows[0].get("GRP_FULLNM")) or s(rows[0].get("GRP_NM")) or None
        out[gid] = {"region_nm": region_nm, "floor_util_ratio": build_floor_util_ratio(rows)}
    return out


def extract_metric_value(row, item_name=None):
    """비-floor 지표 raw 행 하나 -> DTA_VAL(float) 또는 None.

    item_name을 주면 ITM_NM이 그 값과 일치하는 행만 채택한다(yield 표에 다른
    지표가 섞여 나올 수 있어서). 나머지 표는 필터 없이 DTA_VAL을 그대로 쓴다.
    """
    if item_name is not None and s(row.get("ITM_NM")) != item_name:
        return None
    return to_float(row.get("DTA_VAL"))


def build_metric_by_region(rows, name_lookup, item_name=None):
    """비-floor 지표 raw 행 목록(한 건물유형 x 한 분기 스코프) -> ({region_code: value}, unmatched Counter).

    CLS_NM(지역명 텍스트)을 floor_util의 이름→GRP_ID 조회표로 region_code화한다.
    못 찾은 이름은 unmatched로 세고 그 행은 스킵한다(조용히 죽이지 않는다).
    """
    out = {}
    unmatched = Counter()
    for row in rows:
        val = extract_metric_value(row, item_name=item_name)
        if val is None:
            continue
        rc = resolve_region_code(row.get("CLS_NM"), name_lookup)
        if rc is None:
            unmatched[s(row.get("CLS_NM"))] += 1
            continue
        out[rc] = val
    return out, unmatched


def merge_metrics(quarter, bld_type, per_metric_rows):
    """quarter(YYYYQQ) x bld_type x {지표: {region_code: 값}} -> rent_stat upsert dict 목록.

    (분기, 지역, 건물유형) 키로 6개 조각을 병합한다. 일부 지표가 없어도
    (quiet-zero·이름 미매칭) 그 컬럼만 NULL로 두고 나머지는 채운다(전량주의 금지).
    quarter 형식이 이상하면 (api_quarter_to_db_quarter가 None) 빈 목록.
    """
    db_quarter = api_quarter_to_db_quarter(quarter)
    if db_quarter is None:
        return []

    floor_util = per_metric_rows.get("floor_util") or {}
    region_codes = set(floor_util.keys())
    for metric in METRIC_TO_COLUMN:
        region_codes |= set((per_metric_rows.get(metric) or {}).keys())

    records = []
    for rc in sorted(region_codes):
        fu = floor_util.get(rc) or {}
        row = {
            "quarter": db_quarter,
            "region_code": rc,
            "region_nm": fu.get("region_nm"),
            "bld_type": bld_type,
            "floor_util_ratio": fu.get("floor_util_ratio") or None,
        }
        for metric, column in METRIC_TO_COLUMN.items():
            values = per_metric_rows.get(metric) or {}
            row[column] = values.get(rc)
        records.append(row)
    return records


def assert_unique(records, fields=("quarter", "region_code", "bld_type")):
    """rent_stat의 복합 PK(quarter, region_code, bld_type) 중복을 upsert 전에 잡는다."""
    seen = set()
    for r in records:
        key = tuple(r.get(f) for f in fields)
        if key in seen:
            raise RuntimeError(
                "{} 조합이 중복된 행이 있습니다 ({!r}) — upsert 전에 해결해야 합니다.".format(
                    "+".join(fields), key))
        seen.add(key)
    return len(records)


def read_jsonl(path):
    """raw JSONL을 읽는다. 깨진 줄은 건너뛰고 개수만 센다."""
    rows, broken = [], 0
    if not os.path.exists(path):
        return rows, broken
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                broken += 1
    return rows, broken


def latest_batch(rows):
    """(건물유형, 지표, 분기)마다 fetched_at이 가장 늦은 배치만 남긴다.

    raw는 append이므로 같은 조합을 두 번 수집하면 두 배치가 쌓인다. 그대로
    적재하면 값이 두 번 겹쳐 병합에 혼선을 준다(load_transactions.py의
    latest_batch()와 같은 이유).
    """
    newest = {}
    for r in rows:
        k = (r.get("bld_type"), r.get("metric"), r.get("quarter_id"))
        f = r.get("fetched_at") or ""
        if k not in newest or f > newest[k]:
            newest[k] = f
    return [r for r in rows
            if (r.get("fetched_at") or "") == newest.get(
                (r.get("bld_type"), r.get("metric"), r.get("quarter_id")))]


def raw_path(raw_dir, bld_type, metric):
    """collect_rone.raw_path()와 동일한 경로 규칙(중복 정의 — 순환참조 회피)."""
    return os.path.join(raw_dir, BLD_TYPE_SLUG[bld_type], "{}.jsonl".format(metric))


def process_bld_type(raw_dir, bld_type):
    """한 건물유형의 raw 6종을 읽어 (rent_stat upsert dict 목록, 리포트 통계)를 만든다."""
    raw_by_metric = {}
    broken_total = 0
    for metric in METRICS:
        rows, broken = read_jsonl(raw_path(raw_dir, bld_type, metric))
        rows = latest_batch(rows)
        raw_by_metric[metric] = [r for r in rows if r.get("bld_type") == bld_type]
        broken_total += broken

    quarters = set()
    for metric in METRICS:
        quarters |= {r.get("quarter_id") for r in raw_by_metric[metric] if r.get("quarter_id")}

    records = []
    stats = {
        "raw_rows": {m: len(raw_by_metric[m]) for m in METRICS},
        "unmatched": Counter(),
        "conflicts": Counter(),
        "floor_util_fill": [],   # 각 (지역,분기)의 채움 비율(0~1) — 평균 보고용
    }

    for quarter in sorted(quarters):
        fu_rows = [r["row"] for r in raw_by_metric["floor_util"]
                   if r.get("quarter_id") == quarter and isinstance(r.get("row"), dict)]
        name_lookup, conflicts = build_name_lookup(fu_rows)
        stats["conflicts"].update(conflicts)
        floor_util_by_region = build_floor_util_by_region(fu_rows)
        for region in floor_util_by_region.values():
            stats["floor_util_fill"].append(len(region["floor_util_ratio"]) / FLOOR_BUCKET_COUNT)

        per_metric_rows = {"floor_util": floor_util_by_region}
        for metric in METRIC_TO_COLUMN:
            m_rows = [r["row"] for r in raw_by_metric[metric]
                      if r.get("quarter_id") == quarter and isinstance(r.get("row"), dict)]
            item_name = YIELD_ITEM_NAME if metric == "yield" else None
            by_region, unmatched = build_metric_by_region(m_rows, name_lookup, item_name=item_name)
            stats["unmatched"].update(unmatched)
            per_metric_rows[metric] = by_region

        records.extend(merge_metrics(quarter, bld_type, per_metric_rows))

    return records, stats, broken_total


# ── Supabase(PostgREST) ──────────────────────────────────────────────────────


def get_supabase_config():
    load_dotenv()
    url = os.environ.get("SANGGA_SUPABASE_URL", "").strip().rstrip("/")
    key = (os.environ.get("SANGGA_SUPABASE_SERVICE_KEY")
           or os.environ.get("SANGGA_SUPABASE_ANON_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError(".env에 SANGGA_SUPABASE_URL과 키가 필요합니다.")
    return url, key


def upsert_batch(base_url, headers, table, rows, resolution, batch_size=BATCH_SIZE):
    sent = 0
    total = (len(rows) + batch_size - 1) // batch_size
    for i in range(0, len(rows), batch_size):
        part = rows[i:i + batch_size]
        no = i // batch_size + 1
        try:
            r = requests.post(
                "{}/rest/v1/{}".format(base_url, table),
                headers=dict(headers, **{
                    "Content-Type": "application/json",
                    "Prefer": "resolution={},return=minimal".format(resolution),
                }),
                data=json.dumps(part, ensure_ascii=False).encode("utf-8"),
                timeout=TIMEOUT_SEC,
            )
        except requests.RequestException as e:
            raise RuntimeError("{} 저장 {}/{} 중 네트워크 오류: {}".format(table, no, total, e))
        if r.status_code >= 300:
            raise RuntimeError("{} 저장 {}/{} 실패 (HTTP {}): {}".format(
                table, no, total, r.status_code, r.text[:300]))
        sent += len(part)
        print("  [{}] {}/{} 배치 {:,}행 (누적 {:,}/{:,})".format(
            table, no, total, len(part), sent, len(rows)), flush=True)
    return sent


def assert_table_exists(base_url, headers, table):
    """적재 전에 대상 테이블이 라이브에 있는지 확인한다 (반쯤 적재 방지)."""
    r = requests.get("{}/rest/v1/{}".format(base_url, table),
                     params={"select": "*", "limit": "1"},
                     headers=headers, timeout=TIMEOUT_SEC)
    if r.status_code == 404:
        raise RuntimeError(
            "라이브 DB에 '{}' 테이블이 없습니다.\n"
            "       Supabase 대시보드 → SQL Editor에서 supabase/schema.sql을 먼저 적용하세요.".format(table))
    if r.status_code >= 300:
        raise RuntimeError("{} 조회 실패 (HTTP {}): {}".format(table, r.status_code, r.text[:200]))


# ── 보고 ─────────────────────────────────────────────────────────────────────


def print_report(all_stats, broken_total, record_count):
    print("=" * 78)
    print("R-ONE raw → rent_stat 변환 결과")
    print("=" * 78)
    if broken_total:
        print("  [경고] 파싱 불가로 건너뛴 줄: {:,}".format(broken_total))
    for bld_type, stats in all_stats:
        print("")
        print("[ {} ]".format(bld_type))
        print("  raw 행수: " + " / ".join(
            "{} {:,}".format(m, stats["raw_rows"][m]) for m in METRICS))
        if stats["unmatched"]:
            top = ", ".join("{}({})".format(k, v) for k, v in stats["unmatched"].most_common(5))
            print("  지역명 미매칭 {:,}건 (상위: {})".format(sum(stats["unmatched"].values()), top))
        if stats["conflicts"]:
            print("  ⚠️ 같은 이름·다른 GRP_ID 충돌 {:,}건".format(sum(stats["conflicts"].values())))
        if stats["floor_util_fill"]:
            avg = sum(stats["floor_util_fill"]) / len(stats["floor_util_fill"])
            print("  층별효용비율 평균 채움 비율: {:.1f}% ({}개 지역x분기, §6.1의 66.6%와 참고 대조)".format(
                avg * 100, len(stats["floor_util_fill"])))
    print("")
    print("[ rent_stat ] {:,}행 (would-upsert)".format(record_count))
    print("=" * 78)


# ── 메인 ─────────────────────────────────────────────────────────────────────


def _reject_unknown_args(argv, bool_flags, value_flags):
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in value_flags:
            i += 2
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
    _reject_unknown_args(argv, bool_flags=("--dry-run",), value_flags=("--bld-type", "--raw-dir"))
    opts = {"bld_type": None, "raw_dir": None, "dry_run": "--dry-run" in argv}
    for flag, key in (("--bld-type", "bld_type"), ("--raw-dir", "raw_dir")):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise ValueError("{} 뒤에 값이 필요합니다.".format(flag))
            opts[key] = argv[i + 1]
    if opts["bld_type"] is not None and opts["bld_type"] not in BLD_TYPES:
        raise ValueError("--bld-type은 {} 중 하나여야 합니다: {!r}".format(BLD_TYPES, opts["bld_type"]))
    if opts["raw_dir"] is None:
        opts["raw_dir"] = os.path.join(PROJECT_ROOT, "data", "raw", RAW_SUBDIR)
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

    bld_types = (opts["bld_type"],) if opts["bld_type"] else BLD_TYPES

    all_records = []
    all_stats = []
    broken_total = 0
    for bld_type in bld_types:
        records, stats, broken = process_bld_type(opts["raw_dir"], bld_type)
        broken_total += broken
        all_records.extend(records)
        all_stats.append((bld_type, stats))

    if not all_records:
        print("[에러] raw가 비어 있습니다: {}".format(opts["raw_dir"]))
        print("       먼저 python scripts/collectors/collect_rone.py 를 실행하세요.")
        return 1

    try:
        assert_unique(all_records)
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1

    print_report(all_stats, broken_total, len(all_records))

    if opts["dry_run"]:
        print("")
        print("--dry-run 지정 — DB 적재를 건너뜁니다.")
        return 0

    try:
        base_url, key = get_supabase_config()
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1
    headers = {"apikey": key, "Authorization": "Bearer {}".format(key)}

    try:
        assert_table_exists(base_url, headers, "rent_stat")
        print("")
        print("적재 시작...", flush=True)
        sent = upsert_batch(base_url, headers, "rent_stat", all_records, "merge-duplicates")
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1

    print("")
    print("=" * 78)
    print("적재 완료: rent_stat {:,}행".format(sent))
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
