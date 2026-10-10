import { describe, it, expect } from 'vitest';
import { HOME_TITLE, SITE_NAME, pageTitle } from './seo';
import { buildingTitle, buildingFacts } from './buildingHead';

describe('seo — 탭 제목', () => {
  it('건물 이름 + 도로명이면 "<이름> — <구 도로명> | 상가 층별 스택뷰"(서버 조각과 같은 꼴)', () => {
    expect(pageTitle('테스트빌딩', '서울특별시 강남구 테헤란로 1')).toBe('테스트빌딩 — 강남구 테헤란로 1 | 상가 층별 스택뷰');
  });

  it('도로명이 없으면 "<이름> | 상가 층별 스택뷰"', () => {
    expect(pageTitle('테스트빌딩')).toBe('테스트빌딩 | 상가 층별 스택뷰');
    expect(pageTitle('테스트빌딩', null)).toBe('테스트빌딩 | 상가 층별 스택뷰');
    expect(pageTitle('테스트빌딩', '  ')).toBe('테스트빌딩 | 상가 층별 스택뷰');
  });

  it('이름이 없으면(null) 첫 화면 제목', () => {
    expect(pageTitle(null)).toBe(HOME_TITLE);
    expect(pageTitle(undefined, '서울특별시 강남구 테헤란로 1')).toBe(HOME_TITLE);
  });

  it('빈 이름이면 첫 화면 제목("— 상가 층별 스택뷰" 같은 반쪽 제목을 만들지 않는다)', () => {
    expect(pageTitle('')).toBe(HOME_TITLE);
    expect(pageTitle('   ')).toBe(HOME_TITLE);
  });

  it('탭 제목과 서버 조각의 첫 HTML 제목이 글자까지 같다(결정 0037)', () => {
    for (const road of ['서울특별시 강남구 테헤란로 1', '대전광역시 서구 둔산로 100', '테헤란로', null]) {
      const f = buildingFacts([
        { bld_id: '1168010600109420015_1', pnu: '1168010600109420015', floor_no: 1, floor_label: null, segment_cnt: 1, main_use: null, uses: null, bld_nm: '가나빌딩', road_addr: road },
      ])!;
      expect(pageTitle('가나빌딩', road)).toBe(buildingTitle({ ...f, name: '가나빌딩' }));
    }
  });

  it('첫 화면 제목은 서비스 이름으로 시작한다', () => {
    expect(SITE_NAME).toBe('상가 층별 스택뷰');
    expect(HOME_TITLE.startsWith(SITE_NAME)).toBe(true);
  });
});
