-- =====================================================================
-- 구 비교를 색인이 타게 — search_scope · search_buildings (2026-09-10a)
-- =====================================================================
-- 결정 0028 §백로그의 "형제 search_buildings/search_scope 의 같은 char(5) 캐스트 결함".
-- 2026-09-09c 가 search_stores 에서 먼저 쓴 처방을, 같은 병을 앓는 형제 둘에 옮긴다.
-- 바뀌는 것은 **한 토큰 × 네 자리**뿐이다(`= pat.gu` → `= pat.gu::char(5)`).
--
-- 무엇이 잘못돼 있었나
-- --------------------
-- `mv_search_parcel.sigungu_code` 는 `char(5)` 인데 `pat.gu` 는 `text` 다. 둘을 그냥
-- 견주면 PostgreSQL 이 **컬럼 쪽**을 text 로 올려 맞춘다 — 그러면 `idx_msp_sigungu` 를
-- 못 타고(Index Cond 가 아니라 Filter) 구를 골라도 표를 통째로 훑는다.
--
-- 라이브 실측 2026-09-10 (`explain (analyze, buffers)`, 두 함수의 addr 가지와 같은 조건):
--
--   sigungu_code = '11680'::text     Parallel Seq Scan · 188,442행 · 버퍼 5,312 · 116ms
--   sigungu_code = '11680'::char(5)  Index Scan using idx_msp_sigungu · 12,138행 · 버퍼 353 · 8ms
--
-- (0028 이 **이 표(mv_search_parcel)** 를 두고 미리 재 둔 859.9 → 76.6ms · 188,442 → 12,138행 과 같은 그림이다.)
--
-- ⛔ `pat.gu is null or` 절반은 그대로 둔다
-- ----------------------------------------
-- 이 둘은 구를 안 고른 **전국 검색을 일부러 허용**한다(구 없이는 답이 안 되는
-- `search_stores` 와 다른 점이다). null 이면 `null::char(5)` 라 `is null` 가지가 받으므로
-- 옛 동작과 글자 그대로 같다.
-- ⚠️ 5자보다 긴 입력은 bpchar 캐스트가 조용히 자른다. 구 코드는 서버 목록(list_open_sigungu)
--    에서만 오고 화면도 5자리 숫자만 통과시키므로(src/lib/urlState.ts) 실사용 0건이다.
--
-- ⛔ 버린 안 — 색인을 text 식(expression)으로 새로 만들기
-- ------------------------------------------------------
-- 같은 표에 색인 하나를 더 얹는 일이고, 이 레포는 식 색인을 라이브에서 지우고 "되살리지
-- 말 것"이라 못 박아 두었다(schema.sql 의 idx_building_display_nm 주석 — "식 인덱스는 라이브에서 지웠다. 되살리지 말 것"). 부르는 쪽 한 토큰이면 끝나는 일이다.
--
-- ⛔ api 쌍둥이는 안 건드린다
-- --------------------------
-- `api.search_scope`·`api.search_buildings` 는 본체를 통째로 넘기는 통과 함수라
-- 본문이 안 바뀐다. 거기 붙은 grant 도 손대지 않는다.
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- --------------------------------------
-- `scripts/dbx.py` 는 `psql -v ON_ERROR_STOP=1 -f` 로 돌린다(자동커밋 — `--single-transaction`
-- 이 없다). 함수 둘을 잇달아 다시 만드는 판이라, 감싸지 않고 중간에 끊기면 **한 함수만 새
-- 것**인 상태가 남는다(에러 0 · 검색은 되는데 한쪽만 느린, 찾기 어려운 어긋남).
-- 한 덩어리로 묶으면 실패한 순간 **적용 전 상태 그대로** 되돌아간다
-- (2026-09-05c · 2026-09-09b · 2026-09-09c 가 같은 이유로 같은 모양을 쓴다).
-- ⓘ `notify` 는 커밋되어야 전달되므로 commit **뒤**에 둔다.
--
-- 실행법
-- ------
--   python scripts/dbx.py -f supabase/migrations/2026-09-10a_search_gu_index_cond.sql
--
-- 적용한 사람이 보게 되는 것
-- --------------------------
--   · BEGIN · CREATE FUNCTION ×2 · REVOKE ×2 · COMMIT · NOTIFY
--   · 사실상 즉시 끝난다 — 표를 다시 굽지 않고 함수 본문만 갈아 끼운다.
--   · 중간에 실패하면 **아무것도 안 바뀐 상태**로 되돌아간다 — 고친 뒤 처음부터 다시 돌린다.
--   · 적용 뒤 `python scripts/post_load.py --check` 는 그대로 exit 0 이어야 한다.
--     공개 호출 목록은 하나도 안 늘었다 — 총계 **25 그대로**다.
--   · `python scripts/post_load.py` 는 **다시 돌릴 필요가 없다**(요약표를 안 건드린다).
--   · 확인 ①: 두 함수의 addr 가지와 같은 조건으로 EXPLAIN 을 떠서
--     `Index Cond: (sigungu_code = '11680'::character(5))` 가 보이면 성공이다.
--   · 확인 ②: 함수 자체를 같은 자로 다시 잰다(EXPLAIN Execution Time, 더운 캐시 3회) —
--     넓은 검색어(`빌딩`·`타워`·`search_scope('빌딩')`)가 내려가고, **주소를 콕 집는 검색**
--     (`테헤란로 152`·`그랑프리` — 적용 전 ~5ms)이 느려지지 않아야 한다. 구 색인이 새로
--     쓸 만해지면 플래너가 trigram 대신 그쪽을 고를 수 있어 좁은 검색은 반대로 갈 수 있다.
--
-- ⛔ 다시 만든 자리에서 다시 닫는다
-- --------------------------------
-- `create or replace` 는 기존 권한을 보존하므로 기능상 필수는 아니다. 그래도 이 레포는
-- **만든 자리에서 다시 닫는 것**을 관습으로 삼는다(2026-09-01d·2026-08-16b) — 대시보드가
-- 같은 함수를 다시 만드는 날 anon 기본권한이 조용히 붙어도 여기서 걷힌다.
-- ⛔ grant 는 적지 않는다 — 화면이 부르는 문은 api 쌍둥이 하나뿐이고, public 원본은
--    2026-09-05a 로 닫아 둔 그대로여야 한다.
--
-- 되돌리기:
--   아래 두 블록을 **옛 본문**으로 다시 돌린다 — 원문은
--     · search_scope     … supabase/migrations/2026-08-13e_search_by_sigungu.sql
--     · search_buildings … supabase/migrations/2026-08-14e_search_with_coords.sql
--   그 파일의 `create or replace function …` 블록을 그대로 다시 실행하면 된다
--   (본문에서 `::char(5)` 만 빠진 판이다). 그 뒤 `notify pgrst, 'reload schema';`.

-- ⛔ 여기부터 commit 까지가 **한 덩어리**다(위 머리말 참조).
begin;

-- ── 1) 이 검색어가 몇 곳과 맞는가 ───────────────────────────────────────────
create or replace function search_scope(q text, sigungu text default null)
returns table (too_broad boolean, match_cnt int)
language sql
stable
security definer
set search_path = public
as $$
  with pat as (
    select case when search_key(q) is null then null
                else '%' || replace(replace(replace(search_key(q), '\', '\\'),
                                    '%', '\%'), '_', '\_') || '%'
           end as p,
           nullif(btrim(coalesce(sigungu, '')), '') as gu
  ),
  c as (
    select
      (select count(*) from mv_search_parcel pc cross join pat
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
            or pc.jibun_addr_key like pat.p escape '\')) as addr_cnt,
      (select count(*) from building b
         join mv_search_parcel pc on pc.pnu = b.pnu
         cross join pat
        where pat.p is not null
          and (pat.gu is null or pc.sigungu_code = pat.gu::char(5))
          and b.nm_key like pat.p escape '\')            as nm_cnt
  )
  select greatest(c.addr_cnt, c.nm_cnt) > search_scope_limit(),
         least(greatest(c.addr_cnt, c.nm_cnt), 2147483647)::int
  from c;
$$;

-- 만든 자리에서 다시 닫는다(형제 마이그레이션과 같은 관습 — 위 머리말).
revoke all on function search_scope(text, text) from public, anon, authenticated;

-- ── 2) 검색 본체 — 고른 구 안에서만 ─────────────────────────────────────────
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
  total_cnt      bigint
)
language sql
stable
security definer
set search_path = public
as $$
  with pat as (
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
    t.total_cnt
  from top t
  join mv_search_parcel pc on pc.pnu = t.pnu
  join parcel p on p.pnu = t.pnu
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
$$;

-- 만든 자리에서 다시 닫는다(형제 마이그레이션과 같은 관습 — 위 머리말).
revoke all on function search_buildings(text, int, text) from public, anon, authenticated;

commit;

-- ⛔ 커밋 **뒤**여야 한다 — 롤백된 판에서도 PostgREST 에 헛알림이 가면 안 된다(09-09b 선례).
--    칸 구성은 안 바뀌었지만, 본문을 갈았으니 캐시를 다시 읽게 해 둔다.
notify pgrst, 'reload schema';
