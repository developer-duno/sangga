# sangga — 코드베이스 구조

> 상업용 부동산을 층별·업종별로 공간분석하는 플랫폼. 필지(PNU)→건물→호실 3층 구조.
> 프론트 = React 19 + Vite(SPA 1화면), 백엔드 = Supabase(PostgREST+RPC) 단독(서버 코드 없음),
> 수집 = 로컬 파이썬(표준 라이브러리 + requests/dotenv, pandas·numpy 없음).
> 배포 = Vercel(`https://sangga-one.vercel.app`, GitHub 연결 — main push 가 곧 배포).
> 실측 갱신: 2026-08-25 (감사 배치)

## 디렉토리 트리

```
src/                     # 프론트 (라우터·상태관리 라이브러리 없음 — useState/useEffect + 단일 styles.css)
├── main.tsx             # 진입점: #root 마운트 + styles.css
├── App.tsx              # 유일한 화면·유일한 상태 소유자. 주소(?sgg=&bld=)를 첫 그림에만 읽고,
│                         #   그 뒤론 화면 상태가 주인 → 주소는 replaceState 로 따라 적히기만 함
├── types.ts             # DB 응답 타입 단일 소스 (e2e/fixtures.ts 도 여기서 import)
├── components/          # 화면 조각 13개 + 각 .test.tsx (hooks/·constants/ 폴더는 없음)
│   ├── RegionPicker.tsx     # 시도→구 2단 칩. 목록 진실 = 서버 RPC list_open_sigungu()
│   ├── BuildingSearch.tsx   # 검색 폼+결과. search_buildings / 0건이면 search_scope 재질의
│   ├── DistrictMap.tsx      # 카카오맵 + 상권 폴리곤 (정적 /districts.geojson — Supabase 안 씀)
│   ├── FloorStack.tsx       # 시그니처 화면: 층 스택+속한 상권+실거래+참고시세 등 6개 질의를
│   │                         #   독립 상태로 발사 (하나 실패해도 나머지 렌더). 카드 다섯 장의 뼈대
│   ├── SectionCard.tsx      # 카드 공통 틀(로드맵 Wave 2) — 접어도 요약 한 줄은 항상 보임,
│   │                         #   본문은 hidden 으로 감춰 둘 뿐 DOM 에서 안 뺌(인쇄가 되살릴 수 있게)
│   ├── IndustryMixSection.tsx  # 둘레의 업종 분포(결정 0014) — 상권/반경 두 스코프, 자체 질의 보유
│   ├── PriceBandSection.tsx    # 참고 매매 시세 밴드(Stage B·결정 0013) — FloorStack 안에서 렌더
│   ├── ErrorBoundary.tsx    # 하얀 화면 안전망(결정 0016) — 클래스 컴포넌트(리액트가 훅으로
│   │                         #   오류를 못 잡게 해서). key 로 구/건물 바뀔 때마다 그물을 새로 침
│   ├── AppFooter.tsx        # 화면 맨 아래 — 이 자료를 어떻게 믿을지 + FeedbackBox 감쌈
│   ├── FeedbackBox.tsx      # 익명 의견함(결정 0016) — 이름·연락처 안 받음, submit_feedback 호출
│   ├── ShareButton.tsx      # 지금 화면 주소 복사 버튼(결정 0019, 휴대폰 대응)
│   ├── PrintButton.tsx      # 종이로 뽑기 버튼(결정 0020) — window.print() 호출, 인쇄의 유일한 길 아님
│   └── PrintHeader.tsx      # 종이에만 나오는 머리글(건물명·주소·뽑은시각·원본주소) — @media print 전용
└── lib/                 # 부수효과·순수함수 계층 (components 를 절대 import 안 함)
    ├── supabase.ts      # 클라이언트 1개 생성 (env 읽는 유일한 곳 — 그래서 흉내내기 까다로움)
    ├── appConstants.ts  # 서버 함수/뷰 이름·짝수(TX_LIST_CAP 등) 상수만 모은 순수 모듈
    │                     #   (supabase.ts 와 분리한 이유: 이건 env 를 안 봐서 테스트가 흉내 안 내도 됨)
    ├── regions.ts       # 시도 정적 표 — 코드→이름표기 전용 (열림 진실은 서버 list_open_sigungu())
    ├── districts.ts     # districts.geojson 1회 fetch + 프라미스 캐시 (실패는 캐시 안 함)
    ├── geo.ts           # 순수 기하: ray casting 점포함·bounds·GeoJSON↔카카오 좌표 뒤집기
    ├── format.ts        # 순수 표시 변환(층·면적·금액·오류 문구) — 계산은 안 함(곱셈 등은 옆 파일로)
    ├── industryMix.ts   # 업종 분포 순수 계산(결정 0014) — IndustryMixSection 의 계산 부분만 분리
    ├── priceBand.ts      # 참고 시세 밴드 순수 계산·어휘(결정 0013) — 단가×면적 곱셈은 여기서만
    ├── sectionCards.ts  # 카드 배치 정본 SECTION_PLAN(제목·역할태그·기본펼침) + 펼침 상한 4
    ├── urlState.ts      # 주소(?sgg=&bld=) 조립/파싱 순수 부품(결정 0019) — 물음표 방식, rewrite 불필요
    ├── restoreBuilding.ts  # 링크로 들어온 건물을 v_floor_stack 행에서 되살림(검색 안 거침)
    ├── printStamp.ts    # 종이에 적을 "언제 뽑았나" 문구 생성(결정 0020) — toLocaleString 지역차 회피
    └── feedback.ts       # 의견/오류 둘 다 submit_feedback 하나로 보냄 — 절대 예외를 밖으로 안 던짐

scripts/                 # 데이터 파이프라인 전부 (수동 실행 — 자동화는 감시 워크플로우뿐)
├── dbx.py               # psql 감싸기 (SANGGA_DATABASE_URL) — DDL·EXPLAIN·matview 전용 통로
├── post_load.py         # ★ 모든 적재 후 필수: VACUUM+matview 3종 갱신+신선도 점검
├── post_load.py --check # 낡음 여부 + anon 권한(읽기/쓰기) 노출 점검 — post_load 본체엔 안 들어 있음
├── backup_raw.py        # data/raw → F:\sangga-raw-backup (robocopy /E + SHA-256 검증)
├── normalize_floor.py   # 층 정규화 정본 (지상n=n/지하n=-n/옥탑=99/불명=None) — 재구현 금지
├── floor_coverage_report.py         # normalize_floor() 전수 적용 리포트(층정보 원본 텍스트 대상)
├── check_data_quality.py            # 상권정보 분기 스냅샷 CSV 데이터 품질 검증(결측률 등)
├── check_new_sangkwon_quarter.py    # 분기 스냅샷 감시 (기준선 상수는 적재 후 사람이 올림)
├── check_district_source_update.py  # 상권 원천(서울·소진공) 수정일 감시
├── check_watch_heartbeat.py         # 감시 워크플로우 4종이 서로의 최근 성공 시각을 확인(전멸 대비)
├── check_live_health.py             # 라이브(첫 화면+JS 번들+상권 지도)가 밖에서 두드려 서 있나 확인
├── feedback_digest.py               # 의견함 주간 알림 — 숫자만(get_feedback_stats), 본문은 안 뽑음
├── setup_git_hooks.py               # main 잠금(로컬 훅+GitHub 규칙) 새 컴퓨터에서 1회 세팅/확인
├── download_sangkwon_history.py     # 상권정보 "주기성 과거 데이터" 분기별 zip 일괄 다운로드
├── make_env_local.py                # .env → .env.local (브라우저용 공개키만 골라 씀)
├── backtest_price.py                # Stage B 백테스트 성적표(docs/backtest/) 재생성 — DB 읽기 전용
├── load_price_gate.py               # 통과구.csv → price_gate_sigungu 적재(관문 3종, 걸리면 롤백)
├── build_district_geojson.py        # district → public/districts.geojson (단순화)
├── build_rone_map.py / load_rone_map.py  # district↔R-ONE 매핑 후보 생성 / seed 적재(관문 3종)
├── seeds/               # district_rone_map.csv (사람이 확정한 매핑 정본)
└── collectors/          # 원천별 수집기·적재기 17개 (fetch_/collect_ = 받기, load_/convert_ = 적재)
    ├── collect_transactions.py / load_transactions.py    # 실거래 (PNU 조립·tx_id 해시 멱등)
    ├── fetch_bldrgst_bulk.py / convert_bldrgst_bulk.py   # 건축HUB 일괄 zip → API 동형 JSONL
    ├── collect_building_ledger.py / load_building_ledger.py  # 건축물대장 → 3층 생성 (최대 적재기)
    ├── load_sangkwon_snapshot.py                         # 상권정보 CSV → parcel+unit_business
    ├── collect_rone.py / load_rone.py                    # R-ONE 임대동향 → rent_stat
    ├── collect_vworld_land.py / load_vworld_land.py / load_vworld_bulk.py  # 토지특성 → parcel
    ├── fetch_seoul_district.py / load_seoul_district.py  # 서울 상권영역(SHP) → district
    ├── fetch_sbiz_district.py / load_sbiz_district.py    # 대전 주요상권(CSV) → district
    └── load_bjd_code.py                                  # 법정동코드 전체자료(code.go.kr) 적재

supabase/
├── schema.sql           # 정본 2,809줄 (라이브 반영본 — 마이그레이션과 드리프트 가드로 동기)
└── migrations/          # 날짜 파일명 38개, 라이브 적용 순서 그대로

tests/                   # pytest 41파일 1,840개 — collector/스크립트 1:1 + 드리프트 가드
e2e/                     # playwright 19개(2파일: fixtures.ts, floor-stack.spec.ts). 넓은화면(chromium)·
│                         #   휴대폰(mobile, Pixel 7) 2벌로 돌아 실행은 38회. E2E_PORT 로 포트 회피
.github/workflows/       # ci.yml(test+web) + 감시 4종: district-source-watch·feedback-digest·
│                         #   live-health-watch·sangkwon-quarterly-watch (전부 하트비트로 서로 감시)
docs/                    # 상세계획·알려진한계(조사 전 필독)·PROGRESS·ROADMAP + decisions/0001~0020 (20개)
```

## 핵심 모듈 역할

| 모듈 | 책임 (1줄) |
|---|---|
| `src/App.tsx` | 상태 6개(주소로 연 값·selected·sigungu·sigunguName·restoring·restoreFailed) 소유·배분. 구 변경 시 `key` 로 BuildingSearch 강제 재마운트(검색 초기화), 지도·층별 화면은 각각 `key` 를 준 `ErrorBoundary` 로 감쌈 |
| `src/components/FloorStack.tsx` | 층 스택 + 속한 상권 + 실거래 + 참고 시세 + 업종 분포 섹션. 질의 6개 독립 실패 허용, 카드 다섯 장(`SectionCard`)의 뼈대 |
| `src/components/SectionCard.tsx` | 다섯 카드 공통 틀 — 첫 화면 펼침 상한 4장(`sectionCards.ts` 의 `SECTION_PLAN` 이 정본), 접힌 카드도 본문은 그려 두고 `hidden` 만 해서 인쇄가 되살릴 수 있게 함 |
| `src/lib/supabase.ts` | anon 클라이언트(persistSession:false). 원본 표는 닫혀 있고 함수·뷰만 접근 |
| `src/lib/appConstants.ts` | 서버 함수/뷰 이름과 짝수(TX_LIST_CAP·FEEDBACK_MAX_LEN 등)만 모은 순수 모듈 — env 를 안 봐서 테스트가 흉내낼 필요 없음 |
| `src/lib/urlState.ts` | 화면 상태 ↔ `?sgg=&bld=` 주소 변환 순수 부품(결정 0019). 되살리는 중엔 절대 안 씀(링크 자멸 방지) |
| `scripts/post_load.py` | "했다고 믿지 않고 다시 잰다" — 등식 검증·geojson 대조·24개월 창·anon 허용목록(`--check`) |
| `scripts/collectors/load_transactions.py` | 실거래 적재: PNU 조립(집합만 가능)·층 정규화·unit_price 는 DB 생성 컬럼 |
| `supabase/schema.sql` | 3층 구조 + district(공간 조인만) + transaction(FK 없이 sigungu/pnu 로 연결) + app_feedback(넣기 전용 함수 1개만 열림) |

## 의존성 / 데이터 흐름

- **프론트 단방향**: `main → App → components → lib → types` (역방향 import 0건, 컴포넌트끼리 import 는
  `FloorStack → SectionCard/IndustryMixSection/PriceBandSection`, `AppFooter → FeedbackBox` 처럼
  같은 계층 안 조립만 있고 밖으로 새지 않는다). 외부 경계 3개 = Supabase REST · 정적 geojson · 카카오맵 스크립트.
- **DB 3층**: `parcel(pnu) ← building(bld_id) ← building_floor/unit`. `unit_business`·`transaction` 은
  FK 없이 (pnu, floor)·(sigungu, floor) 로 느슨하게 붙는다. `district` 는 `st_contains` 공간 조인뿐.
  건물 좌표는 **필지(parcel.geom, `st_y/st_x`로 뽑음)에서** 나온다. `app_feedback` 은 anon 에게
  통째로 닫혀 있고 `submit_feedback()` 넣기 전용 함수 하나만 열려 있다(읽는 함수는 없음).
- **대표 시나리오** (검색→층 스택→가지고 나가기): 첫 그림에서 주소(`?sgg=&bld=`)가 있으면
  `restoreBuilding.ts` 로 검색 없이 건물을 되살리고, 없으면 RegionPicker `list_open_sigungu()` →
  구 선택 → BuildingSearch `search_buildings(q, lim, sigungu)`(0건 시 `search_scope`) → 선택 →
  FloorStack 이 6개 질의 동시 발사: `v_coverage_stats`·`v_floor_stack`·`list_building_districts(bld_id)`·
  `list_parcel_transactions(pnu)`·`get_sigungu_tx_stats(sigungu)`·`list_price_bands(p_pnu)` →
  층 막대+실거래+참고시세 섹션 렌더, `IndustryMixSection` 이 `list_industry_mix(p_pnu)` 를 따로 발사.
  건물을 고르면 화면 상태가 `urlState.ts` 로 주소에 따라 적히고(되살리는 중엔 안 적음),
  `ShareButton`(주소 복사)·`PrintButton`(브라우저 인쇄, `@media print` 로 조종장치 숨김+`PrintHeader` 노출)
  로 가지고 나갈 수 있다. `AppFooter`→`FeedbackBox` 가 보던 지역·건물을 함께 실어 익명 의견을 보낸다.
- **데이터 파이프라인** (예: 상권정보 분기): 감시 워크플로우가 이슈 → 사람이 zip 받기
  (`download_sangkwon_history.py`) → `backup_raw.py` → `load_sangkwon_snapshot.py` →
  **`post_load.py`(필수)** → 감시 기준선 상수를 사람이 올림.

## 진입점

- 빌드: `pnpm build` (tsc -b && vite build)
- 실행: `pnpm dev` (http://localhost:5173)
- 테스트: `pnpm test`(vitest 411, 21파일) / `python -m pytest tests/ -q`(1,840, 41파일) /
  `E2E_PORT=5273 pnpm test:e2e`(19개 × 2벌 = 38회)
- 린트: `pnpm exec oxlint` / `python -m ruff check scripts/ tests/`
- 배포: `main` push → Vercel 자동 배포(`https://sangga-one.vercel.app`). `main` 은 잠겨 있어
  가지→PR→검사(`test`·`web`) 통과→머지 순서로만 들어간다(결정 0018).

---
이 파일은 실측 기반으로 갱신됨. 코드 구조가 크게 바뀌면 다시 갱신 필요.
