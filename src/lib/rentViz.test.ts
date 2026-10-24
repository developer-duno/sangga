import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { RentStat, RentStatHistory } from '../types';
import {
  RENT_TREND_QUARTERS,
  isRentHistoryList,
  quarterSeq,
  rentStepWidths,
  rentTrend,
  trendGeometry,
} from './rentViz';

/** 운영 읽기 값(서울>강남>테헤란로 · 2026-10-24 — 천원/㎡). */
const COLLECTIVE = { '1': 74.6, '2': 32.48, '3': 23.54, '4': 23.73, '5': 25.0, '-1': 16.95, '6+': 22.7 };
const OFFICE = { '1': 38.99, '2': 31.4, '3': 27.09, '4': 26.6, '5': 26.51, '-1': 13.93, '11+': 28.62, '6-10': 26.8 };

const Q8 = ['2024Q3', '2024Q4', '2025Q1', '2025Q2', '2025Q3', '2025Q4', '2026Q1', '2026Q2'];

function stat(over: Partial<RentStat> = {}): RentStat {
  return {
    district_nm: '역삼역',
    rone_region_nm: '서울>강남>테헤란로',
    bld_type: '집합상가',
    quarter: '2026Q2',
    vacancy_rate: 6.74,
    rent_per_m2: 74.6,
    yield_rate: 1.91,
    ...over,
  };
}

function h(quarter: string, over: Partial<RentStatHistory> = {}): RentStatHistory {
  return {
    rone_region_nm: '서울>강남>테헤란로',
    bld_type: '집합상가',
    quarter,
    vacancy_rate: 5,
    rent_per_m2: 74,
    yield_rate: 1.5,
    income_yield_rate: 0.9,
    ...over,
  };
}

/** 8분기 · 마지막 분기 = 카드 줄 값. */
function eight(over: (q: string, i: number) => Partial<RentStatHistory> = () => ({})): RentStatHistory[] {
  return Q8.map((q, i) =>
    h(q, i === 7 ? { vacancy_rate: 6.74, rent_per_m2: 74.6, yield_rate: 1.91, ...over(q, i) } : over(q, i)),
  );
}

describe('rentStepWidths — 계단 막대 폭(%) · 세 잣대의 열쇠 규칙', () => {
  it('가장 비싼 구간이 100 · 나머지는 그 값에 비례', () => {
    const w = rentStepWidths(COLLECTIVE);
    expect(w.get('1')).toBe(100);
    expect(w.get('2')).toBeCloseTo((32.48 / 74.6) * 100, 10);
    expect(w.get('-1')).toBeCloseTo((16.95 / 74.6) * 100, 10);
    expect(w.get('6+')).toBeCloseTo((22.7 / 74.6) * 100, 10);
    expect([...w.keys()]).toEqual(['6+', '5', '4', '3', '2', '1', '-1']);
  });

  it('오피스 — 11+ · 6-10 둘 다', () => {
    expect([...rentStepWidths(OFFICE).keys()]).toEqual(['11+', '6-10', '5', '4', '3', '2', '1', '-1']);
  });

  it('★ 열쇠 겹침 — 셋 다 있으면 6+ 는 어느 층도 안 쓴다(막대 없음) · 6-10 만 있으면 11층 이상 자리는 6+', () => {
    const all = rentStepWidths({ '1': 50, '6+': 40, '6-10': 30, '11+': 20 });
    expect([...all.keys()]).toEqual(['11+', '6-10', '1']);
    const noTop = rentStepWidths({ '1': 50, '6+': 40, '6-10': 30 });
    expect([...noTop.keys()]).toEqual(['6+', '6-10', '1']);
  });

  it('모양 이상 · 0 이하 · 모르는 열쇠는 막대 없음(표와 같은 줄만)', () => {
    expect(rentStepWidths(null).size).toBe(0);
    expect(rentStepWidths([1, 2]).size).toBe(0);
    expect(rentStepWidths('x').size).toBe(0);
    const w = rentStepWidths({ '1': 40, '2': 0, '3': -1, '7': 99, '4': 'x' });
    expect([...w.entries()]).toEqual([['1', 100]]);
  });
});

describe('quarterSeq — 최근 n분기(옛 → 최근)', () => {
  it('해를 넘어간다', () => {
    expect(quarterSeq('2026Q2', 8)).toEqual(Q8);
    expect(quarterSeq('2025Q1', 2)).toEqual(['2024Q4', '2025Q1']);
  });
  it('못 읽으면 null', () => {
    expect(quarterSeq('2026Q5', 8)).toBeNull();
    expect(quarterSeq('202602', 8)).toBeNull();
    expect(quarterSeq(null, 8)).toBeNull();
    expect(quarterSeq('2026Q2', 0)).toBeNull();
  });
});

describe('trendGeometry — 그림마다 제 눈금 · 0 선 · 없는 값은 null', () => {
  it('양수만 — 위 끝 = niceCeil(최댓값) · 0 선 바닥 · 길이 비례', () => {
    const g = trendGeometry([2, 4, null, 7.65]);
    expect(g.top).toBe(10);
    expect(g.bottom).toBe(0);
    expect(g.zero).toBe(0);
    expect(g.bars[0]).toEqual({ bottom: 0, height: 20, neg: false });
    expect(g.bars[2]).toBeNull();
    expect(g.bars[3]?.height).toBeCloseTo(76.5, 10);
  });

  it('음수 — 0 선이 올라오고 음수 막대는 그 아래로', () => {
    const g = trendGeometry([1, -0.5]);
    expect(g.top).toBe(1);
    expect(g.bottom).toBe(0.5);
    expect(g.zero).toBeCloseTo(100 / 3, 10);
    expect(g.bars[1]?.neg).toBe(true);
    expect(g.bars[1]?.bottom).toBeCloseTo(0, 10);
    expect(g.bars[1]?.height).toBeCloseTo(100 / 3, 10);
  });

  it('0 은 값이다 — 높이 0 막대(null 아님) · 전부 0 이면 눈금 폭 0', () => {
    const g = trendGeometry([0, 0]);
    expect(g.bars).toEqual([
      { bottom: 0, height: 0, neg: false },
      { bottom: 0, height: 0, neg: false },
    ]);
  });
});

describe('rentTrend — 카드 줄 하나의 8분기 흐름', () => {
  it('★ 창 = 카드 줄 분기까지 8분기 · 그림 셋 · 눈금 글', () => {
    const t = rentTrend(eight(), stat())!;
    expect(t.first).toBe('2024년 3분기');
    expect(t.last).toBe('2026년 2분기');
    expect(t.charts.map((c) => c.key)).toEqual(['vacancy', 'rent', 'yield']);
    expect(t.charts.map((c) => c.scale)).toEqual(['눈금 0 ~ 10%', '눈금 0 ~ 100,000원', '눈금 0 ~ 2%']);
    expect(t.charts[0].bars).toHaveLength(RENT_TREND_QUARTERS);
    expect(t.charts[0].bars.map((b) => b.quarter)).toEqual(Q8);
    expect(t.hasGap).toBe(false);
  });

  it('★ 종류를 섞지 않는다 — 같은 조사구역의 다른 종류 줄은 안 쓴다', () => {
    const rows = [...eight(), ...Q8.map((q) => h(q, { bld_type: '오피스', vacancy_rate: 99 }))];
    const t = rentTrend(rows, stat())!;
    expect(t.charts[0].bars.every((b) => b.text !== '99%')).toBe(true);
  });

  it('★ 빠진 분기는 null 막대(→ 「–」) — 창 밖 분기는 안 쓴다', () => {
    const rows = [h('2024Q2', { vacancy_rate: 50 }), ...eight().filter((r) => r.quarter !== '2025Q1')];
    const t = rentTrend(rows, stat())!;
    const vac = t.charts[0];
    expect(vac.bars.find((b) => b.quarter === '2025Q1')?.geom).toBeNull();
    expect(vac.bars.find((b) => b.quarter === '2025Q1')?.text).toBeNull();
    expect(vac.aria).toContain('2025년 1분기 공표값 없음');
    expect(vac.scale).toBe('눈금 0 ~ 10%'); // 창 밖 50% 는 눈금에 안 든다
    expect(t.hasGap).toBe(true);
  });

  it('한 지표가 창 내내 없으면 그 그림만 뺀다', () => {
    const t = rentTrend(eight(() => ({ yield_rate: null })).map((r, i) => (i === 7 ? { ...r, yield_rate: 1.91 } : r)), stat())!;
    expect(t.charts.map((c) => c.key)).toEqual(['vacancy', 'rent', 'yield']);
    const t2 = rentTrend(eight(() => ({ vacancy_rate: null })), stat({ vacancy_rate: null }))!;
    expect(t2.charts.map((c) => c.key)).toEqual(['rent', 'yield']);
  });

  it.each([
    ['응답 없음', null, stat()],
    ['카드 줄 없음', eight(), undefined],
    ['분기를 못 읽음', eight(), stat({ quarter: '2026-2' })],
    ['같은 분기 둘', [...eight(), h('2025Q3')], stat()],
    ['마지막 분기 값이 카드 줄과 다름', eight((_q, i) => (i === 7 ? { rent_per_m2: 70 } : {})), stat()],
    ['마지막 분기 줄이 없음', eight().slice(0, 7), stat()],
    ['다른 조사구역', eight().map((r) => ({ ...r, rone_region_nm: '서울>강남>신사역' })), stat()],
    ['창 안 분기가 하나', [eight()[7]], stat()],
  ])('★ %s → null(흐름만 빠진다)', (_name, rows, s) => {
    expect(rentTrend(rows as RentStatHistory[] | null, s as RentStat | undefined)).toBeNull();
  });

  it('비율·나누기를 글자로 내지 않는다 · 금지어 0', () => {
    const t = rentTrend(eight(), stat())!;
    const texts = [t.first, t.last, ...t.charts.flatMap((c) => [c.label, c.scale, c.aria])];
    for (const s of texts) {
      expect(s).not.toMatch(/배\b|비율|퍼센트|추정|시세/);
      for (const w of ['적정가격', '적정가', '평가액', '감정가', '가치평가']) expect(s).not.toContain(w);
    }
  });
});

describe('isRentHistoryList — 응답 모양', () => {
  it('정상 · 빈 배열 통과', () => {
    expect(isRentHistoryList(eight())).toBe(true);
    expect(isRentHistoryList([])).toBe(true);
  });
  it.each([
    ['객체', { code: 'PGRST202' }],
    ['값이 글자', [h('2026Q2', { yield_rate: '1' as unknown as number })]],
    ['조사구역 없음', [{ ...h('2026Q2'), rone_region_nm: null }]],
    ['분기 없음', [{ ...h('2026Q2'), quarter: undefined }]],
  ])('%s → 거부', (_n, x) => {
    expect(isRentHistoryList(x)).toBe(false);
  });
});

/** `needle` 이 처음 나오는 자리를 감싼 @media 머리들(바깥 → 안쪽 · `floorIndustry.test` 의 같은 함수). 없으면 null. */
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

describe('CSS 가드 — 임대 계단 막대 · 8분기 흐름(결정 0038 C · V5)', () => {
  const css = readFileSync('src/styles.css', 'utf8').replace(/\r\n/g, '\n');
  const bodyAt = (needle: string) => {
    const at = css.indexOf(needle);
    return at < 0 ? '' : css.slice(css.indexOf('{', at) + 1, css.indexOf('}', at));
  };

  it('★ 사실 색(호박) — 층 목록 면적 막대(파랑 --accent)와 다른 색', () => {
    expect(bodyAt('\n.rent__step-fill {')).toMatch(/background:\s*var\(--fact-3\)/);
    expect(bodyAt('\n.rent-trend__bar {')).toMatch(/background:\s*var\(--fact-3\)/);
    expect(bodyAt('\n.floor__fill {')).toMatch(/background:\s*var\(--accent\)/);
  });

  it('★ 휴대폰 한 칸 규칙은 screen 720 묶음에만 · 기본(넓은 화면·종이)은 셋 한 줄 · 옛 720 묶음엔 없음', () => {
    expect(mediaAt(css, '\n.rent-trend__charts {')).toEqual([]);
    expect(bodyAt('\n.rent-trend__charts {')).toMatch(/grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\)/);
    const at = '  .rent-trend__charts {\n    grid-template-columns: minmax(0, 1fr);';
    expect(mediaAt(css, at)).toEqual(['@media screen and (max-width: 720px)']);
    const src = css.replace(/\/\*[\s\S]*?\*\//g, (m) => ' '.repeat(m.length));
    const heads: Array<string[] | null> = [];
    for (let i = src.indexOf('.rent-trend'); i >= 0; i = src.indexOf('.rent-trend', i + 1)) {
      heads.push(mediaAt(`${css.slice(0, i)}§`, '§'));
    }
    expect(heads.some((hd) => hd?.includes('@media (max-width: 720px)'))).toBe(false);
    // 양성 대조 — 옛 묶음에 넣으면 그 머리가 나온다.
    const moved = '@media (max-width: 720px) {\n  .rent-trend__charts {\n    gap: 1px;\n  }\n}\n' + css;
    expect(mediaAt(moved, '  .rent-trend__charts {\n    gap: 1px;')).toEqual(['@media (max-width: 720px)']);
  });

  it('★ 종이 — 흐름 덩어리만 avoid(카드 통째 아님)', () => {
    const at = '  .rent-trend,\n';
    expect(mediaAt(css, at)).toEqual(['@media print']);
    expect(bodyAt(at)).toMatch(/break-inside:\s*avoid/);
  });

  it('새 글자 칸은 처음부터 13px(S4)', () => {
    for (const sel of ['.rent-trend__cap', '.rent-trend__name', '.rent-trend__gap', '.rent-trend__note']) {
      expect(bodyAt(`\n${sel} {`), sel).toMatch(/font-size:\s*13px/);
    }
  });
});
