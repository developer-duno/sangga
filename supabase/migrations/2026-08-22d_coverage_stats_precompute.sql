-- =====================================================================
-- 마이그레이션 2026-08-22d — 각주 집계를 **미리 계산해 둔다**(사전계산)
-- =====================================================================
-- 실행법 ⚠️ **대시보드 SQL Editor 로 돌린다.**
--   여기엔 `create index concurrently` 가 없다(새로 만드는 표라 잠글 것이 없다).
--   → Supabase 대시보드 → SQL Editor 에 이 파일을 통째로 붙여 실행.
--   → 그 다음 `python scripts/post_load.py` (플래그 없이 — 새 요약표가 갱신 목록에
--     들어갔으므로 여기서 한 번 돌려 그 경로가 실제로 도는지 확인한다).
--   ⓘ 한 문장씩 `if not exists / or replace` 라 두 번 돌아도 안전하다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 무엇이 문제였나 (2026-08-22 라이브 실측, 2026-08-22a 적용 직후)
-- ─────────────────────────────────────────────────────────────────────
-- 08-22a 가 각주 범위를 "서비스 지역"으로 좁히면서 where 절에
-- `substr(ub.pnu,1,5)::char(5) in (select sigungu_code from mv_open_sigungu)` 가 붙었다.
-- 커버링 인덱스(idx_ub_snapshot_floor_pnu) 덕에 **힙에는 안 간다**(Heap Fetches 0).
-- 그런데 최신 스냅샷 **277만 행마다** substr 을 잘라 해시표와 맞춰 보는 일 자체가 남아,
-- 순수 실행 시간이 이렇게 됐다:
--
--     08-11f 커버링 인덱스 적용 후 (전국 집계)   131ms
--     08-22a 지역 조건 추가 후 (서비스 지역)   ~2,100ms   ← 3회 반복 실측, 약 16배
--
-- anon 공개 호출의 statement timeout 은 **3초**다. 2.1초는 그 문턱에 위험하게 붙어 있다
-- (부하가 조금만 겹치면 넘는다). 화면은 각주를 못 받으면 null 로 조용히 강등돼 에러는
-- 안 나지만, **각주가 사실상 안 보이는 상태**가 된다 — 08-22a 가 고치려던 바로 그 값이.
--
-- ─────────────────────────────────────────────────────────────────────
-- 처방 — 값이 바뀌는 순간에만 계산한다
-- ─────────────────────────────────────────────────────────────────────
-- 이 집계값은 **적재할 때만 바뀐다.** 점포 표(unit_business)는 분기 스냅샷 append-only 이고
-- 열린 구 목록(mv_open_sigungu)도 적재 뒤 post_load 에서만 갱신된다. 그런데 지금은
-- **화면을 열 때마다** 277만 행을 다시 세고 있다 — 하루에 몇 천 번 같은 답을 다시 구하는 셈.
-- → 물질화뷰(mv_coverage_stats)로 **한 번 세어 한 줄로 굳혀** 두고, 화면은 그 한 줄을 읽는다.
--   신선도는 `python scripts/post_load.py` 시점이다. 자료도 정확히 그때만 바뀌므로
--   "낡을 수 있는 구간"이 아예 없다(적재 → post_load 는 한 세트다).
--
-- ⛔ **화면이 읽는 이름은 안 바꾼다.** v_coverage_stats 라는 뷰는 그대로 두고 속만
--    갈아 끼운다(`select * from mv_coverage_stats`). 프론트 수정 0.
--
-- ⛔ **drop view 하지 말 것.** 이 뷰는 anon/authenticated 에게 SELECT 가 열려 있는데
--    drop 하면 그 GRANT 가 같이 사라진다. 그리고 `scripts/post_load.py --check` 는
--    "허용목록 밖인데 **열린** 것"만 잡지 "열려 있어야 하는데 **닫힌** 것"은 못 잡는다.
--    → `create or replace view` 로만 고친다. 컬럼 이름·순서·타입이 그대로여야 성립하는데,
--      물질화뷰가 **같은 select 를 그대로** 담으므로 (char(6), bigint, bigint, numeric) 로
--      완전히 일치한다.
--
-- ⛔ **물질화뷰 자체는 공개키에 열지 않는다**(2026-08-13f 정책). Supabase 는 새로 만드는
--    표·물질화뷰를 anon 에게 자동으로 열어 준다(pg_default_acl). 08-13f 가 기본권한을
--    닫아 뒀지만 그건 **postgres 가 만드는 것**에만 걸린다 — 대시보드(supabase_admin)로
--    만들면 지금도 자동 개방이다. 그래서 만든 자리에서 **명시적으로 회수**한다.
--
-- 검산 (실행 후):
--   select * from v_coverage_stats;
--     → 값이 그대로여야 한다: store_cnt 634,770 · floor_missing_cnt 222,443 · pct 35.0
--   explain (analyze, buffers) select * from v_coverage_stats;
--     → "Seq Scan on mv_coverage_stats" 1행, 실행 시간 1ms 미만.

-- ── 1) 미리 계산해 둘 표부터 만든다 ───────────────────────────────────────
-- ⚠️ **문장 순서가 안전장치다.** 표 만들기 → 인덱스 → 권한 회수 → 뷰 갈아끼우기 순.
--    중간에서 멈춰도 남는 상태가 항상 안전하다:
--      · 1)까지만 돌면 → 아무도 안 읽는 표가 하나 생겼을 뿐(뷰는 옛 실시간 집계 그대로)
--      · 3)까지 돌면   → 표는 닫혀 있고 뷰만 그 표를 읽는다(최종 상태)
--    반대로 뷰를 먼저 갈면 "아직 권한을 안 닫은 표"를 화면이 읽는 구간이 생긴다.
--
-- select 본문은 2026-08-22a 의 v_coverage_stats 와 **한 글자도 다르지 않다** — 옮겨
-- 적은 것이지 새로 설계한 것이 아니다. 두 곳을 함께 고쳐야 하는 관계이므로 아래
-- comment 에 그 사실을 박아 둔다.
create materialized view if not exists mv_coverage_stats as
select
  ub.snapshot_ym,
  count(*)                                                    as store_cnt,
  count(*) filter (where ub.floor_no is null)                 as floor_missing_cnt,
  round(100.0 * count(*) filter (where ub.floor_no is null)
        / count(*), 1)                                        as floor_missing_pct
from unit_business ub
where ub.snapshot_ym = (select max(snapshot_ym) from unit_business)
  -- ⚠️ `::char(5)` 로 타입을 맞춘다. substr(char) 의 결과는 text 인데 sigungu_code 는
  --    char(5) 라, 맞춰 두지 않으면 비교마다 캐스트가 낀다(2026-08-16b 와 같은 병).
  and substr(ub.pnu, 1, 5)::char(5) in (select sigungu_code from mv_open_sigungu)
group by ub.snapshot_ym;

comment on materialized view mv_coverage_stats is
  '§8.6 스택 뷰 각주 집계를 **미리 계산해 둔 한 줄**(2026-08-22d). 화면은 이 표를 직접 '
  '읽지 않고 v_coverage_stats 뷰를 거친다 — 표 자체는 anon 에게 닫혀 있다. '
  '왜 사전계산인가: 실시간 집계는 최신 스냅샷 277만 행마다 substr 을 잘라 대조하느라 '
  '순수 실행 ~2,100ms 였고(2026-08-22 실측, 3회 반복), anon 의 3초 제한에 붙어 있었다. '
  '집계값은 **적재 시점에만** 바뀌므로 그때 한 번 세면 된다. '
  '신선도 = python scripts/post_load.py 를 돌린 시점(적재와 한 세트다). '
  '⚠️ 본문은 2026-08-22a 의 v_coverage_stats select 와 동일하다 — 범위(서비스 지역)나 '
  '분기 기준을 고칠 때는 여기와 supabase/schema.sql 을 함께 고칠 것.';

-- ── 2) unique 인덱스 — `refresh ... concurrently` 의 필수 조건 ──────────────
-- 이게 없으면 갱신이 끝날 때까지 각주 조회가 통째로 잠긴다(post_load 는 전부
-- concurrently 로 돈다 — tests/test_post_load.py 가 그걸 강제한다).
-- 행이 한 줄뿐이라 인덱스의 조회 이득은 없다. 순전히 concurrently 자격 요건이다.
create unique index if not exists idx_mcs_snapshot_ym on mv_coverage_stats (snapshot_ym);

analyze mv_coverage_stats;

-- ── 3) 표는 공개키에게 닫는다 (2026-08-13f 정책) ────────────────────────────
-- ⛔ `from public` 만으로는 아무것도 안 닫힌다 — anon·authenticated 가 **직접** 받은
--    GRANT 는 그대로 남는다(2026-08-10 라이브 실측).
-- 값 자체는 집계 4개뿐이라 새어 나가도 큰일은 아니지만, "새 물질화뷰는 닫는다"는
-- 규칙에 예외를 만들면 다음번에 위험한 표가 같은 논리로 열린다.
revoke all on mv_coverage_stats from public, anon, authenticated;

-- ── 4) 화면이 읽는 뷰의 속만 갈아 끼운다 (이름·컬럼 불변 = 프론트 수정 0) ─────
create or replace view v_coverage_stats as
select * from mv_coverage_stats;

comment on view v_coverage_stats is
  '§8.6 스택 뷰 각주용 집계. **미리 계산해 둔 mv_coverage_stats 한 줄을 그대로 내보낸다**'
  '(2026-08-22d — 실시간 집계는 ~2,100ms 로 anon 3초 제한에 붙어 있었다). '
  '★ 범위는 **서비스 지역(mv_open_sigungu = 화면에서 고를 수 있는 구)** 뿐이다(2026-08-22a). '
  '전국을 세면 화면이 보여주지도 않는 지역까지 섞여 결측률이 15.3%p 과장된다(50.3% vs 35.0%). '
  '분기 기준은 v_floor_stack 과 동일한 전역 최신 snapshot_ym — 둘을 항상 함께 고칠 것. '
  'ℹ️ pnu 가 NULL 인 행(실측 1,819)은 지역 특정 불가라 분모에서 빠진다. '
  'ℹ️ 신선도 = python scripts/post_load.py 시점(집계값도 적재 때만 바뀐다). '
  '★ 공개 접근: anon/authenticated에게 SELECT 허용(집계값만, 상호명 없음). '
  '⛔ drop 하지 말 것 — GRANT 가 날아가는데 post_load --check 는 "닫힌 것"을 못 잡는다. '
  'ℹ️ 린트 0010(security definer view) 의도적 예외 — security_invoker=true로 되돌리면 원본 표 401. '
  '재검토 방아쇠: 공개 배포일 / 지도·반경 검색(§6.4) 착수일';

-- ⚠️ `create or replace view` 는 뷰의 **옵션을 통째로 갈아 끼운다**(AT_ReplaceRelOptions).
--    지금은 지우면 기본값(false)으로 돌아가 결과가 같지만, "우연히 맞는 것"에 기대지 않는다.
--    이 뷰가 소유자 권한으로 도는 것은 사고가 아니라 선택이다 — invoker 로 돌면 anon 이
--    mv_coverage_stats 를 못 읽어 각주가 401 이 된다.
alter view v_coverage_stats set (security_invoker = false);

-- 대조용 — replace 는 GRANT 를 보존하므로 이미 열려 있다. 무해하지만, 혹시라도 닫혀 있으면
-- 아무 경보 없이 각주만 사라지는 자리(위 ⛔ 참조)라 여기서 한 번 더 못 박는다.
grant select on v_coverage_stats to anon, authenticated;

-- ─────────────────────────────────────────────────────────────────────
-- ⚠️ 갱신을 잊으면 어떻게 되나 → 잊을 수 없게 해 뒀다
-- ─────────────────────────────────────────────────────────────────────
-- 미리 계산해 두는 값은 "갱신을 잊으면 조용히 낡는다"는 대가를 치른다. 그래서 이 표는
-- `scripts/post_load.py` 의 REFRESH_MVS 에 **mv_open_sigungu 뒤로** 넣었다(그 표를 읽으므로).
-- 적재 뒤 post_load 는 이미 운영 5계명에 박힌 한 세트라, 별도로 기억할 것이 늘지 않는다.
--
-- ⚠️ 드리프트 가드(tests/test_schema_migration_sync.py)의 한계
--   그 가드는 인덱스·함수·**일반 뷰(create or replace view)** 이름만 재생해 대조한다.
--   `create materialized view` 는 `or replace` 가 없어 정규식에 안 걸린다 — 즉
--   **물질화뷰 본문·존재 여부는 사람이 schema.sql 에 반영해야 한다.**
--   이 마이그레이션에서는 반영했다(supabase/schema.sql 의 mv_coverage_stats).
--   위 `idx_mcs_snapshot_ym` 은 인덱스라 가드가 지켜 준다.
