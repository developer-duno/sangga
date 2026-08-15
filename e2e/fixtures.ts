import type {
  BuildingHit,
  CoverageStats,
  FloorRow,
  ParcelTransaction,
  SigunguTxStat,
} from '../src/types';

/**
 * E2E 픽스처 빌더.
 *
 * 필드셋은 단위 테스트(src/components/FloorStack.test.tsx의 floor()/stats(),
 * src/components/BuildingSearch.test.tsx의 hit())와 동일하게 맞췄다 — 여기서 새 응답
 * 모양을 발명하지 않는다.
 */

export function searchHit(over: Partial<BuildingHit> = {}): BuildingHit {
  return {
    bld_id: '1168010100-1',
    pnu: '1168010100100010000',
    bld_nm: '테스트빌딩',
    road_addr: '서울 강남구 테헤란로 1',
    bld_cnt_in_pnu: 1,
    floor_cnt: 2,
    min_floor: -1,
    max_floor: 1,
    has_roof: false,
    total_cnt: 1,
    ...over,
  };
}

export function floorRow(over: Partial<FloorRow> = {}): FloorRow {
  return {
    bld_id: '1168010100-1',
    pnu: '1168010100100010000',
    floor_no: 1,
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
    ...over,
  };
}

/** 이 땅에서 신고된 거래 하나(함수 list_parcel_transactions 한 행). */
export function parcelTx(over: Partial<ParcelTransaction> = {}): ParcelTransaction {
  return {
    floor_no: 1,
    contract_ym: '202605',
    contract_day: 12,
    bld_area_m2: 84.3,
    price_won: 320_000_000,
    unit_price: 3_800_000,
    tx_type: '집합',
    ...over,
  };
}

/**
 * 구 층대별 단가 5칸(함수 get_sigungu_tx_stats). 서버는 **표본이 0인 층대도** 준다 —
 * 칸이 빠지면 화면에서 그 층이 사라져 "아예 안 판다"처럼 읽힌다.
 */
export function sigunguTxStats(counts: Record<string, number> = { '1층': 213 }): SigunguTxStat[] {
  return ['지하', '1층', '2층', '3층이상', '층미상'].map((band) => {
    const n = counts[band] ?? 0;
    return {
      floor_band: band,
      n,
      median_unit_price: n > 0 ? 22_500_000 : null,
      p25_unit_price: n > 0 ? 13_800_000 : null,
      p75_unit_price: n > 0 ? 37_300_000 : null,
      window_from: '202408',
      sigungu_nm: '강남구',
    };
  });
}

export function coverageStats(over: Partial<CoverageStats> = {}): CoverageStats {
  return {
    snapshot_ym: '202603',
    store_cnt: 64239,
    floor_missing_cnt: 21124,
    floor_missing_pct: 32.9,
    ...over,
  };
}
