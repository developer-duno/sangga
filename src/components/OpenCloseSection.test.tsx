import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import type { DistrictOpenClose, OpenCloseQuarter } from '../types';

/**
 * "상권 개업·폐업 (서울시 공표)" 카드 — 결정 0033 R2.
 *
 * 여기서 특히 지키는 것
 *  ① 못 읽었으면(PGRST202·모양 이상) 아무 말도 안 한다 — "자료 없음"이라 적으면 거짓이다.
 *  ② 빈 상태 넷(서울 밖 · 상권 밖 · 좌표 없음 · 창 안 자료 없음)은 카드가 서서 그 사실을 적는다.
 *  ③ 표본 < 30 이면 비율을 적지 않고 개수만 + 사실 문장.
 *  ④ 추이는 옛 → 최신, 빠진 분기는 빈 칸, 막대 높이는 **숫자로** 본다.
 *  ⑤ 인자 이름이 `p_pnu` 다.
 */

const responses = {
  oc: { data: null as unknown, error: null as unknown },
  /** 「전부 보기」 함수(결정 0038 H · V6)의 답 — 기본은 함수 없음(PGRST202): 단추 없이 지금 그대로. */
  all: { data: null as unknown, error: { code: 'PGRST202' } as unknown },
};
/** 전부 보기 답을 늦게 돌려주고 싶을 때 — 주면 그 Promise 를 쓴다(늦은 답 버리기 시험). */
const allGate: { next: Promise<{ data: unknown; error: unknown }> | null } = { next: null };
const rpcCalls: Array<{ fn: string; args: unknown }> = [];

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string, args?: unknown) => {
      rpcCalls.push({ fn, args });
      if (fn === 'list_district_openclose_all') {
        const gated = allGate.next;
        allGate.next = null;
        return gated ?? Promise.resolve(responses.all);
      }
      return Promise.resolve(responses.oc);
    },
  },
}));

const { OpenCloseSection } = await import('./OpenCloseSection');
const { resetDataFreshnessCache } = await import('../lib/loadDataFreshness');

/**
 * 이 카드가 부른 것만 — 카드 머리 날짜 줄(S3)의 신선도 요청은 뺀다(맨 아래 표와 나눠 쓰는 한 번의 요청이라
 * 이 카드의 질문이 아니다). ⓘ 그 요청은 시험마다 새로 나간다(아래 beforeEach 가 보관을 비운다) — 시험 차례에 기대지 않게.
 */
const ocCalls = () => rpcCalls.filter((c) => c.fn === 'list_district_openclose');
/** 「전부 보기」 함수를 부른 것만. */
const allCalls = () => rpcCalls.filter((c) => c.fn === 'list_district_openclose_all');

const PNU = '1168010500101590000';
const DAEJEON = '3011010700108770000';
const WINDOW = ['20262', '20261', '20254', '20253', '20252', '20251', '20244', '20243'];

function q(over: Partial<OpenCloseQuarter> & { quarter: string }): OpenCloseQuarter {
  return {
    similr_induty_stor_co: 441,
    stor_co: 378,
    frc_stor_co: 63,
    opbiz_stor_co: 5,
    clsbiz_stor_co: 9,
    opbiz_rt: 1.13,
    clsbiz_rt: 2.04,
    ...over,
  };
}

function okRow(over: Partial<DistrictOpenClose> = {}): DistrictOpenClose {
  return {
    status: 'ok',
    district_id: '3120218',
    district_nm: '코엑스',
    district_type: '발달상권',
    latest_quarter: '20262',
    quarters: [
      q({ quarter: '20262' }),
      q({ quarter: '20261', opbiz_stor_co: 10, clsbiz_stor_co: 18, opbiz_rt: 2.5, clsbiz_rt: 4.0 }),
      q({ quarter: '20244', opbiz_rt: 1.0, clsbiz_rt: 2.0 }),
    ],
    industries: [
      {
        svc_induty_cd: 'CS300011',
        svc_induty_cd_nm: '일반의류',
        similr_induty_stor_co: 90,
        stor_co: 90,
        frc_stor_co: 0,
        opbiz_stor_co: 1,
        clsbiz_stor_co: 4,
        opbiz_rt: 1.0,
        clsbiz_rt: 4.0,
      },
      {
        svc_induty_cd: 'CS100001',
        svc_induty_cd_nm: '한식음식점',
        similr_induty_stor_co: 1,
        stor_co: 1,
        frc_stor_co: 0,
        opbiz_stor_co: 2,
        clsbiz_stor_co: 0,
        opbiz_rt: 200,
        clsbiz_rt: null,
      },
    ],
    other_industries: {
      industry_count: 47,
      similr_induty_stor_co: 172,
      stor_co: 149,
      frc_stor_co: 23,
      opbiz_stor_co: 1,
      clsbiz_stor_co: 1,
      opbiz_rt: 0.58,
      clsbiz_rt: 0.58,
    },
    window_quarters: WINDOW,
    ...over,
  };
}

function headRow(status: DistrictOpenClose['status']): DistrictOpenClose {
  return {
    status,
    district_id: null,
    district_nm: null,
    district_type: null,
    latest_quarter: null,
    quarters: null,
    industries: null,
    other_industries: null,
    window_quarters: WINDOW,
  };
}

beforeEach(() => {
  rpcCalls.length = 0;
  allGate.next = null;
  responses.all = { data: null, error: { code: 'PGRST202' } };
  resetDataFreshnessCache();
  responses.oc = {
    data: [okRow(), okRow({ district_id: '3001496', district_nm: '강남 마이스 관광특구', district_type: '관광특구' })],
    error: null,
  };
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function openCard() {
  fireEvent.click(await screen.findByRole('button', { name: /상권 개업·폐업/ }));
}

describe('OpenCloseSection — 서울 자료가 있을 때', () => {
  it('★ 접힌 카드로 서고, 요약은 상권 이름과 언제까지의 자료인지만 말한다(값 없음) · p_pnu 로 묻는다', async () => {
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    expect(await screen.findByText('상권 개업·폐업 (서울시 공표)')).toBeTruthy();
    // ⛔ 접힌 요약에는 값(개수·비율)이 없다 — 한정어 없이 이 건물 값으로 읽힌다(👤 F1).
    const summary = container.querySelector('.card__summary')?.textContent ?? '';
    expect(summary).toBe('코엑스 외 상권 1곳 · 2026년 2분기까지 서울시 공표');
    expect(summary).not.toContain('%');
    expect(summary).not.toMatch(/(개업|폐업|점포)\s*[\d,]+곳/);
    expect(screen.getByRole('button').getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelector('.card__body')?.hasAttribute('hidden')).toBe(true);
    // ⓘ 카드 머리 날짜 줄(S3)이 신선도 표를 묻는 것은 뺀다 — 맨 아래 표와 나눠 쓰는 한 번의 요청이라 이 카드의 질문이 아니다.
    // 상권 줄이 왔으니 「전부 보기」 함수도 한 번(같은 p_pnu · 결정 0038 H · V6) — 미리 부르기가 아니라 카드가 묻는다.
    await waitFor(() => expect(allCalls()).toHaveLength(1));
    expect(rpcCalls.filter((c) => c.fn !== 'get_data_freshness')).toEqual([
      { fn: 'list_district_openclose', args: { p_pnu: PNU } },
      { fn: 'list_district_openclose_all', args: { p_pnu: PNU } },
    ]);
  });

  it('펼치면 상권마다 이름·유형·큰 숫자·분기 도장, 그리고 발 문구 넷', async () => {
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    const names = [...container.querySelectorAll('.oc__name')].map((n) => n.textContent);
    expect(names).toEqual(['코엑스 · 발달상권', '강남 마이스 관광특구 · 관광특구']);
    const first = container.querySelectorAll('.oc__district')[0];
    expect([...first.querySelectorAll('.oc__latest .oc__num')].map((n) => n.textContent)).toEqual([
      '점포 441곳(프랜차이즈 포함)',
      // 프랜차이즈 비중(👤 물결 1-B) — 분모는 점포(프랜차이즈 포함) 441 · stor_co(378)면 16.67% 가 된다.
      '프랜차이즈 63곳 (점포의 14.29% · 서울시 공표 개수로 계산)',
      '개업 5곳 · 개업률(분기) 1.13%',
      '폐업 9곳 · 폐업률(분기) 2.04%',
    ]);
    expect(first.querySelector('.oc__quarter')?.textContent).toBe('2026년 2분기');
    expect(container.querySelector('.oc__lead')?.textContent).toContain('이 건물이 속한 상권의 개업·폐업입니다');
    const text = container.textContent ?? '';
    expect(text).toContain(
      '출처: 서울시 상권분석서비스(점포-상권) · 서울 열린데이터광장 · 공공누리 1유형(출처표시)',
    );
    expect(text).toContain('상권 전체 값이며 이 건물의 값이 아닙니다');
    expect(text).toContain('서울시 100업종 기준이라 ‘둘레의 업종 분포’ 카드(소상공인시장진흥공단');
    expect(text).toContain(
      '서울시 계산식(개업·폐업 점포 ÷ 점포(프랜차이즈 포함) × 100)으로 낸 값입니다 — 서울시 자료는 이 점포 수를 ‘유사 업종 점포 수’라고 부릅니다.',
    );
    // 👤 화면 낱말은 '점포(프랜차이즈 포함)' — '유사 업종 점포'는 발 문구의 서울시 이름 설명 한 곳뿐.
    expect(text.split('유사 업종 점포').length - 1).toBe(1);
    // 최신 분기가 창의 최신과 같으면 "까지입니다" 문장은 없다.
    expect(text).not.toContain('까지입니다');
    // ★ 자료가 있는 상권에는 빈 상태 문장이 없다.
    expect(container.querySelector('.oc__none')).toBeNull();
    for (const empty of ['자료를 내지 않았습니다', '자료가 없습니다', '찾지 못했습니다', '서울 상권만 다룹니다']) {
      expect(text).not.toContain(empty);
    }
    // 추이 제목에 '분기별'과 창 크기.
    expect(container.querySelector('.oc__trend-cap')?.textContent).toContain('분기별 개업률·폐업률 — 최근 2년(8분기)');
    for (const banned of ['적정가', '평가액', '감정가', '정확하지 않을 수', '참고용']) {
      expect(text).not.toContain(banned);
    }
  });

  it('★ 8분기 추이 — 옛 → 최신 순, 빠진 분기는 빈 칸, 막대 높이는 숫자로', async () => {
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    const block = container.querySelectorAll('.oc__district')[0];
    const cols = [...block.querySelectorAll('.oc__col')] as HTMLElement[];
    expect(cols.map((c) => c.dataset.quarter)).toEqual([...WINDOW].reverse());
    expect(cols.map((c) => c.className.replace('oc__col oc__col--', ''))).toEqual([
      'missing',
      'ok',
      'missing',
      'missing',
      'missing',
      'missing',
      'ok',
      'ok',
    ]);
    // 빈 칸에는 막대가 아예 없다(0 높이 막대도 아니다).
    expect(cols[0].querySelectorAll('.oc__bar')).toHaveLength(0);
    expect(cols[0].querySelector('.oc__gap')?.getAttribute('aria-label')).toBe('2024년 3분기 자료 없음');
    // 최댓값 = 4.0(20261 폐업률) → 100%.
    const h = (el: Element | null) => parseFloat((el as HTMLElement).style.height);
    expect(h(cols[6].querySelector('.oc__bar--close'))).toBeCloseTo(100, 6);
    expect(h(cols[6].querySelector('.oc__bar--open'))).toBeCloseTo(62.5, 6);
    expect(h(cols[7].querySelector('.oc__bar--open'))).toBeCloseTo(28.25, 6);
    expect(h(cols[7].querySelector('.oc__bar--close'))).toBeCloseTo(51, 6);
    expect(h(cols[1].querySelector('.oc__bar--close'))).toBeCloseTo(50, 6);
    expect(cols[7].querySelector('.oc__bar--open')?.getAttribute('aria-label')).toBe('2026년 2분기 개업률 1.13%');
  });

  it('★ 업종 표는 접혀 있고, 공표 비율 그대로(null 은 –) · 점포 30곳 미만 업종은 비율만 – · 마지막 줄 그 밖 N업종 (더해서 계산)', async () => {
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    const det = container.querySelector('.oc__ind') as HTMLDetailsElement;
    expect(det.tagName).toBe('DETAILS');
    expect(det.open).toBe(false);
    expect(det.querySelector('summary')?.textContent).toBe('업종별 표 — 2026년 2분기 · 점포가 많은 순');
    expect([...det.querySelectorAll('thead th')].map((th) => th.textContent)).toEqual([
      '업종',
      '점포(프랜차이즈 포함)',
      '개업 (개업률·분기)',
      '폐업 (폐업률·분기)',
    ]);
    const rows = [...det.querySelectorAll('tbody tr')].map((tr) =>
      [...tr.children].map((c) => c.textContent),
    );
    expect(rows).toEqual([
      ['일반의류', '90곳', '1곳 (1%)', '4곳 (4%)'],
      // 점포 1곳 업종의 공표 비율 200% 는 적지 않는다 — 개수는 그대로(2026-10-06).
      ['한식음식점', '1곳', '2곳 (–)', '0곳 (–)'],
      ['그 밖 47업종 (더해서 계산)', '172곳', '1곳 (0.58%)', '1곳 (0.58%)'],
    ]);
    // '–' 의 두 뜻을 표 아래 한 줄로 밝힌다(2026-10-06 — 검사관 🟡 · 사장님 결정).
    expect(det.querySelector('table + .oc__note')?.textContent).toBe(
      "'–' = 점포(프랜차이즈 포함)가 30곳이 안 되거나 서울시가 비율을 내지 않은 칸입니다.",
    );
  });

  it('★ 업종 줄 비율의 경계 — 점포 30곳은 보이고 29곳은 – (카드 위 큰 숫자와 같은 30 · 2026-10-06)', async () => {
    const ind = (cd: string, similr: number) => ({
      svc_induty_cd: cd,
      svc_induty_cd_nm: cd,
      similr_induty_stor_co: similr,
      stor_co: similr,
      frc_stor_co: 0,
      opbiz_stor_co: 1,
      clsbiz_stor_co: 6,
      opbiz_rt: 3.33,
      clsbiz_rt: 200,
    });
    responses.oc = {
      data: [okRow({ industries: [ind('서른', 30), ind('스물아홉', 29), ind('셋', 3)] })],
      error: null,
    };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    const rows = [...container.querySelectorAll('.oc__ind tbody tr:not(.oc__other)')].map((tr) =>
      [...tr.children].map((c) => c.textContent),
    );
    expect(rows).toEqual([
      ['서른', '30곳', '1곳 (3.33%)', '6곳 (200%)'],
      ['스물아홉', '29곳', '1곳 (–)', '6곳 (–)'],
      ['셋', '3곳', '1곳 (–)', '6곳 (–)'],
    ]);
  });

  it('업종이 열 개 이하라 그 밖 줄이 null 이면 그 줄은 없다', async () => {
    responses.oc = { data: [okRow({ other_industries: null })], error: null };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    expect(container.querySelector('.oc__other')).toBeNull();
    expect(container.querySelectorAll('.oc__ind tbody tr')).toHaveLength(2);
  });

  it('★ 표본 < 30 — 비율 없이 개수만 + 사실 문장(변명 문구 없음)', async () => {
    responses.oc = {
      data: [
        okRow({
          quarters: [
            q({ quarter: '20262', similr_induty_stor_co: 22, frc_stor_co: 4, opbiz_stor_co: 1, clsbiz_stor_co: 2, opbiz_rt: null, clsbiz_rt: null }),
          ],
        }),
      ],
      error: null,
    };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    expect([...container.querySelectorAll('.oc__latest .oc__num')].map((n) => n.textContent)).toEqual([
      '점포 22곳(프랜차이즈 포함)',
      // 분모가 30곳이 안 되면 프랜차이즈도 비율 없이 개수만.
      '프랜차이즈 4곳',
      '개업 1곳',
      '폐업 2곳',
    ]);
    expect(container.textContent).toContain('표본 22곳(점포 · 프랜차이즈 포함) — 30곳이 안 돼 비율은 적지 않습니다.');
    expect(container.querySelector('.oc__latest')?.textContent).not.toContain('%');
    // 그 분기 칸은 막대 없이 '표본'.
    const last = [...container.querySelectorAll('.oc__col')].pop()!;
    expect(last.className).toContain('oc__col--nosample');
    expect(last.querySelectorAll('.oc__bar')).toHaveLength(0);
  });

  it('★ 비율이 null 이어도 점포가 30곳 이상이면 표본 문장을 띄우지 않는다(F5)', async () => {
    responses.oc = {
      data: [okRow({ quarters: [q({ quarter: '20262', similr_induty_stor_co: 45, opbiz_rt: null, clsbiz_rt: null })] })],
      error: null,
    };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    // 큰 숫자 아래 표본 문장(.oc__note)이 없다 — 추이 칸 설명의 '표본' 낱말과는 다르다.
    expect(container.textContent).not.toContain('표본 45곳');
    expect([...container.querySelectorAll('.oc__district > .oc__note')]).toHaveLength(0);
    // 개업·폐업 칸에 비율이 없다(프랜차이즈 비중은 점포 45곳이라 따로 선다 — 다른 칸이다).
    for (const sel of ['.oc__num--open', '.oc__num--close']) {
      expect(container.querySelector(`.oc__latest ${sel}`)?.textContent).not.toContain('%');
    }
  });

  it('★ 막대 눈금은 카드 하나에 하나 — 두 상권이 같은 눈금이고, 눈금 글이 보인다(F4)', async () => {
    responses.oc = {
      data: [
        okRow(),
        okRow({
          district_id: '3001496',
          district_nm: '강남 마이스 관광특구',
          quarters: [q({ quarter: '20262', opbiz_rt: 1.0, clsbiz_rt: 2.0 })],
        }),
      ],
      error: null,
    };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    expect(container.querySelector('.oc__scale')?.textContent).toBe(
      '막대가 꽉 차면 4%(분기) · 보는 기간(최근 2년(8분기))의 가장 큰 값 기준',
    );
    const h = (el: Element | null) => parseFloat((el as HTMLElement).style.height);
    const blocks = container.querySelectorAll('.oc__district');
    const lastOf = (b: Element) => [...b.querySelectorAll('.oc__col')].pop()!;
    // 첫 상권 최댓값 4.0 = 100% · 둘째 상권 2.0 은 제 최댓값이 아니라 공통 눈금 기준 50%.
    expect(h(blocks[0].querySelectorAll('.oc__col')[6].querySelector('.oc__bar--close'))).toBeCloseTo(100, 6);
    expect(h(lastOf(blocks[1]).querySelector('.oc__bar--close'))).toBeCloseTo(50, 6);
    expect(h(lastOf(blocks[1]).querySelector('.oc__bar--open'))).toBeCloseTo(25, 6);
  });

  it('★ 눈금은 첫 상권이 아니라 카드 전체 최댓값 — 둘째 상권이 더 크면 그것이 꽉 찬다(F4)', async () => {
    // 재검사관 V4(눈금을 첫 상권 최댓값으로) 생존 변이를 잡는 짝 — 위 시험은 첫 상권이 최댓값이라 못 가른다.
    responses.oc = {
      data: [
        okRow(),
        okRow({
          district_id: '3001496',
          district_nm: '강남 마이스 관광특구',
          quarters: [q({ quarter: '20262', opbiz_rt: 2.0, clsbiz_rt: 8.0 })],
        }),
      ],
      error: null,
    };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    expect(container.querySelector('.oc__scale')?.textContent).toBe(
      '막대가 꽉 차면 8%(분기) · 보는 기간(최근 2년(8분기))의 가장 큰 값 기준',
    );
    const h = (el: Element | null) => parseFloat((el as HTMLElement).style.height);
    const blocks = container.querySelectorAll('.oc__district');
    const lastOf = (b: Element) => [...b.querySelectorAll('.oc__col')].pop()!;
    expect(h(lastOf(blocks[1]).querySelector('.oc__bar--close'))).toBeCloseTo(100, 6);
    expect(h(blocks[0].querySelectorAll('.oc__col')[6].querySelector('.oc__bar--close'))).toBeCloseTo(50, 6);
  });

  it('그릴 막대가 없으면(비율 전부 null) 눈금 글도 없다', async () => {
    responses.oc = {
      data: [okRow({ quarters: [q({ quarter: '20262', similr_induty_stor_co: 10, opbiz_rt: null, clsbiz_rt: null })] })],
      error: null,
    };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    expect(container.querySelector('.oc__scale')).toBeNull();
  });

  it('★ 이 상권의 최신 분기가 창의 최신보다 이르면 그 사실을 적는다', async () => {
    responses.oc = {
      data: [okRow({ latest_quarter: '20261', quarters: [q({ quarter: '20261' })] })],
      error: null,
    };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    expect(container.textContent).toContain('이 상권 자료는 2026년 1분기까지입니다.');
    expect(container.querySelector('.oc__quarter')?.textContent).toBe('2026년 1분기');
  });
});

describe('OpenCloseSection — 프랜차이즈 비중 (👤 물결 1-B)', () => {
  it('★ ok 상권 줄마다 최신 분기 큰 숫자 줄에 서고, 접힌 요약에는 없다', async () => {
    responses.oc = {
      data: [
        okRow(),
        okRow({
          district_id: '3001496',
          district_nm: '강남 마이스 관광특구',
          quarters: [q({ quarter: '20262', similr_induty_stor_co: 665, stor_co: 545, frc_stor_co: 120 })],
        }),
      ],
      error: null,
    };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    expect([...container.querySelectorAll('.oc__latest .oc__num--frc')].map((n) => n.textContent)).toEqual([
      '프랜차이즈 63곳 (점포의 14.29% · 서울시 공표 개수로 계산)',
      '프랜차이즈 120곳 (점포의 18.05% · 서울시 공표 개수로 계산)',
    ]);
    // ⛔ 요약에는 값을 적지 않는다(기존 결정) — 프랜차이즈도 마찬가지.
    expect(container.querySelector('.card__summary')?.textContent).not.toContain('프랜차이즈');
  });

  it('★ 빈 상태(서울 밖 · 창 안 자료 없음)에는 프랜차이즈 줄이 없다', async () => {
    responses.oc = { data: [headRow('not_seoul')], error: null };
    const { container, unmount } = render(<OpenCloseSection pnu={DAEJEON} />);
    await openCard();
    expect(container.querySelector('.oc__num--frc')).toBeNull();
    expect(container.textContent).not.toContain('프랜차이즈 ');
    unmount();

    responses.oc = {
      data: [okRow({ status: 'no_data', latest_quarter: null, quarters: null, industries: null, other_industries: null })],
      error: null,
    };
    const second = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    expect(second.container.querySelector('.oc__num--frc')).toBeNull();
  });
});

describe('OpenCloseSection — 빈 상태 넷 (카드는 선다)', () => {
  it('★ not_seoul — 지역 이름은 pnu 앞 두 자리로 표에서 고른다', async () => {
    responses.oc = { data: [headRow('not_seoul')], error: null };
    const { container } = render(<OpenCloseSection pnu={DAEJEON} />);
    await openCard();
    expect(container.querySelector('.oc__lead')?.textContent).toBe(
      '서울시 상권분석서비스는 서울 상권만 다룹니다 — 이 건물(대전)에는 그 자료가 없습니다.',
    );
    expect(container.querySelector('.card__summary')?.textContent).toBe(
      '서울 상권만 다루는 자료라 이 건물(대전)에는 없습니다',
    );
    expect(container.querySelector('.oc__col')).toBeNull();
  });

  it('not_seoul — 표에 없는 코드면 괄호를 뺀다', async () => {
    responses.oc = { data: [headRow('not_seoul')], error: null };
    const { container } = render(<OpenCloseSection pnu="9911010700108770000" />);
    await openCard();
    expect(container.querySelector('.oc__lead')?.textContent).toBe(
      '서울시 상권분석서비스는 서울 상권만 다룹니다 — 이 건물에는 그 자료가 없습니다.',
    );
  });

  it('outside_seoul_district', async () => {
    responses.oc = { data: [headRow('outside_seoul_district')], error: null };
    const { container } = render(<OpenCloseSection pnu="1156011000100400000" />);
    await openCard();
    expect(container.querySelector('.oc__lead')?.textContent).toBe(
      '이 건물이 속한 서울시 상권이 없어 자료가 없습니다.',
    );
  });

  it('no_coord', async () => {
    responses.oc = { data: [headRow('no_coord')], error: null };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    expect(container.querySelector('.oc__lead')?.textContent).toBe(
      '이 건물의 위치 정보가 없어 속한 상권을 찾지 못했습니다.',
    );
  });

  it('★ no_data — 상권 이름을 적고, 최근 2년(8분기) 자료를 내지 않았다고 적는다', async () => {
    responses.oc = {
      data: [okRow({ status: 'no_data', latest_quarter: null, quarters: null, industries: null, other_industries: null })],
      error: null,
    };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    expect(container.querySelector('.oc__name')?.textContent).toBe('코엑스 · 발달상권');
    expect(container.querySelector('.oc__none')?.textContent).toBe(
      '최근 2년(8분기) 동안 서울시가 이 상권의 개업·폐업 자료를 내지 않았습니다.',
    );
    expect(container.querySelector('.oc__col')).toBeNull();
  });
});

describe('OpenCloseSection — 못 읽었을 때 · 건물이 바뀔 때 · 미리 보낸 답', () => {
  it('★ 함수가 아직 없으면(PGRST202) 카드를 통째로 생략한다', async () => {
    responses.oc = { data: null, error: { code: 'PGRST202' } };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await waitFor(() => expect(ocCalls()).toHaveLength(1));
    await Promise.resolve();
    expect(container.textContent).toBe('');
  });

  it('★ 응답에 error 가 있으면 data 모양이 맞아도 카드를 세우지 않는다', async () => {
    responses.oc = { data: [okRow()], error: { message: 'boom' } };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await waitFor(() => expect(ocCalls()).toHaveLength(1));
    await Promise.resolve();
    expect(container.textContent).toBe('');
  });

  it('★ 상권 줄인데 창이 비어 있으면 카드를 숨긴다(F6 — "최근 0분기"를 지어내지 않는다)', async () => {
    responses.oc = { data: [okRow({ window_quarters: [] })], error: null };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await waitFor(() => expect(ocCalls()).toHaveLength(1));
    await Promise.resolve();
    expect(container.textContent).toBe('');
    expect(console.warn).toHaveBeenCalled();
  });

  it('★ 숫자 칸 열쇠가 빠지면 카드를 숨긴다(F5)', async () => {
    const { stor_co: _drop, ...noStor } = q({ quarter: '20262' });
    responses.oc = { data: [okRow({ quarters: [noStor as OpenCloseQuarter] })], error: null };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await waitFor(() => expect(ocCalls()).toHaveLength(1));
    await Promise.resolve();
    expect(container.textContent).toBe('');
  });

  it('뜻밖의 모양이면 카드만 사라진다', async () => {
    responses.oc = { data: [{ status: 'closed', window_quarters: [] }], error: null };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await waitFor(() => expect(ocCalls()).toHaveLength(1));
    await Promise.resolve();
    expect(container.textContent).toBe('');
  });

  it('★ pnu 가 바뀌면 옛 답을 지운다', async () => {
    const { rerender, container } = render(<OpenCloseSection pnu={PNU} />);
    await screen.findByText('상권 개업·폐업 (서울시 공표)');
    responses.oc = { data: null, error: null };
    rerender(<OpenCloseSection pnu="1168010100100020000" />);
    await waitFor(() => expect(container.querySelector('.oc')).toBeNull());
    expect(ocCalls().map((c) => c.args)).toEqual([{ p_pnu: PNU }, { p_pnu: '1168010100100020000' }]);
  });

  it('★ 미리 보낸 이 pnu 의 답이 있으면 그것을 쓰고 다시 묻지 않는다', async () => {
    const prefetch = {
      pnu: DAEJEON,
      results: new Map([
        ['list_district_openclose', Promise.resolve({ data: [headRow('not_seoul')], error: null })],
      ]),
    };
    const { container } = render(<OpenCloseSection pnu={DAEJEON} prefetch={prefetch} />);
    await screen.findByText('상권 개업·폐업 (서울시 공표)');
    expect(container.querySelector('.card__summary')?.textContent).toContain('대전');
    expect(ocCalls()).toHaveLength(0);
  });
});

/**
 * 창업자 업종 칩(👤 결정 0036 결정 18 ⑨ · ⑮) — 칩을 고르면 업종 표에서 짝 업종 줄을 굵게 하고
 * 표(`details`)를 펼친 채로 둔다(강조가 안 보이면 의미 없다). 짝 업종이 상위 표에 없으면 한 줄.
 */
describe('OpenCloseSection — 창업자 업종 칩', () => {
  function details(container: HTMLElement) {
    return [...container.querySelectorAll('details.oc__ind')] as HTMLDetailsElement[];
  }
  function hitRows(container: HTMLElement) {
    return [...container.querySelectorAll('.oc__table tr.oc__hit th')].map((e) => e.textContent);
  }

  it('★ 한식 칩이면 업종 표가 펼쳐진 채 한식음식점 줄만 굵다', async () => {
    const { container } = render(<OpenCloseSection pnu={PNU} chip="한식" />);
    await openCard();
    const ds = details(container);
    expect(ds).toHaveLength(2);
    expect(ds.every((d) => d.open)).toBe(true);
    expect(hitRows(container)).toEqual(['한식음식점', '한식음식점']);
    // 양성 대조 — 일반의류 줄은 굵지 않다.
    expect(container.querySelectorAll('.oc__table tr:not(.oc__hit) th').length).toBeGreaterThan(0);
    expect(screen.queryByText(/상위 업종에 없습니다/)).toBeNull();
  });

  it('전체 칩이면 지금 그대로 — 표는 접히고 굵은 줄이 없다', async () => {
    const { container } = render(<OpenCloseSection pnu={PNU} chip="전체" />);
    await openCard();
    expect(details(container).every((d) => !d.open)).toBe(true);
    expect(container.querySelector('.oc__hit')).toBeNull();
    expect(screen.queryByText(/상위 업종에 없습니다/)).toBeNull();
  });

  it('★ 짝 업종이 상위 표에 없으면 표 위에 한 줄(괄호 = 칩 이름) · 표는 그래도 펼친다', async () => {
    const { container } = render(<OpenCloseSection pnu={PNU} chip="미용" />);
    await openCard();
    expect(await screen.findAllByText('고른 업종(미용)은 이 상권 점포 수 상위 업종에 없습니다')).toHaveLength(2);
    expect(container.querySelector('.oc__hit')).toBeNull();
    expect(details(container).every((d) => d.open)).toBe(true);
  });

  it('★ 칩을 바꾸면 열린 카드도 따라 바뀐다', async () => {
    const { container, rerender } = render(<OpenCloseSection pnu={PNU} chip="전체" />);
    await openCard();
    expect(details(container).every((d) => !d.open)).toBe(true);
    rerender(<OpenCloseSection pnu={PNU} chip="한식" />);
    expect(details(container).every((d) => d.open)).toBe(true);
    expect(hitRows(container)).toEqual(['한식음식점', '한식음식점']);
    rerender(<OpenCloseSection pnu={PNU} chip="전체" />);
    expect(container.querySelector('.oc__hit')).toBeNull();
  });

  it('대전(not_seoul)이면 칩을 골라도 지금 글 그대로', async () => {
    responses.oc = { data: [headRow('not_seoul')], error: null };
    const { container } = render(<OpenCloseSection pnu={DAEJEON} chip="카페" />);
    await openCard();
    expect(container.querySelector('.oc__lead')?.textContent).toBe(
      '서울시 상권분석서비스는 서울 상권만 다룹니다 — 이 건물(대전)에는 그 자료가 없습니다.',
    );
    expect(screen.queryByText(/상위 업종에 없습니다/)).toBeNull();
  });
});

describe('OpenCloseSection — 창업자 업종 칩 (검사 뒤 보완)', () => {
  function ind(cd: string, nm: string) {
    return {
      svc_induty_cd: cd,
      svc_induty_cd_nm: nm,
      similr_induty_stor_co: 40,
      stor_co: 40,
      frc_stor_co: 0,
      opbiz_stor_co: 1,
      clsbiz_stor_co: 1,
      opbiz_rt: 2.5,
      clsbiz_rt: 2.5,
    };
  }
  const NONE = /고른 업종\(.+\)은 이 상권 점포 수 상위 업종에 없습니다/;
  const PART = /^고른 업종 가운데 /;

  it('★ F2 칩 사이를 오가면 손님이 접어 둔 업종 표가 다시 펼쳐진다', async () => {
    const { container, rerender } = render(<OpenCloseSection pnu={PNU} chip="카페" />);
    await openCard();
    const d = container.querySelector('details.oc__ind') as HTMLDetailsElement;
    expect(d.open).toBe(true);
    d.open = false;
    rerender(<OpenCloseSection pnu={PNU} chip="미용" />);
    expect((container.querySelector('details.oc__ind') as HTMLDetailsElement).open).toBe(true);
  });

  it('★ F5 짝 업종이 일부만 표에 있으면 빠진 것만 이름으로 한 줄 — 하나도 없을 때 문구는 안 뜬다', async () => {
    responses.oc = {
      data: [
        okRow({
          industries: [
            ind('CS300011', '일반의류'),
            ind('CS200001', '일반교습학원'),
            ind('CS200002', '외국어학원'),
          ],
        }),
      ],
      error: null,
    };
    render(<OpenCloseSection pnu={PNU} chip="학원" />);
    await openCard();
    expect(
      screen.getByText('고른 업종 가운데 예술학원·컴퓨터학원·스포츠 강습은 상위 업종에 없습니다'),
    ).toBeTruthy();
    expect(screen.queryByText(NONE)).toBeNull();
  });

  it('★ F5 짝 업종이 정확히 하나만 빠지면 그 하나만 이름으로 한 줄', async () => {
    responses.oc = {
      data: [okRow({ industries: [ind('CS200028', '미용실'), ind('CS200030', '피부관리실')] })],
      error: null,
    };
    render(<OpenCloseSection pnu={PNU} chip="미용" />);
    await openCard();
    expect(screen.getByText('고른 업종 가운데 네일숍은 상위 업종에 없습니다')).toBeTruthy();
    expect(screen.queryByText(NONE)).toBeNull();
  });

  it('F5 짝 업종이 다 있으면 줄이 없다 · 하나도 없으면 기존 문구만(양성 대조)', async () => {
    responses.oc = {
      data: [
        okRow({
          industries: [ind('CS200028', '미용실'), ind('CS200029', '네일숍'), ind('CS200030', '피부관리실')],
        }),
      ],
      error: null,
    };
    const { rerender } = render(<OpenCloseSection pnu={PNU} chip="미용" />);
    await openCard();
    expect(screen.queryByText(PART)).toBeNull();
    expect(screen.queryByText(NONE)).toBeNull();

    rerender(<OpenCloseSection pnu={PNU} chip="편의점" />);
    expect(screen.getByText('고른 업종(편의점)은 이 상권 점포 수 상위 업종에 없습니다')).toBeTruthy();
    expect(screen.queryByText(PART)).toBeNull();
  });
});

/**
 * 「전부 보기 (N분기)」(결정 0038 H · V6) — 기본 8분기 그대로 + 단추. N 은 서버 칸 `total_quarters` 값 그대로.
 * 전부 답에서 8분기 창의 no_data 가 ok 로 바뀐 상권은 '이 상권 자료는 ○년 ○분기까지' 가 꼭 함께 선다.
 * 실패(함수 없음·오류·모양 이상)면 단추만 없다 · 늦은 답은 버린다 · 필지가 바뀌면 전부 보기 상태를 비운다.
 */
describe('OpenCloseSection — 전부 보기 (결정 0038 H · V6)', () => {
  /** 최신 → 옛 n 분기(표 전체 창). 분기 글자는 시험 안에서만 만든다. */
  function windowOf(n: number): string[] {
    const out: string[] = [];
    let y = 2026;
    let qq = 2;
    for (let i = 0; i < n; i++) {
      out.push(`${y}${qq}`);
      qq -= 1;
      if (qq === 0) {
        qq = 4;
        y -= 1;
      }
    }
    return out;
  }

  /** 전부 답의 한 줄 — 8분기 줄에 옛 분기(들)를 더하고 창·total_quarters 를 바꾼다. */
  function allRowOf(row: DistrictOpenClose, n: number, extra: OpenCloseQuarter[] = []) {
    return {
      ...row,
      quarters: row.quarters === null ? (extra.length ? extra : null) : [...row.quarters, ...extra],
      window_quarters: windowOf(n),
      total_quarters: n,
    };
  }

  const OLD = windowOf(13)[12]; // 13분기 창의 가장 옛 분기 — 8분기 창 밖
  const bigOld = q({ quarter: OLD, opbiz_rt: 5, clsbiz_rt: 20 });

  async function allButton() {
    return (await screen.findByRole('button', { name: /^전부 보기 \(/ })) as HTMLButtonElement;
  }

  it('★ 단추 글의 N 은 total_quarters 칸 값 그대로(13 — 8 도 22 도 아니다) · 답이 오기 전엔 단추가 없다', async () => {
    let release!: (v: { data: unknown; error: unknown }) => void;
    allGate.next = new Promise((r) => (release = r));
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    expect(container.querySelector('.oc__all')).toBeNull();
    const eight = responses.oc.data as DistrictOpenClose[];
    release({ data: eight.map((r) => allRowOf(r, 13, [bigOld])), error: null });
    expect((await allButton()).textContent).toBe('전부 보기 (13분기)');
    expect((await allButton()).getAttribute('aria-expanded')).toBe('false');
    expect(allCalls()).toEqual([{ fn: 'list_district_openclose_all', args: { p_pnu: PNU } }]);
  });

  it('★ 누르면 모든 상권이 전부 창 — 옛 → 최신 · 넓은 그림은 밀기 상자 안 · 눈금은 그 창 기준 · 서버 재호출 0 · 되돌리기', async () => {
    const eight = responses.oc.data as DistrictOpenClose[];
    responses.all = { data: eight.map((r) => allRowOf(r, 13, [bigOld])), error: null };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    expect(container.querySelectorAll('.oc__district')[0].querySelectorAll('.oc__col')).toHaveLength(8);
    expect(container.querySelector('.oc__scroll')).toBeNull();
    fireEvent.click(await allButton());

    const blocks = [...container.querySelectorAll('.oc__district')];
    expect(blocks).toHaveLength(2);
    for (const b of blocks) {
      const cols = [...b.querySelectorAll('.oc__col')] as HTMLElement[];
      expect(cols.map((c) => c.dataset.quarter)).toEqual([...windowOf(13)].reverse());
      expect(b.querySelector('.oc__scroll .oc__cols.oc__cols--wide')).not.toBeNull();
      expect((b.querySelector('.oc__cols') as HTMLElement).style.getPropertyValue('--oc-n')).toBe('13');
      // 빠진 분기는 빈 칸 그대로(0 막대가 아니다).
      expect(cols[1].className).toContain('oc__col--missing');
      expect(cols[1].querySelectorAll('.oc__bar')).toHaveLength(0);
    }
    expect(blocks[0].querySelector('.oc__trend-cap')?.textContent).toContain('분기별 개업률·폐업률 — 최근 13분기');
    // 눈금 = 보는 창(13분기)의 최댓값 20% — 옛 분기 하나 때문에 커진다는 것을 글이 밝힌다.
    expect(container.querySelector('.oc__scale')?.textContent).toBe(
      '막대가 꽉 차면 20%(분기) · 보는 기간(최근 13분기)의 가장 큰 값 기준',
    );
    const h = (el: Element | null) => parseFloat((el as HTMLElement).style.height);
    const firstCols = blocks[0].querySelectorAll('.oc__col');
    expect(h(firstCols[0].querySelector('.oc__bar--close'))).toBeCloseTo(100, 6);
    expect(h(firstCols[firstCols.length - 2].querySelector('.oc__bar--close'))).toBeCloseTo(20, 6); // 4.0 / 20
    // 글은 그대로 — 큰 숫자 줄·업종 표는 최신 분기 것 그대로다.
    expect(blocks[0].querySelector('.oc__quarter')?.textContent).toBe('2026년 2분기');
    expect(allCalls()).toHaveLength(1);

    const back = screen.getByRole('button', { name: '최근 2년(8분기)만 보기' });
    expect(back.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(back);
    expect(container.querySelectorAll('.oc__district')[0].querySelectorAll('.oc__col')).toHaveLength(8);
    expect(container.querySelector('.oc__scroll')).toBeNull();
    expect(container.querySelector('.oc__scale')?.textContent).toContain('보는 기간(최근 2년(8분기))');
    expect(allCalls()).toHaveLength(1);
  });

  it('★ 8분기 창에서 no_data 이던 상권이 전부 창에서 ok 가 되면 「이 상권 자료는 ○년 ○분기까지」가 꼭 함께 선다', async () => {
    const nodata = okRow({
      district_id: '3110001',
      district_nm: '옛 자료만 있는 상권',
      status: 'no_data',
      latest_quarter: null,
      quarters: null,
      industries: null,
      other_industries: null,
    });
    responses.oc = { data: [okRow(), nodata], error: null };
    responses.all = {
      data: [
        allRowOf(okRow(), 13, [bigOld]),
        { ...allRowOf(nodata, 13, [bigOld]), status: 'ok', latest_quarter: OLD },
      ],
      error: null,
    };
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    const second = () => container.querySelectorAll('.oc__district')[1];
    expect(second().textContent).toContain('최근 2년(8분기) 동안 서울시가 이 상권의 개업·폐업 자료를 내지 않았습니다.');
    fireEvent.click(await allButton());
    expect(second().querySelector('.oc__quarter')?.textContent).toBe('2023년 2분기');
    expect(second().textContent).toContain('이 상권 자료는 2023년 2분기까지입니다.');
    // 최신 분기를 가진 첫 상권에는 그 문장이 없다.
    expect(container.querySelectorAll('.oc__district')[0].textContent).not.toContain('까지입니다');
  });

  it.each([
    ['함수 없음(PGRST202)', { data: null, error: { code: 'PGRST202' } }],
    ['오류', { data: null, error: { message: 'boom' } }],
    ['total_quarters 칸 없음', 'no-total'],
    ['total_quarters 가 창 길이와 다름', 'mismatch'],
    ['전부가 8분기보다 길지 않음', 'eight'],
  ])('★ %s — 단추만 없고 카드·8분기 그림은 그대로', async (_name, kind) => {
    const eight = responses.oc.data as DistrictOpenClose[];
    responses.all =
      kind === 'no-total'
        ? { data: eight.map((r) => ({ ...r, window_quarters: windowOf(13) })), error: null }
        : kind === 'mismatch'
          ? { data: eight.map((r) => ({ ...allRowOf(r, 13), total_quarters: 22 })), error: null }
          : kind === 'eight'
            ? { data: eight.map((r) => allRowOf(r, 8)), error: null }
            : (kind as { data: unknown; error: unknown });
    const { container } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    await waitFor(() => expect(allCalls()).toHaveLength(1));
    await Promise.resolve();
    await Promise.resolve();
    expect(container.querySelector('.oc__all')).toBeNull();
    expect(container.querySelectorAll('.oc__district')).toHaveLength(2);
    expect(container.querySelectorAll('.oc__district')[0].querySelectorAll('.oc__col')).toHaveLength(8);
  });

  it('★ 대전·상권 밖·좌표 없음에는 전부 보기를 묻지 않는다', async () => {
    for (const st of ['not_seoul', 'outside_seoul_district', 'no_coord'] as const) {
      rpcCalls.length = 0;
      responses.oc = { data: [headRow(st)], error: null };
      const { unmount } = render(<OpenCloseSection pnu={st === 'not_seoul' ? DAEJEON : PNU} />);
      await screen.findByText('상권 개업·폐업 (서울시 공표)');
      await Promise.resolve();
      expect(allCalls(), st).toHaveLength(0);
      unmount();
    }
  });

  it('★ 늦은 답은 버린다 — 필지가 바뀐 뒤 도착한 앞 필지의 전부 답으로 단추를 세우지 않는다', async () => {
    let release!: (v: { data: unknown; error: unknown }) => void;
    allGate.next = new Promise((r) => (release = r));
    const eight = responses.oc.data as DistrictOpenClose[];
    const { container, rerender } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    await waitFor(() => expect(allCalls()).toHaveLength(1));
    // 새 필지 = 서울 상권 하나 · 그 필지의 전부 답은 함수 없음(기본값).
    const other = '1168010100100020000';
    responses.oc = { data: [okRow({ district_id: '3110002', district_nm: '다른 상권' })], error: null };
    rerender(<OpenCloseSection pnu={other} />);
    await waitFor(() => expect(container.querySelector('.oc__name')?.textContent).toContain('다른 상권'));
    await waitFor(() => expect(allCalls()).toHaveLength(2));
    release({ data: eight.map((r) => allRowOf(r, 13, [bigOld])), error: null });
    // 늦은 답이 상태에 들어갔다면 다시 그려질 만큼 기다린다(마이크로태스크 두 번으로는 React 가 아직 안 그린다).
    await new Promise((r) => setTimeout(r, 50));
    expect(container.querySelector('.oc__all')).toBeNull();
    expect(allCalls().map((c) => c.args)).toEqual([{ p_pnu: PNU }, { p_pnu: other }]);
  });

  it('★ 필지가 바뀌면 전부 보기 상태를 비운다 — 새 필지는 8분기로 시작한다', async () => {
    const eight = responses.oc.data as DistrictOpenClose[];
    responses.all = { data: eight.map((r) => allRowOf(r, 13, [bigOld])), error: null };
    const { container, rerender } = render(<OpenCloseSection pnu={PNU} />);
    await openCard();
    fireEvent.click(await allButton());
    expect(container.querySelector('.oc__scroll')).not.toBeNull();

    const other = '1168010100100020000';
    const next = [okRow({ district_id: '3110002', district_nm: '다른 상권' })];
    responses.oc = { data: next, error: null };
    responses.all = { data: next.map((r) => allRowOf(r, 22)), error: null };
    rerender(<OpenCloseSection pnu={other} />);
    await waitFor(() => expect(container.querySelector('.oc__name')?.textContent).toContain('다른 상권'));
    await openCard(); // 답을 비우는 동안 카드가 내려갔다 다시 서서 접힌 채다
    expect((await allButton()).textContent).toBe('전부 보기 (22분기)');
    expect(container.querySelector('.oc__scroll')).toBeNull();
    expect(container.querySelectorAll('.oc__col')).toHaveLength(8);
  });
});
