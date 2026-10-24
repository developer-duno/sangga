import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { FloorIndustryRow } from '../types';
import {
  FLOOR_INDUSTRY_CATS,
  FLOOR_INDUSTRY_LEGEND_LEAD,
  bandLabel,
  bandSegments,
  floorIndustryView,
  industryCatOf,
  legendCats,
  parseFloorIndustry,
  placelessStoresText,
  unknownStoresText,
} from './floorIndustry';

function r(floor_no: number | null, cat_l_cd: string | null, store_cnt: number, cat_l_nm: string | null = null): FloorIndustryRow {
  return { floor_no, cat_l_cd, cat_l_nm, store_cnt };
}

/** 층 목록 — 강남파이낸스센터 꼴의 작은 판(41·2·1·지하 1 · 3층은 점포 0). */
const FLOORS = [
  { floor_no: 41, store_cnt: 38 },
  { floor_no: 3, store_cnt: 0 },
  { floor_no: 2, store_cnt: 8 },
  { floor_no: 1, store_cnt: 14 },
  { floor_no: -1, store_cnt: 3 },
];

const ROWS: FloorIndustryRow[] = [
  r(41, 'M1', 26, '과학·기술'),
  r(41, 'P1', 5, '교육'),
  r(41, 'G2', 3, '소매'),
  r(41, 'S2', 4, '수리·개인'),
  r(7, 'I2', 2, '음식'), // 층 목록에 없는 층
  r(2, 'I2', 5, '음식'),
  r(2, 'G2', 2, '소매'),
  r(2, 'N1', 1, '시설관리·임대'),
  r(1, 'I2', 12, '음식'),
  r(1, 'M1', 1, '과학·기술'),
  r(1, 'G2', 1, '소매'),
  r(-1, 'I2', 3, '음식'),
  r(null, 'I2', 10, '음식'),
  r(null, 'G2', 5, '소매'),
  r(null, 'S2', 3, '수리·개인'),
  r(null, null, 2),
];

describe('industryCatOf — 범주 고정 표(§2-7)', () => {
  it('다섯 대분류만 제 색 · 나머지·빈 코드·모르는 코드는 「그 밖」', () => {
    expect(['I2', 'G2', 'M1', 'P1', 'L1'].map(industryCatOf)).toEqual(['food', 'retail', 'sci', 'edu', 'realty']);
    for (const cd of ['S2', 'N1', 'R1', 'I1', 'Q1', 'ZZ', '', ' ', null, undefined]) {
      expect(industryCatOf(cd), String(cd)).toBe('other');
    }
    expect(industryCatOf(' I2 ')).toBe('food');
  });

  it('차례·이름·색 이름 고정 — 음식 · 소매 · 과학·기술 · 교육 · 부동산 · 그 밖', () => {
    expect(FLOOR_INDUSTRY_CATS.map((c) => [c.label, c.token])).toEqual([
      ['음식', '--ind-food'],
      ['소매', '--ind-retail'],
      ['과학·기술', '--ind-sci'],
      ['교육', '--ind-edu'],
      ['부동산', '--ind-realty'],
      ['그 밖', '--ind-other'],
    ]);
  });
});

describe('parseFloorIndustry — 응답 모양', () => {
  it('정상 줄 · 빈 배열은 그대로', () => {
    expect(parseFloorIndustry(ROWS)).toEqual(ROWS);
    expect(parseFloorIndustry([])).toEqual([]);
  });

  it('하나라도 어긋나면 통째로 null', () => {
    const bad: unknown[] = [
      null,
      {},
      'x',
      [r(0, 'I2', 1)], // 층 0 은 없다(절대 규칙 4)
      [r(1.5, 'I2', 1)],
      [{ ...r(1, 'I2', 1), floor_no: '1' }],
      [r(1, 'I2', 0)], // 0 인 줄은 서버가 안 준다
      [r(1, 'I2', -1)],
      [{ ...r(1, 'I2', 1), store_cnt: '3' }],
      [{ ...r(1, 'I2', 1), cat_l_cd: 3 }],
      [{ ...r(1, 'I2', 1), cat_l_nm: 3 }],
      [r(1, 'I2', 1), null],
    ];
    for (const d of bad) expect(parseFloorIndustry(d), JSON.stringify(d)).toBeNull();
  });
});

describe('floorIndustryView — 띠 합 = 그 층 store_cnt (결정 0038 D)', () => {
  const v = floorIndustryView(ROWS, FLOORS)!;

  it('★ 층 목록의 층마다 띠 합 = 그 층 「점포 N」', () => {
    for (const f of FLOORS) expect(v.byFloor.get(f.floor_no)?.total ?? 0, String(f.floor_no)).toBe(f.store_cnt);
    expect(v.byFloor.has(3)).toBe(false); // 점포 0 층은 띠 없음
    expect(v.max).toBe(38);
  });

  it('★ 한 층이라도 어긋나면 통째로 null(띠와 옆 글이 다른 수를 말하지 않게)', () => {
    expect(floorIndustryView(ROWS, FLOORS.map((f) => (f.floor_no === 2 ? { ...f, store_cnt: 9 } : f)))).toBeNull();
    expect(floorIndustryView(ROWS, FLOORS.map((f) => (f.floor_no === 3 ? { ...f, store_cnt: 1 } : f)))).toBeNull();
    // store_cnt 를 모르는 층에 띠가 오면 어긋남(모르는 수 옆에 띠를 안 그린다) · 띠도 없으면 그대로.
    expect(floorIndustryView(ROWS, FLOORS.map((f) => (f.floor_no === 1 ? { ...f, store_cnt: null } : f)))).toBeNull();
    expect(floorIndustryView(ROWS, FLOORS.map((f) => (f.floor_no === 3 ? { ...f, store_cnt: null } : f)))).not.toBeNull();
  });

  it('띠 안 차례 = 범주 고정 차례 · 「그 밖」은 나머지 대분류와 빈 코드를 합친다', () => {
    expect(v.byFloor.get(41)!.parts).toEqual([
      { key: 'retail', n: 3 },
      { key: 'sci', n: 26 },
      { key: 'edu', n: 5 },
      { key: 'other', n: 4 },
    ]);
    expect(v.byFloor.get(2)!.parts).toEqual([
      { key: 'food', n: 5 },
      { key: 'retail', n: 2 },
      { key: 'other', n: 1 },
    ]);
  });

  it('층 모름(na) 한 묶음 · 자리 없는 점포(층 목록에 없는 층)', () => {
    expect(v.unknown).toEqual({
      total: 20,
      parts: [
        { key: 'food', n: 10 },
        { key: 'retail', n: 5 },
        { key: 'other', n: 5 },
      ],
    });
    expect(v.placeless).toEqual({ total: 2, floors: [{ floor_no: 7, n: 2 }] });
  });

  it('없으면 null — 층 모름·자리 없는 점포 줄이 안 선다 · 빈 응답도 층 목록이 전부 0 이면 정상', () => {
    const plain = floorIndustryView(
      ROWS.filter((x) => x.floor_no !== null && x.floor_no !== 7),
      FLOORS,
    )!;
    expect(plain.unknown).toBeNull();
    expect(plain.placeless).toBeNull();
    const empty = floorIndustryView([], [{ floor_no: 1, store_cnt: 0 }])!;
    expect(empty.byFloor.size).toBe(0);
    expect(empty.max).toBe(0);
    expect(floorIndustryView([], [{ floor_no: 1, store_cnt: 2 }])).toBeNull();
  });

  it('자리 없는 층은 위층 먼저', () => {
    const p = floorIndustryView([r(-3, 'I2', 1), r(9, 'I2', 2), r(5, null, 1)], [{ floor_no: 1, store_cnt: 0 }])!.placeless!;
    expect(p.floors.map((f) => f.floor_no)).toEqual([9, 5, -3]);
    expect(p.total).toBe(4);
  });
});

describe('bandSegments — 폭 %', () => {
  const v = floorIndustryView(ROWS, FLOORS)!;

  it('조각 폭 = n ÷ 가장 많은 층 × 100 · 가장 많은 층은 합 100 · 다른 층은 그 층 점포 수 비율만큼', () => {
    const top = bandSegments(v.byFloor.get(41)!, v.max)!;
    expect(top.map((s) => s.pct)).toEqual([(3 / 38) * 100, (26 / 38) * 100, (5 / 38) * 100, (4 / 38) * 100]);
    expect(top.reduce((s, x) => s + x.pct, 0)).toBeCloseTo(100, 9);
    const one = bandSegments(v.byFloor.get(1)!, v.max)!;
    expect(one.reduce((s, x) => s + x.pct, 0)).toBeCloseTo((14 / 38) * 100, 9);
    expect(one.map((s) => s.key)).toEqual(['food', 'retail', 'sci']);
  });

  it('자가 0·음수·NaN 이거나 띠가 자보다 크면 null(그리지 않는다)', () => {
    const b = v.byFloor.get(1)!;
    for (const m of [0, -1, Number.NaN, Number.POSITIVE_INFINITY, 13]) expect(bandSegments(b, m), String(m)).toBeNull();
  });
});

describe('글 — 범례 · 층 모름 · 자리 없는 점포 · 띠 이름', () => {
  const v = floorIndustryView(ROWS, FLOORS)!;

  it('범례 머리에 「대분류」·「이 땅의 가게」·펼친 목록은 「소분류」(👤 결정 D)', () => {
    expect(FLOOR_INDUSTRY_LEGEND_LEAD).toContain('대분류');
    expect(FLOOR_INDUSTRY_LEGEND_LEAD).toContain('이 땅의 가게');
    expect(FLOOR_INDUSTRY_LEGEND_LEAD).toContain('소분류');
  });

  it('범례 범주 = 그려진 띠에 든 것만 · 고정 차례(층 모름에만 있는 범주는 범례에 안 든다)', () => {
    expect(legendCats(v)).toEqual(['food', 'retail', 'sci', 'edu', 'other']);
    const onlyNa = floorIndustryView([r(null, 'L1', 2), r(1, 'I2', 1)], [{ floor_no: 1, store_cnt: 1 }])!;
    expect(legendCats(onlyNa)).toEqual(['food']);
  });

  it('층 모름 줄 · 자리 없는 점포 줄 · 띠 이름', () => {
    expect(unknownStoresText(v.unknown!)).toBe(
      '층 모름 20곳 — 원본에 층이 비어 있거나 읽을 수 없는 가게, 숫자 없이 "지하"라고만 적힌 가게 (음식 10 · 소매 5 · 그 밖 5)',
    );
    expect(placelessStoresText({ total: 3, floors: [{ floor_no: 7, n: 2 }, { floor_no: -3, n: 1 }] })).toBe(
      '자리 없는 점포 3곳 — 이 건물 층 목록에 없는 층에 적힌 가게 (7층 2곳 · 지하 3층 1곳)',
    );
    expect(bandLabel(1, null, v.byFloor.get(1)!)).toBe('1층 가게 업종(대분류): 음식 12곳 · 소매 1곳 · 과학·기술 1곳');
    expect(bandLabel(-1, null, v.byFloor.get(-1)!)).toBe('지하 1층 가게 업종(대분류): 음식 3곳');
  });

  it('비율 글 0 · 금지어 0', () => {
    const texts = [
      FLOOR_INDUSTRY_LEGEND_LEAD,
      unknownStoresText(v.unknown!),
      placelessStoresText(v.placeless!),
      ...[...v.byFloor.entries()].map(([no, b]) => bandLabel(no, null, b)),
    ];
    for (const t of texts) {
      expect(t).not.toMatch(/%|퍼센트|비율/);
      for (const w of ['적정가격', '적정가', '평가액', '감정가', '가치평가']) expect(t).not.toContain(w);
    }
  });
});

/** `needle` 이 처음 나오는 자리를 감싼 @media 머리들(바깥 → 안쪽 · `unitViz.test` 의 같은 함수). 없으면 null. */
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

/**
 * 층 줄 칸 틀(`grid-template-columns` · `gap` · 안쪽 여백 10 · 테두리 1)에서 막대 칸의 왼·오른 바깥 거리(px).
 * 막대 칸 = 둘째 칸(`minmax(…, 1fr)`) — 그 앞 칸 하나 · 뒤 칸 다섯.
 */
function barInset(cols: string, gap: number): { left: number; right: number } {
  const parts = cols.replace(/minmax\([^)]*\)/, 'BAR').trim().split(/\s+/);
  const px = (s: string) => Number(/^(\d+)px$/.exec(s)?.[1] ?? Number.NaN);
  const bar = parts.indexOf('BAR');
  const before = parts.slice(0, bar).map(px);
  const after = parts.slice(bar + 1).map(px);
  const edge = 1 + 10;
  return {
    left: edge + before.reduce((s, x) => s + x, 0) + gap * before.length,
    right: edge + after.reduce((s, x) => s + x, 0) + gap * after.length,
  };
}

describe('CSS 가드 — 층 목록 업종 띠(결정 0038 D · V4)', () => {
  const css = readFileSync('src/styles.css', 'utf8').replace(/\r\n/g, '\n');
  const rule = (sel: string, src = css) =>
    new RegExp(`(?:^|\\n)\\s*${sel.replace(/[.+[\]=']/g, (c) => `\\${c}`)}\\s*\\{([^}]*)\\}`).exec(src)?.[1] ?? '';
  const margin = (body: string) => /margin:\s*([^;]+);/.exec(body)?.[1].trim() ?? '';

  it('★ 띠의 왼·오른 바깥 여백 = 층 줄 칸 틀에서 셈한 막대 칸 자리(넓은 화면 기본)', () => {
    const row = rule('.floor__row');
    const cols = /grid-template-columns:\s*([^;]+);/.exec(row)![1];
    const gap = Number(/gap:\s*(\d+)px/.exec(row)![1]);
    expect(row).toMatch(/padding:\s*9px 10px/);
    expect(row).toMatch(/border:\s*1px solid/);
    const { left, right } = barInset(cols, gap);
    expect([left, right]).toEqual([97, 505]);
    expect(margin(rule('.floor__ind'))).toBe(`-8px ${right}px 4px ${left}px`);
    // 양성 대조 — 칸 하나를 넓히면 셈이 달라진다.
    expect(barInset(cols.replace('118px', '130px'), gap).right).toBe(517);
  });

  it('★ 1024~1279 두 칸 — 줄인 칸 틀과 같은 묶음 · 같은 셈', () => {
    const at = '    .app--wide .floor__ind {';
    expect(mediaAt(css, at)).toEqual(['@media screen and (min-width: 1024px)', '@media (max-width: 1279px)']);
    const rowBody = /\n {4}\.app--wide \.floor__row \{([^}]*)\}/.exec(css)![1];
    const cols = /grid-template-columns:\s*([^;]+);/.exec(rowBody)![1];
    const gap = Number(/gap:\s*(\d+)px/.exec(rowBody)![1]);
    const { left, right } = barInset(cols, gap);
    expect([left, right]).toEqual([83, 427]);
    const body = /\n {4}\.app--wide \.floor__ind \{([^}]*)\}/.exec(css)![1];
    expect(margin(body)).toBe(`-8px ${right}px 4px ${left}px`);
  });

  it('휴대폰(넷째 줄 · 폭 전체)은 screen 720 묶음에만(옛 720 묶음 금지 — 종이가 바뀐다)', () => {
    expect(mediaAt(css, '  .floor__ind {\n    margin: -6px 11px 4px;')).toEqual(['@media screen and (max-width: 720px)']);
    expect(mediaAt(css, '\n.floor__ind {\n')).toEqual([]);
    // 양성 대조 — 옛 묶음에 넣으면 그 머리가 나온다.
    const moved = '@media (max-width: 720px) {\n  .floor__ind {\n    margin: 0 9px;\n  }\n}\n' + css;
    expect(mediaAt(moved, '  .floor__ind {\n    margin: 0 9px;')).toEqual(['@media (max-width: 720px)']);
  });

  it('범주 색 여섯 — :root 에 결정 시안 값 · 조각·견본 둘 다 칠한다', () => {
    const root = rule(':root');
    const want: Record<string, string> = {
      '--ind-food': '#2a78d6',
      '--ind-retail': '#eb6834',
      '--ind-sci': '#1baf7a',
      '--ind-edu': '#eda100',
      '--ind-realty': '#e87ba4',
      '--ind-other': '#9a9ca6',
    };
    for (const c of FLOOR_INDUSTRY_CATS) {
      expect(root, c.token).toContain(`${c.token}: ${want[c.token]};`);
      const body = new RegExp(
        `\\.floor__ind-seg\\[data-cat='${c.key}'\\],\\n\\.floor__ind-swatch\\[data-cat='${c.key}'\\]\\s*\\{([^}]*)\\}`,
      ).exec(css)?.[1];
      expect(body, c.key).toMatch(new RegExp(`background:\\s*var\\(${c.token}\\)`));
    }
  });

  it('조각 사이 흰 줄은 box-shadow(자리를 안 먹는다) · 조각에 border 없음 · 미리 잡은 자리는 안 보임(자리는 남는다)', () => {
    expect(rule('.floor__ind-seg + .floor__ind-seg')).toMatch(/box-shadow:\s*inset 2px 0 0 var\(--card\)/);
    expect(rule('.floor__ind-seg')).not.toMatch(/border:|border-left|border-right/);
    expect(rule('.floor__ind.floor__ind--pending')).toMatch(/visibility:\s*hidden/);
    expect(rule('.floor__ind.floor__ind--pending')).not.toMatch(/display:\s*none/);
  });

  it('카드 아래 줄 글자 13px(기본 규칙 — 종이도)', () => {
    const body = /\n\.floor__ind-legend,\n\.floor__ind-unknown,\n\.floor__ind-placeless \{([^}]*)\}/.exec(css)?.[1] ?? '';
    expect(body).toMatch(/font-size:\s*13px/);
  });
});
