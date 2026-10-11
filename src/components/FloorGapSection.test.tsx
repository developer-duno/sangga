import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import type { BasePrice, FloorRow, RentStat, SigunguTxStat } from '../types';
import type { SidePrefetch } from '../lib/sidePrefetch';

/**
 * 「층 차이 세 잣대」 카드(결정 0036 결정 15 · 물결 1-C2). 짝짓기 규칙은 `lib/floorGap.test.ts` 가 덮고,
 * 여기서는 ① 재료 하나가 실패하면 그 칸만 '–' · 셋 다 없으면 카드째 숨김 · 층 0줄도 숨김
 * ② 부동산원은 임대 카드와 **같은 미리 보낸 답**을 받아 RPC 를 더 안 낸다 ③ 접힌 채 시작 · 요약에 값 0.
 */

const responses = { rent: { data: null as unknown, error: null as unknown } };
const rpcCalls: Array<{ fn: string; args: unknown }> = [];

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string, args?: unknown) => {
      rpcCalls.push({ fn, args });
      return Promise.resolve(responses.rent);
    },
  },
}));

const { FloorGapSection } = await import('./FloorGapSection');

const PNU = '1168010100100010000';

function floor(floorNo: number): FloorRow {
  return {
    bld_id: `${PNU}_1`,
    pnu: PNU,
    floor_no: floorNo,
    floor_label: null,
    floor_area_m2: 300,
    floor_area_gross_m2: 340,
    segment_cnt: 1,
    main_use: '소매점',
    uses: [],
    bld_nm: '테스트빌딩',
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
}

const BASES: BasePrice[] = [{ floor_no: 1, median_price_per_m2: 5_000_000, ho_cnt: 12, notice_date: '2026-01-01' }];
const TX: SigunguTxStat[] = [
  { floor_band: '1층', n: 213, median_unit_price: 3_800_000, p25_unit_price: null, p75_unit_price: null, window_from: '202410', sigungu_nm: '강남구' },
  { floor_band: '2층', n: 9, median_unit_price: 2_500_000, p25_unit_price: null, p75_unit_price: null, window_from: '202410', sigungu_nm: '강남구' },
];
function rent(): RentStat {
  return {
    district_nm: '역삼역',
    rone_region_nm: '서울>강남>테헤란로',
    bld_type: '집합상가',
    quarter: '2026Q2',
    vacancy_rate: 3.5,
    rent_per_m2: 74.6,
    yield_rate: 0.82,
    floor_rent: { '1': 74.6, '2': 50.5 },
  } as RentStat;
}

beforeEach(() => {
  rpcCalls.length = 0;
  responses.rent = { data: [rent()], error: null };
});
afterEach(() => cleanup());

function cellText(container: HTMLElement, floorNo: number, k: string): string {
  return container.querySelector(`.gap__row[data-floor="${floorNo}"] .gap__cell--${k} .gap__val`)?.textContent ?? '';
}

describe('FloorGapSection', () => {
  it('접힌 채 서고 요약에 값이 없다 · 펼친 본문은 층마다 세 칸', async () => {
    const { container } = render(
      <FloorGapSection floors={[floor(2), floor(1)]} basePrices={BASES} txStats={TX} pnu={PNU} />,
    );
    const toggle = await screen.findByRole('button', { name: /층 차이 세 잣대/ });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelector('.card__summary')?.textContent).toBe('국세청 · 구 실거래 · 부동산원 — 층마다 나란히');
    await waitFor(() => expect(cellText(container, 1, 'rent')).toBe('74.6'));
    expect([...container.querySelectorAll('.gap__row')].map((r) => r.getAttribute('data-floor'))).toEqual(['2', '1']);
    expect(cellText(container, 1, 'base')).toBe('500만');
    expect(cellText(container, 1, 'tx')).toBe('㎡당 380만');
    expect(cellText(container, 2, 'base')).toBe('–');
    expect(cellText(container, 2, 'tx')).toBe('㎡당 250만');
    expect(container.textContent).toContain('서로 나누거나 비율을 계산하지 않았습니다');
    expect(container.textContent).toContain('세무 기준가격 — 시세가 아닙니다');
    expect(container.textContent).toContain('A등급 · 공식 고시');
    expect(container.textContent).toContain('B등급 · 공식 표본조사');
    expect(container.textContent).not.toMatch(/[%％]/);
  });

  it('부동산원 함수가 실패하면 그 칸만 – (카드는 선다)', async () => {
    responses.rent = { data: null, error: { code: 'PGRST202' } };
    const { container } = render(
      <FloorGapSection floors={[floor(1)]} basePrices={BASES} txStats={TX} pnu={PNU} />,
    );
    await screen.findByRole('button', { name: /층 차이 세 잣대/ });
    await waitFor(() => expect(rpcCalls).toHaveLength(1));
    expect(cellText(container, 1, 'rent')).toBe('–');
    expect(cellText(container, 1, 'base')).toBe('500만');
  });

  it('조사 대상 아님이면 그 칸 머리에 임대 카드와 같은 글', async () => {
    responses.rent = { data: [], error: null };
    const { container } = render(<FloorGapSection floors={[floor(1)]} basePrices={BASES} txStats={TX} pnu={PNU} />);
    await waitFor(() =>
      expect(container.querySelector('.gap__head--rent')?.textContent).toContain('부동산원 조사 대상 상권이 아닙니다'),
    );
    expect(cellText(container, 1, 'rent')).toBe('–');
  });

  it('★ 국세청·부동산원이 둘 다 비면 구 실거래가 있어도 카드째 숨긴다(빈 배열도 null 처럼)', async () => {
    responses.rent = { data: [], error: null };
    const { container } = render(<FloorGapSection floors={[floor(1)]} basePrices={[]} txStats={TX} pnu={PNU} />);
    await waitFor(() => expect(rpcCalls).toHaveLength(1));
    await new Promise((r) => setTimeout(r, 0));
    expect(container.querySelector('.gap')).toBeNull();
  });

  it('세 재료가 모두 없으면 카드째 숨긴다', async () => {
    responses.rent = { data: null, error: { code: 'PGRST202' } };
    const { container } = render(<FloorGapSection floors={[floor(1)]} basePrices={null} txStats={null} pnu={PNU} />);
    await waitFor(() => expect(rpcCalls).toHaveLength(1));
    expect(container.querySelector('.gap')).toBeNull();
  });

  it('층이 0줄이면 숨긴다', () => {
    const { container } = render(<FloorGapSection floors={[]} basePrices={BASES} txStats={TX} pnu={PNU} />);
    expect(container.querySelector('.gap')).toBeNull();
  });

  it('미리 보낸 답이 있으면 그것을 받고 RPC 를 더 안 낸다(임대 카드와 같은 Promise 를 나눈다)', async () => {
    const shared = Promise.resolve({ data: [rent()], error: null });
    const prefetch: SidePrefetch = { pnu: PNU, results: new Map([['list_rent_stats', shared]]) };
    const { container } = render(
      <FloorGapSection floors={[floor(1)]} basePrices={null} txStats={TX} pnu={PNU} prefetch={prefetch} />,
    );
    await waitFor(() => expect(cellText(container, 1, 'rent')).toBe('74.6'));
    expect(rpcCalls).toHaveLength(0);
  });
});
