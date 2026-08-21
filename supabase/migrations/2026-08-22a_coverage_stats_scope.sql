-- =====================================================================
-- 마이그레이션 2026-08-22a — 각주 집계(v_coverage_stats)를 "서비스 지역" 기준으로
-- =====================================================================
-- 실행법 ⚠️ **대시보드 SQL Editor 로 돌린다.**
--   여기엔 `create index concurrently` 가 없다(아래 "왜 concurrently 가 아닌가" 참조).
--   → Supabase 대시보드 → SQL Editor 에 이 파일을 통째로 붙여 실행.
--   → 그 다음 `python scripts/post_load.py` (플래그 없이 — vacuum(analyze)·요약표 갱신·
--     공개 노출 점검이 다 들어 있다. `--check` 만 돌리면 가시성 지도를 안 손봐서
--     Index Only Scan 이 힙을 되짚는 상태가 그대로 남는다).
--   ⓘ SQL Editor 가 타임아웃을 내면 **그냥 다시 돌리면 된다.** 첫 오류에서 통째로
--     멈추므로(한 트랜잭션) 아직 아무것도 안 지워졌고, 문장마다 if not exists / or replace /
--     if exists 라 두 번 돌아도 안전하다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 무엇이 문제였나 (2026-08-22 라이브 실측)
-- ─────────────────────────────────────────────────────────────────────
-- 화면 각주는 "점포 N곳 중 층이 없는 것이 M%" 라고 말한다. 그런데 뷰가 세는 것은
-- **전국** 점포였고, 화면이 보여주는 것은 **서울+대전 30개 구뿐**이다(결정 0006).
-- 세는 곳과 보여주는 곳이 다르니 각주가 실제보다 나쁘게 말한다:
--
--     전국          2,772,484 곳 · 층 없음 1,393,405 = 50.3%
--     열린 지역만      634,770 곳 · 층 없음   222,443 = 35.0%
--                                                      ↑ 15.3%p 과장
--
-- 사용자가 보는 건물은 전부 열린 지역 안에 있으므로, 각주도 그 범위를 세야 한다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 처방 — mv_open_sigungu(열린 구 목록)로 범위를 좁힌다
-- ─────────────────────────────────────────────────────────────────────
-- "열린 지역"의 진실은 이미 서버 한 곳(mv_open_sigungu)에 있다(CLAUDE.md 확정설계 9).
-- 목록을 여기에 베껴 적으면 자료가 늘 때 각주만 낡으므로, 그 표를 그대로 읽는다.
--
-- ⛔ **drop view 하지 말 것.** 이 뷰는 anon/authenticated 에게 SELECT 가 열려 있는데
--    drop 하면 그 GRANT 가 같이 사라진다. 그리고 `scripts/post_load.py --check` 는
--    "허용목록 밖인데 **열린** 것"만 잡지 "열려 있어야 하는데 **닫힌** 것"은 못 잡는다
--    (unexpected_anon_readables 는 열린 것에서 허용목록을 뺄 뿐이다).
--    즉 권한이 날아가도 아무 경보가 안 울리고 화면 각주만 조용히 사라진다.
--    → `create or replace view` 로만 고친다. 그러려면 **컬럼 이름·순서·타입이
--      그대로**여야 하므로 select 목록은 손대지 않고 where 절만 더한다.
--
-- ⚠️ NULL pnu 는 분모에서 빠진다 — 실측 **1,819행**(전 스냅샷 합계, 2026-08-22).
--    지역을 특정할 수 없는 행이라 "서비스 지역 통계"에 넣을 자리가 없다.
--    최신 스냅샷 2,772,484 행에 견주면 0.07% 미만이라 각주 숫자를 흔들지 않는다.
--
-- ⚠️ 상단 주석의 "분기"는 **snapshot_ym(스냅샷 분기)** 를 말한다. 지역 조건을 더해도
--    그 약속은 그대로다 — v_floor_stack 과 **똑같은 전역 최신 분기**를 쓴다.
--    바뀐 것은 "어느 지역을 세느냐"뿐이고, "어느 분기를 세느냐"는 손대지 않았다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 🔴 인덱스를 같이 갈아야 한다 (안 하면 2026-08-11f 의 간헐 500 이 되살아난다)
-- ─────────────────────────────────────────────────────────────────────
-- 지금 뷰는 idx_ub_snapshot_floor (snapshot_ym, floor_no) 로 **Index Only Scan** 을 탄다.
-- 11f 실측: 버퍼 636,527 → 698, 힙 방문 0, 1,028ms → 131ms.
-- 그런데 새 where 절이 **pnu 를 읽는다.** pnu 가 인덱스에 없으면 행마다 힙에 다녀와야 해서
-- (최신 스냅샷 277만 행) 11f 가 고친 바로 그 병 — 캐시가 식은 첫 요청이 3초 제한을 넘겨
-- 500 — 이 그대로 재발한다.
-- → 세 컬럼짜리(snapshot_ym, floor_no, pnu) 로 갈아 다시 힙에 안 가게 한다.
--   옛 인덱스는 새 인덱스의 **앞부분(prefix)** 이라 남겨 둘 이유가 없다(중복).
--
-- 왜 concurrently 가 아닌가: 이 표는 append-only 분기 스냅샷이고 지금은 라이브 쓰기가
-- 없다. concurrently 는 트랜잭션 밖에서만 돌아 SQL Editor 로 못 붙인다(11f 가 겪은 25P02).
-- 잠깐의 잠금을 감수하고 SQL Editor 한 번으로 끝내는 쪽을 고른다.
--
-- 검산 (실행 후):
--   explain (analyze, buffers) select * from v_coverage_stats;
--     → "Index Only Scan using idx_ub_snapshot_floor_pnu" 가 보이고
--       Heap Fetches 가 0 에 가까워야 한다. 안 그러면 vacuum 을 한 번 더 돌린다.
--   select * from v_coverage_stats;
--     → store_cnt 가 277만대에서 63만대로, floor_missing_pct 가 50.3 에서 35.0 으로.

-- ── 1) 새 커버링 인덱스부터 만든다 ─────────────────────────────────────────
-- ⚠️ **문장 순서가 안전장치다.** create(새 인덱스) → replace(뷰) → drop(옛 인덱스) 순으로
--    둔다. 어떤 이유로든 중간에서 멈춰도(SQL Editor 타임아웃 등) 남는 상태가 항상 안전하다:
--      · 1)까지만 돌면  → 인덱스만 하나 더 있는 상태(뷰는 옛 전국 집계 + 옛 인덱스 그대로)
--      · 2)까지 돌면    → 새 뷰 + 새 인덱스(옛 인덱스는 중복으로 남아 있을 뿐)
--    반대로 drop 을 먼저 두면 "새 where 절을 쓰는 뷰가 커버링 인덱스 없이 사는 구간"이
--    생기는데, 그게 바로 이 마이그레이션이 막으려는 그 500 이다.
create index if not exists idx_ub_snapshot_floor_pnu
  on unit_business (snapshot_ym, floor_no, pnu);

comment on index idx_ub_snapshot_floor_pnu is
  'v_coverage_stats 각주 집계 전용 커버링 인덱스. 뷰가 읽는 세 컬럼이 다 들어 있어 '
  '힙에 안 간다(Index Only Scan). pnu 가 빠지면 최신 스냅샷 277만 행마다 힙 페이지를 '
  '방문해 캐시가 식은 첫 요청이 3초 제한을 넘겨 500 이 된다(2026-08-11f 실측: '
  '버퍼 636,527 → 698, 1,028ms → 131ms). 옛 idx_ub_snapshot_floor 를 대체한다.';

-- ── 2) 뷰를 열린 지역 기준으로 (컬럼 목록 불변 = replace 성립) ───────────────
create or replace view v_coverage_stats as
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

comment on view v_coverage_stats is
  '§8.6 스택 뷰 각주용 집계. v_floor_stack과 동일한 전역 최신 분기 기준 — 둘을 항상 함께 고칠 것. '
  '★ 범위는 **서비스 지역(mv_open_sigungu = 화면에서 고를 수 있는 구)** 뿐이다(2026-08-22a). '
  '전국을 세면 화면이 보여주지도 않는 지역까지 섞여 결측률이 15.3%p 과장된다(50.3% vs 35.0%). '
  'ℹ️ pnu 가 NULL 인 행(실측 1,819)은 지역 특정 불가라 분모에서 빠진다. '
  '★ 공개 접근: anon/authenticated에게 SELECT 허용(집계값만, 상호명 없음). '
  '⛔ drop 하지 말 것 — GRANT 가 날아가는데 post_load --check 는 "닫힌 것"을 못 잡는다. '
  'ℹ️ 린트 0010(security definer view) 의도적 예외 — security_invoker=true로 되돌리면 원본 표(unit_business) 401. '
  '재검토 방아쇠: 공개 배포일 / 지도·반경 검색(§6.4) 착수일';

-- ── 3) 옛 인덱스는 **맨 마지막에** 지운다 (위 1) 주석의 순서 이유 참조) ──────
-- 새 인덱스의 앞부분(prefix)이라 남겨 둘 이유가 없다(같은 조회를 두 번 색인하는 셈).
drop index if exists idx_ub_snapshot_floor;

-- 인덱스를 갈았으니 통계도 새로 떠야 플래너가 새 것을 고른다.
analyze unit_business;

-- ─────────────────────────────────────────────────────────────────────
-- ⚠️ 드리프트 가드의 한계 (tests/test_schema_migration_sync.py)
-- ─────────────────────────────────────────────────────────────────────
-- 그 가드는 **인덱스·함수·컬럼 이름**만 재생해 대조한다. `create or replace view` 는
-- 감시 대상이 아니다(정규식 4종에 view 가 없다). 그래서 위 인덱스 두 줄은 기계가
-- 지켜 주지만, **뷰 본문은 사람이 schema.sql 에 같이 반영해야 한다.**
-- 이 마이그레이션에서는 반영했다(supabase/schema.sql 의 v_coverage_stats).
