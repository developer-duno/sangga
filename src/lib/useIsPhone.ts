import { useEffect, useState } from 'react';

/**
 * 휴대폰 꼴(아래 탭 · 결정 0039 W4a)인가 — CSS 의 `@media screen and (max-width: 720px)` 묶음과 **같은 질의**.
 *
 * ⛔ **인쇄하는 동안은 값을 얼린다.** 크롬·사파리는 인쇄에 들어갈 때 screen 질의가 거짓이 되어 change 가 오고(playwright 의
 *    `emulateMedia('print')` 도 같다), 그대로 따르면 종이를 그리는 도중에 넓은 꼴로 다시 그리려 든다 — 그래서 change 가 왔을 때
 *    `print` 질의가 참이면 무시한다(종이에서 돌아오면 다시 맞춘다).
 * ⓘ `matchMedia` 가 없는 곳(jsdom 시험)은 넓은 화면 — 기존 시험은 전부 지금 경로 그대로 돈다.
 */
export const PHONE_QUERY = 'screen and (max-width: 720px)';

function hasMatchMedia(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function';
}

export function useIsPhone(): boolean {
  const [phone, setPhone] = useState(() => hasMatchMedia() && window.matchMedia(PHONE_QUERY).matches);
  useEffect(() => {
    if (!hasMatchMedia()) return;
    const mq = window.matchMedia(PHONE_QUERY);
    const sync = () => {
      if (window.matchMedia('print').matches) return;
      setPhone(mq.matches);
    };
    sync();
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, []);
  return phone;
}
