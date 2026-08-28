# -*- coding: utf-8 -*-
"""마이그레이션 2026-08-28a(LH 상가 공고 알림판)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙여 넣기 전에는 아무도 모르는 종류의 실수**다.
DB 없이 SQL 글자만 본다(CI 에는 DB 가 없다) — 대신 아래는 글자만으로 확실히 잡힌다.

  1) 표가 밖에 열린다 → 함수가 마감 지난 공고를 빼 주는데 표가 열리면 그 규칙이 통째로
     우회돼, 이미 끝난 공고를 화면에 뿌리는 길이 생긴다.
  2) `delete` 가 끼어든다 → "마감된 공고도 남긴다"는 결재가 조용히 뒤집힌다. 지워진 뒤에는
     되돌릴 방법이 없다(그 이력은 다른 어떤 자료로도 못 만든다).
  3) 마감 거르기가 함수에서 빠진다 → 화면마다 제 나름대로 거르게 되고, 언젠가 한 화면이
     빠뜨려 사용자가 끝난 공고를 보고 헛걸음한다.
  4) `notify pgrst` 누락 → DB 에는 함수가 멀쩡히 있는데 화면만 404(PGRST202) 가 난다.
  5) 정본(schema.sql) 미동기 → 새 환경만 다르게 만들어진다.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-08-28a_lh_notice.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

TABLE = "lh_notice"
FN = "list_lh_notices"


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
    """주석을 걷어낸 **실제 문장만** 돌려준다.

    설명 주석에 적어 둔 말이 문장으로 오해되면, 코드가 망가져도 초록이 된다
    (test_schema_grant_signatures 가 같은 이유로 같은 방식을 쓴다).
    """
    return "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )


def fn_body(sql, name=FN):
    """`create or replace function <name>(...)` 부터 `$$;` 까지."""
    m = re.search(
        r"(?im)^create\s+or\s+replace\s+function\s+(?:public\.)?" + name + r"\s*\(",
        sql,
    )
    assert m, "{} 정의를 못 찾았습니다".format(name)
    end = sql.index("$$;", m.start())
    return sql[m.start():end]


# ── 1. 표는 밖에서 잠긴다 ─────────────────────────────────────────────────────


class TestTableIsClosed:
    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_revoked_from_the_public_roles(self, path):
        text = statements(read(path))
        assert "revoke all on {} from public, anon, authenticated;".format(TABLE) in text

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_row_level_security_is_on(self, path):
        assert "alter table {} enable row level security".format(TABLE) in read(path)

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_no_policy_is_created(self, path):
        """정책을 하나도 안 만드는 것이 곧 '전부 거부'다 — 이 레포의 다른 표와 같은 방식."""
        assert not re.search(r"(?im)^create\s+policy", statements(read(path)))

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_only_the_api_wrapper_is_opened(self, path):
        text = statements(read(path))
        assert "grant execute on function api.{}(text) to anon, authenticated;".format(FN) in text
        # ⛔ public 쪽은 끝까지 닫아 둔다 — 통과 함수가 security definer 라 열 필요가 없다.
        assert "grant execute on function {}(text) to anon".format(FN) not in text
        assert "grant execute on function public.{}(text) to anon".format(FN) not in text

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_revokes_before_granting(self, path):
        """create or replace 는 권한을 남기지만, 대시보드가 다시 만들면 anon 이 자동으로
        붙는다 — 만든 자리에서 다시 닫는다."""
        text = statements(read(path))
        assert text.index("revoke all on function api.{}(text)".format(FN)) < text.index(
            "grant execute on function api.{}(text)".format(FN))


# ── 2. 지우지 않는다 (결재된 설계) ────────────────────────────────────────────


class TestNeverDeletes:
    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_no_delete_or_truncate_anywhere(self, path):
        raw = read(path)
        # schema.sql 은 파일 전체가 아니라 **이 표를 다루는 구간만** 본다 — 남의 구간에
        # 있는 delete 로 헛경보를 내면 이 가드가 곧 무시된다.
        if path == SCHEMA:
            raw = raw[raw.index("create table if not exists lh_notice"):]
            # ⚠️ 끝을 `-- 완료` 로 잡으면 **그 뒤에 새 구간이 끼는 날** 남의 SQL 까지 훑는다
            #    (2026-08-28b arch_permit 이 실제로 그 사이에 들어왔다). 다음 큰 구분선까지만 본다.
            raw = raw[:raw.index("\n-- =====")]
        text = statements(raw).lower()
        assert "delete from lh_notice" not in text
        assert "truncate" not in text

    def test_the_collector_upserts_instead(self):
        import collect_lh_notices as lh

        assert "on conflict (pan_id) do update set" in lh.build_insert([{
            "pan_id": "A", "pan_nm": "B", "kind_cd": "23", "kind_nm": "분양 입찰",
            "kind_nm_src": "원문", "spl_inf_tp_cd": None, "cnp_nm": "경기도",
            "sido_code": "41", "is_nationwide": False, "pan_ss": "공고중",
            "notice_date": "2026-08-26", "close_date": "2026-12-31",
            "dtl_url": None, "collected_at": "2026-08-28T12:00:00+09:00",
        }])


# ── 3. 숨기는 규칙은 함수 한 곳에만 ───────────────────────────────────────────


class TestHidingRule:
    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_filters_out_closed_notices(self, path):
        body = fn_body(read(path))
        assert "close_date >= current_date" in body

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_keeps_the_ones_with_no_close_date(self, path):
        """⛔ 마감일을 **모르는** 것과 마감된 것은 다른 말이다 — 모른다고 숨기면 살아 있는
        공고가 조용히 사라진다."""
        body = fn_body(read(path))
        assert "close_date is null or" in body

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_nationwide_shows_up_everywhere(self, path):
        """실측 531건 중 59건이 '전국'이다 — 이 줄이 없으면 그것들이 어디에서도 안 보인다."""
        body = fn_body(read(path))
        assert "or n.is_nationwide" in body

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_sido_param_is_cast_before_comparing(self, path):
        """⛔ text 파라미터를 char 컬럼에 그대로 대면 컬럼 쪽이 캐스트돼 인덱스가 죽는다
        (2026-08-16b 라이브 실측: 459.8ms ↔ 0.796ms)."""
        body = fn_body(read(path))
        assert "v_sido char(2)" in body
        assert "n.sido_code = v_sido" in body

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_sorts_soonest_deadline_first(self, path):
        body = fn_body(read(path))
        assert "order by n.close_date asc nulls last" in body


# ── 4. 화면이 실제로 부를 수 있나 ─────────────────────────────────────────────


class TestReachableFromTheScreen:
    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_has_an_api_twin(self, path):
        """화면은 db.schema='api' 로 붙는다 — public 은 REST 노출에서 빠져 있다."""
        assert re.search(
            r"(?im)^create\s+or\s+replace\s+function\s+api\." + FN + r"\s*\(", read(path))

    def test_tells_postgrest_to_reload(self, migration):
        """⛔ 빠뜨리면 DB 에는 있는데 화면만 404(PGRST202) 가 난다 — 찾기 어려운 고장이다."""
        assert "notify pgrst, 'reload schema';" in statements(migration)

    def test_the_exposure_check_knows_about_it(self):
        """post_load --check 의 허용 목록에 없으면 '뚫렸다'고 잘못 알린다."""
        import post_load

        assert FN in post_load.ANON_CALLABLE_ALLOWLIST
        # 표는 **열려 있으면 안 되므로** 허용 목록에 없어야 한다.
        assert TABLE not in post_load.ANON_READABLE_ALLOWLIST


# ── 5. 정본 동기 ──────────────────────────────────────────────────────────────


class TestSchemaMirrorsTheMigration:
    def test_table_is_in_the_canonical_file(self, schema):
        assert "create table if not exists {} (".format(TABLE) in schema

    @pytest.mark.parametrize("col", [
        "pan_id", "pan_nm", "kind_cd", "kind_nm", "kind_nm_src", "spl_inf_tp_cd",
        "cnp_nm", "sido_code", "is_nationwide", "pan_ss", "notice_date", "close_date",
        "dtl_url", "collected_at",
    ])
    def test_every_column_is_in_both(self, migration, schema, col):
        for text in (migration, schema):
            block = text[text.index("create table if not exists {} (".format(TABLE)):]
            block = block[:block.index(");")]
            assert re.search(r"(?m)^\s+{}\s".format(col), block), col

    @pytest.mark.parametrize("idx", ["idx_lh_notice_close", "idx_lh_notice_sido"])
    def test_indexes_are_in_both(self, migration, schema, idx):
        for text in (migration, schema):
            assert "create index if not exists {} on".format(idx) in text
