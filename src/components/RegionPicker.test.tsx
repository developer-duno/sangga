import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { SIDOS, OPEN_SIDO_CODES, isOpenSido, openRegionLabel, isOpenPnu } from '../lib/regions';
import type { OpenSigungu } from '../types';

/**
 * 지역 게이트 + 구 고르기 테스트 (결정 0006 + 2026-08-13e 사장님 결정).
 *
 * 핵심 불변식 둘:
 * ① 전국을 다 보여주되 열린 곳만 열려 있다고 말한다 — 지역명을 테스트에 박지 않는다.
 * ② 열린 시도를 누르면 실제로 자료가 있는 구만 서버(`list_open_sigungu`)에서 받아
 *    보여주고, 고른 구가 코드+이름으로 부모에 전달된다.
 */

const rpc = vi.fn();
vi.mock('../lib/supabase', () => ({
  supabase: { rpc: (...args: unknown[]) => rpc(...args) },
}));

const { RegionPicker } = await import('./RegionPicker');

function gu(over: Partial<OpenSigungu> = {}): OpenSigungu {
  return {
    sido_code: '11',
    sido_nm: '서울',
    sigungu_code: '11680',
    sigungu_nm: '강남구',
    building_cnt: 14223,
    ...over,
  };
}

beforeEach(() => {
  rpc.mockReset();
  rpc.mockResolvedValue({ data: [gu()], error: null });
});

afterEach(() => cleanup());

// ── regions.ts ──────────────────────────────────────────────────────────

describe('regions.ts', () => {
  it('전국 시도를 담는다(광주·전남 통합 반영 후 16개)', () => {
    expect(SIDOS).toHaveLength(16);
  });

  it('시도 코드는 2자리 숫자이고 중복이 없다', () => {
    const codes = SIDOS.map((s) => s.code);
    expect(new Set(codes).size).toBe(codes.length);
    for (const c of codes) expect(c).toMatch(/^\d{2}$/);
  });

  it('옛 광주(29)·전남(46) 코드는 목록에 없다 — 전남광주(12)로 통합됐다', () => {
    const codes = new Set(SIDOS.map((s) => s.code));
    expect(codes.has('29')).toBe(false);
    expect(codes.has('46')).toBe(false);
    expect(codes.has('12')).toBe(true);
  });

  it('열린 코드는 반드시 목록 안에 있는 시도여야 한다', () => {
    // 오타로 없는 코드를 열어 두면 화면엔 아무 표시도 안 나고 조용히 무시된다.
    const known = new Set(SIDOS.map((s) => s.code));
    for (const c of OPEN_SIDO_CODES) expect(known.has(c)).toBe(true);
  });

  it('openRegionLabel 은 열린 시도 이름을 이어 붙인다', () => {
    const expected = SIDOS.filter((s) => isOpenSido(s.code))
      .map((s) => s.name)
      .join('·');
    expect(openRegionLabel()).toBe(expected);
  });

  it('isOpenPnu 는 PNU 앞 2자리로 판정한다', () => {
    const open = OPEN_SIDO_CODES[0];
    expect(isOpenPnu(open + '68010100108230004')).toBe(true);
    expect(isOpenPnu('9999999999999999999')).toBe(false);
    expect(isOpenPnu(null)).toBe(false);
    expect(isOpenPnu('')).toBe(false);
  });
});

// ── RegionPicker — 시도 목록·잠긴 지역 안내 (기존 동작 유지) ────────────────

describe('RegionPicker — 시도 목록', () => {
  function setup(
    over: Partial<Parameters<typeof RegionPicker>[0]> = {},
    list: OpenSigungu[] = [
      gu(),
      gu({ sigungu_code: '11440', sigungu_nm: '마포구' }),
      gu({ sido_code: '30', sido_nm: '대전광역시', sigungu_code: '30200', sigungu_nm: '유성구' }),
    ],
  ) {
    rpc.mockResolvedValue({ data: list, error: null });
    const onSelectSigungu = vi.fn();
    render(
      <RegionPicker selectedSigungu={null} onSelectSigungu={onSelectSigungu} {...over} />,
    );
    return { onSelectSigungu };
  }

  it('자료가 없는 지역은 아예 보여주지 않는다', async () => {
    // 사장님 결정(2026-08-13): "굳이 서비스 안 하는 도시를 보여줘야 할까?"
    // 예전에는 전국 17개를 다 그리고 잠긴 곳을 🔒 로 표시했다. 누를 수 없는 칩을
    // 늘어놓는 대신 안내 문장 한 줄로 대신한다.
    setup();
    await waitFor(() => expect(screen.getByRole('button', { name: '서울' })).toBeTruthy());

    const shown = SIDOS.filter((s) =>
      screen.queryByRole('button', { name: new RegExp(`^${s.name}$`) }),
    );
    expect(shown.map((s) => s.code).sort()).toEqual(['11', '30']);
    expect(screen.queryByText(/🔒/)).toBeNull();
  });

  it('목록은 서버 응답에서 뽑는다 — 프론트에 박아 두지 않는다', async () => {
    // 자료가 한 시도만 오면 한 칩만 보여야 한다. 하드코딩이면 이 검사가 깨진다.
    setup({}, [gu()]);
    await waitFor(() => expect(screen.getByRole('button', { name: '서울' })).toBeTruthy());
    expect(screen.queryByRole('button', { name: '대전' })).toBeNull();
  });

  it('강조는 한 번에 하나뿐이다 — 여러 도시가 동시에 선택된 것처럼 보이면 안 된다', async () => {
    // 사장님이 실제로 발견한 버그(2026-08-13): `--on` 이 "열린 지역"을 뜻해서
    // 열린 시도가 전부 파랗게 칠해졌고, 자료 있는 곳만 남기자 모든 칩이 선택된
    // 것처럼 보였다. 이제 `--on` 은 "지금 펼친 시도" 하나만 가리킨다.
    setup();
    await waitFor(() => expect(screen.getByRole('button', { name: '서울' })).toBeTruthy());

    const chips = () =>
      ['서울', '대전'].map((n) => screen.getByRole('button', { name: n }));
    expect(chips().filter((b) => b.className.includes('region__chip--on'))).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: '대전' }));
    const on = chips().filter((b) => b.className.includes('region__chip--on'));
    expect(on).toHaveLength(1);
    expect(on[0].textContent).toBe('대전');
  });

  it('시도를 누르면 그 시도의 구만 펼쳐지고, 다시 누르면 접힌다', async () => {
    setup();
    await waitFor(() => expect(screen.getByRole('button', { name: '서울' })).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: '서울' }));
    expect(screen.getByRole('button', { name: '강남구' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: '유성구' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '서울' }));
    expect(screen.queryByRole('button', { name: '강남구' })).toBeNull();
  });

  it('다른 시도를 누르면 그쪽 구로 갈아탄다', async () => {
    setup();
    await waitFor(() => expect(screen.getByRole('button', { name: '서울' })).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: '서울' }));
    fireEvent.click(screen.getByRole('button', { name: '대전' }));
    expect(screen.getByRole('button', { name: '유성구' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: '강남구' })).toBeNull();
  });

  it('"다른 지역은 준비 중" 안내는 남긴다 — 목록에서 뺐다고 영영 안 된다는 뜻은 아니다', async () => {
    setup();
    await waitFor(() => expect(screen.getByRole('button', { name: '서울' })).toBeTruthy());
    expect(screen.getByText(/준비 중/)).toBeTruthy();
    expect(screen.getByText(openRegionLabel())).toBeTruthy();
  });
});

// ── RegionPicker — 구 고르기 (2026-08-13 신설) ──────────────────────────────

describe('RegionPicker — 구 목록', () => {
  function setup(over: Partial<Parameters<typeof RegionPicker>[0]> = {}) {
    const onSelectSigungu = vi.fn();
    render(
      <RegionPicker selectedSigungu={null} onSelectSigungu={onSelectSigungu} {...over} />,
    );
    return { onSelectSigungu };
  }

  it('구 목록을 서버에서 받아 그린다 — 열린 시도를 누르면 그 시도의 구만 보인다', async () => {
    rpc.mockResolvedValue({
      data: [
        gu({ sigungu_code: '11680', sigungu_nm: '강남구' }),
        gu({ sigungu_code: '30170', sido_code: '30', sido_nm: '대전', sigungu_nm: '서구' }),
      ],
      error: null,
    });
    setup();
    await waitFor(() => expect(rpc).toHaveBeenCalledWith('list_open_sigungu'));

    fireEvent.click(screen.getByRole('button', { name: /^서울$/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: '강남구' })).toBeTruthy());
    // 대전 구는 서울을 펼쳤을 때 안 섞여 나온다.
    expect(screen.queryByRole('button', { name: '서구' })).toBeNull();
  });

  it('구를 고르면 코드와 이름을 부모에게 알린다', async () => {
    rpc.mockResolvedValue({
      data: [gu({ sigungu_code: '11680', sigungu_nm: '강남구' })],
      error: null,
    });
    const { onSelectSigungu } = setup();
    // ⚠️ 시도 칩도 서버 응답(list_open_sigungu)을 받은 뒤에 그려진다 — 기다렸다 누른다.
    await waitFor(() => expect(screen.getByRole('button', { name: /^서울$/ })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /^서울$/ }));
    fireEvent.click(screen.getByRole('button', { name: '강남구' }));
    expect(onSelectSigungu).toHaveBeenCalledWith('11680', '강남구');
  });

  it('이미 고른 구를 다시 누르면 해제한다', async () => {
    rpc.mockResolvedValue({
      data: [gu({ sigungu_code: '11680', sigungu_nm: '강남구' })],
      error: null,
    });
    const { onSelectSigungu } = setup({ selectedSigungu: '11680' });
    await waitFor(() => expect(screen.getByRole('button', { name: /^서울$/ })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /^서울$/ }));
    fireEvent.click(screen.getByRole('button', { name: '강남구' }));
    expect(onSelectSigungu).toHaveBeenCalledWith(null, null);
  });

  it('선택한 구가 있으면 화면에 알려주고, 해제 버튼으로 해제할 수 있다', async () => {
    rpc.mockResolvedValue({
      data: [gu({ sigungu_code: '11680', sigungu_nm: '강남구' })],
      error: null,
    });
    const { onSelectSigungu } = setup({ selectedSigungu: '11680' });
    await waitFor(() => expect(screen.getByText(/선택한 지역/)).toBeTruthy());
    expect(screen.getByText(/강남구/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '선택 해제' }));
    expect(onSelectSigungu).toHaveBeenCalledWith(null, null);
  });

  it('지역 목록을 못 받으면 이유를 말하고 다시 시도할 길을 준다', async () => {
    // 목록이 서버에서 오므로 실패하면 고를 것이 없다. 그때 조용히 빈 화면을 두면
    // "고장난 것"처럼 보인다 — 무슨 일인지 말하고 다시 시도 버튼을 준다.
    rpc.mockResolvedValue({ data: null, error: { message: 'network error' } });
    setup();
    await waitFor(() => expect(screen.getByText(/불러오지 못했습니다/)).toBeTruthy());
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeTruthy();
    // 안내 문장(본체)은 그대로 살아 있어야 한다.
    expect(screen.getByText(/준비 중/)).toBeTruthy();
  });
});
