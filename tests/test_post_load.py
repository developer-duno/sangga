# -*- coding: utf-8 -*-
"""scripts/post_load.py 1:1 단위 테스트.

여기서 지키는 것은 "적재 후 마무리가 조용히 반쪽이 되는 것"이다. 세 가지 모두
**에러 없이** 틀리는 종류라 사람 눈으로는 안 잡힌다:
  1) ANALYZE 대상에서 큰 표가 빠짐 → 통계가 낡아 화면이 느려진다
  2) `concurrently` 가 빠짐 → 갱신 중 검색이 통째로 잠긴다
  3) 신선도 판정이 헐거워짐 → 낡은 요약표를 "신선"이라 보고한다

공용 설정 파일(conftest.py) 없이 이 파일 안에서 import 경로를 직접 해결한다
(tests/test_backup_raw.py 와 동일한 방식).
"""

import os
import sys

import pytest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402


# ── 1. ANALYZE 대상 ─────────────────────────────────────────────────────────


class TestBuildAnalyzeSql:
    def test_covers_the_tables_that_bulk_loads_touch(self):
        """대량 적재가 건드리는 표가 빠지면 그 표만 낡은 채로 남는다."""
        sql = post_load.build_analyze_sql()
        for t in ("parcel", "unit_business", "building", "building_floor"):
            assert "vacuum (analyze) {};".format(t) in sql, (
                "{} 가 갱신 대상에서 빠졌습니다".format(t)
            )

    def test_uses_vacuum_not_just_analyze(self):
        """⛔ analyze 만으로는 **가시성 지도**가 안 고쳐진다.

        2026-08-13 실측: 전국 시드 뒤 각주 뷰가 Heap Fetches 232,890 · 956ms 로
        되돌아갔고, `vacuum (analyze)` 한 번에 Heap Fetches 0 · 화면 0.31초가 됐다.
        analyze 로만 되돌리면 이 회귀가 조용히 재발한다(에러는 안 난다).
        """
        assert post_load.build_analyze_sql(("t",)).startswith("vacuum (analyze)"), (
            "analyze 만 돌리면 인덱스 전용 조회가 행마다 힙을 다시 방문합니다"
        )

    def test_one_statement_per_line(self):
        sql = post_load.build_analyze_sql(("a", "b"))
        assert sql == "vacuum (analyze) a;\nvacuum (analyze) b;"

    def test_empty_list_makes_empty_sql(self):
        assert post_load.build_analyze_sql(()) == ""


# ── 2. 요약표 갱신 ──────────────────────────────────────────────────────────


class TestBuildRefreshSql:
    def test_uses_concurrently(self):
        """⛔ 빼면 갱신이 끝날 때까지 그 표를 읽는 검색이 잠긴다."""
        assert "concurrently" in post_load.build_refresh_sql()

    def test_targets_the_search_summary(self):
        assert post_load.build_refresh_sql().endswith("mv_search_parcel;")

    def test_custom_target(self):
        assert post_load.build_refresh_sql("x") == "refresh materialized view concurrently x;"


# ── 3. 신선도 판정 ──────────────────────────────────────────────────────────


class TestIsStale:
    """요약표 행수 == count(distinct building.pnu) 는 **등식**이다(building.pnu 가 parcel 참조).

    추정이 아니라 반드시 성립해야 하는 값이라, 다르면 갱신을 빼먹은 것이 확정된다.
    """

    def test_same_counts_are_fresh(self):
        assert post_load.is_stale(188442, 188442) is False

    def test_fewer_rows_is_stale(self):
        """건물이 늘었는데 갱신을 안 한 경우 — 새 건물이 검색에서 빠진다."""
        assert post_load.is_stale(188442, 190000) is True

    def test_more_rows_is_also_stale(self):
        """건물이 줄었는데 갱신을 안 한 경우도 낡은 것이다(없는 건물이 검색된다)."""
        assert post_load.is_stale(190000, 188442) is True

    def test_accepts_strings_from_psql(self):
        """psql -tA 는 문자열을 준다. '188442' 와 188442 를 다르다고 하면 안 된다."""
        assert post_load.is_stale("188442", "188442") is False
        assert post_load.is_stale("188442", "188443") is True


class TestBuildFreshnessSql:
    def test_compares_summary_against_distinct_building_pnu(self):
        sql = post_load.build_freshness_sql()
        assert "count(*) from mv_search_parcel" in sql
        assert "count(distinct pnu) from building" in sql

    def test_returns_one_delimited_value(self):
        """한 줄로 받아 쪼갠다 — 구분자가 빠지면 report_freshness 가 깨진다."""
        assert "'|'" in post_load.build_freshness_sql()


# ── 4. 인자 파싱 ────────────────────────────────────────────────────────────


class TestParseArgs:
    def test_default_is_apply_not_check(self):
        assert post_load.parse_args([])["check"] is False

    def test_check_flag(self):
        assert post_load.parse_args(["--check"])["check"] is True

    def test_unknown_arg_raises(self):
        """오타를 조용히 무시하면 '확인만'이 '실제 실행'으로 바뀐다."""
        with pytest.raises(ValueError) as e:
            post_load.parse_args(["--chek"])
        assert "알 수 없는 인자" in str(e.value)

    def test_help_is_rejected_not_silently_ignored(self):
        with pytest.raises(ValueError):
            post_load.parse_args(["--help"])


# ── 5. 흐름 (DB 없이) ───────────────────────────────────────────────────────


class TestMainFlow:
    def test_check_returns_1_when_stale(self, monkeypatch):
        """CI·다른 스크립트가 종료 코드로 받아 쓸 수 있어야 한다."""
        monkeypatch.setattr(post_load, "query_one", lambda sql: "100|200")
        assert post_load.main(["--check"]) == 1

    def test_check_returns_0_when_fresh(self, monkeypatch):
        # --check 는 두 가지를 묻는다(신선도 · 공개키 노출) — mock 도 갈라 답해야 한다.
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "200|200" if "count(" in sql else "v_floor_stack")
        assert post_load.main(["--check"]) == 0

    def test_check_never_writes(self, monkeypatch):
        """--check 는 읽기만 해야 한다 — 실수로 갱신을 돌리면 안 된다."""
        calls = []
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "200|200" if "count(" in sql else "v_floor_stack")
        monkeypatch.setattr(post_load.dbx, "run_sql",
                            lambda *a, **k: calls.append(a) or 0)
        post_load.main(["--check"])
        assert calls == []

    def test_apply_runs_analyze_then_refresh_then_rechecks(self, monkeypatch):
        """했다고 믿지 않고 **다시 재는지**까지 확인한다."""
        ran = []
        monkeypatch.setattr(post_load.dbx, "run_sql",
                            lambda sql, **k: ran.append(sql) or 0)
        checked = []
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: checked.append(sql) or "200|200")
        assert post_load.main([]) == 0
        assert len(ran) == 2 and "vacuum (analyze)" in ran[0] and "refresh" in ran[1]
        assert len(checked) == 1

    def test_apply_stops_when_analyze_fails(self, monkeypatch):
        """앞이 실패했는데 뒤를 계속 돌면 '성공했다'는 착각이 남는다."""
        monkeypatch.setattr(post_load.dbx, "run_sql", lambda sql, **k: 2)
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: pytest.fail("실패했는데 신선도를 재면 안 됩니다"))
        assert post_load.main([]) == 2

    def test_apply_reports_failure_when_still_stale_after_refresh(self, monkeypatch):
        """갱신을 돌렸는데도 안 맞으면 성공으로 끝내면 안 된다."""
        monkeypatch.setattr(post_load.dbx, "run_sql", lambda sql, **k: 0)
        monkeypatch.setattr(post_load, "query_one", lambda sql: "100|200")
        assert post_load.main([]) == 1


# ── 6. 공개키 노출 점검 (2026-08-13 실제 사고에서 신설) ─────────────────────


class TestAnonExposure:
    """정적 검사(schema.sql 에 revoke 가 적혀 있나)로는 못 잡는 사고가 있다.

    2026-08-13: 새로 만든 물질화뷰 2개가 Supabase 기본 권한 때문에 **자동으로**
    anon 에게 열렸다. schema.sql 에는 아무 문제가 없었는데 라이브만 뚫려 있었다.
    그래서 이 점검은 반드시 **라이브에 물어본다.**
    """

    def test_allowlist_is_only_what_the_screen_reads(self):
        """허용 목록이 늘어나면 노출면이 늘어난 것이다 — 눈에 띄게 해 둔다.

        우리 자료는 화면이 읽는 뷰 2개뿐이고, 나머지 3개는 PostGIS 확장이 스스로
        만드는 좌표계 정의표·메타데이터라 우리 데이터가 아니다(닫으면 PostGIS 가 깨진다).
        """
        assert post_load.ANON_READABLE_ALLOWLIST == (
            "v_floor_stack",
            "v_coverage_stats",
            "spatial_ref_sys",
            "geography_columns",
            "geometry_columns",
        )
        ours = [n for n in post_load.ANON_READABLE_ALLOWLIST if n.startswith("v_")]
        assert ours == ["v_floor_stack", "v_coverage_stats"], (
            "우리 자료 중 공개된 것이 늘었습니다 — 정말 화면이 읽는 것인지 확인하세요"
        )

    def test_flags_anything_outside_the_allowlist(self):
        got = post_load.unexpected_anon_readables(
            ["v_floor_stack", "v_coverage_stats", "mv_search_parcel"]
        )
        assert got == ["mv_search_parcel"]

    def test_quiet_when_only_allowed_are_open(self):
        assert post_load.unexpected_anon_readables(["v_coverage_stats", "v_floor_stack"]) == []

    def test_catches_raw_tables_being_opened(self):
        """원본 표가 열리는 것이 가장 위험하다."""
        assert post_load.unexpected_anon_readables(["parcel", "building"]) == ["building", "parcel"]

    def test_ignores_blank_lines_from_psql(self):
        assert post_load.unexpected_anon_readables(["", "  ", "v_floor_stack"]) == []

    def test_sql_asks_about_anon_and_public_schema(self):
        sql = post_load.build_anon_exposure_sql()
        assert "has_table_privilege('anon'" in sql
        assert "nspname = 'public'" in sql
        # 물질화뷰('m')가 빠지면 2026-08-13 사고를 그대로 놓친다.
        assert "'m'" in sql

    def test_check_returns_1_when_something_is_exposed(self, monkeypatch):
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "200|200" if "count(" in sql
                            else "v_floor_stack\nmv_search_parcel")
        assert post_load.main(["--check"]) == 1

    def test_check_returns_0_when_clean(self, monkeypatch):
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "200|200" if "count(" in sql
                            else "v_floor_stack\nv_coverage_stats")
        assert post_load.main(["--check"]) == 0
