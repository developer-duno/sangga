import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
import type { DistrictCensusPop } from '../types';
import { SECTION_PLAN } from '../lib/sectionCards';

/**
 * 대전 「상권 인구 (통계청 집계구)」 카드 — 결정 0045 PR⑤(본보기 = PopSection.test).
 *
 * 여기서 특히 지키는 것
 *  ① 제목·자료 갈래를 이 카드 것으로 바꿔 끼운다(자리·펼침은 받은 plan 그대로) · 접힌 요약에 값이 없다 · 인자 `p_pnu`
 *  ② 못 읽었으면(PGRST202·오류·모양 이상·0줄) 카드째 숨긴다 — 「자료 없음」이라 적지 않는다
 *  ③ 필지가 바뀌면 옛 답을 비우고, 늦게 온 앞 필지 답은 버린다 · 미리 보낸 답이 있으면 다시 안 묻는다
 *  ④ 상권 둘 — 값 + 범위 · 범위만 · 가구 · 종사자 덩이 제목 · 덩어리 발 · 발 문구 다섯 · 서버 차례 그대로
 *  ⑤ 건물 단위 셋 — 한 문단 + 출처 줄
 */

const responses = {
  census: { data: null as unknown, error: null as unknown },
};
const gate: { next: Promise<{ data: unknown; error: unknown }> | null } = { next: null };
const rpcCalls: Array<{ fn: string; args: unknown }> = [];

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string, args?: unknown) => {
      rpcCalls.push({ fn, args });
      if (fn === 'get_data_freshness') return Promise.resolve({ data: null, error: { code: 'PGRST202' } });
      const g = gate.next;
      gate.next = null;
      return g ?? Promise.resolve(responses.census);
    },
  },
}));

const { CensusPopSection } = await import('./CensusPopSection');
const { resetDataFreshnessCache } = await import('../lib/loadDataFreshness');

const censusCalls = () => rpcCalls.filter((c) => c.fn === 'get_district_census_pop');

const DJ = '3017010100100010000';

function okRow(over: Partial<DistrictCensusPop> = {}): DistrictCensusPop {
  return {
    status: 'ok',
    district_id: 'DJ001',
    district_nm: '둔산 가짜거리',
    district_type: '발달상권',
    area_m2: 120000.5,
    n_overlap: 9,
    n_full: 3,
    cover_pct: 100,
    pop: 3120,
    pop_lo: 1840,
    pop_hi: 4610,
    hh: 1380,
    hh_lo: 820,
    hh_hi: 2050,
    emp: 5900,
    emp_lo: 2700,
    emp_hi: 11200,
    received_on: '2026-10-08',
    base_year: 2024,
    bnd_base_date: '2025-06-30',
    ...over,
  };
}

function wideRow(): DistrictCensusPop {
  return okRow({
    district_id: 'DJ002',
    district_nm: '시청역 가짜출구',
    n_overlap: 3,
    n_full: 0,
    cover_pct: 99.975,
    pop: 420,
    pop_lo: 0,
    pop_hi: 1380,
    hh: 190,
    hh_lo: 0,
    hh_hi: 640,
    emp: 4100,
    emp_lo: 0,
    emp_hi: 15300,
  });
}

function headRow(status: DistrictCensusPop['status']): DistrictCensusPop {
  return {
    ...okRow(),
    status,
    district_id: null,
    district_nm: null,
    district_type: null,
    area_m2: null,
    n_overlap: null,
    n_full: null,
    cover_pct: null,
    pop: null,
    pop_lo: null,
    pop_hi: null,
    hh: null,
    hh_lo: null,
    hh_hi: null,
    emp: null,
    emp_lo: null,
    emp_hi: null,
  };
}

function noDataRow(): DistrictCensusPop {
  return { ...headRow('no_data'), district_id: 'DJ003', district_nm: '유성 가짜골목', district_type: '골목상권' };
}

beforeEach(() => {
  rpcCalls.length = 0;
  gate.next = null;
  resetDataFreshnessCache();
  responses.census = { data: [okRow(), wideRow()], error: null };
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function openCard() {
  fireEvent.click(await screen.findByRole('button', { name: /상권 인구/ }));
}

describe('CensusPopSection — 자료가 있을 때', () => {
  it('★ 제목을 바꿔 끼운 접힌 카드 · 요약에 값 0 · p_pnu 로 묻는다', async () => {
    const { container } = render(<CensusPopSection pnu={DJ} />);
    expect(await screen.findByText('상권 인구 (통계청 집계구)')).toBeTruthy();
    expect(container.textContent).not.toContain('상권 인구 (서울시 공표)');
    const summary = container.querySelector('.card__summary')?.textContent ?? '';
    expect(summary).toBe('둔산 가짜거리 외 상권 1곳 · 통계청 집계구 2024년 통계');
    expect(summary).not.toMatch(/명/);
    expect(screen.getByRole('button', { name: /상권 인구/ }).getAttribute('aria-expanded')).toBe('false');
    expect(censusCalls()).toEqual([{ fn: 'get_district_census_pop', args: { p_pnu: DJ } }]);
    expect(container.querySelector('section.card.pop.pop--census')).not.toBeNull();
  });

  it('★ 받은 plan 의 역할·펼침은 그대로 · 제목·자료 갈래만 바꾼다', async () => {
    render(<CensusPopSection pnu={DJ} plan={{ ...SECTION_PLAN.pop, defaultOpen: true }} />);
    const btn = await screen.findByRole('button', { name: /상권 인구 \(통계청 집계구\)/ });
    expect(btn.getAttribute('aria-expanded')).toBe('true');
    expect(btn.textContent).toContain(SECTION_PLAN.pop.role);
  });

  it('★ 상권 둘 — 첫째 값 + 범위 · 둘째 범위만 · 덩이 제목 · 덩어리 발 · lead · C 배지 · 발 문구 다섯', async () => {
    const { container } = render(<CensusPopSection pnu={DJ} />);
    await openCard();
    expect(container.querySelector('.pop__lead')?.textContent).toBe(
      '이 건물이 속한 상권의 인구입니다 — 통계청 집계구 통계를 상권 모양에 맞춰 면적 비율로 나눈 어림값이고, 이 건물의 인구가 아닙니다.',
    );
    expect(container.querySelector('.pop__lead strong')?.textContent).toBe('이 건물이 속한 상권의 인구입니다');
    expect(container.querySelector('.pop__lead b')?.textContent).toBe('면적 비율로 나눈 어림값');
    expect(container.querySelector('.grade__badge.grade__badge--est')?.textContent).toBe('C등급 · 통계청 집계구 어림');
    expect(container.querySelector('.pop__badge-note')?.textContent).toBe(
      '통계청 SGIS 2024년 집계구 통계 · 2025년 6월 경계 · 사람이 신청해 받은 자료',
    );
    const blocks = container.querySelectorAll('.pop__district');
    expect(blocks).toHaveLength(2);
    const [a, b] = [...blocks];
    // 서버 차례 그대로(재정렬 0).
    expect(a.querySelector('.pop__name')?.textContent).toBe('둔산 가짜거리 · 발달상권');
    expect(b.querySelector('.pop__name')?.textContent).toBe('시청역 가짜출구 · 발달상권');
    expect(a.querySelector('.pop__chunk--resident .pop__chunk-h')?.textContent).toBe('사는 사람 (거주 인구)');
    expect(a.querySelector('.pop__chunk--resident .pop__num')?.textContent).toBe('약 3,120명');
    expect(a.querySelector('.pop__chunk--resident .pop__q')?.textContent).toBe('범위 1,840~4,610명');
    expect(a.querySelector('.pop__chunk--resident .pop__big')?.textContent).toBe(
      '약 3,120명범위 1,840~4,610명가구 약 1,380 (범위 820~2,050)',
    );
    expect(a.querySelector('.pop__chunk--emp .pop__chunk-h')?.textContent).toBe('사업체 종사자 (통계청)');
    expect(a.querySelector('.pop__chunk--emp .pop__big')?.textContent).toBe('약 5,900명범위 2,700~11,200명');
    expect(a.querySelector('.pop__note')?.textContent).toBe(
      '겹친 집계구 9개 · 통째로 든 집계구 3개 · 상권 넓이의 100% 를 덮음',
    );
    // 범위만 — 큰 숫자가 범위 · .pop__q 없음.
    expect(b.querySelector('.pop__chunk--resident .pop__num')?.textContent).toBe('범위 0~1,380명');
    expect(b.querySelector('.pop__chunk--resident .pop__q')).toBeNull();
    expect(b.querySelector('.pop__chunk--resident .pop__big')?.textContent).toBe('범위 0~1,380명가구 범위 0~640');
    expect(b.querySelector('.pop__chunk--emp .pop__big')?.textContent).toBe('범위 0~15,300명');
    expect(b.querySelector('.pop__note')?.textContent).toBe(
      '겹친 집계구 3개 · 통째로 든 집계구 0개 · 상권 넓이의 99.98% 를 덮음 — 범위가 넓어 값 대신 범위만 적은 칸이 있습니다',
    );
    const why = [...container.querySelectorAll('.pop__why li')].map((li) => li.textContent);
    expect(why).toEqual([
      '출처: 통계청 SGIS 통계지리정보서비스 집계구 통계(2024년)·집계구 경계(2025년 6월) — 자료신청 87909 · 공공누리 1유형.',
      '이 상권 안의 합계(어림)이며 이 건물의 값이 아닙니다.',
      '집계구(통계청이 통계를 내는 가장 작은 구역)는 상권 경계와 딱 맞지 않아, 겹친 넓이의 비율로 나눠 더했습니다. 범위의 아래 끝은 상권에 통째로 든 집계구만 더한 값, 위 끝은 조금이라도 겹친 집계구를 전부 더한 값입니다. 범위가 값의 2배를 넘으면 값 대신 범위만 적습니다.',
      '사업체 종사자는 통계청 전국사업체조사 기준이라 서울 카드의 「일하는 사람(직장인구)」과 같은 뜻이 아닙니다. 길단위인구는 서울시 자료라 서울만 있습니다.',
      '통계청이 다음 판을 내면 사람이 다시 받아 넣습니다(받은 날 기준 1년 뒤 예정).',
    ]);
    expect(container.querySelector('.pop__why li strong')?.textContent).toBe('이 상권 안의 합계(어림)이며 이 건물의 값이 아닙니다.');
    // 「일하는 사람」은 발 문구 한 곳뿐.
    expect((container.textContent ?? '').split('일하는 사람').length - 1).toBe(1);
  });

  it('★ no_data 상권 — 이름 + 한 줄 · 덩이 0', async () => {
    responses.census = { data: [okRow(), noDataRow()], error: null };
    const { container } = render(<CensusPopSection pnu={DJ} />);
    await openCard();
    const nd = container.querySelector('.pop__district--nodata')!;
    expect(nd.querySelector('.pop__name')?.textContent).toBe('유성 가짜골목 · 골목상권');
    expect(nd.querySelector('.pop__none')?.textContent).toBe('통계청 집계구와 겹치지 않아 이 상권의 인구를 셈하지 못했습니다.');
    expect(nd.querySelectorAll('.pop__chunk')).toHaveLength(0);
  });
});

describe('CensusPopSection — 건물 단위 셋', () => {
  it('좌표 없음 · 대전 밖 · 대전 상권 밖 — 한 문단 + 출처 줄', async () => {
    const cases: Array<[DistrictCensusPop['status'], string, string]> = [
      ['no_coord', DJ, '이 건물의 위치 정보가 없어 속한 상권을 찾지 못했습니다.'],
      [
        'not_daejeon',
        '1168010100100010000',
        '통계청 집계구 인구는 대전 상권에만 붙였습니다 — 이 건물(서울)에는 그 자료가 없습니다.',
      ],
      ['outside_daejeon_district', DJ, '이 건물이 속한 대전 상권이 없어 자료가 없습니다.'],
    ];
    for (const [status, pnu, body] of cases) {
      responses.census = { data: [headRow(status)], error: null };
      const { container, unmount } = render(<CensusPopSection pnu={pnu} />);
      await openCard();
      expect(container.querySelector('section.pop--none')).not.toBeNull();
      expect(container.querySelector('.pop__lead')?.textContent, status).toBe(body);
      expect(container.querySelector('.pop__src')?.textContent).toMatch(/^출처: 통계청 SGIS/);
      expect(container.querySelectorAll('.pop__district')).toHaveLength(0);
      unmount();
    }
  });
});

describe('CensusPopSection — 못 읽었을 때 · 필지가 바뀔 때', () => {
  it('★ 함수 없음(PGRST202) · 오류 · 0줄(표지 없음) · 섞인 답 → 카드째 숨긴다', async () => {
    for (const res of [
      { data: null, error: { code: 'PGRST202' } },
      { data: [okRow()], error: { message: 'boom' } },
      { data: [], error: null },
      { data: [okRow(), { ...wideRow(), pop_lo: 9999 }], error: null },
      { data: [headRow('no_coord'), okRow()], error: null },
    ]) {
      rpcCalls.length = 0;
      responses.census = res;
      const { container, unmount } = render(<CensusPopSection pnu={DJ} />);
      await waitFor(() => expect(censusCalls()).toHaveLength(1));
      await act(async () => {});
      expect(container.textContent, JSON.stringify(res)).toBe('');
      unmount();
    }
  });

  it('★ 필지가 바뀌면 옛 답을 곧바로 비우고, 늦게 온 앞 필지 답은 버린다', async () => {
    let releaseOld!: (v: { data: unknown; error: unknown }) => void;
    gate.next = new Promise((r) => (releaseOld = r));
    const { container, rerender } = render(<CensusPopSection pnu={DJ} />);
    await waitFor(() => expect(censusCalls()).toHaveLength(1));
    responses.census = { data: [okRow({ district_nm: '새 상권' })], error: null };
    rerender(<CensusPopSection pnu="3017010100100020000" />);
    await waitFor(() => expect(container.textContent).toMatch(/새 상권/));
    await act(async () => releaseOld({ data: [okRow({ district_nm: '옛 상권' })], error: null }));
    await act(async () => {});
    expect(container.textContent).toContain('새 상권');
    expect(container.textContent).not.toContain('옛 상권');
  });

  it('★ 필지가 바뀌면 새 답이 오기 전 옛 상권 이름이 남지 않는다', async () => {
    const { container, rerender } = render(<CensusPopSection pnu={DJ} />);
    await screen.findByText('상권 인구 (통계청 집계구)');
    expect(container.textContent).toContain('둔산 가짜거리');
    let release!: (v: { data: unknown; error: unknown }) => void;
    gate.next = new Promise((r) => (release = r));
    rerender(<CensusPopSection pnu="3017010100100020000" />);
    expect(container.textContent).toBe('');
    await act(async () => release({ data: [okRow({ district_nm: '새 상권' })], error: null }));
    expect(container.querySelector('.card__summary')?.textContent).toContain('새 상권');
  });

  it('★ 미리 보낸 이 pnu 의 답이 있으면 그것을 쓰고 다시 묻지 않는다', async () => {
    const prefetch = {
      pnu: DJ,
      results: new Map([
        ['get_district_census_pop', Promise.resolve({ data: [okRow({ district_nm: '미리 받은 상권' })], error: null })],
      ]),
    };
    render(<CensusPopSection pnu={DJ} prefetch={prefetch} />);
    await waitFor(() => expect(document.body.textContent).toMatch(/미리 받은 상권/));
    expect(censusCalls()).toHaveLength(0);
  });
});
