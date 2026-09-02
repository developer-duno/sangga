import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import type { LhNotice } from '../types';

/**
 * "LH 상가 분양·입점 공고" 카드 — 입구에 서는 유일한 카드.
 *
 * 여기서 특히 지키는 것
 * ---------------------
 *  ① **못 읽었으면 아무 말도 안 한다** — 마이그레이션 적용 전 라이브가 그 상태다.
 *     "공고 없음"이라 적으면 모르는 것을 없는 것이라 말하게 된다.
 *  ② **빈손이어도 카드를 안 만든다** — 0건 카드는 입구를 가로막기만 한다.
 *  ③ **서버에 묻는 값이 시도 두 자리다** — 목은 인자 값을 안 보므로 여기서 눈으로 보지
 *     않으면 다섯 자리를 보내도 시험이 전부 초록이다. 지금은 서버도 앞 두 자리만 보게
 *     막아 두었지만, 그 방어선에 기대면 그것이 사라지는 날 화면만 조용히 빈손이 된다.
 *  ④ **값·신청 방법을 옮겨 적지 않는다** — 우리 몫은 "무엇이 열려 있나"까지다.
 */

const responses = { notices: { data: null as unknown, error: null as unknown } };

/** 마지막 rpc 호출들. 함수 이름과 **인자 이름·값**을 여기서 확인한다. */
const rpcCalls: Array<{ fn: string; args: unknown }> = [];

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string, args?: unknown) => {
      rpcCalls.push({ fn, args });
      return Promise.resolve(responses.notices);
    },
  },
}));

const { LhNoticeSection } = await import('./LhNoticeSection');

function notice(over: Partial<LhNotice> = {}): LhNotice {
  return {
    pan_id: '2026-0001',
    pan_nm: '서울강남 A1블록 단지내상가 입찰공고',
    kind_nm: '분양 입찰',
    pan_ss: '공고중',
    notice_date: '2026-08-20',
    // 마감일은 **올해 기준 상대값**으로 짓는다 — 올해 마감이면 연도를 빼고 적으므로,
    // 연도를 박아 두면 해가 바뀌는 순간 '~9월 17일' 단언이 저절로 빨개진다.
    close_date: `${new Date().getFullYear()}-09-17`,
    dtl_url: 'https://apply.lh.or.kr/notice/2026-0001',
    // 시각은 **현지 시각으로 지어** 쓴다 — 돌리는 시간대·날짜에 따라 답이 달라지지
    // 않게(글로벌 규칙: 시험에 시각을 박아 넣지 않는다).
    collected_at: new Date(2026, 7, 27, 9, 0).toISOString(),
    ...over,
  };
}

beforeEach(() => {
  rpcCalls.length = 0;
  responses.notices = { data: [notice()], error: null };
});

afterEach(() => cleanup());

describe('LhNoticeSection — 공고가 있을 때', () => {
  it('접힌 카드로 서고, 요약 한 줄에 건수와 수집일이 적힌다', async () => {
    responses.notices = {
      data: [notice(), notice({ pan_id: '2026-0002', pan_nm: '대전유성 임대상가 공고' })],
      error: null,
    };
    const { container } = render(<LhNoticeSection sigungu="11680" />);

    // 제목은 배치표(ENTRY_SECTION_PLAN)에서 온다 — 컴포넌트가 따로 적지 않는다.
    expect(await screen.findByText('LH 상가 분양·입점 공고')).toBeTruthy();
    expect(container.querySelector('.card__summary')?.textContent).toBe(
      '2건 · 8월 27일 수집 기준',
    );
    // ⛔ 입구를 가로막지 않는다 — 접힌 채로 시작한다.
    expect(screen.getByRole('button').getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelector('.card__body')?.hasAttribute('hidden')).toBe(true);
  });

  it('펼치면 줄마다 종류·공고명·상태·마감일과 LH 링크가 나온다', async () => {
    render(<LhNoticeSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /LH 상가 분양·입점 공고/ }));

    expect(screen.getByText('분양 입찰')).toBeTruthy();
    expect(screen.getByText('서울강남 A1블록 단지내상가 입찰공고')).toBeTruthy();
    expect(screen.getByText('공고중')).toBeTruthy();
    expect(screen.getByText('~9월 17일')).toBeTruthy();

    const link = screen.getByRole('link', { name: 'LH에서 보기' }) as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('https://apply.lh.or.kr/notice/2026-0001');
    // 새 창으로 열되, 열린 쪽이 우리 창을 되돌려 다른 주소로 보내지 못하게 한다.
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('마감일이 없는 공고는 "마감일 미정"이라 적는다', async () => {
    responses.notices = { data: [notice({ close_date: null })], error: null };
    render(<LhNoticeSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /LH 상가 분양·입점 공고/ }));

    expect(screen.getByText('마감일 미정')).toBeTruthy();
  });

  it('★ 마감이 올해가 아니면 연도를 함께 적는다 (내년 마감이 지난 날짜처럼 보이지 않게)', async () => {
    // 배선 가드 — 마감일 문장을 closeText 를 안 거치고 컴포넌트가 직접 짓게 바뀌면
    // 연도가 조용히 사라진다(2026-08-30 라이브: 2027-06-30 이 "~6월 30일"로 보였다).
    const nextYear = new Date().getFullYear() + 1;
    responses.notices = { data: [notice({ close_date: `${nextYear}-06-30` })], error: null };
    render(<LhNoticeSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /LH 상가 분양·입점 공고/ }));

    expect(screen.getByText(`~${nextYear}년 6월 30일`)).toBeTruthy();
  });

  it('★ 서버에는 시도 두 자리로 묻는다 (구 코드 다섯 자리를 그대로 보내지 않는다)', async () => {
    render(<LhNoticeSection sigungu="30170" />);
    await waitFor(() => expect(rpcCalls.length).toBeGreaterThan(0));

    expect(rpcCalls[0].fn).toBe('list_lh_notices');
    // 인자 **이름**도 함께 본다 — `p_sido` 가 아니면 라이브에서만 PGRST202 가 난다
    // (이름이 틀린 것은 서버가 대신 봐줄 수 없는 종류의 어긋남이다).
    expect(rpcCalls[0].args).toEqual({ p_sido: '30' });
  });

  it('★ 값·신청 방법을 옮겨 적지 않고 링크로 넘긴다', async () => {
    const { container } = render(<LhNoticeSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /LH 상가 분양·입점 공고/ }));

    const text = container.textContent ?? '';
    expect(text).toContain('신청 방법과 가격·자격은 공고문에 있습니다');
    // 공공누리 출처표시 — 어디까지가 우리 말인지 가른다.
    expect(text).toContain('출처: 한국토지주택공사(LH)');
    // 절대 규칙 2 — 금칙어는 어디에도 없다.
    for (const banned of ['적정가격', '적정가', '평가액', '감정가', '가치평가']) {
      expect(text.includes(banned)).toBe(false);
    }
  });

  it('★ pan_ss·dtl_url 이 null 인 행이 섞여도 목록이 살아남고 그 행이 그려진다', async () => {
    // DB nullable(원본 API 결측)이라 실제로 이런 행이 온다 — 예전엔 이 한 행 때문에
    // isLhNoticeList 가 목록 전체를 거절해 카드가 통째로 사라졌다.
    responses.notices = {
      data: [notice({ pan_id: '2026-0002', pan_nm: '대전유성 임대상가 공고', pan_ss: null, dtl_url: null })],
      error: null,
    };
    render(<LhNoticeSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /LH 상가 분양·입점 공고/ }));

    expect(screen.getByText('대전유성 임대상가 공고')).toBeTruthy();
    // pan_ss 가 없으므로 그 칸은 안 그려진다(빈 문자열을 지어내지 않는다).
    expect(document.querySelector('.lh__ss')).toBeNull();
    // dtl_url 이 없으므로 링크도 안 만든다(주소 모양이 아닌 값과 같은 처리).
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('주소 모양이 아니면 링크를 아예 안 만든다 (줄은 그대로 남는다)', async () => {
    responses.notices = { data: [notice({ dtl_url: 'javascript:alert(1)' })], error: null };
    render(<LhNoticeSection sigungu="11680" />);
    fireEvent.click(await screen.findByRole('button', { name: /LH 상가 분양·입점 공고/ }));

    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('서울강남 A1블록 단지내상가 입찰공고')).toBeTruthy();
  });

  it('같은 시도 안에서 구만 바꾸면 다시 묻지 않는다 (답이 같다)', async () => {
    const { rerender } = render(<LhNoticeSection sigungu="11680" />);
    await waitFor(() => expect(rpcCalls).toHaveLength(1));

    rerender(<LhNoticeSection sigungu="11440" />);
    await waitFor(() => expect(screen.getByText('LH 상가 분양·입점 공고')).toBeTruthy());
    expect(rpcCalls).toHaveLength(1);

    // 시도가 바뀌면 그때는 다시 묻는다.
    rerender(<LhNoticeSection sigungu="30170" />);
    await waitFor(() => expect(rpcCalls).toHaveLength(2));
    expect(rpcCalls[1].args).toEqual({ p_sido: '30' });
  });
});

describe('LhNoticeSection — 빈손이거나 못 읽었을 때', () => {
  it('★ 서버에 함수가 아직 없으면 카드를 통째로 생략한다 (조용히)', async () => {
    responses.notices = {
      data: null,
      error: { code: 'PGRST202', message: 'function does not exist' },
    };
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { container } = render(<LhNoticeSection sigungu="11680" />);

    // ⚠️ "무엇이든 한 번 불렸다"로 보면 안 된다 — 렌더가 터질 때 React 도 콘솔에 적으므로,
    //    검사를 없애 카드가 터지는 상태에서도 그 단언은 통과한다(2026-08-28 돌연변이 실측).
    //    우리가 남긴 말인지까지 본다.
    await waitFor(() =>
      expect(warn).toHaveBeenCalledWith(
        expect.stringContaining('LH 공고 조회 실패'),
        expect.anything(),
      ),
    );
    expect(container.querySelector('.lh')).toBeNull();
    // "공고 없음" 같은 말을 남기지 않는다 — 모르는 것을 없는 것이라 말하지 않는다.
    expect(container.textContent).toBe('');
    warn.mockRestore();
  });

  it('★ 뜻밖의 모양이 와도 터지지 않고 생략한다', async () => {
    responses.notices = { data: { message: '어라' }, error: null };
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { container } = render(<LhNoticeSection sigungu="11680" />);

    // ⚠️ "무엇이든 한 번 불렸다"로 보면 안 된다 — 렌더가 터질 때 React 도 콘솔에 적으므로,
    //    검사를 없애 카드가 터지는 상태에서도 그 단언은 통과한다(2026-08-28 돌연변이 실측).
    //    우리가 남긴 말인지까지 본다.
    await waitFor(() =>
      expect(warn).toHaveBeenCalledWith(
        expect.stringContaining('LH 공고 조회 실패'),
        expect.anything(),
      ),
    );
    expect(container.querySelector('.lh')).toBeNull();
    warn.mockRestore();
  });

  it('열린 공고가 0건이면 빈 카드를 만들지 않는다', async () => {
    responses.notices = { data: [], error: null };
    const { container } = render(<LhNoticeSection sigungu="11680" />);

    await waitFor(() => expect(rpcCalls).toHaveLength(1));
    expect(container.querySelector('.lh')).toBeNull();
  });

  it('구 코드가 다섯 자리 숫자가 아니면 서버에 묻지도 않는다', async () => {
    const { container } = render(<LhNoticeSection sigungu="11" />);

    await waitFor(() => expect(container.querySelector('.lh')).toBeNull());
    expect(rpcCalls).toHaveLength(0);
  });
});
