import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
import type { DistrictPop } from '../types';

/**
 * 「상권 인구 (서울시 공표)」 카드 — 결정 0045 PR③(본보기 = OpenCloseSection.test).
 *
 * 여기서 특히 지키는 것
 *  ① 접힌 요약에 값이 없다 · 인자 이름이 `p_pnu` 다
 *  ② 못 읽었으면(PGRST202·오류·모양 이상) 카드째 숨긴다
 *  ③ 필지가 바뀌면 옛 답을 비우고, 늦게 온 앞 필지 답은 버린다 · 미리 보낸 답이 있으면 다시 안 묻는다
 *  ④ 길단위인구 3개월간 그대로 · 미니 막대 둘 · 사는/일하는 「YYYY년 기준」(= value_quarter) · 끊긴 상권 「…까지」
 *  ⑤ 빈 상태 넷 · 발 문구 넷 · C 배지 · 판단 낱말·비율 글자 0
 */

const responses = {
  pop: { data: null as unknown, error: null as unknown },
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
      return g ?? Promise.resolve(responses.pop);
    },
  },
}));

const { PopSection } = await import('./PopSection');
const { resetDataFreshnessCache } = await import('../lib/loadDataFreshness');

const popCalls = () => rpcCalls.filter((c) => c.fn === 'list_district_pop');

const PNU = '1168010500101590000';
const DAEJEON = '3011010700108770000';

const FLOW = {
  tot: 412560,
  ml: 190100,
  fml: 222460,
  tmzon_00_06: 58000,
  tmzon_06_11: 82300,
  tmzon_11_14: 69700,
  tmzon_14_17: 68000,
  tmzon_17_21: 84000,
  tmzon_21_24: 50400,
  mon: 59900,
  tues: 59900,
  wed: 60500,
  thur: 59900,
  fri: 59900,
  sat: 57500,
  sun: 55000,
};

function okRow(over: Partial<DistrictPop> = {}): DistrictPop {
  return {
    status: 'ok',
    district_id: '3110001',
    district_nm: '○○역 2번 출구',
    district_type: '골목상권',
    flow_table_quarter: '20262',
    flow_quarter: '20262',
    flow: FLOW,
    resident_value_quarter: '20234',
    resident_last_quarter: '20262',
    resident: { tot: 2310, ml: 1090, fml: 1220, tot_hshld: 1120 },
    worker_value_quarter: '20244',
    worker_last_quarter: '20262',
    worker: { tot: 6840, ml: 3900, fml: 2940 },
    ...over,
  };
}

function headRow(status: DistrictPop['status']): DistrictPop {
  return {
    status,
    district_id: null,
    district_nm: null,
    district_type: null,
    flow_table_quarter: null,
    flow_quarter: null,
    flow: null,
    resident_value_quarter: null,
    resident_last_quarter: null,
    resident: null,
    worker_value_quarter: null,
    worker_last_quarter: null,
    worker: null,
  };
}

function noDataRow(): DistrictPop {
  return { ...headRow('no_data'), district_id: '3110002', district_nm: '△△ 골목', district_type: '골목상권' };
}

beforeEach(() => {
  rpcCalls.length = 0;
  gate.next = null;
  resetDataFreshnessCache();
  responses.pop = { data: [okRow(), noDataRow()], error: null };
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function openCard() {
  fireEvent.click(await screen.findByRole('button', { name: /상권 인구/ }));
}

describe('PopSection — 자료가 있을 때', () => {
  it('★ 접힌 카드로 서고, 요약에 값이 없다 · p_pnu 로 묻는다', async () => {
    const { container } = render(<PopSection pnu={PNU} />);
    expect(await screen.findByText('상권 인구 (서울시 공표)')).toBeTruthy();
    const summary = container.querySelector('.card__summary')?.textContent ?? '';
    expect(summary).toBe(
      '○○역 2번 출구 외 상권 1곳 · 길단위인구 2026년 2분기 · 사는 사람 2023년 · 일하는 사람 2024년 기준',
    );
    expect(summary).not.toMatch(/명/);
    expect(screen.getByRole('button', { name: /상권 인구/ }).getAttribute('aria-expanded')).toBe('false');
    expect(popCalls()).toEqual([{ fn: 'list_district_pop', args: { p_pnu: PNU } }]);
    expect(container.querySelector('.card--empty')).toBeNull();
  });

  it('★ 덩이 셋 — 길단위 「3개월간」 큰 숫자 · 사는/일하는 「YYYY년 기준」 · lead · C 배지 · 발 문구 넷', async () => {
    const { container } = render(<PopSection pnu={PNU} />);
    await openCard();
    expect(container.querySelector('.pop__lead')?.textContent).toBe(
      '이 건물이 속한 상권의 인구입니다 — 서울시가 공표한 상권 값 그대로이고, 이 건물의 인구가 아닙니다.',
    );
    expect(container.querySelector('.grade__badge.grade__badge--est')?.textContent).toBe('C등급 · 서울시 집계');
    // 배지 옆 작은 글(검사 뒤 보완 F4 · 메인 문구).
    expect(container.querySelector('.pop__badge-line .pop__badge-note')?.textContent).toBe(
      '서울시 상권분석서비스 · 생활인구·주민등록·통신사 자료로 서울시가 셈',
    );
    const block = container.querySelector('.pop__district')!;
    expect(block.querySelector('.pop__name')?.textContent).toBe('○○역 2번 출구 · 골목상권');
    const flow = block.querySelector('.pop__chunk--flow')!;
    expect(flow.querySelector('.pop__chunk-h')?.textContent).toBe('길단위인구 (서울시 집계)');
    expect(flow.querySelector('.pop__big')?.textContent).toBe('412,560명2026년 2분기 3개월간남 190,100 · 여 222,460');
    expect(block.querySelector('.pop__chunk--resident .pop__big')?.textContent).toBe(
      // 가구 수는 싣지 않는다(메인 결정 나 — 서울시 화면 가구세대 수와 다른 값).
      // 서울시가 안 바꾼 해 괄호(검사 뒤 보완 F2 · 시안 원문).
      '2,310명2023년 기준 (서울시가 2024·2025년에는 안 바꿈)남 1,090 · 여 1,220',
    );
    expect(block.querySelector('.pop__chunk--worker .pop__big')?.textContent).toBe(
      '6,840명2024년 기준 (서울시가 2025년에는 안 바꿈)남 3,900 · 여 2,940',
    );
    const why = [...container.querySelectorAll('.pop__why li')].map((li) => li.textContent);
    expect(why).toEqual([
      '출처: 서울시 상권분석서비스 「상권-길단위인구」·「상권-상주인구」·「상권-직장인구」(열린데이터광장 · 공공누리 1유형).',
      '이 상권 전체의 값이며 이 건물의 값이 아닙니다.',
      '길단위인구는 서울시·KT 생활인구를 10m 길 단위로 나눈 값의 3개월 합입니다(서울시 칸 이름은 「유동인구」). 사는 사람은 주민등록, 일하는 사람은 통신사 자료를 바탕으로 서울시가 셉니다.',
      '사는 사람·일하는 사람은 서울시가 1년에 한 번 바꿉니다 — 「YYYY년 기준」은 값이 마지막으로 바뀐 해입니다.',
    ]);
    // no_data 상권.
    expect(container.querySelectorAll('.pop__district')[1].querySelector('.pop__none')?.textContent).toBe(
      '서울시가 이 상권의 인구 자료를 내지 않았습니다.',
    );
  });

  it('★ 미니 막대 둘 — 시간대 6 · 요일 7 · 높이 = 값 ÷ 묶음 최댓값 · 눈금 글 · 읽어 주기 글', async () => {
    const { container } = render(<PopSection pnu={PNU} />);
    await openCard();
    const figs = container.querySelectorAll('.pop__mini .pop__bars-fig');
    expect(figs).toHaveLength(2);
    expect(figs[0].querySelector('.pop__scale')?.textContent).toBe('시간대 · 꽉 차면 84,000명(3개월간)');
    expect(figs[1].querySelector('.pop__scale')?.textContent).toBe('요일 · 꽉 차면 60,500명(3개월간)');
    const time = [...figs[0].querySelectorAll<HTMLElement>('.pop__bar')];
    const day = [...figs[1].querySelectorAll<HTMLElement>('.pop__bar')];
    expect(time).toHaveLength(6);
    expect(day).toHaveLength(7);
    expect(time[4].style.height).toBe('100%');
    expect(Number.parseFloat(time[0].style.height)).toBeCloseTo((58000 / 84000) * 100, 4);
    expect(time[0].getAttribute('aria-label')).toBe('시간대 0~6 58,000명');
    expect([...figs[1].querySelectorAll('.pop__tick')].map((t) => t.textContent)).toEqual(['월', '화', '수', '목', '금', '토', '일']);
  });

  it('★ 끊긴 상권 — 사는 사람 값이 없으면 「…까지입니다」 · 길단위가 옛 분기면 「…까지입니다」', async () => {
    responses.pop = {
      data: [
        okRow({
          flow_quarter: '20254',
          resident: null,
          resident_value_quarter: null,
          resident_last_quarter: '20224',
          worker: null,
          worker_value_quarter: null,
          worker_last_quarter: null,
        }),
      ],
      error: null,
    };
    const { container } = render(<PopSection pnu={PNU} />);
    await openCard();
    expect(container.querySelector('.pop__chunk--flow .pop__note')?.textContent).toBe(
      '이 상권 길단위인구 자료는 2025년 4분기까지입니다',
    );
    expect(container.querySelector('.pop__chunk--resident .pop__note')?.textContent).toBe(
      '이 상권 사는 사람 자료는 2022년 4분기까지입니다',
    );
    // 값도 마지막 분기도 없으면 덩이 자체가 없다.
    expect(container.querySelector('.pop__chunk--worker')).toBeNull();
  });

  it('⛔ 펼친 글 어디에도 비율 글자·나누기 낱말·판단 낱말·금지어가 없다', async () => {
    const { container } = render(<PopSection pnu={PNU} />);
    await openCard();
    const text = container.textContent ?? '';
    expect(/[%％]|퍼센트|\d\s*배/.test(text)).toBe(false);
    for (const w of ['하루 평균', '점포당', '/ha', '많', '높은', '낮은', '부족', '충분', '추천', '적정가', '감정가', '평가액']) {
      expect(text.includes(w), w).toBe(false);
    }
  });
});

describe('PopSection — 빈 상태 넷', () => {
  it('서울 밖 · 상권 밖 · 좌표 없음 — 개업·폐업 카드와 같은 글', async () => {
    responses.pop = { data: [headRow('not_seoul')], error: null };
    const { container, unmount } = render(<PopSection pnu={DAEJEON} />);
    await openCard();
    expect(container.querySelector('.card__summary')?.textContent).toBe('서울 상권만 다루는 자료라 이 건물(대전)에는 없습니다');
    expect(container.querySelector('.pop__lead')?.textContent).toBe(
      '서울시 상권분석서비스는 서울 상권만 다룹니다 — 이 건물(대전)에는 그 자료가 없습니다.',
    );
    unmount();
    responses.pop = { data: [headRow('outside_seoul_district')], error: null };
    const b = render(<PopSection pnu={PNU} />);
    await openCard();
    expect(b.container.querySelector('.pop__lead')?.textContent).toBe('이 건물이 속한 서울시 상권이 없어 자료가 없습니다.');
    b.unmount();
    responses.pop = { data: [headRow('no_coord')], error: null };
    const c = render(<PopSection pnu={PNU} />);
    await openCard();
    expect(c.container.querySelector('.pop__lead')?.textContent).toBe('이 건물의 위치 정보가 없어 속한 상권을 찾지 못했습니다.');
  });

  it('no_data 만 — 요약 한 줄', async () => {
    responses.pop = { data: [noDataRow()], error: null };
    const { container } = render(<PopSection pnu={PNU} />);
    await screen.findByText('상권 인구 (서울시 공표)');
    expect(container.querySelector('.card__summary')?.textContent).toBe('△△ 골목 · 서울시 인구 자료가 없습니다');
  });
});

describe('PopSection — 못 읽었을 때 · 필지가 바뀔 때', () => {
  it('★ 함수 없음(PGRST202) · 오류 · 모양 이상이면 카드째 숨긴다', async () => {
    for (const res of [
      { data: null, error: { code: 'PGRST202' } },
      { data: [okRow()], error: { message: 'boom' } },
      { data: [okRow(), { ...okRow(), flow: { ...FLOW, sun: 1.5 } }], error: null },
    ]) {
      rpcCalls.length = 0;
      responses.pop = res;
      const { container, unmount } = render(<PopSection pnu={PNU} />);
      await waitFor(() => expect(popCalls()).toHaveLength(1));
      await act(async () => {});
      expect(container.textContent, JSON.stringify(res.error)).toBe('');
      unmount();
    }
  });

  it('★ 필지가 바뀌면 옛 답을 비우고, 늦게 온 앞 필지 답은 버린다', async () => {
    let releaseOld!: (v: { data: unknown; error: unknown }) => void;
    gate.next = new Promise((r) => (releaseOld = r));
    const { container, rerender } = render(<PopSection pnu={PNU} />);
    await waitFor(() => expect(popCalls()).toHaveLength(1));
    responses.pop = { data: [okRow({ district_nm: '새 상권' })], error: null };
    rerender(<PopSection pnu="1168010100100020000" />);
    await waitFor(() => expect(document.body.textContent).toMatch(/새 상권/));
    await act(async () => releaseOld({ data: [okRow({ district_nm: '옛 상권' })], error: null }));
    await act(async () => {});
    expect(container.textContent).toContain('새 상권');
    expect(container.textContent).not.toContain('옛 상권');
  });

  it('★ 미리 보낸 이 pnu 의 답이 있으면 그것을 쓰고 다시 묻지 않는다', async () => {
    const prefetch = {
      pnu: PNU,
      results: new Map([['list_district_pop', Promise.resolve({ data: [okRow({ district_nm: '미리 받은 상권' })], error: null })]]),
    };
    render(<PopSection pnu={PNU} prefetch={prefetch} />);
    await waitFor(() => expect(document.body.textContent).toMatch(/미리 받은 상권/));
    expect(popCalls()).toHaveLength(0);
  });

  it('★ 필지가 바뀌면 옛 답을 곧바로 비운다 — 새 답이 오기 전 앞 상권 숫자가 안 남는다(검사 뒤 보완 F6)', async () => {
    const { container, rerender } = render(<PopSection pnu={PNU} />);
    await screen.findByText('상권 인구 (서울시 공표)');
    expect(container.textContent).toContain('○○역 2번 출구');
    let release!: (v: { data: unknown; error: unknown }) => void;
    gate.next = new Promise((r) => (release = r));
    rerender(<PopSection pnu="1168010100100020000" />);
    // 새 답을 기다리는 동안 카드가 없다(앞 상권 이름·숫자가 붙어 있지 않다).
    expect(container.textContent).toBe('');
    await act(async () => release({ data: [okRow({ district_nm: '새 상권' })], error: null }));
    expect(container.querySelector('.card__summary')?.textContent).toContain('새 상권');
  });

  it('★ ok 인데 셋 다 없는 줄은 「자료 없음」 덩어리로 그린다 — 빈 덩어리 금지(검사 뒤 보완 F12)', async () => {
    responses.pop = {
      data: [okRow({ flow: null, flow_quarter: null, resident: null, worker: null })],
      error: null,
    };
    const { container } = render(<PopSection pnu={PNU} />);
    await openCard();
    const block = container.querySelector('.pop__district')!;
    expect(block.classList.contains('pop__district--nodata')).toBe(true);
    expect(block.querySelector('.pop__none')?.textContent).toBe('서울시가 이 상권의 인구 자료를 내지 않았습니다.');
    expect(block.querySelectorAll('.pop__chunk')).toHaveLength(0);
    expect(container.querySelector('.card__summary')?.textContent).toBe('○○역 2번 출구 · 서울시 인구 자료가 없습니다');
  });
});
