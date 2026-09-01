# -*- coding: utf-8 -*-
"""api 스키마 마이그레이션들의 불변식을 지킨다(뿌리는 2026-08-22e).

⚠️ 보는 대상은 22e 하나가 아니라 **api 에 무언가를 만드는 마이그레이션 전부**다
   (api_migration_files 참조). 새 공개 함수는 새 파일에 생기는데, 이미 라이브에
   적용된 22e 를 고쳐 넣는 것은 역사 조작이기 때문이다.

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

# 화면이 부르는 함수·읽는 뷰 = post_load 의 anon 허용 목록 **그 자체**.
# ⚠️ 개수를 글자로 적지 않는다 — 공개 함수가 하나 늘 때마다 주석만 거짓말이 된다.
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

# ⚠️ `or replace` 를 **선택**으로 둔다. 필수로 두면 `create function api.xxx` 로 쓴
#    마이그레이션 하나가 이 보안 검사를 **통째로 빠져나간다** — 지금까지 레포 관습이
#    한결같았을 뿐, 문법상 언제든 쓸 수 있는 형태다(2026-08-24 적대검증 지적).
RE_API_FN = re.compile(r"(?im)^create\s+(?:or\s+replace\s+)?function\s+api\.(\w+)")
RE_API_VIEW = re.compile(r"(?im)^create\s+(?:or\s+replace\s+)?view\s+api\.(\w+)")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


MIGRATION_DIR = os.path.dirname(MIGRATION)
RE_MAKES_API_OBJECT = re.compile(r"(?im)^create\s+(?:or\s+replace\s+)?(function|view)\s+api\.")


def api_migration_files():
    """api 스키마에 무언가를 만드는 마이그레이션을 이름(=날짜)순으로 모은다.

    ⚠️ **22e 하나만 보면 안 된다.** 새 공개 함수는 새 마이그레이션에 생기는데, 이미
       라이브에 적용된 22e 를 고쳐 넣는 것은 역사 조작이다. 파일이 하나뿐이라고 가정하면
       공개 함수가 하나 늘 때마다 이 검사가 **"22e 에 없다"는 엉뚱한 이유로** 실패한다
       (2026-08-24b 의견함을 넣을 때 실제로 그랬다).

    이렇게 넓히면 검사가 약해지는 것이 아니라 **강해진다** — 어느 마이그레이션에서 만든
    api 객체든 security definer·빈 search_path·완전수식·revoke 를 똑같이 요구받는다.
    """
    out = []
    for name in sorted(os.listdir(MIGRATION_DIR)):
        if not name.endswith(".sql"):
            continue
        path = os.path.join(MIGRATION_DIR, name)
        if RE_MAKES_API_OBJECT.search(read(path)):
            out.append(path)
    return out


@pytest.fixture(scope="module")
def migration():
    """api 를 다루는 마이그레이션을 날짜순으로 이어 붙인 한 덩어리."""
    return "\n".join(read(p) for p in api_migration_files())


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


def function_bodies(sql):
    """`create or replace function api.X ... as $$ ... $$;` 를 이름→(머리, 본문)으로."""
    out = {}
    for m in re.finditer(
        r"(?is)^create\s+(?:or\s+replace\s+)?function\s+api\.(\w+)\s*\((.*?)\)\s*"
        r"(.*?)as\s*\$\$(.*?)\$\$\s*;",
        sql,
        re.MULTILINE,
    ):
        out[m.group(1)] = (m.group(3), m.group(4))
    return out


@pytest.fixture(scope="module")
def parsed_fns(migration):
    """파싱은 한 번만 — 함수마다 도는 검사들이 같은 텍스트를 거듭 파싱하지 않게."""
    return function_bodies(migration)


class TestScreenFunctions:
    def test_every_screen_function_is_wrapped(self, migration):
        got = set(RE_API_FN.findall(migration))
        assert got == set(SCREEN_FNS), (
            "api 래퍼 함수 목록이 화면이 부르는 것과 다릅니다: {}".format(sorted(got))
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
    def test_the_root_migration_is_actually_included(self):
        """⛔ 파일을 못 찾으면 위 검사들이 **빈 텍스트를 보며 조용히 지나갈** 수 있다.

        지금은 함수 목록 비교가 먼저 깨지지만, 그건 우연히 그런 것이다. 뿌리 파일이
        목록에 있다는 사실 자체를 못 박아 둔다.
        """
        assert MIGRATION in api_migration_files(), (
            "api 스키마의 뿌리 마이그레이션(2026-08-22e)이 목록에서 빠졌습니다"
        )

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


class TestGuardRegexHasNoHole:
    """이 파일의 검사는 정규식이 잡아낸 것에만 걸린다 — 정규식이 놓치면 검사도 없는 것과 같다."""

    def test_plain_create_function_is_still_caught(self):
        """⛔ `or replace` 없이 쓴 것도 잡아야 한다.

        지금까지 레포 관습이 한결같았을 뿐, 문법상 언제든 쓸 수 있는 형태다. 놓치면 그
        마이그레이션 하나가 security definer·search_path·revoke 검사를 통째로 빠져나간다
        (2026-08-24 적대검증 지적).
        """
        assert RE_API_FN.findall("create function api.sneaky(x text)") == ["sneaky"]
        assert RE_API_VIEW.findall("create view api.sneaky as select 1") == ["sneaky"]
        assert RE_MAKES_API_OBJECT.search("create function api.sneaky(x text)")

    def test_or_replace_form_still_works(self):
        """넓혔다고 원래 잡던 것을 놓치면 안 된다."""
        assert RE_API_FN.findall("create or replace function api.normal(x text)") == ["normal"]
        assert RE_MAKES_API_OBJECT.search("create or replace view api.normal as select 1")

    def test_other_schemas_are_not_caught(self):
        """api 스키마만 본다 — public 함수까지 걸리면 검사가 엉뚱한 것을 요구한다."""
        assert RE_API_FN.findall("create function public.normal(x text)") == []
        assert not RE_MAKES_API_OBJECT.search("create or replace function public.normal(x text)")


class TestDefaultPrivilegesActuallyBlockPublic:
    """⛔ 기본권한이 **PUBLIC 까지** 막는가 (2026-09-01 감사 후속).

    왜 이 시험이 필요한가
    ---------------------
    정본은 오랫동안 이렇게만 적어 뒀다:

        alter default privileges in schema api revoke all on functions from anon, authenticated;

    이건 **아무 일도 하지 않는다.** PostgreSQL 의 내장 기본값은 새 함수에 **PUBLIC 에게
    EXECUTE** 를 주는데(공식 문서 §5.8 표 5.2 — "FUNCTION or PROCEDURE: Default PUBLIC
    Privileges = X"), 그 기본값에 `anon`·`authenticated` 는 애초에 들어 있지 않다.
    없는 것을 회수하면 결과가 내장 기본값과 같아서 Postgres 는 항목조차 저장하지 않는다 —
    실제로 라이브 `pg_default_acl` 에 `api` 항목이 **0건**이었다(2026-09-01 실측).

    즉 `api` 는 그동안 "새 함수는 PUBLIC 에게 열림" 위에 서 있었다. 지금 함수들이 안전한
    것은 **만든 자리마다 사람이 revoke 를 기억해 왔기 때문**이지 기본 규칙 덕이 아니다.

    ⚠️ 이 시험은 글자만 본다(CI 에 DB 가 없다). 라이브 적용 여부는 마이그레이션
       `2026-09-01b` 와 `post_load.py --check` 소관이다.
    """

    GLOBAL = "alter default privileges revoke execute on functions from public;"

    def test_execute_is_revoked_from_public_globally(self, schema):
        """⛔ **전역 한 줄**이 있어야 한다 — 이게 유일하게 실제로 막는 문장이다."""
        assert self.GLOBAL in schema, (
            "정본에 '{}' 가 없습니다 — 이 줄이 빠지면 새 함수가 PUBLIC 에게 열린 채 태어납니다."
            .format(self.GLOBAL)
        )

    @pytest.mark.parametrize("schema_name", ["api", "public"])
    def test_the_useless_per_schema_form_never_comes_back(self, schema, schema_name):
        """⛔ **스키마별 형태로 되돌아가지 않는다 — 그건 아무 일도 안 한다.**

        공식 문서가 우리가 쓰던 그 문장을 그대로 '효과 없음' 예시로 든다:
          "This command has no effect, unless it is undoing a matching GRANT:
           ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;"
        스키마별 기본권한은 전역 기본값에 **더하기만** 할 뿐 빼지 못하기 때문이다.
        실제로 이 마이그레이션의 첫 판이 그 형태였고, 라이브에 적용해 보니 `pg_default_acl`
        에 항목조차 안 생겨 무효임이 드러났다. 그 자리로 돌아가면 여기서 잡는다.
        """
        useless = (
            "alter default privileges in schema {} revoke execute on functions from public;"
            .format(schema_name)
        )
        assert useless not in schema, (
            "'{}' 는 **아무 일도 하지 않습니다**(공식 문서의 '효과 없음' 예시). "
            "전역 형태('{}')를 쓰세요.".format(useless, self.GLOBAL)
        )

    def test_the_anon_authenticated_lines_are_kept_too(self, schema):
        """⛔ 옛 줄을 **지우지 않는다.** 지금은 무해하지만, 누가 기본권한에 그 둘을 넣는 날
        (Supabase 정책 변경·사람이 grant) 다시 일하게 된다. 둘은 대체 관계가 아니다."""
        for schema_name in ("api", "public"):
            assert (
                "alter default privileges in schema {} revoke all on functions from anon, authenticated;"
                .format(schema_name) in schema
            )


class TestSchemaUsageIsGrantedForBothSchemas:
    """⛔ 방을 여는 권한(usage)은 그 안의 물건을 쓰는 권한(execute)과 **별개 축**이다.

    `api` 에는 있고 `public` 에는 없어 비대칭이던 것을 2026-09-01 에 채웠다. 라이브는
    Supabase 가 깔아 준 상태라 멀쩡하지만(`nspacl` 에 anon=U 실측), 그건 물려받은 것이지
    정본이 말한 것이 아니다 — **정본만으로 새 창고를 세우면** anon 이 public 을 못 연다.
    """

    @pytest.mark.parametrize("schema_name", ["api", "public"])
    def test_usage_is_granted(self, schema, schema_name):
        assert (
            "grant usage on schema {} to anon, authenticated, service_role;".format(schema_name)
            in schema
        )
