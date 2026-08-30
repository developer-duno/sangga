import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import type { RentStat } from '../types';

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

const responses = { rent: { data: null as unknown, error: null as unknown } };

/** 마지막 rpc 호출들. 함수 이름과 **인자 이름·값**을 여기서 확인한다. */
const rpcCalls: Array<{ fn: string; args: unknown }> = [];

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string, args?: unknown) => {
      rpcCalls.push({ fn, args });
      return Promise.resolve(responses.rent);
    },
  },
}));

const { RentStatSection } = await import('./RentStatSection');

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
  responses.rent = { data: [stat()], error: null };
});

afterEach(() => cleanup());

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

    expect(rpcCalls).toEqual([{ fn: 'list_rent_stats', args: { p_pnu: PNU } }]);
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

    await waitFor(() => expect(rpcCalls).toHaveLength(1));
    // "조사값 없음"이라 적지 않는다 — 없는 것과 모르는 것은 다르다.
    expect(container.querySelector('.rent')).toBeNull();
    expect(container.textContent).toBe('');
  });

  it('★ 뜻밖의 모양이 와도 터지지 않고 카드만 사라진다', async () => {
    // 다른 함수의 응답이 흘러든 경우. 렌더 중에 터지면 층별 화면 전체가 오류 안내가 된다.
    responses.rent = { data: { code: 'PGRST202', message: 'x' }, error: null };
    const { container } = render(<RentStatSection pnu={PNU} />);

    await waitFor(() => expect(rpcCalls).toHaveLength(1));
    expect(container.textContent).toBe('');
  });

  it('값 자리에 글자가 온 줄이 섞여 있어도 통째로 접는다', async () => {
    responses.rent = {
      data: [stat(), { ...stat(), vacancy_rate: '10.08' }],
      error: null,
    };
    const { container } = render(<RentStatSection pnu={PNU} />);

    await waitFor(() => expect(rpcCalls).toHaveLength(1));
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
    expect(rpcCalls.map((c) => c.args)).toEqual([
      { p_pnu: PNU },
      { p_pnu: '1168010100100020000' },
    ]);
  });
});
