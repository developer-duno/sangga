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

describe('App — 구를 바꾸면 이전 결과가 사라진다', () => {
  it('검색 결과·선택 건물·검색어가 구를 바꾸는 순간 함께 사라진다', async () => {
    render(<App />);

    await pickGu('서울', '강남구');

    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);

    const hitBtn = await screen.findByRole('button', { name: /테스트빌딩/ });
    fireEvent.click(hitBtn);
    await waitFor(() => expect(screen.getByRole('heading', { name: '테스트빌딩' })).toBeTruthy());
    expect(screen.getByText(/강남구에서/)).toBeTruthy();

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

    // 그 사이 사용자가 검색으로 다른 건물을 고른다.
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
