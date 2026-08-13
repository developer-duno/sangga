-- =====================================================================
-- 오늘 만든 요약표 2개가 공개키로 통째로 읽혔다 — 즉시 닫는다 (2026-08-13f)
-- =====================================================================
-- ## 무엇이 뚫려 있었나 (적대검증 실측, 2026-08-13)
--
--   GET /rest/v1/mv_search_parcel?select=pnu,road_addr&limit=3   → 200 (실제 주소 반환)
--   Prefer: count=exact                                          → 188,442행 전체 카운트 가능
--   GET /rest/v1/parcel?select=pnu&limit=1                       → 401 (원본은 정상 차단)
--
-- 즉 오늘 만든 "6,000곳 넘으면 끊는다"는 게이트를 **REST 페이지네이션으로 그냥
-- 건너뛸 수 있었다.** `?limit=1000&offset=N` 을 반복하면 도로명·지번주소·시군구·
-- 법정동 188,442건을 몇 분이면 통째로 내려받는다. 원본 표를 닫아 둔 설계가
-- 이 옆문으로 무력화된 상태였다.
--
-- ## 왜 이렇게 됐나 — 일회성 revoke 는 "그때 있던 표"만 닫는다
--
-- 2026-08-08 에 `revoke all on all tables in schema public from anon, authenticated;`
-- 를 돌려 원본 표들을 닫았다. 그런데 그건 **그 시점에 존재하던 객체만** 대상이다.
-- Supabase 는 스키마 public 에 기본 권한(pg_default_acl)을 걸어 두어,
-- **새로 만드는 표·물질화뷰마다 anon 에게 전체 권한을 자동으로 준다.**
-- 오늘 만든 mv_search_parcel(13d)·mv_open_sigungu(13e)가 정확히 그 경로로 열렸다.
-- ⚠️ 물질화뷰는 `enable row level security` 도 못 걸어(테이블 전용) 이중 방어도 없다.
--
-- ## 두 겹으로 막는다
--   ① 지금 열려 있는 두 개를 닫는다
--   ② **앞으로 만들 것도 자동으로 안 열리게** 기본 권한 자체를 바꾼다
--      — 이게 없으면 다음에 표를 하나 더 만들 때 같은 일이 또 난다(사람 기억에 의존).

begin;

-- ① 지금 열려 있는 것을 닫는다.
--    ⛔ `from public` 만으로는 아무것도 안 닫힌다 — anon·authenticated 가 **직접** 받은
--       GRANT 는 그대로 남는다(PostgreSQL 공식 sql-revoke.html + 2026-08-10 라이브 실측).
revoke all on mv_search_parcel from public, anon, authenticated;
revoke all on mv_open_sigungu  from public, anon, authenticated;

-- ② 앞으로 postgres 가 public 스키마에 만드는 표·물질화뷰는 기본으로 닫힌다.
--    이 프로젝트의 설계가 이미 "원본은 닫고 화면이 읽는 뷰만 연다" 이므로,
--    기본값이 "열림"인 쪽이 설계와 어긋나 있었다. 필요한 것만 명시적으로 grant 한다.
--    (명시 > 암묵 — 잊어서 열리는 것보다 잊어서 닫히는 편이 안전하다.)
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;

commit;

-- 화면이 읽는 것은 그대로 열려 있어야 한다(대조용 — 이미 열려 있으면 무해).
grant select on v_floor_stack    to anon, authenticated;
grant select on v_coverage_stats to anon, authenticated;
