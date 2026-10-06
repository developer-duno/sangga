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
마이그레이션을 **날짜순으로 재생**해 "지금 살아 있어야 할" 인덱스·함수·뷰·저장 컬럼을
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

# 이름 앞에 붙을 수 있는 스키마 접두.
# ⚠️ `api\.` 를 빼면 안 된다 — 2026-08-22e 가 `create or replace view api.parcel` 처럼
#    스키마를 붙여 쓰기 시작했고, 접두를 모르는 정규식은 `api.parcel` 에서 이름을
#    **"api"** 로 잡는다. 그러면 새 객체 12개가 전부 "api" 라는 한 이름으로 뭉개져
#    가드가 조용히 헛돈다(빠진 것을 못 잡는다).
SCHEMA_PREFIX = r"(?:public\.|api\.)?"

# 줄 맨 앞(들여쓰기 0)에서 시작하는 진짜 SQL 문장만 본다.
# 설명 주석(`-- create index …`) 안에 옛 형태를 인용해 둔 줄과 섞이면 안 된다.
# ⓘ `create index` 만은 접두를 안 붙인다 — 거기 오는 이름은 대상 표가 아니라 **인덱스
#    이름**이라 스키마로 한정할 수 없다(문법상 불가). `drop index` 는 한정할 수 있어 붙인다.
RE_CREATE_INDEX = re.compile(
    r"(?im)^create\s+(?:unique\s+)?index\s+(?:concurrently\s+)?"
    r"(?:if\s+not\s+exists\s+)?(\w+)"
)
# ⓘ `concurrently` 를 건너뛴다(2026-09-27e) — 없으면 그 낱말 자체가 "지운 인덱스 이름"으로 잡혀
#    진짜로 지운 인덱스가 기록에서 빠진다(좀비를 못 잡는다).
RE_DROP_INDEX = re.compile(
    r"(?im)^drop\s+index\s+(?:concurrently\s+)?(?:if\s+exists\s+)?" + SCHEMA_PREFIX + r"(\w+)")
# 인덱스 이름 바꾸기(2026-09-27e — include 칸을 더하려고 v2 로 만든 뒤 옛 이름으로 되돌린다).
# 되짚기에서 "옛 이름이 사라지고 새 이름이 산다"로 친다. 모르면 v2 가 산 것으로 남아
# "정본에 없는 인덱스"로 헛경보가 나고, 되돌린 옛 이름은 "지운 인덱스"로 좀비 경보가 난다.
RE_RENAME_INDEX = re.compile(
    r"(?im)^alter\s+index\s+(?:if\s+exists\s+)?" + SCHEMA_PREFIX + r"(\w+)\s+rename\s+to\s+(\w+)")
# ⓘ `or replace` 는 **있어도 없어도** 잡는다(2026-10-03 넓힘). 예전엔 필수였는데, 그러면
#    `create function x(...)`(or replace 없이 — 반환 칸을 바꾸려고 drop 뒤 새로 만드는 꼴,
#    실제로 2026-08-11_search_by_jibun.sql:53 이 그렇다)로 만들고 정본에 안 옮긴 함수를
#    가드가 **아예 못 봤다**. 정본 쪽 찾기(`schema_has_fn`·`schema_has_view`)도 같이 넓혔다.
#    ⚠️ 못 보는 것: `create temp view`·`create recursive view` · 동적 SQL(`execute '…'`) 안의 정의 ·
#       들여쓴 정의(줄머리 고정은 설명 주석 속 인용을 피하려는 일부러 둔 한계다).
RE_CREATE_FN = re.compile(
    r"(?im)^create\s+(?:or\s+replace\s+)?function\s+" + SCHEMA_PREFIX + r"(\w+)")
RE_DROP_FN = re.compile(r"(?im)^drop\s+function\s+(?:if\s+exists\s+)?" + SCHEMA_PREFIX + r"(\w+)")
# 뷰도 같은 병을 앓는다 — 2026-08-22a 가 v_coverage_stats 의 where 절을 고칠 때
# 정본에 옮겨 적는 것을 잊으면 새 환경만 전국을 세게 된다(에러 0, 조용한 드리프트).
# ⚠️ 물질화 뷰(create materialized view)는 이 정규식에 안 걸린다 — `create` 바로 뒤가
#    `materialized` 라 `view` 자리에 못 닿는다. 물질화 뷰는 아래 RE_CREATE_MATVIEW 가 따로 본다.
RE_CREATE_VIEW = re.compile(
    r"(?im)^create\s+(?:or\s+replace\s+)?view\s+" + SCHEMA_PREFIX + r"(\w+)")
RE_DROP_VIEW = re.compile(r"(?im)^drop\s+view\s+(?:if\s+exists\s+)?" + SCHEMA_PREFIX + r"(\w+)")
# 물질화 뷰는 위 정규식에 안 걸린다(`create` 바로 뒤가 `materialized` 라서 — 위 ⚠️). 그래서 따로 본다 —
# 2026-08-22d 가 mv_coverage_stats 를 만들 때 이 구멍이 드러났다: 새 요약표를 정본에
# 안 옮겨도 아무 테스트가 안 울렸고, 그 파일로 새 환경을 만들면 각주가 통째로 깨진다.
RE_CREATE_MATVIEW = re.compile(
    r"(?im)^create\s+materialized\s+view\s+(?:if\s+not\s+exists\s+)?" + SCHEMA_PREFIX + r"(\w+)"
)
RE_DROP_MATVIEW = re.compile(
    r"(?im)^drop\s+materialized\s+view\s+(?:if\s+exists\s+)?" + SCHEMA_PREFIX + r"(\w+)"
)
# 물질화뷰 이름 바꾸기(2026-10-07a · 결정 0035 — 새 기준으로 `<이름>_next` 에 먼저 굽고, 옛 것을
# 지운 뒤 정본 이름으로 되돌린다). 모르면 _next 가 산 것으로 남아 "정본에 없는 물질화뷰"로
# 헛경보가 나고, 정본 이름은 drop 뒤 되살아난 것을 못 봐 '지운 것'으로 남는다.
RE_RENAME_MATVIEW = re.compile(
    r"(?im)^alter\s+materialized\s+view\s+(?:if\s+exists\s+)?" + SCHEMA_PREFIX
    + r"(\w+)\s+rename\s+to\s+(\w+)")
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


def replay(create_re, drop_re, rename_re=None):
    """마이그레이션을 순서대로 재생해 **지금 살아 있어야 할 이름**과 **지운 이름**을 낸다.

    ⚠️ 한 파일 **안에서도 적힌 순서대로** 처리해야 한다. 만든 것을 먼저 다 훑고 지운 것을
       나중에 훑으면, `drop index ...;` 다음 줄에서 같은 이름을 다시 만드는 흔한 패턴
       (인덱스 정의만 바꾸기)이 "지워진 것"으로 잘못 기록된다 — 2026-08-13 에 실제로
       idx_tx_pnu 를 부분 인덱스로 바꾸다가 이 가드가 헛경보를 냈다.
    """
    alive, dropped = set(), set()
    for path in migration_files():
        sql = read(path)
        events = [(m.start(), "create", m.group(1), None) for m in create_re.finditer(sql)]
        events += [(m.start(), "drop", m.group(1), None) for m in drop_re.finditer(sql)]
        if rename_re is not None:
            events += [(m.start(), "rename", m.group(1), m.group(2))
                       for m in rename_re.finditer(sql)]
        for _, kind, name, new in sorted(events, key=lambda e: e[0]):
            if kind == "create":
                alive.add(name)
                dropped.discard(name)
            elif kind == "drop":
                alive.discard(name)
                dropped.add(name)
            else:
                # 이름 바꾸기 = 옛 이름은 **라이브에서 사라진다** — 정본에 옛 이름(v2)이 남아
                # 있으면 좀비로 잡아야 하므로 dropped 에도 넣는다(2026-09-27e 검사관 지적).
                alive.discard(name)
                dropped.add(name)
                alive.add(new)
                dropped.discard(new)
    return alive, dropped


def schema_has_index(schema, name):
    return re.search(
        r"(?im)^create\s+(?:unique\s+)?index\s+(?:concurrently\s+)?"
        r"(?:if\s+not\s+exists\s+)?{}\b".format(re.escape(name)),
        schema,
    )


def schema_has_fn(schema, name):
    """정본에 그 이름의 함수 정의가 있는가 — `or replace` 는 있어도 없어도 된다.

    ⓘ 가드 본체(test_live_functions_are_in_schema)와 양성 대조가 **같은 함수**를 지난다.
    ⚠️ 못 보는 것: 들여쓴 정의 · 따옴표 이름(`"x"(`) · 동적 SQL 안의 정의.
    """
    return re.search(
        r"(?im)^create\s+(?:or\s+replace\s+)?function\s+{}{}\s*\(".format(
            SCHEMA_PREFIX, re.escape(name)
        ),
        schema,
    )


def schema_has_view(schema, name):
    """정본에 그 이름의 (물질화가 아닌) 뷰 정의가 있는가 — `or replace` 는 있어도 없어도 된다.

    ⓘ 산 뷰 가드·지운 뷰(좀비) 가드·양성 대조가 **같은 함수**를 지난다.
    ⚠️ `create materialized view` 는 여기 안 걸린다(schema_has_matview 가 따로 본다).
    ⚠️ 못 보는 것: 들여쓴 정의 · `create temp|recursive view` · 따옴표 이름.
    """
    return re.search(
        r"(?im)^create\s+(?:or\s+replace\s+)?view\s+{}{}\b".format(
            SCHEMA_PREFIX, re.escape(name)
        ),
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
    alive, _ = replay(RE_CREATE_INDEX, RE_DROP_INDEX, RE_RENAME_INDEX)
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
    _, dropped = replay(RE_CREATE_INDEX, RE_DROP_INDEX, RE_RENAME_INDEX)
    zombies = sorted(n for n in dropped if schema_has_index(schema_sql, n))
    assert not zombies, (
        "라이브에서 지운 인덱스가 schema.sql 에 남아 있습니다: {}\n"
        "→ 정본과 라이브가 갈라집니다. schema.sql 에서 지우세요.".format(zombies)
    )


def test_live_functions_are_in_schema(schema_sql):
    """마이그레이션으로 만든 함수는 정본에도 있어야 한다 (search_key 누락 사고 재발 방지)."""
    alive, _ = replay(RE_CREATE_FN, RE_DROP_FN)
    missing = sorted(n for n in alive if not schema_has_fn(schema_sql, n))
    assert not missing, (
        "마이그레이션에는 있는데 schema.sql 에 없는 함수: {}\n"
        "→ 이 파일로 새 환경을 만들면 그 함수가 없어 검색·표시가 통째로 깨집니다 "
        "(2026-08-11 에 search_key 가 실제로 이 상태였습니다).".format(missing)
    )


def test_live_views_are_in_schema(schema_sql):
    """마이그레이션으로 만든/고친 뷰는 정본에도 있어야 한다.

    ⚠️ 이름만 본다 — 본문(where 절 등)까지는 대조하지 못한다. 2026-08-22a 처럼
       기존 뷰의 where 절만 바꾸는 변경은 이 가드로 못 잡으니 사람이 맞춰야 한다.
       그래도 "새 뷰를 만들고 정본에 안 옮긴 것"은 여기서 걸린다.
    """
    alive, _ = replay(RE_CREATE_VIEW, RE_DROP_VIEW)
    missing = sorted(n for n in alive if not schema_has_view(schema_sql, n))
    assert not missing, (
        "마이그레이션에는 있는데 schema.sql 에 없는 뷰: {}\n"
        "→ 이 파일로 새 환경을 만들면 그 뷰가 없어 화면이 401/빈칸이 됩니다.".format(missing)
    )


def schema_has_matview(schema, name):
    return re.search(
        r"(?im)^create\s+materialized\s+view\s+(?:if\s+not\s+exists\s+)?"
        r"{}{}\b".format(SCHEMA_PREFIX, re.escape(name)),
        schema,
    )


def test_live_matviews_are_in_schema(schema_sql):
    """마이그레이션으로 만든 물질화뷰는 정본에도 있어야 한다.

    `create` 바로 뒤가 `materialized` 라 위 뷰 가드(RE_CREATE_VIEW)가 못 본다. 빠지면 이 파일로
    만든 새 환경에서 그 요약표가 아예 없어 검색·지역목록·각주가 통째로 깨진다.
    """
    alive, _ = replay(RE_CREATE_MATVIEW, RE_DROP_MATVIEW, RE_RENAME_MATVIEW)
    missing = sorted(n for n in alive if not schema_has_matview(schema_sql, n))
    assert not missing, (
        "마이그레이션에는 있는데 schema.sql 에 없는 물질화뷰: {}\n"
        "→ 이 파일로 새 환경을 만들면 그 요약표가 없어 검색·각주가 통째로 깨집니다.".format(
            missing
        )
    )


def test_dropped_views_are_gone_from_schema(schema_sql):
    """마이그레이션에서 지운 뷰가 정본에 남아 있으면 안 된다."""
    _, dropped = replay(RE_CREATE_VIEW, RE_DROP_VIEW)
    zombies = sorted(n for n in dropped if schema_has_view(schema_sql, n))
    assert not zombies, (
        "라이브에서 지운 뷰가 schema.sql 에 남아 있습니다: {}".format(zombies)
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
    alive, dropped = replay(RE_CREATE_INDEX, RE_DROP_INDEX, RE_RENAME_INDEX)
    # 11e 가 만든 셋 중 idx_building_nm_key 는 지금도 살아 있다 — 빈 집합 통과를 막는 기준점.
    assert "idx_building_nm_key" in alive, "재생이 11e 가 만든 idx_building_nm_key 를 못 봤습니다"
    # 나머지 둘(parcel 주소 색인)은 11e 가 만들고 2026-10-01b 가 지웠다. 11e 파일 안에서 '만들었다'를
    # 직접 읽고, 끝까지 재생하면 '지웠다'로 나와야 한다 — 둘 중 하나만 보면 반쪽 가드다.
    e = read(os.path.join(MIG_DIR, "2026-08-11e_search_key_stored.sql"))
    made_in_11e = {m.group(1) for m in RE_CREATE_INDEX.finditer(e)}
    for name in ("idx_parcel_road_key", "idx_parcel_jibun_key"):
        assert name in made_in_11e, "재생이 11e 가 만든 {} 를 못 봤습니다".format(name)
        assert name in dropped, "재생이 10-01b 가 지운 {} 를 못 봤습니다".format(name)
        assert name not in alive, "{} 가 10-01b 로 지워졌는데 살아 있다고 나옵니다".format(name)
    for name in ("idx_building_display_nm", "idx_parcel_road_addr", "idx_parcel_jibun_addr"):
        assert name in dropped, "재생이 11e 가 지운 {} 를 못 봤습니다".format(name)
        assert name not in alive, "{} 가 지워졌는데 살아 있다고 나옵니다".format(name)

    fns, _ = replay(RE_CREATE_FN, RE_DROP_FN)
    assert "search_key" in fns, "재생이 11c 의 search_key 를 못 봤습니다"

    views, _ = replay(RE_CREATE_VIEW, RE_DROP_VIEW)
    assert "v_coverage_stats" in views, "재생이 뷰(v_coverage_stats)를 못 봤습니다"

    # 물질화뷰 정규식도 헛돌면 안 된다 — 지금까지 만든 4개가 전부 잡혀야 한다.
    mvs, _ = replay(RE_CREATE_MATVIEW, RE_DROP_MATVIEW, RE_RENAME_MATVIEW)
    for name in ("mv_search_parcel", "mv_open_sigungu", "mv_sigungu_tx_stats",
                 "mv_coverage_stats"):
        assert name in mvs, "재생이 물질화뷰 {} 를 못 봤습니다".format(name)


def test_replay_actually_sees_the_2026_10_07a_matview_swap(schema_sql):
    """10-07a 의 '_next 로 굽고 → 옛 것 drop → 정본 이름으로 rename'(물질화뷰 셋 + 색인 다섯)을 읽는가.

    ⛔ 되짚기가 물질화뷰 이름 바꾸기를 모르면 _next 가 산 것으로 남고 정본 이름은 '지운 것'으로
       남는다 — 아래 대조군이 그 상태를 직접 보여 준다(가드가 헛돌지 않는다는 증거).
    """
    swapped = ("mv_parcel_store_names", "mv_district_industry_mix", "mv_coverage_stats")
    mvs, dropped = replay(RE_CREATE_MATVIEW, RE_DROP_MATVIEW, RE_RENAME_MATVIEW)
    for name in swapped:
        assert name in mvs and name not in dropped, name
        assert name + "_next" not in mvs, name + "_next 가 살아 있다고 나옵니다"
        assert name + "_next" in dropped
        assert not schema_has_matview(schema_sql, name + "_next"), "정본에 _next 가 남았습니다"
    # 대조군 — 이름 바꾸기를 빼고 되짚으면 _next 가 산 것으로, 정본 이름이 지운 것으로 남는다.
    mvs_wo, dropped_wo = replay(RE_CREATE_MATVIEW, RE_DROP_MATVIEW)
    assert {n + "_next" for n in swapped} <= mvs_wo
    assert set(swapped) <= dropped_wo
    idx, idx_dropped = replay(RE_CREATE_INDEX, RE_DROP_INDEX, RE_RENAME_INDEX)
    for name in ("idx_mpsn_pnu", "idx_mpsn_sigungu", "idx_mpsn_names", "idx_mcs_snapshot_ym",
                 "mv_district_industry_mix_key"):
        assert name in idx and name + "_next" not in idx, name
        assert schema_has_index(schema_sql, name)


@pytest.mark.parametrize("sql,expect", [
    ("alter materialized view mv_a_next rename to mv_a", ("mv_a_next", "mv_a")),          # 흔한 꼴
    ("ALTER  MATERIALIZED VIEW  public.mv_a_next\n RENAME TO mv_a", ("mv_a_next", "mv_a")),  # 변형 꼴
    ("alter materialized view if exists mv_a_next rename to mv_a", ("mv_a_next", "mv_a")),
])
def test_rename_matview_regex_sees_both_forms(sql, expect):
    assert [m.groups() for m in RE_RENAME_MATVIEW.finditer("select 1;\n" + sql)] == [expect]


@pytest.mark.parametrize("sql", [
    "-- alter materialized view mv_a_next rename to mv_a",   # 설명 주석 속 인용
    "alter materialized view mv_a rename column x to y",     # 칸 이름 바꾸기는 표 이름 바꾸기가 아니다
    "alter view v_a rename to v_b",                          # 일반 뷰
])
def test_rename_matview_regex_leaves_the_rest_alone(sql):
    assert list(RE_RENAME_MATVIEW.finditer("select 1;\n" + sql)) == []


def test_replay_actually_sees_the_2026_09_27e_concurrent_swap():
    """27e 의 '새 이름으로 만들고 → 옛 것을 concurrently 로 지우고 → 이름을 되돌리기'를 읽어내는가.

    ⛔ 되짚기가 이름 바꾸기를 모르면 v2 가 살아 있는 것으로 남고, `drop index concurrently` 를
       모르면 'concurrently' 라는 이름을 지운 것으로 적는다 — 둘 다 에러 없이 헛돈다.
    """
    alive, dropped = replay(RE_CREATE_INDEX, RE_DROP_INDEX, RE_RENAME_INDEX)
    assert "idx_arch_permit_pnu" in alive
    assert "idx_arch_permit_pnu" not in dropped, "이름을 되돌린 인덱스가 '지운 것'으로 남았습니다"
    assert "idx_arch_permit_pnu_v2" not in alive, "이름을 바꾼 v2 가 살아 있다고 나옵니다"
    assert "concurrently" not in dropped, "`concurrently` 를 인덱스 이름으로 잡고 있습니다"
    # 이름 바꾸기를 빼고 되짚으면 v2 가 남는다 — 위 단언이 헛돌지 않는다는 대조군.
    alive_wo, _ = replay(RE_CREATE_INDEX, RE_DROP_INDEX)
    assert "idx_arch_permit_pnu_v2" in alive_wo
    # 바꾸기 전 이름(v2)은 '라이브에서 사라진 이름'으로 기록돼야 한다 — 정본에 남으면 좀비.
    assert "idx_arch_permit_pnu_v2" in dropped


def test_a_renamed_away_index_left_in_schema_is_a_zombie(schema_sql):
    """정본에 바꾸기 전 이름(v2)이 남아 있으면 좀비 가드가 빨강이어야 한다 — 가짜 정본으로 확인."""
    _, dropped = replay(RE_CREATE_INDEX, RE_DROP_INDEX, RE_RENAME_INDEX)
    fake = schema_sql + (
        "\ncreate index if not exists idx_arch_permit_pnu_v2 on arch_permit (pnu);\n")
    zombies = sorted(n for n in dropped if schema_has_index(fake, n))
    assert "idx_arch_permit_pnu_v2" in zombies
    # 진짜 정본에는 없다(평소 초록).
    assert not schema_has_index(schema_sql, "idx_arch_permit_pnu_v2")


def test_replay_reads_schema_qualified_names():
    """`api.` 접두가 붙은 객체의 **이름**을 제대로 읽어내는가 (2026-08-22e).

    접두를 모르는 정규식은 `create or replace view api.parcel` 에서 이름을 **"api"** 로
    잡는다. 그러면 22e 가 만든 12개 뷰·9개 함수가 전부 "api" 한 이름으로 뭉개져,
    정본에서 빠진 것이 있어도 가드가 조용히 통과한다. 그 상태를 직접 막는다.
    """
    views, _ = replay(RE_CREATE_VIEW, RE_DROP_VIEW)
    assert "api" not in views, (
        "정규식이 스키마 접두를 이름으로 잘못 잡고 있습니다 — SCHEMA_PREFIX 를 확인하세요"
    )
    for name in ("parcel", "unit_business", "transaction", "bjd_code"):
        assert name in views, "재생이 22e 의 pass-through 뷰 {} 를 못 봤습니다".format(name)

    fns, _ = replay(RE_CREATE_FN, RE_DROP_FN)
    assert "api" not in fns, (
        "정규식이 스키마 접두를 이름으로 잘못 잡고 있습니다 — SCHEMA_PREFIX 를 확인하세요"
    )


# ── 양성 대조 — 탐지(정규식·schema_has_*)가 `or replace` 없는 꼴도 실제로 잡는가 (2026-10-03) ──
#
# "정본에 없는 것 = 0개"만 단언하는 시험은 탐지가 죽어도 초록이다. 가드 본체와 **같은
# 정규식·같은 함수**에 나쁜 예를 넣어 걸리는지 본다(흔한 꼴 + 변형 꼴).


@pytest.mark.parametrize("sql", [
    "create or replace function foo(x int)",          # 흔한 꼴
    "create function public.foo(x int)",              # or replace 없는 꼴(예전엔 못 봤다)
    "CREATE  OR  REPLACE\n FUNCTION api.foo (x int)",  # 대소문자·공백 변형
])
def test_create_fn_regex_sees_both_forms(sql):
    assert [m.group(1) for m in RE_CREATE_FN.finditer("select 1;\n" + sql)] == ["foo"]


@pytest.mark.parametrize("sql", [
    "create or replace view bar as select 1",
    "create view api.bar as select 1",
    "Create View public.bar as select 1",
])
def test_create_view_regex_sees_both_forms(sql):
    assert [m.group(1) for m in RE_CREATE_VIEW.finditer("select 1;\n" + sql)] == ["bar"]


@pytest.mark.parametrize("sql", [
    "create materialized view mv_x as select 1",      # 물질화 뷰는 뷰로 세지 않는다
    "create materialized view if not exists mv_x as select 1",
    "-- create view bar as select 1",                  # 설명 주석 속 인용
    "  create view bar as select 1",                   # 들여쓴 꼴(일부러 둔 한계)
])
def test_create_view_regex_leaves_the_rest_alone(sql):
    assert list(RE_CREATE_VIEW.finditer("select 1;\n" + sql)) == []


def test_replay_now_sees_the_bare_create_function_of_2026_08_11():
    """실제 원장 한 줄 — 08-11 의 `create function search_buildings(`(or replace 없음)를 읽는가."""
    body = read(os.path.join(MIG_DIR, "2026-08-11_search_by_jibun.sql"))
    assert "search_buildings" in {m.group(1) for m in RE_CREATE_FN.finditer(body)}


@pytest.mark.parametrize("schema", [
    "create or replace function foo(x int) returns int",
    "create function public.foo(x int) returns int",
    "create function foo (x int) returns int",
])
def test_schema_has_fn_sees_both_forms(schema):
    assert schema_has_fn("select 1;\n" + schema, "foo")


@pytest.mark.parametrize("schema", [
    "create function foo_v2(x int)",       # 이름이 앞부분만 같은 다른 함수
    "-- create function foo(x int)",
    "drop function if exists foo(int);",
])
def test_schema_has_fn_leaves_the_rest_alone(schema):
    assert not schema_has_fn("select 1;\n" + schema, "foo")


@pytest.mark.parametrize("schema", [
    "create or replace view bar as select 1",
    "create view api.bar as select 1",
])
def test_schema_has_view_sees_both_forms(schema):
    assert schema_has_view("select 1;\n" + schema, "bar")


@pytest.mark.parametrize("schema", [
    "create materialized view bar as select 1",   # 물질화 뷰는 뷰가 아니다
    "create view bar_v2 as select 1",
    "-- create view bar as select 1",
])
def test_schema_has_view_leaves_the_rest_alone(schema):
    assert not schema_has_view("select 1;\n" + schema, "bar")


def test_a_bare_created_function_missing_from_schema_turns_the_guard_red(schema_sql):
    """마이그레이션에만 `create function public.zz_only_in_mig(` 가 있으면 '빠진 함수'로 나와야 한다."""
    mig = "create function public.zz_only_in_mig(x int) returns int language sql as $$ select 1 $$;"
    alive = {m.group(1) for m in RE_CREATE_FN.finditer(mig)}
    assert sorted(n for n in alive if not schema_has_fn(schema_sql, n)) == ["zz_only_in_mig"]


def test_a_bare_created_view_missing_from_schema_turns_the_guard_red(schema_sql):
    """마이그레이션에만 `create view api.zz_only_in_mig as` 가 있으면 '빠진 뷰'로 나와야 한다."""
    mig = "create view api.zz_only_in_mig as select 1;"
    alive = {m.group(1) for m in RE_CREATE_VIEW.finditer(mig)}
    assert sorted(n for n in alive if not schema_has_view(schema_sql, n)) == ["zz_only_in_mig"]


def test_a_dropped_view_left_as_bare_create_view_is_a_zombie(schema_sql):
    """지운 뷰가 정본에 `create view x as`(or replace 없이)로 남아 있어도 좀비로 잡혀야 한다."""
    fake = schema_sql + "\ncreate view zz_dropped_view as select 1;\n"
    assert schema_has_view(fake, "zz_dropped_view")
    assert not schema_has_view(schema_sql, "zz_dropped_view")
