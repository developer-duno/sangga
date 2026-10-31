import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { DistrictSales } from '../types';
import {
  SALES_BADGE,
  SALES_BADGE_NOTE,
  SALES_GAP_NOTE,
  SALES_LEAD_REST,
  SALES_LEAD_STRONG,
  SALES_NOTES,
  formatAmount,
  headBody,
  headSummary,
  isDistrictSalesList,
  salesBigText,
  salesLagText,
  salesNoDataText,
  salesScaleMax,
  salesScaleText,
  salesSummary,
  salesTableRows,
  salesTrendCells,
} from './districtSales';

/**
 * 「업종별 추정매출 (서울시 추정)」 순수 계산(결정 0045 PR③).
 * 지키는 것: 모양 검사(섞인 답 통째 거부) · 접힌 요약 값 0 · 큰 숫자는 trend 칸 값 그대로 · 막대 비례·'–' ·
 * 칩 코드 여럿은 따로 · 분기·연도 글자 0 · 비율·나누기 글자 0 · 판단 낱말 0 · 금지어 0.
 */

const PNU = '1168010100100010000';
const WINDOW = ['20262', '20261', '20254', '20253', '20252', '20251', '20244', '20243'];

const TOP = [
  { cd: 'CS100001', nm: '한식음식점', amt: 214_000_000, co: 4120, mdwk_amt: 1, wkend_amt: 1 },
  { cd: 'CS100010', nm: '커피-음료', amt: 139_000_000, co: 5310, mdwk_amt: 1, wkend_amt: 1 },
  { cd: 'CS300002', nm: '편의점', amt: 98_000_000, co: 3250, mdwk_amt: 1, wkend_amt: 1 },
  { cd: 'CS200028', nm: '미용실', amt: 61_000_000, co: 980, mdwk_amt: 1, wkend_amt: 1 },
  { cd: 'CS200001', nm: '일반교습학원', amt: 47_000_000, co: 410, mdwk_amt: 1, wkend_amt: 1 },
];

const INDUSTRIES = [
  ...TOP.map(({ cd, nm, amt, co }) => ({ cd, nm, amt, co })),
  { cd: 'CS200029', nm: '네일숍', amt: 61_000_000 - 1, co: 980 },
  { cd: 'CS200002', nm: '외국어학원', amt: 9_000_000, co: 120 },
  { cd: 'CS200003', nm: '예술학원', amt: 8_000_000, co: 90 },
];

function okRow(over: Partial<DistrictSales> = {}): DistrictSales {
  return {
    status: 'ok',
    district_id: '3110001',
    district_nm: '○○역 2번 출구',
    district_type: '골목상권',
    latest_quarter: '20262',
    window_quarters: WINDOW,
    // 최신 → 옛 · 20244 는 빠진 분기(창 안 '–').
    trend: [
      { quarter: '20262', amt: 723_000_000, co: 15208 },
      { quarter: '20261', amt: 654_000_000, co: 14000 },
      { quarter: '20254', amt: 760_000_000, co: 16000 },
      { quarter: '20253', amt: 623_000_000, co: 13000 },
      { quarter: '20252', amt: 707_000_000, co: 15000 },
      { quarter: '20251', amt: 676_000_000, co: 14500 },
      { quarter: '20243', amt: 692_000_000, co: 14800 },
    ],
    top: TOP,
    rest_cnt: 9,
    rest_amt: 164_000_000,
    rest_co: 1138,
    industries: INDUSTRIES,
    ...over,
  };
}

function headRow(status: DistrictSales['status']): DistrictSales {
  return {
    status,
    district_id: null,
    district_nm: null,
    district_type: null,
    latest_quarter: null,
    window_quarters: WINDOW,
    trend: null,
    top: null,
    rest_cnt: null,
    rest_amt: null,
    rest_co: null,
    industries: null,
  };
}

function noDataRow(over: Partial<DistrictSales> = {}): DistrictSales {
  return { ...headRow('no_data'), district_id: '3110002', district_nm: '△△ 골목', district_type: '골목상권', ...over };
}

describe('isDistrictSalesList — 모양 검사', () => {
  it('정상 답(상권 줄 · no_data 줄 · 상태 줄)은 받는다', () => {
    expect(isDistrictSalesList([okRow()])).toBe(true);
    expect(isDistrictSalesList([okRow(), noDataRow()])).toBe(true);
    expect(isDistrictSalesList([headRow('not_seoul')])).toBe(true);
  });

  it('⛔ 빈 배열 · 배열 아님 · 모르는 상태는 거부', () => {
    expect(isDistrictSalesList([])).toBe(false);
    expect(isDistrictSalesList(null)).toBe(false);
    expect(isDistrictSalesList({})).toBe(false);
    expect(isDistrictSalesList([{ ...okRow(), status: 'weird' }])).toBe(false);
  });

  it('⛔ 상권 줄인데 창이 비면 거부(「최근 0분기」를 지어내지 않는다)', () => {
    expect(isDistrictSalesList([okRow({ window_quarters: [] })])).toBe(false);
    expect(isDistrictSalesList([noDataRow({ window_quarters: [] })])).toBe(false);
  });

  it('⛔ ok 줄 칸 하나라도 어긋나면 거부 — trend·top·rest·industries·latest_quarter', () => {
    const bad: Array<Partial<DistrictSales> | Record<string, unknown>> = [
      { trend: null },
      { trend: [{ quarter: '20262', amt: -1, co: 1 }] },
      { trend: [{ quarter: '20262', amt: 1.5, co: 1 }] },
      { trend: [{ quarter: '2026Q2', amt: 1, co: 1 }] },
      { trend: [{ quarter: '20262', amt: 1 }] },
      { top: [...TOP, TOP[0]] },
      { top: [{ cd: 'CS1', nm: null, amt: 1, co: 1 }] },
      { top: null },
      { rest_cnt: null },
      { rest_amt: -5 },
      { industries: null },
      { industries: [{ cd: 'CS1', nm: 'x', amt: '1', co: 1 }] },
      { latest_quarter: '2026-2' },
      { latest_quarter: null },
      { district_id: null },
    ];
    for (const b of bad) expect(isDistrictSalesList([{ ...okRow(), ...b }]), JSON.stringify(b)).toBe(false);
  });

  it('⛔ 섞인 답(정상 줄 + 이상한 줄 하나)은 통째로 거부 — 양성 대조: 정상 둘은 받는다', () => {
    expect(isDistrictSalesList([okRow(), okRow({ district_id: 'x2' })])).toBe(true);
    expect(isDistrictSalesList([okRow(), { ...okRow(), rest_co: 1.2 }])).toBe(false);
  });
});

describe('salesSummary — 접힌 요약 (값 0)', () => {
  it('상권 하나 · 여럿 — 표 전체 최신 분기까지', () => {
    expect(salesSummary([okRow()], PNU)).toBe('○○역 2번 출구 · 2026년 2분기까지 서울시 추정');
    expect(salesSummary([okRow(), noDataRow()], PNU)).toBe('○○역 2번 출구 외 상권 1곳 · 2026년 2분기까지 서울시 추정');
  });

  it('빈 상태 넷 — 개업·폐업 카드와 같은 글 · no_data 만 추정매출 글', () => {
    expect(salesSummary([headRow('not_seoul')], '3011010700108770000')).toBe(
      '서울 상권만 다루는 자료라 이 건물(대전)에는 없습니다',
    );
    expect(salesSummary([headRow('outside_seoul_district')], PNU)).toBe('이 건물이 속한 서울시 상권이 없습니다');
    expect(salesSummary([headRow('no_coord')], PNU)).toBe('위치 정보가 없어 속한 상권을 찾지 못했습니다');
    expect(salesSummary([noDataRow()], PNU)).toBe('△△ 골목 · 최근 2년(8분기) 안에 서울시 추정매출 자료가 없습니다');
  });

  it('⛔ 요약에 금액·건수가 없다', () => {
    const s = salesSummary([okRow()], PNU);
    expect(s).not.toMatch(/억|만원|건/);
  });

  it('펼친 본문 상태 글도 개업·폐업 카드와 같다', () => {
    expect(headBody('not_seoul', '3011010700108770000')).toBe(
      '서울시 상권분석서비스는 서울 상권만 다룹니다 — 이 건물(대전)에는 그 자료가 없습니다.',
    );
    expect(headSummary('not_seoul', '9911010700108770000')).toBe('서울 상권만 다루는 자료라 이 건물에는 없습니다');
  });
});

describe('salesBigText — 큰 숫자 줄', () => {
  it('★ 그 상권 latest_quarter 의 trend 칸 값 그대로(3개월 합)', () => {
    expect(salesBigText(okRow())).toEqual({
      amount: '2026년 2분기(3개월) 매출 7억 2,300만원',
      count: '결제 15,208건',
      industries: '14업종 합',
    });
  });

  it('⛔ top + rest 를 더해 다시 만들지 않는다 — trend 값과 업종 합이 달라도 trend 값', () => {
    // top 합 559,000,000 + rest 164,000,000 = 723,000,000 — trend 를 다른 값으로 두면 갈린다.
    const r = okRow({ trend: [{ quarter: '20262', amt: 800_000_000, co: 20000 }] });
    expect(salesBigText(r)?.amount).toBe('2026년 2분기(3개월) 매출 8억원');
    expect(salesBigText(r)?.count).toBe('결제 20,000건');
  });

  it('trend 에 그 분기가 없으면 금액·건수 자리에 「–」 · ok 줄이 아니면 null', () => {
    const r = okRow({ trend: [{ quarter: '20261', amt: 1, co: 1 }] });
    expect(salesBigText(r)).toEqual({ amount: '2026년 2분기(3개월) 매출 –', count: '결제 –', industries: '14업종 합' });
    expect(salesBigText(noDataRow())).toBeNull();
  });

  it('금액 서식 = 개별공시지가 줄과 같다(10만 미만 원 · 만원 반올림 · 억)', () => {
    expect(formatAmount(14_999)).toBe('14,999원');
    expect(formatAmount(61_000_000)).toBe('6,100만원');
    expect(formatAmount(723_000_000)).toBe('7억 2,300만원');
    expect(formatAmount(null)).toBe('–');
  });

  it('이 상권 자료가 창 최신보다 옛 분기에서 멈췄으면 그 글 한 줄', () => {
    expect(salesLagText(okRow())).toBeNull();
    expect(salesLagText(okRow({ latest_quarter: '20254' }))).toBe('이 상권 자료는 2025년 4분기까지입니다.');
  });
});

describe('흐름 막대 — salesTrendCells · salesScaleMax · salesScaleText', () => {
  it('★ 칸 = 창 전부 · 옛 → 최신 · 빠진 분기는 missing(0 막대 아님) · 최신 칸 표시', () => {
    const max = salesScaleMax([okRow()]);
    const cells = salesTrendCells(okRow(), max);
    expect(cells.map((c) => c.quarter)).toEqual([...WINDOW].reverse());
    const gap = cells.find((c) => c.quarter === '20244')!;
    expect(gap.kind).toBe('missing');
    expect(gap.h).toBe(0);
    expect(gap.amt).toBeNull();
    expect(cells.filter((c) => c.last).map((c) => c.quarter)).toEqual(['20262']);
  });

  it('★ 높이 비례 — 가장 큰 분기 = 100 · 다른 분기는 금액 ÷ 그 값', () => {
    const max = salesScaleMax([okRow()]);
    expect(max).toBe(760_000_000);
    const cells = salesTrendCells(okRow(), max);
    expect(cells.find((c) => c.quarter === '20254')!.h).toBe(100);
    expect(cells.find((c) => c.quarter === '20262')!.h).toBeCloseTo((723 / 760) * 100, 6);
  });

  it('카드 하나에 눈금 하나 — ok 상권 전부의 창 안 최댓값(창 밖 분기는 안 센다)', () => {
    const other = okRow({
      district_id: 'x2',
      trend: [
        { quarter: '20262', amt: 900_000_000, co: 1 },
        { quarter: '20234', amt: 5_000_000_000, co: 1 }, // 창 밖
      ],
    });
    expect(salesScaleMax([okRow(), other, noDataRow()])).toBe(900_000_000);
    expect(salesScaleMax([noDataRow()])).toBe(0);
  });

  it('눈금 글(목업 글자 그대로)', () => {
    expect(salesScaleText(760_000_000)).toBe('막대가 꽉 차면 7억 6,000만원(3개월 합)');
  });
});

describe('salesTableRows — 업종 표 · 창업자 칩', () => {
  it('★ 상위 5(차례 그대로) + 「그 밖 9업종 (더해서)」 · 막대 길이 = 첫 줄 대비', () => {
    const t = salesTableRows(okRow(), '전체');
    expect(t.rows.map((r) => r.name)).toEqual(['한식음식점', '커피-음료', '편의점', '미용실', '일반교습학원']);
    expect(t.rows[0]).toMatchObject({ amount: '2억 1,400만원', count: '4,120건', w: 100, hit: false });
    expect(t.rows[1].w).toBeCloseTo((139 / 214) * 100, 6);
    expect(t.rest).toEqual({ label: '그 밖 9업종 (더해서)', amount: '1억 6,400만원', count: '1,138건' });
    // 칩 「전체」면 표시 0.
    expect(t.hitTail).toBeNull();
    expect(t.chipOutside).toEqual([]);
    expect(t.chipNone).toBeNull();
    expect(t.chipPartial).toBeNull();
  });

  it('그 밖 0업종이면 그 줄이 없다', () => {
    expect(salesTableRows(okRow({ rest_cnt: 0, rest_amt: 0, rest_co: 0 }), '전체').rest).toBeNull();
  });

  it('★ 칩 카페 — 상위 5 안이면 그 줄 hit + 꼬리', () => {
    const t = salesTableRows(okRow(), '카페');
    expect(t.rows.filter((r) => r.hit).map((r) => r.cd)).toEqual(['CS100010']);
    expect(t.hitTail).toBe(' · 고른 업종(카페)');
    expect(t.chipOutside).toEqual([]);
    expect(t.chipNone).toBeNull();
  });

  it('★ 칩 미용(코드 셋) — 안 · 상위 5 밖 · 없음 셋이 따로 선다(더하지 않는다)', () => {
    const t = salesTableRows(okRow(), '미용');
    expect(t.rows.filter((r) => r.hit).map((r) => r.name)).toEqual(['미용실']);
    expect(t.chipOutside).toEqual(['고른 업종(미용): 네일숍 6,100만원 · 980건 (상위 5 밖)']);
    expect(t.chipPartial).toBe('고른 업종 가운데 피부관리실은 이 자료에 없습니다');
    expect(t.chipNone).toBeNull();
  });

  it('⛔ 칩 학원(코드 다섯) — 상위 5 밖 둘은 코드마다 한 줄(합친 금액 줄이 없다) · 빠진 둘은 이름으로', () => {
    const t = salesTableRows(okRow(), '학원');
    expect(t.chipOutside).toEqual([
      '고른 업종(학원): 외국어학원 900만원 · 120건 (상위 5 밖)',
      '고른 업종(학원): 예술학원 800만원 · 90건 (상위 5 밖)',
    ]);
    // 더한 값(1,700만원·210건)은 어디에도 없다.
    expect(JSON.stringify(t)).not.toContain('1,700만원');
    expect(t.chipPartial).toBe('고른 업종 가운데 컴퓨터학원·스포츠 강습은 이 자료에 없습니다');
  });

  it('★ 칩 업종 전부가 이 자료에 없으면 한 줄', () => {
    const r = okRow({ top: TOP.filter((x) => x.cd !== 'CS300002'), industries: INDUSTRIES.filter((x) => x.cd !== 'CS300002') });
    const t = salesTableRows(r, '편의점');
    expect(t.chipNone).toBe('고른 업종(편의점)은 이 자료에 없습니다');
    expect(t.chipPartial).toBeNull();
    expect(t.chipOutside).toEqual([]);
  });
});

// ── 가드 ───────────────────────────────────────────────────────────────────

/**
 * ⓐ 분기·연도 글자(개업·폐업 카드 가드와 같은 꼴).
 * 못 보는 것: 숫자를 쪼개 이은 꼴('20' + '26')이나 계산으로 만든 연도.
 */
function findQuarterOrYearLiterals(src: string): string[] {
  return src.match(/(?<![\d])20\d{2}(?:[1-4](?!\d)|년|Q[1-4]|-\d{2})/g) ?? [];
}

/**
 * ⓑ 비율·나누기 글자(층별 공표값 카드 가드와 같은 꼴) — `%`·`％`·'퍼센트'·숫자 뒤 '배'.
 * 못 보는 것: 나누기 기호로 적은 식 · 숫자 없이 글자로 쓴 비교('절반'). 막대 폭 % 는 style 값이라 글이 아니다(여기는 글만 본다).
 */
function hasRatio(text: string): boolean {
  return /[%％]|퍼센트|\d\s*배/.test(text);
}

/** 화면이 나누지 않는다는 낱말 — 서울시 화면을 설명하는 발 문구 한 곳(SALES_NOTES.unit)에만 나온다. */
const DIVIDE_WORDS = ['점포당', '월평균', '하루 평균'];

/** ⓒ 판단 낱말(역할 요약 판 가드와 같은 목록). 못 보는 것: 띄어 쓴 변형 · 목록 밖 낱말. */
const JUDGMENT = ['많', '적습', '적다', '적은 편', '되겠', '될 것', '좋', '나쁘', '유망', '추천', '괜찮', '충분', '부족', '활발', '위험', '높습', '높은', '낮습', '낮은', '비싸', '저렴', '인기', '늘었', '줄었', '늘다', '줄다'];
function judgmentWords(text: string): string[] {
  return JUDGMENT.filter((w) => text.includes(w));
}

/** ⓓ 금지어(절대 규칙 2) — 공백을 지운 글로도 본다. */
const FORBIDDEN = ['적정가격', '적정가', '평가액', '감정가', '가치평가'];
function forbiddenWords(text: string): string[] {
  const t = text.replace(/\s+/g, '');
  return FORBIDDEN.filter((w) => t.includes(w));
}

/** 이 lib 가 만드는 글 전부(대표 입력으로). */
function allSalesTexts(): string[] {
  const max = salesScaleMax([okRow()]);
  const texts: string[] = [
    salesSummary([okRow(), noDataRow()], PNU),
    salesSummary([noDataRow()], PNU),
    salesSummary([headRow('not_seoul')], '3011010700108770000'),
    headBody('outside_seoul_district', PNU),
    headBody('no_coord', PNU),
    salesNoDataText(noDataRow()),
    salesLagText(okRow({ latest_quarter: '20254' })) ?? '',
    salesScaleText(max),
    SALES_GAP_NOTE,
    SALES_LEAD_STRONG,
    ...SALES_LEAD_REST,
    SALES_BADGE,
    SALES_BADGE_NOTE,
    SALES_NOTES.source,
    ...SALES_NOTES.notBuilding,
    SALES_NOTES.method,
    SALES_NOTES.industry,
  ];
  const big = salesBigText(okRow())!;
  texts.push(big.amount, big.count, big.industries);
  for (const chip of ['카페', '미용', '학원', '편의점'] as const) {
    const t = salesTableRows(okRow(), chip);
    texts.push(...t.rows.flatMap((r) => [r.name, r.amount, r.count]), t.rest?.label ?? '', t.hitTail ?? '');
    texts.push(...t.chipOutside, t.chipNone ?? '', t.chipPartial ?? '');
  }
  return texts;
}

describe('⛔ 가드 — 분기·연도 글자 · 비율·나누기 · 판단 낱말 · 금지어', () => {
  it('양성 대조 — 탐지 함수 넷이 흔한 꼴과 변형 꼴을 실제로 잡는다', () => {
    expect(findQuarterOrYearLiterals("const x = '20262';")).toEqual(['20262']);
    expect(findQuarterOrYearLiterals('// 2025년 3분기까지')).toEqual(['2025년']);
    expect(findQuarterOrYearLiterals('기록 2026-10-31')).toEqual(['2026-10']);
    expect(findQuarterOrYearLiterals('상위 5 · 3개월 합 · 100업종')).toEqual([]);
    expect(hasRatio('업종의 18%')).toBe(true);
    expect(hasRatio('68 퍼센트')).toBe(true);
    expect(hasRatio('1.8배')).toBe(true);
    expect(hasRatio('C등급 배지 · 보정 비율')).toBe(false);
    expect(judgmentWords('매출이 높은 업종')).toEqual(['높은']);
    expect(judgmentWords('작년보다 늘었습니다')).toEqual(['늘었']);
    // 띄어 쓴 변형도 공백을 지워 잡는다.
    expect(forbiddenWords('적정 가격')).toEqual(['적정가격', '적정가']);
    expect(forbiddenWords('감정가로')).toEqual(['감정가']);
  });

  it('ⓐ 카드·도우미 원문에 분기·연도 글자가 없다', () => {
    for (const f of ['./districtSales.ts', '../components/SalesSection.tsx']) {
      const src = readFileSync(fileURLToPath(new URL(f, import.meta.url)), 'utf-8');
      expect(findQuarterOrYearLiterals(src), f).toEqual([]);
      expect(forbiddenWords(src), f).toEqual([]);
    }
  });

  it('ⓑ 만드는 글에 비율 글자가 없고, 「점포당·월평균·하루 평균」은 서울시 화면 설명 한 줄에만', () => {
    const texts = allSalesTexts();
    for (const t of texts) expect(hasRatio(t), t).toBe(false);
    for (const t of texts.filter((x) => x !== SALES_NOTES.unit)) {
      for (const w of DIVIDE_WORDS) expect(t.includes(w), `${w} · ${t}`).toBe(false);
    }
    // 양성 대조 — 그 한 줄에는 실제로 있다(위 검사가 헛돌지 않는다).
    expect(SALES_NOTES.unit).toContain('점포당 월평균');
  });

  it('ⓒ·ⓓ 만드는 글에 판단 낱말·금지어가 없다', () => {
    for (const t of allSalesTexts()) {
      expect(judgmentWords(t), t).toEqual([]);
      expect(forbiddenWords(t), t).toEqual([]);
    }
  });

  it('발 문구에 「현금 매출」 문장을 넣지 않는다(메인 정정 · 보정 비율이 무엇을 보정하는지 서울시가 밝히지 않는다)', () => {
    expect(JSON.stringify(SALES_NOTES)).not.toContain('현금');
  });
});
