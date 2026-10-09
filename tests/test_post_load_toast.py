# -*- coding: utf-8 -*-
"""`post_load.py --check` 의 별관(TOAST) 쫓겨남 경보(2026-10-05) — DB 없이 픽스처로만 본다.

큰 옆 칸(본관 고정 도형 등) 탓에 **작은 값**이 별관으로 쫓겨나면 그 칸을 훑는 쿼리가 10배
느려진다(2026-09-27 P10 #164). 경보는 [주의]까지만 — 종료 코드를 바꾸지 않는다.

⛔ 가드 본체와 양성 대조가 **같은 함수**(build_toast_scan_sql·parse_toast_scan·toast_evictions)를
   지난다. 라이브 양성 대조(임시 표)도 같은 함수로 쟀다 — PROGRESS 「2026-10-05 (5)」.
"""

import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

DISTRICT = [
    ("public", "district", c, "public.district", c)
    for c in ("district_id", "district_type", "sigungu_code", "dna_vector", "metrics", "raw_metrics")
]
STORE = [
    ("public", "mv_parcel_store_names", c, "public.mv_parcel_store_names", c)
    for c in ("pnu", "sigungu_code", "store_names", "store_names_key", "store_snapshot_ym")
]
TARGETS = DISTRICT + STORE


def targets_raw(targets):
    return json.dumps([list(t) for t in targets], ensure_ascii=False)


def scan_raw(rows):
    """psql 이 찍는 모양 그대로 — 앞에 `SET` 꼬리표, 마지막 줄이 결과."""
    return "SET\n" + json.dumps(rows)


def fake_query(monkeypatch, targets, rows, asked=None):
    def fake(sql):
        if asked is not None:
            asked.append(sql)
        if sql == post_load.TOAST_TARGETS_SQL:
            return targets_raw(targets)
        assert sql.startswith("set statement_timeout")
        return scan_raw(rows)
    monkeypatch.setattr(post_load, "query_one", fake)


FILTER_HEAD = "count(*) filter (where "
FILTER_COND_RE = re.compile(
    r"pg_column_toast_chunk_id\((?P<c>[^()]+)\) is not null"
    r" and pg_column_size\((?P=c)\) (?P<op><=|<|>=|>|=) (?P<n>\d+)")


def filter_clauses(sql):
    """생성된 SQL → [(칸, 비교 연산자, 기준 바이트)] — 시험이 기준을 실제 크기에 대 보는 데 쓴다.

    `count(*) filter (where ` 머리부터 짝이 맞는 닫는 `)` 까지 조건 **전체**를 떼어 꼴 하나와
    통째로(fullmatch) 맞춘다 — 조건 뒤에 `and false`·`or …` 를 덧붙인 꼴도 놓치지 않는다."""
    out = []
    start = sql.find(FILTER_HEAD)
    while start != -1:
        i = start + len(FILTER_HEAD)
        depth = 1                      # `filter (` 의 여는 괄호
        j = i
        while depth:
            if j >= len(sql):
                raise AssertionError("filter 괄호가 닫히지 않았습니다")
            depth += {"(": 1, ")": -1}.get(sql[j], 0)
            j += 1
        cond = sql[i:j - 1]
        m = FILTER_COND_RE.fullmatch(cond)
        if m is None:
            raise AssertionError("filter 조건 꼴이 다릅니다: {!r}".format(cond))
        out.append((m.group("c"), m.group("op"), m.group("n")))
        start = sql.find(FILTER_HEAD, j)
    return out


def counted(op, limit, size):
    return {"<": size < limit, "<=": size <= limit, ">": size > limit,
            ">=": size >= limit, "=": size == limit}[op]


class TestTargetsSql:
    def test_picks_only_tables_with_nonempty_toast_and_movable_varlena_columns(self):
        sql = post_load.TOAST_TARGETS_SQL
        assert "n.nspname in ('public','api')" in sql
        assert "c.relkind in ('r','m')" in sql
        assert "pg_relation_size(c.reltoastrelid) > 0" in sql      # 별관이 빈 표는 훑지 않는다
        assert "a.attlen = -1" in sql
        assert "a.attstorage in ('x','e')" in sql                  # m·p 는 본관 고정이라 뺀다
        assert "not a.attisdropped" in sql and "a.attnum > 0" in sql
        assert "format('%I.%I', n.nspname, c.relname)" in sql and "quote_ident(a.attname)" in sql

    def test_where_clause_is_exactly_the_approved_condition(self):
        """글자가 '들어 있나'만 보면 `… and false`·`(… or true)` 를 덧붙인 꼴이 살아남아 라이브에서
        "볼 칸 0 [정상]"이 조용히 초록이 된다 — WHERE 조건 전체를 통째로 맞춘다."""
        sql = " ".join(post_load.TOAST_TARGETS_SQL.split())
        assert sql.count(" where ") == 1
        where = sql.split(" where ", 1)[1]
        assert where == (
            "n.nspname in ('public','api') and c.relkind in ('r','m') "
            "and c.reltoastrelid <> 0 and pg_relation_size(c.reltoastrelid) > 0 "
            "and a.attnum > 0 and not a.attisdropped and a.attlen = -1 "
            "and a.attstorage in ('x','e');")

    def test_targets_query_also_has_statement_timeout(self):
        assert post_load.TOAST_TARGETS_SQL.startswith("set statement_timeout = '60s';\nselect ")

    def test_sql_is_ascii_only(self):
        """윈도우에서 psql -c 인자는 cp949 로 넘어가 한글이 서버에서 깨진다(2026-10-05 실측)."""
        assert post_load.TOAST_TARGETS_SQL.isascii()
        assert post_load.build_toast_scan_sql(TARGETS).isascii()


class TestParseTargets:
    def test_reads_last_line_as_json(self):
        assert post_load.parse_toast_targets("SET\n" + targets_raw(TARGETS)) == TARGETS

    def test_empty_array_means_nothing_to_scan(self):
        assert post_load.parse_toast_targets("[]") == []

    @pytest.mark.parametrize("raw", ["", "SET", '{"a": 1}', '[["public", "t", "c"]]',
                                     '[["public", "t", "c", "public.t", ""]]'])
    def test_bad_shape_raises(self, raw):
        with pytest.raises(ValueError):
            post_load.parse_toast_targets(raw)


class TestBuildScanSql:
    def test_one_scan_per_table(self):
        sql = post_load.build_toast_scan_sql(TARGETS)
        assert sql.count(" from public.district") == 1
        assert sql.count(" from public.mv_parcel_store_names") == 1
        assert sql.count("union all") == 1
        assert sql.startswith("set statement_timeout = '60s';\n")

    def test_every_column_has_the_small_value_filter(self):
        clauses = filter_clauses(post_load.build_toast_scan_sql(TARGETS))
        assert [c for c, _, _ in clauses] == [t[4] for t in TARGETS]

    def test_boundary_255_counted_256_not(self):
        """256바이트 **미만**만 센다 — 255 는 경보, 256 은 큰 값(정상). 라이브 임시 표 실측과 같다."""
        for _, op, limit in filter_clauses(post_load.build_toast_scan_sql(TARGETS)):
            assert counted(op, int(limit), 255) is True
            assert counted(op, int(limit), 256) is False

    def test_uses_server_quoted_names_as_given(self):
        odd = [("public", "Odd Tbl", "My Col", '"public"."Odd Tbl"', '"My Col"')]
        sql = post_load.build_toast_scan_sql(odd)
        assert 'from "public"."Odd Tbl"' in sql
        assert 'pg_column_toast_chunk_id("My Col")' in sql

    def test_no_targets_raises(self):
        with pytest.raises(ValueError):
            post_load.build_toast_scan_sql([])


class TestParseScanAndJudge:
    def test_maps_counts_back_to_columns(self):
        rows = [[0, 0, 0, 0, 0, 0, 3], [1, 0, 0, 0, 0, 0]]
        counts = post_load.parse_toast_scan(scan_raw(rows), TARGETS)
        assert ("public", "district", "raw_metrics", 3) in counts
        assert len(counts) == len(TARGETS)
        assert post_load.toast_evictions(counts) == [("public", "district", "raw_metrics", 3)]

    def test_order_of_rows_does_not_matter(self):
        rows = [[1, 0, 0, 0, 7, 0], [0, 0, 0, 0, 0, 0, 0]]
        found = post_load.toast_evictions(post_load.parse_toast_scan(scan_raw(rows), TARGETS))
        assert found == [("public", "mv_parcel_store_names", "store_names_key", 7)]

    def test_big_values_only_means_no_alarm(self):
        """큰 값만 별관에 있으면(지금 라이브의 630·429) SQL 이 0 을 돌려준다 → 경보 0."""
        rows = [[0, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0]]
        assert post_load.toast_evictions(post_load.parse_toast_scan(scan_raw(rows), TARGETS)) == []

    @pytest.mark.parametrize("rows", [
        [[0, 0, 0, 0, 0, 0, 0]],                                   # 표 하나가 빠짐
        [[0, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0]],                  # 칸 수 모자람
        [[0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0]],            # 같은 표 두 번
        [[0, 0, 0, 0, 0, 0, 0], [2, 0, 0, 0, 0, 0]],               # 없는 표 번호
        [[0, 0, 0, 0, 0, 0, 0], [1, 0, 0, True, 0, 0]],            # 숫자가 아님
        [[0, 0, 0, 0, 0, 0, 0], []],
    ])
    def test_bad_answer_raises(self, rows):
        with pytest.raises(ValueError):
            post_load.parse_toast_scan(scan_raw(rows), TARGETS)


class TestReport:
    def test_positive_prints_warning_and_fix(self, monkeypatch, capsys):
        fake_query(monkeypatch, TARGETS, [[0, 0, 0, 12, 0, 0, 0], [1, 0, 0, 0, 0, 0]])
        found = post_load.report_toast_evictions()
        out = capsys.readouterr().out
        assert found == [("public", "district", "sigungu_code", 12)]
        assert "[주의] 별관(TOAST)으로 쫓겨난 작은 값: public.district.sigungu_code 12개" in out
        assert "set storage main" in out
        assert "[정상]" not in out

    def test_negative_prints_scope(self, monkeypatch, capsys):
        asked = []
        fake_query(monkeypatch, TARGETS, [[0, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0]], asked)
        assert post_load.report_toast_evictions() == []
        out = capsys.readouterr().out
        assert "[정상] 별관 점검: 별관을 쓰는 표 2개 · 칸 11개 · 쫓겨난 작은 값(256바이트 미만) 0." in out
        assert len(asked) == 2

    def test_no_toast_tables_skips_the_scan(self, monkeypatch, capsys):
        asked = []
        fake_query(monkeypatch, [], [], asked)
        assert post_load.report_toast_evictions() == []
        assert "볼 칸 0" in capsys.readouterr().out
        assert asked == [post_load.TOAST_TARGETS_SQL]

    def test_query_failure_warns_and_does_not_raise(self, monkeypatch, capsys):
        def boom(sql):
            raise RuntimeError("function pg_column_toast_chunk_id does not exist")
        monkeypatch.setattr(post_load, "query_one", boom)
        assert post_load.report_toast_evictions() == []
        assert "[주의] 별관(TOAST) 점검을 하지 못했습니다: RuntimeError: function pg_column_toast_chunk_id" \
            in capsys.readouterr().out

    def test_psql_failure_prints_server_reason_not_command_line(self, monkeypatch, capsys):
        """psql 실패면 서버가 말한 마지막 줄만 — 명령줄(접속 주소·사용자 이름·SQL 전문)은 안 찍는다."""
        def boom(sql):
            raise subprocess.CalledProcessError(
                1, ["psql", "-h", "db.example.invalid", "-p", "5432", "-U", "someone", "-c", sql],
                output="SET\nERROR:  canceling statement due to statement timeout\n".encode("utf-8"))
        monkeypatch.setattr(post_load, "query_one", boom)
        assert post_load.report_toast_evictions() == []
        out = capsys.readouterr().out
        assert "[주의] 별관(TOAST) 점검을 하지 못했습니다: ERROR:  canceling statement due to statement timeout" \
            in out
        for leak in ("-h", "-U", "psql", "db.example.invalid", "someone", "pg_class"):
            assert leak not in out

    @staticmethod
    def _psql_fail(monkeypatch, output):
        def boom(sql):
            raise subprocess.CalledProcessError(1, ["psql", "-c", sql], output=output)
        monkeypatch.setattr(post_load, "query_one", boom)

    def test_error_line_wins_over_trailing_caret(self, monkeypatch, capsys):
        """재검사관 라이브 실측 꼴 — ERROR 뒤에 cp949 `줄 1: …` 와 `^` 가 온다. 마지막 줄(`^`)이 아니라 ERROR 줄."""
        output = (b'ERROR:  relation "x" does not exist\n'
                  + "줄 1: select 1 from x".encode("cp949") + b"\n         ^\n")
        self._psql_fail(monkeypatch, output)
        assert post_load.report_toast_evictions() == []
        out = capsys.readouterr().out
        assert 'relation "x" does not exist' in out
        assert "점검을 하지 못했습니다: ^" not in out

    def test_cp949_bytes_do_not_raise(self, monkeypatch, capsys):
        """utf-8 로 풀 수 없는 바이트(cp949)만 와도 예외 없이 한 줄이 나온다(strict 로 바꾸면 터진다)."""
        self._psql_fail(monkeypatch, "힌트:  어떤 안내".encode("cp949") + b"\n")
        assert post_load.report_toast_evictions() == []
        out = capsys.readouterr().out
        assert "[주의] 별관(TOAST) 점검을 하지 못했습니다: " in out

    def test_psql_connection_error_line_is_chosen(self, monkeypatch, capsys):
        self._psql_fail(monkeypatch, b"psql: error: connection to server failed: timeout expired\n")
        post_load.report_toast_evictions()
        assert "점검을 하지 못했습니다: psql: error: connection to server failed: timeout expired" \
            in capsys.readouterr().out

    def test_fix_hint_keeps_template_file_and_reload_ways(self, monkeypatch, capsys):
        """고치는 법 문구를 지킨다 — 본보기 파일 이름 · 일반 표 vacuum full · 요약표 concurrently 없는 refresh."""
        fake_query(monkeypatch, TARGETS, [[0, 0, 0, 1, 0, 0, 0], [1, 0, 0, 0, 0, 0]])
        post_load.report_toast_evictions()
        out = capsys.readouterr().out
        assert "supabase/migrations/2026-09-27d_district_name_storage.sql" in out
        assert os.path.exists(os.path.join(ROOT, "supabase", "migrations",
                                           "2026-09-27d_district_name_storage.sql"))
        assert "`vacuum full <표>`" in out
        assert "concurrently 없는 refresh" in out

    def test_psql_failure_without_output_says_so(self, monkeypatch, capsys):
        def boom(sql):
            raise subprocess.CalledProcessError(2, ["psql", "-U", "someone"], output=b"")
        monkeypatch.setattr(post_load, "query_one", boom)
        post_load.report_toast_evictions()
        out = capsys.readouterr().out
        assert "종료 코드 2" in out and "someone" not in out

    def test_short_answer_warns_instead_of_false_ok(self, monkeypatch, capsys):
        fake_query(monkeypatch, TARGETS, [[0, 0, 0, 0, 0, 0, 0]])
        assert post_load.report_toast_evictions() == []
        out = capsys.readouterr().out
        assert "[주의] 별관(TOAST) 점검을 하지 못했습니다" in out
        assert "[정상]" not in out


QUIET = (
    ("report_freshness", lambda: ("1", "1", False)),
    ("report_map_freshness", lambda: ({}, False)),
    ("report_tx_window_freshness", lambda: ("", "", False)),
    ("report_coverage_freshness", lambda: ("", "", False)),
    ("report_industry_mix_freshness", lambda: ("", "", False)),
    ("report_tx_geog_freshness", lambda: ("1", "1", False)),
    ("report_anon_exposure", lambda: ([], [])),
    ("report_write_exposure", lambda: []),
    ("report_slow_functions", lambda: []),
    ("report_canonical_indexes", lambda: []),
    ("report_function_drift", lambda: []),
    ("report_snapshot_release", lambda *a: (False, False)),
    ("report_store_names_freshness", lambda: ("", "", False)),
    ("report_industry_floor_freshness", lambda: ("", "", False)),
    ("report_industry_floor_consistency", lambda: ("0", False)),
    ("precheck_snapshot_release", lambda: (False, "202606", "")),
)


class TestExitCodeUnchanged:
    """⛔ 약속: 별관 경보는 [주의]까지만 — 걸려도 --check 의 종료 코드를 바꾸지 않는다."""

    def _quiet(self, monkeypatch):
        for name, val in QUIET:
            monkeypatch.setattr(post_load, name, val)

    def test_alarm_through_real_report_keeps_exit_0(self, monkeypatch, capsys):
        self._quiet(monkeypatch)
        fake_query(monkeypatch, TARGETS, [[0, 5, 5, 5, 5, 5, 5], [1, 9, 9, 9, 9, 9]])
        assert post_load.main(["--check"]) == 0
        assert "[주의] 별관(TOAST)으로 쫓겨난 작은 값" in capsys.readouterr().out

    def test_failure_through_real_report_keeps_exit_0(self, monkeypatch):
        self._quiet(monkeypatch)

        def boom(sql):
            raise RuntimeError("down")
        monkeypatch.setattr(post_load, "query_one", boom)
        assert post_load.main(["--check"]) == 0

    def test_other_incidents_still_exit_1(self, monkeypatch):
        self._quiet(monkeypatch)
        monkeypatch.setattr(post_load, "report_toast_evictions",
                            lambda: [("public", "district", "metrics", 3)])
        assert post_load.main(["--check"]) == 0
        monkeypatch.setattr(post_load, "report_canonical_indexes", lambda: [("idx_x", "없음")])
        assert post_load.main(["--check"]) == 1

    def test_called_in_check_only_not_in_apply(self, monkeypatch):
        calls = []
        self._quiet(monkeypatch)
        monkeypatch.setattr(post_load, "report_toast_evictions", lambda: calls.append(1) or [])
        post_load.main(["--check"])
        assert calls == [1]
        monkeypatch.setattr(post_load.dbx, "run_sql", lambda sql, **k: 0)
        post_load.main([])
        assert calls == [1]
