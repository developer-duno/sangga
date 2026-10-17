import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, within, fireEvent } from '@testing-library/react';

/**
 * 화면 맨 아래 — 「함께 보면 좋은 사이트」 구역 시험(2026-10-06 · 2u 인계 10-05).
 *
 * 여기서 지키는 것 둘:
 *  ① **링크 두 개의 글자·주소·새 창·`rel`** — `rel` 이 없으면 새 창으로 열린 쪽이 우리 창을
 *     되돌려 다른 주소로 보낼 수 있다. 눈으로는 절대 안 보이는 종류라 시험이 방어선이다.
 *  ② **이 이름의 구역이 하나뿐** — 넘기기 구역(`HandoffLinks`) 안에 섞이거나 두 번 그려지면
 *     읽어 주는 기기에서 같은 이름의 길잡이가 겹친다.
 *
 * 신선도 표·의견함은 서버를 부르므로 그 입구만 막아 둔다(답이 없으면 신선도 표는 조용히 빈다).
 */

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: () => Promise.resolve({ data: null, error: { code: 'PGRST202', message: 'none' } }),
  },
}));

const { AppFooter } = await import('./AppFooter');

afterEach(cleanup);

const FAMILY = [
  { label: '2u부동산(아파트 매물·시세)', href: 'https://2u.pe.kr' },
  { label: '미분양 아파트 비교', href: 'https://mibunyang-peach.vercel.app' },
];

describe('AppFooter — 함께 보면 좋은 사이트', () => {
  it('접근 이름 「함께 보면 좋은 사이트」의 nav 가 하나 서고 머리말이 보인다', () => {
    render(<AppFooter />);

    const navs = screen.getAllByRole('navigation', { name: '함께 보면 좋은 사이트' });
    expect(navs).toHaveLength(1);
    expect(within(navs[0]).getByText('함께 보면 좋은 사이트')).toBeTruthy();
  });

  it('★ 링크 두 개 — 글자 그대로 · 주소 · 새 창 + rel', () => {
    render(<AppFooter />);

    const nav = screen.getByRole('navigation', { name: '함께 보면 좋은 사이트' });
    const links = within(nav).getAllByRole('link');
    expect(links).toHaveLength(FAMILY.length);

    for (const f of FAMILY) {
      const a = within(nav).getByRole('link', { name: f.label });
      expect(a.getAttribute('href'), `${f.label} 주소`).toBe(f.href);
      expect(a.getAttribute('target'), `${f.label} 새 창`).toBe('_blank');
      expect(a.getAttribute('rel'), `${f.label} rel`).toBe('noopener noreferrer');
    }
  });

  it('넘기기 구역(「더 필요하면 여기서」) 안에 섞이지 않는다', () => {
    render(<AppFooter />);

    const handoff = screen.getByRole('heading', { name: '더 필요하면 여기서' }).closest('section');
    expect(handoff).not.toBeNull();
    for (const f of FAMILY) {
      expect(within(handoff as HTMLElement).queryByRole('link', { name: f.label })).toBeNull();
    }
  });
});

describe('AppFooter — 휴대폰 더보기 차례(결정 0039 W4a)', () => {
  it('★ 의견함은 차례를 바꿔도 같은 자리(맨 뒤) — 폰을 돌려 휴대폰 ↔ 넓은 꼴이 바뀌어도 쓰던 글이 남는다(검사 🟡 F8)', () => {
    const lead = <section className="role">역할 줄</section>;
    const { container, rerender } = render(<AppFooter lead={lead} phoneOrder />);
    const foot = container.querySelector('footer.foot')!;
    expect(foot.classList.contains('foot--phone')).toBe(true);
    expect(foot.firstElementChild?.classList.contains('role')).toBe(true);
    expect(foot.lastElementChild?.classList.contains('fb')).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '의견 보내기' }));
    const box = within(foot as HTMLElement).getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: '쓰던 글' } });

    rerender(<AppFooter />);
    expect(foot.classList.contains('foot--phone')).toBe(false);
    expect(foot.firstElementChild?.classList.contains('foot__notice')).toBe(true);
    const after = within(foot as HTMLElement).getByRole('textbox') as HTMLTextAreaElement;
    expect(after).toBe(box); // 같은 물건 — 다시 태어나지 않았다
    expect(after.value).toBe('쓰던 글');
  });
});
