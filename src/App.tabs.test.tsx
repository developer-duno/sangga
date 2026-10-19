import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act, within } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import type { BuildingHit, FloorRow, OpenSigungu } from './types';
import { PHONE_QUERY } from './lib/useIsPhone';

/**
 * 휴대폰 아래 탭(결정 0039 Q1 · W4a) — App 의 배선을 본다. jsdom 에는 `matchMedia` 가 없어 다른 App 시험은 전부 넓은 화면이다 —
 * 여기서만 흉내 `matchMedia` 로 휴대폰 꼴을 켠다. 지도 알맹이(카카오)는 가짜(`App.mapPick.test.tsx` 와 같은 꼴).
 * ⓘ 탭에 안 맞는 덩어리를 숨기는 것은 CSS(720 화면 묶음)라 jsdom 은 눈으로 못 본다 — 그건 E2E(BK~BP)가 본다. 여기서는
 *   탭 표시·`hidden`·그릴지 말지·뒤로가기 칸·CSS 규칙 자리를 본다.
 */

const rpc = vi.fn();
const from = vi.fn();

function makeQuery(result: { data: unknown; error: unknown }) {
  const q: Record<string, unknown> = {};
  for (const m of ['select', 'eq', 'order', 'limit']) q[m] = () => q;
  q.then = (cb: (r: unknown) => unknown) => Promise.resolve(result).then(cb);
  return q;
}

vi.mock('./lib/supabase', () => ({
  supabase: {
    rpc: (...args: unknown[]) => rpc(...args),
    from: (view: string) => from(view),
  },
}));

// ⓘ 가짜 지도도 진짜처럼 `visible` 이 거짓이면 `hidden` 으로 숨기기만 하고(W4b) 받은 꼴(`layout`)을 적어 둔다.
vi.mock('./components/DistrictMap', () => ({
  DistrictMap: ({
    sigungu,
    visible = true,
    layout = 'card',
  }: {
    sigungu: string | null;
    visible?: boolean;
    layout?: 'card' | 'full';
  }) =>
    sigungu ? (
      <section className="dmap" hidden={!visible} data-layout={layout}>
        가짜 지도
      </section>
    ) : null,
}));

const { default: App } = await import('./App');

const BLD = '1168010100100010000_1024110';

function gu(over: Partial<OpenSigungu> = {}): OpenSigungu {
  return { sido_code: '11', sido_nm: '서울', sigungu_code: '11680', sigungu_nm: '강남구', building_cnt: 1, ...over };
}

function hit(over: Partial<BuildingHit> = {}): BuildingHit {
  return {
    bld_id: BLD,
    pnu: '1168010100100010000',
    bld_nm: '테스트빌딩',
    road_addr: '서울 강남구 테헤란로 1',
    bld_cnt_in_pnu: 1,
    floor_cnt: 1,
    min_floor: 1,
    max_floor: 1,
    has_roof: false,
    total_cnt: 1,
    ...over,
  };
}

function floorRow(bldId = BLD, name = '테스트빌딩'): FloorRow {
  return {
    bld_id: bldId,
    pnu: '1168010100100010000',
    floor_no: 1,
    floor_label: null,
    floor_area_m2: 100,
    floor_area_gross_m2: 110,
    segment_cnt: 1,
    main_use: '소매점',
    uses: [],
    bld_nm: name,
    approve_date: '2003-05-14',
    is_jiphap: true,
    road_addr: '서울 강남구 테헤란로 1',
    road_contact: null,
    bld_cnt_in_pnu: 1,
    store_cnt: 1,
    stores: [],
    total_area_m2: 1234.5,
    far: 350.5,
    bcr: 59.9,
    parking_cnt: 12,
  };
}

/** 흉내 `matchMedia` — 휴대폰 폭이면 `PHONE_QUERY` 가 참. 인쇄는 늘 거짓. */
function phoneMedia() {
  window.matchMedia = ((q: string) => ({
    media: q,
    matches: q === PHONE_QUERY,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  window.history.replaceState(null, '', '/');
  window.localStorage.setItem('sangga.viewerRole', '둘러보기');
  rpc.mockReset();
  from.mockReset();
  from.mockImplementation((view: string) =>
    makeQuery(view === 'v_coverage_stats' ? { data: [], error: null } : { data: [floorRow()], error: null }),
  );
  rpc.mockImplementation((fn: string) => {
    if (fn === 'list_open_sigungu') return Promise.resolve({ data: [gu()], error: null });
    if (fn === 'search_buildings')
      return Promise.resolve({ data: [hit(), hit({ bld_id: `${BLD}9`, bld_nm: '둘째빌딩' })], error: null });
    return Promise.resolve({ data: [], error: null });
  });
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  delete (window as { matchMedia?: unknown }).matchMedia;
  vi.restoreAllMocks();
});

const bar = () => screen.queryByRole('navigation', { name: '화면 고르기' });
const tabNames = () => within(bar()!).getAllByRole('button').map((b) => b.textContent);
const current = () => within(bar()!).getByRole('button', { current: 'page' }).textContent;
const tab = (name: string) => within(bar()!).getByRole('button', { name });
const entry = () => document.getElementById('entry-panel')!;

async function pickGu() {
  fireEvent.click(await screen.findByRole('button', { name: /^서울$/ }));
  fireEvent.click(await screen.findByRole('button', { name: /^강남구/ }));
}

async function searchAndOpen(name: RegExp = /테스트빌딩/) {
  const input = screen.getByLabelText('건물명 또는 주소');
  fireEvent.change(input, { target: { value: '테헤란로' } });
  fireEvent.submit(input.closest('form')!);
  fireEvent.click(await screen.findByRole('button', { name }));
}

describe('휴대폰 아래 탭 (결정 0039 W4a)', () => {
  it('★ 넓은 화면(matchMedia 없음)은 지금 그대로 — 탭 0 · 바로 접힘 · 뒤로가기 칸 0 · 이름표 0', async () => {
    const { container } = render(<App />);
    await pickGu();
    const before = window.history.length;
    await searchAndOpen();
    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(bar()).toBeNull();
    expect(container.querySelector('.entrybar')).not.toBeNull();
    const app = container.querySelector('.app')!;
    expect(app.classList.contains('app--tabs')).toBe(false);
    expect(app.hasAttribute('data-tab')).toBe(false);
    expect(window.history.length).toBe(before);
    expect(window.history.state).toBeNull();
    // 꼬리말 차례 그대로(안내가 맨 앞 · 의견함은 맨 뒤).
    const foot = container.querySelector('footer.foot')!;
    expect(foot.firstElementChild?.classList.contains('foot__notice')).toBe(true);
    expect(foot.lastElementChild?.classList.contains('fb')).toBe(true);
    // W4b — 띠·지도 가득·홈 화면 안내는 넓은 화면 DOM 0 · 지도는 카드 꼴에 숨김 속성 없음 · 지역 고르개 id 없음.
    expect(container.querySelector('.rstrip')).toBeNull();
    expect(container.querySelector('.hshint')).toBeNull();
    expect(app.classList.contains('app--mapfull')).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: /상권 지도 보기/ }));
    const map = container.querySelector('section.dmap')!;
    expect(map.getAttribute('data-layout')).toBe('card');
    expect(map.hasAttribute('hidden')).toBe(false);
    expect(container.querySelector('section.region')!.hasAttribute('id')).toBe(false);
  });

  it('★ 휴대폰 — 탭 넷 · 첫 탭 찾기 · 빈 건물 탭(흐림 · 안내 · 찾으러 가기) · 바·안내 줄 없음', async () => {
    phoneMedia();
    const { container } = render(<App />);
    expect(tabNames()).toEqual(['찾기', '지도', '건물', '더보기']);
    expect(current()).toBe('찾기');
    expect(tab('건물').classList.contains('tabbar__btn--dim')).toBe(true);
    expect(container.querySelector('.app')!.getAttribute('data-tab')).toBe('find');
    expect(screen.queryByText('위에서 건물을 검색해 선택해 주세요.')).toBeNull();

    fireEvent.click(tab('건물'));
    expect(current()).toBe('건물');
    expect(entry().hidden).toBe(true);
    expect(screen.getByText('아직 고른 건물이 없습니다')).toBeTruthy();
    expect(screen.getByText('찾기나 지도에서 건물을 고르면 여기에 층별 화면이 섭니다')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '건물 찾으러 가기' }));
    expect(current()).toBe('찾기');
    expect(entry().hidden).toBe(false);
    expect(container.querySelector('.entrybar')).toBeNull();
  });

  it('★ 휴대폰 — 건물을 열면 건물 탭 + 뒤로가기 한 칸(여럿 열어도 한 칸) · 검색해도 건물이 남는다 · 뒤로 = 아까 탭', async () => {
    phoneMedia();
    const { container } = render(<App />);
    await pickGu();
    const before = window.history.length;
    await searchAndOpen();
    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(current()).toBe('건물');
    expect(tab('건물').classList.contains('tabbar__btn--dim')).toBe(false);
    expect(entry().hidden).toBe(true);
    expect(container.querySelector('.entrybar')).toBeNull();
    expect(window.history.length).toBe(before + 1);
    expect(window.history.state).toEqual({ sanggaTab: 'bld' });
    expect(window.location.search).toContain(`bld=${BLD}`);

    // 찾기 탭에서 새로 검색해도 보던 건물은 남는다(§7-1).
    fireEvent.click(tab('찾기'));
    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '둘째' } });
    fireEvent.submit(input.closest('form')!);
    await screen.findByRole('button', { name: /둘째빌딩/ });
    expect(container.querySelector('section.stack')).not.toBeNull();

    // 둘째 건물을 열어도 칸은 더 안 쌓인다.
    from.mockImplementation((view: string) =>
      makeQuery(view === 'v_coverage_stats' ? { data: [], error: null } : { data: [floorRow(`${BLD}9`, '둘째빌딩')], error: null }),
    );
    fireEvent.click(screen.getByRole('button', { name: /둘째빌딩/ }));
    await screen.findByRole('heading', { name: '둘째빌딩' });
    expect(current()).toBe('건물');
    expect(window.history.length).toBe(before + 1);

    // 뒤로(앞 칸 = base) → 열기 직전 탭(찾기) · 건물은 그대로 · 주소는 지금 건물로 다시 적힌다.
    window.history.replaceState({ sanggaTab: 'base' }, '', '/?sgg=11680');
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate', { state: { sanggaTab: 'base' } }));
    });
    expect(current()).toBe('찾기');
    expect(container.querySelector('section.stack')).not.toBeNull();
    expect(window.location.search).toContain(`bld=${BLD}9`);
    expect(window.history.state).toEqual({ sanggaTab: 'base' });
    // 앞으로(bld 칸) → 건물 탭.
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate', { state: { sanggaTab: 'bld' } }));
    });
    expect(current()).toBe('건물');
    // 우리 표식이 없는 칸이면 아무것도 안 바꾼다(양성 대조의 반대편).
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate', { state: null }));
    });
    expect(current()).toBe('건물');
  });

  it('★ 휴대폰 창업자 — 첫 탭 지도 · 지역 고르개가 지도 탭에도 · 지도는 지도 탭에서만 그린다', async () => {
    phoneMedia();
    window.localStorage.setItem('sangga.viewerRole', '창업자');
    const { container } = render(<App />);
    expect(current()).toBe('지도');
    expect(entry().hidden).toBe(false);
    await pickGu(); // 지도 탭에 선 지역 고르개로
    const map = container.querySelector<HTMLElement>('.dmap')!;
    expect(map).not.toBeNull();
    // W4b(결정 0039 §4-11) — 탭을 옮겨도 지도를 다시 그리지 않는다: 같은 노드가 숨기만 했다가 돌아오면 다시 보인다(relayout 은 DistrictMap 시험).
    fireEvent.click(tab('찾기'));
    expect(container.querySelector('.dmap')).toBe(map);
    expect(map.hidden).toBe(true);
    fireEvent.click(tab('더보기'));
    expect(entry().hidden).toBe(true);
    fireEvent.click(tab('지도'));
    expect(container.querySelector('.dmap')).toBe(map);
    expect(map.hidden).toBe(false);
  });

  it('★ 휴대폰 중개사 — 탭 = 찾기·건물·뽑은 건물·더보기 · 지도는 찾기 탭 · 빈 「뽑은 건물」 안내 · 목록은 펼친 채', async () => {
    phoneMedia();
    window.localStorage.setItem('sangga.viewerRole', '중개사');
    const { container, unmount } = render(<App />);
    expect(tabNames()).toEqual(['찾기', '건물', '뽑은 건물', '더보기']);
    await pickGu();
    expect(container.querySelector('.dmap')).not.toBeNull();
    fireEvent.click(tab('뽑은 건물'));
    expect(screen.getByText('아직 뽑은 건물이 없습니다')).toBeTruthy();
    expect(screen.getByText('건물 화면에서 「인쇄 · PDF로 저장」을 누르면 여기에 남습니다')).toBeTruthy();
    unmount();

    const { total_cnt: _t, ...saved } = hit({ bld_nm: '뽑은빌딩' });
    void _t;
    window.localStorage.setItem('sangga.recentPrinted', JSON.stringify([saved]));
    const second = render(<App />);
    // 찾기 탭 검색 아래에는 없다(넓은 화면 자리) — 탭 안에서 펼친 채(접는 단추 없이 줄이 바로).
    expect(second.container.querySelector('.search .recent')).toBeNull();
    fireEvent.click(tab('뽑은 건물'));
    expect(screen.queryByRole('button', { name: /최근 뽑은 건물/ })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /뽑은빌딩/ }));
    expect(current()).toBe('건물');
    await screen.findByRole('heading', { name: '테스트빌딩' }); // 층 행의 이름(가짜 층 응답)
  });

  it('★ 휴대폰 건물 직행 링크 — 첫 탭 건물(되살리는 동안 안내도 건물 탭)', async () => {
    phoneMedia();
    window.history.replaceState(null, '', `/?sgg=11680&bld=${BLD}`);
    render(<App />);
    expect(current()).toBe('건물');
    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(current()).toBe('건물');
    // 링크로 온 방문은 칸을 쌓지 않는다(뒤로 = 사이트를 나감).
    expect(window.history.state).toBeNull();
  });

  it('★ 휴대폰 더보기 — 역할 줄이 꼬리말 맨 앞 · 의견함이 안내 앞 · 입구엔 역할 줄 없음 · 역할을 바꿔 탭이 사라지면 찾기', async () => {
    phoneMedia();
    window.localStorage.setItem('sangga.viewerRole', '투자자');
    const { container } = render(<App />);
    expect(entry().querySelector('.role')).toBeNull();
    const foot = container.querySelector('footer.foot')!;
    expect(foot.firstElementChild?.classList.contains('role')).toBe(true);
    // 눈 차례(의견함이 안내 앞)는 CSS order(`.foot--phone` · 아래 CSS 시험) — 의견함 DOM 자리는 넓은 화면과 같은 맨 뒤(F8).
    expect(foot.classList.contains('foot--phone')).toBe(true);
    expect(foot.lastElementChild?.classList.contains('fb')).toBe(true);

    fireEvent.click(tab('지도'));
    fireEvent.click(tab('더보기'));
    fireEvent.click(tab('지도'));
    expect(current()).toBe('지도');
    // 지도 탭에 있다가(더보기의 역할 줄로) 중개사가 되면 지도 탭이 없어 찾기로.
    fireEvent.click(within(foot as HTMLElement).getByRole('button', { name: '중개사' }));
    expect(current()).toBe('찾기');
    expect(tabNames()).toEqual(['찾기', '건물', '뽑은 건물', '더보기']);
  });

  it('★ 휴대폰 첫 방문(저장값 없음) — 큰 카드는 찾기 탭 입구 맨 위 그대로 · 더보기엔 작은 줄 없음', async () => {
    phoneMedia();
    window.localStorage.clear();
    const { container } = render(<App />);
    expect(entry().querySelector('.rolecards')).not.toBeNull();
    expect(container.querySelector('footer.foot .role')).toBeNull();
  });

  it('★ 휴대폰 — 건물을 연 채 찾기 탭에도 입구 카드 셋이 선다(넓은 화면은 지금처럼 건물을 열면 물러남 · 검사 🟠 F2)', async () => {
    phoneMedia();
    // 입구 카드가 실제로 서게 단가 흐름 한 줄을 준다(빈 답이면 카드가 안 선다 — 양성 대조가 비지 않게).
    const flowRow = {
      yr: '2015', n: 12, n_all: 14, median_unit_price: 1000, p25_unit_price: 800, p75_unit_price: 1200,
      median_area_m2: 50, floor_missing: 1, ym_cnt: 12, first_ym: '201501', last_ym: '201512',
    };
    const baseRpc = rpc.getMockImplementation()!;
    rpc.mockImplementation((fn: string, ...rest: unknown[]) =>
      fn === 'get_sigungu_tx_yearly' ? Promise.resolve({ data: [flowRow], error: null }) : baseRpc(fn, ...rest),
    );
    const { container } = render(<App />);
    await pickGu();
    const cards = () => container.querySelectorAll('.app__main > .card').length;
    await vi.waitFor(() => expect(cards()).toBeGreaterThan(0));
    const before = cards();
    await searchAndOpen();
    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(cards()).toBe(before); // 건물 탭에선 CSS 가 숨긴다 · 종이에선 인쇄 감춤(아래 CSS 시험)
    fireEvent.click(tab('찾기'));
    expect(cards()).toBe(before);
    cleanup();

    // 넓은 화면 대조 — 건물을 열면 카드가 물러난다(지금 그대로).
    delete (window as { matchMedia?: unknown }).matchMedia;
    window.history.replaceState(null, '', '/');
    const wide = render(<App />);
    await pickGu();
    await vi.waitFor(() => expect(wide.container.querySelectorAll('.app__main > .card').length).toBeGreaterThan(0));
    await searchAndOpen();
    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(wide.container.querySelectorAll('.app__main > .card').length).toBe(0);
  });

  it('★ 휴대폰 첫 방문 큰 카드 — 「가게를 열려고」(창업자)는 지도 탭 · 다른 역할은 찾기 그대로 · 커서는 고른 탭 단추(검사 🟠 F3 · 🟡 F4)', async () => {
    phoneMedia();
    window.localStorage.clear();
    const first = render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /가게를 열려고/ }));
    expect(current()).toBe('지도');
    expect(document.activeElement).toBe(tab('지도'));
    first.unmount();

    window.localStorage.clear();
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /투자·매입하려고/ }));
    expect(current()).toBe('찾기');
    expect(document.activeElement).toBe(tab('찾기'));
  });

  it('★ 휴대폰 건물 직행 링크인데 건물을 못 찾으면 — 「위에서…」 대신 「건물 찾으러 가기」 → 찾기 탭(검사 🟡 F5)', async () => {
    phoneMedia();
    from.mockImplementation((view: string) => makeQuery(view === 'v_coverage_stats' ? { data: [], error: null } : { data: [], error: null }));
    window.history.replaceState(null, '', `/?sgg=11680&bld=${BLD}`);
    render(<App />);
    expect(await screen.findByText('링크에 담긴 건물을 찾지 못했습니다.')).toBeTruthy();
    expect(screen.queryByText(/위에서 건물을 검색해 선택해 주세요/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '건물 찾으러 가기' }));
    expect(current()).toBe('찾기');
  });

  it('★ 넓은 화면 뒤로가기 — 우리 표식이 있는 칸이어도 탭·주소를 다시 쓰지 않는다(W4a 전과 같게 · 검사 🟡 F9)', async () => {
    render(<App />);
    await pickGu();
    await searchAndOpen();
    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(window.location.search).toContain(`bld=${BLD}`);
    window.history.replaceState({ sanggaTab: 'base' }, '', '/?sgg=11680');
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate', { state: { sanggaTab: 'base' } }));
    });
    // 휴대폰이면 지금 건물로 주소를 다시 적는다(위 「건물을 열면…」 시험) — 넓은 화면은 손대지 않는다.
    expect(window.location.search).toBe('?sgg=11680');
    expect(bar()).toBeNull();
  });
});

// ── 휴대폰 지도 가득 · 위 한 줄 띠 (👤 2026-10-19 결정 0039 W4b) ──────────────────────────────────

describe('휴대폰 지도 가득 (결정 0039 W4b)', () => {
  const strip = () => document.querySelector<HTMLButtonElement>('.rstrip__btn');
  const appEl = (c: HTMLElement) => c.querySelector('.app')!;

  /** 강남구·서초구 두 구 — 띠로 다른 구를 고르는 시험용. */
  function twoGus() {
    const base = rpc.getMockImplementation()!;
    rpc.mockImplementation((fn: string, ...rest: unknown[]) =>
      fn === 'list_open_sigungu'
        ? Promise.resolve({ data: [gu(), gu({ sigungu_code: '11650', sigungu_nm: '서초구' })], error: null })
        : base(fn, ...rest),
    );
  }

  it('★ 창업자 + 구 → 지도 탭: 지도 가득 · 띠 「서울 강남구」 · 띠를 누르면 같은 지역 고르개가 펼쳐지고 다른 구를 고르면 닫힘', async () => {
    phoneMedia();
    twoGus();
    window.localStorage.setItem('sangga.viewerRole', '창업자');
    const { container } = render(<App />);
    expect(current()).toBe('지도');
    // 구 고르기 전 = 지금 지역 고르개 화면 그대로(띠·가득 없음).
    expect(strip()).toBeNull();
    expect(appEl(container).classList.contains('app--mapfull')).toBe(false);
    await pickGu();

    expect(appEl(container).classList.contains('app--mapfull')).toBe(true);
    expect(strip()!.textContent).toBe('서울 강남구 ▾');
    expect(strip()!.getAttribute('aria-expanded')).toBe('false');
    const region = container.querySelector('section.region')!;
    expect(strip()!.getAttribute('aria-controls')).toBe('region-panel');
    expect(region.id).toBe('region-panel');
    expect(container.querySelector('section.dmap')!.getAttribute('data-layout')).toBe('full');
    expect(appEl(container).classList.contains('app--regionopen')).toBe(false);

    fireEvent.click(strip()!);
    expect(strip()!.getAttribute('aria-expanded')).toBe('true');
    expect(appEl(container).classList.contains('app--regionopen')).toBe(true);
    fireEvent.click(await screen.findByRole('button', { name: /^서초구/ }));
    // 다른 구를 고르면 닫히고 띠 글이 그 구 · 지역 고르개는 같은 노드(다시 태어나지 않는다).
    expect(appEl(container).classList.contains('app--regionopen')).toBe(false);
    expect(strip()!.textContent).toBe('서울 서초구 ▾');
    expect(strip()!.getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelector('section.region')).toBe(region);
  });

  it('★ 띠로 펼친 채 탭을 옮기면 닫힌다 · 찾기 탭엔 띠·가득 없음(지도는 같은 노드가 숨음)', async () => {
    phoneMedia();
    window.localStorage.setItem('sangga.viewerRole', '창업자');
    const { container } = render(<App />);
    await pickGu();
    const map = container.querySelector<HTMLElement>('section.dmap')!;
    fireEvent.click(strip()!);
    expect(appEl(container).classList.contains('app--regionopen')).toBe(true);
    fireEvent.click(tab('찾기'));
    expect(strip()).toBeNull();
    expect(appEl(container).classList.contains('app--mapfull')).toBe(false);
    expect(appEl(container).classList.contains('app--regionopen')).toBe(false);
    expect(map.hidden).toBe(true);
    fireEvent.click(tab('지도'));
    expect(strip()!.getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelector('section.dmap')).toBe(map);
    expect(map.hidden).toBe(false);
  });

  it('★ 첫 방문 그대로 — 지도 탭에 아직 안 간 사람(투자자 · 찾기 탭)은 지도를 안 그린다 · 한 번 본 뒤엔 숨기기만', async () => {
    phoneMedia();
    window.localStorage.setItem('sangga.viewerRole', '투자자');
    const { container } = render(<App />);
    await pickGu();
    expect(current()).toBe('찾기');
    expect(container.querySelector('section.dmap')).toBeNull();
    fireEvent.click(tab('지도'));
    const map = container.querySelector<HTMLElement>('section.dmap')!;
    expect(map.hidden).toBe(false);
    expect(strip()!.textContent).toBe('서울 강남구 ▾');
    fireEvent.click(tab('찾기'));
    expect(container.querySelector('section.dmap')).toBe(map);
    expect(map.hidden).toBe(true);
  });

  it('★ 중개사 — 띠·지도 가득 없음 · 지도는 찾기 탭 카드 꼴 그대로 · 다른 탭에선 같은 노드가 숨음', async () => {
    phoneMedia();
    window.localStorage.setItem('sangga.viewerRole', '중개사');
    const { container } = render(<App />);
    await pickGu();
    const map = container.querySelector<HTMLElement>('section.dmap')!;
    expect(map.getAttribute('data-layout')).toBe('card');
    expect(map.hidden).toBe(false);
    expect(strip()).toBeNull();
    expect(appEl(container).classList.contains('app--mapfull')).toBe(false);
    fireEvent.click(tab('뽑은 건물'));
    expect(container.querySelector('section.dmap')).toBe(map);
    expect(map.hidden).toBe(true);
    expect(strip()).toBeNull();
    fireEvent.click(tab('찾기'));
    expect(map.hidden).toBe(false);
  });

  it('★ 더보기 — 홈 화면 상자가 의견함 다음·안내 앞(눈 차례) · 의견함 DOM 자리는 그대로 맨 뒤', async () => {
    phoneMedia();
    const { container } = render(<App />);
    fireEvent.click(tab('더보기'));
    const foot = container.querySelector('footer.foot')!;
    const kids = [...foot.children];
    const at = (cls: string) => kids.findIndex((k) => k.classList.contains(cls));
    expect(at('hshint')).toBeGreaterThan(at('role'));
    expect(at('hshint')).toBeLessThan(at('foot__notice'));
    expect(foot.lastElementChild?.classList.contains('fb')).toBe(true);
  });
});

// ── CSS 가드 — 탭 꼴은 휴대폰 화면 묶음에만 · 종이에서 빠짐 · 44px 목록 ──────────────────────────────────

/**
 * CSS 를 주석 빼고 `@media` 묶음 밖(기본 규칙)과 안으로 갈라 규칙 목록으로 편다(`RoleSummary.test.tsx` 의 같은 이름 함수와 같은 꼴).
 * 못 보는 것: `@media` 안의 또 다른 겹 묶음 · 문자열 안의 중괄호 · 괄호 안 쉼표(선택자를 쉼표로만 가른다).
 */
function cssRules(css: string): { sel: string[]; body: string; media: string | null }[] {
  const src = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const out: { sel: string[]; body: string; media: string | null }[] = [];
  const take = (chunk: string, media: string | null) => {
    for (const m of chunk.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      out.push({ sel: m[1].split(',').map((x) => x.trim()), body: m[2], media });
    }
  };
  let i = 0;
  let plain = '';
  while (i < src.length) {
    const at = src.indexOf('@media', i);
    if (at < 0) {
      plain += src.slice(i);
      break;
    }
    plain += src.slice(i, at);
    const open = src.indexOf('{', at);
    let depth = 1;
    let j = open + 1;
    while (j < src.length && depth > 0) {
      if (src[j] === '{') depth += 1;
      else if (src[j] === '}') depth -= 1;
      j += 1;
    }
    take(src.slice(open + 1, j - 1), src.slice(at, open).trim());
    i = j;
  }
  take(plain, null);
  return out;
}

const PHONE = '@media screen and (max-width: 720px)';

/** 탭 꼴 이름표(`.app--tabs`·`.tabbar`)가 나오는 규칙의 묶음 머리들(인쇄 묶음은 뺀다). */
function tabMedias(css: string): (string | null)[] {
  return cssRules(css)
    .filter((r) => r.media !== '@media print' && r.sel.some((s) => /\.app--tabs|\.tabbar/.test(s)))
    .filter((r) => !(r.media === '@media screen' && /min-height:\s*44px/.test(r.body)))
    .map((r) => r.media);
}

describe('휴대폰 아래 탭 — CSS', () => {
  const css = readFileSync('src/styles.css', 'utf8');
  const rules = cssRules(css);

  it('탭 꼴 규칙은 전부 휴대폰 화면 묶음 안 — 기본 규칙·넓은 화면엔 0 · 양성 대조(흔한 꼴 + 다른 묶음 꼴)', () => {
    const medias = tabMedias(css);
    expect(medias.length).toBeGreaterThan(8);
    expect(new Set(medias)).toEqual(new Set([PHONE]));
    expect(tabMedias(`${css}\n.tabbar { position: fixed; }`)).toContain(null);
    expect(tabMedias(`${css}\n@media (max-width: 720px) {\n  .app--tabs .foot { display: none; }\n}`)).toContain(
      '@media (max-width: 720px)',
    );
  });

  it('종이에서 빠진다 — 탭 막대·빈 건물 안내 · 휴대폰에서 건물을 연 채면 입구(지도) 째', () => {
    const hide = rules.filter((r) => r.media === '@media print' && /display:\s*none/.test(r.body)).flatMap((r) => r.sel);
    for (const s of ['.tabbar', '.tabempty', '.app--tabs.app--bld .entry']) expect(hide, s).toContain(s);
  });

  it('누르는 것 44px 목록에 탭 단추·찾으러 가기·요약 더 보기 · 탭 단추 글자 13px 이상', () => {
    const tall = rules.filter((r) => r.media === '@media screen' && /min-height:\s*44px/.test(r.body)).flatMap((r) => r.sel);
    for (const s of ['.tabbar__btn', '.tabempty__go', '.rsum__more']) expect(tall, s).toContain(s);
    const btn = rules.find((r) => r.media === PHONE && r.sel.includes('.tabbar__btn') && /font-size/.test(r.body))!;
    expect(Number(/font-size:\s*(\d+)px/.exec(btn.body)![1])).toBeGreaterThanOrEqual(13);
  });

  it('아이폰 홈 막대 — 탭 막대에 safe-area 아래 · viewport-fit=cover · 줌은 막지 않는다', () => {
    const tabbar = rules.find((r) => r.media === PHONE && r.sel.includes('.tabbar') && /position:\s*fixed/.test(r.body))!;
    expect(tabbar.body).toMatch(/env\(safe-area-inset-bottom/);
    const html = readFileSync('index.html', 'utf8');
    const vp = /<meta name="viewport" content="([^"]+)"/.exec(html)![1];
    expect(vp).toContain('viewport-fit=cover');
    expect(vp).not.toMatch(/user-scalable\s*=\s*no|maximum-scale/);
  });

  it('작은 눌림 칸(넘기기 링크 폭 · 사무소 입력칸 높이)은 휴대폰 묶음에만 — 넓은 화면 그대로', () => {
    const wide = rules.filter((r) => r.media !== PHONE && r.media !== '@media print');
    expect(wide.filter((r) => r.sel.includes('.links__a') && /min-width/.test(r.body))).toEqual([]);
    expect(wide.filter((r) => r.sel.includes('.office__field input') && /min-height/.test(r.body))).toEqual([]);
    expect(rules.some((r) => r.media === PHONE && r.sel.includes('.links__a') && /min-width:\s*44px/.test(r.body))).toBe(true);
    expect(rules.some((r) => r.media === PHONE && r.sel.includes('.office__field input') && /min-height:\s*44px/.test(r.body))).toBe(
      true,
    );
  });

  it('좌우 안전 영역은 기본 `.app` 규칙(모든 폭 — viewport-fit=cover 가 모든 폭에 먹는다) · 탭 묶음엔 중복 없음(검사 🟠 F1)', () => {
    const app = rules.find((r) => r.media === null && r.sel.includes('.app'))!;
    expect(app.body).toMatch(/padding-left:\s*max\(20px,\s*env\(safe-area-inset-left/);
    expect(app.body).toMatch(/padding-right:\s*max\(20px,\s*env\(safe-area-inset-right/);
    const tabs = rules.filter((r) => r.media === PHONE && r.sel.includes('.app--tabs'));
    expect(tabs.length).toBe(1);
    expect(tabs[0].body).not.toMatch(/padding-(left|right)/);
  });

  it('흐린 「건물」 탭 — 단추 통째 투명도 0(글자 대비 유지) · 흐림은 그림만(검사 🟡 F7)', () => {
    const dim = rules.filter((r) => r.sel.some((s) => s.startsWith('.tabbar__btn--dim')));
    expect(dim.length).toBeGreaterThan(0);
    expect(dim.filter((r) => r.sel.includes('.tabbar__btn--dim') && /opacity/.test(r.body))).toEqual([]);
    expect(dim.some((r) => r.sel.includes('.tabbar__btn--dim .tabbar__icon') && /opacity/.test(r.body))).toBe(true);
  });

  it('더보기 눈 차례는 휴대폰 묶음의 CSS order — 역할 줄 0 · 의견함 1 · 나머지 2(검사 🟡 F8)', () => {
    const order = (sel: string) => {
      const r = rules.find((x) => x.media === PHONE && x.sel.includes(sel) && /order:/.test(x.body));
      return r ? Number(/order:\s*(\d+)/.exec(r.body)![1]) : null;
    };
    expect(order('.foot--phone > .role')).toBe(0);
    expect(order('.foot--phone > .fb')).toBe(1);
    expect(order('.foot--phone > *')).toBe(2);
    expect(rules.filter((r) => r.media !== PHONE && r.sel.some((s) => s.includes('.foot--phone')))).toEqual([]);
  });

  it('종이 — 휴대폰에서 건물을 연 채면 입구 카드도 빠지고(F2) · 건물이 없으면 숨긴 입구를 되살린다(F6)', () => {
    const print = rules.filter((r) => r.media === '@media print');
    const hide = print.filter((r) => /display:\s*none/.test(r.body)).flatMap((r) => r.sel);
    expect(hide).toContain('.app--tabs.app--bld .app__main > .card');
    expect(
      print.some((r) => r.sel.includes('.app--tabs:not(.app--bld) .entry[hidden]') && /display:\s*block/.test(r.body)),
    ).toBe(true);
  });

  /** W4b 이름표(띠·지도 가득·판·홈 화면 상자)가 나오는 규칙의 묶음 머리들(인쇄 묶음·44px 목록은 뺀다). */
  function w4bMedias(src: string): (string | null)[] {
    return cssRules(src)
      .filter((r) => r.media !== '@media print' && r.sel.some((s) => /\.app--mapfull|\.app--regionopen|\.rstrip|\.dmap--full|\.dsheet|\.hshint/.test(s)))
      .filter((r) => !(r.media === '@media screen' && /min-height:\s*44px/.test(r.body)))
      .map((r) => r.media);
  }

  it('W4b 규칙(띠·지도 가득·판·홈 화면 상자)은 전부 휴대폰 화면 묶음 안 · 양성 대조(기본 규칙 꼴 + 다른 묶음 꼴)', () => {
    const medias = w4bMedias(css);
    expect(medias.length).toBeGreaterThan(15);
    expect(new Set(medias)).toEqual(new Set([PHONE]));
    expect(w4bMedias(`${css}\n.rstrip { position: fixed; }`)).toContain(null);
    expect(w4bMedias(`${css}\n@media (max-width: 720px) {\n  .x,\n  .app--mapfull .dmap--full { top: 0; }\n}`)).toContain(
      '@media (max-width: 720px)',
    );
  });

  it('W4b — 지도 탭에서 사이트 제목 줄이 숨고 · 지역 고르개는 띠를 눌렀을 때만 · 종이에서 띠·판·홈 화면 상자가 빠진다 · 44px 목록', () => {
    const phone = rules.filter((r) => r.media === PHONE && /display:\s*none/.test(r.body)).flatMap((r) => r.sel);
    expect(phone).toContain('.app--mapfull .app__head');
    expect(phone).toContain('.app--mapfull:not(.app--regionopen) .entry > .region');
    const hide = rules.filter((r) => r.media === '@media print' && /display:\s*none/.test(r.body)).flatMap((r) => r.sel);
    for (const s of ['.rstrip', '.dsheet', '.hshint', '.chips']) expect(hide, s).toContain(s);
    const tall = rules.filter((r) => r.media === '@media screen' && /min-height:\s*44px/.test(r.body)).flatMap((r) => r.sel);
    for (const s of ['.rstrip__btn', '.dsheet__handle', '.dsheet__fold', '.hshint__btn']) expect(tall, s).toContain(s);
  });
});
