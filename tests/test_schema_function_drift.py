# -*- coding: utf-8 -*-
"""정본(schema.sql)의 함수 본문이 **가장 최근 마이그레이션**과 글자 그대로 같은가.

왜 이 파일이 새로 필요했나 (2026-09-01 2차 적대검증)
----------------------------------------------------
`list_lh_notices` 의 정본 본문 주석 5줄이 라이브(`pg_proc.prosrc`)와 달랐다. **드리프트를
잡겠다는 작업이 같은 종류의 드리프트를 새로 남긴 것**이다.

이게 왜 사소하지 않은가:

  · **함수 본문 주석은 라이브에 실린다.** `create function … as $$ … $$` 의 `$$` 안쪽은
    통째로 `pg_proc.prosrc` 에 저장된다. 즉 주석도 라이브의 일부다 — 파일 위 머리말 주석
    (`create` 문 **바깥**)과는 성질이 전혀 다르다.
  · 그래서 "정본만 살짝 다듬었다"가 **곧 정본↔라이브 불일치**가 된다. 다음 사람이 정본을
    믿고 "라이브도 이렇겠지" 하는 순간 틀린 전제 위에서 일하게 된다.
  · 이 레포는 실제로 이 함정을 **두 번** 밟았다(01a 가 COMMENT 를 빠뜨린 것, 그리고 이번).

기존 가드가 왜 못 잡았나
------------------------
`tests/test_lh_notice_migration.py` 는 **특정 부분문자열**만 본다(`"접수마감" in body` 등).
그러면 문장이 맞는 한 주석이 아무리 갈라져도 초록이다. ⇒ **전체 대조**가 필요하다.

무엇을 보나
-----------
마이그레이션 파일들에서 `create or replace function <이름>` 을 전부 걷어, **이름마다 가장
최근 파일**의 본문을 정본의 같은 함수 본문과 글자 단위로 맞춘다.

⚠️ 한계 (정직하게 적어 둔다)
  · **글자만 본다.** 라이브에 그 마이그레이션이 실제로 적용됐는지는 안 본다(CI 에 DB 가 없다).
    그건 사람이 적용하며 확인할 몫이고, 이 시험은 "적용한 것과 정본이 같은가"만 지킨다.
  · 마이그레이션이 없는 함수(정본에서만 태어난 것)는 대조 대상이 아니다 — 비교할 짝이 없다.
  · 파일명 날짜순으로 '최근'을 정한다. 이 레포의 마이그레이션은 `YYYY-MM-DD?_설명.sql`
    형식이라 이름 정렬이 곧 시간순이다.
"""

import io
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIG_DIR = os.path.join(ROOT, "supabase", "migrations")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

DOLLAR = chr(36) * 2
# `create or replace function <이름>( … ) … as $$ <본문> $$;`
FN_RE = re.compile(
    r"create\s+or\s+replace\s+function\s+([\w.]+)\s*\(.*?"
    + re.escape(DOLLAR) + r"(.*?)" + re.escape(DOLLAR) + r"\s*;",
    re.S | re.I,
)


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def bodies(sql):
    """이름 → 본문(마지막 정의가 이긴다 — 한 파일 안에서 두 번 정의하면 뒤가 실제 동작)."""
    out = {}
    for m in FN_RE.finditer(sql):
        out[m.group(1).strip().lower()] = m.group(2)
    return out


def norm(body):
    """줄바꿈 표기(CRLF/LF)만 통일한다.

    ⛔ 공백·주석은 **일부러 안 건드린다.** 이 시험의 목적이 바로 "주석 한 글자까지 같은가"다.
       여기서 주석을 걷어내면 이번에 잡은 그 드리프트를 다시 못 본다.
    """
    return body.replace("\r\n", "\n")


@pytest.fixture(scope="module")
def latest_migration_bodies():
    """마이그레이션 전체에서 함수 이름 → (가장 최근 파일명, 본문)."""
    out = {}
    for name in sorted(os.listdir(MIG_DIR)):
        if not name.endswith(".sql"):
            continue
        for fn, body in bodies(read(os.path.join(MIG_DIR, name))).items():
            out[fn] = (name, body)      # 정렬이 시간순 → 뒤가 이긴다
    return out


@pytest.fixture(scope="module")
def schema_bodies():
    return bodies(read(SCHEMA))


class TestCanonicalMatchesTheLatestMigration:
    def test_the_parser_finds_functions_at_all(self, schema_bodies, latest_migration_bodies):
        """⛔ **파서가 헛돌면 아래 시험들이 조용히 초록이 된다** — 이 레포가 가장 여러 번
        데인 '가짜 초록'이다. 그래서 개수를 먼저 못 박는다."""
        assert len(schema_bodies) >= 30, (
            "정본에서 함수를 {}개밖에 못 찾았습니다 — 정규식이 헛돕니다.".format(len(schema_bodies)))
        assert len(latest_migration_bodies) >= 5, (
            "마이그레이션에서 함수를 {}개밖에 못 찾았습니다."
            .format(len(latest_migration_bodies)))

    def test_every_migrated_function_matches_canonical(
            self, schema_bodies, latest_migration_bodies):
        """⛔ 마이그레이션으로 라이브에 올린 본문과 정본이 **글자 그대로** 같아야 한다.

        다르면 정본을 믿는 사람이 라이브와 다른 것을 보게 된다. 함수 본문 주석은
        `pg_proc.prosrc` 에 실려 라이브의 일부가 되기 때문이다.
        """
        drifted = []
        for fn, (mig_name, mig_body) in sorted(latest_migration_bodies.items()):
            if fn not in schema_bodies:
                continue          # 마이그레이션에서 지운 함수 등 — 여기 대상 아님
            if norm(schema_bodies[fn]) != norm(mig_body):
                drifted.append((fn, mig_name))
        assert not drifted, (
            "정본과 마이그레이션의 함수 본문이 다릅니다 (주석 포함): {}\n"
            "  → 마이그레이션 쪽이 라이브에 실린 것입니다. 정본 본문을 그 파일에서 **글자 그대로** "
            "복사해 오세요. 설명을 늘리고 싶으면 `create` 문 **바깥** 머리말 주석에 적습니다 "
            "(본문에 넣으면 그 순간 라이브와 어긋납니다)."
            .format(drifted)
        )

    def test_this_guard_would_catch_a_one_character_change(
            self, schema_bodies, latest_migration_bodies):
        """⛔ **가드가 진짜 무는지**를 시험 안에서 확인한다 — 주석 한 글자만 바꿔도 걸려야 한다."""
        shared = [f for f in latest_migration_bodies if f in schema_bodies]
        assert shared, "대조할 짝이 하나도 없습니다 — 파서나 파일 배치가 바뀌었습니다."
        fn = sorted(shared)[0]
        tampered = norm(schema_bodies[fn]) + " "
        assert tampered != norm(latest_migration_bodies[fn][1])
