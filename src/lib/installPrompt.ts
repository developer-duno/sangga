import { useEffect, useState } from 'react';

/**
 * 홈 화면 추가(👤 2026-10-19 W4b 3번 「가」) — 안드로이드 크롬이 주는 설치 창 이벤트(`beforeinstallprompt`)를 붙잡아 둔다.
 *
 * ⓘ 이 이벤트는 크롬 계열에만 있다(MDN — 사파리·파이어폭스 없음). 그리기 **전에** 올 수 있어서(MDN) 이 모듈은 `main.tsx` 가
 *   가장 먼저 들여오고, 들여오는 순간 듣기 시작한다. `preventDefault()` 로 브라우저 기본 띠를 막고 이벤트를 보관한다 —
 *   「홈 화면에 추가」 단추를 누를 때 `prompt()` 로 그 창을 띄운다(한 이벤트는 한 번만 쓸 수 있어 쓰면 비운다).
 * ⛔ 설치 팝업을 우리가 먼저 띄우지 않는다(결정 0039 §8) — 단추를 눌렀을 때만.
 */
export type InstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice?: Promise<{ outcome: 'accepted' | 'dismissed' }>;
};

let held: InstallPromptEvent | null = null;
const listeners = new Set<() => void>();

function notify() {
  for (const l of listeners) l();
}

function onBefore(e: Event) {
  e.preventDefault();
  held = e as InstallPromptEvent;
  notify();
}

function onInstalled() {
  held = null;
  notify();
}

if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', onBefore);
  window.addEventListener('appinstalled', onInstalled);
}

/** 붙잡아 둔 설치 창 이벤트(없으면 null)와 그것을 띄우는 함수. 띄운 뒤엔 비운다(결과에 따라 글을 바꾸지 않는다 — 단추만 사라진다). */
export function useInstallPrompt(): { canInstall: boolean; install: () => void } {
  const [, setTick] = useState(0);
  useEffect(() => {
    const l = () => setTick((n) => n + 1);
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  }, []);
  return {
    canInstall: held !== null,
    install: () => {
      const ev = held;
      if (ev === null) return;
      held = null;
      notify();
      // 사람이 창을 닫거나 브라우저가 거절해도 화면에는 아무 일 없다(단추만 사라진 그대로).
      ev.prompt().catch(() => {});
    },
  };
}

/**
 * 이미 홈 화면에서 연 창인가 — `display-mode: standalone`(MDN · 널리 지원) 또는 아이폰 옛 사파리의 `navigator.standalone`.
 * ⓘ 둘 다 없는 곳(jsdom 시험·옛 브라우저)은 거짓 — 안내가 선다.
 */
export function isStandalone(): boolean {
  try {
    if (typeof window.matchMedia === 'function' && window.matchMedia('(display-mode: standalone)').matches) return true;
  } catch {
    // 질의를 못 하는 곳은 아니라고 본다.
  }
  try {
    return (navigator as Navigator & { standalone?: boolean }).standalone === true;
  } catch {
    return false;
  }
}
