-- =====================================================================
-- 서울 상권 개업·폐업 — 표 district_openclose · 함수 list_district_openclose · 신선도 11줄째 (2026-10-05b)
-- =====================================================================
-- 결정 0033(개업·폐업: 서울시가 공표한 개업률·폐업률을 그대로 나른다) 의 창고·함수 조각(PR R1).
--
-- 왜
-- --
-- 서울시 상권분석서비스 「점포-상권」(OA-15577 · 열린 API VwsmTrdarStorQq)이 **분기마다** 상권
-- 1,650개 × 업종 100종의 점포 수·유사 업종 점포 수·개업/폐업 점포 수·개업률·폐업률·프랜차이즈
-- 점포 수를 공표한다(국세청 사업자등록 기반). 상권 코드가 우리 district.district_id 서울 1,650개와
-- 20분기 모두 100% 일치한다(결정 0033 실측표). 우리가 사진 비교로 추정할 이유가 없다 — 공표값을
-- 그대로 담아 그대로 나른다.
--
-- 무엇이 생기나
-- -------------
--   ① 표 district_openclose — (분기, 상권, 업종) 한 줄. 공개키는 못 읽는다(화면은 함수로만).
--      색인 (district_id, quarter) — 함수가 상권별로 최근 분기를 읽는 길. max(quarter)(신선도)는
--      기본키(첫 칸 quarter)가 받친다 → 같은 색인을 또 만들지 않는다(tests/test_freshness_index.py
--      가 '첫 칸이 quarter 인 기본키'도 인정한다).
--   ② list_district_openclose(p_pnu) + api 쌍둥이 — 필지가 속한 서울 상권**마다**(좁은 상권 먼저 ·
--      합치지 않는다) 표 전체 기준 최근 8분기(창) 안의 상권 합산과 그 상권의 최신 분기 업종별 표,
--      그리고 빈 상태 구분 칸 status(창 안에 그 상권 행이 없으면 no_data).
--      공개 호출 허용 총계 27 → 28(api 쌍둥이 하나).
--   ③ get_data_freshness() 에 11번째 줄 '상권 개업·폐업 (서울시)' — 기존 분기 규칙(분기말 +
--      5개월 - 하루)을 쓴다. 이 자료의 분기 꼴은 'YYYYQ' 다섯 자리(Q 없음 · 예 20262)라 `norm` 에
--      **셋째 갈래** `^\d{4}[1-4]$`(앞 네 자리 + 분기×3 → YYYYMM)를 더했다 — 안 더하면 그 줄이
--      **조용히** '정해진 주기 없음'이 된다. 20262 → 202606 → 다음 예정 2026-10-31.
--      ⛔ api.get_data_freshness 는 안 건드린다(public 을 부르는 통과 함수 — 돌려주는 칸도 그대로).
--
-- 잠금
-- ----
-- 새 표에 `references district` 를 거는 순간 district 에 SHARE ROW EXCLUSIVE 잠금이 잡힌다
-- (PostgreSQL 17 문서 13.3 표 — 외래 키를 만드는 CREATE TABLE · 화면의 읽기는 안 막지만 그 표에
-- 쓰는 적재와는 줄을 선다). 나머지(새 표의 색인·RLS·함수 교체)는 새 객체이거나 표를 안 잠근다.
-- 그래도 기다림의 상한을 두려고 `lock_timeout = '2s'` 를 **begin 앞**(세션 설정)에 둔다 —
-- 2초 넘게 못 잡으면 덩어리가 통째로 되돌아가 아무것도 안 바뀐다(다시 돌리면 된다 · 전부 멱등).
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 표만 생기고 신선도가 반쯤 바뀐 채 끊기지 않게 한 덩어리로
-- 묶는다. `notify pgrst` 는 commit **뒤**.
--
-- 실행 순서 (결정 0033 「실행 계획」 R1 — ⚠️ 순서가 곧 안전장치다)
-- ------------------------------------------------------------------
--   1) 22분기 수집을 **먼저 끝낸다**(collect_seoul_openclose.py — 최신 분기부터 · --end-quarter 의무).
--   2) **같은 날에** 이 파일 적용:  python scripts/dbx.py -f supabase/migrations/2026-10-05b_district_openclose.sql
--   3) 곧바로 22분기를 **한 번에** 적재(load_seoul_openclose.py) → post_load.py → post_load.py --check.
--   ⚠️ 이 파일만 먼저 넣고 적재를 미루면 신선도 11번째 줄이 '자료 없음'으로 운영 화면에 남는다.
--      일부 분기만 먼저 넣으면 max(quarter) 가 옛 분기라 '지났습니다'가 바로 뜨고 그물 6호가 이슈를 연다.
--
-- 적용한 사람이 보게 되는 것 (파일의 실제 문장 순서)
-- --------------------------------------------------
--   SET · BEGIN · CREATE TABLE · COMMENT ×4 · CREATE INDEX · ALTER TABLE · REVOKE ·
--   CREATE FUNCTION · COMMENT · REVOKE · CREATE FUNCTION · REVOKE · GRANT ·
--   CREATE FUNCTION · COMMENT · REVOKE · COMMIT · NOTIFY
--   (api 쌍둥이에는 comment 를 따로 달지 않는다 — 2026-10-04a·정본과 같은 관례)
--
-- 적용 뒤 확인 (dbx.py 로 · 적재 전이면 표가 비어 ok 대신 no_data 가 나온다)
-- ------------------------------------------------------------------------
--   select count(*) from api.get_data_freshness();                       -- 11
--   select src, basis, next_expected from api.get_data_freshness() where src like '상권 개업%';
--   select status, district_nm, latest_quarter from api.list_district_openclose('<서울 상권 안 필지>');
--   select status from api.list_district_openclose('<대전 필지>');      -- not_seoul
--
-- 되돌리기 = **새 마이그레이션 파일**(set lock_timeout → begin → get_data_freshness 10줄판 =
-- 2026-10-01a 의 정의를 그대로 다시 만들기 · comment · revoke → api.list_district_openclose 먼저
-- drop → public.list_district_openclose drop → drop table district_openclose → commit → notify)
-- **+ 정본 되돌림(이 PR revert)**. 적용된 이 파일은 고치지 않는다(원장). ⚠️ 라이브만 되돌리면 정본·
-- 가드(test_data_freshness_migration · test_schema_function_drift)와 어긋나 시험이 빨강이 된다.

set lock_timeout = '2s';

begin;

create table if not exists district_openclose (
  quarter                char(5) not null,              -- '20262' (서울시 표기 YYYYQ · Q 없음)
  district_id            text    not null references district(district_id),
  svc_induty_cd          text    not null,              -- 서울시 서비스 업종 100종 코드 (CS100001 …)
  svc_induty_cd_nm       text,
  stor_co                int,                           -- 일반 점포 수(프랜차이즈 제외)
  similr_induty_stor_co  int,                           -- 유사 업종 점포 수 = stor_co + frc_stor_co · 공표 비율의 분모
  opbiz_rt               numeric(6,2),                  -- 개업률 % (공표값 그대로 — 100 을 넘는 행도 있다)
  opbiz_stor_co          int,
  clsbiz_rt              numeric(6,2),                  -- 폐업률 % (공표값 그대로)
  clsbiz_stor_co         int,
  frc_stor_co            int,                           -- 프랜차이즈 점포 수
  source_nm              text,                          -- raw 파일 이름(어느 판에서 왔나)
  loaded_at              timestamptz default now(),
  primary key (quarter, district_id, svc_induty_cd)
);

comment on table district_openclose is '결정 0033 서울시 상권분석서비스(점포-상권 · OA-15577) 공표값 그대로 — (분기, 상권, 업종) 한 줄. 상권 합계 행은 원본에 없다(업종 행을 더한다). 공개키 읽기 금지 — 화면은 list_district_openclose 로만 읽는다';
comment on column district_openclose.similr_induty_stor_co is '유사 업종 점포 수(= stor_co + frc_stor_co, 원본 100% 성립). 서울시 개업률·폐업률의 분모 — stor_co 가 아니다(결정 0033 검산 99.93% · stor 분모면 96.1%)';
comment on column district_openclose.opbiz_rt is '개업률 % — 서울시 공표값 그대로(= 개업 점포 수 ÷ 유사 업종 점포 수 × 100 반올림). 유사 업종 점포 수가 0 이면 0 으로 공표된다. 100 을 넘는 행도 공표값 그대로다';
comment on column district_openclose.clsbiz_rt is '폐업률 % — 서울시 공표값 그대로(= 폐업 점포 수 ÷ 유사 업종 점포 수 × 100 반올림). 유사 업종 점포 수가 0 인데 폐업이 있는 행은 0 으로 공표된다(분기 안에 그 업종 마지막 가게까지 닫힘)';

-- 함수가 상권별로 최근 분기를 읽는 길. max(quarter) 는 기본키(첫 칸 quarter)가 받친다.
create index if not exists idx_district_openclose_district on district_openclose (district_id, quarter);

alter table district_openclose enable row level security;

-- ⛔ Supabase 는 새 표를 anon 에 자동으로 연다(pg_default_acl) — 만든 자리에서 닫는다.
revoke all on district_openclose from public, anon, authenticated;

create or replace function list_district_openclose(p_pnu text)
returns table (
  status           text,
  district_id      text,
  district_nm      text,
  district_type    text,
  latest_quarter   text,
  quarters         jsonb,
  industries       jsonb,
  other_industries jsonb,
  window_quarters  jsonb
)
language sql
stable
security definer
set search_path = public
as $$
  with recursive const as (
    -- 상권 합산 비율을 내는 최소 표본(결정 0033 결정 7 · 절대 규칙 3)과 보는 분기 창의 크기.
    -- 둘 다 한 곳에만 적는다.
    select 30 as min_similr, 8 as n_quarters
  ),
  me as (
    -- 좌표가 없으면 아무 상권에도 안 든다는 **단정**이 새어 나가지 않게 따로 가른다(no_coord).
    -- ⛔ pnu 칸은 char(19) — 인자를 그대로 견주면 칸 쪽이 text 로 캐스트돼 색인이 죽는다.
    select p.geom
    from parcel p
    where p.pnu = p_pnu::char(19) and p.geom is not null
  ),
  hit as (
    -- 서울 필지가 담긴 **서울시 상권**만. 술어는 list_building_districts 와 같은 st_contains.
    select d.district_id, d.district_nm, d.district_type, d.area_m2
    from district d cross join me
    where left(p_pnu::char(19), 2) = '11'
      and left(d.sigungu_code, 2) = '11'
      and st_contains(d.geom, me.geom)
  ),
  head as (
    -- 건물 단위 상태 셋 — 판정 순서가 곧 뜻이다(위부터, 서로 배타).
    --   no_coord               필지 좌표 없음(서울이든 아니든 — 모르는 것은 모른다고)
    --   not_seoul              시·도가 서울이 아님(대전 등 — 서울시 자료는 서울 상권만 다룬다)
    --   outside_seoul_district 서울인데 속한 서울시 상권이 없음
    -- 셋 다 아니면 null → 상권마다 ok / no_data 한 줄씩이 대신 나간다.
    select case
             when not exists (select 1 from me) then 'no_coord'
             when left(p_pnu::char(19), 2) <> '11' then 'not_seoul'
             when not exists (select 1 from hit) then 'outside_seoul_district'
           end as status
  ),
  win (quarter, n) as (
    -- **표 전체** 기준 가장 최근 8분기 — 모든 상권이 같은 창을 본다(상권마다 제 최신 8분기를
    -- 잡으면 자료가 끊긴 상권이 몇 해 전 숫자를 '최근'처럼 보인다). 한 분기씩 기본키(첫 칸
    -- quarter)를 거꾸로 짚어 내려간다 — distinct 로 168만 행을 훑지 않는다.
    select max(o.quarter), 1 from district_openclose o
    union all
    select (select max(o.quarter) from district_openclose o where o.quarter < w.quarter), w.n + 1
    from win w cross join const c
    where w.n < c.n_quarters and w.quarter is not null
  ),
  wq as (
    -- 창 그 자체(표 전체 최근 8분기 · 최신 → 옛 순 · 표가 비었으면 빈 배열) — 화면이 그 상권의
    -- latest_quarter 와 견주어 "이 상권은 n분기까지"를 말할 수 있게 **모든 줄에 같은 값**을 싣는다.
    select coalesce(jsonb_agg(w.quarter::text order by w.quarter desc)
                      filter (where w.quarter is not null), '[]'::jsonb) as window_quarters
    from win w
  ),
  qs as (
    -- 창 안의 분기 × 이 필지의 상권. 창 안에서 그 상권에 빠진 분기는 빠진 채 둔다(채우지 않는다).
    select h.district_id, w.quarter
    from hit h cross join win w
    where w.quarter is not null
  ),
  sums as (
    -- ⛔ 그 상권·분기의 업종 행 **전부**를 더한다(결정 0033 결정 7 합산 규칙). 유사 업종 점포 수가
    --   0 인데 개업·폐업이 있는 행(분기 안에 그 업종 마지막 가게까지 닫힘)도 분자에 넣는다 —
    --   닫힌 가게는 실제로 닫혔다. 여기에 유사 업종 점포 수 조건을 걸면 그 가게들이 숫자에서 사라진다.
    select o.district_id, o.quarter,
           sum(o.similr_induty_stor_co) as similr,
           sum(o.stor_co)               as stor,
           sum(o.frc_stor_co)           as frc,
           sum(o.opbiz_stor_co)         as opbiz,
           sum(o.clsbiz_stor_co)        as clsbiz
    from qs
    join district_openclose o on o.district_id = qs.district_id and o.quarter = qs.quarter
    group by o.district_id, o.quarter
  ),
  latest as (
    -- 그 상권이 창 안에서 **실제로 가진** 최신 분기 — 창의 최신(표 전체 최신)과 다를 수 있다
    -- (화면이 "이 상권은 20xx년 n분기까지"라고 따로 말할 수 있게 그대로 돌려준다).
    -- 창 안에 행이 하나도 없으면 여기 없다 → no_data.
    select s.district_id, max(s.quarter) as quarter
    from sums s
    group by s.district_id
  ),
  ranked as (
    -- 최신 분기 업종 행 — 유사 업종 점포 수가 많은 순(같으면 코드 순). 위 10개만 따로 싣고
    -- 나머지는 '그 밖 N업종' 한 덩어리로 더한다. 업종 행의 비율은 공표값 그대로다.
    select o.*,
           row_number() over (partition by o.district_id
                              order by o.similr_induty_stor_co desc, o.svc_induty_cd) as rn
    from latest l
    join district_openclose o on o.district_id = l.district_id and o.quarter = l.quarter
  ),
  rows_out as (
    select hd.status,
           null::text as district_id, null::text as district_nm, null::text as district_type,
           null::text as latest_quarter,
           null::jsonb as quarters, null::jsonb as industries, null::jsonb as other_industries,
           0::numeric as sort_area
    from head hd
    where hd.status is not null
    union all
    select case when l.quarter is null then 'no_data' else 'ok' end,
           h.district_id, h.district_nm, h.district_type,
           l.quarter::text,
           (select jsonb_agg(jsonb_build_object(
                     'quarter',               s.quarter::text,
                     'similr_induty_stor_co', s.similr,
                     'stor_co',               s.stor,
                     'frc_stor_co',           s.frc,
                     'opbiz_stor_co',         s.opbiz,
                     'clsbiz_stor_co',        s.clsbiz,
                     -- 서울시 산식 그대로(분모 = 유사 업종 점포 수). 표본이 모자라면 비율은 null —
                     -- 개수만 나간다. 분모가 0 이면 여기서 이미 null 이다(min_similr > 0).
                     'opbiz_rt',  case when s.similr >= c.min_similr
                                       then round(s.opbiz * 100.0 / s.similr, 2) end,
                     'clsbiz_rt', case when s.similr >= c.min_similr
                                       then round(s.clsbiz * 100.0 / s.similr, 2) end)
                   order by s.quarter desc)
              from sums s cross join const c
             where s.district_id = h.district_id),
           (select jsonb_agg(jsonb_build_object(
                     'svc_induty_cd',         r.svc_induty_cd,
                     'svc_induty_cd_nm',      r.svc_induty_cd_nm,
                     'similr_induty_stor_co', r.similr_induty_stor_co,
                     'stor_co',               r.stor_co,
                     'frc_stor_co',           r.frc_stor_co,
                     'opbiz_stor_co',         r.opbiz_stor_co,
                     'opbiz_rt',              r.opbiz_rt,
                     'clsbiz_stor_co',        r.clsbiz_stor_co,
                     'clsbiz_rt',             r.clsbiz_rt)
                   order by r.rn)
              from ranked r
             where r.district_id = h.district_id and r.rn <= 10),
           (select case when count(*) > 0 then jsonb_build_object(
                     'industry_count',        count(*),
                     'similr_induty_stor_co', sum(r.similr_induty_stor_co),
                     'stor_co',               sum(r.stor_co),
                     'frc_stor_co',           sum(r.frc_stor_co),
                     'opbiz_stor_co',         sum(r.opbiz_stor_co),
                     'clsbiz_stor_co',        sum(r.clsbiz_stor_co),
                     'opbiz_rt',  case when sum(r.similr_induty_stor_co) >= max(c.min_similr)
                                       then round(sum(r.opbiz_stor_co) * 100.0
                                                  / sum(r.similr_induty_stor_co), 2) end,
                     'clsbiz_rt', case when sum(r.similr_induty_stor_co) >= max(c.min_similr)
                                       then round(sum(r.clsbiz_stor_co) * 100.0
                                                  / sum(r.similr_induty_stor_co), 2) end) end
              from ranked r cross join const c
             where r.district_id = h.district_id and r.rn > 10),
           h.area_m2
    from hit h
    left join latest l on l.district_id = h.district_id
  )
  select ro.status, ro.district_id, ro.district_nm, ro.district_type, ro.latest_quarter,
         ro.quarters, ro.industries, ro.other_industries, wq.window_quarters
  from rows_out ro cross join wq
  -- 좁은 상권이 더 구체적인 설명이라 먼저 온다(list_building_districts 와 같은 정렬).
  order by ro.sort_area asc, ro.district_id;
$$;

comment on function list_district_openclose(text) is
  '결정 0033 이 필지가 속한 서울시 상권마다(좁은 상권 먼저 · 합치지 않는다) 서울시 상권분석서비스가 '
  '공표한 개업·폐업 — 표 전체 기준 최근 8분기(모든 상권이 같은 창) 안의 상권 합산(유사 업종 점포 수·'
  '점포 수·프랜차이즈·개업·폐업의 합과, '
  '서울시 산식 그대로의 비율 = 개업 합 ÷ 유사 업종 점포 수 합 × 100 · 폐업 같음 · 유사 업종 점포 수 합이 '
  '30 미만이면 비율 null · 창 안에서 그 상권에 빠진 분기는 빠진 채) + 그 상권의 최신 분기 업종별 표(유사 업종 '
  '점포 수 상위 10 · 나머지는 그 밖 N업종 합 · 업종 행의 비율은 공표값 그대로). latest_quarter 는 그 상권이 '
  '창 안에서 실제로 가진 최신 분기다(표 전체 최신과 다를 수 있다). window_quarters 는 그 창의 분기 목록(jsonb · '
  '최신 → 옛 순 · 표가 비었으면 빈 배열)이고 status 와 무관하게 **모든 줄에 같은 값**이다(no_coord·not_seoul·'
  'outside_seoul_district 줄에도). '
  '합산은 업종 행 전부를 더한다(유사 업종 점포 수 0 인데 폐업이 있는 '
  '행도 분자에 든다). status 로 빈 상태를 가른다: no_coord(필지 좌표 없음) → not_seoul(서울 아님) → '
  'outside_seoul_district(서울인데 속한 서울시 상권 없음) — 이 셋은 한 줄만, 아니면 상권마다 ok(창 안에 행 있음) / '
  'no_data(창 안에 행 없음 — 창 밖 옛 분기만 있어도 no_data). 대전은 not_seoul 이다 — 숫자 0 이 아니라 그 자료가 없는 곳이다. '
  'security definer (district_openclose·district·parcel 이 anon 에게 닫혀 있어 소유자 권한으로 대신 '
  '읽는다. 나가는 것은 상권 이름·종류와 서울시 공표 수·비율뿐이다).';

-- 만든 자리에서 다시 닫는다(대시보드 판은 anon 을 붙인다).
revoke all on function list_district_openclose(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.list_district_openclose(p_pnu text)
returns table (
  status           text,
  district_id      text,
  district_nm      text,
  district_type    text,
  latest_quarter   text,
  quarters         jsonb,
  industries       jsonb,
  other_industries jsonb,
  window_quarters  jsonb
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_district_openclose(p_pnu) $$;

revoke all on function api.list_district_openclose(text) from public, anon, authenticated;
grant execute on function api.list_district_openclose(text) to anon, authenticated;

-- ⛔ public.list_district_openclose 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.

-- ── 신선도 11번째 줄 (결정 0033 설계 칸 6) ─────────────────────────────────────
-- 정본(schema.sql)의 정의를 그대로 잘라 붙였다 — 머리·comment 는 tests/test_data_freshness_migration.py
-- 가 정본과 글자 대조한다(create or replace 는 머리 속성을 새 정의로 덮어쓴다).
create or replace function get_data_freshness()
returns table (
  src           text,
  basis_kind    text,
  basis         text,
  next_expected date,
  cadence       text
)
language sql
stable
security definer
set search_path = public
as $$
  with raw as (
    -- ⓘ 순서를 ord 로 못 박는다. union all 은 순서를 보장하지 않으므로, 이 숫자가 없으면
    --   화면의 줄 순서가 실행할 때마다 달라질 수 있다(사람은 그걸 자료가 바뀐 것으로 읽는다).
    select 1 as ord,
           '점포·업종 (상권정보)'::text as src,
           '분기'::text                 as basis_kind,
           (select max(t.snapshot_ym)::text from unit_business t) as basis,
           'sangkwon'::text             as rule_kind,
           '분기마다 (다음 분기 자료가 공개되면 사람이 적재)'::text as cadence
    union all
    select 2, '실거래 (매매)', '계약월',
           (select max(t.contract_ym)::text from transaction t),
           'none',
           '수시 (서울·대전 전부 활성화 뒤 확대)'
    union all
    select 3, '건축물대장', '적재일',
           (select (max(t.updated_at) at time zone 'Asia/Seoul')::date::text from building t),
           'none',
           '월간 파일 (사람이 적재)'
    union all
    select 4, '상권 경계', '계산일',
           (select (max(t.computed_at) at time zone 'Asia/Seoul')::date::text from district t),
           'none',
           '비정기 (원천이 바뀌면)'
    union all
    select 5, 'LH 상가 공고', '수집일',
           (select (max(t.collected_at) at time zone 'Asia/Seoul')::date::text from lh_notice t),
           'none',
           '주 1회 감시 · 적재는 사람'
    union all
    select 6, '건축 인허가', '기준월',
           (select max(t.loaded_ym)::text from arch_permit t),
           'permit',
           '월 1회'
    union all
    select 7, '국세청 기준시가', '고시일',
           (select max(t.notice_date)::text from nts_base_price t),
           'nts',
           '연 1회 (매년 3월 고시)'
    union all
    select 8, '상권 임대 동향 (부동산원)', '분기',
           (select max(t.quarter)::text from rent_stat t),
           'rone',
           '분기마다'
    union all
    select 9, '참고 시세 성적표', '적재일',
           (select (max(t.loaded_at) at time zone 'Asia/Seoul')::date::text
              from price_gate_sigungu t),
           'none',
           '재생성 때 (결재 사항)'
    union all
    select 10, '필지 (토지 특성)', '갱신일',
           (select (max(t.updated_at) at time zone 'Asia/Seoul')::date::text from parcel t),
           'none',
           '연 1회 (브이월드)'
    union all
    -- 결정 0033 — 서울시 상권분석서비스 개업·폐업. 분기 꼴이 'YYYYQ' 다섯 자리(Q 없음)다.
    select 11, '상권 개업·폐업 (서울시)', '분기',
           (select max(t.quarter)::text from district_openclose t),
           'seoul_openclose',
           '분기마다'
  ),
  norm as (
    -- 분기 규칙을 쓰는 세 줄을 **같은 모양('YYYYMM' 분기말 달)** 으로 맞춘다. 이렇게 해야
    -- 아래 계산이 한 번만 적힌다 — 세 벌로 적어 두면 한쪽만 고쳐지는 날 자료끼리 서로
    -- 다른 주기를 말한다.
    -- ⛔ 서울시 분기 꼴('20262')은 둘째 갈래(`YYYYQn`)에도 첫째 갈래(여섯 자리)에도 안 걸린다 —
    --   셋째 갈래가 없으면 그 줄은 에러 없이 '정해진 주기 없음'(null)이 된다(결정 0033 v3 재검사).
    select r.*,
           case
             when r.rule_kind = 'sangkwon' and r.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
               then r.basis
             when r.rule_kind = 'rone' and r.basis ~ '^\d{4}Q[1-4]$'
               then left(r.basis, 4) || lpad((right(r.basis, 1)::int * 3)::text, 2, '0')
             when r.rule_kind = 'seoul_openclose' and r.basis ~ '^\d{4}[1-4]$'
               then left(r.basis, 4) || lpad((right(r.basis, 1)::int * 3)::text, 2, '0')
           end as q_ym
    from raw r
  )
  select n.src,
         n.basis_kind,
         n.basis,
         case
           -- 분기 자료: 다음 분기가 **공개되는 달**의 말일(분기말 + 5개월 - 하루).
           when n.q_ym is not null
             then (to_date(n.q_ym, 'YYYYMM') + interval '5 months' - interval '1 day')::date
           -- 월간 자료: 다음 판이 **공개되는 달**의 말일(기준월 + 3개월 - 하루).
           when n.rule_kind = 'permit' and n.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
             then (to_date(n.basis, 'YYYYMM') + interval '3 months' - interval '1 day')::date
           -- 연 1회: 다음 해 3월 31일(국세청 고시가 매년 3월).
           when n.rule_kind = 'nts' and n.basis ~ '^\d{4}-\d{2}-\d{2}$'
             then make_date(left(n.basis, 4)::int + 1, 3, 31)
         end as next_expected,
         n.cadence
  from norm n
  order by n.ord;
$$;

comment on function get_data_freshness() is
  '화면 아래 "이 자료는 언제 것인가" 표. 열한 갈래 자료의 가장 최근 도장(분기·계약월·적재일·'
  '계산일·수집일·기준월·고시일·갱신일)을 창고에서 읽어 한 줄씩 준다. '
  '⛔ 숫자를 화면에 박지 않기 위한 함수다 — 신선도를 글자로 적어 두면 적재하는 순간부터 '
  '그 글자만 거짓말을 한다. next_expected 도 사람이 적는 값이 아니라 규칙으로 계산한다: '
  '분기 자료는 분기말 달 + 5개월 - 하루(다음 분기가 공개되는 달의 말일 — 분기 꼴 셋 '
  '''YYYYMM''·''YYYYQn''·''YYYYQ''(서울시 다섯 자리)를 같은 분기말 달로 맞춘 뒤 한 번만 계산), 월간 자료는 '
  '기준월 + 3개월 - 하루(다음 판이 공개되는 달의 말일), 국세청 기준시가는 고시일의 다음 해 3월 31일. '
  '주기가 없는 자료는 null 이다 — 없는 주기를 지어내면 "늦었다"는 거짓 신호가 뜬다. '
  '기준값이 그 모양이 아니면 계산하지 않고 그 칸만 비운다(to_date 가 터지면 표가 통째로 '
  '사라진다). timestamptz 는 전부 Asia/Seoul 로 옮겨 날짜를 자른다 — 이 DB 가 UTC 라 '
  '그냥 자르면 한국 새벽 0~9시에 어제 날짜가 찍힌다. '
  '⛔ api_quota_log 는 안 본다 — 그건 우리 호출 장부이지 자료의 나이가 아니고, 하한선일 뿐이다. '
  '자료가 0행이면 basis 가 null 이고 줄은 그대로 나온다(화면이 "자료 없음"이라 적는다 — '
  '줄을 빼면 "그런 자료를 안 쓴다"로 읽힌다). '
  'security definer (열한 표가 전부 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 집계 도장 열한 개뿐이고 원본 행은 한 줄도 안 나간다). 2026-09-05d · 월간 규칙 2026-10-01a · '
  '서울 개업·폐업 2026-10-05b';

revoke all on function get_data_freshness() from public, anon, authenticated;

commit;

-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';
