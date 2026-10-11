-- =====================================================================
-- 2026-10-11c — 건물 표에 승강기·호수·구조·내진·에너지 칸을 싣는다 (물결 2-1 PR① · 결정 0036)
-- =====================================================================
-- 왜
-- --
-- 건축물대장 표제부 원본(`data/raw/bldrgst_bulk_converted/<구>/title.jsonl` 의 item)에는 승강기 대수
-- (`rideUseElvtCnt` 승용 · `emgenUseElvtCnt` 비상용) · 호수(`hoCnt`) · 구조(`strctCdNm`) · 내진 설계
-- 적용 여부(`rserthqkDsgnApplyYn`) · 내진 능력(`rserthqkAblty`) · 에너지 효율 등급(`engrGrade`) ·
-- 녹색 건축 등급(`gnBldGrade`)이 이미 들어 있는데, 적재기가 안 담아 `building` 에 칸이 없다.
-- 이 파일은 **DB 만** 바꾼다(칸 8개 + 화면 창구 둘). 값은 적재기를 `--building-only` 로 다시 돌려 채우고,
-- 화면(층별 화면·검색 결과 줄)은 다음 PR② 다. 화면 타입은 새 칸을 선택 칸으로 받을 것이라
-- 이 파일이 먼저 라이브에 올라가도 지금 화면은 그대로 선다(옛 화면은 새 칸을 무시한다).
--
-- 무엇을 바꾸나
-- -------------
--   ① building 끝에 칸 8개(원값 그대로 — 0 은 0, 빈 문자열은 NULL. 뜻풀이는 화면 몫 · 2026-08-24a 와 같은 원칙):
--        elevator_ride smallint · elevator_emgen smallint · ho_cnt integer · strct_nm text ·
--        seismic_design boolean('1'→true · '0'→false · 빈값·그 밖→NULL) · seismic_ability text ·
--        energy_grade text · green_grade text  (+ 칸 comment 8)
--      ⛔ 승강기·호수의 0 에는 대장 미기재가 섞여 있다(2026-10-11 실측: 강남 지상 11층 이상의 24% 가
--         승강기 0). ⛔ 내진 false 에는 1988년 전 건물(법이 없던 때)·미기재가 섞여 있다.
--   ② api.building 을 다시 만든다 — 적재기는 REST 로 쓰는데 profile 헤더를 안 보내 PostgREST 의 **첫 스키마
--      (api)** 를 탄다(2026-08-22e 머리말 · pgrst.db_schemas = 'api, graphql_public'). `select *` 뷰는 만든
--      날의 칸으로 굳어 있어, 안 고치면 적재기 upsert 가 새 칸을 못 찾는다(PGRST204 — 2026-10-08a 와 같은 일).
--   ③ v_floor_stack 맨 뒤에 5칸(elevator_ride · elevator_emgen · ho_cnt · strct_nm · seismic_design) +
--      api.v_floor_stack 재생성(2026-08-24a 꼴). ⛔ 내진 능력·에너지 등급·녹색 등급은 **내보내지 않는다**
--      (채움 0.4~8.5% — 사장님 결정 2026-10-11). 표에만 둔다.
--   ④ search_buildings + api 쌍둥이 — 기존 16칸 **뒤에** ho_cnt · elevator_ride · elevator_emgen
--      (2026-10-09a 꼴: 결과를 lim 행으로 줄인 뒤 마지막 select 에서 building 을 기본키로 읽는 그 조인
--      `bo` 에서 꺼낸다 — 검색 가지는 한 글자도 안 바꾼다).
--
-- 바꾸지 않는 것
-- --------------
--   · 공개 호출 허용 목록(post_load.py --check 총계 30) — 새 함수가 없고 search_buildings 의 이름·인자가
--     그대로다. 뷰 둘은 이미 열린 뷰에 칸이 붙는 것이라 그 점검(표·뷰·함수 단위)이 세지 않는다 —
--     새 칸은 건축물대장 공개 항목이다(2026-08-24a 와 같은 판단).
--   · public.v_floor_stack 의 권한 — `create or replace view` 는 권한을 보존한다(2026-10-07a 와 같은 줄 ·
--     옵션 security_invoker 만 다시 적는다).
--
-- 왜 search_buildings 는 drop 인가
-- --------------------------------
-- `returns table` 의 칸은 OUT 파라미터라 칸을 더하면 `create or replace` 가 거부한다(2026-10-09a 머리말).
-- 지우고 다시 만들면 권한과 comment 도 사라진다 → comment 는 정본에서 잘라 다시 달고, api 쌍둥이에 실행
-- 권한을 다시 준다(public 원본은 revoke 만 — CLAUDE.md 🚪). 부르는 쪽(api)부터 지운다.
-- 이 함수를 부르는 다른 DB 객체는 api 쌍둥이 하나뿐 · v_floor_stack 에 기대는 것은 api.v_floor_stack 하나뿐 ·
-- building 을 `select *` 로 읽는 것은 api.building 하나뿐이다(정본 grep 2026-10-11).
--
-- 잠금 (PostgreSQL 17 문서)
-- -------------------------
--   · `alter table … add column` — ACCESS EXCLUSIVE(sql-altertable: "An ACCESS EXCLUSIVE lock is acquired
--     unless explicitly noted" — ADD COLUMN 은 따로 적힌 예외가 아니다). 기본값 없는 NULL 칸이라 표를 다시
--     쓰지 않지만 잠금은 **commit 까지** 이어진다 — 그동안 건물을 읽는 화면(층별 화면·검색)은 오류가 아니라
--     잠깐 기다림이다. 이 덩어리에는 굽기·훑기가 없어(전부 메타데이터) 곧 commit 한다.
--   · `create or replace view` — 그 뷰에 ACCESS EXCLUSIVE(2026-10-07a 머리말과 같은 판단) · `drop function` —
--     그 함수 객체에 잠금.
--   · `lock_timeout = '2s'` 는 **begin 앞**(세션 설정)에 둔다 — 오래 도는 조회가 building 을 쥐고 있어 2초 넘게
--     못 잡으면 덩어리가 통째로 되돌아가 아무것도 안 바뀐다. 다시 돌리면 된다(칸 추가는 `if not exists`).
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 검색 쌍둥이를 지운 뒤 끊기면 화면 검색이 통째로 사라진 채 남는다 —
-- 한 덩어리로 묶는다. `notify pgrst` 는 commit **뒤**.
--
-- 실행 순서 (DB 먼저 → 값 채우기 → 화면 PR②)
-- ------------------------------------------
--   ① 이 파일(머지 뒤 · 본 폴더 main · 사람 적은 시간):
--        python scripts/dbx.py -f supabase/migrations/2026-10-11c_building_elevator_ho.sql
--   ② 구마다 값 채우기 — 건물 표만(층·호실은 안 건드린다):
--        python scripts/collectors/load_building_ledger.py --raw-dir data/raw/bldrgst_bulk_converted/<구> --snapshot-ym 202606 --building-only --dry-run
--        python scripts/collectors/load_building_ledger.py --raw-dir data/raw/bldrgst_bulk_converted/<구> --snapshot-ym 202606 --building-only
--      ⛔ ① 보다 먼저 돌리면 upsert 가 새 칸을 못 찾아 PGRST204 로 멈춘다(넣은 것 0 — ① 뒤 다시 돌리면 된다).
--      ⛔ ① 뒤에는 `--building-only` 없는 평소 적재도 새 칸을 싣는다(같은 칸 목록 — 적재기 build_building_record).
--   ③ python scripts/post_load.py → python scripts/post_load.py --check (exit 0)
--   ④ 화면 PR② 머지.
--
-- 적용 뒤 확인
-- ------------
--   select column_name, data_type from information_schema.columns
--    where table_schema = 'api' and table_name = 'building'
--      and column_name in ('elevator_ride','elevator_emgen','ho_cnt','strct_nm','seismic_design',
--                          'seismic_ability','energy_grade','green_grade') order by 1;          -- 8줄
--   select column_name from information_schema.columns
--    where table_schema = 'api' and table_name = 'v_floor_stack'
--      and column_name in ('elevator_ride','elevator_emgen','ho_cnt','strct_nm','seismic_design',
--                          'seismic_ability','energy_grade','green_grade') order by 1;          -- 5줄(능력·등급 둘 없음)
--   select ho_cnt, elevator_ride, elevator_emgen from api.search_buildings('타워', 3, '11680'); -- 3칸 · 오류 0
--   (② 뒤) select count(*) filter (where elevator_ride is not null), count(*) filter (where seismic_design)
--          from building;                                                                      -- 0 보다 크다
--   python scripts/post_load.py --check                                                        -- exit 0
--
-- 되돌리기
-- --------
-- **새 마이그레이션 파일**로: set lock_timeout → begin → api 쌍둥이 drop → public drop → 2026-10-09a 의
-- `search_buildings` 정의(16칸)와 comment → public revoke → 16칸 api 쌍둥이 → api revoke·grant →
-- (v_floor_stack 의 칸은 `create or replace` 로 못 지운다 — 남겨도 화면이 안 읽으면 그만이다. 꼭 지우려면
-- 2026-08-24a 되돌리기 절) → commit → notify. building 칸은 남겨도 해가 없다.
-- 정본 schema.sql 은 PR revert 로 함께 되돌린다. 적용된 이 파일은 고치지 않는다(원장).

set lock_timeout = '2s';

-- ⛔ 여기부터 commit 까지가 **한 덩어리**다(위 머리말 참조).
begin;

-- ① 칸 8개 — 표 맨 뒤에(기존 칸 순서는 그대로). 기본값 없는 NULL 칸이라 표를 다시 쓰지 않는다.
alter table building
  add column if not exists elevator_ride   smallint,
  add column if not exists elevator_emgen  smallint,
  add column if not exists ho_cnt          integer,
  add column if not exists strct_nm        text,
  add column if not exists seismic_design  boolean,
  add column if not exists seismic_ability text,
  add column if not exists energy_grade    text,
  add column if not exists green_grade     text;

comment on column building.elevator_ride is
  '승용 승강기 대수(건축물대장 표제부 rideUseElvtCnt 원값 · 빈값 NULL). '
  '0 = 대장 미기재가 섞여 있다(2026-10-11 실측: 강남 지상 11층 이상의 24% 가 승강기 0) — 뜻풀이는 화면 몫(2026-10-11c)';
comment on column building.elevator_emgen is
  '비상용 승강기 대수(표제부 emgenUseElvtCnt 원값 · 빈값 NULL). '
  '0 = 대장 미기재가 섞여 있다(2026-10-11 실측: 강남 지상 11층 이상의 24% 가 승강기 0) — 뜻풀이는 화면 몫(2026-10-11c)';
comment on column building.ho_cnt is
  '호수(표제부 hoCnt 원값 · 빈값 NULL). '
  '0 = 대장 미기재가 섞여 있다(2026-10-11 실측: 강남 지상 11층 이상의 24% 가 승강기 0 — 같은 대장의 같은 결) — 뜻풀이는 화면 몫(2026-10-11c)';
comment on column building.strct_nm is
  '구조 이름(표제부 strctCdNm 원값 · 빈값 NULL)(2026-10-11c)';
comment on column building.seismic_design is
  '내진 설계 적용 여부(표제부 rserthqkDsgnApplyYn — ''1''=true · ''0''=false · 빈값·그 밖=NULL). '
  '1988년 전 건물은 거의 다 false — 법이 없던 때이고 미기재와 섞여 있다 · 화면은 true 일 때만 적는다(2026-10-11c)';
comment on column building.seismic_ability is
  '내진 능력(표제부 rserthqkAblty 원값 · 빈값 NULL). 채움 0.4~8.5% — 화면에 안 낸다(사장님 결정 2026-10-11 · 2026-10-11c)';
comment on column building.energy_grade is
  '에너지 효율 등급(표제부 engrGrade 원값 · 빈값 NULL). 채움 0.4~8.5% — 화면에 안 낸다(사장님 결정 2026-10-11 · 2026-10-11c)';
comment on column building.green_grade is
  '녹색 건축 등급(표제부 gnBldGrade 원값 · 빈값 NULL). 채움 0.4~8.5% — 화면에 안 낸다(사장님 결정 2026-10-11 · 2026-10-11c)';

-- ② 표에 더한 칸을 적재기의 문(api.building)에도 싣는다 — `select *` 는 만든 날의 칸으로 굳는다.
create or replace view api.building         as select * from public.building;
revoke all on api.building         from public, anon, authenticated;
grant select, insert, update, delete on api.building         to service_role;

-- ③ 층별 화면 뷰 — 기존 목록 그대로 + 끝에 5칸(정본 schema.sql 과 글자 그대로).
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
  st_x(p.geom)::double precision as lng,
  -- ── 2026-10-11c 가 더한 건물 사양 5칸 (물결 2-1 · 결정 0036) ─────────────────
  -- 위 스펙 4칸과 같은 결 — **건물 한 채**의 값이라 층마다 되풀이되고, 원값 그대로 낸다.
  -- ⛔ 승강기·호수의 0 에는 대장 미기재가 섞여 있다(2026-10-11 실측: 강남 지상 11층 이상의
  --    24% 가 승강기 0) — "없음"으로 읽을지는 화면 한 곳이 정한다.
  -- ⛔ 내진 false 에는 1988년 전 건물(법이 없던 때)·미기재가 섞여 있다 — 화면은 true 일 때만 적는다.
  -- ⛔ 내진 능력·에너지 효율 등급·녹색 건축 등급은 여기서 **내보내지 않는다**(채움 0.4~8.5% —
  --    사장님 결정 2026-10-11). 표(building)에만 있다.
  b.elevator_ride,          -- 승용 승강기 대수 (0 = 미기재 섞임)
  b.elevator_emgen,         -- 비상용 승강기 대수 (0 = 미기재 섞임)
  b.ho_cnt,                 -- 호수 (0 = 미기재 섞임)
  b.strct_nm,               -- 구조 이름 (빈값 = NULL)
  b.seismic_design          -- 내진 설계 적용 여부 (false 에 1988년 전·미기재 섞임)
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
    and ub.snapshot_ym = (select r.published_ym from snapshot_release r)
) st on true;

-- create or replace view 는 뷰 옵션을 새 정의(옵션 없음)로 갈아 끼운다 — 정본과 같게 다시 적는다.
alter view v_floor_stack set (security_invoker = false);

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
  '⚠️ elevator_ride·elevator_emgen·ho_cnt·strct_nm·seismic_design 도 건물 한 채의 원값이다(2026-10-11c). '
  '승강기·호수 0 에는 대장 미기재가 섞여 있고 seismic_design false 에는 1988년 전 건물·미기재가 섞여 있다 — '
  '뜻풀이는 화면이 한다. 내진 능력·에너지·녹색 등급은 표에만 있고 이 뷰는 내보내지 않는다(채움이 낮다). '
  'ℹ️ 린트 0010(security definer view) 의도적 예외 — security_invoker=true로 되돌리면 원본 표 401 + 상호명·성명 노출 확대. '
  '재검토 방아쇠: 공개 배포일 / 지도·반경 검색(§6.4) 착수일';

-- api 쌍둥이 재생성 — `select *` 는 만들 때 굳는다(public 뷰 교체 **뒤**에 와야 새 칸을 본다).
create or replace view api.v_floor_stack as select * from public.v_floor_stack;
-- 먼저 회수하고 준다(grant 는 더하기라 자동으로 붙은 쓰기 권한을 못 걷어낸다 — 2026-08-24a).
revoke all on api.v_floor_stack     from public, anon, authenticated;
grant select on api.v_floor_stack     to anon, authenticated;

-- ④ 검색 — 돌려주는 칸이 늘어 replace 가 거부된다 → api(부르는 쪽)를 먼저 지운다.
drop function if exists api.search_buildings(text, int, text);
drop function if exists search_buildings(text, int, text);

-- public 원본 — 정본 schema.sql 과 글자 그대로(머리 속성·본문·comment).
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
  total_cnt      bigint,
  -- 소유 구조 세 칸(2026-10-09a · 결정 0036 결정 5) — building 원값 그대로(null 은 null,
  -- 0 은 0). '미상' 판정은 화면 몫이다. ⛔ 기존 13칸 **뒤에만** 붙인다 — 칸은 자리로
  -- 맞춰지므로 앞에 끼우면 api 쌍둥이·화면이 칸을 엇갈려 읽는다.
  is_jiphap      boolean,
  approve_date   date,
  parking_cnt    integer,
  -- 건물 사양 세 칸(2026-10-11c · 물결 2-1) — building 원값 그대로(0 은 0 — 승강기·호수의 0 에는
  -- 대장 미기재가 섞여 있다). ⛔ 기존 16칸 **뒤에만** 붙인다(위 세 칸과 같은 이유).
  ho_cnt         integer,
  elevator_ride  smallint,
  elevator_emgen smallint
)
language plpgsql
stable
security definer
set search_path = public
set plan_cache_mode = force_custom_plan
as $$
#variable_conflict use_column
begin
  return query
with pat as not materialized (
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
       -- ⛔ `::char(5)` 를 지우지 말 것 — 컬럼이 char(5) 인데 text 와 견주면 **컬럼 쪽**이
       --    text 로 캐스트돼 색인이 Index Cond 가 아니라 Filter 로 떨어진다(라이브 실측
       --    2026-09-10: Parallel Seq Scan 188,442행·버퍼 5,312·116ms → Index Scan 12,138행·버퍼 353·8ms).
       --    형제 `search_stores` 가 같은 처방을 쓴다(결정 0028 §백로그).
       -- ⚠️ 5자보다 긴 입력은 bpchar 캐스트가 조용히 자른다 — 구 코드는 서버 목록에서만
       --    오고 화면도 /^\d{5}$/ 로 막으므로(src/lib/urlState.ts) 실사용 0건이다.
       -- ⛔ `pat.gu is null or` 절반은 그대로 둔다 — 이 함수는 구를 안 고른 전국 검색을
       --    일부러 허용한다(구 없이는 답이 안 되는 `search_stores` 와 다른 점이다).
       and (pat.gu is null or pc.sigungu_code = pat.gu::char(5))
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
       and (pat.gu is null or pc.sigungu_code = pat.gu::char(5))
       and (pat.gu is null or (b.pnu >= pat.gu::char(19)
                                     and b.pnu <= (pat.gu || repeat('9',14))::char(19)))
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
    t.total_cnt,
    bo.is_jiphap, bo.approve_date, bo.parking_cnt,
    bo.ho_cnt, bo.elevator_ride, bo.elevator_emgen
  from top t
  join mv_search_parcel pc on pc.pnu = t.pnu
  join parcel p on p.pnu = t.pnu
  -- ③ 소유 구조 세 칸(2026-10-09a)은 결과를 줄인 **뒤** 기본키(bld_id)로 한 번 더 읽는다 —
  --    lim 행(최대 100)번의 색인 조회다. ⛔ 위 hit·nm 가지에 실어 나르지 말 것 — 검색 가지는
  --    낱말 하나에도 민감하다(가지 2→3 에 763→1,550ms · search_stores 머리말).
  --    top 의 bld_id 는 building 에서 왔으므로 이 조인은 행을 줄이지 않는다.
  --    건물 사양 세 칸(2026-10-11c)도 같은 조인에서 꺼낸다 — 조인을 하나 더 두지 않는다.
  join building bo on bo.bld_id = t.bld_id
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
end;
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
  'is_jiphap·approve_date·parking_cnt 는 building 원값 그대로다(2026-10-09a) — null·0 을 '
  '"미상"으로 읽을지는 화면이 정한다. '
  'ho_cnt·elevator_ride·elevator_emgen 도 building 원값 그대로다(2026-10-11c) — 0 에는 대장 미기재가 섞여 있다. '
  '⛔ 주소 가지와 이름 가지를 OR로 합치지 말 것 — 두 조인 테이블에 걸친 OR은 gin_trgm 인덱스를 무력화한다';

-- ⛔ public 원본에는 grant 를 주지 않는다 — 화면은 api 쌍둥이로만 들어온다(CLAUDE.md 🚪).
revoke all on function search_buildings(text, int, text) from public, anon, authenticated;

-- api 쌍둥이 — 같은 19칸 · security definer · 빈 search_path · public. 완전수식(정본 그대로).
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
  total_cnt      bigint,
  is_jiphap      boolean,
  approve_date   date,
  parking_cnt    integer,
  ho_cnt         integer,
  elevator_ride  smallint,
  elevator_emgen smallint
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.search_buildings(q, lim, sigungu) $$;

-- ⚠️ drop 으로 권한이 함께 사라졌다 — 다시 주지 않으면 검색이 permission denied 로 죽는다
--    (2026-08-13 401 전례 · 2026-08-14e 머리말). 먼저 회수하고 준다(정본의 api 권한 줄과 같은 꼴).
revoke all on function api.search_buildings(text, int, text)  from public, anon, authenticated;
grant execute on function api.search_buildings(text, int, text)  to anon, authenticated;

commit;

-- ⛔ 커밋 **뒤**여야 한다 — 표·뷰·결과 칸이 바뀌었으니 PostgREST 가 스키마 캐시를 다시 읽어야
--    새 칸을 낸다(적재기 upsert 도 새 칸을 못 찾는다 — PGRST204). 롤백된 판에서 헛알림이 가지 않게.
notify pgrst, 'reload schema';
