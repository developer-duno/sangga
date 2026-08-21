# -*- coding: utf-8 -*-
"""scripts/post_load.py 1:1 단위 테스트.

여기서 지키는 것은 "적재 후 마무리가 조용히 반쪽이 되는 것"이다. 넷 다
**에러 없이** 틀리는 종류라 사람 눈으로는 안 잡힌다:
  1) ANALYZE 대상에서 큰 표가 빠짐 → 통계가 낡아 화면이 느려진다
  2) `concurrently` 가 빠짐 → 갱신 중 검색이 통째로 잠긴다
  3) 신선도 판정이 헐거워짐 → 낡은 요약표를 "신선"이라 보고한다
  4) 지도 상권 파일 검사가 빠짐 → 지도만 옛날 상권을 계속 보여준다(2026-08-14 신설)

공용 설정 파일(conftest.py) 없이 이 파일 안에서 import 경로를 직접 해결한다
(tests/test_backup_raw.py 와 동일한 방식).
"""

import os
import sys
from datetime import datetime

import pytest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402


@pytest.fixture
def map_is_fresh(monkeypatch):
    """지도 파일 검사만 빼고 본다.

    ⚠️ 이 stub 이 없으면 `main()` 이 **레포에 실제로 있는** public/districts.geojson 을
       읽어 라이브(가짜 mock 값)와 대조하게 돼, 이 반의 관심사와 상관없이 결과가 흔들린다.
       지도 검사 자체는 아래 TestMapFreshness 가 따로 본다.
    """
    monkeypatch.setattr(post_load, "report_map_freshness",
                        lambda: ({"district_cnt": 0, "max_computed_at": ""}, False))


@pytest.fixture
def tx_window_is_fresh(monkeypatch):
    """실거래 단가 창 검사만 빼고 본다 (map_is_fresh 와 같은 이유 — 관심사 분리).

    이 stub 이 없으면 `main()` 이 라이브 mv_sigungu_tx_stats 를 물으러 가거나,
    mock 된 query_one 의 엉뚱한 답을 창으로 오해해 이 반의 관심사와 상관없이 흔들린다.
    창 판정 자체는 아래 TestTxWindowStale 이 따로 본다.
    """
    monkeypatch.setattr(post_load, "report_tx_window_freshness",
                        lambda: ("202408", "202408", False))


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
        # 검색 요약표는 반드시 대상에 있어야 한다(순서·다른 표는 아래 전용 검사에서 본다).
        assert "concurrently mv_search_parcel;" in post_load.build_refresh_sql()

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
    def test_check_returns_1_when_stale(self, monkeypatch, map_is_fresh, tx_window_is_fresh):
        """CI·다른 스크립트가 종료 코드로 받아 쓸 수 있어야 한다."""
        monkeypatch.setattr(post_load, "query_one", lambda sql: "100|200")
        assert post_load.main(["--check"]) == 1

    def test_check_returns_0_when_fresh(self, monkeypatch, map_is_fresh, tx_window_is_fresh):
        # --check 는 세 가지를 묻는다(신선도 · 지도 파일 · 공개키 노출) — mock 도 갈라 답해야 한다.
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "200|200" if "count(" in sql else "v_floor_stack")
        assert post_load.main(["--check"]) == 0

    def test_check_never_writes(self, monkeypatch, map_is_fresh, tx_window_is_fresh):
        """--check 는 읽기만 해야 한다 — 실수로 갱신을 돌리면 안 된다."""
        calls = []
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "200|200" if "count(" in sql else "v_floor_stack")
        monkeypatch.setattr(post_load.dbx, "run_sql",
                            lambda *a, **k: calls.append(a) or 0)
        post_load.main(["--check"])
        assert calls == []

    def test_apply_runs_analyze_then_refresh_then_rechecks(self, monkeypatch, map_is_fresh, tx_window_is_fresh):
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

    def test_apply_reports_failure_when_still_stale_after_refresh(self, monkeypatch, map_is_fresh, tx_window_is_fresh):
        """갱신을 돌렸는데도 안 맞으면 성공으로 끝내면 안 된다."""
        monkeypatch.setattr(post_load.dbx, "run_sql", lambda sql, **k: 0)
        monkeypatch.setattr(post_load, "query_one", lambda sql: "100|200")
        assert post_load.main([]) == 1


# ── 5-b. 실거래 단가 창 신선도 (2026-08-15 신설 — 결정 0012 Stage A) ────────


class TestTxWindowStale:
    """창은 갱신하는 순간 굳는다 — 오래 안 돌리면 "최근 24개월" 문구만 조용히 낡는다.

    독립 리뷰(2026-08-15)가 잡은 구멍: window_from 은 화면에서 항상 사실을 말하지만,
    "최근 24개월"이라는 앞 문구는 갱신을 미루면 거짓이 된다. 그래서 --check 가 잰다.
    """

    def test_same_month_is_fresh(self):
        assert post_load.is_tx_window_stale("202408", "202408") is False

    def test_one_month_drift_is_normal(self):
        """갱신 직후에도 달이 바뀌면 1개월 차이가 난다 — 경계 오차는 낡음이 아니다."""
        assert post_load.is_tx_window_stale("202408", "202409") is False
        assert post_load.is_tx_window_stale("202409", "202408") is False

    def test_two_months_drift_is_stale(self):
        assert post_load.is_tx_window_stale("202408", "202410") is True

    def test_year_boundary_is_one_month_not_eightynine(self):
        """202412↔202501 은 1개월 차이다 — 문자열 뺄셈이면 89 로 오판한다."""
        assert post_load.is_tx_window_stale("202412", "202501") is False

    def test_empty_table_is_stale(self):
        """행이 0개면 창 자체가 없다 — '검사할 게 없다'고 넘어가면 빈 표가 정상이 된다."""
        assert post_load.is_tx_window_stale("", "202408") is True
        assert post_load.is_tx_window_stale(None, "202408") is True

    def test_garbage_is_stale(self):
        assert post_load.is_tx_window_stale("24개월", "202408") is True


class TestExpectedTxWindowFrom:
    def test_subtracts_24_months(self):
        assert post_load.expected_tx_window_from(datetime(2026, 8, 15)) == "202408"

    def test_january_rolls_into_previous_year(self):
        assert post_load.expected_tx_window_from(datetime(2026, 1, 3)) == "202401"

    def test_december(self):
        assert post_load.expected_tx_window_from(datetime(2026, 12, 31)) == "202412"


# ── 6. 공개키 노출 점검 (2026-08-13 실제 사고에서 신설) ─────────────────────


class TestAnonExposure:
    """정적 검사(schema.sql 에 revoke 가 적혀 있나)로는 못 잡는 사고가 있다.

    2026-08-13: 새로 만든 물질화뷰 2개가 Supabase 기본 권한 때문에 **자동으로**
    anon 에게 열렸다. schema.sql 에는 아무 문제가 없었는데 라이브만 뚫려 있었다.
    그래서 이 점검은 반드시 **라이브에 물어본다.**
    """

    def test_allowlist_is_only_what_the_screen_reads(self):
        """허용 목록이 늘어나면 노출면이 늘어난 것이다 — 눈에 띄게 해 둔다.

        확장(PostGIS·pg_trgm)이 만든 것은 SQL 단계에서 제외하므로, 여기 남는 것은
        **전부 우리가 만든 것**이다. 그래서 목록이 짧고, 늘면 바로 눈에 띈다.
        """
        assert post_load.ANON_READABLE_ALLOWLIST == ("v_floor_stack", "v_coverage_stats")
        assert post_load.ANON_CALLABLE_ALLOWLIST == (
            "search_buildings", "search_scope", "list_open_sigungu",
            "list_building_districts",
            "list_parcel_transactions", "get_sigungu_tx_stats",
            "list_price_bands",
        )

    def test_stage_b_internals_are_never_allowed(self):
        """⛔ Stage B(결정 0013)에서 화면이 부르는 것은 list_price_bands 하나뿐이다.

        게이트 표가 열리면 "어느 구가 켜져 있나"를 통째로 긁어갈 수 있고, 층대 도우미가
        열리면 노출면만 늘 뿐 화면에 쓸모가 없다. 둘 다 열려 있으면 사고다.
        """
        for name in ("price_gate_sigungu", "price_floor_band"):
            assert name not in post_load.ANON_READABLE_ALLOWLIST
            assert name not in post_load.ANON_CALLABLE_ALLOWLIST
            assert post_load.unexpected_anon_readables([name]) == [name]

    def test_the_tx_matview_is_never_allowed(self):
        """⛔ Stage A 의 물질화뷰가 허용 목록에 들어가면 안 된다(결정 0012).

        화면은 함수 둘로만 읽는다. 표가 열리면 REST 페이지네이션으로 구 전체 분포를
        통째로 긁어갈 수 있고, 그건 2026-08-13 사고(mv_search_parcel 200)와 같은 형태다.
        """
        assert "mv_sigungu_tx_stats" not in post_load.ANON_READABLE_ALLOWLIST
        assert "mv_sigungu_tx_stats" not in post_load.ANON_CALLABLE_ALLOWLIST
        assert post_load.unexpected_anon_readables(["mv_sigungu_tx_stats"]) == [
            "mv_sigungu_tx_stats"
        ]

    def test_the_coverage_matview_is_never_allowed(self):
        """⛔ 각주 집계를 미리 계산해 둔 표(2026-08-22d)도 허용 목록에 들어가면 안 된다.

        화면이 읽는 것은 **v_coverage_stats 뷰 하나**다. 표 이름이 허용 목록에 슬쩍
        들어가면 "뷰만 연다"는 설계가 무너지고, 다음 요약표도 같은 논리로 열린다.
        """
        assert "mv_coverage_stats" not in post_load.ANON_READABLE_ALLOWLIST
        assert "mv_coverage_stats" not in post_load.ANON_CALLABLE_ALLOWLIST
        assert post_load.unexpected_anon_readables(["mv_coverage_stats"]) == [
            "mv_coverage_stats"
        ]


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

    def test_check_returns_1_when_something_is_exposed(self, monkeypatch, map_is_fresh, tx_window_is_fresh):
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "200|200" if "count(" in sql
                            else "v_floor_stack\nmv_search_parcel")
        assert post_load.main(["--check"]) == 1

    def test_check_returns_0_when_clean(self, monkeypatch, map_is_fresh, tx_window_is_fresh):
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "200|200" if "count(" in sql
                            else "v_floor_stack\nv_coverage_stats")
        assert post_load.main(["--check"]) == 0


# ── 7. 요약표를 **둘 다** 갱신하는가 (2026-08-13 2차 검증에서 잡힌 결함) ──────


class TestRefreshCoversBothSummaries:
    """⛔ mv_open_sigungu 가 빠져 있었다.

    그러면 새 구에 건물이 들어와도 **화면의 지역 목록에 안 나타나** 고를 수도, 검색할
    수도 없다. 에러가 안 나므로 아무도 모른다 — 그 지역이 원래 없는 것처럼 보인다.
    """

    def test_refreshes_both_matviews(self):
        sql = post_load.build_refresh_sql()
        for mv in ("mv_search_parcel", "mv_open_sigungu"):
            assert "refresh materialized view concurrently {};".format(mv) in sql, (
                "{} 가 갱신 대상에서 빠졌습니다".format(mv)
            )

    def test_refreshes_the_transaction_stats(self):
        """⛔ Stage A 의 구 단가 표(결정 0012)가 빠지면 **창(24개월)이 옛날에 굳은 채** 남는다.

        이것도 에러가 안 난다 — 새 실거래를 넣어도 화면 숫자가 그대로다.
        """
        assert "refresh materialized view concurrently mv_sigungu_tx_stats;" in (
            post_load.build_refresh_sql()
        )

    def test_order_matters_search_parcel_first(self):
        """mv_open_sigungu 는 mv_search_parcel 에서 만들어진다 — 순서가 바뀌면 한 박자 늦는다."""
        sql = post_load.build_refresh_sql()
        assert sql.index("mv_search_parcel") < sql.index("mv_open_sigungu")

    def test_refreshes_the_coverage_stats(self):
        """⛔ 각주 집계 사전계산(2026-08-22d)이 빠지면 각주가 **옛 적재 때 값에 굳는다**.

        이것도 에러가 안 난다 — 새 분기를 넣어도 화면 각주만 옛 숫자를 계속 말한다.
        (미리 계산해 두는 대가는 정확히 이것뿐이라, 갱신 목록에 있는지를 기계가 지킨다.)
        """
        assert "refresh materialized view concurrently mv_coverage_stats;" in (
            post_load.build_refresh_sql()
        )

    def test_coverage_stats_comes_after_open_sigungu(self):
        """mv_coverage_stats 는 mv_open_sigungu 를 읽는다("서비스 지역만 센다").

        앞에 두면 구가 늘어난 날 각주만 한 박자 낡은 범위를 센다.
        """
        sql = post_load.build_refresh_sql()
        assert sql.index("mv_open_sigungu") < sql.index("mv_coverage_stats")

    def test_all_are_concurrently(self):
        for line in post_load.build_refresh_sql().splitlines():
            assert line.startswith("refresh materialized view concurrently"), line


class TestAnonExposureCoversFunctions:
    """표·뷰만 보면 **함수가 열린 것을 놓친다**(2026-08-13: unit_business_append_only)."""

    def test_sql_asks_about_functions_too(self):
        sql = post_load.build_anon_exposure_sql()
        assert "has_function_privilege('anon'" in sql
        assert "pg_proc" in sql
        # ⚠️ **글자가 있는 것만으로는 부족하다.** 앞의 `union all` 을 `--` 로 바꾸면
        #    함수 절이 통째로 주석이 되는데 위 두 검사는 그대로 통과한다
        #    (2026-08-13 주입 시험에서 실제로 그렇게 샜다). 실제로 **합쳐지는지**를 본다.
        assert " union all " in sql, "표 절과 함수 절이 실제로 합쳐져야 합니다"
        assert "--" not in sql, "SQL 안에 주석이 있으면 그 뒤가 통째로 죽는다"

    def test_sql_excludes_extension_objects(self):
        """⛔ 확장이 만든 함수를 세면 PostGIS 수백 개가 "사고"로 잡혀 진짜 사고가 묻힌다.

        2026-08-13 실측: 제외 필터 없이 돌렸더니 경고 한 줄이 화면을 가득 채웠다.
        `pg_depend.deptype='e'` = "이 객체는 확장의 일부" — 그것만 빼면 우리 것만 남는다.
        """
        sql = post_load.build_anon_exposure_sql()
        assert sql.count("pg_depend") == 2, "표·함수 양쪽 모두에서 확장을 걸러야 합니다"
        assert "deptype = 'e'" in sql

    def test_screen_rpcs_are_allowed(self):
        assert post_load.unexpected_anon_readables(
            ["search_buildings", "search_scope", "list_open_sigungu", "v_floor_stack"]
        ) == []

    def test_flags_a_function_that_the_screen_never_calls(self):
        assert post_load.unexpected_anon_readables(["unit_business_append_only"]) == [
            "unit_business_append_only"
        ]

    def test_flags_helper_functions_if_they_reopen(self):
        """도우미 함수는 뷰가 저장 컬럼을 읽게 만들어 닫아 뒀다 — 다시 열리면 사고다."""
        assert post_load.unexpected_anon_readables(["building_display_nm", "mask_person_name"]) == [
            "building_display_nm",
            "mask_person_name",
        ]


# ── 8. 지도 상권 파일 신선도 (2026-08-14 신설 — 결정 0010) ──────────────────


class TestMapFreshness:
    """지도의 상권 면은 DB 가 아니라 **구워 둔 정적 파일**에서 읽는다.

    그래서 상권을 새로 적재하고 파일 굽기를 잊으면 **지도만** 옛날 상권을 계속 보여준다 —
    검색도 층별 화면도 멀쩡하고 에러도 안 나서, 이 검사가 없으면 아무도 모른다.
    """

    FIXED = "2020-01-01T00:00:00.000000Z"      # 의미 없는 고정 과거값(날짜 하드코딩 함정 회피)

    def test_matching_count_and_time_is_fresh(self):
        meta = {"district_cnt": 1687, "max_computed_at": self.FIXED}
        assert post_load.is_map_stale(meta, 1687, self.FIXED) is False

    def test_new_districts_loaded_but_file_not_rebaked(self):
        meta = {"district_cnt": 1650, "max_computed_at": self.FIXED}
        assert post_load.is_map_stale(meta, 1687, self.FIXED) is True

    def test_same_count_but_geometry_recomputed(self):
        """행수는 그대로인데 경계만 다시 계산된 경우 — 개수만 보면 못 잡는다."""
        meta = {"district_cnt": 1687, "max_computed_at": self.FIXED}
        assert post_load.is_map_stale(meta, 1687, "2021-06-01T00:00:00.000000Z") is True

    def test_missing_file_is_stale_not_ok(self):
        """"파일이 없으니 검사할 게 없다"고 넘어가면 텅 빈 지도를 정상이라 보고하게 된다."""
        assert post_load.is_map_stale(None, 1687, self.FIXED) is True

    def test_broken_meta_is_stale(self):
        assert post_load.is_map_stale({"district_cnt": "어쩌구"}, 1687, self.FIXED) is True
        assert post_load.is_map_stale({}, 1687, self.FIXED) is True

    def test_accepts_strings_from_psql(self):
        """psql -tA 는 문자열을 준다 — '1687' 과 1687 을 다르다고 하면 안 된다."""
        meta = {"district_cnt": 1687, "max_computed_at": self.FIXED}
        assert post_load.is_map_stale(meta, "1687", self.FIXED) is False

    def test_uses_the_bakers_own_sql_so_the_two_sides_cannot_drift(self):
        """등식의 양쪽(굽는 쪽·검사하는 쪽)이 **같은 SQL** 을 써야 한다.

        따로 적어 두면 한쪽만 고쳤을 때 자료가 그대로인데도 영영 "낡음"이 뜬다.
        """
        assert (post_load.build_district_geojson.build_meta_sql()
                == post_load.build_district_geojson.build_meta_sql())
        assert "at time zone 'UTC'" in post_load.build_district_geojson.build_meta_sql()

    def test_check_returns_1_when_the_map_file_is_stale(self, monkeypatch, tx_window_is_fresh):
        """요약표·권한이 다 정상이어도 지도가 낡았으면 종료 코드 1 이어야 한다."""
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "200|200" if "count(" in sql else "v_floor_stack")
        monkeypatch.setattr(post_load.build_district_geojson, "read_meta",
                            lambda *a, **k: {"district_cnt": 1, "max_computed_at": "옛날"})
        assert post_load.main(["--check"]) == 1

    def test_check_returns_0_when_the_map_file_matches(self, monkeypatch, tx_window_is_fresh):
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "200|200" if "count(" in sql else "v_floor_stack")
        monkeypatch.setattr(post_load.build_district_geojson, "read_meta",
                            lambda *a, **k: {"district_cnt": 200, "max_computed_at": "200"})
        assert post_load.main(["--check"]) == 0

    def test_apply_checks_the_map_but_never_bakes_it(self, monkeypatch, tx_window_is_fresh):
        """⚠️ 굽기까지 대신 하면 안 된다 — git 에 커밋하는 자산이라 사람이 봐야 한다.

        본 실행이 조용히 파일을 새로 쓰면, 커밋 안 된 생성물이 워킹트리에 쌓인다.
        """
        monkeypatch.setattr(post_load.dbx, "run_sql", lambda sql, **k: 0)
        monkeypatch.setattr(post_load, "query_one", lambda sql: "200|200")
        monkeypatch.setattr(post_load.build_district_geojson, "read_meta",
                            lambda *a, **k: {"district_cnt": 200, "max_computed_at": "200"})
        monkeypatch.setattr(post_load.build_district_geojson, "main",
                            lambda *a, **k: pytest.fail("post_load 가 지도 파일을 구우면 안 됩니다"))
        assert post_load.main([]) == 0

    def test_apply_returns_1_when_the_map_is_left_stale(self, monkeypatch, capsys, tx_window_is_fresh):
        """낡은 채로 끝났으면 성공으로 보고하면 안 된다 — 명령을 안내해야 한다."""
        monkeypatch.setattr(post_load.dbx, "run_sql", lambda sql, **k: 0)
        monkeypatch.setattr(post_load, "query_one", lambda sql: "200|200")
        monkeypatch.setattr(post_load.build_district_geojson, "read_meta",
                            lambda *a, **k: None)
        assert post_load.main([]) == 1
        assert "build_district_geojson.py" in capsys.readouterr().out
