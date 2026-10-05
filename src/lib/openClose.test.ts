import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { DistrictOpenClose, OpenCloseQuarter } from '../types';
import {
  industryRows,
  isOpenCloseList,
  openCloseQuarterLabel,
  openCloseSummary,
  otherIndustries,
  sidoNameOfPnu,
  trendCells,
  trendScaleMax,
  windowText,
} from './openClose';

/**
 * 상권 개업·폐업 카드의 순수 계산(결정 0033 R2).
 *
 * 여기서 특히 지키는 것
 *  ① 추이 칸은 **옛 분기 왼쪽 → 최신 오른쪽**이고, 그 상권에 없는 분기는 **빈 칸**(0 막대 아님)
 *  ② 막대 높이는 그 상권 창 안 최댓값 기준 비례 — **숫자로** 단언한다(글자만 보면 모양이 깨져도 초록)
 *  ③ 서버 모양이 어긋나면 카드째 빠진다(빈 배열·모르는 상태 포함)
 *  ④ 화면 코드에 분기·연도 글자가 없다(양성 대조 짝)
 */

const WINDOW = ['20262', '20261', '20254', '20253', '20252', '20251', '20244', '20243'];

function q(over: Partial<OpenCloseQuarter> & { quarter: string }): OpenCloseQuarter {
  return {
    similr_induty_stor_co: 441,
    stor_co: 378,
    frc_stor_co: 63,
    opbiz_stor_co: 5,
    clsbiz_stor_co: 9,
    opbiz_rt: 1.13,
    clsbiz_rt: 2.04,
    ...over,
  };
}

function okRow(over: Partial<DistrictOpenClose> = {}): DistrictOpenClose {
  return {
    status: 'ok',
    district_id: '3120218',
    district_nm: '코엑스',
    district_type: '발달상권',
    latest_quarter: '20262',
    quarters: [q({ quarter: '20262' }), q({ quarter: '20261', opbiz_rt: 2.5, clsbiz_rt: 4.0 })],
    industries: null,
    other_industries: null,
    window_quarters: WINDOW,
    ...over,
  };
}

function headRow(status: DistrictOpenClose['status']): DistrictOpenClose {
  return {
    status,
    district_id: null,
    district_nm: null,
    district_type: null,
    latest_quarter: null,
    quarters: null,
    industries: null,
    other_industries: null,
    window_quarters: WINDOW,
  };
}

describe('openCloseQuarterLabel — 서울시 분기 표기', () => {
  it('다섯 자리를 연도·분기로 읽고, 못 읽으면 null(원본 코드를 새지 않는다)', () => {
    expect(openCloseQuarterLabel('20262')).toBe('2026년 2분기');
    expect(openCloseQuarterLabel('20255')).toBeNull();
    expect(openCloseQuarterLabel('2026Q2')).toBeNull();
    expect(openCloseQuarterLabel(null)).toBeNull();
  });
});

describe('trendCells — 추이 칸', () => {
  it('★ 순서는 옛 → 최신(왼 → 오른)이고 칸 수는 창의 크기다', () => {
    const cells = trendCells(WINDOW, okRow().quarters!);
    expect(cells.map((c) => c.quarter)).toEqual([...WINDOW].reverse());
    expect(cells[0].label).toBe('2024년 3분기');
    expect(cells[cells.length - 1].label).toBe('2026년 2분기');
  });

  it('★ 그 상권에 없는 분기는 빈 칸(missing) — 높이 0 막대가 아니다', () => {
    const cells = trendCells(WINDOW, okRow().quarters!);
    const missing = cells.filter((c) => c.kind === 'missing').map((c) => c.quarter);
    expect(missing).toEqual(['20243', '20244', '20251', '20252', '20253', '20254']);
    for (const c of cells.filter((x) => x.kind === 'missing')) {
      expect(c.openRt).toBeNull();
      expect(c.closeRt).toBeNull();
    }
  });

  it('★ 막대 높이 = 그 상권 창 안 두 비율 중 최댓값(4.0)을 100 으로 둔 비례 — 숫자로 본다', () => {
    const cells = trendCells(WINDOW, okRow().quarters!);
    const last = cells[cells.length - 1];
    const prev = cells[cells.length - 2];
    expect(prev.closeH).toBeCloseTo(100, 6);
    expect(prev.openH).toBeCloseTo(62.5, 6);
    expect(last.openH).toBeCloseTo((1.13 / 4) * 100, 6);
    expect(last.closeH).toBeCloseTo(51, 6);
  });

  it('비율이 null 인 분기(표본 부족)는 막대 없이 nosample — 최댓값 계산에서도 빠진다', () => {
    const cells = trendCells(WINDOW, [
      q({ quarter: '20262' }),
      q({ quarter: '20261', similr_induty_stor_co: 12, opbiz_rt: null, clsbiz_rt: null }),
    ]);
    const prev = cells.find((c) => c.quarter === '20261')!;
    expect(prev.kind).toBe('nosample');
    expect(prev.similr).toBe(12);
    expect(prev.openH).toBe(0);
    const last = cells.find((c) => c.quarter === '20262')!;
    expect(last.closeH).toBeCloseTo(100, 6);
  });

  it('★ 공통 눈금 — trendScaleMax 는 카드 안 ok 상권 전부의 최댓값, 주면 그 눈금으로 그린다', () => {
    const a = okRow();
    const b = okRow({ district_id: 'b', quarters: [q({ quarter: '20262', opbiz_rt: 1.0, clsbiz_rt: 2.0 })] });
    expect(trendScaleMax([a, b])).toBe(4);
    // 창 밖 분기와 상태 줄은 세지 않는다.
    const outside = okRow({ quarters: [q({ quarter: '20262' }), q({ quarter: '20232', clsbiz_rt: 99 })] });
    expect(trendScaleMax([outside, headRow('not_seoul')])).toBe(2.04);
    const cells = trendCells(WINDOW, b.quarters!, 4);
    expect(cells[cells.length - 1].closeH).toBeCloseTo(50, 6);
    expect(cells[cells.length - 1].openH).toBeCloseTo(25, 6);
  });

  it('0 은 값이다 — 비율이 모두 0 이면 ok 칸에 높이 0', () => {
    const cells = trendCells(['20262'], [q({ quarter: '20262', opbiz_rt: 0, clsbiz_rt: 0 })]);
    expect(cells[0].kind).toBe('ok');
    expect(cells[0].openH).toBe(0);
  });
});

describe('isOpenCloseList — 서버 응답 모양', () => {
  it('상권 줄·상태 줄 모양을 받는다', () => {
    expect(isOpenCloseList([okRow()])).toBe(true);
    expect(isOpenCloseList([headRow('not_seoul')])).toBe(true);
    expect(
      isOpenCloseList([
        okRow({ status: 'no_data', latest_quarter: null, quarters: null }),
      ]),
    ).toBe(true);
  });

  it('★ 빈 배열 · 모르는 상태 · 창이 배열이 아님 · 최신 분기 합이 없음 → 거부', () => {
    expect(isOpenCloseList([])).toBe(false);
    expect(isOpenCloseList([{ ...okRow(), status: 'closed' }])).toBe(false);
    expect(isOpenCloseList([{ ...okRow(), window_quarters: null }])).toBe(false);
    expect(isOpenCloseList([okRow({ latest_quarter: '20254' })])).toBe(false);
    expect(isOpenCloseList([okRow({ quarters: [q({ quarter: '20262', opbiz_rt: '1.13' as never })] })])).toBe(
      false,
    );
    expect(isOpenCloseList({ code: 'PGRST202' })).toBe(false);
  });

  it('★ 숫자 칸 열쇠가 빠지면 거부한다 — 분기 합·업종 표·그 밖 합 모두(F5)', () => {
    const { stor_co: _drop, ...noStor } = q({ quarter: '20262' });
    expect(isOpenCloseList([okRow({ quarters: [noStor as OpenCloseQuarter] })])).toBe(false);
    const { clsbiz_rt: _r, ...noRate } = q({ quarter: '20262' });
    expect(isOpenCloseList([okRow({ quarters: [noRate as OpenCloseQuarter] })])).toBe(false);
    // 비율 null 은 받는다(열쇠는 있다) · 개수 null 은 받지 않는다(개수는 늘 수).
    expect(isOpenCloseList([okRow({ quarters: [q({ quarter: '20262', opbiz_rt: null, clsbiz_rt: null })] })])).toBe(true);
    expect(isOpenCloseList([okRow({ quarters: [q({ quarter: '20262', opbiz_stor_co: null as never })] })])).toBe(false);
    const ind = { svc_induty_cd: 'CS1', svc_induty_cd_nm: '한식', similr_induty_stor_co: 9, stor_co: 9, frc_stor_co: 0, opbiz_stor_co: 1, clsbiz_stor_co: 0, opbiz_rt: 11.1, clsbiz_rt: 0 };
    expect(isOpenCloseList([okRow({ industries: [ind] })])).toBe(true);
    const { frc_stor_co: _f, ...indNoFrc } = ind;
    expect(isOpenCloseList([okRow({ industries: [indNoFrc as never] })])).toBe(false);
    expect(isOpenCloseList([okRow({ industries: 'x' as never })])).toBe(false);
    expect(isOpenCloseList([okRow({ other_industries: { industry_count: 3 } as never })])).toBe(false);
    expect(industryRows(null)).toBeNull();
    expect(otherIndustries(null)).toBeNull();
  });

  it('★ 상권 줄인데 창이 비어 있으면 거부한다(F6) — 상태 줄은 빈 창이어도 받는다', () => {
    expect(isOpenCloseList([okRow({ window_quarters: [] })])).toBe(false);
    expect(isOpenCloseList([okRow({ status: 'no_data', latest_quarter: null, quarters: null, window_quarters: [] })])).toBe(false);
    expect(isOpenCloseList([{ ...headRow('not_seoul'), window_quarters: [] }])).toBe(true);
  });
});

/** 요약에 값(개수·비율)이 섞였나 — 상권 수('외 상권 1곳')는 값이 아니다. */
function summaryHasValue(text: string): boolean {
  return /%/.test(text) || /(개업|폐업|점포)\s*[\d,]+곳/.test(text);
}

describe('openCloseSummary — 접힌 한 줄 (⛔ 값을 적지 않는다)', () => {
  it('양성 대조 — 값 탐지가 비율·개수를 실제로 잡는다', () => {
    expect(summaryHasValue('코엑스 · 2026년 2분기 개업 5곳(1.13%)')).toBe(true);
    expect(summaryHasValue('코엑스 · 폐업 1,234곳')).toBe(true);
    expect(summaryHasValue('코엑스 외 상권 1곳 · 2026년 2분기까지 서울시 공표')).toBe(false);
  });

  it('★ 첫 상권 이름 + 외 상권 N곳 + 표 전체 최신 분기까지 서울시 공표 — 숫자 없음', () => {
    const rows = [okRow(), okRow({ district_id: '3001496', district_nm: '강남 마이스 관광특구' })];
    const s = openCloseSummary(rows, '1168010500101590000');
    expect(s).toBe('코엑스 외 상권 1곳 · 2026년 2분기까지 서울시 공표');
    expect(summaryHasValue(s)).toBe(false);
  });

  it('상권 하나면 이름만 · 분기는 상권 최신이 아니라 창의 최신', () => {
    const rows = [okRow({ latest_quarter: '20261', quarters: [q({ quarter: '20261' })] })];
    expect(openCloseSummary(rows, '1168010500101590000')).toBe('코엑스 · 2026년 2분기까지 서울시 공표');
  });

  it('빈 상태는 그 사실 한 줄 — 서울 밖 지역 이름은 표에서 고른다', () => {
    expect(openCloseSummary([headRow('not_seoul')], '3011010700108770000')).toBe(
      '서울 상권만 다루는 자료라 이 건물(대전)에는 없습니다',
    );
    expect(openCloseSummary([headRow('not_seoul')], '9911010700108770000')).toBe(
      '서울 상권만 다루는 자료라 이 건물에는 없습니다',
    );
    expect(openCloseSummary([headRow('outside_seoul_district')], '1156011000100400000')).toBe(
      '이 건물이 속한 서울시 상권이 없습니다',
    );
    expect(openCloseSummary([headRow('no_coord')], '1156011000100400000')).toBe(
      '위치 정보가 없어 속한 상권을 찾지 못했습니다',
    );
    expect(
      openCloseSummary([okRow({ status: 'no_data', latest_quarter: null, quarters: null })], '1168010500101590000'),
    ).toBe('코엑스 · 최근 2년(8분기) 서울시 자료 없음');
  });

  it('sidoNameOfPnu · windowText', () => {
    expect(sidoNameOfPnu('3011010700108770000')).toBe('대전');
    expect(sidoNameOfPnu('9911010700108770000')).toBeNull();
    expect(windowText(WINDOW)).toBe('최근 2년(8분기)');
    expect(windowText(WINDOW.slice(0, 3))).toBe('최근 3분기');
  });
});

/**
 * ⛔ 화면 코드에 분기·연도 글자를 박지 않는다(결정 0033 R2 · txFlow 와 같은 가드).
 *
 * 못 보는 것: 숫자를 쪼개 이은 꼴('20' + '26')이나 계산으로 만든 연도는 못 본다.
 */
function findQuarterOrYearLiterals(src: string): string[] {
  return src.match(/(?<![\d])20\d{2}(?:[1-4](?!\d)|년|Q[1-4]|-\d{2})/g) ?? [];
}

describe('⛔ 분기·연도 리터럴 가드', () => {
  it('양성 대조 — 흔한 꼴과 변형 꼴을 실제로 잡는다', () => {
    expect(findQuarterOrYearLiterals("const x = '20262';")).toEqual(['20262']);
    expect(findQuarterOrYearLiterals('// 2025년 3분기까지')).toEqual(['2025년']);
    expect(findQuarterOrYearLiterals("label('2026Q2')")).toEqual(['2026Q2']);
    expect(findQuarterOrYearLiterals('기록 2026-10-06')).toEqual(['2026-10']);
    expect(findQuarterOrYearLiterals('결정 0033 · 100업종 · 30곳')).toEqual([]);
  });

  it('카드와 도우미 원문에 분기·연도 글자가 없다', () => {
    for (const f of ['../components/OpenCloseSection.tsx', './openClose.ts']) {
      const src = readFileSync(fileURLToPath(new URL(f, import.meta.url)), 'utf-8');
      expect(findQuarterOrYearLiterals(src), f).toEqual([]);
    }
  });
});
