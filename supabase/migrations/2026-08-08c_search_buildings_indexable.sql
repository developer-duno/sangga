-- =====================================================================
-- 마이그레이션 2026-08-08 (c) — 검색 함수 인덱스 활용 + 빈 검색어 차단
-- =====================================================================
-- 어떻게 쓰나: Supabase 대시보드 → SQL Editor → New query → 이 파일 전체
--             붙여넣기 → Run. 몇 번을 실행해도 안전하다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 (2026-08-08 3차 적대검증, EXPLAIN ANALYZE로 확정)
-- ─────────────────────────────────────────────────────────────────────
-- 2026-08-08b가 만든 search_buildings에 세 가지 문제가 확인됐다.
--
-- (1) **OR 가 인덱스를 무력화한다.** 필터가
--       `b.bld_nm ilike X OR pc.road_addr ilike X`
--     로 **서로 다른 두 조인 테이블에 걸친 OR** 이라, 어느 한쪽 조건만으로는 최종
--     매칭 여부를 못 정한다 → Postgres가 조인 전에 한 표만 걸러낼 수 없어
--     `idx_building_nm`(gin trgm)을 못 쓴다. 합성 55만 행 EXPLAIN 실측에서
--     단독 쿼리는 Bitmap Index Scan(30ms)인데 함수 안에서는 순차 스캔이 됐다.
--     ⇒ **UNION 두 가지로 쪼갠다.** 각 가지는 표 하나만 거르므로 인덱스를 탄다.
--
-- (2) **parcel.road_addr 에 텍스트 인덱스가 아예 없다.** building.bld_nm 에는
--     gin_trgm 이 있는데 road_addr 에는 없어 비대칭이었다(실측: 같은 선택도에서
--     비용 8배·시간 28배). 주소 검색은 문서화된 주요 경로다(검색창 예시가
--     '테헤란로 117').  ⇒ gin_trgm 인덱스를 추가한다.
--
-- (3) **빈 검색어가 전체 목록 덤프가 된다.** q 가 NULL·빈 문자열·공백뿐이면
--     패턴이 '%%' 가 되어 필터 없이 전 건물이 나온다(라이브 실측 total_cnt=12,405).
--     화면은 빈 검색어를 막지만 RPC 직접 호출은 안 막힌다.
--     ⇒ 서버에서 빈 검색어를 0건으로 잘라낸다.
--
-- ⚠️ 현재 규모(강남 12,405건물)에서는 152~277ms 로 사용자 체감 문제가 아니다.
--    이건 **전국 확장 전에 미리 막는 조치**다. 다만 (3)은 지금도 실효가 있다.
--
-- ※ 남는 성질: `count(*) over ()` 는 정확한 전체 건수를 주기 위해 매칭 전부를
--   세므로 lim 을 줄여도 비용이 줄지 않는다(실측 lim=1 254ms vs lim=100 277ms).
--   이건 "정확한 건수"의 대가로 의도적으로 남긴다 — 예전의 "N개 이상"이라는
--   부정직한 표기로 되돌아가지 않기 위해서다. 인덱스를 타게 되면 그 비용 자체가
--   크게 줄어든다.
-- =====================================================================

-- 1) 주소 검색용 트라이그램 인덱스 (building.bld_nm 과 대칭 맞추기)
create index if not exists idx_parcel_road_addr
  on parcel using gin (road_addr gin_trgm_ops);

-- 2) 검색 함수 재정의
create or replace function search_buildings(q text, lim int default 25)
returns table (
  bld_id         text,
  pnu            char(19),
  bld_nm         text,
  road_addr      text,
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
    -- LIKE 특수문자는 리터럴로. 역슬래시를 **먼저** 바꿔야 한다.
    select case
             when coalesce(btrim(q), '') = '' then null
             else '%' ||
                  replace(replace(replace(q, '\', '\\'), '%', '\%'), '_', '\_') ||
                  '%'
           end as p
  ),
  hit as (
    -- ⛔ OR 로 합치지 말 것 — 두 조인 테이블에 걸친 OR 은 인덱스를 못 쓰게 만든다.
    --    UNION 은 각 가지가 표 하나만 거르므로 gin_trgm 인덱스를 탄다(중복은 UNION 이 제거).
    select b.bld_id, b.pnu, b.bld_nm, pc.road_addr
      from building b
      join parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null
       and b.bld_nm ilike pat.p escape '\'
    union
    select b.bld_id, b.pnu, b.bld_nm, pc.road_addr
      from building b
      join parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null
       and pc.road_addr ilike pat.p escape '\'
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
      (lower(e.bld_nm) = lower(q))      desc nulls last,  -- 이름이 검색어와 정확히 같음
      (e.bld_nm ilike q || '%')         desc nulls last,  -- 이름이 검색어로 시작
      (e.bld_nm is null)                asc,              -- 이름 있는 건물 먼저
      length(e.bld_nm)                  asc nulls last,   -- 짧고 핵심적인 이름 먼저
      e.road_addr                       asc nulls last,   -- 그다음 주소순(동네가 고루 섞인다)
      e.bld_id
    limit greatest(1, least(coalesce(lim, 25), 100))
  )
  select
    t.bld_id, t.pnu, t.bld_nm, t.road_addr,
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
  'security definer — 원본 표가 anon에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '입력의 % _ \ 는 서버가 리터럴로 이스케이프하고, 빈 검색어는 0건으로 잘라낸다. '
  '⛔ WHERE를 OR로 되돌리지 말 것 — 두 조인 테이블에 걸친 OR은 gin_trgm 인덱스를 무력화한다';

-- 권한은 2026-08-08b 에서 이미 잡혔지만 멱등하게 다시 못 박는다.
revoke all on function search_buildings(text, int) from public;
grant execute on function search_buildings(text, int) to anon, authenticated;

-- =====================================================================
-- 확인 (붙여넣고 Run 한 뒤 이 쿼리로 검산)
-- =====================================================================
-- 기대: 0건 (빈 검색어가 전체 덤프가 되지 않는다)
--   select count(*) from search_buildings('', 25);
--   select count(*) from search_buildings(null, 25);
--   select count(*) from search_buildings('   ', 25);
--
-- 기대: 예전과 같은 결과 (법정동 2곳 이상, total_cnt 1742)
--   select count(distinct left(pnu,10)) as 법정동수, max(total_cnt) from search_buildings('빌딩', 25);
--
-- 기대: 1건
--   select bld_nm, total_cnt from search_buildings('KB손해보험빌딩', 25);
--
-- 기대: 인덱스를 타는지 (Bitmap Index Scan 또는 Bitmap Heap Scan 이 보여야 한다)
--   explain analyze select * from search_buildings('빌딩', 25);
-- =====================================================================
