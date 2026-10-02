# -*- coding: utf-8 -*-
"""마이그레이션 2026-09-05e(성적표 공개 — 게이트 읽기 함수)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙여 넣기 전에는 아무도 모르는 종류의 실수**다.
DB 없이 SQL 글자만 본다(CI 에는 DB 가 없다) — 대신 아래는 글자만으로 확실히 잡힌다.

  1) 나가는 칸이 늘어난다 → 이 함수는 **구별 요약**만 내보내기로 하고 연 길이다.
     개별 검증 거래(필지·층·단가)를 붙이는 순간 공개 파일로 원자료가 나가는 길이 된다.
  2) 표 `price_gate_sigungu` 가 열린다 → 화면은 함수로만 읽는데 표가 열리면 그 계약이
     통째로 우회된다(결정 0013 §4 의 "정본은 서버 한 곳"이 무너진다).
  3) `grant` 가 `revoke` 보다 먼저 온다 → 대시보드가 함수를 다시 만들 때 붙는 anon
     기본권한을 못 걷는다.
  4) public 원본까지 연다 → api 통과 함수가 security definer 라 열 필요가 없는데,
     열면 옛 문(public 스키마)으로 가는 길이 하나 더 생긴다.
  5) `notify pgrst` 누락 → DB 에는 함수가 멀쩡히 있는데 화면만 404(PGRST202) 가 난다.
  6) 정본(schema.sql) 미동기 → 새 환경만 다르게 만들어진다.
"""

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
SCORECARD_TS = os.path.join(ROOT, "src", "lib", "scorecard.ts")
MIGRATION = os.path.join(
    ROOT, "supabase", "migrations", "2026-09-05e_price_gate_read.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

BOTH = [MIGRATION, SCHEMA]

TABLE = "price_gate_sigungu"
FN = "list_price_gate"

# 나가도 되는 칸 — **이것이 전부다**. 결정 0013 §2 의 판정과 그 근거까지.
RETURNED_COLUMNS = (
    "sigungu_code",
    "sigungu_nm",
    "n_paired",
    "ladder_mdape",
    "base_mdape",
    "gate_pass",
    "loaded_at",
)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def statements(sql):
    """주석을 걷어낸 **실제 SQL 문장만**.

    설명 주석에 적어 둔 말이 문장으로 오해되면 코드가 망가져도 초록이 된다
    (test_lh_notice_migration·test_schema_grant_signatures 가 같은 이유로 같은 방식을 쓴다).
    """
    return "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )


def fn_block(sql, name=FN, schema=""):
    """`create or replace function [schema.]<name>(` 부터 `$$;` 까지 (본문 + 머리)."""
    m = re.search(
        r"(?im)^create\s+or\s+replace\s+function\s+"
        + (re.escape(schema) if schema else r"(?!api\.)(?:public\.)?")
        + name + r"\s*\(",
        sql,
    )
    assert m, "{}{} 정의를 못 찾았습니다".format(schema, name)
    end = sql.index("$$;", m.start())
    return sql[m.start():end]


# ── 탐지 함수 (2026-10-02 감사) ─────────────────────────────────────────────
# "없다"만 단언하는 가드는 탐지가 헛돌아도 초록이다. 그래서 탐지를 **글자를 받아 위반
# 목록을 돌려주는 함수**로 빼 두고, 가드 본체와 맨 아래 양성 대조(§7)가 같은 함수를 지난다.


def write_words_in(body):
    """함수 본문에서 **쓰기 낱말**을 찾아 돌려준다 — 없으면 빈 목록.

    ⛔ `update` 만 뒤에 낱말 경계를 둔다(`updated_at` 같은 칸 이름과 가르려고).
       예전에는 금지어가 `"update "`(뒤 공백)라 **줄바꿈이 오면** 놓쳤다.
    ⓘ 나머지 셋은 예전 그대로 글자가 들어 있기만 해도 잡는다(좁히지 않는다).
    ⚠️ 거짓 빨강 쪽: 뒤쪽 낱말 경계만 보므로 `last_update` 처럼 **`update` 로 끝나는 칸 이름**이
       걸린다(2026-10-02 검사관 실측 · 지금 본문에는 0건) — 그런 칸을 쓰게 되면 이 탐지를
       고칠 것(시험을 느슨하게 하지 말고).
    """
    return re.findall(r"insert|delete|truncate|update\b", body.lower())


def table_grants_in(text, name):
    """`grant <무엇이든> on [table] [public.]<name>` 꼴을 찾아 돌려준다 — 없으면 빈 목록.

    ⛔ 예전에는 `"grant select on <표>"` 글자를 통째로 찾아, `on table …` 이나 `public.`
       접두가 붙으면 놓쳤다. 권한 종류(select·all·여러 개)와 칸 수(줄바꿈 포함)는 안 가린다.
    ⓘ `[^;]` 라서 한 문장(세미콜론) 밖으로는 안 넘어간다 — 앞 문장의 grant 와 뒤 문장의
       `revoke all on <표>` 가 이어 붙어 걸리는 일이 없다.
    ⚠️ 못 보는 것(2026-10-02 검사관 실측): 여러 대상 나열에서 첫째가 아닌 자리
       (`on v_floor_stack, <표>`) · 따옴표 이름(`"<표>"`) · `on all tables in schema public`.
    """
    return [m.group(0) for m in re.finditer(
        r"(?i)\bgrant\b[^;]*?\bon\s+(?:table\s+)?(?:public\.)?" + re.escape(name), text)]


def public_fn_grants_in(text, name):
    """함수 grant 문장의 **대상** 가운데 api 통과 함수가 아닌 `<name>(` — 없으면 빈 목록.

    `grant … on function|routine …` 문장마다 대상들을 뽑아, 이름이 `<name>` 인데
    `api.<name>` 이 아닌 것(= public 원본 · 소문자, 적힌 그대로)을 돌려준다.
    ⛔ 예전에는 `… to anon` 까지 글자로 못 박아, 받는 쪽 순서가 바뀌면
       (`to authenticated, anon`) 놓쳤다. 받는 쪽은 아예 안 본다 — 누구에게든 열면 안 된다.
    ⛔ `grant execute on function [public.]<name>(` 를 한 덩어리로 찾으면 `grant all` ·
       여러 대상 나열(`api.<name>(), <name>()`) · `on routine` 을 놓친다(2026-10-02 검사관
       실측) — 형제 test_arch_permit_migration.py 의 grant_targets 와 같은 방식으로 본다.
    ⓘ `revoke grant option for …` 는 회수라 건너뛴다.
    ⚠️ 못 보는 것: 인자 괄호 없는 `on function <name> to …` · 따옴표 이름
       (`"<name>"()`) · `on procedure`.
    """
    found = []
    for stmt in re.findall(
            r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*?"
            r"\bon\s+(?:function|routine)\b([^;]*)",
            text):
        found += re.findall(
            r"(?i)(?<![\w.])((?:\w+\.)?" + re.escape(name) + r")\s*\(", stmt)
    return [t.lower() for t in found if t.lower() != "api." + name]


def allowlist_hits(name, allowlists=None):
    """허용 목록 안에서 **맨 이름이 `name` 인 항목**을 적힌 그대로 모은다 — 없으면 빈 목록.

    ⛔ 허용 목록은 2026-09-01 부터 `스키마.이름` 꼴이라, 맨 이름으로 `not in` 을 보면
       `"public.<표>"` 로 넣는 순간 초록이다. 스키마를 벗긴 이름으로 견준다
       (벗기는 규칙은 post_load._bare_names 한 곳 — 여기서 다시 적지 않는다).
    ⓘ `allowlists` 를 안 주면 지금의 실제 두 목록(읽기·부르기)을 본다.
    """
    import post_load

    if allowlists is None:
        allowlists = (post_load.ANON_READABLE_ALLOWLIST,
                      post_load.ANON_CALLABLE_ALLOWLIST)
    return [
        q for allow in allowlists for q in allow
        if post_load._bare_names((q,)) == (name,)
    ]


# ── 1. 나가는 것은 구별 요약뿐 ───────────────────────────────────────────────


class TestOnlySummariesLeave:
    @pytest.mark.parametrize("path", BOTH)
    @pytest.mark.parametrize("col", RETURNED_COLUMNS)
    def test_every_promised_column_is_there(self, path, col):
        block = fn_block(read(path))
        assert re.search(r"(?m)^\s+{}\s".format(col), block), col

    @pytest.mark.parametrize("path", BOTH)
    def test_nothing_else_is_returned(self, path):
        """⛔ **칸이 늘면 여기서 먼저 운다.**

        이 함수의 계약은 "구별 요약 한 줄씩"이다. 검증 거래를 붙이는 것은 별건 판단이라,
        조용히 늘어나는 것을 막는다(returns table 안의 칸 이름을 통째로 대조한다).
        """
        block = fn_block(read(path))
        head = block[block.index("returns table"):block.index(")", block.index("returns table"))]
        found = tuple(m.group(1) for m in re.finditer(r"(?m)^\s+(\w+)\s+\w", head))
        assert found == RETURNED_COLUMNS

    @pytest.mark.parametrize("path", BOTH)
    def test_the_raw_transaction_table_is_never_touched(self, path):
        """⛔ 개별 실거래는 이 길로 안 나간다 — 함수 본문이 `transaction` 을 안 읽는다."""
        body = statements(fn_block(read(path)))
        assert "transaction" not in body
        assert "검증거래별원자료" not in body

    @pytest.mark.parametrize("path", BOTH)
    def test_it_only_reads(self, path):
        """⛔ 표를 채우는 것은 backtest_price.py → load_price_gate.py 다(결정 0013 §4).
        여기에 쓰기가 붙는 날 그 규칙이 우회된다."""
        body = statements(fn_block(read(path)))
        assert write_words_in(body) == []

    @pytest.mark.parametrize("path", BOTH)
    def test_it_does_not_filter_out_the_failing_districts(self, path):
        """⛔ 통과한 구만 주면 "왜 우리 구는 없나"에 답할 수 없다 — 탈락 사유가 본론이다."""
        body = statements(fn_block(read(path)))
        assert "where" not in body.lower()
        assert "gate_pass" in body


# ── 2. 표는 밖에서 잠긴 채로 ─────────────────────────────────────────────────


class TestTableStaysClosed:
    def test_the_table_is_revoked_in_the_canonical_file(self):
        """이 마이그레이션은 표를 안 만든다 — 정본의 잠금이 그대로인지만 본다."""
        text = statements(read(SCHEMA))
        assert "revoke all on {} from public, anon, authenticated;".format(TABLE) in text
        assert "alter table {} enable row level security".format(TABLE) in text

    @pytest.mark.parametrize("path", BOTH)
    def test_the_migration_never_opens_the_table(self, path):
        text = statements(read(path))
        assert table_grants_in(text, TABLE) == []

    def test_the_exposure_check_does_not_allow_the_table(self):
        assert allowlist_hits(TABLE) == []


# ── 3. 문은 api 쪽 하나만 ────────────────────────────────────────────────────


class TestOnlyTheApiTwinIsOpened:
    @pytest.mark.parametrize("path", BOTH)
    def test_the_api_twin_is_granted(self, path):
        text = statements(read(path))
        assert "grant execute on function api.{}() to anon, authenticated;".format(FN) in text

    @pytest.mark.parametrize("path", BOTH)
    def test_the_public_original_stays_shut(self, path):
        """⛔ 통과 함수가 security definer 라 public 원본을 열 필요가 없다."""
        text = statements(read(path))
        assert public_fn_grants_in(text, FN) == []
        assert "revoke all on function {}() from public, anon, authenticated;".format(FN) in text

    @pytest.mark.parametrize("path", BOTH)
    def test_revokes_before_granting(self, path):
        """⛔ 순서가 뒤집히면 대시보드가 붙인 anon 기본권한을 못 걷는다."""
        text = statements(read(path))
        assert text.index("revoke all on function api.{}()".format(FN)) < text.index(
            "grant execute on function api.{}()".format(FN))

    @pytest.mark.parametrize("path", BOTH)
    def test_the_api_twin_is_security_definer_with_an_empty_search_path(self, path):
        block = fn_block(read(path), schema="api.")
        assert "security definer" in block
        assert "set search_path = ''" in block

    def test_it_is_in_the_exposure_allowlist(self):
        """post_load --check 의 허용 목록에 없으면 '뚫렸다'고 잘못 알린다."""
        import post_load

        assert "api.{}".format(FN) in post_load.ANON_CALLABLE_ALLOWLIST
        assert FN in post_load.ANON_CALLABLE_NAMES

    def test_the_migration_tells_postgrest_to_reload(self):
        """⛔ 빠뜨리면 DB 에는 있는데 화면만 404(PGRST202) 가 난다 — 찾기 어려운 고장이다."""
        assert "notify pgrst, 'reload schema';" in statements(read(MIGRATION))


# ── 4. 코멘트가 규칙을 싣고 다닌다 ───────────────────────────────────────────


class TestTheCommentCarriesTheRule:
    @pytest.mark.parametrize("path", BOTH)
    def test_says_where_the_truth_lives(self, path):
        """함수 코멘트는 **라이브 DB 안에 남는 유일한 설명**이다 — 정본 규칙을 여기 싣는다."""
        text = read(path)
        i = text.index("comment on function {}() is".format(FN))
        cmt = text[i:text.index(";", i)]
        assert "0013" in cmt, "어느 결정에서 온 규칙인지 적어야 합니다"
        assert "2026-09-05e" in cmt, "어느 마이그레이션이 만들었는지 적어야 합니다"
        assert "security definer" in cmt


# ── 5. 기준선이 두 곳에서 갈라지지 않게 ──────────────────────────────────────


class TestTheGateThresholdDoesNotDrift:
    """⛔ 기준선(결정 0013 §2 ①)이 **파이썬과 화면 두 곳에** 적혀 있다.

    왜 두 곳에 있나 — 쓰임이 다르다:
      · `scripts/backtest_price.py` 의 `GATE_MAX_MDAPE` = **판정의 정본**. 이 값으로
        `gate_pass()` 가 통과 여부를 계산하고 그 결과가 통과구.csv → price_gate_sigungu 로
        흘러간다. (`scripts/load_price_gate.py` 는 그 판정을 다시 계산해 **대조**만 하므로
        기준선을 갖고 있지 않다.)
      · `src/lib/scorecard.ts` 의 `GATE_MDAPE_LIMIT` = **설명용**. 판정에는 안 쓰고,
        떨어진 구에서 "오차 중앙값이 기준선 N% 를 넘습니다"라고 말할 때만 쓴다.

    갈라지면 무슨 일이 나나 — 화면이 **옛 기준선을 말한다.** 판정은 서버 값을 그대로
    쓰므로 여전히 맞는데 설명만 틀린, 에러가 전혀 안 나는 종류의 거짓말이다. 그래서 기계가 잰다.

    ⚠️ 이 시험은 화면 파일을 **글자로** 본다(파이썬이 TS 를 실행할 수 없다). 그래서 상수를
       계산식으로 바꾸면 여기서 빨간불이 나는데, 그때는 시험을 고칠 것이 아니라 "왜 상수가
       아니어야 하나"를 먼저 답해야 한다.
    """

    def test_the_python_side_is_the_documented_baseline(self):
        import backtest_price

        # 결정 0013 §2 ① — 사장님 재결재로 확정된 값. 바꾸는 것은 재결재 사항이다.
        assert backtest_price.GATE_MAX_MDAPE == 0.3

    def test_the_screen_copy_says_the_same_number(self):
        import backtest_price

        src = read(SCORECARD_TS)
        m = re.search(r"export\s+const\s+GATE_MDAPE_LIMIT\s*=\s*([0-9.]+)\s*;", src)
        assert m, "src/lib/scorecard.ts 에서 GATE_MDAPE_LIMIT 을 못 찾았습니다"
        assert float(m.group(1)) == backtest_price.GATE_MAX_MDAPE, (
            "화면 기준선({})이 판정의 정본 backtest_price.GATE_MAX_MDAPE({})와 다릅니다 — "
            "화면 문구만 옛 기준선을 말하게 됩니다".format(m.group(1), backtest_price.GATE_MAX_MDAPE)
        )

    def test_the_screen_constant_is_not_a_statistic_literal(self):
        """⚠️ 이 상수는 **정책 값**이라 '숫자 복사 금지' 가드에 걸리면 안 된다.

        화면 파일에는 통계 수치 리터럴이 하나도 없어야 하고(`src/lib/scorecard.test.ts`),
        그 가드는 백분율 모양(`\\d+\\.\\d+%`)과 성적표 대표 수치를 찾는다. `0.3` 은 둘 다
        아니므로 공존한다 — 이 시험은 그 공존이 **우연이 아님**을 못박아 둔다(누가 상수를
        `30.0%` 같은 글자로 바꾸면 저쪽 가드가 울리고, 여기서 왜인지 알 수 있다).
        """
        line = [ln for ln in read(SCORECARD_TS).splitlines()
                if "GATE_MDAPE_LIMIT =" in ln][0]
        assert not re.search(r"\d+\.\d+\s?%", line)
        assert not re.search(r"\b(53|93)\.\d", line)

    def test_the_loader_only_cross_checks_and_owns_no_threshold(self):
        """⛔ `load_price_gate.py` 에 기준선 숫자를 새로 두지 않는다 — 두면 정본이 셋이 된다."""
        import load_price_gate

        assert not hasattr(load_price_gate, "GATE_MAX_MDAPE")
        # 판정은 언제나 backtest_price 의 함수 하나로만 한다.
        assert "backtest_price.gate_pass(" in read(
            os.path.join(SCRIPTS_DIR, "load_price_gate.py"))


# ── 6. 정본 동기 ────────────────────────────────────────────────────────────


class TestSchemaMirrorsTheMigration:
    @pytest.mark.parametrize("name,schema", [(FN, ""), (FN, "api.")])
    def test_both_functions_are_in_the_canonical_file(self, name, schema):
        assert re.search(
            r"(?im)^create\s+or\s+replace\s+function\s+" + re.escape(schema) + name + r"\s*\(",
            read(SCHEMA))

    def test_the_bodies_are_letter_for_letter_the_same(self):
        """⛔ 정본만 살짝 다듬는 것이 곧 정본↔라이브 불일치다(2026-09-01 2차 적대검증).

        ⓘ 전 함수를 훑는 형제 가드가 따로 있다(tests/test_schema_function_drift.py).
          여기서는 이 함수 하나를 못 박아 두어, 실패 메시지가 무엇 때문인지 바로 보이게 한다.
        """
        for schema in ("", "api."):
            assert fn_block(read(MIGRATION), schema=schema) == fn_block(read(SCHEMA), schema=schema)


# ── 7. 위 가드들이 진짜 무는가 (2026-10-02 감사 — 양성 대조) ─────────────────
# 가드 본체와 **같은 탐지 함수**에 나쁜 예를 넣어 본다. 흔한 꼴만이 아니라 감사 때
# 실제로 놓쳤던 변형 꼴까지 — 그 꼴을 다시 놓치게 고치면 여기가 먼저 운다.


@pytest.mark.parametrize("bad", [
    "select 1 from (delete from t returning 1) d",
    "insert into t values (1)",
    "truncate t",
    "update t set n = 0",
    "select 1 from (update\n    t set n = 0 returning 1) u",   # 놓치던 꼴 — 뒤가 줄바꿈
    "UPDATE\tt SET n = 0",
    "select 1 from t for update;",
])
def test_write_words_in_catches_every_write(bad):
    assert write_words_in(bad), bad


def test_write_words_in_leaves_plain_reads_alone():
    assert write_words_in(
        "select g.loaded_at, g.updated_at\n  from price_gate_sigungu g\n  order by 1") == []


@pytest.mark.parametrize("bad", [
    "grant select on {t} to anon;",
    "grant all on {t} to anon;",
    "grant select on table public.{t} to anon;",               # 놓치던 꼴
    "grant select on public.{t} to anon;",
    "grant select, insert on table {t} to authenticated;",
    "GRANT ALL PRIVILEGES ON TABLE {t} TO anon;",
    "grant select\n  on {t}\n  to anon;",
])
def test_table_grants_in_catches_every_shape(bad):
    assert table_grants_in(bad.format(t=TABLE), TABLE), bad


@pytest.mark.parametrize("good", [
    "revoke all on {t} from public, anon, authenticated;",
    "alter table {t} enable row level security;",
    "grant execute on function api.list_price_gate() to anon, authenticated;",
    # 앞 문장의 grant 가 뒤 문장의 표 이름과 이어 붙어 걸리면 안 된다.
    "grant select on v_floor_stack to anon;\nrevoke all on {t} from anon;",
])
def test_table_grants_in_leaves_the_rest_alone(good):
    assert table_grants_in(good.format(t=TABLE), TABLE) == [], good


@pytest.mark.parametrize("bad", [
    "grant execute on function {f}() to anon;",
    "grant execute on function public.{f}() to anon;",
    "grant execute on function {f}() to authenticated, anon;",   # 놓치던 꼴 — 받는 쪽 순서
    "grant execute on function public.{f}() to authenticated;",
    "GRANT EXECUTE ON FUNCTION {f} () TO anon;",
    "grant execute\n  on function {f}()\n  to anon;",
    # ↓ 검사관이 "초록(못 잡음)"이라 적은 세 꼴(2026-10-02)
    "grant all on function {f}() to anon;",
    "grant execute on function api.{f}(), {f}() to anon;",      # 여러 대상 중 public 원본
    "grant execute on routine {f}() to anon;",
])
def test_public_fn_grants_in_catches_any_grantee(bad):
    assert public_fn_grants_in(bad.format(f=FN), FN), bad


@pytest.mark.parametrize("good", [
    "grant execute on function api.{f}() to anon, authenticated;",
    "revoke all on function {f}() from public, anon, authenticated;",
    "revoke all on function public.{f}() from public, anon, authenticated;",
    "revoke grant option for execute on function {f}() from anon;",
    "grant execute on function api.{f}(), api.other_fn() to anon;",
    "grant execute on function {f}_v2() to anon;",          # 이름이 앞부분만 같은 다른 함수
    # 앞 문장의 grant 가 뒤 문장의 함수 이름과 이어 붙어 걸리면 안 된다.
    "grant execute on function api.{f}() to anon;\nrevoke all on function {f}() from anon;",
])
def test_public_fn_grants_in_leaves_the_api_twin_alone(good):
    assert public_fn_grants_in(good.format(f=FN), FN) == [], good


def test_allowlist_hits_sees_the_schema_qualified_form():
    fine = ("api." + FN, "public.v_floor_stack")
    # 나쁜 예 — 맨 이름(흔한 꼴)과 스키마가 붙은 이름(놓치던 꼴).
    for bad in (TABLE, "public." + TABLE, "api." + TABLE):
        assert allowlist_hits(TABLE, [fine + (bad,)]) == [bad], bad
    # 좋은 예 — 이름이 겹치기만 하는 것은 안 걸린다.
    assert allowlist_hits(TABLE, [fine, ("public.%s_archive" % TABLE,)]) == []
    # 전제 — 실제 목록이 정말 `스키마.이름` 꼴이고, 이 함수가 그 꼴에서 이름을 찾아낸다.
    assert allowlist_hits(FN) == ["api." + FN]
