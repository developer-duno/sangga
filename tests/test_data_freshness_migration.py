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

ⓘ 2026-10-05b(결정 0033)에 11번째 줄 '상권 개업·폐업 (서울시)'과 `norm` 셋째 갈래(서울시 분기 꼴
   'YYYYQ' 다섯 자리)가 생겼다. 10-01a 도 이제 라이브에 적용된 **원장**이라 고칠 수 없다 — 그래서
   본문 불변식·규칙 검사의 두 벌을 (정본, 10-01a) 에서 **(정본, 10-05b)** 로 옮겼고, 10-01a 는
   "열 줄 그대로 남아 있나"(test_the_10_01a_ledger_is_left_as_applied)만 따로 본다.

ⓘ 2026-10-12b(사장님 결정 2026-10-12)에 10번째 줄 '필지 (토지 특성)'의 기준이 받아 둔 날(updated_at)에서
   **공시 연도**(max(land_price_year))로, 다음 갱신 예정이 null 에서 **다음 해 6월 30일**(새 규칙 갈래
   'land_year')로 바뀌었다. 10-05b 도 이제 원장이라 본문 불변식·규칙 검사의 두 벌을 **(정본, 10-12b)** 로
   옮겼고, 10-05b 는 "옛 필지 줄 그대로 남아 있나"(test_the_10_05b_ledger_is_left_as_applied)만 따로 본다.
   새 규칙의 날짜는 로컬 PostgreSQL 이 있으면 실제로 돌려 본다(TestLandYearRealRun — CI 는 건너뛴다).

ⓘ 2026-10-15a(사장님 결정 2026-10-15 · F3+F5)에 2번 줄(실거래)이 새 규칙 'tx'(계약월 + 2개월 - 하루)를,
   3번 줄(건축물대장)이 기준 '판'(ledger_release.release_ym) + 월간 규칙 'permit' 을 쓰게 됐다. 10-12b 도
   이제 원장이라 두 벌을 **(정본, 10-15a)** 로 옮겼고, 10-12b 는 "옛 실거래·대장 줄 그대로 남아 있나"
   (test_the_10_12b_ledger_is_left_as_applied)만 따로 본다. '+2개월' 은 이제 'tx' 갈래 한 자리에만 있어야
   하고, 인허가·대장의 'permit' 갈래는 그대로 '+3개월' 이다(monthly_rule_months 교차 변이).
   10-15a 전용 시험(표·표지 명령·실제 날짜)은 tests/test_freshness_monthly_rules_migration.py.
"""

import os
import re
import shutil
import socket
import subprocess
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-09-05d_data_freshness.sql")
# 월간 규칙을 바꾼 마이그레이션(2026-10-01a) — public 함수 하나만 다시 만든다.
PERMIT_MIGRATION = os.path.join(
    ROOT, "supabase", "migrations", "2026-10-01a_permit_next_expected.sql")
# 11번째 줄(서울 개업·폐업)과 norm 셋째 갈래를 더한 마이그레이션(2026-10-05b · 결정 0033).
OPENCLOSE_MIGRATION = os.path.join(
    ROOT, "supabase", "migrations", "2026-10-05b_district_openclose.sql")
# 10번째 줄(필지)의 기준을 공시 연도로 바꾼 마이그레이션(2026-10-12b · 사장님 결정 2026-10-12).
LAND_MIGRATION = os.path.join(
    ROOT, "supabase", "migrations", "2026-10-12b_freshness_land_price_year.sql")
# 2번(실거래)·3번(건축물대장) 줄에 월간 규칙을 건 마이그레이션(2026-10-15a · 사장님 결정 2026-10-15).
# 2026-10-18a(결정 0041) — 9번 줄(참고 시세 성적표)을 빼고 신선도 함수를 다시 만든 가장 최근 판. 정본과 글자가 같아야 하는 쪽.
DROP_GATE_MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-18a_price_use_group.sql")
# 2026-10-29a(결정 0044) — 12번 줄(대전시 동네 폐업)을 더해 다시 만든 가장 최근 판. 정본과 글자가 같아야 하는 쪽은 이제 이 파일이다
# (10-18a 판에 그 줄만 더한 글인지는 tests/test_daejeon_dong_closure_migration.py 가 대조한다).
DAEJEON_MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-29a_daejeon_dong_closure.sql")
MONTHLY_MIGRATION = os.path.join(
    ROOT, "supabase", "migrations", "2026-10-15a_freshness_monthly_rules.sql")
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
    "상권 개업·폐업 (서울시)",
    "동네 폐업 (대전시)",
)
# 결정 0041(2026-10-18a)로 정본에서 뺀 갈래 — 적용된 원장(10-15a)에만 남는다.
SCHEMA_DROPPED_LABELS = ("참고 시세 성적표",)
# 결정 0044(2026-10-29a)로 정본에 더한 갈래 — 원장(10-15a)에는 없다.
SCHEMA_ADDED_LABELS = ("동네 폐업 (대전시)",)


def labels_for(request):
    """public_body 가 정본이면 뺀 갈래를 걷은 목록(대전 줄 포함 열한 갈래), 원장(10-15a)이면 대전 줄 없는 열한 갈래."""
    if "schema" in request.node.callspec.id:
        return tuple(x for x in SOURCE_LABELS if x not in SCHEMA_DROPPED_LABELS)
    return tuple(x for x in SOURCE_LABELS if x not in SCHEMA_ADDED_LABELS)

# `timestamptz` 를 날짜로 자르는 자리 — 전부 한국 시각으로 옮긴 뒤 잘라야 한다.
# ⓘ parcel 은 2026-10-12b 부터 timestamptz 가 아니라 공시 연도(smallint)를 읽는다 — 이 목록에서 뺐다.
# ⓘ building 은 2026-10-15a 부터 timestamptz 가 아니라 판 표지(ledger_release.release_ym)를 읽는다 — 뺐다.
TIMESTAMPTZ_TABLES = ("district", "lh_notice", "price_gate_sigungu")


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


@pytest.fixture(scope="module", params=(SCHEMA, MONTHLY_MIGRATION), ids=("schema", "2026-10-15a"))
def public_body(request):
    """public 함수의 본문에서 **주석을 걷어낸 실제 SQL**.

    ⛔ 주석을 남겨 두면 양쪽으로 다 틀린다 — 문장을 `--` 로 죽여도 글자가 남아 초록이 되고,
       반대로 설명하려고 주석에 인용한 말('union all 은 순서를 보장하지 않는다')이 문장으로
       세어진다(실제로 그 한 줄 때문에 줄 수 세기가 10 을 세었다).

    ⓘ **지금 정본(schema.sql)과 가장 최근에 이 함수를 다시 만든 마이그레이션 두 벌**을 본다 —
       05d·10-01a 는 라이브에 적용된 날짜 원장이라 그때의 정의를 그대로 간직해야 하므로
       (test_the_old_ledger_is_left_as_applied · test_the_10_01a_ledger_is_left_as_applied),
       이 fixture 의 대상에서 뺐다(2026-10-05b 로 10-01a → 10-05b 이동 · 2026-10-12b 로 10-05b → 10-12b 이동 ·
       2026-10-15a 로 10-12b → 10-15a 이동).
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
    def test_source_row_is_present(self, request, public_body, label):
        """⛔ 한 갈래가 빠지면 그 줄이 **조용히** 사라진다 — 에러가 아니라 누락이다.

        ⚠️ **따옴표까지 붙여 SQL 문자열 그대로** 찾는다. 이름만 부분일치로 보면
           '국세청 기준시가' → '국세청 기준시가 아님' 처럼 **덧붙여 바꾼 이름이 그대로
           통과**한다(돌연변이 시험으로 실증 — 처음 판이 정확히 그랬다). 그러면 화면 글자가
           바뀌었는데도 가드는 초록이다.
        """
        literal = "'{}'".format(label)
        if label not in labels_for(request):
            # 결정 0041 — 정본에서는 그 줄이 **없어야** 한다(되살아나면 지운 게이트 표를 읽는다).
            assert literal not in public_body
            return
        assert literal in public_body, (
            "{} 줄이 함수에서 빠졌거나 이름이 바뀌었습니다 — 화면 표에서 그 자료가 통째로 "
            "사라지고, 보는 사람은 '그런 자료는 안 쓰나 보다'로 읽습니다".format(literal)
        )

    def test_there_are_exactly_eleven_rows(self, request, public_body):
        """줄 수를 못 박는다 — 자료를 늘리거나 줄이면 이 시험과 화면 시험이 함께 걸린다.

        ⓘ 정본은 2026-10-18a(결정 0041)부터 열 줄 → 2026-10-29a(결정 0044 대전 줄)부터 다시 열한 줄,
          원장 10-15a 는 (성적표 줄이 든) 열한 줄 그대로다.
        """
        labels = labels_for(request)
        assert public_body.count("union all") == len(labels) - 1, (
            "자료 갈래 수가 {}개가 아닙니다 — 늘렸다면 SOURCE_LABELS 와 화면 시험도 "
            "함께 고치세요".format(len(labels))
        )

    def test_rows_are_ordered_deterministically(self, public_body):
        """union all 은 순서를 보장하지 않는다 — 순서가 흔들리면 사람은 자료가 바뀐 줄 안다."""
        assert re.search(r"order\s+by\s+\w+\.ord", public_body), (
            "ord 로 순서를 못 박지 않았습니다"
        )


class TestTimezone:
    @pytest.mark.parametrize("table", TIMESTAMPTZ_TABLES)
    def test_timestamptz_is_converted_to_seoul(self, request, public_body, table):
        """⛔ 이 DB 는 UTC 다 — 그냥 날짜로 자르면 한국 새벽 0~9시에 어제 날짜가 찍힌다.

        그 시간대에 보는 사람만 겪으므로 재현이 거의 안 된다. 글자로 못 박아 둔다.
        """
        m = re.search(r"from\s+" + re.escape(table) + r"\s+t\)", public_body)
        if table == "price_gate_sigungu" and "schema" in request.node.callspec.id:
            # 결정 0041 — 정본은 게이트 표를 더는 읽지 않는다(표를 지웠다).
            assert m is None
            return
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


def monthly_rule_months(body):
    """{'permit': N, 'tx': M} — 각 갈래가 `to_date(n.basis,'YYYYMM') + interval 'N months' - interval '1 day'` 로
    더하는 달 수. 갈래가 없거나 꼴이 다르면 그 열쇠가 빠진다(가드 본체와 교차 변이가 같은 함수를 지난다).

    못 보는 것: 별칭이 n 이 아닌 꼴 · 한 갈래가 두 번 적힌 꼴(앞의 것만 본다 — 개수는 가드가 따로 센다).
    """
    out = {}
    for kind in ("permit", "tx"):
        m = re.search(
            r"when\s+n\.rule_kind\s*=\s*'" + kind + r"'[^\n]*\n\s*then\s*\(to_date\(n\.basis,\s*'YYYYMM'\)"
            r"\s*\+\s*interval\s+'(\d+) months'\s*-\s*interval\s+'1 day'\)::date", body)
        if m:
            out[kind] = int(m.group(1))
    return out


class TestNextExpectedRules:
    @pytest.mark.parametrize("path", (SCHEMA, MONTHLY_MIGRATION), ids=("schema", "2026-10-15a"))
    def test_each_rule_is_written_exactly_once(self, path):
        """규칙이 두 벌이면 한쪽만 고쳐지는 날 두 자료가 서로 다른 주기를 말한다.

        ⛔ 05d·10-01a·10-05b·10-12b 원장이 아니라 **지금 정본과 그것을 라이브에 올리는 2026-10-15a** 를 본다.
           월간(인허가·대장 판) = 기준월 + 3개월 - 하루(다음 판이 공개되는 달의 말일 — 사장님 결정 2026-10-01).
           실거래 = 계약월 + 2개월 - 하루(새 갈래 'tx' — 사장님 결정 2026-10-15).
           '+2개월' 은 'tx' 갈래 **한 자리에만** 있어야 한다 — 인허가 갈래로 새면 매달 1일~20일 무렵 지난
           날짜가 화면에 선다(2026-10-01a 이전 사고). 갈래별 달 수는 monthly_rule_months 가 따로 본다.
        """
        body = statements(function_body(read(path), FN))
        assert body.count("interval '5 months'") == 1, "분기 규칙이 한 번이 아닙니다"
        # 2026-10-29a(결정 0044) — 정본에는 대전시 동네 폐업의 '받은 날 + 3개월'(날짜 더하기 · to_date 아님)이 하나 더 있다.
        daejeon = body.count("then (n.basis::date + interval '3 months')::date")
        assert daejeon == (1 if path == SCHEMA else 0)
        assert body.count("interval '3 months'") - daejeon == 1, "월간 규칙(+3개월)이 한 번이 아닙니다"
        assert body.count("interval '2 months'") == 1, "실거래 규칙(+2개월)이 한 번이 아닙니다"
        assert monthly_rule_months(body) == {"permit": 3, "tx": 2}, (
            "인허가·대장(permit) = +3개월 · 실거래(tx) = +2개월 이 아닙니다: {}".format(monthly_rule_months(body)))
        # 연 1회 규칙은 둘이다 — 국세청(다음 해 3월 31일)·필지 공시 연도(다음 해 6월 30일, 2026-10-12b).
        assert body.count("make_date(") == 2, "연 1회 규칙(국세청·필지)이 두 자리가 아닙니다"

    @pytest.mark.parametrize("old,new,kind", [
        # tx 2 → 3: 실거래가 대장·인허가와 같은 날짜를 말한다
        ("then (to_date(n.basis, 'YYYYMM') + interval '2 months' - interval '1 day')::date",
         "then (to_date(n.basis, 'YYYYMM') + interval '3 months' - interval '1 day')::date", "tx"),
        # permit 3 → 2: 옛 월간 규칙(지금 판이 게시된 달의 말일)으로 되돌아간다
        ("then (to_date(n.basis, 'YYYYMM') + interval '3 months' - interval '1 day')::date",
         "then (to_date(n.basis, 'YYYYMM') + interval '2 months' - interval '1 day')::date", "permit"),
    ], ids=("tx-2-to-3", "permit-3-to-2"))
    def test_mutation_swapping_the_month_counts_is_noticed(self, old, new, kind):
        """교차 변이 — 한쪽 갈래의 달 수만 바꿔도 가드가 빨강이다(개수 세기만으로는 2↔3 맞바꿈을 못 본다)."""
        body = statements(function_body(read(SCHEMA), FN))
        assert body.count(old) == 1, "전제: 그 갈래 글자가 지금 판에 한 번 있다"
        broken = body.replace(old, new, 1)
        got = monthly_rule_months(broken)
        assert got.get(kind) != {"permit": 3, "tx": 2}[kind], got

    @pytest.mark.parametrize("path", (SCHEMA, MONTHLY_MIGRATION), ids=("schema", "2026-10-15a"))
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
        # 2026-10-15a — 실거래 'tx' 갈래가 셋째 자리(대장 판은 인허가 'permit' 갈래를 같이 쓴다).
        assert public_body.count(r"^\d{4}(0[1-9]|1[0-2])$") == 3, (
            "'YYYYMM' 모양 검사가 세 자리(상권정보·인허가/대장·실거래)에 다 있지 않습니다"
        )
        assert r"^\d{4}Q[1-4]$" in public_body, "부동산원 분기 모양 검사가 없습니다"
        assert r"^\d{4}[1-4]$" in public_body, "서울시 분기(YYYYQ 다섯 자리) 모양 검사가 없습니다"
        assert r"^\d{4}-\d{2}-\d{2}$" in public_body, "고시일 모양 검사가 없습니다"
        assert r"^\d{4}$" in public_body, "공시 연도(네 자리) 모양 검사가 없습니다"


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

    @pytest.mark.parametrize("path", (PERMIT_MIGRATION, OPENCLOSE_MIGRATION, LAND_MIGRATION, MONTHLY_MIGRATION),
                             ids=("2026-10-01a", "2026-10-05b", "2026-10-12b", "2026-10-15a"))
    def test_function_head_matches_the_schema(self, path, schema):
        """함수 머리(`returns table`·`language sql`·`stable`·`security definer`·`search_path`)가

        정본과 10-01a·10-05b 에서 **글자 그대로** 같아야 한다 — `create or replace` 는 머리 속성을
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
        migration_head = extract_head(read(path))
        assert migration_head == schema_head, (
            "마이그레이션의 함수 머리가 정본(schema.sql)과 글자가 다릅니다 — 새 환경만 조용히 "
            "다른 모양으로 만들어집니다"
        )
        for needle in ("security definer", "set search_path = public", "language sql"):
            assert needle in migration_head.lower() or needle in migration_head, (
                "{} 가 함수 머리에 없습니다".format(needle)
            )
        assert re.search(r"(?im)^stable\s*$", migration_head), "stable 한 줄이 없습니다"

    def test_comment_matches_the_schema(self, schema):
        r"""`comment on function … is '…';` 문자열이 정본과 **가장 최근 마이그레이션(10-15a)** 에서 같아야 한다.

        ⓘ 2026-10-05b 로 comment 가 '열한 갈래'로 바뀌었다 — 10-01a 의 comment 는 원장이라 옛 글
        그대로 남고(test_the_10_01a_ledger_is_left_as_applied), 정본과 대조하는 쪽은 10-05b 였다.
        2026-10-12b 로 필지 공시 연도 규칙 한 구절이 더해져 대조 쪽이 10-12b 로 옮겼다.
        2026-10-15a 로 실거래·대장 판 월간 규칙 구절이 더해져 대조 쪽이 10-15a 로 옮겼다.

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
        # ⓘ 2026-10-18a(결정 0041)로 '열 갈래'·성적표 줄 뺌이 comment 에 들어가 대조 쪽이 10-18a 로 옮겼고,
        #   2026-10-29a(결정 0044)로 '열한 갈래'·대전 줄이 들어가 10-29a 로 옮겼다.
        migration_comment = extract_comment(read(DAEJEON_MIGRATION))
        assert migration_comment == schema_comment, (
            "10-29a 의 comment 가 정본(schema.sql)과 글자가 다릅니다 — 라이브 설명이 "
            "schema.sql 의 서술과 갈라집니다"
        )

    def test_the_10_01a_ledger_is_left_as_applied(self, permit_migration):
        """⛔ 10-01a 는 라이브에 적용된 원장이다 — 열 줄·두 갈래 그대로여야 한다(고쳐 쓰면 원장이 거짓말)."""
        body = statements(function_body(permit_migration, FN))
        assert body.count("union all") == 9
        assert "district_openclose" not in body
        assert r"^\d{4}[1-4]$" not in body
        assert "2026-10-05b" not in permit_migration


class TestSeoulOpenCloseRule:
    """2026-10-05b — 11번째 줄은 **기존 분기 규칙**을 쓰고, 'YYYYQ' 다섯 자리를 분기말 달로 옮긴다."""

    SEOUL_BRANCH = re.compile(
        r"when\s+r\.rule_kind\s*=\s*'seoul_openclose'\s+and\s+r\.basis\s*~\s*'\^\\d\{4\}\[1-4\]\$'\s*\n"
        r"\s*then\s+(left\(r\.basis,\s*4\)\s*\|\|\s*lpad\(\(right\(r\.basis,\s*1\)::int\s*\*\s*3\)::text,"
        r"\s*2,\s*'0'\))")
    RONE_BRANCH = re.compile(
        r"when\s+r\.rule_kind\s*=\s*'rone'\s+and\s+r\.basis\s*~\s*'\^\\d\{4\}Q\[1-4\]\$'\s*\n"
        r"\s*then\s+(.*)")

    def test_the_row_uses_the_seoul_rule(self, public_body):
        assert re.search(
            r"select\s+11,\s*'상권 개업·폐업 \(서울시\)',\s*'분기',\s*\n\s*"
            r"\(select max\(t\.quarter\)::text from district_openclose t\),\s*\n\s*'seoul_openclose'",
            public_body), "11번째 줄이 district_openclose 의 max(quarter) 와 seoul_openclose 규칙을 쓰지 않습니다"

    def test_third_branch_exists_and_equals_the_rone_formula(self, public_body):
        """셋째 갈래가 없으면 그 줄은 **조용히** '정해진 주기 없음'이 된다(결정 0033 v3 재검사).

        식은 부동산원 갈래와 글자가 같다 — 그 식이 라이브에서 2026Q2 → 2026-10-31 을 낸다
        (10-01a 머리말 적용 뒤 확인표). 그래서 20262 → 202606 → 2026-10-31(상권정보 줄과 같은 날).
        """
        m = self.SEOUL_BRANCH.search(public_body)
        assert m, "norm 의 셋째 갈래(서울시 YYYYQ)가 없습니다"
        r = self.RONE_BRANCH.search(public_body)
        assert r and r.group(1).strip() == m.group(1).strip()

    def test_mutation_without_third_branch_is_noticed(self, public_body):
        broken = self.SEOUL_BRANCH.sub("", public_body, count=1)
        assert broken != public_body
        assert not self.SEOUL_BRANCH.search(broken)

    def test_the_date_for_20262_is_2026_10_31(self):
        """그 식을 파이썬으로 그대로 따라 셈한다: 앞 네 자리 + 분기×3 → 분기말 달 + 5개월 - 하루."""
        import datetime
        basis = "20262"
        ym = basis[:4] + "{:02d}".format(int(basis[-1]) * 3)
        assert ym == "202606"
        y, m = int(ym[:4]), int(ym[4:]) + 5
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        assert datetime.date(y, m, 1) - datetime.timedelta(days=1) == datetime.date(2026, 10, 31)


# ── 2026-10-12b — 필지 줄의 기준 = 공시 연도 · 다음 갱신 = 다음 해 6월 30일 ──────────────

def parcel_row_columns(body):
    """10번째 줄(필지)이 parcel 에서 집계하는 칸 이름들(적힌 순서 · 소문자).

    잡는 꼴: `max(t.<칸>)` · `min(t.<칸>)` 뒤에 무엇이 붙든(`at time zone …`·`::date::text`) 그 줄 안의
    `from parcel t`. 그 줄은 `select 10, '필지 (토지 특성)'` 부터 다음 `union all` 까지로 자른다.
    ⚠️ 못 보는 것: 별칭이 t 가 아닌 꼴(`from parcel p`) · 스키마를 붙인 꼴(`public.parcel`) — 지금 판은
       모두 `from parcel t` 다. 줄을 못 찾으면 None(가드가 빨강을 낸다).
    """
    m = re.search(r"(?s)select\s+10,\s*'필지 \(토지 특성\)'(.*?)union\s+all", body)
    if not m:
        return None
    return [c.lower() for c in re.findall(
        r"(?is)\b(?:max|min)\(\s*t\.(\w+)\s*\).*?\bfrom\s+parcel\s+t\b", m.group(1))]


LAND_BRANCH = re.compile(
    r"when\s+n\.rule_kind\s*=\s*'land_year'\s+and\s+n\.basis\s*~\s*'(?P<re>[^']*)'\s*\n"
    r"\s*then\s+make_date\(n\.basis::int\s*\+\s*(?P<plus>\d+),\s*(?P<month>\d+),\s*(?P<day>\d+)\)")


def land_branch(body):
    """land_year 갈래의 (정규식, 더하는 해, 달, 날). 갈래가 없거나 꼴이 다르면 None."""
    m = LAND_BRANCH.search(body)
    if not m:
        return None
    return m.group("re"), int(m.group("plus")), int(m.group("month")), int(m.group("day"))


EXPECTED_BRANCH = (r"^\d{4}$", 1, 6, 30)


class TestLandYearRule:
    """2026-10-12b — 👤 결정: 기준 = '공시 연도'(max(land_price_year)) · 다음 갱신 = 다음 해 6월 30일."""

    def test_the_row_reads_the_notice_year(self, public_body):
        assert re.search(
            r"select\s+10,\s*'필지 \(토지 특성\)',\s*'공시 연도',\s*\n\s*"
            r"\(select max\(t\.land_price_year\)::text from parcel t\),\s*\n\s*'land_year',\s*\n\s*"
            r"'연 1회 \(브이월드\)'",
            public_body), "10번째 줄이 '공시 연도' · max(land_price_year) · land_year 규칙이 아닙니다"

    def test_the_row_no_longer_reads_updated_at(self, public_body):
        """⛔ 받아 둔 날(updated_at)이 아니라 공시 연도만 읽는다."""
        assert parcel_row_columns(public_body) == ["land_price_year"]

    def test_detector_sees_the_old_updated_at_row(self):
        """양성 대조 — 같은 탐지 함수에 옛 판(10-05b 원장)을 넣으면 updated_at 을 잡는다."""
        old = statements(function_body(read(OPENCLOSE_MIGRATION), FN))
        assert parcel_row_columns(old) == ["updated_at"]

    @pytest.mark.parametrize("snippet", [
        "(select (max(t.updated_at) at time zone 'Asia/Seoul')::date::text from parcel t)",
        "(select min(t.updated_at)::text from parcel t)",
        "(select MAX( t.updated_at )::text\n              from parcel t)",
    ])
    def test_detector_catches_updated_at_put_back(self, public_body, snippet):
        """양성 대조(흔한 꼴 + 변형 꼴) — 기준을 updated_at 으로 되돌리면 같은 함수가 잡는다."""
        good = "(select max(t.land_price_year)::text from parcel t)"
        assert good in public_body, "전제: 지금 판의 필지 줄 꼴"
        broken = public_body.replace(good, snippet, 1)
        assert parcel_row_columns(broken) == ["updated_at"]

    def test_branch_is_next_year_june_30_for_four_digits_only(self, public_body):
        assert land_branch(public_body) == EXPECTED_BRANCH, (
            "land_year 갈래가 '네 자리 연도일 때만 다음 해 6월 30일'이 아닙니다(👤 2026-10-12 결정)")

    @pytest.mark.parametrize("old,new", [
        ("make_date(n.basis::int + 1, 6, 30)", "make_date(n.basis::int + 1, 5, 31)"),
        ("make_date(n.basis::int + 1, 6, 30)", "make_date(n.basis::int, 6, 30)"),
        (r"n.basis ~ '^\d{4}$'", r"n.basis ~ '\d{4}'"),
        (r"n.basis ~ '^\d{4}$'", r"n.basis ~ '^\d+$'"),
    ])
    def test_mutation_of_the_branch_is_noticed(self, public_body, old, new):
        assert old in public_body, "전제: 그 글자가 지금 판에 있다"
        assert land_branch(public_body.replace(old, new, 1)) != EXPECTED_BRANCH

    def test_the_date_for_2026_is_2027_06_30(self):
        """정본의 갈래 숫자를 그대로 읽어 파이썬으로 셈한다: make_date(연도 + 1, 6, 30)."""
        import datetime
        branch = land_branch(statements(function_body(read(SCHEMA), FN)))
        assert branch
        _, plus, month, day = branch
        assert datetime.date(2026 + plus, month, day) == datetime.date(2027, 6, 30)

    @pytest.mark.parametrize("basis", ["2026Q2", "202606", "26", "", "2026-06-30", "20262"])
    def test_other_shapes_do_not_match_the_branch(self, basis):
        """모양이 다르면 그 갈래가 안 걸린다(→ next_expected null) — 정본의 정규식 그대로 본다.

        ⓘ PostgreSQL `~ '^\\d{4}$'` 와 파이썬 re.search 는 이 꼴(앵커 둘·숫자 넷)에서 같은 뜻이다.
           실제 PostgreSQL 판정은 TestLandYearRealRun 이 본다(로컬에서만).
        """
        branch = land_branch(statements(function_body(read(SCHEMA), FN)))
        assert branch
        assert re.search(branch[0], basis) is None
        assert re.search(branch[0], "2026") is not None   # 양성 대조

    def test_the_10_05b_ledger_is_left_as_applied(self):
        """⛔ 10-05b 는 라이브에 적용된 원장이다 — 옛 필지 줄('갱신일' · updated_at · 'none') 그대로."""
        text = read(OPENCLOSE_MIGRATION)
        body = statements(function_body(text, FN))
        assert "'갱신일'" in body
        assert "land_price_year" not in body
        assert "land_year" not in body
        assert "2026-10-12b" not in text


@pytest.fixture(scope="module")
def land_migration():
    return read(LAND_MIGRATION)


class TestLandYearMigrationShape:
    """2026-10-12b 의 순서 — 색인(concurrently · begin 밖) → 관문 → begin → 함수 → commit → notify."""

    INDEX_RE = re.compile(
        r"(?im)^create\s+index\s+concurrently\s+if\s+not\s+exists\s+idx_parcel_land_price_year\s+"
        r"on\s+parcel\s*\(\s*land_price_year\s*\)\s*;")

    def test_order(self, land_migration):
        code = statements(land_migration)
        timeout = re.search(r"(?im)^set\s+statement_timeout\s*=\s*'900s'\s*;", code)
        index = self.INDEX_RE.search(code)
        gate = re.search(r"(?im)^do\s+\$\$", code)
        lock = re.search(r"(?im)^set\s+lock_timeout\s*=\s*'\d+s'\s*;", code)
        begin = re.search(r"(?im)^begin\s*;", code)
        create = re.search(r"(?im)^create\s+or\s+replace\s+function\s+get_data_freshness\s*\(", code)
        revoke = re.search(r"(?im)^revoke\s+all\s+on\s+function\s+get_data_freshness\s*\(", code)
        commit = re.search(r"(?im)^commit\s*;", code)
        notify = code.find("notify pgrst, 'reload schema';")
        assert all((timeout, index, gate, lock, begin, create, revoke, commit)) and notify != -1
        assert (timeout.start() < index.start() < gate.start() < lock.start() < begin.start()
                < create.start() < revoke.start() < commit.start() < notify), (
            "statement_timeout → 색인 → 관문 → lock_timeout → begin → 함수 → revoke → commit → notify "
            "순서가 아닙니다")

    def test_gate_checks_the_index_is_valid(self, land_migration):
        gate = re.search(r"(?ims)^do\s+\$\$(.*?)\$\$\s*;", statements(land_migration))
        assert gate, "관문(do 블록)이 없습니다"
        assert "idx_parcel_land_price_year" in gate.group(1)
        assert re.search(r"(?i)\bi\.indisvalid\b", gate.group(1))
        assert re.search(r"(?i)\braise\s+exception\b", gate.group(1))

    def test_no_concurrently_inside_the_transaction(self, land_migration):
        code = statements(land_migration)
        b = re.search(r"(?im)^begin\s*;", code).start()
        c = re.search(r"(?im)^commit\s*;", code).start()
        assert "concurrently" not in code[b:c].lower()

    def test_only_the_public_function_is_recreated(self, land_migration):
        """api 쌍둥이는 본문이 그대로라 다시 만들지 않는다 — 만들면 grant 를 다시 줘야 한다."""
        made = re.findall(r"(?im)^create\s+(?:or\s+replace\s+)?function\s+([\w.]+)\s*\(",
                          statements(land_migration))
        assert made == [FN], made

    def test_no_grant_at_all(self, land_migration):
        assert not re.search(r"(?im)^\s*grant\s", statements(land_migration))
        assert grant_targets(land_migration) == []

    def test_public_original_is_revoked_again(self, land_migration):
        assert re.search(
            r"(?im)^revoke\s+all\s+on\s+function\s+{}\s*\(\s*\)\s+"
            r"from\s+public,\s*anon,\s*authenticated\s*;".format(FN),
            statements(land_migration))

    def test_function_text_equals_the_schema(self, schema):
        """머리·본문·comment·revoke 덩어리가 정본과 글자 그대로 — 드리프트 가드는 본문만 본다.

        ⓘ 2026-10-15a 부터 정본과 같아야 하는 쪽은 10-15a 였고, 2026-10-18a(결정 0041 — 9번 줄 뺌)부터는
          10-18a 였고, 2026-10-29a(결정 0044 — 대전 줄 더함)부터는 10-29a 다(10-12b·10-15a·10-18a 는 원장).
        """
        def block(sql):
            m = re.search(
                r"(?ms)^create\s+or\s+replace\s+function\s+get_data_freshness\s*\(.*?"
                r"^revoke\s+all\s+on\s+function\s+get_data_freshness\s*\(\)[^\n]*;",
                sql.replace("\r\n", "\n"))
            assert m, "덩어리를 못 찾았습니다"
            return m.group(0)
        assert block(read(DAEJEON_MIGRATION)) == block(schema)

    def test_the_10_12b_ledger_is_left_as_applied(self, land_migration):
        """⛔ 10-12b 는 라이브에 적용된 원장이다 — 옛 실거래('none'·'수시')·대장('적재일'·building) 줄 그대로."""
        body = statements(function_body(land_migration, FN))
        assert "'수시 (서울·대전 전부 활성화 뒤 확대)'" in body
        assert "'적재일'" in body and "from building t" in body
        assert "'tx'" not in body and "ledger_release" not in body
        assert body.count("interval '2 months'") == 0
        assert "2026-10-15a" not in land_migration

    def test_schema_has_the_index(self, schema):
        assert re.search(
            r"(?im)^create\s+index\s+if\s+not\s+exists\s+idx_parcel_land_price_year\s+"
            r"on\s+parcel\s*\(\s*land_price_year\s*\)\s*;", statements(schema))

    def test_comment_names_the_new_rule(self, land_migration):
        m = re.search(r"(?ims)^comment\s+on\s+function\s+{}\s*\(\s*\)\s+is(.*?);\s*$".format(FN),
                      land_migration)
        assert m
        assert "공시 연도의 다음 해 6월 30일" in m.group(1)
        assert "2026-10-12b" in m.group(1)
        assert "갱신일" not in m.group(1)


# ── 로컬 PostgreSQL 이 있을 때만 — 새 규칙을 실제로 돌린다 ─────────────────────────────

LAND_SHIM = """
create table snapshot_release (published_ym text);
create table transaction (contract_ym text);
create table building (updated_at timestamptz);
create table district (computed_at timestamptz);
create table lh_notice (collected_at timestamptz);
create table arch_permit (loaded_ym text);
create table nts_base_price (notice_date date);
create table rent_stat (quarter char(6));
create table price_gate_sigungu (loaded_at timestamptz);
create table parcel (pnu char(19) primary key, land_price_year smallint, updated_at timestamptz);
create table district_openclose (quarter text);
-- 2026-10-15a — 정본 함수의 건축물대장 줄이 이 표지를 읽는다(없으면 함수 만들기가 실패한다).
create table ledger_release (release_ym text);
-- 2026-10-29a(결정 0044) — 정본 함수의 대전시 동네 폐업 줄이 이 표지를 읽는다.
create table daejeon_closure_release (received_on date);
-- 모양 시험용 — 필지 줄의 basis 를 아무 글자로나 바꿔 넣는 자리(실제 함수에는 없다).
create table land_basis_override (v text);
"""

PARCEL_BASIS = "(select max(t.land_price_year)::text from parcel t)"


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    psycopg2 = pytest.importorskip("psycopg2")
    initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
    if not initdb or not pg_ctl:
        pytest.skip("로컬 PostgreSQL(initdb·pg_ctl)이 없다 — CI 는 글자 가드만 본다")
    data = str(tmp_path_factory.mktemp("pgdata"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    subprocess.run([initdb, "-D", data, "-U", "postgres", "-A", "trust", "-E", "UTF8",
                    "--no-locale"], check=True, capture_output=True)
    log = os.path.join(data, "log.txt")
    # ⛔ capture_output 금지 — 서버 자식이 파이프를 물려받아 run() 이 끝없이 기다린다(Windows 실측).
    subprocess.run([pg_ctl, "-D", data, "-l", log, "-w", "-t", "60", "-o",
                    "-p {} -c listen_addresses=127.0.0.1".format(port), "start"],
                   check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=120)
    try:
        conn = None
        for _ in range(30):
            try:
                conn = psycopg2.connect(host="127.0.0.1", port=port, user="postgres", dbname="postgres")
                break
            except psycopg2.OperationalError:
                time.sleep(0.5)
        assert conn is not None, "로컬 PostgreSQL 에 못 붙었다"
        conn.autocommit = True
        yield conn
        conn.close()
    finally:
        subprocess.run([pg_ctl, "-D", data, "-m", "fast", "-w", "stop"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)


def _create_fn_sql(sql):
    """`create or replace function get_data_freshness()` 부터 그 `$$;` 까지(줄머리 고정)."""
    m = re.search(r"(?ms)^create\s+or\s+replace\s+function\s+get_data_freshness\s*\(.*?^\$\$;",
                  sql.replace("\r\n", "\n"))
    assert m, "함수 문장을 못 찾았습니다"
    return m.group(0)


def _land_row(conn, fn_sql, parcel_years=(), override=None):
    """흉내 판 위에 함수를 만들고 필지 줄 (basis_kind, basis, next_expected) 를 돌려준다."""
    cur = conn.cursor()
    cur.execute("drop schema if exists public cascade; create schema public;")
    cur.execute(LAND_SHIM)
    if override is not None:
        assert PARCEL_BASIS in fn_sql, "전제: 필지 줄의 basis 꼴"
        fn_sql = fn_sql.replace(PARCEL_BASIS, "(select v from land_basis_override)", 1)
        cur.execute("insert into land_basis_override values (%s)", (override,))
    cur.execute(fn_sql)
    for i, y in enumerate(parcel_years):
        cur.execute("insert into parcel values (%s, %s, now())", ("{:019d}".format(i + 1), y))
    cur.execute("select src, basis_kind, basis, next_expected from get_data_freshness()")
    rows = cur.fetchall()
    # 정본은 2026-10-18a(결정 0041)부터 열 줄 → 2026-10-29a(결정 0044 대전 줄)부터 열한 줄 ·
    # 원장(10-12b)은 열한 줄(성적표 줄이 든 판).
    want = 11 if ("'참고 시세 성적표'" in fn_sql or "'동네 폐업 (대전시)'" in fn_sql) else 10
    assert len(rows) == want, "{}줄이 아닙니다: {}".format(want, len(rows))
    land = [r for r in rows if r[0] == "필지 (토지 특성)"]
    assert len(land) == 1
    return land[0][1:]


class TestLandYearRealRun:
    @pytest.mark.parametrize("path", (SCHEMA, LAND_MIGRATION), ids=("schema", "2026-10-12b"))
    def test_2026_is_due_2027_06_30(self, pg, path):
        kind, basis, nxt = _land_row(pg, _create_fn_sql(read(path)), (2026, 2025, None, 2018))
        assert (kind, basis, str(nxt)) == ("공시 연도", "2026", "2027-06-30")

    def test_no_parcel_rows_keeps_the_row_with_nulls(self, pg):
        assert _land_row(pg, _create_fn_sql(read(SCHEMA)), ()) == ("공시 연도", None, None)

    def test_only_null_years_keeps_the_row_with_nulls(self, pg):
        assert _land_row(pg, _create_fn_sql(read(SCHEMA)), (None, None)) == ("공시 연도", None, None)

    @pytest.mark.parametrize("bad", ["2026Q2", "202606", "26", "20262", "2026-06-30", ""])
    def test_other_shapes_give_null_not_an_error(self, pg, bad):
        """⛔ 모양이 안 맞으면 계산하지 않는다 — `::int` 가 터지면 표가 통째로 사라진다."""
        _, basis, nxt = _land_row(pg, _create_fn_sql(read(SCHEMA)), override=bad)
        assert basis == bad and nxt is None

    def test_override_shim_really_feeds_the_branch(self, pg):
        """양성 대조 — 같은 흉내 길로 '2030' 을 넣으면 2031-06-30 이 나온다(흉내가 헛돌지 않는다)."""
        _, basis, nxt = _land_row(pg, _create_fn_sql(read(SCHEMA)), override="2030")
        assert (basis, str(nxt)) == ("2030", "2031-06-30")

    @pytest.mark.parametrize("old,new", [
        ("make_date(n.basis::int + 1, 6, 30)", "make_date(n.basis::int + 1, 5, 31)"),
        ("make_date(n.basis::int + 1, 6, 30)", "make_date(n.basis::int, 6, 30)"),
    ])
    def test_mutation_of_the_date_is_noticed(self, pg, old, new):
        fn = _create_fn_sql(read(SCHEMA))
        assert old in fn
        _, _, nxt = _land_row(pg, fn.replace(old, new, 1), (2026,))
        assert str(nxt) != "2027-06-30"

    def test_mutation_loose_shape_check_is_noticed(self, pg):
        """정규식을 앵커 없이 느슨하게 하면 '26' 에서 지어낸 날짜(0027-06-30)가 나온다."""
        fn = _create_fn_sql(read(SCHEMA)).replace(r"n.basis ~ '^\d{4}$'", r"n.basis ~ '\d+'", 1)
        assert r"n.basis ~ '\d+'" in fn
        _, _, nxt = _land_row(pg, fn, override="26")
        assert nxt is not None
