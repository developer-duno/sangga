# -*- coding: utf-8 -*-
"""표를 통째로 잠그는 마이그레이션은 `set lock_timeout` 을 begin 앞에 두는가 — 전 파일 가드.

왜 (레포 규칙 2026-09-27d · CLAUDE.md 「잠금을 잡는 DDL」)
  ACCESS EXCLUSIVE 는 읽기(ACCESS SHARE)까지 막는 가장 센 잠금이다. 그 잠금을 기다리는 문장이
  하나 줄을 서면, **그 뒤에 온 화면 조회가 전부 그 뒤에 줄을 선다** — 오래 도는 조회 하나가 표를
  쥐고 있으면 마이그레이션이 그것을 기다리는 동안 사이트 전체가 멈춘다. 그래서 기다림의 상한을
  `set lock_timeout` 으로 자르는데, 그 설정은 **세션 설정**이어야 하고(`set local` 은 begin 안에서만
  살아 begin 앞에 둘 수 없다) **첫 `begin;` 앞**에 있어야 한다(트랜잭션이 실패해 되돌아가도
  설정이 남고, 덩어리의 첫 문장부터 적용된다).
  지금까지는 마이그레이션마다 개별 시험(test_district_name_storage · test_rent_floor_migration ·
  test_arch_permit_migration)이 자기 파일만 지켰다 — 새 파일이 그 규칙을 잊으면 아무도 몰랐다.
  이 시험은 `supabase/migrations/*.sql` **전부**를 훑는다.

무엇을 ACCESS EXCLUSIVE 로 보나 — 공식 문서에 그렇다고 **적힌** 것만 (PostgreSQL 17)
  · https://www.postgresql.org/docs/17/explicit-locking.html (13.3 표 「ACCESS EXCLUSIVE」)
      "Acquired by the DROP TABLE, TRUNCATE, REINDEX, CLUSTER, VACUUM FULL, and REFRESH MATERIALIZED
      VIEW (without CONCURRENTLY) commands. Many forms of ALTER INDEX and ALTER TABLE also acquire a
      lock at this level. This is also the default lock mode for LOCK TABLE statements that do not
      specify a mode explicitly."  (REINDEX CONCURRENTLY 는 같은 표에서 SHARE UPDATE EXCLUSIVE)
  · https://www.postgresql.org/docs/17/sql-altertable.html
      "An ACCESS EXCLUSIVE lock is acquired unless explicitly noted." — 가볍다고 적힌 것만 뺀다:
      SET STATISTICS · SET (fillfactor·toast.*·autovacuum_*·parallel_workers) · VALIDATE CONSTRAINT ·
      CLUSTER ON / SET WITHOUT CLUSTER (SHARE UPDATE EXCLUSIVE) · ADD FOREIGN KEY ·
      ENABLE/DISABLE TRIGGER (SHARE ROW EXCLUSIVE). 한 문장에 여럿이면 가장 센 것.
      RENAME 은 따로 적힌 것이 없어 기본값(ACCESS EXCLUSIVE) — ENABLE ROW LEVEL SECURITY·SET STORAGE·
      ADD COLUMN·ALTER COLUMN TYPE 도 같다.
  · https://www.postgresql.org/docs/17/sql-alterindex.html
      "An ACCESS EXCLUSIVE lock is held unless explicitly noted." · "Renaming an index acquires a
      SHARE UPDATE EXCLUSIVE lock." → ALTER INDEX … RENAME 만 뺀다.
  · https://www.postgresql.org/docs/17/sql-dropindex.html
      "A normal DROP INDEX acquires an ACCESS EXCLUSIVE lock on the table" — CONCURRENTLY 는 뺀다.
  · https://www.postgresql.org/docs/17/sql-refreshmaterializedview.html — CONCURRENTLY 없는 갱신은
      그 뷰의 읽기를 막는다(위 13.3 표와 같은 말).
  ⓘ 넣지 않은 것: CREATE INDEX(SHARE — 쓰기만 막는다, sql-createindex) · CREATE INDEX CONCURRENTLY ·
    COMMENT ON (SHARE UPDATE EXCLUSIVE — 13.3 표).

"이미 있는 객체"만 본다
  같은 파일 안에서 **먼저 만든** 표·물질화 뷰·색인에 거는 문장(새 표에 `enable row level security`
  등)은 아무도 그 객체를 쓰고 있지 않으므로 줄 세우기가 없다 — 뺀다. `drop … if exists` 로 지우고
  다시 만드는 꼴의 drop 은 **있던 것**을 지우므로 센다.

옛 파일
  이 규칙(2026-09-27d)보다 먼저 라이브에 적용된 파일은 원장이라 고칠 수 없다(CLAUDE.md
  「적용된 마이그레이션 파일은 고치지 않는다」). 그런 파일은 아래 `LEGACY` 표에 **이름과 이유**로
  올린다 — 탐지를 좁혀 숨기지 않는다. 표에 있는데 이제 안 걸리는 이름(낡은 예외)도 빨강이다.

⚠️ 글자만 본다 — 라이브에서 실제로 잠금을 기다렸는지는 CI 에 DB 가 없어 못 본다.
ⓘ 도우미는 이 파일 안에서만 쓴다(시험 파일끼리 import 하지 않는 레포 관습).
"""

import glob
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS = os.path.join(ROOT, "supabase", "migrations")

# 규칙(2026-09-27d)보다 먼저 적용된 원장 — 고칠 수 없어 이름으로 뺀다. 이유는 걸리는 문장.
LEGACY = {
    "2026-08-08_public_read_policy.sql":
        "있던 표 11개에 alter table … enable row level security (규칙 전 · 원장)",
    "2026-08-11c_search_ignore_spaces.sql":
        "옛 검색 색인 3개를 drop index(concurrently 아님) (규칙 전 · 원장)",
    "2026-08-11d_widen_bcr.sql":
        "building 에 alter column … type (규칙 전 · 원장)",
    "2026-08-11e_search_key_stored.sql":
        "building·parcel 에 add column + 옛 색인 drop index (규칙 전 · 원장)",
    "2026-08-13b_view_and_index_hygiene.sql":
        "idx_tx_pnu 를 drop index(concurrently 아님) (규칙 전 · 원장)",
    "2026-08-13c_display_nm_stored.sql":
        "building 에 add column (규칙 전 · 원장)",
    "2026-08-14b_district_source_and_fn_sources.sql":
        "district 에 add column (규칙 전 · 원장)",
    "2026-08-22a_coverage_stats_scope.sql":
        "idx_ub_snapshot_floor 를 drop index(concurrently 아님) (규칙 전 · 원장)",
    "2026-08-22c_industry_mix.sql":
        "idx_ub_pnu 를 drop index(concurrently 아님) (규칙 전 · 원장)",
    "2026-09-09c_search_stores.sql":
        "idx_ub_name 을 drop index(concurrently 아님) (규칙 전 · 원장)",
}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


RE_DOLLAR = re.compile(r"\$(?:[A-Za-z_]\w*)?\$")


def statements(sql):
    """SQL 을 문장 목록으로 자른다(소문자 · 공백 한 칸 · 순서 유지).

    걷는 것: `--` 주석 · `/* */` 주석 · `$tag$ … $tag$` 본문 통째(함수 본문과 `do` 블록 —
    함수 본문은 나중에 돌고, `do` 블록 안 plpgsql 의 `begin` 을 트랜잭션 시작으로 읽지 않게).
    작은따옴표 문자열은 글자를 남기되 그 안의 `;` 만 공백으로(값 `'0'` 을 읽기 위해).

    못 보는 것:
      · `do $$ … $$` 블록 안·동적 SQL(`execute '…'`) 안의 DDL — 본문째 걷는다.
      · `E'…\\''` 처럼 백슬래시로 따옴표를 감춘 문자열(`''` 만 안다) · 큰따옴표 이름 안의 `;`.
      · psql 메타 명령(`\\set` 등) — 지금 마이그레이션에는 0건.
    """
    out, buf, i, n = [], [], 0, len(sql)
    while i < n:
        c = sql[i]
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j
            continue
        if sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = n if j < 0 else j + 2
            buf.append(" ")
            continue
        if c == "'":
            j = i + 1
            while True:
                k = sql.find("'", j)
                if k < 0:
                    j = n
                    break
                if sql.startswith("''", k):
                    j = k + 2
                    continue
                j = k + 1
                break
            buf.append(sql[i:j].replace(";", " "))
            i = j
            continue
        if c == "$" and not (i > 0 and (sql[i - 1].isalnum() or sql[i - 1] == "_")):
            m = RE_DOLLAR.match(sql, i)
            if m:
                k = sql.find(m.group(0), m.end())
                i = n if k < 0 else k + len(m.group(0))
                buf.append(" $body$ ")
                continue
        if c == ";":
            out.append(" ".join("".join(buf).split()).lower())
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    out.append(" ".join("".join(buf).split()).lower())
    return [s for s in out if s]


def obj_name(raw):
    """`public."District"(col)` → `district`. 스키마는 public 만 걷는다(api.x 는 그대로)."""
    name = raw.split("(", 1)[0].replace('"', "").strip()
    return name[len("public."):] if name.startswith("public.") else name


def split_top(text):
    """괄호 밖 쉼표로 자른다(`numeric(10,2)` 안 쉼표는 안 자른다)."""
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur).strip())
    return [p for p in parts if p]


RE_LIGHT_SUB = re.compile(
    r"^(?:alter (?:column )?\S+ set statistics\b"
    r"|validate constraint\b"
    r"|add (?:constraint \S+ )?foreign key\b"
    r"|(?:enable|disable) (?:always |replica )?trigger\b"
    r"|cluster on\b"
    r"|set without cluster\b)")
RE_LIGHT_PARAM = re.compile(r"^(?:fillfactor|toast\.\w+|autovacuum_\w+|parallel_workers)$")


def alter_table_sub_is_light(sub):
    """ALTER TABLE 하위 명령 하나가 문서상 ACCESS EXCLUSIVE 보다 가벼운가."""
    if RE_LIGHT_SUB.match(sub):
        return True
    m = re.match(r"^set \((.*)\)$", sub)
    if m:
        keys = [p.split("=", 1)[0].strip() for p in split_top(m.group(1))]
        return bool(keys) and all(RE_LIGHT_PARAM.match(k) for k in keys)
    return False


def names(text):
    return [obj_name(x) for x in split_top(text)]


def ae_targets(stmt):
    """한 문장이 ACCESS EXCLUSIVE 를 잡는 대상 이름들. 안 잡으면 [].

    못 보는 것(공식 문서에 잠금 수준이 **적혀 있지 않아** 넣지 않은 것):
      · DROP VIEW · DROP MATERIALIZED VIEW · CREATE OR REPLACE VIEW · ALTER VIEW ·
        ALTER MATERIALIZED VIEW · CREATE/ALTER/DROP POLICY · DROP FUNCTION 이 기대는 객체.
        (구현상으로는 뷰·정책 일부가 센 잠금을 잡는다고 알려져 있지만 문서 근거가 없다.)
      · ALTER TABLE … SET (…) 에서 `reset (…)` 꼴은 문서가 SET 만 말해 전부 센 쪽으로 본다
        (가벼운데 걸리는 쪽 — 놓치는 쪽이 아니다).
    """
    s = stmt
    m = re.match(r"^drop table (?:if exists )?(.+?)(?: cascade| restrict)?$", s)
    if m:
        return names(m.group(1))
    m = re.match(r"^truncate (?:table )?(?:only )?(.+?)"
                 r"(?: (?:restart|continue) identity)?(?: cascade| restrict)?$", s)
    if m:
        return names(m.group(1))
    m = re.match(r"^reindex (?:\([^)]*\) )?(?:index|table|schema|database|system) "
                 r"(concurrently )?(\S+)", s)
    if m:
        return [] if m.group(1) else [obj_name(m.group(2))]
    m = re.match(r"^cluster\b(?: \([^)]*\))?(?: verbose)?(?: (\S+))?", s)
    if m:
        return [obj_name(m.group(1))] if m.group(1) else ["*"]
    m = re.match(r"^vacuum(?: (\([^)]*\)))?((?: (?:full|freeze|verbose|analyze))*)(?: (.+))?$", s)
    if m:
        opts = m.group(1) or ""
        full = bool(re.search(r"\bfull\b(?! (?:false|off|0)\b)", opts)) \
            or " full" in (m.group(2) or "")
        if not full:
            return []
        return names(m.group(3)) if m.group(3) else ["*"]
    m = re.match(r"^refresh materialized view (concurrently )?(\S+)", s)
    if m:
        return [] if m.group(1) else [obj_name(m.group(2))]
    m = re.match(r"^lock (?:table )?(?:only )?(.+?)(?: in (.+?) mode)?(?: nowait)?$", s)
    if m:
        mode = m.group(2)
        return names(m.group(1)) if mode in (None, "access exclusive") else []
    m = re.match(r"^drop index (concurrently )?(?:if exists )?(.+?)(?: cascade| restrict)?$", s)
    if m:
        return [] if m.group(1) else names(m.group(2))
    m = re.match(r"^alter table (?:if exists )?(?:only )?(\S+) (.+)$", s)
    if m:
        subs = split_top(m.group(2))
        return [] if subs and all(alter_table_sub_is_light(x) for x in subs) \
            else [obj_name(m.group(1))]
    m = re.match(r"^alter index (?:if exists )?(\S+) (.+)$", s)
    if m:
        return [] if m.group(2).startswith("rename ") else [obj_name(m.group(1))]
    return []


RE_CREATE_REL = re.compile(
    r"^create (?:or replace )?(?:(?:global |local )?(?:temporary |temp )|unlogged )?"
    r"(?:table|materialized view) (?:if not exists )?([^\s(]+)")
RE_CREATE_IDX = re.compile(
    r"^create (?:unique )?index (?:concurrently )?(?:if not exists )?(\S+) on ")


def created_name(stmt):
    m = RE_CREATE_REL.match(stmt) or RE_CREATE_IDX.match(stmt)
    return obj_name(m.group(1)) if m else None


RE_SESSION_LT = re.compile(r"^set (?:session )?lock_timeout(?: to | ?= ?)(.+)$")


def is_session_lock_timeout(stmt):
    """세션 수준 `set lock_timeout = <0 아닌 값>` 인가. `set local` 은 아니다(begin 안에서만 산다)."""
    m = RE_SESSION_LT.match(stmt)
    if not m:
        return False
    val = m.group(1).strip().strip("'").strip()
    return not re.fullmatch(r"0(?:\s*(?:us|ms|s|min|h|d))?|default", val)


def is_begin(stmt):
    return bool(re.match(r"^(?:begin|start transaction)\b", stmt))


def lock_timeout_problems(sql):
    """한 파일의 문제 목록. 비면 통과.

    규칙: 이미 있는 객체에 ACCESS EXCLUSIVE 를 거는 문장이 하나라도 있으면, 세션 수준
    `set lock_timeout` 이 **첫 `begin;`** 과 **첫 그런 문장** 둘 다보다 앞에 있어야 한다.

    못 보는 것:
      · lock_timeout 을 건 뒤 `reset lock_timeout`·`set lock_timeout = 0` 으로 다시 푸는 것
        (개별 시험 test_district_name_storage 만 그 꼴을 본다).
      · 값이 너무 긴 것(예 '10min') — 값의 크기는 판정하지 않는다.
      · `ae_targets`·`statements` 머리말의 못 보는 것 전부.
    """
    stmts = statements(sql)
    created = set()
    first_ae = first_begin = first_lt = None
    for idx, st in enumerate(stmts):
        if first_lt is None and is_session_lock_timeout(st):
            first_lt = idx
        if first_begin is None and is_begin(st):
            first_begin = idx
        if first_ae is None and any(t not in created for t in ae_targets(st)):
            first_ae = (idx, st)
        name = created_name(st)
        if name:
            created.add(name)
    if first_ae is None:
        return []
    need = min(x for x in (first_ae[0], first_begin) if x is not None)
    if first_lt is None:
        return ["표를 통째로 잠그는 문장이 있는데 세션 `set lock_timeout` 이 없습니다: "
                + first_ae[1][:80]]
    if first_lt > need:
        return ["세션 `set lock_timeout` 이 첫 `begin;`·첫 잠금 문장보다 뒤에 있습니다: "
                + first_ae[1][:80]]
    return []


def migration_files():
    return sorted(glob.glob(os.path.join(MIGRATIONS, "*.sql")))


# ---------------------------------------------------------------- 본 가드

def test_there_are_migrations_to_scan():
    assert len(migration_files()) >= 70, "마이그레이션 폴더를 못 찾았거나 비었습니다"


def test_every_migration_sets_lock_timeout_before_exclusive_ddl():
    bad = []
    for path in migration_files():
        name = os.path.basename(path)
        if name in LEGACY:
            continue
        for p in lock_timeout_problems(read(path)):
            bad.append("{}: {}".format(name, p))
    assert not bad, "\n".join(bad)


def test_legacy_entries_still_hit():
    """예외 표에 있는데 파일이 없거나 이제 안 걸리면 낡은 예외 — 표에서 지운다."""
    stale = []
    for name in LEGACY:
        path = os.path.join(MIGRATIONS, name)
        if not os.path.exists(path):
            stale.append("{}: 파일 없음".format(name))
        elif not lock_timeout_problems(read(path)):
            stale.append("{}: 이제 안 걸린다".format(name))
    assert not stale, "\n".join(stale)


def test_legacy_files_are_older_than_the_rule():
    """원장 예외는 규칙(2026-09-27d)보다 **먼저** 적용된 파일만 — 새 파일을 표에 올려 숨기지 않는다."""
    late = [n for n in LEGACY if n[:11] >= "2026-09-27d"]
    assert not late, late


def test_rule_followers_are_seen_and_pass():
    """규칙을 따른 실제 파일은 **잠금 문장이 잡히면서** 통과한다(헛통과가 아님을 확인)."""
    for name in ("2026-09-27d_district_name_storage.sql", "2026-10-04a_rent_floor_rent.sql"):
        sql = read(os.path.join(MIGRATIONS, name))
        assert any(ae_targets(s) for s in statements(sql)), name
        assert lock_timeout_problems(sql) == [], name


# ---------------------------------------------------------------- 양성 대조(같은 함수를 지난다)

OK_BASIC = "set lock_timeout = '2s';\n\nbegin;\nalter table rent_stat add column x int;\ncommit;\n"


@pytest.mark.parametrize("sql", [
    OK_BASIC,
    # 변형: 대문자 · `to` · 세션 키워드
    "SET SESSION LOCK_TIMEOUT TO '2s';\nBEGIN;\nALTER TABLE Rent_Stat ADD COLUMN x int;\nCOMMIT;\n",
    # begin 없는 자동 커밋 파일: 잠금 문장 앞이면 된다
    "set lock_timeout = '2s';\ndrop index if exists idx_a;\n",
    # 같은 파일에서 만든 표에 거는 것은 이미 있는 객체가 아니다
    "begin;\ncreate table t_new (a int);\nalter table t_new enable row level security;\ncommit;\n",
    # 가벼운 잠금들
    "begin;\nalter table t validate constraint c, alter column a set statistics 100;\ncommit;\n",
    "begin;\nalter index idx_a rename to idx_b;\ncommit;\n",
    "drop index concurrently if exists idx_a;\nrefresh materialized view concurrently mv_a;\n",
    "begin;\nalter table t set (fillfactor = 90, autovacuum_enabled = false);\ncommit;\n",
    "vacuum (analyze) district;\n",
    # 주석·문자열·함수 본문 안의 글자는 문장이 아니다
    "-- begin;\n-- alter table t add column x int;\nselect 1;\n",
    "comment on table t is 'drop table t; begin;';\n",
    "create function f() returns void language plpgsql as $$\nbegin\n"
    "  execute 'select 1';\nend $$;\n",
])
def test_detector_passes(sql):
    assert lock_timeout_problems(sql) == []


@pytest.mark.parametrize("sql", [
    # 흔한 꼴: lock_timeout 을 begin 뒤로
    "begin;\nset lock_timeout = '2s';\nalter table rent_stat add column x int;\ncommit;\n",
    # 변형: 대문자 BEGIN · 그 뒤 SET
    "BEGIN;\nSET LOCK_TIMEOUT = '2s';\nALTER TABLE District ALTER COLUMN a SET STORAGE MAIN;\nCOMMIT;\n",
    # set local 은 세션 설정이 아니다
    "begin;\nset local lock_timeout = '2s';\nalter table t add column x int;\ncommit;\n",
    # 아예 없음
    "begin;\nalter table t add column x int;\ncommit;\n",
    # 0 은 '기다림 무한'이라 건 것이 아니다
    "set lock_timeout = '0';\nbegin;\nalter table t add column x int;\ncommit;\n",
    # 주석 안 begin 은 무시하고 진짜 begin 뒤 set 을 잡는다
    "-- set lock_timeout = '2s';\nbegin;\nset lock_timeout = '2s';\ntruncate t;\ncommit;\n",
    # 다른 잠금 문장들
    "drop index if exists idx_a;\nset lock_timeout = '2s';\n",
    "begin;\ndrop table if exists t_old cascade;\ncommit;\n",
    "begin;\nrefresh materialized view mv_a;\ncommit;\n",
    "vacuum (full, analyze) district;\n",
    "vacuum full district;\n",
    "begin;\nlock table t;\ncommit;\n",
    "begin;\nlock table t in access exclusive mode;\ncommit;\n",
    "reindex index idx_a;\n",
    "cluster t using idx_a;\n",
    "begin;\nalter index idx_a set tablespace x;\ncommit;\n",
    "begin;\nalter table t alter column a type numeric(10,2);\ncommit;\n",
    "begin;\nalter table only public.t rename to t2;\ncommit;\n",
    # 가벼운 것과 센 것이 섞이면 센 쪽
    "begin;\nalter table t validate constraint c, add column x int;\ncommit;\n",
    # 다른 표를 만든 것은 이 표를 새것으로 만들지 않는다
    "begin;\ncreate table t_new (a int);\nalter table t_old enable row level security;\ncommit;\n",
    # drop 하고 다시 만드는 꼴: drop 은 있던 것을 지운다
    "begin;\ndrop table if exists t;\ncreate table t (a int);\ncommit;\n",
])
def test_detector_catches(sql):
    assert lock_timeout_problems(sql), sql


def test_mutation_real_file_lock_timeout_after_begin_is_red():
    """실제 파일(2026-10-04a)에서 lock_timeout 을 begin 뒤로 옮기면 빨강."""
    text = read(os.path.join(MIGRATIONS, "2026-10-04a_rent_floor_rent.sql")).replace("\r\n", "\n")
    lt = "set lock_timeout = '2s';\n\nbegin;\n"
    assert lt in text, "전제: lock_timeout 이 begin 바로 앞"
    assert lock_timeout_problems(text.replace(lt, "begin;\nset lock_timeout = '2s';\n", 1))


def test_mutation_real_file_lock_timeout_removed_is_red():
    text = read(os.path.join(MIGRATIONS, "2026-09-27d_district_name_storage.sql"))
    text = text.replace("\r\n", "\n")
    assert "set lock_timeout = '2s';" in text
    assert lock_timeout_problems(text.replace("set lock_timeout = '2s';", "", 1))
