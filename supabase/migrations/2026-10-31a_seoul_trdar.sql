-- =====================================================================
-- 2026-10-31a — 서울 상권 4종(추정매출 · 길단위인구 · 상주인구 · 직장인구) 표·함수·신선도 세 줄 (결정 0045 PR②)
-- =====================================================================
--
-- 왜
-- --
-- 결정 0045 ①-1(👤 2026-10-31): 서울시 상권분석서비스 열린 API 네 종 — 추정매출(OA-15572 · VwsmTrdarSelngQq) ·
-- 길단위인구(OA-15568 · VwsmTrdarFlpopQq) · 상주인구(OA-15584 · VwsmTrdarRepopQq) · 직장인구(OA-15569 ·
-- VwsmTrdarWrcPopltnQq) — 를 2021년 1분기부터 22분기 전부(①-2) **공표값 그대로** 담는다. 상권 코드는 개업·폐업
-- (결정 0033)과 같은 서울 상권 1,650개다. 이 PR 은 창고·함수까지이고 화면 카드는 PR③ 이다 — 카드 변화 0 ·
-- 맨 아래 신선도 표에는 세 줄이 새로 선다(13·14 는 20262 기준 2026-10-31 지남 · 15 는 예정 없음 — `DataFreshness.tsx` 가
-- 서버 줄을 전부 그린다) — 운영 적용 전 전/후 캡처는 메인.
--
-- 무엇이 생기나 (새 객체 + 신선도 함수 세 줄 — 기존 표·함수는 한 글자도 안 바꾼다)
-- ----------------------------------------------------------------------------
--   ① 표 넷 — district_sales((분기, 상권, 업종) 한 줄 · 숫자 48칸) · district_pop_flow · district_pop_resident ·
--      district_pop_worker((분기, 상권) 한 줄). 칸 이름 = API 칸 이름을 소문자로 그대로 · 분기 꼴 = district_openclose
--      와 같은 char(5) 'YYYYQ' · 상권 구분 코드·이름과 상권 이름은 싣지 않는다(district 표에 있다 — 0033 과 같다).
--      전부 RLS 켬 + 권한 회수(공개키 0) — 화면은 함수로만 읽는다.
--   ② 표지 seoul_trdar_release — 네 표마다 한 줄(가장 최근 분기 · 값이 마지막으로 바뀐 분기 · 적재 시각).
--      ⓘ 상주·직장은 서울시가 "1년 중 4분기에 한 번" 갱신해 다음 해 1·2·3분기가 같은 값이다 — 그래서 「YYYY년 기준」
--        글은 max(quarter) 가 아니라 이 표지의 value_quarter 로 쓴다(10-31 실측: 상주 20234 · 직장 20244 의 값이
--        20262 까지 그대로).
--   ③ list_district_sales(p_pnu) + api 쌍둥이 — 필지가 속한 서울 상권마다(좁은 상권 먼저 · 합치지 않는다) 표 전체
--      최근 8분기 창 안의 상권 합(당월 매출 금액·건수)과 그 상권 최신 분기의 업종 상위 5 · 그 밖 합 · 업종 전부.
--   ④ list_district_pop(p_pnu) + api 쌍둥이 — 같은 상권마다 길단위인구(그 상권 최신 분기 + 표 전체 최신 분기
--      flow_table_quarter) · 상주인구 · 직장인구(⛔ 표지의 그 표 max_quarter 분기 행만 — 그 상권이 옛 분기에서
--      끊겼으면 그 칸 null · 그 상권의 마지막 분기는 *_last_quarter · 기준은 표지의 「값이 바뀐 분기」).
--      ③·④ 의 상권 찾기(me·hit)·빈 상태(head) 판정·차례는 list_district_openclose 본문 글자 그대로다
--      (tests/test_seoul_trdar_migration.py 가 대조한다). 공개 호출 허용 총계 34 → 36(post_load.py).
--   ⑤ get_data_freshness 다시 만들기 — 13 「상권 추정매출 (서울시)」 · 14 「상권 길단위인구 (서울시)」(기준 = 분기 ·
--      규칙은 개업·폐업 줄과 같은 'seoul_openclose' — 분기말 + 5개월 − 하루) · 15 「상권 상주·직장인구 (서울시)」
--      (👤 2026-10-31 「다음 예정 없음」 — 기준 = 값이 바뀐 분기 둘을 글로 합침 「상주 2023년 4분기, 직장 2024년
--      4분기」 · 규칙 'none' → 예정일 null). 새 규칙 갈래는 더하지 않는다 · 나머지 열두 줄·규칙은 글자 그대로다.
--      ⓘ api.get_data_freshness 는 다시 만들지 않는다 — 통과 함수라 본문이 그대로다(2026-10-29a 와 같은 판단).
-- ⛔ 머리(language · stable · security definer · set search_path)와 comment 는 정본(schema.sql)과 글자 그대로다 —
--    tests/test_seoul_trdar_migration.py 가 대조한다(CLAUDE.md ⛔ 2026-10-01a).
-- ⛔ 서명은 이름마다 하나뿐이다.
--
-- 잠금
-- ----
-- 새 표·새 색인·새 함수 만들기와 함수 교체(create or replace)뿐이라 이미 있는 표를 ACCESS EXCLUSIVE 로 잠그는
-- 문장이 없다(PostgreSQL 17 문서 13.3 표 — tests/test_migration_lock_timeout_guard.py 도 그렇게 본다). 다만 새 표의
-- `references district` 는 district 에 SHARE ROW EXCLUSIVE 를 잡는다(화면 읽기는 안 막고 district 에 쓰는 적재와만
-- 줄을 선다). 공식 문서(https://www.postgresql.org/docs/17/sql-altertable.html · 2026-10-31 확인): "Note that ADD
-- FOREIGN KEY also acquires a SHARE ROW EXCLUSIVE lock on the referenced table, in addition to the lock on the table
-- on which the constraint is declared." 형제(2026-10-05b · 2026-10-29a) 관습대로 기다림의 상한 `lock_timeout = '2s'` 를
-- **begin 앞**(세션 설정)에 둔다 — 2초 넘게 못 잡으면 통째로 되돌아간다(다시 돌리면 된다 · 전부 멱등).
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 표만 생기고 신선도가 반쯤 바뀐 채 끊기지 않게 한 덩어리로 묶는다.
-- `notify pgrst` 는 commit **뒤**.
--
-- 실행 순서 (⚠️ 순서가 곧 안전장치다 · Claude 가 dbx 로 · 사장님께 여쭌 뒤)
-- ------------------------------------------------------------------------
--   1) 수집 4종을 **먼저 다 끝낸다**:
--        python scripts/collectors/collect_seoul_trdar.py --service all --end-quarter <분기> --quarters 22
--   2) 적재 **전** 디스크 판정 — (지금 사용량 + 이번 적재 약 +310MB + WAL 여유 1GB) 가 디스크의 85% 미만일 때만
--      (넘으면 디스크 확장부터 · 분기 감시 이슈 본문과 같은 판정식).
--   3) python scripts/collectors/load_seoul_trdar.py --dry-run — 관문 통과를 **먼저** 확인한다(DB 안 씀 · 관문 ⒤ 업종
--      코드는 실적재 트랜잭션 안에서 본다). ⛔ 마이그를 먼저 넣고 dry-run 이 걸리면 신선도 13·14·15 줄이
--      '자료 없음'으로 라이브에 남는다.
--   4) **같은 날에** 이 파일 적용:  python scripts/dbx.py -f supabase/migrations/2026-10-31a_seoul_trdar.sql
--   5) 곧바로 4종을 **한 번에** 실적재(분할 적재 금지 — 한 트랜잭션):  python scripts/collectors/load_seoul_trdar.py
--   6) python scripts/post_load.py → python scripts/post_load.py --check — 0 이어야 한다(허용 목록 총계 36 ·
--      정본↔라이브 함수 일치).
--   ⛔ 상권정보 새 분기(202609)·부동산원·개업·폐업·실거래·건축물대장 적재와 **같은 날 넣지 않는다**(디스크·WAL 이
--      겹치고, 무엇 때문에 어긋났는지 가를 수 없다).
--   ⚠️ 이 파일만 먼저 넣고 적재를 미루면 신선도 13·14·15 줄이 '자료 없음'(basis null)으로 운영 화면에 남는다.
--   ⓘ 이 파일 적용과 PR 머지 사이에 **본 폴더(main)** 에서 `--check` 를 돌리면 api 쌍둥이 둘이 허용 목록 밖 공개
--     함수로, get_data_freshness 가 정본과 달라 [사고]가 되는 것이 **정상**이다 — main 의 post_load.py·schema.sql 은
--     아직 옛 판이다. 머지 뒤에 사라진다.
--
-- 적용 뒤 확인 (dbx.py 로 · 적재 전이면 표가 비어 ok 대신 no_data 가 나온다)
-- ------------------------------------------------------------------------
--   select count(*) from api.get_data_freshness();                                  -- 14
--   select src, basis_kind, basis, next_expected from api.get_data_freshness() where src like '상권 %(서울시)';
--     → 적재 뒤: 추정매출·길단위인구 = 20262 · 2026-10-31(20263 이면 2027-01-31) / 상주·직장 = 「상주 2023년 4분기, 직장 2024년 4분기」 · null
--   select tbl, max_quarter, value_quarter from seoul_trdar_release order by tbl;
--   select status, district_nm, latest_quarter, rest_cnt from api.list_district_sales('<서울 상권 안 필지>');
--   select status, flow_table_quarter, flow_quarter, resident_value_quarter, resident_last_quarter,
--          worker_value_quarter, worker_last_quarter from api.list_district_pop('<같은 필지>');
--   select status from api.list_district_sales('<대전 필지>');                       -- not_seoul
--   select has_table_privilege('anon', 'district_sales', 'select');                 -- f (다섯 다)
--
-- 되돌리기
-- --------
-- **새 마이그레이션 파일**로 (신선도 함수 먼저 → 표 나중 — 표부터 지우면 함수가 없는 표를 읽어 신선도 표가 통째로
-- 사라진다): `set lock_timeout = '2s'; begin;` →
--   ① 2026-10-29a_daejeon_dong_closure.sql 의 get_data_freshness 정의 첫 줄부터 그 함수의 revoke 줄까지(comment 포함)를
--      글자 그대로(13·14·15 줄이 없는 판)
--   ② drop function api.list_district_sales(text); drop function api.list_district_pop(text);
--   ③ drop function list_district_sales(text); drop function list_district_pop(text);
--   ④ drop table seoul_trdar_release;
--   ⑤ drop table district_sales; drop table district_pop_flow; drop table district_pop_resident; drop table district_pop_worker;
-- → `commit;` → `notify pgrst, 'reload schema';` 그리고 이 PR revert(정본 · post_load 허용 목록 36 → 34 · 감시 힌트 ·
-- 화면 상수). 적용된 이 파일은 고치지 않는다(원장 — CLAUDE.md 「적용된 마이그레이션 파일은 고치지 않는다」).

set lock_timeout = '2s';

begin;

-- =====================================================================
-- 표·함수: 서울 상권 4종 — 추정매출 · 길단위인구 · 상주인구 · 직장인구 (2026-10-31a · 결정 0045 PR②)
-- =====================================================================
-- 서울시 상권분석서비스 열린 API 네 종의 공표값을 그대로 담는다(우리가 계산하는 것은 함수의 상권 합 — 업종 행의
-- 더하기 — 뿐이다). 적재는 scripts/collectors/load_seoul_trdar.py(네 표를 한 트랜잭션으로 · 분할 적재 금지).
-- 칸 이름은 API 칸 이름의 소문자 그대로다. 숫자는 API 가 실수 꼴(157199.0)로 주는 정수값이다(적재기가 정수로 옮기고,
-- 소수 꼬리가 0 이 아니면 멈춘다).
-- 이 표들은 get_data_freshness 가 읽으므로(분기 · 표지) 그 함수보다 **앞**에 둔다.
create table if not exists district_sales (
  quarter                    char(5) not null,      -- '20262' (서울시 표기 YYYYQ · Q 없음 — district_openclose 와 같다)
  district_id                text    not null references district(district_id),
  svc_induty_cd              text    not null,      -- 서울시 서비스 업종 100종 코드 (CS100001 …)
  svc_induty_cd_nm           text,
  thsmon_selng_amt           bigint,                -- 당월 매출 금액(원) — 상권 합은 int4 를 넘는다
  thsmon_selng_co            int,                   -- 당월 매출 건수
  mdwk_selng_amt             bigint,                -- 주중
  wkend_selng_amt            bigint,                -- 주말
  mon_selng_amt              bigint,
  tues_selng_amt             bigint,
  wed_selng_amt              bigint,
  thur_selng_amt             bigint,
  fri_selng_amt              bigint,
  sat_selng_amt              bigint,
  sun_selng_amt              bigint,
  tmzon_00_06_selng_amt      bigint,                -- 시간대
  tmzon_06_11_selng_amt      bigint,
  tmzon_11_14_selng_amt      bigint,
  tmzon_14_17_selng_amt      bigint,
  tmzon_17_21_selng_amt      bigint,
  tmzon_21_24_selng_amt      bigint,
  ml_selng_amt               bigint,                -- 성별
  fml_selng_amt              bigint,
  agrde_10_selng_amt         bigint,                -- 연령대
  agrde_20_selng_amt         bigint,
  agrde_30_selng_amt         bigint,
  agrde_40_selng_amt         bigint,
  agrde_50_selng_amt         bigint,
  agrde_60_above_selng_amt   bigint,
  mdwk_selng_co              int,
  wkend_selng_co             int,
  mon_selng_co               int,
  tues_selng_co              int,
  wed_selng_co               int,
  thur_selng_co              int,
  fri_selng_co               int,
  sat_selng_co               int,
  sun_selng_co               int,
  tmzon_00_06_selng_co       int,
  tmzon_06_11_selng_co       int,
  tmzon_11_14_selng_co       int,
  tmzon_14_17_selng_co       int,
  tmzon_17_21_selng_co       int,
  tmzon_21_24_selng_co       int,
  ml_selng_co                int,
  fml_selng_co               int,
  agrde_10_selng_co          int,
  agrde_20_selng_co          int,
  agrde_30_selng_co          int,
  agrde_40_selng_co          int,
  agrde_50_selng_co          int,
  agrde_60_above_selng_co    int,
  source_nm                  text,                  -- raw 파일 이름(어느 판에서 왔나)
  loaded_at                  timestamptz default now(),
  primary key (quarter, district_id, svc_induty_cd)
);

comment on table district_sales is '결정 0045 서울시 상권분석서비스 추정매출(OA-15572 · VwsmTrdarSelngQq) 공표값 그대로 — (분기, 상권, 업종) 한 줄. 서울시가 카드 결제 금액을 바탕으로 추정해 공표한 값이다(산출식은 서울시 몫 · 우리는 더하기만 한다). 상권 합계 행은 원본에 없다(업종 행을 더한다). 공개키 읽기 금지 — 화면은 list_district_sales 로만 읽는다';

-- 함수가 상권별로 최근 분기를 읽는 길. max(quarter)(신선도)는 기본키(첫 칸 quarter)가 받친다.
create index if not exists idx_district_sales_district on district_sales (district_id, quarter);

alter table district_sales enable row level security;

-- ⛔ Supabase 는 새 표를 anon 에 자동으로 연다(pg_default_acl) — 만든 자리에서 닫는다.
revoke all on district_sales from public, anon, authenticated;

create table if not exists district_pop_flow (
  quarter                    char(5) not null,      -- '20262'
  district_id                text    not null references district(district_id),
  tot_flpop_co               bigint,                -- 총 길단위인구(서울시 칸 이름은 「유동인구」 · 단위 미표기)
  ml_flpop_co                bigint,
  fml_flpop_co               bigint,
  agrde_10_flpop_co          bigint,
  agrde_20_flpop_co          bigint,
  agrde_30_flpop_co          bigint,
  agrde_40_flpop_co          bigint,
  agrde_50_flpop_co          bigint,
  agrde_60_above_flpop_co    bigint,
  tmzon_00_06_flpop_co       bigint,
  tmzon_06_11_flpop_co       bigint,
  tmzon_11_14_flpop_co       bigint,
  tmzon_14_17_flpop_co       bigint,
  tmzon_17_21_flpop_co       bigint,
  tmzon_21_24_flpop_co       bigint,
  mon_flpop_co               bigint,
  tues_flpop_co              bigint,
  wed_flpop_co               bigint,
  thur_flpop_co              bigint,
  fri_flpop_co               bigint,
  sat_flpop_co               bigint,
  sun_flpop_co               bigint,
  source_nm                  text,
  loaded_at                  timestamptz default now(),
  primary key (quarter, district_id)
);

comment on table district_pop_flow is '결정 0045 서울시 상권분석서비스 길단위인구(OA-15568 · VwsmTrdarFlpopQq) 공표값 그대로 — (분기, 상권) 한 줄. 서울시 칸 이름은 「유동인구」이고 단위(일평균·분기 합)는 원문에 적혀 있지 않다. 공개키 읽기 금지 — 화면은 list_district_pop 으로만 읽는다';

create index if not exists idx_district_pop_flow_district on district_pop_flow (district_id, quarter);

alter table district_pop_flow enable row level security;

revoke all on district_pop_flow from public, anon, authenticated;

create table if not exists district_pop_resident (
  quarter                    char(5) not null,      -- '20262' — ⚠️ 값은 4분기 코드에서만 바뀐다(seoul_trdar_release)
  district_id                text    not null references district(district_id),
  tot_repop_co               int,                   -- 총 상주인구
  ml_repop_co                int,
  fml_repop_co               int,
  agrde_10_repop_co          int,
  agrde_20_repop_co          int,
  agrde_30_repop_co          int,
  agrde_40_repop_co          int,
  agrde_50_repop_co          int,
  agrde_60_above_repop_co    int,
  mag_10_repop_co            int,                   -- 남성 연령대
  mag_20_repop_co            int,
  mag_30_repop_co            int,
  mag_40_repop_co            int,
  mag_50_repop_co            int,
  mag_60_above_repop_co      int,
  fag_10_repop_co            int,                   -- 여성 연령대
  fag_20_repop_co            int,
  fag_30_repop_co            int,
  fag_40_repop_co            int,
  fag_50_repop_co            int,
  fag_60_above_repop_co      int,
  tot_hshld_co               int,                   -- 총 가구
  apt_hshld_co               int,                   -- 아파트 가구
  non_apt_hshld_co           int,                   -- 비아파트 가구
  source_nm                  text,
  loaded_at                  timestamptz default now(),
  primary key (quarter, district_id)
);

comment on table district_pop_resident is '결정 0045 서울시 상권분석서비스 상주인구(OA-15584 · VwsmTrdarRepopQq) 공표값 그대로 — (분기, 상권) 한 줄. 서울시가 1년 중 4분기에 한 번 값을 바꾸고 다음 해 1·2·3분기는 같은 값이다(10-31 실측: 20234 값이 20262 까지 그대로 — 2024·2025 갱신 건너뜀). 「YYYY년 기준」은 seoul_trdar_release.value_quarter 로 쓴다. 공개키 읽기 금지';

create index if not exists idx_district_pop_resident_district on district_pop_resident (district_id, quarter);

alter table district_pop_resident enable row level security;

revoke all on district_pop_resident from public, anon, authenticated;

create table if not exists district_pop_worker (
  quarter                       char(5) not null,   -- '20262' — ⚠️ 값은 4분기 코드에서만 바뀐다(seoul_trdar_release)
  district_id                   text    not null references district(district_id),
  tot_wrc_popltn_co             int,                -- 총 직장인구
  ml_wrc_popltn_co              int,
  fml_wrc_popltn_co             int,
  agrde_10_wrc_popltn_co        int,
  agrde_20_wrc_popltn_co        int,
  agrde_30_wrc_popltn_co        int,
  agrde_40_wrc_popltn_co        int,
  agrde_50_wrc_popltn_co        int,
  agrde_60_above_wrc_popltn_co  int,
  mag_10_wrc_popltn_co          int,
  mag_20_wrc_popltn_co          int,
  mag_30_wrc_popltn_co          int,
  mag_40_wrc_popltn_co          int,
  mag_50_wrc_popltn_co          int,
  mag_60_above_wrc_popltn_co    int,
  fag_10_wrc_popltn_co          int,
  fag_20_wrc_popltn_co          int,
  fag_30_wrc_popltn_co          int,
  fag_40_wrc_popltn_co          int,
  fag_50_wrc_popltn_co          int,
  fag_60_above_wrc_popltn_co    int,
  source_nm                     text,
  loaded_at                     timestamptz default now(),
  primary key (quarter, district_id)
);

comment on table district_pop_worker is '결정 0045 서울시 상권분석서비스 직장인구(OA-15569 · VwsmTrdarWrcPopltnQq) 공표값 그대로 — (분기, 상권) 한 줄. 서울시가 1년 중 4분기에 한 번 값을 바꾸고 다음 해 1·2·3분기는 같은 값이다(10-31 실측: 20244 값이 20262 까지 그대로). 「YYYY년 기준」은 seoul_trdar_release.value_quarter 로 쓴다. 공개키 읽기 금지';

create index if not exists idx_district_pop_worker_district on district_pop_worker (district_id, quarter);

alter table district_pop_worker enable row level security;

revoke all on district_pop_worker from public, anon, authenticated;

-- 네 표의 표지 — 적재기가 같은 트랜잭션에서 네 줄을 올린다. value_quarter 는 이웃 분기의 상권별 숫자를 견주어
-- 「하나라도 바뀐 상권이 있는 마지막 분기」를 적재기가 계산한 것이다(매출·길단위인구는 분기마다 바뀌어 max 와 같다).
create table if not exists seoul_trdar_release (
  tbl            text        primary key,           -- district_sales · district_pop_flow · district_pop_resident · district_pop_worker
  max_quarter    char(5)     not null,              -- 그 표에 든 가장 최근 분기
  value_quarter  char(5)     not null,              -- 값이 마지막으로 바뀐 분기
  loaded_at      timestamptz not null default now(),
  check (value_quarter <= max_quarter)
);

comment on table seoul_trdar_release is '결정 0045 서울 상권 4종의 표지 — 표마다 가장 최근 분기(max_quarter)와 값이 마지막으로 바뀐 분기(value_quarter). 상주 2024·2025 갱신 건너뜀 실측 10-31(서울시 공지 「1년 중 4분기에 한 번」과 다르다) — 그래서 「다음 갱신 예정」은 계산하지 않고 이 값만 적는다. 공개키 읽기 금지';

alter table seoul_trdar_release enable row level security;

revoke all on seoul_trdar_release from public, anon, authenticated;

create or replace function list_district_sales(p_pnu text)
returns table (
  status           text,
  district_id      text,
  district_nm      text,
  district_type    text,
  latest_quarter   text,
  window_quarters  text[],
  trend            jsonb,
  top              jsonb,
  rest_cnt         int,
  rest_amt         bigint,
  rest_co          bigint,
  industries       jsonb
)
language sql
stable
security definer
set search_path = public
as $$
  with recursive const as (
    -- 보는 분기 창의 크기 · 따로 싣는 상위 업종 수 · 업종 전부의 상한. 셋 다 한 곳에만 적는다.
    select 8 as n_quarters, 5 as n_top, 100 as n_industries
  ),
  me as (
    -- 좌표가 없으면 아무 상권에도 안 든다는 **단정**이 새어 나가지 않게 따로 가른다(no_coord).
    -- ⛔ pnu 칸은 char(19) — 인자를 그대로 견주면 칸 쪽이 text 로 캐스트돼 색인이 죽는다.
    select p.geom
    from parcel p
    where p.pnu = p_pnu::char(19) and p.geom is not null
  ),
  hit as (
    -- 서울 필지가 담긴 **서울시 상권**만. 술어는 list_building_districts 와 같은 st_contains.
    select d.district_id, d.district_nm, d.district_type, d.area_m2
    from district d cross join me
    where left(p_pnu::char(19), 2) = '11'
      and left(d.sigungu_code, 2) = '11'
      and st_contains(d.geom, me.geom)
  ),
  head as (
    -- 건물 단위 상태 셋 — 판정 순서가 곧 뜻이다(위부터, 서로 배타).
    --   no_coord               필지 좌표 없음(서울이든 아니든 — 모르는 것은 모른다고)
    --   not_seoul              시·도가 서울이 아님(대전 등 — 서울시 자료는 서울 상권만 다룬다)
    --   outside_seoul_district 서울인데 속한 서울시 상권이 없음
    -- 셋 다 아니면 null → 상권마다 ok / no_data 한 줄씩이 대신 나간다.
    select case
             when not exists (select 1 from me) then 'no_coord'
             when left(p_pnu::char(19), 2) <> '11' then 'not_seoul'
             when not exists (select 1 from hit) then 'outside_seoul_district'
           end as status
  ),
  win (quarter, n) as (
    -- **표 전체** 기준 가장 최근 8분기 — 모든 상권이 같은 창을 본다(list_district_openclose 와 같은 꼴 · 상권마다
    -- 제 최신 8분기를 잡으면 자료가 끊긴 상권이 몇 해 전 숫자를 '최근'처럼 보인다). 한 분기씩 기본키(첫 칸
    -- quarter)를 거꾸로 짚어 내려간다 — distinct 로 수십만 행을 훑지 않는다.
    select max(o.quarter), 1 from district_sales o
    union all
    select (select max(o.quarter) from district_sales o where o.quarter < w.quarter), w.n + 1
    from win w cross join const c
    where w.n < c.n_quarters and w.quarter is not null
  ),
  wq as (
    -- 창 그 자체(최신 → 옛 순 · 표가 비었으면 빈 배열) — **모든 줄에 같은 값**을 싣는다.
    select coalesce(array_agg(w.quarter::text order by w.quarter desc)
                      filter (where w.quarter is not null), '{}'::text[]) as window_quarters
    from win w
  ),
  qs as (
    -- 창 안의 분기 × 이 필지의 상권. 창 안에서 그 상권에 빠진 분기는 빠진 채 둔다(채우지 않는다).
    select h.district_id, w.quarter
    from hit h cross join win w
    where w.quarter is not null
  ),
  sums as (
    -- 그 상권·분기의 업종 행 **전부**를 더한다(당월 매출 금액·건수 — 서울시가 상권 합계 행을 안 준다).
    select o.district_id, o.quarter,
           sum(o.thsmon_selng_amt) as amt,
           sum(o.thsmon_selng_co)  as co
    from qs
    join district_sales o on o.district_id = qs.district_id and o.quarter = qs.quarter
    group by o.district_id, o.quarter
  ),
  latest as (
    -- 그 상권이 창 안에서 **실제로 가진** 최신 분기(표 전체 최신과 다를 수 있다). 창 안에 행이 없으면 여기 없다 → no_data.
    select s.district_id, max(s.quarter) as quarter
    from sums s
    group by s.district_id
  ),
  ranked as (
    -- 최신 분기 업종 행 — 당월 매출 금액이 큰 순(같으면 코드 순).
    select o.*,
           row_number() over (partition by o.district_id
                              order by o.thsmon_selng_amt desc, o.svc_induty_cd) as rn
    from latest l
    join district_sales o on o.district_id = l.district_id and o.quarter = l.quarter
  ),
  rest as (
    -- 상위 5 밖 업종 — 수와 합(한 덩어리).
    select r.district_id,
           count(*)::int                    as cnt,
           sum(r.thsmon_selng_amt)::bigint  as amt,
           sum(r.thsmon_selng_co)::bigint   as co
    from ranked r cross join const c
    where r.rn > c.n_top
    group by r.district_id
  ),
  rows_out as (
    select hd.status,
           null::text as district_id, null::text as district_nm, null::text as district_type,
           null::text as latest_quarter,
           null::jsonb as trend, null::jsonb as top,
           null::int as rest_cnt, null::bigint as rest_amt, null::bigint as rest_co,
           null::jsonb as industries,
           0::numeric as sort_area
    from head hd
    where hd.status is not null
    union all
    select case when l.quarter is null then 'no_data' else 'ok' end,
           h.district_id, h.district_nm, h.district_type,
           l.quarter::text,
           (select jsonb_agg(jsonb_build_object(
                     'quarter', s.quarter::text,
                     'amt',     s.amt,
                     'co',      s.co)
                   order by s.quarter desc)
              from sums s
             where s.district_id = h.district_id),
           (select jsonb_agg(jsonb_build_object(
                     'cd',        r.svc_induty_cd,
                     'nm',        r.svc_induty_cd_nm,
                     'amt',       r.thsmon_selng_amt,
                     'co',        r.thsmon_selng_co,
                     'mdwk_amt',  r.mdwk_selng_amt,
                     'wkend_amt', r.wkend_selng_amt)
                   order by r.rn)
              from ranked r cross join const c
             where r.district_id = h.district_id and r.rn <= c.n_top),
           case when l.quarter is not null then coalesce(rs.cnt, 0) end,
           case when l.quarter is not null then coalesce(rs.amt, 0) end,
           case when l.quarter is not null then coalesce(rs.co, 0) end,
           (select jsonb_agg(jsonb_build_object(
                     'cd',  r.svc_induty_cd,
                     'nm',  r.svc_induty_cd_nm,
                     'amt', r.thsmon_selng_amt,
                     'co',  r.thsmon_selng_co)
                   order by r.rn)
              from ranked r cross join const c
             where r.district_id = h.district_id and r.rn <= c.n_industries),
           h.area_m2
    from hit h
    left join latest l on l.district_id = h.district_id
    left join rest rs on rs.district_id = h.district_id
  )
  select ro.status, ro.district_id, ro.district_nm, ro.district_type, ro.latest_quarter,
         wq.window_quarters, ro.trend, ro.top, ro.rest_cnt, ro.rest_amt, ro.rest_co, ro.industries
  from rows_out ro cross join wq
  -- 좁은 상권이 더 구체적인 설명이라 먼저 온다(list_building_districts 와 같은 정렬).
  order by ro.sort_area asc, ro.district_id;
$$;

comment on function list_district_sales(text) is
  '결정 0045 이 필지가 속한 서울시 상권마다(좁은 상권 먼저 · 합치지 않는다) 서울시 상권분석서비스가 공표한 '
  '추정매출 — 표 전체 기준 최근 8분기(모든 상권이 같은 창) 안의 상권 합(trend: 분기마다 당월 매출 금액 합 amt · '
  '건수 합 co · 최신 → 옛 순 · 창 안에서 그 상권에 빠진 분기는 빠진 채) + 그 상권의 최신 분기 업종 상위 5(top: '
  '당월 매출 금액 큰 순 · 같으면 코드 순 · 주중·주말 금액 포함) + 그 밖 업종 수·금액 합·건수 합(rest_cnt·rest_amt·'
  'rest_co) + 최신 분기 업종 전부(industries · 같은 차례 · 상한 100). latest_quarter 는 그 상권이 창 안에서 실제로 '
  '가진 최신 분기다. window_quarters 는 창의 분기 목록(최신 → 옛 순 · 표가 비었으면 빈 배열)이고 모든 줄에 같은 값이다. '
  '상권 찾기·status 는 list_district_openclose 와 같은 글이다: no_coord(필지 좌표 없음) → not_seoul(서울 아님) → '
  'outside_seoul_district(서울인데 속한 서울시 상권 없음) — 이 셋은 한 줄만, 아니면 상권마다 ok / no_data(창 안에 행 없음). '
  '값은 서울시가 카드 결제 금액을 바탕으로 추정해 공표한 상권 값이며 이 건물의 매출이 아니다. '
  'security definer (district_sales·district·parcel 이 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 상권 이름·종류와 서울시 공표 금액·건수뿐이다).';

-- 만든 자리에서 다시 닫는다(대시보드 판은 anon 을 붙인다).
revoke all on function list_district_sales(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.list_district_sales(p_pnu text)
returns table (
  status           text,
  district_id      text,
  district_nm      text,
  district_type    text,
  latest_quarter   text,
  window_quarters  text[],
  trend            jsonb,
  top              jsonb,
  rest_cnt         int,
  rest_amt         bigint,
  rest_co          bigint,
  industries       jsonb
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_district_sales(p_pnu) $$;

revoke all on function api.list_district_sales(text) from public, anon, authenticated;
grant execute on function api.list_district_sales(text) to anon, authenticated;

-- ⛔ public.list_district_sales 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.

create or replace function list_district_pop(p_pnu text)
returns table (
  status                  text,
  district_id             text,
  district_nm             text,
  district_type           text,
  flow_table_quarter      char(5),
  flow_quarter            char(5),
  flow                    jsonb,
  resident_value_quarter  char(5),
  resident_last_quarter   char(5),
  resident                jsonb,
  worker_value_quarter    char(5),
  worker_last_quarter     char(5),
  worker                  jsonb
)
language sql
stable
security definer
set search_path = public
as $$
  with me as (
    -- 좌표가 없으면 아무 상권에도 안 든다는 **단정**이 새어 나가지 않게 따로 가른다(no_coord).
    -- ⛔ pnu 칸은 char(19) — 인자를 그대로 견주면 칸 쪽이 text 로 캐스트돼 색인이 죽는다.
    select p.geom
    from parcel p
    where p.pnu = p_pnu::char(19) and p.geom is not null
  ),
  hit as (
    -- 서울 필지가 담긴 **서울시 상권**만. 술어는 list_building_districts 와 같은 st_contains.
    select d.district_id, d.district_nm, d.district_type, d.area_m2
    from district d cross join me
    where left(p_pnu::char(19), 2) = '11'
      and left(d.sigungu_code, 2) = '11'
      and st_contains(d.geom, me.geom)
  ),
  head as (
    -- 건물 단위 상태 셋 — 판정 순서가 곧 뜻이다(위부터, 서로 배타).
    --   no_coord               필지 좌표 없음(서울이든 아니든 — 모르는 것은 모른다고)
    --   not_seoul              시·도가 서울이 아님(대전 등 — 서울시 자료는 서울 상권만 다룬다)
    --   outside_seoul_district 서울인데 속한 서울시 상권이 없음
    -- 셋 다 아니면 null → 상권마다 ok / no_data 한 줄씩이 대신 나간다.
    select case
             when not exists (select 1 from me) then 'no_coord'
             when left(p_pnu::char(19), 2) <> '11' then 'not_seoul'
             when not exists (select 1 from hit) then 'outside_seoul_district'
           end as status
  ),
  rel as (
    -- 상주·직장의 「값이 마지막으로 바뀐 분기」(value_quarter)와 그 표의 가장 최근 분기(max_quarter) — 표 전체 기준
    -- 하나(적재기가 표지에 적는다 · 상권마다 아니다). 길단위인구는 표 전체 최신 분기 — 화면이 그 상권의 분기와 견주어
    -- 「이 상권 자료는 ○분기까지」를 쓸 수 있게 모든 상권 줄에 같은 값을 싣는다.
    select (select r.value_quarter from seoul_trdar_release r where r.tbl = 'district_pop_resident') as resident_vq,
           (select r.max_quarter   from seoul_trdar_release r where r.tbl = 'district_pop_resident') as resident_mq,
           (select r.value_quarter from seoul_trdar_release r where r.tbl = 'district_pop_worker')   as worker_vq,
           (select r.max_quarter   from seoul_trdar_release r where r.tbl = 'district_pop_worker')   as worker_mq,
           (select max(o.quarter) from district_pop_flow o)                                          as flow_tq
  ),
  rows_out as (
    select hd.status,
           null::text as district_id, null::text as district_nm, null::text as district_type,
           null::char(5) as flow_table_quarter, null::char(5) as flow_quarter, null::jsonb as flow,
           null::char(5) as resident_value_quarter, null::char(5) as resident_last_quarter, null::jsonb as resident,
           null::char(5) as worker_value_quarter, null::char(5) as worker_last_quarter, null::jsonb as worker,
           0::numeric as sort_area
    from head hd
    where hd.status is not null
    union all
    -- 셋 중 그 상권에 자료가 없는 것은 그 칸(분기·값)만 null — 셋 다 없을 때만 no_data.
    -- ⛔ 상주·직장 값은 **표지의 max_quarter 분기 행**에서만 읽는다 — 그 상권이 옛 분기에서 끊겼으면(10-31 raw 실측:
    --   상주 4곳 · 직장 2곳) 옛 값을 「YYYY년 기준」으로 내보내지 않고 그 칸을 비운다. 그 상권이 가진 마지막 분기는
    --   *_last_quarter 로 따로 준다(화면이 「이 상권 자료는 ○분기까지」를 쓸 수 있게).
    select case when f.quarter is null and rs.quarter is null and wk.quarter is null
                then 'no_data' else 'ok' end,
           h.district_id, h.district_nm, h.district_type,
           rel.flow_tq,
           f.quarter,
           case when f.quarter is not null then jsonb_build_object(
             'tot',            f.tot_flpop_co,
             'ml',             f.ml_flpop_co,
             'fml',            f.fml_flpop_co,
             'agrde_10',       f.agrde_10_flpop_co,
             'agrde_20',       f.agrde_20_flpop_co,
             'agrde_30',       f.agrde_30_flpop_co,
             'agrde_40',       f.agrde_40_flpop_co,
             'agrde_50',       f.agrde_50_flpop_co,
             'agrde_60_above', f.agrde_60_above_flpop_co,
             'tmzon_00_06',    f.tmzon_00_06_flpop_co,
             'tmzon_06_11',    f.tmzon_06_11_flpop_co,
             'tmzon_11_14',    f.tmzon_11_14_flpop_co,
             'tmzon_14_17',    f.tmzon_14_17_flpop_co,
             'tmzon_17_21',    f.tmzon_17_21_flpop_co,
             'tmzon_21_24',    f.tmzon_21_24_flpop_co,
             'mon',            f.mon_flpop_co,
             'tues',           f.tues_flpop_co,
             'wed',            f.wed_flpop_co,
             'thur',           f.thur_flpop_co,
             'fri',            f.fri_flpop_co,
             'sat',            f.sat_flpop_co,
             'sun',            f.sun_flpop_co) end,
           case when rs.quarter is not null then rel.resident_vq end,
           (select max(o.quarter) from district_pop_resident o where o.district_id = h.district_id),
           case when rs.quarter is not null then jsonb_build_object(
             'tot',            rs.tot_repop_co,
             'ml',             rs.ml_repop_co,
             'fml',            rs.fml_repop_co,
             'agrde_10',       rs.agrde_10_repop_co,
             'agrde_20',       rs.agrde_20_repop_co,
             'agrde_30',       rs.agrde_30_repop_co,
             'agrde_40',       rs.agrde_40_repop_co,
             'agrde_50',       rs.agrde_50_repop_co,
             'agrde_60_above', rs.agrde_60_above_repop_co,
             'mag_10',         rs.mag_10_repop_co,
             'mag_20',         rs.mag_20_repop_co,
             'mag_30',         rs.mag_30_repop_co,
             'mag_40',         rs.mag_40_repop_co,
             'mag_50',         rs.mag_50_repop_co,
             'mag_60_above',   rs.mag_60_above_repop_co,
             'fag_10',         rs.fag_10_repop_co,
             'fag_20',         rs.fag_20_repop_co,
             'fag_30',         rs.fag_30_repop_co,
             'fag_40',         rs.fag_40_repop_co,
             'fag_50',         rs.fag_50_repop_co,
             'fag_60_above',   rs.fag_60_above_repop_co,
             'tot_hshld',      rs.tot_hshld_co,
             'apt_hshld',      rs.apt_hshld_co,
             'non_apt_hshld',  rs.non_apt_hshld_co) end,
           case when wk.quarter is not null then rel.worker_vq end,
           (select max(o.quarter) from district_pop_worker o where o.district_id = h.district_id),
           case when wk.quarter is not null then jsonb_build_object(
             'tot',            wk.tot_wrc_popltn_co,
             'ml',             wk.ml_wrc_popltn_co,
             'fml',            wk.fml_wrc_popltn_co,
             'agrde_10',       wk.agrde_10_wrc_popltn_co,
             'agrde_20',       wk.agrde_20_wrc_popltn_co,
             'agrde_30',       wk.agrde_30_wrc_popltn_co,
             'agrde_40',       wk.agrde_40_wrc_popltn_co,
             'agrde_50',       wk.agrde_50_wrc_popltn_co,
             'agrde_60_above', wk.agrde_60_above_wrc_popltn_co,
             'mag_10',         wk.mag_10_wrc_popltn_co,
             'mag_20',         wk.mag_20_wrc_popltn_co,
             'mag_30',         wk.mag_30_wrc_popltn_co,
             'mag_40',         wk.mag_40_wrc_popltn_co,
             'mag_50',         wk.mag_50_wrc_popltn_co,
             'mag_60_above',   wk.mag_60_above_wrc_popltn_co,
             'fag_10',         wk.fag_10_wrc_popltn_co,
             'fag_20',         wk.fag_20_wrc_popltn_co,
             'fag_30',         wk.fag_30_wrc_popltn_co,
             'fag_40',         wk.fag_40_wrc_popltn_co,
             'fag_50',         wk.fag_50_wrc_popltn_co,
             'fag_60_above',   wk.fag_60_above_wrc_popltn_co) end,
           h.area_m2
    from hit h
    cross join rel
    -- 길단위인구는 그 상권이 가진 **가장 최근 분기** 한 행(색인 (district_id, quarter) 를 거꾸로 한 번 짚는다) ·
    -- 상주·직장은 **표지 max_quarter 분기** 한 행(기본키로 한 번 짚는다 — 없으면 null).
    left join lateral (select o.* from district_pop_flow o
                        where o.district_id = h.district_id order by o.quarter desc limit 1) f on true
    left join district_pop_resident rs on rs.district_id = h.district_id and rs.quarter = rel.resident_mq
    left join district_pop_worker wk on wk.district_id = h.district_id and wk.quarter = rel.worker_mq
  )
  select ro.status, ro.district_id, ro.district_nm, ro.district_type,
         ro.flow_table_quarter, ro.flow_quarter, ro.flow,
         ro.resident_value_quarter, ro.resident_last_quarter, ro.resident,
         ro.worker_value_quarter, ro.worker_last_quarter, ro.worker
  from rows_out ro
  -- 좁은 상권이 더 구체적인 설명이라 먼저 온다(list_building_districts 와 같은 정렬).
  order by ro.sort_area asc, ro.district_id;
$$;

comment on function list_district_pop(text) is
  '결정 0045 이 필지가 속한 서울시 상권마다(좁은 상권 먼저 · 합치지 않는다) 서울시 상권분석서비스가 공표한 '
  '인구 셋 — 길단위인구(flow: 그 상권이 가진 가장 최근 분기 flow_quarter 의 숫자 22칸 · flow_table_quarter = 표 전체 '
  '최신 분기 · 서울시 칸 이름은 「유동인구」 · 단위 미표기) · 상주인구(resident: 표지 seoul_trdar_release 의 그 표 '
  'max_quarter 분기 행의 숫자 24칸 · 가구 셋 포함) · 직장인구(worker: 같은 규칙 · 숫자 21칸). 그 상권이 그 분기 행을 '
  '안 가졌으면(옛 분기에서 끊김) 그 칸은 null 이고 옛 값을 내보내지 않는다 — 그 상권의 마지막 분기는 '
  'resident_last_quarter·worker_last_quarter. '
  '상주·직장은 서울시가 1년 중 4분기에 한 번 값을 바꾸고 다음 해 1·2·3분기가 같은 값이라 「YYYY년 기준」은 '
  'resident_value_quarter·worker_value_quarter(표지의 값이 마지막으로 바뀐 분기 · 표 전체 기준 하나)로 쓴다. '
  '셋 중 그 상권에 자료가 없는 것은 그 칸만 null 이고, 셋 다 없으면 no_data 다. '
  '상권 찾기·status 는 list_district_openclose 와 같은 글이다: no_coord → not_seoul → outside_seoul_district(이 셋은 한 줄만) · '
  '아니면 상권마다 ok / no_data. 값은 상권 단위 공표값이며 이 건물의 인구가 아니다. '
  'security definer (district_pop_*·seoul_trdar_release·district·parcel 이 anon 에게 닫혀 있어 소유자 권한으로 대신 '
  '읽는다. 나가는 것은 상권 이름·종류와 서울시 공표 수뿐이다).';

revoke all on function list_district_pop(text) from public, anon, authenticated;

create or replace function api.list_district_pop(p_pnu text)
returns table (
  status                  text,
  district_id             text,
  district_nm             text,
  district_type           text,
  flow_table_quarter      char(5),
  flow_quarter            char(5),
  flow                    jsonb,
  resident_value_quarter  char(5),
  resident_last_quarter   char(5),
  resident                jsonb,
  worker_value_quarter    char(5),
  worker_last_quarter     char(5),
  worker                  jsonb
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_district_pop(p_pnu) $$;

revoke all on function api.list_district_pop(text) from public, anon, authenticated;
grant execute on function api.list_district_pop(text) to anon, authenticated;

-- ⛔ public.list_district_pop 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.

-- =====================================================================
-- get_data_freshness — 2026-10-29a 판 + 서울 상권 4종 세 줄(13 · 14 · 15)
-- =====================================================================
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
           (select r.published_ym::text from snapshot_release r) as basis,
           'sangkwon'::text             as rule_kind,
           '분기마다 (다음 분기 자료가 공개되면 사람이 적재)'::text as cadence
    union all
    -- 2026-10-15a — 실거래는 매달 최근 6개월을 다시 받는다(사장님 결정 2026-10-15 · 규칙 'tx').
    select 2, '실거래 (매매)', '계약월',
           (select max(t.contract_ym)::text from transaction t),
           'tx',
           '월 1회 (최근 6개월 다시 받기)'
    union all
    -- 2026-10-15a — 기준은 적재일(max(building.updated_at))이 아니라 표지의 판이다(30개 구를 다 넣은 뒤
    --   사람이 올린다). 규칙은 인허가와 같은 월간 갈래 — 건축HUB 일괄 파일도 다음 달 20일 무렵 게시된다.
    select 3, '건축물대장', '판',
           (select r.release_ym::text from ledger_release r),
           'permit',
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
    -- ⓘ 9번(옛 성적표 줄)은 2026-10-18a(결정 0041)에 뺐다 — 뒤 번호는 그대로 둔다(순서만 정하는 칸이다).
    -- 2026-10-12b — 기준은 우리가 받아 둔 날(updated_at)이 아니라 개별공시지가의 공시 연도다
    --   (사장님 결정 2026-10-12). smallint 라 '2026' 네 자리로 나온다.
    select 10, '필지 (토지 특성)', '공시 연도',
           (select max(t.land_price_year)::text from parcel t),
           'land_year',
           '연 1회 (브이월드)'
    union all
    -- 결정 0033 — 서울시 상권분석서비스 개업·폐업. 분기 꼴이 'YYYYQ' 다섯 자리(Q 없음)다.
    select 11, '상권 개업·폐업 (서울시)', '분기',
           (select max(t.quarter)::text from district_openclose t),
           'seoul_openclose',
           '분기마다'
    union all
    -- 2026-10-29a(결정 0044) — 대전시 동네 폐업. 기준 = 사람이 대전시 사이트에서 받은 날(표지 한 줄)이다.
    select 12, '동네 폐업 (대전시)', '받은 날',
           (select r.received_on::text from daejeon_closure_release r),
           'daejeon_closure',
           '분기마다 (사람이 대전시 사이트에서 받음)'
    union all
    -- 2026-10-31a(결정 0045) — 서울시 상권분석서비스 추정매출·길단위인구. 분기 꼴은 개업·폐업과 같은 'YYYYQ' 라
    --   같은 규칙(seoul_openclose — 분기말 + 5개월 - 하루)을 쓴다.
    select 13, '상권 추정매출 (서울시)', '분기',
           (select max(t.quarter)::text from district_sales t),
           'seoul_openclose',
           '분기마다'
    union all
    select 14, '상권 길단위인구 (서울시)', '분기',
           (select max(t.quarter)::text from district_pop_flow t),
           'seoul_openclose',
           '분기마다'
    union all
    -- 2026-10-31a(결정 0045 · 사장님 결정 10-31 「다음 예정 없음」) — 상주·직장인구는 한 줄. 기준 = 값이 마지막으로
    --   바뀐 분기 둘을 글로 합친다(표지 seoul_trdar_release). 서울시 공지는 연 1회지만 실제 갱신이 불규칙(상주
    --   2024·2025 건너뜀)이라 예정일을 계산하지 않는다('none' → null). 표지가 비면 basis 도 null(화면 '자료 없음').
    select 15, '상권 상주·직장인구 (서울시)', '값이 바뀐 분기',
           (select '상주 ' || left(a.value_quarter, 4) || '년 ' || right(a.value_quarter, 1) || '분기, 직장 '
                   || left(b.value_quarter, 4) || '년 ' || right(b.value_quarter, 1) || '분기'
              from seoul_trdar_release a, seoul_trdar_release b
             where a.tbl = 'district_pop_resident' and b.tbl = 'district_pop_worker'),
           'none',
           '연 1회 (서울시 공지) · 실제는 불규칙 — 예정일 계산 안 함'
  ),
  norm as (
    -- 분기 규칙을 쓰는 세 줄을 **같은 모양('YYYYMM' 분기말 달)** 으로 맞춘다. 이렇게 해야
    -- 아래 계산이 한 번만 적힌다 — 세 벌로 적어 두면 한쪽만 고쳐지는 날 자료끼리 서로
    -- 다른 주기를 말한다.
    -- ⛔ 서울시 분기 꼴('20262')은 둘째 갈래(`YYYYQn`)에도 첫째 갈래(여섯 자리)에도 안 걸린다 —
    --   셋째 갈래가 없으면 그 줄은 에러 없이 '정해진 주기 없음'(null)이 된다(결정 0033 v3 재검사).
    select r.*,
           case
             when r.rule_kind = 'sangkwon' and r.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
               then r.basis
             when r.rule_kind = 'rone' and r.basis ~ '^\d{4}Q[1-4]$'
               then left(r.basis, 4) || lpad((right(r.basis, 1)::int * 3)::text, 2, '0')
             when r.rule_kind = 'seoul_openclose' and r.basis ~ '^\d{4}[1-4]$'
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
           -- 월간 자료(인허가 기준월 · 건축물대장 판): 다음 판이 **공개되는 달**의 말일(기준월 + 3개월 - 하루).
           when n.rule_kind = 'permit' and n.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
             then (to_date(n.basis, 'YYYYMM') + interval '3 months' - interval '1 day')::date
           -- 실거래: 계약월 + 2개월 - 하루(사장님 결정 2026-10-15 — 매달 최근 6개월을 다시 받는다).
           when n.rule_kind = 'tx' and n.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
             then (to_date(n.basis, 'YYYYMM') + interval '2 months' - interval '1 day')::date
           -- 연 1회: 다음 해 3월 31일(국세청 고시가 매년 3월).
           when n.rule_kind = 'nts' and n.basis ~ '^\d{4}-\d{2}-\d{2}$'
             then make_date(left(n.basis, 4)::int + 1, 3, 31)
           -- 연 1회: 개별공시지가는 공시 연도의 다음 해 6월 30일(사장님 결정 2026-10-12).
           --   네 자리 연도일 때만 — 모양이 다르면 ::int 가 터져 표가 통째로 사라진다.
           when n.rule_kind = 'land_year' and n.basis ~ '^\d{4}$'
             then make_date(n.basis::int + 1, 6, 30)
           -- 대전시 동네 폐업: 받은 날 + 3개월(분기마다 사람이 받는다 — 2026-10-29a · 결정 0044).
           --   'YYYY-MM-DD' 일 때만 — 모양이 다르면 ::date 가 터져 표가 통째로 사라진다.
           when n.rule_kind = 'daejeon_closure' and n.basis ~ '^\d{4}-\d{2}-\d{2}$'
             then (n.basis::date + interval '3 months')::date
         end as next_expected,
         n.cadence
  from norm n
  order by n.ord;
$$;

comment on function get_data_freshness() is
  '화면 아래 "이 자료는 언제 것인가" 표. 열넷 갈래 자료의 가장 최근 도장(분기·계약월·판·'
  '계산일·수집일·기준월·고시일·공시 연도·받은 날·값이 바뀐 분기)을 창고에서 읽어 한 줄씩 준다. '
  '⛔ 숫자를 화면에 박지 않기 위한 함수다 — 신선도를 글자로 적어 두면 적재하는 순간부터 '
  '그 글자만 거짓말을 한다. next_expected 도 사람이 적는 값이 아니라 규칙으로 계산한다: '
  '분기 자료는 분기말 달 + 5개월 - 하루(다음 분기가 공개되는 달의 말일 — 분기 꼴 셋 '
  '''YYYYMM''·''YYYYQn''·''YYYYQ''(서울시 다섯 자리)를 같은 분기말 달로 맞춘 뒤 한 번만 계산), 월간 자료'
  '(인허가 기준월·건축물대장 판)는 기준월 + 3개월 - 하루(다음 판이 공개되는 달의 말일), 실거래는 계약월 + '
  '2개월 - 하루(매달 최근 6개월을 다시 받는다), 국세청 기준시가는 고시일의 다음 해 3월 31일, '
  '필지(개별공시지가)는 공시 연도의 다음 해 6월 30일(기준값이 네 자리 연도일 때만), 대전시 동네 폐업은 '
  '받은 날 + 3개월(분기마다 사람이 받는다 · 기준값이 YYYY-MM-DD 일 때만). 서울 상권 추정매출·길단위인구는 '
  '개업·폐업과 같은 분기 규칙이고, 서울 상권 상주·직장인구는 실제 갱신이 불규칙해 예정일을 계산하지 않는다'
  '(기준 = 값이 마지막으로 바뀐 분기 둘을 글로 합침). '
  '주기가 없는 자료는 null 이다 — 없는 주기를 지어내면 "늦었다"는 거짓 신호가 뜬다. '
  '기준값이 그 모양이 아니면 계산하지 않고 그 칸만 비운다(to_date 가 터지면 표가 통째로 '
  '사라진다). timestamptz 는 전부 Asia/Seoul 로 옮겨 날짜를 자른다 — 이 DB 가 UTC 라 '
  '그냥 자르면 한국 새벽 0~9시에 어제 날짜가 찍힌다. '
  '⛔ api_quota_log 는 안 본다 — 그건 우리 호출 장부이지 자료의 나이가 아니고, 하한선일 뿐이다. '
  '자료가 0행이면 basis 가 null 이고 줄은 그대로 나온다(화면이 "자료 없음"이라 적는다 — '
  '줄을 빼면 "그런 자료를 안 쓴다"로 읽힌다). '
  'security definer (열넷 표가 전부 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 집계 도장 열네 개뿐이고 원본 행은 한 줄도 안 나간다). 2026-09-05d · 월간 규칙 2026-10-01a · '
  '서울 개업·폐업 2026-10-05b · 필지 공시 연도 2026-10-12b · 실거래·대장 판 월간 규칙 2026-10-15a · '
  '성적표 줄 뺌 2026-10-18a(결정 0041) · 대전시 동네 폐업 2026-10-29a(결정 0044) · 서울 상권 4종 세 줄 2026-10-31a(결정 0045)';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function get_data_freshness() from public, anon, authenticated;

commit;

notify pgrst, 'reload schema';
