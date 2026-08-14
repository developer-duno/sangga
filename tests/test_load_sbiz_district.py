# -*- coding: utf-8 -*-
"""
scripts/collectors/load_sbiz_district.py 단위 테스트

DB 없이 검증한다:
  1. 좌표 관문         — ★ 경위도 뒤바뀜·투영좌표 유입을 잡는다 (하나라도 벗어나면 전체 중단)
  2. 링 파싱           — ★ 한 칸에 링이 여러 개다(전국 36%). 점 부족·형식 오류는 안 건너뛴다
  3. 상권좌표수 대조   — ★ 큰 칸이 잘려도 에러가 안 난다. 전 링 합계로 잡는다
  4. record_to_row     — 접두사·공백 붙은 유형구분·char(5) 잘림 방지
  5. SQL 조립          — st_node·st_makevalid, WKT 를 한 번만 싣기, upsert, source_nm
  6. build_sql         — 한 트랜잭션, 배치, ★ 면이 안 만들어지면 **관문이 되돌리나**,
                         ★ 유령 감지는 **정보**로 남고 **우리 소스로만** 한정되나
  7. read_csv          — cp949, 13만 자 넘는 칸, 시도 필터

conftest.py를 새로 만들지 않기 위해 sys.path 조작은 이 파일 안에서만 한다.
"""

import csv
import io
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COLLECTORS_DIR = os.path.join(_ROOT, "scripts", "collectors")
if _COLLECTORS_DIR not in sys.path:
    sys.path.insert(0, _COLLECTORS_DIR)

import load_sbiz_district as L  # noqa: E402


# ── 1. ★ 좌표 관문 ───────────────────────────────────────────────────────────


def test_korea_point_accepts_daejeon():
    assert L.assert_korea_point(127.3845, 36.3504, "대전시청") is True


def test_korea_point_rejects_swapped_lng_lat():
    """★ 가장 흔한 사고. 위도(36.35)가 경도 자리에 오면 한국 상자를 벗어난다."""
    with pytest.raises(ValueError) as e:
        L.assert_korea_point(36.3504, 127.3845, "3행 2번째 점")
    assert "3행 2번째 점" in str(e.value)          # 어디서 났는지 말해 준다
    assert "뒤바뀌" in str(e.value)


def test_korea_point_rejects_projected_meters():
    """5181 같은 투영좌표(미터, 수십만)가 섞이면 값 자체가 상자 밖이다."""
    with pytest.raises(ValueError):
        L.assert_korea_point(197093.0, 453418.0, "x")


def test_korea_point_rejects_japan():
    """경도만 조금 벗어나도 잡아야 한다(대마도 근처)."""
    with pytest.raises(ValueError):
        L.assert_korea_point(133.5, 34.5, "x")


# ── 2. 링 파싱 ────────────────────────────────────────────────────────────────

_RING_TEXT = "127.400,36.350|127.410,36.350|127.410,36.340"


def test_parse_ring_reads_points_as_written():
    pts = L.parse_ring(_RING_TEXT, "x")
    assert pts == [(127.4, 36.35), (127.41, 36.35), (127.41, 36.34)]


def test_parse_ring_ignores_trailing_separator():
    """끝에 붙은 '|' 는 좌표가 아니다 — 그것 때문에 멈추면 안 된다."""
    assert len(L.parse_ring(_RING_TEXT + "|", "x")) == 3


def test_parse_ring_rejects_too_few_points():
    with pytest.raises(ValueError):
        L.parse_ring("127.4,36.35|127.41,36.35", "x")


def test_parse_ring_rejects_broken_token():
    with pytest.raises(ValueError) as e:
        L.parse_ring("127.4,36.35|127.41|127.41,36.34", "7행")
    assert "7행" in str(e.value)


def test_parse_ring_rejects_non_numeric():
    with pytest.raises(ValueError):
        L.parse_ring("127.4,36.35|가,나|127.41,36.34", "x")


def test_parse_ring_rejects_empty():
    with pytest.raises(ValueError):
        L.parse_ring("   ", "x")


def test_parse_ring_stops_the_whole_row_on_one_bad_point():
    """★ 나쁜 점 하나를 건너뛰고 나머지로 폴리곤을 만들면 **모양이 다른 상권**이 된다."""
    with pytest.raises(ValueError):
        L.parse_ring("127.4,36.35|999.9,36.35|127.41,36.34", "x")


def test_close_ring_closes_only_when_needed():
    pts = [(1.0, 1.0), (2.0, 1.0), (2.0, 2.0)]
    assert L.close_ring(pts)[-1] == (1.0, 1.0)
    assert len(L.close_ring(pts)) == 4
    already = pts + [(1.0, 1.0)]
    assert L.close_ring(already) == already        # 이미 닫힌 링에 점을 또 붙이지 않는다


# ── 3. ★ 상권좌표수 대조 (잘린 칸을 잡는 유일한 방법) ────────────────────────


def test_point_count_matches():
    assert L.assert_point_count("3", 3, "x") is True


def test_point_count_catches_truncated_field():
    with pytest.raises(ValueError) as e:
        L.assert_point_count("1200", 3, "9행")
    assert "잘렸을" in str(e.value)


def test_point_count_skips_when_source_is_silent():
    """소스가 개수를 안 적어 줬으면 대조할 것이 없다 — 그렇다고 멈추지는 않는다."""
    assert L.assert_point_count("", 3, "x") is True


def test_point_count_uses_source_count_not_closed_count():
    """우리가 링을 닫으며 더한 점은 세지 않는다 — 안 그러면 정상 자료가 전부 실패한다."""
    wkt, rings = L.coords_to_linework_wkt(_RING_TEXT, "3", "x")
    assert wkt.startswith("MULTILINESTRING((")
    assert rings == 1


def test_already_closed_source_ring_also_passes():
    """실측: 소스의 링 2,043개가 **전부 이미 닫혀** 있다. 그때 점을 또 붙이면 안 된다."""
    closed = _RING_TEXT + "|127.400,36.350"
    wkt, _ = L.coords_to_linework_wkt(closed, "4", "x")
    assert wkt.count("127.4000000 36.3500000") == 2      # 첫 점 = 끝 점, 딱 두 번


# ── 2-b. ★ 한 칸에 링이 여러 개 (전국 1,227행 중 440행 = 36%) ────────────────

# 실측 형태: `…,36.298)|(127.338,…` — 링 사이에 괄호가 맞대어 있다.
_RING2 = "127.500,36.450|127.510,36.450|127.510,36.440"
_TWO_RINGS = _RING_TEXT + ")|(" + _RING2


def test_split_rings_finds_both_rings():
    """★ 이 분리가 없으면 float('36.350)') 에서 죽는다 — 첫 판이 실제로 그랬다."""
    assert len(L.split_rings(_TWO_RINGS, "x")) == 2


def test_split_rings_strips_leading_and_trailing_parens():
    """파일에 따라 맨 앞 '(' 와 맨 뒤 ')' 가 남아 있을 수 있다."""
    rings = L.split_rings("(" + _TWO_RINGS + ")", "x")
    assert rings[0].startswith("127.400")
    assert rings[1].endswith("36.440")


def test_multi_ring_becomes_multilinestring_with_both_rings():
    wkt, rings = L.coords_to_linework_wkt(_TWO_RINGS, "6", "x")
    assert rings == 2
    assert wkt.startswith("MULTILINESTRING((")
    assert wkt.count("(127.") == 2                        # 링 두 개가 모두 살아 있다
    assert "127.5000000 36.4500000" in wkt                # 두 번째 링을 안 버렸다


def test_multi_ring_point_count_is_the_sum_of_all_rings():
    """★ 합계로 세지 않으면 링이 여럿인 440행이 전부 '잘렸다'며 실패한다."""
    with pytest.raises(ValueError):
        L.coords_to_linework_wkt(_TWO_RINGS, "3", "x")     # 첫 링만 센 값
    assert L.coords_to_linework_wkt(_TWO_RINGS, "6", "x")[1] == 2


def test_multi_ring_checks_every_ring_against_the_korea_box():
    """두 번째 링의 나쁜 점도 잡아야 한다 — 첫 링만 보면 관문에 구멍이 생긴다."""
    with pytest.raises(ValueError) as e:
        L.coords_to_linework_wkt(_RING_TEXT + ")|(127.5,36.45|999.9,36.45|127.51,36.44)",
                                 "6", "3행")
    assert "2번째 링" in str(e.value)


def test_multi_ring_rejects_a_ring_with_too_few_points():
    """링별로 3점 이상이어야 한다. 조각 하나가 부실하면 그 상권 전체를 멈춘다."""
    with pytest.raises(ValueError):
        L.coords_to_linework_wkt(_RING_TEXT + ")|(127.5,36.45|127.51,36.45)", "5", "x")


def test_we_do_not_decide_which_ring_is_a_hole():
    """★ 소스가 겉/구멍을 안 알려준다 — 우리가 정하면 그게 숨은 판단이 된다.
    그래서 MULTIPOLYGON 을 조립하지 않고 선만 내보내 st_buildarea 에 맡긴다."""
    wkt, _ = L.coords_to_linework_wkt(_TWO_RINGS, "6", "x")
    assert "POLYGON" not in wkt


# ── 4. CSV 한 줄 → 우리 컬럼 ─────────────────────────────────────────────────

_REC = {
    "상권번호": " 30001 ", "상권명": " 은행동 ", "유형구분": "주요상권 ",
    "시도코드": "30", "시도명": "대전", "시군구코드": "30110", "시군구명": "동구",
    "상권좌표수": "3", "상권좌표": _RING_TEXT, "데이터기준일자": "2024-01-01",
}


def test_record_prefixes_id_to_avoid_collision():
    """★ 서울 자료의 상권코드와 겹치면 upsert 가 남의 상권을 덮어쓴다(조용한 오염)."""
    r = L.record_to_row(_REC, "2행")
    assert r["district_id"] == "sbiz-30001"


def test_record_trims_type_trailing_space():
    """실측: 유형구분 값이 '주요상권 ' 로 뒤에 공백이 붙어 온다."""
    assert L.record_to_row(_REC, "2행")["district_type"] == "주요상권"


def test_record_trims_name():
    assert L.record_to_row(_REC, "2행")["district_nm"] == "은행동"


def test_record_refuses_non_five_digit_sigungu():
    """district.sigungu_code 는 char(5) — 더 길면 말없이 잘려 엉뚱한 시군구가 된다."""
    with pytest.raises(ValueError) as e:
        L.record_to_row(dict(_REC, 시군구코드="3011000000"), "2행")
    assert "char(5)" in str(e.value)


def test_record_refuses_missing_id():
    with pytest.raises(ValueError):
        L.record_to_row(dict(_REC, 상권번호="  "), "2행")


# ── 5. SQL 한 줄 ──────────────────────────────────────────────────────────────


def _row():
    return L.record_to_row(_REC, "2행")


def test_insert_repairs_broken_polygons():
    """깨진 폴리곤에 st_contains 를 쓰면 오류를 던지거나 조용히 틀린 답을 낸다."""
    sql = L.build_insert([_row()])
    assert "st_makevalid" in sql
    assert "st_collectionextract" in sql
    assert "st_multi(" in sql                      # 컬럼이 MultiPolygon 을 요구한다


def test_insert_lets_postgis_decide_holes():
    """★ 겉/구멍 판정을 st_buildarea(even-odd)에 맡긴다. 이게 빠지면 선이 그대로
    들어가 collectionextract(…,3) 이 **빈 면**을 내고 상권이 통째로 사라진다."""
    sql = L.build_insert([_row()])
    assert "st_buildarea(" in sql
    assert "MULTILINESTRING" in sql                # 넘기는 것은 면이 아니라 선이다


def test_insert_nodes_the_linework_before_building_areas():
    """★ 자기끼리 꼬인 링(나비넥타이)을 그대로 넘기면 st_buildarea 가 오류가 아니라
    **NULL** 을 돌려준다 — 그 상권이 에러 한 줄 없이 사라진다(2026-08-14 라이브 실측).
    st_makevalid 는 선에 무력해 순서를 바꿔도 소용없고, st_node 로 교차점에서 잘라야 한다."""
    sql = L.build_insert([_row()])
    # st_node 는 st_buildarea 의 **안쪽**(= 먼저 도는 자리)에 있어야 한다. 바깥에 두면
    # 이미 NULL 이 나온 뒤라 손댈 것이 없다. 글자 순서로는 안쪽이 뒤에 온다.
    assert "st_buildarea(st_node(st_geomfromtext(" in sql


def test_insert_keeps_source_srid_4326():
    """소스가 경위도라 변환이 없다 — 여기에 5181 이 끼면 지도가 통째로 어긋난다."""
    sql = L.build_insert([_row()])
    assert "st_geomfromtext(v.wkt::text, 4326)" in sql
    assert "5181" not in sql


def test_insert_carries_the_wkt_only_once():
    """★ WKT 한 칸이 13만 자다. 식을 자리마다 되풀이하면 SQL 이 몇 배로 부푼다."""
    sql = L.build_insert([_row()])
    assert sql.count("127.4000000 36.3500000") == 2   # 링 안의 첫 점·닫는 점, 그게 전부


def test_insert_computes_area_and_center_in_sql():
    """CSV 에는 면적·중심 칸이 없다 — 서버가 계산해야 한다."""
    sql = L.build_insert([_row()])
    assert "st_area(g.geom::geography)" in sql
    assert "st_centroid(g.geom)" in sql
    assert "st_y(c.pt)" in sql and "st_x(c.pt)" in sql


def test_insert_stamps_the_source():
    """출처를 행마다 담아야 화면 문구가 소스를 따라간다(2026-08-14)."""
    sql = L.build_insert([_row()])
    assert "'소상공인시장진흥공단'" in sql
    assert "source_nm = excluded.source_nm" in sql


def test_insert_upserts_not_duplicates():
    assert "on conflict (district_id) do update set" in L.build_insert([_row()])


# ── 6. 전체 SQL ───────────────────────────────────────────────────────────────


def test_build_sql_is_one_transaction():
    sql = L.build_sql([_row()])
    assert sql.startswith("begin;")
    assert sql.rstrip().endswith("commit;")


def test_build_sql_batches_rows():
    rows = [L.record_to_row(dict(_REC, 상권번호=str(i)), "x") for i in range(250)]
    sql = L.build_sql(rows, batch_rows=100)
    assert sql.count("insert into district") == 3


def test_ghost_check_is_scoped_to_our_source():
    """★ 서울 로더의 전역 유령 감지를 그대로 베끼면, 대전을 넣는 순간 서울 1,650개가
    전부 '유령'으로 잡힌다(오탐). 우리 접두사 안에서만 세야 한다."""
    sql = L.build_sql([_row()])
    assert "유령 의심" in sql
    # 유령 감지 문장 하나만 떼어 본다 (다른 점검문에도 sbiz-% 가 나오므로 전체 개수로 세면
    # 점검을 하나 더할 때마다 이 가드가 헛경보를 낸다).
    ghost = next(line for line in sql.splitlines() if "유령 의심" in line)
    assert ghost.count("like 'sbiz-%'") == 2        # 세는 쪽·기준 시각 쪽 모두 한정
    assert "from district where computed_at <" not in sql   # 전역 비교가 아니다
    assert sql.index("유령 의심") < sql.rindex("commit;")


def test_build_sql_blocks_commit_when_an_area_failed():
    """★ st_buildarea 가 면을 못 만들면 geom 이 NULL 로 들어간다 — 에러가 아니라
    **보이지 않는 상권**이 된다(행 수는 맞아서 아무도 모른다).

    세기만 해서는 못 막는다: psql 은 select 가 몇을 돌려주든 종료코드 0 이라 그대로
    commit 된다. do 블록에서 예외를 던져야 ON_ERROR_STOP 이 걸려 통째로 되돌아간다."""
    sql = L.build_sql([_row()])
    assert "면이 안 만들어진 상권" in sql
    assert "st_isempty(geom)" in sql
    assert "do $$" in sql
    assert "raise exception" in sql
    assert sql.index("raise exception") < sql.rindex("commit;")
    # 관문도 우리 소스 안에서만 센다 — 서울 자료의 결함까지 끌어와 대전 적재를 막으면 안 된다.
    gate = sql[sql.index("do $$"):sql.index("end $$;")]
    assert "like 'sbiz-%'" in gate


def test_ghost_check_stays_informational_not_a_gate():
    """★ 하나는 관문, 하나는 정보다. 유령(소스에서 사라진 상권)은 통폐합인지 일시
    누락인지 자료를 봐야 알 수 있어 기계가 정할 수 없다 — 막으면 정상적인 통폐합
    때마다 적재가 통째로 실패한다."""
    sql = L.build_sql([_row()])
    ghost = next(line for line in sql.splitlines() if "유령 의심" in line)
    assert ghost.lstrip().startswith("select count(*)")
    assert "raise" not in ghost


def test_build_sql_names_duplicate_ids():
    """같은 식별자가 한 문장에 두 번 있으면 PostgreSQL 이 트랜잭션째 죽는다.
    그 메시지로는 원인을 못 찾으니 어느 상권인지 미리 대고 멈춘다."""
    with pytest.raises(ValueError) as e:
        L.build_sql([_row(), _row()])
    assert "sbiz-30001" in str(e.value)


def test_build_sql_refuses_empty():
    """빈 목록을 조용히 성공 처리하면 '적재했다'고 착각한다."""
    with pytest.raises(ValueError):
        L.build_sql([])


def test_sql_str_escapes_single_quote():
    assert L.sql_str("Joe's 상가") == "'Joe''s 상가'"


def test_summarize_counts_by_type_and_gu():
    rows = [_row(), L.record_to_row(dict(_REC, 상권번호="2", 시군구코드="30170"), "x")]
    s = L.summarize(rows)
    assert s["total"] == 2
    assert s["by_gu"] == {"30110": 1, "30170": 1}


# ── 7. 파일 읽기 (cp949 · 큰 칸 · 시도 필터) ─────────────────────────────────

_HEADER = ["상권번호", "상권명", "유형구분", "시도코드", "시도명",
           "시군구코드", "시군구명", "상권좌표수", "상권좌표", "데이터기준일자"]


def _big_ring(n=8000):
    """13만 자를 넘기는 좌표 칸을 만든다 (csv 기본 상한 131,072 를 넘겨야 한다)."""
    pts = ["{:.6f},{:.6f}".format(127.3 + i * 1e-6, 36.3 + i * 1e-6) for i in range(n)]
    return "|".join(pts)


def _write_csv(path, rows):
    with io.open(path, "w", encoding=L.ENCODING, newline="") as f:
        w = csv.writer(f)
        w.writerow(_HEADER)
        for r in rows:
            w.writerow(r)


def _row_values(code="30001", sido="30", sigungu="30110", coords=_RING_TEXT, cnt="3"):
    return [code, "은행동", "주요상권 ", sido, "대전", sigungu, "동구",
            cnt, coords, "2024-01-01"]


def test_read_csv_defaults_to_daejeon(tmp_path):
    """서울은 서울시 자료가 정본이라 기본값이 대전(30)이다."""
    path = str(tmp_path / "sbiz.csv")
    _write_csv(path, [_row_values(), _row_values(code="11001", sido="11", sigungu="11680")])
    rows = L.read_csv(path)
    assert [r["district_id"] for r in rows] == ["sbiz-30001"]


def test_read_csv_can_take_another_sido(tmp_path):
    path = str(tmp_path / "sbiz.csv")
    _write_csv(path, [_row_values(), _row_values(code="27001", sido="27", sigungu="27110")])
    assert len(L.read_csv(path, sido_code="27")) == 1


def test_seoul_is_refused_by_the_code_not_by_memory(tmp_path):
    """★ 서울을 이 소스로 넣으면 상권 정본이 둘이 된다(결정 0009 §1-②).
    "넣지 말자"를 사람이 기억하는 방식은 몇 달 뒤 전국을 열 때 조용히 깨진다."""
    path = str(tmp_path / "sbiz.csv")
    _write_csv(path, [_row_values(code="11001", sido="11", sigungu="11680")])
    with pytest.raises(ValueError) as e:
        L.read_csv(path, sido_code="11")
    msg = str(e.value)
    assert "결정 0009" in msg
    assert "load_seoul_district.py" in msg          # 대신 무엇을 쓸지도 알려 준다


def test_read_csv_handles_field_larger_than_csv_default_limit(tmp_path):
    """★ 상권좌표 한 칸이 13만 자를 넘는다. 상한을 안 올리면 파이썬이 통째로 죽는다."""
    big = _big_ring()
    assert len(big) > 131072
    path = str(tmp_path / "sbiz.csv")
    _write_csv(path, [_row_values(coords=big, cnt=str(big.count("|") + 1))])
    rows = L.read_csv(path)
    assert rows[0]["wkt"].startswith("MULTILINESTRING((")


def test_read_csv_reads_multi_ring_rows_end_to_end(tmp_path):
    """★ 실제 파일의 36%가 이 모양이다 — 읽기 경로 전체가 견디는지 본다."""
    path = str(tmp_path / "sbiz.csv")
    _write_csv(path, [_row_values(coords=_TWO_RINGS, cnt="6")])
    rows = L.read_csv(path)
    assert rows[0]["ring_count"] == 2
    assert L.summarize(rows)["multi_ring"] == 1


def test_read_csv_reports_available_sido_when_nothing_matched(tmp_path):
    """0행을 조용히 성공 처리하면 '적재했다'고 착각한다 — 무엇이 있었는지 보여준다."""
    path = str(tmp_path / "sbiz.csv")
    _write_csv(path, [_row_values(code="11001", sido="11", sigungu="11680")])
    with pytest.raises(ValueError) as e:
        L.read_csv(path)
    assert "11" in str(e.value)


def test_read_csv_refuses_changed_header(tmp_path):
    path = str(tmp_path / "sbiz.csv")
    with io.open(path, "w", encoding=L.ENCODING, newline="") as f:
        csv.writer(f).writerow(["상권번호", "상권명"])
    with pytest.raises(ValueError) as e:
        L.read_csv(path)
    assert "상권좌표" in str(e.value)
