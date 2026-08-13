-- =====================================================================
-- 마이그레이션 2026-08-11f — 각주 집계(v_coverage_stats) 간헐 500 해소
-- =====================================================================
-- 실행법 ⚠️ **대시보드 SQL Editor 로는 안 된다.**
--   `create index concurrently` 는 트랜잭션 블록 안에서 못 돈다. SQL Editor 는
--   스크립트 전체를 한 트랜잭션으로 감싸므로 25P02 로 죽는다.
--   → `python scripts/dbx.py -f supabase/migrations/2026-08-11f_ub_coverage_index.sql`
--     (psql 은 문장을 각각 자기 트랜잭션으로 돌린다)
--   concurrently 를 쓰는 이유: 125만 행 테이블을 라이브 서비스 중에 잠그지 않으려고.
--
-- ─────────────────────────────────────────────────────────────────────
-- 무엇이 문제였나 (2026-08-11 라이브 실측)
-- ─────────────────────────────────────────────────────────────────────
-- 각주 뷰가 **캐시가 식어 있으면** 3초 제한을 넘겨 500 을 냈다.
--   차가울 때: HTTP 500, 3.2초, {"code":"57014","message":"canceling statement
--              due to statement timeout"}
--   따뜻할 때: HTTP 200, 0.5~0.85초
-- 같은 요청이 왔다 갔다 하니 재현이 어렵다 — 사용자가 오랜만에 화면을 열 때만
-- 각주가 사라지고, 새로고침하면 살아난다.
--
-- ⛔ "인덱스가 없어서"가 **아니었다.** pkey 가 (snapshot_ym, biz_no) 라
--    `where snapshot_ym = …` 는 이미 인덱스를 탄다. 진짜 원인은 그 다음이다:
--
--      Parallel Index Scan using unit_business_pkey  (actual time=0.045..913.570)
--        Buffers: shared hit=636522 read=1816
--
--    힙은 **42,969 페이지**뿐인데 버퍼를 **636,527번** 만졌다 = 테이블을 15번 훑은 꼴.
--    인덱스는 biz_no 순서인데 힙은 적재 순서라, 그 순서로 훑으면 **행 하나마다**
--    힙 페이지를 한 번씩 방문한다(최신 스냅샷 63.5만 행 = 63.5만 번).
--    캐시에 있으면 hit(빠름), 없으면 디스크 read(느림) — 이게 간헐 500 의 정체다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 처방 — 힙에 아예 안 가게 한다 (Index Only Scan)
-- ─────────────────────────────────────────────────────────────────────
-- 뷰가 쓰는 컬럼은 snapshot_ym 과 floor_no **둘뿐**이다:
--     count(*) / count(*) filter (where floor_no is null) / group by snapshot_ym
-- 그래서 (snapshot_ym, floor_no) 인덱스면 필요한 값이 인덱스 안에 다 있어
-- 힙에 다녀올 일이 없다.
--   · include (floor_no) 가 아니라 **키 컬럼**으로 둔 이유: floor_no 는 값 종류가
--     적어(층 번호) btree 중복 제거(PG13+)가 잘 먹혀 인덱스가 더 작아진다.
--   · Index Only Scan 은 visibility map 이 깨끗해야 효과가 난다 → 아래 analyze.
--     (2026-08-10 autovacuum 이 돌았고 dead tuple 0 인 것은 확인했다)
--
-- 검산 (실행 후):
--   explain (analyze, buffers) select * from v_coverage_stats;
--     → "Index Only Scan using idx_ub_snapshot_floor" 가 보이고
--       Buffers 가 63만대에서 수천 대로 떨어져야 한다. Heap Fetches 도 작아야 한다.

create index concurrently if not exists idx_ub_snapshot_floor
  on unit_business (snapshot_ym, floor_no);

comment on index idx_ub_snapshot_floor is
  'v_coverage_stats 각주 집계 전용 커버링 인덱스. 이 둘만 있으면 힙에 안 간다. '
  '없으면 최신 스냅샷 63.5만 행마다 힙 페이지를 한 번씩 방문해(버퍼 63.6만 회) '
  '캐시가 식은 첫 요청이 3초 제한을 넘겨 500 이 된다(2026-08-11 실측).';

analyze unit_business;
