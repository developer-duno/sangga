import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { RecentPrinted } from './RecentPrinted';
import type { RecentPrinted as Entry } from '../lib/recentPrintedStore';

/**
 * 중개사 「최근 뽑은 건물」 접힌 줄(결정 0036 결정 18 ⑥⑩ · 「이 기기 저장」 ②③④).
 * 역할 조건·저장·고른 뒤 이동은 App.test 가 본다 — 여기는 그리기만.
 */
afterEach(cleanup);

function entry(n: number, over: Partial<Entry> = {}): Entry {
  return {
    bld_id: `b${n}`,
    pnu: '1168010100100010000',
    bld_nm: `빌딩${n}`,
    road_addr: `서울 강남구 테헤란로 ${n}`,
    bld_cnt_in_pnu: 1,
    floor_cnt: 3,
    min_floor: 1,
    max_floor: 3,
    has_roof: false,
    ...over,
  };
}

describe('RecentPrinted', () => {
  it('★ 목록이 비면 줄 자체를 안 그린다 — 양성 대조: 한 건이면 선다', () => {
    const { container, rerender } = render(
      <RecentPrinted items={[]} onPick={vi.fn()} onClear={vi.fn()} />,
    );
    expect(container.querySelector('.recent')).toBeNull();
    rerender(<RecentPrinted items={[entry(1)]} onPick={vi.fn()} onClear={vi.fn()} />);
    expect(container.querySelector('.recent')).not.toBeNull();
  });

  it('처음엔 접혀 있다(개수만) · 누르면 펼쳐 이름·주소 · 다시 누르면 접힌다', () => {
    render(<RecentPrinted items={[entry(1), entry(2), entry(3)]} onPick={vi.fn()} onClear={vi.fn()} />);
    const toggle = screen.getByRole('button', { name: /최근 뽑은 건물 3/ });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByText('빌딩1')).toBeNull();
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('빌딩1')).toBeTruthy();
    expect(screen.getByText('서울 강남구 테헤란로 3')).toBeTruthy();
    fireEvent.click(toggle);
    expect(screen.queryByText('빌딩1')).toBeNull();
  });

  it('이름·주소가 없으면 검색 결과 줄과 같은 글', () => {
    render(
      <RecentPrinted items={[entry(1, { bld_nm: null, road_addr: '' })]} onPick={vi.fn()} onClear={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /최근 뽑은 건물/ }));
    expect(screen.getByText('(이름 없는 건물)')).toBeTruthy();
    expect(screen.getByText('주소 없음')).toBeTruthy();
  });

  it('줄을 누르면 그 건물을 넘긴다 · 「지우기」는 onClear', () => {
    const onPick = vi.fn();
    const onClear = vi.fn();
    render(<RecentPrinted items={[entry(1), entry(2)]} onPick={onPick} onClear={onClear} />);
    fireEvent.click(screen.getByRole('button', { name: /최근 뽑은 건물/ }));
    fireEvent.click(screen.getByRole('button', { name: /빌딩2/ }));
    expect(onPick).toHaveBeenCalledWith(entry(2));
    expect(onClear).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '지우기' }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it('펼친 안에 안내 두 줄(이 기기에만 · 사무소 컴퓨터면 지워 주세요)', () => {
    const { container } = render(
      <RecentPrinted items={[entry(1)]} onPick={vi.fn()} onClear={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /최근 뽑은 건물/ }));
    const notes = [...container.querySelectorAll('.recent__note')].map((p) => p.textContent);
    expect(notes).toEqual([
      '이 기기에만 저장 · 서버로 보내지 않음',
      '여럿이 쓰는 사무소 컴퓨터라면 다 본 뒤 지워 주세요',
    ]);
  });

  it('모든 단추가 type="button" (폼 안에 들어가도 제출이 되지 않게)', () => {
    render(<RecentPrinted items={[entry(1)]} onPick={vi.fn()} onClear={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /최근 뽑은 건물/ }));
    const btns = screen.getAllByRole('button');
    expect(btns.length).toBe(3);
    for (const b of btns) expect(b.getAttribute('type')).toBe('button');
  });
});
