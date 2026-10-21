import { readFileSync } from 'node:fs';
import { describe, it, expect } from 'vitest';
import type { ParcelTransaction, SigunguTxStat } from '../types';
import {
  TX_PLOT_MIN,
  TX_SHAPE_ORDER,
  txBandAxisMaxWon,
  txBandMark,
  txPlot,
  txPlotShows,
  txShape,
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
  it('4건이면 null · 5건이면 점 5개', () => {
    expect(txPlot(Array.from({ length: 4 }, () => tx()))).toBeNull();
    expect(txPlot(Array.from({ length: 5 }, () => tx()))!.points).toHaveLength(5);
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
