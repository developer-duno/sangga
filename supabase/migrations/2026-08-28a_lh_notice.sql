-- =====================================================================
-- 마이그레이션 2026-08-28a — LH 상가 공고 알림판 (창고 + 읽는 함수 하나)
-- =====================================================================
-- 실행법 ⚠️ **대시보드 SQL Editor 로 돌린다.** 표 하나 + 함수 둘이라 빠르고 한
--   트랜잭션에 들어간다(중간에 실패하면 통째로 없던 일이 된다).
--   → 붙여넣고 Run → 아래 6) 검산 쿼리 → `python scripts/post_load.py --check`.
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 하나
-- ─────────────────────────────────────────────────────────────────────
-- 이 서비스는 "이미 있는 건물을 들여다보는 곳"이다. 그런데 창업자가 실제로 사려는
-- 상가 중 **지금 공고가 떠 있는 것**은 여기 한 줄도 없다 — 그건 LH 청약센터에만 있고,
-- 우리 화면을 다 본 사람은 결국 다른 곳으로 가서 처음부터 다시 찾는다.
--
-- LH 분양·임대 상가 공고는 공공 API 로 열려 있다(포털 lhLeaseNoticeInfo1). 1년 창을
-- 훑으면 상가 공고가 531건 나온다(2026-08-28 실측 · 전체 2,913건 중). 그걸 받아 두고
-- 지금 살아 있는 것만 보여 주면, 화면이 "보기"에서 "그래서 뭘 할 수 있나"로 이어진다.
--
-- ─────────────────────────────────────────────────────────────────────
-- ⛔ 마감된 공고를 **지우지 않는다** (결재된 설계)
-- ─────────────────────────────────────────────────────────────────────
-- 화면에서만 숨기고 창고에는 남긴다. 지우면 "이 지역에 상가 공고가 얼마나 자주
-- 뜨는가"를 나중에 셀 수 없고, 그 값은 지금 우리가 가진 어떤 자료로도 못 만든다.
-- 숨기는 일은 **읽는 함수**가 한다(close_date >= current_date) — 창고는 그대로 둔다.
--
-- ─────────────────────────────────────────────────────────────────────
-- ⛔ 호실 목록·가격은 담지 않는다 (실측 근거)
-- ─────────────────────────────────────────────────────────────────────
-- 같은 기관의 공급정보 API 로 상가 공고의 호실·가격을 물으면 **빈 응답**이 온다
-- (2026-08-27 실측 2건). 없는 것을 있는 것처럼 칸만 만들어 두면 다음 세션이 "왜 늘
-- 비어 있지" 하고 같은 조사를 되풀이한다. 그래서 칸을 아예 안 만든다 —
-- 상세는 `dtl_url`(LH 공고문)로 보낸다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 1) 표 — 밖에서는 통째로 잠긴다
-- ─────────────────────────────────────────────────────────────────────
create table if not exists lh_notice (
  -- LH 가 준 공고 식별자. **숫자가 아니다** — '0000061158' · 'BN-0001342' · 'LN-…'
  -- 세 갈래가 섞여 있다(2026-08-28 실측 531건: 201… 256 / LN- 179 / BN- 96).
  -- 숫자로 바꿔 담았다면 그 자리에서 절반이 깨졌을 것이다.
  pan_id         text primary key,
  pan_nm         text not null,

  -- 공고 종류. 코드(AIS_TP_CD)와 **원문 이름**을 둘 다 남기고, 화면에 쓸 짧은 이름은
  -- 따로 둔다. 실측 4종: 23 분양ㆍ(구)임대상가(입찰) / 24 임대상가(추첨) /
  -- 43 임대상가(입찰) / 38 임대상가(공모ㆍ심사).
  -- ⛔ 원문 칸을 없애지 말 것 — 짧은 이름은 **우리가 지은 말**이라, 원문이 없으면
  --    LH 가 종류를 늘렸을 때 우리 말과 저쪽 말을 다시 맞춰 볼 근거가 사라진다.
  kind_cd        text not null,
  kind_nm        text not null,
  kind_nm_src    text not null,

  -- 공급정보 구분코드(220·221·223·224). 지금 화면은 안 쓰지만 종류 코드와 짝이 되는
  -- 값이라 함께 담는다 — 나중에 갈래가 늘면 이 둘의 조합으로 가린다.
  spl_inf_tp_cd  text,

  -- LH 가 적어 준 지역 이름 그대로('경기도' · '전국' · '전남광주통합특별시').
  cnp_nm         text,
  -- 위 이름을 우리 시도코드로 옮긴 것. **옮기지 못했으면 NULL** 이고, 그 사실은
  -- 수집기가 화면에 대고 경고한다(조용한 누락 금지).
  sido_code      char(2),
  -- '전국' 공고. 지역이 없는 게 아니라 **모든 지역**이라, NULL 과 뜻이 정반대다.
  -- 이 칸이 없으면 전국 공고가 어느 지역에서도 안 보이거나(NULL 취급) 아무 지역에나
  -- 잘못 붙는다.
  is_nationwide  boolean not null default false,

  -- 공고 상태. 실측 5종(접수마감·상담요청·공고중·정정공고중·접수중).
  -- ⛔ CHECK 로 목록을 못 박지 않는다 — LH 가 새 상태를 쓰는 날 수집이 통째로 멈춘다.
  --    화면은 이 값을 그대로 보여 주기만 한다.
  pan_ss         text,

  -- 공고일 · 마감일. 원본이 '2026.08.27' 같은 글자라 수집기가 날짜로 바꿔 넣는다.
  -- ⚠️ 비어 있을 수 있다(PAN_DT 는 531건 중 181건이 빈 값) — NULL 을 허용한다.
  notice_date    date,
  close_date     date,

  dtl_url        text,
  -- 언제 받아 온 값인가. 화면이 "며칠 전 자료"를 말할 수 있어야 한다.
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

-- 읽는 함수가 늘 마감일로 거르고 마감일로 정렬한다. 표가 작아도(연 500여 건) 정렬이
-- 공짜는 아니고, 해가 쌓이면 이 인덱스가 그 값을 붙잡아 둔다.
create index if not exists idx_lh_notice_close on lh_notice (close_date);
-- 지역별로 고르는 것이 화면의 기본 동작이다.
create index if not exists idx_lh_notice_sido on lh_notice (sido_code);

-- RLS 를 켜되 정책은 하나도 만들지 않는다 = 전부 거부(이 레포의 다른 표와 같은 방식).
alter table lh_notice enable row level security;

-- ⛔ RLS 만 믿지 않는다 — security definer 경로는 RLS 를 우회하므로 권한이 방어선이다.
--    ⚠️ 정본 위쪽의 `revoke all on all tables in schema public` 은 그 줄을 지날 때의
--       표만 닫는 일회성 명령이라 여기서 만든 표에는 안 걸린다. 만든 자리에서 닫는다.
revoke all on lh_notice from public, anon, authenticated;

-- =====================================================================
-- 2) list_lh_notices — 이 지역에서 **지금 살아 있는** 공고
-- =====================================================================
-- ⛔ 마감 지난 것은 여기서 뺀다(창고에는 남아 있다). 화면이 스스로 거르게 두면 언젠가
--    한 화면이 그 규칙을 빠뜨리고, 그날 사용자는 이미 끝난 공고를 보고 헛걸음한다.
--    거르는 자리를 **한 곳**으로 못 박는다.
--
-- ⛔ 마감일이 없는 공고(NULL)는 **뺴지 않는다.** 마감일을 모르는 것과 마감된 것은 다른
--    말이라, 모른다고 숨기면 살아 있는 공고가 조용히 사라진다. 대신 정렬에서 맨 뒤로
--    보낸다(nulls last).
--
-- ⚠️ '전국' 공고는 어느 지역을 골라도 함께 나온다 — 그게 '전국'이라는 말의 뜻이다.
--    실측 531건 중 59건이 전국이라, 이 줄이 없으면 전국 공고가 어디에서도 안 보인다.
create or replace function list_lh_notices(p_sido text)
returns table (
  pan_id       text,
  pan_nm       text,
  kind_nm      text,
  pan_ss       text,
  notice_date  date,
  close_date   date,
  dtl_url      text,
  collected_at timestamptz
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  -- ⛔ **파라미터를 그대로 쓰지 말 것.** 서명은 text 인데 컬럼은 char(2) 다. 이 표는
  --    작아서 지금은 손해가 안 보이지만, `char컬럼 = text파라미터` 는 컬럼 쪽을 캐스트해
  --    인덱스를 통째로 무력화한다(2026-08-16b 라이브 실측: 459.8ms ↔ 0.796ms).
  --    같은 함정을 같은 방식으로 막는다.
  --
  -- ⚠️ 앞 2자리만 쓴다 — 화면의 지역 고르개는 **시군구 코드**(11680)를 들고 있어서,
  --    그걸 그대로 넘겨도 서울 공고가 나오게 한다. 시도 코드('11')를 넘기면 자기 자신이다.
  v_sido char(2) := nullif(left(btrim(coalesce(p_sido, '')), 2), '');
begin
  return query
    select n.pan_id, n.pan_nm, n.kind_nm, n.pan_ss,
           n.notice_date, n.close_date, n.dtl_url, n.collected_at
      from lh_notice n
     -- 고른 지역의 공고 + 전국 공고. 지역을 안 넘기면(NULL) 전국만 나온다 —
     -- 아무거나 다 보여 주는 것보다 "고른 게 없으면 모두에게 해당하는 것만"이 맞다.
     where ((v_sido is not null and n.sido_code = v_sido) or n.is_nationwide)
       and (n.close_date is null or n.close_date >= current_date)
     -- 곧 마감되는 것이 위로. 마감일을 모르는 것은 맨 뒤.
     order by n.close_date asc nulls last, n.notice_date desc nulls last, n.pan_id;
end;
$$;

comment on function list_lh_notices(text) is
  '이 지역에서 지금 살아 있는 LH 상가 공고(마감 지난 것은 뺀다 — 창고에는 남아 있다). '
  '''전국'' 공고는 어느 지역을 골라도 함께 나온다. 시군구 코드를 넘겨도 앞 2자리로 본다.';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function list_lh_notices(text) from public, anon, authenticated;

-- =====================================================================
-- 3) api 스키마 통과 함수 — 화면이 실제로 부르는 것
-- =====================================================================
-- 화면은 db.schema='api' 로 붙는다(2026-08-22e). public 은 REST 노출에서 빠져 있어
-- 여기에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.list_lh_notices(p_sido text)
returns table (
  pan_id       text,
  pan_nm       text,
  kind_nm      text,
  pan_ss       text,
  notice_date  date,
  close_date   date,
  dtl_url      text,
  collected_at timestamptz
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_lh_notices(p_sido) $$;

revoke all on function api.list_lh_notices(text) from public, anon, authenticated;
grant execute on function api.list_lh_notices(text) to anon, authenticated;

-- ⛔ public.list_lh_notices 는 끝까지 닫아 둔다 — 통과 함수가 security definer 라
--    소유자 권한으로 부르므로 anon 에게 열 필요가 없다.

-- ⛔ **이 줄을 빠뜨리면 화면에서 404(PGRST202) 가 난다.** PostgREST 는 스키마를
--    캐시하므로 새 함수를 만들어도 알려 주기 전까지는 "그런 함수 없다"고 답한다.
--    DB 에는 멀쩡히 있는데 화면만 안 되는, 원인을 찾기 어려운 종류의 고장이다.
notify pgrst, 'reload schema';

-- ─────────────────────────────────────────────────────────────────────
-- 4) 검산 — 붙여넣고 Run 한 뒤 이걸 돌린다
-- ─────────────────────────────────────────────────────────────────────
-- ① 표가 밖에서 잠겨 있나 (기대: 네 줄 전부 false)
--    select has_table_privilege('anon','lh_notice','select') as sel,
--           has_table_privilege('anon','lh_notice','insert') as ins,
--           has_table_privilege('anon','lh_notice','update') as upd,
--           has_table_privilege('anon','lh_notice','delete') as del;
--
-- ② 열린 것은 통과 함수 하나뿐인가 (기대: api 는 true, public 은 false)
--    select has_function_privilege('anon','api.list_lh_notices(text)','execute')    as api_open,
--           has_function_privilege('anon','public.list_lh_notices(text)','execute') as public_open;
--
-- ③ 적재 뒤 실제로 나오나 (기대: 서울 공고 + 전국 공고, 마감 지난 것은 0줄)
--    select count(*) as 살아있는_서울 from list_lh_notices('11');
--    select count(*) as 시군구로_넘겨도_같나 from list_lh_notices('11680');
--    select count(*) as 마감지난것 from list_lh_notices('11') where close_date < current_date;
--
-- ④ 창고에는 마감된 것이 남아 있나 (기대: 화면 수보다 창고 수가 크다)
--    select count(*) as 창고전체, count(*) filter (where close_date >= current_date) as 살아있는것
--      from lh_notice;
