-- =====================================================================
-- 건물이 속한 상권을 화면에 알려 준다 (2026-08-14)
-- =====================================================================
-- district 표는 2026-08-14 에 서울 1,650개로 찼는데(결정 0008) **읽는 코드가 0줄**이었다.
-- 층별 스택 화면(§8.6)에 "속한 상권" 한 줄을 붙이기 위한 유일한 입구가 이 함수다.
--
-- ## 왜 `covered` 를 표에서 직접 세나
--
-- 화면에 "서울만 상권 자료가 있다"고 적어 두면, 대전·부산 상권을 넣는 날 표만 늘고
-- **화면 문구는 낡은 채 남는다**(코드를 한 줄도 안 고쳤는데 거짓말이 시작되는 결함).
-- 결정 0006/0009 의 `list_open_sigungu()` 와 같은 결로, "그 건물의 시·도에 상권 자료가
-- 실제로 있는가"를 district 표에 직접 물어본다 — 자료가 늘면 화면이 저절로 따라온다.
--
-- ⚠️ 그래서 `covered=false`("아직 자료가 없는 지역")와 `districts=[]`("자료는 있는데
--    어느 경계에도 안 들어감")는 **다른 상태**다. 화면이 둘을 다르게 말해야 한다.
--
-- ## 왜 겹치면 전부 나열하나
--
-- 한 건물이 상권 여러 개에 걸치는 일이 실제로 있다(결정 0008 검증 때 3,342동). 하나만
-- 골라 보여주면 그 고르는 규칙이 곧 숨은 판단이 된다 — 사장님 결정은 **전부 나열**이다.
-- 정렬은 면적 오름차순(좁은 상권이 더 구체적인 설명이라 먼저) + district_id 로 안정화
-- (면적이 같을 때 순서가 호출마다 흔들리면 안 된다).
--
-- ## 왜 st_contains 인가
--
-- 결정 0008 의 실측(68.5% / 31.5%)이 바로 이 술어로 나온 숫자다. 여기서 술어를 바꾸면
-- (st_intersects·st_dwithin 등) 화면이 그 실측과 어긋난 말을 하게 된다.
--
-- ## 왜 본문에서 함수명으로 한정하나
--
-- 파라미터 이름 `bld_id` 가 `building.bld_id` 컬럼과 겹친다. 그냥 `bld_id` 라고 쓰면
-- PostgreSQL 이 컬럼을 우선 집어 `where b.bld_id = b.bld_id`(항상 참 = 전 건물)가 된다.
-- `list_building_districts.bld_id` 로 한정해야 파라미터를 가리킨다.
create or replace function list_building_districts(bld_id text)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  with me as (
    select p.geom, left(b.pnu, 2) as sido
    from building b
    join parcel p on p.pnu = b.pnu
    -- 좌표가 없으면 아예 답하지 않는다(covered=false = "모른다"). 여기를 열어 두면
    -- st_contains 가 NULL→거짓으로 흘러 "어느 경계에도 안 든다"는 **단정**이 되어 버린다.
    where b.bld_id = list_building_districts.bld_id
      and p.geom is not null
  )
  select jsonb_build_object(
    'covered', exists (select 1 from district d cross join me
                       where left(d.sigungu_code, 2) = me.sido),
    'districts', coalesce((
      select jsonb_agg(jsonb_build_object('name', d.district_nm, 'type', d.district_type)
                       order by d.area_m2 asc, d.district_id)
      from district d cross join me
      where st_contains(d.geom, me.geom)
    ), '[]'::jsonb)
  );
$$;

comment on function list_building_districts(text) is
  '§8.6 이 건물이 속한 상권 목록. 겹치면 전부 준다(좁은 상권 먼저). '
  'covered=false 는 "그 시·도에 상권 경계 자료가 아직 없다"는 뜻이라 빈 목록(경계 밖)과 다르다 — '
  '지역명을 화면에 박지 않으려고 표에서 직접 센다(자료가 늘면 화면이 저절로 따라온다). '
  'security definer (district·building·parcel 이 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 상권 이름·종류뿐)';

-- 화면이 부르는 함수이므로 명시적으로 연다(2026-08-13g 이후 함수는 기본으로 닫혀 있다).
grant execute on function list_building_districts(text) to anon, authenticated;
