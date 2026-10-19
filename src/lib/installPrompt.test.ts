import { describe, it, expect, vi, afterEach } from 'vitest';

/**
 * 홈 화면 추가 이벤트 붙잡기(결정 0039 W4b · `lib/installPrompt.ts`).
 * ⚠️ 모듈이 들여와지는 순간 듣기 시작하고 붙잡은 이벤트를 모듈 안에 둔다 — 시험마다 새로 들여온다.
 */
async function fresh() {
  vi.resetModules();
  return import('./installPrompt');
}

function fakeEvent() {
  const ev = new Event('beforeinstallprompt', { cancelable: true }) as Event & { prompt: () => Promise<void> };
  ev.prompt = vi.fn(() => Promise.resolve());
  return ev;
}

afterEach(() => {
  delete (window as { matchMedia?: unknown }).matchMedia;
  delete (navigator as { standalone?: unknown }).standalone;
});

describe('installPrompt — 붙잡기', () => {
  it('들여오자마자 이벤트를 붙잡고 브라우저 기본 띠를 막는다(preventDefault)', async () => {
    await fresh();
    const ev = fakeEvent();
    window.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(true);
  });
});

describe('isStandalone — 이미 홈 화면에서 연 창인가', () => {
  it('matchMedia 가 없으면(jsdom·옛 브라우저) 거짓', async () => {
    const { isStandalone } = await fresh();
    expect(isStandalone()).toBe(false);
  });

  it('display-mode: standalone 이 참이면 참 · 다른 질의만 참이면 거짓(양성/음성)', async () => {
    const { isStandalone } = await fresh();
    window.matchMedia = ((q: string) => ({ matches: q === '(display-mode: standalone)' })) as unknown as typeof window.matchMedia;
    expect(isStandalone()).toBe(true);
    window.matchMedia = ((q: string) => ({ matches: q === 'print' })) as unknown as typeof window.matchMedia;
    expect(isStandalone()).toBe(false);
  });

  it('아이폰 옛 사파리 navigator.standalone 이 참이면 참', async () => {
    const { isStandalone } = await fresh();
    Object.defineProperty(navigator, 'standalone', { value: true, configurable: true });
    expect(isStandalone()).toBe(true);
  });

  it('matchMedia 가 던져도 죽지 않는다', async () => {
    const { isStandalone } = await fresh();
    window.matchMedia = (() => {
      throw new Error('막힘');
    }) as unknown as typeof window.matchMedia;
    expect(isStandalone()).toBe(false);
  });
});
