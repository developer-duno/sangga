import type { DistrictPop, DistrictPopFlow } from '../types';
import { districtLabel, formatCount, headSummary, isQuarterCode } from './districtSales';
import { OPEN_CLOSE_STATUSES, openCloseQuarterLabel, splitQuarter } from './openClose';

/**
 * 「상권 인구 (서울시 공표)」 카드의 **순수 계산**만 모은다(결정 0045 PR③ · 컴포넌트에 계산 0).
 *
 * ⛔ **공표값 그대로다.** 길단위인구는 서울시가 공표한 **3개월간 인구수**(명)다 — 하루 평균·면적당으로 바꾸지 않는다
 *    (👤 결정 ②). 여기서 하는 산수는 미니 막대의 **높이**(그 묶음 최댓값에 대한 비례)뿐이다.
 * ⛔ **이 건물의 값이 아니다.** 이 건물이 속한 서울시 상권 전체의 값이다. 상권이 여럿이면 상권마다 따로 둔다.
 * ⛔ **분기·연도 글자를 박지 않는다.** 「YYYY년 기준」은 서버의 `*_value_quarter`(값이 마지막으로 바뀐 분기) 앞 네 자리다
 *    — `*_last_quarter`(그 상권이 가진 마지막 분기)로 쓰지 않는다.
 * ⛔ 판단 낱말·비율 글자를 쓰지 않는다 — 숫자만 나란히. 연령 칸은 이번에 안 그린다.
 */

// ── 모양 검사 ───────────────────────────────────────────────────────────────

function isCount(x: unknown): boolean {
  return typeof x === 'number' && Number.isInteger(x) && x >= 0;
}

function isNullableString(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'string';
}

function isNullableQuarter(x: unknown): boolean {
  return x === null || x === undefined || isQuarterCode(x);
}

/** 시간대 여섯 칸(차례 = 화면 막대 차례)과 막대 아래 글. */
export const FLOW_TIME_KEYS = [
  ['tmzon_00_06', '0~6'],
  ['tmzon_06_11', '6~11'],
  ['tmzon_11_14', '11~14'],
  ['tmzon_14_17', '14~17'],
  ['tmzon_17_21', '17~21'],
  ['tmzon_21_24', '21~24'],
] as const;

/** 요일 일곱 칸. */
export const FLOW_DAY_KEYS = [
  ['mon', '월'],
  ['tues', '화'],
  ['wed', '수'],
  ['thur', '목'],
  ['fri', '금'],
  ['sat', '토'],
  ['sun', '일'],
] as const;

/** 숫자 객체 — null 이거나, 필수 칸(tot·ml·fml + more)이 전부 0 이상 정수. */
function isPeopleObject(x: unknown, more: readonly string[] = []): boolean {
  if (x === null || x === undefined) return true;
  if (typeof x !== 'object' || Array.isArray(x)) return false;
  const r = x as Record<string, unknown>;
  return ['tot', 'ml', 'fml', ...more].every((k) => isCount(r[k]));
}

const FLOW_REQUIRED: readonly string[] = [...FLOW_TIME_KEYS.map((k) => k[0]), ...FLOW_DAY_KEYS.map((k) => k[0])];

function isPopRow(x: unknown): x is DistrictPop {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  if (typeof r.status !== 'string' || !(OPEN_CLOSE_STATUSES as readonly string[]).includes(r.status)) return false;
  if (r.status === 'ok' || r.status === 'no_data') {
    if (typeof r.district_id !== 'string' || !isNullableString(r.district_nm) || !isNullableString(r.district_type)) {
      return false;
    }
  }
  if (r.status !== 'ok') return true;
  return (
    isNullableQuarter(r.flow_table_quarter) &&
    isNullableQuarter(r.flow_quarter) &&
    isNullableQuarter(r.resident_value_quarter) &&
    isNullableQuarter(r.resident_last_quarter) &&
    isNullableQuarter(r.worker_value_quarter) &&
    isNullableQuarter(r.worker_last_quarter) &&
    isPeopleObject(r.flow, FLOW_REQUIRED) &&
    isPeopleObject(r.resident) &&
    isPeopleObject(r.worker) &&
    // 길단위인구 값이 왔으면 그 분기도 와야 한다(「○분기 3개월간」을 지어내지 않는다).
    (r.flow === null || r.flow === undefined || isQuarterCode(r.flow_quarter))
  );
}

/**
 * 서버 응답(`list_district_pop`)의 **모양**을 본다. 하나라도 어긋나면 false → 카드가 통째로 빠진다(콘솔 경고만).
 * ⛔ 빈 배열·섞인 답(정상 줄 + 이상한 줄 하나)은 통째로 거부한다.
 */
export function isDistrictPopList(x: unknown): x is DistrictPop[] {
  return Array.isArray(x) && x.length > 0 && x.every(isPopRow);
}

/**
 * 모양 검사를 지난 답을 화면이 쓸 꼴로 — `ok` 줄인데 길단위·사는·일하는 셋 다 null 이면 그 줄을 `no_data` 로 다룬다
 * (검사 뒤 보완 F12 — 빈 덩어리를 그리지 않는다 · 서버는 셋 중 하나라도 있어야 ok 를 주므로 이상한 답 방어다).
 */
export function normalizePopRows(rows: readonly DistrictPop[]): DistrictPop[] {
  return rows.map((r) =>
    r.status === 'ok' && !r.flow && !r.resident && !r.worker ? { ...r, status: 'no_data' } : r,
  );
}

// ── 「YYYY년 기준」 ─────────────────────────────────────────────────────────

/**
 * 값이 마지막으로 바뀐 분기 → 「○○○○년 기준」. 못 읽으면 null.
 * 그 상권의 마지막 분기(`lastQuarter`)를 주면 그 사이 서울시가 값을 안 바꾼 해를 시안 원문 꼴로 덧붙인다(검사 뒤 보완 F2) —
 * 해 = 값이 바뀐 해 + 1 부터 마지막 분기의 해 − 1 까지 · 비면 괄호 없음 · 「(서울시가 ○○○○·○○○○년에는 안 바꿈)」.
 * ⓘ 해는 서버 값에서 계산한다(글자로 박지 않는다).
 */
export function valueYearText(
  valueQuarter: string | null | undefined,
  lastQuarter?: string | null,
): string | null {
  const s = splitQuarter(valueQuarter);
  if (!s) return null;
  const base = `${s.year}년 기준`;
  const last = splitQuarter(lastQuarter);
  if (!last) return base;
  const years: number[] = [];
  for (let y = Number(s.year) + 1; y <= Number(last.year) - 1; y++) years.push(y);
  return years.length > 0 ? `${base} (서울시가 ${years.join('·')}년에는 안 바꿈)` : base;
}

// ── 접힌 요약 ───────────────────────────────────────────────────────────────

/**
 * 접혀 있어도 보이는 한 줄 — `openCloseSummary` 규칙 그대로(**값 0**).
 * 「○○ 외 상권 1곳 · 길단위인구 ○○○○년 2분기 · 사는 사람 ○○○○년 · 일하는 사람 ○○○○년 기준」 — 길단위 = `flow_table_quarter` ·
 * 사는/일하는 = 첫 ok 상권 줄의 `*_value_quarter` · 셋 중 없는 것은 그 조각을 뺀다.
 */
export function popSummary(rows: readonly DistrictPop[], pnu: string): string {
  const head = rows.find((r) => r.status !== 'ok' && r.status !== 'no_data');
  if (head) return headSummary(head.status, pnu);
  const districts = rows.filter((r) => r.status === 'ok' || r.status === 'no_data');
  const lead = districts[0];
  const others = districts.length - 1;
  const who = others > 0 ? `${districtLabel(lead)} 외 상권 ${others}곳` : districtLabel(lead);
  const ok = districts.find((r) => r.status === 'ok');
  if (!ok) return `${who} · 서울시 인구 자료가 없습니다`;
  const parts: string[] = [];
  const flowLabel = openCloseQuarterLabel(ok.flow_table_quarter);
  if (flowLabel) parts.push(`길단위인구 ${flowLabel}`);
  const people: string[] = [];
  const ry = splitQuarter(ok.resident_value_quarter);
  if (ry) people.push(`사는 사람 ${ry.year}년`);
  const wy = splitQuarter(ok.worker_value_quarter);
  if (wy) people.push(`일하는 사람 ${wy.year}년`);
  if (people.length > 0) parts.push(`${people.join(' · ')} 기준`);
  return parts.length > 0 ? `${who} · ${parts.join(' · ')}` : who;
}

// ── 길단위인구 덩이 ─────────────────────────────────────────────────────────

export type PopBig = {
  /** 「412,560명」 */
  num: string;
  /** 「○○○○년 2분기 3개월간」 · 「○○○○년 기준」 */
  when: string | null;
  /** 「남 190,100 · 여 222,460」 */
  detail: string;
};

/** 길단위인구 큰 숫자 줄 — 값 그대로(3개월간 인구수). flow 가 없으면 null. */
export function flowBigText(row: DistrictPop): PopBig | null {
  const f = row.flow;
  if (row.status !== 'ok' || !f) return null;
  const label = openCloseQuarterLabel(row.flow_quarter);
  return {
    num: formatCount(f.tot, '명'),
    when: label ? `${label} 3개월간` : null,
    detail: `남 ${formatCount(f.ml, '')} · 여 ${formatCount(f.fml, '')}`,
  };
}

export type FlowBar = { key: string; tick: string; value: number; h: number };
export type FlowBars = { bars: FlowBar[]; max: number; scale: string | null };

function barsOf(f: DistrictPopFlow, keys: readonly (readonly [string, string])[]): FlowBars {
  const values = keys.map(([k]) => (typeof f[k] === 'number' ? (f[k] as number) : 0));
  const max = Math.max(0, ...values);
  return {
    bars: keys.map(([k, tick], i) => ({ key: k, tick, value: values[i], h: max > 0 ? (values[i] / max) * 100 : 0 })),
    max,
    // 단위 꼬리 「(3개월간)」 — 막대 값도 3개월간 인구수다(검사 뒤 보완 F3).
    scale: max > 0 ? `꽉 차면 ${formatCount(max, '명')}(3개월간)` : null,
  };
}

/** 시간대 여섯 · 요일 일곱 미니 막대 — 값 그대로 · 높이 = 값 ÷ 그 묶음 최댓값. flow 가 없으면 null. */
export function flowBars(row: DistrictPop): { time: FlowBars; day: FlowBars } | null {
  const f = row.flow;
  if (row.status !== 'ok' || !f) return null;
  return { time: barsOf(f, FLOW_TIME_KEYS), day: barsOf(f, FLOW_DAY_KEYS) };
}

/** 그 상권 길단위인구가 표 전체 최신보다 옛 분기에서 멈췄으면 한 줄. */
export function flowLagText(row: DistrictPop): string | null {
  if (row.status !== 'ok' || !row.flow_quarter || !row.flow_table_quarter) return null;
  if (row.flow_quarter === row.flow_table_quarter) return null;
  const label = openCloseQuarterLabel(row.flow_quarter);
  return label ? `이 상권 길단위인구 자료는 ${label}까지입니다` : null;
}

// ── 사는 사람 · 일하는 사람 ─────────────────────────────────────────────────

/** 사는 사람(상주인구) 줄 — 「2,310명」 · 「○○○○년 기준」 · 「남 1,090 · 여 1,220」(가구 수는 안 싣는다). 값이 없으면 null. */
export function residentText(row: DistrictPop): PopBig | null {
  const r = row.resident;
  if (row.status !== 'ok' || !r) return null;
  // ⛔ 가구 수는 싣지 않는다(메인 결정 나) — 서울시 화면의 가구세대 수(평창동동측 1,858)와 우리 `tot_hshld`(776)가
  //    다른 값이라 같은 상권에 다른 가구 수를 적게 된다 · 👤 결정 원문에도 가구는 없다. 칸은 타입에만 남긴다.
  return {
    num: formatCount(r.tot, '명'),
    when: valueYearText(row.resident_value_quarter, row.resident_last_quarter),
    detail: `남 ${formatCount(r.ml, '')} · 여 ${formatCount(r.fml, '')}`,
  };
}

/** 일하는 사람(직장인구) 줄 — 「6,840명」 · 「○○○○년 기준」 · 「남 3,900 · 여 2,940」. 값이 없으면 null. */
export function workerText(row: DistrictPop): PopBig | null {
  const w = row.worker;
  if (row.status !== 'ok' || !w) return null;
  return {
    num: formatCount(w.tot, '명'),
    when: valueYearText(row.worker_value_quarter, row.worker_last_quarter),
    detail: `남 ${formatCount(w.ml, '')} · 여 ${formatCount(w.fml, '')}`,
  };
}

/**
 * 값은 없고(옛 분기에서 끊김) 그 상권의 마지막 분기만 있을 때 한 줄 — 「이 상권 사는 사람 자료는 ○○○○년 ○분기까지입니다」.
 * 값이 있거나 마지막 분기도 없으면 null(둘 다 없으면 그 덩이 자체가 없다).
 */
export function residentLagText(row: DistrictPop): string | null {
  if (row.status !== 'ok' || row.resident) return null;
  const label = openCloseQuarterLabel(row.resident_last_quarter);
  return label ? `이 상권 사는 사람 자료는 ${label}까지입니다` : null;
}

export function workerLagText(row: DistrictPop): string | null {
  if (row.status !== 'ok' || row.worker) return null;
  const label = openCloseQuarterLabel(row.worker_last_quarter);
  return label ? `이 상권 일하는 사람 자료는 ${label}까지입니다` : null;
}

// ── 글 ──────────────────────────────────────────────────────────────────────

export const POP_LEAD_STRONG = '이 건물이 속한 상권의 인구입니다';
export const POP_LEAD_REST: readonly [string, string, string] = [
  ' — 서울시가 공표한 ',
  '상권 값',
  ' 그대로이고, 이 건물의 인구가 아닙니다.',
];

export const POP_BADGE = 'C등급 · 서울시 집계';
/** 배지 옆 작은 글(검사 뒤 보완 F4 · 메인 문구 — 추정매출 카드의 `SALES_BADGE_NOTE` 꼴). */
export const POP_BADGE_NOTE = '서울시 상권분석서비스 · 생활인구·주민등록·통신사 자료로 서울시가 셈';

/** 덩이 머리 셋(목업 글자 그대로). */
export const POP_CHUNK_TITLES = {
  flow: '길단위인구 (서울시 집계)',
  resident: '사는 사람 (상주인구)',
  worker: '일하는 사람 (직장인구)',
} as const;

/** 미니 막대 묶음 이름. */
export const POP_BAR_GROUPS = { time: '시간대', day: '요일' } as const;

/** 발 문구 넷(목업 글자 그대로). 둘째는 굵게. */
export const POP_NOTES = {
  source:
    '출처: 서울시 상권분석서비스 「상권-길단위인구」·「상권-상주인구」·「상권-직장인구」(열린데이터광장 · 공공누리 1유형).',
  notBuilding: '이 상권 전체의 값이며 이 건물의 값이 아닙니다.',
  method:
    '길단위인구는 서울시·KT 생활인구를 10m 길 단위로 나눈 값의 3개월 합입니다(서울시 칸 이름은 「유동인구」). 사는 사람은 주민등록, 일하는 사람은 통신사 자료를 바탕으로 서울시가 셉니다.',
  yearly: '사는 사람·일하는 사람은 서울시가 1년에 한 번 바꿉니다 — 「YYYY년 기준」은 값이 마지막으로 바뀐 해입니다.',
} as const;

/** 상권 줄인데 셋 다 없음(no_data). */
export const POP_NO_DATA_TEXT = '서울시가 이 상권의 인구 자료를 내지 않았습니다.';
