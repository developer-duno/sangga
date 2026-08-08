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
  function setup(over: Partial<Parameters<typeof BuildingSearch>[0]> = {}) {
    const onSelect = vi.fn();
    const onSearchStart = vi.fn();
    render(
      <BuildingSearch
        onSelect={onSelect}
        onSearchStart={onSearchStart}
        selectedBldId={null}
        {...over}
      />,
    );
    const input = screen.getByLabelText('건물명 또는 도로명주소') as HTMLInputElement;
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
    await waitFor(() => expect(rpc).toHaveBeenCalledTimes(1));
    expect(rpc).toHaveBeenCalledWith('search_buildings', {
      q: '스타(별)빌딩 100%',
      lim: expect.any(Number),
    });
  });

  it('앞뒤 공백은 떼고 보낸다', async () => {
    const { input } = setup();
    search(input, '  미도맨션  ');
    await waitFor(() => expect(rpc).toHaveBeenCalledTimes(1));
    expect(rpc.mock.calls[0][1]).toMatchObject({ q: '미도맨션' });
  });

  it('공백뿐인 검색어로는 서버를 부르지 않는다', () => {
    const { onSearchStart, input } = setup();
    search(input, '    ');
    expect(rpc).not.toHaveBeenCalled();
    expect(onSearchStart).not.toHaveBeenCalled();
  });

  it('결과가 없으면 담긴 범위가 강남구뿐임을 알려준다', async () => {
    const { input } = setup();
    search(input, '없는건물');
    await waitFor(() => expect(screen.getByText(/결과가 없습니다/)).toBeTruthy());
    expect(screen.getByText(/강남구/)).toBeTruthy();
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
