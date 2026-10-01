# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-01b(안 쓰는 큰 색인 5개 지우기)가 딱 그것만 하는가.

왜 이 시험이 있나 (사장님 결정 2026-10-01 "5개 전부 지우기")
--------------------------------------------------------------
10/31 분기 적재 전에 디스크 여유를 만들려고, 통계 초기화(2026-07-24) 뒤 안 쓰였거나 오래전에
쓰임이 끊긴 색인 다섯(합계 421MB)을 지운다. 색인 지우기는 **에러가 안 나고 조용히 느려지는**
종류라, 이름 하나를 잘못 적으면(살아 있는 색인을 지우면) 아무도 모르게 화면이 느려진다.
반대로 `concurrently` 가 빠지면 표 전체에 ACCESS EXCLUSIVE 잠금이 걸려 그동안 화면 읽기가 멈춘다.

무엇을 지키나
-------------
ⓐ 새 마이그레이션의 실제 문장(주석 제외)은 `set statement_timeout = '900s'` 하나 + 정확히 이 다섯
   이름의 `drop index concurrently if exists <이름>;` 다섯 줄뿐이다 — 한 줄 한 문장, 트랜잭션 없음,
   다른 drop·create·alter 없음, statement_timeout 이 첫 drop 앞
ⓑ 정본(schema.sql)에 다섯 이름의 `create index` 가 0건(주석 안의 인용은 세지 않는다)
ⓒ 머리말 되돌리기 주석의 `create index concurrently` 다섯 문장이 지우기 전 정본 원문과
   종류·표·칸·연산자 클래스까지 같고(EXPECTED_ROLLBACK), 적용 전 확인에 업종 분포 요약표의
   explain · 라이브 정의(pg_get_indexdef) · 통계 초기화 시각 · 갱신 시간 기준값 쿼리가 있다
ⓓ 돌연변이 — 위 판정기가 실제로 빨강을 내는지 사본 문자열로 확인한다(빈 집합 통과 금지)

ⓘ 도우미는 다른 시험 파일에서 import 하지 않는다 — 시험끼리 얽히면 한쪽 고장이 다른 쪽을 가린다.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
MIGRATION = os.path.join(
    ROOT, "supabase", "migrations", "2026-10-01b_drop_unused_indexes.sql")

DROPPED = (
    "idx_ub_geom",
    "idx_unit_geom",
    "idx_parcel_road_key",
    "idx_parcel_jibun_key",
    "idx_ub_cat",
)

RE_DROP_LINE = re.compile(r"(?i)^drop\s+index\s+concurrently\s+if\s+exists\s+(\w+)\s*;$")
RE_TIMEOUT_LINE = re.compile(r"(?i)^set\s+statement_timeout\s*=\s*'900s'\s*;$")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def norm(text):
    return text.replace("\r\n", "\n")


def code_lines(sql):
    """주석 줄·빈 줄을 걷어낸 실제 문장 줄."""
    out = []
    for line in norm(sql).splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        out.append(s)
    return out


def migration_problems(sql):
    """마이그레이션 본문의 문제 목록(빈 목록 = 정상)."""
    bad = []
    lines = code_lines(sql)
    if not lines:
        return ["실제 문장이 하나도 없습니다"]
    if not RE_TIMEOUT_LINE.match(lines[0]):
        bad.append("첫 문장이 `set statement_timeout = '900s';` 가 아닙니다: {}".format(lines[0]))
    names = []
    for line in lines[1:]:
        m = RE_DROP_LINE.match(line)
        if not m:
            bad.append("`drop index concurrently if exists <이름>;` 한 줄 한 문장이 아닌 줄: {}".format(line))
            continue
        names.append(m.group(1))
    if sorted(names) != sorted(DROPPED):
        bad.append("지우는 이름이 다릅니다: {} (기대 {})".format(sorted(names), sorted(DROPPED)))
    if len(names) != len(set(names)):
        bad.append("같은 이름을 두 번 지웁니다: {}".format(names))
    low = "\n".join(lines).lower()
    for word in ("begin", "commit"):
        if re.search(r"(?m)^{}\b".format(word), low):
            bad.append("`{}` 가 있습니다 — concurrently 는 트랜잭션 안에서 못 돕니다".format(word))
    return bad


def schema_problems(schema):
    """정본에 지운 다섯의 create index 가 남아 있으면 그 이름들."""
    return [
        n for n in DROPPED
        if re.search(
            r"(?im)^[ \t]*create\s+(?:unique\s+)?index\s+(?:concurrently\s+)?"
            r"(?:if\s+not\s+exists\s+)?{}\b".format(re.escape(n)),
            schema,
        )
    ]


# 되돌리기 기대 문장 — 지우기 전 정본(5e52bdf 의 schema.sql 365·422·423·1074·1075줄) 원문에
# `concurrently` 만 더한 것. ⛔ 이름만 대조하면 연산자 클래스(gin_trgm_ops)를 빼거나 표 이름을
#    바꿔도 초록이다(2026-10-01 검사관 지적) — 그래서 종류·표·칸·연산자 클래스까지 통째로 본다.
#    공백 수는 정렬용이라 눌러서 비교한다.
EXPECTED_ROLLBACK = {
    "create index concurrently if not exists idx_unit_geom on unit using gist (geom);",
    "create index concurrently if not exists idx_ub_cat on unit_business (cat_s_cd, snapshot_ym);",
    "create index concurrently if not exists idx_ub_geom on unit_business using gist (geom);",
    "create index concurrently if not exists idx_parcel_road_key "
    "on parcel using gin (road_addr_key gin_trgm_ops);",
    "create index concurrently if not exists idx_parcel_jibun_key "
    "on parcel using gin (jibun_addr_key gin_trgm_ops);",
}


def rollback_statements(sql):
    """머리말 주석 줄 중 `create index concurrently …` 문장(공백을 누른 꼴)."""
    out = []
    for line in norm(sql).splitlines():
        m = re.match(r"^--\s+(create\s+index\s+concurrently\b.*)$", line.strip(), re.I)
        if m:
            out.append(re.sub(r"\s+", " ", m.group(1)).strip().lower())
    return out


def header_problems(sql):
    """머리말(주석)에 되돌리기 문장·적용 전 확인 쿼리가 있는가."""
    bad = []
    text = norm(sql)
    got = rollback_statements(sql)
    if sorted(got) != sorted(EXPECTED_ROLLBACK):
        bad.append("되돌리기 문장이 기대와 다릅니다:\n  없음 {}\n  낯섦 {}".format(
            sorted(EXPECTED_ROLLBACK - set(got)), sorted(set(got) - EXPECTED_ROLLBACK)))
    if not re.search(r"(?im)^--\s+explain\s*$", text) or "st_contains(d.geom, ub.geom)" not in text:
        bad.append("적용 전 확인에 업종 분포 요약표 정의의 explain 이 없습니다")
    for must in ("pg_get_indexdef(s.indexrelid)", "stats_reset from pg_stat_database",
                 "extensions.pg_stat_statements",
                 "'refresh materialized view concurrently mv_district_industry_mix%'"):
        if must not in text:
            bad.append("적용 전 확인 쿼리에 `{}` 가 없습니다".format(must))
    return bad


# ── 지금 상태 ────────────────────────────────────────────────────────────────
def test_migration_drops_exactly_the_five_concurrently():
    assert migration_problems(read(MIGRATION)) == []


def test_schema_no_longer_creates_the_five():
    assert schema_problems(read(SCHEMA)) == []


def test_header_has_rollback_and_precheck():
    assert header_problems(read(MIGRATION)) == []


def test_migration_line_endings_are_not_mixed():
    """줄바꿈이 한 가지로만 돼 있다 — 섞이면 빨강.

    ⚠️ 몇 가지인지는 꺼낸 곳마다 다르다: 저장소에는 마이그레이션이 전부 LF 로 들어 있고
       (`git ls-files --eol` → i/lf), 윈도우 작업본은 autocrlf 로 CRLF, CI(ubuntu)는 변환이
       없어 LF 다. 처음엔 "CRLF 여야 한다"로 썼다가 CI 에서만 빨강이 났다(2026-10-01 검사관).
    """
    with open(MIGRATION, "rb") as f:
        b = f.read()
    assert b.count(b"\n") > 0
    assert b.count(b"\r\n") in (0, b.count(b"\n"))


# ── 돌연변이 — 판정기가 정말 빨강을 내는가 ─────────────────────────────────────
def test_mutation_missing_concurrently_is_noticed():
    sql = read(MIGRATION)
    broken = sql.replace(
        "drop index concurrently if exists idx_ub_cat;", "drop index if exists idx_ub_cat;", 1)
    assert broken != sql, "끼워 넣기가 안 됐습니다"
    assert migration_problems(broken)


def test_mutation_extra_live_index_drop_is_noticed():
    sql = read(MIGRATION)
    broken = sql + "\ndrop index concurrently if exists idx_ub_pnu_cat;\n"
    assert migration_problems(broken)


def test_mutation_missing_one_drop_is_noticed():
    sql = read(MIGRATION)
    broken = sql.replace("drop index concurrently if exists idx_unit_geom;", "", 1)
    assert broken != sql, "끼워 넣기가 안 됐습니다"
    assert migration_problems(broken)


# ⚠️ `set statement_timeout = '900s';` 는 머리말 되돌리기 주석에도 같은 글자로 있다 — 그냥
#    str.replace(…, 1) 하면 **주석 쪽**이 바뀌어 돌연변이가 헛돈다(처음 쓸 때 실제로 그랬다).
#    그래서 줄머리(들여쓰기 0)의 진짜 문장만 고친다.
RE_TIMEOUT_CODE = re.compile(r"(?m)^set statement_timeout = '900s';$")


def test_mutation_wrapped_in_transaction_is_noticed():
    sql = read(MIGRATION)
    broken = RE_TIMEOUT_CODE.sub("set statement_timeout = '900s';\nbegin;", sql, count=1) + "\ncommit;\n"
    assert broken.count("\nbegin;") == 1, "끼워 넣기가 안 됐습니다"
    assert migration_problems(broken)


def test_mutation_two_statements_on_one_line_is_noticed():
    sql = read(MIGRATION)
    broken = sql.replace(
        "drop index concurrently if exists idx_ub_cat;",
        "drop index concurrently if exists idx_ub_cat; drop view if exists v_x;", 1)
    assert broken != sql, "끼워 넣기가 안 됐습니다"
    assert migration_problems(broken)


def test_mutation_without_statement_timeout_is_noticed():
    sql = read(MIGRATION)
    broken = RE_TIMEOUT_CODE.sub("", sql, count=1)
    assert broken != sql, "끼워 넣기가 안 됐습니다"
    assert "--     set statement_timeout = '900s';" in broken, "주석 쪽까지 지워졌습니다"
    assert migration_problems(broken)


def test_mutation_revived_create_in_schema_is_noticed():
    schema = read(SCHEMA)
    broken = schema + "\ncreate index if not exists idx_ub_cat      on unit_business (cat_s_cd, snapshot_ym);\n"
    assert schema_problems(broken) == ["idx_ub_cat"]


def test_mutation_commented_create_in_schema_does_not_count():
    schema = read(SCHEMA)
    quoted = schema + "\n-- create index if not exists idx_ub_cat on unit_business (cat_s_cd, snapshot_ym);\n"
    assert schema_problems(quoted) == []


def test_mutation_rollback_without_opclass_is_noticed():
    sql = read(MIGRATION)
    broken = sql.replace("(road_addr_key gin_trgm_ops)", "(road_addr_key)", 1)
    assert broken != sql, "끼워 넣기가 안 됐습니다"
    assert header_problems(broken)


def test_mutation_rollback_on_wrong_table_is_noticed():
    sql = read(MIGRATION)
    broken = sql.replace("idx_unit_geom  on unit using gist", "idx_unit_geom  on unit_business using gist", 1)
    assert broken != sql, "끼워 넣기가 안 됐습니다"
    assert header_problems(broken)


def test_mutation_rollback_extra_statement_is_noticed():
    sql = read(MIGRATION)
    broken = sql.replace(
        "--     set statement_timeout = '900s';",
        "--     set statement_timeout = '900s';\n"
        "--     create index concurrently if not exists idx_x on parcel (pnu);", 1)
    assert broken != sql, "끼워 넣기가 안 됐습니다"
    assert header_problems(broken)


def test_rollback_expectation_covers_exactly_the_five():
    """기대 문장 목록 자체가 다섯 이름을 정확히 한 번씩 덮는가(목록에서 하나 빠뜨리면 빨강).

    ⓘ 정의 글자는 5e52bdf 의 schema.sql 원문을 보고 옮겼다(그 판은 git 에만 있어 CI 에서
       직접 대조하지 않는다 — 옮긴 글자의 검증은 2026-10-01 작업반 보고에 남겼다).
    """
    for stmt in EXPECTED_ROLLBACK:
        assert stmt.startswith("create index concurrently if not exists ")
        name = stmt.split()[6]  # create index concurrently if not exists <이름>
        assert name in DROPPED, stmt
    assert {s.split()[6] for s in EXPECTED_ROLLBACK} == set(DROPPED)


def test_mutation_missing_rollback_line_is_noticed():
    sql = read(MIGRATION)
    broken = re.sub(r"(?m)^--\s+create index concurrently if not exists idx_ub_geom\b.*$", "--", sql)
    assert broken != sql, "끼워 넣기가 안 됐습니다"
    assert header_problems(broken)
