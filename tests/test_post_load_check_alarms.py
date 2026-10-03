# -*- coding: utf-8 -*-
"""`post_load.py --check` 의 경보 셋(2026-09-27 P7) — DB 없이 픽스처로만 본다.

  ① 느려짐 — **지난 점검 이후** 평균이 1초를 넘으면 [주의](종료 코드 1 아님)
  ② 정본 색인 — schema.sql 의 색인이 라이브에 없거나 invalid 면 [사고]
     (2026-10-02 보탬: INCLUDE 칸이 다르면 [사고] · 라이브에만 있는 색인은 [주의])
  ③ 정본↔라이브 함수 — 언어·본문 md5·설정이 다르면 [사고]

각 판정은 순수 함수로 떼어 두었으므로 여기서는 그 함수들을 직접 친다.
"""

import hashlib
import io
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
D = chr(36) * 2


def read_schema():
    with io.open(SCHEMA, encoding="utf-8") as fh:
        return fh.read()


def entry(fn, calls, total_ms, since="1756000000"):
    return {"fn": fn, "calls": calls, "total_ms": float(total_ms), "since": since}


# ── ① 느려짐 경보 ────────────────────────────────────────────────────────────


class TestSlowDiff:
    def test_first_run_only_saves_a_baseline(self):
        """직전 스냅샷이 없으면 비교하지 않는다 — 전부 기준만."""
        cur = {"1:10": entry("get_data_freshness", 59, 59 * 2330.8)}
        per_fn, rebased = post_load.diff_api_stats(None, cur)
        assert per_fn == {}
        assert rebased == 1

    def test_high_cumulative_mean_but_fast_since_last_check_is_quiet(self):
        """⛔ 누적 평균 2,412ms 짜리도 **그 사이** 호출이 빨랐으면 경보가 없어야 한다.

        색인을 고친 신선도 함수가 그 예다(누적 2,412ms · 색인 뒤 12~16ms).
        """
        prev = {"1:10": entry("get_data_freshness", 59, 59 * 2412.0)}
        cur = {"1:10": entry("get_data_freshness", 62, 59 * 2412.0 + 3 * 15.0)}
        per_fn, rebased = post_load.diff_api_stats(prev, cur, 1756000100)
        assert rebased == 0
        assert per_fn["get_data_freshness"][0] == 3
        assert post_load.slow_functions(per_fn) == []

    def test_mean_1001ms_since_last_check_alarms(self):
        prev = {"1:10": entry("list_price_bands", 10, 1000.0)}
        cur = {"1:10": entry("list_price_bands", 11, 2001.0)}
        per_fn, _ = post_load.diff_api_stats(prev, cur, 1756000100)
        slow = post_load.slow_functions(per_fn)
        assert [(f, c) for f, c, _ in slow] == [("list_price_bands", 1)]
        assert slow[0][2] == pytest.approx(1001.0)

    def test_exactly_1000ms_is_not_over(self):
        """기준은 '초과'다 — 딱 1,000ms 는 경보가 아니다."""
        assert post_load.slow_functions({"x": [2, 2000.0]}) == []

    def test_stats_since_changed_before_last_check_is_a_reset_not_a_comparison(self):
        """통계가 초기화됐는데 그 시각이 직전 점검 **앞**이면 언제 쌓였는지 몰라 안 센다."""
        prev = {"1:10": entry("search_buildings", 50, 5000.0, since="1756000000")}
        cur = {"1:10": entry("search_buildings", 60, 600000.0, since="1756000050")}
        per_fn, rebased = post_load.diff_api_stats(prev, cur, 1756000100)
        assert per_fn == {}
        assert rebased == 1

    def test_calls_decreased_is_a_reset(self):
        prev = {"1:10": entry("search_buildings", 50, 5000.0)}
        cur = {"1:10": entry("search_buildings", 40, 400000.0)}
        per_fn, rebased = post_load.diff_api_stats(prev, cur, 1756000100)
        assert per_fn == {}
        assert rebased == 1

    def test_new_row_born_after_last_check_counts_whole(self):
        prev = {}
        cur = {"1:11": entry("search_stores", 4, 8000.0, since="1756000200")}
        per_fn, rebased = post_load.diff_api_stats(prev, cur, 1756000100)
        assert per_fn == {"search_stores": [4, 8000.0]}
        assert rebased == 0

    def test_row_evicted_and_reborn_after_last_check_counts_whole(self):
        """⛔ 밀려났다 다시 생긴 줄 — stats_since 가 바뀌었지만 직전 점검 **뒤**라 통째로 센다.

        라이브 pg_stat_statements 는 5,000 줄 상한에 4,888 줄이라(2026-09-27) 곧 밀어내기가 시작된다.
        이걸 기준만 잡으면 드물게 불리는 느린 함수는 매번 밀려났다 돌아와 **영영 안 울린다**.
        """
        prev = {"1:10": entry("list_price_bands", 50, 5000.0, since="1756000000")}
        cur = {"1:10": entry("list_price_bands", 2, 4000.0, since="1756000150")}
        per_fn, rebased = post_load.diff_api_stats(prev, cur, 1756000100)
        assert per_fn == {"list_price_bands": [2, 4000.0]}
        assert rebased == 0
        assert [f for f, _, _ in post_load.slow_functions(per_fn)] == ["list_price_bands"]

    def test_new_row_older_than_last_check_is_baseline_only(self):
        """직전에 없었는데 나이는 더 많은 줄(밀려났다 돌아온 것 등)은 언제 쌓였는지 모른다."""
        cur = {"1:11": entry("search_stores", 4, 8000.0, since="1756000000")}
        per_fn, rebased = post_load.diff_api_stats({}, cur, 1756000100)
        assert per_fn == {}
        assert rebased == 1

    def test_rows_of_the_same_function_add_up(self):
        """같은 함수가 역할·인자 모양마다 여러 줄 — 함수 단위로 합쳐 평균을 낸다."""
        prev = {"1:10": entry("f", 10, 100.0), "2:10": entry("f", 10, 100.0)}
        cur = {"1:10": entry("f", 11, 100.0 + 3000.0), "2:10": entry("f", 11, 100.0 + 10.0)}
        per_fn, _ = post_load.diff_api_stats(prev, cur, 1756000100)
        assert per_fn["f"] == [2, pytest.approx(3010.0)]
        assert [f for f, _, _ in post_load.slow_functions(per_fn)] == ["f"]

    def test_no_new_calls_is_quiet(self):
        prev = {"1:10": entry("f", 10, 99999.0)}
        per_fn, rebased = post_load.diff_api_stats(prev, dict(prev), 1756000100)
        assert per_fn == {} and rebased == 0


class TestSlowParseAndSql:
    def test_parse_skips_malformed_lines(self):
        raw = "10|123|list_price_bands|57|16940.4|1756000000.1\n\n  \nbroken|line\n"
        got = post_load.parse_api_stats(raw)
        assert got == {"10:123": entry("list_price_bands", 57, 16940.4, "1756000000.1")}

    def test_sql_reads_toplevel_rows_of_allowlisted_api_functions(self):
        sql = post_load.build_api_stats_sql()
        assert "extensions.pg_stat_statements" in sql
        assert "s.toplevel" in sql
        for name in post_load.ANON_CALLABLE_NAMES:
            assert "'{}'".format(name) in sql
        # 정규식이 실제 PostgREST 문장에서 함수 이름을 뽑는가 (SQL 안의 패턴을 파이썬으로 재현)
        pat = re.search(r"regexp_match\(s\.query, '(.*?)'\)", sql).group(1)
        q = ('WITH pgrst_source AS (SELECT "pgrst_call".* FROM (SELECT $1 AS json_data) p, '
             'LATERAL "api"."search_buildings"("q" := _."q") pgrst_call)')
        assert re.search(pat, q).group(1) == "search_buildings"


class TestSlowReport:
    def _fake(self, monkeypatch, now, rows):
        def fake(sql):
            if "extract(epoch from now())" in sql:
                return str(now)
            return rows
        monkeypatch.setattr(post_load, "query_one", fake)

    def test_two_runs_baseline_then_alarm(self, monkeypatch, tmp_path, capsys):
        path = str(tmp_path / "logs" / "snap.json")
        monkeypatch.setattr(post_load, "API_STATS_SNAPSHOT_PATH", path)

        self._fake(monkeypatch, 1756000100, "1|10|list_price_bands|10|1000|1756000000")
        assert post_load.report_slow_functions() == []
        assert "[정보]" in capsys.readouterr().out
        with io.open(path, encoding="utf-8") as fh:
            assert json.load(fh)["entries"]["1:10"]["calls"] == 10

        self._fake(monkeypatch, 1756000200, "1|10|list_price_bands|12|4000|1756000000")
        slow = post_load.report_slow_functions()
        out = capsys.readouterr().out
        assert [f for f, _, _ in slow] == ["list_price_bands"]
        assert "[주의] 느려짐: api.list_price_bands" in out and "1,500ms" in out

    def test_no_new_calls_says_so(self, monkeypatch, tmp_path, capsys):
        path = str(tmp_path / "snap.json")
        monkeypatch.setattr(post_load, "API_STATS_SNAPSHOT_PATH", path)
        self._fake(monkeypatch, 1756000100, "1|10|f|10|1000|1756000000")
        post_load.report_slow_functions()
        self._fake(monkeypatch, 1756000200, "1|10|f|10|1000|1756000000")
        capsys.readouterr()
        assert post_load.report_slow_functions() == []
        assert "지난 점검 이후 api 호출 없음" in capsys.readouterr().out

    @pytest.mark.parametrize("content", [
        "{not json",
        '{"taken_at": "x", "entries": {}}',
        '{"taken_at": 1, "entries": {"1:10": "문자열"}}',
        "[1, 2]",
        '{"taken_at": 1, "entries": {"1:10": {"fn": "f", "since": "1756000000"}}}',
        '{"taken_at": 1, "entries": {"1:10": {"fn": "f", "calls": "10", "total_ms": 1.0}}}',
        '{"taken_at": 1, "entries": {"1:10": {"fn": "f", "calls": true, "total_ms": 1.0}}}',
    ])
    def test_broken_snapshot_warns_and_rebases(self, monkeypatch, tmp_path, capsys, content):
        """⛔ 스냅샷 파일 모양이 틀려도 --check 가 죽지 않는다 — [주의] 한 줄 + 기준만 새로.

        줄 값이 사전이 아니거나 calls·total_ms 가 숫자가 아닌 것도 **파일** 탓이다 — 비교 코드
        오류 문구로 새면 안 된다(2026-10-03 읽기·비교 try 분리)."""
        path = tmp_path / "snap.json"
        path.write_text(content, encoding="utf-8")
        monkeypatch.setattr(post_load, "API_STATS_SNAPSHOT_PATH", str(path))
        self._fake(monkeypatch, 1756000200, "1|10|f|12|99999|1756000000")
        assert post_load.report_slow_functions() == []
        out = capsys.readouterr().out
        assert "[주의] 느려짐 경보: 직전 스냅샷 파일 모양이 틀립니다" in out
        assert "비교하는 코드가 실패했습니다" not in out
        assert "기준을 새로 저장했습니다(1줄)" in out
        assert json.loads(path.read_text(encoding="utf-8"))["entries"]["1:10"]["calls"] == 12

    def test_diff_code_error_is_not_blamed_on_the_file(self, monkeypatch, tmp_path, capsys):
        """⛔ 비교 코드가 터지면 '파일 모양' 이 아니라 비교 오류 문구 — 예외 종류 이름만 · 기준은 새로."""
        path = tmp_path / "snap.json"
        monkeypatch.setattr(post_load, "API_STATS_SNAPSHOT_PATH", str(path))
        self._fake(monkeypatch, 1756000100, "1|10|f|10|1000|1756000000")
        post_load.report_slow_functions()
        capsys.readouterr()

        def boom(*a, **k):
            raise ZeroDivisionError("속 글은 안 찍는다")
        monkeypatch.setattr(post_load, "diff_api_stats", boom)
        self._fake(monkeypatch, 1756000200, "1|10|f|12|99999|1756000000")
        assert post_load.report_slow_functions() == []
        out = capsys.readouterr().out
        assert "[주의] 느려짐 경보: 직전 스냅샷과 비교하는 코드가 실패했습니다(ZeroDivisionError)" in out
        assert "파일 모양이 틀립니다" not in out and "속 글은 안 찍는다" not in out
        assert "기준을 새로 저장했습니다(1줄)" in out
        assert json.loads(path.read_text(encoding="utf-8"))["entries"]["1:10"]["calls"] == 12

    def test_diff_code_error_does_not_make_check_exit_1(self, monkeypatch, tmp_path):
        """비교 오류도 [주의] — --check 를 죽이지 않고 종료 코드에도 안 들어간다."""
        monkeypatch.setattr(post_load, "API_STATS_SNAPSHOT_PATH", str(tmp_path / "snap.json"))
        (tmp_path / "snap.json").write_text(
            '{"taken_at": 1, "entries": {"1:10": {"fn": "f", "calls": 1, "total_ms": 1.0, "since": "0"}}}',
            encoding="utf-8")

        def boom(*a, **k):
            raise RuntimeError("x")
        monkeypatch.setattr(post_load, "diff_api_stats", boom)
        self._fake(monkeypatch, 1756000200, "1|10|f|12|99999|1756000000")
        for name, val in (
            ("report_freshness", lambda: ("1", "1", False)),
            ("report_map_freshness", lambda: ({}, False)),
            ("report_tx_window_freshness", lambda: ("", "", False)),
            ("report_coverage_freshness", lambda: ("", "", False)),
            ("report_industry_mix_freshness", lambda: ("", "", False)),
            ("report_tx_geog_freshness", lambda: ("1", "1", False)),
            ("report_anon_exposure", lambda: ([], [])),
            ("report_write_exposure", lambda: []),
            ("report_canonical_indexes", lambda: []),
            ("report_function_drift", lambda: []),
        ):
            monkeypatch.setattr(post_load, name, val)
        assert post_load.main(["--check"]) == 0

    def test_unreadable_stats_warns_but_does_not_raise(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(post_load, "API_STATS_SNAPSHOT_PATH", str(tmp_path / "s.json"))

        def boom(sql):
            raise RuntimeError("relation does not exist")
        monkeypatch.setattr(post_load, "query_one", boom)
        assert post_load.report_slow_functions() == []
        assert "[주의] 느려짐 경보를 읽지 못했습니다" in capsys.readouterr().out
        assert not (tmp_path / "s.json").exists()

    def test_slow_alarm_does_not_make_check_exit_1(self, monkeypatch):
        """⛔ 약속: [주의] 는 종료 코드 1 을 만들지 않는다 — 느린 것은 고장이 아니라 신호다."""
        for name, val in (
            ("report_freshness", lambda: ("1", "1", False)),
            ("report_map_freshness", lambda: ({}, False)),
            ("report_tx_window_freshness", lambda: ("", "", False)),
            ("report_coverage_freshness", lambda: ("", "", False)),
            ("report_industry_mix_freshness", lambda: ("", "", False)),
            ("report_tx_geog_freshness", lambda: ("1", "1", False)),
            ("report_anon_exposure", lambda: ([], [])),
            ("report_write_exposure", lambda: []),
            ("report_slow_functions", lambda: [("list_price_bands", 3, 5000.0)]),
            ("report_canonical_indexes", lambda: []),
            ("report_function_drift", lambda: []),
        ):
            monkeypatch.setattr(post_load, name, val)
        assert post_load.main(["--check"]) == 0
        monkeypatch.setattr(post_load, "report_canonical_indexes", lambda: [("idx_x", "없음")])
        assert post_load.main(["--check"]) == 1
        monkeypatch.setattr(post_load, "report_canonical_indexes", lambda: [])
        monkeypatch.setattr(post_load, "report_function_drift", lambda: [("public.f", ["본문"])])
        assert post_load.main(["--check"]) == 1
        monkeypatch.setattr(post_load, "report_function_drift", lambda: [])
        monkeypatch.setattr(post_load, "report_tx_geog_freshness", lambda: ("4383", "4384", True))
        assert post_load.main(["--check"]) == 1


class TestSlowSnapshotSaveFailure:
    """저장 실패 안내가 실제 동작과 같은가(2026-10-03) — 저장은 os.replace 앞에서 멈추므로
    옛 스냅샷 파일이 그대로 남는다. 다음 점검은 '기준부터'가 아니라 그 옛 파일을 읽는다."""

    def _fake(self, monkeypatch, now, rows):
        monkeypatch.setattr(post_load, "query_one",
                            lambda sql: str(now) if "extract(epoch from now())" in sql else rows)

    def _block_save(self, path):
        os.mkdir(str(path) + ".tmp")          # 임시 파일 자리가 폴더라 open(…, "w") 가 OSError

    def _unblock_save(self, path):
        os.rmdir(str(path) + ".tmp")

    def test_old_snapshot_survives_and_next_check_compares_with_it(self, monkeypatch, tmp_path, capsys):
        path = tmp_path / "snap.json"
        monkeypatch.setattr(post_load, "API_STATS_SNAPSHOT_PATH", str(path))
        self._fake(monkeypatch, 1756000100, "1|10|f|10|1000|1756000000")
        post_load.report_slow_functions()
        before = path.read_text(encoding="utf-8")
        capsys.readouterr()

        self._block_save(path)
        self._fake(monkeypatch, 1756000200, "1|10|f|11|1100|1756000000")
        post_load.report_slow_functions()
        out = capsys.readouterr().out
        assert ("[주의] 느려짐 경보: 스냅샷을 저장하지 못했습니다(" in out
                and "옛 스냅샷 파일이 그대로 남아 다음 점검은 그 파일과 다시 비교합니다." in out)
        assert "기준부터" not in out and "저장했습니다" not in out
        assert path.read_text(encoding="utf-8") == before

        # 다음 점검: 옛 파일(10회·1,000ms)과 비교 → 3회·8,100ms(평균 2,700ms)가 울려야 한다.
        self._unblock_save(path)
        self._fake(monkeypatch, 1756000300, "1|10|f|13|9100|1756000000")
        slow = post_load.report_slow_functions()
        assert [(f, c) for f, c, _ in slow] == [("f", 3)]

    def test_no_snapshot_and_save_fails_never_says_saved(self, monkeypatch, tmp_path, capsys):
        """⛔ 직전 파일이 없는데 저장도 실패하면 '기준만 저장했습니다'를 말하면 안 된다."""
        path = tmp_path / "snap.json"
        monkeypatch.setattr(post_load, "API_STATS_SNAPSHOT_PATH", str(path))
        self._block_save(path)
        self._fake(monkeypatch, 1756000100, "1|10|f|10|1000|1756000000")
        assert post_load.report_slow_functions() == []
        out = capsys.readouterr().out
        assert "스냅샷 파일이 아직 없어 다음 점검도 기준부터입니다." in out
        assert "저장했습니다" not in out and "[정보]" not in out
        assert not path.exists()

    def test_broken_snapshot_and_save_fails_says_it_will_be_read_again(self, monkeypatch, tmp_path, capsys):
        path = tmp_path / "snap.json"
        path.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(post_load, "API_STATS_SNAPSHOT_PATH", str(path))
        self._block_save(path)
        self._fake(monkeypatch, 1756000100, "1|10|f|10|1000|1756000000")
        assert post_load.report_slow_functions() == []
        out = capsys.readouterr().out
        assert "파일 모양이 틀립니다" in out
        assert "옛 스냅샷 파일이 그대로 남아 다음 점검도 그 파일을 다시 읽습니다." in out
        assert "저장했습니다" not in out
        assert path.read_text(encoding="utf-8") == "{not json"

    def test_diff_error_and_save_fails_says_the_old_file_stays(self, monkeypatch, tmp_path, capsys):
        """⛔ 비교 코드 오류 + 저장 실패: 파일은 멀쩡히 있으니 '아직 없어 … 기준부터' 가 아니다."""
        path = tmp_path / "snap.json"
        monkeypatch.setattr(post_load, "API_STATS_SNAPSHOT_PATH", str(path))
        self._fake(monkeypatch, 1756000100, "1|10|f|10|1000|1756000000")
        post_load.report_slow_functions()
        before = path.read_text(encoding="utf-8")
        capsys.readouterr()

        def boom(*a, **k):
            raise RuntimeError("x")
        monkeypatch.setattr(post_load, "diff_api_stats", boom)
        self._block_save(path)
        self._fake(monkeypatch, 1756000200, "1|10|f|12|99999|1756000000")
        assert post_load.report_slow_functions() == []
        out = capsys.readouterr().out
        assert "비교하는 코드가 실패했습니다(RuntimeError)" in out
        assert "옛 스냅샷 파일이 그대로 남아 다음 점검도 그 파일을 다시 읽습니다." in out
        assert "아직 없어" not in out and "기준부터" not in out and "저장했습니다" not in out
        assert path.read_text(encoding="utf-8") == before

    def test_save_fails_with_rebased_rows_does_not_claim_a_new_baseline(self, monkeypatch, tmp_path, capsys):
        """⛔ 저장이 실패했으면 기준만 새로 잡은 줄도 실제로는 안 잡혔다 — '기준만 새로 잡았습니다' 금지.
        그 줄은 다음 점검에서도 다시 기준만이므로 '이번 점검 몫까지 함께 센다' 류도 금지."""
        path = tmp_path / "snap.json"
        monkeypatch.setattr(post_load, "API_STATS_SNAPSHOT_PATH", str(path))
        self._fake(monkeypatch, 1756000100, "1|10|f|10|1000|1756000000")
        post_load.report_slow_functions()
        capsys.readouterr()

        self._block_save(path)
        # 통계가 직전 점검 **앞** 시각으로 초기화된 줄(calls 감소) → 기준만 새로 잡을 줄 1개
        self._fake(monkeypatch, 1756000200, "1|10|f|5|500|1756000050")
        assert post_load.report_slow_functions() == []
        out = capsys.readouterr().out
        assert "다음 점검은 그 파일과 다시 비교합니다." in out
        assert ("ⓘ 통계가 초기화됐거나 새로 잡힌 1줄은 이번엔 비교하지 않았습니다"
                "(저장이 실패해 기준도 새로 잡히지 않았습니다).") in out
        assert "기준만 새로 잡았습니다" not in out and "함께 셉니다" not in out
        assert "저장했습니다" not in out


# ── 참고 시세 이웃 요약표 신선도 ────────────────────────────────────────────


class TestTxGeogFreshness:
    def _run(self, monkeypatch, capsys, raw):
        monkeypatch.setattr(post_load, "query_one", lambda sql: raw)
        got = post_load.report_tx_geog_freshness()
        return got, capsys.readouterr().out

    def test_equal_sets_are_fresh(self, monkeypatch, capsys):
        (rows, expected, stale), out = self._run(monkeypatch, capsys, "4384|4384|0|0")
        assert (rows, expected, stale) == ("4384", "4384", False)
        assert "[신선] 참고 시세 이웃 요약표 4384행" in out
        assert "표에만 있는 필지 0곳 · 표에 빠진 필지 0곳" in out

    @pytest.mark.parametrize("raw", ["4383|4384|0|1", "4385|4384|1|0", "0|4384|0|4384"])
    def test_any_difference_is_stale(self, monkeypatch, capsys, raw):
        """많아도 적어도 낡음이다 — 거래가 지워진 필지가 남아 있어도 이웃에 헛 필지가 섞인다."""
        (_, _, stale), out = self._run(monkeypatch, capsys, raw)
        assert stale is True
        assert "[낡음] 참고 시세 이웃 요약표" in out and "post_load.py" in out

    def test_same_row_count_but_different_sets_is_stale(self, monkeypatch, capsys):
        """⛔ 행수가 같아도(지워진 필지 1 · 새 필지 1) 집합이 다르면 낡음이다 — 예전엔 [신선]이었다."""
        (rows, expected, stale), out = self._run(monkeypatch, capsys, "4384|4384|1|1")
        assert (rows, expected, stale) == ("4384", "4384", True)
        assert "표에만 있는 필지 1곳 · 표에 빠진 필지 1곳" in out
        assert "[신선]" not in out

    @pytest.mark.parametrize("raw", ["4384|4384", "4384|4384|0", "4384|4384|x|0", "4384|4384|1|x"])
    def test_malformed_answer_is_loud(self, monkeypatch, raw):
        """답 모양이 틀리면 [신선]·[낡음] 어느 쪽으로도 넘어가지 않고 예외로 죽는다(칸이 모자라거나
        숫자가 아님 — 앞 칸만으로 낡음이 정해져도 뒤 칸이 글자면 죽는다)."""
        monkeypatch.setattr(post_load, "query_one", lambda sql: raw)
        with pytest.raises(ValueError):
            post_load.report_tx_geog_freshness()

    def test_sql_counts_both_set_differences_from_one_condition(self):
        """한 번의 조회 · 조건 글자는 TX_GEOG_CONDITION 한 곳 · 양쪽 차집합 둘 다 센다."""
        sql = post_load.build_tx_geog_freshness_sql()
        assert sql.count(post_load.TX_GEOG_CONDITION) == 1
        assert "from parcel p where " + post_load.TX_GEOG_CONDITION in sql   # 옛 단언을 이어받는다
        assert "from mv_tx_parcel_geog" in sql
        assert sql.count("'|'") == 3 and sql.rstrip().endswith(";") and sql.count(";") == 1
        assert "from mv_tx_parcel_geog m where not exists (select 1 from want w where w.pnu = m.pnu)" in sql
        assert "from want w where not exists (select 1 from mv_tx_parcel_geog m where m.pnu = w.pnu)" in sql
        assert "::char" not in sql          # pnu 는 양쪽 다 char(19) 칸 — 캐스트를 넣으면 색인이 죽는다

    @pytest.mark.parametrize("raw", ["4384|4384|1|0", "4384|4384|0|1", "4385|4384|0|0"])
    def test_each_term_alone_makes_it_stale(self, monkeypatch, capsys, raw):
        """판정의 세 항(표에만 있음 · 표에 빠짐 · 행수 다름)이 **각각 혼자서도** 낡음을 만든다.

        실데이터에선 pnu 가 유일 키라 안 나오는 조합도 있지만, 항 하나를 지운 변이를 잡으려면 필요하다."""
        (_, _, stale), out = self._run(monkeypatch, capsys, raw)
        assert stale is True and "[낡음]" in out

    @staticmethod
    def _matches(definition):
        """뷰 정의의 where 절 **전체**가 TX_GEOG_CONDITION 과 같은가 — 본 시험과 양성 대조가 함께 쓰는 판정."""
        norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()  # noqa: E731
        m = re.search(r"\bfrom parcel p where (.*)$", norm(definition))
        assert m, "뷰 정의에서 where 절을 못 찾았습니다: " + definition
        return m.group(1) == norm(post_load.TX_GEOG_CONDITION)

    def _view_definition(self):
        m = re.search(r"create materialized view if not exists mv_tx_parcel_geog as(.*?);",
                      read_schema(), re.S)
        assert m, "정본에서 mv_tx_parcel_geog 정의를 못 찾았습니다."
        return m.group(1)

    def test_condition_matches_the_view_definition_in_schema(self):
        """⛔ 오른쪽(있어야 할 필지)은 뷰 정의의 where 절 **전체**와 같아야 한다 — 갈리면 늘 낡음/늘 신선.

        예전엔 부분 문자열 비교라 정본 where 끝에 조건을 덧붙여도 초록이었다(2026-10-03)."""
        assert self._matches(self._view_definition())

    @pytest.mark.parametrize("mutate", [
        lambda d: d + " and p.x is not null",
        lambda d: d + "\n   or p.pnu is null",
        lambda d: d.replace("and exists (select 1 from transaction t where t.pnu = p.pnu)", ""),
        lambda d: re.sub(r"p\.geom is not null\s+and ", "", d),
    ])
    def test_where_clause_comparison_catches_added_or_removed_conditions(self, mutate):
        """양성 대조: 정의 사본(정본 파일은 안 고친다)에 조건을 더하거나 빼면 **본 시험과 같은 판정**이
        거짓이어야 한다 — 판정을 부분 문자열 비교로 되돌리면 여기가 빨개진다."""
        original = self._view_definition()
        mutated = mutate(original)
        assert mutated != original, "변이가 정의를 못 바꿨습니다 — 탐침 글자를 정본에 맞추세요."
        assert not self._matches(mutated)


class TestApplyRechecksTxGeog:
    """갱신 흐름(`--check` 없이)도 참고 시세 이웃 요약표를 다시 잰다 — REFRESH_MVS 에 있어 방금
    다시 구운 표다(2026-10-03 · 예전엔 --check 쪽에만 있었다)."""

    def _apply(self, monkeypatch, geog):
        assert "mv_tx_parcel_geog" in post_load.REFRESH_MVS
        monkeypatch.setattr(post_load.dbx, "run_sql", lambda sql, **k: 0)
        for name, val in (
            ("report_freshness", lambda: ("1", "1", False)),
            ("report_map_freshness", lambda: ({}, False)),
            ("report_tx_window_freshness", lambda: ("", "", False)),
            ("report_coverage_freshness", lambda: ("", "", False)),
            ("report_industry_mix_freshness", lambda: ("", "", False)),
        ):
            monkeypatch.setattr(post_load, name, val)
        asked = []

        def fake_query_one(sql):
            asked.append(sql)
            assert sql == post_load.build_tx_geog_freshness_sql()
            return geog
        monkeypatch.setattr(post_load, "query_one", fake_query_one)
        return post_load.main([]), asked

    def test_only_this_table_stale_after_refresh_exits_1(self, monkeypatch, capsys):
        code, asked = self._apply(monkeypatch, "4384|4384|1|1")
        assert code == 1 and len(asked) == 1
        assert "[낡음] 참고 시세 이웃 요약표" in capsys.readouterr().out

    def test_fresh_after_refresh_exits_0(self, monkeypatch, capsys):
        code, asked = self._apply(monkeypatch, "4384|4384|0|0")
        assert code == 0 and len(asked) == 1
        assert "[신선] 참고 시세 이웃 요약표" in capsys.readouterr().out


# ── ② 정본 색인 ──────────────────────────────────────────────────────────────


INDEX_FIXTURE = """
create index if not exists idx_a on t (a);
create unique index if not exists idx_b     on t (b);
create unique index if not exists mv_key
  on mv (k);
  create index concurrently idx_c on t (c);
create unique index concurrently if not exists idx_d on t (d);
-- create index if not exists idx_commented on t (x);
create index if not exists idx_a on t (a);
"""


class TestCanonicalIndexes:
    def test_parser_forms(self):
        assert post_load.canonical_index_names(INDEX_FIXTURE) == [
            "idx_a", "idx_b", "mv_key", "idx_c", "idx_d"]

    def test_parser_reads_every_index_in_the_real_schema(self):
        """⛔ 파서가 헛돌면 '문제 0' 이 가짜 초록이 된다 — 머리 수와 대조한다."""
        raw = read_schema()
        heads = len(re.findall(r"(?im)^\s*create\s+(?:unique\s+)?index\b", raw))
        names = post_load.canonical_index_names(raw)
        assert len(names) == heads
        # 바닥값 = 지금 정본 색인 수. 2026-10-01b 가 안 쓰는 다섯을 지워 54 → 49 가 됐다.
        assert heads >= 49
        for must in ("idx_parcel_updated_at", "idx_msp_pnu", "mv_district_industry_mix_key"):
            assert must in names

    def test_problems(self):
        live = "idx_a|true\nidx_b|false\n\n"
        got = post_load.index_problems(["idx_a", "idx_b", "idx_c"], live)
        assert [n for n, _ in got] == ["idx_b", "idx_c"]
        assert "indisvalid" in got[0][1] and "없음" in got[1][1]

    def test_all_present_and_valid_is_clean(self):
        assert post_load.index_problems(["idx_a"], "idx_a|true\nidx_live_only|false") == []


# ── ② 보탬(2026-10-02): INCLUDE 칸 대조 · 라이브에만 있는 색인 ────────────────
#
# 이름만 보던 점검은 INCLUDE 칸이 라이브에서 빠져도 [정상]이라 했다(빠져도 에러는 안 나고
# 느려지기만 한다 — idx_arch_permit_pnu 의 arch_pms_day). 그리고 색인을 지우는 마이그레이션이
# 덜 적용돼 라이브에만 남은 색인은 아예 안 봤다.


def index_line(name, include=None, valid="true", table="t", con="false", ext="false", definition=None):
    """LIVE_INDEX_SQL 한 줄(이름|valid|표|제약|확장|색인 정의)을 pg_get_indexdef 모양으로 짓는다."""
    if definition is None:
        definition = "CREATE INDEX {} ON public.{} USING btree (a)".format(name, table)
        if include:
            definition += " INCLUDE ({})".format(", ".join(include))
    return "|".join([name, valid, table, con, ext, definition])


INCLUDE_FIXTURE = """
create index if not exists idx_plain on t (a);
create index if not exists idx_multi on t (pnu, ym)
  -- include (ghost); 주석의 세미콜론과 include 글자에 속지 않는다
  INCLUDE (Cat_L , cat_m,
           "Cat_N")
  where a is not null;
create unique index concurrently if not exists idx_u
  on t (b) Include(x);
-- create index if not exists idx_commented on t (x) include (y);
create index if not exists idx_after on t (c);
create index if not exists idx_multi on t (pnu) include (other);
"""


class TestCanonicalIndexIncludes:
    def test_extracts_include_columns_in_order(self):
        """ⓒ 여러 줄 문장 · 문장 가운데 낀 주석 줄 · include 대소문자 · 따옴표 · 같은 이름은 첫 문장."""
        assert post_load.canonical_index_includes(INCLUDE_FIXTURE) == {
            "idx_plain": [],
            "idx_multi": ["cat_l", "cat_m", "cat_n"],
            "idx_u": ["x"],
            "idx_after": [],
        }

    def test_include_of_the_next_statement_does_not_leak_backwards(self):
        """문장은 첫 `;` 에서 끝난다 — 뒤 문장의 include 를 앞 색인이 가져가면 안 된다."""
        got = post_load.canonical_index_includes(
            "create index idx_a on t (a);\ncreate index idx_b on t (b) include (z);\n")
        assert got == {"idx_a": [], "idx_b": ["z"]}

    def test_names_match_the_name_parser(self):
        assert list(post_load.canonical_index_includes(INCLUDE_FIXTURE)) == \
            post_load.canonical_index_names(INCLUDE_FIXTURE)

    def test_real_schema_has_exactly_the_two_known_include_indexes(self):
        """⛔ 양성 대조(ⓓ): 추출이 조용히 0개를 내면 INCLUDE 대조는 영원히 초록이다.

        정본에 include 를 더하거나 뺐다면 이 목록도 함께 고친다(그게 이 시험의 일이다)."""
        raw = read_schema()
        includes = post_load.canonical_index_includes(raw)
        assert set(includes) == set(post_load.canonical_index_names(raw))
        assert {k: v for k, v in includes.items() if v} == {
            "idx_ub_pnu_cat": ["cat_l_cd", "cat_l_nm", "cat_m_cd", "cat_m_nm"],
            "idx_arch_permit_pnu": [
                "loaded_ym", "use_apr_day", "main_purps_cd", "real_stcns_day", "arch_pms_day"],
        }


class TestLiveIndexParser:
    def test_reads_all_six_fields(self):
        live = post_load.parse_live_indexes(
            index_line("Idx_A", include=["x", "y"], table="parcel") + "\n\n"
            + index_line("parcel_pkey", table="parcel", con="true") + "\n"
            + index_line("srs_idx", valid="false", table="spatial_ref_sys", ext="true"))
        assert live["idx_a"] == {
            "valid": True, "table": "parcel", "constraint": False, "extension": False,
            "include": ["x", "y"]}
        assert live["parcel_pkey"]["constraint"] is True and live["parcel_pkey"]["include"] == []
        assert live["srs_idx"]["extension"] is True and live["srs_idx"]["valid"] is False

    def test_pipes_inside_the_definition_do_not_shift_fields(self):
        """식 색인의 `||` 는 구분자와 같은 글자다 — 정의는 맨 끝 칸이라 앞의 다섯 번만 자른다."""
        definition = ("CREATE INDEX idx_e ON public.t USING btree (((a || '|'::text) || b)) "
                      "INCLUDE (c, \"D\") WHERE (e IS NOT NULL)")
        row = post_load.parse_live_indexes(index_line("idx_e", table="t", definition=definition))["idx_e"]
        assert row["table"] == "t" and row["valid"] is True
        assert row["include"] == ["c", "d"]

    @pytest.mark.parametrize("line", ["idx_a|true", "idx_a|true|t|false|false|", "idx_a|true|t|false"])
    def test_short_or_empty_definition_is_unknown_not_empty(self, line):
        """⛔ 칸이 모자라면 include 는 None(모름) — 빈 목록이면 'INCLUDE 없음'과 구별이 안 된다."""
        assert post_load.parse_live_indexes(line)["idx_a"]["include"] is None

    def test_query_shape_matches_the_parser(self):
        """조회가 내는 칸 수와 파서가 기대하는 칸 수가 갈리면 전부 '읽지 못함'이 된다."""
        sql = post_load.LIVE_INDEX_SQL
        assert sql.count("'|'") == post_load._LIVE_INDEX_FIELDS - 1
        assert sql.rindex("'|'") < sql.index("pg_get_indexdef(i.indexrelid)")   # 정의가 맨 끝 칸
        assert "n.nspname in ('public','api')" in sql

    def test_query_fields_come_in_the_order_the_parser_reads(self):
        """⛔ 칸 수가 맞아도 순서가 바뀌면 조용히 틀린다(valid 자리에 표 이름이 오면 전부 invalid).

        select 목록을 구분자로 잘라, 칸마다 그 자리의 표지가 들어 있는지 본다."""
        select_list = post_load.LIVE_INDEX_SQL.split(" from pg_index i ")[0]
        fields = select_list.split("'|'")
        markers = ["c.relname", "i.indisvalid::text", "t.relname", "from pg_constraint k",
                   "from pg_depend d", "pg_get_indexdef(i.indexrelid)"]
        assert len(fields) == len(markers) == post_load._LIVE_INDEX_FIELDS
        for pos, (field, marker) in enumerate(zip(fields, markers)):
            assert marker in field, "{}번째 칸에 {} 가 없습니다: {}".format(pos + 1, marker, field)
            for other in markers[:pos] + markers[pos + 1:]:
                assert other not in field, "{}번째 칸에 다른 칸의 표지 {} 가 섞였습니다".format(pos + 1, other)

    def test_constraint_flag_counts_only_primary_unique_exclusion(self):
        """⛔ conindid 는 외래키 제약에도 채워진다(참조되는 쪽 색인) — contype 을 안 거르면 외래키가
        가리키는 일반 유일 색인이 '제약이 만든 색인'으로 빠져 라이브 전용에서 안 보인다."""
        assert ("from pg_constraint k where k.conindid = i.indexrelid "
                "and k.contype in ('p','u','x'))") in post_load.LIVE_INDEX_SQL

    def test_extension_flag_looks_at_the_table_and_the_index(self):
        """확장 소유 판정은 표(indrelid)와 색인(indexrelid) 둘 다 — 조건을 통째로 본다
        (`i.indrelid` 글자만 찾으면 join 줄에도 있어 헛돈다)."""
        assert ("from pg_depend d where d.classid = 'pg_class'::regclass "
                "and d.objid in (i.indrelid, i.indexrelid) and d.deptype = 'e')") in post_load.LIVE_INDEX_SQL


class TestIndexIncludeProblems:
    """ⓐ INCLUDE 같음 / 다름 / 정본에만 / 라이브에만."""

    CANON = {"idx_x": ["a", "b"], "idx_y": []}

    def problems(self, *lines):
        return post_load.index_problems(["idx_x", "idx_y"], "\n".join(lines), self.CANON)

    def test_same_include_is_clean(self):
        assert self.problems(index_line("idx_x", include=["a", "b"]), index_line("idx_y")) == []

    def test_different_include_is_a_problem(self):
        got = self.problems(index_line("idx_x", include=["a"]), index_line("idx_y"))
        assert got == [("idx_x", "INCLUDE 칸이 다름: 정본 (a, b) · 라이브 (a)")]

    def test_include_only_in_canon(self):
        got = self.problems(index_line("idx_x"), index_line("idx_y"))
        assert got == [("idx_x", "INCLUDE 칸이 다름: 정본 (a, b) · 라이브 (없음)")]

    def test_include_only_in_live(self):
        got = self.problems(index_line("idx_x", include=["a", "b"]), index_line("idx_y", include=["z"]))
        assert got == [("idx_y", "INCLUDE 칸이 다름: 정본 (없음) · 라이브 (z)")]

    def test_order_matters(self):
        got = self.problems(index_line("idx_x", include=["b", "a"]), index_line("idx_y"))
        assert got == [("idx_x", "INCLUDE 칸이 다름: 정본 (a, b) · 라이브 (b, a)")]

    def test_case_spacing_and_quotes_do_not_matter(self):
        definition = 'CREATE INDEX idx_x ON public.t USING btree (k) INCLUDE ("A",  b) WHERE (k > 0)'
        assert self.problems(index_line("idx_x", definition=definition), index_line("idx_y")) == []

    def test_index_missing_from_the_include_map_must_have_no_include(self):
        got = post_load.index_problems(["idx_z"], index_line("idx_z", include=["q"]), {})
        assert got == [("idx_z", "INCLUDE 칸이 다름: 정본 (없음) · 라이브 (q)")]

    def test_unreadable_definition_is_loud(self):
        """⛔ 조회 줄 모양이 틀어져 정의를 못 읽으면 초록이 아니라 [사고]다."""
        got = post_load.index_problems(["idx_x"], "idx_x|true", self.CANON)
        assert len(got) == 1 and got[0][0] == "idx_x" and "INCLUDE 칸을 읽지 못함" in got[0][1]

    @pytest.mark.parametrize("name, canon", [("idx_y", CANON), ("idx_z", {})])
    def test_unreadable_definition_is_loud_even_when_canon_has_no_include(self, name, canon):
        """⛔ 정본에 include 가 없는 색인(정본의 대부분)도 같다 — 못 읽은 것을 '없음 == 없음'
        으로 넘기면 조회 줄 모양이 틀어진 날 거의 전부가 초록이 된다. 사유 문구까지 본다."""
        got = post_load.index_problems([name], name + "|true", canon)
        assert got == [(name, "INCLUDE 칸을 읽지 못함(라이브 조회 줄에 색인 정의가 없음)")]

    def test_missing_and_invalid_still_win_over_include(self):
        got = self.problems(index_line("idx_x", include=["a"], valid="false"))
        assert got == [("idx_x", "indisvalid=false(쓸 수 없는 색인)"), ("idx_y", "라이브에 없음")]


class TestLiveOnlyIndexes:
    """ⓑ 라이브에만 있는 색인 — 제약이 만든 것·확장 소유 표의 것은 뺀다."""

    def test_true_live_only_is_reported_with_its_table(self):
        raw = "\n".join([
            index_line("idx_a"),
            index_line("idx_zombie", table="unit_business"),
            index_line("idx_half_built", valid="false", table="parcel"),
        ])
        assert post_load.live_only_indexes(["idx_a"], raw) == [
            ("idx_half_built", "parcel", False), ("idx_zombie", "unit_business", True)]

    def test_constraint_backed_indexes_are_not_live_only(self):
        raw = "\n".join([index_line("idx_a"), index_line("parcel_pkey", table="parcel", con="true")])
        assert post_load.live_only_indexes(["idx_a"], raw) == []

    def test_extension_owned_table_indexes_are_not_live_only(self):
        raw = "\n".join([index_line("idx_a"), index_line("srs_idx", table="spatial_ref_sys", ext="true")])
        assert post_load.live_only_indexes(["idx_a"], raw) == []

    def test_canonical_names_are_never_live_only(self):
        assert post_load.live_only_indexes(["idx_a", "idx_gone"], index_line("idx_a")) == []


class TestReportCanonicalIndexes:
    """ⓕ 보고 함수를 가장 낮은 경계(query_one)만 가짜로 두고 부른다 — 실제 출력 문구를 본다."""

    SQL = (
        "create index if not exists idx_a on t (a);\n"
        "create index if not exists idx_inc on t (pnu)\n  include (c1, c2);\n"
    )
    CLEAN = [
        index_line("idx_a"),
        index_line("idx_inc", include=["c1", "c2"]),
        index_line("t_pkey", con="true"),
        index_line("srs_idx", table="spatial_ref_sys", ext="true"),
    ]

    def run(self, monkeypatch, capsys, lines):
        calls = []

        def fake_query_one(sql):
            calls.append(sql)
            return "\n".join(lines)
        monkeypatch.setattr(post_load, "query_one", fake_query_one)
        bad = post_load.report_canonical_indexes(sql_text=self.SQL)
        assert calls == [post_load.LIVE_INDEX_SQL]          # 라이브 조회는 한 번뿐이다
        return bad, capsys.readouterr().out

    def test_clean(self, monkeypatch, capsys):
        bad, out = self.run(monkeypatch, capsys, self.CLEAN)
        assert bad == []
        assert ("[정상] 정본 색인 2개가 라이브에 모두 있고 쓸 수 있으며, INCLUDE 칸도 같습니다"
                "(INCLUDE 가 있는 색인 1개).") in out
        assert "[정상] 라이브에만 있는 색인 없음" in out
        assert "[사고]" not in out and "[주의]" not in out

    def test_include_difference_is_an_incident(self, monkeypatch, capsys):
        lines = [self.CLEAN[0], index_line("idx_inc", include=["c1"])] + self.CLEAN[2:]
        bad, out = self.run(monkeypatch, capsys, lines)
        assert bad == [("idx_inc", "INCLUDE 칸이 다름: 정본 (c1, c2) · 라이브 (c1)")]
        assert "[사고] 정본(schema.sql) 색인 중 라이브에 없거나 못 쓰거나 INCLUDE 칸이 다른 것 1개:" in out
        assert "       · idx_inc — INCLUDE 칸이 다름: 정본 (c1, c2) · 라이브 (c1)" in out
        assert "`create index if not exists` 로는 안 고쳐집니다" in out
        assert "[정상] 정본 색인" not in out
        assert "[정상] 라이브에만 있는 색인 없음" in out       # 두 점검은 서로 독립이다

    def test_missing_index_keeps_the_old_wording_without_the_include_hint(self, monkeypatch, capsys):
        bad, out = self.run(monkeypatch, capsys, self.CLEAN[1:])
        assert bad == [("idx_a", "라이브에 없음")]
        assert "       · idx_a — 라이브에 없음" in out
        assert "정본의 create index 문을 라이브에 적용하세요." in out
        assert "안 고쳐집니다" not in out

    def test_live_only_is_a_caution_and_not_returned(self, monkeypatch, capsys):
        lines = self.CLEAN + [index_line("idx_zombie", table="unit_business"),
                              index_line("idx_half", valid="false", table="parcel")]
        bad, out = self.run(monkeypatch, capsys, lines)
        assert bad == []                                      # 종료 코드에 안 들어간다
        assert "[주의] 라이브에만 있는 색인 2개(정본 schema.sql 에 없음):" in out
        assert "       · idx_zombie (표 unit_business)" in out
        assert "       · idx_half (표 parcel · indisvalid=false)" in out
        assert "색인을 지우는 마이그레이션이 덜 적용됐거나 라이브에서 손으로 만든 것 — 정본에 넣거나 지우세요." in out
        assert "t_pkey" not in out and "srs_idx" not in out
        assert "[정상] 정본 색인 2개" in out and "[사고]" not in out

    @pytest.mark.parametrize("lines", [[], ["", "   "]])
    def test_empty_live_answer_does_not_claim_no_live_only_indexes(self, monkeypatch, capsys, lines):
        """⛔ 한 줄도 못 읽었는데 '라이브에만 있는 색인 없음'이라 하면 거짓 안심이다."""
        bad, out = self.run(monkeypatch, capsys, lines)
        assert bad == [("idx_a", "라이브에 없음"), ("idx_inc", "라이브에 없음")]   # 종료 코드는 [사고]가 정한다
        assert "[사고]" in out
        assert "[주의] 라이브 색인 목록을 한 줄도 읽지 못했습니다 — 라이브 전용 색인 판정을 건너뜁니다." in out
        assert "라이브에만 있는 색인 없음" not in out
        assert "[주의] 라이브에만 있는 색인" not in out


class TestCheckExitCodeForIndexes:
    """ⓔ 종료 코드: INCLUDE 다름 → 1 · 라이브 전용만 → 0. 정본은 실제 schema.sql 을 쓴다."""

    def live_from_schema(self):
        raw = read_schema()
        includes = post_load.canonical_index_includes(raw)
        return [index_line(name, include=includes[name]) for name in post_load.canonical_index_names(raw)]

    def check(self, monkeypatch, capsys, lines):
        for name, val in (
            ("report_freshness", lambda: ("1", "1", False)),
            ("report_map_freshness", lambda: ({}, False)),
            ("report_tx_window_freshness", lambda: ("", "", False)),
            ("report_coverage_freshness", lambda: ("", "", False)),
            ("report_industry_mix_freshness", lambda: ("", "", False)),
            ("report_tx_geog_freshness", lambda: ("1", "1", False)),
            ("report_anon_exposure", lambda: ([], [])),
            ("report_write_exposure", lambda: []),
            ("report_slow_functions", lambda: []),
            ("report_function_drift", lambda: []),
        ):
            monkeypatch.setattr(post_load, name, val)
        monkeypatch.setattr(post_load, "query_one", lambda sql: "\n".join(lines))
        code = post_load.main(["--check"])
        return code, capsys.readouterr().out

    def test_live_equal_to_schema_exits_0(self, monkeypatch, capsys):
        lines = self.live_from_schema() + [index_line("parcel_pkey", table="parcel", con="true")]
        code, out = self.check(monkeypatch, capsys, lines)
        assert code == 0
        assert "INCLUDE 칸도 같습니다(INCLUDE 가 있는 색인 2개)." in out
        assert "[정상] 라이브에만 있는 색인 없음" in out

    def test_include_column_dropped_in_live_exits_1(self, monkeypatch, capsys):
        """2026-09-27e 가 더한 허가일 칸이 라이브에서 빠진 꼴 — 이름은 같아 예전엔 [정상]이었다."""
        lines = [ln for ln in self.live_from_schema() if not ln.startswith("idx_arch_permit_pnu|")]
        assert len(lines) == len(self.live_from_schema()) - 1
        lines.append(index_line("idx_arch_permit_pnu", table="arch_permit", include=[
            "loaded_ym", "use_apr_day", "main_purps_cd", "real_stcns_day"]))
        code, out = self.check(monkeypatch, capsys, lines)
        assert code == 1
        assert ("       · idx_arch_permit_pnu — INCLUDE 칸이 다름: 정본 (loaded_ym, use_apr_day, "
                "main_purps_cd, real_stcns_day, arch_pms_day) · 라이브 (loaded_ym, use_apr_day, "
                "main_purps_cd, real_stcns_day)") in out

    def test_live_only_index_alone_exits_0(self, monkeypatch, capsys):
        lines = self.live_from_schema() + [index_line("idx_ub_name", table="unit_business")]
        code, out = self.check(monkeypatch, capsys, lines)
        assert code == 0
        assert "[주의] 라이브에만 있는 색인 1개" in out
        assert "       · idx_ub_name (표 unit_business)" in out


# ── ③ 정본↔라이브 함수 ───────────────────────────────────────────────────────


BODY_F = "\n  select 1;  -- 본문 주석도 라이브의 일부\n"
FN_FIXTURE = (
    "create or replace function f(x text)\n"
    "returns int\n"
    "language sql\n"
    "stable\n"
    "set search_path = public, extensions, pg_temp   -- 2026-09-23a 머리 주석\n"
    "as " + D + BODY_F + D + ";\n"
    "\n"
    "-- language plpgsql 이라고 적힌 바깥 주석\n"
    "create or replace function api.g()\n"
    "returns table (a int)\n"
    "language sql\n"
    "security definer\n"
    "set search_path = ''\n"
    "as " + D + "\n  select public.f('a');\n" + D + ";\n"
    "\n"
    "create function h()\n"
    "returns int\n"
    "language sql\n"
    "as " + D + " select 2 " + D + ";\n"
)


def md5(s):
    return hashlib.md5(s.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def live_line(schema, name, lang, body, cfg):
    return "{}|{}|{}|{}|{}".format(schema, name, lang, md5(body), cfg)


LIVE_SAME = "\n".join([
    live_line("public", "f", "sql", BODY_F, "search_path=public, extensions, pg_temp"),
    live_line("api", "g", "sql", "\n  select public.f('a');\n", 'search_path=""'),
    live_line("public", "h", "sql", " select 2 ", ""),
    live_line("public", "live_only", "plpgsql", "x", ""),
])


class TestCanonicalFunctions:
    def test_parser_reads_language_body_and_settings(self):
        got = post_load.canonical_functions(FN_FIXTURE)
        assert got["public.f"] == ("sql", md5(BODY_F), "search_path=public,extensions,pg_temp")
        assert got["api.g"][0] == "sql"
        assert got["api.g"][2] == "search_path="
        # `or replace` 없는 `create function` 도 읽는다(마이그레이션 2026-08-11 이 그 꼴이었다)
        assert got["public.h"] == ("sql", md5(" select 2 "), "")
        assert len(got) == 3

    def test_parser_reads_every_function_in_the_real_schema(self):
        raw = read_schema()
        # ⚠️ 머리 수는 **모듈 밖의 독립 패턴**으로 센다 — 모듈의 정규식으로 세면 둘이 같이 헛돌 때
        #    같이 0 을 세어 초록이 된다. 이름에 따옴표(`"api"."x"`)가 있어도 머리로는 센다
        #    (파서가 그 꼴을 못 읽으면 개수가 어긋나 여기서 빨개진다).
        heads = len(re.findall(r'(?im)^\s*create\s+(?:or\s+replace\s+)?function\s+[\w."]+\s*\(', raw))
        canon = post_load.canonical_functions(raw)
        assert heads == len(canon) and heads >= 30
        assert all(lang in ("sql", "plpgsql") for lang, _, _ in canon.values())
        assert canon["api.search_stores"][2] == "search_path="
        assert canon["public.search_buildings"][0] == "plpgsql"

    def test_same_is_clean_and_live_only_is_out_of_scope(self):
        canon = post_load.canonical_functions(FN_FIXTURE)
        assert post_load.function_drift(canon, post_load.parse_live_functions(LIVE_SAME)) == []

    def test_crlf_only_difference_is_not_drift(self):
        canon = post_load.canonical_functions(FN_FIXTURE.replace("\n", "\r\n"))
        assert post_load.function_drift(canon, post_load.parse_live_functions(LIVE_SAME)) == []

    def test_comment_only_body_change_is_drift(self):
        """⛔ 뒷문: 라이브 본문에 주석 한 줄만 달라도 잡혀야 한다."""
        live = LIVE_SAME.replace(md5(BODY_F), md5(BODY_F + "-- 라이브에서만 고침\n"))
        bad = post_load.function_drift(post_load.canonical_functions(FN_FIXTURE),
                                       post_load.parse_live_functions(live))
        assert [n for n, _ in bad] == ["public.f"] and "본문" in bad[0][1][0]

    def test_setting_change_is_drift(self):
        live = LIVE_SAME.replace("search_path=public, extensions, pg_temp", "search_path=public")
        bad = post_load.function_drift(post_load.canonical_functions(FN_FIXTURE),
                                       post_load.parse_live_functions(live))
        assert [n for n, _ in bad] == ["public.f"] and "설정" in bad[0][1][0]

    def test_language_change_is_drift(self):
        live = LIVE_SAME.replace("public|f|sql|", "public|f|plpgsql|")
        bad = post_load.function_drift(post_load.canonical_functions(FN_FIXTURE),
                                       post_load.parse_live_functions(live))
        assert "언어" in bad[0][1][0]

    def test_missing_and_overload_are_drift(self):
        canon = post_load.canonical_functions(FN_FIXTURE)
        only_f = post_load.parse_live_functions(LIVE_SAME.splitlines()[0])
        assert post_load.function_drift(canon, only_f) == [
            ("api.g", ["라이브에 없음"]), ("public.h", ["라이브에 없음"])]
        twice = LIVE_SAME + "\n" + LIVE_SAME.splitlines()[0]
        bad = post_load.function_drift(canon, post_load.parse_live_functions(twice))
        assert bad[0][0] == "public.f" and "오버로드" in bad[0][1][0]

    def test_config_forms_meet(self):
        n = post_load._norm_config
        assert n("search_path = public, extensions, pg_temp") == n("search_path=public, extensions, pg_temp")
        assert n("search_path = ''") == n('search_path=""')
