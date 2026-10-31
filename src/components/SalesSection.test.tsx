import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
import type { DistrictSales } from '../types';

/**
 * 「업종별 추정매출 (서울시 추정)」 카드 — 결정 0045 PR③(본보기 = OpenCloseSection.test).
 *
 * 여기서 특히 지키는 것
 *  ① 접힌 요약에 값이 없다 · 인자 이름이 `p_pnu` 다
 *  ② 못 읽었으면(PGRST202·오류·모양 이상) 카드째 숨긴다 — 「자료 없음」이라 적지 않는다
 *  ③ 필지가 바뀌면 옛 답을 비우고, 늦게 온 앞 필지 답은 버린다 · 미리 보낸 답이 있으면 다시 안 묻는다
 *  ④ 큰 숫자 = 3개월 합 그대로 · 막대 높이 비례 · 빠진 분기 '–' · 업종 표 5 + 그 밖 · 칩 hit / 상위 5 밖 / 없음
 *  ⑤ 빈 상태 넷 · 「…까지」 · 발 문구 다섯 · C 배지 · 판단 낱말·비율 글자 0
 */

const responses = {
  sales: { data: null as unknown, error: null as unknown },
};
/** 답을 늦게 돌려주고 싶을 때(늦은 답 버리기 시험). */
const gate: { next: Promise<{ data: unknown; error: unknown }> | null } = { next: null };
const rpcCalls: Array<{ fn: string; args: unknown }> = [];

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string, args?: unknown) => {
      rpcCalls.push({ fn, args });
      // 카드 머리 날짜 줄(S3)의 신선도 요청 — 이 카드의 질문이 아니라 함수 없음으로 답한다.
      if (fn === 'get_data_freshness') return Promise.resolve({ data: null, error: { code: 'PGRST202' } });
      const g = gate.next;
      gate.next = null;
      return g ?? Promise.resolve(responses.sales);
    },
  },
}));

const { SalesSection } = await import('./SalesSection');
const { resetDataFreshnessCache } = await import('../lib/loadDataFreshness');

const salesCalls = () => rpcCalls.filter((c) => c.fn === 'list_district_sales');

const PNU = '1168010500101590000';
const DAEJEON = '3011010700108770000';
const WINDOW = ['20262', '20261', '20254', '20253', '20252', '20251', '20244', '20243'];

const TOP = [
  { cd: 'CS100001', nm: '한식음식점', amt: 214_000_000, co: 4120, mdwk_amt: 1, wkend_amt: 1 },
  { cd: 'CS100010', nm: '커피-음료', amt: 139_000_000, co: 5310, mdwk_amt: 1, wkend_amt: 1 },
  { cd: 'CS300002', nm: '편의점', amt: 98_000_000, co: 3250, mdwk_amt: 1, wkend_amt: 1 },
  { cd: 'CS200028', nm: '미용실', amt: 61_000_000, co: 980, mdwk_amt: 1, wkend_amt: 1 },
  { cd: 'CS200001', nm: '일반교습학원', amt: 47_000_000, co: 410, mdwk_amt: 1, wkend_amt: 1 },
];

function okRow(over: Partial<DistrictSales> = {}): DistrictSales {
  return {
    status: 'ok',
    district_id: '3110001',
    district_nm: '○○역 2번 출구',
    district_type: '골목상권',
    latest_quarter: '20262',
    window_quarters: WINDOW,
    trend: [
      { quarter: '20262', amt: 723_000_000, co: 15208 },
      { quarter: '20261', amt: 654_000_000, co: 14000 },
      { quarter: '20254', amt: 760_000_000, co: 16000 },
      { quarter: '20253', amt: 623_000_000, co: 13000 },
      { quarter: '20252', amt: 707_000_000, co: 15000 },
      { quarter: '20251', amt: 676_000_000, co: 14500 },
      { quarter: '20243', amt: 692_000_000, co: 14800 },
    ],
    top: TOP,
    rest_cnt: 9,
    rest_amt: 164_000_000,
    rest_co: 1138,
    industries: [
      ...TOP.map(({ cd, nm, amt, co }) => ({ cd, nm, amt, co })),
      { cd: 'CS200029', nm: '네일숍', amt: 61_000_000, co: 980 },
    ],
    ...over,
  };
}

function headRow(status: DistrictSales['status']): DistrictSales {
  return {
    status,
    district_id: null,
    district_nm: null,
    district_type: null,
    latest_quarter: null,
    window_quarters: WINDOW,
    trend: null,
    top: null,
    rest_cnt: null,
    rest_amt: null,
    rest_co: null,
    industries: null,
  };
}

function noDataRow(): DistrictSales {
  return { ...headRow('no_data'), district_id: '3110002', district_nm: '△△ 골목', district_type: '골목상권' };
}

beforeEach(() => {
  rpcCalls.length = 0;
  gate.next = null;
  resetDataFreshnessCache();
  responses.sales = { data: [okRow(), noDataRow()], error: null };
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function openCard() {
  fireEvent.click(await screen.findByRole('button', { name: /업종별 추정매출/ }));
}

describe('SalesSection — 자료가 있을 때', () => {
  it('★ 접힌 카드로 서고, 요약에 값이 없다 · p_pnu 로 묻는다', async () => {
    const { container } = render(<SalesSection pnu={PNU} />);
    expect(await screen.findByText('업종별 추정매출 (서울시 추정)')).toBeTruthy();
    const summary = container.querySelector('.card__summary')?.textContent ?? '';
    expect(summary).toBe('○○역 2번 출구 외 상권 1곳 · 2026년 2분기까지 서울시 추정');
    expect(summary).not.toMatch(/억|만원|건/);
    expect(screen.getByRole('button', { name: /업종별 추정매출/ }).getAttribute('aria-expanded')).toBe('false');
    expect(salesCalls()).toEqual([{ fn: 'list_district_sales', args: { p_pnu: PNU } }]);
    // 자료가 찬 카드는 종이에 나온다 — 빈 상태 이름표가 없다.
    expect(container.querySelector('.card--empty')).toBeNull();
  });

  it('★ 큰 숫자 줄 = 3개월 합 그대로 · lead · C 배지 · 상권마다 덩어리(합치지 않는다)', async () => {
    const { container } = render(<SalesSection pnu={PNU} />);
    await openCard();
    expect(container.querySelector('.sales__lead')?.textContent).toBe(
      '이 건물이 속한 상권의 추정매출입니다 — 서울시가 카드 결제 금액으로 추정해 공표한 상권 값 그대로이고, 이 건물의 매출이 아닙니다.',
    );
    expect(container.querySelector('.grade__badge.grade__badge--est')?.textContent).toBe('C등급 · 서울시 추정');
    const blocks = container.querySelectorAll('.sales__district');
    expect(blocks).toHaveLength(2);
    expect(blocks[0].querySelector('.sales__name')?.textContent).toBe('○○역 2번 출구 · 골목상권');
    expect(blocks[0].querySelector('.sales__big')?.textContent).toBe(
      '2026년 2분기(3개월) 매출 7억 2,300만원결제 15,208건14업종 합',
    );
    expect(blocks[1].querySelector('.sales__none')?.textContent).toBe(
      '최근 2년(8분기) 동안 서울시가 이 상권의 추정매출 자료를 내지 않았습니다.',
    );
  });

  it('★ 흐름 막대 — 옛 → 최신 · 가장 큰 분기 = 100% · 빠진 분기 「–」 · 최신 칸 짙은 색 · 눈금 글', async () => {
    const { container } = render(<SalesSection pnu={PNU} />);
    await openCard();
    expect(container.querySelector('.sales__scale')?.textContent).toBe('막대가 꽉 차면 7억 6,000만원(3개월 합)');
    const cols = [...container.querySelectorAll('.sales__col')];
    expect(cols.map((c) => c.getAttribute('data-quarter'))).toEqual([...WINDOW].reverse());
    const bar = (q: string) => container.querySelector<HTMLElement>(`.sales__col[data-quarter="${q}"] .sales__bar`);
    expect(bar('20254')?.style.height).toBe('100%');
    expect(Number.parseFloat(bar('20262')!.style.height)).toBeCloseTo((723 / 760) * 100, 4);
    expect(bar('20262')?.classList.contains('sales__bar--last')).toBe(true);
    expect(bar('20261')?.classList.contains('sales__bar--last')).toBe(false);
    const gap = container.querySelector('.sales__col[data-quarter="20244"]');
    expect(gap?.querySelector('.sales__bar')).toBeNull();
    expect(gap?.querySelector('.sales__gap')?.textContent).toBe('–');
    expect(bar('20262')?.getAttribute('aria-label')).toBe('2026년 2분기 매출 7억 2,300만원 · 결제 15,208건 (3개월 합)');
    expect(screen.getByText('‘–’ 칸은 그 분기에 서울시가 이 상권 자료를 내지 않은 것입니다.')).toBeTruthy();
    // 눈금 글은 상권 덩어리 안 흐름 그림 머리 아래(검사 뒤 보완 F1) · 해 글은 시안 꼴 「’24」(F10 · 온전한 해는 title).
    expect(container.querySelector('.sales__district .sales__trend .sales__scale')).not.toBeNull();
    const firstYear = container.querySelector('.sales__col[data-quarter="20243"] .sales__tick-year');
    expect(firstYear?.textContent).toBe('’24');
    expect(firstYear?.getAttribute('title')).toBe('2024년');
  });

  it('★ 상권마다 제 눈금(검사 뒤 보완 F1) — 관광특구 1,163억 · 골목 19.9억이어도 두 상권 모두 가장 큰 분기가 100% · 눈금 글도 상권마다', async () => {
    responses.sales = {
      data: [
        okRow({
          district_id: 'small',
          district_nm: '작은 골목',
          trend: [
            { quarter: '20262', amt: 1_990_000_000, co: 100 },
            { quarter: '20261', amt: 995_000_000, co: 50 },
          ],
        }),
        okRow({
          district_id: 'big',
          district_nm: '큰 관광특구',
          district_type: '관광특구',
          trend: [
            { quarter: '20262', amt: 116_300_000_000, co: 9000 },
            { quarter: '20261', amt: 58_150_000_000, co: 4500 },
          ],
        }),
      ],
      error: null,
    };
    const { container } = render(<SalesSection pnu={PNU} />);
    await openCard();
    const blocks = container.querySelectorAll('.sales__district');
    expect(blocks).toHaveLength(2);
    const h = (b: Element, q: string) =>
      Number.parseFloat(b.querySelector<HTMLElement>(`.sales__col[data-quarter="${q}"] .sales__bar`)!.style.height);
    expect(h(blocks[0], '20262')).toBe(100);
    expect(h(blocks[0], '20261')).toBeCloseTo(50, 4);
    expect(h(blocks[1], '20262')).toBe(100);
    expect(h(blocks[1], '20261')).toBeCloseTo(50, 4);
    expect([...container.querySelectorAll('.sales__scale')].map((p) => p.textContent)).toEqual([
      '막대가 꽉 차면 19억 9,000만원(3개월 합)',
      '막대가 꽉 차면 1,163억원(3개월 합)',
    ]);
    // 눈금 글은 상권 덩어리 안에만 — 카드 머리 공통 눈금 줄은 없다.
    expect(container.querySelector('.sales > .card__body > .sales__scale')).toBeNull();
  });

  it('★ 업종 표 5줄 + 그 밖 · 막대 길이 = 첫 줄 대비 · 발 문구 다섯(현금 문장 없음)', async () => {
    const { container } = render(<SalesSection pnu={PNU} />);
    await openCard();
    const rows = [...container.querySelectorAll('.sales__table tbody tr')];
    expect(rows).toHaveLength(6);
    expect(rows.map((r) => r.querySelector('th')?.textContent)).toEqual([
      '한식음식점',
      '커피-음료',
      '편의점',
      '미용실',
      '일반교습학원',
      '그 밖 9업종 (더해서)',
    ]);
    expect(rows[0].querySelectorAll('td')[0].textContent).toBe('2억 1,400만원');
    expect(rows[0].querySelectorAll('td')[1].textContent).toBe('4,120건');
    expect(rows[0].querySelector<HTMLElement>('.sales__w i')?.style.width).toBe('100%');
    expect(Number.parseFloat(rows[1].querySelector<HTMLElement>('.sales__w i')!.style.width)).toBeCloseTo((139 / 214) * 100, 4);
    expect(container.querySelector('.sales__table thead th')?.textContent).toBe('업종 (2026년 2분기)');
    const why = [...container.querySelectorAll('.sales__why li')].map((li) => li.textContent);
    expect(why).toEqual([
      '출처: 서울시 상권분석서비스 「상권-추정매출」(열린데이터광장 · 공공누리 1유형 출처표시).',
      '이 상권 전체의 값이며 이 건물의 값이 아닙니다. 상권이 여럿이면 상권마다 따로 적고 더하지 않습니다.',
      '금액·건수는 서울시가 공표한 분기(3개월) 합계 그대로입니다 — 서울시 화면은 이 값을 점포당 월평균으로 바꿔 보여 줍니다.',
      '카드사 결제 금액에 서울시가 보정 비율을 곱해 추정한 값이고, 산출식·표본은 서울시가 공개하지 않습니다.',
      '업종은 서울시 생활밀접업종 기준이라 「업종 분포」 카드(소상공인시장진흥공단)와 다릅니다.',
    ]);
    expect(container.textContent).not.toContain('현금');
  });

  it('★ 칩 카페 — 짝 업종 줄 hit + 꼬리 「 · 고른 업종(카페)」', async () => {
    const { container } = render(<SalesSection pnu={PNU} chip="카페" />);
    await openCard();
    const hit = container.querySelectorAll('.sales__hit');
    expect(hit).toHaveLength(1);
    expect(hit[0].querySelector('th')?.textContent).toBe('커피-음료 · 고른 업종(카페)');
    expect(container.querySelector('.sales__chip-out')).toBeNull();
    expect(container.querySelector('.sales__chip-none')).toBeNull();
  });

  it('★ 칩 미용 — 상위 5 안 hit · 상위 5 밖 한 줄 · 빠진 이름 한 줄(더하지 않는다)', async () => {
    const { container } = render(<SalesSection pnu={PNU} chip="미용" />);
    await openCard();
    expect(container.querySelector('.sales__hit th')?.textContent).toBe('미용실 · 고른 업종(미용)');
    expect([...container.querySelectorAll('.sales__chip-out')].map((p) => p.textContent)).toEqual([
      '고른 업종(미용): 네일숍 6,100만원 · 980건 (3개월 합 · 상위 5 밖)',
    ]);
    expect(container.querySelector('.sales__chip-part')?.textContent).toBe(
      '고른 업종 가운데 피부관리실은 이 자료에 없습니다',
    );
  });

  it('★ 칩 업종이 이 자료에 없으면 「고른 업종(편의점)은 이 자료에 없습니다」', async () => {
    const r = okRow();
    responses.sales = {
      data: [
        {
          ...r,
          top: TOP.filter((x) => x.cd !== 'CS300002'),
          industries: r.industries!.filter((x) => x.cd !== 'CS300002'),
        },
      ],
      error: null,
    };
    const { container } = render(<SalesSection pnu={PNU} chip="편의점" />);
    await openCard();
    expect(container.querySelector('.sales__chip-none')?.textContent).toBe('고른 업종(편의점)은 이 자료에 없습니다');
    expect(container.querySelector('.sales__hit')).toBeNull();
  });

  it('이 상권 자료가 창 최신보다 옛 분기에서 멈췄으면 「…까지입니다.」', async () => {
    responses.sales = { data: [okRow({ latest_quarter: '20254' })], error: null };
    const { container } = render(<SalesSection pnu={PNU} />);
    await openCard();
    expect(container.querySelector('.sales__note')?.textContent).toBe('이 상권 자료는 2025년 4분기까지입니다.');
  });

  it('⛔ 펼친 글 어디에도 비율 글자·판단 낱말·금지어가 없다', async () => {
    const { container } = render(<SalesSection pnu={PNU} chip="미용" />);
    await openCard();
    const text = container.textContent ?? '';
    expect(/[%％]|퍼센트|\d\s*배/.test(text)).toBe(false);
    for (const w of ['많', '높은', '낮은', '부족', '충분', '추천', '적정가', '감정가', '평가액']) {
      expect(text.includes(w), w).toBe(false);
    }
  });
});

describe('SalesSection — 빈 상태 넷', () => {
  it('서울 밖(not_seoul) — 카드가 서서 그 사실(대전)', async () => {
    responses.sales = { data: [headRow('not_seoul')], error: null };
    const { container } = render(<SalesSection pnu={DAEJEON} />);
    await openCard();
    expect(container.querySelector('.card__summary')?.textContent).toBe(
      '서울 상권만 다루는 자료라 이 건물(대전)에는 없습니다',
    );
    expect(container.querySelector('.sales__lead')?.textContent).toBe(
      '서울시 상권분석서비스는 서울 상권만 다룹니다 — 이 건물(대전)에는 그 자료가 없습니다.',
    );
  });

  it('상권 밖 · 좌표 없음 — 개업·폐업 카드와 같은 글', async () => {
    responses.sales = { data: [headRow('outside_seoul_district')], error: null };
    const { container, unmount } = render(<SalesSection pnu={PNU} />);
    await openCard();
    expect(container.querySelector('.sales__lead')?.textContent).toBe('이 건물이 속한 서울시 상권이 없어 자료가 없습니다.');
    unmount();
    responses.sales = { data: [headRow('no_coord')], error: null };
    const again = render(<SalesSection pnu={PNU} />);
    await openCard();
    expect(again.container.querySelector('.sales__lead')?.textContent).toBe(
      '이 건물의 위치 정보가 없어 속한 상권을 찾지 못했습니다.',
    );
  });

  it('창 안 자료 없음(no_data 만) — 요약 한 줄 · 덩어리 글', async () => {
    responses.sales = { data: [noDataRow()], error: null };
    const { container } = render(<SalesSection pnu={PNU} />);
    await openCard();
    expect(container.querySelector('.card__summary')?.textContent).toBe(
      '△△ 골목 · 최근 2년(8분기) 안에 서울시 추정매출 자료가 없습니다',
    );
    expect(container.querySelector('.sales__scale')).toBeNull();
  });
});

describe('SalesSection — 못 읽었을 때 · 필지가 바뀔 때', () => {
  it('★ 함수가 아직 없으면(PGRST202) 카드를 통째로 생략한다', async () => {
    responses.sales = { data: null, error: { code: 'PGRST202' } };
    const { container } = render(<SalesSection pnu={PNU} />);
    await waitFor(() => expect(salesCalls()).toHaveLength(1));
    await act(async () => {});
    expect(container.textContent).toBe('');
  });

  it('★ 모양이 이상하면(섞인 답 · 상권 줄 창 빔) 카드째 숨긴다 — 「자료 없음」이라 적지 않는다', async () => {
    responses.sales = { data: [okRow(), { ...okRow(), co: 1, rest_cnt: -1 }], error: null };
    const { container, unmount } = render(<SalesSection pnu={PNU} />);
    await waitFor(() => expect(salesCalls()).toHaveLength(1));
    await act(async () => {});
    expect(container.textContent).toBe('');
    unmount();
    responses.sales = { data: [okRow({ window_quarters: [] })], error: null };
    const again = render(<SalesSection pnu={PNU} />);
    await waitFor(() => expect(salesCalls()).toHaveLength(2));
    await act(async () => {});
    expect(again.container.textContent).toBe('');
  });

  it('★ 필지가 바뀌면 옛 답을 비운다 — 새 답이 오기 전 앞 상권 숫자가 안 남는다', async () => {
    const { container, rerender } = render(<SalesSection pnu={PNU} />);
    await screen.findByText('업종별 추정매출 (서울시 추정)');
    let release!: (v: { data: unknown; error: unknown }) => void;
    gate.next = new Promise((r) => (release = r));
    rerender(<SalesSection pnu="1168010100100020000" />);
    // 새 답을 기다리는 동안 카드가 없다(앞 상권 숫자가 붙어 있지 않다).
    expect(container.textContent).toBe('');
    await act(async () => release({ data: [okRow({ district_nm: '새 상권' })], error: null }));
    expect(container.querySelector('.card__summary')?.textContent).toContain('새 상권');
  });

  it('★ 늦은 답은 버린다 — 필지가 바뀐 뒤 도착한 앞 필지 답이 새 필지 카드에 붙지 않는다', async () => {
    let releaseOld!: (v: { data: unknown; error: unknown }) => void;
    gate.next = new Promise((r) => (releaseOld = r));
    const { container, rerender } = render(<SalesSection pnu={PNU} />);
    await waitFor(() => expect(salesCalls()).toHaveLength(1));
    responses.sales = { data: [okRow({ district_nm: '새 상권' })], error: null };
    rerender(<SalesSection pnu="1168010100100020000" />);
    await waitFor(() => expect(document.body.textContent).toMatch(/새 상권/));
    await act(async () => releaseOld({ data: [okRow({ district_nm: '옛 상권' })], error: null }));
    await act(async () => {});
    expect(container.textContent).toContain('새 상권');
    expect(container.textContent).not.toContain('옛 상권');
  });

  it('★ 미리 보낸 이 pnu 의 답이 있으면 그것을 쓰고 다시 묻지 않는다 · 다른 pnu 것이면 스스로 묻는다', async () => {
    const prefetch = {
      pnu: PNU,
      results: new Map([['list_district_sales', Promise.resolve({ data: [okRow({ district_nm: '미리 받은 상권' })], error: null })]]),
    };
    const { unmount } = render(<SalesSection pnu={PNU} prefetch={prefetch} />);
    await waitFor(() => expect(document.body.textContent).toMatch(/미리 받은 상권/));
    expect(salesCalls()).toHaveLength(0);
    unmount();
    render(<SalesSection pnu="1168010100100020000" prefetch={prefetch} />);
    await waitFor(() => expect(document.body.textContent).toMatch(/○○역 2번 출구/));
    expect(salesCalls()).toEqual([{ fn: 'list_district_sales', args: { p_pnu: '1168010100100020000' } }]);
  });
});
