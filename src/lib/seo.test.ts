import { describe, it, expect } from 'vitest';
import { HOME_TITLE, SITE_NAME, pageTitle } from './seo';

describe('seo — 탭 제목', () => {
  it('건물 이름이 있으면 "<이름> — 상가 층별 스택뷰"', () => {
    expect(pageTitle('테스트빌딩')).toBe('테스트빌딩 — 상가 층별 스택뷰');
  });

  it('이름이 없으면(null) 첫 화면 제목', () => {
    expect(pageTitle(null)).toBe(HOME_TITLE);
    expect(pageTitle(undefined)).toBe(HOME_TITLE);
  });

  it('빈 이름이면 첫 화면 제목("— 상가 층별 스택뷰" 같은 반쪽 제목을 만들지 않는다)', () => {
    expect(pageTitle('')).toBe(HOME_TITLE);
  });

  it('첫 화면 제목은 서비스 이름으로 시작한다', () => {
    expect(SITE_NAME).toBe('상가 층별 스택뷰');
    expect(HOME_TITLE.startsWith(SITE_NAME)).toBe(true);
  });
});
