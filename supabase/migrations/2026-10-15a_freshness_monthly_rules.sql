-- =====================================================================
-- 마이그레이션 2026-10-15a — 신선도 표 '실거래'·'건축물대장' 두 줄에 월간 규칙
--   (F3+F5 · 사장님 결정 2026-10-15 · 시안 https://claude.ai/artifact/VHuY9yJWepczsQe6osMERE)
-- =====================================================================
-- 실행법:
--   → `python scripts/dbx.py -f supabase/migrations/2026-10-15a_freshness_monthly_rules.sql`
--   (색인·concurrently 가 없어 대시보드 SQL Editor 로도 돌지만, 관습대로 dbx.py 로 돌린다.)
--
-- 무엇을 하나 (한 begin/commit 안 — 표와 함수가 함께 바뀌거나 함께 안 바뀐다):
--   ① 새 한 줄 표 ledger_release(건축물대장 판 표지) — 처음 한 줄 = 2026년 8월 판
--      (10-14 대장 8월 판 30개 구 적재가 15:48 KST 에 끝났다 — docs/PROGRESS.md 「2026-10-14」)
--   ② get_data_freshness() 다시 만들기 — 2번 줄(실거래)·3번 줄(건축물대장)만 바뀐다
--   ⓘ api.get_data_freshness 는 다시 만들지 않는다 — public 원본을 부르기만 하는 통과 함수라 본문이
--     그대로이고, 다시 만들면 grant 를 다시 줘야 한다(그 줄이 빠지는 날 화면이 permission denied).
--
-- 왜 (2026-10-14 신선도 정밀조사 · 사장님 결정 2026-10-15)
--   두 줄 다 '정해진 주기 없음'(rule_kind 'none')이라 감시 그물 6호(check_data_freshness.py)가 못 보던
--   자리다 — 10-14 실측에서 대장은 우리 6월 판 vs 포털 7·8월 판, 실거래는 우리 202608 vs API 202610 이었다.
--   · 실거래 = 계약월 + 2개월 - 하루(사장님 결정 '가' — 인허가와 같은 '+N개월 - 하루' 셈법 ·
--     매달 최근 6개월을 다시 받는다 — collect_transactions.py --recollect-months 6).
--     202610 → 2026-11-30 · 202612 → 2027-01-31 · 202601 → 2026-02-28 · 202801 → 2028-02-29.
--   · 건축물대장 = 기준을 '적재일'(max(building.updated_at))에서 **판**(ledger_release.release_ym)으로,
--     규칙은 인허가와 같은 월간 갈래 'permit'(판 + 3개월 - 하루 = 다음 판이 공개되는 달의 말일).
--     건축HUB 일괄 파일은 N월 판이 (N+1)월 20일 무렵 게시된다(2026-10-15 실측 — 8월 판 OPN20260920…,
--     7월 판 OPN20260820…, 6월 판 OPN20260720…) — 인허가 월간 파일과 같은 주기다.
--     '202608' → 2026-10-31 · '202611' → 2027-01-31.
--   · 표지를 따로 두는 이유: building 표에는 판 칸이 없고(load_building_ledger.py --snapshot-ym 은 상권
--     조인률 보고용이라 저장하지 않는다), max(updated_at) 은 적재가 반쯤 끝난 순간에도 '오늘'이 된다.
--     표지는 30개 구를 다 넣은 뒤 사람이 `python scripts/publish_ledger_release.py --ym <판>` 으로 올린다
--     (그 명령이 열린 구 전부의 max(building.updated_at) 이 지난 표지 뒤인지 본 뒤에만 올린다).
--
-- 모양이 안 맞으면 계산하지 않는다: 두 갈래 다 basis 가 `^\d{4}(0[1-9]|1[0-2])$` 일 때만 to_date 를
--   부른다. 그 밖(null·'2026-10'·'20261')은 next_expected 가 null — to_date 가 터지면 표가 통째로
--   사라진다(이 함수의 기존 원칙). 표가 0줄이면 basis 가 null 이고 줄은 그대로 나온다.
--
-- 잠금: 새 표 만들기는 다른 표를 잠그지 않는다. 함수 교체(create or replace function)는 표 잠금이 없다.
--   `set lock_timeout = '5s'` 는 begin **앞**(세션 설정)에 둔다 — 함수 카탈로그 행을 다른 세션이 쥐고
--   있으면 오래 줄 서지 않고 실패하게(실패하면 begin 안이라 통째 롤백 — 잠시 뒤 다시 돌린다).
--
-- ⚠️ 적용 뒤 post_load.py --check 는 대장 표지 점검을 본다 — 이 파일을 적용하기 **전**에 그 점검이 든 판이
--   머지되면 '표지를 못 읽음 [사고]'가 정상으로 난다(DB 먼저 → 머지 순서를 지킨다).
--
-- 되돌리기 (함수 먼저 → 표 나중 — 표부터 지우면 새 함수가 없는 표를 읽어 화면 표가 통째로 사라진다):
--   ① 2026-10-12b_freshness_land_price_year.sql 에서 get_data_freshness 함수 정의 첫 줄부터 그 함수의
--      revoke 줄까지(comment 포함)를 `set lock_timeout = '5s'; begin; … commit;` 으로 감싸 다시 돌리고
--      `notify pgrst, 'reload schema';` (이 파일 전에 이 함수를 마지막으로 만든 판이 10-12b 다)
--   ② `drop table if exists ledger_release;`
--   (되돌리면 schema.sql 의 표·함수·comment 도 함께 되돌린다 — 안 그러면 post_load --check 의
--    정본 함수 대조가 [사고]. scripts/publish_ledger_release.py 와 --check 의 대장 표지 점검도 함께.)
--
-- 적용 뒤 확인:
--   ① select id, release_ym, loaded_at from ledger_release;              -- 1 | 202608 | 2026-10-14 06:48:00+00
--   ② select src, basis_kind, basis, next_expected, cadence from api.get_data_freshness()
--       where src in ('실거래 (매매)', '건축물대장');
--        → 실거래 (매매) | 계약월 | 202610 | 2026-11-30 | 월 1회 (최근 6개월 다시 받기)
--        → 건축물대장    | 판     | 202608 | 2026-10-31 | 월간 파일 (사람이 적재)
--   ③ select has_table_privilege('anon', 'ledger_release', 'select');   -- f
--   ④ python scripts/publish_ledger_release.py --show                     -- 판 202608 · 구마다 판정
--   ⑤ python scripts/post_load.py --check → [정상] 대장 표지 · 정본 함수 대조 [정상] · 공개 허용 총계 그대로
--   ⑥ 라이브 화면 맨 아래 표 — 실거래 '2026년 11월 30일 무렵' · 건축물대장 '2026년 8월' · '2026년 10월 31일 무렵'

set lock_timeout = '5s';

begin;

-- ── ① 건축물대장 판 표지 ledger_release ─────────────────────────────────────
create table if not exists ledger_release (
  id          int primary key default 1 check (id = 1),
  release_ym  char(6) not null check (release_ym ~ '^\d{6}$'),
  loaded_at   timestamptz not null default now()
);

comment on table ledger_release is
  '건축물대장 판 표지 — 한 줄뿐(id = 1 · 2026-10-15a). 신선도 표 건축물대장 줄의 기준(판)이 이 칸을 읽는다. '
  '30개 구를 다 넣은 뒤 사람이 python scripts/publish_ledger_release.py --ym <판> 으로 올린다(앞으로만 · '
  '열린 구 전부가 지난 표지 뒤에 적재됐을 때만). 0줄이면 신선도 줄의 기준이 비고 post_load.py --check 가 '
  '[사고]로 잡는다. 공개키 접근 0(RLS 켬 + 정책 0 + 권한 회수)';
comment on column ledger_release.release_ym is
  '지금 다 들어 있는 건축물대장 판(YYYYMM — 건축HUB 일괄 파일의 기준월). N월 판은 (N+1)월 20일 무렵 게시된다';
comment on column ledger_release.loaded_at is
  '표지를 적은 시각. publish_ledger_release.py 가 다음 판을 올릴 때 열린 구마다 max(building.updated_at) 이 '
  '이 시각 뒤인지 본다(대장 적재기가 갱신 행에도 적재 시각을 싣는다 — 2026-10-15)';

alter table ledger_release enable row level security;

-- ⛔ Supabase 는 새 표를 anon 에 자동으로 연다(pg_default_acl) — 만든 자리에서 닫는다.
revoke all on ledger_release from public, anon, authenticated;

-- 처음 한 줄 = 10-14 대장 8월 판 30개 구 적재가 끝난 시각. 이미 있으면 건드리지 않는다
-- (정본을 다시 돌려도 지금 표지를 되돌리지 않게).
insert into ledger_release (id, release_ym, loaded_at)
values (1, '202608', '2026-10-14 15:48:00+09')
on conflict (id) do nothing;

-- ── ② get_data_freshness — 2번(실거래)·3번(건축물대장) 줄에 월간 규칙 ───────────
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
  '화면 아래 "이 자료는 언제 것인가" 표. 열한 갈래 자료의 가장 최근 도장(분기·계약월·판·적재일·'
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
  'security definer (열한 표가 전부 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 집계 도장 열한 개뿐이고 원본 행은 한 줄도 안 나간다). 2026-09-05d · 월간 규칙 2026-10-01a · '
  '서울 개업·폐업 2026-10-05b · 필지 공시 연도 2026-10-12b · 실거래·대장 판 월간 규칙 2026-10-15a';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function get_data_freshness() from public, anon, authenticated;

commit;

-- 안 알리면 바뀐 함수가 다음 재시작까지 스키마 캐시에 안 잡힐 수 있다(commit 뒤 — 롤백된 판에서 헛알림 금지).
notify pgrst, 'reload schema';
