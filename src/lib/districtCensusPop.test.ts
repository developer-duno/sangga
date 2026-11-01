import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { DistrictCensusPop } from '../types';
import {
  CENSUS_BADGE,
  CENSUS_CHUNK_TITLES,
  CENSUS_LEAD_REST,
  CENSUS_LEAD_STRONG,
  CENSUS_NOTES,
  CENSUS_NO_DATA_TEXT,
  CENSUS_POP_TITLE,
  boundaryText,
  censusBadgeNote,
  censusHeadBody,
  censusHeadSummary,
  censusNote,
  censusSourceText,
  censusSummary,
  coverText,
  empBig,
  isDistrictCensusPopList,
  rangeOnly,
  residentBig,
} from './districtCensusPop';

/**
 * 대전 「상권 인구 (통계청 집계구)」 순수 계산(결정 0045 PR⑤).
 * 지키는 것: 모양 검사(섞인 답 통째 거부 · 양성 대조) · 2배 식 경계 · 가구 따로 · 접힌 요약 값 0 · 건물 단위 글 셋 ·
 * 연도는 서버 표지 값 · 글 가드(연도 글자 0 · % 는 덮임 한 곳 · 금지어 0 · 「일하는 사람」·「직장인구」는 발 문구 한 문장 · 「유동인구」 0).
 */

const DJ = '3017010100100010000';

function okRow(over: Partial<DistrictCensusPop> = {}): DistrictCensusPop {
  return {
    status: 'ok',
    district_id: 'DJ001',
    district_nm: '둔산 가짜거리',
    district_type: '발달상권',
    area_m2: 120000.5,
    n_overlap: 9,
    n_full: 3,
    cover_pct: 100,
    pop: 3120,
    pop_lo: 1840,
    pop_hi: 4610,
    hh: 1380,
    hh_lo: 820,
    hh_hi: 2050,
    emp: 5900,
    emp_lo: 2700,
    emp_hi: 11200,
    received_on: '2026-10-08',
    base_year: 2024,
    bnd_base_date: '2025-06-30',
    ...over,
  };
}

/** 범위만 적는 상권(통째로 든 집계구 0개 — 하한 0). */
function wideRow(): DistrictCensusPop {
  return okRow({
    district_id: 'DJ002',
    district_nm: '시청역 가짜출구',
    n_overlap: 3,
    n_full: 0,
    cover_pct: 99.975,
    pop: 420,
    pop_lo: 0,
    pop_hi: 1380,
    hh: 190,
    hh_lo: 0,
    hh_hi: 640,
    emp: 4100,
    emp_lo: 0,
    emp_hi: 15300,
  });
}

function headRow(status: DistrictCensusPop['status']): DistrictCensusPop {
  return {
    ...okRow(),
    status,
    district_id: null,
    district_nm: null,
    district_type: null,
    area_m2: null,
    n_overlap: null,
    n_full: null,
    cover_pct: null,
    pop: null,
    pop_lo: null,
    pop_hi: null,
    hh: null,
    hh_lo: null,
    hh_hi: null,
    emp: null,
    emp_lo: null,
    emp_hi: null,
  };
}

function noDataRow(): DistrictCensusPop {
  return { ...headRow('no_data'), district_id: 'DJ003', district_nm: '유성 가짜골목', district_type: '골목상권' };
}

describe('모양 검사 isDistrictCensusPopList', () => {
  it('양성 대조 — 정상 답(ok 둘 · ok + no_data · 건물 단위 한 줄)은 받는다', () => {
    expect(isDistrictCensusPopList([okRow(), wideRow()])).toBe(true);
    expect(isDistrictCensusPopList([okRow(), noDataRow()])).toBe(true);
    for (const s of ['no_coord', 'not_daejeon', 'outside_daejeon_district'] as const) {
      expect(isDistrictCensusPopList([headRow(s)]), s).toBe(true);
    }
  });

  it('⛔ 빈 배열(표지 없음)·배열 아님·모르는 상태는 거부', () => {
    expect(isDistrictCensusPopList([])).toBe(false);
    expect(isDistrictCensusPopList(null)).toBe(false);
    expect(isDistrictCensusPopList({ status: 'ok' })).toBe(false);
    expect(isDistrictCensusPopList([{ ...okRow(), status: 'not_seoul' }])).toBe(false);
  });

  it('⛔ 섞인 답 — 정상 줄 + 이상한 줄 하나 · 건물 단위 줄이 다른 줄과 함께 · 표지 칸이 줄마다 다름', () => {
    expect(isDistrictCensusPopList([okRow(), { ...wideRow(), pop: -1 }])).toBe(false);
    expect(isDistrictCensusPopList([headRow('no_coord'), okRow()])).toBe(false);
    expect(isDistrictCensusPopList([okRow(), { ...wideRow(), base_year: 2023 }])).toBe(false);
    expect(isDistrictCensusPopList([okRow(), { ...wideRow(), received_on: '2026-10-09' }])).toBe(false);
  });

  it('⛔ 숫자 칸 — 음수·소수·문자열·null · 하한 > 값 · 값 > 상한 · 통째 > 겹친', () => {
    const bad: Partial<DistrictCensusPop>[] = [
      { pop: -1, pop_lo: -1 },
      { emp: 5900.5 },
      { hh: '1380' as unknown as number },
      { pop: null },
      { pop_lo: 3121 },
      { hh_hi: 1379 },
      { emp_lo: 6000 },
      { n_full: 10 },
      { n_overlap: -1 },
      { cover_pct: -0.1 },
      { cover_pct: Number.NaN },
    ];
    for (const over of bad) expect(isDistrictCensusPopList([okRow(over)]), JSON.stringify(over)).toBe(false);
    // 경계 — 하한 = 값 = 상한 · 통째 = 겹친 은 받는다.
    expect(isDistrictCensusPopList([okRow({ pop_lo: 3120, pop_hi: 3120, n_full: 9 })])).toBe(true);
  });

  it('⛔ 날짜·연도 꼴 — received_on·bnd_base_date 는 실제 있는 YYYY-MM-DD · base_year 네 자리', () => {
    for (const over of [
      { received_on: '2026-10-8' },
      { received_on: '2026-13-01' },
      { received_on: '2026-02-30' },
      { received_on: null },
      { bnd_base_date: '202506' },
      { base_year: 24 },
      { base_year: 2024.5 },
      { base_year: null },
    ]) {
      expect(isDistrictCensusPopList([okRow(over as Partial<DistrictCensusPop>)]), JSON.stringify(over)).toBe(false);
    }
  });

  it('상권 줄(ok·no_data)은 district_id 가 글자여야 한다', () => {
    expect(isDistrictCensusPopList([{ ...noDataRow(), district_id: null }])).toBe(false);
    expect(isDistrictCensusPopList([okRow({ district_id: 7 as unknown as string })])).toBe(false);
  });
});

describe('2배 식 rangeOnly — 비교 하나', () => {
  it('★ 경계 — 범위 = 2 × 값 이면 값을 보이고, 1 넘으면 범위만', () => {
    expect(rangeOnly(1000, 0, 2000)).toBe(false);
    expect(rangeOnly(1000, 0, 2001)).toBe(true);
    expect(rangeOnly(1000, 500, 2500)).toBe(false);
    expect(rangeOnly(1000, 500, 2501)).toBe(true);
    // 값 0 · 범위 0 은 값을 보인다.
    expect(rangeOnly(0, 0, 0)).toBe(false);
  });

  it('덩이 글 — 경계(같으면 값 · +1 이면 범위만)가 화면 글에도 그대로', () => {
    expect(residentBig(okRow({ pop: 1000, pop_lo: 0, pop_hi: 2000 }))?.num).toBe('약 1,000명');
    expect(residentBig(okRow({ pop: 1000, pop_lo: 0, pop_hi: 2001 }))?.num).toBe('범위 0~2,001명');
  });
});

describe('덩이 글 · 덩어리 발', () => {
  it('★ 값 + 범위 — 사는 사람(가구 포함) · 사업체 종사자', () => {
    expect(residentBig(okRow())).toEqual({
      num: '약 3,120명',
      range: '범위 1,840~4,610명',
      detail: '가구 약 1,380 (범위 820~2,050)',
    });
    expect(empBig(okRow())).toEqual({ num: '약 5,900명', range: '범위 2,700~11,200명', detail: null });
  });

  it('★ 범위만 — 값을 숨기고 범위를 큰 숫자로 · range 칸 없음', () => {
    expect(residentBig(wideRow())).toEqual({ num: '범위 0~1,380명', range: null, detail: '가구 범위 0~640' });
    expect(empBig(wideRow())).toEqual({ num: '범위 0~15,300명', range: null, detail: null });
  });

  it('★ 가구는 따로 2배 식 — 인구는 값인데 가구만 범위만 · 그 반대', () => {
    const hhWide = okRow({ hh: 100, hh_lo: 0, hh_hi: 900 });
    expect(residentBig(hhWide)).toEqual({ num: '약 3,120명', range: '범위 1,840~4,610명', detail: '가구 범위 0~900' });
    const popWide = okRow({ pop: 100, pop_lo: 0, pop_hi: 4610 });
    expect(residentBig(popWide)).toEqual({
      num: '범위 0~4,610명',
      range: null,
      detail: '가구 약 1,380 (범위 820~2,050)',
    });
  });

  it('ok 가 아니면 덩이 글 null', () => {
    expect(residentBig(noDataRow())).toBeNull();
    expect(empBig(headRow('no_coord'))).toBeNull();
    expect(censusNote(noDataRow())).toBeNull();
  });

  it('★ 덩어리 발 — 겹친·통째·덮임(서버 값) + 범위만 칸이 있으면 꼬리', () => {
    expect(censusNote(okRow())).toBe('겹친 집계구 9개 · 통째로 든 집계구 3개 · 상권 넓이의 100% 를 덮음');
    expect(censusNote(wideRow())).toBe(
      '겹친 집계구 3개 · 통째로 든 집계구 0개 · 상권 넓이의 99.98% 를 덮음 — 범위가 넓어 값 대신 범위만 적은 칸이 있습니다',
    );
    // 가구 하나만 범위만이어도 꼬리.
    expect(censusNote(okRow({ hh: 100, hh_lo: 0, hh_hi: 900 }))).toMatch(/ — 범위가 넓어 값 대신 범위만 적은 칸이 있습니다$/);
  });

  it('덮임 — 둘째 자리 반올림 · 끝 0 뗌 · 99.975 는 내려가지 않는다(부동소수 함정)', () => {
    expect(coverText(100)).toBe('100');
    expect(coverText(99.975)).toBe('99.98');
    expect(coverText(99.5)).toBe('99.5');
    expect(coverText(100.004)).toBe('100');
    expect(coverText(1234.5)).toBe('1234.5');
  });
});

describe('접힌 요약 — 값 0', () => {
  it('★ 「○○ 외 상권 N곳 · 통계청 집계구 YYYY년 통계」 · 연도는 첫 ok 줄의 base_year', () => {
    expect(censusSummary([okRow(), wideRow()], DJ)).toBe('둔산 가짜거리 외 상권 1곳 · 통계청 집계구 2024년 통계');
    expect(censusSummary([okRow()], DJ)).toBe('둔산 가짜거리 · 통계청 집계구 2024년 통계');
    // 서버 값을 따라 바뀐다(글자로 박지 않았다).
    expect(censusSummary([okRow({ base_year: 2025 })], DJ)).toBe('둔산 가짜거리 · 통계청 집계구 2025년 통계');
    for (const s of [censusSummary([okRow(), wideRow()], DJ), censusSummary([wideRow()], DJ)]) {
      expect(s).not.toMatch(/명|%|\d,\d/);
    }
  });

  it('ok 없음 · 건물 단위 셋', () => {
    expect(censusSummary([noDataRow()], DJ)).toBe('유성 가짜골목 · 통계청 집계구 인구 자료가 없습니다');
    expect(censusSummary([noDataRow(), { ...noDataRow(), district_id: 'DJ004' }], DJ)).toBe(
      '유성 가짜골목 외 상권 1곳 · 통계청 집계구 인구 자료가 없습니다',
    );
    expect(censusSummary([headRow('no_coord')], DJ)).toBe('위치 정보가 없어 속한 상권을 찾지 못했습니다');
    expect(censusSummary([headRow('outside_daejeon_district')], DJ)).toBe('이 건물이 속한 대전 상권이 없습니다');
    expect(censusSummary([headRow('not_daejeon')], '1168010100100010000')).toBe(
      '대전 상권에만 붙인 자료라 이 건물(서울)에는 없습니다',
    );
  });
});

describe('건물 단위 상태 글 셋', () => {
  it('★ no_coord = 서울 글 그대로 · not_daejeon = 시·도 이름(모르면 괄호 없음) · outside', () => {
    expect(censusHeadBody('no_coord', DJ)).toBe('이 건물의 위치 정보가 없어 속한 상권을 찾지 못했습니다.');
    expect(censusHeadBody('not_daejeon', '1168010100100010000')).toBe(
      '통계청 집계구 인구는 대전 상권에만 붙였습니다 — 이 건물(서울)에는 그 자료가 없습니다.',
    );
    expect(censusHeadBody('not_daejeon', '9911010100100010000')).toBe(
      '통계청 집계구 인구는 대전 상권에만 붙였습니다 — 이 건물에는 그 자료가 없습니다.',
    );
    expect(censusHeadBody('outside_daejeon_district', DJ)).toBe('이 건물이 속한 대전 상권이 없어 자료가 없습니다.');
    expect(censusHeadSummary('not_daejeon', '9911010100100010000')).toBe('대전 상권에만 붙인 자료라 이 건물에는 없습니다');
  });
});

describe('연도는 서버 표지 값', () => {
  it('★ 배지 옆·출처 — base_year · bnd_base_date 의 년·월', () => {
    expect(censusBadgeNote(okRow())).toBe('통계청 SGIS 2024년 집계구 통계 · 2025년 6월 경계 · 사람이 신청해 받은 자료');
    expect(censusSourceText(okRow())).toBe(
      '출처: 통계청 SGIS 통계지리정보서비스 집계구 통계(2024년)·집계구 경계(2025년 6월) — 자료신청 87909 · 공공누리 1유형.',
    );
    const next = okRow({ base_year: 2025, bnd_base_date: '2026-12-31' });
    expect(censusBadgeNote(next)).toBe('통계청 SGIS 2025년 집계구 통계 · 2026년 12월 경계 · 사람이 신청해 받은 자료');
    expect(censusSourceText(next)).toContain('집계구 통계(2025년)·집계구 경계(2026년 12월)');
    expect(boundaryText('2025-06-30')).toBe('2025년 6월');
    expect(boundaryText('bad')).toBeNull();
  });
});

// ── 글 가드 ─────────────────────────────────────────────────────────────────

/** 분기·연도 글자(districtPop.test 와 같은 탐지 꼴). */
function findQuarterOrYearLiterals(src: string): string[] {
  return src.match(/(?<![\d])20\d{2}(?:[1-4](?!\d)|년|Q[1-4]|-\d{2})/g) ?? [];
}
const FORBIDDEN = ['적정가격', '적정가', '평가액', '감정가', '가치평가'];
/** 판단 낱말(「적습니다」는 '적어 둔다'는 뜻이라 뺀다). */
const JUDGMENT = ['많', '되겠', '될 것', '좋', '나쁘', '유망', '추천', '괜찮', '충분', '부족', '활발', '위험', '높습', '높은', '낮습', '낮은', '비싸', '저렴', '인기', '늘었', '줄었'];
/** 「일하는 사람」·「직장인구」 낱말이 든 글만 고른다. */
function mentionsWorker(texts: readonly string[]): string[] {
  return texts.filter((t) => t.includes('일하는 사람') || t.includes('직장인구'));
}

/** 주석을 지운 원문 — 코드 글만 본다. */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1');
}

const SOURCES = ['./districtCensusPop.ts', '../components/CensusPopSection.tsx'];
const readSrc = (f: string) => readFileSync(fileURLToPath(new URL(f, import.meta.url)), 'utf-8');

/** 이 카드가 만드는 글 전부(상권 둘 · 건물 단위 셋 · no_data · 상수). */
function allTexts(): string[] {
  const rows = [okRow(), wideRow()];
  const texts: string[] = [
    CENSUS_POP_TITLE,
    CENSUS_LEAD_STRONG,
    ...CENSUS_LEAD_REST,
    CENSUS_BADGE,
    censusBadgeNote(okRow()),
    censusSourceText(okRow()),
    ...Object.values(CENSUS_CHUNK_TITLES),
    ...Object.values(CENSUS_NOTES),
    CENSUS_NO_DATA_TEXT,
    censusSummary(rows, DJ),
    censusSummary([noDataRow()], DJ),
  ];
  for (const s of ['no_coord', 'not_daejeon', 'outside_daejeon_district'] as const) {
    texts.push(censusHeadBody(s, DJ), censusHeadSummary(s, DJ));
  }
  for (const r of rows) {
    for (const big of [residentBig(r), empBig(r)]) texts.push(big!.num, big!.range ?? '', big!.detail ?? '');
    texts.push(censusNote(r)!);
  }
  return texts.filter((t) => t !== '');
}

describe('⛔ 글 가드', () => {
  it('양성 대조 — 탐지가 실제로 잡는다', () => {
    expect(findQuarterOrYearLiterals("`통계청 SGIS 2024년 집계구`")).toEqual(['2024년']);
    expect(findQuarterOrYearLiterals("'2025-06'")).toEqual(['2025-06']);
    expect(mentionsWorker(['일하는 사람 (직장인구)', '사는 사람', '직장인구는 서울만'])).toHaveLength(2);
    expect(stripComments("// 2024년\nconst a = '%';").includes('2024년')).toBe(false);
    expect(JUDGMENT.filter((w) => '사람이 많은 상권'.includes(w))).toEqual(['많']);
  });

  it('ⓐ lib·컴포넌트 원문에 분기·연도 글자·금지어·「유동인구」가 없다', () => {
    for (const f of SOURCES) {
      const src = readSrc(f);
      expect(findQuarterOrYearLiterals(src), f).toEqual([]);
      for (const w of [...FORBIDDEN, '유동인구']) expect(src.includes(w), `${f} ${w}`).toBe(false);
    }
  });

  it('ⓑ 코드 글(주석 밖)의 % 는 lib 의 덮임 줄 한 곳뿐 · 컴포넌트는 0', () => {
    const lib = stripComments(readSrc('./districtCensusPop.ts'));
    const pctLines = lib.split('\n').filter((l) => /[%％]/.test(l));
    expect(pctLines).toHaveLength(1);
    expect(pctLines[0]).toContain('coverText(row.cover_pct)');
    expect(/[%％]/.test(stripComments(readSrc('../components/CensusPopSection.tsx')))).toBe(false);
  });

  it('ⓒ 만드는 글 — % 는 덮임 발에만 · 「2배」는 발 문구 셋째에만 · 금지어·판단 낱말·「유동인구」 0 · 연도는 서버 값 자리에만', () => {
    const texts = allTexts();
    expect(texts.length).toBeGreaterThan(20); // 헛돌지 않는다
    for (const t of texts) {
      const isNote = t.startsWith('겹친 집계구');
      expect(/[%％]|퍼센트/.test(t), t).toBe(isNote);
      if (/\d\s*배/.test(t)) expect(t).toBe(CENSUS_NOTES.method);
      for (const w of FORBIDDEN) expect(t.replace(/\s+/g, '').includes(w), `${w} · ${t}`).toBe(false);
      expect(JUDGMENT.filter((w) => t.includes(w)), t).toEqual([]);
      expect(t.includes('유동인구'), t).toBe(false);
    }
  });

  it('ⓓ 「일하는 사람」·「직장인구」는 발 문구 넷째 한 문장에만', () => {
    expect(mentionsWorker(allTexts())).toEqual([CENSUS_NOTES.empNotWorker]);
    // 원문에서도 그 상수 한 곳뿐(주석 밖).
    for (const f of SOURCES) {
      const lines = stripComments(readSrc(f))
        .split('\n')
        .filter((l) => l.includes('일하는 사람') || l.includes('직장인구'));
      expect(lines.length, f).toBe(f.endsWith('.ts') ? 1 : 0);
    }
  });
});
