-- =====================================================================
-- 2026-11-01a — 이 자리 가게 이력 (결정 0045 PR④ · 표 둘 + 함수 + 신선도 16번 줄)
-- =====================================================================
--
-- 왜
-- --
-- 손님이 「이 자리에 전에 무슨 가게가 있었나」를 묻는다. DB 의 점포 표 unit_business 는 최근 4분기만 둔다
-- (2026-10-28 👤 「4분기 보관」) — 옛 분기를 DB 에 쌓지 않고, 로컬에 받아 둔 소진공 상가(상권)정보 zip(2015Q4~
-- 분기마다 하나 · 43개)을 한 번 읽어 가게마다 한 줄의 결과표(약 130MB)만 넣는다(👤 결정 0045 ⑤-1 — 2017Q4 이후).
-- 열쇠는 상가업소번호 + 같은 땅·층·상호(⑤-2 · 함정 5 ①~⑥) — 조사 C(2026-10-31) 재현이 이 판의 근거다.
--
-- 무엇이 생기나 (새 객체 + 신선도 함수 한 줄 + 옛 칸 설명 하나 — 기존 표의 행·칸은 한 글자도 안 바꾼다)
-- ---------------------------------------------------------------------------------------------
--   ① 표 둘 — store_history(가게 사슬 한 줄 · PK (biz_no_last, last_ym) · 색인 (pnu, is_current desc, seen_cnt desc)) ·
--      store_history_release(표지 한 줄 · last_ym · 빌드 날 · 줄 수). 둘 다 RLS 켬 + 권한 회수(공개키 0).
--      적재는 scripts/collectors/load_store_history.py(통째 교체 · 한 트랜잭션 · 관문 ⒜~⒦).
--   ② 함수 get_store_history(p_pnu text, p_limit int default 20, p_offset int default 0) + api 쌍둥이 — 그 땅의 가게 줄
--      (지금 보임 → 보인 분기 수 ↓ → 층) · 넘기기 · total_cnt · history_last_ym · 표지 0줄이면 0줄 · 줄 없으면 no_data 한 줄.
--      공개 호출 허용 총계 36 → 37(post_load.py ANON_CALLABLE_ALLOWLIST).
--   ③ get_data_freshness 다시 만들기 — 16번 줄 「가게 이력 (점포 자료 누적)」(기준 = 표지 last_ym · 점포 줄과 같은
--      'sangkwon' 규칙 · 새 규칙 0) · comment 「열다섯」. 나머지 열다섯 줄·규칙은 글자 그대로다.
--      ⓘ api.get_data_freshness 는 다시 만들지 않는다 — 통과 함수라 본문이 그대로다(2026-10-29a 와 같은 판단).
--   ④ unit_business.biz_no 칸 설명 정정 — 옛 글 「업종분류 개편 시 번호가 새로 생성되어 연계 불가」는 조사 C 실측
--      (이웃 분기 95~99% 같은 번호)과 어긋난다.
-- ⛔ 머리(language · stable · security definer · set search_path)와 comment 는 정본(schema.sql)과 글자 그대로다 —
--    tests/test_store_history_migration.py 가 대조한다(CLAUDE.md ⛔ 2026-10-01a).
-- ⛔ 서명은 하나뿐이다(이름당 pg_proc 1 · 인자 (text, integer, integer)).
--
-- 잠금
-- ----
-- 새 표·색인·함수 만들기는 기존 표를 잠그지 않는다. ④ 의 COMMENT ON 은 SHARE UPDATE EXCLUSIVE 다(PostgreSQL 문서
-- 13.3 Explicit Locking — "SHARE UPDATE EXCLUSIVE … Acquired by VACUUM (without FULL), ANALYZE, CREATE INDEX
-- CONCURRENTLY, CREATE STATISTICS, COMMENT ON, …" · 2026-10-31 확인) — ACCESS EXCLUSIVE 가 아니라 읽기·쓰기를 막지
-- 않는다(같은 표의 VACUUM·ANALYZE 와만 부딪힌다). 그래도 형제 관습대로 `lock_timeout` 은 **begin 앞**(세션 설정)에 둔다 —
-- 오래 못 잡으면 줄 서지 않고 실패한다(통째 롤백 · 다시 돌리면 된다 · 전부 멱등).
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 중간에 끊기면 신선도 함수가 없는 표를 읽거나 api 쌍둥이 없이 원본만 남는다.
-- `notify pgrst` 는 commit **뒤**.
--
-- 실행 순서 (Claude 가 dbx 로 · 사장님께 여쭌 뒤 · ⚠️ 순서가 곧 안전장치다)
-- ------------------------------------------------------------------------
--   1) python scripts/dbx.py -f supabase/migrations/2026-11-01a_store_history.sql
--      (적용 전엔 신선도 16번 줄이 없고, 적용 뒤 적재 전엔 '자료 없음'(basis null) — 같은 날 아래를 잇는다)
--   2) python scripts/build_store_history.py --zip-dir <원본 zip 폴더>   — 약 15분 · DB 0 · 결과는 data/derived/store_history/
--   3) 적재 **전** 디스크 판정 — (지금 사용량 + 약 130MB + WAL 여유 1GB) 가 디스크의 85% 미만일 때만(넘으면 확장부터)
--   4) python scripts/collectors/load_store_history.py --dry-run → 실적재(관문 ⒦: 결과표 마지막 분기 =
--      snapshot_release.loaded_ym 이 아니면 통째 롤백)
--   5) python scripts/post_load.py → python scripts/post_load.py --check — 0 이어야 한다(허용 목록 총계 37 · 정본↔라이브
--      함수 일치 · 「가게 이력 표지 = 보여 주는 분기」 [정상])
--   ⛔ 상권 202609·R-ONE·개업·폐업·실거래·건축물대장 적재와 **같은 날 넣지 않는다**(디스크·WAL 이 한 번에 몰린다).
--   ⓘ 상권 202609 가 먼저 오면 그 분기 전국 모드 적재 → 2) 빌드가 zip 44개를 읽는다(운영 순서: 새 분기 적재 → 빌드 →
--     이력 적재 → post_load — 결정 0045 「가게 이력 — 결정 0035 표지의 예외」).
--   ⓘ 1)과 머지 사이에 **본 폴더(main)** 에서 `--check` 를 돌리면 api.get_store_history 가 허용 목록 밖 공개 함수로
--     [사고]가 되고 get_data_freshness 가 정본과 달라 [사고]가 되는 것이 **정상**이다 — 그 창은 PR 가지 판으로 잰다.
--
-- 적용 뒤 확인 (dbx + anon 키로 **화면 요청 그대로**)
-- ------------------------------------------------
--   select oid::regprocedure, proconfig, prosecdef, provolatile from pg_proc
--    where proname = 'get_store_history';                          -- 두 줄(public·api) · 둘 다 prosecdef t · provolatile s
--   select has_table_privilege('anon', 'store_history', 'select'),
--          has_table_privilege('anon', 'store_history_release', 'select');   -- f · f
--   4) 적재 뒤: select status, floor_no, biz_name, first_ym, last_ym, seen_cnt, is_current, total_cnt, history_last_ym
--                from api.get_store_history('<서울 필지 19자리>', 5, 0);   → ok 줄 ≤ 5 · total_cnt 같은 값 · 202606
--   select src, basis, next_expected from api.get_data_freshness() where src = '가게 이력 (점포 자료 누적)';
--     → 가게 이력 (점포 자료 누적) | 202606 | 2026-10-31
--   anon 키:
--     POST /rest/v1/rpc/get_store_history {"p_pnu":"<서울 필지>"}            → 200 · [ok 줄들]
--     POST /rest/v1/rpc/get_store_history {"p_pnu":"1168010100199990000"}   → 200 · [no_data 한 줄]
--
-- 되돌리기
-- --------
-- **새 마이그레이션 파일**로 (신선도 함수 먼저 → 표 나중 — 표부터 지우면 함수가 없는 표를 읽어 신선도 표가 통째로
-- 사라진다): `set lock_timeout = '5s'; begin;` →
--   ① 2026-10-31a_seoul_trdar.sql 의 get_data_freshness 정의 첫 줄부터 그 함수의 revoke 줄까지(comment 포함)를
--      글자 그대로(16번 줄이 없는 판)
--   ② drop function api.get_store_history(text, integer, integer); drop function get_store_history(text, integer, integer);
--   ③ drop table store_history_release; drop table store_history;
--   ④ comment on column unit_business.biz_no is '업종분류 개편(837→247) 시 번호가 새로 생성되어 과거와 연계 불가. 주소+상호명 재매칭 필요';
-- → `commit;` → `notify pgrst, 'reload schema';` 그리고 이 PR revert(정본 · post_load 허용 목록 37 → 36 · 화면 상수).
-- 적용된 이 파일은 고치지 않는다(원장).

set statement_timeout = '60s';
set lock_timeout = '5s';

begin;

-- =====================================================================
-- 표·함수: 이 자리 가게 이력 (2026-11-01a · 결정 0045 PR④)
-- =====================================================================
-- 소진공 상가(상권)정보 분기 자료(2017Q4~ · 서울+대전)를 **로컬 zip 에서 한 번 읽어**(scripts/build_store_history.py)
-- 가게(사슬)마다 한 줄로 담는다. 옛 분기는 DB 에 두지 않는다(unit_business 는 최근 4분기 보관 · 2026-10-28) —
-- 결과표만 적재기(scripts/collectors/load_store_history.py · 통째 교체 · 한 트랜잭션)가 넣는다.
-- 열쇠 규칙(👤 결정 0045 함정 5): ① 상가업소번호로 잇는다 ② 번호가 끝난 사슬은 다음 분기 새 번호 중 같은
--   (pnu, 층, 정규화 상호)가 정확히 하나일 때만(끝난 쪽도 하나) ③ 층 모름이면 안 잇는다 ④ 정규화 = 공백 제거 +
--   전각→반각 ⑤ 값은 마지막 분기 값 ⑥ 한 분기라도 빠지면 새 사슬.
-- ⛔ seen_cnt 는 「자료에 보인 분기 수」이지 영업 기간이 아니다 · 지금 안 보임 ≠ 폐업 · 옛 상호 ≠ 그 시절 간판.
-- 두 표는 공개키에게 닫혀 있다(RLS 켬 + 정책 0 + 권한 회수) — 화면은 get_store_history 로만 읽는다.
-- 표지 store_history_release 를 get_data_freshness 가 읽으므로 그 함수보다 **앞**에 둔다.
create table if not exists store_history (
  pnu          char(19) not null,
  floor_no     smallint check (floor_no is null or floor_no <> 0),
  biz_name     text not null,
  biz_no_last  text not null,
  first_ym     char(6) not null check (first_ym ~ '^\d{4}(03|06|09|12)$'),
  last_ym      char(6) not null check (last_ym ~ '^\d{4}(03|06|09|12)$'),
  seen_cnt     smallint not null check (seen_cnt >= 1),
  is_current   boolean not null,
  n_links      smallint not null default 0 check (n_links >= 0),
  truncated    boolean not null,
  primary key (biz_no_last, last_ym),
  check (first_ym <= last_ym)
);

-- 함수가 땅 하나의 줄을 「지금 보임 → 보인 분기 수」 차례로 꺼낸다.
create index if not exists idx_store_history_pnu on store_history (pnu, is_current desc, seen_cnt desc);

comment on table store_history is
  '결정 0045 PR④ 이 자리 가게 이력 — 소진공 상가(상권)정보 분기 자료(2017Q4~ · 서울+대전)를 로컬 zip 에서 한 번 읽어 '
  '가게(사슬)마다 한 줄(scripts/build_store_history.py → load_store_history.py 가 통째 교체). '
  '「N분기 보임」은 자료에 보인 분기 수이지 영업 기간이 아니다 · 안 보임 ≠ 폐업 · 빠졌다 돌아온 번호는 새 사슬. '
  '열쇠 = 상가업소번호(①) + 번호가 끝난 사슬만 같은 땅·층·정규화 상호가 양쪽 다 정확히 하나일 때 잇는다(②~⑥). '
  '주 열쇠 = (마지막 번호, 마지막 분기) — 한 분기에 같은 번호는 한 줄이라 늘 다르다. 같은 가게가 번호 둘로 동시에 올라 있다 '
  '한쪽만 돌아오면 같은 first_ym 줄이 둘 날 수 있다(자료 성질 · 10-31 빌드 17건 + 본사 번호 이동 2건). '
  '공개키 읽기 금지 — 화면은 get_store_history 로만 읽는다';
comment on column store_history.floor_no is '마지막 분기의 층(정수 · 지하 음수 · 옥탑 99 · 모름 null — 0 없음 · 절대 규칙 4)';
comment on column store_history.biz_name is '마지막 분기의 상호(원문 그대로)';
comment on column store_history.biz_no_last is '마지막 분기의 상가업소번호(보조 열쇠로 이었으면 새 번호)';
comment on column store_history.first_ym is '처음 보인 분기 YYYYMM(분기말 달) — 201712 이면 그 전은 모른다(truncated)';
comment on column store_history.last_ym is '마지막으로 보인 분기 YYYYMM(분기말 달)';
comment on column store_history.seen_cnt is '자료에 보인 분기 수(사슬은 끊김이 없어 first~last 분기 수와 같다) — 영업 기간이 아니다';
comment on column store_history.is_current is '결과표의 마지막 분기에 보이는가';
comment on column store_history.n_links is '보조 열쇠(같은 땅·층·정규화 상호)로 이은 횟수';
comment on column store_history.truncated is 'first_ym 이 결과표의 첫 분기(201712)인가 — 그 전 기록은 읽지 않았다';

alter table store_history enable row level security;

-- ⛔ Supabase 는 새 표를 anon 에 자동으로 연다(pg_default_acl) — 만든 자리에서 닫는다.
revoke all on store_history from public, anon, authenticated;

-- 가게 이력 표지 — 한 줄뿐(id = 1). 적재기가 통째 교체와 같은 트랜잭션에서 적는다.
create table if not exists store_history_release (
  id         smallint primary key check (id = 1),
  first_ym   char(6) not null check (first_ym ~ '^\d{4}(03|06|09|12)$'),
  last_ym    char(6) not null check (last_ym ~ '^\d{4}(03|06|09|12)$'),
  built_on   date not null,
  row_cnt    integer not null,
  loaded_at  timestamptz not null default now(),
  check (first_ym <= last_ym)
);

comment on table store_history_release is
  '결정 0045 PR④ 가게 이력 표지 — 한 줄뿐(id = 1). first_ym = 결과표의 첫 분기(201712 — 화면 「○년 ○분기~」) · '
  'last_ym = 결과표의 마지막 분기 · built_on = 로컬에서 구운 날 · '
  'row_cnt = 넣은 줄 수. 신선도 16번 줄과 post_load --check 가 읽는다 · snapshot_release.published_ym 과 같아야 정상'
  '(다르면 --check [주의] — 새 분기 적재 뒤 다시 굽고 넣는다). 0줄이면 get_store_history 도 0줄. 공개키 읽기 금지';

alter table store_history_release enable row level security;

-- ⛔ Supabase 는 새 표를 anon 에 자동으로 연다(pg_default_acl) — 만든 자리에서 닫는다.
revoke all on store_history_release from public, anon, authenticated;

-- 땅(필지) 하나의 가게 줄 — 지금 보임 → 보인 분기 수 ↓ → 층 차례 · 넘기기(p_limit 1~100 · p_offset 0 이상).
--   표지가 0줄이면(적재 전) 0줄 — 화면은 카드째 숨긴다. 그 땅에 줄이 없으면 status 'no_data' 한 줄(total_cnt 0).
create or replace function get_store_history(p_pnu text, p_limit int default 20, p_offset int default 0)
returns table (
  status           text,
  floor_no         smallint,
  biz_name         text,
  first_ym         char(6),
  last_ym          char(6),
  seen_cnt         smallint,
  is_current       boolean,
  truncated        boolean,
  total_cnt        integer,
  current_cnt      integer,
  history_first_ym char(6),
  history_last_ym  char(6)
)
language sql
stable
security definer
set search_path = public
as $$
  with pa as (
    -- 넘기기 인자 — 한 번에 1~100줄 · 음수 offset 은 0(넘치는 인자로 표를 통째로 긁지 못하게).
    -- offset 상한 2,000,000 — 한 땅 최대 줄 수(10-31 빌드 1,951)보다 넉넉히 크고, 아래 셈(off + lim)이 정수를 넘지 않게
    --   (p_offset 2147483647 에서 22003 정수 넘침 — 보완 2 G-2).
    select least(greatest(coalesce(p_limit, 20), 1), 100) as lim,
           least(greatest(coalesce(p_offset, 0), 0), 2000000) as off
  ),
  rel as (
    -- 표지. 0줄이면(아직 안 넣음) 이 함수도 0줄.
    select r.first_ym, r.last_ym from store_history_release r
  ),
  mine as (
    -- ⛔ char(19) 로 견준다 — text 로 견주면 칸이 캐스트돼 색인이 죽는다.
    select h.floor_no, h.biz_name, h.first_ym, h.last_ym, h.seen_cnt, h.is_current, h.truncated,
           row_number() over (order by h.is_current desc, h.seen_cnt desc, h.floor_no asc nulls last,
                                       h.biz_name, h.biz_no_last, h.last_ym) as rn
    from store_history h
    where h.pnu = p_pnu::char(19)
  ),
  cnt as (
    select count(*)::int as n, (count(*) filter (where mine.is_current))::int as n_cur from mine
  )
  select case when c.n = 0 then 'no_data' else 'ok' end,
         m.floor_no, m.biz_name, m.first_ym, m.last_ym, m.seen_cnt, m.is_current, m.truncated,
         c.n,
         c.n_cur,
         r.first_ym,
         r.last_ym
  from rel r
  cross join cnt c
  cross join pa
  left join mine m on m.rn > pa.off and m.rn <= pa.off::bigint + pa.lim
  where c.n = 0 or m.rn is not null
  order by m.rn;
$$;

comment on function get_store_history(text, integer, integer) is
  '결정 0045 PR④ 이 자리 가게 이력 — 그 땅(필지)의 가게 줄(건물 값이 아니라 그 땅에 보인 점포 줄). 줄 = 마지막 층·상호·'
  '처음/마지막 보인 분기·보인 분기 수·지금 보임·첫 분기부터인가(truncated). 차례 = 지금 보임 → 보인 분기 수 ↓ → 층(모름 끝) → '
  '상호. 넘기기 p_limit(1~100 으로 자름 · 기본 20) · p_offset(음수면 0 · 상한 2,000,000 — 넘치는 인자로 정수 넘침이 나지 않게). total_cnt = 그 땅 줄 전체 수(모든 줄에 같은 값) · '
  'current_cnt = 그 땅에서 지금 보이는 줄 수(모든 줄에 같은 값 · no_data 면 0) · history_first_ym·history_last_ym = 표지의 첫·마지막 분기. 표지가 0줄이면 0줄(적재 전 — 화면은 카드째 숨김) · 그 땅에 줄이 없으면 '
  'status no_data 한 줄(total_cnt 0). D등급 — 「N분기 보임」은 자료에 보인 분기 수이지 영업 기간이 아니고, 지금 안 보이는 '
  '가게도 문을 닫았다는 뜻이 아닐 수 있다. security definer (표 둘이 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 그 땅의 층·상호·분기 수뿐이고 상가업소번호는 안 나간다).';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function get_store_history(text, integer, integer) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.get_store_history(p_pnu text, p_limit int default 20, p_offset int default 0)
returns table (
  status           text,
  floor_no         smallint,
  biz_name         text,
  first_ym         char(6),
  last_ym          char(6),
  seen_cnt         smallint,
  is_current       boolean,
  truncated        boolean,
  total_cnt        integer,
  current_cnt      integer,
  history_first_ym char(6),
  history_last_ym  char(6)
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.get_store_history(p_pnu, p_limit, p_offset) $$;

revoke all on function api.get_store_history(text, integer, integer) from public, anon, authenticated;
grant execute on function api.get_store_history(text, integer, integer) to anon, authenticated;

-- ⛔ public.get_store_history 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.

-- ── 점포 번호 칸 설명 정정(조사 C 실측) ───────────────────────────────────────
comment on column unit_business.biz_no is '상가업소번호. 이웃 분기 사이 95~99% 가 같은 번호로 이어진다(2026-10-31 조사 C · 서울·대전) — 가게 이력(store_history · 결정 0045 PR④)의 주 열쇠. 끊기는 자리 셋: 2017Q3 번호 체계 단절(그 분기는 읽지 않는다) · 2024Q4 대량 재발급(이웃 분기 겹침 대전 0.788·서울 0.761 — 층 모름 줄은 보조 열쇠로 못 이어 같은 가게가 두 줄로 나뉠 수 있다) · 분기당 약 1% 재발급(보조 열쇠 = 같은 땅·층·정규화 상호로 잇는다 · scripts/build_store_history.py). 대전 번호 65% 에 박힌 20220806 은 발급일 도장이지 시계열이 끊기는 자리가 아니다(2015Q4 파일에도 있다). 옛 글 「업종분류 개편 시 번호가 새로 생성되어 연계 불가」는 실측과 어긋나 2026-11-01a 에 고쳤다.';

-- ── 신선도 표 16번 줄(가게 이력) ─────────────────────────────────────────────
-- 표지 store_history_release(위)를 읽으므로 표 **뒤**에 다시 만든다.
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
    union all
    -- 2026-10-31a(결정 0045) — 서울시 상권분석서비스 추정매출·길단위인구. 분기 꼴은 개업·폐업과 같은 'YYYYQ' 라
    --   같은 규칙(seoul_openclose — 분기말 + 5개월 - 하루)을 쓴다.
    select 13, '상권 추정매출 (서울시)', '분기',
           (select max(t.quarter)::text from district_sales t),
           'seoul_openclose',
           '분기마다'
    union all
    select 14, '상권 길단위인구 (서울시)', '분기',
           (select max(t.quarter)::text from district_pop_flow t),
           'seoul_openclose',
           '분기마다'
    union all
    -- 2026-10-31a(결정 0045 · 사장님 결정 10-31 「다음 예정 없음」) — 상주·직장인구는 한 줄. 기준 = 값이 마지막으로
    --   바뀐 분기 둘을 글로 합친다(표지 seoul_trdar_release). 서울시 공지는 연 1회지만 실제 갱신이 불규칙(상주
    --   2024·2025 건너뜀)이라 예정일을 계산하지 않는다('none' → null). 표지가 비면 basis 도 null(화면 '자료 없음').
    select 15, '상권 상주·직장인구 (서울시)', '값이 바뀐 분기',
           (select '상주 ' || left(a.value_quarter, 4) || '년 ' || right(a.value_quarter, 1) || '분기, 직장 '
                   || left(b.value_quarter, 4) || '년 ' || right(b.value_quarter, 1) || '분기'
              from seoul_trdar_release a, seoul_trdar_release b
             where a.tbl = 'district_pop_resident' and b.tbl = 'district_pop_worker'),
           'none',
           '연 1회 (서울시 공지) · 실제는 불규칙 — 예정일 계산 안 함'
    union all
    -- 2026-11-01a(결정 0045 PR④) — 가게 이력 결과표의 마지막 분기. 점포 줄(ord 1)과 같은 `sangkwon` 규칙 — 같은 분기면
    --   같은 날 「지났습니다」가 뜬다(정상 · 새 분기 적재 → 빌드 → 적재 순서). 표지가 비면 basis null(화면 '자료 없음').
    select 16, '가게 이력 (점포 자료 누적)', '분기',
           (select r.last_ym::text from store_history_release r),
           'sangkwon',
           '분기마다 (새 분기 점포 자료를 적재한 뒤 다시 굽는다)'
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
  '화면 아래 "이 자료는 언제 것인가" 표. 열다섯 갈래 자료의 가장 최근 도장(분기·계약월·판·'
  '계산일·수집일·기준월·고시일·공시 연도·받은 날·값이 바뀐 분기)을 창고에서 읽어 한 줄씩 준다. '
  '⛔ 숫자를 화면에 박지 않기 위한 함수다 — 신선도를 글자로 적어 두면 적재하는 순간부터 '
  '그 글자만 거짓말을 한다. next_expected 도 사람이 적는 값이 아니라 규칙으로 계산한다: '
  '분기 자료는 분기말 달 + 5개월 - 하루(다음 분기가 공개되는 달의 말일 — 분기 꼴 셋 '
  '''YYYYMM''·''YYYYQn''·''YYYYQ''(서울시 다섯 자리)를 같은 분기말 달로 맞춘 뒤 한 번만 계산), 월간 자료'
  '(인허가 기준월·건축물대장 판)는 기준월 + 3개월 - 하루(다음 판이 공개되는 달의 말일), 실거래는 계약월 + '
  '2개월 - 하루(매달 최근 6개월을 다시 받는다), 국세청 기준시가는 고시일의 다음 해 3월 31일, '
  '필지(개별공시지가)는 공시 연도의 다음 해 6월 30일(기준값이 네 자리 연도일 때만), 대전시 동네 폐업은 '
  '받은 날 + 3개월(분기마다 사람이 받는다 · 기준값이 YYYY-MM-DD 일 때만). 서울 상권 추정매출·길단위인구는 '
  '개업·폐업과 같은 분기 규칙이고, 서울 상권 상주·직장인구는 실제 갱신이 불규칙해 예정일을 계산하지 않는다'
  '(기준 = 값이 마지막으로 바뀐 분기 둘을 글로 합침). '
  '주기가 없는 자료는 null 이다 — 없는 주기를 지어내면 "늦었다"는 거짓 신호가 뜬다. '
  '기준값이 그 모양이 아니면 계산하지 않고 그 칸만 비운다(to_date 가 터지면 표가 통째로 '
  '사라진다). timestamptz 는 전부 Asia/Seoul 로 옮겨 날짜를 자른다 — 이 DB 가 UTC 라 '
  '그냥 자르면 한국 새벽 0~9시에 어제 날짜가 찍힌다. '
  '⛔ api_quota_log 는 안 본다 — 그건 우리 호출 장부이지 자료의 나이가 아니고, 하한선일 뿐이다. '
  '자료가 0행이면 basis 가 null 이고 줄은 그대로 나온다(화면이 "자료 없음"이라 적는다 — '
  '줄을 빼면 "그런 자료를 안 쓴다"로 읽힌다). '
  'security definer (열다섯 표가 전부 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 집계 도장 열다섯 개뿐이고 원본 행은 한 줄도 안 나간다). 2026-09-05d · 월간 규칙 2026-10-01a · '
  '서울 개업·폐업 2026-10-05b · 필지 공시 연도 2026-10-12b · 실거래·대장 판 월간 규칙 2026-10-15a · '
  '성적표 줄 뺌 2026-10-18a(결정 0041) · 대전시 동네 폐업 2026-10-29a(결정 0044) · 서울 상권 4종 세 줄 2026-10-31a(결정 0045) · 가게 이력 2026-11-01a(결정 0045 PR④)';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function get_data_freshness() from public, anon, authenticated;

commit;

notify pgrst, 'reload schema';
