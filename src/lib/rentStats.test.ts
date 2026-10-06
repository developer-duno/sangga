import { describe, it, expect } from 'vitest';
import type { DistrictOpenClose, RentStat } from '../types';
import { openCloseSummary } from './openClose';
import {
  BLD_TYPE_ORDER,
  defaultBldType,
  floorRentLines,
  formatRate,
  formatRentPerM2,
  isRentStatList,
  lacksCoord,
  quarterLabel,
  RENT_NO_COORD_SUMMARY,
  rentSummary,
  toRentRows,
  typeOptions,
} from './rentStats';

/**
 * 상권 임대 동향 카드의 순수 규칙(결정 0024).
 *
 * 여기서 특히 지키는 것
 * ---------------------
 *  ① **단위** — 공표값은 천원/㎡ 다(원본 raw 의 `UI_NM` 실측). 1,000을 안 곱하면 화면이
 *     실제의 1/1000 을 적고, 그 숫자도 그럴듯해서 아무도 못 알아챈다.
 *  ② **없는 값에 칸을 만들지 않는다** — 조사 안 한 지표에 '—'를 적으면 조사했는데 비어
 *     있는 것처럼 읽힌다.
 *  ③ **요약에 값을 담지 않는다** — 접힌 요약에는 "이 건물이 아니라 상권"이라는 한정어를
 *     담을 자리가 없어서, 숫자만 나오면 이 건물 값으로 읽힌다.
 */

function stat(over: Partial<RentStat> = {}): RentStat {
  return {
    district_nm: '역삼역',
    rone_region_nm: '서울>강남>테헤란로',
    bld_type: '집합상가',
    quarter: '2026Q2',
    vacancy_rate: 10.08,
    rent_per_m2: 27.06,
    yield_rate: 0.82,
    ...over,
  };
}

describe('quarterLabel — 조사 분기', () => {
  it("'2026Q2' 를 '2026년 2분기'로 적는다", () => {
    expect(quarterLabel('2026Q2')).toBe('2026년 2분기');
  });

  it('읽을 수 없으면 null 이다 (원본 코드가 화면으로 새어 나가지 않게)', () => {
    // '—'나 원본을 돌려주면 화면에 "(2026Q9 조사)" 같은 말이 그대로 박힌다.
    expect(quarterLabel('2026Q9')).toBeNull();
    expect(quarterLabel('202602')).toBeNull();
    expect(quarterLabel(null)).toBeNull();
    expect(quarterLabel('')).toBeNull();
  });
});

describe('formatRentPerM2 — 공표 단위(천원/㎡)를 원으로', () => {
  it('★ 1,000을 곱한다 (안 곱하면 화면이 실제의 1/1000을 적는다)', () => {
    expect(formatRentPerM2(27.06)).toBe('27,060원');
  });

  it('원 단위로 반올림한다 (소수 원은 뜻이 없다)', () => {
    expect(formatRentPerM2(27.0631)).toBe('27,063원');
  });

  it('값이 아니면 null 이다 (칸 자체를 안 만들게)', () => {
    expect(formatRentPerM2(null)).toBeNull();
    expect(formatRentPerM2(undefined)).toBeNull();
    expect(formatRentPerM2(Number.NaN)).toBeNull();
  });

  it('0 은 값으로 적는다 (없는 것과 0 은 다르다)', () => {
    expect(formatRentPerM2(0)).toBe('0원');
  });
});

describe('formatRate — 비율', () => {
  it('소수 둘째 자리까지 둔다 (분기 수익률은 1% 안팎이라 첫째로 뭉개면 값이 사라진다)', () => {
    expect(formatRate(0.817)).toBe('0.82%');
    expect(formatRate(10.077)).toBe('10.08%');
  });

  it('값이 아니면 null 이다', () => {
    expect(formatRate(null)).toBeNull();
    expect(formatRate(Number.POSITIVE_INFINITY)).toBeNull();
  });
});

describe('typeOptions / defaultBldType — 건물 종류', () => {
  it('정해진 차례대로 준다 — 맨 앞이 집합상가다', () => {
    const rows = [stat({ bld_type: '오피스' }), stat({ bld_type: '집합상가' })];
    expect(typeOptions(rows)).toEqual(['집합상가', '오피스']);
    expect(defaultBldType(rows)).toBe('집합상가');
  });

  it('집합상가가 없으면 있는 것 중 첫째가 기본이다 (없는 종류를 화면에 박지 않는다)', () => {
    const rows = [stat({ bld_type: '오피스' }), stat({ bld_type: '소규모상가' })];
    expect(defaultBldType(rows)).toBe('소규모상가');
  });

  it('★ 모르는 종류도 버리지 않는다 (부동산원이 늘리는 날 조용히 빠지지 않게)', () => {
    const rows = [stat({ bld_type: '새로운상가' }), stat({ bld_type: '집합상가' })];
    expect(typeOptions(rows)).toEqual(['집합상가', '새로운상가']);
  });

  it('줄이 없으면 고를 것도 없다', () => {
    expect(typeOptions([])).toEqual([]);
    expect(defaultBldType([])).toBeNull();
  });

  it('차례표에 넷이 그대로 있다 (부동산원 조사 종류)', () => {
    expect([...BLD_TYPE_ORDER]).toEqual(['집합상가', '중대형상가', '소규모상가', '오피스']);
  });
});

describe('toRentRows — 고른 종류의 줄', () => {
  it('고른 종류만 남기고, 세 지표를 라벨과 함께 낸다', () => {
    const rows = toRentRows([stat(), stat({ bld_type: '오피스' })], '집합상가');
    expect(rows).toHaveLength(1);
    expect(rows[0].districtNm).toBe('역삼역');
    expect(rows[0].regionNm).toBe('서울>강남>테헤란로');
    expect(rows[0].quarter).toBe('2026년 2분기');
    expect(rows[0].metrics.map((m) => `${m.label} ${m.value}`)).toEqual([
      '공실률 10.08%',
      '㎡당 임대료 27,060원',
      '투자수익률(분기) 0.82%',
    ]);
  });

  it('★ 수익률 라벨에 "분기"가 붙어 있다 (연 수익률로 읽히면 뜻이 정반대가 된다)', () => {
    // 상가 수익률을 연 4~5%로 아는 사람에게 0.82%는 "형편없는 자리"로 읽힌다.
    const [row] = toRentRows([stat()], '집합상가');
    expect(row.metrics.find((m) => m.key === 'yield')?.label).toBe('투자수익률(분기)');
  });

  it('없는 지표는 칸을 아예 안 만든다 (조사 안 한 것을 비어 있는 것처럼 보이지 않게)', () => {
    const [row] = toRentRows([stat({ vacancy_rate: null, yield_rate: null })], '집합상가');
    expect(row.metrics.map((m) => m.key)).toEqual(['rent']);
  });

  it('셋 다 없는 줄은 통째로 버린다 (상권 이름만 남은 빈 줄은 "0"처럼 읽힌다)', () => {
    const empty = stat({ vacancy_rate: null, rent_per_m2: null, yield_rate: null });
    expect(toRentRows([empty], '집합상가')).toEqual([]);
  });

  it('상권 이름이 없어도 자리를 비워 두지 않는다', () => {
    const [row] = toRentRows([stat({ district_nm: null })], '집합상가');
    expect(row.districtNm).toBe('(이름 없는 상권)');
  });

  it('★ 같은 상권이 조사구역 둘이면 둘 다 나온다 (하나로 뭉치지 않는다)', () => {
    // 부동산원이 건물 종류마다 서울 권역 분할을 달리해 한 상권이 경로 둘을 갖는다
    // (district_rone_map 의 PK 가 복합인 이유). 뭉치면 한쪽 조사구역이 사라진다.
    const rows = toRentRows(
      [stat(), stat({ rone_region_nm: '서울>영등포신촌>여의도', vacancy_rate: 5.5 })],
      '집합상가',
    );
    expect(rows.map((r) => r.regionNm)).toEqual([
      '서울>강남>테헤란로',
      '서울>영등포신촌>여의도',
    ]);
    expect(rows[0].key).not.toBe(rows[1].key);
  });

  it('분기를 못 읽으면 도장을 안 찍는다 (없는 시점을 지어내지 않는다)', () => {
    const [row] = toRentRows([stat({ quarter: 'zzz' })], '집합상가');
    expect(row.quarter).toBeNull();
  });
});

describe('rentSummary — 접혀 있어도 보이는 한 줄', () => {
  it('무엇이 들어 있는지와 언제 것인지만 말한다', () => {
    expect(rentSummary([stat()])).toBe('공실률 · ㎡당 임대료 · 투자수익률 · 2026년 2분기 조사');
  });

  it('★ 요약에 값을 담지 않는다 (숫자만 보면 이 건물 값으로 읽힌다)', () => {
    const summary = rentSummary([stat()]);
    expect(summary).not.toContain('10.08');
    expect(summary).not.toContain('27,060');
  });

  it('분기가 여럿이면 개수만 말한다 (하나를 고르면 나머지 줄에 거짓말이 된다)', () => {
    const summary = rentSummary([stat(), stat({ quarter: '2026Q1', bld_type: '오피스' })]);
    expect(summary).toBe('공실률 · ㎡당 임대료 · 투자수익률 · 조사 분기 2개');
  });

  it('분기를 하나도 못 읽으면 시점 조각만 뺀다', () => {
    expect(rentSummary([stat({ quarter: 'zzz' })])).toBe('공실률 · ㎡당 임대료 · 투자수익률');
  });

  it('★ 줄이 없으면 그렇다고 적는다 (시·도 평균으로 메우지 않는다)', () => {
    expect(rentSummary([])).toBe('부동산원 조사 대상 상권이 아닙니다');
  });

  it('★ 좌표 없는 건물의 빈 줄은 "상권을 못 찾음" — 개업·폐업 카드(no_coord)와 같은 글 (2026-10-06)', () => {
    const noCoordRow: DistrictOpenClose = {
      status: 'no_coord',
      district_id: null,
      district_nm: null,
      district_type: null,
      latest_quarter: null,
      quarters: null,
      industries: null,
      other_industries: null,
      window_quarters: [],
    };
    expect(rentSummary([], true)).toBe(RENT_NO_COORD_SUMMARY);
    expect(rentSummary([], true)).toBe(openCloseSummary([noCoordRow], '1168010100100010000'));
    // 줄이 왔으면 좌표와 상관없이 원래 요약이다.
    expect(rentSummary([stat()], true)).toBe(rentSummary([stat()]));
  });
});

// ── 결정 0031 — 층별 임대료 · 소득수익률 (선택 칸 둘) ─────────────────────────

/** 2026-10-04 라이브 실호출 값(서울>강남>테헤란로 · 집합상가 · 2026Q2 — 천원/㎡). */
const TEHERAN_COLLECTIVE = {
  '1': 74.6,
  '2': 32.48,
  '3': 23.54,
  '4': 23.73,
  '5': 25.0,
  '-1': 16.95,
  '6+': 22.7,
};

/** 같은 곳 오피스 — 위 구간이 6~10층 · 11층 이상으로 나뉜다. */
const TEHERAN_OFFICE = {
  '1': 38.99,
  '2': 31.4,
  '3': 27.09,
  '4': 26.6,
  '5': 26.51,
  '-1': 13.93,
  '11+': 28.62,
  '6-10': 26.73,
};

describe('floorRentLines — 층별 표의 줄 (결정 0031)', () => {
  it('★ 높은 층이 위로, 열쇠를 사람 말로, 천원/㎡ 를 원으로 바꿔 낸다', () => {
    expect(floorRentLines(TEHERAN_COLLECTIVE).map((l) => `${l.label} ${l.value}`)).toEqual([
      '6층 이상 22,700원',
      '5층 25,000원',
      '4층 23,730원',
      '3층 23,540원',
      '2층 32,480원',
      '1층 74,600원',
      '지하 1층 16,950원',
    ]);
  });

  it('오피스의 두 위 구간(11층 이상 · 6~10층)도 높은 층부터 선다', () => {
    expect(floorRentLines(TEHERAN_OFFICE).map((l) => l.label)).toEqual([
      '11층 이상',
      '6~10층',
      '5층',
      '4층',
      '3층',
      '2층',
      '1층',
      '지하 1층',
    ]);
  });

  it('★ 모르는 열쇠·숫자 아님·0 이하는 그 줄만 빼고 나머지는 그린다 (표 전체를 버리지 않는다)', () => {
    const lines = floorRentLines({
      '1': 52.46,
      '2': '32.96',
      '3': 0,
      '4': -1,
      '7': 20,
      B2: 10,
      '5': Number.NaN,
      '-1': 19.0,
    });
    expect(lines.map((l) => l.key)).toEqual(['1', '-1']);
  });

  it('없거나 객체가 아니면 빈 표다 (던지지 않는다)', () => {
    expect(floorRentLines(undefined)).toEqual([]);
    expect(floorRentLines(null)).toEqual([]);
    expect(floorRentLines('{"1":74.6}')).toEqual([]);
    // 배열은 열쇠 '1' 을 가진 객체처럼 보이지만 층별 표가 아니다.
    expect(floorRentLines([10, 20])).toEqual([]);
    expect(floorRentLines({})).toEqual([]);
  });
});

describe('toRentRows — 층별 표 · 소득수익률 (결정 0031)', () => {
  it('★ 소득수익률을 분기 라벨로 투자수익률 뒤에 적는다', () => {
    const [row] = toRentRows([stat({ income_yield_rate: 0.9 })], '집합상가');
    expect(row.metrics.map((m) => `${m.label} ${m.value}`)).toEqual([
      '공실률 10.08%',
      '㎡당 임대료 27,060원',
      '투자수익률(분기) 0.82%',
      '소득수익률(분기) 0.9%',
    ]);
  });

  it('★ 소득수익률 0 은 "0%" 로 적는다 (빈 값과 다르다 — null 일 때만 없음)', () => {
    const [zero] = toRentRows([stat({ income_yield_rate: 0 })], '집합상가');
    expect(zero.metrics.find((m) => m.key === 'income')?.value).toBe('0%');
    const [none] = toRentRows([stat({ income_yield_rate: null })], '집합상가');
    expect(none.metrics.find((m) => m.key === 'income')).toBeUndefined();
  });

  it('소득수익률 자리에 글자가 와도 그 값만 빠진다 (줄은 선다)', () => {
    const [row] = toRentRows(
      [stat({ income_yield_rate: '0.9' as unknown as number })],
      '집합상가',
    );
    expect(row.metrics.map((m) => m.key)).toEqual(['vacancy', 'rent', 'yield']);
  });

  it('줄마다 그 줄의 층별 표가 붙는다 (조사구역끼리 섞이지 않는다)', () => {
    const rows = toRentRows(
      [
        stat({ floor_rent: TEHERAN_COLLECTIVE }),
        stat({ rone_region_nm: '서울>영등포신촌>여의도', floor_rent: { '1': 40 } }),
      ],
      '집합상가',
    );
    expect(rows[0].floorRents).toHaveLength(7);
    expect(rows[1].floorRents.map((l) => `${l.label} ${l.value}`)).toEqual(['1층 40,000원']);
  });

  it('★ 새 칸이 없는 줄(옛 함수의 답)도 그대로 선다 — 표는 빈 채로', () => {
    const [row] = toRentRows([stat()], '집합상가');
    expect(row.floorRents).toEqual([]);
    expect(row.metrics.map((m) => m.key)).toEqual(['vacancy', 'rent', 'yield']);
  });

  it('지표는 다 비어도 층별 표가 있으면 줄을 버리지 않는다', () => {
    const only = stat({
      vacancy_rate: null,
      rent_per_m2: null,
      yield_rate: null,
      floor_rent: { '1': 30 },
    });
    const rows = toRentRows([only], '집합상가');
    expect(rows).toHaveLength(1);
    expect(rows[0].metrics).toEqual([]);
  });
});

describe('rentSummary — 소득수익률 · 층별 표 (결정 0031)', () => {
  it('★ 온 값이 있으면 소득수익률 이름과 끝에 "층별 임대료 포함"을 더한다 (값은 여전히 안 적는다)', () => {
    const summary = rentSummary([
      stat({ income_yield_rate: 0.9, floor_rent: TEHERAN_COLLECTIVE }),
    ]);
    expect(summary).toBe(
      '공실률 · ㎡당 임대료 · 투자수익률 · 소득수익률 · 2026년 2분기 조사 · 층별 임대료 포함',
    );
    expect(summary).not.toContain('74,600');
  });

  it('소득수익률이 0 이어도 이름은 선다 (0 은 값이다)', () => {
    expect(rentSummary([stat({ income_yield_rate: 0 })])).toBe(
      '공실률 · ㎡당 임대료 · 투자수익률 · 소득수익률 · 2026년 2분기 조사',
    );
  });

  it('층별 표가 하나도 없으면 "층별 임대료 포함"을 적지 않는다 (펼쳐도 없는 것을 약속하지 않는다)', () => {
    expect(rentSummary([stat({ floor_rent: { '1': 0, x: 3 } })])).toBe(
      '공실률 · ㎡당 임대료 · 투자수익률 · 2026년 2분기 조사',
    );
  });
});

describe('isRentStatList — 서버 응답의 모양', () => {
  it('★ 선택 칸 둘이 이상한 모양이어도 목록을 거부하지 않는다 (그 값·그 표만 빠진다)', () => {
    expect(
      isRentStatList([
        stat({
          income_yield_rate: 'x' as unknown as number,
          floor_rent: 'broken' as unknown as Record<string, number>,
        }),
        stat({ floor_rent: TEHERAN_COLLECTIVE, income_yield_rate: 0.9 }),
      ]),
    ).toBe(true);
  });

  it('빈 배열은 정상이다 (조사 대상이 아닌 자리)', () => {
    expect(isRentStatList([])).toBe(true);
  });

  it('제대로 된 줄을 받아들인다 (값이 비어 있어도)', () => {
    expect(isRentStatList([stat(), stat({ vacancy_rate: null, district_nm: null })])).toBe(true);
  });

  it('★ 뜻밖의 답을 걸러 낸다 (렌더 도중에 터지면 층별 화면이 통째로 오류 안내가 된다)', () => {
    expect(isRentStatList({ code: 'PGRST202' })).toBe(false);
    expect(isRentStatList(null)).toBe(false);
    // 숫자 자리에 글자가 오면 화면에서 그대로 터진다.
    expect(isRentStatList([stat({ vacancy_rate: '10.08' as unknown as number })])).toBe(false);
    // 조사구역 이름이 없으면 어느 자리의 값인지 말할 수 없다.
    expect(isRentStatList([{ ...stat(), rone_region_nm: undefined }])).toBe(false);
  });
});

describe('lacksCoord — 좌표 없는 건물 (2026-10-06)', () => {
  it('lat 또는 lng 가 명시적 null 일 때만 참이다', () => {
    expect(lacksCoord({ lat: null, lng: null })).toBe(true);
    expect(lacksCoord({ lat: null, lng: 127 })).toBe(true);
    expect(lacksCoord({ lat: 37.5, lng: null })).toBe(true);
  });

  it('칸이 없으면(옛 서버 · undefined) 모르는 것이라 거짓이다', () => {
    expect(lacksCoord({})).toBe(false);
    expect(lacksCoord({ lat: undefined, lng: undefined })).toBe(false);
  });

  it('좌표가 있으면 거짓이다 (0 도 좌표다)', () => {
    expect(lacksCoord({ lat: 37.5, lng: 127.03 })).toBe(false);
    expect(lacksCoord({ lat: 0, lng: 0 })).toBe(false);
  });
});
