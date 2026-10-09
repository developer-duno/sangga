/*
  브라우저 탭 제목의 정본(👤 2026-10-09 — 검색·AI 노출 기본 세팅).

  ⛔ `HOME_TITLE` 은 `index.html` 의 `<title>` 과 글자가 같아야 한다 — 첫 HTML(검색 봇·카카오톡이
     읽는 것)과 화면이 띄운 뒤의 탭 제목이 갈리면 안 된다. `tests/test_seo_head.py` 가 둘을 대조한다.
  ⛔ '서울·대전'은 서버 목록이 아니라 글자라 저절로 안 따라온다 — 열린 지역이 늘면
     `index.html`·`public/og-image.png`(scripts/make_og_image.py)·`public/site.webmanifest` description·`tests/test_seo_head.py`·이 파일을 함께 고친다.
*/

import { shortAddr } from './buildingHead';

export const SITE_NAME = '상가 층별 스택뷰';

export const HOME_TITLE = '상가 층별 스택뷰 — 서울·대전 상가 건물 층별 공공데이터';

/**
 * 건물을 골랐으면 서버 조각(결정 0037)의 첫 HTML 제목과 **같은 꼴** —
 * `<이름> — <도로명에서 시·도를 뗀 것> | 상가 층별 스택뷰`, 도로명이 없으면 `<이름> | 상가 층별 스택뷰`.
 * 이름이 없으면(없음·빈 이름) 첫 화면 제목.
 * ⛔ 주소 줄이기는 `buildingHead.ts` 의 `shortAddr` 하나를 함께 쓴다 — 따로 만들면 탭 제목과 첫 HTML 제목이 갈린다.
 */
export function pageTitle(bldNm: string | null | undefined, roadAddr?: string | null): string {
  const name = bldNm?.trim();
  if (!name) return HOME_TITLE;
  const road = roadAddr?.trim();
  return road ? `${name} — ${shortAddr(road)} | ${SITE_NAME}` : `${name} | ${SITE_NAME}`;
}
