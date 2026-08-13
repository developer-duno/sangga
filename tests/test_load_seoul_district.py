# -*- coding: utf-8 -*-
"""
scripts/collectors/load_seoul_district.py 단위 테스트

pyshp·네트워크·DB 없이 순수 로직만 검증한다:
  1. assert_projection      — ★ 5181 vs 5186 (틀리면 지도가 100km 밀린다)
  2. sql_str / sql_num      — 따옴표 escape, 숫자 아닌 값은 null
  3. ring_to_wkt            — 안 닫힌 링 닫기, 점이 모자라면 거부
  4. geo_to_multipolygon_wkt— Polygon·MultiPolygon 둘 다 MULTIPOLYGON 으로
  5. record_to_row          — DBF 필드 → 우리 컬럼, 처음 보는 종류 표시
  6. row_to_values_sql      — ★ st_makevalid 가 빠지지 않았나 (깨진 폴리곤 6개 대비)
  7. build_sql              — 트랜잭션으로 감쌌나, 배치로 쪼갰나, upsert 인가
  8. pyshp 늦은 import      — CI 가 pyshp 없이도 돌아야 한다

conftest.py를 새로 만들지 않기 위해 sys.path 조작은 이 파일 안에서만 한다.
"""

import io
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COLLECTORS_DIR = os.path.join(_ROOT, "scripts", "collectors")
if _COLLECTORS_DIR not in sys.path:
    sys.path.insert(0, _COLLECTORS_DIR)

import load_seoul_district as L  # noqa: E402


# ── 1. 좌표계 관문 (이 프로젝트에서 가장 비싼 실수를 막는 자리) ───────────────

_PRJ_5181 = ('PROJCS["Korea_2000_Korea_Central_Belt",'
             'PARAMETER["False_Easting",200000.0],'
             'PARAMETER["False_Northing",500000.0]]')
_PRJ_5186 = _PRJ_5181.replace("500000.0", "600000.0")


def test_projection_accepts_5181():
    assert L.assert_projection(_PRJ_5181) is True


def test_projection_rejects_5186():
    """False Northing 600000 = EPSG:5186. 그대로 넣으면 지도가 100km 밀린다."""
    with pytest.raises(ValueError) as e:
        L.assert_projection(_PRJ_5186)
    assert "100km" in str(e.value)


def test_projection_rejects_missing():
    """포털이 .prj 를 빼거나 형식을 바꾸면 조용히 넘어가지 않는다."""
    with pytest.raises(ValueError):
        L.assert_projection("")


# ── 2. SQL 리터럴 ─────────────────────────────────────────────────────────────


def test_sql_str_escapes_single_quote():
    """상권 이름에 작은따옴표가 섞이면 SQL 이 깨진다 — 실제로 있을 수 있는 이름이다."""
    assert L.sql_str("Joe's 상가") == "'Joe''s 상가'"


def test_sql_str_none_becomes_null():
    assert L.sql_str(None) == "null"


@pytest.mark.parametrize("raw,expected", [
    ("149264", "149264.0"),
    (12.5, "12.5"),
    ("", "null"),
    (None, "null"),
    ("숫자아님", "null"),
])
def test_sql_num(raw, expected):
    assert L.sql_num(raw) == expected


# ── 3~4. 폴리곤 → WKT ─────────────────────────────────────────────────────────

_SQUARE = [(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)]
_OPEN_SQUARE = [(0, 0), (0, 10), (10, 10), (10, 0)]        # 마지막 점이 첫 점과 다름


def test_ring_closes_open_ring():
    wkt = L.ring_to_wkt(_OPEN_SQUARE)
    assert wkt.startswith("(0.000 0.000")
    assert wkt.endswith("0.000 0.000)")          # 첫 점으로 닫혔다
    assert wkt.count(",") == 4                    # 4점 + 닫는 점 = 5개


def test_ring_rejects_too_few_points():
    with pytest.raises(ValueError):
        L.ring_to_wkt([(0, 0), (1, 1), (0, 0)])   # 3점으로는 면이 안 된다


def test_polygon_becomes_multipolygon():
    wkt = L.geo_to_multipolygon_wkt({"type": "Polygon", "coordinates": [_SQUARE]})
    assert wkt.startswith("MULTIPOLYGON(((")


def test_multipolygon_keeps_all_parts():
    shifted = [(x + 100, y) for x, y in _SQUARE]
    wkt = L.geo_to_multipolygon_wkt(
        {"type": "MultiPolygon", "coordinates": [[_SQUARE], [shifted]]})
    assert wkt.count("((") == 2                   # 섬 두 개가 모두 살아 있다


def test_polygon_with_hole_keeps_hole():
    hole = [(2, 2), (2, 4), (4, 4), (4, 2), (2, 2)]
    wkt = L.geo_to_multipolygon_wkt({"type": "Polygon", "coordinates": [_SQUARE, hole]})
    assert wkt.count("(2.000 2.000") == 1         # 구멍이 섬으로 바뀌지 않았다


def test_rejects_non_polygon():
    with pytest.raises(ValueError):
        L.geo_to_multipolygon_wkt({"type": "Point", "coordinates": [0, 0]})


# ── 5. DBF 한 줄 → 우리 컬럼 ─────────────────────────────────────────────────

_REC = {
    "TRDAR_CD": "3110008 ", "TRDAR_CD_N": " 배화여자대학교 ", "TRDAR_SE_1": "골목상권",
    "SIGNGU_CD": "11110", "XCNTS_VALU": "197093", "YDNTS_VALU": "453418",
    "RELM_AR": "149264",
}


def test_record_maps_and_trims():
    r = L.record_to_row(_REC, "MULTIPOLYGON(((0 0,0 1,1 1,0 0)))")
    assert r["district_id"] == "3110008"           # 앞뒤 공백 제거
    assert r["district_nm"] == "배화여자대학교"
    assert r["district_type"] == "골목상권"
    assert r["sigungu_code"] == "11110"            # 우리 char(5) 와 같은 형식
    assert r["unknown_type"] is False


def test_record_flags_unknown_type():
    """소스가 종류를 늘려도 멈추지는 않되, 사람이 알아채게 표시한다."""
    r = L.record_to_row(dict(_REC, TRDAR_SE_1="신설상권"), "x")
    assert r["unknown_type"] is True


def test_record_blank_name_becomes_none():
    r = L.record_to_row(dict(_REC, TRDAR_CD_N="   "), "x")
    assert r["district_nm"] is None


# ── 6. values 한 줄 ───────────────────────────────────────────────────────────


def _row():
    return L.record_to_row(_REC, "MULTIPOLYGON(((0 0,0 1,1 1,0 0)))")


def test_values_sql_repairs_broken_polygons():
    """1,650개 중 6개가 Ring Self-intersection 으로 깨져 있었다(2026-08-14 실측).
    깨진 채 넣으면 st_contains 가 오류를 던지거나 조용히 틀린 답을 낸다."""
    sql = L.row_to_values_sql(_row())
    assert "st_makevalid" in sql
    assert "st_collectionextract" in sql          # 면만 남기는 안전핀


def test_values_sql_transforms_from_source_to_target_srid():
    sql = L.row_to_values_sql(_row())
    assert "st_geomfromtext('MULTIPOLYGON(((0 0,0 1,1 1,0 0)))', 5181)" in sql
    assert ", 4326)" in sql
    assert "st_multi(" in sql                     # 컬럼이 MultiPolygon 을 요구한다


def test_values_sql_center_uses_source_srid_too():
    """중심좌표도 5181 이다 — 하나만 변환하면 경계와 중심이 100km 떨어진다."""
    sql = L.row_to_values_sql(_row())
    assert "st_makepoint(197093.0, 453418.0), 5181" in sql


# ── 7. 전체 SQL ───────────────────────────────────────────────────────────────


def test_build_sql_is_one_transaction():
    """반쯤 들어간 상권 표는 '있는데 비어 보이는' 최악의 상태다."""
    sql = L.build_sql([_row()])
    assert sql.startswith("begin;")
    assert sql.rstrip().endswith("commit;")


def test_build_sql_upserts_not_duplicates():
    sql = L.build_sql([_row()])
    assert "on conflict (district_id) do update set" in sql


def test_build_sql_batches_rows():
    rows = [L.record_to_row(dict(_REC, TRDAR_CD=str(i)), "MULTIPOLYGON(((0 0,0 1,1 1,0 0)))")
            for i in range(250)]
    sql = L.build_sql(rows, batch_rows=100)
    assert sql.count("insert into district") == 3   # 100 + 100 + 50


def test_build_sql_refuses_empty():
    """빈 목록을 조용히 성공 처리하면 '적재했다'고 착각한다."""
    with pytest.raises(ValueError):
        L.build_sql([])


def test_summarize_counts_by_type_and_gu():
    rows = [_row(), L.record_to_row(dict(_REC, TRDAR_CD="2", SIGNGU_CD="11140",
                                         TRDAR_SE_1="전통시장"), "x")]
    s = L.summarize(rows)
    assert s["total"] == 2
    assert s["gu_count"] == 2
    assert s["by_type"] == {"골목상권": 1, "전통시장": 1}


# ── 8. pyshp 는 늦게 부른다 (CI 가 pyshp 없이도 돌아야 한다) ─────────────────


def test_shapefile_is_imported_lazily():
    """`import shapefile` 이 파일 맨 위로 올라가면 CI 의 pip 목록에 pyshp 를 넣어야
    하고, 넣는 걸 잊으면 테스트가 통째로 수집 단계에서 죽는다. 들여쓰기 = 함수 안."""
    src = io.open(os.path.join(_COLLECTORS_DIR, "load_seoul_district.py"),
                  encoding="utf-8").read()
    hits = [ln for ln in src.splitlines() if ln.rstrip().endswith("import shapefile")
            or ln.strip().startswith("import shapefile")]
    assert hits, "import shapefile 을 못 찾았습니다"
    for ln in hits:
        assert ln.startswith(" "), "모듈 최상단에서 shapefile 을 부르면 안 됩니다: {!r}".format(ln)


def test_known_types_match_the_source():
    """소스 4종(2026-08-14 실측). 우리 스키마 주석의 5종으로 억지 매핑하지 않는다."""
    assert L.KNOWN_TYPES == ("골목상권", "발달상권", "전통시장", "관광특구")
