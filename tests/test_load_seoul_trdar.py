# -*- coding: utf-8 -*-
"""scripts/collectors/load_seoul_trdar.py 단위 테스트 (결정 0045 PR② · 적재기 1:1).

DB 없이 본다:
  1. 칸 표 — 서비스마다 숫자 칸 수(48·22·24·21) · CSV 칸 = 마이그레이션 표 칸(글자 대조)
  2. ⒞ 정수 변환(157199.0 · 1880979478.0 · 소수 꼬리·null 은 걸림)
  3. 관문 ⒜ ⒝ ⒟ ⒠ ⒢ ⒣ — 각각 걸림 + 양성 대조(정상 자료는 통과)
  4. 분기 파일 고르기(같은 분기 두 날짜 → 최신 · `_pages/` 는 안 봄)
  5. 값 바뀐 분기(바뀜 없음 → 첫 분기 · 중간만 바뀜 → 그 분기 · 한쪽에만 있는 상권은 안 셈)
  6. build_sql 글자(begin/commit · \\copy 경로 · 관문 ⒤ raise · 분기 delete · 표지 upsert · 행수 확인)
  7. main — dry-run 쓰기 0 · 4종 중 하나 raw 없음 → exit 1 · 관문 걸림 → staging 조각 0
"""

import json
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "scripts"), os.path.join(_ROOT, "scripts", "collectors")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import load_seoul_trdar as L  # noqa: E402

MIGRATION = os.path.join(_ROOT, "supabase", "migrations", "2026-10-31a_seoul_trdar.sql")
D1, D2 = "3110001", "3110002"


def raw_row(service, quarter, district, value=10.0, induty="CS100001"):
    r = {"STDR_YYQU_CD": quarter, "TRDAR_SE_CD": "A", "TRDAR_SE_CD_NM": "골목상권",
         "TRDAR_CD": district, "TRDAR_CD_NM": "어느 상권"}
    if service == "sales":
        r.update({"SVC_INDUTY_CD": induty, "SVC_INDUTY_CD_NM": "한식음식점"})
    r.update({c: value for c in L.NUM_COLS[service]})
    return r


def write_q(raw_dir, service, quarter, rows, date="20261031"):
    d = os.path.join(str(raw_dir), service)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "{}_{}.jsonl".format(quarter, date))
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"quarter": quarter, "fetched_at": "x", "row": r}, ensure_ascii=False) + "\n")
    return p


def all_quarters(last="20262"):
    out, y, q = [], 2021, 1
    while True:
        cur = "{}{}".format(y, q)
        out.append(cur)
        if cur == last:
            return out
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)


@pytest.fixture
def small_ranges(monkeypatch):
    """행수 범위를 작게 — 시험 자료(분기당 몇 줄)로 ⒠ 가 지나게."""
    monkeypatch.setattr(L, "ROWS_PER_QUARTER", {s: (1, 10) for s in L.SERVICES})


# ── 1. 칸 표 ─────────────────────────────────────────────────────────────────


def test_numeric_column_counts():
    assert {s: len(c) for s, c in L.NUM_COLS.items()} == {"sales": 48, "flow": 22, "resident": 24, "worker": 21}
    assert len(L.raw_cols("sales")) == 55 and len(L.raw_cols("flow")) == 27
    assert len(L.raw_cols("resident")) == 29 and len(L.raw_cols("worker")) == 26


def table_columns(sql, table):
    m = re.search(r"(?ms)^create table if not exists " + table + r" \((.*?)\n\);", sql)
    assert m, table
    return tuple(ln.split()[0] for ln in m.group(1).splitlines()
                 if ln.strip() and not ln.strip().startswith(("--", "primary key")))


@pytest.mark.parametrize("service", L.SERVICES)
def test_csv_columns_are_the_table_columns(service):
    """CSV 칸 = 마이그레이션 표 칸(loaded_at 빼고 · 같은 차례) — 한 칸이 어긋나면 \\copy 가 엉뚱한 칸에 넣는다."""
    cols = table_columns(open(MIGRATION, encoding="utf-8").read(), L.TABLES[service])
    assert L.csv_columns(service) == tuple(c for c in cols if c != "loaded_at")


# ── 2. ⒞ 정수 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("v,want", [(157199.0, 157199), (1880979478.0, 1880979478), ("12", 12), (0.0, 0)])
def test_to_int_accepts_integer_values(v, want):
    assert L.to_int(v, "c", "w") == want


@pytest.mark.parametrize("v", [157199.5, "3.01", None, "", "  ", "abc", float("nan")])
def test_to_int_refuses_fraction_null_and_text(v):
    with pytest.raises(L.GateError, match="⒞"):
        L.to_int(v, "c", "w")


# ── 3. 관문 ──────────────────────────────────────────────────────────────────


def test_good_quarter_passes(small_ranges):
    rows = [L.normalize("flow", raw_row("flow", "20262", d), "20262", "f", "w") for d in (D1, D2)]
    assert L.quarter_problems("flow", "20262", rows, {D1, D2}) == []


def test_gate_a_unknown_district(small_ranges):
    rows = [L.normalize("flow", raw_row("flow", "20262", "9999999"), "20262", "f", "w")]
    assert any(m.startswith("⒜") for m in L.quarter_problems("flow", "20262", rows, {D1}))


def test_gate_b_mixed_quarter_and_columns():
    with pytest.raises(L.GateError, match="⒝"):
        L.normalize("flow", raw_row("flow", "20261", D1), "20262", "f", "w")
    bad = raw_row("worker", "20262", D1)
    bad["NEW_COL"] = 1.0
    with pytest.raises(L.GateError, match="모르는 칸"):
        L.normalize("worker", bad, "20262", "f", "w")
    gone = raw_row("worker", "20262", D1)
    gone.pop("TOT_WRC_POPLTN_CO")
    with pytest.raises(L.GateError, match="빠진 칸"):
        L.normalize("worker", gone, "20262", "f", "w")


def test_gate_b_line_quarter_only_differs(tmp_path):
    """G2 — 줄의 quarter 칸만 파일 분기와 다르고 행 STDR_YYQU_CD 는 같은 꼴: 줄 검사만이 잡는다(행 검사는 지나간다)."""
    d = tmp_path / "flow"
    d.mkdir()
    p = d / "20262_20261031.jsonl"
    p.write_text(json.dumps({"quarter": "20261", "fetched_at": "x", "row": raw_row("flow", "20262", D1)},
                            ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(L.GateError, match="줄의 quarter"):
        L.read_quarter_file("flow", str(p), "20262")


def test_gate_b_line_quarter_mismatch(tmp_path):
    p = write_q(tmp_path, "flow", "20262", [raw_row("flow", "20262", D1)])
    with pytest.raises(L.GateError, match="⒝"):
        L.read_quarter_file("flow", p, "20261")


def test_gate_d_duplicates(small_ranges):
    r = L.normalize("sales", raw_row("sales", "20262", D1), "20262", "f", "w")
    assert any(m.startswith("⒟") for m in L.quarter_problems("sales", "20262", [r, r], None))
    other = L.normalize("sales", raw_row("sales", "20262", D1, induty="CS100002"), "20262", "f", "w")
    assert L.quarter_problems("sales", "20262", [r, other], None) == []      # 업종이 다르면 중복 아님


def test_gate_a_and_e_point_to_the_district_source(small_ranges):
    """F5 — ⒜·⒠ 멈춤 문구 끝에 상권 경계 원천을 먼저 보라는 한 줄(다른 관문 문구엔 없다)."""
    rows = [L.normalize("flow", raw_row("flow", "20262", "9999999"), "20262", "f", "w")]
    a = [m for m in L.quarter_problems("flow", "20262", rows, {D1}) if m.startswith("⒜")]
    assert a and a[0].endswith(L.DISTRICT_HINT) and "fetch_seoul_district.py" in a[0]
    big = [L.normalize("worker", raw_row("worker", "20262", "31100{:02d}".format(i)), "20262", "f", "w")
           for i in range(11)]
    e = [m for m in L.quarter_problems("worker", "20262", big, None) if m.startswith("⒠")]
    assert e and e[0].endswith(L.DISTRICT_HINT)
    r = L.normalize("sales", raw_row("sales", "20262", D1), "20262", "f", "w")
    d = [m for m in L.quarter_problems("sales", "20262", [r, r], None) if m.startswith("⒟")]
    assert d and L.DISTRICT_HINT not in d[0]


@pytest.mark.parametrize("people_q,warned", [("20254", True), ("20262", False)])
def test_people_older_than_sales_warns(people_q, warned):
    """F4 — 상주 max 가 다른 서비스 max 보다 옛 분기면 경고 한 줄(멈추지 않음) · 같으면 없음(양성·음성)."""
    reps = {"sales": {"max_quarter": "20262"}, "flow": {"max_quarter": "20262"},
            "resident": {"max_quarter": people_q}, "worker": {"max_quarter": "20262"}}
    w = L.stale_tail_warnings(reps)
    assert len(w) == (1 if warned else 0)
    if warned:
        assert w[0] == "[경고] resident 가 20262보다 옛 분기(20254)까지만 — 서울시는 네 자료를 같은 날 게시한다(2026-09-11)"


@pytest.mark.parametrize("sales_q,n", [("20254", 1), ("20262", 0)])
def test_any_service_with_a_missing_tail_warns(sales_q, n):
    """G4 — 매출 쪽 꼬리가 빠져도(sales 20254 · flow 20262) 경고 1 · 넷 다 같으면 0."""
    reps = {"sales": {"max_quarter": sales_q}, "flow": {"max_quarter": "20262"},
            "resident": {"max_quarter": "20262"}, "worker": {"max_quarter": "20262"}}
    w = L.stale_tail_warnings(reps)
    assert len(w) == n
    if n:
        assert w[0].startswith("[경고] sales 가 20262보다 옛 분기(20254)까지만")


def test_gate_e_row_count_range():
    rows = [L.normalize("resident", raw_row("resident", "20262", D1), "20262", "f", "w")]
    assert any(m.startswith("⒠") for m in L.quarter_problems("resident", "20262", rows, None))
    assert L.ROWS_PER_QUARTER == {"sales": (18_000, 26_000), "flow": (1_600, 1_700),
                                  "resident": (1_600, 1_700), "worker": (1_600, 1_700)}


def test_gate_g_missing_and_older_quarters():
    assert L.missing_quarters(all_quarters()) == ([], [])
    qs = [q for q in all_quarters() if q != "20233"]
    assert L.missing_quarters(qs) == (["20233"], [])
    assert L.missing_quarters(["20204"] + all_quarters("20212")) == ([], ["20204"])
    # 끝이 다른 두 서비스 — 각자 제 범위면 통과
    assert L.missing_quarters(all_quarters("20254")) == ([], [])


def test_gate_h_induty_code_shape_and_set_warning(small_ranges):
    bad = L.normalize("sales", raw_row("sales", "20262", D1, induty="X1"), "20262", "f", "w")
    assert any(m.startswith("⒣") for m in L.quarter_problems("sales", "20262", [bad], None))
    rep = {"induty_sets": {"20261": frozenset({"CS100001", "CS100002"}), "20262": frozenset({"CS100001"})}}
    warns = L.induty_warnings(rep)
    assert len(warns) == 1 and "20262" in warns[0] and "경고" in warns[0]
    assert L.induty_warnings({"induty_sets": {"20261": frozenset({"A"}), "20262": frozenset({"A"})}}) == []


# ── 4. 분기 파일 고르기 ──────────────────────────────────────────────────────


def test_pick_newest_date_per_quarter_and_skip_pages(tmp_path):
    write_q(tmp_path, "flow", "20262", [raw_row("flow", "20262", D1)], date="20261001")
    newest = write_q(tmp_path, "flow", "20262", [raw_row("flow", "20262", D1)], date="20261031")
    pages = tmp_path / "flow" / "_pages"
    pages.mkdir()
    (pages / "20262_20261231.jsonl").write_text("{}", encoding="utf-8")
    assert L.pick_sources(L.list_raw(str(tmp_path), "flow")) == {"20262": newest}


# ── 5. 값 바뀐 분기 ──────────────────────────────────────────────────────────


def scan_three(tmp_path, service, values, extra_last=False):
    for q, v in zip(("20211", "20212", "20213"), values):
        rows = [raw_row(service, q, D1, v), raw_row(service, q, D2, 5.0)]
        if extra_last and q == "20213":
            rows.append(raw_row(service, q, "3110003", 7.0))
        write_q(tmp_path, service, q, rows)
    return L.scan_service(service, L.pick_sources(L.list_raw(str(tmp_path), service)))


def test_value_quarter_no_change_is_the_first(tmp_path, small_ranges):
    rep = scan_three(tmp_path, "resident", (10.0, 10.0, 10.0))
    assert (rep["max_quarter"], rep["value_quarter"]) == ("20213", "20211")


def test_value_quarter_middle_change(tmp_path, small_ranges):
    rep = scan_three(tmp_path, "worker", (10.0, 11.0, 11.0))
    assert rep["value_quarter"] == "20212" and rep["changes"] == {"20212": 1, "20213": 0}


def test_value_quarter_ignores_districts_on_one_side(tmp_path, small_ranges):
    """⛔ 상권이 하나 새로 들어온 것만으로 '바뀜'이 되지 않는다(10-31 실측 상주 20242 꼴)."""
    rep = scan_three(tmp_path, "resident", (10.0, 11.0, 11.0), extra_last=True)
    assert rep["value_quarter"] == "20212"
    assert L.changed_districts({D1: (1,)}, {D1: (1,), D2: (2,)}) == 0          # 양성 대조 짝 ↓
    assert L.changed_districts({D1: (1,)}, {D1: (2,), D2: (2,)}) == 1


def test_new_district_alone_does_not_move_the_value_quarter(tmp_path, small_ranges):
    """양성 대조 짝 — ① 상권 하나가 마지막 분기에 새로 생기기만 하고 값은 그대로 → 첫 분기 그대로 ·
    ② 같은 자료에서 값 하나만 바꾸면 → 그 분기."""
    rep = scan_three(tmp_path / "a", "resident", (10.0, 10.0, 10.0), extra_last=True)
    assert rep["value_quarter"] == "20211" and rep["changes"] == {"20212": 0, "20213": 0}
    rep = scan_three(tmp_path / "b", "resident", (10.0, 10.0, 12.0), extra_last=True)
    assert rep["value_quarter"] == "20213" and rep["changes"]["20213"] == 1


def test_value_quarter_for_sales_compares_all_industries(tmp_path, small_ranges):
    for q, v in zip(("20211", "20212"), (10.0, 10.0)):
        write_q(tmp_path, "sales", q, [raw_row("sales", q, D1, v), raw_row("sales", q, D1, v, "CS100002")])
    write_q(tmp_path, "sales", "20213", [raw_row("sales", "20213", D1, 10.0),
                                          raw_row("sales", "20213", D1, 99.0, "CS100002")])
    rep = L.scan_service("sales", L.pick_sources(L.list_raw(str(tmp_path), "sales")))
    assert rep["value_quarter"] == "20213" == rep["max_quarter"]


# ── 6. build_sql ─────────────────────────────────────────────────────────────


@pytest.fixture
def sql():
    csv_paths = {s: "D:\\staging\\it's\\{}.csv".format(L.TABLES[s]) for s in L.SERVICES}
    quarters = {"sales": ["20262", "20211"], "flow": ["20211", "20262"],
                "resident": ["20211", "20262"], "worker": ["20211", "20262"]}
    expected = {"sales": 43372, "flow": 3297, "resident": 3260, "worker": 3271}
    release = {"sales": ("20262", "20262"), "flow": ("20262", "20262"),
               "resident": ("20262", "20234"), "worker": ("20262", "20244")}
    return L.build_sql(csv_paths, quarters, expected, release)


def test_sql_is_one_transaction(sql):
    assert sql.startswith("begin;\n") and sql.rstrip().endswith("commit;")
    assert sql.count("begin;") == 1 and sql.count("\ncommit;") == 1


def test_sql_copy_paths_are_literals(sql):
    for s in L.SERVICES:
        assert "\\copy tmp_{} (".format(s) in sql
    assert "from 'D:/staging/it''s/district_sales.csv'" in sql       # 빗금·작은따옴표 처리


def test_sql_induty_gate_raises(sql):
    m = re.search(r"(?s)select count\(\*\) into bad from tmp_sales\s+where svc_induty_cd not in "
                  r"\(select distinct o\.svc_induty_cd from district_openclose o\);\s+if bad <> 0 then\s+raise exception", sql)
    assert m, "관문 ⒤ 가 없습니다"


def test_sql_deletes_only_the_loaded_quarters_then_inserts(sql):
    for s in L.SERVICES:
        t = L.TABLES[s]
        d = sql.index("delete from {} where quarter in ('20211', '20262');".format(t))
        i = sql.index("insert into {} (".format(t))
        assert d < i


def test_sql_release_upsert_and_row_checks(sql):
    assert re.search(r"insert into seoul_trdar_release \(tbl, max_quarter, value_quarter, loaded_at\) values", sql)
    for t, mq, vq in (("district_pop_resident", "20262", "20234"), ("district_pop_worker", "20262", "20244")):
        assert "('{}', '{}', '{}', now())".format(t, mq, vq) in sql
    assert "on conflict (tbl) do update set" in sql
    assert sql.index("insert into seoul_trdar_release") < sql.index("commit;")
    for s, n in (("sales", 43372), ("worker", 3271)):
        assert "if cnt <> {} then".format(n) in sql
        assert "from {} where quarter in".format(L.TABLES[s]) in sql


def test_sql_district_gate_for_every_table(sql):
    for s in L.SERVICES:
        assert "from tmp_{} t\n   where not exists (select 1 from district d".format(s) in sql


# ── 7. main ──────────────────────────────────────────────────────────────────


def fill_all(raw_dir, last_q="20262", last_pop="20262"):
    for s in L.SERVICES:
        for q in all_quarters(last_q if s in ("sales", "flow") else last_pop):
            write_q(raw_dir, s, q, [raw_row(s, q, D1), raw_row(s, q, D2)])


def no_db(monkeypatch):
    import dbx  # noqa: PLC0415

    def boom(*a, **k):
        raise AssertionError("DB 에 쓰려 했습니다")

    monkeypatch.setattr(dbx, "run_sql", boom)
    monkeypatch.setattr(L, "seoul_district_ids", lambda *a, **k: {D1, D2})


def test_dry_run_writes_nothing(tmp_path, monkeypatch, small_ranges, capsys):
    no_db(monkeypatch)
    fill_all(tmp_path / "raw", last_pop="20254")
    rc = L.main(["--dry-run", "--raw-dir", str(tmp_path / "raw"), "--staging-dir", str(tmp_path / "st")])
    assert rc == 0 and not (tmp_path / "st").exists()
    out = capsys.readouterr().out
    assert "관문 통과" in out and "20254" in out
    # F4 — 상주·직장(20254)이 매출(20262)보다 옛 분기라 경고는 서되 멈추지 않는다(rc 0)
    assert "[경고] resident 가 20262보다 옛 분기(20254)까지만" in out
    assert "[경고] worker 가 20262보다 옛 분기(20254)까지만" in out
    # F3 — 관문 ⒤ 는 실적재 트랜잭션 안에서 본다는 한 줄 · dry-run → 마이그 → 실적재 순서
    assert "관문 ⒤" in out and "dry-run 은 못 본다" in out
    assert out.index("dry-run 통과") < out.index("마이그 2026-10-31a 적용") < out.index("실적재 → post_load")


def test_one_service_missing_stops_everything(tmp_path, monkeypatch, small_ranges, capsys):
    no_db(monkeypatch)
    fill_all(tmp_path / "raw")
    for n in os.listdir(tmp_path / "raw" / "worker"):
        os.remove(tmp_path / "raw" / "worker" / n)
    rc = L.main(["--raw-dir", str(tmp_path / "raw"), "--staging-dir", str(tmp_path / "st")])
    assert rc == 1
    assert "worker raw 가 없습니다" in capsys.readouterr().err
    assert not any(n.endswith((".csv", ".part")) for n in os.listdir(tmp_path / "st"))


def test_real_run_builds_sql_with_release(tmp_path, monkeypatch, small_ranges):
    import dbx  # noqa: PLC0415
    monkeypatch.setattr(L, "seoul_district_ids", lambda *a, **k: {D1, D2})
    got = {}
    monkeypatch.setattr(dbx, "run_sql", lambda s: got.setdefault("sql", s) and 0)
    fill_all(tmp_path / "raw")
    rc = L.main(["--raw-dir", str(tmp_path / "raw"), "--staging-dir", str(tmp_path / "st")])
    assert rc == 0
    assert sorted(os.listdir(tmp_path / "st")) == sorted("{}.csv".format(t) for t in L.TABLES.values())
    lines = (tmp_path / "st" / "district_pop_flow.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 44 and lines[0].split(",")[:3] == ["20211", D1, "10"]
    assert "('district_pop_resident', '20262', '20211', now())" in got["sql"]   # 값이 한 번도 안 바뀜 → 첫 분기
