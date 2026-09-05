-- =====================================================================
-- 마이그레이션 2026-09-05a — 열린 채 남아 있던 public 함수 9개 닫기
-- =====================================================================
-- 실행법: python scripts/dbx.py -f supabase/migrations/2026-09-05a_close_public_leftovers.sql
--   → 그다음 `python scripts/post_load.py --check`
--   기대 출력: "[정상] 공개키가 읽거나 부를 수 있는 것은 허용된 21개뿐입니다."
--             + [주의] 0줄 + [정리] 0줄. (지금은 [주의] 9줄이 뜬다.)
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 아홉 개가 아직 열려 있나
-- ─────────────────────────────────────────────────────────────────────
-- PostgreSQL 은 새로 만드는 함수에 PUBLIC(= 이 DB 의 모든 롤) EXECUTE 를 기본으로 준다
-- (공식 문서 §5.8 표 5.2 — "FUNCTION or PROCEDURE: Default PUBLIC Privileges = X").
-- 그 기본값을 막는 전역 한 줄은 **2026-09-01b** 에서야 들어갔고, 기본권한은 성질상
-- "앞으로 만들 것"에만 걸린다 — 그 줄이 생기기 전에 태어난 함수는 한 개도 안 바뀐다.
-- 이 아홉이 정확히 그 앞 세대다(라이브 `proacl` 실측: 전부 `=X/postgres` = PUBLIC 보유).
--
-- ⛔ **`revoke ... from public` 만으로는 안 닫힌다.** 아홉 전부 PUBLIC 말고도
--    `anon=X/postgres`·`authenticated=X/postgres` 를 **따로 직접** 갖고 있다. PUBLIC 은
--    실제 롤이 아니라 "모든 롤"을 가리키는 가상 그룹이라, 거기서 회수해도 직접 받은 몫은
--    그대로 남는다. 공식 문서(sql-revoke.html)가 못 박는다:
--      "revoking ... from PUBLIC does not necessarily mean that all roles have lost ...
--       privilege: those who have it granted directly ... will still have it"
--    2026-08-10 에 이 레포가 똑같은 함정에 한 번 데였다(도우미 함수 revoke 가 적혀 있는데도
--    anon 공개키 RPC 가 HTTP 200 이었다). 그래서 세 대상을 모두 적는다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 화면은 안 깨진다 (닫아도 되는 근거)
-- ─────────────────────────────────────────────────────────────────────
-- 화면은 `api.*` 래퍼 17개만 부른다. 그 열일곱은 전부 `security definer`·postgres 소유라
-- **부르는 사람 권한이 아니라 소유자 권한으로** 속을 읽는다 — 여기서 닫는 public 원본에
-- anon 이 직접 닿을 필요가 없다(2026-09-05 라이브 실측으로 재확인).
-- ⓘ 실피해는 원래도 0 이었다 — REST 노출 스키마에서 public 을 빼 뒀기 때문에(2026-08-24
--   "옛 문 닫기") 인터넷에서 이 아홉에 닿는 길 자체가 없다. 그래도 닫는 이유는 방어를
--   한 겹(노출 설정)에만 기대지 않기 위해서다. 그 설정이 되돌아가는 날 이게 마지막 문이다.
--
-- ⓘ `service_role` 은 **일부러 남긴다.** 적재기·점검 스크립트가 그 열쇠로 도는데,
--    같이 회수하면 화면이 아니라 우리 도구가 조용히 멈춘다.
--
-- ⛔ 되돌리는 법(그대로 되돌린다):
--     grant execute on function public.get_sigungu_tx_stats(text)      to anon, authenticated;
--     grant execute on function public.list_building_districts(text)   to anon, authenticated;
--     grant execute on function public.list_industry_detail(text, text) to anon, authenticated;
--     grant execute on function public.list_industry_mix(text)         to anon, authenticated;
--     grant execute on function public.list_open_sigungu()             to anon, authenticated;
--     grant execute on function public.list_parcel_transactions(text)  to anon, authenticated;
--     grant execute on function public.list_price_bands(text)          to anon, authenticated;
--     grant execute on function public.search_buildings(text, integer, text) to anon, authenticated;
--     grant execute on function public.search_scope(text, text)        to anon, authenticated;

begin;

revoke execute on function public.get_sigungu_tx_stats(text)          from public, anon, authenticated;
revoke execute on function public.list_building_districts(text)       from public, anon, authenticated;
revoke execute on function public.list_industry_detail(text, text)    from public, anon, authenticated;
revoke execute on function public.list_industry_mix(text)             from public, anon, authenticated;
revoke execute on function public.list_open_sigungu()                 from public, anon, authenticated;
revoke execute on function public.list_parcel_transactions(text)      from public, anon, authenticated;
revoke execute on function public.list_price_bands(text)              from public, anon, authenticated;
revoke execute on function public.search_buildings(text, integer, text) from public, anon, authenticated;
revoke execute on function public.search_scope(text, text)            from public, anon, authenticated;

commit;

-- 권한 변경이라 설정도 함께 알린다(형제 마이그레이션과 같은 관습).
notify pgrst, 'reload config';
notify pgrst, 'reload schema';

-- 확인: 아홉의 ACL 에 anon·authenticated·PUBLIC(빈 grantee)이 남아 있으면 안 된다.
--       service_role 만 남는 것이 정상이다.
--
--   select p.proname, p.proacl
--     from pg_proc p
--     join pg_namespace n on n.oid = p.pronamespace
--    where n.nspname = 'public'
--      and p.proname in ('get_sigungu_tx_stats','list_building_districts',
--                        'list_industry_detail','list_industry_mix','list_open_sigungu',
--                        'list_parcel_transactions','list_price_bands',
--                        'search_buildings','search_scope')
--    order by p.proname;
