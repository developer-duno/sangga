# -*- coding: utf-8 -*-
"""scripts/build_sgis_district_pop.py(대전 상권 안 인구 — 결정 0045 PR⑤ · 로컬 굽기)의 시험.

작은 가짜 판을 tmp 에 만든다 — 집계구 경계 zip(pyshp Writer · EPSG 5179 꼴 좌표의 네모들) + 총괄 통계 zip(csv 다섯) +
상권 TSV(psql 안내 두 줄 + 6칸) — 그리고 겹침·통째·배분·하한·상한을 **손으로 계산한 값**과 맞댄다.
경계값: 겹침 100.0㎡ 는 들고 99.9㎡ 는 빠진다 · 겹침 비율 0.990 은 통째 · 0.980 은 아니다.
멈춤: 총괄 값 N/A · 값 없음 · 파일 둘 · 연도 어긋남 · 걸친 집계구 0 상권 · 받은 날 폴더 모양.

shapely·pyshp 가 없으면(CI) 도형이 드는 시험은 건너뛴다 — 순수 함수(받은 날·폴더 고르기·분위·대조 판정)는 늘 돈다.
"""

import csv
import io
import json
import os
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import build_sgis_district_pop as b  # noqa: E402

# ── 가짜 판 ─────────────────────────────────────────────────────────────────

# 상권(5179 평면 · 네모) — (id, 이름, 종류, 시군구, x0, y0, x1, y1)
DISTRICTS = [
    ("sbiz-1", "통째와 반", "주요상권", "30200", 0, 0, 200, 100),        # 면적 20,000
    ("sbiz-2", "경계 100㎡", "주요상권", "30200", 1000, 0, 1100, 100),
    ("sbiz-3", "통째 0.990", "주요상권", "30200", 2000, 0, 2100, 100),
    ("sbiz-4", "통째 아님 0.980", "주요상권", "30200", 3000, 0, 3100, 100),
    ("3001", "서울 하나", "골목상권", "11680", 5000, 0, 5100, 100),
    ("3002", "서울 공표 없음", "골목상권", "11680", 6000, 0, 6100, 100),
]
# 집계구 — (코드, x0, y0, x1, y1, 거주 인구)
OAS = [
    ("25000000000001", 0, 0, 100, 100, 100),           # sbiz-1 안에 통째(비율 1)
    ("25000000000002", 100, 0, 300, 100, 200),         # sbiz-1 에 반(겹침 10,000 / 20,000)
    ("25000000000003", 0, 100, 100, 200, 70),          # sbiz-1 과 변만 닿음(겹침 0)
    ("25000000000004", -10, 0, 0.999, 100, 50),        # sbiz-1 과 99.9㎡ — 빠진다
    ("25000000000006", 1099, 0, 1200, 100, 1000),      # sbiz-2 와 정확히 100.0㎡ — 든다(비율 100/10,100)
    ("25000000000008", 2000, 0, 2100, 101, 300),       # sbiz-3 — 10,000/10,100 = 0.990099 → 통째
    ("25000000000010", 3000, 0, 3100, 102, 400),       # sbiz-4 — 10,000/10,200 = 0.980392 → 통째 아님
    ("11000000000001", 5000, 0, 5100, 100, 500),
    ("11000000000002", 6000, 0, 6100, 100, 100),
    ("31000000000001", 9000, 0, 9100, 100, 999),       # 다른 시·도 — 안 읽는다
]


def _rect_wkt(x0, y0, x1, y1):
    return "POLYGON(({0} {1},{0} {3},{2} {3},{2} {1},{0} {1}))".format(x0, y0, x1, y1)


def _vals(pop):
    """항목마다 값 — 가구 = 거주 // 2 · 종사자 = 거주 × 2 · 사업체 = 거주 // 10."""
    return {"pop": pop, "hh": pop // 2, "emp": pop * 2, "est": pop // 10}


def make_census_zip(path, year="2024", override=None, extra_files=None, drop_oa=None, oas=None):
    """총괄 4파일 + 섞인 파일 하나. override = {(oa, key): 글자} · drop_oa = 그 집계구 줄을 다 뺀다."""
    oas = OAS if oas is None else oas
    names = {"pop": "2025년기준_{}년_인구총괄(총인구).csv", "hh": "2025년기준_{}년_가구총괄.csv",
             "emp": "2025년기준_{}년_산업분류별(11차_대분류)_총괄종사자수.csv",
             "est": "2025년기준_{}년_산업분류별(11차_대분류)_총괄사업체수.csv"}
    codes = {k: c for k, _s, c in b.ITEMS}
    with zipfile.ZipFile(path, "w") as z:
        for key, fn in names.items():
            buf = io.StringIO()
            w = csv.writer(buf, lineterminator="\n")
            for code, *_r, pop in oas:
                if code == drop_oa:
                    continue
                v = (override or {}).get((code, key), str(_vals(pop)[key]))
                w.writerow([year, code, codes[key], v])
                if key == "pop":
                    w.writerow([year, code, "to_in_007", "1"])        # 같은 파일의 다른 항목(남자) — 안 읽는다
            z.writestr(fn.format(year), "\ufeff" + buf.getvalue())
        z.writestr("2025년기준_{}년_인구총괄(평균나이).csv".format(year), "\ufeff2024,25000000000001,to_in_002,40.1\n")
        for fn, body in (extra_files or {}).items():
            z.writestr(fn, body)


def make_boundary_zip(path, oas=OAS, dates=None):
    import shapefile  # noqa: PLC0415

    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON, encoding="utf-8")
    w.field("BASE_DATE", "C", 8)
    w.field("ADM_CD", "C", 8)
    w.field("TOT_OA_CD", "C", 20)
    for i, oa in enumerate(oas):
        if len(oa) == 3:                    # (코드, 고리 점 목록, 값) — 고장 난 도형 시험용
            code, ring, _pop = oa
        else:
            code, x0, y0, x1, y1, _pop = oa
            # 시계 방향(바깥 고리) — shapefile 관례.
            ring = [(x0, y0), (x0, y1), (x1, y1), (x1, y0), (x0, y0)]
        w.poly([ring])
        w.record((dates or {}).get(i, "20250630"), code[:8], code)
    w.close()
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("bnd_oa_00_2025_2Q.shp", shp.getvalue())
        z.writestr("bnd_oa_00_2025_2Q.shx", shx.getvalue())
        z.writestr("bnd_oa_00_2025_2Q.dbf", dbf.getvalue())


def district_lines(rows=DISTRICTS):
    out = ["Output format is unaligned.", 'Field separator is "\t".']
    for did, nm, typ, sgg, x0, y0, x1, y1 in rows:
        out.append("\t".join([did, nm, typ, sgg, str(float((x1 - x0) * (y1 - y0))), _rect_wkt(x0, y0, x1, y1)]))
    return out


@pytest.fixture
def geo():
    pytest.importorskip("shapely")
    pytest.importorskip("shapefile")


@pytest.fixture
def raw(tmp_path, geo):
    d = tmp_path / "sgis" / "req1_2026-10-08"
    d.mkdir(parents=True)
    make_census_zip(str(d / "_census_reqdoc_1.zip"))
    make_boundary_zip(str(d / "bnd_oa_00_2025_2Q.zip"))
    return d


def lines_of(rows=DISTRICTS):
    return lambda _sido: district_lines(rows)


def by_id(rows):
    return {r["district_id"]: r for r in rows}


# ── 계산 손대조 ─────────────────────────────────────────────────────────────


class TestHandComputed:
    def test_full_and_half(self, raw):
        rows, meta, _ = b.build(str(raw), lines_of())
        r = by_id(rows)["sbiz-1"]
        # 집계구 1(비율 1 · 100) + 집계구 2(비율 0.5 · 200) — 3 은 변만 닿고 4 는 99.9㎡ 라 빠진다.
        assert (r["n_overlap"], r["n_full"]) == (2, 1)
        assert (r["pop"], r["pop_lo"], r["pop_hi"]) == (200, 100, 300)
        assert (r["hh"], r["hh_lo"], r["hh_hi"]) == (100, 50, 150)
        assert (r["emp"], r["emp_lo"], r["emp_hi"]) == (400, 200, 600)
        assert (r["est"], r["est_lo"], r["est_hi"]) == (20, 10, 30)
        assert r["cover_pct"] == 100.0 and r["area_m2"] == 20000.0

    def test_overlap_exactly_100_is_in_and_99_9_is_out(self, raw):
        rows, _meta, _ = b.build(str(raw), lines_of())
        r = by_id(rows)["sbiz-2"]
        assert (r["n_overlap"], r["n_full"]) == (1, 0)
        assert (r["pop"], r["pop_lo"], r["pop_hi"]) == (round(1000 * 100 / 10100), 0, 1000)
        assert r["cover_pct"] == 1.0
        # 99.9㎡ 쪽(집계구 4)은 sbiz-1 에 안 들었다(위 시험의 n_overlap 2) — 상수가 100 인 것도 본다.
        assert b.OVERLAP_MIN_M2 == 100.0 and b.FULL_RATIO == 0.99

    def test_ratio_0_990_is_full_and_0_980_is_not(self, raw):
        rows, meta, _ = b.build(str(raw), lines_of())
        r3, r4 = by_id(rows)["sbiz-3"], by_id(rows)["sbiz-4"]
        assert (r3["n_overlap"], r3["n_full"]) == (1, 1)
        assert (r4["n_overlap"], r4["n_full"]) == (1, 0)
        assert (r4["pop"], r4["pop_lo"], r4["pop_hi"]) == (round(400 * 10000 / 10200), 0, 400)

    def test_allocation_below_the_floor_is_clamped(self, raw):
        """통째(0.990)인 집계구는 하한에 300 전부 · 배분엔 297 — 「값 < 하한」을 내지 않고 하한으로 끼운다."""
        rows, meta, _ = b.build(str(raw), lines_of())
        r3 = by_id(rows)["sbiz-3"]
        assert round(300 * 10000 / 10100) == 297                       # 끼우기 전 값(전제)
        assert (r3["pop"], r3["pop_lo"], r3["pop_hi"]) == (300, 300, 300)
        # 거주 297·가구 148·종사자 594 는 끼웠고, 사업체는 30 × 0.990 = 29.7 → 반올림 30 = 하한이라 안 끼웠다.
        assert r3["n_clamped"] == 3 and meta["n_clamped"] == 3
        assert (r3["est"], r3["est_lo"]) == (30, 30)
        assert by_id(rows)["sbiz-1"]["n_clamped"] == 0                 # 양성 대조 — 끼울 일이 없는 상권은 0

    def test_clamp_positive_control_ratio_0_995(self, raw):
        """메인 조건 ⓑ — 비율 0.995 집계구 하나짜리 상권: 배분 995 < 하한 1,000 → 끼운 뒤 = 하한 · 로그 한 줄에 상권·항목."""
        oas = OAS + [("25000000000020", 7000, 0, 7100, 100.5, 1000)]          # 10,000 / 10,050 = 0.99502
        dists = DISTRICTS + [("sbiz-7", "0.995 하나", "주요상권", "30200", 7000, 0, 7100, 100)]
        make_boundary_zip(str(raw / "bnd_oa_00_2025_2Q.zip"), oas)
        make_census_zip(str(raw / "_census_reqdoc_1.zip"), oas=oas)
        rows, _meta, _ = b.build(str(raw), lines_of(dists))
        r = by_id(rows)["sbiz-7"]
        assert round(1000 * 10000 / 10050) == 995                             # 끼우기 전(전제)
        assert (r["n_overlap"], r["n_full"]) == (1, 1)
        assert (r["pop"], r["pop_lo"], r["pop_hi"]) == (1000, 1000, 1000)
        assert "pop 995→1000" in r["clamped"]
        line = b.clamp_line(rows, "대전")
        assert line.startswith("  범위(하한~상한)로 끼운 칸: 대전 ") and "sbiz-7 pop 995→1000" in line

    def test_cover_denominator_is_the_shapely_area_not_the_tsv_column(self, raw):
        """검사관 🟡 — TSV 넓이 칸(DB st_area · 참고)을 일부러 2배로 적어도 덮임·넓이는 WKT 의 shapely 넓이로 센다."""
        lines = district_lines()
        i = next(k for k, ln in enumerate(lines) if ln.startswith("sbiz-1\t"))
        p = lines[i].split("\t")
        p[4] = str(float(p[4]) * 2)
        lines[i] = "\t".join(p)
        rows, _meta, _ = b.build(str(raw), lambda _s: lines)
        r = by_id(rows)["sbiz-1"]
        assert r["area_m2"] == 20000.0 and r["cover_pct"] == 100.0       # 2배 칸을 썼다면 40,000 · 50%
        assert float(p[4]) == 40000.0                                    # 양성 대조 — 칸은 정말 2배로 들어갔다

    def test_broken_shapes_go_through_buffer_zero(self, raw):
        """검사관 🟡 — 자기 교차(나비 모양) 집계구 하나와 상권 하나가 buffer(0) 갈래를 지나 결과를 낸다."""
        from shapely import wkt  # noqa: PLC0415

        bow_oa = [(8000, 0), (8100, 100), (8100, 0), (8000, 100), (8000, 0)]     # 나비 모양(자기 교차)
        oas = OAS + [("25000000000030", bow_oa, 600)]
        bow_d = "POLYGON((8000 0,8100 100,8100 0,8000 100,8000 0))"
        assert not wkt.loads(bow_d).is_valid                                       # 전제: 정말 고장 난 도형
        make_boundary_zip(str(raw / "bnd_oa_00_2025_2Q.zip"), oas)
        make_census_zip(str(raw / "_census_reqdoc_1.zip"), oas=oas)
        _codes, _geoms, bmeta = b.read_boundary(str(raw / "bnd_oa_00_2025_2Q.zip"), ("25",))
        assert bmeta["n_invalid_fixed"] == 1                                       # 경계 쪽 갈래
        lines = district_lines() + ["\t".join(["sbiz-8", "나비", "주요상권", "30200", "1.0", bow_d])]
        rows, _meta, _ = b.build(str(raw), lambda _s: lines)                      # 상권 쪽 갈래(멈추지 않는다)
        r = by_id(rows)["sbiz-8"]
        assert r["n_overlap"] >= 1 and r["area_m2"] > 0 and 0 < r["cover_pct"] <= 100.5
        assert 0 <= r["pop_lo"] <= r["pop"] <= r["pop_hi"] <= 600

    def test_clamp_line_says_zero_cells(self):
        """끼운 칸이 없으면 「대전 0칸」 — 상권 이름 없이."""
        assert b.clamp_line([{"district_id": "sbiz-1", "clamped": [], "n_clamped": 0}], "대전") == \
            "  범위(하한~상한)로 끼운 칸: 대전 0칸"

    def test_only_daejeon_rows_and_meta(self, raw):
        rows, meta, _ = b.build(str(raw), lines_of())
        assert [r["district_id"] for r in rows] == ["sbiz-1", "sbiz-2", "sbiz-3", "sbiz-4"]
        assert meta["sido"] == ["30"] and meta["base_year"] == 2024
        assert meta["received_on"] == "2026-10-08" and meta["bnd_base_date"] == "2025-06-30"
        assert meta["n_oa_total"] == len(OAS)
        assert meta["n_oa_by_sido"] == {"30": 7}                        # 대전 = 집계구 접두 25
        assert meta["partial"] is False and meta["overlap_min_m2"] == 100.0 and meta["full_ratio"] == 0.99

    def test_other_province_oas_are_not_read(self, raw):
        """접두 31 집계구가 sbiz-1 과 겹치게 놓여도 대전(25)만 읽는다."""
        oas = OAS + [("31000000000099", 0, 0, 200, 100, 7777)]
        make_boundary_zip(str(raw / "bnd_oa_00_2025_2Q.zip"), oas)
        rows, _meta, _ = b.build(str(raw), lines_of())
        assert by_id(rows)["sbiz-1"]["pop_hi"] == 300


# ── 멈춤 ────────────────────────────────────────────────────────────────────


class TestStops:
    @pytest.mark.parametrize("value", ["N/A", "", "1.5", "-3"])
    def test_bad_value_of_an_overlapping_oa_stops(self, raw, value):
        make_census_zip(str(raw / "_census_reqdoc_1.zip"), override={("25000000000002", "hh"): value})
        with pytest.raises(b.BuildError) as e:
            b.build(str(raw), lines_of())
        assert "25000000000002" in str(e.value) and "hh" in str(e.value)

    def test_na_on_an_oa_that_overlaps_nothing_is_ignored(self, raw):
        """양성 대조 — 어느 상권에도 안 걸친 집계구(3 은 변만 닿음)의 N/A 는 계산에 안 들어 멈추지 않는다."""
        make_census_zip(str(raw / "_census_reqdoc_1.zip"), override={("25000000000003", "pop"): "N/A"})
        rows, _meta, _ = b.build(str(raw), lines_of())
        assert by_id(rows)["sbiz-1"]["pop"] == 200

    def test_missing_value_stops(self, raw):
        make_census_zip(str(raw / "_census_reqdoc_1.zip"), drop_oa="25000000000001")
        with pytest.raises(b.BuildError, match="25000000000001"):
            b.build(str(raw), lines_of())

    def test_two_matching_files_stop(self, raw):
        make_census_zip(str(raw / "_census_reqdoc_1.zip"), extra_files={"2025년기준_2024년_가구총괄(사본).csv": ""})
        with pytest.raises(b.BuildError, match="가구총괄"):
            b.build(str(raw), lines_of())

    def test_year_mismatch_between_names_stops(self, raw):
        make_census_zip(str(raw / "_census_reqdoc_1.zip"), year="2024",
                        extra_files={})
        # 한 파일만 다른 연도 이름 — 가구총괄을 2023 판으로 바꿔 넣는다.
        p = str(raw / "_census_reqdoc_1.zip")
        with zipfile.ZipFile(p) as z:
            items = {n: z.read(n) for n in z.namelist()}
        with zipfile.ZipFile(p, "w") as z:
            for n, data in items.items():
                z.writestr(n.replace("2024년_가구총괄", "2023년_가구총괄"), data)
        with pytest.raises(b.BuildError, match="기준 연도"):
            b.build(str(raw), lines_of())

    def test_year_column_mismatch_stops(self, raw):
        make_census_zip(str(raw / "_census_reqdoc_1.zip"), year="2024")
        p = str(raw / "_census_reqdoc_1.zip")
        with zipfile.ZipFile(p) as z:
            items = {n: z.read(n) for n in z.namelist()}
        with zipfile.ZipFile(p, "w") as z:
            for n, data in items.items():
                if "가구총괄" in n:
                    data = data.replace(b"2024,", b"2023,")
                z.writestr(n, data)
        with pytest.raises(b.BuildError, match="연도 칸"):
            b.build(str(raw), lines_of())

    def test_district_with_no_overlap_stops(self, raw):
        rows = DISTRICTS + [("sbiz-9", "빈 들", "주요상권", "30200", 8000, 8000, 8100, 8100)]
        with pytest.raises(b.BuildError, match="sbiz-9"):
            b.build(str(raw), lines_of(rows))

    def test_no_district_for_the_province_stops(self, raw):
        with pytest.raises(b.BuildError, match="상권이 0 개"):
            b.build(str(raw), lines_of([d for d in DISTRICTS if not d[3].startswith("30")]))

    def test_bad_district_line_stops(self, raw):
        bad = district_lines() + ["sbiz-x\t이름\t종류\t30200\t1.0"]
        with pytest.raises(b.BuildError, match="상권 줄 꼴"):
            b.build(str(raw), lambda _s: bad)

    def test_two_base_dates_stop(self, raw):
        make_boundary_zip(str(raw / "bnd_oa_00_2025_2Q.zip"), dates={0: "20241231"})
        with pytest.raises(b.BuildError, match="BASE_DATE"):
            b.build(str(raw), lines_of())


# ── 받은 날 · 폴더 고르기 (도형 없이) ───────────────────────────────────────


class TestReceivedOn:
    def test_tail_of_the_folder_name(self, tmp_path):
        assert b.received_on_of(str(tmp_path / "req87909_2026-10-08")).isoformat() == "2026-10-08"

    @pytest.mark.parametrize("name", ["req87909_2026-1-08", "req87909_20261008", "req87909_2026-02-30", "x"])
    def test_bad_shapes_stop(self, tmp_path, name):
        with pytest.raises(b.BuildError):
            b.received_on_of(str(tmp_path / name))

    def test_default_is_the_latest_received(self, tmp_path):
        for n in ("req99999_2026-03-01", "req10000_2026-10-08", "notes"):
            (tmp_path / n).mkdir()
        assert os.path.basename(b.default_raw_dir(str(tmp_path))) == "req10000_2026-10-08"
        assert b.default_raw_dir(str(tmp_path / "없음")) is None


# ── main · 파일 쓰기 ────────────────────────────────────────────────────────


def _tsv(tmp_path):
    p = tmp_path / "district.tsv"
    p.write_text("\n".join(district_lines()) + "\n", encoding="utf-8")
    return str(p)


class TestMain:
    def test_dry_run_writes_nothing(self, raw, tmp_path):
        out = tmp_path / "out"
        rc = b.main(["--raw-dir", str(raw), "--district-tsv", _tsv(tmp_path), "--out-dir", str(out), "--dry-run"])
        assert rc == 0 and not out.exists()

    def test_writes_csv_and_meta(self, raw, tmp_path):
        out = tmp_path / "out"
        assert b.main(["--raw-dir", str(raw), "--district-tsv", _tsv(tmp_path), "--out-dir", str(out)]) == 0
        assert sorted(os.listdir(out)) == ["20261008.csv", "20261008.meta.json"]
        with open(out / "20261008.csv", encoding="utf-8", newline="") as f:
            got = list(csv.reader(f))
        assert tuple(got[0]) == b.COLUMNS and [r[0] for r in got[1:]] == ["sbiz-1", "sbiz-2", "sbiz-3", "sbiz-4"]
        assert got[1][b.COLUMNS.index("pop")] == "200"
        meta = json.loads((out / "20261008.meta.json").read_text(encoding="utf-8"))
        import hashlib  # noqa: PLC0415
        assert meta["rows"] == 4 and meta["sha256"] == hashlib.sha256((out / "20261008.csv").read_bytes()).hexdigest()
        assert meta["built_at"].endswith("+09:00")
        assert b"\r\n" not in (out / "20261008.csv").read_bytes()

    def test_failure_writes_nothing(self, raw, tmp_path):
        make_census_zip(str(raw / "_census_reqdoc_1.zip"), override={("25000000000001", "pop"): "N/A"})
        out = tmp_path / "out"
        assert b.main(["--raw-dir", str(raw), "--district-tsv", _tsv(tmp_path), "--out-dir", str(out)]) == 1
        assert not out.exists()


# ── 서울 대조 ───────────────────────────────────────────────────────────────


def _official(tmp_path, body):
    p = tmp_path / "resident.tsv"
    p.write_text("Output format is unaligned.\nField separator is \"\t\".\n" + body, encoding="utf-8")
    return str(p)


class TestCompareSeoul:
    def test_stats_and_unpublished_districts_are_counted_not_failed(self, raw, tmp_path):
        tsv = _official(tmp_path, "3001\t520\t250\n3002\t\t\n")
        _rows, _meta, (st, lines) = b.build(str(raw), lines_of(), compare_tsv=tsv)
        assert (st["n"], st["no_official"]) == (1, 1)
        assert st["median_pct"] == round((500 - 520) / 520 * 100, 1)
        assert st["inside_n"] == 0 and st["inside_pct"] == 0.0       # 범위 500~500 밖의 520
        assert st["sum_ratio"] == round(500 / 520, 3) and st["hh_median_pct"] == 0.0
        assert [ln[0] for ln in lines] == ["3001"]

    def test_same_year_far_from_the_reference_stops(self, raw, tmp_path):
        """2024 통계인데 11-01 값(범위 안 95.5%)과 멀면 exit 1 · 대조 파일·결과표를 안 쓴다."""
        out = tmp_path / "out"
        rc = b.main(["--raw-dir", str(raw), "--district-tsv", _tsv(tmp_path), "--out-dir", str(out),
                     "--compare-seoul", _official(tmp_path, "3001\t520\t250\n")])
        assert rc == 1 and not out.exists()

    def test_other_year_only_reports(self, raw, tmp_path):
        """양성 대조 — 다른 통계 연도면 같은 차이여도 멈추지 않고 대조 파일까지 쓴다."""
        make_census_zip(str(raw / "_census_reqdoc_1.zip"), year="2025")
        p = str(raw / "_census_reqdoc_1.zip")
        with zipfile.ZipFile(p) as z:
            items = {n.replace("2025년기준_2025년", "2026년기준_2025년"): z.read(n) for n in z.namelist()}
        with zipfile.ZipFile(p, "w") as z:
            for n, data in items.items():
                z.writestr(n, data)
        out = tmp_path / "out"
        rc = b.main(["--raw-dir", str(raw), "--district-tsv", _tsv(tmp_path), "--out-dir", str(out),
                     "--compare-seoul", _official(tmp_path, "3001\t520\t250\n")])
        assert rc == 0
        assert sorted(os.listdir(out)) == ["20261008.csv", "20261008.meta.json", "20261008.seoul_compare.csv"]

    def test_compare_ok_tolerance(self):
        ref = b.SEOUL_REF
        near = {"median_pct": ref["median_pct"] + 0.1, "inside_pct": ref["inside_pct"] - 0.1}
        far = {"median_pct": ref["median_pct"] + 0.2, "inside_pct": ref["inside_pct"]}
        assert b.compare_ok(near, 2024) and not b.compare_ok(far, 2024) and b.compare_ok(far, 2025)
