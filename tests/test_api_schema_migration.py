# -*- coding: utf-8 -*-
"""마이그레이션 2026-08-22e(api 스키마)의 불변식을 지킨다.

여기서 막는 것은 **"라이브에 붙여 넣기 전에는 아무도 모르는" 종류의 실수**다. 이 파일은
DB 없이 SQL 글자만 본다(CI 에는 DB 가 없다) — 대신 아래 넷은 글자만으로 확실히 잡힌다:

  1) 래퍼 함수에서 `security definer` 가 빠짐
     → public 쪽 권한을 나중에 회수하는 순간 화면이 401 이 된다(그날까지는 멀쩡히 돈다).
  2) `set search_path = ''` 가 빠짐
     → security definer 함수가 검색경로에 휘둘린다. 표준 방어를 잃는다.
  3) 본문의 `public.` 완전수식이 빠짐
     → 검색경로가 비어 있으므로 **호출하는 순간** "함수 없음"이다.
  4) 수집기용 뷰에 `revoke` 가 빠짐
     → Supabase 가 새 객체를 anon 에 자동 개방한다(pg_default_acl). 상호명·실거래가
       통째로 새고, 그 사실은 `post_load.py --check` 가 라이브에서야 알려 준다.

⚠️ 한계: 정의 본문이 원본과 같은 결과를 내는지까지는 못 본다. 그건 라이브에서만 확인된다.
"""

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-08-22e_api_schema.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

# 화면이 부르는 함수 9개·읽는 뷰 2개 = post_load 의 anon 허용 목록 **그 자체**.
# 손으로 다시 적으면 화면 함수가 하나 늘 때 두 목록이 갈라지고, 실패 메시지가
# 진짜 원인(허용 목록 드리프트)을 가리키지 않는다 — 그래서 import 로 한 곳만 진실.
SCREEN_FNS = post_load.ANON_CALLABLE_ALLOWLIST
SCREEN_VIEWS = post_load.ANON_READABLE_ALLOWLIST

# 수집·적재기가 REST 로 쓰는 표 10개(scripts/ 를 훑어 뽑은 목록).
COLLECTOR_VIEWS = (
    "parcel",
    "building",
    "unit",
    "building_floor",
    "unit_business",
    "transaction",
    "rent_stat",
    "collect_progress",
    "api_quota_log",
    "bjd_code",
)

RE_API_FN = re.compile(r"(?im)^create\s+or\s+replace\s+function\s+api\.(\w+)")
RE_API_VIEW = re.compile(r"(?im)^create\s+or\s+replace\s+view\s+api\.(\w+)")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def migration():
    return read(MIGRATION)


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


def function_bodies(sql):
    """`create or replace function api.X ... as $$ ... $$;` 를 이름→(머리, 본문)으로."""
    out = {}
    for m in re.finditer(
        r"(?is)^create\s+or\s+replace\s+function\s+api\.(\w+)\s*\((.*?)\)\s*"
        r"(.*?)as\s*\$\$(.*?)\$\$\s*;",
        sql,
        re.MULTILINE,
    ):
        out[m.group(1)] = (m.group(3), m.group(4))
    return out


@pytest.fixture(scope="module")
def parsed_fns(migration):
    """파싱은 한 번만 — 파라미터라이즈드 테스트 9개×2종이 같은 텍스트를 재파싱하지 않게."""
    return function_bodies(migration)


class TestScreenFunctions:
    def test_all_nine_screen_functions_are_wrapped(self, migration):
        got = set(RE_API_FN.findall(migration))
        assert got == set(SCREEN_FNS), (
            "api 래퍼 함수 목록이 화면이 부르는 9개와 다릅니다: {}".format(sorted(got))
        )

    @pytest.mark.parametrize("name", SCREEN_FNS)
    def test_wrapper_is_security_definer_with_empty_search_path(self, parsed_fns, name):
        head, _ = parsed_fns[name]
        assert "security definer" in head.lower(), (
            "{} 에 security definer 가 없습니다 — public 쪽을 닫는 날 화면이 401 이 됩니다"
            .format(name)
        )
        assert re.search(r"set\s+search_path\s*=\s*''", head), (
            "{} 에 set search_path = '' 가 없습니다".format(name)
        )

    @pytest.mark.parametrize("name", SCREEN_FNS)
    def test_wrapper_body_is_schema_qualified(self, parsed_fns, name):
        _, body = parsed_fns[name]
        assert "public.{}(".format(name) in body, (
            "{} 의 본문이 public. 으로 완전수식돼 있지 않습니다 — 검색경로가 비어 있어 "
            "호출하는 순간 '함수 없음'이 됩니다".format(name)
        )

    @pytest.mark.parametrize("name", SCREEN_FNS)
    def test_wrapper_is_granted_to_anon(self, migration, name):
        assert re.search(
            r"grant\s+execute\s+on\s+function\s+api\.{}\s*\(".format(re.escape(name)),
            migration,
            re.IGNORECASE,
        ), "{} 에 anon 실행 권한을 안 줬습니다 — 화면이 못 부릅니다".format(name)

    @pytest.mark.parametrize("name", SCREEN_FNS)
    def test_wrapper_revoke_names_anon_too(self, migration, name):
        """뷰들과 같은 대칭 방어 — `from public` 만으로는 대시보드(supabase_admin)가
        같은 함수를 재생성했을 때 자동으로 붙는 anon 권한을 못 걷는다(2026-08-10 결)."""
        assert re.search(
            r"revoke\s+all\s+on\s+function\s+api\.{}\s*\([^)]*\)\s+"
            r"from\s+public,\s*anon,\s*authenticated".format(re.escape(name)),
            migration,
            re.IGNORECASE,
        ), "api.{} 의 revoke 가 public 만 회수합니다 — anon·authenticated 도 명시".format(name)


class TestViews:
    def test_view_list_is_exactly_what_we_meant(self, migration):
        got = set(RE_API_VIEW.findall(migration))
        assert got == set(SCREEN_VIEWS) | set(COLLECTOR_VIEWS), (
            "api 뷰 목록이 의도와 다릅니다: {}".format(sorted(got))
        )

    @pytest.mark.parametrize("name", COLLECTOR_VIEWS)
    def test_collector_views_are_closed_to_anon(self, migration, name):
        """⛔ 가장 위험한 실수. 빠지면 Supabase 기본 권한이 그대로 anon 에 열어 준다."""
        assert re.search(
            r"revoke\s+all\s+on\s+api\.{}\s+from\s+public,\s*anon,\s*authenticated".format(
                re.escape(name)
            ),
            migration,
            re.IGNORECASE,
        ), "api.{} 에 revoke 가 없습니다 — 상호명·실거래가 통째로 샐 수 있습니다".format(name)

    @pytest.mark.parametrize("name", COLLECTOR_VIEWS)
    def test_collector_views_are_writable_by_service_role(self, migration, name):
        assert re.search(
            r"grant\s+select,\s*insert,\s*update,\s*delete\s+on\s+api\.{}\s".format(
                re.escape(name)
            ),
            migration,
            re.IGNORECASE,
        ), "api.{} 에 service_role 쓰기 권한이 없습니다 — 적재기가 멈춥니다".format(name)

    @pytest.mark.parametrize("name", SCREEN_VIEWS)
    def test_screen_views_revoke_before_grant(self, migration, name):
        """grant 는 더하기라, 자동으로 붙은 쓰기 권한을 못 걷어낸다(2026-08-22 라이브 사례)."""
        revoke = migration.find("revoke all on api.{}".format(name))
        grant = migration.find("grant select on api.{}".format(name))
        assert revoke != -1 and grant != -1, "{} 의 revoke/grant 짝이 없습니다".format(name)
        assert revoke < grant, "{} 는 회수를 먼저 하고 줘야 합니다".format(name)


class TestMigrationShape:
    def test_creates_schema_and_usage(self, migration):
        assert re.search(r"create\s+schema\s+if\s+not\s+exists\s+api", migration, re.I)
        assert re.search(
            r"grant\s+usage\s+on\s+schema\s+api\s+to\s+anon,\s*authenticated,\s*service_role",
            migration,
            re.I,
        )

    def test_tells_postgrest_to_reload(self, migration):
        assert "notify pgrst, 'reload schema';" in migration, (
            "스키마 캐시 리로드를 안 알리면 다음 재시작까지 404 가 납니다"
        )

    def test_recovery_sql_for_the_known_dashboard_drift_is_written_down(self, migration):
        """대시보드 저장이 런타임에 반영 안 되는 버그(supabase#45904)의 복구 SQL.

        머리말에서 지워지면, 그 상황에 빠진 다음 사람이 처음부터 다시 찾아야 한다.
        """
        assert "45904" in migration
        assert "pgrst.db_schemas" in migration


class TestSchemaSqlHasTheSameThing:
    """정본(schema.sql)에도 같은 것이 있어야 한다 — 한쪽만 고치면 조용히 갈라진다."""

    def test_functions(self, schema):
        got = set(RE_API_FN.findall(schema))
        assert got == set(SCREEN_FNS), "정본의 api 함수 목록이 다릅니다: {}".format(sorted(got))

    def test_views(self, schema):
        got = set(RE_API_VIEW.findall(schema))
        assert got == set(SCREEN_VIEWS) | set(COLLECTOR_VIEWS), (
            "정본의 api 뷰 목록이 다릅니다: {}".format(sorted(got))
        )
