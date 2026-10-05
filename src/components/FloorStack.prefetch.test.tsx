import { StrictMode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, act } from '@testing-library/react';
import { SECTION_PLAN } from '../lib/sectionCards';
import type { BuildingHit, DistrictOpenClose, FloorRow, IndustryMix, RentStat } from '../types';

/**
 * 곁 카드 요청을 건물을 고른 순간 먼저 보내는가(로드맵 속도 P3 · `lib/sidePrefetch.ts`).
 *
 * ⚠️ 이 파일의 흉내 rpc 는 진짜 supabase 처럼 **`.then` 을 부를 때마다 요청 한 번**을 센다
 *    (postgrest-js 는 `then()` 안에서 fetch 한다). `rpc()` 호출 수만 세면 "요청 객체를 저장해
 *    두고 부모·자식이 각각 `.then`" 하는 결함(실제로는 두 번 나감)을 못 잡는다.
 */

type Res = { data: unknown; error: unknown };
type Deferred = { promise: Promise<Res>; resolve: (r: Res) => void };

function deferred(): Deferred {
  let resolve!: (r: Res) => void;
  const promise = new Promise<Res>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

const SIDE_FNS = [
  'list_industry_mix',
  'count_nearby_permits',
  'list_rent_stats',
  'list_district_openclose',
] as const;
type SideFn = (typeof SIDE_FNS)[number];

/** 실제로 나간 요청(= `.then` 호출) 기록. */
const fetches: Array<{ fn: string; pnu: unknown }> = [];

const state = {
  /** 층 목록 응답. bld_id 별로. 없으면 영영 안 온다. */
  floors: new Map<string, Promise<Res>>(),
  /** 곁 함수 응답을 만드는 곳. (함수, pnu, 몇 번째 요청인지) → 응답. */
  side: (_fn: SideFn, _pnu: string, _nth: number): Promise<Res> =>
    Promise.resolve({ data: null, error: { message: 'unset' } }),
};

vi.mock('../lib/supabase', () => ({
  supabase: {
    from: (view: string) => {
      let bldId = '';
      const q: Record<string, unknown> = {};
      q.select = () => q;
      q.order = () => q;
      q.limit = () => q;
      q.eq = (_col: string, val: string) => {
        bldId = val;
        return q;
      };
      q.then = (onF: (r: Res) => unknown, onR?: (e: unknown) => unknown) => {
        if (view === 'v_coverage_stats') {
          return Promise.resolve({ data: [], error: null }).then(onF, onR);
        }
        return (state.floors.get(bldId) ?? new Promise<Res>(() => {})).then(onF, onR);
      };
      return q;
    },
    rpc: (fn: string, args?: { p_pnu?: string }) => ({
      // 진짜 빌더처럼 `.then` 마다 새 요청이다.
      then(onF: (r: Res) => unknown, onR?: (e: unknown) => unknown) {
        fetches.push({ fn, pnu: args?.p_pnu });
        if ((SIDE_FNS as readonly string[]).includes(fn)) {
          const nth = fetches.filter((f) => f.fn === fn && f.pnu === args?.p_pnu).length;
          return state.side(fn as SideFn, String(args?.p_pnu), nth).then(onF, onR);
        }
        // 층별 화면 자신의 요청(상권·실거래·시세·기준시가)은 여기서 보지 않는다 — 실패로 답해
        // 그 섹션들을 조용히 빼 둔다.
        return Promise.resolve({ data: null, error: { message: 'not here' } }).then(onF, onR);
      },
    }),
  },
}));

const { FloorStack } = await import('./FloorStack');
const { IndustryMixSection } = await import('./IndustryMixSection');
const { RentStatSection } = await import('./RentStatSection');
const { OpenCloseSection } = await import('./OpenCloseSection');
const { takePrefetched } = await import('../lib/sidePrefetch');

const A = { bld_id: 'A-1', pnu: '1168010100100010000', tag: '가' };
const B = { bld_id: 'B-1', pnu: '1168010100100020000', tag: '나' };

function building(b: typeof A): BuildingHit {
  return {
    bld_id: b.bld_id,
    pnu: b.pnu,
    bld_nm: `빌딩${b.tag}`,
    road_addr: '서울 강남구 테헤란로 1',
    bld_cnt_in_pnu: 1,
    floor_cnt: 1,
    min_floor: 1,
    max_floor: 1,
    has_roof: false,
  };
}

function floorsOf(b: typeof A): Promise<Res> {
  const row: FloorRow = {
    bld_id: b.bld_id,
    pnu: b.pnu,
    floor_no: 1,
    floor_label: null,
    floor_area_m2: 300,
    floor_area_gross_m2: 340,
    segment_cnt: 1,
    main_use: '소매점',
    uses: [],
    bld_nm: `빌딩${b.tag}`,
    approve_date: '2003-05-14',
    is_jiphap: true,
    road_addr: '서울 강남구 테헤란로 1',
    road_contact: null,
    bld_cnt_in_pnu: 1,
    store_cnt: 2,
    stores: [],
    total_area_m2: 1234.5,
    far: 350.5,
    bcr: 59.9,
    parking_cnt: 12,
  };
  return Promise.resolve({ data: [row], error: null });
}

/** 필지마다 다른 값 — 화면에 어느 건물 것이 붙었는지 글자로 가린다. */
function mixOf(pnu: string): IndustryMix {
  const tag = pnu === A.pnu ? '가' : '나';
  const total = pnu === A.pnu ? 111 : 222;
  return {
    snapshot_ym: '202606',
    radius_m: 500,
    districts: [
      {
        district_id: `d-${tag}`,
        name: `상권${tag}`,
        type: '발달상권',
        source_nm: '서울특별시 상권분석서비스',
        total,
        cats: [{ cd: 'I2', nm: '음식', n: total }],
      },
    ],
    radius: { total, cats: [{ cd: 'I2', nm: '음식', n: total }] },
  };
}

function rentOf(pnu: string): RentStat[] {
  const tag = pnu === A.pnu ? '가' : '나';
  return [
    {
      district_nm: `임대상권${tag}`,
      rone_region_nm: '서울>강남>테헤란로',
      bld_type: '집합상가',
      quarter: '2026Q2',
      vacancy_rate: 10.08,
      rent_per_m2: 27.06,
      yield_rate: 0.82,
    },
  ];
}

/** 상권 개업·폐업(결정 0033) — 필지마다 다른 상권 이름. */
function openCloseOf(pnu: string): DistrictOpenClose[] {
  const tag = pnu === A.pnu ? '가' : '나';
  return [
    {
      status: 'ok',
      district_id: `oc-${tag}`,
      district_nm: `개폐업상권${tag}`,
      district_type: '발달상권',
      latest_quarter: '20262',
      quarters: [
        {
          quarter: '20262',
          similr_induty_stor_co: 100,
          stor_co: 90,
          frc_stor_co: 10,
          opbiz_stor_co: 3,
          clsbiz_stor_co: 4,
          opbiz_rt: 3,
          clsbiz_rt: 4,
        },
      ],
      industries: null,
      other_industries: null,
      window_quarters: ['20262'],
    },
  ];
}

function okSide(fn: SideFn, pnu: string): Res {
  if (fn === 'list_industry_mix') return { data: mixOf(pnu), error: null };
  if (fn === 'list_rent_stats') return { data: rentOf(pnu), error: null };
  if (fn === 'list_district_openclose') return { data: openCloseOf(pnu), error: null };
  const total = pnu === A.pnu ? 3 : 7;
  return { data: { total_cnt: total, started_cnt: 2, base_ym: '202607' }, error: null };
}

function countFetches(fn: string, pnu?: string) {
  return fetches.filter((f) => f.fn === fn && (pnu === undefined || f.pnu === pnu)).length;
}

beforeEach(() => {
  fetches.length = 0;
  state.floors = new Map();
  state.side = (fn, pnu) => Promise.resolve(okSide(fn, pnu));
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('FloorStack — 곁 카드 요청을 먼저 보낸다 (P3)', () => {
  it('(a) 층 목록이 아직 안 왔는데도 네 요청은 이미 출발했다', async () => {
    // 층 목록은 영영 안 온다(state.floors 비어 있음).
    render(<FloorStack building={building(A)} />);
    expect(screen.getByText('층 정보를 불러오는 중…')).toBeTruthy();

    await waitFor(() => {
      for (const fn of SIDE_FNS) expect(countFetches(fn, A.pnu)).toBe(1);
    });
    // 카드는 아직 없다(층 목록이 와야 선다) — 요청만 먼저 나간 것이다.
    expect(screen.queryByText(SECTION_PLAN.industry.title)).toBeNull();
  });

  it('(b) 건물 A→B 로 바꾼 뒤 A 의 답이 늦게 와도 B 카드에는 B 값만 붙는다', async () => {
    const lateA = new Map<SideFn, Deferred>(SIDE_FNS.map((fn) => [fn, deferred()]));
    state.side = (fn, pnu) => (pnu === A.pnu ? lateA.get(fn)!.promise : Promise.resolve(okSide(fn, pnu)));
    state.floors.set(A.bld_id, floorsOf(A));
    state.floors.set(B.bld_id, floorsOf(B));

    const { rerender, container } = render(<FloorStack building={building(A)} />);
    await screen.findByText('빌딩가');
    rerender(<FloorStack building={building(B)} />);
    await screen.findByText('빌딩나');
    await screen.findByText('임대상권나');
    await screen.findByText(SECTION_PLAN.openclose.title);

    // 이제서야 A 의 답이 도착한다.
    await act(async () => {
      for (const fn of SIDE_FNS) lateA.get(fn)!.resolve(okSide(fn, A.pnu));
    });

    const text = container.textContent ?? '';
    expect(text).toContain('상권나');
    expect(text).toContain('반경 500m 이내 222곳');
    expect(text).toContain('새로 올라오는 상가 건물 7동');
    expect(text).not.toContain('상권가');
    expect(text).not.toContain('임대상권가');
    expect(text).toContain('개폐업상권나');
    expect(text).not.toContain('개폐업상권가');
    expect(text).not.toContain('111곳');
    expect(text).not.toContain('상가 건물 3동');
  });

  it('(c) 미리 보낸 요청이 실패하면 카드는 지금의 실패 화면과 같다 — 다시 묻지 않는다', async () => {
    // 첫 요청만 실패하고 그 뒤로는 성공한다. 카드가 미리 보낸 결과를 안 받고 스스로 다시
    // 물으면 성공 답을 받아 카드가 서 버린다 — 그 결함을 잡으려는 모양이다.
    state.side = (fn, pnu, nth) =>
      Promise.resolve(nth === 1 ? { data: null, error: { message: 'boom' } } : okSide(fn, pnu));
    state.floors.set(A.bld_id, floorsOf(A));

    render(<FloorStack building={building(A)} />);
    await screen.findByText('빌딩가');
    await act(async () => {});

    // 업종 분포·임대 동향은 실패면 카드째 사라지고, 인허가 줄도 없다(각 카드의 실패 규칙 그대로).
    expect(screen.queryByText(SECTION_PLAN.industry.title)).toBeNull();
    expect(screen.queryByText(SECTION_PLAN.rent.title)).toBeNull();
    expect(screen.queryByText(SECTION_PLAN.openclose.title)).toBeNull();
    expect(screen.queryByText(/새로 올라오는 상가 건물/)).toBeNull();
    for (const fn of SIDE_FNS) expect(countFetches(fn)).toBe(1);
  });

  it('(c-2) 인허가 한 줄만 실패하면 업종 카드는 서고 그 줄만 빠진다', async () => {
    state.side = (fn, pnu) =>
      Promise.resolve(
        fn === 'count_nearby_permits' ? { data: null, error: { message: 'boom' } } : okSide(fn, pnu),
      );
    state.floors.set(A.bld_id, floorsOf(A));

    render(<FloorStack building={building(A)} />);
    await screen.findByText('임대상권가');
    expect(screen.getByText(SECTION_PLAN.industry.title)).toBeTruthy();
    expect(screen.queryByText(/새로 올라오는 상가 건물/)).toBeNull();
  });

  it('(d) 건물 한 번 보는 데 네 함수 각각 정확히 1회', async () => {
    state.floors.set(A.bld_id, floorsOf(A));
    render(<FloorStack building={building(A)} />);
    await screen.findByText('임대상권가');
    await screen.findByText('새로 올라오는 상가 건물 3동');
    for (const fn of SIDE_FNS) expect(countFetches(fn)).toBe(1);
  });

  it('(d-2) 개발 모드(StrictMode)의 이중 실행에서도 각 1회', async () => {
    state.floors.set(A.bld_id, floorsOf(A));
    render(
      <StrictMode>
        <FloorStack building={building(A)} />
      </StrictMode>,
    );
    await screen.findByText('임대상권가');
    await screen.findByText('새로 올라오는 상가 건물 3동');
    for (const fn of SIDE_FNS) expect(countFetches(fn)).toBe(1);
  });
});

describe('곁 카드 — 다른 필지의 미리 보낸 답은 받지 않는다 (보관 열쇠 = 함수 + pnu)', () => {
  /** 건물 A 몫으로 미리 받아 둔 한 벌 — 이미 도착해 있다. */
  function prefetchOfA() {
    return {
      pnu: A.pnu,
      results: new Map<string, Promise<Res>>(
        SIDE_FNS.map((fn) => [fn, Promise.resolve(okSide(fn, A.pnu))]),
      ),
    };
  }

  it('takePrefetched 는 pnu 가 다르면 null, 같으면 그 함수의 답', () => {
    const pre = prefetchOfA();
    expect(takePrefetched(pre, 'list_industry_mix', B.pnu)).toBeNull();
    expect(takePrefetched(pre, 'list_industry_mix', A.pnu)).toBe(
      pre.results.get('list_industry_mix'),
    );
    expect(takePrefetched(null, 'list_industry_mix', A.pnu)).toBeNull();
  });

  it('업종 분포 카드: A 몫을 받은 채 B 로 그려지면 B 를 스스로 묻고 B 값만 보인다', async () => {
    const { container } = render(<IndustryMixSection pnu={B.pnu} prefetch={prefetchOfA()} />);
    await screen.findByText('새로 올라오는 상가 건물 7동');
    const text = container.textContent ?? '';
    expect(text).toContain('반경 500m 이내 222곳');
    expect(text).not.toContain('111곳');
    expect(countFetches('list_industry_mix', B.pnu)).toBe(1);
  });

  it('임대 동향 카드: A 몫을 받은 채 B 로 그려지면 B 값만 보인다', async () => {
    render(<RentStatSection pnu={B.pnu} prefetch={prefetchOfA()} />);
    expect(await screen.findByText('임대상권나')).toBeTruthy();
    expect(screen.queryByText('임대상권가')).toBeNull();
  });

  it('개업·폐업 카드: A 몫을 받은 채 B 로 그려지면 B 를 스스로 묻고 B 값만 보인다', async () => {
    const { container } = render(<OpenCloseSection pnu={B.pnu} prefetch={prefetchOfA()} />);
    await screen.findByText(SECTION_PLAN.openclose.title);
    const text = container.textContent ?? '';
    expect(text).toContain('개폐업상권나');
    expect(text).not.toContain('개폐업상권가');
    expect(countFetches('list_district_openclose', B.pnu)).toBe(1);
  });
});
