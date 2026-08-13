/** 화면 표시용 변환 모음. 계산은 하지 않고 보기 좋게만 바꾼다. */

import type { BuildingHit } from '../types';

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

/**
 * 분기 스냅샷 키 '202603' → '2026년 1분기'.
 *
 * 상권정보는 분기말 기준으로 배포된다(3·6·9·12월). 형식이 다르면 억지로 해석하지 않고
 * 원본을 그대로 보여준다 — 틀린 분기를 말하는 것보다 낫다.
 */
export function formatQuarter(ym: string | null | undefined): string {
  if (!ym) return '—';
  const s = ym.trim();
  const m = /^(\d{4})(\d{2})$/.exec(s);
  if (!m) return s;
  const month = Number(m[2]);
  if (month < 1 || month > 12) return s;
  return `${m[1]}년 ${Math.ceil(month / 3)}분기`;
}

/**
 * 비율(%)을 "N곳 중 1곳"의 N으로. 32.9 → 3.
 *
 * 비율이 0 이하이거나 숫자가 아니면 null을 준다 — 그 경우 화면은 "N곳 중 1곳" 문구
 * 자체를 만들지 않는다(1/0으로 만든 무한대를 화면에 내보내지 않기 위해).
 */
export function oneInEvery(pct: number | null | undefined): number | null {
  if (pct === null || pct === undefined || !Number.isFinite(pct) || pct <= 0) return null;
  return Math.round(100 / pct);
}

/** 사용승인일 '2003-05-14' → '2003년 5월'. 없으면 '—'. */
export function formatApproveDate(date: string | null): string {
  if (!date) return '—';
  const m = /^(\d{4})-(\d{2})/.exec(date);
  if (!m) return date;
  return `${m[1]}년 ${Number(m[2])}월`;
}

/**
 * 서버 오류 원문 대신 사람이 읽을 문구로 바꾼다.
 *
 * 원문에는 `permission denied for table building_floor`처럼 내부 표 이름이 섞여 나올 수
 * 있어 그대로 화면에 띄우지 않는다. 단 "함수가 아직 DB에 없다"(PGRST202)는 원인이
 * 분명하고 조치가 정해져 있으므로 그대로 안내한다.
 */
export function describeError(ex: unknown): string {
  const code =
    typeof ex === 'object' && ex !== null && 'code' in ex
      ? String((ex as { code: unknown }).code)
      : '';
  if (code === 'PGRST202') {
    return (
      '검색 기능이 아직 DB에 적용되지 않았습니다. ' +
      'supabase/migrations/2026-08-08b_search_buildings.sql을 Supabase SQL Editor에서 실행해 주세요.'
    );
  }
  // 57014 = statement_timeout. 고장이 아니라 **검색어가 너무 넓어서** 나는 것이다.
  // 2026-08-11 실측: '동'·'1'·'서울' 은 수십만 건과 맞아 정확한 건수를 세는 데
  // 3초를 넘긴다('서울'은 서울 건물 17만 개 전부와 매칭). "실패했습니다"로 뭉뚱그리면
  // 사용자가 고장인 줄 알고 같은 검색을 반복한다 — 무엇을 하면 되는지 알려준다.
  // ⛔ 결과를 임의로 잘라 보여주지 않는다(사장님 판단, 2026-08-11): 16,267건인데
  //    "1,000개 이상"이라고 적는 것은 정보를 자르는 것이다.
  if (code === '57014') {
    return (
      '검색어가 너무 넓어 결과를 다 세지 못했습니다. ' +
      '동 이름이나 건물 이름을 조금 더 자세히 넣어 주세요 (예: "명동" → "명동길", "서울" → "서울역").'
    );
  }
  return '검색에 실패했습니다. 잠시 후 다시 시도해 주세요.';
}

/**
 * "지하 2층 ~ 15층 + 옥탑"처럼 층 범위를 한 줄로.
 *
 * 부호 처리를 직접 하지 않고 `formatFloor`를 재사용한다 — 예전엔 아래쪽만 음수를
 * 처리하고 위쪽은 그대로 찍어서, 지하만 있는 건물이 "지하 5층 ~ -1층"으로 보였다
 * (2026-08-08 실측: 강남에 지하층만 있는 건물 213개).
 */
export function describeRange(h: BuildingHit): string {
  if (h.min_floor === null || h.max_floor === null) {
    return h.has_roof ? '옥탑만' : '층 정보 없음';
  }
  const bottom = formatFloor(h.min_floor, null);
  const top = formatFloor(h.max_floor, null);
  const range = bottom === top ? bottom : `${bottom} ~ ${top}`;
  return h.has_roof ? `${range} + 옥탑` : range;
}
