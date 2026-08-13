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
  /** 서버 함수 list_building_districts 의 응답. */
  districts: { data: null as unknown, error: null as unknown },
};

vi.mock('../lib/supabase', () => ({
  FLOOR_STACK_VIEW: 'v_floor_stack',
  COVERAGE_STATS_VIEW: 'v_coverage_stats',
  BUILDING_DISTRICTS_FN: 'list_building_districts',
  supabase: {
    from: (view: string) =>
      makeQuery(view === 'v_coverage_stats' ? responses.stats : responses.floors),
    // 상권 줄이 이 rpc 를 부른다. 흉내에 rpc 가 없으면 화면이 통째로 죽으므로
    // (undefined.then) 여기 없는 것 자체가 다른 테스트 전부를 빨갛게 만든다.
    rpc: (_fn: string, _args?: unknown) => Promise.resolve(responses.districts),
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
  responses.districts = { data: { covered: true, districts: [] }, error: null };
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
      },
      error: null,
    };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/역삼역\(발달상권\)/)).toBeTruthy());
    expect(screen.getByText(/선릉역\(발달상권\)/)).toBeTruthy();
    // 공공누리 1유형(출처표시) 의무 — 상권을 보여줄 때 항상 함께 나가야 한다.
    expect(screen.getByText(/출처: 서울특별시 상권분석서비스/)).toBeTruthy();
  });

  it('자료는 있는데 경계 밖이면 "없음"이라고 말한다 (출처는 그대로 붙인다)', async () => {
    // 경계 밖은 정상 상태다. 이 판정도 서울 자료를 읽어서 내린 것이므로 출처를 붙인다.
    responses.districts = { data: { covered: true, districts: [] }, error: null };
    render(<FloorStack building={building()} />);
    await waitFor(() => expect(screen.getByText(/어느 상권 경계에도 들지 않는/)).toBeTruthy());
    expect(screen.getByText(/출처: 서울특별시 상권분석서비스/)).toBeTruthy();
    expect(screen.queryByText(/준비되지 않았습니다/)).toBeNull();
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
    await waitFor(() => expect(screen.getByText('1층')).toBeTruthy());
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
