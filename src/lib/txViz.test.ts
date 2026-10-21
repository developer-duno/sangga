import { readFileSync } from 'node:fs';
import { describe, it, expect } from 'vitest';
import type { ParcelTransaction, SigunguTxStat } from '../types';
import {
  TX_LABEL_GAP,
  TX_LABEL_H,
  TX_LABEL_MAX_SHIFT,
  TX_PLOT_MIN,
  TX_PLOT_REF,
  TX_SHAPE_ORDER,
  txBandAxisMaxWon,
  txBandMark,
  txLabelWidth,
  txPlot,
  txPlotShows,
  txShape,
  mayOverlap,
  type TxLabel,
  type TxPlotPoint,
  type TxSpan,
} from './txViz';
import { TX_MIN_SAMPLE } from './appConstants';

/**
 * 실거래 카드 그림(결정 0038 B · V2) — 그림이 깨져도 글자 시험은 초록이다(§2-10). 값 → 자리·꼴을 숫자로 못 박는다.
 */

function stat(over: Partial<SigunguTxStat> = {}): SigunguTxStat {
  return {
    floor_band: '1층',
    n: 213,
    median_unit_price: 22_500_000,
    p25_unit_price: 13_800_000,
    p75_unit_price: 37_300_000,
    window_from: '202408',
    sigungu_nm: '강남구',
    ...over,
  };
}

function tx(over: Partial<ParcelTransaction> = {}): ParcelTransaction {
  return {
    floor_no: 1,
    contract_ym: '202605',
    contract_day: 12,
    bld_area_m2: 84.3,
    price_won: 320_000_000,
    unit_price: 3_800_000,
    tx_type: '집합',
    ...over,
  };
}

describe('txBandAxisMaxWon — 구 층대 띠 축 상한', () => {
  it('값을 내는 줄의 p75·가운데값 최댓값을 만원 단위로 올린다', () => {
    // p75 3,730만 → 5,000만(1·2·2.5·5 × 10ⁿ).
    expect(txBandAxisMaxWon([stat()])).toBe(50_000_000);
    const low = { median_unit_price: 10_000_000, p25_unit_price: 5_000_000 };
    expect(
      txBandAxisMaxWon([stat({ ...low, p75_unit_price: 19_046_000 }), stat({ ...low, n: 9, p75_unit_price: 12_000_000 })]),
    ).toBe(20_000_000);
    // 가운데값이 p75 보다 클 리는 없지만, 큰 쪽이 축을 정한다(띠·눈금이 축 밖으로 안 나가게).
    expect(txBandAxisMaxWon([stat()])).toBe(50_000_000);
  });

  it('표본 부족(5건 미만) 줄은 축에 안 넣는다 · 값을 내는 줄이 없으면 null', () => {
    const low = { median_unit_price: 10_000_000, p25_unit_price: 5_000_000 };
    expect(
      txBandAxisMaxWon([stat({ ...low, p75_unit_price: 19_000_000 }), stat({ ...low, n: 4, p75_unit_price: 90_000_000 })]),
    ).toBe(20_000_000);
    expect(txBandAxisMaxWon([stat({ n: 4 }), stat({ n: 0, median_unit_price: null })])).toBeNull();
    expect(txBandAxisMaxWon([])).toBeNull();
  });

  it('p75 가 없으면 가운데값으로 올린다', () => {
    expect(txBandAxisMaxWon([stat({ median_unit_price: 7_000_000, p75_unit_price: null })])).toBe(10_000_000);
  });
});

describe('txBandMark — 층대 줄 하나의 띠', () => {
  it('p25~p75 띠 + 가운데값 눈금 — 같은 축 위 %', () => {
    const m = txBandMark(stat(), 50_000_000);
    expect(m.kind).toBe('band');
    if (m.kind !== 'band') return;
    expect(m.left).toBeCloseTo(27.6, 9);
    expect(m.width).toBeCloseTo(47.0, 9);
    expect(m.x).toBeCloseTo(45.0, 9);
  });

  it('문턱 = 표본 5건 — 4건은 "–"(0 으로 안 그린다) · 5건은 띠', () => {
    expect(TX_MIN_SAMPLE).toBe(5);
    expect(txBandMark(stat({ n: 4 }), 50_000_000)).toEqual({ kind: 'none' });
    expect(txBandMark(stat({ n: 5 }), 50_000_000).kind).toBe('band');
    expect(txBandMark(stat({ n: 0, median_unit_price: null, p25_unit_price: null, p75_unit_price: null }), 50_000_000)).toEqual({
      kind: 'none',
    });
  });

  it('가운데값이 없거나 축이 없으면 "–"', () => {
    expect(txBandMark(stat({ median_unit_price: null }), 50_000_000)).toEqual({ kind: 'none' });
    expect(txBandMark(stat(), null)).toEqual({ kind: 'none' });
  });

  it('사분위가 없거나 폭 0·뒤집힘이면 띠 없이 눈금만', () => {
    expect(txBandMark(stat({ p25_unit_price: null }), 50_000_000)).toEqual({ kind: 'tick', x: 45 });
    expect(txBandMark(stat({ p25_unit_price: 22_500_000, p75_unit_price: 22_500_000 }), 50_000_000)).toEqual({
      kind: 'tick',
      x: 45,
    });
    expect(txBandMark(stat({ p25_unit_price: 40_000_000, p75_unit_price: 10_000_000 }), 50_000_000)).toEqual({
      kind: 'tick',
      x: 45,
    });
  });
});

describe('txPlotShows · TX_PLOT_MIN — 점그림 문턱', () => {
  it('목록의 거래 수 4건 = 안 섬 · 5건 = 섬(지분·층 미상도 센다)', () => {
    expect(TX_PLOT_MIN).toBe(5);
    expect(txPlotShows(Array.from({ length: 4 }, () => tx()))).toBe(false);
    expect(txPlotShows(Array.from({ length: 5 }, () => tx()))).toBe(true);
    const mixed = [tx({ is_share: true }), tx({ floor_no: null }), tx({ is_share: true, floor_no: null }), tx(), tx()];
    expect(txPlotShows(mixed)).toBe(true);
    expect(txPlotShows([])).toBe(false);
  });
});

describe('txShape — 층 묶음 다섯', () => {
  it('지하 · 1층 · 2층 · 3층 이상(옥탑 포함) · 층 미상', () => {
    expect(txShape(-1)).toBe('b');
    expect(txShape(-3)).toBe('b');
    expect(txShape(1)).toBe('1');
    expect(txShape(2)).toBe('2');
    expect(txShape(3)).toBe('3+');
    expect(txShape(17)).toBe('3+');
    expect(txShape(99)).toBe('3+');
    expect(txShape(null)).toBe('na');
    expect(txShape(undefined)).toBe('na');
    expect(txShape(Number.NaN)).toBe('na');
    // 0 은 쓰지 않는 값 — 지하로도 지상으로도 세지 않는다(절대 규칙 4).
    expect(txShape(0)).toBe('na');
  });

  it('범례 차례는 고정 다섯', () => {
    expect(TX_SHAPE_ORDER).toEqual(['1', '2', '3+', 'b', 'na']);
  });
});

describe('txPlot — 거래 → 점 자리·꼴', () => {
  it('4건이면 null · 5건이면 점 5개(값이 다 다를 때)', () => {
    expect(txPlot(Array.from({ length: 4 }, (_, i) => tx({ unit_price: (i + 1) * 1_000_000 })))).toBeNull();
    expect(txPlot(Array.from({ length: 5 }, (_, i) => tx({ unit_price: (i + 1) * 1_000_000 })))!.points).toHaveLength(5);
  });

  it('세로 = ㎡당 단가(0 ~ 최댓값 올림) · 가로 = 가장 이른 달 0 ~ 가장 늦은 달 100', () => {
    const p = txPlot([
      tx({ contract_ym: '202401', unit_price: 2_000_000 }),
      tx({ contract_ym: '202501', unit_price: 4_000_000 }),
      tx({ contract_ym: '202601', unit_price: 8_000_000 }),
      tx({ contract_ym: '202407', unit_price: 1_000_000 }),
      tx({ contract_ym: '202601', unit_price: 3_000_000 }),
    ])!;
    expect(p.yMaxWon).toBe(10_000_000);
    expect(p.fromYm).toBe('202401');
    expect(p.toYm).toBe('202601');
    expect(p.points.map((x) => x.x)).toEqual([0, 50, 100, 25, 100]);
    expect(p.points.map((x) => x.y)).toEqual([20, 40, 80, 10, 30]);
    expect(p.skipped).toBe(0);
  });

  it('계약 달이 하나뿐이면 가로 자리는 전부 가운데(50)', () => {
    const p = txPlot(Array.from({ length: 5 }, () => tx()))!;
    expect(p.points.every((x) => x.x === 50)).toBe(true);
    expect(p.fromYm).toBe(p.toYm);
  });

  it('층 묶음 다섯 꼴 · 지분은 빈 꼴(값은 그대로 찍는다)', () => {
    const p = txPlot([
      tx({ floor_no: 1 }),
      tx({ floor_no: 2 }),
      tx({ floor_no: 5 }),
      tx({ floor_no: -1 }),
      tx({ floor_no: null }),
      tx({ floor_no: 2, is_share: true, unit_price: 1_480_000 }),
    ])!;
    expect(p.points.map((x) => x.shape)).toEqual(['1', '2', '3+', 'b', 'na', '2']);
    expect(p.points.map((x) => x.hollow)).toEqual([false, false, false, false, false, true]);
    // 지분도 0 이 아니라 제 값 자리에 선다.
    expect(p.points[5].y).toBeCloseTo((1_480_000 / 5_000_000) * 100, 9);
    expect(p.shapes).toEqual(['1', '2', '3+', 'b', 'na']);
    expect(p.hasHollow).toBe(true);
  });

  it('옛 서버(is_share 없음)·false 는 빈 꼴이 아니다', () => {
    const p = txPlot([tx(), tx({ is_share: false }), tx(), tx(), tx()])!;
    expect(p.hasHollow).toBe(false);
    expect(p.points.some((x) => x.hollow)).toBe(false);
  });

  it('㎡당 값이 없거나 0 이하·계약 달을 못 읽은 거래는 점을 빼고 센다(0 에 찍지 않는다)', () => {
    const p = txPlot([
      tx({ unit_price: null }),
      tx({ unit_price: 0 }),
      tx({ contract_ym: '2026-05' }),
      tx({ contract_ym: '202613' }),
      tx(),
    ])!;
    expect(p.points).toHaveLength(1);
    expect(p.skipped).toBe(4);
    expect(p.shapes).toEqual(['1']);
  });

  it('찍을 점이 하나도 없으면 null(빈 그림을 세우지 않는다)', () => {
    expect(txPlot(Array.from({ length: 6 }, () => tx({ unit_price: null })))).toBeNull();
  });
});

// ── 보완 1(👤 2026-10-21 「점 옆에 금액」) ─────────────────────────────────────────

/** 글자 상자 둘이 겹치나(맞닿음은 겹침 아님 · 부동소수 오차 1e-6 px 는 맞닿음으로 본다). */
function overlaps(a: TxLabel['box'], b: TxLabel['box']): boolean {
  const e = 1e-6;
  return a.x0 < b.x1 - e && b.x0 < a.x1 - e && a.y0 < b.y1 - e && b.y0 < a.y1 - e;
}
function overlapPairs(labels: TxLabel[]): string[] {
  const bad: string[] = [];
  for (let i = 0; i < labels.length; i += 1) {
    for (let j = i + 1; j < labels.length; j += 1) {
      if (overlaps(labels[i].box, labels[j].box)) bad.push(`${labels[i].text} ↔ ${labels[j].text}`);
    }
  }
  return bad;
}
/**
 * 실제 폭 W(≥ 기준 폭)에서 그 글자가 차지할 상자 — CSS 와 같은 규칙(점 자리 % + 7px · 칸 끝 붙임)으로 다시 세운다.
 * 세로는 기준 높이 그대로(실제 칸은 더 높아 사이가 벌어지기만 한다).
 */
function boxAt(l: TxLabel, W: number, h: number): TxLabel['box'] {
  const w = txLabelWidth(l.text);
  const ax = (l.x / 100) * W;
  const x0 =
    l.side === 'r'
      ? ax + TX_LABEL_GAP
      : l.side === 'l'
        ? ax - TX_LABEL_GAP - w
        : l.side === 'c'
          ? ax - w / 2
          : l.side === 'L'
            ? 0
            : W - w;
  const cy = (l.y / 100) * h;
  return { x0, x1: x0 + w, y0: cy - TX_LABEL_H / 2, y1: cy + TX_LABEL_H / 2 };
}
/** 그 꼴의 폭 범위(기준 폭 ~ 가장 넓은 폭)를 촘촘히 훑어 겹침·칸 밖 — 폭이 늘 때 마주 보던 글자가 엇갈려 겹치는 꼴까지 잡는다. */
function problemsAtWidths(labels: TxLabel[], ref: { w: number; maxW: number; h: number }): string[] {
  const bad: string[] = [];
  for (let s = 0; s <= 40; s += 1) {
    const W = ref.w + ((ref.maxW - ref.w) * s) / 40;
    const k = Math.round(W);
    const boxes = labels.map((l) => boxAt(l, W, ref.h));
    boxes.forEach((b, i) => {
      if (b.x0 < -1e-9 || b.x1 > W + 1e-9) bad.push(`${k}px 칸 밖 ${labels[i].text}`);
      for (let j = i + 1; j < boxes.length; j += 1) {
        if (overlaps(b, boxes[j])) bad.push(`${k}px ${labels[i].text} ↔ ${labels[j].text}`);
      }
    });
  }
  return bad;
}
/**
 * 글자가 점을 덮나(보완 2) — 폭 범위 전체에서, **모든 점**(묶음 안 제 점 포함 · 점 = 지름 10px 상자)과 글자 상자의 겹침.
 */
function dotHitsAtWidths(labels: TxLabel[], points: TxPlotPoint[], ref: { w: number; maxW: number; h: number }): string[] {
  const bad: string[] = [];
  for (let s = 0; s <= 40; s += 1) {
    const W = ref.w + ((ref.maxW - ref.w) * s) / 40;
    for (const l of labels) {
      const b = boxAt(l, W, ref.h);
      for (const p of points) {
        const cx = (p.x / 100) * W;
        const cy = (p.y / 100) * ref.h;
        if (overlaps(b, { x0: cx - 5, x1: cx + 5, y0: cy - 5, y1: cy + 5 })) bad.push(`${Math.round(W)}px ${l.text} ↔ 점 ${p.price}`);
      }
    }
  }
  return [...new Set(bad)];
}
/** 글자가 기준 칸 안에 있나(세로) — 가로는 점 옆이라 칸 폭을 넘지 않게 고른 쪽만 본다. */
function outOfBox(labels: TxLabel[], ref: { w: number; h: number }): string[] {
  return labels
    .filter((l) => l.box.y0 < -1e-9 || l.box.y1 > ref.h + 1e-9 || l.box.x0 < -1e-9 || l.box.x1 > ref.w + 1e-9)
    .map((l) => l.text);
}

/** 유니온오피스텔 꼴 가짜 자료 12건(👤 운영 전 사진의 모양 — 값은 지시서 예시 · 나머지는 지어낸 것). */
const UNION = [
  tx({ floor_no: 11, contract_ym: '202608', unit_price: 9_000_000 }),
  tx({ floor_no: 2, contract_ym: '202603', unit_price: 2_600_000, is_share: true }),
  tx({ floor_no: 2, contract_ym: '202603', unit_price: 2_600_000, is_share: true }),
  tx({ floor_no: 5, contract_ym: '202507', unit_price: 7_380_000 }),
  tx({ floor_no: 7, contract_ym: '202507', unit_price: 7_290_000 }),
  tx({ floor_no: 9, contract_ym: '202507', unit_price: 7_720_000 }),
  tx({ floor_no: 1, contract_ym: '202511', unit_price: 6_100_000 }),
  tx({ floor_no: 4, contract_ym: '202504', unit_price: 6_900_000 }),
  tx({ floor_no: 2, contract_ym: '202502', unit_price: 4_200_000 }),
  tx({ floor_no: -1, contract_ym: '202410', unit_price: 3_000_000 }),
  tx({ floor_no: null, contract_ym: '202405', unit_price: 3_500_000 }),
  tx({ floor_no: 1, contract_ym: '202402', unit_price: 5_000_000 }),
];

describe('txPlot — 겹친 거래 묶기 · 눈금 넷(보완 1 F2·F4)', () => {
  it('같은 달 + 같은 값 + 같은 꼴은 점 하나 · n = 건수 · 다른 꼴·지분 여부가 다르면 따로', () => {
    const p = txPlot([
      tx({ is_share: true, unit_price: 2_600_000 }),
      tx({ is_share: true, unit_price: 2_600_000 }),
      tx({ is_share: false, unit_price: 2_600_000 }),
      tx({ floor_no: 2, unit_price: 2_600_000 }),
      tx({ unit_price: 2_600_000, contract_ym: '202604' }),
    ])!;
    expect(p.points.map((x) => [x.shape, x.hollow, x.n])).toEqual([
      ['1', true, 2],
      ['1', false, 1],
      ['2', false, 1],
      ['1', false, 1],
    ]);
  });

  it('가로 눈금 = 축 상한의 0 · ¼ · ½ · ¾ · 끝', () => {
    const p = txPlot(UNION)!;
    expect(p.yMaxWon).toBe(10_000_000);
    expect(p.ticks).toEqual([
      { y: 0, won: 0 },
      { y: 25, won: 2_500_000 },
      { y: 50, won: 5_000_000 },
      { y: 75, won: 7_500_000 },
      { y: 100, won: 10_000_000 },
    ]);
  });
});

describe('txPlotLabels — 점 금액 글자 자리(보완 1 F1·F3)', () => {
  it('유니온 꼴 12건 — 글자 = 목록과 같은 서식(formatManWon) · 겹친 지분 둘은 「260만 ×2」 · 두 벌 모두 겹침 0 · 칸 안', () => {
    const p = txPlot(UNION)!;
    expect(p.points).toHaveLength(11);
    for (const kind of ['wide', 'narrow'] as const) {
      const labels = p.labels[kind];
      expect(overlapPairs(labels), kind).toEqual([]);
      expect(outOfBox(labels, TX_PLOT_REF[kind]), kind).toEqual([]);
      expect(problemsAtWidths(labels, TX_PLOT_REF[kind]), kind).toEqual([]);
      expect(dotHitsAtWidths(labels, p.points, TX_PLOT_REF[kind]), kind).toEqual([]);
      const texts = labels.map((l) => l.text);
      expect(texts).toContain('900만');
      expect(texts).toContain('260만 ×2');
      // 점 하나에 글자 하나 — 묶지 않았으면 11개, 묶었으면 건수 합이 12.
      const count = (t: string) => Number(/×(\d+)$/.exec(t)?.[1] ?? 1);
      expect(texts.reduce((s, t) => s + count(t), 0), kind).toBe(12);
    }
    // 넓은 벌은 몰린 2025-07 셋도 낱개로 비켜 적는다(묶지 않는다).
    expect(p.labels.wide.map((l) => l.text)).toEqual(expect.arrayContaining(['738만', '729만', '772만']));
  });

  it('비켜 적지 않으면 겹칠 자리(같은 달 가까운 값 셋)도 겹침 0 — 세로로 한 줄씩(16px) 벌어진다', () => {
    const pts = txPlot([
      tx({ contract_ym: '202507', unit_price: 7_380_000, floor_no: 5 }),
      tx({ contract_ym: '202507', unit_price: 7_290_000, floor_no: 6 }),
      tx({ contract_ym: '202507', unit_price: 7_720_000, floor_no: 7 }),
      tx({ contract_ym: '202401', unit_price: 1_000_000 }),
      tx({ contract_ym: '202608', unit_price: 9_000_000 }),
    ])!;
    for (const kind of ['wide', 'narrow'] as const) {
      const labs = pts.labels[kind].filter((l) => ['738만', '729만', '772만'].includes(l.text));
      // 셋 다 낱개로(묶지 않는다) · 겹침 0 · 제 점 높이에서 두 줄 안(점 왼쪽·오른쪽으로 갈라 앉거나 위아래로 비킨다).
      expect(labs, kind).toHaveLength(3);
      expect(overlapPairs(pts.labels[kind]), kind).toEqual([]);
      for (const l of labs) {
        const want = (Number(l.text.replace(/[^0-9]/g, '')) * 10_000 / pts.yMaxWon) * TX_PLOT_REF[kind].h;
        expect(Math.abs((l.box.y0 + l.box.y1) / 2 - want), `${kind} ${l.text}`).toBeLessThanOrEqual(TX_LABEL_MAX_SHIFT + 1e-9);
      }
    }
    // 그대로 두면(제 점 높이 · 오른쪽) 셋이 겹친다 — 비켜 적기가 실제로 일했다(양성 대조).
    const naive = pts.points
      .filter((p) => [7_380_000, 7_290_000, 7_720_000].includes(p.price))
      .map((p) => {
        const ax = (p.x / 100) * TX_PLOT_REF.wide.w;
        const ay = (p.y / 100) * TX_PLOT_REF.wide.h;
        const w = txLabelWidth(`${p.price / 10_000}만`);
        return { x0: ax + TX_LABEL_GAP, x1: ax + TX_LABEL_GAP + w, y0: ay - TX_LABEL_H / 2, y1: ay + TX_LABEL_H / 2 };
      });
    expect(overlaps(naive[0], naive[1]) || overlaps(naive[1], naive[2]) || overlaps(naive[0], naive[2])).toBe(true);
  });

  it('한 달에 몰려 가까이 둘 칸이 모자라면 「a만~b만 ×N」 묶음 글자로 · 건수 합 그대로 · 겹침 0', () => {
    const many = Array.from({ length: 20 }, (_, i) => tx({ contract_ym: '202507', unit_price: 5_000_000 + i * 10_000, floor_no: i + 3 }));
    const p = txPlot([...many, tx({ contract_ym: '202401', unit_price: 1_000_000 })])!;
    const count = (t: string) => Number(/×(\d+)$/.exec(t)?.[1] ?? 1);
    for (const kind of ['wide', 'narrow'] as const) {
      const labels = p.labels[kind];
      expect(overlapPairs(labels), kind).toEqual([]);
      expect(problemsAtWidths(labels, TX_PLOT_REF[kind]), kind).toEqual([]);
      expect(dotHitsAtWidths(labels, p.points, TX_PLOT_REF[kind]), kind).toEqual([]);
      expect(labels.reduce((s, l) => s + count(l.text), 0), kind).toBe(21);
      // 같은 달 묶음이 남아 있는 동안은 한도(한 줄)를 늘리지 않는다 — 모든 글자가 제 점(묶음이면 점들 가운데)에서 한 줄 이내.
      expect(labels.filter((l) => l.shift > TX_LABEL_MAX_SHIFT + 1e-9).map((l) => `${l.text} ${l.shift}`), kind).toEqual([]);
      // 낱개 20 은 제 점 가까이에 다 못 앉는다 — 묶음 글자가 생긴다(목록과 같은 서식: 「500만~519만」 꼴).
      const merged = labels.filter((l) => /^\d[\d,]*만~\d[\d,]*만 ×\d+$/.test(l.text));
      expect(merged.length, kind).toBeGreaterThan(0);
      expect(labels.length, kind).toBeLessThan(21);
    }
  });

  it('점이 빽빽해도(100건 · 여러 달) 두 벌 모두 겹침 0 · 칸 안 · 건수 합 = 점 건수 합', () => {
    let seed = 7;
    const rnd = () => {
      seed = (seed * 1_103_515_245 + 12_345) % 2_147_483_648;
      return seed / 2_147_483_648;
    };
    const txs = Array.from({ length: 100 }, () =>
      tx({
        contract_ym: `${2024 + Math.floor(rnd() * 3)}${String(1 + Math.floor(rnd() * 12)).padStart(2, '0')}`,
        unit_price: Math.round(1_000_000 + rnd() * 9_000_000),
        floor_no: Math.floor(rnd() * 6) - 1 || null,
        is_share: rnd() < 0.1,
      }),
    );
    const p = txPlot(txs)!;
    const total = p.points.reduce((s, x) => s + x.n, 0);
    for (const kind of ['wide', 'narrow'] as const) {
      const labels = p.labels[kind];
      expect(labels.length, kind).toBeGreaterThan(0);
      // 비켜난 거리는 칸 높이 안(보완 2 — 같은 달 묶음이 없으면 한도를 한 줄씩 늘린다 · 빽빽한 자료는 한 줄을 넘을 수 있다).
      expect(labels.filter((l) => l.shift > TX_PLOT_REF[kind].h).map((l) => `${l.text} ${l.shift}`), kind).toEqual([]);
      expect(overlapPairs(labels), kind).toEqual([]);
      expect(outOfBox(labels, TX_PLOT_REF[kind]), kind).toEqual([]);
      expect(problemsAtWidths(labels, TX_PLOT_REF[kind]), kind).toEqual([]);
      expect(dotHitsAtWidths(labels, p.points, TX_PLOT_REF[kind]), kind).toEqual([]);
      const count = (t: string) => Number(/×(\d+)$/.exec(t)?.[1] ?? 1);
      expect(labels.reduce((s, l) => s + count(l.text), 0), kind).toBe(total);
    }
  });

  it('오른쪽 끝 점의 글자는 왼쪽에 · 그 밖은 오른쪽 · 가로 자리는 제 점(묶지 않은 글자)', () => {
    const p = txPlot([
      tx({ contract_ym: '202401', unit_price: 1_000_000 }),
      tx({ contract_ym: '202501', unit_price: 5_000_000 }),
      tx({ contract_ym: '202601', unit_price: 9_000_000 }),
      tx({ contract_ym: '202407', unit_price: 3_000_000 }),
      tx({ contract_ym: '202507', unit_price: 7_000_000 }),
    ])!;
    const by = (t: string) => p.labels.wide.find((l) => l.text === t)!;
    expect(by('900만').side).toBe('l');
    expect(by('100만').side).toBe('r');
    expect(by('100만').x).toBeCloseTo(0, 9);
    expect(by('900만').x).toBeCloseTo(100, 9);
    expect(by('500만').x).toBeCloseTo(50, 9);
  });

  it('양성 대조 — 기준 폭에선 떨어져 있어도 폭이 늘며 엇갈려 겹치는 짝을 검사 함수가 잡는다', () => {
    const ref = { w: 200, maxW: 800, h: 200 };
    // 오른쪽 점(55%)의 글자는 왼쪽에, 왼쪽 점(50%)의 글자는 오른쪽에 — 기준 폭 200 에선 4px 떨어짐 · 400 에선 겹침.
    const mk = (x: number, side: TxLabel['side']): TxLabel => ({ text: '900만', x, y: 50, side, shift: 0, box: { x0: 0, x1: 0, y0: 0, y1: 0 } });
    const pair = [mk(55, 'l'), mk(50, 'r')];
    expect(overlapPairs(pair.map((l) => ({ ...l, box: boxAt(l, ref.w, ref.h) })))).toEqual([]);
    expect(problemsAtWidths(pair, ref).length).toBeGreaterThan(0);
  });

  it('보완 2 — 운영 유니온오피스텔 꼴 12건(휴대폰): 다른 달은 묶지 않는다 · 어느 글자도 점을 덮지 않는다', () => {
    // 2026-10-21 운영 사진(메인)의 점 자리를 옮긴 가짜 자료 — 2024-01 747만 ×2 · 2024-07 689만 · 2025-07 셋(729·738·772) + 353만(층 미상) …
    const p = txPlot([
      tx({ floor_no: 5, contract_ym: '202401', unit_price: 7_470_000 }),
      tx({ floor_no: 5, contract_ym: '202401', unit_price: 7_470_000 }),
      tx({ floor_no: 6, contract_ym: '202407', unit_price: 6_890_000 }),
      tx({ floor_no: null, contract_ym: '202409', unit_price: 1_180_000, is_share: true }),
      tx({ floor_no: 7, contract_ym: '202507', unit_price: 7_290_000 }),
      tx({ floor_no: 8, contract_ym: '202507', unit_price: 7_380_000 }),
      tx({ floor_no: 9, contract_ym: '202507', unit_price: 7_720_000 }),
      tx({ floor_no: null, contract_ym: '202507', unit_price: 3_530_000 }),
      tx({ floor_no: null, contract_ym: '202512', unit_price: 4_440_000 }),
      tx({ floor_no: null, contract_ym: '202603', unit_price: 2_600_000, is_share: true }),
      tx({ floor_no: null, contract_ym: '202603', unit_price: 2_600_000, is_share: true }),
      tx({ floor_no: 11, contract_ym: '202608', unit_price: 9_000_000 }),
    ])!;
    expect(p.points).toHaveLength(10);
    const ok2507 = [['729만~772만 ×3'], ['729만', '738만', '772만']];
    for (const kind of ['wide', 'narrow'] as const) {
      const labels = p.labels[kind];
      const texts = labels.map((l) => l.text);
      expect(texts, kind).toEqual(expect.arrayContaining(['747만 ×2', '689만', '118만', '353만', '444만', '260만 ×2', '900만']));
      // 2025-07 셋은 같은 달 — 묶음 하나 또는 셋 다 따로(그 밖의 묶음 글자 0 = 다른 달끼리 안 묶었다).
      const rest = texts.filter((t) => !['747만 ×2', '689만', '118만', '353만', '444만', '260만 ×2', '900만'].includes(t)).sort();
      expect(ok2507.map((x) => [...x].sort()), kind).toContainEqual(rest);
      expect(overlapPairs(labels), kind).toEqual([]);
      expect(problemsAtWidths(labels, TX_PLOT_REF[kind]), kind).toEqual([]);
      expect(dotHitsAtWidths(labels, p.points, TX_PLOT_REF[kind]), kind).toEqual([]);
      // 「747만 ×2」 글자는 2024-01 점(맨 왼쪽) 옆 · 「689만」은 2024-07 점 옆 — 제 점에서 한 줄 이내.
      for (const t of ['747만 ×2', '689만']) {
        const l = labels.find((x) => x.text === t)!;
        expect(l.shift, `${kind} ${t}`).toBeLessThanOrEqual(TX_LABEL_MAX_SHIFT + 1e-9);
      }
      expect(labels.find((x) => x.text === '747만 ×2')!.x, kind).toBeCloseTo(0, 9);
    }
  });

  it('mayOverlap — 기준 폭에선 떨어졌어도 폭 범위 안에서 엇갈려 겹치는 짝은 참 · 범위 밖에서만 겹치면 거짓', () => {
    // 오른쪽 점(55%)의 글자는 왼쪽에, 왼쪽 점(50%)의 글자는 오른쪽에 — 폭 200 에선 4px 떨어짐 · 400 에선 겹침.
    const a: TxSpan = { side: 'l', alpha: 0.55, c: -TX_LABEL_GAP - 42, w: 42 };
    const b: TxSpan = { side: 'r', alpha: 0.5, c: TX_LABEL_GAP, w: 42 };
    expect(mayOverlap(a, b, 200, 800)).toBe(true);
    expect(mayOverlap(b, a, 200, 800)).toBe(true);
    // 폭 범위를 200~250 으로 좁히면 아직 엇갈리지 않는다.
    expect(mayOverlap(a, b, 200, 250)).toBe(false);
    // 같은 차례로 벌어지기만 하는 짝(둘 다 오른쪽)은 기준 폭에서 떨어져 있으면 끝까지 거짓.
    expect(mayOverlap({ ...b, alpha: 0.1 }, { ...b, alpha: 0.5 }, 200, 800)).toBe(false);
    // 같은 점 자리(α 같음)면 폭과 상관없이 구간만 본다 — 글자 오른쪽 vs 제 점(7px 떨어짐) = 거짓.
    expect(mayOverlap(b, { side: 'r', alpha: 0.5, c: -5, w: 10 }, 200, 800)).toBe(false);
  });

  it('보완 2 — 다른 달 점 여섯이 같은 높이로 몰려도 다른 달끼리는 묶지 않는다(위아래로 비켜 적는다)', () => {
    const p = txPlot([
      ...['202401', '202402', '202403', '202404', '202405', '202406'].map((m) => tx({ contract_ym: m, unit_price: 5_000_000 })),
      tx({ contract_ym: '202412', unit_price: 1_000_000 }),
    ])!;
    for (const kind of ['wide', 'narrow'] as const) {
      const labels = p.labels[kind];
      expect(labels.map((l) => l.text).sort(), kind).toEqual(['100만', '500만', '500만', '500만', '500만', '500만', '500만']);
      expect(overlapPairs(labels), kind).toEqual([]);
      expect(problemsAtWidths(labels, TX_PLOT_REF[kind]), kind).toEqual([]);
      expect(dotHitsAtWidths(labels, p.points, TX_PLOT_REF[kind]), kind).toEqual([]);
    }
  });

  it('양성 대조 — 점 덮기 검사 함수는 점 위에 놓인 글자를 잡는다', () => {
    const pt: TxPlotPoint = { x: 50, y: 50, shape: '1', hollow: false, price: 5_000_000, n: 1 };
    const onDot: TxLabel = { text: '500만', x: 40, y: 50, side: 'r', shift: 0, box: { x0: 0, x1: 0, y0: 0, y1: 0 } };
    expect(dotHitsAtWidths([onDot], [pt], { w: 200, maxW: 400, h: 200 }).length).toBeGreaterThan(0);
  });

  it('폭이 늘며 엇갈리는 짝 —오른쪽 점 글자는 왼쪽에(칸 끝이라) · 바로 왼쪽 점 글자는 오른쪽에 · 같은 높이여도 휴대폰 폭 범위 전체에서 겹침 0', () => {
    // 휴대폰 기준 폭 160 에서 2달 차이 = 8px · 높이 차 약 15px(한 줄 16 보다 조금 덜 — 서로의 점은 안 덮는다).
    // 기준 폭에선 두 글자가 6px 떨어지지만 폭이 약 280px 을 넘으면 엇갈려 겹칠 자리다.
    const p = txPlot([
      tx({ contract_ym: '202001', unit_price: 1_000_000 }),
      tx({ contract_ym: '202305', unit_price: 9_000_000 }),
      tx({ contract_ym: '202204', unit_price: 4_460_000, floor_no: 2 }),
      tx({ contract_ym: '202206', unit_price: 5_000_000, floor_no: 1 }),
      tx({ contract_ym: '202011', unit_price: 2_000_000 }),
    ])!;
    const ref = TX_PLOT_REF.narrow;
    const labels = p.labels.narrow;
    const a = labels.find((l) => l.text === '500만' && l.side === 'l');
    const b = labels.find((l) => l.text === '446만' && l.side === 'r');
    expect(a && b, '두 글자가 마주 보는 자리에 선다').toBeTruthy();
    expect(problemsAtWidths(labels, ref)).toEqual([]);
  });

  it('글자 서식 = 목록과 같은 formatManWon — 1,000만 이상은 쉼표 · 1만 미만은 원 단위', () => {
    const p = txPlot([
      tx({ contract_ym: '202401', unit_price: 12_340_000 }),
      tx({ contract_ym: '202501', unit_price: 5_000 }),
      tx({ contract_ym: '202601', unit_price: 3_000_000 }),
      tx({ contract_ym: '202407', unit_price: 8_000_000 }),
      tx({ contract_ym: '202507', unit_price: 6_000_000 }),
    ])!;
    const texts = p.labels.wide.map((l) => l.text);
    expect(texts).toContain('1,234만');
    expect(texts).toContain('5,000원');
  });

  it('글자 폭 어림은 글자 수에 따라 늘고 넉넉하다(13px 숫자 ≈ 7.2px → 8 로)', () => {
    expect(txLabelWidth('900만')).toBe(4 + 8 * 3 + 14);
    expect(txLabelWidth('260만 ×2')).toBeGreaterThan(txLabelWidth('260만'));
    expect(txLabelWidth('1,000만')).toBe(4 + 8 * 4 + 4 + 14);
  });
});

/**
 * `needle` 이 처음 나오는 자리를 감싼 @media 머리들(바깥 → 안쪽). 없으면 null.
 * 못 보는 것: 주석 안의 중괄호·문자열 안의 중괄호(styles.css 주석에 `{` 가 있으면 어긋난다 — 주석을 먼저 지운다).
 */
function mediaAt(css: string, needle: string): string[] | null {
  const src = css.replace(/\/\*[\s\S]*?\*\//g, (m) => ' '.repeat(m.length));
  const at = src.indexOf(needle);
  if (at < 0) return null;
  const stack: Array<string | null> = [];
  let head = 0;
  for (let i = 0; i < at; i += 1) {
    if (src[i] === '{') {
      const sel = src.slice(head, i).trim();
      stack.push(sel.startsWith('@media') ? sel.replace(/\s+/g, ' ') : null);
      head = i + 1;
    } else if (src[i] === '}') {
      stack.pop();
      head = i + 1;
    } else if (src[i] === ';') {
      head = i + 1;
    }
  }
  return stack.filter((s): s is string => s !== null);
}

describe('CSS 가드 — 실거래 그림(결정 0038 §2-8·§2-9)', () => {
  // 윈도우 작업본은 CRLF · 저장소·CI 는 LF — 줄바꿈이 든 검색어를 쓰므로 LF 로 맞춰 읽는다(CLAUDE.md 줄바꿈 경고).
  const css = readFileSync('src/styles.css', 'utf8').replace(/\r\n/g, '\n');

  it('휴대폰 배치(글을 아래 줄로)는 `@media screen and (max-width: 720px)` 묶음에만 — 종이 모양이 안 바뀐다', () => {
    expect(mediaAt(css, "'band viz viz'")).toEqual(['@media screen and (max-width: 720px)']);
    expect(css.split("'band viz viz'")).toHaveLength(2);
    // 양성 대조 — 옛 묶음(@media (max-width: 720px))에 넣으면 걸린다.
    const moved = "@media (max-width: 720px) {\n  .x { grid-template-areas: 'band viz viz'; }\n}\n" + css.replace("'band viz viz'", "'zz'");
    expect(mediaAt(moved, "'band viz viz'")).toEqual(['@media (max-width: 720px)']);
  });

  it('띠 줄의 기본 칸 틀은 띠 칸 말고 고정 폭(줄마다 같은 값이 같은 자리) · 축 글 줄도 같은 틀', () => {
    const grid = 'grid-template-columns: 72px minmax(0, 2fr) minmax(0, 3fr) 88px;';
    expect(mediaAt(css, `.tx__bands--viz li {\n  ${grid}`)).toEqual([]);
    expect(css.split(grid)).toHaveLength(3);
    // 양성 대조 — 표본 칸을 auto 로 두면 이 틀이 사라진다.
    expect(css.replaceAll(grid, 'grid-template-columns: 72px minmax(0, 2fr) minmax(0, 3fr) auto;').split(grid)).toHaveLength(1);
  });

  it('점 꼴 색은 사실 토큰 · 층 미상 회색 · 빈 꼴 바탕색 — CSS 규칙(SVG 속성의 var() 금지)', () => {
    const rule = (sel: string) => new RegExp(`${sel.replace(/[.[\]'*>]/g, (c) => `\\${c}`)}\\s*\\{([^}]*)\\}`).exec(css)?.[1] ?? '';
    expect(rule('.tx__shape > *')).toMatch(/fill:\s*var\(--fact-3\)/);
    expect(rule('.tx__shape > *')).toMatch(/stroke:\s*var\(--fact-4\)/);
    expect(rule(".tx__shape[data-shape='na'] > *")).toMatch(/fill:\s*var\(--viz-na\)/);
    expect(rule(".tx__shape[data-hollow='1'] > *")).toMatch(/fill:\s*var\(--card\)/);
    // 양성 대조 — 없는 규칙은 빈 글.
    expect(rule(".tx__shape[data-hollow='9'] > *")).toBe('');
  });

  it('종이 — 점그림 덩어리에만 break-inside: avoid(카드 통째 아님) · 축 글은 띠 목록과 같은 장', () => {
    expect(mediaAt(css, '  .tx__plot,\n')).toEqual(['@media print']);
    const avoid = /\.tx__plot,[\s\S]*?\{\s*break-inside:\s*avoid;/.exec(css);
    expect(avoid).not.toBeNull();
    // 카드 통째(`.tx {` 다음 줄 break-inside)는 없다.
    expect(/\n\s*\.tx\s*\{\s*break-inside/.test(css)).toBe(false);
    expect(mediaAt(css, '.tx__axis {\n    break-before: avoid;')).toEqual(['@media print']);
  });
});
