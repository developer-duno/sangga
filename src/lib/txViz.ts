/**
 * 실거래 기록 카드의 그림 두 벌(결정 0038 B · V2) — 값을 자리(%)·모양으로 바꾸는 순수 함수만 둔다.
 *
 *  ① 구 층대별 단가 띠 — 층대 줄마다 p25~p75 가로 띠 + 가운데값 세로 눈금 · 축 = 0 ~ 그 블록 최댓값 올림(`niceCeil`).
 *     내린 참고 시세 띠(A · 결정 0041)와 **좌표 함수만** 공유하고 색은 사실 색(호박)이다(§2-6).
 *  ② 이 땅 거래 점그림 — 세로 = ㎡당 단가 · 가로 = 계약 시기 · 점 모양 = 층 묶음 · 지분 = 같은 꼴의 빈 꼴.
 *     목록의 거래가 `TX_PLOT_MIN` 건 이상일 때만 선다.
 *
 * 지키는 것(viz.ts 와 같다): DOM 을 재지 않는다(전부 %) · 없는 값은 0 으로 그리지 않는다(그 점·그 띠를 빼고 null/`none`) ·
 * 비율을 글자로 내지 않는다(여기 숫자는 자리에만 쓴다 · 결정 0033).
 *
 * 못 보는 것: 같은 달·같은 단가 거래는 점이 겹친다(점 수 ≠ 거래 수 — 거래 수는 목록 제목이 말한다).
 *   한 거래의 ㎡당 단가가 나머지보다 열 배쯤 크면 나머지 점이 바닥에 몰린다(축은 그림에 하나 — §2-7).
 */
import { TX_MIN_SAMPLE } from './appConstants';
import type { ParcelTransaction, SigunguTxStat } from '../types';
import { niceCeil, pctOf, rangePct } from './viz';

// ── ① 구 층대별 단가 띠 ─────────────────────────────────────────────────────────

/** 층대 줄이 값을 내나 — 화면 글과 같은 문턱(표본 `TX_MIN_SAMPLE` 건 이상) + 가운데값이 있어야 한다. */
function statShowsValue(s: SigunguTxStat): boolean {
  return s.n >= TX_MIN_SAMPLE && s.median_unit_price !== null;
}

/**
 * 블록 축 상한(㎡당 원) — 값을 내는 줄의 p75·가운데값 가운데 가장 큰 값을 **만원 단위로** `niceCeil` 올린 값.
 * 예: p75 최대 3,730만 → 5,000만. 값을 내는 줄이 하나도 없으면 null(축·띠를 그리지 않는다).
 */
export function txBandAxisMaxWon(stats: SigunguTxStat[]): number | null {
  let top = 0;
  for (const s of stats) {
    if (!statShowsValue(s)) continue;
    top = Math.max(top, s.median_unit_price as number, s.p75_unit_price ?? 0);
  }
  const man = niceCeil(top / 10_000);
  return man === null ? null : man * 10_000;
}

/** 한 줄의 그림 — 띠(p25~p75) + 가운데값 눈금 · 눈금만(사분위가 없거나 폭 0) · 없음("–"). 자리·폭은 축 0~상한 위 %. */
export type TxBandMark =
  | { kind: 'none' }
  | { kind: 'tick'; x: number }
  | { kind: 'band'; left: number; width: number; x: number };

/**
 * 층대 줄 하나 → 그림. 표본 부족·가운데값 없음은 `none`(띠 없이 "–" — 까닭 글 「표본 부족」은 옆에 그대로 · §2-4 0 으로 안 그린다).
 * p25·p75 가 없거나 p25 > p75·같은 값이면 띠 없이 눈금만(폭 0 띠를 최소 폭으로 키우지 않는다).
 */
export function txBandMark(s: SigunguTxStat, maxWon: number | null): TxBandMark {
  if (!statShowsValue(s)) return { kind: 'none' };
  const x = pctOf(s.median_unit_price, maxWon);
  if (x === null) return { kind: 'none' };
  const r = rangePct(s.p25_unit_price, s.p75_unit_price, maxWon);
  if (r === null || r.width <= 0) return { kind: 'tick', x };
  return { kind: 'band', left: r.left, width: r.width, x };
}

// ── ② 이 땅 거래 점그림 ─────────────────────────────────────────────────────────

/**
 * 점그림이 서는 거래 수 — 목록에 있는 거래 수(지분 포함 · 층 미상 포함)가 이 수 이상일 때만.
 * ⓘ `TX_MIN_SAMPLE` 과 **같은 수**지만 뜻이 다르다 — 통계를 감추는 문턱이 아니라 "낱건이 이만큼 쌓였다"(결정 0038 B).
 */
export const TX_PLOT_MIN = TX_MIN_SAMPLE;

/** 목록의 거래 수가 문턱 이상인가. */
export function txPlotShows(txs: ParcelTransaction[]): boolean {
  return txs.length >= TX_PLOT_MIN;
}

/** 층 묶음 다섯 — 지하 · 1층 · 2층 · 3층 이상(옥탑 99 포함) · 층 미상. */
export type TxShape = 'b' | '1' | '2' | '3+' | 'na';

/** 층 번호 → 층 묶음. null·0·숫자 아님 = 층 미상(0 은 쓰지 않는 값이라 지하로도 지상으로도 세지 않는다 · 절대 규칙 4). */
export function txShape(floorNo: number | null | undefined): TxShape {
  if (typeof floorNo !== 'number' || !Number.isFinite(floorNo) || floorNo === 0) return 'na';
  if (floorNo < 0) return 'b';
  if (floorNo === 1) return '1';
  if (floorNo === 2) return '2';
  return '3+';
}

/** 범례 차례와 글(결정 0038 B · 메인 해석 2026-10-21 — 보통 거래 = 속 찬 꼴 · 지분 = 같은 꼴의 빈 꼴). */
export const TX_SHAPE_ORDER: readonly TxShape[] = ['1', '2', '3+', 'b', 'na'];
export const TX_SHAPE_LABEL: Record<TxShape, string> = {
  '1': '1층',
  '2': '2층',
  '3+': '3층 이상',
  b: '지하',
  na: '층 미상',
};

/** 'YYYYMM' → 달 번호(연 × 12 + 월 − 1). 못 읽으면 null. */
function monthIndex(ym: string | null | undefined): number | null {
  if (!ym) return null;
  const m = /^(\d{4})(\d{2})$/.exec(ym.trim());
  if (!m) return null;
  const month = Number(m[2]);
  if (month < 1 || month > 12) return null;
  return Number(m[1]) * 12 + month - 1;
}

export type TxPlotPoint = {
  /** 가로 자리(%) — 가장 이른 계약 달 = 0 · 가장 늦은 달 = 100 · 달이 하나뿐이면 50. */
  x: number;
  /** 세로 자리(%) — 아래(0) = ㎡당 0 · 위(100) = 축 상한. */
  y: number;
  shape: TxShape;
  /** 지분 거래 — 같은 꼴의 빈 꼴로 그린다(값은 그대로 · §7 지분 ㎡당 약 0.39배). */
  hollow: boolean;
};

export type TxPlot = {
  points: TxPlotPoint[];
  /** 세로 축 상한(㎡당 원). */
  yMaxWon: number;
  /** 가로 축 양 끝 계약 달(원본 'YYYYMM'). */
  fromYm: string;
  toYm: string;
  /** 점이 없는 거래 수 — ㎡당 단가가 없거나(면적 없음) 계약 달을 못 읽은 것(0 으로 찍지 않는다). */
  skipped: number;
  /** 그려진 층 묶음(범례 차례대로) · 빈 꼴(지분)이 하나라도 있나. */
  shapes: TxShape[];
  hasHollow: boolean;
};

/**
 * 거래 목록 → 점그림. 목록이 `TX_PLOT_MIN` 건 미만이거나 찍을 점이 하나도 없으면 null(그림을 안 그린다).
 * ㎡당 단가가 없거나 0 이하·계약 달을 못 읽은 거래는 점을 빼고 `skipped` 로 센다.
 */
export function txPlot(txs: ParcelTransaction[]): TxPlot | null {
  if (!txPlotShows(txs)) return null;
  const drawable: Array<{ t: ParcelTransaction; idx: number; price: number }> = [];
  let skipped = 0;
  for (const t of txs) {
    const idx = monthIndex(t.contract_ym);
    const price = t.unit_price;
    if (idx === null || typeof price !== 'number' || !Number.isFinite(price) || price <= 0) {
      skipped += 1;
      continue;
    }
    drawable.push({ t, idx, price });
  }
  if (drawable.length === 0) return null;

  const man = niceCeil(Math.max(...drawable.map((d) => d.price)) / 10_000);
  if (man === null) return null;
  const yMaxWon = man * 10_000;
  const lo = Math.min(...drawable.map((d) => d.idx));
  const hi = Math.max(...drawable.map((d) => d.idx));

  const points: TxPlotPoint[] = drawable.map((d) => ({
    x: hi === lo ? 50 : (pctOf(d.idx - lo, hi - lo) as number),
    y: pctOf(d.price, yMaxWon) as number,
    shape: txShape(d.t.floor_no),
    hollow: d.t.is_share === true,
  }));
  const seen = new Set(points.map((p) => p.shape));
  return {
    points,
    yMaxWon,
    fromYm: drawable.find((d) => d.idx === lo)!.t.contract_ym,
    toYm: drawable.find((d) => d.idx === hi)!.t.contract_ym,
    skipped,
    shapes: TX_SHAPE_ORDER.filter((s) => seen.has(s)),
    hasHollow: points.some((p) => p.hollow),
  };
}
