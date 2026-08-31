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

# 2026-08-14 에 실제로 받은 파일의 .prj 원문 그대로 (지어낸 문자열이 아니다).
_PRJ_5181 = (
    'PROJCS["Korea_2000_Korea_Central_Belt",GEOGCS["GCS_Korea_2000",'
    'DATUM["D_Korea_2000",SPHEROID["GRS_1980",6378137.0,298.257222101]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",200000.0],'
    'PARAMETER["False_Northing",500000.0],PARAMETER["Central_Meridian",127.0],'
    'PARAMETER["Scale_Factor",1.0],PARAMETER["Latitude_Of_Origin",38.0],'
    'UNIT["Meter",1.0]]'
)
# 헷갈리는 이웃 3종. 셋 다 "겉보기엔 비슷한" 한국 좌표계다.
_PRJ_5186 = _PRJ_5181.replace('"False_Northing",500000.0', '"False_Northing",600000.0')
_PRJ_5174 = _PRJ_5181.replace("GRS_1980", "Bessel_1841").replace("Korea_2000", "Korean_1985")
_PRJ_5180 = _PRJ_5181.replace('"Central_Meridian",127.0', '"Central_Meridian",125.0')


def test_projection_accepts_5181():
    assert L.assert_projection(_PRJ_5181) is True


def test_projection_rejects_5186():
    """False Northing 600000 = EPSG:5186. 그대로 넣으면 지도가 100km 밀린다."""
    with pytest.raises(ValueError) as e:
        L.assert_projection(_PRJ_5186)
    assert "100km" in str(e.value)


def test_projection_rejects_5174_different_datum():
    """★ 2026-08-14 적대검증이 잡은 구멍.

    라이브 spatial_ref_sys 실측: **5174·5180·5181 이 전부 y_0=500000** 이다.
    False Northing 만 보던 예전 관문은 5174 를 그대로 통과시켰다 — 측지계가
    Bessel 1841 이라 약 300m 어긋난 지도가 **조용히** 만들어졌을 것이다.
    """
    with pytest.raises(ValueError) as e:
        L.assert_projection(_PRJ_5174)
    assert "SPHEROID" in str(e.value)


def test_projection_rejects_5180_west_belt():
    """서부원점(5180)은 경도가 125 다. 이것도 y_0=500000 이라 예전 관문을 통과했다."""
    with pytest.raises(ValueError) as e:
        L.assert_projection(_PRJ_5180)
    assert "Central_Meridian" in str(e.value)


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


def test_values_sql_stamps_the_source():
    """출처(공공누리 1유형 의무)를 행마다 담는다. 2026-08-14 백필은 1회성이라,
    나중에 갱신으로 새 상권이 들어오면 그 행만 출처가 비어 화면에서 줄이 사라진다."""
    sql = L.row_to_values_sql(_row())
    assert "'서울특별시 상권분석서비스'" in sql
    assert "source_nm = excluded.source_nm" in L.build_sql([_row()])


def test_build_sql_batches_rows():
    rows = [L.record_to_row(dict(_REC, TRDAR_CD=str(i)), "MULTIPOLYGON(((0 0,0 1,1 1,0 0)))")
            for i in range(250)]
    sql = L.build_sql(rows, batch_rows=100)
    assert sql.count("insert into district") == 3   # 100 + 100 + 50


def test_build_sql_counts_ghost_districts():
    """소스에서 사라진 상권은 upsert 로 안 지워진다 — 행 수도 비슷해 눈치채기 어렵다.
    지우지는 않되 **반드시 세어서 보여줘야** 조용히 지나가지 않는다(2026-08-14 지적)."""
    sql = L.build_sql([_row()])
    assert "유령 의심" in sql
    assert "computed_at < (select max(computed_at) from district" in sql
    # 세는 것은 commit 앞이어야 같은 트랜잭션 안에서 이번 판 기준으로 센다
    assert sql.index("유령 의심") < sql.rindex("commit;")


def test_build_sql_ghost_count_is_scoped_to_our_source():
    """⛔ 유령 세기를 **우리 소스로 한정**한다 (2026-08-31 감사).

    district 표에 서울뿐이던 시절의 쿼리는 전역 max(computed_at) 를 봤다. 2026-08-14 에
    소진공(대전) 37개가 들어온 뒤로는, 서울을 다시 적재할 때마다 손대지도 않은 그 37개가
    통째로 "유령 의심"으로 잡힌다 — 0 이 정상이라는 뜻이 무너지면 아무도 그 숫자를 안 본다.
    동생 load_sbiz_district.py 는 만들 때부터 자기 소스로 한정해 뒀다(그 주석이 이 오탐을
    미리 이름 대어 경고한다). 되돌리면 이 테스트가 빨간불이 된다.
    """
    sql = L.build_sql([_row()])
    ghost = sql[sql.index("유령 의심"):sql.rindex("commit;")]
    # 바깥 count 와 안쪽 max 둘 **다** 한정돼야 한다 — 하나만 걸면 여전히 어긋난다.
    assert ghost.count("source_nm = '{}'".format(L.SOURCE_NM)) == 2, ghost
    assert "소상공인" not in ghost      # 남의 소스 이름을 여기서 언급하지 않는다


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
