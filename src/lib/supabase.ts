import { createClient } from '@supabase/supabase-js';

/**
 * 브라우저용 Supabase 클라이언트.
 *
 * ⚠️ 여기 들어오는 값은 브라우저에 그대로 실린다. Vite는 `VITE_`로 시작하는
 * 환경변수만 번들에 넣으므로, 관리자 키(SERVICE_KEY)에는 절대 `VITE_`를
 * 붙이지 않는다. 공개키(anon)만 쓴다.
 */
const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  throw new Error(
    '.env.local에 VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY가 필요합니다. ' +
      'scripts/make_env_local.py를 실행하면 .env에서 자동으로 만들어집니다.',
  );
}

/**
 * ⚠️ `db: { schema: 'api' }` 를 지우지 말 것 (2026-08-22e).
 *
 * 서버는 PostgREST 가 보는 스키마를 `public` 에서 `api` 로 옮긴다 — PostGIS 가 public 에
 * 설치돼 시스템 표(`spatial_ref_sys`)가 REST 로 노출되는데 소유자가 supabase_admin 이라
 * 우리 권한으로 회수가 안 되기 때문이다(회수 대신 이사).
 *
 * supabase-js 는 이 값이 없으면 요청마다 `accept-profile: public` 헤더를 보낸다(실측).
 * 즉 여기를 비워 두면 서버가 api 만 노출한 순간 **화면 전체가 PGRST106/406** 이 된다.
 *
 * 그래서 적용 순서가 정해져 있다 — ①마이그레이션 2026-08-22e →
 * ②대시보드 Exposed schemas 에 `api` 추가(순서 `api, public`) → ③이 코드 배포 →
 * ④Exposed schemas 에서 `public` 제거. **②보다 ③이 먼저 나가면 화면이 죽는다.**
 * (파이썬 수집기는 profile 헤더를 안 보내 "첫 스키마"를 타므로 코드 변경이 없다 —
 *  그래서 목록 순서가 `api, public` 이라야 한다.)
 */
export const supabase = createClient(url, anonKey, {
  auth: { persistSession: false },
  db: { schema: 'api' },
});
