import { describe, it, expect } from 'vitest';
import type { BasePrice, FloorRow } from '../types';
import { pairBasePrices } from './basePrice';

/**
 * 국세청 기준시가 짝짓기 테스트.
 *
 * 여기서 지키는 것은 셋이다:
 *  ① 없는 사실을 지어내지 않는다 (0원·표본 없는 줄은 아예 안 그린다)
 *  ② 이 **건물**의 층만 그린다 (서버는 필지 전체를 준다 — 옆 동 층이 새면 안 된다)
 *  ③ 화면이 정한 순서(고층 → 지하)를 그대로 따른다
 */

function base(over: Partial<BasePrice> = {}): BasePrice {
  return {
    floor_no: 2,
    median_price_per_m2: 3_000_000,
    ho_cnt: 12,
    notice_date: '2026-01-01',
    ...over,
  };
}

function floor(floorNo: number, over: Partial<FloorRow> = {}): FloorRow {
  return {
    bld_id: '1168010100-1',
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

describe('pairBasePrices — 층 짝짓기', () => {
  it('화면이 그리는 순서(고층 → 지하) 그대로 돌려준다', () => {
    // 서버는 오름차순으로 준다 — 인덱스로 맞추면 층이 통째로 뒤집힌다.
    const rows = pairBasePrices(
      [base({ floor_no: -1 }), base({ floor_no: 2 })],
      [floor(2), floor(-1)],
    );
    expect(rows.map((r) => r.label)).toEqual(['2층', '지하 1층']);
  });

  it('이 건물에 없는 층(옆 동)은 그리지 않는다', () => {
    // 서버는 **필지** 전체를 준다. 한 땅에 여러 동이 서 있으면 옆 동 층이 함께 온다.
    const rows = pairBasePrices([base({ floor_no: 2 }), base({ floor_no: 7 })], [floor(2)]);
    expect(rows).toHaveLength(1);
    expect(rows[0].label).toBe('2층');
  });

  it('옥탑(99)·지하(음수)를 층 이름으로 적는다 — "99층"이 나오면 안 된다', () => {
    // 옥탑은 전국에 14행뿐이라(2026-08-27 적재 담당 실측) 눈으로는 거의 못 잡는다.
    // 층 표기 규칙을 여기서 새로 정하지 않고 화면 공용 자(formatFloor)를 그대로 쓴다.
    const rows = pairBasePrices(
      [base({ floor_no: 99 }), base({ floor_no: -2 })],
      [floor(99), floor(-2)],
    );
    expect(rows.map((r) => r.label)).toEqual(['옥탑', '지하 2층']);
    expect(rows.map((r) => r.label).join()).not.toContain('99층');
  });

  it('층 이름표가 있으면 그것을 쓴다 (대장에 적힌 그대로가 제일 정확하다)', () => {
    const rows = pairBasePrices([base({ floor_no: 2 })], [floor(2, { floor_label: '2층(중2층)' })]);
    expect(rows[0].label).toBe('2층(중2층)');
  });

  it('층이 안 적힌 묶음(floor_no null)은 조용히 버린다', () => {
    // 서버는 층이 안 적힌 호실도 한 묶음으로 준다(`group by n.floor_no`). 어느 층에도
    // 붙일 수 없으므로 그리지 않는다 — 억지로 어느 층에 얹으면 그게 곧 거짓말이다.
    const rows = pairBasePrices([base({ floor_no: null }), base({ floor_no: 2 })], [floor(2)]);
    expect(rows).toHaveLength(1);
    expect(rows[0].label).toBe('2층');
  });

  it('아직 안 왔거나 못 읽었으면(null) 빈 목록이다', () => {
    expect(pairBasePrices(null, [floor(2)])).toEqual([]);
  });
});

describe('pairBasePrices — 값으로 적으면 안 되는 줄', () => {
  it('⛔ 0원·음수·숫자 아님은 줄째로 버린다 (빈 0원을 적지 않는다)', () => {
    for (const v of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
      const rows = pairBasePrices([base({ median_price_per_m2: v })], [floor(2)]);
      expect(rows).toEqual([]);
    }
  });

  it('⛔ 몇 호를 세어 낸 값인지 모르면 값도 안 낸다 (값과 근거는 한 몸 — 절대 규칙 3)', () => {
    for (const n of [0, -1, Number.NaN]) {
      const rows = pairBasePrices([base({ ho_cnt: n })], [floor(2)]);
      expect(rows).toEqual([]);
    }
  });

  it('한 줄이 걸러져도 나머지 층은 그대로 그린다', () => {
    const rows = pairBasePrices(
      [base({ floor_no: 2, median_price_per_m2: 0 }), base({ floor_no: 3 })],
      [floor(3), floor(2)],
    );
    expect(rows.map((r) => r.label)).toEqual(['3층']);
  });
});
