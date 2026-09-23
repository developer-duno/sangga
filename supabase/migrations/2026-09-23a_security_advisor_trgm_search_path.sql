-- 2026-09-23a: Supabase 보안 고문 경고 8건 해소 — pg_trgm 을 extensions 로 · 헬퍼 함수 7개 search_path 고정
--   mibunyang 세션566 (사장님 지시 "상가쪽 문제해결 부탁해") · 라이브 적용완료(psql, 한 트랜잭션 안 자체검사 후 COMMIT)
--
-- 경고 0014 Extension in Public — pg_trgm 1.6(relocatable). trigram 색인 7개(building.bld_nm·nm_key ·
--   parcel.road/jibun_addr_key · mv_search_parcel.road/jibun_addr_key · mv_parcel_store_names.store_names_key,
--   gin_trgm_ops)는 연산자 클래스를 OID 로 참조하므로 스키마를 옮겨도 그대로 동작한다.
--   상가 함수 본문에 trigram 함수·연산자 이름 사용 0건(실측).
-- 경고 0011 Function Search Path Mutable ×7 — 전부 SECURITY INVOKER 헬퍼(immutable sql 6 + 트리거 1).
--   ⚠️ SET 절이 붙은 SQL 함수는 플래너가 인라인하지 못한다 → 호출당 비용이 조금 는다
--      (mv_search_parcel 새로고침 때 search_key 가 행마다 불린다). 출력은 같다.
--
-- 적용 전후 자체검사(모두 동일): 함수 6개 출력 · 색인 7개 칸 ILIKE '%강남%' 건수(554~14,749) ·
--   trigram 색인 valid · search_path 7/7.
-- 적용 후 스모크(읽기 전용): search_buildings('테헤란로',5,null)=5행 · search_stores('스타벅스',5,'11680',null)=5행 ·
--   search_scope('강남',null)=too_broad/12,961.
--
-- 그대로 둔 것(이 파일 밖, 이유는 인계 메모 참조):
--   · 보안 정의자 뷰 v_floor_stack · v_coverage_stats = 의도된 설계(원본 표는 anon 정책 0 으로 잠그고 뷰로만 공개).
--     security_invoker 로 바꾸면 화면이 빈다.
--   · spatial_ref_sys RLS 꺼짐 · postgis in public · st_estimatedextent ×6 = PostGIS 고유.
--     주인 supabase_admin · postgis 3.3.7 relocatable=false · 시험 REVOKE(되돌림) "no privileges could be revoked".
--
-- ROLLBACK:
-- ALTER EXTENSION pg_trgm SET SCHEMA public;
-- ALTER FUNCTION public.building_display_nm(text, text) RESET search_path;
-- ALTER FUNCTION public.mask_person_name(text) RESET search_path;
-- ALTER FUNCTION public.parcel_jibun_addr(text, text, text, text) RESET search_path;
-- ALTER FUNCTION public.price_floor_band(smallint) RESET search_path;
-- ALTER FUNCTION public.search_key(text) RESET search_path;
-- ALTER FUNCTION public.search_scope_limit() RESET search_path;
-- ALTER FUNCTION public.unit_business_append_only() RESET search_path;

ALTER EXTENSION pg_trgm SET SCHEMA extensions;
ALTER FUNCTION public.building_display_nm(text, text) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.mask_person_name(text) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.parcel_jibun_addr(text, text, text, text) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.price_floor_band(smallint) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.search_key(text) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.search_scope_limit() SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.unit_business_append_only() SET search_path = public, extensions, pg_temp;
