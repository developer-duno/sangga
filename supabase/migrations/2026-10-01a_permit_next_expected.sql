-- =====================================================================
-- 인허가 '다음 갱신 예정'을 다음 판이 **공개되는 달**의 말일로 — get_data_freshness (2026-10-01a)
-- =====================================================================
-- 👤 사장님 결정 2026-10-01. 바뀌는 것은 **월간 규칙 한 줄**뿐이다(건축 인허가 줄).
-- 나가는 칸·줄 수·순서·다른 아홉 줄의 값은 한 글자도 안 바뀐다.
--
-- 왜 바꾸나
-- ---------
-- 옛 규칙(05d)은 월간 자료를 "기준월 + 2개월 - 하루(다음 달 말일)"로 셌다. 그런데 건축HUB
-- 인허가 월간 파일은 **그 달 다음 달 20일 무렵** 게시된다(202608 은 9월 20일 무렵 — 결정 0023
-- 결정 3 개정 단락). 그러니 옛 규칙은 **지금 들어 있는 판이 게시된 달**의 말일을 띄웠고,
-- 다음 판(202609)이 나오기 전인 매달 1일~20일 무렵에는 이미 지난 날짜가 화면에 섰다.
-- 2026-10-01 09:00 KST 라이브 실측: 건축 인허가 202608 → 2026-09-30 (오늘보다 하루 전).
--
-- 무엇이 바뀌나
-- -------------
--   · 월간 자료(건축 인허가): 기준월 + **3개월** - 하루 = 다음 판이 공개되는 달의 말일.
--       202608 → 2026-10-31 · 202609 → 2026-11-30 · 202611 → 2027-01-31 · 202612 → 2027-02-28.
--   · 함수 본문 안의 줄 주석과 `comment on function` 문자열도 같은 말로 고쳤다
--     (본문 주석은 `pg_proc.prosrc` 에 실려 라이브의 일부다 — 정본과 글자 그대로 같아야 한다,
--     tests/test_schema_function_drift.py).
--   · 분기 규칙(분기말 + 5개월 - 하루)·연 1회 규칙(고시일 다음 해 3월 31일)·주기 없는 여섯 줄(null)은
--     그대로다.
--   · ⛔ api 쌍둥이(`api.get_data_freshness`)는 **안 건드린다** — public 을 부르는 통과 함수라
--     public 본문이 바뀌면 그대로 따라온다. 그래서 grant 도 한 줄도 없다(허용 총계 25 불변).
--
-- 잠금
-- ----
-- 함수 본문 하나를 바꿔 끼울 뿐이라 표를 잠그거나 훑는 것이 없다 — **즉시 끝난다**.
-- `lock_timeout` 은 두지 않는다: 이 레포에서 그것을 둔 것은 표 DDL(2026-09-27d `set storage`,
-- 2026-09-27e 색인 교체)뿐이고, 함수만 바꾼 형제(2026-09-10b·2026-09-27a)는 두지 않았다.
--
-- 실행법
-- ------
--   python scripts/dbx.py -f supabase/migrations/2026-10-01a_permit_next_expected.sql
--
-- 적용한 사람이 보게 되는 것
-- --------------------------
--   · BEGIN · CREATE FUNCTION · COMMENT · REVOKE · COMMIT · NOTIFY
--   · 중간에 실패하면 **아무것도 안 바뀐 상태**로 되돌아간다 — 고친 뒤 처음부터 다시 돌린다.
--   · `python scripts/post_load.py` 는 **다시 돌릴 필요가 없다** — 갱신할 표가 안 바뀌었다.
--   · `python scripts/post_load.py --check` 는 그대로 exit 0, 공개 호출 허용 총계 25 불변.
--
-- 적용 뒤 확인
-- ------------
--   select src, basis, next_expected from api.get_data_freshness()
--    where next_expected is not null order by src;
--   기대(2026-10-01 라이브 기준 — 기준값이 그 사이 바뀌었으면 규칙대로 다시 셈한다): 4행
--     건축 인허가               | 202608     | 2026-10-31   ← 바뀐 줄(옛 값 2026-09-30)
--     국세청 기준시가           | 2026-01-01 | 2027-03-31   (그대로)
--     상권 임대 동향 (부동산원) | 2026Q2     | 2026-10-31   (그대로)
--     점포·업종 (상권정보)      | 202606     | 2026-10-31   (그대로)
--   그리고 `select count(*) from api.get_data_freshness();` = 10 (줄 수 불변).
--
-- 되돌리기: 2026-09-05d_data_freshness.sql 의 62~182줄(public `create or replace function
--   get_data_freshness()` 부터 그 `comment on function` · 뒤따르는 `revoke` 까지)을 그대로 다시
--   돌린 뒤 `notify pgrst, 'reload schema';`. api 쌍둥이·표·색인은 이 파일이 손대지 않으므로
--   되돌릴 것이 없다.
--   ⚠️ 라이브만 되돌리면 정본(schema.sql)·가드(tests/test_data_freshness_migration.py ·
--      test_schema_function_drift.py)와 어긋나 시험이 빨강이 된다 — 되돌릴 땐 이 PR 자체를
--      revert 해 정본·가드를 함께 되돌린다.

-- ⛔ 여기부터 commit 까지가 **한 덩어리**다. `scripts/dbx.py` 는 psql 자동커밋으로 돌리므로
--    (`--single-transaction` 이 없다) 감싸지 않으면 함수만 바뀌고 revoke 가 빠진 채 남을 수
--    있다 — 그 순간 public 원본이 열린 채로 라이브에 서 있게 된다.
-- ⓘ `notify` 는 커밋되어야 전달되므로 commit **뒤**에 둔다(2026-09-10b 선례).
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
           -- 월간 자료: 다음 판이 **공개되는 달**의 말일(기준월 + 3개월 - 하루).
           when n.rule_kind = 'permit' and n.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
             then (to_date(n.basis, 'YYYYMM') + interval '3 months' - interval '1 day')::date
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
  '기준월 + 3개월 - 하루(다음 판이 공개되는 달의 말일), 국세청 기준시가는 고시일의 다음 해 3월 31일. '
  '주기가 없는 자료는 null 이다 — 없는 주기를 지어내면 "늦었다"는 거짓 신호가 뜬다. '
  '기준값이 그 모양이 아니면 계산하지 않고 그 칸만 비운다(to_date 가 터지면 표가 통째로 '
  '사라진다). timestamptz 는 전부 Asia/Seoul 로 옮겨 날짜를 자른다 — 이 DB 가 UTC 라 '
  '그냥 자르면 한국 새벽 0~9시에 어제 날짜가 찍힌다. '
  '⛔ api_quota_log 는 안 본다 — 그건 우리 호출 장부이지 자료의 나이가 아니고, 하한선일 뿐이다. '
  '자료가 0행이면 basis 가 null 이고 줄은 그대로 나온다(화면이 "자료 없음"이라 적는다 — '
  '줄을 빼면 "그런 자료를 안 쓴다"로 읽힌다). '
  'security definer (열 표가 전부 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 집계 도장 열 개뿐이고 원본 행은 한 줄도 안 나간다). 2026-09-05d · 월간 규칙 2026-10-01a';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다
--    (2026-09-05d 와 같은 관습). ⛔ public 원본에는 grant 를 주지 않는다 —
--    화면은 api 쌍둥이(이 파일이 안 건드린다)로만 들어온다.
revoke all on function get_data_freshness() from public, anon, authenticated;

commit;

-- ⛔ 커밋 **뒤**여야 한다 — 롤백된 판에서도 PostgREST 에 헛알림이 가면 안 된다.
notify pgrst, 'reload schema';
