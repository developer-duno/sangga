import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/react';
import { PrintHeader } from './PrintHeader';

/**
 * 종이에만 나오는 머리글.
 *
 * 여기서 지키는 것은 셋이다:
 *   ① 이 종이가 **무슨 건물인지**(이름·주소) — 없는 건물이 실재하므로 빈칸을 안 만든다
 *   ② **언제 뽑았는지** — 화면을 열어 두고 한참 뒤에 인쇄하는 것이 오히려 흔하다
 *   ③ **원본이 어디인지**(주소) — 링크 복사 버튼과 **같은 값**이어야 한다
 *
 * ⚠️ 화면에서 안 보인다는 것은 CSS 라 여기서 못 본다(jsdom 은 우리 스타일시트를 안 읽는다).
 *    그건 E2E 가 인쇄 매체를 흉내 내 확인한다.
 */
const AT = new Date(2026, 7, 25, 3, 20); // 월은 0부터라 7 = 8월

beforeEach(() => {
  // Date 만 가짜로 세운다 — 타이머까지 가짜로 만들면 리액트의 비동기 도구가 멈춘다.
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(AT);
});

afterEach(() => {
  vi.useRealTimers();
  cleanup();
});

const URL_ = 'https://sangga-one.vercel.app/?sgg=11680&bld=1168010100106350002_1024112';

describe('PrintHeader — 종이 머리글', () => {
  it('건물 이름·주소·원본 주소를 적는다', () => {
    const { container } = render(
      <PrintHeader name="한국과학기술회관" address="서울특별시 강남구 테헤란로7길 22" url={URL_} />,
    );
    expect(container.querySelector('.printmeta__title')?.textContent).toBe('한국과학기술회관');
    expect(container.querySelector('.printmeta__addr')?.textContent).toBe(
      '서울특별시 강남구 테헤란로7길 22',
    );
    expect(container.querySelector('.printmeta__url')?.textContent).toBe(URL_);
  });

  it('이름·주소가 없는 건물이면 빈칸 대신 그렇다고 적는다', () => {
    // 이름 없는 건물·주소 없는 건물이 실재한다. 빈 줄을 남기면 종이가 고장 난 것처럼 보인다.
    const { container } = render(<PrintHeader name={null} address={null} url={URL_} />);
    expect(container.querySelector('.printmeta__title')?.textContent).toBe('(이름 없는 건물)');
    expect(container.querySelector('.printmeta__addr')?.textContent).toBe('주소 없음');
  });

  it('처음 그릴 때 그 시각을 적는다', () => {
    const { container } = render(<PrintHeader name="가" address="나" url={URL_} />);
    expect(container.querySelector('.printmeta__when')?.textContent).toBe('2026-08-25 03:20 뽑음');
  });

  it('인쇄가 시작되기 직전에 시각을 다시 맞춘다 (오래 열어 둔 화면을 뽑는 경우)', () => {
    const { container } = render(<PrintHeader name="가" address="나" url={URL_} />);

    // 화면을 한참 열어 뒀다.
    vi.setSystemTime(new Date(2026, 7, 25, 6, 5));
    fireEvent(window, new Event('beforeprint'));

    // 열었을 때(03:20)가 아니라 뽑는 지금(06:05)이 적힌다.
    expect(container.querySelector('.printmeta__when')?.textContent).toBe('2026-08-25 06:05 뽑음');
  });

  it('사라진 뒤에는 인쇄 신호를 안 듣는다 (치우지 않으면 없는 화면을 고치려 든다)', () => {
    const { unmount } = render(<PrintHeader name="가" address="나" url={URL_} />);
    unmount();
    // 걷어내지 않았다면 여기서 없는 컴포넌트에 상태를 밀어 넣어 경고가 난다.
    expect(() => fireEvent(window, new Event('beforeprint'))).not.toThrow();
  });

  it('서비스 이름을 함께 적는다 — 종이만 받은 사람이 출처를 알 수 있게', () => {
    const { container } = render(<PrintHeader name="가" address="나" url={URL_} />);
    expect(container.querySelector('.printmeta__app')?.textContent).toBe('상가 층별 스택뷰');
  });
});
