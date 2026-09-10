explain (analyze, buffers)
with pat as (


    select
      case when esc.v is null then null else '%' || esc.v || '%' end as p,
      search_key('학원') as k,
      esc.gu
    from (
      select case when search_key('학원') is null then null
                  else replace(replace(replace(search_key('학원'), '\', '\\'),
                               '%', '\%'), '_', '\_')
             end as v,
             nullif(btrim(coalesce('11680', '')), '') as gu
    ) esc
  ),


  hit as (
    select m.pnu, p.road_addr, m.store_names, m.store_snapshot_ym
      from mv_parcel_store_names m



      join parcel p on p.pnu = m.pnu
      cross join pat
     where pat.p is not null
       and pat.gu is not null






       and m.sigungu_code = pat.gu::char(5)
       and m.store_names_key like pat.p escape '\'


       and exists (
         select 1 from building b
          where b.pnu = m.pnu
            and exists (select 1 from building_floor f
                         where f.bld_id = b.bld_id and f.floor_no is not null)
       )
  ),

  matched as (
    select h.pnu, h.road_addr, h.store_snapshot_ym,
           agg.n        as match_store_cnt,
           agg.exact_hit



      from hit h
      cross join pat
      join lateral (
        select count(*)::int as n,
               coalesce(bool_or(search_key(u.nm) = pat.k), false) as exact_hit
          from unnest(h.store_names) as u(nm)
         where search_key(u.nm) like pat.p escape '\'
      ) agg on true



     where agg.n > 0
  ),
  tot as (
    select m.*,
           count(*) over ()               as total_parcel_cnt,
           sum(m.match_store_cnt) over () as total_store_cnt
      from matched m
  ),


  gate as (
    select coalesce((select max(t.total_parcel_cnt) from tot t), 0)
             > search_scope_limit() as broad
  ),
  page as (



    select t.*
      from tot t
      cross join gate g
     where not g.broad
     order by t.match_store_cnt desc,
              t.exact_hit       desc,
              t.road_addr       asc nulls last,
              t.pnu
     limit  greatest(1, least(coalesce(50, 50), 200))
     offset greatest(0, coalesce(0, 0))
  ),
  rows_out as (
    select
      pg.pnu,
      rep.bld_id,
      rep.bld_nm,
      p.road_addr,
      parcel_jibun_addr(p.sido_nm, p.sigungu_nm, p.emd_nm, p.jibun) as jibun_addr,


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


    cross join pat
    join parcel p on p.pnu = pg.pnu
    join lateral (

      select b.bld_id, b.display_nm as bld_nm
        from building b
       where b.pnu = pg.pnu
         and exists (select 1 from building_floor f
                      where f.bld_id = b.bld_id and f.floor_no is not null)
       order by b.total_area_m2 desc nulls last, b.bld_id
       limit 1
    ) rep on true
    join lateral (



      select count(*)::int as bld_cnt_in_pnu
        from building b2
       where b2.pnu = pg.pnu
         and exists (select 1 from building_floor f
                      where f.bld_id = b2.bld_id and f.floor_no is not null)
    ) cnt on true
    join lateral (


      select count(*)::int                                    as floor_cnt,
             min(s.floor_no) filter (where s.floor_no <> 99)  as min_floor,
             max(s.floor_no) filter (where s.floor_no <> 99)  as max_floor,
             coalesce(bool_or(s.floor_no = 99), false)        as has_roof
        from v_building_floor_stack s
       where s.bld_id = rep.bld_id
    ) fs on true
    join lateral (







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
