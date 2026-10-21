# 조사 C 결과 — 역할별 첫 화면 · 휴대폰 앱 꼴 · 지도 배율 관례 (2026-10-17 · 웹 조사 · 레포 수정 0)

> 정직한 전제: 검색·문서 가져오기로는 **앱 안의 하단 탭 이름·바텀시트 유무를 확인할 수 없는 곳이 대부분**이었다(앱 스토어 소개는 기능 글이고 화면 구조를 안 쓴다). 확인 못 한 칸은 "확인 못 함", 추측은 '추정'으로 표시했다. 44곳 조사(`경쟁사조사-2026-10.md`)와 겹치는 내용은 다시 쓰지 않았다.

## 결론 (5줄)
1. **추천 꼴 = 하단 탭 3~4개(찾기 · 내 메모 · 설명) + 건물 화면은 한 줄 길게 + 접힘 카드(지금 방식 유지·다듬기).** 장점: 안드로이드 가이드(3~5개)와 맞고 역할 바꾸기도 한 곳에 둔다. 단점: 탭을 오가면 건물 화면 위치 기억이 끊긴다 → 탭 상태 보존 필요.
2. **자료 카드 10여 장은 탭으로 쪼개지 말고 "역할 순서 + 접힘" 유지.** NN/g: 탭은 "긴 구역 몇 개", 아코디언은 "짧은 구역 여러 개". 단점: 접힌 것은 놓치기 쉬움 → 핵심 카드만 열어 두기(이미 상한 4).
3. **역할 고르기는 "처음 한 번 칩 + 언제든 바꾸기"가 관례에 가깝다.** 서울시 상권분석(나는 사장/나도 곧 사장), 에어비앤비(손님/호스트 방식 전환), 노션(용도 한 문항) 모두 선택이 순서·탭·추천을 바꾼다. 자료는 한 벌, 보이는 순서만 바뀌는 결정 0036 #11과 같은 결.
4. **지도 배율: 카카오 `setBounds`는 여백(padding) 인자가 있고 기본 사방 32.** "도형 전부 담기"와 "여백 두기"는 SDK만으로 가능. 밀집 중심 맞춤은 공식 기능이 아니라 우리가 계산해 `setBounds`에 넣어야 한다(추정).
5. **PWA는 manifest(이름·아이콘 192/512·start_url·display)+HTTPS면 크롬 설치 가능. iOS는 수동 안내(공유 → 홈 화면에 추가), 설치 버튼 이벤트 없음.** 비용은 거의 0이지만 효과는 설치한 사람만.

## 1. 휴대폰 앱 꼴 표 (12행)
| # | 서비스 | ① 하단 탭 | ② 바텀시트 | ③ 첫 화면 | ④ 역할·목적 고르기 | ⑤ PC와 구조 다름 | 출처 |
|---|---|---|---|---|---|---|---|
| 1 | 네이버 부동산(네이버페이 앱 안) | 별도 앱은 2024 종료, **네이버페이 앱 하단에 증권·부동산 탭 추가**(2023-12). 부동산 안쪽 탭 이름은 확인 못 함 | 확인 못 함(매물지도 "매물목록뷰"는 있음) | 부동산 홈에 인기 급상승·최근 본 매물, 매물지도 | 없음(추정) | 확인 못 함 | [designcompass](https://designcompass.org/2024/08/14/naver-real-estate-service-end/) · [tokenpost](https://www.tokenpost.kr/news/tech/341600) · [AMPM](https://inside.ampm.co.kr/insight/10896) |
| 2 | 직방 | 확인 못 함 | 확인 못 함 | 칼럼 평가: 첫 화면에서 **집 유형을 고르고** → 지도로 찾기 또는 지하철역으로 찾기(2차 출처) | 유형 고르기만 | 확인 못 함 | [Wishket](https://yozm.wishket.com/magazine/detail/1077/) · [앱스토어](https://apps.apple.com/KR/app/id503098735) |
| 3 | 호갱노노 | "**전체**"·"**이야기**" 탭 이름만 확인. 나머지 확인 못 함 | 확인 못 함 | 지도 기반(앱 설명) | 없음 | 확인 못 함 | [앱스토어](https://apps.apple.com/kr/app/id1084799742) |
| 4 | 밸류맵 | 확인 못 함 | 확인 못 함 | 지도 형식의 토지·건물 실거래 조회 앱 | 확인 못 함 | 확인 못 함 | [뉴스토마토](https://www.newstomato.com/ReadNews.aspx?no=859490) |
| 5 | 디스코 | 확인 못 함 | 확인 못 함 | 앱 켤 때 **현재 위치로 지도 이동**(v1.0.73) · 첫 화면 개편(v1.1.0, 내용 없음) | 확인 못 함 | 확인 못 함 | [앱스토어](https://apps.apple.com/kr/app/%EB%94%94%EC%8A%A4%EC%BD%94-%EB%93%B1%EA%B8%B0-%ED%99%95%EC%9D%B8-%EC%8B%A4%EA%B1%B0%EB%9E%98%EA%B0%80/id1249912799) |
| 6 | 부동산플래닛 | 확인 못 함 | 확인 못 함 | 지도(지번을 찍으면 공시지가·건축물 정보) · 후기: **아이폰은 로드뷰가 지도 위쪽에 작게** | 확인 못 함 | 후기상 PC와 로드뷰 위치가 다름 | [앱스토어](https://apps.apple.com/kr/app/%EB%B6%80%EB%8F%99%EC%82%B0%ED%94%8C%EB%9E%98%EB%8B%9B-%EC%A0%84%EA%B5%AD-%ED%86%A0%EC%A7%80%EA%B1%B4%EB%AC%BC-%EC%8B%A4%EA%B1%B0%EB%9E%98%EA%B0%80-%EB%B0%8F-ai-%EC%B6%94%EC%A0%95%EA%B0%80/id1621637899?l=ko) |
| 7 | 랜드북 | 부동산 분석을 접고 건축설계 AI로 전환(44곳 조사) — 휴대폰 구조 확인 못 함 | — | — | — | — | 기존 문서 |
| 8 | 아실 | 확인 못 함 | 확인 못 함 | 확인 못 함 | 확인 못 함 | 확인 못 함 | 공식 안내 못 찾음 |
| 9 | 서울시 상권분석(우리마을가게) | PC는 상단 메뉴(뜨는 상권·나는 사장·나도 곧 사장·지역/상권별 현황). **모바일은 "위치정보 기반으로 설계"**, 하단 탭은 확인 못 함 | 확인 못 함 | 메인 서비스 카드 4(창업신호등·서울상권검색·상권정보분석·지역별현황) | **있음**: 예비창업자(업종 고민/확정) vs 기존 사장님 | 모바일은 위치 기반, **회원가입은 PC만** | [golmok](https://golmok.seoul.go.kr/introduce1.do) |
| 10 | 소상공인365 | 확인 못 함 | 확인 못 함 | 4대 서비스 → 상권분석은 **간단/상세 분석을 고른 뒤 지도에서 지역 선택** | 목적별 서비스 + "따라하기" | 확인 못 함 | [Newsis](https://www.newsis.com/view/NISX20241218_0003001986) · [SBS Biz](https://biz.sbs.co.kr/amp/article/20000204201) |
| 11 | 나이스비즈맵 | 확인 못 함 | 확인 못 함 | 확인 못 함 | 확인 못 함 | 확인 못 함 | 검색에서 안 나옴 |
| 12 | 오픈업(핀다) | 확인 못 함 | 확인 못 함 | 관심 지역 설정 후 등급·AI 해설 리포트(프로 · B2B 2025-10) | 일반(무료)·프로(본사)로 갈림 | 확인 못 함 | [Byline](https://byline.network/2025/10/1028/) |

**표에서 읽히는 것**: 확인된 곳(네이버·직방·디스코·부동산플래닛·호갱노노)은 모두 **지도 중심**이고, 역할/목적 고르기가 확인된 곳은 서울시 상권분석과 직방(유형 고르기)뿐. 하단 탭·바텀시트는 공개 글로 확인된 사실이 거의 없다 — 앱을 직접 열어 캡처하는 방법밖에 없다.

## 2. 역할(목적)별 첫 화면을 다르게 하는 사례
- **에어비앤비(여행 ↔ 호스팅)**: 프로필에서 "호스팅으로 전환". 호스팅 방식 하단 탭은 받은편지함·캘린더·숙소·진행·프로필, 여행 방식은 탐색·여행 등(커뮤니티 운영자 글, 버전 차이 가능). 바꾸는 것 = **하단 탭 전체**. [도움말](https://www.airbnb.com/help/article/3546) · [커뮤니티](https://community.withairbnb.com/t5/Hosting/Airbnb-App/td-p/799489)
- **노션(업무·개인·학교)**: 용도 한 문항 → 환영 설문과 **템플릿 추천·체크리스트**가 달라짐(제3자 분석, 공식 문서 못 열었음). 바꾸는 것 = 홈 카드·추천. [Candu](https://candu.ai/blog/how-notion-crafts-a-personalized-onboarding-experience-6-lessons-to-guide-new-users)
- **듀오링고(왜 배우나·목표)**: 목표·수준 질문이 학습 경로를 개인화(분석 글 하나). 바꾸는 것 = 기본 경로. [Appcues](https://www.appcues.com/blog/the-10-best-user-onboarding-experiences)
- **서울시 상권분석(나는 사장 / 나도 곧 사장)**: 업종 고민이면 업종 추천, 확정이면 지역 비교로 흐름이 갈림. 바꾸는 것 = **기본 흐름과 문구**. [golmok](https://golmok.seoul.go.kr/introduce1.do)
- 공통: 선택 한 번 → (홈 카드 순서 · 탭 · 기본 추천) 중 하나를 바꿈. 소비자 앱의 "나는 ○○" 첫 화면 실제 사례는 검색으로 더 못 찾았다.

## 3. 지도 배율 관례
- **카카오 `setBounds` 서명(공식 원문)**: `setBounds(bounds[, paddingTop, paddingRight, paddingBottom, paddingLeft])`. 파라미터 `bounds: LatLngBounds`, 나머지 `Number`. 설명: 주어진 영역이 화면 안에 보이도록 중심과 확대 수준을 정함, padding은 top·right·bottom·left 순서이고 일부만 주면 CSS padding 규칙처럼 채워지며 **지정하지 않으면 기본 상하좌우 32가 적용**. [apis.map.kakao.com/web/documentation](https://apis.map.kakao.com/web/documentation/) (Map 절). `LatLngBounds` 메서드: equals·toString·getSouthWest·getNorthEast·isEmpty·extend·contain.
- **react-kakao-maps-sdk 1.2.2**(npm 패키지 `.d.ts` 직접 확인): `Map`에 `padding?: number`(기본 32, 중심을 영역으로 줄 때 padding만큼 빼고 계산)가 있다. 사방 개별 padding은 이 prop에 없음 → 위·아래를 다르게 두려면 `useMap()`으로 얻은 map에 직접 `setBounds(bounds, t, r, b, l)`. 문서 홈 [react-kakao-maps-sdk.jaeseokim.dev](https://react-kakao-maps-sdk.jaeseokim.dev/) (예제 페이지 직접 주소는 404였음).
- **도형 전부 vs 밀집 중심**: 공식 문서에 "행정구를 보여 줄 때의 관례"는 없다. `LatLngBounds.extend`로 전부 넣고 `setBounds` 하면 "전부 담기", 일부만 넣으면 "중심 맞춤" — 선택은 우리 몫(추정). 포럼에는 `extend`가 점 하나씩만 먹힌 사례([devtalk](https://devtalk.kakao.com/t/bounds-extend/116542)).
- **멀리서 점·묶음으로**: 카카오 `MarkerClusterer`(옵션 `gridSize`·`averageCenter`·`minLevel`), react-kakao-maps-sdk에도 `MarkerClusterer`(같은 옵션). 도형(Polygon)을 점으로 바꾸는 기능은 문서에 없어 확대 수준에 따라 마커/도형을 번갈아 그리는 건 우리 몫(추정). 구글 지도도 같은 관례: 멀리 묶음, 가까이 낱개 [Google](https://developers.google.com/maps/articles/toomanymarkers).

## 4. PWA 최소 요소
- Chromium 설치 조건: manifest의 `name`/`short_name`, `icons`(**192·512px**), `start_url`, `display`(또는 `display_override`), `prefer_related_applications` 없음/false + **HTTPS**. 서비스 워커는 설치에 필수 아님. [MDN](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable)
- iOS: 설치 안내 이벤트(`beforeinstallprompt`) 없음 → 공유 → "홈 화면에 추가"를 수동 안내, `display`는 standalone만 지원, `apple-touch-icon` 권장(없으면 화면 캡처가 아이콘). [web.dev](https://web.dev/learn/pwa/installation)
- safe-area: `env(safe-area-inset-bottom)`으로 하단 탭이 홈 막대에 안 겹치게. [MDN env()](https://developer.mozilla.org/en-US/docs/Web/CSS/env). `viewport-fit=cover`가 있어야 값이 0이 아니라는 설명은 이 문서엔 없고 일반 지식이다(추정).
- `theme-color` 메타는 공식 문서를 열지 못함.

## 5. 한 쪽 긴 스크롤 vs 탭 분할
- NN/g: **탭 = 긴 구역 몇 개 / 아코디언 = 짧은 구역 여러 개**. [Tabs vs. Accordions](https://www.nngroup.com/videos/tabs-vs-accordions/)
- NN/g: 아코디언은 휴대폰 긴 페이지를 덜어 주지만 길을 잃거나 스크롤이 늘 수 있다. [Accordions on Mobile](https://www.nngroup.com/videos/accordions-on-mobile/)
- NN/g: 사용자가 대부분의 내용이 필요하거나 덩어리로 못 나누면 아코디언을 피하라. [5 Scenarios](https://www.nngroup.com/videos/avoid-accordions/)
- NN/g 시선 연구(데스크톱): 보는 시간의 74%가 첫 두 화면 → 중요한 것은 위에. 모바일 수치 아님. [Scrolling and Attention](https://www.nngroup.com/articles/scrolling-and-attention/)
- 안드로이드: 하단 내비 바는 **같은 단계 목적지 3~5개**, 더 많으면 서랍(위쪽으로 손이 가야 해 불리). [Android Developers](https://developer.android.com/design/ui/mobile/guides/layout-and-content/layout-and-nav-patterns)
- 애플 HIG 탭 바: 최상위 이동용 · 늘 보이게 · 동작 버튼 아님 — 페이지 본문이 안 와서 **원문 대조 못 함(기억 기반 추정)**. [HIG](https://developer.apple.com/design/human-interface-guidelines/tab-bars)
- 머티리얼 바텀 시트: 표준(주 화면 옆에 계속 떠 있는 보조 내용) vs 모달(닫아야 아래를 누름). [material.io](https://material.io/components/sheets-bottom)

## 확인 못 한 것
- 네이버(부동산 안쪽)·직방·호갱노노·밸류맵·디스코·부동산플래닛·아실·나이스비즈맵·오픈업·소상공인365·우리마을가게 앱의 **하단 탭 이름과 바텀시트 유무** — 공개 글에 없음. 사장님 휴대폰에서 실제 앱 캡처가 필요.
- 애플 HIG 원문 인용, 머티리얼 3 네비게이션 바 원문(안드로이드 개발자 문서로 대체), 노션·듀오링고 **공식** 온보딩 설명, 카카오 문서의 "행정구 보기" 관례, `theme-color` 공식 문서, `viewport-fit=cover` 조건.
- 직방 "집 유형 고르기"는 칼럼 평가(2차 출처)라 현행 화면인지 미확인. 에어비앤비 탭 이름은 커뮤니티 운영자 글.
- NN/g의 **휴대폰 전용** 스크롤 수치(영상 요약만 확인, 원문 기사 미열람).
