import { describe, it, expect } from 'vitest';
import {
  formatUnitArea,
  hasUnitList,
  noUnitDataText,
  orphanUnits,
  orphanUnitsText,
  parseFloorUnits,
  parseUnitSummary,
  unitDisplayName,
  unitSummaryText,
} from './unitTable';
import type { UnitFloorSummary } from '../types';

/**
 * 호실 구성표(결정 0032)의 순수 규칙 시험.
 *
 * 값은 2026-10-04 라이브 실호출(신구로자이 나인스에비뉴 · 강남레체 · 대전유성BYC빌딩)에서 왔다.
 */

function row(over: Partial<UnitFloorSummary> = {}): UnitFloorSummary {
  return {
    floor_no: 3,
    unit_cnt: 543,
    median_area_m2: 4.0,
    min_area_m2: 2.74,
    max_area_m2: 8.81,
    floor_kind: 'mixed',
    ...over,
  };
}

describe('parseUnitSummary — 서버 응답 모양', () => {
  it('배열이 아니면 null(실패) — 빈 배열(자료 없음)과 섞지 않는다', () => {
    expect(parseUnitSummary(null)).toBeNull();
    expect(parseUnitSummary({ code: 'PGRST202' })).toBeNull();
    expect(parseUnitSummary(undefined)).toBeNull();
    expect(parseUnitSummary([])).toEqual([]);
  });

  it('빈 칸을 허용한다 — 주거 층 면적 셋 null · 층 미상 줄(floor_no null)', () => {
    const got = parseUnitSummary([
      { floor_no: 35, unit_cnt: 10, median_area_m2: null, min_area_m2: null, max_area_m2: null, floor_kind: 'residential' },
      { floor_no: null, unit_cnt: 7, median_area_m2: null, min_area_m2: null, max_area_m2: null, floor_kind: 'unknown' },
    ]);
    expect(got).toHaveLength(2);
    expect(got![1].floor_no).toBeNull();
    expect(got![0].median_area_m2).toBeNull();
  });

  it('이상한 줄은 그 줄만 빼고 나머지는 선다 (.every() 통째 거부 금지)', () => {
    const got = parseUnitSummary([
      row({ floor_no: 4 }),
      { ...row(), floor_kind: 'apartment' },
      { ...row(), unit_cnt: 'many' },
      { ...row(), floor_no: 2.5 },
      { ...row(), median_area_m2: 'abc' },
      'garbage',
      null,
      row({ floor_no: 1, floor_kind: 'commercial' }),
    ]);
    expect(got!.map((r) => r.floor_no)).toEqual([4, 1]);
  });

  it('숫자 글자로 와도 숫자로 받는다 (numeric 칸)', () => {
    const got = parseUnitSummary([{ ...row(), median_area_m2: '4.00', unit_cnt: '543' }]);
    expect(got![0].median_area_m2).toBe(4);
    expect(got![0].unit_cnt).toBe(543);
  });
});

describe('parseFloorUnits — 서버 응답 모양', () => {
  it('배열이 아니면 null', () => {
    expect(parseFloorUnits({ code: 'PGRST202' })).toBeNull();
  });

  it('호 이름 null·빈 글자 · 면적 null 을 허용한다', () => {
    const got = parseFloorUnits([
      { ho: '3가001호', excl_area_m2: 4.0, total_cnt: 543 },
      { ho: null, excl_area_m2: null, total_cnt: 543 },
      { ho: '', excl_area_m2: 3.9, total_cnt: 543 },
    ]);
    expect(got).toHaveLength(3);
    expect(got![1].ho).toBeNull();
    expect(got![2].ho).toBe('');
  });

  it('이상한 줄은 그 줄만 뺀다', () => {
    const got = parseFloorUnits([
      { ho: 101, excl_area_m2: 4, total_cnt: 2 },
      { ho: '102호', excl_area_m2: 4, total_cnt: 'x' },
      { ho: '103호', excl_area_m2: 4, total_cnt: 2 },
    ]);
    expect(got!.map((u) => u.ho)).toEqual(['103호']);
  });
});

describe('unitSummaryText — 층 줄 아래 요약 한 줄', () => {
  it('목록 제공 층: 호실 N칸 · 보통 A㎡ · B~C㎡ (소수 첫째 자리)', () => {
    expect(unitSummaryText(row())).toBe('호실 543칸 · 보통 4.0㎡ · 2.7~8.8㎡');
    expect(unitSummaryText(row({ floor_kind: 'commercial', unit_cnt: 690, min_area_m2: 3.18, max_area_m2: 13.07 }))).toBe(
      '호실 690칸 · 보통 4.0㎡ · 3.2~13.1㎡',
    );
  });

  it('1칸이면 범위 없이 그 칸 면적만', () => {
    expect(
      unitSummaryText(row({ unit_cnt: 1, median_area_m2: 64.31, min_area_m2: 64.31, max_area_m2: 64.31 })),
    ).toBe('호실 1칸 · 64.3㎡');
  });

  it('주거 층은 세대 수만 · 오피스텔은 N실 · 미상은 용도 미상 (면적을 적지 않는다)', () => {
    const none = { median_area_m2: null, min_area_m2: null, max_area_m2: null };
    expect(unitSummaryText(row({ ...none, unit_cnt: 10, floor_kind: 'residential' }))).toBe('세대 10');
    expect(unitSummaryText(row({ ...none, unit_cnt: 10, floor_kind: 'officetel' }))).toBe('오피스텔 10실');
    expect(unitSummaryText(row({ ...none, unit_cnt: 12, floor_kind: 'unknown' }))).toBe('호실 12칸 · 용도 미상');
  });

  it('⛔ 서버가 실수로 주거 층에 면적을 실어 보내도 화면은 적지 않는다', () => {
    expect(unitSummaryText(row({ floor_kind: 'residential', unit_cnt: 2 }))).toBe('세대 2');
  });

  it('목록 제공 층인데 면적이 없으면 면적 조각만 뺀다 (0㎡ 를 지어내지 않는다)', () => {
    expect(
      unitSummaryText(row({ median_area_m2: null, min_area_m2: null, max_area_m2: null, unit_cnt: 3 })),
    ).toBe('호실 3칸');
  });

  it('천 단위 쉼표', () => {
    expect(unitSummaryText(row({ unit_cnt: 5372 }))).toContain('호실 5,372칸');
  });
});

describe('그 밖의 작은 규칙', () => {
  it('목록은 commercial·mixed 층에서만', () => {
    expect(hasUnitList('commercial')).toBe(true);
    expect(hasUnitList('mixed')).toBe(true);
    expect(hasUnitList('residential')).toBe(false);
    expect(hasUnitList('officetel')).toBe(false);
    expect(hasUnitList('unknown')).toBe(false);
  });

  it('면적 표기 — 0 이하·빈 값은 —', () => {
    expect(formatUnitArea(3.94)).toBe('3.9㎡');
    expect(formatUnitArea(4)).toBe('4.0㎡');
    expect(formatUnitArea(84083)).toBe('84,083.0㎡');
    expect(formatUnitArea(0)).toBe('—');
    expect(formatUnitArea(null)).toBe('—');
  });

  it('호 이름은 원문 그대로 · 빈 이름(null·빈 글자)은 "(호 이름 없음)"', () => {
    expect(unitDisplayName(' 3가001호 ')).toBe(' 3가001호 ');
    expect(unitDisplayName(null)).toBe('(호 이름 없음)');
    expect(unitDisplayName('')).toBe('(호 이름 없음)');
  });

  it('자료 없는 건물 안내는 건물 종류로 가르고, 모르면 중립 문장만', () => {
    expect(noUnitDataText(false)).toBe(
      '이 건물에는 호실 자료가 없습니다 — 칸별로 등기가 나뉘지 않은 일반 건물이면 원래 없는 자료입니다.',
    );
    expect(noUnitDataText(true, 3)).toBe(
      '이 건물에는 호실 자료가 없습니다 — 같은 땅 다른 동에 붙어 있을 수 있습니다.',
    );
    expect(noUnitDataText(true, 3)).not.toContain('일반 건물');
    expect(noUnitDataText(null)).toBe('이 건물에는 호실 자료가 없습니다.');
  });

  it('⛔ "같은 땅 다른 동" 절은 그 땅에 동이 둘 이상일 때만 — 한 동이거나 모르면 중립 문장', () => {
    const neutral = '이 건물에는 호실 자료가 없습니다.';
    expect(noUnitDataText(true, 1)).toBe(neutral);
    expect(noUnitDataText(true, null)).toBe(neutral);
    expect(noUnitDataText(true)).toBe(neutral);
    expect(noUnitDataText(true, 2)).toContain('같은 땅 다른 동');
  });

  it('⛔ 동 수가 문자열로 와도("3") "같은 땅 다른 동" 절을 붙이지 않는다 — 숫자일 때만', () => {
    // 서버 답의 모양이 어긋나 동 수가 글자로 오는 경우를 타입을 속여 흉내 낸다.
    // `'3' > 1` 은 JS 에서 참이라, `typeof` 가드가 빠지면 이 시험이 빨강이 된다.
    const asString = '3' as unknown as number;
    expect(noUnitDataText(true, asString)).toBe('이 건물에는 호실 자료가 없습니다.');
    // 양성 대조 — 같은 값이 숫자로 오면 그 절이 붙는다(가드가 늘 중립만 내는 꼴이 아님을 확인).
    expect(noUnitDataText(true, 3)).toBe(
      '이 건물에는 호실 자료가 없습니다 — 같은 땅 다른 동에 붙어 있을 수 있습니다.',
    );
  });
});

describe('orphanUnits — 층 줄에 붙을 자리가 없는 호실', () => {
  it('층 미상 줄과 층 목록에 없는 층을 따로 센다', () => {
    const summary = [
      row({ floor_no: 3, unit_cnt: 10 }),
      row({ floor_no: 7, unit_cnt: 4 }),
      row({ floor_no: 8, unit_cnt: 5 }),
      row({ floor_no: null, unit_cnt: 2, floor_kind: 'unknown' }),
    ];
    const o = orphanUnits(summary, [3, 2, 1]);
    expect(o).toEqual({ noFloorUnits: 2, missingFloors: 2, missingFloorUnits: 9 });
    expect(orphanUnitsText(o)).toBe('층을 알 수 없는 호실 2칸 · 층 목록에 없는 층 2개의 호실 9칸');
  });

  it('모두 붙으면 줄을 안 그린다 (null)', () => {
    expect(orphanUnitsText(orphanUnits([row({ floor_no: 3 })], [3]))).toBeNull();
  });
});
