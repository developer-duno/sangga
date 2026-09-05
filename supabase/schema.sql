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
-- 앞으로 만들 **함수**는 PUBLIC 에게 열린 채 태어나지 않는다 (2026-09-01b)
-- =====================================================================
-- ⛔ **이 줄이 여기(첫 `create function` 앞)에 있어야 하는 이유** — 2026-09-01 2차
--    적대검증에서 잡혔다. 원래는 권한 절(파일 2/3 지점)에 있었는데, 기본권한은
--    "**앞으로** 만드는 것"에만 걸리므로 **그 줄 위에서 만들어지는 함수 16개는 여전히
--    PUBLIC 에게 열린 채 태어났다.** 지금 라이브에 PUBLIC EXECUTE 가 남아 있는 9개가
--    정확히 그 16개 안에 있다 — 즉 정본만으로 새 창고를 세우면 **같은 누출이 그대로
--    재현**됐다. 시험(test_api_schema_migration.py)이 이 줄의 **위치**까지 지킨다.
--
-- ⛔ **`in schema` 를 붙이지 말 것.** 붙이면 공식 문서가 말하는 '효과 없음'이 된다:
--      "This command has no effect, unless it is undoing a matching GRANT:
--       ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;"
--    스키마별 기본권한은 전역 기본값에 **더하기만** 할 뿐 빼지 못한다. PostgreSQL 내장
--    기본값이 새 함수에 PUBLIC EXECUTE 를 주므로(공식 문서 §5.8 표 5.2), `anon`·
--    `authenticated` 만 회수해 온 지금까지의 줄들은 **PUBLIC 을 한 번도 못 막았다.**
--
-- ⚠️ 전역이라 **postgres 가 만드는 함수 전부**에 걸린다(public·api 뿐 아니라 어느 스키마든).
--    · 기존 객체는 한 개도 안 바뀐다 — 기본권한은 "앞으로"에만 적용된다.
--    · 다른 롤(supabase_admin 등)이 만드는 것에는 안 걸린다 — 그물이지 대체재가 아니라,
--      **만든 자리 `revoke` 관습은 그대로 유지**한다.
--    · ⚠️ **확장(extension)도 함수다.** 앞으로 postgres 로 `create extension` 이나
--      `alter extension … update` 를 돌리면 그 확장 함수들이 PUBLIC 실행 불가로 태어난다
--      (이 DB 의 pgcrypto·uuid-ossp·pg_stat_statements 49개가 postgres 소유다).
--      그때는 그 확장에 대해 필요한 롤에 개별 `grant execute` 를 준다.
--      ⓘ 현재 실피해 0 — 컬럼 기본값에서 uuid/crypt 를 쓰는 자리가 0행이고, anon 은
--        표에 직접 못 닿는다.
--
-- 되돌리기 한 줄: `alter default privileges grant execute on functions to public;`
alter default privileges revoke execute on functions from public;

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

comment on column building.total_area_m2 is
  '연면적 ㎡. 원본에 오기입이 섞여 있다 '
  '(2026-08-24 라이브 실측: 24만 동 중 100만㎡ 초과 6동, 그 급에서만 오기입 확률이 높다). '
  '화면은 100만㎡ 초과를 미상 처리한다(FloorStack MAX_TOTAL_AREA_M2) — 걸리는 수가 눈에 띄게 '
  '늘면 상한이 아니라 원본 적재를 의심할 것. 미기재는 0으로 온다(0 = 미상, 같은 날 실측 1,204동).';

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

-- ── 표시명 저장 컬럼 (2026-08-13) ───────────────────────────────────────────
-- 뷰가 위 함수를 **직접 부르면 그 함수를 anon 에게 열어 둘 수밖에 없다** — 뷰 안에서
-- 부르는 함수의 실행 권한은 뷰 소유자가 아니라 **접속한 롤**로 검사되기 때문이다.
-- 실제로 2026-08-10 에 함수를 닫자 층별 스택 화면이 401 로 죽어 되돌려야 했다.
-- 그래서 값을 미리 계산해 컬럼에 담고, 뷰는 컬럼만 읽는다 => 함수를 닫아도 화면이 산다.
-- (덤으로 뷰가 행마다 정규식을 두 번씩 돌리지 않는다.)
--
-- 검색 함수(search_buildings)는 security definer 라 소유자 권한으로 돌므로 함수를 그대로
-- 불러도 된다 — 그래서 거기까지 바꾸지는 않았다(고칠 이유가 없는 곳은 안 건드린다).
--
-- ⚠️ 테이블 정의부가 아니라 여기 있는 이유: 이 컬럼이 쓰는 함수가 바로 위에서 정의된다.
-- ⚠️ generated ... stored 는 IMMUTABLE 함수만 쓸 수 있다 — 위 두 함수 다 IMMUTABLE 이다.
alter table building
  add column if not exists display_nm text
  generated always as (building_display_nm(bld_nm, dong_nm)) stored;

comment on column building.display_nm is
  '화면에 보일 건물 이름 = building_display_nm(bld_nm, dong_nm) 을 미리 계산해 둔 값. '
  '뷰가 함수를 직접 부르면 그 함수를 anon 에게 열어야 하므로, 값을 컬럼에 담아 함수를 닫는다(2026-08-13). '
  '라이브 실측: 242,631행 전부에서 함수 결과와 0건 차이.';

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
-- ⚠️ 옛 `idx_ub_pnu (pnu, snapshot_ym)` 자리다(2026-08-22c 에서 지웠다). 앞 두 칸이 같고
--    업종 네 칸이 include 로 더 붙어 있어 **완전한 대체**다 — 옛것을 되살리면 105MB 를
--    그냥 두 번 쓰게 된다(2026-08-22a 가 idx_ub_snapshot_floor 에 한 정리와 같다).
-- ⛔ include 네 칸을 지우지 말 것. 반경 업종 집계가 이 칸들 때문에 힙에 안 간다.
--    최악 표본(중구 `1114013400101890026` — 이웃 1,414필지·점포 4,433곳)에서 **찬 캐시**
--    2,383ms → 적용 직후 `list_industry_mix()` 전체 **44.5ms**(반경 집계만 14.7ms ·
--    **Heap Fetches 0** · Index Only Scan, 2026-08-22 라이브 실측).
--    ⚠️ 더운 캐시로는 차이가 안 보인다(옛 인덱스로도 23ms) — 지키는 것은 **첫 방문자**다.
--    지워도 **에러는 안 나고 느려지기만 한다** — 가장 늦게 발견되는 종류의 회귀다.
-- ⓘ 이 파일에서는 문장 순서가 상관없다. 마이그레이션(2026-08-22c)에서는 옛 idx_ub_pnu 를
--    지우는 문장을 **맨 끝**에 둔다 — drop index 의 ACCESS EXCLUSIVE 락이 커밋까지 유지돼
--    앞에 두면 물질화뷰 굽는 27초 내내 unit_business 읽기가 줄을 서기 때문이다.
create index if not exists idx_ub_pnu_cat  on unit_business (pnu, snapshot_ym)
  include (cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm);
create index if not exists idx_ub_name     on unit_business using gin (biz_name gin_trgm_ops);
create index if not exists idx_ub_cat      on unit_business (cat_s_cd, snapshot_ym);
create index if not exists idx_ub_geom     on unit_business using gist (geom);
-- 각주 집계(v_coverage_stats) 전용 **커버링** 인덱스 — 뷰가 쓰는 세 컬럼이 다 들어
-- 있어 힙에 안 간다(Index Only Scan). 없으면 pkey(snapshot_ym, biz_no)로 인덱스는
-- 타지만 행마다 힙 페이지를 한 번씩 방문해(최신 스냅샷 63.5만 행 = 버퍼 63.6만 회)
-- **캐시가 식은 첫 요청만 3초 제한을 넘겨 500**이 된다. 따뜻하면 200이라 재현이
-- 어렵다. 실측(2026-08-11f): 버퍼 636,527 → 698, 힙 방문 0, 1,028ms → 131ms, 8.6MB.
-- ⚠️ pnu 가 세 번째로 들어간 이유(2026-08-22a): 집계가 "서비스 지역만" 세게 되면서
--    where 절이 pnu 를 읽는다. 빼면 그 순간 위 500 이 그대로 재발한다.
--    (옛 2-컬럼 인덱스는 이것의 앞부분이라 중복 — 2026-08-22a 에서 지웠다.)
-- ℹ️ 2026-08-22d 부터 이 집계를 미리 계산해 두므로(mv_coverage_stats) 이 인덱스가
--    받쳐 주는 것은 **화면 요청이 아니라 post_load 의 갱신**이다. 여전히 필요하다 —
--    빠지면 갱신이 277만 행의 힙을 되짚어 적재 마무리가 길어진다.
create index if not exists idx_ub_snapshot_floor_pnu on unit_business (snapshot_ym, floor_no, pnu);


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
-- 사다리 L6(같은 법정동 = PNU 앞 10자리) 전용 **표현식** 인덱스 (2026-08-22b).
-- L6 조건은 `substr(t.pnu,1,10) = …` 라 위 idx_tx_pnu 로는 못 탄다(인덱스는 pnu 원본
-- 순서인데 조건은 자른 값이다). 성적표 §1 기준 채택의 53%가 L6 이고 이 조회는
-- **층 수 × 호출**만큼 도니, 거래가 쌓일수록 그대로 느려진다.
-- 부분 조건을 idx_tx_pnu 와 같게 맞춘 이유: substr(NULL) 은 어차피 `=` 로 안 걸린다
-- (뜻은 같고 인덱스만 작아진다 — 실거래에는 PNU 없는 행이 많다).
create index if not exists idx_tx_pnu10_ym on transaction (substr(pnu, 1, 10), contract_ym) where pnu is not null;
create index if not exists idx_tx_region on transaction (sigungu_code, contract_ym);
create index if not exists idx_tx_floor  on transaction (sigungu_code, floor_no, contract_ym);

-- =====================================================================
-- L4. district — 상권 (사전계산 대상 ★ 엔진 패턴)
-- =====================================================================
-- 전국 수천 개 규모. 미분양 엔진과 같은 크기라 지표 전부 사전계산 가능.
create table if not exists district (
  district_id     text primary key,
  district_nm     text,
  -- 소스(서울 상권분석서비스)가 쓰는 4종을 **그대로** 넣는다:
  --   골목상권 / 발달상권 / 전통시장 / 관광특구   (2026-08-14 적재 실측 1,650개)
  -- 예전 주석은 '역세권/근린/대학가/오피스/관광' 이었는데, 자료를 보기 전에 적어 둔
  -- 추측이었다. 억지로 매핑하면 '전통시장' 처럼 갈 곳 없는 종류가 생겨 정보가 날아간다.
  district_type   text,
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

-- ── 출처 컬럼 (2026-08-14) ──────────────────────────────────────────────────
-- ⚠️ 테이블 정의부 안이 아니라 여기 있는 이유: 마이그레이션과 **같은 문장**이라야
--    정본↔마이그레이션 대조가 눈으로도, 드리프트 가드(tests/test_schema_migration_sync.py)
--    로도 된다. 가드는 `add column <이름>` 형태만 알아본다.
alter table district
  add column if not exists source_nm text;

-- 출처 없는 행이 생기는 순간 화면의 출처 줄이 **소리 없이** 사라진다(공공누리 1유형은
-- 출처표시가 의무다). 에러가 아니라 "한 줄이 안 보일" 뿐이라 아무도 눈치채지 못하므로
-- DB 가 막게 한다. 쓰는 경로는 적재기 둘뿐이고 둘 다 값을 담는다(2026-08-14 실측).
alter table district
  alter column source_nm set not null;

comment on column district.metrics is '정규화 점수. 화면 순위용';
comment on column district.raw_metrics is '원본값. 주석에 출처·기준시점과 함께 노출';
comment on column district.source_nm is
  '이 상권 경계를 어디서 받았나 — **화면에 그대로 보여줄 문구**로 넣는다 '
  '(공공누리 1유형은 출처표시가 의무라 화면에서 지울 수 없다). '
  '소스가 둘 이상이 된 순간(서울시 + 소상공인시장진흥공단) 화면에 박아 둔 고정 문구는 '
  '거짓말이 되므로, 문구를 코드가 아니라 자료가 들고 있게 한다.';

create index if not exists idx_district_geom on district using gist (geom);
create index if not exists idx_district_type on district (district_type);

-- ── district_rone_map — 상권 ↔ 부동산원 임대통계 이름 잇기 (2026-08-14) ────────
-- 상가 임대료 실거래는 존재하지 않으므로(절대 규칙 5) rent_stat 으로 역산하는 것이
-- 유일한 경로인데, 두 자료가 상권을 부르는 이름이 서로 다르다. 그 대응을 사람이 한 번
-- 정해 두는 표다.
--
-- 왜 region_code 가 아니라 **이름 경로**인가: rent_stat 의 키는
-- (quarter, region_code, bld_type) 인데 **같은 상권 이름이 bld_type 4종마다 다른
-- region_code** 를 갖는다(대전은 이름 12개 vs 코드 28개, 2026-08-14 실측). 코드 하나를
-- 박으면 그 종류의 통계만 읽히고 나머지 3종이 조용히 사라진다.
--
-- 왜 미매핑 상권에는 **행이 아예 없나**: "모른다"를 NULL·빈 값으로 적으면 조인이 조용히
-- 성립해 엉뚱한 상권의 임대료가 붙는다. 행이 없으면 조인이 안 되고 화면은 상위 근사
-- (권역)나 "표본 없음"으로 자연히 내려간다. 없는 매핑을 지어내지 않는 것이 안전장치다.
--
-- ★ PK 가 (district_id, rone_region_nm) 복합인 이유 — 한 상권이 경로 **둘**일 수 있다.
-- 부동산원이 통계 종류(bld_type)마다 서울 권역을 다르게 나눈다(라이브 실측 2026-08-14):
--   · 오피스                 → 서울>여의도마포>{공덕역·당산역·여의도} · 서울>기타>홍대/합정
--   · 소규모·중대형·집합상가 → 서울>영등포신촌>{공덕역·당산역·여의도·홍대/합정}
-- 하나만 고르면 나머지 종류의 통계가 통째로 사라진다. 조회가 (이름 경로, bld_type)으로
-- rent_stat 을 찾을 때 존재하는 쪽이 자연히 골라지므로 bld_type 칸은 두지 않는다.
create table if not exists district_rone_map (
  district_id     text not null references district(district_id),
  rone_region_nm  text not null,          -- rent_stat.region_nm 전체 경로 ("대전>둔산")
  match_method    text not null,          -- 'exact' | 'normalized' | 'token' | 'manual'
  note            text,
  created_at      timestamptz default now(),
  primary key (district_id, rone_region_nm)
);

comment on table district_rone_map is
  'district(상권 경계) → rent_stat(부동산원 임대동향) 상권 이름 잇기. '
  'R-ONE 상권 하나에 district 여럿이 붙고, district 하나도 경로를 **둘까지** 가질 수 있다 '
  '(PK 가 복합인 이유). 부동산원이 bld_type 마다 서울 권역 분할을 달리해 같은 상권이 '
  '오피스는 여의도마포·기타, 상가는 영등포신촌으로 갈리기 때문이다 — 라이브 실측 2026-08-14, '
  '이중 경로 잎 = 공덕역·당산역·여의도·홍대/합정. '
  '⚠️ 이 표에 **없는** district 는 "아직 이을 근거가 없다"는 뜻이며, 그 상태가 정상이다 — '
  '없는 매핑을 지어내면 임대료 추정이 통째로 틀어진다(내부용 표, 화면에 직접 안 나간다).';

comment on column district_rone_map.rone_region_nm is
  'rent_stat.region_nm 의 **전체 경로**를 그대로 적는다. region_code 가 아닌 이유: '
  '같은 상권이라도 bld_type(오피스/중대형상가/소규모상가/집합상가)마다 코드가 달라 '
  '코드로 박으면 나머지 종류의 통계가 조용히 안 읽힌다(2026-08-14 실측).';

comment on column district_rone_map.match_method is
  '어떻게 이었나 — exact(이름 그대로) / normalized(꼬리 시설어를 떼고 같음) / '
  'token(앞말 겹침, 기계 판단) / manual(사람이 지리 지식으로 정함). '
  '나중에 "이 매핑을 얼마나 믿을 수 있나"를 되물을 때의 유일한 근거다.';

comment on column district_rone_map.note is
  'manual 이면 **왜 그렇게 판단했는지**를 적는다(예: 동춘당이 송촌동 소재). '
  '근거 없는 manual 은 다음 사람이 검증할 수 없다.';

-- 역방향 조회용: "이 R-ONE 상권에 붙은 district 가 몇 개인가"(1:N 의 N 쪽).
create index if not exists idx_district_rone_map_region
  on district_rone_map (rone_region_nm);

-- ⛔ 만든 자리에서 바로 닫는다. 아래쪽 `revoke ... on all tables` 에만 기대면 방어가
--    한 겹이고, 그 문장은 **돌리는 그 순간의 표만** 닫는 일회성이다(Supabase 는 새로
--    생기는 표를 anon 에 자동으로 연다 — pg_default_acl). 마이그레이션
--    2026-08-14c 와 **같은 문장**을 여기에도 둬 정본↔라이브가 눈으로도 대조되게 한다.
revoke all on district_rone_map from public, anon, authenticated;

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
  b.display_nm as bld_nm,   -- 함수를 부르지 않는다(위 §표시명 저장 컬럼 참조)
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
  b.display_nm as bld_nm,   -- 함수를 부르지 않는다(위 §표시명 저장 컬럼 참조)
  b.approve_date,
  b.is_jiphap,
  p.road_addr,
  p.road_contact,
  pb.bld_cnt_in_pnu,
  st.store_cnt,
  st.stores,
  -- ── 건물 스펙 4칸 (2026-08-24a · 로드맵 Wave 2 PR-B) ──────────────────────
  -- 층이 아니라 **건물 한 채**의 값이라 같은 건물의 모든 층 행에 같은 값이 실린다
  -- (화면은 head 행 하나만 읽는다). 원본을 그대로 낸다 — 0 을 NULL 로 바꾸는 것도
  -- 상한을 거는 것도 여기서 하지 않는다. 서버가 뜻을 지어내면 나중에 그 판단을 누가
  -- 어디서 했는지 못 찾는다(집계·백테스트는 원본이 필요하다).
  -- ⛔ 0 은 "0" 이 아니라 **대장 미기재**다 — 롯데월드타워가 주차 0·건폐율 0 으로
  --    들어와 있어 값으로는 둘을 못 가른다. "NULL 이 0행" 은 현재 적재분(서울·대전
  --    30개 구)의 관찰값이지 구조적 보장이 아니다(적재기는 결측을 NULL 로 쓴다 —
  --    load_building_ledger.py 의 _to_float·sum_parking). [C] 전국 적재 후 다시 셀 것.
  --    뜻풀이(0·NULL 둘 다 "미상")는 화면 한 곳에서만 한다.
  b.total_area_m2,          -- 연면적 ㎡ (0 = 미기재)
  b.far,                    -- 용적률 % (0 = 미기재)
  b.bcr,                    -- 건폐율 % (0 = 미기재, 소스 오류로 100 초과 실재)
  b.parking_cnt,            -- 주차 4종(옥내외 × 자주/기계) 합 (0 = 미기재, 일부만 적힌 대장이면 부분합)
  -- ── 2026-08-25a 가 더한 좌표 2칸 (링크로 들어온 사람의 건물 되살리기) ──────
  -- ⛔ parcel.lat/lng **칸이 아니라** geom 에서 뽑는다. 검색(search_buildings)과 상권
  --    판정(list_building_districts)이 전부 geom 을 보므로 같은 칸을 봐야 한다. 칸을
  --    섞으면 같은 건물인데 **들어온 길에 따라 마커 자리가 갈리고**, 에러가 안 나서
  --    못 찾는다("지도 마커는 상권 밖인데 글자는 상권 안") — 2026-08-14e 가 정한 규칙.
  -- ⓘ 필지 도형의 대표 좌표라 한 땅에 건물이 여럿이면 같은 자리에 찍힌다(검색도 동일).
  --    좌표 없는 필지는 NULL 이고 화면은 마커를 생략한다(0,0 으로 채우지 않는다).
  st_y(p.geom)::double precision as lat,
  st_x(p.geom)::double precision as lng
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
  '⚠️ total_area_m2·far·bcr·parking_cnt 는 **건물 한 채**의 값이라 층마다 되풀이된다. '
  '0 은 "0" 이 아니라 "대장 미기재"다(NULL 은 현재 적재분 30개 구에서 0행 — 관찰값이지 보장이 아니다. '
  '적재기는 결측을 NULL 로 쓴다: load_building_ledger.py 의 _to_float·sum_parking. 전국 적재 후 다시 셀 것). '
  'bcr 은 소스 오류로 100 을 넘는 행이 있고, parking_cnt 는 주차 4종(옥내외 × 자주/기계) 합이라 '
  '일부만 적힌 대장이면 부분합이다 — 뜻풀이·상한은 화면이 한 곳에서 한다(2026-08-24a). '
  '⚠️ lat·lng 는 **parcel.geom 에서 뽑은** 필지 대표 좌표다(2026-08-25a). parcel 에 있는 lat/lng '
  '칸과는 다른 칸이며, 그 칸을 쓰면 검색·상권판정과 자리가 갈린다(2026-08-14e 규칙). '
  '한 땅에 건물이 여럿이면 같은 자리에 찍힌다 — 검색도 같은 한계다. 좌표 없는 필지는 NULL(마커 생략). '
  'ℹ️ 린트 0010(security definer view) 의도적 예외 — security_invoker=true로 되돌리면 원본 표 401 + 상호명·성명 노출 확대. '
  '재검토 방아쇠: 공개 배포일 / 지도·반경 검색(§6.4) 착수일';

-- =====================================================================
-- 함수: list_building_districts — 이 건물이 속한 상권 (§8.6 한 줄)
-- =====================================================================
-- district 표는 2026-08-14 에 서울 1,650개로 찼는데(결정 0008) **읽는 코드가 0줄**이었다.
-- 층별 스택 화면의 "속한 상권" 한 줄이 이 함수 하나만 부른다.
--
-- ## 왜 `covered` 를 표에서 직접 세나
--
-- 화면에 "서울만 상권 자료가 있다"고 적어 두면, 대전·부산 상권을 넣는 날 표만 늘고
-- **화면 문구는 낡은 채 남는다**(코드를 한 줄도 안 고쳤는데 거짓말이 시작되는 결함).
-- 결정 0006/0009 의 list_open_sigungu() 와 같은 결로, "그 건물의 시·도에 상권 자료가
-- 실제로 있는가"를 district 표에 직접 물어본다 — 자료가 늘면 화면이 저절로 따라온다.
--
-- ⚠️ `covered=false`("아직 자료가 없는 지역")와 `districts=[]`("자료는 있는데 어느
--    경계에도 안 들어감")는 **다른 상태**다. 화면이 둘을 다르게 말해야 한다.
--
-- ## 왜 겹치면 전부 나열하나
--
-- 한 건물이 상권 여러 개에 걸치는 일이 실제로 있다(결정 0008 검증 때 3,342동). 하나만
-- 골라 보여주면 그 고르는 규칙이 곧 숨은 판단이 된다 — 사장님 결정은 **전부 나열**이다.
-- 정렬은 면적 오름차순(좁은 상권이 더 구체적인 설명이라 먼저) + district_id 로 안정화.
--
-- ## 왜 st_contains 인가
--
-- 결정 0008 의 실측(68.5% / 31.5%)이 바로 이 술어로 나온 숫자다. 술어를 바꾸면
-- (st_intersects·st_dwithin 등) 화면이 그 실측과 어긋난 말을 하게 된다.
--
-- ## 왜 본문에서 함수명으로 한정하나
--
-- 파라미터 이름 bld_id 가 building.bld_id 컬럼과 겹친다. 그냥 `bld_id` 라고 쓰면
-- PostgreSQL 이 컬럼을 우선 집어 `where b.bld_id = b.bld_id`(항상 참 = 전 건물)가 된다.
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

-- =====================================================================
-- 검색 전용 요약표 — 찾힐 수 있는 필지만 (2026-08-13d)
-- =====================================================================
-- 전국 시드로 parcel 이 1,119,149행이 됐지만 건물은 서울·대전 242,631동뿐이다.
-- 늘어난 93만 필지는 **검색 결과가 될 수 없는데도**(건물이 없어 조인에서 탈락)
-- 검색할 때마다 훑혔다 — 2글자 검색어는 trigram 이 못 걸러 표를 통째로 훑기 때문이다.
-- 실측(2026-08-13): '명동' 1,725ms -> 500. 게다가 범위 판정이 건물 없는 필지까지
-- 세어 '명동'(전국 필지 약 10,036 > 상한 6,000)을 **막아 버렸다.**
--
-- 필터로는 안 고쳐진다(EXISTS 4,620ms / 건물에서 출발 2,401ms / 열린 지역만 1,417ms).
-- 비용이 "무엇을 거르나"가 아니라 **"몇 행을 훑나"로 정해지기 때문**이다.
-- => 훑을 표 자체를 작게 만든다: 188,442행(42MB), 같은 스캔 **109ms**(15.8배).
--    ⚠️ 옛 주석의 '25MB'는 인덱스 없는 임시표를 잰 값이었다 — 실제는 42MB(총 63MB).
--
-- ⚠️ **자료를 새로 넣으면 반드시 갱신할 것** (ANALYZE 와 같은 성격의 적재 후 절차):
--      refresh materialized view concurrently mv_search_parcel;
--    안 하면 새로 넣은 건물이 **조용히 검색에서 빠진다**(에러가 아니다).

create materialized view if not exists mv_search_parcel as
select
  pc.pnu,
  substr(pc.pnu, 1, 5)::char(5) as sigungu_code,   -- 검색 범위를 좁히는 칸
  pc.road_addr,
  pc.road_addr_key,
  pc.jibun_addr_key,
  pc.sido_nm,
  pc.sigungu_nm,
  pc.emd_nm,
  pc.jibun
from parcel pc
where exists (select 1 from building b where b.pnu = pc.pnu);

comment on materialized view mv_search_parcel is
  '§8.1 검색 전용 요약표 — **건물이 있는 필지만** 담는다(2026-08-13). 전국 시드로 parcel 이 '
  '112만 행이 됐지만 건물은 서울·대전 24만 동뿐이라, 나머지 93만 필지는 검색 결과가 될 수 없는데도 '
  '매번 훑혔다(명동 1,725ms → 500). 이 표는 188,442행(42MB, 인덱스 포함 63MB)이라 같은 스캔이 109ms 다. '
  'sigungu_code 는 "고른 구 안에서만 검색"(2026-08-13e)에 쓴다. '
  '⚠️ 자료를 새로 넣으면 `python scripts/post_load.py` 를 반드시 돌릴 것 — '
  '안 하면 새 건물이 조용히 검색에서 빠진다(ANALYZE 와 같은 성격의 적재 후 필수 절차).';

create unique index if not exists idx_msp_pnu        on mv_search_parcel (pnu);
create index if not exists idx_msp_road_key          on mv_search_parcel using gin (road_addr_key gin_trgm_ops);
create index if not exists idx_msp_jibun_key         on mv_search_parcel using gin (jibun_addr_key gin_trgm_ops);
-- 구로 좁히는 것이 이제 기본 경로다 — 이 인덱스가 그 길을 연다.
create index if not exists idx_msp_sigungu           on mv_search_parcel (sigungu_code);

analyze mv_search_parcel;

-- ── 2) 고를 수 있는 구 목록 ─────────────────────────────────────────────────
-- ⚠️ **자료가 실제로 있는 구만** 낸다. 목록을 코드에 박아 두면 자료가 없는 구를
--    고를 수 있게 되고, 고르면 아무것도 안 나와 "고장난 것"처럼 보인다.
--    30행짜리라 물질화해 두고 요약표와 함께 갱신한다(매 화면 로드마다 24만 행을
--    집계할 이유가 없다).
create materialized view if not exists mv_open_sigungu as
select
  substr(pc.sigungu_code, 1, 2)::char(2) as sido_code,
  max(pc.sido_nm)                        as sido_nm,
  pc.sigungu_code,
  max(pc.sigungu_nm)                     as sigungu_nm,
  count(*)::int                          as building_cnt
from mv_search_parcel pc
join building b on b.pnu = pc.pnu
group by pc.sigungu_code;

comment on materialized view mv_open_sigungu is
  '§8.1 지금 검색할 수 있는 시군구 목록(자료가 실제로 있는 곳만). 화면의 지역 고르기가 이걸 읽는다. '
  '⚠️ 목록을 프론트에 박지 말 것 — 자료 없는 구를 고르면 "고장난 것"처럼 보인다. '
  '`python scripts/post_load.py` 가 mv_search_parcel 과 함께 갱신한다.';

create unique index if not exists idx_mos_sigungu on mv_open_sigungu (sigungu_code);
analyze mv_open_sigungu;

-- =====================================================================
-- 요약표: mv_coverage_stats — 각주 집계를 **미리 계산해 둔 한 줄** (2026-08-22d)
-- =====================================================================
-- 왜 미리 계산하나: 실시간 집계는 최신 스냅샷 **277만 행마다** substr 을 잘라 열린 구
-- 목록과 대조하느라 순수 실행 **~2,100ms** 였다(2026-08-22 실측, 3회 반복).
-- 커버링 인덱스로 힙에는 안 가는데(Heap Fetches 0) 대조 자체가 남는다. anon 공개 호출의
-- statement timeout 은 3초라 그 문턱에 붙어 있었다 — 넘으면 화면은 각주를 null 로 조용히
-- 강등해 **에러 없이 각주만 사라진다.**
-- 이 값은 **적재할 때만** 바뀐다(점포 표는 분기 append-only, 열린 구 목록은 post_load 에서만
-- 갱신). 그러니 화면을 열 때마다 다시 셀 이유가 없다 — 바뀌는 순간에 한 번 세어 굳힌다.
--
-- ⛔ 화면은 이 표를 **직접 읽지 않는다.** 아래 v_coverage_stats 뷰만 anon 에게 열려 있다
--    (요약표는 공개키에 안 연다 — 2026-08-13f 정책. 회수는 파일 아래 revoke 절에 있다).
-- ⚠️ select 본문은 아래 뷰가 예전에 갖고 있던 것과 동일하다 — 범위(서비스 지역)나 분기
--    기준을 고칠 때는 supabase/migrations 의 해당 파일과 여기를 함께 고칠 것.
create materialized view if not exists mv_coverage_stats as
select
  ub.snapshot_ym,
  count(*)                                                    as store_cnt,
  count(*) filter (where ub.floor_no is null)                 as floor_missing_cnt,
  round(100.0 * count(*) filter (where ub.floor_no is null)
        / count(*), 1)                                        as floor_missing_pct
from unit_business ub
where ub.snapshot_ym = (select max(snapshot_ym) from unit_business)
  -- 서비스 지역(화면에서 고를 수 있는 구)만 센다 — 전국을 세면 화면이 보여주지도 않는
  -- 지역까지 섞여 결측률이 15.3%p 과장된다(2026-08-22 실측 50.3% vs 35.0%).
  -- 목록을 여기 베껴 적지 않고 mv_open_sigungu 를 그대로 읽는 이유: 자료가 늘 때
  -- 각주만 낡는 드리프트를 막으려고(확정설계 9 — 열린 지역의 진실은 서버 한 곳).
  -- ⚠️ `::char(5)` 로 타입을 맞춘다. substr(char) 의 결과는 text 인데 sigungu_code 는
  --    char(5) 라, 안 맞추면 비교마다 캐스트가 낀다(2026-08-16b 와 같은 병).
  -- ℹ️ pnu 가 NULL 인 행(실측 1,819)은 지역 특정 불가라 분모에서 빠진다.
  and substr(ub.pnu, 1, 5)::char(5) in (select sigungu_code from mv_open_sigungu)
group by ub.snapshot_ym;
-- group by 라 행이 있을 때만 결과가 나온다 = 0으로 나누는 경우가 없다.

comment on materialized view mv_coverage_stats is
  '§8.6 스택 뷰 각주 집계를 **미리 계산해 둔 한 줄**(2026-08-22d). 화면은 이 표를 직접 '
  '읽지 않고 v_coverage_stats 뷰를 거친다 — 표 자체는 anon 에게 닫혀 있다. '
  '왜 사전계산인가: 실시간 집계는 최신 스냅샷 277만 행마다 substr 을 잘라 열린 구 목록과 '
  '대조하느라 순수 실행 2.1~4.9초였고(2026-08-22 실측, 부하에 따라 흔들린다), anon 의 '
  '3초 제한을 넘나들었다. 집계값은 **적재 시점에만** 바뀌므로 그때 한 번 세면 된다. '
  '신선도 = python scripts/post_load.py 를 돌린 시점(적재와 한 세트다 — 그 스크립트의 '
  '--check 가 원본 최신 분기와 대조해 낡음을 잡는다). '
  '⚠️ 본문은 2026-08-22a 의 v_coverage_stats select 와 동일하다 — 범위(서비스 지역)나 '
  '분기 기준을 고칠 때는 여기와 supabase/schema.sql 을 함께 고칠 것.';

-- `refresh ... concurrently` 의 필수 조건(post_load 는 전부 concurrently 로 돈다).
-- 행이 한 줄뿐이라 조회 이득은 없다 — 순전히 자격 요건이다.
create unique index if not exists idx_mcs_snapshot_ym on mv_coverage_stats (snapshot_ym);
analyze mv_coverage_stats;

-- =====================================================================
-- 뷰: v_coverage_stats — 스택 뷰 각주용 집계
-- =====================================================================
-- 화면 각주("점포 N곳 중 층이 없는 것이 M%")의 숫자를 담는 뷰. 예전에는 이 숫자가
-- FloorStack.tsx에 문자열로 박혀 있었는데, 점포 데이터는 위 요약표의 where 절대로
-- **최신 분기를 자동으로 따라가므로** 새 분기를 적재하는 순간 코드 변경 0인 채로
-- 각주만 옛 숫자를 말하게 된다.
--
-- ⚠️ **계산은 여기서 안 한다.** 2026-08-22d 부터 미리 계산해 둔 mv_coverage_stats 한 줄을
--    그대로 내보낸다(실시간 집계는 ~2,100ms 로 anon 3초 제한에 붙어 있었다 — 위 요약표
--    주석 참조). 화면이 읽는 이름·컬럼은 그대로라 프론트는 이 변경을 모른다.
-- ⚠️ v_floor_stack과 **똑같은** 분기 기준을 쓴다("분기" = snapshot_ym 스냅샷 분기).
--    한쪽만 바꾸면 화면의 점포 목록과 각주가 서로 다른 분기를 말하게 되므로 항상 함께 고칠 것.
--    2026-08-22a 에서 **지역** 조건이 붙었지만 그 약속은 그대로다 — 바뀐 것은 "어느 지역을
--    세느냐"뿐이고 "어느 분기를 세느냐"는 손대지 않았다.
-- ⚠️ 내보내는 것은 집계값뿐이다 — 상호명·좌표·주소는 넣지 않는다(노출면 최소 원칙).
-- ⛔ **drop 하고 다시 만들지 말 것.** anon SELECT 가 같이 날아가는데
--    `scripts/post_load.py --check` 는 "열려 있으면 안 되는데 열린 것"만 잡지
--    "열려 있어야 하는데 닫힌 것"은 못 잡는다 → 경보 없이 각주만 조용히 사라진다.
create or replace view v_coverage_stats as
select * from mv_coverage_stats;

comment on view v_coverage_stats is
  '§8.6 스택 뷰 각주용 집계. **미리 계산해 둔 mv_coverage_stats 한 줄을 그대로 내보낸다** '
  '(2026-08-22d — 실시간 집계는 2.1~4.9초로 anon 3초 제한을 넘나들었다). '
  '★ 범위는 **서비스 지역(mv_open_sigungu = 화면에서 고를 수 있는 구)** 뿐이다(2026-08-22a). '
  '전국을 세면 화면이 보여주지도 않는 지역까지 섞여 결측률이 15.3%p 과장된다(50.3% vs 35.0%). '
  '분기 기준은 v_floor_stack 과 동일한 전역 최신 snapshot_ym — 둘을 항상 함께 고칠 것. '
  'ℹ️ pnu 가 NULL 인 행(실측 1,819)은 지역 특정 불가라 분모에서 빠진다. '
  'ℹ️ 신선도 = python scripts/post_load.py 시점 — 그 스크립트의 --check 가 낡음을 잡는다. '
  '★ 공개 접근: anon/authenticated에게 SELECT **만** 허용(집계값만, 상호명 없음). '
  '⛔ drop 하지 말 것 — GRANT 가 날아가는데 post_load --check 는 "닫힌 것"을 못 잡는다. '
  'ℹ️ 린트 0010(security definer view) 의도적 예외 — security_invoker=true로 되돌리면 원본 표 401. '
  '재검토 방아쇠: 공개 배포일 / 지도·반경 검색(§6.4) 착수일';

create or replace function list_open_sigungu()
returns table (sido_code char(2), sido_nm text, sigungu_code char(5), sigungu_nm text, building_cnt int)
language sql
stable
security definer
set search_path = public
as $$
  select m.sido_code, m.sido_nm, m.sigungu_code, m.sigungu_nm, m.building_cnt
  from mv_open_sigungu m
  order by m.sido_code, m.sigungu_nm;
$$;

comment on function list_open_sigungu() is
  '§8.1 화면의 지역 고르기가 부르는 목록 — 자료가 실제로 있는 시군구만. security definer '
  '(원본 표가 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. 나가는 것은 지역명·건물수뿐)';

-- ── 3) 범위 판정 — 고른 구 안에서만 센다 ────────────────────────────────────

-- ── 상한: 어디까지가 "한 곳을 짚는 검색"인가 ──────────────────────────────────
-- 글자 수로 가르면 안 된다. '명동'은 2글자여도 동이 확정되지만 '강남'은 2글자에
-- 구 조각이다. 그래서 **몇 곳이 걸리는가**로 가른다. 선은 실측으로 정했다:
--
--   가장 큰 법정동   신림동 4,537필지   ← 검색이 실제로 세는 기준(mv_search_parcel)
--   가장 작은 구 검색 '유성구' 7,159필지  ← 같은 기준
--   ⚠️ 옛 주석은 '유성구 11,248'이라 적었는데 그건 parcel×building **조인 행수**였다
--      (한 필지에 건물이 여럿이면 중복 집계). search_scope() 는 조인 없이 필지만 센다.
--
-- 6,000 은 그 사이다 ⇒ **어떤 동 이름도 통과하고, 시·구 이름은 걸린다.**
--   통과: 둔산동 701 · 명동 1,349 · 역삼동 2,819 · 신림동 4,537
--   차단: 유성구 7,159 · 강남 12,961 · 서울·동 등 시도 단위
--   ⛔ **"구 이름은 전부 차단된다"는 말은 사실이 아니다** — 30개 구 중 **13개**는
--      상한 미만이라 통과한다(가장 작은 노원구 3,479 · 금천 3,492 · 도봉 3,710).
--      이 게이트가 확실히 막는 것은 **시·도 단위**이고, 구는 큰 곳만 걸린다.
--      2026-08-13e 부터는 화면이 구를 먼저 고르므로 이 게이트는 **안전망**이다.
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
  '검색이 "한 곳을 짚는" 것으로 인정되는 상한(곳). 검색이 실제로 훑는 표(mv_search_parcel) 기준으로 '
  '가장 큰 법정동(신림동 4,537)보다 크고 가장 작은 구 단위 검색(유성구 7,159)보다 작게 잡았다. '
  '⚠️ "구 이름은 전부 차단된다"는 말은 사실이 아니다 — 30개 구 중 13개는 상한 미만이라 통과한다'
  '(노원 3,479·금천 3,492·도봉 3,710). 확실히 막는 것은 시·도 단위이고, 2026-08-13e 부터는 '
  '화면이 구를 먼저 고르므로 이 상한은 안전망이다.';

-- ── 이 검색어가 몇 곳과 맞는가 ───────────────────────────────────────────────
-- 세기만 하는 일이라 싸다(조인·정렬이 없다). 무거운 검색은 이걸로 먼저 걸러낸다.
-- 주소(필지)와 건물이름은 세는 대상이 다르므로 **큰 쪽**으로 판정한다
--   예: '빌딩' 은 주소 매칭 0곳이지만 건물이름 15,068곳 → 큰 쪽인 15,068 로 판정.
create or replace function search_scope(q text, sigungu text default null)
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
           end as p,
           nullif(btrim(coalesce(sigungu, '')), '') as gu
  ),
  c as (
    select
      (select count(*) from mv_search_parcel pc cross join pat
        where pat.p is not null
          and (pat.gu is null or pc.sigungu_code = pat.gu)
          and (pc.road_addr_key  like pat.p escape '\'
            or pc.jibun_addr_key like pat.p escape '\')) as addr_cnt,
      (select count(*) from building b
         join mv_search_parcel pc on pc.pnu = b.pnu
         cross join pat
        where pat.p is not null
          and (pat.gu is null or pc.sigungu_code = pat.gu)
          and b.nm_key like pat.p escape '\')            as nm_cnt
  )
  select greatest(c.addr_cnt, c.nm_cnt) > search_scope_limit(),
         least(greatest(c.addr_cnt, c.nm_cnt), 2147483647)::int
  from c;
$$;

comment on function search_scope(text, text) is
  '§8.1 검색어가 몇 곳과 맞는지 세어 "너무 넓은 검색"인지 알려준다. sigungu 를 주면 그 구 안에서만 센다. '
  '화면은 결과가 0건일 때 이걸 불러 "찾는 게 없음"과 "너무 넓음"을 구분한다. '
  '**찾힐 수 있는 필지(mv_search_parcel)만** 센다 — 건물 없는 필지를 세면 판정이 실제보다 넓어진다.';

-- ── 4) 검색 본체 — 고른 구 안에서만 ─────────────────────────────────────────
create or replace function search_buildings(q text, lim int default 25, sigungu text default null)
returns table (
  bld_id         text,
  pnu            char(19),
  bld_nm         text,
  road_addr      text,
  jibun_addr     text,
  -- 상권 지도의 마커 자리(2026-08-14e). **필지(parcel.geom)** 좌표라 한 땅에 여러 동이면
  -- 같은 점이고, 상권 판정(list_building_districts)과 같은 칸을 본다 — 마커와 글자가
  -- 서로 다른 칸을 보면 "지도는 상권 밖, 글자는 상권 안"이 된다.
  lat            double precision,
  lng            double precision,
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
      -- ⚠️ k 는 **이스케이프 전** 값이다(정확일치·앞글자일치 정렬에 쓴다).
      search_key(q) as k,
      esc.gu
    from (
      select case when search_key(q) is null then null
                  else replace(replace(replace(search_key(q), '\', '\\'),
                               '%', '\%'), '_', '\_')
             end as v,
             nullif(btrim(coalesce(sigungu, '')), '') as gu
    ) esc
  ),
  -- ① 주소 두 칸은 같은 표라 한 번만 훑는다. 그 표는 **검색 전용 요약표**이고,
  --    구를 골랐으면 그 구만 본다(이제 이게 기본 경로다 — idx_msp_sigungu).
  --    `limit 상한+1` 이 범위 게이트를 겸한다(구를 안 고른 경로의 안전망).
  addr as materialized (
    select pc.pnu, pc.road_addr, pc.jibun_addr_key
      from mv_search_parcel pc
      cross join pat
     where pat.p is not null
       and (pat.gu is null or pc.sigungu_code = pat.gu)
       and (pc.road_addr_key  like pat.p escape '\'
         or pc.jibun_addr_key like pat.p escape '\')
     limit search_scope_limit() + 1
  ),
  -- ⛔ 주소 가지와 이름 가지를 OR 하나로 합치지 말 것 — 서로 다른 두 표라 조인 전에
  --    한 표를 못 걸러 gin_trgm 인덱스가 통째로 무력화된다(2026-08-08 실측).
  nm as materialized (
    select b.bld_id, b.pnu, b.nm_key, b.display_nm as bld_nm,
           pc.road_addr, pc.jibun_addr_key
      from building b
      join mv_search_parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null
       and (pat.gu is null or pc.sigungu_code = pat.gu)
       and b.nm_key like pat.p escape '\'
     limit search_scope_limit() + 1
  ),
  gate as (
    select ((select count(*) from addr) > search_scope_limit()
         or (select count(*) from nm)   > search_scope_limit()) as broad
  ),
  hit as (
    select b.bld_id, b.pnu, b.nm_key, b.display_nm as bld_nm,
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
  -- ② 지번주소 조립·좌표 뽑기는 여기서 처음 한다 — 25행에만 필요하다.
  --    parcel 은 pnu 가 기본키라 이 조인은 25번의 색인 조회다(요약표에 geom 을 넣어
  --    표를 키우는 것보다 싸다 — 요약표는 188,442행이고 검색마다 통째로 훑힌다).
  select
    t.bld_id, t.pnu, t.bld_nm, t.road_addr,
    parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun) as jibun_addr,
    st_y(p.geom)::double precision as lat,
    st_x(p.geom)::double precision as lng,
    (select count(*)::int from building b2 where b2.pnu = t.pnu) as bld_cnt_in_pnu,
    fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof,
    t.total_cnt
  from top t
  join mv_search_parcel pc on pc.pnu = t.pnu
  join parcel p on p.pnu = t.pnu
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

comment on function search_buildings(text, int, text) is
  '§8.1 건물 검색. 건물 1개 = 1행이며 total_cnt로 정확한 전체 건수를 함께 준다. '
  'sigungu 를 주면 **그 구 안에서만** 찾는다(2026-08-13e, 사장님 결정) — 같은 건물 이름이 '
  '여러 구에 겹치기 때문이다(이름 33,851종 중 2,443종이 2개 이상 구에 존재). '
  'lat·lng 는 상권 지도의 마커 자리다(2026-08-14e) — **필지(parcel.geom) 좌표**라 한 땅에 '
  '여러 동이면 같은 점이고, 상권 판정(list_building_districts)과 같은 칸을 본다. '
  'security definer — 원본 표가 anon에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '입력의 % _ \ 는 서버가 리터럴로 이스케이프하고, 빈 검색어는 0건으로 잘라낸다. '
  '이름은 building.display_nm(동명칭 폴백 + 개인 성명 가림)만 본다 — 보이는 것 = 검색되는 것. '
  '주소는 mv_search_parcel(건물이 있는 필지만)을 본다. ⚠️ 자료 적재 후 `python scripts/post_load.py` 필수. '
  '⛔ 주소 가지와 이름 가지를 OR로 합치지 말 것 — 두 조인 테이블에 걸친 OR은 gin_trgm 인덱스를 무력화한다';

-- ⚠️ public 원본은 회수만 한다 — 열리는 쪽은 api.* 래퍼뿐(2026-09-05a). Postgres 는 새 함수의 EXECUTE 를 PUBLIC 에 기본 부여한다.
revoke all on function search_scope(text, text) from public;
-- 2026-09-05a: public.* 원본은 닫는다 — 화면은 api.* 래퍼만 부른다(security definer).
revoke all on function search_scope(text, text) from public, anon, authenticated;
revoke all on function search_buildings(text, int, text) from public, anon, authenticated;
revoke all on function list_open_sigungu() from public, anon, authenticated;
revoke all on function list_building_districts(text) from public, anon, authenticated;
revoke all on function search_scope_limit() from public, anon, authenticated;


-- =====================================================================
-- Stage A — 층별 화면의 실거래 "사실 표시" (2026-08-15, 결정 0012)
-- =====================================================================
-- 결정 0012 는 시세 표시를 두 단계로 갈랐고, 여기 있는 것은 **Stage A** 뿐이다 —
-- 추정이 한 톨도 없고, 신고된 거래를 그대로 보여주거나 세어서 중앙값·사분위를 낼 뿐이다.
-- (추정 밴드 = Stage B 는 백테스트 성적표가 나온 뒤 따로 결재한다.)
--
-- 왜 둘인가: 자기 실거래가 있는 필지는 **서울 1.8% · 대전 1.4%** 뿐이라(2026-08-15 실측)
-- 이력만 붙이면 98% 건물이 빈칸이다. 그래서 구 단위 분포를 함께 낸다(항상 보여줄 수 있다).
-- 왜 구인가: 실거래의 동은 **문자**(emd_nm), 건물의 법정동은 **코드**라 이름 대조가 조용히
-- 어긋난다. 구는 pnu 앞 5자리로 확정된다. 법정동은 매핑 검증 후의 경로다(결정 0012 §4).

-- ── ① 이 필지의 실거래 이력 ─────────────────────────────────────────────────
-- 202401 부터인 이유: 실거래 지번은 **2024-01 부터만 공개**된다(그 전은 100% 마스킹 —
--   알려진한계). 구간을 명시해 "이 목록이 무엇의 전부인지"를 함수가 스스로 말하게 한다.
-- 100행 상한인 이유: 한 필지에 거래가 **852건**인 곳이 실재한다(라이브 실측 2026-08-15).
-- ⚠️ 파라미터 `pnu` 가 `transaction.pnu` 와 겹친다 — 함수명으로 한정하지 않으면 컬럼이
--    이겨 `where t.pnu = t.pnu`(= 전 국토 거래)가 된다(list_building_districts 와 같은 함정).
create or replace function list_parcel_transactions(pnu text)
returns table (
  floor_no     smallint,
  contract_ym  text,
  contract_day smallint,
  bld_area_m2  numeric,
  price_won    bigint,
  unit_price   numeric,
  tx_type      text
)
language sql
stable
security definer
set search_path = public
as $$
  select t.floor_no,
         t.contract_ym::text,
         t.contract_day,
         t.bld_area_m2,
         t.price_won,
         t.unit_price,
         t.tx_type
  from transaction t
  where t.pnu = list_parcel_transactions.pnu
    and t.contract_ym >= '202401'
  -- 계약일이 없는 행(구 자료)이 최신인 척 위로 올라오면 안 된다 → nulls last.
  -- 마지막 tx_id 는 같은 날 여러 건일 때 순서가 호출마다 흔들리지 않게 하는 못이다.
  order by t.contract_ym desc, t.contract_day desc nulls last, t.tx_id
  limit 100;
$$;

comment on function list_parcel_transactions(text) is
  'Stage A(결정 0012) 이 필지의 실거래 이력 — 추정이 아니라 신고된 거래 그대로. '
  '지번이 공개된 구간(202401 이후)만 나온다: 그 전은 지번이 100% 마스킹돼 필지에 붙지 않는다. '
  '최신순 100행 상한(한 필지 852건인 곳이 실재한다). 없는 pnu 는 빈 결과(에러가 아니다). '
  'security definer — transaction 이 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 층·계약시점·면적·금액·단가·거래유형뿐(상호명·개인정보 없음)';

-- ── ② 구 × 층대 단가 분포 (사전계산) ────────────────────────────────────────
-- 왜 집합만: 통건물(일반)은 지번이 100% 마스킹되고 건물 한 채 값이라 ㎡당 단가의 성격이
--   다르다. 섞으면 분포가 오염된다.
-- 왜 window_from 을 굳혀 두나: 물질화뷰는 갱신 시점에 계산돼 그대로 굳는다. 화면이
--   "최근 24개월"이라고만 적으면 갱신을 미룬 날 그 문구만 조용히 거짓말이 된다.
--   시각은 KST 고정 — now() 는 UTC 라 월말·월초에 한 달이 어긋난다(timezone 룰).
-- 왜 unit_price 가 있는 행만 세나: n 은 화면에 "표본 N건"으로 나가고 중앙값은 unit_price
--   로 낸다. 단가가 없는 행을 n 에 세면 근거로 쓴 것보다 표본이 많다고 말하게 된다.
-- ⚠️ '지하'는 지금 **항상 0건**이다 — 2017년부터 국토부가 상업업무용 실거래의 floor 를
--    빈 값으로 준다(알려진한계). 지하는 '층미상'에 흡수돼 있다. 칸을 남겨 두는 이유는
--    자료가 돌아오는 날 화면이 저절로 따라오게 하기 위해서다.
-- ⚠️ 옥탑(99)은 '3층이상'에 들어간다(결정 0012 의 층대 정의가 ">=3").
create materialized view if not exists mv_sigungu_tx_stats as
with win as (
  select to_char((now() at time zone 'Asia/Seoul') - interval '24 months', 'YYYYMM') as from_ym
)
select
  t.sigungu_code,
  case
    when t.floor_no is null then '층미상'
    when t.floor_no < 0    then '지하'
    when t.floor_no = 1    then '1층'
    when t.floor_no = 2    then '2층'
    else                        '3층이상'
  end                                                              as floor_band,
  min(w.from_ym)                                                   as window_from,
  count(*)::int                                                    as n,
  percentile_cont(0.5)  within group (order by t.unit_price)       as median_unit_price,
  percentile_cont(0.25) within group (order by t.unit_price)       as p25_unit_price,
  percentile_cont(0.75) within group (order by t.unit_price)       as p75_unit_price
from transaction t
cross join win w
where t.tx_type = '집합'
  and t.unit_price is not null
  and t.contract_ym >= w.from_ym
group by t.sigungu_code, 2;

comment on materialized view mv_sigungu_tx_stats is
  'Stage A(결정 0012) 구×층대 실거래 단가 분포 — 집합(구분소유) 거래만, 갱신 시점 기준 24개월. '
  'window_from 은 그 창의 시작 달을 굳혀 둔 것이다(화면이 "최근 24개월"만 적으면 갱신을 미룬 날 '
  '그 문구가 조용히 거짓말이 된다). n 은 단가를 낼 수 있었던 행 수 = 중앙값의 실제 근거 수다. '
  '⚠️ 자료를 새로 넣으면 `python scripts/post_load.py` 로 갱신할 것. '
  '⛔ anon 에게 열지 않는다 — 화면은 get_sigungu_tx_stats() 로만 읽는다.';

-- `concurrently` 갱신의 전제 조건(없으면 갱신 중 이 표를 읽는 화면이 통째로 잠긴다).
create unique index if not exists idx_msts_key on mv_sigungu_tx_stats (sigungu_code, floor_band);

analyze mv_sigungu_tx_stats;

-- 층대 5칸을 **항상 같은 순서로** 내보낸다. 표본 0 인 층대는 물질화뷰에 행 자체가 없어,
-- 그대로 내면 그 칸이 화면에서 사라져 "지하는 아예 안 판다"처럼 읽힌다.
-- 구 이름도 서버가 준다 — 화면에 지역명을 글자로 박으면 자료가 늘 때 화면만 낡는다
-- (list_open_sigungu·list_building_districts 와 같은 원칙).
create or replace function get_sigungu_tx_stats(sigungu text)
returns table (
  floor_band        text,
  n                 int,
  median_unit_price numeric,
  p25_unit_price    numeric,
  p75_unit_price    numeric,
  window_from       text,
  sigungu_nm        text
)
language sql
stable
security definer
set search_path = public
as $$
  select b.band,
         coalesce(s.n, 0),
         s.median_unit_price,
         s.p25_unit_price,
         s.p75_unit_price,
         -- 창은 갱신할 때 한 번 정해져 표 전체가 같은 값을 가진다. 그 구에 거래가
         -- 한 건도 없어도 "언제부터 세었는지"는 말할 수 있어야 하므로 전체에서 읽는다.
         (select max(m.window_from) from mv_sigungu_tx_stats m),
         (select o.sigungu_nm from mv_open_sigungu o
           where o.sigungu_code = get_sigungu_tx_stats.sigungu)
  from (values ('지하', 1), ('1층', 2), ('2층', 3), ('3층이상', 4), ('층미상', 5)) as b(band, ord)
  left join mv_sigungu_tx_stats s
    on s.sigungu_code = get_sigungu_tx_stats.sigungu
   and s.floor_band  = b.band
  order by b.ord;
$$;

comment on function get_sigungu_tx_stats(text) is
  'Stage A(결정 0012) 구 실거래 단가 분포 — 층대 5칸을 **항상 같은 순서로** 돌려준다. '
  '표본이 없는 층대는 물질화뷰에 행이 없으므로 여기서 n=0 으로 채운다(칸이 사라지면 '
  '"그 층은 아예 안 판다"처럼 읽힌다). 화면은 n<5 면 수치를 감추고 "표본 부족"만 적는다. '
  'window_from 은 집계한 창의 시작 달, sigungu_nm 은 구 이름(화면에 지역명을 박지 않기 위해 '
  '서버가 준다). security definer — 물질화뷰가 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다';

revoke all on function list_parcel_transactions(text) from public, anon, authenticated;
revoke all on function get_sigungu_tx_stats(text) from public, anon, authenticated;


-- =====================================================================
-- Stage B — 참고 시세 밴드의 **서버 쪽** (2026-08-16, 결정 0013)
-- =====================================================================
-- 결정 0012 는 시세 표시를 두 단계로 갈랐고, Stage A(사실 표시)는 2026-08-15a 로 이미
-- 라이브에 있다. 여기서 만드는 것은 **Stage B** — 곁의 실거래로 "이 언저리"를 어림해
-- 밴드로 내보내는 길이다. 그 착수 여부는 성적표 v1(`docs/backtest/성적표-v1.md`)을 들고
-- 사장님이 재결재했고, 그 결재문이 결정 0013 이다.
--
-- ⛔ 절대 규칙 2 — 감정평가사 독점 업무를 연상시키는 표현(CLAUDE.md 금지 목록)은 이 파일
--    어디에도 쓰지 않는다. 여기 있는 것은 전부 **참고·추정**이며, 근거 단계(stage)와
--    표본 수(n)를 함께 낸다(절대 규칙 3). 근거를 숨긴 숫자는 내보내지 않는다.
--
-- 세 가지를 만든다:
--   ① price_gate_sigungu   — "이 구에서 참고 시세를 내도 되는가"의 정본 (결정 0013 §2)
--   ② price_floor_band()   — 층 번호 → 층대 이름 (백테스트와 **같은** 정의)
--   ③ list_price_bands()   — 이 필지의 층마다 밴드(또는 안 내는 이유)를 돌려준다
--
-- ## 왜 구 단위 게이트인가 (전 지역에 켜지 않는가)
--
-- 성적표 v1 은 "어디서나 믿을 만하다"를 보여주지 못했다. 어떤 구에서는 사다리가
-- **구 평균보다도 못하다**(금천구: 사다리 26.0% vs 구 평균 17.6%). 이미 화면에 있는
-- 구 평균보다 못한 값을 "추정"이라며 얹으면 후퇴다. 그래서 두 조건을 모두 만족한
-- 구에서만 켠다 — ① 운영 MdAPE ≤ 30% ② 같은 구에서 사다리가 구 평균을 이길 것.
--
-- ## 왜 목록을 표(DB)에 두나 — 화면·문서가 아니라
--
-- 목록을 화면 코드나 문서에 복사하면 성적표를 다시 뽑는 날 그 사본만 조용히 낡는다
-- (`list_open_sigungu()` 때 실제로 겪은 드리프트 — 확정 설계 9). 통과 구의 진실은
-- 서버 한 곳이고, 그 표를 채우는 것은 사람 손이 아니라 백테스트 산출물이다:
--   python scripts/backtest_price.py      → docs/backtest/통과구.csv
--   python scripts/load_price_gate.py     → price_gate_sigungu

-- =====================================================================
-- ① price_gate_sigungu — 참고 시세를 켜도 되는 구
-- =====================================================================
-- ## 왜 판정 근거(n_paired·ladder_mdape·base_mdape)까지 같이 넣나
--
-- 참·거짓만 남기면 "왜 이 구가 꺼져 있나"를 다음 사람이 성적표를 다시 뽑아야 알 수 있다.
-- 판정과 그 근거를 같은 줄에 두면, 표 한 번 조회로 "26.0% 인데 구 평균이 17.6% 라 졌다"
-- 까지 말할 수 있다. 숫자는 **짝지은 비교**(두 방법 모두 성립한 거래만)의 MdAPE 다.
create table if not exists price_gate_sigungu (
  sigungu_code  text        primary key,          -- PNU 앞 5자리
  sigungu_nm    text,
  n_paired      int,                              -- 짝지은 비교에 쓴 검증 거래 수
  ladder_mdape  numeric,                          -- 운영 모드(사다리) 오차 중앙값 (0~1)
  base_mdape    numeric,                          -- 대조군(구 평균) 오차 중앙값 (0~1)
  gate_pass     boolean     not null,
  loaded_at     timestamptz not null default now()
);

comment on table price_gate_sigungu is
  '결정 0013 §2 참고 시세 출시 기준선 — 이 구에서 밴드를 화면에 내도 되는가의 정본. '
  '조건 둘을 모두 만족해야 true: ① 사다리 MdAPE <= 30% ② 사다리가 BASE(구 평균)를 이김. '
  '⛔ 손으로 구를 넣고 빼지 않는다 — scripts/backtest_price.py 가 만든 docs/backtest/통과구.csv 를 '
  'scripts/load_price_gate.py 로만 갱신한다(결정 0013 §4). 기준선 자체를 바꾸는 것은 재결재 사항이다. '
  '⛔ anon 에게 열지 않는다 — 화면은 list_price_bands() 로만 읽는다.';

comment on column price_gate_sigungu.ladder_mdape is
  '짝지은 비교(두 방법 모두 성립한 거래만) 기준 운영 모드 MdAPE. 비율이다(0.29 = 29%)';
comment on column price_gate_sigungu.base_mdape is
  '같은 집합에서 잰 구 평균(BASE)의 MdAPE. 이 값보다 ladder_mdape 가 작아야 통과다';

-- 2026-08-13f 가 기본 권한을 바꿔 뒀지만, 그 명령이 닿지 않는 경로(대시보드가 만든 것 등)가
-- 남아 있으므로 **만든 자리에서 한 번 더 닫는다.** 라이브 확인은 post_load.py --check 가 한다.
revoke all on price_gate_sigungu from public, anon, authenticated;

-- ⛔ **이 표만 RLS 선언이 빠져 있었다** (2026-09-01 감사에서 기계 대조로 발견 — 정본의
--    `create table` 17개 vs `enable row level security` 16개, 빠진 하나가 이것이었다).
--    라이브는 켜져 있으니(17/17 실측) 지금 바뀌는 것은 없고, **정본으로 새 창고를 만들 때만**
--    이 표가 이중 잠금의 한 겹을 잃는다. 그 상태에서 누가 이 표를 대시보드로 다시 만들면
--    Supabase 가 새 객체에 anon 권한을 자동으로 붙이는 경로(2026-08-13 mv_search_parcel 사고)
--    에 그대로 노출된다.
-- ⓘ 다른 표와 같이 **정책은 하나도 만들지 않는다** — "RLS 켬 + 정책 0개" 가 곧 전부 거부다.
-- ⚠️ 이 표는 다른 16개와 성격이 하나 다르다: **유일한 독자가 정의자 함수 하나**(list_price_bands)
--    다. 그 함수는 이 표의 소유자와 같은 롤(postgres)이 만들므로 소유자 RLS 면제로 그대로
--    돈다(force 미사용). ⛔ 소유자가 갈리는 환경에서는 게이트가 통째로 0행이 되어 **전 구가
--    조용히 gate_fail 로 뒤집힌다** — 에러가 안 나므로 아무도 모른다.
alter table price_gate_sigungu enable row level security;

-- =====================================================================
-- ② price_floor_band — 층 번호 → 층대 이름
-- =====================================================================
-- ## 왜 mv_sigungu_tx_stats 의 CASE 를 안 쓰고 새로 만드나 (정의가 셋이 되는데도)
--
-- Stage A 의 층대(mv_sigungu_tx_stats)는 **옥탑(99)을 '3층이상'에 흡수**한다. 결정 0012 의
-- 층대 정의가 ">=3" 이라서다. 그런데 Stage B 의 근거인 백테스트(`scripts/backtest_price.py`
-- 의 `floor_band()`)는 옥탑을 **따로** 센다 — 그래서 성적표가 "옥탑은 근거 0건"이라고
-- 말할 수 있었고, 결정 0013 §3 이 옥탑을 미제공으로 정할 수 있었다.
-- 두 정의를 하나로 합치면 둘 중 하나가 근거와 어긋난다: Stage A 로 맞추면 옥탑이 3층+
-- 표본에 섞여 "검증된 적 없는 층"에 값이 나가고, Stage B 로 맞추면 이미 라이브에 나가는
-- Stage A 화면의 칸이 하루아침에 바뀐다. 그래서 **Stage B 는 자기 근거와 같은 자를 쓴다.**
-- ⛔ 그러니 이 함수와 mv_sigungu_tx_stats 의 CASE 를 "중복"이라며 합치지 말 것.
--
-- ## 왜 search_path 를 안 박나
--
-- 이 함수는 표를 한 줄도 읽지 않는다(순수 계산). SET 절을 붙이면 SQL 함수 인라인이 막혀
-- 후보 한 줄마다 함수 호출이 남는다 — 같은 이유로 형제 함수 search_key() 도 안 박았다.
create or replace function price_floor_band(p_floor smallint)
returns text
language sql
immutable
parallel safe
as $$
  select case
    when p_floor is null then '층미상'
    when p_floor < 0     then '지하'
    when p_floor = 1     then '1층'
    when p_floor = 2     then '2층'
    when p_floor = 99    then '옥탑'
    else                      '3층+'
  end
$$;

comment on function price_floor_band(smallint) is
  'Stage B(결정 0013) 층대 이름 — scripts/backtest_price.py 의 floor_band() 와 **같은 정의**다. '
  '지하=음수 / 1층 / 2층 / 3층+ / 옥탑=99 / 층미상=NULL(절대 규칙 4: 0 은 쓰지 않는다). '
  '⚠️ mv_sigungu_tx_stats 의 층대(옥탑을 3층이상에 흡수)와 일부러 다르다 — Stage A 와 Stage B 는 '
  '각자의 근거와 같은 자를 쓴다. 내부용이라 anon 에게 열지 않는다';

revoke all on function price_floor_band(smallint) from public, anon, authenticated;

-- =====================================================================
-- 반경 조회용 지리 인덱스
-- =====================================================================
-- 기존 idx_parcel_geom 은 **geometry** 인덱스라 미터 단위 반경 질의(geography)에 붙지 않는다.
-- 4326 geometry 로 거리를 재면 단위가 '도(degree)'라 위도에 따라 실제 거리가 달라진다 —
-- 백테스트는 haversine(미터)로 쟀으므로 화면도 미터로 잰다. 다만 "같은 자로 쟀다"가
-- "성적표 숫자가 곧 이 화면의 성적"이라는 뜻은 아니다 — 아래 사다리 주석 참조.
-- ⚠️ 이 인덱스를 만드는 동안 parcel(1.1M 행)에 **쓰기가 잠긴다**(SHARE 락 — 읽기는 된다).
--    대시보드 SQL Editor 는 한 트랜잭션이라 concurrently 를 쓸 수 없다. 적재 작업과
--    겹치지 않는 시간에 적용할 것.
-- ⓘ 좌표는 지금 parcel.lat/lng 와 geom 이 같은 값에서 나온다(load_sangkwon_snapshot 이
--    lat/lng 로 geom 을 만든다). 둘이 어긋나지 않게 하는 제약은 아직 없다(별건).
create index if not exists idx_parcel_geog on parcel using gist ((geom::geography));

-- =====================================================================
-- ③ list_price_bands — 이 필지의 층별 참고 시세 밴드
-- =====================================================================
-- ## 무엇을 돌려주나
--
-- 층 하나에 한 줄. `status` 가 그 줄의 성격을 말한다:
--   gate_fail    — 이 구는 아직 참고 시세를 내지 않는다(결정 0013 §2). 층 나열도 하지 않는다
--   floor_1f     — 1층은 제공하지 않는다(백테스트 MdAPE 45.2% — 코너·전면 여부가 자료에 없다)
--   no_evidence  — 지하·옥탑·층미상. 백테스트 표본이 **0건**이라 아무 말도 할 수 없다
--   no_estimate  — 사다리가 어느 단계도 못 세웠다("표본 부족")
--   ok           — 밴드를 낸다. stage(근거 단계)와 n(표본 수)을 반드시 함께 쓴다
--
-- ## 왜 밴드가 p25~p75 인가
--
-- 추정 한 점(중앙값)만 내면 "이 가격이다"로 읽힌다. 성적표가 말하는 것은 "이 언저리다"뿐이다
-- (전체 MdAPE 29.1%). 그래서 후보 거래 단가의 **사분위 폭**을 그대로 내보낸다 — 폭이 곧
-- "곁의 가게들이 실제로 이만큼 갈렸다"는 사실이다. 총액 환산은 화면이 median_area_m2 로 한다.
--
-- ## 사다리 (결정 0012 §6.2 · 백테스트와 같은 순서·같은 최소 표본)
--
--   L2  같은 필지 + 같은 층          최소 1건
--   L4  반경 100m + 같은 층          최소 3건
--   L5  반경 500m + 같은 층          최소 5건
--   L6  같은 법정동 + 같은 층대      최소 1건
--
-- ⛔ 이 최소 표본은 `scripts/backtest_price.py` 의 `MIN_SAMPLES` 와 **같은 값이라야 한다.**
--    갈라지면 화면과 성적표가 서로 다른 방법이 되는데 어디서도 에러가 안 난다.
-- ⚠️ 다만 **같아지는 것은 사다리 규칙과 최소 표본까지**다. 후보를 고르는 창은 서로 다르다:
--    백테스트는 학습 구간(~202512)의 거래만 후보로 쓰고, 여기서는 **오늘 기준 롤링 24개월**을
--    쓴다(검증 구간의 거래도 후보가 된다). 그래서 성적표의 29.1%·45.2% 같은 숫자는 이 함수의
--    성적이 아니라 **참고치**다 — "이 규칙이 그때 그 자료에서 이 정도였다"까지만 말한다.
-- ⚠️ BASE(구 평균)는 사다리에 넣지 않는다. 대조군이지 단계가 아니다(성적표 §1).
--
-- ## 왜 후보를 한 번만 모으고 층마다 다시 안 재나
--
-- 반경은 **필지 위치**로 정해지므로 층이 바뀌어도 이웃은 그대로다. 건물 한 채에 층이
-- 열몇 개니, 층마다 반경을 다시 재면 같은 지리 조회를 열몇 번 반복하게 된다.
--
-- ## 왜 24개월인가 · 왜 KST 인가
--
-- Stage A 의 구 분포(mv_sigungu_tx_stats)와 같은 창을 쓴다 — 한 화면에서 두 숫자가 서로
-- 다른 기간을 말하면 비교가 거짓말이 된다. now() 는 UTC 라 월말·월초에 한 달이 어긋나므로
-- KST 로 고정한다(timezone 룰).
--
-- ⚠️ 파라미터를 p_ 로 시작하는 이유: `pnu`·`floor_no` 는 컬럼 이름과 겹친다. 겹치면
--    PostgreSQL 이 컬럼을 우선 집어 `where t.pnu = t.pnu`(= 전 국토 거래)가 된다
--    (list_parcel_transactions·list_building_districts 가 밟을 뻔한 함정).
create or replace function list_price_bands(p_pnu text)
returns table (
  floor_no        smallint,
  status          text,
  stage           text,
  n               int,
  p25             numeric,
  median          numeric,
  p75             numeric,
  median_area_m2  numeric,
  window_from     text
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  -- ⛔ **파라미터를 그대로 쓰지 말 것.** 서명은 text 인데 pnu 컬럼은 세 표(parcel·
  --    building_floor·transaction) 모두 char(19) 다. `char컬럼 = text파라미터` 는 컬럼 쪽이
  --    text 로 캐스트돼 인덱스가 통째로 무력해진다(2026-08-16b 라이브 실측):
  --      · building_floor 층 목록: text 비교 cost 31,239 · 459.8ms ↔ char 비교 cost 2.07 · 0.796ms
  --      · 함수 전체:              707~733ms          ↔ char(19) 파라미터 복제본 73~101ms
  --    L4 주석의 배열 이야기와 **같은 병의 스칼라판**이다 — 파라미터와 컬럼의 타입을 맞춘다.
  -- ⓘ text→char(19) 캐스트는 19자를 넘는 입력을 자르지만, pnu 는 19자 고정이라 무해하다
  --    (더 긴 입력은 애초에 pnu 가 아니고, 잘려도 없는 필지라 빈 결과다).
  v_pnu      char(19) := p_pnu;
  -- ⚠️ **char(6) 이다.** contract_ym 컬럼이 char(6) 인데 여기를 text 로 두면
  --    `char컬럼 >= text변수` 비교에서 컬럼이 text 로 캐스트돼 인덱스 조건으로
  --    못 들어간다(2026-08-16b 가 pnu 에서 겪은 것과 **같은 병**). 나갈 때만
  --    `::text` 로 되돌린다 — window_from 은 text 로 약속돼 있다.
  v_from     char(6);
  v_gate     boolean;
  v_geog     geography;
  -- ⚠️ text[] 가 아니라 char(19)[] 인 이유: transaction.pnu 가 char(19) 라 text 와 견주면
  --    캐스트가 끼어 배열 조건이 인덱스 안으로 못 들어간다(아래 L4 주석의 실측 참조).
  v_near100  char(19)[];
  v_near500  char(19)[];
  v_floor    smallint;
  v_band     text;
  v_stage    text;
  v_n        int;
  v_p25      numeric;
  v_med      numeric;
  v_p75      numeric;
  v_area     numeric;
begin
  v_from := to_char((now() at time zone 'Asia/Seoul') - interval '24 months', 'YYYYMM');

  -- ⓘ 여기만 `::char(5)` 가 없는 것은 실수가 아니다(2026-08-22 라이브 실측).
  --    price_gate_sigungu.sigungu_code 는 **text** 다(mv_open_sigungu·parcel·transaction
  --    쪽 sigungu_code 가 char(5) 인 것과 다르다). substr() 의 결과도 text 라 지금이
  --    이미 타입이 맞은 상태다 — 여기에 ::char(5) 를 붙이면 text→char(5)→text 로
  --    되돌아가는 군더더기 캐스트가 생기고, 덤으로 bpchar 의 뒤 공백 무시 규칙까지
  --    끌어들인다. 타입을 맞추라는 규칙(2026-08-16b)은 **상대 컬럼의 타입**을 보라는
  --    뜻이지 char 로 통일하라는 뜻이 아니다.
  select g.gate_pass into v_gate
    from price_gate_sigungu g
   where g.sigungu_code = substr(v_pnu, 1, 5);

  -- 아직 판정이 없는 구(표에 줄이 없음)도 '아니오'다 — 모르면 안 낸다.
  if v_gate is not true then
    return query select null::smallint, 'gate_fail'::text, null::text, null::int,
                        null::numeric, null::numeric, null::numeric, null::numeric, v_from::text;
    return;
  end if;

  select p.geom::geography into v_geog from parcel p where p.pnu = v_pnu;

  -- 500m 안을 한 번만 훑고 100m 는 거기서 걸러 쓴다(백테스트 neighbors_within 과 같은 방식).
  -- 좌표가 없으면 두 배열이 비고, 반경 단계는 후보 0건이 되어 저절로 건너뛴다
  -- (백테스트의 coords_missing 과 같은 취급 — 죽지 않고 아래 단계로 내려간다).
  -- 마지막 인자 false = **구면**으로 잰다(기본값 true 는 회전타원체). 백테스트가 쓴
  -- haversine 이 구면이라 자를 맞춘 것이다. 남는 차이는 반지름 소수점뿐이고
  -- (PostGIS 6,371,008.7714m vs 백테스트 6,371,008.8m) 500m 에서 1mm 미만이라 무시한다.
  if v_geog is not null then
    select coalesce(array_agg(p.pnu) filter (
             where st_dwithin(p.geom::geography, v_geog, 100, false)), '{}'),
           coalesce(array_agg(p.pnu), '{}')
      into v_near100, v_near500
      from parcel p
     where p.geom is not null
       and st_dwithin(p.geom::geography, v_geog, 500, false);
  end if;
  v_near100 := coalesce(v_near100, '{}');
  v_near500 := coalesce(v_near500, '{}');

  for v_floor in
    select distinct bf.floor_no from building_floor bf
     where bf.pnu = v_pnu
     order by 1
  loop
    -- 1층은 값이 자리(코너·전면·골목)로 갈리는데 그 자리가 공공데이터에 없다.
    -- 백테스트 MdAPE 45.2% — 다른 층대의 두 배다. 그래서 "모른다"고 말한다(결정 0013 §3).
    if v_floor = 1 then
      return query select v_floor, 'floor_1f'::text, null::text, null::int,
                          null::numeric, null::numeric, null::numeric, null::numeric, v_from::text;
      continue;
    end if;

    -- 지하(음수)·옥탑(99)·층미상은 백테스트 표본이 **0건**이다(2017년부터 실거래 원본에
    -- 지하층 표기가 오지 않는다 — 알려진한계). 검증된 적 없는 층에는 값을 내지 않는다.
    if v_floor is null or v_floor < 0 or v_floor = 99 then
      return query select v_floor, 'no_evidence'::text, null::text, null::int,
                          null::numeric, null::numeric, null::numeric, null::numeric, v_from::text;
      continue;
    end if;

    v_band := price_floor_band(v_floor);

    select a.lvl, a.cnt, a.q25, a.q50, a.q75, a.area_med
      into v_stage, v_n, v_p25, v_med, v_p75, v_area
      from (
        select c.lvl,
               count(*)::int                                              as cnt,
               -- 자리수를 원본 컬럼과 맞춘다(unit_price=numeric(14,2)·bld_area_m2=numeric(10,2)).
               -- 보간 결과는 소수점이 끝없이 늘어나 화면·JSON 에 의미 없는 자리가 실린다.
               (percentile_cont(0.25) within group (order by c.unit_price))
                 ::numeric(14,2)                                           as q25,
               (percentile_cont(0.5)  within group (order by c.unit_price))
                 ::numeric(14,2)                                           as q50,
               (percentile_cont(0.75) within group (order by c.unit_price))
                 ::numeric(14,2)                                           as q75,
               -- 총액 환산의 자 — 화면이 "㎡당 단가 × 이 면적"으로 억 단위를 만든다.
               -- 면적이 없는 행은 빼고 잰다(있는 것처럼 0 을 섞으면 총액이 작아진다).
               (percentile_cont(0.5)  within group (order by c.bld_area_m2)
                 filter (where c.bld_area_m2 is not null))
                 ::numeric(10,2)                                           as area_med
          from (
            -- L2 — 같은 필지 같은 층
            select 'L2'::text as lvl, t.unit_price, t.bld_area_m2
              from transaction t
             where t.tx_type = '집합' and t.unit_price is not null
               and t.contract_ym >= v_from
               and t.pnu = v_pnu and t.floor_no = v_floor
            union all
            -- L4 — 반경 100m 같은 층
            -- ⚠️ 배열의 타입이 성능을 가른다(2026-08-16 라이브 EXPLAIN 실측, 이웃 839필지):
            --    · `t.pnu::text = any(text[])` → 배열이 **힙 필터**로 밀려 1,957행을 읽고 버림
            --      (buffers 618 · 4.4~5.7ms)
            --    · `join unnest(...) on t.pnu = nb.pnu` → 해시 조인이라 1,934행을 먼저 뜸
            --      (buffers 610 · 8.1~8.2ms)
            --    · `t.pnu = any(char(19)[])` → **Index Cond** 로 들어가 idx_tx_pnu 를 그대로 탐
            --      (buffers 133 · heap blocks 392→5 · 2.5~2.7ms) ← 이것을 쓴다
            --    핵심은 캐스트를 없애 **컬럼과 배열의 타입을 맞추는 것**이다.
            select 'L4', t.unit_price, t.bld_area_m2
              from transaction t
             where t.tx_type = '집합' and t.unit_price is not null
               and t.contract_ym >= v_from
               and t.floor_no = v_floor and t.pnu = any(v_near100)
            union all
            -- L5 — 반경 500m 같은 층
            select 'L5', t.unit_price, t.bld_area_m2
              from transaction t
             where t.tx_type = '집합' and t.unit_price is not null
               and t.contract_ym >= v_from
               and t.floor_no = v_floor and t.pnu = any(v_near500)
            union all
            -- L6 — 같은 법정동(PNU 앞 10자리) 같은 층대
            -- "행정동" 이 아니라 법정동인 이유: 실거래의 동은 문자, 건물의 동은 코드라
            -- 이름 대조가 조용히 어긋난다(성적표 §1 · 결정 0012 §4).
            select 'L6', t.unit_price, t.bld_area_m2
              from transaction t
             where t.tx_type = '집합' and t.unit_price is not null
               and t.contract_ym >= v_from
               and t.pnu is not null
               and substr(t.pnu, 1, 10) = substr(v_pnu, 1, 10)
               and price_floor_band(t.floor_no) = v_band
          ) c
         group by c.lvl
      ) a
      -- 최소 표본은 백테스트 MIN_SAMPLES 와 같은 값이다(위 ⛔ 주석 참조).
      join (values ('L2', 1, 1), ('L4', 2, 3), ('L5', 3, 5), ('L6', 4, 1))
             as s(lvl, ord, min_n) on s.lvl = a.lvl
     where a.cnt >= s.min_n
     order by s.ord
     limit 1;   -- 처음 성립하는 단계를 채택한다(사다리 걷기)

    if v_stage is null then
      return query select v_floor, 'no_estimate'::text, null::text, null::int,
                          null::numeric, null::numeric, null::numeric, null::numeric, v_from::text;
    else
      return query select v_floor, 'ok'::text, v_stage, v_n,
                          v_p25, v_med, v_p75, v_area, v_from::text;
    end if;
  end loop;
  return;
end;
$$;

comment on function list_price_bands(text) is
  'Stage B(결정 0013) 이 필지의 층별 참고 시세 밴드 — 곁의 실거래(최근 24개월·집합)로 어림한 '
  '추정값이며 감정평가가 아니다. 한 층에 한 줄이고 status 가 그 줄의 성격을 말한다: '
  'gate_fail(이 구는 기준선 미달 — 층 나열 없이 한 줄) / floor_1f(1층 미제공) / '
  'no_evidence(지하·옥탑·층미상 — 백테스트 표본 0건) / no_estimate(표본 부족) / ok(밴드). '
  'ok 인 줄은 stage(L2·L4·L5·L6)와 n(표본 수)을 **반드시 함께** 표시한다(절대 규칙 3). '
  'p25/median/p75 는 ㎡당 단가, median_area_m2 는 총액 환산용 후보 면적 중앙값이다. '
  'security definer — transaction·parcel·price_gate_sigungu 가 anon 에게 닫혀 있어 '
  '소유자 권한으로 대신 읽는다. 나가는 것은 층·통계값뿐(개별 거래·상호명은 나가지 않는다)';

-- public 원본은 닫는다 — 화면이 부르는 것은 api.list_price_bands 뿐(2026-09-05a)
revoke all on function list_price_bands(text) from public, anon, authenticated;


-- =====================================================================
-- 둘레의 업종 분포 (결정 0014 · 마이그레이션 2026-08-22c)
-- =====================================================================
-- 층별 화면에 "이 동네에 무슨 장사가 몇 곳 있나"를 두 자로 보여준다:
--   ① 상권 스코프 — 이 땅이 속한 상권(들) 안. 겹치면 전부(결정 0011 과 같은 규칙)
--   ② 반경 스코프 — 이 땅에서 500m 안
--
-- ## 왜 ①만 미리 계산하나 (2026-08-22 라이브 실측이 정했다)
--
--   ① 그때그때 세기                    → 12,512ms(찬 캐시) / 56ms(더운 캐시)
--   ② 반경, geom::geography 로 바로     → 47,756ms  ← 캐스트가 gist 인덱스를 죽인다
--   ③ 반경, bbox 선거름 + geography     →  2,976ms  ← 3초 제한 코앞
--   ④ 반경, 이웃 필지 PNU 배열 경유     →    469ms  ← 채택
--
-- ①이 더울 때 56ms 인데 찰 때 12.5초인 것이 핵심이다 — 2026-08-11 v_coverage_stats 500
-- 사고와 같은 병이라, 더운 캐시로 재고 "빠르다"고 하면 첫 방문자만 죽는다. 상권 안 점포
-- 수는 (상권, 분기)만으로 정해지고 필지와 무관하므로 미리 계산할 수 있다(굽기 26.7초 ·
-- 62,457행 · 5.6MB · 읽기 0.32ms). ⚠️ 반대로 반경은 답이 필지마다 달라 미리 못 굽는다.
--
-- ## 왜 반경을 이웃 필지로 재나
--
-- list_price_bands 가 같은 화면에서 이미 "반경 500m"를 이웃 필지로 정의해 쓴다. 두 블록이
-- 서로 다른 자로 500m 를 재면 비교가 거짓말이 된다. 두 자의 답을 8곳에서 대조해 최대
-- 차이 1.4% 임을 확인했다(unit_business.pnu 채움률 99.94%).
create materialized view if not exists mv_district_industry_mix as
select d.district_id,
       ub.snapshot_ym,
       ub.cat_l_cd, ub.cat_l_nm,
       ub.cat_m_cd, ub.cat_m_nm,
       count(*)::int as n
from district d
join unit_business ub
  on ub.geom is not null
 and st_contains(d.geom, ub.geom)
where ub.snapshot_ym = (select max(u.snapshot_ym) from unit_business u)
group by 1, 2, 3, 4, 5, 6;

comment on materialized view mv_district_industry_mix is
  '상권 × 업종(중분류) 점포 수 — 최신 분기 한 개만. 살아있는 쿼리는 찬 캐시에서 12.5초라 '
  '미리 굽는다(라이브 실측, 굽기 26.7초 · 읽기 0.32ms). 대분류는 이 표를 합쳐서 낸다. '
  '⚠️ 상권이 겹치는 자리의 점포는 **양쪽에 모두** 세어진다(2026-08-22 실측: 상권 안 462,858곳 중 '
  '17,946곳 = 3.9% 가 두 상권에 겹침, 3겹은 0건). 상권끼리 더하면 그만큼 부풀려진다. '
  '⚠️ 어느 분기가 최신인지는 **구울 때** 굳는다 — 새 분기를 적재하면 `python scripts/post_load.py`. '
  '⛔ anon 에게 열지 않는다 — 화면은 list_industry_mix 함수로만 읽는다.';

-- `concurrently` 갱신의 전제 조건. 조회(상권 몇 개 + 분기 하나)도 이 인덱스로 탄다(0.32ms).
create unique index if not exists mv_district_industry_mix_key
  on mv_district_industry_mix (district_id, snapshot_ym, cat_m_cd);

analyze mv_district_industry_mix;

-- ⚠️ 파라미터를 `p_` 로 시작하는 이유: `pnu` 는 컬럼 이름과 겹친다. 겹치면 PostgreSQL 이
--    컬럼을 우선 집어 `where p.pnu = p.pnu`(= 전 국토)가 된다.
-- ⛔ `p_pnu::char(19)` 캐스트를 지우지 말 것 — 컬럼이 char(19) 라 text 와 견주면 **컬럼 쪽**이
--    캐스트돼 인덱스가 통째로 죽는다(2026-08-16b 실측 459.8ms↔0.796ms).
create or replace function list_industry_mix(p_pnu text)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  with snap as (
    -- 두 블록이 반드시 **같은 분기**를 말하게 한다. 정본은 사전계산표 쪽이다 —
    -- 표가 낡으면 두 블록이 **함께** 낡을 뿐, 서로 다른 분기를 말하지는 않는다
    -- (한 화면에서 두 숫자가 다른 기간을 말하는 것이 가장 나쁜 상태다).
    select coalesce(
             (select max(m.snapshot_ym) from mv_district_industry_mix m),
             (select max(u.snapshot_ym) from unit_business u)) as ym
  ),
  me as (
    -- 좌표가 없으면 아예 답하지 않는다. 여기를 열어 두면 반경 0곳이 "이 동네엔 가게가
    -- 없다"는 **단정**으로 새어 나간다(list_building_districts 와 같은 원칙).
    select p.geom as g, p.geom::geography as gg
    from parcel p
    where p.pnu = p_pnu::char(19) and p.geom is not null
  ),
  hit as (
    -- 술어를 st_contains 로 맞춘다 — 결정 0008·0011 의 실측이 이 술어로 나온 숫자다.
    select d.district_id, d.district_nm, d.district_type, d.source_nm, d.area_m2
    from district d cross join me
    where st_contains(d.geom, me.g)
  ),
  near as (
    -- ⚠️ char(19)[] 이라야 한다. text[] 로 두면 배열 조건이 인덱스 안으로 못 들어가
    --    힙 필터로 밀린다(list_price_bands L4 주석의 실측과 같은 병).
    -- 마지막 인자 false = 구면으로 잰다. list_price_bands 와 같은 자를 쓴다.
    select coalesce(array_agg(p.pnu), '{}'::char(19)[]) as pnus
    from parcel p cross join me
    where p.geom is not null
      and st_dwithin(p.geom::geography, me.gg, 500, false)
  ),
  dcat as (
    select h.district_id, m.cat_l_cd, m.cat_l_nm, sum(m.n)::int as n
    from hit h
    join mv_district_industry_mix m
      on m.district_id = h.district_id
     and m.snapshot_ym = (select ym from snap)
    group by 1, 2, 3
  ),
  rcat as (
    select ub.cat_l_cd, ub.cat_l_nm, count(*)::int as n
    from unit_business ub cross join near
    where ub.snapshot_ym = (select ym from snap)
      and ub.pnu = any(near.pnus)
    group by 1, 2
  ),
  dj as (
    select h.area_m2, h.district_id,
           jsonb_build_object(
             'district_id', h.district_id,
             'name', h.district_nm,
             'type', h.district_type,
             'source_nm', h.source_nm,
             'total', coalesce((select sum(c.n) from dcat c
                                 where c.district_id = h.district_id), 0)::int,
             'cats', coalesce((select jsonb_agg(
                                        jsonb_build_object('cd', c.cat_l_cd,
                                                           'nm', c.cat_l_nm,
                                                           'n',  c.n)
                                        order by c.n desc, c.cat_l_cd)
                                 from dcat c where c.district_id = h.district_id),
                              '[]'::jsonb)
           ) as j
    from hit h
  )
  select jsonb_build_object(
    'snapshot_ym', (select ym from snap),
    'radius_m', 500,
    -- 좁은 상권이 더 구체적인 설명이라 먼저 온다(list_building_districts 와 같은 정렬).
    'districts', coalesce((select jsonb_agg(dj.j order by dj.area_m2 asc, dj.district_id)
                            from dj), '[]'::jsonb),
    -- 좌표가 없으면 null 이다. **빈 집계가 아니라 "모른다"** 라서 화면이 그 블록을 감춘다.
    'radius', case when exists (select 1 from me) then jsonb_build_object(
        'total', coalesce((select sum(r.n) from rcat r), 0)::int,
        'cats',  coalesce((select jsonb_agg(
                                    jsonb_build_object('cd', r.cat_l_cd,
                                                       'nm', r.cat_l_nm,
                                                       'n',  r.n)
                                    order by r.n desc, r.cat_l_cd)
                            from rcat r), '[]'::jsonb)
      ) else null end
  );
$$;

comment on function list_industry_mix(text) is
  '결정 0014 이 필지 둘레의 업종 분포(대분류). districts = 속한 상권마다 한 묶음(겹치면 전부, '
  '좁은 상권 먼저) · radius = 반경 500m. radius 가 null 이면 필지 좌표가 없어 **모른다**는 뜻이고 '
  '빈 집계와 다르다. snapshot_ym 은 두 블록이 함께 쓰는 분기다(사전계산표가 정본). '
  '⚠️ 상권끼리 더하지 말 것 — 겹치는 자리의 점포는 양쪽에 세어진다(실측 3.9%). '
  'security definer — unit_business·parcel·district 가 anon 에게 닫혀 있어 소유자 권한으로 '
  '대신 읽는다. **나가는 것은 업종별 개수뿐이다 — 상호명은 한 글자도 나가지 않는다.**';

-- 대분류를 누를 때만 부른다(첫 화면에서 75종을 다 내려보내지 않는다).
-- ⛔ `p_cat::char(2)` 캐스트도 같은 이유다 — cat_l_cd 가 char(2) 다.
create or replace function list_industry_detail(p_pnu text, p_cat text)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  with snap as (
    select coalesce(
             (select max(m.snapshot_ym) from mv_district_industry_mix m),
             (select max(u.snapshot_ym) from unit_business u)) as ym
  ),
  me as (
    select p.geom as g, p.geom::geography as gg
    from parcel p
    where p.pnu = p_pnu::char(19) and p.geom is not null
  ),
  hit as (
    select d.district_id, d.district_nm, d.area_m2
    from district d cross join me
    where st_contains(d.geom, me.g)
  ),
  near as (
    select coalesce(array_agg(p.pnu), '{}'::char(19)[]) as pnus
    from parcel p cross join me
    where p.geom is not null
      and st_dwithin(p.geom::geography, me.gg, 500, false)
  ),
  dsub as (
    select h.district_id, m.cat_m_cd, m.cat_m_nm, sum(m.n)::int as n
    from hit h
    join mv_district_industry_mix m
      on m.district_id = h.district_id
     and m.snapshot_ym = (select ym from snap)
     and m.cat_l_cd = p_cat::char(2)
    group by 1, 2, 3
  ),
  rsub as (
    select ub.cat_m_cd, ub.cat_m_nm, count(*)::int as n
    from unit_business ub cross join near
    where ub.snapshot_ym = (select ym from snap)
      and ub.pnu = any(near.pnus)
      and ub.cat_l_cd = p_cat::char(2)
    group by 1, 2
  ),
  dj as (
    select h.area_m2, h.district_id,
           jsonb_build_object(
             'district_id', h.district_id,
             'name', h.district_nm,
             'total', coalesce((select sum(s.n) from dsub s
                                 where s.district_id = h.district_id), 0)::int,
             'cats', coalesce((select jsonb_agg(
                                        jsonb_build_object('cd', s.cat_m_cd,
                                                           'nm', s.cat_m_nm,
                                                           'n',  s.n)
                                        order by s.n desc, s.cat_m_cd)
                                 from dsub s where s.district_id = h.district_id),
                              '[]'::jsonb)
           ) as j
    from hit h
  )
  select jsonb_build_object(
    'snapshot_ym', (select ym from snap),
    'radius_m', 500,
    -- 물어본 업종을 그대로 돌려준다 — 화면이 늦게 도착한 답(그 사이 다른 업종을 고른
    -- 경우)을 버릴 수 있어야 한다. 이게 없으면 목록이 조용히 뒤바뀐다.
    'cat_l_cd', p_cat,
    'districts', coalesce((select jsonb_agg(dj.j order by dj.area_m2 asc, dj.district_id)
                            from dj), '[]'::jsonb),
    'radius', case when exists (select 1 from me) then jsonb_build_object(
        'total', coalesce((select sum(s.n) from rsub s), 0)::int,
        'cats',  coalesce((select jsonb_agg(
                                    jsonb_build_object('cd', s.cat_m_cd,
                                                       'nm', s.cat_m_nm,
                                                       'n',  s.n)
                                    order by s.n desc, s.cat_m_cd)
                            from rsub s), '[]'::jsonb)
      ) else null end
  );
$$;

comment on function list_industry_detail(text, text) is
  '결정 0014 고른 대분류 안의 중분류 분포. 반환 구조는 list_industry_mix 와 같고 cat_l_cd 를 '
  '그대로 되돌려 준다(늦게 도착한 답을 화면이 버릴 수 있게). '
  'security definer — **나가는 것은 업종별 개수뿐이다(상호명 없음).**';

revoke all on function list_industry_mix(text) from public, anon, authenticated;
revoke all on function list_industry_detail(text, text) from public, anon, authenticated;


-- ── ⛔ 요약표는 공개키에게 열지 않는다 (2026-08-13f) ─────────────────────────
-- Supabase 는 스키마 public 에 기본 권한을 걸어 두어 **새로 만드는 표·물질화뷰마다
-- anon 에게 전체 권한을 자동으로 준다.** 2026-08-08 의 `revoke ... on all tables` 는
-- 그 시점에 있던 것만 닫는 일회성 명령이라, 오늘 만든 이 둘이 그 사이로 열렸다.
-- 실측(적대검증): `GET /rest/v1/mv_search_parcel?limit=3` 이 200 + 188,442행 카운트까지
-- 가능했다 — 검색 상한 게이트를 REST 페이지네이션으로 통째로 건너뛸 수 있었다.
-- ⚠️ 물질화뷰는 `enable row level security` 도 못 걸어(테이블 전용) 이중 방어가 없다.
revoke all on mv_search_parcel from public, anon, authenticated;
revoke all on mv_open_sigungu  from public, anon, authenticated;
revoke all on mv_sigungu_tx_stats from public, anon, authenticated;
-- 각주 집계를 미리 계산해 둔 표(2026-08-22d). 값은 집계 4개뿐이라 새어도 큰일은
-- 아니지만, "새 요약표는 닫는다"에 예외를 만들면 다음번엔 위험한 표가 같은 논리로 열린다.
-- 화면은 v_coverage_stats 뷰로만 읽는다.
revoke all on mv_coverage_stats from public, anon, authenticated;
-- 상호명은 안 나가더라도 이 표가 열리면 **전국 상권의 업종 구성이 통째로** 긁힌다(2026-08-22c).
revoke all on mv_district_industry_mix from public, anon, authenticated;

-- 그리고 **앞으로 만들 것도 자동으로 안 열리게** 기본값 자체를 바꾼다.
-- 이게 없으면 다음에 표를 하나 더 만들 때 같은 일이 또 난다(사람 기억에 의존하게 된다).
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
-- ⚠️ **함수도 반드시 포함해야 한다.** 2026-08-13f 는 표·시퀀스만 닫아 반쪽이었고,
--    라이브를 다시 보니 `pg_default_acl`(객체종류 f)이 여전히 anon 에게 EXECUTE 를
--    자동으로 주고 있었다 — 새 함수를 만들 때마다 사람이 revoke 를 기억해야 하는 상태.
--    실제로 트리거용 `unit_business_append_only` 가 그렇게 열려 있었다(2026-08-13g).
alter default privileges in schema public revoke all on functions from anon, authenticated;
-- ⛔ **위 줄은 PUBLIC 을 한 번도 못 막았다** (2026-09-01 라이브 실측). PostgreSQL 내장
--    기본값이 새 함수에 **PUBLIC 에게 EXECUTE** 를 준다(공식 문서 §5.8 표 5.2). `anon`·
--    `authenticated` 는 그 기본값에 **애초에 없어서** 회수해도 PUBLIC 이 그대로 남는다.
--    ⛔ **`pg_default_acl` 의 public 스키마 항목을 오독하지 말 것** (2026-09-01 2차 검증에서
--      정정). 그 항목이 `{postgres=X, service_role=X}` 로 보이고 PUBLIC 이 없는데, 예전
--      주석은 이것을 "Supabase 부트스트랩이 PUBLIC 을 막아 둔 것"이라 읽었다 — **둘 다 틀렸다.**
--        ① 스키마별 항목에 PUBLIC 이 없는 것은 **아무 뜻이 없다.** 스키마별 기본권한은
--           전역 기본값에 **더하기만** 하고 빼지 못하므로, 항목에 안 적혀도 PUBLIC 은 온다.
--        ② 거기서 anon·authenticated 가 빠져 있는 것은 **바로 위 우리 줄이 한 일**이지
--           Supabase 가 한 일이 아니다.
--    ⇒ 실제 차단은 **파일 맨 앞의 전역 한 줄**이 한다(첫 `create function` 앞 — 거기 있어야
--      그 아래 모든 함수에 걸린다). 마이그레이션 2026-09-01b.

-- 트리거가 부르는 함수는 사람이 직접 부를 일이 없다. 노출면은 "화면이 쓰는 것"만 남긴다.
revoke all on function unit_business_append_only() from public, anon, authenticated;

-- ── 생성 컬럼이 부르는 헬퍼는 **쓰는 롤**에게 EXECUTE 가 필요하다 (2026-09-01 독립 검토) ──
--
-- ⛔ **여기 빠지면 적재가 죽는다 — 그런데 지금 라이브에서는 안 죽는다.** 그 차이가 함정이다.
--    `parcel`·`building` 의 검색 키 컬럼이 `generated always as (search_key(...)) stored` 라,
--    PostgreSQL 은 **INSERT/UPDATE 하는 그 순간 그 롤로** 이 함수들을 부른다. 적재기는
--    service_role 로 쓴다(scripts/collectors/*.py 가 SANGGA_SUPABASE_SERVICE_KEY 사용).
-- ⚠️ 지금까지 정본에는 이 세 함수에 대한 grant 가 **한 줄도 없었다.** 라이브가 도는 이유는
--    우리 파일이 아니라 **Supabase 부트스트랩의 스키마별 기본권한**(`pg_default_acl` 실측:
--    `postgres | public | f → postgres=X | service_role=X`)이다. 즉 **물려받은 것이지 우리가
--    말한 것이 아니었다.** 맨 Postgres 로 이 파일만 돌려 창고를 세우면 적재가
--    `permission denied for function search_key` 로 죽는다.
-- ⓘ 라이브에 적용해도 변화 0이다(이미 그 권한을 갖고 있다) — 정본이 **스스로 완결되게**
--    하는 것이 목적이다.
-- ⛔ anon 에게는 주지 않는다. 화면은 이 함수들을 직접 부르지 않고, 저장된 컬럼 값만 읽는다.
grant execute on function search_key(text)                          to service_role;
grant execute on function building_display_nm(text, text)           to service_role;
grant execute on function parcel_jibun_addr(text, text, text, text) to service_role;


-- 상한 함수는 내부용이다. 화면은 search_scope() 가 돌려주는 판정만 쓴다.
-- (search_scope() 자체의 revoke·grant 는 그 함수를 만드는 자리에 한 벌만 둔다 —
--  같은 grant 를 두 곳에 적어 두면 한쪽 서명이 낡아도 다른 쪽이 가려 준다.)
revoke all on function search_scope_limit() from public, anon, authenticated;

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
-- 내부용 매핑표. 화면은 이 표를 직접 읽지 않는다(함수를 거친다).
-- ⛔ Supabase 는 **새로 생기는 표를 anon 에 자동으로 연다**(pg_default_acl) — 아래
--    `revoke ... on all tables` 는 이 파일을 돌리는 그 순간의 표만 닫는 일회성 명령이다.
--    그래서 마이그레이션(2026-08-14c)에서는 만든 자리에서 따로 한 번 더 닫는다.
alter table district_rone_map enable row level security;
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

-- 화면이 실제로 읽는 뷰 하나만 연다(src/lib/appConstants.ts의 FLOOR_STACK_VIEW).
-- authenticated에도 주는 이유: 지금은 로그인이 없지만 나중에 붙였을 때 화면이
-- 조용히 빈 목록으로 바뀌는 사고를 막는다. 둘 다 읽기 전용이다.
grant select on v_floor_stack to anon, authenticated;
-- 각주 숫자용 집계 뷰(집계값 4개뿐 — 상호명·좌표 없음).
-- ⛔ **먼저 회수하고 준다.** 라이브 실측(2026-08-22)에서 이 뷰만 anon·authenticated 에게
--    INSERT·UPDATE·DELETE·TRUNCATE·REFERENCES·TRIGGER 까지 열려 있었다(v_floor_stack 은
--    SELECT 하나뿐 — 둘이 어긋나 있었다). 출처는 Supabase 기본 권한(pg_default_acl) 이고,
--    `grant select` 는 **더하기라** 그걸 못 걷어낸다.
-- ℹ️ **이 파일로 만드는 새 환경에서는 위 `revoke all on all tables` 스윕이 두 뷰를 모두
--    덮으므로 원래도 SELECT 만이다.** 어긋난 것은 라이브뿐이었다 — 그 스윕은 *돌린 그 시점의*
--    객체만 닫는 일회성 명령이라, 그 뒤에 만들어진(또는 대시보드로 다시 만들어진) 뷰에는
--    안 걸린다. 그래서 정본에도 짝을 남겨 **어느 경로로 만들어져도 같은 상태**가 되게 한다.
--    (같은 이유로 v_floor_stack 은 건드리지 않는다 — 라이브·새 환경 둘 다 이미 SELECT 만이다.)
-- ⚠️ 뷰 아래가 물질화뷰라 실제 쓰기는 어차피 실패한다 — 그래도 선언은 최소 권한이어야
--    한다. 나중에 속이 쓰기 가능한 것으로 바뀌면 그 순간 경보 없이 진짜로 열린다.
revoke all on v_coverage_stats from public, anon, authenticated;
grant select on v_coverage_stats to anon, authenticated;

-- 검색 함수의 public 원본은 닫는다 — 열리는 것은 api.search_buildings 뿐(2026-09-05a)
revoke all on function search_buildings(text, int, text) from public;
revoke all on function search_buildings(text, int, text) from public, anon, authenticated;

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
--    ✅ 2026-08-22e 에서 (A)를 채택해 아래 "API 스키마" 절로 구현했다.


-- =====================================================================
-- API 스키마 — PostgREST 가 보는 곳을 public 밖으로 옮긴다 (2026-08-22e 추가)
-- =====================================================================
-- 위 "남은 구멍"의 해결이다. PostGIS 가 public 에 설치돼 `spatial_ref_sys` 같은
-- 시스템 표가 REST 로 노출되는데 소유자가 supabase_admin 이라 **우리 권한으로는 회수가
-- 안 된다.** 그래서 회수 대신 **이사**한다 — PostgREST 가 보는 스키마 목록에서 public 을
-- 빼면 public 안의 모든 것이 REST 에서 사라진다.
--
-- 2026-08-08 이 "미검증"으로 미뤄 둔 전제 2개는 2026-08-22 도커 실측으로 둘 다 통과했다:
--   (전제1) 노출 목록에서 public 제거 가능 → ✅ 되고, public 접근은 PGRST106/406 으로 막힌다.
--   (전제2) pass-through 뷰로 업서트 가능 → ✅ PK 자동 감지가 뷰를 관통한다(단일·복합 PK 모두).
--           ⇒ 수집·적재기는 코드 변경 0(REST 경로도 표 이름도 그대로).
-- 상세·적용 순서·드리프트 복구 SQL 은 supabase/migrations/2026-08-22e_api_schema.sql 헤더.
--
-- ⚠️ 노출 목록의 **순서가 `api, public`** 이라야 한다. profile 헤더를 안 보내는 클라이언트
--    (파이썬 수집기)는 "첫 스키마"를 타기 때문이다. 화면(supabase-js)은 기본으로
--    `accept-profile: public` 을 보내므로 `db: { schema: 'api' }` 가 필수다.

create schema if not exists api;

-- 스키마를 여는 것과 그 안을 읽는 것은 별개다. usage 가 없으면 PostgREST 가 못 연다.
grant usage on schema api to anon, authenticated, service_role;

-- ⛔ **`public` 쪽에는 이 줄이 없었다** (문서화된 백로그 — 2026-09-01 감사에서 정리).
--    라이브는 Supabase 가 깔아 준 상태라 멀쩡하지만(`nspacl` 에 anon=U 실측), 그건 물려받은
--    것이지 정본이 말한 것이 아니다. **정본만으로 새 창고를 세우면** anon 이 public 스키마를
--    못 열어, 그 안을 읽는 정의자 함수들이 다른 이유로 죽는다.
--    ⓘ 실행 권한(위 기본권한 블록)과는 별개 축이다 — usage 는 "방문을 여는 것", execute 는
--      "그 안의 물건을 쓰는 것". 하나만 있어도 안 된다.
grant usage on schema public to anon, authenticated, service_role;

-- ⛔ 기본값부터 닫는다 — Supabase 는 새 객체마다 anon 에 권한을 자동으로 준다
--    (pg_default_acl). public 에서 2026-08-13f·13g 가 겪은 함정을 새 스키마에서
--    반복하지 않는다. ⚠️ 이 문장은 **실행한 롤이 만드는 것**에만 걸리므로, 아래에서
--    객체마다 revoke 를 한 번 더 명시한다(최종 방어선은 post_load.py --check).
alter default privileges in schema api revoke all on tables from anon, authenticated;
alter default privileges in schema api revoke all on sequences from anon, authenticated;
alter default privileges in schema api revoke all on functions from anon, authenticated;
-- ⛔ **위 세 줄만으로는 함수가 안 막힌다** (2026-09-01 라이브 실측으로 발견).
--    PostgreSQL 의 내장 기본값은 새 함수에 **PUBLIC 에게 EXECUTE** 를 준다(공식 문서
--    §5.8 표 5.2). 그런데 그 기본값에 `anon`·`authenticated` 는 애초에 없어서, 위 줄은
--    **없는 것을 회수하는 셈**이라 아무 일도 하지 않는다 — 실제로 라이브 `pg_default_acl`
--    에 `api` 항목이 **0건**이었다(어느 롤에도 없음). 즉 이 스키마는 그동안 내장 기본값
--    (= PUBLIC 에 열림) 위에 서 있었다. 지금 함수 17개가 안전한 것은 전부 만든 자리에서
--    명시 회수를 해 왔기 때문이지 이 기본 규칙 덕이 아니다.
--    ⓘ 대조로 `public` 스키마는 항목이 있고 PUBLIC 이 빠져 있다 — Supabase 부트스트랩이
--      걸어 둔 것이라 **우리가 건 규칙이 아니다.** 아래 두 줄로 우리 뜻을 명시한다.
--    ⚠️ 여전히 "실행한 롤이 만드는 것"에만 걸린다 — 만든 자리 revoke 관습은 그대로 둔다.
--    마이그레이션 2026-09-01b.
-- ⛔ **여기에 `in schema api … from public` 을 적지 말 것 — 아무 일도 안 한다.**
--    공식 문서가 우리가 쓰던 바로 그 문장을 '효과 없음' 예시로 든다:
--      "Per-schema REVOKE is only useful to reverse the effects of a previous per-schema
--       GRANT." / "This command has no effect, unless it is undoing a matching GRANT:
--       ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;"
--    스키마별 기본권한은 전역 기본값에 **더하기만** 할 뿐 빼지 못한다.
--    ⇒ 진짜 차단은 **전역 한 줄**이고, 이 파일 위쪽(public 기본권한 블록 끝)에 있다.
--    (이 자리에 스키마별 형태를 한 번 넣었다가 라이브에서 무효임이 드러나 지웠다 — 2026-09-01b.)

-- ── 화면이 읽는 뷰 2개 ───────────────────────────────────────────────────────
-- 원본을 옮기지 않고 **덧붙인다** — 옮기면 public 을 읽는 다른 뷰·함수가 전부 깨진다.
-- 뷰의 기본값 `security_invoker = false` 덕에 소유자(postgres) 권한으로 읽으므로,
-- 나중에 public 쪽 anon 권한을 전부 회수해도 이 뷰는 그대로 돈다(자립).
-- ⚠️ **`select *` 는 만들 때의 칼럼 목록으로 굳는다.** public 쪽 뷰에 칼럼을 덧붙여도
--    이 쌍둥이는 옛 칼럼만 낸다 — 에러가 아니라 조용한 누락이라 아무도 모른다.
--    그러니 public 뷰의 칼럼을 바꾸는 마이그레이션은 **반드시** 이 두 줄을 다시 실행하고
--    `notify pgrst, 'reload schema';` 까지 해야 한다(2026-08-24a 가 그 형태의 첫 사례).
create or replace view api.v_floor_stack as select * from public.v_floor_stack;
create or replace view api.v_coverage_stats as select * from public.v_coverage_stats;

-- 먼저 회수하고 준다(grant 는 더하기라 자동으로 붙은 쓰기 권한을 못 걷어낸다).
revoke all on api.v_floor_stack     from public, anon, authenticated;
revoke all on api.v_coverage_stats  from public, anon, authenticated;
grant select on api.v_floor_stack     to anon, authenticated;
grant select on api.v_coverage_stats  to anon, authenticated;

-- ── 화면이 부르는 함수 9개 — 같은 서명으로 감싼다 ────────────────────────────
-- ⚠️ 서명(파라미터 이름·타입·기본값)과 돌려주는 칸 이름을 원본과 한 글자도 다르지 않게
--    적는다. PostgREST 는 JSON 키 이름으로 인자를 찾으므로 하나만 달라도 PGRST202 다.
-- ⚠️ `set search_path = ''` 라 본문의 이름은 전부 `public.` 으로 완전수식한다 —
--    누가 검색경로를 갈아끼워도 다른 함수가 대신 불릴 수 없다(security definer 표준 방어).
-- ⓘ volatility 는 원본과 맞춘다(전부 stable).
create or replace function api.search_buildings(q text, lim int default 25, sigungu text default null)
returns table (
  bld_id         text,
  pnu            char(19),
  bld_nm         text,
  road_addr      text,
  jibun_addr     text,
  lat            double precision,
  lng            double precision,
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
set search_path = ''
as $$ select * from public.search_buildings(q, lim, sigungu) $$;

create or replace function api.search_scope(q text, sigungu text default null)
returns table (too_broad boolean, match_cnt int)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.search_scope(q, sigungu) $$;

create or replace function api.list_open_sigungu()
returns table (sido_code char(2), sido_nm text, sigungu_code char(5), sigungu_nm text, building_cnt int)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_open_sigungu() $$;

create or replace function api.list_building_districts(bld_id text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$ select public.list_building_districts(bld_id) $$;

create or replace function api.list_parcel_transactions(pnu text)
returns table (
  floor_no     smallint,
  contract_ym  text,
  contract_day smallint,
  bld_area_m2  numeric,
  price_won    bigint,
  unit_price   numeric,
  tx_type      text
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_parcel_transactions(pnu) $$;

create or replace function api.get_sigungu_tx_stats(sigungu text)
returns table (
  floor_band        text,
  n                 int,
  median_unit_price numeric,
  p25_unit_price    numeric,
  p75_unit_price    numeric,
  window_from       text,
  sigungu_nm        text
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.get_sigungu_tx_stats(sigungu) $$;

create or replace function api.list_price_bands(p_pnu text)
returns table (
  floor_no        smallint,
  status          text,
  stage           text,
  n               int,
  p25             numeric,
  median          numeric,
  p75             numeric,
  median_area_m2  numeric,
  window_from     text
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_price_bands(p_pnu) $$;

create or replace function api.list_industry_mix(p_pnu text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$ select public.list_industry_mix(p_pnu) $$;

create or replace function api.list_industry_detail(p_pnu text, p_cat text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$ select public.list_industry_detail(p_pnu, p_cat) $$;

-- Postgres 는 새 함수의 EXECUTE 를 PUBLIC(모든 롤)에게 기본으로 준다. 위 기본값 변경은
-- anon·authenticated 만 다루므로 PUBLIC 경로가 남는다 — 먼저 회수하고 필요한 롤에만 준다.
revoke all on function api.search_buildings(text, int, text)  from public, anon, authenticated;
revoke all on function api.search_scope(text, text)           from public, anon, authenticated;
revoke all on function api.list_open_sigungu()                from public, anon, authenticated;
revoke all on function api.list_building_districts(text)      from public, anon, authenticated;
revoke all on function api.list_parcel_transactions(text)     from public, anon, authenticated;
revoke all on function api.get_sigungu_tx_stats(text)         from public, anon, authenticated;
revoke all on function api.list_price_bands(text)             from public, anon, authenticated;
revoke all on function api.list_industry_mix(text)            from public, anon, authenticated;
revoke all on function api.list_industry_detail(text, text)   from public, anon, authenticated;

grant execute on function api.search_buildings(text, int, text)  to anon, authenticated;
grant execute on function api.search_scope(text, text)           to anon, authenticated;
grant execute on function api.list_open_sigungu()                to anon, authenticated;
grant execute on function api.list_building_districts(text)      to anon, authenticated;
grant execute on function api.list_parcel_transactions(text)     to anon, authenticated;
grant execute on function api.get_sigungu_tx_stats(text)         to anon, authenticated;
grant execute on function api.list_price_bands(text)             to anon, authenticated;
grant execute on function api.list_industry_mix(text)            to anon, authenticated;
grant execute on function api.list_industry_detail(text, text)   to anon, authenticated;

-- ── 수집·적재기가 REST 로 쓰는 표 — pass-through 뷰 ──────────────────────────
-- 이 목록은 스크립트를 훑어 뽑은 것이다(`/rest/v1/` 와 upsert 대상). 여기 **없는 것**은
-- 일부러 없다 — district·district_rone_map·price_gate_sigungu·물질화뷰들은 psql(dbx.py)
-- 로만 다루므로 REST 경로가 필요 없고, 안 만드는 것이 곧 노출면을 줄이는 일이다.
--
-- ⚠️ **뷰는 RLS 를 우회한다.** 아래 표는 전부 RLS 가 켜져 있지만 이 뷰는 소유자 권한으로
--    읽으므로 RLS 가 안 걸린다 — **권한만이 방어선**이다. anon 에게 하나라도 새면
--    상호명(unit_business)·실거래(transaction)가 통째로 나간다. 그래서 표마다 revoke 를
--    명시한다(자동 개방이 없기를 믿고 넘어가지 않는다).
create or replace view api.parcel           as select * from public.parcel;
create or replace view api.building         as select * from public.building;
create or replace view api.unit             as select * from public.unit;
create or replace view api.building_floor   as select * from public.building_floor;
create or replace view api.unit_business    as select * from public.unit_business;
create or replace view api.transaction      as select * from public.transaction;
create or replace view api.rent_stat        as select * from public.rent_stat;
create or replace view api.collect_progress as select * from public.collect_progress;
create or replace view api.api_quota_log    as select * from public.api_quota_log;
create or replace view api.bjd_code         as select * from public.bjd_code;

revoke all on api.parcel           from public, anon, authenticated;
revoke all on api.building         from public, anon, authenticated;
revoke all on api.unit             from public, anon, authenticated;
revoke all on api.building_floor   from public, anon, authenticated;
revoke all on api.unit_business    from public, anon, authenticated;
revoke all on api.transaction      from public, anon, authenticated;
revoke all on api.rent_stat        from public, anon, authenticated;
revoke all on api.collect_progress from public, anon, authenticated;
revoke all on api.api_quota_log    from public, anon, authenticated;
revoke all on api.bjd_code         from public, anon, authenticated;

grant select, insert, update, delete on api.parcel           to service_role;
grant select, insert, update, delete on api.building         to service_role;
grant select, insert, update, delete on api.unit             to service_role;
grant select, insert, update, delete on api.building_floor   to service_role;
grant select, insert, update, delete on api.unit_business    to service_role;
grant select, insert, update, delete on api.transaction      to service_role;
grant select, insert, update, delete on api.rent_stat        to service_role;
grant select, insert, update, delete on api.collect_progress to service_role;
grant select, insert, update, delete on api.api_quota_log    to service_role;
grant select, insert, update, delete on api.bjd_code         to service_role;

-- =====================================================================
-- 우편함 — 화면에서 들어오는 짧은 글 한 통 (2026-08-24b)
-- =====================================================================
-- 사람이 쓴 의견(kind=opinion)과 화면이 죽으며 자동으로 남긴 것(kind=error)을 한 표로
-- 받는다. 둘은 다른 문제로 보이지만 필요한 길이 같아서("밖에서 안으로 짧은 글 넣기")
-- 길을 두 번 뚫지 않는다.
--
-- ⛔ 이것은 "쓰기 권한을 여는 일"이 아니다 — 표는 밖에서 통째로 잠겨 있고, **정해진 모양의
--    편지만 넣는 함수** 하나만 열린다(이 파일의 다른 공개 기능과 같은 구조). 넣은 사람도
--    자기 편지를 다시 못 읽는다. 읽기는 service_role 만 한다.
-- ⛔ 개인정보 칸이 없다 — 이름·연락처·이메일을 받지 않는다. 받는 순간 처리방침·보관기간·
--    파기절차가 따라붙는데, 아직 아무도 모르는 서비스가 오지도 않은 문의를 위해 법적 의무를
--    먼저 지는 것은 순서가 거꾸로다. 필요해지면 그때 칸을 붙인다.
create table if not exists app_feedback (
  id          bigserial primary key,
  kind        text not null check (kind in ('opinion', 'error')),
  -- 상한은 함수가 자르지만, 함수를 우회하는 길이 생겨도 표가 스스로 지키게 제약을 둔다.
  -- ⛔ **여기 담긴 글을 나중에 화면에 뿌릴 때 그대로 HTML 로 넣지 말 것.** 지금은 읽는
  --    화면이 없어서(dbx.py 로만 본다) 위험이 0 이지만, 관리 화면을 만드는 PR 은 이 표를
  --    처음 보는 사람이 쓸 수 있다. 저장할 때는 아무것도 안 거른다 — 거르는 책임은
  --    **보여주는 쪽**에 있다(2026-08-24 적대검증이 남긴 예고).
  body        text not null check (char_length(body) between 1 and 2000),
  -- 무엇을 보던 중이었나(건물·구·화면). 오류면 브라우저 종류까지.
  -- ⚠️ 모양을 강제하지 않는다 — 담을 칸이 늘 때마다 마이그레이션을 해야 하면 "그냥 안 담는"
  --    선택을 하게 된다. 읽는 쪽에서 없는 칸을 견디게 쓴다.
  context     jsonb,
  created_at  timestamptz not null default now()
);

comment on table app_feedback is
  '화면에서 들어온 짧은 글 한 통. kind=opinion 은 사람이 쓴 의견, kind=error 는 '
  '화면이 죽으며 자동으로 남긴 것. ★ anon 에게 통째로 닫혀 있고 api.submit_feedback() '
  '함수로만 들어온다(넣기 전용 — 넣은 사람도 못 읽는다). 개인정보 칸 없음(2026-08-24b).';

-- 분당 상한을 재는 쿼리가 매번 전수를 훑지 않게 한다.
create index if not exists idx_app_feedback_created on app_feedback (created_at desc);

-- RLS 를 켜되 정책은 하나도 만들지 않는다 = 전부 거부(다른 표와 같은 방식).
alter table app_feedback enable row level security;

-- ⛔ RLS 만 믿지 않는다 — security definer 경로는 RLS 를 우회하므로 권한이 방어선이다.
--    ⚠️ 위쪽 `revoke all on all tables in schema public` 은 그 줄을 지날 때의 표만 닫는
--       일회성 명령이라 여기서 만든 표에는 안 걸린다. 만든 자리에서 다시 닫는다.
revoke all on app_feedback from public, anon, authenticated;
-- bigserial 이 함께 만드는 시퀀스도 닫는다(표만 닫으면 "닫았다"가 반쪽이 된다).
revoke all on sequence app_feedback_id_seq from public, anon, authenticated;

-- 반환값이 boolean 인 이유: void 면 화면이 성공·실패를 모른 채 "보냈습니다"를 띄우게 된다.
create or replace function submit_feedback(
  p_kind    text,
  p_body    text,
  p_context jsonb default null
)
returns boolean
language plpgsql
volatile
security definer
set search_path = public
as $$
declare
  v_kind text := lower(btrim(coalesce(p_kind, '')));
  v_body text := btrim(coalesce(p_body, ''));
  v_ctx  jsonb := p_context;
begin
  -- 예외를 던지지 않고 거짓을 돌려준다 — 오류 기록 경로에서 예외가 나면
  -- **오류를 알리다 오류가 나는** 꼴이 된다.
  if v_kind not in ('opinion', 'error') then
    return false;
  end if;
  if v_body = '' then
    return false;
  end if;

  -- 거절이 아니라 자르기 — 긴 의견을 통째로 버리는 것이 더 나쁘다.
  v_body := left(v_body, 2000);

  -- 곁다리가 너무 크면 곁다리만 버린다. 본문은 살린다.
  if v_ctx is not null and char_length(v_ctx::text) > 4000 then
    v_ctx := null;
  end if;

  -- ⛔ 인터넷에 열린 구멍은 언젠가 봇이 찾는다. "아직 아무도 모른다"는 방어가 아니다.
  --    IP 를 모르므로(PostgREST 뒤라 client_addr 이 프록시다) 전역 상한으로 막는다.
  --
  -- ⛔ **세기와 넣기 사이를 잠그지 않으면 상한이 안 걸린다.** 동시에 들어온 요청들은
  --    각자 자기 시점의 count 를 보므로 서로가 넣는 중이라는 것을 모른 채 전부 통과한다
  --    (READ COMMITTED 기본 격리). 그러면 천천히 보내는 사람만 막히고 **한꺼번에 쏟아붓는
  --    봇은 그대로 지나간다** — 막으려던 상대를 정확히 못 막는다(2026-08-24 적대검증).
  perform pg_advisory_xact_lock(hashtext('app_feedback_rate_limit'));

  -- 분당 상한(2026-08-24b) — 순간적으로 쏟아붓는 것을 막는다.
  if (select count(*) from app_feedback where created_at > now() - interval '1 minute') >= 60 then
    return false;
  end if;

  -- 하루 상한(2026-08-24c) — 분당 상한만으로는 하루 86,400통까지 열려 있다.
  -- 본문 2,000자 + 곁다리 4,000자면 하루 500MB 까지 자랄 수 있는 문이라, 창고 등급을
  -- 생각하면 그대로 둘 수 없다.
  --
  -- ⛔ **"표 전체 총량"으로 막지 않는다.** 총량 상한은 한 번 차면 90일이 지날 때까지
  --    정상 사용자를 **영구히** 막는다 — 봇 한 번에 서비스가 통째로 벙어리가 된다.
  --    하루 창은 하루면 저절로 풀리므로 그 함정이 없다.
  -- ⚠️ 1,000 은 **안전망이지 사업 기준이 아니다.** 지금 실사용은 하루 0~몇 통이라
  --    수백 배 여유다. 주간 알림이 실제 건수를 보여주기 시작하면 그 숫자로 조인다.
  -- ⚠️ 종류별로 따로 센다 — 합쳐서 재면 오류가 쏟아지는 날(정작 알림이 가장 필요한 날)
  --    사람의 의견이 밀려난다.
  if (select count(*) from app_feedback
      where kind = v_kind and created_at > now() - interval '1 day') >= 1000 then
    return false;
  end if;

  insert into app_feedback (kind, body, context) values (v_kind, v_body, v_ctx);

  -- 들어온 김에 오래된 것을 치운다(보관 정책). 예약 장치를 새로 들이지 않고 이미 있는
  -- 길에 얹는다 — 밖에 새 문을 안 여는 가장 싼 방법이다.
  --
  -- ⚠️ 치우다 실패해도 **편지 넣기를 막지 않는다.** 이 함수는 오류 보고 경로이기도 해서
  --    "오류를 알리다 오류가 나면 안 된다"는 원칙이 이미 서 있다. 치우기는 곁다리 살림이고,
  --    그 살림이 실제로 도는지는 get_feedback_stats().oldest_days 가 따로 감시한다
  --    (조용히 삼켜도 눈이 있는 자리다).
  begin
    perform purge_old_feedback();
  exception when others then
    null;
  end;

  return true;
end;
$$;

comment on function submit_feedback(text, text, jsonb) is
  '화면에서 온 짧은 글 한 통을 app_feedback 에 넣는다. 넣었으면 true, 모양이 아니거나 '
  '상한(분당 60 · 종류별 하루 1,000)에 걸리면 false — 예외를 던지지 않는다. 넣은 뒤 '
  '90일 지난 글을 함께 치운다(2026-08-24c). security definer: 표가 anon 에게 통째로 '
  '닫혀 있어 소유자 권한으로 대신 넣는다.';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function submit_feedback(text, text, jsonb) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.submit_feedback(
  p_kind    text,
  p_body    text,
  p_context jsonb default null
)
returns boolean
language sql
volatile
security definer
set search_path = ''
as $$ select public.submit_feedback(p_kind, p_body, p_context) $$;

revoke all on function api.submit_feedback(text, text, jsonb) from public, anon, authenticated;
grant execute on function api.submit_feedback(text, text, jsonb) to anon, authenticated;

-- ⛔ public.submit_feedback 은 끝까지 닫아 둔다 — 통과 함수가 security definer 라
--    소유자 권한으로 부르므로 anon 에게 열 필요가 없다.

-- =====================================================================
-- 의견함 — 주간 건수 알림 · 보관 정책 · 하루 상한 (2026-08-24c)
-- =====================================================================
-- 우편함을 만들어 놓고 **읽을 계기가 없었다.** 매주 건수를 알려 주는 길과, 오래된 글을
-- 스스로 치우는 길을 함께 낸다. 상세한 이유·버린 선택지는
-- supabase/migrations/2026-08-24c_feedback_digest_and_retention.sql 머리말 참조.
--
-- ⛔ 밖으로 새로 열린 것은 api.get_feedback_stats() **하나**뿐이고 **숫자만** 준다.
--    지우는 함수는 밖에 안 연다 — 편지가 들어올 때 submit_feedback 이 스스로 치운다.

-- ── 보관 정책 ────────────────────────────────────────────────────────────────
create or replace function purge_old_feedback()
returns bigint
language plpgsql
volatile
security definer
set search_path = public
as $$
declare
  v_deleted bigint;
begin
  -- ⚠️ 90일은 인자가 아니라 **본문에 박힌 상수**다. 인자로 열어 두면 "유연성"이라는
  --    이름으로 언젠가 최근 글까지 지울 수 있는 문이 된다. 기한을 바꾸려면 이 파일을
  --    고쳐 새 마이그레이션을 내야 한다 — 그 마찰이 방어선이다.
  delete from app_feedback where created_at < now() - interval '90 days';
  get diagnostics v_deleted = row_count;
  return v_deleted;
end;
$$;

comment on function purge_old_feedback() is
  '90일보다 오래된 의견·오류 기록을 지운다(멱등 — 이미 지워졌으면 0). 인자가 없어 그 '
  '기한을 밖에서 바꿀 방법이 없다. ⛔ api 통과 함수를 만들지 않는다 — 밖에서 부를 수 '
  '없어야 한다. 부르는 곳은 submit_feedback 안(편지가 올 때)과 dbx.py(사람) 둘뿐.';

revoke all on function purge_old_feedback() from public, anon, authenticated;

-- ── 주간 알림이 읽는 숫자 ────────────────────────────────────────────────────
create or replace function get_feedback_stats(p_days integer default 7)
returns table(
  opinion_cnt  bigint,   -- 최근 p_days 일 동안 온 사람의 의견
  error_cnt    bigint,   -- 최근 p_days 일 동안 화면이 자동으로 남긴 오류
  total_cnt    bigint,   -- 표에 남아 있는 전부 (보관 정책 덕에 최대 90일치)
  oldest_days  integer   -- 가장 오래된 글의 나이(일). 비어 있으면 NULL
)
language sql
stable
security definer
set search_path = public
as $$
  select
    count(*) filter (
      where kind = 'opinion'
        and created_at > now() - (least(greatest(coalesce(p_days, 7), 1), 90) || ' days')::interval
    ),
    count(*) filter (
      where kind = 'error'
        and created_at > now() - (least(greatest(coalesce(p_days, 7), 1), 90) || ' days')::interval
    ),
    count(*),
    -- ⭐ 이 한 칸이 "치우기가 실제로 도는지"를 지켜본다. 편지가 안 들어오는 동안에는
    --    치우기도 안 돌기 때문에(치우기를 넣기 경로에 얹었다), 이 값이 90을 넘으면
    --    보관 정책이 밀린 것이고 주간 알림이 그 사실로 이슈를 연다.
    (extract(epoch from (now() - min(created_at))) / 86400)::integer
  from app_feedback;
$$;

comment on function get_feedback_stats(integer) is
  '의견함 숫자만 돌려준다 — 최근 p_days(기본 7·1~90 사이로 자름)일 의견/오류 건수, 표 '
  '전체 건수, 가장 오래된 글의 나이(일). ⛔ body·context 는 어떤 칸으로도 안 나간다. '
  '주간 알림 워크플로 전용(2026-08-24c).';

revoke all on function get_feedback_stats(integer) from public, anon, authenticated;

-- api 통과 함수 — 화면이 아니라 GitHub Actions 주간 워크플로가 공개키(anon)로 부른다.
-- ⓘ 공개키는 비밀값이 아니다 — 이미 배포된 화면의 자바스크립트 묶음에 그대로 실려 있어
--   누구나 라이브에서 읽을 수 있다. 워크플로에 둬도 노출면이 늘지 않는다(비밀값 0 유지).
create or replace function api.get_feedback_stats(p_days integer default 7)
returns table(
  opinion_cnt bigint,
  error_cnt   bigint,
  total_cnt   bigint,
  oldest_days integer
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.get_feedback_stats(p_days) $$;

revoke all on function api.get_feedback_stats(integer) from public, anon, authenticated;
grant execute on function api.get_feedback_stats(integer) to anon, authenticated;

-- ⛔ api.purge_old_feedback 은 **일부러 안 만든다.** 지우는 일이 밖에서 불릴 수 있으면,
--    지금은 무해해도 "유연성"을 이유로 인자가 붙는 날 데이터 파괴 창구가 된다.
-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';

-- =====================================================================
-- 국세청 기준시가 — 상업용건물·오피스텔 호실 단위 (2026-08-27a)
-- =====================================================================
-- 국세청이 해마다 1월 1일자로 고시하는 **㎡당 기준시가**를 호실 하나에 한 줄씩 담는다
-- (2026년 판 실측 2,490,451행 · 전국 17개 시도, 포털 3036455). 상세한 실측 근거·버린
-- 선택지는 supabase/migrations/2026-08-27a_nts_base_price.sql 머리말 참조.
--
-- ⛔ **세금을 매길 때 쓰는 과세표준이지, 시장에서 사고파는 값이 아니다** — 화면에서도
--    "국세청 고시 기준시가"라는 이름 그대로 쓴다(절대 규칙 2).
-- ⭐ 층·호실 단위로 값이 매겨진 **유일한 전국 공공자료**다. 실거래가 없는 곳에서도
--    "이 건물 3층은 1층의 몇 할인가"를 말할 수 있는 재료다.
-- ⚠️ 고시가격은 **㎡당 단가**다 — 전 행 분포로 확정했다(중앙값 189만원/㎡. 총액이라면
--    상가 한 칸이 189만원이라는 뜻이 되어 말이 안 된다).
-- ⚠️ **공유면적을 함께 담는다.** 안 담으면 누군가 `고시가격 × 전용면적`으로 총액을 재고
--    공용부만큼 조용히 적게 나온다.
-- ⚠️ 층 구분은 실측 3종(지상층·지하층·**옥탑층 14행**)이다. 옥탑이 14행뿐이라 "둘뿐"으로
--    넘겨짚기 딱 좋은 자리 — 적재기는 모르는 구분값에서 **통째로 멈춘다**.
create table if not exists nts_base_price (
  id              bigserial primary key,
  -- 조립 실패('가,확정예정지번' 11,008행)를 **버리지 않고** 담기 위해 NULL 을 허용한다.
  pnu             char(19),
  -- 원본이 적어 준 법정동코드 그대로(광주 29·전남 46 포함). pnu 는 통합코드 12 로 재코딩된
  -- 값이라, 원본을 잃으면 "우리가 바꾼 것"과 "원래 그랬던 것"을 다시 못 가린다.
  bjd_code_orig   char(10)  not null,
  special_cd      text      not null,   -- '일반지번' / '산' / '가,확정예정지번' (원문 보존)
  bld_nm          text,                 -- 상가건물블록주소 (= 건물 이름)
  dong_nm         text,                 -- 상가건물동주소   (예: '1(단일)')
  floor_no        smallint,             -- 지상 n / 지하 -n / 옥탑 99 / 불명 NULL
  ho              text,                 -- 상가건물호주소 (22행은 비어 있다 → NULL)
  area_m2         numeric(12,2),        -- 전용면적
  common_area_m2  numeric(12,2),        -- 공유면적 (총액을 재려면 전용+공유가 필요하다)
  price_per_m2    numeric(14,2),        -- 고시가격 = ㎡당
  kind            text      not null,   -- 상가종류코드: '상가' / '오피스텔'
  notice_date     date      not null,   -- 고시일자 (2026년 판은 전 행 2026-01-01)
  created_at      timestamptz default now(),
  constraint chk_nts_floor check (floor_no is null or floor_no <> 0)
);

comment on table nts_base_price is
  '국세청 상업용건물·오피스텔 기준시가(호실 단위, 연 1회 고시). 고시가격은 **㎡당 단가**다 '
  '(전 행 분포로 확정 — 중앙값 189만원/㎡). ⛔ 과세표준이지 시세가 아니다. '
  '⛔ anon 에게 통째로 닫혀 있고 list_base_prices() 로만 읽는다. 원본 zip = '
  'data/raw/nts_base_price/ (포털 3036455).';
comment on column nts_base_price.pnu is
  '필지고유번호 19자리. 특수지코드가 ''가,확정예정지번''이면 조립 불가라 NULL(행은 보존).';
comment on column nts_base_price.bjd_code_orig is
  '원본 법정동코드. 광주 29·전남 46 은 우리 DB 통합코드 12 로 재코딩해 pnu 를 만들지만 '
  '이 칸은 원본 그대로 둔다.';
comment on column nts_base_price.floor_no is
  '지상n=n / 지하n=-n / 옥탑=99 / 불명=NULL. ⛔ 0 은 CHECK 로 막는다 — 지하와 결측이 '
  '섞이면 층별 집계가 조용히 오염된다(절대 규칙 4).';
comment on column nts_base_price.price_per_m2 is
  '고시가격(원/㎡). 총액을 재려면 (전용면적 + 공유면적)을 곱해야 한다 — 전용면적만 '
  '곱하면 공용부만큼 적게 나온다.';

-- 화면이 보는 길은 "이 필지의 층별"뿐이다. 필지 하나당 수십~수백 행이라 pnu 만으로 충분하다.
create index if not exists idx_nts_pnu on nts_base_price (pnu);
-- 같은 고시연도를 다시 넣을 때(재적재) 지우는 자리. 249만 행을 전수 훑지 않게 한다.
create index if not exists idx_nts_notice on nts_base_price (notice_date);

-- RLS 를 켜되 정책은 하나도 만들지 않는다 = 전부 거부(다른 표와 같은 방식).
alter table nts_base_price enable row level security;

-- ⛔ RLS 만 믿지 않는다 — security definer 경로는 RLS 를 우회하므로 권한이 방어선이다.
--    ⚠️ 위쪽 `revoke all on all tables in schema public` 은 그 줄을 지날 때의 표만 닫는
--       일회성 명령이라 여기서 만든 표에는 안 걸린다. 만든 자리에서 다시 닫는다.
revoke all on nts_base_price from public, anon, authenticated;
-- bigserial 이 함께 만드는 시퀀스도 닫는다(표만 닫으면 "닫았다"가 반쪽이 된다).
revoke all on sequence nts_base_price_id_seq from public, anon, authenticated;

-- ⛔ api 쪽 pass-through 뷰를 **일부러 안 만든다** — 적재기는 psql(dbx.py)로만 다루므로
--    REST 경로가 필요 없고, 안 만드는 것이 곧 노출면을 줄이는 일이다.

-- ── list_base_prices — 이 필지의 층별 기준시가 ────────────────────────────────
-- 층 하나에 한 줄. 값이 없으면 **줄이 아예 없다**(0 을 만들어 내지 않는다).
--
-- ⛔ **'상가' 종류만 센다.** 같은 건물에 오피스텔(1,331,606행)과 상가(1,158,845행)가 섞여
--    있는데, 오피스텔은 주거 가격이라 함께 중앙값을 내면 상가 값이 통째로 끌려간다.
--    실측 예: 신부파스칼텔 1층 상가 290만원/㎡ ↔ 2층 오피스텔 184만원/㎡.
-- ⛔ **여러 해가 쌓여도 한 해만 본다.** 필터 없이 묶으면 2026년과 2027년 값의 중앙값이라는
--    뜻 없는 숫자가 나온다. 그 필지에 있는 **가장 최근 고시일자**만 골라 그 안에서 센다.
-- ⚠️ 파라미터를 p_ 로 시작하는 이유: `pnu` 는 컬럼 이름과 겹친다. 겹치면 PostgreSQL 이
--    컬럼을 우선 집어 `where n.pnu = n.pnu`(= 전 국토)가 된다(list_price_bands 와 같은 함정).
create or replace function list_base_prices(p_pnu text)
returns table (
  floor_no             smallint,
  median_price_per_m2  numeric,
  ho_cnt               int,
  notice_date          date
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  -- ⛔ **파라미터를 그대로 쓰지 말 것.** 서명은 text 인데 pnu 컬럼은 char(19) 다.
  --    `char컬럼 = text파라미터` 는 컬럼 쪽이 text 로 캐스트돼 **인덱스가 통째로 무력해진다**
  --    (2026-08-16b 라이브 실측: 459.8ms ↔ 0.796ms). 서명은 text 로 두고(PostgREST 가 보내는
  --    값이 text 다) 안에서 char(19) 로 받아 쓴다.
  v_pnu  char(19) := p_pnu;
  v_date date;
begin
  select max(n.notice_date) into v_date
    from nts_base_price n
   where n.pnu = v_pnu and n.kind = '상가';

  -- 이 필지에 상가 기준시가가 없다 = 줄 0개. 빈 목록과 "0원"은 다른 말이다.
  if v_date is null then
    return;
  end if;

  return query
    select n.floor_no,
           -- percentile_cont 는 numeric 을 double precision 으로 받아 계산한다. 고시가격은
           -- 원 단위 정수이므로 소수점을 남길 이유가 없어 되돌릴 때 반올림한다.
           round(percentile_cont(0.5) within group (order by n.price_per_m2)::numeric, 0),
           count(*)::int,
           v_date
      from nts_base_price n
     where n.pnu = v_pnu
       and n.kind = '상가'
       and n.notice_date = v_date
       and n.price_per_m2 is not null
     group by n.floor_no
     -- 위층이 먼저 — 층별 스택 화면과 같은 순서(높은 층이 위).
     order by n.floor_no desc nulls last;
end;
$$;

comment on function list_base_prices(text) is
  '이 필지의 층별 국세청 기준시가 — 층, ㎡당 고시가격 중앙값, 호실 수, 고시일자. '
  '⛔ 종류가 ''상가''인 호실만 센다(오피스텔은 주거 가격이라 섞으면 상가 값이 끌려간다). '
  '⛔ 그 필지의 가장 최근 고시일자 한 해만 본다. 값이 없으면 줄이 없다(0 을 만들지 않는다).';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function list_base_prices(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.list_base_prices(p_pnu text)
returns table (
  floor_no             smallint,
  median_price_per_m2  numeric,
  ho_cnt               int,
  notice_date          date
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_base_prices(p_pnu) $$;

revoke all on function api.list_base_prices(text) from public, anon, authenticated;
grant execute on function api.list_base_prices(text) to anon, authenticated;

-- ⛔ public.list_base_prices 는 끝까지 닫아 둔다 — 통과 함수가 security definer 라
--    소유자 권한으로 부르므로 anon 에게 열 필요가 없다.

-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';

-- =====================================================================
-- LH 상가 공고 알림판 (2026-08-28a)
-- =====================================================================
-- LH 가 내는 분양·임대 **상가** 공고를 받아 두고, 지금 살아 있는 것만 화면에 보여 준다
-- (포털 lhLeaseNoticeInfo1 · UPP_AIS_TP_CD='22'). 1년 창 실측 531건(전체 2,913건 중,
-- 2026-08-28). 상세한 실측 근거·버린 선택지는
-- supabase/migrations/2026-08-28a_lh_notice.sql 머리말 참조.
--
-- ⛔ **마감된 공고를 지우지 않는다** — 숨기는 일은 읽는 함수가 한다. 지우면 "이 지역에
--    상가 공고가 얼마나 자주 뜨는가"를 나중에 셀 수 없고, 그 값은 다른 어떤 자료로도
--    못 만든다.
-- ⛔ **호실 목록·가격 칸이 없다** — 같은 기관의 공급정보 API 가 상가 공고에는 빈 응답을
--    준다(2026-08-27 실측 2건). 상세는 dtl_url(LH 공고문)로 보낸다.
-- ⚠️ '전국' 공고(531건 중 59건)는 지역이 없는 게 아니라 **모든 지역**이라, NULL 이 아니라
--    is_nationwide 로 담는다 — 그러지 않으면 어느 지역에서도 안 보인다.
create table if not exists lh_notice (
  -- LH 공고 식별자. **숫자가 아니다** — '0000061158'·'BN-0001342'·'LN-…' 가 섞여 있다.
  pan_id         text primary key,
  pan_nm         text not null,
  -- 종류: 코드 · 화면용 짧은 이름 · **원문 이름**을 다 남긴다. 짧은 이름은 우리가 지은
  -- 말이라, 원문이 없으면 LH 가 종류를 늘렸을 때 대조할 근거가 사라진다.
  -- 실측 4종: 23 분양ㆍ(구)임대상가(입찰) / 24 임대상가(추첨) / 43 임대상가(입찰) /
  --           38 임대상가(공모ㆍ심사)
  kind_cd        text not null,
  kind_nm        text not null,
  kind_nm_src    text not null,
  spl_inf_tp_cd  text,                  -- 공급정보 구분코드(220·221·223·224)
  cnp_nm         text,                  -- LH 가 적어 준 지역 이름 그대로('경기도'·'전국')
  sido_code      char(2),               -- 우리 시도코드로 옮긴 것. 못 옮겼으면 NULL(수집기가 경고)
  is_nationwide  boolean not null default false,
  -- ⛔ 상태에 CHECK 를 걸지 않는다 — LH 가 새 상태를 쓰는 날 수집이 통째로 멈춘다.
  --    실측 5종(접수마감·상담요청·공고중·정정공고중·접수중).
  pan_ss         text,
  notice_date    date,                  -- 원본 '2026.08.27' 을 날짜로. 비어 있을 수 있다
  close_date     date,
  dtl_url        text,
  collected_at   timestamptz not null default now()
);

comment on table lh_notice is
  'LH 분양·임대 상가 공고 목록(포털 lhLeaseNoticeInfo1, UPP_AIS_TP_CD=22 만). '
  '⛔ 마감된 공고도 지우지 않는다 — 숨기는 일은 list_lh_notices() 가 한다. '
  '⛔ anon 에게 통째로 닫혀 있고 list_lh_notices() 로만 읽는다. '
  '⛔ 호실 목록·가격은 없다(공급정보 API 가 상가에는 빈 응답 — 2026-08-27 실측).';
comment on column lh_notice.pan_id is
  'LH 공고 식별자. 숫자가 아니다 — ''0000061158''·''BN-0001342''·''LN-…'' 가 섞여 있다.';
comment on column lh_notice.sido_code is
  '시도 2자리. LH 지역명을 옮긴 값이며 옮기지 못했으면 NULL(수집기가 경고한다). '
  '''전국''은 NULL 이 아니라 is_nationwide=true 로 담는다.';
comment on column lh_notice.kind_nm_src is
  'LH 원문 종류명. kind_nm 은 화면용으로 우리가 줄인 말이라, 원문이 있어야 나중에 '
  'LH 가 종류를 늘렸을 때 대조할 수 있다.';

create index if not exists idx_lh_notice_close on lh_notice (close_date);
create index if not exists idx_lh_notice_sido on lh_notice (sido_code);

alter table lh_notice enable row level security;

-- ⛔ 위쪽의 `revoke all on all tables in schema public` 은 그 줄을 지날 때의 표만 닫는
--    일회성 명령이라 여기서 만든 표에는 안 걸린다. 만든 자리에서 다시 닫는다.
revoke all on lh_notice from public, anon, authenticated;

-- ── list_lh_notices — 이 지역에서 지금 살아 있는 공고 ─────────────────────────
-- ⛔ 마감 지난 것을 여기서 뺀다(창고에는 남는다). 화면이 스스로 거르게 두면 언젠가 한
--    화면이 그 규칙을 빠뜨리고, 그날 사용자는 끝난 공고를 보고 헛걸음한다.
-- ⛔ 마감일을 **모르는** 공고(NULL)는 빼지 않는다 — 모른다고 숨기면 살아 있는 공고가
--    조용히 사라진다. 정렬에서 맨 뒤로 보낸다.
-- ⛔ **본문을 여기서 손보지 말 것 — 마이그레이션이 정본이다.**
--    함수 본문 주석은 `pg_proc.prosrc` 에 그대로 실려 **라이브에서 읽힌다.** 즉 여기서
--    주석 한 줄만 다듬어도 그 순간 정본↔라이브가 어긋난다(2026-09-01 2차 검증에서 실제로
--    5줄이 어긋나 있었다 — 드리프트를 잡겠다는 작업이 같은 드리프트를 남긴 것이다).
--    아래 블록은 `supabase/migrations/2026-09-05c_lh_fold_and_dedupe.sql` 에서 **글자 그대로**
--    복사한 것이고, tests/test_schema_function_drift.py 가 그 일치를 지킨다.
--    바꿀 일이 생기면 **새 마이그레이션 파일**을 만들고 그 본문을 여기 복사한다.
--
-- 배경 설명(본문에 넣으면 라이브와 어긋나므로 여기 둔다):
--  · 시간축: now()(timestamptz) → at time zone 'Asia/Seoul'(서울 벽시계) → ::date(서울
--    달력 날짜). 이 DB 의 TimeZone 은 UTC 이고 어느 롤에도 재정의가 없다(실측).
--    STABLE 이라 idx_lh_notice_close 를 그대로 탄다. 마이그레이션 2026-09-01a.
--  · 2026-09-01c: 본문 주석이 "NULL 마감일은 여전히 뺀다"로 적혀 **코드와 반대말**을
--    하고 있었다(코드는 남긴다). 01a 를 제자리에서 고치지 않고 새 파일로 정정했다 —
--    그 문구가 라이브 prosrc 에 그대로 있어 01a 는 그 시점 라이브를 정확히 재현하기 때문.
--  · 2026-09-01d: '접수마감'은 마감일과 무관하게 뺀다. 이 표는 pan_ss 에 CHECK 를 안 걸어
--    두었으므로 **허용 목록**으로 바꾸면 새 상태가 오는 날 살아 있는 공고가 통째로 사라진다.
--  · 2026-09-05c: 칸 둘(is_nationwide·dup_cnt)을 함께 준다. is_nationwide 는 **LH 가 지역을
--    '전국'이라 적었다**는 뜻이고(수집기 map_sido 실측 — 빈 칸은 false 다), 화면은 그 줄들을
--    접어 두되 **제목으로 지역을 추측하지 않는다**(결재 ①). dup_cnt 는 대괄호 표시·공백을
--    지운 제목이 같은 줄이 몇이었나이며, 그중 최신 한 줄만 나간다(결재 ②). 상한 200 은
--    형제 list_district_buildings 와 같은 자릿수다(상한 없는 목록 함수는 자료가 늘 때 위험).
create or replace function list_lh_notices(p_sido text)
returns table (
  pan_id        text,
  pan_nm        text,
  kind_nm       text,
  pan_ss        text,
  notice_date   date,
  close_date    date,
  dtl_url       text,
  collected_at  timestamptz,
  is_nationwide boolean,
  dup_cnt       int
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  -- ⛔ 파라미터를 그대로 쓰지 않는다 — 서명은 text 인데 컬럼은 char(2) 라, 그대로 비교하면
  --    컬럼 쪽이 캐스트돼 인덱스가 무력해진다(2026-08-16b 와 같은 함정).
  -- ⚠️ 앞 2자리만 쓴다 — 화면의 지역 고르개는 시군구 코드(11680)를 들고 있다.
  v_sido char(2) := nullif(left(btrim(coalesce(p_sido, '')), 2), '');
begin
  return query
    with alive as (
      -- ⛔ kind_cd 는 화면에 안 나가지만 **묶는 열쇠의 절반**이라 여기서 함께 든다
      --    (아래 partition 참조). 빼면 분양과 임대가 한 줄로 합쳐진다.
      select n.pan_id, n.pan_nm, n.kind_nm, n.kind_cd, n.pan_ss,
             n.notice_date, n.close_date, n.dtl_url, n.collected_at, n.is_nationwide,
             -- ⛔ 같은 공고를 묶는 열쇠(2026-09-05c). **대괄호 표시와 공백을 둘 다** 지운다 —
             --    재게시는 `[정정공고]` 가 붙거나 띄어쓰기가 달라지는 두 가지로 흔들려서,
             --    하나만 지우면 라이브에서 60·62 가 나왔다(둘 다 지우면 59 — 2026-09-01 실측).
             -- ⛔ 여기서 제목을 더 뭉개지 말 것 — 열쇠가 헐거워지면 **서로 다른 공고가 합쳐져**
             --    사용자가 못 보는 공고가 생긴다(여러 줄로 세는 것보다 나쁘다).
             regexp_replace(n.pan_nm, '\[[^]]*\]|\s+', '', 'g') as norm_key
        from lh_notice n
       where ((v_sido is not null and n.sido_code = v_sido) or n.is_nationwide)
         -- ⛔ `current_date` 로 되돌리지 말 것 — 이 DB 는 UTC 라 한국 새벽에 끝난 공고가
         --    아침 9시까지 남는다(2026-09-01a 머리말).
         -- ⛔ 마감일을 **모르는** 것(NULL)은 이 판정에서 **제외한다 = 그대로 남긴다.**
         --    모른다 ≠ 끝났다 — 모른다고 숨기면 살아 있는 공고가 조용히 사라진다.
         and (n.close_date is null or n.close_date >= (now() at time zone 'Asia/Seoul')::date)
         -- ⛔ LH 가 **끝났다고 적어 준 것**은 마감일과 무관하게 뺀다(2026-09-01d).
         --    마감일이 먼 미래로 적힌 공고는 날짜 필터가 원리적으로 못 거른다 —
         --    실측으로 '접수마감'인데 마감일 2028-12-31 인 것이 2건 있었고 하나는 [취소공고]다.
         -- ⛔ **허용 목록으로 바꾸지 말 것** — 새 상태가 생기는 날 살아 있는 공고가 통째로
         --    사라진다(표 정의가 CHECK 를 안 건 것과 같은 이유). 모르는 상태는 통과시킨다.
         and (n.pan_ss is null or n.pan_ss <> '접수마감')
    ),
    ranked as (
      -- 같은 열쇠(**종류 + 정규화 제목**) 안에서 **최신 한 줄만** 남긴다(rn=1). 최신은
      -- 공고일 → 받아 둔 시각 → pan_id 순으로 정한다 — 마지막 pan_id 까지 두는 것은
      -- 같은 질문에 매번 같은 답이 나오게 하기 위해서다(정렬 기준이 부족하면 흔들린다).
      -- ⛔ 종류(kind_cd)를 partition 에서 빼지 말 것 — 분양과 임대는 제목이 같아도 다른
      --    물건이라 합치면 하나가 화면에서 사라진다(창고 전체 실측 417 vs 419 = 2쌍).
      -- dup_cnt = **나 말고 몇 줄이 더 있었나**(0 이면 재게시 없음). 화면은 이 값이 있을
      -- 때만 "정정·재게시 N회"를 적는다.
      select a.*,
             row_number() over (partition by a.kind_cd, a.norm_key
                                    order by a.notice_date desc nulls last,
                                             a.collected_at desc,
                                             a.pan_id desc) as rn,
             (count(*) over (partition by a.kind_cd, a.norm_key) - 1)::int as dup_cnt
        from alive a
    )
    -- ⚠️ 바깥 별칭을 `n` 으로 둔다 — 아래 정렬이 `n.close_date` 로 읽혀야 마감 임박순 가드
    --    (tests/test_lh_notice_migration.py)가 옛 판들과 **같은 글자**로 이 함수를 지킨다.
    select n.pan_id, n.pan_nm, n.kind_nm, n.pan_ss,
           n.notice_date, n.close_date, n.dtl_url, n.collected_at,
           n.is_nationwide, n.dup_cnt
      from ranked n
     where n.rn = 1
     order by n.close_date asc nulls last, n.notice_date desc nulls last, n.pan_id
     -- ⛔ 상한을 없애지 말 것(2026-09-05c) — 형제 list_district_buildings 와 같은 자릿수다.
     --    닿으면 조용히 잘리는 쪽은 마감이 먼 것·마감일 미상이다. 닿기 시작하면 상한을
     --    늘릴 게 아니라 페이지를 만들 때다.
     limit 200;
end;
$$;

-- ⛔ 이 코멘트는 라이브·마이그레이션과 **글자 그대로 같아야 한다.** 2026-09-01a 가 본문만
--    정본에 옮기고 코멘트를 빠뜨려, **드리프트를 잡는 작업이 새 드리프트를 만들었다**
--    (라이브 195자 vs 정본 2문장 — 같은 날 적대검증에서 잡혔다). 회귀 가드는
--    tests/test_lh_notice_migration.py 의 코멘트 대조 시험이다.
comment on function list_lh_notices(text) is
  '이 지역에서 지금 살아 있는 LH 상가 공고(마감 지난 것은 뺀다 — 창고에는 남아 있다). '
  '''전국'' 공고는 어느 지역을 골라도 함께 나온다. 시군구 코드를 넘겨도 앞 2자리로 본다. '
  '⛔ 마감 판정은 **한국 날짜**다(2026-09-01a) — DB 세션이 UTC 라 current_date 를 쓰면 '
  '한국 새벽 0~9시에 어제 끝난 공고가 남는다. '
  '⛔ LH 가 ''접수마감''이라 적은 것은 마감일과 무관하게 뺀다(2026-09-01d) — '
  '마감일이 먼 미래인 공고는 날짜만으로는 영영 못 거른다. '
  '⛔ is_nationwide 는 **LH 가 지역을 ''전국''이라 적었다**는 뜻이다(칸이 빈 것이 아니다) — '
  '화면은 그 줄들을 접어 두고 제목으로 지역을 추측하지 않는다(2026-09-05c). '
  '⛔ **종류가 같고** 대괄호 표시·공백을 지운 제목이 같으면 **최신 한 줄만** 주고 dup_cnt 로 나머지 수를 '
  '알린다(2026-09-05c) — 재게시는 새 pan_id 를 받아 같은 물건이 여러 줄이 된다. '
  '⛔ 200건에서 끊는다(2026-09-05c) — 상한 없는 목록은 자료가 늘 때 창고·화면을 함께 끈다.';

revoke all on function list_lh_notices(text) from public, anon, authenticated;

create or replace function api.list_lh_notices(p_sido text)
returns table (
  pan_id        text,
  pan_nm        text,
  kind_nm       text,
  pan_ss        text,
  notice_date   date,
  close_date    date,
  dtl_url       text,
  collected_at  timestamptz,
  is_nationwide boolean,
  dup_cnt       int
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_lh_notices(p_sido) $$;

revoke all on function api.list_lh_notices(text) from public, anon, authenticated;
grant execute on function api.list_lh_notices(text) to anon, authenticated;

-- ⛔ public.list_lh_notices 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.

-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';

-- =====================================================================
-- 건축인허가 — 곧 올라오는 건물 (2026-08-28b)
-- =====================================================================
-- 건축 허가를 받았지만 **아직 사용승인이 안 난** 건물이다(건축HUB 분류 01·opnTaskCd 0101,
-- 전국·월간). 한 줄에 허가일·착공일·사용승인일이 같이 있어서 **사용승인일이 빈 칸이면
-- 아직 안 지어진 건물**이라는 뜻이 된다. 2026-07 판 실측: 원본 6,498,901행 → 적재 대상
-- 556,527행(그중 착공 61,332). 실측 근거·버린 선택지는
-- supabase/migrations/2026-08-28b_arch_permit.sql 머리말 참조.
--
-- ⚠️ **월 1회 수동 갱신**이고, 원본은 건축HUB 에 최근 3개월치만 남는다 — 받은 zip 은
--    `python scripts/backup_raw.py` 로 백업할 것(절대 규칙 6 과 같은 이유).
-- ⛔ **PK 가 두 칸인 이유**: 같은 허가건이 달마다 다시 나오므로, 한 칸짜리 PK 로 두면
--    다음 달 적재가 PK 충돌로 통째로 실패한다. 읽는 함수는 가장 최근 기준월만 본다.
-- ⛔ **mgm_pmsrgst_pk 는 text 다** — 22자리 값이 있어 bigint 를 넘친다(원본도 VARCHAR(33)).
-- ⛔ 용도로 거르지 않고 다 담는다 — 무엇을 상가로 볼지는 읽는 함수 한 곳에서만 정한다.
create table if not exists arch_permit (
  -- 관리_허가대장_PK. **숫자로 담지 않는다** — 22자리가 있어 bigint 를 넘는다.
  mgm_pmsrgst_pk  text      not null,
  -- 기준월(YYYYMM). 달마다 한 벌이 쌓이고, 읽는 함수는 가장 최근 한 벌만 본다.
  loaded_ym       char(6)   not null,
  -- 조립 실패(블록·특수지번 등)를 **버리지 않고** 담기 위해 NULL 을 허용한다.
  pnu             char(19),
  sigungu_cd      char(5),
  plat_plc        text,                   -- 대지 위치(지번 주소 원문)
  arch_gb_nm      text,                   -- 신축·증축·개축 …
  main_purps_cd   text,                   -- 주용도 코드(5자리). 앞 두 글자가 대분류다
  main_purps_nm   text,
  tot_area        numeric(19,9),          -- 연면적(㎡)
  arch_pms_day    date      not null,     -- 필터가 유효한 최근 날짜만 통과시킨다
  real_stcns_day  date,                   -- 실제 착공일. 있으면 **땅을 파기 시작한 것**
  -- 담는 행은 전부 NULL 이다(그것이 곧 '미준공'이다). 적재 SQL 이 다시 확인한다.
  use_apr_day     date,
  crtn_day        date,                   -- 원본 생성일자
  created_at      timestamptz default now(),
  primary key (mgm_pmsrgst_pk, loaded_ym)
);

comment on table arch_permit is
  '건축인허가 기본개요 중 **아직 사용승인이 안 난 최근 허가분**(건축HUB 분류 01·0101, 전국 월간). '
  '2026-07 판 실측 556,527행(원본 6,498,901행에서). 달마다 한 벌이 쌓이며 읽는 함수는 가장 '
  '최근 기준월만 본다. ⛔ anon 에게 통째로 닫혀 있고 count_nearby_permits() 로만 읽는다 — '
  '그것도 개수만 나간다(건물 주소·이름은 한 글자도 안 나간다). '
  '⚠️ 원본은 건축HUB 에 최근 3개월치만 남는다 — 받은 zip 은 backup_raw.py 로 백업할 것.';
comment on column arch_permit.mgm_pmsrgst_pk is
  '관리 허가대장 PK. **text 다** — 22자리 값이 있어 bigint 를 넘친다(원본도 VARCHAR(33)).';
comment on column arch_permit.loaded_ym is
  '원본 파일의 기준월(YYYYMM). 같은 허가건이 달마다 다시 나오므로 PK 의 한 칸이다 — '
  '한 칸짜리 PK 로 두면 다음 달 적재가 PK 충돌로 통째로 실패한다.';
comment on column arch_permit.use_apr_day is
  '사용승인일. 이 표에서는 **항상 NULL** 이다(그것이 곧 미준공이라는 뜻) — 값이 생기면 '
  '적재 관문이 통째로 되돌린다.';
comment on column arch_permit.real_stcns_day is
  '실제 착공일. 있으면 이미 공사가 시작된 것이라 "곧"이 더 가깝다는 뜻이다.';

-- 읽는 길은 "이 필지들 중 상가 미준공 몇 곳"뿐이다. 그래서 pnu 로 찾고, 세는 데 필요한
-- 칸을 **include 로 함께 실어** 힙에 안 가게 한다(idx_ub_pnu_cat 과 같은 처방).
-- ⛔ include 네 칸을 지우지 말 것 — 지워도 **에러는 안 나고 느려지기만 한다**.
create index if not exists idx_arch_permit_pnu on arch_permit (pnu)
  include (loaded_ym, use_apr_day, main_purps_cd, real_stcns_day);

-- 같은 기준월을 다시 넣을 때(월 1회 갱신) 지우는 자리. 55만 행을 전수 훑지 않게 한다.
create index if not exists idx_arch_permit_ym on arch_permit (loaded_ym);

alter table arch_permit enable row level security;

-- ⛔ 위쪽의 `revoke all on all tables in schema public` 은 그 줄을 지날 때의 표만 닫는
--    일회성 명령이라 여기서 만든 표에는 안 걸린다. 만든 자리에서 다시 닫는다.
revoke all on arch_permit from public, anon, authenticated;

-- ── count_nearby_permits — 둘레에 곧 올라올 상가 건물이 몇 곳인가 ─────────────
-- 한 줄만 돌려준다: 전체 곳수 · 그중 이미 착공한 곳수 · 그중 2년 넘게 착공
-- 기록이 없는 곳수(2026-09-05b) · 어느 달 자료인가.
--
-- 무엇을 '상가'로 보나 (2026-07 판 적재 대상 556,527행 실측 분포가 근거다):
--   03 제1종근린생활 24,952 · 04 제2종근린생활 39,882 · 07 판매 1,617 · 14 업무 5,967
--   = 72,419곳(적재 대상의 13.0%). 앞 두 글자로 보므로 `04005 제조업소` 같은 하위 코드도
--   저절로 따라온다.
-- 일부러 뺀 것: 15 숙박·16 위락·27 관광휴게(상가 축이 아니다) · 17 공장·18 창고(산업물류) ·
--   01·02 주택(주거) · **주용도가 빈 값 389,822행(70%)**(모르는 것을 상가라고 부르지 않는다 —
--   세면 화면 숫자가 대여섯 배로 부푼다).
--
-- ⛔ 좌표가 없으면 **줄을 아예 안 돌려준다**. 0 을 돌려주면 "둘레에 아무것도 안 생긴다"는
--    단정이 되는데 사실은 모르는 것이다(list_industry_mix 와 같은 원칙).
create or replace function count_nearby_permits(p_pnu text)
returns table (
  total_cnt    int,
  started_cnt  int,
  stale_cnt    int,
  base_ym      text
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  -- ⛔ **파라미터를 그대로 쓰지 말 것.** 서명은 text 인데 pnu 컬럼은 char(19) 다.
  --    `char컬럼 = text파라미터` 는 컬럼 쪽이 캐스트돼 **인덱스가 통째로 무력해진다**
  --    (2026-08-16b 라이브 실측: 459.8ms ↔ 0.796ms).
  v_pnu char(19) := p_pnu;
  v_ym  char(6);
  -- 기준월의 **말일**. '2년 넘게 미착공'을 재는 자다 — 오늘이 아니라 **자료가
  -- 말하는 시점**이다. 이 표는 그 달의 상태를 찍은 것이라, 오늘로 재면 자료가
  -- 보지 못한 시간까지 섞어 세게 된다.
  v_month_end date;
begin
  select max(a.loaded_ym) into v_ym from arch_permit a;
  -- 아직 한 번도 안 담았다 = 줄 0개. "0곳"과 "모른다"는 다른 말이다.
  if v_ym is null then
    return;
  end if;
  v_month_end := (to_date(v_ym, 'YYYYMM') + interval '1 month' - interval '1 day')::date;

  return query
    with me as (
      select p.geom::geography as gg
        from parcel p
       where p.pnu = v_pnu and p.geom is not null
    ),
    near as (
      -- ⚠️ char(19)[] 이라야 한다. text[] 로 두면 배열 조건이 인덱스 안으로 못 들어가
      --    힙 필터로 밀린다(list_industry_mix 주석의 실측과 같은 병).
      -- 마지막 인자 false = 구면으로 잰다. 형제 함수들과 같은 자를 쓴다.
      select coalesce(array_agg(p.pnu), '{}'::char(19)[]) as pnus
        from parcel p cross join me
       where p.geom is not null
         and st_dwithin(p.geom::geography, me.gg, 500, false)
    ),
    hit as (
      -- ⛔ 허가일은 **세는 데만** 쓴다. 밖으로 나가는 것은 여전히 개수뿐이다.
      select a.real_stcns_day, a.arch_pms_day
        from arch_permit a cross join near
       where a.pnu = any(near.pnus)
         and a.loaded_ym = v_ym
         -- 표에는 미준공만 담기지만 규칙을 한 군데에만 두지 않는다 — 언젠가 누가 완공분까지
         -- 담기로 해도 이 화면은 계속 '곧 올라올 것'만 말해야 한다.
         and a.use_apr_day is null
         and left(a.main_purps_cd, 2) = any(array['03', '04', '07', '14'])
    )
    select (select count(*) from hit)::int,
           (select count(*) from hit where hit.real_stcns_day is not null)::int,
           -- ⛔ **재는 자는 기준월의 말일이다 — 오늘이 아니다.** 자료가 그 달
           --    상태라, 오늘로 재면 자료가 보지 못한 시간까지 섞어 세게 된다.
           -- ⛔ **빼는 수가 아니다.** 위 전체 곳수 안에 들어 있는 부분집합이다.
           -- ⛔ **'실효됐다'가 아니다.** 원본에 실효 칸이 아예 없어, 우리가 아는
           --    것은 '그 달 자료에 착공 기록이 없다'까지다(사장님 결재 2026-09-05).
           --    부등호도 **넘는 것만** 센다 — 딱 2년은 아직 아니다.
           (select count(*) from hit
             where hit.real_stcns_day is null
               and hit.arch_pms_day < (v_month_end - interval '2 years')::date)::int,
           v_ym::text
     where exists (select 1 from me);
end;
$$;

comment on function count_nearby_permits(text) is
  '이 필지에서 반경 500m 안에 **곧 올라올 상가 건물**이 몇 곳인가 — 전체 곳수, 그중 이미 '
  '착공한 곳수, 자료의 기준월. 대상은 사용승인이 안 난 최근(2023-01-01 이후) 허가분 중 '
  '주용도 대분류가 03(1종근생)·04(2종근생)·07(판매)·14(업무)인 것뿐이다. '
  '⛔ 주용도가 빈 값인 허가는 세지 않는다(모르는 것을 상가라고 부르지 않는다). '
  '⛔ 필지 좌표가 없으면 줄을 아예 안 돌려준다 — 0 곳과 "모른다"는 다른 말이다. '
  'security definer — arch_permit·parcel 이 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '**나가는 것은 개수와 기준월뿐이다 — 건물 주소·이름은 한 글자도 안 나간다.** '
  '2026-09-05b: stale_cnt = 그중 **기준월 말일 기준으로 허가 후 2년 넘게 착공 기록이 '
  '없는** 곳수(전체 곳수 안에 들어 있는 부분집합이다). ⛔ "허가가 실효됐다"는 뜻이 '
  '아니다 — 원본에 실효 칸이 없어 단정하지 않는다.';

revoke all on function count_nearby_permits(text) from public, anon, authenticated;

create or replace function api.count_nearby_permits(p_pnu text)
returns table (
  total_cnt    int,
  started_cnt  int,
  stale_cnt    int,
  base_ym      text
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.count_nearby_permits(p_pnu) $$;

revoke all on function api.count_nearby_permits(text) from public, anon, authenticated;
grant execute on function api.count_nearby_permits(text) to anon, authenticated;

-- ⛔ public.count_nearby_permits 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.

-- =====================================================================
-- 함수: list_rent_stats — 이 땅이 속한 상권의 임대 조사값 (2026-08-31a · 결정 0024)
-- =====================================================================
-- `rent_stat` 은 2026-08-09 에 7,232행이 들어왔는데 **읽는 코드가 0줄**이었다. 이 함수
-- 하나가 층별 화면의 여섯 번째 카드를 먹인다.
--
-- ⛔ **역산하지 않는다.** 절대 규칙 5 는 임대료를 부동산원 수익률·층별효용비율로 역산하라고
--    하지만, 그 역산은 백테스트와 재결재를 거친 뒤의 일이다(결정 0013 이 매매에 그렇게 했다).
--    이 함수는 조사값을 **그대로** 나른다 — 곱하지도, 나누지도, 층으로 펴지도 않는다.
--    그래서 나가는 값에 `floor_util_ratio` 가 없다(있으면 화면이 언젠가 곱하게 된다).
--
-- ## 왜 상권을 거쳐 가나
--
-- rent_stat 의 지역 축은 시군구가 아니라 **상권**이다(같은 강남 안에서도 상권마다 값이
-- 다르다). 그래서 필지 → 상권(공간) → district_rone_map(이름) → rent_stat 으로 두 번
-- 건너간다. 이을 근거가 없으면 **줄이 아예 없다** — 시·도 평균으로 메우지 않는다.
-- 부동산원 표본이 닿지 않는 자리가 실제로 훨씬 많고(전국 상권 중 조사 대상은 일부다),
-- 그 자리에 상위 평균을 적으면 조사하지 않은 곳을 조사한 것처럼 말하게 된다.
--
-- ## 왜 (경로, 종류)마다 최신 분기를 따로 고르나
--
-- 전체 최신 분기 하나로 잘라 내면, 그 분기에 그 종류의 표본이 없는 상권에서 **그 종류가
-- 통째로 사라진다**(사용자에게는 "오피스는 조사 안 하는 동네"로 보인다). 줄마다 분기를
-- 함께 내보내므로 화면은 각 줄이 언제 것인지 정직하게 적을 수 있다.
--
-- ⚠️ 한 상권이 R-ONE 경로를 **둘까지** 가진다(district_rone_map 의 PK 가 복합인 이유 —
--    부동산원이 bld_type 마다 서울 권역 분할을 달리한다). 그래서 조인이 상권당 여러 줄을
--    낼 수 있고, 그 줄들은 **서로 다른 조사구역의 값**이다 — 화면이 조사구역 이름을 함께
--    적어야 사람이 그 사실을 알 수 있다.
-- ⛔ 종류(bld_type)끼리 더하거나 평균 내지 않는다 — 모집단이 다른 네 조사다.
-- ⚠️ `rent_stat` 에는 region_nm 인덱스가 없지만 표가 7,232행뿐이라 그대로 훑는다.
--    표가 자릿수 단위로 커지면 그때 인덱스를 만든다(지금 만들면 쓰지도 않을 것을 지킨다).
-- ⛔ `p_pnu::char(19)` 캐스트를 지우지 말 것 — 컬럼이 char(19) 라 text 와 견주면 **컬럼 쪽**이
--    캐스트돼 인덱스가 통째로 죽는다(2026-08-16b 실측 459.8ms↔0.796ms).
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

-- ⛔ public.list_rent_stats 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.

-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';

-- =====================================================================
-- 함수: list_district_buildings / list_parcel_buildings — 상권 → 건물 다리
-- =====================================================================
-- 마이그레이션 2026-08-31b. 정방향 list_building_districts 의 짝이다.
--
-- 왜: 지도는 상권을 누르면 이름·유형만 알려주고 끝나 **막다른 길**이었다. 창업자는
--     건물 이름을 모르므로 검색으로 들어올 수 없다.
--
-- 판정은 정방향과 글자 그대로 같아야 한다 — st_contains(d.geom, parcel.geom).
--    다르면 "상권 목록으로 들어간 건물인데 그 건물 화면엔 그 상권이 안 뜨는" 모순이 난다.
--    필지는 폴리곤이 아니라 **점 하나**라, 경계에 걸친 땅은 "걸쳐서 빠지는" 것이 아니라
--    그 대표점이 안쪽이냐 바깥이냐로 갈린다.
--
-- 세로줄은 건물이 아니라 **땅(필지)** 이다. 점포 수를 필지 단위로만 셀 수 있어서다
--    (unit_business.unit_id 295만 행 전량 NULL — 건물 단위로는 영영 못 가른다).
--    건물로 줄세우면 한 땅의 동들이 같은 점포 수를 **복사해** 갖는다: 명동 상위 10에
--    "롯데호텔 및 백화점 317" 이 네 줄 연달아 나온다(본관동·신관동·부속건물 2동).
--    한 땅에 동이 많은 것은 예외가 아니라 정상이다 — 전국 실측 20동 초과 637곳(21,635동),
--    최대 168동(헬리오시티) · 창덕궁 157 · 서울대 154 · 경복궁 140.
--
-- 미리 굽지 않는다. 형제 mv_district_industry_mix 는 **전 상권 x 전 점포**라 12.5초였고,
--    여기는 상권 하나만 본다 — 최대 상권도 찬 캐시 0.5초 / 더운 35ms(2026-08-31 실측).
create or replace function list_district_buildings(
  p_district_id text,
  p_limit       int default 50,
  p_offset      int default 0
)
returns table (
  pnu              char(19),
  store_cnt        int,        -- 이 **땅**의 점포 수(최신 분기)
  bld_cnt_in_pnu   int,        -- 1 보다 크면 화면이 "같은 땅에 N동"을 적는다
  bld_id           text,       -- 대표 동 = 연면적 최대. 아래 칸들은 검색 결과와 같은 모양
  bld_nm           text,
  road_addr        text,
  jibun_addr       text,
  lat              double precision,
  lng              double precision,
  floor_cnt        int,
  min_floor        smallint,
  max_floor        smallint,
  has_roof         boolean,
  total_parcel_cnt bigint,     -- 상한에 잘리기 전 전체 규모(모든 행에 같은 값)
  total_bld_cnt    bigint
)
language sql
stable
security definer
set search_path = public
as $$
  with scope as (
    -- ⛔ 정방향(list_building_districts)과 같은 판정. 좌표 없는 필지는 아예 안 본다 —
    --    st_contains 가 NULL 을 거짓으로 흘리면 "상권 밖"이라는 **단정**이 되어 버린다.
    select p.pnu
    from district d
    join parcel p on st_contains(d.geom, p.geom)
    where d.district_id = p_district_id
      and p.geom is not null
  ),
  elig as (
    -- 층 자료가 아예 없는 건물은 눌러도 빈 화면이라 뺀다
    -- (검색과 **같은 규칙** — 2026-08-13 실측 242,631 중 239동).
    select b.bld_id, b.pnu, b.display_nm, b.total_area_m2
    from scope sc
    join building b on b.pnu = sc.pnu
    where exists (
      select 1 from building_floor f
      where f.bld_id = b.bld_id and f.floor_no is not null
    )
  ),
  stores as (
    select ub.pnu, count(*)::int as n
    from unit_business ub
    join scope sc on sc.pnu = ub.pnu
    where ub.snapshot_ym = (select max(u.snapshot_ym) from unit_business u)
    group by 1
  ),
  land as (
    -- ⓘ 창 함수는 GROUP BY **뒤에** 돈다 → count(*) over () = 땅 수,
    --    sum(count(*)) over () = 동 수. 둘을 한 번에 얻으려고 이 모양을 쓴다.
    select e.pnu,
           coalesce(max(s.n), 0)::int as store_cnt,
           count(*)::int              as bld_cnt_in_pnu,
           count(*)      over ()      as total_parcel_cnt,
           sum(count(*)) over ()      as total_bld_cnt
    from elig e
    left join stores s on s.pnu = e.pnu
    group by e.pnu
  ),
  page as (
    -- ⛔ 무거운 조인(주소 조립·좌표·층 집계) 전에 **상한을 먼저** 건다.
    --    검색 함수가 "25행에만 필요하다"며 쓰는 것과 같은 수법이다.
    -- 정렬 tie-break 에 pnu 를 둔다 — 없으면 같은 점포 수끼리 순서가 흔들려
    -- '더 보기'가 이미 본 줄을 다시 가져오거나 건너뛴다.
    select *
    from land
    order by store_cnt desc, pnu
    limit  greatest(1, least(coalesce(p_limit, 50), 200))
    offset greatest(0, coalesce(p_offset, 0))
  )
  select
    pg.pnu,
    pg.store_cnt,
    pg.bld_cnt_in_pnu,
    rep.bld_id,
    rep.display_nm as bld_nm,
    p.road_addr,
    parcel_jibun_addr(p.sido_nm, p.sigungu_nm, p.emd_nm, p.jibun) as jibun_addr,
    -- ⛔ 좌표는 geom 에서만 뽑는다. parcel 의 lat/lng **칸**을 쓰면 검색·상권판정과
    --    자리가 갈려 "마커는 상권 밖인데 글자는 상권 안"이 된다(2026-08-14e 규칙).
    st_y(p.geom)::double precision as lat,
    st_x(p.geom)::double precision as lng,
    fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof,
    pg.total_parcel_cnt,
    pg.total_bld_cnt
  from page pg
  join parcel p on p.pnu = pg.pnu
  join lateral (
    select e.bld_id, e.display_nm
    from elig e
    where e.pnu = pg.pnu
    order by e.total_area_m2 desc nulls last, e.bld_id
    limit 1
  ) rep on true
  join lateral (
    -- ⛔ 층수 규칙을 여기서 새로 정하지 않는다 — 검색 함수의 것을 글자 그대로 옮겼다.
    --    갈리면 같은 건물이 들어온 길에 따라 "지하2~15층"과 "지하2~99층"으로 갈린다.
    select count(*)::int                                    as floor_cnt,
           min(s.floor_no) filter (where s.floor_no <> 99)  as min_floor,
           max(s.floor_no) filter (where s.floor_no <> 99)  as max_floor,
           coalesce(bool_or(s.floor_no = 99), false)        as has_roof
    from v_building_floor_stack s
    where s.bld_id = rep.bld_id
  ) fs on true
  order by pg.store_cnt desc, pg.pnu;
$$;

comment on function list_district_buildings(text, int, int) is
  '상권 하나에 속한 **땅(필지)** 목록을 점포 많은 순으로. 정방향 list_building_districts 와 '
  '같은 판정(st_contains + parcel.geom)을 써야 두 화면이 같은 말을 한다. '
  'store_cnt 는 **그 땅**의 점포 수다(건물별로는 영영 못 가른다 — unit_business.unit_id 전량 NULL). '
  '한 땅에 여러 동이면 대표 동(연면적 최대) 한 채만 싣고 bld_cnt_in_pnu 로 몇 동인지 알린다.';

-- Supabase 는 새 함수를 anon 에게 자동으로 연다(pg_default_acl) — 만든 자리에서 닫는다.
-- 2026-08-31 실측: 이 줄 없이 만드니 anon 실행 권한이 곧바로 t 였다.
revoke all on function list_district_buildings(text, int, int) from public, anon, authenticated;

-- 한 땅의 동 목록 — 목록에서 "같은 땅에 N동"을 **펼칠 때만** 부른다.
-- 목록에 동을 전부 실으면 대전역 상권에서 606동이 딸려 오는데, 필지의 94%
-- (176,488/188,442)는 동이 하나뿐이라 그 짐은 대부분 쓰이지 않는다.
create or replace function list_parcel_buildings(p_pnu text)
returns table (
  bld_id        text,
  bld_nm        text,
  dong_nm       text,
  total_area_m2 numeric,
  floor_cnt     int,
  min_floor     smallint,
  max_floor     smallint,
  has_roof      boolean
)
language sql
stable
security definer
set search_path = public
as $$
  select
    b.bld_id,
    b.display_nm as bld_nm,
    -- 동명칭을 함께 준다 — 한 땅의 동들은 **이름이 같은 일이 흔해서**(롯데호텔 4동 전부
    -- '롯데호텔 및 백화점') 이것 없이는 사용자가 무엇을 고르는지 알 수 없다.
    -- ⓘ 새로 여는 칸이 아니다: display_nm 은 건물명이 비면 이미 동명칭을 그대로 내보낸다.
    --    그래도 성명 가림을 한 번 더 통과시킨다 — 정상 동명칭엔 무해하고, 만에 하나
    --    사람 이름이 끝에 붙어 있으면 지운다.
    nullif(btrim(mask_person_name(b.dong_nm)), '') as dong_nm,
    b.total_area_m2,
    fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof
  from building b
  join lateral (
    select count(*)::int                                    as floor_cnt,
           min(s.floor_no) filter (where s.floor_no <> 99)  as min_floor,
           max(s.floor_no) filter (where s.floor_no <> 99)  as max_floor,
           coalesce(bool_or(s.floor_no = 99), false)        as has_roof
    from v_building_floor_stack s
    where s.bld_id = b.bld_id
  ) fs on true
  -- ⛔ `p_pnu::char(19)` 의 캐스트를 지우지 말 것. pnu 컬럼이 char(19) 인데 text 와 견주면
  --    **컬럼 쪽**이 text 로 캐스트돼 인덱스가 통째로 죽는다(2026-08-16b 실측 459.8ms↔0.796ms).
  where b.pnu = p_pnu::char(19)
    and exists (
      select 1 from building_floor f
      where f.bld_id = b.bld_id and f.floor_no is not null
    )
  order by b.total_area_m2 desc nulls last, b.bld_id;
$$;

comment on function list_parcel_buildings(text) is
  '한 필지에 선 동 목록. 목록 화면에서 "같은 땅에 N동"을 펼칠 때만 부른다. '
  '층 자료 없는 동은 뺀다(눌러도 빈 화면이라 — 검색과 같은 규칙). '
  '동명칭을 함께 주는 이유: 한 땅의 동들은 건물명이 같은 일이 흔해 이름만으로는 못 가린다.';

revoke all on function list_parcel_buildings(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것.
create or replace function api.list_district_buildings(
  p_district_id text,
  p_limit       int default 50,
  p_offset      int default 0
)
returns table (
  pnu              char(19),
  store_cnt        int,
  bld_cnt_in_pnu   int,
  bld_id           text,
  bld_nm           text,
  road_addr        text,
  jibun_addr       text,
  lat              double precision,
  lng              double precision,
  floor_cnt        int,
  min_floor        smallint,
  max_floor        smallint,
  has_roof         boolean,
  total_parcel_cnt bigint,
  total_bld_cnt    bigint
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_district_buildings(p_district_id, p_limit, p_offset) $$;

revoke all on function api.list_district_buildings(text, int, int) from public, anon, authenticated;
grant execute on function api.list_district_buildings(text, int, int) to anon, authenticated;

create or replace function api.list_parcel_buildings(p_pnu text)
returns table (
  bld_id        text,
  bld_nm        text,
  dong_nm       text,
  total_area_m2 numeric,
  floor_cnt     int,
  min_floor     smallint,
  max_floor     smallint,
  has_roof      boolean
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_parcel_buildings(p_pnu) $$;

revoke all on function api.list_parcel_buildings(text) from public, anon, authenticated;
grant execute on function api.list_parcel_buildings(text) to anon, authenticated;

notify pgrst, 'reload schema';

-- =====================================================================
-- 함수: get_data_freshness — 이 자료는 언제 것인가 (2026-09-05d)
-- =====================================================================
-- 마이그레이션 2026-09-05d. 화면 아래 푸터의 표 한 장이 이 함수 하나만 부른다.
--
-- 왜: 신선도를 아는 길이 `python scripts/post_load.py --check` 뿐이었다 — 우리만 볼 수
--     있는 자리다. 보는 사람은 이 화면의 숫자가 언제 것인지 알 방법이 없었다.
--
-- 날짜를 화면에 박지 않기 위한 함수다. 글자로 적어 두면 적재하는 순간부터 그 글자만
--    거짓말을 한다(코드는 한 줄도 안 고쳤는데 화면이 옛 분기를 말한다). 기준일은 창고에서
--    읽고, "다음 갱신 예정"은 **규칙으로 계산**한다 — 어느 쪽도 사람이 적는 숫자가 아니다.
--
-- 규칙은 셋뿐이고 함수 안에 한 번씩만 적혀 있다: 분기 자료는 분기말 + 5개월 - 하루(다음
--    분기가 공개되는 달의 말일), 월간 자료는 기준월 + 2개월 - 하루, 국세청 기준시가는
--    고시일의 다음 해 3월 31일. 주기가 없는 자료는 null 이다 — 없는 주기를 지어내면
--    "늦었다"는 거짓 신호가 화면에 뜬다.
--
-- 모양이 안 맞으면 계산하지 않는다. `to_date('2026Q3','YYYYMM')` 은 **에러**이고, 그 한 줄이
--    터지면 표가 통째로 사라진다(unit_business.snapshot_ym 은 컬럼 주석이 두 형식을 허용한다).
--
-- api_quota_log 는 안 본다 — 그건 우리 호출 장부이지 자료의 나이가 아니다(하한선일 뿐이라
--    신선도의 근거로 쓰면 틀린 날짜를 자신 있게 적게 된다).
--
-- 시간대는 Asia/Seoul 로 고정한다. 이 DB 는 UTC 라(2026-09-01a) 그냥 날짜로 자르면 한국
--    새벽 0~9시에 어제 날짜가 찍힌다 — 신선도 표가 하루 낡아 보이는 자리다.
create or replace function get_data_freshness()
returns table (
  src           text,
  basis_kind    text,
  basis         text,
  next_expected date,
  cadence       text
)
language sql
stable
security definer
set search_path = public
as $$
  with raw as (
    -- ⓘ 순서를 ord 로 못 박는다. union all 은 순서를 보장하지 않으므로, 이 숫자가 없으면
    --   화면의 줄 순서가 실행할 때마다 달라질 수 있다(사람은 그걸 자료가 바뀐 것으로 읽는다).
    select 1 as ord,
           '점포·업종 (상권정보)'::text as src,
           '분기'::text                 as basis_kind,
           (select max(t.snapshot_ym)::text from unit_business t) as basis,
           'sangkwon'::text             as rule_kind,
           '분기마다 (다음 분기 자료가 공개되면 사람이 적재)'::text as cadence
    union all
    select 2, '실거래 (매매)', '계약월',
           (select max(t.contract_ym)::text from transaction t),
           'none',
           '수시 (서울·대전 전부 활성화 뒤 확대)'
    union all
    select 3, '건축물대장', '적재일',
           (select (max(t.updated_at) at time zone 'Asia/Seoul')::date::text from building t),
           'none',
           '월간 파일 (사람이 적재)'
    union all
    select 4, '상권 경계', '계산일',
           (select (max(t.computed_at) at time zone 'Asia/Seoul')::date::text from district t),
           'none',
           '비정기 (원천이 바뀌면)'
    union all
    select 5, 'LH 상가 공고', '수집일',
           (select (max(t.collected_at) at time zone 'Asia/Seoul')::date::text from lh_notice t),
           'none',
           '주 1회 감시 · 적재는 사람'
    union all
    select 6, '건축 인허가', '기준월',
           (select max(t.loaded_ym)::text from arch_permit t),
           'permit',
           '월 1회'
    union all
    select 7, '국세청 기준시가', '고시일',
           (select max(t.notice_date)::text from nts_base_price t),
           'nts',
           '연 1회 (매년 3월 고시)'
    union all
    select 8, '상권 임대 동향 (부동산원)', '분기',
           (select max(t.quarter)::text from rent_stat t),
           'rone',
           '분기마다'
    union all
    select 9, '참고 시세 성적표', '적재일',
           (select (max(t.loaded_at) at time zone 'Asia/Seoul')::date::text
              from price_gate_sigungu t),
           'none',
           '재생성 때 (결재 사항)'
    union all
    select 10, '필지 (토지 특성)', '갱신일',
           (select (max(t.updated_at) at time zone 'Asia/Seoul')::date::text from parcel t),
           'none',
           '연 1회 (브이월드)'
  ),
  norm as (
    -- 분기 규칙을 쓰는 두 줄을 **같은 모양('YYYYMM' 분기말 달)** 으로 맞춘다. 이렇게 해야
    -- 아래 계산이 한 번만 적힌다 — 두 벌로 적어 두면 한쪽만 고쳐지는 날 두 자료가 서로
    -- 다른 주기를 말한다.
    select r.*,
           case
             when r.rule_kind = 'sangkwon' and r.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
               then r.basis
             when r.rule_kind = 'rone' and r.basis ~ '^\d{4}Q[1-4]$'
               then left(r.basis, 4) || lpad((right(r.basis, 1)::int * 3)::text, 2, '0')
           end as q_ym
    from raw r
  )
  select n.src,
         n.basis_kind,
         n.basis,
         case
           -- 분기 자료: 다음 분기가 **공개되는 달**의 말일(분기말 + 5개월 - 하루).
           when n.q_ym is not null
             then (to_date(n.q_ym, 'YYYYMM') + interval '5 months' - interval '1 day')::date
           -- 월간 자료: 다음 달 말일(기준월 + 2개월 - 하루).
           when n.rule_kind = 'permit' and n.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
             then (to_date(n.basis, 'YYYYMM') + interval '2 months' - interval '1 day')::date
           -- 연 1회: 다음 해 3월 31일(국세청 고시가 매년 3월).
           when n.rule_kind = 'nts' and n.basis ~ '^\d{4}-\d{2}-\d{2}$'
             then make_date(left(n.basis, 4)::int + 1, 3, 31)
         end as next_expected,
         n.cadence
  from norm n
  order by n.ord;
$$;

comment on function get_data_freshness() is
  '화면 아래 "이 자료는 언제 것인가" 표. 열 갈래 자료의 가장 최근 도장(분기·계약월·적재일·'
  '계산일·수집일·기준월·고시일·갱신일)을 창고에서 읽어 한 줄씩 준다. '
  '⛔ 숫자를 화면에 박지 않기 위한 함수다 — 신선도를 글자로 적어 두면 적재하는 순간부터 '
  '그 글자만 거짓말을 한다. next_expected 도 사람이 적는 값이 아니라 규칙으로 계산한다: '
  '분기 자료는 분기말 달 + 5개월 - 하루(다음 분기가 공개되는 달의 말일), 월간 자료는 '
  '기준월 + 2개월 - 하루(다음 달 말일), 국세청 기준시가는 고시일의 다음 해 3월 31일. '
  '주기가 없는 자료는 null 이다 — 없는 주기를 지어내면 "늦었다"는 거짓 신호가 뜬다. '
  '기준값이 그 모양이 아니면 계산하지 않고 그 칸만 비운다(to_date 가 터지면 표가 통째로 '
  '사라진다). timestamptz 는 전부 Asia/Seoul 로 옮겨 날짜를 자른다 — 이 DB 가 UTC 라 '
  '그냥 자르면 한국 새벽 0~9시에 어제 날짜가 찍힌다. '
  '⛔ api_quota_log 는 안 본다 — 그건 우리 호출 장부이지 자료의 나이가 아니고, 하한선일 뿐이다. '
  '자료가 0행이면 basis 가 null 이고 줄은 그대로 나온다(화면이 "자료 없음"이라 적는다 — '
  '줄을 빼면 "그런 자료를 안 쓴다"로 읽힌다). '
  'security definer (열 표가 전부 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 집계 도장 열 개뿐이고 원본 행은 한 줄도 안 나간다). 2026-09-05d';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function get_data_freshness() from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.get_data_freshness()
returns table (
  src           text,
  basis_kind    text,
  basis         text,
  next_expected date,
  cadence       text
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.get_data_freshness() $$;

revoke all on function api.get_data_freshness() from public, anon, authenticated;
grant execute on function api.get_data_freshness() to anon, authenticated;

-- ⛔ public.get_data_freshness 는 끝까지 닫아 둔다 — 통과 함수가 security definer 라
--    소유자 권한으로 부르므로 anon 에게 열 필요가 없다.

-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';

-- =====================================================================
-- 완료
-- =====================================================================
-- 다음 단계:
--   1) 법정동코드 적재
--   2) 상권정보 분기 파일 → unit_business + parcel/building/unit
--   3) 조인 성공률 측정 (90% 미만이면 정규화 로직 재점검)
-- =====================================================================
