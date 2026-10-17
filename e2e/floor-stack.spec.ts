import { test, expect, type Page } from '@playwright/test';
import {
  searchHit,
  floorRow,
  coverageStats,
  parcelTx,
  sigunguTxStats,
  priceBands,
  priceBandGate,
  industryMix,
  industryFloors,
  industryMedian,
  industryMedianM,
  industryDetailTwoDistricts,
  industryMixTwoDistricts,
  nearbyPermits,
  basePrices,
  lhNotice,
  priceGate,
  rentStat,
  rentStatOld,
  rentStats,
  openClose,
  openCloseNotSeoul,
  dataFreshness,
  scorecard,
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
// 참고 매매 시세 밴드(Stage B · 결정 0013). 이것도 안 막으면 실존하지 않는 도메인으로
// 요청이 나간다 — 기본값은 빈 배열이라 섹션이 아예 안 뜬다(기존 테스트에 영향 0).
const PRICE_BAND_PATTERN = '**/rest/v1/rpc/list_price_bands*';
// 국세청 기준시가. 참고 시세 카드 **안**에 한 줄로 붙지만 자료는 완전히 다른 것이다.
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
// 상권 개업·폐업(결정 0033). ⚠️ 기본값은 **함수가 없는 상태**다(임대 동향과 같은 이유) — 다른
// 스펙들의 카드 수·화면이 그대로 남는다. 카드를 보는 것은 스펙 AI 뿐이다.
const OPEN_CLOSE_PATTERN = '**/rest/v1/rpc/list_district_openclose*';
// 호실 구성표(결정 0032). 요약은 건물을 열 때 · 목록은 층을 펼칠 때 나간다.
// ⚠️ 기본값은 둘 다 **함수가 없는 상태**다 — 그때 요약도 "자료 없음" 안내도 조용히 빠지는지가
//    스펙 AH 의 관심사다(빈 배열로 두면 "호실 자료가 없는 건물"이라는 **다른 답**이 되어 안내가 선다).
const UNIT_SUMMARY_PATTERN = '**/rest/v1/rpc/list_unit_floor_summary*';
const FLOOR_UNITS_PATTERN = '**/rest/v1/rpc/list_floor_units*';
// 개별공시지가 한 줄(결정 0036 결정 7) — 층별 화면 머리의 사양 칸 아래. 건물을 열 때 나간다.
// ⚠️ 기본값은 **함수가 없는 상태**다 — 그때 줄이 조용히 빠지고 머리 모양이 그대로라 다른 스펙이 영향을
//    안 받는다. 값을 보는 것은 스펙 AP 뿐이다(안 막으면 실존하지 않는 도메인으로 나가 DNS 에 좌우된다).
const LAND_PRICE_PATTERN = '**/rest/v1/rpc/get_parcel_land_price*';
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
// 참고 시세 성적표 — 이것도 **입구**에서 나가는 요청이다(LH 공고와 한 쌍으로 막는다).
// ⚠️ 기본값은 역시 **함수가 없는 상태**다 — 마이그레이션 적용 전 라이브이 그것이고,
//    그때 카드가 통째로 조용히 빠지는지가 다른 입구 시험들이 기대는 전제다.
const PRICE_GATE_PATTERN = '**/rest/v1/rpc/list_price_gate*';
// 동네 매매 단가 흐름(결정 0027) — 이것도 **입구**에서 나가는 요청이다(위 둘과 한 쌍으로 막는다).
// ⚠️ 기본값은 역시 **함수가 없는 상태**다 — 마이그레이션 적용 전 라이브이 그것이고,
//    그때 카드가 통째로 조용히 빠지는지가 스펙 X 의 관심사다.
const TX_YEARLY_PATTERN = '**/rest/v1/rpc/get_sigungu_tx_yearly*';
// 성적표 파일은 **같은 출처**(개발 서버의 public/)라 REST 목과 결이 다르다 — 라우트를
// 안 걸면 진짜 파일이 그대로 나간다. 스펙 AB 는 작은 판으로 갈아 끼운다.
const SCORECARD_PATTERN = '**/scorecard-v2.json';

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
  bands: unknown[] = [],
  floors?: unknown[],
  mix?: unknown,
  bases?: unknown[],
  permits?: unknown,
  rents?: unknown[],
) {
  await mockJson(page, STATS_PATTERN, [coverageStats()]);
  await mockJson(page, FLOOR_PATTERN, floors ?? [floorRow()]);
  await mockJson(page, PRICE_BAND_PATTERN, bands);
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
  // 상권 개업·폐업도 기본이 **함수가 없는 상태**다(위 상수 주석 참조). 스펙 AI 만 덮어쓴다.
  await mockMissingFunction(page, OPEN_CLOSE_PATTERN);
  // 호실 구성표 둘도 기본이 **함수가 없는 상태**다(위 상수 주석 참조). 호실을 보는 스펙은
  // 이 뒤에 자기 응답을 한 번 더 등록한다(나중에 등록한 것이 먼저 잡힌다).
  await mockMissingFunction(page, UNIT_SUMMARY_PATTERN);
  await mockMissingFunction(page, FLOOR_UNITS_PATTERN);
  // 개별공시지가 한 줄도 기본이 **함수가 없는 상태**다(위 상수 주석 참조). 스펙 AP 만 덮어쓴다.
  await mockMissingFunction(page, LAND_PRICE_PATTERN);
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
    성적표 카드도 구를 고르는 순간 함께 묻는다 — 같은 이유로 막는다.
    기본값이 **함수가 없는 상태**인 것도 같다(마이그레이션 적용 전 라이브). 성적을 보고
    싶은 시험은 이 뒤에 자기 응답을 한 번 더 등록한다.
  */
  await mockMissingFunction(page, PRICE_GATE_PATTERN);
  /*
    동네 매매 단가 흐름 카드도 구를 고르는 순간 함께 묻는다 — 같은 이유로 막는다.
    기본값이 **함수가 없는 상태**인 것도 같다(마이그레이션 적용 전 라이브). 흐름을 보고
    싶은 시험은 이 뒤에 자기 응답을 한 번 더 등록한다.
  */
  await mockMissingFunction(page, TX_YEARLY_PATTERN);
}

/** 시도 칩을 눌러 구 목록을 펼치고, 그 안의 구 칩을 눌러 고른다. */
async function pickGu(page: Page, sidoName: string, guName: string) {
  await page.getByRole('button', { name: new RegExp(`^${sidoName}$`) }).click();
  await page.getByRole('button', { name: guName }).click();
}

/**
 * 접힌 카드를 펼친다(로드맵 Wave 2 『한 장 요약 접힘 틀』).
 *
 * 첫 화면에 펼쳐 두는 카드는 넷뿐이라 『참고 매매 시세』는 접힌 채로 시작한다 —
 * 그 안의 값·근거를 보려면 한 번 눌러야 한다. 이미 펼쳐져 있으면 아무 일도 안 한다.
 */
async function openCard(page: Page, title: RegExp) {
  const toggle = page.getByRole('button', { name: title });
  if ((await toggle.getAttribute('aria-expanded')) === 'false') await toggle.click();
}

async function search(page: Page, text: string) {
  await page.getByLabel('건물명 또는 주소').fill(text);
  await page.getByRole('button', { name: '검색' }).click();
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
  await page.locator('.entrybar').getByRole('button', { name: button }).click();
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
    // 참고 시세 섹션(Stage B)까지 한 벌로 태운다 — "섹션이 통째로 안 뜨는 회귀"를 잡는 자리다.
    await mockFloorStack(page, [], priceBands(), [floorRow({ floor_no: 2 }), floorRow()]);

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
    // 참고 시세 섹션도 같은 종류의 위험을 진다(별도 RPC 하나에 통째로 달려 있다).
    // ⚠️ 이 카드는 첫 화면에서 **접혀 있다**(펼침 상한 4장) — 카드 자체는 보이지만
    //    값·근거는 펼쳐야 나온다.
    await expect(stack.locator('section.band')).toBeVisible();
    await openCard(page, /참고 매매 시세/);
    await expect(stack.getByText(/C등급 · 파생 추정/)).toBeVisible();
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

  test('B. 새 검색을 제출하면 이전 층 스택이 즉시 사라진다', async ({ page }) => {
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
    await mockJson(page, SEARCH_PATTERN, [searchHit({ bld_id: 'other', bld_nm: '다른빌딩' })], 300);

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
    await expect(page.locator('section.stack')).toHaveCount(0);
    await expect(page.getByText('위에서 건물을 검색해 선택해 주세요.')).toBeVisible();
  });

  test('C. 검색 결과 0건일 때도 이전 층 스택이 사라진다', async ({ page }) => {
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
    await expect(stack.getByText(/강남구 층대별 거래 단가/)).toBeVisible();
    await expect(stack.getByText(/중앙값 ㎡당 2,250만/)).toBeVisible();
    await expect(stack.getByText('표본 부족').first()).toBeVisible();
    // 출처표시 의무 + 절대 규칙 3(근거 레벨·표본 수 병기).
    await expect(stack.getByText(/국토교통부 상업업무용 부동산 매매 실거래가/)).toBeVisible();
    // 같은 배지가 세 잣대 카드(물결 1-C2) 칸 머리에도 선다 — 실거래 카드 안으로 좁힌다.
    await expect(stack.locator('section.tx').getByText(/A등급 · 실거래/)).toBeVisible();
    // 절대 규칙 2 — 금칙어 5종은 화면 어디에도 없다.
    // ⚠️ '참고 매매 시세'는 절대 규칙 2 가 정한 **허용 대체어**라 Stage B 섹션이 쓴다.
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
      '지분 = 건물 일부 몫만 사고판 거래라 ㎡당 값이 낮게 나옵니다 — 층대별 단가·참고 가격대 계산에서는 뺍니다.',
    );
    // G 의 규칙(Stage A 블록 안에는 '시세'라는 말조차 없다)을 설명 줄이 선 상태에서도 본다 —
    // G 는 지분 없는 거래뿐이라 이 줄이 그려지는 경우를 못 본다.
    await expect(page.locator('section.stack section.tx')).not.toContainText('시세');
  });

  // ── 참고 매매 시세 밴드 (Stage B · 결정 0013) ─────────────────────────────
  // 이 화면에서 **추정값이 나오는 유일한 자리**다. 값과 근거가 한 몸으로 나가는지,
  // 안 내는 이유 넷을 각각 다른 말로 하는지를 눈으로 확인한다.

  test('H. 참고 시세 밴드가 근거·표본·등급과 함께 뜨고, 값을 안 내는 층은 이유가 다르게 적힌다', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [parcelTx()], priceBands(), [
      floorRow({ floor_no: 2 }),
      floorRow(),
      floorRow({ floor_no: -1 }),
    ]);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const band = page.locator('section.band');
    await expect(band).toBeVisible();
    await openCard(page, /참고 매매 시세/);
    // 매매인지 임대인지를 화면이 먼저 말한다(절대 규칙 5 — 임대 실거래는 존재하지 않는다).
    await expect(band.getByText(/사고파는 값이고 월세·보증금이 아닙니다/)).toBeVisible();
    // 값 + 근거 단계 + 표본 수가 한 줄에 함께 나온다(절대 규칙 3).
    await expect(
      band.getByText('비슷한 호실 한 칸 32.8㎡ (10평) 기준 2.4억~6.2억'),
    ).toBeVisible();
    await expect(band.getByText(/500m 안 같은 층/)).toBeVisible();
    await expect(band.getByText(/거래 15건/)).toBeVisible();
    await expect(band.getByText(/먼 근거/).first()).toBeVisible();
    await expect(band.getByText(/C등급 · 파생 추정/)).toBeVisible();
    // 1층은 오차가 기준선 밖이라서, 지하는 검증한 적이 없어서 — 서로 다른 말로 적는다.
    await expect(band.getByText(/1층은 내지 않습니다/)).toBeVisible();
    // 1층 문구는 층마다의 성적을 볼 자리(첫 화면 성적표 카드)로 안내한다.
    await expect(band.getByText(/「참고 시세는 얼마나 맞나」 카드에서 볼 수 있습니다/)).toBeVisible();
    await expect(band.getByText(/참고 시세를 내지 않은 층: 지하 1층/)).toBeVisible();
    // 지하는 줄로 반복하지 않는다 — 값 있는 2층 + 1층 두 줄뿐이다.
    await expect(band.locator('.band__row')).toHaveCount(2);

    // 밴드 줄을 누르면 위쪽 층 목록의 그 층이 펼쳐진다(두 목록이 서로를 가리킨다).
    await band.locator('.band__hit').first().click();
    await expect(page.locator('.detail')).toBeVisible();
    await expect(band.locator('.band__row--on')).toHaveCount(1);

    // Stage A 의 사실 표시는 그대로 남아 있다(추정이 사실을 밀어내지 않는다).
    // ⚠️ 거래가 없는 층의 뱃지 칸은 **빈 span** 이라 hidden 이다 — 자리는 남기되 0건이라
    //    적지 않기 때문이다. 그래서 글자로 찾는다(1층에 거래 1건이 붙는다).
    await expect(page.locator('.floor__tx', { hasText: '거래 1건' })).toBeVisible();
  });

  test('I. 기준선을 못 넘은 구에서는 층별 밴드 없이 한 문단만 나온다', async ({ page }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [parcelTx()], priceBandGate());

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const band = page.locator('section.band');
    await expect(band).toBeVisible();
    await openCard(page, /참고 매매 시세/);
    await expect(band.locator('.band__row')).toHaveCount(0);
    await expect(band.getByText(/구 전체는 아직 참고 시세를 내지 않습니다/)).toBeVisible();
    // 오차율·구 개수는 서버가 정본이라 화면에 복사하지 않는다(결정 0013 §4).
    await expect(band.locator('.band__gate')).not.toContainText('%');
    // 층 목록과 실거래 기록은 그대로 나온다 — 밴드만 없는 것이다.
    await expect(page.locator('.floors .floor')).toHaveCount(1);
    // ⚠️ **층별 화면 안으로 좁혀서** 본다(형제 시험 G 와 같은 방식). 화면 아래 안내가
    //    카드 제목을 한 번씩 더 적으므로(넘기기 구역의 "어디서 뭐를 보나"), 좁히지 않으면
    //    같은 글자가 둘이 되어 어느 쪽을 잡았는지 모르게 된다.
    await expect(page.locator('section.stack').getByText('실거래 기록')).toBeVisible();
  });

  // ── 화면 공짜 3종 (로드맵 Wave 2 PR-A) ────────────────────────────────────
  // 서버에서 이미 오는데 화면이 안 쓰던 값 셋이다. 셋 다 "서버 응답 한 칸이 조용히
  // 빠지면 화면에서도 조용히 사라지는" 종류라 여기서 눈으로 확인한다.

  test('J. 구 칩 건물 수 · 도로접면 · 업종 요약 · 건물 스펙 4칸이 함께 뜬다', async ({ page }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [], [
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
    // 새로 늘어난 문구에도 금칙어(절대 규칙 2)는 없다. '시세'는 참고 시세 섹션에
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
    await mockFloorStack(page, [], [], undefined, industryMix());

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
  // 첫 화면에 펼쳐 두는 카드는 **넷**뿐이고, 다섯 번째(참고 매매 시세 = 이 화면에서
  // 추정값이 나오는 유일한 자리)는 접힌 채로 시작한다. 다만 접힘은 **숨김이 아니다** —
  // 접힌 카드도 제목과 핵심 한 줄은 그대로 보여야 한다. 이 배치는 CSS·상태가 얽혀 있어
  // 단위 시험만으로는 "화면에서 정말 그런가"를 못 본다.

  test('L. 카드 넷만 펼쳐져 있고, 접힌 카드는 눌러야 내용이 나온다', async ({ page }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(
      page,
      [parcelTx()],
      priceBands(),
      [floorRow({ floor_no: 2 }), floorRow()],
      industryMix(),
    );

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();

    const stack = page.locator('section.stack');
    // 다섯 장 + 늘 서는 빈 카드 셋(결정 0036 결정 2 · 물결 1-B — 아무것도 안 불러서 목업이 없어도 선다)
    // ⓘ 세 잣대(물결 1-C2)는 국세청·부동산원이 둘 다 비면(이 시험의 목업 = 함수 없음) 서지 않는다.
    await expect(stack.locator('.card')).toHaveCount(8);
    await expect(stack.locator('.card__toggle[aria-expanded="true"]')).toHaveCount(4);

    const band = stack.locator('section.band');
    // 접힌 채로도 제목과 핵심 한 줄은 읽힌다 — 본문(값)만 없다.
    await expect(band.locator('.card__title')).toHaveText('참고 매매 시세 (추정값)');
    await expect(band.locator('.card__summary')).toHaveText('값을 낸 층 1개');
    // ⚠️ "DOM 에 없다"가 아니라 **"안 보인다"**를 본다. 접힌 본문은 자리에 남겨 둔다 —
    //    안 그러면 종이로 뽑을 때 이 카드가 통째로 빠진다(결정 0020, 시험 R·S).
    await expect(band.locator('.card__body')).toBeHidden();

    // 누르면 그 자리에서 값·근거가 함께 나온다(절대 규칙 3 — 값과 근거는 한 몸이다).
    await openCard(page, /참고 매매 시세/);
    await expect(band.locator('.band__val').first()).toBeVisible();
    await expect(band.getByText(/C등급 · 파생 추정/)).toBeVisible();

    // 펼쳐진 카드도 접을 수 있다 — 접으면 본문만 사라지고 요약은 남는다.
    const floorsCard = stack.locator('.card--floors');
    await expect(floorsCard.locator('.floor')).toHaveCount(2);
    await floorsCard.locator('.card__toggle').click();
    await expect(floorsCard.locator('.card__body')).toBeHidden();
    await expect(floorsCard.locator('.card__summary')).toHaveText('층 2개 · 점포 4곳');

    // ⛔ 층 목록을 접어 둔 채로 시세 줄을 눌러도 그 층이 보여야 한다. 안 그러면 눌렀는데
    //    화면이 그대로라, 사람은 고장 났다고 읽는다. (진짜 브라우저에서만 도는 길이다 —
    //    스크롤을 다음 그림으로 미루는 requestAnimationFrame 이 여기서 실제로 돈다.)
    await expect(band.locator('.band__row--on')).toHaveCount(0);
    await band.locator('.band__hit').first().click();
    await expect(floorsCard.locator('.card__toggle')).toHaveAttribute('aria-expanded', 'true');
    await expect(stack.locator('.detail')).toBeVisible();
    await expect(band.locator('.band__row--on')).toHaveCount(1);
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
    await expect(fresh.locator('tbody tr')).toHaveCount(11);
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
  test('O. 링크로 바로 들어오면 검색 없이 그 건물이 열린다', async ({ page }) => {
    await mockOpenSigungu(page);
    await mockFloorStack(page, [], [], [floorRow({ floor_no: 2 }), floorRow()]);
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
    if (await isPhoneTabs(page)) {
      await expect(tabButton(page, '건물')).toHaveAttribute('aria-current', 'page');
      await expect(page.locator('.entrybar')).toHaveCount(0);
    } else {
      await expect(page.locator('.entrybar__place')).toHaveText('서울 강남구');
    }
    await expect(page.locator('section.dmap')).toHaveCount(0);
    await unfoldEntry(page, '상권 지도 보기');
    await expect(page.getByRole('heading', { name: /강남구 상권 지도/ })).toBeVisible();
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
    await mockFloorStack(page, [], [], []);

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
      priceBands(),
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
    // 빈 카드 셋은 화면에서는 선다(접힌 채 제목 + 요약 한 줄) — 아래 종이에서만 빠진다.
    for (const k of ['sales', 'pop', 'history']) {
      await expect(page.locator(`section.card--${k} .card__summary`)).toHaveText('지금은 비어 있음');
    }

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
    // 빈 카드 셋도 종이에서 빠진다(👤 물결 1-B — "지금은 비어 있음" 뿐이라 종이 자리만 먹는다).
    // ⓘ 빼는 이름표는 빈 상태일 때만 붙는 `card--empty` 다 — 자료가 차면 그때부터 종이에 나온다.
    await expect(page.locator('section.card--empty')).toHaveCount(3);
    for (const k of ['sales', 'pop', 'history']) {
      await expect(page.locator(`section.card--${k}`)).toBeHidden();
    }

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

    const band = page.locator('section.band');
    const floorsCard = page.locator('.card--floors');

    // 사용자가 층 목록까지 접어 둔 채로 인쇄하는 상황을 만든다.
    // (『참고 매매 시세』는 원래 접힌 채로 시작한다 — 첫 화면 펼침 상한이 넷이라서.)
    await floorsCard.locator('.card__toggle').click();
    await expect(floorsCard.locator('.card__body')).toBeHidden();
    await expect(band.locator('.card__body')).toBeHidden();

    await page.emulateMedia({ media: 'print' });

    // ⛔ 화면에서 접는 것은 "지금은 안 볼래"이지 "종이에서도 빼라"가 아니다.
    //    이게 깨지면 종이에서 카드가 **제목만 남고 통째로 사라진다**(2026-08-25 실측).
    await expect(floorsCard.locator('.card__body')).toBeVisible();
    await expect(band.locator('.card__body')).toBeVisible();
    await expect(band.locator('.band__val').first()).toBeVisible();
    // 값과 근거는 한 몸이다(절대 규칙 3) — 종이에서도 함께 나와야 한다.
    await expect(band.getByText(/C등급 · 파생 추정/)).toBeVisible();

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
    await mockJson(page, PRICE_BAND_PATTERN, []);
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
   * 참고 시세 카드 **안**에 붙지만 자료는 완전히 다른 것이다 — 추정이 아니라 고시된 값.
   * 그래서 여기서 눈으로 보는 것은 둘이다:
   *   ① 값·호 수·고시일이 한 줄에 함께 나오고, "시세가 아니다"라고 못 박는다
   *   ② 서버에 함수가 아직 없으면 **그 줄만** 빠지고 카드의 나머지는 멀쩡하다
   * (거르기·짝짓기 같은 순수 규칙은 src/lib/basePrice.test.ts 가 촘촘히 덮는다.)
   */

  /** 층 목록·밴드는 같게 두고 기준시가만 갈아 끼운다. `bases` 를 안 주면 함수가 없는 상태다. */
  async function openBuilding(page: Page, bases?: unknown[]) {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(
      page,
      [],
      priceBands(),
      [floorRow({ floor_no: 2 }), floorRow()],
      undefined,
      bases,
    );
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await openCard(page, /참고 매매 시세/);
  }

  test('U. 기준시가가 층마다 값·호 수·고시일과 함께 뜨고, 추정과 섞이지 않는다', async ({
    page,
  }) => {
    await openBuilding(page, basePrices());

    const band = page.locator('section.band');
    const rows = band.locator('.band__base-rows li');
    await expect(rows).toHaveCount(2);
    // 값만 떼어 내보내지 않는다 — 이 값은 그 층 호실들의 가운데값이다(절대 규칙 3).
    await expect(rows.first()).toContainText('2층');
    await expect(rows.first()).toContainText('㎡당 300만');
    await expect(rows.first()).toContainText('호 12개 가운데값 · 2026년 1월 1일 고시');
    // 세무 기준가격이라는 사실을 카드 안에서 한 번 못 박는다.
    await expect(band.getByText(/시세가 아닙니다/)).toBeVisible();
    await expect(band.getByText(/A등급 · 공식 고시/)).toBeVisible();

    // 추정 밴드는 그대로 남고(하나가 다른 하나를 밀어내지 않는다), 두 값이 한 줄에서 섞이지도 않는다.
    await expect(band.getByText('비슷한 호실 한 칸 32.8㎡ (10평) 기준 2.4억~6.2억')).toBeVisible();
    await expect(band.locator('.band__row').first()).not.toContainText('고시');
  });

  test('V. 서버에 함수가 아직 없으면 그 줄만 조용히 빠진다', async ({ page }) => {
    // 마이그레이션을 적용하기 전 라이브가 바로 이 상태다(404/PGRST202).
    await openBuilding(page);

    const band = page.locator('section.band');
    await expect(band.locator('.band__base')).toHaveCount(0);
    // 카드도 값도 그대로다 — "기준시가 없음"이라고 적지도 않는다.
    await expect(band.locator('.band__val').first()).toBeVisible();
    await expect(band).not.toContainText('기준시가');
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

    // ⛔ 건물을 고르면 화면의 주제가 그 건물이다 — 카드는 물러난다.
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack')).toBeVisible();
    await expect(page.locator('section.lh')).toHaveCount(0);
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
    // ⓘ 입구 카드는 이제 **셋**이다(성적표·흐름도 같은 기본값 = 함수 없음). **셋 다**
    //   빠져도 검색창이 서 있는지를 이 한 시험이 함께 본다 — 곁다리들이 본체를 못 죽인다.
    await expect(page.locator('section.score')).toHaveCount(0);
    await expect(page.locator('.app')).not.toContainText('참고 시세는 얼마나 맞나');
    await expect(page.locator('section.flow')).toHaveCount(0);
    await expect(page.locator('.app')).not.toContainText('동네 매매 단가 흐름');
  });
});

// ── 입구 — 참고 시세 성적표 (로드맵 Wave 4) ────────────────────────────────
//
// 두 갈래에서 값이 온다는 것이 이 화면의 특징이고, 그 이음매는 진짜 브라우저에서만 보인다:
//   · 판정(어느 구가 켜지나) = 서버 함수 `list_price_gate`
//   · 방법·단계 분포        = **같은 출처의 정적 파일** `/scorecard-v2.json`
// 단위 시험은 둘 다 흉내로 넣지만, "정말 그 주소를 받아 오나"는 여기서만 확인된다.
//
// ⓘ **함수가 없을 때 카드가 조용히 빠지는 경로는 여기 없다** — 그건 이미 위 스펙 X 가
//   같은 자리에서 함께 본다(그 시험은 두 입구 함수가 **둘 다** 404 인 상태에서 검색창이
//   멀쩡한지를 본다). 같은 것을 두 번 보는 시험을 만들지 않는다.
//   카드 자체가 빠지는지는 단위 시험(ScorecardSection.test.tsx)이 따로 본다.

test.describe('입구 — 참고 시세 성적표', () => {
  test('AB. 접힌 카드로 서고, 펼치면 체감 단계 분포가 가장 흔한 자리부터 나온다', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    // ⚠️ mockOpenSigungu 뒤에 등록해야 이 응답이 잡힌다(나중에 등록한 것이 먼저다).
    await mockJson(page, PRICE_GATE_PATTERN, priceGate());
    // 정적 파일도 갈아 끼운다 — 안 그러면 진짜 성적표(구운 파일)가 나가 시험이 그 판의
    // 숫자에 매인다(성적표를 다시 뽑는 날 코드 변경 0 인데 빨간불이 된다).
    await mockJson(page, SCORECARD_PATTERN, scorecard());

    await page.goto('/');
    // 구를 고르기 전에는 물을 곳이 없다 — 카드도 없다.
    await expect(page.locator('section.score')).toHaveCount(0);

    await pickGu(page, '서울', '강남구');

    const score = page.locator('section.score');
    await expect(score).toBeVisible();
    // 접혀 있어도 **이 구가 받나 못 받나**와 언제 잰 성적인가는 읽힌다.
    const summary = score.locator('.card__summary');
    await expect(summary).toContainText('참고 시세 제공');
    await expect(summary).toContainText('262건');
    await expect(summary).toContainText('성적표 v2');
    await expect(summary).toContainText('2026년 8월 15일 생성');
    await expect(score.locator('.card__body')).toBeHidden();

    await openCard(page, /참고 시세는 얼마나 맞나/);

    // ① 이 구의 성적 — 사다리와 구 평균을 나란히.
    await expect(score.locator('.score__mine')).toContainText('28.3%');
    await expect(score.locator('.score__mine')).toContainText('49.2%');

    // ② ★ 체감 단계 분포 — **가장 흔한 자리(폴백)가 맨 위**(로드맵 Wave 4).
    const stages = score.locator('.score__stages .score__rows li');
    await expect(stages).toHaveCount(2);
    await expect(stages.first()).toContainText('L6');
    await expect(stages.first()).toContainText('60.0%');
    // 커버리지가 유리한 숫자라는 정직 공지(결정 0013 §3).
    await expect(score.locator('.score__honest')).toContainText('유리');

    // ③ 전체 구 — 떨어진 구도 함께 서고, 왜 떨어졌는지가 적힌다.
    await expect(score.locator('.score__all .score__rows li')).toHaveCount(2);
    await expect(score.locator('.score__all')).toContainText('금천구');

    // ④ 방법 + 도장.
    await expect(score.locator('.grade__badge')).toHaveText('검증 성적 · 원본 성적표 v2');

    // ⛔ 건물을 고르면 화면의 주제가 그 건물이다 — 입구 카드는 물러난다.
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page);
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack')).toBeVisible();
    await expect(page.locator('section.score')).toHaveCount(0);
  });

  test('AK. 펼치면 층마다의 오차 블록이 서고, 1층이 기준선을 넘은 이유가 한 줄 붙는다', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    await mockJson(page, PRICE_GATE_PATTERN, priceGate());
    await mockJson(page, SCORECARD_PATTERN, scorecard());

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    const score = page.locator('section.score');
    await expect(score).toBeVisible();
    await openCard(page, /참고 시세는 얼마나 맞나/);

    const floors = score.locator('.score__floors');
    await expect(floors).toBeVisible();
    await expect(floors.getByRole('heading', { name: '층마다 얼마나 맞나' })).toBeVisible();
    const rows = floors.locator('.score__rows li');
    await expect(rows).toHaveCount(3);
    await expect(rows.first()).toContainText('1층');
    await expect(rows.first()).toContainText('오차 중앙값 45.0%');
    await expect(rows.first()).toContainText('739건');
    await expect(rows.nth(2)).toContainText('3층 이상');
    // 1층은 기준선을 넘었다 — 층별 화면에서 값을 안 내는 이유가 이 블록에서 보인다.
    await expect(floors.locator('.score__why')).toContainText('1층은 오차가 기준선');
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
    await expect(flow.locator('.grade__badge')).toHaveText('A등급 · 실거래');

    // ⛔ 건물을 고르면 화면의 주제가 그 건물이다 — 입구 카드는 물러난다.
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page);
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack')).toBeVisible();
    await expect(page.locator('section.flow')).toHaveCount(0);
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
    await mockFloorStack(page, [], [], undefined, industryMix(), undefined, nearbyPermits());

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
      priceBands(),
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
    // 여섯 장 + 빈 카드 셋(물결 1-B) + 세 잣대(물결 1-C2 · 접힌 채).
    await expect(stack.locator('.card')).toHaveCount(10);
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

    // ⛔ 이 카드는 조사값이다. 추정으로 읽히는 말이 섞이면 바로 옆 참고 시세 카드와
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
    await mockFloorStack(page, [], priceBands(), [floorRow({ floor_no: 2 }), floorRow()]);

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
      priceBands(),
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
    await mockFloorStack(page, [], priceBands(), [floorRow({ floor_no: 2 }), floorRow()]);

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
    await mockFloorStack(page, [], priceBands(), [floorRow({ floor_no: 2 }), floorRow()]);

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

    // 양성 대조 — 다른 줄은 여전히 한 줄 말줄임이다.
    const addrWhiteSpace = await addrEl.evaluate(
      (el) => el.ownerDocument.defaultView!.getComputedStyle(el).whiteSpace,
    );
    expect(addrWhiteSpace).toBe('nowrap');
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
  async function openBuilding(page: Page, summary?: unknown[], floors = unitFloors()) {
    const unitRequests: Array<Record<string, unknown>> = [];
    page.on('request', (r) => {
      if (r.method() === 'POST' && r.url().includes('/rpc/list_floor_units')) {
        unitRequests.push((r.postDataJSON() ?? {}) as Record<string, unknown>);
      }
    });
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [], floors);
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
          body: JSON.stringify(floorUnitsPage(args.p_offset ?? 0, args.p_limit ?? 50)),
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
    const unitRequests = await openBuilding(page, unitSummary());
    const card = page.locator('.card--floors');

    // ① 요약 둘째 줄 — 요약이 있는 층만(5층은 없다).
    const lines = card.locator('.floor__units');
    await expect(lines).toHaveCount(3);
    await expect(lines.nth(0)).toHaveText('세대 10');
    await expect(lines.nth(1)).toHaveText('호실 543칸 · 보통 4.0㎡ · 2.7~8.8㎡');
    await expect(lines.nth(2)).toHaveText('호실 690칸 · 보통 4.0㎡ · 3.2~13.1㎡');
    await expect(card.getByText(/'보통'은 그 층 호실 전용면적의 가운데값입니다/)).toBeVisible();

    // ⛔ 요약 줄 때문에 층 줄의 칸 수가 늘지 않는다(좁은 화면 포함) — 요약이 있는 층(3층)과 없는
    //    층(5층)의 층 줄이 같은 칸 배치·같은 높이여야 한다(요약은 층 줄 **밖** 둘째 줄이다).
    const shape = (label: string) =>
      floorRowOf(page, label).evaluate((el) => ({
        cols: el.ownerDocument.defaultView!.getComputedStyle(el).gridTemplateColumns,
        kids: el.children.length,
        h: Math.round(el.getBoundingClientRect().height),
      }));
    expect(await shape('3층')).toEqual(await shape('5층'));

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
    await mockFloorStack(page, [], priceBands(), [floorRow({ floor_no: 2 }), floorRow()], industryMix());
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
      '프랜차이즈 63곳 (점포의 14.29%)',
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
    await expect(oc.locator('.oc__scale')).toHaveText('막대가 꽉 차면 2.74%(분기)');
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
});

// ── 첫 화면 역할 단추 (👤 결정 0036 결정 18) ──────────────────────────────────
// 역할별 표 세 벌·저장 예외는 단위 시험이 덮는다(`FloorStack.test.tsx`·`viewerRoleStore.test.ts`·
// `App.test.tsx`). 여기서만 보이는 것은 **진짜 브라우저 저장소로 새로고침 뒤에도 남는가**,
// 좁은 폭(412px)에서도 같은 차례로 서는가, 종이에서 빠지는가다.

test.describe('첫 화면 — 역할 단추', () => {
  test('AM. 창업자를 고르면 카드가 그 차례·펼침으로 서고, 새로고침해도 남고, 다시 누르면 지금 차례로', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    // 카드가 전부 서게 한다 — 임대·개업폐업까지 답해야 차례 전체를 견줄 수 있다(빈 카드 셋은 늘 선다).
    await mockFloorStack(
      page,
      [parcelTx()],
      priceBands(),
      [floorRow({ floor_no: 2 }), floorRow()],
      industryMix(),
      undefined,
      undefined,
      rentStats(),
    );
    // 나중에 등록한 것이 먼저 잡힌다 — mockFloorStack 의 '함수 없음' 위에 덮는다.
    await mockJson(page, OPEN_CLOSE_PATTERN, openClose());

    const NO_ROLE = [
      '속한 상권',
      '층 목록',
      '둘레의 업종 분포',
      '실거래 기록',
      '참고 매매 시세 (추정값)',
      // 세 잣대(물결 1-C2) — 참고 매매 시세 바로 뒤 · 접힌 채.
      '층 차이 세 잣대 (공표값 나란히)',
      '상권 임대 동향 (부동산원 조사)',
      '상권 개업·폐업 (서울시 공표)',
      '업종별 추정매출',
      '유동인구',
      '이 자리 가게 이력',
    ];
    // 빈 카드 셋은 창업자 차례에서 개업·폐업 바로 뒤(👤 물결 1-B).
    const FOUNDER = [
      '속한 상권',
      '층 목록',
      '둘레의 업종 분포',
      '상권 개업·폐업 (서울시 공표)',
      '업종별 추정매출',
      '유동인구',
      '이 자리 가게 이력',
      '실거래 기록',
      '참고 매매 시세 (추정값)',
      '층 차이 세 잣대 (공표값 나란히)',
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
    if (await isPhoneTabs(page)) await expect(tabButton(page, '건물')).toHaveAttribute('aria-current', 'page');
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
  test('AN. 창업자면 지도가 검색창 위·칩 여섯 · 카페 칩으로 건물을 열면 두 카드가 따르고, 투자자면 칩 없이 지금 차례', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], priceBands(), [floorRow({ floor_no: 2 }), floorRow()], industryMix());
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
    if (phone) {
      await expect(tabButton(page, '건물')).toHaveAttribute('aria-current', 'page');
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
      await gotoTab(page, '찾기');
      await expect(page.locator('section.dmap')).toHaveCount(0);
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

/** 층 함수 목업 — 물어본 `p_cat_m` 대로 갈라 답한다(대분류 줄과 칩 줄이 다른 답을 받게 · 서버처럼 그대로 되돌림). */
async function mockIndustryFloors(page: Page) {
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
      body: JSON.stringify(industryFloors(args.p_cat_l ?? 'I2', args.p_cat_m ?? null)),
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
    await mockFloorStack(page, [], priceBands(), [floorRow()], industryMix());
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
    await mockIndustryFloors(page);

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
    await mockFloorStack(page, [], [], [floorRow({ floor_no: 2 }), floorRow()]);
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

// ── 인쇄 한 장 보강 + 세 잣대 (👤 결정 0036 결정 3·8·15 · 물결 1-C2) ─────────────────────────
// 저장 규칙·칸 모양·짝짓기는 단위 시험이 덮는다(`brokerOfficeStore.test`·`unitPrint.test`·`floorGap.test`·
// `App.test`·`FloorStack.test`). 여기서만 보이는 것은 **종이**(인쇄 시험 넷 — 결정 0036 「지키는 것」)와
// 좁은 폭(412px)에서 세 잣대가 넘치지 않는가다.

test.describe('종이 한 장 보강 — 사무소 칸 · 호실 구성표 · 세 잣대', () => {
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
    await mockFloorStack(page, [], [], [floorRow({ floor_no: 2 }), floorRow()]);
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
    await mockFloorStack(page, [], [], [
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

  test('AS. 세 잣대 — 접힌 카드로 서고 펼치면 층마다 세 값 · 412px 넘침 0 · 종이에서는 줄 단위', async ({
    page,
  }, testInfo) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(
      page,
      [],
      priceBands(),
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
    await expect(gap.locator('.card__summary')).toHaveText('국세청 · 구 실거래 · 부동산원 — 층마다 나란히');
    // 자리 = 참고 매매 시세 바로 뒤(역할 없음).
    const titles = await page.locator('section.stack .card .card__title').allTextContents();
    expect(titles[titles.indexOf('층 차이 세 잣대 (공표값 나란히)') - 1]).toBe('참고 매매 시세 (추정값)');

    await openCard(page, /층 차이 세 잣대/);
    const val = (no: number, k: string) => gap.locator(`.gap__row[data-floor="${no}"] .gap__cell--${k} .gap__val`);
    await expect(val(1, 'base')).toHaveText('410만');
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
    await mockFloorStack(page, [], [], [floorRow({ floor_no: 2, ...spec }), floorRow(spec)]);
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
    await mockFloorStack(page, [], [], [6, 5, 4, 3, 2, 1].map((no) => floorRow({ floor_no: no, ...spec })));
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
    await mockFloorStack(page, [], [], [99, 5, 4, 3, 2, 1, -1].map((no) => floorRow({ floor_no: no, ...spec })));
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
    await mockFloorStack(page, [], priceBands(), [floorRow()], industryMixTwoDistricts());
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
    await mockFloorStack(page, [], priceBands(), [floorRow()], industryMixTwoDistricts());
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
  test('AY. 검색으로 연 건물 이름이 첫 화면 높이 안에 · 바 단추 44px · 펼치면 입력칸에 커서 · 접힌 지도는 종이에 없고 펼친 지도는 종이에 나온다', async ({
    page,
  }, testInfo) => {
    // 넓은 화면은 흔한 노트북 폭(1366×768)으로 잰다 · 휴대폰은 Pixel 7 프리셋 그대로(412×839).
    if (testInfo.project.name === 'chromium') await page.setViewportSize({ width: 1366, height: 768 });
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page, [], [], [floorRow({ floor_no: 2 }), floorRow()]);

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
    'label:has(input[type=radio]), label:has(input[type=checkbox]), a.links__a, a.family__a';
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
    const fs = parseFloat(getComputedStyle(el).fontSize);
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
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(
      page,
      [parcelTx()],
      priceBands(),
      [floorRow({ floor_no: 2 }), floorRow()],
      industryMix(),
      undefined,
      undefined,
      rentStats(),
    );
    await mockJson(page, OPEN_CLOSE_PATTERN, openClose());

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

  test('BA. 검색 결과를 내려 아래쪽 건물을 고르면 위 칸이 접히며 화면이 맨 위로 — 바와 건물 이름이 화면 안', async ({
    page,
  }) => {
    await mockOpenSigungu(page);
    const hits = Array.from({ length: 12 }, (_, i) =>
      searchHit({ bld_id: `1168010100100${String(i + 10).padStart(2, '0')}0000_1`, bld_nm: `결과빌딩${i + 1}` }),
    );
    await mockJson(page, SEARCH_PATTERN, hits);
    await mockFloorStack(page, [], [], [floorRow({ floor_no: 2 }), floorRow()]);

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
    // 휴대폰(W4a)은 바 대신 아래 탭 막대(늘 화면 안 · 고른 탭 = 건물).
    await expect(page.locator(phone ? 'nav.tabbar' : '.entrybar')).toBeInViewport();
    const title = (await head.getByRole('heading').first().boundingBox())!;
    expect(title.y).toBeGreaterThanOrEqual(0);
    expect(title.y + title.height).toBeLessThanOrEqual(vh);
    // 커서는 바의 첫 단추(고른 결과 줄이 숨어 커서가 문서 맨 앞으로 날아가지 않게) · 휴대폰은 고른 탭(건물).
    if (phone) await expect(tabButton(page, '건물')).toBeFocused();
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
      // 지분 거래는 숨는 12번째 줄에만 — 접힌 화면엔 설명 줄이 없고 펼치거나 종이면 선다(👤 2026-10-16).
      Array.from({ length: 12 }, (_, i) => parcelTx({ is_share: i === 11 })),
      [],
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

    // 지분은 숨은 12번째 줄에만 — 접힌 화면엔 설명 줄이 안 보인다(줄은 DOM 에 있다 · 종이용).
    const shareNote = page.locator('section.tx .tx__share-note');
    await expect(shareNote).toHaveCount(1);
    await expect(shareNote).toBeHidden();

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
    await expect(shareNote).toBeHidden();

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
      [],
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

// ── 그림 (결정 0038 V1 — E ▲ 눈금·층 묶음 쌓은 막대 · A 참고 시세 띠) ─────────────────────
// 값 → 자리·폭 계산은 단위 시험(`viz.test.ts`·`industryMix.test.ts`·`priceBand.test.ts`)이, 서는 경우/안 서는 경우는 컴포넌트 시험이 덮는다.
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
    await mockFloorStack(page, [], priceBands(), [floorRow()], industryMixTwoDistricts());
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

test.describe('그림 — 참고 매매 시세 (결정 0038 A)', () => {
  test('BE. 값 나는 층마다 p25~p75 띠 + 가운데값 눈금(축 0 ~ ㎡당 2,000만) · 먼 근거 연한 띠 · 1층 "–" · 넓은 화면은 글 왼쪽 · 휴대폰은 글 위 · 종이에도 그대로', async ({
    page,
  }, testInfo) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    // 2층 = 먼 근거(L5 · p25 746.5만 · 가운데 1,626.5만 · p75 1,904.6만) · 3층 = 이 땅 같은 층(L2 · 900만~1,500만 · 가운데 1,200만) · 1층 = 내지 않음.
    const bands = [
      ...priceBands(),
      { ...priceBands()[2], floor_no: 3, stage: 'L2', n: 8, p25: 9_000_000, median: 12_000_000, p75: 15_000_000 },
    ];
    await mockFloorStack(page, [], bands, [
      floorRow({ floor_no: 3 }),
      floorRow({ floor_no: 2 }),
      floorRow(),
      floorRow({ floor_no: -1 }),
    ]);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    const card = page.locator('section.band');
    await openCard(page, /참고 매매 시세/);
    const row = (label: string) => card.locator('.band__row').filter({ has: page.locator('.band__floor', { hasText: new RegExp(`^${label}$`) }) });
    await expect(card.locator('.band__row')).toHaveCount(3);

    const mobile = testInfo.project.name === 'mobile';
    const [estBand, estFar, estInk, estChip] = await Promise.all(
      ['--est-band', '--est-line', '--est-ink', '--est-chip'].map((n) => tokenRgb(page, n)),
    );

    const check = async () => {
      // ② 띠 자리 = 픽스처 사분위 ÷ 상한 2,000만.
      const r2 = row('2층');
      const t2 = r2.locator('.band__track');
      expect(await pctIn(r2.locator('.band__range'), t2, 'left')).toBeCloseTo((7_465_269.63 / 20_000_000) * 100, 0);
      const w2 = ((await r2.locator('.band__range').boundingBox())!.width / (await t2.boundingBox())!.width) * 100;
      expect(w2).toBeCloseTo(((19_045_698.84 - 7_465_269.63) / 20_000_000) * 100, 0);
      expect(await pctIn(r2.locator('.band__tick'), t2)).toBeCloseTo((16_265_452.18 / 20_000_000) * 100, 0);
      const r3 = row('3층');
      const t3 = r3.locator('.band__track');
      expect(await pctIn(r3.locator('.band__range'), t3, 'left')).toBeCloseTo(45, 0);
      expect(((await r3.locator('.band__range').boundingBox())!.width / (await t3.boundingBox())!.width) * 100).toBeCloseTo(30, 0);
      expect(await pctIn(r3.locator('.band__tick'), t3)).toBeCloseTo(60, 0);
      // ④ 색 — 추정 회청 · 먼 근거(2층)는 연한 띠 · 가까운 근거(3층)는 진한 띠 · 눈금 잉크 · 바탕 칩.
      const bg = (l: ReturnType<Page['locator']>) => l.evaluate((e) => e.ownerDocument.defaultView!.getComputedStyle(e).backgroundColor);
      expect(await bg(r2.locator('.band__range'))).toBe(estFar);
      expect(await bg(r3.locator('.band__range'))).toBe(estBand);
      expect(await bg(r2.locator('.band__tick'))).toBe(estInk);
      expect(await bg(t2)).toBe(estChip);
      // 1층은 띠 없이 "–" · 까닭 글은 그대로.
      const r1 = row('1층');
      await expect(r1.locator('.band__range, .band__tick')).toHaveCount(0);
      await expect(r1.locator('.band__viz')).toHaveText('–');
      await expect(r1.locator('.band__none')).toContainText('1층은 내지 않습니다');
      // A2 눈금 글 — 띠 목록 바로 아래 한 줄 · 왼쪽 끝 = 띠 칸 왼쪽 · 오른쪽 끝 = 띠 칸 오른쪽.
      const axis = card.locator('.band__axis');
      await expect(axis).toHaveText('0㎡당 2,000만');
      const sc = (await axis.locator('.band__axis-scale').boundingBox())!;
      const tb = (await t2.boundingBox())!;
      expect(Math.abs(sc.x - tb.x)).toBeLessThan(1.5);
      expect(Math.abs(sc.x + sc.width - (tb.x + tb.width))).toBeLessThan(1.5);
    };
    await check();

    // A3 배치 — 넓은 화면은 띠가 글 왼쪽(같은 줄) · 휴대폰은 층 이름 / 띠 / 글 차례로 위아래.
    const vb = (await row('2층').locator('.band__viz').boundingBox())!;
    const xb = (await row('2층').locator('.band__text').boundingBox())!;
    const fb = (await row('2층').locator('.band__floor').boundingBox())!;
    if (mobile) {
      expect(vb.y).toBeGreaterThanOrEqual(fb.y + fb.height - 0.5);
      expect(xb.y).toBeGreaterThanOrEqual(vb.y + vb.height - 0.5);
      expect(vb.width).toBeGreaterThan((await row('2층').boundingBox())!.width * 0.8);
    } else {
      expect(vb.x + vb.width).toBeLessThanOrEqual(xb.x);
      expect(vb.x).toBeGreaterThanOrEqual(fb.x + fb.width);
      expect(Math.abs(vb.y + vb.height / 2 - (xb.y + xb.height / 2))).toBeLessThan(xb.height / 2);
    }
    // 글은 그대로.
    await expect(row('2층').locator('.band__val')).toHaveText('비슷한 호실 한 칸 32.8㎡ (10평) 기준 2.4억~6.2억');
    expect(await page.locator('html').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    for (const el of await card.locator('.band__hit, .band__axis').all()) {
      expect(await el.evaluate((e) => e.scrollWidth - e.clientWidth)).toBeLessThanOrEqual(0);
    }
    await card.screenshot({ path: testInfo.outputPath(`be-band-${testInfo.project.name}.png`) });

    // ⑤ 종이 — 같은 띠 · 같은 자리 · 같은 색(`print-color-adjust: exact`).
    await page.emulateMedia({ media: 'print' });
    await expect(row('2층').locator('.band__range')).toBeVisible();
    await check();
    expect(await row('2층').locator('.band__range').evaluate((e) => e.ownerDocument.defaultView!.getComputedStyle(e).printColorAdjust)).toBe('exact');
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
      priceBands(),
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

    // ② 투자자 — 판이 건물 머리 **앞**(같은 부모) · 시세 타일은 C등급 추정 색 · 임대 타일은 「상권 평균」.
    await openWithRole(page, '투자자');
    const sum = page.locator('section.stack > .rsum');
    await expect(sum).toBeVisible();
    await expect(sum.locator('.rsum__question')).toHaveText('얼마고 얼마 벌리나');
    await expect(sum.locator('.rsum__tile--rent')).toContainText('상권 평균');
    await expect(sum.locator('.rsum__tile--band .grade__badge--est')).toHaveText('C등급 · 파생 추정');
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

  test('BH. 빈 저장소로 `/` 를 열면 입구 맨 위에 큰 카드(작은 줄 숨김) · 휴대폰은 세로 쌓기·카드 56px·둘러보기 44px · 넓은 화면은 한 줄 · 종이에 없음 · 카드를 누르면 사라지고 그 역할 화면', { tag: '@first-visit' }, async ({ page }, testInfo) => {
    await mockOpenSigungu(page);
    await page.goto('/');
    const box = page.locator('section.rolecards');
    await expect(box).toBeVisible();
    await expect(box.getByText('무엇을 하러 오셨나요?')).toBeVisible();
    await expect(page.locator('section.role')).toHaveCount(0);
    // 덮개가 아니다 — 지역 고르기가 카드 **아래**에 그대로 보인다.
    const region = page.getByRole('button', { name: /^서울$/ });
    await expect(region).toBeVisible();
    expect((await region.boundingBox())!.y).toBeGreaterThan((await box.boundingBox())!.y);

    const cards = box.locator('.rolecards__card');
    await expect(cards).toHaveCount(3);
    const rects = await Promise.all([0, 1, 2].map(async (i) => (await cards.nth(i).boundingBox())!));
    for (const r of rects) expect(r.height).toBeGreaterThanOrEqual(56);
    if (testInfo.project.name === 'mobile') {
      // 세로로 쌓기 — 왼쪽 끝이 같고 위에서 아래로.
      expect(rects[1].y).toBeGreaterThanOrEqual(rects[0].y + rects[0].height);
      expect(rects[2].y).toBeGreaterThanOrEqual(rects[1].y + rects[1].height);
      expect(Math.abs(rects[1].x - rects[0].x)).toBeLessThanOrEqual(1);
    } else {
      // 넓은 화면 = 한 줄에 셋.
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

  test('BJ. 건물 직행 링크(`bld`)에서는 안 뜨고 저장도 안 한다 · `?sgg=` 만 든 링크에서는 뜬다', { tag: '@first-visit' }, async ({ page }) => {
    await mockOpenSigungu(page);
    await mockFloorStack(page, [], [], [floorRow({ floor_no: 2 }), floorRow()]);
    await page.goto(`/?sgg=11680&bld=${LINK_BLD}`);
    await expect(page.locator('section.stack').getByRole('heading', { name: '테스트빌딩' })).toBeVisible();
    if (await isPhoneTabs(page)) await expect(tabButton(page, '건물')).toHaveAttribute('aria-current', 'page');
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
    await mockFloorStack(page, [], [], [floorRow({ floor_no: 2 }), floorRow()]);
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
    // 지도 탭 = 지역 고르개(같은 하나) · 검색 없음.
    await gotoTab(page, '지도');
    await expect(page.locator('section.region')).toBeVisible();
    await expect(page.locator('section.search')).toBeHidden();
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
    await mockFloorStack(page, [], [], [floorRow({ floor_no: 2 }), floorRow()]);
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
    await expect(page.locator('section.dmap')).toHaveCount(0);
  });

  test('BN. 뒤로가기 — 건물을 열 때만 한 칸(여럿 열어도 한 칸) · 뒤로 = 아까 탭(건물은 남음) · 앞으로 = 건물 · 넓은 화면은 칸 0', async ({
    page,
  }, testInfo) => {
    await mockOpenSigungu(page);
    // ⚠️ 둘째 건물 번호도 진짜 꼴(19자리_숫자)로 — 주소 쓰기는 꼴이 틀린 번호를 버린다(`urlState.ts` 의 BLD_RE).
    const OTHER = '1168010100100020000_2';
    await mockJson(page, SEARCH_PATTERN, [searchHit(), searchHit({ bld_id: OTHER, bld_nm: '다른빌딩' })]);
    await mockFloorStack(page, [], [], [floorRow({ floor_no: 2 }), floorRow()]);
    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');
    const len = () => page.evaluate(() => (globalThis as unknown as { history: { length: number } }).history.length);
    const before = await len();
    await page.getByRole('button', { name: /테스트빌딩/ }).click();
    await expect(page.locator('section.stack .stack__head')).toBeVisible();
    if (testInfo.project.name !== 'mobile') {
      expect(await len()).toBe(before); // 넓은 화면은 지금처럼 replaceState 만
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
});
