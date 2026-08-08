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

export const supabase = createClient(url, anonKey, {
  auth: { persistSession: false },
});

/** 층별 스택의 본체. */
export const FLOOR_STACK_VIEW = 'v_floor_stack';

/**
 * 화면 각주 숫자(점포 수·층 결측 비율)의 출처.
 *
 * 각주를 손으로 박아 두면 새 분기를 적재하는 순간 화면만 옛 숫자를 말한다
 * — 코드는 한 줄도 안 고쳤는데 거짓말이 시작되는 종류의 결함이다.
 */
export const COVERAGE_STATS_VIEW = 'v_coverage_stats';
