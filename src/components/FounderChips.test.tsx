import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { FounderChips } from './FounderChips';

/**
 * 창업자 업종 칩 줄(👤 결정 0036 결정 18 ⑤⑨) — 칩 여섯 · 하나만 눌린 모양(`aria-pressed`).
 * 상태는 위(App)가 쥔다 — 여기서는 무엇을 알리는지만 본다. 창업자에게만 서는지는 `App.test`.
 */
afterEach(cleanup);

describe('FounderChips', () => {
  it('칩 여섯 개가 카페·한식·미용·학원·편의점·전체 차례로 선다', () => {
    render(<FounderChips chip="전체" onChange={() => {}} />);
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual([
      '카페',
      '한식',
      '미용',
      '학원',
      '편의점',
      '전체',
    ]);
  });

  it('고른 칩 하나만 눌린 모양이다', () => {
    render(<FounderChips chip="미용" onChange={() => {}} />);
    const pressed = screen
      .getAllByRole('button')
      .filter((b) => b.getAttribute('aria-pressed') === 'true')
      .map((b) => b.textContent);
    expect(pressed).toEqual(['미용']);
  });

  it('다른 칩을 누르면 그 칩을 알린다', () => {
    const onChange = vi.fn();
    render(<FounderChips chip="전체" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: '카페' }));
    expect(onChange).toHaveBeenCalledWith('카페');
  });

  it('고른 칩을 다시 눌러도 풀리지 않는다 — 되돌리기는 전체 칩이다', () => {
    const onChange = vi.fn();
    render(<FounderChips chip="카페" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: '카페' }));
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '전체' }));
    expect(onChange).toHaveBeenCalledWith('전체');
  });
});

describe('FounderChips — 안내 한 줄 (👤 F4)', () => {
  it('칩 줄 곁에 작은 글 — 글자 그대로', () => {
    const { container } = render(<FounderChips chip="전체" onChange={() => {}} />);
    expect(container.querySelector('.chips .chips__note')?.textContent).toBe(
      '건물을 열면 업종 분포·개업·폐업 카드에 반영됩니다',
    );
  });
});
