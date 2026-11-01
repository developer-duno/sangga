# -*- coding: utf-8 -*-
"""scripts/collectors/load_sgis_district_pop.py(대전 상권 안 인구 결과표 → DB · 결정 0045 PR⑤)의 시험.

  · 관문 ⒜~⒣ 마다 걸리는 입력 하나 + 통과 입력(양성 대조) — 걸리면 DB 는 손도 안 댄다(dbx 자리에 부르면 바로
    실패하는 가짜를 늘 끼운다 · 관문이 회귀해도 운영 DB 로 못 간다)
  · 적재 SQL 모양 — lock_timeout 이 begin 앞 · TRUNCATE · 표지 upsert · ⒤⒥ raise 글 · 행수 대조
  · 로컬 PostgreSQL + psql 이 있으면 적재 SQL 을 실제로 돌린다 — 정상 · ⒤ 롤백 · ⒥ 롤백 · 같은 날 다시 넣기
"""

import datetime
import glob
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "scripts"), os.path.join(ROOT, "scripts", "collectors")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import load_sgis_district_pop as L  # noqa: E402

TODAY = datetime.date(2026, 11, 1)

ROWS = [
    ["sbiz-1", "좁은 상권", "주요상권", "30200", "163949.7", "13", "5", "99.995",
     "4348", "2513", "6172", "3213", "1800", "4000", "5201", "2819", "12161", "640", "300", "900"],
    ["sbiz-2", "넓은 상권", "주요상권", "30200", "9000.0", "2", "0", "100.0",
     "300", "0", "500", "100", "0", "200", "50", "0", "90", "5", "0", "9"],
]
META = {"received_on": "2026-10-08", "raw_dir": "req87909_2026-10-08", "base_year": 2024,
        "bnd_base_date": "2025-06-30", "n_oa_total": 108510, "n_oa_by_sido": {"30": 3050}, "sido": ["30"],
        "overlap_min_m2": 100.0, "full_ratio": 0.99, "partial": False, "n_clamped": 0,
        "built_at": "2026-11-01T19:30:59+09:00"}


def write_pair(d, rows=ROWS, meta_over=None, header=None, sha=None, nrows=None, name="20261008"):
    d.mkdir(parents=True, exist_ok=True)
    csv_path = d / (name + ".csv")
    lines = [",".join(header or L.COLUMNS)] + [",".join(r) for r in rows]
    csv_path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    meta = dict(META, rows=len(rows) if nrows is None else nrows,
                sha256=sha or hashlib.sha256(csv_path.read_bytes()).hexdigest())
    meta.update(meta_over or {})
    for k in [k for k, v in meta.items() if v is DROP]:
        del meta[k]
    (d / (name + ".meta.json")).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return str(csv_path)


DROP = object()


@pytest.fixture(autouse=True)
def no_real_db(monkeypatch):
    """dbx 자리에 부르면 바로 실패하는 가짜 — 관문이 회귀해도 시험이 운영 DB 로 못 간다."""
    import dbx  # noqa: PLC0415

    def boom(*_a, **_k):
        raise AssertionError("시험이 dbx.run_sql 을 불렀습니다 — 관문을 지나 실적재 길로 갔습니다")
    monkeypatch.setattr(dbx, "run_sql", boom)


def gate(csv_path, today=TODAY):
    meta = L.read_meta(csv_path)
    problems, stats = L.check_csv(csv_path, meta, today=today)
    return problems, stats


def codes(problems):
    return {p.split(" ")[0] for p in problems}


# ── 관문 ────────────────────────────────────────────────────────────────────


class TestGates:
    def test_good_pair_passes(self, tmp_path):
        problems, stats = gate(write_pair(tmp_path))
        assert problems == [] and stats["rows"] == 2 and stats["zero_full"] == 1 and stats["pop_sum"] == 4648

    @pytest.mark.parametrize("over,word", [
        ({"partial": True}, "partial"), ({"sido": ["11", "30"]}, "sido"), ({"base_year": "2024"}, "base_year"),
        ({"base_year": True}, "base_year"), ({"bnd_base_date": "20250630"}, "bnd_base_date"),
        ({"received_on": "2026-13-01"}, "received_on"), ({"built_at": "어제"}, "built_at"),
        ({"rows": DROP}, "rows"), ({"full_ratio": "0.99"}, "full_ratio"),
    ])
    def test_a_meta(self, tmp_path, over, word):
        with pytest.raises(L.GateError) as e:
            gate(write_pair(tmp_path, meta_over=over))
        assert "⒜" in str(e.value) and word in str(e.value)

    def test_a_missing_meta_or_csv(self, tmp_path):
        p = write_pair(tmp_path)
        os.remove(L.meta_path_for(p))
        with pytest.raises(L.GateError, match="⒜"):
            gate(p)
        with pytest.raises(L.GateError, match="⒜"):
            L.read_meta(str(tmp_path / "없음.csv"))

    def test_b_header(self, tmp_path):
        bad = list(L.COLUMNS)
        bad[8] = "population"
        with pytest.raises(L.GateError, match="⒝"):
            gate(write_pair(tmp_path, header=bad))

    def test_b_short_row(self, tmp_path):
        assert "⒝" in codes(gate(write_pair(tmp_path, rows=[ROWS[0][:-1], ROWS[1]]))[0])

    @pytest.mark.parametrize("rows", [
        [ROWS[0], ROWS[0]],                                   # 중복
        [[""] + ROWS[0][1:]],                                 # 빈 id
        [ROWS[0][:3] + ["11680"] + ROWS[0][4:]],              # 서울 시군구
        [ROWS[0][:3] + ["3020"] + ROWS[0][4:]],               # 네 자리
        [],                                                   # 줄 0
    ])
    def test_c_ids(self, tmp_path, rows):
        assert "⒞" in codes(gate(write_pair(tmp_path, rows=rows))[0])

    @pytest.mark.parametrize("col,val", [("pop", "-1"), ("pop", "1.5"), ("hh_hi", ""), ("area_m2", "abc"),
                                         ("pop", "7000"), ("emp_lo", "6000")])
    def test_d_numbers_and_order(self, tmp_path, col, val):
        r = list(ROWS[0])
        r[L.COLUMNS.index(col)] = val
        assert "⒟" in codes(gate(write_pair(tmp_path, rows=[r]))[0])

    @pytest.mark.parametrize("n_ov,n_full", [("0", "0"), ("2", "3")])
    def test_e_counts(self, tmp_path, n_ov, n_full):
        r = list(ROWS[1])
        r[5], r[6] = n_ov, n_full
        assert "⒠" in codes(gate(write_pair(tmp_path, rows=[r]))[0])

    @pytest.mark.parametrize("cov,bad", [("94.999", True), ("95.0", False), ("100.5", False), ("100.6", True)])
    def test_f_cover(self, tmp_path, cov, bad):
        r = list(ROWS[1])
        r[7] = cov
        assert ("⒡" in codes(gate(write_pair(tmp_path, rows=[r]))[0])) is bad

    def test_g_rows_and_fingerprint(self, tmp_path):
        assert "⒢" in codes(gate(write_pair(tmp_path, nrows=3))[0])
        assert "⒢" in codes(gate(write_pair(tmp_path / "b", sha="0" * 64))[0])

    @pytest.mark.parametrize("received,bad", [("2026-11-01", False), ("2026-11-02", True)])
    def test_h_received_not_in_future(self, tmp_path, received, bad):
        problems = gate(write_pair(tmp_path, meta_over={"received_on": received}))[0]
        assert ("⒣" in codes(problems)) is bad

    def test_main_dry_run_and_gate_failure_never_touch_the_db(self, tmp_path, capsys):
        p = write_pair(tmp_path)
        assert L.main(["--csv", p, "--dry-run"], today=TODAY) == 0
        assert "관문 통과" in capsys.readouterr().out
        bad = write_pair(tmp_path / "bad", nrows=9)
        assert L.main(["--csv", bad], today=TODAY) == 1          # 실적재 길이어도 관문에서 멈춘다(가짜 dbx 안 불림)

    def test_positive_control_real_load_path_reaches_dbx(self, tmp_path):
        """양성 대조 — 관문을 지난 실적재는 dbx 를 부른다(위 가짜가 실제로 지키고 있다)."""
        p = write_pair(tmp_path)
        with pytest.raises(AssertionError, match="dbx.run_sql"):
            L.main(["--csv", p, "--staging-dir", str(tmp_path / "st")], today=TODAY)

    def test_default_csv_is_the_latest_name(self, tmp_path):
        write_pair(tmp_path, name="20251001")
        write_pair(tmp_path, name="20261008")
        (tmp_path / "20261008.seoul_compare.csv").write_text("x", encoding="utf-8")
        assert os.path.basename(L.default_csv(str(tmp_path))) == "20261008.csv"
        assert L.default_csv(str(tmp_path / "없음")) is None


# ── SQL 모양 ────────────────────────────────────────────────────────────────


class TestSqlShape:
    @pytest.fixture
    def sql(self):
        return L.build_sql("C:\\x\\st.csv", 2, dict(META))

    def test_lock_timeout_before_begin_and_one_transaction(self, sql):
        assert sql.index("set lock_timeout = '5s';") < sql.index("begin;") < sql.index("commit;")
        assert sql.count("begin;") == 1 and sql.count("commit;") == 1
        assert "set local lock_timeout" not in sql

    def test_truncate_insert_and_release_upsert(self, sql):
        assert sql.index("truncate district_census_pop;") < sql.index("insert into district_census_pop (")
        assert "insert into sgis_census_release (id, received_on, base_year, bnd_base_date, n_oa_total, rows_cnt, built_at," in sql
        assert "values (1, date '2026-10-08', 2024, date '2025-06-30', 108510, 2," in sql
        assert "on conflict (id) do update set received_on = excluded.received_on" in sql
        assert "from 'C:/x/st.csv' with (format csv, header true, encoding 'UTF8')" in sql

    def test_gates_i_and_j_raise_inside_the_transaction(self, sql):
        i, j, t = sql.index("raise exception '⒤"), sql.index("raise exception '⒥"), sql.index("truncate")
        assert sql.index("begin;") < i < t and j < t
        assert "where left(d.sigungu_code, 2) in ('30')" in sql
        assert "where received_on > date '2026-10-08'" in sql          # 같은 날은 허용(>)
        # ⒤ 의 % 는 자리표시자 둘(v_missing · v_extra) — 글자 % 가 없다(있으면 too few parameters).
        line = sql[i:sql.index("\n", i)]
        assert line.count("%") == 2 and line.endswith("v_missing, v_extra;")

    def test_row_count_checks_before_and_after(self, sql):
        assert sql.count("<> 2 then") == 2


# ── 실제 실행 (로컬 PostgreSQL + psql 이 있을 때만) ──────────────────────────

MIG = (sorted(glob.glob(os.path.join(ROOT, "supabase", "migrations", "*_sgis_district_pop.sql")))
       or [os.path.join(ROOT, "supabase", "migrations", "(없음)_sgis_district_pop.sql")])[-1]
SHIM = """
create role anon;
create role authenticated;
create schema api;
create table parcel (pnu char(19) primary key, geom text, land_price_year smallint);
create table district (district_id text primary key, district_nm text, district_type text,
                       sigungu_code char(5), geom text, area_m2 numeric(14,2), computed_at timestamptz);
create function st_contains(poly text, pt text) returns boolean language sql immutable
  as 'select position(''|'' || pt || ''|'' in poly) > 0';
create table snapshot_release (published_ym text);
create table transaction (contract_ym text);
create table ledger_release (release_ym text);
create table lh_notice (collected_at timestamptz);
create table arch_permit (loaded_ym text);
create table nts_base_price (notice_date date);
create table rent_stat (quarter char(6));
create table district_openclose (quarter text);
create table daejeon_closure_release (received_on date);
create table district_sales (quarter char(5));
create table district_pop_flow (quarter char(5));
create table seoul_trdar_release (tbl text, value_quarter char(5));
create table store_history_release (last_ym char(6));
insert into district (district_id, district_nm, district_type, sigungu_code) values
  ('sbiz-1', '좁은 상권', '주요상권', '30200'), ('sbiz-2', '넓은 상권', '주요상권', '30200'),
  ('3001', '서울 상권', '골목상권', '11680');
"""


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    psycopg2 = pytest.importorskip("psycopg2")
    initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
    if not initdb or not pg_ctl or not shutil.which("psql"):
        pytest.skip("로컬 PostgreSQL(initdb·pg_ctl·psql)이 없다 — CI 는 관문·글자 시험만 본다")
    data = str(tmp_path_factory.mktemp("pgdata"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    subprocess.run([initdb, "-D", data, "-U", "postgres", "-A", "trust", "-E", "UTF8",
                    "--no-locale"], check=True, capture_output=True)
    log = os.path.join(data, "log.txt")
    # ⛔ capture_output 금지 — 서버 자식이 파이프를 물려받아 run() 이 끝없이 기다린다(Windows 실측).
    subprocess.run([pg_ctl, "-D", data, "-l", log, "-w", "-t", "60", "-o",
                    "-p {} -c listen_addresses=127.0.0.1".format(port), "start"],
                   check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=120)
    try:
        conn = None
        for _ in range(30):
            try:
                conn = psycopg2.connect(host="127.0.0.1", port=port, user="postgres", dbname="postgres")
                break
            except psycopg2.OperationalError:
                time.sleep(0.5)
        assert conn is not None, "로컬 PostgreSQL 에 못 붙었다"
        conn.autocommit = True
        yield conn
        conn.close()
    finally:
        subprocess.run([pg_ctl, "-D", data, "-m", "fast", "-w", "stop"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)


def _setup(pg, release=None):
    """흉내 판 + 마이그 통째 + 앞서 들어 있던 옛 줄 하나(+ 표지)."""
    c = pg.cursor()
    c.execute("drop schema if exists api cascade; drop schema if exists public cascade; create schema public;")
    c.execute("drop role if exists anon; drop role if exists authenticated;")
    c.execute(SHIM)
    with open(MIG, encoding="utf-8") as f:
        c.execute(f.read())
    c.execute("insert into district_census_pop values ('sbiz-old', '옛', null, '30200', 1, 1, 0, 99, "
              "1, 0, 1, 1, 0, 1, 1, 0, 1, 1, 0, 1)")
    if release:
        c.execute("insert into sgis_census_release values (1, %s, 2024, '2025-06-30', 1, 1, now(), 100, 0.99)",
                  (release,))
    return c


def _run(pg, tmp_path, rows=ROWS, meta_over=None):
    meta = dict(META, **(meta_over or {}))
    src = tmp_path / "result.csv"
    src.write_text(",".join(L.COLUMNS) + "\n" + "".join(",".join(r) + "\n" for r in rows), encoding="utf-8")
    staging = str(tmp_path / "staging" / "district_census_pop.csv")
    n = L.write_staging(str(src), staging)
    sql_path = tmp_path / "load.sql"
    sql_path.write_text(L.build_sql(staging, n, meta), encoding="utf-8")
    r = subprocess.run([shutil.which("psql"), "-h", "127.0.0.1", "-p", str(pg.info.port), "-U", "postgres",
                        "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-q", "-f", str(sql_path)],
                       env=dict(os.environ, PGCLIENTENCODING="UTF8"), stdin=subprocess.DEVNULL,
                       capture_output=True, timeout=120)
    return r.returncode, r.stderr.decode("utf-8", "replace")


def _state(c):
    c.execute("select string_agg(district_id, ',' order by district_id), sum(pop) from district_census_pop")
    rows = c.fetchone()
    c.execute("select received_on, base_year, rows_cnt from sgis_census_release")
    return rows, c.fetchall()


class TestRealRunLoadSql:
    def test_normal_load_replaces_everything_and_writes_the_release(self, pg, tmp_path):
        c = _setup(pg)
        rc, err = _run(pg, tmp_path)
        assert rc == 0, err
        assert _state(c) == (("sbiz-1,sbiz-2", 4648), [(datetime.date(2026, 10, 8), 2024, 2)])
        # 표지가 올라가 함수가 줄을 낸다(흉내 판 parcel 은 비어 있어 no_coord 한 줄 · 표지 받은 날이 실린다).
        c.execute("select status, received_on from api.get_district_census_pop('3020010100100010000')")
        assert c.fetchall() == [("no_coord", datetime.date(2026, 10, 8))]

    def test_i_mismatch_rolls_back(self, pg, tmp_path):
        """⒤ — 결과표에 sbiz-2 가 없고 서울 3001 이 있다 → raise → 옛 줄 그대로."""
        c = _setup(pg)
        seoul = ["3001"] + ROWS[0][1:3] + ["30200"] + ROWS[0][4:]
        rc, err = _run(pg, tmp_path, rows=[ROWS[0], seoul])
        assert rc != 0 and "⒤" in err and "1 · district 에 없는 줄 1" in err
        assert _state(c) == (("sbiz-old", 1), [])

    def test_j_earlier_received_rolls_back(self, pg, tmp_path):
        c = _setup(pg, release=datetime.date(2026, 12, 1))
        rc, err = _run(pg, tmp_path)
        assert rc != 0 and "⒥" in err
        assert _state(c) == (("sbiz-old", 1), [(datetime.date(2026, 12, 1), 2024, 1)])

    def test_j_same_day_reload_is_allowed(self, pg, tmp_path):
        c = _setup(pg, release=datetime.date(2026, 10, 8))
        rc, err = _run(pg, tmp_path)
        assert rc == 0, err
        assert _state(c)[1] == [(datetime.date(2026, 10, 8), 2024, 2)]
