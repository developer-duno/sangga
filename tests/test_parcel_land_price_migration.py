# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-11b(개별공시지가 한 줄 · 물결 1-C1 · 결정 0036 결정 7)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙여 넣기 전에는 아무도 모르는 종류의 실수**다:

  1) 마이그레이션과 정본(schema.sql)의 글자가 갈린다 → 새 환경만 다른 모양으로 만들어진다.
     `create or replace` 는 머리 속성(security definer·search_path·stable)을 새 정의로 덮어쓰는데,
     드리프트 가드는 `$$` 안 본문만 본다 — 그래서 머리·comment 까지 여기서 글자로 대조한다
     (CLAUDE.md ⛔ 2026-10-01a · 본보기 tests/test_data_freshness_migration.py).
  2) 머리 속성 하나가 빠진다 → `set search_path` 가 빠지면 anon 경로가 `relation does not exist` 로 죽고,
     security definer 가 빠지면 닫힌 parcel 을 못 읽어 `permission denied` 다(둘 다 화면에선 줄만 조용히 빠진다).
  3) public 원본에 grant 를 준다 → security definer 원본이 밖에 열린다(🚪 grant 는 api 쌍둥이에만).
  4) 인자를 char(19) 로 받지 않는다 → 기본키 색인이 죽는다(char(19) 함정 — 2026-08-16b).

② 실행 가드(로컬 PostgreSQL 이 있을 때만)는 흉내 판 위에서 두 함수를 실제로 만들고 불러 본다 —
   값 있음 = 한 줄 · 값·연도 null = 0줄 · 없는 필지 = 0줄 · 0원 = 한 줄(0 은 값이다) · api 쌍둥이(search_path '')
   가 public 원본을 찾아 같은 답을 준다. plpgsql 의 반환 칸 이름 충돌(column reference is ambiguous)은
   만들 때가 아니라 **부를 때** 터지므로 이 실행만이 잡는다. CI 에는 PostgreSQL 이 없어 건너뛴다.
"""

import os
import re
import shutil
import socket
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-11b_parcel_land_price.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

FN = "get_parcel_land_price"
API_FN = "api.get_parcel_land_price"
SIG = "(text)"

# 머리 — 정본과 글자 대조와 별도로, 무엇이어야 하는지를 못 박는다.
PUBLIC_HEAD = ("language plpgsql", "stable", "security definer", "set search_path = public")
API_HEAD = ("language sql", "stable", "security definer", "set search_path = ''")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


@pytest.fixture(scope="module")
def mig():
    return read(MIGRATION)


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


def statements(sql):
    """주석 줄을 걷어낸 실제 문장만 — 권한 가드는 이쪽을 본다(주석으로 죽인 문장을 '있다'로 보지 않게)."""
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


def fn_block(sql, name):
    """`create or replace function <name>(` 부터 `$$;` 까지 — 머리 + 본문 통째(줄머리 고정)."""
    m = re.search(r"(?ms)^create\s+or\s+replace\s+function\s+" + re.escape(name)
                  + r"\s*\(.*?\$\$\s*;", sql)
    assert m, "{} 의 정의를 못 찾았습니다 — 정규식이 헛돌면 아래 대조가 통째로 무의미해집니다".format(name)
    return m.group(0)


def fn_comment(sql, name):
    m = re.search(r"(?ms)^comment\s+on\s+function\s+" + re.escape(name) + r"\s*\(.*?';\s*$", sql)
    assert m, "{} 의 comment 를 못 찾았습니다".format(name)
    return m.group(0)


def head_of(block):
    return block[: block.index("$$")]


def body_of(block):
    return block[block.index("$$") + 2: block.rindex("$$")]


def head_problems(block, want):
    """머리에서 빠진 속성 목록(비면 정상). 가드 본체와 양성 대조가 이 같은 함수를 지난다.

    줄 단위로 본다(대소문자·줄 끝 공백 무시) — `stable` 이 `volatile` 로, `set search_path = public` 이
    다른 값으로 바뀐 꼴도 '빠짐'으로 잡힌다.
    ⚠️ 못 보는 것: 한 줄에 여러 속성을 이어 쓴 꼴(`stable security definer`) — 이 레포 정본은 쓰지 않는다
       (그 꼴이 들어오면 정본 대조는 통과해도 여기서 빨강이 난다 — 넓히지 말고 정본을 줄 단위로 맞춘다).
    """
    lines = {ln.strip().lower() for ln in head_of(block).splitlines()}
    return [w for w in want if w not in lines]


def grant_targets(sql):
    """`grant … on function <대상>(` 의 대상 이름 전부(소문자 · 스키마 그대로).

    권한 종류(execute·all)·받는 역할·들여쓰기·줄바꿈·대소문자와 무관하게 본다.
    ⓘ 가드 본체와 양성 대조가 이 **같은 함수**를 지난다(형제 tests/test_industry_floor_migration.py 와 같은 꼴).
    ⚠️ 못 보는 것: 인자 괄호 없는 `on function <이름> to …` · 따옴표 이름 · 일괄 grant(`all functions in schema`).
    """
    found = []
    for stmt in re.findall(r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*?"
                           r"\bon\s+(?:function|routine)\b([^;]*)", statements(sql)):
        found += re.findall(r"(?i)(?<![\w.])((?:\w+\.)?\w+)\s*\(", stmt)
    return [t.lower() for t in found]


def char19_problems(block):
    """인자를 char(19) 로 받아 쓰는지 — 어긋난 까닭 목록(비면 정상). 양성 대조가 같은 함수를 지난다.

    ⚠️ 못 보는 것: 다른 변수 이름으로 받은 꼴(그땐 '받지 않음'으로 빨강 — 넓히지 말고 이름을 맞춘다).
    """
    body = statements(body_of(block))
    out = []
    if not re.search(r"(?m)^\s*v_pnu\s+char\(19\)\s*:=\s*p_pnu\s*;", body):
        out.append("v_pnu char(19) 로 받지 않음")
    if not re.search(r"\bp\.pnu\s*=\s*v_pnu\b", body):
        out.append("p.pnu = v_pnu 로 견주지 않음")
    # 선언 줄 밖에서 p_pnu 를 직접 쓰면 칸 쪽이 text 로 캐스트돼 색인이 죽는다.
    rest = re.sub(r"(?m)^\s*v_pnu\s+char\(19\)\s*:=\s*p_pnu\s*;", "", body)
    if re.search(r"\bp_pnu\b", rest):
        out.append("p_pnu 를 그대로 씀")
    return out


# ── ① 글자 가드 ─────────────────────────────────────────────────────────────


class TestMirrorsTheSchema:
    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_head_and_body_are_the_same_text(self, mig, schema, name):
        assert fn_block(mig, name) == fn_block(schema, name), (
            "{} 가 정본과 글자가 다릅니다 — 새 환경만 다른 모양이 됩니다".format(name))

    def test_comment_is_the_same_text(self, mig, schema):
        assert fn_comment(mig, FN) == fn_comment(schema, FN)

    def test_mirror_detector_sees_a_head_only_change(self, mig, schema):
        """양성 대조 — 본문은 그대로 두고 머리 한 줄만 바꾼 사본이 정본과 어긋난다고 잡힌다."""
        changed = mig.replace("set search_path = public\nas $$", "as $$", 1)
        assert changed != mig
        assert fn_block(changed, FN) != fn_block(schema, FN)

    def test_mirror_detector_sees_a_comment_only_change(self, mig, schema):
        changed = mig.replace("나가는 것은 숫자 두 개뿐이다", "나가는 것은 숫자뿐이다", 1)
        assert changed != mig
        assert fn_comment(changed, FN) != fn_comment(schema, FN)


class TestHeads:
    def test_public_head(self, mig, schema):
        for sql in (mig, schema):
            assert head_problems(fn_block(sql, FN), PUBLIC_HEAD) == []

    def test_api_twin_head_and_body(self, mig, schema):
        for sql in (mig, schema):
            block = fn_block(sql, API_FN)
            assert head_problems(block, API_HEAD) == []
            assert body_of(block).strip() == "select * from public.get_parcel_land_price(p_pnu)"

    @pytest.mark.parametrize("old, new", (
        ("security definer\n", ""),                                   # security definer 빠짐
        ("set search_path = public\n", ""),                           # search_path 빠짐
        ("stable\n", "volatile\n"),                                   # stable → volatile
        ("set search_path = public\n", "set search_path = pg_temp\n"),  # 다른 값
    ))
    def test_head_detector_catches_a_missing_attribute(self, mig, old, new):
        """양성 대조 — 머리 속성 하나를 지우거나 바꾼 public 원본 사본이 걸린다."""
        block = fn_block(mig, FN)
        assert old in head_of(block)
        assert head_problems(block.replace(old, new, 1), PUBLIC_HEAD)

    @pytest.mark.parametrize("old, new", (
        ("security definer\n", ""),
        ("set search_path = ''\n", ""),
        ("stable\n", ""),
    ))
    def test_head_detector_catches_a_missing_attribute_on_the_twin(self, mig, old, new):
        block = fn_block(mig, API_FN)
        assert old in head_of(block)
        assert head_problems(block.replace(old, new, 1), API_HEAD)

    def test_returns_the_two_columns(self, mig):
        """두 함수가 같은 칸 두 개를 같은 형으로 돌려준다(쌍둥이가 다르면 화면 검증기가 응답을 버린다)."""
        want = "returns table (\n  land_price      integer,\n  land_price_year smallint\n)\n"
        for name in (FN, API_FN):
            assert want in head_of(fn_block(mig, name)), name


class TestBody:
    def test_takes_the_pnu_as_char19(self, mig):
        assert char19_problems(fn_block(mig, FN)) == []

    @pytest.mark.parametrize("old, new", (
        ("v_pnu char(19) := p_pnu;", "v_pnu text := p_pnu;"),         # text 로 받음
        ("where p.pnu = v_pnu", "where p.pnu = p_pnu"),                 # 인자를 그대로 씀
    ))
    def test_char19_detector_catches_variants(self, mig, old, new):
        block = fn_block(mig, FN)
        assert old in block
        assert char19_problems(block.replace(old, new, 1))

    def test_nulls_make_no_row(self, mig):
        """값이나 연도가 없으면 줄이 없다 — 0 을 만들어 내지 않는다(화면도 줄을 안 그린다)."""
        body = statements(body_of(fn_block(mig, FN)))
        assert "and p.land_price is not null" in body
        assert "and p.land_price_year is not null" in body
        assert "coalesce" not in body.lower()

    def test_reads_only_parcel(self, mig):
        body = statements(body_of(fn_block(mig, FN)))
        assert re.findall(r"(?i)\bfrom\s+(\w+)", body) == ["parcel"]


class TestPermissions:
    def test_only_the_api_twin_is_granted(self, mig, schema):
        assert grant_targets(mig) == [API_FN]
        assert [t for t in grant_targets(schema) if "land_price" in t] == [API_FN]

    @pytest.mark.parametrize("bad", (
        "grant execute on function get_parcel_land_price(text) to anon;",
        "grant all on function public.get_parcel_land_price(text) to anon;",
        "  GRANT EXECUTE\n  ON FUNCTION Get_Parcel_Land_Price ( text ) TO authenticated;",
    ))
    def test_grant_detector_catches_the_public_original(self, mig, bad):
        """양성 대조 — public 원본에 grant 를 주는 사본이 걸린다(흔한 꼴 + 들여쓴·대문자 변형 꼴)."""
        found = grant_targets(mig + "\n" + bad + "\n")
        assert [t for t in found if t != API_FN], found

    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_every_function_is_revoked_with_anon_named(self, mig, schema, name):
        for sql in (mig, schema):
            assert re.search(r"(?m)^revoke all on function " + re.escape(name + SIG)
                             + r" from public, anon, authenticated;", statements(sql)), name

    def test_revoke_before_grant(self, mig):
        code = statements(mig)
        assert (code.index("revoke all on function api.get_parcel_land_price(")
                < code.index("grant execute on function api.get_parcel_land_price("))

    def test_allowlist_has_the_api_twin_only(self):
        assert API_FN in post_load.ANON_CALLABLE_ALLOWLIST
        assert FN not in post_load.ANON_CALLABLE_ALLOWLIST
        assert "public." + FN not in post_load.ANON_CALLABLE_ALLOWLIST


class TestMigrationShape:
    def test_settings_before_begin_and_notify_after_commit(self, mig):
        code = statements(mig)
        begin = re.search(r"(?m)^begin;", code).start()
        commit = re.search(r"(?m)^commit;", code).start()
        notify = code.index("notify pgrst, 'reload schema';")
        assert code.index("set lock_timeout = ") < begin
        assert code.index("set statement_timeout = ") < begin
        assert begin < commit < notify
        assert len(re.findall(r"(?m)^begin;", code)) == 1 and len(re.findall(r"(?m)^commit;", code)) == 1
        for stmt in re.finditer(r"(?im)^(create|drop|alter|insert|revoke|grant|analyze|comment)\b", code):
            assert begin < stmt.start() < commit, "begin/commit 밖의 문장: " + stmt.group(0)

    def test_only_new_objects(self, mig):
        """기존 객체는 안 건드린다 — drop·alter 0, 만드는 함수는 새 이름 둘뿐."""
        code = statements(mig)
        assert not re.search(r"(?im)^\s*(drop|alter)\s", code)
        made = re.findall(r"(?im)^create\s+(?:or\s+replace\s+)?(\w+(?:\s+view)?)\s+([\w.]+)", code)
        assert made == [("function", FN), ("function", API_FN)]

    def test_rollback_paragraph_is_written(self, mig):
        assert "되돌리기" in mig and "drop function api.get_parcel_land_price(text)" in mig

    def test_no_banned_words(self, mig):
        for w in ("적정가격", "적정가", "감정가", "평가액"):
            assert w not in mig


# ── ② 실행 가드 (로컬 PostgreSQL 이 있을 때만) ──────────────────────────────

SHIM = """
create schema api;
create table parcel (pnu char(19) primary key, land_price integer, land_price_year smallint);
"""

PNU_OK = "1168010100106010000"
PNU_NULL = "1168010100106020000"
PNU_NOYEAR = "1168010100106030000"
PNU_ZERO = "1168010100106040000"
PNU_NONE = "1168010100106050000"

FIXTURE = """
insert into parcel values
  ('{ok}', 59490000, 2026),
  ('{nul}', null, null),
  ('{noyear}', 1000, null),
  ('{zero}', 0, 2025);
""".format(ok=PNU_OK, nul=PNU_NULL, noyear=PNU_NOYEAR, zero=PNU_ZERO)


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    psycopg2 = pytest.importorskip("psycopg2")
    initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
    if not initdb or not pg_ctl:
        pytest.skip("로컬 PostgreSQL(initdb·pg_ctl)이 없다 — CI 는 글자 가드(①)만 본다")
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


@pytest.fixture(scope="module")
def cur(pg):
    """흉내 판 위에 마이그레이션의 두 함수(정본과 같은 글)를 그대로 넣는다."""
    mig = read(MIGRATION)
    c = pg.cursor()
    c.execute("drop schema if exists api cascade; drop schema if exists public cascade; create schema public;")
    c.execute(SHIM)
    c.execute(FIXTURE)
    c.execute(fn_block(mig, FN))
    c.execute(fn_block(mig, API_FN))
    return c


def _rows(cur, fn, pnu):
    cur.execute("select land_price, land_price_year from {}(%s)".format(fn), (pnu,))
    return cur.fetchall()


class TestRealRun:
    @pytest.mark.parametrize("fn", (FN, API_FN))
    def test_value_is_one_row(self, cur, fn):
        assert _rows(cur, fn, PNU_OK) == [(59490000, 2026)]

    @pytest.mark.parametrize("pnu", (PNU_NULL, PNU_NOYEAR, PNU_NONE))
    def test_null_or_missing_is_no_row(self, cur, pnu):
        assert _rows(cur, API_FN, pnu) == []

    def test_zero_is_a_value(self, cur):
        """0 원은 값이다(적재기가 원본 '0' 을 0 으로 담는다) — 걸러 내지 않는다."""
        assert _rows(cur, API_FN, PNU_ZERO) == [(0, 2025)]

    def test_twin_works_with_an_empty_search_path(self, cur):
        """api 쌍둥이는 search_path '' 라 public. 을 붙여 부른다 — 호출자 경로가 비어도 같은 답."""
        cur.execute("set search_path to ''")
        try:
            assert _rows(cur, API_FN, PNU_OK) == [(59490000, 2026)]
        finally:
            cur.execute("reset search_path")

    def test_return_types(self, cur):
        cur.execute("select pg_typeof(land_price)::text, pg_typeof(land_price_year)::text "
                    "from api.get_parcel_land_price(%s)", (PNU_OK,))
        assert cur.fetchone() == ("integer", "smallint")
