-- =====================================================================
-- 임대 사실 카드 — 상권 임대 동향(부동산원 조사) 읽는 함수 (2026-08-31a)
-- =====================================================================
-- 결정 0024. 층별 화면의 **여섯 번째 카드**가 이 함수 하나만 부른다.
--
-- 무엇이 달라지나
-- ---------------
-- 표는 하나도 안 만든다. 이미 있는 것(`rent_stat` 7,232행 · `district_rone_map` 396행)을
-- **처음으로 읽는 길**을 뚫는 마이그레이션이다 — 2026-08-09 에 들어온 임대 자료를 지금까지
-- 화면이 한 줄도 안 읽고 있었다.
--
-- ⛔ 역산하지 않는다
-- ------------------
-- 절대 규칙 5 는 임대료를 부동산원 수익률·층별효용비율로 **역산**하라고 한다. 그 역산은
-- 백테스트와 재결재를 거친 뒤의 일이고(매매가 결정 0013 으로 그렇게 했다), 이 함수는
-- 조사값을 **그대로** 나른다 — 곱하지도 나누지도 층으로 펴지도 않는다. 그래서 나가는 값에
-- `floor_util_ratio` 가 아예 없다. 있으면 화면이 언젠가 그것을 곱하게 된다.
--
-- 왜 상권을 두 번 건너가나
-- -------------------------
-- rent_stat 의 지역 축은 시군구가 아니라 **상권**이다(같은 강남 안에서도 상권마다 값이
-- 다르다 — 상세계획 §6.1 의 지하1층 계수 1.8배 차이가 그 증거다). 그래서
-- 필지 → 상권(공간 판정) → district_rone_map(이름 잇기) → rent_stat 으로 간다.
--
-- ⛔ 이을 근거가 없으면 **줄이 아예 없다.** 시·도 평균으로 메우지 않는다 — 부동산원 표본이
--    닿지 않는 자리가 훨씬 많은데, 거기에 상위 평균을 적으면 조사하지 않은 곳을 조사한
--    것처럼 말하게 된다. 화면은 그때 "부동산원 조사 대상 상권이 아닙니다"라고 적는다.
--
-- ⚠️ 한 상권이 R-ONE 경로를 **둘까지** 가진다(district_rone_map 의 PK 가 복합인 이유 —
--    부동산원이 bld_type 마다 서울 권역 분할을 달리한다). 그래서 상권 하나가 여러 줄을
--    낼 수 있고 그 줄들은 서로 다른 조사구역의 값이다 — 그래서 조사구역 이름을 함께 준다.
--
-- ⚠️ 단위는 **원본 그대로** 내보낸다: 공실률 %, 임대료 천원/㎡, 투자수익률 %(분기).
--    원 단위로 바꿔 적는 일은 화면이 하고, 그 사실을 화면이 밝힌다. 여기서 미리 곱해 두면
--    "서버 값 = 공표값"이라는 대조가 깨져 나중에 아무도 어느 쪽이 원본인지 모르게 된다.
--
-- 적용
-- ----
-- Supabase SQL Editor 에 통째로 붙여 실행한다(표 변경 0 · 되돌리려면 두 함수를 drop).
-- 실행 뒤 `python scripts/post_load.py --check` 로 공개 롤 권한이 그대로인지 본다.

create or replace function list_rent_stats(p_pnu text)
returns table (
  district_nm     text,
  rone_region_nm  text,
  bld_type        text,
  quarter         text,
  vacancy_rate    numeric,
  rent_per_m2     numeric,
  yield_rate      numeric
)
language sql
stable
security definer
set search_path = public
as $$
  with me as (
    -- 좌표가 없으면 아예 답하지 않는다. 여기를 열어 두면 빈손이 "이 자리는 조사 대상이
    -- 아니다"라는 **단정**으로 새어 나간다(list_building_districts 와 같은 원칙).
    select p.geom as g
    from parcel p
    where p.pnu = p_pnu::char(19) and p.geom is not null
  ),
  hit as (
    -- 술어를 st_contains 로 맞춘다 — 결정 0008·0011·0014 의 실측이 이 술어로 나온 숫자다.
    select d.district_id, d.district_nm, d.area_m2
    from district d cross join me
    where st_contains(d.geom, me.g)
  ),
  pair as (
    -- 이을 근거가 없는 상권은 여기서 저절로 빠진다(district_rone_map 에 행이 없다).
    select h.district_id, h.district_nm, h.area_m2, m.rone_region_nm
    from hit h
    join district_rone_map m on m.district_id = h.district_id
  ),
  latest as (
    -- (조사구역, 종류)마다 가장 최근 분기 한 줄. 전체 최신 분기 하나로 자르면 그 분기에
    -- 표본이 없는 종류가 통째로 사라진다("오피스는 조사 안 하는 동네"로 보인다).
    select distinct on (r.region_nm, r.bld_type)
           r.region_nm, r.bld_type, r.quarter,
           r.vacancy_rate, r.rent_per_m2, r.yield_rate
    from rent_stat r
    where r.region_nm in (select p.rone_region_nm from pair p)
    order by r.region_nm, r.bld_type, r.quarter desc
  )
  select p.district_nm,
         p.rone_region_nm,
         l.bld_type,
         l.quarter::text,
         l.vacancy_rate,
         l.rent_per_m2,
         l.yield_rate
  from pair p
  join latest l on l.region_nm = p.rone_region_nm
  -- 좁은 상권이 더 구체적인 설명이라 먼저 온다(list_building_districts 와 같은 정렬).
  order by p.area_m2 asc, p.district_id, l.bld_type, l.region_nm;
$$;

comment on function list_rent_stats(text) is
  '결정 0024 이 필지가 속한 상권의 한국부동산원 임대동향조사 값 — 상권 이름, 부동산원 '
  '조사구역 이름, 건물 종류, 분기, 공실률(%), ㎡당 임대료(천원/㎡ 공표 단위 그대로), '
  '투자수익률(%). ⛔ 역산·환산을 하지 않는다(조사값 그대로 나른다 — 층별효용비율은 안 나간다). '
  '⛔ 이을 근거가 없으면 줄이 아예 없다 — 시·도 평균으로 메우지 않는다(조사 안 한 곳을 '
  '조사한 것처럼 말하지 않기 위해서다). (조사구역, 종류)마다 가장 최근 분기 한 줄만 준다 — '
  '전체 최신 분기로 자르면 그 분기에 표본이 없는 종류가 통째로 사라진다. '
  'security definer (district·district_rone_map·rent_stat·parcel 이 anon 에게 닫혀 있어 '
  '소유자 권한으로 대신 읽는다. 나가는 것은 상권·조사구역 이름과 공표 통계값뿐이다).';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function list_rent_stats(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.list_rent_stats(p_pnu text)
returns table (
  district_nm     text,
  rone_region_nm  text,
  bld_type        text,
  quarter         text,
  vacancy_rate    numeric,
  rent_per_m2     numeric,
  yield_rate      numeric
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_rent_stats(p_pnu) $$;

revoke all on function api.list_rent_stats(text) from public, anon, authenticated;
grant execute on function api.list_rent_stats(text) to anon, authenticated;

-- ⛔ public.list_rent_stats 는 끝까지 닫아 둔다 — 통과 함수가 security definer 라
--    소유자 권한으로 부르므로 anon 에게 열 필요가 없다.

-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';
