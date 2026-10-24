-- =====================================================================
-- 2026-10-24a — 층 목록 업종 띠 (결정 0038 D · V4)
-- =====================================================================
--
-- 왜
-- --
-- 층 목록 카드의 층 줄은 「점포 8」처럼 수만 있고 **무슨 장사인지는 층을 펼쳐야**(소분류 목록) 보인다. 👤 2026-10-17
-- 결정 D 「가」 — 면적 막대 아래 가는 업종 띠(색 = 소진공 대분류 · 길이 = 이 땅 점포 수) + 카드 아래 「층 모름 N곳」.
-- 화면이 부르는 함수·뷰 중 층별 대분류 개수를 내주는 곳이 없어(v_floor_stack 은 층마다 점포 수와 상호·소분류 목록뿐)
-- 함수 하나와 그 api 쌍둥이를 연다. 기존 객체는 한 글자도 안 바꾼다(결정 0038 §4 — 새 이름 더하기).
-- 실측(2026-10-24 운영 읽기 조회 · 분기 202606): 대분류 10종(I2 음식 840,255 · G2 소매 648,129 · S2 수리·개인 329,827 ·
-- M1 과학·기술 293,137 · P1 교육 181,775 · N1 시설관리·임대 119,955 · R1 예술·스포츠 116,012 · L1 부동산 105,445 ·
-- I1 숙박 80,483 · Q1 보건의료 57,466) · 대분류 null 0 · 강남파이낸스센터 땅 115점포(층 있음 95 · 층 null 20) — 층마다
-- 같은 셈의 합 = v_floor_stack.store_cnt(53개 층 전부 일치) · 개포종합상가 땅 43점포(층 null 22).
--
-- 무엇이 생기나 (새 객체만 — 기존 객체는 한 글자도 안 바꾼다)
-- ------------------------------------------------------------
--   ① 함수 list_floor_industry(p_pnu text) — (floor_no smallint, cat_l_cd text, cat_l_nm text, store_cnt integer) 여러 줄.
--      plpgsql · 안에서 char(19) 로 받아 idx_ub_pnu_cat 을 탄다(Index Only Scan) · 공개키에 닫힘.
--   ② api 쌍둥이 api.list_floor_industry — security definer · search_path '' · anon·authenticated 에게만 실행.
--      공개 호출 허용 총계 30 → 31(post_load.py ANON_CALLABLE_ALLOWLIST · 결정 0038 §4 「지금 32」는 0041 로 두 개가 빠지기 전 수).
--   ⛔ 서명은 하나뿐이다(이름당 pg_proc 1 — 같은 이름 둘이면 PostgREST 가 못 고른다 · PGRST203 · 결정 0038 §7).
-- ⛔ 머리(language · stable · security definer · set search_path)와 comment 는 정본(schema.sql)과 글자 그대로다 —
--    tests/test_floor_industry_migration.py 가 대조한다(CLAUDE.md ⛔ 2026-10-01a).
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
-- 실행 순서 — DB 먼저 → 그 뒤 화면 머지 (Claude 가 dbx 로 · 사장님께 여쭌 뒤)
-- ----------------------------------------------------------------------
-- 어느 쪽이 먼저여도 손님 화면은 안 깨진다 — 화면은 함수가 없으면(PGRST202) 띠·「층 모름」 줄만 조용히 안 그린다.
-- 그래도 DB 를 먼저 넣어 머지 직후부터 띠가 서게 한다.
--   ① python scripts/dbx.py -f supabase/migrations/2026-10-24a_floor_industry.sql
--   ② 적용 뒤 확인(아래)
--   ③ 화면 PR 머지(→ Vercel 배포) → python scripts/post_load.py --check — 0 이어야 한다
--      (허용 목록 총계 31 · 정본↔라이브 함수 일치).
--   ⓘ ①과 ③ 사이에 **본 폴더(main)** 에서 `--check` 를 돌리면 api.list_floor_industry 가 허용 목록 밖
--      공개 함수로 [사고]가 되는 것이 **정상**이다 — main 의 post_load.py 는 아직 30 판이다. ③ 뒤에 사라진다.
--
-- 적용 뒤 확인 (dbx + anon 키로 **화면 요청 그대로**)
-- ------------------------------------------------
--   select oid::regprocedure, proconfig, prosecdef, provolatile from pg_proc
--    where proname = 'list_floor_industry';        -- 두 줄(public·api) · 둘 다 prosecdef t · provolatile s
--   anon 키:
--     POST /rest/v1/rpc/list_floor_industry {"p_pnu":"1168010100107370000"}  → 200 · 줄 합 115(층 null 줄 합 20)
--     POST /rest/v1/rpc/list_floor_industry {"p_pnu":"0000000000000000000"}  → 200 · []
--   눈 확인: 넓은 화면·412px — 층 목록 카드의 층 줄 아래 가는 색 띠 · 카드 아래 「층 모름 20곳」.
--
-- 되돌리기
-- --------
-- **새 마이그레이션 파일**로: begin → drop function api.list_floor_industry(text) →
-- drop function list_floor_industry(text) → commit → notify. 그리고 이 PR revert(정본 · post_load 허용
-- 목록 31 → 30 · 화면 띠). 화면은 함수가 없으면(PGRST202) 띠만 빠지고 나머지는 선다.
-- 적용된 이 파일은 고치지 않는다(원장).

set statement_timeout = '60s';
set lock_timeout = '5s';

begin;

-- 층 목록 카드의 층 줄마다 면적 막대 아래 **가는 업종 띠**를 그린다(결정 0038 D · V4) — 색 = 소진공 대분류 ·
-- 길이 = 이 땅 점포 수. 층 줄의 「점포 N」(v_floor_stack.store_cnt)과 **같은 행 집합**을 센다 — 같은 땅(pnu) ·
-- 같은 분기(snapshot_release.published_ym) · 같은 층 번호. 그래서 층 목록에 있는 층이면 그 층 줄들의 합이 곧
-- 그 층의 store_cnt 다(화면이 그 합을 대조해 어긋나면 띠를 통째로 버린다).
-- 층 번호가 없는 가게(floor_no null — 원본에 층이 비었거나 읽을 수 없거나, 숫자 없이 '지'만 적힌 가게)는
-- **한 묶음(na)** 으로 floor_no null 줄에 센다 — 숨기지 않는다(화면 카드 아래 「층 모름 N곳」).
-- ⓘ 층 목록(층별개요)에 없는 층 번호의 가게도 그 층 번호 그대로 나간다 — 「자리 없는 점포」로 묶는 것은 화면이 한다
--   (이 함수는 건물을 모르고 땅만 안다 — 같은 땅 여러 동이면 동마다 같은 답이다 · store_cnt 와 같은 D등급).
-- ⓘ 업종은 대분류(cat_l_cd · cat_l_nm)까지만 나간다 — 상호·소분류·biz_no·좌표는 한 글자도 안 나간다.
-- ⚠️ 파라미터를 p_ 로 시작하는 이유: 반환 칸 이름(floor_no·store_cnt …)과 표 칸이 겹쳐도 인자가 섞이지 않게.
create or replace function list_floor_industry(p_pnu text)
returns table (
  floor_no  smallint,
  cat_l_cd  text,
  cat_l_nm  text,
  store_cnt integer
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  -- ⛔ **파라미터를 그대로 쓰지 말 것.** 서명은 text 인데 pnu 칸은 char(19) 다.
  --    `char칸 = text파라미터` 는 칸 쪽이 text 로 캐스트돼 **색인이 무력해진다**
  --    (2026-08-16b 라이브 실측: 459.8ms ↔ 0.796ms). 안에서 char(19) 로 받아 쓴다.
  v_pnu char(19) := p_pnu;
begin
  -- ⓘ 반환 칸 이름이 plpgsql 변수가 되므로 표 칸은 늘 별칭(u.·r.)을 붙여 읽는다(이름 충돌 오류 방지).
  -- ⓘ idx_ub_pnu_cat (pnu, snapshot_ym) include (cat_l_cd, cat_l_nm, …, floor_no …) 하나로 힙에 안 간다
  --   (2026-10-24 운영 읽기 실측 강남파이낸스센터 115점포: Index Only Scan · Heap Fetches 0 · 2.3ms).
  -- ⛔ 분기 조건은 v_floor_stack 의 store_cnt 와 글자 그대로 같다 — 다르면 띠 합이 「점포 N」과 어긋난다.
  return query
    select u.floor_no,
           u.cat_l_cd::text,
           u.cat_l_nm,
           count(*)::int
      from unit_business u
     where u.pnu = v_pnu
       and u.snapshot_ym = (select r.published_ym from snapshot_release r)
     group by u.floor_no, u.cat_l_cd, u.cat_l_nm
     order by u.floor_no desc nulls last, u.cat_l_cd nulls last, u.cat_l_nm nulls last;
end;
$$;

comment on function list_floor_industry(text) is
  '이 필지의 점포를 (층, 소진공 대분류)로 센다 — 층 목록 카드의 층별 업종 띠(결정 0038 D · V4 · 2026-10-24a). '
  '분기 = snapshot_release.published_ym · 같은 땅·같은 분기·같은 층이라 층 목록에 있는 층이면 합이 v_floor_stack.store_cnt 와 같다. '
  '층 번호가 없는 가게는 floor_no null 줄 하나의 묶음(na) · 층 목록에 없는 층 번호는 그대로 나가고 화면이 「자리 없는 점포」로 묶는다. '
  '점포는 땅 단위라 같은 땅 여러 동이면 동마다 같은 답이다(D등급). '
  'security definer (unit_business 가 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. 나가는 것은 층·대분류·개수뿐이다).';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function list_floor_industry(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.list_floor_industry(p_pnu text)
returns table (
  floor_no  smallint,
  cat_l_cd  text,
  cat_l_nm  text,
  store_cnt integer
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_floor_industry(p_pnu) $$;

revoke all on function api.list_floor_industry(text) from public, anon, authenticated;
grant execute on function api.list_floor_industry(text) to anon, authenticated;

-- ⛔ public.list_floor_industry 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.

commit;

notify pgrst, 'reload schema';
