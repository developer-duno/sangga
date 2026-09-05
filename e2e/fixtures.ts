import type {
  BasePrice,
  BuildingHit,
  CoverageStats,
  FloorRow,
  IndustryMix,
  LhNotice,
  NearbyPermits,
  ParcelTransaction,
  PriceBand,
  RentStat,
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
    bld_id: '1168010100100010000_1024110',
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
    bld_id: '1168010100100010000_1024110',
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
 * 국세청 기준시가 한 줄(함수 list_base_prices).
 *
 * ⛔ **시세가 아니라 세무 기준가격**이다 — 위 `priceBand`(추정)와 다른 자로 잰 다른 값이라
 *    화면에서도 카드 맨 끝에 갈라 그린다. 필드·기본값은 단위 테스트
 *    (src/components/FloorStack.test.tsx 의 basePrice())와 같다.
 */
export function basePrice(over: Partial<BasePrice> = {}): BasePrice {
  return {
    floor_no: 2,
    median_price_per_m2: 3_000_000,
    ho_cnt: 12,
    notice_date: '2026-01-01',
    ...over,
  };
}

/** 이 필지의 층별 기준시가 한 벌. 서버는 **필지 전체**를 오름차순으로 준다. */
export function basePrices(): BasePrice[] {
  return [basePrice({ floor_no: 1, median_price_per_m2: 4_100_000 }), basePrice({ floor_no: 2 })];
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

/**
 * 둘레에 새로 올라오는 상가 건물(함수 count_nearby_permits) — 업종 분포 카드 안의 한 줄.
 *
 * ⚠️ **한 행짜리 목록**으로 흉내 낸다. 서버 함수가 `returns table` 이면 PostgREST 가 이렇게
 *    싸서 주고, 그 껍데기 차이는 라이브에서만 드러나는 종류다(목은 우리가 적어 준 모양을
 *    그대로 돌려주므로 어느 쪽으로 틀려도 조용하다). 화면이 둘 다 받는지는 단위 시험
 *    (src/lib/nearbyPermits.test.ts)이 함께 본다.
 * ⓘ 3동 중 2동 착공 = 허가만 1동. 셋이 서로 맞물려 있어 산수가 틀리면 바로 드러난다.
 */
export function nearbyPermits(over: Partial<NearbyPermits> = {}): NearbyPermits[] {
  return [{ total_cnt: 3, started_cnt: 2, base_ym: '202607', ...over }];
}

/**
 * LH 상가 분양·입점 공고 한 줄(함수 list_lh_notices). 입구 카드에만 쓴다.
 *
 * ⚠️ `collected_at` 은 **현지 시각으로 지어** 쓴다 — 돌리는 시간대·날짜에 따라 요약 줄의
 *    "M월 D일 수집 기준"이 달라지면 시험이 어느 날 갑자기 빨개진다(글로벌 규칙: 시험에
 *    시각을 박아 넣지 않는다). 필드셋은 단위 테스트(src/components/LhNoticeSection.test.tsx
 *    의 notice())와 같다 — 여기서 새 응답 모양을 발명하지 않는다.
 */
export function lhNotice(over: Partial<LhNotice> = {}): LhNotice {
  return {
    pan_id: '2026-0001',
    pan_nm: '서울강남 A1블록 단지내상가 입찰공고',
    kind_nm: '분양 입찰',
    pan_ss: '공고중',
    notice_date: '2026-08-20',
    // ⚠️ 마감일도 **올해 기준 상대값**이다 — 스펙 W 가 '~9월 17일'을 단언하는데, 마감이
    //    올해가 아니면 화면이 연도를 함께 적으므로 연도를 박아 두면 해가 바뀌는 순간
    //    코드는 그대로인데 시험만 빨개진다.
    close_date: `${new Date().getFullYear()}-09-17`,
    dtl_url: 'https://apply.lh.or.kr/notice/2026-0001',
    collected_at: new Date(2026, 7, 27, 9, 0).toISOString(),
    // 2026-09-05c 로 늘어난 두 칸(결정 0026). 기본은 **그 지역 공고 · 재게시 없음** —
    // 접힘 묶음·꼬리표를 보려는 시험만 이 값을 덮어쓴다.
    is_nationwide: false,
    dup_cnt: 0,
    ...over,
  };
}

/**
 * 상권 임대 동향 한 줄(함수 `list_rent_stats`). 결정 0024.
 *
 * ⛔ **조사값이지 추정이 아니다** — 위 `priceBand`(우리가 어림한 것)와 다른 자로 잰 다른
 *    값이라 화면에서도 카드를 갈라 그린다. 필드·기본값은 단위 테스트
 *    (src/components/RentStatSection.test.tsx 의 stat())와 같다.
 * ⚠️ `rent_per_m2` 는 **천원/㎡**(부동산원 공표 단위 그대로)다 — 27.06 이 화면에서
 *    '27,060원'이 되는지가 스펙 Z 의 관심사다.
 */
export function rentStat(over: Partial<RentStat> = {}): RentStat {
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

/** 한 상권에 종류 둘 — 고르개가 실제로 갈아 끼우는지 보려면 둘이라야 한다. */
export function rentStats(): RentStat[] {
  return [
    rentStat(),
    rentStat({ bld_type: '오피스', vacancy_rate: 5.5, rent_per_m2: 18.4, yield_rate: 1.1 }),
  ];
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
