import { test, expect, type Page } from '@playwright/test';
import {
  searchHit,
  floorRow,
  coverageStats,
  parcelTx,
  sigunguTxStats,
  industryMix,
  industryFloors,
  industryMedian,
  industryMedianM,
  industryDetailTwoDistricts,
  industryMixTwoDistricts,
  nearbyPermits,
  basePrices,
  lhNotice,
  rentStat,
  rentStatOld,
  rentStats,
  openClose,
  openCloseNotSeoul,
  daejeonClosure,
  districtSales,
  districtPop,
  dataFreshness,
  storeHit,
  unitSummary,
  floorUnitsPage,
} from './fixtures';

/**
 * "여러 조각이 실제로 이어 붙는가"만 본다 — App.tsx가 실제로 BuildingSearch·FloorStack을
 * state로 이어 붙이는 부분. 층 표기 부호·각주 숫자 같은 순수 변환 로직은
 * src/components/FloorStack.test.tsx·BuildingSearch.test.tsx가 이미 촘촘히 덮고 있어
 * 여기서 반복하지 않는다.
 *
 * 네트워크(Supabase REST)는 전부 page.route로 가로챈다 — 라이브 DB·비밀값 의존 0.
 * supabase-js가 부르는 실제 경로:
 *   POST /rest/v1/rpc/list_open_sigungu  (구 목록 — RegionPicker가 마운트 시 부른다)
 *   POST /rest/v1/rpc/search_buildings   (검색)
 *   GET  /rest/v1/v_coverage_stats       (각주 집계)
 *   GET  /rest/v1/v_floor_stack          (층 목록)
 *   POST /rest/v1/rpc/list_building_districts  (속한 상권 — FloorStack이 건물마다 부른다)
 * playwright.config.ts에서 VITE_SUPABASE_URL을 실존하지 않는 도메인으로 주입하므로
 * 브라우저 입장에서 전부 교차 출처(cross-origin) 요청이다 — preflight(OPTIONS)도 함께
 * 응답해야 실제 GET/POST가 나간다.
 *
 * ⚠️ 2026-08-13부터 검색은 "구를 고른 뒤 그 안에서만" 한다(사장님 결정) — RegionPicker가
 *    마운트되자마자 list_open_sigungu를 부르므로, 검색 전에 반드시 구를 하나 고르는
 *    단계가 필요하다(pickGu 헬퍼). 안 그러면 "먼저 지역을 골라 주세요" 안내만 뜬다.
 */

const SIGUNGU_PATTERN = '**/rest/v1/rpc/list_open_sigungu*';
const SEARCH_PATTERN = '**/rest/v1/rpc/search_buildings*';
// 결과가 0건이면 화면이 "정말 없음"인지 "검색어가 너무 넓음"인지 서버에 한 번 더 묻는다.
// ⚠️ 이걸 안 막으면 그 요청이 **진짜 Supabase 로 나간다** — 테스트가 네트워크와 라이브
//    데이터에 좌우된다(2026-08-13 에 실제로 그런 상태였다).
const SCOPE_PATTERN = '**/rest/v1/rpc/search_scope*';
// 가게 이름으로 찾은 땅(결정 0028) — 검색 한 번에 **건물과 나란히** 나가는 두 번째 요청이다.
// ⚠️ 안 막으면 실존하지 않는 도메인으로 요청이 나가 테스트가 DNS 에 좌우된다.
// ⓘ 기본값은 **빈 배열**이다(함수 부재가 아니다) — 그러면 구역이 안 서므로 기존 검색
//   스펙들이 보는 화면이 그대로다. 함수 부재 경로는 단위 시험이 따로 본다.
const SEARCH_STORES_PATTERN = '**/rest/v1/rpc/search_stores*';
const STATS_PATTERN = '**/rest/v1/v_coverage_stats*';
const FLOOR_PATTERN = '**/rest/v1/v_floor_stack*';
// ⚠️ 이 함수는 jsonb **스칼라**를 돌려준다 — PostgREST 가 그대로 JSON 으로 주므로
//    응답이 행 배열이 아니라 **객체 하나**다. 배열로 흉내 내면 라이브와 모양이 달라져
//    "테스트만 통과하는" 가짜 초록이 된다.
const DISTRICT_PATTERN = '**/rest/v1/rpc/list_building_districts*';
// 실거래 사실 표시(Stage A · 결정 0012). 층 스택이 건물마다 이 둘을 더 부른다 —
// 막지 않으면 실존하지 않는 도메인으로 요청이 나가 테스트가 네트워크에 좌우된다.
const PARCEL_TX_PATTERN = '**/rest/v1/rpc/list_parcel_transactions*';
const TX_STATS_PATTERN = '**/rest/v1/rpc/get_sigungu_tx_stats*';
// 국세청 기준시가. 『층별 공표값 나란히』 카드의 기준시가 칸에 들어간다(결정 0041 — 내린 참고 시세 카드에서 옮겼다).
// ⚠️ 기본값은 **함수가 없는 상태**(404/PGRST202)다 — 마이그레이션 적용 전 라이브가 바로
//    그 상태이고, 그때 이 줄이 조용히 빠지는지가 테스트 V 의 관심사다. 안 막으면 실존하지
//    않는 도메인으로 요청이 나가 테스트가 DNS 에 좌우된다.
const BASE_PRICE_PATTERN = '**/rest/v1/rpc/list_base_prices*';
// 둘레의 업종 분포(결정 0014). 층 스택이 건물마다 이 둘을 더 부른다.
// ⚠️ **일부러 404(PGRST202)로 답한다** — 마이그레이션을 적용하기 전 라이브가 바로 그
//    상태이고, 그때 이 섹션이 **조용히 사라지는지**가 여기서 확인하려는 것이다.
//    (안 막으면 실존하지 않는 도메인으로 요청이 나가 테스트가 DNS 에 좌우된다.)
const INDUSTRY_MIX_PATTERN = '**/rest/v1/rpc/list_industry_mix*';
const INDUSTRY_DETAIL_PATTERN = '**/rest/v1/rpc/list_industry_detail*';
// 업종별 층 분포(물결 2-2) — 대분류를 고른 뒤에만 부른다. 기본은 **함수가 없는 상태**(상세와 같은 이유 —
// 층 줄만 조용히 빠진다). 층 줄을 보는 것은 스펙 AO(와 AN 의 목업)뿐이다.
const INDUSTRY_FLOORS_PATTERN = '**/rest/v1/rpc/list_industry_floors*';
// 업종 비중 비교(물결 2-3) — 업종 분포 카드의 상권 블록 비교 글. 건물을 열 때 곁 카드와 함께 미리 나간다.
// 기본은 **함수가 없는 상태**(비교 글만 조용히 빠진다 — 다른 스펙의 카드 글자가 그대로다). 비교 글을 보는 것은 스펙 AW 뿐이다.
// ⛔ 끝에 `*` 를 붙이지 않는다 — 붙이면 중분류 함수(`list_industry_median_m`)까지 잡는다(rpc 는 POST 라 주소 뒤에 물음표 인자가 없다).
const INDUSTRY_MEDIAN_PATTERN = '**/rest/v1/rpc/list_industry_median';
// 업종 비중 비교 · 중분류(물결 2-3b) — 대분류를 고른 뒤 상세와 따로 부른다. 기본은 **함수가 없는 상태**(중분류 비교 글만
// 조용히 빠진다). 비교 글을 보는 것은 스펙 AX 뿐이다.
const INDUSTRY_MEDIAN_M_PATTERN = '**/rest/v1/rpc/list_industry_median_m*';
// 둘레에 새로 올라오는 상가 건물(건축 인허가). 업종 분포 카드 **안**에 한 줄로 붙지만
// 자료는 완전히 다른 것이다(장사 중인 가게 수 ↔ 아직 안 지어진 건물 수).
// ⚠️ 기본값은 역시 **함수가 없는 상태**다 — 안 막으면 실존하지 않는 도메인으로 요청이
//    나가 테스트가 DNS 에 좌우된다.
const NEARBY_PERMITS_PATTERN = '**/rest/v1/rpc/count_nearby_permits*';
// 상권 임대 동향(결정 0024). 층별 화면의 임대 카드가 이것 하나를 부른다.
// ⚠️ 몇 번째 카드인지는 적지 않는다 — 카드가 늘 때마다 이 주석이 낡는다.
//    지금 몇 장이고 순서가 어떤지는 src/lib/sectionCards.ts 의 SECTION_PLAN 이 정본이다.
// ⚠️ 기본값은 역시 **함수가 없는 상태**다 — 마이그레이션 적용 전 라이브이 그것이고,
//    그때 카드가 통째로 조용히 빠지는지가 테스트 AA 의 관심사다.
const RENT_STATS_PATTERN = '**/rest/v1/rpc/list_rent_stats*';
// 임대 동향의 8분기 흐름(결정 0038 C · V5) — 건물을 고르는 순간 곁 카드와 함께 미리 나간다.
// ⚠️ 기본값은 **함수가 없는 상태**다 — 그때 흐름만 조용히 빠지고 임대 카드는 그대로라 다른 스펙이 영향을 안 받는다.
//    흐름을 보는 것은 스펙 CI 뿐이다. ⓘ 위 `list_rent_stats*` 꼴은 이 이름(`list_rent_stat_history`)과 안 겹친다.
const RENT_HISTORY_PATTERN = '**/rest/v1/rpc/list_rent_stat_history*';
// 상권 개업·폐업(결정 0033). ⚠️ 기본값은 **함수가 없는 상태**다(임대 동향과 같은 이유) — 다른
// 스펙들의 카드 수·화면이 그대로 남는다. 카드를 보는 것은 스펙 AI 뿐이다.
const OPEN_CLOSE_PATTERN = '**/rest/v1/rpc/list_district_openclose*';
// 개업·폐업 「전부 보기」(결정 0038 H · V6) — 카드가 8분기 답에서 상권 줄을 받으면 스스로 한 번 더 묻는다.
// ⓘ 위 `list_district_openclose*` 꼴이 이 이름(`list_district_openclose_all`)도 잡는다 — 그래서 기본값(함수 없음)도 같이
//   받고, 개폐업 답을 덮은 스펙에서는 8분기 답(total_quarters 칸 없음)을 받아 단추만 조용히 빠진다. 단추를 보는 것은 스펙 CJ 뿐이다
//   (그 스펙은 이 꼴을 **나중에** 등록해 먼저 잡히게 한다).
const OPEN_CLOSE_ALL_PATTERN = '**/rest/v1/rpc/list_district_openclose_all*';
// 대전 「동네 폐업 (대전시 공표)」(결정 0044) — 대전 필지를 열 때만 곁 카드와 함께 미리 나간다(서울 건물은 요청 0).
// ⚠️ 기본값은 **함수가 없는 상태**다 — 그때 대전 건물의 개업·폐업 카드는 지금 대전 화면 그대로라 스펙 AI 가 그대로다.
//    대전 카드를 보는 것은 스펙 CM 뿐이다(안 막으면 실존하지 않는 도메인으로 나가 DNS 에 좌우된다).
const DAEJEON_CLOSURE_PATTERN = '**/rest/v1/rpc/get_daejeon_dong_closure*';
// 업종별 추정매출 · 상권 인구(결정 0045 PR③) — 서울 필지를 열 때만 곁 카드와 함께 미리 나간다(대전 건물은 요청 0).
// ⚠️ 기본값은 **함수가 없는 상태**다 — 그때 두 카드는 통째로 빠지고 다른 스펙의 카드 수·화면이 그대로다.
//    카드를 보는 것은 스펙 CN·CO(와 차례 전체를 견주는 AM)뿐이다(안 막으면 실존하지 않는 도메인으로 나가 DNS 에 좌우된다).
const SALES_PATTERN = '**/rest/v1/rpc/list_district_sales*';
const POP_PATTERN = '**/rest/v1/rpc/list_district_pop*';
// 호실 구성표(결정 0032). 요약은 건물을 열 때 · 목록은 층을 펼칠 때 나간다.
// ⚠️ 기본값은 둘 다 **함수가 없는 상태**다 — 그때 요약도 "자료 없음" 안내도 조용히 빠지는지가
//    스펙 AH 의 관심사다(빈 배열로 두면 "호실 자료가 없는 건물"이라는 **다른 답**이 되어 안내가 선다).
const UNIT_SUMMARY_PATTERN = '**/rest/v1/rpc/list_unit_floor_summary*';
const FLOOR_UNITS_PATTERN = '**/rest/v1/rpc/list_floor_units*';
// 개별공시지가 한 줄(결정 0036 결정 7) — 층별 화면 머리의 사양 칸 아래. 건물을 열 때 나간다.
// ⚠️ 기본값은 **함수가 없는 상태**다 — 그때 줄이 조용히 빠지고 머리 모양이 그대로라 다른 스펙이 영향을
//    안 받는다. 값을 보는 것은 스펙 AP 뿐이다(안 막으면 실존하지 않는 도메인으로 나가 DNS 에 좌우된다).
const LAND_PRICE_PATTERN = '**/rest/v1/rpc/get_parcel_land_price*';
// 층 목록 업종 띠(결정 0038 D · V4) — 건물을 고르는 순간 곁 카드와 함께 미리 나간다.
// ⚠️ 기본값은 **함수가 없는 상태**다 — 그때 띠·「층 모름」 줄이 조용히 빠지고 층 목록 모양이 그대로라 다른 스펙이 영향을
//    안 받는다. 띠를 보는 것은 스펙 CG·CH·AF 뿐이다(안 막으면 실존하지 않는 도메인으로 나가 DNS 에 좌우된다).
const FLOOR_INDUSTRY_PATTERN = '**/rest/v1/rpc/list_floor_industry*';
// 의견함(2026-08-24b). 화면에서 창고로 **나가는** 유일한 길이라, 여기만 방향이 반대다.
const FEEDBACK_PATTERN = '**/rest/v1/rpc/submit_feedback*';
// LH 상가 분양·입점 공고 — 유일하게 **입구**(건물을 고르기 전)에서 나가는 요청이다.
// ⚠️ 층 스택이 아니라 구를 고르는 순간 나가므로 `mockFloorStack` 이 아니라
//    `mockOpenSigungu` 와 한 쌍으로 막는다(아래).
const LH_NOTICE_PATTERN = '**/rest/v1/rpc/list_lh_notices*';
// 화면 아래 신선도 표(2026-09-05d). ⚠️ **첫 그림에서 바로 나간다** — 푸터는 구를 고르기
// 전에도 서 있어서, 건물·구와 아무 상관 없이 모든 시험에서 이 요청이 뜬다. 그래서
// `mockOpenSigungu` 와 한 쌍으로 막는다(안 막으면 실존하지 않는 도메인으로 나가 테스트가
// DNS 에 좌우된다).
// ⚠️ 기본값은 역시 **함수가 없는 상태**다 — 마이그레이션 적용 전 라이브가 그것이고, 그때
//    표가 통째로 조용히 빠지는지가 테스트 M 의 관심사 중 하나다.
const DATA_FRESHNESS_PATTERN = '**/rest/v1/rpc/get_data_freshness*';
// 동네 매매 단가 흐름(결정 0027) — 이것도 **입구**에서 나가는 요청이다(위 둘과 한 쌍으로 막는다).
// ⚠️ 기본값은 역시 **함수가 없는 상태**다 — 마이그레이션 적용 전 라이브이 그것이고,
//    그때 카드가 통째로 조용히 빠지는지가 스펙 X 의 관심사다.
const TX_YEARLY_PATTERN = '**/rest/v1/rpc/get_sigungu_tx_yearly*';

const CORS_HEADERS = {
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'GET,POST,OPTIONS',
  'access-control-allow-headers': '*',
};

async function mockJson(page: Page, pattern: string, body: unknown, delayMs = 0) {
  await page.route(pattern, async (route) => {
    if (route.request().method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: CORS_HEADERS });
      return;
    }
    if (delayMs > 0) await new Promise((r) => setTimeout(r, delayMs));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: CORS_HEADERS,
      body: JSON.stringify(body),
    });
  });
}

/**
 * 층 스택이 부르는 REST 를 한 벌로 막는다.
 *
 * `mix` 를 안 주면 업종 분포 함수 둘을 **없는 것으로** 답한다(마이그레이션 적용 전 라이브).
 * 그게 기본값인 이유는, 그 상태에서 섹션이 조용히 사라지는지가 테스트 A 의 관심사이기
 * 때문이다 — 정상 응답을 보고 싶으면 그때만 넘긴다(테스트 K).
 */
async function mockFloorStack(
  page: Page,
  txs: unknown[] = [],
  floors?: unknown[],
  mix?: unknown,
  bases?: unknown[],
  permits?: unknown,
  rents?: unknown[],
) {
  await mockJson(page, STATS_PATTERN, [coverageStats()]);
  await mockJson(page, FLOOR_PATTERN, floors ?? [floorRow()]);
  await mockJson(page, PARCEL_TX_PATTERN, txs);
  await mockJson(page, TX_STATS_PATTERN, sigunguTxStats());
  await mockJson(page, DISTRICT_PATTERN, {
    covered: true,
    districts: [{ name: '역삼역', type: '발달상권' }],
    // 출처는 화면에 박힌 글자가 아니라 서버가 자료에서 읽어 주는 값이다(2026-08-14).
    sources: ['서울특별시 상권분석서비스'],
  });
  // 업종 분포는 기본이 **함수가 없는 상태**다(위 상수 주석 참조).
  if (mix === undefined) {
    await mockMissingFunction(page, INDUSTRY_MIX_PATTERN);
  } else {
    await mockJson(page, INDUSTRY_MIX_PATTERN, mix);
  }
  // 상세는 대분류를 고를 때만 부른다 — 여기서는 늘 없는 상태로 둔다(고르는 흐름은
  // src/components/IndustryMixSection.test.tsx 가 이미 촘촘히 덮는다).
  await mockMissingFunction(page, INDUSTRY_DETAIL_PATTERN);
  await mockMissingFunction(page, INDUSTRY_FLOORS_PATTERN);
  // 업종 비중 비교(물결 2-3)도 기본이 **함수가 없는 상태**다(위 상수 주석 참조). 스펙 AW 만 덮어쓴다.
  await mockMissingFunction(page, INDUSTRY_MEDIAN_PATTERN);
  // 중분류(물결 2-3b)도 기본이 **함수가 없는 상태**다. 스펙 AX 만 덮어쓴다.
  await mockMissingFunction(page, INDUSTRY_MEDIAN_M_PATTERN);
  // 기준시가도 기본이 **함수가 없는 상태**다(위 상수 주석 참조).
  if (bases === undefined) {
    await mockMissingFunction(page, BASE_PRICE_PATTERN);
  } else {
    await mockJson(page, BASE_PRICE_PATTERN, bases);
  }
  // 둘레의 인허가 한 줄도 기본이 **함수가 없는 상태**다(위 상수 주석 참조).
  if (permits === undefined) {
    await mockMissingFunction(page, NEARBY_PERMITS_PATTERN);
  } else {
    await mockJson(page, NEARBY_PERMITS_PATTERN, permits);
  }
  // 상권 임대 동향도 기본이 **함수가 없는 상태**다(위 상수 주석 참조).
  // ⛔ 빈 배열로 두면 안 된다 — 그건 "물어봤더니 조사 대상이 아니었다"는 **다른 답**이라
  //    카드가 서고, 그러면 카드 수를 세는 시험(L)이 이유 없이 달라진다.
  if (rents === undefined) {
    await mockMissingFunction(page, RENT_STATS_PATTERN);
  } else {
    await mockJson(page, RENT_STATS_PATTERN, rents);
  }
  // 임대 8분기 흐름도 기본이 **함수가 없는 상태**다(위 상수 주석 참조). 스펙 CI 만 덮어쓴다.
  await mockMissingFunction(page, RENT_HISTORY_PATTERN);
  // 상권 개업·폐업도 기본이 **함수가 없는 상태**다(위 상수 주석 참조). 스펙 AI 만 덮어쓴다.
  await mockMissingFunction(page, OPEN_CLOSE_PATTERN);
  // 대전 동네 폐업도 기본이 **함수가 없는 상태**다(위 상수 주석 참조). 스펙 CM 만 덮어쓴다.
  await mockMissingFunction(page, DAEJEON_CLOSURE_PATTERN);
  // 업종별 추정매출 · 상권 인구도 기본이 **함수가 없는 상태**다(위 상수 주석 참조). 스펙 CN·CO·AM 만 덮어쓴다.
  await mockMissingFunction(page, SALES_PATTERN);
  await mockMissingFunction(page, POP_PATTERN);
  // 호실 구성표 둘도 기본이 **함수가 없는 상태**다(위 상수 주석 참조). 호실을 보는 스펙은
  // 이 뒤에 자기 응답을 한 번 더 등록한다(나중에 등록한 것이 먼저 잡힌다).
  await mockMissingFunction(page, UNIT_SUMMARY_PATTERN);
  await mockMissingFunction(page, FLOOR_UNITS_PATTERN);
  // 개별공시지가 한 줄도 기본이 **함수가 없는 상태**다(위 상수 주석 참조). 스펙 AP 만 덮어쓴다.
  await mockMissingFunction(page, LAND_PRICE_PATTERN);
  // 층 목록 업종 띠도 기본이 **함수가 없는 상태**다(위 상수 주석 참조). 스펙 CG·AF 만 덮어쓴다.
  await mockMissingFunction(page, FLOOR_INDUSTRY_PATTERN);
}

/**
 * 아직 라이브에 없는 서버 함수를 흉내 낸다 — PostgREST 가 실제로 내는 404/PGRST202.
 *
 * 빈 배열이나 200 으로 답하면 "적용 전 라이브"가 아니라 "자료가 없는 라이브"를 흉내 내게
 * 되는데, 그 둘은 화면이 갈라 대해야 하는 서로 다른 상태다.
 */
async function mockMissingFunction(page: Page, pattern: string) {
  await page.route(pattern, async (route) => {
    if (route.request().method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: CORS_HEADERS });
      return;
    }
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      headers: CORS_HEADERS,
      body: JSON.stringify({ code: 'PGRST202', message: 'function does not exist' }),
    });
  });
}

/** 구 목록(RegionPicker가 마운트 시 부르는 것)을 가로챈다. 기본값은 강남구 하나. */
async function mockOpenSigungu(
  page: Page,
  rows: unknown[] = [
    { sido_code: '11', sido_nm: '서울', sigungu_code: '11680', sigungu_nm: '강남구', building_cnt: 14223 },
  ],
) {
  await mockJson(page, SIGUNGU_PATTERN, rows);
  /*
    검색을 누르면 가게 이름 질의가 건물 질의와 **나란히** 나간다(결정 0028) — 안 막으면
    그 요청이 실존하지 않는 도메인으로 나가 테스트가 DNS 에 좌우된다.

    기본값은 **빈 배열**이라 구역이 안 선다 — 기존 검색 스펙들이 보던 화면 그대로다.
    가게 결과를 보고 싶은 시험은 이 뒤에 자기 응답을 한 번 더 등록한다(나중에 등록한 것이
    먼저 잡힌다).
    ⓘ 여기(구 목록 옆)에 두는 이유: 검색하는 시험은 **예외 없이** 먼저 구를 골라야 하므로
      이 함수가 곧 "검색을 하는 시험 전부"와 같은 자리다.
  */
  await mockJson(page, SEARCH_STORES_PATTERN, []);
  /*
    구를 고르는 순간 입구 카드(LH 공고)가 함께 묻는다 — 안 막으면 그 요청이 실존하지
    않는 도메인으로 나가 테스트가 DNS 에 좌우된다.

    기본값은 **함수가 없는 상태**(404/PGRST202)다. 마이그레이션 적용 전 라이브가 바로 그
    상태이고, 그때 카드가 조용히 사라지는지가 테스트 X 의 관심사다. 공고를 보고 싶은
    테스트는 이 뒤에 자기 응답을 한 번 더 등록한다(나중에 등록한 것이 먼저 잡힌다).
  */
  await mockMissingFunction(page, LH_NOTICE_PATTERN);
  /*
    화면 아래 신선도 표도 여기서 함께 막는다 — 푸터는 구를 고르기 전부터 서 있어서
    이 요청은 **모든 시험**에서 첫 그림과 함께 나간다.

    기본값은 LH 와 같은 이유로 **함수가 없는 상태**다. 표를 보고 싶은 시험은 이 뒤에
    자기 응답을 한 번 더 등록한다(나중에 등록한 것이 먼저 잡힌다).
  */
  await mockMissingFunction(page, DATA_FRESHNESS_PATTERN);
  /*
    동네 매매 단가 흐름 카드도 구를 고르는 순간 함께 묻는다 — 같은 이유로 막는다.
    기본값이 **함수가 없는 상태**인 것도 같다(마이그레이션 적용 전 라이브). 흐름을 보고
    싶은 시험은 이 뒤에 자기 응답을 한 번 더 등록한다.
  */
  await mockMissingFunction(page, TX_YEARLY_PATTERN);
}

/** 시도 칩을 눌러 구 목록을 펼치고, 그 안의 구 칩을 눌러 고른다. */
async function pickGu(page: Page, sidoName: string, guName: string) {
  // 휴대폰 지도 가득(결정 0039 W4b) — 지역 고르개는 위 띠(「서울 강남구 ▾」)를 눌러야 펼쳐진다.
  const strip = page.locator('.rstrip__btn');
  if ((await strip.count()) > 0 && (await strip.getAttribute('aria-expanded')) === 'false') await strip.click();
  // PC 두 칸(결정 0039 W5 보완 D2) — 구를 고른 뒤엔 칩 상자가 「서울 강남구 · 바꾸기」 한 줄로 접혀 있다 → 「바꾸기」로 펼친다.
  //   펼친 시도는 그대로라 같은 시도의 구는 시도 칩을 다시 누르지 않는다(누르면 시도가 접힌다).
  const fold = page.locator('.regionfold__btn');
  if ((await fold.count()) > 0 && (await fold.getAttribute('aria-expanded')) === 'false') {
    await fold.click();
    const gu = page.getByRole('button', { name: guName });
    if (await gu.first().isVisible()) {
      await gu.click();
      return;
    }
  }
  await page.getByRole('button', { name: new RegExp(`^${sidoName}$`) }).click();
  await page.getByRole('button', { name: guName }).click();
}

/**
 * 접힌 카드를 펼친다(로드맵 Wave 2 『한 장 요약 접힘 틀』).
 *
 * 첫 화면에 펼쳐 두는 카드는 넷뿐이라 『층별 공표값 나란히』 같은 카드는 접힌 채로 시작한다 —
 * 그 안의 값·근거를 보려면 한 번 눌러야 한다. 이미 펼쳐져 있으면 아무 일도 안 한다.
 */
async function openCard(page: Page, title: RegExp) {
  const toggle = page.getByRole('button', { name: title });
  if ((await toggle.getAttribute('aria-expanded')) === 'false') await toggle.click();
}

async function search(page: Page, text: string) {
  await page.getByLabel('건물명 또는 주소').fill(text);
  // 이름 그대로(exact) — PC 두 칸 「← 목록으로(테헤란로 검색 1곳)」 단추도 '검색' 을 품는다(👤 2026-10-22 방법 나 R3 글).
  await page.getByRole('button', { name: '검색', exact: true }).click();
}

/**
 * 건물을 연 동안 한 줄 바로 접힌 입구(S1)를 바의 단추로 펼친다. 단추 이름은 낭독기가 읽는 이름이다 — 기호(←·▾)는
 * `aria-hidden` 이라 빠진다(보이는 글자는 '← 다른 건물 찾기'·'나는 창업자 ▾'). 접힌 동안 역할 줄·지역 고르개·검색창은 숨고
 * 지도는 아예 안 그려지므로, 건물을 연 뒤 그것들을 만지는 시험은 먼저 이것을 부른다.
 */
async function unfoldEntry(page: Page, button: string | RegExp = '다른 건물 찾기') {
  // 휴대폰(결정 0039 W4a)은 바 대신 아래 탭 — 바의 단추 이름을 그 탭으로 옮겨 누른다(찾기 · 지도 · 더보기).
  // 중개사는 지도 탭이 없고 지도가 찾기 탭 안이다.
  if (await isPhoneTabs(page)) {
    const name = String(button);
    if (name.includes('상권 지도')) {
      await gotoTab(page, (await tabButton(page, '지도').count()) > 0 ? '지도' : '찾기');
    } else if (name.includes('나는')) {
      await gotoTab(page, '더보기');
    } else {
      await gotoTab(page, '찾기');
    }
    return;
  }
  // PC 두 칸(결정 0039 W5 · 1024px 이상 — chromium 판 1280)은 바가 없고 왼쪽 칸이 늘 서 있다 — 띠로 접혀 있으면 펼치기만.
  if (await isTwoCols(page)) {
    const rail = page.getByRole('button', { name: '왼쪽 칸 펼치기' });
    if ((await rail.count()) > 0) await rail.click();
    return;
  }
  await page.locator('.entrybar').getByRole('button', { name: button }).click();
}

/**
 * PC 두 칸(결정 0039 W5)인가 — 1024px 이상(chromium 판 1280×720)에서만 `.app--wide` 가 붙는다.
 * ⓘ 화면이 그려지기 전(새로고침 직후)에도 맞게 창 폭으로 가른다 — 이름표가 실제로 붙는지는 BV 가 본다.
 */
async function isTwoCols(page: Page): Promise<boolean> {
  return (page.viewportSize()?.width ?? 0) >= 1024;
}

/** 휴대폰 아래 탭(결정 0039 W4a)이 서 있나 — mobile 판(412px)에서만 선다. */
async function isPhoneTabs(page: Page): Promise<boolean> {
  return (await page.locator('nav.tabbar').count()) > 0;
}

function tabButton(page: Page, name: string) {
  return page.getByRole('navigation', { name: '화면 고르기' }).getByRole('button', { name, exact: true });
}

/** 휴대폰이면 그 탭을 누른다 · 넓은 화면은 아무 일도 안 한다(탭이 없고 그 덩어리가 이미 화면에 있다). */
async function gotoTab(page: Page, name: '찾기' | '지도' | '건물' | '뽑은 건물' | '더보기') {
  if (!(await isPhoneTabs(page))) return;
  await tabButton(page, name).click();
  await expect(tabButton(page, name)).toHaveAttribute('aria-current', 'page');
}

/**
 * 건물을 고른 뒤 입구 카드(LH·단가 흐름)가 물러나는가.
 * 넓은 화면 = 카드가 DOM 에서 빠진다(지금 그대로). 휴대폰(W4a 검사 🟠 F2) = 건물 탭에선 숨고 · 찾기 탭으로 가면 다시 서고 ·
 * 건물을 연 채 종이에서는 빠진다(종이 = 건물 한 장). 끝나면 건물 탭으로 돌려 둔다.
 */
async function expectEntryCardRetreats(page: Page, sel: string) {
  const card = page.locator(sel);
  if (!(await isPhoneTabs(page))) {
    await expect(card).toHaveCount(0);
    return;
  }
  await expect(card).toHaveCount(1);
  await expect(card).toBeHidden();
  await gotoTab(page, '찾기');
  await expect(card).toBeVisible();
  await page.emulateMedia({ media: 'print' });
  await expect(card).toBeHidden();
  await expect(page.locator('section.stack .stack__head')).toBeVisible();
  await page.emulateMedia({ media: null });
  await gotoTab(page, '건물');
}

/*
  '물어봤음' 기본값(결정 0039 §4-7 · W3). 이 기기 저장값이 없으면 입구 맨 위에 역할 고르기 큰 카드가 서고 작은 역할 단추 줄은
  숨는다 — 이 파일의 시험은 그 카드가 나오기 전 화면(역할 없음)을 전제로 쓰였으므로, 페이지가 열릴 때마다 **열쇠에 값이 없을
  때만** `둘러보기`(= 역할 없음)를 넣는다. 그래서 시험이 따로 넣는 역할(AQ·BF 의 addInitScript — 이 스크립트 뒤에 돈다)과
  시험 안에서 고른 값(새로고침 뒤에도)이 이긴다.
  ⓘ 큰 카드 전용 시험은 태그 `@first-visit` 를 달아 이 기본값을 건너뛴다(빈 저장소 = 처음 온 사람).
*/
test.beforeEach(async ({ page }, testInfo) => {
  if (testInfo.tags.includes('@first-visit')) return;
  await page.addInitScript(() => {
    // ⚠️ 이 파일의 타입 검사는 브라우저 타입(DOM)을 안 켠다 — 전역을 좁은 모양으로 꺼내 쓴다(시험 AQ 와 같은 사정).
    const w = globalThis as unknown as {
      localStorage: { getItem(k: string): string | null; setItem(k: string, v: string): void };
    };
    if (w.localStorage.getItem('sangga.viewerRole') === null) w.localStorage.setItem('sangga.viewerRole', '둘러보기');
  });
});

test.describe('층별 스택뷰 — 검색부터 렌더까지', () => {
  test('A. 검색 → 결과 클릭 → 층 스택 렌더', async ({ page }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    // 층별 공표값 카드(결정 0041)까지 한 벌로 태운다 — "섹션이 통째로 안 뜨는 회귀"를 잡는 자리다.
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()]);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');

    const hitBtn = page.getByRole('button', { name: /테스트빌딩/ });
    await expect(hitBtn).toBeVisible();
    await hitBtn.click();

    const stack = page.locator('section.stack');
    await expect(stack.getByRole('heading', { name: '테스트빌딩' })).toBeVisible();
    await expect(stack.getByText('서울 강남구 테헤란로 1')).toBeVisible();
    // 속한 상권 한 줄(2026-08-14). 이 줄은 별도 RPC 응답에 달려 있어 다른 조각이 다
    // 정상이어도 혼자 조용히 빠질 수 있다 — 그래서 여기서 눈으로 확인한다.
    await expect(stack.locator('.card--district .card__title')).toHaveText('속한 상권');
    await expect(stack.getByText(/역삼역\(발달상권\)/)).toBeVisible();
    // 출처표시는 공공누리 1유형 의무다 — 상권 이름이 보이는데 출처만 빠지는 것도 결함이다.
    await expect(stack.getByText(/출처: 서울특별시 상권분석서비스/)).toBeVisible();
    // 층별 공표값 카드(결정 0041)도 같은 종류의 위험을 진다(곁 자료 셋에 달려 있다).
    // ⚠️ 이 카드는 첫 화면에서 **접혀 있다**(펼침 상한 4장) — 카드 자체는 보이지만
    //    값·근거는 펼쳐야 나온다. 기준시가 함수가 없어도(이 목업) 구 상가 단가 칸 하나로 선다(E2).
    await expect(stack.locator('section.gap')).toBeVisible();
    await openCard(page, /층별 공표값 나란히/);
    await expect(stack.getByText(/서로 나누거나 비율을 계산하지 않았습니다/)).toBeVisible();
    // 내린 참고 매매 시세 카드는 없다(결정 0041 E1).
    await expect(stack).not.toContainText('참고 매매 시세');
    // 업종 분포(결정 0014)는 **서버에 함수가 아직 없는 상태**로 흉내 냈다(mockFloorStack).
    // 그때 이 섹션은 아무 말도 없이 사라져야 한다 — "업종 없음" 같은 문구를 남기면
    // 모르는 것을 없는 것이라 말하게 되고, 터지면 층 스택 전체가 같이 죽는다.
    await expect(stack.locator('section.mix')).toHaveCount(0);
    // 층별 규모를 보여주는 막대. 글자가 아니라 **그림**이라 아무 단언에도 안 걸려 있었고,
    // 그래서 2026-08-22 에 좁은 폭에서만 `display: none` 으로 숨겼을 때 E2E 가 전부
    // 초록이었다. 이 줄은 모바일 프로젝트에서 그 회귀를 잡으라고 있는 자리다.
    await expect(stack.locator('.floor__bar').first()).toBeVisible();
    // 바탕(track)만 보면 안 된다 — 크기를 말하는 건 안의 색칠(fill)이다. fill 만
    // 숨기는 회귀(width:0·display:none)는 위 줄이 초록인 채 정보만 사라진다.
    await expect(stack.locator('.floor__fill').first()).toBeVisible();
    await expect(stack.getByRole('heading', { name: '테스트빌딩' })).toBeVisible();
  });

  test('B. 새 검색을 제출하면 이전 층 스택이 즉시 사라진다', { tag: '@onecol' }, async ({ page }) => {
    // App.tsx onSearchStart 주석에 박제된 실제 라이브 회귀 재현: 두 번째 검색 응답을
    // 일부러 늦춰서, 응답을 기다리지 않고 선택이 먼저 비워지는지를 본다.
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack')).toBeVisible();

    await page.unroute(SEARCH_PATTERN);
    // 1초 늦춘다 — 답을 기다리는 동안의 화면(두 칸 「찾는 중…」 · 보완 3)을 붙잡을 틈.
    await mockJson(page, SEARCH_PATTERN, [searchHit({ bld_id: 'other', bld_nm: '다른빌딩' })], 1000);

    // 건물을 열면 입구가 한 줄로 접힌다(S1) — 바의 「다른 건물 찾기」로 검색창을 펼친다.
    await unfoldEntry(page);
    await search(page, '다른동');

    if (await isPhoneTabs(page)) {
      // 휴대폰 탭 꼴(👤 확정 결정 0039 §7-1)은 검색해도 보던 건물을 남긴다 — 찾기 탭에선 안 보이고 「건물」 탭에 그대로.
      await expect(page.locator('section.stack')).toHaveCount(1);
      await expect(page.locator('section.stack')).toBeHidden();
      await gotoTab(page, '건물');
      await expect(page.locator('section.stack').getByRole('heading', { name: '테스트빌딩' })).toBeVisible();
      return;
    }
    if (await isTwoCols(page)) {
      // PC 두 칸은 건물을 쥐고 있되(👤 2026-10-21 W5 보완 D1) 오른쪽이 목록으로 바뀐다(👤 2026-10-22 방법 나 R2) — 옛 건물은 화면에서
      //   숨고(DOM 은 그대로) 목록 위 「← 보던 건물(이름)로」 · 늦게 오는 응답을 기다리는 동안에도 옛 건물이 보이지 않는다 · 빈 오른쪽 안내 줄 0.
      await expect(page.locator('section.stack')).toHaveCount(1);
      await expect(page.locator('section.stack')).toBeHidden();
      // 답이 오기 전 — 오른쪽 목록 자리에 「찾는 중…」 한 줄(13px · 낭독 자리 안 · 보완 3).
      const loadingLine = page.locator('section.rlist .msg--live[role="status"] .rlist__loading');
      await expect(loadingLine).toHaveText('찾는 중…');
      await expect(loadingLine).toHaveCSS('font-size', '13px');
      await expect(page.getByRole('button', { name: /다른빌딩/ })).toBeVisible();
      await expect(loadingLine).toHaveCount(0);
      await expect(page.locator('section.stack')).toBeHidden();
      await expect(page.getByRole('button', { name: '보던 건물(테스트빌딩)로' })).toBeVisible();
      await expect(page.locator('.rpane-empty')).toHaveCount(0);
      return;
    }
    await expect(page.locator('section.stack')).toHaveCount(0);
    await expect(page.getByText('위에서 건물을 검색해 선택해 주세요.')).toBeVisible();
  });

  test('C. 검색 결과 0건일 때도 이전 층 스택이 사라진다', { tag: '@onecol' }, async ({ page }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack')).toBeVisible();

    await page.unroute(SEARCH_PATTERN);
    await mockJson(page, SEARCH_PATTERN, []);
    await mockJson(page, SCOPE_PATTERN, [{ too_broad: false, match_cnt: 0 }]);

    await unfoldEntry(page); // 건물을 열면 입구가 접힌다(S1)
    await search(page, '없는건물');

    // ⚠️ 구 단위 검색으로 바뀐 뒤 문구도 바뀌었다 — "지금 보실 수 있는 지역은 …"이 아니라
    //    **고른 구 안에서** 못 찾았다고 말한다(2026-08-13 2차 검증에서 정리).
    // ⚠️ '강남구'는 지역 칩에도 있으므로 **문구 안에서** 찾아야 한다(그냥 getByText 는 모호).
    await expect(page.getByText(/강남구에서 찾지 못했습니다/)).toBeVisible();
    // 휴대폰 탭 꼴은 보던 건물을 남긴다(§7-1) — 찾기 탭에선 숨어 있다.
    if (await isPhoneTabs(page)) await expect(page.locator('section.stack')).toBeHidden();
    // PC 두 칸(W5 보완 D1)도 보던 건물을 쥐고 있다 — 오른쪽은 「못 찾음」 목록이라 화면에선 숨고 「← 보던 건물로」(👤 10-22 방법 나 R2).
    else if (await isTwoCols(page)) {
      await expect(page.locator('section.stack')).toBeHidden();
      await expect(page.locator('section.rlist').getByText(/강남구에서 찾지 못했습니다/)).toBeVisible();
      await expect(page.getByRole('button', { name: '보던 건물(테스트빌딩)로' })).toBeVisible();
    }
    else await expect(page.locator('section.stack')).toHaveCount(0);
  });

  // ── 너무 넓은 검색 안내 (2026-08-13 안내창 → 2026-09-10 건물 쪽은 한 줄) ──────────────────────────────────
  // 이 서비스는 건물 한 채·필지 한 곳을 놓고 상권을 분석한다. '서울'·'동'처럼 어디를
  // 볼지 정해지지 않는 검색은 결과 25개를 억지로 보여줘도 쓸모가 없고, 서버에서는
  // 20만 건과 맞아 3초를 넘겨 500이 됐다(라이브 실측). 그래서 안내로 바꿨다.

  test('D. 한 글자로 검색하면 서버를 부르지 않고 바로 안내창이 뜬다', async ({ page }) => {
    let searchCalls = 0;
    await mockOpenSigungu(page);
    await page.route(SEARCH_PATTERN, async (route) => {
      searchCalls += 1;
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
    });
    await mockFloorStack(page);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '동');

    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByText('한 글자로는 찾을 수 없어요')).toBeVisible();
    expect(searchCalls).toBe(0); // 물어볼 필요가 없는 질문은 아예 안 보낸다
  });

  test('E. 너무 넓은 검색이면 걸린 곳 수와 무엇을 넣을지 알려준다 — 그 아래 가게 구역은 보이고 눌린다', async ({ page }) => {
    await mockOpenSigungu(page);
    // ⚠️ 가게 답도 함께 준다 — 이 시험의 본론은 "안내가 한 줄이라 **그 밑의 가게 구역이 가려지지
    //    않는다**"인데, 가게 답이 없으면 구역 자체가 안 서서 무엇도 증명하지 못한다(2026-09-10
    //    사후 검증에서 발견 — jsdom 은 겹침을 못 보므로 이 사실을 볼 수 있는 곳은 여기뿐이다).
    await mockJson(page, SEARCH_STORES_PATTERN, [storeHit({ total_parcel_cnt: 3, total_store_cnt: 12 })]);
    await mockJson(page, SEARCH_PATTERN, []);
    await mockJson(page, SCOPE_PATTERN, [{ too_broad: true, match_cnt: 163487 }]);
    await mockFloorStack(page);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '서울');

    /*
      ⛔ 이 경우는 **안내창(모달)이 아니라 건물 결과 자리의 한 줄**이다 — 덮개가 화면을 통째로
         덮으면 건물이 0건이어도 멀쩡히 서 있는 가게 이름 구역을 가리고 클릭까지 삼킨다
         (결정 0028 §백로그 🟡-10). 한 글자·구 미선택(D·F)은 그대로 안내창이다.
    */
    await expect(page.getByText(/너무 넓은 검색/)).toBeVisible();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByText('163,487곳')).toBeVisible();
    // ⚠️ 예시 '역삼동 823-4'는 아래 가게 줄의 지번에도 있으므로 **안내 한 줄 안**에서만 찾는다
    //    (페이지 전체 getByText 는 strict mode 로 두 요소에 걸려 실패한다).
    await expect(page.getByText(/너무 넓은 검색/)).toContainText('역삼동 823-4');
    /*
      ⚠️ 여기서 여태 센 문구는 '결과가 없습니다'였는데 **그 말은 이 앱에 아예 없다** — 무엇을
         세도 0이라 늘 초록인 빈 단언이었다. 진짜 문구는 '찾지 못했습니다'다(C 시험 참조).
    */
    await expect(page.getByText(/찾지 못했습니다/)).toHaveCount(0);
    // 본론 — 안내 한 줄 **아래 가게 구역이 서 있고, 눌린다**. Playwright 의 click 은 다른 요소에
    // 가려져 있으면 실패하므로(actionability) 이 한 줄이 곧 "덮개가 없다"는 단언이다.
    const stores = page.getByRole('region', { name: '가게 이름으로 찾은 땅' });
    await expect(stores).toBeVisible();
    await expect(stores).toContainText('이 이름의 가게가 있는 땅 3곳 · 가게 12곳');
    await stores.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack').getByRole('heading', { name: '테스트빌딩' })).toBeVisible();
  });

  // ── 구를 고른 뒤에만 검색된다 (2026-08-13e) ──────────────────────────────
  // 같은 건물 이름이 여러 구에 겹친다(이름 33,851종 중 2,443종이 2개 이상 구에 존재).
  // 그래서 검색은 이제 "구를 고른 뒤 그 안에서만" 한다 — 사장님 결정.

  test('F. 구를 고르지 않으면 검색을 막고, 구를 고르면 그 구에서 찾은 결과를 보여준다', async ({ page }) => {
    let searchCalls = 0;
    await mockOpenSigungu(page);
    await page.route(SEARCH_PATTERN, async (route) => {
      searchCalls += 1;
      const url = route.request().postData() ?? '';
      // 서버에 실제로 구 코드가 실려 가는지도 함께 확인한다.
      expect(url).toContain('"sigungu":"11680"');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([searchHit()]),
      });
    });
    await mockFloorStack(page);

    await page.goto('/');

    // 구를 고르기 전에는 검색을 눌러도 서버를 안 부르고 안내만 뜬다.
    await search(page, '테헤란로');
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByText('먼저 지역을 골라 주세요')).toBeVisible();
    expect(searchCalls).toBe(0);
    await page.getByRole('button', { name: '닫기' }).click();

    // 구를 고르면 그제서야 검색이 되고, 어느 구에서 찾았는지가 결과에 드러난다.
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');

    await expect(page.getByRole('button', { name: /테스트빌딩/ })).toBeVisible();
    await expect(page.getByText(/강남구에서/)).toBeVisible();
    expect(searchCalls).toBe(1);
  });

  // ── 실거래 사실 표시 (Stage A · 결정 0012) ───────────────────────────────
  // 이 섹션은 별도 RPC 둘에 달려 있어, 다른 조각이 다 정상이어도 혼자 조용히 빠질 수 있다
  // (상권 줄과 같은 종류의 위험). 그래서 여기서 눈으로 확인한다.

  test('G. 층 스택에 실거래 이력·구 단가·층 뱃지가 함께 뜬다', async ({ page }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [parcelTx()]);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const stack = page.locator('section.stack');
    await expect(stack.getByText('실거래 기록')).toBeVisible();
    // ① 이 땅의 이력 — 금액·단가를 사람이 읽는 단위로.
    await expect(stack.getByText(/이 땅에서 신고된 거래 1건/)).toBeVisible();
    await expect(stack.getByText('3억 2,000만')).toBeVisible();
    // 층 스택의 그 층에도 건수 뱃지가 붙는다(픽스처의 층·거래 층이 모두 1층).
    await expect(stack.locator('.floor__tx')).toHaveText('거래 1건');
    // ② 구 단가 — 표본이 충분한 층대만 수치가 나오고, 모자란 층대는 그렇다고 말한다.
    await expect(stack.getByText(/강남구 층대별 거래 단가 \(상가 거래 기준\)/)).toBeVisible();
    await expect(stack.getByText(/중앙값 ㎡당 2,250만/)).toBeVisible();
    await expect(stack.getByText('표본 부족').first()).toBeVisible();
    // 출처표시 의무 + 절대 규칙 3(근거 레벨·표본 수 병기).
    await expect(stack.getByText(/국토교통부 상업업무용 부동산 매매 실거래가/)).toBeVisible();
    // 같은 배지가 층별 공표값 카드(물결 1-C2) 칸 머리에도 선다 — 실거래 카드 안으로 좁힌다.
    await expect(stack.locator('section.tx').getByText(/A등급 · 실거래 집계/)).toBeVisible();
    // 절대 규칙 2 — 금칙어 5종은 화면 어디에도 없다.
    // ⚠️ '시세'는 다른 카드(층별 공표값의 「시세가 아닙니다」 등)가 정당하게 쓴다.
    //    그래서 '시세' 금지는 화면 전체가 아니라 **Stage A 블록 안**으로 좁힌다 —
    //    "사실을 말하는 블록은 그 말조차 쓰지 않는다"는 원래 뜻은 그대로 지킨다.
    await expect(stack.locator('section.tx')).not.toContainText('시세');
    await expect(stack).not.toContainText('적정가');
    await expect(stack).not.toContainText('평가액');
    await expect(stack).not.toContainText('감정가');
    await expect(stack).not.toContainText('가치평가');
  });

  // 지분 거래(2026-10-08a · 물결 0-2b) — 목록에서 지우지 않고 '지분' 꼬리표 + 목록 아래 설명 한 줄.
  // 좁은 화면(412px)에서 줄이 접혀도 꼬리표가 남는지까지 두 화면에서 본다.
  test('AL. 지분 거래 줄에 "지분" 꼬리표가 붙고 목록 아래 설명이 선다', async ({ page }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [
      parcelTx({ is_share: true, price_won: 50_000_000, unit_price: 593_000 }),
      parcelTx(),
    ]);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const list = page.locator('section.stack .tx__list');
    await expect(list.locator('li')).toHaveCount(2);
    // 지분 거래도 그대로 보인다 — 금액과 꼬리표가 같은 줄에.
    const shareRow = list.locator('li').filter({ hasText: '5,000만' });
    await expect(shareRow.locator('.tx__share')).toHaveText('지분');
    await expect(shareRow.locator('.tx__share')).toBeVisible();
    // 일반 거래 줄에는 꼬리표가 없다.
    await expect(list.locator('li').filter({ hasText: '3억 2,000만' }).locator('.tx__share')).toHaveCount(0);
    await expect(page.locator('section.stack .tx__share-note')).toHaveText(
      '지분 = 건물 일부 몫만 사고판 거래라 ㎡당 값이 낮게 나옵니다 — 층대별 단가 계산에서는 뺍니다.',
    );
    // G 의 규칙(Stage A 블록 안에는 '시세'라는 말조차 없다)을 설명 줄이 선 상태에서도 본다 —
    // G 는 지분 없는 거래뿐이라 이 줄이 그려지는 경우를 못 본다.
    await expect(page.locator('section.stack section.tx')).not.toContainText('시세');
  });

  test('J. 구 칩 건물 수 · 도로접면 · 업종 요약 · 건물 스펙 4칸이 함께 뜬다', async ({ page }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [
      floorRow({
        floor_no: 2,
        road_contact: '광대로한면',
        // 건물 스펙 4칸(로드맵 Wave 2 PR-B). 주차만 0 으로 둔다 — 대장이 미기재를 0 으로
        // 주는 실제 모양이다(롯데월드타워가 그렇게 들어와 있다). 값과 "미상"이 한 화면에
        // 같이 있어야 "둘을 갈라 적는가"를 볼 수 있다.
        parking_cnt: 0,
        stores: [
          { name: null, cat: '한식' },
          { name: null, cat: '커피' },
        ],
      }),
      floorRow({ road_contact: '광대로한면', stores: [{ name: null, cat: '한식' }] }),
    ]);

    await page.goto('/');

    // ① 구 칩에 그 구의 건물 수가 함께 적힌다(mockOpenSigungu 기본값 14,223동).
    await page.getByRole('button', { name: /^서울$/ }).click();
    const guChip = page.getByRole('button', { name: /^강남구/ });
    await expect(guChip).toContainText('14,223동');
    // 칩의 숫자 칸에도 '시세'가 못 들어온다(예: "시세 등급" 배지 같은 훗날의 유혹).
    await expect(page.locator('.region__gu-cnt').first()).not.toContainText('시세');
    await guChip.click();

    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const stack = page.locator('section.stack');
    // ② 도로접면은 토지특성 **원문 그대로** 나온다(재해석 금지 — 시세 사다리의 등급과
    //    화면이 다른 말을 하기 시작하면 같은 땅에 기준이 둘 생긴다).
    await expect(stack.getByText('도로접면')).toBeVisible();
    await expect(stack.getByText('광대로한면')).toBeVisible();
    // ②-b 건물 스펙 4칸(로드맵 Wave 2 PR-B). 값이 오면 그대로 적고, 0(=대장 미기재)은
    //      값이 아니라 "미상"이라고 적는다 — 0 을 값으로 적으면 없는 사실이 생긴다.
    //      ⚠️ 칸끼리 안 섞이게 **그 칸(div)** 으로 좁혀 본다.
    const facts = stack.locator('.stack__facts div');
    await expect(facts.filter({ hasText: '연면적' })).toContainText('1,234.5㎡ (373평)');
    await expect(facts.filter({ hasText: '용적률' })).toContainText('350.5%');
    await expect(facts.filter({ hasText: '건폐율' })).toContainText('59.9%');
    await expect(facts.filter({ hasText: '주차' })).toContainText('미상');
    // ③ 업종 요약은 층을 안 펼쳐도 보이고, 층 여럿을 합쳐 센다(2층 한식 + 1층 한식 = 2곳).
    await expect(stack.locator('.stack__biz')).toContainText('한식 2곳');
    await expect(stack.locator('.stack__biz')).toContainText('커피 1곳');
    // 새로 늘어난 문구에도 금칙어(절대 규칙 2)는 없다. '시세'는 층별 공표값 카드에
    // 정당하게 있으므로 stack 통째가 아니라 **새 문구의 스코프**(.stack__biz)로 좁혀 단언한다
    // (같은 방식의 선례: 실거래 섹션의 not.toContainText('시세')).
    await expect(stack).not.toContainText('적정가');
    await expect(stack).not.toContainText('평가액');
    await expect(stack).not.toContainText('감정가');
    await expect(stack).not.toContainText('가치평가');
    await expect(stack.locator('.stack__biz')).not.toContainText('시세');
  });

  // ── 둘레의 업종 분포 (결정 0014) ─────────────────────────────────────────
  // A 는 **함수가 없는 라이브**에서 이 섹션이 조용히 사라지는지를 본다. 그 반대편,
  // 곧 "서버가 제대로 답했을 때 실제로 그려지는가"는 여태 아무 데서도 안 봤다
  // (PR #77 의 기록 공백). 두 상태를 다 봐야 "언제나 안 뜨는" 회귀를 잡을 수 있다.

  test('K. 서버가 답하면 둘레의 업종 분포가 상권·반경 두 묶음으로 그려진다', async ({ page }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], undefined, industryMix());

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const mix = page.locator('section.mix');
    // ⚠️ 카드 머리에는 제목 옆에 역할 태그가 붙는다 — 이름이 딱 맞아떨어지지 않으므로
    //    정확히 같은지가 아니라 **들어 있는지**로 본다.
    await expect(mix.getByRole('heading', { name: /둘레의 업종 분포/ })).toBeVisible();
    // 이 건물 점포와 세는 대상이 다르다는 말이 먼저 나온다(층 목록의 업종 요약과 혼동 금지).
    await expect(mix.getByText(/이 건물만이 아니라 이 땅 둘레의 가게들입니다/)).toBeVisible();

    // ① 상권 묶음 — 이름·종류·총수. ② 반경 묶음 — 길이는 서버가 준 값으로 적는다.
    await expect(mix.getByRole('heading', { name: /강남역\(발달상권\) 안/ })).toBeVisible();
    // 반경 묶음은 총수까지 함께 본다 — 제목만 보면 상권 묶음의 숫자를 그대로 베껴
    // 그리는 회귀(두 스코프가 같은 값을 말하는 상태)를 못 잡는다.
    await expect(mix.getByRole('heading', { name: /반경 500m 안 200곳/ })).toBeVisible();
    // 대분류 행: 이름·개수·몫이 한 줄에 함께 나온다(총수 없이 %만 있으면 못 읽는다).
    // ① 상권 묶음(100곳 중 음식 60곳)
    const districtBar = mix.locator('.mix__block').first().locator('.mix__bars li').first();
    await expect(districtBar.locator('.mix__cat')).toHaveText('음식');
    await expect(districtBar.locator('.mix__n')).toHaveText('60곳');
    await expect(districtBar.locator('.mix__pct')).toHaveText('60.0%');
    // ② 반경 묶음(200곳 중 음식 150곳 = 75.0%) — 스코프마다 제 값으로 센다.
    const radiusBar = mix.locator('.mix__block').nth(1).locator('.mix__bars li').first();
    await expect(radiusBar.locator('.mix__n')).toHaveText('150곳');
    await expect(radiusBar.locator('.mix__pct')).toHaveText('75.0%');
    // 대분류를 고를 수 있는 자리(중분류로 나뉘는 입구).
    await expect(mix.getByLabel('업종 골라보기')).toBeVisible();
    // 기준 분기·출처는 서버가 준 값이다 — 화면에 글자로 박으면 자료가 바뀌는 날 거짓말이 된다.
    await expect(mix.getByText(/2026년 2분기 기준/)).toBeVisible();
    await expect(mix.getByText(/소상공인시장진흥공단 상가\(상권\)정보/)).toBeVisible();
    // 절대 규칙 3 — 근거 등급을 함께 적는다. 이 섹션은 어림이 아니라 실측 집계다.
    await expect(mix.getByText(/A등급 · 실측 집계/)).toBeVisible();
    // ⛔ 이 섹션은 **개수만** 말한다. 값·시세가 새어 들어오면 성격이 통째로 바뀐다.
    await expect(mix).not.toContainText('시세');
    await expect(mix).not.toContainText('적정가');
    // 둘레의 인허가 함수는 여기서 **없는 상태**다(mockFloorStack 기본값) — 그 줄만 빠지고
    // 카드의 나머지는 위처럼 그대로 선다.
    await expect(mix.locator('.mix__permits')).toHaveCount(0);
  });

  // ── 한 장 요약 접힘 틀 (로드맵 Wave 2) ───────────────────────────────────
  // 첫 화면에 펼쳐 두는 카드는 **넷**뿐이고, 다섯 번째(층별 공표값 나란히 — 결정 0041 로 내린
  // 참고 매매 시세의 자리)는 접힌 채로 시작한다. 다만 접힘은 **숨김이 아니다** —
  // 접힌 카드도 제목과 핵심 한 줄은 그대로 보여야 한다. 이 배치는 CSS·상태가 얽혀 있어
  // 단위 시험만으로는 "화면에서 정말 그런가"를 못 본다.

  test('L. 카드 넷만 펼쳐져 있고, 접힌 카드는 눌러야 내용이 나온다', async ({ page }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(
      page,
      [parcelTx()],
      [floorRow({ floor_no: 2 }), floorRow()],
      industryMix(),
    );

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const stack = page.locator('section.stack');
    // 다섯 장 + 빈 카드 하나(가게 이력 — 결정 0036 결정 2 · 물결 1-B · 아무것도 안 불러서 목업이 없어도 선다).
    // ⓘ 서울 건물이라 추정매출·상권 인구는 제 카드인데, 함수가 기본(함수 없음)이라 카드째 숨는다(결정 0045 PR③ · CN·CO).
    // ⓘ 층별 공표값은 값 든 칸 하나면 선다(결정 0041 E2) — 이 목업은 구 상가 단가 1층 칸 하나로 선다.
    await expect(stack.locator('.card')).toHaveCount(6);
    await expect(stack.locator('section.card--empty')).toHaveCount(1);
    await expect(stack.locator('.card__toggle[aria-expanded="true"]')).toHaveCount(4);

    const gap = stack.locator('section.gap');
    // 접힌 채로도 제목과 핵심 한 줄은 읽힌다 — 본문(값)만 없다.
    await expect(gap.locator('.card__title')).toHaveText('층별 공표값 나란히 — 국세청 기준시가 · 구 상가 단가 · 부동산원 임대료');
    await expect(gap.locator('.card__summary')).toHaveText('국세청 기준시가 · 구 상가 단가 · 부동산원 임대료 — 층마다 나란히');
    // ⚠️ "DOM 에 없다"가 아니라 **"안 보인다"**를 본다. 접힌 본문은 자리에 남겨 둔다 —
    //    안 그러면 종이로 뽑을 때 이 카드가 통째로 빠진다(결정 0020, 시험 R·S).
    await expect(gap.locator('.card__body')).toBeHidden();

    // 누르면 그 자리에서 값·근거가 함께 나온다(절대 규칙 3 — 값과 근거는 한 몸이다).
    await openCard(page, /층별 공표값 나란히/);
    await expect(gap.locator('.gap__row[data-floor="1"] .gap__cell--tx .gap__val')).toHaveText('㎡당 2,250만');
    await expect(gap.locator('.gap__head--tx').getByText('A등급 · 실거래 집계', { exact: true })).toBeVisible();

    // 펼쳐진 카드도 접을 수 있다 — 접으면 본문만 사라지고 요약은 남는다.
    const floorsCard = stack.locator('.card--floors');
    await expect(floorsCard.locator('.floor')).toHaveCount(2);
    await floorsCard.locator('.card__toggle').click();
    await expect(floorsCard.locator('.card__body')).toBeHidden();
    await expect(floorsCard.locator('.card__summary')).toHaveText('층 2개 · 점포 4곳');
  });
});

test.describe('화면 아래 — 어디까지 믿을지와 한마디 남기는 자리', () => {
  /**
   * 왜 E2E 로도 보나 — 이 자리는 **화면에서 창고로 나가는 유일한 길**이다. 나머지는 전부
   * 읽기라 방향이 반대고, 그래서 여기만 실제 브라우저에서 요청이 나가는지 눈으로 확인해
   * 둘 값어치가 있다(그 요청이 안 나가면 사람은 "보냈다"고 믿고 우리는 아무것도 못 받는다).
   */
  test('M. 아래 안내와 "언제 것인가" 표가 보이고, 의견을 보내면 보던 지역이 함께 간다', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    // 신선도 표는 기본이 '함수 없음'이라(mockOpenSigungu) 여기서만 진짜 답을 덮어 등록한다.
    await mockJson(page, DATA_FRESHNESS_PATTERN, dataFreshness());

    // 실제로 나간 요청을 붙잡는다 — 인자 이름까지 눈으로 본다.
    const sent: Array<Record<string, unknown>> = [];
    await page.route(FEEDBACK_PATTERN, async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: CORS_HEADERS });
        return;
      }
      sent.push(route.request().postDataJSON() as Record<string, unknown>);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: CORS_HEADERS,
        // ⚠️ boolean 을 돌려주는 함수라 PostgREST 응답이 배열이 아니라 **스칼라 true** 다.
        //    배열로 흉내 내면 라이브와 모양이 달라져 "테스트만 통과하는" 가짜 초록이 된다.
        body: JSON.stringify(true),
      });
    });

    await page.goto('/');
    // 휴대폰(결정 0039 W4a)은 꼬리말이 「더보기」 탭 안이다.
    await gotoTab(page, '더보기');

    // 건물을 고르지 않아도 아래 안내는 늘 보인다 — 다 보고 난 사람이 찾는 자리다.
    const foot = page.locator('footer.foot');
    await expect(foot.getByText(/감정평가가 아니며/)).toBeVisible();
    await expect(foot.getByText(/"미상"/)).toBeVisible();

    // 넘기기 링크 구역(결정 0014 §5) — 안내 바로 뒤에 선다.
    await expect(foot.getByRole('heading', { name: '더 필요하면 여기서' })).toBeVisible();
    // ⛔ `rel` 이 이 자리의 유일한 안전장치다 — 없으면 새 창으로 열린 쪽이 우리 창을
    //    되돌려 다른 주소로 보낼 수 있다. 화면으로는 절대 안 보이는 종류라 여기서 본다.
    const outLink = foot.getByRole('link', { name: '네이버 부동산' });
    await expect(outLink).toHaveAttribute('target', '_blank');
    await expect(outLink).toHaveAttribute('rel', 'noopener noreferrer');
    // 안내는 **접힌 채로** 시작한다 — 나가는 문 앞을 설명으로 가로막지 않는다.
    await expect(foot.locator('.links__guide-body')).toBeHidden();
    // 형제 사이트 링크(2026-10-06) — 넘기기 구역과 따로 선 한 줄 구역, 링크는 두 개뿐이다.
    const family = foot.getByRole('navigation', { name: '함께 보면 좋은 사이트' });
    await expect(family).toBeVisible();
    await expect(family.getByRole('link')).toHaveCount(2);
    // "언제 것인가" 표도 같은 자리에 선다 — "어디까지 믿어도 되나"의 나머지 절반이다.
    // ⛔ 여기 뜨는 글자 중 화면이 아는 것은 하나도 없다(자료 이름·기준값·주기 전부 서버 값).
    //    화면에 박아 두면 적재하는 순간부터 그 글자만 거짓말을 한다.
    const fresh = foot.locator('section.fresh');
    await expect(fresh.getByRole('heading', { name: '이 자료는 언제 것인가' })).toBeVisible();
    await expect(fresh.locator('tbody tr')).toHaveCount(10); // 결정 0041 로 성적표 줄을 뺀 열 줄
    await expect(fresh.getByText('점포·업종 (상권정보)')).toBeVisible();
    // '202606' 이 사람 말로 바뀌어 실린다(원본을 그대로 찍지 않는다).
    await expect(fresh.getByText('2026년 2분기').first()).toBeVisible();
    // 아직 안 온 예정일은 '무렵'만 — 가짜 답이 2099년이라 날이 흘러도 이 줄은 안 바뀐다.
    await expect(fresh.getByText('2099년 3월 31일 무렵', { exact: true })).toBeVisible();
    // 지난 예정일은 지났다고 사실대로 적는다(인허가 2026-08-31 — 앞으로도 늘 과거다).
    await expect(fresh.getByText('2026년 8월 31일 무렵 — 지났습니다, 갱신 전')).toBeVisible();
    // 주기가 없는 자료에 아무 날짜나 적지 않는다.
    await expect(fresh.getByText('정해진 주기 없음').first()).toBeVisible();
    // 자료가 아직 한 행도 없는 갈래도 줄은 남는다 — 빼면 "그런 자료를 안 쓴다"로 읽힌다.
    await expect(fresh.getByText('자료 없음')).toBeVisible();

    // 보던 지역이 함께 실리는지 보려고 구를 하나 고른다(휴대폰은 찾기 탭에서 고르고 더보기로 돌아온다).
    await gotoTab(page, '찾기');
    await pickGu(page, '서울', '강남구');
    await gotoTab(page, '더보기');

    await foot.getByRole('button', { name: '의견 보내기' }).click();
    // 답장을 못 한다는 사실을 **미리** 말한다 — 기다리게 해 놓고 안 하는 것이 가장 나쁘다.
    await expect(foot.getByText(/답장을 드릴 수 없습니다/)).toBeVisible();

    // 종류를 고르지 않으면 보내기가 잠겨 있다(기본 선택 없음 — 2026-10-06).
    await foot.getByRole('radio', { name: '건의·제안' }).check();
    await foot.getByRole('textbox').fill('3층 정보가 안 보여요');
    await foot.getByRole('button', { name: '보내기' }).click();

    await expect(foot.getByText(/고맙습니다/)).toBeVisible();

    expect(sent).toHaveLength(1);
    expect(sent[0].p_kind).toBe('opinion');
    expect(sent[0].p_body).toBe('3층 정보가 안 보여요');
    // ⛔ 여기가 이 의견함의 값어치 전부다 — 사람이 손으로 안 적어도 어디를 보던 중이었는지가
    //    함께 간다. 이 줄이 깨지면 남는 것은 맥락 없는 한 줄짜리 불평뿐이다.
    expect((sent[0].p_context as Record<string, unknown>).sigungu).toBe('11680');
    // 고른 종류는 kind 가 아니라 context.category 로 실린다(서버 CHECK 는 그대로).
    expect((sent[0].p_context as Record<string, unknown>).category).toBe('suggest');
  });

  test('N. 못 보냈으면 못 보냈다고 말한다 — 거짓 안심을 만들지 않는다', async ({ page }) => {
    await mockOpenSigungu(page);
    // 마이그레이션 적용 전 라이브가 정확히 이 상태다(함수가 아직 없다).
    await mockMissingFunction(page, FEEDBACK_PATTERN);

    await page.goto('/');
    await gotoTab(page, '더보기'); // 휴대폰은 꼬리말이 「더보기」 탭 안(W4a)
    const foot = page.locator('footer.foot');

    // 신선도 표도 같은 상태(함수 없음)다 — **통째로 빠지되 아래 안내는 그대로 선다.**
    // "자료 없음"이라 적으면 모르는 것을 없는 것이라 말하게 된다(LH 카드와 같은 규칙).
    await expect(foot.locator('section.fresh')).toHaveCount(0);
    await expect(foot.locator('.foot__notice')).toBeVisible();

    await foot.getByRole('button', { name: '의견 보내기' }).click();
    await foot.getByRole('radio', { name: '건의·제안' }).check();
    await foot.getByRole('textbox').fill('한마디');
    await foot.getByRole('button', { name: '보내기' }).click();

    await expect(foot.getByText(/보내지 못했습니다/)).toBeVisible();
    await expect(foot.getByText(/고맙습니다/)).toHaveCount(0);
    // 적은 글은 남아 있어야 한다 — 다시 쓰게 만들면 대부분 그냥 떠난다.
    await expect(foot.getByRole('textbox')).toHaveValue('한마디');
  });
});

/**
 * 주소로 들고 다니기 — 공유 링크 · 새로고침 복원.
 *
 * 여기서만 잡히는 것
 * ------------------
 * 이 흐름의 값어치는 **검색을 한 번도 거치지 않는 것**이다. 단위 테스트는 그 사실을
 * 흉내로만 확인하지만, 여기서는 진짜 브라우저가 진짜 주소로 들어와 화면이 서는지 본다.
 * 주소를 읽는 시점(첫 그림 한 번)과 서버 응답이 오는 시점이 어긋나면 여기서 드러난다.
 */
const LINK_BLD = '1168010100100010000_1024110';

test.describe('층별 스택뷰 — 주소로 들고 다니기', () => {
  test('O. 링크로 바로 들어오면 검색 없이 그 건물이 열린다', { tag: '@onecol' }, async ({ page }) => {
    await mockOpenSigungu(page);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()]);
    // 검색은 **안 불려야** 정상이다. 그래도 막아 둔다 — 안 막으면 혹시 불렸을 때
    // 실존하지 않는 도메인으로 요청이 나가 실패 원인이 흐려진다.
    let searched = 0;
    await page.route(SEARCH_PATTERN, async (route) => {
      searched += 1;
      await route.fulfill({ status: 200, body: '[]' });
    });

    await page.goto(`/?sgg=11680&bld=${LINK_BLD}`);

    const stack = page.locator('section.stack');
    await expect(stack.getByRole('heading', { name: '테스트빌딩' })).toBeVisible();
    // 구 이름도 살아난다 — 주소에는 코드(11680)만 담겨 있고 이름은 서버 목록에서 얻는다.
    // ⓘ 링크로 연 건물은 입구가 접힌 채 시작한다(S1) — 바에 지금 구, 지도는 펼쳐야 그린다.
    //    휴대폰(W4a)은 바 대신 탭 — 첫 탭이 「건물」이고 지도는 지도 탭에서만 그린다.
    //    PC 두 칸(W5)은 바가 없고 왼쪽 칸(지도 포함)이 링크로 열어도 그대로 선다(Q5 — 자동 접기 없음).
    if (await isPhoneTabs(page)) {
      await expect(tabButton(page, '건물')).toHaveAttribute('aria-current', 'page');
      await expect(page.locator('.entrybar')).toHaveCount(0);
    } else if (await isTwoCols(page)) {
      await expect(page.locator('.entrybar')).toHaveCount(0);
      await expect(page.locator('section.dmap')).toBeVisible();
    } else {
      await expect(page.locator('.entrybar__place')).toHaveText('서울 강남구');
    }
    if (!(await isTwoCols(page))) await expect(page.locator('section.dmap')).toHaveCount(0);
    await unfoldEntry(page, '상권 지도 보기');
    // 휴대폰 지도 탭은 지도 가득(W4b) — 제목 대신 위 띠에 지금 구가 선다.
    if (await isPhoneTabs(page)) await expect(page.locator('.rstrip__btn')).toHaveText('서울 강남구 ▾');
    else await expect(page.getByRole('heading', { name: /강남구 상권 지도/ })).toBeVisible();
    // 가지고 나가는 버튼도 함께 선다(휴대폰은 건물 탭에).
    await gotoTab(page, '건물');
    await expect(page.getByRole('button', { name: '링크 복사' })).toBeVisible();
    // ★ 열자마자 주소가 스스로 지워지지 않는다(그러면 새로고침하는 순간 링크가 죽는다).
    expect(new URL(page.url()).search).toContain(`bld=${LINK_BLD}`);
    expect(searched).toBe(0);
  });

  test('P. 층 자료가 없는 건물 링크면 빈 화면 대신 안내가 뜬다', async ({ page }) => {
    await mockOpenSigungu(page);
    // 층이 한 줄도 없는 건물이 239동 실재한다.
    await mockFloorStack(page, [], []);

    await page.goto(`/?sgg=11680&bld=${LINK_BLD}`);

    await expect(page.getByText(/링크에 담긴 건물을 찾지 못했습니다/)).toBeVisible();
    await expect(page.locator('section.stack')).toHaveCount(0);
    // 실패해도 주소는 남긴다 — 서버가 잠깐 흔들린 것일 수 있어 새로고침으로 다시 해 본다.
    expect(new URL(page.url()).search).toContain(`bld=${LINK_BLD}`);
  });

  test('Q. 검색으로 건물을 고르면 주소에 그 건물이 적힌다', async ({ page }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page);

    await page.goto('/');
    // 아무것도 안 고른 첫 화면은 주소가 깨끗하다('?'만 남기지 않는다).
    expect(new URL(page.url()).search).toBe('');

    await pickGu(page, '서울', '강남구');
    await expect.poll(() => new URL(page.url()).search).toContain('sgg=11680');

    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    await expect.poll(() => new URL(page.url()).search).toContain(`bld=${LINK_BLD}`);
  });
});

test.describe('층별 스택뷰 — 종이로 뽑기', () => {
  /**
   * 왜 E2E 로 보나 — 이 기능은 **거의 전부가 CSS** 다(결정 0020). 화면 시험(jsdom)은
   * 스타일시트를 읽지 않아 "종이에서 무엇이 보이나"를 원리적으로 못 본다. 인쇄 매체를
   * 흉내 낼 수 있는 곳은 여기뿐이다.
   *
   * ⚠️ `emulateMedia` 는 그 페이지에 계속 남는다 — 시험이 끝나면 되돌린다(다음 시험이
   *    같은 페이지를 쓰지는 않지만, 남겨 두면 실패했을 때 원인을 찾기 어렵다).
   */
  async function openBuilding(page: Page) {
    await mockOpenSigungu(page);
    /*
      ⛔ 신선도 표를 **여기서 진짜 답으로 덮는다.** 기본값(함수 없음)으로 두면 표가 아예 안
         그려져, `.fresh` 의 인쇄 규칙이 **한 번도 실제로 돌지 않는다** — 이 레포가 인쇄로 데인
         사고(막대가 백지로 나옴 · 접힌 카드가 통째로 사라짐)는 전부 이 자리에서만 잡혔고,
         그때도 "규칙을 적어 뒀다"는 사실만으로는 아무것도 보장되지 않았다.
    */
    await mockJson(page, DATA_FRESHNESS_PATTERN, dataFreshness());
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(
      page,
      [parcelTx()],
      [floorRow({ floor_no: 2 }), floorRow()],
      industryMix(),
    );
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack')).toBeVisible();
  }

  test('R. 종이에서는 조종 장치가 빠지고 머리글이 붙는다', async ({ page }) => {
    await openBuilding(page);

    // 화면에서는 — 버튼이 있고 머리글은 없다.
    await expect(page.getByRole('button', { name: '인쇄 · PDF로 저장' })).toBeVisible();
    await expect(page.locator('.printmeta')).toBeHidden();
    // 빈 카드는 화면에서는 선다(접힌 채 제목 + 요약 한 줄) — 아래 종이에서만 빠진다.
    // ⓘ 서울 건물이라 빈 카드는 가게 이력 하나다(결정 0045 PR③) — 추정매출·상권 인구는 제 카드가 그리고, 여기서는
    //   그 함수가 기본(함수 없음)이라 카드째 없다.
    await expect(page.locator('section.card--history .card__summary')).toHaveText('지금은 비어 있음');
    await expect(page.locator('section.card--sales')).toHaveCount(0);
    await expect(page.locator('section.card--pop')).toHaveCount(0);
    await expect(page.locator('section.sales')).toHaveCount(0);
    await expect(page.locator('section.pop')).toHaveCount(0);

    await page.emulateMedia({ media: 'print' });

    // ① 종이에서 누를 수 없는 것은 종이에 없다.
    //    (규칙 없이 뽑으면 첫 장 위 절반이 검색창·구 칩·버튼이었다 — 2026-08-25 실측)
    await expect(page.locator('.region')).toBeHidden();
    await expect(page.locator('.search')).toBeHidden();
    await expect(page.locator('.takeout')).toBeHidden();
    await expect(page.locator('.fb')).toBeHidden();
    await expect(page.locator('.dmap__toggle')).toBeHidden();
    await expect(page.locator('.card__caret').first()).toBeHidden();
    // ⛔ 넘기기 링크 구역도 통째로 빠진다(결정 0014 §5 — "페이지 끝 한 구역이면 인쇄 시
    //    그것만 제외하면 된다"). 종이에서는 아무 데도 못 누르므로 죽은 파란 글씨만 남는다.
    await expect(page.locator('.links')).toBeHidden();
    // 형제 사이트 링크 구역도 같은 이유로 빠진다(2026-10-06).
    await expect(page.locator('.family')).toBeHidden();
    // 빈 카드도 종이에서 빠진다(👤 물결 1-B — "지금은 비어 있음" 뿐이라 종이 자리만 먹는다 · 서울 건물은 가게 이력 하나).
    // ⓘ 빼는 이름표는 빈 상태일 때만 붙는 `card--empty` 다 — 자료가 차면 그때부터 종이에 나온다.
    await expect(page.locator('section.card--empty')).toHaveCount(1);
    await expect(page.locator('section.card--history')).toBeHidden();

    // ② 이 종이가 무슨 건물이고 언제 것이며 원본이 어디인지.
    const meta = page.locator('.printmeta');
    await expect(meta).toBeVisible();
    await expect(meta.locator('.printmeta__title')).toHaveText('테스트빌딩');
    await expect(meta.locator('.printmeta__addr')).toHaveText('서울 강남구 테헤란로 1');
    await expect(meta.locator('.printmeta__app')).toHaveText('상가 층별 스택뷰');
    // ⚠️ 시각을 값으로 박지 않는다 — 돌리는 날·시간대에 따라 달라진다. 모양만 본다.
    await expect(meta.locator('.printmeta__when')).toHaveText(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2} 뽑음$/);
    // 원본 주소는 링크 복사 버튼이 주는 것과 같은 값이다.
    await expect(meta.locator('.printmeta__url')).toHaveText(new RegExp(`bld=${LINK_BLD}`));

    // ③ 본론과 근거·출처·면책은 그대로 남는다 — 뺀 것은 조종 장치뿐이다.
    await expect(page.locator('.stack__title')).toBeVisible();
    await expect(page.locator('.card--floors .floor').first()).toBeVisible();
    await expect(page.locator('.foot__notice')).toBeVisible();
    // ⛔ "이 자료는 언제 것인가"도 종이에 남는다 — 조종 장치가 아니라 **내용**이다.
    //    종이는 되물을 수가 없어서, 이 숫자가 언제 것인지는 화면에서보다 종이에서 더 중요하다.
    //    (감춤 목록에 `.fresh` 를 넣으면 이 줄이 빨간불이 된다 — 돌연변이로 확인함.)
    await expect(page.locator('section.fresh')).toBeVisible();
    await expect(page.locator('.tx__src')).toBeVisible();

    await page.emulateMedia({ media: null });
  });

  test('S. 접어 둔 카드도 종이에는 나오고, 막대 색이 지워지지 않는다', async ({ page }) => {
    await openBuilding(page);

    const gap = page.locator('section.gap');
    const floorsCard = page.locator('.card--floors');

    // 사용자가 층 목록까지 접어 둔 채로 인쇄하는 상황을 만든다.
    // (『층별 공표값 나란히』는 원래 접힌 채로 시작한다 — 첫 화면 펼침 상한이 넷이라서.)
    await floorsCard.locator('.card__toggle').click();
    await expect(floorsCard.locator('.card__body')).toBeHidden();
    await expect(gap.locator('.card__body')).toBeHidden();

    await page.emulateMedia({ media: 'print' });

    // ⛔ 화면에서 접는 것은 "지금은 안 볼래"이지 "종이에서도 빼라"가 아니다.
    //    이게 깨지면 종이에서 카드가 **제목만 남고 통째로 사라진다**(2026-08-25 실측).
    await expect(floorsCard.locator('.card__body')).toBeVisible();
    await expect(gap.locator('.card__body')).toBeVisible();
    await expect(gap.locator('.gap__val').first()).toBeVisible();
    // 값과 근거는 한 몸이다(절대 규칙 3) — 종이에서도 함께 나와야 한다.
    await expect(gap.locator('.gap__head--tx').getByText('A등급 · 실거래 집계', { exact: true })).toBeVisible();

    // ⛔ 브라우저는 잉크를 아끼려고 배경색을 안 찍는다. 그런데 이 화면에서 막대는
    //    **본론**이라, 이 설정이 빠지면 층별 스택이 종이에서 백지가 된다(2026-08-25 실측).
    await expect(page.locator('.floor__fill').first()).toHaveCSS('print-color-adjust', 'exact');

    // ⛔ 줄 하나가 두 장에 걸쳐 반으로 잘리지 않게 한다. 긴 목록 카드는 이어지도록 **일부러**
    //    두었으므로(카드에 걸면 3장이 4장이 되고 흰 자리가 크게 남는다 — 2026-08-25 실측),
    //    잘림을 막는 최후의 방어선이 줄 단위의 이 설정이다.
    await expect(page.locator('.floor').first()).toHaveCSS('break-inside', 'avoid');
    // 산문이 든 짧은 카드는 반대로 통째로 유지한다 — 문장이 두 장에 걸리면 흐름이 끊긴다.
    await expect(page.locator('.card--district')).toHaveCSS('break-inside', 'avoid');

    await page.emulateMedia({ media: null });
  });

  test('T. 자료가 오기 전에 뽑으면 종이가 스스로 고백한다', async ({ page }) => {
    // ⚠️ jsdom(vitest)은 CSS 를 안 읽어 `::after` 를 원리적으로 못 본다 — 여기가 유일한
    //    방어선이다(B3). 층 목록만 일부러 늦춰, "불러오는 중" 문구가 뜬 채로 인쇄 매체로
    //    바꿔도 안전한지를 본다.
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockJson(page, STATS_PATTERN, [coverageStats()]);
    await mockJson(page, FLOOR_PATTERN, [floorRow()], 5000);
    await mockJson(page, PARCEL_TX_PATTERN, []);
    await mockJson(page, TX_STATS_PATTERN, sigunguTxStats());
    await mockJson(page, DISTRICT_PATTERN, { covered: true, districts: [], sources: [] });
    await mockMissingFunction(page, INDUSTRY_MIX_PATTERN);
    await mockMissingFunction(page, INDUSTRY_DETAIL_PATTERN);
    await mockMissingFunction(page, INDUSTRY_FLOORS_PATTERN);
    await mockMissingFunction(page, INDUSTRY_MEDIAN_PATTERN);
    await mockMissingFunction(page, INDUSTRY_MEDIAN_M_PATTERN);
    await mockMissingFunction(page, BASE_PRICE_PATTERN);
    await mockMissingFunction(page, UNIT_SUMMARY_PATTERN);
    await mockMissingFunction(page, FLOOR_UNITS_PATTERN);
    await mockMissingFunction(page, LAND_PRICE_PATTERN);
    await mockMissingFunction(page, OPEN_CLOSE_PATTERN);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    // 아직 층 목록이 오지 않은 상태("불러오는 중")를 붙잡는다.
    const loadingMsg = page.locator('.msg--loading');
    await expect(loadingMsg).toBeVisible();

    // ⛔ 버튼을 잠그는 방식이 아니라 CSS 로만 막으므로, 인쇄 매체로 바꾸기 전에도
    //    `PrintButton` 은 멀쩡히 눌린다(사용자가 다른 길로 인쇄할 수도 있으니 버튼을
    //    없애거나 막지 않는다) — `.takeout` 자체는 인쇄 매체에서 빠지는 게 정상이라
    //    (테스트 R) 그건 여기서 화면 모드일 때만 확인한다.
    await expect(page.getByRole('button', { name: '인쇄 · PDF로 저장' })).toBeVisible();

    await page.emulateMedia({ media: 'print' });

    // ⚠️ Playwright 의 텍스트 매칭(getByText 등)은 DOM 텍스트 노드만 본다 — `::after` 로
    //    덧붙인 CSS 생성 콘텐츠는 텍스트 노드가 아니라서 안 잡힌다. 그래서 브라우저가
    //    실제로 계산한 값(getComputedStyle)을 직접 읽는다 — 이게 "정말로 그 글자가
    //    종이에 그려지는가"를 보는 유일하고 확실한 방법이다.
    // ⚠️ 이 파일의 타입 검사(tsconfig.e2e.json)는 브라우저 타입(DOM)을 안 켠다 — 이 코드는
    //    브라우저 안에서 도는데 검사만 Node 쪽에서 하기 때문이다. 그래서 `window`·
    //    `getComputedStyle` 같은 전역 이름을 곧이곧대로 쓰면 "그런 이름 없다"고 빨간불이
    //    난다. 지금 보고 있는 그 요소가 속한 창을 타고 들어가면 같은 일을 하면서 검사도 통과한다.
    const afterContent = await loadingMsg.evaluate(
      (el) => el.ownerDocument.defaultView!.getComputedStyle(el, '::after').content,
    );
    expect(afterContent).toContain('아직 자료를 받는 중에 뽑힌 종이라');

    await page.emulateMedia({ media: null });
  });
});

test.describe('층별 스택뷰 — 국세청 기준시가', () => {
  /**
   * 『층별 공표값 나란히』 카드의 기준시가 칸(결정 0041 ㉤ — 내린 참고 시세 카드에서 옮겼다) — 추정이 아니라 고시된 값.
   * 그래서 여기서 눈으로 보는 것은 둘이다:
   *   ① 값·호 수·고시일이 한 칸에 함께 나오고, "시세가 아니다"라고 카드 안에서 한 번 못 박는다
   *   ② 서버에 함수가 아직 없으면 **그 칸만** '–' 이고 카드의 나머지는 멀쩡하다
   * (거르기·짝짓기 같은 순수 규칙은 src/lib/basePrice.test.ts 가 촘촘히 덮는다.)
   */

  /** 층 목록은 같게 두고 기준시가만 갈아 끼운다. `bases` 를 안 주면 함수가 없는 상태다. */
  async function openBuilding(page: Page, bases?: unknown[]) {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(
      page,
      [],
      [floorRow({ floor_no: 2 }), floorRow()],
      undefined,
      bases,
    );
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await openCard(page, /층별 공표값 나란히/);
  }

  const baseCell = (page: Page, floorNo: number) =>
    page.locator(`section.gap .gap__row[data-floor="${floorNo}"] .gap__cell--base`);

  test('U. 기준시가가 층마다 값·호 수·고시일과 함께 뜨고, 「시세가 아닙니다」를 카드 안에서 한 번 적는다', async ({
    page,
  }) => {
    await openBuilding(page, basePrices());

    const gap = page.locator('section.gap');
    // 값만 떼어 내보내지 않는다 — 이 값은 그 층 호실들의 가운데값이다(절대 규칙 3).
    await expect(baseCell(page, 2).locator('.gap__val')).toHaveText('300만');
    await expect(baseCell(page, 2).locator('.gap__sub')).toHaveText('(호 12개 가운데값 · 2026년 1월 1일 고시)');
    // 1층에도 선다 — 밴드처럼 1층을 빼지 않는다(국세청이 낸 값이다).
    await expect(baseCell(page, 1).locator('.gap__val')).toHaveText('410만');
    // 세무 기준가격이라는 사실을 카드 안에서 한 번 못 박는다.
    await expect(gap.getByText(/시세가 아닙니다/)).toHaveCount(1);
    await expect(gap.locator('.gap__head--base').getByText(/A등급 · 공식 고시/)).toBeVisible();
  });

  test('V. 서버에 함수가 아직 없으면 그 칸만 – 이고 카드는 그대로다', async ({ page }) => {
    // 마이그레이션을 적용하기 전 라이브가 바로 이 상태다(404/PGRST202).
    await openBuilding(page);

    const gap = page.locator('section.gap');
    await expect(baseCell(page, 2).locator('.gap__val')).toHaveText('–');
    await expect(baseCell(page, 1).locator('.gap__val')).toHaveText('–');
    // 카드도 다른 칸 값도 그대로다 — "기준시가 없음"이라고 적지도 않는다.
    await expect(gap.locator('.gap__row[data-floor="1"] .gap__cell--tx .gap__val')).toHaveText('㎡당 2,250만');
    await expect(gap).not.toContainText('기준시가 없음');
  });
});

test.describe('입구 — LH 상가 분양·입점 공고', () => {
  /**
   * 이 카드만 **입구**(구는 골랐고 건물은 아직 안 고른 자리)에 선다.
   *
   * 여기서만 잡히는 것
   * ------------------
   * 카드 안쪽(요약 문구·링크·빈손 처리)은 단위 시험이 촘촘히 덮는다. 진짜 브라우저라야
   * 보이는 것은 **서는 자리와 사라지는 때**다 — 구를 고르는 순간 요청이 실제로 나가는지,
   * 건물을 고르면 분석 화면을 어지럽히지 않고 물러나는지.
   */

  test('W. 구를 고르면 접힌 카드로 서고, 펼치면 공고 줄과 LH 링크가 나온다', async ({ page }) => {
    await mockOpenSigungu(page);
    // ⚠️ mockOpenSigungu 뒤에 등록해야 이 응답이 잡힌다(나중에 등록한 것이 먼저다).
    await mockJson(page, LH_NOTICE_PATTERN, [
      // 재게시가 있었던 줄 — 서버가 최신 한 줄만 주고 그 사실을 dup_cnt 로 알린다(결정 0026).
      lhNotice({ dup_cnt: 1 }),
      lhNotice({
        pan_id: '2026-0002',
        pan_nm: '수서역세권 근린생활시설 임대공고',
        kind_nm: '임대 추첨',
        pan_ss: '접수중',
        close_date: null,
      }),
      // LH 가 지역을 '전국'이라 적은 줄 — 제목은 다른 도시다. 접어 두되 지우지 않는다.
      lhNotice({
        pan_id: '2026-0003',
        pan_nm: '인천계양 지구 단지내상가 공고',
        is_nationwide: true,
      }),
    ]);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page);

    await page.goto('/');
    // 구를 고르기 전에는 물을 곳이 없다 — 카드도 없다.
    await expect(page.locator('section.lh')).toHaveCount(0);

    await pickGu(page, '서울', '강남구');

    const lh = page.locator('section.lh');
    await expect(lh).toBeVisible();
    // 접혀 있어도 건수와 **수집일**은 읽힌다 — 마감이 있는 자료라 낡음을 감추지 않는다.
    // 접어 둔 것(전국 표시)도 세어서 밝힌다 — 감추는 것과 없는 척하는 것은 다르다.
    await expect(lh.locator('.card__summary')).toHaveText(
      '2건 · 전국 표시 1건 · 2026년 8월 27일 수집 기준',
    );
    await expect(lh.locator('.card__body')).toBeHidden();

    await openCard(page, /LH 상가 분양·입점 공고/);
    // 위 목록은 **그 지역 공고**만이다(접힌 묶음은 아래에 따로 있다).
    const rows = lh.locator('.lh__list').first().locator('li');
    await expect(rows).toHaveCount(2);
    await expect(rows.first()).toContainText('분양 입찰');
    await expect(rows.first()).toContainText('서울강남 A1블록 단지내상가 입찰공고');
    await expect(rows.first()).toContainText('공고중');
    await expect(rows.first()).toContainText('~9월 17일');
    // 같은 공고가 다시 올라왔던 줄에는 꼬리표가 붙는다(서버가 최신 한 줄만 준다).
    await expect(rows.first()).toContainText('정정·재게시 1회');
    // 마감일이 없는 공고를 '0월 0일'처럼 지어내지 않는다.
    await expect(rows.nth(1)).toContainText('마감일 미정');

    // ⛔ LH 가 '전국'이라 적은 줄은 **접혀 있다가** 눌러야 나온다(결정 0026) — 지운 것이
    //    아니라 접은 것이고, 화면이 제목으로 지역을 추측하지 않는다는 사실도 함께 적는다.
    const more = lh.getByRole('button', { name: /전국.*1건/ });
    await expect(more).toContainText("LH가 지역을 '전국'으로 적은 공고");
    await expect(lh.getByText('인천계양 지구 단지내상가 공고')).toBeHidden();
    await more.click();
    await expect(lh.getByText('인천계양 지구 단지내상가 공고')).toBeVisible();
    await expect(lh).toContainText('제목을 보고 지역을 추측하지 않습니다');

    // 신청·가격은 우리가 옮겨 적지 않고 링크로 넘긴다(전략 — 매물은 링크로).
    const link = rows.first().getByRole('link', { name: 'LH에서 보기' });
    await expect(link).toHaveAttribute('href', 'https://apply.lh.or.kr/notice/2026-0001');
    await expect(link).toHaveAttribute('target', '_blank');
    await expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    await expect(lh).toContainText('출처: 한국토지주택공사(LH)');

    // ⛔ 건물을 고르면 화면의 주제가 그 건물이다 — 카드는 물러난다(휴대폰은 건물 탭에서 숨고 찾기 탭엔 남는다 · W4a F2).
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack')).toBeVisible();
    await expectEntryCardRetreats(page, 'section.lh'); // 휴대폰은 찾기 탭에 남는다(F2)
  });

  test('X. 입구 함수가 아직 없으면 그 카드들이 통째로 조용히 빠진다', async ({ page }) => {
    // 마이그레이션을 적용하기 전 라이브가 바로 이 상태다(404/PGRST202) — mockOpenSigungu 의
    // 기본값이 그것이라 여기서는 아무것도 덧붙이지 않는다.
    // ⓘ 검색·층 스택 목은 일부러 안 건다 — 이 시험은 건물을 고르지 않으므로 그 요청이
    //   애초에 나가지 않는다. 안 쓰는 목을 걸어 두면 "이 시험이 그것까지 본다"고 읽힌다.
    await mockOpenSigungu(page);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');

    // 검색창은 멀쩡하다 — 곁다리 하나가 입구를 통째로 죽이지 않는다.
    await expect(page.getByLabel('건물명 또는 주소')).toBeVisible();
    await expect(page.locator('section.lh')).toHaveCount(0);
    // "공고 없음" 같은 말도 남기지 않는다 — 모르는 것을 없는 것이라 말하지 않는다.
    await expect(page.locator('.app')).not.toContainText('LH 상가 분양·입점 공고');
    // ⓘ 입구 카드는 **둘**이다(흐름도 같은 기본값 = 함수 없음 · 성적표 카드는 결정 0041 로 내렸다). **둘 다**
    //   빠져도 검색창이 서 있는지를 이 한 시험이 함께 본다 — 곁다리들이 본체를 못 죽인다.
    await expect(page.locator('.app')).not.toContainText('참고 시세는 얼마나 맞나');
    await expect(page.locator('section.flow')).toHaveCount(0);
    await expect(page.locator('.app')).not.toContainText('동네 매매 단가 흐름');
  });
});

// ── 입구 — 동네 매매 단가 흐름 (결정 0027) ─────────────────────────────────
//
// ⓘ **함수가 없을 때 카드가 조용히 빠지는 경로는 여기 없다** — 위 스펙 X 가 같은 자리에서
//   함께 본다(입구 함수 셋이 **전부** 404 인 상태에서 검색창이 멀쩡한지). 같은 것을 두 번
//   보는 시험을 만들지 않는다.
// ⚠️ 픽스처를 `e2e/fixtures.ts` 가 아니라 **여기 둔다** — 이 판에서 그 파일은 다른 작업이
//    함께 만지고 있어, 한 줄을 얹으면 서로의 변경이 엉킨다. 쓰는 곳이 이 시험 하나뿐이라
//    옮길 이유도 아직 없다.

/** 첫 해(몇 달치) · 온전한 해 · 올해(표본 부족) 셋 — 화면이 갈라 대해야 하는 세 상태다. */
function txYearly() {
  return [
    {
      yr: '2006',
      n: 447,
      n_all: 447,
      median_unit_price: 4_902_441,
      p25_unit_price: 3_100_000,
      p75_unit_price: 7_400_000,
      median_area_m2: 46.4,
      floor_missing: 92,
      ym_cnt: 4,
      first_ym: '200609',
      last_ym: '200612',
      sigungu_nm: '강남구',
    },
    {
      yr: '2015',
      n: 1550,
      n_all: 1550,
      median_unit_price: 21_171_384,
      p25_unit_price: 12_000_000,
      p75_unit_price: 33_000_000,
      median_area_m2: 18.3,
      floor_missing: 155,
      ym_cnt: 12,
      first_ym: '201501',
      last_ym: '201512',
      sigungu_nm: '강남구',
    },
    {
      yr: '2026',
      n: 3,
      n_all: 3,
      median_unit_price: 30_000_000,
      p25_unit_price: 28_000_000,
      p75_unit_price: 32_000_000,
      median_area_m2: 12.5,
      floor_missing: 1,
      ym_cnt: 8,
      first_ym: '202601',
      last_ym: '202608',
      sigungu_nm: '강남구',
    },
  ];
}

test.describe('입구 — 동네 매매 단가 흐름', () => {
  test('AC. 접힌 카드로 서고, 펼치면 해마다 한 줄씩 — 해의 일부와 표본 부족을 정직하게 적는다', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    // ⚠️ mockOpenSigungu 뒤에 등록해야 이 응답이 잡힌다(나중에 등록한 것이 먼저다).
    await mockJson(page, TX_YEARLY_PATTERN, txYearly());

    await page.goto('/');
    // 구를 고르기 전에는 물을 곳이 없다 — 카드도 없다.
    await expect(page.locator('section.flow')).toHaveCount(0);

    await pickGu(page, '서울', '강남구');

    const flow = page.locator('section.flow');
    await expect(flow).toBeVisible();
    // 접혀 있어도 **언제부터 언제까지 몇 건인지**는 읽힌다(범위·건수 전부 서버가 준 값).
    const summary = flow.locator('.card__summary');
    await expect(summary).toContainText('2006년 9월');
    await expect(summary).toContainText('2026년 8월');
    await expect(summary).toContainText('2,000건');
    await expect(flow.locator('.card__body')).toBeHidden();

    await openCard(page, /동네 매매 단가 흐름/);
    // 상가(근생·판매) 거래만 센 표다(결정 0040 D3) — 제목이 그 사실을 말한다.
    await expect(flow.getByText('동네 매매 단가 흐름 (실거래 · 상가 거래 기준)')).toBeVisible();

    const rows = flow.locator('.flow__rows li');
    await expect(rows).toHaveCount(3);
    // ① 첫 해는 몇 달치뿐이다 — 그렇다고 적는다.
    await expect(rows.first()).toContainText('9~12월분');
    await expect(rows.first()).toContainText('㎡당 490만');
    await expect(rows.first()).toContainText('층 미상 21%');
    // 그 해 단가의 근거가 된 거래 **한 건의 크기**도 같은 줄에 적힌다(2026-09-09b) —
    // 초소형 구획이 무더기로 거래된 해를 기준선 없이 알아보게 하는 사실 한 칸이다.
    await expect(rows.first()).toContainText('한 건 면적 중앙값 46㎡');
    // ② ★ 표본이 모자란 해는 값을 안 적는다(절대 규칙 3).
    await expect(rows.last()).toContainText('표본 부족 (단가 근거 거래 3건 · 지분 제외)');
    await expect(rows.last()).not.toContainText('㎡당');
    // 라벨이 길어졌다(2026-10-08a) — 휴대폰 폭에서도 줄이 카드 밖으로 넘치지 않는다.
    const overflow = await rows.last().evaluate((el) => {
      const card = el.closest('section.flow')!.getBoundingClientRect();
      const r = el.getBoundingClientRect();
      return { right: r.right - card.right, scroll: el.scrollWidth - el.clientWidth };
    });
    expect(overflow.right).toBeLessThanOrEqual(1);
    expect(overflow.scroll).toBeLessThanOrEqual(1);
    expect(
      await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth),
    ).toBeLessThanOrEqual(0);
    // 면적도 함께 감춘다 — 단가와 **같은 거래들**을 잰 값이라, 이것만 남기면 감춘 근거를
    // 곁눈으로 말해 주는 셈이 된다.
    await expect(rows.last()).not.toContainText('한 건 면적');
    // ③ 근거 등급 — 어림한 값이 아니라 신고된 거래다.
    await expect(flow.locator('.grade__badge')).toHaveText('A등급 · 실거래 집계');

    // ⛔ 건물을 고르면 화면의 주제가 그 건물이다 — 입구 카드는 물러난다(휴대폰은 건물 탭에서 숨고 찾기 탭엔 남는다 · W4a F2).
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page);
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack')).toBeVisible();
    await expectEntryCardRetreats(page, 'section.flow'); // 휴대폰은 찾기 탭에 남는다(F2)
  });
});

// ── 둘레에 새로 올라오는 상가 건물 (건축 인허가) ───────────────────────────
// 업종 분포 카드 **안**에 붙는 한 줄이라, 카드가 서는 것과 이 줄이 서는 것은 별개다.
// 단위 시험은 두 조건을 따로 흉내 내지만 "정말 그 카드 안에 그려지나"는 여기서만 본다.
// (그 줄이 없는 경우는 위 테스트 K 가 같은 자리에서 함께 본다.)

test.describe('층별 스택뷰 — 둘레에 새로 올라오는 건물', () => {
  test('Y. 서버가 답하면 업종 분포 카드 안에 동수·허가만·착공·기준월이 한 줄로 뜬다', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    // 업종 분포가 있어야 카드가 선다 — 이 줄은 그 카드 안에 산다.
    await mockFloorStack(page, [], undefined, industryMix(), undefined, nearbyPermits());

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const permits = page.locator('section.mix .mix__permits');
    await expect(permits).toBeVisible();
    // 3동 중 2동 착공 = 허가만 1동. 셋이 서로 맞물려 있어 산수가 틀리면 여기서 드러난다.
    await expect(permits).toContainText('새로 올라오는 상가 건물 3동');
    await expect(permits).toContainText('허가만 1동 · 착공 2동');
    // 기준월은 서버가 준 값이다 — 화면에 글자로 박으면 자료가 바뀌는 날 거짓말이 된다.
    await expect(permits).toContainText('(2026년 7월 인허가 기준)');
    // 오래 멈춰 있는 것은 **빼지 않고 한 줄로 덧붙인다**(사장님 결재 2026-09-05).
    await expect(permits).toContainText('그중 1동은 허가 후 2년 넘게 착공하지 않았습니다');
    // ⛔ 앞일을 단정하지 않는다 — 허가를 받고도 안 짓거나 용도가 바뀌는 일이 흔하다.
    await expect(permits).toContainText('허가를 받았다고 모두 지어지는 것은 아닙니다');
    await expect(permits).not.toContainText('예정');
    // ⛔ 이 카드는 값을 말하지 않는다. 인허가 줄이 들어와도 그 성격은 그대로다.
    await expect(page.locator('section.mix')).not.toContainText('시세');
  });
});

// ── 상권 임대 동향 (부동산원 조사 · 결정 0024) ──────────────────────────────
// 층별 화면의 **여섯 번째 카드**다. 카드 안쪽의 규칙(단위 환산·종류 고르기·요약 문구)은
// 단위 시험이 촘촘히 덮는다 — 여기서만 보이는 것은 **그 카드가 층별 화면에 실제로 서는가**,
// 그리고 접힘 예산을 지키며 **접힌 채로 서는가**다.

test.describe('층별 스택뷰 — 상권 임대 동향', () => {
  test('Z. 접힌 여섯째 카드로 서고, 펼치면 조사값이 상권·분기와 함께 뜬다', async ({ page }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(
      page,
      [],
      [floorRow({ floor_no: 2 }), floorRow()],
      industryMix(),
      undefined,
      undefined,
      rentStats(),
    );

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const stack = page.locator('section.stack');
    const rent = stack.locator('section.rent');
    await expect(rent).toBeVisible();
    // 카드가 하나 늘어도 **첫 화면 펼침은 여전히 넷**이다(로드맵 Wave 2 의 예산).
    // 다섯 장 + 빈 카드 하나(가게 이력 · 물결 1-B) + 층별 공표값(결정 0041 · 접힌 채 — 참고 매매 시세 카드는 내렸다).
    // ⓘ 서울 건물이라 추정매출·상권 인구는 제 카드인데, 함수가 기본(함수 없음)이라 카드째 숨는다(결정 0045 PR③ · CN·CO).
    await expect(stack.locator('.card')).toHaveCount(7);
    await expect(stack.locator('.card__toggle[aria-expanded="true"]')).toHaveCount(4);
    // 접혀 있어도 무엇·언제는 읽힌다. ⛔ 값은 요약에 없다 — 한정어 없이 이 건물 값으로 읽힌다.
    await expect(rent.locator('.card__summary')).toHaveText(
      '공실률 · ㎡당 임대료 · 투자수익률 · 소득수익률 · 2026년 2분기 조사 · 층별 임대료 포함',
    );
    await expect(rent.locator('.card__body')).toBeHidden();

    await openCard(page, /상권 임대 동향/);
    // ★ 단위 — 공표값은 천원/㎡ 다. 1,000을 안 곱하면 '75원'이 되는데 그것도 그럴듯하다.
    await expect(rent.getByText('㎡당 임대료 74,600원')).toBeVisible();
    await expect(rent.getByText('공실률 10.08%')).toBeVisible();
    // ★ '분기'가 붙어 있어야 한다 — 연 수익률로 읽히면 0.82%는 정반대의 뜻이 된다.
    await expect(rent.getByText('투자수익률(분기) 0.82%')).toBeVisible();
    // ⚠️ 요약 줄에도 같은 분기 글자가 있다 — **줄 안의 도장**을 콕 집어 본다(요약을 잡으면
    //    "줄마다 분기를 적는가"라는 이 단언의 뜻이 사라진다).
    await expect(rent.locator('.rent__quarter')).toHaveText('2026년 2분기 조사');
    // 어느 상권의, 부동산원 어느 조사구역 값인지 함께 적는다.
    await expect(rent.locator('.rent__where')).toHaveText('역삼역');
    await expect(rent.locator('.rent__scope')).toHaveText(
      '부동산원 조사구역 서울>강남>테헤란로',
    );

    // ★ 층별 표(결정 0031) — 그 조사구역 줄 안에, 높은 층부터, 지하 1층까지. 소득수익률은 분기 라벨.
    await expect(rent.getByText('소득수익률(분기) 0.9%')).toBeVisible();
    const floors = rent.locator('.rent__rows li .rent__floors');
    await expect(floors).toBeVisible();
    await expect(floors.locator('caption')).toHaveText(
      '층별 ㎡당 월 임대료 — 조사 상권 평균, 이 건물 값이 아님',
    );
    await expect(floors.locator('tbody tr')).toHaveCount(7);
    await expect(floors.locator('tbody tr').first()).toHaveText(/6층 이상\s*22,700원/);
    await expect(floors.locator('tr[data-floor="-1"]')).toHaveText(/지하 1층\s*16,950원/);
    await expect(rent.getByText(/조사 상권의 평균입니다/)).toBeVisible();

    // 종류를 갈아 끼우면 값이 함께 바뀌고, 무엇을 보는 중인지도 따라간다.
    await rent.getByLabel('건물 종류 골라보기').selectOption('오피스');
    await expect(rent.getByText('㎡당 임대료 18,400원')).toBeVisible();
    await expect(rent.locator('.rent__now-type')).toHaveText('오피스');
    // 표도 그 종류의 것으로 바뀐다(오피스는 위 구간이 둘로 나뉜다).
    await expect(floors.locator('tbody tr').first()).toHaveText(/11층 이상\s*28,620원/);
    // ⛔ 종류를 섞지 않는다 — 집합상가 값이 같은 화면에 남아 있으면 안 된다.
    await expect(rent).not.toContainText('74,600원');
    await expect(rent).not.toContainText('22,700원');

    // ⛔ 이 카드는 조사값이다. 추정으로 읽히는 말이 섞이면 이 건물 값처럼 읽혀
    //    구분이 무너진다(사실과 추정을 가르는 것이 이 화면의 신뢰다).
    await expect(rent).not.toContainText('추정');
    await expect(rent).not.toContainText('시세');
    await expect(rent.getByText(/B등급 · 공식 표본조사/)).toBeVisible();
    await expect(rent).toContainText('출처: 한국부동산원 상업용부동산 임대동향조사');
  });

  test('AA. 서버에 함수가 아직 없으면 카드가 통째로 조용히 빠진다', async ({ page }) => {
    // 마이그레이션을 적용하기 전 라이브가 바로 이 상태다(404/PGRST202) — mockFloorStack 의
    // 기본값이 그것이라 여기서는 아무것도 덧붙이지 않는다.
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()]);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const stack = page.locator('section.stack');
    // 층 목록은 멀쩡하다 — 곁다리 하나가 본체를 죽이지 않는다.
    await expect(stack.locator('.card--floors .floor')).toHaveCount(2);
    await expect(stack.locator('section.rent')).toHaveCount(0);
    // "조사값 없음" 같은 말도 남기지 않는다 — 모르는 것을 없는 것이라 말하지 않는다.
    await expect(stack).not.toContainText('상권 임대 동향');
  });

  test('AE. 새 두 칸이 없는 답(2026-10-04a 이전 함수)에서도 카드가 서고, 층별 표만 빠진다', async ({
    page,
  }) => {
    // 결정 0031 — 층별 임대료·소득수익률은 **선택 칸**이다. 화면이 먼저 나가고 함수가 뒤에
    // 바뀌어도(또는 되돌려도) 카드가 통째로 사라지면 안 된다.
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(
      page,
      [],
      [floorRow({ floor_no: 2 }), floorRow()],
      industryMix(),
      undefined,
      undefined,
      [rentStatOld()],
    );

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const rent = page.locator('section.stack section.rent');
    await expect(rent).toBeVisible();
    // 요약은 온 것만 말한다 — 소득수익률·층별 표를 약속하지 않는다.
    await expect(rent.locator('.card__summary')).toHaveText(
      '공실률 · ㎡당 임대료 · 투자수익률 · 2026년 2분기 조사',
    );
    await openCard(page, /상권 임대 동향/);
    await expect(rent.getByText('㎡당 임대료 74,600원')).toBeVisible();
    await expect(rent.locator('.rent__floors')).toHaveCount(0);
    await expect(rent).not.toContainText('소득수익률(분기)');
  });
});

// ── 가게 이름으로 찾기 (결정 0028) ──────────────────────────────────────────
//
// 검색 한 번에 서버를 **둘** 부르고(건물 · 가게 이름) 결과를 두 구역으로 나란히 그린다.
// 여기서만 확인되는 것은 "두 요청이 정말 함께 나가고, 두 구역이 함께 서고, 가게 줄을 누르면
// 층별 화면까지 이어지는가"다 — 조각별 규칙(모양 검사·외 N곳·경쟁 가드)은 단위 시험이 덮는다.
//
// ⓘ **함수가 없을 때 구역이 조용히 빠지는 경로는 여기 없다** — 그건 단위 시험
//   (BuildingSearch.test.tsx)이 같은 자리에서 본다. 같은 것을 두 번 보는 시험을 만들지 않는다.

test.describe('검색 — 가게 이름으로 찾은 땅', () => {
  test('AD. 검색하면 건물 구역과 가게 구역이 함께 서고, 땅 줄을 누르면 층별 화면으로 간다', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit({ bld_nm: '건물로찾은빌딩' })]);
    // ⚠️ mockOpenSigungu 뒤에 등록해야 이 응답이 잡힌다(나중에 등록한 것이 먼저다).
    await mockJson(page, SEARCH_STORES_PATTERN, [
      storeHit({ total_parcel_cnt: 3, total_store_cnt: 12 }),
    ]);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()]);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '스타벅스');

    // 건물 구역 — 여태 있던 그대로다.
    await expect(page.getByRole('button', { name: /건물로찾은빌딩/ })).toBeVisible();

    // 가게 구역 — 사용자가 고를 것 없이 함께 선다.
    const stores = page.getByRole('region', { name: '가게 이름으로 찾은 땅' });
    await expect(stores).toBeVisible();
    await expect(stores).toContainText('이 이름의 가게가 있는 땅 3곳 · 가게 12곳');
    // 서버가 준 상호 원문과, 3개보다 많이 걸렸다는 사실.
    await expect(stores).toContainText('스타벅스역삼점 · 스타벅스테헤란점 외 3곳');
    // ⛔ "이 건물의 가게"가 아니라 **이 땅에** — 층별 화면의 점포 칸과 세는 대상이 다르다.
    await expect(stores).toContainText('이 땅에 가게 5곳 일치');
    // 분기 도장은 서버가 준 값이다(화면에 글자로 박지 않는다).
    await expect(stores).toContainText('2026년 6월 기준 점포 자료');

    // 누르면 검색 결과를 골랐을 때와 **같은 길**로 층별 화면에 닿는다.
    await stores.getByRole('button', { name: /테스트빌딩/ }).click();

    const stack = page.locator('section.stack');
    await expect(stack.getByRole('heading', { name: '테스트빌딩' })).toBeVisible();
    await expect(stack.locator('.card--floors .floor')).toHaveCount(2);
  });

  test('AJ. 일치 상호가 길면 한 줄로 안 잘리고 두 줄까지 보인다', async ({ page }) => {
    // 사장님 결정 C(2026-10-07) — .stores__names 는 line-clamp:2 로 두 줄까지 보여준다.
    // 상호를 넓은 화면에서도 두 줄이 되게 충분히 길게 짓는다(실제 가게 이름 아님).
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit({ bld_nm: '건물로찾은빌딩' })]);
    await mockJson(page, SEARCH_STORES_PATTERN, [
      storeHit({
        matched_names: [
          '아주긴이름의테스트카페역삼중앙점',
          '아주긴이름의테스트카페테헤란로점',
          '아주긴이름의테스트카페강남대로점',
        ],
        match_store_cnt: 7,
        total_parcel_cnt: 3,
        total_store_cnt: 12,
      }),
    ]);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()]);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '아주긴이름의테스트카페');

    const stores = page.getByRole('region', { name: '가게 이름으로 찾은 땅' });
    await expect(stores).toBeVisible();
    const namesLine = stores.locator('.stores__names');
    await expect(namesLine).toContainText('외 4곳');

    const namesHeight = await namesLine.evaluate((el) => el.getBoundingClientRect().height);
    // 한 줄 기준 높이 — 같은 카드의 .stores__addr(여전히 한 줄 말줄임)로 잰다.
    const addrEl = stores.locator('.stores__addr').first();
    await expect(addrEl).toBeVisible();
    const oneLineHeight = await addrEl.evaluate((el) => el.getBoundingClientRect().height);

    expect(namesHeight).toBeGreaterThan(oneLineHeight * 1.3);
    expect(namesHeight).toBeLessThanOrEqual(oneLineHeight * 2 + 2);

    // 양성 대조 — 다른 줄은 여전히 한 줄 말줄임이다. ⓘ PC 두 칸 오른쪽 표(👤 2026-10-22 방법 나 R4)는 칸 안 말줄임 0 이라 줄을 넘긴다.
    const addrWhiteSpace = await addrEl.evaluate(
      (el) => el.ownerDocument.defaultView!.getComputedStyle(el).whiteSpace,
    );
    expect(addrWhiteSpace).toBe((await isTwoCols(page)) ? 'normal' : 'nowrap');
  });
});

test.describe('층별 스택뷰 — 호실 구성표', () => {
  /**
   * 결정 0032. 여기서 눈으로 보는 것은 넷이다:
   *   ① 층 줄 아래 요약 둘째 줄 + 펼친 층의 호 목록(50줄 + 더 보기) + 섞임 안내
   *   ② 주거 층은 수만 — 목록 요청이 **아예 안 나간다**(요청 기록으로 단언)
   *   ③ 호실 자료가 없는 건물의 안내 한 줄 · 함수가 없으면 요약·안내 둘 다 조용히 생략
   *   ④ 종이 — 목록이 든 층만 줄 단위로 끊고, 요약 줄은 층 줄과 한 덩어리
   * (응답 모양 검사·요약 글 같은 순수 규칙은 src/lib/unitTable.test.ts 가 촘촘히 덮는다.)
   */

  /** 층 목록 넷 — 5층은 **요약이 없는 층**(좁은 화면에서 층 줄 모양을 견줄 짝)이다. */
  function unitFloors() {
    return [
      floorRow({ floor_no: 35, main_use: '아파트' }),
      floorRow({ floor_no: 5 }),
      floorRow({ floor_no: 3 }),
      floorRow({ floor_no: 1 }),
    ];
  }

  /**
   * 건물을 연다. `summary` 를 안 주면 함수가 없는 상태(mockFloorStack 기본값) 그대로다.
   * 돌려주는 배열에 목록 함수로 나간 요청(인자)이 차례로 쌓인다.
   */
  async function openBuilding(
    page: Page,
    summary?: unknown[],
    floors = unitFloors(),
    unitsOf: (floorNo: number, offset: number, limit: number) => unknown[] = (_no, offset, limit) =>
      floorUnitsPage(offset, limit),
    /** 층 목록 업종 띠(결정 0038 V4) 응답 — 안 주면 함수 없음(mockFloorStack 기본값). */
    industry?: unknown[],
  ) {
    const unitRequests: Array<Record<string, unknown>> = [];
    page.on('request', (r) => {
      if (r.method() === 'POST' && r.url().includes('/rpc/list_floor_units')) {
        unitRequests.push((r.postDataJSON() ?? {}) as Record<string, unknown>);
      }
    });
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], floors);
    if (industry !== undefined) await mockJson(page, FLOOR_INDUSTRY_PATTERN, industry);
    if (summary !== undefined) {
      await mockJson(page, UNIT_SUMMARY_PATTERN, summary);
      await page.route(FLOOR_UNITS_PATTERN, async (route) => {
        if (route.request().method() === 'OPTIONS') {
          await route.fulfill({ status: 204, headers: CORS_HEADERS });
          return;
        }
        const args = (route.request().postDataJSON() ?? {}) as Record<string, number>;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: CORS_HEADERS,
          body: JSON.stringify(unitsOf(args.p_floor_no, args.p_offset ?? 0, args.p_limit ?? 50)),
        });
      });
    }
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack')).toBeVisible();
    return unitRequests;
  }

  /** 층 이름으로 층 줄 버튼을 찾는다. */
  function floorRowOf(page: Page, label: string) {
    return page
      .locator('.card--floors .floor__row')
      .filter({ has: page.locator('.floor__label', { hasText: new RegExp(`^${label}$`) }) });
  }

  test('AF. 층 줄 아래 요약이 서고, 섞인 층을 펼치면 목록·안내·더 보기 — 주거 층은 목록 요청이 안 나간다', async ({
    page,
  }, testInfo) => {
    // 업종 띠(결정 0038 V4)도 함께 — 5층은 점포 0(띠 없음)이라 아래 모양 비교가 「요약·띠 둘 다 있는 층 ↔ 둘 다 없는 층」이 된다.
    const floors = unitFloors().map((f) => (f.floor_no === 5 ? { ...f, store_cnt: 0 } : f));
    const industry = [35, 3, 1].map((no) => ({ floor_no: no, cat_l_cd: 'I2', cat_l_nm: '음식', store_cnt: 2 }));
    const unitRequests = await openBuilding(page, unitSummary(), floors, undefined, industry);
    const card = page.locator('.card--floors');
    await expect(card.locator('.floor__ind:not(.floor__ind--pending)')).toHaveCount(3);

    // ① 요약 둘째 줄 — 요약이 있는 층만(5층은 없다).
    const lines = card.locator('.floor__units');
    await expect(lines).toHaveCount(3);
    await expect(lines.nth(0)).toHaveText('세대 10');
    await expect(lines.nth(1)).toHaveText('호실 543칸 · 보통 4.0㎡ · 2.7~8.8㎡');
    await expect(lines.nth(2)).toHaveText('호실 690칸 · 보통 4.0㎡ · 3.2~13.1㎡');
    await expect(card.getByText(/'보통'은 그 층 호실 전용면적의 가운데값입니다/)).toBeVisible();

    // ⛔ 요약 줄·업종 띠 때문에 층 줄의 칸 수가 늘지 않는다(좁은 화면 포함) — 요약·띠가 있는 층(3층)과 없는
    //    층(5층)의 층 줄이 같은 칸 배치·같은 높이여야 한다(요약·띠는 층 줄 **밖** 둘째 줄이다 · 결정 0038 V4).
    const shape = (label: string) =>
      floorRowOf(page, label).evaluate((el) => ({
        cols: el.ownerDocument.defaultView!.getComputedStyle(el).gridTemplateColumns,
        kids: el.children.length,
        h: Math.round(el.getBoundingClientRect().height),
      }));
    expect(await shape('3층')).toEqual(await shape('5층'));
    await expect(card.locator('#floor-3 .floor__head .floor__ind')).toHaveCount(1);
    await expect(card.locator('#floor-5 .floor__head .floor__ind')).toHaveCount(0);

    // ② 주거 층은 수만 — 펼쳐도 목록을 부르지 않는다.
    await floorRowOf(page, '35층').click();
    await expect(card.locator('.units')).toContainText('주거·오피스텔 층은 호 목록을 보여 주지 않습니다.');
    await expect(card.locator('.units__list')).toHaveCount(0);

    // ① 섞인 층 — 펼치는 그때 50줄 + 섞임 안내.
    await floorRowOf(page, '3층').click();
    const list = card.locator('.units__list li');
    await expect(list).toHaveCount(50);
    await expect(list.first()).toContainText('3가001호');
    await expect(card.locator('.units__mixed')).toHaveText(
      '이 층은 상가와 주거·오피스텔이 섞여 있어 함께 나옵니다 — 호실마다의 용도는 아직 담지 않았습니다.',
    );
    await expect(card).not.toContainText('대장 자료에 없습니다');
    // 넓은 화면은 상세가 세 칸(구획 · 점포 · 호실)으로 나란히, 좁은 화면은 한 칸으로 접힌다.
    // ⓘ 한 번 `.detail` 규칙에 밀려 셋째 칸이 둘째 줄로 떨어진 적이 있다(이 스펙의 스크린숏으로 잡음).
    const detailCols = await card
      .locator('.detail--units')
      .evaluate((el) => el.ownerDocument.defaultView!.getComputedStyle(el).gridTemplateColumns.split(' ').length);
    expect(detailCols).toBe(testInfo.project.name === 'mobile' ? 1 : 3);
    await page.getByRole('button', { name: /더 보기/ }).click();
    await expect(list).toHaveCount(100);
    await expect(list.nth(50)).toContainText('3가051호');

    // ② 요청 기록 — 목록 제공 층(1·3층)의 첫 쪽(호실 구성표 기본값 '지하~3층' — 물결 1-C2 · 👤 2026-10-11)과
    //    펼친 3층의 둘째 쪽만 나갔다. 35층(주거)을 묻는 요청은 **0번**이다.
    // ⓘ 개발 서버는 StrictMode 라 effect 가 두 번 돌아 첫 쪽 요청이 겹쳐 나갈 수 있다(앞 것은
    //   버려진다) — 그래서 횟수가 아니라 **무엇을 물었나**(층·쪽)의 묶음으로 본다.
    const asked = [...new Set(unitRequests.map((a) => `${a.p_floor_no}/${a.p_offset}/${a.p_limit}`))].sort();
    expect(asked).toEqual(['1/0/50', '3/0/50', '3/50/50']);
    expect(unitRequests.some((a) => a.p_floor_no === 35)).toBe(false);
    expect(unitRequests.every((a) => a.p_bld_id === searchHit().bld_id)).toBe(true);

    await card.screenshot({ path: testInfo.outputPath(`u2-floors-${testInfo.project.name}.png`) });
    // 등급 문단의 호실 문장(👤 2026-10-04 쉬운 말) — 목록 제공 층 요약이 붙었으니 선다.
    const grade = page.locator('p.grade', { hasText: 'D등급' });
    await expect(grade).toContainText('이 호실 면적에 임대 카드의 ㎡당 임대료를 곱해도 이 호실의 월세가 아닙니다.');
    await grade.screenshot({ path: testInfo.outputPath(`u2-grade-${testInfo.project.name}.png`) });

    // ④ 종이 — 목록이 든 층만 줄 단위로 끊는다.
    await page.emulateMedia({ media: 'print' });
    const opened = card.locator('li.floor.floor--units-open');
    await expect(opened).toHaveCount(1);
    await expect(opened).toHaveCSS('break-inside', 'auto');
    // 나머지 층은 그대로 통째 유지 · 층 줄과 요약 줄은 한 덩어리 · 호 목록 줄도 갈리지 않는다.
    await expect(card.locator('li.floor').first()).toHaveCSS('break-inside', 'avoid');
    await expect(opened.locator('.floor__head')).toHaveCSS('break-inside', 'avoid');
    await expect(list.first()).toHaveCSS('break-inside', 'avoid');
    await expect(lines.nth(1)).toBeVisible();
    // 받아 둔 줄은 종이에 그대로 나오고, 누르는 장치(더 보기)만 빠진다.
    await expect(list.nth(99)).toBeVisible();
    await expect(card.locator('.units__more')).toBeHidden();
    await card.screenshot({ path: testInfo.outputPath(`u2-floors-print-${testInfo.project.name}.png`) });
    await page.emulateMedia({ media: null });
  });

  test('AG. 호실 자료가 없는 건물이면 층 목록 카드 맨 아래에 안내 한 줄', async ({ page }, testInfo) => {
    // floorRow 의 기본값은 집합건물이라 문구를 일반 건물 쪽으로 보려고 덮어쓴다.
    const unitRequests = await openBuilding(page, [], [floorRow({ floor_no: 2, is_jiphap: false }), floorRow({ is_jiphap: false })]);
    const card = page.locator('.card--floors');
    await expect(card.locator('.floor__units-none')).toHaveText(
      '이 건물에는 호실 자료가 없습니다 — 칸별로 등기가 나뉘지 않은 일반 건물이면 원래 없는 자료입니다.',
    );
    await expect(card.locator('.floor__units')).toHaveCount(0);
    await card.screenshot({ path: testInfo.outputPath(`u2-nounits-${testInfo.project.name}.png`) });
    expect(unitRequests).toHaveLength(0);
  });

  test('AH. 서버에 함수가 아직 없으면 요약도 안내도 조용히 빠진다', async ({ page }) => {
    // 마이그레이션 적용 전 라이브의 상태(404/PGRST202) — mockFloorStack 의 기본값 그대로다.
    const unitRequests = await openBuilding(page);
    const card = page.locator('.card--floors');
    await expect(card.locator('.floor__row')).toHaveCount(4);
    await expect(card.locator('.floor__units')).toHaveCount(0);
    await expect(card.locator('.floor__units-none')).toHaveCount(0);
    await expect(card).not.toContainText('전유부');
    await expect(card).not.toContainText('건축물대장 기준');
    // 층을 펼쳐도 셋째 칸이 안 생기고 목록 요청도 안 나간다.
    await floorRowOf(page, '3층').click();
    await expect(card.locator('.detail')).toBeVisible();
    await expect(card.locator('.units')).toHaveCount(0);
    expect(unitRequests).toHaveLength(0);
  });

  test('CA. 호실 크기 칸 한 줄(결정 0038 G · V3) — 호 목록 위 · 인쇄 구성표에도 · 폭 = 전용면적 비례 · 한 색 · 50칸 + 「그 밖 N호」 · 면적 없음 「–」 · 넓은 칸에만 「101호 · 300.0㎡」(글자는 칸 안 · 13px) · 넘침 0 · 종이에 그대로', async ({
    page,
  }, testInfo) => {
    // 1층(인쇄 구성표 · 기본 지하~3층) = 300 · 150 · 20 · 0 → 칸 셋 63.8% · 31.9% · 4.3% + 「104호 –」.
    // 5층(펼친 상세) = 900 · 40 → 95.7% · 4.3% · 3층 = 543호(칸 50 + 그 밖 493호).
    const units: Record<number, Array<{ ho: string; excl_area_m2: number; total_cnt: number }>> = {
      1: [
        { ho: '101호', excl_area_m2: 300, total_cnt: 4 },
        { ho: '102호', excl_area_m2: 150, total_cnt: 4 },
        { ho: '103호', excl_area_m2: 20, total_cnt: 4 },
        { ho: '104호', excl_area_m2: 0, total_cnt: 4 },
      ],
      // 큰 호는 대장 호 이름이 비고 꼬리 「호」만 붙은 꼴(운영 개포주공 7단지상가 실측) — 칸 글자는 면적만 「900.0㎡」.
      5: [
        { ho: '호', excl_area_m2: 900, total_cnt: 2 },
        { ho: '502호', excl_area_m2: 40, total_cnt: 2 },
      ],
    };
    const summary = [
      ...unitSummary(),
      { floor_no: 5, unit_cnt: 2, median_area_m2: 470, min_area_m2: 40, max_area_m2: 900, floor_kind: 'commercial' },
    ];
    await openBuilding(page, summary, unitFloors(), (no, offset, limit) =>
      units[no] ? (offset === 0 ? units[no] : []) : floorUnitsPage(offset, limit),
    );
    const card = page.locator('.card--floors');
    const phone = testInfo.project.name === 'mobile';
    // 호실 구성표 기본값(지하~3층)이라 1·3층 층 줄 아래에 인쇄 구성표 칸 줄이 먼저 선다(5층은 계획 밖 — 칸 줄 없음).
    await expect(card.locator('#floor-1 .floor__unitprint .ucell')).toHaveCount(3);
    await expect(card.locator('#floor-3 .floor__unitprint .ucell')).toHaveCount(50);
    await expect(card.locator('#floor-5 .ucells')).toHaveCount(0);
    // 주거 층(35층)은 목록이 0줄이라 칸도 없다.
    await expect(card.locator('#floor-35 .ucells')).toHaveCount(0);
    // V3 보완 2 — 목록이 늦게 와도 세 칸이 안 밀린다: 5층 목록 답을 붙잡아 두고 펼치면 칸 줄 자리가 먼저(안 보이게) 서 있고,
    // 답이 온 뒤 세 칸의 높이 자리 그대로 · 진짜 칸 줄 높이 = 미리 잡은 자리 높이.
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    await page.route(FLOOR_UNITS_PATTERN, async (route) => {
      const a = (route.request().postDataJSON() ?? {}) as Record<string, number>;
      if (route.request().method() === 'POST' && a.p_floor_no === 5) await gate;
      await route.fallback();
    });
    await floorRowOf(page, '5층').click();
    const pend = card.locator('#floor-5 .detail > .ucells--pending');
    await expect(pend).toHaveCount(1);
    await expect(pend).toHaveCSS('visibility', 'hidden');
    await expect(pend).toHaveAttribute('aria-hidden', 'true');
    const colY = async () => (await card.locator('#floor-5 .detail > .detail__col').first().boundingBox())!.y;
    const yBefore = await colY();
    const hBefore = (await pend.boundingBox())!.height;
    release();
    await expect(card.locator('#floor-5 .detail > .ucells .ucell')).toHaveCount(2);
    await expect(pend).toHaveCount(0);
    expect(Math.abs((await colY()) - yBefore), '세 칸이 밀리지 않음').toBeLessThan(1);
    expect(Math.abs((await card.locator('#floor-5 .detail > .ucells').boundingBox())!.height - hBefore)).toBeLessThan(1);
    // 👤 2026-10-22 「펼친 칸 위 전체 폭」 — 칸 줄은 상세 세 칸(용도별 구획 · 점포 · 호실) **위** 가로 전체 한 줄 ·
    // 호실 칸 안에는 없다(두 번 그리지 않기) · 그림은 목록과 같은 내용이라 aria-hidden · 한 색(사실 색 --fact-2).
    await expect(card.locator('#floor-5 .units .ucells')).toHaveCount(0);
    const strip5 = card.locator('#floor-5 .detail > .ucells .ucells__strip');
    await expect(strip5).toHaveAttribute('aria-hidden', 'true');
    const fullWidth = async () => {
      const row = (await card.locator('#floor-5 .detail > .ucells').boundingBox())!;
      const detail = await card.locator('#floor-5 .detail').evaluate((el) => {
        const cs = el.ownerDocument.defaultView!.getComputedStyle(el);
        const b = el.getBoundingClientRect();
        return { x: b.x + parseFloat(cs.borderLeftWidth) + parseFloat(cs.paddingLeft), w: el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) };
      });
      const cols = await card.locator('#floor-5 .detail > .detail__col').evaluateAll((els) => els.map((e) => e.getBoundingClientRect().y));
      return { row, detail, cols };
    };
    {
      const f = await fullWidth();
      expect(Math.abs(f.row.x - f.detail.x)).toBeLessThan(1);
      expect(Math.abs(f.row.width - f.detail.w)).toBeLessThan(1);
      expect(f.cols).toHaveLength(3);
      for (const y of f.cols) expect(f.row.y + f.row.height).toBeLessThanOrEqual(y + 0.5);
    }
    for (const c of await card.locator('.ucell').all()) await expect(c).toHaveCSS('background-color', 'rgb(224, 180, 90)');
    // 글 — 설명 · 「그 밖 N호」 · 「–」 · 복층 각주(옆 글이 읽히고 그림만 숨는다).
    const note1 = card.locator('#floor-1 .floor__unitprint .ucells__note');
    await expect(note1).toHaveText(
      '크기 비교이지 자리 배치가 아닙니다. 전용면적 값이 없는 호(칸 없음): 104호 –. 여러 층에 걸친 호실은 걸친 층마다 한 번씩 셉니다.',
    );
    await expect(card.locator('#floor-3 .floor__unitprint .ucells__rest')).toHaveText('그 밖 493호');
    await expect(card.locator('#floor-1 .ucells__rest')).toHaveCount(0);

    const measure = (sel: string) =>
      card.locator(sel).evaluate((root) => {
        const win = root.ownerDocument.defaultView!;
        const r = (el: { getBoundingClientRect(): { x: number; width: number } }) => el.getBoundingClientRect();
        const row = root.querySelector('.ucells__row')!;
        const strip = root.querySelector('.ucells__strip')!;
        const cells = [...root.querySelectorAll('.ucell')].map((c) => {
          const lab = c.querySelector('.ucell__lab');
          const shown = lab !== null && win.getComputedStyle(lab).display !== 'none';
          return {
            x: r(c).x,
            w: r(c).width,
            lab: shown ? { x: r(lab!).x, w: r(lab!).width, fs: win.getComputedStyle(lab!).fontSize, t: lab!.textContent } : null,
          };
        });
        return { row: r(row).width, strip: { x: r(strip).x, w: r(strip).width }, cells };
      });
    /**
     * 한 칸 줄 단언 — 칸 폭 비율 · 폭 합 = 줄 · 줄 바깥 폭 ≥ 기준 폭(`UNIT_CELL_REF` 와 같은 수) · 보이는 글자 = 기대 ·
     * 글자 상자가 제 칸 안 · 13px.
     */
    const check = async (sel: string, shares: number[], labs: string[], refW: number, where: string) => {
      const m = await measure(sel);
      expect(m.row, `${where} ${sel} 줄 폭`).toBeGreaterThanOrEqual(refW);
      expect(m.cells.map((c) => c.w / m.strip.w).map((v, i) => Math.abs(v - shares[i]) < 0.01)).toEqual(shares.map(() => true));
      expect(Math.abs(m.cells.reduce((s, c) => s + c.w, 0) - m.strip.w), `${where} 폭 합`).toBeLessThan(1);
      const last = m.cells[m.cells.length - 1];
      expect(last.x + last.w, `${where} 넘침`).toBeLessThanOrEqual(m.strip.x + m.strip.w + 0.5);
      expect(m.cells.filter((c) => c.lab).map((c) => c.lab!.t), `${where} ${sel} 글자`).toEqual(labs);
      for (const c of m.cells) {
        if (!c.lab) continue;
        expect(c.lab.fs).toBe('13px');
        expect(c.lab.x, `${where} ${c.lab.t} 왼쪽`).toBeGreaterThanOrEqual(c.x - 0.5);
        expect(c.lab.x + c.lab.w, `${where} ${c.lab.t} 오른쪽`).toBeLessThanOrEqual(c.x + c.w + 0.5);
      }
    };
    const SH1 = [300 / 470, 150 / 470, 20 / 470];
    const SH5 = [900 / 940, 40 / 940];
    const SH3 = Array.from({ length: 50 }, () => 1 / 50);
    for (const vw of phone ? [412, 360] : [1280, 1024, 1023, 721]) {
      await page.setViewportSize({ width: vw, height: 900 });
      const where = `${testInfo.project.name} ${vw}`;
      // 인쇄 구성표 꼴(기준 넓은 480 · 휴대폰 230) — 휴대폰은 101호만, 넓은 화면은 102호까지.
      await check('#floor-1 .floor__unitprint .ucells', SH1, phone ? ['101호 · 300.0㎡'] : ['101호 · 300.0㎡', '102호 · 150.0㎡'], phone ? 230 : 480, where);
      await check('#floor-3 .floor__unitprint .ucells', SH3, [], phone ? 230 : 480, where);
      // 펼친 상세 세 칸 위 전체 폭 꼴(기준 넓은 500 · 휴대폰 180 · 👤 2026-10-22).
      await check('#floor-5 .detail > .ucells', SH5, ['900.0㎡'], phone ? 180 : 500, where);
      // 가로 넘침 — 칸 줄이 더한 넘침 0(칸 줄을 숨긴 쪽과 같다) · 문서 넘침 0(721 도 — 2026-10-26 한 열 721~819 층 줄 칸 틀 · CL).
      const [over, overWithout] = await page.locator('html').evaluate((html) => {
        const doc = html.ownerDocument;
        const w = () => html.scrollWidth - doc.defaultView!.innerWidth;
        const st = doc.createElement('style');
        const a = w();
        st.textContent = '.ucells{display:none!important}';
        doc.head.appendChild(st);
        const b = w();
        st.remove();
        return [a, b];
      });
      expect(over, `${where} 칸 줄이 더한 가로 넘침`).toBe(overWithout);
      expect(over, `${where} 가로 넘침`).toBeLessThanOrEqual(0);
      await expect(card.locator('.ucells__note').first()).toHaveCSS('font-size', '13px');
      await expect(card.locator('.ucells__rest').first()).toHaveCSS('font-size', '13px');
    }
    await card.screenshot({ path: testInfo.outputPath(`v3-cells-${testInfo.project.name}.png`) });

    // 3층을 펼치면 상세에도 칸 50 + 「그 밖 493호」(더 보기로 목록이 늘어도 칸 줄은 첫 50호 그대로).
    await floorRowOf(page, '3층').click();
    await expect(card.locator('#floor-3 .detail > .ucells .ucell')).toHaveCount(50);
    await expect(card.locator('#floor-3 .detail > .ucells .ucells__rest')).toHaveText('그 밖 493호');
    await card.locator('#floor-3 .units__more').click();
    await expect(card.locator('#floor-3 .units__list li')).toHaveCount(100);
    await expect(card.locator('#floor-3 .detail > .ucells .ucell')).toHaveCount(50);
    await floorRowOf(page, '5층').click();

    // 종이(A4 폭 703 흉내) — 넓은 벌 글자 · 칸 줄에만 break-inside: avoid · 층·카드 통째에는 안 건다.
    await page.setViewportSize({ width: 703, height: 900 });
    await page.emulateMedia({ media: 'print' });
    try {
      await check('#floor-1 .floor__unitprint .ucells', SH1, ['101호 · 300.0㎡', '102호 · 150.0㎡'], 480, 'print 703');
      await check('#floor-5 .detail > .ucells', SH5, ['900.0㎡'], 500, 'print 703');
      /*
        V3 보완 2(메인 운영 종이 실측 — 인쇄 구성표 칸 줄·목록이 카드 오른쪽 테두리 밖으로). 종이 흉내 폭 740 = 720 묶음이 안 걸려 층 줄이
        여러 칸이고 카드 안쪽(약 620px)이 층 줄 버튼 최소 폭(약 682px)보다 좁은 꼴(운영 page.pdf 와 같은 꼴) — 구성표 칸 줄·목록·펼친 상세의
        오른쪽 끝 ≤ 카드 안쪽 오른쪽. 층 줄 버튼 글자 자리는 고치기 전과 같다(옛 규칙을 덮어 견준다 · 덮은 쪽은 실제로 넘친다 = 양성 대조).
      */
      for (const pw of [740, 760, 800]) {
        await page.setViewportSize({ width: pw, height: 900 });
        const edges = () =>
          card.evaluate((c) => {
            const right = (s: string) => [...c.querySelectorAll(s)].map((e) => e.getBoundingClientRect().right);
            const win = c.ownerDocument.defaultView!;
            const cs = win.getComputedStyle(c);
            // 종이 95%(보완 3) — 계산된 테두리·안쪽 여백은 줄이기 전 값이라 상자(줄인 값)와 단위를 맞춘다.
            const z = parseFloat(win.getComputedStyle(c.ownerDocument.documentElement).zoom) || 1;
            return {
              inner: c.getBoundingClientRect().right - (parseFloat(cs.borderRightWidth) + parseFloat(cs.paddingRight)) * z,
              blocks: right('.floor__unitprint .ucells__row, .floor__unitprint-list, .floor__unitprint-more, .detail'),
              head: [...c.querySelectorAll('#floor-1 .floor__row > *')].map((e) => Math.round(e.getBoundingClientRect().left)),
            };
          });
        const now = await edges();
        expect(now.blocks.length, `print ${pw} 덩어리 수`).toBeGreaterThanOrEqual(6);
        for (const r of now.blocks) expect(r, `print ${pw} 카드 안쪽 오른쪽 ${now.inner}`).toBeLessThanOrEqual(now.inner + 0.5);
        const old = await card.evaluate(async (c) => {
          const doc = c.ownerDocument;
          const st = doc.createElement('style');
          st.textContent = '.floors{grid-template-columns:none!important}';
          doc.head.appendChild(st);
          const blocks = [...c.querySelectorAll('.floor__unitprint-list')].map((e) => e.getBoundingClientRect().right);
          const head = [...c.querySelectorAll('#floor-1 .floor__row > *')].map((e) => Math.round(e.getBoundingClientRect().left));
          st.remove();
          return { blocks, head };
        });
        expect(old.head, `print ${pw} 층 줄 글자 자리 그대로`).toEqual(now.head);
        if (pw === 740) expect(Math.max(...old.blocks), '양성 대조 — 옛 규칙이면 넘친다').toBeGreaterThan(now.inner + 1);
      }
      await page.setViewportSize({ width: 703, height: 900 });
      await expect(card.locator('#floor-1 .ucells__row')).toHaveCSS('break-inside', 'avoid');
      await expect(card.locator('#floor-1 .ucells')).toHaveCSS('break-inside', 'auto');
      await card.screenshot({ path: testInfo.outputPath(`v3-cells-print-${testInfo.project.name}.png`) });
    } finally {
      await page.emulateMedia({ media: null });
    }
  });

  test('CB. 종이 95%(👤 2026-10-22 결정 0038 V3 보완 3) — 실제 page.pdf 장수가 옛 판(넘침 때문에 크롬이 저절로 줄이던 때)과 같다 · 95% 를 빼면 같거나 는다 · 종이에 그려진 크기 0.95 · 화면 크기는 그대로', async ({
    page,
  }, testInfo) => {
    // page.pdf 는 크롬(headless)에만 있다 — 휴대폰 꼴(mobile)도 크롬 엔진이지만 같은 PDF 라 한 벌만 본다.
    test.skip(testInfo.project.name !== 'chromium', 'page.pdf 는 chromium 한 벌만');
    // 가짜 41층 건물(강남파이낸스센터 꼴 층 수) — 호실 요약 0줄(구성표 없음 · 층 줄만 쌓인다).
    const floors = Array.from({ length: 41 }, (_, i) => floorRow({ floor_no: 41 - i, main_use: '기타일반업무시설' }));
    // 층 목록 업종 띠(결정 0038 V4 보완 1)도 선 채로 잰다 — 층마다 점포 2곳(픽스처 store_cnt) + 층 모름 3곳.
    const industry = [
      ...floors.map((f) => ({ floor_no: f.floor_no, cat_l_cd: 'I2', cat_l_nm: '음식', store_cnt: 2 })),
      { floor_no: null, cat_l_cd: 'G2', cat_l_nm: '소매', store_cnt: 3 },
    ];
    await openBuilding(page, [], floors, undefined, industry);
    await page.setViewportSize({ width: 1280, height: 900 });
    await expect(page.locator('.card--floors .floor__row')).toHaveCount(41);
    await expect(page.locator('.card--floors .floor__ind:not(.floor__ind--pending)')).toHaveCount(41);
    await expect(page.locator('.card--floors .floor__ind-unknown')).toBeVisible();
    await page.waitForLoadState('networkidle');
    // 화면에는 줄이기가 없다.
    expect(await page.locator('html').evaluate((h) => h.ownerDocument.defaultView!.getComputedStyle(h).zoom)).toBe('1');
    const pages = async (css?: string) => {
      const st = css ? await page.addStyleTag({ content: css }) : null;
      try {
        const buf = await page.pdf({ format: 'A4' });
        return (buf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) ?? []).length;
      } finally {
        await st?.evaluate((e) => e.remove());
      }
    };
    const now = await pages();
    // 옛 판(e603758) = 층 목록 묶음 규칙도 95% 도 없던 때 — 넘침 때문에 크롬이 저절로 약 95% 로 줄였다.
    const old = await pages('@media print { html { zoom: 1 !important; } .floors { grid-template-columns: none !important; } }');
    // 보완 2 판(77e60f2) = 넘침만 고치고 95% 없음 — 한 장 늘던 회귀(양성 대조).
    const noZoom = await pages('@media print { html { zoom: 1 !important; } }');
    // ⛔ 장수를 숫자로 박지 않는다 — 글꼴이 다른 CI(우분투)에서는 같은 가짜 건물이 [6, 6, 6] 이었다(윈도우 [5, 5, 6]).
    // ① 지킬 핵심: 95% 규칙 = 옛 판과 같은 장수 ② 95% 를 빼면 장수가 같거나 는다(윈도우는 실제로 한 장 는다 — 리눅스는 같을 수 있다).
    expect(now, `장수 지금 ${now} · 옛 판 ${old} · 95% 뺌 ${noZoom}`).toBe(old);
    expect(noZoom).toBeGreaterThanOrEqual(now);
    // ③ 95% 가 실제로 먹는가는 장수 말고 그려진 크기로(글꼴과 무관) — 높이가 CSS 로 고정된 층 막대(`.floor__bar`)의 그려진 높이 ÷ 계산된
    //    높이(줄이기 전 값)가 종이 흉내에서 0.95 · 화면에서 1 · 95% 를 덮어 끄면 종이에서도 1(양성 대조).
    //    ⓘ 맨 아래 층(`.last()`) — 화면은 층 목록 아래 10줄만 보여 위층 막대는 숨어 높이가 0 이다(S2).
    //    ⓘ 리눅스에서는 ①②가 95% 를 빼도 초록일 수 있다(장수가 안 갈림) — 95% 규칙을 지키는 것은 이 ③ 이다.
    const barRatio = () =>
      page.locator('.card--floors .floor__bar').last().evaluate((b) => {
        const h = parseFloat(b.ownerDocument.defaultView!.getComputedStyle(b).height);
        return b.getBoundingClientRect().height / h;
      });
    expect(await barRatio()).toBeCloseTo(1, 2);
    await page.emulateMedia({ media: 'print' });
    try {
      expect(await page.locator('html').evaluate((h) => h.ownerDocument.defaultView!.getComputedStyle(h).zoom)).toBe('0.95');
      expect(await barRatio()).toBeCloseTo(0.95, 2);
      const off = await page.addStyleTag({ content: '@media print { html { zoom: 1 !important; } }' });
      expect(await barRatio()).toBeCloseTo(1, 2);
      await off.evaluate((e) => e.remove());
    } finally {
      await page.emulateMedia({ media: null });
    }
  });
});

// ── 상권 개업·폐업 (서울시 공표 · 결정 0033 R2) ──────────────────────────────
// 카드 안쪽 규칙(표본 < 30 · 빠진 분기 빈 칸 · 막대 높이 · 빈 상태 넷)은 단위 시험이 덮는다
// (`OpenCloseSection.test.tsx`·`openClose.test.ts`). 여기서만 보이는 것은 **층별 화면에 접힌 채
// 실제로 서는가**, 좁은 폭(412px)에서 추이 칸이 넘치지 않는가, 종이에도 나오는가다.

test.describe('층별 스택뷰 — 상권 개업·폐업', () => {
  test('AI. 접힌 카드로 서고 펼치면 서울 상권 숫자·발 문구, 대전 건물이면 그 사실 한 줄', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()], industryMix());
    // 나중에 등록한 것이 먼저 잡힌다 — mockFloorStack 의 '함수 없음' 위에 덮는다.
    await mockJson(page, OPEN_CLOSE_PATTERN, openClose());

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const stack = page.locator('section.stack');
    const oc = stack.locator('section.oc');
    await expect(oc).toBeVisible();
    // 카드가 하나 늘어도 첫 화면 펼침은 여전히 넷이다(로드맵 Wave 2 의 예산).
    await expect(stack.locator('.card__toggle[aria-expanded="true"]')).toHaveCount(4);
    await expect(oc.locator('.card__summary')).toHaveText(
      '코엑스 외 상권 1곳 · 2026년 2분기까지 서울시 공표',
    );
    await expect(oc.locator('.card__body')).toBeHidden();

    await openCard(page, /상권 개업·폐업/);
    await expect(oc.locator('.oc__name')).toHaveText(['코엑스 · 발달상권', '강남 마이스 관광특구 · 관광특구']);
    const first = oc.locator('.oc__district').first();
    await expect(first.locator('.oc__latest .oc__num')).toHaveText([
      '점포 441곳(프랜차이즈 포함)',
      // 프랜차이즈 비중(👤 물결 1-B) — 63 ÷ 441(점포(프랜차이즈 포함)) · stor_co 378 이 분모가 아니다.
      '프랜차이즈 63곳 (점포의 14.29% · 서울시 공표 개수로 계산)',
      '개업 5곳 · 개업률(분기) 1.13%',
      '폐업 9곳 · 폐업률(분기) 2.04%',
    ]);
    // 추이 — 여덟 칸, 옛 분기가 왼쪽. 둘째 상권은 빠진 분기가 빈 칸으로 선다.
    await expect(first.locator('.oc__col')).toHaveCount(8);
    await expect(first.locator('.oc__col').first()).toHaveAttribute('data-quarter', '20243');
    await expect(first.locator('.oc__col').last()).toHaveAttribute('data-quarter', '20262');
    const second = oc.locator('.oc__district').nth(1);
    await expect(second.locator('.oc__col--missing')).toHaveCount(6);
    await expect(second.locator('.oc__col--missing .oc__bar')).toHaveCount(0);
    // 막대 눈금 — 카드 하나에 하나(두 상권 공통). 최댓값은 첫 상권 가장 옛 분기 폐업률 2.74%.
    await expect(oc.locator('.oc__scale')).toHaveText('막대가 꽉 차면 2.74%(분기) · 보는 기간(최근 2년(8분기))의 가장 큰 값 기준');
    const barPct = async (bar: ReturnType<typeof oc.locator>) =>
      bar.evaluate((el) => {
        // 바탕 칸의 아래 선(1px)은 빼고 잰다(clientHeight).
        return (el.getBoundingClientRect().height / el.parentElement!.clientHeight) * 100;
      });
    const firstMax = await barPct(first.locator('.oc__col').first().locator('.oc__bar--close'));
    const secondClose = await barPct(second.locator('.oc__col').last().locator('.oc__bar--close'));
    const secondOpen = await barPct(second.locator('.oc__col').last().locator('.oc__bar--open'));
    expect(firstMax).toBeCloseTo(100, 0);
    // ★ 둘째 상권 2.1% 는 제 최댓값(100%)이 아니라 공통 눈금 2.74% 기준 비례다.
    expect(secondClose).toBeCloseTo((2.1 / 2.74) * 100, 0);
    expect(secondOpen).toBeCloseTo((1.5 / 2.74) * 100, 0);
    // 업종 표는 접혀 있다.
    await expect(first.locator('.oc__table')).toBeHidden();
    await first.locator('.oc__ind-sum').click();
    await expect(first.locator('.oc__table tbody tr')).toHaveCount(2);
    // ⛔ 업종 이름 첫 칸이 좁아 '일/반/의/류'처럼 한 글자씩 세로로 쪼개지면 안 된다
    // — 그 칸 글자 크기의 4.5배(글자 4~5개 들어갈 폭) 이상을 최소로 본다.
    const nameCell = first.locator('.oc__table tbody th').first();
    const nameCellWidth = await nameCell.evaluate((el) => el.getBoundingClientRect().width);
    const nameCellFontSize = await nameCell.evaluate((el) =>
      parseFloat(el.ownerDocument.defaultView!.getComputedStyle(el).fontSize),
    );
    expect(nameCellWidth).toBeGreaterThanOrEqual(nameCellFontSize * 4.5);
    await expect(first.locator('.oc__other')).toContainText('그 밖 47업종');
    // 발 문구 넷.
    await expect(oc).toContainText(
      '출처: 서울시 상권분석서비스(점포-상권) · 서울 열린데이터광장 · 공공누리 1유형(출처표시)',
    );
    await expect(oc).toContainText('상권 전체 값이며 이 건물의 값이 아닙니다');
    await expect(oc).toContainText('둘레의 업종 분포');
    await expect(oc).toContainText('서울시 계산식(개업·폐업 점포 ÷ 점포(프랜차이즈 포함) × 100)');
    await expect(oc.locator('.oc__trend-cap').first()).toContainText('분기별 개업률·폐업률 — 최근 2년(8분기)');

    // ⛔ 좁은 폭(412px)에서 여덟 칸 막대가 옆으로 넘치지 않는다 — 페이지도, 추이 칸도.
    // ⓘ e2e 는 DOM 타입 없이 돈다 — 전역 document 대신 locator 로 잰다.
    const overflow = {
      page: await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth),
      cols: await oc
        .locator('.oc__cols')
        .evaluateAll((els) => Math.max(...els.map((c) => c.scrollWidth - c.clientWidth))),
    };
    expect(overflow.page).toBeLessThanOrEqual(0);
    expect(overflow.cols).toBeLessThanOrEqual(0);

    // 종이 — 펼친 카드 본문이 그대로 나오고 막대 색이 안 지워진다.
    await page.emulateMedia({ media: 'print' });
    await expect(first.locator('.oc__bar--open').first()).toHaveCSS('print-color-adjust', 'exact');
    await expect(first.locator('.oc__trend')).toHaveCSS('break-inside', 'avoid');
    await expect(oc.locator('.oc__scale')).toBeVisible();
    await page.emulateMedia({ media: null });

    // 같은 시험 안에서 대전 건물로 — 카드는 서고 그 사실 한 줄(지역 이름은 pnu 로 고른다).
    await mockJson(page, OPEN_CLOSE_PATTERN, openCloseNotSeoul());
    await mockJson(page, SEARCH_PATTERN, [
      searchHit({ bld_id: 'dj-1', pnu: '3011010700108770000', bld_nm: '대전빌딩', road_addr: '대전 중구 1' }),
    ]);
    await unfoldEntry(page); // 건물을 열면 입구가 접힌다(S1)
    await search(page, '대전빌딩');
    await page.getByRole('button', { name: /대전빌딩/ }).click();
    // ⓘ 층 목록 목업은 그대로라 머리 제목은 앞 건물 이름이다 — 카드 요약이 바뀐 것으로 본다.
    await expect(oc.locator('.card__summary')).toHaveText('서울 상권만 다루는 자료라 이 건물(대전)에는 없습니다');
    // 빈 카드 — 대전 건물의 매출·유동인구는 그 사실 한 줄, 가게 이력은 지역과 무관(👤 물결 1-B).
    await expect(stack.locator('section.card--sales .card__summary')).toHaveText('대전은 아직 받지 않았습니다');
    await expect(stack.locator('section.card--pop .card__summary')).toHaveText('대전은 아직 받지 않았습니다');
    await expect(stack.locator('section.card--history .card__summary')).toHaveText('지금은 비어 있음');
    await openCard(page, /상권 개업·폐업/);
    await expect(oc.locator('.oc__lead')).toHaveText(
      '서울시 상권분석서비스는 서울 상권만 다룹니다 — 이 건물(대전)에는 그 자료가 없습니다.',
    );
    await expect(oc.locator('.oc__col')).toHaveCount(0);
    await expect(oc).not.toContainText('코엑스');
  });

  test('CM. 대전 건물 — 「동네 폐업 (대전시 공표)」 카드(요약은 동·언제까지만) · 펼치면 이름 줄·폐업 378건·기간·분기 막대 다섯(옛 → 최근 · 높이 비례 · 막대 위 건수 13px)·업종 표 5줄 + 그 밖·발 문구 여섯 · 넘침 0 · 창업자 요약 칸 · 종이에 그대로 · 함수 없으면 지금 대전 카드', async ({
    page,
  }, testInfo) => {
    const DJ = '3017010100100010000';
    const BLD = `${DJ}_1`;
    await page.addInitScript(() => {
      type Kv = { setItem(k: string, v: string): void };
      (globalThis as unknown as { localStorage: Kv }).localStorage.setItem('sangga.viewerRole', '창업자');
    });
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit({ bld_id: BLD, pnu: DJ, bld_nm: '대전빌딩', road_addr: '대전 서구 둔산로 1' })]);
    await mockFloorStack(page, [], [floorRow({ bld_id: BLD, pnu: DJ, floor_no: 2 }), floorRow({ bld_id: BLD, pnu: DJ })], industryMix());
    // 나중에 등록한 것이 먼저 잡힌다 — mockFloorStack 의 '함수 없음' 위에 덮는다.
    await mockJson(page, OPEN_CLOSE_PATTERN, openCloseNotSeoul());
    const djCalls: string[] = [];
    await page.route(DAEJEON_CLOSURE_PATTERN, async (route) => {
      if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: CORS_HEADERS });
      djCalls.push(route.request().postData() ?? '');
      await route.fulfill({ status: 200, contentType: 'application/json', headers: CORS_HEADERS, body: JSON.stringify(daejeonClosure()) });
    });

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await gotoTab(page, '찾기'); // 휴대폰 창업자는 첫 탭이 지도다(0036 ④)
    await search(page, '대전빌딩');
    await page.getByRole('button', { name: /대전빌딩/ }).first().click();

    const stack = page.locator('section.stack');
    const oc = stack.locator('section.oc');
    await expect(oc).toBeVisible();
    await expect(oc.locator('.card__h')).toContainText('동네 폐업 (대전시 공표)');
    await expect(stack.getByText('상권 개업·폐업 (서울시 공표)')).toHaveCount(0);
    // 접힌 요약에 값 0 — 동과 언제까지만(서울 카드와 같은 규칙 · 펼침은 역할 배치 그대로).
    await expect(oc.locator('.card__summary')).toHaveText('둔산2동 · 2026년 1분기까지 대전시 공표');
    // 미리 부르기 한 번 — 카드와 요약 판이 같은 답을 나눠 쓴다.
    expect(djCalls).toEqual([JSON.stringify({ p_pnu: DJ })]);
    // 창업자 요약 칸(지시서 #9).
    const tile = page.locator('.rsum__tile--openclose');
    await expect(tile.locator('.rsum__label')).toHaveText('동네 폐업 (대전시 공표)');
    await expect(tile).toContainText('폐업 378건 · 2025년 2분기~2026년 1분기(가게 업종)');
    await expect(tile).toContainText('둔산2동 · 대전시 공표');

    await openCard(page, /동네 폐업/);
    await expect(oc.locator('.oc__name')).toHaveText('둔산2동 · 가게 업종');
    await expect(oc.locator('.oc__latest .oc__num')).toHaveText('폐업 378건');
    await expect(oc.locator('.oc__latest .oc__quarter')).toHaveText('2025년 2분기~2026년 1분기');
    const cols = oc.locator('.oc__col');
    await expect(cols).toHaveCount(5);
    await expect(oc.locator('.oc__val')).toHaveText(['95', '100', '80', '103', '95']);
    // 옛 분기 왼쪽 → 최근 오른쪽 · 막대 높이 비례(103 이 가장 높다 · 80 은 그 약 0.78배).
    const xs = await cols.evaluateAll((els) => els.map((e) => e.getBoundingClientRect().x));
    expect([...xs].sort((a, b) => a - b)).toEqual(xs);
    const hs = await oc.locator('.oc__bar').evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height));
    expect(Math.max(...hs)).toBeCloseTo(hs[3], 3);
    expect(hs[2] / hs[3]).toBeGreaterThan(0.75);
    expect(hs[2] / hs[3]).toBeLessThan(0.81);
    await expect(oc.locator('.oc__val').first()).toHaveCSS('font-size', '13px');
    await expect(oc.locator('.oc__table--dj tbody tr')).toHaveText([
      '음식점업111건',
      '주점 및 비알코올 음료점업35건',
      '섬유, 의복, 신발 및 가죽제품 소매업32건',
      '미용, 욕탕 및 유사 서비스업26건',
      '유원지 및 기타 오락관련 서비스업21건',
      '그 밖 11종 153건',
    ]);
    await expect(oc.locator('.oc__why li')).toHaveCount(6);
    await expect(oc.locator('.oc__why li').last()).toHaveText(
      "업종 이름은 나라 표준 업종(대전시 기준)이라 '업종 분포' 카드(소상공인시장진흥공단)와 다릅니다.",
    );
    await expect(oc.locator('.oc__why li strong')).toHaveText('동네(행정동) 전체 값이며 이 건물의 값이 아닙니다.');
    await expect(oc).not.toContainText('%');
    const overflow = await page.evaluate(() => {
      const d = (globalThis as unknown as { document: { documentElement: { scrollWidth: number; clientWidth: number } } })
        .document.documentElement;
      return d.scrollWidth - d.clientWidth;
    });
    testInfo.annotations.push({ type: 'CM 실측', description: `${testInfo.project.name}: 막대 높이 ${hs.map((h) => h.toFixed(1)).join('·')} · 넘침 ${overflow}` });
    expect(overflow).toBeLessThanOrEqual(0);

    // 종이 — 펼친 본문이 그대로 나오고 막대 색이 안 지워진다 · 그림은 한 덩어리.
    await page.emulateMedia({ media: 'print' });
    await expect(oc.locator('.oc__bar').first()).toHaveCSS('print-color-adjust', 'exact');
    await expect(oc.locator('.oc__trend')).toHaveCSS('break-inside', 'avoid');
    await expect(oc.locator('.oc__why li')).toHaveCount(6);
    await page.emulateMedia({ media: null });

    // 함수가 없으면(PGRST202) — 지금 대전 카드 그대로(옛 제목 · 옛 문장).
    await page.unrouteAll({ behavior: 'ignoreErrors' });
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit({ bld_id: BLD, pnu: DJ, bld_nm: '대전빌딩', road_addr: '대전 서구 둔산로 1' })]);
    await mockFloorStack(page, [], [floorRow({ bld_id: BLD, pnu: DJ, floor_no: 2 }), floorRow({ bld_id: BLD, pnu: DJ })], industryMix());
    await mockJson(page, OPEN_CLOSE_PATTERN, openCloseNotSeoul());
    await page.reload();
    const oc2 = page.locator('section.stack section.oc');
    await expect(oc2).toBeVisible();
    await expect(oc2.locator('.card__h')).toContainText('상권 개업·폐업 (서울시 공표)');
    await openCard(page, /상권 개업·폐업/);
    await expect(oc2.locator('.oc__lead')).toHaveText(
      '서울시 상권분석서비스는 서울 상권만 다룹니다 — 이 건물(대전)에는 그 자료가 없습니다.',
    );
    await expect(page.locator('.rsum__tile--openclose')).toContainText('서울 상권만 다루는 자료라 이 건물(대전)에는 없습니다');
  });

  test('CN. 서울 건물 — 「업종별 추정매출 (서울시 추정)」 카드(요약 값 0) · 펼치면 큰 숫자 3개월 합 · 흐름 막대 높이 비례·빠진 분기 「–」 · 업종 표 5 + 그 밖 · 칩 카페 hit · 칩 미용 일부 없음 · 13px · 넘침 0 · 종이에 나옴 · 함수 없으면 카드 0', async ({
    page,
  }, testInfo) => {
    await page.addInitScript(() => {
      type Kv = { setItem(k: string, v: string): void };
      (globalThis as unknown as { localStorage: Kv }).localStorage.setItem('sangga.viewerRole', '창업자');
    });
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()], industryMix());
    const salesCalls: string[] = [];
    await page.route(SALES_PATTERN, async (route) => {
      if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: CORS_HEADERS });
      salesCalls.push(route.request().postData() ?? '');
      await route.fulfill({ status: 200, contentType: 'application/json', headers: CORS_HEADERS, body: JSON.stringify(districtSales()) });
    });

    /** 창업자 · 칩을 골라 건물을 연다(칩은 저장되지 않아 열 때마다 고른다). */
    async function openWithChip(chip: string) {
      await page.goto('/');
      await gotoTab(page, '지도'); // 휴대폰 — 칩은 지도 머리(창업자 첫 탭이 지도라 이미 거기다)
      await pickGu(page, '서울', '강남구');
      await page.locator('.dmap__head .chips').getByRole('button', { name: chip, exact: true }).click();
      await gotoTab(page, '찾기');
      await search(page, '테헤란로');
      await page.getByRole('button', { name: /테스트빌딩/ }).first().click();
      await expect(page.locator('section.stack')).toBeVisible();
    }

    await openWithChip('카페');
    const sales = page.locator('section.stack section.sales');
    await expect(sales).toBeVisible();
    await expect(sales.locator('.card__h')).toContainText('업종별 추정매출 (서울시 추정)');
    // 접힌 요약에 값 0 — 상권과 언제까지만.
    const summary = sales.locator('.card__summary');
    await expect(summary).toHaveText('○○역 2번 출구 외 상권 1곳 · 2026년 2분기까지 서울시 추정');
    expect(await summary.textContent()).not.toMatch(/억|만원|건/);
    await expect(sales).not.toHaveClass(/card--empty/);
    // 서울 필지라 미리 부르기가 한 번 보냈고, 카드는 그 답을 받는다(다시 안 묻는다).
    expect(salesCalls).toEqual([JSON.stringify({ p_pnu: searchHit().pnu })]);

    await openCard(page, /업종별 추정매출/);
    const first = sales.locator('.sales__district').first();
    await expect(sales.locator('.sales__district')).toHaveCount(2);
    await expect(first.locator('.sales__name')).toHaveText('○○역 2번 출구 · 골목상권');
    await expect(first.locator('.sales__num')).toHaveText('2026년 2분기(3개월) 매출 7억 2,300만원');
    await expect(first.locator('.sales__big')).toContainText('결제 15,208건');
    // 눈금 글은 상권 덩어리마다(검사 뒤 보완 F1 — 관광특구가 골목의 약 153배라 카드 하나 눈금이면 골목 막대가 사라진다).
    await expect(sales.locator('.sales__scale')).toHaveText([
      '막대가 꽉 차면 7억 6,000만원(3개월 합)',
      '막대가 꽉 차면 1,163억원(3개월 합)',
    ]);
    await expect(first.locator('.sales__scale')).toHaveText('막대가 꽉 차면 7억 6,000만원(3개월 합)');
    // 흐름 막대 — 옛 → 최신 · 가장 큰 분기(20254) = 칸 높이 · 최신(20262) = 723/760 · 빠진 분기(20244) = 「–」.
    const cols = first.locator('.sales__col');
    await expect(cols).toHaveCount(8);
    const xs = await cols.evaluateAll((els) => els.map((e) => e.getBoundingClientRect().x));
    expect([...xs].sort((a, b) => a - b)).toEqual(xs);
    const barH = (q: string) =>
      first.locator(`.sales__col[data-quarter="${q}"] .sales__bar`).evaluate((e) => e.getBoundingClientRect().height);
    const boxH = await first.locator('.sales__col[data-quarter="20254"] .sales__bars').evaluate((e) => e.clientHeight);
    const hMax = await barH('20254');
    const hLast = await barH('20262');
    expect(hMax).toBeCloseTo(boxH, 0);
    expect(hLast / hMax).toBeGreaterThan(723 / 760 - 0.02);
    expect(hLast / hMax).toBeLessThan(723 / 760 + 0.02);
    await expect(first.locator('.sales__col[data-quarter="20244"] .sales__bar')).toHaveCount(0);
    await expect(first.locator('.sales__col[data-quarter="20244"] .sales__gap')).toHaveText('–');
    await expect(first.locator('.sales__bar--last')).toHaveCount(1);
    // 둘째 상권(관광특구 · 첫 상권의 약 153배)도 제 눈금에서 가장 큰 분기가 칸 높이 — 상권마다 제 눈금이라 첫 상권 막대도 안 사라진다.
    const second = sales.locator('.sales__district').nth(1);
    const bigH = await second.locator('.sales__col[data-quarter="20262"] .sales__bar').evaluate((e) => e.getBoundingClientRect().height);
    const bigBox = await second.locator('.sales__col[data-quarter="20262"] .sales__bars').evaluate((e) => e.clientHeight);
    expect(bigH).toBeCloseTo(bigBox, 0);
    expect(hMax / boxH).toBeGreaterThan(0.95); // 공통 눈금이었다면 760 ÷ 116,300 ≈ 0.7%
    // 해 글 — 휴대폰 칸 폭에서도 잘리지 않는다(검사 뒤 보완 F10 · 시안 꼴 「’24」).
    const years = first.locator('.sales__tick-year');
    await expect(years).toHaveText(['’24', '’25', '’26']);
    for (const y of await years.all()) {
      expect(await y.evaluate((e) => e.scrollWidth - e.clientWidth)).toBeLessThanOrEqual(0);
      const tick = y.locator('xpath=..');
      expect(await tick.evaluate((e) => e.scrollWidth - e.clientWidth)).toBeLessThanOrEqual(0);
    }
    // 업종 표 5 + 그 밖 · 칩 카페 hit 줄.
    await expect(first.locator('.sales__table tbody tr th')).toHaveText([
      '한식음식점',
      '커피-음료 · 고른 업종(카페)',
      '편의점',
      '미용실',
      '스포츠 강습',
      '그 밖 9업종 (더해서)',
    ]);
    // 이름 첫 칸 — 낱말 가운데서 줄을 안 바꾸고(「스포츠 강/습」 금지) 폭은 글자 4.5개 이상(검사 뒤 보완 F10).
    const nameCell = first.locator('.sales__table tbody tr th').nth(4);
    const nameBox = await nameCell.evaluate((e) => {
      const cs = e.ownerDocument.defaultView!.getComputedStyle(e);
      return { w: e.getBoundingClientRect().width, fs: Number.parseFloat(cs.fontSize), wb: cs.wordBreak };
    });
    expect(nameBox.wb).toBe('keep-all');
    expect(nameBox.w).toBeGreaterThanOrEqual(nameBox.fs * 4.5);
    // 「강습」 두 글자가 같은 줄(글자 상자의 위 끝이 같다).
    const gangTops = await nameCell.evaluate((e) => {
      const t = e.firstChild!;
      const i = (t.textContent ?? '').indexOf('강습');
      const r = e.ownerDocument.createRange();
      const tops: number[] = [];
      for (const k of [i, i + 1]) {
        r.setStart(t, k);
        r.setEnd(t, k + 1);
        tops.push(r.getBoundingClientRect().top);
      }
      return tops;
    });
    expect(Math.abs(gangTops[0] - gangTops[1])).toBeLessThan(2);
    await expect(first.locator('.sales__hit')).toHaveCount(1);
    await expect(sales).not.toContainText('%');
    // 13px(화면 묶음).
    for (const sel of ['.sales__scale', '.sales__tick', '.sales__table', '.sales__why', '.sales__lead']) {
      await expect(sales.locator(sel).first()).toHaveCSS('font-size', '13px');
    }
    const overflow = await page.evaluate(() => {
      const d = (globalThis as unknown as { document: { documentElement: { scrollWidth: number; clientWidth: number } } })
        .document.documentElement;
      return d.scrollWidth - d.clientWidth;
    });
    const cardOver = await sales.evaluate((e) => e.scrollWidth - e.clientWidth);
    testInfo.annotations.push({
      type: 'CN 실측',
      description: `${testInfo.project.name}: 막대 ${hMax.toFixed(1)}·${hLast.toFixed(1)} / 칸 ${boxH} · 넘침 ${overflow} · 카드 넘침 ${cardOver}`,
    });
    expect(overflow).toBeLessThanOrEqual(0);
    expect(cardOver).toBeLessThanOrEqual(0);

    // 종이 — 자료가 찬 카드는 종이에 나온다(빈 카드 이름표 없음) · 그림·표 줄은 덩어리 · 막대 색 유지.
    await page.emulateMedia({ media: 'print' });
    await expect(sales).toBeVisible();
    await expect(first.locator('.sales__bar').first()).toHaveCSS('print-color-adjust', 'exact');
    await expect(first.locator('.sales__trend')).toHaveCSS('break-inside', 'avoid');
    await expect(first.locator('.sales__table tbody tr').first()).toHaveCSS('break-inside', 'avoid');
    await expect(sales).not.toHaveCSS('break-inside', 'avoid');
    await page.emulateMedia({ media: null });

    // 칩 미용(서울시 코드 셋) — 미용실 hit · 네일숍은 상위 5 밖 한 줄 · 피부관리실은 없다는 한 줄(더하지 않는다).
    await openWithChip('미용');
    await openCard(page, /업종별 추정매출/);
    await expect(first.locator('.sales__hit th')).toHaveText('미용실 · 고른 업종(미용)');
    await expect(first.locator('.sales__chip-out')).toHaveText(['고른 업종(미용): 네일숍 3,000만원 · 610건 (3개월 합 · 상위 5 밖)']);
    await expect(first.locator('.sales__chip-part')).toHaveText('고른 업종 가운데 피부관리실은 이 자료에 없습니다');

    // 함수가 없으면(PGRST202) — 카드째 없다(「자료 없음」이라 적지 않는다). 나중에 등록한 것이 먼저 잡힌다.
    await mockMissingFunction(page, SALES_PATTERN);
    await page.reload();
    await expect(page.locator('section.stack .stack__head')).toBeVisible();
    await expect(page.locator('section.stack section.card--floors')).toBeVisible();
    await expect(page.locator('section.sales')).toHaveCount(0);
    await expect(page.locator('section.card--sales')).toHaveCount(0);
  });

  test('CO. 서울 건물 — 「상권 인구 (서울시 공표)」 카드(요약 값 0) · 길단위 큰 숫자 「3개월간」 · 미니 막대 둘(휴대폰은 한 칸씩) · 사는/일하는 「YYYY년 기준」 · 끊긴 상권 「…까지」 · 13px · 넘침 0 · 종이에 나옴 · 함수 없으면 카드 0', async ({
    page,
  }, testInfo) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()], industryMix());
    await mockJson(page, POP_PATTERN, districtPop());

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).first().click();
    const pop = page.locator('section.stack section.pop');
    await expect(pop).toBeVisible();
    await expect(pop.locator('.card__h')).toContainText('상권 인구 (서울시 공표)');
    const summary = pop.locator('.card__summary');
    await expect(summary).toHaveText(
      '○○역 2번 출구 외 상권 1곳 · 길단위인구 2026년 2분기 · 사는 사람 2023년 · 일하는 사람 2024년 기준',
    );
    expect(await summary.textContent()).not.toMatch(/명/);

    await openCard(page, /상권 인구/);
    const blocks = pop.locator('.pop__district');
    await expect(blocks).toHaveCount(2);
    const first = blocks.first();
    await expect(first.locator('.pop__chunk--flow .pop__num')).toHaveText('412,560명');
    await expect(first.locator('.pop__chunk--flow .pop__q')).toHaveText('2026년 2분기 3개월간');
    // 서울시가 안 바꾼 해 괄호(검사 뒤 보완 F2 · 시안 원문).
    await expect(first.locator('.pop__chunk--resident .pop__q')).toHaveText('2023년 기준 (서울시가 2024·2025년에는 안 바꿈)');
    await expect(first.locator('.pop__chunk--worker .pop__q')).toHaveText('2024년 기준 (서울시가 2025년에는 안 바꿈)');
    // 배지 옆 작은 글(검사 뒤 보완 F4).
    await expect(pop.locator('.pop__badge-note')).toHaveText('서울시 상권분석서비스 · 생활인구·주민등록·통신사 자료로 서울시가 셈');
    // 가구 수는 싣지 않는다(메인 결정 나 — 서울시 화면 가구세대 수와 다른 값 · 목업엔 있었다).
    await expect(first.locator('.pop__chunk--resident .pop__big')).toHaveText(
      '2,310명2023년 기준 (서울시가 2024·2025년에는 안 바꿈)남 1,090 · 여 1,220',
    );
    await expect(pop).not.toContainText('가구');
    // 미니 막대 둘 — 시간대 6 · 요일 7 · 높이 = 값 ÷ 묶음 최댓값(17~21시 84,000 이 칸 높이 · 0~6시 58,000).
    const figs = first.locator('.pop__bars-fig');
    await expect(figs).toHaveCount(2);
    await expect(figs.nth(0).locator('.pop__scale')).toHaveText('시간대 · 꽉 차면 84,000명(3개월간)');
    await expect(figs.nth(0).locator('.pop__bar')).toHaveCount(6);
    await expect(figs.nth(1).locator('.pop__bar')).toHaveCount(7);
    const hs = await figs.nth(0).locator('.pop__bar').evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height));
    expect(Math.max(...hs)).toBeCloseTo(hs[4], 3);
    expect(hs[0] / hs[4]).toBeGreaterThan(58000 / 84000 - 0.03);
    expect(hs[0] / hs[4]).toBeLessThan(58000 / 84000 + 0.03);
    // 휴대폰은 한 칸씩(위 → 아래) · 넓은 화면은 나란히(같은 줄).
    const [r0, r1] = await figs.evaluateAll((els) => els.map((e) => e.getBoundingClientRect()).map((r) => ({ top: r.top, bottom: r.bottom })));
    if (testInfo.project.name === 'mobile') expect(r1.top).toBeGreaterThanOrEqual(r0.bottom - 1);
    else expect(Math.abs(r1.top - r0.top)).toBeLessThan(2);
    // 끊긴 상권 — 길단위 「…까지」 · 사는 사람 「…까지」 · 일하는 사람 덩이 없음.
    const second = blocks.nth(1);
    await expect(second.locator('.pop__chunk--flow .pop__note')).toHaveText('이 상권 길단위인구 자료는 2025년 4분기까지입니다');
    await expect(second.locator('.pop__chunk--resident .pop__note')).toHaveText('이 상권 사는 사람 자료는 2022년 4분기까지입니다');
    await expect(second.locator('.pop__chunk--worker')).toHaveCount(0);
    await expect(pop).not.toContainText('%');
    await expect(pop).not.toContainText('하루 평균');
    for (const sel of ['.pop__scale', '.pop__tick', '.pop__why', '.pop__lead', '.pop__q']) {
      await expect(pop.locator(sel).first()).toHaveCSS('font-size', '13px');
    }
    const overflow = await page.evaluate(() => {
      const d = (globalThis as unknown as { document: { documentElement: { scrollWidth: number; clientWidth: number } } })
        .document.documentElement;
      return d.scrollWidth - d.clientWidth;
    });
    const cardOver = await pop.evaluate((e) => e.scrollWidth - e.clientWidth);
    testInfo.annotations.push({
      type: 'CO 실측',
      description: `${testInfo.project.name}: 시간대 막대 ${hs.map((h) => h.toFixed(1)).join('·')} · 넘침 ${overflow} · 카드 넘침 ${cardOver}`,
    });
    expect(overflow).toBeLessThanOrEqual(0);
    expect(cardOver).toBeLessThanOrEqual(0);

    // 종이 — 카드가 나오고 인구 덩이는 한 덩어리 · 막대 색 유지.
    await page.emulateMedia({ media: 'print' });
    await expect(pop).toBeVisible();
    await expect(first.locator('.pop__chunk').first()).toHaveCSS('break-inside', 'avoid');
    await expect(first.locator('.pop__bar').first()).toHaveCSS('print-color-adjust', 'exact');
    await expect(pop).not.toHaveCSS('break-inside', 'avoid');
    await page.emulateMedia({ media: null });

    // 함수가 없으면(PGRST202) — 카드째 없다.
    await mockMissingFunction(page, POP_PATTERN);
    await page.reload();
    await expect(page.locator('section.stack section.card--floors')).toBeVisible();
    await expect(page.locator('section.pop')).toHaveCount(0);
    await expect(page.locator('section.card--pop')).toHaveCount(0);
  });
});

// ── 첫 화면 역할 단추 (👤 결정 0036 결정 18) ──────────────────────────────────
// 역할별 표 세 벌·저장 예외는 단위 시험이 덮는다(`FloorStack.test.tsx`·`viewerRoleStore.test.ts`·
// `App.test.tsx`). 여기서만 보이는 것은 **진짜 브라우저 저장소로 새로고침 뒤에도 남는가**,
// 좁은 폭(412px)에서도 같은 차례로 서는가, 종이에서 빠지는가다.

test.describe('첫 화면 — 역할 단추', () => {
  test('AM. 창업자를 고르면 카드가 그 차례·펼침으로 서고, 새로고침해도 남고, 다시 누르면 지금 차례로', { tag: '@onecol' }, async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    // 카드가 전부 서게 한다 — 임대·개업폐업까지 답해야 차례 전체를 견줄 수 있다(빈 카드 셋은 늘 선다).
    await mockFloorStack(
      page,
      [parcelTx()],
      [floorRow({ floor_no: 2 }), floorRow()],
      industryMix(),
      undefined,
      undefined,
      rentStats(),
    );
    // 나중에 등록한 것이 먼저 잡힌다 — mockFloorStack 의 '함수 없음' 위에 덮는다.
    await mockJson(page, OPEN_CLOSE_PATTERN, openClose());
    // 추정매출 · 상권 인구(결정 0045 PR③ — 서울 건물이라 제 카드가 선다).
    await mockJson(page, SALES_PATTERN, districtSales());
    await mockJson(page, POP_PATTERN, districtPop());

    const NO_ROLE = [
      '속한 상권',
      '층 목록',
      '둘레의 업종 분포',
      '실거래 기록',
      // 층별 공표값(결정 0041) — 내린 참고 매매 시세의 자리 · 접힌 채.
      '층별 공표값 나란히 — 국세청 기준시가 · 구 상가 단가 · 부동산원 임대료',
      '상권 임대 동향 (부동산원 조사)',
      '상권 개업·폐업 (서울시 공표)',
      '업종별 추정매출 (서울시 추정)',
      '상권 인구 (서울시 공표)',
      '이 자리 가게 이력',
    ];
    // 빈 카드 셋은 창업자 차례에서 개업·폐업 바로 뒤(👤 물결 1-B).
    const FOUNDER = [
      '속한 상권',
      '층 목록',
      '둘레의 업종 분포',
      '상권 개업·폐업 (서울시 공표)',
      '업종별 추정매출 (서울시 추정)',
      '상권 인구 (서울시 공표)',
      '이 자리 가게 이력',
      '실거래 기록',
      '층별 공표값 나란히 — 국세청 기준시가 · 구 상가 단가 · 부동산원 임대료',
      '상권 임대 동향 (부동산원 조사)',
    ];
    // ⚠️ exact — 카드 머리의 역할 태그('창업자')가 버튼 이름 안에 들어 있어 부분 일치로 찾으면 겹친다.
    const roleBtn = (name: string) => page.locator('.role').getByRole('button', { name, exact: true });
    const stack = page.locator('section.stack');
    const titles = stack.locator('.card .card__title');
    const opened = stack.locator('.card__toggle[aria-expanded="true"]');

    await page.goto('/');
    // 휴대폰(W4a)은 작은 역할 줄이 「더보기」 탭 맨 위 — 고른 뒤 찾기 탭으로 돌아와 구를 고른다.
    await gotoTab(page, '더보기');
    for (const name of ['투자자', '창업자', '중개사']) {
      await expect(roleBtn(name)).toHaveAttribute('aria-pressed', 'false');
    }
    await roleBtn('창업자').click();
    await expect(roleBtn('창업자')).toHaveAttribute('aria-pressed', 'true');

    await gotoTab(page, '찾기');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    await expect(titles).toHaveText(FOUNDER);
    await expect(opened).toHaveCount(4);
    await expect(stack.locator('section.oc .card__toggle')).toHaveAttribute('aria-expanded', 'true');
    await expect(stack.locator('section.tx .card__toggle')).toHaveAttribute('aria-expanded', 'false');
    // 역할은 주소에 안 실린다 — 구·건물 둘뿐(결정 18 ③).
    expect([...new URL(page.url()).searchParams.keys()].sort()).toEqual(['bld', 'sgg']);

    // 새로고침 — 건물은 주소가(결정 0019), 역할은 이 기기 저장이 되살린다.
    await page.reload();
    // ⓘ 링크로 되살린 건물은 입구가 접힌 채(되살리는 동안도 — S1) — 되살아난 역할은 바 단추 글자로 먼저 본다.
    //    휴대폰(W4a)은 바 대신 탭 — 건물 직행 주소라 첫 탭이 「건물」이다.
    //    PC 두 칸(W5)은 바가 없고 왼쪽 칸의 역할 줄이 그대로 서 있다 — 되살아난 역할을 그 줄에서 본다.
    if (await isPhoneTabs(page)) await expect(tabButton(page, '건물')).toHaveAttribute('aria-current', 'page');
    else if (await isTwoCols(page)) await expect(roleBtn('창업자')).toHaveAttribute('aria-pressed', 'true');
    else await expect(page.locator('.entrybar').getByRole('button', { name: '나는 창업자' })).toBeVisible();
    await expect(titles).toHaveText(FOUNDER);
    await expect(opened).toHaveCount(4);

    // 다시 누르면 해제 — 열린 건물 화면이 그 자리에서 지금 차례로 돌아간다.
    // ⓘ 건물을 연 동안 입구가 접혀 있다(S1) — 바의 역할 단추로 역할 줄을 펼친다.
    await unfoldEntry(page, '나는 창업자');
    await expect(roleBtn('창업자')).toHaveAttribute('aria-pressed', 'true');
    await roleBtn('창업자').click();
    await expect(roleBtn('창업자')).toHaveAttribute('aria-pressed', 'false');
    await expect(titles).toHaveText(NO_ROLE);
    await expect(opened).toHaveCount(4);
    await expect(stack.locator('section.oc .card__toggle')).toHaveAttribute('aria-expanded', 'false');

    // 저장도 지웠다 — 새로고침해도 지금 차례.
    await page.reload();
    await expect(titles).toHaveText(NO_ROLE);
    // 새로고침으로 다시 접혔다(S1) — 역할 없음이면 바 단추가 '역할 고르기'다. 펼쳐 역할 줄을 본다.
    await unfoldEntry(page, '나는 역할 고르기');
    for (const name of ['투자자', '창업자', '중개사']) {
      await expect(roleBtn(name)).toHaveAttribute('aria-pressed', 'false');
    }

    // 종이에서는 역할 줄이 빠진다(누르는 장치).
    await expect(page.locator('.role')).toBeVisible();
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('.role')).toBeHidden();
    await page.emulateMedia({ media: null });
    await expect(page.locator('.role')).toBeVisible();
  });
});

// ── 창업자 입구 · 업종 칩 (👤 결정 0036 결정 18 ④⑤⑨ · 물결 1-A2(ii)) ──────────────────
// 칩 표·카드 안 강조·첫 렌더 함정·DOM 조각이 다시 태어나지 않는가는 단위 시험이 덮는다
// (`founderChips.test.ts`·`IndustryMixSection.test.tsx`·`OpenCloseSection.test.tsx`·`App.test.tsx`).
// 여기서만 보이는 것은 **실제 배치**(지도가 검색창 위로 오나 · 좁은 폭에서 칩 줄이 안 넘치나)와 종이다.

test.describe('첫 화면 — 창업자 입구 · 업종 칩', () => {
  test('AN. 창업자면 지도가 검색창 위·칩 여섯 · 카페 칩으로 건물을 열면 두 카드가 따르고, 투자자면 칩 없이 지금 차례', { tag: '@onecol' }, async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()], industryMix());
    // 나중에 등록한 것이 먼저 잡힌다 — mockFloorStack 의 '함수 없음' 위에 덮는다.
    await mockJson(page, OPEN_CLOSE_PATTERN, openClose());
    await mockJson(page, INDUSTRY_DETAIL_PATTERN, {
      snapshot_ym: '202606',
      radius_m: 500,
      cat_l_cd: 'I2',
      districts: [],
      radius: {
        total: 150,
        cats: [
          { cd: 'I201', nm: '한식', n: 100 },
          { cd: 'I212', nm: '비알코올', n: 50 },
        ],
      },
    });
    // 층 분포(물결 2-2)도 답한다 — 층 줄 자체는 AO 가 본다(여기서는 칩 흐름이 층 함수와 함께 서는지만).
    await mockJson(page, INDUSTRY_FLOORS_PATTERN, industryFloors());

    // ⚠️ exact — 카드 머리의 역할 태그('창업자')가 버튼 이름 안에 들어 있어 부분 일치로 찾으면 겹친다.
    const roleBtn = (name: string) => page.locator('.role').getByRole('button', { name, exact: true });
    const chips = page.locator('.dmap__head .chips');
    const chipBtn = (name: string) => chips.getByRole('button', { name, exact: true });
    const top = async (sel: string) => (await page.locator(sel).boundingBox())!.y;

    await page.goto('/');
    const phone = await isPhoneTabs(page);
    await gotoTab(page, '더보기'); // 휴대폰(W4a)은 역할 줄이 「더보기」 탭
    await roleBtn('창업자').click();
    // 휴대폰 = 창업자 입구가 「지도」 탭(결정 0036 ④ 짝 · 지역 고르개도 그 탭에 선다).
    await gotoTab(page, '지도');
    await pickGu(page, '서울', '강남구');

    // 창업자 = 지도가 검색창 위(결정 18 ④) · 지도 제목 줄에 칩 여섯, 처음은 전체.
    await expect(page.locator('section.dmap')).toBeVisible();
    if (phone) await expect(page.locator('section.search')).toBeHidden(); // 지도 탭엔 검색이 없다(찾기 탭)
    else expect(await top('section.dmap')).toBeLessThan(await top('section.search'));
    await expect(chips.getByRole('button')).toHaveText(['카페', '한식', '미용', '학원', '편의점', '전체']);
    await expect(chipBtn('전체')).toHaveAttribute('aria-pressed', 'true');
    // 칩 곁 안내 한 줄(👤 F4) — 글자 그대로.
    await expect(chips.locator('.chips__note')).toHaveText('상권 목록과, 건물을 열면 업종 분포·개업·폐업 카드에 반영됩니다');
    // ⛔ 좁은 폭(412px)에서도 칩 줄(안내 한 줄 포함)이 옆으로 넘치지 않는다.
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);

    await chipBtn('카페').click();
    await expect(chipBtn('카페')).toHaveAttribute('aria-pressed', 'true');
    // 칩은 저장하지 않는다 — 주소에도 안 실린다.
    expect([...new URL(page.url()).searchParams.keys()]).toEqual(['sgg']);

    await gotoTab(page, '찾기');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    // 접힌 바에 고른 업종 글자(👤 G2 · 단추 아님) — 카드의 굵은 줄이 왜 굵은지 접힌 채로도 보인다. 종이에선 바째 빠진다.
    // ⓘ 지도 기억 되살리기(G1)는 E2E 에서 지도 알맹이가 안 그려져(키 없음) 볼 수 없다 — `DistrictMap.test` 「G1」·`App.mapPick.test` 가 본다.
    // ⓘ 휴대폰(W4a)은 바 대신 탭이라 이 글자가 없다(건물 탭으로 바로 간다).
    // ⓘ PC 두 칸(W5)은 바가 없다 — 왼쪽 칸 지도 머리의 칩 줄이 건물을 연 채로도 그대로 보인다(Q5).
    if (phone) {
      await expect(tabButton(page, '건물')).toHaveAttribute('aria-current', 'page');
    } else if (await isTwoCols(page)) {
      await expect(page.locator('.entrybar')).toHaveCount(0);
      await expect(chipBtn('카페')).toBeVisible();
      await expect(chipBtn('카페')).toHaveAttribute('aria-pressed', 'true');
    } else {
      await expect(page.locator('.entrybar .entrybar__chip')).toHaveText('업종: 카페');
      await page.emulateMedia({ media: 'print' });
      await expect(page.locator('.entrybar__chip')).toBeHidden();
      await page.emulateMedia({ media: null });
    }

    // 둘레 업종 분포 — 음식(I2)을 미리 고른 채 열리고 짝 중분류(비알코올) 줄이 굵다.
    const mix = page.locator('section.mix');
    await expect(mix.locator('select.mix__select')).toHaveValue('I2');
    await expect(mix.locator('li.mix__hit .mix__cat')).toHaveText(['비알코올']);
    // 개업·폐업 — 업종 표가 펼쳐져 있고, 짝 업종(커피-음료)이 상위 표에 없으면 그렇다고 한 줄.
    const oc = page.locator('section.oc');
    const first = oc.locator('.oc__district').first();
    await expect(first.locator('.oc__chip-none')).toHaveText('고른 업종(카페)은 이 상권 점포 수 상위 업종에 없습니다');
    await expect(first.locator('.oc__table')).toBeVisible();

    // 종이에서는 칩 줄이 빠진다(역할 단추 줄과 같은 꼴).
    // ⓘ 건물을 연 동안 지도(칩 줄)는 접혀 안 그려진다(S1) — 「상권 지도 보기」로 펼친 채 본다(칩 값은 그대로).
    await unfoldEntry(page, '상권 지도 보기');
    await expect(chipBtn('카페')).toHaveAttribute('aria-pressed', 'true');
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('.chips')).toBeHidden();
    await page.emulateMedia({ media: null });
    await expect(page.locator('.chips')).toBeVisible();

    // 투자자 — 칩 줄이 없고 차례는 지금 그대로(검색 → 지도) · 칩 효과도 풀린다.
    await gotoTab(page, '더보기');
    await roleBtn('투자자').click();
    await expect(page.locator('.chips')).toHaveCount(0);
    if (phone) {
      // 휴대폰 투자자 = 지도는 지도 탭(칩 없이) · 찾기 탭엔 검색만.
      await gotoTab(page, '지도');
      await expect(page.locator('section.dmap')).toBeVisible();
      await expect(page.locator('.chips')).toHaveCount(0);
      // 찾기 탭에선 지도가 숨기만 한다(W4b — 다시 그리지 않고 돌아오면 relayout · 같은 노드).
      await gotoTab(page, '찾기');
      await expect(page.locator('section.dmap')).toBeHidden();
    } else {
      expect(await top('section.search')).toBeLessThan(await top('section.dmap'));
    }
    await expect(mix.locator('select.mix__select')).toHaveValue('');
    await expect(oc.locator('.oc__chip-none')).toHaveCount(0);
  });
});

// ── 업종별 층 분포 (👤 결정 0036 결정 18 ⑲~㉑ · 물결 2-2) ──────────────────────────────
// 층 묶음 계산·늦은 답 버리기·실패 시 줄 없음은 단위 시험(`industryMix.test.ts`·`IndustryMixSection.test.tsx`)이
// 덮는다. 여기서만 보이는 것은 **실제 줄 글자가 블록 안에 서는지**와 좁은 폭(412px)에서 그 긴 한 줄이 안 넘치는지다.

/**
 * 층 함수 목업 — 물어본 `p_cat_m` 대로 갈라 답한다(대분류 줄과 칩 줄이 다른 답을 받게 · 서버처럼 그대로 되돌림).
 * `counted` 를 주면 응답에 `basement_unknown_counted`(물결 2-2c)를 싣는다 — 안 주면 칸 없는 옛 서버 꼴.
 */
async function mockIndustryFloors(page: Page, counted?: boolean) {
  await page.route(INDUSTRY_FLOORS_PATTERN, async (route) => {
    if (route.request().method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: CORS_HEADERS });
      return;
    }
    const args = (route.request().postDataJSON() ?? {}) as { p_cat_l?: string; p_cat_m?: string[] | null };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: CORS_HEADERS,
      body: JSON.stringify({
        ...industryFloors(args.p_cat_l ?? 'I2', args.p_cat_m ?? null),
        ...(counted === undefined ? {} : { basement_unknown_counted: counted }),
      }),
    });
  });
}

test.describe('층별 스택뷰 — 업종별 층 분포', () => {
  test('AO. 대분류를 고르면 블록마다 층 줄(층 미상 칸·%), 창업자 카페 칩이면 고른 업종 줄이 하나 더, 412px 넘침 0', async ({
    page,
  }) => {
    const LINE_D = '층별 음식: 지하 0곳 · 1층 36곳 · 2층 9곳 · 3층 이상 3곳 · 층 미상 12곳 (20%)';
    const LINE_R = '층별 음식: 지하 2곳 · 1층 90곳 · 2층 24곳 · 3층 이상 9곳 · 층 미상 25곳 (17%)';
    const CHIP_D = '층별 고른 업종(카페): 지하 0곳 · 1층 15곳 · 2층 3곳 · 3층 이상 0곳 · 층 미상 2곳 (10%)';
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow()], industryMix());
    // 나중에 등록한 것이 먼저 잡힌다 — mockFloorStack 의 '함수 없음' 위에 덮는다.
    await mockJson(page, INDUSTRY_DETAIL_PATTERN, {
      snapshot_ym: '202606',
      radius_m: 500,
      cat_l_cd: 'I2',
      districts: [
        {
          district_id: '3120189',
          name: '강남역',
          total: 60,
          cats: [
            { cd: 'I201', nm: '한식', n: 40 },
            { cd: 'I212', nm: '비알코올', n: 20 },
          ],
        },
      ],
      radius: { total: 150, cats: [{ cd: 'I201', nm: '한식', n: 100 }, { cd: 'I212', nm: '비알코올', n: 50 }] },
    });
    // ① 은 지금 분기(202606 — '지'를 아직 지하에 못 센 분기 · 물결 2-2c counted false)의 옛 문구를 본다.
    await mockIndustryFloors(page, false);

    const roleBtn = (name: string) => page.locator('.role').getByRole('button', { name, exact: true });
    const noOverflow = async () =>
      expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);

    // ① 역할 없이 — 대분류를 고르면 상권·반경 블록마다 한 줄 · 칩 줄 없음 · '층 미상' 설명 한 줄.
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    const mix = page.locator('section.mix');
    if ((await mix.locator('.card__toggle').getAttribute('aria-expanded')) === 'false') {
      await mix.locator('.card__toggle').click();
    }
    await expect(mix.locator('.mix__floors')).toHaveCount(0);
    await mix.locator('select.mix__select').selectOption('I2');
    await expect(mix.locator('.mix__detail .mix__floors')).toHaveText([LINE_D, LINE_R]);
    await expect(mix.locator('.mix__floors--chip')).toHaveCount(0);
    await expect(mix.locator('.mix__why li')).toHaveCount(3);
    await expect(mix.locator('.mix__why li').nth(2)).toContainText(
      "층 미상 — 원본에 층이 비어 있거나 숫자 없이 '지하'라고만 적힌 가게입니다",
    );
    await noOverflow();
    for (const el of await mix.locator('.mix__floors').all()) {
      expect(await el.evaluate((e) => e.scrollWidth - e.clientWidth)).toBeLessThanOrEqual(0);
    }

    // ①-2 물결 2-2c — '지'를 지하에 센 분기(counted true)면 설명이 새 두 항목(👤 2026-10-13 D2' 글자 그대로).
    //      나중에 등록한 목업이 먼저 잡힌다. 층 줄 꼴은 그대로다.
    await mockIndustryFloors(page, true);
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    if ((await mix.locator('.card__toggle').getAttribute('aria-expanded')) === 'false') {
      await mix.locator('.card__toggle').click();
    }
    await mix.locator('select.mix__select').selectOption('I2');
    await expect(mix.locator('.mix__detail .mix__floors')).toHaveText([LINE_D, LINE_R]);
    await expect(mix.locator('.mix__why li')).toHaveCount(4);
    await expect(mix.locator('.mix__why li').nth(2)).toHaveText('층 미상 — 원본에 층이 비어 있거나 읽을 수 없는 가게입니다.');
    await expect(mix.locator('.mix__why li').nth(3)).toHaveText(
      "지하 — 몇 층인지 없이 '지하'라고만 적힌 가게도 지하에 셉니다.",
    );
    await noOverflow();

    // ② 창업자 + 카페 칩 — 같은 대분류가 미리 골라지고 상권 블록에 '고른 업종(카페)' 줄이 하나 더(반경은 칩 0곳이라 없음).
    await page.goto('/');
    await gotoTab(page, '더보기'); // 휴대폰(W4a) — 역할 줄은 더보기 · 지도·칩은 지도 탭 · 검색은 찾기 탭
    await roleBtn('창업자').click();
    await gotoTab(page, '지도');
    await pickGu(page, '서울', '강남구');
    await page.locator('.dmap__head .chips').getByRole('button', { name: '카페', exact: true }).click();
    await gotoTab(page, '찾기');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(mix.locator('select.mix__select')).toHaveValue('I2');
    if ((await mix.locator('.card__toggle').getAttribute('aria-expanded')) === 'false') {
      await mix.locator('.card__toggle').click();
    }
    await expect(mix.locator('.mix__floors--chip')).toHaveText([CHIP_D]);
    await expect(mix.locator('.mix__detail .mix__floors:not(.mix__floors--chip)')).toHaveText([LINE_D, LINE_R]);
    await noOverflow();
    for (const el of await mix.locator('.mix__floors').all()) {
      expect(await el.evaluate((e) => e.scrollWidth - e.clientWidth)).toBeLessThanOrEqual(0);
    }
  });
});

// ── 개별공시지가 한 줄 (결정 0036 결정 7 · 물결 1-C1) ─────────────────────────
// 글·모양 검증·실패면 줄 없음은 단위 시험이 덮는다(`landPrice.test.ts`·`FloorStack.test.tsx`).
// 여기서만 보이는 것은 **진짜 브라우저에서 머리에 서는가**, 좁은 폭(412px)에서 넘치지 않는가,
// 종이에도 그대로 나오는가(내용이라 숨기지 않는다)다.

test.describe('층별 스택뷰 — 개별공시지가 한 줄', () => {
  test('AP. 값이 오면 사양 칸 아래 배지 + 한 줄 — 넘침 0 · 종이에도 그대로', async ({ page }) => {
    // 👤 2026-10-11 문구 · 금액은 가장 긴 꼴(1억 이상 '1억 8,840만원')로 좁은 폭을 시험한다.
    const TEXT = '개별공시지가 땅 1㎡당 1억 8,840만원 · 2026년 공시 (이 건물이 선 땅 · 공시가격 — 시세가 아닙니다)';
    const BADGE = 'A등급 · 공식 공시';
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()]);
    // 나중에 등록한 것이 먼저 잡힌다 — 기본(함수 없음)을 값으로 덮는다.
    const asked: unknown[] = [];
    await page.route(LAND_PRICE_PATTERN, async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: CORS_HEADERS });
        return;
      }
      asked.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: CORS_HEADERS,
        body: JSON.stringify([{ land_price: 188_400_000, land_price_year: 2026 }]),
      });
    });

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const line = page.locator('section.stack .stack__head .stack__land');
    await expect(line.locator('.stack__land-text')).toHaveText(TEXT);
    // 배지는 기준시가 줄과 같은 `grade__badge` 꼴 · 낱말은 '공시'(기준시가는 '고시').
    await expect(line.locator('.grade__badge')).toHaveText(BADGE);
    await expect(line).toHaveText(BADGE + TEXT);
    await expect(line).toBeVisible();
    // 사양 칸(dl) 바로 뒤에 선다.
    expect(
      await line.evaluate((e) => e.previousElementSibling?.classList.contains('stack__facts') ?? false),
    ).toBe(true);
    // 인자는 p_pnu(형제 기준시가와 같다 — 목은 인자 이름을 안 보므로 여기서 본다). 개발 서버는
    // StrictMode 라 effect 가 두 번 돌아 같은 요청이 두 번 나갈 수 있다(배포판은 한 번).
    expect(asked.length).toBeGreaterThan(0);
    expect(asked.every((a) => JSON.stringify(a) === JSON.stringify({ p_pnu: searchHit().pnu }))).toBe(true);
    // 좁은 폭에서도 줄 안·페이지 가로 넘침이 없다.
    expect(await line.evaluate((e) => e.scrollWidth - e.clientWidth)).toBeLessThanOrEqual(0);
    // 배지가 줄 상자 오른쪽 밖으로 삐져나가지 않는다(inline-block 이라 통째로 다음 줄로 내려가야 한다).
    expect(
      await line.evaluate((e) => {
        const b = e.querySelector('.grade__badge')!.getBoundingClientRect();
        return b.right - e.getBoundingClientRect().right;
      }),
    ).toBeLessThanOrEqual(0);
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);

    // 종이 — 내용이라 그대로 나온다(조종 장치처럼 빠지지 않는다).
    await page.emulateMedia({ media: 'print' });
    await expect(line).toBeVisible();
    await expect(line).toHaveText(BADGE + TEXT);
    await page.emulateMedia({ media: null });
  });
});

// ── 인쇄 한 장 보강 + 층별 공표값 (👤 결정 0036 결정 3·8·15 · 물결 1-C2 · 결정 0041) ─────────────────────────
// 저장 규칙·칸 모양·짝짓기는 단위 시험이 덮는다(`brokerOfficeStore.test`·`unitPrint.test`·`floorGap.test`·
// `App.test`·`FloorStack.test`). 여기서만 보이는 것은 **종이**(인쇄 시험 넷 — 결정 0036 「지키는 것」)와
// 좁은 폭(412px)에서 층별 공표값 카드가 넘치지 않는가다.

test.describe('종이 한 장 보강 — 사무소 칸 · 호실 구성표 · 층별 공표값', () => {
  /** 중개사로 저장해 두고(+ 최근 뽑은 건물 한 줄) 건물을 연다 — 저장은 진짜 브라우저 저장소. */
  async function openAsBroker(page: Page) {
    const { total_cnt: _t, ...recent } = searchHit({ bld_id: '1168010100100020000_1', pnu: '1168010100100020000', bld_nm: '옛빌딩' });
    void _t;
    await page.addInitScript((r) => {
      // ⚠️ 이 파일의 타입 검사는 브라우저 타입(DOM)을 안 켠다 — 전역을 좁은 모양으로 꺼내 쓴다(시험 T 와 같은 사정).
      type Kv = { getItem(k: string): string | null; setItem(k: string, v: string): void };
      const w = globalThis as unknown as { localStorage: Kv; sessionStorage: Kv };
      // 새로고침 때 다시 심지 않는다 — 시험 중 적은 칸이 새로고침 뒤에도 남는지 보려고.
      if (w.sessionStorage.getItem('__seeded')) return;
      w.sessionStorage.setItem('__seeded', '1');
      w.localStorage.setItem('sangga.viewerRole', '중개사');
      w.localStorage.setItem('sangga.recentPrinted', JSON.stringify([r]));
    }, recent);
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()]);
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).first().click();
    await expect(page.locator('section.stack')).toBeVisible();
  }

  test('AQ. 중개사 사무소 칸 — 비면 종이 머리 상자 없음 · 채우면 종이에만 · 칸·최근 줄은 종이에서 빠진다', async ({
    page,
  }, testInfo) => {
    await openAsBroker(page);
    const office = page.locator('details.office');
    const box = page.locator('.printmeta__office');
    await expect(office).toBeVisible();
    // 「최근 뽑은 건물」 줄은 검색창 안이다 — 건물을 열면 입구가 접히므로(S1) 펼쳐서 본다.
    // 휴대폰(W4a)은 검색 아래가 아니라 「뽑은 건물」 탭(👤 2번 「가」)이다.
    if (await isPhoneTabs(page)) await gotoTab(page, '뽑은 건물');
    else await unfoldEntry(page);
    await expect(page.locator('section.recent')).toBeVisible();

    // ① 칸이 비면 — 종이 머리 오른쪽 상자가 아예 없다.
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('.printmeta')).toBeVisible();
    await expect(box).toHaveCount(0);
    // ④ 입력 칸·고르기는 종이에서 빠진다 · (+) 1-A2(iii) 후속: 「최근 뽑은 건물」 줄도 빠진다.
    await expect(office).toBeHidden();
    await expect(page.locator('.unitpick')).toBeHidden();
    await expect(page.locator('section.recent')).toBeHidden();
    await page.emulateMedia({ media: null });
    await gotoTab(page, '건물'); // 사무소 칸은 건물 탭(가지고 나가기 줄)

    // ② 채우면 — 화면에서는 안 보이고(머리글째 화면에 없다) 종이에만 보인다 · 빈 칸은 줄째 빠진다.
    await office.locator('summary').click();
    await expect(office.getByText('이 기기에만 저장 · 서버로 보내지 않음')).toBeVisible();
    await expect(office.getByText('여럿이 함께 쓰는 컴퓨터라면 다 쓴 뒤 지우기를 눌러 주세요')).toBeVisible();
    await page.getByLabel('사무소 이름').fill('역삼공인중개사');
    await page.getByLabel('전화').fill('02-0000-0000');
    // 접힌 줄 제목에 채움 상태(접어 둬도 무엇이 찍힐지 보인다).
    await expect(office.locator('summary')).toHaveText('종이에 찍을 내 사무소 정보 — 채워짐(역삼공인중개사)');
    await expect(box).toHaveCount(1);
    await expect(box).toBeHidden();
    // 412px 에서도 입력 칸이 가로로 넘치지 않는다.
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    // 휴대폰(W4a · 결정 0039 §5 W4 줄)은 입력 칸 높이 44px 이상(171×29 였다) · 넓은 화면은 그대로(메인 판단 ⑥).
    const nameBox = (await page.getByLabel('사무소 이름').boundingBox())!;
    if (testInfo.project.name === 'mobile') expect(nameBox.height).toBeGreaterThanOrEqual(44);
    else expect(nameBox.height).toBeLessThan(44);

    await page.emulateMedia({ media: 'print' });
    await expect(box).toBeVisible();
    await expect(box.locator('p')).toHaveText(['역삼공인중개사', '전화 02-0000-0000']);
    // 구분선은 머리 전체 폭(상자가 서도 끊기지 않게) — 머리글이 갖고, 왼쪽 덩어리의 발 줄은 안 갖는다.
    await expect(page.locator('.printmeta')).toHaveCSS('border-bottom-style', 'solid');
    await expect(page.locator('.printmeta__foot')).toHaveCSS('border-bottom-style', 'none');
    await expect(office).toBeHidden();
    await page.locator('.printmeta').screenshot({ path: testInfo.outputPath(`c2-office-print-${testInfo.project.name}.png`) });
    await page.emulateMedia({ media: null });

    // 새로고침 뒤에도 남는다(이 기기 저장) · 주소에는 sgg·bld 둘뿐.
    expect([...new URL(page.url()).searchParams.keys()].sort()).toEqual(['bld', 'sgg']);
    await page.reload();
    await expect(page.locator('section.stack')).toBeVisible();
    await expect(page.getByLabel('사무소 이름')).toHaveValue('역삼공인중개사');
  });

  test('AR. 호실 구성표 「지하~3층」·「전부」가 각각 종이(와 화면)에 그 층 호 목록 줄로 · 고르기 자체는 종이에서 빠진다', async ({
    page,
  }, testInfo) => {
    const unitRequests: Array<Record<string, unknown>> = [];
    page.on('request', (r) => {
      if (r.method() === 'POST' && r.url().includes('/rpc/list_floor_units')) {
        unitRequests.push((r.postDataJSON() ?? {}) as Record<string, unknown>);
      }
    });
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [
      floorRow({ floor_no: 35, main_use: '아파트' }),
      floorRow({ floor_no: 5 }),
      floorRow({ floor_no: 4 }),
      floorRow({ floor_no: 3 }),
      floorRow({ floor_no: 1 }),
      floorRow({ floor_no: -1 }),
    ]);
    const kind = (floor_no: number, floor_kind: string) => ({
      floor_no, unit_cnt: 543, median_area_m2: null, min_area_m2: null, max_area_m2: null, floor_kind,
    });
    await mockJson(page, UNIT_SUMMARY_PATTERN, [
      kind(35, 'residential'), kind(5, 'commercial'), kind(4, 'commercial'), kind(3, 'mixed'), kind(1, 'commercial'),
      kind(-1, 'commercial'),
    ]);
    await page.route(FLOOR_UNITS_PATTERN, async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: CORS_HEADERS });
        return;
      }
      const args = (route.request().postDataJSON() ?? {}) as Record<string, number>;
      // 4층 목록만 서버 오류 — 그 층만 빠지고 다 끝난 뒤 못 받은 층 수 한 줄(화면·종이)이 서는지 본다.
      if (args.p_floor_no === 4) {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          headers: CORS_HEADERS,
          body: JSON.stringify({ code: 'XX000', message: 'boom', details: null, hint: null }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: CORS_HEADERS,
        body: JSON.stringify(floorUnitsPage(args.p_offset ?? 0, args.p_limit ?? 50)),
      });
    });
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack')).toBeVisible();

    const card = page.locator('.card--floors');
    const listOf = (no: number) => card.locator(`#floor-${no} .floor__unitprint-list li`);
    const pick = page.locator('.unitpick');
    // 기본 = 지하~3층(👤 2026-10-11 · 결정 8 원문) — 건물을 열자마자 화면에서도 지하 1층·1층·3층 아래에
    // 50호씩 + 남은 수 한 줄(5층·35층은 없다). 받는 동안의 「불러오는 중」 줄은 다 받으면 사라진다.
    await expect(pick.getByLabel('지하~3층')).toBeChecked();
    for (const no of [-1, 1, 3]) await expect(listOf(no)).toHaveCount(50);
    await expect(card.locator('.floor__unitprint-loading')).toHaveCount(0);
    await expect(card.locator('#floor-5 .floor__unitprint')).toHaveCount(0);
    await expect(card.locator('#floor-3 .floor__unitprint-more')).toHaveText('이 층은 493호 더 있습니다');
    await expect(card.locator('.floor__unitprint-failed')).toHaveCount(0);

    await page.emulateMedia({ media: 'print' });
    await expect(pick).toBeHidden();
    await expect(listOf(-1).first()).toBeVisible();
    await expect(listOf(3).nth(49)).toBeVisible();
    await expect(card.locator('#floor-3 .floor__unitprint-more')).toBeVisible();
    // 줄 단위로 끊는다 — 고른 층은 통째 avoid 가 아니고, 호 줄 하나하나는 avoid.
    await expect(card.locator('#floor-3')).toHaveCSS('break-inside', 'auto');
    await expect(listOf(3).first()).toHaveCSS('break-inside', 'avoid');
    await card.screenshot({ path: testInfo.outputPath(`c2-units-low-print-${testInfo.project.name}.png`) });
    await page.emulateMedia({ media: null });

    // 전부 — 5층까지(아래층부터) · 주거 35층은 여전히 없다 · 서버 오류 난 4층만 빠지고 그 수 한 줄.
    const failed = card.locator('.floor__unitprint-failed');
    await pick.getByLabel('전부').check();
    await expect(listOf(5)).toHaveCount(50);
    await expect(failed).toHaveText('1개 층은 호실 목록을 못 불러왔습니다');
    await expect(listOf(4)).toHaveCount(0);
    await page.emulateMedia({ media: 'print' });
    await expect(listOf(5).first()).toBeVisible();
    await expect(card.locator('#floor-35 .floor__unitprint')).toHaveCount(0);
    // 못 받은 층 수 줄은 종이에도 남는다(👤 2026-10-11 — 빠진 층이 있다는 것을 종이를 받는 사람도 안다).
    await expect(failed).toBeVisible();
    await page.emulateMedia({ media: null });

    // 넣지 않음 — 화면·종이 모두 목록이 빠진다(선택지로 남는다) · 못 받은 층 줄도 같이 빠진다.
    await pick.getByLabel('넣지 않음').check();
    await expect(card.locator('.floor__unitprint')).toHaveCount(0);
    await expect(failed).toHaveCount(0);
    await page.emulateMedia({ media: 'print' });
    await expect(card.locator('.floor__unitprint')).toHaveCount(0);
    await page.emulateMedia({ media: null });

    // ⛔ 주거 층은 요청조차 안 나간다 · 늘 첫 쪽(offset 0, 50).
    expect(unitRequests.some((a) => a.p_floor_no === 35)).toBe(false);
    expect(unitRequests.every((a) => a.p_offset === 0 && a.p_limit === 50)).toBe(true);
    expect([...new Set(unitRequests.map((a) => a.p_floor_no))].sort()).toEqual([-1, 1, 3, 4, 5]);
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
  });

  test('AS. 층별 공표값 나란히 — 접힌 카드로 서고 펼치면 층마다 세 값(기준시가 칸에 호 수·고시일) · 412px 넘침 0 · 종이에서는 줄 단위', async ({
    page,
  }, testInfo) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(
      page,
      [],
      [floorRow({ floor_no: 2 }), floorRow(), floorRow({ floor_no: -1 })],
      undefined,
      basePrices(),
      undefined,
      [rentStat()],
    );
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const gap = page.locator('section.card--floorgap');
    await expect(gap.locator('.card__toggle')).toHaveAttribute('aria-expanded', 'false');
    await expect(gap.locator('.card__summary')).toHaveText('국세청 기준시가 · 구 상가 단가 · 부동산원 임대료 — 층마다 나란히');
    // 자리 = 실거래 기록 바로 뒤(역할 없음 · 결정 0041 — 내린 참고 매매 시세의 자리).
    const titles = await page.locator('section.stack .card .card__title').allTextContents();
    expect(titles[titles.indexOf('층별 공표값 나란히 — 국세청 기준시가 · 구 상가 단가 · 부동산원 임대료') - 1]).toBe('실거래 기록');

    await openCard(page, /층별 공표값 나란히/);
    const val = (no: number, k: string) => gap.locator(`.gap__row[data-floor="${no}"] .gap__cell--${k} .gap__val`);
    await expect(val(1, 'base')).toHaveText('410만');
    // 기준시가 칸 작은 글 = 호 수 · 고시일(결정 0041 ㉤).
    await expect(gap.locator('.gap__row[data-floor="1"] .gap__cell--base .gap__sub')).toHaveText('(호 12개 가운데값 · 2026년 1월 1일 고시)');
    await expect(val(1, 'tx')).toHaveText('㎡당 2,250만');
    await expect(val(1, 'rent')).toHaveText('74.6');
    await expect(val(2, 'tx')).toHaveText('표본 부족 (0건)');
    await expect(val(-1, 'rent')).toHaveText('16.95');
    await expect(gap.locator('.gap__row[data-floor="-1"] .gap__cell--rent .gap__sub')).toHaveText(' (상권 평균 · 지하 1층)');
    await expect(val(-1, 'base')).toHaveText('–');
    await expect(gap.locator('.gap__head--rent')).toContainText('서울>강남>테헤란로 집합상가 평균 — 이 건물 값 아님');
    await expect(gap).toContainText('서로 나누거나 비율을 계산하지 않았습니다');
    await expect(gap).not.toContainText('%');
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    for (const el of await gap.locator('.gap__row').all()) {
      expect(await el.evaluate((e) => e.scrollWidth - e.clientWidth)).toBeLessThanOrEqual(0);
    }
    await gap.screenshot({ path: testInfo.outputPath(`c2-gap-${testInfo.project.name}.png`) });

    await page.emulateMedia({ media: 'print' });
    await expect(gap.locator('.gap__row').first()).toHaveCSS('break-inside', 'avoid');
    await expect(gap).not.toHaveCSS('break-inside', 'avoid');
    await page.emulateMedia({ media: null });
  });
});

// ── 승강기·구조·내진·대장 호수 (물결 2-1 PR② · 👤 2026-10-11~12) ─────────────────────────────
// 칸마다의 경계(undefined/null/0/양수 · 비상용>승용 · 일반건물)는 단위 시험이 덮는다(`format.test`·`FloorStack.test`).
// 여기서는 진짜 화면에서 칸 자리(주차 바로 뒤)·좁은 폭 넘침·**종이**(인쇄 매체)에 새 칸이 그대로 나오는지를 본다.

test.describe('건물 머리 새 칸 — 구조 · 승강기 · 내진설계 · 대장 호수', () => {
  test('AT. 새 칸이 다 오면 주차 바로 뒤 네 칸 · 412px 넘침 0 · 종이에도 그대로', async ({ page }) => {
    const spec = {
      strct_nm: '철근콘크리트구조',
      elevator_ride: 2,
      elevator_emgen: 1,
      seismic_design: true,
      ho_cnt: 48,
      // 건물 주용도 — 주거(공동주택·단독주택)가 아니어야 대장 호수가 선다(👤 결정 B).
      bld_main_use: '제2종근린생활시설',
    };
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2, ...spec }), floorRow(spec)]);
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const facts = page.locator('section.stack .stack__facts');
    const cell = (label: string) => facts.locator('div').filter({ has: page.locator('dt', { hasText: new RegExp(`^${label}$`) }) });
    const expected: [string, string][] = [
      ['구조', '철근콘크리트구조'],
      ['승강기', '3대 (비상용 1대 포함)'],
      ['내진설계', '적용'],
      ['대장 호수', '48호'],
    ];
    for (const [label, value] of expected) {
      await expect(cell(label).locator('dd')).toHaveText(value);
    }
    const labels = await facts.locator('dt').allTextContents();
    const at = labels.indexOf('주차');
    expect(labels.slice(at, at + 5)).toEqual(['주차', '구조', '승강기', '내진설계', '대장 호수']);
    expect(await facts.evaluate((e) => e.scrollWidth - e.clientWidth)).toBeLessThanOrEqual(0);
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);

    // 종이 — 머리 칸은 내용이라 그대로 나온다(`.stack__head` 안).
    await page.emulateMedia({ media: 'print' });
    for (const [label, value] of expected) {
      await expect(cell(label)).toBeVisible();
      await expect(cell(label).locator('dd')).toHaveText(value);
    }
    await page.emulateMedia({ media: null });
  });

  test('AU. 일반건물·0 인 지상 6층 건물 — 내진설계·대장 호수 칸 없음 · 구조·승강기는 미상', async ({ page }) => {
    const spec = {
      is_jiphap: false,
      strct_nm: null,
      elevator_ride: 0,
      elevator_emgen: 0,
      seismic_design: false,
      ho_cnt: 0,
      bld_main_use: '업무시설',
    };
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    // 지상 6층 — 승강기 합 0 이 '미상'으로 서는 경계(👤 결정 A · 5층 이하면 칸 없음은 AV).
    await mockFloorStack(page, [], [6, 5, 4, 3, 2, 1].map((no) => floorRow({ floor_no: no, ...spec })));
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const facts = page.locator('section.stack .stack__facts');
    const cell = (label: string) => facts.locator('div').filter({ has: page.locator('dt', { hasText: new RegExp(`^${label}$`) }) });
    await expect(cell('건물 종류').locator('dd')).toHaveText('일반건물');
    await expect(cell('구조').locator('dd')).toHaveText('미상');
    await expect(cell('승강기').locator('dd')).toHaveText('미상');
    await expect(cell('내진설계')).toHaveCount(0);
    await expect(cell('대장 호수')).toHaveCount(0);
    for (const bad of ['0대', '0호', '미적용']) {
      await expect(facts).not.toContainText(bad);
    }
  });

  test('AV. 지상 5층 공동주택(집합·호수 48) — 승강기 0 이면 승강기 칸 없음 · 주거라 대장 호수 칸 없음 · 종이도 같다', async ({
    page,
  }) => {
    const spec = {
      is_jiphap: true,
      strct_nm: '철근콘크리트구조',
      elevator_ride: 0,
      elevator_emgen: 0,
      seismic_design: true,
      ho_cnt: 48,
      bld_main_use: '공동주택',
    };
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    // 지하 1 + 지상 5 + 옥탑 — 행은 7개지만 지상 최고층은 5(옥탑·지하는 안 센다).
    await mockFloorStack(page, [], [99, 5, 4, 3, 2, 1, -1].map((no) => floorRow({ floor_no: no, ...spec })));
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const facts = page.locator('section.stack .stack__facts');
    const cell = (label: string) => facts.locator('div').filter({ has: page.locator('dt', { hasText: new RegExp(`^${label}$`) }) });
    // 양성 대조: 같은 머리의 다른 새 칸은 선다(칸이 통째로 안 그려진 것이 아니다).
    await expect(cell('구조').locator('dd')).toHaveText('철근콘크리트구조');
    await expect(cell('내진설계').locator('dd')).toHaveText('적용');
    await expect(cell('승강기')).toHaveCount(0);
    await expect(cell('대장 호수')).toHaveCount(0);
    await expect(facts).not.toContainText('미상');

    await page.emulateMedia({ media: 'print' });
    await expect(cell('구조')).toBeVisible();
    await expect(cell('승강기')).toHaveCount(0);
    await expect(cell('대장 호수')).toHaveCount(0);
    await page.emulateMedia({ media: null });
  });
});

// ── 업종 비중 비교 (물결 2-3 · 결정 0036 결정 18 ㉓~㉖) ─────────────────────────
// 글·모양 검증·실패면 비교 글 0·늦은 답 버림은 단위 시험이 덮는다(`industryMix.test.ts`·`IndustryMixSection.test.tsx`).
// 여기서만 보이는 것은 **진짜 브라우저에서 상권 블록 줄 아래에 서는가**, 좁은 폭(412px)에서 넘치지 않는가,
// 종이에도 그대로 나오는가(내용이라 숨기지 않는다)다.

test.describe('층별 스택뷰 — 업종 비중 비교', () => {
  test('AW. 상권 블록 줄마다 「서울 골목상권 가운데 25.0%」 · 배지 C 설명 줄 · 30곳 미만 상권은 사실 한 줄 · 반경엔 없음 · 412px 넘침 0 · 종이에도', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow()], industryMixTwoDistricts());
    // 나중에 등록한 것이 먼저 잡힌다 — mockFloorStack 의 '함수 없음' 위에 덮는다.
    // 받은 요청 주소를 모은다(⑥) — 이 처리기가 중분류 함수 요청까지 잡으면 대분류 패턴이 넓어진 것이다.
    const medianUrls: string[] = [];
    await page.route(INDUSTRY_MEDIAN_PATTERN, async (route) => {
      medianUrls.push(route.request().url());
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: CORS_HEADERS });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: CORS_HEADERS,
        body: JSON.stringify(industryMedian()),
      });
    });

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    const mix = page.locator('section.mix');
    if ((await mix.locator('.card__toggle').getAttribute('aria-expanded')) === 'false') {
      await mix.locator('.card__toggle').click();
    }
    const block = (heading: string) => mix.locator('.mix__block').filter({ has: page.getByRole('heading', { name: heading }) });
    const gol = block('역삼골목(골목상권) 안 215곳');
    const market = block('역삼시장(전통시장) 안 12곳');
    const radius = block('반경 500m 안 200곳');

    // ① 골목 — 줄마다 비교 글(막대 차례 그대로 · 같은 li 안) + 블록 머리 아래 배지 C 설명 줄.
    await expect(gol.locator('.mix__med')).toHaveText(['서울 골목상권 가운데 25.0%', '서울 골목상권 가운데 19.3%']);
    await expect(gol.locator('.mix__bars li').first().locator('.mix__med')).toHaveText('서울 골목상권 가운데 25.0%');
    await expect(gol.locator('.mix__med-note .grade__badge--est')).toHaveText('C등급 · 비교값');
    await expect(gol.locator('.mix__med-note')).toHaveText(
      'C등급 · 비교값가운데값은 서울 골목상권 999곳(점포 30곳 이상 상권)의 업종 비중을 크기순으로 세웠을 때 한가운데 값입니다 — 비교용 숫자입니다.',
    );
    // ② 전통시장(점포 12곳) — 비교값 대신 사실 한 줄 · 줄마다 비교 글 0.
    await expect(market.locator('.mix__med-note')).toHaveText(['점포 12곳 — 30곳이 안 돼 비교값은 적지 않습니다.']);
    await expect(market.locator('.mix__med')).toHaveCount(0);
    // ③ 반경 블록엔 견줄 상대가 없다.
    await expect(radius).toHaveCount(1);
    await expect(radius).not.toContainText('가운데');
    await expect(radius.locator('.mix__med, .mix__med-note')).toHaveCount(0);
    // 판단 낱말 0(숫자만 나란히 — 👤 ㉕).
    for (const t of await mix.locator('.mix__med, .mix__med-note').allTextContents()) {
      expect(t).not.toMatch(/많|적다|적습|높|낮|%p|배/);
    }

    // ④ 412px — 페이지·줄 각각 넘침 0.
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    for (const el of await mix.locator('.mix__med, .mix__med-note, .mix__bars li').all()) {
      expect(await el.evaluate((e) => e.scrollWidth - e.clientWidth)).toBeLessThanOrEqual(0);
    }

    // ⑤ 종이에도 그대로(내용이라 숨기지 않는다).
    await page.emulateMedia({ media: 'print' });
    await expect(gol.locator('.mix__med').first()).toBeVisible();
    await expect(gol.locator('.mix__med-note')).toBeVisible();
    await expect(market.locator('.mix__med-note')).toBeVisible();
    await page.emulateMedia({ media: null });

    // ⑥ 대분류 목업 패턴은 대분류 함수만 잡는다 — 대분류를 골라 중분류 함수 요청을 실제로 내보낸 뒤(그 응답까지 기다린다 ·
    //    기본 '함수 없음' 목업이 답한다), 위 처리기가 받은 주소가 전부 `/rpc/list_industry_median` 로 끝나는지 본다.
    //    패턴 끝에 `*` 를 붙이면(INDUSTRY_MEDIAN_PATTERN 주석의 ⛔) 중분류 요청이 이 처리기로 와 빨강.
    const medianMAnswered = page.waitForResponse(
      (r) => r.url().endsWith('/rpc/list_industry_median_m') && r.request().method() === 'POST',
    );
    await mix.locator('select.mix__select').selectOption('I2');
    await medianMAnswered;
    expect(medianUrls.length).toBeGreaterThan(0);
    for (const url of medianUrls) expect(url).toMatch(/\/rpc\/list_industry_median$/);
  });
});

// ── 업종 비중 비교 · 중분류 (물결 2-3b · 결정 0036 결정 18 ㉗~㉚) ─────────────────────
// 글·모양 검증·실패면 글 0·늦은 답 버리기는 단위 시험이 덮는다(`industryMix.test.ts`·`IndustryMixSection.test.tsx`).
// 여기서만 보이는 것은 진짜 브라우저에서 대분류를 고른 뒤 **상세의 상권 블록**에 서는가, 반경 블록엔 없는가,
// 412px 에서 넘치지 않는가, 종이에도 그대로 나오는가다.

test.describe('층별 스택뷰 — 업종 비중 비교 · 중분류', () => {
  test('AX. 대분류를 고르면 상세 상권 블록 중분류 줄마다 「서울 골목상권 가운데 15.2%」 · 배지 C 설명 줄 · 30곳 미만 상권은 사실 한 줄 · 반경엔 없음 · 412px 넘침 0 · 종이에도', async ({
    page,
  }) => {
    const NOTE =
      'C등급 · 비교값가운데값은 서울 골목상권 가운데 음식 가게가 30곳 이상인 526곳의 음식 안 업종 비중을 크기순으로 세웠을 때 한가운데 값입니다 — 비교용 숫자입니다.';
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow()], industryMixTwoDistricts());
    // 나중에 등록한 것이 먼저 잡힌다 — mockFloorStack 의 '함수 없음' 위에 덮는다.
    await mockJson(page, INDUSTRY_DETAIL_PATTERN, industryDetailTwoDistricts());
    const asked: unknown[] = [];
    await page.route(INDUSTRY_MEDIAN_M_PATTERN, async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: CORS_HEADERS });
        return;
      }
      asked.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: CORS_HEADERS,
        body: JSON.stringify(industryMedianM()),
      });
    });

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    const mix = page.locator('section.mix');
    if ((await mix.locator('.card__toggle').getAttribute('aria-expanded')) === 'false') {
      await mix.locator('.card__toggle').click();
    }
    // 고르기 전에는 묻지도 않는다(따로 부름) · 대분류 블록엔 대분류 비교 함수가 없어(기본 목업) 비교 글 0.
    await expect(mix.locator('.mix__detail')).toHaveCount(0);
    expect(asked).toHaveLength(0);
    await mix.locator('select.mix__select').selectOption('I2');

    const detail = mix.locator('.mix__detail');
    const block = (heading: string) =>
      detail.locator('.mix__block').filter({ has: page.getByRole('heading', { name: heading }) });
    const gol = block('역삼골목(골목상권) 안 음식 120곳');
    const market = block('역삼시장(전통시장) 안 음식 7곳');
    const radius = block('반경 500m 안 음식 150곳');

    // ① 골목 — 중분류 줄마다 비교 글(막대 차례 그대로 · 같은 li 안) + 블록 머리 아래 배지 C 설명 줄.
    await expect(gol.locator('.mix__med')).toHaveText([
      '서울 골목상권 가운데 38.1%',
      '서울 골목상권 가운데 15.2%',
      '서울 골목상권 가운데 20.6%',
      '서울 골목상권 가운데 9.8%',
    ]);
    // 카페(비알코올) 줄 — 막대는 대분류 안 몫 21.7%(26/120 · 👤 ㉘), 둘째 줄은 가운데값.
    const cafe = gol.locator('.mix__bars li').filter({ hasText: '비알코올' });
    await expect(cafe.locator('.mix__pct')).toHaveText('21.7%');
    await expect(cafe.locator('.mix__med')).toHaveText('서울 골목상권 가운데 15.2%');
    await expect(gol.locator('.mix__med-note .grade__badge--est')).toHaveText('C등급 · 비교값');
    await expect(gol.locator('.mix__med-note')).toHaveText(NOTE);
    // ② 전통시장(음식 7곳) — 비교값 대신 사실 한 줄 · 줄마다 비교 글 0.
    await expect(market.locator('.mix__med-note')).toHaveText(['음식 7곳 — 30곳이 안 돼 비교값은 적지 않습니다.']);
    await expect(market.locator('.mix__med')).toHaveCount(0);
    // ③ 반경 블록엔 견줄 상대가 없다.
    await expect(radius).toHaveCount(1);
    await expect(radius).not.toContainText('가운데');
    await expect(radius.locator('.mix__med, .mix__med-note')).toHaveCount(0);
    // 판단 낱말 0(숫자만 나란히 — 👤 ㉚ 어제 틀 그대로).
    for (const t of await detail.locator('.mix__med, .mix__med-note').allTextContents()) {
      expect(t).not.toMatch(/많|적다|적습|높|낮|%p|배/);
    }
    // 인자는 { p_pnu, p_cat_l } — 대분류를 고른 뒤 한 번(개발 서버 StrictMode 라 두 번 나갈 수 있어 개수는 안 본다).
    expect(asked[0]).toEqual({ p_pnu: searchHit().pnu, p_cat_l: 'I2' });

    // ④ 412px — 페이지·줄 각각 넘침 0.
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    for (const el of await detail.locator('.mix__med, .mix__med-note, .mix__bars li').all()) {
      expect(await el.evaluate((e) => e.scrollWidth - e.clientWidth)).toBeLessThanOrEqual(0);
    }

    // ⑤ 종이에도 그대로(내용이라 숨기지 않는다).
    await page.emulateMedia({ media: 'print' });
    await expect(gol.locator('.mix__med').first()).toBeVisible();
    await expect(gol.locator('.mix__med-note')).toBeVisible();
    await expect(market.locator('.mix__med-note')).toBeVisible();
    await page.emulateMedia({ media: null });
  });
});

// ── 입구 접기 (S1 · 👤 2026-10-14·15 · 시안 Qjdr1GXX) ─────────────────────────────────────
// 접힘·펼침·새 건물에 다시 접힘·검색어 보존은 단위 시험(`App.test.tsx` 「입구 접기 (S1)」)이 덮는다.
// 여기서만 보이는 것은 **실제 배치**(건물 이름이 첫 화면 높이 안에 오나 · 바 단추가 44px 인가 · 좁은 폭에서 안 넘치나)와 종이다.

test.describe('첫 화면 — 건물을 열면 입구가 한 줄로 접힌다', () => {
  test('AY. 검색으로 연 건물 이름이 첫 화면 높이 안에 · 바 단추 44px · 펼치면 입력칸에 커서 · 접힌 지도는 종이에 없고 펼친 지도는 종이에 나온다', { tag: '@onecol' }, async ({
    page,
  }) => {
    // 폭은 프로젝트가 정한다(W5 보완 F5) — 한 열 S1 은 desktop-1000(1000×768 · 태그 @onecol) · 두 칸은 chromium(1280×720) ·
    //   휴대폰은 Pixel 7 프리셋(412×839). 1366×768 두 칸에서 건물 이름이 첫 화면 안인지는 BV 가 잰다.
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()]);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    const head = page.locator('.stack__head');
    await expect(head.getByRole('heading', { name: '테스트빌딩' })).toBeVisible();

    // ① 건물 이름이 문서 맨 위에서 첫 화면 높이 안에 — 맨 위에서 스크롤 없이 보인다
    //    (접기 전에는 역할·지역 칩·검색 결과·지도 아래로 밀려 있었다 — 접기 전 코드로 돌리면 이 줄이 빨강).
    //    ⓘ 결과 줄을 누를 때 화면이 움직였을 수 있어 화면 안 위치가 아니라 **문서 위치**(+ scrollY)로 잰다.
    //    ⓘ 이 파일의 타입 검사는 브라우저 타입(DOM)을 안 켠다 — 전역을 좁은 모양으로 꺼내 쓴다(시험 T 와 같은 사정).
    const vh = page.viewportSize()!.height;
    const title = (await head.getByRole('heading', { name: '테스트빌딩' }).boundingBox())!;
    const docBottom = title.y + title.height + (await page.evaluate(() => (globalThis as unknown as { scrollY: number }).scrollY));
    expect(docBottom).toBeLessThanOrEqual(vh);

    if (await isPhoneTabs(page)) {
      // 휴대폰(결정 0039 W4a)은 한 줄 바 대신 아래 탭 — 건물 탭 · 위 덩어리 숨김 · 지도 안 그림 · 소개 줄 숨김.
      await expect(page.locator('.entrybar')).toHaveCount(0);
      await expect(tabButton(page, '건물')).toHaveAttribute('aria-current', 'page');
      await expect(page.locator('.region')).toBeHidden();
      await expect(page.locator('.search')).toBeHidden();
      await expect(page.locator('section.dmap')).toHaveCount(0);
      await expect(page.locator('.app__sub')).toBeHidden();
      // 지도 탭에서 뽑아도 종이 = 건물 한 장(👤 「건물 한 장」 — 그 탭이 그린 지도는 종이에서 빠진다).
      await gotoTab(page, '지도');
      await expect(page.locator('section.dmap')).toBeVisible();
      await page.emulateMedia({ media: 'print' });
      await expect(page.locator('section.dmap')).toBeHidden();
      await expect(page.locator('nav.tabbar')).toBeHidden();
      await expect(page.locator('.printmeta')).toBeVisible();
      await expect(head.getByRole('heading', { name: '테스트빌딩' })).toBeVisible();
      await page.emulateMedia({ media: null });
      return;
    }

    if (await isTwoCols(page)) {
      // PC 두 칸(W5 · Q5)은 바가 없고 왼쪽 칸(검색·지도)이 그대로 선다 · 소개 한 줄은 건물을 연 동안 빠진다(머리 작게).
      await expect(page.locator('.entrybar')).toHaveCount(0);
      await expect(page.locator('.search')).toBeVisible();
      await expect(page.locator('section.dmap')).toBeVisible();
      await expect(page.locator('.app__sub')).toBeHidden();
      // 종이 — 「상권 지도 넣기」를 안 켰으면 건물만(왼쪽 칸째 빠짐 · 켠 종이는 BW).
      await page.emulateMedia({ media: 'print' });
      await expect(page.locator('section.dmap')).toBeHidden();
      await expect(page.locator('.printmeta')).toBeVisible();
      await expect(head.getByRole('heading', { name: '테스트빌딩' })).toBeVisible();
      await page.emulateMedia({ media: null });
      return;
    }

    // ② 한 줄 바 — 지금 구 · 단추 셋(높이 44px 이상) · 위 덩어리는 숨고 지도는 안 그린다.
    const bar = page.locator('.entrybar');
    await expect(bar.locator('.entrybar__place')).toHaveText('서울 강남구');
    await expect(bar.getByRole('button')).toHaveText(['← 다른 건물 찾기', '상권 지도 보기', '나는 역할 고르기 ▾']);
    for (const btn of await bar.getByRole('button').all()) {
      expect((await btn.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
    await expect(page.locator('.role')).toBeHidden();
    await expect(page.locator('.region')).toBeHidden();
    await expect(page.locator('.search')).toBeHidden();
    await expect(page.locator('section.dmap')).toHaveCount(0);
    // 소개 한 줄도 접힌 동안 빠진다(제목만 작게 남는다) — 펼치면 다시 보인다(아래 ④에서 대조).
    await expect(page.locator('.app__sub')).toBeHidden();
    // 좁은 폭(412px)에서도 바가 옆으로 넘치지 않는다.
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);

    // ③ 접힌 채 종이 — 바는 빠지고 지도도 없다(👤 10-15) · 종이 머리글은 그대로.
    await page.emulateMedia({ media: 'print' });
    await expect(bar).toBeHidden();
    await expect(page.locator('section.dmap')).toHaveCount(0);
    await expect(page.locator('.printmeta')).toBeVisible();
    await page.emulateMedia({ media: null });

    // ④ 「다른 건물 찾기」 — 검색창이 펼쳐지고 입력칸에 커서 · 보던 건물은 아래 그대로 · 「위 칸 접기」로 다시 한 줄.
    await unfoldEntry(page);
    await expect(page.getByLabel('건물명 또는 주소')).toBeFocused();
    await expect(head).toBeVisible();
    await expect(page.locator('.app__sub')).toBeVisible();
    const fold = page.getByRole('button', { name: '위 칸 접기' });
    expect((await fold.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await fold.click();
    await expect(page.locator('.search')).toBeHidden();
    await expect(bar).toHaveCount(1);

    // ⑤ 「상권 지도 보기」로 펼친 채 뽑으면 지도가 종이에 나온다(지금처럼) · 접기 단추는 빠진다.
    await unfoldEntry(page, '상권 지도 보기');
    await expect(page.locator('section.dmap')).toBeVisible();
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('section.dmap')).toBeVisible();
    await expect(page.locator('.entrybar')).toBeHidden();
    await expect(page.locator('.dmap__toggle')).toBeHidden();
    await page.emulateMedia({ media: null });
  });
});

// ── 누르는 것 44px · 글자 13px (S4 · 👤 2026-10-14) ───────────────────────────────────────────
// styles.css 의 `@media screen` 두 묶음(글자 13px · 누르는 것 44px)을 지키는 시험. 새 단추·새 글자 칸이 묶음에서 빠지면 여기서 빨강.
// 재는 것: 보이는 단추·펼침 머리(summary)·고르개(select)·입력칸·라디오/체크 이름표 + **따로 서 있는 링크 줄**(넘기기 링크
// `.links__a` · 형제 사이트 `.family__a`). ⛔ 문장 속 링크(글 안의 `a`)는 재지 않는다 — 글 줄 높이가 곧 링크 높이라 44px 를
// 주면 문단이 벌어진다(지시서 S4-1 "문장 속 글자 링크는 제외"). 글자는 글자를 직접 담은 보이는 요소 전부.

/**
 * 지금 화면에서 44px 미만 누르는 것 · 13px 미만 글자를 이름별로 센다(브라우저 안에서 잰다).
 * ⓘ 이 파일의 타입 검사는 브라우저 타입(DOM)을 안 켠다 — 그래서 잴 코드를 **글자로** 넘긴다(브라우저에서만 돈다).
 */
const MEASURE_TARGETS_JS = `(() => {
  const vis = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
  };
  const name = (el) => el.tagName.toLowerCase() + '.' + [...el.classList].join('.');
  const sel =
    'button, summary, select, input:not([type=hidden]):not([type=radio]):not([type=checkbox]), ' +
    'label:has(input[type=radio]), label:has(input[type=checkbox]), a.links__a, a.family__a, ' +
    // 결정 0042 — 구 칩은 단추에서 진짜 링크로(역할은 단추) · 층별 머리의 내부 링크 줄도 누르는 것이다.
    'a.region__gu-chip, a.stack__links-a';
  const small = [];
  const narrow = [];
  let targets = 0;
  for (const el of document.querySelectorAll(sel)) {
    if (!vis(el)) continue;
    targets += 1;
    const r = el.getBoundingClientRect();
    if (r.height < 44 - 0.01) small.push(name(el) + ' ' + Math.round(r.height) + 'px');
    if (r.width < 44 - 0.01) narrow.push(name(el) + ' ' + Math.round(r.width) + 'px');
  }
  const tiny = [];
  let texts = 0;
  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el)) continue;
    if (![...el.childNodes].some((c) => c.nodeType === 3 && (c.textContent || '').trim())) continue;
    texts += 1;
    let fs = parseFloat(getComputedStyle(el).fontSize);
    // 글을 0 크기로 두고 ::before 로 다시 쓰는 칸(휴대폰 「같은 땅 다른 동」 · 10-19 U1)은 눈에 보이는 글 = ::before 의 글자 크기.
    const before = getComputedStyle(el, '::before');
    if (fs === 0 && before.content !== 'none') fs = parseFloat(before.fontSize);
    if (fs < 13 - 0.01) tiny.push(name(el) + ' ' + fs + 'px');
  }
  return { targets, small, narrow, texts, tiny };
})()`;

async function measureTargets(page: Page) {
  return (await page.evaluate(MEASURE_TARGETS_JS)) as {
    targets: number;
    small: string[];
    narrow: string[];
    texts: number;
    tiny: string[];
  };
}

test.describe('누르는 것 44px · 글자 13px', () => {
  test('AZ. 건물 화면의 누르는 것은 44px 이상 · 글자는 13px 이상(기본 · 카드 다 펼침) — 종이에서는 이 높이가 안 먹는다', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    await mockJson(page, DATA_FRESHNESS_PATTERN, dataFreshness());
    // 같은 땅 2동(결정 0042 보완 F6) — 머리 링크 줄에 2글자 동 링크 「A동」(이름 없음)이 서게 해 그 폭·높이도 잰다.
    await mockJson(page, SEARCH_PATTERN, [searchHit({ bld_cnt_in_pnu: 2 })]);
    await mockFloorStack(
      page,
      [parcelTx()],
      [floorRow({ floor_no: 2, bld_cnt_in_pnu: 2 }), floorRow({ bld_cnt_in_pnu: 2 })],
      industryMix(),
      undefined,
      undefined,
      rentStats(),
    );
    await mockJson(page, OPEN_CLOSE_PATTERN, openClose());
    await mockJson(page, '**/rest/v1/rpc/list_parcel_buildings*', [
      { bld_id: searchHit().bld_id, bld_nm: '테스트빌딩', dong_nm: '본동', total_area_m2: 900, floor_cnt: 2, min_floor: 1, max_floor: 2, has_roof: false },
      { bld_id: '1168010100100010000_1024999', bld_nm: null, dong_nm: 'A동', total_area_m2: 100, floor_cnt: 1, min_floor: 1, max_floor: 1, has_roof: false },
    ]);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    // 입구(검색 결과까지 선 화면)도 잰다 — 역할·지역 칩·결과 줄.
    await expect(page.getByRole('button', { name: /테스트빌딩/ })).toBeVisible();
    const entry = await measureTargets(page);
    expect(entry.small).toEqual([]);
    expect(entry.tiny).toEqual([]);

    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack')).toBeVisible();
    await expect(page.locator('section.oc')).toBeVisible();
    // 짧은 동 링크가 실제로 선 뒤에 잰다(빈 측정으로 초록이 되지 않게).
    await expect(page.locator('a.stack__links-a', { hasText: /^A동$/ })).toBeVisible();
    const first = await measureTargets(page);
    expect(first.targets).toBeGreaterThan(10); // 재는 것이 실제로 있었다(빈 측정으로 초록이 되지 않게)
    expect(first.small).toEqual([]);
    expect(first.tiny).toEqual([]);

    // 접힌 카드를 다 펼친다 — 펼쳐야 서는 단추(업종 고르개·더 보기)와 작은 글자까지.
    const closed = page.locator('.card__toggle[aria-expanded="false"]');
    for (let i = 0; i < 20 && (await closed.count()) > 0; i += 1) await closed.first().click();
    // 위 칸을 펼쳐 지도 머리·역할 줄까지 선 화면도.
    await unfoldEntry(page, '상권 지도 보기');
    await expect(page.locator('section.dmap')).toBeVisible();
    const all = await measureTargets(page);
    if (await isPhoneTabs(page)) {
      // 휴대폰(W4a) — 탭마다 따로 선다: 지도 탭 · 더보기 탭(역할 줄·의견함·넘기기 링크·형제 사이트)도 재고, 폭도 본다(412px ·
      // 결정 0039 §5 W4 줄 「AZ 시험에 폭도」 — 넘기기 링크 26·39px 이 44px 로). 건물 탭(카드 다 펼침)도 폭을 다시 잰다.
      expect(all.targets).toBeGreaterThan(0);
      expect(all.small).toEqual([]);
      expect(all.tiny).toEqual([]);
      expect(all.narrow).toEqual([]);
      // 지도 가득(W4b) — 위 띠 단추 · 판 손잡이 · 반으로 펼친 판의 「접기」도 잰다(지도 탭엔 지도 접기 단추가 없다).
      await expect(page.locator('.rstrip__btn')).toBeVisible();
      await expect(page.locator('.dmap__toggle')).toHaveCount(0);
      await page.locator('.dsheet__handle').click();
      await expect(page.locator('.dsheet__fold')).toBeVisible();
      const sheet = await measureTargets(page);
      expect(sheet.small).toEqual([]);
      expect(sheet.tiny).toEqual([]);
      expect(sheet.narrow).toEqual([]);
      await gotoTab(page, '더보기');
      await page.getByRole('button', { name: '의견 보내기' }).click();
      const more = await measureTargets(page);
      expect(more.targets).toBeGreaterThan(5);
      expect(more.small).toEqual([]);
      expect(more.tiny).toEqual([]);
      expect(more.narrow).toEqual([]);
      await gotoTab(page, '건물');
      const bld = await measureTargets(page);
      expect(bld.targets).toBeGreaterThan(first.targets);
      expect(bld.small).toEqual([]);
      expect(bld.narrow).toEqual([]);
    } else {
      expect(all.targets).toBeGreaterThan(first.targets);
      expect(all.small).toEqual([]);
      expect(all.tiny).toEqual([]);
    }

    // ⛔ 종이에서는 44px 이 안 먹는다(`@media screen` 안) — 카드 머리 단추는 화면 44px · 종이는 원래 높이.
    const toggle = page.locator('.card__toggle').first();
    expect((await toggle.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await page.emulateMedia({ media: 'print' });
    expect((await toggle.boundingBox())!.height).toBeLessThan(44);
    await page.emulateMedia({ media: null });
  });

  test('BA. 검색 결과를 내려 아래쪽 건물을 고르면 위 칸이 접히며 화면이 맨 위로 — 바와 건물 이름이 화면 안', { tag: '@onecol' }, async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    const hits = Array.from({ length: 12 }, (_, i) =>
      searchHit({ bld_id: `1168010100100${String(i + 10).padStart(2, '0')}0000_1`, bld_nm: `결과빌딩${i + 1}` }),
    );
    await mockJson(page, SEARCH_PATTERN, hits);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()]);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    const last = page.getByRole('button', { name: /결과빌딩12/ });
    await expect(last).toBeVisible();
    // 손님이 결과 목록을 끝까지 내린 상태(문서 맨 아래로 굴린다).
    await page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)');
    // 정말 아래로 내려온 상태에서 고른다(이 전제가 없으면 시험이 아무것도 안 본다).
    // ⓘ 휴대폰 탭 꼴(W4a)은 찾기 탭에 역할 줄·꼬리말이 없어 문서가 짧다 — 내려간 만큼만 본다.
    const minScroll = (await isPhoneTabs(page)) ? 50 : 200;
    expect(await page.evaluate(() => (globalThis as unknown as { scrollY: number }).scrollY)).toBeGreaterThan(minScroll);
    await last.click();

    const head = page.locator('.stack__head');
    await expect(head).toBeVisible();
    const vh = page.viewportSize()!.height;
    const phone = await isPhoneTabs(page);
    const cols = await isTwoCols(page);
    // 휴대폰(W4a)은 바 대신 아래 탭 막대(늘 화면 안 · 고른 탭 = 건물) · PC 두 칸(W5)은 바 대신 왼쪽 칸(화면에 붙어 늘 화면 안).
    await expect(page.locator(phone ? 'nav.tabbar' : cols ? '.entry' : '.entrybar')).toBeInViewport();
    const title = (await head.getByRole('heading').first().boundingBox())!;
    expect(title.y).toBeGreaterThanOrEqual(0);
    expect(title.y + title.height).toBeLessThanOrEqual(vh);
    // 커서는 바의 첫 단추(고른 결과 줄이 숨어 커서가 문서 맨 앞으로 날아가지 않게) · 휴대폰은 고른 탭(건물).
    // PC 두 칸은 결과가 오른쪽 목록이라(👤 2026-10-22 방법 나) 고르면 목록이 숨는다 — 건물 맨 위 「← 목록으로」에 커서(문서 맨 앞으로 안 날아간다).
    if (phone) await expect(tabButton(page, '건물')).toBeFocused();
    else if (cols) await expect(page.locator('.rback__btn')).toBeFocused();
    else await expect(page.getByRole('button', { name: '다른 건물 찾기' })).toBeFocused();
  });
});

// 긴 카드 창(S2 · 👤 2026-10-15) — 층 목록은 아래 10줄(단추는 목록 위)·이 땅 거래 목록은 처음 10줄만 화면에, 「전부 보기」로 펼치고 같은 자리에서
// 다시 접는다. 숨김은 `@media screen` 안 규칙이라 jsdom(vitest)은 못 본다 — 실제로 숨는지·종이에는 전부 나오는지는 여기서만.
test.describe('긴 카드 창', () => {
  test('BB. 층·거래가 11줄 이상이면 화면엔 10줄(층은 아래 10줄 · 단추는 목록 위) + 「전부 보기」 단추(44px · 13px) · 펼치고 다시 접기 · 종이에는 늘 전부 나오고 단추는 없다', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(
      page,
      // 지분 거래는 숨는 12번째 줄에만 — 점그림이 서서 설명 줄은 늘 선다(결정 0038 B · V2 · 그 전엔 👤 2026-10-16 「접힌 화면엔 없음」).
      Array.from({ length: 12 }, (_, i) => parcelTx({ is_share: i === 11 })),
      Array.from({ length: 12 }, (_, i) => floorRow({ floor_no: 12 - i })),
    );

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const floorsCard = page.locator('.card--floors');
    const floorRows = floorsCard.locator('.floors > li');
    const txRows = page.locator('section.tx .tx__list > li');
    const floorFold = floorsCard.locator('.list__fold');
    const txFold = page.locator('section.tx .list__fold');

    // 줄은 전부 그려져 있고(12) 화면엔 아래 10줄만 — 숨는 것은 맨 위층 둘(👤 「아래 10줄」).
    await expect(floorRows).toHaveCount(12);
    await expect(floorsCard.locator('.floors > li:visible')).toHaveCount(10);
    await expect(floorsCard.locator('#floor-12')).toBeHidden();
    await expect(floorsCard.locator('#floor-11')).toBeHidden();
    await expect(floorsCard.locator('#floor-10')).toBeVisible();
    await expect(floorsCard.locator('#floor-1')).toBeVisible();
    await expect(txRows).toHaveCount(12);
    await expect(page.locator('section.tx .tx__list > li:visible')).toHaveCount(10);

    await expect(floorFold).toHaveText('위층 전부 보기 (2개 층 더)');
    // 층 단추는 목록 **위** — 보이는 첫 줄(10층)보다 위에 선다.
    expect((await floorFold.boundingBox())!.y).toBeLessThan((await floorsCard.locator('#floor-10').boundingBox())!.y);
    // 접힌 동안 거래 목록의 보이는 마지막 줄 아래 점선이 없다(그 뒤 줄이 숨어 있어도).
    await expect(page.locator('section.tx .tx__list > li:visible').last()).toHaveCSS('border-bottom-style', 'none');
    await expect(txFold).toHaveText('거래 전부 보기 (12건)');
    for (const btn of [floorFold, txFold]) {
      expect((await btn.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      // 글자 13px(화면 하한) — 이 파일은 DOM 타입을 안 싣는다(getComputedStyle 대신 toHaveCSS).
      await expect(btn).toHaveCSS('font-size', '13px');
    }

    // 지분은 숨은 12번째 줄에만 — 그래도 거래가 5건 이상이라 점그림이 서고(결정 0038 B · V2), 그림에는 숨은 줄의 지분도
    // 빈 꼴로 보이므로 설명 줄은 **늘** 선다(`shownShare` 의 예외). 그림이 안 서는 목록의 숨김 갈래는 vitest(S2 묶음)가 본다.
    const shareNote = page.locator('section.tx .tx__share-note');
    await expect(shareNote).toHaveCount(1);
    await expect(page.locator('section.tx .tx__plot')).toBeVisible();
    await expect(shareNote).toBeVisible();

    // 펼치면 전부 → 같은 자리 단추로 다시 접으면 10줄 + 그 카드 머리가 화면 안으로 굴러온다.
    // ⓘ 접기 전에 단추를 화면 맨 위로 올려 카드 머리를 화면 **밖**으로 내보낸다 — 머리가 처음부터 화면 안이면
    //   「굴렀나」를 못 가른다(S2 검사 🟡). 그래서 '밖이다'를 먼저 단언하고 누른다.
    const floorsHead = floorsCard.locator('.card__h');
    const txHead = page.locator('section.tx .card__h');
    await floorFold.click();
    await expect(floorsCard.locator('.floors > li:visible')).toHaveCount(12);
    await expect(floorFold).toHaveText('층 목록 접기');
    await floorFold.evaluate((el) => el.scrollIntoView({ block: 'start' }));
    await expect(floorsHead).not.toBeInViewport();
    await floorFold.click();
    await expect(floorsCard.locator('.floors > li:visible')).toHaveCount(10);
    await expect(floorsHead).toBeInViewport({ ratio: 0.9 });
    await txFold.click();
    await expect(page.locator('section.tx .tx__list > li:visible')).toHaveCount(12);
    await expect(txFold).toHaveText('거래 목록 접기');
    await expect(shareNote).toBeVisible();
    await txFold.evaluate((el) => el.scrollIntoView({ block: 'start' }));
    await expect(txHead).not.toBeInViewport();
    await txFold.click();
    await expect(page.locator('section.tx .tx__list > li:visible')).toHaveCount(10);
    await expect(txHead).toBeInViewport({ ratio: 0.9 });
    await expect(shareNote).toBeVisible();

    // ⛔ 종이에는 늘 전부(접힌 상태에서 뽑아도) — 단추는 누르는 장치라 빠진다. 지분 설명 줄도 종이엔 늘 선다.
    await page.emulateMedia({ media: 'print' });
    await expect(floorsCard.locator('.floors > li:visible')).toHaveCount(12);
    await expect(page.locator('section.tx .tx__list > li:visible')).toHaveCount(12);
    await expect(floorFold).toBeHidden();
    await expect(txFold).toBeHidden();
    await expect(shareNote).toBeVisible();
    await page.emulateMedia({ media: null });
  });
});

// 휴대폰 층 줄 = 세 줄(S2 후속 · 👤 2026-10-16 시안 「나」) — 좁은 화면에서 층 줄 칸 일곱이 한 칸씩 세로로 쌓여 한 줄이
// 214px 였다(운영 실측). `@media screen and (max-width: 720px)` 의 그리드 자리로 세 줄에 묶는다. CSS 라 jsdom 은 못 본다.
test.describe('휴대폰 층 줄', () => {
  test('BC. 휴대폰 폭에서 층 줄은 세 줄(층 이름·용도·▼ / 막대 / 면적·점포·거래) · 긴 용도는 첫 줄 안에서만 줄바꿈 · 넓은 화면과 종이는 그대로', async ({
    page,
  }, testInfo) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(
      page,
      [parcelTx({ floor_no: 2 }), parcelTx({ floor_no: 2 })],
      [
        floorRow({ floor_no: 2, main_use: '기타제1종근린생활시설', floor_area_m2: 2116.2, store_cnt: 8 }),
        // 용도 이름이 긴 층 — 좁은 화면에서 첫 줄 안에서만 줄을 바꾼다(가로 넘침 0).
        floorRow({ floor_no: 1, main_use: '제2종근린생활시설(일반음식점·휴게음식점·제과점) 및 업무시설(일반업무시설)' }),
        floorRow({ floor_no: -1, main_use: '주차장', store_cnt: null }),
      ],
    );

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const card = page.locator('.card--floors');
    await expect(card.locator('.floor__row')).toHaveCount(3);
    const mobile = testInfo.project.name === 'mobile';

    /** 층 줄 하나의 칸 자리(뷰포트 기준). */
    const shapeOf = (no: number) =>
      card.locator(`#floor-${no} .floor__row`).evaluate((row) => {
        const r = (sel: string) => {
          const b = (sel === '' ? row : row.querySelector(sel)!).getBoundingClientRect();
          return { top: b.top, bottom: b.bottom, left: b.left, right: b.right, h: b.height, w: b.width, mid: (b.top + b.bottom) / 2 };
        };
        return {
          row: r(''),
          label: r('.floor__label'),
          bar: r('.floor__bar'),
          use: r('.floor__use'),
          area: r('.floor__area'),
          stores: r('.floor__stores'),
          tx: r('.floor__tx'),
          caret: r('.floor__caret'),
          over: row.scrollWidth - row.clientWidth,
          areas: row.ownerDocument.defaultView!.getComputedStyle(row).gridTemplateAreas,
        };
      });

    for (const no of [2, 1, -1]) {
      const s = await shapeOf(no);
      expect(s.over, `${no}층 줄 가로 넘침`).toBeLessThanOrEqual(0);
      if (mobile) {
        // 세 줄 — 한 줄 높이는 지금(214px)의 절반도 안 된다(긴 용도 층은 아래에서 따로 본다).
        if (no !== 1) expect(s.row.h, `${no}층 줄 높이`).toBeLessThan(120);
        // ① 층 이름 · 용도 · ▼ 가 같은 첫 줄(가운데가 같다) — ▼ 는 오른쪽 끝.
        expect(Math.abs(s.label.mid - s.caret.mid)).toBeLessThan(2);
        expect(s.use.left).toBeGreaterThan(s.label.right);
        expect(s.caret.left).toBeGreaterThan(s.use.right);
        // ② 막대는 첫 줄 아래, 폭 전체.
        expect(s.bar.top).toBeGreaterThanOrEqual(Math.max(s.label.bottom, s.use.bottom, s.caret.bottom));
        expect(s.bar.w).toBeGreaterThan(s.row.w * 0.8);
        // ③ 면적(왼쪽) · 점포(오른쪽)는 막대 아래 같은 줄.
        expect(s.area.top).toBeGreaterThanOrEqual(s.bar.bottom);
        expect(Math.abs(s.area.mid - s.stores.mid)).toBeLessThan(2);
        expect(s.stores.left).toBeGreaterThan(s.area.right);
        // 거래가 없는 층(2층만 거래가 있다)은 점포가 ▼ 와 같은 오른쪽 끝에 선다(빈 뱃지 칸만큼 안쪽에 서지 않게).
        if (no !== 2) expect(Math.abs(s.stores.right - s.caret.right)).toBeLessThan(2);
      } else {
        // 넓은 화면은 그대로 — 한 줄 44px(바꾸기 전 실측) · 그리드 자리 이름 없음.
        expect(s.row.h, `${no}층 줄 높이`).toBe(44);
        expect(s.areas).toBe('none');
      }
    }
    if (mobile) {
      // 거래가 있는 층은 「거래 N건」이 점포 오른쪽 같은 줄.
      const two = await shapeOf(2);
      expect(Math.abs(two.tx.mid - two.stores.mid)).toBeLessThan(2);
      expect(two.tx.left).toBeGreaterThan(two.stores.right);
      // 긴 용도는 첫 줄 안에서 줄을 바꾼다(양성 대조 — 이 픽스처가 실제로 줄바꿈을 일으키는지).
      const one = await shapeOf(1);
      expect(one.use.h).toBeGreaterThan(one.label.h * 1.5);
      // 늘어난 높이는 용도 칸이 늘어난 만큼뿐이다(막대·면적 줄은 그대로).
      expect(Math.abs(one.row.h - two.row.h - (one.use.h - two.use.h))).toBeLessThan(2);
    }
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    await card.screenshot({ path: testInfo.outputPath(`bc-floors-${testInfo.project.name}.png`) });

    // ⛔ 종이는 그대로 — 새 규칙은 `screen` 안에만 있다(그리드 자리 이름 없음 · 칸 수도 지금 그대로).
    await page.emulateMedia({ media: 'print' });
    const printed = await card
      .locator('#floor-2 .floor__row')
      .evaluate((el) => {
        const cs = el.ownerDocument.defaultView!.getComputedStyle(el);
        return { areas: cs.gridTemplateAreas, cols: cs.gridTemplateColumns.split(' ').length };
      });
    expect(printed).toEqual({ areas: 'none', cols: mobile ? 1 : 7 });
    await page.emulateMedia({ media: null });
  });
});

// ── 그림 (결정 0038 V1 — E ▲ 눈금·층 묶음 쌓은 막대 · A 참고 시세 띠는 결정 0041 로 내림) ─────────────────────
// 값 → 자리·폭 계산은 단위 시험(`viz.test.ts`·`industryMix.test.ts`)이, 서는 경우/안 서는 경우는 컴포넌트 시험이 덮는다.
// 여기서만 보이는 것은 **실제로 그려진 자리**(브라우저가 배치한 상자의 비율이 픽스처 숫자와 맞나) · 색이 토큰 값인가 ·
// 넓은 화면·휴대폰·종이에서 같은 그림이 서는가다(그림이 깨져도 글자 시험은 초록이다 — 결정 0038 §2-10).

/** `:root` 의 색 토큰 → `rgb(r, g, b)`(계산된 스타일과 견주려고). */
async function tokenRgb(page: Page, name: string) {
  const hex = await page
    .locator('html')
    .evaluate((el, n) => el.ownerDocument.defaultView!.getComputedStyle(el).getPropertyValue(n).trim(), name);
  expect(hex, name).toMatch(/^#[0-9a-f]{6}$/i);
  const n = (i: number) => parseInt(hex.slice(i, i + 2), 16);
  return `rgb(${n(1)}, ${n(3)}, ${n(5)})`;
}

/** 상자 a 의 가운데(또는 왼쪽 끝)가 상자 b 의 폭에서 몇 % 자리인가. */
async function pctIn(a: ReturnType<Page['locator']>, b: ReturnType<Page['locator']>, at: 'center' | 'left' = 'center') {
  const x = (await a.boundingBox())!;
  const y = (await b.boundingBox())!;
  const px = at === 'center' ? x.x + x.width / 2 : x.x;
  return ((px - y.x) / y.width) * 100;
}

test.describe('그림 — 둘레의 업종 분포 (결정 0038 E)', () => {
  test('BD. 상권 막대 줄마다 ▲(가운데값 자리 · 추정 잉크색) · 반경엔 없음 · 층 줄 위 쌓은 막대(칸 수 = 0 아닌 묶음 · 폭 합 100% · 호박 진하기 + 회색) · 412px 넘침 0 · 종이에도 그대로', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow()], industryMixTwoDistricts());
    // 나중에 등록한 것이 먼저 잡힌다 — mockFloorStack 의 '함수 없음' 위에 덮는다.
    await mockJson(page, INDUSTRY_MEDIAN_PATTERN, industryMedian());
    await mockJson(page, INDUSTRY_MEDIAN_M_PATTERN, industryMedianM());
    await mockJson(page, INDUSTRY_DETAIL_PATTERN, industryDetailTwoDistricts());
    // 층 묶음 — 골목(지하 0곳 → 칸 넷)과 반경(다섯 묶음 다 → 칸 다섯). 합 = 그 블록 업종 총수(120 · 150).
    const fl = industryFloors();
    await mockJson(page, INDUSTRY_FLOORS_PATTERN, {
      ...fl,
      districts: [{ district_id: '3110001', name: '역삼골목', total: 120, bands: { b: 0, '1': 78, '2': 18, '3+': 6, na: 18 } }],
    });

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    const mix = page.locator('section.mix');
    if ((await mix.locator('.card__toggle').getAttribute('aria-expanded')) === 'false') {
      await mix.locator('.card__toggle').click();
    }
    const block = (root: ReturnType<Page['locator']>, heading: string) =>
      root.locator('.mix__block').filter({ has: page.getByRole('heading', { name: heading }) });
    const gol = block(mix, '역삼골목(골목상권) 안 215곳');
    await expect(gol.locator('.mix__med')).toHaveCount(2);

    const inkRgb = await tokenRgb(page, '--est-ink');
    /** 블록의 막대 줄마다 ▲ 가운데의 막대 칸 안 자리(%) — 없으면 null. */
    const markPcts = async (root: ReturnType<Page['locator']>) => {
      const out: Array<number | null> = [];
      for (const li of await root.locator('.mix__bars li').all()) {
        const mark = li.locator('.mix__mark');
        out.push((await mark.count()) === 0 ? null : await pctIn(mark, li.locator('.mix__bar')));
      }
      return out;
    };
    /**
     * ▲ 가 정말 눈에 보이나 — 가운데 점을 눌렀을 때 맨 위에 있는 것이 그 ▲ 인가(`elementFromPoint`).
     * ⓘ `toBeVisible()` 은 상자 크기만 봐서, 부모가 `overflow: hidden` 으로 ▲ 를 잘라도 초록이다(검사관 변이 실측).
     *   잘리면 그 점에서 잡히는 것은 줄(li) 같은 다른 상자다.
     * ⛔ ▲ 자신을 `scrollIntoView` 하지 않는다 — `overflow: hidden` 칸도 스크립트로는 굴러가서, 잘린 ▲ 를 칸 안으로 끌어올려
     *   이 단언이 초록이 된다(실측: 변이에서 2 passed). 페이지만 굴리게 **줄(li)** 을 화면에 들인다(막대 칸은 줄의 조상이 아니다).
     */
    const expectMarksOnTop = async (root: ReturnType<Page['locator']>) => {
      const marks = await root.locator('.mix__mark').all();
      expect(marks.length).toBeGreaterThan(0);
      for (const m of marks) {
        const hit = await m.evaluate((e) => {
          e.closest('li')!.scrollIntoView({ block: 'center' });
          const r = e.getBoundingClientRect();
          const at = e.ownerDocument.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return at === e || (at !== null && e.contains(at)) ? 'mark' : at === null ? 'none' : at.className;
        });
        expect(hit).toBe('mark');
      }
    };
    const checkMarks = async () => {
      // ① 대분류 상권 블록 — 골목 음식 25.0 · 소매 19.3(픽스처 med_pct) · 전통시장(30곳 미만)·반경엔 없음.
      const g = await markPcts(gol);
      expect(g).toHaveLength(2);
      expect(g[0]!).toBeCloseTo(25.0, 0);
      expect(g[1]!).toBeCloseTo(19.3, 0);
      expect(await markPcts(block(mix, '역삼시장(전통시장) 안 12곳'))).toEqual([null, null]);
      expect(await markPcts(block(mix, '반경 500m 안 200곳'))).toEqual([null, null]);
      // ▲ 는 막대 바로 아래에서 위를 가리킨다(꼭짓점이 막대 아래 변에 닿는다) · 추정 잉크색.
      const mark = gol.locator('.mix__mark').first();
      const mb = (await mark.boundingBox())!;
      const bb = (await gol.locator('.mix__bars li').first().locator('.mix__bar').boundingBox())!;
      expect(Math.abs(mb.y - (bb.y + bb.height))).toBeLessThan(1.5);
      expect(mb.height).toBeGreaterThan(3);
      expect(await mark.evaluate((e) => e.ownerDocument.defaultView!.getComputedStyle(e).borderBottomColor)).toBe(inkRgb);
      await expectMarksOnTop(gol);
    };
    await checkMarks();

    // 대분류를 고르면 상세 — 중분류 ▲(골목 한식 38.1 · 비알코올 15.2 · 기타 간이 20.6 · 주점 9.8) + 층 묶음 막대.
    await mix.locator('select.mix__select').selectOption('I2');
    const detail = mix.locator('.mix__detail');
    const dGol = block(detail, '역삼골목(골목상권) 안 음식 120곳');
    const dRadius = block(detail, '반경 500m 안 음식 150곳');
    await expect(dGol.locator('.mix__med')).toHaveCount(4);
    await expect(detail.locator('.mix__floors')).toHaveCount(2);
    const checkDetail = async () => {
      const d = await markPcts(dGol);
      expect(d.map((v) => Math.round(v!))).toEqual([38, 15, 21, 10]);
      expect(await markPcts(dRadius)).toEqual([null, null]);
      await expectMarksOnTop(dGol);

      // ③ 쌓은 막대 — 층 줄 글 바로 위 · 칸 수 = 0 아닌 묶음 수 · 칸 폭 합 ≈ 막대 폭 · 칸 폭 ∝ 곳 수.
      const steps = await Promise.all(['--fact-1', '--fact-2', '--fact-3', '--fact-4', '--viz-na'].map((n) => tokenRgb(page, n)));
      const checkStack = async (root: ReturnType<Page['locator']>, bands: number[]) => {
        const stack = root.locator('.mix__stack');
        await expect(stack).toHaveCount(1);
        // 글 줄 바로 앞 형제다.
        expect(await root.locator('.mix__floors').evaluate((p) => p.previousElementSibling?.className)).toBe('mix__stack');
        const sb = (await stack.boundingBox())!;
        const cells = stack.locator('.mix__stack-cell');
        const want = bands.map((n, i) => ({ n, i })).filter((c) => c.n > 0);
        await expect(cells).toHaveCount(want.length);
        const sum = bands.reduce((a, b) => a + b, 0);
        let total = 0;
        for (const [k, c] of want.entries()) {
          const cb = (await cells.nth(k).boundingBox())!;
          total += cb.width;
          expect((cb.width / sb.width) * 100).toBeCloseTo((c.n / sum) * 100, 0);
          // ④ 색 = 토큰 값(지하 → 3층 이상 호박 4단 · 층 미상 회색).
          expect(await cells.nth(k).evaluate((e) => e.ownerDocument.defaultView!.getComputedStyle(e).backgroundColor)).toBe(steps[c.i]);
          // 층 미상 칸만 흰 사선 빗금(흑백 밝기가 1층과 비슷해 무늬로 가른다) — 화면과 종이 둘 다.
          const img = await cells.nth(k).evaluate((e) => e.ownerDocument.defaultView!.getComputedStyle(e).backgroundImage);
          if (c.i === 4) expect(img).toContain('repeating-linear-gradient');
          else expect(img).toBe('none');
        }
        expect(Math.abs(total - sb.width)).toBeLessThan(1);
      };
      await checkStack(dGol, [0, 78, 18, 6, 18]);
      await checkStack(dRadius, [2, 90, 24, 9, 25]);
    };
    await checkDetail();
    // 글 줄은 그대로(층 줄 글자 대조).
    await expect(dGol.locator('.mix__floors')).toHaveText('층별 음식: 지하 0곳 · 1층 78곳 · 2층 18곳 · 3층 이상 6곳 · 층 미상 18곳 (15%)');

    // 412px — 페이지·막대 줄 넘침 0.
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    for (const el of await mix.locator('.mix__bars li, .mix__stack').all()) {
      expect(await el.evaluate((e) => e.scrollWidth - e.clientWidth)).toBeLessThanOrEqual(0);
    }

    // ⑤ 종이 — 같은 그림 · 같은 자리 · 같은 색(`print-color-adjust: exact`).
    await page.emulateMedia({ media: 'print' });
    await expect(gol.locator('.mix__mark').first()).toBeVisible();
    await expect(dGol.locator('.mix__stack')).toBeVisible();
    await checkMarks();
    await checkDetail();
    expect(await gol.locator('.mix__mark').first().evaluate((e) => e.ownerDocument.defaultView!.getComputedStyle(e).printColorAdjust)).toBe('exact');
    await page.emulateMedia({ media: null });
  });
});

// ── 역할 요약 판 (👤 결정 0039 Q2 · §4-2 · §4-9 · W2) ──────────────────────────────────────
// 값 고르기·빈 값 갈래·판단 낱말·추가 호출 0 은 단위 시험(`roleSummary.test`·`RoleSummary.test`)이 덮는다.
// 여기서만 보이는 것은 **자리(건물 머리 위)·좁은 폭 넘침·종이에서 빠짐·단추 높이**다.

test.describe('층별 스택뷰 — 역할 요약 판', () => {
  async function openWithRole(page: Page, role: string | null) {
    if (role !== null) {
      await page.addInitScript((r) => {
        // ⚠️ 이 파일의 타입 검사는 브라우저 타입(DOM)을 안 켠다 — 전역을 좁은 모양으로 꺼내 쓴다(시험 AQ 와 같은 사정).
        const w = globalThis as unknown as { localStorage: { setItem(k: string, v: string): void } };
        w.localStorage.setItem('sangga.viewerRole', r);
      }, role);
    }
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(
      page,
      [parcelTx()],
      [floorRow({ floor_no: 2 }), floorRow()],
      industryMix(),
      undefined,
      undefined,
      rentStats(),
    );
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).first().click();
    await expect(page.locator('section.stack .stack__head')).toBeVisible();
  }

  test('BF. 역할을 고르면 건물 머리 위에 타일 판(근거·등급 줄) · 역할이 없으면 판 없음 · 412px 넘침 0 · 종이에서는 빠진다', async ({
    page,
  }) => {
    // ① 역할 없음 — 판이 없다(지금 화면 그대로).
    await openWithRole(page, null);
    await expect(page.locator('section.stack .stack__head')).toBeVisible();
    await expect(page.locator('.rsum')).toHaveCount(0);

    // ② 투자자 — 판이 건물 머리 **앞**(같은 부모) · 첫 타일은 공표값(결정 0041 E3 — 이 목업은 기준시가 함수가 없어
    //    구 상가 단가 · A등급 실거래 · 추정 색 아님) · 임대 타일은 「상권 평균」.
    await openWithRole(page, '투자자');
    const sum = page.locator('section.stack > .rsum');
    await expect(sum).toBeVisible();
    await expect(sum.locator('.rsum__question')).toHaveText('얼마고 얼마 벌리나');
    await expect(sum.locator('.rsum__tile--rent')).toContainText('상권 평균');
    await expect(sum.locator('.rsum__tile--txstat .rsum__label')).toHaveText('구 상가 단가 (1층)');
    await expect(sum.locator('.rsum__tile--txstat .grade__badge')).toHaveText('A등급 · 실거래 집계');
    await expect(sum.locator('.rsum__tile--txstat .grade__badge--est')).toHaveCount(0);
    await expect(sum).not.toContainText('참고 시세');
    expect(await sum.locator('.rsum__tile').count()).toBeGreaterThanOrEqual(3);
    expect(
      await sum.evaluate((e) => {
        const head = e.parentElement!.querySelector(':scope > .stack__head')!;
        return (e.compareDocumentPosition(head) & 4) !== 0; // 4 = 머리가 판 뒤에 온다
      }),
    ).toBe(true);
    // 판이 건물 이름보다 위(첫 3초).
    const sumBox = (await sum.boundingBox())!;
    const titleBox = (await page.locator('.stack__title').boundingBox())!;
    expect(sumBox.y).toBeLessThan(titleBox.y);
    // 좁은 폭에서도 판 안·페이지 가로 넘침이 없다.
    expect(await sum.evaluate((e) => e.scrollWidth - e.clientWidth)).toBeLessThanOrEqual(0);
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);

    // ③ 종이 — 판은 빠지고(§4-2) 건물 머리는 그대로.
    await page.emulateMedia({ media: 'print' });
    await expect(sum).toBeHidden();
    await expect(page.locator('section.stack .stack__head')).toBeVisible();
    await page.emulateMedia({ media: null });
  });

  test('BK. 휴대폰 요약 판은 타일 2칸 + 「요약 N칸 더 보기」(44px) — 건물 이름이 첫 화면에 · 누르면 다 · 넓은 화면은 다 보이고 단추 없음 · 종이에서 판째 빠짐', async ({
    page,
  }, testInfo) => {
    await openWithRole(page, '투자자');
    const sum = page.locator('section.stack > .rsum');
    const tiles = sum.locator('.rsum__tile');
    const more = sum.getByRole('button', { name: /^요약 \d+칸 더 보기$/ });
    // 곁 카드 값이 다 와 타일이 다 선 뒤에 센다(임대 타일이 마지막 쪽).
    await expect(sum.locator('.rsum__tile--rent')).toContainText('상권 평균');
    await expect.poll(() => tiles.count()).toBeGreaterThanOrEqual(3);
    const n = await tiles.count();
    if (testInfo.project.name === 'mobile') {
      // 👤 2026-10-17 W4a 4번 「가」 · 결정 0039 §7-8.
      await expect(sum.locator('.rsum__tile:visible')).toHaveCount(2);
      await expect(more).toHaveText(`요약 ${n - 2}칸 더 보기`);
      expect((await more.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      // 건물 이름이 첫 화면 높이 안(문서 위치 · 맨 위에서 스크롤 없이).
      const title = (await page.locator('.stack__title').boundingBox())!;
      const sy = await page.evaluate(() => (globalThis as unknown as { scrollY: number }).scrollY);
      expect(title.y + title.height + sy).toBeLessThanOrEqual(page.viewportSize()!.height);
      await more.click();
      await expect(sum.locator('.rsum__tile:visible')).toHaveCount(n);
      await expect(sum.getByRole('button', { name: '요약 접기' })).toHaveAttribute('aria-expanded', 'true');
    } else {
      await expect(sum.locator('.rsum__tile:visible')).toHaveCount(n);
      await expect(more).toBeHidden();
    }
    await page.emulateMedia({ media: 'print' });
    await expect(sum).toBeHidden();
    await page.emulateMedia({ media: null });
  });

  test('BG. 중개사 판의 「한 장으로 뽑기」 — 화면 44px 이상 · 누르면 인쇄 창 · 종이에서는 판째 빠진다', async ({ page }) => {
    await openWithRole(page, '중개사');
    const btn = page.locator('.rsum').getByRole('button', { name: '한 장으로 뽑기' });
    await expect(btn).toBeVisible();
    expect((await btn.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await expect(page.locator('.rsum__tile--owner')).toContainText('사용승인');
    // 인쇄 창은 흉내만 — 불렸는지 센다.
    await page.evaluate(() => {
      const w = globalThis as unknown as { print: () => void; __printed: number };
      w.__printed = 0;
      w.print = () => {
        w.__printed += 1;
      };
    });
    await btn.click();
    expect(await page.evaluate(() => (globalThis as unknown as { __printed: number }).__printed)).toBe(1);
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('.rsum')).toBeHidden();
    await page.emulateMedia({ media: null });
  });
});

/*
  역할 고르기 큰 카드(결정 0039 Q3 · §4-10 · §7-4 · W3). 세 시험 모두 `@first-visit` — 맨 위 beforeEach 의 '물어봤음' 기본값을
  넣지 않은 빈 저장소(처음 온 사람)에서 시작한다. 카드 글·알림·저장 규칙은 단위 시험(`RoleCards.test`·`viewerRoleStore.test`·
  `App.test` 「큰 카드」)이 본다 — 여기서는 실제 배치(휴대폰 세로 쌓기·넓은 화면 한 줄·높이)·종이·새로고침을 본다.
*/
test.describe('첫 화면 — 역할 고르기 큰 카드', () => {
  /** 이 페이지의 이 기기 저장값(역할 열쇠). */
  async function storedRole(page: Page) {
    return page.evaluate(
      () =>
        (globalThis as unknown as { localStorage: { getItem(k: string): string | null } }).localStorage.getItem(
          'sangga.viewerRole',
        ),
    );
  }

  test('BH. 빈 저장소로 `/` 를 열면 입구 맨 위에 큰 카드(작은 줄 숨김) · 휴대폰은 세로 쌓기·카드 56px·둘러보기 44px · 넓은 화면은 한 줄 · 종이에 없음 · 카드를 누르면 사라지고 그 역할 화면', { tag: ['@first-visit', '@onecol'] }, async ({ page }, testInfo) => {
    await mockOpenSigungu(page);
    await page.goto('/');
    const box = page.locator('section.rolecards');
    await expect(box).toBeVisible();
    await expect(box.getByText('무엇을 하러 오셨나요?')).toBeVisible();
    await expect(page.locator('section.role')).toHaveCount(0);
    // 덮개가 아니다 — 지역 고르기가 그대로 보인다. 한 열·휴대폰 = 카드 **아래** · PC 두 칸 = 카드는 오른쪽 빈 칸 · 왼쪽 칸 맨 위가
    // 지역 고르기(👤 2026-10-22 왼쪽 칸 다듬기 L6 — 지역·검색·지도가 바로 보이게).
    const region = page.getByRole('button', { name: /^서울$/ });
    await expect(region).toBeVisible();
    if (await isTwoCols(page)) {
      const left = (await page.locator('.entry').boundingBox())!;
      const b = (await box.boundingBox())!;
      expect(b.x).toBeGreaterThanOrEqual(left.x + left.width);
      expect(await page.locator('.entry section.rolecards').count()).toBe(0);
      expect((await region.boundingBox())!.y).toBeLessThan(left.y + 200);
    } else {
      expect((await region.boundingBox())!.y).toBeGreaterThan((await box.boundingBox())!.y);
    }

    const cards = box.locator('.rolecards__card');
    await expect(cards).toHaveCount(3);
    const rects = await Promise.all([0, 1, 2].map(async (i) => (await cards.nth(i).boundingBox())!));
    for (const r of rects) expect(r.height).toBeGreaterThanOrEqual(56);
    // 휴대폰은 세로로 쌓기 · 한 열 넓은 화면(desktop-1000)·PC 두 칸 오른쪽 빈 칸(L6)은 한 줄에 셋.
    if (testInfo.project.name === 'mobile') {
      // 세로로 쌓기 — 왼쪽 끝이 같고 위에서 아래로.
      expect(rects[1].y).toBeGreaterThanOrEqual(rects[0].y + rects[0].height);
      expect(rects[2].y).toBeGreaterThanOrEqual(rects[1].y + rects[1].height);
      expect(Math.abs(rects[1].x - rects[0].x)).toBeLessThanOrEqual(1);
    } else {
      // 한 열 넓은 화면 · PC 두 칸 오른쪽 = 한 줄에 셋.
      expect(Math.abs(rects[1].y - rects[0].y)).toBeLessThanOrEqual(1);
      expect(Math.abs(rects[2].y - rects[0].y)).toBeLessThanOrEqual(1);
      expect(rects[1].x).toBeGreaterThan(rects[0].x + rects[0].width - 1);
    }
    const browse = box.getByRole('button', { name: '그냥 둘러보기' });
    expect((await browse.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);

    // 종이 — 누르는 장치라 빠진다.
    await page.emulateMedia({ media: 'print' });
    await expect(box).toBeHidden();
    await page.emulateMedia({ media: null });
    await expect(box).toBeVisible();

    // 카드를 누르면 사라지고 작은 줄에 그 역할 · 창업자 차례(지도가 검색창 위)는 구를 골라야 보이니 저장값과 눌림만.
    await cards.filter({ hasText: '가게를 열려고' }).click();
    await expect(box).toHaveCount(0);
    await gotoTab(page, '더보기'); // 휴대폰(W4a)은 작은 역할 줄이 「더보기」 탭(숨은 단추는 역할로 못 찾는다)
    await expect(page.locator('section.role').getByRole('button', { name: '창업자' })).toHaveAttribute('aria-pressed', 'true');
    expect(await storedRole(page)).toBe('창업자');
    // 주소에는 안 실린다.
    expect(new URL(page.url()).search).toBe('');
  });

  test('BI. 「그냥 둘러보기」= 카드 사라짐 · 아무 역할도 안 눌림 · 새로고침해도 안 뜬다', { tag: '@first-visit' }, async ({ page }) => {
    await mockOpenSigungu(page);
    await page.goto('/');
    await page.locator('section.rolecards').getByRole('button', { name: '그냥 둘러보기' }).click();
    await expect(page.locator('section.rolecards')).toHaveCount(0);
    await gotoTab(page, '더보기'); // 휴대폰(W4a)은 작은 역할 줄이 「더보기」 탭
    for (const name of ['투자자', '창업자', '중개사']) {
      await expect(page.locator('section.role').getByRole('button', { name })).toHaveAttribute('aria-pressed', 'false');
    }
    expect(await storedRole(page)).toBe('둘러보기');
    await page.reload();
    await gotoTab(page, '더보기'); // 휴대폰(W4a)은 작은 역할 줄이 「더보기」 탭
    await expect(page.locator('section.role')).toBeVisible();
    await expect(page.locator('section.rolecards')).toHaveCount(0);
  });

  test('BJ. 건물 직행 링크(`bld`)에서는 안 뜨고 저장도 안 한다 · `?sgg=` 만 든 링크에서는 뜬다', { tag: ['@first-visit', '@onecol'] }, async ({ page }) => {
    await mockOpenSigungu(page);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()]);
    await page.goto(`/?sgg=11680&bld=${LINK_BLD}`);
    await expect(page.locator('section.stack').getByRole('heading', { name: '테스트빌딩' })).toBeVisible();
    // PC 두 칸(W5)은 바가 없고 왼쪽 칸에 작은 역할 줄이 그대로 선다(아래에서 본다).
    if (await isPhoneTabs(page)) await expect(tabButton(page, '건물')).toHaveAttribute('aria-current', 'page');
    else if (await isTwoCols(page)) await expect(page.locator('.entrybar')).toHaveCount(0);
    else await expect(page.locator('.entrybar').getByRole('button', { name: '나는 역할 고르기' })).toBeVisible();
    await unfoldEntry(page, '나는 역할 고르기'); // 휴대폰은 「더보기」 탭
    await expect(page.locator('section.role')).toBeVisible();
    await expect(page.locator('section.rolecards')).toHaveCount(0);
    expect(await storedRole(page)).toBeNull();

    await page.goto('/?sgg=11680');
    await expect(page.locator('section.rolecards')).toBeVisible();
    await expect(page.locator('section.role')).toHaveCount(0);
  });
});

// ── 휴대폰 아래 탭 (결정 0039 Q1 · W4a · 👤 2026-10-17 결정 7건) ─────────────────────────────────────────────
// 휴대폰(mobile 판 · 412px)에서만 선다 — 넓은 화면(chromium)은 탭 0 을 보고 끝난다. 탭 상태·뒤로가기 칸·역할별 탭은 vitest
// (`App.tabs.test.tsx`)도 본다 — 여기서만 보이는 것은 **CSS 로 숨는 덩어리 · 고정 막대의 자리 · 종이 · 자판 · 진짜 뒤로가기**다.
test.describe('휴대폰 아래 탭', () => {
  async function openBuilding(page: Page) {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()]);
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack .stack__head')).toBeVisible();
  }

  test('BL. 탭 넷(그림 + 글자 · 44px · 13px · 고른 탭 강조) · 첫 탭 찾기 · 빈 건물 탭 안내 · 탭마다 다른 덩어리 · 꼬리말이 막대에 안 가림 · 넓은 화면엔 탭 0', async ({
    page,
  }, testInfo) => {
    await mockOpenSigungu(page);
    await page.goto('/');
    const bar = page.getByRole('navigation', { name: '화면 고르기' });
    if (testInfo.project.name !== 'mobile') {
      await expect(page.locator('section.region')).toBeVisible();
      await expect(bar).toHaveCount(0);
      await expect(page.locator('footer.foot .foot__notice')).toBeVisible();
      return;
    }
    const btns = bar.getByRole('button');
    await expect(btns).toHaveText(['찾기', '지도', '건물', '더보기']);
    await expect(bar.getByRole('button', { name: '찾기', exact: true })).toHaveAttribute('aria-current', 'page');
    for (const b of await btns.all()) {
      const box = (await b.boundingBox())!;
      expect(box.height).toBeGreaterThanOrEqual(44);
      expect(box.width).toBeGreaterThanOrEqual(44);
      await expect(b).toHaveCSS('font-size', '13px');
      await expect(b.locator('svg')).toHaveCount(1);
    }
    // 고른 탭은 강조색 · 굵게(나머지와 다르다).
    // ⚠️ 이 파일의 타입 검사는 브라우저 타입(DOM)을 안 켠다 — 전역을 좁은 모양으로 꺼내 쓴다.
    const color = (name: string) =>
      tabButton(page, name).evaluate(
        (e) => (globalThis as unknown as { getComputedStyle(x: unknown): { color: string } }).getComputedStyle(e).color,
      );
    expect(await color('찾기')).not.toBe(await color('지도'));
    // 막대는 화면 맨 아래에 붙는다(고정).
    const vh = page.viewportSize()!.height;
    const barBox = (await bar.boundingBox())!;
    expect(Math.abs(barBox.y + barBox.height - vh)).toBeLessThanOrEqual(1);

    // 찾기 탭 = 지역·검색 · 꼬리말 숨김.
    await expect(page.locator('section.region')).toBeVisible();
    await expect(page.locator('section.search')).toBeVisible();
    await expect(page.locator('footer.foot')).toBeHidden();
    // 빈 건물 탭(👤 1번 「가」) — 흐린 탭 · 안내 둘 · 찾으러 가기(44px) → 찾기.
    await expect(tabButton(page, '건물')).toHaveClass(/tabbar__btn--dim/);
    await gotoTab(page, '건물');
    await expect(page.getByText('아직 고른 건물이 없습니다', { exact: true })).toBeVisible();
    await expect(page.getByText('찾기나 지도에서 건물을 고르면 여기에 층별 화면이 섭니다', { exact: true })).toBeVisible();
    await expect(page.locator('section.search')).toBeHidden();
    const go = page.getByRole('button', { name: '건물 찾으러 가기' });
    expect((await go.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await go.click();
    await expect(tabButton(page, '찾기')).toHaveAttribute('aria-current', 'page');
    // 지도 탭 = 지역 고르개(같은 하나) · 검색 없음 — 구를 고르기 전 그대로.
    await gotoTab(page, '지도');
    await expect(page.locator('section.region')).toBeVisible();
    await expect(page.locator('section.search')).toBeHidden();
    // 구를 고르면 지도 가득(W4b) — 지역 고르개는 위 띠를 눌러야 펼쳐진다(같은 하나 · 찾기 탭에선 그대로 보인다).
    await pickGu(page, '서울', '강남구');
    await expect(page.locator('.rstrip__btn')).toHaveText('서울 강남구 ▾');
    await expect(page.locator('section.region')).toBeHidden();
    await page.locator('.rstrip__btn').click();
    await expect(page.locator('section.region')).toBeVisible();
    await gotoTab(page, '찾기');
    await expect(page.locator('section.region')).toBeVisible();
    // 더보기 탭 = 역할 줄 → 의견함 → 안내 차례 · 맨 아래까지 내려도 막대에 안 가린다.
    await gotoTab(page, '더보기');
    await expect(page.locator('section.region')).toBeHidden();
    const foot = page.locator('footer.foot');
    await expect(foot).toBeVisible();
    const y = async (sel: string) => (await foot.locator(sel).first().boundingBox())!.y;
    expect(await y('section.role')).toBeLessThan(await y('.fb'));
    expect(await y('.fb')).toBeLessThan(await y('.foot__notice'));
    await page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)');
    const last = (await foot.locator('nav.family').boundingBox())!;
    expect(last.y + last.height).toBeLessThanOrEqual((await bar.boundingBox())!.y);
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
  });

  test('BM. 첫 탭 — 창업자 = 지도 · 건물 직행 링크 = 건물 · 중개사 탭 = 찾기·건물·뽑은 건물·더보기(지도는 찾기 탭 · 빈 안내)', async ({
    page,
  }, testInfo) => {
    const setRole = (r: string) =>
      page.addInitScript((v) => {
        const w = globalThis as unknown as { localStorage: { setItem(k: string, val: string): void } };
        w.localStorage.setItem('sangga.viewerRole', v);
      }, r);
    await mockOpenSigungu(page);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()]);
    await setRole('창업자');
    await page.goto('/');
    if (testInfo.project.name !== 'mobile') {
      // 넓은 화면은 아래 탭이 없다 — 창업자 첫 화면·건물 직행 링크·중개사 어느 쪽도 탭 막대 0(지금 화면 그대로).
      await expect(page.locator('section.region')).toBeVisible();
      await expect(page.locator('nav.tabbar')).toHaveCount(0);
      await page.goto(`/?sgg=11680&bld=${LINK_BLD}`);
      await expect(page.locator('section.stack').getByRole('heading', { name: '테스트빌딩' })).toBeVisible();
      await expect(page.locator('nav.tabbar')).toHaveCount(0);
      await setRole('중개사');
      await page.goto('/');
      await expect(page.locator('section.region')).toBeVisible();
      await expect(page.locator('nav.tabbar')).toHaveCount(0);
      return;
    }
    await expect(tabButton(page, '지도')).toHaveAttribute('aria-current', 'page');
    await expect(page.locator('section.region')).toBeVisible();
    await page.goto(`/?sgg=11680&bld=${LINK_BLD}`);
    await expect(tabButton(page, '건물')).toHaveAttribute('aria-current', 'page');
    await expect(page.locator('section.stack').getByRole('heading', { name: '테스트빌딩' })).toBeVisible();

    await setRole('중개사');
    await page.goto('/');
    const bar = page.getByRole('navigation', { name: '화면 고르기' });
    await expect(bar.getByRole('button')).toHaveText(['찾기', '건물', '뽑은 건물', '더보기']);
    await expect(tabButton(page, '찾기')).toHaveAttribute('aria-current', 'page');
    await pickGu(page, '서울', '강남구');
    await expect(page.getByRole('heading', { name: /강남구 상권 지도/ })).toBeVisible();
    await gotoTab(page, '뽑은 건물');
    await expect(page.getByText('아직 뽑은 건물이 없습니다', { exact: true })).toBeVisible();
    await expect(page.getByText('건물 화면에서 「인쇄 · PDF로 저장」을 누르면 여기에 남습니다', { exact: true })).toBeVisible();
    // 다른 탭에선 지도가 숨기만 한다(W4b — 같은 노드 · 찾기 탭으로 돌아오면 relayout) · 중개사엔 띠·지도 가득이 없다.
    await expect(page.locator('section.dmap')).toBeHidden();
    await expect(page.locator('.rstrip')).toHaveCount(0);
    await gotoTab(page, '찾기');
    await expect(page.locator('section.dmap .dmap__toggle')).toBeVisible();
  });

  test('BN. 뒤로가기 — 건물을 열 때만 한 칸(여럿 열어도 한 칸) · 뒤로 = 아까 탭(건물은 남음) · 앞으로 = 건물 · 넓은 화면은 칸 0', async ({
    page,
  }, testInfo) => {
    await mockOpenSigungu(page);
    // ⚠️ 둘째 건물 번호도 진짜 꼴(19자리_숫자)로 — 주소 쓰기는 꼴이 틀린 번호를 버린다(`urlState.ts` 의 BLD_RE).
    const OTHER = '1168010100100020000_2';
    await mockJson(page, SEARCH_PATTERN, [searchHit(), searchHit({ bld_id: OTHER, bld_nm: '다른빌딩' })]);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()]);
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    const len = () => page.evaluate(() => (globalThis as unknown as { history: { length: number } }).history.length);
    const before = await len();
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack .stack__head')).toBeVisible();
    if (testInfo.project.name !== 'mobile') {
      // PC 두 칸은 오른쪽 목록에서 고르면 한 칸(👤 2026-10-22 방법 나 R3 — 뒤로가기 = 목록 · CD 가 오가기를 본다). 같은 표식이라 여럿 열어도 한 칸.
      expect(await len()).toBe(before + 1);
      return;
    }
    expect(await len()).toBe(before + 1);
    await expect(tabButton(page, '건물')).toHaveAttribute('aria-current', 'page');
    // 찾기 탭에서 둘째 건물을 열어도 칸은 그대로 하나.
    await gotoTab(page, '찾기');
    await page.getByRole('button', { name: /다른빌딩/ }).click();
    await expect(tabButton(page, '건물')).toHaveAttribute('aria-current', 'page');
    expect(await len()).toBe(before + 1);
    // ⓘ 주소는 페이지 안에서 읽는다 — `page.url()` 은 같은 문서 안 주소 바꾸기(push/replace)를 늦게 따라올 수 있다.
    const bldNow = () =>
      page.evaluate(() =>
        new URLSearchParams((globalThis as unknown as { location: { search: string } }).location.search).get('bld'),
      );
    await expect.poll(bldNow).toBe(OTHER);

    await page.goBack();
    await expect(tabButton(page, '찾기')).toHaveAttribute('aria-current', 'page');
    await expect(page.locator('section.search')).toBeVisible();
    // 건물은 남는다(§7-1) · 주소는 지금 건물로 다시 적힌다.
    await expect(page.locator('section.stack')).toHaveCount(1);
    await expect.poll(bldNow).toBe(OTHER);
    await page.goForward();
    await expect(tabButton(page, '건물')).toHaveAttribute('aria-current', 'page');
    await expect(page.locator('section.stack .stack__head')).toBeVisible();
  });

  test('BO. 건물을 연 채 찾기·지도·더보기 탭에서 뽑아도 종이 = 건물 한 장 · 탭 막대·바 없음 · 안내 글은 남음', async ({ page }, testInfo) => {
    await openBuilding(page);
    if (testInfo.project.name !== 'mobile') {
      // 넓은 화면은 탭 막대가 없다 — 화면에도 종이에도 0(넓은 화면 종이의 나머지는 R·AY 가 본다).
      await expect(page.locator('nav.tabbar')).toHaveCount(0);
      await page.emulateMedia({ media: 'print' });
      await expect(page.locator('section.stack .stack__head')).toBeVisible();
      await expect(page.locator('nav.tabbar')).toHaveCount(0);
      await page.emulateMedia({ media: null });
      return;
    }
    for (const t of ['찾기', '지도', '더보기'] as const) {
      await gotoTab(page, t);
      await expect(page.locator('section.stack')).toBeHidden();
      await page.emulateMedia({ media: 'print' });
      await expect(page.locator('.printmeta')).toBeVisible();
      await expect(page.locator('section.stack .stack__head')).toBeVisible();
      await expect(page.locator('.card--floors .floor').first()).toBeVisible();
      await expect(page.locator('.foot__notice')).toBeVisible();
      await expect(page.locator('nav.tabbar')).toBeHidden();
      await expect(page.locator('section.dmap')).toBeHidden();
      await expect(page.locator('.search')).toBeHidden();
      await expect(page.locator('.fb')).toBeHidden();
      await page.emulateMedia({ media: null });
      await expect(page.locator('nav.tabbar')).toBeVisible();
    }
  });

  test('BP. 글 입력칸에 커서가 있으면(휴대폰 자판) 탭 막대가 숨고, 커서가 빠지면 돌아온다 · 라디오는 해당 없음', async ({ page }, testInfo) => {
    await mockOpenSigungu(page);
    await page.goto('/');
    const bar = page.locator('nav.tabbar');
    if (testInfo.project.name !== 'mobile') {
      // 넓은 화면은 탭 막대가 없다 — 검색창에 커서가 가도 0 그대로.
      await expect(page.getByLabel('건물명 또는 주소')).toBeVisible();
      await expect(bar).toHaveCount(0);
      await page.getByLabel('건물명 또는 주소').focus();
      await expect(bar).toHaveCount(0);
      return;
    }
    await expect(bar).toBeVisible();
    await page.getByLabel('건물명 또는 주소').focus();
    await expect(bar).toBeHidden();
    await page.getByLabel('건물명 또는 주소').blur();
    await expect(bar).toBeVisible();
    // 의견함 종류(라디오)를 눌러도 막대는 그대로(자판이 안 뜬다) · 글 칸에 커서면 숨는다.
    await gotoTab(page, '더보기');
    await page.getByRole('button', { name: '의견 보내기' }).click();
    await page.getByRole('radio', { name: '건의·제안' }).check();
    await expect(bar).toBeVisible();
    await page.locator('footer.foot').getByRole('textbox').focus();
    await expect(bar).toBeHidden();
  });

  test('BQ. 건물 없이 더보기 탭에서 뽑으면 종이에 입구가 되살아난다(넓은 화면 종이처럼) · 탭 막대 없음', async ({ page }, testInfo) => {
    await mockOpenSigungu(page);
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    const entryDisplay = () =>
      page.locator('#entry-panel').evaluate(
        (e) => (globalThis as unknown as { getComputedStyle(x: unknown): { display: string } }).getComputedStyle(e).display,
      );
    if (testInfo.project.name !== 'mobile') {
      // 넓은 화면은 입구를 숨긴 적이 없다 — 화면·종이 모두 입구가 서 있고 탭 막대 0.
      await page.emulateMedia({ media: 'print' });
      expect(await entryDisplay()).not.toBe('none');
      await expect(page.locator('nav.tabbar')).toHaveCount(0);
      await page.emulateMedia({ media: null });
      return;
    }
    await gotoTab(page, '더보기');
    await expect(page.locator('#entry-panel')).toBeHidden();
    await page.emulateMedia({ media: 'print' });
    // 탭이 숨긴 입구(`hidden`)를 종이에서 되살린다 — 건물이 없으면 지금처럼 입구(👤 W4a 「건물 한 장」의 짝 · 검사 🟡 F6).
    expect(await entryDisplay()).toBe('block');
    await expect(page.locator('nav.tabbar')).toBeHidden();
    await expect(page.locator('.foot__notice')).toBeVisible();
    await page.emulateMedia({ media: null });
    await expect(page.locator('#entry-panel')).toBeHidden();
  });
});

test.describe('검색 색인 보강 (결정 0042)', () => {
  test('BR. 건물 직행 — h1 은 건물 이름 하나 · 탭 제목에 동 구분 · 같은 땅 다른 동·구 내부 링크(진짜 href · 누르면 화면 안) · 종이에 링크 줄 없음 · 첫 화면은 사이트 이름 h1 + 구 칩 = 열린 구 수만큼 링크', async ({
    page,
  }) => {
    const gus = [
      { sido_code: '11', sido_nm: '서울', sigungu_code: '11680', sigungu_nm: '강남구', building_cnt: 14223 },
      { sido_code: '11', sido_nm: '서울', sigungu_code: '11440', sigungu_nm: '마포구', building_cnt: 9000 },
      { sido_code: '30', sido_nm: '대전', sigungu_code: '30170', sigungu_nm: '서구', building_cnt: 5000 },
    ];
    const OTHER = '1168010100100010000_1024999';
    await mockOpenSigungu(page, gus);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2, bld_cnt_in_pnu: 2 }), floorRow({ bld_cnt_in_pnu: 2 })]);
    const dong = (bld_id: string, dong_nm: string) => ({
      bld_id,
      bld_nm: '테스트빌딩',
      dong_nm,
      total_area_m2: 900,
      floor_cnt: 2,
      min_floor: 1,
      max_floor: 2,
      has_roof: false,
    });
    await mockJson(page, '**/rest/v1/rpc/list_parcel_buildings*', [dong(LINK_BLD, 'A동'), dong(OTHER, 'B동')]);

    await page.goto(`/?sgg=11680&bld=${LINK_BLD}`);
    const stack = page.locator('section.stack');
    await expect(page).toHaveTitle('테스트빌딩 A동 — 강남구 테헤란로 1 | 상가 층별 스택뷰');
    // 렌더 h1 도 같은 동 구분(보완 F3) · 정확히 1개.
    await expect(page.locator('h1')).toHaveCount(1);
    await expect(page.locator('h1')).toHaveText('테스트빌딩 A동');

    const links = stack.locator('nav.stack__links a');
    await expect(links).toHaveCount(2);
    await expect(links.nth(0)).toHaveText('테스트빌딩 B동');
    await expect(links.nth(0)).toHaveAttribute('href', `/?sgg=11680&bld=${OTHER}`);
    await expect(links.nth(1)).toHaveText('강남구 다른 건물 찾기');
    await expect(links.nth(1)).toHaveAttribute('href', '/?sgg=11680');
    expect(await page.locator('a[href^="/?sgg="]').count()).toBeGreaterThanOrEqual(1);

    // 종이에는 누르는 문이 없다 — 머리의 링크 줄은 숨고, 첫 HTML 링크 묶음(.seo-links)은 React 가 이미 덮었다.
    await page.emulateMedia({ media: 'print' });
    await expect(stack.locator('nav.stack__links')).toBeHidden();
    await expect(stack.getByRole('heading', { level: 1, name: '테스트빌딩 A동' })).toBeVisible();
    await expect(page.locator('.seo-links')).toHaveCount(0);
    await page.emulateMedia({ media: null });

    // 보통 누름 = 화면 안에서 그 동으로(새로 읽지 않는다 — 창 표식이 남는다) · 주소가 따라 적힌다.
    await page.evaluate(() => {
      (globalThis as unknown as { __noReload: number }).__noReload = 1;
    });
    await links.nth(0).click();
    await expect.poll(() => new URL(page.url()).search).toContain(`bld=${OTHER}`);
    expect(await page.evaluate(() => (globalThis as unknown as { __noReload?: number }).__noReload)).toBe(1);
    await expect(page).toHaveTitle('테스트빌딩 B동 — 강남구 테헤란로 1 | 상가 층별 스택뷰');
    await expect(page.locator('h1')).toHaveText('테스트빌딩 B동');

    // 첫 화면 — h1 은 사이트 이름 하나 · 지역 고르개의 구 칩이 열린 구 수만큼 진짜 링크(펼치지 않은 시도 것도 DOM 에).
    await page.goto('/');
    await expect(page.locator('h1')).toHaveCount(1);
    await expect(page.locator('h1')).toHaveText('상가 층별 스택뷰');
    await expect(page.locator('a[href^="/?sgg="]')).toHaveCount(gus.length);
    await pickGu(page, '서울', '마포구');
    await expect.poll(() => new URL(page.url()).search).toBe('?sgg=11440');
  });

  test('BS. 휴대폰의 같은 땅 다른 동 = 첫 줄 「같은 땅 다른 동 (외 N동)」 + 한 줄 칩(44px · 옆으로 밀기 · 점 없음 · 페이지 가로 넘침 0 · 키보드로 옮기면 칩 줄이 따라 밀림) · 넓은 화면은 그대로(점·글자 링크) · 종이에 없음', async ({
    page,
  }, testInfo) => {
    const mobile = testInfo.project.name === 'mobile';
    // 운영 실측(헬리오시티 168동 · 링크 줄 312px)과 같은 폭.
    if (mobile) await page.setViewportSize({ width: 390, height: 844 });
    await mockOpenSigungu(page);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2, bld_cnt_in_pnu: 14 }), floorRow({ bld_cnt_in_pnu: 14 })]);
    const dongs = Array.from({ length: 14 }, (_, i) => ({
      bld_id: i === 0 ? LINK_BLD : `1168010100100010000_10249${String(i).padStart(2, '0')}`,
      bld_nm: '테스트빌딩',
      dong_nm: `${101 + i}동`,
      total_area_m2: 900 - i,
      floor_cnt: 2,
      min_floor: 1,
      max_floor: 2,
      has_roof: false,
    }));
    await mockJson(page, '**/rest/v1/rpc/list_parcel_buildings*', dongs);

    await page.goto(`/?sgg=11680&bld=${LINK_BLD}`);
    const nav = page.locator('section.stack nav.stack__links');
    // 링크 수·글자는 그대로 — 다른 동 10 + 구 찾기 1(두 벌을 그리지 않는다 · 낭독기에 같은 글이 두 번 안 나온다).
    await expect(nav.locator('a')).toHaveCount(11);
    const row = nav.locator('.stack__links-row').first();
    await expect(row).toHaveText('같은 땅 다른 동: ' + [102, 103, 104, 105, 106, 107, 108, 109, 110, 111].map((n) => `테스트빌딩 ${n}동`).join(' · ') + ' 외 3동');
    await expect(nav.locator('.stack__links-row').nth(1)).toHaveText('강남구 다른 건물 찾기');
    await nav.screenshot({ path: testInfo.outputPath(`bs-nav-${testInfo.project.name}.png`) });
    await page.locator('section.stack header.stack__head').screenshot({ path: testInfo.outputPath(`bs-head-${testInfo.project.name}.png`) });

    const shape = await row.evaluate((el) => {
      const win = el.ownerDocument.defaultView!;
      // ⓘ 이 파일은 DOM 타입을 안 켠다 — 쓰는 모양만 적는다.
      const box = (n: { getBoundingClientRect(): { top: number; bottom: number; left: number; right: number; height: number } }) => {
        const b = n.getBoundingClientRect();
        return { top: b.top, bottom: b.bottom, left: b.left, right: b.right, h: b.height, mid: (b.top + b.bottom) / 2 };
      };
      const chips = el.querySelector('.stack__links-chips')!;
      const more = el.querySelector('.stack__links-more')!;
      return {
        row: box(el),
        lead: box(el.querySelector('.stack__links-lead')!),
        more: box(more),
        chipsBox: box(chips),
        chips: [...el.querySelectorAll('a.stack__links-a')].map((a) => ({ ...box(a), bg: win.getComputedStyle(a).backgroundColor })),
        sepShown: [...el.querySelectorAll('.stack__links-sep')].map((s) => win.getComputedStyle(s).display !== 'none'),
        leadFont: win.getComputedStyle(el.querySelector('.stack__links-lead')!).fontSize,
        leadBefore: win.getComputedStyle(el.querySelector('.stack__links-lead')!, '::before').content,
        moreBefore: win.getComputedStyle(more, '::before').content,
        moreAfter: win.getComputedStyle(more, '::after').content,
        chipsOver: chips.scrollWidth - chips.clientWidth,
        overflowX: win.getComputedStyle(chips).overflowX,
      };
    });
    expect(shape.chips).toHaveLength(10);
    expect(shape.sepShown).toHaveLength(9);
    if (mobile) {
      testInfo.annotations.push({ type: '다른 동 줄 높이(px)', description: String(shape.row.h) });
      // 한 줄 칩 — 운영 312px 대비 60~110px · 칩은 모두 같은 줄(줄바꿈 0) · 칩마다 44px 이상 · 둥근 바탕.
      expect(shape.row.h).toBeGreaterThanOrEqual(60);
      expect(shape.row.h).toBeLessThanOrEqual(110);
      for (const c of shape.chips) {
        expect(Math.abs(c.top - shape.chips[0].top)).toBeLessThan(1);
        expect(c.h).toBeGreaterThanOrEqual(44);
        expect(c.bg).not.toBe('rgba(0, 0, 0, 0)');
      }
      // 첫 줄 = 「같은 땅 다른 동」 + 「(외 3동)」 같은 줄 · 칩 줄은 그 아래 · 점(·)과 쌍점(:)은 안 보인다.
      expect(Math.abs(shape.lead.mid - shape.more.mid)).toBeLessThan(2);
      expect(shape.more.left).toBeGreaterThan(shape.lead.right);
      expect(shape.chipsBox.top).toBeGreaterThanOrEqual(shape.lead.bottom);
      expect(shape.sepShown.every((s) => !s)).toBe(true);
      // 쌍점 없는 첫 줄 = 원래 글(「같은 땅 다른 동:」)은 0 크기 · `::before` 가 쌍점 없이 다시 쓴다(낭독기용 대체 글은 빈 글).
      expect(shape.leadFont).toBe('0px');
      expect(shape.leadBefore).toBe('"같은 땅 다른 동" / ""');
      expect(shape.lead.right - shape.lead.left).toBeGreaterThan(50);
      expect([shape.moreBefore, shape.moreAfter]).toEqual(['"("', '")"']);
      // 칩 줄만 옆으로 밀린다 — 넘치는 칩이 있고(양성 대조) 페이지는 가로로 안 밀린다.
      expect(shape.overflowX).toBe('auto');
      expect(shape.chipsOver).toBeGreaterThan(0);
      expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
      // 키보드 — 마지막 칩에 초점을 주면 칩 줄이 따라 밀려 그 칩이 보인다.
      const last = row.locator('a.stack__links-a').last();
      await last.focus();
      await expect(last).toBeFocused();
      expect(await row.locator('.stack__links-chips').evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
      await expect(last).toBeInViewport();
    } else {
      // 넓은 화면은 그대로 — 점·쌍점이 보이고, 「외 3동」은 괄호 없이 끝에 · 링크에 바탕 없음 · 칩 줄 넘침 없음.
      expect(shape.sepShown.every((s) => s)).toBe(true);
      expect(shape.leadBefore).toBe('none');
      expect(shape.leadFont).toBe('14px');
      expect([shape.moreBefore, shape.moreAfter]).toEqual(['none', 'none']);
      for (const c of shape.chips) expect(c.bg).toBe('rgba(0, 0, 0, 0)');
      expect(shape.overflowX).toBe('visible');
    }

    // 종이에는 누르는 문이 없다(두 폭 모두).
    await page.emulateMedia({ media: 'print' });
    await expect(nav).toBeHidden();
    await page.emulateMedia({ media: null });
  });
});

// ── 휴대폰 지도 가득 · 끌어올리는 상권 판 · 홈 화면 안내 (👤 2026-10-19 결정 0039 W4b) ─────────────────────────────
// ⓘ E2E 에는 카카오 키가 없다 — 지도 칸은 안내 글뿐이고, 띠·판·칩 줄·자리·종이는 여기서 본다(relayout 배선은 `DistrictMap.test`).
test.describe('휴대폰 지도 가득 · 상권 판 · 홈 화면 안내 (결정 0039 W4b)', () => {
  /** 상권 경계 파일 목업 — 강남구 3곳 · 서초구 2곳(실제 파일의 상권 수가 바뀌어도 시험이 안 흔들리게). */
  async function mockDistricts(page: Page) {
    const sq = (id: string, gu: string, x: number) => ({
      type: 'Feature',
      geometry: {
        type: 'Polygon',
        coordinates: [[[x, 37.5], [x + 0.01, 37.5], [x + 0.01, 37.51], [x, 37.51], [x, 37.5]]],
      },
      properties: {
        district_id: id,
        district_nm: `상권${id}`,
        district_type: '골목상권',
        source_nm: '서울특별시 상권분석서비스',
        sigungu_code: gu,
        area_m2: 1,
      },
    });
    await page.route('**/districts.geojson', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          type: 'FeatureCollection',
          meta: { district_cnt: 5, max_computed_at: '2026-10-01T00:00:00Z' },
          features: [
            sq('a', '11680', 127.0),
            sq('b', '11680', 127.02),
            sq('c', '11680', 127.04),
            sq('d', '11650', 127.06),
            sq('e', '11650', 127.08),
          ],
        }),
      }),
    );
  }

  test('BT. 휴대폰 지도 탭 = 위 띠 「서울 강남구 ▾」 + 지도 가득(화면 70% 이상) · 칩 여섯 한 줄 옆으로 밀기 · 판 엿보기 → 반 → 가득 → 엿보기 · 띠로 다른 구 · 탭을 옮겨도 같은 지도 · 가로 넘침 0 · 종이에 띠·칩·손잡이 없음(판 안 범례·출처는 남음) · 넓은 화면은 그대로', async ({
    page,
  }, testInfo) => {
    await mockOpenSigungu(page, [
      { sido_code: '11', sido_nm: '서울', sigungu_code: '11680', sigungu_nm: '강남구', building_cnt: 14223 },
      { sido_code: '11', sido_nm: '서울', sigungu_code: '11650', sigungu_nm: '서초구', building_cnt: 9000 },
    ]);
    await mockDistricts(page);
    await page.addInitScript(() => {
      const w = globalThis as unknown as { localStorage: { setItem(k: string, v: string): void } };
      w.localStorage.setItem('sangga.viewerRole', '창업자');
    });
    await page.goto('/?sgg=11680');

    if (testInfo.project.name !== 'mobile') {
      // 넓은 화면 = 지금 그대로 — 지도 카드(제목·접기 단추·칩 밑 설명) · 띠·지도 가득·판 0.
      await expect(page.locator('section.dmap .dmap__toggle')).toBeVisible();
      await expect(page.locator('.dmap__head .chips__note')).toBeVisible();
      await expect(page.locator('.rstrip')).toHaveCount(0);
      await expect(page.locator('.app--mapfull')).toHaveCount(0);
      await expect(page.locator('.dsheet')).toHaveCount(0);
      // PC 두 칸(W5 보완 D2)은 구가 정해지면 칩 상자를 「서울 강남구 · 바꾸기」 한 줄로 접는다 · 한 열(721~1023)은 칩 상자 그대로.
      if (await isTwoCols(page)) {
        await expect(page.locator('.regionfold')).toBeVisible();
        await expect(page.locator('.regionfold__place')).toHaveText('서울 강남구');
        await expect(page.locator('section.region')).toBeHidden();
      } else {
        await expect(page.locator('section.region')).toBeVisible();
      }
      return;
    }

    const vh = page.viewportSize()!.height;
    const box = async (sel: string) => (await page.locator(sel).boundingBox())!;
    await expect(tabButton(page, '지도')).toHaveAttribute('aria-current', 'page');
    const strip = page.locator('.rstrip__btn');
    await expect(strip).toHaveText('서울 강남구 ▾');
    await expect(strip).toHaveAttribute('aria-expanded', 'false');
    expect((await box('.rstrip__btn')).height).toBeGreaterThanOrEqual(44);
    // 지도 탭에서는 사이트 제목·소개 한 줄이 안 보이고 · 지역 고르개는 띠를 눌러야.
    await expect(page.locator('.app__head')).toBeHidden();
    await expect(page.locator('section.region')).toBeHidden();
    await expect(page.locator('.dmap__toggle')).toHaveCount(0);
    // 지도 가득 — 덩어리도 지도 칸도 화면의 70% 이상(키가 없어 칸 안은 안내 글) · 칩 줄은 칩 44px + 선 1px(W4b 보완 C1).
    expect((await box('section.dmap')).height).toBeGreaterThanOrEqual(0.7 * vh);
    expect((await box('.dmap__canvas')).height).toBeGreaterThanOrEqual(0.7 * vh);
    expect((await box('.dmap__head')).height).toBeLessThanOrEqual(45);    // 지도를 끄는 손가락이 쪽을 당기지 않는다(C3 · 뿌리 html 까지) · 흐름에 남는 것은 띠 아래에서 시작(C4).
    await expect(page.locator('html')).toHaveCSS('overscroll-behavior-y', 'none');
    await expect(page.locator('.app--mapfull')).toHaveCSS('padding-top', '48px');

    // 칩 여섯 = 한 줄(같은 높이) · 칩 줄만 옆으로 밀린다 · 칩 밑 설명 글은 숨음 · 칩 44px.
    const chipBtns = page.locator('.dmap__head .chips__chip');
    await expect(chipBtns).toHaveCount(6);
    const ys: number[] = [];
    for (const c of await chipBtns.all()) {
      const b = (await c.boundingBox())!;
      ys.push(b.y);
      expect(b.height).toBeGreaterThanOrEqual(44);
    }
    expect(Math.max(...ys) - Math.min(...ys)).toBeLessThanOrEqual(1);
    await expect(page.locator('.dmap__head .chips__list')).toHaveCSS('overflow-x', 'auto');
    await expect(page.locator('.chips__note')).toBeHidden();

    // 판 — 엿보기 한 줄(구 이름 · 상권 수) → 반(화면 40% 이상 · 지도 칸은 판 위에서 끝남) → 가득(띠 바로 아래) → 엿보기.
    const sheet = page.locator('.dsheet');
    const handle = sheet.locator('.dsheet__handle');
    await expect(sheet.locator('.dsheet__title')).toHaveText('강남구 상권 3곳');
    await expect(sheet.locator('.dsheet__hint')).toHaveText('지도를 누르면 그 자리 상권');
    await expect(handle).toHaveAttribute('aria-label', '상권 판 펼치기');
    const hb = (await handle.boundingBox())!;
    expect(hb.height).toBeGreaterThanOrEqual(44);
    expect(hb.width).toBeGreaterThanOrEqual(44);
    expect((await box('.dsheet')).height).toBeLessThan(0.15 * vh);
    await expect(sheet.locator('.dmap__src')).toBeHidden();

    await handle.click();
    await expect(handle).toHaveAttribute('aria-label', '상권 판 더 펼치기');
    expect((await box('.dsheet')).height).toBeGreaterThanOrEqual(0.4 * vh);
    const canvas = await box('.dmap__canvas');
    expect(canvas.y + canvas.height).toBeLessThanOrEqual((await box('.dsheet')).y + 1); // 판이 지도를 안 덮는다(로고 자리)
    await expect(sheet.locator('.dmap__src')).toHaveText('출처: 서울특별시 상권분석서비스');
    await expect(sheet.getByRole('button', { name: '접기' })).toBeVisible();

    await handle.click();
    await expect(handle).toHaveAttribute('aria-label', '상권 판 접기');
    const stripBox = await box('.rstrip');
    expect(Math.abs((await box('.dsheet')).y - (stripBox.y + stripBox.height))).toBeLessThanOrEqual(1);
    await handle.click();
    await expect(handle).toHaveAttribute('aria-label', '상권 판 펼치기');

    // 띠 → 지역 고르개(같은 하나)가 띠 아래로 · 다른 구를 고르면 닫히고 띠 글이 그 구 · 판은 그 구의 수.
    await strip.click();
    await expect(strip).toHaveAttribute('aria-expanded', 'true');
    await expect(page.locator('section.region')).toBeVisible();
    const seocho = page.getByRole('button', { name: /^서초구/ });
    if (!(await seocho.isVisible())) await page.getByRole('button', { name: /^서울$/ }).click();
    await seocho.click();
    await expect(strip).toHaveText('서울 서초구 ▾');
    await expect(strip).toHaveAttribute('aria-expanded', 'false');
    await expect(page.locator('section.region')).toBeHidden();
    await expect(sheet.locator('.dsheet__title')).toHaveText('서초구 상권 2곳');

    // 탭을 옮겨도 지도를 다시 그리지 않는다 — 같은 노드가 숨었다가 다시 보인다(결정 0039 §4-11 · relayout 은 DistrictMap 시험).
    await page
      .locator('section.dmap')
      .evaluate((e) => (e as unknown as { setAttribute(k: string, v: string): void }).setAttribute('data-w4b-mark', '1'));
    await gotoTab(page, '찾기');
    await expect(page.locator('section.dmap[data-w4b-mark="1"]')).toBeHidden();
    await expect(page.locator('section.region')).toBeVisible();
    await expect(page.locator('.rstrip')).toHaveCount(0);
    await expect(page.locator('.app__head')).toBeVisible();
    await gotoTab(page, '지도');
    await expect(page.locator('section.dmap[data-w4b-mark="1"]')).toBeVisible();
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);

    // 종이(건물 없음) — 띠·칩 줄·판의 손잡이·안내가 빠지고, 판 안 범례·출처(공공누리 출처표시)는 남는다 · 판은 흐름(W4b 보완 A3).
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('.rstrip')).toBeHidden();
    await expect(page.locator('.chips')).toBeHidden();
    await expect(sheet.locator('.dsheet__handle')).toBeHidden();
    await expect(sheet.locator('.dsheet__hint')).toBeHidden();
    await expect(sheet.locator('.dsheet__title')).toHaveText('서초구 상권 2곳');
    await expect(sheet.locator('.dmap__legend')).toBeVisible();
    await expect(sheet.locator('.dmap__src')).toHaveText('출처: 서울특별시 상권분석서비스');
    await expect(sheet.locator('.dmap__src')).toBeVisible();
    await expect(sheet).toHaveCSS('position', 'static');
    await page.emulateMedia({ media: null });
    await expect(page.locator('.rstrip')).toBeVisible();
  });

  test('BU. 더보기 탭 「홈 화면에 두고 앱처럼 쓰기」 — 두 줄 글자 그대로 · 의견함 다음·안내 앞 · 단추 0 → 크롬 설치 이벤트가 오면 「홈 화면에 추가」(44px) → 누르면 그 창 1회 → 단추 사라짐 · 종이에 없음 · 넓은 화면은 상자 0', async ({
    page,
  }, testInfo) => {
    await mockOpenSigungu(page);
    await page.goto('/');
    const hint = page.locator('.hshint');
    if (testInfo.project.name !== 'mobile') {
      await expect(page.locator('footer.foot .foot__notice')).toBeVisible();
      await expect(hint).toHaveCount(0);
      return;
    }
    await gotoTab(page, '더보기');
    await expect(hint.locator('.hshint__h')).toHaveText('홈 화면에 두고 앱처럼 쓰기');
    await expect(hint.locator('li')).toHaveText([
      '아이폰 Safari: 공유 단추 → 「홈 화면에 추가」',
      '안드로이드 크롬: 더보기(⋮) → 「설치 및 바로가기 만들기」',
    ]);
    await expect(hint.getByRole('button')).toHaveCount(0);
    const y = async (sel: string) => (await page.locator(sel).first().boundingBox())!.y;
    expect(await y('footer.foot .fb')).toBeLessThan(await y('.hshint'));
    expect(await y('.hshint')).toBeLessThan(await y('footer.foot .foot__notice'));

    // 크롬이 설치 창 이벤트를 준 것처럼(prompt 흉내) — 단추가 서고, 누르면 그 창을 한 번 띄운 뒤 단추만 사라진다.
    await page.evaluate(() => {
      const g = globalThis as unknown as {
        Event: new (t: string, o?: { cancelable?: boolean }) => object;
        dispatchEvent(e: object): boolean;
        w4bPrompted: number;
      };
      g.w4bPrompted = 0;
      const ev = new g.Event('beforeinstallprompt', { cancelable: true }) as { prompt?: () => Promise<void> };
      ev.prompt = () => {
        g.w4bPrompted += 1;
        return Promise.resolve();
      };
      g.dispatchEvent(ev);
    });
    const btn = hint.getByRole('button', { name: '홈 화면에 추가' });
    await expect(btn).toBeVisible();
    expect((await btn.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await expect(hint.locator('li').nth(1)).toHaveText(
      '안드로이드 크롬: 아래 단추를 누르거나 더보기(⋮) → 「설치 및 바로가기 만들기」',
    );
    await btn.click();
    expect(await page.evaluate(() => (globalThis as unknown as { w4bPrompted: number }).w4bPrompted)).toBe(1);
    await expect(hint.getByRole('button')).toHaveCount(0);

    await page.emulateMedia({ media: 'print' });
    await expect(hint).toBeHidden();
    await page.emulateMedia({ media: null });
    await expect(hint).toBeVisible();
  });
});

// ── PC 두 칸 (결정 0039 Q5 · W5 · §4-13 · 👤 2026-10-21 4건) ─────────────────────────────────────────────
// 1024px 이상(chromium 판 1280×720)에서만 선다 — 휴대폰(mobile 판)은 두 칸 이름표·새 단추 0 을 보고 끝난다(skip 0).
// 배선(이름표·`inert`·같은 노드·체크란)은 vitest(`App.wide.test.tsx`)도 본다 — 여기서만 보이는 것은 **칸의 실제 자리
// (1/3 · 56px 띠 · 화면에 붙음) · 가로 넘침 · 종이**다. ⓘ E2E 엔 카카오 키가 없어 지도 칸은 안내 글뿐(지도 그림의 종이 모양은 못 본다).
test.describe('PC 두 칸', () => {
  async function openTall(page: Page) {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    // 층이 많은 건물 — 오른쪽 칸이 화면보다 훨씬 길어야 '왼쪽은 화면에 붙음'을 잴 수 있다.
    await mockFloorStack(page, [], Array.from({ length: 24 }, (_, i) => floorRow({ floor_no: i + 1 })));
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
  }

  async function phoneHasNoCols(page: Page) {
    await expect(page.locator('nav.tabbar')).toHaveCount(1);
    for (const sel of ['.app--wide', '.app--lcollapsed', '.entry__fold', '.lrail', '.mapprint', '.rpane-empty']) {
      await expect(page.locator(sel), sel).toHaveCount(0);
    }
  }

  test('BV. 1280 두 칸 — 왼쪽 ≈ 1/3 · 오른쪽 건물 · 건물을 열어도 같은 지도 · 「왼쪽 칸 접기」 → 56px 띠(건물 칸 넓어짐) → 펼치면 같은 지도 · 왼쪽은 화면에 붙음 · 가로 넘침 0 · 1366×768 건물 이름 첫 화면 · 1023 은 지금 한 열', async ({
    page,
  }, testInfo) => {
    await openTall(page);
    if (testInfo.project.name === 'mobile') {
      await phoneHasNoCols(page);
      return;
    }
    await expect(page.locator('.app')).toHaveClass(/app--wide/);
    // 건물 없음 = 오른쪽 안내 한 줄(👤 「가」 — 글자 그대로) · 「위에서…」 줄 없음.
    await expect(page.locator('.rpane-empty')).toHaveText('왼쪽에서 건물을 고르면 여기에 층별 화면이 섭니다');
    await expect(page.getByText('위에서 건물을 검색해 선택해 주세요.')).toHaveCount(0);
    const map = page.locator('section.dmap');
    await expect(map).toBeVisible();
    await map.evaluate((el) => el.setAttribute('data-w5-mark', '1'));

    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    const stack = page.locator('section.stack');
    await expect(stack.getByRole('heading', { name: '테스트빌딩' })).toBeVisible();

    // ① 자리 — 왼쪽 칸 오른쪽 끝 < 건물 칸 왼쪽 끝 · 왼쪽 폭 ≈ (본문 폭 − 틈 24) ÷ 3 ± 20px · 바 없음 · 같은 지도 노드가 보임(Q5).
    const box = async (sel: string) => (await page.locator(sel).first().boundingBox())!;
    const left = await box('.entry');
    const right = await box('section.stack');
    const main = await box('.app__main');
    expect(left.x + left.width).toBeLessThan(right.x);
    expect(Math.abs(left.width - (main.width - 24) / 3)).toBeLessThanOrEqual(20);
    expect(left.y).toBeLessThanOrEqual(right.y + 1); // 두 칸이 같은 줄에서 시작한다(아래로 쌓이지 않음)
    await expect(page.locator('.entrybar')).toHaveCount(0);
    await expect(page.locator('section.dmap[data-w5-mark="1"]')).toBeVisible();
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);

    // ② 왼쪽은 화면에 붙는다 — 건물 칸 끝(층별 화면 맨 아래)까지 굴려도 왼쪽 칸 위가 화면 안(0 이상) · 지도·검색이 늘 보임.
    //    ⓘ 꼬리말(두 칸 아래 전체 폭)까지 내려가면 왼쪽 칸도 제 자리(본문 grid 칸)를 따라 올라간다 — sticky 의 원래 동작.
    await page.evaluate(
      'window.scrollTo(0, window.scrollY + document.querySelector("section.stack").getBoundingClientRect().bottom - window.innerHeight)',
    );
    expect(await page.evaluate(() => (globalThis as unknown as { scrollY: number }).scrollY)).toBeGreaterThan(500);
    const stackEnd = await box('section.stack');
    expect(Math.abs(stackEnd.y + stackEnd.height - page.viewportSize()!.height)).toBeLessThanOrEqual(2); // 정말 건물 칸 끝이다
    const stuck = await box('.entry');
    expect(stuck.y).toBeGreaterThanOrEqual(0);
    expect(stuck.y).toBeLessThanOrEqual(20);
    await expect(page.getByLabel('건물명 또는 주소')).toBeInViewport();
    expect(await page.locator('.entry').evaluate((el) => el.ownerDocument.defaultView!.getComputedStyle(el).overflowY)).toBe('auto');
    await page.evaluate('window.scrollTo(0, 0)');

    // ③ 「왼쪽 칸 접기」(44px) → 56px 띠 · 건물 칸이 넓어진다 · 띠 단추 44px · 구 이름 세로 글.
    const fold = page.getByRole('button', { name: '왼쪽 칸 접기' });
    expect((await fold.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await fold.click();
    await expect(page.locator('.entry')).toBeHidden();
    const rail = await box('.lrail');
    expect(Math.round(rail.width)).toBe(56);
    expect((await box('section.stack')).width).toBeGreaterThan(right.width + 250);
    for (const b of await page.locator('.lrail').getByRole('button').all()) {
      expect((await b.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
    await expect(page.locator('.lrail__place')).toHaveText('서울 강남구');
    expect(await page.locator('.lrail__place').evaluate((el) => el.ownerDocument.defaultView!.getComputedStyle(el).writingMode)).toBe('vertical-rl');
    await expect(page.getByRole('button', { name: '왼쪽 칸 펼치기' })).toBeFocused();
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);

    // ④ 펼치면 같은 지도 노드 그대로(언마운트 0) · 커서는 「왼쪽 칸 접기」.
    await page.getByRole('button', { name: '왼쪽 칸 펼치기' }).click();
    await expect(page.locator('.lrail')).toHaveCount(0);
    await expect(page.locator('section.dmap[data-w5-mark="1"]')).toBeVisible();
    await expect(fold).toBeFocused();
    await page.screenshot({ path: testInfo.outputPath('bv-two-cols-1280.png') });

    // ⑤ 흔한 노트북 1366×768 — 건물 이름이 문서 맨 위 첫 화면 안(S1 의 AY ① 과 같은 잣대).
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.evaluate('window.scrollTo(0, 0)');
    const title = (await stack.getByRole('heading', { name: '테스트빌딩' }).boundingBox())!;
    expect(title.y + title.height).toBeLessThanOrEqual(768);

    // ⑥ 1024×768(두 칸 가장 좁은 폭 · W5 보완 F2) — 층 줄이 오른쪽 칸 안 · 문서 가로 넘침 0 · 왼쪽 칸 안 가로 넘침 0.
    //   (화면 밖 표지 이름 숨김(F4)은 지도 키가 없어 여기선 못 본다 — vitest CSS 가드.)
    await page.setViewportSize({ width: 1024, height: 768 });
    await expect(page.locator('.app')).toHaveClass(/app--wide/);
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBe(0);
    expect(await page.locator('.entry').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    const narrowStack = await box('section.stack');
    // ⓘ 11줄 이상이면 화면엔 10줄만 선다(BB) — 보이는 줄만 잰다(숨은 줄은 상자가 없다).
    const rows = page.locator('section.stack .floor__row:visible');
    expect(await rows.count()).toBeGreaterThan(0);
    for (const row of await rows.all()) {
      const r = (await row.boundingBox())!;
      expect(r.x + r.width).toBeLessThanOrEqual(narrowStack.x + narrowStack.width + 0.5);
      expect(await row.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    }
    await page.screenshot({ path: testInfo.outputPath('bv-two-cols-1024.png'), fullPage: false });

    // ⑦ 1023 — 두 칸이 아니다: 지금 한 열(건물을 연 채라 S1 바 · 입구 숨김 · 지도 안 그림).
    await page.setViewportSize({ width: 1023, height: 720 });
    await expect(page.locator('.app')).not.toHaveClass(/app--wide/);
    await expect(page.locator('.entrybar')).toBeVisible();
    await expect(page.locator('.entry')).toBeHidden();
    await expect(page.locator('section.dmap')).toHaveCount(0);
    await expect(page.locator('.entry__fold')).toHaveCount(0);
    await expect(page.locator('.mapprint')).toHaveCount(0);
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
  });

  test('BW. 종이 — 두 칸에서 체크란 끔 = 오른쪽(건물)만 · 「상권 지도 넣기」 켬 = 지도 덩어리만 더(역할·지역·검색은 빠짐 · 띠로 접은 채여도) · 체크란·접기 단추는 종이에 없음 · 1023 은 지금 규칙', async ({
    page,
  }, testInfo) => {
    await openTall(page);
    if (testInfo.project.name === 'mobile') {
      await phoneHasNoCols(page);
      return;
    }
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    const stack = page.locator('section.stack');
    await expect(stack.getByRole('heading', { name: '테스트빌딩' })).toBeVisible();
    const box = page.getByRole('checkbox', { name: '상권 지도 넣기' });
    await expect(box).not.toBeChecked();
    expect((await page.locator('.mapprint').boundingBox())!.height).toBeGreaterThanOrEqual(44);

    // ① 끔(기본) — 종이 = 건물만: 왼쪽 칸(지도 포함) 통째 빠짐 · 종이 머리글·층별 화면은 남음.
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('.entry')).toBeHidden();
    await expect(page.locator('section.dmap')).toBeHidden();
    await expect(stack).toBeVisible();
    await expect(page.locator('.printmeta')).toBeVisible();
    await expect(page.locator('.mapprint')).toBeHidden();
    expect(await page.locator('.app__main').evaluate((el) => el.ownerDocument.defaultView!.getComputedStyle(el).display)).toBe('block'); // 종이에선 grid 풀림
    await page.emulateMedia({ media: null });

    // ② 켬 — 종이에 지도 덩어리(제목)만 더 · 역할·지역·검색·접기 단추·지도 접기 단추는 빠짐 · 차례 = 지도 → 건물.
    await box.check();
    await expect(page.locator('.app')).toHaveClass(/app--printmap/);
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('section.dmap')).toBeVisible();
    await expect(page.getByRole('heading', { name: /강남구 상권 지도/ })).toBeVisible();
    for (const sel of ['.role', '.region', '.search', '.entry__fold', '.dmap__toggle', '.mapprint']) {
      await expect(page.locator(sel).first(), sel).toBeHidden();
    }
    await expect(stack).toBeVisible();
    const y = async (sel: string) => (await page.locator(sel).first().boundingBox())!.y;
    expect(await y('section.dmap')).toBeLessThan(await y('section.stack'));
    await page.emulateMedia({ media: null });

    // ③ 켠 채 왼쪽을 띠로 접어도 종이엔 지도(숨은 지도를 종이에서 되살린다) · 띠는 종이에 없음.
    await page.getByRole('button', { name: '왼쪽 칸 접기' }).click();
    await expect(page.locator('section.dmap')).toBeHidden();
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('section.dmap')).toBeVisible();
    await expect(page.locator('.lrail')).toBeHidden();
    await page.emulateMedia({ media: null });
    await page.getByRole('button', { name: '왼쪽 칸 펼치기' }).click();

    // ④ 다시 끄면 종이 = 건물만.
    await box.uncheck();
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('section.dmap')).toBeHidden();
    await page.emulateMedia({ media: null });

    // ⑤ 1023(한 열) — 체크란 없음 · 지금 10-15 규칙: 접힌 채면 지도 안 그림(종이에도 없음) · 「상권 지도 보기」로 펼치면 종이에 나온다.
    await page.setViewportSize({ width: 1023, height: 720 });
    await expect(page.locator('.mapprint')).toHaveCount(0);
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('section.dmap')).toHaveCount(0);
    await page.emulateMedia({ media: null });
    await unfoldEntry(page, '상권 지도 보기');
    await expect(page.locator('section.dmap')).toBeVisible();
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('section.dmap')).toBeVisible();
    await page.emulateMedia({ media: null });
  });

  /*
    왼쪽 칸 다듬기(👤 2026-10-22 「가」) — 목록 줄 두 줄(이름 전체 · 말줄임 0) · 주소는 길 이름부터 · 안쪽 굴림 0(왼쪽 칸 굴림 하나) ·
    검색칸 안내 글 짧게(잘림 0). ⓘ 상권 건물 목록·화면 밖 표지는 지도 키가 없어 여기서 안 선다 → vitest CSS 가드(App.wide.test).
  */
  test('CC. 왼쪽 칸 다듬기 — 1280·1024 두 칸: 안내 글 잘림 0 · 예시 줄 · 주소 길 이름부터 · 왼쪽 칸엔 목록 0(→ CD 오른쪽 표) · 가로 넘침 0 · 1000 한 열 · 휴대폰은 그대로', async ({
    page,
  }, testInfo) => {
    // 왼쪽 칸(약 370px 글 자리)보다 긴 이름 — 1280 에서도 한 줄에 안 들어가 두 줄로 넘어가야 한다.
    const LONG = '아주아주긴이름의강남역삼테헤란로제일종합상가빌딩신관동과구관동과별관동부속동';
    const OTHER_GU = '서울특별시 서초구 강남대로 2 (서초동, 아주아주긴부속건물이름이붙은주소 지하상가 연결통로 쪽 출입구)';
    const hits = [
      searchHit({ bld_nm: LONG, road_addr: '서울특별시 강남구 테헤란로 100', jibun_addr: '서울특별시 강남구 역삼동 823-4', min_floor: -3, max_floor: 12, floor_cnt: 15, total_cnt: 26 }),
      // 다른 구 · 아주 긴 주소 — 줄이 왼쪽 칸 밖으로 밀리지 않고 끝이 줄어야 한다.
      searchHit({ bld_id: 'other-gu', bld_nm: '옆구빌딩', road_addr: OTHER_GU, min_floor: -1, max_floor: 5, total_cnt: 26 }),
      ...Array.from({ length: 23 }, (_, i) =>
        searchHit({ bld_id: `b${i}`, bld_nm: `역삼빌딩${i + 1}`, road_addr: `서울특별시 강남구 테헤란로 ${200 + i}`, jibun_addr: `서울특별시 강남구 역삼동 ${900 + i}`, total_cnt: 26 }),
      ),
    ];
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, hits);
    await mockJson(
      page,
      SEARCH_STORES_PATTERN,
      Array.from({ length: 8 }, (_, i) =>
        storeHit({ pnu: `11680101001000${String(i).padStart(5, '0')}`, bld_id: `s${i}`, bld_nm: i === 0 ? `${LONG}별관` : `가게건물${i}`, road_addr: `서울특별시 강남구 테헤란로 ${300 + i}`, jibun_addr: `서울특별시 강남구 역삼동 ${700 + i}`, total_parcel_cnt: 8, total_store_cnt: 16 }),
      ),
    );
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await expect(page.getByRole('button', { name: new RegExp(LONG) }).first()).toBeVisible();
    const input = page.getByLabel('건물명 또는 주소');

    if (testInfo.project.name === 'mobile') {
      // 휴대폰 = 변화 0 — 안내 글 긴 꼴 · 주소 전체 · 목록 안쪽 굴림 그대로(320px).
      expect(await input.getAttribute('placeholder')).toContain('스타벅스');
      await expect(page.locator('.hit__addr').first()).toHaveText('서울특별시 강남구 테헤란로 100');
      expect(await page.locator('.hits').evaluate((el) => el.ownerDocument.defaultView!.getComputedStyle(el).maxHeight)).toBe('320px');
      await expect(page.locator('.search__eg')).toHaveCount(0);
      return;
    }

    for (const width of [1280, 1024]) {
      await page.setViewportSize({ width, height: 800 });
      await expect(page.locator('.app')).toHaveClass(/app--wide/);
      // L5 — 짧은 안내 글이 입력칸 글 자리 안에 들어간다(글 폭을 그 칸의 글꼴로 잰다).
      expect(await input.getAttribute('placeholder')).toBe('건물명·주소·가게 이름');
      const fit = await input.evaluate((el) => {
        const doc = el.ownerDocument;
        const cs = doc.defaultView!.getComputedStyle(el);
        const ctx = doc.createElement('canvas').getContext('2d')!;
        ctx.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
        const room = el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
        return room - ctx.measureText(el.getAttribute('placeholder') ?? '').width;
      });
      expect(fit, `${width} 안내 글 여유`).toBeGreaterThanOrEqual(0);
      // 보완 1 — 검색칸 바로 아래 예시 한 줄(두 칸만 · 13px · 글을 쳐 둔 채로도 남음).
      const eg = page.locator('.search__eg');
      await expect(eg).toBeVisible();
      await expect(eg).toHaveText('예: 미도맨션\u00a0· 테헤란로 117\u00a0· 역삼동 823-4\u00a0· 스타벅스');
      expect(await eg.evaluate((el) => el.ownerDocument.defaultView!.getComputedStyle(el).fontSize)).toBe('13px');
      const inBox = (await input.boundingBox())!;
      const egBox = (await eg.boundingBox())!;
      expect(egBox.y).toBeGreaterThanOrEqual(inBox.y + inBox.height);
      expect(egBox.y).toBeLessThan(inBox.y + inBox.height + 24);

      // 보완 1 — 보이는 줄마다 첫 글자가 가운뎃점이 아니다(목록 줄 · 예시 줄). 줄을 여는 칸의 머리 장식(::before)과 글 속 점을 둘 다 본다.
      const leadDots = await page.locator('.entry').evaluate((root) => {
        const doc = root.ownerDocument;
        const view = doc.defaultView!;
        const found: string[] = [];
        // ⓘ e2e 타입 설정엔 DOM 이 없다 — 찾은 요소를 root 와 같은 타입으로 본다.
        const rows = Array.from(root.querySelectorAll('.hit, .stores__row, .dbld__row, .search__eg')) as (typeof root)[];
        for (const row of rows) {
          const rr = row.getBoundingClientRect();
          const rcs = view.getComputedStyle(row);
          const left = rr.left + parseFloat(rcs.borderLeftWidth) + parseFloat(rcs.paddingLeft);
          // ① 줄 맨 앞에 선 칸의 머리 장식이 점인가(flex 줄은 늘 줄의 왼쪽 끝에서 시작한다).
          for (const c of Array.from(row.children) as (typeof root)[]) {
            const r0 = c.getClientRects()[0];
            if (r0 && Math.abs(r0.left - left) < 2 && view.getComputedStyle(c, '::before').content.includes('·')) {
              found.push(`머리 장식: ${row.textContent?.slice(0, 20)}`);
            }
          }
          // ② 글 속 점 — 앞 글자(빈칸 빼고)가 윗줄에 있거나 없으면 그 점이 줄 맨 앞이다.
          const walker = doc.createTreeWalker(row, 4);
          let prev: { top: number } | null = null;
          for (let n = walker.nextNode(); n; n = walker.nextNode()) {
            const text = n.textContent ?? '';
            for (let i = 0; i < text.length; i += 1) {
              if (/\s/.test(text[i])) continue;
              const range = doc.createRange();
              range.setStart(n, i);
              range.setEnd(n, i + 1);
              const rect = range.getClientRects()[0];
              if (!rect || rect.width === 0) continue; // 말줄임에 가려진 글자
              if (text[i] === '·' && (prev === null || prev.top < rect.top - 2)) found.push(`글: ${text.slice(Math.max(0, i - 8), i + 8)}`);
              prev = { top: rect.top };
            }
          }
        }
        return found;
      });
      expect(leadDots, `${width} 줄 맨 앞 가운뎃점`).toEqual([]);

      // 👤 2026-10-22 방법 나 — 목록은 왼쪽 칸에 안 선다(오른쪽 표 · L1 두 줄·L3 굴림 하나는 걷었다 → 오른쪽 자리·말줄임 0·굴림 하나는 CD).
      await expect(page.locator('.entry').locator('.hit, .stores__row, .dbld__row')).toHaveCount(0);

      // L2 — 고른 구 주소는 길 이름부터 · 다른 구는 그대로(오른쪽 표에서도 같은 글).
      await expect(page.locator('.hit__addr').nth(0)).toHaveText('테헤란로 100');
      await expect(page.locator('.hit__jibun').nth(0)).toHaveText('지번 역삼동 823-4');
      await expect(page.locator('.hit__addr').nth(1)).toHaveText(OTHER_GU);
      await expect(page.locator('.stores__addr').first()).toHaveText('테헤란로 300');

      // 왼쪽 칸 굴림은 칸 안 하나 · 왼쪽 칸·문서 가로 넘침 0.
      const pane = await page.locator('.entry').evaluate((el) => ({
        oy: el.ownerDocument.defaultView!.getComputedStyle(el).overflowY,
        wide: el.scrollWidth - el.clientWidth,
      }));
      expect(pane).toEqual({ oy: 'auto', wide: 0 });
      expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
      await page.screenshot({ path: testInfo.outputPath(`cc-left-${width}.png`) });
    }

    // 1000 한 열 = 변화 0 — 안내 글 긴 꼴 · 주소 전체 · 목록 안쪽 굴림(320px) 그대로 · 이름은 한 줄 말줄임.
    await page.setViewportSize({ width: 1000, height: 768 });
    await expect(page.locator('.app')).not.toHaveClass(/app--wide/);
    expect(await input.getAttribute('placeholder')).toContain('스타벅스');
    await expect(page.locator('.hit__addr').first()).toHaveText('서울특별시 강남구 테헤란로 100');
    const one = await page.locator('.hits').evaluate((el) => {
      const cs = el.ownerDocument.defaultView!.getComputedStyle(el);
      return { mh: cs.maxHeight, oy: cs.overflowY };
    });
    expect(one).toEqual({ mh: '320px', oy: 'auto' });
    await expect(page.locator('.search__eg')).toHaveCount(0);
    expect(await page.locator('.hit__name').first().evaluate((el) => el.ownerDocument.defaultView!.getComputedStyle(el).whiteSpace)).toBe('nowrap');
  });

  /*
    방법 나(👤 2026-10-22 · R1~R7) — 검색 결과·가게 이름 결과는 PC 두 칸에서 오른쪽 넓은 칸에 표(이름 · 길 주소 · 층 · 점포)로 선다.
    목록에서 고르면 오른쪽 = 건물 + 「← 목록으로(…)」 · 브라우저 뒤로가기도 목록으로(굴린 자리 그대로) · 목록 위 「← 보던 건물(이름)로」.
    ⓘ 상권 건물 목록·지도 칸 높이는 지도 키가 없어 여기서 안 선다 → vitest(App.wide.test 배선 · CSS 가드).
  */
  test('CD. 오른쪽 목록 — 1280·1024 두 칸: 목록이 오른쪽 표 네 칸(한 줄 · 이름 말줄임 0 · 점포 오른쪽 맞춤) · 왼쪽엔 목록 0 · 고르면 건물 + 「← 목록으로」 · 뒤로가기·단추로 오가기(굴린 자리 그대로) · 종이 = 건물 · 휴대폰은 그대로', async ({
    page,
  }, testInfo) => {
    const LONG = '아주아주긴이름의강남역삼테헤란로제일종합상가빌딩신관동과구관동과별관동부속동';
    const hits = [
      searchHit({ bld_nm: LONG, road_addr: '서울특별시 강남구 테헤란로 100', jibun_addr: '서울특별시 강남구 역삼동 823-4', bld_cnt_in_pnu: 3, min_floor: -3, max_floor: 12, floor_cnt: 15, total_cnt: 25 }),
      // 건물 번호는 진짜 꼴(19자리_번호) — 주소 쓰기가 그 꼴만 적는다(`urlState` BLD_RE).
      ...Array.from({ length: 24 }, (_, i) =>
        searchHit({ bld_id: `11680101001000${String(i).padStart(5, '0')}_${1000 + i}`, bld_nm: `역삼빌딩${i + 1}`, road_addr: `서울특별시 강남구 테헤란로 ${200 + i}`, jibun_addr: `서울특별시 강남구 역삼동 ${900 + i}`, total_cnt: 25 }),
      ),
    ];
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, hits);
    await mockJson(
      page,
      SEARCH_STORES_PATTERN,
      Array.from({ length: 3 }, (_, i) =>
        storeHit({ pnu: `11680101001000${String(i).padStart(5, '0')}`, bld_id: `s${i}`, bld_nm: `가게건물${i}`, road_addr: `서울특별시 강남구 테헤란로 ${300 + i}`, match_store_cnt: 10 ** i, total_parcel_cnt: 3, total_store_cnt: 111 }),
      ),
    );
    await mockFloorStack(page);
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await expect(page.getByRole('button', { name: new RegExp(LONG) })).toBeVisible();

    if (!(await isTwoCols(page))) {
      // 휴대폰 = 변화 0 — 결과는 찾기 탭 검색칸 아래 지금 꼴(표 머리·칸 이름표·오른쪽 자리 0).
      await expect(page.locator('.entry .hit')).toHaveCount(25);
      await expect(page.locator('section.rlist, .rtable__head, .rcell')).toHaveCount(0);
      return;
    }

    const rlist = page.locator('section.rlist');
    // ⓘ e2e 타입 설정엔 DOM 이 없다 — 창 굴림 값은 globalThis 로 읽는다(BA 와 같은 꼴).
    const readScrollY = () => page.evaluate(() => (globalThis as unknown as { scrollY: number }).scrollY);
    const row = (name: string) => rlist.locator('.hit').filter({ has: page.locator('.hit__name', { hasText: new RegExp(`^${name}$`) }) });
    for (const width of [1280, 1024]) {
      await page.setViewportSize({ width, height: 800 });
      // R1 — 목록은 오른쪽 칸(왼쪽 칸 오른쪽 끝보다 오른쪽) · 왼쪽 칸엔 목록 0.
      await expect(rlist).toBeVisible();
      await expect(page.locator('.entry').locator('.hit, .stores__row')).toHaveCount(0);
      const entryBox = (await page.locator('.entry').boundingBox())!;
      const listBox = (await rlist.boundingBox())!;
      expect(listBox.x, `${width} 오른쪽 칸`).toBeGreaterThan(entryBox.x + entryBox.width);
      // R4 — 건물 검색 결과 표는 세 칸(👤 2026-10-22 「검색 결과는 세 칸」 — 점포 칸 자체가 없다) · 가게 이름 표는 네 칸 ·
      //   줄마다 칸이 한 줄(칸 위 끝이 같다 · 왼쪽부터 차례) · 이름 칸은 이름 머리와 같은 자리.
      await expect(rlist.locator('.rtable__head').first().locator('.rcell')).toHaveText(['이름', '길 주소', '층']);
      // 가게 이름 표도 세 칸(👤 2026-10-23 D4 「빈 층 칸을 빼고 이름·길 주소·일치 가게 세 칸」).
      await expect(rlist.locator('.search__stores .rtable__head .rcell')).toHaveText(['이름', '길 주소', '일치 가게']);
      await expect(rlist.locator('.stores__row').first().locator(':scope > .rcell')).toHaveCount(3);
      // 「목록 닫기 ✕」(👤 10-23 D2) — 목록 머리 줄 오른쪽 끝 · 44px 이상.
      const closeBox = (await rlist.getByRole('button', { name: '목록 닫기' }).boundingBox())!;
      expect(closeBox.height).toBeGreaterThanOrEqual(44);
      expect(Math.abs(closeBox.x + closeBox.width - (listBox.x + listBox.width))).toBeLessThan(2);
      await expect(rlist.locator('.hits .rcell--store')).toHaveCount(0);
      const cells = await row(LONG).locator('.rcell').evaluateAll((els) => els.map((e) => e.getBoundingClientRect()).map((r) => ({ x: r.x, y: r.y, w: r.width })));
      expect(cells).toHaveLength(3);
      // 셋째(층) 칸이 줄 오른쪽 끝까지 — 빈 넷째 자리가 남지 않는다(줄 안쪽 오른쪽 여백 = 줄 왼쪽 여백 · 2px 안).
      const rowBox = (await row(LONG).boundingBox())!;
      expect(Math.abs(rowBox.x + rowBox.width - (cells[2].x + cells[2].w) - (cells[0].x - rowBox.x)), `${width} 세 칸 꽉 참`).toBeLessThan(2);
      for (let i = 1; i < 3; i += 1) {
        expect(Math.abs(cells[i].y - cells[0].y), `${width} 칸 ${i} 같은 줄`).toBeLessThan(4);
        expect(cells[i].x, `${width} 칸 ${i} 차례`).toBeGreaterThan(cells[i - 1].x + cells[i - 1].w - 1);
      }
      const headName = (await rlist.locator('.rtable__head').first().locator('.rcell--name').boundingBox())!;
      expect(Math.abs(headName.x - cells[0].x)).toBeLessThan(2);
      // 이름 말줄임 0(긴 이름은 칸 안에서 줄을 넘긴다) · 층 글 잘림 0 · 주소 칸 아래 지번·「같은 땅에 3동」.
      for (const sel of ['.hit__name', '.stores__name', '.hit__meta', '.hit__addr']) {
        const cut = await rlist.locator(sel).evaluateAll((els) => els.filter((e) => e.scrollWidth > e.clientWidth + 0.5).length);
        expect(cut, `${width} ${sel} 잘림`).toBe(0);
      }
      await expect(row(LONG).locator('.rcell--addr > *')).toHaveText(['테헤란로 100', '지번 역삼동 823-4', '같은 땅에 3동']);
      await expect(row(LONG).locator('.rcell--floor')).toHaveText('지하 3층 ~ 12층 · 15개 층');
      // 점포 칸 = 오른쪽 맞춤(가게 이름 결과 · 1 · 10 · 100곳) — 글 오른쪽 끝이 칸 오른쪽 끝에 붙는다.
      const storeCells = rlist.locator('.stores__row .rcell--store');
      await expect(storeCells).toHaveText(['이 땅에 가게 1곳 일치', '이 땅에 가게 10곳 일치', '이 땅에 가게 100곳 일치']);
      const rightGap = await storeCells.evaluateAll((els) =>
        els.map((e) => {
          const range = e.ownerDocument.createRange();
          range.selectNodeContents(e);
          const rects = Array.from(range.getClientRects()) as { right: number }[];
          return e.getBoundingClientRect().right - Math.max(...rects.map((r) => r.right));
        }),
      );
      for (const g of rightGap) expect(g, `${width} 점포 오른쪽 맞춤`).toBeLessThan(2);
      // 13px 이상 · 가로 넘침 0(오른쪽 칸 · 문서).
      for (const sel of ['.hit__jibun', '.hit__warn', '.rtable__head']) await expect(rlist.locator(sel).first()).toHaveCSS('font-size', '13px');
      expect(await rlist.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
      expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
      await page.screenshot({ path: testInfo.outputPath(`cd-list-${width}.png`), fullPage: true });
    }

    // R3 — 목록을 내려 고른다 → 오른쪽 = 건물(맨 위) + 「← 목록으로(테헤란로 검색)」(수 없음 · 할루 🟡a) · 목록은 숨음.
    await page.setViewportSize({ width: 1280, height: 720 });
    const pick = row('역삼빌딩20');
    await pick.scrollIntoViewIfNeeded();
    const listY = await readScrollY();
    expect(listY).toBeGreaterThan(200);
    await pick.click();
    await expect(page.locator('section.stack')).toBeVisible();
    await expect(rlist).toBeHidden();
    const backBtn = page.getByRole('button', { name: '목록으로(테헤란로 검색)' });
    await expect(backBtn).toBeVisible();
    await expect(backBtn).toHaveText('← 목록으로(테헤란로 검색)');
    await expect(page).toHaveURL(/bld=1168010100100000019_1019/);
    expect(await readScrollY()).toBeLessThan(5);
    const bldTop = (await backBtn.boundingBox())!;
    expect(bldTop.y).toBeLessThan(200); // 건물 맨 위(단추 → 담아 가기 → 층별 머리)
    await page.screenshot({ path: testInfo.outputPath('cd-building-1280.png') });

    // 브라우저 뒤로가기 = 목록(보던 자리 그대로 · 주소 꼴 그대로) · 커서 = 「← 보던 건물로」.
    await page.goBack();
    await expect(rlist).toBeVisible();
    await expect(page.locator('section.stack')).toBeHidden();
    await expect.poll(() => readScrollY()).toBeGreaterThan(listY - 3);
    expect(Math.abs((await readScrollY()) - listY)).toBeLessThan(3);
    const toBld = page.getByRole('button', { name: '보던 건물(역삼빌딩20)로' });
    await expect(toBld).toBeFocused();
    // 주소 꼴 그대로 — 건물은 쥐고 있으니 목록 보기에서도 같은 건물 주소(목록 상태는 안 싣는다 · 결정 0019).
    await expect(page).toHaveURL(/\?sgg=11680&bld=1168010100100000019_1019$/);
    // 「← 보던 건물로」 → 건물 · 다시 「← 목록으로」 단추 → 목록(같은 자리). ⓘ 커서가 이미 단추에 있어 자판으로 누른다 — 마우스 click 은
    //   화면 밖(목록 맨 위) 단추를 먼저 화면 안으로 굴려 '보던 자리'를 바꿔 버린다(시험이 만드는 굴림).
    await page.keyboard.press('Enter');
    await expect(page.locator('section.stack')).toBeVisible();
    await expect(backBtn).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(rlist).toBeVisible();
    await expect(toBld).toBeFocused();
    await expect.poll(() => readScrollY()).toBeGreaterThan(listY - 3);
    expect(Math.abs((await readScrollY()) - listY)).toBeLessThan(3);

    // 종이 — 목록이 오른쪽에 선 채 뽑아도 종이 = 건물(목록·「← 보던 건물로」 빠짐 · 건물 머리 보임).
    await page.emulateMedia({ media: 'print' });
    await expect(rlist).toBeHidden();
    await expect(page.locator('section.stack .stack__head')).toBeVisible();
    await expect(page.locator('.rback')).toHaveCount(0); // 목록 보기 중엔 「← 목록으로」 자체가 없다
    await page.emulateMedia({ media: null });
    // 건물 보기에서 뽑아도 「← 목록으로」는 종이에 없다.
    await toBld.click();
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('.rback')).toBeHidden();
    await expect(page.locator('section.stack .stack__head')).toBeVisible();
    await page.emulateMedia({ media: null });

    // 1000 한 열 = 변화 0 — 결과는 입구 검색칸 아래 지금 꼴(오른쪽 자리·표 0).
    await page.setViewportSize({ width: 1000, height: 768 });
    await expect(page.locator('section.rlist, .rtable__head, .rback')).toHaveCount(0);
  });

  /*
    후속 PR(적대 재검사 🟡) — 진짜 브라우저 뒤로가기로 재현 순서 그대로: 검색 → 건물 → 새 검색 → 「목록 닫기」(이웃 칸 = 건물로) → 뒤로.
    뒤 칸은 첫 검색의 목록 칸인데 그 목록은 이미 닫혔다 → 그 칸에서 멈추면 화면이 안 바뀐다(헛눌림) → 한 칸 더 가서 이전 페이지(빈 탭)로 나간다.
    ⓘ vitest 는 jsdom 창 하나를 시험들이 나눠 써서 진짜 칸 이동을 못 본다 — 여기서 본다.
  */
  test('CF. 뒤로가기 빈 칸 지나치기 — 검색 → 건물 → 새 검색 → 「목록 닫기」 → 뒤로 한 번 = 닫힌 옛 목록 칸에서 멈추지 않고 이전 페이지로 · 휴대폰은 그대로', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit(), searchHit({ bld_id: '1168010100100020000_2', bld_nm: '다른빌딩' })]);
    await mockFloorStack(page);
    await page.goto('/');
    if (!(await isTwoCols(page))) return; // 휴대폰 = 이 갈래 없음(탭 꼴의 칸 규칙 그대로)
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack')).toBeVisible();
    await search(page, '다른동');
    await expect(page.getByRole('button', { name: /다른빌딩/ })).toBeVisible();
    await page.getByRole('button', { name: '목록 닫기' }).click();
    await expect(page.locator('section.stack')).toBeVisible();
    await expect(page.locator('section.rlist')).toBeHidden();
    // 뒤로 한 번 — 앱 안의 빈 칸(닫힌 목록)을 지나 이전 페이지(빈 탭)로.
    await page.goBack();
    await expect.poll(() => page.url()).toBe('about:blank');
  });

  /*
    👤 2026-10-23 D3 「지도와 「누른 자리」가 굴리지 않고 첫 화면에 들어오게」 — E2E 엔 지도 키가 없어 지도 칸·범례·누른 자리가 안 선다.
    그래서 지도 덩어리 안에 그 셋을 **진짜와 같은 이름표**로 세워(`DistrictMap` 의 카드 꼴 · `PickedList` 의 「누른 자리 (1곳):」 + 상권 단추 하나 ·
    범례 다섯 유형) 실제 CSS 가 정한 높이·자리를 잰다 — 「누른 자리」 줄의 아래 끝이 첫 화면(굴리기 전) 안 · 지도 칸 300px 이상.
  */
  test('CE. 지도 첫 화면 — 1280×900 · 1024×768 · 1440×900 · 1920×1080 두 칸에서 지도 칸(300px 이상)과 「누른 자리」 줄 아래 끝이 굴리지 않고 첫 화면 안 · 휴대폰·1000 은 그대로', async ({
    page,
  }, testInfo) => {
    await mockOpenSigungu(page);
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    if (!(await isTwoCols(page))) {
      // 휴대폰 = 변화 0(지도 탭 가득 · 이 규칙은 두 칸 묶음 안).
      await expect(page.locator('.app')).not.toHaveClass(/app--wide/);
      return;
    }
    const PROBE = [
      '<div class="dmap__canvas" data-probe="1"></div>',
      '<ul class="dmap__legend" data-probe="1">',
      ...['골목상권', '발달상권', '전통시장', '관광특구', '주요상권'].map((t) => `<li><span class="dmap__swatch"></span>${t}</li>`),
      '</ul>',
      '<div class="dmap__picked" data-probe="1"><span class="dmap__picked-key">누른 자리 (1곳):</span>',
      '<ul class="dmap__picked-list"><li><button type="button" class="dmap__picked-btn"><span class="dmap__swatch"></span>',
      '<span class="dmap__picked-nm">대전향촌우편취급국</span><span class="dmap__picked-ty">골목상권</span></button></li></ul></div>',
    ].join('');
    // 위를 줄인 두 가지(👤 10-23 D3) — 「왼쪽 칸 접기」는 사이트 제목 줄(제목 바로 옆 · 같은 줄) · 역할 안내 글은 보이는 줄 0(단추 설명으로 · 글자 그대로).
    const fold = page.locator('.app__head .entry__fold');
    await expect(fold).toBeVisible();
    await expect(page.locator('.entry .entry__fold')).toHaveCount(0);
    const titleBox = (await page.locator('.app__head .app__title').boundingBox())!;
    const foldBox = (await fold.boundingBox())!;
    expect(Math.abs(foldBox.y + foldBox.height / 2 - (titleBox.y + titleBox.height / 2))).toBeLessThan(12);
    expect(foldBox.x).toBeGreaterThan(titleBox.x + titleBox.width);
    expect(foldBox.height).toBeGreaterThanOrEqual(44);
    await expect(page.locator('.entry .role__note')).toBeHidden();
    await expect(page.locator('.entry .role__chip').first()).toHaveAttribute('title', '고르면 화면 순서가 맞춰집니다 · 이 기기에만 저장 · 다시 누르면 해제');
    // 마우스 없는 태블릿(hover: none — 가로로 눕힌 아이패드 등)은 올릴 수 없으니 안내 글이 보이는 줄 그대로(👤 2026-10-26).
    // ⓘ 크롬 미디어 흉내(Emulation.setEmulatedMedia)는 hover 를 안 바꾼다(10-26 실측) → 터치 창(hasTouch · isMobile)을 따로 연다(hover: none 실측).
    {
      const tablet = await page.context().browser()!.newContext({ viewport: { width: 1180, height: 820 }, hasTouch: true, isMobile: true });
      await tablet.addInitScript(() => {
        try {
          if (!localStorage.getItem('sangga.viewerRole')) localStorage.setItem('sangga.viewerRole', '둘러보기');
        } catch {
          /* 저장 막힘 — 큰 카드가 서면 아래 단언이 잡는다 */
        }
      });
      const tp = await tablet.newPage();
      await mockOpenSigungu(tp);
      await tp.goto(new URL('/', page.url()).href); // 새 창은 프로젝트 baseURL 을 안 물려받는다
      expect(
        await tp.evaluate(() => (globalThis as unknown as { matchMedia: (q: string) => { matches: boolean } }).matchMedia('(hover: none)').matches),
      ).toBe(true);
      await expect(tp.locator('.app')).toHaveClass(/app--wide/);
      await expect(tp.locator('.entry .role__note')).toBeVisible();
      await expect(tp.locator('.entry .role__note')).toHaveText('고르면 화면 순서가 맞춰집니다 · 이 기기에만 저장 · 다시 누르면 해제');
      await expect(tp.locator('.entry .role__chip').first()).toHaveAttribute('title', '고르면 화면 순서가 맞춰집니다 · 이 기기에만 저장 · 다시 누르면 해제');
      await tablet.close();
    }
    await expect(page.locator('.entry .role__note')).toBeHidden();

    type Probe = { canvasTop: number; canvasH: number; pickedBottom: number };
    const measure = (w: number, h: number) =>
      page.locator('.entry section.dmap').evaluate((sec, html): Probe => {
        // ⓘ e2e 타입 설정엔 DOM 이 없다 — 쓰는 것만 좁게 적는다.
        type El = { remove(): void; hidden: boolean; getBoundingClientRect(): { top: number; height: number; bottom: number } };
        const root = sec as unknown as {
          ownerDocument: { defaultView: { scrollTo(x: number, y: number): void } };
          querySelectorAll(s: string): { forEach(f: (e: El) => void): void };
          querySelector(s: string): El;
          insertAdjacentHTML(at: string, html: string): void;
        };
        root.ownerDocument.defaultView.scrollTo(0, 0);
        root.querySelectorAll('[data-probe]').forEach((e) => e.remove());
        root.querySelectorAll(':scope > .msg').forEach((e) => {
          e.hidden = true;
        });
        root.insertAdjacentHTML('beforeend', html);
        const box = (s: string) => root.querySelector(s).getBoundingClientRect();
        return { canvasTop: box('.dmap__canvas').top, canvasH: box('.dmap__canvas').height, pickedBottom: box('.dmap__picked').bottom };
      }, PROBE).then((m) => ({ ...m, w, h }));

    const rows: string[] = [];
    for (const [w, h] of [[1280, 900], [1024, 768], [1440, 900], [1920, 1080]] as const) {
      await page.setViewportSize({ width: w, height: h });
      await expect(page.locator('.app')).toHaveClass(/app--wide/);
      const m = await measure(w, h);
      rows.push(`${w}×${h} 지도 y ${Math.round(m.canvasTop)} 높이 ${Math.round(m.canvasH)} · 누른 자리 아래 끝 ${Math.round(m.pickedBottom)}`);
      expect.soft(m.canvasH, `${w}×${h} 지도 칸 300px 이상`).toBeGreaterThanOrEqual(299.5);
      expect.soft(m.canvasH, `${w}×${h} 지도 칸 상한 640px`).toBeLessThanOrEqual(640.5);
      // ⓘ 1024×768 은 위를 줄여도 들지 않는다(지도 300 · 아래 끝 약 887 — 👤 10-23 「억지로 더 빼지 말 것 · 숫자와 함께 보고」) → 숫자만 남긴다.
      if (w !== 1024) expect.soft(m.pickedBottom, `${w}×${h} 누른 자리 아래 끝 ≤ 창 높이`).toBeLessThanOrEqual(h);
      await page.screenshot({ path: testInfo.outputPath(`ce-map-${w}x${h}.png`) });
    }
    // 큰 창은 지도가 더 크다(남는 높이를 받는다 — 1920×1080 은 300 보다 크다).
    const big = await measure(1920, 1080);
    expect(big.canvasH).toBeGreaterThan(400);
    testInfo.annotations.push({ type: '지도 첫 화면', description: rows.join(' / ') });
  });
});

// 실거래 기록 카드의 그림(결정 0038 B · V2 · 👤 2026-10-21 「계획대로 둘 다」) — 그림이 깨져도 글자 시험은 초록이다(§2-10).
// 폭·자리·색은 CSS 라 jsdom(vitest)은 못 본다 — 넓은 화면(1280 두 칸)·휴대폰(412)·종이에서 여기서만 잰다.
test.describe('실거래 그림', () => {
  // 12건 — 층 묶음 다섯 꼴 + 지분 둘(숨는 11·12번째 줄 · 같은 달·같은 값 1층 둘 = 점 하나 「100만 ×2」 — 보완 1) ·
  // 계약 달 2024-01 ~ 2026-05 · ㎡당 최대 920만(축 1,000만).
  const TXS = [
    parcelTx({ floor_no: 1, contract_ym: '202605', unit_price: 9_200_000 }),
    parcelTx({ floor_no: 1, contract_ym: '202511', unit_price: 6_100_000 }),
    parcelTx({ floor_no: 2, contract_ym: '202508', unit_price: 4_200_000 }),
    parcelTx({ floor_no: 2, contract_ym: '202503', unit_price: 3_900_000 }),
    parcelTx({ floor_no: 5, contract_ym: '202501', unit_price: 3_100_000 }),
    parcelTx({ floor_no: 99, contract_ym: '202410', unit_price: 2_400_000 }),
    parcelTx({ floor_no: -1, contract_ym: '202407', unit_price: 2_000_000 }),
    parcelTx({ floor_no: null, contract_ym: '202404', unit_price: 3_500_000 }),
    parcelTx({ floor_no: 3, contract_ym: '202403', unit_price: 2_800_000 }),
    parcelTx({ floor_no: 1, contract_ym: '202402', unit_price: 5_000_000 }),
    parcelTx({ floor_no: 1, contract_ym: '202401', unit_price: 1_000_000, is_share: true }),
    parcelTx({ floor_no: 1, contract_ym: '202401', unit_price: 1_000_000, is_share: true }),
  ];

  test('BX. 구 층대 띠(사실 색 · p25~p75 폭 비례 · 줄마다 같은 자 · 표본 부족 "–") + 이 땅 거래 점그림(층 묶음 꼴 · 지분 빈 꼴 · 자리 비례 · 설명 줄 늘) · 넓은 화면 글 오른쪽 · 휴대폰 글 아래 줄·넘침 0 · 13px · 종이에 그대로', async ({
    page,
  }, testInfo) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, TXS);
    // 1층·2층 = 값을 냄(픽스처 값 1,380만~3,730만 · 가운데 2,250만) · 지하 = 4건(표본 부족). 나중에 등록한 것이 먼저 잡힌다.
    await mockJson(page, TX_STATS_PATTERN, sigunguTxStats({ 지하: 4, '1층': 213, '2층': 9 }));

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const card = page.locator('section.tx');
    await expect(card.locator('.tx__bands--viz')).toBeVisible();
    const phone = (page.viewportSize()?.width ?? 0) <= 720;
    const row = (name: string) =>
      card.locator('.tx__bands li').filter({ has: page.locator('.tx__band', { hasText: new RegExp(`^${name}$`) }) });
    const box = async (sel: ReturnType<Page['locator']>) => (await sel.boundingBox())!;

    // ① 띠 — 축 5,000만(p75 3,730만 올림) → 띠 27.6% ~ 74.6% · 눈금 45%. 띠 칸 안쪽(테두리 1px 뺀 폭) 기준.
    const track = await box(row('1층').locator('.tx__track'));
    const range = await box(row('1층').locator('.tx__range'));
    const tick = await box(row('1층').locator('.tx__tick'));
    const inner = track.width - 2;
    expect(inner).toBeGreaterThan(60);
    expect(Math.abs((range.x - (track.x + 1)) / inner - 0.276)).toBeLessThan(0.012);
    expect(Math.abs(range.width / inner - 0.47)).toBeLessThan(0.012);
    expect(Math.abs((tick.x + tick.width / 2 - (track.x + 1)) / inner - 0.45)).toBeLessThan(0.012);
    // 사실 색(호박) — 띠 = --fact-2 · 눈금 = --fact-4 · 바탕 = --warn-bg.
    await expect(row('1층').locator('.tx__range')).toHaveCSS('background-color', 'rgb(224, 180, 90)');
    await expect(row('1층').locator('.tx__tick')).toHaveCSS('background-color', 'rgb(125, 84, 20)');
    await expect(row('1층').locator('.tx__track')).toHaveCSS('background-color', 'rgb(253, 243, 227)');
    // 줄마다 같은 자 — 같은 값의 2층 띠가 1층 띠와 같은 자리·같은 폭 · 축 글 줄도 띠 칸과 같은 자리.
    const track2 = await box(row('2층').locator('.tx__track'));
    const range2 = await box(row('2층').locator('.tx__range'));
    expect(Math.abs(track2.x - track.x)).toBeLessThan(1);
    expect(Math.abs(track2.width - track.width)).toBeLessThan(1);
    expect(Math.abs(range2.x - range.x)).toBeLessThan(1);
    const axis = await box(card.locator('.tx__axis-scale'));
    expect(Math.abs(axis.x - track.x)).toBeLessThan(1.5);
    expect(Math.abs(axis.x + axis.width - (track.x + track.width))).toBeLessThan(1.5);
    await expect(card.locator('.tx__axis')).toHaveText('0㎡당 5,000만');
    // 표본 부족 — 띠 없이 "–" · 까닭 글 그대로 · 0 으로 안 그린다.
    await expect(row('지하').locator('.tx__viz--none')).toHaveText('–');
    await expect(row('지하').locator('.tx__range')).toHaveCount(0);
    await expect(row('지하').locator('.tx__val')).toHaveText('표본 부족');
    // 글은 한 글자도 안 바뀐다 — 넓은 화면은 띠 오른쪽, 휴대폰은 띠 아래 줄.
    await expect(row('1층').locator('.tx__val')).toHaveText('중앙값 ㎡당 2,250만 (가운데 절반 1,380만~3,730만)');
    const val = await box(row('1층').locator('.tx__val'));
    if (phone) expect(val.y).toBeGreaterThanOrEqual(track.y + track.height - 1);
    else expect(val.x).toBeGreaterThanOrEqual(track.x + track.width - 1);

    // ② 점그림 — 12건 · 같은 달·같은 값 지분 둘은 점 하나(보완 1 F2) → 점 11 · 빈 꼴 1 · 꼴 다섯.
    const plot = card.locator('.tx__plot');
    await expect(plot).toBeVisible();
    const dots = plot.locator('.tx__plot-in .tx__dot');
    await expect(dots).toHaveCount(11);
    await expect(plot.locator('.tx__plot-in .tx__shape[data-hollow="1"]')).toHaveCount(1);
    const shapes = await plot.locator('.tx__plot-in .tx__shape').evaluateAll((els) => els.map((e) => e.getAttribute('data-shape')));
    expect(shapes).toEqual(['1', '1', '2', '2', '3+', '3+', 'b', 'na', '3+', '1', '1']);
    // 칠 — 찬 꼴 = 호박(--fact-3) · 층 미상 = 회색(--viz-na) · 빈 꼴 = 바탕(--card 흰색).
    // ⓘ 이 파일은 DOM 타입을 안 싣는다 — getComputedStyle 대신 toHaveCSS.
    const shapeEl = (i: number) => plot.locator('.tx__plot-in .tx__shape').nth(i).locator(':scope > *');
    await expect(shapeEl(0)).toHaveCSS('fill', 'rgb(185, 132, 42)');
    await expect(shapeEl(7)).toHaveCSS('fill', 'rgb(180, 183, 191)');
    await expect(shapeEl(10)).toHaveCSS('fill', 'rgb(255, 255, 255)');
    // 자리 — 세로 = ㎡당 값 ÷ 1,000만(아래가 0) · 가로 = 2024-01(왼쪽 끝) ~ 2026-05(오른쪽 끝) · 점은 그림 칸 밖으로 안 나간다.
    const area = await box(plot.locator('.tx__plot-in'));
    const frame = await box(plot.locator('.tx__plot-area'));
    const center = async (i: number) => {
      const b = await box(dots.nth(i));
      return { x: b.x + b.width / 2, y: b.y + b.height / 2, b };
    };
    for (const [i, won] of [[0, 9_200_000], [6, 2_000_000], [10, 1_000_000]] as const) {
      const c = await center(i);
      expect(Math.abs((area.y + area.height - c.y) / area.height - won / 10_000_000)).toBeLessThan(0.02);
    }
    expect(Math.abs((await center(0)).x - (area.x + area.width))).toBeLessThan(1.5);
    expect(Math.abs((await center(10)).x - area.x)).toBeLessThan(1.5);
    for (let i = 0; i < 11; i += 1) {
      const { b } = await center(i);
      expect(b.x).toBeGreaterThanOrEqual(frame.x);
      expect(b.x + b.width).toBeLessThanOrEqual(frame.x + frame.width);
      expect(b.y).toBeGreaterThanOrEqual(frame.y);
      expect(b.y + b.height).toBeLessThanOrEqual(frame.y + frame.height);
    }
    // 세로 눈금 넷 + 가로 눈금선(보완 1 F4) — 눈금 글은 그 선과 같은 높이.
    await expect(plot.locator('.tx__plot-yin .tx__tick-y')).toHaveText(['0', '250만', '500만', '750만', '1,000만']);
    await expect(plot.locator('.tx__plot-unit')).toHaveText('㎡당');
    const grids = plot.locator('.tx__plot-in .tx__grid');
    await expect(grids).toHaveCount(5);
    for (let k = 0; k < 5; k += 1) {
      const g = await box(grids.nth(k));
      const t = await box(plot.locator('.tx__plot-yin .tx__tick-y').nth(k));
      expect(Math.abs(g.y - (t.y + t.height / 2))).toBeLessThan(2);
    }
    await expect(plot.locator('.tx__plot-x')).toHaveText('2024년 1월2026년 5월');
    await expect(plot.locator('.tx__key')).toHaveText(['1층', '2층', '3층 이상', '지하', '층 미상', '속이 빈 꼴 = 지분']);
    // 점 금액 글자(보완 1 F1·F3·F5) — 넓은 화면은 넓은 벌 · 휴대폰은 휴대폰 벌 하나만 보인다 · 실제 상자로 글자끼리 겹침 0 · 그림 칸 안.
    const labs = plot.locator(phone ? '.tx__labs--narrow .tx__lab' : '.tx__labs--wide .tx__lab');
    await expect(plot.locator(phone ? '.tx__labs--wide' : '.tx__labs--narrow')).toBeHidden();
    await expect(labs.first()).toBeVisible();
    const labTexts = await labs.allTextContents();
    expect(labTexts.reduce((s, t) => s + Number(/×(\d+)$/.exec(t)?.[1] ?? 1), 0)).toBe(12);
    if (!phone) expect(labTexts).toEqual(expect.arrayContaining(['920만', '100만 ×2', '350만']));
    /** 보이는 글자의 실제 상자 — 글자끼리 겹침(0.5px 넘게) · 그림 칸 밖을 모은다. */
    const labelProblems = async (sel: string) => {
      const ls = plot.locator(sel);
      const fr = await box(plot.locator('.tx__plot-area'));
      const n = await ls.count();
      const bs: Array<{ t: string; b: { x: number; y: number; width: number; height: number } }> = [];
      for (let i = 0; i < n; i += 1) bs.push({ t: (await ls.nth(i).textContent()) ?? '', b: await box(ls.nth(i)) });
      const bad: string[] = [];
      // 보완 2 — 글자가 어느 점도 덮지 않는다(묶음 안 제 점 포함 · 점 상자 = .tx__dot 10px).
      const ds = plot.locator('.tx__plot-in .tx__dot');
      const dn = await ds.count();
      const dbs: Array<{ x: number; y: number; width: number; height: number }> = [];
      for (let i = 0; i < dn; i += 1) dbs.push(await box(ds.nth(i)));
      bs.forEach(({ t, b: a }) => {
        dbs.forEach((d, k) => {
          if (a.x < d.x + d.width - 0.5 && d.x < a.x + a.width - 0.5 && a.y < d.y + d.height - 0.5 && d.y < a.y + a.height - 0.5) {
            bad.push(`${t} ↔ 점 ${k}`);
          }
        });
      });
      bs.forEach(({ t, b: a }, i) => {
        if (a.x < fr.x - 0.5 || a.x + a.width > fr.x + fr.width + 0.5 || a.y < fr.y - 0.5 || a.y + a.height > fr.y + fr.height + 0.5) {
          bad.push(`칸 밖 ${t}`);
        }
        for (let j = i + 1; j < bs.length; j += 1) {
          const b = bs[j].b;
          if (a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5) {
            bad.push(`${t} ↔ ${bs[j].t}`);
          }
        }
      });
      return bad;
    };
    expect(await labelProblems(phone ? '.tx__labs--narrow .tx__lab' : '.tx__labs--wide .tx__lab')).toEqual([]);
    await expect(labs.first()).toHaveCSS('font-size', '13px');
    // 글자 자리는 '그 꼴에서 가장 좁은 폭'(txViz.ts TX_PLOT_REF — 넓은 벌 460 · 휴대폰 벌 160 · 높이 200/320)으로 계산한다 —
    // 실제 점 칸이 그보다 좁으면 겹칠 수 있으니 여기서 잰다(넓은 벌이 서는 가장 좁은 두 곳 = 721 한 열 · 1024 두 칸 ·
    // 10-21 실측 점 칸 폭: 1280 659 · 1024 488 · 721 529 · 412 220 · 360 168 · 320 128 — 320 폭 전화는 덮지 않는다).
    expect(area.width).toBeGreaterThanOrEqual(phone ? 160 : 460);
    // 높이 — 넓은 화면 220px 칸(안쪽 202 ≥ 기준 200) · 휴대폰 340px 칸(안쪽 322 ≥ 기준 320 · 보완 1 F5 · 보완 2 에서 300 → 340).
    expect(area.height).toBeGreaterThanOrEqual(phone ? 320 : 200);
    if (!phone) {
      for (const width of [721, 1024]) {
        await page.setViewportSize({ width, height: 800 });
        const a = await box(plot.locator('.tx__plot-in'));
        expect(a.width, `${width}px 점 칸 폭`).toBeGreaterThanOrEqual(460);
        expect(await labelProblems('.tx__labs--wide .tx__lab'), `${width}px`).toEqual([]);
      }
      await page.setViewportSize({ width: 1280, height: 720 });
    } else {
      // 360px 전화(휴대폰 벌의 기준 폭 200 이 이 폭을 덮는다).
      await page.setViewportSize({ width: 360, height: 780 });
      const a = await box(plot.locator('.tx__plot-in'));
      expect(a.width, '360px 점 칸 폭').toBeGreaterThanOrEqual(160);
      expect(await labelProblems('.tx__labs--narrow .tx__lab'), '360px').toEqual([]);
      expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
      await page.setViewportSize({ width: 412, height: 839 });
    }
    // 그림은 목록과 같은 내용이라 낭독기에서 뺀다 · 목록은 그대로(처음 10건 + 전부 보기).
    await expect(plot).toHaveAttribute('aria-hidden', 'true');
    await expect(card.locator('.tx__list > li:visible')).toHaveCount(10);
    await expect(card.locator('.list__fold')).toHaveText('거래 전부 보기 (12건)');
    // 지분은 숨는 11·12번째 줄에만 — 그림이 서서 설명 줄은 접힌 화면에도 선다.
    await expect(card.locator('.tx__share-note')).toBeVisible();
    // 글자 13px 이상(S4) — 눈금·범례·"–".
    for (const sel of ['.tx__plot-unit', '.tx__plot-y', '.tx__plot-x', '.tx__keys', '.tx__axis', '.tx__viz--none']) {
      await expect(card.locator(sel).first()).toHaveCSS('font-size', '13px');
    }
    // 가로 넘침 0(문서·카드).
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    expect(await card.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    await card.screenshot({ path: testInfo.outputPath(`bx-tx-${testInfo.project.name}.png`) });

    // ③ 종이 — 그림이 그대로 서고(폭 0 백지 아님), 휴대폰 배치(screen 묶음)는 종이에 안 샌다(글은 띠 오른쪽).
    await page.emulateMedia({ media: 'print' });
    await expect(plot).toBeVisible();
    await expect(row('1층').locator('.tx__range')).toBeVisible();
    const pTrack = await box(row('1층').locator('.tx__track'));
    expect(pTrack.width).toBeGreaterThan(40);
    const pVal = await box(row('1층').locator('.tx__val'));
    expect(pVal.x).toBeGreaterThanOrEqual(pTrack.x + pTrack.width - 1);
    await expect(plot).toHaveCSS('break-inside', 'avoid');
    // 금액 글자·눈금선도 종이에 그대로(보완 1 F6) — 종이는 넓은 벌(휴대폰 벌은 screen 묶음이라 종이에 안 샌다).
    await expect(plot.locator('.tx__labs--wide .tx__lab').first()).toBeVisible();
    await expect(plot.locator('.tx__labs--narrow')).toBeHidden();
    await expect(plot.locator('.tx__plot-in .tx__grid').nth(2)).toBeVisible();
    await expect(card.locator('.tx__list > li:visible')).toHaveCount(12);
    await expect(card.locator('.tx__share-note')).toBeVisible();
    await card.screenshot({ path: testInfo.outputPath(`bx-tx-print-${testInfo.project.name}.png`) });
    await page.emulateMedia({ media: null });
  });
});

test.describe('층별 스택뷰 — 층 목록 업종 띠 (결정 0038 D · V4)', () => {
  /** 층 목록 넷 — 3층·지하 1층은 점포 0(띠 없음 · 모양을 견줄 짝) · 2층 4곳(가장 많은 층) · 1층 2곳. */
  function bandFloors() {
    return [
      floorRow({ floor_no: 3, store_cnt: 0 }),
      floorRow({ floor_no: 2, store_cnt: 4 }),
      floorRow({ floor_no: 1, store_cnt: 2 }),
      floorRow({ floor_no: -1, store_cnt: 0 }),
    ];
  }

  /** `list_floor_industry` 응답 — 층 목록에 없는 7층 2곳 · 층 모름 5곳. 층마다 합 = 위 store_cnt. */
  const BAND_ROWS = [
    { floor_no: 7, cat_l_cd: 'P1', cat_l_nm: '교육', store_cnt: 2 },
    { floor_no: 2, cat_l_cd: 'I2', cat_l_nm: '음식', store_cnt: 1 },
    { floor_no: 2, cat_l_cd: 'M1', cat_l_nm: '과학·기술', store_cnt: 3 },
    { floor_no: 1, cat_l_cd: 'G2', cat_l_nm: '소매', store_cnt: 1 },
    { floor_no: 1, cat_l_cd: 'I2', cat_l_nm: '음식', store_cnt: 1 },
    { floor_no: null, cat_l_cd: 'I2', cat_l_nm: '음식', store_cnt: 4 },
    { floor_no: null, cat_l_cd: 'L1', cat_l_nm: '부동산', store_cnt: 1 },
  ];

  /** 건물을 연다. `rows` 를 안 주면 함수가 없는 상태(mockFloorStack 기본값) 그대로. */
  async function openBand(page: Page, rows?: unknown[], delayMs = 0) {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], bandFloors());
    if (rows !== undefined) await mockJson(page, FLOOR_INDUSTRY_PATTERN, rows, delayMs);
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack')).toBeVisible();
  }

  const headOf = (page: Page, no: number) => page.locator(`.card--floors #floor-${no} .floor__head`);
  const box = async (sel: ReturnType<Page['locator']>) => (await sel.boundingBox())!;

  /** 띠(`.floor__ind-strip` — 조각이 서는 칸)와 막대(`.floor__bar`)의 왼·오른 끝이 같은가 — 1.5px 안. */
  async function expectBandUnderBar(page: Page, no: number, what: string) {
    const bar = await box(headOf(page, no).locator('.floor__bar'));
    const ind = await box(headOf(page, no).locator('.floor__ind-strip'));
    expect(Math.abs(ind.x - bar.x), `${what} 왼쪽 끝`).toBeLessThan(1.5);
    expect(Math.abs(ind.x + ind.width - (bar.x + bar.width)), `${what} 오른쪽 끝`).toBeLessThan(1.5);
    return ind;
  }

  test('CG. 층 목록 업종 띠 — 막대 아래 같은 가로 자리 · 조각 폭 = 점포 수 ÷ 가장 많은 층 · 범주 색 · 범례(대분류)·층 모름·자리 없는 점포 · 층 줄 모양 그대로 · 답이 늦어도 층 줄이 안 밀림 · 휴대폰 넷째 줄 · 1024·1000 · 넘침 0 · 13px · 종이에 그대로 · 함수가 없으면 띠만 빠짐', async ({
    page,
  }, testInfo) => {
    // 답을 1.5초 늦춘다 — 자리를 미리 잡아 두었는지(층 줄이 안 밀리는지) 본다.
    await openBand(page, BAND_ROWS, 1500);
    const card = page.locator('.card--floors');
    const phone = (page.viewportSize()?.width ?? 0) <= 720;

    // ⓪ 답 전 — 점포 있는 층(2·1층)에만 빈 자리 · 답 뒤 1층 줄 자리가 그대로(답이 늦어도 안 밀린다).
    await expect(card.locator('.floor__ind--pending')).toHaveCount(2);
    const rowY = async () => (await box(card.locator('#floor-1 .floor__row'))).y;
    const beforeY = await rowY();
    const listBefore = await box(card.locator('ol.floors'));
    await expect(card.locator('.floor__ind:not(.floor__ind--pending)')).toHaveCount(2);
    await expect(card.locator('.floor__ind--pending')).toHaveCount(0);
    expect(Math.abs((await rowY()) - beforeY)).toBeLessThan(0.5);
    expect(Math.abs((await box(card.locator('ol.floors'))).height - listBefore.height)).toBeLessThan(0.5);

    // ① 띠는 버튼 밖 · 점포 0 층은 띠 줄 자체가 없다 · 층 줄 모양(칸 틀·칸 수·높이)은 띠 있는 층과 없는 층이 같다.
    await expect(card.locator('.floor__row .floor__ind')).toHaveCount(0);
    await expect(headOf(page, 3).locator('.floor__ind')).toHaveCount(0);
    await expect(headOf(page, -1).locator('.floor__ind')).toHaveCount(0);
    const shape = (no: number) =>
      headOf(page, no)
        .locator('.floor__row')
        .evaluate((el) => ({
          cols: el.ownerDocument.defaultView!.getComputedStyle(el).gridTemplateColumns,
          kids: el.children.length,
          h: Math.round(el.getBoundingClientRect().height),
        }));
    expect(await shape(2)).toEqual(await shape(3));
    await expect(headOf(page, 2).getByRole('button')).toHaveCount(1);

    // ② 가로 자리 = 막대 칸 · 조각 폭 = n ÷ 4(2층) — 2층 띠 = 칸 전체 · 1층 띠 = 절반.
    const ind2 = await expectBandUnderBar(page, 2, '2층');
    const seg2 = headOf(page, 2).locator('.floor__ind-seg');
    await expect(seg2).toHaveCount(2);
    expect(await seg2.evaluateAll((els) => els.map((e) => e.getAttribute('data-cat')))).toEqual(['food', 'sci']);
    const food2 = await box(seg2.nth(0));
    const sci2 = await box(seg2.nth(1));
    expect(Math.abs(food2.width / ind2.width - 0.25)).toBeLessThan(0.02);
    expect(Math.abs(sci2.width / ind2.width - 0.75)).toBeLessThan(0.02);
    expect(Math.abs(food2.x - ind2.x)).toBeLessThan(0.5);
    const ind1 = await expectBandUnderBar(page, 1, '1층');
    const seg1 = headOf(page, 1).locator('.floor__ind-seg');
    expect(await seg1.evaluateAll((els) => els.map((e) => e.getAttribute('data-cat')))).toEqual(['food', 'retail']);
    const last1 = await box(seg1.nth(1));
    expect(Math.abs((last1.x + last1.width - ind1.x) / ind1.width - 0.5)).toBeLessThan(0.02);
    expect(ind2.height).toBeGreaterThanOrEqual(5);
    // 색 토큰(§2-7 고정) — 음식 파랑 · 소매 주황 · 과학·기술 청록.
    await expect(seg2.nth(0)).toHaveCSS('background-color', 'rgb(42, 120, 214)');
    await expect(seg2.nth(1)).toHaveCSS('background-color', 'rgb(27, 175, 122)');
    await expect(seg1.nth(1)).toHaveCSS('background-color', 'rgb(235, 104, 52)');
    // 띠는 옆 글에 없는 업종을 말한다 — 그림 이름.
    await expect(headOf(page, 2).locator('.floor__ind')).toHaveAttribute('role', 'img');
    await expect(headOf(page, 2).locator('.floor__ind')).toHaveAttribute(
      'aria-label',
      '2층 가게 업종(대분류): 음식 1곳 · 과학·기술 3곳',
    );
    // 휴대폰 — 세 줄 묶음 아래 넷째 줄(점포 글 아래) · 막대와 같은 폭 전체. 넓은 화면 — 층 줄 버튼 바로 아래.
    const stores2 = await box(headOf(page, 2).locator('.floor__stores'));
    const btn2 = await box(headOf(page, 2).locator('.floor__row'));
    if (phone) expect(ind2.y).toBeGreaterThanOrEqual(stores2.y + stores2.height - 1);
    expect(ind2.y).toBeGreaterThanOrEqual(btn2.y + btn2.height - 10);
    expect(ind2.y).toBeLessThanOrEqual(btn2.y + btn2.height + 1);

    // ③ 카드 아래 줄 — 범례(대분류 · 이 땅의 가게 · 소분류 · 그려진 범주만 고정 차례) · 층 모름 · 자리 없는 점포.
    await expect(card.locator('.floor__ind-legend')).toHaveText(
      '막대 아래 가는 띠 = 이 땅의 가게 수와 업종 대분류(층을 펼치면 나오는 가게 목록은 소분류): 음식 · 소매 · 과학·기술',
    );
    await expect(card.locator('.floor__ind-swatch').nth(1)).toHaveCSS('background-color', 'rgb(235, 104, 52)');
    await expect(card.locator('.floor__ind-unknown')).toHaveText(
      '층 모름 5곳 — 원본에 층이 비어 있거나 읽을 수 없는 가게, 숫자 없이 "지하"라고만 적힌 가게 (음식 4 · 부동산 1)',
    );
    await expect(card.locator('.floor__ind-placeless')).toHaveText(
      '자리 없는 점포 2곳 — 이 건물 층 목록에 없는 층에 적힌 가게 (7층 2곳)',
    );
    for (const sel of ['.floor__ind-legend', '.floor__ind-unknown', '.floor__ind-placeless']) {
      await expect(card.locator(sel)).toHaveCSS('font-size', '13px');
    }
    // 글은 그대로 — 「점포 4」·「점포 2」.
    await expect(headOf(page, 2).locator('.floor__stores')).toHaveText('점포 4');
    await expect(headOf(page, 1).locator('.floor__stores')).toHaveText('점포 2');
    // 가로 넘침 0(문서·카드).
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    expect(await card.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    await card.screenshot({ path: testInfo.outputPath(`cg-floors-${testInfo.project.name}.png`) });

    // ④ PC 두 칸 1024(층 줄 칸을 줄인 폭 · W5) · 한 열 PC 1000 — 그 폭에서도 막대 아래 같은 자리 · 카드 밖으로 안 넘친다.
    if (!phone) {
      for (const width of [1024, 1000]) {
        await page.setViewportSize({ width, height: 768 });
        await expectBandUnderBar(page, 2, `${width}px 2층`);
        await expectBandUnderBar(page, 1, `${width}px 1층`);
        expect(await card.evaluate((el) => el.scrollWidth - el.clientWidth), `${width}px 카드 넘침`).toBeLessThanOrEqual(0);
        expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
        await card.screenshot({ path: testInfo.outputPath(`cg-floors-${width}.png`) });
      }
      await page.setViewportSize({ width: 1280, height: 720 });
    } else {
      await page.setViewportSize({ width: 360, height: 780 });
      await expectBandUnderBar(page, 2, '360px 2층');
      expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
      await page.setViewportSize({ width: 412, height: 839 });
    }

    // ⑤ 종이 — 띠가 그대로 서고(폭 0 백지 아님 · 색 그대로) · 층 줄+띠는 한 덩어리(.floor__head avoid) · 카드 아래 줄도 그대로.
    await page.emulateMedia({ media: 'print' });
    await expect(headOf(page, 2).locator('.floor__ind')).toHaveCount(1);
    await expect(headOf(page, 2).locator('.floor__ind')).toBeVisible();
    if (!phone) {
      /*
        V4 보완 1 — A4 종이 흉내 폭(740 = V3 보완 2 가 「운영 page.pdf 와 같은 꼴」이라 쓴 폭 · 703 · 800)에서 띠 끝 = 막대 끝.
        740 은 `.floors` 가 카드 안쪽 폭으로 묶여 층 줄이 최소 폭(칸 합)으로 카드보다 넓은 꼴 — 띠 상자가 층 줄과 같은 칸 틀이라 같이 넓어진다
        (옛 바깥 여백 97·505px 판은 막대 76 · 띠 54 로 짧았다).
      */
      const measured: string[] = [];
      for (const pw of [740, 703, 800]) {
        await page.setViewportSize({ width: pw, height: 900 });
        const pInd = await expectBandUnderBar(page, 2, `종이 ${pw} 2층`);
        expect(pInd.width, `종이 ${pw} 띠 폭`).toBeGreaterThan(40);
        const pBar = await box(headOf(page, 2).locator('.floor__bar'));
        measured.push(`${pw}: 막대 ${pBar.width.toFixed(1)} · 띠 ${pInd.width.toFixed(1)}`);
      }
      testInfo.annotations.push({ type: '종이 폭별 막대·띠(px)', description: measured.join(' / ') });
      await page.setViewportSize({ width: 1280, height: 720 });
    } else {
      // 휴대폰 폭(412)을 둔 채 흉내 낸 종이 — 층 줄이 옛 `@media (max-width: 720px)` 묶음으로 한 칸이 되어 막대가 폭 전체 · 띠도 폭 전체(기본 규칙).
      await expectBandUnderBar(page, 2, '종이 412 2층');
      expect(await card.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    }
    await expect(seg2.nth(0)).toHaveCSS('background-color', 'rgb(42, 120, 214)');
    await expect(seg2.nth(0)).toHaveCSS('print-color-adjust', 'exact');
    await expect(headOf(page, 2)).toHaveCSS('break-inside', 'avoid');
    await expect(card.locator('.floor__ind-legend')).toBeVisible();
    await expect(card.locator('.floor__ind-unknown')).toBeVisible();
    await card.screenshot({ path: testInfo.outputPath(`cg-floors-print-${testInfo.project.name}.png`) });
    await page.emulateMedia({ media: null });
  });

  test('CH. 층 목록 업종 띠 — 함수가 없거나(PGRST202) 띠 합이 「점포 N」과 다르면 띠·범례·층 모름 줄만 빠지고 카드는 그대로', async ({
    page,
  }) => {
    // ① 함수 없음(mockFloorStack 기본값).
    await openBand(page);
    const card = page.locator('.card--floors');
    await expect(card.locator('.floor__row')).toHaveCount(4);
    await expect(card.locator('.floor__ind--pending')).toHaveCount(0);
    await expect(card.locator('.floor__ind')).toHaveCount(0);
    await expect(card.locator('.floor__ind-legend')).toHaveCount(0);
    await expect(card.locator('.floor__ind-unknown')).toHaveCount(0);
    await expect(headOf(page, 2).locator('.floor__stores')).toHaveText('점포 4');

    // ② 띠 합이 다름(2층 5 ≠ 4) — 통째로 버린다(띠와 옆 글이 다른 수를 말하지 않게).
    await page.unrouteAll({ behavior: 'ignoreErrors' });
    await openBand(page, [...BAND_ROWS, { floor_no: 2, cat_l_cd: 'I2', cat_l_nm: '음식', store_cnt: 1 }]);
    await expect(page.locator('.card--floors .floor__row')).toHaveCount(4);
    await expect(page.locator('.card--floors .floor__ind--pending')).toHaveCount(0);
    await expect(page.locator('.card--floors .floor__ind')).toHaveCount(0);
    await expect(page.locator('.card--floors .floor__ind-unknown')).toHaveCount(0);
  });

  /*
    한 열 좁은 폭(721~819 · 2026-10-26) — 기본 층 줄 칸 틀(최소 682px)이 카드 안쪽(721 → 601 · 760 → 640)보다 넓어
    721~741 은 문서가 가로로 넘치고 742~801 은 층 줄·▼ 가 카드 테두리 밖으로 나갔다 → 두 칸 1279 갈래와 같은 칸 틀.
    820 · 1023 은 기본 칸 틀 그대로(경계 양쪽을 함께 잰다). 휴대폰(720 이하)은 세 줄 묶음이라 해당 없음.
  */
  test('CL. 한 열 좁은 폭 721~819 — 층 줄·▼ 가 층 목록 카드 안 · 문서 가로 넘침 0 · 업종 띠는 막대 아래 같은 자리 · 820·1023 도 그대로', async ({
    page,
  }, testInfo) => {
    test.skip(testInfo.project.name === 'mobile', '휴대폰(720px 이하)은 세 줄 묶음 — 이 폭 갈래가 없다');
    await openBand(page, BAND_ROWS);
    const card = page.locator('.card--floors');
    await expect(card.locator('.floor__ind:not(.floor__ind--pending)')).toHaveCount(2);
    const measured: string[] = [];
    for (const vw of [721, 741, 760, 801, 819, 820, 1023]) {
      await page.setViewportSize({ width: vw, height: 900 });
      await expect(page.locator('.app--wide')).toHaveCount(0);
      const m = await card.evaluate((el) => {
        const cs = el.ownerDocument.defaultView!.getComputedStyle(el);
        const r = el.getBoundingClientRect();
        const innerRight = r.right - parseFloat(cs.borderRightWidth) - parseFloat(cs.paddingRight);
        const shown = [...el.querySelectorAll('.floors > li:not(.list__folded)')];
        const right = (sel: string) => shown.map((li) => li.querySelector(sel)?.getBoundingClientRect().right ?? -1);
        const html = el.ownerDocument.documentElement;
        const bar = el.querySelector('#floor-2 .floor__bar')!.getBoundingClientRect().width;
        return {
          innerRight,
          li: shown.map((li) => li.getBoundingClientRect().right),
          row: right('.floor__row'),
          caret: right('.floor__caret'),
          over: html.scrollWidth - html.clientWidth,
          bar,
        };
      });
      const where = `${vw}px`;
      expect(m.li.length, `${where} 보이는 층 줄`).toBe(4);
      expect(m.over, `${where} 문서 가로 넘침`).toBeLessThanOrEqual(0);
      for (const [i, x] of m.li.entries()) expect(x, `${where} ${i}번째 층 줄(li) 오른쪽`).toBeLessThanOrEqual(m.innerRight + 0.5);
      for (const [i, x] of m.row.entries()) expect(x, `${where} ${i}번째 층 줄 단추 오른쪽`).toBeLessThanOrEqual(m.innerRight + 0.5);
      for (const [i, x] of m.caret.entries()) {
        expect(x, `${where} ${i}번째 ▼ 있음`).toBeGreaterThan(0);
        expect(x, `${where} ${i}번째 ▼ 오른쪽`).toBeLessThanOrEqual(m.innerRight);
      }
      // 업종 띠 = 막대 칸(왼·오른 끝 ±1px) — 띠 칸 틀이 층 줄과 같은 묶음에서 같이 줄었는지.
      for (const no of [2, 1]) {
        const bar = await box(headOf(page, no).locator('.floor__bar'));
        const ind = await box(headOf(page, no).locator('.floor__ind-strip'));
        expect(Math.abs(ind.x - bar.x), `${where} ${no}층 띠 왼쪽 끝`).toBeLessThanOrEqual(1);
        expect(Math.abs(ind.x + ind.width - (bar.x + bar.width)), `${where} ${no}층 띠 오른쪽 끝`).toBeLessThanOrEqual(1);
      }
      measured.push(`${vw}: 카드 안쪽 오른쪽 ${m.innerRight.toFixed(1)} · 층 줄 오른쪽 ${Math.max(...m.row).toFixed(1)} · 막대 ${m.bar.toFixed(1)}`);
    }
    testInfo.annotations.push({ type: '폭별 카드 안쪽·층 줄·막대(px)', description: measured.join(' / ') });
    await page.setViewportSize({ width: 721, height: 900 });
    await card.screenshot({ path: testInfo.outputPath(`cl-floors-721-${testInfo.project.name}.png`) });
  });
});

test.describe('층별 스택뷰 — 임대 계단 막대 · 8분기 흐름 (결정 0038 C · V5)', () => {
  const Q8 = ['2024Q3', '2024Q4', '2025Q1', '2025Q2', '2025Q3', '2025Q4', '2026Q1', '2026Q2'];
  /** 집합상가 공실률 8분기 — 2025Q1 은 줄이 없다(공표 안 됨) · 마지막 = 카드 줄 값(rentStats() 의 10.08). */
  const COLL_VAC = [2.79, 2.79, null, 4.31, 7.65, 6.42, 6.74, 10.08];
  /** 집합상가 투자수익률 — 2025Q3 음수(0 선 아래로). */
  const COLL_YLD = [1.96, 1.47, null, 1.53, -0.5, 2.07, 2.3, 0.82];
  const OFF_VAC = [3.0, 2.43, 2.86, 3.05, 4.07, 3.93, 4.82, 5.5];

  /** `list_rent_stat_history` 응답 — 테헤란로 집합상가(2025Q1 줄 없음) · 오피스 8분기. 마지막 분기 = rentStats() 의 카드 줄 값. */
  function history() {
    const rows: unknown[] = [];
    Q8.forEach((q, i) => {
      if (COLL_VAC[i] !== null) {
        rows.push({
          rone_region_nm: '서울>강남>테헤란로',
          bld_type: '집합상가',
          quarter: q,
          vacancy_rate: COLL_VAC[i],
          rent_per_m2: i === 7 ? 74.6 : 73.5 + i * 0.1,
          yield_rate: COLL_YLD[i],
          income_yield_rate: 0.9,
        });
      }
      rows.push({
        rone_region_nm: '서울>강남>테헤란로',
        bld_type: '오피스',
        quarter: q,
        vacancy_rate: OFF_VAC[i],
        rent_per_m2: i === 7 ? 18.4 : 17.5 + i * 0.1,
        yield_rate: i === 7 ? 1.1 : 1.0,
        income_yield_rate: 0.84,
      });
    });
    return rows;
  }

  /** 건물을 열고 임대 카드를 펼친다. `hist` 를 안 주면 흐름 함수가 없는 상태(mockFloorStack 기본값). */
  async function openRent(page: Page, hist?: unknown[], onHistory?: () => void) {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()], industryMix(), undefined, undefined, rentStats());
    if (hist !== undefined) {
      await page.route(RENT_HISTORY_PATTERN, async (route) => {
        if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: CORS_HEADERS });
        onHistory?.();
        await route.fulfill({ status: 200, contentType: 'application/json', headers: CORS_HEADERS, body: JSON.stringify(hist) });
      });
    }
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    const rent = page.locator('section.stack section.rent');
    await expect(rent).toBeVisible();
    await openCard(page, /상권 임대 동향/);
    return rent;
  }

  const box = async (sel: ReturnType<Page['locator']>) => (await sel.boundingBox())!;
  const noOverflow = async (page: Page, rent: ReturnType<Page['locator']>, what: string) => {
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth), `${what} 문서 넘침`).toBeLessThanOrEqual(0);
    expect(await rent.evaluate((el) => el.scrollWidth - el.clientWidth), `${what} 카드 넘침`).toBeLessThanOrEqual(0);
  };

  /** 계단 막대 — 1층(가장 비싼 구간)이 칸 끝 · 2층 막대 폭 ÷ 1층 막대 폭 = 32.48 ÷ 74.6. */
  async function expectSteps(rent: ReturnType<Page['locator']>, what: string) {
    const fill = (k: string) => rent.locator(`.rent__floors tr[data-floor="${k}"] .rent__step-fill`);
    const cell = await box(rent.locator('.rent__floors tr[data-floor="1"] .rent__step'));
    const one = await box(fill('1'));
    const two = await box(fill('2'));
    expect(one.width, `${what} 1층 막대 폭`).toBeGreaterThan(20);
    expect(Math.abs(two.width / one.width - 32.48 / 74.6), `${what} 2층 ÷ 1층`).toBeLessThan(0.02);
    // 1층 막대 = 칸 안쪽 끝까지(왼쪽 여백 12px 뺀 폭).
    expect(Math.abs(one.x + one.width - (cell.x + cell.width)), `${what} 1층 막대 끝`).toBeLessThan(1.5);
    // 금액 글과 막대 사이 틈 12px(글에 막대가 붙어 숫자의 일부처럼 읽히지 않게).
    const val = await box(rent.locator('.rent__floors tr[data-floor="1"] td').first());
    expect(one.x - (val.x + val.width), `${what} 금액 ↔ 막대 틈`).toBeGreaterThanOrEqual(11);
  }

  /** 8분기 흐름 — 공실률 막대 높이 ÷ 그림 높이 = 값 ÷ 위 끝(10%) · 빠진 분기는 「–」. */
  async function expectTrend(rent: ReturnType<Page['locator']>, what: string) {
    const vac = rent.locator('.rent-trend__chart[data-metric="vacancy"]');
    const plot = await box(vac.locator('.rent-trend__plot'));
    expect(plot.height, `${what} 그림 높이`).toBeGreaterThan(40);
    for (const [i, q] of Q8.entries()) {
      const col = vac.locator(`.rent-trend__col[data-quarter="${q}"]`);
      const v = COLL_VAC[i];
      if (v === null) {
        await expect(col.locator('.rent-trend__gap')).toHaveText('–');
        await expect(col.locator('.rent-trend__bar')).toHaveCount(0);
        continue;
      }
      const bar = await box(col.locator('.rent-trend__bar'));
      expect(Math.abs(bar.height / plot.height - v / 20), `${what} ${q} 높이`).toBeLessThan(0.03);
      expect(bar.width, `${what} ${q} 폭`).toBeGreaterThan(2);
    }
  }

  test('CI. 임대 카드 — 층별 표 줄마다 계단 막대(사실 색 · 값에 비례) + 8분기 흐름 그림 셋(그림마다 제 눈금 · 빠진 분기 「–」 · 음수는 0 선 아래) · 종류 바꿔도 다시 안 부름 · 휴대폰 한 칸씩 · 1024·1000 · 넘침 0 · 13px · 종이 740·703 · 함수 없으면 흐름만 빠짐', async ({
    page,
  }, testInfo) => {
    let historyHits = 0;
    const rent = await openRent(page, history(), () => {
      historyHits += 1;
    });
    const phone = (page.viewportSize()?.width ?? 0) <= 720;

    // ① 계단 막대 — 층별 표 안 · 사실 색(호박 --fact-3) · 층 목록 면적 막대(파랑)와 다른 색 · 글은 그대로.
    await expect(rent.locator('.rent__floors caption')).toHaveText('층별 ㎡당 월 임대료 — 조사 상권 평균, 이 건물 값이 아님');
    await expect(rent.locator('.rent__floors tbody tr').first()).toHaveText(/6층 이상\s*22,700원/);
    await expect(rent.locator('.rent__step-fill')).toHaveCount(7);
    await expectSteps(rent, '넓은·휴대폰');
    await expect(rent.locator('.rent__step-fill').first()).toHaveCSS('background-color', 'rgb(185, 132, 42)');
    await expect(page.locator('.card--floors .floor__fill').first()).not.toHaveCSS('background-color', 'rgb(185, 132, 42)');
    await expect(rent.locator('.rent__step').first()).toHaveAttribute('aria-hidden', 'true');

    // ② 8분기 흐름 — 머리 「이 건물 값이 아님」 · 그림 셋 · 그림마다 제 눈금(공실률 0~20% · 임대료 0~100,000원 · 수익률 -0.5~2.5%).
    const fig = rent.locator('.rent__rows li .rent-trend');
    await expect(fig).toBeVisible();
    await expect(fig.locator('figcaption')).toContainText('최근 8분기 흐름 — 조사 상권 평균, 이 건물 값이 아님');
    await expect(fig.locator('.rent-trend__dir')).toHaveText('왼쪽 2024년 3분기 → 오른쪽 2026년 2분기');
    await expect(fig.locator('.rent-trend__chart')).toHaveCount(3);
    await expect(fig.locator('.rent-trend__scale')).toHaveText(['눈금 0 ~ 20%', '눈금 0 ~ 100,000원', '눈금 -0.5% ~ 2.5%']);
    await expectTrend(rent, '넓은·휴대폰');
    await expect(fig.locator('.rent-trend__note')).toHaveText('‘–’ = 그 분기에 부동산원이 이 값을 공표하지 않았습니다(0 이 아닙니다).');
    await expect(fig.locator('.rent-trend__bar').first()).toHaveCSS('background-color', 'rgb(185, 132, 42)');
    // 음수(2025Q3 -0.5%)는 0 선 아래로 — 막대 위 끝 = 0 선.
    const yld = fig.locator('.rent-trend__chart[data-metric="yield"]');
    const zero = await box(yld.locator('.rent-trend__zero'));
    const neg = await box(yld.locator('.rent-trend__col[data-quarter="2025Q3"] .rent-trend__bar'));
    expect(Math.abs(neg.y - zero.y)).toBeLessThan(1.5);
    expect(neg.height).toBeGreaterThan(5);
    await expect(yld).toHaveAttribute('role', 'img');
    await expect(yld).toHaveAttribute('aria-label', /2025년 1분기 공표값 없음 · .*2025년 3분기 -0\.5%/);
    // 13px · 가로 넘침 0.
    for (const sel of ['.rent-trend__cap', '.rent-trend__name', '.rent-trend__scale', '.rent-trend__note']) {
      await expect(fig.locator(sel).first()).toHaveCSS('font-size', '13px');
    }
    await noOverflow(page, rent, '처음 폭');
    // 넓은 화면 = 그림 셋 한 줄 · 휴대폰 = 한 칸씩 위아래(그림마다 폭 전체).
    const c0 = await box(fig.locator('.rent-trend__chart').nth(0));
    const c1 = await box(fig.locator('.rent-trend__chart').nth(1));
    if (phone) {
      expect(c1.y).toBeGreaterThan(c0.y + c0.height - 1);
      expect(Math.abs(c1.width - c0.width)).toBeLessThan(1);
    } else {
      expect(Math.abs(c1.y - c0.y)).toBeLessThan(1);
      expect(c1.x).toBeGreaterThan(c0.x + c0.width);
    }
    await rent.screenshot({ path: testInfo.outputPath(`ci-rent-${testInfo.project.name}.png`) });

    // ③ 종류를 바꾸면 그 종류의 흐름 — 흐름 요청은 다시 안 나간다(한 번 받은 네 종류에서 고른다).
    expect(historyHits).toBe(1);
    await rent.getByLabel('건물 종류 골라보기').selectOption('오피스');
    await expect(rent.locator('.rent-trend__chart[data-metric="vacancy"]')).toHaveAttribute('aria-label', /2026년 2분기 5\.5%/);
    await expect(rent.locator('.rent-trend__chart[data-metric="vacancy"]')).not.toHaveAttribute('aria-label', /10\.08%/);
    await expect(rent.locator('.rent-trend__note')).toHaveCount(0);
    await expect(rent.locator('.rent__floors tbody tr').first()).toHaveText(/11층 이상\s*28,620원/);
    await expect(rent.locator('.rent__step-fill')).toHaveCount(8);
    expect(historyHits).toBe(1);
    await rent.getByLabel('건물 종류 골라보기').selectOption('집합상가');
    await expect(rent.locator('.rent-trend__note')).toHaveCount(1);

    // ④ PC 두 칸 1024 · 한 열 PC 1000 · 360 — 그 폭에서도 비례 · 넘침 0.
    const widths = phone ? [360] : [1024, 1000];
    for (const width of widths) {
      await page.setViewportSize({ width, height: 800 });
      await expectSteps(rent, `${width}px`);
      await expectTrend(rent, `${width}px`);
      await noOverflow(page, rent, `${width}px`);
      await rent.screenshot({ path: testInfo.outputPath(`ci-rent-${width}.png`) });
    }
    await page.setViewportSize(phone ? { width: 412, height: 839 } : { width: 1280, height: 720 });

    // ⑤ 종이 — 막대·그림이 그대로(폭 0 백지 아님) · 색 그대로 · 흐름 덩어리 avoid · A4 흉내 폭 740·703 에서 넘침·잘림 0.
    await page.emulateMedia({ media: 'print' });
    await expect(fig).toBeVisible();
    await expect(fig).toHaveCSS('break-inside', 'avoid');
    await expect(fig.locator('.rent-trend__bar').first()).toHaveCSS('print-color-adjust', 'exact');
    await expect(rent.locator('.rent__step-fill').first()).toHaveCSS('background-color', 'rgb(185, 132, 42)');
    const paper = phone ? [412] : [740, 703];
    for (const pw of paper) {
      await page.setViewportSize({ width: pw, height: 900 });
      await expectSteps(rent, `종이 ${pw}`);
      await expectTrend(rent, `종이 ${pw}`);
      await noOverflow(page, rent, `종이 ${pw}`);
      const figBox = await box(fig);
      const card = await box(rent);
      expect(figBox.x + figBox.width, `종이 ${pw} 그림 오른쪽 잘림`).toBeLessThanOrEqual(card.x + card.width + 0.5);
    }
    await rent.screenshot({ path: testInfo.outputPath(`ci-rent-print-${testInfo.project.name}.png`) });
    await page.emulateMedia({ media: null });

    // ⑥ 흐름 함수가 없으면(PGRST202 · mockFloorStack 기본값) 흐름만 빠지고 카드·층별 표·계단 막대는 그대로.
    await page.unrouteAll({ behavior: 'ignoreErrors' });
    await page.setViewportSize(phone ? { width: 412, height: 839 } : { width: 1280, height: 720 });
    const rent2 = await openRent(page);
    await expect(rent2.getByText('㎡당 임대료 74,600원')).toBeVisible();
    await expect(rent2.locator('.rent__floors')).toBeVisible();
    await expect(rent2.locator('.rent__step-fill')).toHaveCount(7);
    await expect(rent2.locator('.rent-trend')).toHaveCount(0);
    await expect(rent2).not.toContainText('8분기');
  });
});

test.describe('층별 스택뷰 — 개업·폐업 전부 보기 (결정 0038 H · V6)', () => {
  /** 표 전체 창(최신 → 옛) n 분기. */
  function windowOf(n: number): string[] {
    const out: string[] = [];
    let y = 2026;
    let qq = 2;
    for (let i = 0; i < n; i++) {
      out.push(`${y}${qq}`);
      qq -= 1;
      if (qq === 0) {
        qq = 4;
        y -= 1;
      }
    }
    return out;
  }
  const ALL = windowOf(22);
  const EIGHT = ALL.slice(0, 8);
  const quarter = (qq: string, opRt: number, clRt: number) => ({
    quarter: qq,
    similr_induty_stor_co: 441,
    stor_co: 378,
    frc_stor_co: 63,
    opbiz_stor_co: 5,
    clsbiz_stor_co: 9,
    opbiz_rt: opRt,
    clsbiz_rt: clRt,
  });
  /** 8분기 창에서는 no_data 인 상권(옛 분기 자료만). */
  const NODATA = {
    status: 'no_data',
    district_id: '3110999',
    district_nm: '옛 자료만 있는 상권',
    district_type: '골목상권',
    latest_quarter: null,
    quarters: null,
    industries: null,
    other_industries: null,
    window_quarters: EIGHT,
  };
  /** 첫 상권 가장 옛 분기(코로나 무렵) 폐업률 9% — 전부 창의 눈금이 된다(8분기 창의 눈금은 2.74%). */
  const BIG = 9;

  function eightAnswer() {
    return [...openClose(), NODATA];
  }

  function allAnswer() {
    const [a, b] = openClose();
    const older = ALL.slice(8).map((qq, i) => quarter(qq, 1.0, qq === ALL[21] ? BIG : 1.5 + (i % 3) * 0.1));
    return [
      { ...a, quarters: [...(a.quarters ?? []), ...older], window_quarters: ALL, total_quarters: ALL.length },
      { ...b, window_quarters: ALL, total_quarters: ALL.length },
      {
        ...NODATA,
        status: 'ok',
        latest_quarter: ALL[18],
        quarters: [quarter(ALL[18], 1.2, 2.4), quarter(ALL[19], 1.1, 2.2)],
        window_quarters: ALL,
        total_quarters: ALL.length,
      },
    ];
  }

  /**
   * 건물을 열고 개폐업 카드를 펼친다. `all` 이 null 이면 전부 보기 함수가 없는 상태(PGRST202).
   * `hold` 를 주면 전부 보기 답을 그 약속이 풀릴 때까지 붙잡는다(답이 늦은 화면 — V6 보완 2).
   */
  async function openOc(page: Page, all: unknown[] | null, onAll?: () => void, hold?: Promise<unknown>) {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [floorRow({ floor_no: 2 }), floorRow()], industryMix());
    // 나중에 등록한 것이 먼저 잡힌다 — 8분기 꼴(`…openclose*`)이 전부 보기 이름도 잡으므로 전부 보기를 **뒤에** 건다.
    await mockJson(page, OPEN_CLOSE_PATTERN, eightAnswer());
    if (all === null && !hold) {
      await mockMissingFunction(page, OPEN_CLOSE_ALL_PATTERN);
    } else {
      await page.route(OPEN_CLOSE_ALL_PATTERN, async (route) => {
        if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: CORS_HEADERS });
        onAll?.();
        if (hold) await hold;
        if (all === null) {
          await route.fulfill({
            status: 404,
            contentType: 'application/json',
            headers: CORS_HEADERS,
            body: JSON.stringify({ code: 'PGRST202', message: 'function does not exist' }),
          });
          return;
        }
        await route.fulfill({ status: 200, contentType: 'application/json', headers: CORS_HEADERS, body: JSON.stringify(all) });
      });
    }
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    const oc = page.locator('section.stack section.oc');
    await expect(oc).toBeVisible();
    await openCard(page, /상권 개업·폐업/);
    return oc;
  }

  const box = async (sel: ReturnType<Page['locator']>) => (await sel.boundingBox())!;
  const docOverflow = (page: Page) => page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth);
  /**
   * 막대 높이 ÷ 바탕 칸 높이(%). 바탕 칸의 아래 선(1px)은 빼고 잰다(clientHeight).
   * ⓘ 화면 그림 크기(getBoundingClientRect)가 아니라 배치 높이(계산된 height)로 잰다 — 종이는 판 전체를 95%로 줄여 찍어(결정 0038 V3)
   *   그림 크기만 줄고 clientHeight 는 그대로라 섞어 재면 5% 어긋난다.
   */
  const barPct = (bar: ReturnType<Page['locator']>) =>
    bar.evaluate((el) => (parseFloat(el.ownerDocument.defaultView!.getComputedStyle(el).height) / el.parentElement!.clientHeight) * 100);

  test('CJ. 개업·폐업 「전부 보기 (N분기)」 — N = total_quarters · 누르면 모든 상권 22칸(옛 → 최신 · 다시 안 부름) · 8분기 no_data → ok 상권은 「…까지」 · 눈금 글은 보는 창 기준 · 넓은 그림만 옆으로 밀기(칸 40px · 13px · 44px 단추) · 1024·1000 · 종이 740·703 은 밀기 풀고 잘림 0 · 함수 없으면 단추만 빠짐', async ({
    page,
  }, testInfo) => {
    let allHits = 0;
    const oc = await openOc(page, allAnswer(), () => {
      allHits += 1;
    });
    const phone = (page.viewportSize()?.width ?? 0) <= 720;

    // ① 기본은 8분기 그대로 + 단추(N = 서버 칸 값 22) · 단추 44px · 13px · 8분기 그림에는 밀기 상자 없음.
    const btn = oc.locator('.oc__all');
    await expect(btn).toHaveText('전부 보기 (22분기)');
    await expect(btn).toHaveAttribute('aria-expanded', 'false');
    expect((await box(btn)).height).toBeGreaterThanOrEqual(44);
    await expect(btn).toHaveCSS('font-size', '13px');
    await expect(oc.locator('.oc__district').first().locator('.oc__col')).toHaveCount(8);
    await expect(oc.locator('.oc__scroll')).toHaveCount(0);
    await expect(oc.locator('.oc__district').nth(2)).toContainText(
      '최근 2년(8분기) 동안 서울시가 이 상권의 개업·폐업 자료를 내지 않았습니다.',
    );
    await expect(oc.locator('.oc__scale')).toHaveText('막대가 꽉 차면 2.74%(분기) · 보는 기간(최근 2년(8분기))의 가장 큰 값 기준');
    expect(allHits).toBe(1);

    // ② 누르면 모든 상권이 같은 22분기 창 — 옛 분기 왼쪽 · 눈금 = 그 창의 가장 큰 값(9%) · 서버는 다시 안 부른다.
    await btn.click();
    await expect(btn).toHaveText('최근 2년(8분기)만 보기');
    await expect(btn).toHaveAttribute('aria-expanded', 'true');
    const blocks = oc.locator('.oc__district');
    await expect(blocks).toHaveCount(3);
    for (let i = 0; i < 3; i++) {
      const cols = blocks.nth(i).locator('.oc__col');
      await expect(cols).toHaveCount(22);
      await expect(cols.first()).toHaveAttribute('data-quarter', ALL[21]);
      await expect(cols.last()).toHaveAttribute('data-quarter', ALL[0]);
      await expect(blocks.nth(i).locator('.oc__trend-cap')).toContainText('분기별 개업률·폐업률 — 최근 22분기');
    }
    await expect(oc.locator('.oc__scale')).toHaveText(`막대가 꽉 차면 ${BIG}%(분기) · 보는 기간(최근 22분기)의 가장 큰 값 기준`);
    const first = blocks.first();
    expect(await barPct(first.locator('.oc__col').first().locator('.oc__bar--close'))).toBeCloseTo(100, 0);
    // 최신 분기 폐업률 2.04% → 같은 눈금 9% 기준 비례(8분기 창에서는 2.04 ÷ 2.74).
    expect(await barPct(first.locator('.oc__col').last().locator('.oc__bar--close'))).toBeCloseTo((2.04 / BIG) * 100, 0);
    // 빠진 분기는 빈 칸 그대로(둘째 상권 · 막대 0).
    await expect(blocks.nth(1).locator('.oc__col--missing')).toHaveCount(20);
    await expect(blocks.nth(1).locator('.oc__col--missing .oc__bar')).toHaveCount(0);
    // ⛔ 8분기 창의 no_data 가 ok 로 — 그 상권의 마지막 분기를 꼭 함께(옛 숫자를 최근처럼 보이지 않게).
    const third = blocks.nth(2);
    await expect(third.locator('.oc__quarter')).toHaveText('2021년 4분기');
    await expect(third).toContainText('이 상권 자료는 2021년 4분기까지입니다.');
    await expect(first).not.toContainText('까지입니다');
    // 글은 그대로 — 큰 숫자 줄은 최신 분기.
    await expect(first.locator('.oc__latest .oc__num').nth(2)).toHaveText('개업 5곳 · 개업률(분기) 1.13%');
    expect(allHits).toBe(1);

    // ③ 넓은 그림만 옆으로 민다 — 칸마다 40px 이상 · 글자 13px · 문서·카드는 넘치지 않음 · 밀면 움직인다.
    const scroll = first.locator('.oc__scroll');
    await expect(scroll).toHaveCSS('overflow-x', 'auto');
    expect((await box(first.locator('.oc__col').first())).width).toBeGreaterThanOrEqual(39.5);
    await expect(first.locator('.oc__tick').first()).toHaveCSS('font-size', '13px');
    const wideOk = async (what: string) => {
      expect(await docOverflow(page), `${what} 문서 넘침`).toBeLessThanOrEqual(0);
      expect(await oc.evaluate((el) => el.scrollWidth - el.clientWidth), `${what} 카드 넘침`).toBeLessThanOrEqual(0);
      expect(await scroll.evaluate((el) => el.scrollWidth - el.clientWidth), `${what} 그림이 밀기 상자보다 넓다`).toBeGreaterThan(0);
    };
    await wideOk('처음 폭');
    if (phone) {
      // 휴대폰은 최근 분기부터(👤 2026-10-25 · styles.css 720 화면 묶음의 rtl) — 열자마자 마지막 칸(최근)이 보이고 첫 칸(옛)은 왼쪽 밖.
      // 세 상권 모두 본다(V6 보완 2) — 상권마다 밀기 상자가 따로라 첫 상권만 보면 둘째·셋째가 옛 분기부터 열려도 모른다.
      for (let i = 0; i < 3; i++) {
        const b = blocks.nth(i);
        const sb = await box(b.locator('.oc__scroll'));
        const lastCol = await box(b.locator('.oc__col').last());
        const firstCol = await box(b.locator('.oc__col').first());
        expect(lastCol.x + lastCol.width, `휴대폰 상권 ${i} 최근 분기 칸이 밀기 상자 안`).toBeLessThanOrEqual(sb.x + sb.width + 1);
        expect(lastCol.x, `휴대폰 상권 ${i} 최근 분기 칸이 밀기 상자 안(왼쪽)`).toBeGreaterThanOrEqual(sb.x - 1);
        expect(firstCol.x, `휴대폰 상권 ${i} 옛 분기 칸은 왼쪽 밖`).toBeLessThan(sb.x);
      }
    }
    // 휴대폰(rtl)은 왼쪽으로 밀면 scrollLeft 가 음수(크롬 표준) · 넓은 화면은 오른쪽으로 밀면 양수.
    const moved = await scroll.evaluate((el, toLeft) => {
      el.scrollLeft = toLeft ? -10000 : 10000;
      return el.scrollLeft;
    }, phone);
    if (phone) expect(moved).toBeLessThan(0);
    else expect(moved).toBeGreaterThan(0);
    await oc.screenshot({ path: testInfo.outputPath(`cj-oc-all-${testInfo.project.name}.png`) });

    // ④ PC 두 칸 1024 · 한 열 PC 1000 · 360 — 그 폭에서도 문서·카드 넘침 0.
    for (const width of phone ? [360] : [1024, 1000]) {
      await page.setViewportSize({ width, height: 800 });
      await wideOk(`${width}px`);
    }
    await page.setViewportSize(phone ? { width: 412, height: 839 } : { width: 1280, height: 720 });

    // ⑤ 종이 — 단추 없음 · 밀기를 풀고(visible) 종이 폭에 맞춤(그림 오른쪽 잘림 0) · 막대·색 그대로 · 추이 덩어리 avoid.
    await page.emulateMedia({ media: 'print' });
    await expect(btn).toBeHidden();
    await expect(scroll).toHaveCSS('overflow-x', 'visible');
    await expect(first.locator('.oc__trend')).toHaveCSS('break-inside', 'avoid');
    await expect(first.locator('.oc__bar--open').first()).toHaveCSS('print-color-adjust', 'exact');
    for (const pw of phone ? [412] : [740, 703]) {
      await page.setViewportSize({ width: pw, height: 900 });
      expect(await docOverflow(page), `종이 ${pw} 문서 넘침`).toBeLessThanOrEqual(0);
      const card = await box(oc);
      for (let i = 0; i < 3; i++) {
        const cols = blocks.nth(i).locator('.oc__cols');
        expect(await cols.evaluate((el) => el.scrollWidth - el.clientWidth), `종이 ${pw} 상권 ${i} 칸 넘침`).toBeLessThanOrEqual(0);
        const c = await box(cols);
        expect(c.x + c.width, `종이 ${pw} 상권 ${i} 그림 오른쪽 잘림`).toBeLessThanOrEqual(card.x + card.width + 0.5);
        const lastCol = await box(blocks.nth(i).locator('.oc__col').last());
        expect(lastCol.x + lastCol.width, `종이 ${pw} 상권 ${i} 마지막 칸`).toBeLessThanOrEqual(c.x + c.width + 0.5);
      }
      expect(await barPct(first.locator('.oc__col').first().locator('.oc__bar--close'))).toBeCloseTo(100, 0);
    }
    await oc.screenshot({ path: testInfo.outputPath(`cj-oc-all-print-${testInfo.project.name}.png`) });
    await page.emulateMedia({ media: null });
    await page.setViewportSize(phone ? { width: 412, height: 839 } : { width: 1280, height: 720 });

    // ⑥ 되돌리면 8분기 그대로(밀기 상자 없음 · 눈금도 8분기 기준) · 그래도 다시 안 부른다.
    await btn.click();
    await expect(first.locator('.oc__col')).toHaveCount(8);
    await expect(oc.locator('.oc__scroll')).toHaveCount(0);
    await expect(oc.locator('.oc__scale')).toContainText('보는 기간(최근 2년(8분기))');
    expect(allHits).toBe(1);

    // ⑦ 전부 보기 함수가 없으면(PGRST202) 단추만 빠지고 카드·8분기 그림은 그대로.
    await page.unrouteAll({ behavior: 'ignoreErrors' });
    const oc2 = await openOc(page, null);
    await expect(oc2.locator('.oc__district').first().locator('.oc__col')).toHaveCount(8);
    await expect(oc2.locator('.oc__name')).toHaveCount(3);
    await expect(oc2.locator('.oc__all')).toHaveCount(0);
    await expect(oc2).not.toContainText('전부 보기');
  });

  test('CK. 개업·폐업 전부 보기 단추 — 답이 늦어도 그림이 안 밀린다(빈 상자 · 단추와 같은 높이 · 안 보임) · 함수 없음이면 빈 상자가 접히고 단추 0', async ({
    page,
  }, testInfo) => {
    // ① 전부 답을 붙잡아 둔 채 카드를 연다 — 단추 자리에 보이지 않는 빈 상자.
    let release!: () => void;
    const hold = new Promise<void>((r) => (release = r));
    const oc = await openOc(page, allAnswer(), undefined, hold);
    const slot = oc.locator('.oc__all--slot');
    const btn = oc.locator('button.oc__all');
    await expect(slot).toHaveCount(1);
    await expect(slot).toHaveAttribute('aria-hidden', 'true');
    await expect(slot).toHaveCSS('visibility', 'hidden');
    await expect(slot).toBeHidden();
    await expect(slot).toHaveText('');
    await expect(btn).toHaveCount(0);
    await expect(oc.locator('.oc__district')).toHaveCount(3);
    const firstDistrict = oc.locator('.oc__district').first();
    const yBefore = (await box(firstDistrict)).y;
    const scaleYBefore = (await box(oc.locator('.oc__scale'))).y;
    const slotH = (await box(slot)).height;

    // ② 1.5초 늦게 답한다 → 그 자리에 단추 · 높이 같고 아래가 안 밀린다.
    await page.waitForTimeout(1500);
    release();
    await expect(btn).toHaveText('전부 보기 (22분기)');
    await expect(slot).toHaveCount(0);
    const btnH = (await box(btn)).height;
    const yAfter = (await box(firstDistrict)).y;
    const scaleYAfter = (await box(oc.locator('.oc__scale'))).y;
    testInfo.annotations.push({
      type: 'CK 실측',
      description: `${testInfo.project.name}: 빈 상자 ${slotH}px · 단추 ${btnH}px · 첫 상권 y ${yBefore} → ${yAfter} · 눈금 y ${scaleYBefore} → ${scaleYAfter}`,
    });
    console.log(`[CK 실측] ${testInfo.project.name}: 빈 상자 ${slotH}px · 단추 ${btnH}px · 첫 상권 y ${yBefore} → ${yAfter}`);
    expect(Math.abs(btnH - slotH), '빈 상자 높이 = 단추 높이').toBeLessThan(0.5);
    expect(Math.abs(yAfter - yBefore), '첫 상권 줄이 안 밀린다').toBeLessThan(1);
    expect(Math.abs(scaleYAfter - scaleYBefore), '눈금 줄이 안 밀린다').toBeLessThan(1);

    // ③ 함수 없음(PGRST202)이 늦게 오면 — 그동안 빈 상자 → 답이 오면 접히고 단추 0 · 카드·8분기는 그대로.
    await page.unrouteAll({ behavior: 'ignoreErrors' });
    let release2!: () => void;
    const hold2 = new Promise<void>((r) => (release2 = r));
    const oc2 = await openOc(page, null, undefined, hold2);
    await expect(oc2.locator('.oc__all--slot')).toHaveCount(1);
    release2();
    await expect(oc2.locator('.oc__all--slot')).toHaveCount(0);
    await expect(oc2.locator('.oc__all')).toHaveCount(0);
    await expect(oc2.locator('.oc__district').first().locator('.oc__col')).toHaveCount(8);
  });
});
