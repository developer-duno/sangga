import { readFileSync } from 'node:fs';
import { describe, it, expect } from 'vitest';
import { cssVar, pctOf, stackPct, VIZ_TONES } from './viz';

/**
 * 그림 좌표 함수(결정 0038 V1). 그림이 깨져도 글자 시험은 초록이다(§2-10) — 값 → 자리·폭을 숫자로 못 박는다.
 */

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

  /*
    흑백 종이에서 층 묶음 칸이 갈리나 — 호박 4단끼리는 **밝기**로, 층 미상은 **무늬**(흰 사선 빗금)로 가른다.
    못 보는 것: 층 미상 회색의 흑백 밝기는 1층 칸(--fact-2)과 비슷하다(183.0 vs 182.9) — 무늬로 가르고, 무늬가 실제로
    찍히는지는 E2E BD(종이 매체 computed background-image)가 본다. 짙은 회색으로 밝기를 가르면 '모르는 칸'이 가장 무거워 보여 쓰지 않는다.
  */
  it('흑백 종이에서도 호박 4단이 밝기로 갈린다(이웃 칸 차 ≥ 25) · 층 미상은 채도 낮은 회색 + 빗금 무늬', () => {
    const css = readFileSync('src/styles.css', 'utf8');
    const root = css.slice(css.indexOf(':root {'), css.indexOf('}', css.indexOf(':root {')));
    const rgb = (n: string) => {
      const m = new RegExp(`${n}\\s*:\\s*#([0-9a-f]{6})\\s*;`).exec(root);
      expect(m, n).not.toBeNull();
      const h = m![1];
      return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
    };
    const luma = ([r, g, b]: number[]) => 0.299 * r + 0.587 * g + 0.114 * b;
    const names = VIZ_TONES.fact.steps;
    const lum = names.map((n) => luma(rgb(n)));
    const tooClose: string[] = [];
    for (let i = 0; i < lum.length; i += 1) {
      for (let j = i + 1; j < lum.length; j += 1) {
        if (Math.abs(lum[i] - lum[j]) < 25) tooClose.push(`${names[i]}~${names[j]} ${Math.abs(lum[i] - lum[j]).toFixed(1)}`);
      }
    }
    expect(tooClose).toEqual([]);
    // 옅음 → 짙음 차례(지하 → 3층 이상).
    expect([...lum].sort((a, b) => b - a)).toEqual(lum);
    // 층 미상은 회색 — R·G·B 가 서로 16 안쪽(호박처럼 보이지 않게).
    const na = rgb(VIZ_TONES.na);
    expect(Math.max(...na) - Math.min(...na)).toBeLessThanOrEqual(16);
    // 층 미상 칸만 빗금 — 무늬 규칙이 있고, 그 색 토큰이 :root 에 있다.
    const hatch = /\.mix__stack-cell\[data-band='na'\]\s*\{[^}]*repeating-linear-gradient\([^)]*var\(--viz-na-hatch\)/;
    expect(hatch.test(css)).toBe(true);
    rgb('--viz-na-hatch');
    // 양성 대조 — 무늬 규칙을 지우면 걸린다.
    expect(hatch.test(css.replaceAll("[data-band='na']", "[data-band='xx']"))).toBe(false);
  });
});
