-- =====================================================================
-- 마이그레이션 2026-08-22e — PostgREST 노출면을 public 에서 api 로 옮긴다
-- =====================================================================
-- 실행법 ⚠️ **대시보드 SQL Editor 로 돌린다.** 전부 메타데이터 조작이라 빠르고,
--   한 트랜잭션에 들어간다(중간에 실패하면 통째로 없던 일이 된다).
--   → 붙여넣고 Run → 그다음 **반드시** `python scripts/post_load.py --check`(노출 점검).
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 하나 — public 안에 우리 것이 아닌 것이 있다
-- ─────────────────────────────────────────────────────────────────────
-- PostGIS 가 `public` 스키마에 설치돼 있어 `spatial_ref_sys` 같은 시스템 표가 REST 로
-- 그대로 노출된다. 소유자가 `supabase_admin` 이라 **우리 권한으로는 회수가 안 된다**
-- (2026-08-08 실측: anon 이 그 표를 INSERT·DELETE 할 수 있다). 우리 표는 RLS 로 잠겨
-- 있어 안전하지만, 좌표계표가 지워지면 `ST_Transform`·`ST_DWithin` 이 통째로 깨진다
-- — 지금은 상권 판정·반경 조회가 그 함수들 위에 얹혀 있으므로 더는 "영향 0" 이 아니다.
--
-- 처방은 회수가 아니라 **이사**다. PostgREST 가 보는 스키마 목록에서 public 을 빼면
-- public 안의 모든 것이 REST 에서 사라진다 — 우리가 고를 수 있는 유일한 손잡이다.
-- (상세·배경: 2026-08-08_public_read_policy.sql §5)
--
-- ─────────────────────────────────────────────────────────────────────
-- 미검증이던 전제 2개 — 2026-08-22 실측으로 둘 다 통과
-- ─────────────────────────────────────────────────────────────────────
-- 2026-08-08 은 "공식 문서에 없어 모른다"는 이유로 착수를 미뤘다. 일회용 도커
-- (supabase/postgres:17.6.1.127 + PostgREST 16.2)로 둘 다 직접 재현했다:
--
--   (전제1) 노출 목록에서 public 을 뺄 수 있는가 → ✅ **된다.**
--           `PGRST_DB_SCHEMAS="api"` 단독으로 기동되고, public 의 표를 부르면
--           **PGRST106 / HTTP 406** 으로 막힌다(조용한 통과가 아니라 명시적 거절).
--
--   (전제2) pass-through 뷰로 업서트가 되는가 → ✅ **된다.**
--           `create view api.X as select * from public.X` 는 자동 갱신 가능 뷰가 되고,
--           PostgREST 의 PK 자동 감지가 **뷰를 관통해 원본 표의 PK 를 찾는다.**
--           단일 PK·복합 PK 둘 다에서 `Prefer: resolution=merge-duplicates` 와
--           `resolution=ignore-duplicates` 업서트가 정상 동작했다.
--           ⇒ **수집·적재기는 코드 변경이 0이다**(경로도 표 이름도 그대로).
--
--   함께 확인한 것:
--     · 뷰 위의 뷰(api.v_floor_stack → public.v_floor_stack) 읽기 정상.
--     · api 래퍼 함수 → public 함수 호출 정상(아래 3번의 형태).
--     · **supabase-js 는 기본으로 `accept-profile: public` 을 보낸다** → 화면은
--       `createClient(..., { db: { schema: 'api' } })` 가 **필수**다(src/lib/supabase.ts).
--     · 파이썬 수집기는 profile 헤더를 안 보낸다 → "db-schemas 의 **첫 스키마**"라는
--       PostgREST 기본값을 탄다. ⚠️ 그래서 노출 목록의 **순서가 `api, public`** 이라야
--       한다. `public, api` 로 적으면 헤더 없는 요청이 계속 public 을 향한다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 라이브 적용 순서 (이 순서를 지키면 중간에 화면이 죽는 구간이 없다)
-- ─────────────────────────────────────────────────────────────────────
--   ① 이 파일을 SQL Editor 에서 Run.
--      이 시점엔 노출 목록이 아직 public 이라 **아무것도 안 바뀐다**(api 는 준비만 된 상태).
--   ② 대시보드 → Settings → API → Exposed schemas 에 `api` 를 **추가**하고
--      **맨 앞으로** 둔다(순서 = `api, public`). public 은 아직 빼지 않는다.
--   ③ 화면 배포(db.schema='api') + 수집기 1회 스모크. 이 단계에서 둘 다 api 로 돈다.
--   ④ Exposed schemas 에서 `public` 을 **뺀다**. 이제 PostGIS 시스템 표가 REST 에서 사라진다.
--   ⑤ `python scripts/post_load.py --check` 로 노출면을 다시 잰다.
--
-- ⚠️ 호스티드 함정 — 대시보드 저장이 런타임에 반영 안 되는 드리프트 버그
--    supabase/supabase#45904 (오픈). 대시보드에는 저장됐는데 PostgREST 는 옛 목록으로
--    계속 도는 경우가 보고돼 있다. 증상은 "④를 했는데 public 이 그대로 열려 있다" 또는
--    반대로 "②를 했는데 api 가 404". 복구는 설정을 롤에 직접 박고 리로드를 시키는 것이다:
--
--      alter role authenticator set pgrst.db_schemas = 'api, graphql_public';
--      notify pgrst, 'reload config';
--      notify pgrst, 'reload schema';
--
--    ⛔ `graphql_public` 을 빼지 말 것 — 이 줄에 적는 목록이 곧 노출 전체를 덮어쓴다.
--       'api' 만 적으면 GraphQL 엔드포인트가 함께 죽는다.
--    ⛔ 리로드는 **두 번**이다(config + schema). config 만 보내면 그 다음 호출이 404 로
--       온다(2026-08-22 실측).
--
--    (되돌리려면 `alter role authenticator set pgrst.db_schemas = 'api, public, graphql_public';`
--     + 같은 notify 두 줄. `reset` 은 Supabase 기본값으로 돌아가므로 public 이 다시 열린다.)
--
-- ✅ 2026-08-24 실행 완료 — 위 ④(public 빼기)를 라이브에 적용했다. 대시보드가 아니라
--    **롤에 직접** 박는 경로를 썼다(값: 'api, graphql_public'). 검증: Accept-Profile: public
--    요청이 PGRST106 으로 거절 · 화면이 쓰는 함수 9개·뷰 2개는 api 스키마에서 정상.
--    되돌아갔는지는 `python scripts/post_load.py --check` 가 매번 본다(public_rest_exposed).
--
-- ─────────────────────────────────────────────────────────────────────
-- 되돌리기
-- ─────────────────────────────────────────────────────────────────────
-- 노출 목록에 public 을 다시 넣으면 즉시 원상복귀다(이 파일이 만든 것은 전부 **덧붙임**
-- 이라 public 쪽을 하나도 안 건드린다). api 스키마 자체를 지우려면
-- `drop schema api cascade;` — 화면·수집기가 api 를 안 볼 때만.
-- =====================================================================


-- =====================================================================
-- 1) 스키마
-- =====================================================================
create schema if not exists api;

-- 스키마를 "볼 수 있게" 하는 것과 그 안의 객체를 읽는 것은 별개다. usage 가 없으면
-- 아래 grant 를 아무리 줘도 PostgREST 가 스키마를 못 연다.
grant usage on schema api to anon, authenticated, service_role;

-- ⛔ Supabase 는 **새로 만드는 객체마다 anon 에게 권한을 자동으로 준다**(pg_default_acl).
--    2026-08-13f·13g 가 public 에서 겪은 그 함정을 새 스키마에서 반복하지 않는다 —
--    기본값부터 닫고, 열 것만 아래에서 하나씩 명시한다.
-- ⚠️ 한계: `alter default privileges` 는 **이 문장을 실행한 롤이 만드는 것**에만 걸린다.
--    대시보드가 `supabase_admin` 으로 만든 객체는 여전히 자동 개방이다. 그래서 아래에서
--    객체마다 `revoke` 를 한 번 더 명시하고, 최종 방어선은 `post_load.py --check` 다.
alter default privileges in schema api revoke all on tables from anon, authenticated;
alter default privileges in schema api revoke all on sequences from anon, authenticated;
alter default privileges in schema api revoke all on functions from anon, authenticated;


-- =====================================================================
-- 2) 화면이 읽는 뷰 2개 — 그대로 통과시킨다
-- =====================================================================
-- ⓘ 왜 뷰 위에 뷰를 또 얹나: 원본을 api 로 **옮기면** public 쪽을 읽는 것들
--    (다른 뷰·함수·앞으로의 SQL)이 전부 깨진다. 덧붙이면 아무것도 안 깨진다.
-- ⓘ 자립한다: 뷰의 기본값은 `security_invoker = false` 라 **소유자(postgres) 권한**으로
--    아래를 읽는다. 나중에 public 쪽 anon 권한을 전부 회수해도 이 뷰는 그대로 돈다.
create or replace view api.v_floor_stack as select * from public.v_floor_stack;
create or replace view api.v_coverage_stats as select * from public.v_coverage_stats;

-- **먼저 회수하고 준다.** grant 는 더하기라, 자동으로 붙은 INSERT·DELETE 를 못 걷어낸다
-- (2026-08-22 라이브에서 v_coverage_stats 가 실제로 그 상태였다).
revoke all on api.v_floor_stack     from public, anon, authenticated;
revoke all on api.v_coverage_stats  from public, anon, authenticated;
grant select on api.v_floor_stack     to anon, authenticated;
grant select on api.v_coverage_stats  to anon, authenticated;


-- =====================================================================
-- 3) 화면이 부르는 함수 9개 — 같은 서명으로 감싼다
-- =====================================================================
-- ⚠️ **서명(파라미터 이름·타입·기본값)과 돌려주는 칸 이름을 원본과 한 글자도 다르지 않게**
--    적는다. PostgREST 는 JSON 키 이름으로 인자를 찾으므로 이름이 하나만 달라도
--    PGRST202(함수 없음)가 난다. 특히 `list_price_bands`·`list_industry_mix` 는 `p_pnu`,
--    `list_industry_detail` 은 `p_pnu, p_cat` 이다(컬럼명과 겹쳐서 접두사가 붙어 있다).
--
-- ⚠️ `security definer` + `set search_path = ''` 인 이유:
--    · security definer — 원본 함수는 anon 에게 열려 있지만, 나중에 public 쪽을 통째로
--      닫아도 이 래퍼가 소유자 권한으로 계속 부를 수 있게 한다(자립).
--    · search_path = '' — 빈 검색경로라 **본문의 이름을 전부 `public.` 으로 완전수식**해야
--      한다. 반대로 말하면, 완전수식했으므로 누가 검색경로를 갈아끼워도 다른 함수가
--      대신 불릴 수 없다(security definer 함수의 표준 방어).
--
-- ⓘ volatility 는 원본과 맞춘다(전부 `stable`). 다르게 적으면 플래너가 다르게 판단한다.

-- ── 검색 ─────────────────────────────────────────────────────────────
create or replace function api.search_buildings(q text, lim int default 25, sigungu text default null)
returns table (
  bld_id         text,
  pnu            char(19),
  bld_nm         text,
  road_addr      text,
  jibun_addr     text,
  lat            double precision,
  lng            double precision,
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
set search_path = ''
as $$ select * from public.search_buildings(q, lim, sigungu) $$;

create or replace function api.search_scope(q text, sigungu text default null)
returns table (too_broad boolean, match_cnt int)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.search_scope(q, sigungu) $$;

create or replace function api.list_open_sigungu()
returns table (sido_code char(2), sido_nm text, sigungu_code char(5), sigungu_nm text, building_cnt int)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_open_sigungu() $$;

-- ── 층별 화면 ────────────────────────────────────────────────────────
create or replace function api.list_building_districts(bld_id text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$ select public.list_building_districts(bld_id) $$;

create or replace function api.list_parcel_transactions(pnu text)
returns table (
  floor_no     smallint,
  contract_ym  text,
  contract_day smallint,
  bld_area_m2  numeric,
  price_won    bigint,
  unit_price   numeric,
  tx_type      text
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_parcel_transactions(pnu) $$;

create or replace function api.get_sigungu_tx_stats(sigungu text)
returns table (
  floor_band        text,
  n                 int,
  median_unit_price numeric,
  p25_unit_price    numeric,
  p75_unit_price    numeric,
  window_from       text,
  sigungu_nm        text
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.get_sigungu_tx_stats(sigungu) $$;

create or replace function api.list_price_bands(p_pnu text)
returns table (
  floor_no        smallint,
  status          text,
  stage           text,
  n               int,
  p25             numeric,
  median          numeric,
  p75             numeric,
  median_area_m2  numeric,
  window_from     text
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_price_bands(p_pnu) $$;

create or replace function api.list_industry_mix(p_pnu text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$ select public.list_industry_mix(p_pnu) $$;

create or replace function api.list_industry_detail(p_pnu text, p_cat text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$ select public.list_industry_detail(p_pnu, p_cat) $$;

-- Postgres 는 새 함수의 EXECUTE 를 **PUBLIC(모든 롤)** 에게 기본으로 준다. 위의
-- `alter default privileges` 는 anon·authenticated 만 다루므로 PUBLIC 경로가 남는다 —
-- 2026-08-10 이 "revoke from public 이 무효였다"고 적어 둔 것의 **반대 방향**이다
-- (그때는 PUBLIC 만 회수해서 직접 GRANT 가 남았고, 여기는 PUBLIC 을 안 지우면 그게 남는다).
-- 그래서 **먼저 PUBLIC 을 회수하고** 필요한 롤에만 정확히 준다. anon·authenticated 를
-- 같이 적는 이유는 뷰들과 같다 — 이 함수를 나중에 **대시보드**(supabase_admin)로
-- 재생성하면 위의 default privileges 가 안 걸려 anon 권한이 자동으로 붙는데, 그때
-- 이 줄을 다시 돌려도 public 만 회수해서는 그 구멍을 못 닫는다(대칭 방어).
revoke all on function api.search_buildings(text, int, text)  from public, anon, authenticated;
revoke all on function api.search_scope(text, text)           from public, anon, authenticated;
revoke all on function api.list_open_sigungu()                from public, anon, authenticated;
revoke all on function api.list_building_districts(text)      from public, anon, authenticated;
revoke all on function api.list_parcel_transactions(text)     from public, anon, authenticated;
revoke all on function api.get_sigungu_tx_stats(text)         from public, anon, authenticated;
revoke all on function api.list_price_bands(text)             from public, anon, authenticated;
revoke all on function api.list_industry_mix(text)            from public, anon, authenticated;
revoke all on function api.list_industry_detail(text, text)   from public, anon, authenticated;

grant execute on function api.search_buildings(text, int, text)  to anon, authenticated;
grant execute on function api.search_scope(text, text)           to anon, authenticated;
grant execute on function api.list_open_sigungu()                to anon, authenticated;
grant execute on function api.list_building_districts(text)      to anon, authenticated;
grant execute on function api.list_parcel_transactions(text)     to anon, authenticated;
grant execute on function api.get_sigungu_tx_stats(text)         to anon, authenticated;
grant execute on function api.list_price_bands(text)             to anon, authenticated;
grant execute on function api.list_industry_mix(text)            to anon, authenticated;
grant execute on function api.list_industry_detail(text, text)   to anon, authenticated;


-- =====================================================================
-- 4) 수집·적재기가 REST 로 쓰는 표 — pass-through 뷰
-- =====================================================================
-- 이 목록은 상상이 아니라 **스크립트를 훑어 뽑은 것**이다(`/rest/v1/` 와 upsert 대상):
--   parcel            ← load_vworld_land / load_vworld_bulk / load_sangkwon_snapshot (읽기도)
--   building          ← load_building_ledger
--   unit              ← load_building_ledger
--   building_floor    ← load_building_ledger
--   unit_business     ← load_sangkwon_snapshot
--   transaction       ← load_transactions (업서트 + 옛 행 DELETE), backtest_price (읽기)
--   rent_stat         ← load_rone
--   collect_progress  ← 수집기 4종의 이어받기 원장
--   api_quota_log     ← 수집기 4종의 호출 예산 원장
--   bjd_code          ← load_bjd_code (쓰기), backtest_price (읽기)
--
-- ⛔ 여기 **없는 것**은 일부러 없다. `district`·`district_rone_map`·`price_gate_sigungu`·
--    물질화뷰들은 psql(dbx.py) 로만 다루므로 REST 경로가 필요 없다. 안 만드는 것이
--    곧 노출면을 줄이는 일이다 — 나중에 REST 로 쓰게 되면 그때 이 목록에 더한다.
--
-- ⚠️ **뷰는 RLS 를 우회한다.** 아래 표들은 전부 RLS 가 켜져 있지만, 이 뷰는 소유자
--    (postgres = 표의 주인) 권한으로 읽으므로 RLS 가 안 걸린다. 즉 **권한만이 방어선**이다.
--    anon 에게 하나라도 새면 상호명(unit_business)·실거래(transaction)가 통째로 나간다.
--    그래서 표마다 `revoke` 를 **명시**한다(자동 개방을 믿고 넘어가지 않는다).
create or replace view api.parcel           as select * from public.parcel;
create or replace view api.building         as select * from public.building;
create or replace view api.unit             as select * from public.unit;
create or replace view api.building_floor   as select * from public.building_floor;
create or replace view api.unit_business    as select * from public.unit_business;
create or replace view api.transaction      as select * from public.transaction;
create or replace view api.rent_stat        as select * from public.rent_stat;
create or replace view api.collect_progress as select * from public.collect_progress;
create or replace view api.api_quota_log    as select * from public.api_quota_log;
create or replace view api.bjd_code         as select * from public.bjd_code;

revoke all on api.parcel           from public, anon, authenticated;
revoke all on api.building         from public, anon, authenticated;
revoke all on api.unit             from public, anon, authenticated;
revoke all on api.building_floor   from public, anon, authenticated;
revoke all on api.unit_business    from public, anon, authenticated;
revoke all on api.transaction      from public, anon, authenticated;
revoke all on api.rent_stat        from public, anon, authenticated;
revoke all on api.collect_progress from public, anon, authenticated;
revoke all on api.api_quota_log    from public, anon, authenticated;
revoke all on api.bjd_code         from public, anon, authenticated;

grant select, insert, update, delete on api.parcel           to service_role;
grant select, insert, update, delete on api.building         to service_role;
grant select, insert, update, delete on api.unit             to service_role;
grant select, insert, update, delete on api.building_floor   to service_role;
grant select, insert, update, delete on api.unit_business    to service_role;
grant select, insert, update, delete on api.transaction      to service_role;
grant select, insert, update, delete on api.rent_stat        to service_role;
grant select, insert, update, delete on api.collect_progress to service_role;
grant select, insert, update, delete on api.api_quota_log    to service_role;
grant select, insert, update, delete on api.bjd_code         to service_role;


-- =====================================================================
-- 5) PostgREST 에게 "스키마가 바뀌었다"고 알린다
-- =====================================================================
-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';


-- =====================================================================
-- 6) 확인 (붙여넣고 Run 한 뒤 이 쿼리로 검산)
-- =====================================================================
-- 기대: 12행 (화면 뷰 2 + 수집기 뷰 10)
--
--   select table_name from information_schema.views
--   where table_schema = 'api' order by table_name;
--
-- 기대: anon 이 읽을 수 있는 api 객체는 v_floor_stack·v_coverage_stats **둘뿐**
--
--   select c.relname
--   from pg_class c join pg_namespace n on n.oid = c.relnamespace
--   where n.nspname = 'api' and has_table_privilege('anon', c.oid, 'SELECT')
--   order by 1;
--
-- 기대: anon 이 부를 수 있는 api 함수는 9개
--
--   select p.proname
--   from pg_proc p join pg_namespace n on n.oid = p.pronamespace
--   where n.nspname = 'api' and has_function_privilege('anon', p.oid, 'EXECUTE')
--   order by 1;
--
-- 기대: 위 셋을 사람 말로 한 번에 — python scripts/post_load.py --check
-- =====================================================================
