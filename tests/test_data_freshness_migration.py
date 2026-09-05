# -*- coding: utf-8 -*-
"""마이그레이션 2026-09-05d(이 자료는 언제 것인가 — 푸터 신선도 표)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙여 넣기 전에는 아무도 모르는 종류의 실수**다.
DB 없이 SQL 글자만 본다(CI 에는 DB 가 없다) — 대신 아래는 글자만으로 확실히 잡힌다.

  1) 자료 한 갈래가 빠진다 → 화면의 표에서 그 줄이 조용히 사라지고, 보는 사람은
     "그런 자료는 안 쓰나 보다"로 읽는다. 에러가 아니라 **누락**이라 아무도 모른다.
  2) `at time zone 'Asia/Seoul'` 이 빠진다 → 이 DB 는 UTC 라(2026-09-01a 실측) 한국
     새벽 0~9시에 **어제 날짜**가 찍힌다. 신선도 표가 하루 낡아 보이는 자리이고,
     그 시간대에 화면을 보는 사람만 겪으므로 재현이 거의 안 된다.
  3) `api_quota_log` 를 근거로 끌어다 쓴다 → 그건 "우리가 API 를 몇 번 불렀나"의 장부이지
     자료의 나이가 아니다. 게다가 실패·재시도가 섞인 **하한선**이라, 신선도의 근거로 쓰면
     틀린 날짜를 자신 있게 적게 된다(로드맵 Wave 4 가 못 박아 둔 금지 사항).
  4) 나가는 칸 이름이 바뀐다 → 화면 검증기(`isDataFreshnessList`)가 목록을 통째로 거절해
     표가 사라진다. 서버가 조용히 바뀌어도 화면은 에러를 안 낸다.
  5) `revoke` 없이 `grant` 만 한다 → 회수를 안 하고 주면, 대시보드가 같은 함수를 다시
     만들며 자동으로 붙인 권한을 못 걷는다(2026-08-22 라이브 사례).
  6) public 원본까지 열어 준다 → 통과 함수가 `security definer` 라 열 필요가 없는데
     열어 두면 노출면만 늘어난다.
  7) `notify pgrst` 누락 → DB 에는 함수가 멀쩡히 있는데 화면만 404(PGRST202) 가 난다.
  8) 정본(schema.sql) 미동기 → 새 환경만 다르게 만들어진다.

⚠️ 한계: 규칙이 **맞는 날짜를 내는지**는 여기서 못 본다(DB 가 없다). 그건 라이브에서
   `select * from api.get_data_freshness();` 로 사람이 확인한다.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-09-05d_data_freshness.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

FN = "get_data_freshness"

# 나가는 칸 — 화면(`src/types.ts` 의 DataFreshnessRow)과 **정확히** 같아야 한다.
COLUMNS = ("src", "basis_kind", "basis", "next_expected", "cadence")

# 표에 서야 할 열 갈래. 하나라도 빠지면 화면에서 그 줄이 조용히 사라진다.
SOURCE_LABELS = (
    "점포·업종 (상권정보)",
    "실거래 (매매)",
    "건축물대장",
    "상권 경계",
    "LH 상가 공고",
    "건축 인허가",
    "국세청 기준시가",
    "상권 임대 동향 (부동산원)",
    "참고 시세 성적표",
    "필지 (토지 특성)",
)

# `timestamptz` 를 날짜로 자르는 자리 — 전부 한국 시각으로 옮긴 뒤 잘라야 한다.
TIMESTAMPTZ_TABLES = ("building", "district", "lh_notice", "price_gate_sigungu", "parcel")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def migration():
    return read(MIGRATION)


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


def statements(sql):
    """주석을 걷어낸 **실제 문장만**.

    ⛔ 권한 가드는 반드시 이쪽을 본다. 원문을 보면 실제 문장을 `--` 로 주석 처리해 죽여도
       글자는 남아 있으므로 "있다"고 판정한다 — 막는다던 규칙이 꺼져도 초록이 되는,
       이 레포가 가장 여러 번 데인 실패 모드다(2026-09-01 2차 적대검증).
    """
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


def function_body(sql, name):
    """`create [or replace] function <name>( … ) … as $$ <본문> $$;` 의 본문."""
    dollar = re.escape(chr(36) * 2)
    m = re.search(
        r"(?is)^create\s+(?:or\s+replace\s+)?function\s+"
        + re.escape(name)
        + r"\s*\(.*?" + dollar + r"(.*?)" + dollar + r"\s*;",
        sql,
        re.MULTILINE,
    )
    assert m, "{} 의 본문을 못 찾았습니다 — 정규식이 헛돌면 아래 검사가 통째로 무의미해집니다".format(name)
    return m.group(1)


@pytest.fixture(scope="module")
def public_body(migration):
    """public 함수의 본문에서 **주석을 걷어낸 실제 SQL**.

    ⛔ 주석을 남겨 두면 양쪽으로 다 틀린다 — 문장을 `--` 로 죽여도 글자가 남아 초록이 되고,
       반대로 설명하려고 주석에 인용한 말('union all 은 순서를 보장하지 않는다')이 문장으로
       세어진다(실제로 그 한 줄 때문에 줄 수 세기가 10 을 세었다).
    """
    return statements(function_body(migration, FN))


class TestFunctionExists:
    def test_migration_creates_both_functions(self, migration):
        assert re.search(
            r"(?im)^create\s+or\s+replace\s+function\s+{}\s*\(\s*\)".format(FN), migration
        ), "public.{} 를 안 만듭니다".format(FN)
        assert re.search(
            r"(?im)^create\s+or\s+replace\s+function\s+api\.{}\s*\(\s*\)".format(FN), migration
        ), "api.{} 통과 함수를 안 만듭니다 — 화면은 api 스키마만 부릅니다".format(FN)

    def test_schema_has_it_too(self, schema):
        """정본에도 같은 것이 있어야 한다 — 한쪽만 고치면 새 환경만 조용히 달라진다."""
        stmts = statements(schema)
        assert re.search(r"(?im)^create\s+or\s+replace\s+function\s+{}\s*\(\s*\)".format(FN), stmts)
        assert re.search(
            r"(?im)^create\s+or\s+replace\s+function\s+api\.{}\s*\(\s*\)".format(FN), stmts
        )

    def test_it_is_stable_and_security_definer(self, migration):
        """열 표가 전부 anon 에게 닫혀 있어 소유자 권한으로 대신 읽어야 한다."""
        head = migration[: migration.index(chr(36) * 2)]
        assert "security definer" in head.lower()
        assert re.search(r"(?im)^stable\s*$", head)


class TestReturnedColumns:
    def test_returns_exactly_these_columns(self, migration):
        """화면 검증기와 짝이다 — 이름이 하나만 달라져도 표가 통째로 사라진다."""
        for name in (FN, "api." + FN):
            m = re.search(
                r"(?is)create\s+or\s+replace\s+function\s+" + re.escape(name)
                + r"\s*\(\s*\)\s*returns\s+table\s*\((.*?)\)\s*language",
                migration,
            )
            assert m, "{} 의 returns table 을 못 읽었습니다".format(name)
            got = tuple(
                ln.strip().split()[0]
                for ln in m.group(1).splitlines()
                if ln.strip() and not ln.strip().startswith("--")
            )
            assert got == COLUMNS, "{} 가 내보내는 칸이 다릅니다: {}".format(name, got)


class TestEverySourceIsListed:
    @pytest.mark.parametrize("label", SOURCE_LABELS)
    def test_source_row_is_present(self, public_body, label):
        """⛔ 한 갈래가 빠지면 그 줄이 **조용히** 사라진다 — 에러가 아니라 누락이다.

        ⚠️ **따옴표까지 붙여 SQL 문자열 그대로** 찾는다. 이름만 부분일치로 보면
           '국세청 기준시가' → '국세청 기준시가 아님' 처럼 **덧붙여 바꾼 이름이 그대로
           통과**한다(돌연변이 시험으로 실증 — 처음 판이 정확히 그랬다). 그러면 화면 글자가
           바뀌었는데도 가드는 초록이다.
        """
        literal = "'{}'".format(label)
        assert literal in public_body, (
            "{} 줄이 함수에서 빠졌거나 이름이 바뀌었습니다 — 화면 표에서 그 자료가 통째로 "
            "사라지고, 보는 사람은 '그런 자료는 안 쓰나 보다'로 읽습니다".format(literal)
        )

    def test_there_are_exactly_ten_rows(self, public_body):
        """줄 수를 못 박는다 — 자료를 늘리거나 줄이면 이 시험과 화면 시험이 함께 걸린다."""
        assert public_body.count("union all") == len(SOURCE_LABELS) - 1, (
            "자료 갈래 수가 {}개가 아닙니다 — 늘렸다면 SOURCE_LABELS 와 화면 시험도 "
            "함께 고치세요".format(len(SOURCE_LABELS))
        )

    def test_rows_are_ordered_deterministically(self, public_body):
        """union all 은 순서를 보장하지 않는다 — 순서가 흔들리면 사람은 자료가 바뀐 줄 안다."""
        assert re.search(r"order\s+by\s+\w+\.ord", public_body), (
            "ord 로 순서를 못 박지 않았습니다"
        )


class TestTimezone:
    @pytest.mark.parametrize("table", TIMESTAMPTZ_TABLES)
    def test_timestamptz_is_converted_to_seoul(self, public_body, table):
        """⛔ 이 DB 는 UTC 다 — 그냥 날짜로 자르면 한국 새벽 0~9시에 어제 날짜가 찍힌다.

        그 시간대에 보는 사람만 겪으므로 재현이 거의 안 된다. 글자로 못 박아 둔다.
        """
        m = re.search(r"from\s+" + re.escape(table) + r"\s+t\)", public_body)
        assert m, "{} 를 읽는 자리를 못 찾았습니다".format(table)
        # 그 줄(또는 바로 앞줄)에서 max() 를 한국 시각으로 옮겼는지 본다.
        window = public_body[max(0, m.start() - 200): m.end()]
        assert "at time zone 'Asia/Seoul'" in window, (
            "{} 의 시각을 Asia/Seoul 로 옮기지 않고 날짜로 잘랐습니다 — 이 DB 는 UTC 라 "
            "한국 새벽 0~9시에 어제 날짜가 찍힙니다".format(table)
        )

    def test_no_bare_current_date_or_now(self, public_body):
        """'오늘'을 함수 안에서 판단하지 않는다 — 이 함수는 도장을 나르기만 한다."""
        assert not re.search(r"\bcurrent_date\b", public_body)
        assert not re.search(r"\bnow\s*\(", public_body)


class TestForbiddenSource:
    def test_api_quota_log_is_never_read(self, migration, schema):
        """⛔ 호출 장부는 자료의 나이가 아니다(하한선일 뿐 — 로드맵 Wave 4 금지 사항)."""
        assert "api_quota_log" not in function_body(migration, FN)
        assert "api_quota_log" not in function_body(migration, "api." + FN)
        assert "api_quota_log" not in function_body(schema, FN)


class TestNextExpectedRules:
    def test_each_rule_is_written_exactly_once(self, public_body):
        """규칙이 두 벌이면 한쪽만 고쳐지는 날 두 자료가 서로 다른 주기를 말한다."""
        assert public_body.count("interval '5 months'") == 1, "분기 규칙이 한 번이 아닙니다"
        assert public_body.count("interval '2 months'") == 1, "월간 규칙이 한 번이 아닙니다"
        assert public_body.count("make_date(") == 1, "연 1회 규칙이 한 번이 아닙니다"

    def test_shape_is_checked_before_to_date(self, public_body):
        """`to_date('2026Q3','YYYYMM')` 은 **에러**다 — 터지면 표가 통째로 사라진다.

        (unit_business.snapshot_ym 은 컬럼 주석이 '2026Q3' 형식도 허용한다.)
        """
        assert public_body.count(r"^\d{4}(0[1-9]|1[0-2])$") == 2, (
            "'YYYYMM' 모양 검사가 두 자리(상권정보·인허가)에 다 있지 않습니다"
        )
        assert r"^\d{4}Q[1-4]$" in public_body, "부동산원 분기 모양 검사가 없습니다"
        assert r"^\d{4}-\d{2}-\d{2}$" in public_body, "고시일 모양 검사가 없습니다"


class TestPermissions:
    def test_revoke_comes_before_grant(self, migration):
        """grant 는 더하기라, 자동으로 붙은 권한을 못 걷어낸다(2026-08-22 라이브 사례)."""
        stmts = statements(migration)
        revoke = stmts.find("revoke all on function api.{}()".format(FN))
        grant = stmts.find("grant execute on function api.{}()".format(FN))
        assert revoke != -1, "api 통과 함수의 revoke 가 없습니다"
        assert grant != -1, "api 통과 함수의 grant 가 없습니다"
        assert revoke < grant, "회수를 먼저 하고 줘야 합니다"

    def test_only_the_api_wrapper_is_granted(self, migration, schema):
        """⛔ public 원본은 끝까지 닫아 둔다 — 통과 함수가 security definer 다."""
        for sql in (migration, schema):
            stmts = statements(sql)
            granted = re.findall(
                r"(?im)^grant\s+execute\s+on\s+function\s+((?:public\.|api\.)?{})\s*\(\s*\)"
                .format(FN),
                stmts,
            )
            assert granted == ["api." + FN], (
                "grant 대상이 api 통과 함수 하나가 아닙니다: {}".format(granted)
            )

    def test_public_original_is_revoked_from_anon_too(self, migration):
        """`from public` 만으로는 직접 부여된 anon 권한을 못 걷는다(2026-08-10 실측)."""
        stmts = statements(migration)
        assert re.search(
            r"(?im)^revoke\s+all\s+on\s+function\s+{}\s*\(\s*\)\s+"
            r"from\s+public,\s*anon,\s*authenticated".format(FN),
            stmts,
        ), "public 원본의 revoke 가 anon·authenticated 를 안 지목합니다"


class TestMigrationShape:
    def test_tells_postgrest_to_reload(self, migration):
        assert "notify pgrst, 'reload schema';" in migration, (
            "스키마 캐시 리로드를 안 알리면 DB 에는 함수가 있는데 화면만 404 가 납니다"
        )

    def test_comment_is_written(self, migration, schema):
        """주석은 `pg_proc` 이 아니라 `pg_description` 에 실린다 — 빠뜨리기 쉬운 자리다."""
        for sql in (migration, schema):
            assert re.search(
                r"(?im)^comment\s+on\s+function\s+{}\s*\(\s*\)\s+is".format(FN), sql
            ), "comment on function 이 없습니다"
        assert "2026-09-05d" in migration
