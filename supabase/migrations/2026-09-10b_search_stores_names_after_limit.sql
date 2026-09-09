-- =====================================================================
-- 가게 이름 셋을 **50줄에만** 만든다 — search_stores (2026-09-10b)
-- =====================================================================
-- 결정 0028 §백로그 🟡-5. 나가는 칸·순서·총계·정렬은 **한 글자도 안 바뀐다.**
-- 같은 답을 더 적은 일로 낸다.
--
-- 무엇이 낭비였나
-- ---------------
-- 화면 한 줄에 적는 "걸린 상호 최대 3개"(matched_names)를, 지금은 ②matched 에서
-- **걸린 땅마다** 만든다. 그 뒤 page 가 50줄로 자른다 — 즉 게이트 상한(6,000땅)까지
-- 땅마다 `unnest → search_key → like → distinct → 정렬 → limit 3 → array_agg` 를
-- 돌려 놓고, 그중 50개만 쓰고 나머지는 버린다.
-- 강남 '학원'은 898땅이 걸리므로 898번 돌고 50번을 쓴다.
--
-- 라이브 기준선 (2026-09-10 04:10 KST · 더운 캐시 중앙값, 연속 3회)
--   · search_stores('학원',     50, '11680', 0) — 약 322ms
--   · search_stores('카페',     50, '11680', 0) — 약 290ms
--   · search_stores('공인중개사',50, '11680', 0) — 약 149ms
--   · search_stores('스타벅스', 50, '11680', 0) — 약  30ms   (여긴 걸리는 땅이 적어 원래 싸다)
--
-- 어떻게 고치나 — 자르고 **나서** 만든다
-- --------------------------------------
--   ① ②matched 에서 그 스칼라 하위질의를 뺀다(개수 세기 agg 와 `where agg.n > 0` 은 그대로).
--   ② rows_out 에 lateral 하나를 붙여, 이미 50줄로 잘린 `page` 의 땅마다 요약표를
--      **제 기본키로 한 줄** 다시 읽어(유일 색인 idx_mpsn_pnu) 같은 산식으로 만든다.
--      rows_out 에는 여태 `pat` 이 없었으므로 `cross join pat` 을 함께 붙인다
--      (한 줄짜리 CTE 라 행수를 바꾸지 않는다).
--   => 그 일을 page 가 자른 줄에만 한다(기본 50 · 상한 200).
--
-- ⛔ 이름 배열은 정렬·총계·게이트 어디에도 안 쓰인다 (옮겨도 되는 근거)
-- --------------------------------------------------------------------
--   · tot 의 창 함수 둘 — count(*) over () · sum(match_store_cnt) over ()
--   · ③gate — max(total_parcel_cnt) > search_scope_limit()
--   · page 의 order by — match_store_cnt · exact_hit · road_addr · pnu
--   · 마지막 order by — too_broad · match_store_cnt · exact_hit · road_addr · pnu
-- 넷 중 어디에도 matched_names 가 없다. 그래서 자르기 **뒤로** 옮겨도 어느 줄이
-- 뽑히는지·어떤 순서로 서는지가 달라지지 않는다.
--
-- ⛔ 버린 안 — `h.store_names` 배열을 page 까지 실어 나르기
-- --------------------------------------------------------
-- 이름 배열 대신 **원본 배열**을 matched → tot → page 로 들고 가서 rows_out 에서 풀면
-- 요약표를 다시 안 읽어도 된다. 그런데 그 길은 6,000개짜리 배열 뭉치를 창 함수(tot)와
-- 정렬(page)에 태운다 — 지금보다 무겁다. 다시 읽는 쪽이 싸다.
--
-- ⓘ "점포 표 되짚기 금지(3.2초)"와는 무관하다
-- -------------------------------------------
-- 결정 0028 이 못 박은 금지는 **점포 표(unit_business 277만 행)** 를 2단계로 되짚는 것이다
-- (강남 시제품 찬 캐시 3.2초). 여기서 다시 읽는 것은 요약표(mv_parcel_store_names)의
-- **같은 한 줄**이고, 그것도 유일 색인 idx_mpsn_pnu 로 page 가 자른 줄 수(기본 50 · 상한 200)만큼이다.
--
-- 실행법
-- ------
--   python scripts/dbx.py -f supabase/migrations/2026-09-10b_search_stores_names_after_limit.sql
--
-- 적용한 사람이 보게 되는 것
-- --------------------------
--   · BEGIN · CREATE FUNCTION · REVOKE · COMMIT · NOTIFY
--   · **즉시 끝난다** — 함수 본문 하나를 바꿔 끼울 뿐, 표를 굽거나 훑는 것이 없다.
--   · 중간에 실패하면 **아무것도 안 바뀐 상태**로 되돌아간다 — 고친 뒤 처음부터 다시 돌린다.
--   · 공개 호출 목록은 하나도 안 늘었다 — `python scripts/post_load.py --check` 는 그대로
--     exit 0, 허용 총계 **25 불변**이다(api 쌍둥이는 한 글자도 안 건드린다).
--   · `python scripts/post_load.py` 는 **다시 돌릴 필요가 없다** — 갱신할 표가 안 바뀌었다.
--   · 결과 동일성 확인: 적용 **전** `search_stores('학원',50,'11680',0)`·('카페')·
--     ('스타벅스')·('공인중개사') 의 (pnu, matched_names, match_store_cnt,
--     total_parcel_cnt, total_store_cnt) 를 떠 두고, 적용 **뒤** 같은 쿼리와
--     `except` 를 **양방향**으로 돌려 둘 다 0행이면 같은 답이다.
--
-- 되돌리기: 2026-09-09c 의 `create or replace function search_stores(` 블록(그 파일의
--   public 쪽 함수 + 뒤따르는 revoke)을 그대로 다시 돌린 뒤 `notify pgrst, 'reload schema';`.
--   표·색인·api 쌍둥이는 이 파일이 손대지 않으므로 되돌릴 것이 없다.
--   ⚠️ 라이브만 되돌리면 정본(schema.sql)·가드(tests §9)와 어긋나 시험이 빨강이 된다 —
--      되돌릴 땐 이 PR 자체를 revert 해 정본·가드를 함께 되돌린다.

-- ⛔ 여기부터 commit 까지가 **한 덩어리**다. `scripts/dbx.py` 는 psql 자동커밋으로 돌리므로
--    (`--single-transaction` 이 없다) 감싸지 않으면 함수만 바뀌고 revoke 가 빠진 채 남을 수
--    있다 — 그 순간 public 원본이 열린 채로 라이브에 서 있게 된다.
-- ⓘ `notify` 는 커밋되어야 전달되므로 commit **뒤**에 둔다(09-09b·09-09c 선례).
begin;

create or replace function search_stores(
  q        text,
  lim      int  default 50,
  sigungu  text default null,
  p_offset int  default 0
)
returns table (
  pnu               char(19),
  bld_id            text,
  bld_nm            text,
  road_addr         text,
  jibun_addr        text,
  lat               double precision,
  lng               double precision,
  bld_cnt_in_pnu    int,
  floor_cnt         int,
  min_floor         smallint,
  max_floor         smallint,
  has_roof          boolean,
  matched_names     text[],
  match_store_cnt   int,
  total_parcel_cnt  bigint,
  total_store_cnt   bigint,
  too_broad         boolean,
  store_snapshot_ym text
)
language sql
stable
security definer
set search_path = public
as $$
  with pat as (
    -- 전처리는 형제 search_buildings 의 것을 **글자 그대로** 물려받는다 — 같은 검색어에
    -- 건물과 가게가 다른 답을 내면 안 된다. k 는 **이스케이프 전** 값이다(정확일치 정렬용).
    select
      case when esc.v is null then null else '%' || esc.v || '%' end as p,
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
  -- ① 이름이 걸린 **땅**을 찾는다. 구를 안 골랐으면 0건이다(결정 0007) —
  --    상호는 같은 이름이 전국에 널려 있어 구 없이는 답이 될 수 없다.
  hit as (
    select m.pnu, p.road_addr, m.store_names, m.store_snapshot_ym
      from mv_parcel_store_names m
      -- ⓘ road_addr 은 아래 정렬의 tie-break 에만 쓴다. 요약표에 road_addr 을 또 담지
      --    않는 이유는, 같은 사실을 두 표가 들고 있으면 언젠가 갈리기 때문이다 —
      --    필지 기본키 조회 한 번이 그 위험보다 싸다.
      join parcel p on p.pnu = m.pnu
      cross join pat
     where pat.p is not null
       and pat.gu is not null
       -- ⛔ `::char(5)` 를 지우지 말 것 — 컬럼이 char(5) 인데 text 와 견주면 **컬럼 쪽**이
       --    text 로 캐스트돼 색인이 Index Cond 가 아니라 Filter 로 떨어진다(형제 표 라이브
       --    실측 2026-09-10: 2글자 검색 859.9ms → 76.6ms, 훑는 행 188,442 → 12,138).
       --    `list_parcel_buildings` 의 `p_pnu::char(19)` 와 같은 처방(2026-08-16b).
       -- ⚠️ 5자보다 긴 입력은 bpchar 캐스트가 조용히 자른다 — 구 코드는 서버 목록에서만
       --    오므로 실사용 0건이다.
       and m.sigungu_code = pat.gu::char(5)
       and m.store_names_key like pat.p escape '\'
       -- 층 자료가 아예 없는 건물뿐인 땅은 눌러도 빈 화면이라 뺀다
       -- (검색·결정 0025 와 **같은 규칙** — 갈리면 들어온 길에 따라 다른 답이 된다).
       and exists (
         select 1 from building b
          where b.pnu = m.pnu
            and exists (select 1 from building_floor f
                         where f.bld_id = b.bld_id and f.floor_no is not null)
       )
  ),
  -- ② 그 땅 안에서 **어느 이름이 몇 곳** 걸렸나. 요약표 한 줄 안에서 센다(되짚기 없음).
  matched as (
    select h.pnu, h.road_addr, h.store_snapshot_ym,
           agg.n        as match_store_cnt,
           agg.exact_hit
      -- ⓘ 화면에 적을 이름 셋(matched_names)은 여기서 안 만든다 — 아래 rows_out 의
      --    lateral 로 내려갔다(2026-09-10b · 0028 §백로그 🟡-5). 여기서 만들면
      --    게이트 상한(6,000땅)까지 땅마다 돌고 나서 50줄만 낸다.
      from hit h
      cross join pat
      join lateral (
        select count(*)::int as n,
               coalesce(bool_or(search_key(u.nm) = pat.k), false) as exact_hit
          from unnest(h.store_names) as u(nm)
         where search_key(u.nm) like pat.p escape '\'
      ) agg on true
     -- ⓘ store_names_key 는 이름들을 '|' 로 이은 한 줄이라, 검색어가 그 이음매를 걸치면
     --    ①에서 걸리고도 실제 이름은 하나도 안 맞을 수 있다. 그 헛것을 여기서 뺀다 —
     --    그래야 아래 총계(땅 수·가게 수)가 화면에 서는 줄과 같은 말을 한다.
     where agg.n > 0
  ),
  tot as (
    select m.*,
           count(*) over ()               as total_parcel_cnt,
           sum(m.match_store_cnt) over () as total_store_cnt
      from matched m
  ),
  -- ③ 너무 넓은 검색어인가. 구 안 최다가 '학원' 강남 898땅이라 실제로는 거의 안 닿는
  --    안전망이다(구를 안 고르면 애초에 0건이라 여기 오지도 않는다).
  gate as (
    select coalesce((select max(t.total_parcel_cnt) from tot t), 0)
             > search_scope_limit() as broad
  ),
  page as (
    -- ⛔ 무거운 조인(대표 동·주소 조립·좌표·층 집계) 전에 **상한을 먼저** 건다.
    --    tie-break 에 pnu 를 둔다 — 없으면 같은 수끼리 순서가 흔들려 '더 보기'가
    --    이미 본 줄을 다시 가져오거나 건너뛴다(결정 0025 와 같은 이유).
    select t.*
      from tot t
      cross join gate g
     where not g.broad
     order by t.match_store_cnt desc,
              t.exact_hit       desc,
              t.road_addr       asc nulls last,
              t.pnu
     limit  greatest(1, least(coalesce(lim, 50), 200))
     offset greatest(0, coalesce(p_offset, 0))
  ),
  rows_out as (
    select
      pg.pnu,
      rep.bld_id,
      rep.bld_nm,
      p.road_addr,
      parcel_jibun_addr(p.sido_nm, p.sigungu_nm, p.emd_nm, p.jibun) as jibun_addr,
      -- ⛔ 좌표는 geom 에서만 뽑는다. parcel 의 lat/lng **칸**을 쓰면 검색·상권판정과
      --    자리가 갈려 "마커는 상권 밖인데 글자는 상권 안"이 된다(2026-08-14e 규칙).
      st_y(p.geom)::double precision as lat,
      st_x(p.geom)::double precision as lng,
      cnt.bld_cnt_in_pnu,
      fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof,
      mn.matched_names,
      pg.match_store_cnt,
      pg.total_parcel_cnt,
      pg.total_store_cnt,
      false as too_broad,
      pg.store_snapshot_ym::text as store_snapshot_ym,
      pg.exact_hit
    from page pg
    -- ⓘ pat 은 한 줄짜리 CTE 라 cross join 이 행수를 바꾸지 않는다. 아래 mn lateral 이
    --    검색 패턴(pat.p)과 정확일치 키(pat.k)를 쓰므로 여기서 한 번 끌어온다.
    cross join pat
    join parcel p on p.pnu = pg.pnu
    join lateral (
      -- 대표 동 = 연면적 최대(결정 0025 와 같은 자). 층 자료 없는 동은 뺀다.
      select b.bld_id, b.display_nm as bld_nm
        from building b
       where b.pnu = pg.pnu
         and exists (select 1 from building_floor f
                      where f.bld_id = b.bld_id and f.floor_no is not null)
       order by b.total_area_m2 desc nulls last, b.bld_id
       limit 1
    ) rep on true
    join lateral (
      -- 1 보다 크면 화면이 "같은 땅에 N동"을 적고, 누르면 list_parcel_buildings 로 펼친다.
      -- ⛔ 그 함수도 층 자료 없는 동을 빼므로 여기서도 같은 조건으로 센다 — 안 그러면
      --    "3동"이라 적어 놓고 펼치면 2동만 나온다.
      select count(*)::int as bld_cnt_in_pnu
        from building b2
       where b2.pnu = pg.pnu
         and exists (select 1 from building_floor f
                      where f.bld_id = b2.bld_id and f.floor_no is not null)
    ) cnt on true
    join lateral (
      -- ⛔ 층수 규칙을 여기서 새로 정하지 않는다 — 검색 함수의 것을 글자 그대로 옮겼다.
      --    갈리면 같은 건물이 "지하2~15층"과 "지하2~99층"으로 갈린다.
      select count(*)::int                                    as floor_cnt,
             min(s.floor_no) filter (where s.floor_no <> 99)  as min_floor,
             max(s.floor_no) filter (where s.floor_no <> 99)  as max_floor,
             coalesce(bool_or(s.floor_no = 99), false)        as has_roof
        from v_building_floor_stack s
       where s.bld_id = rep.bld_id
    ) fs on true
    join lateral (
      -- 화면에 적을 이름 최대 3개 — 정확히 같은 이름 먼저, 그다음 가나다.
      -- ⛔ 원문 그대로 낸다(간판에 걸린 공개 이름이다 — 결정 0028 결정 5).
      -- ⛔ 이 셈을 ②(matched)로 되돌리지 말 것 — 거기서 하면 게이트 상한(6,000땅)까지
      --    땅마다 unnest→like→정렬을 돌고 나서 50줄만 낸다. 여기(page 뒤)면 **page 가 자른 줄 수만큼**
      --    (기본 50 · 상한 200)이다(2026-09-10b · 0028 §백로그 🟡-5).
      -- ⓘ 되짚는 곳이 점포 표가 아니라 **요약표의 같은 한 줄**(유일 색인 idx_mpsn_pnu)이라
      --    "점포 표 되짚기 금지(3.2초)"와는 무관하다.
      select array_agg(d.nm order by d.is_exact desc, d.nm) as matched_names
      from (
        select distinct u2.nm,
               (search_key(u2.nm) = pat.k) as is_exact
          from mv_parcel_store_names m2,
               unnest(m2.store_names) as u2(nm)
         where m2.pnu = pg.pnu
           and search_key(u2.nm) like pat.p escape '\'
         order by is_exact desc, nm
         limit 3
      ) d
    ) mn on true
    union all
    -- ⛔ 게이트에 걸리면 **0건이 아니라 한 줄**이다 — 0건이면 화면이 "그런 가게가 없다"고
    --    말하게 되는데 사실은 "너무 많다"이다. 지금의 search_scope 는 상호를 안 세므로
    --    (그걸 고치면 "기존 검색 함수 불변"이 깨진다) 이 함수가 제 총계를 함께 낸다.
    select
      null::char(19), null::text, null::text, null::text, null::text,
      null::double precision, null::double precision,
      null::int, null::int, null::smallint, null::smallint, null::boolean,
      null::text[], null::int,
      gr.total_parcel_cnt, gr.total_store_cnt,
      true, gr.store_snapshot_ym::text,
      false
    from (
      select max(t.total_parcel_cnt) as total_parcel_cnt,
             max(t.total_store_cnt)  as total_store_cnt,
             max(t.store_snapshot_ym) as store_snapshot_ym
        from tot t
    ) gr
    cross join gate g
    where g.broad
  )
  select
    o.pnu, o.bld_id, o.bld_nm, o.road_addr, o.jibun_addr, o.lat, o.lng,
    o.bld_cnt_in_pnu, o.floor_cnt, o.min_floor, o.max_floor, o.has_roof,
    o.matched_names, o.match_store_cnt, o.total_parcel_cnt, o.total_store_cnt,
    o.too_broad, o.store_snapshot_ym
  from rows_out o
  order by
    o.too_broad        desc,
    o.match_store_cnt  desc nulls last,
    o.exact_hit        desc,
    o.road_addr        asc nulls last,
    o.pnu;
$$;

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다
--    (2026-09-01d:89-90 과 같은 관습). ⛔ public 원본에는 grant 를 주지 않는다 —
--    화면은 api 쌍둥이(이 파일이 안 건드린다)로만 들어온다.
revoke all on function search_stores(text, int, text, int) from public, anon, authenticated;

commit;

-- ⛔ 커밋 **뒤**여야 한다 — 롤백된 판에서도 PostgREST 에 헛알림이 가면 안 된다.
--    이게 빠지면 DB 에는 새 함수가 멀쩡히 있는데 화면은 옛 계획을 계속 쓴다.
notify pgrst, 'reload schema';
