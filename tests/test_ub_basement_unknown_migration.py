# -*- coding: utf-8 -*-
"""점포 표 '지하인데 층 모름' 칸 — 마이그레이션 2026-10-14a 의 불변식 (물결 2-2c PR①).

무엇을 막나
-----------
unit_business 는 append-only 라 칸을 틀리게 넣으면 그 분기는 영영 못 고친다. 이 파일은 칸을 만드는 쪽을 본다:
  · 덩어리 꼴 — `set lock_timeout` 이 begin **앞** · 칸 → 제약(NOT VALID) → api 거울 뷰 다시 만들기 → commit →
    VALIDATE → notify. NOT VALID 가 빠지면 ACCESS EXCLUSIVE 안에서 1.5GB 를 훑어 그동안 점포 표 읽기가 전부
    줄을 선다. 뷰를 다시 안 만들면 적재기 upsert 가 새 칸을 못 찾는다(PGRST204).
  · 정본과 글자 대조 — 칸 comment · 제약 식 · api 뷰 줄.
  · 로컬 PostgreSQL 이 있으면 실제로 돌려 본다(없으면 건너뜀 — CI 는 글자 가드만): 칸·제약·뷰가 서고,
    칸 true 인데 floor_no 가 있는 행은 막히고(새 행), 이미 있던 그런 행은 VALIDATE 가 막는다.

ⓘ 탐지는 이 파일 안의 작은 함수로 빼서 가드 본체와 양성 대조가 **같은 함수**를 지난다(CLAUDE.md ⛔).
ⓘ 도우미는 형제 시험(test_transaction_share_migration.py)에서 **복사**해 왔다(import 안 함).
"""

import io
import os
import re
import shutil
import socket
import subprocess
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
MIG = os.path.join(ROOT, "supabase", "migrations", "2026-10-14a_ub_floor_basement_unknown.sql")

COL = "floor_basement_unknown"
CON = "chk_ub_basement_unknown"
VIEW_LINE = "create or replace view api.unit_business    as select * from public.unit_business;"

RE_LINE_COMMENT = re.compile(r"--[^\n]*")


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read().replace("\r\n", "\n")


def code(sql):
    """`--` 주석을 지운다 — 주석 속 글자(설명용)에 걸리면 가드가 거짓말을 한다."""
    return RE_LINE_COMMENT.sub("", sql)


def flat(sql):
    return re.sub(r"\s+", " ", code(sql)).strip()


def stmt_at(pattern, sql):
    """줄머리 pattern 부터 작은따옴표 밖의 첫 `;` 까지(여러 줄 comment 문장도 통째로)."""
    m = re.search(pattern, sql, re.M)
    assert m, pattern
    i, quoted = m.start(), False
    while True:
        c = sql[i]
        if c == "'":
            quoted = not quoted
        elif c == ";" and not quoted:
            return sql[m.start():i + 1]
        i += 1


# ── 탐지 함수 (가드 본체와 양성 대조가 같이 지난다) ─────────────────────────────


def block_order_problems(sql):
    """덩어리 꼴이 어긋난 곳 목록 — 비어 있어야 한다.

    본다: lock_timeout < begin < add column < add constraint(NOT VALID) < api 뷰 다시 만들기 < commit <
          validate < notify · begin/commit 각 하나 · 뷰 뒤에 회수·service_role 권한.
    ⚠️ 못 보는 것: 동적 SQL(`execute '…'`) 안의 문장 · 들여쓴 문장(줄머리 고정).
    """
    src = code(sql)
    problems = []

    def at(pattern):
        m = re.search(pattern, src, re.M | re.I)
        return m.start() if m else None

    marks = [
        ("lock_timeout", at(r"^set\s+(?:session\s+)?lock_timeout\s*(?:=|to)\s*'2s'\s*;")),
        ("begin", at(r"^begin\s*;")),
        ("add column", at(r"^alter\s+table\s+(?:public\.)?unit_business\s+add\s+column\s+(?:if\s+not\s+exists\s+)?"
                          + COL + r"\s+boolean\s*;")),
        ("add constraint not valid", at(
            r"^alter\s+table\s+(?:public\.)?unit_business\s+add\s+constraint\s+" + CON
            + r"\s+check\s*\([^;]*\)\s+not\s+valid\s*;")),
        ("api view", at(r"^create\s+or\s+replace\s+view\s+api\.unit_business\s+as\s+select\s+\*\s+from\s+"
                        r"public\.unit_business\s*;")),
        ("commit", at(r"^commit\s*;")),
        ("validate", at(r"^alter\s+table\s+(?:public\.)?unit_business\s+validate\s+constraint\s+" + CON + r"\s*;")),
        ("notify", at(r"^notify\s+pgrst\s*,\s*'reload schema'\s*;")),
    ]
    for name, pos in marks:
        if pos is None:
            problems.append("없음: " + name)
    seen = [(n, p) for n, p in marks if p is not None]
    for (n1, p1), (n2, p2) in zip(seen, seen[1:]):
        if not p1 < p2:
            problems.append("순서: {} 가 {} 뒤에 있다".format(n1, n2))
    if len(re.findall(r"(?mi)^begin\s*;", src)) != 1 or len(re.findall(r"(?mi)^commit\s*;", src)) != 1:
        problems.append("begin/commit 이 하나씩이 아니다")
    view = dict(marks).get("api view")
    commit = dict(marks).get("commit")
    if view is not None and commit is not None:
        tail = re.sub(r"\s+", " ", src[view:commit])
        if "revoke all on api.unit_business from public, anon, authenticated;" not in tail:
            problems.append("뷰 뒤 회수 없음")
        if "grant select, insert, update, delete on api.unit_business to service_role;" not in tail:
            problems.append("뷰 뒤 service_role 권한 없음")
    if re.search(r"grant\s[^;]*on\s+api\.unit_business\s+to\s[^;]*\b(?:anon|authenticated|public)\b", src, re.I):
        problems.append("api.unit_business 를 공개 롤에 열었다")
    return problems


def check_expr(sql):
    """제약 chk_ub_basement_unknown 의 check 식(공백 접음) — 없으면 None."""
    m = re.search(r"add\s+constraint\s+" + CON + r"\s+check\s*\((.*?)\)\s*(?:not\s+valid\s*)?;",
                  code(sql), re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


# ── 1. 마이그레이션 덩어리 꼴 ───────────────────────────────────────────────────


def test_마이그_덩어리_꼴이_맞다():
    assert block_order_problems(read(MIG)) == []


@pytest.mark.parametrize("old, new, want", [
    ("check (floor_basement_unknown is not true or floor_no is null) not valid;",
     "check (floor_basement_unknown is not true or floor_no is null);", "없음: add constraint not valid"),
    (VIEW_LINE + "\n", "", "없음: api view"),
    ("set lock_timeout = '2s';\n", "", "없음: lock_timeout"),
    ("commit;\n", "", "없음: commit"),
], ids=["not_valid_빠짐", "뷰_재생성_빠짐", "lock_timeout_빠짐", "commit_빠짐"])
def test_돌연변이_덩어리_꼴이_깨지면_잡힌다(old, new, want):
    src = read(MIG)
    assert old in src
    assert want in block_order_problems(src.replace(old, new, 1))


def test_돌연변이_validate_를_덩어리_안으로_넣으면_잡힌다():
    src = read(MIG)
    v = "alter table unit_business validate constraint chk_ub_basement_unknown;\n"
    moved = src.replace(v, "", 1).replace("commit;\n", v + "commit;\n", 1)
    assert any(p.startswith("순서:") for p in block_order_problems(moved))


def test_변형_꼴도_알아본다():
    """양성 대조 변형 — 대문자·`public.` 한정·`set session lock_timeout to` 도 같은 꼴로 본다."""
    src = read(MIG)
    v = (src.replace("set lock_timeout = '2s';", "SET SESSION lock_timeout TO '2s';", 1)
            .replace("alter table unit_business\n  add column", "ALTER TABLE public.unit_business\n  ADD COLUMN", 1))
    assert block_order_problems(v) == []


def test_돌연변이_공개_롤에_열면_잡힌다():
    src = read(MIG).replace("to service_role;", "to service_role, anon;", 1)
    assert "api.unit_business 를 공개 롤에 열었다" in block_order_problems(src)


# ── 2. 정본과 글자 대조 ────────────────────────────────────────────────────────


def test_정본_칸_comment_가_마이그와_글자_일치():
    pat = r"^comment on column unit_business\.floor_basement_unknown is"
    assert stmt_at(pat, read(SCHEMA)) == stmt_at(pat, read(MIG))


def test_정본_제약_식이_마이그와_같다():
    want = "floor_basement_unknown is not true or floor_no is null"
    assert check_expr(read(MIG)) == want
    assert check_expr(read(SCHEMA)) == want


def test_돌연변이_제약_식이_다르면_잡힌다():
    bad = read(SCHEMA).replace("check (floor_basement_unknown is not true or floor_no is null);",
                               "check (floor_basement_unknown or floor_no is null);", 1)
    assert check_expr(bad) != check_expr(read(MIG))


def test_정본에_칸_추가와_api_뷰_줄이_있다():
    s = read(SCHEMA)
    assert re.search(r"(?m)^alter table unit_business\n  add column if not exists floor_basement_unknown boolean;", s)
    assert re.search(r"(?m)^" + re.escape(VIEW_LINE) + "$", s)
    # 칸 추가는 표 정의 **뒤**에(없는 표엔 못 붙인다)
    assert s.index("create table if not exists unit_business (") < s.index(
        "add column if not exists floor_basement_unknown")


# ── 3. 로컬 PostgreSQL 로 실제 실행 (없으면 건너뜀) ────────────────────────────

SHIM = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role; end if;
end $$;
create schema api;
"""


def _old_state(schema_sql):
    """적용 **전** 라이브와 같은 모양 — 정본 표 정의(geom 은 PostGIS 없이 text) + append-only 트리거 + api 뷰."""
    table = stmt_at(r"^create table if not exists unit_business \(", schema_sql)
    table = table.replace("geometry(Point, 4326)", "text")
    trig_fn = stmt_at(r"^create or replace function unit_business_append_only\(\)", schema_sql)
    trig_fn = schema_sql[schema_sql.index(trig_fn):schema_sql.index("$$;", schema_sql.index(trig_fn)) + 3]
    trig = stmt_at(r"^create trigger unit_business_append_only", schema_sql)
    joined = "\n".join([table, trig_fn, trig,
                        "create or replace view api.unit_business as select * from public.unit_business;"])
    assert COL not in joined
    return joined


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    psycopg2 = pytest.importorskip("psycopg2")
    initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
    if not initdb or not pg_ctl:
        pytest.skip("로컬 PostgreSQL(initdb·pg_ctl)이 없다 — CI 는 글자 가드(1~2)만 본다")
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

    def connect(dbname):
        for _ in range(30):
            try:
                c = psycopg2.connect(host="127.0.0.1", port=port, user="postgres", dbname=dbname)
                c.autocommit = True
                return c
            except psycopg2.OperationalError:
                time.sleep(0.5)
        raise AssertionError("로컬 PostgreSQL 에 못 붙었다")

    try:
        yield psycopg2, connect
    finally:
        subprocess.run([pg_ctl, "-D", data, "-m", "fast", "-w", "stop"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)


def _fresh_db(pg, name):
    _psycopg2, connect = pg
    admin = connect("postgres")
    admin.cursor().execute("create database {}".format(name))
    admin.close()
    conn = connect(name)
    c = conn.cursor()
    c.execute(SHIM)
    c.execute(_old_state(read(SCHEMA)))
    return conn, c


INS = ("insert into api.unit_business (snapshot_ym, biz_no, floor_no, {col}) values (%s, %s, %s, %s)")


@pytest.fixture(scope="module")
def applied(pg):
    conn, c = _fresh_db(pg, "applied")
    # 적용 전 옛 분기 행 — 칸이 아직 없다(지하 1층 · 층 모름 · 지상).
    c.execute("insert into unit_business (snapshot_ym, biz_no, floor_no) values "
              "('202606','a',-1), ('202606','b',null), ('202606','c',3)")
    c.execute(read(MIG))   # 마이그레이션 원문 그대로(set · begin … commit · validate · notify)
    yield c
    conn.close()


class TestRealRun:
    def test_칸이_생기고_거울_뷰에도_보인다(self, applied):
        applied.execute("select table_schema, data_type, is_nullable, column_default "
                        "from information_schema.columns where table_name = 'unit_business' "
                        "and column_name = %s order by 1", (COL,))
        assert applied.fetchall() == [("api", "boolean", "YES", None), ("public", "boolean", "YES", None)]

    def test_제약이_검증된_채_선다(self, applied):
        applied.execute("select convalidated from pg_constraint where conname = %s", (CON,))
        assert applied.fetchall() == [(True,)]

    def test_옛_분기_행은_null_그대로다(self, applied):
        applied.execute("select biz_no, floor_no, {} from unit_business order by 1".format(COL))
        assert applied.fetchall() == [("a", -1, None), ("b", None, None), ("c", 3, None)]

    def test_새_행_층_모름_true_는_층이_비어야_들어간다(self, applied, pg):
        psycopg2, _ = pg
        applied.execute(INS.format(col=COL), ("202609", "n1", None, True))
        applied.execute(INS.format(col=COL), ("202609", "n2", -1, False))
        with pytest.raises(psycopg2.errors.CheckViolation):
            applied.execute(INS.format(col=COL), ("202609", "n3", -1, True))

    def test_권한은_service_role_만(self, applied):
        applied.execute("select has_table_privilege('anon', 'api.unit_business', 'select'),"
                        "       has_table_privilege('authenticated', 'api.unit_business', 'select'),"
                        "       has_table_privilege('service_role', 'api.unit_business', 'insert')")
        assert applied.fetchone() == (False, False, True)


def test_이미_있던_어긋난_행은_validate_가_막는다(pg):
    """칸을 먼저 손으로 붙이고 어긋난 행(true + 층 있음)을 넣어 둔 창고 — 덩어리는 들어가도 VALIDATE 에서 멈춘다."""
    psycopg2, _ = pg
    conn, c = _fresh_db(pg, "dirty")
    try:
        c.execute("alter table unit_business add column {} boolean".format(COL))
        c.execute("insert into unit_business (snapshot_ym, biz_no, floor_no, {}) values "
                  "('202609', 'x', -1, true)".format(COL))
        with pytest.raises(psycopg2.errors.CheckViolation):
            c.execute(read(MIG))
        # 덩어리(칸·NOT VALID 제약·뷰)는 이미 commit 됐고, 검증만 안 된 채 남는다 — 머리말 「실행」 ⓘ 와 같다.
        c.execute("select convalidated from pg_constraint where conname = %s", (CON,))
        assert c.fetchall() == [(False,)]
    finally:
        conn.close()
