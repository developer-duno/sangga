import { readFileSync } from 'node:fs';
import { describe, it, expect } from 'vitest';
import { cssVar, niceCeil, pctOf, rangePct, stackPct, VIZ_TONES } from './viz';

/**
 * 그림 좌표 함수(결정 0038 V1). 그림이 깨져도 글자 시험은 초록이다(§2-10) — 값 → 자리·폭을 숫자로 못 박는다.
 */

describe('niceCeil — 축 상한 올림', () => {
  it('1·2·2.5·5 × 10ⁿ 가운데 값 이상인 가장 작은 수', () => {
    expect(niceCeil(1904.57)).toBe(2000);
    expect(niceCeil(2001)).toBe(2500);
    expect(niceCeil(2600)).toBe(5000);
    expect(niceCeil(5001)).toBe(10000);
    expect(niceCeil(120)).toBe(200);
    expect(niceCeil(0.37)).toBe(0.5);
    expect(niceCeil(7)).toBe(10);
  });

  it('상한과 같은 값이면 그 값 그대로(한 칸 더 올리지 않는다)', () => {
    expect(niceCeil(2000)).toBe(2000);
    expect(niceCeil(1000)).toBe(1000);
    expect(niceCeil(250)).toBe(250);
    expect(niceCeil(1)).toBe(1);
  });

  it('0 이하·NaN·무한대·null 이면 null', () => {
    expect(niceCeil(0)).toBeNull();
    expect(niceCeil(-5)).toBeNull();
    expect(niceCeil(Number.NaN)).toBeNull();
    expect(niceCeil(Number.POSITIVE_INFINITY)).toBeNull();
    expect(niceCeil(null)).toBeNull();
    expect(niceCeil(undefined)).toBeNull();
  });
});

describe('pctOf — 값 → 축 위 자리(%)', () => {
  it('0 은 0% · 상한은 100% · 가운데는 비례', () => {
    expect(pctOf(0, 2000)).toBe(0);
    expect(pctOf(2000, 2000)).toBe(100);
    expect(pctOf(500, 2000)).toBe(25);
    expect(pctOf(25.0, 100)).toBe(25);
  });

  it('상한보다 크면 100 에 붙인다(축 밖으로 안 나간다)', () => {
    expect(pctOf(2500, 2000)).toBe(100);
  });

  it('값 없음·NaN·음수 · 상한 0 이하면 null(0 으로 그리지 않는다)', () => {
    expect(pctOf(null, 100)).toBeNull();
    expect(pctOf(undefined, 100)).toBeNull();
    expect(pctOf(Number.NaN, 100)).toBeNull();
    expect(pctOf(-1, 100)).toBeNull();
    expect(pctOf(10, 0)).toBeNull();
    expect(pctOf(10, -100)).toBeNull();
    expect(pctOf(10, null)).toBeNull();
    expect(pctOf(10, Number.NaN)).toBeNull();
  });
});

describe('rangePct — 범위 → [왼쪽 %, 폭 %]', () => {
  it('p25~p75 를 같은 축에 놓는다', () => {
    const r = rangePct(746.5, 1904.6, 2000)!;
    expect(r.left).toBeCloseTo(37.325, 6);
    expect(r.width).toBeCloseTo(57.905, 6);
  });

  it('0 부터 상한까지면 0 · 100', () => {
    expect(rangePct(0, 2000, 2000)).toEqual({ left: 0, width: 100 });
  });

  it('lo = hi 면 폭 0(부르는 쪽이 눈금만 그린다)', () => {
    expect(rangePct(1000, 1000, 2000)).toEqual({ left: 50, width: 0 });
  });

  it('p25 > p75 · 값 없음 · NaN · 음수 · 상한 0 이면 null', () => {
    expect(rangePct(1500, 1000, 2000)).toBeNull();
    expect(rangePct(null, 1000, 2000)).toBeNull();
    expect(rangePct(100, null, 2000)).toBeNull();
    expect(rangePct(Number.NaN, 1000, 2000)).toBeNull();
    expect(rangePct(-10, 1000, 2000)).toBeNull();
    expect(rangePct(100, 1000, 0)).toBeNull();
  });
});

describe('stackPct — 쌓은 막대 칸 나누기', () => {
  it('칸마다 n ÷ 합 · 차례 그대로 · 합 100', () => {
    const s = stackPct([
      { key: 'b', n: 2 },
      { key: '1', n: 90 },
      { key: '2', n: 24 },
      { key: '3+', n: 9 },
      { key: 'na', n: 25 },
    ])!;
    expect(s.map((x) => x.key)).toEqual(['b', '1', '2', '3+', 'na']);
    expect(s[1].pct).toBeCloseTo(60, 6);
    expect(s.reduce((a, x) => a + x.pct, 0)).toBeCloseTo(100, 9);
  });

  it('0 인 칸은 뺀다(최소 폭 강제 금지)', () => {
    const s = stackPct([
      { key: 'b', n: 0 },
      { key: '1', n: 36 },
      { key: '2', n: 9 },
      { key: '3+', n: 3 },
      { key: 'na', n: 12 },
    ])!;
    expect(s.map((x) => x.key)).toEqual(['1', '2', '3+', 'na']);
    expect(s[0].pct).toBeCloseTo(60, 6);
  });

  it('한 칸만 있으면 그 칸이 100%', () => {
    expect(stackPct([{ key: 'b', n: 0 }, { key: '1', n: 5 }])).toEqual([{ key: '1', pct: 100 }]);
  });

  it('합 0 · 음수 · NaN · 빈 목록이면 null(그림 전체를 안 그린다)', () => {
    expect(stackPct([{ key: 'a', n: 0 }, { key: 'b', n: 0 }])).toBeNull();
    expect(stackPct([{ key: 'a', n: -1 }, { key: 'b', n: 5 }])).toBeNull();
    expect(stackPct([{ key: 'a', n: Number.NaN }, { key: 'b', n: 5 }])).toBeNull();
    expect(stackPct([])).toBeNull();
  });
});

describe('VIZ_TONES — 색 두 벌은 CSS 변수 이름', () => {
  it('사실(호박 진하기 4단)과 추정(회청)이 갈라져 있고 이름이 전부 -- 로 시작한다', () => {
    expect(VIZ_TONES.fact.steps).toHaveLength(4);
    const all = [
      VIZ_TONES.fact.bg,
      VIZ_TONES.fact.line,
      ...VIZ_TONES.fact.steps,
      ...Object.values(VIZ_TONES.est),
      VIZ_TONES.na,
    ];
    for (const n of all) expect(n).toMatch(/^--[a-z][a-z0-9-]*$/);
    // 추정 쪽에 사실 진하기가 섞이지 않는다.
    for (const n of Object.values(VIZ_TONES.est)) expect(VIZ_TONES.fact.steps).not.toContain(n);
    expect(cssVar('--est-ink')).toBe('var(--est-ink)');
  });

  it('이름마다 styles.css 의 :root 에 값이 있다(없는 변수로 칠하면 그림이 말없이 투명해진다)', () => {
    const css = readFileSync('src/styles.css', 'utf8');
    const root = css.slice(css.indexOf(':root {'), css.indexOf('}', css.indexOf(':root {')));
    const names = new Set([
      VIZ_TONES.fact.bg,
      VIZ_TONES.fact.line,
      ...VIZ_TONES.fact.steps,
      ...Object.values(VIZ_TONES.est),
      VIZ_TONES.na,
    ]);
    const declared = (n: string) => new RegExp(`${n}\\s*:\\s*#[0-9a-f]{6}\\s*;`).test(root);
    for (const n of names) expect(declared(n), n).toBe(true);
    // 양성 대조 — 없는 이름은 걸린다.
    expect(declared('--viz-nope')).toBe(false);
  });
});
