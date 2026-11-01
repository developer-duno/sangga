# -*- coding: utf-8 -*-
"""대전 상권 안 인구 — SGIS 집계구 통계를 상권 면에 면적 비율로 나눠 담아 상권마다 한 줄의 결과표를 굽는다
(결정 0045 ③-1·③-3 · PR⑤).

왜 이렇게 하나
--------------
서울은 서울시가 상권마다 상주·직장 인구를 공표한다(PR②). 대전은 그런 공표값이 없어서, 통계청 SGIS 가
집계구(동보다 작은 통계 구역 · 전국 108,510개)마다 낸 **2024년 인구·가구·종사자·사업체 총괄**을 상권 면에
겹쳐 담는다(👤 ③-1 — 대전만 · 거주 인구·가구·총종사자 · 상권 합계만 DB · 집계구 경계는 안 싣는다).
⛔ 이 값은 **어림(C 등급)** 이다 — 집계구 안에서 사람이 고르게 산다고 보고 겹친 면적 비율로 나눴다.
   그래서 값 옆에 늘 범위를 함께 낸다(👤 ③-3 · 함정 6):
     하한 = 상권 안에 **통째로** 든 집계구(겹침 / 집계구 면적 ≥ 0.99)의 합
     상한 = 상권에 **조금이라도**(겹침 ≥ 100㎡) 걸친 집계구 전부의 합
   화면은 「범위(상한 − 하한) > 2 × 값 이면 범위만」 · C 배지 · 「상권 안 합계 — 건물 값 아님」(다음 단계).
   이 결과표는 값·하한·상한·겹친 수·통째 수를 **그대로** 둔다(서버에서 숨기지 않는다).

계산 (2026-10-31 조사반 b4_overlap 그대로 · 11-01 서울 정답 대조로 검산)
-----------------------------------------------------------------------
  · 평면 = EPSG 5179(집계구 경계 좌표계). 상권은 DB 에서 `st_transform(geom, 5179)` WKT 로 읽고,
    상권 면적은 그 WKT 의 shapely 면적(DB 의 st_area 칸은 참고).
  · 겹침 < OVERLAP_MIN_M2(100㎡)는 버린다(경계선이 스친 조각) · 통째 = 겹침 / 집계구 면적 ≥ FULL_RATIO(0.99).
  · 배분값 = Σ(겹침 비율 × 값)을 파이썬 round() 로 정수 · 하한·상한 = 정수 합.
    배분값이 하한보다 작으면(통째 비율 0.99~1 이라 생긴다) 하한~상한 안으로 끼운다 — 끼운 칸 수는 meta n_clamped.
  · 덮임(cover_pct) = 겹침 합 / 상권 면적 × 100(소수 3자리).
  · 고장 난 도형(자기 교차)은 buffer(0) 으로 고친다(2025-2Q 경계에 10개).

멈추는 경우 (exit 1 — 결과표를 쓰지 않는다)
-------------------------------------------
  · 받은 날 폴더 이름 끝 10자리가 YYYY-MM-DD 가 아님 · 통계 zip / 경계 zip 이 정확히 1개가 아님
  · 총괄 4파일(이름 부분 문자열 · ITEMS)이 정확히 1개씩이 아님 · 파일 이름의 기준 연도가 서로 다름 · 연도 칸이 다름
  · 걸친 집계구의 총괄 값이 'N/A' 이거나 없음(집계구·항목을 찍는다) · 정수가 아닌 값
  · 상권이 0개 · 걸친 집계구가 0 인 상권이 있음 · 경계 BASE_DATE 가 한 가지가 아님

쓰는 법 (프로젝트 루트에서 · 외부 호출 0 · DB 는 읽기만)
-------------------------------------------------------
    python scripts/build_sgis_district_pop.py --dry-run          # 요약만(파일 쓰기 0 · 상권 도형은 DB 에서 읽는다)
    python scripts/build_sgis_district_pop.py                    # data/derived/sgis_district_pop/<받은 날 YYYYMMDD>.csv + .meta.json
    python scripts/build_sgis_district_pop.py --compare-seoul <서울시 상주인구 tsv>   # 서울 1,650 도 계산해 공표값과 대조
    → python scripts/collectors/load_sgis_district_pop.py --dry-run → 실적재 → post_load.py · --check
  `--raw-dir` 기본 = data/raw/sgis_census/ 아래 받은 날(폴더 이름 끝 날짜)이 가장 늦은 폴더.
  `--district-tsv <파일>` = DB 대신 그 TSV(같은 6칸: district_id, district_nm, district_type, sigungu_code,
  area_m2, 5179 WKT — psql 안내 두 줄은 건너뛴다 · 시험·오프라인용).
  ⛔ 시·도 코드 둘을 섞지 말 것 — 상권·PNU·시군구의 대전은 **30**, 집계구 코드의 대전 접두는 **25**(SIDO_TO_OA).
  shapely·pyshp 는 함수 안에서 부른다(CI 에는 없다 — 이 스크립트는 사람이 이 PC 에서 돌린다).
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
import statistics
import subprocess
import sys
import tempfile
import time
import zipfile
from zoneinfo import ZoneInfo

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
DEFAULT_RAW_ROOT = os.path.join(PROJECT_ROOT, "data", "raw", "sgis_census")
DEFAULT_OUT_DIR = os.path.join(PROJECT_ROOT, "data", "derived", "sgis_district_pop")
KST = ZoneInfo("Asia/Seoul")

OVERLAP_MIN_M2 = 100.0
FULL_RATIO = 0.99

# 결과표의 시·도(상권·PNU 코드) → 집계구 코드 접두. ⛔ 대전은 상권 30 · 집계구 25 다.
SIDO_TO_OA = {"30": "25", "11": "11"}
DEFAULT_SIDO = ("30",)
COMPARE_SIDO = "11"

# (결과 칸, 통계 파일 이름 부분 문자열(정확히 1개 맞아야), 항목 코드)
ITEMS = (
    ("pop", "인구총괄(총인구)", "to_in_001"),
    ("hh", "가구총괄", "to_ga_001"),
    ("emp", "총괄종사자수", "to_em_020"),
    ("est", "총괄사업체수", "to_fa_010"),
)
COLUMNS = ("district_id", "district_nm", "district_type", "sigungu_code", "area_m2", "n_overlap", "n_full",
           "cover_pct", "pop", "pop_lo", "pop_hi", "hh", "hh_lo", "hh_hi", "emp", "emp_lo", "emp_hi",
           "est", "est_lo", "est_hi")

RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_BASE_YEAR = re.compile(r"_(\d{4})년_")
RE_INT = re.compile(r"^\d+$")
CENSUS_ZIP_PREFIX = "_census_reqdoc_"
BND_ZIP_PREFIX = "bnd_oa_"
PSQL_NOTICES = ("Output format is", "Field separator is")

# 11-01 서울 정답 대조(2024 통계 · 2025-2Q 경계 · 서울시 상주인구 20262) — 같은 입력이면 ±0.1%p 안에서 재현돼야 한다.
SEOUL_REF = {"base_year": 2024, "median_pct": -3.8, "inside_pct": 95.5, "tol_pp": 0.1}

DISTRICT_SQL = (
    "select district_id, district_nm, district_type, sigungu_code, "
    "round(st_area(st_transform(geom, 5179))::numeric, 1), st_astext(st_transform(geom, 5179), 1) "
    "from district where left(sigungu_code, 2) = any(array[{sido}]) order by district_id"
)


class BuildError(ValueError):
    """멈춤 — 결과표를 쓰지 않는다."""


def log(msg=""):
    print(msg, flush=True)


# ── 입력 고르기 ──────────────────────────────────────────────────────────────


def received_on_of(raw_dir):
    """폴더 이름 끝 10자리 = 받은 날(YYYY-MM-DD). 모양이 틀리면 멈춤."""
    name = os.path.basename(os.path.normpath(raw_dir))
    tail = name[-10:]
    if not RE_DATE.match(tail):
        raise BuildError("받은 날 폴더 이름 끝이 YYYY-MM-DD 가 아닙니다: {!r}".format(name))
    try:
        return datetime.date.fromisoformat(tail)
    except ValueError:
        raise BuildError("받은 날이 달력에 없는 날입니다: {!r}".format(name))


def default_raw_dir(root=DEFAULT_RAW_ROOT):
    """root 아래에서 받은 날(이름 끝 날짜)이 가장 늦은 폴더. 같은 날이면 이름이 늦은 것. 없으면 None."""
    if not os.path.isdir(root):
        return None
    cands = [n for n in os.listdir(root)
             if os.path.isdir(os.path.join(root, n)) and RE_DATE.match(n[-10:])]
    if not cands:
        return None
    return os.path.join(root, max(cands, key=lambda n: (n[-10:], n)))


def one_zip(raw_dir, prefix):
    found = sorted(n for n in os.listdir(raw_dir) if n.startswith(prefix) and n.lower().endswith(".zip"))
    if len(found) != 1:
        raise BuildError("{} 로 시작하는 zip 이 정확히 1개가 아닙니다: {}".format(prefix, found))
    return os.path.join(raw_dir, found[0])


# ── 통계 읽기 ────────────────────────────────────────────────────────────────


def pick_item_files(names):
    """zip 안 이름 목록 → {칸: 파일 이름}. 부분 문자열이 정확히 1개 맞아야 한다."""
    out = {}
    for key, sub, _code in ITEMS:
        hit = [n for n in names if sub in n and n.lower().endswith(".csv")]
        if len(hit) != 1:
            raise BuildError("통계 파일 「{}」이 정확히 1개가 아닙니다: {}".format(sub, hit))
        out[key] = hit[0]
    years = {}
    for key, fn in out.items():
        m = RE_BASE_YEAR.search(os.path.basename(fn))
        if not m:
            raise BuildError("통계 파일 이름에 「_YYYY년_」이 없습니다: {!r}".format(fn))
        years[key] = int(m.group(1))
    if len(set(years.values())) != 1:
        raise BuildError("통계 파일들의 기준 연도가 서로 다릅니다: {}".format(years))
    return out, next(iter(years.values()))


def read_census(census_zip, oa_prefixes):
    """총괄 4파일 → ({칸: {집계구: 값 문자열}}, 기준 연도). 집계구 접두로 시·도를 거른다.
    값은 문자열 그대로 둔다('N/A' 판정은 걸친 집계구에서만 — oa_value)."""
    with zipfile.ZipFile(census_zip, metadata_encoding="cp949") as z:
        files, base_year = pick_item_files(z.namelist())
        data = {}
        for key, _sub, code in ITEMS:
            vals = {}
            with z.open(files[key]) as f:
                for r in csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig")):
                    if not r:
                        continue
                    if len(r) != 4:
                        raise BuildError("{} 칸 수가 4 가 아닙니다: {!r}".format(files[key], r))
                    year, oa, c, v = r
                    if c != code or not oa.startswith(oa_prefixes):
                        continue
                    if year != str(base_year):
                        raise BuildError("{} 연도 칸 {!r} ≠ 파일 이름 기준 연도 {}".format(files[key], year, base_year))
                    vals[oa] = v
            data[key] = vals
    return data, base_year, files


def oa_value(census, key, oa):
    """걸친 집계구 하나의 값(정수). 'N/A'·없음·정수 아님이면 멈춤."""
    v = census[key].get(oa)
    if v is None:
        raise BuildError("집계구 {} 의 {} 값이 통계에 없습니다".format(oa, key))
    if v == "N/A":
        raise BuildError("집계구 {} 의 {} 값이 'N/A' 입니다(총괄은 N/A 가 없어야 한다)".format(oa, key))
    if not RE_INT.match(v):
        raise BuildError("집계구 {} 의 {} 값이 0 이상 정수가 아닙니다: {!r}".format(oa, key, v))
    return int(v)


# ── 경계 읽기 ────────────────────────────────────────────────────────────────


def read_boundary(bnd_zip, oa_prefixes):
    """집계구 경계 zip(shp·shx·dbf) → (codes, geoms, 메타 dict). 메모리에서 읽는다(풀지 않는다)."""
    import shapefile  # noqa: PLC0415  (pyshp — CI 에는 없다)
    from shapely.geometry import shape  # noqa: PLC0415

    with zipfile.ZipFile(bnd_zip) as z:
        names = z.namelist()

        def one(ext):
            hit = [n for n in names if n.lower().endswith(ext)]
            if len(hit) != 1:
                raise BuildError("경계 zip 안 {} 파일이 정확히 1개가 아닙니다: {}".format(ext, hit))
            return io.BytesIO(z.read(hit[0]))

        r = shapefile.Reader(shp=one(".shp"), shx=one(".shx"), dbf=one(".dbf"), encoding="utf-8")
        fields = [f[0] for f in r.fields[1:]]          # 첫 칸은 DeletionFlag
        for need in ("BASE_DATE", "TOT_OA_CD"):
            if need not in fields:
                raise BuildError("경계 dbf 에 {} 칸이 없습니다: {}".format(need, fields))
        i_date, i_code = fields.index("BASE_DATE"), fields.index("TOT_OA_CD")
        dates = set()
        by_prefix = collections.Counter()
        codes, geoms = [], []
        n_invalid = 0
        n_total = len(r)
        for i in range(n_total):
            rec = r.record(i)
            dates.add(str(rec[i_date]))
            code = str(rec[i_code])
            by_prefix[code[:2]] += 1
            if not code.startswith(oa_prefixes):
                continue
            g = shape(r.shape(i).__geo_interface__)
            if not g.is_valid:
                n_invalid += 1
                g = g.buffer(0)
            codes.append(code)
            geoms.append(g)
    if len(dates) != 1:
        raise BuildError("경계 BASE_DATE 가 한 가지가 아닙니다: {}".format(sorted(dates)[:5]))
    d = dates.pop()
    if not re.match(r"^\d{8}$", d):
        raise BuildError("경계 BASE_DATE 꼴이 YYYYMMDD 가 아닙니다: {!r}".format(d))
    bnd_base_date = datetime.date(int(d[:4]), int(d[4:6]), int(d[6:]))
    return codes, geoms, {"n_oa_total": n_total, "by_prefix": dict(by_prefix), "n_invalid_fixed": n_invalid,
                          "bnd_base_date": bnd_base_date}


# ── 상권 도형 ────────────────────────────────────────────────────────────────


def parse_district_lines(lines, sido):
    """6칸 TSV 줄들 → 상권 dict 목록(sigungu_code 앞 두 자리 ∈ sido 만). psql 안내 두 줄·빈 줄은 건너뛴다."""
    from shapely import wkt  # noqa: PLC0415

    out = []
    for ln in lines:
        ln = ln.rstrip("\r\n")
        if not ln.strip() or ln.startswith(PSQL_NOTICES):
            continue
        p = ln.split("\t")
        if len(p) != 6 or not p[5].upper().startswith(("MULTIPOLYGON", "POLYGON")):
            raise BuildError("상권 줄 꼴이 다릅니다(6칸 · 5179 WKT): {!r}".format(ln[:120]))
        if p[3][:2] not in sido:
            continue
        g = wkt.loads(p[5])
        if not g.is_valid:
            g = g.buffer(0)
        out.append({"id": p[0], "nm": p[1], "type": p[2], "sgg": p[3], "g": g})
    return out


def fetch_district_lines(sido):
    """DB 에서 상권 도형을 읽는다(읽기만). 접속은 build_sitemap.fetch_rows 와 같은 길(PGPASSWORD · UTF-8 임시 파일)."""
    import dbx  # noqa: PLC0415  (--district-tsv 만 쓰는 시험·오프라인은 DB 설정 없이도 돈다)

    args, password = dbx.parts()
    env = dict(os.environ)
    env["PGPASSWORD"] = password  # ⚠️ 명령줄 노출 금지
    env["PGCLIENTENCODING"] = "UTF8"
    fd, path = tempfile.mkstemp(suffix=".sql", prefix="sgis_district_")
    os.close(fd)
    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(DISTRICT_SQL.format(sido=", ".join("'{}'".format(s) for s in sido)) + ";\n")
        cmd = ["psql"] + args + ["-q", "-t", "-A", "-F", "\t", "-v", "ON_ERROR_STOP=1", "-f", path]
        out = subprocess.check_output(cmd, env=env, stderr=subprocess.STDOUT)
    finally:
        os.unlink(path)
    return out.decode("utf-8").splitlines()


# ── 계산 ─────────────────────────────────────────────────────────────────────


def compute(districts, codes, geoms, census):
    """상권마다 겹침·통째·배분·하한·상한. 걸친 집계구가 0 인 상권이 있으면 멈춤."""
    from shapely.strtree import STRtree  # noqa: PLC0415

    tree = STRtree(geoms)
    oa_area = [g.area for g in geoms]
    rows = []
    for d in sorted(districts, key=lambda x: x["id"]):
        g = d["g"]
        hits = []
        for i in tree.query(g):
            a = geoms[i].intersection(g).area
            if a >= OVERLAP_MIN_M2:
                hits.append((codes[i], a, a / oa_area[i]))
        if not hits:
            raise BuildError("상권 {} {} 에 걸친 집계구가 0 개입니다(겹침 ≥ {}㎡)".format(
                d["id"], d["nm"], OVERLAP_MIN_M2))
        area = g.area
        row = {"district_id": d["id"], "district_nm": d["nm"], "district_type": d["type"],
               "sigungu_code": d["sgg"], "area_m2": round(area, 1), "n_overlap": len(hits),
               "n_full": sum(1 for _c, _a, w in hits if w >= FULL_RATIO),
               "cover_pct": round(sum(a for _c, a, _w in hits) / area * 100, 3)}
        row["n_clamped"] = 0
        for key, _sub, _code in ITEMS:
            vals = [(oa_value(census, key, c), w) for c, _a, w in hits]
            lo = sum(v for v, w in vals if w >= FULL_RATIO)
            hi = sum(v for v, _w in vals)
            alloc = round(sum(w * v for v, w in vals))
            # 통째(비율 0.99~1)인 집계구는 하한에 값 전부 · 배분엔 비율만큼 들어가 배분이 하한보다 조금 작을 수 있다
            # (2024 통계 서울 3120150 종사자 5,350 < 하한 5,351 — 대전 0건). 「값이 범위 밖」은 화면에서 모순이라 끼운다.
            clamped = min(max(alloc, lo), hi)
            row["n_clamped"] += clamped != alloc
            row[key], row[key + "_lo"], row[key + "_hi"] = clamped, lo, hi
        rows.append(row)
    return rows


def write_csv(rows, path):
    """결과 csv(utf-8 · LF · 머리줄) → (바이트 수, sha256)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow([r[c] for c in COLUMNS])
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return os.path.getsize(path), h.hexdigest()


# ── 서울 대조 ────────────────────────────────────────────────────────────────


def read_official_tsv(path):
    """서울시 상주인구 TSV(district_id \\t 거주 \\t 가구 · 빈 값 = 공표 없음) → {id: (거주|None, 가구|None)}."""
    out = {}
    with io.open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.rstrip("\r\n")
            if not ln.strip() or ln.startswith(PSQL_NOTICES):
                continue
            p = ln.split("\t")
            if len(p) != 3 or not p[0]:
                raise BuildError("공표 TSV 줄 꼴이 다릅니다(3칸): {!r}".format(ln[:80]))
            out[p[0]] = tuple(int(x) if x else None for x in p[1:])
    return out


def _q(xs, p):
    """조사반 compare_seoul.py 와 같은 분위(가까운 순위)."""
    xs = sorted(xs)
    n = len(xs)
    return xs[min(n - 1, int(p / 100 * (n - 1) + 0.5))]


def compare_seoul(rows, official):
    """서울 결과 줄 vs 공표 → (통계 dict, 대조 줄 목록). 공표 없는 상권은 빼고 수만 센다."""
    both = [r for r in rows if r["district_id"] in official and official[r["district_id"]][0] is not None]
    no_off = len(rows) - len(both)
    pairs = [(r, official[r["district_id"]][0], official[r["district_id"]][1]) for r in both]
    pos = [(r, b) for r, b, _h in pairs if b > 0]
    diffs = [(r["pop"] - b) / b for r, b in pos]
    inside = sum(1 for r, b, _h in pairs if r["pop_lo"] <= b <= r["pop_hi"])
    hh = [(r["hh"] - h) / h for r, _b, h in pairs if h]
    st = {
        "n": len(pairs), "no_official": no_off, "zero_official": len(pairs) - len(pos),
        "median_pct": round(statistics.median(diffs) * 100, 1) if diffs else None,
        "q25_pct": round(_q(diffs, 25) * 100, 1) if diffs else None,
        "q75_pct": round(_q(diffs, 75) * 100, 1) if diffs else None,
        "within30_pct": round(sum(1 for d in diffs if abs(d) <= 0.30) / len(diffs) * 100, 1) if diffs else None,
        "sum_ratio": round(sum(r["pop"] for r, _b, _h in pairs) / sum(b for _r, b, _h in pairs), 3) if pairs else None,
        "inside_n": inside,
        "inside_pct": round(inside / len(pairs) * 100, 1) if pairs else None,
        "hh_median_pct": round(statistics.median(hh) * 100, 1) if hh else None,
    }
    lines = []
    for r, b, h in pairs:
        d = round((r["pop"] - b) / b * 100, 1) if b else ""
        lines.append([r["district_id"], r["district_nm"], r["district_type"], r["area_m2"], r["n_overlap"],
                      r["n_full"], r["pop"], r["pop_lo"], r["pop_hi"], b, d, r["hh"], "" if h is None else h])
    return st, lines


COMPARE_COLUMNS = ("district_id", "district_nm", "district_type", "area_m2", "n_overlap", "n_full", "sgis_pop",
                   "sgis_pop_lo", "sgis_pop_hi", "seoul_pop", "diff_pct", "sgis_hh", "seoul_hh")


def compare_ok(st, base_year, ref=SEOUL_REF):
    """같은 기준 연도면 11-01 대조값과 ±tol 안이어야 한다. 다른 연도면 늘 참(새 판 — 참고로만 찍는다)."""
    if base_year != ref["base_year"]:
        return True
    tol = ref["tol_pp"] + 1e-9
    return (st["median_pct"] is not None and abs(st["median_pct"] - ref["median_pct"]) <= tol
            and st["inside_pct"] is not None and abs(st["inside_pct"] - ref["inside_pct"]) <= tol)


# ── 요약 ─────────────────────────────────────────────────────────────────────


def summary_lines(rows):
    n_zero = sum(1 for r in rows if r["n_full"] == 0)
    cov = [r["cover_pct"] for r in rows]
    out = ["  상권 {} · 통째 0 인 상권 {} · 덮임 {:.3f}~{:.3f}% · 걸친 집계구 가운데 {} · 범위로 끼운 칸 {}".format(
        len(rows), n_zero, min(cov), max(cov), statistics.median(r["n_overlap"] for r in rows),
        sum(r["n_clamped"] for r in rows))]
    for r in rows:
        out.append("    {} {} {}/{} 거주 {:,} [{:,}~{:,}] 가구 {:,} 종사자 {:,} [{:,}~{:,}] 덮임 {}%".format(
            r["district_id"], r["district_nm"], r["n_overlap"], r["n_full"], r["pop"], r["pop_lo"], r["pop_hi"],
            r["hh"], r["emp"], r["emp_lo"], r["emp_hi"], r["cover_pct"]))
    return out


# ── 메인 ─────────────────────────────────────────────────────────────────────


def build(raw_dir, district_lines_fn, sido=DEFAULT_SIDO, compare_tsv=None):
    """→ (결과 줄(sido 만), meta 앞부분, 서울 대조(통계, 줄) 또는 None)."""
    received_on = received_on_of(raw_dir)
    census_zip = one_zip(raw_dir, CENSUS_ZIP_PREFIX)
    bnd_zip = one_zip(raw_dir, BND_ZIP_PREFIX)
    all_sido = tuple(sido) + ((COMPARE_SIDO,) if compare_tsv and COMPARE_SIDO not in sido else ())
    prefixes = tuple(SIDO_TO_OA[s] for s in all_sido)

    t0 = time.time()
    census, base_year, files = read_census(census_zip, prefixes)
    log("  통계 {}년 · 총괄 4파일 · 집계구 {} · {:.0f}초".format(
        base_year, {k: len(v) for k, v in census.items()}, time.time() - t0))
    t1 = time.time()
    codes, geoms, bmeta = read_boundary(bnd_zip, prefixes)
    log("  경계 {:,} 중 접두 {} = {:,} · 고친 도형 {} · 기준 {} · {:.0f}초".format(
        bmeta["n_oa_total"], prefixes, len(codes), bmeta["n_invalid_fixed"], bmeta["bnd_base_date"],
        time.time() - t1))
    districts = parse_district_lines(district_lines_fn(all_sido), all_sido)
    by = collections.Counter(d["sgg"][:2] for d in districts)
    for s in all_sido:
        if not by.get(s):
            raise BuildError("시·도 {} 의 상권이 0 개입니다".format(s))
    t2 = time.time()
    rows_all = compute(districts, codes, geoms, census)
    log("  상권 {} · 겹침 계산 {:.0f}초".format(dict(by), time.time() - t2))

    rows = [r for r in rows_all if r["sigungu_code"][:2] in sido]
    meta = {
        "received_on": received_on.isoformat(), "raw_dir": os.path.basename(os.path.normpath(raw_dir)),
        "base_year": base_year, "bnd_base_date": bmeta["bnd_base_date"].isoformat(),
        "n_oa_total": bmeta["n_oa_total"],
        # 키 = 상권 쪽 시·도 코드(30) · 값 = 그 시·도 집계구 수(접두 SIDO_TO_OA — 대전 25)
        "n_oa_by_sido": {s: bmeta["by_prefix"].get(SIDO_TO_OA[s], 0) for s in sido},
        "sido": list(sido), "overlap_min_m2": OVERLAP_MIN_M2, "full_ratio": FULL_RATIO, "partial": False,
        "n_clamped": sum(r["n_clamped"] for r in rows),
        "census_files": sorted(os.path.basename(f) for f in files.values()),
    }
    cmp = None
    if compare_tsv:
        seoul = [r for r in rows_all if r["sigungu_code"][:2] == COMPARE_SIDO]
        cmp = compare_seoul(seoul, read_official_tsv(compare_tsv))
    return rows, meta, cmp


def main(argv=None):
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="대전 상권 안 인구(SGIS 집계구 면적 비율) 결과표 굽기", allow_abbrev=False)
    p.add_argument("--raw-dir", default=None, help="SGIS 받은 날 폴더(기본 = data/raw/sgis_census/ 의 가장 늦은 것)")
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    p.add_argument("--district-tsv", default=None, help="DB 대신 이 상권 TSV(6칸 · 5179 WKT)")
    p.add_argument("--compare-seoul", default=None, metavar="TSV", help="서울시 상주인구 TSV 와 대조(서울 1,650 도 계산)")
    p.add_argument("--dry-run", action="store_true", help="요약만 — 파일 쓰기 0(상권 도형 DB 읽기는 한다)")
    a = p.parse_args(argv)

    raw_dir = a.raw_dir or default_raw_dir()
    if not raw_dir or not os.path.isdir(raw_dir):
        print("실패 — SGIS 받은 날 폴더가 없습니다: {}".format(raw_dir), file=sys.stderr)
        return 1
    if a.district_tsv:
        def lines_fn(_sido):
            with io.open(a.district_tsv, encoding="utf-8") as f:
                return f.read().splitlines()
    else:
        lines_fn = fetch_district_lines

    log("=" * 74)
    log("대전 상권 안 인구 (SGIS 집계구) {}".format("(dry-run)" if a.dry_run else ""))
    log("=" * 74)
    log("  받은 날 폴더 {}".format(raw_dir))
    t0 = time.time()
    try:
        rows, meta, cmp = build(raw_dir, lines_fn, compare_tsv=a.compare_seoul)
    except (BuildError, OSError, zipfile.BadZipFile, subprocess.CalledProcessError) as e:
        print("실패 — 결과표를 쓰지 않았습니다: {}".format(e), file=sys.stderr)
        return 1
    secs = time.time() - t0
    for ln in summary_lines(rows):
        log(ln)
    log("  모두 {:.0f}초".format(secs))

    rc = 0
    if cmp:
        st, _lines = cmp
        log()
        log("서울 대조 — 거주 인구 vs 서울시 상주인구 공표값")
        log("  n={} (공표 없는 상권 {} 제외 · 공표 0 {}) · 오차 가운데 {}% · 사분위 {}~{}% · ±30% 안 {}%".format(
            st["n"], st["no_official"], st["zero_official"], st["median_pct"], st["q25_pct"], st["q75_pct"],
            st["within30_pct"]))
        log("  합계 비율 {} · 공표값이 범위 안 {}/{} = {}% · 가구 오차 가운데 {}%".format(
            st["sum_ratio"], st["inside_n"], st["n"], st["inside_pct"], st["hh_median_pct"]))
        log("  11-01 기준(통계 {}년): 가운데 {}% · 범위 안 {}% · 허용 ±{}%p".format(
            SEOUL_REF["base_year"], SEOUL_REF["median_pct"], SEOUL_REF["inside_pct"], SEOUL_REF["tol_pp"]))
        if not compare_ok(st, meta["base_year"]):
            print("서울 대조가 11-01 값과 ±{}%p 밖입니다 — 계산이 바뀌었습니다(멈춤).".format(SEOUL_REF["tol_pp"]),
                  file=sys.stderr)
            rc = 1

    if a.dry_run:
        log()
        log("--dry-run — 파일에 아무것도 쓰지 않았습니다.")
        return rc
    if rc:
        return rc

    stem = meta["received_on"].replace("-", "")
    path = os.path.join(a.out_dir, stem + ".csv")
    size, digest = write_csv(rows, path)
    meta.update({"rows": len(rows), "sha256": digest,
                 "built_at": datetime.datetime.now(KST).isoformat(timespec="seconds")})
    with io.open(os.path.join(a.out_dir, stem + ".meta.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    log()
    log("  결과표 {} · {}줄 · {:,}바이트".format(path, len(rows), size))
    if cmp:
        cpath = os.path.join(a.out_dir, stem + ".seoul_compare.csv")
        with io.open(cpath, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(COMPARE_COLUMNS)
            w.writerows(cmp[1])
        log("  서울 대조 {}".format(cpath))
    log("  다음: python scripts/collectors/load_sgis_district_pop.py --dry-run → 실적재 → post_load.py · --check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
