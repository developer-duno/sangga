import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import type {
  BuildingHit,
  CoverageStats,
  FloorRow,
  ParcelTransaction,
  PriceBand,
  SigunguTxStat,
} from '../types';

/**
 * 층별 스택 화면 테스트.
 *
 * 특히 **각주 숫자가 손으로 박힌 값이 아니라 DB에서 온 값인지**를 지킨다.
 * 예전에는 "32.9%·64,239곳"이 문자열로 박혀 있었는데, 점포 데이터는 최신 분기를
 * 자동 추종하므로 새 분기를 적재하는 순간 각주만 옛 숫자를 말하게 된다
 * — 코드를 한 줄도 안 고쳤는데 화면이 틀려지는 종류의 결함이라 테스트로 못 박는다.
 */

/** supabase 쿼리 빌더 흉내. 어떤 순서로 이어 붙여도 마지막에 결과를 돌려준다. */
function makeQuery(result: { data: unknown; error: unknown }) {
  const q: Record<string, unknown> = {};
  for (const m of ['select', 'eq', 'order', 'limit']) {
    q[m] = () => q;
  }
  q.then = (cb: (r: unknown) => unknown) => Promise.resolve(result).then(cb);
  return q;
}

const responses = {
  floors: { data: [] as unknown, error: null as unknown },
  stats: { data: [] as unknown, error: null as unknown },
  /** 서버 함수 list_building_districts 의 응답. */
  districts: { data: null as unknown, error: null as unknown },
  /** 서버 함수 list_parcel_transactions 의 응답(이 땅의 실거래 이력). */
  txs: { data: [] as unknown, error: null as unknown },
  /** 서버 함수 get_sigungu_tx_stats 의 응답(구 층대별 단가). */
  txStats: { data: [] as unknown, error: null as unknown },
  /** 서버 함수 list_price_bands 의 응답(층별 참고 시세 · Stage B). */
  bands: { data: [] as unknown, error: null as unknown },
  /** true 면 밴드 응답을 영영 돌려주지 않는다 — "아직 안 옴" 상태를 보려고 둔 스위치다. */
  bandsPending: false,
  /**
   * 서버 함수 list_industry_mix 의 응답(둘레의 업종 분포 · 결정 0014).
   *
   * 기본값을 **오류**로 둔다 — 이 파일은 층 스택을 보는 곳이고, 업종 섹션은
   * `IndustryMixSection.test.tsx` 가 따로 본다. 오류면 섹션이 스스로 사라지므로
   * 여기 있는 다른 시험들의 화면이 그대로 유지된다(마이그레이션 적용 전 라이브와 같은 상태).
   */
  industryMix: { data: null as unknown, error: { message: 'not applied' } as unknown },
};

/** 마지막 rpc 호출의 인자. "구 코드를 pnu 에서 뽑아 보내는가"를 여기서 확인한다. */
const rpcCalls: Array<{ fn: string; args: unknown }> = [];

vi.mock('../lib/supabase', () => ({
  FLOOR_STACK_VIEW: 'v_floor_stack',
  COVERAGE_STATS_VIEW: 'v_coverage_stats',
  BUILDING_DISTRICTS_FN: 'list_building_districts',
  PARCEL_TX_FN: 'list_parcel_transactions',
  SIGUNGU_TX_STATS_FN: 'get_sigungu_tx_stats',
  PRICE_BANDS_FN: 'list_price_bands',
  INDUSTRY_MIX_FN: 'list_industry_mix',
  INDUSTRY_DETAIL_FN: 'list_industry_detail',
  // ⚠️ 이 흉내는 모듈을 **통째로** 갈아끼운다 — 진짜 파일에만 상수를 더하면 화면은
  //    undefined 를 그린다. 서버 짝 상수를 추가할 때 여기도 같이 더할 것.
  TX_LIST_CAP: 100,
  TX_OPEN_SINCE_LABEL: '2024년 1월',
  TX_BASEMENT_MISSING_SINCE: 2017,
  supabase: {
    from: (view: string) =>
      makeQuery(view === 'v_coverage_stats' ? responses.stats : responses.floors),
    // 상권 줄·실거래 블록이 이 rpc 를 부른다. 흉내에 rpc 가 없으면 화면이 통째로 죽으므로
    // (undefined.then) 여기 없는 것 자체가 다른 테스트 전부를 빨갛게 만든다.
    //
    // ⚠️ **함수 이름을 보고 갈라 답해야 한다.** 예전처럼 어느 rpc 든 같은 응답을 주면,
    //    실거래 이력에 상권 응답(객체)이 들어가 목록을 도는 코드가 죽거나, 반대로
    //    엉뚱한 응답으로 초록이 나 "테스트만 통과하는" 상태가 된다.
    rpc: (fn: string, args?: unknown) => {
      rpcCalls.push({ fn, args });
      if (fn === 'list_parcel_transactions') return Promise.resolve(responses.txs);
      if (fn === 'get_sigungu_tx_stats') return Promise.resolve(responses.txStats);
      if (fn === 'list_price_bands') {
        return responses.bandsPending ? new Promise(() => {}) : Promise.resolve(responses.bands);
      }
      // 둘레의 업종 분포. 갈라 답하지 않으면 상권 응답(객체)이 흘러들어 업종 목록을
      // 도는 코드가 죽는다 — 이 파일의 다른 시험까지 통째로 빨개진다.
      if (fn === 'list_industry_mix' || fn === 'list_industry_detail') {
        return Promise.resolve(responses.industryMix);
      }
      return Promise.resolve(responses.districts);
    },
  },
}));

const { FloorStack } = await import('./FloorStack');

function building(over: Partial<BuildingHit> = {}): BuildingHit {
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
    ...over,
  };
}

function floor(over: Partial<FloorRow> = {}): FloorRow {
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

function stats(over: Partial<CoverageStats> = {}): CoverageStats {
  return {
    snapshot_ym: '202603',
    store_cnt: 64239,
    floor_missing_cnt: 21124,
    floor_missing_pct: 32.9,
    ...over,
  };
}

function tx(over: Partial<ParcelTransaction> = {}): ParcelTransaction {
  return {
    floor_no: 3,
    contract_ym: '202605',
    contract_day: 12,
    bld_area_m2: 84.3,
    price_won: 320_000_000,
    unit_price: 3_800_000,
    tx_type: '집합',
    ...over,
  };
}

/** 층대 5칸을 서버가 주는 것과 같은 순서로 만든다. n 만 갈아 끼워 쓰는 용도. */
function bands(counts: Partial<Record<string, number>> = {}): SigunguTxStat[] {
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

/** 층별 참고 시세 한 줄(함수 list_price_bands). 기본은 강남 실측값 그대로. */
function priceBand(over: Partial<PriceBand> = {}): PriceBand {
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
 * 지하1층 no_evidence · 1층 floor_1f · 2층 ok · 3층 no_estimate · 옥탑 no_evidence.
 */
function priceBands(): PriceBand[] {
  return [
    priceBand({ floor_no: -1, status: 'no_evidence', ...NO_VALUE }),
    priceBand({ floor_no: 1, status: 'floor_1f', ...NO_VALUE }),
    priceBand({ floor_no: 2 }),
    priceBand({ floor_no: 3, status: 'no_estimate', ...NO_VALUE }),
    priceBand({ floor_no: 99, status: 'no_evidence', ...NO_VALUE }),
  ];
}

/** 기준선을 못 넘은 구 — floor_no 가 null 인 **한 줄**로만 온다. */
function priceBandGate(): PriceBand[] {
  return [priceBand({ floor_no: null, status: 'gate_fail', ...NO_VALUE })];
}

beforeEach(() => {
  rpcCalls.length = 0;
  responses.floors = { data: [floor()], error: null };
  responses.stats = { data: [stats()], error: null };
  responses.districts = {
    data: { covered: true, districts: [], sources: ['서울특별시 상권분석서비스'] },
    error: null,
  };
  responses.txs = { data: [], error: null };
  responses.txStats = { data: bands({ '1층': 213 }), error: null };
  // 기본은 빈 배열 = 참고 시세 섹션 미표시. 이 파일의 다른 테스트는 영향을 안 받는다.
  responses.bands = { data: [], error: null };
  responses.bandsPending = false;
  // 기본은 오류 = 업종 섹션 미표시(마이그레이션 적용 전 라이브와 같은 상태).
  // 그 섹션 자체는 IndustryMixSection.test.tsx 가 따로 본다.
  responses.industryMix = { data: null, error: { message: 'not applied' } };
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('FloorStack — 각주 숫자', () => {
  it('DB가 준 분기·점포 수를 그대로 보여준다', async () => {
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/2026년 1분기/)).toBeTruthy());
    expect(screen.getByText(/64,239곳/)).toBeTruthy();
    // 이 숫자가 **어느 범위**를 센 것인지 밝혀야 한다(2026-08-22a). 뷰가 세는 곳은
    // 화면에서 고를 수 있는 구뿐인데, 그 말이 없으면 사람은 전국 숫자로 읽는다.
    expect(screen.getByText(/서비스 지역/)).toBeTruthy();
  });

  it('DB 값이 바뀌면 각주도 따라 바뀐다 (손으로 박힌 값이 아니다)', async () => {
    // 이 테스트가 이 작업의 핵심이다. 다음 분기를 적재하면 화면이 저절로 따라와야 한다.
    responses.stats = {
      data: [stats({ snapshot_ym: '202609', store_cnt: 70123, floor_missing_pct: 25 })],
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/2026년 3분기/)).toBeTruthy());
    expect(screen.getByText(/70,123곳/)).toBeTruthy();
    // 25% = 4곳 중 1곳
    expect(screen.getByText(/약 4곳 중 1곳\(25%\)/)).toBeTruthy();
    // 옛 하드코딩 값이 남아 있으면 안 된다.
    expect(screen.queryByText(/64,239/)).toBeNull();
    expect(screen.queryByText(/32\.9%/)).toBeNull();
  });

  it('비율은 "N곳 중 1곳"으로 함께 풀어 쓴다', async () => {
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/약 3곳 중 1곳\(32\.9%\)/)).toBeTruthy());
  });

  it('각주를 못 불러오면 옛 숫자를 되살리지 않고 숫자만 뺀다', async () => {
    // 틀린 숫자를 보여주는 것이 숫자를 안 보여주는 것보다 나쁘다.
    responses.stats = { data: null, error: { message: 'boom' } };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/적지 않은 수/)).toBeTruthy());
    expect(screen.getByText(/상권정보 최신 분기 기준/)).toBeTruthy();
    expect(screen.queryByText(/64,239/)).toBeNull();
  });

  it('각주를 못 불러와도 경고 문장 자체는 남는다', async () => {
    responses.stats = { data: [], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/점포 수는 실제와 다를 수 있습니다/)).toBeTruthy());
  });
});

describe('FloorStack — 본체', () => {
  it('층 정보가 없으면 그렇다고 말한다', async () => {
    responses.floors = { data: [], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/층 정보가 없습니다/)).toBeTruthy());
  });

  it('조회에 실패하면 내부 오류 원문을 노출하지 않는다', async () => {
    responses.floors = {
      data: null,
      error: { message: 'permission denied for table building_floor' },
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/층 정보를 불러오지 못했습니다/)).toBeTruthy());
    expect(screen.queryByText(/building_floor/)).toBeNull();
  });

  it('지하층은 부호를 떼고 "지하 n층"으로 쌓는다', async () => {
    responses.floors = { data: [floor({ floor_no: -1, floor_label: null })], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('지하 1층')).toBeTruthy());
  });

  it('한 땅에 여러 동이 있으면 점포가 섞일 수 있다고 경고한다', async () => {
    responses.floors = { data: [floor({ bld_cnt_in_pnu: 3 })], error: null };
    render(<FloorStack building={building({ bld_cnt_in_pnu: 3 })} />);
    await waitFor(() => expect(screen.getByText(/이 땅에 건물이 3동 있습니다/)).toBeTruthy());
  });

  it('D등급 배지를 항상 함께 보여준다', async () => {
    // 추정값 출력 시 근거 레벨 병기는 프로젝트 절대 규칙 3이다.
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/D등급 · 간접 추론/)).toBeTruthy());
  });

  it('점포 0곳(확정)과 정보 없음(null)을 구분해 보여준다', async () => {
    // JS truthy 검사(f.store_cnt ? … : '—')를 쓰면 0 과 null 이 똑같이 '—' 로
    // 보인다. v_floor_stack 의 store_cnt 는 group by 없는 lateral count(*) 라
    // 매칭 0건이어도 항상 확정된 0 을 돌려준다(절대 NULL 이 아니다) — 그러니
    // 0 은 "점포 0"으로, null/undefined 만 '—'로 보여야 한다.
    responses.floors = {
      data: [
        floor({ floor_no: 2, store_cnt: 0 }),
        floor({ floor_no: 1, store_cnt: null }),
      ],
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('점포 0')).toBeTruthy());
    // null 인 층에는 '—' 만 남고 "점포 0"이 또 나오면 안 된다(0과 null이 같아 보이면 실패).
    expect(screen.getAllByText('점포 0')).toHaveLength(1);
    expect(screen.getByText('—')).toBeTruthy();
  });
});

describe('FloorStack — 도로접면 (로드맵 Wave 2 PR-A)', () => {
  it('토지특성 원문을 그대로 적는다 — 말을 옮기지 않는다', async () => {
    // ⛔ '큰길'·'골목' 같은 재해석은 금지다. 시세 사다리가 쓰는 등급(road_grade)과
    //    화면이 서로 다른 말을 하기 시작하면 같은 땅에 기준이 둘 생긴다.
    // 픽스처 값은 실측 어휘 그대로 쓴다(backtest_price.py 의 2026-08-19 목록 —
    // '광대한면' 같은 비슷한-듯-다른 값으로 증명하면 "원문 그대로"의 증거가 아니다).
    responses.floors = { data: [floor({ road_contact: '광대로한면' })], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('도로접면')).toBeTruthy());
    expect(screen.getByText('광대로한면')).toBeTruthy();
    // 재해석 가드는 실제로 쓰일 법한 말(road_grade 어휘)로 걸어야 잡는다 —
    // 화면에 존재한 적 없는 한 단어만 걸면 영구 공허 참이 된다.
    for (const w of ['큰길', '중간', '골목길']) {
      expect(screen.queryByText(new RegExp(w))).toBeNull();
    }
  });

  it("'맹지'·'지정되지않음'·빈 값이면 칸 자체를 안 만든다", async () => {
    for (const v of ['맹지', '지정되지않음', '', '   ', null]) {
      responses.floors = { data: [floor({ road_contact: v })], error: null };
      render(<FloorStack building={building()} />);
      await waitFor(() => expect(screen.getByText('테스트빌딩')).toBeTruthy());
      expect(screen.queryByText('도로접면')).toBeNull();
      cleanup();
    }
  });

  it('앞뒤 공백은 떼고 적는다', async () => {
    responses.floors = { data: [floor({ road_contact: ' 세로한면(가) ' })], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('도로접면')).toBeTruthy());
    expect(screen.getByText('세로한면(가)')).toBeTruthy();
  });
});

describe('FloorStack — 업종 요약 (로드맵 Wave 2 PR-A)', () => {
  /** 층 하나에 업종 이름만 갈아 끼운 점포를 붙인다. */
  function withStores(...cats: Array<string | null>): FloorRow {
    return floor({ stores: cats.map((cat) => ({ name: null, cat })) });
  }

  it('많은 업종 셋을 세어 적고, 나머지는 "외 N종"으로만 센다', async () => {
    responses.floors = {
      data: [withStores('한식', '한식', '커피', '부동산중개', '세탁', '편의점')],
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/많은 업종/)).toBeTruthy());
    const line = document.querySelector('.stack__biz')?.textContent ?? '';
    expect(line).toContain('한식 2곳');
    // 수가 같으면 이름순이다 — 그래야 새로 고칠 때마다 순서가 흔들리지 않는다
    // (부동산중개 < 세탁 < 커피 < 편의점).
    expect(line).toContain('부동산중개 1곳');
    expect(line).toContain('세탁 1곳');
    expect(line).not.toContain('편의점');
    expect(line).toContain('외 2종');
    // 이 줄의 새 문구에 '시세'가 섞이면 안 된다(절대 규칙 2 결 — 시세는 아래
    // 참고 시세 섹션의 말이고, 사실만 세는 이 줄에 들어오는 순간 성격이 섞인다).
    expect(line).not.toContain('시세');
  });

  it('층이 여럿이면 전부 합쳐 센다', async () => {
    responses.floors = {
      data: [
        floor({ floor_no: 2, stores: [{ name: null, cat: '한식' }] }),
        floor({ floor_no: 1, stores: [{ name: null, cat: '한식' }] }),
      ],
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/많은 업종/)).toBeTruthy());
    expect(document.querySelector('.stack__biz')?.textContent).toContain('한식 2곳');
  });

  it('업종 이름이 빈 점포는 순위에 넣지 않는다', async () => {
    // 세는 대상이 "업종"인데 모르는 것을 한 칸으로 만들면, 모르는 것이 업종 하나처럼 보인다.
    responses.floors = { data: [withStores(null, '', '한식')], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/많은 업종/)).toBeTruthy());
    const line = document.querySelector('.stack__biz')?.textContent ?? '';
    expect(line).toContain('한식 1곳');
    expect(line).not.toContain('외 ');
  });

  it('셀 업종이 하나도 없으면 줄을 아예 안 그린다', async () => {
    responses.floors = { data: [floor({ stores: [] })], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('테스트빌딩')).toBeTruthy());
    expect(document.querySelector('.stack__biz')).toBeNull();
  });

  it('동 중복 경고가 요약보다 **위**에 온다', async () => {
    // 이 숫자는 "땅 + 층"으로 붙여 센 것이라 옆 동 점포가 섞여 있다. 요약을 먼저 읽고
    // 나중에 경고를 만나면 이미 읽은 숫자가 안 고쳐진다 — 순서 자체가 규칙이다.
    responses.floors = {
      data: [floor({ bld_cnt_in_pnu: 3, stores: [{ name: null, cat: '한식' }] })],
      error: null,
    };
    render(<FloorStack building={building({ bld_cnt_in_pnu: 3 })} />);
    await waitFor(() => expect(screen.getByText(/많은 업종/)).toBeTruthy());

    const warn = document.querySelector('.warn')!;
    const biz = document.querySelector('.stack__biz')!;
    // DOCUMENT_POSITION_FOLLOWING = 경고 다음에 요약이 온다.
    expect(warn.compareDocumentPosition(biz) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe('FloorStack — 속한 상권', () => {
  /**
   * 이 줄이 말해야 하는 상태가 셋이고, 셋을 섞으면 안 된다:
   *   ① 상권 여럿에 걸침 → 전부 나열 (사장님 결정)
   *   ② 자료는 있는데 어느 경계에도 안 듦 → "없음" (정상 상태)
   *   ③ 그 지역에 상권 자료 자체가 없음 → "준비 중" (모른다는 뜻)
   * ②를 ③처럼 말하면 "모르는 것"을 "없다"고 단정하게 된다.
   */

  it('여러 상권에 걸치면 하나만 고르지 않고 전부 나열한다', async () => {
    responses.districts = {
      data: {
        covered: true,
        districts: [
          { name: '역삼역', type: '발달상권' },
          { name: '선릉역', type: '발달상권' },
        ],
        sources: ['서울특별시 상권분석서비스'],
      },
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/역삼역\(발달상권\)/)).toBeTruthy());
    expect(screen.getByText(/선릉역\(발달상권\)/)).toBeTruthy();
    // 공공누리 1유형(출처표시) 의무 — 상권을 보여줄 때 항상 함께 나가야 한다.
    expect(screen.getByText(/출처: 서울특별시 상권분석서비스/)).toBeTruthy();
  });

  it('출처는 화면이 지어내지 않고 서버가 준 목록을 그대로 적는다', async () => {
    // 소스가 둘인 지역(서울시 + 소진공)에서도 화면이 저절로 따라와야 한다.
    responses.districts = {
      data: {
        covered: true,
        districts: [{ name: '은행동', type: '주요상권' }],
        sources: ['서울특별시 상권분석서비스', '소상공인시장진흥공단'],
      },
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/은행동\(주요상권\)/)).toBeTruthy());
    expect(
      screen.getByText(/출처: 서울특별시 상권분석서비스 · 소상공인시장진흥공단/),
    ).toBeTruthy();
  });

  it('소스가 둘인 지역이어도 실제로 쓴 자료의 출처만 적는다', async () => {
    // 2026-08-14d 로 고친 구조 결함의 화면 쪽 몫이다. 서버가 "이 건물은 서울시 자료의
    // 상권 하나에 있다"고 답하면, 그 지역에 소진공 자료가 함께 있더라도 출처는 서울시
    // 하나여야 한다 — 안 쓴 자료를 덧붙이면 그건 출처표시가 아니라 지어낸 출처다.
    // (어느 출처가 나갈지 정하는 것은 서버 몫이고, 화면은 받은 것만 적는다는 계약을
    //  여기서 못 박는다. 화면이 목록을 늘리거나 줄이면 그 순간 이 테스트가 빨개진다.)
    responses.districts = {
      data: {
        covered: true,
        districts: [{ name: '역삼역', type: '발달상권' }],
        sources: ['서울특별시 상권분석서비스'],
      },
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/역삼역\(발달상권\)/)).toBeTruthy());
    expect(screen.getByText('출처: 서울특별시 상권분석서비스')).toBeTruthy();
    expect(screen.queryByText(/소상공인시장진흥공단/)).toBeNull();
  });

  it('출처 목록이 안 오면 출처 줄만 조용히 생략한다 (상권 이름은 그대로 보인다)', async () => {
    // 마이그레이션 전 라이브는 sources 키를 안 준다. 그때 '서울특별시…'를 지어내면
    // 대전 상권에까지 서울 출처가 붙는다 — 없으면 없는 대로 두는 게 맞다.
    responses.districts = {
      data: { covered: true, districts: [{ name: '역삼역', type: '발달상권' }] },
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/역삼역\(발달상권\)/)).toBeTruthy());
    // ⚠️ 화면에는 실거래 블록의 출처 줄도 있다(2026-08-15) — "출처:"라는 글자만 보고
    //    판정하면 이 테스트가 엉뚱한 줄을 잡는다. 상권 줄의 출처 조각만 콕 집어 본다.
    expect(container.querySelector('.stack__district-src')).toBeNull();
  });

  it('자료는 있는데 경계 밖이면 "없음"이라고 말한다 (출처는 그대로 붙인다)', async () => {
    // 경계 밖은 정상 상태다. 이 판정도 서울 자료를 읽어서 내린 것이므로 출처를 붙인다.
    responses.districts = {
      data: { covered: true, districts: [], sources: ['서울특별시 상권분석서비스'] },
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/어느 상권 경계에도 들지 않는/)).toBeTruthy());
    expect(screen.getByText(/출처: 서울특별시 상권분석서비스/)).toBeTruthy();
    expect(screen.queryByText(/준비되지 않았습니다/)).toBeNull();
  });

  it('경계 밖인데 출처 목록도 안 오면 "없음"만 말하고 출처는 지어내지 않는다', async () => {
    // 마이그레이션 전 라이브는 sources 키를 안 준다. 그때 '서울특별시…'를 채워 넣으면
    // 대전 건물에까지 서울 출처가 붙는다 — 판정("없음")은 그대로 말하되 출처는 비운다.
    responses.districts = { data: { covered: true, districts: [] }, error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/어느 상권 경계에도 들지 않는/)).toBeTruthy());
    // 실거래 블록의 출처 줄과 헷갈리지 않게 상권 줄의 출처 조각만 본다(위와 같은 이유).
    expect(container.querySelector('.stack__district-src')).toBeNull();
  });

  it('그 지역에 상권 자료가 없으면 "준비 중"이라고 말한다 (출처는 안 붙인다)', async () => {
    responses.districts = { data: { covered: false, districts: [] }, error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/아직 준비되지 않았습니다/)).toBeTruthy());
    // 서울 자료로 내린 판정이 아니므로 출처를 붙이면 안 된다.
    expect(screen.queryByText(/서울특별시 상권분석서비스/)).toBeNull();
    // "없음"(경계 밖)과 같은 말로 뭉뚱그리면 안 된다.
    expect(screen.queryByText(/어느 상권 경계에도 들지 않는/)).toBeNull();
  });

  it('조회에 실패하면 상권 줄을 아예 그리지 않는다 (본체는 정상)', async () => {
    // 못 읽었을 때 "없음"이라고 적으면 모르는 것을 아는 것처럼 말하게 된다.
    responses.districts = { data: null, error: { message: 'permission denied' } };
    render(<FloorStack building={building()} />);
    // ⚠️ '1층'은 실거래 층대 이름으로도 나온다(2026-08-15) — 여러 개여도 통과해야 한다.
    await waitFor(() => expect(screen.getAllByText('1층').length).toBeGreaterThan(0));
    expect(screen.queryByText(/속한 상권/)).toBeNull();
    expect(screen.queryByText(/서울특별시 상권분석서비스/)).toBeNull();
  });

  it('이름이 없는 상권도 빠뜨리지 않고 세어 보여준다', async () => {
    responses.districts = {
      data: { covered: true, districts: [{ name: null, type: null }] },
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/\(이름 없음\)/)).toBeTruthy());
  });
});

describe('FloorStack — 실거래 기록 (Stage A · 결정 0012)', () => {
  /**
   * Stage A 는 **추정이 0** 이다. 신고된 거래를 그대로 보여주거나 세기만 한다.
   * 그래서 여기서 지키는 것은 세 가지다:
   *   ① 있는 것만 말한다 (이력이 없으면 그 블록을 아예 안 그린다)
   *   ② 표본이 모자란 층대는 수치를 감춘다 (숫자 모양만 통계인 값을 화면에 안 낸다)
   *   ③ 금칙어("적정가격" 계열)가 한 글자도 없고, 이 블록 안에는 "시세"라는 말조차 없다
   *      (절대 규칙 2 — '참고 매매 시세'는 추정을 내는 아래 `.band` 섹션만 쓰는 말이다)
   */

  it('이 땅의 거래가 있으면 층·시점·면적·금액·단가·유형을 그대로 보여준다', async () => {
    responses.txs = { data: [tx()], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/이 땅에서 신고된 거래 1건/)).toBeTruthy());
    expect(screen.getByText('2026-05')).toBeTruthy();
    expect(screen.getByText('3억 2,000만')).toBeTruthy();
    expect(screen.getByText('㎡당 380만')).toBeTruthy();
    expect(screen.getByText('집합')).toBeTruthy();
  });

  it('서버 상한만큼 왔으면 "잘렸다"고 고지하고, 언제부터 보이는지도 함께 적는다', async () => {
    // ⚠️ 두 문구의 숫자는 **서버가 정본**이다(schema.sql 의 `limit 100` · `contract_ym >= '202401'`).
    //    화면은 supabase.ts 의 짝 상수를 쓰는데, 그 모듈은 이 파일이 통째로 흉내 낸다 —
    //    흉내에서 상수가 빠지면 `undefined` 가 되어 **잘림 고지가 조용히 사라진다**(조건이
    //    `txs.length >= undefined` 라 항상 거짓). 그 구멍을 여기서 막는다.
    responses.txs = { data: Array.from({ length: 100 }, () => tx()), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.tx__cap')).toBeTruthy());
    expect(container.querySelector('.tx__cap')?.textContent ?? '').toContain('100');
    expect(container.querySelector('.tx__note')?.textContent ?? '').toContain('2024년 1월');
  });

  it('거래가 있는 층에만 "거래 N건" 뱃지를 단다 (없는 층에 0건이라 적지 않는다)', async () => {
    // "거래 0건"이라고 적으면 "이 층은 안 팔린다"는 단정이 된다 — 실제로는 지번이 가려진
    // 거래·층이 빠진 거래가 그 밑에 깔려 있다.
    responses.floors = {
      data: [floor({ floor_no: 3 }), floor({ floor_no: 1 })],
      error: null,
    };
    responses.txs = { data: [tx({ floor_no: 3 }), tx({ floor_no: 3 })], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('거래 2건')).toBeTruthy());
    expect(screen.queryByText(/거래 0건/)).toBeNull();
  });

  it('층이 없는 거래는 뱃지로 세지 않되 목록에서는 "층 미상"으로 남긴다', async () => {
    // 2017년부터 국토부가 층을 빈 값으로 준다. 못 세는 것을 목록에서까지 지우면
    // 건수가 조용히 줄어든다.
    responses.txs = { data: [tx({ floor_no: null })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    // '층 미상'은 목록 한 줄과 아래 설명 문장 양쪽에 나온다.
    await waitFor(() => expect(container.querySelector('.tx__floor')?.textContent).toBe('층 미상'));
    // 층 뱃지는 어디에도 안 붙는다(붙일 층이 없다).
    expect(
      [...container.querySelectorAll('.floor__tx')].every((el) => el.textContent === ''),
    ).toBe(true);
    // 그래도 건수는 줄지 않는다 — 못 센 것을 목록에서까지 지우지 않는다.
    expect(screen.getByText(/이 땅에서 신고된 거래 1건/)).toBeTruthy();
  });

  it('이 땅의 거래가 없으면 그 블록을 아예 그리지 않는다 (구 단가는 그대로 나온다)', async () => {
    responses.txs = { data: [], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/강남구 층대별 거래 단가/)).toBeTruthy());
    expect(screen.queryByText(/이 땅에서 신고된 거래/)).toBeNull();
  });

  it('구 단가는 표본이 충분한 층대만 수치를 적는다', async () => {
    responses.txStats = { data: bands({ '1층': 213 }), error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/중앙값 ㎡당 2,250만/)).toBeTruthy());
    expect(screen.getByText(/가운데 절반 1,380만~3,730만/)).toBeTruthy();
    expect(screen.getByText('표본 213건')).toBeTruthy();
  });

  it('표본 5건 미만인 층대는 수치를 감추고 "표본 부족"만 적는다', async () => {
    // 검증 규칙의 미표시 원칙. 4건으로 낸 가운데값을 적으면 사람은 그걸 근거로 쓴다.
    responses.txStats = { data: bands({ '1층': 4, '2층': 5 }), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('표본 4건')).toBeTruthy());
    // 4건짜리는 수치가 없고, 5건짜리는 있다 — 경계가 정확히 5에서 갈려야 한다.
    // ⚠️ 참고 시세 밴드(Stage B)도 "표본 부족"이라는 같은 글자를 쓴다(2026-08-16) —
    //    화면 전체에서 세면 그쪽 줄까지 함께 잡힌다. 이 블록 안만 센다.
    expect(container.querySelectorAll('.tx__bands .tx__val--none')).toHaveLength(4);
    expect(screen.getAllByText(/중앙값 ㎡당/)).toHaveLength(1);
  });

  it('표본 0인 층대도 칸을 지우지 않는다 ("그 층은 아예 안 판다"로 읽히면 안 된다)', async () => {
    responses.txStats = { data: bands({ '1층': 213 }), error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('지하')).toBeTruthy());
    for (const band of ['지하', '2층', '3층이상', '층미상']) {
      expect(screen.getByText(band)).toBeTruthy();
    }
  });

  it('구 이름과 집계 시작 달은 화면이 지어내지 않고 서버가 준 값을 쓴다', async () => {
    responses.txStats = {
      data: bands({ '1층': 9 }).map((b) => ({
        ...b,
        sigungu_nm: '유성구',
        window_from: '202501',
      })),
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/유성구 층대별 거래 단가/)).toBeTruthy());
    expect(screen.getByText(/2025-01 이후 계약분/)).toBeTruthy();
    // ⚠️ '강남구'는 이 건물 주소에도 들어 있다 — 실거래 블록 안만 본다.
    expect(container.querySelector('.tx')?.textContent).not.toContain('강남구');
    // 기간을 글자로 박으면 창이 바뀌는 날 문구만 조용히 거짓말이 된다(밴드 출처 줄과 같은 가드).
    expect(container.querySelector('.tx__src')?.textContent ?? '').not.toContain('24개월');
  });

  it('구 코드는 pnu 앞 5자리로 서버에 보낸다', async () => {
    render(<FloorStack building={building({ pnu: '3020010600100010000' })} />);
    await waitFor(() => expect(screen.getByText(/층대별 거래 단가/)).toBeTruthy());
    const call = rpcCalls.find((c) => c.fn === 'get_sigungu_tx_stats');
    expect(call?.args).toEqual({ sigungu: '30200' });
  });

  it('출처(국토교통부)와 A등급 배지를 항상 함께 보여준다', async () => {
    // 절대 규칙 3 — 근거 레벨 + 표본 수 병기.
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/A등급 · 실거래/)).toBeTruthy());
    expect(screen.getByText(/국토교통부 상업업무용 부동산 매매 실거래가/)).toBeTruthy();
    expect(screen.getByText(/전체 표본 213건/)).toBeTruthy();
  });

  it('조회에 실패하면 실거래 섹션을 아예 그리지 않는다 (본체는 정상)', async () => {
    // 못 읽었을 때 "거래 없음"이라고 적으면 모르는 것을 아는 것처럼 말하게 된다.
    responses.txs = { data: null, error: { message: 'permission denied' } };
    responses.txStats = { data: null, error: { message: 'permission denied' } };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('1층')).toBeTruthy());
    expect(screen.queryByText(/실거래 기록/)).toBeNull();
    expect(screen.queryByText(/permission denied/)).toBeNull();
  });

  it('금칙어("적정가격" 계열)가 화면에 한 글자도 없다', async () => {
    // 절대 규칙 2. '참고 시세'는 허용 대체어라 금칙어 목록에 넣지 않는다 — 대신 아래에서
    // "Stage A 블록 안에는 그 말조차 없다"를 따로 못 박는다.
    responses.txs = { data: [tx()], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/실거래 기록/)).toBeTruthy());
    const text = container.textContent ?? '';
    for (const banned of ['적정가격', '적정가', '평가액', '감정가', '가치평가']) {
      expect(text.includes(banned)).toBe(false);
    }
  });

  it('Stage A 블록 안에는 "시세"라는 말이 없다 (사실과 추정을 어휘로도 가른다)', async () => {
    // 추정을 내는 것은 아래 `.band` 섹션뿐이다. 이 블록이 그 말을 쓰기 시작하면
    // 신고된 사실과 어림한 값의 경계가 문구에서부터 흐려진다.
    responses.txs = { data: [tx()], error: null };
    responses.bands = { data: priceBands(), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/실거래 기록/)).toBeTruthy());
    expect(container.querySelector('.tx')?.textContent).not.toContain('시세');
  });
});

describe('FloorStack — 참고 매매 시세 (Stage B · 결정 0013)', () => {
  /**
   * 이 섹션은 이 화면에서 **추정값이 나오는 유일한 자리**다. 그래서 지키는 것이 넷이다:
   *   ① 값과 근거는 한 몸이다 (근거 단계·표본 수 없이 숫자만 내지 않는다 — 절대 규칙 3)
   *   ② 안 내는 이유 넷을 절대 같은 말로 뭉뚱그리지 않는다 (모름 ≠ 없음 ≠ 방침)
   *   ③ 같은 값을 층마다 뿌려 "층마다 따로 쟀다"는 착시를 주지 않는다
   *   ④ 사실(A등급)과 추정(C등급)이 눈으로 갈라 보인다
   */

  /** 이 건물의 층을 서버가 주는 순서(내림차순)로 만든다. */
  function floorsDesc(...floorNos: number[]) {
    return { data: floorNos.map((no) => floor({ floor_no: no })), error: null };
  }

  it('구가 기준선을 못 넘으면 층 나열 없이 한 문단만 낸다', async () => {
    responses.bands = { data: priceBandGate(), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() =>
      expect(screen.getByText(/구 전체는 아직 참고 시세를 내지 않습니다/)).toBeTruthy(),
    );
    expect(container.querySelectorAll('.band__row')).toHaveLength(0);
  });

  it('기준선 안내는 "떨어졌다"고 단정하지 않고 오차율·구 개수도 적지 않는다', async () => {
    // 서버는 판정이 **아예 없는 구**도 같은 값으로 준다(`if v_gate is not true`) —
    // 낙방으로 단정하면 사실이 아닌 말을 하게 된다. 통과 구 목록·수치는 서버가 정본이라
    // 화면에 복사하지 않는다(결정 0013 §4).
    responses.bands = { data: priceBandGate(), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__gate')).toBeTruthy());
    const text = container.querySelector('.band__gate')?.textContent ?? '';
    expect(text).toContain('아직 시험을 보지 않았거나');
    expect(text).not.toContain('표본 부족');
    expect(text).not.toContain('%');
  });

  it('기준선 안내에는 C등급 배지도 출처도 붙이지 않는다 (계산한 것이 없다)', async () => {
    responses.bands = { data: priceBandGate(), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__gate')).toBeTruthy());
    const band = container.querySelector('.band');
    expect(band?.textContent).not.toContain('C등급');
    expect(band?.querySelector('.band__src')).toBeNull();
  });

  it('값을 낼 때는 총액·㎡당·가운데값·근거 단계·표본 수를 한 줄에 함께 낸다', async () => {
    // 절대 규칙 3 — 근거 레벨 + 표본 수 병기. 숫자만 떼어 내보내지 않는다.
    responses.floors = floorsDesc(2);
    responses.bands = { data: [priceBand({ floor_no: 2 })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__val')).toBeTruthy());
    expect(container.querySelector('.band__val')?.textContent).toBe(
      '비슷한 호실 한 칸 32.8㎡ (10평) 기준 2.4억~6.2억',
    );
    const sub = container.querySelector('.band__sub')?.textContent ?? '';
    expect(sub).toContain('㎡당 747만~1,905만');
    expect(sub).toContain('가운데값 ㎡당 1,627만');
    expect(sub).toContain('근거: 500m 안 같은 층');
    expect(sub).toContain('거래 15건');
  });

  it('총액 앞에 주어가 붙어 "이 층 값"으로 읽히지 않는다', async () => {
    // median_area_m2 는 곁 거래들의 면적 중앙값이지 이 층 면적이 아니다. 층 목록의
    // 300㎡(층 전체 연면적)와 나란히 두면 9배 오독이 난다.
    responses.floors = floorsDesc(2);
    responses.bands = { data: [priceBand({ floor_no: 2 })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__val')).toBeTruthy());
    expect(container.querySelector('.band__val')?.textContent).toContain('비슷한 호실 한 칸');
    expect(container.textContent ?? '').not.toContain('이 층 32.8');
  });

  it('환산할 면적이 없으면 총액을 지어내지 않고 ㎡당만 낸다', async () => {
    responses.floors = floorsDesc(2);
    responses.bands = { data: [priceBand({ floor_no: 2, median_area_m2: null })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__val')).toBeTruthy());
    const val = container.querySelector('.band__val')?.textContent ?? '';
    expect(val).toBe('㎡당 747만~1,905만');
    expect(val).not.toContain('억');
    expect(val).not.toContain('—');
  });

  it('곁 거래가 한 건뿐이면 밴드가 아니라 사실로 적는다', async () => {
    // 사분위 셋이 같은 값이면 '2.4억~2.4억'이 되는데, 사람은 그걸 "아주 정확하다"로
    // 읽는다. 사실은 거래 한 건을 그대로 베낀 값이다.
    responses.floors = floorsDesc(3);
    responses.bands = {
      data: [
        priceBand({
          floor_no: 3,
          stage: 'L6',
          n: 1,
          p25: 16_265_452.18,
          p75: 16_265_452.18,
        }),
      ],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__val')).toBeTruthy());
    const val = container.querySelector('.band__val')?.textContent ?? '';
    expect(val).toContain('곁의 거래 1건뿐');
    expect(val).not.toContain('~');
    expect(container.querySelector('.band__sub')?.textContent).toContain('5.3억 안팎');
  });

  it('여러 건이 모두 같은 값이라 폭이 0일 때 "1건뿐"이라 말하지 않는다', async () => {
    // 폭이 0인 까닭은 둘이다 — 한 건뿐이거나, 여러 건이 전부 같은 단가로 신고됐거나.
    // 둘을 한 문장으로 뭉뚱그리면 "1건뿐"이라 적어 놓고 바로 밑에서 "거래 4건"이라 말하는
    // 자기모순이 난다(라이브에 n=10·n=6·n=5 사례가 실제로 있다).
    responses.floors = floorsDesc(2);
    responses.bands = {
      data: [
        priceBand({
          floor_no: 2,
          stage: 'L2',
          n: 4,
          p25: 16_265_452.18,
          p75: 16_265_452.18,
        }),
      ],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__val')).toBeTruthy());
    const val = container.querySelector('.band__val')?.textContent ?? '';
    expect(val).not.toContain('1건뿐');
    expect(val).toContain('곁 거래 4건이 모두 같은 값');
    expect(val).not.toContain('~'); // 폭 0을 '2.4억~2.4억'으로 적지는 않는다
    const sub = container.querySelector('.band__sub')?.textContent ?? '';
    expect(sub).toContain('거래 4건');
    expect(sub).toContain('표본 적음');
    // 표식을 붙였으면 그 뜻을 설명하는 각주도 따라와야 한다(둘 중 하나만 나오면 미아가 된다).
    expect(container.querySelector('.band__why')?.textContent).toContain(
      '곁 거래가 다섯 건이 안 된다는 뜻',
    );
  });

  it('L6은 "이 동네 층대 평균"임을 라벨과 문구가 함께 말한다', async () => {
    // 사다리의 마지막 칸은 층이 아니라 **층대**로 잰 값이다 — 라벨만 읽고도 알아야 한다.
    responses.floors = floorsDesc(5);
    responses.bands = { data: [priceBand({ floor_no: 5, stage: 'L6' })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__sub')).toBeTruthy());
    const sub = container.querySelector('.band__sub')?.textContent ?? '';
    expect(sub).toContain('이 동네(법정동) 3층 이상 평균');
    expect(sub).toContain('층별로 따로 잰 값이 아닙니다');
  });

  it('먼 근거(L5·L6)에는 표식과 그 뜻을 설명하는 각주가 함께 나온다', async () => {
    responses.floors = floorsDesc(2);
    responses.bands = { data: [priceBand({ floor_no: 2, stage: 'L5' })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__sub')).toBeTruthy());
    expect(container.querySelector('.band__sub')?.textContent).toContain('먼 근거');
    expect(container.querySelector('.band__why')?.textContent).toContain(
      '이 땅에서 멀리 떨어진 거래로 어림했다는 뜻',
    );
  });

  it('가까운 근거(L2·L4)에는 "먼 근거" 표식을 붙이지 않는다', async () => {
    responses.floors = floorsDesc(2);
    responses.bands = { data: [priceBand({ floor_no: 2, stage: 'L2', n: 6 })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__sub')).toBeTruthy());
    expect(container.querySelector('.band')?.textContent).not.toContain('먼 근거');
    expect(container.querySelector('.band__sub')?.textContent).toContain('이 땅 같은 층');
  });

  it('곁 거래가 다섯 건이 안 되면 "표본 적음" 표식이 붙는다 (경계는 정확히 5)', async () => {
    responses.floors = floorsDesc(4, 2);
    responses.bands = {
      data: [
        priceBand({ floor_no: 2, stage: 'L4', n: 5 }),
        priceBand({ floor_no: 4, stage: 'L4', n: 4 }),
      ],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.band__sub')).toHaveLength(2));
    const subs = [...container.querySelectorAll('.band__sub')].map((el) => el.textContent ?? '');
    expect(subs[0]).toContain('표본 적음'); // 4건 (위가 4층)
    expect(subs[1]).not.toContain('표본 적음'); // 5건
    expect(container.querySelector('.band__why')?.textContent).toContain(
      '곁 거래가 다섯 건이 안 된다는 뜻',
    );
  });

  it('모르는 근거 단계면 값을 내지 않는다 (근거를 못 적으면 값도 못 낸다)', async () => {
    responses.floors = floorsDesc(2);
    responses.bands = { data: [priceBand({ floor_no: 2, stage: 'L9' })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__none')).toBeTruthy());
    expect(container.querySelector('.band__none')?.textContent).toContain('근거를 표시할 수 없어');
    expect(container.querySelector('.band__val')).toBeNull();
  });

  it('1층은 값 대신 정직 문구를 적고 그 줄에 "표본"이라는 말이 없다', async () => {
    // 자료가 모자란 게 아니라 자리(코너·골목)를 모르는 것이다 — 다른 이유는 다른 말로.
    responses.floors = floorsDesc(1);
    responses.bands = {
      data: [priceBand({ floor_no: 1, status: 'floor_1f', ...NO_VALUE })],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__none')).toBeTruthy());
    const none = container.querySelector('.band__none')?.textContent ?? '';
    expect(none).toContain('1층은 내지 않습니다');
    expect(none).not.toContain('표본');
  });

  it('지하·옥탑은 줄로 반복하지 않고 각주에서 층 이름을 모아 한 번만 말한다', async () => {
    responses.floors = floorsDesc(99, 2, -1);
    responses.bands = {
      data: [
        priceBand({ floor_no: -1, status: 'no_evidence', ...NO_VALUE }),
        priceBand({ floor_no: 2 }),
        priceBand({ floor_no: 99, status: 'no_evidence', ...NO_VALUE }),
      ],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__none-note')).toBeTruthy());
    expect(container.querySelectorAll('.band__none-note')).toHaveLength(1);
    expect(container.querySelectorAll('.band__row')).toHaveLength(1); // 값이 있는 2층 하나뿐
    expect(container.querySelector('.band__none-note')?.textContent).toContain(
      '참고 시세를 내지 않은 층: 옥탑 · 지하 1층',
    );
  });

  it('근거가 아예 없는 층에는 "표본 부족"이라 적지 않는다 (결정 0001)', async () => {
    // "조금만 더 모으면 나오나?"라는 오해를 만든다 — 쌓여도 안 나오는 층이다.
    responses.floors = floorsDesc(-1);
    responses.bands = {
      data: [priceBand({ floor_no: -1, status: 'no_evidence', ...NO_VALUE })],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__none-note')).toBeTruthy());
    const note = container.querySelector('.band__none-note')?.textContent ?? '';
    expect(note).toContain('검증한 적이 없습니다');
    expect(note).toContain('원래 자료에 없는 것');
    expect(note).not.toContain('표본 부족');
    // 지하가 섞였을 때는 층 표기가 안 오는 사실도 함께 적는다.
    expect(note).toContain('2017년부터');
  });

  it('곁 거래를 못 찾은 층은 "쌓이면 나온다"고 말한다 (근거 없음과 다른 말이다)', async () => {
    responses.floors = floorsDesc(3);
    responses.bands = {
      data: [priceBand({ floor_no: 3, status: 'no_estimate', ...NO_VALUE })],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__none')).toBeTruthy());
    const none = container.querySelector('.band__none')?.textContent ?? '';
    expect(none).toContain('표본 부족');
    expect(none).toContain('거래가 쌓이면 나올 수 있습니다');
  });

  it('C등급 배지가 값과 함께 나오고 A등급과 다른 모양을 쓴다', async () => {
    // 상세계획 §7.4 — A와 C가 같은 모양이면 같은 무게로 읽힌다. 색은 어떤 테스트도
    // 보지 못하므로 클래스 유무로 못 박는다.
    responses.floors = floorsDesc(2);
    responses.bands = { data: [priceBand({ floor_no: 2 })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/C등급 · 파생 추정/)).toBeTruthy());
    const badge = container.querySelector('.band .grade__badge');
    expect(badge?.className).toContain('grade__badge--est');
  });

  it('출처와 집계 시작 달은 화면이 지어내지 않고 서버가 준 값을 쓴다', async () => {
    responses.floors = floorsDesc(2);
    responses.bands = { data: [priceBand({ floor_no: 2, window_from: '202501' })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__src')).toBeTruthy());
    const src = container.querySelector('.band__src')?.textContent ?? '';
    expect(src).toContain('국토교통부 상업업무용 부동산 매매 실거래가');
    expect(src).toContain('2025-01 이후 계약분');
    // 기간을 글자로 박으면 창이 바뀌는 날 문구만 조용히 거짓말이 된다.
    expect(src).not.toContain('24개월');
  });

  it('pnu 를 p_pnu 라는 이름으로 보낸다 (라이브 전용 오류를 막는 유일한 가드)', async () => {
    // 형제 함수는 bld_id·pnu·sigungu 인데 이 함수만 p_pnu 다. 목은 인자 이름을 안 보므로
    // 여기서 안 잡으면 테스트는 전부 초록인 채 라이브에서만 PGRST202 가 난다.
    render(<FloorStack building={building({ pnu: '3020010600100010000' })} />);
    await waitFor(() => expect(screen.getByText(/층대별 거래 단가/)).toBeTruthy());
    const call = rpcCalls.find((c) => c.fn === 'list_price_bands');
    expect(call?.args).toEqual({ p_pnu: '3020010600100010000' });
  });

  it('서버가 오름차순으로 줘도 고층부터 그리고, 이 건물에 없는 층은 안 그린다', async () => {
    // 서버는 **필지** 전체의 층을 오름차순으로 준다 — 인덱스로 맞추면 층이 뒤집히고
    // 복수동 필지에서는 옆 동 층까지 샌다.
    responses.floors = floorsDesc(3, 2);
    responses.bands = {
      data: [
        priceBand({ floor_no: 2, stage: 'L5', n: 15 }),
        priceBand({ floor_no: 3, stage: 'L4', n: 6 }),
        priceBand({ floor_no: 7, stage: 'L5', n: 9 }), // 옆 동 층
      ],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.band__row')).toHaveLength(2));
    const labels = [...container.querySelectorAll('.band__floor')].map((el) => el.textContent);
    expect(labels).toEqual(['3층', '2층']);
    expect(container.querySelector('.band')?.textContent).not.toContain('7층');
  });

  it('값이 같은 연속한 층은 한 줄로 묶어 범위로 적는다', async () => {
    // 사다리의 마지막 칸은 층대별로 한 번만 계산되므로 3층 이상 전체가 같은 값이다.
    // 층마다 한 줄씩 뿌리면 "층마다 따로 계산했다"는 착시를 준다(라이브 실측).
    responses.floors = floorsDesc(5, 4, 3, 2);
    responses.bands = {
      data: [
        priceBand({ floor_no: 2, stage: 'L5', n: 15 }),
        priceBand({ floor_no: 3, stage: 'L6', n: 8 }),
        priceBand({ floor_no: 4, stage: 'L6', n: 8 }),
        priceBand({ floor_no: 5, stage: 'L6', n: 8 }),
      ],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.band__row')).toHaveLength(2));
    const labels = [...container.querySelectorAll('.band__floor')].map((el) => el.textContent);
    expect(labels).toEqual(['3층~5층', '2층']);
  });

  it('밴드 줄을 누르면 그 층이 펼쳐지고 줄에 표시가 붙는다', async () => {
    responses.floors = floorsDesc(2);
    responses.bands = { data: [priceBand({ floor_no: 2 })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__hit')).toBeTruthy());
    expect(container.querySelector('.detail')).toBeNull();

    fireEvent.click(container.querySelector('.band__hit')!);

    expect(container.querySelector('.detail')).toBeTruthy();
    expect(container.querySelector('.band__row')?.className).toContain('band__row--on');
  });

  it('조회에 실패하면 섹션을 아예 그리지 않는다 (본체는 정상)', async () => {
    // 못 읽었을 때 "참고 시세 없음"이라고 적으면 모르는 것을 아는 것처럼 말하게 된다.
    responses.bands = { data: null, error: { message: 'permission denied' } };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/층대별 거래 단가/)).toBeTruthy());
    expect(container.querySelector('.band')).toBeNull();
    expect(container.textContent ?? '').not.toContain('permission denied');
  });

  it('아직 안 왔으면 자리를 잡아 두고 "불러오는 중"이라고 말한다 (모름 ≠ 없음)', async () => {
    responses.bandsPending = true;
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/층대별 거래 단가/)).toBeTruthy());
    expect(container.querySelector('.band--wait')).toBeTruthy();
    expect(container.querySelector('.band--wait')?.textContent).toContain('불러오는 중');
  });

  it('옥탑 층에도 지하와 같은 표시를 붙인다 (근거 없는 층이라는 뜻)', async () => {
    responses.floors = floorsDesc(99, 1, -1);
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor')).toHaveLength(3));
    expect(container.querySelector('.floor--roof')).toBeTruthy();
    expect(container.querySelector('.floor--under')).toBeTruthy();
  });

  it('값이 나가는 상태에서도 금칙어 5종이 한 글자도 없다', async () => {
    responses.floors = floorsDesc(99, 3, 2, 1, -1);
    responses.txs = { data: [tx()], error: null };
    responses.bands = { data: priceBands(), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__val')).toBeTruthy());
    const text = container.textContent ?? '';
    for (const banned of ['적정가격', '적정가', '평가액', '감정가', '가치평가']) {
      expect(text.includes(banned)).toBe(false);
    }
  });

  it('값을 못 내는 층이 있으면 대신 볼 수 있는 곳을 이름으로 가리킨다', async () => {
    // "아래" 같은 위치 지시어를 쓰면, 그 블록이 조회 실패로 사라진 날 화면이 없는 곳을
    // 가리키게 된다.
    responses.floors = floorsDesc(3, 2, 1);
    responses.bands = { data: priceBands(), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.band__alt')).toBeTruthy());
    const alt = container.querySelector('.band__alt')?.textContent ?? '';
    expect(alt).toContain('층대별 거래 단가');
    expect(alt).not.toContain('아래');
  });
});
