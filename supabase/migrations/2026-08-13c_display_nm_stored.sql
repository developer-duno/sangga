-- =====================================================================
-- 표시명을 컬럼에 담아 둔다 — 뷰가 함수를 안 불러도 되게 (2026-08-13)
-- =====================================================================
-- ## 무엇이 어긋나 있었나
--
-- 2026-08-10 에 "도우미 함수는 공개 롤에게 열지 않는다"고 정하고 anon 에서 회수했다.
-- 그런데 그 순간 **층별 스택 화면이 401 로 죽었다**(2026-08-12 실측:
-- `permission denied for function building_display_nm`). 급히 되돌렸고, 그 뒤로
-- 정본(schema.sql)은 "회수한다"고 적혀 있는데 라이브는 열려 있는 상태가 됐다.
-- 정본이 거짓말을 하고 있었던 것이다.
--
-- ## 왜 회수하면 화면이 죽었나
--
-- 뷰는 **원본 표**를 읽을 때만 소유자 권한으로 읽는다. 뷰 본문에서 부르는 **함수의
-- 실행 권한은 지금 접속한 롤(anon)로 검사**된다. v_floor_stack 이 본문에서
-- building_display_nm() 을 부르고 있었으므로, 함수를 닫는 순간 뷰가 통째로 막혔다.
-- (search_buildings 는 security definer 라 영향이 없었다 — 그래서 검색만 멀쩡해 보였고,
--  내 검증이 컬럼을 좁혀 부르는 바람에 함수 호출을 우회해 200 을 보고 "안 깨졌다"고
--  잘못 판정했다. 화면이 실제로 보내는 요청 그대로 확인해야 한다는 교훈.)
--
-- ## 처방 — 함수를 부르지 말고 **미리 계산해 둔 값**을 읽는다
--
-- building.nm_key 가 이미 쓰고 있는 방식 그대로다(2026-08-11e). 표시명도 같은 방법으로
-- 컬럼에 담으면 뷰는 컬럼만 읽으면 되고, 함수는 닫아도 화면이 산다.
-- 덤으로 뷰·검색이 행마다 정규식 두 번을 돌리지 않게 된다.
--
-- ⚠️ generated ... stored 는 IMMUTABLE 함수만 쓸 수 있다. building_display_nm 은 IMMUTABLE 이다.
-- ⚠️ 242,631행 테이블에 컬럼을 붙이므로 잠깐 테이블을 다시 쓴다(수 초).
alter table building
  add column if not exists display_nm text
  generated always as (building_display_nm(bld_nm, dong_nm)) stored;

comment on column building.display_nm is
  '화면에 보일 건물 이름 = building_display_nm(bld_nm, dong_nm) 을 미리 계산해 둔 값. '
  '뷰가 함수를 직접 부르면 그 함수를 anon 에게 열어 둘 수밖에 없다(뷰 안의 함수 실행 권한은 '
  '뷰 소유자가 아니라 접속한 롤로 검사된다) — 그래서 값을 컬럼에 담아 함수를 닫는다(2026-08-13).';

-- ── 뷰 두 개가 컬럼을 읽게 바꾼다 ────────────────────────────────────────────
create or replace view v_floor_stack as
select
  s.bld_id,
  s.pnu,
  s.floor_no,
  s.floor_label,
  s.floor_area_m2,
  s.floor_area_gross_m2,
  s.segment_cnt,
  s.main_use,
  s.uses,
  -- ⚠️ 원본 건물명이 아니라 화면에 보일 이름이다(동명칭 폴백 + 개인 성명 가림).
  --    함수를 부르지 않고 미리 계산해 둔 컬럼을 읽는다 — 값은 같고, 함수를 닫을 수 있다.
  b.display_nm as bld_nm,
  b.approve_date,
  b.is_jiphap,
  p.road_addr,
  p.road_contact,
  pb.bld_cnt_in_pnu,
  st.store_cnt,
  st.stores
from v_building_floor_stack s
join building b on b.bld_id = s.bld_id
join parcel   p on p.pnu    = s.pnu
join lateral (
  select count(*)::int as bld_cnt_in_pnu
  from building b2
  where b2.pnu = s.pnu
) pb on true
left join lateral (
  select
    count(*)::int as store_cnt,
    jsonb_agg(jsonb_build_object('name', ub.biz_name, 'cat', ub.cat_s_nm)) as stores
  from unit_business ub
  where ub.pnu = s.pnu
    and ub.floor_no = s.floor_no
    and ub.snapshot_ym = (select max(snapshot_ym) from unit_business)
) st on true;

create or replace view v_unit_current as
select
  u.unit_id,
  u.bld_id,
  u.pnu,
  u.floor_no,
  u.ho,
  u.excl_area_m2,
  b.display_nm as bld_nm,
  b.approve_date,
  p.road_addr,
  p.road_contact,
  ub.biz_name,
  ub.cat_s_nm,
  ub.snapshot_ym,
  (ub.biz_no is null) as is_vacant,
  u.lat,
  u.lng
from unit u
join building b on b.bld_id = u.bld_id
join parcel   p on p.pnu    = u.pnu
left join lateral (
  select x.biz_no, x.biz_name, x.cat_s_nm, x.snapshot_ym
  from unit_business x
  where x.unit_id = u.unit_id
  order by x.snapshot_ym desc
  limit 1
) ub on true;

-- ── 이제 도우미 함수를 닫는다 (2026-08-10 의 원래 의도) ──────────────────────
-- ⛔ `from public` 만으로는 아무것도 안 닫힌다 — PUBLIC 은 실제 롤이 아니라 가상 그룹이라
--    anon·authenticated 가 **직접** 받은 GRANT 는 그대로 남는다(PostgreSQL 공식
--    sql-revoke.html + 2026-08-10 라이브 실측). 그래서 세 대상을 모두 적는다.
revoke all on function mask_person_name(text) from public, anon, authenticated;
revoke all on function building_display_nm(text, text) from public, anon, authenticated;
