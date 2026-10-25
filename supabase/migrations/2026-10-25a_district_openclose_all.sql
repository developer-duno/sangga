-- =====================================================================
-- 2026-10-25a — 상권 개업·폐업 「전부 보기」 (결정 0038 H · V6)
-- =====================================================================
--
-- 왜
-- --
-- 개업·폐업 카드는 표 전체 기준 최근 8분기만 그린다(list_district_openclose · 결정 0033). 그런데 창고
-- district_openclose 에는 그보다 많은 분기가 쌓여 있다(2026-10-25 운영 읽기: 22분기 20211~20262 · 상권 1,650곳
-- 전부 22분기 · 빠진 분기 0). 👤 2026-10-17 결정 H — 기본 8분기 그대로 + 「전부 보기 (N분기)」 단추 · N 은 서버가
-- 주는 칸 값(화면에 분기 수를 박지 않는다). 같은 이름에 기본값 인자를 더하는 `create or replace` 는 옛 서명을
-- 바꾸지 않고 함수를 하나 더 만들어 `{p_pnu}` 호출을 둘이 받는다 → PostgREST 가 못 고른다(PGRST203 · 운영 카드
-- 즉시 소멸 · 결정 0038 §7). 그래서 **새 이름**을 연다.
--
-- 무엇이 생기나 (새 객체만 — 기존 객체는 한 글자도 안 바꾼다)
-- ------------------------------------------------------------
--   ① 함수 list_district_openclose_all(p_pnu text) — list_district_openclose 의 글 그대로에서 **창만** 바꿨다:
--      const 의 `8 as n_quarters` 를 빼고, win 의 재귀를 더 옛 분기가 없을 때(max 가 null)까지 돌리고,
--      wq 에 `count(w.quarter)::int as total_quarters` 를 더해 맨 끝 칸으로 내보낸다. 나머지(상권 찾기 · status 다섯 ·
--      합산 · 표본 30 · 상위 10 · 정렬)는 한 글자도 안 바뀐다 — tests/test_district_openclose_all_migration.py 가
--      정본 list_district_openclose 의 본문에 그 갈래만 적용한 글과 **글자로** 대조한다. 화면은 모양 검사기를 함께 쓴다.
--   ② api 쌍둥이 api.list_district_openclose_all — security definer · search_path '' · anon·authenticated 에게만 실행.
--      공개 호출 허용 총계 32 → 33(post_load.py ANON_CALLABLE_ALLOWLIST).
--   ⛔ list_district_openclose 는 무변경(서명·응답 글자까지).
--   ⛔ 서명은 하나뿐이다(이름당 pg_proc 1).
-- ⛔ 머리(language · stable · security definer · set search_path)와 comment 는 정본(schema.sql)과 글자 그대로다 —
--    tests/test_district_openclose_all_migration.py 가 대조한다(CLAUDE.md ⛔ 2026-10-01a).
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
-- 어느 쪽이 먼저여도 손님 화면은 안 깨진다 — 화면은 함수가 없으면(PGRST202) 「전부 보기」 단추만 조용히 안 그린다
-- (카드·8분기 막대·업종 표는 list_district_openclose 로 선다). 그래도 DB 를 먼저 넣어 머지 직후부터 단추가 서게 한다.
--   ① python scripts/dbx.py -f supabase/migrations/2026-10-25a_district_openclose_all.sql
--   ② 적용 뒤 확인(아래)
--   ③ 화면 PR 머지(→ Vercel 배포) → python scripts/post_load.py --check — 0 이어야 한다
--      (허용 목록 총계 33 · 정본↔라이브 함수 일치).
--   ⓘ ①과 ③ 사이에 **본 폴더(main)** 에서 `--check` 를 돌리면 api.list_district_openclose_all 이 허용 목록 밖
--      공개 함수로 [사고]가 되는 것이 **정상**이다 — main 의 post_load.py 는 아직 32 판이다. ③ 뒤에 사라진다.
--
-- 적용 뒤 확인 (dbx + anon 키로 **화면 요청 그대로**)
-- ------------------------------------------------
--   select oid::regprocedure, proconfig, prosecdef, provolatile from pg_proc
--    where proname = 'list_district_openclose_all';  -- 두 줄(public·api) · 둘 다 prosecdef t · provolatile s
--   select status, district_nm, latest_quarter, jsonb_array_length(quarters), total_quarters
--     from api.list_district_openclose_all('1168010100107370000');   -- 상권 줄마다 ok · 22 · 22
--   anon 키:
--     POST /rest/v1/rpc/list_district_openclose_all {"p_pnu":"1168010100107370000"}  → 200 · total_quarters 22
--     POST /rest/v1/rpc/list_district_openclose_all {"p_pnu":"<대전 필지>"}  → 200 · [not_seoul 한 줄]
--   눈 확인: 넓은 화면·412px — 개업·폐업 카드를 펼치면 「전부 보기 (22분기)」 단추 · 누르면 막대 22칸(옆으로 밀기).
--
-- 되돌리기
-- --------
-- **새 마이그레이션 파일**로: begin → drop function api.list_district_openclose_all(text) →
-- drop function list_district_openclose_all(text) → commit → notify. 그리고 이 PR revert(정본 · post_load 허용
-- 목록 33 → 32 · 화면 단추). 화면은 함수가 없으면(PGRST202) 단추만 빠지고 나머지는 선다.
-- 적용된 이 파일은 고치지 않는다(원장).

set statement_timeout = '60s';
set lock_timeout = '5s';

begin;

-- 개업·폐업 카드의 「전부 보기」(결정 0038 H · V6)를 먹인다 — 창이 표 전체 분기 전부라는 것 말고는
-- list_district_openclose 와 같은 함수다(모양·셈·상태 갈래 전부 · 화면은 모양 검사기를 함께 쓴다).
-- ⛔ 창은 상권마다가 아니라 표 전체 기준이다 — 모든 상권이 같은 창을 본다(결정 0033). 8분기 창에서 no_data 이던
--    상권이 여기서는 옛 분기로 ok 가 될 수 있다 — 화면은 그 상권의 latest_quarter 를 꼭 함께 적는다.
-- ⛔ `p_pnu::char(19)` 캐스트를 지우지 말 것 — 컬럼이 char(19) 라 text 와 견주면 **컬럼 쪽**이
--    캐스트돼 인덱스가 통째로 죽는다(2026-08-16b 실측 459.8ms↔0.796ms).
create or replace function list_district_openclose_all(p_pnu text)
returns table (
  status           text,
  district_id      text,
  district_nm      text,
  district_type    text,
  latest_quarter   text,
  quarters         jsonb,
  industries       jsonb,
  other_industries jsonb,
  window_quarters  jsonb,
  total_quarters   int
)
language sql
stable
security definer
set search_path = public
as $$
  with recursive const as (
    -- 상권 합산 비율을 내는 최소 표본(결정 0033 결정 7 · 절대 규칙 3) — list_district_openclose 와 같은 값.
    -- ⓘ 창의 크기는 없다 — 이 함수의 창은 표 전체 분기 전부다(결정 0038 H · V6).
    select 30 as min_similr
  ),
  me as (
    -- 좌표가 없으면 아무 상권에도 안 든다는 **단정**이 새어 나가지 않게 따로 가른다(no_coord).
    -- ⛔ pnu 칸은 char(19) — 인자를 그대로 견주면 칸 쪽이 text 로 캐스트돼 색인이 죽는다.
    select p.geom
    from parcel p
    where p.pnu = p_pnu::char(19) and p.geom is not null
  ),
  hit as (
    -- 서울 필지가 담긴 **서울시 상권**만. 술어는 list_building_districts 와 같은 st_contains.
    select d.district_id, d.district_nm, d.district_type, d.area_m2
    from district d cross join me
    where left(p_pnu::char(19), 2) = '11'
      and left(d.sigungu_code, 2) = '11'
      and st_contains(d.geom, me.geom)
  ),
  head as (
    -- 건물 단위 상태 셋 — 판정 순서가 곧 뜻이다(위부터, 서로 배타).
    --   no_coord               필지 좌표 없음(서울이든 아니든 — 모르는 것은 모른다고)
    --   not_seoul              시·도가 서울이 아님(대전 등 — 서울시 자료는 서울 상권만 다룬다)
    --   outside_seoul_district 서울인데 속한 서울시 상권이 없음
    -- 셋 다 아니면 null → 상권마다 ok / no_data 한 줄씩이 대신 나간다.
    select case
             when not exists (select 1 from me) then 'no_coord'
             when left(p_pnu::char(19), 2) <> '11' then 'not_seoul'
             when not exists (select 1 from hit) then 'outside_seoul_district'
           end as status
  ),
  win (quarter, n) as (
    -- **표 전체 분기 전부** — 모든 상권이 같은 창을 본다(상권마다 제 분기만 잡으면 자료가 끊긴 상권이
    -- 몇 해 전 숫자를 '최근'처럼 보인다). 한 분기씩 기본키(첫 칸 quarter)를 거꾸로 짚어 내려가고, 더 옛
    -- 분기가 없으면(max 가 null) 멈춘다 — distinct 로 168만 행을 훑지 않는다.
    select max(o.quarter), 1 from district_openclose o
    union all
    select (select max(o.quarter) from district_openclose o where o.quarter < w.quarter), w.n + 1
    from win w
    where w.quarter is not null
  ),
  wq as (
    -- 창 그 자체(표 전체 분기 전부 · 최신 → 옛 순 · 표가 비었으면 빈 배열)와 그 개수 — 화면이 그 상권의
    -- latest_quarter 와 견주어 "이 상권은 n분기까지"를 말하고, 단추 「전부 보기 (N분기)」의 N 을 이 칸에서
    -- 읽게 **모든 줄에 같은 값**을 싣는다(화면에 분기 수를 박지 않는다). 마지막 null 줄은 세지 않는다.
    select coalesce(jsonb_agg(w.quarter::text order by w.quarter desc)
                      filter (where w.quarter is not null), '[]'::jsonb) as window_quarters,
           count(w.quarter)::int as total_quarters
    from win w
  ),
  qs as (
    -- 창 안의 분기 × 이 필지의 상권. 창 안에서 그 상권에 빠진 분기는 빠진 채 둔다(채우지 않는다).
    select h.district_id, w.quarter
    from hit h cross join win w
    where w.quarter is not null
  ),
  sums as (
    -- ⛔ 그 상권·분기의 업종 행 **전부**를 더한다(결정 0033 결정 7 합산 규칙). 유사 업종 점포 수가
    --   0 인데 개업·폐업이 있는 행(분기 안에 그 업종 마지막 가게까지 닫힘)도 분자에 넣는다 —
    --   닫힌 가게는 실제로 닫혔다. 여기에 유사 업종 점포 수 조건을 걸면 그 가게들이 숫자에서 사라진다.
    select o.district_id, o.quarter,
           sum(o.similr_induty_stor_co) as similr,
           sum(o.stor_co)               as stor,
           sum(o.frc_stor_co)           as frc,
           sum(o.opbiz_stor_co)         as opbiz,
           sum(o.clsbiz_stor_co)        as clsbiz
    from qs
    join district_openclose o on o.district_id = qs.district_id and o.quarter = qs.quarter
    group by o.district_id, o.quarter
  ),
  latest as (
    -- 그 상권이 창 안에서 **실제로 가진** 최신 분기 — 창의 최신(표 전체 최신)과 다를 수 있다
    -- (화면이 "이 상권은 20xx년 n분기까지"라고 따로 말할 수 있게 그대로 돌려준다).
    -- 창 안에 행이 하나도 없으면 여기 없다 → no_data.
    select s.district_id, max(s.quarter) as quarter
    from sums s
    group by s.district_id
  ),
  ranked as (
    -- 최신 분기 업종 행 — 유사 업종 점포 수가 많은 순(같으면 코드 순). 위 10개만 따로 싣고
    -- 나머지는 '그 밖 N업종' 한 덩어리로 더한다. 업종 행의 비율은 공표값 그대로다.
    select o.*,
           row_number() over (partition by o.district_id
                              order by o.similr_induty_stor_co desc, o.svc_induty_cd) as rn
    from latest l
    join district_openclose o on o.district_id = l.district_id and o.quarter = l.quarter
  ),
  rows_out as (
    select hd.status,
           null::text as district_id, null::text as district_nm, null::text as district_type,
           null::text as latest_quarter,
           null::jsonb as quarters, null::jsonb as industries, null::jsonb as other_industries,
           0::numeric as sort_area
    from head hd
    where hd.status is not null
    union all
    select case when l.quarter is null then 'no_data' else 'ok' end,
           h.district_id, h.district_nm, h.district_type,
           l.quarter::text,
           (select jsonb_agg(jsonb_build_object(
                     'quarter',               s.quarter::text,
                     'similr_induty_stor_co', s.similr,
                     'stor_co',               s.stor,
                     'frc_stor_co',           s.frc,
                     'opbiz_stor_co',         s.opbiz,
                     'clsbiz_stor_co',        s.clsbiz,
                     -- 서울시 산식 그대로(분모 = 유사 업종 점포 수). 표본이 모자라면 비율은 null —
                     -- 개수만 나간다. 분모가 0 이면 여기서 이미 null 이다(min_similr > 0).
                     'opbiz_rt',  case when s.similr >= c.min_similr
                                       then round(s.opbiz * 100.0 / s.similr, 2) end,
                     'clsbiz_rt', case when s.similr >= c.min_similr
                                       then round(s.clsbiz * 100.0 / s.similr, 2) end)
                   order by s.quarter desc)
              from sums s cross join const c
             where s.district_id = h.district_id),
           (select jsonb_agg(jsonb_build_object(
                     'svc_induty_cd',         r.svc_induty_cd,
                     'svc_induty_cd_nm',      r.svc_induty_cd_nm,
                     'similr_induty_stor_co', r.similr_induty_stor_co,
                     'stor_co',               r.stor_co,
                     'frc_stor_co',           r.frc_stor_co,
                     'opbiz_stor_co',         r.opbiz_stor_co,
                     'opbiz_rt',              r.opbiz_rt,
                     'clsbiz_stor_co',        r.clsbiz_stor_co,
                     'clsbiz_rt',             r.clsbiz_rt)
                   order by r.rn)
              from ranked r
             where r.district_id = h.district_id and r.rn <= 10),
           (select case when count(*) > 0 then jsonb_build_object(
                     'industry_count',        count(*),
                     'similr_induty_stor_co', sum(r.similr_induty_stor_co),
                     'stor_co',               sum(r.stor_co),
                     'frc_stor_co',           sum(r.frc_stor_co),
                     'opbiz_stor_co',         sum(r.opbiz_stor_co),
                     'clsbiz_stor_co',        sum(r.clsbiz_stor_co),
                     'opbiz_rt',  case when sum(r.similr_induty_stor_co) >= max(c.min_similr)
                                       then round(sum(r.opbiz_stor_co) * 100.0
                                                  / sum(r.similr_induty_stor_co), 2) end,
                     'clsbiz_rt', case when sum(r.similr_induty_stor_co) >= max(c.min_similr)
                                       then round(sum(r.clsbiz_stor_co) * 100.0
                                                  / sum(r.similr_induty_stor_co), 2) end) end
              from ranked r cross join const c
             where r.district_id = h.district_id and r.rn > 10),
           h.area_m2
    from hit h
    left join latest l on l.district_id = h.district_id
  )
  select ro.status, ro.district_id, ro.district_nm, ro.district_type, ro.latest_quarter,
         ro.quarters, ro.industries, ro.other_industries, wq.window_quarters, wq.total_quarters
  from rows_out ro cross join wq
  -- 좁은 상권이 더 구체적인 설명이라 먼저 온다(list_building_districts 와 같은 정렬).
  order by ro.sort_area asc, ro.district_id;
$$;

comment on function list_district_openclose_all(text) is
  '결정 0038 H(V6 · 2026-10-25a) 개업·폐업 카드의 「전부 보기」 — list_district_openclose 와 같은 모양·같은 셈(상권마다 · '
  '좁은 상권 먼저 · 서울시 산식 그대로의 비율 · 유사 업종 점포 수 합 30 미만이면 비율 null · 빠진 분기는 빠진 채 · '
  '최신 분기 업종 상위 10 + 그 밖 N업종 · status 다섯 갈래)인데 창만 다르다: 표 전체 기준 최근 8분기가 아니라 **표 전체 분기 전부** '
  '(모든 상권이 같은 창). window_quarters 는 그 전부(최신 → 옛 순 · 표가 비었으면 빈 배열)이고 total_quarters 는 그 개수다 — '
  '둘 다 status 와 무관하게 모든 줄에 같은 값이다. latest_quarter 는 그 상권이 실제로 가진 최신 분기다(표 전체 최신과 다를 수 있다 — '
  '8분기 창에서 no_data 이던 상권이 여기서 ok 로 바뀔 수 있으니 화면은 그 분기를 꼭 함께 적는다). '
  'list_district_openclose 는 그대로 둔다(같은 이름에 인자를 더하면 PostgREST 가 못 고른다 — PGRST203). '
  'security definer (district_openclose·district·parcel 이 anon 에게 닫혀 있어 소유자 권한으로 대신 '
  '읽는다. 나가는 것은 상권 이름·종류와 서울시 공표 수·비율뿐이다).';

-- 만든 자리에서 다시 닫는다(대시보드 판은 anon 을 붙인다).
revoke all on function list_district_openclose_all(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.list_district_openclose_all(p_pnu text)
returns table (
  status           text,
  district_id      text,
  district_nm      text,
  district_type    text,
  latest_quarter   text,
  quarters         jsonb,
  industries       jsonb,
  other_industries jsonb,
  window_quarters  jsonb,
  total_quarters   int
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_district_openclose_all(p_pnu) $$;

revoke all on function api.list_district_openclose_all(text) from public, anon, authenticated;
grant execute on function api.list_district_openclose_all(text) to anon, authenticated;

-- ⛔ public.list_district_openclose_all 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.

commit;

notify pgrst, 'reload schema';
