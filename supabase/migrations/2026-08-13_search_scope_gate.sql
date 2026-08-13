-- =====================================================================
-- 검색: 한 곳을 짚는 검색만 받는다 + 주소 두 칸을 한 번의 스캔으로 (2026-08-13)
-- =====================================================================
-- ## 무엇이 고장나 있었나 (라이브 실측 2026-08-13, anon 공개키)
--
--   '강남' '빌딩' '서울' '동' '1'  → 전부 HTTP 500 (57014 statement timeout, 3초)
--   '명동' 1.62초 / '둔산동' 0.86초 → 아슬아슬하게 통과
--
-- 서울+대전 적재로 building 이 13,817 → 242,631행(17.6배)이 되면서, 강남 파일럿에서
-- 멀쩡하던 검색이 흔한 단어에서 통째로 실패하게 됐다.
--
-- ## 원인 ① — trigram 인덱스는 **3글자 미만에서 선별력이 0** 이다
--
-- pg_trgm 은 LIKE '%…%' 를 색인할 때 패턴 안에 **완전히 들어가는 3글자 조각**만 쓴다.
-- 검색어가 2글자면 그런 조각이 하나도 안 나오므로 인덱스가 아무것도 못 거른다.
-- EXPLAIN 실측(2026-08-13):
--   '%강남%'   → Seq Scan 123ms          (플래너가 인덱스를 아예 포기)
--   '%강남구%' → Bitmap Index Scan 17.6ms (7배 빠름)
-- 함수 안에서는 검색어가 실행 시점 값이라 플래너가 길이를 모른다. 그래서 인덱스를
-- 쓰기로 정했다가 런타임에 후보가 거의 전부가 되고, 재확인으로 18만 행을 버린다
-- (Rows Removed by Index Recheck: 183,547) — Seq Scan 보다 오히려 2.4배 느리다.
--
-- ## 원인 ② — 같은 표를 두 번 훑고 있었다
--
-- 옛 구조는 road_addr_key 가지와 jibun_addr_key 가지가 **각각** parcel 을 스캔하고
-- **각각** building 에 조인했다. 둘 다 parcel 한 표라 OR 로 합치면 한 번만 훑어도 된다.
-- (schema.sql 의 "OR 로 되돌리지 말 것" 경고는 **서로 다른 두 표에 걸친 OR** 이야기다.
--  같은 표의 두 칸을 OR 로 묶는 것은 BitmapOr 로 잘 처리된다 — 다른 상황이다.)
--
-- ## 원인 ③ — 25건만 보여주는데 26,753건 전부의 지번주소를 조립했다
--
-- parcel_jibun_addr() 는 최종 25행에만 필요하다. 마지막에 pnu 로 되짚어 계산한다
-- (pnu 는 parcel 의 기본키라 같은 값이 나온다 = 결과가 바뀌지 않는다).
--
-- ## 고친 뒤 (같은 장비·같은 검색어)
--
--   강남   1,917ms → 869ms
--   빌딩   8,053ms → 1,868ms
--   서울   8,892ms → 5,321ms   ← 여전히 불가능. 아래 ④ 가 이걸 맡는다
--   둔산동          →    59ms
--
-- 20개 검색어(특수문자 % _ \ · 빈 문자열 · 공백만 · 성명 마스킹 대상 포함)로
-- 옛 함수와 결과를 대조해 **전부 0행 차이 + total_cnt 까지 동일**함을 확인했다.
--
-- ## 원인 ④ — 그리고 어떤 기술로도 못 고치는 것이 남는다
--
--   '동'  → 필지 193,090곳과 매칭 (전체 197,076의 **98%**)
--   '서울' → 163,487곳 (83%)
--
-- 20만 건을 정렬해서 25개를 고르는 일은 3초 안에 끝나지 않는다. 계획을 아무리 고쳐도
-- 마찬가지다. 그런데 **이건 성능 문제가 아니라 제품 문제**다 — 이 서비스는 상권분석이고,
-- 분석 단위는 건물 한 채·필지 한 곳이다. '서울'이나 '동'으로는 어느 곳을 분석할지
-- 정해지지 않으므로, 결과 25개를 억지로 보여주는 것 자체가 의미가 없다.
-- 그래서 **너무 넓은 검색은 빨리 0행으로 돌려주고 화면이 안내**하게 한다.
-- (⛔ 결과를 임의로 잘라 보여주지 않는다는 방침은 그대로다 — 자르는 게 아니라 안 한다.)

-- ── 상한: 어디까지가 "한 곳을 짚는 검색"인가 ──────────────────────────────────
-- 글자 수로 가르면 안 된다. '명동'은 2글자여도 동이 확정되지만 '강남'은 2글자에
-- 구 조각이다. 그래서 **몇 곳이 걸리는가**로 가른다. 선은 실측으로 정했다:
--
--   가장 큰 법정동   신림동 4,537필지   ← 검색이 실제로 세는 기준(mv_search_parcel)
--   가장 작은 구 검색 '유성구' 7,159필지  ← 같은 기준
--   ⚠️ 옛 주석은 '유성구 11,248'이라 적었는데 그건 parcel×building **조인 행수**였다
--      (한 필지에 건물이 여럿이면 중복 집계). search_scope() 는 조인 없이 필지만 센다.
--
-- 6,000 은 그 사이다 ⇒ **어떤 동 이름도 통과하고, 시·구 이름은 걸린다.**
--   통과: 둔산동 701 · 명동 1,349 · 역삼동 2,819 · 신림동 4,537
--   차단: 유성구 7,159 · 강남 12,961 · 서울·동 등 시도 단위
--   ⛔ **"구 이름은 전부 차단된다"는 말은 사실이 아니다** — 30개 구 중 **13개**는
--      상한 미만이라 통과한다(가장 작은 노원구 3,479 · 금천 3,492 · 도봉 3,710).
--      이 게이트가 확실히 막는 것은 **시·도 단위**이고, 구는 큰 곳만 걸린다.
--      2026-08-13e 부터는 화면이 구를 먼저 고르므로 이 게이트는 **안전망**이다.
--
-- ⚠️ 데이터가 전국으로 늘면 동 하나의 필지 수도 늘 수 있다. 그때는 위 두 수를
--    다시 재고 이 값을 올려라(정본은 여기 한 곳뿐이다).
create or replace function search_scope_limit()
returns int
language sql
immutable
parallel safe
as $$ select 6000 $$;

comment on function search_scope_limit() is
  '검색이 "한 곳을 짚는" 것으로 인정되는 상한(곳). 가장 큰 법정동(신림동 4,633)보다 크고 '
  '가장 작은 구 단위 검색(유성구 11,248)보다 작게 잡았다 — 동 이름은 통과, 시·구 이름은 차단.';

-- ── 이 검색어가 몇 곳과 맞는가 ───────────────────────────────────────────────
-- 세기만 하는 일이라 싸다(조인·정렬이 없다). 무거운 검색은 이걸로 먼저 걸러낸다.
-- 주소(필지)와 건물이름은 세는 대상이 다르므로 **큰 쪽**으로 판정한다
--   예: '빌딩' 은 주소 매칭 0곳이지만 건물이름 15,068곳 → 큰 쪽인 15,068 로 판정.
create or replace function search_scope(q text)
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
           end as p
  ),
  c as (
    select
      (select count(*) from parcel pc cross join pat
        where pat.p is not null
          and (pc.road_addr_key  like pat.p escape '\'
            or pc.jibun_addr_key like pat.p escape '\')) as addr_cnt,
      (select count(*) from building b cross join pat
        where pat.p is not null
          and b.nm_key like pat.p escape '\')             as nm_cnt
  )
  select greatest(c.addr_cnt, c.nm_cnt) > search_scope_limit(),
         least(greatest(c.addr_cnt, c.nm_cnt), 2147483647)::int
  from c;
$$;

comment on function search_scope(text) is
  '§8.1 검색어가 몇 곳과 맞는지 세어 "너무 넓은 검색"인지 알려준다. 화면은 결과가 0건일 때 '
  '이걸 불러 "찾는 게 없음"과 "너무 넓음"을 구분한다. security definer — 원본 표가 anon 에게 '
  '닫혀 있어 소유자 권한으로 대신 센다(돌려주는 것은 개수뿐이라 개인정보가 나가지 않는다).';

-- ── 검색 본체 ────────────────────────────────────────────────────────────────
create or replace function search_buildings(q text, lim int default 25)
returns table (
  bld_id         text,
  pnu            char(19),
  bld_nm         text,
  road_addr      text,
  jibun_addr     text,
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
      -- ⚠️ k 는 **이스케이프 전** 값이다. 정확일치·앞글자일치 정렬에 쓰는 값이라
      --    이스케이프하면 안 된다(옛 코드는 여기에 이스케이프된 값을 넣어, 이름에
      --    % 나 _ 가 든 건물에서 정확일치 가산점이 조용히 안 먹었다. 마지막
      --    ORDER BY 는 반대로 이스케이프 안 한 값을 써서 두 정렬이 서로 어긋났다).
      search_key(q) as k
    from (
      select case when search_key(q) is null then null
                  else replace(replace(replace(search_key(q), '\', '\\'),
                               '%', '\%'), '_', '\_')
             end as v
    ) esc
  ),
  -- ① 주소 두 칸은 **같은 표**라 한 번만 훑는다 (조인 전 단일 표의 OR 은 안전하다)
  --
  -- ⭐ `limit 상한+1` 이 범위 게이트를 겸한다. 따로 세지 않는 이유: 세는 일을 별도
  --    조회로 두면 좁은 검색어까지 표를 두 번 더 훑어 **오히려 느려진다**
  --    (실측 2026-08-13: '명동' 796ms → 2,803ms). 여기서 상한+1 에서 멈추면
  --      · 넘쳤다 = "한 곳을 짚는 검색이 아니다" → 아래에서 통째로 끊는다
  --      · 안 넘쳤다 = 여기 모인 것이 **곧 전체**다(잘린 것이 없다 = total_cnt 정확)
  --    넓은 검색어는 상한에서 바로 멈추므로 20만 건을 다 훑지 않는다.
  addr as materialized (
    select pc.pnu, pc.road_addr, pc.jibun_addr_key
      from parcel pc
      cross join pat
     where pat.p is not null
       and (pc.road_addr_key  like pat.p escape '\'
         or pc.jibun_addr_key like pat.p escape '\')
     limit search_scope_limit() + 1
  ),
  -- ⛔ 주소 가지와 이름 가지를 OR 하나로 합치지 말 것 — 이쪽은 **서로 다른 두 표**라
  --    조인 전에 한 표를 못 걸러 gin_trgm 인덱스가 통째로 무력화된다(2026-08-08 실측).
  -- ⛔ WHERE 는 **저장 컬럼**(nm_key/road_addr_key/jibun_addr_key)을 써야 한다.
  --    식으로 되돌리면 재확인 때 regexp 가 다시 돌아 3초를 넘긴다(2026-08-11e).
  nm as materialized (
    select b.bld_id, b.pnu, b.nm_key,
           building_display_nm(b.bld_nm, b.dong_nm) as bld_nm,
           pc.road_addr, pc.jibun_addr_key
      from building b
      join parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null and b.nm_key like pat.p escape '\'
     limit search_scope_limit() + 1
  ),
  gate as (
    select ((select count(*) from addr) > search_scope_limit()
         or (select count(*) from nm)   > search_scope_limit()) as broad
  ),
  hit as (
    select b.bld_id, b.pnu, b.nm_key,
           building_display_nm(b.bld_nm, b.dong_nm) as bld_nm,
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
  -- ② 지번주소 조립은 여기서 처음 한다 — 25행에만 필요하다.
  --    pnu 는 parcel 의 기본키라 되짚어도 같은 한 행이다(값이 달라지지 않는다).
  select
    t.bld_id, t.pnu, t.bld_nm, t.road_addr,
    parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun) as jibun_addr,
    (select count(*)::int from building b2 where b2.pnu = t.pnu) as bld_cnt_in_pnu,
    fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof,
    t.total_cnt
  from top t
  join parcel pc on pc.pnu = t.pnu
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

comment on function search_buildings(text, int) is
  '§8.1 건물 검색. 건물 1개 = 1행이며 total_cnt로 정확한 전체 건수를 함께 준다. '
  'security definer — 원본 표가 anon에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '입력의 % _ \ 는 서버가 리터럴로 이스케이프하고, 빈 검색어는 0건으로 잘라낸다. '
  '이름은 building_display_nm() 하나만 본다(동명칭 폴백 + 개인 성명 가림) — 보이는 것 = 검색되는 것. '
  '너무 넓은 검색(search_scope_limit() 초과)은 무거운 일을 하기 전에 0건으로 끊는다 — 상권분석은 '
  '건물 한 채 단위라 "서울" 같은 검색은 결과 25개를 보여줘도 의미가 없다(2026-08-13). '
  '⛔ 주소 가지와 이름 가지를 OR로 합치지 말 것 — 두 조인 테이블에 걸친 OR은 gin_trgm 인덱스를 무력화한다';

-- 상한 함수는 내부용이다. 화면은 search_scope() 가 돌려주는 판정만 쓴다.
revoke all on function search_scope_limit() from public, anon, authenticated;
grant execute on function search_scope(text) to anon, authenticated;
