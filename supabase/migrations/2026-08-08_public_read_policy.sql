-- =====================================================================
-- 마이그레이션 2026-08-08 — 공개 접근 정책 명문화 (RLS + 최소 권한)
-- =====================================================================
-- 어떻게 쓰나: Supabase 대시보드 → SQL Editor → New query → 이 파일 전체
--             붙여넣기 → Run. 몇 번을 실행해도 안전하다(전부 멱등).
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 필요한가 (2026-08-08 라이브 실측)
-- ─────────────────────────────────────────────────────────────────────
-- 실측 결과 지금 라이브 DB는 "우연히" 안전하다. 코드에는 근거가 없다.
--
--   · 원본 표 11개  : anon으로 읽으면 HTTP 200 + 빈 배열, 쓰면 HTTP 401
--                     (42501 "new row violates row-level security policy")
--                     → RLS가 켜져 있고 정책이 0개라는 뜻. 그런데 이 상태를
--                       만든 문장이 schema.sql에 한 줄도 없다.
--   · 뷰 3개        : anon으로 전부 읽힌다. v_unit_current까지 열려 있는데
--                     화면은 v_floor_stack 하나만 쓴다.
--
-- 두 가지가 다 "설정이 아니라 기본 동작의 부수효과"다:
--   (1) Supabase 공식 문서 — SQL Editor로 만든 표는 RLS가 자동으로 켜지지
--       않는다("If you create one in raw SQL or with the SQL Editor,
--       remember to enable RLS yourself"). 지금 켜져 있는 건 누군가 손으로
--       켠 것이고 기록이 없다.
--       ⇒ schema.sql로 DB를 다시 만들면(재해 복구·스테이징·검증용 컨테이너)
--          RLS 없이 만들어져 **모든 표가 읽기·쓰기 전면 개방**된다.
--          실제로 이전 세션이 검증용 Postgres 컨테이너를 그렇게 띄웠다.
--   (2) Supabase 공식 문서 — 뷰는 기본이 security definer라 RLS를 우회한다
--       ("bypass RLS by default because they are usually created with the
--       postgres user"). 뷰가 열린 것도 우리가 정한 게 아니다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 무엇을 고르나 — 노출면을 넓히지 않는 쪽
-- ─────────────────────────────────────────────────────────────────────
-- 선택지 A: 뷰를 security_invoker=true로 바꾸고 원본 표에 anon 읽기 정책을
--           단다. 표준적이지만 그러면 unit_business(상호명)·transaction
--           (실거래)이 anon에게 통째로 직접 열린다.
-- 선택지 B(채택): 원본 표는 계속 닫고, 화면이 실제로 읽는 뷰 하나만 명시적
--           으로 연다. 상호명 노출은 CLAUDE.md에서 변호사 검토 대상으로
--           표시된 항목이라 노출면을 최소로 유지한다.
--
-- 즉 이 파일은 라이브 동작을 바꾸는 게 아니라 **지금 상태를 코드로 못 박는다.**
-- 화면 동작은 그대로다(v_floor_stack 읽기 유지).
-- =====================================================================

-- =====================================================================
-- 1) 원본 표 11개 — RLS 명시적으로 켜기
-- =====================================================================
-- 이미 켜져 있어도 오류가 나지 않는다. 이 문장들이 정본(schema.sql)에 들어가야
-- "schema.sql로 만든 DB = 안전한 DB"가 성립한다.
alter table bjd_code         enable row level security;
alter table parcel           enable row level security;
alter table building         enable row level security;
alter table building_floor   enable row level security;
alter table unit             enable row level security;
alter table unit_business    enable row level security;
alter table transaction      enable row level security;
alter table district         enable row level security;
alter table rent_stat        enable row level security;
alter table collect_progress enable row level security;
alter table api_quota_log    enable row level security;

-- 정책은 일부러 하나도 만들지 않는다.
-- RLS 켬 + 정책 0개 = 공개 롤(anon/authenticated)에게 원본 표는 완전히 안 보인다.
-- 수집·적재 스크립트는 service_role 키를 쓰는데, service_role은 RLS를 우회하므로
-- 영향이 없다(2026-08-08 실측: service로는 121,569행 정상 조회).

-- =====================================================================
-- 2) 공개 롤에게서 표 권한 회수 (이중 잠금)
-- =====================================================================
-- Supabase는 public 스키마의 표에 anon/authenticated SELECT 권한을 기본으로
-- 준다(실측 근거: 권한이 없으면 401 "permission denied"가 나야 하는데 지금은
-- 200 + 빈 배열이 나온다 = 권한은 있고 RLS가 막는 중).
-- RLS만으로도 막히지만, 나중에 누가 정책을 하나 잘못 달면 그 순간 표가 열린다.
-- 권한 자체를 회수해 두면 그런 실수 하나로는 안 뚫린다.
revoke all on all tables in schema public from anon, authenticated;

-- =====================================================================
-- 3) 화면이 실제로 읽는 뷰 하나만 읽기 허용
-- =====================================================================
-- src/lib/supabase.ts의 FLOOR_STACK_VIEW = 'v_floor_stack' 하나뿐이다.
-- v_building_floor_stack은 v_floor_stack의 재료라 직접 열 필요가 없고
-- (뷰가 뷰를 읽는 건 소유자 권한으로 돌아가므로 anon 권한과 무관하다),
-- v_unit_current는 화면이 쓰지 않는 데다 unit_id가 전 행 NULL이라 63,717행을
-- 100% 공실로 잘못 판정하는 뷰다 — 공개 대상에서 뺀다.
grant select on v_floor_stack to anon, authenticated;

-- authenticated에도 같이 주는 이유: 지금은 로그인 기능이 없지만, 나중에 로그인을
-- 붙였을 때 화면이 조용히 빈 목록으로 바뀌는 사고를 막는다. 둘 다 읽기 전용이다.

-- =====================================================================
-- 4) 뷰가 RLS를 우회하는 것이 "의도"임을 코드에 남긴다
-- =====================================================================
-- security_invoker=false는 어차피 기본값이지만, 명시해 두면 이게 사고가 아니라
-- 선택이라는 게 드러난다. 이 설정 때문에 v_floor_stack은 소유자(postgres) 권한
-- 으로 원본 표를 읽는다 — 그래서 원본 표를 닫아 둔 채로 화면이 돌아간다.
-- (PostgreSQL 15+ 필요. schema.sql 헤더가 15+를 전제로 한다)
alter view v_floor_stack           set (security_invoker = false);
alter view v_building_floor_stack  set (security_invoker = false);
alter view v_unit_current          set (security_invoker = false);

comment on view v_floor_stack is
  '§8.6 층별 스택 뷰. store_cnt/stores는 (PNU, 층) 매칭이라 bld_cnt_in_pnu>1이면 건물 간 중복 — D등급 표시 필수. '
  '★ 공개 접근: 이 뷰만 anon/authenticated에게 SELECT 허용된다(2026-08-08 마이그레이션). '
  '원본 표는 RLS 켬 + 정책 0개 + 권한 회수로 닫혀 있고, 이 뷰가 소유자 권한으로 대신 읽는다';

-- =====================================================================
-- 5) ⚠️ 이 마이그레이션이 막지 못하는 것 — PostGIS 시스템 표
-- =====================================================================
-- 위 revoke를 실행하면 spatial_ref_sys / geometry_columns / geography_columns에
-- 대해 "WARNING: no privileges could be revoked" 몇 줄이 나온다. 정상이며 무시해도
-- 되지만, 그 뜻은 **이 세 개는 못 막았다**는 것이다.
--
-- 왜: 소유자가 supabase_admin이라 postgres 롤의 revoke가 통하지 않는다
--     (postgres는 슈퍼유저가 아니고 set role supabase_admin도 거부된다 — 2026-08-08
--      컨테이너 실측). 원인은 PostGIS가 extensions가 아니라 public 스키마에 설치돼
--      REST에 그대로 노출되는 것이다(Supabase 공식 권장 = extensions 스키마).
--
-- 실제 위험(2026-08-08 라이브 실측):
--   · anon INSERT 권한 있음 — 중복 PK로 안전 시험해 HTTP 409(권한 아님) 확인
--   · anon DELETE 권한 있음 — 0건 매칭 필터로 안전 시험해 HTTP 204 확인
--   · parcel.geom이 12,274행 전부 채워져 PostGIS 실사용 중 → 좌표계표가 지워지면
--     좌표 변환이 깨진다
--
-- ─────────────────────────────────────────────────────────────────────
-- 결정 (2026-08-08): 별도 스키마 노출로 간다. 단 공개 배포 직전에 한다.
-- ─────────────────────────────────────────────────────────────────────
-- 방침: PostgREST 노출 스키마를 public → api 로 바꿔 public 자체를 REST에서 없앤다.
--       그러면 spatial_ref_sys를 포함해 public의 모든 것이 REST로 닿지 않는다.
--       (Supabase 지원팀 요청은 병행 가치가 낮다 — 플랫폼 기본 동작이라 개별 회수를
--        해 줄 가능성이 낮고, 위 방법은 우리 손으로 끝낼 수 있다.)
--
-- 왜 오늘 하지 않나 (실증 기반):
--   1. 실제 노출 위험이 지금은 0이다 — 앱이 배포 전이라 anon 키가 세상에 없다.
--   2. 반대로 지금 강행하면 위험이 생긴다 — 아래 두 전제가 **공식 문서에 없어 미검증**이다.
--      이 상태로 도는 수집 파이프라인 위에 큰 변경을 얹는 건 데이터 관리상 손해다.
--   3. 피해가 나도 복구 가능하다 — spatial_ref_sys는 우리 데이터가 아니라 PostGIS가
--      배포하는 표준 좌표계 참조표다(우리 표는 RLS로 잠겨 있어 안전). 지워지면 같은
--      PostGIS 버전에서 다시 채워 넣으면 된다(복구 절차는 아래).
--
-- 착수 전 반드시 시험할 전제 2가지 (일회용 컨테이너 + 스테이징에서):
--   (전제1) Supabase에서 노출 스키마 목록에서 **public을 뺄 수 있는가.**
--           공식 문서(guides/api/using-custom-schemas)는 "api를 추가하는 법"만 다루고
--           public 제거 가능 여부는 언급하지 않는다 — 확인 없이 계획하지 말 것.
--   (전제2) **pass-through 뷰로 upsert가 되는가.** public의 표를 api 스키마에 단일 표
--           뷰(`create view api.building_floor as select * from public.building_floor`)로
--           노출하면 자동 갱신 가능 뷰가 되어, 수집·적재기가 REST 경로·표 이름을 그대로
--           둔 채 쓸 수 있을 가능성이 있다(= 코드 변경 0). 단 `Prefer:
--           resolution=merge-duplicates` 업서트가 뷰에서도 PK를 찾아내는지는 미검증.
--           안 되면 수집기를 직접 Postgres 연결로 바꾸는 큰 작업이 된다.
--
-- 만약 그 전에 실제로 훼손되면 (복구 절차):
--   spatial_ref_sys는 표준 참조 데이터라 같은 PostGIS 버전 컨테이너에서 덤프해 복원한다.
--     docker run -d --name pgtmp public.ecr.aws/supabase/postgres:17.6.1.127 ...
--     docker exec pgtmp pg_dump -U postgres --data-only -t public.spatial_ref_sys postgres > srs.sql
--   그 뒤 Supabase SQL Editor에서 srs.sql 내용을 실행(필요 시 먼저 delete). 우리 업무
--   데이터에는 영향이 없다.

-- =====================================================================
-- 6) 확인 (붙여넣고 Run 한 뒤 이 쿼리로 검산)
-- =====================================================================
-- 기대: 11개 표 전부 rls_enabled = true
--
--   select relname as table_name, relrowsecurity as rls_enabled
--   from pg_class
--   where relnamespace = 'public'::regnamespace and relkind = 'r'
--   order by relname;
--
-- 기대: v_floor_stack만 anon에게 SELECT, 나머지 0행
--
--   select table_name, grantee, privilege_type
--   from information_schema.role_table_grants
--   where table_schema = 'public' and grantee in ('anon','authenticated')
--   order by table_name, grantee;
--
-- 기대: 정책 0행
--
--   select schemaname, tablename, policyname from pg_policies
--   where schemaname = 'public';
-- =====================================================================
