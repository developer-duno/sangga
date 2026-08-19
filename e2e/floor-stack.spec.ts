import { test, expect, type Page } from '@playwright/test';
import {
  searchHit,
  floorRow,
  coverageStats,
  parcelTx,
  sigunguTxStats,
  priceBands,
  priceBandGate,
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

async function mockFloorStack(
  page: Page,
  txs: unknown[] = [],
  bands: unknown[] = [],
  floors?: unknown[],
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
    await expect(stack.getByText('속한 상권:')).toBeVisible();
    await expect(stack.getByText(/역삼역\(발달상권\)/)).toBeVisible();
    // 출처표시는 공공누리 1유형 의무다 — 상권 이름이 보이는데 출처만 빠지는 것도 결함이다.
    await expect(stack.getByText(/출처: 서울특별시 상권분석서비스/)).toBeVisible();
    // 참고 시세 섹션도 같은 종류의 위험을 진다(별도 RPC 하나에 통째로 달려 있다).
    await expect(stack.locator('section.band')).toBeVisible();
    await expect(stack.getByText(/C등급 · 파생 추정/)).toBeVisible();
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
    await expect(band.locator('.band__row')).toHaveCount(0);
    await expect(band.getByText(/구 전체는 아직 참고 시세를 내지 않습니다/)).toBeVisible();
    // 오차율·구 개수는 서버가 정본이라 화면에 복사하지 않는다(결정 0013 §4).
    await expect(band.locator('.band__gate')).not.toContainText('%');
    // 층 목록과 실거래 기록은 그대로 나온다 — 밴드만 없는 것이다.
    await expect(page.locator('.floors .floor')).toHaveCount(1);
    await expect(page.getByText('실거래 기록')).toBeVisible();
  });
});
