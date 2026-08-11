-- 2026-08-11 — 검색에 **지번(구주소)** 가지를 더한다.
--
-- 왜: 실무에서 "역삼동 823-4" 처럼 지번으로 찾는 일이 많은데, 지금 검색은
--     건물명과 도로명주소만 본다. `parcel` 에 시도·시군구·법정동·지번이
--     **197,076건 전부 채워져 있어**(2026-08-11 실측) 바로 쓸 수 있다.
--
-- 실행법: Supabase 대시보드 → SQL Editor 에 이 파일 전체를 붙여넣고 Run.
--
-- 검산 (실행 후):
--   select count(*) from search_buildings('역삼동 823');   -- 0보다 커야 한다
--   explain analyze select * from search_buildings('역삼동 823-4');
--     -> parcel 가지가 Bitmap Index Scan (Seq Scan 이면 인덱스를 못 탄 것)

-- ── 1. 지번 주소 한 줄 만들기 ────────────────────────────────────────────────
--
-- ⛔ concat_ws 를 쓰지 말 것 — IMMUTABLE 이 아니라서 인덱스 식으로 못 쓴다.
--    text 끼리의 `||` 는 IMMUTABLE 이므로 coalesce 와 함께 쓴다.
create or replace function parcel_jibun_addr(
  sido text, sigungu text, emd text, jibun text
) returns text
language sql
immutable
parallel safe
as $$
  select nullif(btrim(
           coalesce(sido, '')    || ' ' ||
           coalesce(sigungu, '') || ' ' ||
           coalesce(emd, '')     || ' ' ||
           coalesce(jibun, '')
         ), '')
$$;

comment on function parcel_jibun_addr(text, text, text, text) is
  '지번(구주소) 한 줄. 예: 서울특별시 강남구 역삼동 823-4. '
  'idx_parcel_jibun_addr 와 search_buildings 가 **글자 하나까지 같은 식**을 써야 '
  '인덱스를 탄다 — 한쪽만 고치지 말 것.';

-- ── 2. 인덱스 ────────────────────────────────────────────────────────────────
--
-- 부분 일치(ILIKE '%…%')라 gin_trgm_ops 가 필요하다. 없으면 parcel 19.7만 행
-- 전수 스캔이 된다(도로명주소 인덱스를 넣을 때 같은 비교를 이미 했다:
-- 2026-08-08 실측 비용 8배·시간 28배).
create index if not exists idx_parcel_jibun_addr
  on parcel using gin (
    parcel_jibun_addr(sido_nm, sigungu_nm, emd_nm, jibun) gin_trgm_ops
  );

-- ── 3. search_buildings 에 지번 가지 추가 ────────────────────────────────────
--
-- 반환 칸이 늘어나므로(jibun_addr) CREATE OR REPLACE 로는 안 되고 DROP 이 필요하다.
drop function if exists search_buildings(text, int);

create function search_buildings(q text, lim int default 25)
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
    -- 빈 검색어(NULL·''·공백뿐)는 NULL 패턴으로 만들어 아래에서 0건이 되게 한다.
    -- 안 그러면 패턴이 '%%'가 되어 **전 건물 목록 덤프**가 된다.
    -- LIKE 특수문자는 리터럴로. 역슬래시를 **먼저** 바꿔야 한다.
    select case
             when coalesce(btrim(q), '') = '' then null
             else '%' ||
                  replace(replace(replace(q, '\', '\\'), '%', '\%'), '_', '\_') ||
                  '%'
           end as p
  ),
  hit as (
    -- ⛔ OR 하나로 합치지 말 것 — 서로 다른 두 표에 걸친 OR 은 조인 전에 한 표를
    --    못 걸러 gin_trgm 인덱스가 통째로 무력화된다(2026-08-08 EXPLAIN 실측:
    --    OR = Seq Scan 두 개 / UNION = Bitmap Index Scan 두 개).
    -- ⛔ 각 가지의 식은 대응하는 인덱스 식과 **글자 하나까지 같아야** 한다.
    select b.bld_id, b.pnu,
           building_display_nm(b.bld_nm, b.dong_nm) as bld_nm,
           pc.road_addr,
           parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun) as jibun_addr
      from building b
      join parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null
       and building_display_nm(b.bld_nm, b.dong_nm) ilike pat.p escape '\'
    union
    select b.bld_id, b.pnu,
           building_display_nm(b.bld_nm, b.dong_nm),
           pc.road_addr,
           parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun)
      from building b
      join parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null
       and pc.road_addr ilike pat.p escape '\'
    union
    -- ★ 지번(구주소) 가지 — 2026-08-11 신설.
    select b.bld_id, b.pnu,
           building_display_nm(b.bld_nm, b.dong_nm),
           pc.road_addr,
           parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun)
      from building b
      join parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null
       and parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun)
           ilike pat.p escape '\'
  ),
  -- 그릴 층이 하나도 없는 건물은 목록에 올리지 않는다(눌러도 빈 화면).
  eligible as (
    select h.*, count(*) over () as total_cnt
    from hit h
    where exists (
      select 1 from building_floor f
      where f.bld_id = h.bld_id and f.floor_no is not null
    )
  ),
  -- 무거운 층 집계는 실제로 보여줄 몇 개에만 돌린다.
  top as (
    select e.*
    from eligible e
    order by
      (lower(e.bld_nm) = lower(q))      desc nulls last,
      (e.bld_nm ilike q || '%')         desc nulls last,
      (e.bld_nm is null)                asc,
      length(e.bld_nm)                  asc nulls last,
      e.road_addr                       asc nulls last,
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
    -- 옥탑(99)은 범위에서 뺀다. 섞으면 최고층이 항상 99가 되어 지상 최고층이 사라진다.
    select
      count(*)::int                                    as floor_cnt,
      min(s.floor_no) filter (where s.floor_no <> 99)  as min_floor,
      max(s.floor_no) filter (where s.floor_no <> 99)  as max_floor,
      coalesce(bool_or(s.floor_no = 99), false)        as has_roof
    from v_building_floor_stack s
    where s.bld_id = t.bld_id
  ) fs on true
  order by
    (lower(t.bld_nm) = lower(q))      desc nulls last,
    (t.bld_nm ilike q || '%')         desc nulls last,
    (t.bld_nm is null)                asc,
    length(t.bld_nm)                  asc nulls last,
    t.road_addr                       asc nulls last,
    t.bld_id;
$$;

comment on function search_buildings(text, int) is
  '§8.1 건물 검색. 건물 1개 = 1행이며 total_cnt로 정확한 전체 건수를 함께 준다. '
  '건물명 · 도로명주소 · **지번(구주소)** 세 가지로 찾는다(지번은 2026-08-11 추가). '
  'security definer — 원본 표가 anon에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '입력의 % _ \ 는 서버가 리터럴로 이스케이프하고, 빈 검색어는 0건으로 잘라낸다.';

-- ── 4. 권한 (DROP 하면 GRANT 도 같이 사라진다 — 반드시 다시 준다) ────────────
revoke all on function search_buildings(text, int) from public, anon, authenticated;
grant execute on function search_buildings(text, int) to anon, authenticated;

-- 도우미 함수는 화면이 직접 부르지 않는다 — 원본 표를 열지 않기 위해 닫아 둔다.
revoke all on function parcel_jibun_addr(text, text, text, text)
  from public, anon, authenticated;
