-- =====================================================================
-- 출처가 "실제로 쓴 자료"를 가리키게 좁힌다 (2026-08-14d)
-- =====================================================================
-- ## 무엇이 잘못됐나 (지금은 무해, 소스가 둘 되는 순간 발병)
--
-- 14b 의 `sources` 는 st_contains 매칭 결과와 **무관하게** 그 시·도 전체의 distinct
-- source_nm 을 돌려줬다. 한 시·도에 소스가 하나뿐인 동안에는 답이 같아서 안 보이지만,
-- 소스가 둘 이상 들어오는 순간(= source_nm 칸을 만든 바로 그 시나리오) 이렇게 된다:
--
--   화면: "속한 상권: 역삼역(발달상권)   출처: 서울특별시 상권분석서비스 · 소상공인시장진흥공단"
--                     ↑ 서울시 자료에서 나온 상권 하나뿐인데
--                                          ↑ 쓰지도 않은 소진공이 출처로 찍힌다
--
-- 공공누리 1유형은 **쓴 자료의 출처를 밝히라는** 의무다. 안 쓴 출처를 덧붙이는 것은
-- 의무 이행이 아니라 **지어낸 출처**다 — 화면이 근거를 부풀리는 종류의 결함이다.
--
-- ## 두 상태의 출처는 의미가 다르다 (그래서 계산도 갈린다)
--
-- ① 상권이 나열되는 상태(districts 비어 있지 않음)
--    화면이 말하는 것 = "이 건물은 역삼역 상권에 있다".
--    그 문장의 근거는 **매칭된 그 상권들**뿐이다 ⇒ 출처도 그 상권들의 것만.
--
-- ② "없음" 상태(covered=true, districts=[])
--    화면이 말하는 것 = "어느 상권 경계에도 들지 않는다".
--    이건 그 시·도 **자료 전부를 상대로** 내린 판정이다(전부를 뒤져서 하나도 없었다는 뜻)
--    ⇒ 그 전부가 근거이므로 시·도 전체 출처를 밝히는 것이 정직하다. 여기서 매칭된 것만
--      쓰면 목록이 비어 출처가 통째로 사라지는데, 판정은 분명 자료를 읽고 내렸으므로
--      그건 근거를 감추는 것이 된다.
--
-- ③ covered=false 는 읽을 자료 자체가 없으므로 sources=[] (기존과 같다).
--
-- ⚠️ 응답 모양은 그대로다(covered·districts·sources 세 키). 프론트 변경 불필요.
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
  ),
  -- 실제로 이 건물을 담고 있는 상권. districts 와 sources 가 **같은 집합**을 보게
  -- 한 번만 정의한다(따로 쓰면 오늘 고친 이 어긋남이 다시 생긴다).
  hit as (
    select d.district_id, d.district_nm, d.district_type, d.source_nm, d.area_m2
    from district d cross join me
    where st_contains(d.geom, me.geom)
  )
  select jsonb_build_object(
    'covered', exists (select 1 from district d cross join me
                       where left(d.sigungu_code, 2) = me.sido),
    'districts', coalesce((
      select jsonb_agg(jsonb_build_object('name', h.district_nm, 'type', h.district_type)
                       order by h.area_m2 asc, h.district_id)
      from hit h
    ), '[]'::jsonb),
    'sources', coalesce((
      select jsonb_agg(s.source_nm order by s.source_nm)
      from (
        select distinct d.source_nm
        from district d cross join me
        where d.source_nm is not null
          -- ★ 두 상태가 갈리는 유일한 지점 (위 주석 ①·② 참조)
          --   상권이 잡혔으면 → 그 상권들의 출처만 ("이 건물은 여기 있다"의 근거)
          --   하나도 안 잡혔으면 → 시·도 전체의 출처 ("어디에도 없다"는 판정의 근거)
          and case when exists (select 1 from hit)
                   then d.district_id in (select h.district_id from hit h)
                   else left(d.sigungu_code, 2) = me.sido
              end
      ) s
    ), '[]'::jsonb)
  );
$$;

comment on function list_building_districts(text) is
  '§8.6 이 건물이 속한 상권 목록. 겹치면 전부 준다(좁은 상권 먼저). '
  'covered=false 는 "그 시·도에 상권 경계 자료가 아직 없다"는 뜻이라 빈 목록(경계 밖)과 다르다 — '
  '지역명을 화면에 박지 않으려고 표에서 직접 센다(자료가 늘면 화면이 저절로 따라온다). '
  'sources 는 화면이 밝힐 출처(district.source_nm)이며 **두 상태에서 의미가 다르다**: '
  '상권이 나열되면 그 상권들의 출처만(안 쓴 자료를 덧붙이면 지어낸 출처가 된다), '
  '"없음" 판정이면 그 시·도 전체의 출처(그 자료 전부를 뒤져서 내린 판정이라 전부가 근거다). '
  'security definer (district·building·parcel 이 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 상권 이름·종류·출처뿐)';

-- create or replace 는 권한을 유지하지만, 이 파일만 보고 새로 만들 때를 대비해 다시 연다
-- (2026-08-13g 이후 함수는 기본으로 닫혀 있다).
grant execute on function list_building_districts(text) to anon, authenticated;
