-- =====================================================================
-- 마이그레이션 2026-08-10b — 뷰 2개에 린트 0010 의도적 예외 주석
-- =====================================================================
-- 어떻게 쓰나: Supabase 대시보드 → SQL Editor → New query → 이 파일 전체
--             붙여넣기 → Run. 몇 번을 실행해도 안전하다(comment on은 멱등).
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 필요한가
-- ─────────────────────────────────────────────────────────────────────
-- `v_floor_stack`·`v_coverage_stats`는 SECURITY DEFINER(=security_invoker
-- false)로 **의도적으로** 만들었다 — 원본 표(building·unit_business 등)는
-- RLS + 권한 회수로 anon에게 닫아 두고, 이 두 뷰만 소유자 권한으로 대신
-- 읽어 화면에 필요한 최소 정보만 내보내기 위해서다(2026-08-08_public_read_
-- policy.sql · 2026-08-08d_coverage_stats.sql 참조).
--
-- Supabase 보안 린트 0010(security_definer_view)은 이 설계를 CRITICAL로
-- 표시한다 — 린트만 보고 "고쳐야지" 하며 security_invoker=true로 되돌리면
--   ① 원본 표가 이미 닫혀 있으므로 화면이 401로 깨지고
--   ② security_invoker=true로 원본 표를 직접 열면 상호명(unit_business.
--      biz_name)·성명(building.bld_nm)이 더 넓게 노출된다(알려진한계 §6
--      "상호명 노출"은 변호사 검토 대상, §3 "건물명 칸에 개인 성명" 참조).
-- 그래서 이 뷰 주석에 "의도된 예외"임을 못박아 다음 사람이 린트 경고만
-- 보고 되돌리지 않게 한다.
--
-- 재검토 방아쇠 — 아래 둘 중 하나가 되면 이 설계를 다시 논의할 것:
--   · 공개 배포일 (지금은 앱 미배포·공개키 미노출)
--   · 지도·반경 검색(§6.4 상권 유사도) 착수일 (좌표 기반 조회가 늘면
--     노출면·성능 트레이드오프가 달라진다)
-- =====================================================================

comment on view v_floor_stack is
  '§8.6 층별 스택 뷰. store_cnt/stores는 (PNU, 층) 매칭이라 bld_cnt_in_pnu>1이면 건물 간 중복 — D등급 표시 필수. '
  '★ 공개 접근: 이 뷰만 anon/authenticated에게 SELECT 허용된다(아래 "공개 접근 정책" 절). '
  '원본 표는 RLS 켬 + 정책 0개 + 권한 회수로 닫혀 있고, 이 뷰가 소유자 권한으로 대신 읽는다. '
  '⚠️ bld_nm은 원본이 아니라 building_display_nm() 결과다(동명칭 폴백 + 개인 성명 가림, 2026-08-08e). '
  'ℹ️ 린트 0010(security definer view) 의도적 예외 — security_invoker=true로 되돌리면 원본 표 401 + 상호명·성명 노출 확대. '
  '재검토 방아쇠: 공개 배포일 / 지도·반경 검색(§6.4) 착수일';

comment on view v_coverage_stats is
  '§8.6 스택 뷰 각주용 집계. v_floor_stack과 동일한 전역 최신 분기 기준 — 둘을 항상 함께 고칠 것. '
  '★ 공개 접근: anon/authenticated에게 SELECT 허용(집계값만, 상호명 없음). '
  'ℹ️ 린트 0010(security definer view) 의도적 예외 — security_invoker=true로 되돌리면 원본 표(unit_business) 401. '
  '재검토 방아쇠: 공개 배포일 / 지도·반경 검색(§6.4) 착수일';

-- =====================================================================
-- 확인 (붙여넣고 Run 한 뒤 이 쿼리로 검산)
-- =====================================================================
-- 기대: 두 뷰 모두 주석에 "린트 0010" 문구가 포함되어야 한다
--
--   select c.relname as view_name, d.description
--   from pg_class c
--   join pg_description d on d.objoid = c.oid and d.objsubid = 0
--   where c.relnamespace = 'public'::regnamespace
--     and c.relname in ('v_floor_stack', 'v_coverage_stats');
-- =====================================================================
