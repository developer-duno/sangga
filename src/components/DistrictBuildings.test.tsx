import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import type { DistrictLand, ParcelBuilding } from '../types';

/**
 * "이 상권의 건물" 목록 — 지도를 막다른 길에서 꺼내는 조각.
 *
 * 여기서 특히 지키는 것
 * ---------------------
 *  ① **한 줄은 땅이다.** 건물로 줄세우면 한 땅의 동들이 같은 점포 수를 복사해 가져
 *     상위 목록이 같은 이름으로 도배된다(명동 상위 10에 롯데호텔 4줄 — 라이브 실측).
 *  ② **못 읽었으면 그 사실을 말한다.** 형제 카드들과 다른 유일한 점이다 — 여기는 사람이
 *     직접 누른 결과라, 아무 반응이 없으면 고장으로 읽는다. 다만 "건물이 없다"고는
 *     여전히 말하지 않는다.
 *  ③ **잘렸으면 잘렸다고 적는다.** 50곳만 보여 주며 전체를 안 적으면 "여기 50곳뿐"이 된다.
 *  ④ **인자 이름이 p_district_id·p_limit·p_offset 이다.** 목(mock)은 인자 이름을 안 보므로
 *     여기서 눈으로 보지 않으면 잘못 불러도 시험이 전부 초록이고 라이브에서만 PGRST202 다.
 *  ⑤ **상권이 바뀌면 옛 목록을 비운다.** 안 비우면 새 이름 아래 옛 건물들이 서 있다.
 */

const responses = {
  lands: { data: null as unknown, error: null as unknown },
  dongs: { data: null as unknown, error: null as unknown },
};

/** 마지막 rpc 호출들. 함수 이름과 **인자 이름·값**을 여기서 확인한다. */
const rpcCalls: Array<{ fn: string; args: Record<string, unknown> }> = [];

/**
 * 다음 목록 조회의 답을 **손에 쥐고 있다가** 원할 때 준다.
 *
 * ⚠️ 이게 없으면 "상권을 바꿨을 때 옛 목록을 비우는가"를 못 잰다 — 답이 곧바로 오면
 *    옛 목록은 어차피 새 목록으로 덮이므로, 비우든 안 비우든 **시험이 똑같이 초록**이다
 *    (2026-08-31 돌연변이 검증에서 실제로 안 잡혔다). 진짜 위험한 구간은 **답을 기다리는
 *    동안**이고, 그 순간을 만들려면 답을 붙들고 있어야 한다.
 */
const hold: { next: Promise<unknown> | null } = { next: null };

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string, args?: Record<string, unknown>) => {
      rpcCalls.push({ fn, args: args ?? {} });
      if (fn === 'list_district_buildings' && hold.next) {
        const held = hold.next;
        hold.next = null;
        return held;
      }
      return Promise.resolve(fn === 'list_district_buildings' ? responses.lands : responses.dongs);
    },
  },
}));

const { DistrictBuildings } = await import('./DistrictBuildings');

function land(over: Partial<DistrictLand> = {}): DistrictLand {
  return {
    pnu: '1114011100100010000',
    store_cnt: 317,
    bld_cnt_in_pnu: 1,
    bld_id: 'B-1',
    bld_nm: '롯데호텔 및 백화점',
    road_addr: '서울특별시 중구 남대문로 81',
    jibun_addr: '서울특별시 중구 소공동 1',
    lat: 37.5651,
    lng: 126.9815,
    floor_cnt: 43,
    min_floor: -7,
    max_floor: 35,
    has_roof: true,
    total_parcel_cnt: 1,
    total_bld_cnt: 1,
    ...over,
  };
}

function dong(over: Partial<ParcelBuilding> = {}): ParcelBuilding {
  return {
    bld_id: 'B-본관',
    bld_nm: '롯데호텔 및 백화점',
    dong_nm: '본관동',
    total_area_m2: 110982.26,
    floor_cnt: 41,
    min_floor: -3,
    max_floor: 37,
    has_roof: true,
    ...over,
  };
}

function show(over: { onSelect?: (h: unknown) => void; districtId?: string } = {}) {
  return render(
    <DistrictBuildings
      districtId={over.districtId ?? '3001492'}
      districtNm="명동 남대문 관광특구"
      onSelect={over.onSelect ?? (() => {})}
      selectedBldId={null}
    />,
  );
}

beforeEach(() => {
  rpcCalls.length = 0;
  responses.lands = { data: [land()], error: null };
  responses.dongs = { data: [dong()], error: null };
});

afterEach(() => cleanup());

describe('DistrictBuildings — 목록', () => {
  it('상권 안의 건물을 보여준다', async () => {
    show();
    expect(await screen.findByText('롯데호텔 및 백화점')).toBeTruthy();
    expect(screen.getByText(/서울특별시 중구 남대문로 81/)).toBeTruthy();
    expect(screen.getByText(/점포 317곳/)).toBeTruthy();
  });

  it('서버에 **인자 이름 그대로** 묻는다 — 목은 이름을 안 보므로 여기서 본다', async () => {
    show();
    await screen.findByText('롯데호텔 및 백화점');
    const call = rpcCalls.find((c) => c.fn === 'list_district_buildings');
    expect(call).toBeTruthy();
    expect(call?.args.p_district_id).toBe('3001492');
    expect(call?.args.p_limit).toBe(50);
    expect(call?.args.p_offset).toBe(0);
  });

  it('점포 수가 **그 땅 전체**를 센 것이라고 밝힌다', async () => {
    show();
    await screen.findByText('롯데호텔 및 백화점');
    // 층별 화면의 점포 칸과 세는 대상이 달라, 흐리면 두 화면이 다른 말을 하는 것처럼 보인다.
    expect(screen.getByText(/그 땅 전체/)).toBeTruthy();
  });

  it('경계에 걸친 땅이 빠질 수 있다고 적는다', async () => {
    show();
    await screen.findByText('롯데호텔 및 백화점');
    expect(screen.getByText(/경계에 걸친 땅은/)).toBeTruthy();
  });
});

describe('DistrictBuildings — 한 땅에 여러 동', () => {
  const many = () => land({ bld_cnt_in_pnu: 4, total_parcel_cnt: 1, total_bld_cnt: 4 });

  it('네 동이 네 줄이 아니라 **한 줄**로 서고 "같은 땅에 4동"이 붙는다', async () => {
    responses.lands = { data: [many()], error: null };
    show();
    await screen.findByText('롯데호텔 및 백화점');
    // ⛔ 이것이 이 조각의 핵심이다 — 라이브에서 실제로 네 줄 연달아 나왔다.
    expect(screen.getAllByText('롯데호텔 및 백화점')).toHaveLength(1);
    expect(screen.getByText(/같은 땅에 4동/)).toBeTruthy();
  });

  it('여러 동인 줄을 누르면 **고르지 않고 펼친다**', async () => {
    responses.lands = { data: [many()], error: null };
    const onSelect = vi.fn();
    show({ onSelect });
    fireEvent.click(await screen.findByText('롯데호텔 및 백화점'));
    expect(await screen.findByText('본관동')).toBeTruthy();
    // 어느 동인지 모르는 채로 건물을 고르면 안 된다.
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('펼친 동을 누르면 **그 동**으로 고른다 — 층도 그 동의 것이다', async () => {
    responses.lands = { data: [many()], error: null };
    const onSelect = vi.fn();
    show({ onSelect });
    fireEvent.click(await screen.findByText('롯데호텔 및 백화점'));
    fireEvent.click(await screen.findByText('본관동'));
    expect(onSelect).toHaveBeenCalledTimes(1);
    const hit = onSelect.mock.calls[0][0] as Record<string, unknown>;
    expect(hit.bld_id).toBe('B-본관');
    expect(hit.min_floor).toBe(-3);
    expect(hit.max_floor).toBe(37);
    // 주소는 같은 땅이라 목록 줄에서 가져온다.
    expect(hit.road_addr).toBe('서울특별시 중구 남대문로 81');
  });

  it('동 목록을 못 읽으면 그 사실만 말한다 — 목록 전체는 그대로 선다', async () => {
    responses.lands = { data: [many()], error: null };
    responses.dongs = { data: null, error: { message: 'PGRST202' } };
    show();
    fireEvent.click(await screen.findByText('롯데호텔 및 백화점'));
    expect(await screen.findByText('동 목록을 불러오지 못했습니다.')).toBeTruthy();
    expect(screen.getByText(/같은 땅에 4동/)).toBeTruthy();
  });
});

describe('DistrictBuildings — 한 동뿐인 줄', () => {
  it('누르면 바로 그 건물로 간다', async () => {
    const onSelect = vi.fn();
    show({ onSelect });
    fireEvent.click(await screen.findByText('롯데호텔 및 백화점'));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect((onSelect.mock.calls[0][0] as Record<string, unknown>).bld_id).toBe('B-1');
  });
});

describe('DistrictBuildings — 말하기 어려운 상태들', () => {
  it('못 읽으면 "불러오지 못했습니다"라고 말한다 — 빈 목록으로 거짓말하지 않는다', async () => {
    responses.lands = { data: null, error: { message: '연결 실패' } };
    show();
    expect(await screen.findByText('건물 목록을 불러오지 못했습니다.')).toBeTruthy();
    // ⛔ "건물이 없다"고는 말하지 않는다 — 모르는 것과 없는 것은 다르다.
    expect(screen.queryByText(/건물 자료가 없습니다/)).toBeNull();
  });

  it('뜻밖의 모양이 와도 렌더로 흘려보내지 않는다', async () => {
    responses.lands = { data: { message: '오류' }, error: null };
    show();
    expect(await screen.findByText('건물 목록을 불러오지 못했습니다.')).toBeTruthy();
  });

  it('건물이 한 동도 없는 상권은 그렇다고 말한다', async () => {
    responses.lands = { data: [], error: null };
    show();
    expect(await screen.findByText('이 상권에는 아직 건물 자료가 없습니다.')).toBeTruthy();
  });

  it('기다리는 동안 "불러오는 중"을 보여준다 — 찬 캐시에서 0.5초가 걸린다', () => {
    show();
    expect(screen.getByText(/불러오는 중/)).toBeTruthy();
  });
});

describe('DistrictBuildings — 더 보기', () => {
  const cut = () =>
    Array.from({ length: 50 }, (_, i) =>
      land({ pnu: `p${i}`, bld_id: `B-${i}`, total_parcel_cnt: 955, total_bld_cnt: 1098 }),
    );

  it('잘렸으면 몇 곳 중 몇 곳인지 적고 더 보기를 낸다', async () => {
    responses.lands = { data: cut(), error: null };
    show();
    expect(await screen.findByText(/955곳 · 건물 1,098동 · 이 중 50곳/)).toBeTruthy();
    expect(screen.getByRole('button', { name: '더 보기' })).toBeTruthy();
  });

  it('다 보여줬으면 더 보기가 없다', async () => {
    responses.lands = { data: [land()], error: null };
    show();
    await screen.findByText('롯데호텔 및 백화점');
    expect(screen.queryByRole('button', { name: '더 보기' })).toBeNull();
  });

  it('더 보기를 누르면 **이미 받은 만큼** 건너뛰고 묻는다', async () => {
    responses.lands = { data: cut(), error: null };
    show();
    fireEvent.click(await screen.findByRole('button', { name: '더 보기' }));
    await waitFor(() => {
      const calls = rpcCalls.filter((c) => c.fn === 'list_district_buildings');
      expect(calls[calls.length - 1].args.p_offset).toBe(50);
    });
  });
});

describe('DistrictBuildings — 상권을 바꿨을 때', () => {
  it('옛 상권의 건물이 **불러오는 동안에도** 새 이름 아래 남지 않는다', async () => {
    responses.lands = { data: [land({ bld_nm: '옛 건물' })], error: null };
    const { rerender } = show();
    await screen.findByText('옛 건물');

    // 새 상권의 답을 붙들어 둔다 — 이 구간이 진짜 위험한 자리다.
    let give: (v: unknown) => void = () => {};
    hold.next = new Promise((res) => {
      give = res;
    });
    rerender(
      <DistrictBuildings
        districtId="3120028"
        districtNm="명동거리"
        onSelect={() => {}}
        selectedBldId={null}
      />,
    );

    // 아직 답이 안 왔는데 옛 건물이 남아 있으면, **새 상권 이름 아래 옛 목록**이 선 것이다.
    await waitFor(() => expect(screen.queryByText('옛 건물')).toBeNull());
    expect(screen.getByText(/불러오는 중/)).toBeTruthy();

    give({ data: [land({ bld_nm: '새 건물', pnu: 'p2', bld_id: 'B-2' })], error: null });
    expect(await screen.findByText('새 건물')).toBeTruthy();
  });
});
