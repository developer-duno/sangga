explain (analyze, buffers)
with pat as not materialized (
    select case when search_key('빌딩') is null then null
                else '%' || replace(replace(replace(search_key('빌딩'), '\', '\\'),
                                    '%', '\%'), '_', '\_') || '%'
           end as p,
           nullif(btrim(coalesce(null, '')), '') as gu
  ),
  c as (
    select
      (select count(*) from mv_search_parcel pc cross join pat
        where pat.p is not null








          and (pat.gu is null or pc.sigungu_code = pat.gu::char(5))
          and (pc.road_addr_key  like pat.p escape '\'
            or pc.jibun_addr_key like pat.p escape '\')) as addr_cnt,
      (select count(*) from building b
         join mv_search_parcel pc on pc.pnu = b.pnu
         cross join pat
        where pat.p is not null
          and (pat.gu is null or pc.sigungu_code = pat.gu::char(5))
          and (pat.gu is null or (b.pnu >= pat.gu::char(19) and b.pnu <= (pat.gu || repeat('9',14))::char(19)))
          and b.nm_key like pat.p escape '\')            as nm_cnt
  )
  select greatest(c.addr_cnt, c.nm_cnt) > search_scope_limit(),
         least(greatest(c.addr_cnt, c.nm_cnt), 2147483647)::int
  from c;
