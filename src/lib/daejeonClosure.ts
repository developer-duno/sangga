import type { DaejeonDongClosure, DaejeonClosureIndustry, DaejeonClosureQuarter } from '../types';
import { openCloseQuarterLabel } from './openClose';

/**
 * 대전 건물의 개업·폐업 카드 자리 「동네 폐업 (대전시 공표)」(결정 0044) — **순수 계산·글**만 모은다.
 *
 * 서울시 상권분석서비스는 서울 상권만 다뤄 대전 건물엔 개업·폐업 자료가 없었다. 대전광역시 상권분석 서비스
 * (8989.daejeon.go.kr)가 **행정동 × 업종 × 월 폐업 수**를 낸다 — 서버(`get_daejeon_dong_closure`)가 그 건물이 선
 * 동의 분기별 합 · 최근 4분기 합 · 업종별 합을 준다. 화면은 **나누지 않는다**(폐업률 없음 · 건수만).
 *
 * ⛔ **동네(행정동) 전체 값이다** — 이 건물의 값이 아니다(발 문구 둘째 줄이 굵게 말한다).
 * ⛔ **개업 수는 없다** — 대전시가 내지 않는다. 대전시 점포 수도 쓰지 않는다(👤 결정 0044 ⑤ 「폐업만」).
 * ⛔ 모양이 이상하거나 숫자끼리 안 맞으면(분기 합 ≠ 업종 합) **null** — 그때 카드는 지금 대전 화면(옛 제목 ·
 *    「그 자료가 없습니다」) 그대로 선다(👤 「함수 실패·모양 이상 → 지금 화면 그대로」).
 */

/** 대전 건물에서만 바뀌는 카드 제목(👤 결정 0044 ① · 서울은 `SECTION_PLAN.openclose.title` 그대로). */
export const DAEJEON_CLOSURE_TITLE = '동네 폐업 (대전시 공표)';

/** 대전시 자료를 붙일 필지인가 — pnu 앞 두 자리가 대전(30). 지역 이름은 `regions.ts` 의 표가 정본이다. */
export function isDaejeonPnu(pnu: string): boolean {
  return pnu.startsWith('30');
}

/** 동을 못 찾은 건물(👤 지시서 원문). */
export const DAEJEON_NO_DONG_TEXT = '이 건물의 동(행정동)을 찾지 못해 대전시 자료를 붙이지 못했습니다.';

/**
 * 발 문구 다섯(👤 지시서 원문 그대로 — 차례도). 둘째 줄은 카드가 굵게 그린다.
 * ⓘ 다섯째 줄의 「2024년까지」는 창의 시작(서버 상수 2025-01)과 짝인 **고정 사실**이다 — 창 끝(최근 분기)과 달리
 *   적재해도 안 움직인다. 창의 시작을 바꾸는 결정이 나면 이 글과 서버 상수(get_daejeon_dong_closure 의 const ·
 *   적재기 START_YM)를 함께 고친다.
 */
export const DAEJEON_CLOSURE_NOTES = [
  '출처: 대전광역시 상권분석 서비스(8989.daejeon.go.kr)',
  '동네(행정동) 전체 값이며 이 건물의 값이 아닙니다.',
  '대전시는 개업 수를 내지 않아 폐업만 싣습니다.',
  '손님을 받는 가게 업종 33종만 셉니다(부동산 임대·인터넷 판매·도매·사무실 업종 등은 뺍니다).',
  '2024년까지는 대전시 집계 방식이 달라 보이고 최근 6개월은 아직 덜 들어와, 둘 다 싣지 않습니다.',
  "업종 이름은 나라 표준 업종(대전시 기준)이라 '업종 분포' 카드(소상공인시장진흥공단)와 다릅니다.",
] as const;

/**
 * 창업자 업종 칩을 골랐을 때(전체 아님) 대전 카드 ok 에만 서는 한 줄(👤 보완 1 F11 원문) — 대전시 업종은
 * 표준산업분류 소분류라 칩(소진공·서울시 업종 짝)과 잇지 않는다.
 */
export const DAEJEON_CHIP_NOTE = '고른 업종은 이 카드에 표시되지 않습니다(대전시 업종 체계가 다름).';

/**
 * 대전 답을 기다리는 상한(ms). 그동안 카드는 안 그리고(옛 제목이 먼저 섰다 바뀌지 않게), 이 안에 답이 없으면
 * 지금 대전 카드(옛 제목·옛 문장)로 선다 — 늦게 온 답은 버린다(보완 1 F7).
 */
export const DAEJEON_CLOSURE_WAIT_MS = 8000;

/** 대전 갈래를 탈 서버 답인가 — 대전 필지에서 서울 함수가 not_seoul 또는 no_coord(좌표 없음 — 대전 함수는 PNU 만 쓴다 · F6). */
export function wantsDaejeon(pnu: string, statuses: readonly string[]): boolean {
  return isDaejeonPnu(pnu) && statuses.some((s) => s === 'not_seoul' || s === 'no_coord');
}

/** 업종 표에 줄로 세우는 수 — 나머지는 「그 밖 N종 M건」 한 줄. */
export const DAEJEON_TOP_INDUSTRIES = 5;

function isCount(x: unknown): x is number {
  return typeof x === 'number' && Number.isInteger(x) && x >= 0;
}

function isQuarter(x: unknown): x is DaejeonClosureQuarter {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return typeof r.quarter === 'string' && openCloseQuarterLabel(r.quarter) !== null && isCount(r.clsbiz_co);
}

function isIndustry(x: unknown): x is DaejeonClosureIndustry {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return typeof r.induty_nm === 'string' && r.induty_nm.trim() !== '' && isCount(r.clsbiz_co) && r.clsbiz_co > 0;
}

/**
 * 서버 답 → 쓸 수 있는 한 줄, 아니면 null(그때 카드는 옛 대전 화면 그대로).
 *
 * 받는 것: 정확히 한 줄 · status 가 `ok` 또는 `no_dong`(대전 필지에만 부르므로 `not_daejeon` 은 이상한 답이다).
 * ok 는 열쇠까지 엄격히 — 동 이름 · 분기 한 칸 이상(옛 → 새 · 겹침 없음) · 더한 분기가 창의 **끝 몇 칸**과 같다 ·
 * 큰 숫자 = 더한 분기들의 합 = 업종 합 · 업종은 많은 순. 하나라도 어긋나면 숫자끼리 다른 말을 하니 통째로 버린다.
 */
export function parseDaejeonClosure(data: unknown): DaejeonDongClosure | null {
  if (!Array.isArray(data) || data.length !== 1) return null;
  const r = data[0] as Record<string, unknown>;
  if (typeof r !== 'object' || r === null) return null;
  if (r.status === 'no_dong') {
    return {
      status: 'no_dong',
      dong_nm: null,
      received_on: typeof r.received_on === 'string' ? r.received_on : null,
      quarters: null,
      sum_quarters: null,
      clsbiz_sum: null,
      industries: null,
    };
  }
  if (r.status !== 'ok') return null;
  const { dong_nm, quarters, sum_quarters, clsbiz_sum, industries } = r;
  if (typeof dong_nm !== 'string' || dong_nm.trim() === '') return null;
  if (!Array.isArray(quarters) || quarters.length === 0 || !quarters.every(isQuarter)) return null;
  const codes = quarters.map((q) => q.quarter);
  if (codes.some((c, i) => i > 0 && c <= codes[i - 1])) return null; // 옛 → 새 · 겹침 없음
  if (!Array.isArray(sum_quarters) || sum_quarters.length === 0 || sum_quarters.length > codes.length) return null;
  const tail = codes.slice(codes.length - sum_quarters.length);
  if (sum_quarters.some((s, i) => s !== tail[i])) return null;
  if (!isCount(clsbiz_sum)) return null;
  if (!Array.isArray(industries) || !industries.every(isIndustry)) return null;
  if (industries.some((x, i) => i > 0 && x.clsbiz_co > industries[i - 1].clsbiz_co)) return null;
  const recent = quarters.slice(codes.length - sum_quarters.length).reduce((a, q) => a + q.clsbiz_co, 0);
  const byIndustry = industries.reduce((a, x) => a + x.clsbiz_co, 0);
  if (recent !== clsbiz_sum || byIndustry !== clsbiz_sum) return null;
  return {
    status: 'ok',
    dong_nm,
    received_on: typeof r.received_on === 'string' ? r.received_on : null,
    quarters,
    sum_quarters: sum_quarters as string[],
    clsbiz_sum,
    industries,
  };
}

/** 이름 줄 — 「둔산2동 · 가게 업종」. */
export function dongLine(dong: string): string {
  return `${dong} · 가게 업종`;
}

/** 건수 표기 「1,234건」. */
export function closureCount(n: number): string {
  return `${n.toLocaleString('ko-KR')}건`;
}

/** 큰 숫자 「폐업 378건」. */
export function closureBigText(n: number): string {
  return `폐업 ${closureCount(n)}`;
}

/** 더한 기간 「2025년 2분기~2026년 1분기」(분기 하나면 그 분기만). 읽을 수 없으면 null. */
export function quarterRangeText(quarters: readonly string[]): string | null {
  if (quarters.length === 0) return null;
  const first = openCloseQuarterLabel(quarters[0]);
  const last = openCloseQuarterLabel(quarters[quarters.length - 1]);
  if (first === null || last === null) return null;
  return quarters.length === 1 ? first : `${first}~${last}`;
}

/** 업종 표 — 위 다섯 줄 + 나머지 「그 밖 N종 M건」(없으면 null). */
export function industryTable(industries: readonly DaejeonClosureIndustry[]): {
  top: DaejeonClosureIndustry[];
  rest: { kinds: number; count: number } | null;
} {
  const top = industries.slice(0, DAEJEON_TOP_INDUSTRIES);
  const others = industries.slice(DAEJEON_TOP_INDUSTRIES);
  return {
    top,
    rest: others.length > 0 ? { kinds: others.length, count: others.reduce((a, x) => a + x.clsbiz_co, 0) } : null,
  };
}

/** 「그 밖 N종 M건」. */
export function restText(rest: { kinds: number; count: number }): string {
  return `그 밖 ${rest.kinds}종 ${closureCount(rest.count)}`;
}

/**
 * 접힌 요약 — 서울 카드와 같은 규칙으로 **값을 적지 않는다**(한정어 「동네 전체」를 담을 자리가 없어 이 건물 값으로
 * 읽힌다). 어느 동인지와 언제까지인지만: 「둔산2동 · 2026년 1분기까지 대전시 공표」.
 */
export function daejeonSummary(row: DaejeonDongClosure): string {
  if (row.status !== 'ok' || row.dong_nm === null || row.quarters === null) return '동(행정동)을 찾지 못했습니다';
  const last = openCloseQuarterLabel(row.quarters[row.quarters.length - 1]?.quarter);
  return last ? `${row.dong_nm} · ${last}까지 대전시 공표` : row.dong_nm;
}

/** 분기 막대 한 칸 — 높이는 창 안 최댓값 대비 %(0 은 0 건이라 높이 0 · 글자로 「0」). */
export type DaejeonBar = { quarter: string; label: string; year: string; q: string; count: number; h: number };

export function daejeonBars(quarters: readonly DaejeonClosureQuarter[]): DaejeonBar[] {
  const max = Math.max(0, ...quarters.map((q) => q.clsbiz_co));
  return quarters.map((q) => ({
    quarter: q.quarter,
    label: openCloseQuarterLabel(q.quarter) ?? q.quarter,
    year: q.quarter.slice(0, 4),
    q: q.quarter.slice(4),
    count: q.clsbiz_co,
    h: max > 0 ? (q.clsbiz_co / max) * 100 : 0,
  }));
}

/**
 * 역할 요약 칸(👤 지시서 #9 · 메인 추가) — 값 줄 「폐업 378건 · 2025년 2분기~2026년 1분기(가게 업종)」(카드와 같은 기간 글 ·
 * 보완 1 F9) · 근거 줄 「둔산2동 · 대전시 공표」.
 */
export function daejeonTileLines(row: DaejeonDongClosure): { line: string; basis: string } | null {
  if (row.status !== 'ok' || row.dong_nm === null || row.clsbiz_sum === null || row.sum_quarters === null) return null;
  const range = quarterRangeText(row.sum_quarters);
  if (range === null) return null;
  return {
    line: `${closureBigText(row.clsbiz_sum)} · ${range}(가게 업종)`,
    basis: `${row.dong_nm} · 대전시 공표`,
  };
}
