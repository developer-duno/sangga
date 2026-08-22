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
 * 이 필지 거래 목록을 서버가 끊는 건수. **서버가 정본**이다
 * (`supabase/schema.sql` 의 `list_parcel_transactions` → `limit 100`).
 *
 * 한 필지에 852건인 곳이 실재해서 서버가 끊는다. 화면은 "잘렸다"고 말해야 하는데,
 * 그 숫자를 따로 박아 두면 서버가 200으로 늘리는 날 화면만 100이라 말한다.
 * ⚠️ 서버 쪽 `limit` 을 고치면 이 값도 같은 커밋에서 함께 고친다.
 */
export const TX_LIST_CAP = 100;

/**
 * 이 필지 거래 목록이 시작되는 달. **서버가 정본**이다
 * (`supabase/schema.sql` 의 `list_parcel_transactions` → `contract_ym >= '202401'`).
 *
 * 그 전 계약분은 지번이 가려져 필지에 붙일 수 없다. 위와 같은 이유로 짝을 맞춰 둔다.
 */
export const TX_OPEN_SINCE_LABEL = '2024년 1월';

/**
 * 실거래 자료에서 층 표기가 빈 값으로 오기 시작한 해.
 *
 * 우리 파싱 문제가 아니라 국토부가 그렇게 준다(원본 전수 재계수로 확인). 층 미상이
 * 왜 이렇게 많은지, 지하는 왜 참고 시세를 못 내는지 두 화면이 같은 사실을 말하므로
 * 숫자를 한 곳에 둔다.
 */
export const TX_BASEMENT_MISSING_SINCE = 2017;

/**
 * 구(시군구) 실거래 단가 분포(`sigungu` 5자리를 받는다). Stage A — 결정 0012.
 *
 * 층대 5칸이 항상 같은 순서로 온다. 구 이름·집계 창도 서버가 함께 주므로 화면에
 * 지역명이나 "최근 24개월" 같은 기간을 글자로 박지 않는다.
 */
export const SIGUNGU_TX_STATS_FN = 'get_sigungu_tx_stats';

/**
 * 이 필지의 층별 참고 매매 시세 밴드. Stage B — 결정 0013.
 *
 * ⚠️ **인자 이름이 `p_pnu` 다.** 형제 넷은 `bld_id`·`pnu`·`sigungu` 인데 이 함수만
 *    접두사가 붙어 있다(파라미터가 컬럼명 `pnu` 와 겹치면 SQL 안에서 어느 쪽인지
 *    갈리지 않기 때문). 목(mock)은 인자 **이름**을 안 보므로 `{ pnu: … }` 로 잘못
 *    불러도 vitest·E2E 는 전부 초록이고 **라이브에서만** PGRST202 가 난다.
 *
 * 돌려주는 것은 층마다 한 줄, 또는 **`gate_fail` 한 줄뿐**이다:
 *  · 참고 시세를 켜도 되는 구인지는 서버가 표(`price_gate_sigungu`)를 보고 정한다.
 *    아니면 층 목록 대신 `floor_no: null` 인 `gate_fail` 한 줄만 온다.
 *  · ⛔ 통과 구 목록을 화면·문서에 복사하지 않는다(결정 0013 §4). 목록의 진실은
 *    서버 한 곳이고, 성적표를 다시 뽑으면 화면이 저절로 따라온다.
 *  · 안 내는 이유가 넷(`gate_fail`·`floor_1f`·`no_evidence`·`no_estimate`)이고 각각
 *    다른 뜻이다 — 화면이 하나로 뭉뚱그리면 "모르는 것"을 "없는 것"이라 말하게 된다.
 */
export const PRICE_BANDS_FN = 'list_price_bands';

/**
 * 이 필지 둘레의 업종 분포(대분류). 결정 0014 — 상권 지표 1단계.
 *
 * ⚠️ **인자 이름이 `p_pnu` 다**(`list_price_bands` 와 같은 이유 — 컬럼명 `pnu` 와 겹친다).
 *    목(mock)은 인자 이름을 안 보므로 `{ pnu: … }` 로 잘못 불러도 vitest·E2E 는 전부
 *    초록이고 **라이브에서만** PGRST202 가 난다.
 *
 * 돌려주는 것은 두 스코프다 — 속한 상권마다 한 묶음(겹치면 전부) + 반경 하나.
 * 기준 분기·반경 길이도 함께 오므로 화면에 '2026년 6월'·'500m'를 글자로 박지 않는다.
 */
export const INDUSTRY_MIX_FN = 'list_industry_mix';

/**
 * 고른 대분류 안의 중분류 분포. 대분류를 누를 때만 부른다.
 *
 * ⚠️ 인자가 **둘**이다 — `{ p_pnu, p_cat }`. 응답의 `cat_l_cd` 는 물어본 값을 그대로
 *    되돌려 준 것이라, 그 사이 다른 업종을 고른 경우 늦게 온 답을 버리는 데 쓴다.
 */
export const INDUSTRY_DETAIL_FN = 'list_industry_detail';
