import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
import {
  SECTION_EXPAND_BUDGET,
  SECTION_PLAN,
  VIEWER_ROLES,
  type ViewerRole,
} from '../lib/sectionCards';
import type {
  BasePrice,
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
  /**
   * 서버 함수 list_base_prices 의 응답(층별 국세청 기준시가).
   *
   * 기본값은 **빈 배열** = 그 줄 미표시라 이 파일의 다른 시험들이 영향을 안 받는다.
   */
  basePrices: { data: [] as unknown, error: null as unknown },
  /**
   * 서버 함수 list_industry_mix 의 응답(둘레의 업종 분포 · 결정 0014).
   *
   * 기본값을 **오류**로 둔다 — 이 파일은 층 스택을 보는 곳이고, 업종 섹션은
   * `IndustryMixSection.test.tsx` 가 따로 본다. 오류면 섹션이 스스로 사라지므로
   * 여기 있는 다른 시험들의 화면이 그대로 유지된다(마이그레이션 적용 전 라이브와 같은 상태).
   */
  industryMix: { data: null as unknown, error: { message: 'not applied' } as unknown },
  /**
   * 서버 함수 list_rent_stats 의 응답(상권 임대 동향 · 결정 0024).
   *
   * 기본값을 **오류**로 둔다(업종 분포와 같은 이유) — 이 파일은 층 스택을 보는 곳이고
   * 그 카드는 `RentStatSection.test.tsx` 가 따로 본다. 오류면 카드가 스스로 사라지므로
   * 여기 있는 다른 시험들의 화면(카드 다섯 장)이 그대로 유지된다.
   */
  rent: { data: null as unknown, error: { message: 'not applied' } as unknown },
  /**
   * 서버 함수 list_district_openclose 의 응답(상권 개업·폐업 · 결정 0033).
   * 기본값을 **오류**로 둔다(임대 동향과 같은 이유) — 그 카드는 `OpenCloseSection.test.tsx` 가 본다.
   */
  openclose: { data: null as unknown, error: { message: 'not applied' } as unknown },
  /**
   * 서버 함수 list_unit_floor_summary 의 응답(호실 구성표 · 결정 0032).
   *
   * 기본값을 **함수 없음(PGRST202)** 으로 둔다 — 그러면 요약 줄도 "자료 없음" 안내도 안 서서
   * 이 파일의 다른 시험들이 보던 화면이 그대로다. 호실을 보는 시험만 덮어쓴다.
   */
  unitSummary: {
    data: null as unknown,
    error: { code: 'PGRST202', message: 'function does not exist' } as unknown,
  },
  /**
   * 서버 함수 list_floor_units 의 응답. 인자(쪽)를 보고 답하도록 함수로 둔다.
   * ⓘ 프라미스를 돌려주면 그대로 따른다 — 영영 안 끝나는 프라미스로 "받는 중" 상태를 붙잡는다.
   */
  floorUnits: (() => ({ data: [] as unknown, error: null as unknown })) as (
    args: Record<string, unknown>,
  ) => { data: unknown; error: unknown } | Promise<never>,
  /**
   * 서버 함수 get_parcel_land_price 의 응답(개별공시지가 한 줄 · 결정 0036 결정 7).
   * 기본값을 **함수 없음(PGRST202)** 으로 둔다 — 줄이 안 서서 다른 시험의 머리 모양이 그대로다.
   * ⓘ 함수로 두면 인자(pnu)를 보고 답한다 — 늦게 온 옛 답 시험이 쓴다.
   */
  landPrice: (() => ({
    data: null as unknown,
    error: { code: 'PGRST202', message: 'function does not exist' } as unknown,
  })) as (args: Record<string, unknown>) => { data: unknown; error: unknown } | Promise<unknown>,
};

/** 마지막 rpc 호출의 인자. "구 코드를 pnu 에서 뽑아 보내는가"를 여기서 확인한다. */
const rpcCalls: Array<{ fn: string; args: unknown }> = [];

// 흉내 낼 것은 **키를 요구하는 클라이언트 하나뿐**이다. 표·함수 이름과 짝수(數)는
// 아무 일도 안 하는 `lib/appConstants.ts` 에 있어 화면이 진짜 값을 그대로 쓴다 —
// 그래서 상수를 더해도 여기를 같이 고칠 일이 없다(예전에는 흉내가 모듈을 통째로
// 갈아끼워서, 여기 안 적은 상수는 화면이 undefined 로 그렸다).
vi.mock('../lib/supabase', () => ({
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
      // 국세청 기준시가. 갈라 답하지 않으면 상권 응답(객체)이 흘러들어 "배열인가" 검사에
      // 걸려 늘 미표시가 된다 — 그러면 이 아래 시험들이 통째로 헛돈다.
      if (fn === 'list_base_prices') return Promise.resolve(responses.basePrices);
      // 둘레의 업종 분포. 갈라 답하지 않으면 상권 응답(객체)이 흘러들어 업종 목록을
      // 도는 코드가 죽는다 — 이 파일의 다른 시험까지 통째로 빨개진다.
      if (fn === 'list_industry_mix' || fn === 'list_industry_detail') {
        return Promise.resolve(responses.industryMix);
      }
      // 둘레의 인허가 한 줄(업종 분포 카드 안). 이 파일에서는 그 카드 자체가 사라진
      // 상태를 보므로 늘 **함수 없음**으로 답한다 — 갈라 답하지 않으면 상권 응답(객체)이
      // 흘러들어, 그 줄이 왜 안 뜨는지가 흐려진다.
      if (fn === 'count_nearby_permits') {
        return Promise.resolve({ data: null, error: { message: 'not applied' } });
      }
      // 상권 임대 동향(결정 0024). 갈라 답하지 않으면 상권 응답(객체)이 흘러들어 모양
      // 검사에 걸리고, 그러면 이 카드가 **왜** 안 뜨는지가 흐려진다(늘 미표시로 굳는다).
      if (fn === 'list_rent_stats') return Promise.resolve(responses.rent);
      // 상권 개업·폐업(결정 0033). 같은 이유로 갈라 답한다.
      if (fn === 'list_district_openclose') return Promise.resolve(responses.openclose);
      // 호실 구성표(결정 0032). 갈라 답하지 않으면 상권 응답(객체)이 흘러들어 "배열인가" 검사에
      // 걸려 늘 실패로 굳는다 — 그러면 요약·목록 시험이 통째로 헛돈다(거짓 초록).
      if (fn === 'list_unit_floor_summary') return Promise.resolve(responses.unitSummary);
      if (fn === 'list_floor_units') {
        return Promise.resolve(responses.floorUnits((args ?? {}) as Record<string, unknown>));
      }
      // 개별공시지가 한 줄(결정 0036 결정 7). 갈라 답하지 않으면 상권 응답(객체)이 흘러들어
      // 늘 '모양 이상 → 줄 없음'으로 굳는다(거짓 초록).
      if (fn === 'get_parcel_land_price') {
        return Promise.resolve(responses.landPrice((args ?? {}) as Record<string, unknown>));
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
    // 건물 스펙 4칸(2026-08-24a). 기본값은 넷 다 값이 있는 정상 건물 —
    // 0(=대장 미기재)·상한 초과는 그것을 보려는 시험에서만 덮어쓴다.
    total_area_m2: 1234.5,
    far: 350.5,
    bcr: 59.9,
    parking_cnt: 12,
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

/** 국세청 기준시가 한 줄(함수 list_base_prices). */
function basePrice(over: Partial<BasePrice> = {}): BasePrice {
  return {
    floor_no: 2,
    median_price_per_m2: 3_000_000,
    ho_cnt: 12,
    notice_date: '2026-01-01',
    ...over,
  };
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
  // 기본은 빈 배열 = 기준시가 줄 미표시. 이 파일의 다른 테스트는 영향을 안 받는다.
  responses.basePrices = { data: [], error: null };
  // 기본은 오류 = 업종 섹션 미표시(마이그레이션 적용 전 라이브와 같은 상태).
  // 그 섹션 자체는 IndustryMixSection.test.tsx 가 따로 본다.
  responses.industryMix = { data: null, error: { message: 'not applied' } };
  // 기본은 오류 = 임대 동향 카드 미표시(마이그레이션 적용 전 라이브와 같은 상태).
  // 그 카드 자체는 RentStatSection.test.tsx 가 따로 본다.
  responses.rent = { data: null, error: { message: 'not applied' } };
  // 기본은 오류 = 개업·폐업 카드 미표시. 그 카드 자체는 OpenCloseSection.test.tsx 가 본다.
  responses.openclose = { data: null, error: { message: 'not applied' } };
  // 기본은 함수 없음 = 호실 요약·안내 미표시(위 주석). 호실 시험만 덮어쓴다.
  responses.unitSummary = {
    data: null,
    error: { code: 'PGRST202', message: 'function does not exist' },
  };
  responses.floorUnits = () => ({ data: [], error: null });
  // 기본은 함수 없음 = 개별공시지가 줄 미표시. 그 줄을 보는 시험만 덮어쓴다.
  responses.landPrice = () => ({
    data: null,
    error: { code: 'PGRST202', message: 'function does not exist' },
  });
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
    const { container } = render(<FloorStack building={building()} />);
    // 층 이름은 층별 공표값 카드(물결 1-C2)의 줄 머리에도 나온다 — 층 목록 카드 안으로 좁혀 본다.
    await waitFor(() => expect(container.querySelector('.card--floors .floor__label')?.textContent).toBe('지하 1층'));
  });

  it('한 땅에 여러 동이 있으면 점포가 섞일 수 있다고 경고한다', async () => {
    responses.floors = { data: [floor({ bld_cnt_in_pnu: 3 })], error: null };
    render(<FloorStack building={building({ bld_cnt_in_pnu: 3 })} />);
    await waitFor(() => expect(screen.getByText(/이 땅에 건물이 3동 있습니다/)).toBeTruthy());
  });

  describe('내부 링크 줄 · h1 (결정 0042 H1·H5)', () => {
    const dong = (bld_id: string, dong_nm: string | null, bld_nm: string | null = '테스트빌딩') => ({
      bld_id,
      bld_nm,
      dong_nm,
      total_area_m2: 100,
      floor_cnt: 2,
      min_floor: 1,
      max_floor: 2,
      has_roof: false,
    });
    const DONGS = [dong('1168010100-1', 'A동'), dong('1168010100-2', 'B동'), dong('1168010100-3', null, null)];

    it('건물 이름이 h1(하나)', async () => {
      render(<FloorStack building={building()} />);
      const h1 = await screen.findByRole('heading', { level: 1 });
      expect(h1.textContent).toBe('테스트빌딩');
      expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    });

    it('★ 같은 땅 여러 동 — 「같은 땅 다른 동: …」(자기는 뺀다 · 이름 + 동 구분) + 「○○구 다른 건물 찾기」 · 진짜 href', async () => {
      responses.floors = { data: [floor({ bld_cnt_in_pnu: 3 })], error: null };
      const { container } = render(
        <FloorStack building={building({ bld_cnt_in_pnu: 3 })} dongs={DONGS} sigunguName="강남구" />,
      );
      // 보완 F3 — 렌더 h1 에도 동 구분(첫 HTML h1·탭 제목과 같은 글).
      await screen.findByRole('heading', { level: 1, name: '테스트빌딩 A동' });
      const nav = container.querySelector('header.stack__head nav.stack__links')!;
      expect(nav.getAttribute('aria-label')).toBe('관련 페이지');
      expect([...nav.querySelectorAll('a')].map((a) => [a.getAttribute('href'), a.textContent])).toEqual([
        ['/?sgg=11680&bld=1168010100-2', '테스트빌딩 B동'],
        ['/?sgg=11680&bld=1168010100-3', '(같은 땅 3동 중 3번째)'],
        ['/?sgg=11680', '강남구 다른 건물 찾기'],
      ]);
      expect(nav.querySelector('.stack__links-row')!.textContent).toBe(
        '같은 땅 다른 동: 테스트빌딩 B동 · (같은 땅 3동 중 3번째)',
      );
    });

    it('★ 보통 누름 = 화면 안에서 그 동으로(땅 칸은 지금 건물 · 동 칸은 목록) / 구 찾기 · Ctrl 누름은 그대로 링크', async () => {
      const onSelectBuilding = vi.fn();
      const onFindInSigungu = vi.fn();
      responses.floors = { data: [floor({ bld_cnt_in_pnu: 3 })], error: null };
      render(
        <FloorStack
          building={building({ bld_cnt_in_pnu: 3, lat: 37.5, lng: 127 })}
          dongs={DONGS}
          sigunguName="강남구"
          onSelectBuilding={onSelectBuilding}
          onFindInSigungu={onFindInSigungu}
        />,
      );
      const b = await screen.findByRole('link', { name: '테스트빌딩 B동' });
      expect(fireEvent.click(b, { ctrlKey: true })).toBe(true);
      expect(onSelectBuilding).not.toHaveBeenCalled();
      expect(fireEvent.click(b)).toBe(false);
      expect(onSelectBuilding).toHaveBeenCalledWith({
        bld_id: '1168010100-2',
        pnu: '1168010100100010000',
        bld_nm: '테스트빌딩',
        road_addr: '서울 강남구 테헤란로 1',
        jibun_addr: undefined,
        lat: 37.5,
        lng: 127,
        bld_cnt_in_pnu: 3,
        floor_cnt: 2,
        min_floor: 1,
        max_floor: 2,
        has_roof: false,
      });
      expect(fireEvent.click(screen.getByRole('link', { name: '강남구 다른 건물 찾기' }))).toBe(false);
      expect(onFindInSigungu).toHaveBeenCalledTimes(1);
    });

    it('다른 동 링크는 첫 HTML 과 같은 10개까지 · 넘치면 「외 N동」(102동 단지 실측)', async () => {
      const many = Array.from({ length: 14 }, (_, i) => dong(`1168010100-${i + 1}`, `${101 + i}동`));
      responses.floors = { data: [floor({ bld_cnt_in_pnu: 14 })], error: null };
      const { container } = render(<FloorStack building={building({ bld_cnt_in_pnu: 14 })} dongs={many} />);
      await screen.findByRole('heading', { level: 1, name: '테스트빌딩 101동' });
      const row = container.querySelector('nav.stack__links .stack__links-row')!;
      expect(row.querySelectorAll('a')).toHaveLength(10);
      expect(row.textContent!.endsWith('테스트빌딩 111동 외 3동')).toBe(true);
    });

    it('★ 재검사 🟡 — 화면 링크도 공용 앞뒤 창(siblingWindow): 14동 중 자기 차례 8번째 → 3~13번째(자기 제외) + 외 3동', async () => {
      const many = Array.from({ length: 14 }, (_, i) => dong(`1168010100-${i + 1}`, `${101 + i}동`));
      const self = many[7]; // 8번째 = 108동
      responses.floors = { data: [floor({ bld_id: self.bld_id, bld_cnt_in_pnu: 14 })], error: null };
      const { container } = render(
        <FloorStack building={building({ bld_id: self.bld_id, bld_cnt_in_pnu: 14 })} dongs={many} />,
      );
      await screen.findByRole('heading', { level: 1, name: '테스트빌딩 108동' });
      const row = container.querySelector('nav.stack__links .stack__links-row')!;
      // 앞에서 10개(101~111동 중 자기 뺌)로 돌아가면 101·102동이 끼고 112·113동이 빠진다.
      expect([...row.querySelectorAll('a')].map((a) => a.textContent)).toEqual(
        [103, 104, 105, 106, 107, 109, 110, 111, 112, 113].map((n) => `테스트빌딩 ${n}동`),
      );
      expect(row.textContent!.endsWith(' 외 3동')).toBe(true);
    });

    it('★ 보완 F3 — 같은 땅 두 동의 렌더 h1 이 서로 다르다 · 동명칭이 비면 차례(N = 뷰 동 수)', async () => {
      responses.floors = { data: [floor({ bld_id: '1168010100-2', bld_cnt_in_pnu: 5 })], error: null };
      const b = render(<FloorStack building={building({ bld_id: '1168010100-2', bld_cnt_in_pnu: 5 })} dongs={DONGS} />);
      await screen.findByRole('heading', { level: 1, name: '테스트빌딩 B동' });
      b.unmount();
      responses.floors = { data: [floor({ bld_id: '1168010100-3', bld_cnt_in_pnu: 5 })], error: null };
      render(<FloorStack building={building({ bld_id: '1168010100-3', bld_nm: null, bld_cnt_in_pnu: 5 })} dongs={DONGS} />);
      // 층 행의 이름이 '테스트빌딩'이라 이름 + 차례(함수 줄 3 · 뷰 5).
      await screen.findByRole('heading', { level: 1, name: '테스트빌딩 (같은 땅 5동 중 3번째)' });
    });

    it('★ 보완 F4 — 불러오는 중·오류·층 0개에서도 h1 은 건물 이름 하나', async () => {
      let release: (v: unknown) => void = () => {};
      responses.floors = new Promise((r) => (release = r)) as unknown as typeof responses.floors;
      const loading = render(<FloorStack building={building({ bld_cnt_in_pnu: 3 })} dongs={DONGS} />);
      expect(screen.getByText('층 정보를 불러오는 중…')).toBeTruthy();
      expect(screen.getAllByRole('heading', { level: 1 }).map((h) => h.textContent)).toEqual(['테스트빌딩 A동']);
      release({ data: [], error: null });
      loading.unmount();

      responses.floors = { data: null, error: { message: 'x' } };
      const failed = render(<FloorStack building={building()} />);
      await waitFor(() => expect(failed.container.querySelector('.msg--error')).not.toBeNull());
      expect(screen.getAllByRole('heading', { level: 1 }).map((h) => h.textContent)).toEqual(['테스트빌딩']);
      failed.unmount();

      responses.floors = { data: [], error: null };
      render(<FloorStack building={building()} />);
      await screen.findByText('이 건물에는 층 정보가 없습니다.');
      expect(screen.getAllByRole('heading', { level: 1 }).map((h) => h.textContent)).toEqual(['테스트빌딩']);
    });

    it('동이 하나거나 목록이 없으면 다른 동 줄 없음 · 구 이름도 없으면 줄 자체가 없다', async () => {
      const { container, unmount } = render(<FloorStack building={building()} dongs={null} sigunguName="강남구" />);
      await screen.findByRole('heading', { level: 1, name: '테스트빌딩' });
      expect(container.querySelector('nav.stack__links')!.textContent).toBe('강남구 다른 건물 찾기');
      unmount();
      // 뷰가 동 1개라 말하면 목록이 와도 줄을 안 세운다(옛 목록이 남은 그림 · 다른 땅 목록 방어).
      const again = render(<FloorStack building={building()} dongs={DONGS} />);
      await screen.findByRole('heading', { level: 1, name: '테스트빌딩' });
      expect(again.container.querySelector('nav.stack__links')).toBeNull();
    });
  });

  it('D등급 배지를 항상 함께 보여준다', async () => {
    // 추정값 출력 시 근거 레벨 병기는 프로젝트 절대 규칙 3이다.
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/D등급 · 간접 추론/)).toBeTruthy());
  });

  it('★ 맨 아래 설명 글 — 「미상」 문장 바로 뒤에 승강기·대장 호수 칸을 두지 않는 까닭 한 문장(👤 2026-10-19 글자 그대로)', async () => {
    render(<FloorStack building={building()} />);
    const badge = await screen.findByText('D등급 · 간접 추론');
    const text = badge.closest('p.grade')!.textContent!;
    expect(text).toContain(
      '0을 값으로 적으면 없는 사실이 생깁니다. 승강기는 5층 이하 건물에서 대장에 0대로 적혀 있으면 칸을 두지 않고, ' +
        '공동주택·단독주택은 대장 호수가 세대 수라 칸을 두지 않습니다.',
    );
    // 호실 목록 안내(있을 때)보다 앞 — 이 건물엔 호실 목록이 없어 문장으로 끝난다.
    expect(text.endsWith('칸을 두지 않습니다.')).toBe(true);
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

describe('FloorStack — 건물 스펙 4칸 (로드맵 Wave 2 PR-B)', () => {
  /** 스펙 칸 하나의 값 글자. `dt` 를 찾아 바로 옆 `dd` 를 읽는다(칸끼리 안 섞이게). */
  function specValue(label: string): string | null {
    const dt = screen.queryByText(label);
    if (!dt) return null;
    return dt.parentElement?.querySelector('dd')?.textContent ?? null;
  }

  it('값이 있으면 연면적·용적률·건폐율·주차를 그대로 적는다', async () => {
    responses.floors = {
      data: [floor({ total_area_m2: 1234.5, far: 350.5, bcr: 59.9, parking_cnt: 12 })],
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('연면적')).toBeTruthy());
    // 연면적은 다른 면적 표기와 같은 규칙(㎡ + 평 병기)을 쓴다 — 같은 화면에서 면적을
    // 두 가지 방식으로 적으면 사람이 둘을 견주지 못한다.
    expect(specValue('연면적')).toBe('1,234.5㎡ (373평)');
    expect(specValue('용적률')).toBe('350.5%');
    expect(specValue('건폐율')).toBe('59.9%');
    expect(specValue('주차')).toBe('12대');
  });

  it('⛔ 0 은 값이 아니라 "미상"이다 (대장이 미기재를 0 으로 준다)', async () => {
    // 롯데월드타워가 실제로 주차 0·건폐율 0 으로 들어와 있다. 네 칸 모두 NULL 이 0행이라
    // "정말 0" 과 "안 적힘"을 갈라낼 방법이 없다 — 그래서 0 을 값으로 적지 않는다.
    responses.floors = {
      data: [floor({ total_area_m2: 0, far: 0, bcr: 0, parking_cnt: 0 })],
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('주차')).toBeTruthy());
    for (const label of ['연면적', '용적률', '건폐율', '주차']) {
      expect(specValue(label)).toBe('미상');
    }
    // "0대"·"0%"·"0㎡" 가 한 글자도 남으면 안 된다 — 그게 이 시험의 본론이다.
    // ⚠️ 화면 전체가 아니라 **스펙 칸 안**에서 본다. 층 목록의 면적("300㎡ (91평)")에도
    //    '0㎡' 라는 글자가 들어 있어서, 넓게 걸면 늘 빨간 헛경보가 난다.
    const facts = document.querySelector('.stack__facts')?.textContent ?? '';
    for (const bad of ['0대', '0%', '0㎡']) {
      expect(facts).not.toContain(bad);
    }
  });

  it('값이 아예 없어도(null) 칸은 남기고 "미상"이라 적는다', async () => {
    responses.floors = {
      data: [floor({ total_area_m2: null, far: null, bcr: null, parking_cnt: null })],
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('주차')).toBeTruthy());
    for (const label of ['연면적', '용적률', '건폐율', '주차']) {
      expect(specValue(label)).toBe('미상');
    }
  });

  it('건폐율이 100%를 넘으면 소스 오류라 보고 적지 않는다', async () => {
    // 2026-08-11 실측: 24만 행 중 7행이 1만%를 넘고 최댓값이 79,095% 다.
    // 한 행이 통계를 흔드는 것과 같은 이유로, 화면에서도 그건 값이 아니다.
    for (const v of [100.01, 79095]) {
      responses.floors = { data: [floor({ bcr: v })], error: null };
      render(<FloorStack building={building()} />);
      await waitFor(() => expect(screen.getByText('건폐율')).toBeTruthy());
      expect(specValue('건폐율')).toBe('미상');
      cleanup();
    }
  });

  it('건폐율 100%(정의상 최댓값)는 그대로 적는다 — 상한을 한 칸 잘못 잡으면 정상값이 사라진다', async () => {
    responses.floors = { data: [floor({ bcr: 100 })], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('건폐율')).toBeTruthy());
    expect(specValue('건폐율')).toBe('100%');
  });

  it('연면적이 상한(100만㎡)을 넘으면 적지 않는다 (861만㎡ 같은 오기입)', async () => {
    responses.floors = { data: [floor({ total_area_m2: 8_610_000 })], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('연면적')).toBeTruthy());
    expect(specValue('연면적')).toBe('미상');
  });

  it('상한 바로 아래(100만㎡)는 정상값으로 적는다', async () => {
    responses.floors = { data: [floor({ total_area_m2: 1_000_000 })], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('연면적')).toBeTruthy());
    expect(specValue('연면적')).toBe('1,000,000㎡ (302,500평)');
  });

  /** 머리 칸 이름표 차례(`dt` 글자). 칸 자리(주차 바로 뒤)를 본다. */
  function factLabels(): string[] {
    return [...document.querySelectorAll('.stack__facts dt')].map((d) => d.textContent ?? '');
  }

  it('물결 2-1 — 새 칸이 다 있으면 주차 바로 뒤 구조 → 승강기 → 내진설계 → 대장 호수', async () => {
    responses.floors = {
      data: [
        floor({
          strct_nm: '철근콘크리트구조',
          elevator_ride: 2,
          elevator_emgen: 1,
          seismic_design: true,
          ho_cnt: 48,
          bld_main_use: '제2종근린생활시설',
        }),
      ],
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('승강기')).toBeTruthy());
    expect(specValue('구조')).toBe('철근콘크리트구조');
    expect(specValue('승강기')).toBe('3대 (비상용 1대 포함)');
    expect(specValue('내진설계')).toBe('적용');
    expect(specValue('대장 호수')).toBe('48호');
    const labels = factLabels();
    const at = labels.indexOf('주차');
    expect(labels.slice(at, at + 5)).toEqual(['주차', '구조', '승강기', '내진설계', '대장 호수']);
  });

  it('물결 2-1 — 새 칸이 아예 안 오면(옛 서버) 넷 다 칸 없음', async () => {
    responses.floors = { data: [floor()], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('주차')).toBeTruthy());
    for (const label of ['구조', '승강기', '내진설계', '대장 호수']) {
      expect(specValue(label), label).toBeNull();
    }
    expect(factLabels().at(-1)).toBe('주차');
  });

  /** 지하 1층 + 1층부터 `top` 층까지(+ 옥탑) — 같은 건물 값 `over` 를 층마다 싣는다(서버처럼). */
  function stackUpTo(top: number, over: Partial<FloorRow>, roof = false): FloorRow[] {
    const nos = [-1, ...Array.from({ length: top }, (_, i) => i + 1), ...(roof ? [99] : [])];
    return nos.map((no) => floor({ floor_no: no, ...over }));
  }

  it('물결 2-1 — null·0: 구조는 미상 · 내진 false·대장 호수 0 은 칸 없음 · 6층 건물의 승강기 0 은 미상 (미적용·0호·0대 안 씀)', async () => {
    responses.floors = {
      data: stackUpTo(6, {
        strct_nm: null,
        elevator_ride: 0,
        elevator_emgen: 0,
        seismic_design: false,
        ho_cnt: 0,
        bld_main_use: '업무시설',
      }),
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('승강기')).toBeTruthy());
    expect(specValue('구조')).toBe('미상');
    expect(specValue('승강기')).toBe('미상');
    expect(specValue('내진설계')).toBeNull();
    expect(specValue('대장 호수')).toBeNull();
    const facts = document.querySelector('.stack__facts')?.textContent ?? '';
    for (const bad of ['0대', '0호', '미적용']) expect(facts).not.toContain(bad);
  });

  it('★ 결정 A — 승강기 합 0·둘 다 null 인 5층 이하 건물은 칸 없음 (옥탑·지하는 층수에 안 센다)', async () => {
    for (const [ride, emgen] of [
      [0, 0],
      [null, null],
    ] as const) {
      // 지하 1 + 지상 5 + 옥탑 = 7행이지만 지상 최고층은 5 — 숨김.
      responses.floors = { data: stackUpTo(5, { elevator_ride: ride, elevator_emgen: emgen }, true), error: null };
      render(<FloorStack building={building()} />);
      await waitFor(() => expect(screen.getByText('주차')).toBeTruthy());
      expect(specValue('승강기'), `${ride}/${emgen}`).toBeNull();
      cleanup();
      // 양성 대조: 같은 값에 지상 6층이면 미상
      responses.floors = { data: stackUpTo(6, { elevator_ride: ride, elevator_emgen: emgen }), error: null };
      render(<FloorStack building={building()} />);
      await waitFor(() => expect(screen.getByText('주차')).toBeTruthy());
      expect(specValue('승강기'), `${ride}/${emgen}`).toBe('미상');
      cleanup();
    }
  });

  it('★ 결정 B — 주용도가 공동주택·단독주택이거나 모르면 집합건물·호수가 있어도 대장 호수 칸 없음', async () => {
    for (const use of ['공동주택', '단독주택', null, undefined]) {
      responses.floors = { data: [floor({ ho_cnt: 48, elevator_ride: 1, bld_main_use: use })], error: null };
      render(<FloorStack building={building()} />);
      await waitFor(() => expect(screen.getByText('주차')).toBeTruthy());
      expect(specValue('대장 호수'), String(use)).toBeNull();
      cleanup();
    }
    // 양성 대조: 상가 집합건물은 보인다
    responses.floors = { data: [floor({ ho_cnt: 48, elevator_ride: 1, bld_main_use: '판매시설' })], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('대장 호수')).toBeTruthy());
    expect(specValue('대장 호수')).toBe('48호');
  });

  it('물결 2-1 — 내진 null 도 칸 없음 · 일반건물은 호수가 있어도 대장 호수 칸 없음 · 승강기 하나만 null', async () => {
    responses.floors = {
      data: [
        floor({
          is_jiphap: false,
          seismic_design: null,
          ho_cnt: 12,
          elevator_ride: null,
          elevator_emgen: 2,
          bld_main_use: '업무시설',
        }),
      ],
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('승강기')).toBeTruthy());
    expect(specValue('내진설계')).toBeNull();
    expect(specValue('대장 호수')).toBeNull();
    expect(specValue('승강기')).toBe('2대 (비상용 2대 포함)');
  });

  it('용적률은 100%를 넘어도 정상값이다 (건폐율 상한을 여기 잘못 옮겨 붙이면 안 된다)', async () => {
    // 용적률은 정의상 100%를 훌쩍 넘는다(층을 쌓을수록 커진다). 두 칸의 상한을
    // 같이 두면 고층 건물의 용적률이 통째로 사라진다.
    responses.floors = { data: [floor({ far: 1234.56 })], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('용적률')).toBeTruthy());
    expect(specValue('용적률')).toBe('1,234.6%');
  });

  it('★ C1 건물 종류 — true 집합건물 · false 일반건물 · null 은 "미상"(일반건물로 단정하지 않는다)', async () => {
    const cases: Array<[boolean | null, string]> = [
      [true, '집합건물'],
      [false, '일반건물'],
      [null, '미상'],
    ];
    for (const [v, want] of cases) {
      responses.floors = { data: [floor({ is_jiphap: v })], error: null };
      render(<FloorStack building={building()} />);
      await waitFor(() => expect(screen.getByText('건물 종류')).toBeTruthy());
      expect(specValue('건물 종류')).toBe(want);
      cleanup();
    }
  });

  it('스펙 칸에는 금칙어(절대 규칙 2)가 한 글자도 없다', async () => {
    responses.floors = { data: [floor()], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('연면적')).toBeTruthy());
    const facts = document.querySelector('.stack__facts')?.textContent ?? '';
    expect(facts).not.toBe('');
    for (const w of ['적정가', '평가액', '감정가', '가치평가', '시세']) {
      expect(facts).not.toContain(w);
    }
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
   *      (절대 규칙 2 — 추정을 내던 참고 매매 시세 카드는 결정 0041 로 내렸고, 사실 블록은 그 말을 쓰지 않는다)
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

  // ── 지분 거래 꼬리표(2026-10-08a · 물결 0-2b) ──────────────────────────────
  // 지분 거래는 목록에서 지우지 않고 '지분' 꼬리표를 단다. 설명 한 줄은 지분 행이 하나라도
  // 있을 때만 — 경계 짝(0건 = 없음 · 1건 = 있음)으로 못 박는다.
  const SHARE_NOTE = /지분 = 건물 일부 몫만 사고판 거래라 ㎡당 값이 낮게 나옵니다/;

  it('지분 거래 줄에만 "지분" 꼬리표가 붙는다', async () => {
    responses.txs = {
      data: [tx({ is_share: true, price_won: 50_000_000 }), tx({ is_share: false })],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/이 땅에서 신고된 거래 2건/)).toBeTruthy());
    const rows = container.querySelectorAll('.tx__list li');
    expect(rows).toHaveLength(2);
    expect(rows[0].querySelector('.tx__share')?.textContent).toBe('지분');
    expect(rows[1].querySelector('.tx__share')).toBeNull();
    // 지분 거래도 지우지 않는다 — 금액이 그대로 보인다.
    expect(screen.getByText('5,000만')).toBeTruthy();
  });

  it('지분 거래가 0건이면 설명 줄이 없다', async () => {
    // 옛 서버(칸 없음 = undefined)와 false 를 함께 — 둘 다 꼬리표·설명 없음.
    responses.txs = { data: [tx(), tx({ is_share: false })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/이 땅에서 신고된 거래 2건/)).toBeTruthy());
    expect(container.querySelector('.tx__share')).toBeNull();
    expect(screen.queryByText(SHARE_NOTE)).toBeNull();
  });

  it('지분 거래가 1건이면 목록 아래 설명 줄이 선다', async () => {
    responses.txs = { data: [tx(), tx({ is_share: true })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(SHARE_NOTE)).toBeTruthy());
    expect(container.querySelectorAll('.tx__share')).toHaveLength(1);
    // 목록 **아래**(같은 블록 안, 목록 뒤)에 선다.
    const note = container.querySelector('.tx__share-note')!;
    const list = container.querySelector('.tx__list')!;
    expect(list.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(note.textContent).toBe(
      '지분 = 건물 일부 몫만 사고판 거래라 ㎡당 값이 낮게 나옵니다 — 층대별 단가 계산에서는 뺍니다.',
    );
  });

  it('구 층대 단가 출처 줄에 "지분 거래 제외"가 적힌다', async () => {
    responses.txs = { data: [], error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/전체 표본/)).toBeTruthy());
    expect(screen.getByText(/집계 · 지분 거래 제외 · 전체 표본/)).toBeTruthy();
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
    await waitFor(() => expect(screen.getByText(/강남구 층대별 거래 단가 \(상가 거래 기준\)/)).toBeTruthy());
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
    // ⚠️ 층별 공표값 카드도 "표본 부족"이라는 같은 글자를 쓴다 —
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
    await waitFor(() => expect(screen.getByText(/유성구 층대별 거래 단가 \(상가 거래 기준\)/)).toBeTruthy());
    expect(screen.getByText(/2025년 1월 이후 계약분/)).toBeTruthy();
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
    const { container } = render(<FloorStack building={building()} />);
    // 같은 배지가 층별 공표값 카드(물결 1-C2) 칸 머리에도 선다 — 실거래 카드 안으로 좁혀 본다.
    await waitFor(() => expect(container.querySelector('section.tx')?.textContent).toMatch(/A등급 · 실거래 집계/));
    expect(screen.getByText(/국토교통부 상업업무용 부동산 매매 실거래가/)).toBeTruthy();
    expect(screen.getByText(/전체 표본 213건/)).toBeTruthy();
  });

  it('조회에 실패하면 실거래 섹션을 아예 그리지 않는다 (본체는 정상)', async () => {
    // 못 읽었을 때 "거래 없음"이라고 적으면 모르는 것을 아는 것처럼 말하게 된다.
    responses.txs = { data: null, error: { message: 'permission denied' } };
    responses.txStats = { data: null, error: { message: 'permission denied' } };
    const { container } = render(<FloorStack building={building()} />);
    // '1층'은 층별 공표값 카드(물결 1-C2)의 줄 머리에도 나온다 — 층 목록 카드 안으로 좁혀 본다.
    await waitFor(() => expect(container.querySelector('.card--floors .floor__label')?.textContent).toBe('1층'));
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
    // 신고된 사실을 세는 블록이 '시세'라는 말을 쓰기 시작하면 사실과 어림한 값의 경계가
    // 문구에서부터 흐려진다(추정 밴드 카드는 결정 0041 로 내렸다).
    responses.txs = { data: [tx()], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/실거래 기록/)).toBeTruthy());
    expect(container.querySelector('.tx')?.textContent).not.toContain('시세');
  });

  it('지분 거래 설명 줄이 선 상태에서도 Stage A 블록 안에 "시세"가 없다', async () => {
    // 설명 줄은 지분 행이 있을 때만 그려진다 — 지분 없는 거래로만 보면 그 줄을 영영 못 본다.
    responses.txs = { data: [tx({ is_share: true }), tx()], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.tx__share-note')).toBeTruthy());
    expect(container.querySelector('.tx')?.textContent).not.toContain('시세');
  });
});

describe('FloorStack — 실거래 그림 (결정 0038 B · V2)', () => {
  /**
   * 지키는 것: ① 글은 한 글자도 안 바뀐다(그림은 옆에 더할 뿐) ② 표본 부족 층대는 띠 없이 "–" ③ 점그림은 목록 거래 5건 이상만
   * ④ 점 꼴 = 층 묶음 · 지분 = 빈 꼴 ⑤ 그림이 서면 지분 설명 줄은 늘 선다 ⑥ 그림은 낭독기에서 뺀다(옆 글과 같은 내용).
   * ⓘ jsdom 은 CSS 를 못 본다 — 자리(인라인 % · 색 변수)만 본다. 실제 폭·넘침·종이는 E2E 「BX」.
   */
  const bandRow = (c: HTMLElement, name: string) =>
    [...c.querySelectorAll('.tx__bands li')].find((li) => li.querySelector('.tx__band')?.textContent === name)!;

  it('구 층대 띠 — 값을 내는 층대만 p25~p75 띠 + 가운데값 눈금(사실 색) · 표본 부족은 "–" · 축 글 한 줄', async () => {
    responses.txStats = { data: bands({ '1층': 213, '2층': 4 }), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.tx__bands--viz')).toBeTruthy());
    const one = bandRow(container, '1층');
    const range = one.querySelector<HTMLElement>('.tx__range')!;
    // 축 = 5,000만(p75 3,730만 올림) → 띠 27.6% ~ 74.6% · 눈금 45%.
    expect(parseFloat(range.style.left)).toBeCloseTo(27.6, 6);
    expect(parseFloat(range.style.width)).toBeCloseTo(47, 6);
    expect(range.style.background).toBe('var(--fact-2)');
    const tick = one.querySelector<HTMLElement>('.tx__tick')!;
    expect(parseFloat(tick.style.left)).toBeCloseTo(45, 6);
    expect(tick.style.background).toBe('var(--fact-4)');
    expect(one.querySelector('.tx__viz')!.getAttribute('aria-hidden')).toBe('true');
    // 표본 부족 층대 — 띠도 눈금도 없이 "–"(0 으로 그리지 않는다) · 까닭 글은 그대로.
    const two = bandRow(container, '2층');
    expect(two.querySelector('.tx__range')).toBeNull();
    expect(two.querySelector('.tx__tick')).toBeNull();
    expect(two.querySelector('.tx__viz--none')!.textContent).toBe('–');
    expect(two.querySelector('.tx__val')!.textContent).toBe('표본 부족');
    // 축 글 — 그림 밖 HTML · 낭독기에서 뺀다.
    const axis = container.querySelector('.tx__axis')!;
    expect(axis.textContent).toBe('0㎡당 5,000만');
    expect(axis.getAttribute('aria-hidden')).toBe('true');
  });

  it('구 층대 글은 그림이 서도 한 글자도 안 바뀐다', async () => {
    responses.txStats = { data: bands({ '1층': 213 }), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.tx__bands--viz')).toBeTruthy());
    const one = bandRow(container, '1층');
    expect(one.querySelector('.tx__val')!.textContent).toBe('중앙값 ㎡당 2,250만 (가운데 절반 1,380만~3,730만)');
    expect(one.querySelector('.tx__n')!.textContent).toBe('표본 213건');
  });

  it('값을 내는 층대가 하나도 없으면 띠·축 없이 지금 글만', async () => {
    responses.txStats = { data: bands({ '1층': 4, '2층': 3 }), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText('표본 4건')).toBeTruthy());
    expect(container.querySelector('.tx__bands--viz')).toBeNull();
    expect(container.querySelector('.tx__viz')).toBeNull();
    expect(container.querySelector('.tx__axis')).toBeNull();
  });

  it('점그림 문턱 — 목록 거래 4건이면 없음 · 5건이면 선다(점 5개 · 낭독기에서 뺀다)', async () => {
    responses.txs = { data: Array.from({ length: 4 }, () => tx()), error: null };
    const four = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/이 땅에서 신고된 거래 4건/)).toBeTruthy());
    expect(four.container.querySelector('.tx__plot')).toBeNull();
    four.unmount();

    responses.txs = { data: Array.from({ length: 5 }, (_, i) => tx({ unit_price: (i + 1) * 1_000_000 })), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.tx__plot')).toBeTruthy());
    expect(container.querySelectorAll('.tx__plot-in .tx__dot')).toHaveLength(5);
    expect(container.querySelector('.tx__plot')!.getAttribute('aria-hidden')).toBe('true');
    // 그림은 제목 아래 · 목록 위.
    const plot = container.querySelector('.tx__plot')!;
    const list = container.querySelector('.tx__list')!;
    expect(plot.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('점 꼴 = 층 묶음 다섯 · 지분 = 빈 꼴 · 범례는 그려진 꼴만(+ 지분 칸)', async () => {
    responses.txs = {
      data: [
        tx({ floor_no: 1, contract_ym: '202401' }),
        tx({ floor_no: 2 }),
        tx({ floor_no: 4 }),
        tx({ floor_no: -1 }),
        tx({ floor_no: null }),
        tx({ floor_no: 2, is_share: true, unit_price: 1_480_000 }),
      ],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.tx__plot')).toBeTruthy());
    const dots = [...container.querySelectorAll('.tx__plot-in .tx__shape')];
    expect(dots.map((d) => d.getAttribute('data-shape'))).toEqual(['1', '2', '3+', 'b', 'na', '2']);
    expect(dots.map((d) => d.getAttribute('data-hollow'))).toEqual(['0', '0', '0', '0', '0', '1']);
    // 색(빈 꼴 = 바탕색 · 찬 꼴 = 호박 · 층 미상 = 회색)은 CSS 규칙이 data 이름표로 칠한다 — 실제 칠은 E2E 「BX」가 본다.
    // 꼴마다 다른 도형.
    expect(dots[0].firstElementChild!.tagName.toLowerCase()).toBe('circle');
    expect(dots[1].firstElementChild!.tagName.toLowerCase()).toBe('rect');
    expect(dots[2].firstElementChild!.tagName.toLowerCase()).toBe('polygon');
    expect(dots[3].firstElementChild!.tagName.toLowerCase()).toBe('polygon');
    expect(dots[2].firstElementChild!.getAttribute('points')).not.toBe(dots[3].firstElementChild!.getAttribute('points'));
    const keys = [...container.querySelectorAll('.tx__key')].map((k) => k.textContent);
    expect(keys).toEqual(['1층', '2층', '3층 이상', '지하', '층 미상', '속이 빈 꼴 = 지분']);
    // 눈금 글 — 세로 0 · ¼ · ½ · ¾ · ㎡당 상한(보완 1 F4) · 가로 가장 이른 달 ~ 가장 늦은 달.
    expect([...container.querySelectorAll('.tx__plot-yin .tx__tick-y')].map((t) => t.textContent)).toEqual([
      '0',
      '125만',
      '250만',
      '375만',
      '500만',
    ]);
    expect(container.querySelector('.tx__plot-unit')!.textContent).toBe('㎡당');
    expect(container.querySelector('.tx__plot-x')!.textContent).toBe('2024년 1월2026년 5월');
  });

  it('지분이 없으면 범례에 지분 칸이 없다 · ㎡당 값 없는 거래는 점 없이 그 수를 말한다', async () => {
    responses.txs = {
      data: [tx(), tx(), tx(), tx(), tx({ unit_price: null, bld_area_m2: null })],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.tx__plot')).toBeTruthy());
    // 같은 달·같은 값·같은 꼴 넷은 점 하나 + 「×4」(보완 1 F2).
    expect(container.querySelectorAll('.tx__plot-in .tx__dot')).toHaveLength(1);
    expect(container.querySelector('.tx__labs--wide .tx__lab')!.textContent).toBe('380만 ×4');
    const keys = [...container.querySelectorAll('.tx__key')].map((k) => k.textContent);
    // 이 파일의 기본 거래는 3층(`tx()`).
    expect(keys).toEqual(['3층 이상', '㎡당 값이나 계약 달이 없는 거래 1건은 점이 없습니다']);
    // 지분 0건 — 설명 줄도 없다(그림이 서도).
    expect(container.querySelector('.tx__share-note')).toBeNull();
    expect(container.querySelector('.tx')?.textContent).not.toContain('시세');
  });

  it('★ 그림이 서면 지분 설명 줄은 늘 선다 — 지분이 숨은 줄(11번째 이후)에만 있어도 · 펼쳐도 접어도', async () => {
    responses.txs = { data: Array.from({ length: 14 }, (_, i) => tx({ is_share: i === 12 })), error: null };
    const { container } = render(<FloorStack building={building()} />);
    const fold = () => container.querySelector<HTMLButtonElement>('.tx__list ~ .list__fold');
    await waitFor(() => expect(fold()).toBeTruthy());
    expect(container.querySelector('.tx__plot')).toBeTruthy();
    const note = () => container.querySelector('.tx__share-note')!;
    expect(note().classList.contains('list__folded')).toBe(false);
    fireEvent.click(fold()!);
    expect(note().classList.contains('list__folded')).toBe(false);
    fireEvent.click(fold()!);
    expect(note().classList.contains('list__folded')).toBe(false);
    // 숨은 줄의 지분도 그림에는 빈 꼴로 있다.
    expect(container.querySelectorAll('.tx__plot-in .tx__shape[data-hollow="1"]')).toHaveLength(1);
  });

  it('보완 1 — 유니온 꼴 12건: 점 금액 글자(목록과 같은 서식) · 겹친 지분 둘 = 점 하나 「260만 ×2」 · 가로 눈금선 다섯 · 두 벌', async () => {
    responses.txs = {
      data: [
        tx({ floor_no: 11, contract_ym: '202608', unit_price: 9_000_000 }),
        tx({ floor_no: 2, contract_ym: '202603', unit_price: 2_600_000, is_share: true }),
        tx({ floor_no: 2, contract_ym: '202603', unit_price: 2_600_000, is_share: true }),
        tx({ floor_no: 5, contract_ym: '202507', unit_price: 7_380_000 }),
        tx({ floor_no: 7, contract_ym: '202507', unit_price: 7_290_000 }),
        tx({ floor_no: 9, contract_ym: '202507', unit_price: 7_720_000 }),
        tx({ floor_no: 1, contract_ym: '202511', unit_price: 6_100_000 }),
        tx({ floor_no: 4, contract_ym: '202504', unit_price: 6_900_000 }),
        tx({ floor_no: 2, contract_ym: '202502', unit_price: 4_200_000 }),
        tx({ floor_no: -1, contract_ym: '202410', unit_price: 3_000_000 }),
        tx({ floor_no: null, contract_ym: '202405', unit_price: 3_500_000 }),
        tx({ floor_no: 1, contract_ym: '202402', unit_price: 5_000_000 }),
      ],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.tx__plot')).toBeTruthy());
    // 겹친 지분 둘은 점 하나 — 점 11 · 거래 목록은 12줄 그대로.
    expect(container.querySelectorAll('.tx__plot-in .tx__dot')).toHaveLength(11);
    expect(container.querySelectorAll('.tx__list > li')).toHaveLength(12);
    const wide = [...container.querySelectorAll('.tx__labs--wide .tx__lab')].map((l) => l.textContent);
    expect(wide).toEqual(['900만', '260만 ×2', '738만', '729만', '772만', '610만', '690만', '420만', '300만', '350만', '500만']);
    // 목록의 ㎡당 표기와 같은 함수(formatManWon) — 목록 첫 줄 「㎡당 900만」의 숫자 부분이 점 글자와 같다.
    expect(container.querySelector('.tx__list > li .tx__unit')!.textContent).toBe('㎡당 900만');
    // 휴대폰 벌도 같은 건수(묶었으면 ×N 합) — 화면에 어느 쪽이 보일지는 CSS(E2E BX).
    const narrow = [...container.querySelectorAll('.tx__labs--narrow .tx__lab')].map((l) => l.textContent ?? '');
    expect(narrow.reduce((s, t) => s + Number(/×(\d+)$/.exec(t)?.[1] ?? 1), 0)).toBe(12);
    // 가로 눈금선 다섯(0 · ¼ · ½ · ¾ · 끝) + 눈금 글.
    expect([...container.querySelectorAll('.tx__plot-in .tx__grid')].map((g) => (g as HTMLElement).style.bottom)).toEqual([
      '0%',
      '25%',
      '50%',
      '75%',
      '100%',
    ]);
    expect([...container.querySelectorAll('.tx__plot-yin .tx__tick-y')].map((t) => t.textContent)).toEqual([
      '0',
      '250만',
      '500만',
      '750만',
      '1,000만',
    ]);
    // 그림은 통째로 낭독기에서 뺀다(글자가 늘어도) · 사실 블록에 '시세' 0.
    expect(container.querySelector('.tx__plot')!.getAttribute('aria-hidden')).toBe('true');
    expect(container.querySelector('.tx')?.textContent).not.toContain('시세');
  });

  it('보완 3 G1 · 보완 4 — 글자를 다 못 단 점그림엔 안내 줄 「글자 자리가 없는 점 N개 — 금액은 아래 거래 목록(「거래 전부 보기」 포함)에 있습니다」 · 다 단 그림엔 없다', async () => {
    let seed = 7;
    const rnd = () => {
      seed = (seed * 1_103_515_245 + 12_345) % 2_147_483_648;
      return seed / 2_147_483_648;
    };
    responses.txs = {
      data: Array.from({ length: 100 }, () =>
        tx({
          contract_ym: `${2024 + Math.floor(rnd() * 3)}${String(1 + Math.floor(rnd() * 12)).padStart(2, '0')}`,
          unit_price: Math.round(1_000_000 + rnd() * 9_000_000),
        }),
      ),
      error: null,
    };
    const dense = render(<FloorStack building={building()} />);
    await waitFor(() => expect(dense.container.querySelector('.tx__plot')).toBeTruthy());
    const note = dense.container.querySelector('.tx__plot-note--narrow');
    expect(note?.textContent).toMatch(/^글자 자리가 없는 점 \d+개 — 금액은 아래 거래 목록\(「거래 전부 보기」 포함\)에 있습니다$/);
    // 거래가 10건을 넘어 「거래 전부 보기」 단추가 실제로 있다(문구가 가리키는 것이 화면에 있다).
    expect(dense.container.querySelector('.tx__list ~ .list__fold')?.textContent).toBe('거래 전부 보기 (100건)');
    // 글자 수 + 안내 줄의 N = 점 수(휴대폰 벌).
    const n = Number(/점 (\d+)개/.exec(note!.textContent!)![1]);
    const dots = dense.container.querySelectorAll('.tx__plot-in .tx__dot').length;
    const covered = dense.container.querySelectorAll('.tx__labs--narrow .tx__lab').length;
    expect(n).toBeGreaterThan(0);
    expect(covered).toBeGreaterThan(0);
    expect(n).toBeLessThan(dots);
    // 안내 줄은 점그림 안(범례 줄 바로 위) — 그림과 함께 낭독기에서 빠진다.
    expect(note!.closest('.tx__plot')).toBeTruthy();
    expect(note!.nextElementSibling?.classList.contains('tx__keys')).toBe(true);
    dense.unmount();

    responses.txs = { data: Array.from({ length: 5 }, (_, i) => tx({ unit_price: (i + 1) * 1_000_000 })), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.tx__plot')).toBeTruthy());
    expect(container.querySelector('.tx__plot-note')).toBeNull();
  });

  it('목록은 그대로 — 처음 10건 + 「거래 전부 보기 (N건)」 · 줄 글자 그대로', async () => {
    responses.txs = { data: Array.from({ length: 12 }, () => tx()), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.tx__plot')).toBeTruthy());
    expect(container.querySelectorAll('.tx__list > li')).toHaveLength(12);
    expect(container.querySelectorAll('.tx__list > li:not(.list__folded)')).toHaveLength(10);
    expect(container.querySelector('.tx__list ~ .list__fold')!.textContent).toBe('거래 전부 보기 (12건)');
    expect(container.querySelector('.tx__list > li')!.textContent).toBe('3층2026-0584.3㎡ (26평)3억 2,000만㎡당 380만집합');
  });
});

describe('FloorStack — 국세청 기준시가 (『층별 공표값 나란히』 카드 안 · 결정 0041 ㉤)', () => {
  /**
   * 내린 참고 매매 시세 카드 안에 있던 기준시가 줄을 층별 공표값 카드의 기준시가 칸으로 옮겼다(정보 손실 0).
   * 지키는 것:
   *   ① 값과 표본(호 수)·고시일을 한 칸에 함께 낸다 (절대 규칙 3)
   *   ② 총액으로 환산하지 않는다 — 서버가 면적을 안 준다
   *   ③ 없거나 못 읽으면 **그 칸만 '–'** (카드의 나머지는 그대로다)
   *   ④ 부기("시세가 아니다")는 카드 안에서 **한 번만** 한다
   *   ⑤ 구 관문이 없다 — 어느 구에서든, 1층에서도 선다(밴드처럼 1층·게이트 구를 빼지 않는다)
   */
  const baseCell = (container: HTMLElement, no: number, part: 'val' | 'sub') =>
    container.querySelector(`.gap__row[data-floor="${no}"] .gap__cell--base .gap__${part}`)?.textContent ?? '';

  function floorsDesc(...nos: number[]) {
    return { data: nos.map((n) => floor({ floor_no: n })), error: null };
  }

  it('층마다 값·호 수·고시일을 한 칸에 함께 적는다', async () => {
    responses.floors = floorsDesc(2);
    responses.basePrices = { data: [basePrice({ floor_no: 2 })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(baseCell(container, 2, 'val')).toBe('300만'));
    // 값만 떼어 내보내지 않는다 — 이 값은 그 층 호실들의 가운데값이다.
    expect(baseCell(container, 2, 'sub')).toBe(' (호 12개 가운데값 · 2026년 1월 1일 고시)');
  });

  it('아주 싼 층(1만 원 미만)도 단위가 겹치지 않게 적는다', async () => {
    // 원본 최저값이 5,000원/㎡ 라 이 층이 실제로 있다(2026-08-27 적재 담당 실측).
    responses.floors = floorsDesc(2);
    responses.basePrices = { data: [basePrice({ floor_no: 2, median_price_per_m2: 5_000 })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(baseCell(container, 2, 'val')).toBe('5,000원'));
  });

  it('세무 기준가격이라는 사실과 A등급 배지를 함께 적는다 (C등급과 다른 모양)', async () => {
    responses.floors = floorsDesc(2);
    responses.basePrices = { data: [basePrice({ floor_no: 2 })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(baseCell(container, 2, 'val')).toBe('300만'));
    const gap = container.querySelector('.gap')!;
    expect(gap.textContent).toContain('세무 기준가격 — 시세가 아닙니다');
    const badge = gap.querySelector('.gap__head--base .grade__badge')!;
    expect(badge.textContent).toBe('A등급 · 공식 고시');
    expect(badge.className).not.toContain('grade__badge--est');
  });

  it('부기는 카드 안에서 한 번만 한다 (줄마다 반복하지 않는다)', async () => {
    responses.floors = floorsDesc(3, 2);
    responses.basePrices = {
      data: [basePrice({ floor_no: 2 }), basePrice({ floor_no: 3, median_price_per_m2: 4_100_000 })],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(baseCell(container, 3, 'val')).toBe('410만'));
    const text = container.querySelector('.gap')?.textContent ?? '';
    expect(text.split('시세가 아닙니다')).toHaveLength(2); // = 딱 한 번 나온다
  });

  it('총액(억)으로 환산하지 않는다 — 서버가 면적을 안 준다', async () => {
    // ⚠️ "'억'이라는 글자가 없다"로는 못 잡는다 — 총액이 만원대면(9,840만) 그 검사를
    //    그대로 빠져나간다. 그래서 **값 칸의 모양 자체**를 못 박는다: ㎡당 단가 하나뿐이다.
    responses.floors = floorsDesc(3, 2);
    responses.basePrices = {
      data: [basePrice({ floor_no: 2 }), basePrice({ floor_no: 3, median_price_per_m2: 4_100_000 })],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(baseCell(container, 3, 'val')).toBe('410만'));
    const vals = [...container.querySelectorAll('.gap__cell--base .gap__val')].map((el) => el.textContent ?? '');
    expect(vals).toHaveLength(2);
    for (const v of vals) expect(v).toMatch(/^[\d,]+(만|원)$/);
    const cells = [...container.querySelectorAll('.gap__cell--base')].map((el) => el.textContent ?? '').join(' ');
    expect(cells).not.toContain('평');
    expect(cells).not.toContain('억');
  });

  it('★ 1층에도 기준시가를 그린다 — 밴드처럼 1층을 빼지 않는다(국세청이 낸 값이다)', async () => {
    responses.floors = floorsDesc(1);
    responses.basePrices = { data: [basePrice({ floor_no: 1 })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(baseCell(container, 1, 'val')).toBe('300만'));
  });

  it('★ 기준시가만 있는 건물에서도 카드가 선다(결정 0041 E2 — 값 든 칸 하나면 선다)', async () => {
    responses.floors = floorsDesc(2);
    responses.txStats = { data: [], error: null };
    responses.basePrices = { data: [basePrice({ floor_no: 2 })], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(baseCell(container, 2, 'val')).toBe('300만'));
    expect(container.querySelector('.gap__row[data-floor="2"] .gap__cell--tx .gap__val')?.textContent).toBe('–');
  });

  it('자료가 없으면(빈 배열) 그 칸만 – 이고 카드는 그대로다 — 「기준시가 없음」이라 적지 않는다', async () => {
    responses.floors = floorsDesc(1);
    responses.basePrices = { data: [], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.gap')).toBeTruthy());
    expect(baseCell(container, 1, 'val')).toBe('–');
    expect(container.querySelector('.gap')?.textContent).not.toContain('기준시가 없음');
    // 이유 한 줄(👤 2026-10-18 ② · 보완 2차 C1) — 빈 배열 = 상가 기준시가 없음(실패 글과 섞지 않는다).
    const note = container.querySelector('.gap__head--base .gap__head-note')?.textContent;
    expect(note).toBe('이 건물에는 국세청이 고시한 상가 기준시가가 없습니다(오피스텔 호실은 주거 가격이라 싣지 않습니다)');
  });

  it('서버에 함수가 아직 없어도(PGRST202) 카드의 나머지는 정상이다', async () => {
    responses.basePrices = { data: null, error: { code: 'PGRST202', message: 'function does not exist' } };
    responses.floors = floorsDesc(1);
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.gap')).toBeTruthy());
    expect(baseCell(container, 1, 'val')).toBe('–');
    expect(container.querySelector('.gap__row[data-floor="1"] .gap__cell--tx .gap__val')?.textContent).toBe('㎡당 2,250만');
    expect(container.textContent ?? '').not.toContain('PGRST202');
    // 실패 = 「불러오지 못했습니다」(상가 기준시가가 없다고 말하지 않는다 — 모르는 것을 없다고 하지 않는다).
    expect(container.querySelector('.gap__head--base .gap__head-note')?.textContent).toBe('기준시가를 불러오지 못했습니다');
    expect(container.textContent).not.toContain('상가 기준시가가 없습니다');
  });

  it('pnu 를 p_pnu 라는 이름으로 보낸다 (라이브 전용 오류를 막는 유일한 가드)', async () => {
    // 목은 인자 **이름**을 안 보므로, 여기서 안 잡으면 테스트는 전부 초록인 채
    // 라이브에서만 PGRST202 가 난다(형제 함수 둘은 pnu·sigungu 다).
    render(<FloorStack building={building({ pnu: '3020010600100010000' })} />);
    await waitFor(() => expect(screen.getByText(/층대별 거래 단가/)).toBeTruthy());
    const call = rpcCalls.find((c) => c.fn === 'list_base_prices');
    expect(call?.args).toEqual({ p_pnu: '3020010600100010000' });
  });

  it('★ 내린 참고 시세 함수를 더 부르지 않는다 · 「참고 매매 시세」 카드가 없다(결정 0041 E1)', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/층대별 거래 단가/)).toBeTruthy());
    expect(rpcCalls.map((c) => c.fn)).not.toContain(['list', 'price', 'bands'].join('_'));
    expect(container.textContent).not.toContain('참고 매매 시세');
  });
});

describe('FloorStack — 한 장 요약 카드 배치 (로드맵 Wave 2)', () => {
  /**
   * 화면 위에서 **실제로** 배치표(`SECTION_PLAN`)대로 그려지는지 본다.
   *
   * `sectionCards.test.ts` 는 표 자체를 세고, `SectionCard.test.tsx` 는 틀 하나의 동작을
   * 본다. 둘 다 초록인데 화면에서는 카드가 안 감싸져 있거나 순서가 뒤바뀌어 있을 수
   * 있어서, "다섯 장이 이 순서로, 이 역할로, 이 상태로 있다"는 여기서만 잡힌다.
   */

  /** 업종 분포 응답 한 벌(모양 검사를 통과하는 최소 형태). */
  const MIX = {
    snapshot_ym: '202606',
    radius_m: 500,
    districts: [
      {
        district_id: '3120189',
        name: '역삼역',
        type: '발달상권',
        source_nm: '서울특별시 상권분석서비스',
        total: 100,
        cats: [{ cd: 'I2', nm: '음식', n: 60 }],
      },
    ],
    radius: { total: 402, cats: [{ cd: 'I2', nm: '음식', n: 200 }] },
  };

  /** 화면에 그려진 카드들을 **위에서 아래 순서 그대로** 읽어 온다. */
  function readCards(container: HTMLElement) {
    return [...container.querySelectorAll('.card')].map((el) => ({
      title: el.querySelector('.card__title')?.textContent ?? '',
      role: el.querySelector('.card__role')?.textContent ?? '',
      open: el.querySelector('.card__toggle')?.getAttribute('aria-expanded') === 'true',
      summary: el.querySelector('.card__summary')?.textContent ?? '',
    }));
  }

  beforeEach(() => {
    // 카드가 **전부** 나오는 상태를 만든다 — 어느 하나라도 응답이 비면 그 카드는
    // 스스로 사라지므로(모름 ≠ 없음), 상한을 세는 시험이 헐거워진다.
    //
    // ⛔ **2026-09-01 감사에서 잡힌 구멍**: 여기에 임대 응답이 없어 여섯째 카드가 아예
    //    안 그려졌고, 아래 배치 단언들이 다섯 장만 보고 있었다. 그래서 임대 카드의
    //    제목·역할·기본 펼침이 **화면 위에서는 한 번도 검사되지 않았다**(배치표 자체를
    //    세는 `sectionCards.test.ts` 만 알고 있었다). 카드를 더할 때 여기를 안 채우면
    //    새 카드는 조용히 이 가드 밖에 남는다.
    responses.floors = { data: [floor({ floor_no: 2 }), floor()], error: null };
    responses.districts = {
      data: {
        covered: true,
        districts: [{ name: '역삼역', type: '발달상권' }],
        sources: ['서울특별시 상권분석서비스'],
      },
      error: null,
    };
    responses.industryMix = { data: MIX, error: null };
    responses.txs = { data: [tx()], error: null };
    // 층별 공표값 카드는 값 든 칸이 하나라도 있으면 선다(결정 0041 E2) — 국세청 한 층도 준다.
    responses.basePrices = {
      data: [{ floor_no: 1, median_price_per_m2: 4_100_000, ho_cnt: 12, notice_date: '2026-01-01' }],
      error: null,
    };
    responses.rent = {
      data: [
        {
          district_nm: '역삼역',
          rone_region_nm: '서울>강남>테헤란로',
          bld_type: '집합상가',
          quarter: '2026Q2',
          vacancy_rate: 10.08,
          rent_per_m2: 27.06,
          yield_rate: 0.82,
        },
      ],
      error: null,
    };
    responses.openclose = {
      data: [
        {
          status: 'ok',
          district_id: '3120189',
          district_nm: '역삼역',
          district_type: '발달상권',
          latest_quarter: '20262',
          quarters: [
            {
              quarter: '20262',
              similr_induty_stor_co: 441,
              stor_co: 378,
              frc_stor_co: 63,
              opbiz_stor_co: 5,
              clsbiz_stor_co: 9,
              opbiz_rt: 1.13,
              clsbiz_rt: 2.04,
            },
          ],
          industries: null,
          other_industries: null,
          window_quarters: ['20262'],
        },
      ],
      error: null,
    };
  });

  it('배치표가 정한 순서·제목·역할·기본 상태 그대로 그려진다', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => {
      expect(container.querySelectorAll('.card')).toHaveLength(Object.keys(SECTION_PLAN).length);
      // 로딩 카드도 한 장으로 세어지므로 장수만 기다리면 경주가 남는다 — 응답이
      // 전부 자리 잡은 뒤에만 배치·상태·요약을 읽는다(본문 없는 카드는 버튼이 없어
      // aria-expanded 판독이 false 로 읽히는 것이 이 경주의 증상이었다).
      expect(container.textContent).not.toContain('불러오는 중');
    });

    const cards = readCards(container);
    expect(cards.map((c) => c.title)).toEqual([
      '속한 상권',
      '층 목록',
      '둘레의 업종 분포',
      '실거래 기록',
      // 층별 공표값(결정 0041 E2) — 내린 참고 매매 시세 카드의 자리 · 접힌 채 시작.
      '층별 공표값 나란히 — 국세청 기준시가 · 구 상가 단가 · 부동산원 임대료',
      '상권 임대 동향 (부동산원 조사)',
      '상권 개업·폐업 (서울시 공표)',
      // 빈 카드 셋(결정 0036 결정 2 · 물결 1-B) — 역할 없음 차례에서는 맨 끝.
      '업종별 추정매출',
      '유동인구',
      '이 자리 가게 이력',
    ]);
    expect(cards.map((c) => c.role)).toEqual([
      '공통', '공통', '창업자', '투자자', '공통', '투자자', '창업자', '창업자', '창업자', '창업자',
    ]);
    // 공통 둘 + 역할마다 하나씩 = 넷을 펼치고, 층별 공표값·임대는 접는다.
    // ⛔ 임대 카드의 defaultOpen 이 실수로 true 가 되는 날 여기서 잡힌다(예산 4장 초과).
    // ⛔ 개업·폐업 카드(결정 0033)도 접힌다 — 이 건물이 아니라 상권 전체의 값이다.
    // ⛔ 빈 카드 셋도 접힌 채 시작한다(👤 — 지금은 "비어 있음" 한 줄뿐이다).
    expect(cards.map((c) => c.open)).toEqual([
      true, true, true, true, false, false, false, false, false, false,
    ]);
  });

  it('첫 화면에 펼쳐진 카드가 상한(4장)을 넘지 않는다', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => {
      expect(container.querySelectorAll('.card')).toHaveLength(Object.keys(SECTION_PLAN).length);
      // 로딩 카드도 한 장으로 세어지므로 장수만 기다리면 경주가 남는다 — 응답이
      // 전부 자리 잡은 뒤에만 배치·상태·요약을 읽는다(본문 없는 카드는 버튼이 없어
      // aria-expanded 판독이 false 로 읽히는 것이 이 경주의 증상이었다).
      expect(container.textContent).not.toContain('불러오는 중');
    });
    expect(readCards(container).filter((c) => c.open)).toHaveLength(SECTION_EXPAND_BUDGET);
  });

  /**
   * 역할별 카드 순서·펼침(👤 결정 0036 결정 18 ②) — 결정 문서의 표를 **글자 그대로** 옮겼다.
   * 배치표(`ROLE_SECTION_LAYOUT`)를 돌려 기대값을 만들지 않는다 — 그러면 표가 틀려도 같이 틀린다.
   * 역할 없음은 위 시험(지금 화면)이 그대로 지킨다.
   */
  const ROLE_TABLE: Record<ViewerRole, Array<[string, boolean]>> = {
    투자자: [
      ['속한 상권', true],
      ['층 목록', true],
      ['실거래 기록', true],
      // 결정 0041 E2 — 층별 공표값이 내린 밴드의 자리와 펼침을 이어받는다.
      ['층별 공표값 나란히 — 국세청 기준시가 · 구 상가 단가 · 부동산원 임대료', true],
      ['상권 임대 동향 (부동산원 조사)', false],
      ['둘레의 업종 분포', false],
      ['상권 개업·폐업 (서울시 공표)', false],
      ['업종별 추정매출', false],
      ['유동인구', false],
      ['이 자리 가게 이력', false],
    ],
    창업자: [
      ['속한 상권', true],
      ['층 목록', true],
      ['둘레의 업종 분포', true],
      ['상권 개업·폐업 (서울시 공표)', true],
      // 빈 카드 셋은 창업자 벌에서 개업·폐업 바로 뒤(👤 2026-10-11).
      ['업종별 추정매출', false],
      ['유동인구', false],
      ['이 자리 가게 이력', false],
      ['실거래 기록', false],
      ['층별 공표값 나란히 — 국세청 기준시가 · 구 상가 단가 · 부동산원 임대료', false],
      ['상권 임대 동향 (부동산원 조사)', false],
    ],
    중개사: [
      ['층 목록', true],
      ['실거래 기록', true],
      ['속한 상권', true],
      // 결정 0041 E2 — 자리만 이어받고 접힘 그대로(중개사 펼침은 셋).
      ['층별 공표값 나란히 — 국세청 기준시가 · 구 상가 단가 · 부동산원 임대료', false],
      ['상권 임대 동향 (부동산원 조사)', false],
      ['둘레의 업종 분포', false],
      ['상권 개업·폐업 (서울시 공표)', false],
      ['업종별 추정매출', false],
      ['유동인구', false],
      ['이 자리 가게 이력', false],
    ],
  };
  const NO_ROLE: Array<[string, boolean]> = [
    ['속한 상권', true],
    ['층 목록', true],
    ['둘레의 업종 분포', true],
    ['실거래 기록', true],
    ['층별 공표값 나란히 — 국세청 기준시가 · 구 상가 단가 · 부동산원 임대료', false],
    ['상권 임대 동향 (부동산원 조사)', false],
    ['상권 개업·폐업 (서울시 공표)', false],
    ['업종별 추정매출', false],
    ['유동인구', false],
    ['이 자리 가게 이력', false],
  ];

  async function settledCards(container: HTMLElement) {
    await waitFor(() => {
      expect(container.querySelectorAll('.card')).toHaveLength(Object.keys(SECTION_PLAN).length);
      expect(container.textContent).not.toContain('불러오는 중');
    });
    return readCards(container).map((c): [string, boolean] => [c.title, c.open]);
  }

  for (const role of VIEWER_ROLES) {
    it(`역할 ${role} — 카드 순서·펼침이 결정 18 표대로다 (펼침은 상한 안)`, async () => {
      const { container } = render(<FloorStack building={building()} viewerRole={role} />);
      const cards = await settledCards(container);
      expect(cards).toEqual(ROLE_TABLE[role]);
      expect(cards.filter(([, open]) => open).length).toBeLessThanOrEqual(SECTION_EXPAND_BUDGET);
    });
  }

  it('역할을 바꾸면 그 자리에서 순서·펼침이 새 표대로 다시 선다 (자료는 다시 묻지 않는다)', async () => {
    const { container, rerender } = render(
      <FloorStack building={building()} viewerRole="투자자" />,
    );
    await settledCards(container);
    const calls = rpcCalls.length;

    // 사람이 접힌 카드를 하나 펼쳐 둔다 — 역할을 바꾸면 그 손길까지 새 표대로 다시 선다.
    fireEvent.click(container.querySelector('.oc .card__toggle')!);
    expect(container.querySelector('.oc .card__toggle')?.getAttribute('aria-expanded')).toBe(
      'true',
    );

    // 자리가 바뀌는 카드(개업·폐업: 투자자 7번째 → 창업자 4번째)의 화면 조각을 쥐어 둔다.
    // 곁 카드 자료는 보관함에서 다시 나오므로 요청 수로는 '다시 태어남'을 못 본다 — 같은 물건인지 본다.
    const ocBefore = container.querySelector('.oc');
    expect(ocBefore).not.toBeNull();

    rerender(<FloorStack building={building()} viewerRole="창업자" />);
    expect(await settledCards(container)).toEqual(ROLE_TABLE.창업자);
    expect(container.querySelector('.oc')).toBe(ocBefore);

    rerender(<FloorStack building={building()} viewerRole="중개사" />);
    expect(await settledCards(container)).toEqual(ROLE_TABLE.중개사);

    // 해제하면 역할을 고르기 전 화면 그대로.
    rerender(<FloorStack building={building()} viewerRole={null} />);
    expect(await settledCards(container)).toEqual(NO_ROLE);

    // 카드는 자리만 옮긴다 — 곁 카드가 다시 태어나 서버에 또 묻지 않는다.
    expect(rpcCalls.length).toBe(calls);
  });

  it('같은 역할로 다시 그려져도 사람이 연 카드는 그대로다 (자료가 올 때마다 접히지 않는다)', async () => {
    const { container, rerender } = render(
      <FloorStack building={building()} viewerRole="투자자" />,
    );
    await settledCards(container);
    fireEvent.click(container.querySelector('.oc .card__toggle')!);
    rerender(<FloorStack building={building()} viewerRole="투자자" />);
    expect(container.querySelector('.oc .card__toggle')?.getAttribute('aria-expanded')).toBe(
      'true',
    );
  });

  it('접힌 카드도 제목과 핵심 한 줄은 보인다 (접힘 ≠ 숨김)', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => {
      expect(container.querySelectorAll('.card')).toHaveLength(Object.keys(SECTION_PLAN).length);
      // 로딩 카드도 한 장으로 세어지므로 장수만 기다리면 경주가 남는다 — 응답이
      // 전부 자리 잡은 뒤에만 배치·상태·요약을 읽는다(본문 없는 카드는 버튼이 없어
      // aria-expanded 판독이 false 로 읽히는 것이 이 경주의 증상이었다).
      expect(container.textContent).not.toContain('불러오는 중');
    });

    const gap = container.querySelector('.gap')!;
    // 본문(값·근거·출처)은 아직 **안 보인다**…
    //
    // ⚠️ "DOM 에 없다"가 아니라 "감춰져 있다"를 본다. 접힌 본문은 자리에 남겨 둔다 —
    //    안 그러면 종이로 뽑을 때 이 카드가 통째로 빠진다(결정 0020).
    expect(gap.querySelector('.card__body')?.hasAttribute('hidden')).toBe(true);
    // …그래도 "무엇이 들어 있는지"는 접은 채로 읽힌다.
    expect(gap.querySelector('.card__summary')?.textContent).toBe(
      '국세청 기준시가 · 구 상가 단가 · 부동산원 임대료 — 층마다 나란히',
    );
  });

  it('접힌 카드를 누르면 그 자리에서 내용이 펼쳐진다', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => {
      expect(container.querySelectorAll('.card')).toHaveLength(Object.keys(SECTION_PLAN).length);
      // 로딩 카드도 한 장으로 세어지므로 장수만 기다리면 경주가 남는다 — 응답이
      // 전부 자리 잡은 뒤에만 배치·상태·요약을 읽는다(본문 없는 카드는 버튼이 없어
      // aria-expanded 판독이 false 로 읽히는 것이 이 경주의 증상이었다).
      expect(container.textContent).not.toContain('불러오는 중');
    });

    fireEvent.click(container.querySelector('.gap .card__toggle')!);
    expect(container.querySelector('.gap .card__body')?.hasAttribute('hidden')).toBe(false);
    expect(container.querySelector('.gap__row[data-floor="1"] .gap__cell--base .gap__val')?.textContent).toBe('410만');
  });

  it('펼쳐진 카드를 누르면 접히고, 요약만 남는다', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => {
      expect(container.querySelectorAll('.card')).toHaveLength(Object.keys(SECTION_PLAN).length);
      // 로딩 카드도 한 장으로 세어지므로 장수만 기다리면 경주가 남는다 — 응답이
      // 전부 자리 잡은 뒤에만 배치·상태·요약을 읽는다(본문 없는 카드는 버튼이 없어
      // aria-expanded 판독이 false 로 읽히는 것이 이 경주의 증상이었다).
      expect(container.textContent).not.toContain('불러오는 중');
    });

    const floorsCard = container.querySelector('.card--floors')!;
    expect(floorsCard.querySelectorAll('.floor')).toHaveLength(2);

    fireEvent.click(floorsCard.querySelector('.card__toggle')!);
    // 층 줄은 자리에 남되 **감춰진다**(결정 0020 — 종이로 뽑을 때 되살려야 한다).
    expect(floorsCard.querySelector('.card__body')?.hasAttribute('hidden')).toBe(true);
    expect(floorsCard.querySelector('.card__summary')?.textContent).toBe('층 2개 · 점포 4곳');
  });

  it('카드 머리·요약에는 금칙어(절대 규칙 2)가 한 글자도 없다', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => {
      expect(container.querySelectorAll('.card')).toHaveLength(Object.keys(SECTION_PLAN).length);
      // 로딩 카드도 한 장으로 세어지므로 장수만 기다리면 경주가 남는다 — 응답이
      // 전부 자리 잡은 뒤에만 배치·상태·요약을 읽는다(본문 없는 카드는 버튼이 없어
      // aria-expanded 판독이 false 로 읽히는 것이 이 경주의 증상이었다).
      expect(container.textContent).not.toContain('불러오는 중');
    });

    const heads = readCards(container)
      .map((c) => `${c.title} ${c.role} ${c.summary}`)
      .join(' ');
    for (const banned of ['적정가격', '적정가', '평가액', '감정가', '가치평가']) {
      expect(heads.includes(banned)).toBe(false);
    }
  });

  it('요약 줄에는 **값**을 적지 않는다 (값과 근거는 한 몸이다 — 절대 규칙 3)', async () => {
    // 요약 한 줄에는 근거 단계·표본 수를 함께 실을 자리가 없다. 그래서 여기에는
    // "몇 개인지"만 적고 금액·단가는 본문에서만 낸다.
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => {
      expect(container.querySelectorAll('.card')).toHaveLength(Object.keys(SECTION_PLAN).length);
      // 로딩 카드도 한 장으로 세어지므로 장수만 기다리면 경주가 남는다 — 응답이
      // 전부 자리 잡은 뒤에만 배치·상태·요약을 읽는다(본문 없는 카드는 버튼이 없어
      // aria-expanded 판독이 false 로 읽히는 것이 이 경주의 증상이었다).
      expect(container.textContent).not.toContain('불러오는 중');
    });

    const summary = container.querySelector('.gap .card__summary')?.textContent ?? '';
    expect(summary).not.toContain('억');
    expect(summary).not.toContain('㎡당');
  });

  it('요약 칸이 카드마다 제 값을 말한다 (접힘 ≠ 숨김)', async () => {
    // 요약은 접었을 때 남는 유일한 정보다. 한 칸이 조용히 빈 문자열이 되어도 화면은
    // 멀쩡해 보이므로(줄만 비어 보인다) 다섯 칸을 통째로 못 박는다.
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => {
      expect(container.querySelectorAll('.card')).toHaveLength(Object.keys(SECTION_PLAN).length);
      // 로딩 카드도 한 장으로 세어지므로 장수만 기다리면 경주가 남는다 — 응답이
      // 전부 자리 잡은 뒤에만 배치·상태·요약을 읽는다(본문 없는 카드는 버튼이 없어
      // aria-expanded 판독이 false 로 읽히는 것이 이 경주의 증상이었다).
      expect(container.textContent).not.toContain('불러오는 중');
    });

    expect(readCards(container).map((c) => c.summary)).toEqual([
      '역삼역(발달상권)출처: 서울특별시 상권분석서비스',
      '층 2개 · 점포 4곳',
      '속한 상권 1개 · 반경 500m 이내 402곳',
      '이 땅 거래 1건 · 강남구 층대별 단가 (상가 거래 기준)',
      // 층별 공표값 — 값 없이 무엇이 들어 있는지만(👤 물결 1-C2 · 비율 0 · 결정 0041 제목과 맞춤).
      '국세청 기준시가 · 구 상가 단가 · 부동산원 임대료 — 층마다 나란히',
      // ⛔ 임대 카드는 첫 화면에서 **접혀 있다** — 그래서 이 한 줄이 접은 채로 읽히는
      //    유일한 내용이다(2026-09-01 감사 전까지 이 줄은 한 번도 검사된 적이 없었다).
      '공실률 · ㎡당 임대료 · 투자수익률 · 2026년 2분기 조사',
      // 개업·폐업 카드는 상권 이름과 언제까지의 자료인지만 — 값은 적지 않는다(결정 0033 · 👤).
      '역삼역 · 2026년 2분기까지 서울시 공표',
      // 빈 카드 셋 — 서울 건물이면 셋 다 이 한 줄(👤 결정 0036 결정 2 · 물결 1-B).
      '지금은 비어 있음',
      '지금은 비어 있음',
      '지금은 비어 있음',
    ]);
  });

  it('★ 빈 카드 셋은 아무것도 부르지 않는다 · 대전 건물이면 매출·유동인구 요약이 그 사실 한 줄', async () => {
    const { container } = render(<FloorStack building={building({ pnu: '3011010700108770000' })} />);
    await waitFor(() => {
      expect(container.querySelectorAll('.card')).toHaveLength(Object.keys(SECTION_PLAN).length);
      expect(container.textContent).not.toContain('불러오는 중');
    });
    const summaryOf = (cls: string) => container.querySelector(`.${cls} .card__summary`)?.textContent;
    expect(summaryOf('card--sales')).toBe('대전은 아직 받지 않았습니다');
    expect(summaryOf('card--pop')).toBe('대전은 아직 받지 않았습니다');
    expect(summaryOf('card--history')).toBe('지금은 비어 있음');
    // 빈 카드 셋은 종이에서 빠지는 이름표를 단다(인쇄 규칙은 E2E 가 본다).
    expect(container.querySelectorAll('.card--empty')).toHaveLength(3);
    // ⛔ 부른 함수는 원래 카드들 것뿐이다 — 빈 카드용 함수 이름이 하나도 없다.
    for (const c of rpcCalls) expect(c.fn).not.toMatch(/sales|pop|history|empty/i);
  });

  it('구 이름을 모르면 그 조각을 빼고 적는다 ("null 층대별 단가"가 되지 않게)', async () => {
    // 구 이름은 서버가 준 값이고, 안 올 수도 있다. 그때 이름 자리를 빈 채로 이어 붙이면
    // 화면에 'null' 이나 'undefined' 가 그대로 찍힌다.
    responses.txStats = {
      data: bands({ '1층': 213 }).map((b) => ({ ...b, sigungu_nm: null })),
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => {
      expect(container.querySelectorAll('.card')).toHaveLength(Object.keys(SECTION_PLAN).length);
      // 로딩 카드도 한 장으로 세어지므로 장수만 기다리면 경주가 남는다 — 응답이
      // 전부 자리 잡은 뒤에만 배치·상태·요약을 읽는다(본문 없는 카드는 버튼이 없어
      // aria-expanded 판독이 false 로 읽히는 것이 이 경주의 증상이었다).
      expect(container.textContent).not.toContain('불러오는 중');
    });

    const summary = container.querySelector('.tx .card__summary')?.textContent ?? '';
    expect(summary).toBe('이 땅 거래 1건 · 층대별 단가 (상가 거래 기준)');
    expect(summary).not.toContain('null');
    expect(summary).not.toContain('undefined');
  });

  it('층 스택의 섹션은 전부 카드다 (틀을 안 쓰고 새 섹션을 끼워 넣지 못하게)', async () => {
    // `.card` 만 세면 "카드 class 를 안 붙인 섹션"이 조용히 늘어난다 — 그 섹션은 제목도
    // 역할 태그도 접기도 없이 화면에 붙는다. 겉의 section 수와 배치표 칸 수를 맞춰 막는다.
    //
    // ⚠️ 이 시험만은 **배치표의 카드가 전부 뜨는 상태**를 만들어야 한다. 곁다리 카드들은
    //    자료가 없으면 스스로 사라지므로(그게 정상이다), 기본값 그대로 두면 "섹션 수 =
    //    배치표 칸 수"가 자료 유무 때문에 어긋난다 — 여기서 보려는 것은 그게 아니다.
    responses.industryMix = {
      data: { snapshot_ym: '202606', radius_m: 500, districts: [], radius: { total: 3, cats: [] } },
      error: null,
    };
    responses.rent = {
      data: [
        {
          district_nm: '역삼역',
          rone_region_nm: '서울>강남>테헤란로',
          bld_type: '집합상가',
          quarter: '2026Q2',
          vacancy_rate: 10.08,
          rent_per_m2: 27.06,
          yield_rate: 0.82,
        },
      ],
      error: null,
    };
    responses.openclose = {
      data: [
        {
          status: 'ok',
          district_id: '3120189',
          district_nm: '역삼역',
          district_type: '발달상권',
          latest_quarter: '20262',
          quarters: [
            {
              quarter: '20262',
              similr_induty_stor_co: 441,
              stor_co: 378,
              frc_stor_co: 63,
              opbiz_stor_co: 5,
              clsbiz_stor_co: 9,
              opbiz_rt: 1.13,
              clsbiz_rt: 2.04,
            },
          ],
          industries: null,
          other_industries: null,
          window_quarters: ['20262'],
        },
      ],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => {
      expect(container.querySelectorAll('.card')).toHaveLength(
        Object.keys(SECTION_PLAN).length,
      );
      // 로딩 카드도 한 장으로 세어지므로 장수만 기다리면 경주가 남는다 — 응답이
      // 전부 자리 잡은 뒤에만 배치·상태·요약을 읽는다(본문 없는 카드는 버튼이 없어
      // aria-expanded 판독이 false 로 읽히는 것이 이 경주의 증상이었다).
      expect(container.textContent).not.toContain('불러오는 중');
    });

    const sections = container.querySelectorAll('.stack > section');
    expect(sections).toHaveLength(Object.keys(SECTION_PLAN).length);
    for (const el of sections) expect(el.classList.contains('card')).toBe(true);
  });

  it('상권 카드는 답과 출처를 요약에 두고, 읽는 법만 본문에 둔다', async () => {
    // 출처표시(공공누리 1유형)는 접었을 때 사라지면 안 된다.
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => {
      expect(container.querySelectorAll('.card')).toHaveLength(Object.keys(SECTION_PLAN).length);
      // 로딩 카드도 한 장으로 세어지므로 장수만 기다리면 경주가 남는다 — 응답이
      // 전부 자리 잡은 뒤에만 배치·상태·요약을 읽는다(본문 없는 카드는 버튼이 없어
      // aria-expanded 판독이 false 로 읽히는 것이 이 경주의 증상이었다).
      expect(container.textContent).not.toContain('불러오는 중');
    });

    const dist = container.querySelector('.card--district')!;
    const summary = dist.querySelector('.card__summary')?.textContent ?? '';
    expect(summary).toContain('역삼역(발달상권)');
    expect(summary).toContain('출처: 서울특별시 상권분석서비스');

    fireEvent.click(dist.querySelector('.card__toggle')!);
    expect(dist.querySelector('.card__summary')?.textContent).toContain('출처: 서울특별시');
  });
});

describe('FloorStack — 호실 구성표 (결정 0032)', () => {
  /** 신구로자이 나인스에비뉴 2026-10-04 라이브 실호출 값 일부. */
  function summaryRows() {
    return [
      { floor_no: 35, unit_cnt: 10, median_area_m2: null, min_area_m2: null, max_area_m2: null, floor_kind: 'residential' },
      { floor_no: 8, unit_cnt: 10, median_area_m2: null, min_area_m2: null, max_area_m2: null, floor_kind: 'officetel' },
      { floor_no: 3, unit_cnt: 543, median_area_m2: 4.0, min_area_m2: 2.74, max_area_m2: 8.81, floor_kind: 'mixed' },
      { floor_no: 1, unit_cnt: 690, median_area_m2: 4.0, min_area_m2: 3.18, max_area_m2: 13.07, floor_kind: 'commercial' },
    ];
  }

  function stackFloors() {
    return [
      floor({ floor_no: 35, main_use: '아파트' }),
      floor({ floor_no: 8, main_use: '오피스텔' }),
      floor({ floor_no: 3 }),
      floor({ floor_no: 1 }),
    ];
  }

  /** 한 쪽(page)의 호 목록을 지어 준다 — 이름은 '3-001호' 꼴, total 은 543. */
  function unitsPage(args: Record<string, unknown>) {
    const offset = Number(args.p_offset ?? 0);
    const limit = Number(args.p_limit ?? 50);
    const rows = [];
    for (let i = offset; i < Math.min(offset + limit, 543); i++) {
      rows.push({ ho: `3-${String(i + 1).padStart(3, '0')}호`, excl_area_m2: 4.0, total_cnt: 543 });
    }
    return { data: rows, error: null };
  }

  function floorButton(container: HTMLElement, label: string): HTMLElement {
    const btn = [...container.querySelectorAll<HTMLElement>('.floor__row')].find(
      (b) => b.querySelector('.floor__label')?.textContent === label,
    );
    if (!btn) throw new Error(`층 줄을 못 찾음: ${label}`);
    return btn;
  }

  function unitCalls() {
    return rpcCalls.filter((c) => c.fn === 'list_floor_units');
  }

  beforeEach(() => {
    responses.floors = { data: stackFloors(), error: null };
    responses.unitSummary = { data: summaryRows(), error: null };
    responses.floorUnits = unitsPage;
  });

  it('층 줄 아래 둘째 줄에 층 종류별 요약을 적는다', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(4));
    const texts = [...container.querySelectorAll('.floor__units')].map((p) => p.textContent);
    expect(texts).toEqual([
      '세대 10',
      '오피스텔 10실',
      '호실 543칸 · 보통 4.0㎡ · 2.7~8.8㎡',
      '호실 690칸 · 보통 4.0㎡ · 3.2~13.1㎡',
    ]);
    // 요약은 층 버튼 **밖**이다 — 버튼 안이면 층 줄 칸 수가 늘고 버튼 이름이 길어진다.
    expect(container.querySelector('.floor__row .floor__units')).toBeNull();
    // '보통' 각주와 복층 각주, 등급 문단의 전용면적 문장이 함께 선다.
    expect(container.textContent).toContain("'보통'은 그 층 호실 전용면적의 가운데값입니다.");
    expect(container.textContent).toContain('여러 층에 걸친 호실은 걸친 층마다 한 번씩 셉니다.');
    // 👤 2026-10-04 사장님이 고르신 쉬운 말 글자 그대로(결정 0032).
    expect(container.textContent).toContain(
      '호실 목록은 건축물대장에 칸별로 적힌 내용 그대로입니다. 면적은 그 칸 안쪽만 잰 넓이라(복도·계단 몫은 빠짐) 분양 광고의 면적보다 작습니다. 어느 칸에 어떤 가게가 있는지는 자료가 없어 알 수 없습니다.',
    );
    expect(container.textContent).toContain(
      '이 호실 면적에 임대 카드의 ㎡당 임대료를 곱해도 이 호실의 월세가 아닙니다. 임대료는 동네(상권) 평균이고, 면적을 재는 방법도 다릅니다.',
    );
    // 금지어(절대 규칙 2)가 새 문장에도 없다.
    for (const w of ['적정가격', '적정가', '평가액', '감정가', '가치평가']) {
      expect(container.textContent).not.toContain(w);
    }
    // 요약이 붙었으니 "자료 없음" 안내는 없다.
    expect(container.querySelector('.floor__units-none')).toBeNull();
  });

  it('요약은 건물을 열 때 p_bld_id 라는 이름으로 bld_id 를 보낸다 (pnu 가 아니다)', async () => {
    render(<FloorStack building={building()} />);
    await waitFor(() =>
      expect(rpcCalls.find((c) => c.fn === 'list_unit_floor_summary')).toBeTruthy(),
    );
    const call = rpcCalls.find((c) => c.fn === 'list_unit_floor_summary')!;
    expect(call.args).toEqual({ p_bld_id: '1168010100-1' });
  });

  it('섞인 층을 펼치면 그때 목록 50줄을 부르고, 섞임 안내를 붙이며, 더 보기로 이어 붙인다', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(4));
    // 펼치기 전에는 목록 요청이 하나도 안 나갔다(그때 부른다).
    expect(unitCalls()).toHaveLength(0);

    fireEvent.click(floorButton(container, '3층'));
    await waitFor(() => expect(container.querySelectorAll('.units__list li')).toHaveLength(50));
    expect(unitCalls()[0].args).toEqual({
      p_bld_id: '1168010100-1',
      p_floor_no: 3,
      p_limit: 50,
      p_offset: 0,
    });
    const col = container.querySelector('.units')!;
    expect(col.querySelector('.detail__h')?.textContent).toContain('호실 (543)');
    // 셋째 칸 제목의 작은 출처 글은 쉬운 말로 — '전유부' 는 더 이상 화면에 없다(2026-10-05).
    expect(col.querySelector('.detail__h')?.textContent).toContain('건축물대장 기준');
    expect(col.querySelector('.detail__h')?.textContent).not.toContain('전유부');
    expect(col.textContent).toContain(
      '이 층은 상가와 주거·오피스텔이 섞여 있어 함께 나옵니다 — 호실마다의 용도는 아직 담지 않았습니다.',
    );
    // ⛔ 우리가 안 담은 것을 대장 탓으로 말하지 않는다(결정 0032 :148).
    expect(container.textContent).not.toContain('대장 자료에 없습니다');
    expect(col.querySelector('.units__list li')?.textContent).toContain('3-001호');
    expect(col.querySelector('.units__list li')?.textContent).toContain('4.0㎡');

    fireEvent.click(screen.getByRole('button', { name: /더 보기/ }));
    await waitFor(() => expect(container.querySelectorAll('.units__list li')).toHaveLength(100));
    expect(unitCalls()[1].args).toMatchObject({ p_offset: 50, p_limit: 50 });
    // 앞 쪽 줄이 사라지지 않고 이어 붙는다.
    expect(container.querySelectorAll('.units__list li')[50].textContent).toContain('3-051호');
  });

  it('목록 제공 층(commercial)에는 섞임 안내를 붙이지 않는다', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(4));
    fireEvent.click(floorButton(container, '1층'));
    await waitFor(() => expect(container.querySelectorAll('.units__list li').length).toBeGreaterThan(0));
    expect(container.querySelector('.units__mixed')).toBeNull();
    expect(unitCalls()[0].args).toMatchObject({ p_floor_no: 1 });
  });

  it('⛔ 주거·오피스텔 층을 펼쳐도 목록을 부르지 않고 안내 한 줄만 적는다', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(4));

    fireEvent.click(floorButton(container, '35층'));
    await waitFor(() => expect(container.querySelector('.units')).toBeTruthy());
    expect(container.querySelector('.units')!.textContent).toContain(
      '주거·오피스텔 층은 호 목록을 보여 주지 않습니다.',
    );
    fireEvent.click(floorButton(container, '8층'));
    await waitFor(() =>
      expect(container.querySelector('.units')!.textContent).toContain('호실 (10)'),
    );
    // 두 층을 다 열어 봤어도 목록 요청은 0번이다.
    await new Promise((r) => setTimeout(r, 0));
    expect(unitCalls()).toHaveLength(0);
    expect(container.querySelector('.units__list')).toBeNull();
  });

  it('호 이름이 빈 칸(null·빈 글자)이면 "(호 이름 없음)", 나머지는 원문 그대로', async () => {
    responses.floorUnits = () => ({
      data: [
        { ho: '(홍길동)', excl_area_m2: 5.5, total_cnt: 3 },
        { ho: null, excl_area_m2: 4.0, total_cnt: 3 },
        { ho: '', excl_area_m2: null, total_cnt: 3 },
      ],
      error: null,
    });
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(4));
    fireEvent.click(floorButton(container, '1층'));
    await waitFor(() => expect(container.querySelectorAll('.units__list li')).toHaveLength(3));
    const names = [...container.querySelectorAll('.units__list .detail__name')].map((n) => n.textContent);
    expect(names).toEqual(['(홍길동)', '(호 이름 없음)', '(호 이름 없음)']);
    // 다 받았으면 더 보기가 없다.
    expect(screen.queryByRole('button', { name: /더 보기/ })).toBeNull();
  });

  it('펼친 층의 목록을 못 불러오면 조용히 비우지 않고 그렇다고 적는다', async () => {
    responses.floorUnits = () => ({ data: null, error: { message: 'boom' } });
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(4));
    fireEvent.click(floorButton(container, '1층'));
    await waitFor(() => expect(container.textContent).toContain('호 목록을 불러오지 못했습니다.'));
    expect(container.textContent).not.toContain('boom');
  });

  it('층 줄에 붙을 자리가 없는 호실을 카드 맨 아래 한 줄로 센다', async () => {
    responses.unitSummary = {
      data: [
        ...summaryRows(),
        { floor_no: 12, unit_cnt: 4, median_area_m2: null, min_area_m2: null, max_area_m2: null, floor_kind: 'residential' },
        { floor_no: 13, unit_cnt: 6, median_area_m2: 5, min_area_m2: 4, max_area_m2: 6, floor_kind: 'commercial' },
        { floor_no: null, unit_cnt: 7, median_area_m2: null, min_area_m2: null, max_area_m2: null, floor_kind: 'unknown' },
      ],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.floor__units-orphan')).toBeTruthy());
    expect(container.querySelector('.floor__units-orphan')!.textContent).toBe(
      '층을 알 수 없는 호실 7칸 · 층 목록에 없는 층 2개의 호실 10칸',
    );
    // 층 줄은 여전히 넷이다(없는 층을 지어 붙이지 않는다).
    expect(container.querySelectorAll('.floor__units')).toHaveLength(4);
  });

  it('호실 자료가 없는 건물(0줄)이면 카드 맨 아래 안내 — 건물 종류로 문구를 가른다', async () => {
    responses.unitSummary = { data: [], error: null };
    responses.floors = { data: [floor({ is_jiphap: false })], error: null };
    const { container, unmount } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.floor__units-none')).toBeTruthy());
    expect(container.querySelector('.floor__units-none')!.textContent).toBe(
      '이 건물에는 호실 자료가 없습니다 — 칸별로 등기가 나뉘지 않은 일반 건물이면 원래 없는 자료입니다.',
    );
    expect(container.querySelector('.floor__units')).toBeNull();
    // 호실 줄이 하나도 없으면 각주·등급 문장도 안 보탠다.
    expect(container.textContent).not.toContain('호실 목록은 건축물대장에 칸별로');
    expect(container.querySelector('.floor__units-note')).toBeNull();
    unmount();

    // 집합건물 · 그 땅에 동이 둘 이상 → "같은 땅 다른 동" 절이 붙는다.
    responses.floors = { data: [floor({ is_jiphap: true, bld_cnt_in_pnu: 2 })], error: null };
    const again = render(<FloorStack building={building({ bld_cnt_in_pnu: 2 })} />);
    await waitFor(() => expect(again.container.querySelector('.floor__units-none')).toBeTruthy());
    expect(again.container.querySelector('.floor__units-none')!.textContent).toBe(
      '이 건물에는 호실 자료가 없습니다 — 같은 땅 다른 동에 붙어 있을 수 있습니다.',
    );
    again.unmount();

    // ⛔ 집합건물이라도 그 땅에 동이 하나뿐이면 없는 동을 가리키지 않는다 — 중립 문장만.
    responses.floors = { data: [floor({ is_jiphap: true, bld_cnt_in_pnu: 1 })], error: null };
    const single = render(<FloorStack building={building()} />);
    await waitFor(() => expect(single.container.querySelector('.floor__units-none')).toBeTruthy());
    expect(single.container.querySelector('.floor__units-none')!.textContent).toBe(
      '이 건물에는 호실 자료가 없습니다.',
    );
  });

  it('⛔ 요약이 한 줄이라도 있으면 "자료 없음" 안내는 서지 않는다 (상호 배제)', async () => {
    // 층 줄에 못 붙는 층 하나뿐이어도 "자료가 없다"가 아니다 — 자료는 있다.
    responses.unitSummary = {
      data: [
        { floor_no: 40, unit_cnt: 3, median_area_m2: null, min_area_m2: null, max_area_m2: null, floor_kind: 'residential' },
      ],
      error: null,
    };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelector('.floor__units-orphan')).toBeTruthy());
    expect(container.querySelector('.floor__units-none')).toBeNull();
    expect(container.textContent).not.toContain('호실 자료가 없습니다');
  });

  it('각주·등급 문장은 층 줄에 실제로 붙은 요약을 보고 선다 (층 종류별 세 갈래)', async () => {
    const MEDIAN = "'보통'은 그 층 호실 전용면적의 가운데값입니다.";
    const MULTI = '여러 층에 걸친 호실은 걸친 층마다 한 번씩 셉니다.';
    const GRADE = '호실 목록은 건축물대장에 칸별로 적힌 내용 그대로입니다.';
    const none = { median_area_m2: null, min_area_m2: null, max_area_m2: null };

    // ① 주거 층뿐인 건물 — 면적을 안 적으므로 '보통'·곱셈 안내 없음, 복층 각주는 있다.
    responses.floors = { data: [floor({ floor_no: 5, main_use: '아파트' })], error: null };
    responses.unitSummary = {
      data: [{ floor_no: 5, unit_cnt: 4, floor_kind: 'residential', ...none }],
      error: null,
    };
    const a = render(<FloorStack building={building()} />);
    await waitFor(() => expect(a.container.querySelector('.floor__units')).toBeTruthy());
    expect(a.container.textContent).not.toContain(MEDIAN);
    expect(a.container.textContent).not.toContain(GRADE);
    expect(a.container.textContent).toContain(MULTI);
    a.unmount();

    // ② 층 줄에 못 붙고 따로 떨어진 호실뿐인 건물 — 셋 다 없음(따로 센 한 줄만 선다).
    responses.floors = { data: [floor({ floor_no: 1 })], error: null };
    responses.unitSummary = {
      data: [
        { floor_no: 9, unit_cnt: 6, median_area_m2: 5, min_area_m2: 4, max_area_m2: 6, floor_kind: 'commercial' },
        { floor_no: null, unit_cnt: 2, floor_kind: 'unknown', ...none },
      ],
      error: null,
    };
    const b = render(<FloorStack building={building()} />);
    await waitFor(() => expect(b.container.querySelector('.floor__units-orphan')).toBeTruthy());
    expect(b.container.querySelector('.floor__units')).toBeNull();
    expect(b.container.querySelector('.floor__units-note')).toBeNull();
    expect(b.container.textContent).not.toContain(GRADE);
    b.unmount();

    // ③ 섞인 층이 붙은 건물 — 셋 다 있다.
    responses.floors = { data: [floor({ floor_no: 3 })], error: null };
    responses.unitSummary = {
      data: [{ floor_no: 3, unit_cnt: 543, median_area_m2: 4, min_area_m2: 2.74, max_area_m2: 8.81, floor_kind: 'mixed' }],
      error: null,
    };
    const c = render(<FloorStack building={building()} />);
    await waitFor(() => expect(c.container.querySelector('.floor__units')).toBeTruthy());
    expect(c.container.textContent).toContain(MEDIAN);
    expect(c.container.textContent).toContain(MULTI);
    expect(c.container.textContent).toContain(GRADE);
  });

  it('더 보기를 받는 동안 버튼을 지우지 않고 "불러오는 중…"으로 잠근다', async () => {
    responses.floorUnits = (args) =>
      Number(args.p_offset ?? 0) === 0 ? unitsPage(args) : new Promise<never>(() => {});
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(4));
    fireEvent.click(floorButton(container, '3층'));
    await waitFor(() => expect(container.querySelectorAll('.units__list li')).toHaveLength(50));

    fireEvent.click(screen.getByRole('button', { name: /더 보기/ }));
    const btn = await screen.findByRole('button', { name: '불러오는 중…' });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
    // 받아 둔 줄은 그대로 남는다.
    expect(container.querySelectorAll('.units__list li')).toHaveLength(50);
  });

  it('다음 쪽이 0줄로 오면 끝으로 본다 — 눌러도 안 느는 더 보기를 남기지 않는다', async () => {
    responses.floorUnits = (args) =>
      Number(args.p_offset ?? 0) === 0 ? unitsPage(args) : { data: [], error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(4));
    fireEvent.click(floorButton(container, '3층'));
    await waitFor(() => expect(container.querySelectorAll('.units__list li')).toHaveLength(50));

    fireEvent.click(screen.getByRole('button', { name: /더 보기/ }));
    await waitFor(() => expect(unitCalls()).toHaveLength(2));
    await waitFor(() => expect(screen.queryByRole('button', { name: /더 보기|불러오는 중/ })).toBeNull());
    expect(container.querySelectorAll('.units__list li')).toHaveLength(50);
    expect(container.textContent).not.toContain('호 목록을 불러오지 못했습니다');
  });

  it('0줄로 끝난 뒤 다른 층을 펼치면 그 층은 처음부터 — 끝 표시가 옮겨 붙지 않는다', async () => {
    // 3층은 둘째 쪽이 0줄(끝) · 1층은 정상 쪽.
    responses.floorUnits = (args) =>
      args.p_floor_no === 3 && Number(args.p_offset ?? 0) > 0 ? { data: [], error: null } : unitsPage(args);
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(4));
    fireEvent.click(floorButton(container, '3층'));
    await waitFor(() => expect(container.querySelectorAll('.units__list li')).toHaveLength(50));
    fireEvent.click(screen.getByRole('button', { name: /더 보기/ }));
    await waitFor(() => expect(screen.queryByRole('button', { name: /더 보기|불러오는 중/ })).toBeNull());

    fireEvent.click(floorButton(container, '1층'));
    await waitFor(() =>
      expect(unitCalls().at(-1)?.args).toEqual({
        p_bld_id: '1168010100-1',
        p_floor_no: 1,
        p_limit: 50,
        p_offset: 0,
      }),
    );
    await waitFor(() => expect(container.querySelectorAll('.units__list li')).toHaveLength(50));
    // 3층의 '끝'이 1층으로 옮겨 붙었다면 여기서 더 보기가 없다.
    expect(screen.getByRole('button', { name: /더 보기/ })).toBeTruthy();
    expect(container.querySelectorAll('.units')).toHaveLength(1);
  });

  it('⛔ 같은 땅의 다른 동으로 바뀌면 요약을 다시 부른다 (의존은 bld_id — pnu 가 아니다)', async () => {
    const { container, rerender } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(4));
    rerender(<FloorStack building={building({ bld_id: '1168010100-2' })} />);
    await waitFor(() =>
      expect(rpcCalls.filter((c) => c.fn === 'list_unit_floor_summary')).toHaveLength(2),
    );
    const calls = rpcCalls.filter((c) => c.fn === 'list_unit_floor_summary');
    expect(calls[1].args).toEqual({ p_bld_id: '1168010100-2' });
  });

  it('⛔ 함수가 없거나(PGRST202) 실패하면 요약도 "자료 없음" 안내도 조용히 생략한다 (0줄과 섞지 않는다)', async () => {
    for (const bad of [
      { data: null, error: { code: 'PGRST202', message: 'function does not exist' } },
      { data: null, error: { message: 'boom' } },
      // 엉뚱한 모양(객체)도 실패다 — 빈 배열로 읽으면 "자료 없음"이라 거짓말을 한다.
      { data: { covered: true }, error: null },
    ]) {
      responses.unitSummary = bad;
      const { container, unmount } = render(<FloorStack building={building()} />);
      await waitFor(() => expect(container.querySelector('.floor__row')).toBeTruthy());
      await waitFor(() =>
        expect(rpcCalls.some((c) => c.fn === 'list_unit_floor_summary')).toBe(true),
      );
      await new Promise((r) => setTimeout(r, 0));
      expect(container.querySelector('.floor__units')).toBeNull();
      expect(container.querySelector('.floor__units-none')).toBeNull();
      // ⓘ '호실' 낱말 자체는 원래 등급 문단("어느 호실인지까지는")에 있다 — 새 글만 본다.
      expect(container.textContent).not.toContain('전유부');
      expect(container.textContent).not.toContain('건축물대장 기준');
      expect(container.textContent).not.toContain('PGRST202');
      unmount();
      rpcCalls.length = 0;
    }
  });
});

describe('FloorStack — 임대 카드 · 좌표 없는 건물 (2026-10-06)', () => {
  it('★ lat/lng 가 명시적 null 이고 빈 답이면 "조사 대상 아님" 이 아니라 "상권을 못 찾음" 이라 적는다', async () => {
    responses.rent = { data: [], error: null };
    render(<FloorStack building={building({ lat: null, lng: null })} />);
    expect(await screen.findByText('위치 정보가 없어 속한 상권을 찾지 못했습니다')).toBeTruthy();
    expect(screen.queryByText('부동산원 조사 대상 상권이 아닙니다')).toBeNull();
  });

  it('lat/lng 칸이 없으면(옛 서버 · undefined) 지금 글 그대로', async () => {
    responses.rent = { data: [], error: null };
    render(<FloorStack building={building()} />);
    expect(await screen.findByText('부동산원 조사 대상 상권이 아닙니다')).toBeTruthy();
  });

  it('좌표가 있는데 빈 답이면 지금 글 그대로 (정말 조사 대상이 아닌 자리)', async () => {
    responses.rent = { data: [], error: null };
    render(<FloorStack building={building({ lat: 37.5, lng: 127.03 })} />);
    expect(await screen.findByText('부동산원 조사 대상 상권이 아닙니다')).toBeTruthy();
  });
});

/**
 * 호실 구성표 고르기(결정 0036 결정 8 · 물결 1-C2) — 층별 화면 쪽. 고르기 단추는 App 에 있고, 여기서는
 * 고른 값(`unitPrintMode`)을 받아 ① 호 목록이 있는 층만 부르는가(주거·오피스텔 요청 0) ② 층 줄 아래에
 * 목록 + '이 층은 N호 더 있습니다' ③ 이미 펼친 층과 겹치면 한 벌만 ④ 실패한 층만 빠진다 ⑤ 상한 안내.
 */
describe('FloorStack — 호실 구성표 고르기 (물결 1-C2)', () => {
  const kinds: Record<number, string> = { 35: 'residential', 8: 'officetel', 3: 'mixed', 1: 'commercial', [-1]: 'commercial' };
  function summaryFor(nos: number[]) {
    return nos.map((n) => ({
      floor_no: n,
      unit_cnt: 60,
      median_area_m2: kinds[n] === 'residential' || kinds[n] === 'officetel' ? null : 4,
      min_area_m2: null,
      max_area_m2: null,
      floor_kind: kinds[n] ?? 'commercial',
    }));
  }
  /** 층마다 첫 쪽 — 3층만 60호(10호 더), 나머지는 2호. */
  function pageFor(args: Record<string, unknown>) {
    const no = Number(args.p_floor_no);
    const total = no === 3 ? 60 : 2;
    const rows = Array.from({ length: Math.min(50, total) }, (_, i) => ({
      ho: `${no}-${i + 1}호`,
      excl_area_m2: 4,
      total_cnt: total,
    }));
    return { data: rows, error: null };
  }
  const NOS = [35, 8, 3, 1, -1];

  beforeEach(() => {
    responses.floors = { data: NOS.map((n) => floor({ floor_no: n })), error: null };
    responses.unitSummary = { data: summaryFor(NOS), error: null };
    responses.floorUnits = pageFor;
  });

  const unitCalls = () => rpcCalls.filter((c) => c.fn === 'list_floor_units').map((c) => c.args as Record<string, unknown>);
  const listOf = (container: HTMLElement, no: number) =>
    [...container.querySelectorAll(`#floor-${no} .floor__unitprint-list li`)].map((li) => li.textContent);

  it('넣지 않음(기본)이면 아무 층도 안 부른다', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(5));
    expect(unitCalls()).toHaveLength(0);
    expect(container.querySelector('.floor__unitprint')).toBeNull();
  });

  it('★ 전부 — 호 목록이 있는 층만 첫 쪽(offset 0)으로 · 주거·오피스텔은 요청 0 · 50호 넘는 층은 남은 수 한 줄', async () => {
    const { container } = render(<FloorStack building={building()} unitPrintMode="all" />);
    await waitFor(() => expect(listOf(container, 3)).toHaveLength(50));
    await waitFor(() => expect(listOf(container, -1)).toHaveLength(2));
    expect(listOf(container, 1)).toEqual(['1-1호 4.0㎡', '1-2호 4.0㎡']);
    const asked = [...new Set(unitCalls().map((a) => `${a.p_floor_no}/${a.p_offset}/${a.p_limit}`))].sort();
    expect(asked).toEqual(['-1/0/50', '1/0/50', '3/0/50']);
    expect(unitCalls().some((a) => a.p_floor_no === 35 || a.p_floor_no === 8)).toBe(false);
    expect(container.querySelector('#floor-3 .floor__unitprint-more')?.textContent).toBe('이 층은 10호 더 있습니다');
    expect(container.querySelector('#floor-1 .floor__unitprint-more')).toBeNull();
    // 종이에서 줄 단위로 끊는 이름표.
    expect(container.querySelector('#floor-3')?.classList.contains('floor--unitprint')).toBe(true);
  });

  it('지하~3층 — 지하 + 1~3층만', async () => {
    responses.floors = { data: [floor({ floor_no: 5 }), ...NOS.map((n) => floor({ floor_no: n }))], error: null };
    responses.unitSummary = { data: summaryFor([5, ...NOS]), error: null };
    const { container } = render(<FloorStack building={building()} unitPrintMode="low" />);
    await waitFor(() => expect(listOf(container, -1)).toHaveLength(2));
    await waitFor(() => expect(listOf(container, 3)).toHaveLength(50));
    expect(unitCalls().some((a) => a.p_floor_no === 5)).toBe(false);
  });

  it('★ 이미 펼친 층과 겹치면 목록은 한 벌만(상세 쪽)', async () => {
    const { container } = render(<FloorStack building={building()} unitPrintMode="all" />);
    await waitFor(() => expect(listOf(container, 1)).toHaveLength(2));
    const row = [...container.querySelectorAll<HTMLElement>('.floor__row')].find(
      (b) => b.querySelector('.floor__label')?.textContent === '1층',
    )!;
    fireEvent.click(row);
    await waitFor(() => expect(container.querySelectorAll('#floor-1 .units__list li')).toHaveLength(2));
    expect(listOf(container, 1)).toHaveLength(0);
    // 양성 대조: 다른 층의 고른 목록은 그대로다.
    expect(listOf(container, -1)).toHaveLength(2);
  });

  it('★ 실패한 층은 그 층만 조용히 빠지고 다른 층은 선다', async () => {
    responses.floorUnits = (args) =>
      Number(args.p_floor_no) === 3 ? { data: null, error: { message: 'boom' } } : pageFor(args);
    const { container } = render(<FloorStack building={building()} unitPrintMode="all" />);
    await waitFor(() => expect(listOf(container, 1)).toHaveLength(2));
    await waitFor(() => expect(listOf(container, -1)).toHaveLength(2));
    expect(container.querySelector('#floor-3 .floor__unitprint')).toBeNull();
    expect(container.textContent).not.toContain('불러오지 못했습니다');
  });

  it('★ 전부 — 호 목록 있는 층이 30개를 넘으면 아래쪽 30개 층만 · 그렇다고 한 줄 · 동시 요청은 4개 이하', async () => {
    const many = Array.from({ length: 33 }, (_, i) => i + 1);
    responses.floors = { data: [...many].reverse().map((n) => floor({ floor_no: n })), error: null };
    responses.unitSummary = { data: summaryFor(many), error: null };
    let inflight = 0;
    let peak = 0;
    responses.floorUnits = ((args: Record<string, unknown>) => {
      inflight += 1;
      peak = Math.max(peak, inflight);
      // ⓘ 타이머 없이 다음 마이크로태스크에 답한다 — 실제로 흐른 시간에 기대지 않는다(전체 시험 부하에서
      //   setTimeout 판은 1초 안에 30층을 못 채워 흔들렸다). 일꾼 넷이 같은 틱에 요청을 내므로 최고치는 그대로 잰다.
      return Promise.resolve().then(() => {
        inflight -= 1;
        return pageFor(args);
      }) as unknown as Promise<never>;
    }) as typeof responses.floorUnits;
    const { container } = render(<FloorStack building={building()} unitPrintMode="all" />);
    await waitFor(() => expect(container.querySelectorAll('.floor__unitprint')).toHaveLength(30));
    expect(container.querySelector('.floor__unitprint-cap')?.textContent).toBe(
      '호실 목록이 있는 층이 32개라 아래쪽 30개 층만 넣었습니다', // 8층은 오피스텔이라 안 센다
    );
    expect(container.querySelector('#floor-31 .floor__unitprint')).not.toBeNull(); // 30번째(8층을 건너뛴다)
    expect(container.querySelector('#floor-32 .floor__unitprint')).toBeNull();
    expect(container.querySelector('#floor-8 .floor__unitprint')).toBeNull();
    expect(peak).toBeLessThanOrEqual(4);
    expect(peak).toBeGreaterThan(1);
  });
});

/**
 * 호실 구성표 고르기 — 검사 뒤 보완(물결 1-C2 · 👤 2026-10-11): 늦은 답 가드 · 바꿀 때 받은 층 다시 쓰기 ·
 * 받는 중/못 받은 층 한 줄 · 층 목록 카드는 손님이 직접 고를 때만 펼친다 · 호 목록 있는 층 수 알림.
 */
describe('FloorStack — 호실 구성표 고르기 보완 (물결 1-C2)', () => {
  const NOS = [5, 3, 1, -1];
  function summary() {
    return NOS.map((n) => ({
      floor_no: n,
      unit_cnt: 2,
      median_area_m2: 4,
      min_area_m2: null,
      max_area_m2: null,
      floor_kind: 'commercial',
    }));
  }
  function page(args: Record<string, unknown>) {
    const no = Number(args.p_floor_no);
    return { data: [{ ho: `${no}-1호`, excl_area_m2: 4, total_cnt: 1 }], error: null };
  }
  const calls = () => rpcCalls.filter((c) => c.fn === 'list_floor_units').map((c) => Number((c.args as Record<string, unknown>).p_floor_no));
  const lists = (container: HTMLElement) => container.querySelectorAll('.floor__unitprint');

  beforeEach(() => {
    responses.floors = { data: NOS.map((n) => floor({ floor_no: n })), error: null };
    responses.unitSummary = { data: summary(), error: null };
    responses.floorUnits = page;
  });

  it("★ '전부'로 바꾼 뒤 답이 오기 전에 '넣지 않음'으로 돌리면 늦은 답이 목록을 되살리지 않는다", async () => {
    const pending: Array<() => void> = [];
    responses.floorUnits = ((args: Record<string, unknown>) =>
      new Promise((r) => pending.push(() => r(page(args))))) as unknown as typeof responses.floorUnits;
    const { container, rerender } = render(<FloorStack building={building()} unitPrintMode="all" />);
    await waitFor(() => expect(pending.length).toBeGreaterThan(0));
    rerender(<FloorStack building={building()} unitPrintMode="none" />);
    await act(async () => {
      for (const go of pending.splice(0)) go();
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(lists(container)).toHaveLength(0);
    expect(container.querySelector('.floor__unitprint-loading')).toBeNull();
  });

  it("★ '지하~3층' → '전부' — 이미 받은 층은 다시 쓰고 새 층(5층)만 부른다", async () => {
    const { container, rerender } = render(<FloorStack building={building()} unitPrintMode="low" />);
    await waitFor(() => expect(lists(container)).toHaveLength(3));
    expect([...new Set(calls())].sort((a, b) => a - b)).toEqual([-1, 1, 3]);
    const before = container.querySelector('#floor-1 .floor__unitprint');
    rpcCalls.length = 0;
    rerender(<FloorStack building={building()} unitPrintMode="all" />);
    // 바꾼 그 순간에도 받은 층은 그대로 서 있다(깜빡임 0).
    expect(lists(container)).toHaveLength(3);
    await waitFor(() => expect(lists(container)).toHaveLength(4));
    expect(calls()).toEqual([5]);
    expect(container.querySelector('#floor-1 .floor__unitprint')).toBe(before);
  });

  it('★ 받는 동안 「호실 목록 불러오는 중 (N/M층)」 · 끝난 뒤 못 받은 층 수 한 줄', async () => {
    const pending: Array<() => void> = [];
    responses.floorUnits = ((args: Record<string, unknown>) =>
      new Promise((r) =>
        pending.push(() =>
          r(Number(args.p_floor_no) === 3 ? { data: null, error: { message: 'boom' } } : page(args)),
        ),
      )) as unknown as typeof responses.floorUnits;
    const { container } = render(<FloorStack building={building()} unitPrintMode="all" />);
    await waitFor(() =>
      expect(container.querySelector('.floor__unitprint-loading')?.textContent).toBe('호실 목록 불러오는 중 (0/4층)'),
    );
    await act(async () => {
      for (const go of pending.splice(0)) go();
      await new Promise((r) => setTimeout(r, 0));
    });
    await waitFor(() => expect(container.querySelector('.floor__unitprint-loading')).toBeNull());
    expect(container.querySelector('.floor__unitprint-failed')?.textContent).toBe('1개 층은 호실 목록을 못 불러왔습니다');
    expect(lists(container)).toHaveLength(3);
  });

  it('★ 층 목록 카드는 손님이 직접 고를 때(신호)만 펼친다 — 기본 고르기로는 접힌 카드 그대로', async () => {
    const { container, rerender } = render(
      <FloorStack building={building()} viewerRole="창업자" unitPrintMode="low" unitPrintOpenSignal={0} />,
    );
    await waitFor(() => expect(lists(container)).toHaveLength(3));
    const toggle = () => container.querySelector('.card--floors .card__toggle')!;
    // 창업자 표는 층 목록이 펼침이다 — 접어 둔 뒤 기본값만 다시 와도 그대로 접혀 있어야 한다.
    fireEvent.click(toggle());
    expect(toggle().getAttribute('aria-expanded')).toBe('false');
    rerender(<FloorStack building={building()} viewerRole="창업자" unitPrintMode="all" unitPrintOpenSignal={0} />);
    await waitFor(() => expect(lists(container)).toHaveLength(4));
    expect(toggle().getAttribute('aria-expanded')).toBe('false');
    // 접힌 채여도 본문(고른 목록)은 DOM 에 있다 — 종이에 나온다(결정 0020).
    expect(container.querySelector('.card--floors .card__body')?.hasAttribute('hidden')).toBe(true);
    // 양성 대조 — 손님이 직접 고르면(신호 +1) 펼친다.
    rerender(<FloorStack building={building()} viewerRole="창업자" unitPrintMode="all" unitPrintOpenSignal={1} />);
    await waitFor(() => expect(toggle().getAttribute('aria-expanded')).toBe('true'));
  });

  it('호 목록이 있는 층 수를 알린다(요약을 받은 뒤 · 고르기와 무관) · 0개도 알린다', async () => {
    const seen: Array<[string, number]> = [];
    render(<FloorStack building={building()} unitPrintMode="none" onUnitListedCount={(b, n) => seen.push([b, n])} />);
    await waitFor(() => expect(seen.at(-1)).toEqual(['1168010100-1', 4]));
    cleanup();
    seen.length = 0;
    responses.unitSummary = {
      data: [{ floor_no: 1, unit_cnt: 9, median_area_m2: null, min_area_m2: null, max_area_m2: null, floor_kind: 'residential' }],
      error: null,
    };
    render(<FloorStack building={building()} onUnitListedCount={(b, n) => seen.push([b, n])} />);
    await waitFor(() => expect(seen.at(-1)).toEqual(['1168010100-1', 0]));
  });
});

describe('FloorStack — 호실 크기 칸 (결정 0038 G · V3)', () => {
  const kinds: Record<number, string> = { 35: 'residential', 5: 'commercial', 3: 'mixed', 1: 'commercial' };
  const NOS = [35, 5, 3, 1];
  /** 1층 = 300 · 150 · 20 · 0 · 5층 = 900 · 40 · 3층 = 543호(쪽마다 50). */
  const FIXED: Record<number, Array<{ ho: string; excl_area_m2: number; total_cnt: number }>> = {
    1: [
      { ho: '101호', excl_area_m2: 300, total_cnt: 4 },
      { ho: '102호', excl_area_m2: 150, total_cnt: 4 },
      { ho: '103호', excl_area_m2: 20, total_cnt: 4 },
      { ho: '104호', excl_area_m2: 0, total_cnt: 4 },
    ],
    5: [
      { ho: '501호', excl_area_m2: 900, total_cnt: 2 },
      { ho: '502호', excl_area_m2: 40, total_cnt: 2 },
    ],
  };
  function pageFor(args: Record<string, unknown>) {
    const no = Number(args.p_floor_no);
    const offset = Number(args.p_offset ?? 0);
    if (FIXED[no]) return { data: offset === 0 ? FIXED[no] : [], error: null };
    const rows = [];
    for (let i = offset; i < Math.min(offset + 50, 543); i++) {
      rows.push({ ho: `3-${String(i + 1).padStart(3, '0')}호`, excl_area_m2: 4.0, total_cnt: 543 });
    }
    return { data: rows, error: null };
  }

  beforeEach(() => {
    responses.floors = { data: NOS.map((n) => floor({ floor_no: n })), error: null };
    responses.unitSummary = {
      data: NOS.map((n) => ({
        floor_no: n,
        unit_cnt: 4,
        median_area_m2: kinds[n] === 'residential' ? null : 4,
        min_area_m2: null,
        max_area_m2: null,
        floor_kind: kinds[n],
      })),
      error: null,
    };
    responses.floorUnits = pageFor;
  });

  function open(container: HTMLElement, label: string) {
    const btn = [...container.querySelectorAll<HTMLElement>('.floor__row')].find(
      (b) => b.querySelector('.floor__label')?.textContent === label,
    );
    if (!btn) throw new Error(`층 줄을 못 찾음: ${label}`);
    fireEvent.click(btn);
  }
  const widths = (root: Element | null) =>
    [...(root?.querySelectorAll<HTMLElement>('.ucell') ?? [])].map((c) => parseFloat(c.style.width));
  const labs = (root: Element | null) =>
    [...(root?.querySelectorAll('.ucell__lab') ?? [])].map((l) => [l.className, l.textContent]);

  it('펼친 층 — 칸 줄은 세 칸(구획·점포·호실) **위** 상세 첫 자식 한 줄(👤 2026-10-22 전체 폭) · 호실 칸 안엔 없음 · 폭 % = 면적 비례 · 면적 0 은 「–」 · 그림만 aria-hidden · 목록은 그대로', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(4));
    open(container, '1층');
    await waitFor(() => expect(container.querySelectorAll('#floor-1 .detail > .ucells .ucell')).toHaveLength(3));
    const detail = container.querySelector('#floor-1 .detail')!;
    const row = detail.querySelector(':scope > .ucells')!;
    // 상세의 **첫 자식**(세 칸보다 앞 — 읽는 차례 = 보이는 차례) · 전체 폭 이름표 · 호실 칸 안에는 칸 줄 0.
    expect(detail.firstElementChild).toBe(row);
    expect(row.classList.contains('ucells--detail')).toBe(true);
    expect(detail.querySelectorAll('.ucells')).toHaveLength(1);
    expect(detail.querySelector('.units .ucells')).toBeNull();
    const w = widths(row);
    [300 / 470, 150 / 470, 20 / 470].forEach((s, i) => expect(w[i]).toBeCloseTo(s * 100, 6));
    expect(row.querySelector('.ucells__strip')!.getAttribute('aria-hidden')).toBe('true');
    // 설명 글 · 「–」 · 복층 각주 — 글이라 aria-hidden 밖.
    const note = row.querySelector('.ucells__note')!;
    expect(note.closest('[aria-hidden]')).toBeNull();
    expect(note.textContent).toBe(
      '크기 비교이지 자리 배치가 아닙니다. 전용면적 값이 없는 호(칸 없음): 104호 –. 여러 층에 걸친 호실은 걸친 층마다 한 번씩 셉니다.',
    );
    expect(row.querySelector('.ucells__rest')).toBeNull();
    // 전체 폭 기준(넓은 500 · 휴대폰 180) — 넓은 벌은 101호·102호 · 휴대폰 벌은 없음(63.8% × 180 < 글자 폭).
    expect(labs(row)).toEqual([
      ['ucell__lab ucell__lab--w', '101호 · 300.0㎡'],
      ['ucell__lab ucell__lab--w', '102호 · 150.0㎡'],
    ]);
    // 목록 글은 한 글자도 안 바뀐다(104호 — 그대로).
    expect([...container.querySelectorAll('#floor-1 .units__list li')].map((li) => li.textContent)).toEqual([
      '101호300.0㎡',
      '102호150.0㎡',
      '103호20.0㎡',
      '104호—',
    ]);
  });

  it('넓은 칸 하나(95.7%)면 휴대폰 벌도 글자 「501호 · 900.0㎡」 · ★ 이름이 「호」뿐인 호는 면적만 「900.0㎡」(👤 2026-10-22)', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(4));
    open(container, '5층');
    await waitFor(() => expect(container.querySelectorAll('#floor-5 .detail > .ucells .ucell')).toHaveLength(2));
    expect(labs(container.querySelector('#floor-5 .detail > .ucells'))).toEqual([
      ['ucell__lab ucell__lab--w ucell__lab--n', '501호 · 900.0㎡'],
    ]);
    cleanup();
    FIXED[5][0].ho = '호';
    try {
      const again = render(<FloorStack building={building()} />).container;
      await waitFor(() => expect(again.querySelectorAll('.floor__units')).toHaveLength(4));
      open(again, '5층');
      await waitFor(() => expect(again.querySelectorAll('#floor-5 .detail > .ucells .ucell')).toHaveLength(2));
      expect(labs(again.querySelector('#floor-5 .detail > .ucells'))).toEqual([
        ['ucell__lab ucell__lab--w ucell__lab--n', '900.0㎡'],
      ]);
      // 목록은 원문 그대로(「호」).
      expect(again.querySelector('#floor-5 .units__list li')?.textContent).toBe('호900.0㎡');
    } finally {
      FIXED[5][0].ho = '501호';
    }
  });

  it('50호 넘는 층 — 칸 50 + 「그 밖 493호」 · 더 보기로 목록이 100줄이 돼도 칸은 50 그대로', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(4));
    open(container, '3층');
    const row = () => container.querySelector('#floor-3 .detail > .ucells');
    await waitFor(() => expect(row()?.querySelectorAll('.ucell')).toHaveLength(50));
    expect(row()?.querySelector('.ucells__rest')?.textContent).toBe('그 밖 493호');
    expect(widths(row()).every((v) => Math.abs(v - 2) < 1e-9)).toBe(true);
    fireEvent.click(container.querySelector<HTMLElement>('#floor-3 .units__more')!);
    await waitFor(() => expect(container.querySelectorAll('#floor-3 .units__list li')).toHaveLength(100));
    expect(row()?.querySelectorAll('.ucell')).toHaveLength(50);
    expect(row()?.querySelector('.ucells__rest')?.textContent).toBe('그 밖 493호');
  });

  it('주거 층은 목록이 0줄이라 칸도 없다 · 목록을 못 받으면 칸도 없다', async () => {
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(4));
    open(container, '35층');
    await waitFor(() => expect(container.querySelector('#floor-35 .units')).not.toBeNull());
    expect(container.querySelector('.ucells')).toBeNull();
    responses.floorUnits = () => ({ data: null, error: { message: 'boom' } });
    open(container, '1층');
    await waitFor(() => expect(container.querySelector('#floor-1 .units')?.textContent).toContain('호 목록을 불러오지 못했습니다.'));
    expect(container.querySelector('.ucells')).toBeNull();
  });

  it('전부 면적이 없으면 칸 줄 없이 「–」 한 줄만', async () => {
    FIXED[5] = [
      { ho: '501호', excl_area_m2: 0, total_cnt: 2 },
      { ho: '502호', excl_area_m2: -1, total_cnt: 2 },
    ];
    try {
      const { container } = render(<FloorStack building={building()} />);
      await waitFor(() => expect(container.querySelectorAll('.floor__units')).toHaveLength(4));
      open(container, '5층');
      await waitFor(() => expect(container.querySelector('#floor-5 .ucells__note')).not.toBeNull());
      expect(container.querySelector('#floor-5 .ucells__strip')).toBeNull();
      expect(container.querySelector('#floor-5 .ucells__note')?.textContent).toBe(
        '전용면적 값이 없는 호(칸 없음): 501호 – · 502호 –',
      );
    } finally {
      FIXED[5] = [
        { ho: '501호', excl_area_m2: 900, total_cnt: 2 },
        { ho: '502호', excl_area_m2: 40, total_cnt: 2 },
      ];
    }
  });

  it('인쇄 호실 구성표(지하~3층)에도 같은 칸 줄 — 목록 위 · 넓은 기준(480)에선 102호까지 글자 · 휴대폰 기준(230)은 101호만', async () => {
    const { container } = render(<FloorStack building={building()} unitPrintMode="low" />);
    await waitFor(() => expect(container.querySelectorAll('#floor-1 .floor__unitprint .ucell')).toHaveLength(3));
    const box = container.querySelector('#floor-1 .floor__unitprint')!;
    expect(box.querySelector('.ucells')!.compareDocumentPosition(box.querySelector('.floor__unitprint-list')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(labs(box)).toEqual([
      ['ucell__lab ucell__lab--w ucell__lab--n', '101호 · 300.0㎡'],
      ['ucell__lab ucell__lab--w', '102호 · 150.0㎡'],
    ]);
    await waitFor(() => expect(container.querySelectorAll('#floor-3 .floor__unitprint .ucell')).toHaveLength(50));
    expect(container.querySelector('#floor-3 .floor__unitprint .ucells__rest')?.textContent).toBe('그 밖 493호');
    // 5층(계획 밖)·35층(주거)은 칸 줄 없음.
    expect(container.querySelector('#floor-5 .ucells')).toBeNull();
    expect(container.querySelector('#floor-35 .ucells')).toBeNull();
  });
});

describe('FloorStack — 개별공시지가 한 줄 (결정 0036 결정 7)', () => {
  const LINE = '개별공시지가 땅 1㎡당 4,523만원 · 2026년 공시 (이 건물이 선 땅 · 공시가격 — 시세가 아닙니다)';

  function landCalls() {
    return rpcCalls.filter((c) => c.fn === 'get_parcel_land_price');
  }

  it('★ 값이 오면 머리의 사양 칸 아래에 한 줄 — 인자는 p_pnu', async () => {
    responses.landPrice = () => ({
      data: [{ land_price: 45_230_000, land_price_year: 2026 }],
      error: null,
    });
    const { container } = render(<FloorStack building={building()} />);
    const line = await screen.findByText(LINE);
    expect(line.closest('.stack__head')).toBeTruthy();
    expect(container.querySelectorAll('.stack__land')).toHaveLength(1);
    // 배지(👤 2026-10-11) — 기준시가 줄과 같은 `grade__badge` 꼴 · 낱말은 '공시'(기준시가는 '고시').
    const badge = container.querySelector('.stack__land .grade__badge');
    expect(badge?.textContent).toBe('A등급 · 공식 공시');
    expect(line.classList.contains('stack__land-text')).toBe(true);
    expect(landCalls()).toEqual([
      { fn: 'get_parcel_land_price', args: { p_pnu: '1168010100100010000' } },
    ]);
  });

  it.each([
    ['함수 없음(PGRST202)', { data: null, error: { code: 'PGRST202', message: 'function does not exist' } }],
    ['그 밖의 오류', { data: null, error: { message: 'boom' } }],
    ['0줄(값 없는 필지)', { data: [], error: null }],
    ['모양 이상(값이 글자)', { data: [{ land_price: '45230000', land_price_year: 2026 }], error: null }],
    ['모양 이상(연도 없음)', { data: [{ land_price: 45_230_000, land_price_year: null }], error: null }],
  ])('%s 이면 줄 자체가 없다 — "자료 없음"이라 적지 않는다', async (_label, res) => {
    responses.landPrice = () => res;
    const { container } = render(<FloorStack building={building()} />);
    await screen.findByText('테스트빌딩');
    await waitFor(() => expect(landCalls()).toHaveLength(1));
    // 응답이 처리될 틈을 준다(then 한 바퀴).
    await new Promise((r) => setTimeout(r, 0));
    expect(container.querySelector('.stack__land')).toBeNull();
    expect(container.textContent).not.toContain('개별공시지가');
    expect(container.textContent).not.toContain('PGRST202');
  });

  // ⓘ 이 컴포넌트 하나 안의 성질이다 — 실제 화면은 App 이 건물마다 FloorStack 을 새로 만들어(key) 다시 부른다.
  it('같은 컴포넌트에서 같은 땅의 다른 동으로 바뀌면 다시 묻지 않는다 — 의존 [building.pnu]', async () => {
    responses.landPrice = () => ({
      data: [{ land_price: 45_230_000, land_price_year: 2026 }],
      error: null,
    });
    const { rerender } = render(<FloorStack building={building()} />);
    await screen.findByText(LINE);
    rerender(<FloorStack building={building({ bld_id: '1168010100-2' })} />);
    await screen.findByText(LINE);
    expect(landCalls()).toHaveLength(1);
  });

  it('★ 필지가 바뀐 뒤 늦게 온 옛 필지의 답은 버린다', async () => {
    let releaseOld: (v: { data: unknown; error: unknown }) => void = () => {};
    responses.landPrice = (args) =>
      args.p_pnu === '1168010100100010000'
        ? new Promise((resolve) => {
            releaseOld = resolve;
          })
        : { data: [{ land_price: 8_500, land_price_year: 2025 }], error: null };
    const { rerender, container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(landCalls()).toHaveLength(1));
    rerender(
      <FloorStack building={building({ bld_id: '1168010100-9', pnu: '1168010100100090000' })} />,
    );
    const NEW = '개별공시지가 땅 1㎡당 8,500원 · 2025년 공시 (이 건물이 선 땅 · 공시가격 — 시세가 아닙니다)';
    await screen.findByText(NEW);
    releaseOld({ data: [{ land_price: 45_230_000, land_price_year: 2026 }], error: null });
    await new Promise((r) => setTimeout(r, 0));
    expect(container.querySelector('.stack__land-text')?.textContent).toBe(NEW);
  });
});

/**
 * 긴 카드 창(S2 · 👤 2026-10-15 "처음 10줄만 먼저 보여 주고 「전부 보기」로 펼친다" · "펼친 뒤 다시 짧게 접는 단추도 둔다").
 * 층 목록은 검사 뒤 다시 여쭤 **「아래 10줄」**(👤 2026-10-15 저녁) — 서버 순서(위층부터)는 그대로, 앞쪽 위층 줄이 숨고
 * 단추 「위층 전부 보기 (N개 층 더)」는 목록 맨 위. 거래 목록은 처음 10건 + 아래 단추 그대로.
 * ⓘ jsdom 은 styles.css 를 안 읽으므로 '화면에서 숨음'은 이름표 `list__folded` 로 본다 — 실제로 숨는지·종이에
 *   전부 나오는지는 E2E 「BB」가 본다. 줄은 늘 전부 DOM 에 있다(`floor-N` id 가 늘 있어야 건너뛰기가 된다).
 */
describe('FloorStack — 긴 카드 창 (S2)', () => {
  /** 층을 서버 순서(내림차순)로 n개 — n층부터 1층까지. */
  function stackOf(n: number) {
    return { data: Array.from({ length: n }, (_, i) => floor({ floor_no: n - i })), error: null };
  }
  const floorFold = (c: HTMLElement) => c.querySelector<HTMLButtonElement>('.card--floors .list__fold');
  const txFold = (c: HTMLElement) => c.querySelector<HTMLButtonElement>('.tx__list ~ .list__fold');
  /** 화면에 보이는(숨김 이름표가 없는) 층 줄의 id. */
  const shownFloors = (c: HTMLElement) =>
    [...c.querySelectorAll('.floors > li:not(.list__folded)')].map((li) => li.id);
  const foldedFloors = (c: HTMLElement) =>
    [...c.querySelectorAll('.floors > li.list__folded')].map((li) => li.id);
  const shownTx = (c: HTMLElement) => c.querySelectorAll('.tx__list > li:not(.list__folded)').length;

  let scrolled: Element[];
  beforeEach(() => {
    scrolled = [];
    // jsdom 에는 scrollIntoView 가 없다 — 어느 요소로 굴렀는지만 적어 둔다.
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value: function (this: Element) {
        scrolled.push(this);
      },
    });
  });
  afterEach(() => {
    delete (HTMLElement.prototype as { scrollIntoView?: unknown }).scrollIntoView;
  });

  it('★ 층이 11줄 이상이면 아래 10줄만 보이고 목록 맨 위에 「위층 전부 보기 (N개 층 더)」 — 줄은 전부 DOM 에', async () => {
    responses.floors = stackOf(12);
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floors > li')).toHaveLength(12));
    // 아래 10줄 — 서버 순서(위층부터) 그대로, 앞쪽 위층 둘이 숨는다.
    expect(shownFloors(container)).toEqual(Array.from({ length: 10 }, (_, i) => `floor-${10 - i}`));
    expect(foldedFloors(container)).toEqual(['floor-12', 'floor-11']);
    const btn = floorFold(container)!;
    expect(btn.textContent).toBe('위층 전부 보기 (2개 층 더)');
    expect(btn.getAttribute('aria-expanded')).toBe('false');
    const list = container.querySelector('.floors')!;
    expect(btn.getAttribute('aria-controls')).toBe(list.id);
    expect(document.getElementById(btn.getAttribute('aria-controls')!)).toBe(list);
    // 단추는 목록 **위**(👤 그림).
    expect(btn.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('★ 위층 전부 보기 → 전부 · 다시 접기 → 아래 10줄 + 층 목록 카드 머리로 굴린다', async () => {
    responses.floors = stackOf(12);
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(floorFold(container)).toBeTruthy());
    fireEvent.click(floorFold(container)!);
    expect(shownFloors(container)).toHaveLength(12);
    expect(floorFold(container)!.textContent).toBe('층 목록 접기');
    expect(floorFold(container)!.getAttribute('aria-expanded')).toBe('true');
    // 펼칠 때는 굴리지 않는다.
    expect(scrolled).toHaveLength(0);

    fireEvent.click(floorFold(container)!);
    expect(foldedFloors(container)).toEqual(['floor-12', 'floor-11']);
    expect(floorFold(container)!.textContent).toBe('위층 전부 보기 (2개 층 더)');
    await waitFor(() => expect(scrolled).toHaveLength(1));
    expect(scrolled[0]).toBe(container.querySelector('.card--floors .card__h'));
  });

  it('★ 경계 — 10줄이면 단추도 숨김도 없고(지금 그대로), 11줄이면 맨 위 한 줄이 숨고 단추가 선다(양성 대조)', async () => {
    responses.floors = stackOf(10);
    const first = render(<FloorStack building={building()} />);
    await waitFor(() => expect(first.container.querySelectorAll('.floors > li')).toHaveLength(10));
    expect(floorFold(first.container)).toBeNull();
    expect(first.container.querySelector('.list__folded')).toBeNull();
    first.unmount();

    responses.floors = stackOf(11);
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(container.querySelectorAll('.floors > li')).toHaveLength(11));
    expect(floorFold(container)?.textContent).toBe('위층 전부 보기 (1개 층 더)');
    expect(foldedFloors(container)).toEqual(['floor-11']);
  });

  it('★ 다른 건물을 열면 층 목록은 다시 아래 10줄', async () => {
    responses.floors = stackOf(12);
    const { container, rerender } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(floorFold(container)).toBeTruthy());
    fireEvent.click(floorFold(container)!);
    expect(shownFloors(container)).toHaveLength(12);
    rerender(<FloorStack building={building({ bld_id: '1168010100-9' })} />);
    await waitFor(() => expect(shownFloors(container)).toHaveLength(10));
    expect(floorFold(container)!.getAttribute('aria-expanded')).toBe('false');
  });

  /** 12층~1층 + 지하 1층 = 13줄 — 숨는 줄은 앞쪽 셋(12·11·10층). */
  const WITH_BASEMENT = {
    data: [...Array.from({ length: 12 }, (_, i) => floor({ floor_no: 12 - i })), floor({ floor_no: -1 })],
    error: null,
  };

  /** 층마다 호 목록이 있는 상가 층 요약 + 한 쪽짜리 호 목록(호실 구성표 고르기용). */
  function unitsFor(nos: number[]) {
    responses.unitSummary = {
      data: nos.map((n) => ({
        floor_no: n,
        unit_cnt: 2,
        median_area_m2: 4,
        min_area_m2: null,
        max_area_m2: null,
        floor_kind: 'commercial',
      })),
      error: null,
    };
    responses.floorUnits = (args) => ({
      data: [{ ho: `${Number(args.p_floor_no)}-1호`, excl_area_m2: 4, total_cnt: 1 }],
      error: null,
    });
  }
  const NOS_WITH_BASEMENT = [...Array.from({ length: 12 }, (_, i) => 12 - i), -1];

  it('★ 호실 구성표를 직접 골랐는데 고른 층 중 숨은 위층이 있으면 층 목록을 전부로 펼친다(맹점 B)', async () => {
    responses.floors = WITH_BASEMENT;
    unitsFor(NOS_WITH_BASEMENT);
    const { container, rerender } = render(
      <FloorStack building={building()} unitPrintMode="low" unitPrintOpenSignal={0} />,
    );
    await waitFor(() => expect(foldedFloors(container)).toHaveLength(3));
    // '전부' = 12층까지 — 숨은 12·11·10층이 고른 층에 든다.
    rerender(<FloorStack building={building()} unitPrintMode="all" unitPrintOpenSignal={1} />);
    await waitFor(() => expect(foldedFloors(container)).toHaveLength(0));
    expect(floorFold(container)!.getAttribute('aria-expanded')).toBe('true');
  });

  it('호실 구성표를 직접 골라도 고른 층이 다 보이는 줄이면 층 목록은 접힌 그대로(양성 대조)', async () => {
    responses.floors = WITH_BASEMENT;
    unitsFor(NOS_WITH_BASEMENT);
    const { container, rerender } = render(
      <FloorStack building={building()} unitPrintMode="none" unitPrintOpenSignal={0} />,
    );
    await waitFor(() => expect(foldedFloors(container)).toHaveLength(3));
    // '지하~3층' = 지하 1·1·2·3층 — 전부 보이는 아래 10줄 안.
    rerender(<FloorStack building={building()} unitPrintMode="low" unitPrintOpenSignal={1} />);
    await waitFor(() => expect(container.querySelectorAll('.floor__unitprint')).toHaveLength(4));
    expect(foldedFloors(container)).toEqual(['floor-12', 'floor-11', 'floor-10']);
  });

  /** 그 층의 줄 단추를 눌러 펼친다. */
  const openRow = (no: number) =>
    fireEvent.click(document.getElementById(`floor-${no}`)!.querySelector('.floor__row')!);

  it('★ 접으면 숨는 줄에 열린 층이 있으면 닫는다(맹점 C)', async () => {
    responses.floors = stackOf(12);
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(floorFold(container)).toBeTruthy());
    fireEvent.click(floorFold(container)!);
    openRow(12);
    expect(container.querySelector('#floor-12 .detail')).toBeTruthy();
    fireEvent.click(floorFold(container)!);
    expect(container.querySelector('.floors .detail')).toBeNull();
    // 접기가 부른 굴리기를 이 시험 안에서 끝낸다(안 기다리면 다음 시험의 기록에 섞인다).
    await waitFor(() => expect(scrolled).toHaveLength(1));
  });

  it('접어도 보이는 줄에 열린 층은 그대로(양성 대조)', async () => {
    responses.floors = stackOf(12);
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(floorFold(container)).toBeTruthy());
    fireEvent.click(floorFold(container)!);
    openRow(1);
    fireEvent.click(floorFold(container)!);
    expect(container.querySelector('#floor-1 .detail')).toBeTruthy();
    await waitFor(() => expect(scrolled).toHaveLength(1));
  });

  it('★ 거래가 11건 이상이면 처음 10건 + 「거래 전부 보기 (N건)」 · 전부 · 다시 접기', async () => {
    responses.txs = { data: Array.from({ length: 12 }, (_, i) => tx({ price_won: (i + 1) * 10_000_000 })), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(txFold(container)).toBeTruthy());
    expect(container.querySelectorAll('.tx__list > li')).toHaveLength(12);
    expect(shownTx(container)).toBe(10);
    const btn = txFold(container)!;
    expect(btn.textContent).toBe('거래 전부 보기 (12건)');
    expect(btn.getAttribute('aria-expanded')).toBe('false');
    expect(document.getElementById(btn.getAttribute('aria-controls')!)).toBe(container.querySelector('.tx__list'));

    fireEvent.click(btn);
    expect(shownTx(container)).toBe(12);
    expect(txFold(container)!.textContent).toBe('거래 목록 접기');
    expect(txFold(container)!.getAttribute('aria-expanded')).toBe('true');

    fireEvent.click(txFold(container)!);
    expect(shownTx(container)).toBe(10);
    await waitFor(() => expect(scrolled).toHaveLength(1));
    expect(scrolled[0]).toBe(container.querySelector('section.tx .card__h'));
  });

  it('★ 거래 경계 — 10건이면 단추·숨김 없음, 11건이면 단추(양성 대조)', async () => {
    responses.txs = { data: Array.from({ length: 10 }, () => tx()), error: null };
    const first = render(<FloorStack building={building()} />);
    await waitFor(() => expect(first.container.querySelectorAll('.tx__list > li')).toHaveLength(10));
    expect(txFold(first.container)).toBeNull();
    expect(first.container.querySelector('.tx__list > li.list__folded')).toBeNull();
    first.unmount();

    responses.txs = { data: Array.from({ length: 11 }, () => tx()), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(txFold(container)?.textContent).toBe('거래 전부 보기 (11건)'));
    expect(container.querySelectorAll('.tx__list > li.list__folded')).toHaveLength(1);
  });

  it('★ 다른 건물을 열면(같은 땅의 다른 동이라도) 거래 목록은 다시 처음 10건 — 동작만 본다', async () => {
    // ⓘ 무엇이 되돌리는지는 가리지 않는다 — 이 시험에서는 새 건물의 층을 받는 동안 카드가 내려갔다 다시 서며 되돌아가고,
    //   실제 화면은 App 이 건물마다 FloorStack 을 새로 만든다(`key`). `ParcelTxList` 의 `key={bldId}` 는 그 둘이 없어져도
    //   남는 덧댐이라 빼도 이 시험은 초록이다(검사 M6) — 그 열쇠 자체를 지키는 시험이 아니다.
    responses.txs = { data: Array.from({ length: 12 }, () => tx()), error: null };
    const { container, rerender } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(txFold(container)).toBeTruthy());
    fireEvent.click(txFold(container)!);
    expect(shownTx(container)).toBe(12);
    rerender(<FloorStack building={building({ bld_id: '1168010100-2' })} />);
    await waitFor(() => expect(shownTx(container)).toBe(10));
    expect(txFold(container)!.getAttribute('aria-expanded')).toBe('false');
  });

  // 지분 설명 줄(👤 2026-10-16) — 화면에 보이는 줄에 지분이 있을 때만 화면에. 줄 자체는 지분이 하나라도 있으면 늘 DOM 에 있고
  // (종이에는 줄이 전부 나오니 설명도 늘 나온다), 숨은 줄에만 있으면 `list__folded` 이름표로 화면에서만 숨는다.
  // ⓘ jsdom 은 CSS 를 못 보니 이름표만 본다 — 실제로 숨는지는 E2E 「BB」.
  const shareNote = (c: HTMLElement) => c.querySelector('.tx__share-note');
  const txsWithShareAt = (n: number, at: number[], over: Partial<ParcelTransaction> = {}) =>
    Array.from({ length: n }, (_, i) => tx({ is_share: at.includes(i), ...over }));
  // ⓘ 점그림(결정 0038 B · V2)이 서면 설명 줄은 늘 선다(아래 「점그림」 묶음). 숨김 갈래(`shownShare`)는 그림이 **안 서는**
  //   목록에서만 살아 있다 — 11건 이상인데 그림이 안 서는 꼴 = 찍을 점이 없는 목록(㎡당 값이 전부 없음)으로 지킨다.
  const NO_PLOT = { unit_price: null };

  it('★ 지분이 숨은 줄(11번째 이후)에만 있으면 접힌 화면에선 설명 줄에 숨김 이름표 · 펼치면 떼고 · 다시 접으면 다시 붙는다', async () => {
    responses.txs = { data: txsWithShareAt(14, [11, 12], NO_PLOT), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(txFold(container)).toBeTruthy());
    // 줄은 DOM 에 있다(종이용) — 화면에서만 숨는 이름표.
    expect(shareNote(container)).not.toBeNull();
    expect(shareNote(container)!.classList.contains('list__folded')).toBe(true);

    fireEvent.click(txFold(container)!);
    expect(shareNote(container)!.classList.contains('list__folded')).toBe(false);

    fireEvent.click(txFold(container)!);
    expect(shareNote(container)!.classList.contains('list__folded')).toBe(true);
  });

  it('★ 경계 — 지분이 11번째 줄(첫 숨은 줄)에만 있으면 접힌 화면에선 숨김 이름표 · 펼치면 뗀다', async () => {
    responses.txs = { data: txsWithShareAt(14, [10], NO_PLOT), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(txFold(container)).toBeTruthy());
    expect(container.querySelector('.tx__plot')).toBeNull();
    expect(shareNote(container)!.classList.contains('list__folded')).toBe(true);
    fireEvent.click(txFold(container)!);
    expect(shareNote(container)!.classList.contains('list__folded')).toBe(false);
  });

  it('보이는 줄(처음 10건)에 지분이 있으면 접혀 있어도 펼쳐도 설명 줄이 보인다(양성 대조)', async () => {
    responses.txs = { data: txsWithShareAt(14, [9]), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(txFold(container)).toBeTruthy());
    expect(shareNote(container)).not.toBeNull();
    expect(shareNote(container)!.classList.contains('list__folded')).toBe(false);
    fireEvent.click(txFold(container)!);
    expect(shareNote(container)!.classList.contains('list__folded')).toBe(false);
  });

  it('지분이 아예 없으면 11건 이상이어도 설명 줄이 없다 — 접혀 있어도 펼쳐도', async () => {
    responses.txs = { data: txsWithShareAt(14, []), error: null };
    const { container } = render(<FloorStack building={building()} />);
    await waitFor(() => expect(txFold(container)).toBeTruthy());
    expect(shareNote(container)).toBeNull();
    fireEvent.click(txFold(container)!);
    expect(shareNote(container)).toBeNull();
  });
});
