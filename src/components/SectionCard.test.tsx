import { describe, it, expect, afterEach } from 'vitest';
import { useState } from 'react';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { SectionCard } from './SectionCard';
import type { SectionPlan } from '../lib/sectionCards';

/**
 * 공통 카드 틀 — 로드맵 Wave 2 『한 장 요약 접힘 틀』.
 *
 * 여기서 지키는 것은 셋이다:
 *   ① 기본 펼침/접힘이 배치표(`SECTION_PLAN`)가 시킨 대로 나온다
 *   ② 눌러서 접고 펼칠 수 있고, 그 상태를 읽어 주는 기기도 안다(`aria-expanded`)
 *   ③ **접혀 있어도 제목과 핵심 한 줄은 보인다** — 접힘이 숨김이 되면 안 된다
 */

const OPEN: SectionPlan = { title: '층 목록', role: '공통', defaultOpen: true };
const CLOSED: SectionPlan = { title: '참고 매매 시세 (추정값)', role: '투자자', defaultOpen: false };

afterEach(cleanup);

describe('SectionCard — 기본 상태', () => {
  it('defaultOpen 이 참이면 본문이 처음부터 보인다', () => {
    render(
      <SectionCard plan={OPEN} className="card--floors" summary="층 3개 · 점포 12곳">
        <p>본문입니다</p>
      </SectionCard>,
    );
    expect(screen.getByText('본문입니다')).toBeTruthy();
    expect(screen.getByRole('button').getAttribute('aria-expanded')).toBe('true');
  });

  it('defaultOpen 이 거짓이면 본문을 안 그린다', () => {
    render(
      <SectionCard plan={CLOSED} className="band" summary="값을 낸 층 2개">
        <p>본문입니다</p>
      </SectionCard>,
    );
    expect(screen.queryByText('본문입니다')).toBeNull();
    expect(screen.getByRole('button').getAttribute('aria-expanded')).toBe('false');
  });

  it('접혀 있어도 제목과 핵심 한 줄은 그대로 보인다 (접힘 ≠ 숨김)', () => {
    const { container } = render(
      <SectionCard plan={CLOSED} className="band" summary="값을 낸 층 2개">
        <p>본문입니다</p>
      </SectionCard>,
    );
    expect(screen.getByText('참고 매매 시세 (추정값)')).toBeTruthy();
    expect(container.querySelector('.card__summary')?.textContent).toBe('값을 낸 층 2개');
  });

  it('역할 태그를 카드 머리에 적는다', () => {
    const { container } = render(
      <SectionCard plan={CLOSED} className="band" summary="값을 낸 층 2개" />,
    );
    expect(container.querySelector('.card__role')?.textContent).toBe('투자자');
  });
});

describe('SectionCard — 접고 펼치기', () => {
  it('누르면 펼쳐지고 다시 누르면 접힌다', () => {
    render(
      <SectionCard plan={CLOSED} className="band" summary="값을 낸 층 2개">
        <p>본문입니다</p>
      </SectionCard>,
    );
    const toggle = screen.getByRole('button');

    fireEvent.click(toggle);
    expect(screen.getByText('본문입니다')).toBeTruthy();
    expect(toggle.getAttribute('aria-expanded')).toBe('true');

    fireEvent.click(toggle);
    expect(screen.queryByText('본문입니다')).toBeNull();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
  });

  it('접으면 요약은 남고 본문만 사라진다', () => {
    const { container } = render(
      <SectionCard plan={OPEN} className="card--floors" summary="층 3개 · 점포 12곳">
        <p>본문입니다</p>
      </SectionCard>,
    );
    fireEvent.click(screen.getByRole('button'));
    expect(container.querySelector('.card__body')).toBeNull();
    expect(container.querySelector('.card__summary')?.textContent).toBe('층 3개 · 점포 12곳');
  });

  it('접힌 카드에는 표시용 class 가 붙는다', () => {
    const { container } = render(
      <SectionCard plan={CLOSED} className="band" summary="값을 낸 층 2개">
        <p>본문입니다</p>
      </SectionCard>,
    );
    expect(container.querySelector('section')?.className).toContain('card--closed');
    fireEvent.click(screen.getByRole('button'));
    expect(container.querySelector('section')?.className).not.toContain('card--closed');
  });
});

describe('SectionCard — 겉모양 계약', () => {
  it('넘겨받은 class 를 겉 section 에 그대로 붙인다 (기존 스타일·시험이 이 이름으로 찾는다)', () => {
    const { container } = render(
      <SectionCard plan={OPEN} className="mix mix--wait" summary="불러오는 중…" />,
    );
    const section = container.querySelector('section');
    expect(section?.classList.contains('card')).toBe(true);
    expect(section?.classList.contains('mix')).toBe(true);
    expect(section?.classList.contains('mix--wait')).toBe(true);
  });

  it('본문이 없으면 빈 상자를 남기지 않는다', () => {
    const { container } = render(
      <SectionCard plan={OPEN} className="band band--wait" summary="불러오는 중…" />,
    );
    expect(container.querySelector('.card__body')).toBeNull();
  });

  it('본문이 없으면 접기 버튼도 안 만든다 (눌러도 아무 일 없는 버튼 금지)', () => {
    // 로딩 카드 둘(업종 분포·참고 시세의 "불러오는 중…")이 정확히 이 상태다. 눈으로 보는
    // 사람에게는 안 열리는 화살표지만, 읽어 주는 기기를 쓰는 사람에게는 "펼칠 수 있음"이라는
    // 거짓말이라 없는 내용을 찾아 헤매게 된다.
    const { container } = render(
      <SectionCard plan={OPEN} className="band band--wait" summary="불러오는 중…" />,
    );
    expect(screen.queryByRole('button')).toBeNull();
    expect(container.querySelector('[aria-expanded]')).toBeNull();
    expect(container.querySelector('.card__caret')).toBeNull();
    // 제목과 요약은 그대로 보인다 — 버튼만 없는 것이다.
    expect(container.querySelector('.card__title')?.textContent).toBe('층 목록');
    expect(container.querySelector('.card__summary')?.textContent).toBe('불러오는 중…');
  });

  it('본문이 있으면 안 그리는 자식(false·null)만으로는 버튼을 만들지 않는다', () => {
    // `{cond && <p/>}` 가 거짓일 때가 이 경우다. `Children.count` 로 세면 1개로 잡혀
    // 빈 버튼이 생긴다 — `toArray` 라야 걸러진다.
    const show = false;
    render(
      <SectionCard plan={OPEN} className="mix" summary="요약">
        {show && <p>본문입니다</p>}
        {null}
      </SectionCard>,
    );
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('펼쳤을 때 버튼이 본문을 aria-controls 로 가리킨다', () => {
    const { container } = render(
      <SectionCard plan={OPEN} className="card--floors" summary="층 3개">
        <p>본문입니다</p>
      </SectionCard>,
    );
    const controls = screen.getByRole('button').getAttribute('aria-controls');
    expect(controls).toBeTruthy();
    expect(container.querySelector('.card__body')?.id).toBe(controls);
  });

  it('접혀 있으면 가리킬 본문이 없으므로 aria-controls 도 안 붙인다', () => {
    render(
      <SectionCard plan={CLOSED} className="band" summary="값을 낸 층 2개">
        <p>본문입니다</p>
      </SectionCard>,
    );
    expect(screen.getByRole('button').getAttribute('aria-controls')).toBeNull();
  });

  it('요약이 없으면 요약 줄 자체를 안 그린다', () => {
    const { container } = render(
      <SectionCard plan={OPEN} className="card--floors" summary={null}>
        <p>본문입니다</p>
      </SectionCard>,
    );
    expect(container.querySelector('.card__summary')).toBeNull();
  });

  it('제목은 h3 안의 버튼 하나다 (목차에서 사라지지 않게)', () => {
    const { container } = render(
      <SectionCard plan={OPEN} className="card--floors" summary="층 3개">
        <p>본문입니다</p>
      </SectionCard>,
    );
    const h3 = container.querySelector('h3.card__h');
    expect(h3).toBeTruthy();
    expect(h3?.querySelector('button.card__toggle')).toBeTruthy();
  });

  it('화살표는 읽어 주는 기기에서 감춘다 (aria-expanded 와 겹쳐 읽히지 않게)', () => {
    const { container } = render(
      <SectionCard plan={OPEN} className="card--floors" summary="층 3개">
        <p>본문입니다</p>
      </SectionCard>,
    );
    expect(container.querySelector('.card__caret')?.getAttribute('aria-hidden')).toBe('true');
  });
});

describe('SectionCard — 밖에서 부르는 신호', () => {
  it('openSignal 이 바뀌면 접혀 있던 카드가 펼쳐진다', () => {
    function Host() {
      const [signal, setSignal] = useState(0);
      return (
        <>
          <button type="button" onClick={() => setSignal((n) => n + 1)}>
            밖에서 펼치기
          </button>
          <SectionCard plan={OPEN} className="card--floors" summary="층 3개" openSignal={signal}>
            <p>본문입니다</p>
          </SectionCard>
        </>
      );
    }
    render(<Host />);
    const card = screen.getByRole('button', { name: /층 목록/ });

    fireEvent.click(card); // 사용자가 접는다
    expect(screen.queryByText('본문입니다')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '밖에서 펼치기' }));
    expect(screen.getByText('본문입니다')).toBeTruthy();
    expect(card.getAttribute('aria-expanded')).toBe('true');
  });

  it('접고 펼칠 때마다 onToggle 로 알린다', () => {
    const seen: boolean[] = [];
    render(
      <SectionCard
        plan={OPEN}
        className="card--floors"
        summary="층 3개"
        onToggle={(v) => seen.push(v)}
      >
        <p>본문입니다</p>
      </SectionCard>,
    );
    expect(seen).toEqual([true]); // 처음 상태부터 알린다

    fireEvent.click(screen.getByRole('button'));
    expect(seen).toEqual([true, false]);

    fireEvent.click(screen.getByRole('button'));
    expect(seen).toEqual([true, false, true]);
  });
});
