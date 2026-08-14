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

vi.mock('./lib/supabase', () => ({
  FLOOR_STACK_VIEW: 'v_floor_stack',
  COVERAGE_STATS_VIEW: 'v_coverage_stats',
  BUILDING_DISTRICTS_FN: 'list_building_districts',
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
    bld_id: '1168010100-1',
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
    bld_id: '1168010100-1',
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

async function pickGu(sidoName: string, guName: string) {
  // ⚠️ 시도 칩도 서버 응답(list_open_sigungu)을 받은 뒤에 그려진다 — 자료가 있는
  //    지역만 보여주기로 하면서(2026-08-13 사장님 결정) 목록이 서버에서 오게 됐다.
  const sidoBtn = await screen.findByRole('button', { name: new RegExp(`^${sidoName}$`) });
  fireEvent.click(sidoBtn);
  const guBtn = await screen.findByRole('button', { name: guName });
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
