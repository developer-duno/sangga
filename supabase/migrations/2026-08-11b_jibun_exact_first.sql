-- 2026-08-11b — 지번으로 찾으면 **정확히 일치하는 지번을 맨 위로**.
--
-- 왜: 2026-08-11 지번 검색을 켠 직후 라이브에서 바로 드러난 문제다.
--     '역삼동 823-4' 로 찾으면 6건이 나오는데 정작 823-4 가 **맨 아래(6번째)**였다.
--       1 규진빌딩      역삼동 823-48
--       2 그랑프리빌딩   역삼동 823-42
--       ...
--       6 (이름없음)     역삼동 823-4     ← 찾던 것
--     부분 일치라 823-4* 가 전부 걸리는데, 정렬이 **건물명 기준**뿐이라
--     이름 없는 건물이 뒤로 밀린 탓이다(`(bld_nm is null) asc`).
--     지번으로 검색한 사람에게 이름 순서는 아무 의미가 없다.
--
-- 어떻게: '…로 끝나는가' 패턴을 하나 더 만들어 정렬 1순위로 올린다.
--     '역삼동 823-4' 로 끝나는 것은 823-4 뿐이고, 823-48 은 '823-48' 로 끝나므로 안 걸린다.
--     검색이 **걸리는 범위는 그대로**이고 **순서만** 바뀐다(놓치는 건물이 생기지 않는다).
--
-- 실행법: Supabase 대시보드 → SQL Editor 에 이 파일 전체를 붙여넣고 Run.
--   ⚠️ 2026-08-11_search_by_jibun.sql 을 **먼저** 적용한 뒤에 이걸 적용할 것.
--
-- 검산 (실행 후):
--   select jibun_addr from search_buildings('역삼동 823-4', 5);
--     -> 첫 줄이 '…역삼동 823-4' 여야 한다 (823-48 이 아니라)

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
    -- p     : 부분 일치용 '%…%'  (검색 대상 범위를 정한다)
    -- p_end : 끝 일치용   '%…'   (정렬에만 쓴다 — 범위를 좁히지 않는다)
    -- 빈 검색어는 NULL 로 만들어 0건이 되게 한다(안 그러면 '%%' = 전 건물 덤프).
    -- LIKE 특수문자는 리터럴로. 역슬래시를 **먼저** 바꿔야 한다.
    select
      case when coalesce(btrim(q), '') = '' then null
           else '%' || esc.v || '%' end as p,
      case when coalesce(btrim(q), '') = '' then null
           else '%' || esc.v end        as p_end
    from (
      select replace(replace(replace(btrim(q), '\', '\\'), '%', '\%'), '_', '\_') as v
    ) esc
  ),
  hit as (
    -- ⛔ OR 하나로 합치지 말 것 — 서로 다른 두 표에 걸친 OR 은 조인 전에 한 표를
    --    못 걸러 gin_trgm 인덱스가 통째로 무력화된다(2026-08-08 EXPLAIN 실측).
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
  -- ★ 지번이 검색어로 **끝나는가**를 여기서 한 번만 계산해 정렬에 쓴다.
  eligible as (
    select h.*,
           count(*) over () as total_cnt,
           coalesce(h.jibun_addr ilike (select p_end from pat) escape '\', false)
             as jibun_hit
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
      e.jibun_hit                       desc,   -- ★ 지번 정확 일치가 1순위
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
    t.jibun_hit                       desc,
    (lower(t.bld_nm) = lower(q))      desc nulls last,
    (t.bld_nm ilike q || '%')         desc nulls last,
    (t.bld_nm is null)                asc,
    length(t.bld_nm)                  asc nulls last,
    t.road_addr                       asc nulls last,
    t.bld_id;
$$;

comment on function search_buildings(text, int) is
  '§8.1 건물 검색. 건물 1개 = 1행이며 total_cnt로 정확한 전체 건수를 함께 준다. '
  '건물명 · 도로명주소 · 지번(구주소) 세 가지로 찾는다(지번 2026-08-11 추가). '
  '지번이 검색어로 끝나는 건물을 맨 위로 올린다 — 823-4 로 찾을 때 823-48 이 먼저 '
  '나오면 안 된다(2026-08-11b). security definer — 원본 표가 anon에게 닫혀 있어 '
  '소유자 권한으로 대신 읽는다. 입력의 % _ \ 는 리터럴로 이스케이프한다.';

-- CREATE OR REPLACE 는 권한을 유지하지만, 확실히 하기 위해 다시 준다.
grant execute on function search_buildings(text, int) to anon, authenticated;
