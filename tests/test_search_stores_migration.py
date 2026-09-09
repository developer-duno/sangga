# -*- coding: utf-8 -*-
"""마이그레이션 2026-09-09c(상호명으로 찾기 — 결정 0028)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙여 넣기 전에는 아무도 모르는 종류의 실수**다.
DB 없이 SQL 글자만 본다(CI 에는 DB 가 없다) — 대신 아래는 글자만으로 확실히 잡힌다.

  1) 나가는 칸이 늘어난다 → 이 함수의 계약은 **땅 한 줄 + 일치 상호 최대 3개**다.
     biz_no·업종 코드·점포 좌표를 붙이는 순간 점포 원자료가 공개키로 새는 길이 된다.
  2) `sigungu` 없이도 답한다 → 상호는 같은 이름이 전국에 널려 있어 구 없이는 답이
     될 수 없다(결정 0007). 조건 한 줄이 빠지면 **전국 검색이 조용히 열린다.**
  3) `grant` 가 `revoke` 보다 먼저 온다 → 대시보드가 함수를 다시 만들 때 붙는 anon
     기본권한을 못 걷는다.
  4) `notify pgrst` 누락 → DB 에는 함수가 멀쩡히 있는데 화면만 404(PGRST202) 가 난다.
  5) 정본(schema.sql) 미동기 → 새 환경만 다르게 만들어진다.
  6) **의존 사슬을 반쪽만 되세운다** → 이 마이그레이션은 요약표에 칸을 더하려고
     mv_search_parcel 을 떨어뜨리는데, 거기 기대어 사는 것이 넷이다
     (mv_open_sigungu → mv_coverage_stats → v_coverage_stats → api.v_coverage_stats).
     하나라도 안 되세우면 검색·지역 목록·각주가 통째로 사라지고, 뷰의 `grant` 를
     빠뜨리면 **경보 없이 각주만** 사라진다(`post_load.py --check` 는 "열려 있어야
     하는데 닫힌 것"을 못 잡는다 — 그 위험이 v_coverage_stats 코멘트의 ⛔ 그것이다).
  7) `drop index idx_ub_name` 이 덩어리 **안**으로 들어간다 → ACCESS EXCLUSIVE 락이
     커밋까지 유지돼, 요약표 굽는 내내 점포 표 읽기가 전부 줄을 선다(2026-08-22c).

ⓘ 도우미(read·statements·flat·fn_block)는 형제 test_tx_yearly_migration.py 에서
  **복사**해 왔다 — import 하지 않는다. 시험 파일끼리 얽히면 한쪽의 고장이 다른 쪽을
  조용히 가린다. (returns_columns 만은 새로 썼다 — 형제 것은 `char(19)` 처럼 괄호가
  든 타입에서 첫 칸만 읽고 멈춘다.)
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
    ROOT, "supabase", "migrations", "2026-09-09c_search_stores.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

BOTH = [MIGRATION, SCHEMA]

FN = "search_stores"
MV = "mv_search_parcel"
OLD_INDEX = "idx_ub_name"

# 나가도 되는 칸 — **이것이 전부다**. 땅 한 줄(대표 동·주소·층 요약)과, 그 땅에서
# 무엇이 몇 곳 걸렸는지, 그리고 전체 규모·너무 넓은지·언제 기준 자료인지.
RETURNED_COLUMNS = (
    "pnu",
    "bld_id",
    "bld_nm",
    "road_addr",
    "jibun_addr",
    "lat",
    "lng",
    "bld_cnt_in_pnu",
    "floor_cnt",
    "min_floor",
    "max_floor",
    "has_roof",
    # 화면에 적을 상호 최대 3개와, 그 땅에서 걸린 가게 수.
    "matched_names",
    "match_store_cnt",
    # 잘리기 전 전체 규모(모든 행에 같은 값) — '더 보기'와 "N곳" 문구가 이걸 읽는다.
    "total_parcel_cnt",
    "total_store_cnt",
    # 너무 넓은 검색어면 0건이 아니라 이 칸이 참인 **한 줄**로 답한다.
    "too_broad",
    # "2026년 6월 기준 점포 자료" 도장(서버 값 — 화면에 숫자 리터럴 0).
    "store_snapshot_ym",
)

# 요약표를 다시 만들 때 **함께 되살려야 할** 색인 — 옛 넷 + 새 하나.
# ⛔ 하나라도 빠지면 갱신이 멈추거나(유니크) 검색이 조용히 느려진다(trgm·구).
MV_INDEXES = (
    ("idx_msp_pnu", True),          # unique — refresh … concurrently 의 자격 요건
    ("idx_msp_road_key", False),
    ("idx_msp_jibun_key", False),
    ("idx_msp_sigungu", False),
    ("idx_msp_store_names", False),  # 2026-09-09c 신설
)

# mv_search_parcel 을 떨어뜨리면 함께 딸려 오는 것들(의존하는 쪽부터) — (종류, 이름).
# ⓘ 종류를 이름에서 유추하지 않는다 — "mv_coverage_stats" 도 "v_coverage_stats" 로 끝난다.
CHAIN = (
    ("view", "api.v_coverage_stats"),
    ("view", "v_coverage_stats"),
    ("materialized view", "mv_coverage_stats"),
    ("materialized view", "mv_open_sigungu"),
    ("materialized view", "mv_search_parcel"),
)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def norm(text):
    """줄바꿈 표기(CRLF/LF)만 통일한다 — 공백·주석은 일부러 안 건드린다."""
    return text.replace("\r\n", "\n")


def statements(sql):
    """주석을 걷어낸 **실제 SQL 문장만** (줄바꿈은 그대로 — `(?m)^…` 정규식용).

    설명 주석에 적어 둔 말이 문장으로 오해되면 코드가 망가져도 초록이 된다
    (형제 test_tx_yearly_migration·test_price_gate_migration 이 같은 방식을 쓴다).
    """
    return "\n".join(
        line for line in norm(sql).splitlines() if not line.lstrip().startswith("--")
    )


def flat(sql):
    """주석을 걷고 **공백을 한 칸으로** 접은 것 — 권한 문장 단언은 전부 이것을 본다.

    ⛔ 왜 접나: 정본은 권한 문장을 칸 맞춰 적는다. 원문 그대로 찾으면 그 정렬 때문에
       "없다"고 판정해 거짓 빨간불이 나고, 그러면 사람이 시험을 느슨하게 고치게 된다.
    """
    return re.sub(r"\s+", " ", statements(sql))


def fn_block(sql, name=FN, schema=""):
    """`create or replace function [schema.]<name>(` 부터 `$$;` 까지 (본문 + 머리)."""
    sql = norm(sql)
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
    """`returns table ( … )` 안의 칸 이름을 **적힌 순서대로**.

    ⛔ 괄호 짝을 세어 닫는다 — `pnu char(19)` 처럼 타입 안에 괄호가 있으면, 첫 `)` 에서
       끊는 형제 구현은 **첫 칸 하나만 읽고 멈춘다**(그러면 칸이 열일곱 개 늘어도 초록).
    """
    start = block.index("returns table")
    open_at = block.index("(", start)
    depth = 0
    close_at = None
    for j in range(open_at, len(block)):
        if block[j] == "(":
            depth += 1
        elif block[j] == ")":
            depth -= 1
            if depth == 0:
                close_at = j
                break
    assert close_at is not None, "returns table 의 괄호가 안 닫힙니다"
    head = block[open_at:close_at]
    return tuple(m.group(1) for m in re.finditer(r"(?m)^\s+(\w+)\s+\w", head))


def at(pattern, sql, last=False):
    """줄머리 정규식이 처음(또는 마지막) 나오는 **위치**."""
    found = [m.start() for m in re.finditer(pattern, sql)]
    assert found, pattern
    return found[-1] if last else found[0]


# ── 1. 나가는 것은 땅 한 줄 + 상호 3개뿐 ─────────────────────────────────────


class TestReturnedColumnsAreFixed:
    @pytest.mark.parametrize("path", BOTH)
    @pytest.mark.parametrize("schema", ["", "api."])
    def test_exactly_these_columns(self, path, schema):
        """⛔ **칸이 늘면 여기서 먼저 운다.**

        점포 원자료(biz_no·업종 코드·좌표)를 붙이는 것은 별건 판단이라, 조용히 늘어나는
        것을 막는다(returns table 안의 칸 이름을 순서까지 통째로 대조한다).
        """
        assert returns_columns(
            fn_block(statements(read(path)), schema=schema)) == RETURNED_COLUMNS

    @pytest.mark.parametrize("path", BOTH)
    def test_the_api_twin_never_restates_the_body(self, path):
        """⛔ api 쌍둥이가 본문에서 칸을 **다시 나열하기 시작하면** 위 자물쇠가 통하지
        않는 자리가 하나 더 생긴다(두 곳의 순서가 갈려도 에러가 안 난다 — PostgreSQL 은
        이름이 아니라 **자리**로 맞춘다). 통째로 넘기게 둔다."""
        body = flat(fn_block(read(path), schema="api."))
        body = body[body.index("$$"):]
        assert "select * from public.{}(q, lim, sigungu, p_offset)".format(FN) in body
        assert re.search(r"\bo\.", body) is None, "쌍둥이가 칸을 직접 나열하고 있습니다"

    @pytest.mark.parametrize("path", BOTH)
    def test_the_store_raw_columns_never_leave(self, path):
        """⛔ 상호 말고는 점포 표의 어떤 칸도 안 나간다.

        나가는 것은 `biz_name`(원문 상호)뿐이다 — 사업자번호·업종 코드·점포 좌표가
        붙는 순간 이 함수는 "가게 찾기"가 아니라 **점포 원자료 창구**가 된다.
        """
        body = statements(fn_block(read(path)))
        for banned in ("biz_no", "cat_l_cd", "cat_m_cd", "cat_s_cd", "ksic_cd",
                       "ub.lat", "ub.lng", "ub.geom"):
            assert banned not in body, banned

    @pytest.mark.parametrize("path", BOTH)
    def test_it_only_reads(self, path):
        """⛔ 이 길에 쓰기가 붙는 날, 읽기 전용이라는 전제가 사라진다."""
        body = statements(fn_block(read(path))).lower()
        for banned in ("insert", "update ", "delete", "truncate"):
            assert banned not in body, banned


# ── 2. 구를 안 고르면 0건 · 너무 넓으면 한 줄 ────────────────────────────────


class TestScopeRules:
    @pytest.mark.parametrize("path", BOTH)
    def test_no_sigungu_means_no_rows(self, path):
        """⛔ 상호는 같은 이름이 전국에 널려 있다 — 구 없이는 답이 될 수 없다(결정 0007).

        이 조건 한 줄이 빠지면 **전국 검색이 조용히 열린다**(에러 없이 느려지고, 결과도
        쓸모없어진다). 형제 search_buildings 는 `gu is null` 이면 전국을 보므로 그쪽
        문장을 그대로 베끼면 이 규칙이 사라진다 — 그 실수를 여기서 잡는다.
        """
        body = flat(fn_block(read(path)))
        assert "and pat.gu is not null" in body, (
            "구를 안 고른 검색이 열려 있습니다 — 결정 0007 위반"
        )
        assert "and pc.sigungu_code = pat.gu" in body
        assert "pat.gu is null or pc.sigungu_code = pat.gu" not in body, (
            "형제 search_buildings 의 '구를 안 고르면 전국' 조건을 베껴 왔습니다"
        )

    @pytest.mark.parametrize("path", BOTH)
    def test_the_gate_uses_the_shared_limit(self, path):
        """⛔ 상한을 숫자로 박지 않는다 — 정본은 search_scope_limit() 한 곳뿐이다."""
        body = flat(fn_block(read(path)))
        assert "> search_scope_limit()" in body
        assert "6000" not in body, "상한을 숫자로 박았습니다"

    @pytest.mark.parametrize("path", BOTH)
    def test_too_broad_answers_with_one_row_not_zero(self, path):
        """⛔ 게이트에 걸렸을 때 0건을 돌려주면 화면이 "그런 가게가 없다"고 말하게 된다 —
        사실은 "너무 많다"이다. 총계를 실은 **한 줄**로 답한다."""
        body = flat(fn_block(read(path)))
        assert "true, gr.store_snapshot_ym::text," in body, (
            "too_broad 한 줄을 내는 가지가 없습니다"
        )
        assert "where g.broad" in body
        assert "where not g.broad" in body, "정상 결과가 게이트를 안 봅니다"

    @pytest.mark.parametrize("path", BOTH)
    def test_paging_is_clamped_and_tie_broken(self, path):
        """⛔ tie-break 가 없으면 '더 보기'가 이미 본 줄을 다시 가져오거나 건너뛴다."""
        body = flat(fn_block(read(path)))
        assert "limit greatest(1, least(coalesce(lim, 50), 200))" in body
        assert "offset greatest(0, coalesce(p_offset, 0))" in body
        assert "t.road_addr asc nulls last, t.pnu" in body

    @pytest.mark.parametrize("path", BOTH)
    def test_input_wildcards_are_escaped(self, path):
        """⛔ `% _ \\` 를 그대로 흘리면 검색어 한 글자가 표 전체를 부른다."""
        body = flat(fn_block(read(path)))
        assert "replace(replace(replace(search_key(q), '\\', '\\\\'), '%', '\\%'), '_', '\\_')" in body
        assert "like pat.p escape '\\'" in body


# ── 3. 새 함수는 닫힌 채로 태어난다 (2026-09-01b) ────────────────────────────


class TestClosedByDefault:
    @pytest.mark.parametrize("path", BOTH)
    def test_it_is_security_definer_with_a_fixed_search_path(self, path):
        """점포 표가 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다 — 그 대신
        검색경로를 못 박아 다른 함수가 대신 불릴 수 없게 한다."""
        block = fn_block(read(path))
        assert "security definer" in block
        assert "set search_path = public" in block
        api = fn_block(read(path), schema="api.")
        assert "security definer" in api
        assert "set search_path = ''" in api

    @pytest.mark.parametrize("path", BOTH)
    def test_public_is_revoked_and_never_granted(self, path):
        """⛔ 통과 함수가 security definer 라 public 원본을 열 필요가 없다."""
        text = flat(read(path))
        assert (
            "revoke all on function %s(text, int, text, int) "
            "from public, anon, authenticated;" % FN in text
        )
        assert not re.search(
            r"grant execute on function (public\.)?%s\(text, int, text, int\)" % FN, text)

    @pytest.mark.parametrize("path", BOTH)
    def test_api_twin_is_granted_after_revoke(self, path):
        """⛔ 순서가 뒤집히면 대시보드가 붙인 anon 기본권한을 못 걷는다."""
        text = flat(read(path))
        rv = text.index("revoke all on function api.%s(text, int, text, int) "
                        "from public, anon, authenticated;" % FN)
        gr = text.index("grant execute on function api.%s(text, int, text, int) "
                        "to anon, authenticated;" % FN)
        assert rv < gr

    @pytest.mark.parametrize("path", BOTH)
    def test_the_summary_table_is_never_opened_to_anon(self, path):
        """⛔ 요약표가 열리면 상호 묶음(store_names)이 통째로 긁혀 구 좁히기·상한이
        전부 우회된다 — 2026-08-13 사고와 같은 형태다."""
        text = flat(read(path))
        assert "grant select on {}".format(MV) not in text
        assert "grant all on {}".format(MV) not in text
        assert "revoke all on {} from public, anon, authenticated;".format(MV) in text

    def test_the_exposure_check_knows_it(self):
        """허용 목록에 없으면 `--check` 가 멀쩡한 함수를 **[사고]** 로 알린다."""
        assert "api.{}".format(FN) in post_load.ANON_CALLABLE_ALLOWLIST
        assert FN in post_load.ANON_CALLABLE_NAMES
        assert MV not in post_load.ANON_READABLE_ALLOWLIST
        assert MV not in post_load.ANON_CALLABLE_ALLOWLIST

    def test_the_migration_reloads_postgrest(self):
        """⛔ 빠뜨리면 DB 에는 있는데 화면만 404(PGRST202) 가 난다."""
        assert "notify pgrst, 'reload schema';" in statements(read(MIGRATION))


# ── 4. 요약표 — 새 칸 셋과 색인 다섯 ─────────────────────────────────────────


class TestTheSummaryTableCarriesTheStoreNames:
    @pytest.mark.parametrize("path", BOTH)
    def test_the_three_new_columns(self, path):
        """⛔ 세 칸이 **요약표에** 있어야 한다. 점포 표를 직접 훑으면 2글자 검색어가
        trigram 을 못 타 7.6초다(라이브 실측)."""
        text = flat(read(path))
        assert "sn.store_names," in text
        assert "sn.store_names_key," in text
        assert "(select l.ym from latest l)::char(6) as store_snapshot_ym" in text

    @pytest.mark.parametrize("path", BOTH)
    def test_store_names_keeps_one_item_per_store(self, path):
        """⛔ **distinct 로 접으면 안 된다.**

        접는 순간 "이 이름의 가게 N곳"을 요약표 한 줄에서 못 세고, 세러 점포 표를
        되짚어야 한다 — 그 2단계가 찬 캐시 3.2초였다(강남 시제품 실측). 그런데 접어도
        에러는 안 나고 숫자만 조용히 작아진다(같은 이름 가게가 한 곳으로 세어진다).
        """
        text = flat(read(path))
        assert "array_agg(ub.biz_name order by ub.biz_name) as store_names" in text
        assert "array_agg(distinct ub.biz_name" not in text, (
            "store_names 를 distinct 로 접었습니다 — 가게 수가 조용히 줄어듭니다"
        )

    @pytest.mark.parametrize("path", BOTH)
    def test_the_key_column_uses_the_same_ruler_as_building_names(self, path):
        """⛔ 건물 이름과 **같은 자**(search_key)로 자른다 — 같은 검색어에 건물과 상호가
        다른 답을 내면 안 된다."""
        text = flat(read(path))
        assert (
            "string_agg(distinct search_key(ub.biz_name), '|') as store_names_key"
            in text
        )

    @pytest.mark.parametrize("path", BOTH)
    def test_only_the_latest_snapshot(self, path):
        """⛔ 분기를 안 고르면 폐업한 옛 가게가 그대로 검색된다.

        ⓘ 스칼라 하위질의여야 idx_ub_pnu_cat (pnu, snapshot_ym) 이 이 조회를 받친다 —
          조인 조건으로 바꾸면 에러 없이 느려지기만 한다(가장 늦게 발견되는 회귀).
        """
        text = flat(read(path))
        assert "select max(u.snapshot_ym) as ym from unit_business u" in text
        assert "and ub.snapshot_ym = (select l.ym from latest l)" in text
        assert "and ub.biz_name is not null" in text

    @pytest.mark.parametrize("path", BOTH)
    def test_it_still_keeps_only_parcels_that_have_buildings(self, path):
        """⛔ 이 조건이 빠지면 요약표가 parcel 전체 사본(112만 행)이 돼 이 표를 만든
        이유가 통째로 사라진다."""
        assert (
            "where exists (select 1 from building b where b.pnu = pc.pnu);"
            in flat(read(path))
        )

    @pytest.mark.parametrize("path", BOTH)
    def test_every_index_is_recreated(self, path):
        """⛔ 뷰를 떨어뜨리면 색인도 함께 사라진다 — **옛 넷 + 새 하나**를 다 만든다.

        유니크가 빠지면 `refresh … concurrently` 가 에러로 멈춰 `post_load.py` 가 통째로
        서고, trgm·구 색인이 빠지면 **에러 없이 검색만 느려진다**(가장 늦게 발견된다).
        """
        text = statements(read(path))
        for name, unique in MV_INDEXES:
            pat = r"(?im)^create %sindex if not exists %s\s+on %s " % (
                "unique " if unique else "", name, MV)
            assert re.search(pat, text), "{} 를 다시 안 만들었습니다".format(name)
        assert re.search(
            r"(?im)^create index if not exists idx_msp_store_names\s+on %s "
            r"using gin \(store_names_key gin_trgm_ops\);" % MV, text)

    def test_the_migration_rebuilds_instead_of_pretending(self):
        """⛔ **`if not exists` 로는 칸이 안 붙는다** — 이미 있으면 아무 일도 안 하고
        에러도 안 난다(화면만 옛 모양을 계속 말한다). 반드시 떨어뜨린 **뒤** 만든다."""
        text = statements(read(MIGRATION))
        drop = text.index("drop materialized view if exists {};".format(MV))
        make = text.index("create materialized view {} as".format(MV))
        assert drop < make, "떨어뜨리기 전에 만들고 있습니다"
        assert "create materialized view if not exists {}".format(MV) not in text, (
            "칸을 더하는 판에서 `if not exists` 는 아무 일도 안 합니다"
        )


# ── 5. 딸려 오는 의존 사슬을 **전부** 되세운다 ───────────────────────────────


class TestTheDependencyChainIsRestored:
    """mv_search_parcel 에 기대어 사는 것이 넷이다 — 결정 0028 §결정 3 이 몰랐던 사실.

    라이브에서 그냥 drop 하면 "cannot drop … because other objects depend on it" 로
    막힌다. 그래서 이 마이그레이션은 다섯을 함께 다시 만든다. 하나라도 빠뜨리면
    검색·지역 목록·각주가 통째로 사라진다.
    """

    def test_dropped_dependents_first(self):
        """⛔ 순서가 뒤집히면 "다른 것이 기대고 있다"로 막힌다."""
        text = statements(read(MIGRATION))
        spots = []
        for kind, name in CHAIN:
            stmt = "drop {} if exists {};".format(kind, name)
            assert stmt in text, stmt
            spots.append(text.index(stmt))
        assert spots == sorted(spots), "사슬을 의존하는 쪽부터 안 떨어뜨립니다"

    def test_never_uses_cascade(self):
        """⛔ cascade 는 **지금 모르는 의존물까지 조용히 지운다.** 이름을 하나씩 적으면
        모르는 것이 있을 때 에러로 멈춘다 — 막히는 편이 조용히 지워지는 것보다 낫다."""
        assert "cascade" not in statements(read(MIGRATION)).lower()

    def test_every_dependent_is_recreated(self):
        text = statements(read(MIGRATION))
        assert re.search(r"(?im)^create materialized view mv_open_sigungu as", text)
        assert re.search(r"(?im)^create materialized view mv_coverage_stats as", text)
        assert re.search(r"(?im)^create or replace view v_coverage_stats as", text)
        assert re.search(
            r"(?im)^create or replace view api\.v_coverage_stats as", text)
        # 그 표들의 유니크 색인도 함께 사라졌다 — 없으면 갱신이 멈춘다.
        assert re.search(
            r"(?im)^create unique index if not exists idx_mos_sigungu "
            r"on mv_open_sigungu \(sigungu_code\);", text)
        assert re.search(
            r"(?im)^create unique index if not exists idx_mcs_snapshot_ym "
            r"on mv_coverage_stats \(snapshot_ym\);", text)

    def test_the_public_view_keeps_its_grant_and_invoker_setting(self):
        """⛔ **이 파일에서 가장 조용히 깨질 수 있는 자리다.**

        뷰가 사라졌다 돌아오면서 anon SELECT 가 같이 날아가는데, `post_load.py --check`
        는 "열려 있으면 안 되는데 열린 것"만 잡지 "열려 있어야 하는데 닫힌 것"은 못
        잡는다 — **경보 없이 각주만** 사라진다(그게 v_coverage_stats 코멘트의 ⛔ 그것이다).
        """
        text = flat(read(MIGRATION))
        for view in ("v_coverage_stats", "api.v_coverage_stats"):
            rv = text.index(
                "revoke all on {} from public, anon, authenticated;".format(view))
            gr = text.index("grant select on {} to anon, authenticated;".format(view))
            assert rv < gr, view
        assert "alter view v_coverage_stats set (security_invoker = false);" in text, (
            "security_invoker 를 안 되돌리면 원본 표가 anon 에게 401 을 낸다"
        )

    def test_the_recreated_dependents_match_the_canon(self):
        """⛔ 되세우면서 본문이 갈리면 **새 환경과 라이브가 다른 말을 하게 된다.**

        정본에서 그대로 베껴 왔는지 문장 단위로 대조한다(주석은 걷고 공백은 접는다 —
        정본은 칸을 맞춰 적는다).
        """
        mig, sch = flat(read(MIGRATION)), flat(read(SCHEMA))
        for name in ("mv_open_sigungu", "mv_coverage_stats"):
            assert _matview_body(mig, name) == _matview_body(sch, name), (
                "{} 본문이 정본과 다릅니다".format(name)
            )

    def test_the_summary_table_body_matches_the_canon(self):
        """정본은 `if not exists` 로, 마이그레이션은 그것 없이 만든다 — 그 한 조각만
        빼고 **글자 그대로** 같아야 한다."""
        assert (_matview_body(flat(read(MIGRATION)), MV)
                == _matview_body(flat(read(SCHEMA)), MV))


def _matview_body(flat_sql, name):
    """`create materialized view [if not exists ]<name> as … ;` 한 문장(접힌 것)."""
    m = re.search(
        r"create materialized view (?:if not exists )?%s as .*?;" % name, flat_sql)
    assert m, name
    return re.sub(r"^create materialized view if not exists ",
                  "create materialized view ", m.group(0))


# ── 6. 옛 상호 색인은 **맨 끝**에서 지운다 ───────────────────────────────────


class TestTheOldIndexIsDroppedLast:
    def test_it_is_the_very_last_statement(self):
        """⛔ 덩어리 **안**에 두면 ACCESS EXCLUSIVE 락이 커밋까지 유지돼, 요약표 굽는
        내내 점포 표를 읽는 다른 세션이 전부 줄을 선다(2026-08-22c 가 적어 둔 함정).
        커밋 뒤 제 트랜잭션에서 혼자 돌면 잠금이 순식간이다."""
        text = statements(read(MIGRATION)).rstrip()
        assert text.endswith("drop index if exists {};".format(OLD_INDEX)), (
            "옛 색인 지우기가 맨 끝이 아닙니다"
        )

    def test_the_canon_no_longer_creates_it(self):
        """⛔ 정본에 남아 있으면 **새 환경에만** 186MB 짜리 색인이 생겨 라이브와 갈린다
        (형제 가드 test_schema_migration_sync 도 같은 것을 본다)."""
        assert not re.search(
            r"(?im)^create\s+(?:unique\s+)?index\s+(?:if\s+not\s+exists\s+)?%s\b"
            % OLD_INDEX, read(SCHEMA)
        ), "지운 색인이 정본에 남아 있습니다"

    def test_nothing_uses_it_anymore(self):
        """지우는 근거 — 쓰는 코드가 0건이다. 함수 본문 어디에도 이름이 없다."""
        assert OLD_INDEX not in statements(read(SCHEMA))


# ── 7. 전부 아니면 전무 (begin … commit) ─────────────────────────────────────


class TestTheRebuildIsAtomic:
    """다섯을 떨어뜨렸다 다시 만드는 판은 반드시 ``begin`` … ``commit`` 으로 감싼다.

    ``scripts/dbx.py -f`` 는 psql 자동커밋(``--single-transaction`` 없음)이라, 감싸지
    않으면 요약표를 굽는 도중 끊겼을 때 **검색·지역 목록·각주가 사라진 채 남는다**
    (그리고 ``post_load.py`` 의 refresh 가 "그런 뷰 없음"으로 멈춰 다른 갱신까지 선다).
    """

    # ⓘ statements() 는 주석만 걷어낸 **한 덩어리 문자열**이라(함수 본문 안의 ';' 때문에
    #   문장으로 쪼개지 않는다) 줄머리 정규식의 **위치**로 순서를 잰다.
    DDL = r"(?m)^(drop |create |grant |revoke |comment on |analyze |alter view )"

    def test_begin_comes_before_the_first_drop(self):
        sql = statements(read(MIGRATION)).lower()
        assert at(r"(?m)^begin;", sql) < at(r"(?m)^drop ", sql)

    def test_commit_comes_after_every_ddl_but_the_last_drop_index(self):
        """⛔ 커밋 뒤에 남아도 되는 것은 **옛 색인 지우기 하나뿐**이다(위 §6). 다른 DDL 이
        덩어리 밖으로 새면 그만큼 '전부 아니면 전무'가 깨진다."""
        sql = statements(read(MIGRATION)).lower()
        commit = at(r"(?m)^commit;", sql)
        outside = [m.start() for m in re.finditer(self.DDL, sql) if m.start() > commit]
        assert outside == [at(r"(?m)^drop index if exists %s;" % OLD_INDEX, sql)], (
            "커밋 뒤에 있으면 안 되는 DDL 이 있습니다: {}".format(
                [sql[p:p + 60] for p in outside])
        )

    def test_notify_comes_after_commit(self):
        """⛔ 안에 두면 롤백된 판에서도 PostgREST 에 헛알림이 간다(09-09b 선례)."""
        sql = statements(read(MIGRATION)).lower()
        assert at(r"(?m)^commit;", sql) < at(r"(?m)^notify pgrst", sql)

    def test_no_concurrent_index_build(self):
        """⛔ `create index concurrently` 만은 트랜잭션 안에서 못 돈다 — 넣으면 이
        마이그레이션이 통째로 실패한다."""
        assert "concurrently" not in statements(read(MIGRATION)).lower()


# ── 8. 정본 동기 · post_load 가 알고 있는가 ──────────────────────────────────


class TestSchemaMirrorsTheMigration:
    @pytest.mark.parametrize("schema", ["", "api."])
    def test_bodies_letter_for_letter(self, schema):
        """⛔ 정본만 살짝 다듬는 것이 곧 정본↔라이브 불일치다(2026-09-01 2차 적대검증).

        ⓘ 전 함수를 훑는 형제 가드가 따로 있다(tests/test_schema_function_drift.py).
          여기서는 이 함수 하나를 못 박아 두어, 실패 메시지가 무엇 때문인지 바로 보이게 한다.
        """
        assert fn_block(read(MIGRATION), schema=schema) == fn_block(
            read(SCHEMA), schema=schema)


class TestPostLoadKnowsIt:
    def test_refresh_list_still_names_the_summary_table(self):
        """⛔ 갱신 목록에서 빠지면 새 가게를 넣어도 **조용히** 검색에서 빠진다."""
        assert MV in post_load.REFRESH_MVS
        assert "refresh materialized view concurrently {};".format(MV) in (
            post_load.build_refresh_sql()
        )

    def test_the_dependent_summary_is_refreshed_after_it(self):
        """mv_open_sigungu 는 mv_search_parcel 에서 만들어진다 — 순서가 바뀌면 한 박자 늦는다."""
        sql = post_load.build_refresh_sql()
        assert sql.index(MV) < sql.index("mv_open_sigungu")

    def test_allowlist(self):
        assert "api." + FN in post_load.ANON_CALLABLE_ALLOWLIST


# ── 9. 가드 자신의 시험 ──────────────────────────────────────────────────────


def test_statements_really_strips_comments():
    """⛔ **주석 제거기가 헛돌면 위 시험들이 조용히 가짜 초록이 된다** — 가드가 없는
    것보다 나쁘다(막고 있다는 거짓 안심)."""
    text = read(MIGRATION)
    line = ("grant execute on function api.%s(text, int, text, int) "
            "to anon, authenticated;" % FN)
    assert line in flat(text), "전제: 원문에는 그 문장이 살아 있다"
    assert line not in flat(text.replace(line, "-- " + line)), (
        "주석으로 죽인 grant 가 여전히 '있다'고 읽힙니다 — 주석 제거가 헛돕니다"
    )


def test_returns_columns_helper_survives_parenthesised_types():
    """⛔ **형제 파일의 구현은 여기서 첫 칸만 읽고 멈춘다** — `char(19)` 의 닫는 괄호를
    `returns table` 의 끝으로 착각하기 때문이다. 그러면 칸이 열일곱 개 늘어도 초록이다."""
    sample = (
        "create or replace function f(x text)\n"
        "returns table (\n"
        "  pnu   char(19),\n"
        "  n     int,\n"
        "  names text[]\n"
        ")\n"
    )
    assert returns_columns(sample) == ("pnu", "n", "names")


def test_the_index_guard_actually_notices_a_missing_index():
    """⛔ 색인 가드가 **죽은 줄을 진짜로 잡는지** 확인한다.

    유니크 색인 한 줄을 주석으로 죽인 사본에서 판정이 뒤집혀야 한다 — 안 뒤집히면
    "색인을 다 되살렸다"는 단언이 사실은 아무것도 안 보고 있는 것이다.
    """
    text = read(MIGRATION)
    line = "create unique index if not exists idx_msp_pnu        on mv_search_parcel (pnu);"
    assert line in text, "전제: 원문에 그 줄이 있다"
    pat = r"(?im)^create unique index if not exists idx_msp_pnu\s+on %s " % MV
    assert re.search(pat, statements(text))
    assert not re.search(pat, statements(text.replace(line, "-- " + line))), (
        "주석으로 죽인 색인이 여전히 '있다'고 읽힙니다"
    )
