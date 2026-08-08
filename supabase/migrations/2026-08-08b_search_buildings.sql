-- =====================================================================
-- 마이그레이션 2026-08-08 (b) — 건물 검색 함수 search_buildings
-- =====================================================================
-- 어떻게 쓰나: Supabase 대시보드 → SQL Editor → New query → 이 파일 전체
--             붙여넣기 → Run. 몇 번을 실행해도 안전하다(create or replace).
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 필요한가 — 지금 검색은 강남 안에서도 "역삼동"만 보여준다 (2026-08-08 실측)
-- ─────────────────────────────────────────────────────────────────────
-- 화면은 뷰 v_floor_stack(= 건물 × 층)에서 600줄을 받아 건물로 접는 방식이었다.
-- 여기엔 두 가지가 겹쳐 있었다:
--   (1) 정렬이 없으면 같은 검색이 매번 다른 결과를 낸다(PostgreSQL은 ORDER BY 없는
--       LIMIT의 행 순서를 보장하지 않는다).
--   (2) 그래서 .order('bld_id')를 넣었더니 — bld_id = PNU(19자리) + '_' + 대장PK 라
--       **앞자리가 법정동 코드**다. 오름차순 = 법정동 번호가 작은 동네부터.
--       넓은 검색어는 그 첫 동네에서 600줄을 다 써버린다.
--
-- 실측(2026-08-08):
--   '빌딩'    → 매칭 15,068행인데 화면에 걸리는 건물 69개, 전부 법정동 1168010100
--   '테헤란로' → 매칭 10,517행인데 건물 95개, 역시 1168010100 하나뿐
--   → 나머지 동네 건물은 **몇 번을 다시 검색해도 나오지 않는다.**
--
-- 근본 원인은 "층 줄을 표본으로 받아 건물을 추린다"는 구조 자체다. 층이 27개인
-- 건물 하나가 27줄을 먹으므로, 표본은 건물을 대표하지 못한다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 처방 — 서버에서 건물 단위로 뽑는다
-- ─────────────────────────────────────────────────────────────────────
-- 이 함수는 처음부터 **건물 1개 = 1행**을 돌려준다. 그래서
--   · 25개를 달라고 하면 진짜 건물 25개가 온다(예전엔 69개 중 25개였다)
--   · total_cnt로 **정확한 전체 건수**를 함께 준다(예전엔 "N개 이상"밖에 못 말했다)
--   · 정렬이 지역이 아니라 **이름 관련도**라 동네 잠김이 사라진다
--   · 검색어의 % _ 를 서버가 파라미터로 이스케이프한다(프론트 이스케이프 불필요)
--   · 층 수·최저/최고층·옥탑 여부까지 한 번에 줘서 2차 조회가 없어진다
--
-- ⚠️ security definer 인 이유: 원본 표(building·parcel·building_floor)는 anon에게
--    닫혀 있다(2026-08-08 공개 접근 정책). 이 함수가 소유자 권한으로 대신 읽는다.
--    search_path를 public으로 고정해 검색 경로 가로채기를 막는다. 입력은 파라미터로만
--    받고 문자열을 이어 붙여 SQL을 만들지 않는다.
-- =====================================================================

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
    -- LIKE 특수문자를 리터럴로 만든다. 역슬래시를 **먼저** 바꿔야 한다
    -- (나중에 바꾸면 방금 넣은 이스케이프까지 다시 이스케이프된다).
    select '%' ||
           replace(replace(replace(coalesce(q, ''), '\', '\\'), '%', '\%'), '_', '\_') ||
           '%' as p
  ),
  hit as (
    select b.bld_id, b.pnu, b.bld_nm, pc.road_addr
    from building b
    join parcel pc on pc.pnu = b.pnu
    cross join pat
    where b.bld_nm     ilike pat.p escape '\'
       or pc.road_addr ilike pat.p escape '\'
  ),
  -- 스택뷰가 그릴 층이 하나도 없는 건물은 목록에 올리지 않는다(눌러도 빈 화면).
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
    t.bld_id,
    t.pnu,
    t.bld_nm,
    t.road_addr,
    (select count(*)::int from building b2 where b2.pnu = t.pnu) as bld_cnt_in_pnu,
    fs.floor_cnt,
    fs.min_floor,
    fs.max_floor,
    fs.has_roof,
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
  '§8.6 건물 검색. 건물 1개 = 1행이며 total_cnt로 정확한 전체 건수를 함께 준다. '
  'security definer — 원본 표가 anon에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '입력의 % _ \ 는 서버가 리터럴로 이스케이프하므로 프론트에서 따로 처리하지 않는다';

-- 공개 롤에게 명시적으로만 실행 권한을 준다.
-- (Postgres는 새 함수의 EXECUTE를 PUBLIC에게 기본 부여한다 — 먼저 회수하고 정확히 준다.)
revoke all on function search_buildings(text, int) from public;
grant execute on function search_buildings(text, int) to anon, authenticated;

-- =====================================================================
-- 확인 (붙여넣고 Run 한 뒤 이 쿼리로 검산)
-- =====================================================================
-- 기대: 법정동이 2곳 이상 섞여 나온다(예전엔 1곳뿐이었다)
--
--   select count(distinct left(pnu, 10)) as 법정동수, max(total_cnt) as 전체건수
--   from search_buildings('빌딩', 25);
--
-- 기대: 정확히 1건, total_cnt = 1
--
--   select bld_nm, total_cnt from search_buildings('KB손해보험빌딩', 25);
--
-- 기대: 0건 (%가 만능문자가 아니라 글자 그대로 취급되므로)
--
--   select count(*) from search_buildings('%', 25);
-- =====================================================================
