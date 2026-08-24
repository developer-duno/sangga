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
import re
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


@pytest.fixture
def coverage_is_fresh(monkeypatch):
    """각주 집계 검사만 빼고 본다 (위 둘과 같은 이유 — 관심사 분리).

    이 stub 이 없으면 `main()` 이 라이브 mv_coverage_stats 를 물으러 가거나, mock 된
    query_one 의 엉뚱한 답을 분기로 오해한다. 판정 자체는 TestCoverageStale 이 따로 본다.
    """
    monkeypatch.setattr(post_load, "report_coverage_freshness",
                        lambda: ("202606", "202606", False))


@pytest.fixture
def industry_mix_is_fresh(monkeypatch):
    """업종 분포 표 검사만 빼고 본다 (위 셋과 같은 이유 — 관심사 분리).

    이 stub 이 없으면 `main()` 이 mock 된 query_one 의 엉뚱한 답("v_floor_stack" 등)을
    분기로 오해해 이 반의 관심사와 상관없이 흔들린다. 판정 자체는 아래
    TestIndustryMixStale 이 따로 본다.
    """
    monkeypatch.setattr(post_load, "report_industry_mix_freshness",
                        lambda: ("202606", "202606", False))


@pytest.fixture
def no_anon_writes(monkeypatch):
    """공개 롤 쓰기권한 점검만 빼고 본다 (위 넷과 같은 이유 — 관심사 분리).

    이 stub 이 없으면 `main()` 이 mock 된 query_one 의 엉뚱한 답("v_floor_stack" 등)을
    **쓸 수 있는 표 이름**으로 오해해 이 반의 관심사와 상관없이 결과가 흔들린다.
    판정 자체는 아래 TestWriteExposure 가 따로 본다.
    """
    monkeypatch.setattr(post_load, "report_write_exposure", lambda: [])


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
    def test_check_returns_1_when_stale(
        self, monkeypatch, map_is_fresh, tx_window_is_fresh, coverage_is_fresh,
        industry_mix_is_fresh, no_anon_writes
    ):
        """CI·다른 스크립트가 종료 코드로 받아 쓸 수 있어야 한다."""
        monkeypatch.setattr(post_load, "query_one", lambda sql: "100|200")
        assert post_load.main(["--check"]) == 1

    def test_check_returns_0_when_fresh(
        self, monkeypatch, map_is_fresh, tx_window_is_fresh, coverage_is_fresh,
        industry_mix_is_fresh, no_anon_writes
    ):
        # --check 는 일곱 가지를 묻는다(요약표 신선도 · 지도 파일 · 실거래 창 ·
        # 각주 집계 · 업종 분포 · 공개키 읽기 · 공개키 쓰기) — mock 도 갈라 답해야 한다.
        # 여기 관심사는 앞의 하나뿐이라 나머지는 fixture 로 빼 둔다.
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "200|200" if "count(" in sql else "v_floor_stack")
        assert post_load.main(["--check"]) == 0

    def test_check_never_writes(
        self, monkeypatch, map_is_fresh, tx_window_is_fresh, coverage_is_fresh,
        industry_mix_is_fresh, no_anon_writes
    ):
        """--check 는 읽기만 해야 한다 — 실수로 갱신을 돌리면 안 된다."""
        calls = []
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "200|200" if "count(" in sql else "v_floor_stack")
        monkeypatch.setattr(post_load.dbx, "run_sql",
                            lambda *a, **k: calls.append(a) or 0)
        post_load.main(["--check"])
        assert calls == []

    def test_apply_runs_analyze_then_refresh_then_rechecks(
        self, monkeypatch, map_is_fresh, tx_window_is_fresh, coverage_is_fresh,
        industry_mix_is_fresh
    ):
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

    def test_output_survives_being_piped_to_a_file(
        self, monkeypatch, map_is_fresh, tx_window_is_fresh, coverage_is_fresh,
        industry_mix_is_fresh, no_anon_writes
    ):
        """⛔ 리다이렉트(`> 파일`)·파이프·CI 로그에서 죽지 않아야 한다 (2026-08-22 실측).

        콘솔에 바로 찍을 때는 멀쩡하던 것이 `> 파일` 로 넘기는 순간 파이썬이 cp949 로
        인코딩해 **em dash(—) 한 글자에서 통째로 터졌다.** 그것도 점검을 다 마치고
        결과를 찍는 도중이라, 종료 코드만 보면 "점검 실패"로 오해하게 된다.
        형제 스크립트들(build_district_geojson.py 등)이 쓰는 처방을 여기도 건다.
        """
        calls = []

        class FakeStdout:
            def isatty(self):
                return False

            def reconfigure(self, **kw):
                calls.append(kw)

            def write(self, s):
                return len(s)

            def flush(self):
                pass

        monkeypatch.setattr(sys, "stdout", FakeStdout())
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "200|200" if "count(" in sql else "v_floor_stack")
        post_load.main(["--check"])
        assert calls == [{"encoding": "utf-8", "errors": "replace"}], (
            "파이프로 넘길 때 stdout 을 UTF-8 로 다시 잡지 않으면 한글 출력이 죽는다"
        )

    def test_apply_stops_when_analyze_fails(self, monkeypatch):
        """앞이 실패했는데 뒤를 계속 돌면 '성공했다'는 착각이 남는다."""
        monkeypatch.setattr(post_load.dbx, "run_sql", lambda sql, **k: 2)
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: pytest.fail("실패했는데 신선도를 재면 안 됩니다"))
        assert post_load.main([]) == 2

    def test_apply_reports_failure_when_still_stale_after_refresh(
        self, monkeypatch, map_is_fresh, tx_window_is_fresh, coverage_is_fresh,
        industry_mix_is_fresh
    ):
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


# ── 5-c. 업종 분포 표 신선도 (2026-08-22 신설 — 결정 0014) ─────────────────


class TestIndustryMixStale:
    """이 표는 "최신 분기"를 담는데, 어느 분기가 최신인지는 **구울 때** 굳는다.

    갱신을 빼먹으면 층별 화면의 업종 분포만 옛 분기를 말한다. 더 고약한 것은 화면에
    적히는 "○○년 ○분기 기준" 문구도 그 옛 분기를 **정직히** 말한다는 점이다 — 화면만
    보면 아무 이상이 없어 보인다. 그래서 표와 원본을 등식으로 견준다.
    """

    def test_same_quarter_is_fresh(self):
        assert post_load.is_industry_mix_stale("202606", "202606") is False

    def test_older_quarter_is_stale(self):
        assert post_load.is_industry_mix_stale("202603", "202606") is True

    def test_empty_table_is_stale(self):
        """굽지 않았으면 화면에서 섹션이 통째로 사라진다 — 조용한 실종이라 잡아야 한다."""
        assert post_load.is_industry_mix_stale("", "202606") is True
        assert post_load.is_industry_mix_stale(None, "202606") is True

    def test_no_store_data_is_not_stale(self):
        """점포 자료가 아예 없는 새 환경에서 헛경보를 내지 않는다 — 견줄 것이 없다."""
        assert post_load.is_industry_mix_stale("", "") is False
        assert post_load.is_industry_mix_stale(None, None) is False

    def test_whitespace_is_trimmed_not_treated_as_drift(self):
        """char(6) 컬럼이라 psql 이 공백을 붙여 줄 수 있다 — 그걸 낡음으로 오판하면 안 된다."""
        assert post_load.is_industry_mix_stale(" 202606 ", "202606") is False

    def test_check_returns_1_when_industry_mix_is_stale(
        self, monkeypatch, map_is_fresh, tx_window_is_fresh, coverage_is_fresh,
        no_anon_writes
    ):
        """⛔ 업종 분포만 낡아도 --check 는 1 이어야 한다.

        이 배선이 빠지면 판정 함수가 아무리 정확해도 아무도 안 물어본다
        (바로 아래 각주 집계 반이 같은 이유로 두는 시험과 한 쌍이다).
        """
        monkeypatch.setattr(
            post_load, "query_one",
            lambda sql: ("202603|202606" if "mv_district_industry_mix" in sql
                         else ("200|200" if "count(" in sql else "v_floor_stack")))
        assert post_load.main(["--check"]) == 1


# ── 5-d. 각주 집계 신선도 (2026-08-22d 신설 — 사전계산의 유일한 대가) ────────


class TestCoverageStale:
    """각주 집계는 갱신하는 순간 계산돼 굳는다.

    2026-08-22d 부터 이 값을 미리 계산해 둔다(실시간 집계는 277만 행 대조로 2~5초라
    공개 호출의 3초 제한을 넘나들었다). 미리 계산해 두는 값이 치르는 대가는 정확히
    하나 — **갱신을 잊으면 조용히 낡는다.** 그 하나를 여기서 등식으로 잡는다.
    """

    def test_same_quarter_is_fresh(self):
        assert post_load.is_coverage_stale("202606", "202606") is False

    def test_different_quarter_is_stale(self):
        """새 분기를 적재하고 post_load 를 안 돌린 상태 — 각주만 옛 결측률을 말한다."""
        assert post_load.is_coverage_stale("202603", "202606") is True

    def test_empty_table_is_stale(self):
        """표가 비어 있으면 각주가 통째로 사라진다 — '검사할 게 없다'로 넘기면 안 된다."""
        assert post_load.is_coverage_stale("", "202606") is True
        assert post_load.is_coverage_stale(None, "202606") is True

    def test_missing_source_is_stale(self):
        """대조할 기준이 없으면 '신선하다'고 말할 근거도 없다."""
        assert post_load.is_coverage_stale("202606", "") is True

    def test_whitespace_is_trimmed(self):
        """psql 출력에는 공백이 섞인다 — 안 다듬으면 같은 분기를 다르다고 본다."""
        assert post_load.is_coverage_stale(" 202606 ", "202606") is False

    def test_sql_compares_the_matview_against_the_source(self):
        """엉뚱한 표를 물으면 판정이 통째로 헛돈다."""
        sql = post_load.build_coverage_freshness_sql()
        assert "mv_coverage_stats" in sql
        assert "unit_business" in sql

    def test_check_returns_1_when_coverage_is_stale(
        self, monkeypatch, map_is_fresh, tx_window_is_fresh, industry_mix_is_fresh,
        no_anon_writes
    ):
        """⛔ 각주만 낡아도 --check 는 1 이어야 한다.

        이 배선이 빠지면 판정 함수가 아무리 정확해도 아무도 안 물어본다 — 2026-08-22
        독립 리뷰가 잡은 구멍이 정확히 그 형태였다(사전계산으로 바꿔 놓고 낡음 검사는 안 붙임).
        """
        monkeypatch.setattr(
            post_load, "query_one",
            lambda sql: ("202603|202606" if "mv_coverage_stats" in sql
                         else ("200|200" if "count(" in sql else "v_floor_stack")))
        assert post_load.main(["--check"]) == 1


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
            "list_industry_mix", "list_industry_detail",
            # ⚠️ 이 목록에서 **유일하게 쓰는** 함수다(2026-08-24b 의견함·오류 기록).
            #    나머지 아홉은 전부 읽기라, 여기가 늘 때는 "무엇이 들어오나"를 한 번 더
            #    본다 — 표가 아니라 함수인지, 넣기만 하는지, 읽는 길은 없는지.
            "submit_feedback",
        )

    def test_the_feedback_table_is_never_allowed(self):
        """⛔ 의견함의 **표**가 허용 목록에 들어가면 안 된다(2026-08-24b).

        화면은 넣기 전용 함수 하나로만 쓴다. 표가 열리면 두 가지가 한꺼번에 무너진다:
          · select 가 열리면 **남이 남긴 글을 아무나 읽는다**(본문에 연락처를 적어 넣은
            사람이 있을 수 있다 — 우리가 요구하지 않았을 뿐 막을 수는 없다).
          · insert 가 열리면 함수 안의 상한·모양 검사를 통째로 건너뛴다.
        2026-08-13 사고(mv_search_parcel 200)와 같은 형태이므로 형제들과 같은 방식으로 막는다.
        """
        assert "app_feedback" not in post_load.ANON_READABLE_ALLOWLIST
        assert "app_feedback" not in post_load.ANON_CALLABLE_ALLOWLIST
        assert post_load.unexpected_anon_readables(["app_feedback"]) == ["app_feedback"]

    def test_the_industry_matview_is_never_allowed(self):
        """⛔ 업종 분포의 사전계산표가 허용 목록에 들어가면 안 된다(결정 0014).

        화면은 함수 둘로만 읽는다. 표가 열리면 상호명은 안 나가더라도 **전국 상권의
        업종 구성이 통째로** REST 페이지네이션으로 긁힌다 — 2026-08-13 사고
        (mv_search_parcel 200)와 같은 형태다.
        """
        assert "mv_district_industry_mix" not in post_load.ANON_READABLE_ALLOWLIST
        assert "mv_district_industry_mix" not in post_load.ANON_CALLABLE_ALLOWLIST
        assert post_load.unexpected_anon_readables(["mv_district_industry_mix"]) == [
            "mv_district_industry_mix"
        ]

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

    def test_sql_asks_about_anon_and_both_schemas(self):
        sql = post_load.build_anon_exposure_sql()
        assert "has_table_privilege('anon'" in sql
        # ⚠️ 2026-08-22e 부터 노출면이 public 에서 api 로 옮겨 간다. 한쪽만 물으면
        #    전환 전(api 만 봄) 또는 전환 후(public 만 봄) 중 하나를 통째로 못 본다.
        # 표 절·함수 절 **양쪽 모두** 두 스키마를 물어야 한다(한쪽만 고치면 반쪽이 된다).
        assert sql.count("nspname in ('public','api')") == 2
        assert "n.nspname in ('public','api')" in sql
        assert "n2.nspname in ('public','api')" in sql
        # 물질화뷰('m')가 빠지면 2026-08-13 사고를 그대로 놓친다.
        assert "'m'" in sql

    def test_check_returns_1_when_something_is_exposed(
        self, monkeypatch, map_is_fresh, tx_window_is_fresh, coverage_is_fresh,
        industry_mix_is_fresh, no_anon_writes
    ):
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "200|200" if "count(" in sql
                            else "v_floor_stack\nmv_search_parcel")
        assert post_load.main(["--check"]) == 1

    def test_the_same_name_in_both_schemas_is_counted_once(self, monkeypatch, capsys):
        """api 뷰·래퍼는 public 과 **같은 이름**이다 — 두 번 세면 안 된다(2026-08-22e).

        그대로 세면 "허용된 11개"가 22개로 보여, 숫자가 늘어난 것이 사고인지 이사인지
        구분이 안 된다. 판정(bad)은 이름 기준이라 어차피 같으므로 세는 쪽만 맞춘다.
        """
        monkeypatch.setattr(
            post_load, "query_one",
            lambda sql: "v_floor_stack\nv_coverage_stats\nv_floor_stack\nv_coverage_stats",
        )
        names, bad = post_load.report_anon_exposure()
        assert names == ["v_coverage_stats", "v_floor_stack"]
        assert bad == []
        assert "허용된 2개" in capsys.readouterr().out

    def test_check_returns_0_when_clean(
        self, monkeypatch, map_is_fresh, tx_window_is_fresh, coverage_is_fresh,
        industry_mix_is_fresh, no_anon_writes
    ):
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

    def test_refreshes_the_industry_mix(self):
        """⛔ 업종 분포 표(결정 0014)가 빠지면 **분기가 옛날에 굳은 채** 남는다.

        이 표는 "최신 분기"를 담는데 그 분기가 무엇인지는 구울 때 정해진다. 안 돌리면
        새 분기를 적재해도 층별 화면의 업종 분포만 옛 분기를 말한다 — 게다가 화면의
        "○○년 ○분기 기준" 문구도 그 옛 분기를 정직히 말하므로 아무도 눈치채지 못한다.
        """
        assert "refresh materialized view concurrently mv_district_industry_mix;" in (
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

    def test_every_refreshed_matview_has_a_unique_index(self):
        """⛔ `concurrently` 는 **unique 인덱스가 있어야만** 돈다.

        없으면 갱신이 `ERROR: cannot refresh materialized view ... concurrently` 로
        실패한다 — 적재 마무리가 통째로 멈춘다. 위 test_all_are_concurrently 가
        "concurrently 로 부르는지"를 지키니, 여기서는 **그게 성립할 조건**을 지킨다.
        둘이 짝이라 한쪽만 있으면 목록에 새 요약표를 더할 때 조용히 깨진다.
        """
        schema_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "supabase", "schema.sql",
        )
        with open(schema_path, encoding="utf-8") as f:
            schema = f.read()
        for mv in post_load.REFRESH_MVS:
            pattern = (
                r"(?im)^create\s+unique\s+index\s+(?:concurrently\s+)?"
                r"(?:if\s+not\s+exists\s+)?\w+\s+on\s+{}\b".format(re.escape(mv))
            )
            assert re.search(pattern, schema), (
                "{} 에 unique 인덱스가 schema.sql 에 없습니다 — "
                "concurrently 갱신이 실패합니다.".format(mv)
            )


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
        # ⚠️ classid 한정이 빠지면 oid 가 우연히 같은 **남의 카탈로그 항목** 때문에 우리
        #    표·함수가 "확장이 만든 것"으로 오인돼 점검에서 통째로 빠질 수 있다.
        assert "d.classid = 'pg_class'::regclass" in sql
        assert "d.classid = 'pg_proc'::regclass" in sql

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


class TestWriteExposure:
    """⛔ 읽기 허용과 쓰기 허용은 다르다 (2026-08-22 독립 리뷰 B-2).

    위 읽기 점검은 **허용 목록**으로 판정한다. 그래서 `v_floor_stack` 처럼 목록에 있는
    이름에 INSERT·UPDATE·DELETE 가 붙어도 조용히 통과한다 — 읽혀도 되는 것과 공개키로
    고쳐도 되는 것은 전혀 다른 이야기인데, 그 차이를 아무도 안 물어보고 있었다.

    ⚠️ 이 점검에는 **확장 제외 필터가 없다.** 읽기 쪽에서 걸러 내던 그 집합이 여기서는
       정확히 실제 노출이기 때문이다 — PostGIS 가 public 스키마에 설치돼 spatial_ref_sys
       등 셋이 REST 로 그대로 딸려 나온다(라이브 실측). 대신 이름으로 갈라, 그 셋만
       나오면 [주의]로 적고 종료 코드는 0 을 지킨다(우리 권한으로 못 고치는 것이라
       매번 1 이면 --check 가 쓸모없어진다). 목록 밖이면 [사고] + 1 이다.
    """

    def test_sql_asks_both_public_roles_about_all_three_privileges(self):
        """anon 만 재면 로그인 사용자에게만 열린 쓰기를 통째로 놓친다."""
        sql = post_load.build_write_exposure_sql()
        for role in ("anon", "authenticated"):
            for priv in ("INSERT", "UPDATE", "DELETE"):
                assert "has_table_privilege('{}', c.oid, '{}')".format(role, priv) in sql, (
                    "{} 의 {} 를 안 물으면 그 조합만 열린 상태를 놓칩니다".format(role, priv)
                )
        # 여섯 중 **하나라도** 있으면 걸려야 한다 — and 로 묶으면 전부 열린 경우만 잡는다.
        assert " and has_table_privilege" not in sql
        assert sql.count(" or has_table_privilege") == 5

    def test_sql_scope_matches_the_read_check(self):
        """스코프가 갈라지면 한쪽만 보는 반쪽 점검이 된다 — 같은 자를 쓴다."""
        sql = post_load.build_write_exposure_sql()
        assert "nspname in ('public','api')" in sql
        assert "c.relkind in ('r','v','m','p')" in sql
        assert "--" not in sql, "SQL 안에 주석이 있으면 그 뒤가 통째로 죽는다"

    def test_sql_does_not_filter_out_extension_objects(self):
        """⛔ 여기서 확장을 제외하면 **진짜 노출을 걸러 낸다**(2026-08-22 리뷰 HIGH).

        라이브 실측: spatial_ref_sys(표)·geometry_columns·geography_columns(뷰) 셋에
        쓰기가 붙어 있고 REST 로 닿는다. 셋 다 PostGIS 산출물이라 `deptype='e'` 필터를
        그대로 옮겨 왔다면 점검이 **영원히 조용한** 상태가 됐을 것이다.
        """
        assert "deptype" not in post_load.build_write_exposure_sql()

    def test_nothing_open_is_quiet(self):
        assert post_load.split_writables([]) == ([], [])
        assert post_load.split_writables(["", "  "]) == ([], [])

    def test_even_an_allowlisted_name_is_an_accident(self):
        """⛔ 이 점검의 핵심 — 읽기 허용 목록에 있는 이름이라도 쓰기가 붙으면 사고다."""
        assert "v_floor_stack" in post_load.ANON_READABLE_ALLOWLIST
        assert post_load.split_writables(["v_floor_stack"]) == ([], ["v_floor_stack"])

    def test_flags_raw_tables(self):
        assert post_load.split_writables(["unit_business", "parcel"]) == (
            [], ["parcel", "unit_business"]
        )

    def test_known_postgis_names_are_not_counted_as_accidents(self):
        """우리 권한으로 못 고치는 셋은 [주의]지 [사고]가 아니다."""
        known, bad = post_load.split_writables(list(post_load.WRITE_KNOWN_POSTGIS))
        assert bad == []
        assert set(known) == set(post_load.WRITE_KNOWN_POSTGIS)

    def test_report_says_accident_and_returns_only_unknown_names(self, monkeypatch, capsys):
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "parcel\nspatial_ref_sys\nv_floor_stack")
        bad = post_load.report_write_exposure()
        assert bad == ["parcel", "v_floor_stack"], "알려진 셋은 종료 코드를 흔들지 않는다"
        out = capsys.readouterr().out
        assert "[사고]" in out
        assert "revoke insert, update, delete" in out
        # 알려진 것도 같은 실행에서 함께 적힌다 — 사고에 묻혀 사라지면 안 된다.
        assert "[주의]" in out and "spatial_ref_sys" in out

    def test_report_warns_about_the_known_three_and_never_says_just_none(
        self, monkeypatch, capsys
    ):
        """알려진 셋만 열려 있을 때: 종료 코드는 0, 그러나 **말은 한다**."""
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "\n".join(post_load.WRITE_KNOWN_POSTGIS))
        assert post_load.report_write_exposure() == []
        out = capsys.readouterr().out
        assert "[사고]" not in out
        assert "우리가 만든 것 중에는" in out, "범위를 안 밝힌 '없습니다'는 [주의] 셋과 앞뒤가 안 맞는다"
        assert "[주의]" in out
        for name in post_load.WRITE_KNOWN_POSTGIS:
            assert name in out
        # 못 고치는 이유와 근본 처방이 함께 적혀야 사람이 헛되이 revoke 를 시도하지 않는다.
        assert "supabase_admin" in out
        assert "2026-08-08" in out
        assert "public" in out

    def test_public_rest_exposed_pure_function(self):
        """옛 문(public) 노출 판정 — 항목 단위 비교여야 한다.

        ⚠️ 'graphql_public' 안에도 'public' 이 글자로 들어 있다 — 부분 문자열 판정이면
           문을 닫고도 계속 [주의]가 찍히는 가짜 경고가 된다.
        """
        assert post_load.public_rest_exposed("pgrst.db_schemas=api, public, graphql_public") is True
        assert post_load.public_rest_exposed("pgrst.db_schemas=api, graphql_public") is False
        assert post_load.public_rest_exposed("pgrst.db_schemas=graphql_public") is False
        # 설정 줄이 아예 없으면(빈 값 포함) 노출로 간주 — 모르는 상태는 안전이 아니다.
        assert post_load.public_rest_exposed("statement_timeout=8s") is True
        assert post_load.public_rest_exposed("") is True
        assert post_load.public_rest_exposed(None) is True

    def test_report_downgrades_to_normal_when_public_door_is_closed(
        self, monkeypatch, capsys
    ):
        """옛 문을 닫았으면(2026-08-24) 알려진 셋은 [주의]가 아니라 [정상]으로 적는다."""
        def fake_query(sql):
            if "rolconfig" in sql:
                return "pgrst.db_schemas=api, graphql_public"
            return "\n".join(post_load.WRITE_KNOWN_POSTGIS)
        monkeypatch.setattr(post_load, "query_one", fake_query)
        assert post_load.report_write_exposure() == []
        out = capsys.readouterr().out
        assert "[주의]" not in out
        assert "인터넷에서는 닿지 않습니다" in out
        for name in post_load.WRITE_KNOWN_POSTGIS:
            assert name in out, "닫혔어도 이름은 계속 보인다 — 조용해지면 아무도 안 묻게 된다"

    def test_report_warns_again_if_public_door_is_reopened(self, monkeypatch, capsys):
        """역회귀 가드 — 누가 노출에 public 을 되돌리면 [주의]가 다시 살아난다."""
        def fake_query(sql):
            if "rolconfig" in sql:
                return "pgrst.db_schemas=api, public, graphql_public"
            return "\n".join(post_load.WRITE_KNOWN_POSTGIS)
        monkeypatch.setattr(post_load, "query_one", fake_query)
        post_load.report_write_exposure()
        out = capsys.readouterr().out
        assert "[주의]" in out
        assert "되돌린 것" in out

    def test_report_is_quiet_when_nothing_at_all_is_writable(self, monkeypatch, capsys):
        """열린 것이 하나도 없으면 [주의]도 안 찍는다 — 없는 경고는 하지 않는다."""
        monkeypatch.setattr(post_load, "query_one", lambda sql: "")
        assert post_load.report_write_exposure() == []
        out = capsys.readouterr().out
        assert "[정상]" in out
        assert "[주의]" not in out

    def test_check_returns_0_when_only_the_known_three_are_writable(
        self, monkeypatch, map_is_fresh, tx_window_is_fresh, coverage_is_fresh,
        industry_mix_is_fresh
    ):
        """알려진 셋 때문에 --check 가 매번 1 이면 아무도 안 보게 된다."""
        monkeypatch.setattr(
            post_load, "query_one",
            lambda sql: ("\n".join(post_load.WRITE_KNOWN_POSTGIS) if "INSERT" in sql
                         else ("200|200" if "count(" in sql else "v_floor_stack")))
        assert post_load.main(["--check"]) == 0

    def test_check_returns_1_when_something_new_is_writable(
        self, monkeypatch, map_is_fresh, tx_window_is_fresh, coverage_is_fresh,
        industry_mix_is_fresh
    ):
        """⛔ 판정이 아무리 정확해도 --check 에 배선이 안 되면 아무도 안 물어본다.

        읽기 쪽은 **허용된 것만** 열린 상태로 두고(그래서 읽기 점검은 조용하다), 쓰기만
        열린 상태를 흉내 낸다 — 그 하나로 종료 코드가 1 이 되어야 한다.
        """
        monkeypatch.setattr(
            post_load, "query_one",
            lambda sql: ("v_floor_stack" if "INSERT" in sql
                         else ("200|200" if "count(" in sql else "v_floor_stack")))
        assert post_load.main(["--check"]) == 1

    def test_apply_does_not_ask_about_permissions(self, monkeypatch):
        """`--check` 없이 돌릴 때는 권한을 안 묻는다 — 읽기 점검과 같은 자리다.

        (적재 마무리는 갱신이 일이고, 권한 점검은 --check 의 일이다. 여기서 물으면
        갱신 경로에 라이브 조회가 하나 더 붙는다.)
        """
        monkeypatch.setattr(post_load.dbx, "run_sql", lambda sql, **k: 0)
        asked = []
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: asked.append(sql) or "200|200")
        monkeypatch.setattr(post_load, "report_map_freshness", lambda: ({}, False))
        monkeypatch.setattr(post_load, "report_tx_window_freshness",
                            lambda: ("202408", "202408", False))
        monkeypatch.setattr(post_load, "report_coverage_freshness",
                            lambda: ("202606", "202606", False))
        monkeypatch.setattr(post_load, "report_industry_mix_freshness",
                            lambda: ("202606", "202606", False))
        post_load.main([])
        assert not any("has_table_privilege" in s for s in asked)


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

    def test_check_returns_1_when_the_map_file_is_stale(
        self, monkeypatch, tx_window_is_fresh, industry_mix_is_fresh
    ):
        """요약표·권한이 다 정상이어도 지도가 낡았으면 종료 코드 1 이어야 한다."""
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: "200|200" if "count(" in sql else "v_floor_stack")
        monkeypatch.setattr(post_load.build_district_geojson, "read_meta",
                            lambda *a, **k: {"district_cnt": 1, "max_computed_at": "옛날"})
        assert post_load.main(["--check"]) == 1

    def test_check_returns_0_when_the_map_file_matches(
        self, monkeypatch, tx_window_is_fresh, coverage_is_fresh, industry_mix_is_fresh,
        no_anon_writes
    ):
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
