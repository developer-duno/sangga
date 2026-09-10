explain (analyze, buffers)
with pat as (
    select case when search_key('빌딩') is null then null
                else '%' || replace(replace(replace(search_key('빌딩'), '\', '\\'),
                                    '%', '\%'), '_', '\_') || '%'
           end as p,
           nullif(btrim(coalesce('11680', '')), '') as gu
  ),
  c as (
    select
      (select count(*) from mv_search_parcel pc cross join pat
        where '%빌딩%' is not null








          and ('11680' is null or pc.sigungu_code = '11680'::char(5))
          and (pc.road_addr_key  like '%빌딩%' escape '\'
            or pc.jibun_addr_key like '%빌딩%' escape '\')) as addr_cnt,
      (select count(*) from building b
         join mv_search_parcel pc on pc.pnu = b.pnu
         cross join pat
        where '%빌딩%' is not null
          and ('11680' is null or pc.sigungu_code = '11680'::char(5))
          and b.pnu >= '11680'::char(19) and b.pnu <= ('11680' || repeat('9',14))::char(19)
          and b.nm_key like '%빌딩%' escape '\')            as nm_cnt
  )
  select greatest(c.addr_cnt, c.nm_cnt) > search_scope_limit(),
         least(greatest(c.addr_cnt, c.nm_cnt), 2147483647)::int
  from c;
