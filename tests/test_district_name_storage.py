# -*- coding: utf-8 -*-
"""상권 표(district)의 이름 칸 둘이 본관(storage main)에 있도록 정본·마이그레이션이 말하는가.

왜 (2026-09-27, 마이그레이션 ``2026-09-27d_district_name_storage.sql``)
  district 한 줄에 큰 도형(geom)이 실려 줄이 한 쪽을 넘치면, PostgreSQL 은 저장 방식이
  extended 인 칸부터 별관(TOAST)으로 내보낸다. geom 은 이미 main 이라 뒤로 밀리고 **작은
  이름 칸**(district_nm·source_nm)이 먼저 쫓겨나, 이름을 읽을 때마다 별관을 왕복했다
  (라이브: 상권 밖 건물의 list_building_districts 10,648쪽·16ms → 바꾼 복사본 517쪽·2.5ms).

  이 성질은 **에러 없이 조용히** 사라진다 — 누가 정본에서 그 줄을 지우거나, 표를 새로 만드는
  환경에서 `add column source_nm` 보다 앞에 두면(없는 칸 → 에러) 되돌리려다 지우면, 화면은
  그대로 뜨고 느려질 뿐이다. 그래서 글자로 지킨다.

무엇을 보나
  ① 정본에 `alter table district … alter column <칸> set storage main` 이 두 칸 모두 있다.
  ② 그 문장이 `create table … district` 와 `add column … source_nm` **뒤**에 있다
     (표 성질이라 적재기 upsert 가 새로 쓰는 줄에도 저절로 적용된다 — 순서만 맞으면 된다).
  ③ 마이그레이션이 **같은 칸 집합**을 main 으로 바꾸고, 기존 줄을 **값을 새로 만드는**
     갱신(`칸 = 칸 || ''`)으로 다시 싣는다 — `칸 = 칸` 은 같은 별관 포인터를 재사용해 아무것도
     안 옮긴다(pg_temp 실측). 그 둘이 `begin;`…`commit;` 안이고, `vacuum full` 은 그 **뒤**
     (트랜잭션 안에서는 못 돈다).
  ④ geom·jsonb 칸의 저장 방식은 건드리지 않는다(요청 범위 밖).

⚠️ 글자만 본다 — 라이브에 적용됐는지는 CI 에 DB 가 없어 못 본다(적용 뒤 확인은 마이그레이션 머리말).
ⓘ 도우미는 이 파일 안에서만 쓴다(시험 파일끼리 import 하지 않는 레포 관습).
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
MIGRATION = os.path.join(
    ROOT, "supabase", "migrations", "2026-09-27d_district_name_storage.sql")

EXPECTED = {"district_nm", "source_nm"}
LOCK_TIMEOUT = "2s"

RE_ALTER_DISTRICT = re.compile(r"(?is)\balter\s+table\s+(?:if\s+exists\s+)?(?:public\.)?district\b(.*?);")
RE_SET_MAIN = re.compile(r"(?i)alter\s+column\s+(\w+)\s+set\s+storage\s+main\b")
RE_SET_ANY = re.compile(r"(?i)alter\s+column\s+(\w+)\s+set\s+storage\s+(\w+)")
RE_CREATE = re.compile(r"(?i)\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?district\s*\(")
RE_ADD_SOURCE = re.compile(r"(?i)\badd\s+column\s+(?:if\s+not\s+exists\s+)?source_nm\b")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def strip_comments(sql):
    """`--` 주석을 걷는다(줄 전체·줄 끝 모두).

    ⚠️ `'…'` 문자열 안의 `--` 도 주석으로 잘라 버린다 — schema.sql 에는 `'… --check …'` 가
    3곳(1292·1330·1332줄 근방, comment on 글) 있다. 전부 district 정의·이 alter 보다 **뒤**이고
    그 줄의 나머지 글만 잘리므로 여기 판정(district alter 의 위치·칸)은 바뀌지 않는다.
    마이그레이션 27d 에는 문자열 안 `--` 가 없다.
    """
    return "\n".join(
        line.split("--", 1)[0] for line in sql.replace("\r\n", "\n").splitlines())


def main_storage_stmts(sql):
    """district 에 set storage main 을 거는 alter 문장들: [(시작 위치, {칸…}), …]."""
    out = []
    for m in RE_ALTER_DISTRICT.finditer(sql):
        cols = {c.lower() for c in RE_SET_MAIN.findall(m.group(1))}
        if cols:
            out.append((m.start(), cols))
    return out


def final_storage(sql):
    """district 의 `set storage` 를 문서 순서대로 되짚어 칸마다 **마지막** 값: {칸: 방식}."""
    last = {}
    for m in RE_ALTER_DISTRICT.finditer(sql):
        for col, mode in RE_SET_ANY.findall(m.group(1)):
            last[col.lower()] = mode.lower()
    return last


def schema_problems(text):
    """정본을 판정해 어긋난 것을 사람이 읽을 문장 목록으로(빈 목록 = 통과)."""
    sql = strip_comments(text)
    bad = []
    stmts = main_storage_stmts(sql)
    cols = set().union(*[c for _, c in stmts]) if stmts else set()
    if cols != EXPECTED:
        bad.append("정본의 main 칸이 {} 인데 기대는 {}".format(sorted(cols), sorted(EXPECTED)))
    # 뒤에서 extended 로 되돌리는 줄이 덧붙으면 "main 문장이 있다"만으로는 못 잡는다 → 마지막 값으로.
    last = final_storage(sql)
    for col in sorted(EXPECTED):
        if last.get(col) != "main":
            bad.append("정본을 끝까지 되짚은 {} 의 저장 방식이 {!r} — main 이어야 합니다".format(
                col, last.get(col)))
    extra = sorted(set(last) - EXPECTED)
    if extra:
        bad.append("정본이 범위 밖 칸의 저장 방식을 바꿉니다: {}".format(extra))
    create = RE_CREATE.search(sql)
    add_src = RE_ADD_SOURCE.search(sql)
    if create is None or add_src is None:
        bad.append("district 정의 또는 source_nm add column 을 못 찾았습니다 — 판정기가 헛돕니다")
        return bad
    for pos, c in stmts:
        if pos < create.start():
            bad.append("set storage main {} 이 create table district 앞에 있습니다".format(sorted(c)))
        if pos < add_src.start():
            bad.append("set storage main {} 이 add column source_nm 앞에 있습니다".format(sorted(c)))
    return bad


def migration_problems(text):
    """마이그레이션을 판정한다(빈 목록 = 통과)."""
    sql = strip_comments(text)
    low = sql.lower()
    bad = []
    stmts = main_storage_stmts(sql)
    cols = set().union(*[c for _, c in stmts]) if stmts else set()
    if cols != EXPECTED:
        bad.append("마이그레이션의 main 칸이 {} 인데 기대는 {}".format(sorted(cols), sorted(EXPECTED)))

    touched = {c.lower() for c, _ in RE_SET_ANY.findall(sql)}
    if touched - EXPECTED:
        bad.append("범위 밖 칸의 저장 방식을 바꿉니다: {}".format(sorted(touched - EXPECTED)))

    upd = re.search(r"(?is)\bupdate\s+(?:public\.)?district\b(.*?);", sql)
    if upd is None:
        bad.append("기존 줄을 다시 싣는 update 가 없습니다 — 저장 방식은 새로 쓰는 줄에만 적용됩니다")
        reloaded = set()
    else:
        pairs = re.findall(r"(?i)\b(\w+)\s*=\s*(\w+)\s*\|\|\s*''", upd.group(1))
        reloaded = {a.lower() for a, b in pairs if a.lower() == b.lower()}
        if reloaded != EXPECTED:
            bad.append("값을 새로 만드는 갱신(칸 = 칸 || '')이 {} 뿐 — 기대 {}".format(
                sorted(reloaded), sorted(EXPECTED)))

    begin = re.search(r"(?m)^begin;", low)
    commit = re.search(r"(?m)^commit;", low)
    vac = re.search(r"(?m)^vacuum\s*\(\s*full", low)
    if begin is None or commit is None:
        bad.append("begin;/commit; 이 없습니다")
        return bad
    for pos, c in stmts:
        if not (begin.start() < pos < commit.start()):
            bad.append("set storage main {} 이 begin…commit 밖에 있습니다".format(sorted(c)))
    if upd is not None and not (begin.start() < upd.start() < commit.start()):
        bad.append("다시 싣는 update 가 begin…commit 밖에 있습니다")
    # set storage 는 ACCESS EXCLUSIVE 라 begin 앞에서 lock_timeout 을 걸어야 줄 세우기를 막는다.
    lt = re.search(r"(?m)^set\s+lock_timeout\b", low)
    if lt is None or lt.start() > begin.start():
        bad.append("`set lock_timeout` 이 begin; 앞에 없습니다 — alter 가 표를 통째로 잠급니다")
    else:
        val = re.match(r"set\s+lock_timeout\s*(?:=|to)\s*'([^']*)'", low[lt.start():])
        if val is None or val.group(1) != LOCK_TIMEOUT:
            bad.append("lock_timeout 값이 {!r} — {!r} 이어야 합니다(anon statement_timeout 보다 짧게)".format(
                val.group(1) if val else None, LOCK_TIMEOUT))
    # begin 부터 vacuum 까지 그 상한을 풀거나 바꾸는 문장이 끼면 vacuum full 이 무한정 줄을 세운다.
    end = vac.start() if vac is not None else len(low)
    between = re.findall(
        r"(?m)^(?:reset\s+(?:lock_timeout|all)\b|set\s+(?:local\s+|session\s+)?lock_timeout\b)",
        low[begin.start():end])
    if between:
        bad.append("begin 과 vacuum 사이에 lock_timeout 을 풀거나 바꾸는 문장 {}건".format(len(between)))
    if vac is None:
        bad.append("vacuum full 이 없습니다 — 부풀어 있는 힙(976쪽 vs 새로 담으면 ~500쪽)을 안 줄입니다")
    elif vac.start() < commit.start():
        bad.append("vacuum full 이 commit 앞에 있습니다 — 트랜잭션 안에서는 못 돕니다")
    return bad


# ── 1. 지금 나무 ────────────────────────────────────────────────────────────


def test_schema_keeps_name_columns_main():
    assert schema_problems(read(SCHEMA)) == []


def test_migration_moves_the_same_columns():
    assert migration_problems(read(MIGRATION)) == []


def test_schema_and_migration_agree():
    s = set().union(*[c for _, c in main_storage_stmts(strip_comments(read(SCHEMA)))])
    m = set().union(*[c for _, c in main_storage_stmts(strip_comments(read(MIGRATION)))])
    assert s == m == EXPECTED


# ── 2. 돌연변이 — 판정기가 헛돌지 않는가 ────────────────────────────────────

SCHEMA_STMT = ("alter table district\n"
               "  alter column district_nm set storage main,\n"
               "  alter column source_nm set storage main;\n")


def _schema_lf():
    text = read(SCHEMA).replace("\r\n", "\n")
    assert SCHEMA_STMT in text, "전제: 정본에 그 문장이 글자 그대로 있다"
    return text


def test_mutation_a_deleting_the_schema_statement_is_red():
    broken = _schema_lf().replace(SCHEMA_STMT, "", 1)
    assert schema_problems(broken), "정본 줄을 지웠는데 통과합니다"


def test_mutation_b_commenting_it_out_is_red():
    commented = "".join("-- " + line + "\n" for line in SCHEMA_STMT.splitlines())
    broken = _schema_lf().replace(SCHEMA_STMT, commented, 1)
    assert schema_problems(broken), "주석으로 죽인 줄을 '있다'고 읽습니다"


def test_mutation_c_one_column_missing_is_red():
    broken = _schema_lf().replace(
        "  alter column district_nm set storage main,\n", "", 1)
    assert schema_problems(broken), "칸 하나를 빼도 통과합니다"


def test_mutation_d_moved_before_add_column_is_red():
    text = _schema_lf().replace(SCHEMA_STMT, "", 1)
    anchor = "alter table district\n  add column if not exists source_nm text;\n"
    assert anchor in text, "전제: add column source_nm 문장"
    broken = text.replace(anchor, SCHEMA_STMT + anchor, 1)
    assert any("add column source_nm 앞" in b for b in schema_problems(broken))


def test_mutation_h_reverting_to_extended_later_is_red():
    """main 문장은 그대로 두고 **뒤에** extended 로 되돌리는 줄을 덧붙인다 → 빨강."""
    text = _schema_lf()
    revert = ("\nalter table district\n"
              "  alter column source_nm set storage extended;\n")
    broken = text.replace(SCHEMA_STMT, SCHEMA_STMT + revert, 1)
    assert any("source_nm 의 저장 방식이 'extended'" in b for b in schema_problems(broken))


MIG_UPD = "   set district_nm = district_nm || '',\n       source_nm   = source_nm || ''\n"


def _mig_lf():
    text = read(MIGRATION).replace("\r\n", "\n")
    assert MIG_UPD in text, "전제: 마이그레이션의 update 글자"
    return text


def test_mutation_e_same_pointer_update_is_red():
    """`칸 = 칸` 은 별관 포인터를 재사용해 아무것도 안 옮긴다(pg_temp 실측)."""
    broken = _mig_lf().replace(
        MIG_UPD, "   set district_nm = district_nm,\n       source_nm   = source_nm\n", 1)
    assert migration_problems(broken)


def test_mutation_f_vacuum_inside_transaction_is_red():
    text = _mig_lf()
    broken = text.replace("\ncommit;\n", "\n", 1).replace(
        "vacuum (full, analyze) district;", "vacuum (full, analyze) district;\ncommit;", 1)
    assert any("commit 앞" in b for b in migration_problems(broken))


LT_LINE = "set lock_timeout = '2s';\n\nbegin;\n"


def test_mutation_i_lock_timeout_after_begin_is_red():
    text = _mig_lf()
    assert LT_LINE in text, "전제: lock_timeout 이 begin 바로 앞"
    broken = text.replace(LT_LINE, "begin;\nset lock_timeout = '2s';\n", 1)
    assert any("begin; 앞에 없습니다" in b for b in migration_problems(broken))


def test_mutation_j_longer_lock_timeout_is_red():
    text = _mig_lf()
    assert LT_LINE in text, "전제: lock_timeout 이 begin 바로 앞"
    broken = text.replace(LT_LINE, "set lock_timeout = '5s';\n\nbegin;\n", 1)
    assert any("lock_timeout 값이 '5s'" in b for b in migration_problems(broken))


@pytest.mark.parametrize("stmt", [
    "reset lock_timeout;",
    "reset all;",
    "set lock_timeout = '0';",
    "set local lock_timeout = '0';",
])
def test_mutation_k_lifting_the_limit_before_vacuum_is_red(stmt):
    text = _mig_lf()
    anchor = "\ncommit;\n"
    assert anchor in text, "전제: commit 문장"
    broken = text.replace(anchor, anchor + "\n" + stmt + "\n", 1)
    assert any("사이에 lock_timeout" in b for b in migration_problems(broken)), stmt


def test_mutation_g_touching_geom_is_red():
    broken = _mig_lf().replace(
        "  alter column source_nm set storage main;",
        "  alter column source_nm set storage main,\n  alter column geom set storage external;", 1)
    assert any("범위 밖" in b for b in migration_problems(broken))


@pytest.mark.parametrize("path", [SCHEMA, MIGRATION])
def test_files_exist(path):
    assert os.path.exists(path)
