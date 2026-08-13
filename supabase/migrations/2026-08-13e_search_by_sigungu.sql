-- =====================================================================
-- 검색을 "고른 구 안에서만" 한다 (2026-08-13e) — 사장님 결정
-- =====================================================================
-- ## 왜 바꾸나 (사장님 지적, 2026-08-13)
--
--   "데이터 정리를 서울이면 서울, 해당 구면 해당 구, 이렇게 분류해서 그 아래에서만
--    검색이 되게 해야지 막 전체 검색하게 하면 좋아? 000빌딩도 최소한 구나 동까지는
--    적어야 검색되게 하면 겹치거나 중복되는 일이 적어질 거 아냐?"
--
-- 맞는 지적이고, 수치가 그것을 뒷받침한다:
--
--   · 같은 건물 이름이 여러 구에 겹친다 — 이름 33,851종 중 **2,443종(7.2%)**이
--     2개 이상 구에 존재한다. 실제로 '명동' 검색은 명동빌딩(강남구)·명동빌딩(중구)·
--     명동프라자(대전 서구)·명동프라자(유성구)를 한꺼번에 내놓았다.
--   · 구로 좁히면 이미 있는 인덱스(idx_parcel_sigungu)만으로 **176ms**.
--     전국을 뒤지면 1,945ms + 겹침.
--   · 지금 자료는 서울 25구(197,403동) + 대전 5구(45,228동) = **30구**뿐이고,
--     가장 큰 강남구가 14,223동이다 ⇒ 구 안에서는 후보가 1/17로 줄어든다.
--
-- ⛔ 이는 결정 0006 의 "지역 선택은 안내일 뿐 검색을 좁히지 않는다"를 **바꾸는
--    결정**이다. 그 결정은 자료가 강남뿐이라 좁힐 것이 없던 시점에 내린 것이고,
--    지금은 30개 구·전국 필지가 들어와 전제가 달라졌다.
--
-- ## 오늘 만든 범위 게이트·요약표는 남긴다 (사장님 결정)
-- 구를 골랐어도 그 안에서 '동' 같은 흔한 말을 넣을 수 있고, 지역을 안 고른 채
-- 부르는 경로(다른 클라이언트·직접 호출)도 있다. 안전망으로 그대로 둔다.

begin;

-- ── 1) 요약표에 시군구 칸을 더한다 ──────────────────────────────────────────
-- 물질화 뷰는 컬럼을 나중에 못 붙인다 → 다시 만든다. 함수가 이 표를 참조하지만
-- language sql 함수 본문은 생성 시점에 의존성이 걸리지 않으므로 순서상 안전하다
-- (그래도 같은 트랜잭션 안에서 끝내 중간 상태가 밖으로 안 보이게 한다).
drop function if exists search_buildings(text, int);
drop function if exists search_scope(text);
drop materialized view if exists mv_search_parcel;

create materialized view mv_search_parcel as
select
  pc.pnu,
  substr(pc.pnu, 1, 5)::char(5) as sigungu_code,   -- 검색 범위를 좁히는 칸
  pc.road_addr,
  pc.road_addr_key,
  pc.jibun_addr_key,
  pc.sido_nm,
  pc.sigungu_nm,
  pc.emd_nm,
  pc.jibun
from parcel pc
where exists (select 1 from building b where b.pnu = pc.pnu);

comment on materialized view mv_search_parcel is
  '§8.1 검색 전용 요약표 — **건물이 있는 필지만** 담는다(2026-08-13). 전국 시드로 parcel 이 '
  '112만 행이 됐지만 건물은 서울·대전 24만 동뿐이라, 나머지 93만 필지는 검색 결과가 될 수 없는데도 '
  '매번 훑혔다(명동 1,725ms → 500). 이 표는 188,442행(42MB, 인덱스 포함 63MB)이라 같은 스캔이 109ms 다. '
  'sigungu_code 는 "고른 구 안에서만 검색"(2026-08-13e)에 쓴다. '
  '⚠️ 자료를 새로 넣으면 `python scripts/post_load.py` 를 반드시 돌릴 것 — '
  '안 하면 새 건물이 조용히 검색에서 빠진다(ANALYZE 와 같은 성격의 적재 후 필수 절차).';

create unique index idx_msp_pnu        on mv_search_parcel (pnu);
create index idx_msp_road_key          on mv_search_parcel using gin (road_addr_key gin_trgm_ops);
create index idx_msp_jibun_key         on mv_search_parcel using gin (jibun_addr_key gin_trgm_ops);
-- 구로 좁히는 것이 이제 기본 경로다 — 이 인덱스가 그 길을 연다.
create index idx_msp_sigungu           on mv_search_parcel (sigungu_code);

analyze mv_search_parcel;

-- ── 2) 고를 수 있는 구 목록 ─────────────────────────────────────────────────
-- ⚠️ **자료가 실제로 있는 구만** 낸다. 목록을 코드에 박아 두면 자료가 없는 구를
--    고를 수 있게 되고, 고르면 아무것도 안 나와 "고장난 것"처럼 보인다.
--    30행짜리라 물질화해 두고 요약표와 함께 갱신한다(매 화면 로드마다 24만 행을
--    집계할 이유가 없다).
drop materialized view if exists mv_open_sigungu;
create materialized view mv_open_sigungu as
select
  substr(pc.sigungu_code, 1, 2)::char(2) as sido_code,
  max(pc.sido_nm)                        as sido_nm,
  pc.sigungu_code,
  max(pc.sigungu_nm)                     as sigungu_nm,
  count(*)::int                          as building_cnt
from mv_search_parcel pc
join building b on b.pnu = pc.pnu
group by pc.sigungu_code;

comment on materialized view mv_open_sigungu is
  '§8.1 지금 검색할 수 있는 시군구 목록(자료가 실제로 있는 곳만). 화면의 지역 고르기가 이걸 읽는다. '
  '⚠️ 목록을 프론트에 박지 말 것 — 자료 없는 구를 고르면 "고장난 것"처럼 보인다. '
  '`python scripts/post_load.py` 가 mv_search_parcel 과 함께 갱신한다.';

create unique index idx_mos_sigungu on mv_open_sigungu (sigungu_code);
analyze mv_open_sigungu;

create or replace function list_open_sigungu()
returns table (sido_code char(2), sido_nm text, sigungu_code char(5), sigungu_nm text, building_cnt int)
language sql
stable
security definer
set search_path = public
as $$
  select m.sido_code, m.sido_nm, m.sigungu_code, m.sigungu_nm, m.building_cnt
  from mv_open_sigungu m
  order by m.sido_code, m.sigungu_nm;
$$;

comment on function list_open_sigungu() is
  '§8.1 화면의 지역 고르기가 부르는 목록 — 자료가 실제로 있는 시군구만. security definer '
  '(원본 표가 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. 나가는 것은 지역명·건물수뿐)';

-- ── 3) 범위 판정 — 고른 구 안에서만 센다 ────────────────────────────────────
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
          and (pat.gu is null or pc.sigungu_code = pat.gu)
          and (pc.road_addr_key  like pat.p escape '\'
            or pc.jibun_addr_key like pat.p escape '\')) as addr_cnt,
      (select count(*) from building b
         join mv_search_parcel pc on pc.pnu = b.pnu
         cross join pat
        where pat.p is not null
          and (pat.gu is null or pc.sigungu_code = pat.gu)
          and b.nm_key like pat.p escape '\')            as nm_cnt
  )
  select greatest(c.addr_cnt, c.nm_cnt) > search_scope_limit(),
         least(greatest(c.addr_cnt, c.nm_cnt), 2147483647)::int
  from c;
$$;

comment on function search_scope(text, text) is
  '§8.1 검색어가 몇 곳과 맞는지 세어 "너무 넓은 검색"인지 알려준다. sigungu 를 주면 그 구 안에서만 센다. '
  '화면은 결과가 0건일 때 이걸 불러 "찾는 게 없음"과 "너무 넓음"을 구분한다. '
  '**찾힐 수 있는 필지(mv_search_parcel)만** 센다 — 건물 없는 필지를 세면 판정이 실제보다 넓어진다.';

-- ── 4) 검색 본체 — 고른 구 안에서만 ─────────────────────────────────────────
create or replace function search_buildings(q text, lim int default 25, sigungu text default null)
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
       and (pat.gu is null or pc.sigungu_code = pat.gu)
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
       and (pat.gu is null or pc.sigungu_code = pat.gu)
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
  -- ② 지번주소 조립은 여기서 처음 한다 — 25행에만 필요하다.
  select
    t.bld_id, t.pnu, t.bld_nm, t.road_addr,
    parcel_jibun_addr(pc.sido_nm, pc.sigungu_nm, pc.emd_nm, pc.jibun) as jibun_addr,
    (select count(*)::int from building b2 where b2.pnu = t.pnu) as bld_cnt_in_pnu,
    fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof,
    t.total_cnt
  from top t
  join mv_search_parcel pc on pc.pnu = t.pnu
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

comment on function search_buildings(text, int, text) is
  '§8.1 건물 검색. 건물 1개 = 1행이며 total_cnt로 정확한 전체 건수를 함께 준다. '
  'sigungu 를 주면 **그 구 안에서만** 찾는다(2026-08-13e, 사장님 결정) — 같은 건물 이름이 '
  '여러 구에 겹치기 때문이다(이름 33,851종 중 2,443종이 2개 이상 구에 존재). '
  'security definer — 원본 표가 anon에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '입력의 % _ \ 는 서버가 리터럴로 이스케이프하고, 빈 검색어는 0건으로 잘라낸다. '
  '이름은 building.display_nm(동명칭 폴백 + 개인 성명 가림)만 본다 — 보이는 것 = 검색되는 것. '
  '주소는 mv_search_parcel(건물이 있는 필지만)을 본다. ⚠️ 자료 적재 후 `python scripts/post_load.py` 필수. '
  '⛔ 주소 가지와 이름 가지를 OR로 합치지 말 것 — 두 조인 테이블에 걸친 OR은 gin_trgm 인덱스를 무력화한다';

grant execute on function search_scope(text, text) to anon, authenticated;
grant execute on function search_buildings(text, int, text) to anon, authenticated;
grant execute on function list_open_sigungu() to anon, authenticated;
revoke all on function search_scope_limit() from public, anon, authenticated;

commit;
