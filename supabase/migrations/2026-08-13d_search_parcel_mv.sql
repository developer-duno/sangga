-- =====================================================================
-- 검색은 "찾힐 수 있는 필지"만 훑는다 — 전용 요약표 (2026-08-13)
-- =====================================================================
-- ## 무엇이 고장났나 (전국 시드 직후 라이브 실측)
--
--   명동   0.59초 → **HTTP 500** (3초 초과)   ← 게다가 게이트에 막혀 0건
--   역전        → **HTTP 500**
--   둔산동 0.03초 → 1.65초
--   search_scope(안내 문구용) 1.1초 → **500**
--
-- 전국 시드로 parcel 이 197,076 → **1,119,149행**(5.7배)이 됐다. 그런데
-- **건물은 서울·대전(242,631동) 그대로**다. 즉 늘어난 93만 필지는 **어차피 검색
-- 결과가 될 수 없는데도**(건물이 없으니 조인에서 전부 탈락) 검색할 때마다 훑혔다.
--
-- ## 왜 필터로는 안 고쳐지나 (후보 4개 전부 실측)
--
--   현행(필지 112만 전부 스캔)          1,725ms
--   + 건물 있는 필지만 (EXISTS)          4,620ms   ← 더 느리다
--   + 건물에서 출발 (건물→필지 pkey)     2,401ms
--   + 열린 지역(서울11·대전30)만          1,417ms
--   검색 전용 요약표(188,442행, 42MB)      **109ms**  ← 15.8배
--
-- 2글자 검색어는 trigram 이 못 걸러 **어차피 표를 통째로 훑는다**(§2026-08-13
-- search_scope_gate 참조). 그러면 비용은 "무엇을 거르나"가 아니라 **"몇 행을
-- 훑나"로 정해진다** ⇒ 훑을 표 자체를 작게 만드는 것 말고 답이 없다.
--
-- ## 두 번째 효과 — 게이트가 다시 정확해진다
--
-- 범위 판정이 필지 수를 세는데, 시드 뒤로는 **건물이 없는 필지까지 세어** 실제보다
-- 넓게 잡았다. 그래서 '명동'(전국 필지 약 10,036 > 상한 6,000)이 **막혔다** —
-- 사장님이 "명동은 동이 확정되니 유효하다"고 짚으신 바로 그 검색어가.
-- 요약표는 찾힐 수 있는 것만 담으므로(명동 1,349) 판정이 다시 맞는다.
--
-- ## ⚠️ 유지비 — 자료를 새로 넣으면 반드시 갱신할 것
--
--     refresh materialized view concurrently mv_search_parcel;
--
-- 안 하면 **새로 넣은 건물이 검색에 안 나온다**(에러가 아니라 조용한 누락).
-- `ANALYZE` 와 같은 성격의 적재 후 필수 절차다. CLAUDE.md 운영 계명에 박아 뒀고,
-- 회귀 가드(tests/test_display_name_sql_sync.py)가 검색 함수가 이 표를 보는지 지킨다.
-- ⚠️ concurrently 는 아래 unique 인덱스가 있어야 동작한다(없으면 조회가 잠긴다).

create materialized view if not exists mv_search_parcel as
select
  pc.pnu,
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
  '⚠️ 자료를 새로 넣으면 `refresh materialized view concurrently mv_search_parcel;` 를 반드시 돌릴 것 — '
  '안 하면 새 건물이 조용히 검색에서 빠진다(ANALYZE 와 같은 성격의 적재 후 필수 절차).';

-- concurrently 갱신에 필수 + pnu 되짚기용
create unique index if not exists idx_msp_pnu on mv_search_parcel (pnu);
-- 부분 일치(LIKE '%…%')라 gin_trgm_ops 가 필요하다(3글자 이상에서만 선별력이 있다).
create index if not exists idx_msp_road_key  on mv_search_parcel using gin (road_addr_key gin_trgm_ops);
create index if not exists idx_msp_jibun_key on mv_search_parcel using gin (jibun_addr_key gin_trgm_ops);

analyze mv_search_parcel;

-- ── 범위 판정도 요약표를 본다 ────────────────────────────────────────────────
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
      -- ⚠️ parcel 이 아니라 mv_search_parcel 이다 — 건물이 없는 필지를 세면 판정이
      --    실제보다 넓어져 '명동' 같은 정상 검색이 막힌다(2026-08-13 실측).
      (select count(*) from mv_search_parcel pc cross join pat
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
  '이걸 불러 "찾는 게 없음"과 "너무 넓음"을 구분한다. **찾힐 수 있는 필지(mv_search_parcel)만** 센다 — '
  '건물 없는 필지를 세면 판정이 실제보다 넓어진다. security definer — 원본 표가 anon 에게 '
  '닫혀 있어 소유자 권한으로 대신 센다(돌려주는 것은 개수뿐이라 개인정보가 나가지 않는다).';

-- ── 검색 본체도 요약표를 본다 ───────────────────────────────────────────────
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
      -- ⚠️ k 는 **이스케이프 전** 값이다(정확일치·앞글자일치 정렬에 쓴다).
      search_key(q) as k
    from (
      select case when search_key(q) is null then null
                  else replace(replace(replace(search_key(q), '\', '\\'),
                               '%', '\%'), '_', '\_')
             end as v
    ) esc
  ),
  -- ① 주소 두 칸은 같은 표라 한 번만 훑는다. 그리고 그 표는 **검색 전용 요약표**다
  --    — 건물이 없는 필지는 어차피 아래 조인에서 전부 탈락하므로 훑을 이유가 없다.
  --    `limit 상한+1` 이 범위 게이트를 겸한다(따로 세면 표를 두 번 더 훑는다).
  addr as materialized (
    select pc.pnu, pc.road_addr, pc.jibun_addr_key
      from mv_search_parcel pc
      cross join pat
     where pat.p is not null
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
     where pat.p is not null and b.nm_key like pat.p escape '\'
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

comment on function search_buildings(text, int) is
  '§8.1 건물 검색. 건물 1개 = 1행이며 total_cnt로 정확한 전체 건수를 함께 준다. '
  'security definer — 원본 표가 anon에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '입력의 % _ \ 는 서버가 리터럴로 이스케이프하고, 빈 검색어는 0건으로 잘라낸다. '
  '이름은 building.display_nm(동명칭 폴백 + 개인 성명 가림)만 본다 — 보이는 것 = 검색되는 것. '
  '주소는 **mv_search_parcel**(건물이 있는 필지만)을 본다 — 전국 시드 뒤 parcel 112만 행을 훑느라 '
  '2글자 검색이 3초를 넘겼다(2026-08-13). ⚠️ 자료 적재 후 그 요약표 갱신 필수. '
  '너무 넓은 검색(search_scope_limit() 초과)은 무거운 일을 하기 전에 0건으로 끊는다 — 상권분석은 '
  '건물 한 채 단위라 "서울" 같은 검색은 결과 25개를 보여줘도 의미가 없다. '
  '⛔ 주소 가지와 이름 가지를 OR로 합치지 말 것 — 두 조인 테이블에 걸친 OR은 gin_trgm 인덱스를 무력화한다';
