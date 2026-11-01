import type { NearbySubway, NearbySubwayBins } from '../types';
import { formatCount } from './districtSales';
import type { FlowBars } from './districtPop';

/**
 * 「상권 인구 (서울시 공표)」 카드 안 넷째 덩이 — 가까운 지하철역 승하차(결정 0045 PR⑥)의 **순수 계산**만 모은다
 * (컴포넌트에 계산 0).
 *
 * ⛔ **서버 값 그대로다.** 하루 평균 승차·하차와 시간대 여섯 칸은 서버(`list_nearby_subway`)가 낸 정수 그대로 적는다 —
 *    반올림·더하기·나누기를 다시 하지 않는다. 여기서 하는 산수는 미니 막대의 **높이**(그 역 여섯 칸 최댓값에 대한 비례)와
 *    막대 한 칸의 값(승차 + 하차 — 높이만 정한다)뿐이다.
 * ⛔ **역 승하차 수이지 이 건물의 값이 아니다.** 건물 앞을 지나는 사람 수로 읽히는 낱말을 쓰지 않는다.
 * ⛔ **달·연도 글자를 박지 않는다.** 기간 글은 서버의 `window_from`·`window_to`('YYYYMM')에서 만든다.
 * ⓘ 역은 서버가 묶은 그대로(역 이름 · 600m 안) — 화면은 다시 묶지 않는다(👤 Q1 「가」).
 */

// ── 모양 검사 ───────────────────────────────────────────────────────────────

export const SUBWAY_STATUSES = ['no_coord', 'not_seoul', 'no_data', 'no_station', 'ok'] as const;

/** 시간대 여섯 칸(차례 = 화면 막대 차례)과 막대 아래 글. */
export const SUBWAY_BIN_KEYS = [
  ['h04_07', '4~7'],
  ['h07_10', '7~10'],
  ['h10_14', '10~14'],
  ['h14_17', '14~17'],
  ['h17_21', '17~21'],
  ['h21_04', '21~'],
] as const satisfies readonly (readonly [keyof NearbySubwayBins, string])[];

function isCount(x: unknown): x is number {
  return typeof x === 'number' && Number.isInteger(x) && x >= 0;
}

function isYm(x: unknown): x is string {
  if (typeof x !== 'string' || !/^\d{6}$/.test(x)) return false;
  const m = Number(x.slice(4));
  return m >= 1 && m <= 12;
}

function isLineList(x: unknown): x is string[] {
  return Array.isArray(x) && x.length > 0 && x.every((s) => typeof s === 'string' && s.trim() !== '');
}

function isBins(x: unknown): x is NearbySubwayBins {
  if (typeof x !== 'object' || x === null || Array.isArray(x)) return false;
  const r = x as Record<string, unknown>;
  return SUBWAY_BIN_KEYS.every(([k]) => {
    const v = r[k];
    if (typeof v !== 'object' || v === null || Array.isArray(v)) return false;
    const b = v as Record<string, unknown>;
    return isCount(b.on) && isCount(b.off);
  });
}

function isOkRow(r: Record<string, unknown>): boolean {
  if (typeof r.station_nm !== 'string' || r.station_nm.trim() === '') return false;
  if (!isLineList(r.lines)) return false;
  if (!isCount(r.dist_m) || (r.dist_m as number) > 500) return false;
  if (typeof r.has_data !== 'boolean') return false;
  if (r.has_data) {
    if (!isLineList(r.lines_with_data)) return false;
    const lines = r.lines as string[];
    if (!(r.lines_with_data as string[]).every((l) => lines.includes(l))) return false;
    if (!isCount(r.on_daily) || !isCount(r.off_daily)) return false;
    if (!isCount(r.months_n) || (r.months_n as number) < 1 || (r.months_n as number) > 12) return false;
    if (!isYm(r.window_from) || !isYm(r.window_to)) return false;
    return isBins(r.bins);
  }
  // 자료 없는 묶음 — 숫자 넷(승차·하차·시간대·자료 있는 호선)은 없다.
  const noLines =
    r.lines_with_data === null ||
    r.lines_with_data === undefined ||
    (Array.isArray(r.lines_with_data) && r.lines_with_data.length === 0);
  const empty = (v: unknown) => v === null || v === undefined;
  return noLines && empty(r.on_daily) && empty(r.off_daily) && empty(r.bins);
}

function isNoStationRow(r: Record<string, unknown>): boolean {
  const empty = (v: unknown) => v === null || v === undefined;
  if (empty(r.nearest_nm) && empty(r.nearest_lines) && empty(r.nearest_dist_m)) return true;
  return (
    typeof r.nearest_nm === 'string' &&
    r.nearest_nm.trim() !== '' &&
    isLineList(r.nearest_lines) &&
    isCount(r.nearest_dist_m) &&
    (r.nearest_dist_m as number) >= 500 && // 서버가 round 하므로 500.0~500.5m 는 500 — 경계 허용(맹점 검사 11-02)
    (r.nearest_dist_m as number) <= 1500
  );
}

function isSubwayRow(x: unknown): x is NearbySubway {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  if (typeof r.status !== 'string' || !(SUBWAY_STATUSES as readonly string[]).includes(r.status)) return false;
  if (r.status === 'ok') return isOkRow(r);
  if (r.status === 'no_station') return isNoStationRow(r);
  return true;
}

/**
 * 서버 응답(`list_nearby_subway`)의 **모양**을 본다. 하나라도 어긋나면 false → 덩이가 빠진다(카드는 그대로 · 콘솔 경고만).
 * ⛔ 빈 배열 · 섞인 답(빈 상태 줄은 한 줄뿐이다 — ok 줄과 섞이거나 둘 이상이면) · 이상한 줄 하나 → 통째로 거부.
 */
export function isNearbySubwayList(x: unknown): x is NearbySubway[] {
  if (!Array.isArray(x) || x.length === 0 || !x.every(isSubwayRow)) return false;
  const rows = x as NearbySubway[];
  const heads = rows.filter((r) => r.status !== 'ok');
  return heads.length === 0 || rows.length === 1;
}

/** 덩이를 그리는 답인가 — ok 줄(역 1곳 이상) 또는 no_station 한 줄. no_data·no_coord·not_seoul 은 덩이 없음. */
export function subwayShows(rows: readonly NearbySubway[] | null): boolean {
  if (!rows || rows.length === 0) return false;
  return rows.every((r) => r.status === 'ok') || (rows.length === 1 && rows[0].status === 'no_station');
}

// ── 역 이름 줄 ───────────────────────────────────────────────────────────────

const NUMBERED_LINE = /^(\d+)호선$/;

/** 호선 이름들 → 「3·4호선 · 신분당선」 조각들(「N호선」은 숫자만 모아 하나로 · 그 밖은 이름 그대로 · 차례 유지). */
function linePieces(lines: readonly string[]): string[] {
  const nums: number[] = [];
  const others: string[] = [];
  for (const l of lines) {
    const m = NUMBERED_LINE.exec(l);
    if (m) {
      if (!nums.includes(Number(m[1]))) nums.push(Number(m[1]));
    } else if (!others.includes(l)) {
      others.push(l);
    }
  }
  nums.sort((a, b) => a - b);
  return [...(nums.length > 0 ? [`${nums.join('·')}호선`] : []), ...others];
}

/** 호선 글 — 자료 있는 호선 먼저, 자료 없는 호선은 「(자료 없음)」 꼬리. 전부 자료 없으면 꼬리 없이 이름만. */
function linesText(lines: readonly string[], withData: readonly string[] | null): string {
  const data = withData ?? [];
  if (data.length === 0) return linePieces(lines).join(' · ');
  const has = lines.filter((l) => data.includes(l));
  const none = lines.filter((l) => !data.includes(l));
  return [...linePieces(has), ...linePieces(none).map((p) => `${p}${SUBWAY_NO_DATA_TAIL}`)].join(' · ');
}

/** 「충무로」 + 작은 글 「3·4호선 · 180m」(자료 없는 호선은 「신분당선(자료 없음)」). */
export function subwayStationLine(row: NearbySubway): { name: string; sub: string } {
  const lines = linesText(row.lines ?? [], row.has_data ? row.lines_with_data : null);
  return { name: row.station_nm ?? '', sub: `${lines} · ${formatCount(row.dist_m, 'm')}` };
}

// ── 숫자 줄 ─────────────────────────────────────────────────────────────────

function ymText(ym: string | null): string {
  if (!ym || !isYm(ym)) return '';
  return `${ym.slice(0, 4)}년 ${Number(ym.slice(4))}월`;
}

export type SubwayNumbers =
  | { on: string; off: string; tail: string; period: string }
  | { none: string };

/**
 * 숫자 줄 — 자료가 있으면 「승차 31,600」·「하차 32,300」 + 「하루 평균」 + 기간 글(창 12개월이면 「최근 12개월(… ~ …) 평균」,
 * 모자라면 「8개월 평균(… ~ … 중 자료 있는 달)」 — 달 글은 서버 창에서). 자료가 없으면 「승하차 자료 없음 — 서울시 자료 밖 노선」.
 */
export function subwayNumbers(row: NearbySubway): SubwayNumbers {
  if (!row.has_data) return { none: SUBWAY_NONE_TEXT };
  const range = `${ymText(row.window_from)}~${ymText(row.window_to)}`;
  const n = row.months_n ?? 0;
  const period = n >= 12 ? `최근 ${n}개월(${range}) 평균` : `${n}개월 평균(${range} 중 자료 있는 달)`;
  return {
    on: `승차 ${formatCount(row.on_daily, '')}`,
    off: `하차 ${formatCount(row.off_daily, '')}`,
    tail: SUBWAY_DAILY_TAIL,
    period,
  };
}

// ── 시간대 막대 ─────────────────────────────────────────────────────────────

/**
 * 시간대 여섯 칸 미니 막대 — 칸 값 = 그 시간대 승차 + 하차(높이만 정한다) · 높이 = 값 ÷ 여섯 칸 최댓값 ·
 * 읽어 주기 글 「4~7 승차 1,200 · 하차 900」(서버 값 그대로). 자료가 없으면 null.
 */
export function subwayBars(row: NearbySubway): FlowBars | null {
  const b = row.bins;
  if (!row.has_data || !b) return null;
  const values = SUBWAY_BIN_KEYS.map(([k]) => b[k].on + b[k].off);
  const max = Math.max(0, ...values);
  return {
    bars: SUBWAY_BIN_KEYS.map(([k, tick], i) => ({
      key: k,
      tick,
      value: values[i],
      h: max > 0 ? (values[i] / max) * 100 : 0,
      label: `${tick} 승차 ${formatCount(b[k].on, '')} · 하차 ${formatCount(b[k].off, '')}`,
    })),
    max,
    scale: max > 0 ? `꽉 차면 ${formatCount(max, '명')}(${SUBWAY_DAILY_TAIL} 승하차)` : null,
  };
}

// ── 500m 안 역 0 ────────────────────────────────────────────────────────────

/** 「500m 안에 지하철역이 없습니다」 + (1.5km 안에 역이 있으면) 「가장 가까운 역: 수유 (4호선) · 820m」. */
export function subwayNoStationText(row: NearbySubway): { main: string; nearest: string | null } {
  const nearest =
    row.nearest_nm && row.nearest_lines && row.nearest_dist_m !== null && row.nearest_dist_m !== undefined
      ? `가장 가까운 역: ${row.nearest_nm} (${linePieces(row.nearest_lines).join(' · ')}) · ${formatCount(row.nearest_dist_m, 'm')}`
      : null;
  return { main: SUBWAY_NO_STATION_TEXT, nearest };
}

// ── 접힌 요약 꼬리 ───────────────────────────────────────────────────────────

/** 접힌 요약 뒤에 붙는 꼬리 — 역 수만(승하차 값 0). 덩이를 안 그리는 답이면 null. */
export function subwaySummaryTail(rows: readonly NearbySubway[] | null): string | null {
  if (!subwayShows(rows)) return null;
  const ok = rows!.filter((r) => r.status === 'ok').length;
  return ok > 0 ? `500m 안 지하철역 ${ok}곳` : '500m 안 지하철역 없음';
}

// ── 글(시안 글자 그대로) ─────────────────────────────────────────────────────

export const SUBWAY_CHUNK_TITLE = '가까운 지하철역 승하차 인원 (카드 기준 · 건물 500m 안)';
export const SUBWAY_BADGE = 'A등급 · 카드 실측 집계';
export const SUBWAY_DAILY_TAIL = '하루 평균';
export const SUBWAY_NO_DATA_TAIL = '(자료 없음)';
export const SUBWAY_NONE_TEXT = '승하차 자료 없음 — 서울시 자료 밖 노선';
export const SUBWAY_NO_STATION_TEXT = '500m 안에 지하철역이 없습니다';

/** 발 문구 넷. ②는 [앞, 굵게, 뒤] · ④는 통째로 굵게. */
export const SUBWAY_NOTES = {
  source: '출처: 서울시 「지하철 호선별 역별 시간대별 승하차 인원」·「역사마스터」(열린데이터광장 · 공공누리 1유형).',
  count: ['교통카드(1회용 포함)를 찍은 ', '승차 수와 하차 수', '입니다 — 한 사람이 타고 내리면 승차 1·하차 1로 셉니다 · 시간대 막대는 승차와 하차를 더한 값입니다.'],
  transfer:
    '환승역은 서울시가 관리 호선 한 줄에 몰아 세기도 해 역 이름으로 합쳐 보여 줍니다 · 환승 통로로 갈아탄 사람은 개찰을 안 지나 안 셉니다.',
  notBuilding: '역 승하차 수이지 이 건물 앞을 지나는 사람 수가 아니고, 이 건물의 값이 아닙니다.',
} as const satisfies { source: string; count: readonly [string, string, string]; transfer: string; notBuilding: string };
