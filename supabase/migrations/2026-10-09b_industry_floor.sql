-- =====================================================================
-- 2026-10-09b — 업종별 층 분포 (물결 2-2 · 결정 0036 결정 18 ⑲~㉑)
-- =====================================================================
--
-- 왜
-- --
-- 층별 화면의 『둘레의 업종 분포』 카드는 대분류를 고르면 중분류와 "같은 업종 N곳"을 보여 준다.
-- 창업자가 그다음에 묻는 것은 "그 가게들이 **몇 층**에 있나"다(1층 카페가 많은 동네인지, 2층 이상
-- 학원이 많은 동네인지). 점포 표에는 층 칸(`unit_business.floor_no`)이 이미 있다 — 다만 절반쯤이
-- 비어 있다(202606 전국 2,772,484행 중 NULL 1,393,405 = 50.3% · 2026-10-09 실측). 그래서 층 미상은
-- 숨기지 않고 **다섯째 묶음**으로 함께 센다(👤 결정 ⑲ — 미상은 값이지 경고가 아니다).
--
-- 무엇이 생기나 (새 객체만 — 기존 객체는 한 글자도 안 바꾼다)
-- ------------------------------------------------------------
--   ① 함수 industry_floor_band(smallint) — 층 묶음 다섯(b · 1 · 2 · 3+ · na · 옥탑 99 는 3+).
--      immutable · strict 아님(NULL → 'na') · 공개키에 닫힘(요약표·함수 안에서만 쓴다).
--   ② 요약표 mv_district_industry_floor — mv_district_industry_mix 정의 그대로 + 층 묶음 칸 하나.
--      분기 = 표지 loaded_ym(결정 0035 — published 가 아니다) · 유일 색인(concurrently 갱신 전제) ·
--      analyze · 공개키에 닫힘. 굽기 약 30초(형제 실측 26.7초).
--   ③ 함수 list_industry_floors(p_pnu, p_cat_l, p_cat_m) — 형제 list_industry_detail 의 snap·me·hit·near
--      를 글자 그대로 쓰고, 상권 안(②) + 반경 500m(점포 표)를 층 묶음으로 센다. 공개키에 닫힘.
--   ④ api 쌍둥이 api.list_industry_floors — security definer · search_path '' · anon·authenticated 에게만 실행.
--      공개 호출 허용 총계 28 → 29(post_load.py ANON_CALLABLE_ALLOWLIST).
--
-- 잠금
-- ----
-- 새 객체만 만든다 — 기존 표·뷰·함수의 정의를 바꾸지 않으므로 화면이 읽는 객체에 거는 잠금이 없다.
-- ② 를 굽는 동안 원본 표(unit_business · district · snapshot_release)에 ACCESS SHARE(읽기)만 잡는다 —
-- 화면 읽기와 적재기 쓰기를 막지 않는다. 그래도 `lock_timeout` 은 형제 관습대로 **begin 앞**(세션
-- 설정)에 둔다 · `statement_timeout = '900s'` — dbx.py 연결 제한이 2분이라 굽기가 잘리지 않게.
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 중간에 끊기면 api 쌍둥이 없이 원본만 남거나(화면 404) 요약표만
-- 남는다 — 한 덩어리로 묶는다. `notify pgrst` 는 commit **뒤**.
--
-- 실행 (머지 뒤 · Claude 가 dbx 로)
-- --------------------------------
--   ⚠️ 순서 = **2026-10-09c(점포 색인 include) 먼저 → 이 파일**(09c 머리말 — 디스크 % · 배치 창 밖).
--   python scripts/dbx.py -f supabase/migrations/2026-10-09b_industry_floor.sql
--   → 이어서 python scripts/post_load.py --check — **09c·09b 둘 다 적용한 뒤 0** 이어야 한다(층 분포 표
--     202606 · 합 대조 어긋남 0 · 허용 목록에 api.list_industry_floors · 정본 색인 mv_district_industry_floor_key
--     있음 · 09c 전에는 정본 색인 점검이 idx_ub_pnu_cat 의 INCLUDE 불일치로 [사고]다)
--
-- 적용 뒤 확인 (dbx + anon 키로 **화면 요청 그대로**)
-- ------------------------------------------------
--   select max(snapshot_ym), count(*) from mv_district_industry_floor;   -- 202606 · 형제보다 몇 배 많은 행
--   select count(*) from (
--     select district_id, cat_m_cd, sum(n) n from mv_district_industry_floor group by 1, 2) f
--   full join (select district_id, cat_m_cd, n from mv_district_industry_mix) m
--     on f.district_id = m.district_id and f.cat_m_cd is not distinct from m.cat_m_cd
--   where f.n is distinct from m.n;                                       -- 0 (빈 중분류 열쇠도 짝을 찾게)
--   select relname, relacl from pg_class where relname = 'mv_district_industry_floor';   -- anon 없음
--   anon 키:
--     POST /rest/v1/rpc/list_industry_floors {"p_pnu":"<강남 필지>","p_cat_l":"I2"}            → 200 · bands 열쇠 다섯
--     POST /rest/v1/rpc/list_industry_floors {"p_pnu":"<같은 필지>","p_cat_l":"I2","p_cat_m":["I212"]} → 200 · cat_m_cds ["I212"]
--     POST /rest/v1/rpc/industry_floor_band {"p_floor":1}                                    → 404/401(밖에 안 열림)
--   눈 확인: 넓은 화면·412px — 업종 분포 카드에서 대분류를 고르면 블록마다 '층별 …' 한 줄.
--
-- 되돌리기
-- --------
-- **새 마이그레이션 파일**로: begin → drop function api.list_industry_floors(text, text, text[]) →
-- drop function list_industry_floors(text, text, text[]) → drop materialized view mv_district_industry_floor →
-- drop function industry_floor_band(smallint) → commit → notify. 그리고 이 PR revert(정본 · post_load 의
-- REFRESH_MVS·QUARTER_MVS·PUBLISH_DO_SQL·점검 둘 · 허용 목록 29 → 28 · 화면 줄). ⚠️ post_load 를 먼저
-- 되돌리지 않고 표만 지우면 다음 post_load 가 없는 표를 refresh 하다 통째 롤백한다 — PR revert 를 먼저 머지한다.
-- 적용된 이 파일은 고치지 않는다(원장). 화면은 함수가 없으면(PGRST202) 층 줄만 조용히 빠지고 카드는 선다.

set statement_timeout = '900s';
set lock_timeout = '5s';

begin;

-- ── 업종별 층 분포 (2026-10-09b · 물결 2-2 · 결정 0036 결정 18 ⑲~㉑) ──────────────────
-- 업종 분포 카드에서 대분류를 고르면 그 대분류(창업자 칩이면 짝 중분류까지) 가게가 몇 층에
-- 있는지를 한 줄로 보탠다. 범위는 형제 둘과 같다 — 속한 상권 안(미리 굽는다) + 반경 500m(그때그때).
-- 층 묶음은 다섯으로 고정한다: 지하(b) · 1층(1) · 2층(2) · 3층 이상(3+ — 옥탑 99 포함) · 층 미상(na).
-- ⛔ 층 미상(NULL)을 빼지 않는다 — 점포 표의 절반쯤(202606 전국 50.3%)이 층이 비어 있어서,
--    빼면 남은 넷이 그 범위의 전부처럼 읽힌다. 미상은 경고가 아니라 **값**이다.
-- ⛔ `strict` 를 붙이지 말 것 — strict 면 NULL 입력에 함수가 아예 안 불리고 NULL 을 돌려줘,
--    층 미상이 'na' 묶음이 아니라 이름 없는 묶음이 된다(화면 열쇠 다섯이 깨진다).
create or replace function industry_floor_band(p_floor smallint)
returns text
language sql
immutable
as $$
  select case
           when p_floor is null then 'na'
           when p_floor < 0     then 'b'
           when p_floor = 1     then '1'
           when p_floor = 2     then '2'
           else '3+'
         end;
$$;

comment on function industry_floor_band(smallint) is
  '물결 2-2 업종별 층 분포의 층 묶음 다섯(2026-10-09b) — NULL = ''na''(층 미상) · 음수 = ''b''(지하) · '
  '1 = ''1'' · 2 = ''2'' · 그 밖 = ''3+''(3층 이상 — 옥탑 99 는 ''3+''). 요약표 mv_district_industry_floor 와 '
  'list_industry_floors 가 같은 이 함수로 묶는다(두 범위가 다른 자로 묶이지 않게). strict 가 아니다 — NULL 도 묶음이다.';

-- 공개키가 직접 부를 일이 없다 — 요약표·함수 안에서만 쓴다(🚪 닫힌 채 태어나도 한 번 더 닫는다).
revoke all on function industry_floor_band(smallint) from public, anon, authenticated;

-- 형제 mv_district_industry_mix 의 정의를 그대로 두고 층 묶음 칸 하나만 더했다. 분기도 같은 자 —
-- 표지 loaded_ym(결정 0035 · published 가 아니다)으로 굽고, post_load.py 가 업종 표와 한 트랜잭션에서
-- 굽는다. 같은 (상권·분기·중분류)의 n 을 층 묶음끼리 더하면 형제 표의 n 과 같아야 한다 —
-- post_load.py --check 가 그 합을 대조한다(어긋나면 [낡음]).
create materialized view if not exists mv_district_industry_floor as
select d.district_id,
       ub.snapshot_ym,
       ub.cat_l_cd, ub.cat_l_nm,
       ub.cat_m_cd, ub.cat_m_nm,
       public.industry_floor_band(ub.floor_no) as floor_band,
       count(*)::int as n
from district d
join unit_business ub
  on ub.geom is not null
 and st_contains(d.geom, ub.geom)
where ub.snapshot_ym = (select r.loaded_ym from snapshot_release r)   -- 표지 loaded_ym(결정 0035)
group by 1, 2, 3, 4, 5, 6, 7;

comment on materialized view mv_district_industry_floor is
  '상권 × 업종(중분류) × 층 묶음 점포 수 — 최신 분기 한 개만(2026-10-09b · 물결 2-2). '
  'mv_district_industry_mix 의 층 묶음 판 — 같은 (상권·중분류) 의 n 합이 형제와 같아야 한다(post_load --check 가 대조). '
  '층 묶음은 industry_floor_band() 다섯(b · 1 · 2 · 3+ · na — 옥탑 99 는 3+, 층 미상은 na 로 그대로 센다). '
  '⚠️ 상권이 겹치는 자리의 점포는 **양쪽에 모두** 세어진다(형제와 같다 — 상권끼리 더하지 말 것). '
  '⚠️ 어느 분기인지는 **구울 때** 굳는다 — 표지 loaded_ym(다 들어온 분기 · 결정 0035)으로 굽고, post_load.py 가 구운 뒤 화면 기준(published_ym)을 올린다. '
  '⛔ anon 에게 열지 않는다 — 화면은 list_industry_floors 함수로만 읽는다.';

-- `concurrently` 갱신의 전제 조건(형제와 같은 꼴 + 층 묶음).
create unique index if not exists mv_district_industry_floor_key
  on mv_district_industry_floor (district_id, snapshot_ym, cat_m_cd, floor_band);

analyze mv_district_industry_floor;

-- ⛔ 새 물질화뷰는 anon 에게 자동으로 열린다(pg_default_acl) — 만든 자리에서 닫는다(아래 목록에도 한 번 더).
revoke all on mv_district_industry_floor from public, anon, authenticated;

-- 대분류를 고른 뒤에만 부른다(첫 화면 미리 부르기에 넣지 않는다). 칸 둘은 형제 list_industry_detail 과
-- 같은 자를 쓴다 — snap(1순위 요약표 · 2순위 published) · me · hit · near 가 글자 그대로 같다.
-- p_cat_m 이 null 이면 그 대분류 전체, 배열이면 그 중분류들만(창업자 칩의 짝 — 학원은 코드 둘).
-- ⛔ `p_cat_l::char(2)` · `p_cat_m::char(4)[]` 캐스트를 지우지 말 것 — 칸이 char 라 text 로 견주면
--    컬럼 쪽이 캐스트돼 색인이 죽는다(2026-08-16b 와 같은 병).
-- ⛔ bands 열쇠 다섯은 **늘 다 있다**(없는 묶음은 0) — 화면 검증기가 열쇠 하나라도 빠지면 그 응답을 버린다.
create or replace function list_industry_floors(p_pnu text, p_cat_l text, p_cat_m text[] default null)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  with snap as (
    select coalesce(
             (select max(m.snapshot_ym) from mv_district_industry_floor m),
             (select r.published_ym from snapshot_release r)) as ym
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
  band as (
    -- 열쇠 다섯 — 순서는 화면이 정한다(FLOOR_BAND_ORDER). 여기서는 빠짐없이 있게만 한다.
    select v.k from (values ('b'), ('1'), ('2'), ('3+'), ('na')) as v(k)
  ),
  dsub as (
    select h.district_id, m.floor_band, sum(m.n)::int as n
    from hit h
    join mv_district_industry_floor m
      on m.district_id = h.district_id
     and m.snapshot_ym = (select ym from snap)
     and m.cat_l_cd = p_cat_l::char(2)
     and (p_cat_m is null or m.cat_m_cd = any(p_cat_m::char(4)[]))
    group by 1, 2
  ),
  rsub as (
    select public.industry_floor_band(ub.floor_no) as floor_band, count(*)::int as n
    from unit_business ub cross join near
    where ub.snapshot_ym = (select ym from snap)
      and ub.pnu = any(near.pnus)
      and ub.cat_l_cd = p_cat_l::char(2)
      and (p_cat_m is null or ub.cat_m_cd = any(p_cat_m::char(4)[]))
    group by 1
  ),
  dj as (
    select h.area_m2, h.district_id,
           jsonb_build_object(
             'district_id', h.district_id,
             'name', h.district_nm,
             'total', coalesce((select sum(s.n) from dsub s
                                 where s.district_id = h.district_id), 0)::int,
             'bands', (select jsonb_object_agg(b.k, coalesce(s.n, 0))
                       from band b
                       left join dsub s
                         on s.district_id = h.district_id and s.floor_band = b.k)
           ) as j
    from hit h
  )
  select jsonb_build_object(
    'snapshot_ym', (select ym from snap),
    'radius_m', 500,
    -- 물어본 업종을 그대로 돌려준다 — 화면이 늦게 도착한 답(그 사이 다른 업종·칩을 고른 경우)을 버린다.
    'cat_l_cd', p_cat_l,
    'cat_m_cds', p_cat_m,
    'districts', coalesce((select jsonb_agg(dj.j order by dj.area_m2 asc, dj.district_id)
                            from dj), '[]'::jsonb),
    -- 좌표가 없으면 null — **빈 집계가 아니라 "모른다"** 라서 화면이 그 줄을 안 그린다.
    'radius', case when exists (select 1 from me) then jsonb_build_object(
        'total', coalesce((select sum(s.n) from rsub s), 0)::int,
        'bands', (select jsonb_object_agg(b.k, coalesce(s.n, 0))
                  from band b
                  left join rsub s on s.floor_band = b.k)
      ) else null end
  );
$$;

comment on function list_industry_floors(text, text, text[]) is
  '물결 2-2(2026-10-09b) 고른 대분류(p_cat_m 이 있으면 그 중분류들만)의 층 묶음 분포. districts = 속한 상권마다 '
  '(좁은 상권 먼저) · radius = 반경 500m(좌표가 없으면 null — 모른다). bands 는 열쇠 다섯(b · 1 · 2 · 3+ · na)이 '
  '늘 다 있다(없으면 0). cat_l_cd·cat_m_cds 를 그대로 되돌려 준다(늦게 도착한 답을 화면이 버릴 수 있게). '
  '분기는 형제 list_industry_detail 과 같은 자(1순위 요약표 · 2순위 published). '
  'security definer — **나가는 것은 개수뿐이다(상호명 없음).**';

revoke all on function list_industry_floors(text, text, text[]) from public, anon, authenticated;

-- ── api 쌍둥이 — 화면이 부르는 문(🚪 grant 는 여기에만) ─────────────────────────────
create or replace function api.list_industry_floors(p_pnu text, p_cat_l text, p_cat_m text[] default null)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$ select public.list_industry_floors(p_pnu, p_cat_l, p_cat_m) $$;

-- Postgres 는 새 함수의 EXECUTE 를 PUBLIC 에게 기본으로 준다 — 먼저 회수하고 필요한 롤에만 준다.
revoke all on function api.list_industry_floors(text, text, text[]) from public, anon, authenticated;
grant execute on function api.list_industry_floors(text, text, text[]) to anon, authenticated;

commit;

notify pgrst, 'reload schema';
