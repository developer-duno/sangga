import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import type { BuildingHit, FloorRow, OpenSigungu } from './types';
import type { DistrictMapPick } from './lib/districtMapPick';

/**
 * App 이 지도에서 누른 상권·펼친 목록을 쥐는가(👤 2026-10-15 G1 「다시 펴면 그대로 되살리기」).
 *
 * 입구가 접히면(S1) 지도는 아예 안 그려진다 — 그래서 기억은 지도 바깥(App)에 있어야 다시 그릴 때 되살아난다.
 * 지도 알맹이(카카오)는 App 시험에서 안 그려지므로 **지도를 가짜로 바꿔** App 의 배선만 본다:
 * 받은 기억을 그대로 다시 넘기나 · 구가 바뀌면 비우나 · 이 기기 저장·주소에 안 싣나.
 * 지도 쪽(기억으로 상권·목록을 다시 세우는가)은 `components/DistrictMap.test.tsx` 「G1」이 본다.
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

/** 가짜 지도 — 받은 기억을 글자로 내걸고, 누르면 기억을 바꿔 알린다. */
vi.mock('./components/DistrictMap', () => {
  return {
    DistrictMap: ({
      sigungu,
      pick,
      onPickChange,
    }: {
      sigungu: string | null;
      pick?: DistrictMapPick;
      onPickChange?: (next: DistrictMapPick) => void;
    }) =>
      sigungu ? (
        <section className="dmap">
          <output data-testid="pick">{JSON.stringify(pick ?? null)}</output>
          <button type="button" onClick={() => onPickChange?.({ sigungu, pickedIds: ['big', 'small'], openId: 'big' })}>
            상권 누르기
          </button>
        </section>
      ) : null,
  };
});

const { default: App } = await import('./App');

const LINK_BLD = '1168010100100010000_1024110';

function gu(over: Partial<OpenSigungu> = {}): OpenSigungu {
  return { sido_code: '11', sido_nm: '서울', sigungu_code: '11680', sigungu_nm: '강남구', building_cnt: 1, ...over };
}

function hit(over: Partial<BuildingHit> = {}): BuildingHit {
  return {
    bld_id: LINK_BLD,
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

function floorRow(): FloorRow {
  return {
    bld_id: LINK_BLD,
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
    total_area_m2: 1234.5,
    far: 350.5,
    bcr: 59.9,
    parking_cnt: 12,
  };
}

beforeEach(() => {
  window.history.replaceState(null, '', '/');
  rpc.mockReset();
  from.mockReset();
  from.mockImplementation((view: string) =>
    makeQuery(view === 'v_coverage_stats' ? { data: [], error: null } : { data: [floorRow()], error: null }),
  );
  rpc.mockImplementation((fn: string) => {
    if (fn === 'list_open_sigungu') {
      return Promise.resolve({
        data: [gu(), gu({ sigungu_code: '30170', sido_code: '30', sido_nm: '대전', sigungu_nm: '서구' })],
        error: null,
      });
    }
    if (fn === 'search_buildings') return Promise.resolve({ data: [hit()], error: null });
    return Promise.resolve({ data: [], error: null });
  });
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

async function pickGu(sidoName: string, guName: string) {
  fireEvent.click(await screen.findByRole('button', { name: new RegExp(`^${sidoName}$`) }));
  fireEvent.click(await screen.findByRole('button', { name: new RegExp(`^${guName}`) }));
}

const pickShown = () => JSON.parse(screen.getByTestId('pick').textContent ?? 'null') as DistrictMapPick | null;

describe('App — 지도에서 누른 상권 기억 (G1)', () => {
  it('★ 접혀 지도가 사라졌다가 「상권 지도 보기」로 다시 그려지면 아까 누른 기억을 그대로 넘긴다 · 저장·주소에는 없다', async () => {
    render(<App />);
    await pickGu('서울', '강남구');
    expect(pickShown()).toEqual({ sigungu: null, pickedIds: null, openId: null });
    fireEvent.click(screen.getByRole('button', { name: '상권 누르기' }));
    expect(pickShown()).toEqual({ sigungu: '11680', pickedIds: ['big', 'small'], openId: 'big' });

    // 건물을 고르면 접혀 지도가 사라진다.
    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    fireEvent.click(await screen.findByRole('button', { name: /테스트빌딩/ }));
    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(screen.queryByTestId('pick')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '상권 지도 보기' }));
    expect(pickShown()).toEqual({ sigungu: '11680', pickedIds: ['big', 'small'], openId: 'big' });

    // ⛔ 화면 상태만 — 이 기기 저장·주소에 상권 번호가 없다.
    expect(Object.values(window.localStorage).join('|')).not.toContain('big');
    expect(window.location.search).not.toContain('big');
  });

  it('★ 구를 바꾸면 기억을 비운다 — 다른 구에서 옛 상권이 되살아나지 않는다', async () => {
    render(<App />);
    await pickGu('서울', '강남구');
    fireEvent.click(screen.getByRole('button', { name: '상권 누르기' }));
    expect(pickShown()?.openId).toBe('big');

    await pickGu('대전', '서구');
    expect(pickShown()).toEqual({ sigungu: null, pickedIds: null, openId: null });

    // 다시 강남구로 돌아와도 옛 기억은 없다.
    await pickGu('서울', '강남구');
    expect(pickShown()).toEqual({ sigungu: null, pickedIds: null, openId: null });
  });

  it('★ 최근 뽑은 건물로 다른 구에 갔다가 다시 돌아와도 옛 기억은 없다 — 지도가 처음부터', async () => {
    // 중개사 + 이 기기에 저장된 최근 건물 둘(강남·대전). 저장 꼴은 검색 결과에서 total_cnt 만 뺀 것.
    const recent = [
      hit({ bld_id: '1168010100100020000_1', pnu: '1168010100100020000', bld_nm: '강남빌딩' }),
      hit({ bld_id: '3017010100100010000_5', pnu: '3017010100100010000', bld_nm: '대전빌딩', road_addr: '대전 서구 둔산로 1' }),
    ].map(({ total_cnt: _t, ...rest }) => {
      void _t;
      return rest;
    });
    window.localStorage.setItem('sangga.viewerRole', '중개사');
    window.localStorage.setItem('sangga.recentPrinted', JSON.stringify(recent));
    const pickRecent = async (name: RegExp) => {
      fireEvent.click(await screen.findByRole('button', { name: /최근 뽑은 건물/ }));
      fireEvent.click(await screen.findByRole('button', { name }));
      await screen.findByRole('button', { name: '상권 지도 보기' }); // 고르면 다시 접힌다
    };

    render(<App />);
    await pickGu('서울', '강남구');
    fireEvent.click(screen.getByRole('button', { name: '상권 누르기' }));
    expect(pickShown()?.sigungu).toBe('11680');

    // 강남 → (최근 건물) 대전 서구 → (펼쳐서 최근 건물) 다시 강남.
    await pickRecent(/대전빌딩/);
    fireEvent.click(screen.getByRole('button', { name: '다른 건물 찾기' }));
    await pickRecent(/강남빌딩/);
    expect(window.location.search).toContain('sgg=11680');

    fireEvent.click(screen.getByRole('button', { name: '상권 지도 보기' }));
    expect(pickShown()).toEqual({ sigungu: null, pickedIds: null, openId: null });
  });
});
