import type { RentStat, RentStatHistory } from '../types';
import { rentKeysOf } from './floorGap';
import { floorRentLines, formatRate, formatRentPerM2, quarterLabel } from './rentStats';
import { niceCeil, pctOf } from './viz';

/**
 * 상권 임대 동향 카드의 그림 두 가지 — **순수 계산**만(결정 0038 C · V5 · 👤 2026-10-17 「나」).
 *
 *  ① 계단 막대 — 층별 ㎡당 월 임대료 표의 줄마다 그 값에 비례한 막대(`rentStepWidths`).
 *  ② 8분기 흐름 — 공실률 · ㎡당 임대료 · 투자수익률 작은 그림 셋, **그림마다 제 눈금**(`rentTrend`).
 *
 * 지키는 것(결정 0038 §2):
 *  · 상권 평균이다 — 이 건물·이 층의 값이 아니다(그림도 카드 안 「이 건물 값이 아님」 머리 아래에만 선다 · 절대 규칙 5).
 *  · 길이는 값에 비례할 뿐 — 비율·나누기를 **글자로** 내지 않는다(결정 0031 · 0036 결정 15). 여기 숫자는 폭·높이(%)에만 쓴다.
 *  · 없는 분기는 0 으로 그리지 않는다 — `null` 막대(화면은 "–") · 0 과 음수는 값이다(그대로 그린다).
 *  · 종류(bld_type)를 섞지 않는다 — 흐름은 카드 줄과 **같은 조사구역 · 같은 종류**의 분기들뿐.
 *  · DOM 을 재지 않는다 — 전부 % (접힌 카드는 폭이 0 · 종이 백지 · §2-3).
 */

// ── ① 계단 막대 ───────────────────────────────────────────────────────────────

/** 층 구간의 대표 층 — 높은 층부터(표 차례와 같다). 열쇠 고르기는 세 잣대의 `rentKeysOf` 를 그대로 쓴다. */
const STEP_FLOORS = [11, 6, 5, 4, 3, 2, 1, -1] as const;

/**
 * 층별 표의 열쇠마다 계단 막대 폭(%) — 이 표에서 가장 비싼 구간이 100.
 *
 * ⓘ 열쇠 겹침(`6+` · `6-10` · `11+`)은 세 잣대와 **같은 대체 규칙**(`floorGap.ts` 의 `rentKeysOf` — 6~10층 = `6-10` →
 *   없으면 `6+` · 11층 이상 = `11+` → 없으면 `6+`)으로 고른다. 세 열쇠가 다 있으면 `6+` 는 어느 층도 쓰지 않으므로
 *   그 줄엔 막대가 없다(줄의 글은 그대로). 운영 자료에서 `6+` 와 `6-10`·`11+` 가 한 줄에 함께 온 적은 없다(2026-10-24 실측).
 * ⛔ 0 이하·숫자 아님·모르는 열쇠는 `floorRentLines` 가 이미 뺀다 — 여기도 그 줄만 본다(표와 같은 줄).
 */
export function rentStepWidths(floorRent: unknown): Map<string, number> {
  const out = new Map<string, number>();
  const lines = floorRentLines(floorRent);
  if (lines.length === 0) return out;
  const src = floorRent as Record<string, number>;
  const present = new Set(lines.map((l) => l.key));
  const chosen: string[] = [];
  for (const floorNo of STEP_FLOORS) {
    const key = rentKeysOf(floorNo).find((k) => present.has(k));
    if (key !== undefined && !chosen.includes(key)) chosen.push(key);
  }
  const max = Math.max(...chosen.map((k) => src[k]));
  for (const k of chosen) {
    const w = pctOf(src[k], max);
    if (w !== null) out.set(k, w);
  }
  return out;
}

// ── ② 8분기 흐름 ──────────────────────────────────────────────────────────────

/** 흐름 창 — 카드 줄의 분기까지 최근 8분기(👤 결정 C 「8분기 흐름」). */
export const RENT_TREND_QUARTERS = 8;

/** 빠진 분기 표기(막대 자리). */
export const TREND_GAP = '–';

/** 까닭 한 줄(§2-4 — 결측은 값이지 경고가 아니다). */
export const TREND_GAP_NOTE = '‘–’ = 그 분기에 부동산원이 이 값을 공표하지 않았습니다(0 이 아닙니다).';

/**
 * 분기 `anchor` 까지 `n` 분기 — 옛 분기 → 최근 차례('2026Q2', 8 → ['2024Q3', … '2026Q2']). 못 읽으면 null.
 */
export function quarterSeq(anchor: string | null | undefined, n: number): string[] | null {
  const m = anchor ? /^(\d{4})Q([1-4])$/.exec(anchor.trim()) : null;
  if (!m || !Number.isInteger(n) || n < 1) return null;
  let idx = Number(m[1]) * 4 + (Number(m[2]) - 1);
  const out: string[] = [];
  for (let i = 0; i < n; i += 1, idx -= 1) out.unshift(`${Math.floor(idx / 4)}Q${(idx % 4) + 1}`);
  return out;
}

type MetricKey = 'vacancy' | 'rent' | 'yield';

/** 그림 셋 — 차례 고정(공실률 · ㎡당 임대료 · 투자수익률). 라벨은 카드 줄의 지표 글과 같은 말. */
const TREND_METRICS: ReadonlyArray<{
  key: MetricKey;
  label: string;
  pick: (r: RentStatHistory) => number | null;
  fmt: (v: number) => string | null;
}> = [
  { key: 'vacancy', label: '공실률', pick: (r) => r.vacancy_rate, fmt: formatRate },
  { key: 'rent', label: '㎡당 임대료', pick: (r) => r.rent_per_m2, fmt: formatRentPerM2 },
  { key: 'yield', label: '투자수익률(분기)', pick: (r) => r.yield_rate, fmt: formatRate },
];

/** 막대 하나 — 값이 없으면(`geom` null) 화면은 "–". `bottom`·`height` 는 그림 높이의 %. */
export type TrendBar = {
  quarter: string;
  /** '2026년 2분기'. */
  label: string;
  /** 사람 말 값('6.74%') · 없으면 null. */
  text: string | null;
  geom: { bottom: number; height: number; neg: boolean } | null;
};

export type TrendChart = {
  key: MetricKey;
  label: string;
  /** 눈금 글('눈금 0 ~ 10%' · 음수가 있으면 '눈금 -2% ~ 4%'). */
  scale: string;
  /** 0 선 자리(그림 높이의 % · 아래에서). 음수가 없으면 0. */
  zero: number;
  bars: TrendBar[];
  /** 읽어 주는 기기용 — 분기마다 값(옆 글에 없는 내용이라 그림 이름으로 단다 · §2-1). */
  aria: string;
};

export type RentTrend = {
  /** 창의 첫·끝 분기 이름('2024년 3분기' · '2026년 2분기'). */
  first: string;
  last: string;
  charts: TrendChart[];
  /** 빠진 분기가 하나라도 있다(→ 까닭 한 줄). */
  hasGap: boolean;
};

/**
 * 값들 → 막대 자리(그림마다 제 눈금 · §2-7 한 눈금에 자료 하나).
 *
 * 위 끝 = 양수 최댓값의 '보기 좋은 수'(`niceCeil`) · 음수가 있으면 아래 끝 = 음수 크기의 '보기 좋은 수' — 0 선은 그 사이.
 * 막대 길이 = |값| ÷ (위 끝 + 아래 끝) × 100 — 0 선에서 위(양수)·아래(음수)로.
 * ⓘ 값이 전부 0 이면 눈금 폭이 없어 막대 높이가 모두 0 이다(0 선만 — 0 은 값이라 "–" 가 아니다).
 */
export function trendGeometry(values: ReadonlyArray<number | null>): {
  top: number;
  bottom: number;
  zero: number;
  bars: Array<{ bottom: number; height: number; neg: boolean } | null>;
} {
  const nums = values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  const top = niceCeil(Math.max(0, ...nums)) ?? 0;
  const bottom = niceCeil(Math.max(0, ...nums.map((v) => -v))) ?? 0;
  const span = top + bottom;
  const zero = span > 0 ? (bottom / span) * 100 : 0;
  const bars = values.map((v) => {
    if (typeof v !== 'number' || !Number.isFinite(v)) return null;
    const h = span > 0 ? (Math.abs(v) / span) * 100 : 0;
    return v < 0 ? { bottom: zero - h, height: h, neg: true } : { bottom: zero, height: h, neg: false };
  });
  return { top, bottom, zero, bars };
}

function scaleText(top: number, bottom: number, fmt: (v: number) => string | null): string {
  if (top === 0 && bottom === 0) return `눈금 없음 — 모든 분기 ${fmt(0) ?? '0'}`;
  const hi = top > 0 ? (fmt(top) ?? String(top)) : (fmt(0) ?? '0');
  const lo = bottom > 0 ? (fmt(-bottom) ?? String(-bottom)) : '0';
  return `눈금 ${lo} ~ ${hi}`;
}

function sameNum(a: number | null | undefined, b: number | null | undefined): boolean {
  return (a ?? null) === (b ?? null);
}

/**
 * 카드 줄 하나(조사구역 × 종류의 최신 분기 — `list_rent_stats`)의 8분기 흐름. 그릴 수 없으면 **null**(카드는 그대로 선다).
 *
 * null 이 되는 경우(전부 조용히 — 실패를 '없음'으로 적지 않는다):
 *  · 흐름 응답이 없다(못 받음 · 함수 없음 · 모양 이상) · 카드 줄의 분기를 못 읽는다.
 *  · 같은 (조사구역, 종류, 분기)가 둘 — 어느 쪽인지 고를 근거가 없다(운영 실측 0 · 2026-10-24).
 *  · ⛔ **짝 대조** — 흐름의 마지막 분기 줄이 카드 줄과 값이 다르다(공실률 · ㎡당 임대료 · 투자수익률). 다른 조사구역을
 *    짚은 것이라 그리면 카드와 흐름이 서로 다른 상권을 말한다(서버는 같은 길로 찾지만 화면도 한 번 더 본다).
 *  · 창 안에 분기가 둘도 안 된다(흐름이 아니다).
 * ⓘ 한 지표가 8분기 내내 없으면 그 그림만 뺀다.
 */
export function rentTrend(
  history: readonly RentStatHistory[] | null,
  stat: RentStat | undefined,
): RentTrend | null {
  if (!history || !stat) return null;
  const quarters = quarterSeq(stat.quarter, RENT_TREND_QUARTERS);
  if (!quarters) return null;

  const byQuarter = new Map<string, RentStatHistory>();
  for (const h of history) {
    if (h.rone_region_nm !== stat.rone_region_nm || h.bld_type !== stat.bld_type) continue;
    if (byQuarter.has(h.quarter)) return null;
    byQuarter.set(h.quarter, h);
  }
  const latest = byQuarter.get(stat.quarter);
  if (
    !latest ||
    !sameNum(latest.vacancy_rate, stat.vacancy_rate) ||
    !sameNum(latest.rent_per_m2, stat.rent_per_m2) ||
    !sameNum(latest.yield_rate, stat.yield_rate)
  ) {
    return null;
  }
  const rowsInWindow = quarters.map((q) => byQuarter.get(q) ?? null);
  if (rowsInWindow.filter((r) => r !== null).length < 2) return null;

  const charts: TrendChart[] = [];
  for (const m of TREND_METRICS) {
    const values = rowsInWindow.map((r) => {
      const v = r ? m.pick(r) : null;
      return typeof v === 'number' && Number.isFinite(v) ? v : null;
    });
    if (values.every((v) => v === null)) continue;
    const g = trendGeometry(values);
    const bars: TrendBar[] = quarters.map((q, i) => {
      const v = values[i];
      return {
        quarter: q,
        label: quarterLabel(q) ?? q,
        text: v === null ? null : m.fmt(v),
        geom: g.bars[i],
      };
    });
    const aria = `${m.label} 최근 ${RENT_TREND_QUARTERS}분기(옛 분기부터): ${bars
      .map((b) => `${b.label} ${b.text ?? '공표값 없음'}`)
      .join(' · ')}`;
    charts.push({ key: m.key, label: m.label, scale: scaleText(g.top, g.bottom, m.fmt), zero: g.zero, bars, aria });
  }
  if (charts.length === 0) return null;

  return {
    first: quarterLabel(quarters[0]) ?? quarters[0],
    last: quarterLabel(quarters[quarters.length - 1]) ?? quarters[quarters.length - 1],
    charts,
    hasGap: charts.some((c) => c.bars.some((b) => b.geom === null)),
  };
}

function isNullableNumber(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'number';
}

/** 흐름 응답 한 줄의 모양. */
export function isRentHistoryRow(x: unknown): x is RentStatHistory {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return (
    typeof r.rone_region_nm === 'string' &&
    typeof r.bld_type === 'string' &&
    typeof r.quarter === 'string' &&
    isNullableNumber(r.vacancy_rate) &&
    isNullableNumber(r.rent_per_m2) &&
    isNullableNumber(r.yield_rate) &&
    isNullableNumber(r.income_yield_rate)
  );
}

/**
 * 흐름 응답 전체의 모양 — 한 줄이라도 이상하면 통째로 거부한다(흐름은 덤이라 버려도 카드는 선다 · 반쪽 흐름을 그리지 않는다).
 * ⓘ 빈 배열은 모양으로는 정상이다(조사 대상이 아닌 자리) — 그때 `rentTrend` 가 짝을 못 찾아 null 이 된다.
 */
export function isRentHistoryList(x: unknown): x is RentStatHistory[] {
  return Array.isArray(x) && x.every(isRentHistoryRow);
}
