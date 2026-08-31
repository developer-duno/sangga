-- =====================================================================
-- 마이그레이션 2026-08-31b — 상권 → 건물 다리 (역방향 조회)
-- =====================================================================
-- 실행법: python scripts/dbx.py -f supabase/migrations/2026-08-31b_district_buildings.sql
--   → 그다음 반드시 `python scripts/post_load.py --check` (노출면 재측정).
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 하나 — 지도가 막다른 길이었다
-- ─────────────────────────────────────────────────────────────────────
-- 지금 지도는 상권을 누르면 **이름과 유형만** 알려주고 끝난다. 거기서 건물로 넘어갈
-- 길이 없다. 그런데 창업자는 **건물 이름을 모른다** — 그들이 아는 것은 "이 동네"뿐이다.
-- 검색은 이름·주소를 알아야 쓰므로, 지도로 들어온 사람에게 이 앱은 길이 끊겨 있었다.
--
-- 정방향(`list_building_districts`, 2026-08-14b)의 짝을 만든다.
-- ⛔ **판정은 정방향과 글자 그대로 같아야 한다** — `st_contains(d.geom, parcel.geom)`.
--    다른 자를 쓰면 "상권 목록으로 들어간 건물인데 그 건물 화면엔 그 상권이 안 뜨는"
--    모순이 난다. 필지는 폴리곤이 아니라 **점 하나**라, 경계에 걸친 땅은 "걸쳐서 빠지는"
--    것이 아니라 **그 대표점이 안쪽이냐 바깥이냐**로 갈린다(화면 문구도 그렇게 쓴다).
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 미리 굽지 않나 (2026-08-31 라이브 실측)
-- ─────────────────────────────────────────────────────────────────────
-- 형제 자산 `mv_district_industry_mix`(2026-08-22c)는 살아있는 쿼리가 12.5초라 미리
-- 구웠다. 그건 **전체 상권 × 전체 점포**를 한꺼번에 세는 모양이었기 때문이고, 여기는
-- **상권 하나**만 본다. 실측:
--     · 대전역1번 출구(1,171동 — 전국 최대) : 찬 517ms / 더운 34.5ms
--     · 명동 남대문…관광특구(1,098동)       : 찬 578ms / 더운 12ms
-- 사전계산 표를 만들면 갱신 의무(post_load)만 늘고 얻는 게 없다.
-- ⚠️ 다만 **찬 캐시 0.5초는 첫 방문자가 문다** — 화면은 "불러오는 중"을 반드시 보여준다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 건물이 아니라 **땅(필지)** 단위로 세로줄을 만드나
-- ─────────────────────────────────────────────────────────────────────
-- 점포 수는 **필지 단위로만** 셀 수 있다(`unit_business.pnu`. `unit_id` 는 295만 행이
-- 전부 NULL 이라 건물 단위로는 영영 못 가른다). 그래서 건물을 그냥 줄세우면 한 땅에 선
-- 동들이 **같은 점포 수를 나눠 갖는 게 아니라 똑같이 복사해 갖는다.**
-- 실측(명동, 점포 많은 순 상위 10): `롯데호텔 및 백화점 317` 이 **네 줄 연달아** 나온다
-- (본관동·신관동·부속건물 2동이 한 필지 1114011100100010000 에 서 있다).
--
-- 게다가 한 땅에 동이 많은 곳은 예외가 아니라 **정상**이다(전국 실측):
--     한 필지 1동 176,488 · 2~5동 9,328 · 6~20동 1,989 · **20동 초과 637곳(21,635동)**
--     최대 168동 = 헬리오시티. 그 뒤로 창덕궁 157 · 서울대 154 · 경복궁 140.
--     ⓘ 대전 원동 65-1 은 261제곱미터 땅에 164동인데, 전통시장 점포를 건축물대장이
--       **호실 단위로**(1층 제100호 …) 관리해서다. 전국에 1,689동(0.7%)뿐이라
--       따로 거르지 않는다 — 걸러 봐야 "왜 이 시장이 안 보이나"가 된다.
-- 헬리오시티를 168줄로 쏟아 놓으면 목록이 죽는다. 그래서 **땅이 한 줄**이고, 그 줄이
-- 몇 동인지(`bld_cnt_in_pnu`)를 함께 실어 화면이 "같은 땅에 N동"을 적는다
-- (검색 결과가 2026-08-11 부터 쓰는 것과 **같은 배지**다 — 규칙을 새로 만들지 않는다).
--
-- ⛔ 그래서 `store_cnt` 는 "이 건물의 점포"가 아니라 **"이 땅의 점포"** 다.
--    화면 문구가 이것을 흐리면 층별 화면의 점포 칸과 세는 대상이 어긋나 보인다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 함수가 둘인가
-- ─────────────────────────────────────────────────────────────────────
-- 목록(50곳)에 그 땅의 동을 전부 실으면 대전역 상권에서 **606동**이 딸려 온다. 그런데
-- 필지의 94%(176,488/188,442)는 동이 하나뿐이라, 그 짐은 대부분 쓰이지 않는다.
-- 그래서 목록은 **대표 동 하나만** 싣고, 여러 동인 줄을 **펼칠 때만** 두 번째 함수를
-- 부른다.

set statement_timeout = '300s';

-- ─────────────────────────────────────────────────────────────────────
-- 1) list_district_buildings — 상권 안의 땅 목록 (점포 많은 순)
-- ─────────────────────────────────────────────────────────────────────
-- ⚠️ 파라미터를 `p_` 로 시작하는 이유: `district_id` 는 컬럼 이름과 겹친다. 겹치면
--    PostgreSQL 이 컬럼을 우선 집어 `where d.district_id = d.district_id`(= 전국)가 된다.
create or replace function list_district_buildings(
  p_district_id text,
  p_limit       int default 50,
  p_offset      int default 0
)
returns table (
  pnu              char(19),
  -- 이 **땅**의 점포 수(최신 분기). 건물별로 가를 수 없다 — 위 머리말 참조.
  store_cnt        int,
  -- 이 땅에 선 동 수(층 자료가 있는 것만). 1 보다 크면 화면이 "같은 땅에 N동"을 적는다.
  bld_cnt_in_pnu   int,
  -- 대표 동 = 연면적이 가장 큰 동. 검색 결과와 같은 칸들이라 화면 배선이 그대로 붙는다.
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
  -- 상한에 잘리기 전 전체 규모. 모든 행에 같은 값으로 실어 "몇 곳 중 몇 곳"을 정직하게
  -- 말하게 한다(검색의 total_cnt 와 같은 수법).
  total_parcel_cnt bigint,
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
    select ub.pnu, count(*)::int as n
    from unit_business ub
    join scope sc on sc.pnu = ub.pnu
    where ub.snapshot_ym = (select max(u.snapshot_ym) from unit_business u)
    group by 1
  ),
  land as (
    -- ⓘ 창 함수는 GROUP BY **뒤에** 돈다 → count(*) over () = 땅 수,
    --    sum(count(*)) over () = 동 수. 둘을 한 번에 얻으려고 이 모양을 쓴다.
    select e.pnu,
           coalesce(max(s.n), 0)::int as store_cnt,
           count(*)::int              as bld_cnt_in_pnu,
           count(*)      over ()      as total_parcel_cnt,
           sum(count(*)) over ()      as total_bld_cnt
    from elig e
    left join stores s on s.pnu = e.pnu
    group by e.pnu
  ),
  page as (
    -- ⛔ 무거운 조인(주소 조립·좌표·층 집계) 전에 **상한을 먼저** 건다.
    --    검색 함수가 "25행에만 필요하다"며 쓰는 것과 같은 수법이다.
    -- 정렬 tie-break 에 pnu 를 둔다 — 없으면 같은 점포 수끼리 순서가 흔들려
    -- '더 보기'가 이미 본 줄을 다시 가져오거나 건너뛴다.
    select *
    from land
    order by store_cnt desc, pnu
    limit  greatest(1, least(coalesce(p_limit, 50), 200))
    offset greatest(0, coalesce(p_offset, 0))
  )
  select
    pg.pnu,
    pg.store_cnt,
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
  order by pg.store_cnt desc, pg.pnu;
$$;

comment on function list_district_buildings(text, int, int) is
  '상권 하나에 속한 **땅(필지)** 목록을 점포 많은 순으로. 정방향 list_building_districts 와 '
  '같은 판정(st_contains + parcel.geom)을 써야 두 화면이 같은 말을 한다. '
  'store_cnt 는 **그 땅**의 점포 수다(건물별로는 영영 못 가른다 — unit_business.unit_id 전량 NULL). '
  '한 땅에 여러 동이면 대표 동(연면적 최대) 한 채만 싣고 bld_cnt_in_pnu 로 몇 동인지 알린다 — '
  '동 목록은 펼칠 때 list_parcel_buildings 로 따로 받는다(필지 94%가 1동이라 미리 실으면 짐만 된다). '
  '⛔ 미리 굽지 않는다: 상권 하나만 보므로 최대 상권도 찬 캐시 0.5초·더운 35ms(2026-08-31 실측).';

-- ⛔ Supabase 는 새로 만드는 함수를 anon 에게 **자동으로** 연다(pg_default_acl). 기본 권한을
--    닫아 뒀어도 **만든 자리에서 한 번 더** 닫는다 — 그 기본값은 "그것을 실행한 롤이 만드는
--    것"에만 걸리기 때문이다. 이 줄을 빠뜨린 채 적용했다가 실측으로 잡았다(2026-08-31:
--    revoke 없이 만드니 anon 실행 권한이 곧바로 t 였다). 형제(2026-08-28a·08-31a)와 같은 처방.
revoke all on function list_district_buildings(text, int, int) from public, anon, authenticated;

-- ─────────────────────────────────────────────────────────────────────
-- 2) list_parcel_buildings — 한 땅의 동 목록 (펼칠 때만)
-- ─────────────────────────────────────────────────────────────────────
create or replace function list_parcel_buildings(p_pnu text)
returns table (
  bld_id        text,
  bld_nm        text,
  dong_nm       text,
  total_area_m2 numeric,
  floor_cnt     int,
  min_floor     smallint,
  max_floor     smallint,
  has_roof      boolean
)
language sql
stable
security definer
set search_path = public
as $$
  select
    b.bld_id,
    b.display_nm as bld_nm,
    -- 동명칭을 함께 준다 — 한 땅의 동들은 **이름이 같은 일이 흔해서**(롯데호텔 4동 전부
    -- '롯데호텔 및 백화점') 이것 없이는 사용자가 무엇을 고르는지 알 수 없다.
    -- ⓘ 새로 여는 칸이 아니다: display_nm 은 건물명이 비면 이미 동명칭을 그대로 내보낸다.
    --    그래도 성명 가림을 한 번 더 통과시킨다 — 정상 동명칭엔 무해하고, 만에 하나
    --    사람 이름이 끝에 붙어 있으면 지운다.
    nullif(btrim(mask_person_name(b.dong_nm)), '') as dong_nm,
    b.total_area_m2,
    fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof
  from building b
  join lateral (
    select count(*)::int                                    as floor_cnt,
           min(s.floor_no) filter (where s.floor_no <> 99)  as min_floor,
           max(s.floor_no) filter (where s.floor_no <> 99)  as max_floor,
           coalesce(bool_or(s.floor_no = 99), false)        as has_roof
    from v_building_floor_stack s
    where s.bld_id = b.bld_id
  ) fs on true
  -- ⛔ `p_pnu::char(19)` 의 캐스트를 지우지 말 것. pnu 컬럼이 char(19) 인데 text 와 견주면
  --    **컬럼 쪽**이 text 로 캐스트돼 인덱스가 통째로 죽는다(2026-08-16b 실측 459.8ms↔0.796ms).
  where b.pnu = p_pnu::char(19)
    and exists (
      select 1 from building_floor f
      where f.bld_id = b.bld_id and f.floor_no is not null
    )
  order by b.total_area_m2 desc nulls last, b.bld_id;
$$;

comment on function list_parcel_buildings(text) is
  '한 필지에 선 동 목록. 목록 화면에서 "같은 땅에 N동"을 **펼칠 때만** 부른다. '
  '층 자료 없는 동은 뺀다(눌러도 빈 화면이라 — 검색과 같은 규칙). '
  '동명칭을 함께 주는 이유: 한 땅의 동들은 건물명이 같은 일이 흔해 이름만으로는 못 가린다.';

-- 위와 같은 이유 — 만든 자리에서 닫는다.
revoke all on function list_parcel_buildings(text) from public, anon, authenticated;

-- ─────────────────────────────────────────────────────────────────────
-- 3) api 통과 함수 — 화면이 실제로 부르는 것
-- ─────────────────────────────────────────────────────────────────────
-- public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기) api 쪽에 통과 함수가 없으면
-- 화면에서 못 부른다.
create or replace function api.list_district_buildings(
  p_district_id text,
  p_limit       int default 50,
  p_offset      int default 0
)
returns table (
  pnu              char(19),
  store_cnt        int,
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
-- ⓘ 통과 함수는 search_path 를 **비운다** — 부르는 대상을 전부 스키마까지 적었으므로
--    빈 경로가 더 좁고, 형제 api 함수들과 같은 모양이다.
set search_path = ''
as $$ select * from public.list_district_buildings(p_district_id, p_limit, p_offset) $$;

revoke all on function api.list_district_buildings(text, int, int) from public, anon, authenticated;
grant execute on function api.list_district_buildings(text, int, int) to anon, authenticated;

create or replace function api.list_parcel_buildings(p_pnu text)
returns table (
  bld_id        text,
  bld_nm        text,
  dong_nm       text,
  total_area_m2 numeric,
  floor_cnt     int,
  min_floor     smallint,
  max_floor     smallint,
  has_roof      boolean
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_parcel_buildings(p_pnu) $$;

revoke all on function api.list_parcel_buildings(text) from public, anon, authenticated;
grant execute on function api.list_parcel_buildings(text) to anon, authenticated;

-- ⛔ public 쪽 두 함수는 끝까지 닫아 둔다 — 통과 함수가 security definer 라 소유자
--    권한으로 부르므로 anon 에게 열 필요가 없다.

-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';
