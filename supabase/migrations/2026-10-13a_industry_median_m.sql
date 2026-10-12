-- =====================================================================
-- 2026-10-13a — 업종 비중 비교 · 중분류 (물결 2-3b · 결정 0036 결정 18 ㉗~㉚)
-- =====================================================================
--
-- 왜
-- --
-- 업종 분포 카드에서 대분류(음식 등)를 고르면 상권 블록에 그 대분류 안의 중분류 막대(카페 21.7% 등)가 선다.
-- 2026-10-12a 가 대분류 막대에 견줄 숫자(같은 종류 상권 가운데값)를 붙였는데, 중분류 막대에는 아직 없다.
-- 그래서 중분류 막대 줄 아래에도 같은 틀로 가운데값을 숫자로만 나란히 적는다(👤 결정 ㉗ 지금 만든다 · ㉚ 어제 틀 그대로).
-- 몫은 **고른 대분류 안의 몫**이다(👤 ㉘ — 음식 가게 중 카페 몇 % · 바로 위 막대와 같은 기준).
-- 모집단은 **그 대분류 가게가 30곳 이상인 상권**만이다(👤 ㉙ — 상권 전체 점포 30곳이 아니다).
--
-- 무엇이 생기나 (새 객체만 — 기존 객체는 한 글자도 안 바꾼다)
-- ------------------------------------------------------------
--   ① 요약표 mv_industry_mix_median_m — 재료는 mv_district_industry_mix(이미 표지 loaded 분기 하나) × district.
--      (시·도, 범위 type|all, 상권 종류, 대분류, 중분류)마다 모집단 상권 수(pop_n)와 대분류 안 비중 가운데값(med_pct).
--      ⛔ 모집단은 그 대분류 가게가 30곳 이상인 상권만(서울 골목상권 음식 526곳 · 2026-10-13 실측).
--      ⛔ 그 중분류가 없는 상권은 0 으로 넣고 센다(그 분기 그 대분류의 중분류 전부 cross join — 2-3 과 같은 규칙).
--      유일 색인(concurrently 갱신 전제) · analyze · 공개키에 닫힘. 행 수백~1천 · 굽기 1초 안팎.
--   ② 함수 list_industry_median_m(p_pnu, p_cat_l) — 형제 list_industry_median 의 snap·me·hit 를 글자 그대로 쓰고,
--      속한 상권마다 그 상권의 그 대분류 가게 수 · 고른 모집단 · 중분류별 가운데값을 낸다. 공개키에 닫힘.
--   ③ api 쌍둥이 api.list_industry_median_m — security definer · search_path '' · anon·authenticated 에게만 실행.
--      공개 호출 허용 총계 31 → 32(post_load.py ANON_CALLABLE_ALLOWLIST).
--   기존 list_industry_detail·list_industry_mix·list_industry_median 의 응답은 **안 바뀐다** — 옛 서버·실패·함수 없음
--   (PGRST202)이면 화면은 중분류 비교 글만 빠진다.
--
-- 잠금
-- ----
-- 새 객체만 만든다 — 기존 표·뷰·함수의 정의를 바꾸지 않으므로 화면이 읽는 객체에 거는 잠금이 없다.
-- ① 을 굽는 동안 원본(mv_district_industry_mix · district)에 ACCESS SHARE(읽기)만 잡는다 — 화면 읽기와
-- post_load 갱신(refresh concurrently = EXCLUSIVE)을 막지 않는다 — EXCLUSIVE 는 ACCESS SHARE 와 충돌하지 않아
-- 겹쳐도 서로 기다리지 않는다(PostgreSQL 공식 문서 explicit-locking 의 잠금 충돌 표).
-- 그래도 `lock_timeout` 은 형제 관습대로 **begin 앞**(세션 설정)에 둔다 · `statement_timeout = '900s'`.
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 중간에 끊기면 api 쌍둥이 없이 원본만 남거나(화면 404) 요약표만
-- 남는다 — 한 덩어리로 묶는다. `notify pgrst` 는 commit **뒤**.
--
-- 실행 (Claude 가 dbx 로 · 디스크 영향 ≈ 0)
-- ---------------------------------------
--   python scripts/dbx.py -f supabase/migrations/2026-10-13a_industry_median_m.sql
--   → 이어서 python scripts/post_load.py --check — 0 이어야 한다(중분류 가운데값 표 202606 · 모집단 수 대조 어긋남 0 ·
--     값 다시 세기 어긋남 0 · 허용 목록에 api.list_industry_median_m · 정본 색인 mv_industry_mix_median_m_key 있음 ·
--     허용된 32개)
--   ⚠️ post_load.py 를 이 마이그레이션 **전에** 새 판(REFRESH_MVS 에 이 표가 든 판)으로 돌리면 없는 표를
--      refresh 하다 통째 롤백한다 — 적용 → 머지 순서를 지킨다(되돌릴 때는 거꾸로).
--
-- 적용 뒤 확인 (dbx + anon 키로 **화면 요청 그대로**)
-- ------------------------------------------------
--   select max(snapshot_ym), count(*) from mv_industry_mix_median_m;        -- 202606 · 수백~1천 행
--   select pop_n, med_pct from mv_industry_mix_median_m
--    where sido_cd = '11' and scope = 'type' and district_type = '골목상권' and cat_l_cd = 'I2' and cat_m_cd = 'I212';
--     -- 526 · 15.2 (한식 I201 38.1 · 기타 간이 I210 20.6 · 동남아시아 0.0)
--   select relname, relacl from pg_class where relname = 'mv_industry_mix_median_m';   -- anon 없음
--   anon 키:
--     POST /rest/v1/rpc/list_industry_median_m {"p_pnu":"<강남 골목상권 안 필지>","p_cat_l":"I2"}  → 200 · min_total 30 · pop.n 526
--     POST /rest/v1/rpc/list_industry_median_m {"p_pnu":"<명동 관광특구 안 필지>","p_cat_l":"I2"}  → 200 · pop.scope "all"
--   눈 확인: 넓은 화면·412px·종이 — 업종 분포 카드에서 음식을 고른 뒤 상권 블록 중분류 줄마다 '서울 골목상권 가운데 15.2%'.
--
-- 되돌리기
-- --------
-- **먼저 이 PR 을 revert 해 머지한다**(정본 · post_load 의 REFRESH_MVS·QUARTER_MVS·PUBLISH_DO_SQL·점검 둘 ·
-- 허용 목록 32 → 31 · 화면 줄) — post_load 를 먼저 되돌리지 않고 표만 지우면 다음 post_load 가 없는 표를
-- refresh 하다 통째 롤백한다. 그다음 **새 마이그레이션 파일**로: begin → drop function api.list_industry_median_m(text, text)
-- → drop function list_industry_median_m(text, text) → drop materialized view mv_industry_mix_median_m → commit → notify.
-- 적용된 이 파일은 고치지 않는다(원장). 화면은 함수가 없으면(PGRST202) 중분류 비교 글만 조용히 빠지고 카드는 선다.

set statement_timeout = '900s';
set lock_timeout = '5s';

begin;

-- ── 업종 비중 비교 · 중분류 (2026-10-13a · 물결 2-3b · 결정 0036 결정 18 ㉗~㉚) ─────────────
-- 고른 대분류 안의 중분류 비중에 견줄 숫자 — 같은 시·도 같은 종류 상권들의 가운데값(반경 블록은 비교 안 함).
-- 재료는 형제 요약표 mv_district_industry_mix 라 분기는 그 표의 분기(표지 loaded_ym) 그대로다 —
-- post_load.py 가 그 표를 구운 **뒤** 같은 트랜잭션에서 이 표를 굽는다(QUARTER_MVS 여섯째).
-- ⛔ 몫 = 그 상권의 중분류 n ÷ 그 상권의 **그 대분류** n(👤 ㉘ — 화면의 중분류 막대와 같은 분모). 상권 전체 점포가 아니다.
-- ⛔ 모집단에서 그 대분류 가게가 30곳 미만인 상권을 뺀다(having sum(n) >= 30 — (상권, 분기, 대분류)마다 · 👤 ㉙).
--    몇 곳뿐인 상권의 몫(1곳이면 100%)이 가운데값을 흔든다. 화면도 그 대분류 30곳 미만 상권엔 비교값을 안 적는다.
-- ⛔ 그 중분류가 없는 상권은 몫 0 으로 넣는다 — (상권, 대분류) × 그 분기 그 대분류의 중분류를 cross join 하고 coalesce(n, 0).
--    빼고 세면 드문 중분류의 가운데값이 부푼다(2-3 과 같은 병).
-- ⛔ 지역 이름을 여기 박지 않는다 — sido_cd(sigungu_code 앞 2자리)만 두고 화면이 '서울'·'대전'을 붙인다.
-- ⓘ 범위 'type' = 같은 종류끼리 · 'all' = 그 시·도 상권 전체(종류가 30곳 미만일 때 함수가 이쪽을 고른다).
-- ⓘ district_type 은 null 대신 '' 를 둔다('all' 줄도 '') — null 이 든 유일 색인은 중복을 못 막는다.
-- ⓘ 대분류·중분류 코드의 빈 값은 운영 0(2026-10-13 실측 0/62,457) — 이음은 형제와 같은 = 라 빈 대분류는 모집단에서 떨어진다.
-- ⛔ 빈 중분류는 중분류 목록(cat)에서 뺀다(cat_m_cd is not null) — 안 빼면 cd 가 null 인 몫 0.0 줄이 생기고 함수 cats 에
--    cd null 이 실린다. 분모(cat_total)에는 그대로 든다 — 빈 중분류 가게도 그 대분류 가게라 화면 막대 분모와 같게.
--    post_load --check 의 다시 세기가 같은 규칙으로 센다.
create materialized view if not exists mv_industry_mix_median_m as
with tot as (
  -- (상권, 분기, 대분류)마다 그 대분류 가게 수 — 그 대분류 가게 30곳 이상 상권만 모집단에 든다
  select m.district_id, m.snapshot_ym, m.cat_l_cd, sum(m.n)::int as cat_total
  from mv_district_industry_mix m
  group by 1, 2, 3
  having sum(m.n) >= 30
),
pop as (
  select t.district_id, t.snapshot_ym, t.cat_l_cd, t.cat_total,
         left(d.sigungu_code, 2) as sido_cd,
         coalesce(d.district_type, '') as district_type
  from tot t
  join district d on d.district_id = t.district_id
),
cat as (
  -- 그 분기 그 대분류에 있는 중분류 전부(이름은 코드마다 하나 — min 으로 고른다)
  select m.snapshot_ym, m.cat_l_cd, m.cat_m_cd, min(m.cat_m_nm) as cat_m_nm
  from mv_district_industry_mix m
  where m.cat_m_cd is not null
  group by 1, 2, 3
),
dcat as (
  select m.district_id, m.snapshot_ym, m.cat_l_cd, m.cat_m_cd, sum(m.n)::int as n
  from mv_district_industry_mix m
  group by 1, 2, 3, 4
),
share as (
  -- 모집단 (상권, 대분류) × 그 대분류의 중분류(cross join) — 없는 중분류는 0 · 분모는 그 상권의 그 대분류 가게 수
  select p.snapshot_ym, p.sido_cd, p.district_type, p.district_id, p.cat_l_cd, c.cat_m_cd, c.cat_m_nm,
         coalesce(dc.n, 0)::float8 / p.cat_total as share
  from pop p
  cross join cat c
  left join dcat dc
    on dc.district_id = p.district_id and dc.snapshot_ym = p.snapshot_ym
   and dc.cat_l_cd = c.cat_l_cd and dc.cat_m_cd = c.cat_m_cd
  where c.snapshot_ym = p.snapshot_ym and c.cat_l_cd = p.cat_l_cd
)
select s.snapshot_ym, s.sido_cd, 'type'::text as scope, s.district_type, s.cat_l_cd,
       count(distinct s.district_id)::int as pop_n,
       s.cat_m_cd, min(s.cat_m_nm) as cat_m_nm,
       round((percentile_cont(0.5) within group (order by s.share) * 100)::numeric, 1)::numeric(5,1) as med_pct
from share s
group by s.snapshot_ym, s.sido_cd, s.district_type, s.cat_l_cd, s.cat_m_cd
union all
select s.snapshot_ym, s.sido_cd, 'all'::text, ''::text, s.cat_l_cd,
       count(distinct s.district_id)::int,
       s.cat_m_cd, min(s.cat_m_nm),
       round((percentile_cont(0.5) within group (order by s.share) * 100)::numeric, 1)::numeric(5,1)
from share s
group by s.snapshot_ym, s.sido_cd, s.cat_l_cd, s.cat_m_cd;

comment on materialized view mv_industry_mix_median_m is
  '상권 업종 비중(고른 대분류 안의 중분류 몫)의 가운데값 — 같은 시·도 같은 종류 상권끼리(scope type) + 그 시·도 상권 전체(scope all) · '
  '분기 하나(2026-10-13a · 물결 2-3b). 재료는 mv_district_industry_mix 라 분기는 그 표의 분기(표지 loaded_ym)다 — '
  'post_load.py 가 그 표 뒤에 같은 트랜잭션에서 굽는다. '
  '몫 = 그 상권의 중분류 가게 수 ÷ 그 상권의 그 대분류 가게 수(화면의 중분류 막대와 같은 분모 — 상권 전체 점포가 아니다). '
  '⛔ 모집단은 그 대분류 가게가 30곳 이상인 상권만(몇 곳뿐인 상권의 몫이 가운데값을 흔든다 · 화면도 그 대분류 30곳 미만 상권엔 비교값을 안 적는다). '
  '⛔ 그 중분류가 없는 상권은 몫 0 으로 넣고 센다(그 분기 그 대분류의 중분류 전부 — 빼면 드문 중분류의 가운데값이 부푼다). '
  'pop_n = 그 묶음·그 대분류의 모집단 상권 수(post_load --check 가 all 줄을 그 대분류 30곳 이상 상권 수와 대조하고 값을 다시 센다). '
  'district_type 은 null 대신 빈 글자(all 줄도 빈 글자) — null 이 든 유일 색인은 중복을 못 막는다. '
  '대분류·중분류 코드의 빈 값은 운영 0(2026-10-13 실측) · 빈 중분류는 중분류 줄로 내지 않는다(분모인 그 대분류 가게 수에는 든다). '
  '지역 이름은 없다(sido_cd 만 — 화면이 붙인다). '
  '⛔ anon 에게 열지 않는다 — 화면은 list_industry_median_m 함수로만 읽는다.';

-- `concurrently` 갱신의 전제 조건 — district_type 이 null 이 아니라('') 평범한 유일 색인으로 된다.
create unique index if not exists mv_industry_mix_median_m_key
  on mv_industry_mix_median_m (snapshot_ym, sido_cd, scope, district_type, cat_l_cd, cat_m_cd);

analyze mv_industry_mix_median_m;

-- ⛔ 새 물질화뷰는 anon 에게 자동으로 열린다(pg_default_acl) — 만든 자리에서 닫는다(아래 목록에도 한 번 더).
revoke all on mv_industry_mix_median_m from public, anon, authenticated;

-- 고른 대분류 안 중분류 몫의 가운데값(비교값)을 속한 상권마다 낸다. 화면은 대분류를 고른 뒤의 상세 블록 중
-- **상권 블록**에만 쓴다(반경 블록은 비교 상대가 없어 이 함수가 아예 안 낸다). snap·me·hit 는 형제
-- list_industry_median 과 글자 그대로 같다 — 같은 분기·같은 상권을 말하게(시험이 대조한다).
-- ⛔ total = 이 상권의 **그 대분류** 가게 수(형제 list_industry_detail 의 상권 total 과 같은 셈) — 0 이면 그 상권 줄이
--    없다(화면 상세 블록이 이미 '이 안에 … 가게가 없습니다'). min_total(30) 미만이면 pop 은 null · cats 는 [].
-- ⛔ 모집단 고르기: 같은 sido_cd·같은 종류 묶음의 그 대분류 pop_n 이 min_pop(30) 이상이면 그 묶음(type), 아니면 같은
--    sido_cd 상권 전체(all) — 이름이 아니라 **수**로 가른다. all 도 30 미만이거나 요약표에 그 묶음이 없으면
--    그 상권 줄을 아예 안 낸다 — '30곳이 안 돼' 라고 잘못 말하지 않게.
-- ⛔ `p_cat_l::char(2)` 캐스트를 지우지 말 것 — 칸이 char(2) 라 text 로 견주면 컬럼 쪽이 캐스트돼 색인이 죽는다.
-- ⛔ 지역 이름을 내지 않는다(sido_cd 만) · 판단 낱말을 내지 않는다(숫자만).
create or replace function list_industry_median_m(p_pnu text, p_cat_l text)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  with lim as (
    select 30 as min_total, 30 as min_pop
  ),
  snap as (
    select coalesce(
             (select max(m.snapshot_ym) from mv_district_industry_mix m),
             (select r.published_ym from snapshot_release r)) as ym
  ),
  me as (
    select p.geom as g, p.geom::geography as gg
    from parcel p
    where p.pnu = p_pnu::char(19) and p.geom is not null
  ),
  hit as (
    select d.district_id, d.district_nm, d.district_type, d.source_nm, d.area_m2
    from district d cross join me
    where st_contains(d.geom, me.g)
  ),
  hd as (
    -- 상권마다 시·도 코드 + 그 분기 그 대분류 가게 수(형제 list_industry_detail 의 상권 total 과 같은 셈)
    select h.district_id, h.area_m2, h.district_type,
           left(d.sigungu_code, 2) as sido_cd,
           coalesce((select sum(m.n) from mv_district_industry_mix m
                      where m.district_id = h.district_id
                        and m.snapshot_ym = (select ym from snap)
                        and m.cat_l_cd = p_cat_l::char(2)), 0)::int as total
    from hit h
    join district d on d.district_id = h.district_id
  ),
  pick as (
    -- 모집단 하나 — 같은 종류(type)의 그 대분류 모집단이 min_pop 이상이면 그것, 아니면 시·도 전체(all)
    select hd.district_id, g.scope, g.district_type, g.pop_n
    from hd
    cross join lateral (
      select t.scope, t.district_type, t.pop_n
      from mv_industry_mix_median_m t
      where t.snapshot_ym = (select ym from snap)
        and t.sido_cd = hd.sido_cd
        and t.cat_l_cd = p_cat_l::char(2)
        and t.pop_n >= (select min_pop from lim)
        and ((t.scope = 'type' and t.district_type = coalesce(hd.district_type, ''))
             or t.scope = 'all')
      order by (t.scope = 'type') desc
      limit 1
    ) g
    where hd.total >= (select min_total from lim)
  ),
  dj as (
    select hd.area_m2, hd.district_id,
           jsonb_build_object(
             'district_id', hd.district_id,
             'type', hd.district_type,
             'total', hd.total,
             'pop', case when p.district_id is null then null else jsonb_build_object(
                      'scope', p.scope,
                      'sido_cd', hd.sido_cd,
                      'district_type', nullif(p.district_type, ''),
                      'n', p.pop_n) end,
             'cats', coalesce((select jsonb_agg(
                                        jsonb_build_object('cd', t.cat_m_cd,
                                                           'nm', t.cat_m_nm,
                                                           'med_pct', t.med_pct)
                                        order by t.med_pct desc, t.cat_m_cd)
                                 from mv_industry_mix_median_m t
                                 where p.district_id is not null
                                   and t.snapshot_ym = (select ym from snap)
                                   and t.sido_cd = hd.sido_cd
                                   and t.scope = p.scope
                                   and t.district_type = p.district_type
                                   and t.cat_l_cd = p_cat_l::char(2)),
                              '[]'::jsonb)
           ) as j
    from hd
    left join pick p on p.district_id = hd.district_id
    where (hd.total > 0 and hd.total < (select min_total from lim)) or p.district_id is not null
  )
  select jsonb_build_object(
    'snapshot_ym', (select ym from snap),
    -- 물어본 대분류를 그대로 돌려준다 — 화면이 늦게 도착한 답(그 사이 다른 대분류를 고른 경우)을 버린다.
    'cat_l_cd', p_cat_l,
    'min_total', (select min_total from lim),
    'min_pop', (select min_pop from lim),
    -- 좁은 상권 먼저(형제 list_industry_median 과 같은 정렬). 좌표가 없으면 [] — 반경 비교는 없다(radius 칸 없음).
    'districts', coalesce((select jsonb_agg(dj.j order by dj.area_m2 asc, dj.district_id)
                            from dj), '[]'::jsonb)
  );
$$;

comment on function list_industry_median_m(text, text) is
  '물결 2-3b(2026-10-13a) 속한 상권마다 고른 대분류 안 중분류 몫의 가운데값 — 비교값. districts = 상권마다 total(그 상권의 '
  '그 대분류 가게 수) · pop · cats(좁은 상권 먼저 · 좌표가 없으면 [] · 그 대분류 가게가 0 인 상권은 줄 없음). pop = 고른 모집단'
  '(scope type = 같은 시·도 같은 종류 · all = 그 시·도 상권 전체 — 종류 묶음이 min_pop 미만일 때) · total 이 min_total 미만이면 '
  'pop null · cats []. 둘 다 30(그 대분류 가게 30곳 이상 상권만 모집단에 든다). cat_l_cd 를 그대로 되돌려 준다(늦게 도착한 답을 '
  '화면이 버릴 수 있게). 분기는 형제 list_industry_median 과 같은 자(1순위 업종 요약표 · 2순위 published). 지역 이름은 없다'
  '(sido_cd 만). security definer — **나가는 것은 백분율 가운데값과 개수뿐이다(상호명 없음).**';

revoke all on function list_industry_median_m(text, text) from public, anon, authenticated;

-- ── api 쌍둥이 — 화면이 부르는 문(🚪 grant 는 여기에만) ─────────────────────────────
create or replace function api.list_industry_median_m(p_pnu text, p_cat_l text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$ select public.list_industry_median_m(p_pnu, p_cat_l) $$;

-- Postgres 는 새 함수의 EXECUTE 를 PUBLIC 에게 기본으로 준다 — 먼저 회수하고 필요한 롤에만 준다.
revoke all on function api.list_industry_median_m(text, text) from public, anon, authenticated;
grant execute on function api.list_industry_median_m(text, text) to anon, authenticated;

commit;

notify pgrst, 'reload schema';
