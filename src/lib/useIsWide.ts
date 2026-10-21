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
    const pm = window.matchMedia('print');
    const sync = () => {
      if (pm.matches) return;
      setWide(mq.matches);
    };
    sync();
    mq.addEventListener('change', sync);
    /*
      종이에서 돌아올 때도 다시 맞춘다(W5 보완 · E2E BW 병렬 실측) — 인쇄를 마치자마자 창 폭도 1023 이하로 바뀌면 브라우저가 둘을 한 번에
      평가해 두 칸 질의 값이 '거짓(인쇄) → 거짓(좁음)'이라 change 가 안 온다 → 인쇄 중 얼려 둔 '두 칸'이 남는다. 인쇄 질의의 change 로 메운다.
    */
    pm.addEventListener('change', sync);
    return () => {
      mq.removeEventListener('change', sync);
      pm.removeEventListener('change', sync);
    };
  }, []);
  return wide;
}
