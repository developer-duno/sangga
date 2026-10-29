# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-11c(건물 표에 승강기·호수·구조·내진·에너지 칸 — 물결 2-1 PR① · 결정 0036)의
불변식을 지킨다.

무엇을 막나 (전부 **에러 없이** 나는 실수다)
---------------------------------------------
  1) 칸 8개의 이름·형이 정본과 갈리거나, 표 앞쪽에 끼운다 → 새 환경만 다른 모양이 된다.
  2) api.building 을 다시 안 만든다 → `select *` 뷰는 만든 날의 칸으로 굳어, 적재기 upsert
     (profile 헤더 없이 첫 스키마 api 를 탄다)가 새 칸을 못 찾고 PGRST204 로 멈춘다.
  3) v_floor_stack 끝 6칸(5칸 + 2026-10-12 PR② 의 bld_main_use)이 빠지거나 순서가 바뀐다 ·
     api.v_floor_stack 을 public 뷰보다 먼저
     (또는 아예 안) 다시 만든다 → 화면이 새 칸을 영영 못 본다(2026-08-24a 함정).
  4) v_floor_stack 이 **내보내지 않기로 한** 세 칸(내진 능력·에너지 등급·녹색 등급 — 채움 0.4~8.5% ·
     사장님 결정 2026-10-11)을 내보낸다. 「없음」 단언이라 탐지는 아래 작은 함수 하나로 빼고
     양성 대조(흔한 꼴 + 변형 꼴)가 같은 함수를 지난다.
  5) search_buildings 의 끝 세 칸(ho_cnt·elevator_ride·elevator_emgen)이 앞에 끼거나 형이 다르다 ·
     머리(language·stable·security definer·search_path·plan_cache_mode)·comment 가 정본과 다르다 ·
     검색 가지(addr·nm·hit)를 건드린다(가지에 민감 — 2026-10-09a 머리말).
  6) 순서 — `set lock_timeout` 이 begin 앞 · begin/commit 한 쌍 · notify 는 commit 뒤 · api 먼저 drop.
  7) 권한 — 함수 grant 는 api 쌍둥이에만(anon·authenticated) · api.building 은 service_role 만 ·
     api.v_floor_stack 은 anon·authenticated 읽기만 · public 객체 grant 0.
  8) 새 함수 0 — 이 마이그레이션은 공개 호출 허용 총계(post_load.py --check)를 늘리지 않는다(적용 때 30 · 지금 32 —
     2026-10-12a 가 31, 2026-10-13a 가 32 로 늘렸다 · 아래 시험이 지금 총계를 본다).

② 실행 가드(로컬 PostgreSQL 이 있을 때만): 흉내 판에 **적용 전 라이브 모양**(10-07a 의 v_floor_stack ·
   10-09a 의 search_buildings 16칸 · 옛 api.building)을 세우고 이 마이그레이션 **파일 통째**를 돌린다 —
   `create or replace view` 가 끝에 붙이기만 하는지(라이브는 앞을 바꾸면 거절한다) · api 뷰 둘이 새 칸을
   내는지 · 적재기 길(api.building 으로 upsert)이 새 칸을 받는지 · plpgsql `return query` 의 형이 맞는지
   (형이 어긋나면 만들 때가 아니라 **부를 때** "structure of query does not match" 로 검색이 죽는다).
   CI 에는 PostgreSQL 이 없어 건너뛴다.

⚠️ 못 보는 것: 라이브에 이 파일이 실제로 적용됐는지(사람이 dbx.py -f 뒤 머리말의 확인 쿼리로) ·
   값이 실제로 채워졌는지(적재기 --building-only 뒤 확인) · 뷰 안에서 `b.*`·별칭 없는 식(`coalesce(…)`)으로
   숨긴 칸을 낸 것 중 아래 탐지 함수 머리말 「못 보는 것」에 적은 꼴.
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
MIG_DIR = os.path.join(ROOT, "supabase", "migrations")
MIGRATION = os.path.join(MIG_DIR, "2026-10-11c_building_elevator_ho.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
PREV_SEARCH = os.path.join(MIG_DIR, "2026-10-09a_search_ownership_cols.sql")
PREV_VIEW = os.path.join(MIG_DIR, "2026-10-07a_snapshot_release.sql")

SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

DOLLAR = chr(36) * 2

NEW_COLS = (
    ("elevator_ride", "smallint"),
    ("elevator_emgen", "smallint"),
    ("ho_cnt", "integer"),
    ("strct_nm", "text"),
    ("seismic_design", "boolean"),
    ("seismic_ability", "text"),
    ("energy_grade", "text"),
    ("green_grade", "text"),
)
# 끝 bld_main_use(= building.main_use)는 2026-10-12 PR② 가 더했다(운영 적용 전 수정 · 주거 건물의 대장 호수 숨김).
VIEW_TAIL = ("elevator_ride", "elevator_emgen", "ho_cnt", "strct_nm", "seismic_design", "bld_main_use")
HIDDEN = ("seismic_ability", "energy_grade", "green_grade")

OLD16 = [
    ("bld_id", "text"), ("pnu", "char(19)"), ("bld_nm", "text"), ("road_addr", "text"),
    ("jibun_addr", "text"), ("lat", "double precision"), ("lng", "double precision"),
    ("bld_cnt_in_pnu", "int"), ("floor_cnt", "int"), ("min_floor", "smallint"),
    ("max_floor", "smallint"), ("has_roof", "boolean"), ("total_cnt", "bigint"),
    ("is_jiphap", "boolean"), ("approve_date", "date"), ("parking_cnt", "integer"),
]
SEARCH_TAIL = [("ho_cnt", "integer"), ("elevator_ride", "smallint"), ("elevator_emgen", "smallint"),
               ("bld_main_use", "text")]

PUBLIC_HEAD = ("language plpgsql", "stable", "security definer", "set search_path = public",
               "set plan_cache_mode = force_custom_plan")
API_HEAD = ("language sql", "stable", "security definer", "set search_path = ''")
FINAL_SELECT_MARK = "  -- ② 지번주소 조립·좌표 뽑기는 여기서 처음 한다"
SPEC_SELECT = ("bo.is_jiphap, bo.approve_date, bo.parking_cnt, bo.ho_cnt, bo.elevator_ride, bo.elevator_emgen, "
               "bo.main_use")


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
    """줄 전체 주석을 걷은 것(줄 구조는 그대로)."""
    return "\n".join(ln for ln in sql.split("\n") if not ln.lstrip().startswith("--"))


RE_COMMENT_STMT = re.compile(r"(?ims)^comment\s+on\s+.*?';\s*$")


def code_only(sql):
    """줄 주석 · `comment on … is '…';` 글 · 줄 끝 `--` 주석까지 걷은 코드만."""
    text = RE_COMMENT_STMT.sub("", statements(sql))
    return "\n".join(ln.split("--")[0] for ln in text.split("\n"))


def flat(sql):
    return re.sub(r"\s+", " ", code_only(sql)).strip()


def alter_block(sql):
    m = re.search(r"(?ims)^alter table building\n\s+add column if not exists elevator_ride\b.*?;", sql)
    assert m, "elevator_ride 를 더하는 alter table building 을 못 찾았습니다"
    return m.group(0)


def view_block(sql):
    m = re.search(r"(?ms)^create or replace view v_floor_stack as\n.*?^\) st on true;", sql)
    assert m, "v_floor_stack 정의를 못 찾았습니다"
    return m.group(0)


def fn_block(sql, api):
    if api:
        head = r"(?im)^create\s+(?:or\s+replace\s+)?function\s+api\.search_buildings\s*\("
    else:
        head = (r"(?im)^create\s+(?:or\s+replace\s+)?function\s+(?!api\.)(?:public\.)?"
                r"search_buildings\s*\(")
    m = re.search(head, sql)
    assert m, "search_buildings{} 정의를 못 찾았습니다".format(" (api)" if api else "")
    end = sql.index(DOLLAR + ";", m.start()) + len(DOLLAR + ";")
    return sql[m.start():end]


def comment_of(sql, pattern):
    m = re.search(pattern, sql)
    assert m, pattern
    return m.group(0)


COL_COMMENT = r"(?ims)^comment\s+on\s+column\s+building\.{}\s+is.*?';\s*$"
VIEW_COMMENT = r"(?ims)^comment\s+on\s+view\s+v_floor_stack\s+is.*?';\s*$"
FN_COMMENT = r"(?ims)^comment\s+on\s+function\s+search_buildings\s*\(text,\s*int,\s*text\)\s+is.*?';\s*$"


# ── 판정 함수 — 가드 본체와 양성 대조가 **같은 함수**를 지난다 ──────────────────


def added_cols(block):
    """`add column if not exists <이름> <형>` (이름, 형) 목록 — 차례 그대로."""
    return [(n.lower(), t.lower()) for n, t in re.findall(
        r"(?i)add\s+column\s+if\s+not\s+exists\s+(\w+)\s+([\w ()]+?)\s*[,;]", block)]


def view_select_cols(block):
    """v_floor_stack select 목록의 **나가는 칸 이름** 차례 — `x.y` 는 y, `… as z` 는 z."""
    body = code_only(block)
    body = body[body.index("select") + len("select"):body.index("\nfrom v_building_floor_stack")]
    out, depth, cur = [], 0, []
    for ch in body:
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    names = []
    for item in (i.strip() for i in out if i.strip()):
        m = re.search(r"(?i)\bas\s+\"?(\w+)\"?\s*$", item) or re.search(r"(\w+|\*)\s*$", item)
        names.append(m.group(1).lower())
    return names


RE_HIDDEN = re.compile(r"(?i)\b(?:" + "|".join(HIDDEN) + r")\b")
RE_STAR = re.compile(r"(?i)\b\w+\s*\.\s*\*")


def hidden_leaks(block):
    """v_floor_stack 정의가 내보내지 않기로 한 세 칸(내진 능력·에너지·녹색 등급)을 내는가.

    잡는 꼴: `b.energy_grade` · `b."green_grade"` · 대문자 · `coalesce(b.seismic_ability, '')` · 별칭 붙인 꼴 ·
       `b.*`(표를 통째로 내보내면 세 칸이 같이 나간다).
    주석·`comment on … is '…'` 글 안의 낱말은 세지 않는다(code_only).
    ⚠️ 못 보는 것: 동적 SQL · 칸 이름을 문자열로 쪼개 이은 꼴 · building 을 다른 뷰로 한 번 감싸 `x.*` 없이
       낸 꼴(그 뷰 쪽은 안 본다).
    """
    code = code_only(block)
    return sorted({m.group(0).lower() for m in RE_HIDDEN.finditer(code)}
                  | {m.group(0).replace(" ", "") for m in RE_STAR.finditer(code)})


def returns_cols(block):
    m = re.search(r"(?is)returns\s+table\s*\(", block)
    assert m, "returns table 을 못 찾았습니다"
    depth, i = 1, m.end()
    while depth:
        depth += {"(": 1, ")": -1}.get(block[i], 0)
        i += 1
    inner = re.sub(r"--[^\n]*", "", block[m.end():i - 1])
    out, depth, cur = [], 0, []
    for ch in inner:
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return [(w[0].lower(), " ".join(w[1:]).lower()) for w in (i.split() for i in out) if w]


def search_col_defects(block):
    cols = returns_cols(block)
    bad = []
    if cols[:len(OLD16)] != OLD16:
        bad.append("앞 16칸이 바뀌었습니다: {}".format(cols[:len(OLD16)]))
    if cols[len(OLD16):] != SEARCH_TAIL:
        bad.append("끝 칸이 {} 입니다(기대 {})".format(cols[len(OLD16):], SEARCH_TAIL))
    return bad


def head_defects(block, must):
    head = re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", block[:block.index(DOLLAR)])).strip().lower()
    return ["머리에 `{}` 가 없습니다".format(w) for w in must if w not in head]


def body_defects(new_block, prev_block):
    """마지막 select 앞까지는 10-09a 와 글자 그대로 · 세 칸은 같은 조인 bo 에서, parking_cnt 바로 뒤."""
    bad = []
    for name, blk in (("새 판", new_block), ("10-09a", prev_block)):
        if blk.count(FINAL_SELECT_MARK) != 1:
            return ["{} 에서 마지막 select 표시 줄을 못 찾았습니다".format(name)]
    nb, pb = new_block[new_block.index(DOLLAR):], prev_block[prev_block.index(DOLLAR):]
    if nb[:nb.index(FINAL_SELECT_MARK)] != pb[:pb.index(FINAL_SELECT_MARK)]:
        bad.append("마지막 select 앞(검색 가지·정렬·limit)이 10-09a 와 다릅니다")
    tail = re.sub(r"\s+", " ", statements(nb[nb.index(FINAL_SELECT_MARK):]))
    if tail.count(SPEC_SELECT) != 1:
        bad.append("select 목록에 `{}` 가 한 번 없습니다".format(SPEC_SELECT))
    if tail.count("join building bo on bo.bld_id = t.bld_id") != 1 or tail.count("join building") != 1:
        bad.append("building 조인이 기본키 조인 bo 하나가 아닙니다")
    return bad


def file_order_defects(sql):
    code = code_only(sql).lower()

    def pos(pattern):
        m = re.search(pattern, code, re.M)
        return m.start() if m else None

    named = dict(
        lock=pos(r"^set lock_timeout\b"),
        begin=pos(r"^begin;"),
        alter=pos(r"^alter table building\b"),
        api_building=pos(r"^create or replace view api\.building\s+as select \* from public\.building;"),
        view=pos(r"^create or replace view v_floor_stack as"),
        invoker=pos(r"^alter view v_floor_stack set \(security_invoker = false\);"),
        api_view=pos(r"^create or replace view api\.v_floor_stack as select \* from public\.v_floor_stack;"),
        drop_api=pos(r"^drop function if exists api\.search_buildings\(text, int, text\);"),
        drop_pub=pos(r"^drop function if exists (?:public\.)?search_buildings\(text, int, text\);"),
        create_pub=pos(r"^create (?:or replace )?function (?:public\.)?search_buildings\("),
        create_api=pos(r"^create (?:or replace )?function api\.search_buildings\("),
        grant=pos(r"^grant execute on function api\.search_buildings\("),
        commit=pos(r"^commit;"),
        notify=pos(r"^notify pgrst\b"),
    )
    missing = [k for k, v in named.items() if v is None]
    if missing:
        return ["문장을 못 찾았습니다: {}".format(missing)]
    chain = ["lock", "begin", "alter", "api_building", "view", "invoker", "api_view", "drop_api",
             "drop_pub", "create_pub", "create_api", "grant", "commit", "notify"]
    bad = ["`{}` 가 `{}` 보다 앞이어야 합니다".format(a, b)
           for a, b in zip(chain, chain[1:]) if not named[a] < named[b]]
    if len(re.findall(r"(?m)^begin;", code)) != 1 or len(re.findall(r"(?m)^commit;", code)) != 1:
        bad.append("begin/commit 이 한 쌍이 아닙니다 — 한 파일 = 한 덩어리")
    return bad


RE_GRANT = re.compile(r"(?is)\bgrant\s+(.*?)\s+on\s+(?:(table|function)\s+)?([\w.]+)\s*(\([^)]*\))?\s+to\s+([^;]+);")


def grants_of(sql):
    """(대상 이름 소문자 — 함수면 '()' 붙임, 받는 쪽 집합, 권한 글) 목록 — 주석·comment 글은 걷는다."""
    out = []
    for priv, kind, obj, args, to in RE_GRANT.findall(flat(sql)):
        name = obj.lower() + ("()" if (kind.lower() == "function" or args) else "")
        out.append((name, {w.strip().lower() for w in to.split(",")}, priv.lower()))
    return out


WANT_GRANTS = [
    ("api.building", {"service_role"}, "select, insert, update, delete"),
    ("api.v_floor_stack", {"anon", "authenticated"}, "select"),
    ("api.search_buildings()", {"anon", "authenticated"}, "execute"),
]


def grant_defects(sql):
    got = grants_of(sql)
    bad = []
    if got != WANT_GRANTS:
        bad.append("grant 가 기대와 다릅니다: {}".format(got))
    code = flat(sql)
    for obj in ("api.building", "api.v_floor_stack", "function api.search_buildings(text, int, text)",
                "function search_buildings(text, int, text)"):
        if "revoke all on {} from public, anon, authenticated;".format(obj) not in code:
            bad.append("`revoke all on {}` 가 없습니다".format(obj))
    for obj, grant_txt in (("api.building", "grant select, insert, update, delete on api.building"),
                           ("api.v_floor_stack", "grant select on api.v_floor_stack"),
                           ("function api.search_buildings(text, int, text)",
                            "grant execute on function api.search_buildings")):
        rv = code.find("revoke all on {} from".format(obj))
        gr = code.find(grant_txt)
        if -1 < gr < rv:
            bad.append("{} 회수가 grant 뒤에 있습니다".format(obj))
    return bad


def created_functions(sql):
    return sorted({m.lower() for m in re.findall(
        r"(?im)^create\s+(?:or\s+replace\s+)?function\s+([\w.]+)\s*\(", code_only(sql))})


# ── 1. 칸 8개 ────────────────────────────────────────────────────────────────


class TestColumns:
    @pytest.mark.parametrize("which", ["mig", "schema"])
    def test_eight_columns_names_and_types(self, which, request):
        assert added_cols(alter_block(request.getfixturevalue(which))) == list(NEW_COLS)

    def test_alter_is_the_schema_letter_for_letter(self, mig, schema):
        assert alter_block(mig) == alter_block(schema)

    def test_schema_adds_them_before_v_floor_stack_reads_them(self, schema):
        """정본을 위에서부터 돌리면(새 환경) 뷰가 칸보다 먼저 서면 안 된다."""
        assert schema.index(alter_block(schema)) < schema.index(view_block(schema))

    def test_not_in_the_create_table_body(self, schema):
        """라이브는 표 끝에 붙였다 — 정본도 create table 본문이 아니라 ALTER 로(같은 칸 모양)."""
        m = re.search(r"(?ms)^create table if not exists building \((.*?)^\);", schema)
        assert m
        for name, _ in NEW_COLS:
            assert not re.search(r"(?m)^\s+{}\b".format(name), m.group(1)), name

    @pytest.mark.parametrize("name", [n for n, _ in NEW_COLS])
    def test_column_comment_matches_schema(self, mig, schema, name):
        a = comment_of(mig, COL_COMMENT.format(name))
        assert a == comment_of(schema, COL_COMMENT.format(name))
        assert "2026-10-11c" in a

    @pytest.mark.parametrize("name", ["elevator_ride", "elevator_emgen"])
    def test_zero_is_unrecorded_warning(self, mig, name):
        assert "0 = 대장 미기재가 섞여 있다" in comment_of(mig, COL_COMMENT.format(name))
        assert "24%" in comment_of(mig, COL_COMMENT.format(name))

    def test_ho_zero_is_mostly_normal(self, mig, schema):
        """호수 0 은 일반건축물에서 정상이다(호 구분 없음) — 승강기 실측(11층+ 24%)을 근거로 끌어오지 않는다.
        파일 어디에도 '호수 0 = 미기재' 꼴의 옛 문장이 남지 않는다."""
        c = comment_of(mig, COL_COMMENT.format("ho_cnt"))
        assert "일반건축물은 호 구분이 없어 0 이 정상" in c and "97.6%" in c and "72%" in c
        assert "미기재" not in c and "승강기" not in c
        for text in (mig, schema):
            assert "승강기·호수의 0" not in text and "승강기·호수 0" not in text
            assert "-- 호수 (0 = 미기재 섞임)" not in text

    def test_seismic_comment(self, mig):
        c = comment_of(mig, COL_COMMENT.format("seismic_design"))
        assert "1988년 전 건물은 거의 다 false" in c and "true 일 때만" in c
        assert "내진 의무 대상이 아닌 작은 건물도 false" in c and "강남 19%·대전 중구 28%" in c

    def test_header_has_the_reload_done_checks(self, mig):
        """재적재 완료 판정(구마다 NULL · 앞뒤 max(updated_at)) + 디스크 멈춤선이 머리말에 있다."""
        head = mig[:mig.index("set lock_timeout")]
        assert "count(*) filter (where elevator_ride is null) as nulls" in head and "group by 1 order by 1" in head
        assert "select max(updated_at), count(*) from building;" in head
        assert "84% 이상이면 멈춘다" in head

    @pytest.mark.parametrize("name", HIDDEN)
    def test_low_fill_columns_say_not_on_screen(self, mig, name):
        c = comment_of(mig, COL_COMMENT.format(name))
        assert "채움 0.4~8.5%" in c and "화면에 안 낸다" in c


class TestColumnMutations:
    @pytest.mark.parametrize("name,mutate", (
        ("type_changed", lambda b: b.replace("ho_cnt          integer", "ho_cnt          smallint", 1)),
        ("column_dropped", lambda b: b.replace("  add column if not exists green_grade     text;",
                                               "  add column if not exists energy_grade    text;", 1)
         .replace("  add column if not exists energy_grade    text,\n", "", 1)),
        ("reordered", lambda b: b.replace(
            "elevator_ride   smallint,\n  add column if not exists elevator_emgen  smallint,",
            "elevator_emgen  smallint,\n  add column if not exists elevator_ride   smallint,", 1)),
    ), ids=["type_changed", "column_dropped", "reordered"])
    def test_detector_bites(self, mig, name, mutate):
        block = alter_block(mig)
        assert added_cols(block) == list(NEW_COLS), "전제: 원문은 정상"
        broken = mutate(block)
        assert broken != block, name
        assert added_cols(broken) != list(NEW_COLS), name


# ── 2. api.building · v_floor_stack ─────────────────────────────────────────


class TestViews:
    def test_view_is_the_schema_letter_for_letter(self, mig, schema):
        assert view_block(mig) == view_block(schema)

    @pytest.mark.parametrize("which", ["mig", "schema"])
    def test_five_columns_appended_after_the_old_ones(self, which, request):
        new = view_select_cols(view_block(request.getfixturevalue(which)))
        old = view_select_cols(view_block(read(PREV_VIEW)))
        assert old[-1] == "lng", "전제: 옛 판의 마지막 칸은 lng"
        assert new[:len(old)] == old, "기존 칸의 이름·순서가 바뀌었습니다 — 라이브가 거절합니다"
        assert tuple(new[len(old):]) == VIEW_TAIL

    @pytest.mark.parametrize("which", ["mig", "schema"])
    def test_hidden_three_are_not_exported(self, which, request):
        assert hidden_leaks(view_block(request.getfixturevalue(which))) == []

    def test_view_comment_matches_schema(self, mig, schema):
        c = comment_of(mig, VIEW_COMMENT)
        assert c == comment_of(schema, VIEW_COMMENT)
        assert "2026-10-11c" in c and "대장 미기재" in c

    def test_api_building_and_twin_shapes(self, mig, schema):
        for text in (mig, schema):
            code = code_only(text)
            assert re.search(r"(?m)^create or replace view api\.building\s+as select \* from public\.building;", code)
            assert re.search(r"(?m)^create or replace view api\.v_floor_stack as select \* from public\.v_floor_stack;",
                             code)

    def test_no_view_is_dropped(self, mig):
        assert not re.search(r"(?im)^\s*drop\s+view", code_only(mig))


class TestHiddenLeakDetector:
    """「없음」 단언의 짝 — 같은 hidden_leaks 를 지나는 사본이 빨갛다."""

    @pytest.mark.parametrize("name,extra", (
        ("plain", "  b.energy_grade,\n"),                               # 흔한 꼴
        ("quoted_upper_alias", '  B."GREEN_GRADE" AS gg,\n'),            # 변형 꼴
        ("wrapped", "  coalesce(b.seismic_ability, '') as sa,\n"),       # 식 안
        ("star", "  b.*,\n"),                                            # 통째로
    ), ids=["plain", "quoted_upper_alias", "wrapped", "star"])
    def test_detector_bites(self, mig, name, extra):
        block = view_block(mig)
        broken = block.replace("  b.elevator_ride,", extra + "  b.elevator_ride,", 1)
        assert broken != block
        assert hidden_leaks(broken), name

    def test_comment_mentions_are_not_leaks(self, mig):
        block = view_block(mig).replace(
            "  b.elevator_ride,", "  -- b.energy_grade 는 안 낸다\n  b.elevator_ride,", 1)
        assert hidden_leaks(block) == []


# ── 3. search_buildings ────────────────────────────────────────────────────


class TestSearch:
    @pytest.mark.parametrize("which", ["mig", "schema"])
    @pytest.mark.parametrize("api", [False, True], ids=["public", "api"])
    def test_nineteen_columns(self, which, api, request):
        bad = search_col_defects(fn_block(request.getfixturevalue(which), api))
        assert not bad, " / ".join(bad)

    def test_old_sixteen_match_10_09a(self):
        assert returns_cols(fn_block(read(PREV_SEARCH), False)) == OLD16

    @pytest.mark.parametrize("api", [False, True], ids=["public", "api"])
    def test_block_is_the_schema_letter_for_letter(self, mig, schema, api):
        assert fn_block(mig, api) == fn_block(schema, api)

    def test_comment_is_the_schema_letter_for_letter(self, mig, schema):
        c = comment_of(mig, FN_COMMENT)
        assert c == comment_of(schema, FN_COMMENT)
        assert "ho_cnt·elevator_ride·elevator_emgen" in c

    @pytest.mark.parametrize("which", ["mig", "schema"])
    def test_heads(self, which, request):
        text = request.getfixturevalue(which)
        bad = head_defects(fn_block(text, False), PUBLIC_HEAD) + head_defects(fn_block(text, True), API_HEAD)
        assert not bad, " / ".join(bad)

    def test_api_body(self, mig):
        block = fn_block(mig, True)
        body = flat(block[block.index(DOLLAR) + 2:block.rindex(DOLLAR)])
        assert body == "select * from public.search_buildings(q, lim, sigungu)"

    @pytest.mark.parametrize("which", ["mig", "schema"])
    def test_branches_untouched_and_columns_from_bo(self, which, request):
        bad = body_defects(fn_block(request.getfixturevalue(which), False), fn_block(read(PREV_SEARCH), False))
        assert not bad, " / ".join(bad)


class TestSearchMutations:
    @pytest.mark.parametrize("name,mutate", (
        ("tail_type", lambda b: b.replace("  elevator_emgen smallint,\n", "  elevator_emgen integer,\n", 1)),
        ("tail_in_front", lambda b: b.replace("returns table (\n  bld_id         text,",
                                              "returns table (\n  ho_cnt         integer,\n  bld_id         text,", 1)),
        ("tail_reordered", lambda b: b.replace("  ho_cnt         integer,\n  elevator_ride  smallint,",
                                               "  elevator_ride  smallint,\n  ho_cnt         integer,", 1)),
    ), ids=["tail_type", "tail_in_front", "tail_reordered"])
    def test_columns(self, mig, name, mutate):
        block = fn_block(mig, False)
        broken = mutate(block)
        assert broken != block, name
        assert search_col_defects(broken), name

    @pytest.mark.parametrize("name,mutate", (
        ("second_join", lambda b: b.replace(
            "  join building bo on bo.bld_id = t.bld_id\n",
            "  join building bo on bo.bld_id = t.bld_id\n  join building bx on bx.bld_id = t.bld_id\n", 1)),
        ("carried_in_branch", lambda b: b.replace(
            "    select b.bld_id, b.pnu, b.nm_key, b.display_nm as bld_nm,\n           a.road_addr",
            "    select b.bld_id, b.pnu, b.nm_key, b.display_nm as bld_nm, b.ho_cnt,\n           a.road_addr", 1)),
        ("select_dropped", lambda b: b.replace(", bo.elevator_emgen,\n", ",\n", 1)),
        ("main_use_dropped", lambda b: b.replace(",\n    bo.main_use\n", "\n", 1)),
    ), ids=["second_join", "carried_in_branch", "select_dropped", "main_use_dropped"])
    def test_body(self, mig, name, mutate):
        prev = fn_block(read(PREV_SEARCH), False)
        block = fn_block(mig, False)
        assert not body_defects(block, prev), "전제: 원문은 정상"
        broken = mutate(block)
        assert broken != block, name
        assert body_defects(broken, prev), name

    @pytest.mark.parametrize("name,api,mutate,must", (
        ("search_path_gone", False, lambda b: b.replace("set search_path = public\n", "", 1), PUBLIC_HEAD),
        ("plan_cache_as_comment", False, lambda b: b.replace(
            "set plan_cache_mode = force_custom_plan\n", "-- set plan_cache_mode = force_custom_plan\n", 1),
         PUBLIC_HEAD),
        ("api_not_definer", True, lambda b: b.replace("security definer\n", "", 1), API_HEAD),
    ), ids=["search_path_gone", "plan_cache_as_comment", "api_not_definer"])
    def test_head(self, mig, name, api, mutate, must):
        block = fn_block(mig, api)
        broken = mutate(block)
        assert broken != block, name
        assert head_defects(broken, must), name


# ── 4. 파일 단위 — 순서 · 권한 · 새 함수 0 ───────────────────────────────────


class TestFile:
    def test_order(self, mig):
        bad = file_order_defects(mig)
        assert not bad, " / ".join(bad)

    def test_grants(self, mig):
        bad = grant_defects(mig)
        assert not bad, " / ".join(bad)

    def test_only_search_buildings_is_created(self, mig):
        assert created_functions(mig) == ["api.search_buildings", "search_buildings"]

    def test_allowlist_total_is_thirty_two_without_this_migration_adding_any(self):
        """새 함수가 없으니 공개 호출 허용 총계(읽기 4 + 호출)는 32 그대로(이 마이그레이션은 더하지 않는다) — 바뀌면 이 PR 범위 밖이다.

        ⓘ 2026-10-12a(업종 비중 비교 · 물결 2-3)가 api.list_industry_median 하나를 더해 31, 2026-10-13a(중분류 · 물결 2-3b)가
        api.list_industry_median_m 하나를 더해 32 가 됐다 — 이 마이그레이션은 여전히 새 공개 호출 0 이다(늘어난 둘은 그 PR 몫 ·
        그 목록은 tests/test_post_load.py 가 통째로 대조한다).
        """
        # ⓘ 2026-10-18a(결정 0041)가 api.list_price_bands·api.list_price_gate 를 지워 32 → 30(이 마이그레이션 몫 아님).
        # ⓘ 2026-10-24a(결정 0038 V4)가 api.list_floor_industry 를 더해 30 → 31(이 마이그레이션 몫 아님).
        # ⓘ 2026-10-24b(결정 0038 V5)가 api.list_rent_stat_history 를 더해 31 → 32(이 마이그레이션 몫 아님).
        # ⓘ 2026-10-25a(결정 0038 V6)가 api.list_district_openclose_all 을 더해 32 → 33(이 마이그레이션 몫 아님).
        # ⓘ 2026-10-29a(결정 0044)가 api.get_daejeon_dong_closure 를 더해 33 → 34(이 마이그레이션 몫 아님).
        assert len(post_load.ANON_READABLE_ALLOWLIST) + len(post_load.ANON_CALLABLE_ALLOWLIST) == 34
        assert "api.list_industry_median" in post_load.ANON_CALLABLE_ALLOWLIST
        assert "api.list_industry_median_m" in post_load.ANON_CALLABLE_ALLOWLIST
        assert "api.search_buildings" in post_load.ANON_CALLABLE_ALLOWLIST

    def test_header_lists_the_order_and_checks(self, mig):
        head = mig[:mig.index("set lock_timeout")]
        for needle in ("ACCESS EXCLUSIVE", "DB 먼저", "--building-only", "PGRST204",
                       "적용 뒤 확인", "되돌리기", "post_load.py --check"):
            assert needle in head, needle


class TestFileMutations:
    @pytest.mark.parametrize("name,mutate", (
        ("lock_after_begin", lambda s: s.replace("set lock_timeout = '2s';\n", "", 1)
         .replace("\nbegin;\n", "\nbegin;\nset lock_timeout = '2s';\n", 1)),
        ("api_view_before_public", lambda s: s.replace(
            "create or replace view api.v_floor_stack as select * from public.v_floor_stack;\n", "", 1)
         .replace("create or replace view v_floor_stack as\n",
                  "create or replace view api.v_floor_stack as select * from public.v_floor_stack;\n"
                  "create or replace view v_floor_stack as\n", 1)),
        ("api_building_gone", lambda s: s.replace(
            "create or replace view api.building         as select * from public.building;\n", "", 1)),
        ("notify_before_commit", lambda s: s.replace("\nnotify pgrst, 'reload schema';\n", "\n", 1)
         .replace("\ncommit;\n", "\nnotify pgrst, 'reload schema';\ncommit;\n", 1)),
        ("public_dropped_first", lambda s: s.replace(
            "drop function if exists api.search_buildings(text, int, text);\n"
            "drop function if exists search_buildings(text, int, text);\n",
            "drop function if exists search_buildings(text, int, text);\n"
            "drop function if exists api.search_buildings(text, int, text);\n", 1)),
    ), ids=["lock_after_begin", "api_view_before_public", "api_building_gone", "notify_before_commit",
            "public_dropped_first"])
    def test_order_detector_bites(self, mig, name, mutate):
        broken = mutate(mig)
        assert broken != mig, name
        assert file_order_defects(broken), name

    @pytest.mark.parametrize("name,mutate", (
        ("public_fn_grant", lambda s: s.replace(
            "\ncommit;\n", "\ngrant execute on function search_buildings(text, int, text) to anon;\ncommit;\n", 1)),
        ("public_table_grant_upper", lambda s: s.replace(
            "\ncommit;\n", "\nGRANT SELECT ON TABLE public.building TO anon;\ncommit;\n", 1)),
        ("api_building_to_anon", lambda s: s.replace(
            "on api.building         to service_role;", "on api.building         to service_role, anon;", 1)),
        ("twin_grant_removed", lambda s: s.replace(
            "grant execute on function api.search_buildings(text, int, text)  to anon, authenticated;\n", "", 1)),
        ("api_view_revoke_after_grant", lambda s: s.replace(
            "revoke all on api.v_floor_stack     from public, anon, authenticated;\n", "", 1)
         .replace("grant select on api.v_floor_stack     to anon, authenticated;\n",
                  "grant select on api.v_floor_stack     to anon, authenticated;\n"
                  "revoke all on api.v_floor_stack     from public, anon, authenticated;\n", 1)),
    ), ids=["public_fn_grant", "public_table_grant_upper", "api_building_to_anon", "twin_grant_removed",
            "api_view_revoke_after_grant"])
    def test_grant_detector_bites(self, mig, name, mutate):
        broken = mutate(mig)
        assert broken != mig, name
        assert grant_defects(broken), name

    def test_commented_grant_is_not_a_grant(self, mig):
        text = mig.replace("\ncommit;\n", "\n-- grant select on building to anon;\ncommit;\n", 1)
        assert not grant_defects(text)


# ── ② 실행 가드 (로컬 PostgreSQL 이 있을 때만) ──────────────────────────────

SHIM = """
do $r$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role; end if;
end $r$;
create table parcel (pnu char(19) primary key, geom text, road_addr text, road_contact text,
                     sido_nm text, sigungu_nm text, emd_nm text, jibun text);
create table building (
  bld_id text primary key, pnu char(19) not null, dong_nm text, bld_nm text,
  total_area_m2 numeric(12,2), ground_floors smallint, under_floors smallint, approve_date date,
  main_use text, bcr numeric(10,2), far numeric(7,2), parking_cnt integer,
  is_jiphap boolean default false, updated_at timestamptz default now(),
  display_nm text, nm_key text);
create table building_floor (bld_id text, floor_no smallint);
create table v_building_floor_stack (bld_id text, pnu char(19), floor_no smallint, floor_label text,
  floor_area_m2 numeric, floor_area_gross_m2 numeric, segment_cnt int, main_use text, uses jsonb);
create table unit_business (pnu char(19), floor_no smallint, snapshot_ym char(6), biz_name text, cat_s_nm text);
create table snapshot_release (id int primary key, loaded_ym char(6), published_ym char(6));
create table mv_search_parcel (pnu char(19), sigungu_code char(5), road_addr text, road_addr_key text,
  jibun_addr_key text, sido_nm text, sigungu_nm text, emd_nm text, jibun text);
create function st_y(g text) returns double precision language sql immutable as 'select 37.5::double precision';
create function st_x(g text) returns double precision language sql immutable as 'select 127.0::double precision';
create function search_key(t text) returns text language sql immutable
  as 'select nullif(lower(replace(t, '' '', '''')), '''')';
create function search_scope_limit() returns int language sql immutable as 'select 6000';
create function parcel_jibun_addr(a text, b text, c text, d text) returns text language sql immutable
  as 'select concat_ws('' '', a, b, c, d)';
create view api.building as select * from public.building;
insert into snapshot_release values (1, '202606', '202606');
insert into parcel values ('1168010100108230004', 'G', '테헤란로 1', '정문', '서울특별시', '강남구', '역삼동', '823-4');
insert into mv_search_parcel values ('1168010100108230004', '11680', '테헤란로 1', '테헤란로1', '역삼동823-4',
  '서울특별시', '강남구', '역삼동', '823-4');
insert into building (bld_id, pnu, bld_nm, parking_cnt, is_jiphap, display_nm, nm_key, main_use)
  values ('B1', '1168010100108230004', '테스트타워', 120, true, '테스트타워', '테스트타워', '판매시설');
insert into building_floor values ('B1', 1), ('B1', 2);
insert into v_building_floor_stack values
  ('B1', '1168010100108230004', 1, '1층', 100, 110, 1, '근린생활시설', '[]'),
  ('B1', '1168010100108230004', 2, '2층', 100, 110, 1, '업무시설', '[]');
insert into unit_business values ('1168010100108230004', 1, '202606', '카페', '카페');
"""


def _prestate_sql():
    """적용 **전** 라이브 모양 — 옛 v_floor_stack(10-07a) · 그 쌍둥이 · 16칸 검색(10-09a) · 그 쌍둥이."""
    prev_view, prev_search = read(PREV_VIEW), read(PREV_SEARCH)
    return "\n".join([
        view_block(prev_view),
        "create view api.v_floor_stack as select * from public.v_floor_stack;",
        fn_block(prev_search, False),
        fn_block(prev_search, True),
    ])


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


def _fresh(conn):
    c = conn.cursor()
    c.execute("drop schema if exists api cascade; drop schema if exists public cascade;"
              " create schema public; create schema api;")
    c.execute(SHIM)
    c.execute(_prestate_sql())
    return c


@pytest.fixture(scope="module")
def cur(pg):
    """흉내 판(적용 전 모양) 위에 이 마이그레이션 **파일 통째**를 돌린 뒤의 커서."""
    c = _fresh(pg)
    c.execute(read(MIGRATION))
    return c


def _cols(cur, schema, table):
    cur.execute("select column_name, data_type from information_schema.columns "
                "where table_schema = %s and table_name = %s order by ordinal_position", (schema, table))
    return cur.fetchall()


class TestRealRun:
    def test_building_gets_eight_columns_at_the_end(self, cur):
        cols = _cols(cur, "public", "building")
        assert cols[-8:] == list(NEW_COLS)   # information_schema 의 형 이름이 NEW_COLS 표기와 같다
        assert cols[-9][0] == "nm_key", "기존 칸 뒤에 붙는다"

    def test_api_building_shows_them(self, cur):
        assert [n for n, _ in _cols(cur, "api", "building")[-8:]] == [n for n, _ in NEW_COLS]

    def test_loader_path_upserts_through_api_building(self, cur):
        """적재기 길 — api.building 으로 on conflict upsert(merge-duplicates 와 같은 꼴)가 새 칸을 받는다."""
        cur.execute(
            "insert into api.building (bld_id, pnu, elevator_ride, elevator_emgen, ho_cnt, strct_nm, "
            "seismic_design, seismic_ability, energy_grade, green_grade) "
            "values ('B1', '1168010100108230004', 2, 1, 0, '철근콘크리트구조', true, null, '1+', null) "
            "on conflict (bld_id) do update set elevator_ride = excluded.elevator_ride, "
            "elevator_emgen = excluded.elevator_emgen, ho_cnt = excluded.ho_cnt, "
            "strct_nm = excluded.strct_nm, seismic_design = excluded.seismic_design, "
            "seismic_ability = excluded.seismic_ability, energy_grade = excluded.energy_grade, "
            "green_grade = excluded.green_grade")
        cur.execute("select elevator_ride, elevator_emgen, ho_cnt, strct_nm, seismic_design, energy_grade, "
                    "parking_cnt from building where bld_id = 'B1'")
        assert cur.fetchone() == (2, 1, 0, "철근콘크리트구조", True, "1+", 120)

    def test_api_floor_stack_tail_and_no_hidden(self, cur):
        names = [n for n, _ in _cols(cur, "api", "v_floor_stack")]
        assert tuple(names[-len(VIEW_TAIL):]) == VIEW_TAIL
        assert names[-len(VIEW_TAIL) - 1] == "lng"
        assert not set(HIDDEN) & set(names)

    def test_floor_stack_rows_carry_the_values(self, cur):
        # bld_main_use 는 건물 주용도(판매시설)다 — 층 줄의 main_use(근린생활시설·업무시설)와 다른 칸.
        cur.execute("select floor_no, elevator_ride, ho_cnt, seismic_design, main_use, bld_main_use "
                    "from api.v_floor_stack where bld_id = 'B1' order by floor_no")
        assert cur.fetchall() == [(1, 2, 0, True, "근린생활시설", "판매시설"),
                                  (2, 2, 0, True, "업무시설", "판매시설")]

    def test_search_returns_the_tail_with_types(self, cur):
        cur.execute("select bld_id, parking_cnt, ho_cnt, elevator_ride, elevator_emgen, bld_main_use, "
                    "pg_typeof(ho_cnt)::text, pg_typeof(elevator_ride)::text, pg_typeof(bld_main_use)::text "
                    "from api.search_buildings('테스트', 25, '11680')")
        assert cur.fetchall() == [("B1", 120, 0, 2, 1, "판매시설", "integer", "smallint", "text")]

    def test_twin_works_with_an_empty_search_path(self, cur):
        cur.execute("set search_path to ''")
        try:
            cur.execute("select count(*) from api.search_buildings('테스트', 25, null)")
            assert cur.fetchone() == (1,)
        finally:
            cur.execute("reset search_path")

    def test_grants_land_where_meant(self, cur):
        cur.execute("select has_function_privilege('anon', 'api.search_buildings(text, int, text)', 'execute'), "
                    "has_function_privilege('anon', 'public.search_buildings(text, int, text)', 'execute'), "
                    "has_table_privilege('anon', 'api.v_floor_stack', 'select'), "
                    "has_table_privilege('anon', 'api.building', 'select'), "
                    "has_table_privilege('service_role', 'api.building', 'insert')")
        assert cur.fetchone() == (True, False, True, False, True)


def _floor_stack_main_use_expr(sql):
    """v_floor_stack 정의 안에서 `… as bld_main_use` 의 왼쪽 식을 돌려준다(없으면 None).

    못 보는 것: 별칭 `b` 가 정말 building 인지는 안 본다(정의의 `from … building b` 는 형제 시험이 본다).
    """
    m = re.search(r"create or replace view v_floor_stack as(.*?);", sql, re.S | re.I)
    if not m:
        return None
    hit = re.search(r"([\w.]+)\s+as\s+bld_main_use\b", m.group(1), re.I)
    return hit.group(1) if hit else None


@pytest.mark.parametrize("path", [MIGRATION, SCHEMA], ids=["mig", "schema"])
def test_floor_stack_main_use_comes_from_building(path):
    # 층 행의 주용도(s.main_use)를 쓰면 주상복합 아래층 '근린생활시설'이 건물 주용도로 둔갑해 아파트 대장 호수가 보인다.
    # 로컬 PostgreSQL 실행 시험만 이것을 잡아(CI 엔 PostgreSQL 이 없다) 글자로도 막는다(2026-10-12 재검사관 🟡-2).
    assert _floor_stack_main_use_expr(read(path)) == "b.main_use"


def test_floor_stack_main_use_guard_catches_floor_alias():
    # 양성 대조 — 흔한 꼴과 변형 꼴(대문자 AS · 줄바꿈)을 같은 함수로 잡는다.
    good = read(MIGRATION)
    assert _floor_stack_main_use_expr(good.replace("b.main_use as bld_main_use", "s.main_use as bld_main_use")) == "s.main_use"
    assert _floor_stack_main_use_expr(good.replace("b.main_use as bld_main_use", "s.main_use\n  AS bld_main_use")) == "s.main_use"


def test_real_run_mismatched_return_type_is_caught(pg):
    """양성 대조 — select 식의 형과 반환 칸 형이 어긋난 사본은 부를 때 죽는다(글자 가드가 못 보는 꼴)."""
    psycopg2 = pytest.importorskip("psycopg2")
    c = _fresh(pg)
    broken = read(MIGRATION).replace("    bo.ho_cnt, bo.elevator_ride, bo.elevator_emgen,\n",
                                     "    bo.ho_cnt::text, bo.elevator_ride, bo.elevator_emgen,\n", 1)
    assert broken != read(MIGRATION)
    c.execute(broken)
    with pytest.raises(psycopg2.Error):
        c.execute("select * from api.search_buildings('테스트', 25, '11680')")
    # ⓘ 판을 새로 깔았으므로 이 시험은 파일 맨 끝에 둔다(위 TestRealRun 의 모듈 커서 판을 덮어쓴다).
