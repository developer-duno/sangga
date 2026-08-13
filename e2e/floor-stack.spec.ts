import { test, expect, type Page } from '@playwright/test';
import { searchHit, floorRow, coverageStats } from './fixtures';

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

async function mockFloorStack(page: Page) {
  await mockJson(page, STATS_PATTERN, [coverageStats()]);
  await mockJson(page, FLOOR_PATTERN, [floorRow()]);
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

async function search(page: Page, text: string) {
  await page.getByLabel('건물명 또는 주소').fill(text);
  await page.getByRole('button', { name: '검색' }).click();
}

test.describe('층별 스택뷰 — 검색부터 렌더까지', () => {
  test('A. 검색 → 결과 클릭 → 층 스택 렌더', async ({ page }) => {
    await mockOpenSigungu(page);
    await mockJson(page, SEARCH_PATTERN, [searchHit()]);
    await mockFloorStack(page);

    await page.goto('/');
    await pickGu(page, '서울', '강남구');
    await search(page, '테헤란로');

    const hitBtn = page.getByRole('button', { name: /테스트빌딩/ });
    await expect(hitBtn).toBeVisible();
    await hitBtn.click();

    const stack = page.locator('section.stack');
    await expect(stack.getByRole('heading', { name: '테스트빌딩' })).toBeVisible();
    await expect(stack.getByText('서울 강남구 테헤란로 1')).toBeVisible();
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

    await expect(page.getByText('결과가 없습니다')).toBeVisible();
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
});
