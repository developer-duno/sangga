import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { resetScorecardCache } from '../lib/scorecard';
import type { PriceGateRow, Scorecard, ScorecardOpsMode } from '../types';

/**
 * "참고 시세는 얼마나 맞나" 카드 — 입구에 서는 두 번째 카드.
 *
 * 여기서 특히 지키는 것
 * ---------------------
 *  ① **못 읽었으면 아무 말도 안 한다** — 마이그레이션 적용 전 라이브가 그 상태다.
 *     "성적 없음"이라 적으면 모르는 것을 없는 것이라 말하게 된다.
 *  ② **파일만 못 읽었으면 판정은 그대로 보여준다** — 둘 중 하나가 없다고 나머지까지
 *     버리지 않는다. 대신 없는 것을 없다고 밝힌다.
 *  ③ **떨어진 구에는 이유를 적는다** — "자료가 없어서"와 "구 평균만 못해서"는 다른 말이고,
 *     그 구별이 이 카드의 존재 이유다(결정 0013 §2 조건 ②).
 *  ④ **금칙어 0** — 절대 규칙 2. 이 카드는 추정의 성적을 말하는 자리라 특히 위험하다.
 */

const responses = { gate: { data: null as unknown, error: null as unknown } };
const rpcCalls: Array<{ fn: string; args: unknown }> = [];

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string, args?: unknown) => {
      rpcCalls.push({ fn, args });
      return Promise.resolve(responses.gate);
    },
  },
}));

const { ScorecardSection } = await import('./ScorecardSection');

function ops(over: Partial<ScorecardOpsMode> = {}): ScorecardOpsMode {
  return {
    kind: '채택단계',
    axis_value: 'L2',
    axis_name: 'L2',
    n_verified: 100,
    n_estimated: 100,
    coverage: 1,
    mdape: 0.2,
    mape: 0.3,
    hit20: 0.5,
    ...over,
  };
}

function card(over: Partial<Scorecard> = {}): Scorecard {
  return {
    version: 'v1',
    generated_at: '2026-08-15T23:44:00+09:00',
    sources: { '통과구.csv': 'a'.repeat(64) },
    stages: [],
    ops_modes: [
      ops({ kind: '전체', axis_value: '전체', axis_name: '전체', n_verified: 1000, coverage: 0.9 }),
      ops({ axis_value: 'L2', axis_name: 'L2', n_verified: 300, mdape: 0.13 }),
      ops({ axis_value: 'L6', axis_name: 'L6', n_verified: 600, mdape: 0.4 }),
      ops({ axis_value: 'no_estimate', axis_name: 'no_estimate', n_verified: 100, mdape: null }),
    ],
    ...over,
  };
}

/** 통과한 구 하나 + 오차는 기준선 안인데 구 평균에 진 구 하나(금천구 사례). */
function gateRows(): PriceGateRow[] {
  return [
    {
      sigungu_code: '11545',
      sigungu_nm: '금천구',
      n_paired: 99,
      ladder_mdape: 0.26,
      base_mdape: 0.176,
      gate_pass: false,
      loaded_at: '2026-08-16T10:00:00+09:00',
    },
    {
      sigungu_code: '11680',
      sigungu_nm: '강남구',
      n_paired: 262,
      ladder_mdape: 0.283,
      base_mdape: 0.492,
      gate_pass: true,
      loaded_at: '2026-08-16T10:00:00+09:00',
    },
  ];
}

function stubFetchOk(doc: Scorecard = card()) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(doc) })),
  );
}

function stubFetchFails() {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) })),
  );
}

beforeEach(() => {
  rpcCalls.length = 0;
  resetScorecardCache();
  responses.gate = { data: gateRows(), error: null };
  stubFetchOk();
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  resetScorecardCache();
});

describe('ScorecardSection — 성적이 있을 때', () => {
  it('접힌 카드로 서고, 요약 한 줄에 이 구의 판정과 성적표 도장이 적힌다', async () => {
    const { container } = render(<ScorecardSection sigungu="11680" />);

    expect(await screen.findByText('참고 시세는 얼마나 맞나')).toBeTruthy();
    const summary = container.querySelector('.card__summary')?.textContent ?? '';
    expect(summary).toContain('참고 시세 제공');
    expect(summary).toContain('262건');
    expect(summary).toContain('성적표 v1');
    expect(summary).toContain('2026년 8월 15일 생성');
    // ⛔ 입구를 가로막지 않는다 — 접힌 채로 시작한다.
    expect(
      screen.getByRole('button', { name: /참고 시세는 얼마나 맞나/ }).getAttribute('aria-expanded'),
    ).toBe('false');
    expect(container.querySelector('.card__body')?.hasAttribute('hidden')).toBe(true);
  });

  it('서버에는 구를 안 넘긴다 — 함수가 열린 구 전부를 준다', async () => {
    render(<ScorecardSection sigungu="11680" />);
    await screen.findByText('참고 시세는 얼마나 맞나');
    expect(rpcCalls).toHaveLength(1);
    expect(rpcCalls[0].fn).toBe('list_price_gate');
    expect(rpcCalls[0].args).toBeUndefined();
  });

  it('펼치면 이 구의 성적 넉 줄이 나온다', async () => {
    const { container } = render(<ScorecardSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /참고 시세는 얼마나 맞나/ }));

    const mine = container.querySelector('.score__mine')?.textContent ?? '';
    expect(mine).toContain('262건');
    expect(mine).toContain('28.3%'); // 사다리
    expect(mine).toContain('49.2%'); // 구 평균
    expect(mine).toContain('제공');
  });

  it('★ 체감 단계 분포가 가장 흔한 자리부터 나온다 (로드맵 Wave 4)', async () => {
    const { container } = render(<ScorecardSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /참고 시세는 얼마나 맞나/ }));

    const rows = container.querySelectorAll('.score__stages .score__rows li');
    expect(rows).toHaveLength(3);
    expect(rows[0].textContent).toContain('L6');
    expect(rows[0].textContent).toContain('60.0%');
    // ⛔ 값을 못 낸 자리에 '0%'를 적지 않는다.
    const none = rows[2].textContent ?? '';
    expect(none).toContain('no_estimate');
    expect(none).not.toContain('오차 중앙값');
  });

  it('커버리지가 유리한 숫자라는 공지가 함께 붙는다 (결정 0013 §3)', async () => {
    const { container } = render(<ScorecardSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /참고 시세는 얼마나 맞나/ }));
    expect(container.querySelector('.score__honest')?.textContent).toContain('유리');
  });

  it('채점한 구 전체가 이름·코드와 함께 나온다 (같은 이름 구가 갈리게)', async () => {
    const { container } = render(<ScorecardSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /참고 시세는 얼마나 맞나/ }));

    const rows = container.querySelectorAll('.score__all .score__rows li');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('금천구');
    expect(rows[0].textContent).toContain('11545');
    expect(rows[1].className).toContain('is-pass');
  });

  it('방법 요약과 배지·도장이 붙는다', async () => {
    const { container } = render(<ScorecardSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /참고 시세는 얼마나 맞나/ }));

    expect(container.querySelector('.grade__badge')?.textContent).toBe('검증 성적 · 원본 성적표 v1');
    expect(container.querySelector('.score__how')?.textContent).toContain('2026년 8월 15일');
    expect(container.querySelectorAll('.score__how-list li')).toHaveLength(4);
  });
});

describe('ScorecardSection — 떨어진 구', () => {
  it('★ 오차는 기준선 안인데 구 평균에 진 구는 그 사실을 적는다', async () => {
    const { container } = render(<ScorecardSection sigungu="11545" />);
    const summary = (await screen.findByText('참고 시세는 얼마나 맞나')) && container;

    expect(summary.querySelector('.card__summary')?.textContent).toContain('못 이깁니다');
    fireEvent.click(screen.getByRole('button', { name: /참고 시세는 얼마나 맞나/ }));
    const why = container.querySelector('.score__why')?.textContent ?? '';
    expect(why).toContain('17.6%');
    // "자료가 없다"로 읽히면 안 된다 — 자료는 있고, 구 평균이 더 정확했을 뿐이다.
    expect(why).not.toContain('자료가 없');
  });

  it('목록에 없는 구는 "아직 채점하지 않았다"고 적는다', async () => {
    const { container } = render(<ScorecardSection sigungu="30110" />);
    await screen.findByText('참고 시세는 얼마나 맞나');
    expect(container.querySelector('.card__summary')?.textContent).toContain('아직');

    fireEvent.click(screen.getByRole('button', { name: /참고 시세는 얼마나 맞나/ }));
    expect(container.querySelector('.score__mine')?.textContent).toContain('찾지 못했습니다');
  });
});

describe('ScorecardSection — 못 읽었을 때', () => {
  it('★ 성적표 파일만 못 읽으면 판정은 그대로 보여주고, 없는 것을 없다고 밝힌다', async () => {
    stubFetchFails();
    const { container } = render(<ScorecardSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /참고 시세는 얼마나 맞나/ }));

    // 판정은 살아 있다.
    expect(container.querySelector('.score__mine')?.textContent).toContain('262건');
    // 방법·분포는 없다고 **말한다**(조용히 비우지 않는다).
    expect(container.querySelector('.score__how')?.textContent).toContain('읽을 수 없습니다');
    expect(container.querySelector('.score__stages')).toBeNull();
    // 도장이 없으면 없다고 적는다 — 날짜를 지어내지 않는다.
    expect(container.querySelector('.card__summary')?.textContent).not.toContain('성적표 v');
  });

  it('★ 판정을 못 읽으면 카드를 통째로 생략한다 (둘 다 실패도 같다)', async () => {
    responses.gate = { data: null, error: { code: 'PGRST202' } };
    stubFetchFails();
    const { container } = render(<ScorecardSection sigungu="11680" />);

    await waitFor(() => expect(console.warn).toHaveBeenCalled());
    expect(container.querySelector('section.score')).toBeNull();
    // "성적 없음" 같은 말도 남기지 않는다 — 모르는 것을 없는 것이라 말하지 않는다.
    expect(container.textContent).toBe('');
  });

  it('★ 판정만 못 읽으면 — 성적표 파일은 멀쩡해도 — 카드를 안 만든다', async () => {
    /*
      ⛔ 두 갈래는 **대칭이 아니다.** 파일만 없으면 판정을 보여줄 수 있지만(위 시험),
         판정이 없으면 방법·분포만 남는데 그것은 "이 구는 받나 못 받나"에 아무 답도 못 한다 —
         요약 한 줄이 바로 그 답이라, 그 줄을 못 만드는 카드는 세우지 않는다.
      ⚠️ 앞 시험은 둘 다 실패시켜 이 경로를 함께 지나가므로, 이 시험이 없으면 "판정이
         없어서"인지 "둘 다 없어서"인지 구별되지 않는다.
    */
    responses.gate = { data: null, error: { code: 'PGRST202' } };
    stubFetchOk(); // 파일은 정상으로 온다
    const { container } = render(<ScorecardSection sigungu="11680" />);

    await waitFor(() => expect(console.warn).toHaveBeenCalled());
    expect(container.querySelector('section.score')).toBeNull();
    // 방법·단계 분포만 따로 흘려보내지도 않는다 — 판정 없는 성적은 이 카드의 답이 아니다.
    expect(container.textContent).toBe('');
  });

  it('게이트 표가 비어 있으면(아직 안 적재) 카드를 안 만든다', async () => {
    responses.gate = { data: [], error: null };
    const { container } = render(<ScorecardSection sigungu="11680" />);
    await waitFor(() => expect(container.textContent).toBe(''));
  });

  it('모양이 다른 답은 렌더로 흘려보내지 않는다', async () => {
    responses.gate = { data: [{ sigungu_code: '11680' }], error: null };
    const { container } = render(<ScorecardSection sigungu="11680" />);
    await waitFor(() => expect(console.warn).toHaveBeenCalled());
    expect(container.querySelector('section.score')).toBeNull();
  });
});

describe('ScorecardSection — 절대 규칙 2', () => {
  it('금칙어가 한 글자도 없다', async () => {
    const { container } = render(<ScorecardSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /참고 시세는 얼마나 맞나/ }));

    const text = container.textContent ?? '';
    for (const banned of ['적정가격', '적정가', '평가액', '감정가', '가치평가']) {
      expect(text.includes(banned), banned).toBe(false);
    }
  });
});
