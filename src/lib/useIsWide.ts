import { useEffect, useState } from 'react';

/**
 * PC 두 칸 꼴(왼쪽 찾기 / 오른쪽 건물 · 결정 0039 Q5 · W5 · §4-13)인가 — CSS 의 `@media screen and (min-width: 1024px)` 묶음과
 * **같은 질의**. 721~1023 은 지금 한 열(S1 입구 접기) · 720 이하는 휴대폰 탭(`useIsPhone`) — 세 꼴은 겹치지 않는다.
 *
 * ⛔ **인쇄하는 동안은 값을 얼린다**(`useIsPhone` 과 같은 까닭) — 인쇄에 들어가면 screen 질의가 거짓이 되어 change 가 오는데,
 *    그대로 따르면 종이를 그리는 도중에 한 열 꼴(입구 접힘·지도 언마운트)로 다시 그리려 든다. 종이는 `.app--wide` 이름표로 가른다.
 * ⓘ `matchMedia` 가 없는 곳(jsdom 시험)은 두 칸이 아니다 — 기존 시험은 전부 지금 경로(한 열) 그대로 돈다.
 */
export const WIDE_QUERY = 'screen and (min-width: 1024px)';

function hasMatchMedia(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function';
}

export function useIsWide(): boolean {
  const [wide, setWide] = useState(() => hasMatchMedia() && window.matchMedia(WIDE_QUERY).matches);
  useEffect(() => {
    if (!hasMatchMedia()) return;
    const mq = window.matchMedia(WIDE_QUERY);
    const sync = () => {
      if (window.matchMedia('print').matches) return;
      setWide(mq.matches);
    };
    sync();
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, []);
  return wide;
}
