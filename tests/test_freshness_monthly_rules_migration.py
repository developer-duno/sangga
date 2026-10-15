# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-15a(F3+F5 — 신선도 표 실거래·건축물대장 줄에 월간 규칙)와 그 짝들을 지킨다.

사장님 결정 2026-10-15:
  · 실거래 = 계약월 + 2개월 - 하루(새 규칙 'tx') · cadence '월 1회 (최근 6개월 다시 받기)'
  · 건축물대장 = 기준을 적재일(max(building.updated_at))에서 판 표지(ledger_release.release_ym)로,
    규칙은 인허가와 같은 'permit'(판 + 3개월 - 하루)
  · 판 표지는 사람이 scripts/publish_ledger_release.py --ym 으로 올린다(ⓐ~ⓓ 판정 뒤)
  · 실거래 수집기 --recollect-months N(최근 N개월 done → pending)
  · post_load.py --check 에 대장 표지 점검([사고] = 0줄·못 읽음)

여기서 보는 것:
  1) 마이그레이션 ↔ 정본(schema.sql) 글자 대조 — 함수 머리·본문·comment·revoke 덩어리, 표 덩어리
     (`create or replace` 는 머리 속성을 덮어쓴다 — CLAUDE.md ⛔ "머리와 comment 까지 글자 대조")
  2) 표: RLS · revoke(public·anon·authenticated) · 처음 한 줄 · grant 0
  3) 두 줄의 규칙 — 글자 탐지 + 양성 대조('tx' 를 'none' 으로 되돌리면 잡는다)
  4) 로컬 PostgreSQL 이 있으면 **마이그레이션 파일을 통째로** 흉내 판 위에 돌려 날짜를 단언(CI 는 건너뜀)
  5) 표지 명령 판정 ⓐ~ⓓ(순수 함수 judge — 본체와 같은 함수) · 수집기 되돌릴 칸 · post_load 점검
"""

import datetime
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from decimal import Decimal

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
COLLECTORS = os.path.join(SCRIPTS, "collectors")
for _p in (SCRIPTS, COLLECTORS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import collect_transactions  # noqa: E402
import post_load  # noqa: E402
import publish_ledger_release as plr  # noqa: E402

MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-15a_freshness_monthly_rules.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
FN = "get_data_freshness"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def statements(sql):
    """줄 전체 주석을 걷은 것(줄 구조는 그대로)."""
    return "\n".join(ln for ln in sql.split("\n") if not ln.lstrip().startswith("--"))


def fn_block(sql):
    """`create or replace function get_data_freshness(` 부터 그 함수의 revoke 줄까지(머리·본문·comment·revoke)."""
    m = re.search(r"(?ms)^create\s+or\s+replace\s+function\s+get_data_freshness\s*\(.*?"
                  r"^revoke\s+all\s+on\s+function\s+get_data_freshness\s*\(\)[^\n]*;", sql)
    assert m, "함수 덩어리를 못 찾았습니다"
    return m.group(0)


def fn_body(sql):
    """public 함수의 `$$ … $$` 본문(줄 주석 걷음)."""
    m = re.search(r"(?ms)^create\s+or\s+replace\s+function\s+get_data_freshness\s*\(.*?\$\$(.*?)\$\$;", sql)
    assert m, "본문을 못 찾았습니다"
    return statements(m.group(1))


def table_block(sql):
    """`create table if not exists ledger_release` 부터 처음 한 줄 insert 의 `on conflict (id) do nothing;` 까지."""
    m = re.search(r"(?ms)^create\s+table\s+if\s+not\s+exists\s+ledger_release\b.*?"
                  r"^on\s+conflict\s+\(id\)\s+do\s+nothing;", sql)
    assert m, "ledger_release 덩어리를 못 찾았습니다"
    return m.group(0)


@pytest.fixture(scope="module")
def mig():
    return read(MIGRATION)


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


# ── 1. 정본과 글자 대조 ─────────────────────────────────────────────────────────


class TestMirrorsTheSchema:
    def test_function_block_equals_the_schema(self, mig, schema):
        """머리·본문·comment·revoke 가 정본과 글자 그대로 — 드리프트 가드는 `$$` 안 본문만 본다."""
        assert fn_block(mig) == fn_block(schema)

    def test_head_keeps_the_four_properties(self, mig):
        head = fn_block(mig)
        head = head[: head.index("$$")]
        assert "language sql" in head
        assert re.search(r"(?m)^stable$", head)
        assert "security definer" in head
        assert "set search_path = public" in head

    def test_table_block_equals_the_schema(self, mig, schema):
        assert table_block(mig) == table_block(schema)

    def test_table_comes_before_the_function_in_schema(self, schema):
        """정본을 위에서부터 돌릴 때 sql 함수 본문 검사가 그 표를 찾아야 한다."""
        assert schema.index("create table if not exists ledger_release") < schema.index(
            "create or replace function get_data_freshness()")

    def test_comment_names_the_new_rules(self, mig):
        m = re.search(r"(?ims)^comment\s+on\s+function\s+get_data_freshness\s*\(\s*\)\s+is(.*?);\s*$", mig)
        assert m
        text = m.group(1).replace("'\n  '", "")      # 이어 쓴 문자열 조각을 한 글로
        assert "실거래는 계약월 + 2개월 - 하루" in text
        assert "(인허가 기준월·건축물대장 판)는 기준월 + 3개월 - 하루" in text
        assert "2026-10-15a" in text


# ── 2. 표 ───────────────────────────────────────────────────────────────────────


class TestLedgerReleaseTable:
    @pytest.mark.parametrize("path", (MIGRATION, SCHEMA), ids=("2026-10-15a", "schema"))
    def test_shape(self, path):
        block = statements(table_block(read(path)))
        assert re.search(r"id\s+int\s+primary\s+key\s+default\s+1\s+check\s+\(id\s*=\s*1\)", block)
        assert re.search(r"release_ym\s+char\(6\)\s+not\s+null\s+check\s+\(release_ym\s+~\s+'\^\\d\{6\}\$'\)", block)
        assert re.search(r"loaded_at\s+timestamptz\s+not\s+null\s+default\s+now\(\)", block)

    @pytest.mark.parametrize("path", (MIGRATION, SCHEMA), ids=("2026-10-15a", "schema"))
    def test_rls_and_revoke(self, path):
        code = statements(read(path))
        assert re.search(r"(?im)^alter\s+table\s+ledger_release\s+enable\s+row\s+level\s+security\s*;", code)
        assert re.search(r"(?im)^revoke\s+all\s+on\s+ledger_release\s+from\s+public,\s*anon,\s*authenticated\s*;",
                         code)

    @pytest.mark.parametrize("path", (MIGRATION, SCHEMA), ids=("2026-10-15a", "schema"))
    def test_first_row(self, path):
        block = statements(table_block(read(path)))
        assert re.search(r"values\s+\(1,\s*'202608',\s*'2026-10-14 15:48:00\+09'\)\s*\n\s*on\s+conflict\s+\(id\)"
                         r"\s+do\s+nothing;", block)

    def test_no_grant_anywhere_in_the_migration(self, mig):
        assert not re.search(r"(?im)^\s*grant\s", statements(mig))

    def test_mutation_without_revoke_is_noticed(self, mig):
        """양성 대조 — revoke 줄을 지우면 위 판정 정규식이 못 찾는다."""
        broken = mig.replace("revoke all on ledger_release from public, anon, authenticated;", "", 1)
        assert broken != mig
        assert not re.search(
            r"(?im)^revoke\s+all\s+on\s+ledger_release\s+from\s+public,\s*anon,\s*authenticated\s*;",
            statements(broken))


class TestMigrationShape:
    def test_order(self, mig):
        code = statements(mig)
        lock = re.search(r"(?im)^set\s+lock_timeout\s*=\s*'\d+s'\s*;", code)
        begin = re.search(r"(?im)^begin\s*;", code)
        table = re.search(r"(?im)^create\s+table\s+if\s+not\s+exists\s+ledger_release", code)
        fn = re.search(r"(?im)^create\s+or\s+replace\s+function\s+get_data_freshness\s*\(", code)
        revoke = re.search(r"(?im)^revoke\s+all\s+on\s+function\s+get_data_freshness\s*\(", code)
        commit = re.search(r"(?im)^commit\s*;", code)
        notify = code.find("notify pgrst, 'reload schema';")
        assert all((lock, begin, table, fn, revoke, commit)) and notify != -1
        assert (lock.start() < begin.start() < table.start() < fn.start() < revoke.start()
                < commit.start() < notify)

    def test_only_the_public_function_is_recreated(self, mig):
        """api 쌍둥이는 본문이 그대로라 다시 만들지 않는다 — 만들면 grant 를 다시 줘야 한다."""
        made = re.findall(r"(?im)^create\s+(?:or\s+replace\s+)?function\s+([\w.]+)\s*\(", statements(mig))
        assert made == [FN]

    def test_header_has_how_to_run_and_revert(self, mig):
        assert "python scripts/dbx.py -f supabase/migrations/2026-10-15a_freshness_monthly_rules.sql" in mig
        assert "2026-10-12b_freshness_land_price_year.sql" in mig     # 되돌리기 판
        assert "drop table if exists ledger_release;" in mig


# ── 3. 두 줄의 규칙 (글자) ──────────────────────────────────────────────────────


def row_of(body, ord_no):
    """raw CTE 의 ord_no 번째 줄 `select N, '<src>', '<kind>', (<basis>), '<rule>', '<cadence>'` → dict. 못 찾으면 None."""
    m = re.search(r"(?s)select\s+{},\s*'([^']*)',\s*'([^']*)',\s*\n\s*(\(select .*?\)),\s*\n\s*'(\w+)',\s*\n\s*"
                  r"'([^']*)'".format(ord_no), body)
    if not m:
        return None
    return {"src": m.group(1), "kind": m.group(2), "basis": m.group(3), "rule": m.group(4), "cadence": m.group(5)}


TX_BRANCH = re.compile(
    r"when\s+n\.rule_kind\s*=\s*'tx'\s+and\s+n\.basis\s*~\s*'(?P<re>[^']*)'\s*\n"
    r"\s*then\s+\(to_date\(n\.basis,\s*'YYYYMM'\)\s*\+\s*interval\s+'(?P<months>\d+) months'\s*-\s*"
    r"interval\s+'1 day'\)::date")
PERMIT_BRANCH = re.compile(
    r"when\s+n\.rule_kind\s*=\s*'permit'\s+and\s+n\.basis\s*~\s*'(?P<re>[^']*)'\s*\n"
    r"\s*then\s+\(to_date\(n\.basis,\s*'YYYYMM'\)\s*\+\s*interval\s+'(?P<months>\d+) months'\s*-\s*"
    r"interval\s+'1 day'\)::date")
YM_SHAPE = r"^\d{4}(0[1-9]|1[0-2])$"


def branch(body, pat):
    """(정규식, 더하는 달 수) — 갈래가 없거나 꼴이 다르면 None."""
    m = pat.search(body)
    return (m.group("re"), int(m.group("months"))) if m else None


def tx_problems(body):
    """실거래 줄이 'tx' 규칙(계약월 + 2개월 - 하루)을 쓰는가 — 가드 본체와 양성 대조가 같은 함수를 지난다.

    못 보는 것: 별칭이 n 이 아닌 꼴 · to_date 를 다른 함수로 바꾼 꼴(그건 실제 실행 시험이 본다).
    """
    bad = []
    row = row_of(body, 2)
    if row is None:
        bad.append("2번 줄을 못 찾았습니다")
    else:
        if row["rule"] != "tx":
            bad.append("실거래 줄 규칙이 'tx' 가 아닙니다: {}".format(row["rule"]))
        if row["cadence"] != "월 1회 (최근 6개월 다시 받기)":
            bad.append("실거래 cadence 가 다릅니다: {}".format(row["cadence"]))
    if branch(body, TX_BRANCH) != (YM_SHAPE, 2):
        bad.append("'tx' 갈래가 '여섯 자리 YYYYMM 일 때만 + 2개월 - 하루' 가 아닙니다")
    return bad


@pytest.mark.parametrize("path", (MIGRATION, SCHEMA), ids=("2026-10-15a", "schema"))
class TestTheTwoRows:
    def test_tx_row(self, path):
        body = fn_body(read(path))
        assert tx_problems(body) == []
        row = row_of(body, 2)
        assert (row["src"], row["kind"], row["basis"]) == (
            "실거래 (매매)", "계약월", "(select max(t.contract_ym)::text from transaction t)")

    def test_ledger_row(self, path):
        body = fn_body(read(path))
        row = row_of(body, 3)
        assert row == {"src": "건축물대장", "kind": "판",
                       "basis": "(select r.release_ym::text from ledger_release r)",
                       "rule": "permit", "cadence": "월간 파일 (사람이 적재)"}

    def test_ledger_row_no_longer_reads_building(self, path):
        body = fn_body(read(path))
        assert "from building" not in body

    def test_permit_branch_unchanged(self, path):
        assert branch(fn_body(read(path)), PERMIT_BRANCH) == (YM_SHAPE, 3)

    def test_eleven_rows(self, path):
        assert fn_body(read(path)).count("union all") == 10


class TestTxDetectorCatches:
    """양성 대조 — 같은 탐지 함수에 망가뜨린 본문을 넣으면 잡는다."""

    @pytest.fixture
    def body(self):
        return fn_body(read(SCHEMA))

    def test_tx_reverted_to_none(self, body):
        broken = body.replace("           'tx',\n", "           'none',\n", 1)
        assert broken != body
        assert any("'tx' 가 아닙니다" in m for m in tx_problems(broken))

    def test_branch_removed(self, body):
        broken = TX_BRANCH.sub("", body, count=1)
        assert broken != body
        assert any("갈래" in m for m in tx_problems(broken))

    @pytest.mark.parametrize("old,new", [
        ("interval '2 months' - interval '1 day'", "interval '3 months' - interval '1 day'"),
        ("when n.rule_kind = 'tx' and n.basis ~ '^\\d{4}(0[1-9]|1[0-2])$'",
         "when n.rule_kind = 'tx' and n.basis ~ '\\d{6}'"),
    ])
    def test_branch_changed(self, body, old, new):
        assert old in body, "전제: 그 글자가 지금 판에 있다"
        assert tx_problems(body.replace(old, new, 1))


def _add_months_minus_day(ym, months):
    """파이썬으로 따라 셈 — to_date(ym) + N개월 - 하루."""
    y, m = int(ym[:4]), int(ym[4:]) + months
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    return datetime.date(y, m, 1) - datetime.timedelta(days=1)


@pytest.mark.parametrize("ym,months,expected", [
    ("202610", 2, "2026-11-30"), ("202612", 2, "2027-01-31"), ("202601", 2, "2026-02-28"),
    ("202801", 2, "2028-02-29"), ("202608", 3, "2026-10-31"), ("202611", 3, "2027-01-31"),
])
def test_examples_follow_the_schema_numbers(ym, months, expected):
    """정본의 갈래 숫자(2·3)를 읽어 예시 날짜를 셈한다 — 결정 문장 ↔ 예시 맞대기."""
    body = fn_body(read(SCHEMA))
    n = branch(body, TX_BRANCH if months == 2 else PERMIT_BRANCH)[1]
    assert str(_add_months_minus_day(ym, n)) == expected


# ── 4. 로컬 PostgreSQL — 마이그레이션 파일을 통째로 돌린다 ──────────────────────

SHIM = """
create role anon;
create role authenticated;
create table snapshot_release (published_ym text);
create table transaction (contract_ym text);
create table building (updated_at timestamptz);
create table district (computed_at timestamptz);
create table lh_notice (collected_at timestamptz);
create table arch_permit (loaded_ym text);
create table nts_base_price (notice_date date);
create table rent_stat (quarter char(6));
create table price_gate_sigungu (loaded_at timestamptz);
create table parcel (pnu char(19) primary key, land_price_year smallint);
create table district_openclose (quarter text);
create table basis_override (v text);
"""
LEDGER_BASIS = "(select r.release_ym::text from ledger_release r)"


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    psycopg2 = pytest.importorskip("psycopg2")
    initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
    if not initdb or not pg_ctl:
        pytest.skip("로컬 PostgreSQL(initdb·pg_ctl)이 없다 — CI 는 글자 가드만 본다")
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


def _fresh(conn, migration_sql):
    """흉내 판을 새로 깔고 마이그레이션 글을 **통째로** 돌린다(begin/commit·notify 포함)."""
    cur = conn.cursor()
    cur.execute("drop schema if exists public cascade; create schema public;")
    cur.execute("drop role if exists anon; drop role if exists authenticated;")
    cur.execute(SHIM)
    cur.execute(migration_sql)
    return cur


def _rows(cur):
    cur.execute("select src, basis_kind, basis, next_expected::text, cadence from get_data_freshness()")
    rows = cur.fetchall()
    assert len(rows) == 11, len(rows)
    return {r[0]: r[1:] for r in rows}


class TestRealRun:
    def test_first_row_and_ledger_date(self, pg):
        cur = _fresh(pg, read(MIGRATION))
        cur.execute("select id, release_ym, loaded_at at time zone 'UTC' from ledger_release")
        assert [(i, y, str(t)) for i, y, t in cur.fetchall()] == [(1, "202608", "2026-10-14 06:48:00")]
        assert _rows(cur)["건축물대장"] == ("판", "202608", "2026-10-31", "월간 파일 (사람이 적재)")

    def test_rerun_keeps_the_existing_flag(self, pg):
        """정본·마이그레이션을 다시 돌려도 지금 표지를 되돌리지 않는다(on conflict do nothing)."""
        cur = _fresh(pg, read(MIGRATION))
        cur.execute("update ledger_release set release_ym = '202611'")
        cur.execute(read(MIGRATION))
        assert _rows(cur)["건축물대장"][1:3] == ("202611", "2027-01-31")

    def test_anon_cannot_read_the_table(self, pg):
        cur = _fresh(pg, read(MIGRATION))
        cur.execute("select has_table_privilege('anon', 'ledger_release', 'select'), "
                    "has_table_privilege('authenticated', 'ledger_release', 'select'), "
                    "(select relrowsecurity from pg_class where relname = 'ledger_release')")
        assert cur.fetchone() == (False, False, True)

    @pytest.mark.parametrize("contract_ym,expected", [
        ("202610", "2026-11-30"), ("202612", "2027-01-31"), ("202601", "2026-02-28"), ("202801", "2028-02-29"),
    ])
    def test_tx_dates(self, pg, contract_ym, expected):
        cur = _fresh(pg, read(MIGRATION))
        cur.execute("insert into transaction values (%s), ('200601')", (contract_ym,))
        assert _rows(cur)["실거래 (매매)"] == ("계약월", contract_ym, expected, "월 1회 (최근 6개월 다시 받기)")

    @pytest.mark.parametrize("bad", ["2026-10", "20261", "202613", "202600"])
    def test_tx_bad_shape_gives_null(self, pg, bad):
        cur = _fresh(pg, read(MIGRATION))
        cur.execute("insert into transaction values (%s)", (bad,))
        assert _rows(cur)["실거래 (매매)"][1:3] == (bad, None)

    def test_tx_no_rows_keeps_the_row(self, pg):
        cur = _fresh(pg, read(MIGRATION))
        assert _rows(cur)["실거래 (매매)"][:3] == ("계약월", None, None)

    def test_empty_ledger_keeps_the_row(self, pg):
        cur = _fresh(pg, read(MIGRATION))
        cur.execute("delete from ledger_release")
        assert _rows(cur)["건축물대장"][:3] == ("판", None, None)

    @pytest.mark.parametrize("v,expected", [("202611", "2027-01-31"), ("2026-10", None), ("20261", None),
                                            (None, None)])
    def test_ledger_shapes_via_override(self, pg, v, expected):
        """표의 check 가 막는 모양은 basis 자리를 흉내 표로 바꿔 넣어 본다(양성 대조 포함 — '202611')."""
        sql = read(MIGRATION)
        assert sql.count(LEDGER_BASIS) == 1
        cur = _fresh(pg, sql.replace(LEDGER_BASIS, "(select v from basis_override)", 1))
        cur.execute("insert into basis_override values (%s)", (v,))
        assert _rows(cur)["건축물대장"][1:3] == (v, expected)

    def test_schema_function_gives_the_same_dates(self, pg):
        """정본의 함수 덩어리로 바꿔 만들어도 같은 날짜(글자 대조와 별개로 실제 실행)."""
        cur = _fresh(pg, read(MIGRATION))
        cur.execute(fn_block(read(SCHEMA)))
        cur.execute("insert into transaction values ('202610')")
        rows = _rows(cur)
        assert rows["실거래 (매매)"][2] == "2026-11-30"
        assert rows["건축물대장"][2] == "2026-10-31"

    @pytest.mark.parametrize("old,new", [
        ("interval '2 months' - interval '1 day'", "interval '3 months' - interval '1 day'"),
        ("           'tx',\n", "           'none',\n"),
    ])
    def test_mutation_is_noticed(self, pg, old, new):
        sql = read(MIGRATION)
        assert old in sql
        cur = _fresh(pg, sql.replace(old, new, 1))
        cur.execute("insert into transaction values ('202610')")
        assert _rows(cur)["실거래 (매매)"][2] != "2026-11-30"


# ── 5-1. 표지 명령 publish_ledger_release ───────────────────────────────────────

LOADED = Decimal("1760424480")           # 2026-10-14 15:48 KST
FLAG = ("202608", LOADED, "2026-10-14 15:48")


def gu(*pairs):
    return [(c, None if e is None else Decimal(e), "") for c, e in pairs]


ALL_AFTER = gu(("11110", "1760500000"), ("11680", "1760424480.5"), ("30110", "1761000000"))


class TestJudge:
    @pytest.mark.parametrize("ym", ["20260", "2026-09", "202613", "202600", "", None, "abcdef", "2026090"])
    def test_a_shape(self, ym):
        code, lines, write = plr.judge(ym, FLAG, "202610", ALL_AFTER)
        assert (code, write) == (2, False) and "ⓐ" in lines[0]

    def test_empty_flag(self):
        assert plr.judge("202609", None, "202610", ALL_AFTER)[::2] == (1, False)

    def test_b_older_is_refused(self):
        code, lines, write = plr.judge("202607", FLAG, "202610", ALL_AFTER)
        assert (code, write) == (1, False) and "ⓑ" in lines[0]

    def test_b_same_is_a_noop(self):
        """지금 운영에 --ym 202608 → 같은 판이라 쓰기 0 · exit 0(구 판정까지 가지 않는다)."""
        code, lines, write = plr.judge("202608", FLAG, "202610", gu(("11110", None)))
        assert (code, write) == (0, False) and "바꿀 것 없음" in lines[0]

    @pytest.mark.parametrize("ym", ["202610", "202611"])
    def test_c_this_month_or_later_is_refused(self, ym):
        code, lines, write = plr.judge(ym, FLAG, "202610", ALL_AFTER)
        assert (code, write) == (1, False) and "ⓒ" in lines[0]

    def test_d_all_after_passes(self):
        code, lines, write = plr.judge("202609", FLAG, "202610", ALL_AFTER)
        assert (code, write) == (0, True)

    @pytest.mark.parametrize("rows,missing", [
        (gu(("11110", "1760500000"), ("11680", "1760424480")), "11680"),       # 같은 시각 = 안 됨
        (gu(("11110", "1760500000"), ("11680", "1760000000")), "11680"),       # 표지 전
        (gu(("11110", "1760500000"), ("30110", None)), "30110"),               # 건물 없음
    ])
    def test_d_missing_gu_is_refused_and_named(self, rows, missing):
        code, lines, write = plr.judge("202609", FLAG, "202610", rows)
        assert (code, write) == (1, False)
        assert "ⓓ" in lines[0] and missing in lines[0]

    def test_d_empty_gu_list_is_refused(self):
        assert plr.judge("202609", FLAG, "202610", [])[::2] == (1, False)

    def test_not_loaded_gu_positive_control(self):
        rows = gu(("a", "2"), ("b", "1"), ("c", None), ("d", "1.000001"))
        assert plr.not_loaded_gu(rows, Decimal("1")) == ["b", "c"]


class TestPublishParsing:
    def test_parse_flag(self):
        assert plr.parse_flag("202608;1760424480.000000;2026-10-14 15:48") == (
            "202608", Decimal("1760424480.000000"), "2026-10-14 15:48")
        assert plr.parse_flag("") is None
        assert plr.parse_flag("2026;1;x") is None

    def test_parse_gu_rows(self):
        assert plr.parse_gu_rows("11110;1760500000.5;2026-10-15 10:00,30110;;") == [
            ("11110", Decimal("1760500000.5"), "2026-10-15 10:00"), ("30110", None, "")]

    @pytest.mark.parametrize("argv,expected", [
        (["--show"], {"mode": "show"}),
        (["--ym", "202609"], {"mode": "ym", "ym": "202609", "dry_run": False}),
        (["--ym", "202609", "--dry-run"], {"mode": "ym", "ym": "202609", "dry_run": True}),
        (["--dry-run", "--ym=202609"], {"mode": "ym", "ym": "202609", "dry_run": True}),
    ])
    def test_parse_args_ok(self, argv, expected):
        assert plr.parse_args(argv) == expected

    @pytest.mark.parametrize("argv", [[], ["--ym"], ["--help"], ["--ym", "202609", "--x"], ["--show", "--dry-run"]])
    def test_parse_args_rejects(self, argv):
        with pytest.raises(ValueError):
            plr.parse_args(argv)

    def test_sql_sent_through_psql_c_is_ascii(self):
        for sql in (plr.FLAG_SQL, plr.GU_SQL, plr.build_update_sql("202609"), post_load.LEDGER_RELEASE_SQL):
            assert {c for c in sql if ord(c) > 127} == set(), sql[:60]

    def test_update_sql_is_forward_only(self):
        sql = plr.build_update_sql("202609")
        assert "where id = 1 and release_ym < '202609'" in sql
        with pytest.raises(ValueError):
            plr.build_update_sql("2026-09")

    def test_kst_this_month(self):
        utc = datetime.datetime(2026, 10, 31, 16, 0, tzinfo=datetime.timezone.utc)   # 한국 11월 1일 01시
        assert plr.kst_this_month(utc) == "202611"


class TestPublishMain:
    def _fake(self, monkeypatch, gu_text="11110;1760500000;x,11680;1760500001;y", update_answer="1"):
        sent = []

        def fake(sql):
            sent.append(sql)
            if sql == plr.FLAG_SQL:
                return "202608;1760424480.000000;2026-10-14 15:48"
            if sql == plr.GU_SQL:
                return gu_text
            if sql.startswith("with u as (update ledger_release"):
                return update_answer
            raise AssertionError(sql)

        monkeypatch.setattr(plr, "query_one", fake)
        monkeypatch.setattr(plr, "kst_this_month", lambda now=None: "202610")
        return sent

    def _updates(self, sent):
        return [s for s in sent if re.search(r"\bupdate\s+ledger_release\b", s)]

    def test_same_release_is_a_noop(self, monkeypatch):
        sent = self._fake(monkeypatch)
        assert plr.main(["--ym", "202608"]) == 0
        assert self._updates(sent) == []

    def test_older_is_refused(self, monkeypatch):
        sent = self._fake(monkeypatch)
        assert plr.main(["--ym", "202607"]) == 1
        assert self._updates(sent) == []

    def test_dry_run_writes_nothing(self, monkeypatch, capsys):
        sent = self._fake(monkeypatch)
        assert plr.main(["--ym", "202609", "--dry-run"]) == 0
        assert self._updates(sent) == []
        assert "쓰기 0" in capsys.readouterr().out

    def test_publish_sends_one_update(self, monkeypatch):
        sent = self._fake(monkeypatch)
        assert plr.main(["--ym", "202609"]) == 0
        assert self._updates(sent) == [plr.build_update_sql("202609")]

    def test_half_loaded_is_refused(self, monkeypatch, capsys):
        sent = self._fake(monkeypatch, gu_text="11110;1760500000;x,11680;1760000000;y")
        assert plr.main(["--ym", "202609"]) == 1
        assert self._updates(sent) == []
        assert "11680" in capsys.readouterr().out

    def test_update_that_changed_nothing_is_a_failure(self, monkeypatch):
        self._fake(monkeypatch, update_answer="0")
        assert plr.main(["--ym", "202609"]) == 1


# ── 5-2. 실거래 수집기 --recollect-months ──────────────────────────────────────


class TestRecollectPlan:
    ROWS = [{"period_key": "202605", "status": "done"}, {"period_key": "202606", "status": "failed"},
            {"period_key": "202607", "status": "pending"}, {"period_key": "202608", "status": "done"},
            {"period_key": "202609", "status": "skipped"}, {"period_key": "202604", "status": "done"}]

    def test_months_and_revert(self):
        months, revert = collect_transactions.recollect_plan("202610", 6, self.ROWS)
        assert months == ["202605", "202606", "202607", "202608", "202609", "202610"]
        assert revert == ["202605", "202608"]       # done 만 · 범위 밖 202604 는 안 건드린다

    @pytest.mark.parametrize("n", [0, 25, -1])
    def test_out_of_range(self, n):
        with pytest.raises(ValueError):
            collect_transactions.recollect_plan("202610", n, [])

    def test_revert_rows_leave_attempts_alone(self):
        rows = collect_transactions.build_revert_rows("11680", ["202605"])
        assert rows == [{"collector": collect_transactions.COLLECTOR, "scope_key": "11680",
                         "period_key": "202605", "status": "pending", "error_msg": None}]
        assert "attempts" not in rows[0]

    @pytest.mark.parametrize("v", ["0", "25"])
    def test_parse_args_rejects_out_of_range(self, v):
        with pytest.raises(ValueError):
            collect_transactions.parse_args(["--recollect-months", v])

    def test_parse_args_accepts(self):
        opts = collect_transactions.parse_args(["--recollect-months", "6", "--end-ym", "202610"])
        assert opts["recollect_months"] == 6
        assert collect_transactions.parse_args([])["recollect_months"] is None


class TestRecollectMain:
    def _stub(self, monkeypatch, argv):
        log = {"seed": [], "upsert": []}
        t = collect_transactions
        monkeypatch.setattr(t, "get_supabase_config", lambda: ("https://x.supabase.co", "k"))
        monkeypatch.setattr(t, "get_api_key", lambda: "APIKEY")
        monkeypatch.setattr(t, "seed_progress", lambda b, h, s, months: log["seed"].append(list(months)))
        monkeypatch.setattr(t, "fetch_progress_rows", lambda *a: TestRecollectPlan.ROWS)
        monkeypatch.setattr(t, "upsert_batch", lambda b, h, table, rows, res, **kw: log["upsert"].append(
            (table, rows, res)))
        monkeypatch.setattr(t, "fetch_pending", lambda *a, **kw: [])
        monkeypatch.setattr(t, "progress_status_counts", lambda *a, **kw: t.Counter())
        monkeypatch.setattr(t, "read_quota_baseline", lambda *a, **kw: 0)
        monkeypatch.setattr(sys, "argv", ["prog"] + argv)
        return log

    def test_dry_run_reverts_nothing(self, monkeypatch, capsys):
        log = self._stub(monkeypatch, ["--months", "6", "--end-ym", "202610", "--recollect-months", "6",
                                       "--dry-run"])
        assert collect_transactions.main() == 0
        assert log["upsert"] == []
        assert len(log["seed"]) == 1            # 기존 시드 한 번뿐 — 다시 받을 달 시드는 안 한다
        assert "다시 받을 달 6개(그중 done 2개)" in capsys.readouterr().out

    def test_run_reverts_done_months(self, monkeypatch):
        log = self._stub(monkeypatch, ["--months", "6", "--end-ym", "202610", "--recollect-months", "6"])
        assert collect_transactions.main() == 0
        assert log["seed"][-1] == ["202605", "202606", "202607", "202608", "202609", "202610"]
        assert log["upsert"] == [("collect_progress",
                                  collect_transactions.build_revert_rows("11680", ["202605", "202608"]),
                                  "merge-duplicates")]

    def test_without_option_nothing_changes(self, monkeypatch):
        log = self._stub(monkeypatch, ["--months", "6", "--end-ym", "202610"])
        assert collect_transactions.main() == 0
        assert log["upsert"] == [] and len(log["seed"]) == 1


# ── 5-3. post_load --check 의 대장 표지 점검 ───────────────────────────────────


class TestPostLoadLedgerCheck:
    def test_judge(self):
        assert post_load.judge_ledger_release("", "")[0][0] == "사고"
        assert post_load.judge_ledger_release("202608", "2026-10-14 15:48") == []

    @pytest.mark.parametrize("answer,fatal,needle", [
        ("", True, "[사고] 대장 표지(ledger_release)가 비었습니다"),
        ("202608|2026-10-14 15:48", False, "[정상] 대장 표지 — 판 202608 (적은 시각 2026-10-14 15:48)"),
    ])
    def test_report(self, monkeypatch, capsys, answer, fatal, needle):
        monkeypatch.setattr(post_load, "query_one", lambda sql: answer)
        assert post_load.report_ledger_release() is fatal
        assert needle in capsys.readouterr().out

    def test_unreadable_is_an_incident(self, monkeypatch, capsys):
        def boom(sql):
            raise RuntimeError('relation "ledger_release" does not exist')
        monkeypatch.setattr(post_load, "query_one", boom)
        assert post_load.report_ledger_release() is True
        assert "[사고] 대장 표지(ledger_release)를 읽지 못했습니다" in capsys.readouterr().out

    QUIET = {
        "report_freshness": lambda: ("1", "1", False),
        "report_map_freshness": lambda: ({}, False),
        "report_tx_window_freshness": lambda: ("", "", False),
        "report_coverage_freshness": lambda: ("", "", False),
        "report_industry_mix_freshness": lambda: ("", "", False),
        "report_store_names_freshness": lambda: ("", "", False),
        "report_industry_floor_freshness": lambda: ("", "", False),
        "report_industry_floor_consistency": lambda: ("0", False),
        "report_industry_median_freshness": lambda: ("", "", False),
        "report_industry_median_consistency": lambda: ("0", False),
        "report_industry_median_m_freshness": lambda: ("", "", False),
        "report_industry_median_m_consistency": lambda: ("0", False),
        "report_tx_geog_freshness": lambda: ("1", "1", False),
        "report_anon_exposure": lambda: ([], []),
        "report_write_exposure": lambda: [],
        "report_slow_functions": lambda: [],
        "report_toast_evictions": lambda: [],
        "report_canonical_indexes": lambda: [],
        "report_function_drift": lambda: [],
        "report_snapshot_release": lambda *a: (False, False),
    }

    @pytest.mark.parametrize("fatal,code", [(True, 1), (False, 0)])
    def test_check_exit_code_follows_the_ledger(self, monkeypatch, fatal, code):
        for name, fn in self.QUIET.items():
            assert hasattr(post_load, name), name
            monkeypatch.setattr(post_load, name, fn)
        monkeypatch.setattr(post_load, "report_ledger_release", lambda: fatal)
        assert post_load.main(["--check"]) == code

    @pytest.mark.parametrize("answer,code,needle", [
        ("", 1, "[사고] 대장 표지(ledger_release)가 비었습니다"),
        ("202608|2026-10-14 15:48", 0, "[정상] 대장 표지 — 판 202608"),
    ])
    def test_real_report_is_wired_into_check(self, monkeypatch, capsys, answer, code, needle):
        """stub 을 풀고 **진짜** report_ledger_release + 가짜 query_one 으로 --check 를 돈다.

        다른 시험 파일들은 autouse·목록으로 report_ledger_release 를 늘 stub 하므로, main 에서 그 호출 줄이
        지워져도 거기선 아무것도 안 걸린다 — 이 시험이 그 배선을 지킨다.
        """
        for name, fn in self.QUIET.items():
            monkeypatch.setattr(post_load, name, fn)
        asked = []

        def fake_query_one(sql):
            asked.append(sql)
            assert sql == post_load.LEDGER_RELEASE_SQL, sql[:80]
            return answer

        monkeypatch.setattr(post_load, "query_one", fake_query_one)
        assert post_load.main(["--check"]) == code
        assert asked == [post_load.LEDGER_RELEASE_SQL]
        assert needle in capsys.readouterr().out

    def test_refresh_flow_does_not_read_the_ledger(self):
        """표지 점검은 --check 에서만 — 갱신 흐름(쓰기)의 몸통에는 없다."""
        src = read(os.path.join(SCRIPTS, "post_load.py"))
        main_src = src[src.index("def main(argv=None):"):]
        check_part, refresh_part = main_src.split("# ① 표지부터 읽는다", 1)
        assert "report_ledger_release()" in check_part
        assert "report_ledger_release" not in refresh_part
