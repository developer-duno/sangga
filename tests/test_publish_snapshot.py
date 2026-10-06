# -*- coding: utf-8 -*-
"""scripts/publish_snapshot.py 1:1 단위 시험 (결정 0035 — 분기 표지 되돌리기·확인 전용).

지키는 것:
  1) 인자는 --show 또는 --ym YYYYMM 하나뿐 — 모르는 인자는 **멈춘다**(종료 코드 2).
     예전 형제 적재기에서 `--help` 가 실제 실행으로 새던 사고와 같은 종류를 막는다.
  2) --ym 은 **점포 표에 있는 분기만** — 없는 분기로 두면 화면 가게 칸이 통째로 빈다.
  3) 표지를 쓰는 SQL 은 두 칸을 **모두** 그 분기로(한 칸만 바꾸면 post_load 가 다시 올리거나
     '낡음'이 영영 안 풀린다) · 표가 비었어도 첫 줄을 만든다(upsert).
  4) 끝에 post_load.py 를 안내한다(요약표 셋은 그 뒤에야 그 분기로 다시 구워진다).
DB 없이 본다 — query_one·dbx.run_sql 을 바꿔 끼운다.
"""

import os
import sys

import pytest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import publish_snapshot as target  # noqa: E402


# ── 1. 인자 ──────────────────────────────────────────────────────────────────


def test_show():
    assert target.parse_args(["--show"]) == {"mode": "show"}


@pytest.mark.parametrize("argv", [["--ym", "202606"], ["--ym=202606"]])
def test_ym(argv):
    assert target.parse_args(argv) == {"mode": "ym", "ym": "202606"}


@pytest.mark.parametrize("argv", [
    [],                         # 아무것도 안 주면 무엇을 할지 모른다
    ["--help"],                 # 모르는 인자 — 실제 실행으로 새면 안 된다
    ["--ym"],                   # 값 없음
    ["--ym", "2026Q2"],         # 분기 꼴이 다름
    ["--ym", "20266"],          # 다섯 자리
    ["--ym", "202606", "--show"],
    ["--show", "--dry-run"],
    ["--ym", "202606'; drop table x; --"],
])
def test_unknown_or_bad_args_stop(argv):
    with pytest.raises(ValueError):
        target.parse_args(argv)


def test_main_returns_2_on_bad_args(monkeypatch, capsys):
    monkeypatch.setattr(target, "query_one", lambda sql: pytest.fail("인자가 틀렸는데 DB 를 물었습니다"))
    assert target.main(["--force"]) == 2
    assert "--show | --ym YYYYMM" in capsys.readouterr().out


# ── 2. SQL ───────────────────────────────────────────────────────────────────


def test_set_sql_moves_both_columns_and_counts_rows():
    sql = target.build_set_sql("202603")
    assert "insert into snapshot_release (id, loaded_ym, loaded_at, loaded_rows, published_ym, published_at)" in sql
    assert "on conflict (id) do update set loaded_ym = excluded.loaded_ym" in sql
    assert "published_ym = excluded.published_ym" in sql
    assert "(select count(*) from unit_business where snapshot_ym = '202603')" in sql
    assert sql.count("'202603'") == 3


@pytest.mark.parametrize("bad", ["", "2026Q2", "202606'--", None])
def test_sql_builders_refuse_odd_quarters(bad):
    with pytest.raises(ValueError):
        target.build_set_sql(bad)
    with pytest.raises(ValueError):
        target.build_exists_sql(bad)


@pytest.mark.parametrize("text,want", [("616096", True), ("0", False), ("", False), (" 3 ", True)])
def test_has_quarter(text, want):
    assert target.has_quarter(text) is want


# ── 3. --ym 흐름 ─────────────────────────────────────────────────────────────


def test_ym_refuses_a_quarter_that_is_not_in_the_store_table(monkeypatch, capsys):
    monkeypatch.setattr(target, "query_one", lambda sql: "0")
    monkeypatch.setattr(target.dbx, "run_sql", lambda *a, **k: pytest.fail("없는 분기로 표지를 썼습니다"))
    assert target.main(["--ym", "201512"]) == 1
    assert "201512 분기 행이 없습니다" in capsys.readouterr().out


def test_ym_writes_then_points_to_post_load(monkeypatch, capsys):
    asked, ran = [], []
    monkeypatch.setattr(target, "query_one", lambda sql: asked.append(sql) or "616096")
    monkeypatch.setattr(target.dbx, "run_sql", lambda sql, **k: ran.append(sql) or 0)
    assert target.main(["--ym", "202603"]) == 0
    assert asked == [target.build_exists_sql("202603")]
    assert ran == [target.build_set_sql("202603")]
    out = capsys.readouterr().out
    assert "표지 = 202603" in out
    assert out.rstrip().splitlines()[-1].startswith("이어서 python scripts/post_load.py")


def test_ym_write_failure_returns_1(monkeypatch):
    monkeypatch.setattr(target, "query_one", lambda sql: "616096")
    monkeypatch.setattr(target.dbx, "run_sql", lambda sql, **k: 3)
    assert target.main(["--ym", "202603"]) == 1


# ── 4. --show 흐름 (DB 쓰기 0) ───────────────────────────────────────────────


def test_show_prints_flag_quarters_and_summary_tables(monkeypatch, capsys):
    answers = {
        target.SHOW_FLAG_SQL: "202606|2026-10-07 10:00|2772484|202606|2026-10-07 10:05",
        target.SHOW_QUARTERS_SQL: "202603:616096,202606:2772484",
        target.SHOW_MVS_SQL: "202606|202606|202606",
    }
    monkeypatch.setattr(target, "query_one", lambda sql: answers[sql])
    monkeypatch.setattr(target.dbx, "run_sql", lambda *a, **k: pytest.fail("--show 가 DB 에 썼습니다"))
    assert target.main(["--show"]) == 0
    out = capsys.readouterr().out
    assert "다 들어온 분기 202606" in out and "보여 주는 분기 202606" in out
    assert "202603 616096 · 202606 2772484" in out
    assert "각주 202606 · 업종 202606 · 가게 이름 202606" in out


def test_show_empty_flag_is_called_an_incident(monkeypatch, capsys):
    answers = {target.SHOW_FLAG_SQL: "", target.SHOW_QUARTERS_SQL: "", target.SHOW_MVS_SQL: "||"}
    monkeypatch.setattr(target, "query_one", lambda sql: answers[sql])
    assert target.main(["--show"]) == 0
    assert "[사고] 표지(snapshot_release)가 비었습니다" in capsys.readouterr().out


def test_show_sql_reads_only():
    for sql in (target.SHOW_FLAG_SQL, target.SHOW_QUARTERS_SQL, target.SHOW_MVS_SQL):
        low = sql.lower()
        assert low.startswith("select ")
        for word in ("insert", "update ", "delete", "drop ", "alter "):
            assert word not in low, word
