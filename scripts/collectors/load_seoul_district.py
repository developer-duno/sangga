# -*- coding: utf-8 -*-
"""서울시 상권분석서비스(영역-상권) SHP → `district` 표 적재.

왜 psql 경유인가 (REST 가 아니라)
---------------------------------
다른 적재기들은 Supabase REST(PostgREST)로 upsert 한다. 그런데 이 자료는 **좌표계가
EPSG:5181** 이고 우리 표는 4326 이다. REST 로는 `ST_Transform` 을 못 부른다.
그렇다고 파이썬에서 변환하려면 pyproj(PROJ 바이너리 동봉)가 필요한데 —
**우리 DB 가 이미 5181 을 알고 있다**(실측 확인). 그래서 SQL 을 만들어 `dbx.py` 로
넘기고 변환은 PostGIS 에 맡긴다. 새 바이너리 의존성 0.

⚠️ 5181 vs 5186 (이걸 틀리면 지도가 100km 밀린다)
--------------------------------------------------
둘 다 "Korea 2000 / Central Belt" 계열인데 False Northing 이 500000 / 600000 이다.
이 파일의 .prj 는 **500000** 이므로 5181 이다(2026-08-14 실측). 그래서 적재 전에
.prj 를 **매번 다시 확인**하고 다르면 멈춘다 — 포털이 조용히 좌표계를 바꿔도 잡힌다.

왜 pyshp 를 늦게 불러오나
-------------------------
필드 대응·WKT 조립 같은 판단 로직은 순수 함수라 pyshp 없이 테스트할 수 있다.
`shapefile` import 를 함수 안으로 미루면 **CI 는 pyshp 를 안 깔아도 된다**(CI 의
pip install 목록에 새 항목이 안 늘어난다).

쓰는 법
-------
    python scripts/collectors/load_seoul_district.py --dry-run   # DB 쓰기 0
    python scripts/collectors/load_seoul_district.py             # 실제 적재
    python scripts/collectors/load_seoul_district.py --sql-out /tmp/d.sql --dry-run
"""

import argparse
import glob
import io
import os
import re
import sys
import zipfile

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
DEFAULT_RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "seoul_district")

SOURCE_SRID = 5181            # .prj 실측값. 아래 assert_projection() 이 매번 재확인한다
TARGET_SRID = 4326            # district.geom 의 좌표계

# 화면이 그대로 보여줄 출처 문구(공공누리 1유형 = 출처표시 의무).
# 2026-08-14 마이그레이션이 기존 1,650행을 백필했지만 그건 **1회성**이다 — 나중에 서울
# 자료가 갱신돼 새 상권이 INSERT 되면 그 행만 출처가 비어 화면에서 출처 줄이 사라진다.
# 그래서 적재기가 행마다 값을 갖게 한다.
SOURCE_NM = "서울특별시 상권분석서비스"

# .prj 가 정말 EPSG:5181 인지 가리는 지문.
#
# ⚠️ **False Northing 하나만 보면 안 된다** (2026-08-14 적대검증에서 잡힌 구멍).
#    라이브 spatial_ref_sys 실측: 5174·5180·5181 이 **전부** y_0=500000 이다.
#    하나만 보면 아래 둘이 그대로 통과해 조용히 어긋난 지도가 된다.
#      · EPSG:5174 — 측지계가 Bessel 1841(구 지적계). 약 300m 어긋난다.
#                    구분하는 유일한 지문이 **SPHEROID** 다.
#      · EPSG:5180 — 서부원점. Central_Meridian 이 125 다(5181 은 127).
#    5186 은 y_0=600000 이라 False Northing 으로 갈린다(100km).
PRJ_SIGNATURE = (
    ("False_Northing", 500000.0, "600000 이면 EPSG:5186 — 100km 밀린다"),
    ("False_Easting", 200000.0, ""),
    ("Central_Meridian", 127.0, "125 면 서부원점(EPSG:5180) — 경도가 통째로 다르다"),
    ("Latitude_Of_Origin", 38.0, ""),
)
EXPECTED_SPHEROID = "GRS_1980"   # 5174(Bessel_1841)와 가르는 유일한 지문

# 소스가 쓰는 상권 종류 4종을 **그대로** 넣는다 (2026-08-14 결정).
# 우리 스키마 주석의 5종(역세권/근린/대학가/오피스/관광)은 자료를 보기 전 추측이었고,
# 억지로 매핑하면 '전통시장' 처럼 갈 곳 없는 종류가 생겨 정보가 날아간다.
KNOWN_TYPES = ("골목상권", "발달상권", "전통시장", "관광특구")

# DBF 필드 → 우리 컬럼. 소스가 필드명을 바꾸면 조용히 NULL 이 되지 않게 아래에서 검증한다.
REQUIRED_FIELDS = ("TRDAR_CD", "TRDAR_CD_N", "TRDAR_SE_1",
                   "SIGNGU_CD", "XCNTS_VALU", "YDNTS_VALU", "RELM_AR")

BATCH_ROWS = 100              # SQL 한 문장에 담을 상권 수 (폴리곤이 커서 잘게 쪼갠다)
COORD_FMT = "{:.3f}"          # 5181 은 미터 단위 — mm 자리까지면 충분하다


# ── 순수 함수 (pyshp·네트워크·DB 없음 — 테스트 대상) ─────────────────────────


def assert_projection(prj_text):
    """.prj 가 정말 EPSG:5181 인지 확인한다. 하나라도 어긋나면 멈춘다.

    지문 4개 + 측지계(SPHEROID)를 **함께** 본다 — 왜 그래야 하는지는 위 PRJ_SIGNATURE
    주석 참조. 어긋난 좌표계는 에러를 내지 않고 **조용히 밀린 지도**를 만들기 때문에,
    적재 전 이 관문이 유일한 방어선이다.
    """
    text = prj_text or ""
    problems = []
    for name, expected, hint in PRJ_SIGNATURE:
        m = re.search(re.escape(name) + r'",\s*(-?[0-9]+(?:\.[0-9]+)?)', text)
        if m is None:
            problems.append("{} 를 못 찾음".format(name))
            continue
        got = float(m.group(1))
        if got != expected:
            problems.append("{}={:g} (기대 {:g}){}".format(
                name, got, expected, (" — " + hint) if hint else ""))
    if EXPECTED_SPHEROID not in text:
        problems.append(
            "SPHEROID 에 {} 가 없음 — 측지계가 다르다"
            "(EPSG:5174 는 Bessel_1841 이고 약 300m 어긋난다)".format(EXPECTED_SPHEROID))
    if problems:
        raise ValueError(
            "좌표계가 EPSG:{} 가 아닙니다 — {}. 그대로 넣으면 지도가 조용히 밀립니다. "
            "사람이 .prj 를 확인해야 합니다.".format(SOURCE_SRID, " / ".join(problems)))
    return True


def sql_str(value):
    """SQL 문자열 리터럴. 작은따옴표는 두 번 써서 escape 한다."""
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def sql_num(value):
    """숫자 리터럴. 비었거나 숫자가 아니면 null."""
    if value is None or value == "":
        return "null"
    try:
        return repr(float(value))
    except (TypeError, ValueError):
        return "null"


def ring_to_wkt(ring):
    """좌표 목록 하나를 WKT 링으로. 닫혀 있지 않으면 첫 점을 붙여 닫는다."""
    pts = [(float(x), float(y)) for x, y in ring]
    if len(pts) < 4:
        raise ValueError("링의 점이 {}개뿐입니다 — 폴리곤이 될 수 없습니다.".format(len(pts)))
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return "(" + ", ".join(
        (COORD_FMT + " " + COORD_FMT).format(x, y) for x, y in pts) + ")"


def geo_to_multipolygon_wkt(geo):
    """pyshp 의 __geo_interface__(GeoJSON 모양)를 MULTIPOLYGON WKT 로 바꾼다.

    링을 겉/구멍으로 묶는 일은 pyshp 가 해 준다 — 우리가 시계방향을 직접 판정하면
    구멍이 섬이 되는 실수를 하기 쉽다. 그래서 좌표만 받아 문자열로 옮긴다.
    """
    kind = (geo or {}).get("type")
    if kind == "Polygon":
        polygons = [geo["coordinates"]]
    elif kind == "MultiPolygon":
        polygons = geo["coordinates"]
    else:
        raise ValueError("폴리곤이 아닙니다: {!r}".format(kind))
    if not polygons:
        raise ValueError("폴리곤이 비어 있습니다.")
    body = ", ".join(
        "(" + ", ".join(ring_to_wkt(r) for r in poly) + ")" for poly in polygons)
    return "MULTIPOLYGON(" + body + ")"


def record_to_row(rec, wkt):
    """DBF 한 줄 + 폴리곤 WKT → 적재용 dict. 값 정리도 여기서 한다."""
    dtype = (rec.get("TRDAR_SE_1") or "").strip()
    return {
        "district_id": (rec.get("TRDAR_CD") or "").strip(),
        "district_nm": (rec.get("TRDAR_CD_N") or "").strip() or None,
        "district_type": dtype or None,
        "sigungu_code": (rec.get("SIGNGU_CD") or "").strip() or None,
        "x_5181": rec.get("XCNTS_VALU"),
        "y_5181": rec.get("YDNTS_VALU"),
        "area_m2": rec.get("RELM_AR"),
        "wkt": wkt,
        "unknown_type": bool(dtype) and dtype not in KNOWN_TYPES,
    }


def row_to_values_sql(row):
    """한 상권을 SQL values(...) 한 줄로. 좌표 변환은 전부 PostGIS 가 한다.

    왜 st_makevalid 를 거치나 (2026-08-14 실측)
    -------------------------------------------
    1,650개 중 **6개가 Ring Self-intersection** 으로 깨져 있다(성수초등학교·중랑역 4번
    등). 깨진 폴리곤에 `st_contains` 를 쓰면 오류를 던지거나 조용히 틀린 답을 낸다 —
    "이 건물이 어느 상권인가"가 이 표의 존재 이유라 그냥 넣을 수 없다.

    st_makevalid 는 **면적을 바꾸지 않았다**(6개 전부 적재 전후 동일, ㎡ 단위까지).
    겹친 점 하나짜리 결함이라 모양은 그대로다. 이미 정상인 폴리곤에는 아무 일도 하지
    않으므로 전부에 걸어도 안전하다. collectionextract(...,3) 은 makevalid 가 드물게
    선/점을 섞어 돌려줄 때 **면(폴리곤)만** 남기는 안전핀이다.
    """
    pt = "st_setsrid(st_makepoint({}, {}), {})".format(
        sql_num(row["x_5181"]), sql_num(row["y_5181"]), SOURCE_SRID)
    wgs = "st_transform({}, {})".format(pt, TARGET_SRID)
    return (
        "({id}, {nm}, {ty}, {gu}, "
        "st_multi(st_collectionextract("
        "st_makevalid(st_transform(st_geomfromtext({wkt}, {src}), {dst})), 3)), "
        "st_y({wgs}), st_x({wgs}), {area}, {source}, now())"
    ).format(
        id=sql_str(row["district_id"]), nm=sql_str(row["district_nm"]),
        ty=sql_str(row["district_type"]), gu=sql_str(row["sigungu_code"]),
        wkt=sql_str(row["wkt"]), src=SOURCE_SRID, dst=TARGET_SRID,
        wgs=wgs, area=sql_num(row["area_m2"]), source=sql_str(SOURCE_NM))


def build_sql(rows, batch_rows=BATCH_ROWS):
    """전체 적재 SQL. 한 트랜잭션으로 묶어 **중간에 실패하면 통째로 되돌린다.**

    반쯤 들어간 상권 표는 "있는데 비어 보이는" 최악의 상태다 — 화면이 조용히 틀린
    답을 낸다. 그래서 all-or-nothing 으로 간다.
    """
    if not rows:
        raise ValueError("넣을 상권이 없습니다.")
    out = ["begin;", "set local statement_timeout = '600s';"]
    for i in range(0, len(rows), batch_rows):
        chunk = rows[i:i + batch_rows]
        out.append(
            "insert into district "
            "(district_id, district_nm, district_type, sigungu_code, geom, "
            "center_lat, center_lng, area_m2, source_nm, computed_at) values\n"
            + ",\n".join(row_to_values_sql(r) for r in chunk)
            + "\non conflict (district_id) do update set "
              "district_nm = excluded.district_nm, "
              "district_type = excluded.district_type, "
              "sigungu_code = excluded.sigungu_code, "
              "geom = excluded.geom, "
              "center_lat = excluded.center_lat, "
              "center_lng = excluded.center_lng, "
              "area_m2 = excluded.area_m2, "
              "source_nm = excluded.source_nm, "
              "computed_at = excluded.computed_at;")
    # 소스에서 **사라진** 상권은 upsert 로는 안 지워진다 — 옛 경계·옛 이름 그대로 남는데
    # 행 수는 비슷해서 아무도 눈치채지 못한다(2026-08-14 적대검증 지적).
    # 이번 판이 건드린 행은 전부 같은 now() 를 갖는다 → 그보다 오래된 computed_at 이
    # 곧 "이번 소스에 없던 상권"이다. **지우지는 않는다**(삭제 정책 미정 — 통폐합인지
    # 일시 누락인지 사람이 봐야 한다). 대신 조용히 지나가지 않게 세어서 보여준다.
    out.append(
        'select count(*) as "이번 판에 없던 상권(유령 의심 — 0 이어야 정상)" '
        "from district where computed_at < (select max(computed_at) from district);")
    out.append("commit;")
    return "\n".join(out) + "\n"


def summarize(rows):
    """사람이 눈으로 확인할 요약. 적재 전후로 같은 것을 본다."""
    by_type, by_gu = {}, {}
    for r in rows:
        by_type[r["district_type"]] = by_type.get(r["district_type"], 0) + 1
        by_gu[r["sigungu_code"]] = by_gu.get(r["sigungu_code"], 0) + 1
    return {
        "total": len(rows),
        "by_type": by_type,
        "gu_count": len(by_gu),
        "unknown_types": sorted({r["district_type"] for r in rows if r["unknown_type"]}),
        "missing_id": sum(1 for r in rows if not r["district_id"]),
    }


# ── pyshp 의존부 (여기서만 shapefile 을 부른다) ──────────────────────────────


def read_zip(zip_path):
    """shapefile zip 을 읽어 (rows, prj_text) 를 돌려준다.

    pyshp 는 여기서만 필요하다 — 위 순수 함수들은 pyshp 없이 테스트된다.
    """
    try:
        import shapefile  # noqa: PLC0415  (늦게 부르는 것이 의도다 — 파일 머리말 참조)
    except ImportError:
        raise SystemExit(
            "pyshp 가 없습니다. 설치: python -m pip install pyshp\n"
            "  (순수 파이썬이라 GDAL 같은 바이너리는 필요 없습니다.)")

    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()

        def pick(suffix):
            hit = [n for n in names if n.lower().endswith(suffix)]
            if not hit:
                raise ValueError("zip 에 {} 가 없습니다.".format(suffix))
            return hit[0]

        prj = z.read(pick(".prj")).decode("utf-8", "replace")
        assert_projection(prj)
        reader = shapefile.Reader(
            shp=io.BytesIO(z.read(pick(".shp"))),
            dbf=io.BytesIO(z.read(pick(".dbf"))),
            encoding="utf-8",          # .cpg 실측값 (cp949 가 아니다)
        )
        field_names = [f[0] for f in reader.fields[1:]]  # [0] 은 삭제 플래그
        missing = [f for f in REQUIRED_FIELDS if f not in field_names]
        if missing:
            raise ValueError(
                "DBF 에 {} 필드가 없습니다 (있는 것: {}). 소스 구조가 바뀌었습니다.".format(
                    ", ".join(missing), ", ".join(field_names)))

        rows = []
        for sr in reader.iterShapeRecords():
            rec = dict(zip(field_names, list(sr.record)))
            rows.append(record_to_row(rec, geo_to_multipolygon_wkt(sr.shape.__geo_interface__)))
    return rows, prj


def newest_zip(raw_dir):
    """가장 최근 기준월 폴더의 zip 을 고른다."""
    hits = sorted(glob.glob(os.path.join(raw_dir, "*", "*.zip")))
    if not hits:
        raise SystemExit(
            "원본이 없습니다: {}\n"
            "  먼저 받으세요: python scripts/collectors/fetch_seoul_district.py".format(raw_dir))
    return hits[-1]


def main(argv=None):
    # cp949 콘솔에서 한글·특수문자(—) 출력이 UnicodeEncodeError 로 죽지 않게 —
    # 형제 스크립트들(backup_raw.py 등)과 같은 처방(2026-08-14 사실검증이 실제
    # 트레이스백을 재현해 발견 — 미리보기를 다 찍고 끝에서 죽어 "고장"으로 오독된다).
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="서울 상권영역 SHP → district 적재")
    p.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    p.add_argument("--zip", help="특정 zip 을 직접 지정")
    p.add_argument("--dry-run", action="store_true", help="DB 에 쓰지 않는다")
    p.add_argument("--sql-out", help="만들어진 SQL 을 이 파일로 저장(검토용)")
    a = p.parse_args(argv)

    zip_path = a.zip or newest_zip(a.raw_dir)
    print("=" * 70)
    print("서울 상권영역 → district 적재")
    print("=" * 70)
    print("  원본: {}".format(zip_path))

    rows, _prj = read_zip(zip_path)
    s = summarize(rows)
    print("  상권 {:,}개 / 시군구 {}개".format(s["total"], s["gu_count"]))
    for k, v in sorted(s["by_type"].items(), key=lambda kv: -kv[1]):
        print("    {:<10} {:>5,}".format(k, v))
    if s["missing_id"]:
        print("  ⚠️ 식별자 없는 행 {}개 — 적재하면 충돌합니다.".format(s["missing_id"]), file=sys.stderr)
        return 1
    if s["unknown_types"]:
        # 멈추지는 않는다. 소스가 종류를 늘리는 건 정상적인 일이고, 그래도 경계는 쓸모 있다.
        print("  ⚠️ 처음 보는 상권 종류: {} (그대로 넣습니다)".format(", ".join(s["unknown_types"])))

    sql = build_sql(rows)
    print("  만들어진 SQL: {:,} 글자".format(len(sql)))

    if a.sql_out:
        with io.open(a.sql_out, "w", encoding="utf-8", newline="\n") as f:
            f.write(sql)
        print("  SQL 저장: {}".format(a.sql_out))

    if a.dry_run:
        print()
        print("--dry-run 지정 — DB 에 아무것도 쓰지 않았습니다.")
        return 0

    import dbx  # noqa: PLC0415  (dry-run 은 DB 설정 없이도 돌아야 한다)
    rc = dbx.run_sql(sql)
    if rc != 0:
        print("적재 실패 (psql 종료코드 {}). 트랜잭션이라 아무것도 안 들어갔습니다.".format(rc),
              file=sys.stderr)
        return rc
    print()
    print("  적재 완료.")
    print("  다음: python scripts/post_load.py   (matview 갱신 + 노출 점검)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
