import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import type { BuildingHit, CoverageStats, FloorRow } from '../types';

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
};

vi.mock('../lib/supabase', () => ({
  FLOOR_STACK_VIEW: 'v_floor_stack',
  COVERAGE_STATS_VIEW: 'v_coverage_stats',
  supabase: {
    from: (view: string) =>
      makeQuery(view === 'v_coverage_stats' ? responses.stats : responses.floors),
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

beforeEach(() => {
  responses.floors = { data: [floor()], error: null };
  responses.stats = { data: [stats()], error: null };
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
});
