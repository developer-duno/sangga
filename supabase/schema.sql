-- =====================================================================
-- 상가 공간분석 플랫폼 — DB 스키마 v1.0
-- 대상: Supabase (PostgreSQL 15+ / PostGIS)
-- 사용법: Supabase 대시보드 → SQL Editor → 전체 붙여넣기 → Run
--        (또는 `python scripts/dbx.py -f supabase/schema.sql` — .env 의
--         SANGGA_DATABASE_URL 로 직접 실행한다)
-- =====================================================================
--
-- ✅ **라이브와 일치한다 (2026-08-13 기준)**
--   `2026-08-13_search_scope_gate` 까지의 마이그레이션을 이 파일에 모두 반영했다.
--   2026-08-11 의 대조는 문서를 믿는 게 아니라 **라이브에서 직접 떠서 기계로 비교**했다:
--     · 함수 — pg_get_functiondef 본문을 문자 단위로 대조
--     · 인덱스 — pg_indexes 이름 집합을 대조 (죽은 식 인덱스 3개 제거)
--     · 컬럼 — information_schema.columns 로 저장 컬럼 3개 확인
--   ⛔ 앞으로 마이그레이션을 라이브에 적용하면 **이 파일에도 같이 반영할 것.**
--      어긋난 채로 두면 "새 환경 구축"이 조용히 다른 DB 를 만들어 낸다.
--      (실제로 11c 의 `search_key` 가 빠진 걸 아무도 몰랐다 — 이 파일만 보면
--       검색이 통째로 깨지는 DB 가 만들어졌을 것이다.)
--   ℹ️ 이제 사람이 안 세도 된다 — `tests/test_schema_migration_sync.py` 가 마이그레이션을
--      날짜순으로 재생해 이 파일에 빠진 것·죽은 것이 있으면 빨간불을 낸다.
--      개수를 여기 적어 두면 그 숫자가 먼저 낡으므로 일부러 적지 않는다.
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
-- 주소 검색용 인덱스는 여기 없다 — 아래 **§검색 키** 절에서 저장 컬럼
-- (parcel.road_addr_key)에 건다. 이유는 그 절에 적었다.
-- 이게 없으면 search_buildings 의 주소 가지가 parcel 전수 스캔이 된다
-- (2026-08-08 실측: 같은 선택도에서 비용 8배·시간 28배).

-- =====================================================================
-- L2. building — 건물
-- =====================================================================
create table if not exists building (
  bld_id          text      primary key,            -- pnu + '_' + 관리건축물대장PK(mgmBldrgstPk).
                                                      -- 동명칭이 아닌 이유: 같은 동명칭인데 서로 다른
                                                      -- 대장(별동·재건축 이력)이 실재하고(강남구 23그룹
                                                      -- 실측), 동명칭 텍스트는 정부 데이터 갱신으로
                                                      -- 바뀔 수 있어 영속 키로 부적합하다.
  pnu             char(19)  not null references parcel(pnu) on delete cascade,
  dong_nm         text,
  bld_nm          text,
  total_area_m2   numeric(12,2),                    -- 연면적
  ground_floors   smallint,
  under_floors    smallint,
  approve_date    date,                             -- 사용승인일
  main_use        text,                             -- 주용도
  -- ⚠️ numeric(6,2)(최대 9,999.99)였다가 2026-08-11 넓혔다. 원본에 건폐율이
  --    79,095% 인 행이 있어(전체 24만 중 7행) 적재가 통째로 멈췄다.
  --    집계에 쓸 때는 반드시 상한을 걸어 거를 것 — 한 행이 평균을 흔든다.
  bcr             numeric(10,2),                    -- 건폐율 (소스 오류값 포함)
  far             numeric(7,2),                     -- 용적률
  parking_cnt     integer,
  is_jiphap       boolean default false,            -- 집합건물 여부
  updated_at      timestamptz default now()
);

comment on column building.is_jiphap is '집합건물만 실거래가에 층이 나온다. 일반건축물(통건물)은 지번도 일부만 공개';

comment on column building.bcr is
  '건폐율 %. 정의상 0~100 이지만 원본에 소스 오류가 섞여 있다 '
  '(2026-08-11 실측: 전체 24만 행 중 7행이 1만%를 넘고 최댓값 79,095%). '
  '⚠️ 평균·분포 등 집계에 쓸 때는 반드시 상한을 걸어 거를 것 — 한 행이 통계를 통째로 흔든다. '
  'numeric(6,2)였을 때 그 7행이 적재를 통째로 멈춰 23,351행이 유실됐다(2026-08-11d로 해소).';

create index if not exists idx_building_pnu on building (pnu);
create index if not exists idx_building_nm  on building using gin (bld_nm gin_trgm_ops);

-- =====================================================================
-- 건물 표시명 — 동명칭 폴백 + 개인 성명 가리기 (2026-08-08e)
-- =====================================================================
-- 건축물대장에는 이름 칸이 둘이다. bld_nm(건물명)만 보면 **이름이 있는데 못 찾는
-- 건물이 404개** 생긴다 — dong_nm(동명칭)에만 진짜 이름이 든 경우다.
-- 실측(2026-08-08): bld_nm 없음 7,044 중 dong_nm 있음 688, 그 중 '주건축물제1동'
-- 같은 일반 라벨 284를 뺀 404가 진짜 이름(7층 이상 43개). 라이브에서 '노보텔'·
-- 'WeWork Building'·'강남텔레피아빌딩'이 전부 0건이었다.
--
-- 그리고 bld_nm 5,361개 중 93개가 '… 단독주택 (김남연)' 형태로 **개인 성명**을
-- 담고 있다(괄호 안 값 빈도가 거의 전부 1회 = 사람 이름의 특징).
--
-- 검색도 표시도 building_display_nm() 하나만 쓴다 → "보이는 것 = 검색되는 것".
-- 원본 표의 값은 건드리지 않는다(되돌릴 수 있게). 내보낼 때만 가린다.

-- 건물명 끝의 (사람이름)을 지운다. 괄호 안이 건물 지칭어면 그대로 둔다
-- ('썬프라자(태양빌딩)'·'은하빌딩2(신관)'은 보호). 이름만 남으면 NULL 로 돌려
-- 동명칭 폴백이 이어받게 한다. IMMUTABLE — 이 식 위에 인덱스를 걸어야 하기 때문.
create or replace function mask_person_name(nm text)
returns text
language sql
immutable
parallel safe
as $$
  select case
    when nm is null then null
    when nm ~ '\([가-힣]{2,4}\)\s*$'
     and nm !~ '\([가-힣]*(빌딩|타워|하우스|플라자|프라자|스퀘어|센터|주택|상가|본관|별관|신관|구관|아파트|오피스|사옥|회관|시장)[가-힣]*\)\s*$'
    then nullif(btrim(regexp_replace(nm, '\s*\([가-힣]{2,4}\)\s*$', '')), '')
    else nm
  end
$$;

comment on function mask_person_name(text) is
  '건물명 끝의 (사람이름)을 지운다. 원본 표는 그대로 두고 내보낼 때만 가린다. '
  'IMMUTABLE — 이 식 위에 인덱스를 걸기 위해 필요하다';

-- 화면에 보일 이름: 건물명(성명 가림) → 동명칭(일반 라벨 제외) → NULL
-- 일반 라벨 = 이름이 아니라 "몇 번째 동인지"를 적은 것. 실측 상위 15종
-- (주건축물제1동 190·가동 12·나동 11·1동 8·2동 7·A동 7·B동 6·1 5·주건축물제2동 2·
--  D동 2·근린생활시설 2·다동 1·2 1·C동 1·3동 1)을 아래 한 줄이 전부 덮는다.
--
-- ⛔ 아래 `public.` 을 떼지 말 것 (2026-08-08 실패로 확인).
--    CREATE INDEX 가 도는 동안 Postgres 는 보안을 위해 search_path 를
--    `pg_catalog, pg_temp` 로 **일시적으로 바꾼다**(공식 문서 명시). 그 순간
--    public 이 안 보이므로 이름만 적은 `mask_person_name(...)` 은
--    "함수가 존재하지 않습니다"(42883)로 실패하고 마이그레이션 전체가 되돌아간다.
--    함수가 없어서가 아니라 **그 순간에만 안 보여서** 나는 오류다.
create or replace function building_display_nm(bld_nm text, dong_nm text)
returns text
language sql
immutable
parallel safe
as $$
  select coalesce(
    nullif(btrim(public.mask_person_name(bld_nm)), ''),
    case
      when btrim(coalesce(dong_nm, '')) = '' then null
      when btrim(dong_nm) ~ '^((주|부속)?건축물)?(제)?[0-9]*동$|^[가-힣]동$|^[A-Za-z]동$|^[0-9]+$|^(근린생활시설|본관|별관|신관|구관|관리동|경비실|주차장|창고)$'
        then null
      else btrim(dong_nm)
    end
  )
$$;

comment on function building_display_nm(text, text) is
  '§8.1 화면에 보일 건물 이름. 건물명(성명 가림) → 동명칭(일반 라벨 제외) → NULL. '
  '검색과 표시가 이 함수 하나만 쓰므로 "보이는 것 = 검색되는 것"이 항상 일치한다';

-- 도우미 함수는 공개 롤에게 열지 않는다 — 뷰·검색 함수가 소유자 권한으로 대신 부른다.
-- ⚠️ `from public`만으로는 부족하다 — PUBLIC은 실제 롤이 아니라 가상 그룹이라,
--    Supabase가 새 함수 생성 시 anon·authenticated에게 자동으로 거는 **직접
--    GRANT**는 회수되지 않는다(PostgreSQL 공식 sql-revoke.html: "revoking ...
--    from PUBLIC does not necessarily mean that all roles have lost ...
--    privilege: those who have it granted directly ... will still have it").
--    라이브 실측(2026-08-10): 이 줄만 있던 상태에서 anon 공개키로 두 함수를
--    RPC 직접 호출하면 둘 다 HTTP 200이었다 — 반드시 anon·authenticated에서
--    직접 회수해야 한다(2026-08-10_revoke_helper_fns_from_anon.sql 참조).
revoke all on function mask_person_name(text) from public, anon, authenticated;
revoke all on function building_display_nm(text, text) from public, anon, authenticated;

-- 검색용 인덱스는 여기 없다 — 아래 **§검색 키** 절에서 저장 컬럼(building.nm_key)에 건다.
-- 이름이 둘 다 없는 건물은 NULL 이라 색인되지 않는다 = 이름으로는 안 찾힌다(의도).

-- =====================================================================
-- L2-a. building_floor — 층별개요 ★ 층별 스택 뷰(§8.6)의 재료
-- =====================================================================
-- 건축HUB getBrFlrOulnInfo. 호실(unit)과 달리 **모든 건물**에 존재한다.
-- 전유공용면적(=unit)은 집합건물에만 있어 강남 실측 1,083/5,903 = 18.35%에서
-- 막히지만, 층별개요는 5,903/5,903 = 100%다(2026-08-07 raw 63,053행 실측,
-- 건물 귀속 실패 0건). 그래서 스택 뷰는 "호실 쌓기"가 아니라 "층 쌓기"로 만든다.
--
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
-- 각주 집계(v_coverage_stats) 전용 **커버링** 인덱스 — 뷰가 쓰는 두 컬럼이 다 들어
-- 있어 힙에 안 간다(Index Only Scan). 없으면 pkey(snapshot_ym, biz_no)로 인덱스는
-- 타지만 행마다 힙 페이지를 한 번씩 방문해(최신 스냅샷 63.5만 행 = 버퍼 63.6만 회)
-- **캐시가 식은 첫 요청만 3초 제한을 넘겨 500**이 된다. 따뜻하면 200이라 재현이
-- 어렵다. 실측(2026-08-11f): 버퍼 636,527 → 698, 힙 방문 0, 1,028ms → 131ms, 8.6MB.
create index if not exists idx_ub_snapshot_floor on unit_business (snapshot_ym, floor_no);


-- ── 3) unit_business 의 "절대 UPDATE/DELETE 금지"가 말로만 있었다 ───────────
-- 분기 스냅샷은 포털에서 내려가면 **재수집이 불가능**하다(CLAUDE.md 절대 규칙 6).
-- 그래서 이 표는 append-only 로 쓰기로 했고 적재기도 그렇게 동작한다
-- (load_sangkwon_snapshot.py 는 ignore-duplicates 만 쓴다 — 2026-08-13 grep 확인:
--  UPDATE·DELETE 를 하는 코드가 한 줄도 없다).
-- 그런데 그 약속이 **주석에만** 있었다. 주석은 실수로 돌린 SQL 한 줄을 못 막는다.
--
-- ⚠️ 정당한 정비가 필요하면(예: 잘못 적재된 분기를 걷어내기) 잠깐 끄고 하면 된다:
--      alter table unit_business disable trigger unit_business_append_only;
--      ... 정비 ...
--      alter table unit_business enable trigger unit_business_append_only;
--    끄는 것 자체가 "지금 되돌릴 수 없는 일을 한다"는 신호가 되도록 일부러 한 단계 둔다.
-- ⚠️ 문(statement) 단위 트리거다. 한 가지 함정을 알고 있어야 한다 — PostgreSQL 은
--    `insert ... on conflict do update` 에서 **문 단위 UPDATE 트리거를 (한 행도 안 바뀌어도)
--    발동**시킨다. 지금 적재기는 unit_business 에 `ignore-duplicates`(= do nothing) 만 쓰므로
--    안 걸리지만(2026-08-13 확인: load_sangkwon_snapshot.py 141행 `"unit_business":
--    "ignore-duplicates"`), 누군가 `merge-duplicates` 로 바꾸면 적재가 통째로 막힌다.
--    그건 사고가 아니라 **의도한 경보**다 — append-only 를 깨는 변경이기 때문이다.
create or replace function unit_business_append_only()
returns trigger
language plpgsql
as $$
begin
  raise exception
    'unit_business 는 append-only 입니다 (시도: %). 분기 스냅샷은 포털에서 내려가면 '
    '재수집이 불가능합니다(절대 규칙 6). 정말 필요하면 트리거를 잠깐 끄고 하세요: '
    'alter table unit_business disable trigger unit_business_append_only;', tg_op
    using errcode = 'restrict_violation';
end
$$;

drop trigger if exists unit_business_append_only on unit_business;
create trigger unit_business_append_only
  before update or delete on unit_business
  for each statement
  execute function unit_business_append_only();

comment on function unit_business_append_only() is
  'unit_business 의 append-only 불변식을 DB 에서 강제한다. 주석으로만 있던 약속을 '
  '실제 방어로 바꾼 것(2026-08-13). 적재기는 ignore-duplicates 만 쓰므로 영향이 없다';

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

-- pnu 가 채워진 행은 7.8%뿐이다(2026-08-13 실측: 22,662행 중 1,757행). 조회는 항상 값이
-- 있는 pnu 를 찾으므로 NULL 을 뺀 부분 인덱스로 충분하다(idx_unit_floor 와 같은 방식).
create index if not exists idx_tx_pnu    on transaction (pnu, contract_ym) where pnu is not null;
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
  -- ⚠️ 원본 b.bld_nm 이 아니다. 동명칭 폴백 + 개인 성명 가림을 거친 값이다
  --    (v_floor_stack 과 같은 규칙 — 뷰마다 어긋나게 두지 않는다, 2026-08-13).
  building_display_nm(b.bld_nm, b.dong_nm) as bld_nm,
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

comment on view v_unit_current is
  '최신 스냅샷 기준. is_vacant는 D등급(간접 추론) 지표이므로 화면에서 구분 표시할 것. '
  '⚠️ bld_nm은 원본이 아니라 building_display_nm() 결과다(동명칭 폴백 + 개인 성명 가림, 2026-08-13). '
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
  -- ⚠️ 원본 건물명이 아니라 화면에 보일 이름이다(동명칭 폴백 + 개인 성명 가림).
  --    원본은 building.bld_nm 에 그대로 있고, 이 뷰는 내보낼 때만 가린다.
  building_display_nm(b.bld_nm, b.dong_nm) as bld_nm,
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
  '§8.6 층별 스택 뷰. store_cnt/stores는 (PNU, 층) 매칭이라 bld_cnt_in_pnu>1이면 건물 간 중복 — D등급 표시 필수. '
  '★ 공개 접근: 이 뷰만 anon/authenticated에게 SELECT 허용된다(아래 "공개 접근 정책" 절). '
  '원본 표는 RLS 켬 + 정책 0개 + 권한 회수로 닫혀 있고, 이 뷰가 소유자 권한으로 대신 읽는다. '
  '⚠️ bld_nm은 원본이 아니라 building_display_nm() 결과다(동명칭 폴백 + 개인 성명 가림, 2026-08-08e). '
  'ℹ️ 린트 0010(security definer view) 의도적 예외 — security_invoker=true로 되돌리면 원본 표 401 + 상호명·성명 노출 확대. '
  '재검토 방아쇠: 공개 배포일 / 지도·반경 검색(§6.4) 착수일';

-- =====================================================================
-- 뷰: v_coverage_stats — 스택 뷰 각주용 집계
-- =====================================================================
-- 화면 각주("점포 N곳 중 층이 없는 것이 M%")의 숫자를 런타임에 계산하기 위한 뷰.
-- 예전에는 이 숫자가 FloorStack.tsx에 문자열로 박혀 있었는데, 점포 데이터는
-- 아래 where 절대로 **최신 분기를 자동으로 따라가므로** 새 분기를 적재하는 순간
-- 코드 변경 0인 채로 각주만 옛 숫자를 말하게 된다.
--
-- ⚠️ v_floor_stack과 **똑같은** 분기 기준을 쓴다. 한쪽만 바꾸면 화면의 점포 목록과
--    각주가 서로 다른 분기를 말하게 되므로 항상 함께 고칠 것.
-- ⚠️ 내보내는 것은 집계값뿐이다 — 상호명·좌표·주소는 넣지 않는다(노출면 최소 원칙).
create or replace view v_coverage_stats as
select
  ub.snapshot_ym,
  count(*)                                                    as store_cnt,
  count(*) filter (where ub.floor_no is null)                 as floor_missing_cnt,
  round(100.0 * count(*) filter (where ub.floor_no is null)
        / count(*), 1)                                        as floor_missing_pct
from unit_business ub
where ub.snapshot_ym = (select max(snapshot_ym) from unit_business)
group by ub.snapshot_ym;
-- group by라 행이 있을 때만 결과가 나온다 = 0으로 나누는 경우가 없다.

comment on view v_coverage_stats is
  '§8.6 스택 뷰 각주용 집계. v_floor_stack과 동일한 전역 최신 분기 기준 — 둘을 항상 함께 고칠 것. '
  '★ 공개 접근: anon/authenticated에게 SELECT 허용(집계값만, 상호명 없음). '
  'ℹ️ 린트 0010(security definer view) 의도적 예외 — security_invoker=true로 되돌리면 원본 표(unit_business) 401. '
  '재검토 방아쇠: 공개 배포일 / 지도·반경 검색(§6.4) 착수일';

-- =====================================================================
-- 함수: search_buildings — 건물 검색 (§8.1 진입점)
-- =====================================================================
-- ⛔ 화면에서 "건물 × 층" 뷰를 표본으로 받아 건물로 접지 말 것. 층이 27개인 건물
--    하나가 27줄을 먹으므로 표본이 건물을 대표하지 못하고, 정렬을 bld_id로 주면
--    앞자리가 법정동 코드라 **검색 결과가 한 동네에 갇힌다**(2026-08-08 실측:
--    '빌딩' 매칭 15,068행인데 화면엔 역삼동 69개 건물뿐, '테헤란로' 10,517행 →
--    역삼동 95개뿐. 다른 동네는 재검색해도 안 나왔다).
--
-- 이 함수는 **건물 1개 = 1행**을 돌려주고 total_cnt로 정확한 전체 건수를 함께 준다.
-- 정렬은 지역이 아니라 이름 관련도이고, 층 수·최저/최고층·옥탑 여부까지 한 번에 준다.
--
-- ⚠️ security definer 인 이유: 원본 표가 anon에게 닫혀 있어(아래 공개 접근 정책)
--    이 함수가 소유자 권한으로 대신 읽는다. search_path를 고정해 가로채기를 막고,
--    입력은 파라미터로만 받아 문자열을 이어 붙이지 않는다(주입 4종 시험 통과).
-- 지번(구주소) 한 줄. 실무에서 "역삼동 823-4"로 찾는 일이 많아 검색 대상에 넣었다.
-- ⛔ concat_ws 는 IMMUTABLE 이 아니라 인덱스 식으로 못 쓴다 — text `||` 로 만든다.
create or replace function parcel_jibun_addr(
  sido text, sigungu text, emd text, jibun text
) returns text
language sql
immutable
parallel safe
as $$
  select nullif(btrim(
           coalesce(sido, '')    || ' ' ||
           coalesce(sigungu, '') || ' ' ||
           coalesce(emd, '')     || ' ' ||
           coalesce(jibun, '')
         ), '')
$$;

comment on function parcel_jibun_addr(text, text, text, text) is
  '지번(구주소) 한 줄. 예: 서울특별시 강남구 역삼동 823-4. '
  'parcel.jibun_addr_key 가 이 값을 search_key() 로 정규화해 저장한다.';

-- =====================================================================
-- 검색 키 — 정규화 함수 + 저장 컬럼 + 인덱스 (2026-08-11c · 11e)
-- =====================================================================
-- ① 왜 정규화하나 — **띄어쓰기 하나에 결과가 사라졌다**(라이브에서 발견).
--      '그랑프리빌딩'  → 1건 (찾힘)
--      '그랑프리 빌딩' → 0건 (못 찾음)   ← 같은 건물인데
--    실무에서 띄어쓰기는 사람마다 다르므로 이건 불편이 아니라 결함이다.
--    그래서 비교 전에 양쪽 모두 **공백을 없애고 소문자로** 바꾼다.
--    ⚠️ 어순을 바꾼 검색('빌딩 그랑프리')은 여전히 안 된다 — 흔한 문제는
--       띄어쓰기이지 어순이 아니라서, 가지를 늘리지 않고 이 방법을 택했다
--       (가지를 늘리면 '빌딩' 같은 흔한 단어가 더 느려진다. 알려진한계 참조).
--
-- ② 왜 식이 아니라 **컬럼에 저장**하나 — 식 인덱스는 흔한 검색어에서 3초 제한에
--    걸려 500을 냈다. EXPLAIN(2026-08-11)이 원인을 짚었다:
--      Bitmap Index Scan  → 후보 197,076건 (parcel 전체)
--      Bitmap Heap Scan   Rows Removed by Index Recheck: 196,680 → 최종 396건
--    2글자 검색어('명동')는 trigram 선별력이 없어 후보가 거의 전체가 되는데,
--    인덱스가 '식'이면 **재확인 때마다 regexp_replace 를 다시 돌린다.**
--    197,076번의 정규식이 진짜 시간 도둑이었다. 계산 결과를 컬럼에 담아 두면
--    재확인이 단순 문자열 비교가 된다 — **결과를 자르지 않고** 빨라진다.
--    ⛔ 그래서 식 인덱스(idx_building_display_nm · idx_parcel_road_addr ·
--       idx_parcel_jibun_addr)는 라이브에서 지웠다. 되살리지 말 것.
--
-- ⚠️ generated ... stored 는 IMMUTABLE 함수만 쓸 수 있다. 아래 셋 다 IMMUTABLE 이다.
create or replace function search_key(t text)
returns text
language sql
immutable
parallel safe
as $$
  select nullif(lower(regexp_replace(coalesce(t, ''), '\s+', '', 'g')), '')
$$;

comment on function search_key(text) is
  '검색 비교용 정규화 키 — 공백 제거 + 소문자. 인덱스 식과 WHERE 식이 갈라지지 '
  '않도록 전처리를 이 함수 하나로 묶었다(2026-08-11c).';

-- 도우미 함수는 anon 에게 열지 않는다 — 화면은 search_buildings 하나만 부르고,
-- 그 함수가 security definer 라 소유자 권한으로 이들을 대신 호출한다.
-- ⛔ `from public` 만 쓰면 **아무것도 안 닫힌다** — PUBLIC 은 실제 롤이 아니라
--    가상 그룹이라, anon·authenticated 가 **직접** 받은 GRANT 는 그대로 남는다
--    (PostgreSQL 공식 sql-revoke.html + 2026-08-10 라이브 실측으로 확인).
--    그래서 세 대상을 모두 적는다.
revoke all on function search_key(text) from public, anon, authenticated;
revoke all on function parcel_jibun_addr(text, text, text, text) from public, anon, authenticated;

-- ── 저장 컬럼 ────────────────────────────────────────────────────────────────
-- ⚠️ 테이블 정의부가 아니라 여기서 붙이는 이유: 저장 컬럼이 쓰는 함수
--    (search_key · building_display_nm · parcel_jibun_addr)가 그 위에서 정의되므로,
--    테이블을 만드는 시점에는 아직 함수가 없다.
alter table building
  add column if not exists nm_key text
  generated always as (search_key(building_display_nm(bld_nm, dong_nm))) stored;

comment on column building.nm_key is
  '검색용 정규화 이름(공백 제거+소문자). search_buildings 와 idx_building_nm_key 가 이 컬럼을 쓴다. '
  '식 인덱스였을 때는 후보 8만 건마다 regexp 를 다시 돌려 검색이 3초를 넘겼다(2026-08-11e).';

alter table parcel
  add column if not exists road_addr_key text
  generated always as (search_key(road_addr)) stored;

alter table parcel
  add column if not exists jibun_addr_key text
  generated always as (search_key(parcel_jibun_addr(sido_nm, sigungu_nm, emd_nm, jibun))) stored;

comment on column parcel.jibun_addr_key is
  '검색용 정규화 지번주소(공백 제거+소문자). 예: 서울특별시강남구역삼동823-4';

-- ── 저장 컬럼 위의 인덱스 ────────────────────────────────────────────────────
-- 부분 일치(LIKE '%…%')라 gin_trgm_ops 가 필요하다. 없으면 전수 스캔.
create index if not exists idx_building_nm_key on building using gin (nm_key gin_trgm_ops);
create index if not exists idx_parcel_road_key on parcel using gin (road_addr_key gin_trgm_ops);
create index if not exists idx_parcel_jibun_key on parcel using gin (jibun_addr_key gin_trgm_ops);

-- ── 상한: 어디까지가 "한 곳을 짚는 검색"인가 ──────────────────────────────────
-- 글자 수로 가르면 안 된다. '명동'은 2글자여도 동이 확정되지만 '강남'은 2글자에
-- 구 조각이다. 그래서 **몇 곳이 걸리는가**로 가른다. 선은 실측으로 정했다:
--
--   가장 큰 법정동   신림동 4,633필지  (전국 637개 동 중 최대, 2026-08-13 실측)
--   가장 작은 구 검색 '유성구' 11,248필지
--
-- 6,000 은 그 사이다 ⇒ **어떤 동 이름도 통과하고, 시·구 이름은 걸린다.**
--   통과: 둔산동 701 · 명동 1,420 · 역삼동 2,849 · 신림동 4,633
--   차단: 유성구 11,248 · 강남 13,529 · 대전광역시 45,150 · 서울 163,487 · 동 193,090
--
-- ⚠️ 데이터가 전국으로 늘면 동 하나의 필지 수도 늘 수 있다. 그때는 위 두 수를
--    다시 재고 이 값을 올려라(정본은 여기 한 곳뿐이다).
create or replace function search_scope_limit()
returns int
language sql
immutable
parallel safe
as $$ select 6000 $$;

comment on function search_scope_limit() is
  '검색이 "한 곳을 짚는" 것으로 인정되는 상한(곳). 가장 큰 법정동(신림동 4,633)보다 크고 '
  '가장 작은 구 단위 검색(유성구 11,248)보다 작게 잡았다 — 동 이름은 통과, 시·구 이름은 차단.';

-- ── 이 검색어가 몇 곳과 맞는가 ───────────────────────────────────────────────
-- 세기만 하는 일이라 싸다(조인·정렬이 없다). 무거운 검색은 이걸로 먼저 걸러낸다.
-- 주소(필지)와 건물이름은 세는 대상이 다르므로 **큰 쪽**으로 판정한다
--   예: '빌딩' 은 주소 매칭 0곳이지만 건물이름 15,068곳 → 큰 쪽인 15,068 로 판정.
create or replace function search_scope(q text)
returns table (too_broad boolean, match_cnt int)
language sql
stable
security definer
set search_path = public
as $$
  with pat as (
    select case when search_key(q) is null then null
                else '%' || replace(replace(replace(search_key(q), '\', '\\'),
                                    '%', '\%'), '_', '\_') || '%'
           end as p
  ),
  c as (
    select
      (select count(*) from parcel pc cross join pat
        where pat.p is not null
          and (pc.road_addr_key  like pat.p escape '\'
            or pc.jibun_addr_key like pat.p escape '\')) as addr_cnt,
      (select count(*) from building b cross join pat
        where pat.p is not null
          and b.nm_key like pat.p escape '\')             as nm_cnt
  )
  select greatest(c.addr_cnt, c.nm_cnt) > search_scope_limit(),
         least(greatest(c.addr_cnt, c.nm_cnt), 2147483647)::int
  from c;
$$;

comment on function search_scope(text) is
  '§8.1 검색어가 몇 곳과 맞는지 세어 "너무 넓은 검색"인지 알려준다. 화면은 결과가 0건일 때 '
  '이걸 불러 "찾는 게 없음"과 "너무 넓음"을 구분한다. security definer — 원본 표가 anon 에게 '
  '닫혀 있어 소유자 권한으로 대신 센다(돌려주는 것은 개수뿐이라 개인정보가 나가지 않는다).';

-- ── 검색 본체 ────────────────────────────────────────────────────────────────
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
    select
      case when esc.v is null then null else '%' || esc.v || '%' end as p,
      case when esc.v is null then null else '%' || esc.v      end as p_end,
      -- ⚠️ k 는 **이스케이프 전** 값이다. 정확일치·앞글자일치 정렬에 쓰는 값이라
      --    이스케이프하면 안 된다(옛 코드는 여기에 이스케이프된 값을 넣어, 이름에
      --    % 나 _ 가 든 건물에서 정확일치 가산점이 조용히 안 먹었다. 마지막
      --    ORDER BY 는 반대로 이스케이프 안 한 값을 써서 두 정렬이 서로 어긋났다).
      search_key(q) as k
    from (
      select case when search_key(q) is null then null
                  else replace(replace(replace(search_key(q), '\', '\\'),
                               '%', '\%'), '_', '\_')
             end as v
    ) esc
  ),
  -- ① 주소 두 칸은 **같은 표**라 한 번만 훑는다 (조인 전 단일 표의 OR 은 안전하다)
  --
  -- ⭐ `limit 상한+1` 이 범위 게이트를 겸한다. 따로 세지 않는 이유: 세는 일을 별도
  --    조회로 두면 좁은 검색어까지 표를 두 번 더 훑어 **오히려 느려진다**
  --    (실측 2026-08-13: '명동' 796ms → 2,803ms). 여기서 상한+1 에서 멈추면
  --      · 넘쳤다 = "한 곳을 짚는 검색이 아니다" → 아래에서 통째로 끊는다
  --      · 안 넘쳤다 = 여기 모인 것이 **곧 전체**다(잘린 것이 없다 = total_cnt 정확)
  --    넓은 검색어는 상한에서 바로 멈추므로 20만 건을 다 훑지 않는다.
  addr as materialized (
    select pc.pnu, pc.road_addr, pc.jibun_addr_key
      from parcel pc
      cross join pat
     where pat.p is not null
       and (pc.road_addr_key  like pat.p escape '\'
         or pc.jibun_addr_key like pat.p escape '\')
     limit search_scope_limit() + 1
  ),
  -- ⛔ 주소 가지와 이름 가지를 OR 하나로 합치지 말 것 — 이쪽은 **서로 다른 두 표**라
  --    조인 전에 한 표를 못 걸러 gin_trgm 인덱스가 통째로 무력화된다(2026-08-08 실측).
  -- ⛔ WHERE 는 **저장 컬럼**(nm_key/road_addr_key/jibun_addr_key)을 써야 한다.
  --    식으로 되돌리면 재확인 때 regexp 가 다시 돌아 3초를 넘긴다(2026-08-11e).
  nm as materialized (
    select b.bld_id, b.pnu, b.nm_key,
           building_display_nm(b.bld_nm, b.dong_nm) as bld_nm,
           pc.road_addr, pc.jibun_addr_key
      from building b
      join parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null and b.nm_key like pat.p escape '\'
     limit search_scope_limit() + 1
  ),
  gate as (
    select ((select count(*) from addr) > search_scope_limit()
         or (select count(*) from nm)   > search_scope_limit()) as broad
  ),
  hit as (
    select b.bld_id, b.pnu, b.nm_key,
           building_display_nm(b.bld_nm, b.dong_nm) as bld_nm,
           a.road_addr, a.jibun_addr_key
      from addr a
      join building b on b.pnu = a.pnu
     where not (select g.broad from gate g)
    union
    select n.bld_id, n.pnu, n.nm_key, n.bld_nm, n.road_addr, n.jibun_addr_key
      from nm n
     where not (select g.broad from gate g)
  ),
  eligible as (
    select h.*,
           count(*) over () as total_cnt,
           coalesce(h.jibun_addr_key like (select p_end from pat) escape '\', false)
             as jibun_hit
    from hit h
    -- 층 자료가 아예 없는 건물은 빈 스택이 되므로 뺀다(2026-08-13 실측: 242,631 중 239개).
    where exists (
      select 1 from building_floor f
      where f.bld_id = h.bld_id and f.floor_no is not null
    )
  ),
  top as (
    select e.*
    from eligible e
    cross join pat
    order by
      e.jibun_hit                    desc,
      (e.nm_key = pat.k)             desc nulls last,
      (e.nm_key like pat.k || '%')   desc nulls last,
      (e.bld_nm is null)             asc,
      length(e.bld_nm)               asc nulls last,
      e.road_addr                    asc nulls last,
      e.bld_id
    limit greatest(1, least(coalesce(lim, 25), 100))
  )
  -- ② 지번주소 조립은 여기서 처음 한다 — 25행에만 필요하다.
  --    pnu 는 parcel 의 기본키라 되짚어도 같은 한 행이다(값이 달라지지 않는다).
  select
    t.bld_id, t.pnu, t.bld_nm, t.road_addr,
    parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun) as jibun_addr,
    (select count(*)::int from building b2 where b2.pnu = t.pnu) as bld_cnt_in_pnu,
    fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof,
    t.total_cnt
  from top t
  join parcel pc on pc.pnu = t.pnu
  join lateral (
    select
      count(*)::int                                    as floor_cnt,
      min(s.floor_no) filter (where s.floor_no <> 99)  as min_floor,
      max(s.floor_no) filter (where s.floor_no <> 99)  as max_floor,
      coalesce(bool_or(s.floor_no = 99), false)        as has_roof
    from v_building_floor_stack s
    where s.bld_id = t.bld_id
  ) fs on true
  order by
    t.jibun_hit                     desc,
    (t.nm_key = search_key(q))      desc nulls last,
    (t.nm_key like search_key(q) || '%') desc nulls last,
    (t.bld_nm is null)              asc,
    length(t.bld_nm)                asc nulls last,
    t.road_addr                     asc nulls last,
    t.bld_id;
$$;

comment on function search_buildings(text, int) is
  '§8.1 건물 검색. 건물 1개 = 1행이며 total_cnt로 정확한 전체 건수를 함께 준다. '
  'security definer — 원본 표가 anon에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '입력의 % _ \ 는 서버가 리터럴로 이스케이프하고, 빈 검색어는 0건으로 잘라낸다. '
  '이름은 building_display_nm() 하나만 본다(동명칭 폴백 + 개인 성명 가림) — 보이는 것 = 검색되는 것. '
  '너무 넓은 검색(search_scope_limit() 초과)은 무거운 일을 하기 전에 0건으로 끊는다 — 상권분석은 '
  '건물 한 채 단위라 "서울" 같은 검색은 결과 25개를 보여줘도 의미가 없다(2026-08-13). '
  '⛔ 주소 가지와 이름 가지를 OR로 합치지 말 것 — 두 조인 테이블에 걸친 OR은 gin_trgm 인덱스를 무력화한다';

-- 상한 함수는 내부용이다. 화면은 search_scope() 가 돌려주는 판정만 쓴다.
revoke all on function search_scope_limit() from public, anon, authenticated;
grant execute on function search_scope(text) to anon, authenticated;

-- =====================================================================
-- 공개 접근 정책 — RLS + 최소 권한 (2026-08-08 추가)
-- =====================================================================
-- ⚠️ 이 절이 없으면 이 파일로 만든 DB는 무방비다. 2026-08-08에 일회용 Supabase
--    Postgres 컨테이너로 실증했다 — 이 절 이전의 schema.sql만 적용한 DB에서
--    공개키 롤(anon)이 원본 표를 읽고, INSERT하고, building_floor를 통째로
--    DELETE하는 데까지 성공했다.
--
-- 왜 여기 없었나: Supabase 공식 문서상 SQL Editor로 만든 표는 RLS가 자동으로
--    켜지지 않는다("If you create one in raw SQL or with the SQL Editor,
--    remember to enable RLS yourself"). 라이브 DB는 누군가 손으로 켜 둔 상태였고
--    그 사실이 코드 어디에도 없었다 = 재현 불가능한 보안.
--
-- 설계 선택: 뷰를 security_invoker=true로 바꿔 원본 표에 읽기 정책을 다는 길도
--    있으나, 그러면 unit_business(상호명)·transaction(실거래)이 anon에게 통째로
--    열린다. 상호명 노출은 CLAUDE.md에서 변호사 검토 대상이므로 노출면을 최소로
--    유지한다 — 원본 표는 닫고, 화면이 읽는 뷰 하나만 연다.

alter table bjd_code         enable row level security;
alter table parcel           enable row level security;
alter table building         enable row level security;
alter table building_floor   enable row level security;
alter table unit             enable row level security;
alter table unit_business    enable row level security;
alter table transaction      enable row level security;
alter table district         enable row level security;
alter table rent_stat        enable row level security;
alter table collect_progress enable row level security;
alter table api_quota_log    enable row level security;

-- 정책은 일부러 하나도 만들지 않는다. RLS 켬 + 정책 0개 = 공개 롤에게 원본 표는
-- 완전히 안 보인다. 수집·적재 스크립트는 service_role 키를 쓰고, service_role은
-- RLS를 우회하므로 영향이 없다(2026-08-08 컨테이너 실측: 읽기·쓰기 정상).

-- 이중 잠금 — Supabase는 public 스키마 표에 anon/authenticated 권한을 기본으로
-- 준다. RLS만으로도 막히지만, 나중에 정책 하나를 잘못 달면 그 순간 열린다.
-- 권한 자체를 회수해 두면 실수 하나로는 안 뚫린다.
-- (PostGIS 시스템 객체 관련 WARNING 몇 줄이 나오는 것은 정상 — 아래 주석 참조)
revoke all on all tables in schema public from anon, authenticated;

-- 화면이 실제로 읽는 뷰 하나만 연다(src/lib/supabase.ts의 FLOOR_STACK_VIEW).
-- authenticated에도 주는 이유: 지금은 로그인이 없지만 나중에 붙였을 때 화면이
-- 조용히 빈 목록으로 바뀌는 사고를 막는다. 둘 다 읽기 전용이다.
grant select on v_floor_stack to anon, authenticated;
-- 각주 숫자용 집계 뷰(집계값 4개뿐 — 상호명·좌표 없음).
grant select on v_coverage_stats to anon, authenticated;

-- 검색 함수도 명시적으로만 연다. Postgres는 새 함수의 EXECUTE를 PUBLIC에게 기본
-- 부여하므로 **먼저 회수하고** 정확히 필요한 롤에만 준다.
revoke all on function search_buildings(text, int) from public;
grant execute on function search_buildings(text, int) to anon, authenticated;

-- 뷰가 RLS를 우회하는 것이 사고가 아니라 선택임을 코드에 남긴다(기본값이지만 명시).
alter view v_floor_stack           set (security_invoker = false);
alter view v_building_floor_stack  set (security_invoker = false);
alter view v_unit_current          set (security_invoker = false);
alter view v_coverage_stats        set (security_invoker = false);

-- ⚠️ 위 revoke는 **표만** 다룬다 — 함수(RPC)는 별개다.
--    Postgres는 새로 만든 함수에 EXECUTE를 PUBLIC에게 기본으로 준다. 즉 우리가 public
--    스키마에 함수를 하나 만들면 그 순간 anon이 REST `/rpc/<이름>`으로 부를 수 있다.
--    **새 함수를 만들 때는 노출 여부를 의식적으로 정할 것**(화면이 쓸 함수면 그대로 두고,
--    아니면 `revoke execute on function ... from anon, authenticated`).
--    지금 우리가 만든 함수는 0개다(노출된 256개는 전부 PostGIS·pg_trgm 것).

-- ⚠️ 남은 구멍 — PostGIS 시스템 표 (우리 권한으로는 못 막는다, 2026-08-08 실측)
--    spatial_ref_sys / geometry_columns / geography_columns는 소유자가
--    supabase_admin이라 postgres 롤의 revoke가 WARNING만 내고 실패한다
--    (postgres는 슈퍼유저가 아니고 set role supabase_admin도 거부된다).
--    라이브 실측: anon이 spatial_ref_sys에 INSERT 권한(HTTP 409 중복키로 확인)과
--    DELETE 권한(HTTP 204로 확인)을 가진다. parcel.geom은 12,274행 전부 채워져
--    있어 PostGIS를 실사용 중이므로 좌표계표가 지워지면 좌표 변환이 깨진다.
--    원인: PostGIS가 extensions가 아니라 public 스키마에 설치돼 REST에 노출됨.
--    (Supabase 공식 권장 = extensions 스키마 설치)
--    해결 후보 — 공개 배포 전 결정 필요:
--      (A) 공개용 뷰만 별도 스키마(api)에 두고 PostgREST 노출 스키마를 그쪽으로
--          변경 → public 자체가 REST에서 사라진다. 단 service_role로 public 표에
--          REST 쓰기를 하는 수집·적재기의 경로를 함께 조정해야 한다.
--      (B) Supabase 지원팀에 권한 회수 요청.
--    지금 당장 급하지 않은 이유: 앱이 아직 배포 전이라 anon 키가 공개되지 않았다.

-- =====================================================================
-- 완료
-- =====================================================================
-- 다음 단계:
--   1) 법정동코드 적재
--   2) 상권정보 분기 파일 → unit_business + parcel/building/unit
--   3) 조인 성공률 측정 (90% 미만이면 정규화 로직 재점검)
-- =====================================================================
