import { describe, it, expect } from 'vitest';
import { roleSummaryView, floorUnknownNote, type RoleSummaryInput, type RoleSummaryView } from './roleSummary';
import type {
  BuildingHit,
  DistrictOpenClose,
  FloorRow,
  IndustryMedian,
  IndustryMix,
  ParcelTransaction,
  PriceBand,
  RentStat,
} from '../types';

/**
 * 역할 요약 판의 고르기(결정 0039 W2) — 역할 셋 × (값 다 있음 · 일부 실패 · 0건 · 대상 아님) + 판단 낱말·금지어·시세↔임대 가드.
 * ⓘ 숫자는 카드 함수가 만든 글 그대로라, 여기서는 **어느 카드 글이 어느 칸에 오는지**와 빈 값 갈래를 본다.
 */

const PNU = '1168010100100010000';

function floor(no: number, store: number | null): FloorRow {
  return {
    bld_id: 'B-1',
    pnu: PNU,
    floor_no: no,
    floor_label: null,
    floor_area_m2: 300,
    floor_area_gross_m2: 340,
    segment_cnt: 1,
    main_use: '소매점',
    uses: [],
    bld_nm: '역삼빌딩',
    approve_date: '2003-05-14',
    is_jiphap: true,
    road_addr: '서울 강남구 테헤란로 1',
    road_contact: null,
    bld_cnt_in_pnu: 1,
    store_cnt: store,
    stores: [],
    total_area_m2: 1234.5,
    far: 350.5,
    bcr: 59.9,
    parking_cnt: 120,
    elevator_ride: 3,
    elevator_emgen: 0,
    ho_cnt: 48,
    bld_main_use: '제1종근린생활시설',
  };
}

const FLOORS: FloorRow[] = [floor(3, 2), floor(2, 3), floor(1, 4)];

const BUILDING: BuildingHit = {
  bld_id: 'B-1',
  pnu: PNU,
  bld_nm: '역삼빌딩',
  road_addr: '서울 강남구 테헤란로 1',
  bld_cnt_in_pnu: 1,
  floor_cnt: 3,
  min_floor: 1,
  max_floor: 3,
  has_roof: false,
};

function band(no: number, over: Partial<PriceBand>): PriceBand {
  return {
    floor_no: no,
    status: 'ok',
    stage: 'L5',
    n: 7,
    p25: 3_000_000,
    median: 3_500_000,
    p75: 4_000_000,
    median_area_m2: 33,
    window_from: '2024-01',
    ...over,
  };
}

const BANDS: PriceBand[] = [
  band(1, { status: 'floor_1f', stage: null, n: null, p25: null, median: null, p75: null, median_area_m2: null }),
  band(2, {}),
  band(3, { stage: 'L6', n: 12, p25: 2_000_000, median: 2_400_000, p75: 2_800_000 }),
];

function tx(ym: string, price: number, over: Partial<ParcelTransaction> = {}): ParcelTransaction {
  return {
    floor_no: 2,
    contract_ym: ym,
    contract_day: 3,
    bld_area_m2: 33,
    price_won: price,
    unit_price: Math.round(price / 33),
    tx_type: '집합',
    ...over,
  };
}

const TXS: ParcelTransaction[] = [
  tx('202603', 240_000_000),
  tx('202511', 230_000_000, { floor_no: null }),
  tx('202508', 120_000_000, { is_share: true }),
  tx('202402', 210_000_000),
];

const RENT: RentStat[] = [
  {
    district_nm: '역삼역',
    rone_region_nm: '서울>강남>테헤란로',
    bld_type: '집합상가',
    quarter: '2026Q2',
    vacancy_rate: 10.08,
    rent_per_m2: 27.06,
    yield_rate: 0.82,
  },
];

const OC: DistrictOpenClose[] = [
  {
    status: 'ok',
    district_id: 'oc-1',
    district_nm: '역삼역 상권',
    district_type: '발달상권',
    latest_quarter: '20262',
    quarters: [
      {
        quarter: '20262',
        similr_induty_stor_co: 412,
        stor_co: 380,
        frc_stor_co: 40,
        opbiz_stor_co: 12,
        clsbiz_stor_co: 9,
        opbiz_rt: 3.1,
        clsbiz_rt: 2.2,
      },
    ],
    industries: null,
    other_industries: null,
    window_quarters: ['20262'],
  },
];

const MIX: IndustryMix = {
  snapshot_ym: '202606',
  radius_m: 500,
  districts: [
    {
      district_id: 'd-1',
      name: '역삼역',
      type: '발달상권',
      source_nm: '서울특별시 상권분석서비스',
      total: 400,
      cats: [
        { cd: 'I2', nm: '음식', n: 160 },
        { cd: 'G2', nm: '소매', n: 120 },
        { cd: 'S2', nm: '수리·개인', n: 80 },
        { cd: 'P1', nm: '교육', n: 40 },
      ],
    },
  ],
  radius: { total: 900, cats: [{ cd: 'I2', nm: '음식', n: 900 }] },
};

const MEDIAN: IndustryMedian = {
  snapshot_ym: '202606',
  min_total: 30,
  min_pop: 30,
  districts: [
    {
      district_id: 'd-1',
      type: '발달상권',
      total: 400,
      pop: { scope: 'type', sido_cd: '11', district_type: '발달상권', n: 249 },
      cats: [
        { cd: 'I2', nm: '음식', med_pct: 25 },
        { cd: 'G2', nm: '소매', med_pct: 18.5 },
      ],
    },
  ],
};

function input(over: Partial<RoleSummaryInput> = {}): RoleSummaryInput {
  return {
    role: '투자자',
    chip: '전체',
    building: BUILDING,
    floors: FLOORS,
    stats: { snapshot_ym: '202606', store_cnt: 1000, floor_missing_cnt: 329, floor_missing_pct: 32.9 },
    txs: TXS,
    bands: BANDS,
    bandsFailed: false,
    landPrice: { land_price: 45_230_000, land_price_year: 2025 },
    noCoord: false,
    rent: RENT,
    openClose: OC,
    mix: MIX,
    median: MEDIAN,
    ...over,
  };
}

function view(over: Partial<RoleSummaryInput> = {}): RoleSummaryView {
  const v = roleSummaryView(input(over));
  if (v === null) throw new Error('판이 없다');
  return v;
}

const tile = (v: RoleSummaryView, key: string) => v.tiles.find((t) => t.key === key);
const tileText = (v: RoleSummaryView, key: string) => {
  const t = tile(v, key);
  return t ? [t.label, ...t.lines, ...t.basis, t.grade?.text ?? ''].join(' | ') : '';
};
const allText = (v: RoleSummaryView) =>
  [v.question, v.answer ?? '', ...v.tiles.map((t) => [t.label, ...t.lines, ...t.basis, t.grade?.text ?? ''].join(' '))].join(' ');

/**
 * 판단 낱말 찾기(결정 0036 ㉕ — 한 줄 답은 사실만). 걸린 낱말 목록을 돌려준다.
 * 못 보는 것: 목록에 없는 판단 말투(예: 「눈여겨볼」) · 띄어 쓴 변형(「많 습니다」).
 */
const JUDGMENT = ['많', '적습', '적다', '적은 편', '되겠', '될 것', '좋', '나쁘', '유망', '추천', '괜찮', '충분', '부족', '활발', '위험', '높습', '높은', '낮습', '낮은', '비싸', '저렴', '인기'];
function judgmentWords(text: string): string[] {
  return JUDGMENT.filter((w) => text.includes(w));
}

/**
 * 금지어 찾기(절대 규칙 2). 못 보는 것: 띄어 쓴 변형(「적정 가격」)은 공백을 지운 글로도 본다 — 그 밖의 변형은 못 본다.
 */
const FORBIDDEN = ['적정가격', '적정가', '평가액', '감정가', '가치평가'];
function forbiddenWords(text: string): string[] {
  const squeezed = text.replace(/\s+/g, '');
  return FORBIDDEN.filter((w) => squeezed.includes(w));
}

describe('roleSummaryView — 역할 없음', () => {
  it('역할이 null 이면 판이 없다', () => {
    expect(roleSummaryView(input({ role: null }))).toBeNull();
  });
  it('층이 없으면 판이 없다', () => {
    expect(roleSummaryView(input({ floors: [] }))).toBeNull();
  });
  it('층 행이 다른 건물 것이면(건물이 바뀐 첫 그림) 판이 없다', () => {
    expect(roleSummaryView(input({ building: { ...BUILDING, bld_id: 'B-2' } }))).toBeNull();
  });
});

describe('투자자 「얼마고 얼마 벌리나」', () => {
  it('값이 다 있으면 시세 띠 · 이 땅 거래 · 상권 임대료 · 공시지가 넷', () => {
    const v = view();
    expect(v.question).toBe('얼마고 얼마 벌리나');
    expect(v.tiles.map((t) => t.key)).toEqual(['band', 'tx', 'rent', 'land']);
    // 시세 = 값을 낸 줄 중 땅에 가장 가까운 지상층(2층) 한 줄 — 카드 글 그대로 + C등급(추정 색).
    const b = tile(v, 'band')!;
    expect(b.label).toBe('참고 시세 (2층)');
    expect(b.lines).toEqual(['비슷한 호실 한 칸 33㎡ (10평) 기준 1.0억~1.3억']);
    expect(b.basis).toEqual(['㎡당 300만~400만 · 가운데값 ㎡당 350만 · 근거: 500m 안 같은 층 · 거래 7건 · 먼 근거']);
    expect(b.grade).toEqual({ text: 'C등급 · 파생 추정', est: true });
    expect(tile(v, 'tx')!.lines).toEqual(['이 땅 거래 4건']);
    expect(tile(v, 'rent')!.lines).toEqual(['㎡당 임대료 27,060원']);
    expect(tile(v, 'rent')!.basis).toEqual(['상권 평균 · 집합상가 · 2026년 2분기 조사', '역삼역 · 부동산원 조사구역 서울>강남>테헤란로']);
    expect(tile(v, 'land')!.lines).toEqual(['땅 1㎡당 4,523만원']);
    expect(v.answer).toBe('2층 참고 시세는 비슷한 호실 한 칸 33㎡ (10평) 기준 1.0억~1.3억입니다. 이 땅 신고 거래는 4건입니다.');
  });

  it('결정 0040 — 서버가 묶음을 주면 시세 타일 근거에도 「업무 거래 N건」이 흘러온다(카드와 같은 bandText · ㉦)', () => {
    const v = view({ bands: [BANDS[0], band(2, { use_group: 'office' }), BANDS[2]] });
    expect(tile(v, 'band')!.basis).toEqual([
      '㎡당 300만~400만 · 가운데값 ㎡당 350만 · 근거: 500m 안 같은 층 · 업무 거래 7건 · 먼 근거',
    ]);
    // 주거 층(값 안 냄)은 시세 타일 대상이 아니다 — 다음 값 낸 층(3층)이 선다.
    const noValue = { stage: null, n: null, p25: null, median: null, p75: null, median_area_m2: null };
    const r = view({
      bands: [
        BANDS[0],
        band(2, { status: 'floor_resid', ...noValue }),
        band(3, { stage: 'L6', n: 12, p25: 2_000_000, median: 2_400_000, p75: 2_800_000, use_group: 'shop' }),
      ],
    });
    expect(tile(r, 'band')!.label).toBe('참고 시세 (3층)');
    expect(tile(r, 'band')!.basis[0]).toContain('상가 거래 12건');
  });

  it('일부 실패(시세·임대·공시지가) = 그 칸 없음 — 「없음」이라 적지 않는다', () => {
    const v = view({ bandsFailed: true, rent: null, landPrice: null });
    expect(v.tiles.map((t) => t.key)).toEqual(['tx']);
    expect(v.answer).toBe('이 땅 신고 거래는 4건입니다.');
    // 실거래까지 아직이면 답도 없다.
    expect(view({ bandsFailed: true, rent: null, landPrice: null, txs: null }).answer).toBeNull();
  });

  it('0건 = 「이 땅 거래 0건」 · 대상 아님 = 카드 글 그대로(구 관문 · 조사 표본 밖)', () => {
    const v = view({ txs: [], bands: [band(0, { floor_no: null, status: 'gate_fail' })], rent: [] });
    expect(tile(v, 'tx')!.lines).toEqual(['이 땅 거래 0건']);
    expect(tile(v, 'band')!.lines).toEqual(['아직 참고 시세를 내지 않는 구입니다']);
    expect(tile(v, 'rent')!.lines).toEqual(['부동산원 조사 대상 상권이 아닙니다']);
    expect(view({ rent: [], noCoord: true }).tiles.find((t) => t.key === 'rent')!.lines).toEqual([
      '위치 정보가 없어 속한 상권을 찾지 못했습니다',
    ]);
    expect(v.answer).toBe('이 구는 아직 참고 시세를 내지 않습니다. 이 땅 신고 거래는 0건입니다.');
  });

  it('값을 낸 줄이 없으면 카드 요약 글 그대로', () => {
    const v = view({ bands: [BANDS[0]] });
    expect(tile(v, 'band')!.lines).toEqual(['이 건물에서는 값을 낸 층이 없습니다']);
  });
});

describe('창업자 「여기서 장사가 되나」', () => {
  it('칩 「전체」 — 속한 상권 블록의 앞 두 대분류 비중 + 가운데값 · 개업/폐업 · 임대 · 1층 점포', () => {
    const v = view({ role: '창업자' });
    expect(v.question).toBe('여기서 장사가 되나');
    expect(v.tiles.map((t) => t.key)).toEqual(['industry', 'openclose', 'rent', 'floor1']);
    const ind = tile(v, 'industry')!;
    expect(ind.label).toBe('업종 비중 (상위 2개)');
    expect(ind.lines).toEqual(['음식 40.0% · 서울 발달상권 가운데 25.0%', '소매 30.0% · 서울 발달상권 가운데 18.5%']);
    expect(ind.basis[0]).toBe('역삼역(발달상권) 안 점포 400곳');
    expect(ind.grade).toEqual({ text: 'C등급 · 비교값', est: true });
    expect(tile(v, 'openclose')!.lines).toEqual(['개업 12곳 · 개업률(분기) 3.1%', '폐업 9곳 · 폐업률(분기) 2.2%']);
    expect(tile(v, 'openclose')!.basis[0]).toBe('역삼역 상권 · 2026년 2분기');
    const f1 = tile(v, 'floor1')!;
    expect(f1.lines).toEqual(['점포 4']);
    expect(f1.basis[0]).toBe('층이 적히지 않은 점포(서비스 지역 전체 약 3곳 중 1곳(32.9%))는 이 수에 들지 않습니다');
    expect(f1.grade).toEqual({ text: 'D등급 · 간접 추론', est: false });
    expect(v.answer).toBe(
      '역삼역(발달상권) 안 음식 업종 비중은 40.0%이고, 비교값은 서울 발달상권 가운데 25.0%입니다. 이 건물 1층에 적힌 점포는 4곳입니다.',
    );
  });

  it('칩을 고르면 그 대분류 하나 — 이름표는 대분류 이름 · 칩이 든 대분류라는 사실 한 줄', () => {
    const v = view({ role: '창업자', chip: '카페' });
    const ind = tile(v, 'industry')!;
    expect(ind.label).toBe('업종 비중 · 음식(대분류)');
    expect(ind.lines).toEqual(['음식 40.0% · 서울 발달상권 가운데 25.0%']);
    expect(ind.basis).toContain('고른 업종(카페)은 음식 대분류에 듭니다');
    // 상권 블록에 그 대분류가 없으면 0곳(사실) · 편의점 칩은 짝짓기 표의 설명 한 줄을 그대로.
    const conv = tile(view({ role: '창업자', chip: '편의점', mix: { ...MIX, districts: [{ ...MIX.districts[0], cats: [MIX.districts[0].cats[0]], total: 160 }] } }), 'industry')!;
    expect(conv.lines).toEqual(['소매 0곳']);
    expect(conv.basis).toContain('종합 소매에는 편의점과 슈퍼마켓이 함께 들어 있습니다');
  });

  it('일부 실패 = 그 칸 없음(곁 카드 넷) · 1층 칸은 층 목록이라 남는다', () => {
    const v = view({ role: '창업자', mix: null, median: null, openClose: null, rent: null, stats: null });
    expect(v.tiles.map((t) => t.key)).toEqual(['floor1']);
    expect(v.tiles[0].basis[0]).toBe('층이 적히지 않은 점포는 이 수에 들지 않습니다');
    // 가운데값만 실패 = 비교 글·배지만 빠진다.
    const noMed = tile(view({ role: '창업자', median: null }), 'industry')!;
    expect(noMed.lines).toEqual(['음식 40.0%', '소매 30.0%']);
    expect(noMed.grade).toBeNull();
    // 상권 블록이 없으면(반경만) 업종 칸 없음 — 반경 값은 내지 않는다.
    expect(tile(view({ role: '창업자', mix: { ...MIX, districts: [] } }), 'industry')).toBeUndefined();
  });

  it('대상 아님 = 카드 글 그대로(대전의 개업·폐업) · 1층 줄이 없으면 「–」', () => {
    const dj = '3017010100100010000';
    const v = view({
      role: '창업자',
      building: { ...BUILDING, pnu: dj },
      openClose: [{ ...OC[0], status: 'not_seoul', district_id: null, district_nm: null, latest_quarter: null, quarters: null }],
      floors: [floor(2, 3)],
    });
    expect(tile(v, 'openclose')!.lines).toEqual(['서울 상권만 다루는 자료라 이 건물(대전)에는 없습니다']);
    expect(tile(v, 'floor1')!.lines).toEqual(['–']);
  });
});

describe('중개사 「손님에게 뭘 보여 주나」', () => {
  it('소유 구조 한 줄 · 대장 호수 · 실거래 최근 3건', () => {
    const v = view({ role: '중개사' });
    expect(v.question).toBe('손님에게 뭘 보여 주나');
    expect(v.tiles.map((t) => t.key)).toEqual(['owner', 'ho', 'tx3']);
    expect(tile(v, 'owner')!.lines).toEqual(['집합건물 · 사용승인 2003년 5월 · 주차 120대 · 승강기 3대 · 대장 호수 48호']);
    expect(tile(v, 'ho')!.label).toBe('대장 호수');
    expect(tile(v, 'ho')!.lines).toEqual(['48호']);
    const t3 = tile(v, 'tx3')!;
    expect(t3.lines).toHaveLength(3);
    expect(t3.lines[0]).toBe('2층 · 2026-03 · 33㎡ (10평) · 2억 4,000만 · ㎡당 727만 · 집합');
    expect(t3.lines[1].startsWith('층 미상 · ')).toBe(true);
    expect(t3.lines[2].endsWith(' · 지분')).toBe(true);
    expect(t3.basis[0]).toBe('이 땅에서 신고된 거래 4건 중 최근 3건');
    expect(v.answer).toBe('집합건물, 대장 호수 48호이며, 이 땅 최근 신고 거래는 2026-03입니다.');
  });

  it('링크로 들어온 건물(검색 줄 칸 없음)도 층 목록 머리로 소유 구조를 말한다', () => {
    const v = view({ role: '중개사', building: { ...BUILDING, is_jiphap: undefined, approve_date: undefined, parking_cnt: undefined } });
    expect(tile(v, 'owner')!.lines[0].startsWith('집합건물 · 사용승인 2003년 5월')).toBe(true);
  });

  it('0건 · 실패 · 숨김(주거 주용도) 갈래', () => {
    expect(tile(view({ role: '중개사', txs: [] }), 'tx3')!.lines).toEqual(['이 땅 거래 0건']);
    expect(view({ role: '중개사', txs: [] }).answer).toBe('집합건물, 대장 호수 48호이며, 이 땅에서 신고된 거래는 0건입니다.');
    expect(tile(view({ role: '중개사', txs: null }), 'tx3')).toBeUndefined();
    const apt = view({ role: '중개사', floors: FLOORS.map((f) => ({ ...f, bld_main_use: '공동주택' })) });
    expect(tile(apt, 'ho')).toBeUndefined();
    expect(apt.answer).toBe('집합건물이며, 이 땅 최근 신고 거래는 2026-03입니다.');
  });
});

describe('검사 반영 — 상권 여럿 · 시세 층 고르기 · 모름과 0 · 같은 땅 여러 동 · 거래 상한', () => {
  it('상권이 둘이면 업종·임대·개업폐업 셋 다 첫째 + 「외 상권 1곳」', () => {
    const two = view({
      role: '창업자',
      mix: { ...MIX, districts: [MIX.districts[0], { ...MIX.districts[0], district_id: 'd-2', name: '강남역', total: 999 }] },
      rent: [RENT[0], { ...RENT[0], district_nm: '강남역', rone_region_nm: '서울>강남>강남대로', rent_per_m2: 51.2 }],
      openClose: [OC[0], { ...OC[0], district_id: 'oc-2', district_nm: '강남역 상권' }],
    });
    expect(tile(two, 'industry')!.basis[0]).toBe('역삼역(발달상권) 안 점포 400곳 · 외 상권 1곳');
    expect(tile(two, 'rent')!.lines).toEqual(['㎡당 임대료 27,060원']);
    expect(tile(two, 'rent')!.basis[1]).toBe('역삼역 외 상권 1곳 · 부동산원 조사구역 서울>강남>테헤란로');
    expect(tile(two, 'openclose')!.basis[0]).toBe('역삼역 상권 외 상권 1곳 · 2026년 2분기');
  });

  it('시세 층 고르기 — 지하와 지상이 섞이면 지상층 · 지하만 값을 내면 그 지하 줄', () => {
    const floors = [floor(2, 3), floor(1, 4), floor(-1, 1)];
    const mixed = view({ floors, bands: [band(-1, { n: 9, p25: 1_000_000, median: 1_100_000, p75: 1_200_000 }), band(2, {})] });
    expect(tile(mixed, 'band')!.label).toBe('참고 시세 (2층)');
    const under = view({ floors, bands: [band(-1, { n: 9, p25: 1_000_000, median: 1_100_000, p75: 1_200_000 }), BANDS[0]] });
    expect(tile(under, 'band')!.label).toBe('참고 시세 (지하 1층)');
    expect(tile(under, 'band')!.basis[0]).toContain('거래 9건');
  });

  it('1층 점포 칸이 비면(모름) 「—」 — 「점포 0」이 아니다', () => {
    const v = view({ role: '창업자', floors: [floor(2, 3), floor(1, null)] });
    expect(tile(v, 'floor1')!.lines).toEqual(['—']);
    expect(tileText(v, 'floor1')).not.toContain('점포 0');
    expect(v.answer ?? '').not.toContain('1층에 적힌 점포');
  });

  it('같은 땅에 건물이 여럿이면 1층 칸에 옆 동이 섞인다는 줄', () => {
    const v = view({ role: '창업자', floors: FLOORS.map((f) => ({ ...f, bld_cnt_in_pnu: 2 })) });
    expect(tile(v, 'floor1')!.basis).toContain('이 땅에 건물이 2동 있어 옆 동 점포가 섞여 보일 수 있습니다');
    expect(tile(view({ role: '창업자' }), 'floor1')!.basis).toHaveLength(1);
  });

  it('거래가 서버 상한(100건)에 닿으면 타일·근거 줄·한 줄 답이 같은 「(최근 100건까지)」 꼴', () => {
    const many = Array.from({ length: 100 }, (_, i) => tx(i === 0 ? '202603' : '202401', 200_000_000));
    expect(tile(view({ txs: many }), 'tx')!.lines).toEqual(['이 땅 거래 100건 (최근 100건까지)']);
    expect(view({ txs: many }).answer).toContain('이 땅 신고 거래는 100건 (최근 100건까지)입니다.');
    expect(tile(view({ role: '중개사', txs: many }), 'tx3')!.basis[0]).toBe('이 땅에서 신고된 거래 100건 (최근 100건까지) 중 최근 3건');
    expect(tile(view({ txs: TXS }), 'tx')!.lines).toEqual(['이 땅 거래 4건']);
  });
});

describe('가드 — 판단 낱말 0 · 금지어 0 · 시세와 임대를 잇지 않는다', () => {
  const scenarios: RoleSummaryInput[] = (['투자자', '창업자', '중개사'] as const).flatMap((role) => [
    input({ role }),
    input({ role, chip: '카페' }),
    input({ role, txs: [], rent: [], bands: [BANDS[0]] }),
    input({ role, bandsFailed: true, rent: null, mix: null, median: null, openClose: null, landPrice: null, txs: null }),
  ]);

  it('한 줄 답에 판단 낱말이 없다 — 양성 대조: 탐지가 실제로 잡는다', () => {
    for (const s of scenarios) {
      const v = roleSummaryView(s)!;
      expect(judgmentWords(v.answer ?? ''), `${s.role} ${v.answer}`).toEqual([]);
    }
    expect(judgmentWords('이 상권은 음식점이 많습니다.')).toEqual(['많']);
    expect(judgmentWords('폐업이 적은 편이라 좋은 자리입니다')).toEqual(['적은 편', '좋']);
  });

  it('판 어디에도 금지어가 없다 — 양성 대조: 붙여 쓴 꼴·띄어 쓴 꼴', () => {
    for (const s of scenarios) expect(forbiddenWords(allText(roleSummaryView(s)!))).toEqual([]);
    expect(forbiddenWords('적정가격은 3억')).toContain('적정가격');
    expect(forbiddenWords('감정 가는 없습니다')).toEqual(['감정가']);
  });

  it('임대 타일에 시세·거래 숫자가 없고, 시세 타일에 임대 숫자가 없고, 투자자 한 줄 답에 임대가 없다', () => {
    const v = view();
    const rent = tileText(v, 'rent');
    const price = [tileText(v, 'band'), tileText(v, 'tx'), tileText(v, 'land')].join(' ');
    expect(rent).not.toMatch(/억|만원|㎡당 \d+만|거래|시세|공시/);
    expect(rent).toContain('상권 평균');
    expect(price).not.toMatch(/27,060|임대|공실|수익률/);
    expect(v.answer).not.toMatch(/임대|27,060/);
    // 수익률(부동산원 투자수익률)은 임대 타일에도 싣지 않는다(나누기·비율 0).
    expect(rent).not.toMatch(/수익률|0\.82/);
  });
});

describe('floorUnknownNote — 1층 칸의 층 미상 글은 한 함수에서만', () => {
  it('비율이 있으면 「서비스 지역 전체」 글자와 함께, 없으면 사실 한 줄', () => {
    expect(floorUnknownNote({ snapshot_ym: '202606', store_cnt: 1, floor_missing_cnt: 1, floor_missing_pct: 50 })).toBe(
      '층이 적히지 않은 점포(서비스 지역 전체 약 2곳 중 1곳(50%))는 이 수에 들지 않습니다',
    );
    expect(floorUnknownNote(null)).toBe('층이 적히지 않은 점포는 이 수에 들지 않습니다');
  });
});
