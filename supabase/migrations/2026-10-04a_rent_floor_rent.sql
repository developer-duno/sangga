-- =====================================================================
-- 층별 임대료·소득수익률 — rent_stat 칸 둘 + list_rent_stats 칸 둘 (2026-10-04a)
-- =====================================================================
-- 결정 0031(층별 임대료: 부동산원이 조사한 값을 그대로 보여준다) 의 창고·함수 조각(PR-R1).
--
-- 왜
-- --
-- 부동산원은 상권 × 층 구간의 ㎡당 임대료를 **이미 조사해 공표한다.** 2026-08-09 에 받아 둔
-- 원본 `data/raw/rone/*/floor_util.jsonl` 에 층 구간마다 `임대료`(천원/㎡)와 `효용비율`(%) 두
-- 항목이 함께 있는데, 적재기가 효용비율만 담고 임대료 줄은 버리고 있었다. 효용비율은 그 층
-- 임대료 ÷ 1층 임대료 × 100 **그 자체**라(서울·대전 최신 분기 1,398쌍 검산 · 최대 차이 0),
-- "임대료 × 효용비율"은 추정이 아니라 공표값을 되만드는 계산이었다. 그래서 공표값을 그대로
-- 담아 그대로 나른다. 같은 김에 yield 원본의 소득수익률(투자수익률과 다른 항목)도 담는다.
--
-- 무엇이 바뀌나
-- -------------
--   ① rent_stat 에 칸 둘 — floor_rent jsonb(층 구간별 ㎡당 임대료, 천원/㎡ 그대로) ·
--      income_yield_rate numeric(5,2)(소득수익률 %, 분기 값). 칸 주석 넷(새 둘 + 고친 둘).
--   ② api.rent_stat 뷰를 다시 만든다 — `select *` 뷰는 **만든 날의 칸으로 굳어** 있어, 표에 칸을
--      더해도 뷰에는 안 생긴다. 적재기는 REST(= 이 뷰)로 쓰므로 안 고치면 새 두 칸을 못 넣는다.
--      칸을 **끝에** 더하는 것은 `create or replace view` 로 된다(2026-08-24a 선례).
--   ③ list_rent_stats 와 api 쌍둥이 — 돌려주는 칸 7개 뒤에 income_yield_rate · floor_rent.
--      ⛔ 돌려주는 칸이 바뀌면 `create or replace` 는 거부된다("cannot change return type") →
--      부르는 쪽(api)부터 지우고 다시 만든다(2026-09-05b 와 같은 순서).
--   ⛔ floor_util_ratio 는 여전히 함수 밖으로 **안 나간다**(결정 0024 유지 — 내보내면 화면이
--      언젠가 곱한다). 함수 이름·서명은 그대로라 공개 호출 허용 목록 25 도 그대로다.
--
-- 잠금
-- ----
-- `alter table … add column`(기본값 없음)은 ACCESS EXCLUSIVE 잠금을 잡는다(PostgreSQL 17 문서
-- ALTER TABLE: 따로 적힌 예외가 아니면 ACCESS EXCLUSIVE). 칸만 더하고 표를 다시 쓰지 않아
-- 순간이지만, 오래 도는 조회가 표를 쥐고 있으면 그 뒤로 화면 조회가 줄을 선다 →
-- `lock_timeout = '2s'` 를 **begin 앞**(세션 설정)에 둔다. 2초 넘게 못 잡으면 트랜잭션이 통째로
-- 되돌아가 아무것도 안 바뀐다 — 다시 돌리면 된다(칸 추가는 `if not exists` 라 멱등).
-- `create or replace view`·`drop/create function` 도 같은 덩어리 안이라 commit 까지 잠금이 이어진다.
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 함수를 지운 뒤 끊기면 화면의 『상권 임대 동향』 카드가
-- 통째로 사라진 채 남는다 — 한 덩어리로 묶는다. `notify pgrst` 는 commit **뒤**.
--
-- 실행법
-- ------
--   python scripts/dbx.py -f supabase/migrations/2026-10-04a_rent_floor_rent.sql
--   (합친 뒤 본 폴더 main 에서 — 그다음 load_rone.py --dry-run → 적재 → post_load.py → --check)
--
--   적재 전후 확인(dbx.py 로 — 적재 전에 ①②를 기록해 두고 적재 뒤 다시 잰다):
--   -- ① 적재 전에 기록하고 ② 적재 뒤 같은 값인지 본다(효용비율이 한 글자도 안 바뀌었나)
--   select md5(string_agg(quarter || region_code || bld_type || coalesce(floor_util_ratio::text, ''), '|' order by quarter, region_code, bld_type)) from rent_stat;
--   -- ③ 적재 뒤 세 값이 모두 같아야 한다(지금 7,232)
--   select count(*), count(floor_rent), count(income_yield_rate) from rent_stat;
--
-- 적용한 사람이 보게 되는 것 (파일의 실제 문장 순서)
-- --------------------------
--   SET · BEGIN · ALTER TABLE · COMMENT ×4 · CREATE VIEW · REVOKE · GRANT ·
--   DROP FUNCTION ×2 · CREATE FUNCTION · COMMENT · REVOKE ·
--   CREATE FUNCTION · REVOKE · GRANT · COMMIT · NOTIFY
--   (api 쌍둥이에는 comment 를 따로 달지 않는다 — 옛 2026-08-31a 와 정본도 그렇다)
--   적재 전에는 새 두 칸이 전부 비어(null) 있다 — 화면은 선택 칸이라 그대로 선다.
--
-- 되돌리기 = **새 마이그레이션 파일**(set lock_timeout → begin → api 먼저 drop → 옛 7칸 정의
-- 다시 만들기 → comment·revoke/grant → commit → notify) **+ 정본 되돌림(PR revert)**.
-- 적용된 이 파일은 고치지 않는다(원장). 칸 둘은 남겨도 해가 없다.

set lock_timeout = '2s';

begin;

alter table rent_stat
  add column if not exists floor_rent jsonb,
  add column if not exists income_yield_rate numeric(5,2);

comment on column rent_stat.floor_util_ratio is '1층=100 기준 층별효용비율(그 층 임대료 ÷ 1층 임대료 × 100 — 부동산원 공표값). 층별 임대료 자체는 floor_rent 에 공표값 그대로 있다(결정 0031). 함수 밖으로 내보내지 않는다(결정 0024 — 내보내면 화면이 언젠가 곱한다)';
comment on column rent_stat.yield_rate is '투자수익률(%) · 분기 값(4를 곱해 한 해 값으로 바꾸지 않는다). 소득수익률은 income_yield_rate';
comment on column rent_stat.floor_rent is '결정 0031 층 구간별 ㎡당 월 임대료(천원/㎡ — 부동산원 층별 임대료 공표값 그대로). 열쇠 = "-1"·"1"~"5"·"6+"(상가 3종) + "6-10"·"11+"(오피스). 0 이하·빈 값은 조사값 없음이라 열쇠를 만들지 않는다. 건물 값이 아니라 조사 상권의 평균이다';
comment on column rent_stat.income_yield_rate is '결정 0031 소득수익률(%) · 분기 값. 투자수익률(yield_rate)과 다른 항목이다(투자 = 소득 + 자본)';

-- 표에 더한 칸을 뷰에도 싣는다(`select *` 는 만든 날의 칸으로 굳는다).
create or replace view api.rent_stat        as select * from public.rent_stat;
revoke all on api.rent_stat        from public, anon, authenticated;
grant select, insert, update, delete on api.rent_stat        to service_role;

-- ⛔ api(부르는 쪽)를 먼저 지운다 — 허공을 가리키는 순간을 안 만들려고(2026-09-05b 머리말).
drop function if exists api.list_rent_stats(text);
drop function if exists public.list_rent_stats(text);

create or replace function list_rent_stats(p_pnu text)
returns table (
  district_nm       text,
  rone_region_nm    text,
  bld_type          text,
  quarter           text,
  vacancy_rate      numeric,
  rent_per_m2       numeric,
  yield_rate        numeric,
  income_yield_rate numeric,
  floor_rent        jsonb
)
language sql
stable
security definer
set search_path = public
as $$
  with me as (
    -- 좌표가 없으면 아예 답하지 않는다. 여기를 열어 두면 빈손이 "이 자리는 조사 대상이
    -- 아니다"라는 **단정**으로 새어 나간다(list_building_districts 와 같은 원칙).
    select p.geom as g
    from parcel p
    where p.pnu = p_pnu::char(19) and p.geom is not null
  ),
  hit as (
    -- 술어를 st_contains 로 맞춘다 — 결정 0008·0011·0014 의 실측이 이 술어로 나온 숫자다.
    select d.district_id, d.district_nm, d.area_m2
    from district d cross join me
    where st_contains(d.geom, me.g)
  ),
  pair as (
    -- 이을 근거가 없는 상권은 여기서 저절로 빠진다(district_rone_map 에 행이 없다).
    select h.district_id, h.district_nm, h.area_m2, m.rone_region_nm
    from hit h
    join district_rone_map m on m.district_id = h.district_id
  ),
  latest as (
    -- (조사구역, 종류)마다 가장 최근 분기 한 줄. 전체 최신 분기 하나로 자르면 그 분기에
    -- 표본이 없는 종류가 통째로 사라진다("오피스는 조사 안 하는 동네"로 보인다).
    -- 결정 0031: 소득수익률과 층별 임대료(공표값 그대로)를 같은 줄에 싣는다.
    -- ⛔ floor_util_ratio 는 여기에도 바깥 select 에도 넣지 않는다(결정 0024).
    select distinct on (r.region_nm, r.bld_type)
           r.region_nm, r.bld_type, r.quarter,
           r.vacancy_rate, r.rent_per_m2, r.yield_rate,
           r.income_yield_rate, r.floor_rent
    from rent_stat r
    where r.region_nm in (select p.rone_region_nm from pair p)
    order by r.region_nm, r.bld_type, r.quarter desc
  )
  select p.district_nm,
         p.rone_region_nm,
         l.bld_type,
         l.quarter::text,
         l.vacancy_rate,
         l.rent_per_m2,
         l.yield_rate,
         l.income_yield_rate,
         l.floor_rent
  from pair p
  join latest l on l.region_nm = p.rone_region_nm
  -- 좁은 상권이 더 구체적인 설명이라 먼저 온다(list_building_districts 와 같은 정렬).
  order by p.area_m2 asc, p.district_id, l.bld_type, l.region_nm;
$$;

comment on function list_rent_stats(text) is
  '결정 0024·0031 이 필지가 속한 상권의 한국부동산원 임대동향조사 값 — 상권 이름, 부동산원 '
  '조사구역 이름, 건물 종류, 분기, 공실률(%), ㎡당 임대료(천원/㎡ 공표 단위 그대로), '
  '투자수익률(%, 분기 값), 소득수익률(%, 분기 값), 층별 ㎡당 임대료(jsonb — 열쇠 "-1"·"1"~"5"·"6+"·'
  '"6-10"·"11+", 천원/㎡ 공표값 그대로 · 조사값 없는 층 구간은 열쇠가 없다). '
  '⛔ 역산·환산을 하지 않는다(조사값 그대로 나른다 — 층별효용비율은 안 나간다). '
  '⛔ 이을 근거가 없으면 줄이 아예 없다 — 시·도 평균으로 메우지 않는다(조사 안 한 곳을 '
  '조사한 것처럼 말하지 않기 위해서다). (조사구역, 종류)마다 가장 최근 분기 한 줄만 준다 — '
  '전체 최신 분기로 자르면 그 분기에 표본이 없는 종류가 통째로 사라진다. '
  'security definer (district·district_rone_map·rent_stat·parcel 이 anon 에게 닫혀 있어 '
  '소유자 권한으로 대신 읽는다. 나가는 것은 상권·조사구역 이름과 공표 통계값뿐이다).';

-- 다시 만든 함수는 그 자리에서 다시 닫는다(새 함수는 닫힌 채 태어나지만 대시보드 판은 다르다).
revoke all on function list_rent_stats(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.list_rent_stats(p_pnu text)
returns table (
  district_nm       text,
  rone_region_nm    text,
  bld_type          text,
  quarter           text,
  vacancy_rate      numeric,
  rent_per_m2       numeric,
  yield_rate        numeric,
  income_yield_rate numeric,
  floor_rent        jsonb
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_rent_stats(p_pnu) $$;

revoke all on function api.list_rent_stats(text) from public, anon, authenticated;
grant execute on function api.list_rent_stats(text) to anon, authenticated;

-- ⛔ public.list_rent_stats 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.

commit;

-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';
