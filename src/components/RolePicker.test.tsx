import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { RolePicker } from './RolePicker';

/**
 * 역할 단추 줄(👤 결정 0036 결정 18 ⑧) — 단추 셋 · 눌린 모양(`aria-pressed`) · 다시 누르면 해제.
 * 저장은 위(App)가 한다 — 여기서는 무엇을 알리는지만 본다.
 */
afterEach(cleanup);

describe('RolePicker', () => {
  it('나는 [투자자][창업자][중개사] + 안내 한 줄', () => {
    const { container } = render(<RolePicker role={null} onChange={() => {}} />);
    expect(container.querySelector('.role__lead')?.textContent).toBe('나는');
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual([
      '투자자',
      '창업자',
      '중개사',
    ]);
    expect(screen.getByText('고르면 화면 순서가 맞춰집니다 · 이 기기에만 저장 · 다시 누르면 해제')).toBeTruthy();
  });

  it('고르기 전에는 아무 단추도 눌려 있지 않다', () => {
    render(<RolePicker role={null} onChange={() => {}} />);
    for (const b of screen.getAllByRole('button')) {
      expect(b.getAttribute('aria-pressed')).toBe('false');
    }
  });

  it('고른 단추만 눌린 모양이다', () => {
    render(<RolePicker role="창업자" onChange={() => {}} />);
    expect(screen.getByRole('button', { name: '창업자' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: '투자자' }).getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByRole('button', { name: '중개사' }).getAttribute('aria-pressed')).toBe('false');
  });

  it('안 눌린 단추를 누르면 그 역할을 알린다', () => {
    const onChange = vi.fn();
    render(<RolePicker role="투자자" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: '중개사' }));
    expect(onChange).toHaveBeenCalledWith('중개사');
  });

  it('★ 고른 단추를 다시 누르면 해제를 알린다 (null)', () => {
    const onChange = vi.fn();
    render(<RolePicker role="투자자" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: '투자자' }));
    expect(onChange).toHaveBeenCalledWith(null);
  });
});
