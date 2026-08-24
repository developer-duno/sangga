import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { PrintButton } from './PrintButton';

/**
 * 종이로 뽑기 버튼.
 *
 * 여기서 지키는 것은 둘뿐이다 — **브라우저의 기본 인쇄를 부른다**는 것과, 그 버튼이
 * 읽어 주는 기기에도 이름으로 잡힌다는 것. 종이의 모양을 정하는 일은 이 버튼이 아니라
 * 인쇄 규칙(CSS)이 한다(`PrintButton.tsx` 머리말 — 사용자는 Ctrl+P 로도 인쇄한다).
 */
afterEach(cleanup);

describe('PrintButton', () => {
  it('누르면 브라우저의 기본 인쇄를 부른다', () => {
    // jsdom 에는 진짜 인쇄가 없다("Not implemented" 를 뱉는다) — 불렸는지만 본다.
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});

    render(<PrintButton />);
    fireEvent.click(screen.getByRole('button', { name: /인쇄/ }));

    expect(print).toHaveBeenCalledTimes(1);
    print.mockRestore();
  });

  it('무엇을 하는 버튼인지 이름에 적는다 (PDF 저장도 같은 길이라는 것까지)', () => {
    render(<PrintButton />);
    // "인쇄"만 적으면 종이가 없는 사람은 자기와 상관없다고 읽는다 — 이 버튼 하나로
    // PDF 저장까지 된다는 사실이 이름에 있어야 한다.
    expect(screen.getByRole('button').textContent).toBe('인쇄 · PDF로 저장');
  });

  it('폼 안에 들어가도 제출 버튼이 되지 않는다', () => {
    // type 을 안 주면 button 은 submit 이 된다 — 언젠가 폼 안으로 옮겨졌을 때
    // 누르는 순간 페이지가 새로고침된다.
    render(<PrintButton />);
    expect(screen.getByRole('button').getAttribute('type')).toBe('button');
  });
});
