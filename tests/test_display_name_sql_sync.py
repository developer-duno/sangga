# -*- coding: utf-8 -*-
"""
건물 표시명 규칙(2026-08-08e)이 schema.sql 과 마이그레이션에서 **같은지** 지킨다.

왜 이 테스트가 있나
-------------------
이 프로젝트는 `supabase/schema.sql`(정본)과 `supabase/migrations/*.sql`(라이브에
붙여넣어 실행하는 것) 두 곳에 같은 SQL 을 적어 둔다. 한쪽만 고치면 **에러 없이**
정본과 라이브가 갈라진다 — 다음 사람이 schema.sql 을 믿고 판단하는데 라이브는
다르게 도는 상태가 된다.

여기서 지키는 것은 세 가지다.
  1) 개인 성명 가리기 정규식이 두 파일에서 글자 하나까지 같다.
  2) 동명칭 일반 라벨 정규식이 두 파일에서 글자 하나까지 같다.
  3) 검색 함수의 이름 가지와 표시명 인덱스가 **같은 식**을 쓴다.
     — 한 글자만 달라도 gin 인덱스를 안 타고, 그건 에러가 아니라 그냥 느려진다.

공용 설정 파일(conftest.py) 없이 이 파일 안에서 경로를 직접 해결한다
(tests/test_backup_raw.py 와 동일한 방식).
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
MIGRATION = os.path.join(
    ROOT, "supabase", "migrations", "2026-08-08e_building_display_name.sql"
)
# 2026-08-10: `from public`만으로는 anon 직접 GRANT가 안 빠진다는 게 라이브로
# 확인돼, 이 마이그레이션이 anon·authenticated에서 직접 회수한다.
REVOKE_MIGRATION = os.path.join(
    ROOT, "supabase", "migrations", "2026-08-10_revoke_helper_fns_from_anon.sql"
)
# 2026-08-13: 검색 범위 게이트("한 곳을 짚는 검색"만 받는다).
SCOPE_GATE_MIGRATION = os.path.join(
    ROOT, "supabase", "migrations", "2026-08-13_search_scope_gate.sql"
)

# 표시명 식 — 검색 WHERE 절과 인덱스가 이것으로 일치해야 인덱스를 탄다.
DISPLAY_EXPR = "building_display_nm(bld_nm, dong_nm)"
DISPLAY_EXPR_QUALIFIED = "building_display_nm(b.bld_nm, b.dong_nm)"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def schema_sql():
    return read(SCHEMA)


@pytest.fixture(scope="module")
def migration_sql():
    return read(MIGRATION)


@pytest.fixture(scope="module")
def revoke_migration_sql():
    return read(REVOKE_MIGRATION)


def extract_person_regexes(sql):
    """mask_person_name 안의 정규식 두 개(대상 패턴 / 건물 지칭어 예외)를 뽑는다."""
    return re.findall(r"'(\\\([^']*?\\\)\\s\*\$)'", sql)


def extract_generic_dong_regex(sql):
    """동명칭 일반 라벨 판정 정규식을 뽑는다."""
    return re.findall(r"'(\^\(\(주\|부속\)\?건축물\)[^']*)'", sql)


def test_migration_file_exists():
    assert os.path.exists(MIGRATION), (
        "마이그레이션 2026-08-08e 파일이 없습니다. schema.sql 만 고치면 "
        "라이브에는 반영되지 않습니다."
    )


def test_person_name_regexes_match(schema_sql, migration_sql):
    """개인 성명 가리기 정규식이 두 파일에서 같아야 한다."""
    a = extract_person_regexes(schema_sql)
    b = extract_person_regexes(migration_sql)
    assert a, "schema.sql 에서 성명 정규식을 못 찾았습니다 (규칙이 사라졌거나 형태가 바뀜)"
    assert len(a) == 2, "성명 정규식은 대상/예외 2개여야 합니다: {}".format(a)
    assert a == b, (
        "schema.sql 과 마이그레이션의 성명 정규식이 다릅니다.\n"
        "  schema.sql : {}\n  migration  : {}".format(a, b)
    )


def test_generic_dong_regex_match(schema_sql, migration_sql):
    """동명칭 일반 라벨 정규식이 두 파일에서 같아야 한다."""
    a = extract_generic_dong_regex(schema_sql)
    b = extract_generic_dong_regex(migration_sql)
    assert a, "schema.sql 에서 일반 라벨 정규식을 못 찾았습니다"
    assert a == b, (
        "schema.sql 과 마이그레이션의 일반 라벨 정규식이 다릅니다.\n"
        "  schema.sql : {}\n  migration  : {}".format(a, b)
    )


def test_generic_dong_regex_covers_observed_labels(schema_sql):
    """실측된 일반 라벨 상위 15종을 규칙이 전부 덮는지 (파이썬 re 로 대조).

    Postgres 와 파이썬은 정규식 엔진이 다르지만, 여기 쓰는 문법(^ $ | ? * [] {})은
    양쪽 모두 같은 뜻이라 이 대조가 성립한다. 2026-08-08 라이브 실측에서 Postgres
    자신의 엔진으로 284건이 걸리는 것을 확인했고, 이 테스트는 그 규칙이 나중에
    조용히 좁아지는 것을 막는다.
    """
    pat = extract_generic_dong_regex(schema_sql)[0]
    rx = re.compile(pat)
    observed = [
        "주건축물제1동", "가동", "나동", "1동", "2동", "A동", "B동", "1",
        "주건축물제2동", "D동", "근린생활시설", "다동", "2", "C동", "3동",
    ]
    missed = [s for s in observed if not rx.search(s)]
    assert not missed, "일반 라벨인데 규칙이 못 잡습니다: {}".format(missed)


def test_generic_dong_regex_does_not_eat_real_names(schema_sql):
    """진짜 건물 이름을 일반 라벨로 오인하면 안 된다 (라이브 실측 이름으로 대조)."""
    pat = extract_generic_dong_regex(schema_sql)[0]
    rx = re.compile(pat)
    real = [
        "노보텔앰배서더서울", "WeWork Building", "역삼동 718빌딩", "미래에셋타워 A동",
        "강남텔레피아빌딩", "백락빌딩", "이용우빌딩", "S-Tower", "서영빌딩",
        "강남ELS빌딩", "지엔에스", "삼성동",
    ]
    eaten = [s for s in real if rx.search(s)]
    assert not eaten, "진짜 이름인데 일반 라벨로 걸립니다: {}".format(eaten)


def test_2026_08_08e_migration_keeps_its_own_expression(migration_sql):
    """2026-08-08e 마이그레이션은 **그 시점의 식**을 그대로 유지해야 한다.

    과거 마이그레이션 파일은 역사 기록이다 — 라이브에 이미 그 형태로 적용됐으므로
    나중 설계(2026-08-11e 저장 컬럼)에 맞춰 소급해 고치지 않는다. 고치면 "라이브에
    실제로 무엇이 실행됐는가"를 잃는다.
    """
    assert DISPLAY_EXPR in migration_sql, (
        "2026-08-08e: 표시명 식 `{}` 이 사라졌습니다".format(DISPLAY_EXPR)
    )
    assert "idx_building_display_nm" in migration_sql, (
        "2026-08-08e: 당시 만든 표시명 인덱스 기록이 사라졌습니다"
    )
    assert DISPLAY_EXPR_QUALIFIED + " ilike pat.p" in migration_sql, (
        "2026-08-08e: 당시 검색 이름 가지 기록이 바뀌었습니다"
    )


def test_schema_search_uses_stored_key_columns(schema_sql):
    """검색 WHERE 절은 **저장 컬럼**을 봐야 한다 (식으로 되돌아가면 3초를 넘긴다).

    2026-08-11e 이전에는 "WHERE 와 인덱스가 **같은 식**인가"를 지켰다. 지금은 그
    식의 결과를 컬럼(nm_key·road_addr_key·jibun_addr_key)에 저장하고 그 위에
    인덱스를 건다. 그래서 지킬 것이 "식끼리 일치"에서 **"컬럼끼리 일치"**로 바뀌었다.

    왜 그렇게 바꿨나 (EXPLAIN 실측 2026-08-11)
    -----------------------------------------
    '명동' 같은 2글자 검색어는 trigram 선별력이 없어 후보가 거의 전체가 된다.
    인덱스가 '식'이면 **재확인 때마다 regexp_replace 를 다시 돌린다** —
    후보 197,076건 × 정규식 = statement_timeout 3초 초과 → HTTP 500.
    저장 컬럼이면 재확인이 단순 문자열 비교라 **결과를 자르지 않고** 빨라진다.

    식으로 되돌리면 에러가 아니라 **흔한 검색어만 조용히 500**이 되므로,
    사람 눈으로는 안 잡힌다 — 이 테스트가 가드다.
    """
    # 저장 컬럼이 표시명 식으로 만들어져야 한다
    # (동명칭 404개 찾기·개인 성명 가림이 전부 이 식에 걸려 있다).
    assert (
        "generated always as (search_key({})) stored".format(DISPLAY_EXPR)
        in schema_sql
    ), "schema.sql: building.nm_key 가 표시명 식으로 만들어지지 않습니다"

    # WHERE 가 저장 컬럼을 본다 (세 가지 = 이름·도로명·지번)
    #
    # ⚠️ 공백 수에 흔들리지 않게 눌러서 비교한다. 2026-08-13 에 `pc.road_addr_key  like`
    #    처럼 정렬용 공백을 두 칸 준 것만으로 이 가드가 빨간불이 됐다 — 지켜야 할 것은
    #    "저장 컬럼을 본다"이지 "공백이 한 칸이다"가 아니다.
    flat = re.sub(r"\s+", " ", schema_sql)
    for where in (
        "b.nm_key like pat.p",
        "pc.road_addr_key like pat.p",
        "pc.jibun_addr_key like pat.p",
    ):
        assert where in flat, (
            "schema.sql: 검색 WHERE 가 `{}` 를 안 씁니다 — 식으로 되돌아가면 "
            "흔한 검색어가 3초를 넘겨 500이 됩니다".format(where)
        )

    # 그 컬럼 위에 인덱스가 있어야 한다 (없으면 전수 스캔)
    for idx in ("idx_building_nm_key", "idx_parcel_road_key", "idx_parcel_jibun_key"):
        assert idx in schema_sql, (
            "schema.sql: {} 가 없습니다 — 검색이 전수 스캔이 됩니다".format(idx)
        )

    # 죽은 식 인덱스를 되살리면 안 된다 (라이브에서 이미 지웠다)
    for dead in (
        "idx_building_display_nm",
        "idx_parcel_road_addr",
        "idx_parcel_jibun_addr",
    ):
        assert not re.search(
            r"(?m)^create index if not exists {}\b".format(dead), schema_sql
        ), (
            "schema.sql: 죽은 식 인덱스 {} 가 되살아났습니다 — 라이브에는 없어서 "
            "정본과 라이브가 갈라집니다(2026-08-11e)".format(dead)
        )

    # 옛 방식(원본 bld_nm 직접 비교)으로 되돌아가면 성명이 다시 새고
    # 동명칭 404개도 다시 안 찾힌다.
    for old in ("and b.bld_nm ilike pat.p", "and b.bld_nm like pat.p"):
        assert old not in schema_sql, (
            "schema.sql: 검색이 원본 bld_nm 을 직접 보고 있습니다 — "
            "2026-08-08e 이전으로 되돌아갔습니다"
        )


def extract_floor_stack_view(sql):
    """v_floor_stack 뷰 정의 블록만 잘라낸다.

    ⚠️ 파일 전체에서 문자열을 찾으면 **검색 함수 쪽 같은 문장에 걸려** 뷰가 망가져도
       통과한다(2026-08-08 주입 시험에서 실제로 그렇게 새는 것을 확인하고 좁혔다).
    """
    head = "create or replace view v_floor_stack as"
    i = sql.find(head)
    if i < 0:
        return None
    j = sql.find("comment on view v_floor_stack", i)
    return sql[i : j if j > 0 else len(sql)]


def test_floor_stack_view_masks_name(schema_sql, migration_sql):
    """스택 뷰 제목도 같은 표시명을 써야 한다 (여기만 빠지면 성명이 화면에 남는다).

    2026-08-13 부터 정본은 함수를 직접 부르지 않고 **미리 계산해 둔 컬럼**(display_nm)을
    읽는다. 값은 같고(라이브 실측 242,631행 0건 차이), 그래야 도우미 함수를 anon 에게서
    닫을 수 있다 — 뷰 안에서 부르는 함수의 실행 권한은 뷰 소유자가 아니라 접속한 롤로
    검사되기 때문이다(2026-08-10 에 함수를 닫자 이 화면이 401 로 죽었다).

    그래서 여기서 지키는 것은 "함수를 부르는가"가 아니라 **"가려진 이름을 내보내는가"**다.
    옛 마이그레이션 파일은 그 시점의 형태(함수 호출)를 그대로 유지한다 — 역사 기록이다.
    """
    masked_forms = (
        DISPLAY_EXPR_QUALIFIED + " as bld_nm",  # 옛 형태: 함수를 직접 호출
        "b.display_nm as bld_nm",                # 새 형태: 미리 계산해 둔 컬럼
    )
    for label, sql in (("schema.sql", schema_sql), ("migration", migration_sql)):
        block = extract_floor_stack_view(sql)
        assert block, "{}: v_floor_stack 뷰 정의를 못 찾았습니다".format(label)
        assert any(f in block for f in masked_forms), (
            "{}: v_floor_stack 이 가려진 이름을 안 내보냅니다 — "
            "스택 뷰 제목에 개인 성명이 남습니다".format(label)
        )
        # 원본 컬럼을 그대로 내보내던 옛 형태로 되돌아가면 안 된다.
        assert not re.search(r"^\s*b\.bld_nm\s*,\s*$", block, re.M), (
            "{}: v_floor_stack 이 b.bld_nm 을 그대로 내보냅니다 "
            "(2026-08-08e 이전으로 되돌아갔습니다)".format(label)
        )


def extract_unit_current_view(sql):
    """v_unit_current 뷰 정의 블록만 잘라낸다 (위 v_floor_stack 과 같은 이유로 좁힌다)."""
    head = "create or replace view v_unit_current as"
    i = sql.find(head)
    if i < 0:
        return None
    j = sql.find("comment on view v_unit_current", i)
    return sql[i : j if j > 0 else len(sql)]


def test_unit_current_view_masks_name(schema_sql):
    """호실 현황 뷰도 가려진 이름을 내보내야 한다.

    2026-08-13 적대검증에서 **이 뷰만 원본 건물명을 그대로 싣고 있는 것**이 발견됐다.
    지금 anon 에게 열려 있지 않아 새고 있진 않지만, "노출 안 돼서 안전한 것"은 안전한
    게 아니라 아직 안 걸린 것이다 — 나중에 이 뷰를 열면 그 순간부터 샌다.

    ⚠️ 이 가드 자체가 없어서 못 잡던 구멍이었다. v_floor_stack 쪽 가드에 주입 시험을
       돌렸더니 엉뚱하게 이 뷰가 망가져도 전부 초록이었다(2026-08-13에 그렇게 발견).
    """
    block = extract_unit_current_view(schema_sql)
    assert block, "schema.sql: v_unit_current 뷰 정의를 못 찾았습니다"
    assert (
        "b.display_nm as bld_nm" in block
        or DISPLAY_EXPR_QUALIFIED + " as bld_nm" in block
    ), "schema.sql: v_unit_current 가 가려진 이름을 안 내보냅니다 — 개인 성명이 그대로 나갑니다"
    assert not re.search(r"^\s*b\.bld_nm\s*,\s*$", block, re.M), (
        "schema.sql: v_unit_current 가 b.bld_nm 을 그대로 내보냅니다"
    )


def test_display_nm_column_is_defined_from_the_masking_function(schema_sql):
    """display_nm 컬럼은 반드시 표시명 함수로 만들어져야 한다.

    이 컬럼이 뷰가 읽는 유일한 출처가 됐으므로, 정의가 바뀌면 가림이 통째로 풀린다.
    (예: 그냥 `bld_nm` 을 복사하도록 바꾸면 개인 성명이 다시 화면에 나온다.)
    """
    flat = re.sub(r"\s+", " ", schema_sql)
    assert (
        "add column if not exists display_nm text generated always as "
        "(building_display_nm(bld_nm, dong_nm)) stored" in flat
    ), (
        "schema.sql: building.display_nm 이 표시명 함수로 만들어지지 않습니다 — "
        "뷰가 이 컬럼을 읽으므로 개인 성명 가림이 풀립니다"
    )


def extract_display_nm_body(sql):
    """building_display_nm 함수 본문($$ ... $$)만 잘라낸다."""
    head = "create or replace function building_display_nm("
    i = sql.find(head)
    if i < 0:
        return None
    a = sql.find("$$", i)
    b = sql.find("$$", a + 2)
    return sql[a : b + 2] if a > 0 and b > 0 else None


def test_mask_call_inside_display_nm_is_schema_qualified(schema_sql, migration_sql):
    """building_display_nm 안의 mask_person_name 호출은 반드시 `public.` 을 붙여야 한다.

    왜 (2026-08-08 라이브 실패로 확인)
    ----------------------------------
    `CREATE INDEX` 가 도는 동안 Postgres 는 보안을 위해 search_path 를
    **`pg_catalog, pg_temp` 로 일시적으로 바꾼다**(공식 문서 명시). 그 순간 public 이
    안 보이므로 이름만 적은 `mask_person_name(...)` 은
    `42883: 함수가 존재하지 않습니다` 로 실패하고, SQL Editor 는 스크립트 전체를
    한 트랜잭션으로 돌리므로 **마이그레이션이 통째로 되돌아간다.**

    함수가 없어서가 아니라 그 순간에만 안 보여서 나는 오류라, 로컬 문법 검사로는
    절대 안 잡힌다 — 이 테스트가 유일한 가드다.
    """
    for label, sql in (("schema.sql", schema_sql), ("migration", migration_sql)):
        body = extract_display_nm_body(sql)
        assert body, "{}: building_display_nm 본문을 못 찾았습니다".format(label)
        assert "public.mask_person_name(" in body, (
            "{}: building_display_nm 이 mask_person_name 을 스키마 없이 부릅니다 — "
            "CREATE INDEX 단계에서 42883 으로 마이그레이션 전체가 되돌아갑니다".format(label)
        )
        assert not re.search(r"(?<![.\w])mask_person_name\s*\(", body), (
            "{}: building_display_nm 본문에 스키마 없는 mask_person_name( 호출이 "
            "남아 있습니다".format(label)
        )


def test_helper_functions_are_immutable(schema_sql, migration_sql):
    """IMMUTABLE 이 아니면 그 식 위에 인덱스를 못 만든다 (마이그레이션이 실패한다)."""
    for label, sql in (("schema.sql", schema_sql), ("migration", migration_sql)):
        for fn in ("mask_person_name", "building_display_nm"):
            body = sql.split("create or replace function {}(".format(fn), 1)
            assert len(body) == 2, "{}: {} 함수가 없습니다".format(label, fn)
            head = body[1][:400]
            assert "immutable" in head, (
                "{}: {} 가 IMMUTABLE 이 아닙니다 — 인덱스를 못 만듭니다".format(label, fn)
            )


def test_helper_functions_are_not_granted_to_anon(schema_sql, revoke_migration_sql):
    """도우미 함수는 anon/authenticated 가 직접 EXECUTE 할 수 없어야 한다(알려진한계 §4).

    왜 `from public` 만으로는 부족한가 (2026-08-10 라이브 실측 + 공식문서로 확정)
    -------------------------------------------------------------------------
    옛 버전은 `revoke all on function ... from public;` 문자열이 파일에 있는지만
    글자로 확인했다. 그런데 그 문장 자체가 **무효**였다 — PUBLIC은 실제 롤이
    아니라 "이 DB의 모든 롤"을 가리키는 가상 그룹이고, Supabase는 새 함수를
    만들 때 anon·authenticated 에게 **직접(directly)** EXECUTE 를 GRANT한다.
    PostgreSQL 공식 문서(sql-revoke.html)가 명시하듯 "revoking ... from PUBLIC
    does not necessarily mean that all roles have lost ... privilege: those who
    have it granted directly ... will still have it" — 즉 `from public` 회수는
    가상 그룹 경로만 지우고 직접 부여분은 그대로 남긴다. 실제로 2026-08-10
    라이브에서 이 문장이 이미 적용된 상태로 anon 공개키 RPC 호출이 둘 다
    HTTP 200 이었다(문서 무결·데이터 오염과 무관하게 옛 테스트는 계속 초록불).
    그래서 이 테스트는 **글자가 있는지가 아니라 회수 대상에 anon·authenticated
    가 실제로 들어 있는지**를 파싱해서 확인한다 — `from public` 만 있고
    `anon`/`authenticated` 가 빠지면 반드시 빨간불이어야 한다.
    """
    for label, sql in (("schema.sql", schema_sql), ("2026-08-10 migration", revoke_migration_sql)):
        for sig in ("mask_person_name(text)", "building_display_nm(text, text)"):
            # 줄 맨 앞(들여쓰기 0)에서 시작하는 진짜 SQL 문장만 찾는다 — `-- ` 로
            # 시작하는 설명 주석 안에 옛 형태(`from public;`)를 그대로 인용해 둔
            # 줄과 혼동하면 안 된다(2026-08-10 마이그레이션 헤더 참고).
            m = re.search(
                r"(?m)^revoke all on function (?:public\.)?{}\s+from\s+([^;]+);".format(
                    re.escape(sig)
                ),
                sql,
            )
            assert m, "{}: {} revoke 문을 찾지 못했습니다".format(label, sig)
            roles = m.group(1)
            for role in ("anon", "authenticated"):
                assert role in roles, (
                    "{}: {} 의 revoke 대상에 {}이 없습니다 — `from public`만으로는 "
                    "Supabase가 새 함수에 직접 건 GRANT가 회수되지 않아 anon RPC가 "
                    "여전히 200을 반환합니다(2026-08-10 라이브 실측)".format(
                        label, sig, role
                    )
                )


# =====================================================================
# 검색 범위 게이트 — "한 곳을 짚는 검색"만 받는다 (2026-08-13)
# =====================================================================
# 왜 가드가 필요한가: 게이트를 지우면 에러가 나지 않는다. `서울`·`동` 같은 흔한
# 검색어만 조용히 3초를 넘겨 500이 되고, 나머지는 멀쩡해 보인다 — 사람 눈으로는
# 안 잡히는 종류다. 라이브 실측(2026-08-13): 게이트 없이 '동'은 7,721ms,
# 게이트를 붙이면 264ms 에 0건으로 끊긴다.


def test_search_scope_gate_exists(schema_sql):
    """범위 판정 함수 두 개가 정본에 있어야 한다."""
    assert "create or replace function search_scope_limit()" in schema_sql, (
        "schema.sql: search_scope_limit() 가 없습니다 — 상한이 코드 여기저기 흩어지면 "
        "서로 다른 값으로 갈라진다"
    )
    assert "create or replace function search_scope(q text, sigungu text default null)" in schema_sql, (
        "schema.sql: search_scope() 가 없습니다 — 화면이 '결과 없음'과 '너무 넓음'을 "
        "구분하지 못하게 된다"
    )


def test_search_bounds_candidates_with_the_limit(schema_sql):
    """후보 수집이 **상한+1 에서 멈춰야** 한다.

    이게 게이트이자 성능 장치다. 상한을 지우면 '동'(필지의 98%와 매칭)이 20만 건을
    전부 모으다 3초를 넘긴다. 따로 세는 조회를 두는 방식으로 되돌리면 좁은 검색어까지
    표를 두 번 더 훑어 오히려 느려진다(실측: '명동' 796ms → 2,803ms).
    """
    flat = re.sub(r"\s+", " ", schema_sql)
    assert flat.count("limit search_scope_limit() + 1") >= 2, (
        "schema.sql: 후보 수집(주소·이름 두 가지)이 상한에서 멈추지 않습니다 — "
        "흔한 검색어가 20만 건을 다 모으다 3초를 넘겨 500이 됩니다"
    )
    assert "not (select g.broad from gate g)" in flat, (
        "schema.sql: 범위를 넘긴 검색을 끊는 게이트가 없습니다 — 결과 25개를 억지로 "
        "보여주게 되는데, 상권분석은 건물 한 채 단위라 의미가 없습니다"
    )


def test_search_scope_is_open_to_anon_but_limit_is_not(schema_sql):
    """화면은 판정(search_scope)만 부른다. 상한 함수는 내부용이라 닫아 둔다."""
    flat = re.sub(r"\s+", " ", schema_sql)
    assert "grant execute on function search_scope(text) to anon" in flat, (
        "schema.sql: search_scope() 가 anon 에게 안 열려 있습니다 — 화면이 '너무 넓은 "
        "검색'인지 물어볼 수 없게 됩니다"
    )
    m = re.search(
        r"revoke all on function search_scope_limit\(\)\s+from\s+([^;]+);", flat
    )
    assert m, "schema.sql: search_scope_limit() revoke 문을 찾지 못했습니다"
    for role in ("anon", "authenticated"):
        assert role in m.group(1), (
            "schema.sql: search_scope_limit() 의 revoke 대상에 {}이 없습니다".format(role)
        )


def test_search_scope_limit_matches_between_schema_and_migration():
    """상한 값이 정본과 마이그레이션에서 갈라지면 안 된다."""
    pat = re.compile(
        r"create or replace function search_scope_limit\(\).*?select\s+(\d+)\s*\$\$",
        re.S,
    )
    found = {}
    for label, path in (
        ("schema.sql", SCHEMA),
        ("migration", SCOPE_GATE_MIGRATION),
    ):
        m = pat.search(read(path))
        assert m, "{}: search_scope_limit() 본문에서 값을 못 읽었습니다".format(label)
        found[label] = int(m.group(1))
    assert found["schema.sql"] == found["migration"], (
        "상한 값이 갈라졌습니다: {} — 한 곳만 고치면 새 환경과 라이브가 다르게 "
        "동작한다".format(found)
    )
    # 근거(2026-08-13 실측): 가장 큰 법정동 신림동 4,633 < 상한 < 가장 작은 구 검색 7,399
    assert 4633 < found["schema.sql"] < 7399, (
        "상한 {}: 동 이름이 막히거나(4,633 이하) 구 이름이 통과(7,399 이상)합니다 — "
        "두 수를 다시 실측하고 값을 정하세요".format(found["schema.sql"])
    )


# =====================================================================
# 검색 전용 요약표 — 찾힐 수 있는 필지만 훑는다 (2026-08-13d)
# =====================================================================
# 왜 가드가 필요한가: 되돌려도 **에러가 안 난다.** 결과도 같다. 다만 2글자 검색어가
# 다시 3초를 넘겨 500이 되고(전국 시드로 parcel 이 112만 행), 범위 판정이 건물 없는
# 필지까지 세어 '명동' 같은 정상 검색을 막는다. 라이브 실측(2026-08-13):
#   parcel 을 훑으면 1,725ms / 요약표(188,442행)를 훑으면 109ms — 15.8배.


def test_search_reads_the_searchable_parcel_summary(schema_sql):
    """검색은 parcel 이 아니라 mv_search_parcel 을 훑어야 한다."""
    flat = re.sub(r"\s+", " ", schema_sql)
    for fn, head in (
        ("search_buildings", "create or replace function search_buildings(q text, lim int default 25, sigungu text default null)"),
        ("search_scope", "create or replace function search_scope(q text, sigungu text default null)"),
    ):
        i = schema_sql.index(head)
        j = schema_sql.index("$$;", schema_sql.index("as $$", i)) + 3
        body = re.sub(r"\s+", " ", schema_sql[i:j])
        assert "from mv_search_parcel" in body, (
            "schema.sql: {} 가 검색 전용 요약표를 안 씁니다 — 전국 시드 뒤 parcel 112만 행을 "
            "훑느라 2글자 검색이 3초를 넘겨 500이 됩니다".format(fn)
        )
        assert "from parcel pc cross join pat" not in body, (
            "schema.sql: {} 가 parcel 을 직접 훑습니다 — 건물 없는 93만 필지까지 훑게 "
            "됩니다(2026-08-13 이전으로 되돌아갔습니다)".format(fn)
        )
    assert "create materialized view if not exists mv_search_parcel" in flat, (
        "schema.sql: mv_search_parcel 정의가 없습니다"
    )


def test_search_summary_keeps_only_parcels_that_have_buildings(schema_sql):
    """요약표는 **건물이 있는 필지만** 담아야 한다.

    조건을 빼면 요약표가 parcel 전체 사본이 돼 크기 이점이 사라지고, 범위 판정도
    다시 부풀려진다(= 이 표를 만든 이유가 통째로 없어진다).
    """
    i = schema_sql.index("create materialized view if not exists mv_search_parcel")
    body = re.sub(r"\s+", " ", schema_sql[i : schema_sql.index(";", i)])
    assert re.search(
        r"where exists\s*\(\s*select 1 from building b where b\.pnu = pc\.pnu\s*\)", body
    ), (
        "schema.sql: mv_search_parcel 이 '건물이 있는 필지만' 조건을 안 씁니다 — "
        "요약표가 parcel 전체 사본이 됩니다"
    )


def test_search_summary_has_the_indexes_it_needs(schema_sql):
    """concurrently 갱신용 unique 인덱스 + 부분 일치용 gin 두 개."""
    flat = re.sub(r"\s+", " ", schema_sql)
    assert "create unique index if not exists idx_msp_pnu on mv_search_parcel (pnu)" in flat, (
        "schema.sql: mv_search_parcel 의 unique 인덱스가 없습니다 — "
        "`refresh materialized view concurrently` 가 동작하지 않아 갱신 중 검색이 잠깁니다"
    )
    for idx, col in (("idx_msp_road_key", "road_addr_key"), ("idx_msp_jibun_key", "jibun_addr_key")):
        assert "{} on mv_search_parcel using gin ({} gin_trgm_ops)".format(idx, col) in flat, (
            "schema.sql: {} 가 없습니다 — 3글자 이상 검색이 전수 스캔이 됩니다".format(idx)
        )


# =====================================================================
# 구 단위 검색 + 요약표 권한 (2026-08-13e · 13f)
# =====================================================================


def test_search_can_be_narrowed_to_one_sigungu(schema_sql):
    """검색이 "고른 구 안에서만" 될 수 있어야 한다 (사장님 결정 2026-08-13).

    같은 건물 이름이 여러 구에 겹치기 때문이다 — 이름 33,851종 중 2,443종(7.2%)이
    2개 이상 구에 존재한다. 좁히는 길이 사라지면 그 중복이 그대로 화면에 나온다.
    """
    flat = re.sub(r"\s+", " ", schema_sql)
    assert "sigungu_code" in flat, "schema.sql: 요약표에 시군구 칸이 없습니다"
    assert "create index if not exists idx_msp_sigungu on mv_search_parcel (sigungu_code)" in flat, (
        "schema.sql: 구로 좁히는 인덱스가 없습니다 — 좁혀도 전수 스캔이 됩니다"
    )
    # ⚠️ **정확히 4곳**이어야 한다 — search_scope 의 주소·이름 가지 2곳,
    #    search_buildings 의 addr·nm 가지 2곳. `>= 2` 로 느슨하게 두면 절반을
    #    지워도 초록이 된다(2026-08-13 주입 시험에서 실제로 그렇게 샜다).
    assert flat.count("pat.gu is null or pc.sigungu_code = pat.gu") == 4, (
        "schema.sql: 구 좁히기 조건이 4곳이 아닙니다({}곳) — 검색·범위판정 각각의 "
        "주소·이름 두 가지 모두에 걸려 있어야 합니다".format(
            flat.count("pat.gu is null or pc.sigungu_code = pat.gu"))
    )


def test_open_sigungu_list_comes_from_the_database(schema_sql):
    """고를 수 있는 구 목록은 **자료가 있는 곳만** 나와야 한다.

    프론트에 목록을 박아 두면 자료 없는 구를 고를 수 있게 되고, 고르면 아무것도
    안 나와 "고장난 것"처럼 보인다.
    """
    flat = re.sub(r"\s+", " ", schema_sql)
    assert "create materialized view if not exists mv_open_sigungu" in flat
    assert "create or replace function list_open_sigungu()" in flat
    assert "grant execute on function list_open_sigungu() to anon" in flat, (
        "schema.sql: 화면이 구 목록을 못 읽습니다"
    )


def test_materialized_views_are_closed_to_anon(schema_sql):
    """⛔ 요약표는 공개키에게 열면 안 된다.

    2026-08-13 적대검증 실측: 만들어 두기만 했더니 `GET /rest/v1/mv_search_parcel`
    가 **200** 이었고 188,442행 전체를 페이지네이션으로 내려받을 수 있었다 —
    검색 상한 게이트를 통째로 건너뛰는 옆문이었다. 원인은 Supabase 가 스키마 public 에
    걸어 둔 기본 권한이라, **새로 만드는 표마다 자동으로 열린다.**
    """
    flat = re.sub(r"\s+", " ", schema_sql)
    for mv in ("mv_search_parcel", "mv_open_sigungu"):
        m = re.search(r"revoke all on {}\s+from\s+([^;]+);".format(mv), flat)
        assert m, "schema.sql: {} 의 권한 회수문이 없습니다".format(mv)
        for role in ("anon", "authenticated"):
            assert role in m.group(1), (
                "schema.sql: {} 회수 대상에 {}이 없습니다 — `from public` 만으로는 "
                "직접 받은 GRANT 가 안 빠집니다".format(mv, role)
            )
    assert "alter default privileges in schema public revoke all on tables from anon" in flat, (
        "schema.sql: 기본 권한이 안전한 쪽으로 안 바뀌어 있습니다 — 다음에 표를 하나 "
        "더 만들면 또 자동으로 열립니다(사람 기억에 의존하게 됩니다)"
    )
