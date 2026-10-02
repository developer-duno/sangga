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
# 반환 표에 stale_cnt 한 칸을 더한 판(사장님 결재 2026-09-05). 함수만 다시 만드는
# 파일이라 **표 시험(RLS·PK·표 권한)은 여기 안 온다** — 그 파일에는 표가 없다.
MIGRATION_STALE = os.path.join(
    ROOT, "supabase", "migrations", "2026-09-05b_permit_stale_cnt.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
# include 에 허가일을 더한 판(2026-09-27e).
MIGRATION_PMS_DAY = os.path.join(
    ROOT, "supabase", "migrations", "2026-09-27e_arch_permit_pnu_pms_day.sql")
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


# ── "없어야 한다" 탐지기 (가드 본체와 양성 대조가 **같은 함수**를 지난다) ─────
#
# ⛔ 글자 통째 비교·줄머리 고정으로 "없음"을 단언하면, 조금만 다르게 적은 위반이
#    전부 초록으로 빠져나간다(2026-10-02 감사 실측 — 들여쓴 `create policy`,
#    받는 역할 순서를 바꾼 grant, `grant all`, `"public.arch_permit"`).
#    그래서 탐지를 함수로 빼고, 그 함수가 **실제로 잡는지**를 아래
#    TestDetectorsActuallyCatch 가 나쁜 예로 확인한다.


def policy_statements(sql):
    """주석을 걷은 문장에서 `create policy` 를 전부 찾는다.

    줄머리든 들여썼든, 같은 줄의 `;` 뒤에 붙었든 잡는다(대소문자 무시).
    ⚠️ 못 보는 것(2026-10-02 검사관 실측): 한 줄에 적은
       `do $$ begin create policy … end $$;` · `then create policy` · 블록 주석(`/* */`)
       뒤에 붙은 것 · 동적 SQL(`execute '…'`).
    """
    return re.findall(r"(?im)(?:^|;)\s*(create\s+policy\b[^;\n]*)", statements(sql))


def grant_targets(sql, name=FN):
    """`grant … on function … <name>(` 의 **대상 이름**을 전부 돌려준다(소문자).

    권한 종류(execute·all)·받는 역할과 그 순서·들여쓰기·줄바꿈·대소문자와
    무관하게 본다. 돌려주는 값은 적힌 그대로의 이름이다 —
    `api.<name>` · `public.<name>` · 스키마 없는 `<name>`.
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


def public_grants(sql, name=FN):
    """api 통과 함수가 아닌 대상(= public 원본)에 준 grant 만 고른다."""
    return [t for t in grant_targets(sql, name) if t != "api." + name]


def allowlisted(name, entries):
    """허용 목록에서 **스키마를 벗긴 이름**이 `name` 과 같은 원소를 돌려준다.

    ⛔ 목록 원소는 2026-09-01 부터 `"public.x"`·`"api.x"` 꼴이다 — 맨 이름으로
       `name in 목록` 을 물으면 표를 목록에 넣어도 영원히 False 다(죽은 단언).
    """
    return [e for e in entries if e.rsplit(".", 1)[-1] == name]


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
        # 들여쓴 꼴·같은 줄 `;` 뒤에 붙은 꼴까지(위 한 줄은 줄머리만 본다).
        assert policy_statements(block) == []

    @pytest.mark.parametrize("path", [MIGRATION, MIGRATION_STALE, SCHEMA])
    def test_only_the_api_wrapper_is_opened(self, path):
        text = statements(read(path))
        assert "grant execute on function api.{}(text) to anon, authenticated;".format(
            FN) in text
        # ⛔ public 쪽은 끝까지 닫아 둔다 — 통과 함수가 security definer 라 열 필요가 없다.
        assert "grant execute on function {}(text) to anon".format(FN) not in text
        assert "grant execute on function public.{}(text) to anon".format(FN) not in text
        # 위 두 줄은 글자 통째 비교라 `to authenticated, anon`·`grant all` 을 놓친다 —
        # 받는 역할·권한 종류와 무관하게 public 원본을 향한 grant 가 0개인지 본다.
        assert public_grants(read(path)) == []

    @pytest.mark.parametrize("path", [MIGRATION, MIGRATION_STALE, SCHEMA])
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
        # ⛔ 위 두 줄은 **죽은 단언**이었다(2026-10-02 감사) — 목록 원소가
        #    `"public.arch_permit"` 꼴이라 맨 이름으로 물으면 표를 넣어도 초록이다.
        #    스키마를 벗긴 이름으로 묻는다.
        assert TABLE not in post_load.ANON_READABLE_NAMES
        assert TABLE not in post_load.ANON_CALLABLE_NAMES
        assert allowlisted(TABLE, post_load.ANON_READABLE_ALLOWLIST) == []
        assert allowlisted(TABLE, post_load.ANON_CALLABLE_ALLOWLIST) == []

    @pytest.mark.parametrize("path", [MIGRATION, MIGRATION_STALE, SCHEMA])
    def test_only_counts_leave_the_building(self, path):
        """⛔ 나가는 것은 개수와 기준월뿐이다 — 주소·건물 이름 칸이 반환값에 끼면 안 된다.

        표에는 `plat_plc`(지번 주소)가 들어 있어서, 반환 목록에 슬쩍 얹기가 쉽다.
        """
        body = fn_body(read(path))
        head = body[:body.index("language")]
        assert "total_cnt" in head and "started_cnt" in head and "base_ym" in head
        for leak in ("plat_plc", "mgm_pmsrgst_pk", "main_purps_nm", "tot_area"):
            assert leak not in head, leak


class TestDetectorsActuallyCatch:
    """양성 대조 — 위 가드가 쓰는 탐지기에 **나쁜 예를 넣으면 걸리는지** 본다.

    "없음"만 단언하는 시험은 탐지기가 죽어도 초록이다(2026-10-02 감사에서 죽은
    단언 2곳·반쪽 27곳). 가드 본체와 **같은 함수**를 지나게 해야 대조가 된다.
    """

    @pytest.mark.parametrize("bad", [
        "create policy p_x on arch_permit for select using (true);",
        "  create policy p_x on arch_permit for select using (true);",   # 들여쓴 꼴
        "\tCREATE  POLICY p_x on arch_permit for select using (true);",
        "alter table arch_permit enable row level security; create policy p_x on arch_permit using (true);",
    ])
    def test_policy_detector_catches(self, bad):
        assert policy_statements("select 1;\n" + bad + "\n") != []

    @pytest.mark.parametrize("good", [
        "-- create policy 는 만들지 않는다 (정책 0개 = 전부 거부)",
        "  -- create policy p_x on arch_permit using (true);",
        "alter table arch_permit enable row level security;",
        "drop policy if exists p_x on arch_permit;",
    ])
    def test_policy_detector_leaves_the_rest_alone(self, good):
        assert policy_statements("select 1;\n" + good + "\n") == []

    @pytest.mark.parametrize("bad", [
        "grant execute on function count_nearby_permits(text) to anon;",
        "grant execute on function public.count_nearby_permits(text) to anon;",
        # ↓ 감사가 "초록(못 잡음)"이라 적은 변형 꼴들
        "grant execute on function public.count_nearby_permits(text) to authenticated, anon;",
        "grant all on function count_nearby_permits(text) to anon;",
        "  grant execute on function count_nearby_permits(text) to anon;",
        "GRANT EXECUTE\n  ON FUNCTION public.count_nearby_permits (text)\n  TO anon;",
        "grant execute on function api.count_nearby_permits(text), count_nearby_permits(text) to anon;",
    ])
    def test_public_grant_detector_catches(self, bad):
        assert public_grants(bad) != []

    @pytest.mark.parametrize("good", [
        "grant execute on function api.count_nearby_permits(text) to anon, authenticated;",
        "revoke all on function count_nearby_permits(text) from public, anon, authenticated;",
        "revoke grant option for execute on function count_nearby_permits(text) from anon;",
        "-- grant execute on function count_nearby_permits(text) to anon;",
        "grant execute on function api.count_nearby_permits_v2(text) to anon;",
        "grant execute on function other_fn(text) to anon;",
    ])
    def test_public_grant_detector_leaves_the_rest_alone(self, good):
        assert public_grants(good) == []

    def test_grant_targets_reports_the_api_wrapper(self):
        """대상 이름을 적힌 그대로 돌려준다 — api 쪽이 안 잡히면 위 판정이 헛돈다."""
        sql = ("revoke all on function api.count_nearby_permits(text) from public;\n"
               "grant execute on function api.count_nearby_permits(text) to anon, authenticated;\n")
        assert grant_targets(sql) == ["api.count_nearby_permits"]

    @pytest.mark.parametrize("entries", [
        ("public.arch_permit",),
        ("api.arch_permit",),
        ("arch_permit",),
        ("api.count_nearby_permits", "public.arch_permit"),
    ])
    def test_allowlist_detector_sees_through_the_schema_prefix(self, entries):
        assert allowlisted(TABLE, entries) != []

    @pytest.mark.parametrize("entries", [
        (),
        ("api.count_nearby_permits",),
        ("public.arch_permit_archive",),
        ("public.v_floor_stack", "api.v_floor_stack"),
    ])
    def test_allowlist_detector_leaves_the_rest_alone(self, entries):
        assert allowlisted(TABLE, entries) == []

    def test_post_load_bare_names_strip_the_schema(self):
        """가드가 기대는 `*_NAMES` 가 실제로 스키마를 벗기는지 — 안 벗기면 가드가 다시 죽는다."""
        import post_load

        assert post_load._bare_names(("public.arch_permit", "api.arch_permit")) == (TABLE,)


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

    @pytest.mark.parametrize("path", [MIGRATION, MIGRATION_STALE, SCHEMA])
    def test_the_reader_pins_one_month(self, path):
        """달이 쌓이는 표라, 기준월을 고정하지 않으면 같은 건물을 여러 번 센다."""
        body = fn_body(read(path))
        assert "max(a.loaded_ym) into v_ym" in body
        assert "a.loaded_ym = v_ym" in body

    @pytest.mark.parametrize("path", [MIGRATION, MIGRATION_STALE, SCHEMA])
    def test_no_data_means_no_row_not_zero(self, path):
        """한 번도 안 담았는데 '0곳'이라고 하면 거짓말이다."""
        body = fn_body(read(path))
        assert "if v_ym is null then" in body


# ── 3. 무엇을 세는가 ──────────────────────────────────────────────────────────


class TestWhatItCounts:
    @pytest.mark.parametrize("path", [MIGRATION, MIGRATION_STALE, SCHEMA])
    def test_only_unfinished_buildings(self, path):
        """표에는 미준공만 담기지만 규칙을 한 군데에만 두지 않는다 — 표가 넓어져도
        이 화면은 계속 '곧 올라올 것'만 말해야 한다."""
        assert "a.use_apr_day is null" in fn_body(read(path))

    @pytest.mark.parametrize("path", [MIGRATION, MIGRATION_STALE, SCHEMA])
    def test_the_commercial_set_is_exactly_the_four(self, path):
        """⛔ 여기를 넓히면 화면 숫자가 조용히 부푼다. 실측 근거는 마이그레이션 머리말에 있다."""
        body = fn_body(read(path))
        m = re.search(r"left\(a\.main_purps_cd,\s*2\)\s*=\s*any\(array\[([^\]]+)\]\)", body)
        assert m, "상가 용도 집합을 못 찾았습니다"
        got = tuple(re.findall(r"'(\d{2})'", m.group(1)))
        assert got == COMMERCIAL

    @pytest.mark.parametrize("path", [MIGRATION, MIGRATION_STALE, SCHEMA])
    def test_blank_purpose_is_not_counted(self, path):
        """주용도가 빈 값인 허가가 70%(389,822행)다. `left(NULL,2)` 는 NULL 이라 any() 에
        안 걸린다 — coalesce 로 빈 문자열을 만들어 넣으면 그 순간 다 딸려 온다."""
        body = fn_body(read(path))
        assert "coalesce(a.main_purps_cd" not in body

    @pytest.mark.parametrize("path", [MIGRATION, MIGRATION_STALE, SCHEMA])
    def test_counts_started_ones_separately(self, path):
        body = fn_body(read(path))
        assert "real_stcns_day is not null" in body

    @pytest.mark.parametrize("path", [MIGRATION_STALE, SCHEMA])
    def test_counts_the_long_stalled_ones_too(self, path):
        """⛔ '그중 N동은 2년 넘게 착공하지 않았습니다' 한 줄의 재료다(결재 2026-09-05).

        세는 자가 둘 다 있어야 뜻이 선다 — **착공 기록이 없고**(`real_stcns_day is null`)
        **허가일이 기준월 말일보다 2년 넘게 전**인 것. 하나라도 빠지면 다른 수가 된다:
          · 착공 조건이 빠지면 이미 짓고 있는 오래된 허가까지 세어 부풀고,
          · 날짜 조건이 빠지면 그냥 '허가만 받은 것'과 같은 수가 된다.
        ⛔ 그리고 재는 시점은 **기준월 말일**(v_month_end)이지 오늘이 아니다 — 이 표는 그
           달의 상태를 찍은 것이라, 오늘로 재면 자료가 보지 못한 시간까지 섞어 센다.
        """
        body = fn_body(read(path))
        assert re.search(
            r"count\(\*\)\s+from\s+hit\s+"
            r"where\s+hit\.real_stcns_day\s+is\s+null\s+"
            r"and\s+hit\.arch_pms_day\s*<\s*\(v_month_end\s*-\s*interval\s*'2 years'\)",
            body,
        ), "stale_cnt 를 세는 조건을 못 찾았습니다"
        # 오늘로 재면 안 된다 — 자료가 말하는 시점으로만 잰다.
        assert "current_date" not in body and "now()" not in body

    @pytest.mark.parametrize("path", [MIGRATION_STALE, SCHEMA])
    def test_the_returned_columns_are_exactly_the_four(self, path):
        """반환 표가 늘거나 순서가 바뀌면 화면이 다른 칸을 읽는다 — 에러 없이 조용히 틀린다."""
        head = fn_body(read(path))
        head = head[:head.index("language")]
        got = re.findall(r"(?m)^\s+(\w+)\s+(?:int|text)\s*,?\s*$", head)
        assert got == ["total_cnt", "started_cnt", "stale_cnt", "base_ym"], got


# ── 4. 반경은 형제 함수와 같은 자 ─────────────────────────────────────────────


class TestRadius:
    @pytest.mark.parametrize("path", [MIGRATION, MIGRATION_STALE, SCHEMA])
    def test_measures_five_hundred_meters_the_same_way(self, path):
        """한 화면에서 '500m 안'이 두 가지를 뜻하면 사람이 읽을 수 없다.

        tests/test_radius_sync.py 의 인구조사가 이 리터럴도 함께 지킨다.
        """
        body = fn_body(read(path))
        assert "st_dwithin(p.geom::geography, me.gg, 500, false)" in body

    @pytest.mark.parametrize("path", [MIGRATION, MIGRATION_STALE, SCHEMA])
    def test_neighbours_go_through_a_char19_array(self, path):
        """⛔ text[] 로 두면 배열 조건이 인덱스 안으로 못 들어가 힙 필터로 밀린다."""
        body = fn_body(read(path))
        assert "'{}'::char(19)[]" in body
        assert "a.pnu = any(near.pnus)" in body

    @pytest.mark.parametrize("path", [MIGRATION, MIGRATION_STALE, SCHEMA])
    def test_the_pnu_parameter_is_cast_before_comparing(self, path):
        """⛔ text 파라미터를 char 컬럼에 그대로 대면 컬럼 쪽이 캐스트돼 인덱스가 죽는다
        (2026-08-16b 라이브 실측: 459.8ms ↔ 0.796ms)."""
        body = fn_body(read(path))
        assert "v_pnu char(19) := p_pnu;" in body
        assert "p.pnu = v_pnu" in body

    @pytest.mark.parametrize("path", [MIGRATION, MIGRATION_STALE, SCHEMA])
    def test_no_coordinates_means_no_row(self, path):
        """⛔ 0 을 돌려주면 '둘레에 아무것도 안 생긴다'는 단정이 된다 — 사실은 모르는 것이다."""
        body = fn_body(read(path))
        assert "where exists (select 1 from me)" in body
        assert "p.geom is not null" in body


# ── 5. 화면이 실제로 부를 수 있나 ─────────────────────────────────────────────


class TestReachableFromTheScreen:
    @pytest.mark.parametrize("path", [MIGRATION, MIGRATION_STALE, SCHEMA])
    def test_has_an_api_twin(self, path):
        """화면은 db.schema='api' 로 붙는다 — public 은 REST 노출에서 빠져 있다."""
        assert re.search(
            r"(?im)^create\s+or\s+replace\s+function\s+api\." + FN + r"\s*\(", read(path))

    @pytest.mark.parametrize("path", [MIGRATION, MIGRATION_STALE])
    def test_tells_postgrest_to_reload(self, path):
        """⛔ 빠뜨리면 DB 에는 있는데 화면만 404(PGRST202) 가 난다 — 찾기 어려운 고장이다.

        ⚠️ 칸을 더한 판(2026-09-05b)에서 더 아프다 — 캐시가 예전 칸 구성을 붙들고 있으면
           새 칸이 아니라 **함수 자체**를 못 찾는다.
        """
        assert "notify pgrst, 'reload schema';" in statements(read(path))


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

    def test_the_covering_index_has_the_permit_day_since_0927e(self, schema):
        """2026-09-27e — 읽는 함수가 꺼내는 arch_pms_day 가 include 에 있어야 Index Only Scan 이다.

        옛 판(08-28b)에는 없던 칸이라 위 '두 파일 다' 시험 대신 정본 + 27e 를 본다. 빠지면
        에러 없이 행마다 힙에 간다(2026-09-27 실측 Index Scan 58쪽).
        """
        e = read(MIGRATION_PMS_DAY)
        for text, head in ((schema, "create index if not exists idx_arch_permit_pnu on"),
                           (e, "create index concurrently if not exists idx_arch_permit_pnu_v2 on")):
            block = text[text.index(head):]
            include = block[:block.index(";")]
            for col in ("loaded_ym", "use_apr_day", "main_purps_cd", "real_stcns_day",
                        "arch_pms_day"):
                assert col in include, col

    def test_0927e_swaps_in_the_new_index_under_the_old_name(self):
        """만들기 → 옛 것 지우기 → 이름 되돌리기 순서, lock_timeout 은 이름 바꾸기 **앞**,
        concurrently 판이라 begin/commit 이 없다."""
        e = statements(read(MIGRATION_PMS_DAY)).lower()
        create = e.index("create index concurrently if not exists idx_arch_permit_pnu_v2 on")
        drop = e.index("drop index concurrently if exists idx_arch_permit_pnu;")
        lock = e.index("set lock_timeout")
        rename = e.index("alter index idx_arch_permit_pnu_v2 rename to idx_arch_permit_pnu;")
        assert e.index("set statement_timeout = '900s';") < create < drop < lock < rename
        assert not re.search(r"(?m)^\s*(begin|commit);", e)

    def test_0927e_gate_checks_the_new_index_before_dropping_the_old(self):
        """관문은 v2 를 만든 **뒤**·옛 색인을 지우기 **앞**. `if not exists` 는 끊겨서 invalid 로
        남은 v2 도 건너뛰므로, 관문 없이는 쓸 수 있는 pnu 색인이 0개인 채로 끝날 수 있다."""
        e = statements(read(MIGRATION_PMS_DAY)).lower()
        create = e.index("create index concurrently if not exists idx_arch_permit_pnu_v2 on")
        drop = e.index("drop index concurrently if exists idx_arch_permit_pnu;")
        gate_start = e.index("do $$")
        gate = e[gate_start:e.index("end $$;", gate_start)]
        assert create < gate_start < drop
        # 글자가 '있나'만 보면 `if exists`·`not i.indisvalid`·`or` 로 뒤집어도 초록이다(재검사관 변이
        # 2026-09-27) — 공백을 접은 조건 전체를 한 문장으로 대조한다.
        g = re.sub(r"\s+", " ", gate)
        assert ("if not exists ( select 1 from pg_index i join pg_class c on c.oid = i.indexrelid "
                "where c.relname = 'idx_arch_permit_pnu_v2' and i.indisvalid "
                "and pg_get_indexdef(i.indexrelid) like '%arch_pms_day%' ) then raise exception") in g

    def test_0927e_table_comment_is_identical_to_the_schema(self, schema):
        """27e 끝의 표 주석은 schema.sql 의 것과 글자 그대로 같아야 한다(줄바꿈 표기만 통일).
        한쪽만 고치면 라이브 주석과 정본이 조용히 갈린다."""
        pat = re.compile(r"(?ms)^comment on table arch_permit is\n.*?';$")
        e = pat.search(read(MIGRATION_PMS_DAY).replace("\r\n", "\n"))
        s = pat.search(schema.replace("\r\n", "\n"))
        assert e and s
        assert e.group(0).encode("utf-8") == s.group(0).encode("utf-8")
        e_all = statements(read(MIGRATION_PMS_DAY)).lower()
        assert e_all.index("comment on table arch_permit is") > e_all.index(
            "alter index idx_arch_permit_pnu_v2 rename to idx_arch_permit_pnu;")

    def test_the_pnu_column_is_char19_in_both(self, migration, schema):
        """char(19) 가 아니면 형제 함수들의 배열 조건이 인덱스를 못 탄다."""
        for text in (migration, schema):
            assert re.search(r"(?m)^\s+pnu\s+char\(19\)", table_block(text))
