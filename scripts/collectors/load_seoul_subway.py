# -*- coding: utf-8 -*-
"""서울 지하철 역사마스터 + 월별 승하차 raw → subway_station · subway_ridership_m 적재 (결정 0045 PR⑥ · 한 트랜잭션).

무엇을 넣나
-----------
수집기(collect_seoul_subway.py)가 쓴 raw 를 **공표값 그대로** 넣는다:
  · 역사마스터(OA-21232 `subwayStationMaster`) — `data/raw/seoul_subway/master/<YYYYMMDD>.json`(이름이 가장 늦은 파일 하나)
    → subway_station(역 한 줄 · 수도권 전체 784역 · 좌표 WGS84 그대로) — **upsert** · 마스터에서 사라진 역은 승하차 참조가
    없을 때만 지운다(참조가 있으면 raise → 통째 롤백 · 사람이 본다).
  · 월별 승하차(OA-12252 `CardSubwayTime`) — `data/raw/seoul_subway/ridership/<YYYYMM>_<YYYYMMDD>.json`(달마다 받은 날이
    가장 늦은 파일 하나) → subway_ridership_m(달 · 원문 호선 · 원문 역 한 줄 · 승차·하차 24시간대 48칸 + 합 둘) — **달 단위 교체**.
  ⓘ 적재기는 수집기 꼴 이름만 읽는다(메인이 따로 받은 파일은 이 꼴 이름으로 옮겨서 넣는다).
  ⓘ 봉투가 「자료 없음」인 파일(`code` 가 INFO-000 이 아니거나 `total` 0 · 행 0)은 그 달 자료 없음으로 건너뛰고 리포트에 적는다.

잇기 — 승하차 (역, 호선) → 마스터 역
----------------------------------
  ① 역 짝표 `scripts/seeds/subway_station_map.csv` 에 (원문 역, 원문 호선)이 있으면: map = 씨앗의 (마스터 역, 마스터 호선)으로 ·
     skip = 그 행을 버리고 센다(마스터에 좌표가 없는 새 역 둘 · 한 달 노이즈 하나).
  ② 아니면 호선 짝표 `scripts/seeds/subway_line_map.csv` 로 호선 표기만 바꾼다(9호선2~3단계 → 9호선(연장) 등 셋).
  ③ (정규화한 역 이름, 호선)으로 마스터 station_id. 정규화 = 공백 전부 제거 → 괄호와 그 안 제거(「잠실(송파구청)」 = 「잠실」).
  ⛔ 표의 기본키는 **원문 열쇠 (달, 원문 호선, 원문 역)** 다 — 짝표 뒤 같은 마스터 역으로 원문 두 줄이 모일 수 있다(창동 4호선 +
     창동 경원선 · 계양·검암·김포공항의 경의선 라벨 줄 + 공항철도 1호선 줄 — 둘 다 진짜 자료라 합치지도 버리지도 않는다 ·
     함수가 묶음으로 더한다 · 2026-11-02 메인 결정 ⑥-1).
  칸 `line_nm`(그 행이 붙은 호선 — 화면의 호선 목록에 쓴다) = 역 짝표 map 이면 원문 호선에 호선 짝표만 · 아니면 호선 짝표 뒤 글.

역 묶음 — 같은 역사(환승역)
--------------------------
서울시는 환승역의 승하차를 **관리 호선 한 줄에 몰아 센다**(충무로 3호선 = 매달 승차 100~190 · 하차 0 / 4호선 = 승차 약 95만).
그래서 호선마다 줄을 세우면 「충무로 3호선 하루 5명」 같은 거짓 숫자가 선다 → 역을 **묶음(group_id)** 으로 합친다:
정규화한 이름이 같고 **서로 600m 안**(하버사인 · 사슬로 이어지면 한 묶음)인 역들. 600m 넘어 갈리는 같은 이름(양평 5호선/중앙선
53.6km · 운정 3.6km · 신촌 2호선/경의중앙선 715m)은 다른 역이다(👤 2026-11-02 Q1 「가」). 묶음 번호는 1부터 · 묶음 안 가장
작은 station_id 차례.

관문 (하나라도 걸리면 DB 는 손도 안 댄다 · exit 1)
--------------------------------------------------
  ⒜ 마스터 행 700~900 · BLDN_ID 중복 0 · 빈 칸 0 · LAT 33~39 · LOT 124~132(WGS84 범위 밖이면 멈춤) · (정규화 이름, 호선) 중복 0
  ⒝ 달마다 칸 머리 = 정해진 51칸(USE_MM·호선·역·48칸·JOB_YMD) · USE_MM = 파일의 달 · 중복 뺀 행 550~700 ·
     같은 (원문 호선, 원문 역)이 두 번이면 **51칸이 완전히 같을 때만** 하나로(202603·202607 실측) · 다르면 멈춤
  ⒞ 승하차 호선 표기 ⊂ 마스터 ROUTE 전부 ∪ 호선 짝표 ride_line (새 표기 = 짝표 손볼 신호)
  ⒟ 달마다 잇기 — 조인률(붙은 행 ÷ (중복 뺀 행 − skip 행)) 90% 이상(결정 0045 원문) **그리고** 안 붙은 행이 전부 skip 목록이고
     10행 이하(짝표 밖 미매칭 0) · 역 짝표 map 의 마스터 역이 마스터에 없어도 여기서 걸린다
  ⒠ 달마다 승차 합 ≥ 1억 · 하차 합 ≥ 1억
  ⒡ 48칸 전부 0 이상 정수값(892.0 → 892 · 소수 꼬리·빈 값·null·음수는 멈춤) · JOB_YMD 는 YYYYMMDD 날짜 또는 빈 값
  ⒢ 빠진 달 보고(202101 ~ 가장 최근 달 사이 raw 없는 달 — 멈추지 않는다 · 리포트에)
  ⒣ (DB 안 · 실적재 SQL) 승하차 station_id 가 전부 subway_station 에 있다(FK 가 지키되 raise 글로도)

쓰는 법 (프로젝트 루트에서)
---------------------------
    python scripts/collectors/load_seoul_subway.py --dry-run          # 관문 리포트 + 묶음·잇기 표 (DB·파일 쓰기 0)
    python scripts/collectors/load_seoul_subway.py                    # 실적재 (한 트랜잭션) → post_load.py · --check
    python scripts/collectors/load_seoul_subway.py --months 202609    # 일부 달만 교체(마스터는 늘 upsert)
  ⛔ 운영 순서: 마이그 2026-11-02a(DB 먼저) → 머지 → 수집 → 이 적재 → post_load.py · post_load.py --check → backup_raw.py.
"""

import argparse
import collections
import csv
import datetime
import decimal
import io
import json
import math
import os
import re
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
DEFAULT_RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "seoul_subway")
DEFAULT_STAGING_DIR = os.path.join(PROJECT_ROOT, "data", "staging", "seoul_subway")
LINE_SEED = os.path.join(SCRIPTS_DIR, "seeds", "subway_line_map.csv")
STATION_SEED = os.path.join(SCRIPTS_DIR, "seeds", "subway_station_map.csv")

FIRST_MONTH = "202101"          # 서울시 「2021년 이후」
MASTER_ROWS = (700, 900)        # 2026-11-02 실측 784
LAT_RANGE = (33.0, 39.0)
LNG_RANGE = (124.0, 132.0)
ROWS_PER_MONTH = (550, 700)     # 2021-01~2026-09 실측 604~623(중복 뺀 뒤)
MIN_JOIN_PCT = 90.0             # 결정 0045 원문
MAX_SKIP_ROWS = 10
MIN_MONTH_SUM = 100_000_000     # 실측 승차합 1.4억(202101)~2.3억
GROUP_DIST_M = 600.0            # 같은 이름 역 묶음 거리(👤 Q1)
EARTH_R = 6371008.8
EXAMPLES = 5

CODE_OK = "INFO-000"
HOURS = tuple(range(4, 24)) + (0, 1, 2, 3)          # 서울시 칸 차례 그대로(4시 → 23시 → 0시 → 3시)
ON_RAW = tuple("HR_{}_GET_ON_NOPE".format(h) for h in HOURS)
OFF_RAW = tuple("HR_{}_GET_OFF_NOPE".format(h) for h in HOURS)
RAW_COLS = ("USE_MM", "SBWY_ROUT_LN_NM", "STTN") + tuple(x for pair in zip(ON_RAW, OFF_RAW) for x in pair) + ("JOB_YMD",)
ON_COLS = tuple("on_h{:02d}".format(h) for h in HOURS)
OFF_COLS = tuple("off_h{:02d}".format(h) for h in HOURS)
RIDE_COLUMNS = (("use_mm", "station_id", "ride_line_nm", "ride_sttn_nm", "line_nm", "on_sum", "off_sum")
                + ON_COLS + OFF_COLS + ("job_ymd",))
STATION_COLUMNS = ("station_id", "station_nm", "name_norm", "line_nm", "group_id", "lat", "lng")

RE_MASTER_FILE = re.compile(r"^(\d{8})(?:_(\d+))?\.json$")
RE_RIDE_FILE = re.compile(r"^(\d{4}(?:0[1-9]|1[0-2]))_(\d{8})(?:_(\d+))?\.json$")
RE_MONTH = re.compile(r"^\d{4}(0[1-9]|1[0-2])$")
RE_YMD = re.compile(r"^\d{8}$")


class GateError(ValueError):
    """관문에 걸림 — DB 에 아무것도 안 쓴다."""


# ── 순수 함수 ────────────────────────────────────────────────────────────────


def norm_name(s):
    """역 이름 정규화 — 공백 전부 제거 → 괄호와 그 안 제거. 「잠실(송파구청)」 → 「잠실」."""
    s = re.sub(r"\s+", "", str(s or ""))
    return re.sub(r"\(.*?\)", "", s)


def haversine_m(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def to_count(value, col, where):
    """⒡ 892.0 · '12' · 3 → 정수. 소수 꼬리·빈 값·null·음수·수 아님이면 멈춘다."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise GateError("⒡ {}: {} 가 비었습니다(null)".format(where, col))
    try:
        d = decimal.Decimal(str(value).strip())
    except (decimal.InvalidOperation, ValueError):
        raise GateError("⒡ {}: {} 가 수가 아닙니다: {!r}".format(where, col, value))
    if not d.is_finite() or d != d.to_integral_value():
        raise GateError("⒡ {}: {} 가 정수값이 아닙니다(소수 꼬리): {!r}".format(where, col, value))
    if d < 0:
        raise GateError("⒡ {}: {} 가 음수입니다: {!r}".format(where, col, value))
    return int(d)


def to_job_date(value, where):
    """⒡ JOB_YMD '20261003' → '2026-10-03'. 빈 값은 None. 꼴이 다르거나 없는 날이면 멈춘다."""
    if value is None or not str(value).strip():
        return None
    s = str(value).strip()
    if not RE_YMD.match(s):
        raise GateError("⒡ {}: JOB_YMD 꼴이 YYYYMMDD 가 아닙니다: {!r}".format(where, value))
    try:
        return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:])).isoformat()
    except ValueError:
        raise GateError("⒡ {}: JOB_YMD 가 없는 날입니다: {!r}".format(where, value))


def read_line_seed(path=LINE_SEED):
    """호선 짝표 → {승하차 호선: 마스터 호선}. 머리·빈 칸·중복이 틀리면 멈춘다."""
    with io.open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    if not rows or rows[0] != ["ride_line", "master_line", "note"]:
        raise GateError("호선 짝표 머리줄이 ride_line,master_line,note 가 아닙니다: {}".format(rows[:1]))
    out = {}
    for i, r in enumerate(rows[1:], 2):
        if len(r) != 3 or not r[0].strip() or not r[1].strip():
            raise GateError("호선 짝표 {}번째 줄 모양이 틀렸습니다: {!r}".format(i, r))
        if r[0] in out:
            raise GateError("호선 짝표에 같은 승하차 호선이 두 번: {!r}".format(r[0]))
        out[r[0]] = r[1]
    return out


def read_station_seed(path=STATION_SEED):
    """역 짝표 → {(원문 역, 원문 호선): ('map', 마스터 역, 마스터 호선) | ('skip', None, None)}."""
    with io.open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    want = ["ride_sttn", "ride_line", "action", "master_sttn", "master_line", "note"]
    if not rows or rows[0] != want:
        raise GateError("역 짝표 머리줄이 {} 가 아닙니다: {}".format(",".join(want), rows[:1]))
    out = {}
    for i, r in enumerate(rows[1:], 2):
        ok = len(r) == 6 and r[0].strip() and r[1].strip() and r[2] in ("map", "skip")
        if ok and r[2] == "map":
            ok = bool(r[3].strip() and r[4].strip())
        if ok and r[2] == "skip":
            ok = not r[3].strip() and not r[4].strip()
        if not ok:
            raise GateError("역 짝표 {}번째 줄 모양이 틀렸습니다: {!r}".format(i, r))
        k = (r[0], r[1])
        if k in out:
            raise GateError("역 짝표에 같은 (역, 호선)이 두 번: {!r}".format(k))
        out[k] = (r[2], r[3] or None, r[4] or None)
    return out


def master_problems(rows):
    """⒜ — 마스터 행 목록(dict) → 문제 문장 목록."""
    bad = []
    lo, hi = MASTER_ROWS
    if not lo <= len(rows) <= hi:
        bad.append("⒜ 마스터 행 {:,} — {}~{} 밖".format(len(rows), lo, hi))
    need = ("BLDN_ID", "BLDN_NM", "ROUTE", "LAT", "LOT")
    blank = [r for r in rows if any(not str(r.get(k) or "").strip() for k in need)]
    if blank:
        bad.append("⒜ 빈 칸이 있는 마스터 행 {}개(예 {})".format(len(blank), blank[:2]))
        return bad
    ids = collections.Counter(str(r["BLDN_ID"]).strip() for r in rows)
    dup = sorted(k for k, n in ids.items() if n > 1)
    if dup:
        bad.append("⒜ BLDN_ID 중복 {}개(예 {})".format(len(dup), dup[:EXAMPLES]))
    out_range = []
    for r in rows:
        try:
            lat, lng = float(r["LAT"]), float(r["LOT"])
        except (TypeError, ValueError):
            out_range.append(r["BLDN_ID"])
            continue
        if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]):
            out_range.append(r["BLDN_ID"])
    if out_range:
        bad.append("⒜ 좌표가 WGS84 대한민국 범위(LAT {}~{} · LOT {}~{}) 밖인 역 {}개(예 {})".format(
            LAT_RANGE[0], LAT_RANGE[1], LNG_RANGE[0], LNG_RANGE[1], len(out_range), out_range[:EXAMPLES]))
    keys = collections.Counter((norm_name(r["BLDN_NM"]), str(r["ROUTE"]).strip()) for r in rows)
    kdup = sorted(k for k, n in keys.items() if n > 1)
    if kdup:
        bad.append("⒜ (정규화 이름, 호선) 중복 {}개(예 {}) — 잇기 열쇠가 둘로 갈린다".format(len(kdup), kdup[:EXAMPLES]))
    return bad


def build_stations(rows):
    """마스터 행 → 역 dict 목록(station_id 차례 · group_id 포함)과 600m 넘어 갈린 이름 목록.

    묶음 = 같은 정규화 이름 안에서 서로 600m 안인 역을 union-find 로 잇는다(사슬도 한 묶음).
    """
    st = []
    for r in rows:
        st.append({"station_id": str(r["BLDN_ID"]).strip(), "station_nm": str(r["BLDN_NM"]).strip(),
                   "name_norm": norm_name(r["BLDN_NM"]), "line_nm": str(r["ROUTE"]).strip(),
                   "lat": float(r["LAT"]), "lng": float(r["LOT"])})
    st.sort(key=lambda s: s["station_id"])
    parent = list(range(len(st)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_name = collections.defaultdict(list)
    for i, s in enumerate(st):
        by_name[s["name_norm"]].append(i)
    for idx in by_name.values():
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                i, j = idx[a], idx[b]
                if haversine_m(st[i]["lat"], st[i]["lng"], st[j]["lat"], st[j]["lng"]) <= GROUP_DIST_M:
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[max(ri, rj)] = min(ri, rj)
    gid, roots = {}, {}
    for i in range(len(st)):              # station_id 차례 — 묶음 번호도 그 차례(1부터)
        r = find(i)
        if r not in roots:
            roots[r] = len(roots) + 1
        gid[i] = roots[r]
    for i, s in enumerate(st):
        s["group_id"] = gid[i]
    split = sorted(n for n, idx in by_name.items() if len({gid[i] for i in idx}) > 1)
    return st, split


def resolve(sttn, line, line_map, station_map, master_key):
    """승하차 (원문 역, 원문 호선) → (station_id | None, 붙은 호선 | None, 'map'|'skip'|'plain').

    station_id 가 None 이고 갈래가 'skip' 이면 씨앗이 뺀 행 · 'plain'/'map' 이면 미매칭.
    """
    hit = station_map.get((sttn, line))
    if hit is not None:
        action, m_st, m_ln = hit
        if action == "skip":
            return None, None, "skip"
        return master_key.get((norm_name(m_st), m_ln)), line_map.get(line, line), "map"
    ln = line_map.get(line, line)
    return master_key.get((norm_name(sttn), ln)), ln, "plain"


def parse_month(ym, payload, where):
    """한 달 봉투 → (중복 뺀 원문 행 목록, 받은 행 수). ⒝·⒡ 를 본다. 「자료 없음」 봉투는 None."""
    rows = payload.get("rows") if isinstance(payload, dict) else None
    code = payload.get("code") if isinstance(payload, dict) else None
    if (code is not None and code != CODE_OK) or not payload.get("total") or not rows:
        return None
    if not isinstance(rows, list):
        raise GateError("⒝ {}: rows 가 목록이 아닙니다".format(where))
    want = set(RAW_COLS)
    seen = collections.OrderedDict()
    for i, r in enumerate(rows, 1):
        at = "{}:{}".format(where, i)
        if not isinstance(r, dict) or set(r) != want:
            got = set(r) if isinstance(r, dict) else set()
            raise GateError("⒝ {}: 칸이 다릅니다(모르는 칸 {} · 빠진 칸 {}) — 서울시가 칸을 바꿨을 수 있습니다".format(
                at, sorted(got - want), sorted(want - got)))
        if str(r["USE_MM"]).strip() != ym:
            raise GateError("⒝ {}: USE_MM {!r} ≠ 파일의 달 {}".format(at, r["USE_MM"], ym))
        k = (str(r["SBWY_ROUT_LN_NM"]).strip(), str(r["STTN"]).strip())
        if not k[0] or not k[1]:
            raise GateError("⒝ {}: 호선·역 이름이 비었습니다".format(at))
        if k in seen:
            if seen[k] != r:
                raise GateError("⒝ {}: 같은 (호선, 역) {} 이 두 번인데 값이 다릅니다 — 서울시 자료를 사람이 본다".format(at, k))
            continue
        seen[k] = r
    return list(seen.values()), len(rows)


def month_rows(ym, raw_rows, line_map, station_map, master_key, where):
    """원문 행 → (표 줄 튜플 목록(RIDE_COLUMNS 차례), 셈 dict). ⒡ 정수 · 잇기 갈래를 센다."""
    out = []
    st = {"skip": 0, "unmatched": [], "joined": 0, "plain": 0, "on": 0, "off": 0, "zero_on": [], "zero_off": [], "skip_keys": []}
    for r in raw_rows:
        line, sttn = str(r["SBWY_ROUT_LN_NM"]).strip(), str(r["STTN"]).strip()
        at = "{} {}·{}".format(where, sttn, line)
        on = [to_count(r[c], c, at) for c in ON_RAW]
        off = [to_count(r[c], c, at) for c in OFF_RAW]
        job = to_job_date(r["JOB_YMD"], at)
        st["on"] += sum(on)
        st["off"] += sum(off)
        if sum(on) == 0:
            st["zero_on"].append((line, sttn))
        if sum(off) == 0:
            st["zero_off"].append((line, sttn))
        sid, ln, how = resolve(sttn, line, line_map, station_map, master_key)
        if how == "skip":
            st["skip"] += 1
            st["skip_keys"].append((sttn, line))
            continue
        if sid is None:
            st["unmatched"].append((sttn, line))
            continue
        st["joined"] += 1
        if how == "plain":
            st["plain"] += 1
        out.append((ym, sid, line, sttn, ln, sum(on), sum(off)) + tuple(on) + tuple(off) + (job,))
    return out, st


def month_problems(n_dedup, stats):
    """⒝(행 수)·⒟·⒠ — 한 달 문제 문장 목록과 조인률(%)."""
    bad = []
    lo, hi = ROWS_PER_MONTH
    if not lo <= n_dedup <= hi:
        bad.append("⒝ 중복 뺀 행 {:,} — {}~{} 밖".format(n_dedup, lo, hi))
    if stats["unmatched"]:
        bad.append("⒟ 짝표 밖 미매칭 {}행 {} — scripts/seeds/subway_station_map.csv 에 map/skip 을 사람이 적은 뒤 다시".format(
            len(stats["unmatched"]), stats["unmatched"][:EXAMPLES]))
    if stats["skip"] > MAX_SKIP_ROWS:
        bad.append("⒟ skip 행 {} — {}행 넘음".format(stats["skip"], MAX_SKIP_ROWS))
    denom = n_dedup - stats["skip"]
    rate = 100.0 * stats["joined"] / denom if denom > 0 else 0.0
    if rate < MIN_JOIN_PCT:
        bad.append("⒟ 조인률 {:.2f}% — {}% 미만".format(rate, MIN_JOIN_PCT))
    if stats["on"] < MIN_MONTH_SUM or stats["off"] < MIN_MONTH_SUM:
        bad.append("⒠ 승차 합 {:,} · 하차 합 {:,} — {:,} 미만".format(stats["on"], stats["off"], MIN_MONTH_SUM))
    return bad, rate


def ride_line_problems(lines, master_lines, line_map):
    """⒞ 승하차 호선 표기 ⊂ 마스터 ROUTE ∪ 호선 짝표 ride_line."""
    odd = sorted(set(lines) - set(master_lines) - set(line_map))
    if odd:
        return ["⒞ 마스터·호선 짝표에 없는 호선 표기 {}개 {} — scripts/seeds/subway_line_map.csv 를 손볼 신호".format(
            len(odd), odd)]
    return []


def month_seq(first, last):
    out, y, m = [], int(first[:4]), int(first[4:])
    while "{:04d}{:02d}".format(y, m) <= last:
        out.append("{:04d}{:02d}".format(y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def missing_months(months, first=FIRST_MONTH):
    """⒢ first ~ 가장 최근 달 사이에 raw 가 없는 달(멈추지 않는다)."""
    if not months:
        return []
    have = set(months)
    return [m for m in month_seq(first, max(months)) if m not in have]


# ── 파일 고르기 ──────────────────────────────────────────────────────────────


def pick_master(raw_dir):
    """`master/<YYYYMMDD>[_n].json` 가운데 (날짜, 꼬리) 가 가장 늦은 것. 없으면 None."""
    d = os.path.join(raw_dir, "master")
    best = None
    if os.path.isdir(d):
        for n in os.listdir(d):
            m = RE_MASTER_FILE.match(n)
            if m:
                k = (m.group(1), int(m.group(2) or 0))
                if best is None or k > best[0]:
                    best = (k, os.path.join(d, n))
    return best[1] if best else None


def pick_months(raw_dir):
    """`ridership/<YYYYMM>_<YYYYMMDD>[_n].json` → {달: 경로} — 달마다 받은 날(·꼬리)이 가장 늦은 것."""
    d = os.path.join(raw_dir, "ridership")
    best = {}
    if os.path.isdir(d):
        for n in os.listdir(d):
            m = RE_RIDE_FILE.match(n)
            if m:
                k = (m.group(2), int(m.group(3) or 0))
                if m.group(1) not in best or k > best[m.group(1)][0]:
                    best[m.group(1)] = (k, os.path.join(d, n))
    return {ym: p for ym, (_, p) in best.items()}


def load_json(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


# ── 한 번 훑기 ───────────────────────────────────────────────────────────────


def scan(raw_dir, months=None, line_map=None, station_map=None):
    """raw 를 훑어 관문·리포트를 셈한다. → dict(stations, split, months{달: 셈}, rows{달: 표 줄}, problems, empty, gaps)."""
    line_map = read_line_seed() if line_map is None else line_map
    station_map = read_station_seed() if station_map is None else station_map
    rep = {"problems": [], "months": collections.OrderedDict(), "rows": {}, "empty": [], "gaps": []}
    mpath = pick_master(raw_dir)
    if not mpath:
        raise GateError("⒜ 역사마스터 raw 가 없습니다 — {}/master/<YYYYMMDD>.json".format(raw_dir))
    payload = load_json(mpath)
    mrows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(mrows, list):
        raise GateError("⒜ 마스터 파일 모양이 다릅니다(rows 목록 없음): {}".format(mpath))
    rep["master_file"] = os.path.basename(mpath)
    bad = master_problems(mrows)
    if bad:
        rep["problems"] += bad
        return rep
    stations, split = build_stations(mrows)
    rep["stations"], rep["split"] = stations, split
    master_key = {(s["name_norm"], s["line_nm"]): s["station_id"] for s in stations}
    master_lines = {s["line_nm"] for s in stations}
    for k, (action, m_st, m_ln) in sorted(station_map.items()):
        if action == "map" and (norm_name(m_st), m_ln) not in master_key:
            rep["problems"].append("⒟ 역 짝표 map {} → ({}, {}) 가 마스터에 없습니다".format(k, m_st, m_ln))

    files = pick_months(raw_dir)
    want = sorted(files) if not months else sorted(m for m in files if m in set(months))
    if months:
        lost = sorted(set(months) - set(files))
        if lost:
            rep["problems"].append("--months 에 준 달 {} 의 raw 가 없습니다".format(lost))
    lines_seen = set()
    for ym in want:
        where = os.path.basename(files[ym])
        parsed = parse_month(ym, load_json(files[ym]), where)
        if parsed is None:
            rep["empty"].append(ym)
            continue
        raw_rows, n_raw = parsed
        lines_seen |= {str(r["SBWY_ROUT_LN_NM"]).strip() for r in raw_rows}
        rows, st = month_rows(ym, raw_rows, line_map, station_map, master_key, where)
        bad, rate = month_problems(len(raw_rows), st)
        st.update({"file": where, "raw": n_raw, "dedup": len(raw_rows), "rate": rate,
                   "plain_rate": 100.0 * st["plain"] / len(raw_rows)})
        rep["months"][ym] = st
        rep["rows"][ym] = rows
        rep["problems"] += ["{} {}".format(ym, b) for b in bad]
    rep["problems"] += ride_line_problems(lines_seen, master_lines, line_map)
    have = [m for m in files if m not in rep["empty"]]
    rep["gaps"] = missing_months(have)
    if not rep["months"]:
        rep["problems"].append("⒝ 넣을 달이 하나도 없습니다(자료 있는 승하차 raw 0)")
    return rep


# ── SQL ──────────────────────────────────────────────────────────────────────


def copy_path_literal(path):
    return path.replace("\\", "/").replace("'", "''")


def write_staging(rep, staging_dir):
    """관문을 지난 두 표 사본 csv(머리줄 포함) → (역 csv, 승하차 csv, 승하차 줄 수)."""
    os.makedirs(staging_dir, exist_ok=True)
    sp = os.path.join(staging_dir, "subway_station.csv")
    rp = os.path.join(staging_dir, "subway_ridership_m.csv")
    with io.open(sp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(STATION_COLUMNS)
        for s in rep["stations"]:
            w.writerow([s["station_id"], s["station_nm"], s["name_norm"], s["line_nm"], s["group_id"],
                        repr(s["lat"]), repr(s["lng"])])
    n = 0
    with io.open(rp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(RIDE_COLUMNS)
        for ym in sorted(rep["rows"]):
            for r in rep["rows"][ym]:
                w.writerow(["" if v is None else v for v in r])
                n += 1
    return sp, rp, n


def build_sql(station_csv, ride_csv, n_stations, n_rides, months):
    """적재 SQL — 한 트랜잭션. 관문은 전부 raise exception(psql 은 select 결과와 무관하게 0 으로 끝난다).
    ⛔ RAISE 글의 % 는 자리표시자다(글자 % 는 %%)."""
    if not months:
        raise ValueError("넣을 달이 없습니다")
    ms = ", ".join("'{}'".format(m) for m in sorted(months))
    scols = ", ".join(STATION_COLUMNS)
    rcols = ", ".join(RIDE_COLUMNS)
    upd = ", ".join("{0} = excluded.{0}".format(c) for c in ("station_nm", "name_norm", "line_nm", "group_id",
                                                          "lat", "lng", "geom", "loaded_at"))
    return """set lock_timeout = '5s';
begin;
set local statement_timeout = '600s';

create temp table stage_subway_station (
  station_id text, station_nm text, name_norm text, line_nm text, group_id int,
  lat double precision, lng double precision
) on commit drop;
\\copy stage_subway_station ({scols}) from '{spath}' with (format csv, header true, encoding 'UTF8')

create temp table stage_subway_ridership (like subway_ridership_m including defaults) on commit drop;
\\copy stage_subway_ridership ({rcols}) from '{rpath}' with (format csv, header true, encoding 'UTF8')

-- ── 행수 대조 — CSV 가 잘려도 \\copy 는 에러 없이 거기까지만 넣는다 ─────────────
do $$
begin
  if (select count(*) from stage_subway_station) <> {ns} then
    raise exception '올린 역 수가 마스터 행 수({ns})와 다릅니다 — 통째로 되돌립니다';
  end if;
  if (select count(*) from stage_subway_ridership) <> {nr} then
    raise exception '올린 승하차 줄 수가 원본에서 읽은 줄 수({nr})와 다릅니다 — 통째로 되돌립니다';
  end if;
end $$;

-- ── 관문 ⒣ — 승하차 station_id 가 전부 이번 마스터에 있다 ─────────────
do $$
declare v_bad int;
begin
  select count(*) into v_bad from stage_subway_ridership r
   where not exists (select 1 from stage_subway_station s where s.station_id = r.station_id);
  if v_bad > 0 then
    raise exception '⒣ 마스터에 없는 역을 가리키는 승하차 줄 %개 — 통째로 되돌립니다', v_bad;
  end if;
end $$;

-- 마스터 upsert(전 칸) — has_ridership 은 맨 끝에서 다시 센다.
insert into subway_station ({scols}, geom, loaded_at)
select {scols}, st_setsrid(st_makepoint(lng, lat), 4326), now() from stage_subway_station
on conflict (station_id) do update set {upd};

-- 이번 달들을 지운다(달 단위 교체 — 개정판 대비). 아래 관문에 걸리면 이 삭제까지 되돌아간다.
delete from subway_ridership_m where use_mm in ({ms});

-- 마스터에서 사라진 역 — 남은 달의 승하차가 가리키면 지우지 않고 멈춘다(사람이 본다).
do $$
declare v_ref text;
begin
  select string_agg(s.station_id, ', ' order by s.station_id) into v_ref
    from subway_station s
   where not exists (select 1 from stage_subway_station t where t.station_id = s.station_id)
     and exists (select 1 from subway_ridership_m r where r.station_id = s.station_id);
  if v_ref is not null then
    raise exception '마스터에서 사라진 역(%)을 다른 달의 승하차가 가리킵니다 — 통째로 되돌립니다', v_ref;
  end if;
end $$;
delete from subway_station s
 where not exists (select 1 from stage_subway_station t where t.station_id = s.station_id);

insert into subway_ridership_m ({rcols})
select {rcols} from stage_subway_ridership;

update subway_station s
   set has_ridership = exists (select 1 from subway_ridership_m r where r.station_id = s.station_id);

do $$
begin
  if (select count(*) from subway_ridership_m where use_mm in ({ms})) <> {nr} then
    raise exception '표에 든 승하차 줄 수가 기대({nr})와 다릅니다 — 통째로 되돌립니다';
  end if;
  if (select count(*) from subway_station) <> {ns} then
    raise exception '표에 든 역 수가 마스터 행 수({ns})와 다릅니다 — 통째로 되돌립니다';
  end if;
end $$;

select (select count(*) from subway_station) as stations,
       (select count(*) from subway_station where has_ridership) as stations_with_ridership,
       (select count(distinct group_id) from subway_station) as station_groups,
       (select count(*) from subway_ridership_m) as ridership_rows,
       (select min(use_mm) from subway_ridership_m) as first_mm,
       (select max(use_mm) from subway_ridership_m) as last_mm;

commit;
""".format(scols=scols, rcols=rcols, spath=copy_path_literal(station_csv), rpath=copy_path_literal(ride_csv),
           ns=int(n_stations), nr=int(n_rides), ms=ms, upd=upd)


# ── 리포트 ───────────────────────────────────────────────────────────────────


def print_report(rep, dry_run):
    print("=" * 96)
    print("서울 지하철 역사마스터 + 승하차 → subway_station · subway_ridership_m {}".format(
        "(dry-run)" if dry_run else ""))
    print("=" * 96)
    st = rep.get("stations") or []
    if st:
        print("  마스터 {} · 역 {:,} · 묶음 {:,} · 이름 {:,} · 서로 600m 넘어 갈린 같은 이름 {} {}".format(
            rep["master_file"], len(st), len({s["group_id"] for s in st}), len({s["name_norm"] for s in st}),
            len(rep["split"]), rep["split"]))
    print("  {:<6} {:>5} {:>5} {:>4} {:>5} {:>8} {:>9} {:>13} {:>13} {:>5} {:>5}".format(
        "달", "원문", "중복뺌", "skip", "붙음", "조인률%", "호선짝표만%", "승차합", "하차합", "승0", "하0"))
    for ym, m in rep["months"].items():
        print("  {:<6} {:>5} {:>5} {:>4} {:>5} {:>8.2f} {:>9.2f} {:>13,} {:>13,} {:>5} {:>5}".format(
            ym, m["raw"], m["dedup"], m["skip"], m["joined"], m["rate"], m["plain_rate"], m["on"], m["off"],
            len(m["zero_on"]), len(m["zero_off"])))
    print("  ⓘ 조인률 = 붙은 행 ÷ (중복 뺀 행 − skip 행) — 관문 ⒟ 문턱 {}% · 호선짝표만 = 역 짝표 없이 호선 짝표로만 붙은 "
          "행 ÷ 중복 뺀 행".format(MIN_JOIN_PCT))
    if rep["months"]:
        rates = [(m["rate"], ym) for ym, m in rep["months"].items()]
        plain = [(round(m["plain_rate"], 2), ym) for ym, m in rep["months"].items()]
        dup = [ym for ym, m in rep["months"].items() if m["raw"] != m["dedup"]]
        skips = collections.Counter(k for m in rep["months"].values() for k in m["skip_keys"])
        last = list(rep["months"])[-1]
        print("  달 {} · 조인률 최저 {:.2f}%({}) · 최고 {:.2f}%({}) · 호선짝표만 최저 {:.2f}%({}) · 최고 {:.2f}%({}) · "
              "같은 값 중복을 하나로 줄인 달 {}".format(
                  len(rates), min(rates)[0], min(rates)[1], max(rates)[0], max(rates)[1],
                  min(plain)[0], min(plain)[1], max(plain)[0], max(plain)[1], dup or "없음"))
        print("  skip 으로 세어 뺀 행 {} · {}".format(sum(skips.values()),
                                                 " · ".join("{}·{} {}".format(k[0], k[1], n) for k, n in sorted(skips.items()))))
        lm = rep["months"][last]
        print("  0 값 역({} — 환승역 몰아 세기 꼴 · 관문 아님): 승차 0 {}행 {} · 하차 0 {}행 {}".format(
            last, len(lm["zero_on"]), lm["zero_on"], len(lm["zero_off"]),
            ", ".join("{}·{}".format(s, ln) for ln, s in lm["zero_off"])))
    if rep["empty"]:
        print("  「자료 없음」 봉투라 건너뛴 달(INFO-200 등): {}".format(rep["empty"]))
    print("  ⒢ 빠진 달(멈추지 않음): {}".format(rep["gaps"] or "없음"))


# ── 메인 ─────────────────────────────────────────────────────────────────────


def main(argv=None):
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="서울 지하철 역사마스터 + 승하차 raw → subway_station · subway_ridership_m",
                                allow_abbrev=False)
    p.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    p.add_argument("--staging-dir", default=DEFAULT_STAGING_DIR)
    p.add_argument("--months", default=None, help="일부 달만(YYYYMM,YYYYMM … · 기본 = raw 에 있는 달 전부)")
    p.add_argument("--dry-run", action="store_true", help="관문 리포트만 — DB·파일 쓰기 0")
    a = p.parse_args(argv)

    months = None
    if a.months:
        months = [m.strip() for m in a.months.split(",") if m.strip()]
        bad = [m for m in months if not RE_MONTH.match(m)]
        if bad:
            print("[에러] --months 꼴이 YYYYMM 이 아닙니다: {}".format(bad), file=sys.stderr)
            return 2
    try:
        rep = scan(a.raw_dir, months)
    except (GateError, OSError, ValueError) as e:
        print("실패 — DB 에는 아무것도 쓰지 않았습니다: {}".format(e), file=sys.stderr)
        return 1

    print_report(rep, a.dry_run)
    if rep["problems"]:
        print()
        print("관문에 걸렸습니다 — DB 에는 아무것도 쓰지 않았습니다:", file=sys.stderr)
        for m in rep["problems"]:
            print("  " + m, file=sys.stderr)
        return 1
    print("  관문 통과 (⒜ · ⒝ · ⒞ · ⒟ · ⒠ · ⒡ · ⒢ 보고 — ⒣ 는 실적재 SQL 안에서)")

    if a.dry_run:
        print()
        print("--dry-run — DB·파일에 아무것도 쓰지 않았습니다.")
        return 0

    sp, rp, n = write_staging(rep, a.staging_dir)
    sql = build_sql(sp, rp, len(rep["stations"]), n, list(rep["months"]))

    import dbx  # noqa: PLC0415  (dry-run 은 DB 설정 없이도 돌아야 한다)
    rc = dbx.run_sql(sql)
    if rc != 0:
        print("적재 실패 (psql 종료코드 {}). 한 트랜잭션이라 아무것도 안 들어갔습니다.".format(rc), file=sys.stderr)
        return rc
    print()
    print("  적재 완료 ({}).".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    print("  다음: python scripts/post_load.py   그리고   python scripts/post_load.py --check")
    print("  라이브 「상권 인구」 카드의 지하철 덩이는 이 적재 뒤에 보인다(그 전엔 함수가 no_data 로 덩이를 숨긴다).")
    print("  💾 원본이 늘었으면 python scripts/backup_raw.py 도 잊지 마세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
