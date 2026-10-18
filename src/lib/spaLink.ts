import type { MouseEvent } from 'react';

/**
 * 진짜 `<a href>` 를 화면 안에서 처리해도 되는 누름인가(결정 0042 — 내부 링크).
 *
 * 검색 봇은 `href` 를 따라가고, 사람의 **보통 왼쪽 누름**만 화면이 가로채(`preventDefault`) 지금처럼 SPA 로 처리한다.
 * Ctrl·Cmd·Shift·Alt 누름(새 탭·새 창)과 가운데 누름은 그대로 링크로 둔다(브라우저 몫).
 */
export function isPlainLeftClick(e: MouseEvent<HTMLElement>): boolean {
  return !e.defaultPrevented && e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey;
}
