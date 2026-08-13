import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import type { BuildingHit } from '../types';

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
  FLOOR_STACK_VIEW: 'v_floor_stack',
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
    let resolveFirst!: (v: unknown) => void;
    rpc.mockReturnValueOnce(new Promise((r) => (resolveFirst = r)));
    rpc.mockResolvedValueOnce({
      data: [hit({ bld_nm: '나중검색결과', total_cnt: 1 })],
      error: null,
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


// ── 너무 넓은 검색 안내창 (2026-08-13) ──────────────────────────────────────
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

  it('두 글자여도 서버가 너무 넓다고 하면 안내하고, 걸린 곳 수를 알려준다', async () => {
    // '강남'은 두 글자지만 구 조각이라 13,529곳과 맞는다. 반대로 '명동'은 두 글자여도
    // 동이 확정된다 — **글자 수로는 안 갈린다.** 그래서 서버가 세어 판정한다.
    serverSays(true, 13529);
    const input = setup();
    search(input, '강남');
    await waitFor(() => expect(screen.getByRole('dialog')).toBeTruthy());
    expect(screen.getByText(/‘강남’/)).toBeTruthy();
    expect(screen.getByText('13,529곳')).toBeTruthy();
    // 결과 목록 쪽 "결과가 없습니다"와 겹쳐 뜨면 안 된다(두 말이 동시에 보인다).
    expect(screen.queryByText(/결과가 없습니다/)).toBeNull();
  });

  it('무엇을 넣으면 되는지 알려준다 (동 이름·건물 이름·지번)', async () => {
    serverSays(true, 163487);
    const input = setup();
    search(input, '서울');
    await waitFor(() => expect(screen.getByRole('dialog')).toBeTruthy());
    for (const example of ['역삼동', '그랑프리빌딩', '역삼동 823-4']) {
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
    serverSays(true, 99999);
    const input = setup();
    search(input, '서울');
    await waitFor(() => expect(screen.getByRole('dialog')).toBeTruthy());
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
