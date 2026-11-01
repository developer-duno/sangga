import type { DistrictCensusPop, DistrictCensusPopStatus } from '../types';
import { districtLabel } from './districtSales';
import { sidoNameOfPnu } from './openClose';

/**
 * 대전 건물의 「상권 인구 (통계청 집계구)」 카드의 **순수 계산**만 모은다(결정 0045 PR⑤ ③-1·③-3 · 컴포넌트에 계산 0).
 *
 * ⛔ **서버 값 그대로다.** 값·하한·상한·겹친 수·통째 수·덮임은 서버(`get_district_census_pop`)가 준 수를 쉼표만 찍어 적는다 —
 *    반올림·다시 셈 0. 여기서 하는 산수는 「범위만 적을까」를 가르는 **비교 하나**(`rangeOnly` — 상한 − 하한 > 2 × 값)뿐이고,
 *    나누기·비율 글자는 만들지 않는다(덮임 % 는 서버 값을 옮긴 것).
 * ⛔ **이 건물의 값이 아니다.** 이 건물이 속한 대전 상권 안의 합계(어림)다. 상권이 여럿이면 상권마다 따로 두고 더하지 않는다.
 * ⛔ **연도 글자를 박지 않는다.** 통계 연도·경계 연월은 서버 표지 칸(`base_year`·`bnd_base_date`)에서 만든다(시험이 원문을 훑는다).
 * ⛔ 판단 낱말·금지어를 쓰지 않는다 · 「일하는 사람」·「직장인구」 낱말은 발 문구 넷째 한 문장에만 둔다(서울 카드와 다른 값이라).
 */

// ── 모양 검사 ───────────────────────────────────────────────────────────────

/** 서버가 주는 줄 상태 다섯. 이 밖의 글자가 오면 모양 검사에서 떨어진다. */
export const CENSUS_POP_STATUSES: readonly DistrictCensusPopStatus[] = [
  'no_coord',
  'not_daejeon',
  'outside_daejeon_district',
  'ok',
  'no_data',
];

/** 건물 단위 상태 셋(한 줄만 온다). */
const HEAD_STATUSES: readonly DistrictCensusPopStatus[] = ['no_coord', 'not_daejeon', 'outside_daejeon_district'];

function isCount(x: unknown): x is number {
  return typeof x === 'number' && Number.isInteger(x) && x >= 0;
}

function isNullableString(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'string';
}

/** 'YYYY-MM-DD' 꼴이고 실제 있는 날인가. */
function isDateText(x: unknown): x is string {
  if (typeof x !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(x)) return false;
  const [y, m, d] = x.split('-').map(Number);
  const t = new Date(Date.UTC(y, m - 1, d));
  return t.getUTCFullYear() === y && t.getUTCMonth() === m - 1 && t.getUTCDate() === d;
}

/** 네 자리 연도. */
function isYear(x: unknown): x is number {
  return typeof x === 'number' && Number.isInteger(x) && x >= 1000 && x <= 9999;
}

/** 0 이상 유한 수(덮임 % · 넓이 — 소수가 온다). */
function isNonNegative(x: unknown): x is number {
  return typeof x === 'number' && Number.isFinite(x) && x >= 0;
}

/** 하한 ≤ 값 ≤ 상한 · 셋 다 0 이상 정수. */
function isTriple(lo: unknown, v: unknown, hi: unknown): boolean {
  return isCount(lo) && isCount(v) && isCount(hi) && lo <= v && v <= hi;
}

function isCensusRow(x: unknown): x is DistrictCensusPop {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  if (typeof r.status !== 'string' || !(CENSUS_POP_STATUSES as readonly string[]).includes(r.status)) return false;
  // 표지 칸 셋은 모든 줄에 온다(서버가 표지와 cross join — 표지가 없으면 0줄).
  if (!isDateText(r.received_on) || !isYear(r.base_year) || !isDateText(r.bnd_base_date)) return false;
  if (r.status === 'ok' || r.status === 'no_data') {
    if (typeof r.district_id !== 'string' || !isNullableString(r.district_nm) || !isNullableString(r.district_type)) {
      return false;
    }
  }
  if (r.status !== 'ok') return true;
  return (
    isCount(r.n_overlap) &&
    isCount(r.n_full) &&
    r.n_full <= r.n_overlap &&
    isNonNegative(r.cover_pct) &&
    (r.area_m2 === null || r.area_m2 === undefined || isNonNegative(r.area_m2)) &&
    isTriple(r.pop_lo, r.pop, r.pop_hi) &&
    isTriple(r.hh_lo, r.hh, r.hh_hi) &&
    isTriple(r.emp_lo, r.emp, r.emp_hi)
  );
}

/**
 * 서버 응답(`get_district_census_pop`)의 **모양**을 본다. 하나라도 어긋나면 false → 카드가 통째로 빠진다(콘솔 경고만).
 * ⛔ 빈 배열(표지 없음)·섞인 답(정상 줄 + 이상한 줄 하나 · 건물 단위 상태 줄이 다른 줄과 함께 옴)은 통째로 거부한다.
 * ⛔ 표지 칸 셋은 모든 줄에 같은 값이어야 한다(줄마다 다른 판을 말하지 않게).
 */
export function isDistrictCensusPopList(x: unknown): x is DistrictCensusPop[] {
  if (!Array.isArray(x) || x.length === 0 || !x.every(isCensusRow)) return false;
  const rows = x as DistrictCensusPop[];
  if (rows.some((r) => HEAD_STATUSES.includes(r.status)) && rows.length !== 1) return false;
  const first = rows[0];
  return rows.every(
    (r) =>
      r.received_on === first.received_on &&
      r.base_year === first.base_year &&
      r.bnd_base_date === first.bnd_base_date,
  );
}

// ── 건물 단위 상태 셋 ───────────────────────────────────────────────────────

/** 건물 단위 상태 줄의 펼친 본문. no_coord 는 서울 카드와 같은 글. */
export function censusHeadBody(status: DistrictCensusPopStatus, pnu: string): string {
  if (status === 'not_daejeon') {
    const sido = sidoNameOfPnu(pnu);
    return sido === null
      ? '통계청 집계구 인구는 대전 상권에만 붙였습니다 — 이 건물에는 그 자료가 없습니다.'
      : `통계청 집계구 인구는 대전 상권에만 붙였습니다 — 이 건물(${sido})에는 그 자료가 없습니다.`;
  }
  if (status === 'outside_daejeon_district') return '이 건물이 속한 대전 상권이 없어 자료가 없습니다.';
  return '이 건물의 위치 정보가 없어 속한 상권을 찾지 못했습니다.';
}

/** 건물 단위 상태 줄의 접힌 요약 — 서울 카드의 `headSummary` 꼴(대전 글). */
export function censusHeadSummary(status: DistrictCensusPopStatus, pnu: string): string {
  if (status === 'not_daejeon') {
    const sido = sidoNameOfPnu(pnu);
    return sido === null
      ? '대전 상권에만 붙인 자료라 이 건물에는 없습니다'
      : `대전 상권에만 붙인 자료라 이 건물(${sido})에는 없습니다`;
  }
  if (status === 'outside_daejeon_district') return '이 건물이 속한 대전 상권이 없습니다';
  return '위치 정보가 없어 속한 상권을 찾지 못했습니다';
}

/** 응답의 건물 단위 상태 줄(있으면 그 한 줄). */
export function censusHeadRow(rows: readonly DistrictCensusPop[]): DistrictCensusPop | undefined {
  return rows.find((r) => HEAD_STATUSES.includes(r.status));
}

// ── 접힌 요약 ───────────────────────────────────────────────────────────────

/**
 * 접혀 있어도 보이는 한 줄 — **값 0**. 「○○ 외 상권 N곳 · 통계청 집계구 ○○○○년 통계」(연도 = 첫 ok 줄의 `base_year`) ·
 * ok 가 없으면 「○○ · 통계청 집계구 인구 자료가 없습니다」 · 건물 단위 상태면 `censusHeadSummary`.
 */
export function censusSummary(rows: readonly DistrictCensusPop[], pnu: string): string {
  const head = censusHeadRow(rows);
  if (head) return censusHeadSummary(head.status, pnu);
  const districts = rows.filter((r) => r.status === 'ok' || r.status === 'no_data');
  const lead = districts[0];
  const others = districts.length - 1;
  const who = others > 0 ? `${districtLabel(lead)} 외 상권 ${others}곳` : districtLabel(lead);
  const ok = districts.find((r) => r.status === 'ok');
  if (!ok || ok.base_year === null) return `${who} · 통계청 집계구 인구 자료가 없습니다`;
  return `${who} · 통계청 집계구 ${ok.base_year}년 통계`;
}

// ── 범위만 적을까 ───────────────────────────────────────────────────────────

/**
 * 범위(상한 − 하한)가 값의 2배를 넘으면 true — 값을 숨기고 범위만 적는다(👤 ③-3 · 함정 6).
 * ⓘ 같으면(= 2배) 값을 보인다. 나누기·비율이 아니라 비교 하나다.
 */
export function rangeOnly(value: number, lo: number, hi: number): boolean {
  return hi - lo > 2 * value;
}

function n(x: number): string {
  return x.toLocaleString('ko-KR');
}

// ── 덩이 글 ─────────────────────────────────────────────────────────────────

export type CensusBig = {
  /** 큰 숫자 — 「약 3,120명」 · 범위만이면 「범위 0~1,380명」. */
  num: string;
  /** 큰 숫자 옆 범위 — 「범위 1,840~4,610명」 · 범위만이면 null(이미 큰 숫자다). */
  range: string | null;
  /** 덧붙임(사는 사람 덩이의 가구) — 없으면 null. */
  detail: string | null;
};

function bigOf(value: number, lo: number, hi: number, unit: string): Pick<CensusBig, 'num' | 'range'> {
  const span = `범위 ${n(lo)}~${n(hi)}${unit}`;
  return rangeOnly(value, lo, hi) ? { num: span, range: null } : { num: `약 ${n(value)}${unit}`, range: span };
}

/**
 * 「사는 사람 (거주 인구)」 덩이 — 인구 값 + 범위 · 가구는 **따로** 2배 식(「가구 약 1,380 (범위 820~2,050)」 ·
 * 범위만이면 「가구 범위 0~640」). ok 가 아니면 null.
 */
export function residentBig(row: DistrictCensusPop): CensusBig | null {
  if (row.status !== 'ok' || row.pop === null || row.pop_lo === null || row.pop_hi === null) return null;
  const big = bigOf(row.pop, row.pop_lo, row.pop_hi, '명');
  let detail: string | null = null;
  if (row.hh !== null && row.hh_lo !== null && row.hh_hi !== null) {
    detail = rangeOnly(row.hh, row.hh_lo, row.hh_hi)
      ? `가구 범위 ${n(row.hh_lo)}~${n(row.hh_hi)}`
      : `가구 약 ${n(row.hh)} (범위 ${n(row.hh_lo)}~${n(row.hh_hi)})`;
  }
  return { ...big, detail };
}

/** 「사업체 종사자 (통계청)」 덩이 — 값 + 범위(범위만이면 범위 하나). ok 가 아니면 null. */
export function empBig(row: DistrictCensusPop): CensusBig | null {
  if (row.status !== 'ok' || row.emp === null || row.emp_lo === null || row.emp_hi === null) return null;
  return { ...bigOf(row.emp, row.emp_lo, row.emp_hi, '명'), detail: null };
}

/** 셋(인구·가구·종사자) 가운데 하나라도 범위만 적었나. */
function anyRangeOnly(row: DistrictCensusPop): boolean {
  const triples: [number | null, number | null, number | null][] = [
    [row.pop, row.pop_lo, row.pop_hi],
    [row.hh, row.hh_lo, row.hh_hi],
    [row.emp, row.emp_lo, row.emp_hi],
  ];
  return triples.some(([v, lo, hi]) => v !== null && lo !== null && hi !== null && rangeOnly(v, lo, hi));
}

/** 덮임을 적는 소수 자릿수. */
export const COVER_DIGITS = 2;

/**
 * 덮임 — 서버 값을 소수 `COVER_DIGITS` 자리까지(반올림), 끝의 0 은 뗀다(100 → 「100」 · 99.975 → 「99.98」).
 * ⓘ 99.975 같은 값은 부동소수로 99.97499… 라 그냥 반올림하면 내려간다 — 12자리 십진 글로 한 번 다듬은 뒤 반올림한다.
 */
export function coverText(pct: number): string {
  const k = 10 ** COVER_DIGITS;
  const rounded = Math.round(Number((pct * k).toPrecision(12))) / k;
  return String(rounded);
}

/**
 * 상권 덩어리 발 한 줄 — 「겹친 집계구 9개 · 통째로 든 집계구 3개 · 상권 넓이의 100% 를 덮음」 +
 * 셋 중 하나라도 범위만이면 꼬리 「 — 범위가 넓어 값 대신 범위만 적은 칸이 있습니다」. ok 가 아니면 null.
 */
export function censusNote(row: DistrictCensusPop): string | null {
  if (row.status !== 'ok' || row.n_overlap === null || row.n_full === null || row.cover_pct === null) return null;
  const base = `겹친 집계구 ${n(row.n_overlap)}개 · 통째로 든 집계구 ${n(row.n_full)}개 · 상권 넓이의 ${coverText(row.cover_pct)}% 를 덮음`;
  return anyRangeOnly(row) ? `${base} — 범위가 넓어 값 대신 범위만 적은 칸이 있습니다` : base;
}

// ── 표지 연도 글 ────────────────────────────────────────────────────────────

/** 경계 기준일 'YYYY-MM-DD' → 「○○○○년 ○월」. 못 읽으면 null. */
export function boundaryText(date: string | null): string | null {
  if (!isDateText(date)) return null;
  const [y, m] = date.split('-').map(Number);
  return `${y}년 ${m}월`;
}

/** 배지 옆 작은 글 — 연도 둘은 서버 표지 값. */
export function censusBadgeNote(row: DistrictCensusPop): string {
  const bnd = boundaryText(row.bnd_base_date);
  return `통계청 SGIS ${row.base_year}년 집계구 통계 · ${bnd} 경계 · 사람이 신청해 받은 자료`;
}

/** 발 문구 첫째(출처) — 연도 둘은 서버 표지 값. */
export function censusSourceText(row: DistrictCensusPop): string {
  const bnd = boundaryText(row.bnd_base_date);
  return `출처: 통계청 SGIS 통계지리정보서비스 집계구 통계(${row.base_year}년)·집계구 경계(${bnd}) — 자료신청 87909 · 공공누리 1유형.`;
}

// ── 글 상수(👤 시안 글자 그대로 · 결정 0045 PR⑤) ───────────────────────────

export const CENSUS_POP_TITLE = '상권 인구 (통계청 집계구)';

export const CENSUS_LEAD_STRONG = '이 건물이 속한 상권의 인구입니다';
export const CENSUS_LEAD_REST: readonly [string, string, string] = [
  ' — 통계청 집계구 통계를 상권 모양에 맞춰 ',
  '면적 비율로 나눈 어림값',
  '이고, 이 건물의 인구가 아닙니다.',
];

export const CENSUS_BADGE = 'C등급 · 통계청 집계구 어림';

/** 덩이 머리 둘(👤 종사자 줄 「나」). */
export const CENSUS_CHUNK_TITLES = {
  resident: '사는 사람 (거주 인구)',
  emp: '사업체 종사자 (통계청)',
} as const;

/** 발 문구 둘째~다섯째(첫째 출처는 `censusSourceText` — 연도가 서버 값이라). 둘째는 굵게. */
export const CENSUS_NOTES = {
  notBuilding: '이 상권 안의 합계(어림)이며 이 건물의 값이 아닙니다.',
  method:
    '집계구(통계청이 통계를 내는 가장 작은 구역)는 상권 경계와 딱 맞지 않아, 겹친 넓이의 비율로 나눠 더했습니다. 범위의 아래 끝은 상권에 통째로 든 집계구만 더한 값, 위 끝은 조금이라도 겹친 집계구를 전부 더한 값입니다. 범위가 값의 2배를 넘으면 값 대신 범위만 적습니다.',
  empNotWorker:
    '사업체 종사자는 통계청 전국사업체조사 기준이라 서울 카드의 「일하는 사람(직장인구)」과 같은 뜻이 아닙니다. 길단위인구는 서울시 자료라 서울만 있습니다.',
  next: '통계청이 다음 판을 내면 사람이 다시 받아 넣습니다(받은 날 기준 1년 뒤 예정).',
} as const;

/** 상권 줄인데 결과표에 그 상권이 없음(no_data). */
export const CENSUS_NO_DATA_TEXT = '통계청 집계구와 겹치지 않아 이 상권의 인구를 셈하지 못했습니다.';
