-- =====================================================================
-- 이 자료는 언제 것인가 — 화면 아래 신선도 표 (2026-09-05d)
-- =====================================================================
-- 로드맵 Wave 4 『자료 신선도 스탬프』. 👤 사장님 결재(2026-09-05): **별도 화면이 아니라
-- 푸터의 표 한 장**이다.
--
-- 무엇이 달라지나
-- ---------------
-- 표는 하나도 안 만든다. 이미 있는 열 갈래의 자료에서 **가장 최근 도장 하나씩**만 꺼내
-- 읽는 길을 뚫는다. 지금까지 "이 화면의 숫자가 언제 것인가"를 아는 길은
-- `python scripts/post_load.py --check` 뿐이었다 — 그건 우리만 볼 수 있는 자리다.
--
-- ⛔ 날짜를 화면에 박지 않기 위한 함수다
-- --------------------------------------
-- 신선도를 글자로 적어 두면 **적재하는 순간부터 그 글자만 거짓말**을 한다(코드는 한 줄도
-- 안 고쳤는데 화면이 옛 분기를 말한다 — `v_coverage_stats` 를 만든 이유와 같은 결).
-- 그래서 기준일은 창고에서 읽고, "다음 갱신 예정"은 **규칙으로 계산**한다. 어느 쪽도
-- 사람이 손으로 적는 숫자가 아니다.
--
-- 다음 갱신 예정 — 세 가지 규칙 (전부 이 함수 안에 한 번씩만 적혀 있다)
-- ---------------------------------------------------------------------
--  · 분기 자료(상권정보 · 부동산원 임대동향)
--      분기말 달 + 5개월 - 하루 = **다음 분기가 공개되는 달의 말일**.
--      202606(2026Q2 적재분) → 2026-10-31 · 202609 → 2027-01-31.
--      (2026Q3 은 2026-10-31 게시 예정 — `check_new_sangkwon_quarter.py` 와 같은 기준.)
--  · 월간 자료(건축 인허가)
--      기준월 + 2개월 - 하루 = **다음 달 말일**. 202607 → 2026-08-31.
--  · 연 1회 자료(국세청 기준시가)
--      고시일의 **다음 해 3월 31일**. 국세청 고시가 매년 3월이다(결정 0021).
-- 규칙이 없는 자료(실거래·건축물대장·상권 경계·LH·성적표·필지)는 **null** 을 준다 —
-- 없는 주기를 지어내면 "늦었다"는 거짓 신호가 화면에 뜬다.
--
-- ⛔ 모양이 안 맞으면 계산하지 않는다
-- ----------------------------------
-- `to_date('2026Q3','YYYYMM')` 은 **에러**다. 그 한 줄이 터지면 표가 통째로 사라진다
-- (`unit_business.snapshot_ym` 은 컬럼 주석이 두 형식을 다 허용한다). 그래서 정규식으로
-- 모양을 먼저 보고, 안 맞으면 그 칸만 비운다 — 기준일은 그대로 보여 준다.
--
-- ⛔ `api_quota_log` 는 쳐다보지도 않는다
-- ---------------------------------------
-- 그건 "우리가 API 를 몇 번 불렀나"의 장부이지 **자료가 언제 것인가**가 아니다. 게다가
-- 하한선일 뿐이라(실패·재시도가 섞인다) 신선도의 근거로 쓰면 틀린 날짜를 자신 있게 적게 된다.
--
-- ⛔ 시간대는 한국으로 고정한다
-- ----------------------------
-- 이 DB 는 UTC 다(2026-09-01a 실측). `timestamptz` 를 그냥 날짜로 자르면 한국 새벽
-- 0~9시에 **어제 날짜**가 찍힌다 — 신선도 표가 하루 낡아 보이는 자리다.
--
-- 나가는 것
-- ---------
-- 열 줄. 각 줄은 (자료 이름 · 기준의 종류 · 기준값 · 다음 갱신 예정 · 주기)다.
-- 자료가 한 행도 없으면 `basis` 가 **null** 이고, 그때도 **줄은 그대로 나온다**
-- (화면이 '자료 없음'이라 적는다 — 줄을 빼면 "그런 자료를 안 쓴다"로 읽힌다).
--
-- 적용
-- ----
-- Supabase SQL Editor 에 통째로 붙여 실행한다(표 변경 0 · 되돌리려면 두 함수를 drop).
--   실행법:  select * from api.get_data_freshness();
--   기대:    10행 (src 가 '점포·업종 (상권정보)' 로 시작해 '필지 (토지 특성)' 로 끝난다)
-- 실행 뒤 `python scripts/post_load.py --check` 로 공개 롤 권한이 그대로인지 본다.

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
