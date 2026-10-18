-- =====================================================================
-- 구 표 둘은 상가 거래만 · 참고 시세 밴드와 그 게이트·성적표 줄을 내린다 (2026-10-18a)
-- =====================================================================
-- 결정 0040(👤 2026-10-17·18 — 용도 묶음 · 구 표 둘 「상가 거래 기준」 D3·D8) 위에 결정 0041(👤 2026-10-18
-- 03~04시 — E1 밴드를 내리고 공표값을 나란히)을 얹은 판이다. 이 파일은 운영에 **아직 적용 전**이라 원장이
-- 아니어서 결정 0041 로 다시 썼다(이름은 그대로). 설계 = docs/decisions/0041-참고시세-밴드-내림-공표값-나란히.md §4-4.
--
-- 왜
-- --
-- 공공기관은 상가 건물·호실 단위 매매 시세를 내지 않고, 우리 밴드는 감정평가 규칙의 거래사례비교법과 같은
-- 계열이면서 보정이 전부 없다(결정 0041 §1). 그래서 「참고 매매 시세(추정값)」 카드와 성적표 카드·켜고 끄는
-- 게이트를 내리고, 이미 있는 공표값 셋(국세청 기준시가 · 구 상가 층대 단가 · 부동산원 임대료)을 앞세운다.
-- 구 층대 단가·동네 단가 흐름은 결정 0040 D3·D8 그대로 **상가(근생·판매) 거래만** 센다.
--
-- 무엇을 남기나(만든다)
-- --------------------
--   ① 묶음 함수 둘 — price_use_group_cd(대장 코드) · price_use_group_nm(실거래 이름). `language sql
--      immutable` · search_path·security definer 없음(인라인 — 요약표 33만 행 스캔에서 행마다 호출이
--      남지 않게). public 에서 닫힌 채(revoke) — 화면은 부르지 않는다. ⓘ cd 는 지금 쓰는 곳 0 이다
--      (유일한 독자였던 층 묶음 함수를 아래에서 지운다) — 결정 0041 ㉦ 「묶음 함수 둘은 그대로」.
--   ② mv_sigungu_tx_stats(구 × 층대 단가) — 상가 거래만(where). 칸 구성 그대로.
--   ③ mv_sigungu_tx_yearly(동네 단가 흐름) — 상가 거래만(**where** — 단가·n_all·floor_missing·ym_cnt·
--      first_ym·last_ym 모두 · 결정 0040 D8). 지분은 지금처럼 filter(단가·n·면적에서만 뺀다).
--      ⛔ 물질화뷰는 정의를 못 고친다 → 떨어뜨리고 다시 굽는다(`if not exists` 면 아무 일도 안 한다).
--   ④ get_data_freshness + api 쌍둥이 — 9번 줄(참고 시세 성적표 · 게이트 표의 적재일)을 빼고 다시 만든다.
--      머리(security definer · set search_path · stable)와 comment 는 정본(schema.sql)에서 글자 그대로
--      잘라 붙였다(create or replace 는 머리 속성을 새 정의로 덮어쓴다 — 시험이 글자 대조). 뒤 번호(10·11)는
--      그대로 둔다(순서만 정하는 칸이다).
--
-- 무엇을 지우나(drop · 순서 = 의존 역순 · `cascade` 금지 — 무엇이 같이 사라질지 모른 채 지우지 않는다)
-- ------------------------------------------------------------------------------------------------
--   api.list_price_bands → list_price_bands → price_floor_use_group → price_floor_band → (색인 둘) mv_tx_parcel_geog
--   → api.list_price_gate → list_price_gate → (get_data_freshness 를 9번 줄 없이 다시 만든 **뒤**)
--   → price_gate_sigungu.
--   ⓘ get_data_freshness 는 문자열 본문 sql 함수라 표 의존이 기록되지 않는다 — 그래도 표를 먼저 지우면
--     그 사이 신선도 표가 "그런 표 없음"으로 터지므로 함수를 먼저 갈아 끼운다.
--   ⓘ 그대로 두는 것: 색인 idx_parcel_geog(업종 분포·인허가 반경 500m 가 쓴다) · idx_tx_pnu10_ym(L6 용으로
--     생겼지만 결정 0041 범위 표에 없다 — 별건) · get_sigungu_tx_stats·get_sigungu_tx_yearly(문자열 본문 sql
--     함수라 물질화뷰 의존이 기록되지 않는다 — 뷰를 떨어뜨려도 막히지 않고, 같은 이름·같은 칸으로 다시
--     세우면 그대로 읽는다).
--
-- 의존 확인 (적용 **전**에 한 번 — 둘 다 0행이어야 drop 이 막히지 않는다)
-- ---------------------------------------------------------------------
--   -- 두 요약표에 기대는 뷰·요약표(자기 자신 제외):
--   select distinct c.relname
--     from pg_depend d
--     join pg_rewrite r on r.oid = d.objid
--     join pg_class c on c.oid = r.ev_class
--    where d.refobjid in ('mv_sigungu_tx_stats'::regclass, 'mv_sigungu_tx_yearly'::regclass)
--      and c.oid not in ('mv_sigungu_tx_stats'::regclass, 'mv_sigungu_tx_yearly'::regclass);
--   -- 지울 표·요약표에 기대는 뷰(자기 자신 제외):
--   select distinct c.relname
--     from pg_depend d
--     join pg_rewrite r on r.oid = d.objid
--     join pg_class c on c.oid = r.ev_class
--    where d.refobjid in ('mv_tx_parcel_geog'::regclass, 'price_gate_sigungu'::regclass)
--      and c.oid <> 'mv_tx_parcel_geog'::regclass;
--
-- 잠금
-- ----
-- `drop materialized view`·`drop table` 은 그 대상에 ACCESS EXCLUSIVE 잠금을, `drop function` 은 함수에 잠금을
-- 잡고 **commit 까지** 이어진다(PostgreSQL 문서 DROP MATERIALIZED VIEW · DROP TABLE · 명시 잠금 표). 실거래 표
-- 자체에는 읽기 잠금(ACCESS SHARE)만 걸린다 — 표를 다시 쓰지 않는다. 요약표 둘을 굽는 동안(10-08 07:04 실측 각
-- 1초 안팎) 구 단가·동네 흐름·신선도 표는 오류가 아니라 잠깐 기다림이다 → 그래도 사람 적은 시간에.
-- `lock_timeout = '2s'` 는 **begin 앞**(세션 설정)에 둔다 — 2초 넘게 못 잡으면 통째로 되돌아가 아무것도
-- 안 바뀐다. 다시 돌리면 된다(함수는 create or replace · 지우기는 if exists · 뷰는 drop if exists 뒤 다시 굽는다).
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 뷰를 지운 뒤 끊기면 구 단가·동네 흐름이 통째로 사라진 채 남고
-- post_load.py 의 refresh 가 "그런 뷰 없음"으로 멈춘다 — 한 덩어리로 묶는다. `notify pgrst` 는 commit **뒤**.
--
-- ① 운영 절차 (결정 0041 §6 — 👤 허락 한 번에 2→3 을 한 자리에서 잇는다)
-- -------------------------------------------------------------------
--   ⓪ 적용 직전 기록: 위 의존 확인 쿼리 둘(0행).
--   ① 워크트리(이 가지)에서 적용:
--        python scripts/dbx.py -f supabase/migrations/2026-10-18a_price_use_group.sql
--   ② **둘 다 워크트리에서** python scripts/post_load.py → python scripts/post_load.py --check
--      (본 폴더 main 의 post_load.py 는 REFRESH_MVS 에 지운 mv_tx_parcel_geog 가 있어 "그런 뷰 없음"으로 멈추고,
--       옛 정본으로 돌리면 함수 드리프트가 뜬다 · 기대 = 드리프트 0 · 공개 호출 허용 목록 두 줄(api.list_price_bands ·
--       api.list_price_gate) 빠짐 · 「transaction.main_use 7종 밖」 0).
--   ③ 바로 PR 머지(= 배포) → 라이브 엔진 3벌 전/후 캡처 → python scripts/indexnow_ping.py(첫 HTML 설명 글이 바뀌었다).
--   ⓘ 적용 ~ 머지 창은 사람 적은 시간에(그 사이 화면 main 은 지운 함수를 부른다 — 참고 시세 카드·성적표 카드가
--     실패해 통째로 사라진다(몇 분)).
--
-- 적용한 사람이 보게 되는 것 (파일의 실제 문장 순서)
-- --------------------------------------------------
--   SET · BEGIN ·
--   CREATE FUNCTION · COMMENT · REVOKE · CREATE FUNCTION · COMMENT · REVOKE ·
--   DROP FUNCTION ×4 · DROP INDEX ×2 · DROP MATERIALIZED VIEW · DROP FUNCTION ×2 ·
--   CREATE FUNCTION · COMMENT · REVOKE · CREATE FUNCTION · REVOKE · GRANT ·
--   DROP TABLE ·
--   DROP MATERIALIZED VIEW · SELECT n · COMMENT · CREATE INDEX · ANALYZE · REVOKE ·
--   DROP MATERIALIZED VIEW · SELECT n · COMMENT · CREATE INDEX · ANALYZE · REVOKE ·
--   COMMENT ×2 ·
--   COMMIT · NOTIFY
--
-- ② 되돌리기 — 목표 = **700a254(운영 10-08a 판 · 결정 0040·0041 이전)** · **새 마이그레이션 파일**로(적용한 뒤에는 이 파일이
--    원장이라 고치지 않는다) + 정본 되돌림(PR revert — 정본이 700a254 판으로 돌아간다)
-- -----------------------------------------------------------------------------------------------------------------
--   순서: ⓐ 화면 PR revert(배포) ⓑ 아래 SQL(새 파일 `<날짜>_revert_price_band_removal.sql`) ⓒ 신선도 함수는 ⓑ 안에서
--     10-15a 판(9번 줄 포함)으로 ⓓ 통과 구 = `git show 700a254:docs/backtest/통과구.csv` 로 꺼낸 판을
--     `git show 700a254:scripts/load_price_gate.py` 로 꺼낸 적재기로 다시 적재 ⓔ python scripts/post_load.py.
--   ⓘ 이 머리말에는 함수 정의 문장을 글자로 적지 않는다 — tests/test_schema_function_drift.py 의 파서가
--     주석을 안 걷어 내 그 글자부터 다음 함수 본문까지를 한 함수로 삼키기 때문이다. 대신 **글자 그대로
--     옮겨 올 곳**을 적는다(그 판의 정본은 `git show 700a254:supabase/schema.sql`):
--
--   set lock_timeout = '2s';
--   begin;
--   -- (1) 표 price_gate_sigungu = 2026-08-16a 파일 41-65행(create table · comment 셋 · revoke) + 700a254 판
--   --     schema.sql 의 `alter table price_gate_sigungu enable row level security;` 를 글자 그대로.
--   -- (2) price_floor_band = 2026-08-16a 파일 85-107행(정의 · comment · revoke)을 글자 그대로.
--   -- (3) mv_tx_parcel_geog = 2026-09-27c 파일 61-84행(create · comment · 유일 색인 · gist 색인 · analyze ·
--   --     revoke)을 글자 그대로.
--   -- (4) list_price_bands(9칸 · 용도 묶음 없음) = 2026-10-08a 파일 282-492행(정의 · comment · revoke)을 글자 그대로 +
--   --     api 쌍둥이 9칸 = 700a254 판 schema.sql 의 api.list_price_bands 정의와 그 revoke · grant 한 줄씩을 글자 그대로.
--   -- (5) list_price_gate + api 쌍둥이 = 2026-09-05e 파일 40-105행(정의 · comment · revoke · grant)을 글자 그대로.
--   -- (6) get_data_freshness = 2026-10-15a 파일 100-246행(9번 줄이 든 판 — 정의 · comment · revoke)을 글자 그대로
--   --     (api 쌍둥이는 본문이 같아 다시 만들 필요가 없다).
--   -- (7) 요약표 둘(용도 불문 · 상가 조건 없는 판) = 2026-10-08a 파일 192-234행(mv_sigungu_tx_stats)·237-279행
--   --     (mv_sigungu_tx_yearly) 을 글자 그대로(drop → create → comment → 유일 색인 → analyze → revoke).
--   -- (8) 그 **뒤에** 묶음 함수 둘을 지운다 — 요약표가 더는 안 쓰게 된 다음이라야 의존(pg_depend 'n')에 안 막힌다:
--   --     drop function if exists price_use_group_nm(text);
--   --     drop function if exists price_use_group_cd(text);
--   -- (9) 구 표 함수 둘의 설명 = 700a254 판 schema.sql 2306-2311행(get_sigungu_tx_stats)·2403-2408행
--   --     (get_sigungu_tx_yearly)의 comment 두 문장을 글자 그대로 — 이 파일 ⑦ 이 덧붙인 「상가(근생·판매) 거래만」
--   --     한 구절을 걷어 낸다(함수 본문은 이 파일이 안 바꿨으니 그대로).
--   commit;
--   notify pgrst, 'reload schema';

set lock_timeout = '2s';

-- ⛔ 여기부터 commit 까지가 **한 덩어리**다(위 머리말 참조).
begin;

-- ① 용도 묶음 함수 둘 — 인라인되게 search_path·security definer 없음(정본 머리말 참조).
create or replace function price_use_group_cd(p_cd text)
returns text
language sql
immutable
parallel safe
as $$
  -- 대장 주용도코드(building_floor.main_purps_cd) 앞 두 자리. Z3(옛 기타근린생활)·Z6(옛 판매및영업)은
  -- 옛 분류라 상가로 본다(Z3 에는 사무소·공공시설이 약 1할 섞여 있다 — 알려진한계). Z8 등 그 밖은 other.
  select case
    when nullif(p_cd, '') is null                          then null
    when left(p_cd, 2) in ('03', '04', '07', 'Z3', 'Z6')   then 'shop'
    when left(p_cd, 2) in ('14')                           then 'office'
    when left(p_cd, 2) in ('15')                           then 'lodging'
    when left(p_cd, 2) in ('01', '02')                     then 'resid'
    else                                                        'other'
  end
$$;

comment on function price_use_group_cd(text) is
  '결정 0040 용도 묶음(대장 코드) — main_purps_cd 앞 두 자리: 03·04·07·Z3·Z6=shop(상가) / 14=office(업무) / '
  '15=lodging(숙박) / 01·02=resid(주거) / NULL·빈 글자=NULL / 그 밖=other(기타). '
  '인라인되게 search_path 를 안 박는다. 내부용';

revoke all on function price_use_group_cd(text) from public, anon, authenticated;

create or replace function price_use_group_nm(p_nm text)
returns text
language sql
immutable
parallel safe
as $$
  -- 실거래 건물 주용도(transaction.main_use — 국토부 buildingUse 이름 7종). 주거 묶음은 없다
  -- (상업업무용 실거래에는 주택이 안 온다).
  select case
    when nullif(p_nm, '') is null                              then null
    when p_nm in ('제1종근린생활', '제2종근린생활', '판매')     then 'shop'
    when p_nm in ('업무')                                      then 'office'
    when p_nm in ('숙박')                                      then 'lodging'
    else                                                            'other'
  end
$$;

comment on function price_use_group_nm(text) is
  '결정 0040 용도 묶음(실거래 이름) — transaction.main_use: 제1종근린생활·제2종근린생활·판매=shop(상가) / '
  '업무=office / 숙박=lodging / NULL·빈 글자=NULL / 교육연구·기타·모르는 글자=other(기타). '
  '구 층대 단가·동네 단가 흐름 요약표가 shop 만 센다. 인라인되게 search_path 를 안 박는다. 내부용';

revoke all on function price_use_group_nm(text) from public, anon, authenticated;

-- ② 지우기 — 의존 역순(머리말 참조). `cascade` 금지 · 없으면 건너뛴다(if exists — 다시 돌려도 된다).
--    api(부르는 쪽)를 먼저 지워 허공을 가리키는 순간을 안 만든다(2026-10-08a 와 같은 순서).
drop function if exists api.list_price_bands(text);
drop function if exists public.list_price_bands(text);
drop function if exists price_floor_use_group(char(19), smallint);
drop function if exists price_floor_band(smallint);
-- 이웃 표의 색인 둘 — 뷰를 지우면 함께 사라지지만, 마이그레이션 되짚기 가드(test_schema_migration_sync)가
-- 색인의 생사를 이름으로 세므로 글자로 먼저 지운다(무해 — 같은 잠금 안이다).
drop index if exists idx_mtpg_geog;
drop index if exists idx_mtpg_pnu;
drop materialized view if exists mv_tx_parcel_geog;
drop function if exists api.list_price_gate();
drop function if exists public.list_price_gate();

-- ③ 신선도 표 — 9번 줄(게이트 표의 적재일)을 빼고 다시 만든다. 표를 지우기 **전에** 갈아 끼운다(머리말 참조).
--    머리·comment 는 정본(schema.sql)에서 글자 그대로 잘라 붙였다.
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
         end as next_expected,
         n.cadence
  from norm n
  order by n.ord;
$$;

comment on function get_data_freshness() is
  '화면 아래 "이 자료는 언제 것인가" 표. 열 갈래 자료의 가장 최근 도장(분기·계약월·판·'
  '계산일·수집일·기준월·고시일·공시 연도)을 창고에서 읽어 한 줄씩 준다. '
  '⛔ 숫자를 화면에 박지 않기 위한 함수다 — 신선도를 글자로 적어 두면 적재하는 순간부터 '
  '그 글자만 거짓말을 한다. next_expected 도 사람이 적는 값이 아니라 규칙으로 계산한다: '
  '분기 자료는 분기말 달 + 5개월 - 하루(다음 분기가 공개되는 달의 말일 — 분기 꼴 셋 '
  '''YYYYMM''·''YYYYQn''·''YYYYQ''(서울시 다섯 자리)를 같은 분기말 달로 맞춘 뒤 한 번만 계산), 월간 자료'
  '(인허가 기준월·건축물대장 판)는 기준월 + 3개월 - 하루(다음 판이 공개되는 달의 말일), 실거래는 계약월 + '
  '2개월 - 하루(매달 최근 6개월을 다시 받는다), 국세청 기준시가는 고시일의 다음 해 3월 31일, '
  '필지(개별공시지가)는 공시 연도의 다음 해 6월 30일(기준값이 네 자리 연도일 때만). '
  '주기가 없는 자료는 null 이다 — 없는 주기를 지어내면 "늦었다"는 거짓 신호가 뜬다. '
  '기준값이 그 모양이 아니면 계산하지 않고 그 칸만 비운다(to_date 가 터지면 표가 통째로 '
  '사라진다). timestamptz 는 전부 Asia/Seoul 로 옮겨 날짜를 자른다 — 이 DB 가 UTC 라 '
  '그냥 자르면 한국 새벽 0~9시에 어제 날짜가 찍힌다. '
  '⛔ api_quota_log 는 안 본다 — 그건 우리 호출 장부이지 자료의 나이가 아니고, 하한선일 뿐이다. '
  '자료가 0행이면 basis 가 null 이고 줄은 그대로 나온다(화면이 "자료 없음"이라 적는다 — '
  '줄을 빼면 "그런 자료를 안 쓴다"로 읽힌다). '
  'security definer (열 표가 전부 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 집계 도장 열 개뿐이고 원본 행은 한 줄도 안 나간다). 2026-09-05d · 월간 규칙 2026-10-01a · '
  '서울 개업·폐업 2026-10-05b · 필지 공시 연도 2026-10-12b · 실거래·대장 판 월간 규칙 2026-10-15a · '
  '성적표 줄 뺌 2026-10-18a(결정 0041)';

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

-- ④ 통과 구 게이트 표 — 마지막 독자(get_data_freshness 9번 줄)를 위에서 뺐으므로 이제 지운다.
drop table if exists price_gate_sigungu;

-- ⑤ 구 × 층대 단가 — 상가 거래만. 물질화뷰는 정의를 못 고친다 → 떨어뜨리고 다시 굽는다.
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
  and price_use_group_nm(t.main_use) = 'shop'
  and t.contract_ym >= w.from_ym
group by t.sigungu_code, 2;

comment on materialized view mv_sigungu_tx_stats is
  'Stage A(결정 0012) 구×층대 실거래 단가 분포 — 집합(구분소유) 거래만, 갱신 시점 기준 24개월. '
  '2026-10-08a: 지분 거래(is_share)는 뺀다 — 건물 일부 몫이라 ㎡당 단가가 낮게 나온다. '
  '2026-10-18a: 상가(근생·판매) 거래만 — 결정 0040 D3(price_use_group_nm(main_use) = shop · 업무·숙박·기타는 안 센다). '
  'window_from 은 그 창의 시작 달을 굳혀 둔 것이다(화면이 "최근 24개월"만 적으면 갱신을 미룬 날 '
  '그 문구가 조용히 거짓말이 된다). n 은 단가를 낼 수 있었던 행 수 = 중앙값의 실제 근거 수다. '
  '⚠️ 자료를 새로 넣으면 `python scripts/post_load.py` 로 갱신할 것. '
  '⛔ anon 에게 열지 않는다 — 화면은 get_sigungu_tx_stats() 로만 읽는다.';

-- 뷰와 함께 사라진 유일 색인을 다시 만든다 — 없으면 post_load 의 refresh concurrently 가 멈춘다.
create unique index if not exists idx_msts_key on mv_sigungu_tx_stats (sigungu_code, floor_band);

analyze mv_sigungu_tx_stats;

-- ⛔ 다시 만든 뷰는 다시 열려 있을 수 있다(pg_default_acl) — 만든 자리에서 다시 닫는다.
revoke all on mv_sigungu_tx_stats from public, anon, authenticated;

-- ⑥ 동네 단가 흐름 — 상가 거래만(where — 건수까지 상가만 · 결정 0040 D8). 지분은 그대로 filter.
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
  and price_use_group_nm(t.main_use) = 'shop'
group by t.sigungu_code, substr(t.contract_ym, 1, 4);

comment on materialized view mv_sigungu_tx_yearly is
  '결정 0027 구×연도 집합(구분소유) 실거래 단가 요약 — 동네 매매 단가 흐름 카드의 재료. '
  'n 은 단가가 있어 중앙값 근거가 된 행 수, n_all 은 그 해 집합 거래 전부(층 미상 비율 분모), '
  'ym_cnt·first_ym·last_ym 은 자료가 해의 일부뿐인지 화면이 적기 위한 값. '
  '2026-09-09b: median_area_m2 = 그 해 단가의 근거가 된 거래 **한 건**의 건물면적 중앙값(㎡) — '
  '단가와 같은 모집단에서 잰다. 다른 해보다 유난히 작으면 초소형 구획이 무더기로 거래된 해다. '
  '2026-10-08a: 지분 거래(is_share)는 단가 셋·n·median_area_m2 에서 빼고 n_all·floor_missing·ym_cnt·first_ym·last_ym 에는 센다. '
  '2026-10-18a: 상가(근생·판매) 거래만 — 결정 0040 D3·D8(where — 단가·n_all·floor_missing·ym_cnt·first_ym·last_ym 모두 상가 거래만). '
  '⚠️ 자료를 새로 넣으면 `python scripts/post_load.py` 로 갱신할 것. '
  '⛔ anon 에게 열지 않는다 — 화면은 api.get_sigungu_tx_yearly() 로만 읽는다.';

create unique index if not exists idx_msty_key on mv_sigungu_tx_yearly (sigungu_code, yr);

analyze mv_sigungu_tx_yearly;

revoke all on mv_sigungu_tx_yearly from public, anon, authenticated;

-- ⑦ 구 표 둘을 읽는 함수 둘의 설명 — 「상가(근생·판매) 거래만」 한 구절(정본에서 글자 그대로 · 함수 본문은 그대로).
comment on function get_sigungu_tx_stats(text) is
  'Stage A(결정 0012) 구 실거래 단가 분포 — 층대 5칸을 **항상 같은 순서로** 돌려준다. '
  '표본이 없는 층대는 물질화뷰에 행이 없으므로 여기서 n=0 으로 채운다(칸이 사라지면 '
  '"그 층은 아예 안 판다"처럼 읽힌다). 화면은 n<5 면 수치를 감추고 "표본 부족"만 적는다. '
  'window_from 은 집계한 창의 시작 달, sigungu_nm 은 구 이름(화면에 지역명을 박지 않기 위해 '
  '서버가 준다). security definer — 물질화뷰가 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '상가(근생·판매) 거래만 — 결정 0040 D3·D8(2026-10-18a)';

comment on function get_sigungu_tx_yearly(text) is
  '결정 0027 구 실거래 단가의 연도별 흐름 — 집합 거래만, 연도 오름차순, 자료가 있는 해만. '
  '화면은 n<5 면 수치를 감추고 "표본 부족"만 적는다(절대 규칙 3). security definer — 물질화뷰가 '
  'anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. sigungu_nm 은 구 이름(화면에 지역명을 박지 않기 위해). '
  '2026-09-09b: median_area_m2 = 그 해 단가의 근거가 된 거래 한 건의 건물면적 중앙값(㎡). '
  '⛔ 숫자를 거르는 칸이 아니다 — 초소형 구획이 무더기로 거래된 해를 사람이 알아보게 하는 사실 한 칸이다. '
  '상가(근생·판매) 거래만 — 결정 0040 D3·D8(2026-10-18a)';

commit;

-- 함수·표가 사라지고 신선도 표의 줄 수가 바뀌었으므로 스키마 캐시를 다시 읽게 한다. 안 알리면 화면이 옛
-- 함수를 부르다 404(PGRST202)를 맞는다.
notify pgrst, 'reload schema';
