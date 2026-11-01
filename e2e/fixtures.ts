import type {
  BasePrice,
  BuildingHit,
  CoverageStats,
  DataFreshnessRow,
  DaejeonDongClosure,
  DistrictCensusPop,
  DistrictPop,
  DistrictSales,
  DistrictOpenClose,
  FloorRow,
  FloorUnit,
  IndustryDetail,
  IndustryFloors,
  IndustryMedian,
  IndustryMedianM,
  IndustryMix,
  LhNotice,
  NearbyPermits,
  NearbySubway,
  ParcelTransaction,
  RentStat,
  SigunguTxStat,
  StoreHistoryRow,
  StoreHit,
  UnitFloorSummary,
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
    // 지분 거래 여부(2026-10-08a) — 서버가 실제로 보내는 boolean. 기본은 일반 거래.
    is_share: false,
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
 * 국세청 기준시가 한 줄(함수 list_base_prices).
 *
 * ⛔ **시세가 아니라 세무 기준가격**이다 — 『층별 공표값 나란히』 카드의 기준시가 칸에 들어간다(결정 0041).
 *    필드·기본값은 단위 테스트
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
 * 업종별 층 분포(함수 list_industry_floors · 물결 2-2). 숫자는 단위 시험
 * (src/components/IndustryMixSection.test.tsx 의 floors())과 같다 — `catM` 이 null 이면 대분류 전체,
 * 배열이면 칩 짝 중분류의 답(서버는 물어본 값을 그대로 되돌려 준다).
 * ⚠️ 대분류 답의 bands 합 = 그 블록의 업종 총수(상권 `음식 60곳` · 반경 `150곳`) — 서버에서는 같은
 *    (상권·중분류)의 층 묶음 합이 업종 표와 같다(post_load --check 가 대조). 어긋난 픽스처는 화면에
 *    '음식 60곳' 아래 층 합 1,234 처럼 서로 다른 말을 세운다.
 */
export function industryFloors(catL = 'I2', catM: string[] | null = null): IndustryFloors {
  if (catM === null) {
    return {
      snapshot_ym: '202606',
      radius_m: 500,
      cat_l_cd: catL,
      cat_m_cds: null,
      districts: [
        { district_id: '3120189', name: '강남역', total: 60, bands: { b: 0, '1': 36, '2': 9, '3+': 3, na: 12 } },
      ],
      radius: { total: 150, bands: { b: 2, '1': 90, '2': 24, '3+': 9, na: 25 } },
    };
  }
  return {
    snapshot_ym: '202606',
    radius_m: 500,
    cat_l_cd: catL,
    cat_m_cds: catM,
    districts: [{ district_id: '3120189', name: '강남역', total: 20, bands: { b: 0, '1': 15, '2': 3, '3+': 0, na: 2 } }],
    radius: { total: 0, bands: { b: 0, '1': 0, '2': 0, '3+': 0, na: 0 } },
  };
}

/**
 * 업종 비중 비교(함수 list_industry_median · 물결 2-3). 상권 둘 — 골목상권(점포 215곳 · 같은 종류 999곳 모집단)과
 * 전통시장(점포 12곳 — 30곳 미만이라 pop null · cats []). 숫자는 2026-10-12 운영 실측 가운데값(서울 골목 음식 25.0 ·
 * 소매 19.3)에서 땄다. 상권 열쇠는 아래 `industryMixTwoDistricts()` 와 같아야 한다(화면이 열쇠로 짝짓는다).
 */
export function industryMedian(over: Partial<IndustryMedian> = {}): IndustryMedian {
  return {
    snapshot_ym: '202606',
    min_total: 30,
    min_pop: 30,
    districts: [
      {
        district_id: '3110001',
        type: '골목상권',
        total: 215,
        pop: { scope: 'type', sido_cd: '11', district_type: '골목상권', n: 999 },
        cats: [
          { cd: 'I2', nm: '음식', med_pct: 25.0 },
          { cd: 'G2', nm: '소매', med_pct: 19.3 },
        ],
      },
      { district_id: '3130001', type: '전통시장', total: 12, pop: null, cats: [] },
    ],
    ...over,
  };
}

/**
 * 업종 상세(함수 list_industry_detail) — 음식(I2)을 고른 뒤의 상세 블록 셋. 상권 열쇠는 `industryMixTwoDistricts()` 와 같다.
 * 골목 음식 120곳(카페 = 비알코올 26곳 → 막대 21.7% · 👤 ㉘ 예시) · 전통시장 음식 7곳 · 반경 음식 150곳. 총수 = cats 합.
 */
export function industryDetailTwoDistricts(): IndustryDetail {
  return {
    snapshot_ym: '202606',
    radius_m: 500,
    cat_l_cd: 'I2',
    districts: [
      {
        district_id: '3110001',
        name: '역삼골목',
        total: 120,
        cats: [
          { cd: 'I201', nm: '한식', n: 46 },
          { cd: 'I212', nm: '비알코올', n: 26 },
          { cd: 'I210', nm: '기타 간이', n: 24 },
          { cd: 'I211', nm: '주점', n: 24 },
        ],
      },
      { district_id: '3130001', name: '역삼시장', total: 7, cats: [{ cd: 'I201', nm: '한식', n: 7 }] },
    ],
    radius: {
      total: 150,
      cats: [
        { cd: 'I201', nm: '한식', n: 100 },
        { cd: 'I212', nm: '비알코올', n: 50 },
      ],
    },
  };
}

/**
 * 업종 비중 비교 · 중분류(함수 list_industry_median_m · 물결 2-3b) — 위 상세와 짝. 골목(음식 120곳 · 같은 종류 음식 30곳
 * 이상 526곳 모집단)과 전통시장(음식 7곳 — 30곳 미만이라 pop null · cats []). 숫자는 2026-10-13 운영 실측 서울 골목 음식 안
 * 가운데값(한식 38.1 · 기타 간이 20.6 · 비알코올 15.2 · 주점 9.8 · 동남아시아 0.0)에서 땄다 — 동남아시아는 상세에 없는
 * 중분류라 화면에 줄이 없다(가운데값만 있고 막대가 없는 줄은 그리지 않는다).
 */
export function industryMedianM(over: Partial<IndustryMedianM> = {}): IndustryMedianM {
  return {
    snapshot_ym: '202606',
    cat_l_cd: 'I2',
    min_total: 30,
    min_pop: 30,
    districts: [
      {
        district_id: '3110001',
        type: '골목상권',
        total: 120,
        pop: { scope: 'type', sido_cd: '11', district_type: '골목상권', n: 526 },
        cats: [
          { cd: 'I201', nm: '한식', med_pct: 38.1 },
          { cd: 'I210', nm: '기타 간이', med_pct: 20.6 },
          { cd: 'I212', nm: '비알코올', med_pct: 15.2 },
          { cd: 'I211', nm: '주점', med_pct: 9.8 },
          { cd: 'I205', nm: '동남아시아', med_pct: 0.0 },
        ],
      },
      { district_id: '3130001', type: '전통시장', total: 7, pop: null, cats: [] },
    ],
    ...over,
  };
}

/** 업종 분포(대분류) — 위 `industryMedian()` 과 짝인 상권 둘 + 반경. 총수는 cats 합과 같다. */
export function industryMixTwoDistricts(): IndustryMix {
  return industryMix({
    districts: [
      {
        district_id: '3110001',
        name: '역삼골목',
        type: '골목상권',
        source_nm: '서울특별시 상권분석서비스',
        total: 215,
        cats: [
          { cd: 'I2', nm: '음식', n: 120 },
          { cd: 'G2', nm: '소매', n: 95 },
        ],
      },
      {
        district_id: '3130001',
        name: '역삼시장',
        type: '전통시장',
        source_nm: '서울특별시 상권분석서비스',
        total: 12,
        cats: [
          { cd: 'I2', nm: '음식', n: 7 },
          { cd: 'G2', nm: '소매', n: 5 },
        ],
      },
    ],
  });
}

/**
 * 둘레에 새로 올라오는 상가 건물(함수 count_nearby_permits) — 업종 분포 카드 안의 한 줄.
 *
 * ⚠️ **한 행짜리 목록**으로 흉내 낸다. 서버 함수가 `returns table` 이면 PostgREST 가 이렇게
 *    싸서 주고, 그 껍데기 차이는 라이브에서만 드러나는 종류다(목은 우리가 적어 준 모양을
 *    그대로 돌려주므로 어느 쪽으로 틀려도 조용하다). 화면이 둘 다 받는지는 단위 시험
 *    (src/lib/nearbyPermits.test.ts)이 함께 본다.
 * ⓘ 3동 중 2동 착공 = 허가만 1동. 셋이 서로 맞물려 있어 산수가 틀리면 바로 드러난다.
 * ⓘ `stale_cnt` 는 **허가만(1동) 안에 들어 있는** 수라 1을 넘을 수 없다(2026-09-05b).
 *    0 으로 두면 그 문장이 아예 안 그려져 E2E 가 볼 것이 없어진다 — 그래서 1이다.
 */
export function nearbyPermits(over: Partial<NearbyPermits> = {}): NearbyPermits[] {
  return [{ total_cnt: 3, started_cnt: 2, stale_cnt: 1, base_ym: '202607', ...over }];
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
 * ⛔ **조사값이지 추정이 아니다** — 이 건물 값(기준시가)과 다른 자로 잰 다른
 *    값이라 화면에서도 카드를 갈라 그린다. 필드·기본값은 단위 테스트
 *    (src/components/RentStatSection.test.tsx 의 stat())와 같다.
 * ⚠️ `rent_per_m2` 는 **천원/㎡**(부동산원 공표 단위 그대로)다 — 74.6 이 화면에서
 *    '74,600원'이 되는지가 스펙 Z 의 관심사다.
 */
export function rentStat(over: Partial<RentStat> = {}): RentStat {
  return {
    district_nm: '역삼역',
    rone_region_nm: '서울>강남>테헤란로',
    bld_type: '집합상가',
    quarter: '2026Q2',
    vacancy_rate: 10.08,
    rent_per_m2: 74.6,
    yield_rate: 0.82,
    // 결정 0031 로 늘어난 두 칸(2026-10-04a) — 값은 같은 날 라이브 실호출(테헤란로 집합상가 ·
    // 2026Q2 · 천원/㎡). ⚠️ 둘 다 **선택 칸**이라, 옛 함수의 답을 흉내 내려면 `rentStatOld()` 를 쓴다.
    income_yield_rate: 0.9,
    floor_rent: { '1': 74.6, '2': 32.48, '3': 23.54, '4': 23.73, '5': 25.0, '-1': 16.95, '6+': 22.7 },
    ...over,
  };
}

/**
 * 새 두 칸(`income_yield_rate`·`floor_rent`)이 **아예 없는** 한 줄 — 2026-10-04a 이전 함수의 답.
 * 그 답에서도 카드가 서는지(선택 칸이 빠졌다고 카드가 사라지지 않는지) 보는 스펙 전용이다.
 */
export function rentStatOld(): RentStat {
  const old: RentStat = { ...rentStat() };
  delete old.income_yield_rate;
  delete old.floor_rent;
  return old;
}

/** 한 상권에 종류 둘 — 고르개가 실제로 갈아 끼우는지 보려면 둘이라야 한다. */
export function rentStats(): RentStat[] {
  return [
    rentStat(),
    rentStat({
      bld_type: '오피스',
      vacancy_rate: 5.5,
      rent_per_m2: 18.4,
      yield_rate: 1.1,
      // 오피스는 위 구간이 6~10층 · 11층 이상으로 나뉜다(같은 날 라이브 실호출 값).
      income_yield_rate: 0.84,
      floor_rent: {
        '1': 38.99,
        '2': 31.4,
        '3': 27.09,
        '4': 26.6,
        '5': 26.51,
        '-1': 13.93,
        '11+': 28.62,
        '6-10': 26.73,
      },
    }),
  ];
}

/**
 * 화면 아래 신선도 표. 라이브와 같은 **열 줄**을 준다(2026-09-05d · 2026-10-16 운영 모양 — 결정 0041 로 성적표 줄을 뺐다 — 실거래·건축물대장은
 * 2026-10-15a 부터 규칙으로 날짜를 주고 건축물대장 기준 종류는 '판' · 서울시 개업·폐업 줄은 결정 0033).
 * ⓘ 카드 머리 날짜 줄(S3)도 이 표에서 읽는다 — 기준값은 2026-10-16 운영 값 그대로라 시안 글자와 같다.
 *
 * ⚠️ 값을 손으로 계산해 적지 않는다 — 여기 적힌 `next_expected` 는 서버가 규칙으로 계산해
 *    주는 값을 흉내 낸 것이고, 규칙이 맞는지는 파이썬 가드와 라이브가 본다. 여기서는
 *    "서버가 준 값이 화면에 그대로 실리는가"만 본다.
 *
 * ⛔ **예정일은 먼 미래(2099년)와 확실한 과거(2026-08-31)만 쓴다.** 화면이 실제 오늘과 견줘
 *    지난 예정일에 "지났습니다, 갱신 전"을 붙이므로(2026-10-01), 가까운 날짜를 두면 날이
 *    흐르는 것만으로 E2E 결과가 바뀐다. 라이브 값과 달라 보여도 일부러 그렇다.
 */
export function dataFreshness(): DataFreshnessRow[] {
  return [
    {
      src: '점포·업종 (상권정보)',
      basis_kind: '분기',
      basis: '202606',
      next_expected: '2099-12-31',
      cadence: '분기마다 (다음 분기 자료가 공개되면 사람이 적재)',
    },
    {
      src: '실거래 (매매)',
      basis_kind: '계약월',
      basis: '202610',
      next_expected: '2099-11-30',
      cadence: '월 1회 (최근 6개월 다시 받기)',
    },
    {
      src: '건축물대장',
      basis_kind: '판',
      basis: '202608',
      next_expected: '2099-10-31',
      cadence: '월간 파일 (사람이 적재)',
    },
    {
      src: '상권 경계',
      basis_kind: '계산일',
      basis: '2026-09-08',
      next_expected: null,
      cadence: '비정기 (원천이 바뀌면)',
    },
    {
      src: 'LH 상가 공고',
      basis_kind: '수집일',
      basis: '2026-10-12',
      next_expected: null,
      cadence: '주 1회 감시 · 적재는 사람',
    },
    {
      // ⓘ 이 줄만 일부러 확실한 과거 예정일이다('지났습니다, 갱신 전' 을 보려고 — 운영 값은 202608 · 2026-10-31).
      src: '건축 인허가',
      basis_kind: '기준월',
      basis: '202608',
      next_expected: '2026-08-31',
      cadence: '월 1회',
    },
    {
      src: '국세청 기준시가',
      basis_kind: '고시일',
      basis: '2026-01-01',
      next_expected: '2099-03-31',
      cadence: '연 1회 (매년 3월 고시)',
    },
    {
      src: '상권 임대 동향 (부동산원)',
      basis_kind: '분기',
      basis: '2026Q2',
      next_expected: '2099-12-31',
      cadence: '분기마다',
    },
    {
      // 자료가 아직 한 행도 없는 갈래도 **줄은 나온다**(화면이 '자료 없음'이라 적는다).
      // 2026-10-12b 서버 모양 — 기준 종류 '공시 연도'. 자료가 0행이면 basis 가 null 이고, 서버 규칙은
      // 네 자리 연도일 때만 날짜를 내므로 next_expected 도 null 이다(값이 있으면 '2026' · '2027-06-30').
      src: '필지 (토지 특성)',
      basis_kind: '공시 연도',
      basis: null,
      next_expected: null,
      cadence: '연 1회 (브이월드)',
    },
    {
      // 결정 0033 — 서울시 분기 꼴은 Q 없는 다섯 자리('20262').
      src: '상권 개업·폐업 (서울시)',
      basis_kind: '분기',
      basis: '20262',
      next_expected: '2099-12-31',
      cadence: '분기마다',
    },
    {
      // 결정 0045 PR④ — 가게 이력(16번 줄 · 점포 줄과 같은 분기 · 보완 1 F-9 — 이력 카드 날짜 줄이 서게).
      src: '가게 이력 (점포 자료 누적)',
      basis_kind: '분기',
      basis: '202606',
      next_expected: '2099-12-31',
      cadence: '분기마다 (새 분기 점포 자료를 적재한 뒤 다시 굽는다)',
    },
  ];
}

/**
 * 가게 이름으로 찾은 **땅** 한 줄(결정 0028).
 *
 * ⛔ 건물이 아니라 땅이다 — 앞 12칸은 `searchHit()` 과 같은 모양이라 그대로 층별 화면으로
 *    넘어가지만, `match_store_cnt` 는 "이 **땅**의 가게"라 층별 화면의 점포 칸과 세는 대상이
 *    다르다.
 */
export function storeHit(over: Partial<StoreHit> = {}): StoreHit {
  return {
    pnu: '1168010100100010000',
    bld_id: '1168010100100010000_1024110',
    bld_nm: '테스트빌딩',
    road_addr: '서울 강남구 테헤란로 1',
    jibun_addr: '서울 강남구 역삼동 823-4',
    lat: 37.5,
    lng: 127.03,
    bld_cnt_in_pnu: 1,
    floor_cnt: 2,
    min_floor: -1,
    max_floor: 1,
    has_roof: false,
    matched_names: ['스타벅스역삼점', '스타벅스테헤란점'],
    match_store_cnt: 5,
    total_parcel_cnt: 1,
    total_store_cnt: 5,
    too_broad: false,
    store_snapshot_ym: '202606',
    ...over,
  };
}

/**
 * 호실 구성표 요약(함수 `list_unit_floor_summary`) — 결정 0032.
 *
 * 값은 2026-10-04 라이브 실호출(신구로자이 나인스에비뉴)에서 골랐다 — 3층 섞인 층 543칸 ·
 * 1층 목록 제공 층 690칸 · 35층 주거 10세대(면적 셋 null). 서버처럼 **높은 층이 위**다.
 * ⛔ 주거 층 면적은 null 이다(서버가 막는다) — 여기에 값을 넣으면 라이브에 없는 모양을 흉내 낸다.
 */
export function unitSummary(): UnitFloorSummary[] {
  return [
    { floor_no: 35, unit_cnt: 10, median_area_m2: null, min_area_m2: null, max_area_m2: null, floor_kind: 'residential' },
    { floor_no: 3, unit_cnt: 543, median_area_m2: 4.0, min_area_m2: 2.74, max_area_m2: 8.81, floor_kind: 'mixed' },
    { floor_no: 1, unit_cnt: 690, median_area_m2: 4.0, min_area_m2: 3.18, max_area_m2: 13.07, floor_kind: 'commercial' },
  ];
}

/**
 * 한 층의 호 목록 한 쪽(함수 `list_floor_units`). 이름은 라이브 꼴('3가001호')을 따라 짓고,
 * `total_cnt` 는 쪽과 무관하게 그 층 전체 수가 모든 줄에 같은 값으로 온다(서버와 같다).
 */
export function floorUnitsPage(offset: number, limit: number, total = 543): FloorUnit[] {
  const rows: FloorUnit[] = [];
  for (let i = offset; i < Math.min(offset + limit, total); i++) {
    rows.push({ ho: `3가${String(i + 1).padStart(3, '0')}호`, excl_area_m2: 4.0, total_cnt: total });
  }
  return rows;
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

/** 표 전체 기준 최근 8분기(최신 → 옛) — 서버 `window_quarters` 꼴 그대로(결정 0033). */
const OC_WINDOW = ['20262', '20261', '20254', '20253', '20252', '20251', '20244', '20243'];

/**
 * 상권 개업·폐업(함수 `list_district_openclose`) — 서울 코엑스 필지의 답 모양(2026-10-06 라이브
 * 실호출 모양 · 값은 일부 줄임). 상권 둘(좁은 상권 먼저) · 둘째 상권은 창 안에 빠진 분기가 있다.
 */
export function openClose(): DistrictOpenClose[] {
  const quarter = (qq: string, op: number, cl: number, opRt: number | null, clRt: number | null) => ({
    quarter: qq,
    similr_induty_stor_co: 441,
    stor_co: 378,
    frc_stor_co: 63,
    opbiz_stor_co: op,
    clsbiz_stor_co: cl,
    opbiz_rt: opRt,
    clsbiz_rt: clRt,
  });
  return [
    {
      status: 'ok',
      district_id: '3120218',
      district_nm: '코엑스',
      district_type: '발달상권',
      latest_quarter: '20262',
      quarters: OC_WINDOW.map((qq, i) => quarter(qq, 5 + i, 9 + i, 1.13 + i * 0.1, 2.04 + i * 0.1)),
      industries: [
        {
          svc_induty_cd: 'CS300011',
          svc_induty_cd_nm: '일반의류',
          similr_induty_stor_co: 90,
          stor_co: 90,
          frc_stor_co: 0,
          opbiz_stor_co: 1,
          clsbiz_stor_co: 4,
          opbiz_rt: 1.0,
          clsbiz_rt: 4.0,
        },
      ],
      other_industries: {
        industry_count: 47,
        similr_induty_stor_co: 172,
        stor_co: 149,
        frc_stor_co: 23,
        opbiz_stor_co: 1,
        clsbiz_stor_co: 1,
        opbiz_rt: 0.58,
        clsbiz_rt: 0.58,
      },
      window_quarters: OC_WINDOW,
    },
    {
      status: 'ok',
      district_id: '3001496',
      district_nm: '강남 마이스 관광특구',
      district_type: '관광특구',
      latest_quarter: '20262',
      quarters: [quarter('20262', 30, 41, 1.5, 2.1), quarter('20254', 28, 35, 1.4, 1.8)],
      industries: null,
      other_industries: null,
      window_quarters: OC_WINDOW,
    },
  ];
}

/** 대전 필지의 답 — 건물 단위 상태 한 줄(나머지 칸 null · 창만 값). */
/**
 * 대전 「동네 폐업 (대전시 공표)」 서버 답(결정 0044 · `get_daejeon_dong_closure`) — 지시서 예시값(둔산2동 ·
 * 20261028 받음) 그대로: 분기 95·100·80·103·95 · 최근 4분기 378 · 업종 1~5위 + 그 밖 11종 153건.
 */
export function daejeonClosure(): DaejeonDongClosure[] {
  const rest = [19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 8].map((n, i) => ({ induty_nm: `그밖업종${i + 1}`, clsbiz_co: n }));
  return [
    {
      status: 'ok',
      dong_nm: '둔산2동',
      received_on: '2026-10-28',
      quarters: [
        { quarter: '20251', clsbiz_co: 95 },
        { quarter: '20252', clsbiz_co: 100 },
        { quarter: '20253', clsbiz_co: 80 },
        { quarter: '20254', clsbiz_co: 103 },
        { quarter: '20261', clsbiz_co: 95 },
      ],
      sum_quarters: ['20252', '20253', '20254', '20261'],
      clsbiz_sum: 378,
      industries: [
        { induty_nm: '음식점업', clsbiz_co: 111 },
        { induty_nm: '주점 및 비알코올 음료점업', clsbiz_co: 35 },
        { induty_nm: '섬유, 의복, 신발 및 가죽제품 소매업', clsbiz_co: 32 },
        { induty_nm: '미용, 욕탕 및 유사 서비스업', clsbiz_co: 26 },
        { induty_nm: '유원지 및 기타 오락관련 서비스업', clsbiz_co: 21 },
        ...rest,
      ],
    },
  ];
}

/**
 * 업종별 추정매출(결정 0045 PR③ · `list_district_sales`) — 상권 둘(좁은 상권 먼저 · 합치지 않는다). 숫자는 가짜 보기 숫자.
 * 첫 상권: 8분기 창에서 20244 가 빠짐('–') · 가장 큰 분기 20254(760,000,000) · 최신 20262 = 7억 2,300만원 · 결제 15,208건 ·
 * 상위 5(커피-음료 포함 · 미용실 포함) + 그 밖 9업종 · 업종 전부에 네일숍(상위 5 밖) — 피부관리실은 없다.
 * 둘째 상권(관광특구): 창 안 두 분기만(나머지 '–') · 첫 상권의 약 153배(상권마다 제 눈금 시험 · 검사 뒤 보완 F1).
 * 업종 이름에 「스포츠 강습」(낱말 사이 빈칸이 든 긴 이름 — 휴대폰 첫 칸 줄바꿈 시험 · F10)을 둔다.
 */
export function districtSales(): DistrictSales[] {
  const window = ['20262', '20261', '20254', '20253', '20252', '20251', '20244', '20243'];
  const top = [
    { cd: 'CS100001', nm: '한식음식점', amt: 214_000_000, co: 4120, mdwk_amt: 150_000_000, wkend_amt: 64_000_000 },
    { cd: 'CS100010', nm: '커피-음료', amt: 139_000_000, co: 5310, mdwk_amt: 90_000_000, wkend_amt: 49_000_000 },
    { cd: 'CS300002', nm: '편의점', amt: 98_000_000, co: 3250, mdwk_amt: 70_000_000, wkend_amt: 28_000_000 },
    { cd: 'CS200028', nm: '미용실', amt: 61_000_000, co: 980, mdwk_amt: 40_000_000, wkend_amt: 21_000_000 },
    { cd: 'CS200005', nm: '스포츠 강습', amt: 47_000_000, co: 410, mdwk_amt: 40_000_000, wkend_amt: 7_000_000 },
  ];
  return [
    {
      status: 'ok',
      district_id: '3110001',
      district_nm: '○○역 2번 출구',
      district_type: '골목상권',
      latest_quarter: '20262',
      window_quarters: window,
      trend: [
        { quarter: '20262', amt: 723_000_000, co: 15208 },
        { quarter: '20261', amt: 654_000_000, co: 14000 },
        { quarter: '20254', amt: 760_000_000, co: 16000 },
        { quarter: '20253', amt: 623_000_000, co: 13000 },
        { quarter: '20252', amt: 707_000_000, co: 15000 },
        { quarter: '20251', amt: 676_000_000, co: 14500 },
        { quarter: '20243', amt: 692_000_000, co: 14800 },
      ],
      top,
      rest_cnt: 9,
      rest_amt: 164_000_000,
      rest_co: 1138,
      industries: [
        ...top.map(({ cd, nm, amt, co }) => ({ cd, nm, amt, co })),
        { cd: 'CS200029', nm: '네일숍', amt: 30_000_000, co: 610 },
      ],
    },
    {
      status: 'ok',
      district_id: '3001496',
      district_nm: '강남 마이스 관광특구',
      district_type: '관광특구',
      latest_quarter: '20262',
      window_quarters: window,
      // 운영 꼴 — 관광특구는 골목상권보다 수십 배 크다(운영 raw 1,163억 vs 골목 가운데값 19.9억 · 검사 뒤 보완 F1).
      // 여기서는 첫 상권 최댓값(7억 6,000만)의 약 153배 — 카드 하나 눈금이면 첫 상권 막대가 1% 안팎으로 사라진다.
      trend: [
        { quarter: '20262', amt: 116_300_000_000, co: 900_000 },
        { quarter: '20261', amt: 58_150_000_000, co: 450_000 },
      ],
      top: [{ cd: 'CS100001', nm: '한식음식점', amt: 116_300_000_000, co: 900_000 }],
      rest_cnt: 0,
      rest_amt: 0,
      rest_co: 0,
      industries: [{ cd: 'CS100001', nm: '한식음식점', amt: 116_300_000_000, co: 900_000 }],
    },
  ];
}

/**
 * 상권 인구(결정 0045 PR③ · `list_district_pop`) — 상권 둘. 첫 상권은 셋 다 · 둘째 상권은 길단위인구가 옛 분기(20254)에서
 * 끊겼고 사는 사람 값이 없다(마지막 분기 20224 — 「…까지」) · 일하는 사람은 마지막 분기도 없다(덩이 없음).
 */
export function districtPop(): DistrictPop[] {
  const flow = {
    tot: 412560,
    ml: 190100,
    fml: 222460,
    agrde_10: 30000,
    agrde_20: 90000,
    agrde_30: 100000,
    agrde_40: 80000,
    agrde_50: 60000,
    agrde_60_above: 52560,
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
  return [
    {
      status: 'ok',
      district_id: '3110001',
      district_nm: '○○역 2번 출구',
      district_type: '골목상권',
      flow_table_quarter: '20262',
      flow_quarter: '20262',
      flow,
      resident_value_quarter: '20234',
      resident_last_quarter: '20262',
      resident: { tot: 2310, ml: 1090, fml: 1220, tot_hshld: 1120, apt_hshld: 600, non_apt_hshld: 520 },
      worker_value_quarter: '20244',
      worker_last_quarter: '20262',
      worker: { tot: 6840, ml: 3900, fml: 2940 },
    },
    {
      status: 'ok',
      district_id: '3001496',
      district_nm: '강남 마이스 관광특구',
      district_type: '관광특구',
      flow_table_quarter: '20262',
      flow_quarter: '20254',
      flow: { ...flow, tot: 1_200_000, ml: 600_000, fml: 600_000 },
      resident_value_quarter: null,
      resident_last_quarter: '20224',
      resident: null,
      worker_value_quarter: null,
      worker_last_quarter: null,
      worker: null,
    },
  ];
}

/**
 * 가까운 지하철역 승하차(결정 0045 PR⑥ · `list_nearby_subway`) — ok 둘(가까운 순 · 서버 차례 그대로). 첫째 = 충무로 3·4호선
 * 180m · 12개월 자료(시간대 17~21 이 가장 큼) · 둘째 = 양재시민의숲 신분당선 320m(서울시 자료 밖 노선 — 숫자 칸 null).
 */
export function nearbySubway(): NearbySubway[] {
  const empty = { nearest_nm: null, nearest_lines: null, nearest_dist_m: null };
  return [
    {
      status: 'ok',
      group_id: 101,
      station_nm: '충무로',
      lines: ['3호선', '4호선'],
      lines_with_data: ['3호선', '4호선'],
      dist_m: 180,
      has_data: true,
      window_from: '202510',
      window_to: '202609',
      months_n: 12,
      on_daily: 31600,
      off_daily: 32300,
      bins: {
        h04_07: { on: 1200, off: 900 },
        h07_10: { on: 9000, off: 8000 },
        h10_14: { on: 5000, off: 6000 },
        h14_17: { on: 4000, off: 4300 },
        h17_21: { on: 10000, off: 11000 },
        h21_04: { on: 2400, off: 2000 },
      },
      ...empty,
    },
    {
      status: 'ok',
      group_id: 202,
      station_nm: '양재시민의숲',
      lines: ['신분당선'],
      lines_with_data: null,
      dist_m: 320,
      has_data: false,
      window_from: '202510',
      window_to: '202609',
      months_n: 0,
      on_daily: null,
      off_daily: null,
      bins: null,
      ...empty,
    },
  ];
}

/** 500m 안 역 0(결정 0045 PR⑥ · 👤 Q3 가) — 가장 가까운 역이 1.5km 안. */
export function nearbySubwayNoStation(): NearbySubway[] {
  return [
    {
      status: 'no_station',
      group_id: null,
      station_nm: null,
      lines: null,
      lines_with_data: null,
      dist_m: null,
      has_data: null,
      window_from: null,
      window_to: null,
      months_n: null,
      on_daily: null,
      off_daily: null,
      bins: null,
      nearest_nm: '수유',
      nearest_lines: ['4호선'],
      nearest_dist_m: 820,
    },
  ];
}

/**
 * 대전 상권 인구(결정 0045 PR⑤ · `get_district_census_pop`) — 상권 둘(좁은 상권 먼저 · 서버 차례 그대로).
 * 첫 상권은 통째로 든 집계구가 있어 값 + 범위 · 둘째 상권은 통째 0개라 셋 다 범위가 값의 2배를 넘어 범위만(시안 숫자 그대로 ·
 * 상권 이름도 가짜).
 */
export function districtCensusPop(): DistrictCensusPop[] {
  const rel = { received_on: '2026-10-08', base_year: 2024, bnd_base_date: '2025-06-30' };
  return [
    {
      status: 'ok',
      district_id: 'DJ-A',
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
      ...rel,
    },
    {
      status: 'ok',
      district_id: 'DJ-B',
      district_nm: '시청역 가짜출구',
      district_type: '발달상권',
      area_m2: 250000,
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
      ...rel,
    },
  ];
}

export function openCloseNotSeoul(): DistrictOpenClose[] {
  return [
    {
      status: 'not_seoul',
      district_id: null,
      district_nm: null,
      district_type: null,
      latest_quarter: null,
      quarters: null,
      industries: null,
      other_industries: null,
      window_quarters: OC_WINDOW,
    },
  ];
}

/**
 * `get_store_history` 응답 — 가게 이력(결정 0045 PR④ · 가짜 보기 값). 23줄 = 지금 보임 6(첫 줄은 첫 분기부터) +
 * 안 보임 17 · 서버 차례 그대로(지금 보임 → 보인 분기 수 ↓). `lastYm` = 표지 마지막 분기(어긋남 줄 시험이 한 분기 앞으로 바꾼다).
 */
export function storeHistory(lastYm = '202606'): StoreHistoryRow[] {
  const base = {
    status: 'ok' as const,
    total_cnt: 23,
    current_cnt: 6,
    history_first_ym: '201712',
    history_last_ym: lastYm,
    truncated: false,
  };
  const names = ['한솔마트', '다솜피아노교습소', '카페 모모', '우리치과의원', '행복공인중개사사무소', '청춘분식'];
  const current: StoreHistoryRow[] = names.map((biz_name, i) => ({
    ...base,
    floor_no: i === 4 ? null : (i % 3) + 1,
    biz_name,
    first_ym: i === 0 ? '201712' : '202003',
    last_ym: lastYm,
    seen_cnt: i === 0 ? 35 : 26 - i,
    is_current: true,
    truncated: i === 0,
  }));
  const gone: StoreHistoryRow[] = Array.from({ length: 17 }, (_v, i) => ({
    ...base,
    floor_no: i % 4 === 0 ? -1 : (i % 3) + 1,
    biz_name: `지난가게${String(i + 1).padStart(2, '0')}`,
    first_ym: '201903',
    last_ym: '202312',
    seen_cnt: 20 - i,
    is_current: false,
  }));
  return [...current, ...gone];
}
