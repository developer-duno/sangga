-- =====================================================================
-- 2026-10-29a — 대전 「동네 폐업 (대전시 공표)」 (결정 0044)
-- =====================================================================
--
-- 왜
-- --
-- 개업·폐업 카드(결정 0033)는 서울시 자료라 대전 건물에서는 "이 건물(대전)에는 그 자료가 없습니다" 한 줄뿐이었다.
-- 대전광역시 상권분석 서비스(8989.daejeon.go.kr)가 행정동 × 업종 × 월 폐업 수를 낸다 — 2026-10-28 사장님이
-- 대전시 소상공정책과와 통화해 「출처 밝히고 사용해도 된다」 구두 허락을 받았다(결정 0044).
-- 👤 결정: ① 대전 건물에서만 제목 「동네 폐업 (대전시 공표)」(서울은 그대로) ② 손님을 받는 가게 업종만(33종)
--          ③ 2025년부터 · 최근 6개월은 뺀다 ④ 원문 그대로 "점포" + 대전시 기준 ⑤ 폐업만(대전시 점포 수·상권 파일은 안 쓴다).
--
-- 무엇이 생기나 (새 객체 + 신선도 함수 한 줄 — 기존 표는 한 글자도 안 바꾼다)
-- -------------------------------------------------------------------------
--   ① 표 넷 — daejeon_dong_closure(행정동 · 달 · 업종 · 폐업 수) · daejeon_pnu_dong(땅 → 동 ⓐ) ·
--      daejeon_bjd_dong(법정동 → 동 ⓑ) · daejeon_closure_release(받은 날 한 줄). 전부 RLS 켬 + 권한 회수(공개키 0).
--      적재는 scripts/collectors/load_daejeon8989_closure.py(통째 교체 · 한 트랜잭션).
--   ② 함수 get_daejeon_dong_closure(p_pnu text) + api 쌍둥이 — 그 건물이 선 동의 분기별 폐업 건수(최근 8분기 창) ·
--      최근 4분기 합 · 업종별(많은 순). status = not_daejeon · no_dong · ok. 받은 날 표지가 0줄이면 0줄.
--      공개 호출 허용 총계 33 → 34(post_load.py ANON_CALLABLE_ALLOWLIST).
--   ③ get_data_freshness 다시 만들기 — 12번 줄 「동네 폐업 (대전시)」 · 기준 = 받은 날 · 다음 갱신 예정 = 받은 날 + 3개월
--      (새 규칙 'daejeon_closure' · 'YYYY-MM-DD' 일 때만 계산) · comment. 나머지 열 줄·규칙은 글자 그대로다.
--      ⓘ api.get_data_freshness 는 다시 만들지 않는다 — 통과 함수라 본문이 그대로다(2026-10-15a 와 같은 판단).
-- ⛔ 머리(language · stable · security definer · set search_path)와 comment 는 정본(schema.sql)과 글자 그대로다 —
--    tests/test_daejeon_dong_closure_migration.py 가 대조한다(CLAUDE.md ⛔ 2026-10-01a).
-- ⛔ 서명은 하나뿐이다(이름당 pg_proc 1).
--
-- 잠금
-- ----
-- 새 표·새 함수 만들기와 함수 교체(create or replace)는 기존 표를 잠그지 않는다. 형제 관습대로 `lock_timeout` 은
-- **begin 앞**(세션 설정)에 둔다 — 함수 카탈로그 행을 다른 세션이 쥐고 있으면 오래 줄 서지 않고 실패한다(통째 롤백).
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 중간에 끊기면 신선도 함수가 없는 표를 읽거나 api 쌍둥이 없이 원본만 남는다.
-- `notify pgrst` 는 commit **뒤**.
--
-- 실행 순서 — DB 먼저 → 적재 → 그 뒤 화면 머지 (Claude 가 dbx 로 · 사장님께 여쭌 뒤)
-- ------------------------------------------------------------------------------
-- 어느 쪽이 먼저여도 손님 화면은 안 깨진다 — 화면은 함수가 없거나(PGRST202) 0줄·모양 이상이면 지금 대전 카드
-- (옛 제목 · 「그 자료가 없습니다」) 그대로 선다.
--   ① python scripts/dbx.py -f supabase/migrations/2026-10-29a_daejeon_dong_closure.sql
--   ② python scripts/collectors/load_daejeon8989_closure.py --raw-dir data/raw/daejeon_8989/20261028 --dry-run → 실적재
--      (적재 전엔 신선도 12번 줄이 '자료 없음'(basis null) — 같은 날 ① 바로 뒤에 넣는다)
--   ③ python scripts/post_load.py → python scripts/post_load.py --check — 0 이어야 한다(허용 목록 총계 34 · 정본↔라이브 함수 일치)
--   ④ 화면 PR 머지(→ Vercel 배포)
--   ⓘ ①과 ④ 사이에 **본 폴더(main)** 에서 `--check` 를 돌리면 api.get_daejeon_dong_closure 가 허용 목록 밖 공개 함수로
--     [사고]가 되고 get_data_freshness 가 정본과 달라 [사고]가 되는 것이 **정상**이다 — main 의 post_load.py·schema.sql 은
--     아직 옛 판이다. ④ 뒤에 사라진다.
--
-- 적용 뒤 확인 (dbx + anon 키로 **화면 요청 그대로**)
-- ------------------------------------------------
--   select oid::regprocedure, proconfig, prosecdef, provolatile from pg_proc
--    where proname = 'get_daejeon_dong_closure';     -- 두 줄(public·api) · 둘 다 prosecdef t · provolatile s
--   select has_table_privilege('anon', 'daejeon_dong_closure', 'select');   -- f (넷 다)
--   ② 적재 뒤: select status, dong_nm, quarters, clsbiz_sum, industries -> 0
--                from api.get_daejeon_dong_closure('<둔산2동 필지>');
--     → ok · 둔산2동 · 95·100·80·103·95(20251~20261) · 378 · {"induty_nm": "음식점업", "clsbiz_co": 111}
--   select src, basis, next_expected from api.get_data_freshness() where src = '동네 폐업 (대전시)';
--     → 동네 폐업 (대전시) | 2026-10-28 | 2027-01-28
--   anon 키:
--     POST /rest/v1/rpc/get_daejeon_dong_closure {"p_pnu":"<둔산2동 필지>"}      → 200 · [ok 한 줄]
--     POST /rest/v1/rpc/get_daejeon_dong_closure {"p_pnu":"1168010100107370000"}  → 200 · [not_daejeon 한 줄]
--
-- 되돌리기
-- --------
-- **새 마이그레이션 파일**로 (신선도 함수 먼저 → 표 나중 — 표부터 지우면 함수가 없는 표를 읽어 신선도 표가 통째로
-- 사라진다): `set lock_timeout = '5s'; begin;` →
--   ① 2026-10-18a_price_use_group.sql 의 get_data_freshness 정의 첫 줄부터 그 함수의 revoke 줄까지(comment 포함)를
--      글자 그대로(12번 줄이 없는 판)
--   ② drop function api.get_daejeon_dong_closure(text); drop function get_daejeon_dong_closure(text);
--   ③ drop table daejeon_closure_release; drop table daejeon_bjd_dong; drop table daejeon_pnu_dong;
--      drop table daejeon_dong_closure;
-- → `commit;` → `notify pgrst, 'reload schema';` 그리고 이 PR revert(정본 · post_load 허용 목록 34 → 33 · 화면 카드).
-- 화면은 함수가 없으면(PGRST202) 대전 카드가 옛 모양으로 선다. 적용된 이 파일은 고치지 않는다(원장).

set statement_timeout = '60s';
set lock_timeout = '5s';

begin;

-- =====================================================================
-- 표·함수: 대전시 동네 폐업 (2026-10-29a · 결정 0044)
-- =====================================================================
-- 대전광역시 상권분석 서비스(8989.daejeon.go.kr)가 내는 **행정동 × 업종(표준산업분류 소분류) × 월 폐업 수**를
-- 공표값 그대로 담고, 대전 건물의 개업·폐업 카드 자리에서 그 건물이 선 동의 분기별 폐업 건수를 보여 준다.
-- ⛔ 대전시는 개업 수를 내지 않는다 — 폐업만 싣는다 · 대전시 점포 수·폐업률(%)은 쓰지 않는다(👤 결정 0044 ⑤).
-- ⛔ 넣는 것은 가게 업종(씨앗 scripts/seeds/daejeon8989_industries.csv 의 y 33종) · 2025-01 이후 달만이다(적재기
--    scripts/collectors/load_daejeon8989_closure.py — 통째 교체 · 받은 날 표지 한 줄).
-- 표 넷은 전부 공개키에게 닫혀 있다(RLS 켬 + 정책 0 + 권한 회수) — 화면은 함수로만 읽는다.
-- 이 표들은 get_data_freshness 가 읽으므로(받은 날 표지) 그 함수보다 **앞**에 둔다.
create table if not exists daejeon_dong_closure (
  ym         text not null check (ym ~ '^\d{4}(0[1-9]|1[0-2])$'),
  dong_nm    text not null,
  induty_nm  text not null,
  clsbiz_co  int  not null check (clsbiz_co > 0),
  primary key (dong_nm, ym, induty_nm)
);

comment on table daejeon_dong_closure is
  '결정 0044 대전시 상권분석 서비스(8989.daejeon.go.kr) 행정동 월별 폐업 수 공표값 그대로 — (행정동, 달, 업종) 한 줄. '
  '가게 업종(씨앗 y 33종) · 2025-01 이후 달만 넣는다(적재기 load_daejeon8989_closure.py 가 통째 교체). '
  '공개키 읽기 금지 — 화면은 get_daejeon_dong_closure 로만 읽는다';
comment on column daejeon_dong_closure.ym is '폐업 년월 YYYYMM(원본 「폐업 년월」 그대로)';
comment on column daejeon_dong_closure.dong_nm is '행정동 이름(원본 「행정동 명」 그대로 — 대전시 자료에는 코드가 없다)';
comment on column daejeon_dong_closure.induty_nm is '업종 이름 — 한국표준산업분류 소분류(원본 「업종분류명(소분류)」 그대로 · 소진공 업종과 다르다)';
comment on column daejeon_dong_closure.clsbiz_co is '폐업 개수(원본 그대로 · 1 이상 — 0 인 줄은 원본에 없다)';

alter table daejeon_dong_closure enable row level security;

-- ⛔ Supabase 는 새 표를 anon 에 자동으로 연다(pg_default_acl) — 만든 자리에서 닫는다.
revoke all on daejeon_dong_closure from public, anon, authenticated;

-- 땅 → 행정동 지도 ⓐ — 소진공 대전 점포 csv 의 지번코드(= PNU)마다 점포가 가장 많은 행정동(동점이면 그 땅은 없다).
create table if not exists daejeon_pnu_dong (
  pnu      char(19) primary key,
  dong_nm  text not null
);

comment on table daejeon_pnu_dong is
  '결정 0044 땅(PNU) → 행정동 이름 ⓐ — 소진공 대전 점포 csv 의 지번코드마다 점포가 가장 많은 행정동(동점이면 뺀다). '
  '대전시 자료에는 행정동 이름만 있어 건물에 붙이는 다리다. 적재기가 폐업 표와 함께 통째 교체한다. 공개키 접근 0';

alter table daejeon_pnu_dong enable row level security;

revoke all on daejeon_pnu_dong from public, anon, authenticated;

-- 땅 → 행정동 지도 ⓑ — 법정동(PNU 앞 10자리)이 소진공 자료에서 행정동 하나로만 이어질 때만.
create table if not exists daejeon_bjd_dong (
  bjd_cd   char(10) primary key,
  dong_nm  text not null
);

comment on table daejeon_bjd_dong is
  '결정 0044 법정동(PNU 앞 10자리) → 행정동 이름 ⓑ — 소진공 대전 점포 csv 에서 그 법정동이 행정동 하나로만 이어질 때만. '
  'ⓐ(daejeon_pnu_dong)에 없는 땅의 대비책이다. 적재기가 통째 교체한다. 공개키 접근 0';

alter table daejeon_bjd_dong enable row level security;

revoke all on daejeon_bjd_dong from public, anon, authenticated;

-- 받은 날 표지 — 한 줄뿐. 함수의 창(받은 날의 달 − 6개월)과 신선도 줄(받은 날 + 3개월)이 이 칸을 읽는다.
create table if not exists daejeon_closure_release (
  id           int primary key default 1 check (id = 1),
  received_on  date not null,
  loaded_at    timestamptz not null default now()
);

comment on table daejeon_closure_release is
  '결정 0044 대전시 동네 폐업 받은 날 표지 — 한 줄뿐(id = 1). 사람이 대전시 사이트에서 한 달씩 받은 날(받은 날 폴더 이름)을 '
  '적재기가 폐업 표와 같은 트랜잭션에서 적는다. 0줄이면 get_daejeon_dong_closure 가 0줄을 준다(화면은 옛 카드 그대로). 공개키 접근 0';
comment on column daejeon_closure_release.received_on is
  '받은 날 — 창의 끝 = 이 날의 달 − 6개월(최근 6개월은 아직 덜 들어온다 · 👤 결정 0044 ③) · 신선도 다음 갱신 예정 = 이 날 + 3개월';

alter table daejeon_closure_release enable row level security;

revoke all on daejeon_closure_release from public, anon, authenticated;

-- 대전 건물의 개업·폐업 카드 자리(결정 0044 ①) — 그 건물이 선 행정동의 분기별 폐업 건수.
-- ⛔ 창 = 2025년 1분기부터, 세 달이 모두 「받은 날의 달 − 6개월」 이하인 분기만, 그중 최근 8분기 ·
--    업종 표 = 창의 최근 4분기 합. 적재기의 START_YM·LAG_MONTHS·MAX_QUARTERS·SUM_QUARTERS 와 같은 수다(시험이 대조).
-- ⛔ `p_pnu::char(19)` 캐스트를 지우지 말 것 — 칸이 char(19) 라 text 와 견주면 **칸 쪽**이 캐스트돼 색인이 죽는다.
create or replace function get_daejeon_dong_closure(p_pnu text)
returns table (
  status        text,
  dong_nm       text,
  received_on   date,
  quarters      jsonb,
  sum_quarters  jsonb,
  clsbiz_sum    int,
  industries    jsonb
)
language sql
stable
security definer
set search_path = public
as $$
  with const as (
    -- 👤 결정 0044 ③ — 2025-01 부터 · 최근 6개월은 뺀다 · 최근 8분기 · 업종 표 = 최근 4분기.
    select date '2025-01-01' as start_month, 6 as lag_months, 8 as max_quarters, 4 as sum_quarters
  ),
  rel as (
    -- 받은 날 표지. 0줄이면(아직 안 넣음) 이 함수도 0줄 — 화면은 옛 카드 그대로 선다.
    select r.received_on from daejeon_closure_release r
  ),
  me as (
    -- ⓐ 땅 → 동 먼저, 없으면 ⓑ 법정동 → 동. 둘 다 없으면 null → no_dong.
    select coalesce(
             (select m.dong_nm from daejeon_pnu_dong m where m.pnu = p_pnu::char(19)),
             (select b.dong_nm from daejeon_bjd_dong b where b.bjd_cd = left(p_pnu::char(19), 10)::char(10))
           ) as dong_nm
  ),
  win as (
    -- 분기 시작 달마다 — 마지막 달(시작 + 2개월)이 「받은 날의 달 − 6개월」 이하인 것만 = 시작이
    -- 「받은 날의 달 − 8개월」 이하. 그중 최근 max_quarters 개.
    select q.qs
    from rel cross join const c
    cross join lateral generate_series(c.start_month::timestamp,
                                       date_trunc('month', rel.received_on::timestamp)
                                         - make_interval(months => c.lag_months + 2),
                                       interval '3 months') as q(qs)
    order by q.qs desc
    limit (select c2.max_quarters from const c2)
  ),
  wq as (
    -- 분기 코드는 서울 개업·폐업 카드와 같은 'YYYYQ' 다섯 자리(화면이 같은 글로 읽는다).
    select w.qs,
           to_char(w.qs, 'YYYY') || extract(quarter from w.qs)::int::text as quarter,
           row_number() over (order by w.qs desc) <= (select c.sum_quarters from const c) as recent
    from win w
  ),
  hits as (
    -- 이 동 · 창 안 세 달의 폐업 줄(표에는 0 인 줄이 없다 — 빈 분기는 아래에서 0 으로 채운다).
    select q.quarter, q.recent, d.induty_nm, d.clsbiz_co
    from wq q
    cross join me
    join daejeon_dong_closure d
      on d.dong_nm = me.dong_nm
     and d.ym between to_char(q.qs, 'YYYYMM') and to_char(q.qs + interval '2 months', 'YYYYMM')
  ),
  st as (
    -- 판정 순서가 곧 뜻이다: 대전이 아님 → 동을 못 찾음 → ok.
    select case
             when left(p_pnu::char(19), 2) is distinct from '30' then 'not_daejeon'
             when me.dong_nm is null then 'no_dong'
             else 'ok'
           end as status,
           me.dong_nm
    from me
  )
  select s.status,
         case when s.status = 'ok' then s.dong_nm end,
         r.received_on,
         -- 창 전부(옛 → 새) · 폐업이 없던 분기도 0 으로(빠진 것이 아니라 0 건이다 — 원본은 0 인 줄을 안 낸다).
         case when s.status = 'ok' then
           (select coalesce(jsonb_agg(jsonb_build_object(
                     'quarter',   q.quarter,
                     'clsbiz_co', (select coalesce(sum(h.clsbiz_co), 0) from hits h where h.quarter = q.quarter))
                   order by q.qs), '[]'::jsonb)
              from wq q) end,
         -- 업종 표·큰 숫자가 더한 분기(창의 최근 4분기 · 옛 → 새).
         case when s.status = 'ok' then
           (select coalesce(jsonb_agg(q.quarter order by q.qs), '[]'::jsonb) from wq q where q.recent) end,
         case when s.status = 'ok' then
           (select coalesce(sum(h.clsbiz_co), 0)::int from hits h where h.recent) end,
         -- 업종별 최근 4분기 합 — 많은 순(같으면 이름 순) · 0 건 업종은 줄이 없다.
         case when s.status = 'ok' then
           (select coalesce(jsonb_agg(jsonb_build_object('induty_nm', i.induty_nm, 'clsbiz_co', i.n)
                                      order by i.n desc, i.induty_nm collate "C"), '[]'::jsonb)
              from (select h.induty_nm, sum(h.clsbiz_co)::int as n
                      from hits h
                     where h.recent
                     group by h.induty_nm) i) end
  from st s
  cross join rel r;
$$;

comment on function get_daejeon_dong_closure(text) is
  '결정 0044(2026-10-29a) 대전 건물의 개업·폐업 카드 자리 — 그 건물이 선 행정동(ⓐ 땅 → 동 · 없으면 ⓑ 법정동 → 동)의 '
  '대전시 공표 폐업 건수(가게 업종 33종). 창 = 2025년 1분기부터 세 달이 모두 「받은 날의 달 − 6개월」 이하인 분기 · 최근 8분기 '
  '(quarters — 옛 → 새 · 폐업 0 인 분기도 0) · 업종 표와 clsbiz_sum 은 창의 최근 4분기(sum_quarters) 합 · industries 는 많은 순 · '
  '0 건 업종 없음. status = not_daejeon(대전 밖) · no_dong(동을 못 찾음) · ok — ok 가 아니면 숫자 칸은 null. '
  '받은 날 표지가 0줄이면 0줄. 개업 수·점포 수·폐업률은 없다(대전시가 개업 수를 내지 않는다 · 결정 0044 ⑤). '
  'security definer (표 넷이 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. 나가는 것은 행정동 이름·업종 이름·공표 폐업 수뿐이다).';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function get_daejeon_dong_closure(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.get_daejeon_dong_closure(p_pnu text)
returns table (
  status        text,
  dong_nm       text,
  received_on   date,
  quarters      jsonb,
  sum_quarters  jsonb,
  clsbiz_sum    int,
  industries    jsonb
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.get_daejeon_dong_closure(p_pnu) $$;

revoke all on function api.get_daejeon_dong_closure(text) from public, anon, authenticated;
grant execute on function api.get_daejeon_dong_closure(text) to anon, authenticated;

-- ⛔ public.get_daejeon_dong_closure 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.

-- ── ③ 신선도 표 12번 줄(대전시 동네 폐업) ─────────────────────────────────────
-- 받은 날 표지(위 ①)를 읽으므로 표 **뒤**에 다시 만든다.
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
           (select r.published_ym::text from snapshot_release r) as basis,
           'sangkwon'::text             as rule_kind,
           '분기마다 (다음 분기 자료가 공개되면 사람이 적재)'::text as cadence
    union all
    -- 2026-10-15a — 실거래는 매달 최근 6개월을 다시 받는다(사장님 결정 2026-10-15 · 규칙 'tx').
    select 2, '실거래 (매매)', '계약월',
           (select max(t.contract_ym)::text from transaction t),
           'tx',
           '월 1회 (최근 6개월 다시 받기)'
    union all
    -- 2026-10-15a — 기준은 적재일(max(building.updated_at))이 아니라 표지의 판이다(30개 구를 다 넣은 뒤
    --   사람이 올린다). 규칙은 인허가와 같은 월간 갈래 — 건축HUB 일괄 파일도 다음 달 20일 무렵 게시된다.
    select 3, '건축물대장', '판',
           (select r.release_ym::text from ledger_release r),
           'permit',
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
    -- ⓘ 9번(옛 성적표 줄)은 2026-10-18a(결정 0041)에 뺐다 — 뒤 번호는 그대로 둔다(순서만 정하는 칸이다).
    -- 2026-10-12b — 기준은 우리가 받아 둔 날(updated_at)이 아니라 개별공시지가의 공시 연도다
    --   (사장님 결정 2026-10-12). smallint 라 '2026' 네 자리로 나온다.
    select 10, '필지 (토지 특성)', '공시 연도',
           (select max(t.land_price_year)::text from parcel t),
           'land_year',
           '연 1회 (브이월드)'
    union all
    -- 결정 0033 — 서울시 상권분석서비스 개업·폐업. 분기 꼴이 'YYYYQ' 다섯 자리(Q 없음)다.
    select 11, '상권 개업·폐업 (서울시)', '분기',
           (select max(t.quarter)::text from district_openclose t),
           'seoul_openclose',
           '분기마다'
    union all
    -- 2026-10-29a(결정 0044) — 대전시 동네 폐업. 기준 = 사람이 대전시 사이트에서 받은 날(표지 한 줄)이다.
    select 12, '동네 폐업 (대전시)', '받은 날',
           (select r.received_on::text from daejeon_closure_release r),
           'daejeon_closure',
           '분기마다 (사람이 대전시 사이트에서 받음)'
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
           -- 월간 자료(인허가 기준월 · 건축물대장 판): 다음 판이 **공개되는 달**의 말일(기준월 + 3개월 - 하루).
           when n.rule_kind = 'permit' and n.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
             then (to_date(n.basis, 'YYYYMM') + interval '3 months' - interval '1 day')::date
           -- 실거래: 계약월 + 2개월 - 하루(사장님 결정 2026-10-15 — 매달 최근 6개월을 다시 받는다).
           when n.rule_kind = 'tx' and n.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
             then (to_date(n.basis, 'YYYYMM') + interval '2 months' - interval '1 day')::date
           -- 연 1회: 다음 해 3월 31일(국세청 고시가 매년 3월).
           when n.rule_kind = 'nts' and n.basis ~ '^\d{4}-\d{2}-\d{2}$'
             then make_date(left(n.basis, 4)::int + 1, 3, 31)
           -- 연 1회: 개별공시지가는 공시 연도의 다음 해 6월 30일(사장님 결정 2026-10-12).
           --   네 자리 연도일 때만 — 모양이 다르면 ::int 가 터져 표가 통째로 사라진다.
           when n.rule_kind = 'land_year' and n.basis ~ '^\d{4}$'
             then make_date(n.basis::int + 1, 6, 30)
           -- 대전시 동네 폐업: 받은 날 + 3개월(분기마다 사람이 받는다 — 2026-10-29a · 결정 0044).
           --   'YYYY-MM-DD' 일 때만 — 모양이 다르면 ::date 가 터져 표가 통째로 사라진다.
           when n.rule_kind = 'daejeon_closure' and n.basis ~ '^\d{4}-\d{2}-\d{2}$'
             then (n.basis::date + interval '3 months')::date
         end as next_expected,
         n.cadence
  from norm n
  order by n.ord;
$$;

comment on function get_data_freshness() is
  '화면 아래 "이 자료는 언제 것인가" 표. 열한 갈래 자료의 가장 최근 도장(분기·계약월·판·'
  '계산일·수집일·기준월·고시일·공시 연도·받은 날)을 창고에서 읽어 한 줄씩 준다. '
  '⛔ 숫자를 화면에 박지 않기 위한 함수다 — 신선도를 글자로 적어 두면 적재하는 순간부터 '
  '그 글자만 거짓말을 한다. next_expected 도 사람이 적는 값이 아니라 규칙으로 계산한다: '
  '분기 자료는 분기말 달 + 5개월 - 하루(다음 분기가 공개되는 달의 말일 — 분기 꼴 셋 '
  '''YYYYMM''·''YYYYQn''·''YYYYQ''(서울시 다섯 자리)를 같은 분기말 달로 맞춘 뒤 한 번만 계산), 월간 자료'
  '(인허가 기준월·건축물대장 판)는 기준월 + 3개월 - 하루(다음 판이 공개되는 달의 말일), 실거래는 계약월 + '
  '2개월 - 하루(매달 최근 6개월을 다시 받는다), 국세청 기준시가는 고시일의 다음 해 3월 31일, '
  '필지(개별공시지가)는 공시 연도의 다음 해 6월 30일(기준값이 네 자리 연도일 때만), 대전시 동네 폐업은 '
  '받은 날 + 3개월(분기마다 사람이 받는다 · 기준값이 YYYY-MM-DD 일 때만). '
  '주기가 없는 자료는 null 이다 — 없는 주기를 지어내면 "늦었다"는 거짓 신호가 뜬다. '
  '기준값이 그 모양이 아니면 계산하지 않고 그 칸만 비운다(to_date 가 터지면 표가 통째로 '
  '사라진다). timestamptz 는 전부 Asia/Seoul 로 옮겨 날짜를 자른다 — 이 DB 가 UTC 라 '
  '그냥 자르면 한국 새벽 0~9시에 어제 날짜가 찍힌다. '
  '⛔ api_quota_log 는 안 본다 — 그건 우리 호출 장부이지 자료의 나이가 아니고, 하한선일 뿐이다. '
  '자료가 0행이면 basis 가 null 이고 줄은 그대로 나온다(화면이 "자료 없음"이라 적는다 — '
  '줄을 빼면 "그런 자료를 안 쓴다"로 읽힌다). '
  'security definer (열한 표가 전부 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 집계 도장 열한 개뿐이고 원본 행은 한 줄도 안 나간다). 2026-09-05d · 월간 규칙 2026-10-01a · '
  '서울 개업·폐업 2026-10-05b · 필지 공시 연도 2026-10-12b · 실거래·대장 판 월간 규칙 2026-10-15a · '
  '성적표 줄 뺌 2026-10-18a(결정 0041) · 대전시 동네 폐업 2026-10-29a(결정 0044)';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function get_data_freshness() from public, anon, authenticated;

commit;

notify pgrst, 'reload schema';
