create function pg_temp.search_scope_v2(q text, sigungu text default null)
returns table (too_broad boolean, match_cnt int)
language plpgsql
stable
security definer
set search_path = public
set plan_cache_mode = force_custom_plan
as $$
#variable_conflict use_column
begin
  return query
with pat as not materialized (
    select case when search_key(q) is null then null
                else '%' || replace(replace(replace(search_key(q), '\', '\\'),
                                    '%', '\%'), '_', '\_') || '%'
           end as p,
           nullif(btrim(coalesce(sigungu, '')), '') as gu
  ),
  c as (
    select
      (select count(*) from mv_search_parcel pc cross join pat
        where pat.p is not null
          -- ⛔ `::char(5)` 를 지우지 말 것 — 컬럼이 char(5) 인데 text 와 견주면 **컬럼 쪽**이
          --    text 로 캐스트돼 색인이 Index Cond 가 아니라 Filter 로 떨어진다(라이브 실측
          --    2026-09-10: Parallel Seq Scan 188,442행·버퍼 5,312·116ms → Index Scan 12,138행·버퍼 353·8ms).
          --    형제 `search_stores` 가 같은 처방을 쓴다(결정 0028 §백로그).
          -- ⚠️ 5자보다 긴 입력은 bpchar 캐스트가 조용히 자른다 — 구 코드는 서버 목록에서만
          --    오고 화면도 /^\d{5}$/ 로 막으므로(src/lib/urlState.ts) 실사용 0건이다.
          -- ⛔ `pat.gu is null or` 절반은 그대로 둔다 — 이 함수는 구를 안 고른 전국 검색을
          --    일부러 허용한다(구 없이는 답이 안 되는 `search_stores` 와 다른 점이다).
          and (pat.gu is null or pc.sigungu_code = pat.gu::char(5))
          and (pc.road_addr_key  like pat.p escape '\'
            or pc.jibun_addr_key like pat.p escape '\')) as addr_cnt,
      (select count(*) from building b
         join mv_search_parcel pc on pc.pnu = b.pnu
         cross join pat
        where pat.p is not null
          and (pat.gu is null or pc.sigungu_code = pat.gu::char(5))
          and (pat.gu is null or (b.pnu >= pat.gu::char(19)
                                        and b.pnu <= (pat.gu || repeat('9',14))::char(19)))
          and b.nm_key like pat.p escape '\')            as nm_cnt
  )
  select greatest(c.addr_cnt, c.nm_cnt) > search_scope_limit(),
         least(greatest(c.addr_cnt, c.nm_cnt), 2147483647)::int
  from c;
end;
$$;

create function pg_temp.search_buildings_v2(q text, lim int default 25, sigungu text default null)
returns table (
  bld_id         text,
  pnu            char(19),
  bld_nm         text,
  road_addr      text,
  jibun_addr     text,
  -- 상권 지도의 마커 자리(2026-08-14e). **필지(parcel.geom)** 좌표라 한 땅에 여러 동이면
  -- 같은 점이고, 상권 판정(list_building_districts)과 같은 칸을 본다 — 마커와 글자가
  -- 서로 다른 칸을 보면 "지도는 상권 밖, 글자는 상권 안"이 된다.
  lat            double precision,
  lng            double precision,
  bld_cnt_in_pnu int,
  floor_cnt      int,
  min_floor      smallint,
  max_floor      smallint,
  has_roof       boolean,
  total_cnt      bigint
)
language plpgsql
stable
security definer
set search_path = public
set plan_cache_mode = force_custom_plan
as $$
#variable_conflict use_column
begin
  return query
with pat as not materialized (
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
       -- ⛔ `::char(5)` 를 지우지 말 것 — 컬럼이 char(5) 인데 text 와 견주면 **컬럼 쪽**이
       --    text 로 캐스트돼 색인이 Index Cond 가 아니라 Filter 로 떨어진다(라이브 실측
       --    2026-09-10: Parallel Seq Scan 188,442행·버퍼 5,312·116ms → Index Scan 12,138행·버퍼 353·8ms).
       --    형제 `search_stores` 가 같은 처방을 쓴다(결정 0028 §백로그).
       -- ⚠️ 5자보다 긴 입력은 bpchar 캐스트가 조용히 자른다 — 구 코드는 서버 목록에서만
       --    오고 화면도 /^\d{5}$/ 로 막으므로(src/lib/urlState.ts) 실사용 0건이다.
       -- ⛔ `pat.gu is null or` 절반은 그대로 둔다 — 이 함수는 구를 안 고른 전국 검색을
       --    일부러 허용한다(구 없이는 답이 안 되는 `search_stores` 와 다른 점이다).
       and (pat.gu is null or pc.sigungu_code = pat.gu::char(5))
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
       and (pat.gu is null or pc.sigungu_code = pat.gu::char(5))
       and (pat.gu is null or (b.pnu >= pat.gu::char(19)
                                     and b.pnu <= (pat.gu || repeat('9',14))::char(19)))
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
end;
$$;

create function pg_temp.search_stores_v2(
  q        text,
  lim      int  default 50,
  sigungu  text default null,
  p_offset int  default 0
)
returns table (
  pnu               char(19),
  bld_id            text,
  bld_nm            text,
  road_addr         text,
  jibun_addr        text,
  lat               double precision,
  lng               double precision,
  bld_cnt_in_pnu    int,
  floor_cnt         int,
  min_floor         smallint,
  max_floor         smallint,
  has_roof          boolean,
  matched_names     text[],
  match_store_cnt   int,
  total_parcel_cnt  bigint,
  total_store_cnt   bigint,
  too_broad         boolean,
  store_snapshot_ym text
)
language plpgsql
stable
security definer
set search_path = public
set plan_cache_mode = force_custom_plan
as $$
#variable_conflict use_column
begin
  return query
with pat as not materialized (
    -- 전처리는 형제 search_buildings 의 것을 **글자 그대로** 물려받는다 — 같은 검색어에
    -- 건물과 가게가 다른 답을 내면 안 된다. k 는 **이스케이프 전** 값이다(정확일치 정렬용).
    select
      case when esc.v is null then null else '%' || esc.v || '%' end as p,
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
  -- ① 이름이 걸린 **땅**을 찾는다. 구를 안 골랐으면 0건이다(결정 0007) —
  --    상호는 같은 이름이 전국에 널려 있어 구 없이는 답이 될 수 없다.
  hit as (
    select m.pnu, p.road_addr, m.store_names, m.store_snapshot_ym
      from mv_parcel_store_names m
      -- ⓘ road_addr 은 아래 정렬의 tie-break 에만 쓴다. 요약표에 road_addr 을 또 담지
      --    않는 이유는, 같은 사실을 두 표가 들고 있으면 언젠가 갈리기 때문이다 —
      --    필지 기본키 조회 한 번이 그 위험보다 싸다.
      join parcel p on p.pnu = m.pnu
      cross join pat
     where pat.p is not null
       and pat.gu is not null
       -- ⛔ `::char(5)` 를 지우지 말 것 — 컬럼이 char(5) 인데 text 와 견주면 **컬럼 쪽**이
       --    text 로 캐스트돼 색인이 Index Cond 가 아니라 Filter 로 떨어진다(형제 표 라이브
       --    실측 2026-09-10: 2글자 검색 859.9ms → 76.6ms, 훑는 행 188,442 → 12,138).
       --    `list_parcel_buildings` 의 `p_pnu::char(19)` 와 같은 처방(2026-08-16b).
       -- ⚠️ 5자보다 긴 입력은 bpchar 캐스트가 조용히 자른다 — 구 코드는 서버 목록에서만
       --    오므로 실사용 0건이다.
       and m.sigungu_code = pat.gu::char(5)
       and m.store_names_key like pat.p escape '\'
       -- 층 자료가 아예 없는 건물뿐인 땅은 눌러도 빈 화면이라 뺀다
       -- (검색·결정 0025 와 **같은 규칙** — 갈리면 들어온 길에 따라 다른 답이 된다).
       and exists (
         select 1 from building b
          where b.pnu = m.pnu
            and exists (select 1 from building_floor f
                         where f.bld_id = b.bld_id and f.floor_no is not null)
       )
  ),
  -- ② 그 땅 안에서 **어느 이름이 몇 곳** 걸렸나. 요약표 한 줄 안에서 센다(되짚기 없음).
  matched as (
    select h.pnu, h.road_addr, h.store_snapshot_ym,
           agg.n        as match_store_cnt,
           agg.exact_hit
      -- ⓘ 화면에 적을 이름 셋(matched_names)은 여기서 안 만든다 — 아래 rows_out 의
      --    lateral 로 내려갔다(2026-09-10b · 0028 §백로그 🟡-5). 여기서 만들면
      --    게이트 상한(6,000땅)까지 땅마다 돌고 나서 50줄만 낸다.
      from hit h
      cross join pat
      join lateral (
        select count(*)::int as n,
               coalesce(bool_or(search_key(u.nm) = pat.k), false) as exact_hit
          from unnest(h.store_names) as u(nm)
         where search_key(u.nm) like pat.p escape '\'
      ) agg on true
     -- ⓘ store_names_key 는 이름들을 '|' 로 이은 한 줄이라, 검색어가 그 이음매를 걸치면
     --    ①에서 걸리고도 실제 이름은 하나도 안 맞을 수 있다. 그 헛것을 여기서 뺀다 —
     --    그래야 아래 총계(땅 수·가게 수)가 화면에 서는 줄과 같은 말을 한다.
     where agg.n > 0
  ),
  tot as (
    select m.*,
           count(*) over ()               as total_parcel_cnt,
           sum(m.match_store_cnt) over () as total_store_cnt
      from matched m
  ),
  -- ③ 너무 넓은 검색어인가. 구 안 최다가 '학원' 강남 898땅이라 실제로는 거의 안 닿는
  --    안전망이다(구를 안 고르면 애초에 0건이라 여기 오지도 않는다).
  gate as (
    select coalesce((select max(t.total_parcel_cnt) from tot t), 0)
             > search_scope_limit() as broad
  ),
  page as (
    -- ⛔ 무거운 조인(대표 동·주소 조립·좌표·층 집계) 전에 **상한을 먼저** 건다.
    --    tie-break 에 pnu 를 둔다 — 없으면 같은 수끼리 순서가 흔들려 '더 보기'가
    --    이미 본 줄을 다시 가져오거나 건너뛴다(결정 0025 와 같은 이유).
    select t.*
      from tot t
      cross join gate g
     where not g.broad
     order by t.match_store_cnt desc,
              t.exact_hit       desc,
              t.road_addr       asc nulls last,
              t.pnu
     limit  greatest(1, least(coalesce(lim, 50), 200))
     offset greatest(0, coalesce(p_offset, 0))
  ),
  rows_out as (
    select
      pg.pnu,
      rep.bld_id,
      rep.bld_nm,
      p.road_addr,
      parcel_jibun_addr(p.sido_nm, p.sigungu_nm, p.emd_nm, p.jibun) as jibun_addr,
      -- ⛔ 좌표는 geom 에서만 뽑는다. parcel 의 lat/lng **칸**을 쓰면 검색·상권판정과
      --    자리가 갈려 "마커는 상권 밖인데 글자는 상권 안"이 된다(2026-08-14e 규칙).
      st_y(p.geom)::double precision as lat,
      st_x(p.geom)::double precision as lng,
      cnt.bld_cnt_in_pnu,
      fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof,
      mn.matched_names,
      pg.match_store_cnt,
      pg.total_parcel_cnt,
      pg.total_store_cnt,
      false as too_broad,
      pg.store_snapshot_ym::text as store_snapshot_ym,
      pg.exact_hit
    from page pg
    -- ⓘ pat 은 한 줄짜리 CTE 라 cross join 이 행수를 바꾸지 않는다. 아래 mn lateral 이
    --    검색 패턴(pat.p)과 정확일치 키(pat.k)를 쓰므로 여기서 한 번 끌어온다.
    cross join pat
    join parcel p on p.pnu = pg.pnu
    join lateral (
      -- 대표 동 = 연면적 최대(결정 0025 와 같은 자). 층 자료 없는 동은 뺀다.
      select b.bld_id, b.display_nm as bld_nm
        from building b
       where b.pnu = pg.pnu
         and exists (select 1 from building_floor f
                      where f.bld_id = b.bld_id and f.floor_no is not null)
       order by b.total_area_m2 desc nulls last, b.bld_id
       limit 1
    ) rep on true
    join lateral (
      -- 1 보다 크면 화면이 "같은 땅에 N동"을 적고, 누르면 list_parcel_buildings 로 펼친다.
      -- ⛔ 그 함수도 층 자료 없는 동을 빼므로 여기서도 같은 조건으로 센다 — 안 그러면
      --    "3동"이라 적어 놓고 펼치면 2동만 나온다.
      select count(*)::int as bld_cnt_in_pnu
        from building b2
       where b2.pnu = pg.pnu
         and exists (select 1 from building_floor f
                      where f.bld_id = b2.bld_id and f.floor_no is not null)
    ) cnt on true
    join lateral (
      -- ⛔ 층수 규칙을 여기서 새로 정하지 않는다 — 검색 함수의 것을 글자 그대로 옮겼다.
      --    갈리면 같은 건물이 "지하2~15층"과 "지하2~99층"으로 갈린다.
      select count(*)::int                                    as floor_cnt,
             min(s.floor_no) filter (where s.floor_no <> 99)  as min_floor,
             max(s.floor_no) filter (where s.floor_no <> 99)  as max_floor,
             coalesce(bool_or(s.floor_no = 99), false)        as has_roof
        from v_building_floor_stack s
       where s.bld_id = rep.bld_id
    ) fs on true
    join lateral (
      -- 화면에 적을 이름 최대 3개 — 정확히 같은 이름 먼저, 그다음 가나다.
      -- ⛔ 원문 그대로 낸다(간판에 걸린 공개 이름이다 — 결정 0028 결정 5).
      -- ⛔ 이 셈을 ②(matched)로 되돌리지 말 것 — 거기서 하면 게이트 상한(6,000땅)까지
      --    땅마다 unnest→like→정렬을 돌고 나서 50줄만 낸다. 여기(page 뒤)면 **page 가 자른 줄 수만큼**
      --    (기본 50 · 상한 200)이다(2026-09-10b · 0028 §백로그 🟡-5).
      -- ⓘ 되짚는 곳이 점포 표가 아니라 **요약표의 같은 한 줄**(유일 색인 idx_mpsn_pnu)이라
      --    "점포 표 되짚기 금지(3.2초)"와는 무관하다.
      select array_agg(d.nm order by d.is_exact desc, d.nm) as matched_names
      from (
        select distinct u2.nm,
               (search_key(u2.nm) = pat.k) as is_exact
          from mv_parcel_store_names m2,
               unnest(m2.store_names) as u2(nm)
         where m2.pnu = pg.pnu
           and search_key(u2.nm) like pat.p escape '\'
         order by is_exact desc, nm
         limit 3
      ) d
    ) mn on true
    union all
    -- ⛔ 게이트에 걸리면 **0건이 아니라 한 줄**이다 — 0건이면 화면이 "그런 가게가 없다"고
    --    말하게 되는데 사실은 "너무 많다"이다. 지금의 search_scope 는 상호를 안 세므로
    --    (그걸 고치면 "기존 검색 함수 불변"이 깨진다) 이 함수가 제 총계를 함께 낸다.
    select
      null::char(19), null::text, null::text, null::text, null::text,
      null::double precision, null::double precision,
      null::int, null::int, null::smallint, null::smallint, null::boolean,
      null::text[], null::int,
      gr.total_parcel_cnt, gr.total_store_cnt,
      true, gr.store_snapshot_ym::text,
      false
    from (
      select max(t.total_parcel_cnt) as total_parcel_cnt,
             max(t.total_store_cnt)  as total_store_cnt,
             max(t.store_snapshot_ym) as store_snapshot_ym
        from tot t
    ) gr
    cross join gate g
    where g.broad
  )
  select
    o.pnu, o.bld_id, o.bld_nm, o.road_addr, o.jibun_addr, o.lat, o.lng,
    o.bld_cnt_in_pnu, o.floor_cnt, o.min_floor, o.max_floor, o.has_roof,
    o.matched_names, o.match_store_cnt, o.total_parcel_cnt, o.total_store_cnt,
    o.too_broad, o.store_snapshot_ym
  from rows_out o
  order by
    o.too_broad        desc,
    o.match_store_cnt  desc nulls last,
    o.exact_hit        desc,
    o.road_addr        asc nulls last,
    o.pnu;
end;
$$;


-- 라이브 api 래퍼와 **같은 모양**(language sql · search_path='' · security definer 아님)으로
-- v2 를 감싼다. 화면은 이 껍데기를 부르므로, 껍데기가 효과를 죽이는지 여기서 본다.
create function pg_temp.api_buildings_v2(q text, lim int default 25, sigungu text default null)
returns table (bld_id text, pnu char(19), bld_nm text, road_addr text, jibun_addr text,
               lat double precision, lng double precision, bld_cnt_in_pnu int, floor_cnt int,
               min_floor smallint, max_floor smallint, has_roof boolean, total_cnt bigint)
language sql stable set search_path = ''
as $W$ select * from pg_temp.search_buildings_v2(q, lim, sigungu) $W$;

create function pg_temp.api_scope_v2(q text, sigungu text default null)
returns table (too_broad boolean, match_cnt int)
language sql stable set search_path = ''
as $W$ select * from pg_temp.search_scope_v2(q, sigungu) $W$;

set statement_timeout = '600s';

create function pg_temp.bench_wrapper()
returns table (kind text, gu text, q text, direct_ms numeric, wrapped_ms numeric, live_api_ms numeric, same boolean)
language plpgsql as $B$
declare
  t0 timestamptz; d numeric; w numeric; L numeric; h1 text; h2 text;
  gus text[] := array['11680','11710','11440','30170','11110'];
  g text; s text;
begin
  foreach g in array gus loop
    foreach s in array array['빌딩','플라자'] loop
      perform 1 from pg_temp.search_buildings_v2(s,25,g) a;
      perform 1 from pg_temp.api_buildings_v2(s,25,g) b;
      perform 1 from api.search_buildings(s,25,g) c;
      t0:=clock_timestamp(); perform 1 from pg_temp.search_buildings_v2(s,25,g) a2;
      d:=extract(epoch from clock_timestamp()-t0)*1000;
      t0:=clock_timestamp(); perform 1 from pg_temp.api_buildings_v2(s,25,g) b2;
      w:=extract(epoch from clock_timestamp()-t0)*1000;
      t0:=clock_timestamp(); perform 1 from api.search_buildings(s,25,g) c2;
      L:=extract(epoch from clock_timestamp()-t0)*1000;
      select md5(string_agg(t::text,'|' order by t::text)) into h1 from pg_temp.api_buildings_v2(s,25,g) t;
      select md5(string_agg(t::text,'|' order by t::text)) into h2 from api.search_buildings(s,25,g) t;
      kind:='buildings'; gu:=g; q:=s; direct_ms:=round(d,1); wrapped_ms:=round(w,1);
      live_api_ms:=round(L,1); same:=(h1 is not distinct from h2); return next;
    end loop;
    foreach s in array array['빌딩'] loop
      perform 1 from pg_temp.search_scope_v2(s,g) a;
      perform 1 from pg_temp.api_scope_v2(s,g) b;
      perform 1 from api.search_scope(s,g) c;
      t0:=clock_timestamp(); perform 1 from pg_temp.search_scope_v2(s,g) a2;
      d:=extract(epoch from clock_timestamp()-t0)*1000;
      t0:=clock_timestamp(); perform 1 from pg_temp.api_scope_v2(s,g) b2;
      w:=extract(epoch from clock_timestamp()-t0)*1000;
      t0:=clock_timestamp(); perform 1 from api.search_scope(s,g) c2;
      L:=extract(epoch from clock_timestamp()-t0)*1000;
      select md5(string_agg(t::text,'|' order by t::text)) into h1 from pg_temp.api_scope_v2(s,g) t;
      select md5(string_agg(t::text,'|' order by t::text)) into h2 from api.search_scope(s,g) t;
      kind:='scope'; gu:=g; q:=s; direct_ms:=round(d,1); wrapped_ms:=round(w,1);
      live_api_ms:=round(L,1); same:=(h1 is not distinct from h2); return next;
    end loop;
  end loop;
end;
$B$;

\echo '--- api 껍데기가 효과를 죽이나 (direct=v2 직접 / wrapped=v2를 api모양 껍데기로 / live_api=지금 라이브 api)'
select * from pg_temp.bench_wrapper() order by kind, gu, q;
