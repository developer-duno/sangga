import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';

/**
 * 홈 화면에 두고 앱처럼 쓰기(👤 2026-10-19 결정 0039 W4b 3번 「가」) — 글은 결재 예시값 그대로(시험이 글자를 못 박는다).
 * ⚠️ 붙잡은 설치 이벤트는 `lib/installPrompt.ts` 모듈 안에 있다 — 시험마다 모듈을 새로 들여온다.
 */
// 꼬리말의 신선도 표가 서버를 부른다 — 이 시험의 관심사가 아니라 비운다(`AppFooter.test` 와 같은 꼴).
vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: () => Promise.resolve({ data: null, error: { code: 'PGRST202', message: 'none' } }),
  },
}));

async function load() {
  vi.resetModules();
  const hint = await import('./HomeScreenHint');
  const footer = await import('./AppFooter');
  return { HomeScreenHint: hint.HomeScreenHint, AppFooter: footer.AppFooter };
}

function fireInstall() {
  const ev = new Event('beforeinstallprompt', { cancelable: true }) as Event & { prompt: () => Promise<void> };
  const prompt = vi.fn(() => Promise.resolve());
  ev.prompt = prompt;
  act(() => {
    window.dispatchEvent(ev);
  });
  return prompt;
}

const IOS = '아이폰 Safari: 공유 단추 → 「홈 화면에 추가」';
const ANDROID = '안드로이드 크롬: 더보기(⋮) → 「설치 및 바로가기 만들기」';
const ANDROID_BTN = '안드로이드 크롬: 아래 단추를 누르거나 더보기(⋮) → 「설치 및 바로가기 만들기」';

afterEach(() => {
  cleanup();
  delete (window as { matchMedia?: unknown }).matchMedia;
});

describe('HomeScreenHint', () => {
  it('★ 제목·두 줄 글자 그대로 · 설치 이벤트 전엔 단추 0(안드로이드 줄은 단추 없는 글)', async () => {
    const { HomeScreenHint } = await load();
    render(<HomeScreenHint />);
    expect(screen.getByText('홈 화면에 두고 앱처럼 쓰기')).toBeTruthy();
    const items = [...document.querySelectorAll('.hshint__list li')].map((li) => li.textContent);
    expect(items).toEqual([IOS, ANDROID]);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('★ 크롬이 설치 이벤트를 주면 단추 「홈 화면에 추가」 + 안드로이드 줄이 단추 글로 · 누르면 prompt 1회 · 단추만 사라진다', async () => {
    const { HomeScreenHint } = await load();
    render(<HomeScreenHint />);
    const prompt = fireInstall();
    const btn = screen.getByRole('button', { name: '홈 화면에 추가' });
    expect(document.querySelectorAll('.hshint__list li')[1].textContent).toBe(ANDROID_BTN);
    fireEvent.click(btn);
    expect(prompt).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button')).toBeNull();
    // 결과에 따라 글을 바꾸지 않는다 — 단추 없는 글로 돌아갈 뿐.
    expect(document.querySelectorAll('.hshint__list li')[1].textContent).toBe(ANDROID);
    expect(screen.getByText(IOS)).toBeTruthy();
  });

  it('★ 이미 홈 화면에서 연 창(standalone)이면 DOM 0 · 양성 대조(아니면 선다)', async () => {
    const { HomeScreenHint } = await load();
    window.matchMedia = ((q: string) => ({ matches: q === '(display-mode: standalone)' })) as unknown as typeof window.matchMedia;
    const { container } = render(<HomeScreenHint />);
    expect(container.innerHTML).toBe('');
    cleanup();
    window.matchMedia = ((q: string) => ({ matches: q === 'print' })) as unknown as typeof window.matchMedia;
    const again = render(<HomeScreenHint />);
    expect(again.container.querySelector('.hshint')).not.toBeNull();
  });

  it('★ 꼬리말 — 휴대폰 차례(phoneOrder)에서만 · 역할 줄 다음 DOM 자리(안내 앞) · 넓은 화면은 DOM 0', async () => {
    const { AppFooter } = await load();
    const wide = render(<AppFooter />);
    expect(wide.container.querySelector('.hshint')).toBeNull();
    cleanup();
    const phone = render(<AppFooter phoneOrder lead={<div className="role">역할</div>} />);
    const kids = [...phone.container.querySelector('footer')!.children].map((k) => k.className.split(' ')[0]);
    expect(kids.slice(0, 3)).toEqual(['role', 'hshint', 'foot__notice']);
    expect(kids.at(-1)).toBe('fb');
  });
});
