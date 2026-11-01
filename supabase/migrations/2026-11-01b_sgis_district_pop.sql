-- =====================================================================
-- 2026-11-01b — 대전 「상권 인구 (통계청 집계구)」 자료·DB (결정 0045 PR⑤ · 표 둘 + 함수 + 신선도 17번 줄 · 화면 0)
-- =====================================================================
--
-- 왜
-- --
-- 서울 상권은 서울시가 상주·직장 인구를 공표한다(PR② · 2026-10-31a). 대전 상권에는 그런 공표값이 없다 — 통계청 SGIS 가
-- 집계구(동보다 작은 통계 구역 · 전국 108,510)마다 낸 2024년 인구·가구·종사자·사업체 총괄을 상권 면에 겹친 면적 비율로
-- 나눠 담는다(👤 결정 0045 ③-1 — 대전만 · 거주 인구·가구·총종사자 · 상권 합계만 DB · 집계구 경계는 안 싣는다).
-- 같은 방식을 서울 1,650 상권에 돌려 서울시 상주인구 공표값과 맞대 보았다(2026-11-01 · 거주 인구 1,633 상권 · 오차 가운데
-- −3.8% · 공표값이 우리 하한~상한 안에 든 상권 95.5%) — 그래서 값과 함께 늘 범위를 낸다(👤 ③-3 · 함정 6).
--
-- 무엇이 생기나 (새 객체 + 신선도 함수 한 줄 — 기존 표의 행·칸은 한 글자도 안 바꾼다)
-- ---------------------------------------------------------------------------------------------
--   ① 표 둘 — district_census_pop(상권 한 줄 · 값·하한·상한 넷 × 셋 + 사업체 · 겹친 수 · 통째 수 · 덮임 · 넓이 ·
--      check 0 ≤ 하한 ≤ 값 ≤ 상한 · 0 ≤ 통째 ≤ 겹침) · sgis_census_release(표지 한 줄 · 받은 날 · 통계 연도 · 경계 기준일).
--      둘 다 RLS 켬 + 권한 회수(공개키 0). 적재는 scripts/collectors/load_sgis_district_pop.py(통째 교체 · 한 트랜잭션 ·
--      관문 ⒜~⒥) — 굽기는 로컬 scripts/build_sgis_district_pop.py(DB 는 상권 도형 읽기만).
--   ② 함수 get_district_census_pop(p_pnu text) + api 쌍둥이 — 그 필지가 속한 대전 상권마다(좁은 상권 먼저) 값·범위·
--      겹친 수·통째 수를 **그대로**(숨기지 않는다 — 「범위가 값의 2배 넘으면 범위만」은 화면 몫) · status no_coord →
--      not_daejeon → outside_daejeon_district(한 줄만) · 아니면 상권마다 ok / no_data · 표지 0줄이면 0줄 · 사업체 수는
--      안 내보낸다. 공개 호출 허용 총계 37 → 38(post_load.py ANON_CALLABLE_ALLOWLIST).
--   ③ get_data_freshness 다시 만들기 — 17번 줄 「상권 인구 (통계청 집계구)」(기준 = 받은 날 · 다음 갱신 예정 = 받은 날 +
--      12개월 — 새 규칙 'sgis' · 'YYYY-MM-DD' 일 때만 계산) · comment 「열여섯」. 나머지 열다섯 줄·규칙은 글자 그대로다.
--      ⓘ api.get_data_freshness 는 다시 만들지 않는다 — 통과 함수라 본문이 그대로다(2026-11-01a 와 같은 판단).
-- ⛔ 머리(language · stable · security definer · set search_path)와 comment 는 정본(schema.sql)과 글자 그대로다 —
--    tests/test_sgis_district_pop_migration.py 가 대조한다(CLAUDE.md ⛔ 2026-10-01a).
-- ⛔ 서명은 하나뿐이다(이름당 pg_proc 1 · 인자 (text)).
-- ⛔ 시·도 코드 둘을 섞지 말 것 — 상권·PNU 의 대전은 30, 집계구 코드의 대전 접두는 25 다(함수는 30 만 본다).
--
-- 잠금
-- ----
-- 새 표·새 함수 만들기와 함수 교체(create or replace)는 기존 표를 잠그지 않는다. 형제 관습대로 `lock_timeout` 은
-- **begin 앞**(세션 설정)에 둔다 — 함수 카탈로그 행을 다른 세션이 쥐고 있으면 오래 줄 서지 않고 실패한다(통째 롤백 ·
-- 다시 돌리면 된다 · 전부 멱등).
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 중간에 끊기면 신선도 함수가 없는 표를 읽거나 api 쌍둥이 없이 원본만 남는다.
-- `notify pgrst` 는 commit **뒤**.
--
-- 실행 순서 — DB 먼저 → 적재 → 그 뒤 화면 머지 (Claude 가 dbx 로 · 사장님께 여쭌 뒤)
-- ------------------------------------------------------------------------------
-- 이 PR 은 화면이 0 이라 어느 쪽이 먼저여도 손님 화면은 안 깨진다(화면 카드는 다음 단계 — 함수가 없거나 0줄이면 숨긴다).
--   ① python scripts/dbx.py -f supabase/migrations/2026-11-01b_sgis_district_pop.sql
--      (적용 뒤 적재 전엔 신선도 17번 줄이 '자료 없음'(basis null) — 같은 날 아래를 잇는다)
--   ② python scripts/build_sgis_district_pop.py   — 약 30초 · DB 는 상권 도형 읽기만 · 결과는 data/derived/sgis_district_pop/
--   ③ python scripts/collectors/load_sgis_district_pop.py --dry-run → 실적재(관문 ⒤: 결과표 상권 = district 의 대전 상권 ·
--      ⒥: 받은 날 앞으로만 — 어긋나면 통째 롤백 · 약 1MB 미만)
--   ④ python scripts/post_load.py → python scripts/post_load.py --check — 0 이어야 한다(허용 목록 총계 38 · 정본↔라이브 함수 일치)
--   ⓘ ①과 머지 사이에 **본 폴더(main)** 에서 `--check` 를 돌리면 api.get_district_census_pop 이 허용 목록 밖 공개 함수로
--     [사고]가 되고 get_data_freshness 가 정본과 달라 [사고]가 되는 것이 **정상**이다 — 그 창은 PR 가지 판으로 잰다.
--
-- 적용 뒤 확인 (dbx + anon 키로 **화면 요청 그대로**)
-- ------------------------------------------------
--   select oid::regprocedure, proconfig, prosecdef, provolatile from pg_proc
--    where proname = 'get_district_census_pop';                  -- 두 줄(public·api) · 둘 다 prosecdef t · provolatile s
--   select has_table_privilege('anon', 'district_census_pop', 'select'),
--          has_table_privilege('anon', 'sgis_census_release', 'select');   -- f · f
--   ③ 적재 뒤: select status, district_nm, n_overlap, n_full, pop, pop_lo, pop_hi, received_on
--                from api.get_district_census_pop('<유성온천역6번 출구 상권 안 대전 필지 19자리>');
--     → ok · 유성온천역6번 출구 · 13 · 5 · 4348 · 2513 · 6172 · 2026-10-08
--   select src, basis, next_expected from api.get_data_freshness() where src = '상권 인구 (통계청 집계구)';
--     → 상권 인구 (통계청 집계구) | 2026-10-08 | 2027-10-08
--   anon 키:
--     POST /rest/v1/rpc/get_district_census_pop {"p_pnu":"<대전 상권 안 필지>"}   → 200 · [ok 줄 1~N]
--     POST /rest/v1/rpc/get_district_census_pop {"p_pnu":"1168010100107370000"}  → 200 · [not_daejeon 한 줄]
--
-- 되돌리기
-- --------
-- **새 마이그레이션 파일**로 (신선도 함수 먼저 → 표 나중 — 표부터 지우면 함수가 없는 표를 읽어 신선도 표가 통째로
-- 사라진다): `set lock_timeout = '5s'; begin;` →
--   ① 2026-11-01a_store_history.sql 의 get_data_freshness 정의 첫 줄부터 그 함수의 revoke 줄까지(comment 포함)를
--      글자 그대로(17번 줄이 없는 판)
--   ② drop function api.get_district_census_pop(text); drop function get_district_census_pop(text);
--   ③ drop table sgis_census_release; drop table district_census_pop;
-- → `commit;` → `notify pgrst, 'reload schema';` 그리고 이 PR revert(정본 · post_load 허용 목록 38 → 37 · 그물 6호 힌트 ·
-- 화면 상수 CARD_SOURCES.census_pop). 적용된 이 파일은 고치지 않는다(원장).

set statement_timeout = '60s';
set lock_timeout = '5s';

begin;

-- =====================================================================
-- 표·함수: 대전 상권 인구 — SGIS 집계구 (2026-11-01b · 결정 0045 PR⑤)
-- =====================================================================
-- 통계청 SGIS 가 집계구(동보다 작은 통계 구역)마다 낸 인구·가구·종사자·사업체 총괄을 대전 상권 면에 **겹친 면적
-- 비율로 나눠 담은** 상권 합계만 싣는다(👤 결정 0045 ③-1 — 대전만 · 집계구 경계는 안 싣는다). 서울은 서울시 공표값(PR②).
-- 굽기는 로컬(scripts/build_sgis_district_pop.py — 겹침 ≥ 100㎡ · 통째 = 겹침/집계구 ≥ 0.99), 적재는
-- scripts/collectors/load_sgis_district_pop.py(통째 교체 · 받은 날 표지 한 줄 · 한 트랜잭션).
-- ⛔ 어림(C 등급)이다 — 집계구 안에서 고르게 산다고 보고 나눈 값이라 늘 범위와 함께 낸다(👤 ③-3 · 함정 6):
--    하한 = 상권 안에 통째로 든 집계구의 합 · 상한 = 조금이라도 걸친 집계구 전부의 합. 「상권 안 합계 — 건물 값 아님」.
-- 표 둘은 공개키에게 닫혀 있다(RLS 켬 + 정책 0 + 권한 회수) — 화면은 get_district_census_pop 으로만 읽는다.
-- 표지 sgis_census_release 를 get_data_freshness 가 읽으므로 그 함수보다 **앞**에 둔다.
create table if not exists district_census_pop (
  district_id    text primary key,
  district_nm    text not null,
  district_type  text,
  sigungu_code   char(5) not null,
  area_m2        numeric not null check (area_m2 > 0),
  n_overlap      integer not null check (n_overlap >= 1),
  n_full         integer not null,
  cover_pct      numeric not null,
  pop            integer not null,
  pop_lo         integer not null,
  pop_hi         integer not null,
  hh             integer not null,
  hh_lo          integer not null,
  hh_hi          integer not null,
  emp            integer not null,
  emp_lo         integer not null,
  emp_hi         integer not null,
  est            integer not null,
  est_lo         integer not null,
  est_hi         integer not null,
  check (0 <= n_full and n_full <= n_overlap),
  check (0 <= pop_lo and pop_lo <= pop and pop <= pop_hi),
  check (0 <= hh_lo and hh_lo <= hh and hh <= hh_hi),
  check (0 <= emp_lo and emp_lo <= emp and emp <= emp_hi),
  check (0 <= est_lo and est_lo <= est and est <= est_hi)
);

comment on table district_census_pop is
  '결정 0045 PR⑤ 대전 상권 안 인구 — 통계청 SGIS 집계구 총괄(인구·가구·종사자·사업체)을 상권 면에 겹친 면적 비율로 '
  '나눠 담은 상권 합계(어림 · C 등급 · 상권 안 합계이지 건물 값이 아니다). 값 = Σ(겹침 비율 × 집계구 값) · '
  '하한(_lo) = 상권 안에 통째로(겹침/집계구 ≥ 0.99) 든 집계구의 합 · 상한(_hi) = 100㎡ 이상 걸친 집계구 전부의 합 · '
  'n_overlap = 걸친 집계구 수 · n_full = 통째로 든 수 · cover_pct = 겹침 합/상권 면적(%). 기준 = 표지 sgis_census_release '
  '(통계 연도 · 집계구 경계 기준일 · 받은 날 폴더 — 2026-10-08 판은 2024년 통계 · 2025년 2분기 경계). '
  'scripts/build_sgis_district_pop.py → load_sgis_district_pop.py 가 통째 교체. 공개키 읽기 금지 — 화면은 '
  'get_district_census_pop 으로만 읽는다(사업체 수 est 는 화면에 안 내보낸다)';

alter table district_census_pop enable row level security;

-- ⛔ Supabase 는 새 표를 anon 에 자동으로 연다(pg_default_acl) — 만든 자리에서 닫는다.
revoke all on district_census_pop from public, anon, authenticated;

-- SGIS 상권 인구 표지 — 한 줄뿐(id = 1). 적재기가 통째 교체와 같은 트랜잭션에서 적는다.
create table if not exists sgis_census_release (
  id              smallint primary key check (id = 1),
  received_on     date not null,
  base_year       smallint not null,
  bnd_base_date   date not null,
  n_oa_total      integer not null,
  rows_cnt        integer not null,
  built_at        timestamptz not null,
  overlap_min_m2  numeric not null,
  full_ratio      numeric not null
);

comment on table sgis_census_release is
  '결정 0045 PR⑤ SGIS 상권 인구 표지 — 한 줄뿐(id = 1). received_on = SGIS 자료제공에서 받은 날(원본 폴더 이름 끝) · '
  'base_year = 통계 기준 연도 · bnd_base_date = 집계구 경계 기준일 · n_oa_total = 경계 파일의 집계구 수(전국) · '
  'rows_cnt = 넣은 상권 줄 수 · built_at = 로컬에서 구운 시각 · overlap_min_m2·full_ratio = 굽기 상수(100㎡ · 0.99). '
  '신선도 17번 줄(받은 날 + 12개월)이 읽는다. 0줄이면 get_district_census_pop 도 0줄. 공개키 읽기 금지';

alter table sgis_census_release enable row level security;

-- ⛔ Supabase 는 새 표를 anon 에 자동으로 연다(pg_default_acl) — 만든 자리에서 닫는다.
revoke all on sgis_census_release from public, anon, authenticated;

-- 필지가 속한 대전 상권마다(좁은 상권 먼저 · 합치지 않는다) SGIS 상권 인구 한 줄.
--   상권 찾기·status·차례는 list_district_pop 글 그대로(서울 → 대전) · 표지 0줄이면 0줄 · 사업체 수(est)는 안 내보낸다.
create or replace function get_district_census_pop(p_pnu text)
returns table (
  status         text,
  district_id    text,
  district_nm    text,
  district_type  text,
  area_m2        numeric,
  n_overlap      integer,
  n_full         integer,
  cover_pct      numeric,
  pop            integer,
  pop_lo         integer,
  pop_hi         integer,
  hh             integer,
  hh_lo          integer,
  hh_hi          integer,
  emp            integer,
  emp_lo         integer,
  emp_hi         integer,
  received_on    date,
  base_year      smallint,
  bnd_base_date  date
)
language sql
stable
security definer
set search_path = public
as $$
  with me as (
    -- 좌표가 없으면 아무 상권에도 안 든다는 **단정**이 새어 나가지 않게 따로 가른다(no_coord).
    -- ⛔ pnu 칸은 char(19) — 인자를 그대로 견주면 칸 쪽이 text 로 캐스트돼 색인이 죽는다.
    select p.geom
    from parcel p
    where p.pnu = p_pnu::char(19) and p.geom is not null
  ),
  hit as (
    -- 대전 필지가 담긴 **대전 상권**만. 술어는 list_building_districts 와 같은 st_contains.
    select d.district_id, d.district_nm, d.district_type, d.area_m2
    from district d cross join me
    where left(p_pnu::char(19), 2) = '30'
      and left(d.sigungu_code, 2) = '30'
      and st_contains(d.geom, me.geom)
  ),
  head as (
    -- 건물 단위 상태 셋 — 판정 순서가 곧 뜻이다(위부터, 서로 배타).
    --   no_coord                 필지 좌표 없음(대전이든 아니든 — 모르는 것은 모른다고)
    --   not_daejeon              시·도가 대전이 아님(서울 등 — 서울은 서울시 공표값 카드가 따로 있다)
    --   outside_daejeon_district 대전인데 속한 대전 상권이 없음
    -- 셋 다 아니면 null → 상권마다 ok / no_data 한 줄씩이 대신 나간다.
    select case
             when not exists (select 1 from me) then 'no_coord'
             when left(p_pnu::char(19), 2) <> '30' then 'not_daejeon'
             when not exists (select 1 from hit) then 'outside_daejeon_district'
           end as status
  ),
  rel as (
    -- 표지. 0줄이면(아직 안 넣음) 이 함수도 0줄 — 화면은 카드째 숨긴다.
    select r.received_on, r.base_year, r.bnd_base_date from sgis_census_release r
  ),
  rows_out as (
    select hd.status,
           null::text as district_id, null::text as district_nm, null::text as district_type,
           null::numeric as area_m2, null::integer as n_overlap, null::integer as n_full, null::numeric as cover_pct,
           null::integer as pop, null::integer as pop_lo, null::integer as pop_hi,
           null::integer as hh, null::integer as hh_lo, null::integer as hh_hi,
           null::integer as emp, null::integer as emp_lo, null::integer as emp_hi,
           0::numeric as sort_area
    from head hd
    where hd.status is not null
    union all
    -- 결과표에 그 상권 줄이 없으면 no_data(숫자 칸은 전부 null — 0 이 아니다).
    -- ⛔ 값·하한·상한·겹친 수·통째 수를 **그대로** 낸다 — 「범위가 값의 2배 넘으면 범위만」은 화면 몫(👤 ③-3).
    select case when c.district_id is null then 'no_data' else 'ok' end,
           h.district_id, h.district_nm, h.district_type,
           c.area_m2, c.n_overlap, c.n_full, c.cover_pct,
           c.pop, c.pop_lo, c.pop_hi,
           c.hh, c.hh_lo, c.hh_hi,
           c.emp, c.emp_lo, c.emp_hi,
           h.area_m2
    from hit h
    left join district_census_pop c on c.district_id = h.district_id
  )
  select ro.status, ro.district_id, ro.district_nm, ro.district_type,
         ro.area_m2, ro.n_overlap, ro.n_full, ro.cover_pct,
         ro.pop, ro.pop_lo, ro.pop_hi,
         ro.hh, ro.hh_lo, ro.hh_hi,
         ro.emp, ro.emp_lo, ro.emp_hi,
         r.received_on, r.base_year, r.bnd_base_date
  from rows_out ro
  cross join rel r
  -- 좁은 상권이 더 구체적인 설명이라 먼저 온다(list_building_districts 와 같은 정렬).
  order by ro.sort_area asc, ro.district_id;
$$;

comment on function get_district_census_pop(text) is
  '결정 0045 PR⑤ 이 필지가 속한 대전 상권마다(좁은 상권 먼저 · 합치지 않는다) 통계청 SGIS 집계구 통계를 겹친 면적 '
  '비율로 나눠 담은 상권 안 인구 — 거주 인구(pop) · 가구(hh) · 총종사자(emp) 셋, 각각 값 · 하한(_lo = 통째로 든 집계구 합) · '
  '상한(_hi = 걸친 집계구 전부 합) + 걸친 집계구 수 n_overlap · 통째 수 n_full · 덮임 cover_pct · 상권 면적 area_m2 · '
  '표지의 받은 날·통계 연도·경계 기준일. 어림(C 등급)이고 상권 안 합계이지 이 건물의 값이 아니다 — 값·범위는 그대로 '
  '내보내고 「범위가 값의 2배 넘으면 범위만」은 화면이 정한다. 사업체 수는 안 내보낸다(👤 결정 0045 ③-1 셋만). '
  '상권 찾기·status 는 list_district_pop 과 같은 글이다(서울 → 대전): no_coord → not_daejeon → outside_daejeon_district'
  '(이 셋은 한 줄만) · 아니면 상권마다 ok / no_data(결과표에 그 상권 줄 없음). 표지가 0줄이면 0줄. '
  'security definer (district_census_pop·sgis_census_release·district·parcel 이 anon 에게 닫혀 있어 소유자 권한으로 '
  '대신 읽는다. 나가는 것은 상권 이름·종류와 상권 합계 수뿐이다).';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function get_district_census_pop(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.get_district_census_pop(p_pnu text)
returns table (
  status         text,
  district_id    text,
  district_nm    text,
  district_type  text,
  area_m2        numeric,
  n_overlap      integer,
  n_full         integer,
  cover_pct      numeric,
  pop            integer,
  pop_lo         integer,
  pop_hi         integer,
  hh             integer,
  hh_lo          integer,
  hh_hi          integer,
  emp            integer,
  emp_lo         integer,
  emp_hi         integer,
  received_on    date,
  base_year      smallint,
  bnd_base_date  date
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.get_district_census_pop(p_pnu) $$;

revoke all on function api.get_district_census_pop(text) from public, anon, authenticated;
grant execute on function api.get_district_census_pop(text) to anon, authenticated;

-- ⛔ public.get_district_census_pop 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.

-- ── 신선도 표 17번 줄(SGIS 상권 인구) ─────────────────────────────────────────
-- 표지 sgis_census_release(위)를 읽으므로 표 **뒤**에 다시 만든다.
create or replace function get_data_freshness()
returns table (
  src           text,
  basis_kind    text,
  basis         text,
  next_expected date,
  cadence       text
)
language sql
stable
security definer
set search_path = public
as $$
  with raw as (
    -- ⓘ 순서를 ord 로 못 박는다. union all 은 순서를 보장하지 않으므로, 이 숫자가 없으면
    --   화면의 줄 순서가 실행할 때마다 달라질 수 있다(사람은 그걸 자료가 바뀐 것으로 읽는다).
    select 1 as ord,
           '점포·업종 (상권정보)'::text as src,
           '분기'::text                 as basis_kind,
           (select r.published_ym::text from snapshot_release r) as basis,
           'sangkwon'::text             as rule_kind,
           '분기마다 (다음 분기 자료가 공개되면 사람이 적재)'::text as cadence
    union all
    -- 2026-10-15a — 실거래는 매달 최근 6개월을 다시 받는다(사장님 결정 2026-10-15 · 규칙 'tx').
    select 2, '실거래 (매매)', '계약월',
           (select max(t.contract_ym)::text from transaction t),
           'tx',
           '월 1회 (최근 6개월 다시 받기)'
    union all
    -- 2026-10-15a — 기준은 적재일(max(building.updated_at))이 아니라 표지의 판이다(30개 구를 다 넣은 뒤
    --   사람이 올린다). 규칙은 인허가와 같은 월간 갈래 — 건축HUB 일괄 파일도 다음 달 20일 무렵 게시된다.
    select 3, '건축물대장', '판',
           (select r.release_ym::text from ledger_release r),
           'permit',
           '월간 파일 (사람이 적재)'
    union all
    select 4, '상권 경계', '계산일',
           (select (max(t.computed_at) at time zone 'Asia/Seoul')::date::text from district t),
           'none',
           '비정기 (원천이 바뀌면)'
    union all
    select 5, 'LH 상가 공고', '수집일',
           (select (max(t.collected_at) at time zone 'Asia/Seoul')::date::text from lh_notice t),
           'none',
           '주 1회 감시 · 적재는 사람'
    union all
    select 6, '건축 인허가', '기준월',
           (select max(t.loaded_ym)::text from arch_permit t),
           'permit',
           '월 1회'
    union all
    select 7, '국세청 기준시가', '고시일',
           (select max(t.notice_date)::text from nts_base_price t),
           'nts',
           '연 1회 (매년 3월 고시)'
    union all
    select 8, '상권 임대 동향 (부동산원)', '분기',
           (select max(t.quarter)::text from rent_stat t),
           'rone',
           '분기마다'
    union all
    -- ⓘ 9번(옛 성적표 줄)은 2026-10-18a(결정 0041)에 뺐다 — 뒤 번호는 그대로 둔다(순서만 정하는 칸이다).
    -- 2026-10-12b — 기준은 우리가 받아 둔 날(updated_at)이 아니라 개별공시지가의 공시 연도다
    --   (사장님 결정 2026-10-12). smallint 라 '2026' 네 자리로 나온다.
    select 10, '필지 (토지 특성)', '공시 연도',
           (select max(t.land_price_year)::text from parcel t),
           'land_year',
           '연 1회 (브이월드)'
    union all
    -- 결정 0033 — 서울시 상권분석서비스 개업·폐업. 분기 꼴이 'YYYYQ' 다섯 자리(Q 없음)다.
    select 11, '상권 개업·폐업 (서울시)', '분기',
           (select max(t.quarter)::text from district_openclose t),
           'seoul_openclose',
           '분기마다'
    union all
    -- 2026-10-29a(결정 0044) — 대전시 동네 폐업. 기준 = 사람이 대전시 사이트에서 받은 날(표지 한 줄)이다.
    select 12, '동네 폐업 (대전시)', '받은 날',
           (select r.received_on::text from daejeon_closure_release r),
           'daejeon_closure',
           '분기마다 (사람이 대전시 사이트에서 받음)'
    union all
    -- 2026-10-31a(결정 0045) — 서울시 상권분석서비스 추정매출·길단위인구. 분기 꼴은 개업·폐업과 같은 'YYYYQ' 라
    --   같은 규칙(seoul_openclose — 분기말 + 5개월 - 하루)을 쓴다.
    select 13, '상권 추정매출 (서울시)', '분기',
           (select max(t.quarter)::text from district_sales t),
           'seoul_openclose',
           '분기마다'
    union all
    select 14, '상권 길단위인구 (서울시)', '분기',
           (select max(t.quarter)::text from district_pop_flow t),
           'seoul_openclose',
           '분기마다'
    union all
    -- 2026-10-31a(결정 0045 · 사장님 결정 10-31 「다음 예정 없음」) — 상주·직장인구는 한 줄. 기준 = 값이 마지막으로
    --   바뀐 분기 둘을 글로 합친다(표지 seoul_trdar_release). 서울시 공지는 연 1회지만 실제 갱신이 불규칙(상주
    --   2024·2025 건너뜀)이라 예정일을 계산하지 않는다('none' → null). 표지가 비면 basis 도 null(화면 '자료 없음').
    select 15, '상권 상주·직장인구 (서울시)', '값이 바뀐 분기',
           (select '상주 ' || left(a.value_quarter, 4) || '년 ' || right(a.value_quarter, 1) || '분기, 직장 '
                   || left(b.value_quarter, 4) || '년 ' || right(b.value_quarter, 1) || '분기'
              from seoul_trdar_release a, seoul_trdar_release b
             where a.tbl = 'district_pop_resident' and b.tbl = 'district_pop_worker'),
           'none',
           '연 1회 (서울시 공지) · 실제는 불규칙 — 예정일 계산 안 함'
    union all
    -- 2026-11-01a(결정 0045 PR④) — 가게 이력 결과표의 마지막 분기. 점포 줄(ord 1)과 같은 `sangkwon` 규칙 — 같은 분기면
    --   같은 날 「지났습니다」가 뜬다(정상 · 새 분기 적재 → 빌드 → 적재 순서). 표지가 비면 basis null(화면 '자료 없음').
    select 16, '가게 이력 (점포 자료 누적)', '분기',
           (select r.last_ym::text from store_history_release r),
           'sangkwon',
           '분기마다 (새 분기 점포 자료를 적재한 뒤 다시 굽는다)'
    union all
    -- 2026-11-01b(결정 0045 PR⑤) — SGIS 집계구 통계를 대전 상권에 나눠 담은 결과표의 받은 날(표지 sgis_census_release).
    --   사람이 SGIS 자료제공에서 연 1회 신청해 받는다 — 받은 날 + 12개월(규칙 'sgis'). 표지가 비면 basis null(화면 '자료 없음').
    select 17, '상권 인구 (통계청 집계구)', '받은 날',
           (select r.received_on::text from sgis_census_release r),
           'sgis',
           '연 1회 (사람이 SGIS 자료제공에서 신청해 받음)'
  ),
  norm as (
    -- 분기 규칙을 쓰는 세 줄을 **같은 모양('YYYYMM' 분기말 달)** 으로 맞춘다. 이렇게 해야
    -- 아래 계산이 한 번만 적힌다 — 세 벌로 적어 두면 한쪽만 고쳐지는 날 자료끼리 서로
    -- 다른 주기를 말한다.
    -- ⛔ 서울시 분기 꼴('20262')은 둘째 갈래(`YYYYQn`)에도 첫째 갈래(여섯 자리)에도 안 걸린다 —
    --   셋째 갈래가 없으면 그 줄은 에러 없이 '정해진 주기 없음'(null)이 된다(결정 0033 v3 재검사).
    select r.*,
           case
             when r.rule_kind = 'sangkwon' and r.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
               then r.basis
             when r.rule_kind = 'rone' and r.basis ~ '^\d{4}Q[1-4]$'
               then left(r.basis, 4) || lpad((right(r.basis, 1)::int * 3)::text, 2, '0')
             when r.rule_kind = 'seoul_openclose' and r.basis ~ '^\d{4}[1-4]$'
               then left(r.basis, 4) || lpad((right(r.basis, 1)::int * 3)::text, 2, '0')
           end as q_ym
    from raw r
  )
  select n.src,
         n.basis_kind,
         n.basis,
         case
           -- 분기 자료: 다음 분기가 **공개되는 달**의 말일(분기말 + 5개월 - 하루).
           when n.q_ym is not null
             then (to_date(n.q_ym, 'YYYYMM') + interval '5 months' - interval '1 day')::date
           -- 월간 자료(인허가 기준월 · 건축물대장 판): 다음 판이 **공개되는 달**의 말일(기준월 + 3개월 - 하루).
           when n.rule_kind = 'permit' and n.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
             then (to_date(n.basis, 'YYYYMM') + interval '3 months' - interval '1 day')::date
           -- 실거래: 계약월 + 2개월 - 하루(사장님 결정 2026-10-15 — 매달 최근 6개월을 다시 받는다).
           when n.rule_kind = 'tx' and n.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
             then (to_date(n.basis, 'YYYYMM') + interval '2 months' - interval '1 day')::date
           -- 연 1회: 다음 해 3월 31일(국세청 고시가 매년 3월).
           when n.rule_kind = 'nts' and n.basis ~ '^\d{4}-\d{2}-\d{2}$'
             then make_date(left(n.basis, 4)::int + 1, 3, 31)
           -- 연 1회: 개별공시지가는 공시 연도의 다음 해 6월 30일(사장님 결정 2026-10-12).
           --   네 자리 연도일 때만 — 모양이 다르면 ::int 가 터져 표가 통째로 사라진다.
           when n.rule_kind = 'land_year' and n.basis ~ '^\d{4}$'
             then make_date(n.basis::int + 1, 6, 30)
           -- 대전시 동네 폐업: 받은 날 + 3개월(분기마다 사람이 받는다 — 2026-10-29a · 결정 0044).
           --   'YYYY-MM-DD' 일 때만 — 모양이 다르면 ::date 가 터져 표가 통째로 사라진다.
           when n.rule_kind = 'daejeon_closure' and n.basis ~ '^\d{4}-\d{2}-\d{2}$'
             then (n.basis::date + interval '3 months')::date
           -- SGIS 상권 인구: 받은 날 + 12개월(연 1회 사람이 신청해 받는다 — 2026-11-01b · 결정 0045 PR⑤).
           --   'YYYY-MM-DD' 일 때만 — 모양이 다르면 ::date 가 터져 표가 통째로 사라진다.
           when n.rule_kind = 'sgis' and n.basis ~ '^\d{4}-\d{2}-\d{2}$'
             then (n.basis::date + interval '12 months')::date
         end as next_expected,
         n.cadence
  from norm n
  order by n.ord;
$$;

comment on function get_data_freshness() is
  '화면 아래 "이 자료는 언제 것인가" 표. 열여섯 갈래 자료의 가장 최근 도장(분기·계약월·판·'
  '계산일·수집일·기준월·고시일·공시 연도·받은 날·값이 바뀐 분기)을 창고에서 읽어 한 줄씩 준다. '
  '⛔ 숫자를 화면에 박지 않기 위한 함수다 — 신선도를 글자로 적어 두면 적재하는 순간부터 '
  '그 글자만 거짓말을 한다. next_expected 도 사람이 적는 값이 아니라 규칙으로 계산한다: '
  '분기 자료는 분기말 달 + 5개월 - 하루(다음 분기가 공개되는 달의 말일 — 분기 꼴 셋 '
  '''YYYYMM''·''YYYYQn''·''YYYYQ''(서울시 다섯 자리)를 같은 분기말 달로 맞춘 뒤 한 번만 계산), 월간 자료'
  '(인허가 기준월·건축물대장 판)는 기준월 + 3개월 - 하루(다음 판이 공개되는 달의 말일), 실거래는 계약월 + '
  '2개월 - 하루(매달 최근 6개월을 다시 받는다), 국세청 기준시가는 고시일의 다음 해 3월 31일, '
  '필지(개별공시지가)는 공시 연도의 다음 해 6월 30일(기준값이 네 자리 연도일 때만), 대전시 동네 폐업은 '
  '받은 날 + 3개월(분기마다 사람이 받는다 · 기준값이 YYYY-MM-DD 일 때만), SGIS 상권 인구는 받은 날 + 12개월(연 1회 · 같은 모양일 때만). '
  '서울 상권 추정매출·길단위인구는 '
  '개업·폐업과 같은 분기 규칙이고, 서울 상권 상주·직장인구는 실제 갱신이 불규칙해 예정일을 계산하지 않는다'
  '(기준 = 값이 마지막으로 바뀐 분기 둘을 글로 합침). '
  '주기가 없는 자료는 null 이다 — 없는 주기를 지어내면 "늦었다"는 거짓 신호가 뜬다. '
  '기준값이 그 모양이 아니면 계산하지 않고 그 칸만 비운다(to_date 가 터지면 표가 통째로 '
  '사라진다). timestamptz 는 전부 Asia/Seoul 로 옮겨 날짜를 자른다 — 이 DB 가 UTC 라 '
  '그냥 자르면 한국 새벽 0~9시에 어제 날짜가 찍힌다. '
  '⛔ api_quota_log 는 안 본다 — 그건 우리 호출 장부이지 자료의 나이가 아니고, 하한선일 뿐이다. '
  '자료가 0행이면 basis 가 null 이고 줄은 그대로 나온다(화면이 "자료 없음"이라 적는다 — '
  '줄을 빼면 "그런 자료를 안 쓴다"로 읽힌다). '
  'security definer (열여섯 표가 전부 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 집계 도장 열여섯 개뿐이고 원본 행은 한 줄도 안 나간다). 2026-09-05d · 월간 규칙 2026-10-01a · '
  '서울 개업·폐업 2026-10-05b · 필지 공시 연도 2026-10-12b · 실거래·대장 판 월간 규칙 2026-10-15a · '
  '성적표 줄 뺌 2026-10-18a(결정 0041) · 대전시 동네 폐업 2026-10-29a(결정 0044) · 서울 상권 4종 세 줄 2026-10-31a(결정 0045) · 가게 이력 2026-11-01a(결정 0045 PR④) · SGIS 상권 인구 2026-11-01b(결정 0045 PR⑤)';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function get_data_freshness() from public, anon, authenticated;

commit;

notify pgrst, 'reload schema';
