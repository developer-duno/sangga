-- =====================================================================
-- 마이그레이션 2026-09-01b — "새 함수는 공개키에게 안 열린다"는 규칙이 **가짜였다**
-- =====================================================================
-- 실행법: python scripts/dbx.py -f supabase/migrations/2026-09-01b_api_default_privileges.sql
--   → 그다음 `python scripts/post_load.py --check`
--
-- ─────────────────────────────────────────────────────────────────────
-- 무엇이 잘못돼 있었나 (2026-09-01 감사 후속 — 라이브 실측 + 공식 문서)
-- ─────────────────────────────────────────────────────────────────────
-- 정본은 두 스키마에 이렇게 적어 뒀고, 그것이 "앞으로 만들 함수도 자동으로 안 열리게"
-- 하는 뿌리라고 믿어 왔다:
--
--     alter default privileges in schema public revoke all on functions from anon, authenticated;
--     alter default privileges in schema api    revoke all on functions from anon, authenticated;
--
-- ⛔ **둘 다 PUBLIC 을 못 막는다.** 두 가지가 겹쳐서 그렇다:
--
--   ① PostgreSQL 의 **내장 기본값이 새 함수에 PUBLIC 으로 EXECUTE 를 준다**
--      (공식 문서 §5.8 표 5.2 — "FUNCTION or PROCEDURE: Default PUBLIC Privileges = X").
--      위 두 줄은 `anon`·`authenticated` 를 회수하는데, 그 둘은 내장 기본값에 **애초에
--      들어 있지 않다.** 없는 것을 회수하는 셈이라 PUBLIC 은 그대로 남는다.
--
--   ② **스키마별(per-schema) 회수로는 전역 기본값을 못 뺀다.** 공식 문서가 못 박는다:
--        "Per-schema REVOKE is only useful to reverse the effects of a previous
--         per-schema GRANT."
--      그리고 하필 **우리가 쓰던 그 문장을 '효과 없음'의 예시로** 들어 놨다:
--        "This command has no effect, unless it is undoing a matching GRANT:
--           ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;"
--      (이 마이그레이션의 첫 판이 정확히 그 형태였다가 라이브에서 무효임이 드러나 고쳤다.)
--
-- ⇒ 그래서 지금까지 **새 함수는 늘 PUBLIC 에게 열린 채 태어났다.** 지금 함수들이 안전한
--   것은 만든 자리마다 사람이 `revoke ... from public` 을 기억해 왔기 때문이지 규칙 덕이
--   아니다. 실제로 그 기억이 몇 번 빠졌고, 그 결과가 **PUBLIC EXECUTE 잔존 9개**다.
--
-- ⓘ `pg_default_acl` 을 보고 "public 스키마는 PUBLIC 이 빠져 있다"고 읽으면 안 된다 —
--   저장된 항목은 **전역 기본값에 더해지는 것**이라, 거기 PUBLIC 이 안 적혔다고 빠진 게
--   아니다. 실제로 public·api 둘 다 열려 있었다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 그래서 **전역**으로 회수한다 (스키마를 지정하지 않는다)
-- ─────────────────────────────────────────────────────────────────────
-- ⚠️ 영향 범위를 정직하게 적는다:
--   · **앞으로 `postgres` 롤이 만드는 함수에만** 걸린다. 기존 91개(public 25·api 17·
--     extensions 49)는 **한 개도 안 바뀐다** — 기본권한은 "앞으로"에만 적용된다.
--   · 다른 롤(supabase_admin 등)이 만드는 것에는 안 걸린다. 그래서 **만든 자리에서
--     `revoke` 하는 관습은 그대로 유지한다** — 이건 그물이지 대체재가 아니다.
--   · 화면은 안 깨진다: 화면이 부르는 api 통과 함수 17개는 전부 `security definer`·
--     postgres 소유라 소유자 권한으로 돌고, anon 에게는 명시 `grant` 가 따로 있다.
-- ⛔ 되돌리는 법(한 줄):
--     alter default privileges grant execute on functions to public;
--
-- ⓘ 이 변경의 방향은 이 레포의 철학과 같다 — **조용히 열리는 것보다 시끄럽게 막히는 편**이
--   낫다. 새 함수에 grant 를 빠뜨리면 권한 오류로 곧바로 드러난다(지금은 조용히 열린다).

begin;

-- ⛔ `in schema …` 를 붙이지 말 것. 붙이는 순간 위 ②의 이유로 **아무 일도 하지 않는다.**
alter default privileges revoke execute on functions from public;

commit;

-- 권한 변경이라 설정도 함께 알린다(형제 마이그레이션과 같은 관습).
notify pgrst, 'reload config';
notify pgrst, 'reload schema';
