import type {
  BuildingHit,
  CoverageStats,
  FloorRow,
  IndustryMix,
  ParcelTransaction,
  PriceBand,
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
    // 건물 스펙 4칸(2026-08-24a). 기본값은 **넷 다 값이 있는** 정상 건물이다 —
    // 0(=대장 미기재)·상한 초과는 그것을 보려는 시험에서만 덮어쓴다.
    total_area_m2: 1234.5,
    far: 350.5,
    bcr: 59.9,
    parking_cnt: 12,
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

/**
 * 층별 참고 매매 시세 한 줄(함수 list_price_bands). Stage B — 결정 0013.
 * 필드·기본값은 단위 테스트(src/components/FloorStack.test.tsx 의 priceBand())와 같다.
 */
export function priceBand(over: Partial<PriceBand> = {}): PriceBand {
  return {
    floor_no: 2,
    status: 'ok',
    stage: 'L5',
    n: 15,
    p25: 7_465_269.63,
    median: 16_265_452.18,
    p75: 19_045_698.84,
    median_area_m2: 32.8,
    window_from: '202408',
    ...over,
  };
}

/** 값을 못 내는 줄은 사분위·근거가 전부 비어서 온다. */
const NO_VALUE = {
  stage: null,
  n: null,
  p25: null,
  median: null,
  p75: null,
  median_area_m2: null,
} as const;

/**
 * 서버가 주는 한 벌 — **오름차순**이다(화면이 뒤집는지 보려면 이 순서 그대로 줘야 한다).
 * 지하1층 no_evidence · 1층 floor_1f · 2층 ok.
 */
export function priceBands(): PriceBand[] {
  return [
    priceBand({ floor_no: -1, status: 'no_evidence', ...NO_VALUE }),
    priceBand({ floor_no: 1, status: 'floor_1f', ...NO_VALUE }),
    priceBand({ floor_no: 2 }),
  ];
}

/** 기준선을 못 넘은 구 — floor_no 가 null 인 **한 줄**로만 온다(층 목록이 아예 없다). */
export function priceBandGate(): PriceBand[] {
  return [priceBand({ floor_no: null, status: 'gate_fail', ...NO_VALUE })];
}

/**
 * 둘레의 업종 분포(함수 list_industry_mix). 결정 0014.
 *
 * 필드·기본값은 단위 테스트(src/components/IndustryMixSection.test.tsx 의 mix())와 같다 —
 * 여기서 새 응답 모양을 발명하지 않는다. 스코프는 **속한 상권 묶음들 + 반경 하나**이고,
 * 기준 분기·반경 길이가 함께 온다(화면이 '500m'·'2026년 2분기'를 글자로 박지 않으므로).
 */
export function industryMix(over: Partial<IndustryMix> = {}): IndustryMix {
  return {
    snapshot_ym: '202606',
    radius_m: 500,
    districts: [
      {
        district_id: '3120189',
        name: '강남역',
        type: '발달상권',
        source_nm: '서울특별시 상권분석서비스',
        total: 100,
        cats: [
          { cd: 'I2', nm: '음식', n: 60 },
          { cd: 'G2', nm: '소매', n: 40 },
        ],
      },
    ],
    radius: {
      total: 200,
      cats: [
        { cd: 'I2', nm: '음식', n: 150 },
        { cd: 'G2', nm: '소매', n: 50 },
      ],
    },
    ...over,
  };
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
