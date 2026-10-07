-- =====================================================================
-- 실거래 지분 표시 칸 + 단가 계산에서만 제외 — transaction.is_share (2026-10-08a)
-- =====================================================================
-- 결정 0036 물결 0-2b 의 PR①(👤 2026-10-08 결정). 조사 = docs/research/share-deals-2026-10.md.
--
-- 왜
-- --
-- 국토부 상업업무용 실거래 원본에는 `shareDealingType` 칸이 있고 값은 정확히 두 가지다
-- (raw 40파일 336,693줄 실측 — ' ' 317,956 · '지분' 18,737). 지분 거래는 건물 일부 몫만 사고판
-- 거래라 같은 구·같은 층 일반 거래보다 ㎡당 값이 **약 0.39배**로 낮게 나온다. 그런데 적재기가
-- 이 칸을 안 읽어, 참고 시세·구 층대 단가·동네 단가 흐름이 지분 거래를 일반 거래처럼 섞어
-- 왔다(집합 거래의 4.8% — 261,065건 중 12,467건).
--
-- 무엇이 바뀌나
-- -------------
--   ① transaction 에 칸 하나 — is_share boolean not null default false (+ 칸 주석).
--      값은 적재기(load_transactions.py)가 다음 재적재 때 채운다. 그 전까지는 전부 false 라
--      **오늘 숫자는 하나도 안 바뀐다**(지분을 뺄 행이 아직 표시돼 있지 않다).
--   ② api.transaction 뷰를 다시 만든다 — `select *` 뷰는 **만든 날의 칸으로 굳어** 있어 표에 칸을
--      더해도 뷰에는 안 생긴다. 적재기 upsert 는 REST(= 이 뷰)로 쓰므로 안 고치면 새 칸을 못 넣는다
--      (PGRST204). 칸을 끝에 더하는 것은 `create or replace view` 로 된다(2026-10-04a 선례).
--   ③ list_parcel_transactions + api 쌍둥이 — 돌려주는 칸 끝에 is_share. 지분 거래도 **지우지 않고**
--      낸다(화면이 그 줄에 '지분' 꼬리표). ⛔ 돌려주는 칸이 바뀌면 `create or replace` 가 거부된다
--      ("cannot change return type") → 부르는 쪽(api)부터 지우고 다시 만든다(2026-10-04a 와 같은 순서).
--   ④ mv_sigungu_tx_stats(구 × 층대 단가) — 지분 거래 제외(where). 칸 구성은 그대로.
--   ⑤ mv_sigungu_tx_yearly(동네 단가 흐름) — 단가 셋·n·median_area_m2 에서만 제외(filter).
--      n_all·floor_missing·ym_cnt·first_ym·last_ym 은 지분도 그대로 센다(👤 결정 — 건수엔 센다).
--      ⛔ 물질화뷰는 정의를 고칠 수 없다(`alter materialized view` 에 그런 길이 없다) → 떨어뜨리고
--      다시 만든다. `if not exists` 로 다시 만들면 아무 일도 안 한다(에러 0 — 2026-09-09b 머리말).
--   ⑥ list_price_bands — 사다리 네 갈래(L2·L4·L5·L6) **모두** 지분 거래 제외. 반환 칸·서명이 그대로라
--      `create or replace` 로 된다. ⛔ 머리(security definer · set search_path · stable)와 comment 는
--      정본에서 그대로 잘라 붙였다(create or replace 는 머리 속성을 새 정의로 덮어쓴다).
--
-- 바꾸지 않는 것
-- --------------
--   · mv_tx_parcel_geog — "거래가 한 건이라도 있는 필지"라는 가장 넓은 상한만 진다(정본 그 자리 주석
--     "거래 조건을 좁히지 말 것, L4·L5 가 건다"). L4·L5 가 거래 쪽에서 지분을 거르므로 여기선 안 건다.
--   · get_data_freshness 의 max(contract_ym) · get_sigungu_tx_stats · get_sigungu_tx_yearly.
--     두 get_ 함수는 `language sql` + `as $$ … $$`(문자열 본문)이라 물질화뷰에 대한 의존이 기록되지
--     않는다 → 뷰를 떨어뜨려도 막히지 않고, 같은 이름·같은 칸으로 다시 세우면 그대로 읽는다
--     (반환 칸이 안 바뀌어 다시 만들 이유가 없다 — 정본 본문과 2026-09-09b 본문도 그대로다).
--   · 공개 호출 허용 목록(post_load.py --check) — 함수 이름·서명이 그대로라 늘지 않는다.
--
-- 잠금
-- ----
-- `alter table … add column … default false` 는 ACCESS EXCLUSIVE 잠금을 잡는다(PostgreSQL 문서
-- ALTER TABLE — 따로 적힌 예외가 아니면 ACCESS EXCLUSIVE). 기본값이 상수라 표를 다시 쓰지는 않지만
-- (PostgreSQL 11+ — 휘발성 기본값일 때만 다시 쓴다), 잠금은 **commit 까지** 이어진다. 이 파일은
-- 같은 덩어리 안에서 32만 행을 훑어 물질화뷰 둘을 다시 굽는다 — 운영 읽기 실측으로 MV 두 개 굽기
-- 각 1초 안팎(10-08 07:04). 그동안 실거래를 읽는 화면(실거래 기록 카드·참고 시세)은 오류가 아니라
-- 잠깐 기다림이다 → 그래도 **사람 적은 시간에** 적용한다.
-- `lock_timeout = '2s'` 는 **begin 앞**(세션 설정)에 둔다 — 오래 도는 조회가 표를 쥐고 있어 2초 넘게
-- 못 잡으면 트랜잭션이 통째로 되돌아가 아무것도 안 바뀐다. 다시 돌리면 된다(칸 추가는 `if not exists`).
-- ⓘ 두 덩어리로 나누면 잠금은 짧아지지만, 가드 tests/test_migration_atomicity.py 가 "첫 commit 뒤의
--   DDL"을 빨강으로 본다(한 파일 = 한 덩어리 규칙) — 그래서 한 덩어리로 둔다.
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 함수·뷰를 지운 뒤 끊기면 실거래 기록 카드·구 단가·동네 단가
-- 흐름이 통째로 사라진 채 남고 post_load.py 의 refresh 가 "그런 뷰 없음"으로 멈춘다 — 한 덩어리로
-- 묶는다. `notify pgrst` 는 commit **뒤**.
--
-- 운영 절차 (순서가 중요하다 — 적재기보다 마이그레이션이 **먼저**. 거꾸로면 적재기 upsert 가
-- is_share 칸을 못 찾아 PGRST204 로 멈춘다)
-- ------------------------------------------------------------------------------------------
--   ⓪ 적용 직전 기록: 디스크 %(Supabase 대시보드) · `select pg_total_relation_size('transaction');`
--      → **85% 이상이면 멈춘다**(디스크 확장 먼저 — 재적재가 32만 행을 다시 써 표가 한 번 커진다).
--   ① 머지 직후 같은 자리(본 폴더 main)에서 적용:
--        python scripts/dbx.py -f supabase/migrations/2026-10-08a_transaction_share_flag.sql
--   ② 적용 직후·재적재 **전**에 기록(칸이 생겼고 전부 false · 지금 327,183행):
--        select count(*), count(*) filter (where is_share) from transaction;
--        select sum(n_all), sum(floor_missing) from mv_sigungu_tx_yearly;
--   ③ 구마다 미리보기로 '옛 행 정리 대상 N행'을 먼저 보고 기록한다(DB 쓰기 0 — 단 collect_progress 는 읽는다):
--        python scripts/collectors/load_transactions.py --sigungu-code <구> --dry-run
--      → 출력의 「[transaction] --dry-run — 정리 대상 N행」. 정리 행이 있으면 ⑤ 의 n_all 감소는
--        지분과 무관하다(seq 재압축으로 남은 옛 행 — make_tx_id 참조).
--   ④ 40개 구 재적재를 **끊지 않고** 끝까지(tx_id 가 그대로라 같은 행을 갱신한다):
--        python scripts/collectors/load_transactions.py --sigungu-code <구>
--      → python scripts/post_load.py → python scripts/post_load.py --check
--   ⑤ 검산:
--        select sigungu_code, count(*) filter (where is_share) from transaction group by 1 order by 1;
--        select tx_type, count(*) filter (where is_share) from transaction group by 1;
--      → raw 기준 전체 지분 18,316 · 집합 지분 12,467(해제 제외·최신 배치 — 2026-10-08 raw 실측)과 대조.
--        sum(n_all)·sum(floor_missing) 은 ② 와 같거나, ③ 의 정리 행만큼만 차이 나야 한다
--        (건수는 지분도 센다 — 다르면 멈추고 본다).
--   ⑥ 뒤 표 크기 기록: `select pg_total_relation_size('transaction');` (⓪ 과 비교)
--
-- 적용한 사람이 보게 되는 것 (파일의 실제 문장 순서)
-- --------------------------------------------------
--   SET · BEGIN · ALTER TABLE · COMMENT · CREATE VIEW · REVOKE · GRANT ·
--   DROP FUNCTION ×2 · CREATE FUNCTION · COMMENT · REVOKE · CREATE FUNCTION · REVOKE · GRANT ·
--   DROP MATERIALIZED VIEW · SELECT n · COMMENT · CREATE INDEX · ANALYZE · REVOKE ·
--   DROP MATERIALIZED VIEW · SELECT n · COMMENT · CREATE INDEX · ANALYZE · REVOKE ·
--   CREATE FUNCTION · COMMENT · REVOKE · COMMIT · NOTIFY
--
-- 되돌리기 = **새 마이그레이션 파일**(set lock_timeout → begin → api 먼저 drop → 옛 7칸 정의 다시
-- 만들기 → 물질화뷰 둘 옛 정의로 다시 굽기 → list_price_bands 옛 본문 → revoke/grant → commit →
-- notify) **+ 정본 되돌림(PR revert)**. 적용된 이 파일은 고치지 않는다(원장). 칸 하나는 남겨도 해가 없다.

set lock_timeout = '2s';

-- ⛔ 여기부터 commit 까지가 **한 덩어리**다(위 머리말 참조).
begin;

-- ① 칸 하나(+ 칸 주석). 상수 기본값이라 표를 다시 쓰지 않는다(잠금은 commit 까지).
alter table transaction
  add column if not exists is_share boolean not null default false;

comment on column transaction.is_share is '지분 거래(국토부 shareDealingType=''지분'') — 건물 일부 몫만 사고판 거래라 ㎡당 단가가 낮게 나온다. 목록에는 그대로 내고 단가 계산(참고 시세·구 층대 단가·동네 단가 흐름의 단가·표본·면적 중앙값)에서만 뺀다. 건수는 센다(2026-10-08a)';

-- ② 표에 더한 칸을 뷰에도 싣는다(`select *` 는 만든 날의 칸으로 굳는다) — 적재기 upsert 의 문.
create or replace view api.transaction      as select * from public.transaction;
revoke all on api.transaction      from public, anon, authenticated;
grant select, insert, update, delete on api.transaction      to service_role;

-- ③ 실거래 목록 — 돌려주는 칸이 늘어 replace 가 거부된다 → api(부르는 쪽)를 먼저 지운다
--    (허공을 가리키는 순간을 안 만들려고 — 2026-10-04a 와 같은 순서).
drop function if exists api.list_parcel_transactions(text);
drop function if exists public.list_parcel_transactions(text);

create or replace function list_parcel_transactions(pnu text)
returns table (
  floor_no     smallint,
  contract_ym  text,
  contract_day smallint,
  bld_area_m2  numeric,
  price_won    bigint,
  unit_price   numeric,
  tx_type      text,
  is_share     boolean
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
         t.tx_type,
         t.is_share
  from transaction t
  -- ⛔ `::char(19)` 캐스트를 지우지 말 것(2026-09-27c). pnu 칸이 char(19) 인데 text 와 견주면
  --    **칸 쪽**이 text 로 캐스트돼 idx_tx_pnu 를 못 탄다 — 라이브 실측으로 거래 0건 필지가
  --    idx_tx_pnu10_ym 으로 2024년 이후 거래 2.8만 행을 훑어 1,876쪽을 만졌다(찬 캐시면
  --    그 쪽마다 창고 읽기다). 캐스트하면 idx_tx_pnu 한 번에 2쪽이다. 형제 함수들의 `p_pnu::char(19)` 와
  --    같은 처방이다(2026-08-16b). 서명(pnu text)은 화면 약속이라 그대로 둔다.
  where t.pnu = list_parcel_transactions.pnu::char(19)
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
  '나가는 것은 층·계약시점·면적·금액·단가·거래유형·지분 여부뿐(상호명·개인정보 없음). '
  '2026-10-08a: is_share = 지분 거래(건물 일부 몫) — 목록에서 지우지 않고 그대로 낸다(단가 계산에서만 뺀다)';

-- ⛔ public 원본은 닫는다 — 화면은 api 쌍둥이로만 들어온다(2026-09-01b).
revoke all on function list_parcel_transactions(text) from public, anon, authenticated;

create or replace function api.list_parcel_transactions(pnu text)
returns table (
  floor_no     smallint,
  contract_ym  text,
  contract_day smallint,
  bld_area_m2  numeric,
  price_won    bigint,
  unit_price   numeric,
  tx_type      text,
  is_share     boolean
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_parcel_transactions(pnu) $$;

revoke all on function api.list_parcel_transactions(text)     from public, anon, authenticated;
grant execute on function api.list_parcel_transactions(text)     to anon, authenticated;

-- ④ 구 × 층대 단가 — 지분 제외. 물질화뷰는 정의를 못 고친다 → 떨어뜨리고 다시 굽는다.
--    ⓘ get_sigungu_tx_stats 는 문자열 본문 sql 함수라 의존이 기록되지 않아 막지 않는다(머리말).
drop materialized view if exists mv_sigungu_tx_stats;

create materialized view mv_sigungu_tx_stats as
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
  and not t.is_share
  and t.contract_ym >= w.from_ym
group by t.sigungu_code, 2;

comment on materialized view mv_sigungu_tx_stats is
  'Stage A(결정 0012) 구×층대 실거래 단가 분포 — 집합(구분소유) 거래만, 갱신 시점 기준 24개월. '
  '2026-10-08a: 지분 거래(is_share)는 뺀다 — 건물 일부 몫이라 ㎡당 단가가 낮게 나온다. '
  'window_from 은 그 창의 시작 달을 굳혀 둔 것이다(화면이 "최근 24개월"만 적으면 갱신을 미룬 날 '
  '그 문구가 조용히 거짓말이 된다). n 은 단가를 낼 수 있었던 행 수 = 중앙값의 실제 근거 수다. '
  '⚠️ 자료를 새로 넣으면 `python scripts/post_load.py` 로 갱신할 것. '
  '⛔ anon 에게 열지 않는다 — 화면은 get_sigungu_tx_stats() 로만 읽는다.';

-- 뷰와 함께 사라진 유일 색인을 다시 만든다 — 없으면 post_load 의 refresh concurrently 가 멈춘다.
create unique index if not exists idx_msts_key on mv_sigungu_tx_stats (sigungu_code, floor_band);

analyze mv_sigungu_tx_stats;

-- ⛔ 다시 만든 뷰는 다시 열려 있을 수 있다(pg_default_acl) — 만든 자리에서 다시 닫는다.
revoke all on mv_sigungu_tx_stats from public, anon, authenticated;

-- ⑤ 동네 단가 흐름 — 단가·n·면적에서만 지분 제외, 건수는 그대로(filter). 떨어뜨리고 다시 굽는다.
drop materialized view if exists mv_sigungu_tx_yearly;

create materialized view mv_sigungu_tx_yearly as
select
  t.sigungu_code,
  substr(t.contract_ym, 1, 4)                                                   as yr,
  count(*)::int                                                                 as n_all,
  count(*) filter (where t.unit_price is not null and not t.is_share)::int      as n,
  percentile_cont(0.5)  within group (order by t.unit_price)
    filter (where t.unit_price is not null and not t.is_share)                  as median_unit_price,
  percentile_cont(0.25) within group (order by t.unit_price)
    filter (where t.unit_price is not null and not t.is_share)                  as p25_unit_price,
  percentile_cont(0.75) within group (order by t.unit_price)
    filter (where t.unit_price is not null and not t.is_share)                  as p75_unit_price,
  -- 그 해 단가의 **근거가 된 거래 한 건**이 얼마나 큰 물건이었나(2026-09-09b).
  -- ⛔ filter 를 위 셋과 **똑같이** 둔다 — 다른 모집단에서 재면 두 숫자가 서로 다른 거래를
  --    말하게 된다. `unit_price` 는 `bld_area_m2 > 0` 일 때만 생기는 생성 컬럼이라, 이
  --    filter 하나로 면적이 0·빈 행은 자연히 빠진다(면적 조건을 따로 적을 이유가 없다).
  percentile_cont(0.5)  within group (order by t.bld_area_m2)
    filter (where t.unit_price is not null and not t.is_share)                  as median_area_m2,
  count(*) filter (where t.floor_no is null)::int                               as floor_missing,
  count(distinct t.contract_ym)::int                                            as ym_cnt,
  min(t.contract_ym)                                                            as first_ym,
  max(t.contract_ym)                                                            as last_ym
from transaction t
where t.tx_type = '집합'
group by t.sigungu_code, substr(t.contract_ym, 1, 4);

comment on materialized view mv_sigungu_tx_yearly is
  '결정 0027 구×연도 집합(구분소유) 실거래 단가 요약 — 동네 매매 단가 흐름 카드의 재료. '
  'n 은 단가가 있어 중앙값 근거가 된 행 수, n_all 은 그 해 집합 거래 전부(층 미상 비율 분모), '
  'ym_cnt·first_ym·last_ym 은 자료가 해의 일부뿐인지 화면이 적기 위한 값. '
  '2026-09-09b: median_area_m2 = 그 해 단가의 근거가 된 거래 **한 건**의 건물면적 중앙값(㎡) — '
  '단가와 같은 모집단에서 잰다. 다른 해보다 유난히 작으면 초소형 구획이 무더기로 거래된 해다. '
  '2026-10-08a: 지분 거래(is_share)는 단가 셋·n·median_area_m2 에서 빼고 n_all·floor_missing·ym_cnt·first_ym·last_ym 에는 센다. '
  '⚠️ 자료를 새로 넣으면 `python scripts/post_load.py` 로 갱신할 것. '
  '⛔ anon 에게 열지 않는다 — 화면은 api.get_sigungu_tx_yearly() 로만 읽는다.';

create unique index if not exists idx_msty_key on mv_sigungu_tx_yearly (sigungu_code, yr);

analyze mv_sigungu_tx_yearly;

revoke all on mv_sigungu_tx_yearly from public, anon, authenticated;

-- ⑥ 참고 시세 사다리 — 네 갈래 모두 지분 제외. 반환 칸·서명이 그대로라 replace 로 된다.
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
  -- ⓘ 변수 대입(text→char(19))은 19자를 넘는 입력에서 **자르지 않고 에러**(value too long)를
  --    낸다 — 끝 공백만 조용히 버린다(2026-09-27 라이브 실측, 예전 주석의 "자른다"는 틀렸다).
  --    화면은 19자 pnu 만 보내므로 무해하다(더 긴 입력은 애초에 pnu 가 아니다).
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
  -- ⛔ 이웃은 parcel(전국 111만 행)이 아니라 **거래가 있는 필지만 모은 요약표**
  --    mv_tx_parcel_geog 에서 찾는다(2026-09-27c). 이웃 배열은 아래 L4·L5 의
  --    `t.pnu = any(…)` 에만 쓰이므로, 거래가 없는 필지는 들어 있어도 아무것도 안 건진다
  --    — 빼도 결과가 같다(라이브 md5 대조로 증명). 찬 캐시에서 parcel 의 GiST·힙을 훑던
  --    수백 쪽이 수십 쪽으로 준다. ⚠️ 새 실거래를 넣고 `post_load.py` 를 안 돌리면 그
  --    필지가 이웃에서 조용히 빠진다(요약표 갱신 목록 REFRESH_MVS 에 들어 있다).
  if v_geog is not null then
    select coalesce(array_agg(p.pnu) filter (
             where st_dwithin(p.geog, v_geog, 100, false)), '{}'),
           coalesce(array_agg(p.pnu), '{}')
      into v_near100, v_near500
      from mv_tx_parcel_geog p
     where st_dwithin(p.geog, v_geog, 500, false);
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
            -- ⛔ 네 갈래 **모두** 지분 거래(is_share)를 뺀다(2026-10-08a) — 건물 일부 몫만 사고판
            --    거래라 ㎡당 단가가 약 0.39배로 낮게 나온다. 한 갈래만 빠뜨리면 그 단계의 밴드만
            --    조용히 내려앉는다(에러 0). 칸 조건이라 색인(idx_tx_pnu·idx_tx_pnu10_ym)은 그대로 탄다.
            -- L2 — 같은 필지 같은 층
            select 'L2'::text as lvl, t.unit_price, t.bld_area_m2
              from transaction t
             where t.tx_type = '집합' and t.unit_price is not null and not t.is_share
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
             where t.tx_type = '집합' and t.unit_price is not null and not t.is_share
               and t.contract_ym >= v_from
               and t.floor_no = v_floor and t.pnu = any(v_near100)
            union all
            -- L5 — 반경 500m 같은 층
            select 'L5', t.unit_price, t.bld_area_m2
              from transaction t
             where t.tx_type = '집합' and t.unit_price is not null and not t.is_share
               and t.contract_ym >= v_from
               and t.floor_no = v_floor and t.pnu = any(v_near500)
            union all
            -- L6 — 같은 법정동(PNU 앞 10자리) 같은 층대
            -- "행정동" 이 아니라 법정동인 이유: 실거래의 동은 문자, 건물의 동은 코드라
            -- 이름 대조가 조용히 어긋난다(성적표 §1 · 결정 0012 §4).
            select 'L6', t.unit_price, t.bld_area_m2
              from transaction t
             where t.tx_type = '집합' and t.unit_price is not null and not t.is_share
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
  'Stage B(결정 0013) 이 필지의 층별 참고 시세 밴드 — 곁의 실거래(최근 24개월·집합·지분 거래 제외 — 2026-10-08a)로 어림한 '
  '추정값이며 감정평가가 아니다. 한 층에 한 줄이고 status 가 그 줄의 성격을 말한다: '
  'gate_fail(이 구는 기준선 미달 — 층 나열 없이 한 줄) / floor_1f(1층 미제공) / '
  'no_evidence(지하·옥탑·층미상 — 백테스트 표본 0건) / no_estimate(표본 부족) / ok(밴드). '
  'ok 인 줄은 stage(L2·L4·L5·L6)와 n(표본 수)을 **반드시 함께** 표시한다(절대 규칙 3). '
  'p25/median/p75 는 ㎡당 단가, median_area_m2 는 총액 환산용 후보 면적 중앙값이다. '
  'security definer — transaction·parcel·price_gate_sigungu 가 anon 에게 닫혀 있어 '
  '소유자 권한으로 대신 읽는다. 나가는 것은 층·통계값뿐(개별 거래·상호명은 나가지 않는다)';

-- public 원본은 닫는다 — 화면이 부르는 것은 api.list_price_bands 뿐(2026-09-05a)
revoke all on function list_price_bands(text) from public, anon, authenticated;

commit;

-- 칸이 늘었으므로 스키마 캐시를 다시 읽게 한다. 안 알리면 화면이 옛 칸 구성으로 부르다
-- 404(PGRST202) 를 맞고, 적재기 upsert 도 새 칸을 못 찾는다(PGRST204).
notify pgrst, 'reload schema';
