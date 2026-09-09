-- =====================================================================
-- 상호명으로 찾기 — search_stores + 필지 요약표에 "그 땅의 가게 이름들" (2026-09-09c)
-- =====================================================================
-- 결정 0028(사장님 결재 2026-09-09). 검색창은 여태 **건물 이름과 주소**만 알았다.
-- 창업자는 건물 이름을 모르고 "스타벅스 있는 건물"로 찾는데, 점포 자료 277만 행(상호
-- 100% 채움)으로 들어오는 문이 하나도 없었다.
--
-- 왜 점포 표를 직접 안 훑나 (실측)
-- --------------------------------
-- '카페'(2글자)는 trigram 선별력이 없어 상호 색인 idx_ub_name 을 **아예 안 탄다** —
-- 구로 좁혀도 Parallel Seq Scan 277만 행, **7.6초**. 반면 '스타벅스'(4글자)는 0.07초다.
-- 즉 문제는 색인이 없어서가 아니라 **훑는 표가 277만 행이라서**다. 그래서 이미 건물
-- 검색이 매 요청 훑는 **필지 요약표(188,442행)** 에 "그 땅의 가게 이름들"을 담아 두고
-- 거기서 찾는다(강남 시제품 실측: 2글자 10ms · 4글자 0.6ms).
--
-- ⛔ 식(expression) 인덱스로는 못 푼다 — 이 레포가 라이브에서 지우고 "되살리지 말 것"이라
--    못 박은 패턴이다(schema.sql 965-973: 재확인마다 정규식을 다시 돌려 간헐 500).
-- ⛔ 점포 표(339만 행 append-only)에 저장 칸을 붙이는 것도 아니다 — 표 재작성 잠금.
--
-- ⚠️⚠️ 이 마이그레이션이 **다섯 객체**를 다시 만드는 까닭 (결정문이 몰랐던 사실)
-- ------------------------------------------------------------------------------
-- 물질화뷰는 칸을 나중에 못 붙인다(`alter materialized view … add column` 이 없다).
-- 그래서 mv_search_parcel 을 떨어뜨렸다 다시 만들어야 하는데 — **이 표에 기대어 사는
-- 것들이 있다.** 라이브에서 그냥 drop 하면 "cannot drop … because other objects depend
-- on it" 로 **막힌다**(결정 0028 §결정 3 은 이 사슬을 몰랐고, 그래서 "몇십 초 잠긴다"는
-- 비용 추정도 이 사슬만큼 늘어난다):
--
--     mv_search_parcel
--       └ mv_open_sigungu        (고를 수 있는 구 목록 — from mv_search_parcel)
--           └ mv_coverage_stats  (각주 집계 — in (select … from mv_open_sigungu))
--               └ v_coverage_stats      (화면이 읽는 뷰)
--                   └ api.v_coverage_stats (화면이 실제로 부르는 문)
--
-- ⛔ `cascade` 는 안 쓴다 — 지금 모르는 의존물이 하나 더 생겨 있으면 그것까지 **조용히**
--    지운다. 하나씩 이름을 적어 떨어뜨리면 모르는 것이 있을 때 **에러로 멈춘다**.
-- ⛔ v_coverage_stats 의 코멘트에는 "drop 하고 다시 만들지 말 것"이 박혀 있다. 그 규칙의
--    이유는 **anon SELECT 가 같이 날아가는데 `post_load.py --check` 가 '열려 있어야 하는데
--    닫힌 것'은 못 잡는다**는 것이다. 여기서는 피할 길이 없으므로(위 사슬) 그 위험을
--    셋으로 상쇄한다: ①같은 트랜잭션 안에서 곧바로 `grant select` 를 **명시로** 다시 준다
--    ②`security_invoker = false` 도 함께 되돌린다 ③그 두 줄이 이 파일에 있는지
--    `tests/test_search_stores_migration.py` 가 지킨다.
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- --------------------------------------
-- `scripts/dbx.py` 는 `psql -v ON_ERROR_STOP=1 -f` 로 돌린다(자동커밋 — `--single-transaction`
-- 이 없다). 이 파일은 다섯 객체를 **먼저 떨어뜨린 뒤** 다시 만든다. 그 사이에 끊기면
-- 검색·지역 목록·각주가 통째로 사라진 채 남고, `post_load.py` 의
-- `refresh materialized view concurrently` 도 "그런 뷰 없음"으로 멈춰 다른 요약표 갱신까지
-- 함께 선다. 한 덩어리로 묶으면 실패한 순간 **적용 전 상태 그대로** 되돌아간다
-- (2026-09-05c·2026-09-09b 가 같은 이유로 같은 모양을 쓴다).
-- ⓘ `create index`(concurrently 가 **아닌** 것)·`analyze`·`grant` 는 트랜잭션 안에서
--   허용된다. `notify` 는 커밋되어야 전달되므로 commit **뒤**에 둔다.
-- ⛔ `create index concurrently` 로 바꾸지 말 것 — 그것만은 트랜잭션 안에서 못 돈다.
--
-- ⚠️ **언제 적용하나 — 새벽에.**
-- ---------------------------
-- mv_search_parcel 은 **건물 검색이 매 요청 훑는 표**다. 커밋 전까지 그 표를 읽는 모든
-- 검색이 줄을 선다(잠긴다). 게다가 이번엔 사슬 넷이 더 붙어 각주(v_coverage_stats)까지
-- 같이 잠긴다. 사람이 안 쓰는 시간에 돌릴 것.
--
-- ⛔ 맨 끝의 `drop index idx_ub_name` 이 왜 커밋 **뒤**에 있나
-- ----------------------------------------------------------
-- `drop index` 의 ACCESS EXCLUSIVE 락은 **커밋까지 유지된다**. 위 덩어리 안에 두면 요약표를
-- 굽는 내내 unit_business 를 읽는 다른 세션이 전부 줄을 선다(2026-08-22c 가 같은 함정을
-- 적어 두었다). 커밋 뒤 제 트랜잭션에서 혼자 돌면 잠금이 순식간이다.
-- ⓘ 이 색인(원문 상호 위 trgm, **186MB** 실측)은 **쓰는 코드가 0건**이다 — 2글자 검색어가
--   못 타서 애초에 우리 목적에 무용했고, 이제 그 일은 요약표의 idx_msp_store_names 가 한다.
--   지운 만큼(186MB)이 새로 만드는 색인(~150MB 추정)을 상쇄한다.
--
-- 실행법
-- ------
--   python scripts/dbx.py -f supabase/migrations/2026-09-09c_search_stores.sql
--
-- 적용한 사람이 보게 되는 것
-- --------------------------
--   · BEGIN · DROP VIEW ×2 · DROP MATERIALIZED VIEW ×3 · CREATE MATERIALIZED VIEW ×3
--     · CREATE VIEW ×2 · COMMENT ×5 · CREATE INDEX ×7 · ANALYZE ×3 · REVOKE · GRANT
--     · CREATE FUNCTION ×2 · COMMIT · NOTIFY · DROP INDEX
--   · 중간에 실패하면 **아무것도 안 바뀐 상태**로 되돌아간다 — 고친 뒤 처음부터 다시 돌린다.
--   · 요약표 굽기가 오래 걸린다(188,442 필지마다 최신 분기 점포를 모은다 — 몇 분 각오).
--   · 적용 뒤 `python scripts/post_load.py --check` 는 그대로 exit 0 이어야 한다.
--     공개 호출 목록이 20 → 21 로 늘었다(api.search_stores) — `--check` 총계 24 → 25.
--   · 적용 뒤 `python scripts/post_load.py` 를 한 번 돌린다(갱신 목록은 안 바뀌었다 —
--     mv_search_parcel 은 이미 REFRESH_MVS 에 있다. 다만 **갱신 시간이 는다**).
--
-- 되돌리기: 이 파일을 되돌리려면 mv_search_parcel 을 옛 아홉 칸으로 다시 만들고(사슬 넷도
-- 함께) `drop function api.search_stores(text,int,text,int)`·`drop function
-- search_stores(text,int,text,int)` 한다. 옛 색인 idx_ub_name 이 필요하면
-- `create index idx_ub_name on unit_business using gin (biz_name gin_trgm_ops);`
-- (186MB · 굽는 데 몇 분).

-- ⛔ 여기부터 commit 까지가 **한 덩어리**다(위 머리말 참조).
begin;

-- ── 0) 사슬을 **끝에서부터** 떨어뜨린다 ─────────────────────────────────────
-- ⛔ 순서를 바꾸면 "다른 것이 기대고 있다"로 막힌다. 그리고 그게 정상이다 —
--    막히는 것이 조용히 지워지는 것보다 낫다(그래서 cascade 를 안 쓴다).
drop view if exists api.v_coverage_stats;
drop view if exists v_coverage_stats;
drop materialized view if exists mv_coverage_stats;
drop materialized view if exists mv_open_sigungu;
drop materialized view if exists mv_search_parcel;

-- ── 1) 검색 전용 요약표 — 칸 셋이 늘었다 ────────────────────────────────────
-- ⛔ `if not exists` 로 쓰지 말 것 — 이미 있으면 **아무 일도 안 하고 에러도 안 난다**
--    (칸이 안 붙은 채 화면만 옛 모양을 계속 말한다). 위에서 떨어뜨렸으므로 그냥 만든다.
create materialized view mv_search_parcel as
with latest as (
  -- ⚠️ **전역** 최신 분기 하나다(지역별로 고르지 않는다) — v_floor_stack·mv_coverage_stats
  --    와 같은 기준이라, 한 지역만 분기가 밀리면 그 지역 가게가 통째로 안 나오는 알려진
  --    결함을 그대로 물려받는다(결정 0028 결정 1 · 알려진한계 §4). 여기서 한 번만 구한다.
  select max(u.snapshot_ym) as ym from unit_business u
)
select
  pc.pnu,
  substr(pc.pnu, 1, 5)::char(5) as sigungu_code,   -- 검색 범위를 좁히는 칸
  pc.road_addr,
  pc.road_addr_key,
  pc.jibun_addr_key,
  pc.sido_nm,
  pc.sigungu_nm,
  pc.emd_nm,
  pc.jibun,
  -- ── 상호명으로 찾기 (결정 0028 결정 3) ───────────────────────────────────
  -- ⛔ distinct 로 접지 않는다 — **점포마다 한 항목**이어야 "이 이름의 가게 N곳"을
  --    요약표 한 줄 안에서 셀 수 있다. 접으면 그 수를 세러 점포 표를 되짚어야 하는데,
  --    그 2단계가 찬 캐시 **3.2초**였다(강남 시제품 실측).
  sn.store_names,
  -- 찾을 때 훑는 칸. 같은 이름이 여럿이면 한 번만 담는다(찾기에는 있으면 되고, 세는 것은
  -- 위 배열이 한다). ⛔ 건물 이름과 **같은 자**(search_key = 공백 제거 + 소문자)로 자른다 —
  -- 같은 검색어에 건물과 상호가 다른 답을 내면 안 된다.
  sn.store_names_key,
  -- 화면이 "2026년 6월 기준 점포 자료" 도장을 찍는 값(전 행 같다 — 숫자 리터럴 0).
  (select l.ym from latest l)::char(6) as store_snapshot_ym
from parcel pc
left join lateral (
  select
    array_agg(ub.biz_name order by ub.biz_name)       as store_names,
    string_agg(distinct search_key(ub.biz_name), '|') as store_names_key
  from unit_business ub
  where ub.pnu = pc.pnu
    -- ⓘ 스칼라 하위질의라 한 번만 계산되고(InitPlan) 상수처럼 쓰인다 —
    --    그래야 idx_ub_pnu_cat (pnu, snapshot_ym) 이 이 조회를 그대로 받친다.
    and ub.snapshot_ym = (select l.ym from latest l)
    and ub.biz_name is not null
) sn on true
where exists (select 1 from building b where b.pnu = pc.pnu);

comment on materialized view mv_search_parcel is
  '§8.1 검색 전용 요약표 — **건물이 있는 필지만** 담는다(2026-08-13). 전국 시드로 parcel 이 '
  '112만 행이 됐지만 건물은 서울·대전 24만 동뿐이라, 나머지 93만 필지는 검색 결과가 될 수 없는데도 '
  '매번 훑혔다(명동 1,725ms → 500). 이 표는 188,442행이라 같은 스캔이 109ms 다. '
  'sigungu_code 는 "고른 구 안에서만 검색"(2026-08-13e)에 쓴다. '
  '2026-09-09c(결정 0028): store_names·store_names_key·store_snapshot_ym 세 칸이 여기 있는 이유는 '
  '**점포 표(277만 행)를 직접 훑으면 2글자 검색어가 trigram 을 못 타 7.6초**가 되기 때문이다 — '
  '이 표(구 안 1.2만 행)에서 찾으면 10ms 다. store_names 는 **점포마다 한 항목**(중복 포함)이라 '
  '"이 이름의 가게 N곳"을 한 줄 안에서 셀 수 있고, store_names_key 는 그 이름들을 건물과 같은 자'
  '(search_key)로 잘라 | 로 이은 것이다(그 위에 idx_msp_store_names). '
  '⚠️ 자료를 새로 넣으면 `python scripts/post_load.py` 를 반드시 돌릴 것 — '
  '안 하면 새 건물·새 가게가 조용히 검색에서 빠진다(ANALYZE 와 같은 성격의 적재 후 필수 절차).';

-- ⛔ 색인은 **전부** 다시 만든다 — 뷰를 떨어뜨릴 때 함께 사라졌다. 하나라도 빠지면
--    갱신이 멈추거나(유니크) 검색이 조용히 느려진다(trgm·구).
create unique index if not exists idx_msp_pnu        on mv_search_parcel (pnu);
create index if not exists idx_msp_road_key          on mv_search_parcel using gin (road_addr_key gin_trgm_ops);
create index if not exists idx_msp_jibun_key         on mv_search_parcel using gin (jibun_addr_key gin_trgm_ops);
-- 구로 좁히는 것이 이제 기본 경로다 — 이 인덱스가 그 길을 연다.
create index if not exists idx_msp_sigungu           on mv_search_parcel (sigungu_code);
-- 상호명 부분 일치(2026-09-09c). 4글자 이상이면 이 색인이 받치고(0.6ms), 2글자는 못 타지만
-- 구 안 1.2만 행 순차 훑기라 10ms 다 — 277만 행을 훑던 7.6초와 비교할 자리가 아니다.
create index if not exists idx_msp_store_names       on mv_search_parcel using gin (store_names_key gin_trgm_ops);

analyze mv_search_parcel;

-- ⛔ 다시 만든 표는 다시 열려 있을 수 있다(Supabase pg_default_acl) — 만든 자리에서 닫는다.
revoke all on mv_search_parcel from public, anon, authenticated;

-- ── 2) 사슬 ① 고를 수 있는 구 목록 — 정본 그대로 되세운다 ───────────────────
create materialized view mv_open_sigungu as
select
  substr(pc.sigungu_code, 1, 2)::char(2) as sido_code,
  max(pc.sido_nm)                        as sido_nm,
  pc.sigungu_code,
  max(pc.sigungu_nm)                     as sigungu_nm,
  count(*)::int                          as building_cnt
from mv_search_parcel pc
join building b on b.pnu = pc.pnu
group by pc.sigungu_code;

comment on materialized view mv_open_sigungu is
  '§8.1 지금 검색할 수 있는 시군구 목록(자료가 실제로 있는 곳만). 화면의 지역 고르기가 이걸 읽는다. '
  '⚠️ 목록을 프론트에 박지 말 것 — 자료 없는 구를 고르면 "고장난 것"처럼 보인다. '
  '`python scripts/post_load.py` 가 mv_search_parcel 과 함께 갱신한다.';

create unique index if not exists idx_mos_sigungu on mv_open_sigungu (sigungu_code);
analyze mv_open_sigungu;

revoke all on mv_open_sigungu from public, anon, authenticated;

-- ── 3) 사슬 ② 각주 집계 — 정본 그대로 되세운다 ──────────────────────────────
create materialized view mv_coverage_stats as
select
  ub.snapshot_ym,
  count(*)                                                    as store_cnt,
  count(*) filter (where ub.floor_no is null)                 as floor_missing_cnt,
  round(100.0 * count(*) filter (where ub.floor_no is null)
        / count(*), 1)                                        as floor_missing_pct
from unit_business ub
where ub.snapshot_ym = (select max(snapshot_ym) from unit_business)
  and substr(ub.pnu, 1, 5)::char(5) in (select sigungu_code from mv_open_sigungu)
group by ub.snapshot_ym;

comment on materialized view mv_coverage_stats is
  '§8.6 스택 뷰 각주 집계를 **미리 계산해 둔 한 줄**(2026-08-22d). 화면은 이 표를 직접 '
  '읽지 않고 v_coverage_stats 뷰를 거친다 — 표 자체는 anon 에게 닫혀 있다. '
  '왜 사전계산인가: 실시간 집계는 최신 스냅샷 277만 행마다 substr 을 잘라 열린 구 목록과 '
  '대조하느라 순수 실행 2.1~4.9초였고(2026-08-22 실측, 부하에 따라 흔들린다), anon 의 '
  '3초 제한을 넘나들었다. 집계값은 **적재 시점에만** 바뀌므로 그때 한 번 세면 된다. '
  '신선도 = python scripts/post_load.py 를 돌린 시점(적재와 한 세트다 — 그 스크립트의 '
  '--check 가 원본 최신 분기와 대조해 낡음을 잡는다). '
  '⚠️ 본문은 2026-08-22a 의 v_coverage_stats select 와 동일하다 — 범위(서비스 지역)나 '
  '분기 기준을 고칠 때는 여기와 supabase/schema.sql 을 함께 고칠 것.';

create unique index if not exists idx_mcs_snapshot_ym on mv_coverage_stats (snapshot_ym);
analyze mv_coverage_stats;

revoke all on mv_coverage_stats from public, anon, authenticated;

-- ── 4) 사슬 ③④ 화면이 읽는 뷰 — **권한까지** 되세운다 ──────────────────────
-- ⛔ 여기가 이 파일에서 가장 조용히 깨질 수 있는 자리다. 뷰가 사라졌다 돌아오면서
--    anon SELECT 가 같이 날아가는데, `post_load.py --check` 는 "열려 있으면 안 되는데
--    열린 것"만 잡지 "열려 있어야 하는데 닫힌 것"은 **못 잡는다** — 경보 없이 각주만
--    조용히 사라진다. 그래서 아래 revoke/grant/security_invoker 세 줄이 필수다.
create or replace view v_coverage_stats as
select * from mv_coverage_stats;

comment on view v_coverage_stats is
  '§8.6 스택 뷰 각주용 집계. **미리 계산해 둔 mv_coverage_stats 한 줄을 그대로 내보낸다** '
  '(2026-08-22d — 실시간 집계는 2.1~4.9초로 anon 3초 제한을 넘나들었다). '
  '★ 범위는 **서비스 지역(mv_open_sigungu = 화면에서 고를 수 있는 구)** 뿐이다(2026-08-22a). '
  '전국을 세면 화면이 보여주지도 않는 지역까지 섞여 결측률이 15.3%p 과장된다(50.3% vs 35.0%). '
  '분기 기준은 v_floor_stack 과 동일한 전역 최신 snapshot_ym — 둘을 항상 함께 고칠 것. '
  'ℹ️ pnu 가 NULL 인 행(실측 1,819)은 지역 특정 불가라 분모에서 빠진다. '
  'ℹ️ 신선도 = python scripts/post_load.py 시점 — 그 스크립트의 --check 가 낡음을 잡는다. '
  '★ 공개 접근: anon/authenticated에게 SELECT **만** 허용(집계값만, 상호명 없음). '
  '⛔ drop 하지 말 것 — GRANT 가 날아가는데 post_load --check 는 "닫힌 것"을 못 잡는다. '
  'ℹ️ 린트 0010(security definer view) 의도적 예외 — security_invoker=true로 되돌리면 원본 표 401. '
  '재검토 방아쇠: 공개 배포일 / 지도·반경 검색(§6.4) 착수일';

-- 뷰가 RLS를 우회하는 것이 사고가 아니라 선택임을 코드에 남긴다(기본값이지만 명시).
alter view v_coverage_stats set (security_invoker = false);

revoke all on v_coverage_stats from public, anon, authenticated;
grant select on v_coverage_stats to anon, authenticated;

create or replace view api.v_coverage_stats as select * from public.v_coverage_stats;

revoke all on api.v_coverage_stats from public, anon, authenticated;
grant select on api.v_coverage_stats to anon, authenticated;

-- ── 5) 상호명으로 찾기 — 본체 ───────────────────────────────────────────────
create or replace function search_stores(
  q        text,
  lim      int  default 50,
  sigungu  text default null,
  p_offset int  default 0
)
returns table (
  pnu               char(19),
  bld_id            text,
  bld_nm            text,
  road_addr         text,
  jibun_addr        text,
  lat               double precision,
  lng               double precision,
  bld_cnt_in_pnu    int,
  floor_cnt         int,
  min_floor         smallint,
  max_floor         smallint,
  has_roof          boolean,
  matched_names     text[],
  match_store_cnt   int,
  total_parcel_cnt  bigint,
  total_store_cnt   bigint,
  too_broad         boolean,
  store_snapshot_ym text
)
language sql
stable
security definer
set search_path = public
as $$
  with pat as (
    -- 전처리는 형제 search_buildings 의 것을 **글자 그대로** 물려받는다 — 같은 검색어에
    -- 건물과 가게가 다른 답을 내면 안 된다. k 는 **이스케이프 전** 값이다(정확일치 정렬용).
    select
      case when esc.v is null then null else '%' || esc.v || '%' end as p,
      search_key(q) as k,
      esc.gu
    from (
      select case when search_key(q) is null then null
                  else replace(replace(replace(search_key(q), '\', '\\'),
                               '%', '\%'), '_', '\_')
             end as v,
             nullif(btrim(coalesce(sigungu, '')), '') as gu
    ) esc
  ),
  -- ① 이름이 걸린 **땅**을 찾는다. 구를 안 골랐으면 0건이다(결정 0007) —
  --    상호는 같은 이름이 전국에 널려 있어 구 없이는 답이 될 수 없다.
  hit as (
    select pc.pnu, pc.road_addr, pc.store_names, pc.store_snapshot_ym
      from mv_search_parcel pc
      cross join pat
     where pat.p is not null
       and pat.gu is not null
       and pc.sigungu_code = pat.gu
       and pc.store_names_key like pat.p escape '\'
       -- 층 자료가 아예 없는 건물뿐인 땅은 눌러도 빈 화면이라 뺀다
       -- (검색·결정 0025 와 **같은 규칙** — 갈리면 들어온 길에 따라 다른 답이 된다).
       and exists (
         select 1 from building b
          where b.pnu = pc.pnu
            and exists (select 1 from building_floor f
                         where f.bld_id = b.bld_id and f.floor_no is not null)
       )
  ),
  -- ② 그 땅 안에서 **어느 이름이 몇 곳** 걸렸나. 요약표 한 줄 안에서 센다(되짚기 없음).
  matched as (
    select h.pnu, h.road_addr, h.store_snapshot_ym,
           agg.n        as match_store_cnt,
           agg.exact_hit,
           (
             -- 화면에 적을 이름 최대 3개 — 정확히 같은 이름 먼저, 그다음 가나다.
             -- ⛔ 원문 그대로 낸다(간판에 걸린 공개 이름이다 — 결정 0028 결정 5).
             select array_agg(d.nm order by d.is_exact desc, d.nm)
             from (
               select distinct u2.nm,
                      (search_key(u2.nm) = pat.k) as is_exact
                 from unnest(h.store_names) as u2(nm)
                where search_key(u2.nm) like pat.p escape '\'
                order by is_exact desc, nm
                limit 3
             ) d
           ) as matched_names
      from hit h
      cross join pat
      join lateral (
        select count(*)::int as n,
               coalesce(bool_or(search_key(u.nm) = pat.k), false) as exact_hit
          from unnest(h.store_names) as u(nm)
         where search_key(u.nm) like pat.p escape '\'
      ) agg on true
     -- ⓘ store_names_key 는 이름들을 '|' 로 이은 한 줄이라, 검색어가 그 이음매를 걸치면
     --    ①에서 걸리고도 실제 이름은 하나도 안 맞을 수 있다. 그 헛것을 여기서 뺀다 —
     --    그래야 아래 총계(땅 수·가게 수)가 화면에 서는 줄과 같은 말을 한다.
     where agg.n > 0
  ),
  tot as (
    select m.*,
           count(*) over ()               as total_parcel_cnt,
           sum(m.match_store_cnt) over () as total_store_cnt
      from matched m
  ),
  -- ③ 너무 넓은 검색어인가. 구 안 최다가 '학원' 강남 898땅이라 실제로는 거의 안 닿는
  --    안전망이다(구를 안 고르면 애초에 0건이라 여기 오지도 않는다).
  gate as (
    select coalesce((select max(t.total_parcel_cnt) from tot t), 0)
             > search_scope_limit() as broad
  ),
  page as (
    -- ⛔ 무거운 조인(대표 동·주소 조립·좌표·층 집계) 전에 **상한을 먼저** 건다.
    --    tie-break 에 pnu 를 둔다 — 없으면 같은 수끼리 순서가 흔들려 '더 보기'가
    --    이미 본 줄을 다시 가져오거나 건너뛴다(결정 0025 와 같은 이유).
    select t.*
      from tot t
      cross join gate g
     where not g.broad
     order by t.match_store_cnt desc,
              t.exact_hit       desc,
              t.road_addr       asc nulls last,
              t.pnu
     limit  greatest(1, least(coalesce(lim, 50), 200))
     offset greatest(0, coalesce(p_offset, 0))
  ),
  rows_out as (
    select
      pg.pnu,
      rep.bld_id,
      rep.bld_nm,
      p.road_addr,
      parcel_jibun_addr(p.sido_nm, p.sigungu_nm, p.emd_nm, p.jibun) as jibun_addr,
      -- ⛔ 좌표는 geom 에서만 뽑는다. parcel 의 lat/lng **칸**을 쓰면 검색·상권판정과
      --    자리가 갈려 "마커는 상권 밖인데 글자는 상권 안"이 된다(2026-08-14e 규칙).
      st_y(p.geom)::double precision as lat,
      st_x(p.geom)::double precision as lng,
      cnt.bld_cnt_in_pnu,
      fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof,
      pg.matched_names,
      pg.match_store_cnt,
      pg.total_parcel_cnt,
      pg.total_store_cnt,
      false as too_broad,
      pg.store_snapshot_ym::text as store_snapshot_ym,
      pg.exact_hit
    from page pg
    join parcel p on p.pnu = pg.pnu
    join lateral (
      -- 대표 동 = 연면적 최대(결정 0025 와 같은 자). 층 자료 없는 동은 뺀다.
      select b.bld_id, b.display_nm as bld_nm
        from building b
       where b.pnu = pg.pnu
         and exists (select 1 from building_floor f
                      where f.bld_id = b.bld_id and f.floor_no is not null)
       order by b.total_area_m2 desc nulls last, b.bld_id
       limit 1
    ) rep on true
    join lateral (
      -- 1 보다 크면 화면이 "같은 땅에 N동"을 적고, 누르면 list_parcel_buildings 로 펼친다.
      -- ⛔ 그 함수도 층 자료 없는 동을 빼므로 여기서도 같은 조건으로 센다 — 안 그러면
      --    "3동"이라 적어 놓고 펼치면 2동만 나온다.
      select count(*)::int as bld_cnt_in_pnu
        from building b2
       where b2.pnu = pg.pnu
         and exists (select 1 from building_floor f
                      where f.bld_id = b2.bld_id and f.floor_no is not null)
    ) cnt on true
    join lateral (
      -- ⛔ 층수 규칙을 여기서 새로 정하지 않는다 — 검색 함수의 것을 글자 그대로 옮겼다.
      --    갈리면 같은 건물이 "지하2~15층"과 "지하2~99층"으로 갈린다.
      select count(*)::int                                    as floor_cnt,
             min(s.floor_no) filter (where s.floor_no <> 99)  as min_floor,
             max(s.floor_no) filter (where s.floor_no <> 99)  as max_floor,
             coalesce(bool_or(s.floor_no = 99), false)        as has_roof
        from v_building_floor_stack s
       where s.bld_id = rep.bld_id
    ) fs on true
    union all
    -- ⛔ 게이트에 걸리면 **0건이 아니라 한 줄**이다 — 0건이면 화면이 "그런 가게가 없다"고
    --    말하게 되는데 사실은 "너무 많다"이다. 지금의 search_scope 는 상호를 안 세므로
    --    (그걸 고치면 "기존 검색 함수 불변"이 깨진다) 이 함수가 제 총계를 함께 낸다.
    select
      null::char(19), null::text, null::text, null::text, null::text,
      null::double precision, null::double precision,
      null::int, null::int, null::smallint, null::smallint, null::boolean,
      null::text[], null::int,
      gr.total_parcel_cnt, gr.total_store_cnt,
      true, gr.store_snapshot_ym::text,
      false
    from (
      select max(t.total_parcel_cnt) as total_parcel_cnt,
             max(t.total_store_cnt)  as total_store_cnt,
             max(t.store_snapshot_ym) as store_snapshot_ym
        from tot t
    ) gr
    cross join gate g
    where g.broad
  )
  select
    o.pnu, o.bld_id, o.bld_nm, o.road_addr, o.jibun_addr, o.lat, o.lng,
    o.bld_cnt_in_pnu, o.floor_cnt, o.min_floor, o.max_floor, o.has_roof,
    o.matched_names, o.match_store_cnt, o.total_parcel_cnt, o.total_store_cnt,
    o.too_broad, o.store_snapshot_ym
  from rows_out o
  order by
    o.too_broad        desc,
    o.match_store_cnt  desc nulls last,
    o.exact_hit        desc,
    o.road_addr        asc nulls last,
    o.pnu;
$$;

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 닫는다.
revoke all on function search_stores(text, int, text, int) from public, anon, authenticated;

comment on function search_stores(text, int, text, int) is
  '결정 0028 상호명으로 찾기 — 한 줄은 건물이 아니라 **땅(필지)** 이다(점포는 필지에만 붙는다: '
  'unit_business.unit_id 전량 NULL — 건물로 줄세우면 한 땅의 동들이 같은 가게를 복사해 갖는다). '
  '⛔ sigungu 를 안 주면 0건이다(결정 0007 — 상호는 같은 이름이 전국에 널려 있다). '
  '일치한 상호는 최대 3개(matched_names)와 그 땅의 일치 가게 수(match_store_cnt)만 나가고, '
  'biz_no·업종 코드·점포 좌표는 한 글자도 안 나간다. 층은 이 줄에 안 적는다 — 층 결측이 셋 중 '
  '하나라 있을 때만 적으면 없는 줄이 1층으로 읽히고, 가져오려면 점포 표를 되짚어야 한다(3.2초). '
  '너무 넓은 검색어는 0건이 아니라 too_broad=true 한 줄로 답한다(총 땅 수·가게 수 포함). '
  'store_snapshot_ym 은 "몇 년 몇 월 기준 점포 자료"를 화면이 적기 위한 값 — ⛔ 폐업 추정은 '
  '하지 않는다(지난 분기 가게는 안 나온다). security definer — 점포 표가 anon 에게 닫혀 있어 '
  '소유자 권한으로 대신 읽는다.';

-- api 쌍둥이 — 화면이 부르는 문. (public 원본은 닫힌 채, 이 문만 anon 에게 연다 — 2026-09-01b 규칙)
create or replace function api.search_stores(
  q        text,
  lim      int  default 50,
  sigungu  text default null,
  p_offset int  default 0
)
returns table (
  pnu               char(19),
  bld_id            text,
  bld_nm            text,
  road_addr         text,
  jibun_addr        text,
  lat               double precision,
  lng               double precision,
  bld_cnt_in_pnu    int,
  floor_cnt         int,
  min_floor         smallint,
  max_floor         smallint,
  has_roof          boolean,
  matched_names     text[],
  match_store_cnt   int,
  total_parcel_cnt  bigint,
  total_store_cnt   bigint,
  too_broad         boolean,
  store_snapshot_ym text
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.search_stores(q, lim, sigungu, p_offset) $$;

revoke all on function api.search_stores(text, int, text, int) from public, anon, authenticated;
grant execute on function api.search_stores(text, int, text, int) to anon, authenticated;

comment on function api.search_stores(text, int, text, int) is
  '결정 0028 상호명으로 찾기 — 화면이 부르는 문. 본체는 public.search_stores 이고 '
  '이 쌍둥이는 칸을 다시 나열하지 않고 통째로 넘긴다(칸 순서가 두 곳에서 갈리면 에러 없이 '
  '값이 뒤바뀐다). ⛔ public 원본은 끝까지 닫아 둔다.';

commit;

-- 함수가 늘었으므로 스키마 캐시를 다시 읽게 한다. 안 알리면 화면이 부를 때 404(PGRST202) 다
-- — DB 에는 멀쩡히 있는데 화면만 안 되는, 찾기 어려운 고장이다.
notify pgrst, 'reload schema';

-- ⛔ **맨 끝** — 커밋 뒤 제 트랜잭션에서 혼자 돈다(위 머리말 참조: drop index 의 잠금은
--    커밋까지 유지되므로 덩어리 안에 두면 요약표 굽는 내내 점포 표 읽기가 줄을 선다).
--    쓰는 코드 0건 · 186MB · 2글자 검색어는 애초에 못 탔다 — 그 일은 이제 요약표가 한다.
drop index if exists idx_ub_name;
