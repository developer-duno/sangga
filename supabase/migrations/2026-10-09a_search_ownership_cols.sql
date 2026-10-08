-- =====================================================================
-- 2026-10-09a — 건물 검색 결과에 소유 구조 세 칸을 더 싣는다 (물결 1-A1 · 결정 0036 결정 5)
-- =====================================================================
-- 왜
-- --
-- 결정 0036 결정 5: 검색 결과 카드에 "집합건물/일반건물 · 사용승인 · 주차"를 한 줄로 보이려 한다.
-- 그런데 `search_buildings` 는 지금 13칸(bld_id … total_cnt)만 돌려준다. 세 값은 `building` 표에
-- 이미 칸으로 있다(`is_jiphap boolean` · `approve_date date` · `parking_cnt integer`). 화면이 결과마다
-- 따로 물으면 왕복이 25번 늘어난다 — 검색 함수가 같은 자리에서 실어 주는 편이 싸다.
-- 이 파일은 **DB 만** 바꾼다. 화면 줄은 다음 PR(1-A2)이고, 화면 타입은 세 칸을 선택 칸(`?`)으로
-- 받으므로 이 파일이 먼저 라이브에 올라가도 화면은 그대로 선다(옛 화면은 새 칸을 무시한다).
--
-- 무엇을 바꾸나
-- -------------
--   ① `search_buildings`(public 원본) — 기존 13칸 **뒤에** `is_jiphap · approve_date · parking_cnt`.
--      값은 building 원값 그대로(null 은 null, 0 은 0) — "미상" 판정은 화면 몫이다.
--      세 칸은 결과를 lim 행으로 줄인 **뒤** 마지막 select 에서 building 을 기본키(bld_id)로
--      한 번 더 읽어 붙인다. 검색 가지(addr·nm·hit)는 한 글자도 안 바꾼다 — 이 함수는 가지에
--      민감하다(가지 2→3 에 763→1,550ms). 결정 0029 의 다섯 낱말(plpgsql · force_custom_plan ·
--      not materialized · use_column · return query)과 구 캐스트(`pat.gu::char(5)`)는 그대로다.
--      ⚠️ `#variable_conflict use_column` 아래에서 세 칸 이름이 plpgsql 변수가 된다 — 본문은
--         `bo.` 로 수식해서만 읽으므로 부딪히지 않는다.
--   ② `api.search_buildings`(화면이 부르는 쌍둥이) — 같은 16칸으로. 머리(stable · security definer ·
--      `set search_path = ''`)와 `public.` 완전수식 본문은 정본 그대로.
--
-- 왜 create or replace 가 아니라 drop 인가
-- ----------------------------------------
-- `returns table` 의 칸은 OUT 파라미터라 칸을 더하면 `create or replace` 가 거부한다
-- ("cannot change return type of existing function"). 지우고 다시 만들면 **권한과 comment 도 함께
-- 사라진다** → comment 는 정본에서 잘라 다시 달고, api 쌍둥이에 실행 권한을 다시 준다.
-- 안 주면 화면 검색이 permission denied 로 죽는다(2026-08-13 401 전례 · 2026-08-14e 머리말).
-- 부르는 쪽(api)부터 지운다(2026-10-04a · 2026-10-08a 와 같은 순서).
-- 이 함수를 부르는 다른 DB 객체는 api 쌍둥이 하나뿐이다(정본 grep 2026-10-08).
--
-- 잠금
-- ----
-- 표 DDL 은 없다 — 함수 둘을 지우고 다시 만들 뿐이라 즉시 끝난다. `drop function` 은 그 함수
-- 객체에 잠금을 잡으므로, 같은 함수를 고치는 다른 세션과 부딪혀 하염없이 기다리지 않게
-- `lock_timeout` 을 **begin 앞**(세션 설정)에 둔다. 못 잡으면 통째로 되돌아가 아무것도 안 바뀐다.
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 쌍둥이를 지운 뒤 끊기면 화면 검색이 통째로 사라진 채
-- 남는다 — 한 덩어리로 묶는다. `notify pgrst` 는 commit **뒤**.
--
-- 되돌리기
-- --------
-- **새 마이그레이션 파일**로: set lock_timeout → begin → api 쌍둥이 drop → public drop →
-- 2026-09-27a 의 `search_buildings` 정의(13칸)를 그대로 다시 만들고 옛 comment(이 PR 앞 정본의 문장) →
-- public revoke → 13칸 api 쌍둥이(2026-08-22e 정의) → api revoke·grant anon → commit → notify.
-- 정본 schema.sql 은 PR revert 로 함께 되돌린다. 적용된 이 파일은 고치지 않는다(원장).
-- 화면은 세 칸을 선택 칸으로 받으므로 되돌려도 깨지지 않는다.
--
-- 실행: python scripts/dbx.py -f supabase/migrations/2026-10-09a_search_ownership_cols.sql

set lock_timeout = '5s';

begin;

-- ① 부르는 쪽(api 쌍둥이)부터 지운다 — 본문이 `select *` 라 원본 칸이 바뀐 채 남으면 호출이 깨진다.
drop function if exists api.search_buildings(text, int, text);
drop function if exists search_buildings(text, int, text);

-- ② public 원본 — 정본 schema.sql 과 글자 그대로(머리 속성·본문·comment).
create or replace function search_buildings(q text, lim int default 25, sigungu text default null)
returns table (
  bld_id         text,
  pnu            char(19),
  bld_nm         text,
  road_addr      text,
  jibun_addr     text,
  -- 상권 지도의 마커 자리(2026-08-14e). **필지(parcel.geom)** 좌표라 한 땅에 여러 동이면
  -- 같은 점이고, 상권 판정(list_building_districts)과 같은 칸을 본다 — 마커와 글자가
  -- 서로 다른 칸을 보면 "지도는 상권 밖, 글자는 상권 안"이 된다.
  lat            double precision,
  lng            double precision,
  bld_cnt_in_pnu int,
  floor_cnt      int,
  min_floor      smallint,
  max_floor      smallint,
  has_roof       boolean,
  total_cnt      bigint,
  -- 소유 구조 세 칸(2026-10-09a · 결정 0036 결정 5) — building 원값 그대로(null 은 null,
  -- 0 은 0). '미상' 판정은 화면 몫이다. ⛔ 기존 13칸 **뒤에만** 붙인다 — 칸은 자리로
  -- 맞춰지므로 앞에 끼우면 api 쌍둥이·화면이 칸을 엇갈려 읽는다.
  is_jiphap      boolean,
  approve_date   date,
  parking_cnt    integer
)
language plpgsql
stable
security definer
set search_path = public
set plan_cache_mode = force_custom_plan
as $$
#variable_conflict use_column
begin
  return query
with pat as not materialized (
    select
      case when esc.v is null then null else '%' || esc.v || '%' end as p,
      case when esc.v is null then null else '%' || esc.v      end as p_end,
      -- ⚠️ k 는 **이스케이프 전** 값이다(정확일치·앞글자일치 정렬에 쓴다).
      search_key(q) as k,
      esc.gu
    from (
      select case when search_key(q) is null then null
                  else replace(replace(replace(search_key(q), '\', '\\'),
                               '%', '\%'), '_', '\_')
             end as v,
             nullif(btrim(coalesce(sigungu, '')), '') as gu
    ) esc
  ),
  -- ① 주소 두 칸은 같은 표라 한 번만 훑는다. 그 표는 **검색 전용 요약표**이고,
  --    구를 골랐으면 그 구만 본다(이제 이게 기본 경로다 — idx_msp_sigungu).
  --    `limit 상한+1` 이 범위 게이트를 겸한다(구를 안 고른 경로의 안전망).
  addr as materialized (
    select pc.pnu, pc.road_addr, pc.jibun_addr_key
      from mv_search_parcel pc
      cross join pat
     where pat.p is not null
       -- ⛔ `::char(5)` 를 지우지 말 것 — 컬럼이 char(5) 인데 text 와 견주면 **컬럼 쪽**이
       --    text 로 캐스트돼 색인이 Index Cond 가 아니라 Filter 로 떨어진다(라이브 실측
       --    2026-09-10: Parallel Seq Scan 188,442행·버퍼 5,312·116ms → Index Scan 12,138행·버퍼 353·8ms).
       --    형제 `search_stores` 가 같은 처방을 쓴다(결정 0028 §백로그).
       -- ⚠️ 5자보다 긴 입력은 bpchar 캐스트가 조용히 자른다 — 구 코드는 서버 목록에서만
       --    오고 화면도 /^\d{5}$/ 로 막으므로(src/lib/urlState.ts) 실사용 0건이다.
       -- ⛔ `pat.gu is null or` 절반은 그대로 둔다 — 이 함수는 구를 안 고른 전국 검색을
       --    일부러 허용한다(구 없이는 답이 안 되는 `search_stores` 와 다른 점이다).
       and (pat.gu is null or pc.sigungu_code = pat.gu::char(5))
       and (pc.road_addr_key  like pat.p escape '\'
         or pc.jibun_addr_key like pat.p escape '\')
     limit search_scope_limit() + 1
  ),
  -- ⛔ 주소 가지와 이름 가지를 OR 하나로 합치지 말 것 — 서로 다른 두 표라 조인 전에
  --    한 표를 못 걸러 gin_trgm 인덱스가 통째로 무력화된다(2026-08-08 실측).
  nm as materialized (
    select b.bld_id, b.pnu, b.nm_key, b.display_nm as bld_nm,
           pc.road_addr, pc.jibun_addr_key
      from building b
      join mv_search_parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null
       and (pat.gu is null or pc.sigungu_code = pat.gu::char(5))
       and (pat.gu is null or (b.pnu >= pat.gu::char(19)
                                     and b.pnu <= (pat.gu || repeat('9',14))::char(19)))
       and b.nm_key like pat.p escape '\'
     limit search_scope_limit() + 1
  ),
  gate as (
    select ((select count(*) from addr) > search_scope_limit()
         or (select count(*) from nm)   > search_scope_limit()) as broad
  ),
  hit as (
    select b.bld_id, b.pnu, b.nm_key, b.display_nm as bld_nm,
           a.road_addr, a.jibun_addr_key
      from addr a
      join building b on b.pnu = a.pnu
     where not (select g.broad from gate g)
    union
    select n.bld_id, n.pnu, n.nm_key, n.bld_nm, n.road_addr, n.jibun_addr_key
      from nm n
     where not (select g.broad from gate g)
  ),
  eligible as (
    select h.*,
           count(*) over () as total_cnt,
           coalesce(h.jibun_addr_key like (select p_end from pat) escape '\', false)
             as jibun_hit
    from hit h
    -- 층 자료가 아예 없는 건물은 빈 스택이 되므로 뺀다(2026-08-13 실측: 242,631 중 239개).
    where exists (
      select 1 from building_floor f
      where f.bld_id = h.bld_id and f.floor_no is not null
    )
  ),
  top as (
    select e.*
    from eligible e
    cross join pat
    order by
      e.jibun_hit                    desc,
      (e.nm_key = pat.k)             desc nulls last,
      (e.nm_key like pat.k || '%')   desc nulls last,
      (e.bld_nm is null)             asc,
      length(e.bld_nm)               asc nulls last,
      e.road_addr                    asc nulls last,
      e.bld_id
    limit greatest(1, least(coalesce(lim, 25), 100))
  )
  -- ② 지번주소 조립·좌표 뽑기는 여기서 처음 한다 — 25행에만 필요하다.
  --    parcel 은 pnu 가 기본키라 이 조인은 25번의 색인 조회다(요약표에 geom 을 넣어
  --    표를 키우는 것보다 싸다 — 요약표는 188,442행이고 검색마다 통째로 훑힌다).
  select
    t.bld_id, t.pnu, t.bld_nm, t.road_addr,
    parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun) as jibun_addr,
    st_y(p.geom)::double precision as lat,
    st_x(p.geom)::double precision as lng,
    (select count(*)::int from building b2 where b2.pnu = t.pnu) as bld_cnt_in_pnu,
    fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof,
    t.total_cnt,
    bo.is_jiphap, bo.approve_date, bo.parking_cnt
  from top t
  join mv_search_parcel pc on pc.pnu = t.pnu
  join parcel p on p.pnu = t.pnu
  -- ③ 소유 구조 세 칸(2026-10-09a)은 결과를 줄인 **뒤** 기본키(bld_id)로 한 번 더 읽는다 —
  --    lim 행(최대 100)번의 색인 조회다. ⛔ 위 hit·nm 가지에 실어 나르지 말 것 — 검색 가지는
  --    낱말 하나에도 민감하다(가지 2→3 에 763→1,550ms · search_stores 머리말).
  --    top 의 bld_id 는 building 에서 왔으므로 이 조인은 행을 줄이지 않는다.
  join building bo on bo.bld_id = t.bld_id
  join lateral (
    select
      count(*)::int                                    as floor_cnt,
      min(s.floor_no) filter (where s.floor_no <> 99)  as min_floor,
      max(s.floor_no) filter (where s.floor_no <> 99)  as max_floor,
      coalesce(bool_or(s.floor_no = 99), false)        as has_roof
    from v_building_floor_stack s
    where s.bld_id = t.bld_id
  ) fs on true
  order by
    t.jibun_hit                     desc,
    (t.nm_key = search_key(q))      desc nulls last,
    (t.nm_key like search_key(q) || '%') desc nulls last,
    (t.bld_nm is null)              asc,
    length(t.bld_nm)                asc nulls last,
    t.road_addr                     asc nulls last,
    t.bld_id;
end;
$$;

comment on function search_buildings(text, int, text) is
  '§8.1 건물 검색. 건물 1개 = 1행이며 total_cnt로 정확한 전체 건수를 함께 준다. '
  'sigungu 를 주면 **그 구 안에서만** 찾는다(2026-08-13e, 사장님 결정) — 같은 건물 이름이 '
  '여러 구에 겹치기 때문이다(이름 33,851종 중 2,443종이 2개 이상 구에 존재). '
  'lat·lng 는 상권 지도의 마커 자리다(2026-08-14e) — **필지(parcel.geom) 좌표**라 한 땅에 '
  '여러 동이면 같은 점이고, 상권 판정(list_building_districts)과 같은 칸을 본다. '
  'security definer — 원본 표가 anon에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '입력의 % _ \ 는 서버가 리터럴로 이스케이프하고, 빈 검색어는 0건으로 잘라낸다. '
  '이름은 building.display_nm(동명칭 폴백 + 개인 성명 가림)만 본다 — 보이는 것 = 검색되는 것. '
  '주소는 mv_search_parcel(건물이 있는 필지만)을 본다. ⚠️ 자료 적재 후 `python scripts/post_load.py` 필수. '
  'is_jiphap·approve_date·parking_cnt 는 building 원값 그대로다(2026-10-09a) — null·0 을 '
  '"미상"으로 읽을지는 화면이 정한다. '
  '⛔ 주소 가지와 이름 가지를 OR로 합치지 말 것 — 두 조인 테이블에 걸친 OR은 gin_trgm 인덱스를 무력화한다';

-- ⛔ public 원본에는 grant 를 주지 않는다 — 화면은 api 쌍둥이로만 들어온다(CLAUDE.md 🚪).
--    drop 으로 ACL 이 사라졌어도, 새 함수는 PUBLIC 실행이 닫힌 채 태어난다(2026-09-01b) —
--    그래도 만든 자리에서 닫는다(2026-09-27a 와 같은 줄).
revoke all on function search_buildings(text, int, text) from public, anon, authenticated;

-- ③ api 쌍둥이 — 같은 16칸 · security definer · 빈 search_path · public. 완전수식(정본 그대로).
create or replace function api.search_buildings(q text, lim int default 25, sigungu text default null)
returns table (
  bld_id         text,
  pnu            char(19),
  bld_nm         text,
  road_addr      text,
  jibun_addr     text,
  lat            double precision,
  lng            double precision,
  bld_cnt_in_pnu int,
  floor_cnt      int,
  min_floor      smallint,
  max_floor      smallint,
  has_roof       boolean,
  total_cnt      bigint,
  is_jiphap      boolean,
  approve_date   date,
  parking_cnt    integer
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.search_buildings(q, lim, sigungu) $$;

-- ⚠️ drop 으로 권한이 함께 사라졌다 — 다시 주지 않으면 검색이 permission denied 로 죽는다
--    (2026-08-13 401 전례 · 2026-08-14e 머리말). 먼저 회수하고 준다(정본의 api 권한 줄과 같은 꼴).
revoke all on function api.search_buildings(text, int, text)  from public, anon, authenticated;
grant execute on function api.search_buildings(text, int, text)  to anon, authenticated;

commit;

-- ⛔ 커밋 **뒤**여야 한다 — 결과 칸이 바뀌었으니 PostgREST 가 스키마 캐시를 다시 읽어야
--    새 세 칸을 낸다. 롤백된 판에서 헛알림이 가지 않게 commit 뒤에 둔다.
notify pgrst, 'reload schema';
