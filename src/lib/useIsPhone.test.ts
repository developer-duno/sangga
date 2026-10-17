import { describe, it, expect, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { PHONE_QUERY, useIsPhone } from './useIsPhone';

/**
 * 흉내 `matchMedia` — 폭(휴대폰인가)과 인쇄 중인가 둘만 쥔다. 브라우저처럼 인쇄에 들어가면 screen 질의가 거짓이 되고
 * 듣는 쪽 전부에 change 를 보낸다.
 */
function fakeMedia(phone: boolean) {
  const st = { phone, printing: false };
  const listeners = new Set<() => void>();
  const matches = (q: string) => (q === 'print' ? st.printing : q === PHONE_QUERY ? st.phone && !st.printing : false);
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
    setPhone(v: boolean) {
      st.phone = v;
      fire();
    },
  };
}

afterEach(() => {
  delete (window as { matchMedia?: unknown }).matchMedia;
});

describe('useIsPhone — 휴대폰 꼴(결정 0039 W4a)', () => {
  it('matchMedia 가 없으면(jsdom) 넓은 화면', () => {
    delete (window as { matchMedia?: unknown }).matchMedia;
    expect(renderHook(() => useIsPhone()).result.current).toBe(false);
  });

  it('질의는 CSS 휴대폰 묶음과 같은 글자', () => {
    expect(PHONE_QUERY).toBe('screen and (max-width: 720px)');
  });

  it('폭이 바뀌면 따라간다', () => {
    const m = fakeMedia(false);
    const { result } = renderHook(() => useIsPhone());
    expect(result.current).toBe(false);
    m.setPhone(true);
    expect(result.current).toBe(true);
    m.setPhone(false);
    expect(result.current).toBe(false);
  });

  it('★ 인쇄 중에는 얼린다 — screen 질의가 거짓이 되어도 휴대폰 꼴 그대로 · 종이에서 돌아오면 다시 맞춘다', () => {
    const m = fakeMedia(true);
    const { result } = renderHook(() => useIsPhone());
    expect(result.current).toBe(true);
    m.setPrinting(true);
    expect(result.current).toBe(true);
    m.setPrinting(false);
    expect(result.current).toBe(true);
  });

  it('양성 대조 — 얼리지 않는 꼴(인쇄를 안 보는 훅)이면 인쇄 중 거짓이 된다(흉내가 실제로 바뀌는지)', () => {
    fakeMedia(true);
    const q = window.matchMedia(PHONE_QUERY);
    expect(q.matches).toBe(true);
    const m = fakeMedia(true);
    const q2 = window.matchMedia(PHONE_QUERY);
    m.setPrinting(true);
    expect(q2.matches).toBe(false);
  });
});
