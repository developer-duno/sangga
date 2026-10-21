# 조사 B 결과 — 역할별 차이 · 휴대폰 배치 · 지도 배율 (읽기 전용 · 기준 main 7a2ceba · 2026-10-17)

## 한 줄 결론
- 역할 차이는 "카드 순서·펼침 + 창업자 칩 + 중개사 칸 몇 개"가 **맞다**(다만 입구 차례 하나가 더 있다 — 표 1).
- 휴대폰 전용 구조(하단 바·시트·탭·고정 바)는 **없다**. 한 쪽 안 세로 스크롤 + 폭 720px 이하에서 칸 접기뿐.
- 지도는 구 상권 전부의 바깥 상자에 맞춰 열려서, 상권 도형 하나(가운데값 약 270m 변)가 화면에서 약 11~16px 밖에 안 된다.

## 1. 역할이 실제로 바꾸는 것 (읽는 자리 전수, 시험 파일 제외)

| 자리 | 무엇이 달라지나 | 종류 |
|---|---|---|
| `src/App.tsx:63` | 상태 `viewerRole` (첫 그림에 `loadViewerRole()` — 기기 저장소 `sangga.viewerRole`, `viewerRoleStore.ts:14`) | 상태 |
| `App.tsx:69` | 창업자일 때만 업종 칩 값이 유효(아니면 늘 '전체') | 칩 |
| `App.tsx:76-79` | 역할 고르기 = 상태 + 저장 + 창업자 아니면 칩 초기화 | 상태 |
| `App.tsx:180` | 중개사일 때만 인쇄 단추가 '최근 뽑은 건물'에 적음 | 중개사 칸 |
| `App.tsx:359` | 중개사만 검색 결과 줄에 소유 구조 한 줄(`BuildingSearch.tsx:424`) | 중개사 칸 |
| `App.tsx:365` | 중개사만 검색창 바로 아래 '최근 뽑은 건물' | 중개사 칸 |
| `App.tsx:403` | 창업자만 지도 머리에 업종 칩 줄(`FounderChips`) | 칩 |
| `App.tsx:430` | 중개사만 종이 머리에 내 사무소 상자 | 중개사 칸(종이) |
| `App.tsx:465` | 칩이 '전체'가 아니면 접힌 바에 `업종: 카페` 글자 | 칩 |
| `App.tsx:496` | 접힌 바 단추 글자 `나는 {역할 ?? 역할 고르기}` | 문구 |
| `App.tsx:519` | 역할 단추 줄 `RolePicker` (역할 없음 = 아무것도 안 눌림) | 입구 |
| `App.tsx:533` → `sectionCards.ts:198` | 입구 두 덩어리 차례: **창업자만 지도→검색**, 나머지·없음은 검색→지도 | 순서 |
| `App.tsx:602` | 중개사만 인쇄 줄에 사무소 정보 입력(`BrokerOfficeForm`) | 중개사 칸 |
| `App.tsx:622-623` | `FloorStack` 에 `viewerRole`·`founderChip` 전달 | 전달 |
| `FloorStack.tsx:312` → `sectionCards.ts:178` | 역할별 `defaultOpen` 표(펼침) | 펼침 |
| `FloorStack.tsx:1120` → `sectionCards.ts:184` | 역할별 카드 그리는 차례 | 순서 |
| 칩이 읽히는 곳: `FloorStack.tsx:928·1003`(업종 분포·개업폐업 카드 강조), `DistrictMap.tsx:111·145·374`→`DistrictBuildings`(지도 상권 목록 업종 기준) | 칩 효과(화면만) | 칩 |

수 확인: `App.tsx` 에서 역할 값을 직접 비교하는 자리 7곳(69·180·359·365·403·430·602), 표를 거치는 자리 3곳(`entryBlockOrder`·`sectionPlansFor`·`sectionOrder`). 다른 컴포넌트는 역할을 직접 모른다(grep 결과 `FloorStack`·`RolePicker`·`sectionCards`·`viewerRoleStore` 뿐). 따라서 **자료·함수·서버 호출은 역할에 따라 달라지지 않는다**(카드는 늘 11장 전부 그려지고 순서·펼침만 다르다). 결론 문장은 맞되 보태야 할 둘: ① 입구 지도/검색 차례 ② 중개사의 종이 머리 사무소·최근 뽑은 건물·소유 구조 줄.

## 2. 카드 목록표 (`sectionCards.ts` `SECTION_PLAN` 정본 · 층별 화면 11장)

| 열쇠 | 제목 | 역할 태그 | 기본(역할 없음) | 투자자 | 창업자 | 중개사 | 자료(날짜 줄) | 빈 카드 | 접힌 채 한 줄 |
|---|---|---|---|---|---|---|---|---|---|
| district | 속한 상권 | 공통 | 펼침 | 1 펼 | 1 펼 | 3 펼 | district | – | 있음(`DistrictAnswer`) |
| floors | 층 목록 | 공통 | 펼침 | 2 펼 | 2 펼 | 1 펼 | ledger·sangkwon·tx | – | `층 N개 · 점포 M곳` |
| industry | 둘레의 업종 분포 | 창업자 | 펼침 | 7 접 | 3 펼 | 7 접 | sangkwon·permit | – | 있음 |
| tx | 실거래 기록 | 투자자 | 펼침 | 3 펼 | 8 접 | 2 펼 | tx | – | `이 땅 거래 N건 · 층대별 단가` |
| band | 참고 매매 시세(추정값) | 투자자 | 접힘 | 4 펼 | 9 접 | 4 펼 | tx·nts | – | 있음(숫자 없는 한 줄) |
| floorgap | 층 차이 세 잣대 | 공통 | 접힘 | 5 접 | 10 접 | 5 접 | nts·tx·rone | – | 고정 문장 |
| rent | 상권 임대 동향 | 투자자 | 접힘 | 6 접 | 11 접 | 6 접 | rone | – | 있음 |
| openclose | 상권 개업·폐업 | 창업자 | 접힘 | 8 접 | 4 펼 | 8 접 | openclose | – | 있음 |
| sales | 업종별 추정매출 | 창업자 | 접힘 | 9 | 5 | 9 | 없음 | **빈 카드** | `지금은 비어 있음`/`대전은 아직…` |
| pop | 유동인구 | 창업자 | 접힘 | 10 | 6 | 10 | 없음 | **빈 카드** | 위와 같음 |
| history | 이 자리 가게 이력 | 창업자 | 접힘 | 11 | 7 | 11 | 없음 | **빈 카드** | 위와 같음 |

(차례 숫자 = 해당 역할에서의 순서 `ROLE_SECTION_LAYOUT`, `sectionCards.ts:142-157`. 역할 없음 차례 = 표 위→아래.) 펼침 상한 4(`SECTION_EXPAND_BUDGET`) — 역할마다 정확히 4장 펼침. 요약 한 줄은 11장 전부 있다(`SectionCard.tsx:130` 에서 `summary` 가 null 이 아니면 그림). 입구 카드 셋(`ENTRY_SECTION_PLAN`: LH 공고·성적표·동네 단가 흐름)은 따로 — 구는 골랐고 건물은 안 골랐을 때만, 접힘(`App.tsx` 입구 카드 세 줄).

## 3. 휴대폰 배치 전수 (`@media` 목록: `grep -n "@media" src/styles.css`)

| 위치 | 묶음 | 하는 일 |
|---|---|---|
| `styles.css:620` | `max-width:720px` | 최근 뽑은 건물 줄 한 칸 |
| `:1700` | `min-width:721px` | 임대 띠 축 3칸(넓은 화면만) |
| `:3420` | `max-width:720px` | 검색 결과·층 줄·상세·호실 상세 한 칸 / 시세 줄 한 칸 / 막대 높이 10px / **지도 높이 300px** / 단가 흐름 줄 두 줄 / 층별 임대료 표 폭 100% |
| `:3512` | `screen and max-width:720px` | **층 줄 세 줄 묶음**(이름·용도·▼ / 막대 / 면적·점포·거래) — 화면만(종이에 안 샌다) |
| `:3640` | `max-width:720px` | 인쇄·공유 줄 세로 / 지도 목록 `.dbld__*` 세로 / 가게 이름 결과 세로 |
| `:3738` | `max-width:720px` | 층 차이 세 잣대 줄 한 칸 |
| `:3850` | `max-width:720px` | 사무소 입력 칸 한 칸 · 호실 인쇄 고르개 여백 |
| `:3902·4031·4095` | `screen` | 13px 글자 · 44px 누르기 · 긴 카드 10줄 창(폭과 무관 — 휴대폰 전용 아님) |
| `:4111` | `print` | 종이 |

- **휴대폰 전용 구조 없음**: 하단 바·시트·탭·서랍 grep 0건(아래 8번). 휴대폰은 "넓은 화면 한 벌을 칸 접기로 좁힌 것"이다.
- **고정/붙는 요소**: `position: fixed` 는 **안내 팝업 `.modal__back` 하나**(`styles.css:381`). `sticky` 0 · `safe-area` 0 · `vh/dvh` 0. 즉 화면 아래/위에 붙는 바가 하나도 없다.
- `index.html`: `viewport = width=device-width, initial-scale=1.0`(줌 막지 않음) · `theme-color #2f5fd0` · `apple-mobile-web-app-title`·`status-bar-style=default` · `link rel=manifest`.
- `public/site.webmanifest`: `display: standalone`, `start_url "/"`, 아이콘 192·512·maskable → **홈 화면에 추가하면 앱 모양 창으로 열린다**. **서비스워커·오프라인 0**(grep 0).
- 주소줄 가림/아래 바 대비 안전영역 처리 없음(`safe-area` 0) — 하단 바를 새로 만들면 처음 다뤄야 한다.

## 4. 지도 배율 로직 (`src/components/DistrictMap.tsx`)

- 첫 범위: `bounds = boundsOf(shown)`(`:221`, `geo.ts:73` — 그 구 상권 도형 **바깥 고리 전점**의 최소/최대) → `MapFocus` effect 가 `map.setBounds(new LatLngBounds(sw, ne))`(`:402`). **패딩 인자 없음**(카카오 기본), 최소 배율 제한 없음, 클러스터 없음(`MarkerClusterer|minLevel|maxLevel` grep 0). `<Map level={INITIAL_LEVEL=6}>`(`:282`, 상수 `:81`)은 초기값일 뿐 곧 `setBounds` 가 덮는다. 구가 0개면 "자료 없음" 글(`:274-277`).
- 건물을 고르면 `map.setLevel(FOCUS_LEVEL=4)` 먼저, 그다음 `panTo`(`:422-423`, 상수 `:73`, 4 ≈ 축척 100m). 효과 의존성이 건물 좌표뿐이라 이후 사용자가 줌한 것은 유지.
- 이름표는 level ≤ 5(`districtLabels.ts:25`)부터만 켠다. 구 전체 열기(setBounds)는 보통 그보다 넓어 **처음엔 이름표 없음**.
- 지도 높이: 기본 420px(`styles.css:788`), 720px 이하 300px(`:3459`), 폭은 100%. 종이: `.dmap__canvas` 는 avoid 대상(`:4339`).
- 도형이 작은 이유(실측, `public/districts.geojson` 1,687개, `area_m2` 전부 있음): 전체 가운데값 72,607㎡ (한 변 환산 약 270m) · 최대 2,462,734㎡ · 최소 1,854㎡. 구별 가운데값 47,496~133,953㎡ (표: 강남 79,185㎡ 103개 · 종로 67,886㎡ 74개 · 송파 103,612㎡ 70개 · 대전 동구 81,500㎡ 3개). 구 바깥 상자는 강남 약 9.2×7.8km, 종로 약 6.1×5.9km. 바깥 상자를 캔버스에 맞춘다고 가정한 **어림** 계산(카카오는 정해진 단계로만 배율을 맞추므로 실제는 최대 2배 차이): 가운데 크기 상권 한 변이 300px 높이에서 **약 11~16px**(강남 11 · 종로 13 · 송파 14 · 대전 동구 16), 412px 폭에서 15~39px. 즉 "구 전체를 한 번에" 맞추는 로직이라 개별 상권은 점이 된다.

## 5. URL·상태 구조

- 주소에 담기는 것은 **둘뿐**: `?sgg=<5자리 구>` · `?bld=<PNU19_숫자>`(`urlState.ts:BLD_RE`). 건물이 있으면 구는 건물 앞 5자리가 이긴다. 담기지 않는 것: 역할·업종 칩·카드 펼침·입구 접힘·지도 누른 상권·층 목록 펼침 — 전부 화면 상태(역할만 기기 저장 `sangga.viewerRole`). 사무소 칸·최근 뽑은 건물도 기기 저장(`brokerOfficeStore`·`recentPrintedStore`, localStorage 사용처는 이 세 개 + 주석뿐).
- 라우터 **없음**(`react-router|wouter|tanstack/react-router` package.json 0건). 쓰는 것은 `history.replaceState`(`App.tsx:310`)뿐 — 뒤로가기 단계가 안 쌓인다. 첫 그림에 한 번만 읽고 그 뒤 주소는 따라 적히기만 한다(`App.tsx:44-49`).
- 화면 전환 = **한 쪽 안 세로 스크롤**: 위에 입구(역할·구·검색·지도) → 건물을 고르면 입구가 한 줄 바(`.entrybar`)로 접히고(`App.tsx:~145·451-486`, S1) 그 아래 인쇄/링크 줄 → 층별 카드 11장 → 바닥글. 건물 없음/되살리는 중/실패는 각자 한 줄 글(`App.tsx:~640`). 서버 쪽 조각은 `api/building.ts` 하나(첫 HTML 머리글만 건물별, 결정 0037).

## 6. 0038 남은 단계가 바꾸는 것 (V1 은 #318 로 끝 — `src/lib/viz.ts` 있음)

| 단계 | 바꾸는 것 | 새 뼈대와 부딪힘 |
|---|---|---|
| V2 (B) | 실거래 카드에 구 층대 띠(사실 색) + 이 땅 점그림 | 카드 안 변경. 카드 순서·접힘 불변이면 충돌 없음. 점그림이 서면 지분 설명 줄이 늘 선다(#315 ② 예외). |
| V3 (G) | 층 펼침 호 목록 위 면적 비례 칸 한 줄 + 인쇄 호실 구성표 | 층 줄 세 줄 묶음(`:3512`)과 별개 자리(펼친 상세 안). 인쇄 표 장수가 달라질 수 있어 PDF 장수 전후 필요. |
| V4 (D) | 층 줄 `.floor__head` 안에 업종 띠(버튼 밖) + 마이그 1 | **휴대폰 세 줄 묶음에서 넷째 줄 추가** — 층 줄 구조를 바꾸는 유일한 단계. 휴대폰 앱 꼴로 층 줄을 다시 짜면 직접 충돌. |
| V5 (C) | 임대 카드 층 계단 막대 + 8분기 흐름 + 마이그 1 | 임대 카드 안. 새 함수 `list_rent_stat_history`, 미리 부르기(`sidePrefetch`) 여섯째. |
| V6 (H) | 개업·폐업 '전부 보기' + 마이그 1 | 카드 안 단추. 22분기 그림은 가로 밀기(`overflow-x:auto`)·종이 `visible`. |
| V7 | 문서 | 없음 |
공통 제약: PR 순서대로만·병렬 금지(전부 `FloorStack.tsx`·`styles.css`·E2E 건드림) · 휴대폰 규칙은 **`@media screen and (max-width:720px)`** 에만(옛 묶음에 넣으면 종이 모양이 바뀜) · 44px·13px 규칙 · 합치기 전 전/후 사진 + 👤 '진행'. **새 뼈대(역할별 첫 화면·휴대폰 앱 꼴)가 층 목록·카드 DOM 순서·카드 key 를 바꾸면 V2~V6 의 자리 지정(`.floor__head`, 카드 안 칸)과 E2E 선택자를 전부 다시 맞춰야 한다.** 착수 순서 충돌 방지: 새 뼈대를 먼저 하든 V2~V6 을 먼저 하든 `FloorStack.tsx`/`styles.css` 동시 수정 금지.

## 7. 제약·주의 (화면 뼈대와 관련된 것만)

1. 결정 0014: 수익·유료벽·가입유도·문의 강요 금지 · 매물은 링크로 · 자료는 한 벌, 시선만 셋 — 데이터를 거르거나 숨기지 않는다(§3). 역할이 바꾸는 것은 순서·접힘뿐이라는 전제가 결정 0036-18 ① 「역할 고르기 전 = 지금 화면 그대로」.
2. 결정 0036-11·18: 역할은 **이 기기에만**, 주소(0019)·의견함(0034)에 싣지 않는다(예외로 ①저장 막힌 창에서도 동작 ⑤주소·의견함 금지만 지킨다). 다시 누르면 해제.
3. 펼침 상한 4(Wave 2) — 늘리려면 로드맵 먼저. `ROLE_SECTION_LAYOUT.order` 는 11칸 전부 한 번씩(빠지면 카드가 조용히 사라짐), 가드 `sectionCards.test.ts`.
4. 카드 객체 동일성: 역할마다 `ROLE_PLANS` 를 한 번만 만든다 — 새 객체를 매번 만들면 자료 도착 때마다 사람이 연 카드가 접힌다(`sectionCards.ts:166`).
5. 결정 0020 종이: 접힌 카드 본문은 `hidden` 으로 DOM 에 남긴다 · `print-color-adjust: exact` 유지 · 긴 카드 창/휴대폰 세 줄/13px/44px 는 `@media screen` 에만 · 접힌 입구의 지도는 안 그려서 종이에도 없다 · 중개사 종이 머리 사무소 상자는 중개사일 때만.
6. 결정 0019: 주소 꼴 `/?sgg=&bld=` 고정, 라우터·rewrite 도입 금지(지도 파일 1.1MB 가 첫 화면으로 바뀔 위험), `vercel.json` rewrites 0 유지 — 서버 조각은 `middleware.ts`→`api/building.ts` 하나뿐(되돌리기 = middleware 삭제). 바꾸려면 새 결정.
7. S1 입구: 위 덩어리는 `hidden` 으로 숨기기만(언마운트 금지 — 검색어·구 이름 되살리기가 산다), 지도만 접힌 동안 안 그림, 누른 상권·목록은 App 이 쥠(`districtMapPick.ts`).
8. 확정 설계 9·10, 절대 규칙 2·3·4·5: 금지어, 근거·표본 병기, 층 정수, 임대 추정 안 함(상권 평균 그림은 건물 층 막대와 다른 색·다른 자리).
9. E2E 57개(`grep -cE "^\s*test\(" e2e/floor-stack.spec.ts` = 57, 넓은 화면 + Pixel 7 412px 두 벌 = 110회 [정정(맹점 검사 2026-10-17): 57×2 = 114회])가 전제하는 것: `.role` 안 단추 이름(투자자·창업자·중개사 `exact`), `unfoldEntry`(「다른 건물 찾기」·「상권 지도 보기」·「나는 …」), `.card__summary`, `.floor__row`, 44px(AZ)·13px 글자(AZ)·가로 넘침 0(BC)·긴 카드 창(BB)·접힌 입구(AY~BA). 하단 바·탭을 넣으면 `.entrybar` 선택자와 AZ 의 44px/13px 목록(`styles.css:4031`)에 이름을 더해야 한다.
10. 새 단추는 44px 이름 목록에, 새 글칸은 처음부터 13px 이상. `viewport` 에서 줌을 막지 않는다(지금 막지 않음 — 바꾸지 말 것).
11. 지도: 카카오 도메인 등록(새 배포 주소) · 지도를 그림으로 저장·재배포 금지(인쇄는 브라우저 기본 기능만).

## 8. "없다" 단정의 근거 (실행한 명령 → 결과)
- 하단 바·시트·탭: `grep -rnE "tabbar|bottom ?bar|bottomsheet|bottom-sheet|drawer|role=\"tab\"|tablist" src --include=*.css --include=*.tsx --include=*.ts` (시험 제외) → **0건**
- 붙는 바: `grep -rnE "position: *sticky" src ...` → **0건** · `position: *fixed` → `styles.css:381` 한 줄(`.modal__back`) · `safe-area` → 0건 · `[0-9]dvh|[0-9]vh` → 0건
- 서비스워커: `grep -rn "serviceWorker\|service-worker\|workbox\|vite-plugin-pwa" src index.html package.json vite.config.* public` → **0건** (manifest 는 있음)
- 라우터: `grep -cE "react-router|wouter|tanstack/react-router" package.json` → **0**
- 클러스터·최소 배율: `grep -n "Cluster\|MarkerClusterer\|minLevel\|maxLevel" src/components/DistrictMap.tsx` → 0건 (`padding` 도 0건, `setBounds` 인자는 상자 하나)
- 역할을 직접 읽는 다른 컴포넌트: 위 `grep -rn "viewerRole\|role ===\|ROLE_SECTION\|ViewerRole" src` 결과 파일은 App·FloorStack·RolePicker·sectionCards·viewerRoleStore 뿐
- 확인하지 않은 것: 운영 라이브 화면(조사는 코드만) · 카카오 `setBounds` 기본 패딩 값(공식 문서 미확인 — "인자를 안 준다"까지만 사실) · 11~16px 는 어림.
