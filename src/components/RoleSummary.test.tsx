import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, act, fireEvent, waitFor } from '@testing-library/react';
import type { ComponentProps } from 'react';
import type {
  BuildingHit,
  DistrictOpenClose,
  FloorRow,
  IndustryMedian,
  IndustryMix,
  ParcelTransaction,
  PriceBand,
  RentStat,
} from '../types';

/**
 * 역할 요약 판(결정 0039 W2) — 층별 화면 전체를 그려서 본다.
 * ⓘ 흉내 rpc 는 진짜 supabase 처럼 `.then` 을 부를 때마다 요청 한 번을 센다(`FloorStack.prefetch.test.tsx` 와 같은 꼴) —
 *   판이 스스로 서버에 묻는지(추가 호출)를 `.then` 수로 잡는다.
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

const fetches: Array<{ fn: string; pnu: unknown }> = [];
const state = {
  floors: new Map<string, FloorRow[]>(),
  /** 곁 함수의 답 — (함수, pnu) → 응답. 기본은 ok 답. */
  side: (fn: string, pnu: string): Promise<Res> => Promise.resolve(okRpc(fn, pnu)),
  /** 판을 끈다(같은 역할로 판 유무만 갈라 rpc 수를 견준다). */
  summaryOff: false,
};

vi.mock('../lib/supabase', () => ({
  supabase: {
    from: (view: string) => {
      let bldId = '';
      const q: Record<string, unknown> = {};
      q.select = () => q;
      q.order = () => q;
      q.limit = () => q;
      q.eq = (_c: string, v: string) => {
        bldId = v;
        return q;
      };
      q.then = (onF: (r: Res) => unknown, onR?: (e: unknown) => unknown) => {
        fetches.push({ fn: `from:${view}`, pnu: bldId });
        if (view === 'v_coverage_stats') {
          return Promise.resolve({
            data: [{ snapshot_ym: '202606', store_cnt: 1000, floor_missing_cnt: 329, floor_missing_pct: 32.9 }],
            error: null,
          }).then(onF, onR);
        }
        const rows = state.floors.get(bldId);
        return (rows ? Promise.resolve({ data: rows, error: null }) : new Promise<Res>(() => {})).then(onF, onR);
      };
      return q;
    },
    rpc: (fn: string, args?: { p_pnu?: string; pnu?: string }) => ({
      then(onF: (r: Res) => unknown, onR?: (e: unknown) => unknown) {
        const pnu = String(args?.p_pnu ?? args?.pnu ?? '');
        fetches.push({ fn, pnu });
        return state.side(fn, pnu).then(onF, onR);
      },
    }),
  },
}));

vi.mock('./RoleSummary', async (orig) => {
  const real = (await orig()) as typeof import('./RoleSummary');
  return {
    RoleSummary: (p: ComponentProps<typeof real.RoleSummary>) => (state.summaryOff ? null : <real.RoleSummary {...p} />),
  };
});

const { FloorStack } = await import('./FloorStack');

const A = { bld_id: 'A-1', pnu: '1168010100100010000', tag: '가' };
const B = { bld_id: 'B-1', pnu: '1168010100100020000', tag: '나' };

function building(b: typeof A): BuildingHit {
  return {
    bld_id: b.bld_id,
    pnu: b.pnu,
    bld_nm: `빌딩${b.tag}`,
    road_addr: '서울 강남구 테헤란로 1',
    bld_cnt_in_pnu: 1,
    floor_cnt: 2,
    min_floor: 1,
    max_floor: 2,
    has_roof: false,
  };
}

function floorsOf(b: typeof A): FloorRow[] {
  const row = (no: number, store: number): FloorRow => ({
    bld_id: b.bld_id,
    pnu: b.pnu,
    floor_no: no,
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
    store_cnt: store,
    stores: [],
    total_area_m2: 1234.5,
    far: 350.5,
    bcr: 59.9,
    parking_cnt: b === A ? 120 : 77,
    ho_cnt: b === A ? 48 : 31,
    bld_main_use: '제1종근린생활시설',
  });
  return [row(2, 3), row(1, b === A ? 4 : 6)];
}

const isA = (pnu: string) => pnu === A.pnu;

function okRpc(fn: string, pnu: string): Res {
  const tag = isA(pnu) ? '가' : '나';
  switch (fn) {
    case 'list_parcel_transactions': {
      const t: ParcelTransaction = {
        floor_no: 2,
        contract_ym: isA(pnu) ? '202603' : '202511',
        contract_day: 1,
        bld_area_m2: 33,
        price_won: isA(pnu) ? 240_000_000 : 180_000_000,
        unit_price: 7_272_727,
        tx_type: '집합',
      };
      return { data: [t], error: null };
    }
    case 'list_price_bands': {
      const b: PriceBand = {
        floor_no: 2,
        status: 'ok',
        stage: 'L5',
        n: 7,
        p25: 3_000_000,
        median: 3_500_000,
        p75: 4_000_000,
        median_area_m2: 33,
        window_from: '2024-01',
      };
      return { data: [b], error: null };
    }
    case 'get_parcel_land_price':
      return { data: [{ land_price: isA(pnu) ? 45_230_000 : 12_340_000, land_price_year: 2025 }], error: null };
    case 'list_rent_stats': {
      const r: RentStat = {
        district_nm: `임대상권${tag}`,
        rone_region_nm: '서울>강남>테헤란로',
        bld_type: '집합상가',
        quarter: '2026Q2',
        vacancy_rate: 10.08,
        rent_per_m2: isA(pnu) ? 27.06 : 31.5,
        yield_rate: 0.82,
      };
      return { data: [r], error: null };
    }
    case 'list_district_openclose': {
      const r: DistrictOpenClose = {
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
            opbiz_stor_co: isA(pnu) ? 3 : 8,
            clsbiz_stor_co: 4,
            opbiz_rt: 3,
            clsbiz_rt: 4,
          },
        ],
        industries: null,
        other_industries: null,
        window_quarters: ['20262'],
      };
      return { data: [r], error: null };
    }
    case 'list_industry_mix': {
      const total = isA(pnu) ? 111 : 222;
      const m: IndustryMix = {
        snapshot_ym: '202606',
        radius_m: 500,
        districts: [
          { district_id: `d-${tag}`, name: `상권${tag}`, type: '발달상권', source_nm: '서울', total, cats: [{ cd: 'I2', nm: '음식', n: total }] },
        ],
        radius: { total, cats: [{ cd: 'I2', nm: '음식', n: total }] },
      };
      return { data: m, error: null };
    }
    case 'list_industry_median': {
      const m: IndustryMedian = {
        snapshot_ym: '202606',
        min_total: 30,
        min_pop: 30,
        districts: [
          {
            district_id: `d-${tag}`,
            type: '발달상권',
            total: isA(pnu) ? 111 : 222,
            pop: { scope: 'type', sido_cd: '11', district_type: '발달상권', n: 249 },
            cats: [{ cd: 'I2', nm: '음식', med_pct: isA(pnu) ? 11.1 : 22.2 }],
          },
        ],
      };
      return { data: m, error: null };
    }
    default:
      return { data: null, error: { message: 'not here' } };
  }
}

const SIDE = ['list_industry_mix', 'count_nearby_permits', 'list_rent_stats', 'list_district_openclose', 'list_industry_median'];

beforeEach(() => {
  fetches.length = 0;
  state.floors = new Map([
    [A.bld_id, floorsOf(A)],
    [B.bld_id, floorsOf(B)],
  ]);
  state.side = (fn, pnu) => Promise.resolve(okRpc(fn, pnu));
  state.summaryOff = false;
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/** 판이 다 선 뒤까지 기다린다(곁 카드 답이 다 와 카드 셋이 선 뒤). */
async function settle() {
  await screen.findByText('임대상권가', { selector: '.rent__where' });
  await act(async () => {});
}

describe('RoleSummary — 층별 화면 맨 위 역할 요약 판', () => {
  it('역할이 없으면 판이 없다(지금 화면 그대로)', async () => {
    const { container } = render(<FloorStack building={building(A)} />);
    await settle();
    expect(container.querySelector('.rsum')).toBeNull();
  });

  it.each([
    ['투자자', 4],
    ['창업자', 4],
    ['중개사', 3],
  ] as const)('%s — 타일 %i개 · 자리는 건물 머리(.stack__head) 앞', async (role, n) => {
    const { container } = render(<FloorStack building={building(A)} viewerRole={role} />);
    await settle();
    await waitFor(() => expect(container.querySelectorAll('.rsum__tile')).toHaveLength(n));
    const sum = container.querySelector('.rsum')!;
    const head = container.querySelector('.stack__head')!;
    expect(sum.compareDocumentPosition(head) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(sum.parentElement).toBe(head.parentElement);
  });

  it('판이 서버에 더 묻지 않는다 — 같은 역할로 판 유무만 갈라 rpc 요청 수가 같다', async () => {
    const counts: number[] = [];
    for (const off of [true, false]) {
      fetches.length = 0;
      state.summaryOff = off;
      const { container } = render(<FloorStack building={building(A)} viewerRole="창업자" />);
      await settle();
      if (!off) await waitFor(() => expect(container.querySelectorAll('.rsum__tile')).toHaveLength(4));
      await act(async () => {});
      counts.push(fetches.length);
      cleanup();
    }
    expect(counts[0]).toBeGreaterThan(0);
    expect(counts[1]).toBe(counts[0]);
    for (const fn of SIDE) expect(fetches.filter((f) => f.fn === fn)).toHaveLength(1);
  });

  it('판 파일은 supabase 를 import 하지 않는다(스스로 묻는 길이 아예 없다)', async () => {
    const { readFileSync } = await import('node:fs');
    for (const f of ['src/components/RoleSummary.tsx', 'src/lib/roleSummary.ts']) {
      expect(readFileSync(f, 'utf8'), f).not.toMatch(/from\s+['"][./]*lib\/supabase['"]|from\s+['"]\.\/supabase['"]/);
    }
  });

  it('건물 A→B — A 의 늦은 곁 답이 와도 판에는 B 값만', async () => {
    const lateA = new Map(SIDE.map((fn) => [fn, deferred()]));
    state.side = (fn, pnu) =>
      isA(pnu) && lateA.has(fn) ? lateA.get(fn)!.promise : Promise.resolve(okRpc(fn, pnu));
    const { rerender, container } = render(<FloorStack building={building(A)} viewerRole="창업자" />);
    await screen.findByText('빌딩가');
    rerender(<FloorStack building={building(B)} viewerRole="창업자" />);
    await screen.findByText('빌딩나');
    await waitFor(() => expect(container.querySelector('.rsum')?.textContent).toContain('개폐업상권나'));
    await act(async () => {
      for (const fn of SIDE) lateA.get(fn)!.resolve(okRpc(fn, A.pnu));
    });
    const text = container.querySelector('.rsum')!.textContent ?? '';
    expect(text).toContain('상권나');
    expect(text).toContain('개업 8곳');
    expect(text).toContain('가운데 22.2%');
    expect(text).toContain('31,500원');
    expect(text).toContain('점포 6');
    expect(text).not.toMatch(/상권가|개업 3곳|가운데 11\.1%|27,060원|점포 4\b/);
  });

  it('중개사 「한 장으로 뽑기」 — 기록(onBeforePrint) 다음에 인쇄 창', async () => {
    const order: string[] = [];
    const print = vi.spyOn(window, 'print').mockImplementation(() => order.push('print'));
    const before = vi.fn(() => order.push('before'));
    render(<FloorStack building={building(A)} viewerRole="중개사" onBeforePrint={before} />);
    await settle();
    fireEvent.click(await screen.findByRole('button', { name: '한 장으로 뽑기' }));
    expect(order).toEqual(['before', 'print']);
    expect(print).toHaveBeenCalledTimes(1);
    // 투자자·창업자 판에는 그 단추가 없다.
    cleanup();
    render(<FloorStack building={building(A)} viewerRole="투자자" />);
    await settle();
    expect(screen.queryByRole('button', { name: '한 장으로 뽑기' })).toBeNull();
  });

  it('투자자 판의 실제 글 — 시세 줄(C등급)·임대(상권 평균)·공시지가', async () => {
    const { container } = render(<FloorStack building={building(A)} viewerRole="투자자" />);
    await settle();
    await waitFor(() => expect(container.querySelectorAll('.rsum__tile')).toHaveLength(4));
    const band = container.querySelector('.rsum__tile--band')!;
    expect(band.classList.contains('rsum__tile--est')).toBe(true);
    expect(band.querySelector('.grade__badge--est')?.textContent).toBe('C등급 · 파생 추정');
    expect(container.querySelector('.rsum__tile--rent')!.textContent).toContain('상권 평균 · 집합상가 · 2026년 2분기 조사');
    expect(container.querySelector('.rsum__answer')!.textContent).toBe(
      '2층 참고 시세는 비슷한 호실 한 칸 33㎡ (10평) 기준 1.0억~1.3억입니다. 이 땅 신고 거래는 1건입니다.',
    );
  });
});

// ── CSS 가드 ────────────────────────────────────────────────────────────────

/**
 * CSS 를 주석 빼고 `@media` 묶음 밖(기본 규칙)과 안으로 갈라 규칙 목록(선택자 · 본문 · 묶음 머리)으로 편다
 * (`DistrictMap.test.tsx` 의 같은 이름 함수와 같은 꼴). 이 파일의 CSS 가드와 양성 대조가 같은 함수를 지난다.
 * 못 보는 것: `@media` 안의 또 다른 `@media`·`@supports` 겹 묶음 · 문자열 안의 중괄호.
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

/** 종이(@media print)에서 `.rsum` 계열 선택자가 나오는 자리 수 · 그중 감추는 규칙 수. */
function printRsum(css: string): { all: number; hide: number } {
  const rules = cssRules(css).filter((r) => r.media === '@media print');
  const hit = rules.flatMap((r) => r.sel.filter((s) => /\.rsum/.test(s)).map(() => r));
  return { all: hit.length, hide: hit.filter((r) => /display:\s*none/.test(r.body)).length };
}

describe('역할 요약 판 — CSS', () => {
  it('종이 감춤은 한 선택자 한 곳(.rsum) — 그 한 줄만 빼면 종이에 나온다 · 양성 대조', async () => {
    const { readFileSync } = await import('node:fs');
    const css = readFileSync('src/styles.css', 'utf8');
    expect(printRsum(css)).toEqual({ all: 1, hide: 1 });
    const hide = cssRules(css).find((r) => r.media === '@media print' && r.sel.includes('.rsum'));
    expect(hide?.body).toMatch(/display:\s*none/);
    // 양성 대조 — 종이 묶음에 감춤이 하나 더 생기면(흔한 꼴 · 선택자 목록 꼴) 센다.
    expect(printRsum(`${css}\n@media print { .rsum__tiles { display: none; } }`).hide).toBe(2);
    expect(printRsum(`${css}\r\n@media print {\r\n  .x,\r\n  .rsum__print {\r\n    display:none;\r\n  }\r\n}`).all).toBe(2);
  });

  it('휴대폰 배치는 화면 720 묶음 안에만 · 기본 규칙엔 휴대폰 꼴(한 칸) 없음 · 단추는 44px 목록', async () => {
    const { readFileSync } = await import('node:fs');
    const rules = cssRules(readFileSync('src/styles.css', 'utf8'));
    const phone = rules.filter((r) => r.sel.includes('.rsum__tiles') && r.media !== null);
    expect(phone.map((r) => r.media)).toEqual(['@media screen and (max-width: 720px)']);
    expect(rules.filter((r) => r.sel.some((s) => /\.rsum/.test(s)) && r.media === '@media (max-width: 720px)')).toEqual([]);
    const tall = rules.filter((r) => r.media === '@media screen' && /min-height:\s*44px/.test(r.body));
    expect(tall.some((r) => r.sel.includes('.rsum__print'))).toBe(true);
    // 카드 통째 break-inside: avoid 금지(종이에 넣는 날 한 장을 넘기면 통째로 다음 장으로 밀린다).
    expect(rules.filter((r) => r.sel.some((s) => /^\.rsum/.test(s)) && /break-inside:\s*avoid/.test(r.body))).toEqual([]);
  });
});
