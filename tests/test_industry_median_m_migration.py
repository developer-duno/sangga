# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-13a(업종 비중 비교 · 중분류 · 물결 2-3b)의 불변식을 지킨다.

형제 tests/test_industry_median_migration.py(대분류 · 2026-10-12a)의 꼴을 그대로 따른다. 여기서 막는 것:

  1) 마이그레이션과 정본(schema.sql)의 글자가 갈린다 → 새 환경만 다른 모양으로 만들어진다
     (`create or replace` 는 머리 속성을 덮어쓰는데 드리프트 가드는 `$$` 안 본문만 본다 — 머리·comment 까지 대조).
  2) 모집단을 '상권 전체 점포 30곳'으로 고른다 → 👤 ㉙ 은 **그 대분류 가게 30곳 이상**이다.
  3) 몫의 분모를 상권 전체 점포로 둔다 → 👤 ㉘ 은 **그 대분류 안의 몫**(바로 위 중분류 막대와 같은 분모)이다.
  4) 그 중분류가 없는 상권을 0 으로 안 넣는다 → 드문 중분류의 가운데값이 부푼다.
  5) public 원본에 grant 를 준다 → security definer 원본이 밖에 열린다(🚪 grant 는 api 쌍둥이에만).
  6) 응답 열쇠가 빠진다 → 화면 검증기가 응답을 통째로 버려 비교 글이 조용히 사라진다.
  7) 지역 이름을 SQL 에 박는다 → 열린 지역이 느는 날 서버 글자만 낡는다.

② 실행 가드(로컬 PostgreSQL 이 있을 때만)는 흉내 판 위에서 형제 업종 표(정본) + 이 요약표 + 함수를 실제로 돌리고,
   post_load --check 의 모집단 대조·값 다시 세기 문장을 정상 판과 손댄 사본에 돌린다. CI 에는 PostgreSQL 이 없어 건너뛴다.
"""

import os
import re
import shutil
import socket
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-13a_industry_median_m.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

LIST_FN = "list_industry_median_m"
API_FN = "api.list_industry_median_m"
MV = "mv_industry_mix_median_m"
MIX = "mv_district_industry_mix"
SIBLING_FN = "list_industry_median"
RESPONSE_KEYS = ("'snapshot_ym'", "'cat_l_cd'", "'min_total'", "'min_pop'", "'districts'", "'district_id'",
                 "'type'", "'total'", "'pop'", "'scope'", "'sido_cd'", "'district_type'", "'n'", "'cats'",
                 "'cd'", "'nm'", "'med_pct'")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


@pytest.fixture(scope="module")
def mig():
    return read(MIGRATION)


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


def statements(sql):
    """주석 줄을 걷어낸 실제 문장만 — 가드는 이쪽을 본다(주석으로 죽인 문장을 '있다'로 보지 않게)."""
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


def fn_block(sql, name):
    """`create or replace function <name>(` 부터 `$$;` 까지 — 머리 + 본문 통째(줄머리 고정)."""
    m = re.search(r"(?ms)^create\s+or\s+replace\s+function\s+" + re.escape(name)
                  + r"\s*\(.*?\$\$\s*;", sql)
    assert m, "{} 의 정의를 못 찾았습니다 — 정규식이 헛돌면 아래 대조가 통째로 무의미해집니다".format(name)
    return m.group(0)


def fn_comment(sql, name):
    m = re.search(r"(?ms)^comment\s+on\s+function\s+" + re.escape(name) + r"\s*\(.*?';\s*$", sql)
    assert m, "{} 의 comment 를 못 찾았습니다".format(name)
    return m.group(0)


def mv_block(sql, name):
    m = re.search(r"(?ms)^create\s+materialized\s+view\s+if\s+not\s+exists\s+" + re.escape(name)
                  + r"\s+as\b.*?;", sql)
    assert m, "{} 의 정의를 못 찾았습니다".format(name)
    return m.group(0)


def mv_comment(sql, name):
    m = re.search(r"(?ms)^comment\s+on\s+materialized\s+view\s+" + re.escape(name) + r"\s+is.*?';\s*$", sql)
    assert m, "{} 의 comment 를 못 찾았습니다".format(name)
    return m.group(0)


def head_of(block):
    return block[: block.index("$$")]


def body_of(block):
    return block[block.index("$$") + 2: block.rindex("$$")]


def cte(body, name):
    """본문에서 CTE 하나(`  <name> as (` ~ `  ),`) — 주석 줄은 걷는다."""
    m = re.search(r"(?ms)^  (?:with\s+)?" + name + r" as \(\n.*?^  \),?\n", body)
    assert m, name
    return statements(re.sub(r"^  with ", "  ", m.group(0))).rstrip(",\n")


def grant_targets(sql):
    """`grant … on function <대상>(` 의 대상 이름 전부(소문자 · 스키마 그대로).

    ⓘ 가드 본체와 양성 대조가 이 **같은 함수**를 지난다(형제 test_industry_median_migration.py 에서 복사).
    ⚠️ 못 보는 것: 인자 괄호 없는 `on function <이름> to …` · 따옴표 이름 · 일괄 grant(`all functions in schema`).
    """
    found = []
    for stmt in re.findall(r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*?"
                           r"\bon\s+(?:function|routine)\b([^;]*)", statements(sql)):
        found += re.findall(r"(?i)(?<![\w.])((?:\w+\.)?\w+)\s*\(", stmt)
    return [t.lower() for t in found]


def mv_problems(block):
    """요약표 정의의 어긋난 까닭 목록(비면 정상). 가드 본체와 양성 대조가 같은 함수를 지난다.

    · 모집단 = **그 대분류** 가게 30곳 이상 상권(tot 가 대분류로 묶고 `having sum(…) >= 30`) — 👤 ㉙
    · 몫의 분모 = 그 상권의 그 대분류 가게 수(`/ p.cat_total`) — 👤 ㉘
    · 없는 중분류 = 0(`cross join` + `coalesce(…, 0)`) · 빈 중분류는 목록에서 뺀다(`cat_m_cd is not null`)
    · 재료 = 업종 요약표만(점포 표·표지를 직접 안 읽는다 — 분기는 재료의 분기 그대로)
    ⚠️ 못 보는 것: 30 을 상수·함수로 감싼 꼴 · coalesce 를 case 로 바꾼 같은 뜻의 꼴 · tot 를 다른 이름으로 바꾼 꼴
       (그때는 이 함수를 넓힌다).
    """
    code = statements(block).lower()
    out = []
    if not re.search(r"having\s+sum\s*\(\s*(?:\w+\.)?n\s*\)\s*>=\s*30\b", code):
        out.append("30곳 미만 상권을 안 뺌")
    tot = re.search(r"\btot\s+as\s*\((.*?)\)\s*,\s*\n\s*pop\s+as", code, flags=re.S)
    if not tot or not re.search(r"\bcat_l_cd\b", tot.group(1)) or not re.search(r"group\s+by\s+1\s*,\s*2\s*,\s*3\b",
                                                                              tot.group(1)):
        out.append("모집단을 대분류마다 고르지 않음(상권 전체 점포로 셈)")
    if not re.search(r"/\s*p\.cat_total\b", code):
        out.append("몫의 분모가 그 대분류 가게 수가 아님")
    if not re.search(r"coalesce\s*\(\s*(?:\w+\.)?n\s*,\s*0\s*\)", code):
        out.append("없는 중분류를 0 으로 안 넣음")
    if not re.search(r"\bcat_m_cd\s+is\s+not\s+null\b", code):
        out.append("빈 중분류를 중분류 목록에서 안 뺌(cd null 줄이 생긴다)")
    if not re.search(r"\bcross\s+join\b", code):
        out.append("(상권, 대분류) × 중분류 cross join 없음")
    if re.search(r"\bfrom\s+unit_business\b|\bjoin\s+unit_business\b", code):
        out.append("점포 표를 직접 읽음")
    if "published_ym" in code or "snapshot_release" in code:
        out.append("표지를 직접 읽음")
    return out


def region_names(sql):
    """SQL 문장(주석 제외) 안의 지역 이름 — 서버는 sido_cd 만 내고 이름은 화면이 붙인다. 같은 함수를 양성 대조가 지난다."""
    return sorted(set(re.findall(r"서울|대전|Seoul|Daejeon", statements(sql), flags=re.I)))


# ── ① 글자 가드 ─────────────────────────────────────────────────────────────


class TestMirrorsTheSchema:
    @pytest.mark.parametrize("name", (LIST_FN, API_FN))
    def test_head_and_body_are_the_same_text(self, mig, schema, name):
        assert fn_block(mig, name) == fn_block(schema, name), (
            "{} 가 정본과 글자가 다릅니다 — 새 환경만 다른 모양이 됩니다".format(name))

    def test_comment_is_the_same_text(self, mig, schema):
        assert fn_comment(mig, LIST_FN) == fn_comment(schema, LIST_FN)

    def test_summary_table_is_the_same_text(self, mig, schema):
        assert mv_block(mig, MV) == mv_block(schema, MV)
        assert mv_comment(mig, MV) == mv_comment(schema, MV)

    def test_unique_index_is_plain_and_in_both(self, mig, schema):
        """district_type 을 '' 로 두어 평범한 유일 색인 — 정본 색인 점검(post_load --check)이 이 이름을 본다."""
        for sql in (mig, schema):
            assert re.search(r"(?m)^create unique index if not exists mv_industry_mix_median_m_key\n"
                             r"  on mv_industry_mix_median_m \(snapshot_ym, sido_cd, scope, district_type, cat_l_cd, "
                             r"cat_m_cd\);", statements(sql)), "유일 색인이 없으면 refresh concurrently 가 멈춥니다"
        names = set(re.findall(r"(?im)^create\s+(?:unique\s+)?index\s+(?:if\s+not\s+exists\s+)?(\w+)", schema))
        assert "mv_industry_mix_median_m_key" in names

    def test_district_type_is_stored_as_empty_text_not_null(self, mig):
        code = statements(mv_block(mig, MV))
        assert "coalesce(d.district_type, '') as district_type" in code
        assert "'all'::text, ''::text, s.cat_l_cd," in code
        assert "'district_type', nullif(p.district_type, '')," in statements(body_of(fn_block(mig, LIST_FN)))

    def test_columns_are_in_the_planned_order(self, mig):
        """칸 = snapshot_ym, sido_cd, scope, district_type, cat_l_cd, pop_n, cat_m_cd, cat_m_nm, med_pct(설계서 §4-1)."""
        code = statements(mv_block(mig, MV))
        assert re.search(r"select s\.snapshot_ym, s\.sido_cd, 'type'::text as scope, s\.district_type, s\.cat_l_cd,\n"
                         r"\s+count\(distinct s\.district_id\)::int as pop_n,\n"
                         r"\s+s\.cat_m_cd, min\(s\.cat_m_nm\) as cat_m_nm,\n"
                         r"\s+round\(.*\) as med_pct\n", code)


class TestSummaryTable:
    def test_definition_has_the_30_floor_the_share_the_zero_and_one_material(self, mig, schema):
        for sql in (mig, schema):
            assert mv_problems(mv_block(sql, MV)) == []

    @pytest.mark.parametrize("old, new", (
        ("  having sum(m.n) >= 30\n", ""),                                       # 30곳 미만도 모집단에
        # 모집단을 상권 전체 점포 30곳으로(대분류로 안 묶음)
        ("  select m.district_id, m.snapshot_ym, m.cat_l_cd, sum(m.n)::int as cat_total\n"
         "  from mv_district_industry_mix m\n  group by 1, 2, 3\n",
         "  select m.district_id, m.snapshot_ym, sum(m.n)::int as cat_total\n"
         "  from mv_district_industry_mix m\n  group by 1, 2\n"),
        ("coalesce(dc.n, 0)::float8 / p.cat_total", "coalesce(dc.n, 0)::float8 / p.total"),   # 분모를 상권 전체로
        ("coalesce(dc.n, 0)::float8", "dc.n::float8"),                            # 없는 중분류를 빼고 셈
        ("  where m.cat_m_cd is not null\n", ""),                                # 빈 중분류 줄을 남김
        ("  cross join cat c\n  left join dcat dc", "  join dcat dc on true\n  left join cat c on true\n  left join dcat dx"),
        ("from mv_district_industry_mix m\n  group by 1, 2, 3\n  having", "from unit_business m\n  group by 1, 2, 3\n  having"),
        ("  join district d on d.district_id = t.district_id\n),",
         "  join district d on d.district_id = t.district_id\n  join snapshot_release r on true\n),"),
    ))
    def test_mutations_are_noticed(self, mig, old, new):
        """양성 대조 — 30 을 지운·상권 전체로 고른·분모를 바꾼·0 을 뺀·cross join 을 없앤·점포 표·표지를 읽는 사본이 걸린다."""
        block = mv_block(mig, MV)
        assert old in block, old
        assert mv_problems(block.replace(old, new, 1))

    def test_cross_join_is_inside_the_same_major_category(self, mig):
        """중분류 목록은 그 분기 **그 대분류**의 것만 — 다른 대분류의 중분류가 0 으로 끼면 0 이 넘친다."""
        code = statements(mv_block(mig, MV))
        assert "where c.snapshot_ym = p.snapshot_ym and c.cat_l_cd = p.cat_l_cd" in code

    def test_both_scopes_group_by_the_same_share(self, mig):
        code = statements(mv_block(mig, MV))
        assert code.count("from share s") == 2
        assert code.count("percentile_cont(0.5) within group (order by s.share) * 100") == 2
        assert "group by s.snapshot_ym, s.sido_cd, s.district_type, s.cat_l_cd, s.cat_m_cd" in code
        assert "group by s.snapshot_ym, s.sido_cd, s.cat_l_cd, s.cat_m_cd;" in code

    def test_closed_to_anon(self, mig, schema):
        for sql in (mig, schema):
            assert len(re.findall(r"(?m)^revoke all on mv_industry_mix_median_m from public, anon, authenticated;",
                                  statements(sql))) == (1 if sql is mig else 2)

    def test_threshold_matches_the_check_sql(self, mig):
        """`--check` 모집단 대조·다시 세기의 30 과 요약표·함수의 30 이 같은 수여야 대조가 성립한다."""
        mv_n = re.search(r"having sum\(m\.n\) >= (\d+)", mv_block(mig, MV)).group(1)
        chk_n = re.search(r"having sum\(n\) >= (\d+)", post_load.INDUSTRY_MEDIAN_M_CONSISTENCY_SQL).group(1)
        re_n = re.search(r"having sum\(m\.n\) >= (\d+)", post_load.INDUSTRY_MEDIAN_M_RECOMPUTE_SQL).group(1)
        fn_n = re.search(r"select (\d+) as min_total, (\d+) as min_pop", fn_block(mig, LIST_FN))
        assert mv_n == chk_n == re_n == fn_n.group(1) == fn_n.group(2) == "30"


class TestFunction:
    def test_list_function_head(self, mig):
        head = head_of(fn_block(mig, LIST_FN))
        assert "security definer" in head and "set search_path = public" in head
        assert re.search(r"(?m)^stable\s*$", head) and re.search(r"(?m)^language sql\s*$", head)
        assert "returns jsonb" in head and "(p_pnu text, p_cat_l text)" in head

    def test_head_lines_match_the_sibling(self, schema):
        """머리 줄(returns · language · stable · security definer · search_path)은 형제와 같은 줄이다."""
        def head_lines(name):
            return head_of(fn_block(schema, name)).splitlines()[1:]
        assert head_lines(LIST_FN) == head_lines(SIBLING_FN)

    def test_api_twin_head_and_body(self, mig):
        block = fn_block(mig, API_FN)
        head = head_of(block)
        assert "security definer" in head and "set search_path = ''" in head
        assert re.search(r"(?m)^stable\s*$", head)
        assert "(p_pnu text, p_cat_l text)" in head
        assert body_of(block).strip() == "select public.list_industry_median_m(p_pnu, p_cat_l)"

    @pytest.mark.parametrize("name", ("snap", "me", "hit"))
    def test_snap_me_hit_are_the_sibling_text(self, schema, name):
        """형제와 다른 분기·다른 상권을 말하면 같은 블록 안에서 막대와 비교 글이 서로 다른 것을 센다."""
        assert cte(body_of(fn_block(schema, LIST_FN)), name) == cte(body_of(fn_block(schema, SIBLING_FN)), name)

    def test_response_keys_are_in_the_body(self, mig):
        body = statements(body_of(fn_block(mig, LIST_FN)))
        for key in RESPONSE_KEYS:
            assert key in body, key
        assert "radius" not in body
        assert "'cat_l_cd', p_cat_l," in body, "물어본 대분류를 그대로 돌려줘야 화면이 늦은 답을 버린다"

    def test_casts_and_no_store_name(self, mig):
        body = statements(body_of(fn_block(mig, LIST_FN)))
        assert "p_pnu::char(19)" in body
        assert body.count("p_cat_l::char(2)") == 3, "total · pick · cats 세 곳 모두 char(2) 로 견준다"
        assert "biz_name" not in body

    def test_total_is_the_major_category_count(self, mig):
        """total = 이 상권의 **그 대분류** 가게 수 — 상권 전체 점포가 아니다(👤 ㉘·㉙ · 30 비교도 이 수로)."""
        hd = cte(body_of(fn_block(mig, LIST_FN)), "hd")
        assert "and m.cat_l_cd = p_cat_l::char(2)), 0)::int as total" in hd

    def test_population_is_chosen_by_count_type_first(self, mig):
        body = statements(body_of(fn_block(mig, LIST_FN)))
        assert "and t.cat_l_cd = p_cat_l::char(2)\n        and t.pop_n >= (select min_pop from lim)" in body
        assert "order by (t.scope = 'type') desc" in body
        assert "where hd.total >= (select min_total from lim)" in body
        # 30곳 미만(1곳 이상)은 pop null 줄 · 0곳은 줄 없음 · 모집단을 못 고른 상권은 줄 없음.
        assert ("where (hd.total > 0 and hd.total < (select min_total from lim)) or p.district_id is not null"
                in body)

    def test_no_region_names_in_sql(self, mig):
        assert region_names(mv_block(mig, MV)) == []
        assert region_names(fn_block(mig, LIST_FN)) == []

    @pytest.mark.parametrize("bad", ("select '서울' as nm", "SELECT 'Seoul'", "case when x = '11' then '대전' end"))
    def test_region_detector_catches(self, bad):
        assert region_names(bad)


class TestPermissions:
    def test_only_the_api_twin_is_granted(self, mig, schema):
        assert grant_targets(mig) == [API_FN]
        assert [t for t in grant_targets(schema) if "industry_median_m" in t] == [API_FN]

    @pytest.mark.parametrize("bad", (
        "grant execute on function list_industry_median_m(text, text) to anon;",
        "grant all on function public.list_industry_median_m(text, text) to anon;",
        "  GRANT EXECUTE\n  ON FUNCTION list_industry_median_m ( text, text ) TO authenticated;",
    ))
    def test_grant_detector_catches_the_public_original(self, mig, bad):
        found = grant_targets(mig + "\n" + bad + "\n")
        assert [t for t in found if t != API_FN], found

    @pytest.mark.parametrize("name", ("list_industry_median_m(text, text)", "api.list_industry_median_m(text, text)"))
    def test_every_function_is_revoked_with_anon_named(self, mig, name):
        assert re.search(r"(?m)^revoke all on function " + re.escape(name)
                         + r" from public, anon, authenticated;", statements(mig)), name

    def test_revoke_before_grant(self, mig, schema):
        for sql in (mig, schema):
            code = statements(sql)
            assert (code.index("revoke all on function api.list_industry_median_m(")
                    < code.index("grant execute on function api.list_industry_median_m("))

    def test_allowlist_has_the_api_twin_only(self):
        assert API_FN in post_load.ANON_CALLABLE_ALLOWLIST
        assert LIST_FN not in post_load.ANON_CALLABLE_ALLOWLIST
        assert not [n for n in post_load.ANON_READABLE_ALLOWLIST if MV in n]
        assert not [n for n in post_load.ANON_CALLABLE_ALLOWLIST if MV in n]

    def test_allowlist_total_is_32(self):
        """읽기 4 + 부르기 28 = `--check` 총계 32(2026-10-13a 로 31 → 32)."""
        assert len(post_load.ANON_READABLE_ALLOWLIST) + len(post_load.ANON_CALLABLE_ALLOWLIST) == 32


class TestPostLoadWiring:
    def test_refresh_order_and_quarter_set(self):
        mvs = post_load.REFRESH_MVS
        assert mvs.index(MV) > mvs.index(MIX), "재료(업종 표) 뒤라야 한다 — 앞이면 옛 업종 표로 굽는다"
        assert mvs.index(MV) == mvs.index("mv_industry_mix_median") + 1
        assert post_load.QUARTER_MVS[-1] == MV and len(post_load.QUARTER_MVS) == 6
        assert MV not in post_load.NON_QUARTER_MVS and len(post_load.NON_QUARTER_MVS) == 5

    def test_publish_do_compares_the_sixth(self):
        do = post_load.PUBLISH_DO_SQL
        assert "select max(t.snapshot_ym) into h from public.mv_industry_mix_median_m t;" in do
        assert "or g is distinct from v or h is distinct from v then" in do
        assert "· 중분류 가운데값 % (통째 롤백)" in do and "v, s, c, m, f, g, h;" in do
        body = post_load.build_publish_tx_sql()
        assert (body.index("refresh materialized view concurrently mv_district_industry_mix;")
                < body.index("refresh materialized view concurrently mv_industry_mix_median_m;")
                < body.index("do $$"))

    @pytest.mark.parametrize("sql", ("INDUSTRY_MEDIAN_M_FRESHNESS_SQL", "INDUSTRY_MEDIAN_M_CONSISTENCY_SQL",
                                     "INDUSTRY_MEDIAN_M_RECOMPUTE_SQL"))
    def test_check_sql_is_ascii(self, sql):
        assert all(ord(ch) < 128 for ch in getattr(post_load, sql)), "psql -c 로 가는 SQL 에 한글이 있으면 서버에서 죽습니다"

    def test_recompute_takes_the_other_road_with_null_safe_keys(self):
        sql = post_load.INDUSTRY_MEDIAN_M_RECOMPUTE_SQL
        assert "percentile_cont" not in sql, "요약표와 같은 함수로 세면 같은 실수를 같이 한다"
        assert "row_number() over" in sql and "rn in ((cnt + 1) / 2, (cnt + 2) / 2)" in sql
        assert "abs(a.med_pct - b.med) > 0.051" in sql
        for k in ("sido_cd", "cat_l_cd", "cat_m_cd"):
            assert "coalesce(a.{0}, '') = coalesce(b.{0}, '')".format(k) in sql, k
        assert "a.snapshot_ym is null or b.snapshot_ym is null" in sql
        assert "count(a.snapshot_ym)::text || '|' || count(b.snapshot_ym)::text" in sql
        # sh 의 비교는 요약표 정의와 같은 = (빈 값 규칙을 한쪽만 바꾸지 않게).
        assert "and x.cat_l_cd = c.cat_l_cd and x.cat_m_cd = c.cat_m_cd), 0)::float8 / p.cat_total as share" in sql
        assert "on c.snapshot_ym = p.snapshot_ym and c.cat_l_cd = p.cat_l_cd" in sql
        # 빈 중분류는 요약표 cat CTE 와 같은 규칙으로 중분류 목록에서 뺀다(분모 cat_total 에는 든다).
        assert "join snap s using (snapshot_ym) where m.cat_m_cd is not null)," in sql

    def test_consistency_keys_and_null_major(self):
        sql = post_load.INDUSTRY_MEDIAN_M_CONSISTENCY_SQL
        assert "full join" in sql and "using (" not in sql
        assert "from mv_industry_mix_median_m where scope = 'all' group by 1, 2, 3" in sql
        assert "coalesce(a.cat_l_cd, '') = coalesce(b.cat_l_cd, '')" in sql
        assert "and cat_l_cd is not null" in sql
        assert "where snapshot_ym in (select snapshot_ym from mv_industry_mix_median_m)" in sql


class TestMigrationShape:
    def test_settings_before_begin_and_notify_after_commit(self, mig):
        code = statements(mig)
        begin = re.search(r"(?m)^begin;", code).start()
        commit = re.search(r"(?m)^commit;", code).start()
        notify = code.index("notify pgrst, 'reload schema';")
        assert code.index("set lock_timeout = ") < begin
        assert code.index("set statement_timeout = '900s';") < begin
        assert begin < commit < notify
        assert len(re.findall(r"(?m)^begin;", code)) == 1 and len(re.findall(r"(?m)^commit;", code)) == 1
        for stmt in re.finditer(r"(?im)^(create|drop|alter|insert|revoke|grant|analyze|comment)\b", code):
            assert begin < stmt.start() < commit, "begin/commit 밖의 문장: " + stmt.group(0)

    def test_only_new_objects(self, mig):
        """기존 객체는 안 건드린다 — drop·alter 0, 만드는 함수는 새 이름 둘뿐, 요약표 하나."""
        code = statements(mig)
        assert not re.search(r"(?im)^\s*(drop|alter)\s", code)
        made = re.findall(r"(?im)^create\s+(?:or\s+replace\s+)?function\s+([\w.]+)\s*\(", code)
        assert made == [LIST_FN, API_FN]
        assert re.findall(r"(?im)^create\s+materialized\s+view\s+if\s+not\s+exists\s+(\w+)", code) == [MV]

    def test_rollback_paragraph_is_written(self, mig):
        assert "되돌리기" in mig
        for piece in ("drop function api.list_industry_median_m(text, text)",
                      "drop function list_industry_median_m(text, text)",
                      "drop materialized view mv_industry_mix_median_m"):
            assert piece in mig, piece


# ── ② 실행 가드 (로컬 PostgreSQL 이 있을 때만) ──────────────────────────────

SHIM = """
create domain geography as text;
create table parcel (pnu char(19) primary key, geom text);
create table district (district_id text primary key, district_nm text, district_type text, source_nm text,
                       area_m2 numeric(14,2), sigungu_code char(5), geom text);
create table unit_business (snapshot_ym char(6), pnu char(19), floor_no smallint, cat_l_cd char(2),
                            cat_l_nm text, cat_m_cd char(4), cat_m_nm text, geom text, biz_name text);
create table snapshot_release (id int primary key, loaded_ym char(6), published_ym char(6));
-- 흉내 낸 공간 판정: 점 이름이 도형 글자 안에 '|이름|' 꼴로 들어 있으면 담긴 것.
create function st_contains(poly text, pt text) returns boolean language sql immutable
  as 'select position(''|'' || pt || ''|'' in poly) > 0';
"""

P_GOL = "1168010100100010000"     # 골목 G31 + 작은 골목 S1(음식 20) + 음식 0곳 골목 Z1 안
P_TOUR = "1168010100100020000"    # 관광특구 T1 안(종류 2곳 → 서울 전체로)
P_NOGEOM = "1168010100100030000"  # 좌표 없음
P_DJ = "3011010100100010000"      # 대전 D1 안(음식 모집단 1곳 < 30 → 줄 없음)

# 골목 31곳(음식 100곳씩): 비알코올 I212 = 1~15번은 0곳, 16~31번은 10~25곳 · 나머지는 한식 I201.
#   → 비알코올 몫(0 포함) 31개를 세우면 16번째 = 10% · 0 을 빼면 10~25 의 가운데 = 17.5%.
#   → 한식 몫 = 1.0 × 15 · 0.90~0.75 × 16 → 가운데 0.90 = 90.0.
# 관광특구 2곳(음식 50 = 한식 25 · 비알코올 25) · 작은 골목 S1(음식 20 + 소매 200 — 상권 전체로는 30곳이 넘지만
# 음식은 20곳이라 음식 모집단 밖) · 골목 Z1(소매 50 · 음식 0) · 대전 D1(음식 40 = 한식 30 · 동남아 I205 10).
#   → 서울 음식 모집단 = 골목 31 + 관광특구 2 = 33 · 동남아 I205 는 대전에만 있어 서울은 전부 0 으로 든다(0 포함).
#   → 서울 소매 모집단 = S1 · Z1 = 2(< 30) — 소매를 물으면 서울 어디서도 줄이 없다.
FIXTURE = """
insert into parcel values ('{gol}', 'PA'), ('{tour}', 'PT'), ('{nogeom}', null), ('{dj}', 'PD');
insert into snapshot_release values (1, '202606', '202606');
insert into district
  select 'G' || lpad(i::text, 2, '0'), '골목' || i, '골목상권', '서울특별시 상권분석서비스', 1000 + i, '11680',
         case when i = 31 then '|PA|G31|' else '|G' || lpad(i::text, 2, '0') || '|' end
  from generate_series(1, 31) i;
insert into district values
  ('T1', '관광1', '관광특구', '서울특별시 상권분석서비스', 9000, '11140', '|PT|T1|'),
  ('T2', '관광2', '관광특구', '서울특별시 상권분석서비스', 9001, '11140', '|T2|'),
  ('S1', '작은골목', '골목상권', '서울특별시 상권분석서비스', 500, '11680', '|PA|S1|'),
  ('Z1', '소매골목', '골목상권', '서울특별시 상권분석서비스', 400, '11680', '|PA|Z1|'),
  ('D1', '대전상권', '주요상권', '소상공인시장진흥공단 주요상권', 700, '30110', '|PD|D1|');
insert into unit_business (snapshot_ym, cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, geom)
  select '202606', 'I2', '음식', 'I212', '비알코올', 'G' || lpad(i::text, 2, '0')
  from generate_series(1, 31) i, generate_series(1, 100) k
  where k <= case when i <= 15 then 0 else i - 6 end;
insert into unit_business (snapshot_ym, cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, geom)
  select '202606', 'I2', '음식', 'I201', '한식', 'G' || lpad(i::text, 2, '0')
  from generate_series(1, 31) i, generate_series(1, 100) k
  where k <= 100 - case when i <= 15 then 0 else i - 6 end;
insert into unit_business (snapshot_ym, cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, geom)
  select '202606', 'I2', '음식', c.m, c.mn, t.g
  from (values ('T1'), ('T2')) t(g),
       (values ('I201', '한식'), ('I212', '비알코올')) c(m, mn),
       generate_series(1, 25) k;
insert into unit_business (snapshot_ym, cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, geom)
  select '202606', 'I2', '음식', 'I201', '한식', 'S1' from generate_series(1, 20) k;
insert into unit_business (snapshot_ym, cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, geom)
  select '202606', 'G2', '소매', 'G204', '종합 소매', 'S1' from generate_series(1, 200) k;
insert into unit_business (snapshot_ym, cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, geom)
  select '202606', 'G2', '소매', 'G204', '종합 소매', 'Z1' from generate_series(1, 50) k;
insert into unit_business (snapshot_ym, cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, geom)
  select '202606', 'I2', '음식', 'I201', '한식', 'D1' from generate_series(1, 30) k;
insert into unit_business (snapshot_ym, cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, geom)
  select '202606', 'I2', '음식', 'I205', '동남아시아', 'D1' from generate_series(1, 10) k;
-- 옛 분기 행 — 업종 표가 표지 loaded 분기만 굽으므로 어디에도 안 든다.
insert into unit_business (snapshot_ym, cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, geom)
  select '202603', 'I1', '숙박', 'I101', '숙박', 'G01' from generate_series(1, 500) k;
""".format(gol=P_GOL, tour=P_TOUR, nogeom=P_NOGEOM, dj=P_DJ)


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    psycopg2 = pytest.importorskip("psycopg2")
    initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
    if not initdb or not pg_ctl:
        pytest.skip("로컬 PostgreSQL(initdb·pg_ctl)이 없다 — CI 는 글자 가드(①)만 본다")
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


@pytest.fixture(scope="module")
def cur(pg):
    """흉내 판 위에 형제 업종 표(정본) + 마이그레이션의 요약표·색인·함수를 넣는다."""
    mig, schema = read(MIGRATION), read(SCHEMA)
    c = pg.cursor()
    c.execute("drop schema if exists public cascade; create schema public;")
    c.execute(SHIM)
    c.execute(FIXTURE)
    c.execute(mv_block(schema, MIX))
    c.execute(mv_block(mig, MV))
    c.execute(re.search(r"(?ms)^create unique index if not exists mv_industry_mix_median_m_key\n.*?;", mig).group(0))
    c.execute(fn_block(mig, LIST_FN))
    return c


def _call(cur, pnu, cat):
    cur.execute("select list_industry_median_m(%s, %s)", (pnu, cat))
    return cur.fetchone()[0]


def _row(cur, sido, scope, dtype, cat_l, cat_m):
    cur.execute("select pop_n, med_pct::text from mv_industry_mix_median_m "
                "where sido_cd = %s and scope = %s and district_type = %s and cat_l_cd = %s and cat_m_cd = %s",
                (sido, scope, dtype, cat_l, cat_m))
    return cur.fetchone()


class TestRealRun:
    def test_zero_is_counted_in_the_median(self, cur):
        """0 포함 가운데값 = 10.0 — 0 을 빼고 세면 17.5 가 된다(드문 중분류가 부푸는 병)."""
        assert _row(cur, "11", "type", "골목상권", "I2", "I212") == (31, "10.0")
        assert _row(cur, "11", "type", "골목상권", "I2", "I201") == (31, "90.0")

    def test_a_middle_category_absent_everywhere_in_the_sido_is_0(self, cur):
        """동남아시아는 대전 D1 에만 있다 — 서울 골목 31곳은 전부 0 으로 들어가 0.0(cross join 이 없으면 줄이 없다)."""
        assert _row(cur, "11", "type", "골목상권", "I2", "I205") == (31, "0.0")
        assert _row(cur, "11", "all", "", "I2", "I205") == (33, "0.0")

    def test_population_is_the_major_category_30_not_the_whole_district(self, cur):
        """S1 은 점포 220곳이지만 음식 20곳 — 음식 모집단 밖(서울 전체 33 = 골목 31 + 관광특구 2) · 소매 모집단 안."""
        assert _row(cur, "11", "all", "", "I2", "I201") == (33, "89.0")
        assert _row(cur, "11", "all", "", "I2", "I212") == (33, "11.0")
        assert _row(cur, "11", "type", "관광특구", "I2", "I201") == (2, "50.0")
        assert _row(cur, "11", "type", "골목상권", "G2", "G204") == (2, "100.0")
        assert _row(cur, "30", "type", "주요상권", "I2", "I201") == (1, "75.0")

    def test_share_denominator_is_the_major_category(self, cur):
        """대전 D1: 한식 30 / 음식 40 = 75% · 동남아 10 / 40 = 25%(상권 전체로 나누면 다른 값)."""
        assert _row(cur, "30", "all", "", "I2", "I205") == (1, "25.0")

    def test_one_quarter_and_unique_shape(self, cur):
        cur.execute("select distinct snapshot_ym from mv_industry_mix_median_m")
        assert [r[0] for r in cur.fetchall()] == ["202606"], "업종 표의 분기 하나만 — 옛 분기 숙박은 안 든다"
        cur.execute("select count(*) from mv_industry_mix_median_m where district_type is null")
        assert cur.fetchone()[0] == 0, "종류 칸은 null 이 아니라 빈 글자"
        cur.execute("select count(*) from mv_industry_mix_median_m where cat_l_cd = 'I1'")
        assert cur.fetchone()[0] == 0
        # 다른 대분류의 중분류가 0 으로 끼지 않는다(소매 묶음에 음식 중분류 0).
        cur.execute("select count(*) from mv_industry_mix_median_m where cat_l_cd = 'G2' and cat_m_cd like 'I%'")
        assert cur.fetchone()[0] == 0

    def test_same_type_population_when_it_has_30(self, cur):
        got = _call(cur, P_GOL, "I2")
        assert got["snapshot_ym"] == "202606" and got["cat_l_cd"] == "I2"
        assert got["min_total"] == 30 and got["min_pop"] == 30
        assert "radius" not in got
        # 좁은 상권 먼저 — Z1(400㎡)은 음식 0곳이라 줄 없음 · S1(500㎡)은 음식 20곳이라 pop null · cats [].
        assert got["districts"][0] == {"district_id": "S1", "type": "골목상권", "total": 20, "pop": None, "cats": []}
        g31 = got["districts"][1]
        assert g31["district_id"] == "G31" and g31["total"] == 100 and g31["type"] == "골목상권"
        assert g31["pop"] == {"scope": "type", "sido_cd": "11", "district_type": "골목상권", "n": 31}
        assert g31["cats"] == [{"cd": "I201", "nm": "한식", "med_pct": 90.0},
                               {"cd": "I212", "nm": "비알코올", "med_pct": 10.0},
                               {"cd": "I205", "nm": "동남아시아", "med_pct": 0.0}]
        assert len(got["districts"]) == 2

    def test_small_type_falls_back_to_the_whole_sido(self, cur):
        got = _call(cur, P_TOUR, "I2")
        [t1] = got["districts"]
        assert t1["total"] == 50
        assert t1["pop"] == {"scope": "all", "sido_cd": "11", "district_type": None, "n": 33}
        assert t1["cats"] == [{"cd": "I201", "nm": "한식", "med_pct": 89.0},
                              {"cd": "I212", "nm": "비알코올", "med_pct": 11.0},
                              {"cd": "I205", "nm": "동남아시아", "med_pct": 0.0}]

    def test_no_population_of_30_drops_the_row_not_says_too_small(self, cur):
        """대전 음식 1곳뿐 · 서울 소매 2곳뿐 — '30곳이 안 돼'(pop null)라고 잘못 말하지 않게 줄을 아예 안 낸다."""
        assert _call(cur, P_DJ, "I2")["districts"] == []
        got = _call(cur, P_GOL, "G2")
        assert got["districts"] == [] and got["cat_l_cd"] == "G2"

    def test_unknown_major_and_no_coord_are_empty(self, cur):
        assert _call(cur, P_GOL, "Z9")["districts"] == []
        got = _call(cur, P_NOGEOM, "I2")
        assert got["districts"] == [] and got["min_total"] == 30

    def test_post_load_m_sqls_agree_on_the_canonical_board(self, cur):
        """--check 의 신선도·모집단 대조·값 다시 세기를 정본 정의로 구운 흉내 판에 — 어긋남 0."""
        cur.execute("set search_path to public")
        cur.execute(post_load.INDUSTRY_MEDIAN_M_FRESHNESS_SQL)
        assert cur.fetchone()[0] == "202606|202606"
        cur.execute(post_load.INDUSTRY_MEDIAN_M_CONSISTENCY_SQL)
        got = tuple(cur.fetchone()[0].split("|"))
        assert got == ("0", "3", "3"), "서울 음식 33 · 서울 소매 2 · 대전 음식 1"
        assert post_load.judge_industry_median_consistency(*got) is False
        cur.execute("select count(*) from mv_industry_mix_median_m")
        n = str(cur.fetchone()[0])
        cur.execute(post_load.INDUSTRY_MEDIAN_M_RECOMPUTE_SQL)
        got = tuple(cur.fetchone()[0].split("|"))
        assert n != "0" and got == ("0", n, n)
        assert post_load.judge_industry_median_recompute(*got) is False

    _ZERO_EXCLUDED = """
        update mv_industry_mix_median_m m set med_pct = s.med
        from (select x.snapshot_ym, left(d.sigungu_code, 2) as sido_cd, coalesce(d.district_type, '') as dt,
                     x.cat_l_cd, x.cat_m_cd,
                     round((percentile_cont(0.5) within group (order by x.n::float8 / t.total) * 100)::numeric, 1)
                       as med
              from (select district_id, snapshot_ym, cat_l_cd, sum(n) as total from mv_district_industry_mix
                    group by 1, 2, 3 having sum(n) >= 30) t
              join district d using (district_id)
              join (select district_id, snapshot_ym, cat_l_cd, cat_m_cd, sum(n) as n from mv_district_industry_mix
                    group by 1, 2, 3, 4) x using (district_id, snapshot_ym, cat_l_cd)
              group by grouping sets ((1, 2, 3, 4, 5), (1, 2, 4, 5))) s
        where m.snapshot_ym = s.snapshot_ym and m.sido_cd = s.sido_cd and m.cat_l_cd = s.cat_l_cd
          and m.cat_m_cd = s.cat_m_cd
          and ((m.scope = 'type' and s.dt is not null and m.district_type = s.dt)
               or (m.scope = 'all' and s.dt is null));
    """

    @pytest.mark.parametrize("tamper, want", [
        # 한 줄을 0.2 틀리게(반올림 한 칸 넘게) — 허용 오차를 1.0 으로 늘리면 놓친다.
        ("update mv_industry_mix_median_m set med_pct = med_pct + 0.2"
         " where scope = 'type' and district_type = '골목상권' and cat_m_cd = 'I212'", ("1", 0, 0)),
        # 모집단 수만 틀린 줄도.
        ("update mv_industry_mix_median_m set pop_n = pop_n + 1"
         " where scope = 'all' and sido_cd = '11' and cat_m_cd = 'I201'", ("1", 0, 0)),
        # 정의 갈림 — 없는 중분류를 빼고(0 미포함) 센 값: 골목 비알코올 10.0 → 17.5 · 서울 전체 비알코올 11.0 → 18.5
        # (I205 는 서울에서 줄 자체가 빠져 갱신 안 됨 · 0 포함 판은 0.0 그대로라 같은 값).
        (_ZERO_EXCLUDED, ("2", 0, 0)),
        # 한쪽에만 있는 줄 — 표에서 한 줄이 빠졌다.
        ("delete from mv_industry_mix_median_m where scope = 'all' and sido_cd = '11' and cat_m_cd = 'I205'",
         ("1", -1, 0)),
        # 표에만 있는 줄 — 재료에 없는 중분류.
        ("insert into mv_industry_mix_median_m (snapshot_ym, sido_cd, scope, district_type, cat_l_cd, pop_n,"
         " cat_m_cd, cat_m_nm, med_pct) values ('202606', '11', 'all', '', 'I2', 33, 'I299', 'x', 1.0)", ("1", 1, 0)),
    ])
    def test_post_load_recompute_sql_catches_tampered_copies(self, pg, cur, tamper, want):
        c = pg.cursor()
        c.execute("drop schema if exists median_m_re cascade; create schema median_m_re;"
                  " create table median_m_re.mv_district_industry_mix as select * from public.mv_district_industry_mix;"
                  " create table median_m_re.district as select * from public.district;"
                  " create table median_m_re.mv_industry_mix_median_m as select * from public.mv_industry_mix_median_m;"
                  " set search_path to median_m_re;")
        try:
            c.execute("select count(*) from mv_industry_mix_median_m")
            n = c.fetchone()[0]
            c.execute(post_load.INDUSTRY_MEDIAN_M_RECOMPUTE_SQL)
            assert c.fetchone()[0] == "0|{0}|{0}".format(n), "손대기 전 사본은 어긋남 0 이어야 한다"
            c.execute(tamper)
            if tamper is self._ZERO_EXCLUDED:
                c.execute("select med_pct::text from mv_industry_mix_median_m where cat_m_cd = 'I212' and sido_cd = '11'"
                          " and scope in ('type', 'all') and district_type in ('골목상권', '') order by scope")
                assert [r[0] for r in c.fetchall()] == ["18.5", "17.5"], "0 을 빼면 부푼다(정의 갈림 흉내 확인)"
            c.execute(post_load.INDUSTRY_MEDIAN_M_RECOMPUTE_SQL)
            got = tuple(c.fetchone()[0].split("|"))
        finally:
            c.execute("reset search_path; drop schema median_m_re cascade;")
        bad, d_med, d_re = want
        assert got == (bad, str(n + d_med), str(n + d_re))
        assert post_load.judge_industry_median_recompute(*got) is True

    @pytest.mark.parametrize("tamper", [
        "update mv_industry_mix_median_m set pop_n = pop_n + 1 where scope = 'all' and sido_cd = '11' and cat_l_cd = 'I2'",
        "delete from mv_industry_mix_median_m where scope = 'all' and sido_cd = '30'",
    ])
    def test_post_load_consistency_sql_catches_tampered_copies(self, pg, cur, tamper):
        c = pg.cursor()
        c.execute("drop schema if exists median_m_pop cascade; create schema median_m_pop;"
                  " create table median_m_pop.mv_district_industry_mix as select * from public.mv_district_industry_mix;"
                  " create table median_m_pop.district as select * from public.district;"
                  " create table median_m_pop.mv_industry_mix_median_m as select * from public.mv_industry_mix_median_m;"
                  " set search_path to median_m_pop;")
        try:
            c.execute(tamper)
            c.execute(post_load.INDUSTRY_MEDIAN_M_CONSISTENCY_SQL)
            got = tuple(c.fetchone()[0].split("|"))
        finally:
            c.execute("reset search_path; drop schema median_m_pop cascade;")
        assert got[0] == "1"
        assert post_load.judge_industry_median_consistency(*got) is True

    # 정상 판을 새로 굽는다 — 재료 사본에 상권을 더한 뒤 마이그레이션의 요약표 정의를 그대로 실행한다.
    _NULL_SIDO = """
        insert into district (district_id, district_type, sigungu_code) values ('N1', '골목상권', null);
        insert into mv_district_industry_mix values ('N1', '202606', 'I2', '음식', 'I201', '한식', 25),
                                                    ('N1', '202606', 'I2', '음식', 'I212', '비알코올', 15);
    """
    # 부산(26) 상권 셋 — 비알코올 몫 10/30 · 11/30 · 13/30 → 가운데 36.666…% 를 표는 36.7 로 반올림한다.
    _ROUGH_MEDIAN = """
        insert into district (district_id, district_type, sigungu_code)
          values ('B1', '골목상권', '26110'), ('B2', '골목상권', '26110'), ('B3', '골목상권', '26110');
        insert into mv_district_industry_mix values
          ('B1', '202606', 'I2', '음식', 'I212', '비알코올', 10), ('B1', '202606', 'I2', '음식', 'I201', '한식', 20),
          ('B2', '202606', 'I2', '음식', 'I212', '비알코올', 11), ('B2', '202606', 'I2', '음식', 'I201', '한식', 19),
          ('B3', '202606', 'I2', '음식', 'I212', '비알코올', 13), ('B3', '202606', 'I2', '음식', 'I201', '한식', 17);
    """
    # 중분류가 빈 음식 줄(운영 0) — 빈 중분류는 중분류 목록에서 빠져 요약표에 cat_m_cd null 줄이 **안** 생긴다(함수 cats 에
    # cd null 이 실리지 않게). 분모(그 대분류 가게 수)에는 그대로 든다 — 부산(26) 상권 셋의 한식 몫 = 20·18·16 / 35 →
    # 가운데 18/35 = 51.4%(빈 중분류를 분모에서도 빼면 100.0). 빼는 조건을 한쪽만 지우면 빨강(아래 변이 시험).
    _NULL_CAT_M = """
        insert into district (district_id, district_type, sigungu_code)
          values ('C1', '골목상권', '26140'), ('C2', '골목상권', '26140'), ('C3', '골목상권', '26140');
        insert into mv_district_industry_mix values
          ('C1', '202606', 'I2', '음식', 'I201', '한식', 20), ('C1', '202606', 'I2', '음식', null, null, 15),
          ('C2', '202606', 'I2', '음식', 'I201', '한식', 18), ('C2', '202606', 'I2', '음식', null, null, 17),
          ('C3', '202606', 'I2', '음식', 'I201', '한식', 16), ('C3', '202606', 'I2', '음식', null, null, 19);
    """
    # 대분류까지 빈 줄(운영 0) — 30곳이 넘어도 요약표 정의(= 이음)에서 모집단이 떨어진다. 모집단 대조가 업종 표 쪽에서
    # 같은 규칙(cat_l_cd is not null)으로 안 빼면 (부산, 빈 대분류) 묶음이 한쪽에만 있어 거짓 [낡음].
    _NULL_CAT_L = """
        insert into district (district_id, district_type, sigungu_code) values ('E1', '골목상권', '26170');
        insert into mv_district_industry_mix values ('E1', '202606', null, null, null, null, 40),
                                                    ('E1', '202606', 'I2', '음식', 'I201', '한식', 35);
    """

    def _bake(self, pg, extra):
        c = pg.cursor()
        c.execute("drop schema if exists median_m_bake cascade; create schema median_m_bake;"
                  " create table median_m_bake.mv_district_industry_mix as select * from public.mv_district_industry_mix;"
                  " create table median_m_bake.district as select * from public.district;"
                  " set search_path to median_m_bake;")
        c.execute(extra)
        return c

    @staticmethod
    def _unbake(c):
        c.execute("reset search_path; drop schema median_m_bake cascade;")

    @pytest.mark.parametrize("extra, check", [
        (_NULL_SIDO, "select count(*) from mv_industry_mix_median_m where sido_cd is null"),
        (_ROUGH_MEDIAN, "select count(*) from mv_industry_mix_median_m where sido_cd = '26' and cat_m_cd = 'I212'"
                        " and med_pct = 36.7"),
        # 빈 중분류 — 줄은 안 생기고(아래 시험) 분모에는 들어 한식 51.4.
        (_NULL_CAT_M, "select count(*) from mv_industry_mix_median_m where sido_cd = '26' and cat_m_cd = 'I201'"
                      " and med_pct = 51.4"),
        (_NULL_CAT_L, "select count(*) from mv_industry_mix_median_m where sido_cd = '26' and cat_l_cd = 'I2'"),
    ], ids=["null-sido", "rough-median", "null-cat-m", "null-cat-l"])
    def test_post_load_m_sqls_stay_green_on_freshly_baked_boards(self, pg, cur, extra, check):
        c = self._bake(pg, extra)
        try:
            c.execute(mv_block(read(MIGRATION), MV))
            c.execute(check)
            assert c.fetchone()[0] >= 1, "흉내 낸 경우가 요약표에 실제로 들어갔어야 한다"
            c.execute("select count(*) from mv_industry_mix_median_m where cat_m_cd is null")
            assert c.fetchone()[0] == 0, "빈 중분류 줄은 요약표에 안 생긴다(함수 cats 에 cd null 이 실리지 않게)"
            c.execute("select count(*) from mv_industry_mix_median_m")
            n = c.fetchone()[0]
            c.execute(post_load.INDUSTRY_MEDIAN_M_RECOMPUTE_SQL)
            got_re = c.fetchone()[0]
            c.execute(post_load.INDUSTRY_MEDIAN_M_CONSISTENCY_SQL)
            got_pop = c.fetchone()[0].split("|")[0]
        finally:
            self._unbake(c)
        assert got_re == "0|{0}|{0}".format(n)
        assert got_pop == "0"

    @pytest.mark.parametrize("target, old, new, extra", [
        # 요약표만 빈 중분류를 남긴다 — 표에만 있는 cd null 줄 → 빨강.
        ("mv", "  where m.cat_m_cd is not null\n", "", _NULL_CAT_M),
        # 다시 세기만 빈 중분류를 남긴다 — 다시 센 쪽에만 있는 줄 → 빨강.
        ("INDUSTRY_MEDIAN_M_RECOMPUTE_SQL", " where m.cat_m_cd is not null)", ")", _NULL_CAT_M),
        # 맞대기 열쇠를 = 로 — 빈 시·도 줄이 양쪽 다 '한쪽에만'으로 세어져 빨강.
        ("INDUSTRY_MEDIAN_M_RECOMPUTE_SQL", "coalesce(a.sido_cd, '') = coalesce(b.sido_cd, '')", "a.sido_cd = b.sido_cd",
         _NULL_SIDO),
        # 모집단 대조에서 빈 대분류를 안 빼면 거짓 [낡음].
        ("INDUSTRY_MEDIAN_M_CONSISTENCY_SQL", " and cat_l_cd is not null", "", _NULL_CAT_L),
    ], ids=["mv-keeps-null-cat-m", "recompute-keeps-null-cat-m", "key-plain-equals", "pop-keeps-null-major"])
    def test_one_sided_null_rule_mutations_go_red(self, pg, cur, target, old, new, extra):
        mv = mv_block(read(MIGRATION), MV)
        sql = post_load.INDUSTRY_MEDIAN_M_RECOMPUTE_SQL if target == "mv" else getattr(post_load, target)
        assert old in (mv if target == "mv" else sql), old
        c = self._bake(pg, extra)
        try:
            c.execute(mv)
            c.execute(sql)
            assert c.fetchone()[0].split("|")[0] == "0", "고치기 전 문장은 초록이어야 변이가 뜻을 갖는다"
            if target == "mv":
                c.execute("drop materialized view mv_industry_mix_median_m;")
                c.execute(mv.replace(old, new, 1))
                c.execute(sql)
            else:
                c.execute(sql.replace(old, new, 1))
            got = c.fetchone()[0].split("|")[0]
        finally:
            self._unbake(c)
        assert got != "0"
