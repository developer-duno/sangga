import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import type { RentStat } from '../types';
import { RENT_NO_COORD_TEXT } from '../lib/rentStats';

/**
 * "상권 임대 동향 (부동산원 조사)" 카드 — 층별 화면의 여섯 번째 카드(결정 0024).
 *
 * 여기서 특히 지키는 것
 * ---------------------
 *  ① **못 읽었으면 아무 말도 안 한다** — 마이그레이션 적용 전 라이브이 그 상태다.
 *     "조사값 없음"이라 적으면 모르는 것을 없는 것이라 말하게 된다.
 *  ② **조사 대상이 아닌 자리에서는 카드가 서고 그렇다고 적는다** — 그냥 사라지면 사람은
 *     "이 서비스는 임대 이야기를 안 한다"로 읽고, 시·도 평균을 적으면 조사 안 한 곳을
 *     조사한 것처럼 말하게 된다. 둘 다 아닌 제3의 답이 이 카드의 존재 이유다.
 *  ③ **이 건물 값이 아니라는 한정어**가 카드 안에 있다 — 접힌 요약에 값을 안 담는 것과
 *     한 쌍이다.
 *  ④ **인자 이름이 `p_pnu`** 다. 목은 인자 이름을 안 보므로 여기서 눈으로 보지 않으면
 *     `{ pnu: … }` 로 잘못 불러도 시험은 전부 초록이고 라이브만 PGRST202 가 난다.
 */

const responses = {
  rent: { data: null as unknown, error: null as unknown },
  /**
   * 8분기 흐름(`list_rent_stat_history` · 결정 0038 V5). 기본은 **함수가 없는 상태**(PGRST202) — 이 파일의 옛 시험들은
   * 흐름 없이 카드가 그대로 서는지를 본다. 흐름을 보는 시험만 덮어쓴다.
   */
  history: null as unknown as PromiseLike<{ data: unknown; error: unknown }> | { data: unknown; error: unknown },
};
const HISTORY_MISSING = { data: null, error: { code: 'PGRST202' } };

/** 마지막 rpc 호출들. 함수 이름과 **인자 이름·값**을 여기서 확인한다. */
const rpcCalls: Array<{ fn: string; args: unknown }> = [];

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string, args?: unknown) => {
      rpcCalls.push({ fn, args });
      if (fn === 'list_rent_stat_history') return Promise.resolve(responses.history);
      return Promise.resolve(responses.rent);
    },
  },
}));

const { RentStatSection } = await import('./RentStatSection');
const { resetDataFreshnessCache } = await import('../lib/loadDataFreshness');

/**
 * 이 카드가 부른 것만 — 카드 머리 날짜 줄(S3)의 신선도 요청은 뺀다(맨 아래 표와 나눠 쓰는 한 번의 요청이라
 * 이 카드의 질문이 아니다). ⓘ 그 요청은 시험마다 새로 나간다(아래 beforeEach 가 보관을 비운다) — 시험 차례에 기대지 않게.
 */
const cardCalls = () =>
  rpcCalls.filter((c) => c.fn !== 'get_data_freshness' && c.fn !== 'list_rent_stat_history');
/** 8분기 흐름 요청(결정 0038 V5) — 카드 요청과 따로 센다(종류를 바꿔도 다시 안 나가는지 본다). */
const historyCalls = () => rpcCalls.filter((c) => c.fn === 'list_rent_stat_history');

function stat(over: Partial<RentStat> = {}): RentStat {
  return {
    district_nm: '역삼역',
    rone_region_nm: '서울>강남>테헤란로',
    bld_type: '집합상가',
    quarter: '2026Q2',
    vacancy_rate: 10.08,
    rent_per_m2: 27.06,
    yield_rate: 0.82,
    ...over,
  };
}

const PNU = '1168010100100010000';

beforeEach(() => {
  rpcCalls.length = 0;
  resetDataFreshnessCache();
  responses.rent = { data: [stat()], error: null };
  responses.history = HISTORY_MISSING;
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/** 카드를 펼친다 — 이 카드는 접힌 채로 선다(첫 화면 펼침 상한 4장). */
async function openCard() {
  fireEvent.click(await screen.findByRole('button', { name: /상권 임대 동향/ }));
}

describe('RentStatSection — 조사값이 있을 때', () => {
  it('접힌 카드로 서고, 요약 한 줄이 무엇·언제만 말한다', async () => {
    const { container } = render(<RentStatSection pnu={PNU} />);

    expect(await screen.findByText('상권 임대 동향 (부동산원 조사)')).toBeTruthy();
    expect(container.querySelector('.card__summary')?.textContent).toBe(
      '공실률 · ㎡당 임대료 · 투자수익률 · 2026년 2분기 조사',
    );
    // ⛔ 요약에 값이 있으면 한정어 없이 이 건물 값으로 읽힌다.
    expect(container.querySelector('.card__summary')?.textContent).not.toContain('27,060');
    expect(screen.getByRole('button').getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelector('.card__body')?.hasAttribute('hidden')).toBe(true);
  });

  it('펼치면 상권·조사구역·세 지표·조사 분기가 한 줄에 나온다', async () => {
    render(<RentStatSection pnu={PNU} />);
    await openCard();

    expect(screen.getByText('역삼역')).toBeTruthy();
    expect(screen.getByText('부동산원 조사구역 서울>강남>테헤란로')).toBeTruthy();
    expect(screen.getByText('공실률 10.08%')).toBeTruthy();
    // ★ 단위 — 공표값은 천원/㎡ 다. 1,000을 안 곱하면 '27원'이 되는데 그것도 그럴듯하다.
    expect(screen.getByText('㎡당 임대료 27,060원')).toBeTruthy();
    // ★ 분기 수익률에 '분기'가 붙어 있어야 한다(연으로 읽히면 뜻이 정반대가 된다).
    expect(screen.getByText('투자수익률(분기) 0.82%')).toBeTruthy();
    expect(screen.getByText('2026년 2분기 조사')).toBeTruthy();
  });

  it('★ 이 건물 값이 아니라는 한정어와 등급·출처가 함께 있다', async () => {
    render(<RentStatSection pnu={PNU} />);
    await openCard();

    expect(screen.getByText(/이 건물이 속한 상권의 조사값입니다/)).toBeTruthy();
    // 추정이 아니라 공식 표본조사다(상세계획 §7.4 의 등급 어휘 — A 실측 / B 공식표본).
    expect(screen.getByText(/B등급 · 공식 표본조사/)).toBeTruthy();
    expect(screen.getByText(/출처: 한국부동산원 상업용부동산 임대동향조사/)).toBeTruthy();
    // 관리비·연 환산·종류 합산 — 셋 다 오해를 부르는 자리라 카드 안에서 못 박는다.
    expect(screen.getByText(/관리비는 포함되지 않습니다/)).toBeTruthy();
    expect(screen.getByText(/한 해 수익률로 바꾸지 않습니다/)).toBeTruthy();
    expect(screen.getByText(/건물 종류끼리 더하거나 견주지 않습니다/)).toBeTruthy();
  });

  it('⛔ 추정으로 읽히는 말을 쓰지 않는다 (이 카드는 조사값이다)', async () => {
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    const text = container.textContent ?? '';
    for (const banned of ['적정가격', '적정가', '평가액', '감정가', '가치평가', '추정', '시세']) {
      expect(text.includes(banned), `'${banned}' 가 카드에 있습니다`).toBe(false);
    }
  });

  it('★ 서버에 p_pnu 라는 이름으로 묻는다 (이름이 어긋나면 라이브만 PGRST202)', async () => {
    render(<RentStatSection pnu={PNU} />);
    await screen.findByText('상권 임대 동향 (부동산원 조사)');

    expect(cardCalls()).toEqual([{ fn: 'list_rent_stats', args: { p_pnu: PNU } }]);
    // 8분기 흐름도 같은 이름의 인자 하나로(결정 0038 V5).
    await waitFor(() => expect(historyCalls()).toEqual([{ fn: 'list_rent_stat_history', args: { p_pnu: PNU } }]));
  });
});

describe('RentStatSection — 층별 임대료 · 소득수익률 (결정 0031)', () => {
  /** 2026-10-04 라이브 실호출 값(서울>강남>테헤란로 · 2026Q2 — 천원/㎡). */
  const COLLECTIVE = { '1': 74.6, '2': 32.48, '3': 23.54, '4': 23.73, '5': 25.0, '-1': 16.95, '6+': 22.7 };
  const OFFICE = {
    '1': 38.99,
    '2': 31.4,
    '3': 27.09,
    '4': 26.6,
    '5': 26.51,
    '-1': 13.93,
    '11+': 28.62,
    '6-10': 26.73,
  };
  const SMALL = { '1': 72.97, '2': 38.92, '-1': 30.02 };

  beforeEach(() => {
    responses.rent = {
      data: [
        stat({ rent_per_m2: 74.6, income_yield_rate: 0.9, floor_rent: COLLECTIVE }),
        stat({ bld_type: '오피스', rent_per_m2: 27.69, income_yield_rate: 0.84, floor_rent: OFFICE }),
        stat({ bld_type: '소규모상가', rent_per_m2: 72.97, income_yield_rate: 0.41, floor_rent: SMALL }),
      ],
      error: null,
    };
  });

  /** 표의 줄을 '층 금액' 글자로 — 화면 차례 그대로. */
  function floorRows(container: HTMLElement): string[] {
    return [...container.querySelectorAll('.rent__floors tbody tr')].map(
      (tr) => `${tr.querySelector('th')?.textContent} ${tr.querySelector('td')?.textContent}`,
    );
  }

  it('★ 펼치면 줄 아래 층별 표가 높은 층부터 서고, 머리글이 "이 건물 값이 아님"을 말한다', async () => {
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    expect(floorRows(container)).toEqual([
      '6층 이상 22,700원',
      '5층 25,000원',
      '4층 23,730원',
      '3층 23,540원',
      '2층 32,480원',
      '1층 74,600원',
      '지하 1층 16,950원',
    ]);
    expect(container.querySelector('.rent__floors caption')?.textContent).toBe(
      '층별 ㎡당 월 임대료 — 조사 상권 평균, 이 건물 값이 아님',
    );
    // 표는 그 조사구역 줄 **안**에 있다(조사구역끼리 섞이지 않게).
    expect(container.querySelector('.rent__rows li .rent__floors')).not.toBeNull();
    expect(screen.getByText(/조사 상권의 평균입니다/)).toBeTruthy();
    expect(screen.getByText(/지하 2층 이하와 옥탑은 부동산원이 층 구간을 발표하지 않습니다/)).toBeTruthy();
  });

  it('★ 소득수익률을 분기 라벨로 적고, 요약 줄 끝에 "층별 임대료 포함"이 붙는다', async () => {
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    expect(screen.getByText('소득수익률(분기) 0.9%')).toBeTruthy();
    expect(container.querySelector('.card__summary')?.textContent).toBe(
      '공실률 · ㎡당 임대료 · 투자수익률 · 소득수익률 · 2026년 2분기 조사 · 층별 임대료 포함',
    );
  });

  it('★ 소득수익률 0 은 "0%" 로 적는다 (빈 값과 다르다)', async () => {
    responses.rent = { data: [stat({ income_yield_rate: 0 })], error: null };
    render(<RentStatSection pnu={PNU} />);
    await openCard();

    expect(screen.getByText('소득수익률(분기) 0%')).toBeTruthy();
  });

  it('기준층·환산임대료·부가가치세·소득수익률 정의를 카드 안에서 밝힌다', async () => {
    render(<RentStatSection pnu={PNU} />);
    await openCard();

    expect(screen.getByText(/부가가치세도 뺀 금액입니다/)).toBeTruthy();
    expect(screen.getByText(/보증금을 월세로 바꿔 더한 값이고/)).toBeTruthy();
    expect(screen.getByText(/3층부터 최고층까지의 평균/)).toBeTruthy();
    expect(screen.getByText(/우리가 곱하거나 나눠 만든 값이 아닙니다/)).toBeTruthy();
    expect(screen.getByText(/순영업소득/)).toBeTruthy();
    // 상가를 볼 때는 1층 값과 거의 같다는 말이, 오피스 문장은 없다.
    expect(screen.getByText(/1층 값과 같은 기준이라 거의 같습니다/)).toBeTruthy();
    expect(screen.queryByText(/3층 이상 평균이라 층별 표의 1층 값과 다릅니다/)).toBeNull();
  });

  it('★ 층별 표가 없으면 "층별 표는 부동산원이" 문장을 빼고, 1층 기준 문장은 그대로 둔다', async () => {
    responses.rent = { data: [stat()], error: null };
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    expect(container.querySelector('.rent__floors')).toBeNull();
    expect(screen.queryByText(/층별 표는 부동산원이/)).toBeNull();
    expect(screen.queryByText(/우리가 곱하거나 나눠 만든 값이 아닙니다/)).toBeNull();
    // 기준층 문장(부동산원 정의)은 표와 무관하게 늘 선다.
    expect(screen.getByText('1층 기준')).toBeTruthy();
    expect(screen.getByText(/3층부터 최고층까지의 평균/)).toBeTruthy();
    expect(container.querySelector('.rent__why')?.textContent).toContain('입니다(부동산원 정의).');
  });

  it('★ 층별 표가 있으면 "층별 표는 부동산원이 … 공표한 값" 문장이 선다', async () => {
    render(<RentStatSection pnu={PNU} />);
    await openCard();

    expect(
      screen.getByText(/층별 표는 부동산원이 층 구간마다 공표한 값이며, 우리가 곱하거나 나눠 만든 값이 아닙니다\./),
    ).toBeTruthy();
  });

  it('★ 소득수익률 값이 없으면 그 정의를 빼고 "투자수익률은 분기 값" 만 적는다', async () => {
    responses.rent = { data: [stat()], error: null };
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    expect(screen.queryByText(/순영업소득/)).toBeNull();
    const why = container.querySelector('.rent__why')?.textContent ?? '';
    expect(why).toContain('투자수익률은 분기 값입니다. 4를 곱해 한 해 수익률로 바꾸지 않습니다.');
    expect(why).not.toContain('소득수익률');
  });

  it('두 설명 조각은 지금 보이는 종류를 따라간다 — 다른 종류에만 있는 값으로 붙지 않는다', async () => {
    responses.rent = {
      data: [
        stat(),
        stat({ bld_type: '오피스', rent_per_m2: 27.69, income_yield_rate: 0.84, floor_rent: OFFICE }),
      ],
      error: null,
    };
    render(<RentStatSection pnu={PNU} />);
    await openCard();

    // 기본은 집합상가 — 표도 소득수익률도 없다.
    expect(screen.queryByText(/순영업소득/)).toBeNull();
    expect(screen.queryByText(/층별 표는 부동산원이/)).toBeNull();

    fireEvent.change(screen.getByLabelText('건물 종류 골라보기'), { target: { value: '오피스' } });

    await waitFor(() => expect(screen.getByText(/순영업소득/)).toBeTruthy());
    expect(screen.getByText(/층별 표는 부동산원이/)).toBeTruthy();
  });

  it('오피스를 고르면 그 종류의 표(11층 이상 · 6~10층)와 오피스 문장으로 바뀐다 — 종류를 섞지 않는다', async () => {
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    fireEvent.change(screen.getByLabelText('건물 종류 골라보기'), { target: { value: '오피스' } });

    await waitFor(() => expect(floorRows(container)[0]).toBe('11층 이상 28,620원'));
    expect(floorRows(container)).toHaveLength(8);
    expect(floorRows(container)).toContain('6~10층 26,730원');
    expect(container.textContent).not.toContain('22,700원');
    expect(screen.getByText(/3층 이상 평균이라 층별 표의 1층 값과 다릅니다/)).toBeTruthy();
    expect(screen.queryByText(/1층 값과 같은 기준이라 거의 같습니다/)).toBeNull();
  });

  it('소규모상가를 고르면 3층 이상 값이 원래 없다고 적는다', async () => {
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();
    expect(screen.queryByText(/소규모상가 조사는 2층 이하 건물이 대상이라/)).toBeNull();

    fireEvent.change(screen.getByLabelText('건물 종류 골라보기'), { target: { value: '소규모상가' } });

    await waitFor(() => expect(floorRows(container)).toEqual(['2층 38,920원', '1층 72,970원', '지하 1층 30,020원']));
    expect(
      screen.getByText('소규모상가 조사는 2층 이하 건물이 대상이라 3층 이상 값이 없습니다.'),
    ).toBeTruthy();
  });

  it('★ 새 칸이 없는 답(옛 함수)에서도 카드는 서고, 표와 표에 딸린 문장만 빠진다', async () => {
    responses.rent = { data: [stat()], error: null };
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    expect(screen.getByText('㎡당 임대료 27,060원')).toBeTruthy();
    expect(container.querySelector('.rent__floors')).toBeNull();
    expect(screen.queryByText(/소득수익률\(분기\)/)).toBeNull();
    expect(screen.queryByText(/조사 상권의 평균입니다/)).toBeNull();
    expect(screen.queryByText(/1층 값과 같은 기준이라/)).toBeNull();
    expect(container.querySelector('.card__summary')?.textContent).toBe(
      '공실률 · ㎡당 임대료 · 투자수익률 · 2026년 2분기 조사',
    );
  });

  it('★ 표 모양이 이상하면 그 표만 빠지고 카드·값은 선다', async () => {
    responses.rent = {
      data: [stat({ floor_rent: 'broken' as unknown as Record<string, number>, income_yield_rate: 0.9 })],
      error: null,
    };
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    expect(screen.getByText('공실률 10.08%')).toBeTruthy();
    expect(screen.getByText('소득수익률(분기) 0.9%')).toBeTruthy();
    expect(container.querySelector('.rent__floors')).toBeNull();
  });

  it('⛔ 층별 표가 있어도 추정으로 읽히는 말을 쓰지 않는다', async () => {
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    const text = container.textContent ?? '';
    for (const banned of ['적정가격', '적정가', '평가액', '감정가', '가치평가', '추정', '시세']) {
      expect(text.includes(banned), `'${banned}' 가 카드에 있습니다`).toBe(false);
    }
  });
});

describe('RentStatSection — 건물 종류 고르기', () => {
  beforeEach(() => {
    responses.rent = {
      data: [
        stat(),
        stat({ bld_type: '오피스', vacancy_rate: 5.5, rent_per_m2: 18.4, yield_rate: 1.1 }),
      ],
      error: null,
    };
  });

  it('처음에는 집합상가를 보여주고, 무엇을 보는 중인지 글자로 적는다', async () => {
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    // 종이에서는 고르개가 빠지므로 이 줄이 혼자 "무슨 종류인가"를 지킨다.
    // (고르개의 option 에도 같은 글자가 있으므로 **이 줄을 콕 집어** 본다.)
    expect(container.querySelector('.rent__now-type')?.textContent).toBe('집합상가');
    expect(screen.getByText('공실률 10.08%')).toBeTruthy();
    // ⛔ 다른 종류의 값이 같은 화면에 함께 나오면 안 된다(모집단이 다른 별개의 조사다).
    expect(screen.queryByText('공실률 5.5%')).toBeNull();
  });

  it('종류를 고르면 그 종류의 값으로 바뀐다', async () => {
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    fireEvent.change(screen.getByLabelText('건물 종류 골라보기'), { target: { value: '오피스' } });

    await waitFor(() => expect(screen.getByText('공실률 5.5%')).toBeTruthy());
    expect(screen.queryByText('공실률 10.08%')).toBeNull();
    expect(screen.getByText('㎡당 임대료 18,400원')).toBeTruthy();
    // 보고 있는 종류를 적는 줄도 함께 따라간다(종이에서는 이 줄만 남는다).
    expect(container.querySelector('.rent__now-type')?.textContent).toBe('오피스');
  });

  it('종류가 하나뿐이면 고르개를 만들지 않는다 (누를 것이 없는 장치는 두지 않는다)', async () => {
    responses.rent = { data: [stat()], error: null };
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    expect(screen.queryByLabelText('건물 종류 골라보기')).toBeNull();
    // 고르개가 없어도 무엇을 보는 중인지는 그대로 적혀 있다.
    expect(container.querySelector('.rent__now-type')?.textContent).toBe('집합상가');
  });
});

describe('RentStatSection — 종류 칸이 비어서 고를 것이 없을 때', () => {
  /*
    2026-09-05. 되돌릴 기본값을 `options[0]` 대신 `defaultBldType(rows)` 로 바꾸면서
    **없던 갈래가 하나 생겼다** — 그 함수는 고를 것이 없으면 `null` 을 준다(예전 `options[0]`
    은 런타임 `undefined` 였다).

    ⓘ 이 시험이 지키는 것을 정확히 적어 둔다. `shown` 의 `bldType === null ? [] : …` 자체는
      **없애도 화면이 똑같다**(`toRentRows` 가 null 과 맞는 줄을 못 찾아 어차피 빈 목록이다 —
      돌연변이로 실측). 그러니 이 시험이 붙드는 것은 그 삼항이 아니라 **"이 상태에서 카드가
      터지지 않는다"** 다. 다음 사람이 `bldType` 을 그냥 `string` 으로 여기고 `.trim()` 같은
      것을 부르는 순간 빨간불이 된다(그것도 실측했다). 카드가 터지면 그물에 걸려 **층별 화면
      전체**가 오류 안내로 바뀐다 — 곁다리 하나로 본체를 잃는 자리다.

    도달 경로: `isRentStat` 은 `bld_type` 이 **문자열이기만** 하면 통과시키므로(빈 글자도
    문자열이다), 종류 칸이 빈 줄만 오면 `typeOptions` 가 그 줄들을 걸러 빈 목록이 된다.
  */
  beforeEach(() => {
    responses.rent = { data: [stat({ bld_type: '' })], error: null };
  });

  it('★ 카드가 터지지 않고 선다 — 줄도 고르개도 없이', async () => {
    const { container } = render(<RentStatSection pnu={PNU} />);

    // 카드 자체는 있다(줄이 하나라도 왔으므로 "조사 대상이 아니다" 쪽이 아니다).
    expect(await screen.findByText('상권 임대 동향 (부동산원 조사)')).toBeTruthy();
    await openCard();

    // 고를 것이 없으니 고르개도 없고, 무엇을 보는 중인지 적는 자리도 비어 있다.
    expect(screen.queryByLabelText('건물 종류 골라보기')).toBeNull();
    expect(container.querySelector('.rent__now-type')?.textContent).toBe('');

    // ⛔ 값이 없는데 숫자 줄을 그리면 "여기는 0%"처럼 읽힌다 — 대신 그 사실을 적는다.
    expect(container.querySelector('.rent__rows')).toBeNull();
    expect(screen.getByText('이 종류는 이번 조사에서 값이 나오지 않았습니다.')).toBeTruthy();
  });
});

describe('RentStatSection — 조사 대상이 아닐 때', () => {
  beforeEach(() => {
    responses.rent = { data: [], error: null };
  });

  it('★ 카드는 서고, 조사 대상이 아니라고 그대로 적는다', async () => {
    const { container } = render(<RentStatSection pnu={PNU} />);

    expect(await screen.findByText('상권 임대 동향 (부동산원 조사)')).toBeTruthy();
    expect(container.querySelector('.card__summary')?.textContent).toBe(
      '부동산원 조사 대상 상권이 아닙니다',
    );
  });

  it('★ 좌표 없는 건물(noCoord)이면 "상권을 못 찾음" — 개업·폐업 카드와 같은 글 (2026-10-06)', async () => {
    const { container } = render(<RentStatSection pnu={PNU} noCoord />);

    expect(await screen.findByText('상권 임대 동향 (부동산원 조사)')).toBeTruthy();
    expect(container.querySelector('.card__summary')?.textContent).toBe(
      '위치 정보가 없어 속한 상권을 찾지 못했습니다',
    );
    await openCard();
    expect(container.querySelector('.rent__lead')?.textContent).toBe(RENT_NO_COORD_TEXT);
    // ⛔ "표본에 안 들었다"는 설명은 좌표가 없는 건물에 대한 말이 아니다.
    expect(screen.queryByText(/정해진 표본 상권/)).toBeNull();
    expect(screen.getByText('출처: 한국부동산원 상업용부동산 임대동향조사.')).toBeTruthy();
    // 본문 글은 개업·폐업 카드의 no_coord 글을 그대로 옮긴 것이다 — 한쪽만 바뀌면 빨강.
    // ⓘ jsdom 의 .tsx 에서는 import.meta.url 이 file: 이 아니다 — 레포 루트 기준 경로로 읽는다
    //   (DistrictMap.test.tsx 의 styles.css 읽기와 같다).
    const oc = readFileSync('src/components/OpenCloseSection.tsx', 'utf-8');
    expect(oc).toContain(`'${RENT_NO_COORD_TEXT}'`);
  });

  it('noCoord 라도 줄이 왔으면 평소 카드다', async () => {
    responses.rent = { data: [stat()], error: null };
    const { container } = render(<RentStatSection pnu={PNU} noCoord />);
    await screen.findByText('상권 임대 동향 (부동산원 조사)');
    expect(container.querySelector('.card__summary')?.textContent).toBe(
      '공실률 · ㎡당 임대료 · 투자수익률 · 2026년 2분기 조사',
    );
  });

  it('★ 이웃 상권·시·도 평균으로 메우지 않는다고 밝힌다', async () => {
    render(<RentStatSection pnu={PNU} />);
    await openCard();

    expect(screen.getByText(/정해진 표본 상권/)).toBeTruthy();
    expect(screen.getByText(/조사하지 않은 곳을 조사한 것처럼/)).toBeTruthy();
    // ⛔ "장사가 안 되는 자리"라는 뜻이 아니라는 것도 함께 말한다(상권 카드와 같은 규칙).
    expect(screen.getByText(/장사가 안 되는 자리라는 뜻이/)).toBeTruthy();
    // 값이 없으니 숫자 줄도 없다.
    expect(document.querySelector('.rent__rows')).toBeNull();
  });
});

describe('RentStatSection — 못 읽었을 때', () => {
  it('★ 함수가 아직 없으면(PGRST202) 카드를 통째로 생략한다', async () => {
    responses.rent = { data: null, error: { code: 'PGRST202' } };
    const { container } = render(<RentStatSection pnu={PNU} />);

    await waitFor(() => expect(cardCalls()).toHaveLength(1));
    // "조사값 없음"이라 적지 않는다 — 없는 것과 모르는 것은 다르다.
    expect(container.querySelector('.rent')).toBeNull();
    expect(container.textContent).toBe('');
  });

  it('★ 뜻밖의 모양이 와도 터지지 않고 카드만 사라진다', async () => {
    // 다른 함수의 응답이 흘러든 경우. 렌더 중에 터지면 층별 화면 전체가 오류 안내가 된다.
    responses.rent = { data: { code: 'PGRST202', message: 'x' }, error: null };
    const { container } = render(<RentStatSection pnu={PNU} />);

    await waitFor(() => expect(cardCalls()).toHaveLength(1));
    expect(container.textContent).toBe('');
  });

  it('값 자리에 글자가 온 줄이 섞여 있어도 통째로 접는다', async () => {
    responses.rent = {
      data: [stat(), { ...stat(), vacancy_rate: '10.08' }],
      error: null,
    };
    const { container } = render(<RentStatSection pnu={PNU} />);

    await waitFor(() => expect(cardCalls()).toHaveLength(1));
    expect(container.textContent).toBe('');
  });
});

describe('RentStatSection — 건물이 바뀔 때', () => {
  it('★ 앞 건물의 조사값이 새 건물 밑에 잠깐이라도 붙어 있지 않는다', async () => {
    const { rerender, container } = render(<RentStatSection pnu={PNU} />);
    await screen.findByText('상권 임대 동향 (부동산원 조사)');

    // 다음 답을 영영 안 주는 상태로 두고 필지를 바꾼다 — 그 사이 화면에 옛 값이 남아
    // 있으면 그 짧은 순간이 그대로 틀린 정보다.
    responses.rent = { data: null as unknown, error: null };
    rerender(<RentStatSection pnu="1168010100100020000" />);

    await waitFor(() => expect(container.querySelector('.rent')).toBeNull());
    expect(cardCalls().map((c) => c.args)).toEqual([
      { p_pnu: PNU },
      { p_pnu: '1168010100100020000' },
    ]);
  });
});

describe('RentStatSection — 계단 막대 · 8분기 흐름 (결정 0038 C · V5)', () => {
  /** 운영 읽기 값(서울>강남>테헤란로 · 2026-10-24 — 천원/㎡). */
  const COLLECTIVE = { '1': 74.6, '2': 32.48, '3': 23.54, '4': 23.73, '5': 25.0, '-1': 16.95, '6+': 22.7 };
  const OFFICE = { '1': 38.99, '2': 31.4, '3': 27.09, '4': 26.6, '5': 26.51, '-1': 13.93, '11+': 28.62, '6-10': 26.8 };
  const QUARTERS = ['2024Q3', '2024Q4', '2025Q1', '2025Q2', '2025Q3', '2025Q4', '2026Q1', '2026Q2'];
  /** 집합상가 8분기(운영 읽기 값 — 마지막 분기 = 카드 줄 값) · 오피스 8분기. */
  const COLL_VAC = [2.79, 2.79, 4.14, 4.31, 7.65, 6.42, 6.74, 6.74];
  const OFF_VAC = [3.0, 2.43, 2.86, 3.05, 4.07, 3.93, 4.82, 4.56];

  function hist(type: string, vac: number[], over: (i: number) => Record<string, unknown> = () => ({})) {
    return QUARTERS.map((q, i) => ({
      rone_region_nm: '서울>강남>테헤란로',
      bld_type: type,
      quarter: q,
      vacancy_rate: vac[i],
      rent_per_m2: type === '오피스' ? 27.69 : 74.6,
      yield_rate: type === '오피스' ? 1.1 : 0.82,
      income_yield_rate: 0.9,
      ...over(i),
    }));
  }

  function twoTypes() {
    return [
      stat({ rent_per_m2: 74.6, vacancy_rate: 6.74, floor_rent: COLLECTIVE }),
      stat({ bld_type: '오피스', vacancy_rate: 4.56, rent_per_m2: 27.69, yield_rate: 1.1, floor_rent: OFFICE }),
    ];
  }

  beforeEach(() => {
    responses.rent = { data: twoTypes(), error: null };
    responses.history = { data: [...hist('집합상가', COLL_VAC), ...hist('오피스', OFF_VAC)], error: null };
  });

  const widthOf = (container: HTMLElement, key: string) =>
    (container.querySelector(`.rent__floors tr[data-floor="${key}"] .rent__step-fill`) as HTMLElement | null)?.style
      .width ?? null;

  it('★ 층별 표 줄마다 계단 막대 — 길이 = 그 표에서 가장 비싼 구간이 칸 끝 · 읽는 기기엔 숨김 · 글은 그대로', async () => {
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    expect(widthOf(container, '1')).toBe('100%');
    expect(parseFloat(widthOf(container, '2') ?? '')).toBeCloseTo((32.48 / 74.6) * 100, 5);
    expect(parseFloat(widthOf(container, '-1') ?? '')).toBeCloseTo((16.95 / 74.6) * 100, 5);
    expect(parseFloat(widthOf(container, '6+') ?? '')).toBeCloseTo((22.7 / 74.6) * 100, 5);
    for (const td of container.querySelectorAll('.rent__step')) expect(td.getAttribute('aria-hidden')).toBe('true');
    // 글(층 · 금액)은 한 글자도 안 빠졌다.
    expect(container.querySelector('.rent__floors tr[data-floor="1"]')?.textContent).toBe('1층74,600원');
  });

  it('★ 오피스 — 11층 이상 · 6~10층 둘 다 막대(세 잣대의 열쇠 규칙 그대로)', async () => {
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();
    fireEvent.change(screen.getByLabelText('건물 종류 골라보기'), { target: { value: '오피스' } });

    expect(widthOf(container, '1')).toBe('100%');
    expect(parseFloat(widthOf(container, '11+') ?? '')).toBeCloseTo((28.62 / 38.99) * 100, 5);
    expect(parseFloat(widthOf(container, '6-10') ?? '')).toBeCloseTo((26.8 / 38.99) * 100, 5);
  });

  it('★ 8분기 흐름 — 그림 셋 · 그림마다 제 눈금 · 막대 높이가 값에 비례 · 이 건물 값 아님 머리 · 분기마다 값은 그림 이름에', async () => {
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    const fig = await waitFor(() => {
      const f = container.querySelector('.rent__rows li .rent-trend');
      expect(f).not.toBeNull();
      return f!;
    });
    expect(fig.querySelector('figcaption')?.textContent).toBe(
      '최근 8분기 흐름 — 조사 상권 평균, 이 건물 값이 아님왼쪽 2024년 3분기 → 오른쪽 2026년 2분기',
    );
    const charts = [...container.querySelectorAll('.rent-trend__chart')];
    expect(charts.map((c) => c.getAttribute('data-metric'))).toEqual(['vacancy', 'rent', 'yield']);
    // 그림마다 제 눈금 — 공실률 위 끝 10%(7.65 → 10) · 임대료 100,000원(74.6 → 100) · 수익률 1%(0.82 → 1).
    expect(charts.map((c) => c.querySelector('.rent-trend__scale')?.textContent)).toEqual([
      '눈금 0 ~ 10%',
      '눈금 0 ~ 100,000원',
      '눈금 0 ~ 1%',
    ]);
    const heights = [...charts[0].querySelectorAll('.rent-trend__bar')].map((b) =>
      parseFloat((b as HTMLElement).style.height),
    );
    expect(heights).toHaveLength(8);
    heights.forEach((h, i) => expect(h).toBeCloseTo(COLL_VAC[i] * 10, 5));
    expect(charts[0].getAttribute('role')).toBe('img');
    expect(charts[0].getAttribute('aria-label')).toBe(
      '공실률 최근 8분기(옛 분기부터): 2024년 3분기 2.79% · 2024년 4분기 2.79% · 2025년 1분기 4.14% · 2025년 2분기 4.31% · ' +
        '2025년 3분기 7.65% · 2025년 4분기 6.42% · 2026년 1분기 6.74% · 2026년 2분기 6.74%',
    );
    // 빠진 분기가 없으면 까닭 줄도 없다.
    expect(container.querySelector('.rent-trend__note')).toBeNull();
    // ⛔ 추정·시세 말이 섞이지 않는다.
    expect(container.textContent).not.toMatch(/추정|시세/);
  });

  it('★ 종류를 바꾸면 그 종류의 흐름 — 서버를 다시 부르지 않는다(한 번 받은 네 종류에서 고른다)', async () => {
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();
    await waitFor(() => expect(container.querySelector('.rent-trend')).not.toBeNull());
    expect(historyCalls()).toHaveLength(1);

    fireEvent.change(screen.getByLabelText('건물 종류 골라보기'), { target: { value: '오피스' } });
    const vac = container.querySelector('.rent-trend__chart[data-metric="vacancy"]');
    expect(vac?.getAttribute('aria-label')).toContain('2026년 2분기 4.56%');
    // ⛔ 종류를 섞지 않는다 — 집합상가 공실률이 오피스 그림에 남아 있지 않다.
    expect(vac?.getAttribute('aria-label')).not.toContain('6.74%');
    expect(historyCalls()).toHaveLength(1);
    expect(cardCalls()).toHaveLength(1);
  });

  it('★ 빠진 분기는 0 막대가 아니라 「–」 + 까닭 한 줄 · 음수 투자수익률은 0 선 아래로', async () => {
    responses.history = {
      data: hist('집합상가', COLL_VAC, (i) => (i === 2 ? { vacancy_rate: null } : i === 4 ? { yield_rate: -0.5 } : {}))
        // 2025Q2 줄은 아예 없다(공표 안 됨).
        .filter((r) => r.quarter !== '2025Q2'),
      error: null,
    };
    responses.rent = { data: [stat({ vacancy_rate: 6.74, rent_per_m2: 74.6, floor_rent: COLLECTIVE })], error: null };
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    const vac = await waitFor(() => {
      const el = container.querySelector('.rent-trend__chart[data-metric="vacancy"]');
      expect(el).not.toBeNull();
      return el!;
    });
    const gapsOf = (el: Element) =>
      [...el.querySelectorAll('.rent-trend__col')].filter((c) => c.querySelector('.rent-trend__gap'));
    expect(gapsOf(vac).map((c) => c.getAttribute('data-quarter'))).toEqual(['2025Q1', '2025Q2']);
    expect(gapsOf(vac)[0].textContent).toBe('–');
    expect(vac.querySelectorAll('.rent-trend__bar')).toHaveLength(6);
    expect(vac.getAttribute('aria-label')).toContain('2025년 1분기 공표값 없음');
    expect(container.querySelector('.rent-trend__note')?.textContent).toBe(
      '‘–’ = 그 분기에 부동산원이 이 값을 공표하지 않았습니다(0 이 아닙니다).',
    );
    const yld = container.querySelector('.rent-trend__chart[data-metric="yield"]')!;
    expect(yld.querySelector('.rent-trend__scale')?.textContent).toBe('눈금 -0.5% ~ 1%');
    const neg = yld.querySelector('.rent-trend__col[data-quarter="2025Q3"] .rent-trend__bar') as HTMLElement;
    expect(neg.classList.contains('rent-trend__bar--neg')).toBe(true);
    // 0 선 = 0.5 / 1.5 → 33.33% · 음수 막대는 그 아래로 33.33% 만큼.
    expect(parseFloat((yld.querySelector('.rent-trend__zero') as HTMLElement).style.bottom)).toBeCloseTo(100 / 3, 5);
    expect(parseFloat(neg.style.bottom)).toBeCloseTo(0, 5);
    expect(parseFloat(neg.style.height)).toBeCloseTo(100 / 3, 5);
  });

  it('★ 흐름 함수가 없으면(PGRST202) 흐름만 빠지고 카드·층별 표·계단 막대는 그대로', async () => {
    responses.history = HISTORY_MISSING;
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();
    await waitFor(() => expect(historyCalls()).toHaveLength(1));
    await act(async () => {});

    expect(container.querySelector('.rent-trend')).toBeNull();
    expect(container.querySelector('.rent__floors')).not.toBeNull();
    expect(widthOf(container, '1')).toBe('100%');
    expect(screen.getByText('공실률 6.74%')).toBeTruthy();
  });

  it.each([
    ['모양 이상(한 줄 값이 글자)', () => [...hist('집합상가', COLL_VAC), { ...hist('집합상가', COLL_VAC)[0], yield_rate: '1' }]],
    ['빈 답', () => []],
    ['마지막 분기 값이 카드 줄과 다름(다른 조사구역)', () => hist('집합상가', COLL_VAC, (i) => (i === 7 ? { vacancy_rate: 9.99 } : {}))],
    ['같은 분기 둘', () => [...hist('집합상가', COLL_VAC), hist('집합상가', COLL_VAC)[3]]],
    ['다른 조사구역뿐', () => hist('집합상가', COLL_VAC).map((r) => ({ ...r, rone_region_nm: '서울>강남>신사역' }))],
  ])('★ %s → 흐름만 조용히 빠진다', async (_name, data) => {
    responses.history = { data: data(), error: null };
    const { container } = render(<RentStatSection pnu={PNU} />);
    await openCard();
    await waitFor(() => expect(historyCalls()).toHaveLength(1));
    await act(async () => {});

    expect(container.querySelector('.rent-trend')).toBeNull();
    expect(container.querySelector('.rent__floors')).not.toBeNull();
  });

  it('★ 필지가 바뀌면 늦게 온 옛 필지 흐름 답은 버린다(cancelled)', async () => {
    let resolveOld: (v: { data: unknown; error: unknown }) => void = () => {};
    responses.history = new Promise((r) => {
      resolveOld = r;
    });
    const { rerender, container } = render(<RentStatSection pnu={PNU} />);
    await openCard();

    // 새 필지: 카드 답은 같은 꼴 · 흐름은 실패.
    responses.history = HISTORY_MISSING;
    rerender(<RentStatSection pnu="1168010100100020000" />);
    await screen.findByText('상권 임대 동향 (부동산원 조사)');
    // 늦게 온 **옛 필지** 흐름 답 — 새 필지 카드에 붙으면 안 된다.
    await act(async () => {
      resolveOld({ data: [...hist('집합상가', COLL_VAC), ...hist('오피스', OFF_VAC)], error: null });
    });
    if (!container.querySelector('.rent__rows')) fireEvent.click(screen.getByRole('button', { name: /상권 임대 동향/ }));
    expect(container.querySelector('.rent__rows')).not.toBeNull();
    expect(container.querySelector('.rent-trend')).toBeNull();
    expect(historyCalls().map((c) => c.args)).toEqual([{ p_pnu: PNU }, { p_pnu: '1168010100100020000' }]);
  });

  it('★ 받아 둔 흐름이 있어도 필지가 바뀌면 비운다(새 필지 흐름이 실패해도 옛 그림이 안 남는다)', async () => {
    const { rerender, container } = render(<RentStatSection pnu={PNU} />);
    await openCard();
    await waitFor(() => expect(container.querySelector('.rent-trend')).not.toBeNull());

    responses.history = HISTORY_MISSING;
    rerender(<RentStatSection pnu="1168010100100020000" />);
    await waitFor(() => expect(historyCalls()).toHaveLength(2));
    await act(async () => {});
    if (!container.querySelector('.rent__rows')) fireEvent.click(screen.getByRole('button', { name: /상권 임대 동향/ }));
    expect(container.querySelector('.rent__rows')).not.toBeNull();
    expect(container.querySelector('.rent-trend')).toBeNull();
  });
});
