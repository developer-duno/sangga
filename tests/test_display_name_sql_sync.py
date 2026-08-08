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


def test_search_and_index_use_the_same_expression(schema_sql, migration_sql):
    """검색 WHERE 절과 인덱스가 같은 식을 써야 gin 인덱스를 탄다.

    한 글자만 달라도 인덱스를 안 타는데, 그건 에러가 아니라 **조용한 성능 저하**라
    사람 눈으로는 안 잡힌다.
    """
    for label, sql in (("schema.sql", schema_sql), ("migration", migration_sql)):
        assert DISPLAY_EXPR in sql, (
            "{}: 표시명 인덱스 식 `{}` 이 없습니다".format(label, DISPLAY_EXPR)
        )
        assert "idx_building_display_nm" in sql, (
            "{}: 표시명 인덱스가 없습니다 — 검색이 전수 스캔이 됩니다".format(label)
        )
        assert DISPLAY_EXPR_QUALIFIED + " ilike pat.p" in sql, (
            "{}: 검색 이름 가지가 표시명 식을 안 씁니다 — 동명칭 404개가 다시 "
            "안 찾히게 됩니다".format(label)
        )
        # 옛 방식(원본 bld_nm 직접 비교)으로 되돌아가면 성명이 다시 새고
        # 동명칭도 다시 안 찾힌다.
        assert "and b.bld_nm ilike pat.p" not in sql, (
            "{}: 검색이 원본 bld_nm 을 직접 보고 있습니다 — 2026-08-08e 이전으로 "
            "되돌아갔습니다".format(label)
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
    """스택 뷰 제목도 같은 표시명을 써야 한다 (여기만 빠지면 성명이 화면에 남는다)."""
    for label, sql in (("schema.sql", schema_sql), ("migration", migration_sql)):
        block = extract_floor_stack_view(sql)
        assert block, "{}: v_floor_stack 뷰 정의를 못 찾았습니다".format(label)
        assert DISPLAY_EXPR_QUALIFIED + " as bld_nm" in block, (
            "{}: v_floor_stack 이 원본 건물명을 그대로 내보냅니다 — "
            "스택 뷰 제목에 개인 성명이 남습니다".format(label)
        )
        # 원본 컬럼을 그대로 내보내던 옛 형태로 되돌아가면 안 된다.
        assert not re.search(r"^\s*b\.bld_nm\s*,\s*$", block, re.M), (
            "{}: v_floor_stack 이 b.bld_nm 을 그대로 내보냅니다 "
            "(2026-08-08e 이전으로 되돌아갔습니다)".format(label)
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


def test_helper_functions_are_not_granted_to_anon(schema_sql, migration_sql):
    """새 함수는 기본적으로 anon 에게 열린다 — 명시적으로 회수해야 한다(알려진한계 §4)."""
    for label, sql in (("schema.sql", schema_sql), ("migration", migration_sql)):
        for sig in ("mask_person_name(text)", "building_display_nm(text, text)"):
            assert "revoke all on function {} from public".format(sig) in sql, (
                "{}: {} 권한 회수가 없습니다 — anon 이 직접 부를 수 있습니다".format(
                    label, sig
                )
            )
