-- =====================================================================
-- 2026-10-24b — 상권 임대 동향의 8분기 흐름 (결정 0038 C · V5)
-- =====================================================================
--
-- 왜
-- --
-- 상권 임대 동향 카드는 (조사구역, 종류)마다 **최신 분기 한 줄**만 보여 준다(list_rent_stats). 그런데 창고
-- rent_stat 에는 조사구역마다 8분기(2024Q3~2026Q2)가 이미 쌓여 있다. 👤 2026-10-17 결정 C 「나」 — 층별 임대료
-- 계단 막대 + 8분기 흐름(공실률 · ㎡당 임대료 · 투자수익률 작은 그림 셋 — 그림마다 제 눈금). 흐름을 그리려면
-- 전 분기가 필요한데 list_rent_stats 는 최신 한 줄만 주고, 그 응답은 임대 카드와 세 잣대가 미리 보낸 답을
-- 나눠 쓴다(takePrefetched — 결정 0038 §7) → 모양을 바꾸면 두 카드가 함께 흔들린다. 그래서 **새 이름**을 연다.
-- 실측(2026-10-24 운영 읽기 조회): rent_stat 7,232행 · 조사구역 이름 395 · (조사구역, 종류) 904쌍 전부 8분기 ·
-- (조사구역, 종류, 분기) 겹침 0 · 투자수익률 음수 135행 · 공실률 0 437행 · 강남파이낸스센터 땅 → 서울>강남>테헤란로
-- 네 종류 × 8분기 = 32줄.
--
-- 무엇이 생기나 (새 객체만 — 기존 객체는 한 글자도 안 바꾼다)
-- ------------------------------------------------------------
--   ① 함수 list_rent_stat_history(p_pnu text) — (rone_region_nm, bld_type, quarter, vacancy_rate, rent_per_m2,
--      yield_rate, income_yield_rate) 여러 줄. sql · 조사구역 찾는 길(me·hit·pair)은 list_rent_stats 의 글 그대로 ·
--      공개키에 닫힘.
--   ② api 쌍둥이 api.list_rent_stat_history — security definer · search_path '' · anon·authenticated 에게만 실행.
--      공개 호출 허용 총계 31 → 32(post_load.py ANON_CALLABLE_ALLOWLIST).
--   ⛔ list_rent_stats 는 무변경(서명·응답 글자까지 — 임대 카드와 세 잣대가 그 응답을 나눠 쓴다).
--   ⛔ 서명은 하나뿐이다(이름당 pg_proc 1 — 같은 이름 둘이면 PostgREST 가 못 고른다 · PGRST203 · 결정 0038 §7).
-- ⛔ 머리(language · stable · security definer · set search_path)와 comment 는 정본(schema.sql)과 글자 그대로다 —
--    tests/test_rent_stat_history_migration.py 가 대조한다(CLAUDE.md ⛔ 2026-10-01a).
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
-- 어느 쪽이 먼저여도 손님 화면은 안 깨진다 — 화면은 함수가 없으면(PGRST202) 8분기 흐름만 조용히 안 그린다
-- (카드·층별 표·계단 막대는 list_rent_stats 로 선다). 그래도 DB 를 먼저 넣어 머지 직후부터 흐름이 서게 한다.
--   ① python scripts/dbx.py -f supabase/migrations/2026-10-24b_rent_stat_history.sql
--   ② 적용 뒤 확인(아래)
--   ③ 화면 PR 머지(→ Vercel 배포) → python scripts/post_load.py --check — 0 이어야 한다
--      (허용 목록 총계 32 · 정본↔라이브 함수 일치).
--   ⓘ ①과 ③ 사이에 **본 폴더(main)** 에서 `--check` 를 돌리면 api.list_rent_stat_history 가 허용 목록 밖
--      공개 함수로 [사고]가 되는 것이 **정상**이다 — main 의 post_load.py 는 아직 31 판이다. ③ 뒤에 사라진다.
--
-- 적용 뒤 확인 (dbx + anon 키로 **화면 요청 그대로**)
-- ------------------------------------------------
--   select oid::regprocedure, proconfig, prosecdef, provolatile from pg_proc
--    where proname = 'list_rent_stat_history';     -- 두 줄(public·api) · 둘 다 prosecdef t · provolatile s
--   anon 키:
--     POST /rest/v1/rpc/list_rent_stat_history {"p_pnu":"1168010100107370000"}  → 200 · 32줄(테헤란로 4종 × 8분기)
--     POST /rest/v1/rpc/list_rent_stat_history {"p_pnu":"0000000000000000000"}  → 200 · []
--   눈 확인: 넓은 화면·412px — 상권 임대 동향 카드를 펼치면 층별 표 옆 계단 막대 · 줄 아래 「최근 8분기 흐름」 그림 셋.
--
-- 되돌리기
-- --------
-- **새 마이그레이션 파일**로: begin → drop function api.list_rent_stat_history(text) →
-- drop function list_rent_stat_history(text) → commit → notify. 그리고 이 PR revert(정본 · post_load 허용
-- 목록 32 → 31 · 화면 흐름). 화면은 함수가 없으면(PGRST202) 흐름만 빠지고 나머지는 선다.
-- 적용된 이 파일은 고치지 않는다(원장).

set statement_timeout = '60s';
set lock_timeout = '5s';

begin;

-- 상권 임대 동향 카드의 **8분기 흐름**(공실률 · ㎡당 임대료 · 투자수익률 작은 그림 셋 · 결정 0038 C · V5)을 먹인다.
-- 이 땅이 속한 부동산원 조사구역마다 **네 종류 × 전 분기**를 한 번에 준다 — 화면은 종류를 바꿀 때 서버를 다시
-- 부르지 않고 이 답에서 고른다.
-- ⛔ 조사구역은 list_rent_stats 와 **같은 길**(필지 → 상권(st_contains) → district_rone_map)로 찾는다 — 아래
--    me·hit·pair 는 그 함수의 글 그대로다(tests/test_rent_stat_history_migration.py 가 글자로 대조한다). 길이
--    갈리면 카드의 값과 흐름이 서로 다른 조사구역을 말한다(에러 없이).
-- ⛔ 역산·환산·평균을 하지 않는다 — 공표값을 그대로 나른다(절대 규칙 5 · 결정 0031). 층별효용비율은 안 나간다.
-- ⛔ 종류(bld_type)끼리 섞지 않는다 — 줄마다 종류를 함께 내보낸다.
-- ⓘ 상권이 여럿이어도 같은 조사구역은 **한 벌만** 나간다(`in (select …)` — 상권마다 되풀이하지 않는다).
--   어느 상권의 줄인지는 list_rent_stats 가 말하고, 화면은 조사구역 이름으로 짝짓는다.
-- ⓘ 빠진 분기는 줄이 없다 — 화면이 "–" 로 둔다(0 으로 메우지 않는다).
-- ⛔ `p_pnu::char(19)` 캐스트를 지우지 말 것 — 컬럼이 char(19) 라 text 와 견주면 **컬럼 쪽**이
--    캐스트돼 인덱스가 통째로 죽는다(2026-08-16b 실측 459.8ms↔0.796ms).
create or replace function list_rent_stat_history(p_pnu text)
returns table (
  rone_region_nm    text,
  bld_type          text,
  quarter           text,
  vacancy_rate      numeric,
  rent_per_m2       numeric,
  yield_rate        numeric,
  income_yield_rate numeric
)
language sql
stable
security definer
set search_path = public
as $$
  with me as (
    -- 좌표가 없으면 아예 답하지 않는다. 여기를 열어 두면 빈손이 "이 자리는 조사 대상이
    -- 아니다"라는 **단정**으로 새어 나간다(list_building_districts 와 같은 원칙).
    select p.geom as g
    from parcel p
    where p.pnu = p_pnu::char(19) and p.geom is not null
  ),
  hit as (
    -- 술어를 st_contains 로 맞춘다 — 결정 0008·0011·0014 의 실측이 이 술어로 나온 숫자다.
    select d.district_id, d.district_nm, d.area_m2
    from district d cross join me
    where st_contains(d.geom, me.g)
  ),
  pair as (
    -- 이을 근거가 없는 상권은 여기서 저절로 빠진다(district_rone_map 에 행이 없다).
    select h.district_id, h.district_nm, h.area_m2, m.rone_region_nm
    from hit h
    join district_rone_map m on m.district_id = h.district_id
  )
  -- ⛔ floor_util_ratio·floor_rent 는 넣지 않는다 — 층별 표는 list_rent_stats 의 최신 한 줄이 맡는다.
  select r.region_nm,
         r.bld_type,
         r.quarter::text,
         r.vacancy_rate,
         r.rent_per_m2,
         r.yield_rate,
         r.income_yield_rate
  from rent_stat r
  where r.region_nm in (select p.rone_region_nm from pair p)
  order by r.region_nm, r.bld_type, r.quarter;
$$;

comment on function list_rent_stat_history(text) is
  '결정 0038 C(V5 · 2026-10-24b) 이 필지가 속한 상권의 부동산원 조사구역마다 임대동향조사 값의 **전 분기** — '
  '조사구역 이름, 건물 종류, 분기, 공실률(%), ㎡당 임대료(천원/㎡ 공표 단위 그대로), 투자수익률(%, 분기 값), '
  '소득수익률(%, 분기 값). 네 종류를 한 번에 준다(화면이 종류를 바꿀 때 서버를 다시 부르지 않는다). '
  '조사구역은 list_rent_stats 와 같은 길(필지 → 상권 → district_rone_map)로 찾는다. '
  '⛔ 역산·환산·평균을 하지 않는다(조사값 그대로 — 층별효용비율은 안 나간다). '
  '⛔ 이을 근거가 없으면 줄이 아예 없다 — 시·도 평균으로 메우지 않는다. 빠진 분기는 줄이 없다(0 으로 안 메운다). '
  'security definer (district·district_rone_map·rent_stat·parcel 이 anon 에게 닫혀 있어 '
  '소유자 권한으로 대신 읽는다. 나가는 것은 조사구역 이름과 공표 통계값뿐이다).';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function list_rent_stat_history(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.list_rent_stat_history(p_pnu text)
returns table (
  rone_region_nm    text,
  bld_type          text,
  quarter           text,
  vacancy_rate      numeric,
  rent_per_m2       numeric,
  yield_rate        numeric,
  income_yield_rate numeric
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_rent_stat_history(p_pnu) $$;

revoke all on function api.list_rent_stat_history(text) from public, anon, authenticated;
grant execute on function api.list_rent_stat_history(text) to anon, authenticated;

-- ⛔ public.list_rent_stat_history 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.

commit;

notify pgrst, 'reload schema';
