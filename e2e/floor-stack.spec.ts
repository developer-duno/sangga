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
// 둘레의 업종 분포(결정 0014). 층 스택이 건물마다 이 둘을 더 부른다.
// ⚠️ **일부러 404(PGRST202)로 답한다** — 마이그레이션을 적용하기 전 라이브가 바로 그
//    상태이고, 그때 이 섹션이 **조용히 사라지는지**가 여기서 확인하려는 것이다.
//    (안 막으면 실존하지 않는 도메인으로 요청이 나가 테스트가 DNS 에 좌우된다.)
const INDUSTRY_MIX_PATTERN = '**/rest/v1/rpc/list_industry_mix*';
const INDUSTRY_DETAIL_PATTERN = '**/rest/v1/rpc/list_industry_detail*';
// 의견함(2026-08-24b). 화면에서 창고로 **나가는** 유일한 길이라, 여기만 방향이 반대다.
const FEEDBACK_PATTERN = '**/rest/v1/rpc/submit_feedback*';

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

    await search(page, '다른동');

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

    await search(page, '없는건물');

    // ⚠️ 구 단위 검색으로 바뀐 뒤 문구도 바뀌었다 — "지금 보실 수 있는 지역은 …"이 아니라
    //    **고른 구 안에서** 못 찾았다고 말한다(2026-08-13 2차 검증에서 정리).
    // ⚠️ '강남구'는 지역 칩에도 있으므로 **문구 안에서** 찾아야 한다(그냥 getByText 는 모호).
    await expect(page.getByText(/강남구에서 찾지 못했습니다/)).toBeVisible();
    await expect(page.locator('section.stack')).toHaveCount(0);
  });

  // ── 너무 넓은 검색 안내창 (2026-08-13) ──────────────────────────────────
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

  test('E. 너무 넓은 검색이면 걸린 곳 수와 무엇을 넣을지 알려준다', async ({ page }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, []);
    await mockJson(page, SCOPE_PATTERN, [{ too_broad: true, match_cnt: 163487 }]);
    await mockFloorStack(page);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '서울');

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText('163,487곳')).toBeVisible();
    await expect(dialog.getByText('역삼동 823-4')).toBeVisible();
    // "결과가 없습니다"와 겹쳐 뜨면 두 말이 동시에 보인다.
    await expect(page.getByText('결과가 없습니다')).toHaveCount(0);

    await dialog.getByRole('button', { name: '닫기' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
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
    await expect(stack.getByText(/A등급 · 실거래/)).toBeVisible();
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
    // 1층은 자리를 몰라서, 지하는 검증한 적이 없어서 — 서로 다른 말로 적는다.
    await expect(band.getByText(/1층은 내지 않습니다/)).toBeVisible();
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
    await expect(page.getByText('실거래 기록')).toBeVisible();
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
    await expect(stack.locator('.card')).toHaveCount(5);
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
  test('M. 아래 안내가 보이고, 의견을 보내면 보던 지역이 함께 간다', async ({ page }) => {
    await mockOpenSigungu(page);

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

    // 건물을 고르지 않아도 아래 안내는 늘 보인다 — 다 보고 난 사람이 찾는 자리다.
    const foot = page.locator('footer.foot');
    await expect(foot.getByText(/감정평가가 아니며/)).toBeVisible();
    await expect(foot.getByText(/"미상"/)).toBeVisible();

    // 보던 지역이 함께 실리는지 보려고 구를 하나 고른다.
    await pickGu(page, '서울', '강남구');

    await foot.getByRole('button', { name: '의견 보내기' }).click();
    // 답장을 못 한다는 사실을 **미리** 말한다 — 기다리게 해 놓고 안 하는 것이 가장 나쁘다.
    await expect(foot.getByText(/답장을 드릴 수 없습니다/)).toBeVisible();

    await foot.getByRole('textbox').fill('3층 정보가 안 보여요');
    await foot.getByRole('button', { name: '보내기' }).click();

    await expect(foot.getByText(/고맙습니다/)).toBeVisible();

    expect(sent).toHaveLength(1);
    expect(sent[0].p_kind).toBe('opinion');
    expect(sent[0].p_body).toBe('3층 정보가 안 보여요');
    // ⛔ 여기가 이 의견함의 값어치 전부다 — 사람이 손으로 안 적어도 어디를 보던 중이었는지가
    //    함께 간다. 이 줄이 깨지면 남는 것은 맥락 없는 한 줄짜리 불평뿐이다.
    expect((sent[0].p_context as Record<string, unknown>).sigungu).toBe('11680');
  });

  test('N. 못 보냈으면 못 보냈다고 말한다 — 거짓 안심을 만들지 않는다', async ({ page }) => {
    await mockOpenSigungu(page);
    // 마이그레이션 적용 전 라이브가 정확히 이 상태다(함수가 아직 없다).
    await mockMissingFunction(page, FEEDBACK_PATTERN);

    await page.goto('/');
    const foot = page.locator('footer.foot');
    await foot.getByRole('button', { name: '의견 보내기' }).click();
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
    await expect(page.getByRole('heading', { name: /강남구 상권 지도/ })).toBeVisible();
    // 가지고 나가는 버튼도 함께 선다.
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

    await page.emulateMedia({ media: 'print' });

    // ① 종이에서 누를 수 없는 것은 종이에 없다.
    //    (규칙 없이 뽑으면 첫 장 위 절반이 검색창·구 칩·버튼이었다 — 2026-08-25 실측)
    await expect(page.locator('.region')).toBeHidden();
    await expect(page.locator('.search')).toBeHidden();
    await expect(page.locator('.takeout')).toBeHidden();
    await expect(page.locator('.fb')).toBeHidden();
    await expect(page.locator('.dmap__toggle')).toBeHidden();
    await expect(page.locator('.card__caret').first()).toBeHidden();

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
});
