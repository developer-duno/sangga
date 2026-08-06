-- =====================================================================
-- 상가 공간분석 플랫폼 — DB 스키마 v1.0
-- 대상: Supabase (PostgreSQL 15+ / PostGIS)
-- 사용법: Supabase 대시보드 → SQL Editor → 전체 붙여넣기 → Run
-- =====================================================================
--
-- 구조: 필지(parcel) → 건물(building) → 호실(unit) 3층
--   아파트는 2층으로 충분했지만 상가는 호실 단위까지 내려가야 한다.
--
-- 층 표기 규칙 (절대 규칙):
--   지상 n층 = n / 지하 n층 = -n / 옥탑 = 99 / 불명 = NULL
--   0을 쓰지 말 것. 지하와 결측이 섞이면 집계가 오염된다.
-- =====================================================================

create extension if not exists postgis;
create extension if not exists pg_trgm;   -- 상호명 부분검색용

-- =====================================================================
-- L0. bjd_code — 법정동코드 (행정표준코드관리시스템, code.go.kr)
-- =====================================================================
-- PNU 조립·시군구코드 조회의 기준 테이블. 존재/폐지 이력을 모두 보관한다.
-- 폐지된 코드도 지우지 않는 이유: 과거 실거래(수십 년 전 계약)가 그 시절 코드로
-- 찍혀 있을 수 있어, 폐지 코드까지 남겨둬야 과거 데이터 조인이 끊기지 않는다.
create table if not exists bjd_code (
  bjd_code      char(10)  primary key,             -- 법정동코드 10자리
  sigungu_code  char(5)   not null,                -- bjd_code 앞 5자리. 실거래가 API 조회 키·parcel.sigungu_code 조인용
  bjd_nm        text      not null,                -- 법정동명 전체 원본 (예: '서울특별시 종로구 청운동')
  sido_nm       text,                              -- 시도명 (법정동코드 자릿수 계층으로 상위 코드 행에서 파생. 세종처럼 시도 전용 코드가 없으면 시군구 레벨 행의 이름을 그대로 사용)
  sigungu_nm    text,                              -- 시군구명 (파생, 그 레벨 행이 없으면 NULL. '용인시 처인구'처럼 시 아래 구가 있으면 합쳐서 보관)
  emd_nm        text,                              -- 읍면동명 (파생, 그 레벨 행이 없으면 NULL)
  ri_nm         text,                              -- 리명 (파생, 리 레벨 행이 아니면 NULL)
  is_active     boolean   not null,                -- true=존재 / false=폐지
  updated_at    timestamptz default now()
);

comment on table bjd_code is '법정동코드 전체자료(code.go.kr /etc/codeFullDown.do). 폐지 코드 포함 전량 적재';
comment on column bjd_code.sigungu_code is 'PNU 19자리 = 법정동코드(10) + 대지구분(1) + 본번(4) + 부번(4) 조립의 1단계 재료';

create index if not exists idx_bjd_sigungu on bjd_code (sigungu_code);
create index if not exists idx_bjd_active  on bjd_code (is_active);

-- =====================================================================
-- L1. parcel — 필지
-- =====================================================================
create table if not exists parcel (
  pnu             char(19)  primary key,            -- 필지고유번호 19자리
  bjd_code        char(10)  not null,               -- 법정동코드
  sigungu_code    char(5)   not null,               -- 실거래가 API 조회 키
  sido_nm         text,
  sigungu_nm      text,
  emd_nm          text,
  jibun           text,                             -- '358-1'
  road_addr       text,
  land_area_m2    numeric(12,2),
  jimok           text,                             -- 지목
  use_zone        text,                             -- 용도지역
  road_contact    text,                             -- 도로접면 ★ 상가 가격 최대 변수
  land_price      integer,                          -- 개별공시지가 원/㎡
  land_price_year smallint,
  lat             double precision,
  lng             double precision,
  geom            geometry(Point, 4326),
  updated_at      timestamptz default now()
);

comment on column parcel.road_contact is '광대로한면/중로각지/세로한면 등. 상가 단가를 배 단위로 가르는 변수';

create index if not exists idx_parcel_sigungu on parcel (sigungu_code);
create index if not exists idx_parcel_geom    on parcel using gist (geom);

-- =====================================================================
-- L2. building — 건물
-- =====================================================================
create table if not exists building (
  bld_id          text      primary key,            -- pnu + '_' + 동명칭
  pnu             char(19)  not null references parcel(pnu) on delete cascade,
  dong_nm         text,
  bld_nm          text,
  total_area_m2   numeric(12,2),                    -- 연면적
  ground_floors   smallint,
  under_floors    smallint,
  approve_date    date,                             -- 사용승인일
  main_use        text,                             -- 주용도
  bcr             numeric(6,2),                     -- 건폐율
  far             numeric(7,2),                     -- 용적률
  parking_cnt     integer,
  is_jiphap       boolean default false,            -- 집합건물 여부
  updated_at      timestamptz default now()
);

comment on column building.is_jiphap is '집합건물만 실거래가에 층이 나온다. 일반건축물(통건물)은 지번도 일부만 공개';

create index if not exists idx_building_pnu on building (pnu);
create index if not exists idx_building_nm  on building using gin (bld_nm gin_trgm_ops);

-- =====================================================================
-- L3. unit — 호실 ★ 분석 주력
-- =====================================================================
create table if not exists unit (
  unit_id       text     primary key,               -- bld_id + '_' + floor + '_' + ho
  bld_id        text     not null references building(bld_id) on delete cascade,
  pnu           char(19) not null,                  -- 조회 최적화용 비정규화
  floor_no      smallint,                           -- 지상n=n / 지하n=-n / 옥탑=99 / 불명=NULL
  ho            text,
  excl_area_m2  numeric(10,2),                      -- 전용면적
  floor_use     text,                               -- 층별 주용도 (층별개요)
  lat           double precision,
  lng           double precision,
  geom          geometry(Point, 4326),
  updated_at    timestamptz default now(),
  constraint chk_floor_not_zero check (floor_no is null or floor_no <> 0)
);

create index if not exists idx_unit_bld   on unit (bld_id, floor_no);
create index if not exists idx_unit_pnu   on unit (pnu);
create index if not exists idx_unit_geom  on unit using gist (geom);
create index if not exists idx_unit_floor on unit (floor_no) where floor_no is not null;

-- =====================================================================
-- L3-a. unit_business — 호실별 업종 분기 스냅샷 ★ append only
-- =====================================================================
-- 절대 UPDATE/DELETE 하지 않는다. 분기마다 INSERT만.
-- 공실 이력·점포 생존기간이 전부 여기서 나온다. 소급 수집 불가.
create table if not exists unit_business (
  snapshot_ym   char(6)  not null,                  -- '2026Q3' 또는 '202609'
  biz_no        text     not null,                  -- 상가업소번호
  unit_id       text,                               -- 매칭 실패 시 NULL 허용
  pnu           char(19),
  floor_no      smallint,
  ho            text,
  biz_name      text,                               -- 상호명 ★ 검색 킬러 기능
  branch_nm     text,
  cat_l_cd      char(2),
  cat_l_nm      text,
  cat_m_cd      char(4),
  cat_m_nm      text,
  cat_s_cd      char(6),
  cat_s_nm      text,
  ksic_cd       text,                               -- 표준산업분류
  road_addr     text,
  lat           double precision,
  lng           double precision,
  geom          geometry(Point, 4326),
  created_at    timestamptz default now(),
  primary key (snapshot_ym, biz_no),
  constraint chk_ub_floor check (floor_no is null or floor_no <> 0)
);

comment on table unit_business is '분기 스냅샷. append only. 이전 분기에 있고 이번에 없으면 폐업/이전 = 공실 후보';
comment on column unit_business.biz_no is '업종분류 개편(837→247) 시 번호가 새로 생성되어 과거와 연계 불가. 주소+상호명 재매칭 필요';

create index if not exists idx_ub_unit     on unit_business (unit_id, snapshot_ym);
create index if not exists idx_ub_pnu      on unit_business (pnu, snapshot_ym);
create index if not exists idx_ub_name     on unit_business using gin (biz_name gin_trgm_ops);
create index if not exists idx_ub_cat      on unit_business (cat_s_cd, snapshot_ym);
create index if not exists idx_ub_geom     on unit_business using gist (geom);

-- =====================================================================
-- L3-b. transaction — 실거래 (매매만. 상가 임대는 데이터가 없음)
-- =====================================================================
create table if not exists transaction (
  tx_id         text     primary key,               -- 해시 (중복 방지)
  pnu           char(19),                           -- 통건물은 조립 실패 가능 → NULL 허용
  bld_id        text,
  sigungu_code  char(5)  not null,
  emd_nm        text,
  bld_nm        text,
  floor_no      smallint,                           -- 정규화된 정수
  bld_area_m2   numeric(10,2),
  land_area_m2  numeric(12,2),
  price_won     bigint   not null,
  unit_price    numeric(14,2)                       -- 원/㎡ (생성 컬럼)
                generated always as (
                  case when bld_area_m2 > 0 then price_won / bld_area_m2 end
                ) stored,
  contract_ym   char(6)  not null,
  contract_day  smallint,
  build_year    smallint,
  tx_type       text,                               -- '집합' / '일반'
  main_use      text,
  created_at    timestamptz default now(),
  constraint chk_tx_floor check (floor_no is null or floor_no <> 0)
);

create index if not exists idx_tx_pnu    on transaction (pnu, contract_ym);
create index if not exists idx_tx_region on transaction (sigungu_code, contract_ym);
create index if not exists idx_tx_floor  on transaction (sigungu_code, floor_no, contract_ym);

-- =====================================================================
-- L4. district — 상권 (사전계산 대상 ★ 엔진 패턴)
-- =====================================================================
-- 전국 수천 개 규모. 미분양 엔진과 같은 크기라 지표 전부 사전계산 가능.
create table if not exists district (
  district_id     text primary key,
  district_nm     text,
  district_type   text,                             -- 역세권/근린/대학가/오피스/관광
  sigungu_code    char(5),
  geom            geometry(MultiPolygon, 4326),
  center_lat      double precision,
  center_lng      double precision,
  area_m2         numeric(14,2),
  store_cnt       integer,
  franchise_ratio numeric(5,2),                     -- 상권 성숙도 지표
  dna_vector      jsonb,                            -- 8차원 유사도 벡터
  metrics         jsonb,                            -- 정규화 점수 0~100
  raw_metrics     jsonb,                            -- 원본값 (주석 표시용)
  computed_at     timestamptz
);

comment on column district.metrics is '정규화 점수. 화면 순위용';
comment on column district.raw_metrics is '원본값. 주석에 출처·기준시점과 함께 노출';

create index if not exists idx_district_geom on district using gist (geom);
create index if not exists idx_district_type on district (district_type);

-- =====================================================================
-- L5. rent_stat — 한국부동산원 임대동향조사
-- =====================================================================
-- 상가 임대료 실거래는 존재하지 않는다. 이 통계로 역산하는 것이 유일한 경로.
create table if not exists rent_stat (
  quarter          char(6) not null,                -- '2026Q2'
  region_code      text    not null,
  region_nm        text,
  bld_type         text    not null,                -- 오피스/중대형상가/소규모상가/집합상가
  vacancy_rate     numeric(5,2),                    -- 공실률 %
  rent_per_m2      numeric(10,2),                   -- 임대료 천원/㎡
  yield_rate       numeric(5,2),                    -- 수익률 %
  conversion_rate  numeric(5,2),                    -- 전환률 %
  rent_price_index numeric(8,2),
  floor_util_ratio jsonb,                           -- 층별효용비율 {"1":100,"2":45,...}
  created_at       timestamptz default now(),
  primary key (quarter, region_code, bld_type)
);

comment on column rent_stat.floor_util_ratio is '1층=100 기준. 층별 임대료 추정의 유일한 공식 근거';

-- =====================================================================
-- 운영: collect_progress — 이어받기 ★
-- =====================================================================
-- 6만 호출을 한 번에 성공시킬 방법은 없다. 중단돼도 이어서 하는 구조가 답.
create table if not exists collect_progress (
  collector     text not null,                      -- 'rtms_commercial'
  scope_key     text not null,                      -- 시군구코드
  period_key    text not null,                      -- 년월
  status        text not null default 'pending',    -- pending/done/failed/skipped
  row_count     integer,
  error_msg     text,
  attempts      smallint default 0,
  updated_at    timestamptz default now(),
  primary key (collector, scope_key, period_key),
  constraint chk_status check (status in ('pending','done','failed','skipped'))
);

create index if not exists idx_progress_pending
  on collect_progress (collector, status) where status = 'pending';

-- =====================================================================
-- 운영: api_quota_log — 일일 호출량 추적
-- =====================================================================
create table if not exists api_quota_log (
  log_date    date not null default current_date,
  collector   text not null,
  api_name    text not null,
  call_count  integer not null default 0,
  primary key (log_date, collector, api_name)
);

-- =====================================================================
-- 뷰: v_unit_current — 최신 분기 기준 호실 현황
-- =====================================================================
create or replace view v_unit_current as
select
  u.unit_id,
  u.bld_id,
  u.pnu,
  u.floor_no,
  u.ho,
  u.excl_area_m2,
  b.bld_nm,
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

comment on view v_unit_current is '최신 스냅샷 기준. is_vacant는 D등급(간접 추론) 지표이므로 화면에서 구분 표시할 것';

-- =====================================================================
-- 완료
-- =====================================================================
-- 다음 단계:
--   1) 법정동코드 적재
--   2) 상권정보 분기 파일 → unit_business + parcel/building/unit
--   3) 조인 성공률 측정 (90% 미만이면 정규화 로직 재점검)
-- =====================================================================
