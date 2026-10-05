import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';

/**
 * 의견함 테스트.
 *
 * 여기서 지키는 것은 **정직성**이다. 조용히 틀리기 쉬운 자리 셋:
 *  ① 못 보냈는데 "보냈습니다"라고 하지 않는가 — 그러면 보낸 사람은 답을 기다리고
 *     우리는 받은 줄 안다. 서버가 함수를 못 찾는 상태(마이그레이션 전)가 실제로 그렇다.
 *  ② 보던 건물·지역이 **자동으로** 함께 가는가 — 사람이 손으로 적게 하면 대부분 안 적고,
 *     그러면 "어디를 보다 무엇이 아쉬웠나"라는 이 의견함의 값어치가 통째로 사라진다.
 *  ③ 답장을 못 한다는 사실을 **미리** 말하는가 — 답을 기다리게 해 놓고 안 하는 것이
 *     가장 나쁘다(개인정보를 안 받기로 한 결정의 뒷면이다).
 *
 * 2026-10-06 — 종류 고르기(기본 선택 없음 · context.category 로 실린다)와 봇 숨김 칸.
 */

const calls: Array<{ kind: string; body: string; context: unknown }> = [];
let willSucceed = true;

// 종류 표(FEEDBACK_CATEGORIES)는 진짜를 쓴다 — 흉내 속에 글자를 다시 적으면 화면과 표가
// 어긋나도 여기는 초록이다. 진짜 모듈이 부르는 클라이언트만 막는다(환경변수 없이 읽히게).
vi.mock('../lib/supabase', () => ({ supabase: {} }));
vi.mock('../lib/feedback', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/feedback')>()),
  submitFeedback: (kind: string, body: string, context: unknown) => {
    calls.push({ kind, body, context });
    return Promise.resolve(willSucceed);
  },
}));

const { FeedbackBox } = await import('./FeedbackBox');

beforeEach(() => {
  calls.length = 0;
  willSucceed = true;
});

afterEach(cleanup);

/**
 * 접힌 상자를 펴고 종류를 고른 뒤 글을 적는 데까지. 대부분의 검사가 여기서 시작한다.
 * 종류를 고르지 않는 경우를 보려면 `pick` 에 null 을 준다.
 */
function openAndType(text: string, pick: string | null = '기타') {
  fireEvent.click(screen.getByRole('button', { name: '의견 보내기' }));
  if (pick) fireEvent.click(screen.getByRole('radio', { name: pick }));
  fireEvent.change(screen.getByRole('textbox'), { target: { value: text } });
}

function sendButton() {
  return screen.getByRole('button', { name: '보내기' }) as HTMLButtonElement;
}

describe('FeedbackBox', () => {
  it('처음에는 접혀 있다 — 늘 펼쳐진 입력칸은 아래 안내를 밀어낸다', () => {
    render(<FeedbackBox />);
    expect(screen.getByRole('button', { name: '의견 보내기' })).toBeTruthy();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('펴면 답장을 못 한다는 사실과 연락처를 적지 말라는 안내가 함께 보인다', () => {
    render(<FeedbackBox />);
    fireEvent.click(screen.getByRole('button', { name: '의견 보내기' }));

    const guide = screen.getByText(/개인정보를 받지 않고/);
    expect(guide.textContent).toContain('답장을 드릴 수 없습니다');
    expect(guide.textContent).toContain('적지 말아 주세요');
  });

  it('빈 글로는 못 보낸다', () => {
    render(<FeedbackBox />);
    fireEvent.click(screen.getByRole('button', { name: '의견 보내기' }));

    const send = screen.getByRole('button', { name: '보내기' }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
  });

  it('공백만 적어도 못 보낸다', () => {
    render(<FeedbackBox />);
    openAndType('    ');
    expect((screen.getByRole('button', { name: '보내기' }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it('보내면 앞뒤 공백을 떼고 opinion 으로 보낸다', async () => {
    render(<FeedbackBox />);
    openAndType('  3층이 안 보여요  ');
    fireEvent.click(screen.getByRole('button', { name: '보내기' }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].kind).toBe('opinion');
    expect(calls[0].body).toBe('3층이 안 보여요');
  });

  it('보던 건물·지역이 자동으로 함께 간다 — 이 의견함의 값어치 전부', async () => {
    render(<FeedbackBox context={{ bld_id: 'B1', sigungu: '11680' }} />);
    openAndType('한마디');
    fireEvent.click(screen.getByRole('button', { name: '보내기' }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].context).toEqual({ bld_id: 'B1', sigungu: '11680', category: 'other' });
  });

  it('종류를 안 고르면 글을 적어도 못 보낸다 — 기본 선택이 없다', () => {
    render(<FeedbackBox />);
    openAndType('한마디', null);

    // 미리 골라 둔 것이 없어야 한다 — 있으면 대부분 그대로 보내 한 갈래로 쌓인다.
    for (const r of screen.getAllByRole('radio') as HTMLInputElement[]) {
      expect(r.checked).toBe(false);
    }
    expect(screen.getAllByRole('radio')).toHaveLength(4);
    expect(sendButton().disabled).toBe(true);

    fireEvent.click(screen.getByRole('radio', { name: '정보가 틀려요' }));
    expect(sendButton().disabled).toBe(false);
  });

  it('고른 종류가 context.category 로 실려 간다 — kind 는 그대로 opinion', async () => {
    render(<FeedbackBox context={{ sigungu: '11680' }} />);
    openAndType('한마디', '버그·오류');
    fireEvent.click(sendButton());

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].kind).toBe('opinion');
    expect(calls[0].context).toEqual({ sigungu: '11680', category: 'bug' });
  });

  it('⛔ 숨김 칸에 값이 있으면 보내지 않고, 봇에게는 똑같이 고맙다고 한다', async () => {
    const { container } = render(<FeedbackBox />);
    openAndType('광고 글');
    const trap = container.querySelector('input[name="fb_url_confirm"]') as HTMLInputElement;
    // 사람 눈·탭 순서·읽어 주는 기기에 안 걸리는 칸이어야 한다.
    expect(trap.tabIndex).toBe(-1);
    expect(trap.getAttribute('aria-hidden')).toBe('true');
    fireEvent.change(trap, { target: { value: 'http://spam.example' } });
    fireEvent.click(sendButton());

    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('고맙습니다'));
    expect(calls).toHaveLength(0);
  });

  it('닫았다 다시 열면 종류 선택이 비어 있다', () => {
    render(<FeedbackBox />);
    openAndType('한마디', '건의·제안');
    expect((screen.getByRole('radio', { name: '건의·제안' }) as HTMLInputElement).checked).toBe(
      true,
    );

    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    fireEvent.click(screen.getByRole('button', { name: '의견 보내기' }));
    for (const r of screen.getAllByRole('radio') as HTMLInputElement[]) {
      expect(r.checked).toBe(false);
    }
    expect(sendButton().disabled).toBe(true);
  });

  it('보내고 나면 고맙다고 말하고 입력칸을 비운다', async () => {
    render(<FeedbackBox />);
    openAndType('한마디');
    fireEvent.click(screen.getByRole('button', { name: '보내기' }));

    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('고맙습니다'));
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('');
    // 고른 종류도 비운다 — 남아 있으면 다음 글이 같은 종류로 그냥 실려 간다.
    expect((screen.getByRole('radio', { name: '기타' }) as HTMLInputElement).checked).toBe(false);
  });

  it('⛔ 못 보냈으면 못 보냈다고 말한다 — 거짓 안심을 만들지 않는다', async () => {
    willSucceed = false;
    render(<FeedbackBox />);
    openAndType('한마디');
    fireEvent.click(screen.getByRole('button', { name: '보내기' }));

    await waitFor(() =>
      expect(screen.getByRole('status').textContent).toContain('보내지 못했습니다'),
    );
    // 실패했으면 적은 글은 남아 있어야 한다 — 다시 쓰게 만들면 대부분 그냥 떠난다.
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('한마디');
  });

  it('실패 뒤 다시 고쳐 쓰기 시작하면 지난 안내는 치운다', async () => {
    willSucceed = false;
    render(<FeedbackBox />);
    openAndType('한마디');
    fireEvent.click(screen.getByRole('button', { name: '보내기' }));
    await waitFor(() =>
      expect(screen.getByRole('status').textContent).toContain('보내지 못했습니다'),
    );

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '한마디 더' } });
    expect(screen.getByRole('status').textContent).toBe('');
  });

  it('보낸 뒤 닫아도 보냈다는 사실은 남는다', async () => {
    render(<FeedbackBox />);
    openAndType('한마디');
    fireEvent.click(screen.getByRole('button', { name: '보내기' }));
    await waitFor(() => expect(calls).toHaveLength(1));

    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(screen.getByRole('status').textContent).toContain('고맙습니다');
  });

  it('글자 수를 보여주고 상한을 넘기지 못하게 한다', () => {
    render(<FeedbackBox />);
    openAndType('12345');
    expect(screen.getByText(/5 \/ 2000자/)).toBeTruthy();
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).maxLength).toBe(2000);
  });
});
