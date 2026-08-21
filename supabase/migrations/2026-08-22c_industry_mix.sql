-- =====================================================================
-- 마이그레이션 2026-08-22c — 상권·반경 업종 분포 (결정 0014 "상권 지표 계산" 1단계)
-- =====================================================================
-- 실행법 ⚠️ **대시보드 SQL Editor 로 돌린다.**
--   `create index concurrently` 가 아니라 보통 create 라 한 트랜잭션에 들어간다.
--   → Supabase 대시보드 → SQL Editor 에 이 파일을 통째로 붙여 실행.
--   → 그다음 **반드시** `python scripts/post_load.py` (요약표 갱신 + 노출 점검).
--
-- ⏱ 오래 걸리는 문장이 둘이다(라이브 실측): 물질화뷰 굽기 **약 27초**,
--    커버링 인덱스 만들기 **약 40초**. 맨 앞의 statement_timeout 을 지우지 말 것.
--
-- ─────────────────────────────────────────────────────────────────────
-- 무엇을 만드나
-- ─────────────────────────────────────────────────────────────────────
-- 층별 화면에 "이 동네에 무슨 장사가 몇 곳 있나"를 두 가지 자로 보여준다:
--   ① 상권 스코프 — 이 땅이 속한 상권(들) 안의 점포를 업종 대분류로 센다.
--                   겹치면 **전부** 나열한다(결정 0011 과 같은 규칙).
--   ② 반경 스코프 — 이 땅에서 500m 안의 점포를 같은 방식으로 센다.
-- 대분류 하나를 고르면 그 안의 중분류를 다시 센다(`list_industry_detail`).
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 상권 스코프만 미리 계산하나 (라이브 실측이 정했다 — 추측이 아니다)
-- ─────────────────────────────────────────────────────────────────────
-- 2026-08-22 라이브에서 후보를 전부 재 봤다(잠실 관광특구 = 가장 넓은 상권):
--
--   ① 상권 안 점포를 그때그때 세기          → **12,512ms**(찬 캐시) / 56ms(더운 캐시)
--   ② 반경 500m, geom::geography 로 바로    → **47,756ms**  ← 캐스트가 gist 인덱스를 죽인다
--   ③ 반경 500m, bbox 선거름 + geography    →   2,976ms     ← 3초 제한 코앞
--   ④ 반경 500m, 이웃 필지 PNU 배열 경유    →     469ms     ← 채택
--
-- ①이 더울 때 56ms 인데 찰 때 12.5초인 것이 핵심이다. 2026-08-11 의 `v_coverage_stats`
-- 500 사고와 **같은 병**이다 — 더운 캐시로 재 놓고 "빠르다"고 하면 첫 방문자만 죽는다.
-- 상권 안 점포 수는 (상권, 분기)만으로 정해지고 필지와 무관하므로 미리 계산할 수 있다.
-- 전국을 한 번 굽는 데 **26.7초**, 결과는 **62,457행 / 5.6MB** 뿐이다. 읽기는 **0.32ms**.
-- (스키마 L4 주석의 "district = 사전계산 대상 ★ 엔진 패턴" 이 말하던 바로 그것이다.)
--
-- ⚠️ 반대로 **반경 스코프는 미리 계산하지 않는다.** 답이 필지마다 달라 표가 필지 수만큼
--    (110만 행 × 업종) 커진다. ④가 수백 ms 라 살아있는 쿼리로 충분하다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 반경을 "이웃 필지 PNU 배열"로 재나 (자를 형제와 맞춘다)
-- ─────────────────────────────────────────────────────────────────────
-- `list_price_bands` 가 이미 같은 화면에서 "반경 500m"를 **이웃 필지**로 정의해 쓴다.
-- 한 화면의 두 블록이 서로 다른 자로 500m 를 재면 비교가 거짓말이 된다.
--
-- 그래서 두 자가 실제로 같은 답을 내는지 8곳에서 대조했다(2026-08-22 라이브):
--   종로 143/143 · 중구 4,360/4,358 · 강서 623/623 · 구로 202/204 ·
--   강남 4,655/4,659 · 송파 82/83 · 대전중구 1,458/1,437 · 대전서구 455/464
-- 최대 차이 1.4% — 점포 점을 직접 재는 것과 사실상 같으면서 6배 빠르다.
-- (`unit_business.pnu` 채움률 99.94% — 최신 분기 2,772,484 중 2,770,692.)
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 커버링 인덱스가 필요한가 · 왜 옛 인덱스를 지우나
-- ─────────────────────────────────────────────────────────────────────
-- ④(469ms)도 이웃이 많은 자리에서는 훨씬 느려진다. 원인은 `idx_ub_pnu` 가 행 위치만
-- 알려 줘서, 업종 칸을 읽으려고 **점포마다 힙을 한 번씩** 뒤지기 때문이다. 업종 네 칸을
-- 인덱스 안에 넣어 두면 힙에 갈 일이 없다(2026-08-11 `idx_ub_snapshot_floor_pnu` 와 같은 처방).
--
-- ⚠️ **최악 표본** — 독립 검토(2026-08-22)가 40개 필지를 훑어 찾은 가장 무거운 자리는
--    강남이 아니라 **중구 `1114013400101890026`**(이웃 **1,414필지 · 점포 4,433곳**)이다.
--    이 값은 캐시와 무관하게 재현된다(라이브 재확인). 표본이 40개뿐이라 **진짜 최악은
--    이보다 더 클 수 있다.**
--
--   찬 캐시, 옛 인덱스 : **2,383ms** (독립 검토 실측)
--   찬 캐시, 새 인덱스 : 아래 "검산" 참조 — 적용 후 실측해 여기에 적는다
--
-- ⚠️ 더운 캐시로는 이 차이가 안 보인다. 같은 조회가 옛 인덱스로도 **23ms** 로 끝난다
--    (힙 페이지가 이미 메모리에 있으면 힙 방문이 공짜다). 그러니 before/after 는 반드시
--    **같은 캐시 상태끼리** 견줄 것 — 이 인덱스가 지키는 것은 **첫 방문자**다.
--
-- 옛 `idx_ub_pnu (pnu, snapshot_ym)` 는 새 인덱스의 **앞부분과 똑같다**. 남겨 두면
-- 105MB 를 그냥 두 번 쓰는 것이라 지운다(2026-08-22a 가 idx_ub_snapshot_floor 에 한 것과
-- 같은 정리). 새 인덱스 279MB − 옛 105MB = 실질 +174MB (DB 4,320MB 기준 +4%).
--
-- 검산 (실행 후 — 최악 표본인 중구 필지로):
--   explain (analyze, buffers) select * from list_industry_mix('1114013400101890026');
--     → 계획에 "Index Only Scan using idx_ub_pnu_cat" 와 **Heap Fetches: 0** 이 보여야 한다.
--       (Heap Fetches 가 0 이 아니면 vacuum 이 덜 된 것 — post_load.py 가 대신 돈다.)

set statement_timeout = '900s';

-- ─────────────────────────────────────────────────────────────────────
-- 1) 커버링 인덱스 — 반경 스코프가 힙에 안 가게
-- ─────────────────────────────────────────────────────────────────────
create index if not exists idx_ub_pnu_cat
  on unit_business (pnu, snapshot_ym)
  include (cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm);

comment on index idx_ub_pnu_cat is
  '반경 업종 집계 전용 커버링 인덱스. 앞 두 칸은 옛 idx_ub_pnu 와 같고, include 네 칸 덕에 '
  'Index Only Scan 이 되어 힙을 안 읽는다(라이브 실측 1,583ms → 23ms · Heap Fetches 0). '
  '⛔ include 를 지우면 그 순간 옛 성능으로 되돌아간다 — 에러는 안 나고 느려지기만 한다.';

-- ⓘ 옛 `idx_ub_pnu` 를 지우는 문장은 **이 파일 맨 끝**에 있다. 여기가 아니다 — 이유는
--    그 자리의 주석 참조(표를 잠그는 문장이라 마지막에 둔다).

-- ─────────────────────────────────────────────────────────────────────
-- 2) mv_district_industry_mix — 상권 × 업종 사전계산
-- ─────────────────────────────────────────────────────────────────────
-- 중분류까지 세어 둔다. 대분류는 여기서 합치면 되므로 표를 둘로 나눌 이유가 없다
-- (62,457행 · 5.6MB 뿐이다).
--
-- ⚠️ **최신 분기 한 개만** 담는다. 분기를 다 담으면 굽는 시간이 분기 수만큼 늘어나는데
--    화면은 최신만 쓴다. 새 분기를 적재하면 `post_load.py` 의 갱신이 저절로 따라온다.
drop materialized view if exists mv_district_industry_mix;

create materialized view mv_district_industry_mix as
select d.district_id,
       ub.snapshot_ym,
       ub.cat_l_cd, ub.cat_l_nm,
       ub.cat_m_cd, ub.cat_m_nm,
       count(*)::int as n
from district d
join unit_business ub
  on ub.geom is not null
 and st_contains(d.geom, ub.geom)
where ub.snapshot_ym = (select max(u.snapshot_ym) from unit_business u)
group by 1, 2, 3, 4, 5, 6;

comment on materialized view mv_district_industry_mix is
  '상권 × 업종(중분류) 점포 수 — 최신 분기 한 개만. 살아있는 쿼리는 찬 캐시에서 12.5초라 '
  '미리 굽는다(라이브 실측, 굽기 26.7초 · 읽기 0.32ms). 대분류는 이 표를 합쳐서 낸다. '
  '⚠️ 상권이 겹치는 자리의 점포는 **양쪽에 모두** 세어진다(2026-08-22 실측: 상권 안 462,858곳 중 '
  '17,946곳 = 3.9% 가 두 상권에 겹침, 3겹은 0건). 상권끼리 더하면 그만큼 부풀려진다. '
  '⛔ anon 에게 열지 않는다 — 화면은 list_industry_mix 함수로만 읽는다.';

-- refresh concurrently 에 반드시 필요하다(고유 인덱스가 없으면 갱신이 표를 잠근다).
-- 조회(상권 몇 개 + 분기 하나)도 이 인덱스로 그대로 탄다 — 라이브 실측 0.32ms.
create unique index if not exists mv_district_industry_mix_key
  on mv_district_industry_mix (district_id, snapshot_ym, cat_m_cd);

-- ⛔ Supabase 는 새로 만드는 표·물질화뷰를 anon 에게 자동으로 연다(pg_default_acl).
--    기본 권한을 닫아 뒀어도(2026-08-13f·g) **만든 자리에서 한 번 더** 닫는다 —
--    그 기본값은 "그것을 실행한 롤이 만드는 것"에만 걸리기 때문이다.
revoke all on mv_district_industry_mix from public, anon, authenticated;

-- ─────────────────────────────────────────────────────────────────────
-- 3) list_industry_mix(p_pnu) — 대분류 분포 (상권 + 반경)
-- ─────────────────────────────────────────────────────────────────────
-- ⚠️ 파라미터를 `p_` 로 시작하는 이유: `pnu` 는 컬럼 이름과 겹친다. 겹치면 PostgreSQL 이
--    컬럼을 우선 집어 `where p.pnu = p.pnu`(= 전 국토)가 된다.
-- ⛔ `p_pnu::char(19)` 의 캐스트를 지우지 말 것. pnu 컬럼이 char(19) 인데 text 와 견주면
--    **컬럼 쪽**이 text 로 캐스트돼 인덱스가 통째로 죽는다(2026-08-16b 실측 459.8ms↔0.796ms).
create or replace function list_industry_mix(p_pnu text)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  with snap as (
    -- 두 블록이 반드시 **같은 분기**를 말하게 한다. 정본은 사전계산표 쪽이다 —
    -- 표가 낡으면 두 블록이 **함께** 낡을 뿐, 서로 다른 분기를 말하지는 않는다
    -- (한 화면에서 두 숫자가 다른 기간을 말하는 것이 가장 나쁜 상태다).
    select coalesce(
             (select max(m.snapshot_ym) from mv_district_industry_mix m),
             (select max(u.snapshot_ym) from unit_business u)) as ym
  ),
  me as (
    -- 좌표가 없으면 아예 답하지 않는다. 여기를 열어 두면 반경 0곳이 "이 동네엔 가게가
    -- 없다"는 **단정**으로 새어 나간다(list_building_districts 와 같은 원칙).
    select p.geom as g, p.geom::geography as gg
    from parcel p
    where p.pnu = p_pnu::char(19) and p.geom is not null
  ),
  hit as (
    -- 술어를 st_contains 로 맞춘다 — 결정 0008·0011 의 실측이 이 술어로 나온 숫자다.
    select d.district_id, d.district_nm, d.district_type, d.source_nm, d.area_m2
    from district d cross join me
    where st_contains(d.geom, me.g)
  ),
  near as (
    -- ⚠️ char(19)[] 이라야 한다. text[] 로 두면 배열 조건이 인덱스 안으로 못 들어가
    --    힙 필터로 밀린다(list_price_bands L4 주석의 실측과 같은 병).
    -- 마지막 인자 false = 구면으로 잰다. list_price_bands 와 같은 자를 쓴다.
    select coalesce(array_agg(p.pnu), '{}'::char(19)[]) as pnus
    from parcel p cross join me
    where p.geom is not null
      and st_dwithin(p.geom::geography, me.gg, 500, false)
  ),
  dcat as (
    select h.district_id, m.cat_l_cd, m.cat_l_nm, sum(m.n)::int as n
    from hit h
    join mv_district_industry_mix m
      on m.district_id = h.district_id
     and m.snapshot_ym = (select ym from snap)
    group by 1, 2, 3
  ),
  rcat as (
    select ub.cat_l_cd, ub.cat_l_nm, count(*)::int as n
    from unit_business ub cross join near
    where ub.snapshot_ym = (select ym from snap)
      and ub.pnu = any(near.pnus)
    group by 1, 2
  ),
  dj as (
    select h.area_m2, h.district_id,
           jsonb_build_object(
             'district_id', h.district_id,
             'name', h.district_nm,
             'type', h.district_type,
             'source_nm', h.source_nm,
             'total', coalesce((select sum(c.n) from dcat c
                                 where c.district_id = h.district_id), 0)::int,
             'cats', coalesce((select jsonb_agg(
                                        jsonb_build_object('cd', c.cat_l_cd,
                                                           'nm', c.cat_l_nm,
                                                           'n',  c.n)
                                        order by c.n desc, c.cat_l_cd)
                                 from dcat c where c.district_id = h.district_id),
                              '[]'::jsonb)
           ) as j
    from hit h
  )
  select jsonb_build_object(
    'snapshot_ym', (select ym from snap),
    'radius_m', 500,
    -- 좁은 상권이 더 구체적인 설명이라 먼저 온다(list_building_districts 와 같은 정렬).
    'districts', coalesce((select jsonb_agg(dj.j order by dj.area_m2 asc, dj.district_id)
                            from dj), '[]'::jsonb),
    -- 좌표가 없으면 null 이다. **빈 집계가 아니라 "모른다"** 라서 화면이 그 블록을 감춘다.
    'radius', case when exists (select 1 from me) then jsonb_build_object(
        'total', coalesce((select sum(r.n) from rcat r), 0)::int,
        'cats',  coalesce((select jsonb_agg(
                                    jsonb_build_object('cd', r.cat_l_cd,
                                                       'nm', r.cat_l_nm,
                                                       'n',  r.n)
                                    order by r.n desc, r.cat_l_cd)
                            from rcat r), '[]'::jsonb)
      ) else null end
  );
$$;

comment on function list_industry_mix(text) is
  '결정 0014 이 필지 둘레의 업종 분포(대분류). districts = 속한 상권마다 한 묶음(겹치면 전부, '
  '좁은 상권 먼저) · radius = 반경 500m. radius 가 null 이면 필지 좌표가 없어 **모른다**는 뜻이고 '
  '빈 집계와 다르다. snapshot_ym 은 두 블록이 함께 쓰는 분기다(사전계산표가 정본). '
  '⚠️ 상권끼리 더하지 말 것 — 겹치는 자리의 점포는 양쪽에 세어진다(실측 3.9%). '
  'security definer — unit_business·parcel·district 가 anon 에게 닫혀 있어 소유자 권한으로 '
  '대신 읽는다. **나가는 것은 업종별 개수뿐이다 — 상호명은 한 글자도 나가지 않는다.**';

-- ─────────────────────────────────────────────────────────────────────
-- 4) list_industry_detail(p_pnu, p_cat) — 고른 대분류의 중분류 분포
-- ─────────────────────────────────────────────────────────────────────
-- 대분류를 누를 때만 부른다(첫 화면에서 75종을 다 내려보내지 않는다).
-- ⛔ `p_cat::char(2)` 캐스트도 같은 이유다 — cat_l_cd 가 char(2) 다.
create or replace function list_industry_detail(p_pnu text, p_cat text)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  with snap as (
    select coalesce(
             (select max(m.snapshot_ym) from mv_district_industry_mix m),
             (select max(u.snapshot_ym) from unit_business u)) as ym
  ),
  me as (
    select p.geom as g, p.geom::geography as gg
    from parcel p
    where p.pnu = p_pnu::char(19) and p.geom is not null
  ),
  hit as (
    select d.district_id, d.district_nm, d.area_m2
    from district d cross join me
    where st_contains(d.geom, me.g)
  ),
  near as (
    select coalesce(array_agg(p.pnu), '{}'::char(19)[]) as pnus
    from parcel p cross join me
    where p.geom is not null
      and st_dwithin(p.geom::geography, me.gg, 500, false)
  ),
  dsub as (
    select h.district_id, m.cat_m_cd, m.cat_m_nm, sum(m.n)::int as n
    from hit h
    join mv_district_industry_mix m
      on m.district_id = h.district_id
     and m.snapshot_ym = (select ym from snap)
     and m.cat_l_cd = p_cat::char(2)
    group by 1, 2, 3
  ),
  rsub as (
    select ub.cat_m_cd, ub.cat_m_nm, count(*)::int as n
    from unit_business ub cross join near
    where ub.snapshot_ym = (select ym from snap)
      and ub.pnu = any(near.pnus)
      and ub.cat_l_cd = p_cat::char(2)
    group by 1, 2
  ),
  dj as (
    select h.area_m2, h.district_id,
           jsonb_build_object(
             'district_id', h.district_id,
             'name', h.district_nm,
             'total', coalesce((select sum(s.n) from dsub s
                                 where s.district_id = h.district_id), 0)::int,
             'cats', coalesce((select jsonb_agg(
                                        jsonb_build_object('cd', s.cat_m_cd,
                                                           'nm', s.cat_m_nm,
                                                           'n',  s.n)
                                        order by s.n desc, s.cat_m_cd)
                                 from dsub s where s.district_id = h.district_id),
                              '[]'::jsonb)
           ) as j
    from hit h
  )
  select jsonb_build_object(
    'snapshot_ym', (select ym from snap),
    'radius_m', 500,
    -- 물어본 업종을 그대로 돌려준다 — 화면이 늦게 도착한 답(그 사이 다른 업종을 고른
    -- 경우)을 버릴 수 있어야 한다. 이게 없으면 목록이 조용히 뒤바뀐다.
    'cat_l_cd', p_cat,
    'districts', coalesce((select jsonb_agg(dj.j order by dj.area_m2 asc, dj.district_id)
                            from dj), '[]'::jsonb),
    'radius', case when exists (select 1 from me) then jsonb_build_object(
        'total', coalesce((select sum(s.n) from rsub s), 0)::int,
        'cats',  coalesce((select jsonb_agg(
                                    jsonb_build_object('cd', s.cat_m_cd,
                                                       'nm', s.cat_m_nm,
                                                       'n',  s.n)
                                    order by s.n desc, s.cat_m_cd)
                            from rsub s), '[]'::jsonb)
      ) else null end
  );
$$;

comment on function list_industry_detail(text, text) is
  '결정 0014 고른 대분류 안의 중분류 분포. 반환 구조는 list_industry_mix 와 같고 cat_l_cd 를 '
  '그대로 되돌려 준다(늦게 도착한 답을 화면이 버릴 수 있게). '
  'security definer — **나가는 것은 업종별 개수뿐이다(상호명 없음).**';

-- 화면이 부르는 함수만 명시적으로 연다(2026-08-13g 이후 함수는 기본으로 닫혀 있다).
grant execute on function list_industry_mix(text) to anon, authenticated;
grant execute on function list_industry_detail(text, text) to anon, authenticated;

-- ─────────────────────────────────────────────────────────────────────
-- 5) 마지막에 — 옛 인덱스를 지운다
-- ─────────────────────────────────────────────────────────────────────
-- ⛔ **이 문장이 표를 잠근다.** `drop index` 는 unit_business 에 ACCESS EXCLUSIVE 락을
--    걸고, 그 락은 **커밋할 때까지 안 풀린다.** 그래서 파일 앞쪽에 두면 뒤따르는 물질화뷰
--    굽기(약 27초) 내내 unit_business 를 읽는 **모든 조회가 줄을 선다** — 이 표는
--    idx_scan 2,265만 회로 이 DB 에서 가장 많이 읽히는 표다(층별 화면이 매번 읽는다).
--    맨 끝으로 내리면 잠기는 시간이 이 한 문장 길이로 줄어든다.
--
-- ⓘ 지워도 안전한 이유: 새 `idx_ub_pnu_cat` 의 앞 두 칸이 옛것과 **똑같다**(pnu,
--    snapshot_ym). 즉 옛 인덱스로 되던 조회는 전부 새 인덱스로도 된다.
-- ⚠️ 위 create 가 **먼저** 끝나 있어야 한다. 순서를 바꾸면 둘 사이의 짧은 틈 동안
--    pnu 조회를 받쳐 줄 인덱스가 하나도 없어진다.
drop index if exists idx_ub_pnu;

-- 새 인덱스·물질화뷰는 통계가 따로 잡힌다 — 안 돌리면 플래너가 안 고른다.
-- ⚠️ Index Only Scan 은 **가시성 맵**까지 새것이라야 힙을 안 읽는다. analyze 만으로는
--    부족하고 vacuum 이 있어야 한다(2026-08-11 실측) — post_load.py 가 대신 돈다.
analyze unit_business;
analyze mv_district_industry_mix;
