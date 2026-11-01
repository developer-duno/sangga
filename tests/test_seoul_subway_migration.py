# -*- coding: utf-8 -*-
"""마이그레이션 *_seoul_subway.sql(서울 지하철 승하차 — 결정 0045 PR⑥)의 불변식.

두 겹으로 본다.

  ① 글자 가드(언제나 돈다 · CI 포함)
     · 정본(schema.sql) ↔ 마이그 **글자 대조**: 표 둘 덩어리(색인·comment·RLS·revoke 포함) · 함수 둘(머리 security definer·
       search_path·stable 까지) · comment · 신선도 함수 덩어리(머리·본문·comment·revoke)
     · 신선도 = SGIS 판(2026-11-01b) + 정한 갈래(18번 줄 · subway 규칙 · 서울시 세 줄 +6개월 · comment)만 — 그 밖의 차이는 빨강
     · 반경 = parcel.geom 점 + st_dwithin(geography, 500, false) · char(19) · grant 는 api 쌍둥이에만 · 표 둘 RLS·revoke
     · 기본키 = 원문 열쇠 (use_mm, ride_line_nm, ride_sttn_nm) · station_id FK(메인 결정 ⑥-1)
     · post_load 허용 총계 39 · ANALYZE_TABLES 둘 · 그물 6호 힌트 열쇠 = 정본 자료 이름
     · 덩어리: lock_timeout 이 begin 앞 · begin/commit 하나 · notify 는 commit 뒤 · 새 객체만
  ② 실행 가드(로컬 PostgreSQL 이 있을 때만 · CI 는 건너뛴다)
     ⓘ 이 PC 의 로컬 PostgreSQL 에는 PostGIS 가 없다(2026-11-02 실측) — 형제 시험처럼 흉내 판이다: 점 = 'lng lat' 글자 ·
       st_distance·st_dwithin·`<->` = 하버사인(구 반지름 6371008.8m — 진짜 미터라 500m·1,500m 단언이 뜻을 가진다).
       마이그를 **통째로** 돌리되 PostGIS 전용 글자 두 곳만 바꿔 끼운다(`geometry(Point, 4326)` → `geometry` ·
       `using gist` → `using btree` — 바꾼 자리 수를 단언한다). ⚠️ 진짜 gist·KNN 계획은 못 본다(운영 EXPLAIN 몫).
     status 다섯 · 묶음 합(두 호선 + 같은 역 두 원문 줄) · 하루 평균 = Σ÷Σ일수 · 빠진 달은 분모에도 없음 · 창 밖 달 제외 ·
     bins 여섯 · 거리순·상한 10 · 1.5km 안 가장 가까운 역 · 신선도 18 줄 · 11 줄 +6개월 · 1 줄 그대로 · 권한 · 두 번 적용 · 변이.

ⓘ 파일 이름의 날짜는 적용 예정일이다(메인이 적용 날에 맞춰 바꿀 수 있다) — 이름 끝 `_seoul_subway.sql` 로 찾는다.
ⓘ 도우미는 이 파일 안에서만 쓴다(시험 파일끼리 import 하지 않는 레포 관습).
"""

import datetime
import glob
import os
import re
import shutil
import socket
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS = os.path.join(ROOT, "supabase", "migrations")
FOUND = sorted(glob.glob(os.path.join(MIGRATIONS, "*_seoul_subway.sql")))
PREV_FRESH = (sorted(glob.glob(os.path.join(MIGRATIONS, "*_sgis_district_pop.sql")))
              or [os.path.join(MIGRATIONS, "(없음)_sgis_district_pop.sql")])[-1]
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

for _p in (os.path.join(ROOT, "scripts"), os.path.join(ROOT, "scripts", "collectors")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import check_data_freshness as cdf  # noqa: E402
import post_load  # noqa: E402

TABLES = ("subway_station", "subway_ridership_m")
FN = "list_nearby_subway"
API_FN = "api." + FN
SIG = "(text)"
SRC = "지하철 승하차 (서울시)"
RETURNS = ("status", "group_id", "station_nm", "lines", "lines_with_data", "dist_m", "has_data", "window_from",
           "window_to", "months_n", "on_daily", "off_daily", "bins", "nearest_nm", "nearest_lines", "nearest_dist_m")
BIN_KEYS = ("h04_07", "h07_10", "h10_14", "h14_17", "h17_21", "h21_04")
HOURS = tuple(range(4, 24)) + (0, 1, 2, 3)

OLD_LAST_ROW = ("           'sgis',\n"
                "           '연 1회 (사람이 SGIS 자료제공에서 신청해 받음)'\n")
ROW18 = ("    union all\n"
         "    -- 2026-11-02a(결정 0045 PR⑥) — 서울시 지하철 승하차의 기준월(표 전체 max(use_mm) — 기본키 첫 칸이 받친다).\n"
         "    --   서울시가 매달 5일 무렵 전월분을 게시한다 — 기준월 + 2개월의 5일(규칙 'subway'). 표가 비면 basis null(화면 '자료 없음').\n"
         "    select 18, '지하철 승하차 (서울시)', '기준월',\n"
         "           (select max(t.use_mm)::text from subway_ridership_m t),\n"
         "           'subway',\n"
         "           '매달 (서울시가 다음 달 5일 무렵 전월분 게시)'\n")
OLD_Q = ("           -- 분기 자료: 다음 분기가 **공개되는 달**의 말일(분기말 + 5개월 - 하루).\n"
         "           when n.q_ym is not null\n")
NEW_Q = ("           -- 서울시 상권분석서비스 분기 자료(개업·폐업·추정매출·길단위인구 — 'seoul_openclose'): 분기말 + 6개월 - 하루\n"
         "           --   (👤 2026-11-02 「가」 · 2026-11-02a — 서울시 안내문 「1분기 5월 말 · 2분기 8월 말 · 3분기 11월 말 ·\n"
         "           --   4분기 다음 해 2월 말」 게시). 아래 일반 분기 갈래보다 **앞**에 둔다(case 는 위에서부터 고른다).\n"
         "           when n.q_ym is not null and n.rule_kind = 'seoul_openclose'\n"
         "             then (to_date(n.q_ym, 'YYYYMM') + interval '6 months' - interval '1 day')::date\n"
         "           -- 분기 자료(상권정보 · 부동산원 · 가게 이력): 다음 분기가 **공개되는 달**의 말일(분기말 + 5개월 - 하루).\n"
         "           when n.q_ym is not null\n")
RULE_END = ("           when n.rule_kind = 'sgis' and n.basis ~ '^\\d{4}-\\d{2}-\\d{2}$'\n"
            "             then (n.basis::date + interval '12 months')::date\n")
RULE18 = ("           -- 지하철 승하차(서울시): 기준월 + 2개월의 5일(서울시가 매달 5일 무렵 전월분 게시 — 2026-11-02a · 결정 0045 PR⑥).\n"
          "           --   'YYYYMM' 일 때만 — 모양이 다르면 to_date 가 터져 표가 통째로 사라진다.\n"
          "           when n.rule_kind = 'subway' and n.basis ~ '^\\d{4}(0[1-9]|1[0-2])$'\n"
          "             then (to_date(n.basis, 'YYYYMM') + interval '2 months' + interval '4 days')::date\n")
FRESH_CHANGES = (
    (OLD_LAST_ROW + "  ),", OLD_LAST_ROW + ROW18 + "  ),"),
    ("    --   같은 규칙(seoul_openclose — 분기말 + 5개월 - 하루)을 쓴다.\n",
     "    --   같은 규칙(seoul_openclose — 분기말 + 6개월 - 하루 · 👤 2026-11-02 「가」 · 2026-11-02a 부터)을 쓴다.\n"),
    (OLD_Q, NEW_Q),
    (RULE_END, RULE_END + RULE18),
    ("열여섯 갈래 자료의 가장 최근 도장", "열일곱 갈래 자료의 가장 최근 도장"),
    ("(열여섯 표가 전부 anon", "(열일곱 표가 전부 anon"),
    ("집계 도장 열여섯 개뿐", "집계 도장 열일곱 개뿐"),
    ("  '분기 자료는 분기말 달 + 5개월 - 하루(다음 분기가 공개되는 달의 말일 — 분기 꼴 셋 '\n",
     "  '분기 자료는 분기말 달 + 5개월 - 하루(다음 분기가 공개되는 달의 말일 · 서울시 상권분석서비스 분기 자료는 + 6개월 - 하루 "
     "— 분기 꼴 셋 '\n"),
    ("SGIS 상권 인구는 받은 날 + 12개월(연 1회 · 같은 모양일 때만). '\n",
     "SGIS 상권 인구는 받은 날 + 12개월(연 1회 · 같은 모양일 때만), 지하철 승하차(서울시)는 기준월 + 2개월의 5일"
     "(매달 · YYYYMM 일 때만). '\n"),
    ("  '개업·폐업과 같은 분기 규칙이고, 서울 상권 상주·직장인구는",
     "  '개업·폐업과 같은 분기 규칙(분기말 + 6개월 - 하루 — 서울시 안내문의 게시 달 말일)이고, 서울 상권 상주·직장인구는"),
    ("· SGIS 상권 인구 2026-11-01b(결정 0045 PR⑤)';",
     "· SGIS 상권 인구 2026-11-01b(결정 0045 PR⑤) · 지하철 승하차·서울시 세 줄 + 6개월 2026-11-02a(결정 0045 PR⑥)';"),
)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


@pytest.fixture(scope="module")
def mig():
    assert len(FOUND) == 1, "*_seoul_subway.sql 마이그가 정확히 하나여야 합니다: {}".format(FOUND)
    return read(FOUND[0])


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


def statements(sql):
    """줄 전체 주석을 걷은 실제 문장만(주석으로 죽인 문장을 '있다'로 보지 않게)."""
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


def fn_block(sql, name):
    """`create or replace function <name>(` 부터 그 `$$;` 까지 — 줄머리 고정(api. 와 안 섞이게)."""
    m = re.search(r"(?ms)^create\s+or\s+replace\s+function\s+" + re.escape(name) + r"\s*\(.*?\$\$\s*;", sql)
    assert m, "{} 의 정의를 못 찾았습니다".format(name)
    return m.group(0)


def head_of(block):
    return block[: block.index("$$")]


def body_of(block):
    return block.split("$$")[1]


def fn_comment(sql):
    m = re.search(r"(?ms)^comment\s+on\s+function\s+" + FN + r"\s*\(\s*text\s*\)\s+is.*?';\s*$", sql)
    assert m, "comment 를 못 찾았습니다"
    return m.group(0)


def table_block(sql, name):
    """`create table if not exists <name> (` 부터 그 표의 revoke 줄까지(색인·comment·RLS 포함)."""
    m = re.search(r"(?ms)^create\s+table\s+if\s+not\s+exists\s+" + re.escape(name) + r"\s*\(.*?"
                  r"^revoke\s+all\s+on\s+" + re.escape(name) + r"\s+from[^\n]*;", sql)
    assert m, "{} 표 덩어리를 못 찾았습니다".format(name)
    return m.group(0)


def fresh_block(sql):
    m = re.search(r"(?ms)^create\s+or\s+replace\s+function\s+get_data_freshness\s*\(\).*?"
                  r"^revoke\s+all\s+on\s+function\s+get_data_freshness\s*\(\)[^\n]*;", sql)
    assert m, "신선도 함수 덩어리를 못 찾았습니다"
    return m.group(0)


def code_lines(text):
    """주석(`--` 뒤)을 걷고 빈 줄을 뺀 줄 목록."""
    out = []
    for ln in text.splitlines():
        ln = re.sub(r"--.*$", "", ln).rstrip()
        if ln.strip():
            out.append(ln)
    return out


def grant_targets(sql):
    """`grant … on function <대상>(` 의 대상 이름 전부(소문자 · 스키마 그대로) — 회수는 안 센다."""
    found = []
    for stmt in re.findall(r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*?\bon\s+(?:function|routine)\b([^;]*)",
                           statements(sql)):
        found += re.findall(r"(?i)(?<![\w.])((?:\w+\.)?\w+)\s*\(", stmt)
    return [t.lower() for t in found]


def fresh_derived_problems(new_block, old_block):
    """새 덩어리 = 11-01b 덩어리 + 정한 갈래인가 — 문제 문장 목록.

    못 보는 것: 정한 갈래 안 글자를 바꾼 꼴은 '다름'으로만 잡힌다(어디가 다른지는 안 짚는다).
    """
    want, bad = old_block, []
    for a, b in FRESH_CHANGES:
        if want.count(a) != 1:
            bad.append("옛 덩어리에서 갈래 앞글을 한 번 찾지 못함: " + a.splitlines()[0])
            continue
        want = want.replace(a, b, 1)
    if new_block != want:
        bad.append("2026-11-01b 판 + 정한 갈래와 글자가 다릅니다")
    return bad


# ── ① 글자 가드 ─────────────────────────────────────────────────────────────


class TestMirrorsTheSchema:
    @pytest.mark.parametrize("name", TABLES)
    def test_table_blocks(self, mig, schema, name):
        assert table_block(mig, name) == table_block(schema, name)

    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_function_head_and_body(self, mig, schema, name):
        assert fn_block(mig, name) == fn_block(schema, name)

    def test_comment(self, mig, schema):
        assert fn_comment(mig) == fn_comment(schema)

    def test_freshness_block(self, mig, schema):
        assert fresh_block(mig) == fresh_block(schema)

    def test_mirror_detector_sees_a_head_only_change(self, mig, schema):
        bad = schema.replace(fn_block(schema, FN), fn_block(schema, FN).replace("set search_path = public\n", "", 1), 1)
        assert fn_block(mig, FN) != fn_block(bad, FN)

    def test_tables_come_before_the_freshness_function_in_schema(self, schema):
        at = schema.index("create or replace function get_data_freshness()")
        for t in TABLES:
            assert schema.index("create table if not exists " + t + " (") < at


class TestHeadsAndReturns:
    def test_public_head(self, mig):
        lines = {ln.strip() for ln in head_of(fn_block(mig, FN)).splitlines()}
        for w in ("language sql", "stable", "security definer", "set search_path = public"):
            assert w in lines, w

    def test_api_head_and_pass_through(self, mig):
        block = fn_block(mig, API_FN)
        lines = {ln.strip() for ln in head_of(block).splitlines()}
        assert {"language sql", "stable", "security definer", "set search_path = ''"} <= lines
        assert "$$ select * from public.list_nearby_subway(p_pnu) $$;" in block

    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_signature_and_returned_columns(self, mig, name):
        block = fn_block(mig, name)
        assert "function {}(p_pnu text)".format(name) in block
        m = re.search(r"(?is)returns\s+table\s*\((.*?)\)\s*language", block)
        assert tuple(ln.split()[0] for ln in m.group(1).splitlines() if ln.strip()) == RETURNS

    def test_one_signature_per_name(self, mig, schema):
        for name in (FN, API_FN):
            for sql in (mig, schema):
                assert len(re.findall(r"(?im)^\s*create\s+(?:or\s+replace\s+)?function\s+" + re.escape(name)
                                      + r"\s*\(", statements(sql))) == 1, name

    def test_pnu_cast(self, mig):
        body = body_of(fn_block(mig, FN))
        assert "p.pnu = p_pnu::char(19)" in body
        assert re.search(r"\bp\.pnu\s*=\s*p_pnu\s*(?:\)|and|$)", body, re.M) is None

    def test_radius_is_the_parcel_point_and_500m_on_the_sphere(self, mig):
        """함정 8 — parcel.geom 점만 · st_dwithin(geography, 500, false) · 거리도 같은 구(false)."""
        code = "\n".join(code_lines(body_of(fn_block(mig, FN))))
        assert "select p.geom::geography as gg\n    from parcel p" in code
        assert code.count("st_dwithin(") == 1
        assert "where st_dwithin(s.geom::geography, me.gg, 500, false)" in code
        assert re.findall(r"st_distance\(([^)]*)\)", code) == ["s.geom::geography, me.gg, false"] * 2
        assert "order by s.geom::geography <-> me.gg\n    limit 1" in code
        assert "where nr.d <= 1500" in code

    def test_status_order(self, mig):
        code = " ".join(" ".join(code_lines(body_of(fn_block(mig, FN)))).split())
        order = [code.index("then '{}'".format(s)) for s in ("no_coord", "not_seoul", "no_data", "no_station")]
        assert order == sorted(order)
        assert "left(p_pnu::char(19), 2) <> '11'" in code

    def test_window_and_daily_average_rules(self, mig):
        """창 = 표 max 기준 12개월 · 분모 = 그 묶음이 가진 달의 일수 합(월별 평균의 평균이 아니다)."""
        code = " ".join(" ".join(code_lines(body_of(fn_block(mig, FN)))).split())
        assert "to_char(to_date(max(r.use_mm), 'YYYYMM') - interval '11 months', 'YYYYMM') as from_mm" in code
        assert "where r.use_mm between w.from_mm and w.to_mm" in code
        assert "(select distinct x.group_id, x.use_mm from rides x) m" in code
        assert "round(a.on_s / dy.n_days)::int, round(a.off_s / dy.n_days)::int" in code
        assert "avg(" not in code

    def test_bins_are_the_six_keys_and_cover_24_hours_once(self, mig):
        code = " ".join(" ".join(code_lines(body_of(fn_block(mig, FN)))).split())
        assert re.findall(r"'(h\d\d_\d\d)', jsonb_build_object", code) == list(BIN_KEYS)
        for side in ("on", "off"):
            sums = re.findall(r"sum\(((?:x\.{0}_h\d\d(?: \+ )?)+)\)::numeric as {0}_\d".format(side), code)
            hours = [int(h) for s in sums for h in re.findall(r"_h(\d\d)", s)]
            assert sorted(hours) == sorted(HOURS) and len(hours) == 24, side

    def test_group_is_group_id_and_limit_10(self, mig):
        code = " ".join(" ".join(code_lines(body_of(fn_block(mig, FN)))).split())
        assert "select n.group_id, min(n.d) as d from near n group by n.group_id order by min(n.d), n.group_id limit 10" in code
        assert "from grp g join subway_station s on s.group_id = g.group_id" in code


class TestPermissions:
    def test_only_the_api_twin_is_granted(self, mig, schema):
        assert grant_targets(mig) == [API_FN]
        assert [t for t in grant_targets(schema) if t.endswith(FN)] == [API_FN]

    @pytest.mark.parametrize("bad", [
        "grant execute on function list_nearby_subway(text) to anon;",
        "  GRANT ALL\n  ON FUNCTION public.List_Nearby_Subway ( text ) TO authenticated;",
    ])
    def test_grant_detector_catches_the_public_original(self, mig, bad):
        assert [t for t in grant_targets(mig + "\n" + bad + "\n") if not t.startswith("api.")]

    @pytest.mark.parametrize("name", (FN, API_FN))
    def test_every_function_is_revoked_with_anon_named(self, mig, schema, name):
        for sql in (mig, schema):
            assert re.search(r"(?m)^revoke all on function " + re.escape(name + SIG)
                             + r" from public, anon, authenticated;", statements(sql)), name

    @pytest.mark.parametrize("name", TABLES)
    def test_tables_are_closed(self, mig, schema, name):
        for sql in (mig, schema):
            block = statements(table_block(sql, name))
            assert "alter table {} enable row level security;".format(name) in block
            assert "revoke all on {} from public, anon, authenticated;".format(name) in block
            assert not re.search(r"(?is)\bgrant\b[^;]*\bon\s+(?:table\s+)?(?:public\.)?" + name + r"\b",
                                 statements(sql))

    def test_post_load_allowlist_and_analyze(self):
        assert API_FN in post_load.ANON_CALLABLE_ALLOWLIST
        assert FN not in post_load.ANON_CALLABLE_ALLOWLIST and "public." + FN not in post_load.ANON_CALLABLE_ALLOWLIST
        for t in TABLES:
            assert t not in post_load.ANON_READABLE_ALLOWLIST
        assert len(post_load.ANON_READABLE_ALLOWLIST) + len(post_load.ANON_CALLABLE_ALLOWLIST) == 39
        assert set(TABLES) <= set(post_load.ANALYZE_TABLES)


class TestTablesShape:
    def test_station_table(self, mig):
        block = table_block(mig, "subway_station")
        assert re.search(r"(?m)^\s+station_id\s+text primary key,$", block)
        assert re.search(r"(?m)^\s+geom\s+geometry\(Point, 4326\) not null,$", block)
        assert re.search(r"(?m)^\s+has_ridership\s+boolean not null default false,$", block)
        assert "create index if not exists idx_subway_station_geog on subway_station using gist ((geom::geography));" \
            in block
        assert "create index if not exists idx_subway_station_group on subway_station (group_id);" in block

    def test_ridership_key_is_the_raw_key_and_station_is_a_plain_fk(self, mig):
        """메인 결정 ⑥-1 — 짝표 뒤 같은 역으로 원문 두 줄이 모인다 → 기본키 = 원문 열쇠 · station_id 는 유일 아님."""
        block = table_block(mig, "subway_ridership_m")
        assert "primary key (use_mm, ride_line_nm, ride_sttn_nm)," in block
        assert re.search(r"(?m)^\s+station_id\s+text not null references subway_station \(station_id\),$", block)
        assert not re.search(r"(?i)unique|primary key \(use_mm, station_id\)", "\n".join(code_lines(block)))
        assert "create index if not exists idx_subway_ridership_station on subway_ridership_m (station_id, use_mm);" \
            in block
        assert "check (use_mm ~ '^\\d{6}$')" in block and "check (on_sum >= 0 and off_sum >= 0)" in block

    def test_ridership_hour_columns_are_the_48(self, mig):
        block = table_block(mig, "subway_ridership_m")
        cols = re.findall(r"(?m)^\s+((?:on|off)_h\d\d)\s+integer not null,$", block)
        assert cols == ["on_h{:02d}".format(h) for h in HOURS] + ["off_h{:02d}".format(h) for h in HOURS]

    def test_loader_columns_match_the_table(self, mig):
        import load_seoul_subway as L  # noqa: PLC0415
        block = table_block(mig, "subway_ridership_m")
        for c in L.RIDE_COLUMNS:
            assert re.search(r"(?m)^\s+" + c + r"\s+", block), c
        st = table_block(mig, "subway_station")
        for c in L.STATION_COLUMNS:
            assert re.search(r"(?m)^\s+" + c + r"\s+", st), c


class TestFreshness:
    def test_new_block_is_the_old_block_plus_the_changes(self, mig):
        assert fresh_derived_problems(fresh_block(mig), fresh_block(read(PREV_FRESH))) == []

    @pytest.mark.parametrize("old,new", [
        ("subway_ridership_m t),\n           'subway',", "subway_ridership_m t),\n           'none',"),
        ("interval '6 months'", "interval '5 months'"),                    # 서울시 +6 을 +5 로 되돌림
        ("+ interval '4 days'", "+ interval '5 days'"),
        ("열일곱 갈래", "열여섯 갈래"),
    ])
    def test_detector_catches_variants(self, mig, old, new):
        block = fresh_block(mig)
        assert old in block
        assert fresh_derived_problems(block.replace(old, new, 1), fresh_block(read(PREV_FRESH)))

    def test_detector_catches_the_seoul_branch_moved_below(self, mig):
        """변형 — 서울시 갈래를 일반 분기 갈래 **뒤**로 옮기면(case 는 위부터 고른다) 걸린다."""
        block = fresh_block(mig)
        head = NEW_Q[: NEW_Q.index("           -- 분기 자료(상권정보")]
        tail = NEW_Q[len(head):]
        assert NEW_Q in block
        moved = block.replace(NEW_Q, tail + head, 1)
        assert fresh_derived_problems(moved, fresh_block(read(PREV_FRESH)))

    def test_eighteenth_row_and_one_new_rule_kind(self, mig):
        body = "\n".join(code_lines(body_of(fresh_block(mig))))
        assert body.count("union all") == 16
        assert re.search(r"select 18, '지하철 승하차 \(서울시\)', '기준월',\n\s+\(select max\(t\.use_mm\)::text from "
                         r"subway_ridership_m t\),\n\s+'subway',", body)
        assert body.count("interval '6 months'") == 1 and body.count("interval '5 months'") == 1
        assert body.count("interval '2 months'") == 2
        assert body.index("n.rule_kind = 'seoul_openclose'\n") < body.index("when n.q_ym is not null\n")

    def test_comment_says_seventeen_three_times(self, mig):
        m = re.search(r"(?ms)^comment\s+on\s+function\s+get_data_freshness\s*\(\)\s+is.*?';\s*$", mig)
        text = m.group(0)
        assert "열일곱 갈래" in text and "열일곱 표" in text and "집계 도장 열일곱 개" in text
        assert "열여섯" not in text
        assert "지하철 승하차(서울시)는 기준월 + 2개월의 5일" in text

    def test_api_twin_is_not_recreated(self, mig):
        assert not re.search(r"(?im)^\s*create\s+(?:or\s+replace\s+)?function\s+api\.get_data_freshness",
                             statements(mig))

    def test_hint_key_is_the_server_label(self, schema):
        assert "'{}'".format(SRC) in schema
        hint = cdf.SOURCE_HINTS[SRC]
        assert hint.index("collect_seoul_subway.py --dry-run --end-month") \
            < hint.index("load_seoul_subway.py --dry-run") < hint.index("post_load.py") < hint.index("backup_raw.py")


class TestMigrationShape:
    def test_settings_before_begin_and_notify_after_commit(self, mig):
        code = statements(mig)
        begin = re.search(r"(?m)^begin;", code).start()
        commit = re.search(r"(?m)^commit;", code).start()
        assert code.index("set lock_timeout = '5s';") < begin < commit < code.index("notify pgrst, 'reload schema';")
        assert len(re.findall(r"(?m)^begin;", code)) == 1 and len(re.findall(r"(?m)^commit;", code)) == 1
        for stmt in re.finditer(r"(?im)^(create|drop|alter|insert|revoke|grant|comment)\b", code):
            assert begin < stmt.start() < commit, "begin/commit 밖의 문장: " + stmt.group(0)

    def test_only_new_objects_and_the_freshness_function(self, mig):
        code = statements(mig)
        assert not re.search(r"(?im)^\s*(?:drop|insert|update|delete|truncate)\s", code)
        alters = re.findall(r"(?im)^alter\s+table\s+(\w+)\s+(.*);", code)
        assert alters == [(t, "enable row level security") for t in TABLES]
        made = re.findall(r"(?im)^create\s+(?:or\s+replace\s+)?(table|function|index)\s+(?:if\s+not\s+exists\s+)?([\w.]+)",
                          code)
        assert made == [("table", TABLES[0]), ("index", "idx_subway_station_geog"),
                        ("index", "idx_subway_station_group"), ("table", TABLES[1]),
                        ("index", "idx_subway_ridership_station"), ("function", FN), ("function", API_FN),
                        ("function", "get_data_freshness")]

    def test_rollback_and_order_paragraphs_are_written(self, mig):
        for s in ("되돌리기", "2026-11-01b_sgis_district_pop.sql", "drop function api.list_nearby_subway(text)",
                  "drop table subway_ridership_m", "drop table subway_station", "39 → 38",
                  "디스크 판정", "backup_raw.py", "그물 6호"):
            assert s in mig, s

    def test_no_banned_words(self, mig):
        for w in ("적정가격", "적정가", "감정가", "평가액", "가치평가"):
            assert w not in mig


# ── ② 실행 가드 (로컬 PostgreSQL 이 있을 때만) ──────────────────────────────

# PostGIS 흉내 — 점 = 'lng lat' 글자 · 거리 = 하버사인(구).
SHIM = r"""
create role anon;
create role authenticated;
create schema api;
create domain geometry as text;
create domain geography as text;
create function st_makepoint(x double precision, y double precision) returns text language sql immutable
  as $f$ select x::text || ' ' || y::text $f$;
create function st_setsrid(g text, srid integer) returns geometry language sql immutable as $f$ select g::geometry $f$;
create function shim_hav(a text, b text) returns double precision language sql immutable as $f$
  select 2 * 6371008.8 * asin(sqrt(
           power(sin(radians(split_part(b, ' ', 2)::float8 - split_part(a, ' ', 2)::float8) / 2), 2)
           + cos(radians(split_part(a, ' ', 2)::float8)) * cos(radians(split_part(b, ' ', 2)::float8))
             * power(sin(radians(split_part(b, ' ', 1)::float8 - split_part(a, ' ', 1)::float8) / 2), 2)))
$f$;
create function st_distance(a geography, b geography, s boolean) returns double precision language sql immutable
  as $f$ select shim_hav(a, b) $f$;
create function st_dwithin(a geography, b geography, r double precision, s boolean) returns boolean
  language sql immutable as $f$ select shim_hav(a, b) <= r $f$;
create operator <-> (leftarg = text, rightarg = text, function = shim_hav);
create table parcel (pnu char(19) primary key, geom geometry, land_price_year smallint);
-- get_data_freshness 가 읽는 나머지 표 — 그 함수가 만들어지고 돌 만큼만.
create table district (district_id text primary key, computed_at timestamptz);
create table snapshot_release (published_ym text);
create table transaction (contract_ym text);
create table ledger_release (release_ym text);
create table lh_notice (collected_at timestamptz);
create table arch_permit (loaded_ym text);
create table nts_base_price (notice_date date);
create table rent_stat (quarter char(6));
create table district_openclose (quarter text);
create table daejeon_closure_release (received_on date);
create table district_sales (quarter char(5));
create table district_pop_flow (quarter char(5));
create table seoul_trdar_release (tbl text, value_quarter char(5));
create table store_history_release (last_ym char(6));
create table sgis_census_release (received_on date);
insert into snapshot_release values ('202606');
insert into district_openclose values ('20262');
"""
# 마이그 안 PostGIS 전용 글자 → 흉내 판 글자(바꾼 자리 수를 단언한다).
POSTGIS_SWAPS = (("geometry(Point, 4326)", "geometry", 1), ("using gist", "using btree", 1))

P = "1114010100100010000"            # 서울 — (127.0, 37.5)
P_FAR = "1114010100100020000"        # 서울 — 500m 안 역 0 · 1.2km 에 D
P_LONELY = "1114010100100030000"     # 서울 — 1.5km 안 역도 없음
P_MANY = "1114010100100040000"       # 서울 — 500m 안 묶음 12
P_NOGEOM = "1114010100100050000"
DJ = "3020010100100010000"           # 대전 — 좌표는 P 와 같다(시·도로 가른다)
DJ_NOGEOM = "3020010100100020000"    # 대전 — 좌표 없음(no_coord 가 not_seoul 보다 먼저)
P_BINS = "1114010100100060000"       # 서울 — (126.8, 37.5) · 100m 에 시간역(24시간 서로 다른 값)
P_NAME = "1114010100100070000"       # 서울 — (126.6, 37.5) · 200m 에 잠실 묶음(이름 다른 두 역)

STATIONS = [
    # (id, 이름, 정규화, 호선, 묶음, lat, lng)
    ("0001", "충무로", "충무로", "3호선", 1, 37.5027, 127.0),          # P 에서 약 300m
    ("0002", "충무로", "충무로", "4호선", 1, 37.5027, 127.0005),       # 같은 역사(44m)
    ("0003", "신촌", "신촌", "2호선", 2, 37.4964, 127.0),              # 약 400m
    ("0004", "신촌", "신촌", "경의중앙선", 3, 37.4964, 127.009),        # 같은 이름 · 794m 밖 → 다른 묶음 · P 에서 889m
    ("0005", "양재시민의숲(매헌)", "양재시민의숲", "신분당선", 4, 37.5, 127.0051),   # 약 450m · 승하차 자료 없음
    ("0006", "멀리역", "멀리역", "1호선", 5, 37.5108, 127.1),           # P_FAR 에서 약 1,201m
] + [("{:04d}".format(100 + i), "고리{}".format(i), "고리{}".format(i), "2호선", 100 + i,
      37.5 + 0.00036 * (i + 1), 127.2) for i in range(12)]              # P_MANY 둘레 40m 간격 12묶음
STATIONS += [
    # 다른 탐침과 17km 넘게 떨어져 기존 결과(묶음 수·줄 수·no_station 의 가장 가까운 역)를 안 바꾼다.
    ("0020", "시간역", "시간역", "1호선", 200, 37.5009, 126.8),               # P_BINS 에서 약 100m
    ("0010", "잠실(송파구청)", "잠실", "2호선", 201, 37.5018, 126.6),        # P_NAME 에서 약 200m · id 가장 작음
    ("0011", "잠실", "잠실", "8호선", 201, 37.5018, 126.6005),               # 같은 묶음(44m) · 원문 이름이 다르다
]


def ride(ym, line, sttn, sid, ln, **hours):
    on = {h: 0 for h in HOURS}
    off = {h: 0 for h in HOURS}
    for k, v in hours.items():
        side, h = k.split("_")
        (on if side == "on" else off)[int(h)] = v
    cols = (["use_mm", "ride_line_nm", "ride_sttn_nm", "station_id", "line_nm", "on_sum", "off_sum"]
            + ["on_h{:02d}".format(h) for h in HOURS] + ["off_h{:02d}".format(h) for h in HOURS])
    vals = ([ym, line, sttn, sid, ln, sum(on.values()), sum(off.values())]
            + [on[h] for h in HOURS] + [off[h] for h in HOURS])
    return "insert into subway_ridership_m ({}) values ({});".format(
        ", ".join(cols), ", ".join("'{}'".format(v) if isinstance(v, str) else str(v) for v in vals))


DAYS = {"202607": 31, "202608": 31, "202609": 30}
RIDES = (
    # 충무로 3호선 — 하루 100(아침) · 하차 0(몰아 세기 꼴)
    [ride(m, "3호선", "충무로", "0001", "3호선", on_08=100 * d) for m, d in DAYS.items()]
    # 충무로 4호선 — 하루 승차 900(아침) · 하차 950(저녁)
    + [ride(m, "4호선", "충무로", "0002", "4호선", on_08=900 * d, off_18=950 * d) for m, d in DAYS.items()]
    # 같은 역(0002)에 원문 두 번째 줄(짝표 뒤 모인 꼴) — 202609 밤 승차 300
    + [ride("202609", "경원선", "충무로", "0002", "경원선", on_22=300)]
    # 창 밖 옛 달 — 빠져야 한다
    + [ride("202409", "3호선", "충무로", "0001", "3호선", on_08=99999)]
    # 신촌 2호선 — 202607 하루 100 · 202608 없음 · 202609 하루 200 → Σ÷Σ = 9100 ÷ 61 = 149(평균의 평균이면 150)
    + [ride("202607", "2호선", "신촌", "0003", "2호선", on_08=3100),
       ride("202609", "2호선", "신촌", "0003", "2호선", on_08=6000)]
    # 시간역 — 202609(30일) 24시간 전부 서로 다른 값: 하루 평균 승차 H+1 · 하차 25−H (H = 0~23)
    + [ride("202609", "1호선", "시간역", "0020", "1호선",
            **{"{}_{:02d}".format(s, h): v for h in range(24)
               for s, v in (("on", (h + 1) * 30), ("off", (25 - h) * 30))})]
    # 잠실 묶음 — 두 역 다 승하차 한 달
    + [ride("202609", "2호선", "잠실", "0010", "2호선", on_08=300),
       ride("202609", "8호선", "잠실", "0011", "8호선", on_08=600)]
)


def fixture_sql():
    out = ["insert into parcel (pnu, geom) values "
           "('{}', '127.0 37.5'), ('{}', '127.1 37.5'), ('{}', '127.5 37.5'), ('{}', '127.2 37.5'), ('{}', null), "
           "('{}', '127.0 37.5'), ('{}', null), ('{}', '126.8 37.5'), ('{}', '126.6 37.5');".format(
               P, P_FAR, P_LONELY, P_MANY, P_NOGEOM, DJ, DJ_NOGEOM, P_BINS, P_NAME)]
    for sid, nm, norm, ln, g, lat, lng in STATIONS:
        out.append("insert into subway_station (station_id, station_nm, name_norm, line_nm, group_id, lat, lng, geom) "
                   "values ('{}', '{}', '{}', '{}', {}, {}, {}, st_setsrid(st_makepoint({}, {}), 4326));".format(
                       sid, nm, norm, ln, g, lat, lng, lng, lat))
    return "\n".join(out + RIDES)


def shimmed(sql):
    for a, b, n in POSTGIS_SWAPS:
        assert sql.count(a) == n, a
        sql = sql.replace(a, b)
    return sql


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


def _fresh(conn, migration_sql=None, rows=True):
    """흉내 판을 새로 깔고 마이그 파일을 **통째로** 돌린 뒤 가짜 줄을 넣는다(rows=False 면 표 비움)."""
    cur = conn.cursor()
    cur.execute("drop schema if exists api cascade; drop schema if exists public cascade; create schema public;")
    cur.execute("drop role if exists anon; drop role if exists authenticated;")
    cur.execute(SHIM)
    cur.execute(shimmed(migration_sql or read(FOUND[0])))
    if rows:
        cur.execute(fixture_sql())
    return cur


def _call(cur, pnu):
    cur.execute("select * from api.list_nearby_subway(%s)", (pnu,))
    cols = [d[0] for d in cur.description]
    return cols, [dict(zip(cols, r)) for r in cur.fetchall()]


def _fresh_rows(cur):
    cur.execute("select src, basis_kind, basis, next_expected, cadence from get_data_freshness()")
    rows = cur.fetchall()
    assert len(rows) == 17
    return {r[0]: r[1:] for r in rows}


@pytest.fixture(scope="module")
def cur(pg):
    return _fresh(pg)


class TestRealRunFunction:
    def test_columns(self, cur):
        assert tuple(_call(cur, P)[0]) == RETURNS

    def test_groups_nearest_first_and_the_transfer_station_is_one_row(self, cur):
        _, rows = _call(cur, P)
        assert [(r["status"], r["station_nm"], r["dist_m"]) for r in rows] == [
            ("ok", "충무로", 300), ("ok", "신촌", 400), ("ok", "양재시민의숲(매헌)", 450)]
        assert all(r["nearest_nm"] is None for r in rows)

    def test_sums_two_lines_and_two_raw_rows_and_divides_by_days(self, cur):
        a = _call(cur, P)[1][0]
        assert a["lines"] == ["3호선", "4호선", "경원선"] and a["lines_with_data"] == ["3호선", "4호선", "경원선"]
        assert (a["has_data"], a["window_from"], a["window_to"], a["months_n"]) == (True, "202510", "202609", 3)
        # Σ승차 = 100·92 + 900·92 + 300 = 92,300 ÷ 92일 = 1,003 · 하차 = 950 · 창 밖 202409(99,999)는 안 든다.
        assert (a["on_daily"], a["off_daily"]) == (1003, 950)
        assert list(a["bins"]) == list(BIN_KEYS) or set(a["bins"]) == set(BIN_KEYS)
        assert a["bins"]["h07_10"] == {"on": 1000, "off": 0}
        assert a["bins"]["h17_21"] == {"on": 0, "off": 950}
        assert a["bins"]["h21_04"] == {"on": 3, "off": 0}
        assert a["bins"]["h04_07"] == a["bins"]["h10_14"] == a["bins"]["h14_17"] == {"on": 0, "off": 0}

    def test_missing_month_is_out_of_the_denominator(self, cur):
        """신촌 2호선 — 202608 이 없다: 9,100 ÷ (31 + 30) = 149 (평균의 평균 150 · 빠진 달까지 92일이면 99)."""
        b = _call(cur, P)[1][1]
        assert (b["months_n"], b["on_daily"], b["off_daily"]) == (2, 149, 0)
        # 같은 이름 신촌 경의중앙선(794m 밖 다른 묶음)은 이 줄 호선에 안 붙는다.
        assert b["lines"] == ["2호선"]

    def test_station_without_ridership_is_shown_without_numbers(self, cur):
        c = _call(cur, P)[1][2]
        assert (c["has_data"], c["months_n"], c["on_daily"], c["off_daily"], c["bins"]) == (False, 0, None, None, None)
        assert c["lines"] == ["신분당선"] and c["lines_with_data"] is None
        assert (c["window_from"], c["window_to"]) == ("202510", "202609")

    def test_at_most_ten_groups_nearest_first(self, cur):
        _, rows = _call(cur, P_MANY)
        assert len(rows) == 10
        assert [r["station_nm"] for r in rows] == ["고리{}".format(i) for i in range(10)]
        assert [r["dist_m"] for r in rows] == sorted(r["dist_m"] for r in rows)

    def test_no_station_names_the_nearest_within_1500m(self, cur):
        _, rows = _call(cur, P_FAR)
        assert len(rows) == 1
        r = rows[0]
        assert r["status"] == "no_station" and r["group_id"] is None and r["on_daily"] is None
        assert (r["nearest_nm"], r["nearest_lines"]) == ("멀리역", ["1호선"])
        assert 1195 <= r["nearest_dist_m"] <= 1205

    def test_no_station_beyond_1500m_names_nothing(self, cur):
        _, rows = _call(cur, P_LONELY)
        assert [(r["status"], r["nearest_nm"], r["nearest_lines"], r["nearest_dist_m"]) for r in rows] == \
            [("no_station", None, None, None)]

    def test_bins_follow_the_six_hour_ranges(self, cur):
        """24시간 전부 서로 다른 값 — 칸 경계(6시·3시 등)를 옮기면 그 칸이 바뀐다.
        배정은 👤 Q4 원문 「4~7·7~10·10~14·14~17·17~21·21~」(끝 시각은 그 칸에 안 든다)."""
        _, rows = _call(cur, P_BINS)
        assert [(r["status"], r["station_nm"]) for r in rows] == [("ok", "시간역")]
        b = rows[0]
        ranges = {"h04_07": (4, 5, 6), "h07_10": (7, 8, 9), "h10_14": (10, 11, 12, 13),
                  "h14_17": (14, 15, 16), "h17_21": (17, 18, 19, 20), "h21_04": (21, 22, 23, 0, 1, 2, 3)}
        want = {k: {"on": sum(h + 1 for h in hs), "off": sum(25 - h for h in hs)} for k, hs in ranges.items()}
        assert want["h04_07"] == {"on": 18, "off": 60} and want["h21_04"] == {"on": 79, "off": 103}
        assert b["bins"] == want
        assert (b["on_daily"], b["off_daily"]) == (sum(h + 1 for h in range(24)), sum(25 - h for h in range(24)))
        assert (b["on_daily"], b["off_daily"]) == (300, 324)

    def test_group_name_is_the_smallest_station_id(self, cur):
        """묶음 대표 이름 = station_id 가 가장 작은 역의 원문 이름(0010 「잠실(송파구청)」 · 0011 「잠실」)."""
        _, rows = _call(cur, P_NAME)
        assert len(rows) == 1
        r = rows[0]
        assert (r["status"], r["station_nm"]) == ("ok", "잠실(송파구청)")
        assert r["lines"] == ["2호선", "8호선"] and r["lines_with_data"] == ["2호선", "8호선"]
        assert (r["on_daily"], r["months_n"]) == (30, 1)

    @pytest.mark.parametrize("pnu,status", [(P_NOGEOM, "no_coord"), (DJ, "not_seoul"), (DJ_NOGEOM, "no_coord")])
    def test_building_level_status_is_one_row(self, cur, pnu, status):
        _, rows = _call(cur, pnu)
        assert [r["status"] for r in rows] == [status]
        assert all(rows[0][c] is None for c in RETURNS[1:])

    def test_unknown_pnu_is_no_coord(self, cur):
        assert [r["status"] for r in _call(cur, "1114010100199990000")[1]] == ["no_coord"]

    def test_empty_ridership_is_no_data(self, pg):
        c = _fresh(pg)
        try:
            c.execute("delete from subway_ridership_m")
            for p in (P, P_FAR, P_MANY):
                assert [r["status"] for r in _call(c, p)[1]] == ["no_data"], p
            assert [r["status"] for r in _call(c, DJ)[1]] == ["not_seoul"]
        finally:
            _fresh(pg)

    def test_empty_station_table_is_no_data(self, pg):
        c = _fresh(pg, rows=False)
        try:
            c.execute(fixture_sql().split("\n")[0])          # 필지만(역·승하차 0)
            assert [r["status"] for r in _call(c, P)[1]] == ["no_data"]
        finally:
            _fresh(pg)

    def test_fk_and_checks(self, pg):
        psycopg2 = pytest.importorskip("psycopg2")
        c = _fresh(pg)
        try:
            with pytest.raises(psycopg2.errors.ForeignKeyViolation):
                c.execute(ride("202609", "9호선", "없는역", "9999", "9호선", on_08=1))
            with pytest.raises(psycopg2.errors.CheckViolation):
                c.execute(ride("2026-9", "9호선", "강남", "0001", "9호선", on_08=1).replace("'2026-9'", "'20269 '"))
            with pytest.raises(psycopg2.errors.UniqueViolation):
                c.execute(ride("202609", "3호선", "충무로", "0001", "3호선", on_08=1))
            c.execute(ride("202609", "3호선", "충무로역", "0001", "3호선", on_08=1))   # 양성 대조 — 원문 열쇠가 다르면 들어간다
        finally:
            _fresh(pg)


class TestRealRunFreshness:
    def test_row18_due_month_plus_two_months_the_fifth(self, cur):
        kind, basis, nxt, cadence = _fresh_rows(cur)[SRC]
        assert (kind, basis, nxt) == ("기준월", "202609", datetime.date(2026, 11, 5))
        assert "매달" in cadence

    def test_seoul_rows_are_quarter_end_plus_six_months(self, cur):
        rows = _fresh_rows(cur)
        assert rows["상권 개업·폐업 (서울시)"][1:3] == ("20262", datetime.date(2026, 11, 30))
        assert rows["점포·업종 (상권정보)"][1:3] == ("202606", datetime.date(2026, 10, 31))

    @pytest.mark.parametrize("q,due", [("20261", (2026, 8, 31)), ("20262", (2026, 11, 30)),
                                       ("20263", (2027, 2, 28)), ("20264", (2027, 5, 31))])
    def test_seoul_quarters_match_the_city_notice(self, pg, q, due):
        """서울시 안내문 「1분기 5월 말 · 2분기 8월 말 · 3분기 11월 말 · 4분기 다음 해 2월 말」 — 기준 분기의 **다음** 분기."""
        c = _fresh(pg)
        try:
            c.execute("update district_openclose set quarter = %s", (q,))
            assert _fresh_rows(c)["상권 개업·폐업 (서울시)"][2] == datetime.date(*due)
        finally:
            _fresh(pg)

    def test_loading_last_month_is_not_overdue(self, pg):
        """적재 당일 안 지남 — 기준월 = 지난달(오늘 기준 · 하드코딩 0)이면 예정일이 오늘보다 뒤다."""
        today = datetime.date.today()
        last = (today.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y%m")
        c = _fresh(pg)
        try:
            c.execute(ride(last, "1호선", "멀리역", "0006", "1호선", on_08=1))
            nxt = _fresh_rows(c)[SRC][2]
            assert nxt is not None and nxt > today
        finally:
            _fresh(pg)

    def test_empty_table_keeps_the_row(self, pg):
        c = _fresh(pg, rows=False)
        try:
            assert _fresh_rows(c)[SRC][1:3] == (None, None)
        finally:
            _fresh(pg)

    @pytest.mark.parametrize("old,new,src,want", [
        ("subway_ridership_m t),\n           'subway',", "subway_ridership_m t),\n           'subwy',", SRC, None),
        ("+ interval '6 months' - interval '1 day'", "+ interval '5 months' - interval '1 day'",
         "상권 개업·폐업 (서울시)", datetime.date(2026, 10, 31)),
    ])
    def test_mutations_change_the_dates(self, pg, old, new, src, want):
        """양성 대조 — 갈래 이름을 틀리면 예정일 null · +6 을 +5 로 되돌리면 10-31(위 날짜 단언이 빨강)."""
        sql = read(FOUND[0])
        assert sql.count(old) == 1
        c = _fresh(pg, sql.replace(old, new, 1))
        try:
            assert _fresh_rows(c)[src][2] == want
        finally:
            _fresh(pg)


class TestRealRunPrivilegesAndReplay:
    def test_privileges(self, cur):
        for t in TABLES:
            cur.execute("select has_table_privilege('anon', %s, 'select'), "
                        "(select relrowsecurity from pg_class where relname = %s)", (t, t))
            assert cur.fetchone() == (False, True), t
        cur.execute("select has_function_privilege('anon', %s, 'execute'), "
                    "has_function_privilege('anon', %s, 'execute'), "
                    "has_function_privilege('authenticated', %s, 'execute')",
                    ("public." + FN + SIG, API_FN + SIG, API_FN + SIG))
        assert cur.fetchone() == (False, True, True)

    def test_twin_works_with_an_empty_search_path(self, cur):
        cur.execute("set search_path to ''")
        try:
            assert _call(cur, P)[1][0]["on_daily"] == 1003
        finally:
            cur.execute("reset search_path")

    def test_one_signature_per_name(self, cur):
        cur.execute("select n.nspname, count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                    "where p.proname = %s group by 1 order by 1", (FN,))
        assert cur.fetchall() == [("api", 1), ("public", 1)]

    def test_applying_twice_gives_the_same_answer(self, pg):
        c = _fresh(pg)
        try:
            before = (_call(c, P), _call(c, P_FAR), _fresh_rows(c))
            c.execute(shimmed(read(FOUND[0])))
            assert (_call(c, P), _call(c, P_FAR), _fresh_rows(c)) == before
        finally:
            _fresh(pg)

    def test_mutation_public_grant_opens_the_original(self, pg):
        """변이 — public 원본에도 grant 를 주면 anon 이 원본을 부를 수 있다(위 권한 단언이 빨강)."""
        line = "grant execute on function api.list_nearby_subway(text) to anon, authenticated;"
        sql = read(FOUND[0])
        assert sql.count(line) == 1
        c = _fresh(pg, sql.replace(line, line + "\ngrant execute on function list_nearby_subway(text) to anon;", 1))
        try:
            c.execute("select has_function_privilege('anon', 'public.list_nearby_subway(text)', 'execute')")
            assert c.fetchone() == (True,)
        finally:
            _fresh(pg)

    def test_mutation_radius_1000_pulls_in_the_far_same_name_station(self, pg):
        """변이 — 반경을 1,000m 로 넓히면 889m 의 신촌 경의중앙선 묶음이 들어온다(위 세 줄 단언이 빨강)."""
        old = "st_dwithin(s.geom::geography, me.gg, 500, false)"
        sql = read(FOUND[0])
        assert sql.count(old) == 1
        c = _fresh(pg, sql.replace(old, "st_dwithin(s.geom::geography, me.gg, 1000, false)", 1))
        try:
            assert "신촌" in [r["station_nm"] for r in _call(c, P)[1]][3:]
        finally:
            _fresh(pg)

    def test_mutation_average_of_monthly_averages_differs(self, pg):
        """변이 — 분모를 「창 안 모든 달 일수」로 바꾸면 신촌이 149 가 아니게 된다(위 Σ÷Σ 단언이 빨강)."""
        old = "(select distinct x.group_id, x.use_mm from rides x) m"
        sql = read(FOUND[0])
        assert sql.count(old) == 1
        c = _fresh(pg, sql.replace(old, "(select distinct x.group_id, y.use_mm from rides x, rides y) m", 1))
        try:
            assert _call(c, P)[1][1]["on_daily"] != 149
        finally:
            _fresh(pg)
