import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { FloorUnit } from '../types';
import { txLabelWidth } from './txViz';
import {
  UNIT_CELLS_NOTE,
  UNIT_CELL_MAX,
  UNIT_CELL_PAD,
  UNIT_CELL_REF,
  UNIT_CELL_REST_GAP,
  UNIT_CELL_SEP,
  unitCellLabelFits,
  unitCellText,
  unitCells,
  unitNameIsBlank,
  unitCellsBlankText,
  unitCellsRestText,
} from './unitViz';

/** 호 하나. `total` 은 그 층 전체 호 수(모든 줄에 같은 값 — 서버와 같다). */
function u(ho: string | null, area: number | null, total = 4): FloorUnit {
  return { ho, excl_area_m2: area, total_cnt: total };
}

/** n 호(면적 같음) — 이름 `n-001호` 꼴. */
function many(n: number, total: number, area = 4): FloorUnit[] {
  return Array.from({ length: n }, (_, i) => u(`${String(i + 1).padStart(3, '0')}호`, area, total));
}

const REF = { wide: 480, narrow: 230 };

describe('unitCells — 폭 % (결정 0038 G1)', () => {
  it('칸 폭 = 그 호 면적 ÷ 칸 줄에 그린 호 면적 합 · 목록 차례 그대로 · 합 100', () => {
    const c = unitCells([u('101호', 300), u('102호', 150), u('103호', 20), u('104호', 0)], 4, REF)!;
    expect(c.cells.map((x) => x.text)).toEqual(['101호 · 300.0㎡', '102호 · 150.0㎡', '103호 · 20.0㎡']);
    expect(c.cells.map((x) => x.pct)).toEqual([(300 / 470) * 100, (150 / 470) * 100, (20 / 470) * 100]);
    expect(c.cells.reduce((s, x) => s + x.pct, 0)).toBeCloseTo(100, 9);
    expect(c.blanks).toEqual(['104호']);
    expect(c.rest).toBe(0);
  });

  it('호 하나면 칸 하나가 100%', () => {
    const c = unitCells([u('B01호', 12.5, 1)], 1, REF)!;
    expect(c.cells).toHaveLength(1);
    expect(c.cells[0].pct).toBe(100);
  });

  it('칸 글자는 목록과 같은 서식 함수(이름 원문 · 면적 소수 첫째 자리)', () => {
    expect(unitCellText('101호', 54)).toBe('101호 · 54.0㎡');
    expect(unitCellText('B01', 1234.56)).toBe('B01 · 1,234.6㎡');
  });

  it('★ 이름이 사실상 없으면 면적만(👤 2026-10-22 — 운영 「호 · 793.8㎡」 결함) · 「호」가 든 진짜 이름은 그대로', () => {
    for (const ho of [null, '', '  ', '호', ' 호 ']) {
      expect(unitNameIsBlank(ho), String(ho)).toBe(true);
      expect(unitCellText(ho, 793.8), String(ho)).toBe('793.8㎡');
    }
    // 양성 대조 — 이름이 있는 꼴은 이름을 지우지 않는다.
    for (const ho of ['101호', '호1', '1호', '가']) {
      expect(unitNameIsBlank(ho), ho).toBe(false);
      expect(unitCellText(ho, 10)).toBe(`${ho} · 10.0㎡`);
    }
    // 칸 줄에서도 — 빈 이름 칸은 면적만 글자로.
    const c = unitCells([u('호', 793.8, 2), u('101호', 10, 2)], 2, REF)!;
    expect(c.cells.map((x) => x.text)).toEqual(['793.8㎡', '101호 · 10.0㎡']);
  });
});

describe('unitCells — 50칸 상한과 「그 밖 N호」 (G3)', () => {
  it('543호 층 첫 쪽 50줄 → 칸 50 · 그 밖 493호', () => {
    const c = unitCells(many(50, 543), 543, REF)!;
    expect(c.cells).toHaveLength(UNIT_CELL_MAX);
    expect(c.rest).toBe(493);
    expect(unitCellsRestText(c.rest)).toBe('그 밖 493호');
  });

  it('더 보기로 목록이 100줄이 돼도 칸은 첫 50호 그대로 · 그 밖 = 전체 − 50', () => {
    const units = many(100, 543);
    units[60] = u('061호', 9999, 543); // 50 줄 밖의 큰 호 — 칸 폭 셈에 들어가면 안 된다
    const c = unitCells(units, 543, REF)!;
    expect(c.cells).toHaveLength(50);
    expect(c.cells.every((x) => Math.abs(x.pct - 2) < 1e-9)).toBe(true);
    expect(c.rest).toBe(493);
  });

  it('경계 — 딱 50호 층은 그 밖 없음 · 51호 층은 그 밖 1호', () => {
    expect(unitCells(many(50, 50), 50, REF)!.rest).toBe(0);
    const c51 = unitCells(many(51, 51), 51, REF)!;
    expect(c51.cells).toHaveLength(50);
    expect(c51.rest).toBe(1);
  });

  it('전체 수를 모르면(null) 받은 줄 수로 센다', () => {
    expect(unitCells(many(51, 0), null, REF)!.rest).toBe(1);
    expect(unitCells(many(3, 0), null, REF)!.rest).toBe(0);
  });

  it('그 밖 수는 천 단위 쉼표', () => {
    expect(unitCellsRestText(1234)).toBe('그 밖 1,234호');
  });
});

describe('unitCells — 면적 0 이하는 칸 없이 「–」 (G4 · 원칙 4)', () => {
  it('0 · 음수 · null · NaN · 무한대는 칸이 아니라 이름 목록으로 — 0 너비 칸을 만들지 않는다', () => {
    const c = unitCells(
      [u('A', 10), u('B', 0), u('C', -3), u('D', null), u('E', Number.NaN), u('F', Number.POSITIVE_INFINITY), u('G', 30)],
      7,
      REF,
    )!;
    expect(c.cells.map((x) => x.text)).toEqual(['A · 10.0㎡', 'G · 30.0㎡']);
    expect(c.cells.map((x) => x.pct)).toEqual([25, 75]);
    expect(c.cells.every((x) => x.pct > 0)).toBe(true);
    expect(c.blanks).toEqual(['B', 'C', 'D', 'E', 'F']);
  });

  it('전부 면적이 없으면 칸 0 + 이름만(칸 줄을 안 그린다)', () => {
    const c = unitCells([u('101호', 0), u('102호', null)], 2, REF)!;
    expect(c.cells).toEqual([]);
    expect(c.blanks).toEqual(['101호', '102호']);
  });

  it('「–」 한 줄 — 다섯까지 이름, 넘으면 「외 N호」 · 없으면 null', () => {
    expect(unitCellsBlankText([])).toBeNull();
    expect(unitCellsBlankText(['104호'])).toBe('전용면적 값이 없는 호(칸 없음): 104호 –');
    expect(unitCellsBlankText(['a', 'b', 'c', 'd', 'e', 'f', 'g'])).toBe(
      '전용면적 값이 없는 호(칸 없음): a – · b – · c – · d – · e – 외 2호',
    );
  });
});

describe('unitCells — 목록 0줄 층 (G6)', () => {
  it('목록이 0줄이면 null — 주거·오피스텔·미상 층은 칸도 없다', () => {
    expect(unitCells([], 0, REF)).toBeNull();
    expect(unitCells([], null, REF)).toBeNull();
  });
});

describe('unitCells — 넓은 칸에만 글자 (G8 · 가장 좁은 폭 기준 계산)', () => {
  it('판정 = 칸 폭(기준 폭 × %) ≥ 글자 폭 어림 + 좌우 여백 + 칸 사이 줄 — 같으면 넣고 1px 모자라면 안 넣는다', () => {
    const text = '101호 · 54.0㎡';
    const need = txLabelWidth(text) + 2 * UNIT_CELL_PAD + UNIT_CELL_SEP;
    expect(unitCellLabelFits(50, text, need * 2)).toBe(true);
    expect(unitCellLabelFits(50, text, need * 2 - 2)).toBe(false);
  });

  it('벌마다 따로 — 31.9% 칸은 넓은 기준(480)에선 글자, 휴대폰 기준(230)에선 없음 · 4.3% 칸은 둘 다 없음', () => {
    const c = unitCells([u('101호', 300), u('102호', 150), u('103호', 20)], 3, REF)!;
    expect(c.cells.map((x) => [x.labWide, x.labNarrow])).toEqual([
      [true, true],
      [true, false],
      [false, false],
    ]);
  });

  it('「그 밖 N호」가 줄 끝에 서면 칸 줄이 좁아진 만큼 빼고 판정한다', () => {
    const text = unitCellText('001호', 100);
    const need = txLabelWidth(text) + 2 * UNIT_CELL_PAD + UNIT_CELL_SEP;
    // 칸 하나가 100%, 기준 폭이 딱 글자 폭 — 그 밖이 없으면 들어가고, 그 밖이 붙으면 그 글 폭만큼 모자라 빠진다.
    const units = [u('001호', 100, 1)];
    expect(unitCells(units, 1, { wide: need, narrow: need })!.cells[0].labWide).toBe(true);
    const withRest = unitCells([u('001호', 100, 60)], 60, { wide: need, narrow: need })!;
    expect(withRest.rest).toBe(59);
    expect(withRest.cells[0].labWide).toBe(false);
    const restW = txLabelWidth(unitCellsRestText(59)) + UNIT_CELL_REST_GAP;
    expect(unitCells([u('001호', 100, 60)], 60, { wide: need + restW, narrow: need })!.cells[0].labWide).toBe(true);
  });

  it('기준 폭 표 — 펼친 상세 세 칸 위 전체 폭(넓은 500 · 휴대폰 180 · 👤 2026-10-22) · 인쇄 구성표(넓은 480 · 휴대폰 230)', () => {
    expect(UNIT_CELL_REF).toEqual({ detail: { wide: 500, narrow: 180 }, print: { wide: 480, narrow: 230 } });
  });
});

describe('unitViz — 글 (G2 · G9)', () => {
  it('설명 글 원문 · 금지어 0 · 새 비율 글 0(% 는 그림 좌표일 뿐)', () => {
    expect(UNIT_CELLS_NOTE).toBe('크기 비교이지 자리 배치가 아닙니다.');
    const c = unitCells([u('101호', 300), u('102호', 0)], 60, REF)!;
    const texts = [UNIT_CELLS_NOTE, ...c.cells.map((x) => x.text), unitCellsRestText(c.rest), unitCellsBlankText(c.blanks)!];
    for (const t of texts) {
      expect(t).not.toMatch(/%|퍼센트|비율/);
      for (const w of ['적정가격', '적정가', '평가액', '감정가', '가치평가']) expect(t).not.toContain(w);
    }
  });
});

/** `needle` 이 처음 나오는 자리를 감싼 @media 머리들(바깥 → 안쪽 · `txViz.test` 의 같은 함수). 없으면 null. */
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

describe('CSS 가드 — 호실 크기 칸(결정 0038 G · V3)', () => {
  // 윈도우 작업본은 CRLF · 저장소·CI 는 LF — LF 로 맞춰 읽는다.
  const css = readFileSync('src/styles.css', 'utf8').replace(/\r\n/g, '\n');
  const rule = (sel: string, src = css) =>
    new RegExp(`(?:^|\\n)${sel.replace(/[.+]/g, (c) => `\\${c}`)}\\s*\\{([^}]*)\\}`).exec(src)?.[1] ?? '';

  it('칸 글자 벌 — 기본(넓은 화면·종이)은 --w · 휴대폰 벌로 바꾸는 규칙은 screen 720 묶음에만(옛 720 묶음 금지)', () => {
    expect(mediaAt(css, '.ucell__lab--w {\n  display: block;')).toEqual([]);
    expect(mediaAt(css, '  .ucell__lab--w {\n    display: none;')).toEqual(['@media screen and (max-width: 720px)']);
    expect(mediaAt(css, '  .ucell__lab--n {\n    display: block;')).toEqual(['@media screen and (max-width: 720px)']);
    // --n 이 --w 뒤(같은 무게 · 뒤가 이긴다 — 둘 다 붙은 글자가 휴대폰에서 서야 한다).
    expect(css.indexOf('  .ucell__lab--n {\n    display: block;')).toBeGreaterThan(css.indexOf('  .ucell__lab--w {\n    display: none;'));
    // 양성 대조 — 옛 묶음에 넣으면 그 머리가 나온다.
    const moved = '@media (max-width: 720px) {\n  .ucell__lab--q {\n    display: block;\n  }\n}\n' + css;
    expect(mediaAt(moved, '  .ucell__lab--q {\n    display: block;')).toEqual(['@media (max-width: 720px)']);
  });

  it('칸 사이 흰 줄은 box-shadow(자리를 안 먹는다) · 칸에 border·overflow 없음(넘친 글자를 숨기지 않는다) · 한 색', () => {
    expect(rule('.ucell + .ucell')).toMatch(/box-shadow:\s*inset 1px 0 0 var\(--card\)/);
    expect(rule('.ucell + .ucell')).not.toMatch(/border/);
    expect(rule('.ucell')).toMatch(/background:\s*var\(--fact-2\)/);
    expect(rule('.ucell')).not.toMatch(/overflow|border/);
    // 양성 대조 — 없는 규칙은 빈 글.
    expect(rule('.ucell + .ucellz')).toBe('');
  });

  it('글자 13px — 칸 안 글자 · 그 밖 N호 · 설명 글(기본 규칙이라 종이도 13px)', () => {
    for (const sel of ['.ucell__lab', '.ucells__rest', '.ucells__note']) {
      expect(mediaAt(css, `\n${sel} {`), sel).toEqual([]);
      expect(rule(sel), sel).toMatch(/font-size:\s*13px/);
    }
  });

  it('펼친 상세에서는 그리드 첫 줄 가로 전체(`grid-column: 1 / -1` · 👤 2026-10-22) — 기본 규칙(어느 폭·종이에서나)', () => {
    expect(mediaAt(css, '\n.ucells.ucells--detail {')).toEqual([]);
    expect(rule('.ucells.ucells--detail')).toMatch(/grid-column:\s*1 \/ -1/);
    // 양성 대조 — 셋째 칸 한 칸만 쓰는 꼴이면 걸린다.
    const moved = css.replace('.ucells.ucells--detail {\n  grid-column: 1 / -1;', '.ucells.ucells--detail {\n  grid-column: 3;');
    expect(moved).not.toBe(css);
    expect(rule('.ucells.ucells--detail', moved)).not.toMatch(/grid-column:\s*1 \/ -1/);
  });

  it('종이 — 칸 줄에만 break-inside: avoid(층·카드 통째 아님)', () => {
    expect(mediaAt(css, '  .ucells__row {\n    break-inside: avoid;')).toEqual(['@media print']);
    expect(/\n\s*\.ucells\s*\{\s*break-inside/.test(css)).toBe(false);
  });
});
