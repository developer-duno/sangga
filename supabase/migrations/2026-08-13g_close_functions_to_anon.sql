-- =====================================================================
-- 함수도 기본으로 닫는다 + 화면이 안 쓰는 함수를 회수한다 (2026-08-13g)
-- =====================================================================
-- ## 2026-08-13f 가 반쪽이었다 (2차 적대검증에서 확인)
--
-- 13f 는 **표·시퀀스**의 기본 권한만 안전한 쪽으로 바꿨다. 그런데 라이브를 다시 보니
-- **함수는 그대로 자동 개방**이었다:
--
--   pg_default_acl (postgres, 객체종류 f) = {postgres=X, anon=X, authenticated=X, service_role=X}
--
-- 즉 `create function` 을 할 때마다 anon 이 **자동으로 실행 권한을 받는다.** 지금까지는
-- 새 함수를 만들 때마다 사람이 기억해서 `revoke` 를 적어 왔다(search_key·
-- building_display_nm·mask_person_name·parcel_jibun_addr·search_scope_limit).
-- 한 번이라도 잊으면 조용히 열린다 — 실제로 아래 ②가 그렇게 열려 있었다.
--
-- ## ① 앞으로 만들 함수는 기본으로 닫힘
--
-- 화면이 쓰는 것만 `grant execute` 로 **명시**한다(명시 > 암묵).
-- ⚠️ 이미 있는 함수의 권한은 안 바뀐다 — 기본 권한은 **새로 만드는 것**에만 적용된다.
--    그래서 아래 ②를 따로 회수한다.
alter default privileges in schema public
  revoke all on functions from anon, authenticated;

-- ## ② 화면이 안 쓰는데 열려 있던 것
--
-- `unit_business_append_only` 는 **트리거가 부르는 함수**다. 사람이 직접 부를 일이 없고,
-- 불러 봐야 예외만 던진다(무해). 그래도 노출면은 "화면이 실제로 쓰는 것"만 남긴다 —
-- 목록이 짧아야 진짜 이상한 것이 눈에 띈다.
revoke all on function unit_business_append_only() from public, anon, authenticated;

-- ## 화면이 쓰는 것은 그대로 열려 있어야 한다 (대조용 — 이미 열려 있으면 무해)
grant execute on function search_buildings(text, int, text) to anon, authenticated;
grant execute on function search_scope(text, text)          to anon, authenticated;
grant execute on function list_open_sigungu()               to anon, authenticated;

-- ⚠️ 남는 위험 (여기서는 못 막는다 — `python scripts/post_load.py --check` 가 잡는다)
--    Supabase 는 `supabase_admin` 롤에도 기본 권한을 걸어 두었고, 그 값은 여전히
--    anon 에게 전체 권한을 준다. 대시보드 SQL Editor 등이 그 롤로 객체를 만들면
--    이 설정으로는 안 막힌다(우리는 postgres 로 접속한다 — current_user 실측).
--    그래서 "만들 때 막는다"에 더해 **"만든 뒤 라이브를 직접 물어보는"** 점검을 둔다.
