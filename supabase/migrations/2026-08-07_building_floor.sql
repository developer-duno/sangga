-- =====================================================================
-- 마이그레이션 2026-08-07 — 층별개요(building_floor) + 층별 스택 뷰 2종
-- =====================================================================
-- 왜: §8.6 층별 스택 뷰를 "호실 쌓기"로 만들면 강남 건물의 82%가 빈 화면이 된다
--     (전유공용면적은 집합건물에만 존재해 1,083/5,903 = 18.35%). 층별개요는
--     5,903/5,903 = 100%를 덮으므로 "층 쌓기"로 만든다.
--
-- 어떻게 쓰나: Supabase 대시보드 → SQL Editor → New query → 이 파일 전체
--             붙여넣기 → Run. 몇 번을 실행해도 안전하다(전부 if not exists /
--             create or replace). 기존 테이블과 데이터는 건드리지 않는다.
--
-- 정본은 supabase/schema.sql이다. 이 파일은 이미 스키마가 적용된 라이브 DB에
-- "이번에 늘어난 것만" 얹기 위한 발췌본이며, 둘이 같은 결과를 내는지는 일회용
-- Postgres 컨테이너에서 대조 검증했다(2026-08-07).
-- =====================================================================

-- =====================================================================
-- L2-a. building_floor — 층별개요 ★ 층별 스택 뷰(§8.6)의 재료
-- =====================================================================
-- 한 행 = "그 층의 한 용도 구획". 원본은 한 층이 용도별로 여러 줄로 쪼개져 온다
-- (실측: 어느 4층 하나가 사무소·일반음식점 5개·예식장 4개·복도·계단 등 19줄).
-- 층 하나로 뭉쳐 담지 않는 이유: 뭉치는 건 뷰로 언제든 되지만 버린 세부는
-- 되살릴 수 없다. 뭉쳐 보려면 v_building_floor_stack을 쓴다.
--
-- ⚠️ 원본에는 행을 1:1로 가리킬 자연키가 없다 — (건물·층·용도·세부용도·
-- 제외여부·부속구분)을 전부 합쳐도 713그룹이 중복이다(같은 층에 같은 이름의
-- 일반음식점 7구획 등). 그래서 unit과 똑같이 **같은 키는 면적을 합산**하고
-- 합쳐진 원본 줄 수를 src_row_cnt에 남긴다. 남은 후보인 rnum(응답 내 순번)은
-- 대장에 행이 하나만 추가·삭제돼도 뒤가 통째로 밀리므로 영속 키가 못 된다.
create table if not exists building_floor (
  floor_id       text     primary key,   -- bld_id + '_' + 층 + '_' + 용도코드 + '_' + 세부용도 + '_' + 플래그
  bld_id         text     not null references building(bld_id) on delete cascade,
  pnu            char(19) not null,                -- 조회 최적화용 비정규화 (unit과 같은 관례)
  floor_no       smallint,                         -- 지상n=n / 지하n=-n / 옥탑=99 / 불명=NULL
  flr_gb_nm      text,                             -- '지상'/'지하'/'옥탑' 원본 이름표
  flr_no_nm      text,                             -- '지3층'·'옥탑1층' 등 원본 표기
  main_purps_cd  text,                             -- 주용도코드
  main_purps_nm  text,                             -- 주용도명 ★ 스택 뷰 '업종' 열의 재료
  etc_purps      text,                             -- 기타용도 — 실제 쓰임새가 여기 있다('예식실'·'계단실')
  strct_nm       text,                             -- 구조
  area_m2        numeric(12,2),                    -- 같은 키 원본 행들의 면적 합
  area_excluded  boolean  not null default false,  -- true = 연면적 산정 제외분
  is_annex       boolean  not null default false,  -- true = 부속건축물
  src_row_cnt    smallint,                         -- 이 행으로 합쳐진 원본 줄 수
  updated_at     timestamptz default now(),
  constraint chk_bf_floor check (floor_no is null or floor_no <> 0)
);

comment on table building_floor is
  '건축HUB 층별개요(getBrFlrOulnInfo). 한 행 = 그 층의 한 용도 구획. §8.6 층별 스택 뷰의 유일한 재료';
comment on column building_floor.area_excluded is
  'areaExctYn=1. 계단실·물탱크실·옥탑 등 연면적 산정에서 빠지는 부분. 데이터 근거(2026-08-07 강남 실측): '
  '층별개요 면적을 전부 더하면 표제부 연면적과 ±1% 일치가 64.1%인데, 이 행들을 빼면 82.6%로 오른다. '
  '부속건축물까지 빼면 81.7%로 도로 떨어지므로 부속은 연면적에 포함된다. 임대 가능 면적에 가까운 값이 '
  '필요하면 area_excluded=false만 합산할 것';
comment on column building_floor.floor_no is
  '옥탑은 층수가 몇이든 99 하나로 합쳐진다(절대 규칙 4). 실측상 옥탑1~옥탑19층이 존재하므로 '
  '원본 층 표기가 필요하면 flr_no_nm를 볼 것';
comment on column building_floor.src_row_cnt is
  '원본에 자연키가 없어 같은 키 행을 합산했다. 2 이상이면 그 층에 같은 용도 구획이 여럿이라는 뜻';

create index if not exists idx_bf_bld   on building_floor (bld_id, floor_no);
create index if not exists idx_bf_pnu   on building_floor (pnu, floor_no);
create index if not exists idx_bf_purps on building_floor (main_purps_cd);

-- =====================================================================
-- 기존 뷰 v_unit_current — 경고 문구 보강 (뷰 정의 자체는 그대로)
-- =====================================================================
comment on view v_unit_current is
  '최신 스냅샷 기준. is_vacant는 D등급(간접 추론) 지표이므로 화면에서 구분 표시할 것. '
  '⛔ §8.6 층별 스택 뷰에는 쓰지 말 것 — unit_business.unit_id가 라이브 전 행 NULL(상권정보에 호정보가 '
  '없다)이라 이 뷰는 호실 63,717행 100%를 공실로 판정한다(2026-08-07 실측). 스택 뷰는 v_floor_stack을 쓴다';

-- =====================================================================
-- 뷰: v_building_floor_stack — 층 단위 집계 (§8.6 스택 뷰 1단)
-- =====================================================================
-- building_floor의 용도별 행을 (건물, 층) 하나로 뭉친다. floor_area_m2는
-- 연면적 산정 제외분(계단실·물탱크실 등)을 뺀 값이라 임대 가능 면적에 가깝고,
-- floor_area_gross_m2는 전부 더한 값이다. 세부 구획은 uses(jsonb)에 면적 큰
-- 순으로 남아 있어, 층을 펼쳤을 때 "사무소 684㎡ / 일반음식점 3곳 424㎡"를
-- 그대로 보여줄 수 있다.
create or replace view v_building_floor_stack as
select
  f.bld_id,
  f.pnu,
  f.floor_no,
  max(f.flr_no_nm)  filter (where not f.area_excluded)          as floor_label,
  sum(f.area_m2)    filter (where not f.area_excluded)          as floor_area_m2,
  sum(f.area_m2)                                                as floor_area_gross_m2,
  count(*)          filter (where not f.area_excluded)          as segment_cnt,
  (array_agg(f.main_purps_nm order by f.area_m2 desc nulls last)
     filter (where not f.area_excluded))[1]                     as main_use,
  jsonb_agg(jsonb_build_object(
              'use', f.main_purps_nm, 'detail', f.etc_purps, 'area_m2', f.area_m2)
            order by f.area_m2 desc nulls last)
     filter (where not f.area_excluded)                         as uses
from building_floor f
where f.floor_no is not null                    -- 층을 못 정한 행은 스택에 쌓을 자리가 없다
group by f.bld_id, f.pnu, f.floor_no;

comment on view v_building_floor_stack is
  '층 단위 집계. main_use는 그 층에서 면적이 가장 큰 용도(첫 행이 아니라 최대 면적 기준)';

-- =====================================================================
-- 뷰: v_floor_stack — 층별 스택 뷰 본체 (§8.6)
-- =====================================================================
-- 층 집계에 건물·필지·점포를 붙인다. Phase 2 시점에 채울 수 있는 열은
-- 층·용도·면적·점포 4개다 — 추정 시세는 Phase 3, 공실 이력은 Phase 5 산출물.
--
-- ⚠️ 점포는 (PNU, 층)으로 붙는다 — 상권정보에 호정보가 전수 결측이라 호 단위로는
-- 붙일 방법이 원천적으로 없다(§8.6). 그래서 한 필지에 건물이 여럿이면 **같은 점포가
-- 각 건물에 중복으로 달린다.** bld_cnt_in_pnu > 1인 행은 그 모호성을 안고 있으므로
-- 화면에서 D등급(간접 추론)으로 구분 표시할 것. 강남 실측 5,903건물/5,375필지라
-- 대부분 1이지만 0은 아니다(직접 재현해 확인함).
--
-- ⏳ 아직은 안 터지지만 조건이 갖춰지면 조용히 틀리는 것 둘 — 지금 라이브는 단일
--    분기(202603)·단일 시군구(강남)라 무해하나, 확장 시 반드시 손볼 것:
--   (1) 점포 분기를 (select max(snapshot_ym) from unit_business)로 고른다. 이건
--       **전역 최신 분기**라, 여러 분기가 쌓인 뒤 어떤 지역이 최신 분기에 없으면
--       그 지역 점포가 통째로 안 붙는다(빈 층으로 보임). 지역별 최신 분기로
--       바꾸거나 조회 파라미터로 빼야 한다. Phase 5(분기 누적) 착수 전 필수.
--   (2) 점포 lateral이 (pnu, floor_no)로 찾는데 unit_business에는 (pnu, snapshot_ym)
--       인덱스만 있다. 강남 6.4만 행에선 무해하지만 전국 수백만 행이면
--       (pnu, floor_no, snapshot_ym) 인덱스가 필요하다.
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
  b.bld_nm,
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

comment on view v_floor_stack is
  '§8.6 층별 스택 뷰. store_cnt/stores는 (PNU, 층) 매칭이라 bld_cnt_in_pnu>1이면 건물 간 중복 — D등급 표시 필수';
