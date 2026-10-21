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
 * 보완 1(👤 2026-10-21 「점 옆에 금액」): 점마다 ㎡당 금액 글자 · 같은 달·같은 값·같은 꼴은 점 하나 + 「×N」 ·
 *   몰린 글자는 비켜 적고 그래도 모자라면 묶음 글자 · 가로 눈금 넷(축 상한 4칸).
 *
 * 못 보는 것: 한 거래의 ㎡당 단가가 나머지보다 열 배쯤 크면 나머지 점이 바닥에 몰린다(축은 그림에 하나 — §2-7).
 *   비켜 적은 글자는 제 점에서 위아래로 떨어질 수 있다(이은 선은 없다 — 가로 자리는 늘 제 점 옆).
 */
import { TX_MIN_SAMPLE } from './appConstants';
import type { ParcelTransaction, SigunguTxStat } from '../types';
import { formatManWon, formatManWonBand } from './format';
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
  /** ㎡당 단가(원). */
  price: number;
  /** 이 점에 겹친 거래 수 — 같은 계약 달 + 같은 ㎡당 값 + 같은 꼴(지분 여부 포함)이면 점 하나로 묶는다(보완 1 F2). */
  n: number;
};

/**
 * 점 금액 글자 하나(보완 1 F1·F3) — 자리는 % 와 고정 px 간격뿐(DOM 을 재지 않는다).
 * 가로: 제 점(`x` %) 오른쪽(`side` 'r' — 점에서 `TX_LABEL_GAP` px)이나 왼쪽('l') · 점 바로 위·아래에 가운데 맞춤('c' · 보완 2) ·
 * 옆 둘 다 칸을 넘으면 칸 왼쪽 끝('L')이나 오른쪽 끝('R')에 붙인다(묶음 글자처럼 긴 글자 · 드물다). 세로: 글자 한가운데가 `y` %(아래 = 0).
 * `box` = 계산에 쓴 기준 폭 공간의 글자 상자(px · 왼쪽·오른쪽·아래·위 — 시험이 겹침 0 을 이 상자로 본다).
 */
export type TxLabel = {
  text: string;
  x: number;
  y: number;
  side: 'r' | 'l' | 'c' | 'L' | 'R';
  /** 제 점(묶음이면 점들의 가운데) 높이에서 비켜난 거리(기준 px · 칸 끝에 막힌 반 줄은 빼고) — `TX_LABEL_MAX_SHIFT` 이하. */
  shift: number;
  box: { x0: number; x1: number; y0: number; y1: number };
};

export type TxPlot = {
  points: TxPlotPoint[];
  /** 세로 축 상한(㎡당 원). */
  yMaxWon: number;
  /** 가로 눈금(보완 1 F4) — 축 상한을 4칸으로: 0 · ¼ · ½ · ¾ · 상한(자리 % · ㎡당 원). */
  ticks: Array<{ y: number; won: number }>;
  /** 점 금액 글자 두 벌 — 넓은 화면·종이용(`wide`)과 휴대폰용(`narrow` · 더 좁은 기준 폭으로 비켜 적음). */
  labels: { wide: TxLabel[]; narrow: TxLabel[] };
  /** 가로 축 양 끝 계약 달(원본 'YYYYMM'). */
  fromYm: string;
  toYm: string;
  /** 점이 없는 거래 수 — ㎡당 단가가 없거나(면적 없음) 계약 달을 못 읽은 것(0 으로 찍지 않는다). */
  skipped: number;
  /** 그려진 층 묶음(범례 차례대로) · 빈 꼴(지분)이 하나라도 있나. */
  shapes: TxShape[];
  hasHollow: boolean;
};

// ── 점 금액 글자 자리(보완 1 · 보완 2) ──────────────────────────────────────────────
//
// 왜 기준 폭 공간인가 — 그림 칸의 실제 폭은 화면마다 다르고 DOM 을 재지 않는다(§2-3). 점의 가로 자리는 % 이고 글자 폭·간격은
// 고정 px 이다. 그래서 '그 꼴의 실제 폭 범위'(가장 좁을 때 ~ 가장 넓을 때) 전체에서 가로가 겹칠 수 있는 짝을 식으로 가려
// 그런 짝만 세로로 비켜 적는다(`mayOverlap`). 세로 칸 높이는 CSS 가 고정 px 로 정하므로 그 값(이하)을 그대로 쓴다.
// 넓은 화면·종이용과 휴대폰용 두 벌을 계산해 CSS 가 고른다.
//
// 보완 2(👤 2026-10-21 운영 사진 유니온오피스텔 휴대폰): ① 글자는 **어느 점도 덮지 않는다**(묶음 안 제 점 포함 — 전에는 점 피하기가
// 덤이라 칸 끝에 붙인 「729만~772만 ×3」이 772만 점을 덮었다) ② 묶음 글자는 **같은 계약 달 안에서만**(전에는 다른 달
// 747만 ×2 와 689만을 한 글자로 묶어 맨 왼쪽 점에 글자가 없었다) — 다른 달끼리는 위·아래·왼쪽·오른쪽으로 비켜 적는다.

/** 글자 줄 높이(px · 13px 글자 + 줄 간격 · CSS `.tx__lab` 의 line-height 와 같다). */
export const TX_LABEL_H = 16;
/** 점 가운데 ~ 글자 가장자리 간격(px · 점 반지름 5 + 틈 · CSS `.tx__lab--r`·`--l` 과 같다). */
export const TX_LABEL_GAP = 7;
/** 점 반지름(px · CSS `.tx__dot` 10px 의 반). */
const DOT = 5;
/** 점 바로 위·아래 글자의 한가운데 ~ 점 한가운데(px) = 반 줄 + 점 반지름 + 1px 틈. */
const ABOVE = TX_LABEL_H / 2 + DOT + 1;
/**
 * 기준 폭 공간(px · 점 칸 `.tx__plot-in` 안쪽) — `w` = 그 꼴에서 가장 좁을 때 이하 · `maxW` = 가장 넓을 때 이상 · `h` = CSS 고정 높이 이하.
 * wide = 721px 이상 화면·종이(가장 좁은 곳 = 1024 두 칸의 오른쪽 칸 488px · 721 한 열 529px · 가장 넓은 곳 = 1023 한 열 약 830px) ·
 * narrow = 휴대폰(412px 전화 220 · 360px 전화 168 — 360 까지 덮는다 · 320 전화(128)는 못 덮는다 · 720px 이 약 530px).
 * 2026-10-21 E2E 실측(점 칸 안쪽 폭) · E2E BX 가 721·1024·360·412 에서 실제 폭 ≥ 기준 폭과 글자 겹침 0 을 다시 잰다.
 * 높이 = CSS `.tx__plot-frame` 칸의 점 칸 안쪽 이하 — 넓은 화면·종이 220px 칸(안쪽 202) → 200 · 휴대폰 340px 칸(안쪽 322 ·
 * `@media screen and (max-width: 720px)` 묶음 · 보완 2 에서 300 → 340) → 320. 글자 한가운데는 % 라 실제 칸이 더 높으면 사이가 벌어지기만 한다.
 */
export const TX_PLOT_REF = {
  wide: { w: 460, maxW: 900, h: 200 },
  narrow: { w: 160, maxW: 560, h: 320 },
} as const;

/**
 * 글자 폭 어림(px · 13px · 숫자는 tabular) — 넉넉하게 잡는다(실제보다 넓게 잡으면 덜 붙을 뿐 겹치지는 않는다).
 * 못 보는 것: 글꼴이 바뀌어 한 글자가 이 어림보다 넓어지면 겹칠 수 있다 — E2E BX 가 실제 상자로 겹침 0 을 다시 본다.
 */
export function txLabelWidth(text: string): number {
  let w = 4;
  for (const ch of text) {
    if (/[0-9]/.test(ch)) w += 8;
    else if (ch === ',' || ch === ' ') w += 4;
    else if (ch === '×' || ch === '~') w += 9;
    else w += 14;
  }
  return w;
}

/** 묶음 글자 — 값 하나면 「260만 ×2」, 여러 값이면 「729만~772만 ×3」(목록·띠와 같은 서식 함수 · 새 서식 0). */
function labelText(prices: number[], n: number): string {
  const lo = Math.min(...prices);
  const hi = Math.max(...prices);
  const body = lo === hi ? formatManWon(lo) : formatManWonBand(lo, hi);
  return n > 1 ? `${body} ×${n}` : body;
}

/** 글자 하나의 씨앗 — 묶인 점들 · 가로 자리(px) · 세로 바람(px) · 비켜 적기 한도 단계(1 = 한 줄 · 보완 2). */
type LabelSeed = { members: number[]; ax: number; ay: number; tier: number };
/** 글자 가로 구간 = [α·폭 + c, α·폭 + c + w] — α = 점 자리 비율(칸 끝에 붙인 글자는 0 또는 1). */
export type TxSpan = { side: TxLabel['side']; alpha: number; c: number; w: number };
type Span = TxSpan;

/**
 * 두 가로 구간이 폭 [minW, maxW] 어디에서든 겹칠 수 있나. 같은 차례로 벌어지기만 하는 짝은 좁은 폭에서만 보면 되지만,
 * 서로 마주 보는 짝(왼쪽 점의 글자는 오른쪽에, 오른쪽 점의 글자는 왼쪽에)은 폭이 늘며 엇갈려 지나가다 겹칠 수 있다 — 그래서 식으로 본다.
 */
export function mayOverlap(a: Span, b: Span, minW: number, maxW: number): boolean {
  const k = b.alpha - a.alpha;
  const p = b.c + b.w - a.c; // b 오른쪽 끝 − a 왼쪽 끝 = k·W + p
  const q = a.c + a.w - b.c; // a 오른쪽 끝 − b 왼쪽 끝 = −k·W + q · 둘 다 양수인 W 가 있으면 겹친다.
  let lo = minW;
  let hi = maxW;
  if (Math.abs(k) < 1e-12) return p > 1e-9 && q > 1e-9;
  if (k > 0) {
    lo = Math.max(lo, -p / k);
    hi = Math.min(hi, q / k);
  } else {
    hi = Math.min(hi, p / -k);
    lo = Math.max(lo, q / k);
  }
  return lo < hi - 1e-9;
}

/**
 * 비켜 적는 한도 한 단계(px) — 글자가 제 점 높이에서 한 줄(`TX_LABEL_H` + 1)보다 멀어지면 남의 점 옆에 앉아 어느 점의 글자인지
 * 헷갈린다(보완 1 휴대폰 사진에서 두 줄로 두었을 때 「280만」이 회색 350만 점 옆에 앉았다). 그래서 한 줄 안에서 먼저 찾고,
 * 못 찾으면 같은 달 묶음 → 묶을 같은 달이 없을 때만 한도를 한 줄씩 늘린다(보완 2 — 다른 달끼리는 묶지 않는다).
 */
export const TX_LABEL_MAX_SHIFT = TX_LABEL_H + 1;

/**
 * 칸 [lo, hi] 안에서 막힌 자리(막는 것의 한가운데 `c` ± 그 거리 `d` 미만 — 다른 글자는 한 줄 + 1px · 점은 반 줄 + 점 반지름 + 1px)를
 * 피해 `want` 에 가장 가까운 한가운데. 없으면 null.
 */
function nearestFree(want: number, blocked: Array<{ c: number; d: number }>, lo: number, hi: number): number | null {
  const cands = [Math.min(hi, Math.max(lo, want)), lo, hi];
  for (const b of blocked) cands.push(b.c - b.d, b.c + b.d);
  let best: number | null = null;
  for (const c of cands) {
    if (c < lo - 1e-9 || c > hi + 1e-9) continue;
    if (blocked.some((b) => Math.abs(c - b.c) < b.d - 1e-9)) continue;
    if (best === null || Math.abs(c - want) < Math.abs(best - want) - 1e-9) best = c;
  }
  return best;
}

/**
 * 점(묶음) → 글자 자리. 글자끼리 겹침 0 · **글자와 점(어느 점이든) 겹침 0** 을 이렇게 만든다:
 *  ① 글자마다 놓을 수 있는 자리 — 제 점 오른쪽('r') · 왼쪽('l') · 바로 위·아래(가운데 맞춤 'c')(칸 안에 들 때만) ·
 *     옆 둘 다 안 들면 칸 끝('L'·'R').
 *  ② 아래 점부터 차례로, 이미 놓은 글자와 모든 점 가운데 **그 꼴의 폭 범위에서 가로가 겹칠 수 있는 것만** 피해 제 점 높이에
 *     가장 가까운 빈 칸을 고른다(옆 자리는 한도 안에서 위아래로 움직이고, 위·아래 자리는 점에 붙은 한 칸뿐).
 *  ③ 빈 칸이 없으면 — 같은 계약 달 글자가 있으면 그것과 묶고(부딪힌 것 먼저), 없으면 그 글자만 한도를 한 줄 늘려 ①부터 다시.
 *     한도가 칸 높이를 넘도록 자리가 없을 때만(매우 빽빽한 자료) 마지막 수단으로 가로로 가장 가까운 글자와 묶는다.
 *  묶거나 한도를 늘릴 때마다 남은 일이 줄어 반드시 끝난다(글자 하나 + 한도 = 칸 높이면 늘 자리가 있다 — 점을 덮지 않는 자리가
 *  하나도 없을 만큼 칸이 점으로 가득하면 글자 0 으로 끝난다).
 */
export function txPlotLabels(points: TxPlotPoint[], ref: { w: number; maxW: number; h: number }): TxLabel[] {
  const H = TX_LABEL_H;
  // 세로 한 칸 = 글자 줄 + 1px 틈(맞닿은 두 줄이 한 덩이로 붙어 보이지 않게).
  const S = H + 1;
  const lo = H / 2;
  const hi = ref.h - H / 2;
  const maxTier = Math.ceil(ref.h / S);
  // 점 = 지름 10px 상자, 가로 자리는 % (α = x/100 · c = −5) — 글자가 이 상자와 겹치지 않는다.
  const dots = points.map((p) => ({
    span: { side: 'r' as const, alpha: p.x / 100, c: -DOT, w: DOT * 2 },
    cy: (p.y / 100) * ref.h,
  }));
  const month = (i: number) => points[i].x; // 같은 계약 달 = 같은 가로 자리.
  let seeds: LabelSeed[] = points.map((p, i) => ({ members: [i], ax: (p.x / 100) * ref.w, ay: (p.y / 100) * ref.h, tier: 1 }));
  const textOf = (s: LabelSeed) =>
    labelText(
      s.members.map((i) => points[i].price),
      s.members.reduce((sum, i) => sum + points[i].n, 0),
    );
  /** 자리 후보 — 옆(한도 안에서 위아래로) 또는 점 바로 위·아래(고정 높이). */
  const slotsOf = (s: LabelSeed, w: number): Array<{ span: Span; heights: number[] | null }> => {
    const alpha = s.ax / ref.w;
    const out: Array<{ span: Span; heights: number[] | null }> = [];
    if (s.ax + TX_LABEL_GAP + w <= ref.w) out.push({ span: { side: 'r', alpha, c: TX_LABEL_GAP, w }, heights: null });
    if (s.ax - TX_LABEL_GAP - w >= 0) out.push({ span: { side: 'l', alpha, c: -TX_LABEL_GAP - w, w }, heights: null });
    if (s.ax - w / 2 >= 0 && s.ax + w / 2 <= ref.w) {
      // 묶음이면 가장 위 점의 위 · 가장 아래 점의 아래(제 점들을 덮지 않게).
      const ys = s.members.map((i) => (points[i].y / 100) * ref.h);
      out.push({ span: { side: 'c', alpha, c: -w / 2, w }, heights: [Math.max(...ys) + ABOVE, Math.min(...ys) - ABOVE] });
    }
    if (out.length === 0) out.push({ span: alpha < 0.5 ? { side: 'L', alpha: 0, c: 0, w } : { side: 'R', alpha: 1, c: -w, w }, heights: null });
    return out;
  };

  const MAX_ROUNDS = points.length * (maxTier + 2) + 2;
  for (let round = 0; round < MAX_ROUNDS; round += 1) {
    const order = seeds.map((_, i) => i).sort((a, b) => seeds[a].ay - seeds[b].ay || seeds[a].ax - seeds[b].ax);
    const placed: Array<{ i: number; text: string; span: Span; cy: number }> = [];
    let fail: { i: number; against: number[] } | null = null;
    for (const i of order) {
      const s = seeds[i];
      const text = textOf(s);
      const limit = TX_LABEL_MAX_SHIFT * s.tier;
      const want = Math.min(hi, Math.max(lo, s.ay));
      let best: { span: Span; cy: number; d: number } | null = null;
      const againstAll = new Set<number>();
      for (const slot of slotsOf(s, txLabelWidth(text))) {
        const against = placed.filter((p) => mayOverlap(slot.span, p.span, ref.w, ref.maxW));
        for (const p of against) againstAll.add(p.i);
        const blocked = [
          ...against.map((p) => ({ c: p.cy, d: S })),
          ...dots.filter((d) => mayOverlap(slot.span, d.span, ref.w, ref.maxW)).map((d) => ({ c: d.cy, d: H / 2 + DOT + 1 })),
        ];
        const cands =
          slot.heights === null
            ? [nearestFree(s.ay, blocked, lo, hi)]
            : slot.heights.filter((y) => y >= lo - 1e-9 && y <= hi + 1e-9 && !blocked.some((b) => Math.abs(y - b.c) < b.d - 1e-9));
        for (const cy of cands) {
          if (cy === null || Math.abs(cy - want) > limit + 1e-9) continue;
          // 옆 자리를 먼저(같은 거리면) — 점 위·아래는 옆이 막혔을 때의 자리.
          const d = Math.abs(cy - s.ay) + (slot.span.side === 'c' ? 0.5 : 0);
          if (best === null || d < best.d - 1e-9) best = { span: slot.span, cy, d };
        }
      }
      if (best === null) {
        fail = { i, against: [...againstAll] };
        break;
      }
      placed.push({ i, text, span: best.span, cy: best.cy });
    }
    if (fail === null) {
      return placed
        .sort((a, b) => a.i - b.i)
        .map((p) => {
          const x0 = p.span.alpha * ref.w + p.span.c;
          return {
            text: p.text,
            x: (seeds[p.i].ax / ref.w) * 100,
            y: (p.cy / ref.h) * 100,
            side: p.span.side,
            shift: Math.abs(p.cy - Math.min(hi, Math.max(lo, seeds[p.i].ay))),
            box: { x0, x1: x0 + p.span.w, y0: p.cy - H / 2, y1: p.cy + H / 2 },
          };
        });
    }
    // ③ 같은 계약 달 글자와 묶는다(부딪힌 것 먼저 · 그다음 세로로 가까운 것).
    const me = seeds[fail.i];
    const sameMonth = seeds
      .map((_, j) => j)
      .filter((j) => j !== fail!.i && month(seeds[j].members[0]) === month(me.members[0]) && seeds[j].ax === me.ax);
    let partner: number | null = null;
    if (sameMonth.length > 0) {
      partner = [...sameMonth].sort(
        (a, b) =>
          Number(!fail!.against.includes(a)) - Number(!fail!.against.includes(b)) ||
          Math.abs(seeds[a].ay - me.ay) - Math.abs(seeds[b].ay - me.ay),
      )[0];
    } else if (me.tier < maxTier) {
      // 묶을 같은 달이 없다 — 이 글자만 한도를 한 줄 늘려 다시(다른 달끼리는 묶지 않는다).
      seeds = seeds.map((s, j) => (j === fail!.i ? { ...s, tier: s.tier + 1 } : s));
      continue;
    } else {
      // 마지막 수단(칸 높이만큼 비켜도 자리가 없는 매우 빽빽한 자료) — 가로로 가장 가까운 글자와 묶는다.
      const pool = fail.against.length > 0 ? fail.against : seeds.map((_, j) => j).filter((j) => j !== fail!.i);
      if (pool.length === 0) return []; // 점이 칸을 가득 메워 글자 하나도 못 놓는다 — 글자 0(점을 덮지 않는다).
      partner = [...pool].sort(
        (a, b) =>
          Math.abs(seeds[a].ax - me.ax) - Math.abs(seeds[b].ax - me.ax) ||
          Math.abs(seeds[a].ay - me.ay) - Math.abs(seeds[b].ay - me.ay),
      )[0];
    }
    const members = [...me.members, ...seeds[partner].members];
    const merged: LabelSeed = {
      members,
      ax: (me.ax + seeds[partner].ax) / 2,
      ay: members.reduce((sum, m) => sum + (points[m].y / 100) * ref.h, 0) / members.length,
      tier: 1,
    };
    seeds = [...seeds.filter((_, j) => j !== fail!.i && j !== partner), merged];
  }
  // 닿지 않는 자리(위 ③ 설명 — 단계 수에 끝이 있다) — 안전하게 글자 0.
  return [];
}

/**
 * 거래 목록 → 점그림. 목록이 `TX_PLOT_MIN` 건 미만이거나 찍을 점이 하나도 없으면 null(그림을 안 그린다).
 * ㎡당 단가가 없거나 0 이하·계약 달을 못 읽은 거래는 점을 빼고 `skipped` 로 센다.
 * 같은 계약 달 + 같은 ㎡당 값 + 같은 꼴(지분 여부 포함) 거래는 점 하나(`n` = 건수)로 묶는다(보완 1 F2).
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

  // 같은 달 + 같은 값 + 같은 꼴(지분 여부 포함)은 점 하나로(처음 나온 차례 그대로).
  const points: TxPlotPoint[] = [];
  const at = new Map<string, number>();
  for (const d of drawable) {
    const shape = txShape(d.t.floor_no);
    const hollow = d.t.is_share === true;
    const key = `${d.idx}|${d.price}|${shape}|${hollow ? 1 : 0}`;
    const seen = at.get(key);
    if (seen !== undefined) {
      points[seen].n += 1;
      continue;
    }
    at.set(key, points.length);
    points.push({
      x: hi === lo ? 50 : (pctOf(d.idx - lo, hi - lo) as number),
      y: pctOf(d.price, yMaxWon) as number,
      shape,
      hollow,
      price: d.price,
      n: 1,
    });
  }
  const seen = new Set(points.map((p) => p.shape));
  return {
    points,
    yMaxWon,
    ticks: [0, 1, 2, 3, 4].map((k) => ({ y: k * 25, won: (yMaxWon * k) / 4 })),
    labels: { wide: txPlotLabels(points, TX_PLOT_REF.wide), narrow: txPlotLabels(points, TX_PLOT_REF.narrow) },
    fromYm: drawable.find((d) => d.idx === lo)!.t.contract_ym,
    toYm: drawable.find((d) => d.idx === hi)!.t.contract_ym,
    skipped,
    shapes: TX_SHAPE_ORDER.filter((s) => seen.has(s)),
    hasHollow: points.some((p) => p.hollow),
  };
}
