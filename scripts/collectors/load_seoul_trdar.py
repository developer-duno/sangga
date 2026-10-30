# -*- coding: utf-8 -*-
"""서울시 상권분석서비스 4종 raw → district_sales · district_pop_flow · district_pop_resident · district_pop_worker
적재 (결정 0045 PR② · **네 표 한 트랜잭션**).

무엇을 넣나
-----------
수집기(collect_seoul_trdar.py)가 쓴 분기 파일 `data/raw/seoul_trdar/<service>/<분기>_<받은날짜>.jsonl`(한 줄 =
{"quarter","fetched_at","row"})을 **공표값 그대로** 넣는다. 우리가 계산하는 값은 표지의 「값이 바뀐 분기」뿐이다.
  · 서비스마다 분기당 **가장 최근에 받은 날짜** 파일 하나(개업·폐업 적재기 pick 규칙과 같다 · `_pages/` 는 안 읽는다).
  · 분기 단위 **교체** — 그 분기 행을 지우고 새로 넣는다(개정판 대비).
  · ⛔ `--service` 인자는 없다 — 네 표를 **늘 함께** 넣는다. 하나라도 raw 가 없으면 관문 ⒢ 에서 멈춘다(분할 적재
    금지 — 신선도 표의 세 줄이 서로 다른 날의 자료를 말하지 않게 · 표지 네 줄이 한 번에 올라가게).

관문 (하나라도 걸리면 DB·파일 쓰기 0 · exit 1)
------------------------------------------------
  ⒜ 상권 코드 ⊂ 서울 상권 — `--dry-run` 은 커밋된 public/districts.geojson 으로(개업·폐업 적재기 seoul_district_ids
     재사용), 실적재는 적재 SQL 안에서 DB 가 district 표로 마지막에 본다(raise → 통째 롤백).
  ⒝ 분기 꼴 YYYYQ + 파일 이름 분기 = 줄의 quarter = 행의 STDR_YYQU_CD(섞임 0).
     칸 머리는 서비스마다 정해진 칸 그대로여야 한다(모르는 칸·빠진 칸이면 멈춘다 — 서울시가 칸을 바꾼 날).
  ⒞ 숫자 칸은 전부 **정수값**(157199.0 → 157199 · 소수 꼬리가 0 이 아니면 멈춘다 · 빈 값·null 도 멈춘다 —
     10-31 표본에 null 이 없었다. 걸리면 사람이 본다). 음수는 막지 않는다(공표값 그대로 — 근거 없는 거르기 금지).
  ⒟ (분기, 상권[, 업종]) 중복 0.
  ⒠ 분기 행수 범위 ROWS_PER_QUARTER(서비스마다 — 10-31 실측 근처).
  ⒢ 빠진 분기 0 — FIRST_QUARTER(서울시 「2021년 이후만 제공」)부터 **그 서비스의** 가장 최근 분기까지 전부
     (sales·flow 의 끝과 resident·worker 의 끝이 달라도 된다 — 각자 제 범위) · 그보다 옛 분기 · raw 없음도 ⒢.
  ⒣ 추정매출 업종 코드 꼴 ^CS\\d{6}$ · 분기 사이 업종 집합이 다르면 **경고만**.
  ⒤ (실적재 SQL 안) 추정매출 업종 코드가 개업·폐업 표(district_openclose)의 업종 집합 안 — 같은 서울시 100종인지
     DB 안에서 본다(어긋나면 raise → 네 표 모두 롤백).

값이 바뀐 분기 (표지 seoul_trdar_release.value_quarter)
--------------------------------------------------------
서비스마다 분기 오름차순으로 이웃 분기의 **상권별 숫자 칸 묶음**(추정매출은 그 상권 업종 행 전부)을 견주어 「하나라도
바뀐 상권이 있는 마지막 분기」(없으면 첫 분기). ⛔ **이웃 두 분기에 둘 다 있는 상권만** 견준다 — 한쪽에만 있는 상권
(분기마다 상권 수가 1,625~1,635 로 흔들린다)까지 세면 상주가 값을 안 바꾼 20242 가 기준 분기가 된다(10-31 실측). 상주·직장은 서울시가 4분기 코드에서만 값을 바꾼다(10-31 실측 —
상주 20234 · 직장 20244 의 값이 20262 까지 그대로). 추정매출·길단위인구는 분기마다 바뀌어 자연히 max 와 같다.

쓰는 법 (프로젝트 루트에서 · 수집 4종이 다 끝난 날 · 마이그레이션 2026-10-31a 를 넣은 직후)
-------------------------------------------------------------------------------------------
    python scripts/collectors/load_seoul_trdar.py --dry-run     # 관문 리포트 · DB·파일 쓰기 0
    python scripts/collectors/load_seoul_trdar.py               # 적재(한 트랜잭션) → post_load.py → --check
⚠️ 적재 **전** 디스크 판정 — (지금 사용량 + 약 +310MB + WAL 여유 1GB) 가 디스크의 85% 미만일 때만. 적재 앞뒤
   `pg_total_relation_size` 를 표 넷에 재서 PROGRESS 에 적는다.
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

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (SCRIPTS_DIR, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from load_seoul_openclose import copy_path_literal, seoul_district_ids  # noqa: E402

PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
DEFAULT_RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "seoul_trdar")
DEFAULT_STAGING_DIR = os.path.join(PROJECT_ROOT, "data", "staging", "seoul_trdar")

FIRST_QUARTER = "20211"     # 서울시 상권분석서비스 「2021년 이후만 제공」
SERVICES = ("sales", "flow", "resident", "worker")
TABLES = {
    "sales": "district_sales",
    "flow": "district_pop_flow",
    "resident": "district_pop_resident",
    "worker": "district_pop_worker",
}
TMP = {s: "tmp_" + s for s in SERVICES}
RELEASE_TABLE = "seoul_trdar_release"

_DAYS = ("MON", "TUES", "WED", "THUR", "FRI", "SAT", "SUN")
_TMZ = ("00_06", "06_11", "11_14", "14_17", "17_21", "21_24")
_AGE = ("10", "20", "30", "40", "50", "60_ABOVE")


def _sales_nums():
    out = ["THSMON_SELNG_AMT", "THSMON_SELNG_CO"]
    for unit in ("AMT", "CO"):
        if unit == "AMT":
            out += ["MDWK_SELNG_AMT", "WKEND_SELNG_AMT"]
        else:
            out += ["MDWK_SELNG_CO", "WKEND_SELNG_CO"]
        out += ["{}_SELNG_{}".format(d, unit) for d in _DAYS]
        out += ["TMZON_{}_SELNG_{}".format(t, unit) for t in _TMZ]
        out += ["ML_SELNG_{}".format(unit), "FML_SELNG_{}".format(unit)]
        out += ["AGRDE_{}_SELNG_{}".format(a, unit) for a in _AGE]
    return tuple(out)


# 숫자 칸(API 대문자 이름 · 표 칸 차례 그대로 — 표 칸 = 소문자)
NUM_COLS = {
    "sales": _sales_nums(),
    "flow": tuple(c + "_FLPOP_CO" for c in
                  ["TOT", "ML", "FML"] + ["AGRDE_" + a for a in _AGE]
                  + ["TMZON_" + t for t in _TMZ] + list(_DAYS)),
    "resident": tuple(c + "_REPOP_CO" for c in
                      ["TOT", "ML", "FML"] + ["AGRDE_" + a for a in _AGE]
                      + ["MAG_" + a for a in _AGE] + ["FAG_" + a for a in _AGE])
    + ("TOT_HSHLD_CO", "APT_HSHLD_CO", "NON_APT_HSHLD_CO"),
    "worker": tuple(c + "_WRC_POPLTN_CO" for c in
                    ["TOT", "ML", "FML"] + ["AGRDE_" + a for a in _AGE]
                    + ["MAG_" + a for a in _AGE] + ["FAG_" + a for a in _AGE]),
}
KEY_COLS = ("STDR_YYQU_CD", "TRDAR_SE_CD", "TRDAR_SE_CD_NM", "TRDAR_CD", "TRDAR_CD_NM")
INDUTY_COLS = ("SVC_INDUTY_CD", "SVC_INDUTY_CD_NM")


def raw_cols(service):
    """원본 행이 가져야 할 칸 전부(열쇠 5 + 업종 2(추정매출만) + 숫자)."""
    return KEY_COLS + (INDUTY_COLS if service == "sales" else ()) + NUM_COLS[service]


def csv_columns(service):
    """표에 넣는 칸(= staging CSV 차례). loaded_at 은 기본값(now())."""
    head = ("quarter", "district_id") + (("svc_induty_cd", "svc_induty_cd_nm") if service == "sales" else ())
    return head + tuple(c.lower() for c in NUM_COLS[service]) + ("source_nm",)


# ⒠ 분기 행수 범위(10-31 실측 — 추정매출 21,133~22,239 · 인구 셋 1,625~1,650)
ROWS_PER_QUARTER = {"sales": (18_000, 26_000), "flow": (1_600, 1_700),
                    "resident": (1_600, 1_700), "worker": (1_600, 1_700)}

RE_QUARTER = re.compile(r"^\d{4}[1-4]$")
RE_FILE = re.compile(r"^(\d{4}[1-4])_(\d{8})\.jsonl$")
RE_INDUTY = re.compile(r"^CS\d{6}$")


class GateError(ValueError):
    """관문에 걸림 — DB·파일에 아무것도 안 쓴다."""


# ── 순수 함수 ────────────────────────────────────────────────────────────────


def to_int(value, col, where):
    """⒞ 157199.0 · '12' → 정수. 소수 꼬리가 0 이 아니거나 빈 값·null·수 아님이면 멈춘다."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise GateError("⒞ {}: {} 가 비었습니다(null) — 10-31 표본엔 없던 꼴이라 사람이 본다".format(where, col))
    try:
        d = decimal.Decimal(str(value).strip())
    except (decimal.InvalidOperation, ValueError):
        raise GateError("⒞ {}: {} 가 수가 아닙니다: {!r}".format(where, col, value))
    if not d.is_finite() or d != d.to_integral_value():
        raise GateError("⒞ {}: {} 가 정수값이 아닙니다(소수 꼬리): {!r}".format(where, col, value))
    return int(d)


def normalize(service, raw, quarter, source_nm, where):
    """원본 행 dict → 표 한 줄 튜플(csv_columns 차례). 칸 머리·분기 섞임(⒝)·정수(⒞)를 여기서 본다."""
    want = raw_cols(service)
    if set(raw) != set(want):
        raise GateError("⒝ {}: 칸이 다릅니다(모르는 칸 {} · 빠진 칸 {}) — 서울시가 칸을 바꿨을 수 있습니다".format(
            where, sorted(set(raw) - set(want)), sorted(set(want) - set(raw))))
    q = str(raw["STDR_YYQU_CD"]).strip()
    if q != quarter:
        raise GateError("⒝ {}: 행의 분기 {!r} ≠ 파일 분기 {}".format(where, q, quarter))
    head = (q, str(raw["TRDAR_CD"]).strip())
    if service == "sales":
        head += (str(raw["SVC_INDUTY_CD"]).strip(), str(raw["SVC_INDUTY_CD_NM"]).strip() or None)
    return head + tuple(to_int(raw[c], c, where) for c in NUM_COLS[service]) + (source_nm,)


def row_key(service, row):
    """⒟ 열쇠 — (분기, 상권[, 업종])."""
    return row[:3] if service == "sales" else row[:2]


def row_nums(service, row):
    """숫자 칸만(값 비교용)."""
    start = 4 if service == "sales" else 2
    return row[start:-1]


def district_signature(service, rows):
    """{상권: 숫자 묶음} — 추정매출은 그 상권 (업종, 숫자) 전부를 차례대로 묶는다."""
    sig = {}
    for r in rows:
        d = r[1]
        if service == "sales":
            sig.setdefault(d, []).append((r[2],) + row_nums(service, r))
        else:
            sig[d] = row_nums(service, r)
    if service == "sales":
        sig = {d: tuple(sorted(v)) for d, v in sig.items()}
    return sig


def changed_districts(prev_sig, cur_sig):
    """이웃 두 분기에 **둘 다 있는** 상권 가운데 숫자가 하나라도 바뀐 상권 수.

    ⛔ 한쪽 분기에만 있는 상권(분기마다 상권 수가 1,625~1,635 로 흔들린다)은 세지 않는다 — 세면 상주가 값을 안 바꾼
    20242 에도 상권 2곳이 드나든 것만으로 '바뀜'이 되어 기준 분기가 20242 로 틀린다(10-31 실측 raw 로 확인 —
    tests/test_load_seoul_trdar.py 가 그 꼴을 시험한다).
    """
    return sum(1 for d in set(prev_sig) & set(cur_sig) if prev_sig[d] != cur_sig[d])


def value_quarter(changes, quarters):
    """changes = {분기: 앞 분기 대비 바뀐 상권 수}(첫 분기 제외). 바뀐 상권이 있는 마지막 분기 · 없으면 첫 분기."""
    qs = sorted(quarters)
    hit = [q for q in qs[1:] if changes.get(q, 0) > 0]
    return hit[-1] if hit else qs[0]


def quarter_problems(service, quarter, rows, known=None):
    """한 분기 관문 ⒜⒟⒠⒣(코드 꼴) — 문제 문장 목록(비면 통과)."""
    bad = []
    if not RE_QUARTER.match(quarter):
        bad.append("⒝ 분기 코드 꼴이 YYYYQ 가 아닙니다: {!r}".format(quarter))
    if known is not None:
        missing = sorted({r[1] for r in rows} - known)
        if missing:
            bad.append("⒜ 서울 상권에 없는 상권 코드 {}개(예 {})".format(len(missing), missing[:5]))
    keys = [row_key(service, r) for r in rows]
    if len(set(keys)) != len(keys):
        bad.append("⒟ (분기·상권{}) 중복 {:,}개".format("·업종" if service == "sales" else "",
                                                       len(keys) - len(set(keys))))
    lo, hi = ROWS_PER_QUARTER[service]
    if not lo <= len(rows) <= hi:
        bad.append("⒠ 행수 {:,} — {:,}~{:,} 밖".format(len(rows), lo, hi))
    if service == "sales":
        odd = sorted({r[2] for r in rows if not RE_INDUTY.match(r[2])})
        if odd:
            bad.append("⒣ 업종 코드 꼴(CS + 여섯 자리)이 아닌 것 {}개(예 {})".format(len(odd), odd[:5]))
    return bad


def missing_quarters(quarters, first=FIRST_QUARTER):
    """⒢ first ~ 가장 최근 분기 사이에 빠진 분기 + first 보다 옛 분기(둘 다 문제)."""
    qs = sorted(q for q in quarters if RE_QUARTER.match(q))
    if not qs:
        return [], []
    older = [q for q in qs if q < first]
    y, q = int(first[:4]), int(first[4])
    have, out = set(qs), []
    while True:
        cur = "{}{}".format(y, q)
        if cur > qs[-1]:
            return out, older
        if cur not in have:
            out.append(cur)
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)


def pick_sources(files):
    """[(분기, 받은날짜, 경로)] → {분기: 경로} — 분기마다 가장 최근 받은 날짜 하나."""
    best = {}
    for q, ymd, path in files:
        if q not in best or ymd > best[q][0]:
            best[q] = (ymd, path)
    return {q: p for q, (_, p) in best.items()}


def list_raw(raw_dir, service):
    """`<raw>/<service>/<분기>_<날짜>.jsonl` 만(`_pages/` 는 하위 폴더라 안 본다)."""
    d = os.path.join(raw_dir, service)
    out = []
    if os.path.isdir(d):
        for n in sorted(os.listdir(d)):
            m = RE_FILE.match(n)
            if m and os.path.isfile(os.path.join(d, n)):
                out.append((m.group(1), m.group(2), os.path.join(d, n)))
    return out


def read_quarter_file(service, path, quarter):
    """분기 파일 → 표 줄 튜플 목록. 줄의 quarter·행의 분기가 파일 이름 분기와 다르면 멈춘다(⒝)."""
    name = os.path.basename(path)
    out = []
    with io.open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            where = "{}/{}:{}".format(service, name, i)
            if str(obj.get("quarter")) != quarter:
                raise GateError("⒝ {}: 줄의 quarter {!r} ≠ 파일 분기 {}".format(where, obj.get("quarter"), quarter))
            out.append(normalize(service, obj["row"], quarter, name, where))
    return out


def scan_service(service, sources, known=None, writer=None):
    """한 서비스의 분기 파일을 옛 분기부터 읽어 관문·값 바뀐 분기를 셈한다(메모리 = 이웃 두 분기뿐).

    writer 가 있으면 읽은 줄을 바로 CSV 로 쓴다. 돌려줌 = 리포트 dict.
    """
    rep = {"rows": {}, "src": {}, "problems": {}, "changes": {}, "induty_sets": {}}
    prev_sig = None
    for q in sorted(sources):
        try:
            rows = read_quarter_file(service, sources[q], q)
        except GateError as e:
            rep["problems"].setdefault(q, []).append(str(e))
            prev_sig = None
            continue
        rep["rows"][q] = len(rows)
        rep["src"][q] = os.path.basename(sources[q])
        bad = quarter_problems(service, q, rows, known)
        if bad:
            rep["problems"][q] = bad
        sig = district_signature(service, rows)
        if prev_sig is not None:
            rep["changes"][q] = changed_districts(prev_sig, sig)
        prev_sig = sig
        if service == "sales":
            rep["induty_sets"][q] = frozenset(r[2] for r in rows)
        if writer is not None:
            for r in rows:
                writer.writerow(["" if v is None else v for v in r])
    qs = sorted(rep["rows"])
    rep["max_quarter"] = qs[-1] if qs else None
    rep["value_quarter"] = value_quarter(rep["changes"], qs) if qs else None
    gaps, older = missing_quarters(qs)
    if not sources:
        rep["problems"]["⒢"] = ["⒢ {} raw 가 없습니다 — 네 서비스를 함께 넣는다(분할 적재 금지)".format(service)]
    elif gaps or older:
        rep["problems"]["⒢"] = ["⒢ {} 빠진 분기 {} · {} 보다 옛 분기 {}".format(
            service, ", ".join(gaps) or "없음", FIRST_QUARTER, ", ".join(older) or "없음")]
    return rep


def induty_warnings(rep):
    """⒣ 분기 사이 업종 집합이 다르면 경고 문장(멈추지 않는다)."""
    sets = rep.get("induty_sets") or {}
    if len(set(sets.values())) <= 1:
        return []
    union = frozenset().union(*sets.values())
    return ["⒣ 경고: {} 분기 업종 {}종 (전체 {}종 중 빠짐 {})".format(
        q, len(s), len(union), sorted(union - s)[:5]) for q, s in sorted(sets.items()) if s != union]


# ── SQL ──────────────────────────────────────────────────────────────────────


def build_sql(csv_paths, quarters, expected, release):
    """적재 SQL — 네 표 한 트랜잭션. 관문은 전부 raise exception(psql 은 select 결과와 무관하게 0 으로 끝난다).

    csv_paths·quarters·expected·release 는 서비스 열쇠 dict — quarters[s] = 그 서비스의 분기 목록,
    expected[s] = 행 수, release[s] = (max_quarter, value_quarter).
    """
    parts = ["begin;", "set local statement_timeout = '1800s';", ""]
    for s in SERVICES:
        parts.append("create temp table {tmp} (like {tbl} including defaults) on commit drop;".format(
            tmp=TMP[s], tbl=TABLES[s]))
        parts.append("\\copy {tmp} ({cols}) from '{csv}' with (format csv, encoding 'UTF8')".format(
            tmp=TMP[s], cols=", ".join(csv_columns(s)), csv=copy_path_literal(csv_paths[s])))
    parts.append("")
    parts.append("-- ── 행수 대조 — CSV 가 잘려도 \\copy 는 에러 없이 거기까지만 넣는다 ──────────────")
    for s in SERVICES:
        parts.append("""do $$
declare cnt bigint;
begin
  select count(*) into cnt from {tmp};
  if cnt <> {n} then
    raise exception '{tmp}: 올린 행이 %개인데 원본에서 읽은 것은 {n}개입니다 — 네 표 모두 되돌립니다', cnt;
  end if;
end $$;""".format(tmp=TMP[s], n=expected[s]))
    parts.append("")
    parts.append("-- ── 관문 ⒜ 상권 코드가 district 에 있나 (DB 가 마지막으로 확인) ─────────────────")
    for s in SERVICES:
        parts.append("""do $$
declare bad bigint;
begin
  select count(distinct t.district_id) into bad from {tmp} t
   where not exists (select 1 from district d where d.district_id = t.district_id);
  if bad <> 0 then
    raise exception '관문 ⒜ {tmp}: district 에 없는 상권 코드 %개 — 네 표 모두 되돌립니다', bad;
  end if;
end $$;""".format(tmp=TMP[s]))
    parts.append("")
    parts.append("-- ── 관문 ⒤ 추정매출 업종이 개업·폐업과 같은 서울시 100종 안인가 ──────────────────")
    parts.append("""do $$
declare bad bigint;
begin
  select count(*) into bad from tmp_sales
   where svc_induty_cd not in (select distinct o.svc_induty_cd from district_openclose o);
  if bad <> 0 then
    raise exception '관문 ⒤ 개업·폐업(district_openclose)에 없는 업종 코드 행이 %개 — 네 표 모두 되돌립니다', bad;
  end if;
end $$;""")
    parts.append("")
    parts.append("-- 분기 단위 교체 — 그 분기 행을 지우고 새로(개정판 대비). 위 관문에 걸리면 이 삭제까지 되돌아간다.")
    for s in SERVICES:
        qs = ", ".join("'{}'".format(q) for q in sorted(quarters[s]))
        cols = ", ".join(csv_columns(s))
        parts.append("delete from {tbl} where quarter in ({qs});".format(tbl=TABLES[s], qs=qs))
        parts.append("insert into {tbl} ({cols}) select {cols} from {tmp};".format(
            tbl=TABLES[s], cols=cols, tmp=TMP[s]))
    parts.append("")
    parts.append("-- 표지 네 줄 — 가장 최근 분기와 값이 마지막으로 바뀐 분기(적재기가 셈한 것).")
    values = ",\n  ".join("('{}', '{}', '{}', now())".format(TABLES[s], release[s][0], release[s][1])
                          for s in SERVICES)
    parts.append("insert into {rel} (tbl, max_quarter, value_quarter, loaded_at) values\n  {v}\n"
                 "on conflict (tbl) do update set max_quarter = excluded.max_quarter, "
                 "value_quarter = excluded.value_quarter, loaded_at = excluded.loaded_at;".format(
                     rel=RELEASE_TABLE, v=values))
    parts.append("")
    for s in SERVICES:
        qs = ", ".join("'{}'".format(q) for q in sorted(quarters[s]))
        parts.append("""do $$
declare cnt bigint;
begin
  select count(*) into cnt from {tbl} where quarter in ({qs});
  if cnt <> {n} then
    raise exception '{tbl}: 표에 든 행이 %개인데 {n}개여야 합니다 — 네 표 모두 되돌립니다', cnt;
  end if;
end $$;""".format(tbl=TABLES[s], qs=qs, n=expected[s]))
    parts.append("")
    parts.append("select tbl as \"표\", max_quarter as \"최근 분기\", value_quarter as \"값 바뀐 분기\" "
                 "from {} order by tbl;".format(RELEASE_TABLE))
    parts.append("")
    parts.append("commit;")
    return "\n".join(parts) + "\n"


# ── 메인 ─────────────────────────────────────────────────────────────────────


def main(argv=None):
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="서울 상권 4종 raw → district_sales·district_pop_* 적재(한 트랜잭션)",
                                allow_abbrev=False)
    p.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    p.add_argument("--staging-dir", default=DEFAULT_STAGING_DIR)
    p.add_argument("--dry-run", action="store_true", help="관문 리포트만 — DB·파일 쓰기 0")
    a = p.parse_args(argv)

    known = seoul_district_ids()
    csv_paths = {s: os.path.join(a.staging_dir, "{}.csv".format(TABLES[s])) for s in SERVICES}
    handles, reports = {}, {}
    try:
        for s in SERVICES:
            sources = pick_sources(list_raw(a.raw_dir, s))
            writer = None
            if not a.dry_run and sources:
                os.makedirs(a.staging_dir, exist_ok=True)
                handles[s] = io.open(csv_paths[s] + ".part", "w", encoding="utf-8", newline="")
                writer = csv.writer(handles[s], lineterminator="\n")
            reports[s] = scan_service(s, sources, known, writer)
    except (ValueError, OSError) as e:
        print("실패: {}".format(e), file=sys.stderr)
        return _drop_parts(handles, csv_paths, 1)
    for h in handles.values():
        h.close()

    print("=" * 78)
    print("서울 상권 4종 → {} {}".format(" · ".join(TABLES[s] for s in SERVICES), "(dry-run)" if a.dry_run else ""))
    print("=" * 78)
    print("  {:<9} {:>6} {:>9}  {:<8} {:<10} {}".format("서비스", "분기", "행", "최근분기", "값바뀐분기", "그 분기에 바뀐 상권"))
    for s in SERVICES:
        r = reports[s]
        vq = r["value_quarter"]
        print("  {:<9} {:>6} {:>9,}  {:<8} {:<10} {}".format(
            s, len(r["rows"]), sum(r["rows"].values()), r["max_quarter"] or "-", vq or "-",
            r["changes"].get(vq, "-") if vq else "-"))
    print("  ⓘ 「바뀐 상권」은 이웃 두 분기에 둘 다 있는 상권 가운데 숫자가 하나라도 바뀐 상권이다"
          "(한쪽에만 있는 상권은 안 센다).")
    if known is None:
        print("  ⓘ public/districts.geojson 이 없어 관문 ⒜ 미리보기를 건너뜁니다 — 적재 SQL 이 DB 에서 본다.")
    for w in induty_warnings(reports["sales"]):
        print("  " + w)

    problems = [(s, q, m) for s in SERVICES for q, ms in reports[s]["problems"].items() for m in ms]
    if problems:
        print()
        print("관문에 걸렸습니다 — DB·파일에는 아무것도 쓰지 않았습니다:", file=sys.stderr)
        for s, q, m in problems:
            print("  {} {}  {}".format(s, q, m), file=sys.stderr)
        return _drop_parts(handles, csv_paths, 1)
    print("  관문 통과 (⒜{} · ⒝ · ⒞ · ⒟ · ⒠ · ⒢ · ⒣ — ⒤ 는 적재 SQL 안에서)".format(
        "" if known is not None else " DB 에서"))

    if a.dry_run:
        print()
        print("--dry-run — DB·파일에 아무것도 쓰지 않았습니다.")
        return 0

    for s in SERVICES:
        os.replace(csv_paths[s] + ".part", csv_paths[s])
    sql = build_sql(csv_paths, {s: list(reports[s]["rows"]) for s in SERVICES},
                    {s: sum(reports[s]["rows"].values()) for s in SERVICES},
                    {s: (reports[s]["max_quarter"], reports[s]["value_quarter"]) for s in SERVICES})

    import dbx  # noqa: PLC0415  (dry-run 은 DB 설정 없이도 돌아야 한다)
    rc = dbx.run_sql(sql)
    if rc != 0:
        print("적재 실패 (psql 종료코드 {}). 한 트랜잭션이라 네 표 모두 아무것도 안 들어갔습니다.".format(rc),
              file=sys.stderr)
        return rc
    print()
    print("  적재 완료 ({}).".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    print("  다음: python scripts/post_load.py   그리고   python scripts/post_load.py --check")
    print("  디스크: 적재 앞뒤 pg_total_relation_size 를 표 넷에 재서 docs/PROGRESS.md 에 적는다(사람 몫).")
    return 0


def _drop_parts(handles, csv_paths, rc):
    """관문에 걸리면 쓰던 staging 조각(.part)을 치운다 — 걸린 판의 CSV 가 남아 다음 사람을 속이지 않게."""
    for s, h in handles.items():
        try:
            h.close()
            os.remove(csv_paths[s] + ".part")
        except OSError:
            pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
