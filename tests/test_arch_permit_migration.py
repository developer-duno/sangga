# -*- coding: utf-8 -*-
"""마이그레이션 2026-08-28b(건축인허가 — 곧 올라오는 건물)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙여 넣기 전에는 아무도 모르는 종류의 실수**다.
DB 없이 SQL 글자만 본다(CI 에는 DB 가 없다) — 대신 아래는 글자만으로 확실히 잡힌다.

  1) 표가 밖에 열린다 → 전국 55만 건의 허가 주소·건물 규모가 통째로 긁힌다. 이 화면이
     내보내기로 한 것은 **개수와 기준월뿐**이다.
  2) PK 가 한 칸이 된다 → 같은 허가건이 달마다 다시 나오므로 **다음 달 적재가 PK 충돌로
     통째로 실패**한다. 그날이 오기 전에는 아무 신호가 없다.
  3) PK 를 bigint 로 바꾼다 → 22자리 값이 넘쳐 조용히 다른 건물이 된다.
  4) 기준월 고정이 빠진다 → 달이 쌓이면 같은 건물을 여러 번 세어 곳수가 부풀어 오른다.
  5) 좌표 없는 필지에 0 을 돌려준다 → "둘레에 아무것도 안 생긴다"는 **단정**이 새어 나간다.
  6) `notify pgrst` 누락 → DB 에는 함수가 멀쩡히 있는데 화면만 404(PGRST202) 가 난다.
  7) 정본(schema.sql) 미동기 → 새 환경만 다르게 만들어진다.
"""

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-08-28b_arch_permit.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

TABLE = "arch_permit"
FN = "count_nearby_permits"

# 상가로 세는 주용도 대분류 — 03 1종근생 · 04 2종근생 · 07 판매 · 14 업무.
COMMERCIAL = ("03", "04", "07", "14")


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
    """`create or replace function <name>(...)` 부터 `$$;` 까지 (주석 제거 전 원문)."""
    m = re.search(
        r"(?im)^create\s+or\s+replace\s+function\s+(?:public\.)?" + name + r"\s*\(", sql)
    assert m, "{} 정의를 못 찾았습니다".format(name)
    end = sql.index("$$;", m.start())
    return sql[m.start():end]


def table_block(sql):
    """`create table ... (` 부터 닫는 `);` 까지."""
    start = sql.index("create table if not exists {} (".format(TABLE))
    return sql[start:sql.index(");", start)]


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
        block = read(path)
        if path == SCHEMA:
            block = block[block.index("create table if not exists {} (".format(TABLE)):]
        assert not re.search(r"(?im)^create\s+policy", statements(block))

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_only_the_api_wrapper_is_opened(self, path):
        text = statements(read(path))
        assert "grant execute on function api.{}(text) to anon, authenticated;".format(
            FN) in text
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

    def test_the_exposure_check_knows_about_it(self):
        """post_load --check 의 허용 목록에 없으면 '뚫렸다'고 잘못 알린다."""
        import post_load

        # ⚠️ 2026-09-01 감사부터 ANON_CALLABLE_ALLOWLIST 는 `api.count_nearby_permits`
        #    처럼 스키마가 붙는다(잔존 노출을 이름만으로 가려 버리던 구멍을 막은 것) —
        #    맨 이름으로 물을 땐 post_load 가 같은 목록에서 파생해 둔 *_NAMES 를 쓴다.
        assert FN in post_load.ANON_CALLABLE_NAMES
        # 표는 **열려 있으면 안 되므로** 허용 목록에 없어야 한다.
        assert TABLE not in post_load.ANON_READABLE_ALLOWLIST
        assert TABLE not in post_load.ANON_CALLABLE_ALLOWLIST

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_only_counts_leave_the_building(self, path):
        """⛔ 나가는 것은 개수와 기준월뿐이다 — 주소·건물 이름 칸이 반환값에 끼면 안 된다.

        표에는 `plat_plc`(지번 주소)가 들어 있어서, 반환 목록에 슬쩍 얹기가 쉽다.
        """
        body = fn_body(read(path))
        head = body[:body.index("language")]
        assert "total_cnt" in head and "started_cnt" in head and "base_ym" in head
        for leak in ("plat_plc", "mgm_pmsrgst_pk", "main_purps_nm", "tot_area"):
            assert leak not in head, leak


# ── 2. 다음 달에 터지지 않는가 ────────────────────────────────────────────────


class TestMonthlyReload:
    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_primary_key_has_two_columns(self, path):
        """⛔ 한 칸짜리 PK 로 두면 다음 달 적재가 PK 충돌로 통째로 실패한다 —
        같은 허가건이 달마다 다시 나오기 때문이다."""
        block = table_block(read(path))
        assert "primary key (mgm_pmsrgst_pk, loaded_ym)" in block
        # 컬럼 선언에 붙은 한 칸짜리 PK 도 없어야 한다.
        assert not re.search(r"(?m)^\s+mgm_pmsrgst_pk\s+\w+.*primary key", block)

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_the_key_column_is_text_not_bigint(self, path):
        """⛔ 22자리 값이 있어 bigint 를 넘친다(원본도 VARCHAR(33)). 넘치면 조용히 다른 건물이 된다."""
        block = table_block(read(path))
        assert re.search(r"(?m)^\s+mgm_pmsrgst_pk\s+text\b", block)

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_the_reader_pins_one_month(self, path):
        """달이 쌓이는 표라, 기준월을 고정하지 않으면 같은 건물을 여러 번 센다."""
        body = fn_body(read(path))
        assert "max(a.loaded_ym) into v_ym" in body
        assert "a.loaded_ym = v_ym" in body

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_no_data_means_no_row_not_zero(self, path):
        """한 번도 안 담았는데 '0곳'이라고 하면 거짓말이다."""
        body = fn_body(read(path))
        assert "if v_ym is null then" in body


# ── 3. 무엇을 세는가 ──────────────────────────────────────────────────────────


class TestWhatItCounts:
    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_only_unfinished_buildings(self, path):
        """표에는 미준공만 담기지만 규칙을 한 군데에만 두지 않는다 — 표가 넓어져도
        이 화면은 계속 '곧 올라올 것'만 말해야 한다."""
        assert "a.use_apr_day is null" in fn_body(read(path))

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_the_commercial_set_is_exactly_the_four(self, path):
        """⛔ 여기를 넓히면 화면 숫자가 조용히 부푼다. 실측 근거는 마이그레이션 머리말에 있다."""
        body = fn_body(read(path))
        m = re.search(r"left\(a\.main_purps_cd,\s*2\)\s*=\s*any\(array\[([^\]]+)\]\)", body)
        assert m, "상가 용도 집합을 못 찾았습니다"
        got = tuple(re.findall(r"'(\d{2})'", m.group(1)))
        assert got == COMMERCIAL

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_blank_purpose_is_not_counted(self, path):
        """주용도가 빈 값인 허가가 70%(389,822행)다. `left(NULL,2)` 는 NULL 이라 any() 에
        안 걸린다 — coalesce 로 빈 문자열을 만들어 넣으면 그 순간 다 딸려 온다."""
        body = fn_body(read(path))
        assert "coalesce(a.main_purps_cd" not in body

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_counts_started_ones_separately(self, path):
        body = fn_body(read(path))
        assert "real_stcns_day is not null" in body


# ── 4. 반경은 형제 함수와 같은 자 ─────────────────────────────────────────────


class TestRadius:
    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_measures_five_hundred_meters_the_same_way(self, path):
        """한 화면에서 '500m 안'이 두 가지를 뜻하면 사람이 읽을 수 없다.

        tests/test_radius_sync.py 의 인구조사가 이 리터럴도 함께 지킨다.
        """
        body = fn_body(read(path))
        assert "st_dwithin(p.geom::geography, me.gg, 500, false)" in body

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_neighbours_go_through_a_char19_array(self, path):
        """⛔ text[] 로 두면 배열 조건이 인덱스 안으로 못 들어가 힙 필터로 밀린다."""
        body = fn_body(read(path))
        assert "'{}'::char(19)[]" in body
        assert "a.pnu = any(near.pnus)" in body

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_the_pnu_parameter_is_cast_before_comparing(self, path):
        """⛔ text 파라미터를 char 컬럼에 그대로 대면 컬럼 쪽이 캐스트돼 인덱스가 죽는다
        (2026-08-16b 라이브 실측: 459.8ms ↔ 0.796ms)."""
        body = fn_body(read(path))
        assert "v_pnu char(19) := p_pnu;" in body
        assert "p.pnu = v_pnu" in body

    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_no_coordinates_means_no_row(self, path):
        """⛔ 0 을 돌려주면 '둘레에 아무것도 안 생긴다'는 단정이 된다 — 사실은 모르는 것이다."""
        body = fn_body(read(path))
        assert "where exists (select 1 from me)" in body
        assert "p.geom is not null" in body


# ── 5. 화면이 실제로 부를 수 있나 ─────────────────────────────────────────────


class TestReachableFromTheScreen:
    @pytest.mark.parametrize("path", [MIGRATION, SCHEMA])
    def test_has_an_api_twin(self, path):
        """화면은 db.schema='api' 로 붙는다 — public 은 REST 노출에서 빠져 있다."""
        assert re.search(
            r"(?im)^create\s+or\s+replace\s+function\s+api\." + FN + r"\s*\(", read(path))

    def test_tells_postgrest_to_reload(self, migration):
        """⛔ 빠뜨리면 DB 에는 있는데 화면만 404(PGRST202) 가 난다 — 찾기 어려운 고장이다."""
        assert "notify pgrst, 'reload schema';" in statements(migration)


# ── 6. 정본 동기 ──────────────────────────────────────────────────────────────


class TestSchemaMirrorsTheMigration:
    def test_table_is_in_the_canonical_file(self, schema):
        assert "create table if not exists {} (".format(TABLE) in schema

    @pytest.mark.parametrize("col", [
        "mgm_pmsrgst_pk", "loaded_ym", "pnu", "sigungu_cd", "plat_plc", "arch_gb_nm",
        "main_purps_cd", "main_purps_nm", "tot_area", "arch_pms_day", "real_stcns_day",
        "use_apr_day", "crtn_day",
    ])
    def test_every_column_is_in_both(self, migration, schema, col):
        for text in (migration, schema):
            assert re.search(r"(?m)^\s+{}\s".format(col), table_block(text)), col

    @pytest.mark.parametrize("idx", ["idx_arch_permit_pnu", "idx_arch_permit_ym"])
    def test_indexes_are_in_both(self, migration, schema, idx):
        for text in (migration, schema):
            assert "create index if not exists {} on".format(idx) in text

    @pytest.mark.parametrize("col", ["loaded_ym", "use_apr_day", "main_purps_cd",
                                     "real_stcns_day"])
    def test_the_covering_index_keeps_its_include_columns(self, migration, schema, col):
        """⛔ include 칸을 지워도 **에러는 안 나고 느려지기만 한다** — 가장 늦게 발견되는
        종류의 회귀라 글자로 지킨다(idx_ub_pnu_cat 과 같은 처방)."""
        for text in (migration, schema):
            block = text[text.index("create index if not exists idx_arch_permit_pnu"):]
            assert col in block[:block.index(";")]

    def test_the_pnu_column_is_char19_in_both(self, migration, schema):
        """char(19) 가 아니면 형제 함수들의 배열 조건이 인덱스를 못 탄다."""
        for text in (migration, schema):
            assert re.search(r"(?m)^\s+pnu\s+char\(19\)", table_block(text))
