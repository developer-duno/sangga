import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';

/**
 * 빈 카드 하나(결정 0036 결정 2 · 물결 1-B).
 *
 * 여기서 특히 지키는 것
 *  ① 접힌 채 서고 요약 한 줄이 보인다(접힘 ≠ 숨김) · 본문은 그려 두고 감춘다(인쇄 규칙 결정 0020)
 *  ② **아무것도 부르지 않는다** — 서버 함수 0
 *  ③ 빈 상태 이름표 `card--empty`(종이에서 빠지는 이름표)가 붙는다
 */

const rpcCalls: string[] = [];
/**
 * 신선도 함수만은 **정상 답**을 준다(검사 뒤 보완 F7) — 그래야 빈 카드가 자료 칸을 빼지 않았을 때 날짜 줄이 실제로 선다
 * (빈 답이면 자료 칸이 있어도 줄이 안 서서 「줄 0」 시험이 헛돈다). 서울 상권 4종 세 줄은 정본 꼴 그대로.
 */
const FRESH_ROWS = [
  { src: '상권 추정매출 (서울시)', basis_kind: '분기', basis: '20262', next_expected: null, cadence: '분기마다' },
  { src: '상권 길단위인구 (서울시)', basis_kind: '분기', basis: '20262', next_expected: null, cadence: '분기마다' },
  {
    src: '상권 상주·직장인구 (서울시)',
    basis_kind: '값이 바뀐 분기',
    basis: '상주 2023년 4분기, 직장 2024년 4분기',
    next_expected: null,
    cadence: '연 1회',
  },
];
vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string) => {
      rpcCalls.push(fn);
      if (fn === 'get_data_freshness') return Promise.resolve({ data: FRESH_ROWS, error: null });
      return Promise.resolve({ data: null, error: null });
    },
    from: (t: string) => {
      rpcCalls.push(`from:${t}`);
      throw new Error('빈 카드는 아무것도 부르지 않는다');
    },
  },
}));

const { EmptySection } = await import('./EmptySection');
const { SectionCard } = await import('./SectionCard');
const { SECTION_PLAN } = await import('../lib/sectionCards');
const { resetDataFreshnessCache } = await import('../lib/loadDataFreshness');

beforeEach(() => {
  resetDataFreshnessCache();
});

afterEach(() => {
  cleanup();
  rpcCalls.length = 0;
});

describe('EmptySection', () => {
  it('★ 접힌 채 서고 제목·역할·요약이 보이며, 본문은 감춰져 있다', () => {
    const { container } = render(<EmptySection kind="sales" pnu="1168010500101590000" />);
    const card = container.querySelector('section.card')!;
    // 제목은 정본 한 곳(SECTION_PLAN) — 결정 0045 PR③ 부터 「(서울시 추정)」이 붙는다(서울 건물은 제 컴포넌트가 그린다).
    expect(card.querySelector('.card__title')?.textContent).toBe('업종별 추정매출 (서울시 추정)');
    expect(card.querySelector('.card__role')?.textContent).toBe('창업자');
    expect(card.querySelector('.card__summary')?.textContent).toBe('지금은 비어 있음');
    expect(screen.getByRole('button').getAttribute('aria-expanded')).toBe('false');
    expect(card.querySelector('.card__body')?.hasAttribute('hidden')).toBe(true);

    fireEvent.click(screen.getByRole('button'));
    expect(card.querySelector('.empty__body')?.textContent).toBe(
      '지금은 비어 있음 — 서울시가 상권마다 공표하는 업종별 추정매출을 받으면 이 자리에 그대로 싣습니다',
    );
  });

  it('★ 빈 상태 이름표 card--empty 와 카드 이름표가 붙는다(종이에서 빠지는 길)', () => {
    for (const kind of ['sales', 'pop'] as const) {
      const { container, unmount } = render(<EmptySection kind={kind} pnu="1168010500101590000" />);
      const cls = container.querySelector('section.card')!.classList;
      expect(cls.contains('card--empty')).toBe(true);
      expect(cls.contains(`card--${kind}`)).toBe(true);
      unmount();
    }
  });

  it('★ 아무것도 부르지 않는다(서버 함수 0)', async () => {
    render(<EmptySection kind="pop" pnu="3011010700108770000" />);
    render(<EmptySection kind="sales" pnu="3011010700108770000" />);
    await Promise.resolve();
    expect(rpcCalls).toEqual([]);
  });

  it('⛔ sales·pop 칸의 자료 칸(서울 카드용 · 결정 0045 PR③)이 있어도 빈 카드에는 날짜 줄이 없고 신선도도 안 묻는다', async () => {
    const sales = render(<EmptySection kind="sales" pnu="3011010700108770000" />);
    const pop = render(<EmptySection kind="pop" pnu="3011010700108770000" />);
    await new Promise((r) => setTimeout(r, 0));
    expect(sales.container.querySelector('.card__src')).toBeNull();
    expect(pop.container.querySelector('.card__src')).toBeNull();
    expect(rpcCalls).toEqual([]);
  });

  it('양성 대조 — 같은 칸(자료 칸 있음)을 빈 카드 거르기 없이 그리면 날짜 줄이 서고 신선도를 묻는다(위 「줄 0」이 헛돌지 않는다)', async () => {
    expect(SECTION_PLAN.sales.sources?.length).toBeGreaterThan(0);
    const { container } = render(<SectionCard plan={SECTION_PLAN.pop} className="card--empty" summary="비어 있음" />);
    await waitFor(() => expect(container.querySelector('.card__src')).not.toBeNull());
    expect(container.querySelector('.card__src')?.textContent).toContain('서울시 상권분석서비스 2026년 2분기');
    expect(rpcCalls).toEqual(['get_data_freshness']);
  });

  it('대전 건물의 유동인구는 그 사실 한 줄(요약·본문)', () => {
    const { container } = render(<EmptySection kind="pop" pnu="3011010700108770000" />);
    expect(container.querySelector('.card__summary')?.textContent).toBe('대전은 아직 받지 않았습니다');
    expect(container.querySelector('.empty__body')?.textContent).toBe(
      '서울시 자료는 서울만 — 대전은 아직 받지 않았습니다',
    );
  });
});
