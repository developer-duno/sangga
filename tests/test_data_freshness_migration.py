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

ⓘ 2026-10-01a 에 월간 규칙이 바뀌었다(기준월 + 2개월 - 하루 → + 3개월 - 하루, 사장님 결정).
   05d 는 라이브에 적용된 **날짜 원장**이라 고치지 않는다 — 그래서 '다음 갱신 예정' 규칙
   검사는 05d 가 아니라 **지금 정본(schema.sql)과 새 마이그레이션 2026-10-01a** 를 본다.
   본문 불변식(열 갈래·줄 수·정렬·시간대·모양 검사)도 같은 두 벌(정본·10-01a)을 본다
   (`public_body` fixture 가 이 둘로 매개변수화돼 있다) — 05d 는 옛 규칙을 그대로 간직해야
   하므로 이 둘에서 빠지고, 그 사실 자체를 test_the_old_ledger_is_left_as_applied 가 따로
   확인한다. 칸·권한·api 쌍둥이·notify 는 그대로 05d 원장을 본다. 10-01a 의 함수 머리와
   comment 는 정본(schema.sql)과 글자 그대로 같은지 대조한다(10-01a 는 CREATE 문 전체를
   다시 쓰므로, 머리·comment 를 베끼다 한 줄이라도 달라지면 라이브가 조용히 다른 모양으로
   만들어진다 — 본문 전체가 정본과 같은지는 test_schema_function_drift.py 가 따로 본다).
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-09-05d_data_freshness.sql")
# 월간 규칙을 바꾼 마이그레이션(2026-10-01a) — public 함수 하나만 다시 만든다.
PERMIT_MIGRATION = os.path.join(
    ROOT, "supabase", "migrations", "2026-10-01a_permit_next_expected.sql")
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


def grant_targets(sql, name=FN):
    """`grant … on function … <name>(` 의 **대상 이름**을 전부 돌려준다(소문자).

    권한 종류(execute·all)·받는 역할과 그 순서·들여쓰기·줄바꿈·대소문자와
    무관하게 본다. 돌려주는 값은 적힌 그대로의 이름이다 —
    `api.<name>` · `public.<name>` · 스키마 없는 `<name>`.

    ⛔ 줄머리에 `grant execute` 로 못 박은 정규식은 `grant all …` 과 들여쓴 꼴을
       놓친다(2026-10-02 감사 실측) — 그래서 탐지를 이 함수로 빼고, 실제로 잡는지를
       TestPermissions 의 양성 대조가 나쁜 예로 확인한다(가드와 **같은 함수**).
    ⓘ `revoke grant option for …` 는 회수라 건너뛴다.
    ⚠️ 못 보는 것(2026-10-02 검사관 실측): 인자 괄호 없는 `on function <name> to …` ·
       따옴표 이름(`"<name>"()`) · `on procedure`.
    """
    found = []
    for stmt in re.findall(
            r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*?"
            r"\bon\s+(?:function|routine)\b([^;]*)",
            statements(sql)):
        found += re.findall(
            r"(?i)(?<![\w.])((?:\w+\.)?" + re.escape(name) + r")\s*\(", stmt)
    return [t.lower() for t in found]


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


@pytest.fixture(scope="module", params=(SCHEMA, PERMIT_MIGRATION), ids=("schema", "2026-10-01a"))
def public_body(request):
    """public 함수의 본문에서 **주석을 걷어낸 실제 SQL**.

    ⛔ 주석을 남겨 두면 양쪽으로 다 틀린다 — 문장을 `--` 로 죽여도 글자가 남아 초록이 되고,
       반대로 설명하려고 주석에 인용한 말('union all 은 순서를 보장하지 않는다')이 문장으로
       세어진다(실제로 그 한 줄 때문에 줄 수 세기가 10 을 세었다).

    ⓘ 2026-10-01a 로 **지금 정본(schema.sql)과 새 마이그레이션 두 벌**을 본다 — 05d 는
       라이브에 적용된 날짜 원장이라 옛 규칙('기준월 + 2개월 - 하루')을 그대로 간직해야
       하므로(test_the_old_ledger_is_left_as_applied), 이 fixture 의 대상에서 뺐다.
    """
    return statements(function_body(read(request.param), FN))


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
    @pytest.mark.parametrize("path", (SCHEMA, PERMIT_MIGRATION), ids=("schema", "2026-10-01a"))
    def test_each_rule_is_written_exactly_once(self, path):
        """규칙이 두 벌이면 한쪽만 고쳐지는 날 두 자료가 서로 다른 주기를 말한다.

        ⛔ 05d 원장이 아니라 **지금 정본과 그것을 라이브에 올리는 2026-10-01a** 를 본다.
           월간 = 기준월 + 3개월 - 하루(다음 판이 공개되는 달의 말일 — 사장님 결정 2026-10-01).
           옛 '2 months' 가 한 글자라도 남으면 매달 1일~20일 무렵 지난 날짜가 화면에 선다.
        """
        body = statements(function_body(read(path), FN))
        assert body.count("interval '5 months'") == 1, "분기 규칙이 한 번이 아닙니다"
        assert body.count("interval '3 months'") == 1, "월간 규칙(+3개월)이 한 번이 아닙니다"
        assert body.count("interval '2 months'") == 0, (
            "옛 월간 규칙(+2개월)이 남아 있습니다 — 지금 판이 게시된 달의 말일을 띄워 "
            "매달 초 이미 지난 날짜가 화면에 섭니다")
        assert body.count("make_date(") == 1, "연 1회 규칙이 한 번이 아닙니다"

    @pytest.mark.parametrize("path", (SCHEMA, PERMIT_MIGRATION), ids=("schema", "2026-10-01a"))
    def test_the_monthly_rule_belongs_to_permit(self, path):
        """+3개월 이 **인허가 줄**의 규칙인지 본다 — 숫자만 세면 다른 갈래로 옮겨 가도 초록이다."""
        body = statements(function_body(read(path), FN))
        assert re.search(
            r"when\s+n\.rule_kind\s*=\s*'permit'[^\n]*\n\s*then\s*\(to_date\(n\.basis,\s*'YYYYMM'\)"
            r"\s*\+\s*interval\s+'3 months'\s*-\s*interval\s+'1 day'\)::date",
            body,
        ), "인허가(rule_kind = 'permit') 줄이 '기준월 + 3개월 - 하루' 가 아닙니다"

    def test_the_old_ledger_is_left_as_applied(self, migration):
        """⛔ 05d 는 라이브에 적용된 날짜 원장이다 — 새 규칙으로 고쳐 쓰면 원장이 거짓말을 한다."""
        body = statements(function_body(migration, FN))
        assert body.count("interval '2 months'") == 1
        assert body.count("interval '3 months'") == 0

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
            # 위 정규식은 줄머리 `grant execute` 만 본다 — `grant all`·들여쓴 꼴까지.
            targets = grant_targets(sql)
            assert targets == ["api." + FN], (
                "grant 대상이 api 통과 함수 하나가 아닙니다: {}".format(targets)
            )

    @pytest.mark.parametrize("bad", [
        "grant execute on function get_data_freshness() to anon;",
        "grant execute on function public.get_data_freshness() to anon;",
        # ↓ 감사가 "초록(못 잡음)"이라 적은 변형 꼴들
        "grant all on function get_data_freshness() to anon;",
        "  grant execute on function get_data_freshness() to anon;",
        "grant execute on function public.get_data_freshness() to authenticated, anon;",
        "GRANT ALL\n  ON FUNCTION public.get_data_freshness ( )\n  TO anon;",
    ])
    def test_grant_detector_catches_the_public_original(self, bad):
        """양성 대조 — 가드와 같은 함수에 나쁜 예를 넣으면 api 가 아닌 대상이 잡힌다.

        ⛔ `!= ["api." + FN]` 로 견주지 않는다 — 탐지 함수가 죽어 `[]` 만 돌려줘도
           그 단언은 참이라 초록이다(2026-10-02 검사관 실측). 잡힌 것을 직접 센다.
        """
        good = "grant execute on function api.get_data_freshness() to anon, authenticated;\n"
        targets = grant_targets(good + bad + "\n")
        assert "api." + FN in targets, "좋은 예의 api 대상부터 못 찾았습니다"
        assert [t for t in targets if t != "api." + FN], (
            "public 원본에 준 grant 를 못 잡았습니다: {}".format(targets)
        )

    @pytest.mark.parametrize("harmless", [
        "revoke all on function get_data_freshness() from public, anon, authenticated;",
        "revoke grant option for execute on function get_data_freshness() from anon;",
        "-- grant execute on function get_data_freshness() to anon;",
        "grant execute on function api.get_data_freshness_v2() to anon;",
        "grant execute on function other_fn() to anon;",
    ])
    def test_grant_detector_leaves_the_rest_alone(self, harmless):
        good = "grant execute on function api.get_data_freshness() to anon, authenticated;\n"
        assert grant_targets(good + harmless + "\n") == ["api." + FN]

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


@pytest.fixture(scope="module")
def permit_migration():
    return read(PERMIT_MIGRATION)


class TestPermitRuleMigration:
    """2026-10-01a — 월간 규칙 한 줄만 바꿔 public 함수를 다시 만든다."""

    def test_it_recreates_only_the_public_function(self, permit_migration):
        """⛔ api 쌍둥이는 안 건드린다 — public 을 부르는 통과 함수라 그대로 따라온다.

        다시 만들면 grant 를 다시 줘야 하고, 그 줄이 빠지는 날 화면이 permission denied 다.
        """
        stmts = statements(permit_migration)
        made = re.findall(r"(?im)^create\s+(?:or\s+replace\s+)?function\s+([\w.]+)\s*\(", stmts)
        assert made == [FN], "public.{} 하나만 다시 만들어야 합니다: {}".format(FN, made)

    def test_no_grant_at_all(self, permit_migration):
        """⛔ public 원본은 끝까지 닫아 둔다 — 이 파일엔 grant 가 한 줄도 없어야 한다."""
        assert not re.search(r"(?im)^\s*grant\s", statements(permit_migration)), (
            "grant 가 있습니다 — public 원본을 열거나 api 권한을 다시 손댈 이유가 없습니다")

    def test_public_original_is_revoked_again(self, permit_migration):
        """대시보드가 다시 만들며 붙인 anon 권한을 만든 자리에서 걷는다(05d 와 같은 관습)."""
        assert re.search(
            r"(?im)^revoke\s+all\s+on\s+function\s+{}\s*\(\s*\)\s+"
            r"from\s+public,\s*anon,\s*authenticated\s*;".format(FN),
            statements(permit_migration),
        ), "public 원본의 revoke 가 없거나 anon·authenticated 를 안 지목합니다"

    def test_comment_is_rewritten_with_the_new_rule(self, permit_migration):
        """주석은 `pg_description` 에 실린다 — 본문만 바꾸면 라이브 설명이 옛 규칙을 말한다."""
        m = re.search(
            r"(?ims)^comment\s+on\s+function\s+{}\s*\(\s*\)\s+is(.*?);\s*$".format(FN),
            permit_migration,
        )
        assert m, "comment on function 이 없습니다"
        assert "기준월 + 3개월 - 하루" in m.group(1)
        assert "2개월" not in m.group(1)
        assert "2026-10-01a" in m.group(1)

    def test_one_transaction_and_notify_after_commit(self, permit_migration):
        """dbx.py 는 자동커밋이라 감싸지 않으면 함수만 바뀌고 revoke 가 빠진 채 남을 수 있다."""
        stmts = statements(permit_migration)
        begin = re.search(r"(?im)^begin\s*;", stmts)
        create = re.search(r"(?im)^create\s+or\s+replace\s+function\s", stmts)
        revoke = re.search(r"(?im)^revoke\s", stmts)
        commit = re.search(r"(?im)^commit\s*;", stmts)
        notify = stmts.find("notify pgrst, 'reload schema';")
        assert begin and create and revoke and commit and notify != -1
        assert begin.start() < create.start() < revoke.start() < commit.start() < notify, (
            "begin → create → revoke → commit → notify 순서가 아닙니다")

    def test_function_head_matches_the_schema(self, permit_migration, schema):
        """함수 머리(`returns table`·`language sql`·`stable`·`security definer`·`search_path`)가

        정본과 10-01a 에서 **글자 그대로** 같아야 한다 — `create or replace` 는 머리 속성을
        새 정의로 덮어쓰므로, 머리를 베끼다 한 줄을 빼먹으면 라이브 함수가 조용히 다른 속성으로
        재생성된다(2026-10-01 적대검증 로컬 실측: `set search_path` 가 빠지면 anon → api 경로가
        `relation "unit_business" does not exist` 로 죽어 화면 표가 통째로 사라지고,
        `security definer` 가 빠지면 화면은 돌지만 속성만 꺼진다 — 둘 다 이 시험 전엔 초록이었다).

        ⛔ api.get_data_freshness 의 머리를 잘못 집지 않게 줄머리(`^`)에 고정한다.
        """
        head_re = re.compile(
            r"(?ims)^create\s+or\s+replace\s+function\s+{}\s*\(".format(FN)
            + r".*?(?=" + re.escape(chr(36) * 2) + r")"
        )

        def extract_head(sql):
            m = head_re.search(statements(sql))
            assert m, "{} 의 함수 머리를 못 찾았습니다".format(FN)
            return m.group(0).replace("\r\n", "\n")

        schema_head = extract_head(schema)
        migration_head = extract_head(permit_migration)
        assert migration_head == schema_head, (
            "10-01a 의 함수 머리가 정본(schema.sql)과 글자가 다릅니다 — 새 환경만 조용히 "
            "다른 모양으로 만들어집니다"
        )
        for needle in ("security definer", "set search_path = public", "language sql"):
            assert needle in migration_head.lower() or needle in migration_head, (
                "{} 가 함수 머리에 없습니다".format(needle)
            )
        assert re.search(r"(?im)^stable\s*$", migration_head), "stable 한 줄이 없습니다"

    def test_comment_matches_the_schema(self, permit_migration, schema):
        r"""`comment on function … is '…';` 문자열이 정본과 10-01a 에서 같아야 한다.

        본문과 머리는 같은데 comment 만 다르면 `pg_description`(라이브 설명)이 schema.sql
        의 서술과 갈라진다 — 다음 사람이 schema.sql 을 읽고 다른 설명을 믿게 된다.

        ⛔ api 쌍둥이의 comment 가 있다면 섞이지 않게 같은 방식으로 줄머리를 고정한다
        (`api.` 접두는 이 정규식에 안 걸린다 — `^comment\s+on\s+function\s+get_data_freshness`
        는 `api.get_data_freshness` 의 `api.` 뒤를 줄머리로 보지 않는다).
        """
        comment_re = re.compile(
            r"(?ims)^comment\s+on\s+function\s+{}\s*\(\s*\)\s+is.*?;\s*$".format(FN)
        )

        def extract_comment(sql):
            m = comment_re.search(statements(sql))
            assert m, "{} 의 comment on function 을 못 찾았습니다".format(FN)
            return m.group(0).replace("\r\n", "\n")

        schema_comment = extract_comment(schema)
        migration_comment = extract_comment(permit_migration)
        assert migration_comment == schema_comment, (
            "10-01a 의 comment 가 정본(schema.sql)과 글자가 다릅니다 — 라이브 설명이 "
            "schema.sql 의 서술과 갈라집니다"
        )
