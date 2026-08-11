-- 2026-08-11e — 검색 키를 **컬럼에 저장**해 재확인(recheck) 비용을 없앤다.
--
-- 왜: 흔한 검색어가 3초 제한(statement_timeout)에 걸려 500을 냈다.
--     `명동`·`상가`·`빌딩`·`서울`·`동`·`1` 전부 실패. EXPLAIN(2026-08-11)이 원인을 짚었다:
--
--       Bitmap Index Scan on idx_parcel_road_addr_key  → 후보 197,076건 (parcel 전체)
--       Bitmap Heap Scan   Rows Removed by Index Recheck: 196,680 → 최종 396건
--
--     두 가지가 겹쳤다.
--       ① `명동`은 2글자다. pg_trgm 은 3글자 단위라 2글자 검색어엔 선별력이 거의 없어
--          거의 전체를 후보로 내놓는다. 이건 trigram 의 성질이라 못 없앤다.
--       ② ⭐ **인덱스가 '식'으로 걸려 있어 재확인 때마다 regexp_replace 를 다시 돌린다.**
--          후보 197,076건 × (regexp_replace + lower + coalesce) = 진짜 시간 도둑.
--
--     ②는 없앨 수 있다 — 계산 결과를 **컬럼에 저장**하면 재확인이 정규식 계산이 아니라
--     단순 문자열 비교가 된다. **결과를 자르지 않고** 빨라진다.
--
-- ⚠️ generated ... stored 는 IMMUTABLE 함수만 쓸 수 있다.
--    building_display_nm · parcel_jibun_addr · search_key 셋 다 IMMUTABLE 확인함(provolatile='i').
-- ⚠️ 저장 컬럼 추가는 테이블을 다시 쓴다(building 24만 · parcel 19.7만) — 수십 초.

-- ── 1. 저장 컬럼 ─────────────────────────────────────────────────────────────
alter table building
  add column if not exists nm_key text
  generated always as (search_key(building_display_nm(bld_nm, dong_nm))) stored;

comment on column building.nm_key is
  '검색용 정규화 이름(공백 제거+소문자). search_buildings 와 idx_building_nm_key 가 이 컬럼을 쓴다. '
  '식 인덱스였을 때는 후보 8만 건마다 regexp 를 다시 돌려 검색이 3초를 넘겼다(2026-08-11e).';

alter table parcel
  add column if not exists road_addr_key text
  generated always as (search_key(road_addr)) stored;

alter table parcel
  add column if not exists jibun_addr_key text
  generated always as (search_key(parcel_jibun_addr(sido_nm, sigungu_nm, emd_nm, jibun))) stored;

comment on column parcel.jibun_addr_key is
  '검색용 정규화 지번주소(공백 제거+소문자). 예: 서울특별시강남구역삼동823-4';

-- ── 2. 저장 컬럼 위의 인덱스 ─────────────────────────────────────────────────
create index if not exists idx_building_nm_key on building using gin (nm_key gin_trgm_ops);
create index if not exists idx_parcel_road_key on parcel using gin (road_addr_key gin_trgm_ops);
create index if not exists idx_parcel_jibun_key on parcel using gin (jibun_addr_key gin_trgm_ops);

-- ── 3. search_buildings — 저장 컬럼을 쓴다 ───────────────────────────────────
create or replace function search_buildings(q text, lim int default 25)
returns table (
  bld_id         text,
  pnu            char(19),
  bld_nm         text,
  road_addr      text,
  jibun_addr     text,
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
      esc.v as k
    from (
      select case when search_key(q) is null then null
                  else replace(replace(replace(search_key(q), '\', '\\'),
                               '%', '\%'), '_', '\_')
             end as v
    ) esc
  ),
  hit as (
    -- ⛔ OR 하나로 합치지 말 것 — 서로 다른 두 표에 걸친 OR 은 조인 전에 한 표를
    --    못 걸러 gin_trgm 인덱스가 통째로 무력화된다(2026-08-08 EXPLAIN 실측).
    -- ⛔ WHERE 는 **저장 컬럼**(nm_key/road_addr_key/jibun_addr_key)을 써야 한다.
    --    식으로 되돌리면 재확인 때 regexp 가 다시 돌아 3초를 넘긴다(2026-08-11e).
    select b.bld_id, b.pnu, b.nm_key,
           building_display_nm(b.bld_nm, b.dong_nm) as bld_nm,
           pc.road_addr, pc.jibun_addr_key,
           parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun) as jibun_addr
      from building b
      join parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null and b.nm_key like pat.p escape '\'
    union
    select b.bld_id, b.pnu, b.nm_key,
           building_display_nm(b.bld_nm, b.dong_nm),
           pc.road_addr, pc.jibun_addr_key,
           parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun)
      from building b
      join parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null and pc.road_addr_key like pat.p escape '\'
    union
    select b.bld_id, b.pnu, b.nm_key,
           building_display_nm(b.bld_nm, b.dong_nm),
           pc.road_addr, pc.jibun_addr_key,
           parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun)
      from building b
      join parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null and pc.jibun_addr_key like pat.p escape '\'
  ),
  eligible as (
    select h.*,
           count(*) over () as total_cnt,
           coalesce(h.jibun_addr_key like (select p_end from pat) escape '\', false)
             as jibun_hit
    from hit h
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
      (e.nm_key = pat.k)             desc nulls last,   -- 저장 컬럼 비교 (regexp 없음)
      (e.nm_key like pat.k || '%')   desc nulls last,
      (e.bld_nm is null)             asc,
      length(e.bld_nm)               asc nulls last,
      e.road_addr                    asc nulls last,
      e.bld_id
    limit greatest(1, least(coalesce(lim, 25), 100))
  )
  select
    t.bld_id, t.pnu, t.bld_nm, t.road_addr, t.jibun_addr,
    (select count(*)::int from building b2 where b2.pnu = t.pnu) as bld_cnt_in_pnu,
    fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof,
    t.total_cnt
  from top t
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

grant execute on function search_buildings(text, int) to anon, authenticated;

-- ── 4. 식 인덱스는 이제 죽었다 — 지운다 ──────────────────────────────────────
drop index if exists idx_building_display_nm_key;
drop index if exists idx_parcel_road_addr_key;
drop index if exists idx_parcel_jibun_addr_key;

-- ── 5. 새 컬럼·인덱스 통계를 즉시 잡아준다 (안 하면 플래너가 헤맨다) ─────────
analyze building;
analyze parcel;
