# -*- coding: utf-8 -*-
"""
결정 0033 R3 — 개업·폐업 정답지 시험 (서울 · 읽기만)

무엇을 하나
-----------
소진공 상가(상권)정보 **두 사진(202603 → 202606)** 을 맞대어 상권마다 "사라진 가게"와
"새로 보인 가게"를 세고, 그 수를 서울시 상권분석서비스가 공표한 **20262 분기 개업·폐업
점포 수**(정답지)와 상권별로 맞대어 본다.

이 시험의 쓰임은 하나다 — **"서울시 공표값이 없는 대전에 사진 비교 숫자를 올려도 되나"
의 근거**. 서울 화면에는 이 숫자를 쓰지 않는다(서울은 공표값을 그대로 나른다 · 결정 0033).

**DB·외부 호출 0.** 입력은 전부 로컬 파일이고, 쓰는 것은 `docs/backtest/` 의 성적표 두 개뿐이다.

입력 (인자로 바꿀 수 있다 · 기본값은 레포 기준 상대경로)
------------------------------------------------------
- 앞 사진 `data/raw/sangkwon_zips/소상공인시장진흥공단_상가(상권)정보_20260331.zip`
- 뒤 사진 `data/raw/sangkwon_zips/상가(상권)정보_20260630.zip`(⚠️ 이 판은 파일 이름에 접두가 없다)
  → 두 zip 안의 **서울 CSV**(멤버 이름에 '서울') · 그 안에서도 `시도코드 = 11` 행만.
- 상권 도형 `public/districts.geojson` 의 서울 1,650개(`sigungu_code` 앞 두 자리 11).
  ⚠️ 이 파일은 지도용으로 **단순화된 도형**(허용 0.0001° ≈ 11m)이다 — DB 원래 도형과 경계 근처가 다를 수 있다.
- 정답지 `data/raw/seoul_openclose/api/20262_20261005.jsonl`(R1 수집기가 받은 원본).

셈법
----
- 가게 → 상권: 점이 도형 **안**(`contains` — 경계 위의 점은 안 센다) · 겹치는 상권이면 **양쪽 모두** 센다.
  DB 의 `mv_district_industry_mix`(`st_contains(d.geom, ub.geom)`)와 같은 뜻.
  좌표가 없는 가게는 셈에서 빠지고 그 수를 성적표에 적는다.
- **A 번호 그대로**: 사라짐 = 앞 사진에만 있는 상가업소번호(상권은 **앞 사진 좌표**로) ·
  새로 보임 = 뒤 사진에만 있는 번호(상권은 **뒤 사진 좌표**로).
- **B 재매칭 뒤**: A 의 사라짐과 새로 보임 가운데 **(pnu, 상호명)이 같으면 한 짝** →
  짝이 여럿이면 번호 7~12자리(번호 생긴 연월)가 같은 것 우선 → 그래도 여럿이면 하나만 짝
  (번호 순 첫째) → 짝지은 가게는 사라짐·새로 보임 **양쪽에서 함께** 뺀다.
  임시번호 재부여(MA0106 → MA0101)도 이 규칙 하나로 처리한다(별도 규칙 없음).
- 정답지: 상권별 Σ`CLSBIZ_STOR_CO`(폐업 ↔ 사라짐) · Σ`OPBIZ_STOR_CO`(개업 ↔ 새로 보임) — 업종 합.
- 점포 수는 **맞대지 않는다**(소진공 247업종 vs 서울시 100업종) — 상권별 CSV 에 참고 열로만.

성적 (A·B × 개업·폐업 = 4칸)
---------------------------
상권별 (우리 ÷ 공식) 비율의 중앙값·사분위(25·75%) · ±30% 안 상권 비율 · 전체 합 비율 ·
순위 상관(스피어만). 공식 값이 0 인 상권은 비율에서 빼고 그 수를 적는다
(스피어만은 0 을 포함한 전 상권으로). **기준선은 이 스크립트가 정하지 않는다** — 성적을
보고 사장님이 정한다(Stage B 결정 0013 과 같은 순서). 그래서 판정 문구를 쓰지 않는다.

출력 (기본 `docs/backtest/`)
----------------------------
- `개업폐업-정답지-v1.md`         — 사람이 읽는 성적표
- `개업폐업-정답지-v1-상권별.csv` — 상권 1행 원자료(가게 한 곳 한 곳 단위 파일은 만들지 않는다)

쓰는 법
-------
    python scripts/backtest_openclose.py
    python scripts/backtest_openclose.py --before-zip <경로> --after-zip <경로> \\
        --districts <경로> --official <경로> --out-dir docs/backtest

의존: pandas(CSV 읽기)·shapely(도형) — 둘 다 함수 안에서 늦게 불러온다(시험은 셈 함수만
보므로 CI 에 shapely 가 없어도 된다).
"""

import argparse
import csv
import io
import json
import math
import os
import re
import time
import zipfile
from collections import Counter, defaultdict, namedtuple
from datetime import date, datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BEFORE_ZIP = os.path.join(
    PROJECT_ROOT, "data", "raw", "sangkwon_zips", "소상공인시장진흥공단_상가(상권)정보_20260331.zip")
DEFAULT_AFTER_ZIP = os.path.join(PROJECT_ROOT, "data", "raw", "sangkwon_zips", "상가(상권)정보_20260630.zip")
DEFAULT_DISTRICTS = os.path.join(PROJECT_ROOT, "public", "districts.geojson")
DEFAULT_OFFICIAL = os.path.join(PROJECT_ROOT, "data", "raw", "seoul_openclose", "api", "20262_20261005.jsonl")
DEFAULT_OUT_DIR = os.path.join(PROJECT_ROOT, "docs", "backtest")

MD_NAME = "개업폐업-정답지-v1.md"
CSV_NAME = "개업폐업-정답지-v1-상권별.csv"

SEOUL_SIDO = "11"
CSV_COLS = ("상가업소번호", "상호명", "시도코드", "지번코드", "경도", "위도")
BAND = 0.30  # ±30% 안
VERDICT_WORDS = ("불합격", "합격", "통과")  # 성적표에 쓰지 않는 판정 낱말(긴 것부터 찾는다)

Store = namedtuple("Store", "name pnu lng lat")


def log(message):
    print("[backtest_openclose] {}".format(message), flush=True)


# ── 셈 규칙 (shapely 없이 시험된다) ──────────────────────────────────────────


def biz_ym(biz_no):
    """상가업소번호 7~12자리 = 번호가 생긴 연월(예 MA0106202201A2069228 → 202201)."""
    return biz_no[6:12]


def diff_by_number(before_ids, after_ids):
    """셈법 A — (앞에만 있는 번호, 뒤에만 있는 번호), 각각 번호 순."""
    before_ids = set(before_ids)
    after_ids = set(after_ids)
    return sorted(before_ids - after_ids), sorted(after_ids - before_ids)


def rematch(gone, new):
    """셈법 B — 사라짐·새로 보임 가운데 (pnu, 상호명)이 같은 것을 한 짝으로.

    gone·new = {번호: Store}. 돌려주는 것 = [(사라진 번호, 새 번호)] (사라진 번호 순).
    짝이 여럿이면 생긴 연월이 같은 것 우선, 그래도 여럿이면 번호 순 첫째 하나만.
    한 가게는 한 번만 짝이 된다.
    """
    new_by_key = defaultdict(list)
    for nid in sorted(new):
        rec = new[nid]
        new_by_key[(rec.pnu, rec.name)].append(nid)
    gone_by_key = defaultdict(list)
    for gid in sorted(gone):
        rec = gone[gid]
        gone_by_key[(rec.pnu, rec.name)].append(gid)

    pairs = []
    for key, gids in gone_by_key.items():
        candidates = new_by_key.get(key)
        if not candidates:
            continue
        used = set()
        unpaired = []
        for gid in gids:  # 1차: 생긴 연월이 같은 것
            ym = biz_ym(gid)
            hit = next((n for n in candidates if n not in used and biz_ym(n) == ym), None)
            if hit is None:
                unpaired.append(gid)
            else:
                used.add(hit)
                pairs.append((gid, hit))
        for gid in unpaired:  # 2차: 남은 것 가운데 번호 순 첫째
            hit = next((n for n in candidates if n not in used), None)
            if hit is not None:
                used.add(hit)
                pairs.append((gid, hit))
    return sorted(pairs)


def apply_rematch(gone_ids, new_ids, pairs):
    """짝지은 가게를 사라짐·새로 보임 양쪽에서 함께 뺀다(순서 유지)."""
    paired_gone = {g for g, _ in pairs}
    paired_new = {n for _, n in pairs}
    return [g for g in gone_ids if g not in paired_gone], [n for n in new_ids if n not in paired_new]


def parse_coord(lng, lat):
    """(경도, 위도) 실수 한 쌍. 비었거나 숫자가 아니거나 0 이면 None(좌표 없음)."""
    try:
        x = float(lng)
        y = float(lat)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)) or x == 0 or y == 0:
        return None
    return (x, y)


def count_by_district(ids, assignment):
    """번호 목록을 상권별로 센다. assignment = {번호: (상권 id, …)} — 겹치면 양쪽 모두."""
    counts = Counter()
    for i in ids:
        for d in assignment.get(i, ()):
            counts[d] += 1
    return dict(counts)


def count_gone_new(gone_ids, new_ids, before_assign, after_assign):
    """사라짐은 **앞 사진** 배정으로, 새로 보임은 **뒤 사진** 배정으로 센다."""
    return count_by_district(gone_ids, before_assign), count_by_district(new_ids, after_assign)


def load_official(path):
    """정답지 jsonl → ({상권: {opbiz, clsbiz, stor, similr}}, {분기})."""
    sums = defaultdict(lambda: {"opbiz": 0, "clsbiz": 0, "stor": 0, "similr": 0})
    quarters = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            quarters.add(str(obj.get("quarter")))
            row = obj["row"]
            s = sums[str(row["TRDAR_CD"])]
            s["opbiz"] += int(round(float(row["OPBIZ_STOR_CO"])))
            s["clsbiz"] += int(round(float(row["CLSBIZ_STOR_CO"])))
            s["stor"] += int(round(float(row["STOR_CO"])))
            s["similr"] += int(round(float(row["SIMILR_INDUTY_STOR_CO"])))
    return dict(sums), quarters


# ── 성적 ─────────────────────────────────────────────────────────────────────


def percentile(values, q):
    """0~1 분위수(선형 보간 — backtest_price.percentile 과 같은 정의). 비면 None."""
    if not values:
        return None
    ordered = sorted(values)
    pos = q * (len(ordered) - 1)
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def _ranks(values):
    """평균 순위(동순위는 평균) — 1부터."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs, ys):
    """스피어만 순위 상관(동순위 평균 순위의 피어슨). 한쪽이 상수면 None."""
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    rx = _ranks(list(xs))
    ry = _ranks(list(ys))
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def ratio_metrics(ours, official, district_ids, band=BAND):
    """상권별 (우리 ÷ 공식) 성적 한 칸. ours·official = {상권: 수} (없으면 0)."""
    ratios = []
    xs = []
    ys = []
    n_zero = 0
    for d in district_ids:
        o = ours.get(d, 0)
        f = official.get(d, 0)
        xs.append(o)
        ys.append(f)
        if f == 0:
            n_zero += 1
        else:
            ratios.append(o / f)
    total_o = sum(xs)
    total_f = sum(ys)
    within = [r for r in ratios if abs(r - 1.0) <= band + 1e-9]
    return {
        "n_districts": len(district_ids),
        "n_zero_official": n_zero,
        "n_ratio": len(ratios),
        "median": percentile(ratios, 0.5),
        "q25": percentile(ratios, 0.25),
        "q75": percentile(ratios, 0.75),
        "within30": (len(within) / len(ratios)) if ratios else None,
        "spearman": spearman(xs, ys),
        "total_ours": total_o,
        "total_official": total_f,
        "total_ratio": (total_o / total_f) if total_f else None,
    }


def find_verdict_words(text):
    """판정 낱말을 찾는다(긴 낱말이 짧은 낱말을 품으면 긴 쪽만 — '불합격' 안의 '합격')."""
    found = []
    rest = text
    for w in VERDICT_WORDS:
        if w in rest:
            found.append(w)
            rest = rest.replace(w, " ")
    return found


# ── 파일 읽기 (pandas·shapely 는 여기서만) ───────────────────────────────────


def seoul_member(zf):
    names = [i.filename for i in zf.infolist() if "서울" in i.filename and i.filename.lower().endswith(".csv")]
    if len(names) != 1:
        raise SystemExit("zip 안 서울 CSV 가 하나가 아니다: {}".format(names))
    return names[0]


def load_snapshot(zip_path):
    """zip 안 서울 CSV → ({번호: Store}, 정보). 시도코드 11 행만."""
    import pandas as pd

    with zipfile.ZipFile(zip_path) as zf:
        member = seoul_member(zf)
        with zf.open(member) as f:
            df = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8-sig"), usecols=list(CSV_COLS),
                             dtype=str, keep_default_na=False)
    n_all = len(df)
    df = df[df["시도코드"] == SEOUL_SIDO]
    stores = {}
    n_dup = 0
    for biz, name, pnu, lng, lat in zip(df["상가업소번호"], df["상호명"], df["지번코드"], df["경도"], df["위도"]):
        if biz in stores:
            n_dup += 1
            continue
        xy = parse_coord(lng, lat)
        stores[biz] = Store(name=name, pnu=pnu, lng=xy[0] if xy else None, lat=xy[1] if xy else None)
    info = {"member": member, "rows_all": n_all, "rows_seoul": len(df), "dup": n_dup,
            "no_coord": sum(1 for s in stores.values() if s.lng is None)}
    return stores, info


def load_districts(path):
    """geojson → [(상권 id, shapely 도형)] (서울만) · 메타 {id: (이름, 종류, 구 코드)} · 깨진 도형 id."""
    from shapely.geometry import shape

    with open(path, encoding="utf-8") as f:
        gj = json.load(f)
    out = []
    meta = {}
    invalid = []
    for feat in gj["features"]:
        p = feat["properties"]
        if not str(p.get("sigungu_code", "")).startswith(SEOUL_SIDO):
            continue
        did = str(p["district_id"])
        geom = shape(feat["geometry"])
        if not geom.is_valid:
            invalid.append(did)
        out.append((did, geom))
        meta[did] = (p.get("district_nm"), p.get("district_type"), str(p.get("sigungu_code")))
    return out, meta, invalid


def assign_to_districts(stores, districts):
    """가게 → 상권. 점이 도형 안(경계 위 제외) · 겹치면 양쪽. ({번호: (상권…)}, 좌표 없음 수)."""
    import numpy as np
    from shapely import STRtree, points

    ids = []
    xs = []
    ys = []
    n_no_coord = 0
    for sid, s in stores.items():
        if s.lng is None or s.lat is None:
            n_no_coord += 1
            continue
        ids.append(sid)
        xs.append(s.lng)
        ys.append(s.lat)
    assignment = {sid: () for sid in ids}
    if not ids:
        return assignment, n_no_coord
    tree = STRtree(points(np.array(xs), np.array(ys)))
    # query(도형, predicate="contains") → 도형.contains(점) 인 (도형 순번, 점 순번)
    poly_idx, pt_idx = tree.query([g for _, g in districts], predicate="contains")
    hits = defaultdict(list)
    for pi, ti in zip(poly_idx.tolist(), pt_idx.tolist()):
        hits[ti].append(districts[pi][0])
    for ti, dids in hits.items():
        assignment[ids[ti]] = tuple(sorted(dids))
    return assignment, n_no_coord


# ── 출력 ─────────────────────────────────────────────────────────────────────


CELLS = (
    ("A", "폐업", "사라짐"),
    ("A", "개업", "새로 보임"),
    ("B", "폐업", "사라짐"),
    ("B", "개업", "새로 보임"),
)


def _ratio(o, f):
    return "" if not f else round(o / f, 6)


def write_csv(path, district_ids, meta, counts, official, after_inside):
    header = ["상권id", "상권이름", "상권종류", "구코드",
              "A_사라짐", "A_새로보임", "B_사라짐", "B_새로보임",
              "공식_폐업", "공식_개업",
              "비율_A_폐업", "비율_A_개업", "비율_B_폐업", "비율_B_개업",
              "참고_우리_뒤사진_상권안_가게수", "참고_공식_점포수", "참고_공식_유사업종점포수"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for d in district_ids:
            nm, typ, sgg = meta[d]
            off = official.get(d, {"opbiz": 0, "clsbiz": 0, "stor": 0, "similr": 0})
            ag, an = counts["A_gone"].get(d, 0), counts["A_new"].get(d, 0)
            bg, bn = counts["B_gone"].get(d, 0), counts["B_new"].get(d, 0)
            w.writerow([d, nm, typ, sgg, ag, an, bg, bn, off["clsbiz"], off["opbiz"],
                        _ratio(ag, off["clsbiz"]), _ratio(an, off["opbiz"]),
                        _ratio(bg, off["clsbiz"]), _ratio(bn, off["opbiz"]),
                        after_inside.get(d, 0), off["stor"], off["similr"]])


def _p(v, digits=1):
    return "-" if v is None else "{:.{}f}%".format(v * 100, digits)


def _r(v, digits=3):
    return "-" if v is None else "{:.{}f}".format(v, digits)


RE_ZIP_DATE = re.compile(r"_(\d{4})(\d{2})(\d{2})\.zip$", re.IGNORECASE)
RE_QUARTER = re.compile(r"^(\d{4})([1-4])$")
QUARTER_LAST_DAY = {1: 31, 2: 30, 3: 30, 4: 31}  # 분기 끝 달(3·6·9·12월)의 마지막 날


def snapshot_label(zip_path):
    """zip 파일 이름 끝 `_YYYYMMDD.zip` → (이름표 YYYYMM, 날짜 date). 날짜가 없으면 (파일 이름, None).

    성적표의 이름표·날짜를 글자로 박지 않고 입력 파일에서 읽는다(2026-10-06 — 다음 분기 사진으로
    다시 돌리면 옛 날짜가 그대로 찍히던 것)."""
    name = os.path.basename(zip_path)
    m = RE_ZIP_DATE.search(name)
    if not m:
        return name, None
    try:
        day = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return name, None
    return m.group(1) + m.group(2), day


def quarter_span(quarters):
    """공식 분기 코드 모음 → (분기 글, 시작 date, 끝 date). 분기가 **하나**이고 `YYYYQ` 꼴일 때만
    날짜를 낸다 — 여럿이면 (코드들을 쉼표로, None, None)."""
    codes = sorted(str(q) for q in quarters)
    m = RE_QUARTER.match(codes[0]) if len(codes) == 1 else None
    if not m:
        return ", ".join(codes), None, None
    year, q = int(m.group(1)), int(m.group(2))
    return codes[0], date(year, 3 * q - 2, 1), date(year, 3 * q, QUARTER_LAST_DAY[q])


def _md(d):
    return "{}/{}".format(d.month, d.day)


def period_context(before_zip, after_zip, quarters):
    """build_markdown 의 기간 글감 — 이름표·사진 날짜·분기 달."""
    before_label, before_day = snapshot_label(before_zip)
    after_label, after_day = snapshot_label(after_zip)
    quarter, q_start, q_end = quarter_span(quarters)
    return {
        "before_label": before_label, "after_label": after_label, "quarter": quarter,
        "before_day": before_day, "after_day": after_day, "q_start": q_start, "q_end": q_end,
    }


def _period_lines(ctx):
    """(기간 어긋남 줄, 한계 줄) — 날짜를 모르면 날짜 글은 뺀다."""
    bd, ad, qs, qe = ctx.get("before_day"), ctx.get("after_day"), ctx.get("q_start"), ctx.get("q_end")
    photo = "({} → {})".format(_md(bd), _md(ad)) if bd and ad else ""
    months = "({}~{}월)".format(qs.month, qe.month) if qs and qe else ""
    span = "({}~{})".format(_md(qs), _md(qe)) if qs and qe else ""
    first = "- 기간 어긋남(있는 그대로): 사진은 {} → {}{}, 공식 분기는 {}{}.".format(
        ctx["before_label"], ctx["after_label"], photo, ctx["quarter"], months)
    if bd and ad and qs and qe and (qs - bd).days == 1 and ad == qe:
        gap = "하루 차이지만"
    else:
        gap = "기준일이 다를 수 있고"
    last = "- 사진 기간{}과 분기{}는 {}, 소진공 사진의 실제 기준일·갱신 지연은 알 수 없다.".format(photo, span, gap)
    return first, last


def build_markdown(ctx):
    L = []
    a = L.append
    a("# 개업·폐업 정답지 시험 v1 — 사진 비교 vs 서울시 공표 (결정 0033 R3)")
    a("")
    a("> 생성: {} · `scripts/backtest_openclose.py` · DB·외부 호출 0 · 실행 {:.0f}초".format(
        ctx["generated_at"], ctx["elapsed_s"]))
    a("")
    a("## 먼저 읽을 것 — 두 값은 뜻이 다르다")
    a("")
    a("- **공식 폐업**(서울시 상권분석서비스 `CLSBIZ_STOR_CO`) = 그 분기 안에 **폐업 신고된 점포 수**. "
      "공표 폐업률은 이 수를 분기말 남은 점포(유사 업종 점포 수)로 나눈 것이고, 여기서 맞대는 것은 "
      "그 비율의 분자 = **분기 안 신고 수**(폐업 점포 수)다. 공식 개업(`OPBIZ_STOR_CO`)도 같은 꼴.")
    a("- **우리 값** = 소진공 두 사진 사이 사라짐·새로 보임. **두 사진 사이 사라짐**에는 폐업뿐 아니라 "
      "이전·이름 변경·임시번호 재부여(MA0106 → MA0101)·자료 정비가 섞인다. 셈법 B 는 그 일부(같은 필지·같은 "
      "상호명)를 짝지어 뺀 값이다.")
    a("- 업종 범위도 다르다 — 소진공은 전 업종(247), 서울시는 100업종. 그래서 점포 수는 맞대지 않고 CSV 에 "
      "참고 열로만 둔다.")
    period_first, period_last = _period_lines(ctx)
    a(period_first)
    a("- ⛔ 이 시험은 **\"대전에 사진 비교를 올려도 되나\"의 근거**이지, 서울 화면에는 쓰지 않는다"
      "(서울은 공표값을 그대로 나른다).")
    a("- 기준선은 여기서 정하지 않는다 — 아래 성적을 보고 사장님이 정한다(Stage B 결정 0013 과 같은 순서).")
    a("")
    a("## 입력")
    a("")
    a("| 구분 | 파일 | 바이트 |")
    a("|---|---|---|")
    for label, path, size in ctx["inputs"]:
        a("| {} | `{}` | {:,} |".format(label, path, size))
    a("")
    a("## 셈 과정 수치")
    a("")
    a("| 항목 | 수 |")
    a("|---|---|")
    for label, value in ctx["process_rows"]:
        a("| {} | {} |".format(label, value if isinstance(value, str) else "{:,}".format(value)))
    a("")
    a("## 성적 — 상권별 (우리 ÷ 공식)")
    a("")
    a("서울 상권 {:,}개. 비율은 공식 값이 0 인 상권을 뺀 나머지로, 스피어만은 0 을 포함한 전 상권으로 낸다. "
      "±30% 안 = 비율 0.7~1.3.".format(ctx["n_districts"]))
    a("")
    a("| 셈법 | 맞대는 것 | 공식 0 상권 | 비율 낸 상권 | 중앙값 | 25% | 75% | ±30% 안 | 스피어만 | 우리 합 | 공식 합 | 전체 합 비율 |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for (method, kind, ours_label), m in ctx["cells"]:
        a("| {} | {} ↔ 공식 {} | {:,} | {:,} | {} | {} | {} | {} | {} | {:,} | {:,} | {} |".format(
            method, ours_label, kind, m["n_zero_official"], m["n_ratio"],
            _r(m["median"]), _r(m["q25"]), _r(m["q75"]), _p(m["within30"]), _r(m["spearman"]),
            m["total_ours"], m["total_official"], _r(m["total_ratio"])))
    a("")
    a("- A = 번호 그대로 · B = (pnu, 상호명) 재매칭 뒤.")
    a("- 겹치는 상권의 가게는 양쪽에 모두 센다 — 우리 합·공식 합 모두 상권별 값을 더한 것이라 같은 기준이다.")
    a("")
    a("## 한계")
    a("")
    a("- 상권 도형은 `public/districts.geojson` — 지도용으로 **단순화된 도형**(`ST_SimplifyPreserveTopology` "
      "허용 0.0001° ≈ 11m · `scripts/build_district_geojson.py`)이다. DB 원래 도형과 경계 근처에서 다를 수 있어 "
      "경계 가까운 가게는 다른 상권으로 갈 수 있다.")
    if ctx["invalid_ids"]:
        a("- 도형 검사(`is_valid`)에 걸린 상권 {}개: {} — 고치지 않고 그대로 썼다.".format(
            len(ctx["invalid_ids"]), ", ".join(ctx["invalid_ids"])))
    a("- 좌표 없는 가게는 셈에서 빠진다(수는 위 표).")
    a("- 셈법 B 의 짝은 (pnu, 상호명) 글자가 똑같을 때만이다 — 띄어쓰기·지점명이 바뀐 이전·간판 변경은 못 묶는다. "
      "반대로 같은 필지의 같은 이름 다른 가게(체인 두 곳 등)를 한 짝으로 묶을 수 있다.")
    a("- 공식 값은 서울시 100업종 안의 점포만 센다. 소진공 247업종 가운데 그 밖 업종의 가게는 우리 쪽에만 들어간다.")
    a(period_last)
    a("")
    a("## 산출물")
    a("")
    a("- 상권별 원자료: `docs/backtest/{}` (상권 1행 · 가게 단위 파일은 만들지 않는다)".format(CSV_NAME))
    a("")
    return "\n".join(L)


def sample_context_for_tests(metrics):
    """build_markdown 시험용 최소 ctx(숫자는 의미 없음)."""
    ctx = {
        "generated_at": "2000-01-01 00:00", "elapsed_s": 0.0,
        "inputs": [("앞 사진", "a.zip", 1)], "process_rows": [("행", 1)],
        "n_districts": metrics["n_districts"],
        "cells": [(c, metrics) for c in CELLS],
        "invalid_ids": ["X"],
    }
    ctx.update(period_context(DEFAULT_BEFORE_ZIP, DEFAULT_AFTER_ZIP, {"20262"}))
    return ctx


# ── 실행 ─────────────────────────────────────────────────────────────────────


def main(argv=None):
    ap = argparse.ArgumentParser(description="결정 0033 R3 — 개업·폐업 정답지 시험(읽기만)")
    ap.add_argument("--before-zip", default=DEFAULT_BEFORE_ZIP)
    ap.add_argument("--after-zip", default=DEFAULT_AFTER_ZIP)
    ap.add_argument("--districts", default=DEFAULT_DISTRICTS)
    ap.add_argument("--official", default=DEFAULT_OFFICIAL)
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    args = ap.parse_args(argv)

    t0 = time.time()
    log("앞 사진 읽기")
    before, binfo = load_snapshot(args.before_zip)
    log("  서울 {:,}행 · 좌표 없음 {:,}".format(binfo["rows_seoul"], binfo["no_coord"]))
    log("뒤 사진 읽기")
    after, ainfo = load_snapshot(args.after_zip)
    log("  서울 {:,}행 · 좌표 없음 {:,}".format(ainfo["rows_seoul"], ainfo["no_coord"]))

    districts, meta, invalid = load_districts(args.districts)
    district_ids = sorted(meta)
    official, quarters = load_official(args.official)
    log("상권 {:,} · 정답지 상권 {:,} · 분기 {}".format(len(district_ids), len(official), sorted(quarters)))
    missing = [d for d in district_ids if d not in official]
    extra = [d for d in official if d not in meta]

    gone_a, new_a = diff_by_number(before, after)
    pairs = rematch({g: before[g] for g in gone_a}, {n: after[n] for n in new_a})
    gone_b, new_b = apply_rematch(gone_a, new_a, pairs)
    same_ym = sum(1 for g, n in pairs if biz_ym(g) == biz_ym(n))
    log("A 사라짐 {:,} · 새로 보임 {:,} · B 짝 {:,}".format(len(gone_a), len(new_a), len(pairs)))

    log("상권 배정(앞 사진의 사라짐 · 뒤 사진 전부)")
    before_assign, gone_no_coord = assign_to_districts({g: before[g] for g in gone_a}, districts)
    after_assign, after_no_coord = assign_to_districts(after, districts)

    a_gone, a_new = count_gone_new(gone_a, new_a, before_assign, after_assign)
    b_gone, b_new = count_gone_new(gone_b, new_b, before_assign, after_assign)
    after_inside = count_by_district(list(after), after_assign)
    counts = {"A_gone": a_gone, "A_new": a_new, "B_gone": b_gone, "B_new": b_new}

    def uniq_inside(ids, assign):
        return sum(1 for i in ids if assign.get(i))

    new_no_coord = sum(1 for n in new_a if after[n].lng is None)
    new_b_no_coord = sum(1 for n in new_b if after[n].lng is None)
    gone_b_no_coord = sum(1 for g in gone_b if before[g].lng is None)

    off_cls = {d: v["clsbiz"] for d, v in official.items()}
    off_op = {d: v["opbiz"] for d, v in official.items()}
    cells = [
        (CELLS[0], ratio_metrics(a_gone, off_cls, district_ids)),
        (CELLS[1], ratio_metrics(a_new, off_op, district_ids)),
        (CELLS[2], ratio_metrics(b_gone, off_cls, district_ids)),
        (CELLS[3], ratio_metrics(b_new, off_op, district_ids)),
    ]

    os.makedirs(args.out_dir, exist_ok=True)
    csv_path = os.path.join(args.out_dir, CSV_NAME)
    write_csv(csv_path, district_ids, meta, counts, official, after_inside)

    elapsed = time.time() - t0
    process_rows = [
        ("앞 사진 서울 행 ({})".format(binfo["member"]), binfo["rows_seoul"]),
        ("뒤 사진 서울 행 ({})".format(ainfo["member"]), ainfo["rows_seoul"]),
        ("앞 사진 같은 번호 중복(뒤의 것 버림)", binfo["dup"]),
        ("뒤 사진 같은 번호 중복(뒤의 것 버림)", ainfo["dup"]),
        ("앞 사진 좌표 없음", binfo["no_coord"]),
        ("뒤 사진 좌표 없음", ainfo["no_coord"]),
        ("뒤 사진 가게 중 서울 상권 안(하나 이상)", uniq_inside(after, after_assign)),
        ("뒤 사진 상권 안 가게 수 합(겹침 양쪽)", sum(after_inside.values())),
        ("A 사라짐(앞에만 있는 번호)", len(gone_a)),
        ("A 사라짐 중 좌표 없음", gone_no_coord),
        ("A 사라짐 중 상권 안", uniq_inside(gone_a, before_assign)),
        ("A 새로 보임(뒤에만 있는 번호)", len(new_a)),
        ("A 새로 보임 중 좌표 없음", new_no_coord),
        ("A 새로 보임 중 상권 안", uniq_inside(new_a, after_assign)),
        ("B 짝 (pnu, 상호명)", len(pairs)),
        ("B 짝 중 생긴 연월이 같은 것", same_ym),
        ("B 짝 중 MA0106 → MA0101", sum(1 for g, n in pairs if g.startswith("MA0106") and n.startswith("MA0101"))),
        ("B 사라짐", len(gone_b)),
        ("B 사라짐 중 좌표 없음", gone_b_no_coord),
        ("B 사라짐 중 상권 안", uniq_inside(gone_b, before_assign)),
        ("B 새로 보임", len(new_b)),
        ("B 새로 보임 중 좌표 없음", new_b_no_coord),
        ("B 새로 보임 중 상권 안", uniq_inside(new_b, after_assign)),
        ("정답지에 없는 서울 도형 상권", len(missing)),
        ("도형에 없는 정답지 상권", len(extra)),
    ]
    inputs = []
    for label, path in (("앞 사진", args.before_zip), ("뒤 사진", args.after_zip),
                        ("상권 도형", args.districts), ("정답지", args.official)):
        inputs.append((label, os.path.relpath(path, PROJECT_ROOT).replace("\\", "/")
                       if os.path.abspath(path).startswith(PROJECT_ROOT) else os.path.basename(path),
                       os.path.getsize(path)))
    ctx = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "elapsed_s": elapsed,
        "inputs": inputs,
        "process_rows": process_rows,
        "n_districts": len(district_ids),
        "cells": cells,
        "invalid_ids": invalid,
    }
    ctx.update(period_context(args.before_zip, args.after_zip, quarters))
    md = build_markdown(ctx)
    words = find_verdict_words(md)
    if words:
        raise SystemExit("성적표에 판정 낱말이 들어갔다: {}".format(words))
    md_path = os.path.join(args.out_dir, MD_NAME)
    with open(md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    log("썼다: {} · {} · {:.0f}초".format(md_path, csv_path, elapsed))
    for (method, kind, _), m in cells:
        log("  {} {}: 중앙값 {} · ±30% {} · 스피어만 {} · 합 비율 {} · 공식0 {}".format(
            method, kind, _r(m["median"]), _p(m["within30"]), _r(m["spearman"]),
            _r(m["total_ratio"]), m["n_zero_official"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
