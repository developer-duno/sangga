import { describe, expect, it } from 'vitest';
import { shortAddr } from './shortAddr';

const SEOGU = { sido: '대전광역시', sigungu: '서구' };

describe('shortAddr — 왼쪽 칸 주소는 길 이름부터 (👤 2026-10-22 L2)', () => {
  it('같은 구 도로명 = 시·구를 뺀다', () => {
    expect(shortAddr('대전광역시 서구 둔산북로 22', SEOGU)).toBe('둔산북로 22');
  });

  it('같은 구 지번 = 동부터', () => {
    expect(shortAddr('대전광역시 서구 둔산동 1451', SEOGU)).toBe('둔산동 1451');
  });

  it('다른 구 주소는 그대로 — 다른 시의 같은 이름 구(인천 서구)도', () => {
    expect(shortAddr('대전광역시 유성구 대학로 99', SEOGU)).toBe('대전광역시 유성구 대학로 99');
    expect(shortAddr('인천광역시 서구 봉오대로 1', SEOGU)).toBe('인천광역시 서구 봉오대로 1');
    // 구 이름이 앞에 붙은 다른 낱말(서구청로)과 헷갈리지 않는다 — 시·도 다음 낱말 전체가 구 이름일 때만.
    expect(shortAddr('대전광역시 서구청로 1', SEOGU)).toBe('대전광역시 서구청로 1');
  });

  it('빈 값 · 구를 모름 = 그대로 · 다 빼면 빈 글이 되는 주소도 그대로', () => {
    expect(shortAddr('', SEOGU)).toBe('');
    expect(shortAddr('대전광역시 서구 둔산북로 22', null)).toBe('대전광역시 서구 둔산북로 22');
    expect(shortAddr('대전광역시 서구 둔산북로 22', { sido: '대전광역시', sigungu: '' })).toBe('대전광역시 서구 둔산북로 22');
    expect(shortAddr('대전광역시 서구 ', SEOGU)).toBe('대전광역시 서구 ');
  });

  it('구 없는 시(세종특별자치시) = 시 이름만 뺀다', () => {
    const SEJONG = { sido: '세종특별자치시', sigungu: '세종특별자치시' };
    expect(shortAddr('세종특별자치시 한누리대로 2130', SEJONG)).toBe('한누리대로 2130');
    expect(shortAddr('세종특별자치시 어진동 590', SEJONG)).toBe('어진동 590');
  });

  it('두 낱말 시군구(수원시 장안구) · 띄어쓰기 두 칸도 맞는다 · 정규식 글자가 든 이름도 안전', () => {
    expect(shortAddr('경기도 수원시 장안구 정조로 1', { sido: '경기도', sigungu: '수원시 장안구' })).toBe('정조로 1');
    expect(shortAddr('대전광역시  서구  둔산북로 22', SEOGU)).toBe('둔산북로 22');
    expect(shortAddr('대전광역시 서(구) 1', { sido: '대전광역시', sigungu: '서(구)' })).toBe('1');
  });
});
