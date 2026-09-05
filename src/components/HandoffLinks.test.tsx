import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

import { HandoffLinks } from './HandoffLinks';
import { HANDOFF_GROUPS } from '../lib/handoffLinks';
import { SECTION_PLAN } from '../lib/sectionCards';

/**
 * 넘기기 링크 구역 시험.
 *
 * 여기서 지키는 것 셋:
 *  ① **새 창 링크에 `rel` 이 붙어 있는가** — 없으면 열린 쪽이 우리 창을 되돌려 다른
 *     주소로 보낼 수 있다. 눈으로는 절대 안 보이는 종류라 시험이 유일한 방어선이다.
 *  ② **접힘이 진짜 접혀 있는가** — 본문을 DOM 에 두고 `hidden` 으로 감추는 방식이라
 *     "DOM 에 있다"로는 아무것도 증명되지 않는다. 사용자가 겪는 것은 "안 보인다"다.
 *  ③ **카드 목록이 `SECTION_PLAN` 을 따라오는가** — 손으로 적은 목록이면 카드가 느는
 *     날 안내만 옛말을 한다.
 */

afterEach(cleanup);

describe('HandoffLinks — 넘기는 곳 목록', () => {
  it('묶음 이름과 링크가 전부 그려진다', () => {
    render(<HandoffLinks />);

    expect(screen.getByRole('heading', { name: '더 필요하면 여기서' })).toBeTruthy();
    for (const g of HANDOFF_GROUPS) {
      expect(screen.getByText(g.need), `${g.need} 묶음`).toBeTruthy();
      for (const l of g.links) {
        expect(screen.getByRole('link', { name: l.label }), `${l.label} 링크`).toBeTruthy();
      }
    }
  });

  it('★ 링크마다 새 창 + rel 이 함께 붙는다 (없으면 열린 쪽이 우리 창을 빼앗을 수 있다)', () => {
    render(<HandoffLinks />);

    for (const g of HANDOFF_GROUPS) {
      for (const l of g.links) {
        const a = screen.getByRole('link', { name: l.label });
        expect(a.getAttribute('href'), `${l.label} 의 주소`).toBe(l.href);
        expect(a.getAttribute('target'), `${l.label} 의 target`).toBe('_blank');
        expect(a.getAttribute('rel'), `${l.label} 의 rel`).toBe('noopener noreferrer');
      }
    }
  });
});

describe('HandoffLinks — 접힌 "어디서 뭐를 보나"', () => {
  /** 접기 버튼. 이름으로 찾는다 — 화살표는 aria-hidden 이라 이름에 안 섞인다. */
  function guideButton() {
    return screen.getByRole('button', { name: '어디서 뭐를 보나' });
  }

  it('처음에는 접혀 있다 — 본문이 DOM 에는 있지만 보이지 않는다', () => {
    const { container } = render(<HandoffLinks />);

    expect(guideButton().getAttribute('aria-expanded')).toBe('false');

    const body = container.querySelector('.links__guide-body');
    // ⚠️ "DOM 에 없다"가 아니라 **"안 보인다"**로 본다(결정 0020 이후의 규칙).
    expect(body).toBeTruthy();
    expect((body as HTMLElement).hidden).toBe(true);
  });

  it('누르면 펼쳐지고 다시 누르면 접힌다', () => {
    const { container } = render(<HandoffLinks />);
    const body = container.querySelector('.links__guide-body') as HTMLElement;

    fireEvent.click(guideButton());
    expect(guideButton().getAttribute('aria-expanded')).toBe('true');
    expect(body.hidden).toBe(false);

    fireEvent.click(guideButton());
    expect(guideButton().getAttribute('aria-expanded')).toBe('false');
    expect(body.hidden).toBe(true);
  });

  it('버튼이 가리키는 곳이 실제로 그 본문이다 (aria-controls 가 허공을 안 가리킨다)', () => {
    const { container } = render(<HandoffLinks />);
    const id = guideButton().getAttribute('aria-controls');

    expect(id).toBeTruthy();
    const body = container.querySelector('.links__guide-body');
    expect(body?.getAttribute('id')).toBe(id);
  });

  it('★ 펼치면 카드 제목이 SECTION_PLAN 대로 전부 나온다 (손으로 적은 목록이 아니다)', () => {
    render(<HandoffLinks />);
    fireEvent.click(guideButton());

    for (const plan of Object.values(SECTION_PLAN)) {
      expect(screen.getByText(plan.title), `${plan.title} 안내`).toBeTruthy();
    }
  });

  it('펼치면 역할 셋의 시작점이 나온다', () => {
    render(<HandoffLinks />);
    fireEvent.click(guideButton());

    for (const role of ['창업자', '투자자', '중개사']) {
      expect(screen.getByText(role), `${role} 시작점`).toBeTruthy();
    }
  });
});
