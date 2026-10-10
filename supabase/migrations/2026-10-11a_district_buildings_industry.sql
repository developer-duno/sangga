-- =====================================================================
-- 2026-10-11a — 지도 상권 목록을 업종 기준으로 (물결 2-2b · 결정 0036 결정 18 ⑨·㉒)
-- =====================================================================
--
-- 왜
-- --
-- 창업자가 지도 위 업종 칩(카페·한식·미용·학원·편의점)을 고르면, 건물을 연 뒤의 두 카드(업종 분포·
-- 개업·폐업)는 그 업종을 따라가는데 **상권 목록(지도에서 상권 이름을 누르면 펼쳐지는 땅 목록)은 여태
-- 땅 전체 점포 수 순서 그대로**였다(결정 18 ⑨ 에서 2-2b 로 미룬 몫). 카페 자리를 찾는 사람에게 카페가 한
-- 곳도 없는 백화점 땅이 맨 위에 선다.
--
-- 무엇이 바뀌나
-- -------------
--   ① list_district_buildings 에 인자 하나 p_cat_m text[] default null(형제 list_industry_floors 와 같은
--      이름·같은 꼴 — 칩의 짝 중분류 코드 · 학원은 둘).
--   ② 인자가 있으면 그 업종 점포가 1곳 이상인 땅만(👤 2026-10-11) · 그 업종 점포 수 많은 순 → 전체 점포 수
--      → pnu(tie-break 유지 — '더 보기' 안정) · total_parcel_cnt·total_bld_cnt 는 거른 뒤 규모.
--   ③ 새 칸 cat_store_cnt(store_cnt 바로 뒤) = 그 땅의 고른 업종 점포 수 · 인자가 null 이면 null.
--      store_cnt 는 언제나 땅 전체 점포 수 그대로.
--   ⛔ 인자가 null(칩 '전체' — 화면은 이 인자를 **아예 안 보낸다**)이면 행·순서·칸 값이 옛 함수와 같다
--      (cat_store_cnt 만 null 로 더 붙는다 — tests/test_district_buildings_industry_migration.py 가 옛 본문과
--      줄 단위로 대조하고, 로컬 PostgreSQL 이 있으면 옛·새 함수를 같은 판에 돌려 결과를 견준다).
--   ⓘ 옛 화면(인자 이름 셋으로 부름)은 새 함수에 그대로 붙는다(넷째 인자에 기본값).
--   ⓘ 분기는 여전히 표지 snapshot_release.published_ym(결정 0035 — 실시간 함수).
--   ⓘ 공개 호출 허용 목록(post_load.py ANON_CALLABLE_ALLOWLIST)은 서명이 아니라 이름을 본다 — 총계 29 그대로.
--
-- 왜 지우고 다시 만드나
-- --------------------
-- 공식 문서(CREATE FUNCTION): `create or replace` 로는 인자 형을 바꿀 수 없고(그렇게 쓰면 **다른 함수**가
-- 새로 생긴다) 반환 형도 바꿀 수 없다(바꾸려면 지우고 다시 만든다). 인자가 셋 → 넷이 되면 같은 이름의
-- 함수가 둘(오버로드) 남아 인자 셋 요청이 두 함수 모두에 맞는다(넷째에 기본값) — 옛 3-인자
-- 둘(api·public)을 지운다. 순서 = api 쌍둥이 먼저(public 원본을 부르는 쪽) → public.
-- ⛔ 머리(language sql · stable · security definer · set search_path)와 comment 는 정본(schema.sql)에서
--    잘라 붙였다 — 시험이 정본과 글자 대조한다(CLAUDE.md ⛔ 2026-10-01a).
--
-- 잠금
-- ----
-- drop/create function 은 그 함수 객체에만 잠금을 건다(표·뷰 잠금 없음). 형제 관습대로 `lock_timeout` 은
-- **begin 앞**(세션 설정)에 둔다.
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 지운 뒤 끊기면 상권 목록 함수가 없는 채로 남아 지도 목록이
-- '불러오지 못했습니다'가 된다 — 한 덩어리로 묶는다. `notify pgrst` 는 commit **뒤**.
--
-- 실행 (머지 뒤 · 👤 허락 뒤 · Claude 가 dbx 로 · 배치 창과 무관 — 표를 안 건드린다)
-- ------------------------------------------------------------------------------
--   python scripts/dbx.py -f supabase/migrations/2026-10-11a_district_buildings_industry.sql
--   → 이어서 python scripts/post_load.py --check — 0 이어야 한다(허용 목록 총계 29 그대로 · 정본↔라이브 함수 일치).
--
-- 적용 뒤 확인 (dbx + anon 키로 **화면 요청 그대로**)
-- ------------------------------------------------
--   select oid::regprocedure, proconfig, prosecdef from pg_proc
--    where proname = 'list_district_buildings';            -- 두 줄(public·api) · 넷째 인자 text[] · 3-인자 0줄
--   anon 키:
--     POST /rest/v1/rpc/list_district_buildings {"p_district_id":"<명동 상권>","p_limit":50,"p_offset":0}
--        → 200 · 적용 전과 같은 줄·같은 순서 · cat_store_cnt null
--     POST /rest/v1/rpc/list_district_buildings {"p_district_id":"<같은 상권>","p_limit":50,"p_offset":0,"p_cat_m":["I212"]}
--        → 200 · 줄마다 cat_store_cnt ≥ 1 · cat_store_cnt 내림차순 · total_parcel_cnt 가 앞보다 작거나 같다
--   눈 확인: 창업자 → 칩 '카페' → 지도에서 상권 이름 → '고른 업종(카페) N곳 · 전체 점포 M곳'.
--
-- 되돌리기
-- --------
-- **새 마이그레이션 파일**로: begin → drop function api.list_district_buildings(text, int, int, text[]) →
-- drop function list_district_buildings(text, int, int, text[]) → 2026-10-07a 의 두 정의(3-인자)·comment·
-- revoke·grant 를 그대로 → commit → notify. 그리고 이 PR revert(정본·화면). 적용된 이 파일은 고치지 않는다(원장).
-- 화면은 칩 '전체'일 때 새 인자를 안 보내므로 옛 함수로 되돌려도 칩 없는 손님은 그대로다
-- (칩을 고른 손님만 PGRST202 → 목록 '불러오지 못했습니다').

set statement_timeout = '60s';
set lock_timeout = '5s';

begin;

drop function if exists api.list_district_buildings(text, int, int);
drop function if exists list_district_buildings(text, int, int);

-- ── public 원본 (🚪 grant 없음 — 화면은 api 쌍둥이로만 들어온다) ──────────────────────
create or replace function list_district_buildings(
  p_district_id text,
  p_limit       int default 50,
  p_offset      int default 0,
  p_cat_m       text[] default null
)
returns table (
  pnu              char(19),
  store_cnt        int,        -- 이 **땅**의 점포 수(최신 분기)
  cat_store_cnt    int,        -- 그중 고른 업종(p_cat_m) 점포 수 · p_cat_m 이 null 이면 null
  bld_cnt_in_pnu   int,        -- 1 보다 크면 화면이 "같은 땅에 N동"을 적는다
  bld_id           text,       -- 대표 동 = 연면적 최대. 아래 칸들은 검색 결과와 같은 모양
  bld_nm           text,
  road_addr        text,
  jibun_addr       text,
  lat              double precision,
  lng              double precision,
  floor_cnt        int,
  min_floor        smallint,
  max_floor        smallint,
  has_roof         boolean,
  total_parcel_cnt bigint,     -- 상한에 잘리기 전 전체 규모(모든 행에 같은 값)
  total_bld_cnt    bigint
)
language sql
stable
security definer
set search_path = public
as $$
  with scope as (
    -- ⛔ 정방향(list_building_districts)과 같은 판정. 좌표 없는 필지는 아예 안 본다 —
    --    st_contains 가 NULL 을 거짓으로 흘리면 "상권 밖"이라는 **단정**이 되어 버린다.
    select p.pnu
    from district d
    join parcel p on st_contains(d.geom, p.geom)
    where d.district_id = p_district_id
      and p.geom is not null
  ),
  elig as (
    -- 층 자료가 아예 없는 건물은 눌러도 빈 화면이라 뺀다
    -- (검색과 **같은 규칙** — 2026-08-13 실측 242,631 중 239동).
    select b.bld_id, b.pnu, b.display_nm, b.total_area_m2
    from scope sc
    join building b on b.pnu = sc.pnu
    where exists (
      select 1 from building_floor f
      where f.bld_id = b.bld_id and f.floor_no is not null
    )
  ),
  stores as (
    -- 고른 업종 점포도 같은 훑기 한 번에 센다 — cat_m_cd 는 색인 idx_ub_pnu_cat 의 include 칸이라
    -- 힙에 안 간다. ⛔ `p_cat_m::char(4)[]` 캐스트를 지우지 말 것(형제 list_industry_floors 와 같은 자 —
    -- 칸이 char(4) 라 text 로 견주면 컬럼 쪽이 캐스트된다). p_cat_m 이 null 이면 cat_n 은 0(아래에서 null 로).
    select ub.pnu, count(*)::int as n,
           (count(*) filter (where ub.cat_m_cd = any(p_cat_m::char(4)[])))::int as cat_n
    from unit_business ub
    join scope sc on sc.pnu = ub.pnu
    where ub.snapshot_ym = (select r.published_ym from snapshot_release r)
    group by 1
  ),
  land as (
    -- ⓘ 창 함수는 GROUP BY **뒤에** 돈다 → count(*) over () = 땅 수,
    --    sum(count(*)) over () = 동 수. 둘을 한 번에 얻으려고 이 모양을 쓴다.
    select e.pnu,
           coalesce(max(s.n), 0)::int as store_cnt,
           (case when p_cat_m is not null then coalesce(max(s.cat_n), 0) end)::int as cat_store_cnt,
           count(*)::int              as bld_cnt_in_pnu,
           count(*)      over ()      as total_parcel_cnt,
           sum(count(*)) over ()      as total_bld_cnt
    from elig e
    left join stores s on s.pnu = e.pnu
    group by e.pnu
    -- 업종을 골랐으면 그 업종 점포가 1곳 이상인 땅만(👤 2026-10-11). ⓘ having 은 창 함수 **앞에** 돈다 —
    -- 그래서 total_parcel_cnt·total_bld_cnt 는 거른 뒤의 규모다('더 보기'가 거른 목록 끝에서 멈춘다).
    having p_cat_m is null or coalesce(max(s.cat_n), 0) > 0
  ),
  page as (
    -- ⛔ 무거운 조인(주소 조립·좌표·층 집계) 전에 **상한을 먼저** 건다.
    --    검색 함수가 "25행에만 필요하다"며 쓰는 것과 같은 수법이다.
    -- 정렬 tie-break 에 pnu 를 둔다 — 없으면 같은 점포 수끼리 순서가 흔들려
    -- '더 보기'가 이미 본 줄을 다시 가져오거나 건너뛴다.
    -- 업종을 골랐으면 그 업종 점포 수가 먼저 · p_cat_m 이 null 이면 cat_store_cnt 가 전부 null 이라
    -- 첫 열쇠가 아무것도 가르지 않는다(옛 순서 store_cnt desc, pnu 그대로).
    select *
    from land
    order by cat_store_cnt desc nulls last, store_cnt desc, pnu
    limit  greatest(1, least(coalesce(p_limit, 50), 200))
    offset greatest(0, coalesce(p_offset, 0))
  )
  select
    pg.pnu,
    pg.store_cnt,
    pg.cat_store_cnt,
    pg.bld_cnt_in_pnu,
    rep.bld_id,
    rep.display_nm as bld_nm,
    p.road_addr,
    parcel_jibun_addr(p.sido_nm, p.sigungu_nm, p.emd_nm, p.jibun) as jibun_addr,
    -- ⛔ 좌표는 geom 에서만 뽑는다. parcel 의 lat/lng **칸**을 쓰면 검색·상권판정과
    --    자리가 갈려 "마커는 상권 밖인데 글자는 상권 안"이 된다(2026-08-14e 규칙).
    st_y(p.geom)::double precision as lat,
    st_x(p.geom)::double precision as lng,
    fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof,
    pg.total_parcel_cnt,
    pg.total_bld_cnt
  from page pg
  join parcel p on p.pnu = pg.pnu
  join lateral (
    select e.bld_id, e.display_nm
    from elig e
    where e.pnu = pg.pnu
    order by e.total_area_m2 desc nulls last, e.bld_id
    limit 1
  ) rep on true
  join lateral (
    -- ⛔ 층수 규칙을 여기서 새로 정하지 않는다 — 검색 함수의 것을 글자 그대로 옮겼다.
    --    갈리면 같은 건물이 들어온 길에 따라 "지하2~15층"과 "지하2~99층"으로 갈린다.
    select count(*)::int                                    as floor_cnt,
           min(s.floor_no) filter (where s.floor_no <> 99)  as min_floor,
           max(s.floor_no) filter (where s.floor_no <> 99)  as max_floor,
           coalesce(bool_or(s.floor_no = 99), false)        as has_roof
    from v_building_floor_stack s
    where s.bld_id = rep.bld_id
  ) fs on true
  order by pg.cat_store_cnt desc nulls last, pg.store_cnt desc, pg.pnu;
$$;

comment on function list_district_buildings(text, int, int, text[]) is
  '상권 하나에 속한 **땅(필지)** 목록을 점포 많은 순으로. 정방향 list_building_districts 와 '
  '같은 판정(st_contains + parcel.geom)을 써야 두 화면이 같은 말을 한다. '
  'store_cnt 는 **그 땅**의 점포 수다(건물별로는 영영 못 가른다 — unit_business.unit_id 전량 NULL). '
  '한 땅에 여러 동이면 대표 동(연면적 최대) 한 채만 싣고 bld_cnt_in_pnu 로 몇 동인지 알린다. '
  'p_cat_m(업종 중분류 코드 배열 · 2026-10-11a)을 주면 그 업종 점포가 1곳 이상인 땅만 그 업종 점포 많은 순으로 '
  '주고 cat_store_cnt 에 그 수를 싣는다(null 이면 옛 결과 그대로 · cat_store_cnt 는 null).';

-- Supabase 는 새 함수를 anon 에게 자동으로 연다(pg_default_acl) — 만든 자리에서 닫는다.
revoke all on function list_district_buildings(text, int, int, text[]) from public, anon, authenticated;

-- ── api 쌍둥이 — 화면이 부르는 문(🚪 grant 는 여기에만) ─────────────────────────────
create or replace function api.list_district_buildings(
  p_district_id text,
  p_limit       int default 50,
  p_offset      int default 0,
  p_cat_m       text[] default null
)
returns table (
  pnu              char(19),
  store_cnt        int,
  cat_store_cnt    int,
  bld_cnt_in_pnu   int,
  bld_id           text,
  bld_nm           text,
  road_addr        text,
  jibun_addr       text,
  lat              double precision,
  lng              double precision,
  floor_cnt        int,
  min_floor        smallint,
  max_floor        smallint,
  has_roof         boolean,
  total_parcel_cnt bigint,
  total_bld_cnt    bigint
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_district_buildings(p_district_id, p_limit, p_offset, p_cat_m) $$;

revoke all on function api.list_district_buildings(text, int, int, text[]) from public, anon, authenticated;
grant execute on function api.list_district_buildings(text, int, int, text[]) to anon, authenticated;

commit;

notify pgrst, 'reload schema';
