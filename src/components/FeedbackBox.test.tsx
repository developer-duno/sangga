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
 */

const calls: Array<{ kind: string; body: string; context: unknown }> = [];
let willSucceed = true;

vi.mock('../lib/feedback', () => ({
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

/** 접힌 상자를 펴고 글을 적는 데까지. 대부분의 검사가 여기서 시작한다. */
function openAndType(text: string) {
  fireEvent.click(screen.getByRole('button', { name: '의견 보내기' }));
  fireEvent.change(screen.getByRole('textbox'), { target: { value: text } });
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
    expect(calls[0].context).toEqual({ bld_id: 'B1', sigungu: '11680' });
  });

  it('보내고 나면 고맙다고 말하고 입력칸을 비운다', async () => {
    render(<FeedbackBox />);
    openAndType('한마디');
    fireEvent.click(screen.getByRole('button', { name: '보내기' }));

    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('고맙습니다'));
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('');
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
