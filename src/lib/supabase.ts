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

/**
 * 이 건물이 속한 상권을 묻는 서버 함수(`bld_id` 하나를 받는다).
 *
 * 돌려주는 것은 `{ covered, districts[] }` 두 칸뿐이다 — `covered` 는 "그 시·도에
 * 상권 경계 자료가 아예 있는가"이고, `districts` 는 그 건물이 실제로 들어가는 상권들이다.
 * 지역 이름을 화면에 박지 않으려고 `covered` 를 서버가 표에서 직접 센다(자료가 늘면
 * 화면이 저절로 따라온다).
 */
export const BUILDING_DISTRICTS_FN = 'list_building_districts';

/**
 * 이 필지에서 일어난 실거래 이력(`pnu` 하나를 받는다). Stage A — 결정 0012.
 *
 * 지번이 공개된 구간(2024-01 이후)만 나온다. 자기 실거래가 있는 필지는 서울 1.8% ·
 * 대전 1.4% 뿐이라 **대부분의 건물에서 빈 배열**이 정상이다.
 */
export const PARCEL_TX_FN = 'list_parcel_transactions';

/**
 * 구(시군구) 실거래 단가 분포(`sigungu` 5자리를 받는다). Stage A — 결정 0012.
 *
 * 층대 5칸이 항상 같은 순서로 온다. 구 이름·집계 창도 서버가 함께 주므로 화면에
 * 지역명이나 "최근 24개월" 같은 기간을 글자로 박지 않는다.
 */
export const SIGUNGU_TX_STATS_FN = 'get_sigungu_tx_stats';
