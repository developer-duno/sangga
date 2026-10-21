import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { RoleCards } from './RoleCards';

/**
 * 역할 고르기 큰 카드(결정 0039 Q3 · W3) — 글 그대로(👤 2026-10-17 시안 A) · 카드 = 그 역할 · 둘러보기 = null.
 * 언제 서는지·저장은 위(App)가 한다 — `App.test` 「큰 카드」 묶음.
 */
afterEach(cleanup);

describe('RoleCards', () => {
  it('질문 + 카드 셋(이름 + 한 줄) + 그냥 둘러보기 + 안내 한 줄 — 글 그대로', () => {
    const { container } = render(<RoleCards onPick={() => {}} />);
    expect(container.querySelector('.rolecards__q')?.textContent).toBe('무엇을 하러 오셨나요?');
    const cards = [...container.querySelectorAll('.rolecards__card')].map((b) => [
      b.querySelector('.rolecards__name')?.textContent,
      b.querySelector('.rolecards__line')?.textContent,
    ]);
    expect(cards).toEqual([
      ['투자·매입하려고', '실거래·층별 공표값을 먼저 펼쳐 둡니다'],
      ['가게를 열려고', '상권 지도·업종 분포를 먼저 보여 드립니다'],
      ['중개하려고', '층별 호실·한 장으로 뽑기를 먼저 둡니다'],
    ]);
    expect(screen.getByRole('button', { name: '그냥 둘러보기' })).toBeTruthy();
    expect(container.querySelector('.rolecards__note')?.textContent).toBe(
      '이 기기에만 저장 · 나중에 위 「나는」에서 언제든 바꿀 수 있어요',
    );
    // 질문이 이 묶음의 이름이다(낭독기).
    expect(screen.getByRole('region', { name: '무엇을 하러 오셨나요?' })).toBeTruthy();
  });

  it('카드를 누르면 그 역할 · 둘러보기를 누르면 null 을 알린다', () => {
    const onPick = vi.fn();
    render(<RoleCards onPick={onPick} />);
    fireEvent.click(screen.getByRole('button', { name: /투자·매입하려고/ }));
    fireEvent.click(screen.getByRole('button', { name: /가게를 열려고/ }));
    fireEvent.click(screen.getByRole('button', { name: /중개하려고/ }));
    fireEvent.click(screen.getByRole('button', { name: '그냥 둘러보기' }));
    expect(onPick.mock.calls).toEqual([['투자자'], ['창업자'], ['중개사'], [null]]);
  });

  it('덮개가 아니다 — dialog 도, 화면 전체를 막는 자리도 아니다', () => {
    const { container } = render(<RoleCards onPick={() => {}} />);
    expect(container.querySelector('[role="dialog"], [aria-modal]')).toBeNull();
  });
});
