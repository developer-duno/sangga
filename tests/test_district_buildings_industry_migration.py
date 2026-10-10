# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-11a(지도 상권 목록 업종 기준 · 물결 2-2b · 결정 0036 결정 18 ⑨·㉒)의 불변식.

여기서 막는 것 — 전부 **에러 없이** 틀리는 종류다:
  1) 칩 '전체'(인자 null)의 결과가 옛 함수와 갈린다 → 칩을 안 고른 모든 손님의 상권 목록이 조용히 바뀐다.
     ① 글자 가드: 옛 본문(2026-10-07a)과 새 본문을 줄 단위로 견줘, 지워진 줄이 정확히 바꾸기로 한 셋
        (점포 세기 머리·정렬 둘)뿐이고 새로 든 코드 줄이 전부 업종 인자(p_cat_m·cat_n·cat_store_cnt)
        에 묶여 있는지 본다 · ② 실행 가드(로컬 PostgreSQL 이 있을 때만): 옛·새 함수를 같은 흉내 판에
        돌려 행·순서·칸 값을 견준다.
  2) 머리(security definer·search_path·stable)·comment 가 정본과 갈린다 → `create or replace` 가 라이브
     속성을 조용히 바꾼다(CLAUDE.md ⛔ 2026-10-01a).
  3) public 원본에 grant 를 준다 → security definer 원본이 밖에 열린다(🚪 grant 는 api 쌍둥이에만).
  4) 옛 3-인자 함수를 안 지운다 → 같은 이름의 함수 둘(오버로드)이 남는다 · 지우기와 다시 만들기가
     begin/commit 밖으로 샌다 → 중간에 끊기면 상권 목록 함수가 없는 채로 남는다.
  5) 분기를 표지 published 가 아닌 것으로 읽는다(결정 0035 — 실시간 함수).

ⓘ 도우미는 이 파일 안에서만 쓴다(시험 파일끼리 import 하지 않는 레포 관습).
⚠️ CI 에는 PostgreSQL 이 없어 ② 실행 가드는 건너뛴다(형제 tests/test_industry_floor_migration.py 와 같은 꼴).
"""

import difflib
import os
import re
import shutil
import socket
import subprocess
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIG_DIR = os.path.join(ROOT, "supabase", "migrations")
MIGRATION = os.path.join(MIG_DIR, "2026-10-11a_district_buildings_industry.sql")
# 이 함수를 바로 앞에서 다시 만든 판(표지 published) — 옛 정의의 정본이다.
PREVIOUS = os.path.join(MIG_DIR, "2026-10-07a_snapshot_release.sql")
SIBLING = os.path.join(MIG_DIR, "2026-10-09b_industry_floor.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

FN = "list_district_buildings"
API_FN = "api.list_district_buildings"
NEW_SIG = "(text, int, int, text[])"
OLD_SIG = "(text, int, int)"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


@pytest.fixture(scope="module")
def mig():
    return read(MIGRATION)


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


@pytest.fixture(scope="module")
def prev():
    return read(PREVIOUS)


def statements(sql):
    """주석 줄을 걷어낸 실제 문장만(주석으로 죽인 문장을 '있다'로 보지 않게)."""
    return "\n".join(ln for ln in sql.split("\n") if not ln.lstrip().startswith("--"))


def fn_block(sql, name):
    """`create or replace function <name>(` 부터 `$$;` 까지(줄머리 고정 — public 이름은 api 쌍둥이를 안 집는다)."""
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


def grant_targets(sql):
    """`grant … on function <대상>(` 의 대상 이름 전부(소문자 · 스키마 그대로).

    ⓘ 가드 본체와 양성 대조가 이 **같은 함수**를 지난다(형제 test_industry_floor_migration.py 에서 복사).
    ⚠️ 못 보는 것: 인자 괄호 없는 `on function <이름> to …` · 따옴표 이름 · 일괄 grant(`all functions in schema`).
    """
    found = []
    for stmt in re.findall(r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*?"
                           r"\bon\s+(?:function|routine)\b([^;]*)", statements(sql)):
        found += re.findall(r"(?i)(?<![\w.])((?:\w+\.)?\w+)\s*\(", stmt)
    return [t.lower() for t in found]


RE_RELEASE_COL = re.compile(
    r"(?i)\br\.(loaded|published)_ym(?:\s*::\s*\w+)?(?:\s+as\s+\w+)?\s+from\s+snapshot_release\s+r\b")


def release_columns(block):
    """블록이 표지에서 읽는 칸 이름들(집합 — 'loaded' · 'published')."""
    code = "\n".join(ln.split("--")[0] for ln in statements(block).split("\n"))
    return {m.lower() for m in RE_RELEASE_COL.findall(code)}


# ── 옛 결과 그대로인가 — 줄 단위 대조 ──────────────────────────────────────────

# 옛 본문에서 **지워져도 되는** 줄(앞뒤 공백 걷은 꼴) — 이 셋 말고 하나라도 지워지면 옛 논리가 바뀐 것이다.
EXPECTED_REMOVED = {
    "select ub.pnu, count(*)::int as n",
    "order by store_cnt desc, pnu",
    "order by pg.store_cnt desc, pg.pnu;",
}
# 새로 든 코드 줄은 전부 이 낱말 중 하나를 품어야 한다(업종 인자에 묶인 줄).
INDUSTRY_WORDS = ("p_cat_m", "cat_n", "cat_store_cnt")
# 예외 하나 — 위 첫 줄이 다음 줄(cat_n)로 이어지려고 끝에 쉼표만 붙은 꼴.
EXPECTED_ADDED_PLAIN = {"select ub.pnu, count(*)::int as n,"}


def body_changes(old_body, new_body):
    """옛·새 본문의 줄 차이 → (지워진 코드 줄 집합, 업종 낱말 없이 새로 든 코드 줄 목록).

    ⓘ 주석 줄(`--` 로 시작)과 빈 줄은 견주지 않는다 — 본문 주석은 라이브에 실리지만 동작은 안 바꾼다.
    ⓘ 가드 본체와 양성 대조가 이 같은 함수를 지난다.
    ⚠️ 못 보는 것: 업종 낱말을 품은 새 줄이 옛 논리를 바꾸는 꼴(그 줄들은 아래 시험이 글자로 따로 본다) ·
       한 줄 안에서 `--` 뒤 주석만 바뀐 꼴(동작과 무관).
    """
    def code_lines(body):
        return [ln.strip() for ln in body.split("\n")
                if ln.strip() and not ln.strip().startswith("--")]

    removed, added = set(), []
    for d in difflib.ndiff(code_lines(old_body), code_lines(new_body)):
        if d.startswith("- "):
            removed.add(d[2:])
        elif (d.startswith("+ ") and not any(w in d for w in INDUSTRY_WORDS)
              and d[2:] not in EXPECTED_ADDED_PLAIN):
            added.append(d[2:])
    return removed, added


class TestNullIsTheOldResult:
    def test_only_the_planned_lines_change(self, mig, prev):
        removed, added = body_changes(body_of(fn_block(prev, FN)), body_of(fn_block(mig, FN)))
        assert removed == EXPECTED_REMOVED
        assert added == [], "업종 인자와 무관한 새 코드 줄 — 칩 '전체'의 결과가 바뀔 수 있습니다"

    @pytest.mark.parametrize("old, new", (
        ("where d.district_id = p_district_id", "where d.district_id = p_district_id and true"),  # 흔한 꼴: 옛 줄 고침
        ("    group by e.pnu\n", "    group by e.pnu, e.bld_id\n"),                                   # 변형: 묶음 열쇠
    ))
    def test_detector_catches_a_changed_old_line(self, mig, prev, old, new):
        """양성 대조 — 옛 줄 하나를 바꾸면 지워진 줄이 하나 더 생긴다."""
        body = body_of(fn_block(mig, FN))
        assert old in body
        removed, _ = body_changes(body_of(fn_block(prev, FN)), body.replace(old, new, 1))
        assert removed != EXPECTED_REMOVED

    def test_detector_catches_an_unrelated_new_line(self, mig, prev):
        """양성 대조 — 업종 인자와 무관한 줄(거르기 하나)을 끼우면 잡힌다."""
        body = body_of(fn_block(mig, FN)).replace(
            "    where ub.snapshot_ym", "    where ub.floor_no is not null\n      and ub.snapshot_ym", 1)
        _, added = body_changes(body_of(fn_block(prev, FN)), body)
        assert "where ub.floor_no is not null" in added

    def test_the_industry_lines_are_the_planned_ones(self, mig):
        flat = re.sub(r"\s+", " ", "\n".join(
            ln.split("--")[0] for ln in body_of(fn_block(mig, FN)).split("\n")))
        for piece in (
            # 세기 — 같은 훑기 한 번 · char(4)[] 캐스트(형제 list_industry_floors 와 같은 자)
            "(count(*) filter (where ub.cat_m_cd = any(p_cat_m::char(4)[])))::int as cat_n",
            # 칸 — 인자가 null 이면 null
            "(case when p_cat_m is not null then coalesce(max(s.cat_n), 0) end)::int as cat_store_cnt",
            # 거르기 — 인자가 null 이면 거르지 않는다 · 있으면 1곳 이상
            "having p_cat_m is null or coalesce(max(s.cat_n), 0) > 0",
            # 정렬 — 업종 수 → 전체 수 → pnu(tie-break)
            "order by cat_store_cnt desc nulls last, store_cnt desc, pnu limit",
            "order by pg.cat_store_cnt desc nulls last, pg.store_cnt desc, pg.pnu;",
            "pg.store_cnt, pg.cat_store_cnt, pg.bld_cnt_in_pnu,",
        ):
            assert piece in flat, piece

    def test_still_reads_published(self, mig, schema):
        """결정 0035 — 실시간 함수는 표지 published 만."""
        assert release_columns(fn_block(mig, FN)) == {"published"}
        assert release_columns(fn_block(schema, FN)) == {"published"}


# ── 정본과 글자 그대로 ───────────────────────────────────────────────────────


class TestMirrorsTheSchema:
    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_head_and_body(self, mig, schema, name):
        assert fn_block(mig, name) == fn_block(schema, name), name

    def test_heads(self, mig):
        pub, api = head_of(fn_block(mig, FN)), head_of(fn_block(mig, API_FN))
        for head, path in ((pub, "set search_path = public"), (api, "set search_path = ''")):
            assert "language sql" in head and "security definer" in head and path in head
            assert re.search(r"(?m)^stable\s*$", head)

    def test_comment(self, mig, schema):
        c = fn_comment(mig, FN)
        assert c == fn_comment(schema, FN)
        assert c.startswith("comment on function {}{} is".format(FN, NEW_SIG))
        assert "p_cat_m" in c and "cat_store_cnt" in c

    def test_comment_detector_catches_one_letter(self, mig):
        """양성 대조 — comment 한 글자가 바뀌면 대조가 갈린다."""
        bad = mig.replace("(null 이면 옛 결과 그대로", "(null 이면 옛 결과 그데로", 1)
        assert bad != mig and fn_comment(bad, FN) != fn_comment(mig, FN)

    def test_api_twin_passes_the_new_argument(self, mig):
        body = re.sub(r"\s+", " ", body_of(fn_block(mig, API_FN))).strip()
        assert body == "select * from public.list_district_buildings(p_district_id, p_limit, p_offset, p_cat_m)"

    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_new_argument_and_column(self, mig, name):
        head = head_of(fn_block(mig, name))
        # 형제 list_industry_floors 와 같은 이름·같은 꼴(칩의 짝 중분류 코드 배열)
        assert re.search(r"(?m)^\s*p_offset\s+int default 0,\n\s*p_cat_m\s+text\[\] default null\n\)", head)
        # 새 칸은 store_cnt 바로 뒤 — api 쌍둥이가 `select *` 라 두 쪽 차례가 같아야 한다
        assert re.search(r"(?m)^\s*store_cnt\s+int,.*\n\s*cat_store_cnt\s+int,", head)

    def test_argument_name_matches_the_sibling(self):
        assert "p_cat_m text[] default null" in fn_block(read(SIBLING), "list_industry_floors")


# ── 지우고 다시 만들기 · 권한 ────────────────────────────────────────────────


class TestDropRecreateAndGrants:
    def test_order_inside_one_transaction(self, mig):
        code = statements(mig)
        pos = [code.index(s) for s in (
            "set lock_timeout",
            "\nbegin;",
            "drop function if exists api.list_district_buildings(text, int, int);",
            "drop function if exists list_district_buildings(text, int, int);",
            "create or replace function list_district_buildings(",
            "create or replace function api.list_district_buildings(",
            "\ncommit;",
            "notify pgrst, 'reload schema';",
        )]
        assert pos == sorted(pos), pos

    def test_old_signature_only_in_the_drops(self, mig):
        lines = [ln for ln in statements(mig).split("\n") if OLD_SIG in ln]
        assert lines == ["drop function if exists api.list_district_buildings(text, int, int);",
                         "drop function if exists list_district_buildings(text, int, int);"]

    @pytest.mark.parametrize("text_fixture", ("mig", "schema"))
    def test_grant_only_on_the_api_twin(self, text_fixture, request):
        text = request.getfixturevalue(text_fixture)
        hits = [t for t in grant_targets(text) if t.endswith(FN)]
        assert hits == [API_FN], hits

    @pytest.mark.parametrize("bad", (
        "grant execute on function list_district_buildings(text, int, int, text[]) to anon;",   # 흔한 꼴
        "GRANT ALL\n  ON FUNCTION public.list_district_buildings(text, int, int, text[])\n  TO authenticated;",  # 변형
    ))
    def test_grant_detector_catches_a_public_grant(self, mig, bad):
        """양성 대조 — public 원본을 여는 grant 를 끼우면 대상에 원본 이름이 잡힌다."""
        targets = grant_targets(mig + "\n" + bad + "\n")
        assert any(t in ("list_district_buildings", "public.list_district_buildings") for t in targets)

    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_revoked_with_the_new_signature(self, mig, name):
        assert "revoke all on function {}{} from public, anon, authenticated;".format(name, NEW_SIG) \
            in statements(mig)
        assert "grant execute on function {}{} to anon, authenticated;".format(API_FN, NEW_SIG) \
            in statements(mig)


def header_order(sql, title_word):
    """머리말 `-- <title_word> …` 절의 번호 줄(①②③)을 차례대로 — 주석 머리말만 본다(코드 줄은 안 본다).

    ⓘ 가드 본체와 양성 대조가 이 같은 함수를 지난다.
    ⚠️ 못 보는 것: 번호 없이 산문으로만 적은 순서 · 절 제목 낱말이 바뀐 꼴.
    """
    lines = [ln[2:].strip() for ln in sql.split("\n") if ln.startswith("--")]
    start = next((i for i, ln in enumerate(lines) if ln.startswith(title_word)), None)
    if start is None:
        return []
    steps = []
    # 제목 바로 다음 줄은 밑줄(`-----`)이다 — 그다음 밑줄이 나오면 다음 절이 시작된 것이다.
    for ln in lines[start + 2:]:
        if ln.startswith("---"):
            break
        if ln[:1] and ln[:1] in "①②③":
            steps.append(ln)
    return steps


class TestHeaderOrder:
    """👤 2026-10-11 — DB 먼저 → 화면 머지 · 되돌리기는 화면 먼저 → DB(새 서버는 옛 화면과 맞물린다)."""

    def test_apply_db_first_then_screen(self, mig):
        steps = header_order(mig, "실행 순서")
        assert len(steps) == 3 and "dbx.py -f" in steps[0] and "화면 PR 머지" in steps[2], steps
        assert "DB 먼저 → 그 뒤 화면 머지" in mig and "배치 창" in mig

    def test_rollback_screen_first_then_db(self, mig):
        steps = header_order(mig, "되돌리기")
        assert len(steps) == 2 and "revert" in steps[0] and "새 마이그레이션 파일" in steps[1], steps

    def test_check_md5_alarm_between_is_written(self, mig):
        assert "[사고](본문 md5 불일치)로 적는 것이 **정상**" in mig

    def test_detector_sees_a_swapped_order(self, mig):
        """양성 대조 — 실행 ①·③ 을 맞바꾼 사본은 첫 단계가 dbx 가 아니다."""
        steps = header_order(mig, "실행 순서")
        bad = mig.replace(steps[0], "@@").replace(steps[2], steps[0]).replace("@@", steps[2])
        assert "dbx.py -f" not in header_order(bad, "실행 순서")[0]


# ── ② 실행 가드 (로컬 PostgreSQL 이 있을 때만) ──────────────────────────────

SHIM = """
create table parcel (pnu char(19) primary key, geom text, road_addr text,
                     sido_nm text, sigungu_nm text, emd_nm text, jibun text);
create table district (district_id text primary key, geom text);
create table building (bld_id text primary key, pnu char(19), display_nm text, total_area_m2 numeric);
create table building_floor (bld_id text, floor_no smallint);
create table v_building_floor_stack (bld_id text, floor_no smallint);
create table unit_business (snapshot_ym char(6), pnu char(19), cat_m_cd char(4));
create table snapshot_release (id int primary key, loaded_ym char(6), published_ym char(6));
-- 흉내 낸 공간 판정: 점 이름이 도형 글자 안에 '|이름|' 꼴로 들어 있으면 담긴 것.
create function st_contains(poly text, pt text) returns boolean language sql immutable
  as 'select position(''|'' || pt || ''|'' in poly) > 0';
create function st_y(g text) returns double precision language sql immutable as 'select 37.5::double precision';
create function st_x(g text) returns double precision language sql immutable as 'select 127.0::double precision';
create function parcel_jibun_addr(a text, b text, c text, d text) returns text language sql immutable
  as 'select concat_ws('' '', a, b, c, d)';
"""


def _pnu(i):
    return "11110101001000{}0000".format(i)


# 땅 일곱 — (점포 전체, 카페 I212, 학원 P105, 학원 P106, 동 수)
LANDS = {
    1: (10, 1, 0, 0, 1),
    2: (5, 3, 1, 0, 2),
    3: (5, 0, 0, 2, 1),
    4: (0, 0, 0, 0, 1),
    5: (3, 3, 0, 0, 1),
    6: (2, 2, 0, 0, 1),
    7: (2, 2, 0, 0, 1),
}


def _fixture_sql():
    out = ["insert into snapshot_release values (1, '202606', '202606');",
           "insert into district values ('D1', '|{}|');".format("|".join("G{}".format(i) for i in LANDS))]
    for i, (total, cafe, a, b, dongs) in LANDS.items():
        p = _pnu(i)
        out.append("insert into parcel values ('{}', 'G{}', '도로 {}', '서울', '중구', '동', '{}');".format(p, i, i, i))
        for d in range(dongs):
            bid = "B{}-{}".format(i, d)
            out.append("insert into building values ('{}', '{}', '건물{}', {});".format(bid, p, bid, 100 * (d + 1)))
            out.append("insert into building_floor values ('{}', 1), ('{}', 2);".format(bid, bid))
            out.append("insert into v_building_floor_stack values ('{}', 1), ('{}', 2);".format(bid, bid))
        cats = ["I212"] * cafe + ["P105"] * a + ["P106"] * b
        cats += ["G204"] * (total - len(cats))
        for c in cats:
            out.append("insert into unit_business values ('202606', '{}', '{}');".format(p, c))
    # 옛 분기의 카페(P3 · P4)는 세지 않는다 — 표지가 202606 이다.
    out.append("insert into unit_business values ('202603', '{}', 'I212'), ('202603', '{}', 'I212');"
               .format(_pnu(3), _pnu(4)))
    # 층 자료 없는 건물만 선 땅(P8)은 목록에 없다(옛 규칙 그대로).
    out.append("insert into parcel values ('{}', 'G8', '도로 8', '서울', '중구', '동', '8');".format(_pnu(8)))
    out.append("insert into building values ('B8', '{}', '층없음', 50);".format(_pnu(8)))
    out.append("insert into unit_business values ('202606', '{}', 'I212');".format(_pnu(8)))
    out.append("update district set geom = geom || 'G8|';")
    return "\n".join(out)


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
    """흉내 판 + 옛 함수(10-07a 본문을 old_ldb 이름으로) + 새 함수와 api 쌍둥이(10-11a)."""
    mig, prev = read(MIGRATION), read(PREVIOUS)
    c = pg.cursor()
    c.execute("drop schema if exists public cascade; drop schema if exists api cascade;"
              " create schema public; create schema api;")
    c.execute(SHIM)
    c.execute(_fixture_sql())
    c.execute(fn_block(prev, FN).replace("function {}(".format(FN), "function old_ldb(", 1))
    c.execute(fn_block(mig, FN))
    c.execute(fn_block(mig, API_FN))
    return c


def _rows(cur, sql, args=()):
    cur.execute(sql, args)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


class TestRealRun:
    @pytest.mark.parametrize("lim, off", ((50, 0), (2, 0), (2, 2), (3, 5), (None, None)))
    def test_null_is_the_old_result(self, cur, lim, off):
        old = _rows(cur, "select * from old_ldb(%s, %s, %s)", ("D1", lim, off))
        new = _rows(cur, "select * from list_district_buildings(%s, %s, %s, null)", ("D1", lim, off))
        assert old, "흉내 판이 비었다 — 비교가 헛돈다"
        assert [r.pop("cat_store_cnt") for r in new] == [None] * len(new)
        assert new == old

    def test_old_screen_call_with_three_named_arguments(self, cur):
        """옛 화면 — 인자 이름 셋으로 부르면 넷째 기본값(null)이 들어가 옛 결과 그대로."""
        old = _rows(cur, "select * from old_ldb(p_district_id := 'D1', p_limit := 50, p_offset := 0)")
        new = _rows(cur, "select * from api.list_district_buildings("
                         "p_district_id := 'D1', p_limit := 50, p_offset := 0)")
        for r in new:
            assert r.pop("cat_store_cnt") is None
        assert new == old

    def test_cafe_filters_and_orders(self, cur):
        got = _rows(cur, "select * from api.list_district_buildings('D1', 50, 0, %s)", (["I212"],))
        # 카페 수 → 전체 수 → pnu · 카페 0곳 땅(P3·P4)은 없다 · 옛 분기 카페는 안 센다 · 층 없는 땅(P8) 없다
        assert [(r["pnu"], r["cat_store_cnt"], r["store_cnt"]) for r in got] == [
            (_pnu(2), 3, 5), (_pnu(5), 3, 3), (_pnu(6), 2, 2), (_pnu(7), 2, 2), (_pnu(1), 1, 10)]
        assert {r["total_parcel_cnt"] for r in got} == {5}
        assert {r["total_bld_cnt"] for r in got} == {6}   # P2 가 두 동

    def test_two_codes_add_up(self, cur):
        got = _rows(cur, "select * from list_district_buildings('D1', 50, 0, %s)", (["P105", "P106"],))
        assert [(r["pnu"], r["cat_store_cnt"]) for r in got] == [(_pnu(3), 2), (_pnu(2), 1)]

    def test_paging_with_the_industry(self, cur):
        first = _rows(cur, "select pnu from list_district_buildings('D1', 2, 0, %s)", (["I212"],))
        second = _rows(cur, "select pnu from list_district_buildings('D1', 2, 2, %s)", (["I212"],))
        assert [r["pnu"] for r in first + second] == [_pnu(2), _pnu(5), _pnu(6), _pnu(7)]

    def test_no_land_with_the_industry(self, cur):
        assert _rows(cur, "select * from list_district_buildings('D1', 50, 0, %s)", (["Z999"],)) == []
