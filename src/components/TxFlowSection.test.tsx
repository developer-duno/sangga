import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import type { SigunguTxYearly } from '../types';

/**
 * 『동네 매매 단가 흐름』 카드 — 입구에 서는 세 번째 카드(결정 0027).
 *
 * 여기서 특히 지키는 것
 * ---------------------
 *  ① **못 읽었으면 아무 말도 안 한다** — 마이그레이션 적용 전 라이브가 그 상태다.
 *     "자료 없음"이라 적으면 모르는 것을 없는 것이라 말하게 된다.
 *  ② **해의 일부는 그렇다고 적는다** — 첫 해·올해는 몇 달치뿐이라, 그냥 그리면 다른 해와
 *     나란히 서면서 "그 해에는 이만큼 팔렸다"로 읽힌다.
 *  ③ **표본이 모자란 해는 값도 막대도 안 낸다**(절대 규칙 3).
 *  ④ **인자 이름을 본다** — 목(mock)은 인자 이름을 안 보므로, 이 시험이 없으면 딴 이름으로
 *     불러도 전부 초록인 채 라이브에서만 PGRST202 가 난다.
 */

const responses = { yearly: { data: null as unknown, error: null as unknown } };
const rpcCalls: Array<{ fn: string; args: unknown }> = [];

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string, args?: unknown) => {
      rpcCalls.push({ fn, args });
      return Promise.resolve(responses.yearly);
    },
  },
}));

const { TxFlowSection } = await import('./TxFlowSection');

function yearlyRow(over: Partial<SigunguTxYearly> = {}): SigunguTxYearly {
  return {
    yr: '2015',
    n: 1550,
    n_all: 1550,
    median_unit_price: 21_171_384,
    p25_unit_price: 12_000_000,
    p75_unit_price: 33_000_000,
    median_area_m2: 18.3,
    floor_missing: 155,
    ym_cnt: 12,
    first_ym: '201501',
    last_ym: '201512',
    sigungu_nm: '강남구',
    ...over,
  };
}

/** 첫 해(몇 달치) · 온전한 해 · 올해(표본 부족) 셋 — 화면이 갈라 대해야 하는 세 상태다. */
function yearlyRows(): SigunguTxYearly[] {
  return [
    yearlyRow({
      yr: '2006',
      n: 447,
      n_all: 447,
      median_unit_price: 4_902_441,
      p25_unit_price: 3_100_000,
      p75_unit_price: 7_400_000,
      median_area_m2: 46.4,
      floor_missing: 92,
      ym_cnt: 4,
      first_ym: '200609',
      last_ym: '200612',
    }),
    yearlyRow(),
    yearlyRow({
      yr: '2026',
      n: 3,
      n_all: 3,
      median_unit_price: 30_000_000,
      floor_missing: 1,
      ym_cnt: 8,
      first_ym: '202601',
      last_ym: '202608',
    }),
  ];
}

beforeEach(() => {
  rpcCalls.length = 0;
  responses.yearly = { data: yearlyRows(), error: null };
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('TxFlowSection — 자료가 있을 때', () => {
  it('접힌 카드로 서고, 요약 한 줄에 자료 범위와 건수가 적힌다', async () => {
    const { container } = render(<TxFlowSection sigungu="11680" />);

    expect(await screen.findByText('동네 매매 단가 흐름 (실거래)')).toBeTruthy();
    const summary = container.querySelector('.card__summary')?.textContent ?? '';
    // 범위·건수는 **서버가 준 값**이다 — 화면에 글자로 박은 것이 아니다.
    expect(summary).toContain('2006년 9월');
    expect(summary).toContain('2026년 8월');
    expect(summary).toContain('2,000건');
    // ⛔ 입구를 가로막지 않는다 — 접힌 채로 시작한다.
    expect(
      screen
        .getByRole('button', { name: /동네 매매 단가 흐름/ })
        .getAttribute('aria-expanded'),
    ).toBe('false');
    expect(container.querySelector('.card__body')?.hasAttribute('hidden')).toBe(true);
  });

  it('★ 서버를 부를 때 인자 이름이 `sigungu` 다', async () => {
    render(<TxFlowSection sigungu="11680" />);
    await screen.findByText('동네 매매 단가 흐름 (실거래)');
    expect(rpcCalls).toHaveLength(1);
    expect(rpcCalls[0].fn).toBe('get_sigungu_tx_yearly');
    expect(rpcCalls[0].args).toEqual({ sigungu: '11680' });
  });

  it('펼치면 해마다 한 줄씩 — 해의 일부와 표본 부족을 정직하게 적는다', async () => {
    const { container } = render(<TxFlowSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /동네 매매 단가 흐름/ }));

    const rows = container.querySelectorAll('.flow__rows li');
    expect(rows).toHaveLength(3);

    const first = rows[0].textContent ?? '';
    expect(first).toContain('2006');
    expect(first).toContain('9~12월분'); // 해의 일부만 있는 해
    expect(first).toContain('㎡당 490만');
    // 가운데 절반은 공용 밴드 표기(`formatManWonBand`)를 그대로 쓴다 — 이 카드만의 자를
    // 새로 만들면 같은 뜻의 폭이 화면마다 다른 모양으로 적힌다.
    expect(first).toContain('가운데 절반 310만~740만');
    expect(first).toContain('층 미상 21%');

    // ⛔ 표본이 모자란 해는 값을 안 적는다 — 3건으로 낸 가운데값은 숫자 모양만 통계다.
    const last = rows[2].textContent ?? '';
    expect(last).toContain('표본 부족');
    expect(last).not.toContain('㎡당');
  });

  it('★ 표본 부족은 무엇이 모자란지 밝힌다 — 오른쪽 건수 칸과 세는 대상이 다르다', async () => {
    // 오른쪽 칸은 그 해 거래 **전부**(40건)이고, 모자란지는 **단가가 있는 거래**(3건)로
    // 가른다. 밝히지 않으면 "표본 부족 · 40건"이 되어 40건을 놓고 숨기는 것처럼 읽힌다.
    responses.yearly = {
      data: [
        yearlyRow(),
        yearlyRow({ yr: '2026', n: 3, n_all: 40, floor_missing: 4, ym_cnt: 8, first_ym: '202601', last_ym: '202608' }),
      ],
      error: null,
    };
    const { container } = render(<TxFlowSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /동네 매매 단가 흐름/ }));

    const last = container.querySelectorAll('.flow__rows li')[1].textContent ?? '';
    expect(last).toContain('표본 부족');
    expect(last).toContain('3건'); // 단가가 있는 거래
    expect(last).toContain('40건'); // 그 해 거래 전부
    expect(last).not.toContain('㎡당');
  });

  it('★ 줄 꼬리에 그 해 거래 한 건의 크기가 함께 적힌다 (2026-09-09b)', async () => {
    // 어떤 해는 ㎡당 값이 앞뒤 해의 두세 배로 튀는데, 시세가 오른 것이 아니라 초소형
    // 구획이 무더기로 거래된 해여서 그렇다. 면적 중앙값을 나란히 적으면 기준선을 하나도
    // 안 긋고 그 사실이 보인다 — 옆에 이미 있는 '층 미상 %'와 같은 방식이다.
    const { container } = render(<TxFlowSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /동네 매매 단가 흐름/ }));

    const rows = container.querySelectorAll('.flow__rows li');
    expect(rows[0].textContent).toContain('한 건 면적 중앙값 46㎡');
    expect(rows[1].textContent).toContain('한 건 면적 중앙값 18㎡');
    // 무엇을 잰 값인지 각주가 밝힌다(절대 규칙 3 의 근거 병기와 같은 결).
    expect(container.querySelector('.flow__src')?.textContent).toContain('한 건 면적');
  });

  it('★ 서버가 그 칸을 안 주면 그 조각만 빠지고 줄은 그대로 선다', async () => {
    // 마이그레이션 적용 전 라이브가 그 상태다. 칸 하나 없다고 카드를 통째로 버리면,
    // 사실 한 칸을 더하려다 있던 카드를 없애는 셈이 된다.
    const { median_area_m2: _drop, ...noArea } = yearlyRow();
    responses.yearly = { data: [noArea, yearlyRow({ yr: '2016', median_area_m2: null })], error: null };

    const { container } = render(<TxFlowSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /동네 매매 단가 흐름/ }));

    const rows = container.querySelectorAll('.flow__rows li');
    expect(rows).toHaveLength(2);
    for (const row of rows) {
      const text = row.textContent ?? '';
      expect(text).not.toContain('한 건 면적');
      // 나머지는 그대로다 — 값·건수·층 미상.
      expect(text).toContain('㎡당 2,117만');
      expect(text).toContain('1,550건');
      expect(text).toContain('층 미상 10%');
    }
  });

  it('★ 표본이 모자란 해는 면적도 감춘다 — 단가와 같은 거래들을 잰 값이다', async () => {
    // 값을 감추면서 이것만 남기면, 감춘 근거를 곁눈으로 말해 주는 셈이 된다.
    const { container } = render(<TxFlowSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /동네 매매 단가 흐름/ }));

    const last = container.querySelectorAll('.flow__rows li')[2].textContent ?? '';
    expect(last).toContain('표본 부족');
    expect(last).not.toContain('한 건 면적');
  });

  it('배지와 각주가 함께 붙는다 (근거·표본 병기 — 절대 규칙 3)', async () => {
    const { container } = render(<TxFlowSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /동네 매매 단가 흐름/ }));

    expect(container.querySelector('.grade__badge')?.textContent).toBe('A등급 · 실거래');
    const src = container.querySelector('.flow__src')?.textContent ?? '';
    // 각주의 두 시점은 **상수에서 온 값**이다(화면에 박은 글자가 아니다).
    expect(src).toContain('2017');
    expect(src).toContain('2024년 1월');
    expect(src).toContain('집합');
  });

  it('★ 막대는 값을 적는 해끼리만 견준다 — 표본 부족 해는 막대도 0 이다', async () => {
    const { container } = render(<TxFlowSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /동네 매매 단가 흐름/ }));

    const fills = container.querySelectorAll<HTMLElement>('.flow__fill');
    expect(fills).toHaveLength(3);
    // 4,902,441 / 21,171,384 = 23%
    expect(fills[0].style.width).toBe('23%');
    expect(fills[1].style.width).toBe('100%');
    // 3,000만이 더 크지만 표본이 모자라 눈금에서 빠졌다 — 막대도 안 그린다.
    expect(fills[2].style.width).toBe('0%');
  });

  it('지역 이름은 서버가 준 값으로 적는다 (화면에 박지 않는다)', async () => {
    const { container } = render(<TxFlowSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /동네 매매 단가 흐름/ }));
    expect(container.querySelector('.flow__lead')?.textContent).toContain('강남구');
  });
});

describe('TxFlowSection — 못 읽었을 때', () => {
  it('★ 함수가 아직 없으면 카드를 통째로 생략한다', async () => {
    responses.yearly = { data: null, error: { code: 'PGRST202' } };
    const { container } = render(<TxFlowSection sigungu="11680" />);

    await waitFor(() => expect(console.warn).toHaveBeenCalled());
    expect(container.querySelector('section.flow')).toBeNull();
    // "자료 없음" 같은 말도 남기지 않는다 — 모르는 것을 없는 것이라 말하지 않는다.
    expect(container.textContent).toBe('');
  });

  it('모양이 다른 답은 렌더로 흘려보내지 않는다', async () => {
    responses.yearly = { data: [{ yr: 2015 }], error: null };
    const { container } = render(<TxFlowSection sigungu="11680" />);
    await waitFor(() => expect(console.warn).toHaveBeenCalled());
    expect(container.querySelector('section.flow')).toBeNull();
  });

  it('빈 배열이면(그 구 자료가 아직 없다) 카드를 안 만든다', async () => {
    responses.yearly = { data: [], error: null };
    const { container } = render(<TxFlowSection sigungu="11680" />);
    await waitFor(() => expect(container.textContent).toBe(''));
  });

  it('★ 구를 바꾸면 앞 구의 줄이 남지 않는다 — 새 답을 못 읽어도', async () => {
    const { container, rerender } = render(<TxFlowSection sigungu="11680" />);
    await screen.findByText('동네 매매 단가 흐름 (실거래)');
    expect(container.textContent).toContain('강남구');

    // 새 구는 못 읽는다(마이그레이션 전 라이브·일시 장애가 그 상태다).
    responses.yearly = { data: null, error: { code: 'PGRST202' } };
    rerender(<TxFlowSection sigungu="11650" />);

    // ⛔ 새 답을 기다리는 동안에도 앞 구의 숫자를 세워 두지 않는다. 안 비우면 여기서
    //    강남구 이름과 강남구 숫자가 **영영** 남아, 서초구를 고른 사람에게 거짓을 말한다.
    expect(container.querySelector('section.flow')).toBeNull();
    expect(container.textContent).toBe('');
    await waitFor(() => expect(console.warn).toHaveBeenCalled());
    expect(container.textContent).toBe('');
  });
});

describe('TxFlowSection — 절대 규칙 2', () => {
  it('금칙어가 한 글자도 없고, "시세"를 단독으로 쓰지 않는다', async () => {
    const { container } = render(<TxFlowSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /동네 매매 단가 흐름/ }));

    const text = container.textContent ?? '';
    for (const banned of ['적정가격', '적정가', '평가액', '감정가', '가치평가', '시세']) {
      expect(text.includes(banned), banned).toBe(false);
    }
  });
});
