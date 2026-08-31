import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
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

/**
 * 동 목록(펼치기) 답을 붙들어 두는 같은 장치. 슬롯을 따로 두는 이유는 목록과 펼치기가
 * **서로 다른 경합**을 갖기 때문이다 — 목록은 상권 단위, 펼치기는 줄 단위다.
 */
const holdDongs: { next: Promise<unknown> | null } = { next: null };

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string, args?: Record<string, unknown>) => {
      rpcCalls.push({ fn, args: args ?? {} });
      if (fn === 'list_district_buildings' && hold.next) {
        const held = hold.next;
        hold.next = null;
        return held;
      }
      if (fn === 'list_parcel_buildings' && holdDongs.next) {
        const held = holdDongs.next;
        holdDongs.next = null;
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
  // 붙들어 둔 답이 다음 시험으로 새면 그 시험이 엉뚱한 이유로 빨개진다.
  hold.next = null;
  holdDongs.next = null;
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

    // ⛔ **함수 이름과 인자 이름을 눈으로 본다.** 위 목(mock)은 목록 함수 하나만 이름으로
    //    가르고 **나머지 이름에는 전부 같은 답**을 준다 — 그래서 이 단언이 없으면
    //    `list_parcel_buildings` 를 오타 내거나 인자를 `pnu` 로 잘못 보내도 시험은 초록이고,
    //    라이브에서만 PGRST202 로 죽는다(목록 함수 쪽 ④ 단언과 같은 취지).
    const call = rpcCalls.find((c) => c.fn === 'list_parcel_buildings');
    expect(call, 'list_parcel_buildings 를 부르지 않았습니다').toBeTruthy();
    expect(call!.args).toEqual({ p_pnu: '1114011100100010000' });
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

  it('★ 펼치는 중에 접으면, 늦게 온 답이 **저절로 되펼치지 않는다**', async () => {
    /*
      2026-08-31 감사. 위 목록의 세대 번호로는 못 잡는 **별개** 경합이다(세대는 상권 단위,
      여기는 줄 단위). 답을 기다리는 동안 사용자가 접었는데 답이 도착하며 다시 펼쳐지면,
      화면이 사용자의 뜻을 덮는다. 되돌리면(settle 의 'loading' 검사 삭제) 빨간불이 된다.
    */
    responses.lands = { data: [many()], error: null };
    show();
    const row = await screen.findByText('롯데호텔 및 백화점');

    let give: (v: unknown) => void = () => {};
    holdDongs.next = new Promise((res) => {
      give = res;
    });
    fireEvent.click(row); // 펼치기 시작
    expect(screen.getByText('동 목록을 불러오는 중…')).toBeTruthy();
    fireEvent.click(row); // 기다리다 말고 접는다
    expect(screen.queryByText('동 목록을 불러오는 중…')).toBeNull();

    await act(async () => {
      give({ data: [dong()], error: null });
    });
    expect(screen.queryByText('본관동')).toBeNull();
  });

  it('★ 펼치는 중에 상권이 바뀌면, 늦게 온 답이 **안 누른 줄을 펼치지 않는다**', async () => {
    /*
      ⚠️ 이 시험이 성립하려면 **두 상권에 같은 땅이 들어 있어야** 한다. 억지 설정이
         아니다 — 상권 경계가 겹치도록 그려져 있어 서울만 3,342동이 두 상권에 동시에
         들어간다(2026-08-14 실측). 겹치지 않는 땅으로 짜면 새 목록에 그 줄이 아예
         없어서 **무엇을 무력화해도 통과하는 가짜 시험**이 된다(실제로 그렇게 짰다가
         돌연변이 검증에서 걸렀다).
    */
    responses.lands = { data: [many()], error: null };
    const { rerender } = show();
    const row = await screen.findByText('롯데호텔 및 백화점');

    let give: (v: unknown) => void = () => {};
    holdDongs.next = new Promise((res) => {
      give = res;
    });
    fireEvent.click(row); // 펼치기 시작 — 답은 붙들려 있다
    expect(screen.getByText('동 목록을 불러오는 중…')).toBeTruthy();

    // 겹치는 옆 상권으로 갈아탄다. **같은 땅**이 그 목록에도 들어 있다.
    rerender(
      <DistrictBuildings
        districtId="3120028"
        districtNm="명동거리"
        onSelect={() => {}}
        selectedBldId={null}
      />,
    );
    await waitFor(() => expect(screen.queryByText('동 목록을 불러오는 중…')).toBeNull());

    await act(async () => {
      give({ data: [dong()], error: null });
    });
    // 새 상권에서는 아무도 이 줄을 누르지 않았다.
    expect(screen.queryByText('본관동')).toBeNull();
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

  it('2쪽을 못 받으면 **이미 받은 목록은 그대로** 두고 그 사실만 알린다', async () => {
    responses.lands = { data: cut(), error: null };
    show();
    await screen.findByText(/이 중 50곳/);
    responses.lands = { data: null, error: { message: '연결 실패' } };
    fireEvent.click(screen.getByRole('button', { name: '더 보기' }));
    expect(await screen.findByText('더 불러오지 못했습니다.')).toBeTruthy();
    // 받아 둔 50곳을 지우면 사용자는 "왜 사라졌지"가 된다.
    expect(screen.getByText(/이 중 50곳/)).toBeTruthy();
  });

  it('★ 더 보기 응답이 늦게 와도 **새 상권 목록에 섞이지 않는다**', async () => {
    /*
      2026-08-31 감사에서 잡힌 경합. 처음 불러오기에만 취소 가드가 있고 '더 보기'에는
      없어서, 더 보기를 누른 직후 지도에서 다른 상권을 누르면 **옛 상권의 2쪽이 새 상권
      이름 아래** 붙었다. 되돌리면(load 의 runId 검사 삭제) 이 시험이 빨간불이 된다.
    */
    responses.lands = { data: cut(), error: null };
    const { rerender } = show();
    await screen.findByText(/이 중 50곳/);

    // 2쪽 답을 붙들어 둔다 — 이 구간이 진짜 위험한 자리다.
    let give: (v: unknown) => void = () => {};
    hold.next = new Promise((res) => {
      give = res;
    });
    fireEvent.click(screen.getByRole('button', { name: '더 보기' }));

    // 답을 기다리는 사이 다른 상권으로 갈아탄다(이쪽은 즉답 — hold 는 한 칸짜리다).
    responses.lands = { data: [land({ bld_nm: '새 상권 건물', pnu: 'x1', bld_id: 'X-1' })], error: null };
    rerender(
      <DistrictBuildings
        districtId="3120028"
        districtNm="명동거리"
        onSelect={() => {}}
        selectedBldId={null}
      />,
    );
    expect(await screen.findByText('새 상권 건물')).toBeTruthy();

    // 이제서야 옛 상권의 2쪽이 도착한다.
    await act(async () => {
      give({ data: [land({ bld_nm: '옛 상권 2쪽', pnu: 'old2', bld_id: 'O-2' })], error: null });
    });
    expect(screen.queryByText('옛 상권 2쪽')).toBeNull();
    expect(screen.getByText('새 상권 건물')).toBeTruthy();
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
