-- =====================================================================
-- 마이그레이션 2026-08-08 (d) — 화면 각주 숫자를 런타임 계산으로
-- =====================================================================
-- 어떻게 쓰나: Supabase 대시보드 → SQL Editor → New query → 이 파일 전체
--             붙여넣기 → Run. 몇 번을 실행해도 안전하다(멱등).
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 필요한가
-- ─────────────────────────────────────────────────────────────────────
-- src/components/FloorStack.tsx의 각주에 숫자가 **손으로 박혀** 있었다:
--     "약 3곳 중 1곳(32.9%)" / "강남 2026년 1분기 상권정보 64,239곳 기준"
--
-- 그런데 이 숫자가 나온 v_floor_stack의 점포는
--     snapshot_ym = (select max(snapshot_ym) from unit_business)
-- 로 **항상 최신 분기를 자동으로 따라간다.** 문구만 안 따라간다.
-- ⇒ 새 분기(2026Q2 등)를 적재하는 순간, 화면의 막대·점포 목록은 새 분기로
--    바뀌는데 각주만 옛 분기 숫자를 말한다. 코드는 한 줄도 안 고쳤는데
--    화면이 거짓말을 시작하는 종류의 결함이다(작성한 날에는 절대 안 잡힌다).
--
-- 그래서 화면이 읽을 수 있는 집계 뷰를 만들어 각주를 런타임에 계산한다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 무엇을 노출하나 — 노출면을 넓히지 않는 선에서
-- ─────────────────────────────────────────────────────────────────────
-- 2026-08-08_public_read_policy.sql이 정한 방침(원본 표는 닫고 화면이 읽는
-- 뷰만 연다)을 그대로 따른다. 이 뷰가 내보내는 것은 **집계값 4개뿐**이다:
-- 분기·점포 수·층 결측 수·층 결측 비율. 상호명(biz_name)·좌표·주소는
-- 들어가지 않는다 — 상호명 노출은 변호사 검토 대상이라 한 줄도 늘리지 않는다.
--
-- ⏳ 지금은 안 터지지만 조건이 갖춰지면 손봐야 하는 것:
--   (1) v_floor_stack과 **똑같이** 전역 최신 분기를 쓴다. 지역별로 최신 분기가
--       달라지면 둘 다 함께 고쳐야 한다(따로 고치면 화면과 각주가 어긋난다).
--   (2) count(*)는 전량을 센다. 강남 6.4만 행에서는 수십 ms지만 전국 수백만
--       행이면 화면 로드마다 부담이 된다. 그때는 집계 결과를 표에 적재하거나
--       materialized view로 바꾼다.
-- =====================================================================

-- 1) 각주용 집계 뷰
create or replace view v_coverage_stats as
select
  ub.snapshot_ym,
  count(*)                                                    as store_cnt,
  count(*) filter (where ub.floor_no is null)                 as floor_missing_cnt,
  round(100.0 * count(*) filter (where ub.floor_no is null)
        / count(*), 1)                                        as floor_missing_pct
from unit_business ub
where ub.snapshot_ym = (select max(snapshot_ym) from unit_business)
group by ub.snapshot_ym;
-- group by 덕분에 행이 있을 때만 결과가 나온다 = count(*)가 0인 경우가 없어
-- 0으로 나누는 일이 생기지 않는다. 데이터가 아예 없으면 0행이 오고, 화면은
-- 그때 숫자를 빼고 경고 문장만 보여준다(틀린 숫자보다 없는 숫자가 낫다).

-- 2) 다른 뷰들과 같은 취급 — 소유자 권한으로 원본 표를 읽는다.
--    원본 표(unit_business)는 RLS 켬 + 권한 회수 상태라 anon이 직접 못 읽는다.
alter view v_coverage_stats set (security_invoker = false);

-- 3) 화면이 읽어야 하므로 이 뷰만 명시적으로 연다.
grant select on v_coverage_stats to anon, authenticated;

comment on view v_coverage_stats is
  '§8.6 스택 뷰 각주용 집계. v_floor_stack과 동일하게 전역 최신 분기를 기준으로 한다 — '
  '둘의 분기 기준이 어긋나면 화면과 각주가 다른 말을 하게 되므로 항상 함께 고칠 것. '
  '★ 공개 접근: anon/authenticated에게 SELECT 허용(집계값만, 상호명 없음)';

-- =====================================================================
-- 4) 확인 (붙여넣고 Run 한 뒤 이 쿼리로 검산)
-- =====================================================================
-- 기대: 1행. store_cnt가 화면 각주와 같은 값이어야 한다.
--
--   select * from v_coverage_stats;
--
-- 기대: v_floor_stack, v_coverage_stats 두 개만 anon에게 SELECT
--
--   select table_name, grantee, privilege_type
--   from information_schema.role_table_grants
--   where table_schema = 'public' and grantee in ('anon','authenticated')
--   order by table_name, grantee;
-- =====================================================================
