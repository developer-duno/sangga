import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import type { BuildingHit, StoreHit } from '../types';

/**
 * 검색 화면 테스트.
 *
 * 여기 담긴 것은 전부 **2026-08-08 적대검증에서 라이브로 재현된 실제 결함**이다.
 * 그때는 프론트 테스트 러너 자체가 없어서 CI를 그대로 통과했다.
 *
 * `../lib/supabase`는 모듈을 읽는 순간 환경변수를 요구하며 throw하므로 반드시 가짜로 바꾼다.
 */
const rpc = vi.fn();
vi.mock('../lib/supabase', () => ({
  supabase: { rpc: (...args: unknown[]) => rpc(...args) },
}));

const { BuildingSearch } = await import('./BuildingSearch');

function hit(over: Partial<BuildingHit> = {}): BuildingHit {
  return {
    bld_id: '1168010100-1',
    pnu: '1168010100100010000',
    bld_nm: '테스트빌딩',
    road_addr: '서울 강남구 테헤란로 1',
    bld_cnt_in_pnu: 1,
    floor_cnt: 5,
    min_floor: 1,
    max_floor: 5,
    has_roof: false,
    ...over,
  };
}

beforeEach(() => {
  rpc.mockReset();
  rpc.mockResolvedValue({ data: [], error: null });
});

afterEach(() => cleanup());

// ── 화면 동작 ────────────────────────────────────────────────────────────

describe('BuildingSearch — 화면 동작', () => {
  // 구를 이미 고른 상태가 기본값이다 — "구를 안 골랐을 때" 동작은 별도
  // describe("BuildingSearch — 구 선택 연동")에서 따로 검사한다.
  function setup(over: Partial<Parameters<typeof BuildingSearch>[0]> = {}) {
    const onSelect = vi.fn();
    const onSearchStart = vi.fn();
    render(
      <BuildingSearch
        onSelect={onSelect}
        onSearchStart={onSearchStart}
        selectedBldId={null}
        sigungu="11680"
        sigunguName="강남구"
        {...over}
      />,
    );
    const input = screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;
    return { onSelect, onSearchStart, input };
  }

  function search(input: HTMLInputElement, text: string) {
    fireEvent.change(input, { target: { value: text } });
    fireEvent.submit(input.closest('form')!);
  }

  it('새 검색을 시작하면 이전 선택을 비우라고 알린다', async () => {
    // 이게 없으면 새로 검색해도 아래 스택뷰가 **이전에 고른 건물**을 계속 그린다.
    // "결과가 없습니다"가 뜬 상태에서도 옛 건물 스택이 그대로 남아 있었다.
    const { onSearchStart, input } = setup();
    search(input, '테헤란로');
    await waitFor(() => expect(onSearchStart).toHaveBeenCalledTimes(1));
  });

  it('검색어를 서버 함수에 파라미터로 넘긴다', async () => {
    // 문자열을 직접 이어 붙이면 % _ ( ) 같은 글자에서 필터가 깨진다.
    // 파라미터로 넘겨야 서버가 리터럴로 이스케이프한다.
    const { input } = setup();
    search(input, '스타(별)빌딩 100%');
    // ⚠️ "몇 번 불렀나"로 재지 말 것 — 결과가 0건이면 화면이 이어서 search_scope 를
    //    한 번 더 부른다("없음"인지 "너무 넓음"인지 가리려고). 여기서 지킬 것은
    //    **첫 호출이 무엇을 어떻게 넘겼는가**다.
    await waitFor(() => expect(rpc).toHaveBeenCalled());
    expect(rpc.mock.calls[0]).toEqual([
      'search_buildings',
      { q: '스타(별)빌딩 100%', lim: expect.any(Number), sigungu: '11680' },
    ]);
  });

  it('앞뒤 공백은 떼고 보낸다', async () => {
    const { input } = setup();
    search(input, '  미도맨션  ');
    await waitFor(() => expect(rpc).toHaveBeenCalled());
    expect(rpc.mock.calls[0][1]).toMatchObject({ q: '미도맨션' });
  });

  it('공백뿐인 검색어로는 서버를 부르지 않는다', () => {
    const { onSearchStart, input } = setup();
    search(input, '    ');
    expect(rpc).not.toHaveBeenCalled();
    expect(onSearchStart).not.toHaveBeenCalled();
  });

  it('결과가 없으면 **고른 구 기준으로** 알려준다', async () => {
    // ⚠️ 구 단위 검색으로 바뀐 뒤 "지금 보실 수 있는 지역은 서울·대전입니다"를 그대로
    //    두면 엉뚱하다 — 사용자는 이미 한 구를 골랐고, 없는 것은 그 구 안에서 없는 것이다.
    const { input } = setup();
    search(input, '없는건물');
    await waitFor(() => expect(screen.getByText(/찾지 못했습니다/)).toBeTruthy());
    expect(screen.getByText('강남구')).toBeTruthy();
  });

  it('전체 건수는 목록 길이가 아니라 서버가 준 total_cnt를 쓴다', async () => {
    // 목록은 상위 25개만 온다. 여기서 hits.length를 쓰면 "15,068개 중 25개"가
    // "25개"로 줄어들어 사용자가 검색어를 좁힐 이유를 알 수 없게 된다.
    rpc.mockResolvedValue({
      data: [hit({ bld_id: 'a', total_cnt: 15068 }), hit({ bld_id: 'b', total_cnt: 15068 })],
      error: null,
    });
    const { input } = setup();
    search(input, '빌딩');
    await waitFor(() => expect(screen.getByText(/15,068개/)).toBeTruthy());
    expect(screen.getByText(/2개만 보여드립니다/)).toBeTruthy();
  });

  it('이름 없는 건물도 빈칸이 아니라 알아볼 수 있게 표시한다', async () => {
    // 건물 12,405개 중 이름이 있는 것은 5,361개(43.2%)뿐이다.
    rpc.mockResolvedValue({ data: [hit({ bld_nm: null, total_cnt: 1 })], error: null });
    const { input } = setup();
    search(input, '테헤란로 1');
    await waitFor(() => expect(screen.getByText('(이름 없는 건물)')).toBeTruthy());
  });

  it('같은 땅에 여러 동이 있으면 경고를 함께 보여준다', async () => {
    rpc.mockResolvedValue({ data: [hit({ bld_cnt_in_pnu: 3, total_cnt: 1 })], error: null });
    const { input } = setup();
    search(input, '테스트');
    await waitFor(() => expect(screen.getByText(/같은 땅에 3동/)).toBeTruthy());
  });

  it('검색이 실패하면 내부 오류 원문 대신 사람 말로 보여준다', async () => {
    rpc.mockResolvedValue({
      data: null,
      error: { code: '42501', message: 'permission denied for table building_floor' },
    });
    const { input } = setup();
    search(input, '테스트');
    await waitFor(() => expect(screen.getByText(/검색에 실패했습니다/)).toBeTruthy());
    expect(screen.queryByText(/building_floor/)).toBeNull();
  });

  it('늦게 도착한 옛 응답이 최신 결과를 덮지 않는다', async () => {
    // 느린 첫 검색이 나중에 끝나면서, 이미 화면에 있는 새 검색 결과를 밀어내는 문제.
    //
    // ⚠️ 순번(`mockReturnValueOnce`)으로 답을 배정하면 안 된다 — 검색 한 번에 서버를
    //    **둘** 부르므로(건물 · 가게 이름, 결정 0028) 두 번째 순번이 같은 검색의 가게
    //    질의에게 가 버린다. **어느 함수를 부르는가**로 배정해야 뜻이 유지된다.
    let resolveFirst!: (v: unknown) => void;
    let buildingCalls = 0;
    rpc.mockImplementation((fn: string) => {
      if (fn !== 'search_buildings') return Promise.resolve({ data: [], error: null });
      buildingCalls += 1;
      return buildingCalls === 1
        ? new Promise((r) => (resolveFirst = r))
        : Promise.resolve({ data: [hit({ bld_nm: '나중검색결과', total_cnt: 1 })], error: null });
    });

    const { input } = setup();
    search(input, '느린검색');
    search(input, '빠른검색');
    await waitFor(() => expect(screen.getByText('나중검색결과')).toBeTruthy());

    resolveFirst({ data: [hit({ bld_nm: '옛검색결과', total_cnt: 1 })], error: null });
    await waitFor(() => expect(screen.getByText('나중검색결과')).toBeTruthy());
    expect(screen.queryByText('옛검색결과')).toBeNull();
  });
});


// ── 너무 넓은 검색 안내 (2026-08-13 안내창 → 2026-09-10 건물 쪽은 한 줄) ──────────────────────────────────────
//
// 왜 이 화면이 필요한가: 이 서비스는 **건물 한 채·필지 한 곳**을 놓고 상권을 분석한다.
// '서울'·'동' 처럼 어디를 볼지 정해지지 않는 검색은 결과 25개를 억지로 보여줘도 쓸모가
// 없고, 서버에서는 20만 건과 맞아 3초를 넘겨 500이 됐다(라이브 실측 2026-08-13).
// 그래서 "결과를 자르는" 대신 **왜 안 되는지와 무엇을 넣으면 되는지**를 말해 준다.

describe('BuildingSearch — 너무 넓은 검색 안내', () => {
  function setup() {
    render(
      <BuildingSearch
        onSelect={vi.fn()}
        onSearchStart={vi.fn()}
        selectedBldId={null}
        sigungu="11680"
        sigunguName="강남구"
      />,
    );
    return screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;
  }

  function search(input: HTMLInputElement, text: string) {
    fireEvent.change(input, { target: { value: text } });
    fireEvent.submit(input.closest('form')!);
  }

  /** search_buildings 는 0건, search_scope 는 주어진 판정을 돌려주는 가짜 서버. */
  function serverSays(tooBroad: boolean, matchCnt = 0) {
    rpc.mockImplementation((fn: string) =>
      fn === 'search_scope'
        ? Promise.resolve({ data: [{ too_broad: tooBroad, match_cnt: matchCnt }], error: null })
        : Promise.resolve({ data: [], error: null }),
    );
  }

  it('한 글자로 검색하면 서버를 부르지 않고 바로 안내한다', () => {
    // 한 글자는 어떤 글자든 수만 곳과 맞는다 — 물어볼 필요가 없다(왕복 낭비).
    const input = setup();
    search(input, '동');
    expect(rpc).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(screen.getByText(/한 글자로는 찾을 수 없어요/)).toBeTruthy();
  });

  it('띄어 쓴 두 글자는 막지 않는다 — 서버(search_key)와 같은 기준으로 잰다', async () => {
    // 서버는 비교 전에 공백을 없앤다('그랑프리 빌딩' = '그랑프리빌딩'). 화면이 다른
    // 기준으로 재면 두 판정이 갈려, 서버는 찾을 수 있는 검색어를 화면이 먼저 막는다.
    //
    // ⚠️ 반대 방향(공백 때문에 짧아지는 경우)은 이 최소 길이(2)에서는 만들 수 없다 —
    //    앞뒤 공백은 trim 이 이미 떼므로 남는 글자가 2개면 정규화해도 2개다. 그래서
    //    여기서는 "덜 막는가"만 검사한다. 최소 길이를 3 이상으로 올리면 그때 반대
    //    방향 검사도 힘이 생기므로 함께 추가할 것.
    serverSays(false, 2);
    const input = setup();
    search(input, ' 명 동 ');
    await waitFor(() => expect(rpc).toHaveBeenCalled());
    expect(rpc.mock.calls[0][0]).toBe('search_buildings');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('두 글자여도 서버가 너무 넓다고 하면 **안내창이 아니라 한 줄로** 걸린 곳 수를 알려준다', async () => {
    // '강남'은 두 글자지만 구 조각이라 13,529곳과 맞는다. 반대로 '명동'은 두 글자여도
    // 동이 확정된다 — **글자 수로는 안 갈린다.** 그래서 서버가 세어 판정한다.
    //
    // ⛔ 이 경우만 안내창(모달)이 아니다 — 덮개가 화면을 통째로 덮으면 건물이 0건이어도
    //    멀쩡히 서 있는 **가게 이름 구역**을 가리고 클릭까지 삼킨다(결정 0028 §백로그 🟡-10).
    serverSays(true, 13529);
    const input = setup();
    search(input, '강남');
    await waitFor(() => expect(screen.getByText(/너무 넓은 검색/)).toBeTruthy());
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByText(/‘강남’/)).toBeTruthy();
    expect(screen.getByText('13,529곳')).toBeTruthy();
    // 한 줄은 `.search` 안에 있어야 한다 — 인쇄가 `.search` 를 통째로 숨기므로 밖에 두면
    // 종이에 죽은 안내가 남는다(가게 구역과 같은 제약).
    expect(screen.getByText(/너무 넓은 검색/).closest('.search')).not.toBeNull();
    // 결과 목록 쪽 "찾지 못했습니다"와 겹쳐 뜨면 안 된다(두 말이 동시에 보인다).
    expect(screen.queryByText(/찾지 못했습니다/)).toBeNull();
  });

  it('무엇을 넣으면 되는지 알려준다 (동 이름·건물 이름·지번·도로명)', async () => {
    serverSays(true, 163487);
    const input = setup();
    search(input, '서울');
    await waitFor(() => expect(screen.getByText(/너무 넓은 검색/)).toBeTruthy());
    // 도로명 갈래도 빠지면 안 된다 — 검색창 placeholder 가 여전히 도로명주소를 권한다.
    for (const example of ['역삼동', '그랑프리빌딩', '역삼동 823-4', '테헤란로 117']) {
      expect(screen.getByText(example)).toBeTruthy();
    }
  });

  it('넓지 않은데 0건이면 안내창이 아니라 "찾지 못했습니다"', async () => {
    // 정말 그런 건물이 없는 것과, 검색어가 넓어 끊긴 것은 다른 말이어야 한다.
    serverSays(false, 3);
    const input = setup();
    search(input, '없는건물이름');
    await waitFor(() => expect(screen.getByText(/찾지 못했습니다/)).toBeTruthy());
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('Esc 로 안내창을 닫을 수 있다', async () => {
    // ⓘ 안내창이 남는 경우(①한 글자)로 잰다 — ③너무 넓음은 이제 안내창이 아니라 한 줄이다.
    const input = setup();
    search(input, '동');
    expect(screen.getByRole('dialog')).toBeTruthy();
    // ⚠️ dialog 가 DOM 에 보이는 순간에는 Esc 리스너가 아직 없다 — 리스너는 커밋 뒤
    //    useEffect 에서 붙고, waitFor 는 act 밖에서 돌아 그 이펙트를 기다려 주지 않는다.
    //    여기서 바로 keyDown 을 쏘면 느린 러너(CI)에서 이펙트보다 먼저 떨어져 유실되고,
    //    아무도 다시 누르지 않으니 영영 안 닫힌다(2026-08-30 CI flaky 실측). 같은 이펙트가
    //    리스너를 붙인 다음 닫기 버튼에 초점을 주므로, 초점 도착 = 리스너 부착 완료 신호다.
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole('button', { name: '닫기' })),
    );
    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('닫기 버튼으로도 닫힌다', () => {
    const input = setup();
    search(input, '1');
    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

// ── 구 선택 연동 (2026-08-13) ────────────────────────────────────────────
//
// 검색은 이제 고른 구 안에서만 한다(사장님 결정) — 같은 건물 이름이 여러 구에
// 겹치기 때문이다(이름 33,851종 중 2,443종이 2개 이상 구에 존재).

describe('BuildingSearch — 구 선택 연동', () => {
  function setup(over: Partial<Parameters<typeof BuildingSearch>[0]> = {}) {
    const onSelect = vi.fn();
    const onSearchStart = vi.fn();
    render(
      <BuildingSearch
        onSelect={onSelect}
        onSearchStart={onSearchStart}
        selectedBldId={null}
        sigungu={null}
        sigunguName={null}
        {...over}
      />,
    );
    const input = screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;
    return { onSelect, onSearchStart, input };
  }

  function search(input: HTMLInputElement, text: string) {
    fireEvent.change(input, { target: { value: text } });
    fireEvent.submit(input.closest('form')!);
  }

  it('구를 고르지 않고 검색하면 서버를 부르지 않고 지역을 먼저 고르라고 안내한다', () => {
    const { input, onSearchStart } = setup();
    search(input, '테헤란로');
    expect(rpc).not.toHaveBeenCalled();
    expect(onSearchStart).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(screen.getByText('먼저 지역을 골라 주세요')).toBeTruthy();
  });

  it('구를 고르면 검색 요청에 그 구 코드가 실려 간다', async () => {
    const { input } = setup({ sigungu: '11680', sigunguName: '강남구' });
    search(input, '테헤란로');
    await waitFor(() => expect(rpc).toHaveBeenCalled());
    expect(rpc.mock.calls[0]).toEqual([
      'search_buildings',
      { q: '테헤란로', lim: expect.any(Number), sigungu: '11680' },
    ]);
  });

  it('결과 문구에 어느 구에서 찾았는지 보여준다', async () => {
    rpc.mockResolvedValue({ data: [hit({ total_cnt: 1706 })], error: null });
    const { input } = setup({ sigungu: '11680', sigunguName: '강남구' });
    search(input, '테헤란로');
    await waitFor(() => expect(screen.getByText(/강남구에서/)).toBeTruthy());
    expect(screen.getByText(/1,706개/)).toBeTruthy();
  });

  it('0건일 때 너무 넓은지 판정하는 요청에도 구 코드가 함께 실려 간다', async () => {
    rpc.mockImplementation((fn: string) =>
      fn === 'search_scope'
        ? Promise.resolve({ data: [{ too_broad: false, match_cnt: 0 }], error: null })
        : Promise.resolve({ data: [], error: null }),
    );
    const { input } = setup({ sigungu: '11680', sigunguName: '강남구' });
    search(input, '없는건물');
    await waitFor(() =>
      expect(rpc).toHaveBeenCalledWith('search_scope', { q: '없는건물', sigungu: '11680' }),
    );
  });
});

// ── 가게 이름으로 찾기 (결정 0028) ──────────────────────────────────────────
//
// 검색 한 번에 서버를 **둘** 부른다(건물 · 가게 이름). 여기서 지키는 것은 대부분
// **"한쪽이 죽어도 다른 쪽은 산다"** 와 **"모르는 것을 없는 것이라 말하지 않는다"** 다.

function storeHit(over: Partial<StoreHit> = {}): StoreHit {
  return {
    pnu: '1168010100100010000',
    bld_id: '1168010100100010000_1024110',
    bld_nm: '테스트빌딩',
    road_addr: '서울 강남구 테헤란로 1',
    jibun_addr: '서울 강남구 역삼동 823-4',
    lat: 37.5,
    lng: 127.03,
    bld_cnt_in_pnu: 1,
    floor_cnt: 5,
    min_floor: 1,
    max_floor: 5,
    has_roof: false,
    matched_names: ['스타벅스역삼점'],
    match_store_cnt: 1,
    total_parcel_cnt: 1,
    total_store_cnt: 1,
    too_broad: false,
    store_snapshot_ym: '202606',
    ...over,
  };
}

describe('BuildingSearch — 가게 이름으로 찾은 땅', () => {
  function setup(over: Partial<Parameters<typeof BuildingSearch>[0]> = {}) {
    const onSelect = vi.fn();
    render(
      <BuildingSearch
        onSelect={onSelect}
        onSearchStart={vi.fn()}
        selectedBldId={null}
        sigungu="11680"
        sigunguName="강남구"
        {...over}
      />,
    );
    const input = screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;
    return { onSelect, input };
  }

  function search(input: HTMLInputElement, text: string) {
    fireEvent.change(input, { target: { value: text } });
    fireEvent.submit(input.closest('form')!);
  }

  /** 함수 이름으로 답을 배정하는 가짜 서버. 안 적은 함수는 빈 배열이다. */
  function serverGives(answers: Record<string, { data?: unknown; error?: unknown }>) {
    rpc.mockImplementation((fn: string) =>
      Promise.resolve({ data: null, error: null, ...(answers[fn] ?? { data: [] }) }),
    );
  }

  const region = () => screen.queryByRole('region', { name: '가게 이름으로 찾은 땅' });

  it('건물 구역과 가게 구역을 **함께** 그리고, 서버를 나란히 부른다', async () => {
    serverGives({
      search_buildings: { data: [hit({ bld_nm: '건물결과', total_cnt: 1 })] },
      search_stores: { data: [storeHit({ total_parcel_cnt: 12, total_store_cnt: 30 })] },
    });
    const { input } = setup();
    search(input, '스타벅스');

    await waitFor(() => expect(screen.getByText('건물결과')).toBeTruthy());
    // 사용자가 고를 것이 없다 — 한 번 눌렀는데 두 답이 온다.
    expect(screen.getByText(/이 이름의 가게가 있는 땅 12곳 · 가게 30곳/)).toBeTruthy();
    expect(screen.getByText('스타벅스역삼점')).toBeTruthy();
    // ⛔ "이 건물의 가게"가 아니라 **이 땅에** — 층별 화면의 점포 칸과 세는 대상이 다르다.
    expect(screen.getByText(/이 땅에 가게 1곳 일치/)).toBeTruthy();
    // 분기 도장은 서버가 준 값을 옮긴 것이다(화면에 글자로 박지 않는다).
    expect(screen.getByText(/2026년 6월 기준 점포 자료/)).toBeTruthy();

    expect(rpc.mock.calls[0]).toEqual([
      'search_buildings',
      { q: '스타벅스', lim: expect.any(Number), sigungu: '11680' },
    ]);
    expect(rpc.mock.calls[1]).toEqual([
      'search_stores',
      { q: '스타벅스', lim: expect.any(Number), sigungu: '11680', p_offset: 0 },
    ]);

    /*
      ⛔ 이 구역은 `.search` **안**에 있어야 한다 — 종이에서 조종 장치가 통째로 빠지는 것이
         `.search` 를 지우는 인쇄 CSS 한 줄이기 때문이다. 밖으로 나가면 검색 상자만 사라지고
         가게 목록은 종이에 남는다(결정 0020).
      ⓘ 인쇄는 거의 전부가 CSS 라 jsdom 이 원리적으로 못 본다 — 그래서 "안 보인다" 대신
        **조상**으로 대신 잰다. 진짜 인쇄 모양은 E2E 가 본다.
    */
    expect(region()!.closest('.search')).not.toBeNull();
  });

  it('그 이름의 가게가 없으면 구역 자체가 없다', async () => {
    serverGives({
      search_buildings: { data: [hit({ total_cnt: 1 })] },
      search_stores: { data: [] },
    });
    const { input } = setup();
    search(input, '테헤란로');
    await waitFor(() => expect(screen.getByText('테스트빌딩')).toBeTruthy());
    expect(region()).toBeNull();
  });

  it('너무 넓은 이름이면 몇 곳인지와 함께 좁히라고 말한다', async () => {
    // ⓘ 건물 쪽처럼 안내창(모달)을 띄우지 않는다 — 멀쩡한 건물 결과를 덮지 않기 위해서다.
    serverGives({
      search_buildings: { data: [hit({ total_cnt: 1 })] },
      search_stores: {
        data: [
          // ⛔ 서버는 이 한 줄의 pnu 를 null 로 보낸다(2026-09-09c broad 가지).
          storeHit({
            pnu: null as unknown as string,
            too_broad: true,
            total_store_cnt: 33630,
            matched_names: null,
          }),
        ],
      },
    });
    const { input } = setup();
    search(input, '카페');
    await waitFor(() => expect(screen.getByText(/이름의 가게가/)).toBeTruthy());
    expect(screen.getByText('33,630곳')).toBeTruthy();
    expect(screen.getByText(/더 좁혀 주세요/)).toBeTruthy();
    // 건물 결과는 그대로 서 있어야 한다.
    expect(screen.getByText('테스트빌딩')).toBeTruthy();
  });

  it('건물 쪽이 "너무 넓은 검색"이어도 가게 구역은 그대로 서고 **눌린다**', async () => {
    /*
      ⛔ 예전에는 건물 쪽 안내가 덮개(모달)였다 — `position:fixed; inset:0` 이라 화면을 통째로
         덮어, 건물이 0건이라 안내가 뜬 그 순간에도 멀쩡히 서 있던 **가게 결과**를 가리고
         클릭까지 삼켰다(결정 0028 §백로그 🟡-10). 건물 0건과 가게 0건은 서로 다른 일이다.
    */
    serverGives({
      search_buildings: { data: [] },
      search_scope: { data: [{ too_broad: true, match_cnt: 13529 }] },
      search_stores: { data: [storeHit({ bld_nm: '가게있는건물' })] },
    });
    const { input, onSelect } = setup();
    search(input, '강남');

    await waitFor(() => expect(screen.getByText(/너무 넓은 검색/)).toBeTruthy());
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(region()).toBeTruthy();
    /*
      ⚠️ 여기서 **진짜 힘을 쓰는 단언은 바로 위 `queryByRole('dialog')` 이 null 이라는 것**이다.
         jsdom 에는 레이아웃도 히트 테스트도 없어서 덮개가 있든 없든 `fireEvent.click` 은
         그대로 꽂힌다 — 아래 클릭만 두면 옛 모달에서도 초록인 가짜 시험이 된다. 클릭은
         "줄이 여전히 버튼으로 살아 있는가"까지만 본다.
    */
    fireEvent.click(screen.getByRole('button', { name: /가게있는건물/ }));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it('가게 질의만 실패하면 건물 결과는 서고, 가게 구역은 못 불러왔다고 말한다', async () => {
    // ⛔ 조용히 생략하지 않는다 — 사람이 누른 결과가 아무 말 없이 사라지면 고장으로 읽힌다.
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    serverGives({
      search_buildings: { data: [hit({ bld_nm: '살아남은건물', total_cnt: 1 })] },
      search_stores: { error: { code: '42501', message: 'permission denied' } },
    });
    const { input } = setup();
    search(input, '스타벅스');

    await waitFor(() => expect(screen.getByText('살아남은건물')).toBeTruthy());
    expect(screen.getByText('가게 이름 결과를 불러오지 못했습니다.')).toBeTruthy();
    // 내부 표 이름이 화면으로 새면 안 된다.
    expect(screen.queryByText(/permission denied/)).toBeNull();
  });

  it('서버에 함수가 아직 없으면(PGRST202) 구역만 조용히 빠진다', async () => {
    // 배포 순서 탓에 잠깐 나는 정상 상태다 — 사용자가 할 수 있는 일이 없다.
    serverGives({
      search_buildings: { data: [hit({ total_cnt: 1 })] },
      search_stores: { error: { code: 'PGRST202', message: 'function does not exist' } },
    });
    const { input } = setup();
    search(input, '스타벅스');
    await waitFor(() => expect(screen.getByText('테스트빌딩')).toBeTruthy());
    expect(region()).toBeNull();
    expect(screen.queryByText('가게 이름 결과를 불러오지 못했습니다.')).toBeNull();
  });

  it('더 보기로 받는 중에 새 검색이 시작되면 늦게 온 쪽은 버린다', async () => {
    let resolveMore!: (v: unknown) => void;
    let storeCalls = 0;
    rpc.mockImplementation((fn: string) => {
      if (fn !== 'search_stores') return Promise.resolve({ data: [], error: null });
      storeCalls += 1;
      if (storeCalls === 1) {
        return Promise.resolve({
          data: [storeHit({ bld_nm: '첫쪽건물', total_parcel_cnt: 2 })],
          error: null,
        });
      }
      // 2번째 = 더 보기(느리게), 3번째 = 새 검색
      return storeCalls === 2
        ? new Promise((r) => (resolveMore = r))
        : Promise.resolve({ data: [], error: null });
    });

    const { input } = setup();
    search(input, '스타벅스');
    await waitFor(() => expect(screen.getByText('첫쪽건물')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: '더 보기' }));
    // 오프셋은 **손에 든 줄 수**다 — 쪽수를 세면 마지막 쪽이 딱 떨어질 때 어긋난다.
    expect(rpc).toHaveBeenCalledWith('search_stores', {
      q: '스타벅스',
      lim: expect.any(Number),
      sigungu: '11680',
      p_offset: 1,
    });

    search(input, '다른가게');
    resolveMore({ data: [storeHit({ pnu: 'b', bld_nm: '둘째쪽건물' })], error: null });
    await waitFor(() => expect(region()).toBeNull());
    expect(screen.queryByText('둘째쪽건물')).toBeNull();
  });

  it('앞 검색의 더 보기가 실패해도 새 검색 결과 위에 그 실패를 적지 않는다', async () => {
    /*
      ⚠️ 이어 붙이기만 막아서는 모자란다 — 붙일 줄이 없어도 **"더 불러오지 못했습니다"라는
         글자**는 남는다. 새 검색이 멀쩡히 성공했는데 그 아래 옛 검색의 실패가 적혀 있으면
         사람은 방금 누른 검색이 반쯤 실패했다고 읽는다. 그래서 요청 번호로 한 번 더 막는다.
    */
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    let failMore!: (v: unknown) => void;
    let storeCalls = 0;
    rpc.mockImplementation((fn: string) => {
      if (fn !== 'search_stores') return Promise.resolve({ data: [], error: null });
      storeCalls += 1;
      if (storeCalls === 1) {
        return Promise.resolve({
          data: [storeHit({ bld_nm: '첫쪽건물', total_parcel_cnt: 2 })],
          error: null,
        });
      }
      if (storeCalls === 2) return new Promise((r) => (failMore = r)); // 더 보기 — 느리게 실패
      return Promise.resolve({
        data: [storeHit({ pnu: 'c', bld_nm: '새검색건물' })],
        error: null,
      });
    });

    const { input } = setup();
    search(input, '스타벅스');
    await waitFor(() => expect(screen.getByText('첫쪽건물')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '더 보기' }));

    search(input, '다른가게');
    await waitFor(() => expect(screen.getByText('새검색건물')).toBeTruthy());
    failMore({ data: null, error: { code: '42501', message: 'boom' } });

    await waitFor(() => expect(screen.getByText('새검색건물')).toBeTruthy());
    expect(screen.queryByText('더 불러오지 못했습니다.')).toBeNull();
  });

  it('더 보기가 정상이면 두 번째 쪽이 첫 쪽 뒤에 붙는다', async () => {
    let storeCalls = 0;
    rpc.mockImplementation((fn: string) => {
      if (fn !== 'search_stores') return Promise.resolve({ data: [], error: null });
      storeCalls += 1;
      return Promise.resolve({
        data:
          storeCalls === 1
            ? [storeHit({ bld_nm: '첫쪽건물', total_parcel_cnt: 2 })]
            : [storeHit({ pnu: 'b', bld_nm: '둘째쪽건물', total_parcel_cnt: 2 })],
        error: null,
      });
    });

    const { input } = setup();
    search(input, '스타벅스');
    await waitFor(() => expect(screen.getByText('첫쪽건물')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: '더 보기' }));
    await waitFor(() => expect(screen.getByText('둘째쪽건물')).toBeTruthy());
    expect(screen.getByText('첫쪽건물')).toBeTruthy();
    // 다 받았으면 '더 보기'가 남아 있으면 안 된다(눌러도 아무 일이 없다).
    expect(screen.queryByRole('button', { name: '더 보기' })).toBeNull();
  });

  it("'더 보기'는 지금 칸에 적힌 말이 아니라 **물어봤던 말**로 다음 쪽을 받는다", async () => {
    /*
      ⛔ 사람은 결과를 보면서 입력창을 계속 고친다. 그때 칸을 다시 읽으면 **다른 검색어의
         51번째 줄**이 이 목록 뒤에 붙는다 — 에러가 아니라 조용히 섞인 거짓 목록이다.
    */
    let storeCalls = 0;
    rpc.mockImplementation((fn: string) => {
      if (fn !== 'search_stores') return Promise.resolve({ data: [], error: null });
      storeCalls += 1;
      return Promise.resolve({
        data: [storeHit({ pnu: `p${storeCalls}`, bld_nm: `쪽${storeCalls}`, total_parcel_cnt: 3 })],
        error: null,
      });
    });

    const { input } = setup();
    search(input, '스타벅스');
    await waitFor(() => expect(screen.getByText('쪽1')).toBeTruthy());

    // 검색은 안 하고 칸만 고친다(구도 함께 바꿔 본다면 그건 다른 렌더라, 여기선 말만).
    fireEvent.change(input, { target: { value: '전혀다른가게' } });
    fireEvent.click(screen.getByRole('button', { name: '더 보기' }));

    expect(rpc).toHaveBeenLastCalledWith('search_stores', {
      q: '스타벅스',
      lim: expect.any(Number),
      sigungu: '11680',
      p_offset: 1,
    });
  });

  it('더 보기 중에 새 검색이 끼어들어도 새 결과의 더 보기 버튼은 눌린다', async () => {
    /*
      ⛔ 새 검색이 '더 보기 중' 표시를 안 끄면, 날아가 있던 앞 요청은 번호가 어긋나 아무것도
         안 하고 나가므로 그 표시를 끌 사람이 아무도 없다 — 새 결과의 버튼이 처음부터 죽은
         채(disabled) 선다. 눌리지 않는다는 신호는 화면 어디에도 안 뜬다.
    */
    let hangMore!: (v: unknown) => void;
    let storeCalls = 0;
    rpc.mockImplementation((fn: string) => {
      if (fn !== 'search_stores') return Promise.resolve({ data: [], error: null });
      storeCalls += 1;
      if (storeCalls === 2) return new Promise((r) => (hangMore = r)); // 더 보기 — 영영 안 온다
      return Promise.resolve({
        data: [storeHit({ pnu: `p${storeCalls}`, bld_nm: `쪽${storeCalls}`, total_parcel_cnt: 3 })],
        error: null,
      });
    });

    const { input } = setup();
    search(input, '스타벅스');
    await waitFor(() => expect(screen.getByText('쪽1')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '더 보기' }));
    expect(screen.getByRole('button', { name: '불러오는 중…' })).toBeTruthy();

    search(input, '다른가게');
    await waitFor(() => expect(screen.getByText('쪽3')).toBeTruthy());

    const more = screen.getByRole('button', { name: '더 보기' }) as HTMLButtonElement;
    expect(more.disabled).toBe(false);
    fireEvent.click(more);
    expect(rpc).toHaveBeenLastCalledWith('search_stores', {
      q: '다른가게',
      lim: expect.any(Number),
      sigungu: '11680',
      p_offset: 1,
    });
    hangMore({ data: [], error: null }); // 뒷정리 — 매달린 약속을 풀어 준다
  });

  it('줄을 누르면 층별 화면으로 갈 **앞 12칸만** 넘긴다', async () => {
    serverGives({
      search_stores: { data: [storeHit({ match_store_cnt: 9, total_store_cnt: 40 })] },
    });
    const { input, onSelect } = setup();
    search(input, '스타벅스');
    await waitFor(() => expect(screen.getByText('테스트빌딩')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: /테스트빌딩/ }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0]).toEqual({
      bld_id: '1168010100100010000_1024110',
      pnu: '1168010100100010000',
      bld_nm: '테스트빌딩',
      road_addr: '서울 강남구 테헤란로 1',
      jibun_addr: '서울 강남구 역삼동 823-4',
      lat: 37.5,
      lng: 127.03,
      bld_cnt_in_pnu: 1,
      floor_cnt: 5,
      min_floor: 1,
      max_floor: 5,
      has_roof: false,
    });
  });

  it('대표 동이 없는 땅은 목록에서 빼지 않고, 갈 수 없다고 적는다', async () => {
    // ⛔ 빼 버리면 "그 이름의 가게가 여기 없다"는 거짓말이 된다.
    serverGives({
      search_stores: {
        data: [storeHit({ bld_id: null, bld_nm: null, matched_names: ['가게하나'] })],
      },
    });
    const { input, onSelect } = setup();
    search(input, '가게하나');
    await waitFor(() => expect(screen.getByText('가게하나')).toBeTruthy());
    expect(screen.getByText('(이름 없는 건물)')).toBeTruthy();
    expect(screen.getByText(/건물 자료가 없어 층별 화면으로 갈 수 없습니다/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /이름 없는 건물/ })).toBeNull();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('새 검색을 시작하면 앞 검색어의 가게 줄을 먼저 비운다', async () => {
    let storeCalls = 0;
    rpc.mockImplementation((fn: string) => {
      if (fn !== 'search_stores') return Promise.resolve({ data: [], error: null });
      storeCalls += 1;
      return storeCalls === 1
        ? Promise.resolve({ data: [storeHit({ bld_nm: '옛가게건물' })], error: null })
        : new Promise(() => {}); // 두 번째 검색은 영영 안 온다
    });
    const { input } = setup();
    search(input, '스타벅스');
    await waitFor(() => expect(screen.getByText('옛가게건물')).toBeTruthy());

    search(input, '다른가게');
    await waitFor(() => expect(screen.queryByText('옛가게건물')).toBeNull());
  });
});

// ── 안내창이 뜰 때 옛 결과가 남지 않는다 (2026-09-10) ────────────────────────
//
// ⛔ ①한 글자 ②구 미선택은 서버를 부르기 **전에** 되돌아 나간다. 그 자리에서 옛 결과를
//    비우지 않으면, 직전 검색이 성공한 상태에서 한 글자를 넣는 순간 옛 건물 목록과 옛 가게
//    구역이 **그대로 선 위에** 안내창이 덮인다 — 사람은 그것을 방금 넣은 말의 결과로 읽는다.
//    조기 반환이 `setStore({ at: 'hidden' })` 보다 앞에 있어서 나던 일이고, 이 흐름을 보는
//    시험이 여태 0개였다(전부 새 화면에서 시작했다).

describe('BuildingSearch — 안내창이 뜰 때 옛 결과가 남지 않는다', () => {
  function props(over: Partial<Parameters<typeof BuildingSearch>[0]> = {}) {
    return {
      onSelect: vi.fn(),
      onSearchStart: vi.fn(),
      selectedBldId: null,
      sigungu: '11680' as string | null,
      sigunguName: '강남구' as string | null,
      ...over,
    };
  }

  function search(input: HTMLInputElement, text: string) {
    fireEvent.change(input, { target: { value: text } });
    fireEvent.submit(input.closest('form')!);
  }

  /** 건물도 가게도 나오는 정상 검색. */
  function serverAnswers() {
    rpc.mockImplementation((fn: string) =>
      fn === 'search_stores'
        ? Promise.resolve({ data: [storeHit({ bld_nm: '옛가게건물' })], error: null })
        : Promise.resolve({ data: [hit({ total_cnt: 1 })], error: null }),
    );
  }

  const region = () => screen.queryByRole('region', { name: '가게 이름으로 찾은 땅' });

  it('한 글자를 넣으면 앞 검색의 건물 목록·가게 구역이 함께 사라진다', async () => {
    serverAnswers();
    const p = props();
    render(<BuildingSearch {...p} />);
    const input = screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;

    search(input, '테헤란로');
    await waitFor(() => expect(screen.getByText('테스트빌딩')).toBeTruthy());
    expect(region()).toBeTruthy();

    search(input, '동');
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(screen.queryByText('테스트빌딩')).toBeNull();
    expect(region()).toBeNull();
    // 위(목록·가게 구역)만 비우고 아래 층 스택을 남기면 반쪽이다 — 정상 검색과 같이
    // 상위에도 "새 검색 시작"을 알려 옛 건물 선택을 푼다(첫 검색 1회 + 지금 1회).
    expect(p.onSearchStart).toHaveBeenCalledTimes(2);
  });

  it('구를 다시 안 고른 채 검색하면 앞 검색의 결과가 함께 사라진다', async () => {
    serverAnswers();
    const p = props();
    const { rerender } = render(<BuildingSearch {...p} />);
    const input = screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;

    search(input, '테헤란로');
    await waitFor(() => expect(screen.getByText('테스트빌딩')).toBeTruthy());
    expect(region()).toBeTruthy();

    // 시·도를 바꾸면 구 선택이 풀린다 — 그 상태로 다시 검색을 누른 경우다.
    // ⓘ App 은 `key={sigungu ?? …}` 로 이미 새로 그리므로 실제 사용자 경로는 ①(한 글자)뿐이다
    //   — 이 시험은 그와 무관하게 컴포넌트 스스로의 계약을 본다.
    rerender(<BuildingSearch {...p} sigungu={null} sigunguName={null} />);
    search(input, '테헤란로');

    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(screen.getByText('먼저 지역을 골라 주세요')).toBeTruthy();
    expect(screen.queryByText('테스트빌딩')).toBeNull();
    expect(region()).toBeNull();
  });
});

// ── 검색창 문구 가드 (결정 0028) ────────────────────────────────────────────

describe('BuildingSearch — 검색창 문구', () => {
  function setup() {
    render(
      <BuildingSearch
        onSelect={vi.fn()}
        onSearchStart={vi.fn()}
        selectedBldId={null}
        sigungu="11680"
        sigunguName="강남구"
      />,
    );
    return screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;
  }

  it('무엇으로 찾을 수 있는지 네 가지를 모두 적는다 — 가게 이름 포함', () => {
    // ⛔ 이 문구를 지키는 시험이 여태 **0개**였다(결정 0028 실측). 가게 이름으로도 찾을 수
    //    있다는 것을 아무 데도 안 적으면, 기능이 있어도 아무도 쓰지 않는다.
    const input = setup();
    for (const part of ['건물명', '도로명주소', '지번', '가게 이름', '스타벅스']) {
      expect(input.placeholder).toContain(part);
    }
  });

  it('읽어 주는 기기가 부르는 이름은 그대로 둔다', () => {
    // 바꾸면 vitest 9곳 + E2E 2곳이 한꺼번에 깨진다 — 문구는 placeholder 로만 늘린다.
    const input = setup();
    expect(input.getAttribute('aria-label')).toBe('건물명 또는 주소');
  });
});
