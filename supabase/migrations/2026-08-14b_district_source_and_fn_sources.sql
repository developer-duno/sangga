-- =====================================================================
-- 상권 출처를 표에 담고, 화면이 그것을 읽게 한다 (2026-08-14)
-- =====================================================================
-- 지금까지 district 는 서울시 자료 한 벌뿐이라 화면에 출처 문구를 **글자로 박아** 두었다
-- (`출처: 서울특별시 상권분석서비스`). 대전 상권을 소상공인시장진흥공단 자료로 채우는
-- 순간 그 문구는 **거짓말이 된다** — 코드를 한 줄도 안 고쳤는데 화면이 틀린 말을 하는,
-- 결정 0006/0009 에서 이미 한 번 겪은 그 결함이다.
--
-- 그래서 출처를 행마다 갖게 하고(`district.source_nm`), 화면은 그 값을 그대로 보여준다.
-- 소스가 늘면 화면이 저절로 따라온다.
--
-- ⚠️ 이 마이그레이션은 **표 구조와 함수만** 바꾼다. 대전 자료 적재는 별도다
--    (scripts/collectors/load_sbiz_district.py).

-- ── 1. 출처 컬럼 ─────────────────────────────────────────────────────────────
alter table district
  add column if not exists source_nm text;

comment on column district.source_nm is
  '이 상권 경계를 어디서 받았나 — **화면에 그대로 보여줄 문구**로 넣는다 '
  '(공공누리 1유형은 출처표시가 의무라 화면에서 지울 수 없다). '
  '소스가 둘 이상이 된 순간(서울시 + 소상공인시장진흥공단) 화면에 박아 둔 고정 문구는 '
  '거짓말이 되므로, 문구를 코드가 아니라 자료가 들고 있게 한다.';

-- 지금 들어 있는 1,650행은 전부 서울시 자료다(결정 0008, 2026-08-14 적재).
-- 이 백필을 빼면 기존 행의 출처가 NULL 이 되어 **화면에서 출처 줄이 통째로 사라진다**.
update district
   set source_nm = '서울특별시 상권분석서비스'
 where source_nm is null;

-- 백필이 끝났으니 잠근다. 출처 없는 행이 생기는 순간 화면의 출처 줄이 **소리 없이**
-- 사라지는데(공공누리 1유형은 출처표시가 의무다), 에러가 아니라 "한 줄이 안 보일" 뿐이라
-- 아무도 눈치채지 못한다. 사람 기억이 아니라 DB 가 막게 한다.
-- 라이브 실측(2026-08-14): 1,687행 전부 채워져 있고, 쓰는 경로는 적재기 둘뿐이며
-- 둘 다 source_nm 을 담는다 — 지금 잠가도 아무것도 깨지지 않는다.
alter table district
  alter column source_nm set not null;

-- ── 2. 화면이 부르는 함수에 sources 를 얹는다 ────────────────────────────────
-- 최상위 키 `sources` 만 늘어난다. covered·districts 의 모양은 그대로다 —
-- 마이그레이션 전 라이브는 이 키를 안 주므로, 화면은 없으면 출처 줄만 조용히 생략한다.
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
    ), '[]'::jsonb),
    -- 출처는 화면이 지어내지 않고 **자료에서 읽는다**. 범위를 covered 와 똑같이(그 시·도)
    -- 잡는 이유: "어느 경계에도 안 듦"이라는 판정도 그 시·도 자료를 읽어서 내린 것이라
    -- 출처를 함께 밝혀야 한다. 한 시·도에 소스가 둘이면 둘 다 나간다.
    'sources', coalesce((
      select jsonb_agg(s.source_nm order by s.source_nm)
      from (select distinct d.source_nm
            from district d cross join me
            where left(d.sigungu_code, 2) = me.sido
              and d.source_nm is not null) s
    ), '[]'::jsonb)
  );
$$;

comment on function list_building_districts(text) is
  '§8.6 이 건물이 속한 상권 목록. 겹치면 전부 준다(좁은 상권 먼저). '
  'covered=false 는 "그 시·도에 상권 경계 자료가 아직 없다"는 뜻이라 빈 목록(경계 밖)과 다르다 — '
  '지역명을 화면에 박지 않으려고 표에서 직접 센다(자료가 늘면 화면이 저절로 따라온다). '
  'sources 는 그 시·도 자료의 출처 목록(district.source_nm) — 화면 출처 문구가 소스마다 따라간다. '
  'security definer (district·building·parcel 이 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 상권 이름·종류·출처뿐)';

-- create or replace 는 권한을 유지하지만, 이 파일만 보고 새로 만들 때를 대비해 다시 연다
-- (2026-08-13g 이후 함수는 기본으로 닫혀 있다).
grant execute on function list_building_districts(text) to anon, authenticated;
