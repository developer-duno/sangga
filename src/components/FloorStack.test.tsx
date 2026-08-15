import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import type {
  BuildingHit,
  CoverageStats,
  FloorRow,
  ParcelTransaction,
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
};

/** 마지막 rpc 호출의 인자. "구 코드를 pnu 에서 뽑아 보내는가"를 여기서 확인한다. */
const rpcCalls: Array<{ fn: string; args: unknown }> = [];

vi.mock('../lib/supabase', () => ({
  FLOOR_STACK_VIEW: 'v_floor_stack',
  COVERAGE_STATS_VIEW: 'v_coverage_stats',
  BUILDING_DISTRICTS_FN: 'list_building_districts',
  PARCEL_TX_FN: 'list_parcel_transactions',
  SIGUNGU_TX_STATS_FN: 'get_sigungu_tx_stats',
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
   *   ③ 금칙어("적정가격"·"시세" 계열)가 한 글자도 없다 (절대 규칙 2)
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
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('표본 4건')).toBeTruthy());
    // 4건짜리는 수치가 없고, 5건짜리는 있다 — 경계가 정확히 5에서 갈려야 한다.
    expect(screen.getAllByText('표본 부족')).toHaveLength(4); // 지하·1층·3층이상·층미상
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

  it('금칙어("적정가격"·"시세" 계열)가 화면에 한 글자도 없다', async () => {
    // 절대 규칙 2. Stage A 는 추정이 아니므로 "시세"라는 말도 쓰지 않는다.
    responses.txs = { data: [tx()], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/실거래 기록/)).toBeTruthy());
    const text = container.textContent ?? '';
    for (const banned of ['적정가격', '적정가', '평가액', '감정가', '가치평가', '시세']) {
      expect(text.includes(banned)).toBe(false);
    }
  });
});
