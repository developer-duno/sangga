-- 2026-08-11c — 검색이 **띄어쓰기를 무시**하게 한다.
--
-- 왜: 사장님이 라이브에서 바로 잡아낸 결함이다.
--       '그랑프리빌딩'  → 1건 (찾힘)
--       '그랑프리 빌딩' → 0건 (못 찾음)   ← 같은 건물인데
--     건물명이 '그랑프리빌딩'(붙여쓰기)인데 검색은 친 글자 그대로를 찾으니
--     공백 하나에 결과가 사라진다. 실무에서 띄어쓰기는 사람마다 다르므로
--     이건 "가끔 불편"이 아니라 **못 찾는 결함**이다.
--
-- 어떻게: 비교할 때 양쪽 모두 **공백을 없애고 소문자로** 바꾼 값을 쓴다.
--       '그랑프리 빌딩' → '그랑프리빌딩'  vs  '그랑프리빌딩' → 일치 ✅
--       '테헤란로 117'  → '테헤란로117'   vs  '…강남구테헤란로117' → 일치 ✅
--       '역삼동 823-4'  → '역삼동823-4'   vs  '…강남구역삼동823-4' → 일치 ✅
--     ⚠️ 단어 순서를 바꾼 검색('빌딩 그랑프리')은 여전히 안 된다. 흔한 문제는
--        띄어쓰기이지 어순이 아니라서, 가지를 늘리지 않고 이 방법을 택했다
--        (가지를 늘리면 '빌딩' 같은 흔한 단어 검색이 더 느려진다 — 알려진한계 참조).
--
-- ⚠️ 인덱스 식과 WHERE 식이 **글자 하나까지 같아야** 인덱스를 탄다.
--    그래서 비교 전처리를 함수 하나(search_key)로 묶어 양쪽이 갈라질 수 없게 했다.
--
-- 실행법: Supabase 대시보드 → SQL Editor 에 이 파일 전체를 붙여넣고 Run.
--   ⚠️ 2026-08-11_search_by_jibun.sql · 2026-08-11b 를 **먼저** 적용한 뒤에.
--   ⏱️ 인덱스 3개를 새로 만든다(parcel 19.7만 · building 1.4만) — 수십 초 걸린다.
--
-- 검산 (실행 후):
--   select count(*) from search_buildings('그랑프리 빌딩');  -- 1 이상
--   select count(*) from search_buildings('그랑프리빌딩');   -- 위와 같아야 한다

-- ── 1. 비교용 정규화 키 ──────────────────────────────────────────────────────
create or replace function search_key(t text)
returns text
language sql
immutable
parallel safe
as $$
  select nullif(lower(regexp_replace(coalesce(t, ''), '\s+', '', 'g')), '')
$$;

comment on function search_key(text) is
  '검색 비교용 정규화: 공백 제거 + 소문자. '
  '띄어쓰기가 달라도 같은 것으로 보게 한다("그랑프리 빌딩" = "그랑프리빌딩"). '
  '⛔ 인덱스 식과 search_buildings 의 WHERE 식이 **글자 하나까지 같아야** 인덱스를 탄다.';

-- ── 2. 정규화 키 위의 인덱스 ─────────────────────────────────────────────────
--
-- 소문자로 이미 내려놨으므로 ILIKE 가 아니라 LIKE 로 찾는다(같은 결과, 더 싸다).
create index if not exists idx_building_display_nm_key
  on building using gin ((search_key(building_display_nm(bld_nm, dong_nm))) gin_trgm_ops);

create index if not exists idx_parcel_road_addr_key
  on parcel using gin ((search_key(road_addr)) gin_trgm_ops);

create index if not exists idx_parcel_jibun_addr_key
  on parcel using gin (
    (search_key(parcel_jibun_addr(sido_nm, sigungu_nm, emd_nm, jibun))) gin_trgm_ops
  );

-- ── 3. search_buildings — 정규화 키로 비교 ───────────────────────────────────
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
    -- 검색어도 같은 규칙으로 정규화한 뒤 LIKE 특수문자만 리터럴로 바꾼다.
    -- 순서 주의: 정규화(공백제거·소문자) → 이스케이프. 역슬래시를 **먼저** 바꾼다.
    -- 빈 검색어는 NULL 로 만들어 0건이 되게 한다(안 그러면 '%%' = 전 건물 덤프).
    select
      case when esc.v is null then null else '%' || esc.v || '%' end as p,
      case when esc.v is null then null else '%' || esc.v      end as p_end
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
    -- ⛔ 각 가지의 식은 대응하는 인덱스 식과 **글자 하나까지 같아야** 한다.
    select b.bld_id, b.pnu,
           building_display_nm(b.bld_nm, b.dong_nm) as bld_nm,
           pc.road_addr,
           parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun) as jibun_addr
      from building b
      join parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null
       and search_key(building_display_nm(b.bld_nm, b.dong_nm)) like pat.p escape '\'
    union
    select b.bld_id, b.pnu,
           building_display_nm(b.bld_nm, b.dong_nm),
           pc.road_addr,
           parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun)
      from building b
      join parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null
       and search_key(pc.road_addr) like pat.p escape '\'
    union
    select b.bld_id, b.pnu,
           building_display_nm(b.bld_nm, b.dong_nm),
           pc.road_addr,
           parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun)
      from building b
      join parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null
       and search_key(parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun))
           like pat.p escape '\'
  ),
  -- 그릴 층이 하나도 없는 건물은 목록에 올리지 않는다(눌러도 빈 화면).
  -- ★ 지번이 검색어로 끝나는가 = 정렬 1순위 (823-4 로 찾을 때 823-48 이 먼저 오면 안 된다).
  eligible as (
    select h.*,
           count(*) over () as total_cnt,
           coalesce(search_key(h.jibun_addr) like (select p_end from pat) escape '\',
                    false) as jibun_hit
    from hit h
    where exists (
      select 1 from building_floor f
      where f.bld_id = h.bld_id and f.floor_no is not null
    )
  ),
  top as (
    select e.*
    from eligible e
    order by
      e.jibun_hit                          desc,
      (search_key(e.bld_nm) = search_key(q)) desc nulls last,  -- 이름 완전일치(띄어쓰기 무시)
      (search_key(e.bld_nm) like search_key(q) || '%') desc nulls last,
      (e.bld_nm is null)                   asc,
      length(e.bld_nm)                     asc nulls last,
      e.road_addr                          asc nulls last,
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
    t.jibun_hit                          desc,
    (search_key(t.bld_nm) = search_key(q)) desc nulls last,
    (search_key(t.bld_nm) like search_key(q) || '%') desc nulls last,
    (t.bld_nm is null)                   asc,
    length(t.bld_nm)                     asc nulls last,
    t.road_addr                          asc nulls last,
    t.bld_id;
$$;

comment on function search_buildings(text, int) is
  '§8.1 건물 검색. 건물 1개 = 1행이며 total_cnt로 정확한 전체 건수를 함께 준다. '
  '건물명 · 도로명주소 · 지번(구주소) 세 가지로 찾고, **띄어쓰기를 무시**한다(2026-08-11c). '
  '지번이 검색어로 끝나는 건물을 맨 위로 올린다(823-4 로 찾을 때 823-48 이 먼저 오면 안 된다). '
  'security definer — 원본 표가 anon에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '입력의 % _ \ 는 리터럴로 이스케이프하고, 빈 검색어는 0건으로 잘라낸다.';

grant execute on function search_buildings(text, int) to anon, authenticated;

-- 도우미 함수는 화면이 직접 부르지 않는다 — 원본 표를 열지 않기 위해 닫아 둔다.
revoke all on function search_key(text) from public, anon, authenticated;

-- ── 4. 쓸모없어진 옛 인덱스 정리 ─────────────────────────────────────────────
--
-- 위에서 WHERE 식이 전부 search_key(...) 로 바뀌었으므로 아래 셋은 이제 아무 쿼리도
-- 타지 않는다. 인덱스는 이 DB 용량의 절반을 차지하므로 죽은 것은 지운다.
-- (idx_building_nm · idx_ub_name 은 다른 용도라 **건드리지 않는다**.)
drop index if exists idx_building_display_nm;
drop index if exists idx_parcel_road_addr;
drop index if exists idx_parcel_jibun_addr;
