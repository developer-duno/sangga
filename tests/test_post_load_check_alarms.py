# -*- coding: utf-8 -*-
"""`post_load.py --check` 의 경보 셋(2026-09-27 P7) — DB 없이 픽스처로만 본다.

  ① 느려짐 — **지난 점검 이후** 평균이 1초를 넘으면 [주의](종료 코드 1 아님)
  ② 정본 색인 — schema.sql 의 색인이 라이브에 없거나 invalid 면 [사고]
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

    def test_stats_since_changed_is_a_reset_not_a_comparison(self):
        """통계가 초기화된 줄은 이번엔 안 센다(느린 새 누적이 있어도)."""
        prev = {"1:10": entry("search_buildings", 50, 5000.0, since="1756000000")}
        cur = {"1:10": entry("search_buildings", 60, 600000.0, since="1756099999")}
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


# ── ② 정본 색인 ──────────────────────────────────────────────────────────────


INDEX_FIXTURE = """
create index if not exists idx_a on t (a);
create unique index if not exists idx_b     on t (b);
create unique index if not exists mv_key
  on mv (k);
  create index concurrently idx_c on t (c);
-- create index if not exists idx_commented on t (x);
create index if not exists idx_a on t (a);
"""


class TestCanonicalIndexes:
    def test_parser_forms(self):
        assert post_load.canonical_index_names(INDEX_FIXTURE) == ["idx_a", "idx_b", "mv_key", "idx_c"]

    def test_parser_reads_every_index_in_the_real_schema(self):
        """⛔ 파서가 헛돌면 '문제 0' 이 가짜 초록이 된다 — 머리 수와 대조한다."""
        raw = read_schema()
        heads = len(re.findall(r"(?im)^\s*create\s+(?:unique\s+)?index\b", raw))
        names = post_load.canonical_index_names(raw)
        assert len(names) == heads
        assert heads >= 50
        for must in ("idx_parcel_updated_at", "idx_msp_pnu", "mv_district_industry_mix_key"):
            assert must in names

    def test_problems(self):
        live = "idx_a|true\nidx_b|false\n\n"
        got = post_load.index_problems(["idx_a", "idx_b", "idx_c"], live)
        assert [n for n, _ in got] == ["idx_b", "idx_c"]
        assert "indisvalid" in got[0][1] and "없음" in got[1][1]

    def test_all_present_and_valid_is_clean(self):
        assert post_load.index_problems(["idx_a"], "idx_a|true\nidx_live_only|false") == []


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
)


def md5(s):
    return hashlib.md5(s.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def live_line(schema, name, lang, body, cfg):
    return "{}|{}|{}|{}|{}".format(schema, name, lang, md5(body), cfg)


LIVE_SAME = "\n".join([
    live_line("public", "f", "sql", BODY_F, "search_path=public, extensions, pg_temp"),
    live_line("api", "g", "sql", "\n  select public.f('a');\n", 'search_path=""'),
    live_line("public", "live_only", "plpgsql", "x", ""),
])


class TestCanonicalFunctions:
    def test_parser_reads_language_body_and_settings(self):
        got = post_load.canonical_functions(FN_FIXTURE)
        assert got["public.f"] == ("sql", md5(BODY_F), "search_path=public,extensions,pg_temp")
        assert got["api.g"][0] == "sql"
        assert got["api.g"][2] == "search_path="

    def test_parser_reads_every_function_in_the_real_schema(self):
        raw = read_schema()
        heads = len(post_load.CANON_FN_HEAD_RE.findall(raw))
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
        assert post_load.function_drift(canon, only_f) == [("api.g", ["라이브에 없음"])]
        twice = LIVE_SAME + "\n" + LIVE_SAME.splitlines()[0]
        bad = post_load.function_drift(canon, post_load.parse_live_functions(twice))
        assert bad[0][0] == "public.f" and "오버로드" in bad[0][1][0]

    def test_config_forms_meet(self):
        n = post_load._norm_config
        assert n("search_path = public, extensions, pg_temp") == n("search_path=public, extensions, pg_temp")
        assert n("search_path = ''") == n('search_path=""')
