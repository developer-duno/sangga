import type { ViewerRole } from './sectionCards';

/**
 * 휴대폰 아래 탭(결정 0039 Q1 · W4a). 폭 720px 이하 화면에서만 선다 — 넓은 화면은 탭이 없다(지금 화면 그대로).
 *
 * ⛔ 탭은 **주소를 바꾸지 않는다**(결정 0039 §4-1 · 0019 주소 꼴 고정) — 이 기기 저장·의견함에도 안 싣는다(화면 상태만).
 * ⓘ 중개사는 「지도」 자리가 「뽑은 건물」(👤 2026-10-17 W4a 「가」 · 결정 0036 ⑩ — 최근 뽑은 건물). 지도는 찾기 탭 안에서 그대로 본다.
 */
export type AppTab = 'find' | 'map' | 'building' | 'printed' | 'more';

export const TAB_LABEL: Record<AppTab, string> = {
  find: '찾기',
  map: '지도',
  building: '건물',
  printed: '뽑은 건물',
  more: '더보기',
};

/** 그 역할에게 서는 탭 넷(왼쪽부터). */
export function tabsFor(role: ViewerRole | null): readonly AppTab[] {
  return role === '중개사' ? ['find', 'building', 'printed', 'more'] : ['find', 'map', 'building', 'more'];
}

/**
 * 첫 그림의 탭 — 건물 직행 링크(`bld`)면 건물 · 창업자면 지도(결정 0036 ④ 「창업자 입구 = 지도 먼저」) · 나머지(역할 없음·
 * 둘러보기·투자자·중개사)는 찾기. ⛔ **첫 그림 한 번만** 쓴다 — 큰 카드에서 막 창업자를 골라도 탭은 그대로(메인 판단).
 */
export function firstTab(role: ViewerRole | null, openedWithBld: boolean): AppTab {
  if (openedWithBld) return 'building';
  return role === '창업자' ? 'map' : 'find';
}

/** 역할이 바뀌어 지금 탭이 그 역할의 탭 넷에 없으면(중개사로 바꿨는데 지도 · 중개사를 풀었는데 뽑은 건물) 찾기로. */
export function tabAfterRoleChange(tab: AppTab, role: ViewerRole | null): AppTab {
  return tabsFor(role).includes(tab) ? tab : 'find';
}

/** 빈 「건물」 탭(👤 2026-10-17 W4a 1번 「가」 — 시안 글자 그대로). */
export const EMPTY_BUILDING_TITLE = '아직 고른 건물이 없습니다';
export const EMPTY_BUILDING_BODY = '찾기나 지도에서 건물을 고르면 여기에 층별 화면이 섭니다';
export const EMPTY_BUILDING_GO = '건물 찾으러 가기';

/** 빈 「뽑은 건물」 탭 — 두 줄 문구는 👤 2026-10-17 저녁 W4a 4번 「가」로 승인된 문구(바뀌면 여기 한 곳만 고친다). */
export const EMPTY_PRINTED_TITLE = '아직 뽑은 건물이 없습니다';
export const EMPTY_PRINTED_BODY = '건물 화면에서 「인쇄 · PDF로 저장」을 누르면 여기에 남습니다';

/**
 * 뒤로가기 표식(👤 2026-10-17 「건물에서만 한 칸」). 건물을 열 때만 `history` 에 한 칸 — 그 칸이 `bld`, 열기 직전 칸이 `base`.
 * ⓘ 이미 `bld` 칸에 서 있으면 새로 쌓지 않는다(건물을 여럿 열어도 늘 한 칸).
 */
export const HISTORY_KEY = 'sanggaTab';
export type HistoryMark = 'base' | 'bld';

export function historyMarkOf(state: unknown): HistoryMark | null {
  if (typeof state !== 'object' || state === null) return null;
  const v = (state as Record<string, unknown>)[HISTORY_KEY];
  return v === 'base' || v === 'bld' ? v : null;
}
