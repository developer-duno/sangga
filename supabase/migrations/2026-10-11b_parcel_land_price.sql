-- =====================================================================
-- 2026-10-11b — 개별공시지가 한 줄 (물결 1-C1 · 결정 0036 결정 7)
-- =====================================================================
--
-- 왜
-- --
-- 층별 화면의 건물 기본 사양(건물 종류·사용승인·주차 …) 자리에 '개별공시지가 ㎡당 N만원 · YYYY년 공시
-- (땅값만 · 공시가격 — 시세가 아닙니다)' 한 줄을 더한다. 값은 이미 받아 둔 브이월드 토지특성
-- (`parcel.land_price` 원/㎡ · `land_price_year`)이다 — 수집 0. 다만 화면이 부르는 함수·뷰 중 이 두 칸을
-- 내주는 곳이 없어(2026-10-11 grep — 표 정의·적재기·적재기 시험뿐) 함수 하나와 그 api 쌍둥이를 연다.
-- 실측(2026-10-11 읽기 조회): 건물이 선 필지 188,442 중 188,355 곳이 2026년 값 · 87 곳 null · 0원 0 곳.
--
-- 무엇이 생기나 (새 객체만 — 기존 객체는 한 글자도 안 바꾼다)
-- ------------------------------------------------------------
--   ① 함수 get_parcel_land_price(p_pnu text) — (land_price integer, land_price_year smallint) 한 줄 또는 0줄.
--      plpgsql · 안에서 char(19) 로 받아 기본키 색인을 탄다 · 공개키에 닫힘.
--   ② api 쌍둥이 api.get_parcel_land_price — security definer · search_path '' · anon·authenticated 에게만 실행.
--      공개 호출 허용 총계 29 → 30(post_load.py ANON_CALLABLE_ALLOWLIST).
-- ⛔ 머리(language · stable · security definer · set search_path)와 comment 는 정본(schema.sql)과 글자 그대로다 —
--    tests/test_parcel_land_price_migration.py 가 대조한다(CLAUDE.md ⛔ 2026-10-01a).
--
-- 잠금
-- ----
-- 새 함수만 만든다 — 표·뷰 잠금 없음. 형제 관습대로 `lock_timeout` 은 **begin 앞**(세션 설정)에 둔다.
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 중간에 끊기면 api 쌍둥이 없이 원본만 남는다 — 한 덩어리로 묶는다.
-- `notify pgrst` 는 commit **뒤**.
--
-- 실행 순서 — DB 먼저 → 그 뒤 화면 머지 (Claude 가 dbx 로 · 배치 창 01:30~12:00 밖)
-- ------------------------------------------------------------------------------
-- 어느 쪽이 먼저여도 손님 화면은 안 깨진다 — 화면은 함수가 없으면(PGRST202) 그 한 줄만 조용히 안 그린다.
-- 그래도 DB 를 먼저 넣어 머지 직후부터 줄이 서게 한다.
--   ① python scripts/dbx.py -f supabase/migrations/2026-10-11b_parcel_land_price.sql
--   ② 적용 뒤 확인(아래)
--   ③ 화면 PR 머지(→ Vercel 배포) → python scripts/post_load.py --check — 0 이어야 한다
--      (허용 목록 총계 30 · 정본↔라이브 함수 일치).
--   ⓘ ①과 ③ 사이에 **본 폴더(main)** 에서 `--check` 를 돌리면 api.get_parcel_land_price 가 허용 목록 밖
--      공개 함수로 [사고]가 되는 것이 **정상**이다 — main 의 post_load.py 는 아직 29 판이다. ③ 뒤에 사라진다.
--
-- 적용 뒤 확인 (dbx + anon 키로 **화면 요청 그대로**)
-- ------------------------------------------------
--   select oid::regprocedure, proconfig, prosecdef, provolatile from pg_proc
--    where proname = 'get_parcel_land_price';      -- 두 줄(public·api) · 둘 다 prosecdef t · provolatile s
--   anon 키:
--     POST /rest/v1/rpc/get_parcel_land_price {"p_pnu":"1168010100106010000"}  → 200 · 한 줄(2026 · 원/㎡ 정수)
--     POST /rest/v1/rpc/get_parcel_land_price {"p_pnu":"0000000000000000000"}  → 200 · []
--   눈 확인: 넓은 화면·412px — 층별 화면 머리의 사양 줄 아래 '개별공시지가 ㎡당 …' 한 줄.
--
-- 되돌리기
-- --------
-- **새 마이그레이션 파일**로: begin → drop function api.get_parcel_land_price(text) →
-- drop function get_parcel_land_price(text) → commit → notify. 그리고 이 PR revert(정본 · post_load 허용
-- 목록 30 → 29 · 화면 줄). 화면은 함수가 없으면(PGRST202) 줄만 빠지고 나머지는 선다.
-- 적용된 이 파일은 고치지 않는다(원장).

set statement_timeout = '60s';
set lock_timeout = '5s';

begin;

-- 층별 화면의 건물 기본 사양 자리에 '개별공시지가 ㎡당 N만원 · YYYY년 공시' 한 줄을 그린다(결정 0036 결정 7).
-- 칸은 브이월드 토지특성 적재 때 이미 채워져 있었는데(parcel.land_price · land_price_year) 화면이 부르는
-- 함수 중 이 칸을 내주는 곳이 없었다. 땅값은 **필지** 값이라 인자는 pnu 다(같은 땅 다른 동이면 같은 값).
-- 값이 없으면 **줄이 아예 없다**(0행) — 0 을 만들어 내지 않는다. 화면도 0행·실패를 '자료 없음'으로 적지 않고
-- 그 줄을 그리지 않는다(실패를 없음으로 말하면 거짓이다).
-- ⓘ land_price 0 은 값이다(적재기가 원본 '0' 을 0 으로 담는다 — 결측과 안 섞는다). 걸러 내지 않는다.
-- ⚠️ 파라미터를 p_ 로 시작하는 이유: 반환 칸 이름(land_price)과 표 칸이 겹쳐도 인자가 섞이지 않게.
create or replace function get_parcel_land_price(p_pnu text)
returns table (
  land_price      integer,
  land_price_year smallint
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  -- ⛔ **파라미터를 그대로 쓰지 말 것.** 서명은 text 인데 pnu 칸은 char(19) 다.
  --    `char칸 = text파라미터` 는 칸 쪽이 text 로 캐스트돼 **기본키 색인이 무력해진다**
  --    (2026-08-16b 라이브 실측: 459.8ms ↔ 0.796ms). 안에서 char(19) 로 받아 쓴다.
  v_pnu char(19) := p_pnu;
begin
  -- ⓘ 반환 칸 이름이 plpgsql 변수가 되므로 표 칸은 늘 별칭(p.)을 붙여 읽는다(이름 충돌 오류 방지).
  return query
    select p.land_price, p.land_price_year
      from parcel p
     where p.pnu = v_pnu
       and p.land_price is not null
       and p.land_price_year is not null;
end;
$$;

comment on function get_parcel_land_price(text) is
  '이 필지의 개별공시지가(원/㎡)와 그 공시 기준연도 — 한 줄 또는 0줄(값이나 연도가 없으면 줄이 없다 · '
  '0 을 만들지 않는다). 브이월드 토지특성(parcel.land_price · land_price_year)을 그대로 나른다 — '
  '땅값만이고 공시가격이지 시세가 아니다. 결정 0036 결정 7 · 2026-10-11b. '
  'security definer (parcel 이 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. 나가는 것은 숫자 두 개뿐이다).';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function get_parcel_land_price(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.get_parcel_land_price(p_pnu text)
returns table (
  land_price      integer,
  land_price_year smallint
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.get_parcel_land_price(p_pnu) $$;

revoke all on function api.get_parcel_land_price(text) from public, anon, authenticated;
grant execute on function api.get_parcel_land_price(text) to anon, authenticated;

-- ⛔ public.get_parcel_land_price 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.

commit;

notify pgrst, 'reload schema';
