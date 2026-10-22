/**
 * PC 두 칸 왼쪽 칸 목록의 주소를 길 이름부터 적는다(👤 2026-10-22 왼쪽 칸 다듬기 「가」 L2).
 *
 * 왼쪽 칸(약 400px)에서는 「대전광역시 서구 둔산북로 22」의 앞 「대전광역시 서구」가 자리를 다 먹어 길 이름이 잘린다.
 * 손님은 이미 그 구를 골라 두었으니(지역 한 줄 「대전 서구」) 앞부분은 같은 말의 되풀이다 → 「둔산북로 22」.
 * 지번도 같다 — 「대전광역시 서구 둔산동 1451」 → 「둔산동 1451」(화면 글 「지번 」은 부르는 쪽이 붙인다).
 *
 * ⛔ 고른 시·구로 **시작할 때만** 뺀다 — 상권이 구 경계를 넘어 걸쳐 다른 구의 땅이 목록에 들 수 있다. 다른 구(같은 이름의
 *    다른 시 「인천광역시 서구」 포함) 주소는 그대로 둔다(빼면 어느 구인지 잃는다).
 * ⓘ 구가 없는 시(세종특별자치시 — 시·도 이름과 시군구 이름이 같다)는 시 이름 한 덩어리만 뺀다.
 * ⓘ 빼고 나서 남는 글이 없으면 원래 주소 그대로(빈 줄을 그리지 않는다).
 */
export type AddrArea = {
  /** 시·도 정식 이름(예: `대전광역시` — `regions.ts` 의 `fullName`). */
  sido: string;
  /** 고른 시군구 이름(예: `서구` · 세종은 `세종특별자치시`). */
  sigungu: string;
};

function esc(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** 낱말 사이 띄어쓰기가 한 칸이 아니어도 맞게(`수원시 장안구` 처럼 이름 안 띄어쓰기 포함). */
function words(s: string): string {
  return s.trim().split(/\s+/).map(esc).join('\\s+');
}

export function shortAddr(addr: string, area: AddrArea | null | undefined): string {
  if (!area || !area.sido.trim() || !area.sigungu.trim()) return addr;
  const head =
    area.sido.trim() === area.sigungu.trim()
      ? `^\\s*${words(area.sido)}\\s+`
      : `^\\s*${words(area.sido)}\\s+${words(area.sigungu)}\\s+`;
  const rest = addr.replace(new RegExp(head), '');
  return rest.trim() === '' ? addr : rest;
}
