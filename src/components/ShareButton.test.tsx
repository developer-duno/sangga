import { describe, expect, it, vi, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ShareButton } from './ShareButton';

/**
 * 여기서 특히 지키는 것
 * ---------------------
 * **복사에 실패했는데 "복사했습니다"라고 말하지 않는 것.** 복사는 https 가 아니면
 * 아예 없고 권한으로도 막힌다. 성공한 척하면 사용자는 빈 클립보드를 붙여넣게 된다
 * — 의견함에서 이미 정한 원칙과 같다(못 보냈으면 못 보냈다고 한다, 결정 0016).
 */

const URL_A = 'https://sangga-one.vercel.app/?sgg=11680&bld=1168010100107110006_1024110';
const URL_B = 'https://sangga-one.vercel.app/?sgg=11680&bld=1168010100106600028_1024113';

/** navigator.clipboard 를 통째로 갈아 끼운다. null 이면 "그런 기능이 없는 환경". */
function setClipboard(writeText: ((text: string) => Promise<void>) | null) {
  Object.defineProperty(navigator, 'clipboard', {
    value: writeText ? { writeText: vi.fn(writeText) } : undefined,
    configurable: true,
    writable: true,
  });
}

afterEach(() => {
  cleanup();
  setClipboard(null);
});

describe('ShareButton', () => {
  it('누르면 지금 주소를 복사한다', async () => {
    const writes: string[] = [];
    setClipboard(async (text) => {
      writes.push(text);
    });

    render(<ShareButton url={URL_A} />);
    fireEvent.click(screen.getByRole('button', { name: '링크 복사' }));

    expect(await screen.findByText('주소를 복사했습니다.')).toBeTruthy();
    expect(writes).toEqual([URL_A]);
  });

  it('복사가 막히면 "복사했습니다"라고 하지 않고 주소를 띄운다', async () => {
    setClipboard(async () => {
      throw new Error('권한 없음');
    });

    render(<ShareButton url={URL_A} />);
    fireEvent.click(screen.getByRole('button', { name: '링크 복사' }));

    expect(await screen.findByDisplayValue(URL_A)).toBeTruthy();
    expect(screen.queryByText('주소를 복사했습니다.')).toBeNull();
  });

  it('클립보드 기능 자체가 없는 곳(https 아님)에서도 안 깨진다', async () => {
    setClipboard(null);

    render(<ShareButton url={URL_A} />);
    fireEvent.click(screen.getByRole('button', { name: '링크 복사' }));

    expect(await screen.findByDisplayValue(URL_A)).toBeTruthy();
    expect(screen.queryByText('주소를 복사했습니다.')).toBeNull();
  });

  it('다른 건물로 옮겨 가면 이전 "복사했습니다"가 남지 않는다', async () => {
    setClipboard(async () => undefined);

    const { rerender } = render(<ShareButton url={URL_A} />);
    fireEvent.click(screen.getByRole('button', { name: '링크 복사' }));
    expect(await screen.findByText('주소를 복사했습니다.')).toBeTruthy();

    // 이 안내가 남아 있으면 **다른 건물** 주소를 복사한 줄 알게 된다.
    rerender(<ShareButton url={URL_B} />);
    await waitFor(() => expect(screen.queryByText('주소를 복사했습니다.')).toBeNull());
  });

  it('되돌아온 주소 칸에 건물 이름을 붙여 무엇의 주소인지 알린다', async () => {
    setClipboard(async () => {
      throw new Error('막힘');
    });

    render(<ShareButton url={URL_A} label="역삼빌딩" />);
    fireEvent.click(screen.getByRole('button', { name: '링크 복사' }));

    expect(await screen.findByLabelText('역삼빌딩 주소')).toBeTruthy();
  });
});
