import { describe, it, expect, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { WIDE_QUERY, useIsWide } from './useIsWide';
import { PHONE_QUERY } from './useIsPhone';

/**
 * 흉내 `matchMedia` — 창 폭(px)과 인쇄 중인가 둘만 쥔다. 질의 글자를 그대로 풀어(min/max-width) 폭과 맞춘다 — 그래서 두 칸·휴대폰
 * 질의를 같은 폭으로 동시에 물어볼 수 있다. 브라우저처럼 인쇄에 들어가면 screen 질의가 거짓이 되고 듣는 쪽 전부에 change 를 보낸다.
 */
function fakeMedia(width: number) {
  const st = { width, printing: false };
  const listeners = new Set<() => void>();
  const matches = (q: string) => {
    if (q === 'print') return st.printing;
    if (st.printing) return false;
    const min = /min-width:\s*(\d+)px/.exec(q);
    const max = /max-width:\s*(\d+)px/.exec(q);
    return (!min || st.width >= Number(min[1])) && (!max || st.width <= Number(max[1]));
  };
  window.matchMedia = ((q: string) => ({
    media: q,
    get matches() {
      return matches(q);
    },
    addEventListener: (_t: string, cb: () => void) => listeners.add(cb),
    removeEventListener: (_t: string, cb: () => void) => listeners.delete(cb),
  })) as unknown as typeof window.matchMedia;
  const fire = () => act(() => listeners.forEach((cb) => cb()));
  return {
    setPrinting(v: boolean) {
      st.printing = v;
      fire();
    },
    setWidth(v: number) {
      st.width = v;
      fire();
    },
  };
}

afterEach(() => {
  delete (window as { matchMedia?: unknown }).matchMedia;
});

describe('useIsWide — PC 두 칸 꼴(결정 0039 W5)', () => {
  it('matchMedia 가 없으면(jsdom) 두 칸이 아니다 — 기존 시험은 한 열 그대로', () => {
    delete (window as { matchMedia?: unknown }).matchMedia;
    expect(renderHook(() => useIsWide()).result.current).toBe(false);
  });

  it('질의는 CSS 두 칸 묶음과 같은 글자', () => {
    expect(WIDE_QUERY).toBe('screen and (min-width: 1024px)');
  });

  it('★ 경계 — 1024 두 칸 · 1023 한 열 · 폭이 바뀌면 따라간다', () => {
    const m = fakeMedia(1024);
    const { result } = renderHook(() => useIsWide());
    expect(result.current).toBe(true);
    m.setWidth(1023);
    expect(result.current).toBe(false);
    m.setWidth(1280);
    expect(result.current).toBe(true);
  });

  it('★ 두 칸과 휴대폰은 동시에 참일 수 없다 — 300~1600px 전부(질의 글자로)', () => {
    for (let w = 300; w <= 1600; w += 1) {
      fakeMedia(w);
      const wide = window.matchMedia(WIDE_QUERY).matches;
      const phone = window.matchMedia(PHONE_QUERY).matches;
      expect(wide && phone, `${w}px`).toBe(false);
    }
    // 양성 대조 — 흉내가 실제로 두 질의를 가른다(한쪽만 늘 거짓이면 위 단언이 헛돈다).
    fakeMedia(1024);
    expect(window.matchMedia(WIDE_QUERY).matches).toBe(true);
    fakeMedia(720);
    expect(window.matchMedia(PHONE_QUERY).matches).toBe(true);
  });

  it('★ 인쇄 중에는 얼린다 — screen 질의가 거짓이 되어도 두 칸 그대로 · 종이에서 돌아오면 다시 맞춘다', () => {
    const m = fakeMedia(1280);
    const { result } = renderHook(() => useIsWide());
    expect(result.current).toBe(true);
    m.setPrinting(true);
    expect(window.matchMedia(WIDE_QUERY).matches).toBe(false); // 양성 대조 — 흉내는 실제로 거짓이 된다
    expect(result.current).toBe(true);
    m.setPrinting(false);
    expect(result.current).toBe(true);
  });
});

/**
 * 브라우저에 더 가까운 흉내 — 질의마다 듣는 쪽을 따로 쥐고, 한 번에 바꾼 뒤 **값이 바뀐 질의에만** change 를 보낸다
 * (인쇄를 마치는 것과 폭이 줄어드는 것이 한 번에 평가되면 두 칸 질의는 '거짓 → 거짓'이라 change 가 안 온다).
 */
function coalescingMedia(width: number) {
  const st = { width, printing: false };
  const listeners = new Map<string, Set<() => void>>();
  const value = (q: string) => {
    if (q === 'print') return st.printing;
    if (st.printing) return false;
    const min = /min-width:\s*(\d+)px/.exec(q);
    const max = /max-width:\s*(\d+)px/.exec(q);
    return (!min || st.width >= Number(min[1])) && (!max || st.width <= Number(max[1]));
  };
  window.matchMedia = ((q: string) => ({
    media: q,
    get matches() {
      return value(q);
    },
    addEventListener: (_t: string, cb: () => void) => {
      if (!listeners.has(q)) listeners.set(q, new Set());
      listeners.get(q)!.add(cb);
    },
    removeEventListener: (_t: string, cb: () => void) => listeners.get(q)?.delete(cb),
  })) as unknown as typeof window.matchMedia;
  return {
    /** 바꿀 것을 한 번에 적용하고 값이 바뀐 질의에만 알린다. 알림을 받은 질의 글자를 돌려준다. */
    apply(next: { width?: number; printing?: boolean }) {
      const before = new Map([...listeners.keys()].map((q) => [q, value(q)]));
      Object.assign(st, next);
      const fired: string[] = [];
      act(() => {
        for (const [q, cbs] of listeners) {
          if (before.get(q) === value(q)) continue;
          fired.push(q);
          cbs.forEach((cb) => cb());
        }
      });
      return fired;
    },
  };
}

describe('useIsWide — 종이에서 돌아오며 폭도 바뀔 때(W5 보완)', () => {
  it('★ 인쇄를 마치는 것과 1023 으로 줄어드는 것이 한 번에 와도(두 칸 질의 change 없음) 한 열로 맞춘다', () => {
    const m = coalescingMedia(1280);
    const { result } = renderHook(() => useIsWide());
    expect(result.current).toBe(true);
    m.apply({ printing: true });
    expect(result.current).toBe(true); // 인쇄 중엔 얼림
    const fired = m.apply({ printing: false, width: 1023 });
    // 양성 대조 — 흉내는 실제로 두 칸 질의엔 알리지 않고 인쇄 질의에만 알렸다(그래서 인쇄 질의를 안 들으면 '두 칸'이 남는다).
    expect(fired).toEqual(['print']);
    expect(result.current).toBe(false);
  });

  it('인쇄를 마치고 폭이 그대로면 두 칸 그대로', () => {
    const m = coalescingMedia(1280);
    const { result } = renderHook(() => useIsWide());
    m.apply({ printing: true });
    m.apply({ printing: false });
    expect(result.current).toBe(true);
  });
});
