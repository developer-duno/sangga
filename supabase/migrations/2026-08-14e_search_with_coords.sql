-- =====================================================================
-- 검색 결과에 좌표 두 칸을 실어 준다 (2026-08-14e) — 상권 지도 마커용
-- =====================================================================
-- ## 왜 필요한가
--
-- 결정 0010 의 상권 지도(Track B)가 "지금 고른 건물이 어디쯤인가"를 마커로 찍으려는데,
-- 검색 결과(`search_buildings`)에 **좌표가 없다.** 화면이 가진 것은 bld_id·pnu·주소뿐이라
-- 마커를 찍으려면 건물을 고를 때마다 좌표를 따로 물어야 한다 — 왕복이 하나 더 늘고,
-- 그 왕복이 실패하면 마커만 조용히 사라진다. 이미 필지를 조인하고 있으므로 같은 자리에서
-- 두 칸을 더 얹는 편이 싸고 확실하다.
--
-- ## 왜 parcel.lat/lng 칸이 아니라 geom 에서 뽑나
--
-- parcel 에는 lat·lng 칸도 있지만, 그 둘과 geom 은 **서로 다른 시점에 채워질 수 있는
-- 별개의 칸**이다. 상권 판정(`list_building_districts`)은 `st_contains(d.geom, p.geom)`
-- 으로 **geom 만** 본다. 마커를 lat/lng 칸에서 뽑으면 두 칸이 어긋난 필지에서
-- "지도 위 마커는 상권 밖인데 아래 글자는 상권 안"이라고 말하게 된다 — 에러가 안 나고
-- 눈으로만 이상한, 가장 찾기 어려운 종류의 어긋남이다. 같은 칸을 보게 못박는다.
--
-- ## 왜 create or replace 가 아니라 drop 인가
--
-- returns table 의 칸 목록은 함수 시그니처의 일부라 `create or replace` 로는 못 바꾼다
-- (`cannot change return type of existing function`). 지우고 다시 만들면 권한도 함께
-- 사라지므로 **grant 를 반드시 다시 준다** — 안 주면 화면이 401 로 죽는다
-- (2026-08-13 에 함수 권한을 회수했다가 층별 화면이 통째로 401 이 된 전례가 있다).
--
-- ## 좌표가 없는 필지
--
-- `st_y(null)` 은 NULL 이다. 프론트는 lat·lng 를 **선택 필드**로 받아 없으면 마커를
-- 안 찍는다 — 없는 좌표를 0,0(아프리카 앞바다)으로 채우지 않는다.

begin;

drop function if exists search_buildings(text, int, text);

create or replace function search_buildings(q text, lim int default 25, sigungu text default null)
returns table (
  bld_id         text,
  pnu            char(19),
  bld_nm         text,
  road_addr      text,
  jibun_addr     text,
  lat            double precision,
  lng            double precision,
  bld_cnt_in_pnu int,
  floor_cnt      int,
  min_floor      smallint,
  max_floor      smallint,
  has_roof       boolean,
  total_cnt      bigint
)
language sql
stable
security definer
set search_path = public
as $$
  with pat as (
    select
      case when esc.v is null then null else '%' || esc.v || '%' end as p,
      case when esc.v is null then null else '%' || esc.v      end as p_end,
      -- ⚠️ k 는 **이스케이프 전** 값이다(정확일치·앞글자일치 정렬에 쓴다).
      search_key(q) as k,
      esc.gu
    from (
      select case when search_key(q) is null then null
                  else replace(replace(replace(search_key(q), '\', '\\'),
                               '%', '\%'), '_', '\_')
             end as v,
             nullif(btrim(coalesce(sigungu, '')), '') as gu
    ) esc
  ),
  -- ① 주소 두 칸은 같은 표라 한 번만 훑는다. 그 표는 **검색 전용 요약표**이고,
  --    구를 골랐으면 그 구만 본다(이제 이게 기본 경로다 — idx_msp_sigungu).
  --    `limit 상한+1` 이 범위 게이트를 겸한다(구를 안 고른 경로의 안전망).
  addr as materialized (
    select pc.pnu, pc.road_addr, pc.jibun_addr_key
      from mv_search_parcel pc
      cross join pat
     where pat.p is not null
       and (pat.gu is null or pc.sigungu_code = pat.gu)
       and (pc.road_addr_key  like pat.p escape '\'
         or pc.jibun_addr_key like pat.p escape '\')
     limit search_scope_limit() + 1
  ),
  -- ⛔ 주소 가지와 이름 가지를 OR 하나로 합치지 말 것 — 서로 다른 두 표라 조인 전에
  --    한 표를 못 걸러 gin_trgm 인덱스가 통째로 무력화된다(2026-08-08 실측).
  nm as materialized (
    select b.bld_id, b.pnu, b.nm_key, b.display_nm as bld_nm,
           pc.road_addr, pc.jibun_addr_key
      from building b
      join mv_search_parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null
       and (pat.gu is null or pc.sigungu_code = pat.gu)
       and b.nm_key like pat.p escape '\'
     limit search_scope_limit() + 1
  ),
  gate as (
    select ((select count(*) from addr) > search_scope_limit()
         or (select count(*) from nm)   > search_scope_limit()) as broad
  ),
  hit as (
    select b.bld_id, b.pnu, b.nm_key, b.display_nm as bld_nm,
           a.road_addr, a.jibun_addr_key
      from addr a
      join building b on b.pnu = a.pnu
     where not (select g.broad from gate g)
    union
    select n.bld_id, n.pnu, n.nm_key, n.bld_nm, n.road_addr, n.jibun_addr_key
      from nm n
     where not (select g.broad from gate g)
  ),
  eligible as (
    select h.*,
           count(*) over () as total_cnt,
           coalesce(h.jibun_addr_key like (select p_end from pat) escape '\', false)
             as jibun_hit
    from hit h
    -- 층 자료가 아예 없는 건물은 빈 스택이 되므로 뺀다(2026-08-13 실측: 242,631 중 239개).
    where exists (
      select 1 from building_floor f
      where f.bld_id = h.bld_id and f.floor_no is not null
    )
  ),
  top as (
    select e.*
    from eligible e
    cross join pat
    order by
      e.jibun_hit                    desc,
      (e.nm_key = pat.k)             desc nulls last,
      (e.nm_key like pat.k || '%')   desc nulls last,
      (e.bld_nm is null)             asc,
      length(e.bld_nm)               asc nulls last,
      e.road_addr                    asc nulls last,
      e.bld_id
    limit greatest(1, least(coalesce(lim, 25), 100))
  )
  -- ② 지번주소 조립·좌표 뽑기는 여기서 처음 한다 — 25행에만 필요하다.
  --    parcel 은 pnu 가 기본키라 이 조인은 25번의 색인 조회다(요약표에 geom 을 넣어
  --    표를 키우는 것보다 싸다 — 요약표는 188,442행이고 검색마다 통째로 훑힌다).
  select
    t.bld_id, t.pnu, t.bld_nm, t.road_addr,
    parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun) as jibun_addr,
    st_y(p.geom)::double precision as lat,
    st_x(p.geom)::double precision as lng,
    (select count(*)::int from building b2 where b2.pnu = t.pnu) as bld_cnt_in_pnu,
    fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof,
    t.total_cnt
  from top t
  join mv_search_parcel pc on pc.pnu = t.pnu
  join parcel p on p.pnu = t.pnu
  join lateral (
    select
      count(*)::int                                    as floor_cnt,
      min(s.floor_no) filter (where s.floor_no <> 99)  as min_floor,
      max(s.floor_no) filter (where s.floor_no <> 99)  as max_floor,
      coalesce(bool_or(s.floor_no = 99), false)        as has_roof
    from v_building_floor_stack s
    where s.bld_id = t.bld_id
  ) fs on true
  order by
    t.jibun_hit                     desc,
    (t.nm_key = search_key(q))      desc nulls last,
    (t.nm_key like search_key(q) || '%') desc nulls last,
    (t.bld_nm is null)              asc,
    length(t.bld_nm)                asc nulls last,
    t.road_addr                     asc nulls last,
    t.bld_id;
$$;

comment on function search_buildings(text, int, text) is
  '§8.1 건물 검색. 건물 1개 = 1행이며 total_cnt로 정확한 전체 건수를 함께 준다. '
  'sigungu 를 주면 **그 구 안에서만** 찾는다(2026-08-13e, 사장님 결정) — 같은 건물 이름이 '
  '여러 구에 겹치기 때문이다(이름 33,851종 중 2,443종이 2개 이상 구에 존재). '
  'lat·lng 는 상권 지도의 마커 자리다(2026-08-14e) — **필지(parcel.geom) 좌표**라 한 땅에 '
  '여러 동이면 같은 점이고, 상권 판정(list_building_districts)과 같은 칸을 본다. '
  'security definer — 원본 표가 anon에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '입력의 % _ \ 는 서버가 리터럴로 이스케이프하고, 빈 검색어는 0건으로 잘라낸다. '
  '이름은 building.display_nm(동명칭 폴백 + 개인 성명 가림)만 본다 — 보이는 것 = 검색되는 것. '
  '주소는 mv_search_parcel(건물이 있는 필지만)을 본다. ⚠️ 자료 적재 후 `python scripts/post_load.py` 필수. '
  '⛔ 주소 가지와 이름 가지를 OR로 합치지 말 것 — 두 조인 테이블에 걸친 OR은 gin_trgm 인덱스를 무력화한다';

-- ⚠️ drop 으로 권한이 함께 사라졌다 — 다시 주지 않으면 화면이 401 로 죽는다.
grant execute on function search_buildings(text, int, text) to anon, authenticated;

commit;
