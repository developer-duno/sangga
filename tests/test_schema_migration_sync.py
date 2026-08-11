# -*- coding: utf-8 -*-
"""마이그레이션에 적용한 것이 정본(schema.sql)에도 반영됐는지 지킨다.

왜 이 테스트가 있나 (2026-08-11 실제 사고)
------------------------------------------
이 프로젝트는 라이브 DB 를 `supabase/migrations/*.sql` 로 고치고, 같은 내용을
`supabase/schema.sql`(정본, "새 환경을 만들 때 돌리는 파일")에도 적어 둔다.
한쪽만 고쳐도 **에러가 안 난다** — 라이브는 잘 돌고 테스트도 초록이다. 그래서
드리프트가 조용히 쌓인다.

2026-08-11 에 라이브를 직접 떠서 대조했더니 실제로 어긋나 있었다:
  · 11c 의 `search_key()` 함수가 정본에 **통째로 빠져** 있었다
    → 그 파일만 보고 새 환경을 만들었으면 검색이 통째로 깨졌다
  · 저장 컬럼 인덱스 3개가 정본에 없고, 반대로 라이브에서 지운 식 인덱스 3개가
    정본에만 남아 있었다
게다가 정본 상단 메모는 "11d·11e 가 미반영"이라고 **틀리게** 적혀 있었다
(11d 는 절반이 이미 반영, 빠진 건 메모에 없던 11c). 사람이 손으로 적는 메모로는
못 막는다는 뜻이라, 기계가 지키게 한다.

무엇을 지키나
-------------
마이그레이션을 **날짜순으로 재생**해 "지금 살아 있어야 할" 인덱스·함수·저장 컬럼을
계산하고, 그것이 정본에 있는지 본다. 중간에 만들었다 지운 것(식 인덱스 3개)은
살아 있지 않으므로 정본에 **없어야** 한다.

⚠️ 한계 (일부러 이 정도만 본다)
  · 이름만 본다. 정의 본문까지 대조하지는 않는다 — 본문 대조는 라이브 접속이
    필요한데 CI 에는 DB 가 없다(라이브 대조는 dbx.py 로 사람이 돌린다).
  · 그래도 "통째로 빠진 것"은 전부 잡힌다. 실제 사고 3건이 모두 그 형태였다.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
MIG_DIR = os.path.join(ROOT, "supabase", "migrations")

# 줄 맨 앞(들여쓰기 0)에서 시작하는 진짜 SQL 문장만 본다.
# 설명 주석(`-- create index …`) 안에 옛 형태를 인용해 둔 줄과 섞이면 안 된다.
RE_CREATE_INDEX = re.compile(
    r"(?im)^create\s+(?:unique\s+)?index\s+(?:concurrently\s+)?"
    r"(?:if\s+not\s+exists\s+)?(\w+)"
)
RE_DROP_INDEX = re.compile(r"(?im)^drop\s+index\s+(?:if\s+exists\s+)?(\w+)")
RE_CREATE_FN = re.compile(r"(?im)^create\s+or\s+replace\s+function\s+(?:public\.)?(\w+)")
RE_DROP_FN = re.compile(r"(?im)^drop\s+function\s+(?:if\s+exists\s+)?(?:public\.)?(\w+)")
RE_ADD_COLUMN = re.compile(r"(?im)^\s*add\s+column\s+(?:if\s+not\s+exists\s+)?(\w+)")
RE_DROP_COLUMN = re.compile(r"(?im)^\s*drop\s+column\s+(?:if\s+exists\s+)?(\w+)")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def migration_files():
    """날짜순(= 파일명 사전순)으로 마이그레이션 경로를 돌려준다.

    파일명이 `2026-08-10_`·`2026-08-10b_` 처럼 날짜+접미사라, 사전순이 곧 적용순이다
    (`_`(0x5F) < `b`(0x62) 라 접미사 없는 쪽이 먼저 온다).
    """
    names = sorted(n for n in os.listdir(MIG_DIR) if n.endswith(".sql"))
    return [os.path.join(MIG_DIR, n) for n in names]


def replay(create_re, drop_re):
    """마이그레이션을 순서대로 재생해 **지금 살아 있어야 할 이름**과 **지운 이름**을 낸다."""
    alive, dropped = set(), set()
    for path in migration_files():
        sql = read(path)
        for name in create_re.findall(sql):
            alive.add(name)
            dropped.discard(name)
        for name in drop_re.findall(sql):
            alive.discard(name)
            dropped.add(name)
    return alive, dropped


def schema_has_index(schema, name):
    return re.search(
        r"(?im)^create\s+(?:unique\s+)?index\s+(?:concurrently\s+)?"
        r"(?:if\s+not\s+exists\s+)?{}\b".format(re.escape(name)),
        schema,
    )


@pytest.fixture(scope="module")
def schema_sql():
    return read(SCHEMA)


def test_migration_dir_is_not_empty():
    files = migration_files()
    assert files, "supabase/migrations 에 .sql 이 없습니다 — 경로가 바뀌었는지 확인"


def test_live_indexes_are_in_schema(schema_sql):
    """마이그레이션으로 만들어 아직 살아 있는 인덱스는 정본에도 있어야 한다."""
    alive, _ = replay(RE_CREATE_INDEX, RE_DROP_INDEX)
    missing = sorted(n for n in alive if not schema_has_index(schema_sql, n))
    assert not missing, (
        "마이그레이션에는 있는데 schema.sql 에 없는 인덱스: {}\n"
        "→ 새 환경을 이 파일로 만들면 그 인덱스가 빠진 채 만들어집니다. "
        "schema.sql 에 같은 정의를 추가하세요.".format(missing)
    )


def test_dropped_indexes_are_gone_from_schema(schema_sql):
    """마이그레이션에서 지운 인덱스가 정본에 남아 있으면 안 된다.

    남아 있으면 새 환경에만 그 인덱스가 생겨 라이브와 다르게 돈다. 실제로
    2026-08-11e 가 지운 식 인덱스 3개가 정본에만 남아 있었다.
    """
    _, dropped = replay(RE_CREATE_INDEX, RE_DROP_INDEX)
    zombies = sorted(n for n in dropped if schema_has_index(schema_sql, n))
    assert not zombies, (
        "라이브에서 지운 인덱스가 schema.sql 에 남아 있습니다: {}\n"
        "→ 정본과 라이브가 갈라집니다. schema.sql 에서 지우세요.".format(zombies)
    )


def test_live_functions_are_in_schema(schema_sql):
    """마이그레이션으로 만든 함수는 정본에도 있어야 한다 (search_key 누락 사고 재발 방지)."""
    alive, _ = replay(RE_CREATE_FN, RE_DROP_FN)
    missing = sorted(
        n
        for n in alive
        if not re.search(
            r"(?im)^create\s+or\s+replace\s+function\s+(?:public\.)?{}\s*\(".format(
                re.escape(n)
            ),
            schema_sql,
        )
    )
    assert not missing, (
        "마이그레이션에는 있는데 schema.sql 에 없는 함수: {}\n"
        "→ 이 파일로 새 환경을 만들면 그 함수가 없어 검색·표시가 통째로 깨집니다 "
        "(2026-08-11 에 search_key 가 실제로 이 상태였습니다).".format(missing)
    )


def test_live_generated_columns_are_in_schema(schema_sql):
    """마이그레이션으로 붙인 저장 컬럼은 정본에도 있어야 한다."""
    alive, _ = replay(RE_ADD_COLUMN, RE_DROP_COLUMN)
    missing = sorted(
        n
        for n in alive
        if not re.search(
            r"(?im)^\s*add\s+column\s+(?:if\s+not\s+exists\s+)?{}\b".format(
                re.escape(n)
            ),
            schema_sql,
        )
    )
    assert not missing, (
        "마이그레이션에는 있는데 schema.sql 에 없는 컬럼: {}\n"
        "→ 그 컬럼을 쓰는 인덱스·함수가 새 환경에서 만들어지지 않습니다.".format(missing)
    )


def test_replay_actually_sees_the_2026_08_11e_swap():
    """재생 로직 자체가 맞는지 — 11e 의 '식 인덱스 → 저장 컬럼 인덱스' 교체를 읽어내는가.

    이 테스트가 없으면, 정규식이 아무것도 못 잡아도 위 네 테스트가 전부 초록이 된다
    (빈 집합은 언제나 통과한다). 즉 **가드가 헛도는 것**을 막는 가드다.
    """
    alive, dropped = replay(RE_CREATE_INDEX, RE_DROP_INDEX)
    for name in ("idx_building_nm_key", "idx_parcel_road_key", "idx_parcel_jibun_key"):
        assert name in alive, "재생이 11e 가 만든 {} 를 못 봤습니다".format(name)
    for name in ("idx_building_display_nm", "idx_parcel_road_addr", "idx_parcel_jibun_addr"):
        assert name in dropped, "재생이 11e 가 지운 {} 를 못 봤습니다".format(name)
        assert name not in alive, "{} 가 지워졌는데 살아 있다고 나옵니다".format(name)

    fns, _ = replay(RE_CREATE_FN, RE_DROP_FN)
    assert "search_key" in fns, "재생이 11c 의 search_key 를 못 봤습니다"
