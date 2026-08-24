import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
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
