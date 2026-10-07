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
    assert "--show | --loaded YYYYMM | --ym YYYYMM" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [["--loaded", "202609"], ["--loaded=202609"]])
def test_loaded(argv):
    assert target.parse_args(argv) == {"mode": "loaded", "ym": "202609"}


@pytest.mark.parametrize("argv", [
    ["--loaded"], ["--loaded", "2026Q3"], ["--loaded", "202609", "--ym", "202609"],
    ["--loaded=20269"], ["--loaded", "202609'--"],
])
def test_bad_loaded_args_stop(argv):
    with pytest.raises(ValueError):
        target.parse_args(argv)


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


# ── 3-2. --loaded 흐름 (2026-10-07 맹점 검사관 🟠2 — 복구 길이 게이트를 건너뛰지 않게) ─────


def test_set_loaded_sql_moves_only_the_loaded_columns():
    sql = target.build_set_loaded_sql("202609")
    assert sql.startswith("update snapshot_release set loaded_ym = '202609', loaded_at = now(),")
    assert "loaded_rows = (select count(*) from unit_business where snapshot_ym = '202609')" in sql
    assert "where id = 1;" in sql
    assert "published" not in sql, "--loaded 는 보여 주는 분기를 건드리지 않는다"
    with pytest.raises(ValueError):
        target.build_set_loaded_sql("2026Q3")


def _loaded_answers(monkeypatch, published="202606", count="2800000", loaded=None):
    """표지 두 칸(loaded|published)과 점포 표 행 수를 흉내 낸다. loaded 를 안 주면 published 와 같다."""
    asked, ran = [], []
    loaded = published if loaded is None else loaded
    answers = {target.FLAG_YMS_SQL: "{}|{}".format(loaded, published) if (loaded or published) else ""}

    def q(sql):
        asked.append(sql)
        return answers.get(sql, count)
    monkeypatch.setattr(target, "query_one", q)
    monkeypatch.setattr(target.dbx, "run_sql", lambda sql, **k: ran.append(sql) or 0)
    return asked, ran


def test_loaded_writes_only_loaded_then_points_to_post_load(monkeypatch, capsys):
    asked, ran = _loaded_answers(monkeypatch)
    assert target.main(["--loaded", "202609"]) == 0
    assert ran == [target.build_set_loaded_sql("202609")]
    assert target.build_exists_sql("202609") in asked
    out = capsys.readouterr().out
    assert "다 들어온 분기 = 202609" in out and "보여 주는 분기는 그대로 202606" in out
    assert out.rstrip().splitlines()[-1].startswith("이어서 python scripts/post_load.py")


def test_loaded_refuses_a_quarter_not_in_the_store_table(monkeypatch, capsys):
    _, ran = _loaded_answers(monkeypatch, count="0")
    assert target.main(["--loaded", "202609"]) == 1
    assert ran == []
    assert "202609 분기 행이 없습니다" in capsys.readouterr().out


def test_loaded_refuses_going_backwards(monkeypatch, capsys):
    _, ran = _loaded_answers(monkeypatch, published="202606")
    assert target.main(["--loaded", "202603"]) == 1
    assert ran == []
    assert "python scripts/publish_snapshot.py --ym 202603" in capsys.readouterr().out


def test_loaded_refuses_an_empty_flag_table(monkeypatch):
    _, ran = _loaded_answers(monkeypatch, published="")
    assert target.main(["--loaded", "202609"]) == 1
    assert ran == []


def test_loaded_write_failure_returns_1(monkeypatch):
    _loaded_answers(monkeypatch)
    monkeypatch.setattr(target.dbx, "run_sql", lambda sql, **k: 3)
    assert target.main(["--loaded", "202609"]) == 1


# ── 3-3. --loaded 는 앞으로만 — 지금 다 들어온 분기 기준 (2026-10-07 (2) · 재검사관 C 🟡) ──────────


def test_loaded_refuses_a_quarter_older_than_the_loaded_one(monkeypatch, capsys):
    """loaded 202606 · published 202603(되돌린 상태) 에 --loaded 202603 → 거부(RPC 의 '앞으로만'과 같은 결)."""
    asked, ran = _loaded_answers(monkeypatch, published="202603", loaded="202606")
    assert target.main(["--loaded", "202603"]) == 1
    assert ran == []
    assert asked == [target.FLAG_YMS_SQL], "거부하면 행 수도 안 센다"
    out = capsys.readouterr().out
    assert "[에러] 202603 은 지금 다 들어온 분기 202606 보다 옛 분기입니다" in out
    assert "python scripts/publish_snapshot.py --ym 202603" in out


def test_loaded_same_quarter_writes_nothing(monkeypatch, capsys):
    asked, ran = _loaded_answers(monkeypatch, published="202606", loaded="202609")
    assert target.main(["--loaded", "202609"]) == 0
    assert ran == [] and asked == [target.FLAG_YMS_SQL]
    assert "이미 다 들어온 분기가 202609 입니다 — 바꿀 것 없음(쓰기 0)" in capsys.readouterr().out


def test_loaded_newer_than_loaded_still_writes(monkeypatch):
    """음성: loaded 202606 · published 202603 에 --loaded 202609 는 그대로 적는다."""
    _, ran = _loaded_answers(monkeypatch, published="202603", loaded="202606")
    assert target.main(["--loaded", "202609"]) == 0
    assert ran == [target.build_set_loaded_sql("202609")]


@pytest.mark.parametrize("answer", ["", "202606|", "|202606", "202606"])
def test_loaded_refuses_an_unreadable_flag(monkeypatch, answer):
    ran = []
    monkeypatch.setattr(target, "query_one", lambda sql: answer)
    monkeypatch.setattr(target.dbx, "run_sql", lambda sql, **k: ran.append(sql) or 0)
    assert target.main(["--loaded", "202609"]) == 1
    assert ran == []


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
    assert "2772484행" in out  # 행 수가 파이썬에서 그대로 붙는지(2026-10-07 검사관 D 🟡 — 늘 "(기록 없음)" 회귀)
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


# ── 5. psql -c 로 가는 SQL 은 ASCII 만 (2026-10-07 라이브 예행연습 실사고) ─────────────────
#
# query_one 은 SQL 을 `psql -c <sql>` 인자로 넘긴다. Windows 에서 그 인자는 cp949 로 전달돼
# 한글이 든 SQL 이 서버에서 `invalid byte sequence for encoding "UTF8"` 로 죽는다 — --show 가
# `coalesce(…, '(기록 없음)')` 로 실제로 죽었다(pytest 는 query_one 을 바꿔 끼워 못 본다).
# 한글 표시는 파이썬에서 붙이고, 여기로 가는 SQL 은 전부 ASCII 여야 한다.


def non_ascii_chars(sql):
    """SQL 안의 비ASCII 글자 집합 — 가드 본체와 양성 대조가 같은 함수를 지난다."""
    return {c for c in sql if ord(c) > 127}


def test_sql_sent_through_psql_c_is_ascii():
    for sql in (target.SHOW_FLAG_SQL, target.SHOW_QUARTERS_SQL, target.SHOW_MVS_SQL,
                target.FLAG_YMS_SQL, target.build_exists_sql("202606")):
        assert non_ascii_chars(sql) == set(), sql[:80]


def test_non_ascii_detector_catches_the_original_bug():
    assert non_ascii_chars("coalesce(r.loaded_rows::text, '(기록 없음)')")  # 원래 죽었던 꼴
    assert non_ascii_chars("select 'x' || '\u00a0'")  # 눈에 안 보이는 글자도 잡는다 — 실제 문자로 들어간 경우


def test_show_renders_missing_row_count_in_python(monkeypatch, capsys):
    answers = {
        target.SHOW_FLAG_SQL: "202606|2026-10-07 10:00||202606|2026-10-07 10:05",
        target.SHOW_QUARTERS_SQL: "202606:2772484",
        target.SHOW_MVS_SQL: "202606|202606|202606",
    }
    monkeypatch.setattr(target, "query_one", lambda sql: answers[sql])
    assert target.main(["--show"]) == 0
    assert "(기록 없음)행" in capsys.readouterr().out
