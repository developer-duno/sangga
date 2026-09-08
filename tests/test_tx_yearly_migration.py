# -*- coding: utf-8 -*-
"""마이그레이션 2026-09-09a(동네 매매 단가 흐름 — 결정 0027)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙여 넣기 전에는 아무도 모르는 종류의 실수**다.
DB 없이 SQL 글자만 본다(CI 에는 DB 가 없다) — 대신 아래는 글자만으로 확실히 잡힌다.

  1) 나가는 칸이 늘어난다 → 이 함수의 계약은 **구×연도 요약 한 줄씩**이다. 개별 거래
     (필지·층·단가)를 붙이는 순간 실거래 원자료가 공개키로 새는 길이 된다.
  2) `grant` 가 `revoke` 보다 먼저 온다 → 대시보드가 함수를 다시 만들 때 붙는 anon
     기본권한을 못 걷는다.
  3) public 원본까지 연다 → api 통과 함수가 security definer 라 열 필요가 없는데,
     열면 옛 문(public 스키마)으로 가는 길이 하나 더 생긴다.
  4) `notify pgrst` 누락 → DB 에는 함수가 멀쩡히 있는데 화면만 404(PGRST202) 가 난다.
  5) 정본(schema.sql) 미동기 → 새 환경만 다르게 만들어진다.
  6) post_load 의 갱신 목록·허용 목록 누락 → 빠지면 화면만 옛 해를 계속 말하거나
     (에러 0), `post_load.py --check` 가 멀쩡한 함수를 **[사고]** 로 알린다.

ⓘ 도우미(read·statements·flat·fn_block)는 형제 파일에서 **복사**해 왔다 — import 하지
  않는다. 시험 파일끼리 얽히면 한쪽의 고장이 다른 쪽을 조용히 가린다.
"""

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

MIGRATION = os.path.join(
    ROOT, "supabase", "migrations", "2026-09-09a_tx_yearly.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

BOTH = [MIGRATION, SCHEMA]

MV = "mv_sigungu_tx_yearly"
FN = "get_sigungu_tx_yearly"

# 나가도 되는 칸 — **이것이 전부다**. 그 해의 요약과, 그 요약이 얼마나 온전한지까지.
RETURNED_COLUMNS = (
    "yr",
    "n",
    "n_all",
    "median_unit_price",
    "p25_unit_price",
    "p75_unit_price",
    "floor_missing",
    "ym_cnt",
    "first_ym",
    "last_ym",
    "sigungu_nm",
)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def statements(sql):
    """주석을 걷어낸 **실제 SQL 문장만** (줄바꿈은 그대로 — `(?m)^…` 정규식용).

    설명 주석에 적어 둔 말이 문장으로 오해되면 코드가 망가져도 초록이 된다
    (test_price_gate_migration·test_api_schema_migration 이 같은 이유로 같은 방식을 쓴다).
    """
    return "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )


def flat(sql):
    """주석을 걷고 **공백을 한 칸으로** 접은 것 — 권한 문장 단언은 전부 이것을 본다.

    ⛔ 왜 접나: 정본은 권한 문장을 **칸 맞춰** 적는다(schema.sql 의 api 권한 묶음 —
       `grant execute on function api.get_sigungu_tx_stats(text)` 뒤에 빈칸이 여럿).
       원문 그대로 찾으면 그 정렬 때문에 "없다"고 판정해 **거짓 빨간불**이 나고,
       그러면 사람이 시험을 느슨하게 고치게 된다. 접는 것은 약화가 아니다 —
       문장의 낱말·순서는 그대로 보고 칸 수만 무시한다.
    ⓘ tests/test_display_name_sql_sync.py 의 _statement_text() 와 같은 뜻이다.
    """
    return re.sub(r"\s+", " ", statements(sql))


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


def returns_columns(block):
    """`returns table ( … )` 안의 칸 이름을 **적힌 순서대로**."""
    start = block.index("returns table")
    head = block[start:block.index(")", start)]
    return tuple(m.group(1) for m in re.finditer(r"(?m)^\s+(\w+)\s+\w", head))


# ── 1. 요약표는 집합 거래만, 해마다 ──────────────────────────────────────────


class TestTheViewExists:
    @pytest.mark.parametrize("path", BOTH)
    def test_view_and_unique_index(self, path):
        """⛔ unique 인덱스가 없으면 `refresh … concurrently` 가 에러로 멈춘다 —
        적재 마무리(post_load.py)가 통째로 서 버린다."""
        text = statements(read(path))
        assert re.search(
            r"(?im)^create materialized view if not exists %s as" % MV, text)
        assert re.search(
            r"(?im)^create unique index if not exists \w+ on %s \(sigungu_code, yr\);" % MV,
            text,
        )

    @pytest.mark.parametrize("path", BOTH)
    def test_only_jiphap_and_grouped_by_year(self, path):
        """⛔ 통건물(일반)을 섞으면 분포가 오염된다(건물 한 채 값이라 ㎡당 단가의 성격이
        다르다 — mv_sigungu_tx_stats 와 같은 이유). 묶는 자는 **연도**뿐이다."""
        body = statements(read(path))
        assert "where t.tx_type = '집합'" in body
        assert "group by t.sigungu_code, substr(t.contract_ym, 1, 4)" in body

    @pytest.mark.parametrize("path", BOTH)
    def test_n_counts_only_rows_that_have_a_unit_price(self, path):
        """⛔ **n 은 절대 규칙 3 의 '표본 5건' 을 재는 유일한 자다.**

        n 을 `count(*)` 로 바꾸면 단가가 빠진 행까지 세어, 근거가 3건뿐인 가운데값을
        화면이 "8건 기준"이라 말하게 된다 — 숫자는 그럴듯하고 에러는 안 난다.
        적대검증에서 실제로 `count(*)::int as n` 돌연변이가 시험 32개를 전부 통과했다.
        n_all(그 해 집합 거래 전부 = 층 미상 비율의 분모)과 짝으로 못 박는다.
        """
        text = flat(read(path))
        assert "count(*) filter (where t.unit_price is not null)::int as n," in text
        assert "count(*)::int as n_all," in text

    @pytest.mark.parametrize("path", BOTH)
    def test_the_view_is_never_opened_to_anon(self, path):
        """⛔ 표가 열리면 화면이 함수로만 읽는다는 계약이 통째로 우회된다."""
        text = flat(read(path))
        assert "grant select on {}".format(MV) not in text
        assert "grant all on {}".format(MV) not in text

    @pytest.mark.parametrize("path", BOTH)
    def test_the_view_is_explicitly_revoked(self, path):
        """⛔ **안 여는 것만으로는 부족하다 — 명시로 닫아야 한다.**

        Supabase 는 새 표·물질화뷰를 anon 에게 자동으로 열어 왔고(pg_default_acl),
        정본에서는 이 뷰가 아래쪽 기본권한 회수보다 **먼저** 만들어진다 — 그래서 새
        환경에서는 이 줄이 없으면 anon 이 그대로 읽는다. 형제 요약표는 전부 이 줄을
        마이그레이션과 정본 **양쪽에** 갖고 있다(mv_sigungu_tx_stats·mv_coverage_stats·
        mv_district_industry_mix).
        """
        assert (
            "revoke all on {} from public, anon, authenticated;".format(MV)
            in flat(read(path))
        )

    def test_the_exposure_check_does_not_allow_the_view(self):
        assert MV not in post_load.ANON_READABLE_ALLOWLIST
        assert MV not in post_load.ANON_CALLABLE_ALLOWLIST


# ── 2. 나가는 것은 구×연도 요약뿐 ────────────────────────────────────────────


class TestReturnedColumnsAreFixed:
    @pytest.mark.parametrize("path", BOTH)
    @pytest.mark.parametrize("schema", ["", "api."])
    def test_exactly_these_columns(self, path, schema):
        """⛔ **칸이 늘면 여기서 먼저 운다.**

        개별 거래를 붙이는 것은 별건 판단이라, 조용히 늘어나는 것을 막는다
        (returns table 안의 칸 이름을 순서까지 통째로 대조한다).
        """
        assert returns_columns(
            fn_block(statements(read(path)), schema=schema)) == RETURNED_COLUMNS

    @pytest.mark.parametrize("path", BOTH)
    def test_it_only_reads(self, path):
        """⛔ 이 길에 쓰기가 붙는 날, 읽기 전용이라는 전제가 사라진다."""
        body = statements(fn_block(read(path))).lower()
        for banned in ("insert", "update ", "delete", "truncate"):
            assert banned not in body, banned

    @pytest.mark.parametrize("path", BOTH)
    def test_it_reads_the_summary_not_the_raw_table(self, path):
        """⛔ 함수가 `transaction` 을 직접 읽으면 개별 거래가 나가는 길이 열린다 —
        읽는 것은 언제나 요약표뿐이다."""
        body = statements(fn_block(read(path)))
        assert MV in body
        assert "from transaction" not in body


# ── 3. 새 함수는 닫힌 채로 태어난다 (2026-09-01b) ────────────────────────────


class TestClosedByDefault:
    @pytest.mark.parametrize("path", BOTH)
    def test_public_is_revoked_and_never_granted(self, path):
        """⛔ 통과 함수가 security definer 라 public 원본을 열 필요가 없다."""
        text = flat(read(path))
        assert (
            "revoke all on function %s(text) from public, anon, authenticated;" % FN
            in text
        )
        assert not re.search(
            r"grant execute on function (public\.)?%s\(text\)" % FN, text)

    @pytest.mark.parametrize("path", BOTH)
    def test_api_twin_is_granted_after_revoke(self, path):
        """⛔ 순서가 뒤집히면 대시보드가 붙인 anon 기본권한을 못 걷는다."""
        text = flat(read(path))
        rv = text.index(
            "revoke all on function api.%s(text) from public, anon, authenticated;" % FN)
        gr = text.index(
            "grant execute on function api.%s(text) to anon, authenticated;" % FN)
        assert rv < gr

    @pytest.mark.parametrize("path", BOTH)
    def test_the_api_twin_is_security_definer_with_an_empty_search_path(self, path):
        block = fn_block(read(path), schema="api.")
        assert "security definer" in block
        assert "set search_path = ''" in block

    def test_it_is_in_the_exposure_allowlist(self):
        """허용 목록에 없으면 `--check` 가 멀쩡한 함수를 **[사고]** 로 알린다."""
        assert "api.{}".format(FN) in post_load.ANON_CALLABLE_ALLOWLIST
        assert FN in post_load.ANON_CALLABLE_NAMES

    def test_the_migration_reloads_postgrest(self):
        """⛔ 빠뜨리면 DB 에는 있는데 화면만 404(PGRST202) 가 난다 — 찾기 어려운 고장이다."""
        assert "notify pgrst, 'reload schema';" in statements(read(MIGRATION))


# ── 4. 코멘트가 규칙을 싣고 다닌다 ───────────────────────────────────────────


class TestTheCommentCarriesTheRule:
    @pytest.mark.parametrize("path", BOTH)
    def test_says_where_the_rule_comes_from(self, path):
        """함수 코멘트는 **라이브 DB 안에 남는 유일한 설명**이다 — 규칙을 여기 싣는다."""
        text = read(path)
        i = text.index("comment on function {}(text) is".format(FN))
        cmt = text[i:text.index(";", i)]
        assert "0027" in cmt, "어느 결정에서 온 규칙인지 적어야 합니다"
        assert "security definer" in cmt


# ── 5. 정본 동기 ─────────────────────────────────────────────────────────────


class TestSchemaMirrorsTheMigration:
    @pytest.mark.parametrize("schema", ["", "api."])
    def test_bodies_letter_for_letter(self, schema):
        """⛔ 정본만 살짝 다듬는 것이 곧 정본↔라이브 불일치다(2026-09-01 2차 적대검증).

        ⓘ 전 함수를 훑는 형제 가드가 따로 있다(tests/test_schema_function_drift.py).
          여기서는 이 함수 하나를 못 박아 두어, 실패 메시지가 무엇 때문인지 바로 보이게 한다.
        """
        assert fn_block(read(MIGRATION), schema=schema) == fn_block(
            read(SCHEMA), schema=schema)


# ── 6. post_load 가 알고 있는가 ──────────────────────────────────────────────


class TestPostLoadKnowsIt:
    def test_refresh_list(self):
        """⛔ 갱신 목록에서 빠지면 새 거래를 넣어도 화면만 **옛 해에 굳은 채** 남는다
        (에러는 안 난다 — 그래서 아무도 모른다)."""
        assert MV in post_load.REFRESH_MVS

    def test_refresh_sql_actually_names_it(self):
        assert "refresh materialized view concurrently {};".format(MV) in (
            post_load.build_refresh_sql()
        )

    def test_allowlist(self):
        assert "api." + FN in post_load.ANON_CALLABLE_ALLOWLIST


# ── 7. 가드 자신의 시험 ──────────────────────────────────────────────────────


def test_statements_really_strips_comments():
    """⛔ **주석 제거기가 헛돌면 위 시험들이 조용히 가짜 초록이 된다** — 가드가 없는
    것보다 나쁘다(막고 있다는 거짓 안심). grant 줄을 주석 처리한 사본에서 판정이
    뒤집히는지 확인한다."""
    text = read(MIGRATION)
    line = "grant execute on function api.%s(text) to anon, authenticated;" % FN
    mutated = text.replace(line, "-- " + line)
    assert line in flat(text), "전제: 원문에는 그 문장이 살아 있다"
    assert line not in flat(mutated), (
        "주석으로 죽인 grant 가 여전히 '있다'고 읽힙니다 — 주석 제거가 헛돕니다"
    )


def test_returns_columns_helper_actually_reads_the_list():
    """⛔ 칸 대조가 **빈 튜플끼리 비교하며** 초록이 되는 일을 막는다."""
    sample = (
        "create or replace function f(x text)\n"
        "returns table (\n"
        "  a  text,\n"
        "  b  int\n"
        ")\n"
    )
    assert returns_columns(sample) == ("a", "b")
