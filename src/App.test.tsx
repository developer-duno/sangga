import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
import type { BuildingHit, FloorRow, OpenSigungu } from './types';

/**
 * App 통합 테스트.
 *
 * 개별 동작(지역 게이트·구 목록·검색 규칙·층 스택 렌더)은 각 컴포넌트 테스트가 이미
 * 촘촘히 덮는다. 여기서는 **여러 컴포넌트를 이어 붙였을 때만 드러나는 것 하나** —
 * 구를 바꾸면 이전 구의 검색 결과·선택 건물이 화면에 남지 않는지만 본다.
 */

const rpc = vi.fn();
const from = vi.fn();

/** supabase 쿼리 빌더 흉내(FloorStack.test.tsx와 동일한 방식). */
function makeQuery(result: { data: unknown; error: unknown }) {
  const q: Record<string, unknown> = {};
  for (const m of ['select', 'eq', 'order', 'limit']) q[m] = () => q;
  q.then = (cb: (r: unknown) => unknown) => Promise.resolve(result).then(cb);
  return q;
}

// 흉내 낼 것은 **키를 요구하는 클라이언트 하나뿐**이다. 표·함수 이름 같은 상수는
// 아무 일도 안 하는 `lib/appConstants.ts` 에 있어 화면이 진짜 값을 그대로 쓴다
// (예전에는 여기 상수를 거울처럼 다시 적어 두어, 진짜 값이 바뀌어도 테스트만 초록이었다).
vi.mock('./lib/supabase', () => ({
  supabase: {
    rpc: (...args: unknown[]) => rpc(...args),
    from: (view: string) => from(view),
  },
}));

const { default: App } = await import('./App');

function gu(over: Partial<OpenSigungu> = {}): OpenSigungu {
  return {
    sido_code: '11',
    sido_nm: '서울',
    sigungu_code: '11680',
    sigungu_nm: '강남구',
    building_cnt: 14223,
    ...over,
  };
}

function hit(over: Partial<BuildingHit> = {}): BuildingHit {
  return {
    bld_id: '1168010100100010000_1024110',
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

function floorRow(over: Partial<FloorRow> = {}): FloorRow {
  return {
    bld_id: '1168010100100010000_1024110',
    pnu: '1168010100100010000',
    floor_no: 1,
    floor_label: null,
    floor_area_m2: 100,
    floor_area_gross_m2: 110,
    segment_cnt: 1,
    main_use: '소매점',
    uses: [],
    bld_nm: '테스트빌딩',
    approve_date: '2003-05-14',
    is_jiphap: true,
    road_addr: '서울 강남구 테헤란로 1',
    road_contact: null,
    bld_cnt_in_pnu: 1,
    store_cnt: 1,
    stores: [],
    // 건물 스펙 4칸(2026-08-24a) — 이 파일은 배선만 보므로 값은 정상값 하나면 된다.
    total_area_m2: 1234.5,
    far: 350.5,
    bcr: 59.9,
    parking_cnt: 12,
    ...over,
  };
}

beforeEach(() => {
  // '물어봤음' 기본값(결정 0039 §4-7 · W3) — 저장값이 없으면 입구 맨 위에 역할 고르기 큰 카드가 서고 작은 역할 단추 줄은
  // 숨는다. 이 파일의 시험은 그 카드가 나오기 전 화면을 전제로 쓰였으므로 시작 때 `둘러보기`(= 역할 없음)를 넣는다.
  // 역할을 따로 넣는 시험은 이 뒤에 setItem 하므로 그 값이 이긴다. 큰 카드 시험은 아래 「큰 카드」 묶음이 이 값을 지우고 본다.
  window.localStorage.setItem('sangga.viewerRole', '둘러보기');
  rpc.mockReset();
  from.mockReset();
  from.mockImplementation((view: string) =>
    makeQuery(view === 'v_coverage_stats' ? { data: [], error: null } : { data: [floorRow()], error: null }),
  );
  rpc.mockImplementation((fn: string) => {
    if (fn === 'list_open_sigungu') {
      return Promise.resolve({
        data: [
          gu({ sigungu_code: '11680', sido_code: '11', sido_nm: '서울', sigungu_nm: '강남구' }),
          gu({ sigungu_code: '30170', sido_code: '30', sido_nm: '대전', sigungu_nm: '서구' }),
        ],
        error: null,
      });
    }
    if (fn === 'search_buildings') {
      return Promise.resolve({ data: [hit()], error: null });
    }
    if (fn === 'list_building_districts') {
      // 이 화면 테스트의 관심사가 아니다 — 상권 줄이 조용히 지나가게만 해 둔다.
      // sources 는 서버가 자료에서 읽어 주는 출처 목록(2026-08-14). 실제 응답 모양 그대로 흉내 낸다.
      return Promise.resolve({
        data: { covered: true, districts: [], sources: ['서울특별시 상권분석서비스'] },
        error: null,
      });
    }
    return Promise.resolve({ data: [], error: null });
  });
});

afterEach(() => cleanup());

/** 주소를 첫 화면으로 되돌린다. App 은 **첫 그림 한 번만** 주소를 읽으므로
 *  render() 앞에서 정해 두어야 한다. */
function openWith(search: string) {
  window.history.replaceState(null, '', `/${search}`);
}

/** 지금 주소의 물음표 뒷부분. */
function currentSearch() {
  return window.location.search;
}


async function pickGu(sidoName: string, guName: string) {
  // ⚠️ 시도 칩도 서버 응답(list_open_sigungu)을 받은 뒤에 그려진다 — 자료가 있는
  //    지역만 보여주기로 하면서(2026-08-13 사장님 결정) 목록이 서버에서 오게 됐다.
  const sidoBtn = await screen.findByRole('button', { name: new RegExp(`^${sidoName}$`) });
  fireEvent.click(sidoBtn);
  // ⚠️ 구 칩에는 이름 뒤에 건물 수("강남구 14,223동")가 함께 붙는다 — 이름 전체가 아니라
  //    **앞부분**으로 찾아야 한다(정확히 일치로 찾으면 칩이 멀쩡히 있는데도 못 찾는다).
  const guBtn = await screen.findByRole('button', { name: new RegExp(`^${guName}`) });
  fireEvent.click(guBtn);
}

/**
 * 건물을 연 동안 한 줄 바로 접힌 입구(S1)를 바의 「다른 건물 찾기」로 펼친다 — 접혀 있지 않으면 아무 일도 안 한다.
 * ⓘ 접힌 입구는 `hidden` 이라 역할 단추·지역 칩·검색 결과를 `getByRole` 이 못 찾는다(손님 눈에도 안 보인다).
 */
function unfoldEntry() {
  const btn = [...document.querySelectorAll<HTMLButtonElement>('.entrybar button')].find(
    (b) => b.textContent === '← 다른 건물 찾기',
  );
  if (btn) fireEvent.click(btn);
}

describe('App — 구를 바꾸면 이전 결과가 사라진다', () => {
  it('검색 결과·선택 건물·검색어가 구를 바꾸는 순간 함께 사라진다', async () => {
    openWith(''); // 앞 시험이 남긴 건물 주소로 시작하면 입구가 접혀 지역 칩이 숨는다(순서 섞기 seed 2·3).
    render(<App />);

    await pickGu('서울', '강남구');

    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);

    const hitBtn = await screen.findByRole('button', { name: /테스트빌딩/ });
    fireEvent.click(hitBtn);
    await waitFor(() => expect(screen.getByRole('heading', { name: '테스트빌딩' })).toBeTruthy());
    expect(screen.getByText(/강남구에서/)).toBeTruthy();

    unfoldEntry(); // 건물을 열면 입구가 접힌다(S1) — 구를 바꾸려면 펼친다.
    await pickGu('대전', '서구');

    // 이전 구의 선택 건물(층 스택)·검색 결과 문구·검색어가 전부 사라졌다.
    expect(screen.queryByRole('heading', { name: '테스트빌딩' })).toBeNull();
    expect(screen.queryByText(/강남구에서/)).toBeNull();
    expect(screen.getByText('위에서 건물을 검색해 선택해 주세요.')).toBeTruthy();
    expect((screen.getByLabelText('건물명 또는 주소') as HTMLInputElement).value).toBe('');
  });
});

/**
 * 입구 카드 — LH 상가 분양·입점 공고.
 *
 * 카드 안쪽(요약 문구·링크·빈손 처리)은 `components/LhNoticeSection.test.tsx` 가 촘촘히
 * 덮는다. 여기서 보는 것은 **여러 조각을 이어 붙였을 때만 드러나는 것 하나** — 이 카드가
 * 서고 사라지는 **때**다. 조건이 App 의 상태 셋(구·선택 건물·되살리는 중)에 걸려 있어
 * 컴포넌트 시험만으로는 볼 수 없다.
 */
describe('App — 입구의 LH 공고 카드', () => {
  const lhNotice = {
    pan_id: '2026-0001',
    pan_nm: '서울강남 A1블록 단지내상가 입찰공고',
    kind_nm: '분양 입찰',
    pan_ss: '공고중',
    notice_date: '2026-08-20',
    close_date: '2026-09-17',
    dtl_url: 'https://apply.lh.or.kr/notice/2026-0001',
    collected_at: new Date(2026, 7, 27, 9, 0).toISOString(),
  };

  /** 기본 목에 LH 응답만 얹는다(나머지 함수는 beforeEach 의 것을 그대로 쓴다). */
  function withLhNotices(rows: unknown[] = [lhNotice]) {
    const base = rpc.getMockImplementation()!;
    rpc.mockImplementation((fn: string, args?: unknown) =>
      fn === 'list_lh_notices' ? Promise.resolve({ data: rows, error: null }) : base(fn, args),
    );
  }

  it('구를 고르면 접힌 카드로 서고, 시도 두 자리로 묻는다', async () => {
    // ⚠️ 주소는 시험끼리 이어진다(replaceState 가 그대로 남는다) — 앞 시험이 남긴 구가
    //    묻어 오면 "구를 고르기 전"이 아니게 되므로 첫 화면으로 되돌려 놓고 시작한다.
    openWith('');
    withLhNotices();
    render(<App />);

    // 구를 고르기 전에는 물을 곳이 없다 — 카드도 질문도 없다.
    await screen.findByRole('button', { name: /^서울$/ });
    expect(screen.queryByText('LH 상가 분양·입점 공고')).toBeNull();

    await pickGu('서울', '강남구');

    expect(await screen.findByText('LH 상가 분양·입점 공고')).toBeTruthy();
    const toggle = screen.getByRole('button', { name: /LH 상가 분양·입점 공고/ });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    // ⚠️ 계약은 시도 두 자리다(서버도 앞 두 자리만 보게 막혀 있지만 거기 기대지 않는다).
    expect(rpc.mock.calls.filter(([fn]) => fn === 'list_lh_notices')[0][1]).toEqual({
      p_sido: '11',
    });
  });

  it('★ 건물을 고르면 사라지고, 선택을 풀면 다시 보인다 (분석 화면을 어지럽히지 않는다)', async () => {
    openWith('');
    withLhNotices();
    render(<App />);
    await pickGu('서울', '강남구');
    await screen.findByText('LH 상가 분양·입점 공고');

    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    fireEvent.click(await screen.findByRole('button', { name: /테스트빌딩/ }));

    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(screen.queryByText('LH 상가 분양·입점 공고')).toBeNull();

    // 새 검색을 걸면 선택이 풀린다 — 다시 입구 상태다.
    fireEvent.change(input, { target: { value: '역삼' } });
    fireEvent.submit(input.closest('form')!);
    expect(await screen.findByText('LH 상가 분양·입점 공고')).toBeTruthy();
  });

  it('링크로 들어와 되살리는 동안에는 카드를 먼저 그리지 않는다 (나타났다 사라지지 않게)', async () => {
    // 층 목록 응답을 붙잡아 "되살리는 중"을 만든다(위 ★ 시험과 같은 방식).
    let release: ((r: { data: unknown; error: unknown }) => void) | null = null;
    const pending = new Promise<{ data: unknown; error: unknown }>((r) => {
      release = r;
    });
    from.mockImplementation((view: string) => {
      if (view === 'v_coverage_stats') return makeQuery({ data: [], error: null });
      const q: Record<string, unknown> = {};
      for (const m of ['select', 'eq', 'order', 'limit']) q[m] = () => q;
      q.then = (cb: (r: unknown) => unknown) => pending.then(cb);
      return q;
    });
    withLhNotices();

    // ⓘ 링크의 건물 id 는 아래 `LINK_BLD` 와 같은 값이지만, 그 상수는 이 블록보다 뒤에
    //   선언돼 있어 여기서는 픽스처에서 그대로 얻는다(같은 값을 두 번 적지 않는다).
    openWith(`?sgg=11680&bld=${hit().bld_id}`);
    render(<App />);

    await screen.findByText('링크에 담긴 건물을 불러오는 중입니다…');
    expect(screen.queryByText('LH 상가 분양·입점 공고')).toBeNull();

    release!({ data: [floorRow()], error: null });
    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(screen.queryByText('LH 상가 분양·입점 공고')).toBeNull();
  });

  it('열린 공고가 없으면 입구에 아무것도 안 생긴다', async () => {
    openWith('');
    withLhNotices([]);
    render(<App />);
    await pickGu('서울', '강남구');

    await waitFor(() =>
      expect(rpc.mock.calls.filter(([fn]) => fn === 'list_lh_notices')).toHaveLength(1),
    );
    expect(screen.queryByText('LH 상가 분양·입점 공고')).toBeNull();
  });
});

/**
 * 주소로 들고 다니기 (공유 링크 · 새로고침 복원).
 *
 * 여기서 특히 지키는 것
 * ---------------------
 * **되살리는 중에 주소가 스스로 지워지지 않는 것.** 되살리는 동안 선택 건물은 아직
 * 비어 있어서, 그 사이 "지금 보고 있는 것"을 주소에 적으면 **링크를 열자마자 그
 * 링크가 사라진다.** 에러가 안 나고 화면도 멀쩡해 보여서, 사용자가 새로고침해 보기
 * 전까지는 아무도 모른다 — 이 기능 전체에서 가장 조용히 깨지는 자리다.
 */
const LINK_BLD = '1168010100100010000_1024110';

describe('App — 주소로 들고 다니기', () => {
  it('링크로 들어오면 검색을 거치지 않고 그 건물이 살아난다', async () => {
    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);

    expect(await screen.findByRole('heading', { name: '테스트빌딩' })).toBeTruthy();
    // 검색을 부르지 않았다 — 층 목록만으로 되살렸다는 뜻이다.
    expect(rpc.mock.calls.filter(([fn]) => fn === 'search_buildings')).toHaveLength(0);
  });

  it('링크로 들어오면 구 이름까지 살아난다', async () => {
    // 주소에는 코드(11680)만 있다. 이름을 주소에 담으면 구 이름이 바뀌는 날 옛 링크가
    // 옛 이름을 말하므로, 이름은 늘 서버 목록에서 얻는다.
    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);

    // 건물이 서면 입구가 접혀 지도를 안 그린다(S1) — 바의 「상권 지도 보기」로 펼쳐 지도 제목을 본다.
    fireEvent.click(await screen.findByRole('button', { name: '상권 지도 보기' }));
    expect(await screen.findByRole('heading', { name: /강남구 상권 지도/ })).toBeTruthy();
  });

  it('★ 되살리는 중에 주소가 지워지지 않는다', async () => {
    // 층 목록 응답을 일부러 붙잡아 둔 채 "되살리는 중" 상태를 만든다.
    let release: ((r: { data: unknown; error: unknown }) => void) | null = null;
    const pending = new Promise<{ data: unknown; error: unknown }>((r) => {
      release = r;
    });
    from.mockImplementation((view: string) => {
      if (view === 'v_coverage_stats') return makeQuery({ data: [], error: null });
      const q: Record<string, unknown> = {};
      for (const m of ['select', 'eq', 'order', 'limit']) q[m] = () => q;
      q.then = (cb: (r: unknown) => unknown) => pending.then(cb);
      return q;
    });

    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);

    expect(await screen.findByText('링크에 담긴 건물을 불러오는 중입니다…')).toBeTruthy();
    // 아직 되살리는 중인데 주소에서 건물이 빠져 있으면, 새로고침하는 순간 링크가 죽는다.
    expect(currentSearch()).toContain(`bld=${LINK_BLD}`);

    release!({ data: [floorRow()], error: null });
    expect(await screen.findByRole('heading', { name: '테스트빌딩' })).toBeTruthy();
    expect(currentSearch()).toContain(`bld=${LINK_BLD}`);
  });

  it('★ 되살리는 중에 사용자가 다른 건물을 고르면, 뒤늦게 도착한 복원 결과가 그 선택을 덮어쓰지 않는다', async () => {
    // 링크가 가리키는 건물(LINK_BLD)의 층 목록 조회만 붙잡아 둔다. 사용자가 검색으로
    // 고를 다른 건물은 즉시 응답하게 해, "먼저 응답한 쪽"이 아니라 "사용자가 실제로
    // 고른 쪽"이 이기는지를 본다.
    let releaseRestore: ((r: { data: unknown; error: unknown }) => void) | null = null;
    const restorePending = new Promise<{ data: unknown; error: unknown }>((r) => {
      releaseRestore = r;
    });

    const otherHit = hit({
      bld_id: '1168010100200020000_2024110',
      pnu: '1168010100200020000',
      bld_nm: '사용자선택빌딩',
      road_addr: '서울 강남구 테헤란로 2',
    });
    const otherFloorRow = floorRow({
      bld_id: otherHit.bld_id,
      pnu: otherHit.pnu,
      bld_nm: otherHit.bld_nm,
      road_addr: otherHit.road_addr,
    });

    // ⚠️ **호출 순번이 아니라 "누구를 물었는가"로** 나눈다. 순번으로 나누면(첫 번째만
    //    붙잡고 두 번째부터 '사용자선택빌딩'을 주기), 덮어쓰기가 실제로 일어나 화면이
    //    링크 건물로 되돌아가도 **다시 그려진 층 목록이 여전히 '사용자선택빌딩'**이라
    //    제목이 안 바뀐다 — 버그가 있어도 초록인 눈먼 시험이 된다(제목은 building 이
    //    아니라 **받아 온 층 자료**의 이름을 그린다: FloorStack 의 `head = floors[0]`).
    from.mockImplementation((view: string) => {
      if (view === 'v_coverage_stats') return makeQuery({ data: [], error: null });
      let askedBldId: string | null = null;
      const q: Record<string, unknown> = {};
      for (const m of ['select', 'order', 'limit']) q[m] = () => q;
      q.eq = (col: string, val: string) => {
        if (col === 'bld_id') askedBldId = val;
        return q;
      };
      q.then = (cb: (r: unknown) => unknown) =>
        (askedBldId === LINK_BLD
          ? restorePending
          : Promise.resolve({ data: [otherFloorRow], error: null })
        ).then(cb);
      return q;
    });
    rpc.mockImplementation((fn: string) => {
      if (fn === 'list_open_sigungu') {
        return Promise.resolve({
          data: [gu({ sigungu_code: '11680', sido_code: '11', sido_nm: '서울', sigungu_nm: '강남구' })],
          error: null,
        });
      }
      if (fn === 'search_buildings') return Promise.resolve({ data: [otherHit], error: null });
      if (fn === 'list_building_districts') {
        return Promise.resolve({ data: { covered: true, districts: [], sources: [] }, error: null });
      }
      return Promise.resolve({ data: [], error: null });
    });

    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);

    expect(await screen.findByText('링크에 담긴 건물을 불러오는 중입니다…')).toBeTruthy();

    // 그 사이 사용자가 검색으로 다른 건물을 고른다(되살리는 동안도 입구는 접혀 있다 — 바에서 펼친다).
    unfoldEntry();
    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    fireEvent.click(await screen.findByRole('button', { name: /사용자선택빌딩/ }));

    expect(await screen.findByRole('heading', { name: '사용자선택빌딩' })).toBeTruthy();

    // 뒤늦게 링크 복원 응답(LINK_BLD, '테스트빌딩')이 도착한다 — 사용자의 선택을
    // 덮어쓰면 안 된다.
    await act(async () => {
      releaseRestore!({ data: [floorRow()], error: null });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByRole('heading', { name: '사용자선택빌딩' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: '테스트빌딩' })).toBeNull();
    // 주소도 사용자가 고른 건물을 가리켜야 한다 — 덮어쓰이면 주소 쓰기 useEffect 가
    // 링크 건물을 다시 적어, 그 상태로 새로고침하면 고른 건물이 통째로 사라진다.
    expect(currentSearch()).toContain(`bld=${otherHit.bld_id}`);
    expect(currentSearch()).not.toContain(`bld=${LINK_BLD}`);
  });

  it('층 자료가 없는 건물이면 빈 화면 대신 정직하게 안내한다', async () => {
    // 층이 한 줄도 없는 건물이 239동 실재한다.
    from.mockImplementation(() => makeQuery({ data: [], error: null }));

    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);

    expect(
      await screen.findByText('링크에 담긴 건물을 찾지 못했습니다. 위에서 건물을 검색해 선택해 주세요.'),
    ).toBeTruthy();
  });

  it('되살리기에 실패해도 주소를 지우지 않는다 (새로고침으로 다시 해 볼 수 있게)', async () => {
    from.mockImplementation(() => makeQuery({ data: null, error: { message: '잠깐 흔들림' } }));

    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);

    await screen.findByText(/찾지 못했습니다/);
    expect(currentSearch()).toContain(`bld=${LINK_BLD}`);
  });

  it('건물을 고르면 주소에 적힌다', async () => {
    openWith('');
    render(<App />);

    await pickGu('서울', '강남구');
    await waitFor(() => expect(currentSearch()).toContain('sgg=11680'));

    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    fireEvent.click(await screen.findByRole('button', { name: /테스트빌딩/ }));

    await waitFor(() => expect(currentSearch()).toContain(`bld=${LINK_BLD}`));
  });

  it('구를 바꾸면 주소에서 이전 건물이 빠진다', async () => {
    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);
    await screen.findByRole('heading', { name: '테스트빌딩' });

    unfoldEntry();
    await pickGu('대전', '서구');

    await waitFor(() => expect(currentSearch()).not.toContain('bld='));
    expect(currentSearch()).toContain('sgg=30170');
  });

  it('아무것도 안 고른 상태에서는 주소가 깨끗하다', async () => {
    openWith('');
    render(<App />);
    await screen.findByRole('button', { name: /^서울$/ });

    // '?' 만 남은 주소를 만들지 않는다.
    expect(currentSearch()).toBe('');
  });

  it('건물을 고른 뒤에만 링크 복사 버튼이 보인다', async () => {
    openWith('');
    render(<App />);
    await pickGu('서울', '강남구');

    expect(screen.queryByRole('button', { name: '링크 복사' })).toBeNull();

    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    fireEvent.click(await screen.findByRole('button', { name: /테스트빌딩/ }));

    expect(await screen.findByRole('button', { name: '링크 복사' })).toBeTruthy();
  });
});

/**
 * 역할 단추(👤 결정 0036 결정 18) — 이어 붙였을 때만 보이는 것: 고른 역할이 **이 기기에 저장**되고
 * 층별 화면이 그 역할 순서로 서며, **주소에는 안 실린다**. 단추 하나의 동작은 `RolePicker.test`,
 * 저장의 예외 처리는 `viewerRoleStore.test`, 역할별 표는 `FloorStack.test` 가 본다.
 */
describe('App — 역할 단추 (결정 0036 결정 18)', () => {
  const KEY = 'sangga.viewerRole';
  afterEach(() => window.localStorage.clear());

  /**
   * 층별 화면 카드 중 이 흉내에서 서는 두 장(속한 상권·층 목록)의 차례. 다른 카드는 응답에 따라
   * 서거나 사라지므로 이 둘만 본다 — 두 장의 앞뒤는 역할 없음과 중개사에서 뒤바뀐다.
   */
  function cardTitles() {
    return [...document.querySelectorAll('.stack .card .card__title')]
      .map((el) => el.textContent)
      .filter((t) => t === '속한 상권' || t === '층 목록');
  }

  it('저장된 역할이 없으면 아무 단추도 눌려 있지 않고 카드는 지금 순서다', async () => {
    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);
    await screen.findByRole('heading', { name: '테스트빌딩' });
    unfoldEntry();
    for (const name of ['투자자', '창업자', '중개사']) {
      expect(screen.getByRole('button', { name }).getAttribute('aria-pressed')).toBe('false');
    }
    await waitFor(() => expect(cardTitles()).toEqual(['속한 상권', '층 목록']));
  });

  it('★ 저장된 역할로 첫 그림부터 눌려 있고, 층별 화면이 그 역할 순서로 선다', async () => {
    window.localStorage.setItem(KEY, '중개사');
    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);
    await screen.findByRole('heading', { name: '테스트빌딩' });
    unfoldEntry();
    expect(screen.getByRole('button', { name: '중개사' }).getAttribute('aria-pressed')).toBe('true');
    // 중개사는 층 목록이 먼저다(역할 없음은 속한 상권이 먼저).
    await waitFor(() => expect(cardTitles()).toEqual(['층 목록', '속한 상권']));
  });

  it('★ 누르면 이 기기에 저장되고, 다시 누르면 「둘러보기」로 적힌다(결정 0039 §7-4) — 주소에는 안 실린다', async () => {
    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);
    await screen.findByRole('heading', { name: '테스트빌딩' });
    await waitFor(() => expect(cardTitles()).toEqual(['속한 상권', '층 목록']));
    const before = currentSearch();
    unfoldEntry();

    fireEvent.click(screen.getByRole('button', { name: '중개사' }));
    expect(window.localStorage.getItem(KEY)).toBe('중개사');
    expect(screen.getByRole('button', { name: '중개사' }).getAttribute('aria-pressed')).toBe('true');
    // 건물 화면이 열린 채 바꿔도 바로 따른다.
    expect(cardTitles()).toEqual(['층 목록', '속한 상권']);
    expect(currentSearch()).toBe(before);

    fireEvent.click(screen.getByRole('button', { name: '중개사' }));
    expect(window.localStorage.getItem(KEY)).toBe('둘러보기');
    expect(cardTitles()).toEqual(['속한 상권', '층 목록']);
    expect(currentSearch()).toBe(before);
  });

  it('★ 저장이 막힌 창에서도 화면은 고른 역할대로 선다 (저장만 못 한다)', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    try {
      openWith(`?sgg=11680&bld=${LINK_BLD}`);
      render(<App />);
      await screen.findByRole('heading', { name: '테스트빌딩' });
      unfoldEntry();
      fireEvent.click(screen.getByRole('button', { name: '중개사' }));
      expect(setItem).toHaveBeenCalled();
      expect(screen.getByRole('button', { name: '중개사' }).getAttribute('aria-pressed')).toBe(
        'true',
      );
      await waitFor(() => expect(cardTitles()).toEqual(['층 목록', '속한 상권']));
    } finally {
      setItem.mockRestore();
      getItem.mockRestore();
    }
  });
});

/**
 * 역할 고르기 큰 카드(결정 0039 Q3 · §4-10 · §7-4 · W3) — 이 기기 저장값이 없고 건물 직행 링크(`bld`)로 연 게 아닐 때만
 * 입구 맨 위(작은 역할 단추 줄 자리)에 선다. 카드 한 장의 글·알림은 `RoleCards.test`, 저장 규칙은 `viewerRoleStore.test`.
 */
describe('App — 역할 고르기 큰 카드 (결정 0039 W3)', () => {
  const KEY = 'sangga.viewerRole';
  // 맨 위 beforeEach 의 '물어봤음' 기본값을 지운다 — 처음 온 사람(빈 저장소).
  beforeEach(() => {
    window.localStorage.clear();
    openWith('');
  });
  afterEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  const cards = () => document.querySelector('section.rolecards');
  const smallRow = () => document.querySelector('section.role');
  const cardBtn = (name: RegExp) => screen.getByRole('button', { name });

  it('★ 빈 저장소로 `/` 를 열면 큰 카드가 서고 작은 단추 줄은 숨는다 · 카드 셋 + 그냥 둘러보기', async () => {
    render(<App />);
    await screen.findByRole('button', { name: /^서울$/ });
    expect(cards()).not.toBeNull();
    expect(smallRow()).toBeNull();
    expect(screen.getByText('무엇을 하러 오셨나요?')).toBeTruthy();
    expect([...document.querySelectorAll('.rolecards__name')].map((e) => e.textContent)).toEqual([
      '투자·매입하려고',
      '가게를 열려고',
      '중개하려고',
    ]);
    expect(screen.getByRole('button', { name: '그냥 둘러보기' })).toBeTruthy();
    // 덮개가 아니다 — 지역 고르기가 같은 화면에 그대로 있다.
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(screen.getByRole('button', { name: /^서울$/ })).toBeTruthy();
  });

  it('★ `?sgg=` 만 든 링크에서도 뜬다(건물 직행만 예외)', async () => {
    openWith('?sgg=30170');
    render(<App />);
    await screen.findByRole('button', { name: /^대전$/ });
    expect(cards()).not.toBeNull();
  });

  it('★ 카드를 누르면 그 역할이 저장되고 카드가 사라지며 작은 줄에 그 역할이 눌린다 · 주소에는 안 실린다', async () => {
    openWith('?sgg=11680');
    render(<App />);
    await screen.findByRole('button', { name: /^서울$/ });
    const before = currentSearch();
    fireEvent.click(cardBtn(/가게를 열려고/));
    expect(window.localStorage.getItem(KEY)).toBe('창업자');
    expect(cards()).toBeNull();
    expect(smallRow()).not.toBeNull();
    expect(screen.getByRole('button', { name: '창업자' }).getAttribute('aria-pressed')).toBe('true');
    expect(currentSearch()).toBe(before);
    expect(currentSearch()).not.toContain(encodeURIComponent('창업자'));
  });

  it('★ 카드로 고르면 커서가 body 로 떨어지지 않고 작은 줄의 눌린 단추로 간다(화면은 안 굴린다)', async () => {
    render(<App />);
    await screen.findByRole('button', { name: /^서울$/ });
    const focus = vi.spyOn(HTMLElement.prototype, 'focus');
    const card = cardBtn(/중개하려고/);
    card.focus();
    fireEvent.click(card);
    expect(cards()).toBeNull();
    const pressed = screen.getByRole('button', { name: '중개사' });
    expect(pressed.getAttribute('aria-pressed')).toBe('true');
    expect(document.activeElement).toBe(pressed);
    expect(focus).toHaveBeenLastCalledWith({ preventScroll: true });
  });

  it('★ 「그냥 둘러보기」로 고르면 작은 줄의 첫 단추에 커서', async () => {
    render(<App />);
    await screen.findByRole('button', { name: /^서울$/ });
    const browse = screen.getByRole('button', { name: '그냥 둘러보기' });
    browse.focus();
    fireEvent.click(browse);
    expect(cards()).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '투자자' }));
    expect(document.activeElement).toBe(document.querySelector('section.role .role__chip'));
  });

  it('★ 「그냥 둘러보기」= `둘러보기` 저장 · 카드 사라짐 · 아무 역할도 안 눌림 · 다시 열어도 안 뜬다', async () => {
    render(<App />);
    await screen.findByRole('button', { name: /^서울$/ });
    fireEvent.click(screen.getByRole('button', { name: '그냥 둘러보기' }));
    expect(window.localStorage.getItem(KEY)).toBe('둘러보기');
    expect(cards()).toBeNull();
    for (const name of ['투자자', '창업자', '중개사']) {
      expect(screen.getByRole('button', { name }).getAttribute('aria-pressed')).toBe('false');
    }
    cleanup();
    render(<App />);
    await screen.findByRole('button', { name: /^서울$/ });
    expect(cards()).toBeNull();
    expect(smallRow()).not.toBeNull();
  });

  it('★ 고른 역할을 작은 단추로 해제하면 `둘러보기`(지우지 않음) → 다음 방문에 큰 카드가 안 뜬다', async () => {
    render(<App />);
    await screen.findByRole('button', { name: /^서울$/ });
    fireEvent.click(cardBtn(/중개하려고/));
    fireEvent.click(screen.getByRole('button', { name: '중개사' }));
    expect(window.localStorage.getItem(KEY)).toBe('둘러보기');
    cleanup();
    render(<App />);
    await screen.findByRole('button', { name: /^서울$/ });
    expect(cards()).toBeNull();
  });

  it('저장값이 모르는 값이면 안 물어본 것으로 보고 뜬다', async () => {
    window.localStorage.setItem(KEY, 'investor');
    render(<App />);
    await screen.findByRole('button', { name: /^서울$/ });
    expect(cards()).not.toBeNull();
  });

  it('★ 저장이 막힌 창 — 뜨고, 누르면 사라지며 화면은 그 역할대로 · 오류 없음 · 다음 방문에 다시 뜬다', async () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    render(<App />);
    await screen.findByRole('button', { name: /^서울$/ });
    expect(cards()).not.toBeNull();
    fireEvent.click(cardBtn(/투자·매입하려고/));
    expect(setItem).toHaveBeenCalled();
    expect(cards()).toBeNull();
    expect(screen.getByRole('button', { name: '투자자' }).getAttribute('aria-pressed')).toBe('true');
    cleanup();
    render(<App />);
    await screen.findByRole('button', { name: /^서울$/ });
    expect(getItem).toHaveBeenCalled();
    expect(cards()).not.toBeNull();
  });

  it('★ 건물 직행 링크(`bld`)로 연 방문에는 그 방문 내내 안 뜨고 저장도 안 한다 → 다음에 `/` 로 오면 뜬다', async () => {
    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);
    await screen.findByRole('heading', { name: '테스트빌딩' });
    unfoldEntry();
    expect(cards()).toBeNull();
    expect(smallRow()).not.toBeNull();
    // 건물 선택을 풀고 입구로 돌아와도(구를 바꾸면 건물이 빠진다) 그 방문 동안은 안 뜬다.
    await pickGu('대전', '서구');
    await waitFor(() => expect(screen.queryByRole('heading', { name: '테스트빌딩' })).toBeNull());
    expect(cards()).toBeNull();
    expect(window.localStorage.getItem(KEY)).toBeNull();

    cleanup();
    openWith('');
    render(<App />);
    await screen.findByRole('button', { name: /^서울$/ });
    expect(cards()).not.toBeNull();
  });

  it('★ 큰 카드가 서 있는 채 건물을 열고 바의 「나는 역할 고르기」를 누르면 펼치고 첫 카드 단추에 커서', async () => {
    const scrolled: Element[] = [];
    Element.prototype.scrollIntoView = vi.fn(function (this: Element) {
      scrolled.push(this);
    });
    render(<App />);
    await pickGu('서울', '강남구');
    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    fireEvent.click(await screen.findByRole('button', { name: /테스트빌딩/ }));
    await screen.findByRole('heading', { name: '테스트빌딩' });
    const roleBar = screen.getByRole('button', { name: '나는 역할 고르기' });
    expect(roleBar.textContent).toBe('나는 역할 고르기 ▾');
    fireEvent.click(roleBar);

    expect(scrolled).toEqual([cards()]);
    expect(document.activeElement).toBe(document.querySelector('section.rolecards .rolecards__card'));
    expect(document.activeElement?.textContent).toContain('투자·매입하려고');
    // @ts-expect-error — jsdom 원래 상태(없음)로 되돌린다.
    delete Element.prototype.scrollIntoView;
  });

  it('★ 의견함 문맥에 역할·둘러보기 값이 실리지 않는다', async () => {
    render(<App />);
    await screen.findByRole('button', { name: /^서울$/ });
    fireEvent.click(cardBtn(/가게를 열려고/));
    fireEvent.click(document.querySelector('.fb__open') as HTMLButtonElement);
    fireEvent.click(document.querySelector('.fb__kinds input') as HTMLInputElement);
    fireEvent.change(document.querySelector('.fb__input') as HTMLTextAreaElement, {
      target: { value: '시험 의견' },
    });
    fireEvent.click(screen.getByRole('button', { name: '보내기' }));
    await waitFor(() => expect(rpc.mock.calls.some(([fn]) => fn === 'submit_feedback')).toBe(true));
    const call = rpc.mock.calls.find(([fn]) => fn === 'submit_feedback')!;
    const ctx = JSON.stringify((call[1] as { p_context: unknown }).p_context);
    expect(ctx.length).toBeGreaterThan(2); // 양성 대조: 문맥은 실린다
    for (const v of ['창업자', '둘러보기', '가게를 열려고']) expect(ctx).not.toContain(v);
  });
});

/**
 * 창업자 입구(👤 결정 0036 결정 18 ④⑤⑨ · 물결 1-A2(ii)) — 이어 붙였을 때만 보이는 것:
 * 창업자면 상권 지도가 검색창 **위**로 오고 지도 제목 줄에 업종 칩이 선다 · 차례를 바꿔도 검색창·
 * 지도가 **다시 태어나지 않는다** · 칩은 저장하지 않고, 창업자에서 벗어나면 전체로 돌아간다 ·
 * 칩을 고른 채 건물을 열면 업종 분포 카드가 그 대분류를 미리 고른다.
 * 칩 줄 하나의 동작은 `FounderChips.test`, 카드 안쪽은 `IndustryMixSection.test`·`OpenCloseSection.test`.
 */
describe('App — 창업자 입구 · 업종 칩 (결정 0036 결정 18 ④⑤⑨)', () => {
  const KEY = 'sangga.viewerRole';
  afterEach(() => window.localStorage.clear());
  // 앞 시험이 주소에 남긴 구·건물을 지운다 — 남아 있으면 첫 그림부터 구가 골라져 있다.
  beforeEach(() => openWith(''));

  const roleBtn = (name: string) =>
    [...document.querySelectorAll('.role button')].find((b) => b.textContent === name) as HTMLButtonElement;
  const chipBtn = (name: string) =>
    [...document.querySelectorAll('.chips button')].find((b) => b.textContent === name) as HTMLButtonElement;
  const mapEl = () => document.querySelector('section.dmap');
  const searchEl = () => document.querySelector('section.search');
  /** 앞의 것이 문서에서 뒤의 것보다 먼저 나오나. */
  const before = (a: Element | null, b: Element | null) =>
    !!a && !!b && (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;

  it('★ 창업자면 지도가 검색창 위 · 지도 제목 줄에 칩 여섯(처음 = 전체) — 투자자는 지금 차례·칩 없음(양성 대조)', async () => {
    window.localStorage.setItem(KEY, '창업자');
    render(<App />);
    await pickGu('서울', '강남구');
    await waitFor(() => expect(mapEl()).not.toBeNull());
    expect(before(mapEl(), searchEl())).toBe(true);
    const chips = mapEl()!.querySelector('.dmap__head .chips');
    expect(chips).not.toBeNull();
    expect([...chips!.querySelectorAll('button')].map((b) => b.textContent)).toEqual([
      '카페',
      '한식',
      '미용',
      '학원',
      '편의점',
      '전체',
    ]);
    expect(chipBtn('전체').getAttribute('aria-pressed')).toBe('true');

    fireEvent.click(roleBtn('투자자'));
    expect(before(searchEl(), mapEl())).toBe(true);
    expect(document.querySelector('.chips')).toBeNull();
  });

  it('★ F4 창업자 칩 줄 곁에 안내 한 줄 — 투자자엔 없다(양성 대조)', async () => {
    const NOTE = '상권 목록과, 건물을 열면 업종 분포·개업·폐업 카드에 반영됩니다';
    window.localStorage.setItem(KEY, '창업자');
    render(<App />);
    await pickGu('서울', '강남구');
    await waitFor(() => expect(mapEl()).not.toBeNull());
    expect(screen.getByText(NOTE)).toBeTruthy();
    fireEvent.click(roleBtn('투자자'));
    expect(screen.queryByText(NOTE)).toBeNull();
  });

  it('역할 없음·중개사도 칩 없음 · 검색 → 지도', async () => {
    render(<App />);
    await pickGu('서울', '강남구');
    await waitFor(() => expect(mapEl()).not.toBeNull());
    expect(before(searchEl(), mapEl())).toBe(true);
    expect(document.querySelector('.chips')).toBeNull();
    fireEvent.click(roleBtn('중개사'));
    expect(before(searchEl(), mapEl())).toBe(true);
    expect(document.querySelector('.chips')).toBeNull();
  });

  it('구를 안 골라 지도가 안 그려지면 창업자여도 칩이 없다', async () => {
    window.localStorage.setItem(KEY, '창업자');
    render(<App />);
    await screen.findByRole('button', { name: /^서울$/ });
    expect(mapEl()).toBeNull();
    expect(document.querySelector('.chips')).toBeNull();
  });

  it('★ 역할을 바꿔 차례가 바뀌어도 검색창·지도는 다시 태어나지 않는다(검색어 그대로)', async () => {
    window.localStorage.setItem(KEY, '창업자');
    render(<App />);
    await pickGu('서울', '강남구');
    await waitFor(() => expect(mapEl()).not.toBeNull());
    const input = screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '스타' } });
    const map = mapEl();
    const search = searchEl();

    fireEvent.click(roleBtn('투자자'));
    // 같은 DOM 조각이 자리만 옮겼다 — 새로 만든 것이면 검색어가 비고 요소가 달라진다.
    expect(screen.getByLabelText('건물명 또는 주소')).toBe(input);
    expect(input.value).toBe('스타');
    expect(mapEl()).toBe(map);
    expect(searchEl()).toBe(search);

    fireEvent.click(roleBtn('창업자'));
    expect(screen.getByLabelText('건물명 또는 주소')).toBe(input);
    expect(mapEl()).toBe(map);
  });

  it('★ 칩은 저장하지 않고, 창업자에서 벗어났다 돌아오면 전체다', async () => {
    window.localStorage.setItem(KEY, '창업자');
    render(<App />);
    await pickGu('서울', '강남구');
    await waitFor(() => expect(mapEl()).not.toBeNull());
    const search = currentSearch();

    fireEvent.click(chipBtn('카페'));
    expect(chipBtn('카페').getAttribute('aria-pressed')).toBe('true');
    expect(chipBtn('전체').getAttribute('aria-pressed')).toBe('false');
    // 이 기기 저장에는 역할 하나뿐 · 주소도 그대로(결정 18 ⑨).
    expect(Object.keys(window.localStorage)).toEqual([KEY]);
    expect(currentSearch()).toBe(search);

    fireEvent.click(roleBtn('투자자'));
    fireEvent.click(roleBtn('창업자'));
    expect(chipBtn('전체').getAttribute('aria-pressed')).toBe('true');
    expect(chipBtn('카페').getAttribute('aria-pressed')).toBe('false');
  });

  it('★ 칩을 고른 채 건물을 열면 업종 분포 카드가 그 대분류를 미리 고르고, 칩을 바꾸면 따라간다 · 투자자로 바꾸면 풀린다', async () => {
    const base = rpc.getMockImplementation()!;
    rpc.mockImplementation((fn: string, args?: unknown) => {
      if (fn === 'list_industry_mix') {
        const cats = [
          { cd: 'I2', nm: '음식', n: 60 },
          { cd: 'S2', nm: '수리·개인', n: 10 },
        ];
        return Promise.resolve({
          data: { snapshot_ym: '202606', radius_m: 500, districts: [], radius: { total: 70, cats } },
          error: null,
        });
      }
      return base(fn, args);
    });
    window.localStorage.setItem(KEY, '창업자');
    render(<App />);
    await pickGu('서울', '강남구');
    await waitFor(() => expect(mapEl()).not.toBeNull());
    fireEvent.click(chipBtn('카페'));

    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    fireEvent.click(await screen.findByRole('button', { name: /테스트빌딩/ }));

    const select = (await screen.findByLabelText('업종 골라보기')) as HTMLSelectElement;
    expect(select.value).toBe('I2');

    // 건물 화면이 열린 채 칩을 바꾼다 — 첫 렌더 함정이면 옛 대분류가 남는다.
    // ⓘ 건물을 열면 입구가 접혀 지도(칩 줄)를 안 그린다(S1) — 바의 「상권 지도 보기」로 펼친다(칩 값은 App 이 쥐어 그대로).
    fireEvent.click(screen.getByRole('button', { name: '상권 지도 보기' }));
    expect(chipBtn('카페').getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(chipBtn('미용'));
    expect((screen.getByLabelText('업종 골라보기') as HTMLSelectElement).value).toBe('S2');

    fireEvent.click(roleBtn('투자자'));
    expect((screen.getByLabelText('업종 골라보기') as HTMLSelectElement).value).toBe('');
  });
});

/**
 * 탭 제목(👤 2026-10-09 검색·AI 노출 기본 세팅 J) — 건물을 고르면 그 이름, 풀면 첫 화면 제목.
 * 정본은 `lib/seo.ts`(첫 HTML `<title>` 과의 글자 대조는 `tests/test_seo_head.py`).
 */
describe('App — 탭 제목', () => {
  it('링크로 들어와 되살리는 동안에는 탭 제목을 건드리지 않는다(서버 조각이 넣은 건물 제목을 덮지 않게)', async () => {
    let release: ((r: { data: unknown; error: unknown }) => void) | null = null;
    const pending = new Promise<{ data: unknown; error: unknown }>((r) => {
      release = r;
    });
    from.mockImplementation((view: string) => {
      if (view === 'v_coverage_stats') return makeQuery({ data: [], error: null });
      const q: Record<string, unknown> = {};
      for (const m of ['select', 'eq', 'order', 'limit']) q[m] = () => q;
      q.then = (cb: (r: unknown) => unknown) => pending.then(cb);
      return q;
    });

    // 서버 조각(결정 0037)이 첫 HTML 에 넣어 둔 제목인 척.
    document.title = '테스트빌딩 — 강남구 테헤란로 1 | 상가 층별 스택뷰';
    openWith(`?sgg=11680&bld=${hit().bld_id}`);
    render(<App />);
    await screen.findByText('링크에 담긴 건물을 불러오는 중입니다…');
    expect(document.title).toBe('테스트빌딩 — 강남구 테헤란로 1 | 상가 층별 스택뷰');

    release!({ data: [floorRow()], error: null });
    await screen.findByRole('heading', { name: '테스트빌딩' });
    // 되살린 뒤의 제목은 서버와 같은 꼴(도로명에서 시·도를 뗀 것).
    expect(document.title).toBe('테스트빌딩 — 강남구 테헤란로 1 | 상가 층별 스택뷰');
  });

  it('건물을 고르면 "<이름> — <구 도로명> | 상가 층별 스택뷰", 선택을 풀면 첫 화면 제목으로 돌아온다', async () => {
    const { HOME_TITLE } = await import('./lib/seo');
    openWith('');
    render(<App />);
    await pickGu('서울', '강남구');
    expect(document.title).toBe(HOME_TITLE);

    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    fireEvent.click(await screen.findByRole('button', { name: /테스트빌딩/ }));
    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(document.title).toBe('테스트빌딩 — 강남구 테헤란로 1 | 상가 층별 스택뷰');

    // 새 검색을 걸면 선택이 풀린다 — 첫 화면 제목으로 돌아온다.
    fireEvent.change(input, { target: { value: '역삼' } });
    fireEvent.submit(input.closest('form')!);
    await waitFor(() => expect(document.title).toBe(HOME_TITLE));
  });
});

/**
 * 검색 색인 보강(결정 0042) — 이어 붙였을 때만 보이는 것: h1 은 늘 하나(첫 화면 = 사이트 이름 · 건물 = 건물 이름) ·
 * 지역 고르개 구 칩 = 진짜 링크(열린 구 전부 · 보통 누름은 화면 안) · 같은 땅 여러 동이면 동 목록을 한 번 받아
 * 탭 제목에 동 구분 + 층별 머리에 다른 동·구 링크(누르면 화면 안에서).
 */
describe('App — 검색 색인 보강 (결정 0042)', () => {
  const PNU = '1168010100100010000';
  const SELF = `${PNU}_1024110`;
  const OTHER = `${PNU}_1024999`;
  const DONGS = [
    { bld_id: SELF, bld_nm: '테스트빌딩', dong_nm: 'A동', total_area_m2: 900, floor_cnt: 3, min_floor: 1, max_floor: 3, has_roof: false },
    { bld_id: OTHER, bld_nm: '테스트빌딩', dong_nm: 'B동', total_area_m2: 500, floor_cnt: 2, min_floor: 1, max_floor: 2, has_roof: false },
  ];

  function twoDongs() {
    from.mockImplementation((view: string) =>
      makeQuery(view === 'v_coverage_stats' ? { data: [], error: null } : { data: [floorRow({ bld_cnt_in_pnu: 2 })], error: null }),
    );
    const base = rpc.getMockImplementation()!;
    rpc.mockImplementation((fn: string, args?: unknown) =>
      fn === 'list_parcel_buildings' ? Promise.resolve({ data: DONGS, error: null }) : base(fn, args),
    );
  }

  it('첫 화면 — h1 은 사이트 이름 하나 · 구 칩은 열린 구 수만큼 진짜 링크 · 보통 누름은 화면 안에서 고르기', async () => {
    openWith('');
    render(<App />);
    await screen.findByRole('button', { name: '서울' });
    expect(screen.getAllByRole('heading', { level: 1 }).map((h) => h.textContent)).toEqual(['상가 층별 스택뷰']);
    const links = [...document.querySelectorAll<HTMLAnchorElement>('a[href^="/?sgg="]')];
    expect(links.map((a) => a.getAttribute('href')).sort()).toEqual(['/?sgg=11680', '/?sgg=30170']);
    await pickGu('서울', '강남구');
    expect(currentSearch()).toBe('?sgg=11680');
  });

  it('★ 같은 땅 두 동 — 동 목록 한 번 · 탭 제목에 동 구분(첫 HTML 과 같은 꼴) · h1 = 건물 이름 하나 · 다른 동·구 링크', async () => {
    twoDongs();
    openWith(`?sgg=11680&bld=${SELF}`);
    render(<App />);
    await screen.findByRole('heading', { level: 1, name: '테스트빌딩' });
    await waitFor(() => expect(document.title).toBe('테스트빌딩 A동 — 강남구 테헤란로 1 | 상가 층별 스택뷰'));
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(document.querySelector('p.app__title')!.textContent).toBe('상가 층별 스택뷰');

    const nav = await waitFor(() => {
      const n = document.querySelector('nav.stack__links');
      expect(n!.textContent).toContain('강남구 다른 건물 찾기');
      return n!;
    });
    const hrefs = [...nav.querySelectorAll('a')].map((a) => [a.getAttribute('href'), a.textContent]);
    expect(hrefs).toEqual([
      [`/?sgg=11680&bld=${OTHER}`, '테스트빌딩 B동'],
      ['/?sgg=11680', '강남구 다른 건물 찾기'],
    ]);
    expect(nav.textContent!.startsWith('같은 땅 다른 동: ')).toBe(true);
    expect(rpc.mock.calls.filter((c) => c[0] === 'list_parcel_buildings')).toEqual([['list_parcel_buildings', { p_pnu: PNU }]]);

    // 보통 누름 = 화면 안에서 그 동으로(주소가 따라 적힌다) · 같은 땅이라 동 목록은 다시 안 묻는다.
    const go = nav.querySelector<HTMLAnchorElement>(`a[href$="${OTHER}"]`)!;
    expect(fireEvent.click(go)).toBe(false); // preventDefault
    await waitFor(() => expect(currentSearch()).toContain(`bld=${OTHER}`));
    await waitFor(() => expect(document.title).toBe('테스트빌딩 B동 — 강남구 테헤란로 1 | 상가 층별 스택뷰'));
    expect(rpc.mock.calls.filter((c) => c[0] === 'list_parcel_buildings')).toHaveLength(1);
  });

  it('「○○구 다른 건물 찾기」 보통 누름 = 위 칸을 펼치고 입력칸에 커서(보던 건물은 그대로) · Ctrl 누름은 링크 그대로', async () => {
    twoDongs();
    openWith(`?sgg=11680&bld=${SELF}`);
    render(<App />);
    const find = await screen.findByRole('link', { name: '강남구 다른 건물 찾기' });
    expect(fireEvent.click(find, { ctrlKey: true })).toBe(true); // 가로채지 않는다(새 탭은 브라우저 몫)
    expect((document.getElementById('entry-panel') as HTMLElement).hidden).toBe(true);
    expect(fireEvent.click(find)).toBe(false);
    await waitFor(() => expect((document.getElementById('entry-panel') as HTMLElement).hidden).toBe(false));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText('건물명 또는 주소')));
    expect(currentSearch()).toContain(`bld=${SELF}`);
  });

  it('동 목록이 실패하면 동 구분·다른 동 줄 없이 지금 화면 그대로', async () => {
    twoDongs();
    const base = rpc.getMockImplementation()!;
    const err = console.error;
    console.error = () => {};
    rpc.mockImplementation((fn: string, args?: unknown) =>
      fn === 'list_parcel_buildings' ? Promise.resolve({ data: null, error: { message: 'x' } }) : base(fn, args),
    );
    try {
      openWith(`?sgg=11680&bld=${SELF}`);
      render(<App />);
      await screen.findByRole('link', { name: '강남구 다른 건물 찾기' });
      expect(document.title).toBe('테스트빌딩 — 강남구 테헤란로 1 | 상가 층별 스택뷰');
      expect(document.querySelector('nav.stack__links')!.textContent).not.toContain('같은 땅 다른 동');
    } finally {
      console.error = err;
    }
  });
});

/**
 * 중개사 「최근 뽑은 건물」(👤 결정 0036 결정 18 ⑥⑩ · 물결 1-A2(iii)) — 이어 붙였을 때만 보이는 것:
 * 인쇄 단추가 적는다(중개사일 때만) · 검색 덩어리 아래 접힌 줄(중개사만) · 누르면 그 건물로(다른 구면
 * 구도) · 지우기 · 주소·의견함에 안 실린다 · 막힌 창에서도 인쇄는 된다.
 * 저장 규칙은 `lib/recentPrintedStore.test`, 줄 하나의 그리기는 `RecentPrinted.test`.
 */
describe('App — 중개사 최근 뽑은 건물 (결정 0036 결정 18 ⑥⑩)', () => {
  const KEY = 'sangga.viewerRole';
  const RKEY = 'sangga.recentPrinted';
  afterEach(() => window.localStorage.clear());
  beforeEach(() => openWith(''));

  const recentEl = () => document.querySelector('section.recent');
  const toggle = () => screen.getByRole('button', { name: /최근 뽑은 건물/ });
  const roleBtn = (name: string) =>
    [...document.querySelectorAll('.role button')].find((b) => b.textContent === name) as HTMLButtonElement;
  const printBtn = () => screen.getByRole('button', { name: '인쇄 · PDF로 저장' });

  function stored(...rows: Array<Partial<BuildingHit>>) {
    window.localStorage.setItem(
      RKEY,
      JSON.stringify(
        rows.map((over) => {
          const { total_cnt: _t, ...rest } = hit(over);
          void _t;
          return rest;
        }),
      ),
    );
  }

  async function openLinked() {
    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);
    await screen.findByRole('heading', { name: '테스트빌딩' });
    // 최근 줄은 검색창 안이다 — 건물을 열면 입구가 접히므로(S1) 펼쳐서 본다.
    unfoldEntry();
  }

  it('★ 중개사가 인쇄 단추를 누르면 인쇄 창 전에 적히고, 검색 입력칸 바로 아래에 접힌 줄이 선다 · 주소는 그대로', async () => {
    window.localStorage.setItem(KEY, '중개사');
    let atPrint: string | null = null;
    const print = vi.spyOn(window, 'print').mockImplementation(() => {
      atPrint = window.localStorage.getItem(RKEY);
    });
    try {
      await openLinked();
      expect(recentEl()).toBeNull(); // 처음엔 목록이 비어 줄이 없다
      const before = currentSearch();
      fireEvent.click(printBtn());
      expect(print).toHaveBeenCalledTimes(1);
      expect(JSON.parse(atPrint ?? '[]').map((r: BuildingHit) => r.bld_id)).toEqual([LINK_BLD]);
      expect(toggle().textContent).toContain('최근 뽑은 건물 1');
      expect(toggle().getAttribute('aria-expanded')).toBe('false');
      // 검색 입력칸 바로 아래(같은 `.search` 안 · 폼 바로 뒤) — 차례는 아래 시험이 결과 목록과 함께 본다.
      expect(document.querySelector('section.search form')?.nextElementSibling).toBe(recentEl());
      // ⛔ 주소에 안 실린다.
      expect(currentSearch()).toBe(before);
      expect(Object.keys(window.localStorage).sort()).toEqual([RKEY, KEY].sort());
    } finally {
      print.mockRestore();
    }
  });

  it('★ 투자자·역할 없음은 인쇄해도 적지 않고 줄도 없다 — 양성 대조: 중개사로 바꾸면 이미 있던 목록이 선다', async () => {
    stored({ bld_id: '1168010100100020000_1', pnu: '1168010100100020000', bld_nm: '옛빌딩' });
    window.localStorage.setItem(KEY, '투자자');
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    try {
      await openLinked();
      fireEvent.click(printBtn());
      expect(print).toHaveBeenCalledTimes(1);
      expect(recentEl()).toBeNull();
      expect(JSON.parse(window.localStorage.getItem(RKEY)!)).toHaveLength(1); // 안 쌓였다

      fireEvent.click(roleBtn('투자자')); // 다시 누르면 역할 없음
      fireEvent.click(printBtn());
      expect(recentEl()).toBeNull();
      expect(JSON.parse(window.localStorage.getItem(RKEY)!)).toHaveLength(1);

      fireEvent.click(roleBtn('중개사'));
      expect(toggle().textContent).toContain('최근 뽑은 건물 1');
    } finally {
      print.mockRestore();
    }
  });

  it('★ 펼쳐 누르면 그 건물 층별 화면으로 간다 (같은 구)', async () => {
    const other = '1168010100100020000_777';
    stored({ bld_id: other, pnu: '1168010100100020000', bld_nm: '옆빌딩' });
    window.localStorage.setItem(KEY, '중개사');
    await openLinked();
    fireEvent.click(toggle());
    fireEvent.click(screen.getByRole('button', { name: /옆빌딩/ }));
    await waitFor(() => expect(currentSearch()).toContain(`bld=${other}`));
    expect(currentSearch()).toContain('sgg=11680');
    expect(document.querySelector('.stack')).not.toBeNull();
    // 펼친 채(openLinked) 같은 구의 최근 건물을 고르면 다시 한 줄로 접힌다(S1 · 검사 🟡 10-15).
    expect((document.querySelector('.entry') as HTMLElement).hidden).toBe(true);
    expect(document.querySelector('.entrybar:not(.entrybar--open)')).not.toBeNull();
  });

  it('★ 다른 구 건물이면 구도 그 구로 바뀐다 (구 코드 = 저장한 pnu 앞 5자리)', async () => {
    const dj = '3017010100100010000_5';
    stored({ bld_id: dj, pnu: '3017010100100010000', bld_nm: '대전빌딩', road_addr: '대전 서구 둔산로 1' });
    window.localStorage.setItem(KEY, '중개사');
    await openLinked();
    fireEvent.click(toggle());
    fireEvent.click(screen.getByRole('button', { name: /대전빌딩/ }));
    await waitFor(() => expect(currentSearch()).toContain('sgg=30170'));
    expect(currentSearch()).toContain(`bld=${dj}`);
    expect(currentSearch()).not.toContain('sgg=11680');
    // 구 이름은 지역 고르개가 서버 목록에서 채운다 — 건물을 고르면 입구가 접히므로(S1) 바의 지금 구로 본다.
    await waitFor(() => expect(document.querySelector('.entrybar__place')?.textContent).toBe('대전 서구'));
  });

  it('★ 자리 = 검색 입력칸 → 최근 줄 → 결과 목록 차례 · 구를 바꿔 검색창이 다시 태어나도 목록은 그대로', async () => {
    stored({ bld_id: '1168010100100020000_1', pnu: '1168010100100020000', bld_nm: '옛빌딩' });
    window.localStorage.setItem(KEY, '중개사');
    render(<App />);
    await pickGu('서울', '강남구');
    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    await screen.findByRole('button', { name: /테스트빌딩/ });
    const hits = document.querySelector('ul.hits');
    const follows = (a: Element | null, b: Element | null) =>
      !!a && !!b && (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
    expect(follows(input, recentEl())).toBe(true);
    expect(follows(recentEl(), hits)).toBe(true);
    // 양성 대조: 결과 목록은 정말 최근 줄 **뒤**다(거꾸로면 거짓).
    expect(follows(hits, recentEl())).toBe(false);

    await pickGu('대전', '서구');
    expect(toggle().textContent).toContain('최근 뽑은 건물 1');
  });

  it('★ 소유 구조 줄은 중개사 검색 결과에만 — 투자자·창업자·역할 없음에는 없다(양성·반대 짝)', async () => {
    const base = rpc.getMockImplementation()!;
    rpc.mockImplementation((fn: string, args?: unknown) =>
      fn === 'search_buildings'
        ? Promise.resolve({
            data: [hit({ is_jiphap: true, approve_date: '2003-05-14', parking_cnt: 120 })],
            error: null,
          })
        : base(fn, args),
    );
    async function ownLine(role: string | null) {
      window.localStorage.clear();
      // 역할 없음 = '물어봤음' 기본값(맨 위 beforeEach 와 같은 뜻 — 결정 0039 W3 큰 카드가 서지 않게).
      window.localStorage.setItem(KEY, role ?? '둘러보기');
      openWith('');
      render(<App />);
      await pickGu('서울', '강남구');
      const input = screen.getByLabelText('건물명 또는 주소');
      fireEvent.change(input, { target: { value: '테헤란로' } });
      fireEvent.submit(input.closest('form')!);
      await screen.findByRole('button', { name: /테스트빌딩/ });
      const text = document.querySelector('.hit .hit__own')?.textContent ?? null;
      cleanup();
      return text;
    }
    expect(await ownLine('중개사')).toBe('집합건물 · 사용승인 2003년 5월 · 주차 120대');
    for (const role of ['투자자', '창업자', null]) {
      expect(await ownLine(role), String(role)).toBeNull();
    }
  });

  it('★ 링크를 되살리는 도중 최근 목록을 누르면, 뒤늦게 온 되살리기 결과가 그 선택을 덮지 않는다', async () => {
    const other = '1168010100100020000_777';
    stored({ bld_id: other, pnu: '1168010100100020000', bld_nm: '옆빌딩' });
    window.localStorage.setItem(KEY, '중개사');
    let release: ((r: { data: unknown; error: unknown }) => void) | null = null;
    const pending = new Promise<{ data: unknown; error: unknown }>((r) => {
      release = r;
    });
    from.mockImplementation((view: string) => {
      if (view === 'v_coverage_stats') return makeQuery({ data: [], error: null });
      const q: Record<string, unknown> = {};
      for (const m of ['select', 'eq', 'order', 'limit']) q[m] = () => q;
      q.then = (cb: (r: unknown) => unknown) => pending.then(cb);
      return q;
    });
    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);
    await screen.findByText('링크에 담긴 건물을 불러오는 중입니다…');
    unfoldEntry(); // 되살리는 동안도 입구는 접혀 있다(검사 🟡 10-15)
    fireEvent.click(toggle());
    fireEvent.click(screen.getByRole('button', { name: /옆빌딩/ }));

    await act(async () => {
      release!({ data: [floorRow()], error: null });
      await pending;
    });
    await waitFor(() => expect(currentSearch()).toContain(`bld=${other}`));
    expect(currentSearch()).not.toContain(`bld=${LINK_BLD}`);
  });

  it('★ 되살리기에 실패한 뒤 최근 목록으로 고르면 실패 상태가 풀린다(새 검색 뒤 실패 안내가 되살아나지 않는다)', async () => {
    const other = '1168010100100020000_777';
    stored({ bld_id: other, pnu: '1168010100100020000', bld_nm: '옆빌딩' });
    window.localStorage.setItem(KEY, '중개사');
    from.mockImplementation((view: string) =>
      makeQuery(view === 'v_coverage_stats' ? { data: [], error: null } : { data: [], error: null }),
    );
    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);
    await screen.findByText(/링크에 담긴 건물을 찾지 못했습니다/); // 양성 대조: 실패 상태로 시작
    fireEvent.click(toggle());
    fireEvent.click(screen.getByRole('button', { name: /옆빌딩/ }));
    await waitFor(() => expect(currentSearch()).toContain(`bld=${other}`));

    // 새 검색 = 선택 해제. 실패 상태가 남아 있으면 여기서 '찾지 못했습니다'가 다시 뜬다.
    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    await screen.findByText('위에서 건물을 검색해 선택해 주세요.');
    expect(screen.queryByText(/링크에 담긴 건물을 찾지 못했습니다/)).toBeNull();
  });

  it('「지우기」는 저장소에서도 지우고 줄이 사라진다', async () => {
    stored({ bld_id: '1168010100100020000_1', pnu: '1168010100100020000', bld_nm: '옛빌딩' });
    window.localStorage.setItem(KEY, '중개사');
    await openLinked();
    fireEvent.click(toggle());
    // 중개사면 사무소 칸(물결 1-C2)에도 「지우기」가 있다 — 최근 줄 안의 것을 누른다.
    fireEvent.click(recentEl()!.querySelector('.recent__clear') as HTMLButtonElement);
    expect(recentEl()).toBeNull();
    expect(window.localStorage.getItem(RKEY)).toBeNull();
  });

  it('★ 의견함 문맥에 목록이 실리지 않는다', async () => {
    stored({ bld_id: '1168010100100020000_1', pnu: '1168010100100020000', bld_nm: '옛빌딩' });
    window.localStorage.setItem(KEY, '중개사');
    await openLinked();
    expect(recentEl()).not.toBeNull(); // 양성 대조: 목록은 있다
    fireEvent.click(document.querySelector('.fb__open') as HTMLButtonElement);
    fireEvent.click(document.querySelector('.fb__kinds input') as HTMLInputElement);
    fireEvent.change(document.querySelector('.fb__input') as HTMLTextAreaElement, {
      target: { value: '시험 의견' },
    });
    fireEvent.click(screen.getByRole('button', { name: '보내기' }));
    await waitFor(() => expect(rpc.mock.calls.some(([fn]) => fn === 'submit_feedback')).toBe(true));
    const call = rpc.mock.calls.find(([fn]) => fn === 'submit_feedback')!;
    const ctx = JSON.stringify((call[1] as { p_context: unknown }).p_context);
    expect(ctx).toContain(LINK_BLD); // 양성 대조: 보던 건물은 실린다
    expect(ctx).not.toContain('옛빌딩');
    expect(ctx).not.toContain('1168010100100020000_1');
  });

  it('★ 저장이 막힌 창 — 인쇄는 되고 오류 없이 줄만 안 선다', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    try {
      await openLinked();
      fireEvent.click(roleBtn('중개사'));
      fireEvent.click(printBtn());
      expect(print).toHaveBeenCalledTimes(1);
      expect(setItem).toHaveBeenCalled();
      expect(recentEl()).toBeNull();
      expect(screen.getByRole('heading', { name: '테스트빌딩' })).toBeTruthy();
    } finally {
      setItem.mockRestore();
      getItem.mockRestore();
      print.mockRestore();
    }
  });
});

/**
 * 인쇄 한 장 보강(👤 결정 0036 결정 3·8 · 물결 1-C2) — 이어 붙였을 때만 보이는 것:
 * 사무소 칸은 중개사만 · 이 기기에만 저장(주소·의견함 0) · 종이 머리 상자는 중개사 + 채운 칸만 ·
 * 호실 구성표 고르기는 누구에게나 · 건물이 바뀌면 기본으로 · 고른 층만 목록을 부른다.
 * 저장 규칙은 `lib/brokerOfficeStore.test`, 층 고르기는 `lib/unitPrint.test`, 종이 모양은 E2E.
 */
describe('App — 인쇄 한 장 보강 (결정 0036 결정 3·8 · 물결 1-C2)', () => {
  const KEY = 'sangga.viewerRole';
  const OKEY = 'sangga.brokerOffice';
  afterEach(() => window.localStorage.clear());
  beforeEach(() => openWith(''));

  const roleBtn = (name: string) =>
    [...document.querySelectorAll('.role button')].find((b) => b.textContent === name) as HTMLButtonElement;
  const officeBox = () => document.querySelector('.printmeta__office');

  async function openLinked() {
    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);
    await screen.findByRole('heading', { name: '테스트빌딩' });
  }

  it('★ 사무소 칸은 중개사만 — 적으면 이 기기에 저장되고 종이 머리 상자에 채운 칸만 · 다른 역할이면 상자 없음(저장은 그대로)', async () => {
    window.localStorage.setItem(KEY, '중개사');
    await openLinked();
    expect(document.querySelector('.office')).not.toBeNull();
    expect(officeBox()).toBeNull(); // 빈 칸뿐이면 상자 없음
    const toggleText = () => document.querySelector('.office__toggle')?.textContent;
    expect(toggleText()).toBe('종이에 찍을 내 사무소 정보');
    expect(document.querySelector('.office')?.textContent).toContain('이 기기에만 저장 · 서버로 보내지 않음');
    expect(document.querySelector('.office')?.textContent).toContain(
      '여럿이 함께 쓰는 컴퓨터라면 다 쓴 뒤 지우기를 눌러 주세요',
    );

    fireEvent.change(screen.getByLabelText('사무소 이름'), { target: { value: '역삼공인중개사' } });
    fireEvent.change(screen.getByLabelText('전화'), { target: { value: '02-0000-0000' } });
    expect(toggleText()).toBe('종이에 찍을 내 사무소 정보 — 채워짐(역삼공인중개사)');
    expect(JSON.parse(window.localStorage.getItem(OKEY)!)).toMatchObject({
      name: '역삼공인중개사',
      phone: '02-0000-0000',
    });
    expect([...officeBox()!.querySelectorAll('p')].map((p) => p.textContent)).toEqual([
      '역삼공인중개사',
      '전화 02-0000-0000',
    ]);
    // ⛔ 주소에 안 실린다.
    expect(currentSearch()).not.toContain('역삼공인중개사');

    // 투자자로 바꾸면 칸도 상자도 없다 — 저장은 지우지 않는다(양성 대조: 다시 중개사면 되살아난다).
    fireEvent.click(roleBtn('투자자'));
    expect(document.querySelector('.office')).toBeNull();
    expect(officeBox()).toBeNull();
    expect(window.localStorage.getItem(OKEY)).not.toBeNull();
    fireEvent.click(roleBtn('중개사'));
    expect(officeBox()?.textContent).toContain('역삼공인중개사');
  });

  it('★ 저장해 둔 칸으로 첫 그림부터 · 「지우기」는 저장소에서도 지우고 상자가 사라진다', async () => {
    window.localStorage.setItem(KEY, '중개사');
    window.localStorage.setItem(
      OKEY,
      JSON.stringify({ name: '역삼', rep: '홍길동', regNo: '', phone: '', memo: '' }),
    );
    await openLinked();
    expect(officeBox()?.textContent).toBe('역삼대표 홍길동');
    // 이름을 지워도 다른 칸이 차 있으면 '채워짐'(이름 없이).
    fireEvent.change(screen.getByLabelText('사무소 이름'), { target: { value: '' } });
    expect(document.querySelector('.office__toggle')?.textContent).toBe('종이에 찍을 내 사무소 정보 — 채워짐');
    fireEvent.click(document.querySelector('.office__clear') as HTMLButtonElement);
    expect(window.localStorage.getItem(OKEY)).toBeNull();
    expect(officeBox()).toBeNull();
    expect((screen.getByLabelText('사무소 이름') as HTMLInputElement).value).toBe('');
  });

  it('★ 의견함 문맥에 사무소 칸이 실리지 않는다', async () => {
    window.localStorage.setItem(KEY, '중개사');
    window.localStorage.setItem(
      OKEY,
      JSON.stringify({ name: '비밀사무소', rep: '김대표', regNo: '', phone: '010-0000-0000', memo: '' }),
    );
    await openLinked();
    expect(officeBox()).not.toBeNull(); // 양성 대조: 칸은 채워져 있다
    fireEvent.click(document.querySelector('.fb__open') as HTMLButtonElement);
    fireEvent.click(document.querySelector('.fb__kinds input') as HTMLInputElement);
    fireEvent.change(document.querySelector('.fb__input') as HTMLTextAreaElement, {
      target: { value: '시험 의견' },
    });
    fireEvent.click(screen.getByRole('button', { name: '보내기' }));
    await waitFor(() => expect(rpc.mock.calls.some(([fn]) => fn === 'submit_feedback')).toBe(true));
    const call = rpc.mock.calls.find(([fn]) => fn === 'submit_feedback')!;
    const ctx = JSON.stringify((call[1] as { p_context: unknown }).p_context);
    expect(ctx).toContain(LINK_BLD); // 양성 대조: 보던 건물은 실린다
    for (const v of ['비밀사무소', '김대표', '010-0000-0000']) expect(ctx).not.toContain(v);
  });

  it('★ 저장이 막힌 창 — 입력·종이 상자는 그대로 되고 오류가 없다', async () => {
    window.localStorage.setItem(KEY, '중개사');
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    try {
      await openLinked();
      fireEvent.change(screen.getByLabelText('사무소 이름'), { target: { value: '역삼' } });
      expect(setItem).toHaveBeenCalled();
      expect(officeBox()?.textContent).toBe('역삼');
    } finally {
      setItem.mockRestore();
    }
  });

  it('★ 호실 구성표 고르기는 누구에게나 · 기본 = 지하~3층(곧장 그 층을 부른다) · 다른 건물에 갔다 와도 기본으로', async () => {
    const base = rpc.getMockImplementation()!;
    const other = hit({ bld_id: '1168010100100020000_9', pnu: '1168010100100020000', bld_nm: '옆빌딩' });
    rpc.mockImplementation((fn: string, args?: unknown) => {
      if (fn === 'list_unit_floor_summary') {
        return Promise.resolve({
          data: [
            {
              floor_no: 1,
              unit_cnt: 2,
              median_area_m2: 10,
              min_area_m2: 9,
              max_area_m2: 11,
              floor_kind: 'commercial',
            },
          ],
          error: null,
        });
      }
      if (fn === 'list_floor_units') {
        return Promise.resolve({
          data: [
            { ho: '101호', excl_area_m2: 10, total_cnt: 2 },
            { ho: '102호', excl_area_m2: 11, total_cnt: 2 },
          ],
          error: null,
        });
      }
      if (fn === 'search_buildings') return Promise.resolve({ data: [other, hit()], error: null });
      return base(fn, args);
    });
    await openLinked(); // 역할 없음
    const radio = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
    await screen.findByLabelText('지하~3층');
    expect(radio('지하~3층').checked).toBe(true);
    await waitFor(() => expect(document.querySelectorAll('.floor__unitprint-list li')).toHaveLength(2));
    const asked = rpc.mock.calls.filter(([fn]) => fn === 'list_floor_units').map(([, a]) => a);
    expect(asked[0]).toEqual({ p_bld_id: LINK_BLD, p_floor_no: 1, p_limit: 50, p_offset: 0 });
    // ⛔ 주소·저장소에 안 실린다.
    expect(currentSearch()).toBe(`?sgg=11680&bld=${LINK_BLD}`);
    // 저장소에는 맨 위 beforeEach 가 넣은 '물어봤음' 역할 값 하나뿐(결정 0039 W3) — 고르기 값은 안 실린다.
    expect(Object.keys(window.localStorage)).toEqual([KEY]);

    // '넣지 않음'은 선택지로 남는다.
    fireEvent.click(radio('넣지 않음'));
    await waitFor(() => expect(document.querySelectorAll('.floor__unitprint-list li')).toHaveLength(0));

    // 옆 건물 → 다시 이 건물 — 돌아와도 옛 고르기('넣지 않음')가 아니라 기본(지하~3층)이다.
    const goTo = async (name: RegExp, bld: string) => {
      const input = screen.getByLabelText('건물명 또는 주소');
      fireEvent.change(input, { target: { value: '테헤란로' } });
      fireEvent.submit(input.closest('form')!);
      fireEvent.click(await screen.findByRole('button', { name }));
      await waitFor(() => expect(currentSearch()).toContain(`bld=${bld}`));
      await screen.findByLabelText('지하~3층');
    };
    await goTo(/옆빌딩/, '1168010100100020000_9');
    expect(radio('지하~3층').checked).toBe(true);
    await goTo(/테스트빌딩/, LINK_BLD);
    expect(radio('지하~3층').checked).toBe(true);
    await waitFor(() => expect(document.querySelectorAll('.floor__unitprint-list li')).toHaveLength(2));
  });

  it('★ 호 목록이 있는 층이 0개인 건물이면 고르기 줄이 없고 목록 요청도 0', async () => {
    // 기본 흉내는 요약에 빈 배열을 준다(= 호실 자료가 없는 건물).
    await openLinked();
    await waitFor(() => expect(rpc.mock.calls.some(([fn]) => fn === 'list_unit_floor_summary')).toBe(true));
    await new Promise((r) => setTimeout(r, 0));
    expect(document.querySelector('.unitpick')).toBeNull();
    expect(rpc.mock.calls.some(([fn]) => fn === 'list_floor_units')).toBe(false);
  });
});

/**
 * 입구 접기(S1 · 👤 2026-10-14·15). 건물을 연 동안 위 덩어리를 한 줄 바로 접고, 바에서 펼치면 그 자리로 간다.
 * 여기서 보는 것 = 여러 조각을 이어 붙였을 때만 드러나는 것(접힘·펼침·새 건물에 다시 접힘·검색어 보존·
 * 지도는 접힌 동안 안 그림). 실제 배치(첫 화면 높이 안에 건물 이름)는 E2E 가 본다.
 */
describe('App — 입구 접기 (S1)', () => {
  const KEY = 'sangga.viewerRole';
  afterEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });
  beforeEach(() => openWith(''));

  const bar = () => document.querySelector('.entrybar:not(.entrybar--open)');
  const entry = () => document.querySelector('.entry') as HTMLElement;
  const barBtn = (name: RegExp | string) => screen.getByRole('button', { name });

  async function openBuildingBySearch() {
    render(<App />);
    await pickGu('서울', '강남구');
    const input = screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    fireEvent.click(await screen.findByRole('button', { name: /테스트빌딩/ }));
    await screen.findByRole('heading', { name: '테스트빌딩' });
    return input;
  }

  it('★ 건물이 없으면 바 없이 지금 화면 그대로 — 건물을 열면 위 덩어리가 접히고 한 줄 바가 선다', async () => {
    render(<App />);
    await pickGu('서울', '강남구');
    expect(bar()).toBeNull();
    expect(entry().hidden).toBe(false);
    expect(document.querySelector('.app--folded')).toBeNull();
    expect(document.querySelector('section.dmap')).not.toBeNull();
    cleanup();
    openWith(''); // 앞 그림이 주소에 적은 구를 지운다(첫 그림 한 번만 주소를 읽는다).

    await openBuildingBySearch();
    expect(bar()).not.toBeNull();
    expect(entry().hidden).toBe(true);
    expect(document.querySelector('.app--folded')).not.toBeNull();
    // 바 내용 — 지금 구(서버가 준 이름 + 짧은 이름표) · 단추 셋(역할 없음 = '역할 고르기'). 보이는 글자 그대로.
    expect(bar()!.querySelector('.entrybar__place')!.textContent).toBe('서울 강남구');
    expect([...bar()!.querySelectorAll('button')].map((b) => b.textContent)).toEqual([
      '← 다른 건물 찾기',
      '상권 지도 보기',
      '나는 역할 고르기 ▾',
    ]);
    // 낭독기에는 기호 없이 읽힌다 · 펼침 상태(닫힘)와 무엇을 펼치는지(위 칸)를 알린다.
    expect(entry().id).toBe('entry-panel');
    for (const name of ['다른 건물 찾기', '상권 지도 보기', '나는 역할 고르기']) {
      const btn = barBtn(name);
      expect(btn.getAttribute('aria-expanded')).toBe('false');
      expect(btn.getAttribute('aria-controls')).toBe('entry-panel');
    }
    // 건물을 고르면 커서는 바의 첫 단추로(고른 결과 줄이 숨어 커서가 문서 맨 앞으로 날아가지 않게).
    expect(document.activeElement).toBe(barBtn('다른 건물 찾기'));
    // 지도는 접힌 동안 그리지 않는다(종이에도 안 나온다 — 👤 10-15).
    expect(document.querySelector('section.dmap')).toBeNull();
    // 사이트 이름은 그대로 있다(크기만 CSS 가 줄인다) — 단 건물을 연 동안은 h1 이 아니라 p(결정 0042 H1 · h1 = 건물 이름 하나).
    expect(document.querySelector('p.app__title')!.textContent).toBe('상가 층별 스택뷰');
    expect(screen.getAllByRole('heading', { level: 1 }).map((h) => h.textContent)).toEqual(['테스트빌딩']);
  });

  it('★ 「다른 건물 찾기」= 위 덩어리만 펼치고 입력칸에 커서 · 검색어·결과·보던 건물 그대로 · 새 건물을 고르면 다시 접힌다', async () => {
    const input = await openBuildingBySearch();
    fireEvent.click(barBtn('다른 건물 찾기'));

    expect(entry().hidden).toBe(false);
    expect(bar()).toBeNull();
    // 같은 입력칸이 그대로(다시 태어나지 않았다) · 검색어 그대로 · 커서가 거기.
    expect(screen.getByLabelText('건물명 또는 주소')).toBe(input);
    expect(input.value).toBe('테헤란로');
    expect(document.activeElement).toBe(input);
    // 검색 결과도 그대로 · 보던 건물도 아래 그대로.
    expect(screen.getByRole('button', { name: /테헤란로 1/ })).toBeTruthy();
    expect(screen.getByRole('heading', { name: '테스트빌딩' })).toBeTruthy();
    // 「위 칸 접기」는 바가 있던 자리 = 펼친 덩어리 **맨 위**(위를 보는 사람이 찾게) · 펼침 상태(열림)를 알린다.
    const fold = barBtn('위 칸 접기');
    expect(fold.textContent).toBe('▲ 위 칸 접기');
    expect(fold.getAttribute('aria-expanded')).toBe('true');
    expect(fold.getAttribute('aria-controls')).toBe('entry-panel');
    expect(fold.compareDocumentPosition(entry()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // 결과에서 건물을 고르면 다시 한 줄로 · 커서는 바의 첫 단추.
    fireEvent.click(screen.getByRole('button', { name: /테헤란로 1/ }));
    expect(entry().hidden).toBe(true);
    expect(bar()).not.toBeNull();
    expect(screen.queryByRole('button', { name: '위 칸 접기' })).toBeNull();
    expect(document.activeElement).toBe(barBtn('다른 건물 찾기'));
  });

  it('★ 「상권 지도 보기」= 펼치고 지도로 옮기며 지도 머리에 커서(지도는 새로 그린다) · 「위 칸 접기」로 접으면 지도는 빠지고 검색어는 남고 커서는 바로', async () => {
    const scrolled: Element[] = [];
    Element.prototype.scrollIntoView = vi.fn(function (this: Element) {
      scrolled.push(this);
    });
    const input = await openBuildingBySearch();
    fireEvent.click(barBtn('상권 지도 보기'));

    expect(entry().hidden).toBe(false);
    const map = document.querySelector('section.dmap');
    expect(map).not.toBeNull();
    expect(scrolled).toEqual([map]);
    expect(document.activeElement).toBe(map!.querySelector('.dmap__toggle'));

    fireEvent.click(barBtn('위 칸 접기'));
    expect(entry().hidden).toBe(true);
    expect(document.querySelector('section.dmap')).toBeNull();
    expect(screen.getByLabelText('건물명 또는 주소')).toBe(input);
    expect(input.value).toBe('테헤란로');
    expect(document.activeElement).toBe(barBtn('다른 건물 찾기'));
    // @ts-expect-error — jsdom 원래 상태(없음)로 되돌린다.
    delete Element.prototype.scrollIntoView;
  });

  it('★ 역할이 있으면 「나는 투자자 ▾」 — 누르면 펼치고 역할 줄로 옮기며 첫 역할 단추에 커서', async () => {
    const scrolled: Element[] = [];
    Element.prototype.scrollIntoView = vi.fn(function (this: Element) {
      scrolled.push(this);
    });
    window.localStorage.setItem(KEY, '투자자');
    await openBuildingBySearch();
    expect(barBtn('나는 투자자').textContent).toBe('나는 투자자 ▾');
    fireEvent.click(barBtn('나는 투자자'));

    expect(entry().hidden).toBe(false);
    expect(scrolled).toEqual([document.querySelector('section.role')]);
    expect(document.activeElement).toBe(document.querySelector('section.role .role__chip'));
    expect(screen.getByRole('button', { name: '투자자' }).getAttribute('aria-pressed')).toBe('true');
    // @ts-expect-error — jsdom 원래 상태(없음)로 되돌린다.
    delete Element.prototype.scrollIntoView;
  });

  it('★ 링크로 연 건물은 되살린 뒤 접힌 채로 시작하고, 바에 구 이름이 살아난다', async () => {
    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);
    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(entry().hidden).toBe(true);
    // 지역 고르개는 숨겨져 있어도 살아 있어 서버 목록에서 구 이름을 채운다.
    await waitFor(() => expect(bar()!.querySelector('.entrybar__place')!.textContent).toBe('서울 강남구'));
    expect(document.querySelector('section.dmap')).toBeNull();
  });

  it('★ 되살리는 동안에도 접힌 모양(입구·지도를 그렸다 접지 않는다) · 되살리기에 실패하면 펼친 화면', async () => {
    // 층 목록 응답을 붙잡아 둔 채 '되살리는 중'을 본다.
    let release: ((r: { data: unknown; error: unknown }) => void) | null = null;
    const pending = new Promise<{ data: unknown; error: unknown }>((r) => {
      release = r;
    });
    from.mockImplementation((view: string) => {
      if (view === 'v_coverage_stats') return makeQuery({ data: [], error: null });
      const q: Record<string, unknown> = {};
      for (const m of ['select', 'eq', 'order', 'limit']) q[m] = () => q;
      q.then = (cb: (r: unknown) => unknown) => pending.then(cb);
      return q;
    });
    openWith(`?sgg=11680&bld=${LINK_BLD}`);
    render(<App />);
    await screen.findByText('링크에 담긴 건물을 불러오는 중입니다…');
    expect(entry().hidden).toBe(true);
    expect(bar()).not.toBeNull();
    // 지도는 그리지 않는다 — 지도 스크립트도 안 부른다.
    expect(document.querySelector('section.dmap')).toBeNull();

    // 층이 한 줄도 없는 건물 = 되살리기 실패 → 펼친 화면(바 없음 · 검색창 보임 · 지도 그림).
    await act(async () => {
      release!({ data: [], error: null });
      await pending;
    });
    expect(await screen.findByText(/링크에 담긴 건물을 찾지 못했습니다/)).toBeTruthy();
    expect(entry().hidden).toBe(false);
    expect(bar()).toBeNull();
    expect(document.querySelector('section.dmap')).not.toBeNull();
  });

  it('★ G2 창업자가 칩을 고른 채 건물을 열면 바에 「업종: 카페」(글자 · 단추 아님) — 전체·투자자면 없다', async () => {
    const chipBtn = (name: string) =>
      [...document.querySelectorAll('.chips button')].find((b) => b.textContent === name) as HTMLButtonElement;
    const chipText = () => bar()?.querySelector('.entrybar__chip')?.textContent ?? null;

    // ① 창업자 + 카페 → 적는다.
    window.localStorage.setItem(KEY, '창업자');
    render(<App />);
    await pickGu('서울', '강남구');
    fireEvent.click(chipBtn('카페'));
    let input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    fireEvent.click(await screen.findByRole('button', { name: /테스트빌딩/ }));
    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(chipText()).toBe('업종: 카페');
    expect(bar()!.querySelector('.entrybar__chip')!.tagName).toBe('SPAN');
    expect([...bar()!.querySelectorAll('button')].map((b) => b.textContent)).toEqual([
      '← 다른 건물 찾기',
      '상권 지도 보기',
      '나는 창업자 ▾',
    ]);
    cleanup();
    openWith('');

    // ② 창업자 + 전체(처음 값) → 안 적는다.
    render(<App />);
    await pickGu('서울', '강남구');
    input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    fireEvent.click(await screen.findByRole('button', { name: /테스트빌딩/ }));
    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(bar()).not.toBeNull();
    expect(chipText()).toBeNull();
    cleanup();
    openWith('');

    // ③ 투자자 → 칩이 없으니 안 적는다.
    window.localStorage.setItem(KEY, '투자자');
    await openBuildingBySearch();
    expect(bar()).not.toBeNull();
    expect(chipText()).toBeNull();
  });
});
