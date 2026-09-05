import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';

import type { DataFreshnessRow } from '../types';

/**
 * 화면 아래 "이 자료는 언제 것인가" 표.
 *
 * 여기서 특히 지키는 것
 * ---------------------
 *  ① **자료 열 갈래가 다 뜬다** — 한 줄이 빠지면 보는 사람은 "그런 자료는 안 쓰나 보다"로
 *     읽는다. 에러가 아니라 조용한 누락이라 아무도 모른다.
 *  ② **못 읽었으면 아무 말도 안 한다** — 마이그레이션 적용 전 라이브가 그 상태다.
 *     "자료 없음"이라 적으면 모르는 것을 없는 것이라 말하게 된다.
 *  ③ **뜻밖의 답이 렌더로 새어 들어가지 않는다** — 이 표는 화면 맨 아래에 있어 터지면
 *     면책 안내와 의견함까지 함께 사라진다.
 *  ④ **화면이 날짜·주기를 지어내지 않는다** — 적히는 글자가 전부 서버 값에서 나온다.
 */

const responses = { fresh: { data: null as unknown, error: null as unknown } };

/** 마지막 rpc 호출들. 함수 이름과 **인자**를 여기서 확인한다. */
const rpcCalls: Array<{ fn: string; args: unknown }> = [];

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string, args?: unknown) => {
      rpcCalls.push({ fn, args });
      return Promise.resolve(responses.fresh);
    },
  },
}));

const { DataFreshness } = await import('./DataFreshness');

function row(over: Partial<DataFreshnessRow> = {}): DataFreshnessRow {
  return {
    src: '점포·업종 (상권정보)',
    basis_kind: '분기',
    basis: '202606',
    next_expected: '2026-10-31',
    cadence: '분기마다 (다음 분기 자료가 공개되면 사람이 적재)',
    ...over,
  };
}

/** 라이브가 주는 것과 같은 열 줄. */
function tenRows(): DataFreshnessRow[] {
  return [
    row(),
    row({
      src: '실거래 (매매)',
      basis_kind: '계약월',
      basis: '202608',
      next_expected: null,
      cadence: '수시 (서울·대전 전부 활성화 뒤 확대)',
    }),
    row({
      src: '건축물대장',
      basis_kind: '적재일',
      basis: '2026-06-30',
      next_expected: null,
      cadence: '월간 파일 (사람이 적재)',
    }),
    row({
      src: '상권 경계',
      basis_kind: '계산일',
      basis: '2026-08-15',
      next_expected: null,
      cadence: '비정기 (원천이 바뀌면)',
    }),
    row({
      src: 'LH 상가 공고',
      basis_kind: '수집일',
      basis: '2026-08-28',
      next_expected: null,
      cadence: '주 1회 감시 · 적재는 사람',
    }),
    row({
      src: '건축 인허가',
      basis_kind: '기준월',
      basis: '202607',
      next_expected: '2026-08-31',
      cadence: '월 1회',
    }),
    row({
      src: '국세청 기준시가',
      basis_kind: '고시일',
      basis: '2026-01-01',
      next_expected: '2027-03-31',
      cadence: '연 1회 (매년 3월 고시)',
    }),
    row({
      src: '상권 임대 동향 (부동산원)',
      basis_kind: '분기',
      basis: '2026Q2',
      next_expected: '2026-10-31',
      cadence: '분기마다',
    }),
    row({
      src: '참고 시세 성적표',
      basis_kind: '적재일',
      basis: '2026-08-16',
      next_expected: null,
      cadence: '재생성 때 (결재 사항)',
    }),
    row({
      src: '필지 (토지 특성)',
      basis_kind: '갱신일',
      basis: '2026-08-29',
      next_expected: null,
      cadence: '연 1회 (브이월드)',
    }),
  ];
}

beforeEach(() => {
  rpcCalls.length = 0;
  responses.fresh = { data: tenRows(), error: null };
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('DataFreshness — 서버가 답할 때', () => {
  it('자료 열 갈래가 한 줄씩 뜬다', async () => {
    const { container } = render(<DataFreshness />);

    expect(await screen.findByText('이 자료는 언제 것인가')).toBeTruthy();
    // 머리글 줄 하나 + 자료 열 줄.
    await waitFor(() => {
      expect(container.querySelectorAll('.fresh__table tbody tr').length).toBe(10);
    });
    for (const src of tenRows().map((r) => r.src)) {
      expect(screen.getByText(src)).toBeTruthy();
    }
  });

  it('인자 없이 그 함수 하나만 부른다', async () => {
    render(<DataFreshness />);
    await screen.findByText('이 자료는 언제 것인가');

    expect(rpcCalls).toHaveLength(1);
    expect(rpcCalls[0].fn).toBe('get_data_freshness');
    expect(rpcCalls[0].args).toBeUndefined();
  });

  it('기준값을 종류에 맞게 읽는다 — 같은 여섯 자리가 분기도 되고 달도 된다', async () => {
    render(<DataFreshness />);

    // ⓘ '2026년 2분기'가 **둘**인 것이 정상이다 — 상권정보('202606')와 부동산원('2026Q2')이
    //   서로 다른 표기로 같은 분기를 말한다. 화면이 그 둘을 같은 말로 바꿔 적는 것이 요점이다.
    expect(await screen.findAllByText('2026년 2분기')).toHaveLength(2);
    expect(screen.getByText('2026년 8월')).toBeTruthy(); // 202608 · 계약월
    expect(screen.getByText('2026년 7월')).toBeTruthy(); // 202607 · 기준월
    expect(screen.getByText('2026년 8월 28일')).toBeTruthy(); // 수집일
  });

  it('다음 갱신 예정이 없는 자료는 그렇게 적는다 — 없는 주기를 지어내지 않는다', async () => {
    render(<DataFreshness />);

    // 분기 자료 둘은 같은 날 함께 갱신된다(같은 규칙을 쓰므로) — 그래서 두 줄이다.
    expect(await screen.findAllByText('2026년 10월 31일 무렵')).toHaveLength(2);
    expect(screen.getByText('2027년 3월 31일 무렵')).toBeTruthy();
    // 열 줄 중 여섯 줄이 주기가 없다(실거래·건축물대장·상권 경계·LH·성적표·필지).
    expect(screen.getAllByText('정해진 주기 없음')).toHaveLength(6);
  });

  it('자료가 아직 한 행도 없는 갈래는 줄을 빼지 않고 "자료 없음"이라 적는다', async () => {
    responses.fresh = {
      data: [row({ src: 'LH 상가 공고', basis: null, next_expected: null })],
      error: null,
    };
    render(<DataFreshness />);

    expect(await screen.findByText('LH 상가 공고')).toBeTruthy();
    expect(screen.getByText('자료 없음')).toBeTruthy();
  });

  it('⛔ 화면이 날짜·주기를 지어내지 않는다 — 적힌 글자가 전부 서버 값에서 나온다', async () => {
    responses.fresh = {
      data: [
        row({
          src: '낯선 자료',
          basis_kind: '언젠가',
          basis: '알 수 없음',
          next_expected: null,
          cadence: '주기 미정',
        }),
      ],
      error: null,
    };
    const { container } = render(<DataFreshness />);

    expect(await screen.findByText('낯선 자료')).toBeTruthy();
    // 모양을 못 읽으면 원본 그대로 — 억지로 해석해 없는 날짜를 만들지 않는다.
    expect(screen.getByText('알 수 없음')).toBeTruthy();
    expect(screen.getByText('주기 미정')).toBeTruthy();
    expect(container.querySelectorAll('.fresh__table tbody tr').length).toBe(1);
  });
});

describe('DataFreshness — 서버가 못 답할 때', () => {
  it('⛔ 함수가 아직 없으면(PGRST202) 표를 통째로 생략한다', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    responses.fresh = {
      data: null,
      error: { code: 'PGRST202', message: 'function does not exist' },
    };
    const { container } = render(<DataFreshness />);

    await waitFor(() => expect(warn).toHaveBeenCalled());
    expect(container.querySelector('.fresh')).toBeNull();
    expect(screen.queryByText('이 자료는 언제 것인가')).toBeNull();
  });

  it('⛔ 모양이 아닌 답도 렌더로 안 들여보낸다 — 여기서 터지면 아래 안내까지 사라진다', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    responses.fresh = { data: { code: 'PGRST202' }, error: null };
    const { container } = render(<DataFreshness />);

    await waitFor(() => expect(warn).toHaveBeenCalled());
    expect(container.querySelector('.fresh')).toBeNull();
  });

  it('빈 배열이면 머리글만 있는 표를 만들지 않는다', async () => {
    responses.fresh = { data: [], error: null };
    const { container } = render(<DataFreshness />);

    await waitFor(() => expect(rpcCalls).toHaveLength(1));
    expect(container.querySelector('.fresh')).toBeNull();
  });
});
