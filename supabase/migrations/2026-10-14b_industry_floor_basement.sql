-- =====================================================================
-- 2026-10-14b — 숫자 없는 지하('지')를 업종별 층 줄의 지하 칸에 (물결 2-2c PR② · 결정 0036)
-- =====================================================================
--
-- 왜
-- --
-- 원본 층정보가 숫자 없이 '지'라고만 적힌 가게(202606 서울 8,750 · 대전 27)는 층 정규화가 몇 층인지 몰라
-- floor_no 를 NULL 로 둔다(절대 규칙 4 — 층 번호를 지어내지 않는다). 그래서 업종별 층 줄(물결 2-2)은 이 가게들을
-- '층 미상'에 셌고, 지하 칸은 하한이었다(알려진한계 §3).
-- 👤 2026-10-13 「지하 칸에 넣기」: 층 번호는 그대로 비워 두고, 2026-10-14a 가 더한 '지하인데 층 모름' 칸
-- (unit_business.floor_basement_unknown)이 true 인 가게를 지하 묶음 'b' 로 센다.
-- 👤 D1 — **새 분기부터만**: 칸은 14a 뒤에 적재한 분기만 true/false 이고 옛 분기(202603·202606)는 NULL 이라
-- 옛 분기는 지금처럼 층 미상에 남는다. 화면 문구는 응답의 basement_unknown_counted 로 두 벌을 가른다(D2').
--
-- 무엇을 바꾸나
-- -------------
--   ① 함수 industry_floor_band(p_floor smallint, p_basement_unknown boolean) — 새 두 인자 판.
--      floor NULL 이고 칸이 true 면 'b', 그 밖은 옛 한 인자 판과 같다(칸 NULL 은 false 로 본다).
--      immutable · strict 아님 · 공개키에 닫힘.
--   ② 요약표 mv_district_industry_floor — 새 함수로 다시 굽는다(_next → 유일 색인 _key_next → 옛 표 drop →
--      표·색인 이름을 정본 이름으로 → 회수 → comment → analyze · 2026-10-07a 와 같은 바꿔 끼우기).
--   ③ 함수 list_industry_floors — 반경 집계(rsub)가 두 인자 판을 쓰고, 응답에 basement_unknown_counted
--      (= 그 분기 점포 행 하나의 칸이 NULL 이 아닌가 — 기본키 차례로 한 행만 본다)를 더한다.
--      머리(stable · security definer · search_path)와 comment 는 정본에서 잘라 붙였다(시험이 글자 대조).
--      api 쌍둥이(api.list_industry_floors)는 응답 jsonb 를 그대로 넘기므로 안 고친다(서명·권한 그대로).
--   ④ 옛 한 인자 판 industry_floor_band(smallint) drop — 같은 이름이 둘 남으면 post_load --check 의 함수
--      대조가 [사고](오버로드)다. 쓰던 곳(옛 요약표·옛 list 함수)을 ②③ 이 먼저 바꾼다.
--
-- 바꾸지 않는 것
-- --------------
--   · 공개 호출 허용 목록 — 새 공개 함수 0(두 인자 판도 닫힘 · api 쌍둥이 서명 그대로).
--   · 층별 화면 각주(mv_coverage_stats · 👤 D3 — '지'는 계속 결측) · 층별 점포(v_floor_stack) · 점포 표 행.
--   · post_load.py — 요약표 이름·유일 색인 이름이 같고, 합 대조(같은 상권·중분류의 층 묶음 합 = 업종 표 n)는
--     'na' 에서 'b' 로 옮길 뿐이라 그대로 성립한다.
--
-- 잠금 (PostgreSQL 17 공식 문서)
-- -----------------------------
--   · _next 를 굽는 동안(약 30초 — 09b 실측 형제 26.7초) 원본 표에 ACCESS SHARE(읽기)만 잡는다 — 화면이 안 막힌다.
--   · `drop materialized view` 는 옛 요약표에 ACCESS EXCLUSIVE — **commit 까지** 그 표를 읽는 list_industry_floors
--     가 잠깐 기다린다(오류가 아니다). 그래서 굽기를 drop **앞**에 두어 기다림을 이름 바꾸기·회수·analyze
--     (12만 행 · 1초 안쪽)로 줄였다.
--   · `drop function` · `create or replace function` 은 함수 메타데이터만.
--   · `lock_timeout` 은 **begin 앞**(세션 설정) — 오래 도는 조회가 옛 요약표를 쥐고 있어 5초 넘게 못 잡으면
--     덩어리가 통째로 되돌아간다(아무것도 안 바뀐다 → 다시 돌리면 된다).
--   · `statement_timeout = '900s'` — dbx.py 연결 제한이 2분이라 굽기가 잘리지 않게.
--
-- ⛔ 언제 돌리나 (맨 앞 관문 DO 가 셋을 확인한다)
-- ---------------------------------------------
--   · 적용 순서 = **2026-10-14a(칸) → 2026-10-14c(점포 색인 include) → 이 파일**(🟠3).
--     14c 전에 들어가면 반경 층 집계가 힙을 방문해 찬 캐시 3초대가 다시 난다(2026-10-09c 의 병).
--   · **표지 loaded_ym = published_ym 일 때만**(🟠5). 새 분기를 적재한 뒤·post_load 전(loaded 만 앞선 창)에
--     돌리면 요약표가 loaded 분기로 구워지고 list 함수의 snap(요약표 max)이 그 분기로 넘어가 층 줄 하나만
--     새 분기를 말한다. 관문이 막는다 — post_load.py 를 먼저 끝낸 뒤 돌린다.
--   · 디스크 확장(10/26~30) 뒤 · 배치 창 01:30~12:00 **밖** · 적재·post_load 와 **동시 금지**.
--
-- 실행
-- ----
--   python scripts/dbx.py -f supabase/migrations/2026-10-14b_industry_floor_basement.sql
--   ⓘ 덩어리 안에서 실패하면 통째로 되돌아간다 → 원인을 없애고 이 파일을 그대로 다시 돌린다.
--   ⓘ 다 성공한 뒤 다시 돌려도 같은 결과다(요약표를 한 번 더 굽는 수고만 든다).
--
-- 적용 뒤 확인
-- ------------
--   select p.oid::regprocedure from pg_proc p where p.proname = 'industry_floor_band';
--     -- 한 줄: industry_floor_band(smallint,boolean)
--   select max(snapshot_ym), count(*) from mv_district_industry_floor;   -- 202606 · 약 12만 행(09b 120,528 과 같다 —
--                                                                          --   옛 분기는 칸이 NULL 이라 묶음이 그대로다)
--   select indexrelid::regclass from pg_index where indrelid = 'mv_district_industry_floor'::regclass;
--     -- mv_district_industry_floor_key 하나(_next 가 남으면 정본 색인 점검 [사고])
--   select relname, relacl from pg_class where relname = 'mv_district_industry_floor';   -- anon 없음
--   python scripts/post_load.py --check   -- PR② 가지 판으로 exit 0(머지 전 main 판은 함수 본문·INCLUDE 가 정본과 달라 [사고]가 정상)
--   anon 키:
--     POST /rest/v1/rpc/list_industry_floors {"p_pnu":"1168010600109420015","p_cat_l":"I2"}
--       → 200 · bands 열쇠 다섯 · basement_unknown_counted false(202606 은 칸이 NULL — 화면은 옛 문구)
--     POST /rest/v1/rpc/industry_floor_band {"p_floor":1,"p_basement_unknown":false} → 404/401(밖에 안 열림)
--   3분기 적재 → post_load 뒤: 같은 요청이 basement_unknown_counted true · 화면 설명 줄이 새 두 항목.
--
-- 되돌리기
-- --------
-- **새 마이그레이션 파일**로(같은 바꿔 끼우기 꼴): set lock_timeout → begin → 한 인자 판 industry_floor_band(smallint)
-- 를 2026-10-09b 글자 그대로 다시 만들기 → 요약표를 그 함수로 _next 굽기 → 바꿔 끼우기(drop · rename 둘 · 회수 ·
-- comment · analyze) → list_industry_floors 를 2026-10-09b 글자로 → drop function industry_floor_band(smallint, boolean)
-- → commit → notify. 그리고 이 PR revert(정본·화면 — 화면은 칸이 없으면 옛 문구라 먼저 머지해도 된다).
-- 적용된 이 파일은 고치지 않는다(원장).

set statement_timeout = '900s';
set lock_timeout = '5s';

begin;

-- ── 관문: 언제 돌려도 되는가 (위 「언제 돌리나」) ─────────────────────────────
do $$
begin
  if not exists (
    select 1 from information_schema.columns
     where table_schema = 'public' and table_name = 'unit_business'
       and column_name = 'floor_basement_unknown'
  ) then
    raise exception 'unit_business.floor_basement_unknown 칸이 없습니다 — 2026-10-14a 를 먼저 적용하세요';
  end if;
  if not exists (
    select 1
      from pg_index i
      join pg_class c on c.oid = i.indexrelid
     where c.relname = 'idx_ub_pnu_cat'
       and i.indisvalid
       and pg_get_indexdef(i.indexrelid) like '%floor_basement_unknown%'
  ) then
    raise exception 'idx_ub_pnu_cat 의 include 에 floor_basement_unknown 이 없습니다 — 2026-10-14c 를 먼저 적용하세요(순서 14a → 14c → 14b)';
  end if;
  if not exists (
    select 1 from snapshot_release r where r.loaded_ym = r.published_ym
  ) then
    raise exception '표지 loaded_ym 과 published_ym 이 다릅니다(적재 뒤 · post_load 전) — python scripts/post_load.py 를 먼저 끝낸 뒤 다시 돌리세요';
  end if;
end $$;

-- ── ① 층 묶음 함수 두 인자 판 ─────────────────────────────────────────────────
-- 업종별 층 줄의 층 묶음 다섯 — 지하(b) · 1층(1) · 2층(2) · 3층 이상(3+ — 옥탑 99 포함) · 층 미상(na).
-- 2026-10-14b(물결 2-2c): floor_no 가 NULL 이어도 '지하인데 층 모름' 칸(unit_business.floor_basement_unknown)이
-- true 면 지하(b)로 센다 — 층 번호는 지어내지 않고(절대 규칙 4) 묶음만 지하로 옮긴다.
-- ⛔ 층 미상(NULL)을 빼지 않는다 — 점포 표의 절반쯤(202606 전국 50.3%)이 층이 비어 있어서,
--    빼면 남은 넷이 그 범위의 전부처럼 읽힌다. 미상은 경고가 아니라 **값**이다.
-- ⛔ `strict` 를 붙이지 말 것 — strict 면 NULL 입력에 함수가 아예 안 불리고 NULL 을 돌려줘,
--    층 미상이 'na' 묶음이 아니라 이름 없는 묶음이 된다(화면 열쇠 다섯이 깨진다). 칸이 NULL 인
--    옛 분기 행(👤 D1 — 거슬러 채우지 않는다)도 그래서 'na' 로 간다.
-- ⛔ 칸 검사는 `is true` 로 — `= true`·`coalesce` 를 빼면 NULL 칸이 'b' 로도 'na' 로도 안 가는 갈래가 생긴다.
create or replace function industry_floor_band(p_floor smallint, p_basement_unknown boolean)
returns text
language sql
immutable
as $$
  select case
           when p_floor is null and p_basement_unknown is true then 'b'
           when p_floor is null then 'na'
           when p_floor < 0     then 'b'
           when p_floor = 1     then '1'
           when p_floor = 2     then '2'
           else '3+'
         end;
$$;

comment on function industry_floor_band(smallint, boolean) is
  '업종별 층 분포의 층 묶음 다섯(2026-10-09b · 두 인자 판 2026-10-14b) — 층 NULL 이고 지하인데 층 모름 칸이 true 면 ''b''(지하) · '
  '그 밖의 NULL = ''na''(층 미상 — 칸 NULL 인 옛 분기 포함) · 음수 = ''b''(지하) · 1 = ''1'' · 2 = ''2'' · '
  '그 밖 = ''3+''(3층 이상 — 옥탑 99 는 ''3+''). 요약표 mv_district_industry_floor 와 list_industry_floors 가 '
  '같은 이 함수로 묶는다(두 범위가 다른 자로 묶이지 않게). strict 가 아니다 — NULL 도 묶음이다.';

-- 공개키가 직접 부를 일이 없다 — 요약표·함수 안에서만 쓴다(🚪 닫힌 채 태어나도 한 번 더 닫는다).
revoke all on function industry_floor_band(smallint, boolean) from public, anon, authenticated;

-- ── ② 요약표 다시 굽기 — _next 로 굽고 바꿔 끼운다(2026-10-07a 꼴) ─────────────
-- 굽기를 drop 앞에 둔다 — 옛 표의 ACCESS EXCLUSIVE 를 쥐는 시간이 이름 바꾸기·analyze 뿐이게.
create materialized view mv_district_industry_floor_next as
select d.district_id,
       ub.snapshot_ym,
       ub.cat_l_cd, ub.cat_l_nm,
       ub.cat_m_cd, ub.cat_m_nm,
       public.industry_floor_band(ub.floor_no, ub.floor_basement_unknown) as floor_band,
       count(*)::int as n
from district d
join unit_business ub
  on ub.geom is not null
 and st_contains(d.geom, ub.geom)
where ub.snapshot_ym = (select r.loaded_ym from snapshot_release r)   -- 표지 loaded_ym(결정 0035)
group by 1, 2, 3, 4, 5, 6, 7;

create unique index mv_district_industry_floor_key_next
  on mv_district_industry_floor_next (district_id, snapshot_ym, cat_m_cd, floor_band);

-- 바꿔 끼우기 — 옛 표의 색인은 표와 함께 사라지므로 이름이 비어 rename 이 된다.
-- ⛔ 색인 이름도 되돌린다 — _key_next 로 남으면 post_load --check 정본 색인 점검이 [사고](🟡12).
drop materialized view mv_district_industry_floor;
alter materialized view mv_district_industry_floor_next rename to mv_district_industry_floor;
alter index mv_district_industry_floor_key_next rename to mv_district_industry_floor_key;

-- ⛔ 새 물질화뷰는 anon 에게 자동으로 열린다(pg_default_acl) — 바꿔 끼운 자리에서 닫는다.
revoke all on mv_district_industry_floor from public, anon, authenticated;

comment on materialized view mv_district_industry_floor is
  '상권 × 업종(중분류) × 층 묶음 점포 수 — 최신 분기 한 개만(2026-10-09b · 물결 2-2 · 두 인자 묶음 2026-10-14b). '
  'mv_district_industry_mix 의 층 묶음 판 — 같은 (상권·중분류) 의 n 합이 형제와 같아야 한다(post_load --check 가 대조). '
  '층 묶음은 industry_floor_band(floor_no, floor_basement_unknown) 다섯(b · 1 · 2 · 3+ · na — 옥탑 99 는 3+, '
  '숫자 없이 지하라고만 적힌 가게는 칸이 채워진 분기부터 b, 층 미상은 na 로 그대로 센다). '
  '⚠️ 상권이 겹치는 자리의 점포는 **양쪽에 모두** 세어진다(형제와 같다 — 상권끼리 더하지 말 것). '
  '⚠️ 어느 분기인지는 **구울 때** 굳는다 — 표지 loaded_ym(다 들어온 분기 · 결정 0035)으로 굽고, post_load.py 가 구운 뒤 화면 기준(published_ym)을 올린다. '
  '⛔ anon 에게 열지 않는다 — 화면은 list_industry_floors 함수로만 읽는다.';

analyze mv_district_industry_floor;

-- ── ③ list_industry_floors — 반경 집계 두 인자 판 + basement_unknown_counted ────
-- 대분류를 고른 뒤에만 부른다(첫 화면 미리 부르기에 넣지 않는다). 칸 둘은 형제 list_industry_detail 과
-- 같은 자를 쓴다 — snap(1순위 요약표 · 2순위 published) · me · hit · near 가 글자 그대로 같다.
-- p_cat_m 이 null 이면 그 대분류 전체, 배열이면 그 중분류들만(창업자 칩의 짝 — 학원은 코드 둘).
-- ⛔ `p_cat_l::char(2)` · `p_cat_m::char(4)[]` 캐스트를 지우지 말 것 — 칸이 char 라 text 로 견주면
--    컬럼 쪽이 캐스트돼 색인이 죽는다(2026-08-16b 와 같은 병).
-- ⛔ bands 열쇠 다섯은 **늘 다 있다**(없는 묶음은 0) — 화면 검증기가 열쇠 하나라도 빠지면 그 응답을 버린다.
-- 2026-10-14b(물결 2-2c): 반경 집계도 요약표와 같은 두 인자 묶음 · 응답에 basement_unknown_counted —
--    그 분기가 '지하인데 층 모름' 칸이 채워진 분기인가(화면이 설명 문구 두 벌을 가른다 · 👤 D2').
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
  counted as (
    -- 그 분기 점포 행 하나(기본키 차례 첫 행 — 색인 한 번)의 '지하인데 층 모름' 칸이 채워졌나.
    -- 칸은 2026-10-14a 뒤 적재한 분기만 true/false 이고 옛 분기는 NULL 이다(👤 D1 · 적재기가 한 분기 안
    -- NULL 0 을 확인한다). 분기에 행이 없으면 false — 화면은 옛 문구를 그대로 둔다.
    select coalesce((
             select ub.floor_basement_unknown is not null
             from unit_business ub
             where ub.snapshot_ym = (select ym from snap)
             order by ub.biz_no
             limit 1), false) as v
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
    select public.industry_floor_band(ub.floor_no, ub.floor_basement_unknown) as floor_band, count(*)::int as n
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
    -- true 면 숫자 없이 '지하'라고만 적힌 가게가 지하(b)에 들어 있다 — 화면 설명 문구가 바뀐다.
    'basement_unknown_counted', (select v from counted),
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
  '2026-10-14b(물결 2-2c): 층 묶음은 두 인자 판(숫자 없이 지하라고만 적힌 가게 → b) · basement_unknown_counted = '
  '그 분기가 지하인데 층 모름 칸이 채워진 분기인가(옛 분기 false — 화면 설명 문구 두 벌). '
  'security definer — **나가는 것은 개수뿐이다(상호명 없음).**';

revoke all on function list_industry_floors(text, text, text[]) from public, anon, authenticated;

-- ── ④ 옛 한 인자 판 지우기 — 쓰던 곳(옛 요약표 · 옛 list 함수)은 위에서 이미 바꿨다 ──
-- ⛔ 남겨 두면 같은 이름이 둘이라 post_load --check 함수 대조가 [사고](오버로드 · 🟡11).
drop function if exists industry_floor_band(smallint);

commit;

notify pgrst, 'reload schema';
