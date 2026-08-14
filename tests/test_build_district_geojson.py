# -*- coding: utf-8 -*-
"""scripts/build_district_geojson.py 1:1 단위 테스트.

여기서 지키는 것은 "지도가 **에러 없이** 틀리는 것"이다. 넷 다 눈으로는 안 잡힌다:
  1) `ST_Simplify`(위상 미보존)로 바뀜 → 면이 스스로 교차해 지도에 꼬인 그림이 그려진다
  2) 순서가 뒤집힘 → 좁은 골목상권이 넓은 상권에 **덮여 사라진다**(클릭도 안 된다)
  3) 신선도 meta 가 어긋남 → 상권을 새로 적재해도 지도만 옛날 것을 계속 보여준다
  4) `generated_at` 이 끼어듦 → 자료가 그대로인데 다시 구울 때마다 git diff 가 난다

DB 없이 돈다 — 전부 순수 함수만 본다(기존 1,249개가 전부 로컬에서 도는 이유).
공용 설정 파일(conftest.py) 없이 이 파일 안에서 import 경로를 직접 해결한다
(tests/test_post_load.py 와 동일한 방식).
"""

import io
import json
import os
import sys

import pytest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import build_district_geojson as bdg  # noqa: E402


# ⚠️ 시각은 **고정된 과거값**을 주입한다. 지금 시각이나 미래 날짜를 쓰면 어느 날
#    자정을 넘기는 순간 코드 변경 0 인데 테스트가 빨개진다(2026-08-02 flowershop 사고).
#    여기서 이 값은 그냥 "어떤 문자열"일 뿐이라 의미가 없다.
FIXED_MAX = "2020-01-01T00:00:00.000000Z"


def make_feature(district_id, area, nm="상권"):
    return {
        "type": "Feature",
        "properties": {
            "district_id": district_id,
            "district_nm": nm,
            "district_type": "골목상권",
            "source_nm": "서울특별시 상권분석서비스",
            "sigungu_code": "11680",
            "area_m2": area,
        },
        "geometry": {"type": "Polygon", "coordinates": [[[127.0, 37.0]]]},
    }


def make_doc(features, cnt=None, max_ca=FIXED_MAX):
    return {
        "type": "FeatureCollection",
        "meta": {
            "district_cnt": len(features) if cnt is None else cnt,
            "max_computed_at": max_ca,
        },
        "features": features,
    }


# ── 1. 도형을 뽑는 SQL ──────────────────────────────────────────────────────


class TestBuildFeaturesSql:
    def test_preserves_topology(self):
        """⛔ 여기가 이 파일에서 가장 중요한 검사다.

        `ST_Simplify` 는 점을 솎다가 면을 **스스로 교차시켜** 깨뜨린다. 그러면 지도에
        리본처럼 꼬인 도형이 그려지거나 아예 안 그려지는데, 에러가 아니라 그림이
        이상해지는 종류라 테스트 없이는 아무도 못 찾는다.
        """
        sql = bdg.build_features_sql()
        assert "st_simplifypreservetopology(" in sql
        # 이름이 비슷해 헷갈린다 — 위상 미보존판으로 바뀌지 않았는지 직접 본다.
        assert "st_simplify(" not in sql, "위상 미보존 ST_Simplify 로 바뀌었습니다"

    def test_uses_the_agreed_tolerance_and_digits(self):
        sql = bdg.build_features_sql()
        assert "0.0001" in sql, "단순화 정도가 바뀌면 파일 크기가 통째로 달라진다"
        assert ", 6)" in sql, "좌표 자릿수 제한이 빠지면 파일이 몇 배로 부푼다"

    def test_custom_tolerance_and_digits_flow_through(self):
        sql = bdg.build_features_sql(tolerance=0.001, digits=4)
        assert "0.001" in sql and ", 4)" in sql

    def test_carries_every_property_the_screen_needs(self):
        sql = bdg.build_features_sql()
        for key in bdg.PROPERTY_KEYS:
            assert "'{k}', {k}".format(k=key) in sql, "{} 가 빠졌습니다".format(key)

    def test_source_nm_is_not_droppable(self):
        """공공누리 1유형 출처 표기를 **자료에서 읽어** 보여준다(결정 0009 §1-③).

        고정 문구를 화면에 박으면 소스가 둘이 된 순간(서울시 / 소진공) 한쪽에 거짓말이 된다.
        """
        assert "source_nm" in bdg.PROPERTY_KEYS
        assert "'source_nm', source_nm" in bdg.build_features_sql()

    def test_geometry_is_nested_as_object_not_string(self):
        """`::json` 이 빠지면 geometry 가 **문자열**로 들어가 지도가 못 읽는다."""
        assert "::json" in bdg.build_features_sql()

    def test_does_not_sort_in_sql(self):
        """정렬은 파이썬이 한다 — DB 문자열 정렬 규칙에 따라 줄 순서가 흔들리면
        내용이 같아도 매번 통째로 diff 가 난다."""
        assert "order by" not in bdg.build_features_sql().lower()

    def test_does_not_leak_raw_geometry_column(self):
        """properties 에 geom 이 들어가면 파일이 두 배가 된다."""
        assert "'geom'," not in bdg.build_features_sql()


# ── 2. 신선도 메타 ──────────────────────────────────────────────────────────


class TestBuildMetaSql:
    def test_counts_district_rows(self):
        assert "count(*)" in bdg.build_meta_sql()
        assert "from district" in bdg.build_meta_sql()

    def test_pins_utc(self):
        """⛔ 시간대를 안 박으면 접속 세션 설정에 따라 `+00` 이 `+09` 로 찍혀,
        자료가 그대로인데 신선도 등식이 어긋난다(굽는 사람과 검사하는 사람의 환경이 다를 때)."""
        sql = bdg.build_meta_sql()
        assert "at time zone 'UTC'" in sql
        assert "to_char(" in sql, "형식을 고정하지 않으면 렌더링이 환경 따라 달라진다"

    def test_returns_one_delimited_value(self):
        assert "'|'" in bdg.build_meta_sql()


class TestParseMetaRow:
    def test_splits_count_and_time(self):
        assert bdg.parse_meta_row("1687|" + FIXED_MAX) == (1687, FIXED_MAX)

    def test_tolerates_surrounding_spaces(self):
        assert bdg.parse_meta_row("  1687|" + FIXED_MAX + "  ") == (1687, FIXED_MAX)

    def test_empty_time_is_allowed(self):
        """표가 비어 있으면 max 가 없다 — 그래도 행수는 읽혀야 한다."""
        assert bdg.parse_meta_row("0|") == (0, "")

    def test_missing_delimiter_raises(self):
        """조용히 넘기면 신선도 검사가 **항상 통과**하는 무용지물이 된다."""
        with pytest.raises(ValueError):
            bdg.parse_meta_row("1687")

    def test_non_number_raises(self):
        with pytest.raises(ValueError):
            bdg.parse_meta_row("어쩌구|" + FIXED_MAX)


# ── 3. 겹침 규칙 = 넓은 것부터 (이 파일의 존재 이유 절반) ────────────────────


class TestFeatureOrder:
    """GeoJSON 의 feature 순서 = 지도에 겹쳐 그리는 순서.

    넓은 것을 먼저(아래) 그려야 좁은 골목상권이 위에 남는다. 뒤집히면 작은 상권은
    덮여서 보이지도, 클릭되지도 않는다(사장님 확정 겹침 규칙 · 결정 0010).
    """

    def test_biggest_area_comes_first(self):
        doc = bdg.assemble_geojson(
            [json.dumps(make_feature("a", 100.0)),
             json.dumps(make_feature("b", 9000.0)),
             json.dumps(make_feature("c", 500.0))],
            3, FIXED_MAX)
        assert [f["properties"]["district_id"] for f in doc["features"]] == ["b", "c", "a"]

    def test_ties_break_by_district_id_for_stable_diffs(self):
        """같은 면적이면 순서가 흔들리면 안 된다 — 흔들리면 매번 diff 가 난다."""
        doc = bdg.assemble_geojson(
            [json.dumps(make_feature("z", 100.0)),
             json.dumps(make_feature("a", 100.0))],
            2, FIXED_MAX)
        assert [f["properties"]["district_id"] for f in doc["features"]] == ["a", "z"]

    def test_missing_area_goes_last(self):
        """면적이 없어도 정렬이 깨지면 안 된다 — 깨지면 겹침 규칙 자체가 무너진다."""
        doc = bdg.assemble_geojson(
            [json.dumps(make_feature("none", None)),
             json.dumps(make_feature("big", 10.0))],
            2, FIXED_MAX)
        assert [f["properties"]["district_id"] for f in doc["features"]] == ["big", "none"]

    def test_sort_key_is_descending_by_area(self):
        big = bdg.feature_sort_key(make_feature("a", 900.0))
        small = bdg.feature_sort_key(make_feature("b", 1.0))
        assert big < small, "정렬 키가 내림차순이 아닙니다"


# ── 4. 문서 조립 ────────────────────────────────────────────────────────────


class TestAssembleGeojson:
    def test_builds_a_feature_collection(self):
        doc = bdg.assemble_geojson([json.dumps(make_feature("a", 1.0))], 1, FIXED_MAX)
        assert doc["type"] == "FeatureCollection"
        assert doc["meta"] == {"district_cnt": 1, "max_computed_at": FIXED_MAX}

    def test_count_mismatch_stops_everything(self):
        """도형이 없어 빠진 상권이 있는데 '다 구웠다'고 넘어가면 지도에서 조용히 사라진다."""
        with pytest.raises(ValueError) as e:
            bdg.assemble_geojson([json.dumps(make_feature("a", 1.0))], 2, FIXED_MAX)
        assert "1" in str(e.value) and "2" in str(e.value)

    def test_no_generated_at(self):
        """만든 시각을 적으면 자료가 그대로인데 다시 구울 때마다 diff 가 난다."""
        doc = bdg.assemble_geojson([json.dumps(make_feature("a", 1.0))], 1, FIXED_MAX)
        assert "generated_at" not in doc["meta"]

    def test_empty_table_makes_empty_file_not_a_crash(self):
        doc = bdg.assemble_geojson([], 0, "")
        assert doc["features"] == [] and doc["meta"]["district_cnt"] == 0


class TestDumpsCompact:
    def test_no_padding_spaces(self):
        text = bdg.dumps_compact(make_doc([make_feature("a", 1.0)]))
        assert '", "' not in text and '": ' not in text

    def test_keeps_hangul_readable(self):
        """`ensure_ascii` 기본값이면 '강남역'이 \\uXXXX 로 부풀어 파일이 커지고 못 읽는다."""
        text = bdg.dumps_compact(make_doc([make_feature("a", 1.0, nm="강남역")]))
        assert "강남역" in text
        assert "\\u" not in text

    def test_round_trips(self):
        doc = make_doc([make_feature("a", 1.0)])
        assert json.loads(bdg.dumps_compact(doc)) == doc


# ── 5. 구운 뒤 다시 재는 관문 ───────────────────────────────────────────────


class TestCheckDocument:
    """"했다고 믿지 않고 다시 잰다"(post_load.py 관행)."""

    def test_good_document_has_no_problems(self):
        doc = make_doc([make_feature("b", 900.0), make_feature("a", 1.0)])
        assert bdg.check_document(doc, 2, FIXED_MAX) == []

    def test_catches_count_drift_against_live(self):
        doc = make_doc([make_feature("a", 1.0)])
        assert bdg.check_document(doc, 2, FIXED_MAX) != []

    def test_catches_meta_lying_about_its_own_features(self):
        doc = make_doc([make_feature("a", 1.0)], cnt=99)
        assert any("meta.district_cnt" in p for p in bdg.check_document(doc, 1, FIXED_MAX))

    def test_catches_stale_time(self):
        doc = make_doc([make_feature("a", 1.0)])
        assert any("max_computed_at" in p
                   for p in bdg.check_document(doc, 1, "2019-01-01T00:00:00.000000Z"))

    def test_catches_wrong_overlap_order(self):
        """좁은 상권이 먼저 오면 넓은 상권이 그 위를 덮는다."""
        doc = make_doc([make_feature("small", 1.0), make_feature("big", 900.0)])
        assert any("넓은 상권부터" in p for p in bdg.check_document(doc, 2, FIXED_MAX))

    def test_catches_empty_geometry(self):
        """도형이 비면 지도에 아무것도 안 그려지는데 에러는 안 난다."""
        f = make_feature("a", 1.0)
        f["geometry"] = {"type": "Polygon", "coordinates": []}
        assert any("도형이 빈" in p for p in bdg.check_document(make_doc([f]), 1, FIXED_MAX))

    def test_catches_generated_at_sneaking_back_in(self):
        doc = make_doc([make_feature("a", 1.0)])
        doc["meta"]["generated_at"] = "언제든"
        assert any("generated_at" in p for p in bdg.check_document(doc, 1, FIXED_MAX))

    def test_catches_wrong_top_level_type(self):
        doc = make_doc([make_feature("a", 1.0)])
        doc["type"] = "Feature"
        assert any("FeatureCollection" in p for p in bdg.check_document(doc, 1, FIXED_MAX))

    def test_survives_a_broken_shape_without_crashing(self):
        assert bdg.check_document({"type": "FeatureCollection"}, 0, "") != []


# ── 6. 파일에서 meta 읽기 (post_load 가 쓴다) ───────────────────────────────


class TestReadMeta:
    def test_reads_meta_from_a_real_file(self, tmp_path):
        path = str(tmp_path / "d.geojson")
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(bdg.dumps_compact(make_doc([make_feature("a", 1.0)])))
        assert bdg.read_meta(path) == {"district_cnt": 1, "max_computed_at": FIXED_MAX}

    def test_missing_file_is_none_not_a_crash(self, tmp_path):
        assert bdg.read_meta(str(tmp_path / "없음.geojson")) is None

    def test_broken_json_is_none(self, tmp_path):
        path = str(tmp_path / "d.geojson")
        with io.open(path, "w", encoding="utf-8") as f:
            f.write("{망가진")
        assert bdg.read_meta(path) is None

    def test_file_without_meta_is_none(self, tmp_path):
        path = str(tmp_path / "d.geojson")
        with io.open(path, "w", encoding="utf-8") as f:
            f.write('{"type":"FeatureCollection","features":[]}')
        assert bdg.read_meta(path) is None


# ── 7. 크기·인자 ───────────────────────────────────────────────────────────


class TestFormatSize:
    def test_reports_bytes_not_characters(self):
        """한글 한 글자가 3바이트라 글자 수로 재면 실제 파일보다 한참 작게 나온다."""
        assert "1,048,576" in bdg.format_size(1048576)
        assert bdg.format_size(1048576).startswith("1.00MB")


class TestParseArgs:
    def test_default_writes_the_file(self):
        assert bdg.parse_args([])["dry_run"] is False

    def test_dry_run_flag(self):
        assert bdg.parse_args(["--dry-run"])["dry_run"] is True

    def test_unknown_arg_raises(self):
        """오타를 조용히 무시하면 '미리보기'가 '실제 생성'으로 바뀐다."""
        with pytest.raises(ValueError) as e:
            bdg.parse_args(["--dryrun"])
        assert "알 수 없는 인자" in str(e.value)


# ── 8. 흐름 (DB 없이) ───────────────────────────────────────────────────────


class TestMainFlow:
    def _fake_db(self, monkeypatch, cnt=2):
        feats = [json.dumps(make_feature("a", 1.0)), json.dumps(make_feature("b", 900.0))]

        def query_lines(sql):
            if "count(*)" in sql:
                return ["{}|{}".format(cnt, FIXED_MAX)]
            return feats

        monkeypatch.setattr(bdg, "query_lines", query_lines)

    def test_dry_run_writes_nothing(self, monkeypatch, tmp_path, capsys):
        self._fake_db(monkeypatch)
        path = str(tmp_path / "out.geojson")
        monkeypatch.setattr(bdg, "OUT_PATH", path)
        assert bdg.main(["--dry-run"]) == 0
        assert not os.path.exists(path), "--dry-run 인데 파일을 썼습니다"
        assert "미리보기" in capsys.readouterr().out

    def test_writes_and_verifies(self, monkeypatch, tmp_path):
        self._fake_db(monkeypatch)
        path = str(tmp_path / "sub" / "out.geojson")   # 폴더가 없어도 만들어야 한다
        monkeypatch.setattr(bdg, "OUT_PATH", path)
        assert bdg.main([]) == 0
        with io.open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        assert doc["meta"]["district_cnt"] == 2
        assert [f["properties"]["district_id"] for f in doc["features"]] == ["b", "a"]

    def test_written_file_uses_lf_only(self, monkeypatch, tmp_path):
        """윈도우 기본값(CRLF)으로 쓰면 내용이 같아도 CI(리눅스)와 파일이 달라진다."""
        self._fake_db(monkeypatch)
        path = str(tmp_path / "out.geojson")
        monkeypatch.setattr(bdg, "OUT_PATH", path)
        bdg.main([])
        with io.open(path, "rb") as f:
            assert b"\r\n" not in f.read()

    def test_fails_when_live_changed_while_baking(self, monkeypatch, tmp_path, capsys):
        """굽는 사이에 자료가 바뀌면 그 파일은 이미 낡은 것이다 — 성공으로 끝내면 안 된다."""
        self._fake_db(monkeypatch)
        path = str(tmp_path / "out.geojson")
        monkeypatch.setattr(bdg, "OUT_PATH", path)

        calls = []
        real = bdg.fetch_live_meta

        def shifting():
            calls.append(1)
            return (2, FIXED_MAX) if len(calls) == 1 else (2, "2021-01-01T00:00:00.000000Z")

        monkeypatch.setattr(bdg, "fetch_live_meta", shifting)
        assert real is not shifting
        assert bdg.main([]) == 1
        assert "실패" in capsys.readouterr().out

    def test_stops_when_rows_go_missing(self, monkeypatch, tmp_path):
        """받은 줄 수가 라이브 행수보다 적으면 멈춘다(빠진 상권이 있다는 뜻)."""
        self._fake_db(monkeypatch, cnt=99)
        monkeypatch.setattr(bdg, "OUT_PATH", str(tmp_path / "out.geojson"))
        with pytest.raises(ValueError):
            bdg.main([])
