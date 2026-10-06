-- =====================================================================
-- 분기 표지 snapshot_release — 새 상권 분기는 '다 넣은 뒤 한 번에' (2026-10-07a · 결정 0035)
-- =====================================================================
--
-- 왜
-- --
-- 화면은 창고의 **가장 새 분기**를 바로 보여 줬다 — `snapshot_ym = (select max(snapshot_ym)
-- from unit_business)`. 그런데 분기 적재기(scripts/collectors/load_sangkwon_snapshot.py)는 한
-- 트랜잭션이 아니다: 시·도 파일마다 1,000행씩 약 2시간 올린다(결정 0005). 첫 1,000행이 들어가는
-- 순간부터 max() 가 새 분기를 가리켜, 그 2시간 동안 손님은 **반쯤 찬 새 분기**(대부분 건물의 가게
-- 칸이 빔)를 보고, 적재가 중간에 죽으면 그 반쪽이 그대로 남는다(append-only 라 지우지도 않는다).
-- ⇒ 분기를 max() 대신 **표지 두 칸**에서 읽는다:
--      loaded_ym    = 다 들어온 분기 — 적재기가 전국 적재 + 교차검증 통과 뒤 RPC 로 적는다.
--                     요약표 셋은 이 칸으로 굽는다.
--      published_ym = 화면이 보는 분기 — post_load.py 가 요약표를 구운 뒤 올린다.
--                     이 UPDATE 한 줄에 모든 카드가 한순간에 바뀐다.
--
-- 무엇이 생기나 / 바뀌나
-- ----------------------
--   ① 표 snapshot_release(한 줄 · id = 1) + comment + RLS + 권한 회수(정책 0) + 첫 줄
--      (1, '202606', now(), 2772484, '202606', now()) — **적용 직후 화면은 그대로다.**
--   ② RPC api.mark_snapshot_loaded(p_ym text, p_rows int) returns jsonb — 적재기 전용.
--      security definer · search_path '' · revoke public/anon/authenticated · **service_role 만**.
--      공개 호출 허용 총계 28 그대로(post_load --check 허용 목록에 넣지 않는다).
--   ③ 요약표 셋을 새 기준(loaded_ym)으로 **임시 이름(_next)에 먼저 굽는다** — 화면이 쓰는
--      옛 표를 안 건드리므로 잠금 0. 색인도 임시 이름으로 · analyze · 권한 회수.
--        mv_parcel_store_names_next(88MB · 약 2분) · mv_district_industry_mix_next(약 30초) ·
--        mv_coverage_stats_next(1줄)
--   ④ 실시간 셋을 published_ym 으로: v_floor_stack(create or replace view — 권한·api 뷰 유지) ·
--      list_district_buildings · get_data_freshness(basis) — 함수는 머리(security definer ·
--      set search_path · stable)와 comment 를 정본에서 글자 그대로.
--      list_industry_mix · list_industry_detail 은 2순위(요약표가 비었을 때)만 published_ym 으로.
--   ⑤ 바꿔 끼우기(짧은 잠금 순간): 옛 요약표 drop → 임시 이름을 정본 이름으로 rename →
--      색인 이름도 rename(idx_mpsn_pnu · idx_mpsn_sigungu · idx_mpsn_names · idx_mcs_snapshot_ym ·
--      mv_district_industry_mix_key). mv_coverage_stats 는 v_coverage_stats 가 매달려 있어
--      먼저 뷰를 _next 로 옮겨 묶고(create or replace view — 권한 유지 · api.v_coverage_stats 는
--      뷰를 보므로 무변경) 옛 표를 지운 뒤 rename · 뷰를 정본 글자로 다시 적는다.
--
-- 순서 — 왜 정본(schema.sql)과 다른가
-- ------------------------------------
-- 한 트랜잭션 안에서 잡은 잠금은 **commit 까지** 쥔다. 화면이 읽는 객체(v_floor_stack · 옛
-- 요약표)에 거는 잠금을 앞에 두면 요약표를 굽는 2~3분 내내 화면 읽기가 그 뒤에 줄을 선다.
-- 그래서 느린 굽기(③)를 **먼저**, 화면 객체를 바꾸는 짧은 문장(④⑤)을 **뒤**에 둔다.
--
-- 잠금
-- ----
--   · ③ create materialized view _next — 원본 표(unit_business·parcel·building·district)에
--     ACCESS SHARE 만(읽기). 화면을 안 막는다.
--   · ④ create or replace view v_floor_stack · create or replace function — 뷰를 바꿀 때 그 뷰에
--     ACCESS EXCLUSIVE(commit 까지 · 몇 ms 짜리 문장 뒤 곧 commit).
--   · ⑤ drop materialized view(옛 표) — ACCESS EXCLUSIVE(PostgreSQL 17 문서 13.3 「DROP TABLE」 —
--     물질화뷰 drop 도 같은 수준). alter materialized view … rename — ACCESS EXCLUSIVE(sql-altertable
--     "unless explicitly noted" · 새로 만든 _next 라 기다릴 상대가 없다). alter index … rename —
--     SHARE UPDATE EXCLUSIVE(sql-alterindex).
--   · 기다림의 상한 `lock_timeout = '2s'` 를 **begin 앞**(세션 설정)에 둔다 — 가게 검색이 옛 표를
--     쥐고 있어 2초 넘게 못 잡으면 덩어리가 통째로 되돌아가 아무것도 안 바뀐다(굽기 2~3분이
--     헛수고가 될 뿐 — 한가한 시간에 다시 돌린다).
--   · `statement_timeout = '900s'` — dbx.py 연결의 제한이 2분이라 가게 이름 표 굽기(약 2분)가
--     잘릴 수 있다(2026-09-27e·10-01b 선례).
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 옛 표를 지우고 새 표 이름을 아직 안 바꾼 채 끊기면 가게
-- 검색·각주·업종 카드가 통째로 사라진다. 한 덩어리로 묶는다. `notify pgrst` 는 commit **뒤**.
--
-- 실행 (한가한 시간 · 머지 뒤 · Claude 가 dbx 로)
-- -----------------------------------------------
--   python scripts/dbx.py -f supabase/migrations/2026-10-07a_snapshot_release.sql
--   → 이어서 python scripts/post_load.py --check (0 이어야 한다 — 표지 202606/202606 · 요약표 202606)
--
-- 적용한 사람이 보게 되는 것 (파일의 실제 문장 순서)
-- --------------------------------------------------
--   SET ×2 · BEGIN · CREATE TABLE · COMMENT ×4 · ALTER TABLE · REVOKE · INSERT 0 1 ·
--   CREATE FUNCTION · COMMENT · REVOKE · GRANT ·
--   SELECT(굽기 — CREATE MATERIALIZED VIEW 는 'SELECT n' 으로 찍힌다) ×3 사이사이 CREATE INDEX ×5 ·
--   ANALYZE ×3 · REVOKE ×3 ·
--   CREATE VIEW · ALTER VIEW · CREATE FUNCTION ×4 · COMMENT ×4 · REVOKE ×4 ·
--   DROP MATERIALIZED VIEW · ALTER MATERIALIZED VIEW · ALTER INDEX ×3 · (가게 이름 표)
--   DROP MATERIALIZED VIEW · ALTER MATERIALIZED VIEW · ALTER INDEX · (업종 표)
--   CREATE VIEW · DROP MATERIALIZED VIEW · ALTER MATERIALIZED VIEW · ALTER INDEX · CREATE VIEW ·
--   ALTER VIEW · (각주 표)  COMMENT ×4 · REVOKE ×3 · COMMIT · NOTIFY
--
-- 적용 뒤 확인 (결정 0035 「적용 뒤 확인」 그대로 — dbx + anon 키로 **화면 요청 그대로**)
-- ----------------------------------------------------------------------------------
--   select * from snapshot_release;                               -- 1줄 · loaded_ym 202606 · published_ym 202606
--   python scripts/post_load.py --check                            -- exit 0
--   select snapshot_ym from mv_coverage_stats;                     -- 202606
--   select max(snapshot_ym) from mv_district_industry_mix;         -- 202606
--   select distinct store_snapshot_ym from mv_parcel_store_names;  -- 202606 한 줄
--   select indexrelname from pg_stat_user_indexes
--    where relname in ('mv_parcel_store_names','mv_coverage_stats','mv_district_industry_mix')
--    order by 1;  -- idx_mcs_snapshot_ym · idx_mpsn_names · idx_mpsn_pnu · idx_mpsn_sigungu · mv_district_industry_mix_key
--   select relname, relacl from pg_class
--    where relname in ('v_floor_stack','v_coverage_stats','mv_coverage_stats','mv_parcel_store_names',
--                      'mv_district_industry_mix','snapshot_release');  -- 뷰 둘만 anon=r · 나머지 anon 없음
--   anon 키(화면 요청 그대로):
--     GET  /rest/v1/v_coverage_stats                                   → 200 · 1행 · snapshot_ym 202606
--     GET  /rest/v1/v_floor_stack?pnu=eq.<강남 필지>&select=floor_no,store_cnt → 200 · 가게 수 적용 전과 같음
--     POST /rest/v1/rpc/list_industry_mix  {"p_pnu":"<같은 필지>"}       → 200 · snapshot_ym 202606
--     POST /rest/v1/rpc/get_data_freshness                              → 200 · 첫 줄 basis 202606
--     POST /rest/v1/rpc/mark_snapshot_loaded {"p_ym":"202606","p_rows":1} → 401/403(anon 은 못 부른다)
--   가게 검색: 적용 전후 같은 검색어(카페·스타벅스 · 강남)의 결과 diff 0.
--   눈 확인: 넓은 화면·412px — 층별 화면 가게 칸·각주·업종 카드·신선도 표 변화 0.
--
-- 되돌리기 = **새 마이그레이션 파일**(뷰·함수·요약표를 max(snapshot_ym) 판으로 되돌리고 RPC·표 drop)
-- **+ 이 PR revert**. 적용된 이 파일은 고치지 않는다(원장). 표지만 옛 분기로 돌리는 것은
-- `python scripts/publish_snapshot.py --ym <분기>` → `python scripts/post_load.py`.

set statement_timeout = '900s';
set lock_timeout = '2s';

begin;

-- ── ① 표지 표 ─────────────────────────────────────────────────────────────
create table if not exists snapshot_release (
  id            int primary key default 1 check (id = 1),
  loaded_ym     char(6) not null check (loaded_ym ~ '^\d{6}$'),
  loaded_at     timestamptz not null default now(),
  loaded_rows   int,
  published_ym  char(6) not null check (published_ym ~ '^\d{6}$'),
  published_at  timestamptz not null default now()
);

comment on table snapshot_release is
  '결정 0035 분기 표지 — 한 줄뿐(id = 1). loaded_ym = 다 들어온 분기(적재기가 RPC 로 · 요약표가 이 칸으로 굽는다), '
  'published_ym = 화면이 보는 분기(post_load.py 가 요약표를 구운 뒤 올린다). 0줄이면 화면 가게 칸이 조용히 빈다 — '
  'post_load.py --check 가 [사고]로 잡는다. 공개키 접근 0(RLS 켬 + 정책 0 + 권한 회수)';
comment on column snapshot_release.loaded_ym is
  '다 들어온 분기(YYYYMM). 적재기가 전국 적재 + 교차검증 통과 뒤 api.mark_snapshot_loaded 로 적는다 — loaded_ym 이하인 분기는 무시(앞으로만 — 같은 분기 재실행·옛 분기 백필이 표지를 끌어내리지 않게)';
comment on column snapshot_release.loaded_rows is
  '표지를 적을 때 적재기가 센 그 분기 행 수(교차검증 값) — post_load.py --check 가 지금 행 수와 대조해 다르면 [주의]';
comment on column snapshot_release.published_ym is
  '화면이 보는 분기(YYYYMM). post_load.py 가 분기와 무관한 판정을 지난 뒤 분기 요약표 셋 굽기·분기 대조와 같은 트랜잭션에서 loaded_ym 으로 올린다(커밋 순간 넷이 함께 바뀜) — 되돌리기는 publish_snapshot.py --ym';

alter table snapshot_release enable row level security;

-- ⛔ Supabase 는 새 표를 anon 에 자동으로 연다(pg_default_acl) — 만든 자리에서 닫는다.
revoke all on snapshot_release from public, anon, authenticated;

-- 처음 한 줄 = 2026-10-06 라이브 상태(202606 2,772,484행) — 적용 직후 화면은 그대로다.
-- 이미 있으면 건드리지 않는다(정본을 다시 돌려도 지금 표지를 되돌리지 않게).
insert into snapshot_release (id, loaded_ym, loaded_at, loaded_rows, published_ym, published_at)
values (1, '202606', now(), 2772484, '202606', now())
on conflict (id) do nothing;

-- ── ② 적재기 전용 RPC ─────────────────────────────────────────────────────
create or replace function api.mark_snapshot_loaded(p_ym text, p_rows int)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_cur public.snapshot_release;
begin
  if p_ym is null or p_ym !~ '^\d{6}$' then
    raise exception '분기는 YYYYMM 여섯 자리여야 합니다 (받은 값: %)', p_ym
      using errcode = '22023';
  end if;
  if not exists (select 1 from public.unit_business u where u.snapshot_ym = p_ym::char(6)) then
    raise exception '점포 표(unit_business)에 % 분기 행이 없습니다 — 적재가 끝난 뒤에 부르세요', p_ym
      using errcode = '22023';
  end if;
  select * into v_cur from public.snapshot_release r where r.id = 1 for update;
  if not found then
    raise exception '표지(snapshot_release)가 비었습니다 — python scripts/publish_snapshot.py --ym <분기> 로 먼저 채우세요'
      using errcode = '55000';
  end if;
  if p_ym <= v_cur.loaded_ym::text then
    return to_jsonb(v_cur);
  end if;
  update public.snapshot_release r
     set loaded_ym = p_ym, loaded_at = now(), loaded_rows = p_rows
   where r.id = 1
  returning * into v_cur;
  return to_jsonb(v_cur);
end
$$;

comment on function api.mark_snapshot_loaded(text, int) is
  '결정 0035 — 적재기가 전국 적재 + 교차검증 일치 뒤 부르는 분기 표지 올리기(loaded_ym · loaded_at · loaded_rows). '
  '분기 모양이 YYYYMM 이 아니거나 점포 표에 그 분기 행이 0 이면 에러. loaded_ym 이하(이미 들어온 분기·같은 분기 '
  '재실행·옛 분기 백필)는 아무것도 안 바꾸고 지금 표지를 돌려준다(앞으로만 — loaded ≥ published 가 늘 성립). '
  '화면 기준(published_ym)은 안 건드린다 — '
  'post_load.py 가 요약표를 구운 뒤 올린다. service_role 전용(공개 호출 허용 목록 밖).';

-- ⛔ 만든 자리에서 닫고 service_role 에게만 준다(공개키는 부르지 못한다).
revoke all on function api.mark_snapshot_loaded(text, int) from public, anon, authenticated;
grant execute on function api.mark_snapshot_loaded(text, int) to service_role;

-- ── ③ 요약표 셋을 임시 이름으로 먼저 굽는다(화면이 쓰는 옛 표는 안 건드린다 — 잠금 0) ──
-- 본문은 정본 schema.sql 의 같은 요약표와 글자 그대로다(이름만 _next).
create materialized view mv_parcel_store_names_next as
with latest as (
  -- ⚠️ **전역** 한 분기다(지역별로 고르지 않는다) — v_floor_stack·mv_coverage_stats
  --    와 같은 기준이라, 한 지역만 분기가 밀리면 그 지역 가게가 통째로 안 나오는 알려진
  --    결함을 그대로 물려받는다(결정 0028 결정 1 · 알려진한계 §4). 여기서 한 번만 구한다.
  -- ⛔ 표지의 **loaded_ym**(다 들어온 분기)이다 — published 가 아니다(결정 0035). post_load 가
  --    새 분기로 먼저 굽고 나서 published 를 올려야 화면이 한순간에 바뀐다.
  select r.loaded_ym as ym from snapshot_release r
)
select
  pc.pnu,
  substr(pc.pnu, 1, 5)::char(5) as sigungu_code,   -- 검색 범위를 좁히는 칸
  -- ⛔ distinct 로 접지 않는다 — **점포마다 한 항목**이어야 "이 이름의 가게 N곳"을
  --    이 표 한 줄 안에서 셀 수 있다. 접으면 그 수를 세러 점포 표를 되짚어야 하는데,
  --    그 2단계가 찬 캐시 3.2초였다(강남 시제품 실측). 접어도 에러는 안 나고 숫자만
  --    조용히 작아진다(같은 이름 가게가 한 곳으로 세어진다).
  s.store_names,
  -- 찾을 때 훑는 칸. 같은 이름이 여럿이면 한 번만 담는다(찾기에는 있으면 되고, 세는 것은
  -- 위 배열이 한다). ⛔ 건물 이름과 **같은 자**(search_key = 공백 제거 + 소문자)로 자른다 —
  -- 같은 검색어에 건물과 상호가 다른 답을 내면 안 된다.
  s.store_names_key,
  -- 그 땅의 가게 수 전부. 화면이 적는 "일치한 가게 수"와는 **다른 값**이다(그건 검색어에
  -- 걸린 것만 센다). ⓘ **지금 이 칸을 읽는 코드는 없다** — 위 lateral 의 별칭 `s` 를 보는
  -- 조인 조건(`s.store_cnt > 0`)은 이 칸이 아니라 그 별칭을 본다. 다음에 쓸 값으로 남겨
  -- 둔다(2026-09-10 검토관 지적 — 예전 주석은 "조인 조건으로 못 박는 데 쓴다"고 적어
  -- 실제와 달랐다).
  s.store_cnt,
  -- 화면이 "2026년 6월 기준 점포 자료" 도장을 찍는 값(전 행 같다 — 화면에 숫자 리터럴 0).
  (select l.ym from latest l)::char(6) as store_snapshot_ym
from parcel pc
join lateral (
  select
    array_agg(ub.biz_name order by ub.biz_name)       as store_names,
    string_agg(distinct search_key(ub.biz_name), '|') as store_names_key,
    count(*)::int                                     as store_cnt
  from unit_business ub
  where ub.pnu = pc.pnu
    -- ⓘ 스칼라 하위질의라 한 번만 계산되고(InitPlan) 상수처럼 쓰인다 —
    --    그래야 idx_ub_pnu_cat (pnu, snapshot_ym) 이 이 조회를 그대로 받친다.
    --    조인 조건(`ub.snapshot_ym = latest.ym`)으로 바꾸면 에러 없이 느려지기만 한다.
    and ub.snapshot_ym = (select l.ym from latest l)
    and ub.biz_name is not null
) s on s.store_cnt > 0
-- ⛔ **건물이 있는 필지만** — 위 mv_search_parcel 과 같은 포함 규칙이다. 갈리면 상호로
--    찾아 들어간 땅이 주소로는 안 나오는(또는 그 반대의) 모순이 난다.
-- ⛔ 그렇다고 mv_search_parcel 을 **참조해서** 쓰지 않는다 — 참조하는 순간 이 표가 그
--    사슬에 하나 더 매달려, 다음에 그 표를 손볼 때 여기까지 함께 딸려 온다(이 표를 형제로
--    세운 이유가 통째로 사라진다).
where exists (select 1 from building b where b.pnu = pc.pnu);

-- 색인도 임시 이름 — ⑤ 에서 정본 이름으로 바꾼다(유일 색인이 없으면 refresh concurrently 가 멈춘다).
create unique index idx_mpsn_pnu_next     on mv_parcel_store_names_next (pnu);
create index idx_mpsn_sigungu_next        on mv_parcel_store_names_next (sigungu_code);
create index idx_mpsn_names_next          on mv_parcel_store_names_next using gin (store_names_key gin_trgm_ops);
analyze mv_parcel_store_names_next;
-- ⛔ 새 물질화뷰는 anon 에게 자동으로 열린다(pg_default_acl) — 만든 자리에서 닫는다.
revoke all on mv_parcel_store_names_next from public, anon, authenticated;

create materialized view mv_district_industry_mix_next as
select d.district_id,
       ub.snapshot_ym,
       ub.cat_l_cd, ub.cat_l_nm,
       ub.cat_m_cd, ub.cat_m_nm,
       count(*)::int as n
from district d
join unit_business ub
  on ub.geom is not null
 and st_contains(d.geom, ub.geom)
where ub.snapshot_ym = (select r.loaded_ym from snapshot_release r)   -- 표지 loaded_ym(결정 0035)
group by 1, 2, 3, 4, 5, 6;

create unique index mv_district_industry_mix_key_next
  on mv_district_industry_mix_next (district_id, snapshot_ym, cat_m_cd);
analyze mv_district_industry_mix_next;
revoke all on mv_district_industry_mix_next from public, anon, authenticated;

create materialized view mv_coverage_stats_next as
select
  ub.snapshot_ym,
  count(*)                                                    as store_cnt,
  count(*) filter (where ub.floor_no is null)                 as floor_missing_cnt,
  round(100.0 * count(*) filter (where ub.floor_no is null)
        / count(*), 1)                                        as floor_missing_pct
from unit_business ub
where ub.snapshot_ym = (select r.loaded_ym from snapshot_release r)   -- 표지 loaded_ym(결정 0035)
  -- 서비스 지역(화면에서 고를 수 있는 구)만 센다 — 전국을 세면 화면이 보여주지도 않는
  -- 지역까지 섞여 결측률이 15.3%p 과장된다(2026-08-22 실측 50.3% vs 35.0%).
  -- 목록을 여기 베껴 적지 않고 mv_open_sigungu 를 그대로 읽는 이유: 자료가 늘 때
  -- 각주만 낡는 드리프트를 막으려고(확정설계 9 — 열린 지역의 진실은 서버 한 곳).
  -- ⚠️ `::char(5)` 로 타입을 맞춘다. substr(char) 의 결과는 text 인데 sigungu_code 는
  --    char(5) 라, 안 맞추면 비교마다 캐스트가 낀다(2026-08-16b 와 같은 병).
  -- ℹ️ pnu 가 NULL 인 행(실측 1,819)은 지역 특정 불가라 분모에서 빠진다.
  and substr(ub.pnu, 1, 5)::char(5) in (select sigungu_code from mv_open_sigungu)
group by ub.snapshot_ym;

create unique index idx_mcs_snapshot_ym_next on mv_coverage_stats_next (snapshot_ym);
analyze mv_coverage_stats_next;
revoke all on mv_coverage_stats_next from public, anon, authenticated;

-- ── ④ 실시간 셋을 published_ym 으로 · 2순위 둘 ──────────────────────────────
-- create or replace view 는 권한(anon SELECT)과 위에 매달린 api.v_floor_stack 을 그대로 둔다.
create or replace view v_floor_stack as
select
  s.bld_id,
  s.pnu,
  s.floor_no,
  s.floor_label,
  s.floor_area_m2,
  s.floor_area_gross_m2,
  s.segment_cnt,
  s.main_use,
  s.uses,
  -- ⚠️ 원본 건물명이 아니라 화면에 보일 이름이다(동명칭 폴백 + 개인 성명 가림).
  --    원본은 building.bld_nm 에 그대로 있고, 이 뷰는 내보낼 때만 가린다.
  b.display_nm as bld_nm,   -- 함수를 부르지 않는다(위 §표시명 저장 컬럼 참조)
  b.approve_date,
  b.is_jiphap,
  p.road_addr,
  p.road_contact,
  pb.bld_cnt_in_pnu,
  st.store_cnt,
  st.stores,
  -- ── 건물 스펙 4칸 (2026-08-24a · 로드맵 Wave 2 PR-B) ──────────────────────
  -- 층이 아니라 **건물 한 채**의 값이라 같은 건물의 모든 층 행에 같은 값이 실린다
  -- (화면은 head 행 하나만 읽는다). 원본을 그대로 낸다 — 0 을 NULL 로 바꾸는 것도
  -- 상한을 거는 것도 여기서 하지 않는다. 서버가 뜻을 지어내면 나중에 그 판단을 누가
  -- 어디서 했는지 못 찾는다(집계·백테스트는 원본이 필요하다).
  -- ⛔ 0 은 "0" 이 아니라 **대장 미기재**다 — 롯데월드타워가 주차 0·건폐율 0 으로
  --    들어와 있어 값으로는 둘을 못 가른다. "NULL 이 0행" 은 현재 적재분(서울·대전
  --    30개 구)의 관찰값이지 구조적 보장이 아니다(적재기는 결측을 NULL 로 쓴다 —
  --    load_building_ledger.py 의 _to_float·sum_parking). [C] 전국 적재 후 다시 셀 것.
  --    뜻풀이(0·NULL 둘 다 "미상")는 화면 한 곳에서만 한다.
  b.total_area_m2,          -- 연면적 ㎡ (0 = 미기재)
  b.far,                    -- 용적률 % (0 = 미기재)
  b.bcr,                    -- 건폐율 % (0 = 미기재, 소스 오류로 100 초과 실재)
  b.parking_cnt,            -- 주차 4종(옥내외 × 자주/기계) 합 (0 = 미기재, 일부만 적힌 대장이면 부분합)
  -- ── 2026-08-25a 가 더한 좌표 2칸 (링크로 들어온 사람의 건물 되살리기) ──────
  -- ⛔ parcel.lat/lng **칸이 아니라** geom 에서 뽑는다. 검색(search_buildings)과 상권
  --    판정(list_building_districts)이 전부 geom 을 보므로 같은 칸을 봐야 한다. 칸을
  --    섞으면 같은 건물인데 **들어온 길에 따라 마커 자리가 갈리고**, 에러가 안 나서
  --    못 찾는다("지도 마커는 상권 밖인데 글자는 상권 안") — 2026-08-14e 가 정한 규칙.
  -- ⓘ 필지 도형의 대표 좌표라 한 땅에 건물이 여럿이면 같은 자리에 찍힌다(검색도 동일).
  --    좌표 없는 필지는 NULL 이고 화면은 마커를 생략한다(0,0 으로 채우지 않는다).
  st_y(p.geom)::double precision as lat,
  st_x(p.geom)::double precision as lng
from v_building_floor_stack s
join building b on b.bld_id = s.bld_id
join parcel   p on p.pnu    = s.pnu
join lateral (
  select count(*)::int as bld_cnt_in_pnu
  from building b2
  where b2.pnu = s.pnu
) pb on true
left join lateral (
  select
    count(*)::int as store_cnt,
    jsonb_agg(jsonb_build_object('name', ub.biz_name, 'cat', ub.cat_s_nm)) as stores
  from unit_business ub
  where ub.pnu = s.pnu
    and ub.floor_no = s.floor_no
    and ub.snapshot_ym = (select r.published_ym from snapshot_release r)
) st on true;

-- create or replace view 는 뷰 옵션을 새 정의(옵션 없음)로 갈아 끼운다 — 정본과 같게 다시 적는다.
alter view v_floor_stack set (security_invoker = false);

-- ⛔ 함수 넷은 머리(security definer · set search_path · stable)와 comment 까지 정본에서 글자 그대로.
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
             (select r.published_ym from snapshot_release r)) as ym
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

revoke all on function list_industry_mix(text) from public, anon, authenticated;

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

revoke all on function list_industry_detail(text, text) from public, anon, authenticated;

create or replace function list_district_buildings(
  p_district_id text,
  p_limit       int default 50,
  p_offset      int default 0
)
returns table (
  pnu              char(19),
  store_cnt        int,        -- 이 **땅**의 점포 수(최신 분기)
  bld_cnt_in_pnu   int,        -- 1 보다 크면 화면이 "같은 땅에 N동"을 적는다
  bld_id           text,       -- 대표 동 = 연면적 최대. 아래 칸들은 검색 결과와 같은 모양
  bld_nm           text,
  road_addr        text,
  jibun_addr       text,
  lat              double precision,
  lng              double precision,
  floor_cnt        int,
  min_floor        smallint,
  max_floor        smallint,
  has_roof         boolean,
  total_parcel_cnt bigint,     -- 상한에 잘리기 전 전체 규모(모든 행에 같은 값)
  total_bld_cnt    bigint
)
language sql
stable
security definer
set search_path = public
as $$
  with scope as (
    -- ⛔ 정방향(list_building_districts)과 같은 판정. 좌표 없는 필지는 아예 안 본다 —
    --    st_contains 가 NULL 을 거짓으로 흘리면 "상권 밖"이라는 **단정**이 되어 버린다.
    select p.pnu
    from district d
    join parcel p on st_contains(d.geom, p.geom)
    where d.district_id = p_district_id
      and p.geom is not null
  ),
  elig as (
    -- 층 자료가 아예 없는 건물은 눌러도 빈 화면이라 뺀다
    -- (검색과 **같은 규칙** — 2026-08-13 실측 242,631 중 239동).
    select b.bld_id, b.pnu, b.display_nm, b.total_area_m2
    from scope sc
    join building b on b.pnu = sc.pnu
    where exists (
      select 1 from building_floor f
      where f.bld_id = b.bld_id and f.floor_no is not null
    )
  ),
  stores as (
    select ub.pnu, count(*)::int as n
    from unit_business ub
    join scope sc on sc.pnu = ub.pnu
    where ub.snapshot_ym = (select r.published_ym from snapshot_release r)
    group by 1
  ),
  land as (
    -- ⓘ 창 함수는 GROUP BY **뒤에** 돈다 → count(*) over () = 땅 수,
    --    sum(count(*)) over () = 동 수. 둘을 한 번에 얻으려고 이 모양을 쓴다.
    select e.pnu,
           coalesce(max(s.n), 0)::int as store_cnt,
           count(*)::int              as bld_cnt_in_pnu,
           count(*)      over ()      as total_parcel_cnt,
           sum(count(*)) over ()      as total_bld_cnt
    from elig e
    left join stores s on s.pnu = e.pnu
    group by e.pnu
  ),
  page as (
    -- ⛔ 무거운 조인(주소 조립·좌표·층 집계) 전에 **상한을 먼저** 건다.
    --    검색 함수가 "25행에만 필요하다"며 쓰는 것과 같은 수법이다.
    -- 정렬 tie-break 에 pnu 를 둔다 — 없으면 같은 점포 수끼리 순서가 흔들려
    -- '더 보기'가 이미 본 줄을 다시 가져오거나 건너뛴다.
    select *
    from land
    order by store_cnt desc, pnu
    limit  greatest(1, least(coalesce(p_limit, 50), 200))
    offset greatest(0, coalesce(p_offset, 0))
  )
  select
    pg.pnu,
    pg.store_cnt,
    pg.bld_cnt_in_pnu,
    rep.bld_id,
    rep.display_nm as bld_nm,
    p.road_addr,
    parcel_jibun_addr(p.sido_nm, p.sigungu_nm, p.emd_nm, p.jibun) as jibun_addr,
    -- ⛔ 좌표는 geom 에서만 뽑는다. parcel 의 lat/lng **칸**을 쓰면 검색·상권판정과
    --    자리가 갈려 "마커는 상권 밖인데 글자는 상권 안"이 된다(2026-08-14e 규칙).
    st_y(p.geom)::double precision as lat,
    st_x(p.geom)::double precision as lng,
    fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof,
    pg.total_parcel_cnt,
    pg.total_bld_cnt
  from page pg
  join parcel p on p.pnu = pg.pnu
  join lateral (
    select e.bld_id, e.display_nm
    from elig e
    where e.pnu = pg.pnu
    order by e.total_area_m2 desc nulls last, e.bld_id
    limit 1
  ) rep on true
  join lateral (
    -- ⛔ 층수 규칙을 여기서 새로 정하지 않는다 — 검색 함수의 것을 글자 그대로 옮겼다.
    --    갈리면 같은 건물이 들어온 길에 따라 "지하2~15층"과 "지하2~99층"으로 갈린다.
    select count(*)::int                                    as floor_cnt,
           min(s.floor_no) filter (where s.floor_no <> 99)  as min_floor,
           max(s.floor_no) filter (where s.floor_no <> 99)  as max_floor,
           coalesce(bool_or(s.floor_no = 99), false)        as has_roof
    from v_building_floor_stack s
    where s.bld_id = rep.bld_id
  ) fs on true
  order by pg.store_cnt desc, pg.pnu;
$$;

comment on function list_district_buildings(text, int, int) is
  '상권 하나에 속한 **땅(필지)** 목록을 점포 많은 순으로. 정방향 list_building_districts 와 '
  '같은 판정(st_contains + parcel.geom)을 써야 두 화면이 같은 말을 한다. '
  'store_cnt 는 **그 땅**의 점포 수다(건물별로는 영영 못 가른다 — unit_business.unit_id 전량 NULL). '
  '한 땅에 여러 동이면 대표 동(연면적 최대) 한 채만 싣고 bld_cnt_in_pnu 로 몇 동인지 알린다.';

revoke all on function list_district_buildings(text, int, int) from public, anon, authenticated;

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

-- ── ⑤ 바꿔 끼우기 — 옛 요약표 drop → 임시 이름을 정본 이름으로 ────────────────
-- (옛 표의 색인은 표와 함께 사라지므로 이름이 비어 rename 이 된다.)
drop materialized view mv_parcel_store_names;
alter materialized view mv_parcel_store_names_next rename to mv_parcel_store_names;
alter index idx_mpsn_pnu_next     rename to idx_mpsn_pnu;
alter index idx_mpsn_sigungu_next rename to idx_mpsn_sigungu;
alter index idx_mpsn_names_next   rename to idx_mpsn_names;

drop materialized view mv_district_industry_mix;
alter materialized view mv_district_industry_mix_next rename to mv_district_industry_mix;
alter index mv_district_industry_mix_key_next rename to mv_district_industry_mix_key;

-- mv_coverage_stats 에는 v_coverage_stats(→ api.v_coverage_stats)가 매달려 있다 — 옛 표를 지우기 전에
-- 뷰를 새 표로 옮겨 묶는다(create or replace view — drop 이 아니라 권한이 유지된다).
create or replace view v_coverage_stats as select * from mv_coverage_stats_next;
drop materialized view mv_coverage_stats;
alter materialized view mv_coverage_stats_next rename to mv_coverage_stats;
alter index idx_mcs_snapshot_ym_next rename to idx_mcs_snapshot_ym;
-- 정본 글자로 다시 적는다(이름이 바뀌었을 뿐 같은 표다 — 뷰 정의를 정본과 맞춘다).
create or replace view v_coverage_stats as
select * from mv_coverage_stats;
alter view v_coverage_stats set (security_invoker = false);

comment on view v_coverage_stats is
  '§8.6 스택 뷰 각주용 집계. **미리 계산해 둔 mv_coverage_stats 한 줄을 그대로 내보낸다** '
  '(2026-08-22d — 실시간 집계는 2.1~4.9초로 anon 3초 제한을 넘나들었다). '
  '★ 범위는 **서비스 지역(mv_open_sigungu = 화면에서 고를 수 있는 구)** 뿐이다(2026-08-22a). '
  '전국을 세면 화면이 보여주지도 않는 지역까지 섞여 결측률이 15.3%p 과장된다(50.3% vs 35.0%). '
  '분기 기준은 표지 loaded_ym(화면은 published — post_load 가 구운 뒤 올린다 · 결정 0035) — v_floor_stack 과 둘을 항상 함께 고칠 것. '
  'ℹ️ pnu 가 NULL 인 행(실측 1,819)은 지역 특정 불가라 분모에서 빠진다. '
  'ℹ️ 신선도 = python scripts/post_load.py 시점 — 그 스크립트의 --check 가 낡음을 잡는다. '
  '★ 공개 접근: anon/authenticated에게 SELECT **만** 허용(집계값만, 상호명 없음). '
  '⛔ drop 하지 말 것 — GRANT 가 날아가는데 post_load --check 는 "닫힌 것"을 못 잡는다. '
  'ℹ️ 린트 0010(security definer view) 의도적 예외 — security_invoker=true로 되돌리면 원본 표 401. '
  '재검토 방아쇠: 공개 배포일 / 지도·반경 검색(§6.4) 착수일';

comment on materialized view mv_parcel_store_names is
  '§8.1 상호명으로 찾기 전용 요약표(2026-09-09c · 결정 0028) — 땅 한 줄에 **그 땅의 가게 '
  '이름들**을 미리 모아 둔다. 형제 mv_search_parcel 과 같은 포함 규칙(건물이 있는 필지만)을 '
  '쓰되 **참조하지는 않는다** — 그 표에 칸을 더하면 거기 기대어 사는 넷(mv_open_sigungu → '
  'mv_coverage_stats → v_coverage_stats → api.v_coverage_stats)까지 떨어뜨렸다 되세워야 하고, '
  '그건 "drop 하고 다시 만들지 말 것"이라 못 박아 둔 뷰를 건드리는 일이다. '
  'store_names 는 **점포마다 한 항목**(중복 포함)이라 "이 이름의 가게 N곳"을 한 줄 안에서 '
  '셀 수 있고, store_names_key 는 그 이름들을 건물과 같은 자(search_key)로 잘라 | 로 이은 것 '
  '— 그 위에 idx_mpsn_names(gin_trgm)가 선다. 점포 표(277만 행)를 직접 훑으면 2글자 검색어가 '
  'trigram 을 못 타 7.6초인데 이 표(구 안 1.2만 행)에서는 10ms 다. '
  '⚠️ 자료를 새로 넣으면 `python scripts/post_load.py` 를 반드시 돌릴 것 — '
  '안 하면 새 가게가 조용히 검색에서 빠진다(에러가 아니다).';

comment on materialized view mv_district_industry_mix is
  '상권 × 업종(중분류) 점포 수 — 최신 분기 한 개만. 살아있는 쿼리는 찬 캐시에서 12.5초라 '
  '미리 굽는다(라이브 실측, 굽기 26.7초 · 읽기 0.32ms). 대분류는 이 표를 합쳐서 낸다. '
  '⚠️ 상권이 겹치는 자리의 점포는 **양쪽에 모두** 세어진다(2026-08-22 실측: 상권 안 462,858곳 중 '
  '17,946곳 = 3.9% 가 두 상권에 겹침, 3겹은 0건). 상권끼리 더하면 그만큼 부풀려진다. '
  '⚠️ 어느 분기인지는 **구울 때** 굳는다 — 표지 loaded_ym(다 들어온 분기 · 결정 0035)으로 굽고, post_load.py 가 구운 뒤 화면 기준(published_ym)을 올린다. '
  '⛔ anon 에게 열지 않는다 — 화면은 list_industry_mix 함수로만 읽는다.';

comment on materialized view mv_coverage_stats is
  '§8.6 스택 뷰 각주 집계를 **미리 계산해 둔 한 줄**(2026-08-22d). 화면은 이 표를 직접 '
  '읽지 않고 v_coverage_stats 뷰를 거친다 — 표 자체는 anon 에게 닫혀 있다. '
  '왜 사전계산인가: 실시간 집계는 최신 스냅샷 277만 행마다 substr 을 잘라 열린 구 목록과 '
  '대조하느라 순수 실행 2.1~4.9초였고(2026-08-22 실측, 부하에 따라 흔들린다), anon 의 '
  '3초 제한을 넘나들었다. 집계값은 **적재 시점에만** 바뀌므로 그때 한 번 세면 된다. '
  '신선도 = python scripts/post_load.py 를 돌린 시점(적재와 한 세트다 — 그 스크립트의 '
  '--check 가 표지 loaded_ym 과 대조해 낡음을 잡는다). 분기 = 표지 loaded_ym(결정 0035). '
  '⚠️ 본문은 2026-08-22a 의 v_coverage_stats select 와 동일하다 — 범위(서비스 지역)나 '
  '분기 기준을 고칠 때는 여기와 supabase/schema.sql 을 함께 고칠 것.';

-- 이름을 바꿔도 권한은 따라오지만, 정본의 '닫힌 요약표 전부' 목록과 같게 다시 적는다.
revoke all on mv_parcel_store_names    from public, anon, authenticated;
revoke all on mv_district_industry_mix from public, anon, authenticated;
revoke all on mv_coverage_stats        from public, anon, authenticated;

commit;

notify pgrst, 'reload schema';
