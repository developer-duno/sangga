import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { useState } from 'react';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { SectionCard } from './SectionCard';
import { DataFreshness } from './DataFreshness';
import { resetDataFreshnessCache } from '../lib/loadDataFreshness';
import { SECTION_PLAN, type SectionPlan } from '../lib/sectionCards';
import type { DataFreshnessRow } from '../types';

/**
 * 카드 머리 날짜 줄(S3)이 신선도 표를 묻는다 — 서버 대신 이 답을 준다.
 * ⓘ 표와 카드가 나눠 쓰는 한 번의 요청(`loadDataFreshness`)을 시험마다 비운다(아래 beforeEach).
 */
const fresh = vi.hoisted(() => ({
  response: { data: null as unknown, error: null as unknown },
  calls: [] as string[],
}));

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string) => {
      fresh.calls.push(fn);
      return Promise.resolve(fresh.response);
    },
  },
}));

/** 2026-10-16 운영 값(기준값만). */
function freshRows(): DataFreshnessRow[] {
  const r = (src: string, basis_kind: string, basis: string): DataFreshnessRow => ({
    src,
    basis_kind,
    basis,
    next_expected: null,
    cadence: '-',
  });
  return [
    r('점포·업종 (상권정보)', '분기', '202606'),
    r('실거래 (매매)', '계약월', '202610'),
    r('건축물대장', '판', '202608'),
    r('상권 경계', '계산일', '2026-09-08'),
    r('국세청 기준시가', '고시일', '2026-01-01'),
  ];
}

beforeEach(() => {
  resetDataFreshnessCache();
  fresh.calls.length = 0;
  fresh.response = { data: freshRows(), error: null };
});

/**
 * 공통 카드 틀 — 로드맵 Wave 2 『한 장 요약 접힘 틀』.
 *
 * 여기서 지키는 것은 넷이다:
 *   ① 기본 펼침/접힘이 배치표(`SECTION_PLAN`)가 시킨 대로 나온다
 *   ② 눌러서 접고 펼칠 수 있고, 그 상태를 읽어 주는 기기도 안다(`aria-expanded`)
 *   ③ **접혀 있어도 제목과 핵심 한 줄은 보인다** — 접힘이 숨김이 되면 안 된다
 *   ④ **접힌 본문은 자리에 남는다** — 감출 뿐 지우지 않는다(결정 0020)
 *
 * ⚠️ ④ 때문에 "DOM 에 없다"로 접힘을 확인하면 안 된다. 그건 이제 거짓이고, 사용자가 실제로
 *    겪는 것은 **"안 보인다"**다. 종이로 뽑을 때 인쇄 규칙이 되살려야 하므로 본문은 남는다 —
 *    그렇게 안 하면 접힌 카드가 종이에서 통째로 빠진다(2026-08-25 실측).
 */

/** 접힌 본문 — **자리에는 있고 안 보인다.** `hidden` 은 읽어 주는 기기에서도 감춘다. */
function bodyOf(container: HTMLElement) {
  return container.querySelector('.card__body');
}

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

  it('defaultOpen 이 거짓이면 본문을 감춘다 — 지우지는 않는다 (종이로 뽑을 때 되살린다)', () => {
    const { container } = render(
      <SectionCard plan={CLOSED} className="band" summary="값을 낸 층 2개">
        <p>본문입니다</p>
      </SectionCard>,
    );
    // 자리에는 있다 — 인쇄 규칙(CSS)은 화면에 아예 없는 것을 되살릴 수 없기 때문이다.
    expect(bodyOf(container)?.textContent).toBe('본문입니다');
    // 그러나 사용자에게는 안 보인다 — `hidden` 은 읽어 주는 기기에서도 감춘다.
    expect(bodyOf(container)?.hasAttribute('hidden')).toBe(true);
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
    const { container } = render(
      <SectionCard plan={CLOSED} className="band" summary="값을 낸 층 2개">
        <p>본문입니다</p>
      </SectionCard>,
    );
    const toggle = screen.getByRole('button');

    fireEvent.click(toggle);
    expect(bodyOf(container)?.hasAttribute('hidden')).toBe(false);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');

    fireEvent.click(toggle);
    expect(bodyOf(container)?.hasAttribute('hidden')).toBe(true);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
  });

  it('접으면 요약은 남고 본문만 감춰진다', () => {
    const { container } = render(
      <SectionCard plan={OPEN} className="card--floors" summary="층 3개 · 점포 12곳">
        <p>본문입니다</p>
      </SectionCard>,
    );
    fireEvent.click(screen.getByRole('button'));
    expect(bodyOf(container)?.hasAttribute('hidden')).toBe(true);
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
    expect(bodyOf(container)?.id).toBe(controls);
  });

  it('접혀 있어도 본문을 가리킨다 — 본문이 자리에 있으므로 (아코디언 표준형)', () => {
    const { container } = render(
      <SectionCard plan={CLOSED} className="band" summary="값을 낸 층 2개">
        <p>본문입니다</p>
      </SectionCard>,
    );
    const controls = screen.getByRole('button').getAttribute('aria-controls');
    expect(controls).toBeTruthy();
    expect(bodyOf(container)?.id).toBe(controls);
    // 가리키기는 하되 감춰져 있다 — 읽어 주는 기기는 `hidden` 때문에 안 읽는다.
    expect(bodyOf(container)?.hasAttribute('hidden')).toBe(true);
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
    const { container } = render(<Host />);
    const card = screen.getByRole('button', { name: /층 목록/ });

    fireEvent.click(card); // 사용자가 접는다
    expect(bodyOf(container)?.hasAttribute('hidden')).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: '밖에서 펼치기' }));
    expect(bodyOf(container)?.hasAttribute('hidden')).toBe(false);
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

describe('SectionCard — 역할을 바꿀 때 (결정 0036 결정 18)', () => {
  /*
    역할을 바꾸면 카드 표가 **다른 객체**로 온다 — 그때 펼침이 새 표대로 다시 선다.
    같은 객체로 다시 그려지면(자료가 와서 다시 그릴 때) 사람이 고른 펼침이 그대로여야 한다.
  */
  it('★ 다른 표가 오면 사람이 바꾼 펼침도 새 표대로 다시 선다', () => {
    const { rerender } = render(
      <SectionCard plan={CLOSED} className="band" summary="요약">
        <p>본문입니다</p>
      </SectionCard>,
    );
    const btn = () => screen.getByRole('button');
    fireEvent.click(btn()); // 사람이 펼친다
    expect(btn().getAttribute('aria-expanded')).toBe('true');

    // 다른 역할의 표 — 이 카드는 접힘. 사람이 펼쳐 둔 것도 새 표대로 접힌다.
    rerender(
      <SectionCard plan={{ ...CLOSED }} className="band" summary="요약">
        <p>본문입니다</p>
      </SectionCard>,
    );
    expect(btn().getAttribute('aria-expanded')).toBe('false');

    // 또 다른 표 — 이번엔 펼침.
    rerender(
      <SectionCard plan={{ ...CLOSED, defaultOpen: true }} className="band" summary="요약">
        <p>본문입니다</p>
      </SectionCard>,
    );
    expect(btn().getAttribute('aria-expanded')).toBe('true');
  });

  it('같은 표로 다시 그려지면 사람이 바꾼 펼침이 그대로다', () => {
    const { rerender } = render(
      <SectionCard plan={CLOSED} className="band" summary="요약">
        <p>본문입니다</p>
      </SectionCard>,
    );
    fireEvent.click(screen.getByRole('button'));
    rerender(
      <SectionCard plan={CLOSED} className="band" summary="새 요약">
        <p>본문입니다</p>
      </SectionCard>,
    );
    expect(screen.getByRole('button').getAttribute('aria-expanded')).toBe('true');
  });
});

describe('SectionCard — 제목 아래 날짜 줄 (S3 · 👤 2026-10-16)', () => {
  it('자료 칸이 있으면 제목 **바로 아래**에 \'자료: 이름 날짜\' 한 줄 — 접혀 있어도 보인다', async () => {
    const { container } = render(
      <SectionCard plan={SECTION_PLAN.floorgap} className="gap" summary="요약 한 줄">
        <p>본문</p>
      </SectionCard>,
    );
    const line = await waitFor(() => {
      const el = container.querySelector('.card__src');
      expect(el).not.toBeNull();
      return el!;
    });
    expect(line.textContent).toBe(
      // 부동산원 줄은 이 표본 표에 없어 그 조각만 빠진다(아래 시험과 같은 규칙).
      '자료: 국세청 기준시가 2026년 1월 1일 고시 · 국토부 실거래 2026년 10월 계약분까지 (최근 두 달은 신고 중)',
    );
    // 자리 — 제목(h3) 바로 다음, 요약 줄 앞.
    expect(line.previousElementSibling?.tagName).toBe('H3');
    expect(line.nextElementSibling?.className).toBe('card__summary');
    // 접힌 카드(층별 공표값은 처음 접힘)에서도 숨지 않는다 — 본문 칸 밖이다.
    expect(screen.getByRole('button').getAttribute('aria-expanded')).toBe('false');
    expect(line.closest('[hidden]')).toBeNull();
  });

  it('⛔ 빈 카드(자료 칸 없음)에는 줄이 없고 묻지도 않는다 — 양성 대조: 같은 자리에 자료 칸을 주면 줄이 선다', async () => {
    // ⓘ 빈 카드 = 가게 이력(결정 0045 PR③ 부터 sales·pop 칸에는 서울 카드용 자료 칸이 있다 — 빈 카드는 EmptySection 이 뺀다).
    const { container, unmount } = render(
      <SectionCard plan={SECTION_PLAN.history} className="card--empty" summary="비어 있음" />,
    );
    // 다른 카드가 물었다면 답이 왔을 시간을 준다.
    await new Promise((r) => setTimeout(r, 0));
    expect(container.querySelector('.card__src')).toBeNull();
    expect(fresh.calls).toEqual([]);
    unmount();

    const withSrc = { ...SECTION_PLAN.history, sources: ['tx'] } as const satisfies SectionPlan;
    const again = render(<SectionCard plan={withSrc} className="card--empty" summary="비어 있음" />);
    await waitFor(() => expect(again.container.querySelector('.card__src')).not.toBeNull());
  });

  it('⛔ 신선도 요청이 실패하면 날짜 줄만 없다 — 카드는 그대로', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    fresh.response = { data: null, error: { code: 'PGRST202', message: 'function does not exist' } };
    const { container } = render(
      <SectionCard plan={SECTION_PLAN.floors} className="card--floors" summary="층 3개">
        <p>본문입니다</p>
      </SectionCard>,
    );
    await waitFor(() => expect(warn).toHaveBeenCalled());
    expect(container.querySelector('.card__src')).toBeNull();
    expect(screen.getByText('층 3개')).toBeTruthy();
    expect(screen.getByText('본문입니다')).toBeTruthy();
    warn.mockRestore();
  });

  it('⛔ 그 자료 줄이 서버 표에 없으면 그 조각만 빠진다(부동산원 줄 없음 → 임대 동향 카드는 줄 없음)', async () => {
    const { container } = render(
      <>
        <SectionCard plan={SECTION_PLAN.rent} className="rent" summary="상권 1곳" />
        <SectionCard plan={SECTION_PLAN.floors} className="card--floors" summary="층 3개" />
      </>,
    );
    // 층 목록 카드는 줄이 선다(같은 표를 받았다는 양성 대조).
    await waitFor(() => expect(container.querySelectorAll('.card__src')).toHaveLength(1));
    expect(container.querySelector('.card--floors .card__src')?.textContent).toBe(
      '자료: 건축물대장 2026년 8월 판 · 상권정보 2026년 2분기 · 국토부 실거래 2026년 10월 계약분까지 (최근 두 달은 신고 중)',
    );
    expect(container.querySelector('.rent .card__src')).toBeNull();
  });

  it('⛔ 카드 여러 장과 맨 아래 표가 **같은 한 번의 요청**을 나눠 쓴다', async () => {
    const { container } = render(
      <>
        <SectionCard plan={SECTION_PLAN.district} className="card--district" summary="a" />
        <SectionCard plan={SECTION_PLAN.floors} className="card--floors" summary="b" />
        <SectionCard plan={SECTION_PLAN.tx} className="tx" summary="c" />
        <DataFreshness today="2026-10-16" />
      </>,
    );
    await waitFor(() => expect(container.querySelectorAll('.card__src')).toHaveLength(3));
    expect(await screen.findByText('이 자료는 언제 것인가')).toBeTruthy();
    expect(fresh.calls).toEqual(['get_data_freshness']);
  });
});

/**
 * styles.css 에서 `@media screen { … }` 묶음들의 **안쪽 글**만 모은다(중괄호 짝을 세어 묶음 끝을 찾는다).
 * ⓘ jsdom 은 CSS 를 적용하지 않으므로 규칙 자체를 본다(`DistrictMap.test` 와 같은 수법 — `?raw` 는 빈 글이 온다).
 * 못 보는 것: 주석 안의 중괄호(지금 styles.css 의 screen 묶음 주석에는 없다) · `@media screen and (…)` 꼴.
 */
function screenBlocks(css: string): string[] {
  const out: string[] = [];
  let at = css.indexOf('@media screen {');
  while (at >= 0) {
    const open = css.indexOf('{', at);
    let depth = 0;
    let i = open;
    for (; i < css.length; i += 1) {
      if (css[i] === '{') depth += 1;
      else if (css[i] === '}') {
        depth -= 1;
        if (depth === 0) break;
      }
    }
    out.push(css.slice(open + 1, i));
    at = css.indexOf('@media screen {', i);
  }
  return out;
}

/** 묶음 글에서 `font-size: 13px` 규칙의 고르개 목록(이름들). */
function screen13pxSelectors(css: string): string[] {
  const names: string[] = [];
  for (const block of screenBlocks(css)) {
    for (const m of block.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      if (/font-size:\s*13px/.test(m[2])) names.push(...m[1].split(',').map((x) => x.trim()));
    }
  }
  return names;
}

describe('날짜 줄 글자 13px 은 화면에서만 (S3 · ⛔ 종이 글자는 그대로)', () => {
  it('양성 대조 — 묶음 안 규칙은 잡고, 묶음 밖 같은 규칙은 안 잡는다', () => {
    const sample = [
      '.x { font-size: 13px; }',
      '@media screen {',
      '  .a,',
      '  .b { font-size: 13px; }',
      '  .c { min-height: 44px; }',
      '}',
      '@media print { .d { font-size: 13px; } }',
    ].join('\n');
    expect(screen13pxSelectors(sample)).toEqual(['.a', '.b']);
  });

  it('`.card__src` 는 화면 13px 묶음에 있고, 기본 규칙은 13px 이 아니다', async () => {
    const { readFileSync } = await import('node:fs');
    const css = readFileSync('src/styles.css', 'utf8');
    const names = screen13pxSelectors(css);
    expect(names).toContain('.card__note'); // 기존 칸 — 묶음을 제대로 읽었다는 표시
    expect(names).toContain('.card__src');
    const base = css.slice(css.indexOf('.card__src {'));
    const rule = base.slice(0, base.indexOf('}'));
    expect(rule).toMatch(/font-size:\s*12px/);
    expect(rule).not.toMatch(/font-size:\s*13px/);
    // 휴대폰 폭에서 낱말 가운데서 끊기지 않게('부동/산원') — 화면·종이 공통 규칙에(C2 · 2026-10-16).
    expect(rule).toMatch(/word-break:\s*keep-all/);
  });
});
