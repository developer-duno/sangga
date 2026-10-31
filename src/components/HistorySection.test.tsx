import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
import type { StoreHistoryRow } from '../types';

/**
 * 「이 자리 가게 이력 (점포 자료 누적)」 카드 — 결정 0045 PR④(본보기 = SalesSection.test).
 *
 * 여기서 특히 지키는 것
 *  ① 못 읽었으면(PGRST202·오류·모양 이상·0줄) 카드째 숨긴다 — 「자료 없음」이라 적지 않는다
 *  ② no_data 한 줄이면 카드는 서되 요약만
 *  ③ 묶음 둘(지금 보임 → 전에 보임 · 서버 차례 그대로) · 칩 · 「N분기 이상」
 *  ④ 더 보기 = 서버 넘기기(p_offset) · 다 받으면 단추 없음 · total 이 바뀐 답은 버림 · 실패하면 단추 거둠
 *  ⑤ 필지가 바뀌면 옛 답을 비운다 · 어긋남 줄은 신선도 표 점포 줄과 다를 때만 · 각주 셋(「폐업」은 둘째 문장 한 곳)
 */

type Res = { data: unknown; error: unknown };
const state = {
  /** p_offset 별 답(없으면 0 쪽 답). 함수로 두면 인자를 보고 답한다. */
  history: ((): Res | Promise<Res> => ({ data: null, error: { code: 'PGRST202' } })) as (
    args: Record<string, unknown>,
  ) => Res | Promise<Res>,
  fresh: { data: null, error: { code: 'PGRST202' } } as Res,
};
const rpcCalls: Array<{ fn: string; args: Record<string, unknown> }> = [];

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string, args: Record<string, unknown> = {}) => {
      rpcCalls.push({ fn, args });
      if (fn === 'get_data_freshness') return Promise.resolve(state.fresh);
      return Promise.resolve(state.history(args));
    },
  },
}));

const { HistorySection } = await import('./HistorySection');
const { resetDataFreshnessCache } = await import('../lib/loadDataFreshness');

const PNU = '1168010100100010000';
const OTHER = '3017010100100010000';
const historyCalls = () => rpcCalls.filter((c) => c.fn === 'get_store_history');

function row(i: number, over: Partial<StoreHistoryRow> = {}): StoreHistoryRow {
  return {
    status: 'ok',
    floor_no: 1,
    biz_name: `가게${String(i).padStart(2, '0')}`,
    first_ym: '202003',
    last_ym: '202606',
    seen_cnt: 26,
    is_current: true,
    truncated: false,
    total_cnt: 23,
    current_cnt: 6,
    history_first_ym: '201712',
    history_last_ym: '202606',
    ...over,
  };
}

/** 23줄 — 지금 보임 6(첫 줄은 첫 분기부터) · 안 보임 17. 서버 차례 그대로. */
const ALL: StoreHistoryRow[] = Array.from({ length: 23 }, (_v, i) =>
  i === 0
    ? row(i, { first_ym: '201712', seen_cnt: 35, truncated: true })
    : i < 6
      ? row(i)
      : row(i, { is_current: false, first_ym: '201903', last_ym: '202312', seen_cnt: 20, floor_no: i % 2 ? null : 2 }),
);

function paged(args: Record<string, unknown>): Res {
  const off = Number(args.p_offset ?? 0);
  const lim = Number(args.p_limit ?? 20);
  return { data: ALL.slice(off, off + lim), error: null };
}

const NO_DATA: StoreHistoryRow = {
  status: 'no_data',
  floor_no: null,
  biz_name: null,
  first_ym: null,
  last_ym: null,
  seen_cnt: null,
  is_current: null,
  truncated: null,
  total_cnt: 0,
  current_cnt: 0,
  history_first_ym: '201712',
  history_last_ym: '202606',
};

beforeEach(() => {
  rpcCalls.length = 0;
  state.history = () => ({ data: null, error: { code: 'PGRST202' } });
  state.fresh = { data: null, error: { code: 'PGRST202' } };
  resetDataFreshnessCache();
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function settle() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
}

describe('HistorySection — 숨김 · no_data', () => {
  it.each([
    ['함수 없음(PGRST202)', () => ({ data: null, error: { code: 'PGRST202' } })],
    ['오류', () => ({ data: null, error: { message: 'boom' } })],
    ['모양 이상', () => ({ data: [{ status: 'ok' }], error: null })],
    ['0줄(적재 전)', () => ({ data: [], error: null })],
  ])('%s → 카드째 숨김(「자료 없음」 글 0)', async (_label, fn) => {
    state.history = fn as typeof state.history;
    const { container } = render(<HistorySection pnu={PNU} />);
    await settle();
    expect(container.querySelector('section.card')).toBeNull();
    expect(container.textContent).toBe('');
    // 첫 쪽은 인자 `{ p_pnu }` 하나(함수 기본값 20·0).
    expect(historyCalls()).toEqual([{ fn: 'get_store_history', args: { p_pnu: PNU } }]);
  });

  it('no_data 한 줄 → 카드는 서되 요약만(본문 없음)', async () => {
    state.history = () => ({ data: [NO_DATA], error: null });
    const { container } = render(<HistorySection pnu={PNU} />);
    await waitFor(() => expect(container.querySelector('section.card')).not.toBeNull());
    expect(container.querySelector('.card__title')?.textContent).toBe('이 자리 가게 이력 (점포 자료 누적)');
    expect(container.querySelector('.card__summary')?.textContent).toBe(
      '2017년 4분기 이후 점포 자료에 이 땅의 가게가 보이지 않습니다',
    );
    expect(container.querySelector('.hist__row')).toBeNull();
    expect(container.querySelector('.hist__notes')).toBeNull();
  });
});

describe('HistorySection — 그리기', () => {
  it('★ 요약 · 묶음 둘(서버 차례 그대로) · 칩 · 「35분기 이상」 · 각주 셋', async () => {
    state.history = paged;
    const { container } = render(<HistorySection pnu={PNU} />);
    await waitFor(() => expect(container.querySelector('section.card.hist')).not.toBeNull());
    expect(container.querySelector('.card__summary')?.textContent).toBe(
      '지금 보이는 가게 6곳 · 전에 보였던 가게 17곳 · 2017년 4분기부터 점포 자료 35분기',
    );
    const groups = container.querySelectorAll('.hist__grp');
    expect(groups).toHaveLength(2);
    expect(groups[0].querySelector('.hist__grp-h')?.textContent).toBe('지금 자료에 보이는 가게 6곳');
    expect(groups[1].querySelector('.hist__grp-h')?.textContent).toBe('전에 보였던 가게 17곳 · 지금은 자료에 안 보임');
    const names = [...container.querySelectorAll('.hist__nm')].map((n) => n.textContent);
    expect(names).toEqual(ALL.slice(0, 20).map((r) => r.biz_name));
    expect(groups[0].querySelectorAll('.hist__chip')).toHaveLength(0);
    expect(groups[1].querySelectorAll('.hist__chip')).toHaveLength(14);
    expect(groups[1].querySelector('.hist__chip')?.textContent).toBe('지금은 안 보임');
    const first = groups[0].querySelector('.hist__row')!;
    expect(first.querySelector('.hist__fl')?.textContent).toBe('1층');
    expect(first.querySelector('.hist__sp')?.textContent).toBe('자료에 35분기 이상 보임 · 자료 시작(2017년 4분기)부터 계속');
    expect(first.querySelector('.hist__sp b')?.textContent).toBe('35분기 이상');
    expect(groups[1].querySelector('.hist__row .hist__fl')?.textContent).toBe('2층');
    expect([...groups[1].querySelectorAll('.hist__fl')].map((n) => n.textContent)).toContain('층 모름');
    const notes = [...container.querySelectorAll('.hist__notes li')].map((n) => n.textContent ?? '');
    expect(notes).toHaveLength(3);
    expect(notes[1].startsWith('자료에서 안 보이는 것은 폐업이 아닐 수 있습니다.')).toBe(true);
    // 「폐업」은 그 문장 한 곳뿐이다(카드 글 전체에서).
    expect((container.textContent ?? '').split('폐업').length - 1).toBe(1);
    expect(container.querySelector('.grade__badge')?.textContent).toBe('D등급 · 간접추론');
    expect(container.querySelector('.hist__lag')).toBeNull();
  });

  it('미리 보낸 답이 있으면 다시 묻지 않는다', async () => {
    state.history = paged;
    const prefetch = {
      pnu: PNU,
      results: new Map([['get_store_history', Promise.resolve(paged({}))]]),
    };
    const { container } = render(<HistorySection pnu={PNU} prefetch={prefetch} />);
    await waitFor(() => expect(container.querySelector('section.card.hist')).not.toBeNull());
    expect(historyCalls()).toEqual([]);
  });
});

describe('HistorySection — 더 보기(서버 넘기기)', () => {
  it('★ 남은 3곳 → 누르면 p_offset 20 으로 묻고 23줄 · 다 받으면 단추 없음', async () => {
    state.history = paged;
    const { container } = render(<HistorySection pnu={PNU} />);
    await waitFor(() => expect(container.querySelector('.hist__more')).not.toBeNull());
    expect(container.querySelector('.hist__more')?.textContent).toBe('더 보기 (남은 3곳)');
    fireEvent.click(container.querySelector('.hist__more')!);
    await waitFor(() => expect(container.querySelectorAll('.hist__row')).toHaveLength(23));
    expect(historyCalls()[1]).toEqual({
      fn: 'get_store_history',
      args: { p_pnu: PNU, p_limit: 20, p_offset: 20 },
    });
    expect(container.querySelector('.hist__more')).toBeNull();
    expect([...container.querySelectorAll('.hist__nm')].map((n) => n.textContent)).toEqual(ALL.map((r) => r.biz_name));
  });

  it('⛔ 그 사이 total 이 바뀐 답은 버리고 단추를 거둔다', async () => {
    state.history = (args) =>
      Number(args.p_offset ?? 0) > 0
        ? { data: ALL.slice(20).map((r) => ({ ...r, total_cnt: 24 })), error: null }
        : paged(args);
    const { container } = render(<HistorySection pnu={PNU} />);
    await waitFor(() => expect(container.querySelector('.hist__more')).not.toBeNull());
    fireEvent.click(container.querySelector('.hist__more')!);
    await waitFor(() => expect(container.querySelector('.hist__more')).toBeNull());
    expect(container.querySelectorAll('.hist__row')).toHaveLength(20);
  });

  it('⛔ 더 보기가 실패하면 단추만 거둔다(카드는 그대로)', async () => {
    state.history = (args) =>
      Number(args.p_offset ?? 0) > 0 ? { data: null, error: { message: 'boom' } } : paged(args);
    const { container } = render(<HistorySection pnu={PNU} />);
    await waitFor(() => expect(container.querySelector('.hist__more')).not.toBeNull());
    fireEvent.click(container.querySelector('.hist__more')!);
    await waitFor(() => expect(container.querySelector('.hist__more')).toBeNull());
    expect(container.querySelector('section.card.hist')).not.toBeNull();
    expect(container.querySelectorAll('.hist__row')).toHaveLength(20);
  });
});

describe('HistorySection — 필지 바뀜 · 어긋남 줄', () => {
  it('필지가 바뀌면 옛 답을 비운다(새 땅이 숨김이면 카드도 없다)', async () => {
    state.history = (args) => (args.p_pnu === PNU ? paged(args) : { data: null, error: { code: 'PGRST202' } });
    const { container, rerender } = render(<HistorySection pnu={PNU} />);
    await waitFor(() => expect(container.querySelector('section.card.hist')).not.toBeNull());
    rerender(<HistorySection pnu={OTHER} />);
    await settle();
    expect(container.querySelector('section.card')).toBeNull();
  });

  it('★ 이력 마지막 분기 ≠ 신선도 표 점포 줄 → 「이 이력은 ○까지입니다」 · 같으면 줄 없음', async () => {
    state.history = paged;
    state.fresh = {
      data: [{ src: '점포·업종 (상권정보)', basis_kind: '분기', basis: '202609', next_expected: '2027-02-28', cadence: '분기마다' }],
      error: null,
    };
    const { container } = render(<HistorySection pnu={PNU} />);
    await waitFor(() => expect(container.querySelector('.hist__lag')).not.toBeNull());
    expect(container.querySelector('.hist__lag')?.textContent).toBe(
      '이 이력은 2026년 2분기까지입니다 (점포 자료는 2026년 3분기)',
    );
    expect(container.querySelector('.hist__lag b')?.textContent).toBe('2026년 2분기');
    cleanup();
    resetDataFreshnessCache();
    state.fresh = {
      data: [{ src: '점포·업종 (상권정보)', basis_kind: '분기', basis: '202606', next_expected: '2026-10-31', cadence: '분기마다' }],
      error: null,
    };
    const same = render(<HistorySection pnu={PNU} />);
    await waitFor(() => expect(same.container.querySelector('section.card.hist')).not.toBeNull());
    await settle();
    expect(same.container.querySelector('.hist__lag')).toBeNull();
  });
});

describe('HistorySection — 보완 1 F-2 줄 key', () => {
  it('보이는 칸이 전부 같은 줄 둘(같은 가게가 번호 둘)도 둘 다 그리고, 더 보기 뒤에도 그대로', async () => {
    const twin = row(0, { biz_name: '쌍둥이가게', first_ym: '201903', last_ym: '202312', seen_cnt: 20, is_current: false });
    const first = [...ALL.slice(0, 6), twin, twin, ...ALL.slice(8, 20)].map((r) => ({ ...r, total_cnt: 22 }));
    const second = ALL.slice(20, 22).map((r) => ({ ...r, total_cnt: 22 }));
    state.history = (args) => ({ data: Number(args.p_offset ?? 0) > 0 ? second : first, error: null });
    // React 는 겹친 key 를 콘솔 오류로만 알리고 일단 둘 다 그린다 — 그 오류가 0 이어야 한다(겹치면 다음 갱신 때 줄이 뒤섞인다).
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { container } = render(<HistorySection pnu={PNU} />);
    await waitFor(() => expect(container.querySelector('.hist__more')).not.toBeNull());
    const twins = () => [...container.querySelectorAll('.hist__nm')].filter((n) => n.textContent === '쌍둥이가게');
    expect(twins()).toHaveLength(2);
    fireEvent.click(container.querySelector('.hist__more')!);
    await waitFor(() => expect(container.querySelectorAll('.hist__row')).toHaveLength(22));
    expect(twins()).toHaveLength(2);
    const keyWarnings = err.mock.calls.filter((c) => c.some((a) => String(a).includes('same key')));
    expect(keyWarnings).toEqual([]);
  });
});
