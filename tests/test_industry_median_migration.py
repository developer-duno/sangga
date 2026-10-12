# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-12a(업종 비중 비교 · 물결 2-3)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙여 넣기 전에는 아무도 모르는 종류의 실수**다:

  1) 마이그레이션과 정본(schema.sql)의 글자가 갈린다 → 새 환경만 다른 모양으로 만들어진다.
     `create or replace` 는 머리 속성(security definer·search_path·stable)을 새 정의로 덮어쓰는데,
     드리프트 가드는 `$$` 안 본문만 본다 — 그래서 머리·comment 까지 여기서 글자로 대조한다.
  2) 모집단에서 점포 30곳 미만 상권을 안 뺀다 → 몇 곳뿐인 상권의 비중(1곳이면 100%)이 가운데값을 흔든다.
  3) 그 업종이 없는 상권을 0 으로 안 넣는다 → 드문 업종의 가운데값이 부푼다(실측 골목 숙박 1.8% vs 2.3%).
  4) public 원본에 grant 를 준다 → security definer 원본이 밖에 열린다(🚪 grant 는 api 쌍둥이에만).
  5) 응답 열쇠(min_total·min_pop·pop·cats·med_pct)가 빠진다 → 화면 검증기가 응답을 통째로 버려 비교 글이 조용히 사라진다.
  6) 지역 이름을 SQL 에 박는다 → 열린 지역이 느는 날 서버 글자만 낡는다(화면이 SIDOS 로 붙인다).

② 실행 가드(로컬 PostgreSQL 이 있을 때만)는 흉내 판 위에서 형제 업종 표(정본) + 이 요약표 + 함수를 실제로
   돌려, 그 업종이 없는 상권이 0 으로 들어가 가운데값이 맞는지(0 포함 10.0 · 빼면 17.5), 30곳 미만 상권이
   모집단 밖인지, 종류가 30곳 미만이면 시·도 전체로 넘어가는지 본다. CI 에는 PostgreSQL 이 없어 건너뛴다.
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
MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-12a_industry_median.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

LIST_FN = "list_industry_median"
API_FN = "api.list_industry_median"
MV = "mv_industry_mix_median"
MIX = "mv_district_industry_mix"
SIBLING_FN = "list_industry_mix"
RESPONSE_KEYS = ("'snapshot_ym'", "'min_total'", "'min_pop'", "'districts'", "'district_id'", "'type'",
                 "'total'", "'pop'", "'scope'", "'sido_cd'", "'district_type'", "'n'", "'cats'", "'cd'",
                 "'nm'", "'med_pct'")


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

    권한 종류(execute·all)·받는 역할·들여쓰기·줄바꿈·대소문자와 무관하게 본다.
    ⓘ 가드 본체와 양성 대조가 이 **같은 함수**를 지난다(형제 test_industry_floor_migration.py 에서 복사).
    ⚠️ 못 보는 것: 인자 괄호 없는 `on function <이름> to …` · 따옴표 이름 · 일괄 grant(`all functions in schema`).
    """
    found = []
    for stmt in re.findall(r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*?"
                           r"\bon\s+(?:function|routine)\b([^;]*)", statements(sql)):
        found += re.findall(r"(?i)(?<![\w.])((?:\w+\.)?\w+)\s*\(", stmt)
    return [t.lower() for t in found]


def mv_problems(block):
    """요약표 정의의 어긋난 까닭 목록(비면 정상). 가드 본체와 양성 대조가 같은 함수를 지난다.

    · 모집단 = 점포 30곳 이상 상권(`having sum(…) >= 30`)
    · 없는 업종 = 0(`cross join` + `coalesce(…, 0)`)
    · 재료 = 업종 요약표만(점포 표·표지를 직접 안 읽는다 — 분기는 재료의 분기 그대로)
    ⚠️ 못 보는 것: 30 을 상수·함수로 감싼 꼴 · coalesce 를 case 로 바꾼 같은 뜻의 꼴(그때는 이 함수를 넓힌다).
    """
    code = statements(block).lower()
    out = []
    if not re.search(r"having\s+sum\s*\(\s*(?:\w+\.)?n\s*\)\s*>=\s*30\b", code):
        out.append("점포 30곳 미만 상권을 안 뺌")
    if not re.search(r"coalesce\s*\(\s*(?:\w+\.)?n\s*,\s*0\s*\)", code):
        out.append("없는 업종을 0 으로 안 넣음")
    if not re.search(r"\bcross\s+join\b", code):
        out.append("상권 × 대분류 cross join 없음")
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
            assert re.search(r"(?m)^create unique index if not exists mv_industry_mix_median_key\n"
                             r"  on mv_industry_mix_median \(snapshot_ym, sido_cd, scope, district_type, cat_l_cd\);",
                             statements(sql)), "유일 색인이 없으면 refresh concurrently 가 멈춥니다"
        names = set(re.findall(r"(?im)^create\s+(?:unique\s+)?index\s+(?:if\s+not\s+exists\s+)?(\w+)", schema))
        assert "mv_industry_mix_median_key" in names

    def test_district_type_is_stored_as_empty_text_not_null(self, mig):
        """null 이 든 유일 색인은 중복을 못 막는다 — 종류 칸은 빈 글자로 둔다(all 줄도)."""
        code = statements(mv_block(mig, MV))
        assert "coalesce(d.district_type, '') as district_type" in code
        assert "'all'::text, ''::text," in code
        # 함수는 빈 글자를 null 로 되돌려 낸다(all 이면 district_type null).
        assert "'district_type', nullif(p.district_type, '')," in statements(body_of(fn_block(mig, LIST_FN)))


class TestSummaryTable:
    def test_definition_has_the_30_floor_the_zero_and_one_material(self, mig, schema):
        for sql in (mig, schema):
            assert mv_problems(mv_block(sql, MV)) == []

    @pytest.mark.parametrize("old, new", (
        ("  having sum(m.n) >= 30\n", ""),                                    # 30곳 미만도 모집단에
        ("coalesce(dc.n, 0)::float8", "dc.n::float8"),                         # 없는 업종을 빼고 셈
        ("  cross join cat c\n  left join dcat dc", "  join dcat dc on true\n  left join cat c on true\n  left join dcat dx"),
        ("from mv_district_industry_mix m\n  group by 1, 2\n  having", "from unit_business m\n  group by 1, 2\n  having"),
        ("  join district d on d.district_id = t.district_id\n),",
         "  join district d on d.district_id = t.district_id\n  join snapshot_release r on true\n),"),
    ))
    def test_mutations_are_noticed(self, mig, old, new):
        """양성 대조 — 30 을 지운·0 을 뺀·cross join 을 없앤·점포 표·표지를 직접 읽는 사본이 걸린다."""
        block = mv_block(mig, MV)
        assert old in block, old
        assert mv_problems(block.replace(old, new, 1))

    def test_both_scopes_group_by_the_same_share(self, mig):
        code = statements(mv_block(mig, MV))
        assert code.count("from share s") == 2
        assert code.count("percentile_cont(0.5) within group (order by s.share) * 100") == 2
        assert "group by s.snapshot_ym, s.sido_cd, s.district_type, s.cat_l_cd" in code
        assert "group by s.snapshot_ym, s.sido_cd, s.cat_l_cd;" in code

    def test_closed_to_anon(self, mig, schema):
        for sql in (mig, schema):
            assert len(re.findall(r"(?m)^revoke all on mv_industry_mix_median from public, anon, authenticated;",
                                  statements(sql))) == (1 if sql is mig else 2)

    def test_threshold_matches_the_check_sql(self, mig):
        """`--check` 모집단 대조의 30 과 요약표의 30 이 같은 수여야 대조가 성립한다."""
        mv_n = re.search(r"having sum\(m\.n\) >= (\d+)", mv_block(mig, MV)).group(1)
        chk_n = re.search(r"having sum\(n\) >= (\d+)", post_load.INDUSTRY_MEDIAN_CONSISTENCY_SQL).group(1)
        fn_n = re.search(r"select (\d+) as min_total, (\d+) as min_pop", fn_block(mig, LIST_FN))
        assert mv_n == chk_n == fn_n.group(1) == fn_n.group(2) == "30"


class TestFunction:
    def test_list_function_head(self, mig):
        head = head_of(fn_block(mig, LIST_FN))
        assert "security definer" in head and "set search_path = public" in head
        assert re.search(r"(?m)^stable\s*$", head)
        assert "returns jsonb" in head and "(p_pnu text)" in head

    def test_api_twin_head_and_body(self, mig):
        block = fn_block(mig, API_FN)
        head = head_of(block)
        assert "security definer" in head and "set search_path = ''" in head
        assert re.search(r"(?m)^stable\s*$", head)
        assert body_of(block).strip() == "select public.list_industry_median(p_pnu)"

    @pytest.mark.parametrize("name", ("snap", "me", "hit"))
    def test_snap_me_hit_are_the_sibling_text(self, schema, name):
        """형제와 다른 분기·다른 상권을 말하면 같은 카드 안에서 막대와 비교 글이 서로 다른 것을 센다."""
        assert cte(body_of(fn_block(schema, LIST_FN)), name) == cte(body_of(fn_block(schema, SIBLING_FN)), name)

    def test_response_keys_are_in_the_body(self, mig):
        body = statements(body_of(fn_block(mig, LIST_FN)))
        for key in RESPONSE_KEYS:
            assert key in body, key
        # 반경 비교는 없다(결정) — radius 칸을 내지 않는다.
        assert "radius" not in body

    def test_cast_and_no_store_name(self, mig):
        body = statements(body_of(fn_block(mig, LIST_FN)))
        assert "p_pnu::char(19)" in body
        assert "biz_name" not in body

    def test_population_is_chosen_by_count_type_first(self, mig):
        """종류(type) 묶음이 min_pop 이상이면 그것, 아니면 시·도 전체(all) — 이름이 아니라 수로 가른다."""
        body = statements(body_of(fn_block(mig, LIST_FN)))
        assert "and t.pop_n >= (select min_pop from lim)" in body
        assert "order by (t.scope = 'type') desc" in body
        assert "where hd.total >= (select min_total from lim)" in body
        # 30곳 미만 상권은 pop null 줄로 남고, 모집단을 못 고른 상권(낡은 표)은 줄을 아예 안 낸다.
        assert "where hd.total < (select min_total from lim) or p.district_id is not null" in body

    def test_no_region_names_in_sql(self, mig):
        assert region_names(mv_block(mig, MV)) == []
        assert region_names(fn_block(mig, LIST_FN)) == []

    @pytest.mark.parametrize("bad", ("select '서울' as nm", "SELECT 'Seoul'", "case when x = '11' then '대전' end"))
    def test_region_detector_catches(self, bad):
        assert region_names(bad)


class TestPermissions:
    def test_only_the_api_twin_is_granted(self, mig, schema):
        assert grant_targets(mig) == [API_FN]
        # 중분류 형제(2026-10-13a · api.list_industry_median_m)는 이름 끝으로 가른다 — 그쪽은 test_industry_median_m_migration.
        assert [t for t in grant_targets(schema) if t.endswith("industry_median")] == [API_FN]

    @pytest.mark.parametrize("bad", (
        "grant execute on function list_industry_median(text) to anon;",
        "grant all on function public.list_industry_median(text) to anon;",
        "  GRANT EXECUTE\n  ON FUNCTION list_industry_median ( text ) TO authenticated;",
    ))
    def test_grant_detector_catches_the_public_original(self, mig, bad):
        """양성 대조 — public 원본에 grant 를 주는 사본이 걸린다(흔한 꼴 + 들여쓴·대문자 변형 꼴)."""
        found = grant_targets(mig + "\n" + bad + "\n")
        assert [t for t in found if t != API_FN], found

    @pytest.mark.parametrize("name", ("list_industry_median(text)", "api.list_industry_median(text)"))
    def test_every_function_is_revoked_with_anon_named(self, mig, name):
        assert re.search(r"(?m)^revoke all on function " + re.escape(name)
                         + r" from public, anon, authenticated;", statements(mig)), name

    def test_revoke_before_grant(self, mig, schema):
        for sql in (mig, schema):
            code = statements(sql)
            assert (code.index("revoke all on function api.list_industry_median(")
                    < code.index("grant execute on function api.list_industry_median("))

    def test_allowlist_has_the_api_twin_only(self):
        assert API_FN in post_load.ANON_CALLABLE_ALLOWLIST
        assert LIST_FN not in post_load.ANON_CALLABLE_ALLOWLIST
        assert not [n for n in post_load.ANON_READABLE_ALLOWLIST if MV in n]
        assert not [n for n in post_load.ANON_CALLABLE_ALLOWLIST if MV in n]


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
        for piece in ("drop function api.list_industry_median(text)", "drop function list_industry_median(text)",
                      "drop materialized view mv_industry_mix_median"):
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

P_GOL = "1168010100100010000"     # 골목 G31 + 작은 골목 S1(점포 20) 안
P_TOUR = "1168010100100020000"    # 관광특구 T1 안(종류 2곳 → 서울 전체로)
P_NOGEOM = "1168010100100030000"  # 좌표 없음
P_DJ = "3011010100100010000"      # 대전 D1 안(시·도 모집단 1곳 < 30 → 줄 없음)

# 골목 31곳(점포 100곳씩): 음식 = 1~15번은 0곳, 16~31번은 10~25곳 · 나머지는 소매.
#   → 음식 비중(0 포함) 31개를 세우면 16번째 = 10% · 0 을 빼면 10~25 의 가운데 = 17.5%.
# 관광특구 2곳(음식 50 · 소매 50) · 작은 골목 1곳(음식 20 — 30곳 미만이라 모집단 밖) · 대전 1곳(음식 40).
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
  ('D1', '대전상권', '주요상권', '소상공인시장진흥공단 주요상권', 700, '30110', '|PD|D1|');
insert into unit_business (snapshot_ym, cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, geom)
  select '202606', 'I2', '음식', 'I201', '한식', 'G' || lpad(i::text, 2, '0')
  from generate_series(1, 31) i, generate_series(1, 100) k
  where k <= case when i <= 15 then 0 else i - 6 end;
insert into unit_business (snapshot_ym, cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, geom)
  select '202606', 'G2', '소매', 'G204', '종합 소매', 'G' || lpad(i::text, 2, '0')
  from generate_series(1, 31) i, generate_series(1, 100) k
  where k <= 100 - case when i <= 15 then 0 else i - 6 end;
insert into unit_business (snapshot_ym, cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, geom)
  select '202606', c.cd, c.nm, c.m, c.mn, t.g
  from (values ('T1'), ('T2')) t(g),
       (values ('I2', '음식', 'I201', '한식'), ('G2', '소매', 'G204', '종합 소매')) c(cd, nm, m, mn),
       generate_series(1, 50) k;
insert into unit_business (snapshot_ym, cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, geom)
  select '202606', 'I2', '음식', 'I201', '한식', 'S1' from generate_series(1, 20) k;
insert into unit_business (snapshot_ym, cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, geom)
  select '202606', 'I2', '음식', 'I201', '한식', 'D1' from generate_series(1, 40) k;
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
    c.execute(re.search(r"(?ms)^create unique index if not exists mv_industry_mix_median_key\n.*?;", mig).group(0))
    c.execute(fn_block(mig, LIST_FN))
    return c


def _call(cur, pnu):
    cur.execute("select list_industry_median(%s)", (pnu,))
    return cur.fetchone()[0]


def _row(cur, sido, scope, dtype, cat):
    cur.execute("select pop_n, med_pct::text from mv_industry_mix_median "
                "where sido_cd = %s and scope = %s and district_type = %s and cat_l_cd = %s",
                (sido, scope, dtype, cat))
    return cur.fetchone()


class TestRealRun:
    def test_zero_is_counted_in_the_median(self, cur):
        """0 포함 가운데값 = 10.0 — 0 을 빼고 세면 17.5 가 된다(드문 업종이 부푸는 병)."""
        assert _row(cur, "11", "type", "골목상권", "I2") == (31, "10.0")
        assert _row(cur, "11", "type", "골목상권", "G2") == (31, "90.0")

    def test_small_district_is_outside_the_population(self, cur):
        """점포 20곳 상권(S1)은 모집단 밖 — 골목 31곳 · 서울 전체 33곳(골목 31 + 관광특구 2)."""
        assert _row(cur, "11", "type", "관광특구", "I2") == (2, "50.0")
        assert _row(cur, "11", "all", "", "I2") == (33, "11.0")
        assert _row(cur, "11", "all", "", "G2") == (33, "89.0")
        assert _row(cur, "30", "type", "주요상권", "I2") == (1, "100.0")

    def test_one_quarter_and_unique_shape(self, cur):
        cur.execute("select distinct snapshot_ym from mv_industry_mix_median")
        assert [r[0] for r in cur.fetchall()] == ["202606"], "업종 표의 분기 하나만 — 옛 분기 숙박은 안 든다"
        cur.execute("select count(*) from mv_industry_mix_median where district_type is null")
        assert cur.fetchone()[0] == 0, "종류 칸은 null 이 아니라 빈 글자"
        cur.execute("select count(*) from mv_industry_mix_median where cat_l_cd = 'I1'")
        assert cur.fetchone()[0] == 0

    def test_same_type_population_when_it_has_30(self, cur):
        got = _call(cur, P_GOL)
        assert got["snapshot_ym"] == "202606" and got["min_total"] == 30 and got["min_pop"] == 30
        assert "radius" not in got
        # 좁은 상권 먼저 — S1(500㎡)이 점포 20곳이라 pop null · cats [].
        assert got["districts"][0] == {"district_id": "S1", "type": "골목상권", "total": 20, "pop": None, "cats": []}
        g31 = got["districts"][1]
        assert g31["district_id"] == "G31" and g31["total"] == 100 and g31["type"] == "골목상권"
        assert g31["pop"] == {"scope": "type", "sido_cd": "11", "district_type": "골목상권", "n": 31}
        assert g31["cats"] == [{"cd": "G2", "nm": "소매", "med_pct": 90.0},
                               {"cd": "I2", "nm": "음식", "med_pct": 10.0}]
        assert len(got["districts"]) == 2

    def test_small_type_falls_back_to_the_whole_sido(self, cur):
        """관광특구 2곳(< 30) → 서울 상권 전체 33곳 · district_type null."""
        got = _call(cur, P_TOUR)
        [t1] = got["districts"]
        assert t1["pop"] == {"scope": "all", "sido_cd": "11", "district_type": None, "n": 33}
        assert t1["cats"] == [{"cd": "G2", "nm": "소매", "med_pct": 89.0},
                              {"cd": "I2", "nm": "음식", "med_pct": 11.0}]

    def test_no_population_of_30_drops_the_row_not_says_too_small(self, cur):
        """대전 1곳뿐(시·도 전체도 < 30) — '30곳이 안 돼'(pop null)라고 잘못 말하지 않게 줄을 아예 안 낸다."""
        assert _call(cur, P_DJ)["districts"] == []

    def test_no_coord_is_empty(self, cur):
        got = _call(cur, P_NOGEOM)
        assert got["districts"] == [] and got["min_total"] == 30

    def test_post_load_consistency_sql_runs_and_agrees(self, cur):
        """post_load --check 의 모집단 대조 문장을 진짜 PostgreSQL 에 — 같은 판에서 어긋남 0(서울 33 · 대전 1)."""
        cur.execute("set search_path to public")
        cur.execute(post_load.INDUSTRY_MEDIAN_CONSISTENCY_SQL)
        got = tuple(cur.fetchone()[0].split("|"))
        assert got == ("0", "2", "2")
        assert post_load.judge_industry_median_consistency(*got) is False
        cur.execute(post_load.INDUSTRY_MEDIAN_FRESHNESS_SQL)
        assert cur.fetchone()[0] == "202606|202606"

    @pytest.mark.parametrize("mix_rows, median_rows, want", [
        # 업종 표에 두 분기가 섞인 적재 중(202606 + 202609) — 가운데값 표 분기(202606)만 센다 → 어긋남 0.
        # (분기로 안 나누면 상권이 두 번 세어져 서울 2곳 ≠ 1곳 — [낡음] 오탐.)
        ([("A", "202606", 40), ("B", "202606", 20), ("A", "202609", 40), ("C", "202609", 50)],
         [("202606", "11", "all", 1)],
         ("0", "1", "1")),
        # 같은 분기인데 모집단 수가 다르면 잡는다.
        ([("A", "202606", 40), ("C", "202606", 50)],
         [("202606", "11", "all", 1)],
         ("1", "1", "1")),
        # 두 표 다 빔 = 새 환경.
        ([], [], ("0", "0", "0")),
    ])
    def test_post_load_consistency_sql_on_hand_made_tables(self, pg, mix_rows, median_rows, want):
        """모집단 대조 문장을 손으로 만든 표에 — 요약표에는 행을 못 넣으므로 같은 이름의 표를 다른 스키마에 둔다."""
        c = pg.cursor()
        c.execute("drop schema if exists median_case cascade; create schema median_case;"
                  " set search_path to median_case;"
                  " create table mv_district_industry_mix (district_id text, snapshot_ym char(6), n int);"
                  " create table mv_industry_mix_median (snapshot_ym char(6), sido_cd text, scope text, pop_n int);"
                  " create table district (district_id text, sigungu_code char(5));"
                  " insert into district values ('A', '11680'), ('B', '11680'), ('C', '11140');")
        try:
            c.executemany("insert into mv_district_industry_mix values (%s, %s, %s)", mix_rows)
            c.executemany("insert into mv_industry_mix_median values (%s, %s, %s, %s)", median_rows)
            c.execute(post_load.INDUSTRY_MEDIAN_CONSISTENCY_SQL)
            got = tuple(c.fetchone()[0].split("|"))
        finally:
            c.execute("reset search_path; drop schema median_case cascade;")
        assert got == want
        assert post_load.judge_industry_median_consistency(*got) is (got[0] != "0")

    def test_post_load_recompute_sql_agrees_on_the_canonical_board(self, cur):
        """--check 의 값 다시 세기(순번으로 가운데 고르기)를 정본 정의로 구운 흉내 판에 — 어긋남 0 · 줄 수 같음.
        (순번을 cnt/2 하나로 줄이면 골목 31곳 음식이 15번째 0% 를 골라 10.0 과 갈린다.)"""
        cur.execute("set search_path to public")
        cur.execute("select count(*) from mv_industry_mix_median")
        n = str(cur.fetchone()[0])
        cur.execute(post_load.INDUSTRY_MEDIAN_RECOMPUTE_SQL)
        got = tuple(cur.fetchone()[0].split("|"))
        assert n != "0" and got == ("0", n, n)
        assert post_load.judge_industry_median_recompute(*got) is False

    # 손으로 만든 사본 — 요약표에는 행을 못 고치므로 같은 이름의 보통 표를 다른 스키마에 둔다.
    # (재료 업종 표·district 도 같이 베껴 와 search_path 하나로 셋 다 사본을 보게 한다.)
    _ZERO_EXCLUDED = """
        update mv_industry_mix_median m set med_pct = s.med
        from (select x.snapshot_ym, left(d.sigungu_code, 2) as sido_cd, coalesce(d.district_type, '') as dt,
                     x.cat_l_cd,
                     round((percentile_cont(0.5) within group (order by x.n::float8 / t.total) * 100)::numeric, 1)
                       as med
              from (select district_id, snapshot_ym, sum(n) as total from mv_district_industry_mix
                    group by 1, 2 having sum(n) >= 30) t
              join district d using (district_id)
              join (select district_id, snapshot_ym, cat_l_cd, sum(n) as n from mv_district_industry_mix
                    group by 1, 2, 3) x using (district_id, snapshot_ym)
              group by grouping sets ((1, 2, 3, 4), (1, 2, 4))) s
        where m.snapshot_ym = s.snapshot_ym and m.sido_cd = s.sido_cd and m.cat_l_cd = s.cat_l_cd
          and ((m.scope = 'type' and s.dt is not null and m.district_type = s.dt)
               or (m.scope = 'all' and s.dt is null));
    """

    @pytest.mark.parametrize("tamper, want", [
        # ② 양성 대조 — 한 줄을 0.2 틀리게(반올림 한 칸 넘게). 허용 오차를 1.0 으로 늘리면 놓친다.
        ("update mv_industry_mix_median set med_pct = med_pct + 0.2"
         " where scope = 'type' and district_type = '골목상권' and cat_l_cd = 'I2'", ("1", 0, 0)),
        # 모집단 수만 틀린 줄도.
        ("update mv_industry_mix_median set pop_n = pop_n + 1"
         " where scope = 'all' and sido_cd = '11' and cat_l_cd = 'G2'", ("1", 0, 0)),
        # ③ 정의 갈림 — 없는 업종을 빼고(0 미포함) 센 값으로 구웠다: 골목 음식 10.0 → 17.5 · 서울 전체 음식 11.0 → 18.5.
        (_ZERO_EXCLUDED, ("2", 0, 0)),
        # ④ 한쪽에만 있는 줄 — 표에서 한 줄이 빠졌다(inner join 으로 바꾸면 놓친다).
        ("delete from mv_industry_mix_median where scope = 'all' and sido_cd = '11' and cat_l_cd = 'G2'",
         ("1", -1, 0)),
        # ④ 표에만 있는 줄 — 재료에 없는 업종.
        ("insert into mv_industry_mix_median (snapshot_ym, sido_cd, scope, district_type, pop_n, cat_l_cd,"
         " cat_l_nm, med_pct) values ('202606', '11', 'all', '', 33, 'Z9', 'x', 1.0)", ("1", 1, 0)),
    ])
    def test_post_load_recompute_sql_catches_tampered_copies(self, pg, cur, tamper, want):
        c = pg.cursor()
        c.execute("drop schema if exists median_re cascade; create schema median_re;"
                  " create table median_re.mv_district_industry_mix as select * from public.mv_district_industry_mix;"
                  " create table median_re.district as select * from public.district;"
                  " create table median_re.mv_industry_mix_median as select * from public.mv_industry_mix_median;"
                  " set search_path to median_re;")
        try:
            c.execute("select count(*) from mv_industry_mix_median")
            n = c.fetchone()[0]
            c.execute(post_load.INDUSTRY_MEDIAN_RECOMPUTE_SQL)
            assert c.fetchone()[0] == "0|{0}|{0}".format(n), "손대기 전 사본은 어긋남 0 이어야 한다"
            c.execute(tamper)
            if tamper is self._ZERO_EXCLUDED:
                c.execute("select med_pct::text from mv_industry_mix_median where cat_l_cd = 'I2' and sido_cd = '11'"
                          " and scope in ('type', 'all') and district_type in ('골목상권', '') order by scope")
                assert [r[0] for r in c.fetchall()] == ["18.5", "17.5"], "0 을 빼면 부푼다(정의 갈림 흉내 확인)"
            c.execute(post_load.INDUSTRY_MEDIAN_RECOMPUTE_SQL)
            got = tuple(c.fetchone()[0].split("|"))
        finally:
            c.execute("reset search_path; drop schema median_re cascade;")
        bad, d_med, d_re = want
        assert got == (bad, str(n + d_med), str(n + d_re))
        assert post_load.judge_industry_median_recompute(*got) is True

    # 정상 판을 새로 굽는다 — 재료 사본에 상권을 더한 뒤 마이그레이션의 요약표 정의를 그대로 실행한다.
    _NULL_SIDO = """
        insert into district (district_id, district_type, sigungu_code) values ('N1', '골목상권', null);
        insert into mv_district_industry_mix values ('N1', '202606', 'I2', '음식', 'I201', '한식', 25),
                                                    ('N1', '202606', 'G2', '소매', 'G204', '종합 소매', 15);
    """
    # 부산(26) 상권 셋 — 음식 비중 10/30 · 11/30 · 13/30 → 가운데 36.666…% 를 표는 36.7 로 반올림한다.
    # 정상 판인데 두 계산법 차이가 0 보다 크고 0.051 미만 — 허용 오차를 0 으로 좁히면 거짓 [낡음].
    _ROUGH_MEDIAN = """
        insert into district (district_id, district_type, sigungu_code)
          values ('B1', '골목상권', '26110'), ('B2', '골목상권', '26110'), ('B3', '골목상권', '26110');
        insert into mv_district_industry_mix values
          ('B1', '202606', 'I2', '음식', 'I201', '한식', 10), ('B1', '202606', 'G2', '소매', 'G204', '종합 소매', 20),
          ('B2', '202606', 'I2', '음식', 'I201', '한식', 11), ('B2', '202606', 'G2', '소매', 'G204', '종합 소매', 19),
          ('B3', '202606', 'I2', '음식', 'I201', '한식', 13), ('B3', '202606', 'G2', '소매', 'G204', '종합 소매', 17);
    """
    # 대분류가 빈 점포 줄(운영 0 · 2026-10-12 마무리 검사관 🟡) — 요약표에 cat_l_cd null 줄이 생긴다.
    # 두 계산법 모두 대분류를 = 로 이어 그 줄 비중은 양쪽 다 0 이라 값은 맞고, 맞대기 열쇠만 null 을 짝지어야 한다.
    # 부산(26) 상권 셋 모두 빈 대분류 점포(15·17·19/35)가 있다 — 다시 세기의 sh 만 is not distinct from 으로
    # 바꾸면 가운데 48.6% 대 요약표 0 으로 갈려 빨강(빈 대분류가 소수인 판이면 가운데가 0 으로 남아 못 가른다).
    _NULL_CAT = """
        insert into district (district_id, district_type, sigungu_code)
          values ('C1', '골목상권', '26140'), ('C2', '골목상권', '26140'), ('C3', '골목상권', '26140');
        insert into mv_district_industry_mix values
          ('C1', '202606', 'I2', '음식', 'I201', '한식', 20), ('C1', '202606', null, null, null, null, 15),
          ('C2', '202606', 'I2', '음식', 'I201', '한식', 18), ('C2', '202606', null, null, null, null, 17),
          ('C3', '202606', 'I2', '음식', 'I201', '한식', 16), ('C3', '202606', null, null, null, null, 19);
    """

    @pytest.mark.parametrize("extra, check", [
        # ① 구 코드가 빈 상권(점포 40곳) — sido_cd null 줄도 짝을 찾아야 한다(using 이면 8|14|14 꼴 거짓 [낡음]).
        (_NULL_SIDO, "select count(*) from mv_industry_mix_median where sido_cd is null"),
        # ② 가운데값이 둥글지 않은 정상 판 — 차이가 0 < d < 0.051 인 줄이 실제로 있어야 이 경우가 뜻을 갖는다.
        (_ROUGH_MEDIAN, "select count(*) from mv_industry_mix_median where sido_cd = '26' and cat_l_cd = 'I2'"
                        " and med_pct = 36.7"),
        # ③ 대분류가 빈 줄 — 열쇠·줄 수 세기가 cat_l_cd 로 짝을 가르면 2k|n-k|n-k 꼴 거짓 [낡음](k = 빈 대분류 줄 수).
        (_NULL_CAT, "select count(*) from mv_industry_mix_median where cat_l_cd is null"),
    ], ids=["null-sido", "rough-median", "null-cat"])
    def test_post_load_recompute_sql_stays_green_on_freshly_baked_boards(self, pg, cur, extra, check):
        c = pg.cursor()
        c.execute("drop schema if exists median_bake cascade; create schema median_bake;"
                  " create table median_bake.mv_district_industry_mix as select * from public.mv_district_industry_mix;"
                  " create table median_bake.district as select * from public.district;"
                  " set search_path to median_bake;")
        try:
            c.execute(extra)
            c.execute(mv_block(read(MIGRATION), MV))
            c.execute(check)
            assert c.fetchone()[0] >= 1, "흉내 낸 경우가 요약표에 실제로 들어갔어야 한다"
            c.execute("select count(*) from mv_industry_mix_median")
            n = c.fetchone()[0]
            c.execute(post_load.INDUSTRY_MEDIAN_RECOMPUTE_SQL)
            got = c.fetchone()[0]
        finally:
            c.execute("reset search_path; drop schema median_bake cascade;")
        assert got == "0|{0}|{0}".format(n)
