import { describe, it, expect } from 'vitest';
import type { BasePrice, FloorRow, RentStat, SigunguTxStat } from '../types';
import {
  FLOOR_GAP_FOOT,
  FLOOR_GAP_SUMMARY,
  GAP_NONE,
  floorGapHeads,
  floorGapRows,
  pickRentRow,
  rentKeysOf,
  txBandOf,
} from './floorGap';

/**
 * 「층 차이 세 잣대」 짝짓기(결정 0036 결정 15 · 물결 1-C2).
 *
 * 지키는 것: ① 세 자료를 **원래 값 그대로** 나른다(나누기·비율 0 — 값 글자를 정확히 단언하므로
 * 나누기가 하나라도 끼면 여기서 빨강) ② 층 → 층대·층 구간 열쇠 ③ 빠진 자료는 그 칸만 '–'.
 */

function floor(floorNo: number, over: Partial<FloorRow> = {}): FloorRow {
  return {
    bld_id: '1168010100100010000_1',
    pnu: '1168010100100010000',
    floor_no: floorNo,
    floor_label: null,
    floor_area_m2: 300,
    floor_area_gross_m2: 340,
    segment_cnt: 1,
    main_use: '소매점',
    uses: [],
    bld_nm: '테스트빌딩',
    approve_date: '2003-05-14',
    is_jiphap: true,
    road_addr: '서울 강남구 테헤란로 1',
    road_contact: null,
    bld_cnt_in_pnu: 1,
    store_cnt: 2,
    stores: [],
    total_area_m2: 1234.5,
    far: 350.5,
    bcr: 59.9,
    parking_cnt: 12,
    ...over,
  };
}

function base(floorNo: number, won: number, ho = 12): BasePrice {
  return { floor_no: floorNo, median_price_per_m2: won, ho_cnt: ho, notice_date: '2026-01-01' };
}

function tx(band: string, n: number, median: number | null = 3_800_000): SigunguTxStat {
  return {
    floor_band: band,
    n,
    median_unit_price: median,
    p25_unit_price: null,
    p75_unit_price: null,
    window_from: '202410',
    sigungu_nm: '강남구',
  };
}

function rent(over: Partial<RentStat> = {}): RentStat {
  return {
    district_nm: '역삼역',
    rone_region_nm: '서울>강남>테헤란로',
    bld_type: '집합상가',
    quarter: '2026Q2',
    vacancy_rate: 3.5,
    rent_per_m2: 74.6,
    yield_rate: 0.82,
    floor_rent: { '11+': 30.1, '6-10': 33.2, '5': 40, '2': 50.5, '1': 74.6, '-1': 28 },
    ...over,
  } as RentStat;
}

const FLOORS = [floor(99), floor(12), floor(7), floor(2), floor(1), floor(-1), floor(-2)];
const TX = [tx('지하', 0, null), tx('1층', 213), tx('2층', 4), tx('3층이상', 57, 2_100_000), tx('층미상', 9)];

describe('txBandOf · rentKeysOf — 층을 각 자료의 묶음으로', () => {
  it('구 실거래 층대 — 옥탑(99)은 3층이상(Stage A 정의) · 지하는 지하', () => {
    expect([-2, -1, 1, 2, 3, 12, 99].map(txBandOf)).toEqual([
      '지하', '지하', '1층', '2층', '3층이상', '3층이상', '3층이상',
    ]);
  });

  it('부동산원 열쇠 — 6~10층은 6-10(없으면 6+) · 11층 이상은 11+(없으면 6+) · 옥탑·지하 2층 이하는 없음', () => {
    expect(rentKeysOf(-1)).toEqual(['-1']);
    expect(rentKeysOf(-2)).toEqual([]);
    expect(rentKeysOf(99)).toEqual([]);
    expect(rentKeysOf(3)).toEqual(['3']);
    expect(rentKeysOf(8)).toEqual(['6-10', '6+']);
    expect(rentKeysOf(15)).toEqual(['11+', '6+']);
  });
});

describe('floorGapRows — 층마다 세 칸', () => {
  it('층 목록 차례 그대로 · 세 값은 공표값 그대로(나누기 0)', () => {
    const rows = floorGapRows(
      FLOORS,
      [base(2, 3_812_000, 7), base(1, 5_000_000), base(-1, 1_200_000, 3)],
      TX,
      [rent()],
    );
    expect(rows.map((r) => r.label)).toEqual(['옥탑', '12층', '7층', '2층', '1층', '지하 1층', '지하 2층']);

    const one = rows.find((r) => r.floorNo === 1)!;
    expect(one.base).toEqual({ value: '500만', sub: '호 12개 가운데값' });
    expect(one.tx).toEqual({ value: '380만', sub: '1층 · 213건' });
    expect(one.rent).toEqual({ value: '74.6', sub: '1층' });

    // 2층 — 구 실거래 표본 4건이라 값 대신 표본 부족(기존 실거래 카드와 같은 상수 5).
    const two = rows.find((r) => r.floorNo === 2)!;
    expect(two.base.value).toBe('381만');
    expect(two.tx).toEqual({ value: '표본 부족 (4건)', sub: null });
    expect(two.rent).toEqual({ value: '50.5', sub: '2층' });

    // 7층 — 6-10 열쇠 · 12층 — 11+ 열쇠 · 둘 다 3층이상 층대.
    expect(rows.find((r) => r.floorNo === 7)!.rent).toEqual({ value: '33.2', sub: '6~10층' });
    expect(rows.find((r) => r.floorNo === 12)!.rent).toEqual({ value: '30.1', sub: '11층 이상' });
    expect(rows.find((r) => r.floorNo === 12)!.tx.value).toBe('210만');

    // 옥탑 — 실거래는 3층이상 층대 · 부동산원은 구간이 없어 '–'.
    const roof = rows.find((r) => r.floorNo === 99)!;
    expect(roof.tx.value).toBe('210만');
    expect(roof.rent.value).toBe(GAP_NONE);

    // 지하 2층 — 부동산원 구간 없음 · 기준시가 없음 · 실거래 지하 0건 → 표본 부족.
    const b2 = rows.find((r) => r.floorNo === -2)!;
    expect(b2.base.value).toBe(GAP_NONE);
    expect(b2.rent.value).toBe(GAP_NONE);
    expect(b2.tx.value).toBe('표본 부족 (0건)');
  });

  it('6-10 열쇠가 없는 상가 조사면 6+ 로', () => {
    const rows = floorGapRows([floor(8), floor(15)], null, null, [rent({ floor_rent: { '6+': 41, '1': 70 } })]);
    expect(rows.map((r) => r.rent)).toEqual([
      { value: '41', sub: '6층 이상' },
      { value: '41', sub: '6층 이상' },
    ]);
  });

  it('자료가 null(못 받음)이면 그 칸만 전부 –', () => {
    const rows = floorGapRows([floor(1)], null, null, null);
    expect(rows[0].base.value).toBe(GAP_NONE);
    expect(rows[0].tx.value).toBe(GAP_NONE);
    expect(rows[0].rent.value).toBe(GAP_NONE);
  });

  it('부동산원은 임대 카드의 기본 종류 · 서버 차례 첫 조사구역 하나만 쓴다(종류를 섞지 않는다)', () => {
    const rows = [
      rent({ bld_type: '오피스', rone_region_nm: '오피스구역', floor_rent: { '1': 99 } }),
      rent({ rone_region_nm: '첫 집합구역', floor_rent: { '1': 70 } }),
      rent({ rone_region_nm: '둘째 집합구역', floor_rent: { '1': 80 } }),
    ];
    expect(pickRentRow(rows)?.rone_region_nm).toBe('첫 집합구역');
    expect(floorGapRows([floor(1)], null, null, rows)[0].rent.value).toBe('70');
  });
});

describe('floorGapHeads — 칸 머리(서버 값으로만)', () => {
  it('구 이름 · 창 시작 달 · 조사구역 · 종류 · 분기', () => {
    const h = floorGapHeads(TX, [rent()], false);
    expect(h.base).toBe('국세청 기준시가 · 원/㎡ · 이 건물');
    expect(h.tx).toBe('구 실거래 단가 · 강남구 · 2024-10부터');
    expect(h.rent).toBe(
      '부동산원 임대료(월) · 천원/㎡ · 서울>강남>테헤란로 집합상가 평균 — 이 건물 값 아님 (2026년 2분기 조사)',
    );
  });

  it('조사 대상 아님·좌표 없음이면 임대 카드와 같은 글', () => {
    expect(floorGapHeads(null, [], false).rent).toBe('부동산원 임대료(월) · 천원/㎡ · 부동산원 조사 대상 상권이 아닙니다');
    expect(floorGapHeads(null, [], true).rent).toBe(
      '부동산원 임대료(월) · 천원/㎡ · 위치 정보가 없어 속한 상권을 찾지 못했습니다',
    );
  });
});

/**
 * ⛔ 비율 금지 가드(결정 15 · 0031) — 탐지는 이 작은 함수 하나로, 가드 본체와 양성 대조가 같은 함수를 지난다.
 * 못 보는 것: 글자로 풀어 쓴 '몇 배'·'반값' 같은 말(값 글자 단언이 대신 지킨다).
 */
function hasPercent(text: string): boolean {
  return /[%％]|퍼센트/.test(text);
}

describe('⛔ 비율 표기 0 — % 가 안 나온다', () => {
  it('양성 대조 — 탐지 함수가 흔한 꼴과 변형 꼴을 실제로 잡는다', () => {
    expect(hasPercent('2층은 1층의 68%')).toBe(true);
    expect(hasPercent('2층은 1층의 68％')).toBe(true);
    expect(hasPercent('68 퍼센트')).toBe(true);
    expect(hasPercent('380만 (1층 · 213건)')).toBe(false);
  });

  it('요약·발·머리·칸 글 어디에도 % 가 없다', () => {
    const rows = floorGapRows(FLOORS, [base(1, 5_000_000)], TX, [rent()]);
    const h = floorGapHeads(TX, [rent()], false);
    const all = [
      FLOOR_GAP_SUMMARY,
      FLOOR_GAP_FOOT,
      h.base,
      h.tx,
      h.rent,
      ...rows.flatMap((r) => [r.base, r.tx, r.rent].flatMap((c) => [c.value, c.sub ?? ''])),
    ].join('\n');
    expect(hasPercent(all)).toBe(false);
  });

  it('접힌 요약에는 값(숫자)이 없다', () => {
    expect(/[0-9]/.test(FLOOR_GAP_SUMMARY)).toBe(false);
  });
});
