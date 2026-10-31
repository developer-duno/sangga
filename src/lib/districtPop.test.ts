import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { DistrictPop } from '../types';
import {
  POP_BADGE,
  POP_BADGE_NOTE,
  POP_BAR_GROUPS,
  POP_CHUNK_TITLES,
  POP_LEAD_REST,
  POP_LEAD_STRONG,
  POP_NOTES,
  POP_NO_DATA_TEXT,
  flowBars,
  flowBigText,
  flowLagText,
  isDistrictPopList,
  normalizePopRows,
  popSummary,
  residentLagText,
  residentText,
  valueYearText,
  workerLagText,
  workerText,
} from './districtPop';

/**
 * 「상권 인구 (서울시 공표)」 순수 계산(결정 0045 PR③).
 * 지키는 것: 모양 검사(섞인 답 통째 거부) · 접힌 요약 값 0 · 3개월간 인구수 그대로 · 「YYYY년 기준」 = value_quarter ·
 * 끊긴 상권 「…까지」 · 분기·연도 글자 0 · 비율·나누기 글자 0 · 판단 낱말 0 · 금지어 0.
 */

const PNU = '1168010100100010000';

const FLOW = {
  tot: 412560,
  ml: 190100,
  fml: 222460,
  agrde_10: 1,
  tmzon_00_06: 58000,
  tmzon_06_11: 82300,
  tmzon_11_14: 69700,
  tmzon_14_17: 68000,
  tmzon_17_21: 84000,
  tmzon_21_24: 50400,
  mon: 59900,
  tues: 59900,
  wed: 60500,
  thur: 59900,
  fri: 59900,
  sat: 57500,
  sun: 55000,
};

function okRow(over: Partial<DistrictPop> = {}): DistrictPop {
  return {
    status: 'ok',
    district_id: '3110001',
    district_nm: '○○역 2번 출구',
    district_type: '골목상권',
    flow_table_quarter: '20262',
    flow_quarter: '20262',
    flow: FLOW,
    resident_value_quarter: '20234',
    resident_last_quarter: '20262',
    resident: { tot: 2310, ml: 1090, fml: 1220, tot_hshld: 1120, apt_hshld: 1, non_apt_hshld: 1 },
    worker_value_quarter: '20244',
    worker_last_quarter: '20262',
    worker: { tot: 6840, ml: 3900, fml: 2940 },
    ...over,
  };
}

function headRow(status: DistrictPop['status']): DistrictPop {
  return {
    status,
    district_id: null,
    district_nm: null,
    district_type: null,
    flow_table_quarter: null,
    flow_quarter: null,
    flow: null,
    resident_value_quarter: null,
    resident_last_quarter: null,
    resident: null,
    worker_value_quarter: null,
    worker_last_quarter: null,
    worker: null,
  };
}

function noDataRow(): DistrictPop {
  return { ...headRow('no_data'), district_id: '3110002', district_nm: '△△ 골목', district_type: '골목상권' };
}

describe('isDistrictPopList — 모양 검사', () => {
  it('정상 답(상권 줄 · no_data · 상태 줄 · 셋 중 일부 null)은 받는다', () => {
    expect(isDistrictPopList([okRow()])).toBe(true);
    expect(isDistrictPopList([okRow(), noDataRow()])).toBe(true);
    expect(isDistrictPopList([headRow('not_seoul')])).toBe(true);
    expect(isDistrictPopList([okRow({ resident: null, resident_value_quarter: null })])).toBe(true);
    expect(isDistrictPopList([okRow({ flow: null, flow_quarter: null })])).toBe(true);
  });

  it('⛔ 빈 배열 · 모르는 상태 거부', () => {
    expect(isDistrictPopList([])).toBe(false);
    expect(isDistrictPopList(null)).toBe(false);
    expect(isDistrictPopList([{ ...okRow(), status: 'x' }])).toBe(false);
  });

  it('⛔ 칸 하나라도 어긋나면 거부 — 길단위 시간대·요일 빠짐 · 소수 · 분기 꼴 · 값은 있는데 분기 없음', () => {
    const { tmzon_21_24: _drop, ...noTime } = FLOW;
    const { sun: _sun, ...noSun } = FLOW;
    const bad: Array<Record<string, unknown>> = [
      { flow: noTime },
      { flow: noSun },
      { flow: { ...FLOW, tot: 1.5 } },
      { flow: { ...FLOW, ml: -1 } },
      { resident: { tot: 1, ml: 1 } },
      { worker: { tot: '1', ml: 1, fml: 1 } },
      { resident_value_quarter: '2023Q4' },
      { worker_last_quarter: 20262 },
      { flow_quarter: null },
      { district_id: null },
      { flow: [] },
    ];
    for (const b of bad) expect(isDistrictPopList([{ ...okRow(), ...b }]), JSON.stringify(b)).toBe(false);
  });

  it('⛔ 섞인 답(정상 줄 + 이상한 줄 하나)은 통째로 거부 — 양성 대조: 정상 둘은 받는다', () => {
    expect(isDistrictPopList([okRow(), okRow({ district_id: 'x2' })])).toBe(true);
    expect(isDistrictPopList([okRow(), { ...okRow(), worker: { tot: 1, ml: 1, fml: 0.5 } }])).toBe(false);
  });
});

describe('popSummary — 접힌 요약 (값 0)', () => {
  it('★ 길단위 = 표 전체 최신 · 사는/일하는 = 값이 바뀐 해', () => {
    expect(popSummary([okRow(), noDataRow()], PNU)).toBe(
      '○○역 2번 출구 외 상권 1곳 · 길단위인구 2026년 2분기 · 사는 사람 2023년 · 일하는 사람 2024년 기준',
    );
  });

  it('셋 중 없는 것은 그 조각을 뺀다', () => {
    expect(popSummary([okRow({ resident: null, resident_value_quarter: null })], PNU)).toBe(
      '○○역 2번 출구 · 길단위인구 2026년 2분기 · 일하는 사람 2024년 기준',
    );
    expect(
      popSummary([okRow({ resident_value_quarter: null, worker_value_quarter: null, resident: null, worker: null })], PNU),
    ).toBe('○○역 2번 출구 · 길단위인구 2026년 2분기');
  });

  it('빈 상태 넷 — 개업·폐업 카드와 같은 글 · no_data 만 인구 글', () => {
    expect(popSummary([headRow('not_seoul')], '3011010700108770000')).toBe(
      '서울 상권만 다루는 자료라 이 건물(대전)에는 없습니다',
    );
    expect(popSummary([headRow('outside_seoul_district')], PNU)).toBe('이 건물이 속한 서울시 상권이 없습니다');
    expect(popSummary([headRow('no_coord')], PNU)).toBe('위치 정보가 없어 속한 상권을 찾지 못했습니다');
    expect(popSummary([noDataRow()], PNU)).toBe('△△ 골목 · 서울시 인구 자료가 없습니다');
  });

  it('⛔ 요약에 인구 수가 없다', () => {
    expect(popSummary([okRow()], PNU)).not.toMatch(/명|412|2,310/);
  });

  it('★ 길단위 분기는 표 전체 최신(flow_table_quarter) — 그 상권이 옛 분기에서 끊겼어도(검사 뒤 보완 F5 · 개업·폐업 요약과 같은 규칙)', () => {
    const lagging = okRow({ flow_quarter: '20254', flow_table_quarter: '20262' });
    expect(popSummary([lagging], PNU)).toBe(
      '○○역 2번 출구 · 길단위인구 2026년 2분기 · 사는 사람 2023년 · 일하는 사람 2024년 기준',
    );
    expect(popSummary([lagging], PNU)).not.toContain('2025년 4분기');
  });
});

describe('normalizePopRows — ok 인데 셋 다 없으면 no_data (검사 뒤 보완 F12)', () => {
  it('★ 셋 다 null 인 ok 줄은 no_data · 하나라도 있으면 그대로 · 상태 줄도 그대로', () => {
    const empty = okRow({ flow: null, flow_quarter: null, resident: null, worker: null });
    const out = normalizePopRows([empty, okRow({ resident: null, worker: null }), headRow('not_seoul')]);
    expect(out.map((r) => r.status)).toEqual(['no_data', 'ok', 'not_seoul']);
    // no_data 로 바뀐 줄은 요약·덩어리에서 「자료 없음」 갈래로 간다.
    expect(popSummary([out[0]], PNU)).toBe('○○역 2번 출구 · 서울시 인구 자료가 없습니다');
    expect(flowBigText(out[0])).toBeNull();
  });
});

describe('길단위인구 덩이', () => {
  it('★ 큰 숫자 = 3개월간 인구수 그대로 · 「3개월간」이 바로 옆', () => {
    expect(flowBigText(okRow())).toEqual({
      num: '412,560명',
      when: '2026년 2분기 3개월간',
      detail: '남 190,100 · 여 222,460',
    });
    expect(flowBigText(okRow({ flow: null, flow_quarter: null }))).toBeNull();
    expect(flowBigText(noDataRow())).toBeNull();
  });

  it('★ 미니 막대 — 시간대 6 · 요일 7 · 값 그대로 · 높이 = 값 ÷ 그 묶음 최댓값 · 눈금 글', () => {
    const b = flowBars(okRow())!;
    expect(b.time.bars.map((x) => x.tick)).toEqual(['0~6', '6~11', '11~14', '14~17', '17~21', '21~24']);
    expect(b.day.bars.map((x) => x.tick)).toEqual(['월', '화', '수', '목', '금', '토', '일']);
    expect(b.time.max).toBe(84000);
    expect(b.time.bars.find((x) => x.tick === '17~21')!.h).toBe(100);
    expect(b.time.bars[0].h).toBeCloseTo((58000 / 84000) * 100, 6);
    expect(b.time.bars[0].value).toBe(58000);
    // 단위 꼬리 「(3개월간)」(검사 뒤 보완 F3).
    expect(b.time.scale).toBe('꽉 차면 84,000명(3개월간)');
    expect(b.day.scale).toBe('꽉 차면 60,500명(3개월간)');
    expect(POP_BAR_GROUPS).toEqual({ time: '시간대', day: '요일' });
  });

  it('묶음이 전부 0 이면 높이 0 · 눈금 글 없음', () => {
    const zero = Object.fromEntries(Object.entries(FLOW).map(([k, v]) => [k, k.startsWith('tmzon') ? 0 : v]));
    const b = flowBars(okRow({ flow: zero as DistrictPop['flow'] }))!;
    expect(b.time.bars.every((x) => x.h === 0)).toBe(true);
    expect(b.time.scale).toBeNull();
  });

  it('그 상권 길단위인구가 표 최신보다 옛 분기면 「…까지입니다」', () => {
    expect(flowLagText(okRow())).toBeNull();
    expect(flowLagText(okRow({ flow_quarter: '20254' }))).toBe('이 상권 길단위인구 자료는 2025년 4분기까지입니다');
  });
});

describe('사는 사람 · 일하는 사람', () => {
  it('★ 「YYYY년 기준」은 값이 마지막으로 바뀐 분기(value_quarter) — 마지막 분기(last_quarter)가 아니다', () => {
    expect(residentText(okRow())).toEqual({
      num: '2,310명',
      when: '2023년 기준 (서울시가 2024·2025년에는 안 바꿈)',
      detail: '남 1,090 · 여 1,220',
    });
    expect(workerText(okRow())).toEqual({
      num: '6,840명',
      when: '2024년 기준 (서울시가 2025년에는 안 바꿈)',
      detail: '남 3,900 · 여 2,940',
    });
    // last_quarter 는 2026 이다 — 그 해가 새면 「2026년 기준」이 된다.
    expect(residentText(okRow())!.when).not.toContain('2026');
    expect(valueYearText('20234')).toBe('2023년 기준');
    expect(valueYearText('2023Q4')).toBeNull();
  });

  it('★ 서울시가 안 바꾼 해 괄호(검사 뒤 보완 F2 · 시안 원문) — 값이 바뀐 해 + 1 ~ 마지막 분기의 해 − 1 · 비면 괄호 없음', () => {
    expect(valueYearText('20234', '20262')).toBe('2023년 기준 (서울시가 2024·2025년에는 안 바꿈)');
    expect(valueYearText('20244', '20262')).toBe('2024년 기준 (서울시가 2025년에는 안 바꿈)');
    expect(valueYearText('20254', '20262')).toBe('2025년 기준');
    expect(valueYearText('20234', null)).toBe('2023년 기준');
    expect(valueYearText('20234', '2026Q2')).toBe('2023년 기준');
  });

  it('⛔ 가구 수는 싣지 않는다(메인 결정 나 — 서울시 화면 가구세대 수와 다른 값) · 양성 대조: 답에는 가구 칸이 있다', () => {
    const r = okRow();
    expect(r.resident?.tot_hshld).toBe(1120);
    for (const t of [residentText(r)!.num, residentText(r)!.when ?? '', residentText(r)!.detail]) {
      expect(t).not.toContain('가구');
      expect(t).not.toContain('1,120');
    }
  });

  it('★ 끊긴 상권 — 값은 null 이고 마지막 분기만 있으면 「…까지입니다」 · 둘 다 없으면 덩이 없음', () => {
    const cut = okRow({ resident: null, resident_value_quarter: null, resident_last_quarter: '20224' });
    expect(residentText(cut)).toBeNull();
    expect(residentLagText(cut)).toBe('이 상권 사는 사람 자료는 2022년 4분기까지입니다');
    const cutW = okRow({ worker: null, worker_value_quarter: null, worker_last_quarter: '20234' });
    expect(workerLagText(cutW)).toBe('이 상권 일하는 사람 자료는 2023년 4분기까지입니다');
    const none = okRow({ resident: null, resident_value_quarter: null, resident_last_quarter: null });
    expect(residentText(none)).toBeNull();
    expect(residentLagText(none)).toBeNull();
    // 값이 있으면 「…까지」는 없다.
    expect(residentLagText(okRow())).toBeNull();
  });
});

// ── 가드(districtSales.test 와 같은 탐지 꼴 · 양성 대조는 그 파일에 있다 — 여기서도 하나씩 둔다) ──

function findQuarterOrYearLiterals(src: string): string[] {
  return src.match(/(?<![\d])20\d{2}(?:[1-4](?!\d)|년|Q[1-4]|-\d{2})/g) ?? [];
}
function hasRatio(text: string): boolean {
  return /[%％]|퍼센트|\d\s*배/.test(text);
}
const JUDGMENT = ['많', '적습', '적다', '적은 편', '되겠', '될 것', '좋', '나쁘', '유망', '추천', '괜찮', '충분', '부족', '활발', '위험', '높습', '높은', '낮습', '낮은', '비싸', '저렴', '인기', '늘었', '줄었', '늘다', '줄다'];
const FORBIDDEN = ['적정가격', '적정가', '평가액', '감정가', '가치평가'];
const DIVIDE_WORDS = ['점포당', '월평균', '하루 평균', '/ha', '면적당'];

function allPopTexts(): string[] {
  const r = okRow();
  const b = flowBars(r)!;
  const texts: string[] = [
    popSummary([r, noDataRow()], PNU),
    popSummary([noDataRow()], PNU),
    flowLagText(okRow({ flow_quarter: '20254' })) ?? '',
    residentLagText(okRow({ resident: null, resident_last_quarter: '20224' })) ?? '',
    workerLagText(okRow({ worker: null, worker_last_quarter: '20234' })) ?? '',
    POP_LEAD_STRONG,
    ...POP_LEAD_REST,
    POP_BADGE,
    POP_BADGE_NOTE,
    POP_NO_DATA_TEXT,
    ...Object.values(POP_CHUNK_TITLES),
    ...Object.values(POP_NOTES),
    b.time.scale ?? '',
    b.day.scale ?? '',
  ];
  for (const big of [flowBigText(r), residentText(r), workerText(r)]) texts.push(big!.num, big!.when ?? '', big!.detail);
  return texts;
}

describe('⛔ 가드 — 분기·연도 글자 · 비율·나누기 · 판단 낱말 · 금지어', () => {
  it('양성 대조', () => {
    expect(findQuarterOrYearLiterals("'20234'")).toEqual(['20234']);
    expect(hasRatio('남자 46%')).toBe(true);
    expect(JUDGMENT.filter((w) => '사람이 많은 상권'.includes(w))).toEqual(['많']);
  });

  it('ⓐ 카드·도우미 원문에 분기·연도 글자·금지어가 없다', () => {
    for (const f of ['./districtPop.ts', '../components/PopSection.tsx']) {
      const src = readFileSync(fileURLToPath(new URL(f, import.meta.url)), 'utf-8');
      expect(findQuarterOrYearLiterals(src), f).toEqual([]);
      for (const w of FORBIDDEN) expect(src.includes(w), `${f} ${w}`).toBe(false);
    }
  });

  it('ⓑ·ⓒ·ⓓ 만드는 글에 비율·나누기 낱말·판단 낱말·금지어가 없다', () => {
    for (const t of allPopTexts()) {
      expect(hasRatio(t), t).toBe(false);
      for (const w of DIVIDE_WORDS) expect(t.includes(w), `${w} · ${t}`).toBe(false);
      expect(JUDGMENT.filter((w) => t.includes(w)), t).toEqual([]);
      expect(FORBIDDEN.filter((w) => t.replace(/\s+/g, '').includes(w)), t).toEqual([]);
    }
  });

  it('ⓔ 컴포넌트 원문에 직접 적힌 글(머리·aria-label 틀 등)에도 비율·나누기·판단 낱말·분기 글자가 없다(검사 뒤 보완 F8) · 양성 대조', () => {
    // 탐지 — 주석을 지운 뒤 따옴표·백틱 글과 JSX 글 가운데 한글이 든 것(districtSales.test 의 같은 이름 함수와 같은 꼴).
    const koreanLiterals = (src: string) =>
      (src
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
        .match(/'[^'\n]*'|"[^"\n]*"|`[^`]*`|>[^<>{}\n]+</g) ?? []).filter((s) => /[가-힣]/.test(s));
    const sample = koreanLiterals('// 많은 사람\n<b>사람이 많은 상권</b>\naria-label={`${n} 하루 평균 3%`}\nstyle={{ height: `${b.h}%` }}');
    expect(sample).toHaveLength(2);
    expect(sample.some((s) => JUDGMENT.some((w) => s.includes(w)))).toBe(true);
    expect(sample.some((s) => hasRatio(s))).toBe(true);
    const comp = '../components/PopSection.tsx';
    const real = koreanLiterals(readFileSync(fileURLToPath(new URL(comp, import.meta.url)), 'utf-8'));
    expect(real.length).toBeGreaterThan(0); // 헛돌지 않는다
    for (const s of real) {
      expect(hasRatio(s), s).toBe(false);
      expect(JUDGMENT.filter((w) => s.includes(w)), s).toEqual([]);
      expect(findQuarterOrYearLiterals(s), s).toEqual([]);
      for (const w of DIVIDE_WORDS) expect(s.includes(w), `${w} · ${s}`).toBe(false);
    }
  });
});
