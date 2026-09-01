# -*- coding: utf-8 -*-
"""정본(schema.sql)의 **표마다** 지켜져야 하는 것들을 기계로 대조한다.

왜 이 파일이 새로 필요했나 (2026-09-01 감사)
--------------------------------------------
`price_gate_sigungu` 하나만 `enable row level security` 가 빠져 있었다. 표 17개 중 16개에만
걸려 있었는데 **아무도 몰랐다** — 표마다 따로 시험을 두는 구조(test_arch_permit_migration.py ·
test_lh_notice_migration.py …)라, 새 표를 만들며 잊으면 그 표를 보는 시험 자체가 없기 때문이다.
실제로 그 줄을 지워 봐도 pytest 2,300여 개가 전부 초록이었다(돌연변이 검증으로 확인).

⇒ **표를 하나 더 만들 때 자동으로 걸리는 그물**이 있어야 한다. 이 파일이 그 그물이다.

여기서 보는 것
--------------
  1) 모든 `create table` 에 대응하는 `enable row level security` 가 있다.
     ⛔ RLS 는 이중 잠금의 한 겹이다. 권한 회수(`revoke`)가 첫 겹인데, Supabase 는 새 객체에
        anon 권한을 자동으로 붙이는 경로가 있어(pg_default_acl — 2026-08-13 mv_search_parcel
        실사고) 한 겹만으로는 부족하다.
  2) 모든 `create table` 이 공개 롤에서 회수된다(`revoke ... from public, anon, authenticated`).
  3) 정책(`create policy`)을 만들지 않는다 — "RLS 켬 + 정책 0개" 가 곧 전부 거부다.

⚠️ 이 파일은 DB 없이 **글자만** 본다(CI 에 DB 가 없다). 라이브가 실제로 그런지는
   `python scripts/post_load.py --check` 소관이다. 둘은 대체 관계가 아니라 서로를 메운다.
"""

import io
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def statements(sql):
    """주석을 걷어낸 **실제 문장만**.

    ⚠️ 이걸 안 하면 설명 주석에 적어 둔 말이 문장으로 오해된다 — 이 레포는 주석 밀도가
       높아서 실제로 그 사고가 났다(2026-09-01: "current_date 로 되돌리지 말 것"이라는
       경고문 자체가 `assert "current_date" not in body` 에 걸렸다).
    """
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def schema():
    return statements(read(SCHEMA))


def tables_in(sql):
    return sorted(set(re.findall(r"(?im)^create\s+table\s+(?:if\s+not\s+exists\s+)?(\w+)", sql)))


def rls_enabled_in(sql):
    return sorted(set(re.findall(
        r"(?im)^alter\s+table\s+(\w+)\s+enable\s+row\s+level\s+security", sql)))


class TestEveryTableHasRls:
    def test_no_table_is_missing_rls(self, schema):
        """⛔ 새 표를 만들며 RLS 를 잊으면 **여기서** 걸린다.

        되돌리면(어느 표든 alter 줄을 지우면) 이 시험이 그 표 이름을 대며 빨간불이 된다.
        """
        missing = sorted(set(tables_in(schema)) - set(rls_enabled_in(schema)))
        assert not missing, (
            "RLS 선언이 빠진 표: {}\n"
            "  → `alter table <표> enable row level security;` 를 그 표를 만드는 자리 근처에 "
            "추가하세요(정책은 만들지 않습니다 — RLS 켬 + 정책 0개가 곧 전부 거부입니다)."
            .format(missing)
        )

    def test_no_rls_line_points_at_a_missing_table(self, schema):
        """반대 방향도 본다 — 표를 지웠는데 RLS 줄만 남으면 새 창고 세우기가 통째로 실패한다."""
        orphan = sorted(set(rls_enabled_in(schema)) - set(tables_in(schema)))
        assert not orphan, "표가 없는데 RLS 를 거는 줄: {}".format(orphan)

    def test_the_guard_itself_would_catch_a_removal(self, schema):
        """⛔ **이 가드가 진짜 무는지**를 시험 안에서 한 번 더 확인한다.

        정규식이 헛돌면(예: 대소문자·`if not exists` 변형을 놓치면) 위 두 시험은 표를
        하나도 못 찾고 조용히 초록이 된다 — 이 레포가 가장 여러 번 데인 '가짜 초록'이다.
        """
        assert len(tables_in(schema)) >= 17, "표를 못 찾고 있습니다 — 정규식이 헛돕니다."
        broken = schema.replace(
            "alter table price_gate_sigungu enable row level security;", "", 1)
        assert "price_gate_sigungu" in (set(tables_in(broken)) - set(rls_enabled_in(broken)))


class TestEveryTableIsClosedToPublicRoles:
    """표는 밖에서 잠근다 — 화면은 정의자 함수로만 읽는다.

    ⚠️ 닫는 방식이 **두 가지**다. 하나만 요구하는 시험을 쓰면 거짓 경보가 되고, 거짓 경보를
       내는 시험은 곧 무시된다(그래서 실제 구조를 그대로 반영한다):
         ① 일괄 스윕 `revoke all on all tables in schema public from anon, authenticated;`
            — 그 줄을 **지날 때 이미 있던** 표만 닫는다(일회성).
         ② 만든 자리에서 개별 `revoke all on <표> from public, anon, authenticated;`
            — 스윕 **뒤에** 만들어지는 표는 이것뿐이라, 빠뜨리면 그 표만 조용히 열린다.
       라이브 실측(2026-09-01): 표 17개 전부 anon 읽기 0건 — 두 방식이 함께 덮고 있다.
    """

    SWEEP = "revoke all on all tables in schema public from anon, authenticated;"

    def test_the_bulk_sweep_exists(self, schema):
        """스윕이 사라지면 그 앞의 표들이 통째로 무방비가 된다."""
        assert self.SWEEP in schema

    def test_tables_created_after_the_sweep_are_revoked_individually(self, schema):
        """⛔ **스윕 뒤에 만들어진 표**는 개별 회수가 유일한 방어다.

        스윕은 그 줄을 지날 때의 표만 닫는 일회성 명령이라(정본 주석이 네 곳에서 그렇게
        경고한다), 뒤에 오는 표는 만든 자리에서 스스로 닫아야 한다.
        """
        assert self.SWEEP in schema, "스윕이 없으면 이 시험의 전제가 성립하지 않는다"
        after = schema[schema.index(self.SWEEP):]
        revoked = set(re.findall(
            r"(?im)^revoke\s+all\s+on\s+(\w+)\s+from\s+public,\s*anon,\s*authenticated", schema))
        missing = sorted(set(tables_in(after)) - revoked)
        assert not missing, (
            "스윕 뒤에 만들어졌는데 개별 회수가 없는 표: {}\n"
            "  → 그 표를 만드는 자리 근처에 "
            "`revoke all on <표> from public, anon, authenticated;` 를 추가하세요."
            .format(missing)
        )


class TestNoPolicies:
    def test_schema_creates_no_policy(self, schema):
        """정책을 하나라도 만들면 '정책 0개 = 전부 거부' 전제가 깨진다 — 그때는 그 정책이
        무엇을 여는지 사람이 따져야 하므로, 조용히 늘어나지 않게 막는다."""
        found = re.findall(r"(?im)^create\s+policy\s+(\S+)", schema)
        assert not found, "정본이 정책을 만듭니다: {}".format(found)
