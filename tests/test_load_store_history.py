# -*- coding: utf-8 -*-
"""scripts/collectors/load_store_history.py 단위 테스트 (결정 0045 PR④ · 적재기 1:1).

DB 없이 본다:
  1. 양성 대조 — 작은 결과표(csv + meta)는 관문 ⒜~⒥ 를 지난다(dry-run 0 · 파일 0 · dbx import 0)
  2. 관문 ⒜~⒥ 각각 걸림(exit 1 · 메시지 앞 글자)
  3. 가장 늦은 결과표 고르기
  4. 적재 SQL 모양(begin/commit · truncate · 표지 upsert · ⒦ raise · \\copy 경로 · 열 칸 차례)
  5. 실적재 길 — 가짜 dbx 로 SQL 이 한 번 나가고 사본 csv 가 써진다
"""

import hashlib
import io
import json
import os
import sys
import types

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COLLECTORS_DIR = os.path.join(_ROOT, "scripts", "collectors")
if _COLLECTORS_DIR not in sys.path:
    sys.path.insert(0, _COLLECTORS_DIR)

import load_store_history as L  # noqa: E402

PD = "3017010100100010000"
PS = "1168010100100010000"
HEADER = "pnu,floor_no,biz_name,biz_no_last,first_ym,last_ym,seen_cnt,is_current,n_links,truncated"


def base_rows():
    return [
        [PD, "1", "김밥", "D1", "201712", "201803", "2", "t", "0", "t"],
        [PS, "", "카페", "S1", "201803", "201803", "1", "t", "1", "f"],
        [PD, "-1", "옛가게", "D2", "201712", "201712", "1", "f", "0", "t"],
    ]


def base_meta():
    return {"built_on": "2026-11-01", "start_ym": "201712", "end_ym": "201803", "sido": ["11", "30"],
            "quarters": 2, "rows": 3, "current_rows": 2, "n_links": 1, "pnu_changed": 0, "dup_biz_no": 0,
            "bad_pnu": 0, "partial": False, "sha256": None}


def make_result(tmp_path, rows=None, meta=None, name="20261101", header=HEADER, fix_sha=True):
    d = tmp_path / "derived"
    d.mkdir(exist_ok=True)
    rows = base_rows() if rows is None else rows
    path = d / (name + ".csv")
    body = header + "\n" + "".join(",".join(r) + "\n" for r in rows)
    path.write_bytes(body.encode("utf-8"))
    m = base_meta()
    m["rows"] = len(rows)
    if fix_sha:
        m["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    m.update(meta or {})
    (d / (name + ".meta.json")).write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    return str(path)


@pytest.fixture
def small_ranges(monkeypatch):
    monkeypatch.setattr(L, "ROWS_RANGE", (1, 10))
    monkeypatch.setattr(L, "CURRENT_RANGE", (1, 10))


# ── 1. 양성 대조 ─────────────────────────────────────────────────────────────


def test_small_result_passes_dry_run_writes_nothing(tmp_path, small_ranges, capsys):
    path = make_result(tmp_path)
    staging = tmp_path / "staging"
    sys.modules.pop("dbx", None)
    rc = L.main(["--csv", path, "--dry-run", "--staging-dir", str(staging)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "관문 통과" in out and "⒦" in out and "실적재 때 DB 안에서" in out
    assert "줄 3 · 지금 보임 2 · 층 모름 1" in out
    assert not staging.exists()
    assert "dbx" not in sys.modules


# ── 2. 관문 ──────────────────────────────────────────────────────────────────


def gate_of(tmp_path, capsys, rows=None, meta=None, header=HEADER, fix_sha=True):
    path = make_result(tmp_path, rows=rows, meta=meta, header=header, fix_sha=fix_sha)
    sys.modules.pop("dbx", None)
    rc = L.main(["--csv", path, "--staging-dir", str(tmp_path / "staging")])   # 실적재여도
    err = capsys.readouterr().err
    assert rc == 1
    assert "dbx" not in sys.modules
    assert not (tmp_path / "staging").exists()
    return err


def test_a_missing_meta(tmp_path, small_ranges, capsys):
    path = make_result(tmp_path)
    os.remove(L.meta_path_for(path))
    assert L.main(["--csv", path, "--dry-run"]) == 1
    assert "⒜" in capsys.readouterr().err


def test_a_missing_csv(tmp_path, capsys):
    assert L.main(["--csv", str(tmp_path / "없음.csv"), "--dry-run"]) == 1
    assert "⒜" in capsys.readouterr().err


@pytest.mark.parametrize("meta", [{"partial": True}, {"sido": ["11"]}, {"start_ym": "201512"},
                                  {"end_ym": "201802"}, {"built_on": "2026-13-01"}])
def test_a_meta_shape(tmp_path, small_ranges, capsys, meta):
    assert "⒜" in gate_of(tmp_path, capsys, meta=meta)


def test_b_header(tmp_path, small_ranges, capsys):
    assert "⒝" in gate_of(tmp_path, capsys, header=HEADER.replace("seen_cnt,is_current", "is_current,seen_cnt"))


def edit(i, j, value):
    rows = base_rows()
    rows[i][j] = value
    return rows


@pytest.mark.parametrize("rows", [
    edit(0, 4, "201711"),                    # 분기 꼴
    edit(2, 5, "201706"),                    # first > last · first < start
    edit(1, 5, "201806"),                    # last > end
    edit(2, 7, "t"),                         # is_current ⇔ last = end
    edit(1, 9, "t"),                         # truncated ⇔ first = start
    edit(0, 7, "true"),                      # t/f 만
])
def test_c_quarters_and_flags(tmp_path, small_ranges, capsys, rows):
    assert "⒞" in gate_of(tmp_path, capsys, rows=rows)


@pytest.mark.parametrize("pnu", ["301701010010001000", "4117010100100010000", "30170101001000100x0"])
def test_d_pnu(tmp_path, small_ranges, capsys, pnu):
    assert "⒟" in gate_of(tmp_path, capsys, rows=edit(0, 0, pnu))


@pytest.mark.parametrize("j, value", [(6, "0"), (6, "3"), (8, "-1"), (6, "x")])
def test_e_counts(tmp_path, small_ranges, capsys, j, value):
    assert "⒠" in gate_of(tmp_path, capsys, rows=edit(0, j, value))


def test_f_duplicate_key(tmp_path, small_ranges, capsys):
    rows = base_rows()
    rows.append([PD, "2", "다른가게", "D1", "201712", "201712", "1", "f", "0", "t"])
    assert "⒡" in gate_of(tmp_path, capsys, rows=rows)


def test_g_row_ranges(tmp_path, capsys):
    err = gate_of(tmp_path, capsys)   # 본 범위(900,000~) 그대로면 작은 표는 걸린다
    assert "⒢" in err and "줄 수 3" in err and "지금 보이는 줄 2" in err


def test_h_rows_mismatch(tmp_path, small_ranges, capsys):
    assert "⒣" in gate_of(tmp_path, capsys, meta={"rows": 4})


def test_h_sha_mismatch(tmp_path, small_ranges, capsys):
    assert "⒣" in gate_of(tmp_path, capsys, meta={"sha256": "0" * 64})


@pytest.mark.parametrize("floor_no", ["0", "100", "-10", "1층"])
def test_i_floor(tmp_path, small_ranges, capsys, floor_no):
    assert "⒤" in gate_of(tmp_path, capsys, rows=edit(0, 1, floor_no))


def test_j_empty_name(tmp_path, small_ranges, capsys):
    assert "⒥" in gate_of(tmp_path, capsys, rows=edit(0, 2, " "))


# ── 3. 결과표 고르기 ─────────────────────────────────────────────────────────


def test_default_csv_picks_latest_name(tmp_path):
    d = tmp_path / "derived"
    d.mkdir()
    for n in ("20261101.csv", "20270201.csv", "20270201.meta.json", "latest.csv"):
        (d / n).write_text("x", encoding="utf-8")
    assert os.path.basename(L.default_csv(str(d))) == "20270201.csv"
    assert L.default_csv(str(tmp_path / "없음")) is None


# ── 4. 적재 SQL ──────────────────────────────────────────────────────────────


def test_build_sql_shape():
    sql = L.build_sql("C:\\a\\b'c\\store_history.csv", 1234, base_meta())
    assert sql.startswith("begin;") and sql.rstrip().endswith("commit;")
    assert "set local lock_timeout = '5s';" in sql and "set local statement_timeout = '600s';" in sql
    cols = ", ".join(L.COLUMNS)
    assert ("\\copy stage_history ({}) from 'C:/a/b''c/store_history.csv' "
            "with (format csv, header true, encoding 'UTF8')").format(cols) in sql
    assert "create temp table stage_history (like store_history including defaults) on commit drop;" in sql
    assert "(select loaded_ym from snapshot_release) is distinct from '201803'" in sql
    assert "raise exception '⒦" in sql
    assert "truncate store_history;" in sql
    assert "insert into store_history_release (id, first_ym, last_ym, built_on, row_cnt, loaded_at)" in sql
    assert "values (1, '201712', '201803', date '2026-11-01', 1234, now())" in sql
    assert "on conflict (id) do update set first_ym = excluded.first_ym, last_ym = excluded.last_ym" in sql
    assert sql.count("<> 1234 then") == 2
    # ⒦ 는 지우기(truncate) 앞에서 본다
    assert sql.index("⒦") < sql.index("truncate store_history;")


def test_columns_order():
    assert ",".join(L.COLUMNS) == HEADER


# ── 5. 실적재 길(가짜 dbx) ──────────────────────────────────────────────────


def test_real_load_writes_staging_and_runs_sql_once(tmp_path, small_ranges, monkeypatch, capsys):
    path = make_result(tmp_path)
    sent = []
    monkeypatch.setitem(sys.modules, "dbx", types.SimpleNamespace(run_sql=lambda sql: sent.append(sql) or 0))
    staging = tmp_path / "staging"
    assert L.main(["--csv", path, "--staging-dir", str(staging)]) == 0
    copy = staging / "store_history.csv"
    assert copy.exists()
    assert io.open(copy, encoding="utf-8").read().splitlines()[0] == HEADER
    assert len(sent) == 1 and copy.as_posix() in sent[0]
    assert "다음: python scripts/post_load.py" in capsys.readouterr().out


def test_real_load_reports_psql_failure(tmp_path, small_ranges, monkeypatch):
    path = make_result(tmp_path)
    monkeypatch.setitem(sys.modules, "dbx", types.SimpleNamespace(run_sql=lambda sql: 3))
    assert L.main(["--csv", path, "--staging-dir", str(tmp_path / "staging")]) == 3
