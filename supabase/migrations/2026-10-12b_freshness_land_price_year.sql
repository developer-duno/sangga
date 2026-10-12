-- =====================================================================
-- 마이그레이션 2026-10-12b — 신선도 표 '필지 (토지 특성)' 줄의 기준을 공시 연도로
--   (물결 1-C 후속 · 사장님 결정 2026-10-12: 기준 = 공시 연도 · 다음 갱신 = 다음 해 6월 30일)
-- =====================================================================
-- 실행법 ⚠️ **대시보드 SQL Editor 로는 안 된다.**
--   `create index concurrently` 는 트랜잭션 블록 안에서 못 돈다. SQL Editor 는 스크립트 전체를
--   한 트랜잭션으로 감싸므로 25P02 로 죽는다(2026-09-27b·2026-10-09c 와 같은 사정).
--   → `python scripts/dbx.py -f supabase/migrations/2026-10-12b_freshness_land_price_year.sql`
--   그래서 색인은 begin 앞(자동커밋)에서 만들고, 함수 교체만 begin/commit 으로 감싼다.
--
-- 적용 순서(이 파일 안에서 정해져 있다 — 바꾸지 말 것):
--   ① 색인 idx_parcel_land_price_year 를 concurrently 로 만든다
--   ② 관문 — 그 색인이 valid 가 아니면 raise(dbx.py 는 ON_ERROR_STOP=1 이라 뒤 문장은 안 돈다)
--   ③ begin → get_data_freshness() 교체 · comment · revoke → commit → notify pgrst
--   색인을 **먼저** 두는 이유: 함수가 먼저 바뀌면 그 사이 페이지를 연 사람마다 parcel 111만 행을
--   통째로 훑는다(아래 '왜'의 2,174ms — anon 제한 3초 아슬아슬, 넘으면 표가 통째로 사라진다).
--   ⓘ api.get_data_freshness 는 다시 만들지 않는다 — public 원본을 부르기만 하는 통과 함수라 본문이
--     그대로이고, 다시 만들면 grant 를 다시 줘야 한다(그 줄이 빠지는 날 화면이 permission denied).
--
-- 왜 (2026-10-12 사장님 결정 · 라이브 실측)
--   필지 줄은 지금까지 `max(updated_at)`(우리가 브이월드 자료를 **받아 둔 날**)을 '갱신일'로 적었다.
--   이 줄이 말하려는 것은 그 땅값이 **몇 년 공시인가**다 — 그래서 기준을 `max(land_price_year)` 로,
--   다음 갱신 예정을 '공시 연도의 다음 해 6월 30일'로 바꾼다(2026 → 2027-06-30 · 화면 '공시 연도 2026년').
--   라이브 분포(2026-10-12 실측): null 109,658 · 2026 1,009,479 · 그 밖 2018~2025 몇 줄 → max = 2026.
--   `explain analyze select max(land_price_year) from parcel` = Parallel Seq Scan **2,174ms**(색인 없음).
--   btree 하나면 max() 는 색인 끝 한 칸만 읽는다(2026-09-27b 의 updated_at 색인이 2,187ms → 9ms 였다).
--
-- 모양이 안 맞으면 계산하지 않는다: 새 갈래는 basis 가 `^\d{4}$`(네 자리 연도)일 때만 make_date 를
--   부른다. 그 밖(null·'2026Q2'·'202606'·'26')은 next_expected 가 null — `::int` 가 터지면 표가
--   통째로 사라진다(이 함수의 기존 원칙).
--
-- 잠금: 색인은 concurrently 라 표를 잠그지 않는다(적용 중에도 화면·검색은 그대로 돈다).
--   함수 교체(create or replace function)는 표 잠금이 없다. `set lock_timeout = '5s'` 는 begin **앞**
--   (세션 설정)에 둔다 — 함수 카탈로그 행을 다른 세션이 쥐고 있으면 오래 줄 서지 않고 실패하게.
--
-- 시간 제한: 맨 앞의 `set statement_timeout = '900s'` 를 **지우지 말 것.** dbx.py 연결의 제한은 2분이다.
--   concurrently 가 그 제한에 끊기면 invalid 색인이 남는다(2026-09-27b·27e·10-09c 와 같은 선례).
--
-- 디스크: 새 색인 약 8MB 추정(근거 = 같은 표 같은 행 수의 idx_parcel_updated_at 라이브 실측 8,016kB ·
--   smallint 칸이라 그보다 크지 않다) + 만드는 동안 기록(WAL). 운영 순서 = 배치 창(01:30~12:00) 밖 ·
--   브이월드 토지특성 적재(load_vworld_*)와 동시에 돌리지 않는다(concurrently 가 그 쓰기를 기다린다).
--
-- 실패하면 (어디서 멈췄는지 먼저 본다 — 아래 "적용 뒤 확인" ①):
--   ⓐ 색인 만들기에서 끊김 → idx_parcel_land_price_year 가 **invalid** 로 남는다. 다시 돌리면
--      `if not exists` 가 그걸 건너뛰고 바로 뒤 관문이 막는다(함수는 안 바뀐다 — 화면은 옛 그대로).
--      할 일: `drop index concurrently if exists idx_parcel_land_price_year;` 뒤 파일을 다시.
--   ⓑ 함수 교체에서 실패(lock_timeout 55P03 등) → begin 안이라 통째로 롤백(옛 함수 그대로 · 색인만
--      남는다 — 해롭지 않다). 잠시 뒤 파일을 다시 돌리면 색인은 건너뛰고 함수만 바뀐다.
--   ⓘ 다 성공한 뒤 파일을 다시 돌려도 정상이다(색인은 건너뛰고 같은 함수를 한 번 더 만든다).
--
-- 되돌리기 (함수 먼저 → 색인 나중 — 색인부터 지우면 새 함수가 남아 있는 동안 parcel 을 통째로 훑는다):
--   ① 2026-10-07a_snapshot_release.sql 에서 get_data_freshness 함수 정의 첫 줄부터 그 함수의
--      revoke 줄까지(comment 포함)를 begin/commit 으로 감싸
--      다시 돌리고 `notify pgrst, 'reload schema';` (이 파일 전에 이 함수를 마지막으로 만든 판이 10-07a 다)
--   ② `drop index concurrently if exists idx_parcel_land_price_year;`
--   (되돌리면 schema.sql 의 함수·comment·색인도 함께 되돌린다 — 안 그러면 post_load --check 의
--    정본 색인·정본 함수 대조가 [사고].)
--
-- 적용 뒤 확인:
--   ① select c.relname, i.indisvalid from pg_index i join pg_class c on c.oid = i.indexrelid
--        where c.relname = 'idx_parcel_land_price_year';                 -- 한 줄 · t
--   ② explain analyze select max(land_price_year) from parcel;          -- Seq Scan 이 아니어야 한다
--   ③ select src, basis_kind, basis, next_expected from api.get_data_freshness() where src like '필지%';
--        → 필지 (토지 특성) | 공시 연도 | 2026 | 2027-06-30
--   ④ python scripts/post_load.py --check → 정본 색인·정본 함수 대조 [정상]
--   ⑤ 라이브 화면 맨 아래 표의 필지 줄 = '공시 연도 2026년' · '2027년 6월 30일 무렵'

set statement_timeout = '900s';

create index concurrently if not exists idx_parcel_land_price_year on parcel (land_price_year);

-- ── 관문: 함수를 바꾸기 **전에** 색인이 쓸 만한지 본다 ─────────────────────
-- `if not exists` 는 끊겨서 invalid 로 남은 색인도 "있다"고 건너뛴다. 그 상태로 함수를 바꾸면
-- 페이지를 열 때마다 parcel 을 통째로 훑는다(에러 없이 표만 느려지다 사라진다).
do $$
begin
  if not exists (
    select 1
      from pg_index i
      join pg_class c on c.oid = i.indexrelid
     where c.relname = 'idx_parcel_land_price_year'
       and i.indisvalid
  ) then
    raise exception 'idx_parcel_land_price_year 가 없거나 invalid 입니다 — 함수는 안 바꿨습니다. 다시 돌리기 전에 drop index concurrently if exists idx_parcel_land_price_year; 를 먼저 하세요';
  end if;
end $$;

set lock_timeout = '5s';

begin;

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
           -- 월간 자료: 다음 판이 **공개되는 달**의 말일(기준월 + 3개월 - 하루).
           when n.rule_kind = 'permit' and n.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
             then (to_date(n.basis, 'YYYYMM') + interval '3 months' - interval '1 day')::date
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
  '화면 아래 "이 자료는 언제 것인가" 표. 열한 갈래 자료의 가장 최근 도장(분기·계약월·적재일·'
  '계산일·수집일·기준월·고시일·공시 연도)을 창고에서 읽어 한 줄씩 준다. '
  '⛔ 숫자를 화면에 박지 않기 위한 함수다 — 신선도를 글자로 적어 두면 적재하는 순간부터 '
  '그 글자만 거짓말을 한다. next_expected 도 사람이 적는 값이 아니라 규칙으로 계산한다: '
  '분기 자료는 분기말 달 + 5개월 - 하루(다음 분기가 공개되는 달의 말일 — 분기 꼴 셋 '
  '''YYYYMM''·''YYYYQn''·''YYYYQ''(서울시 다섯 자리)를 같은 분기말 달로 맞춘 뒤 한 번만 계산), 월간 자료는 '
  '기준월 + 3개월 - 하루(다음 판이 공개되는 달의 말일), 국세청 기준시가는 고시일의 다음 해 3월 31일, '
  '필지(개별공시지가)는 공시 연도의 다음 해 6월 30일(기준값이 네 자리 연도일 때만). '
  '주기가 없는 자료는 null 이다 — 없는 주기를 지어내면 "늦었다"는 거짓 신호가 뜬다. '
  '기준값이 그 모양이 아니면 계산하지 않고 그 칸만 비운다(to_date 가 터지면 표가 통째로 '
  '사라진다). timestamptz 는 전부 Asia/Seoul 로 옮겨 날짜를 자른다 — 이 DB 가 UTC 라 '
  '그냥 자르면 한국 새벽 0~9시에 어제 날짜가 찍힌다. '
  '⛔ api_quota_log 는 안 본다 — 그건 우리 호출 장부이지 자료의 나이가 아니고, 하한선일 뿐이다. '
  '자료가 0행이면 basis 가 null 이고 줄은 그대로 나온다(화면이 "자료 없음"이라 적는다 — '
  '줄을 빼면 "그런 자료를 안 쓴다"로 읽힌다). '
  'security definer (열한 표가 전부 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 집계 도장 열한 개뿐이고 원본 행은 한 줄도 안 나간다). 2026-09-05d · 월간 규칙 2026-10-01a · '
  '서울 개업·폐업 2026-10-05b · 필지 공시 연도 2026-10-12b';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function get_data_freshness() from public, anon, authenticated;

commit;

-- 안 알리면 바뀐 함수가 다음 재시작까지 스키마 캐시에 안 잡힐 수 있다(commit 뒤 — 롤백된 판에서 헛알림 금지).
notify pgrst, 'reload schema';
