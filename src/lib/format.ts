/** 화면 표시용 변환 모음. 계산은 하지 않고 보기 좋게만 바꾼다. */

const M2_PER_PYEONG = 3.305785;

/** 면적을 "520.3㎡ (157평)"으로. 값이 없으면 '—'. */
export function formatArea(m2: number | null | undefined): string {
  if (m2 === null || m2 === undefined || Number.isNaN(m2)) return '—';
  const pyeong = Math.round(m2 / M2_PER_PYEONG);
  return `${m2.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}㎡ (${pyeong.toLocaleString('ko-KR')}평)`;
}

/**
 * 층 번호를 사람이 읽는 표기로. DB 표기 규칙은 지상 n=n / 지하 n=-n / 옥탑=99이고
 * 0은 제약으로 존재하지 않는다(지하와 결측이 섞이는 것을 막기 위해).
 *
 * 원본 이름표(`floor_label`)가 있으면 그걸 우선한다 — 대장에 적힌 그대로가 제일 정확하다.
 */
export function formatFloor(floorNo: number, label: string | null): string {
  if (label && label.trim()) return label.trim();
  if (floorNo === 99) return '옥탑';
  if (floorNo < 0) return `지하 ${Math.abs(floorNo)}층`;
  return `${floorNo}층`;
}

/** 스택에서 층을 위→아래로 세울 때 쓰는 정렬 키. 옥탑이 제일 위, 지하가 제일 아래. */
export function floorSortKey(floorNo: number): number {
  return floorNo;
}

/** 사용승인일 '2003-05-14' → '2003년 5월'. 없으면 '—'. */
export function formatApproveDate(date: string | null): string {
  if (!date) return '—';
  const m = /^(\d{4})-(\d{2})/.exec(date);
  if (!m) return date;
  return `${m[1]}년 ${Number(m[2])}월`;
}
