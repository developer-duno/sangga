# sangga — 코드베이스 구조

> 상업용 부동산을 층별·업종별로 공간분석하는 플랫폼. 필지(PNU)→건물→호실 3층 구조.
> 프론트 = React 19 + Vite(SPA 1화면), 백엔드 = Supabase(PostgREST+RPC) 단독(서버 코드 없음),
> 수집 = 로컬 파이썬(표준 라이브러리 + requests/dotenv, pandas·numpy 없음).
> 자동 생성: 2026-08-15 (Explore 에이전트 2개 실측 종합)

## 디렉토리 트리

```
src/                     # 프론트 (라우터·상태관리 라이브러리 없음 — useState/useEffect + 단일 styles.css)
├── main.tsx             # 진입점: #root 마운트 + styles.css
├── App.tsx              # 유일한 화면·유일한 상태 소유자 (selected/sigungu/sigunguName → 4개 자식 배분)
├── types.ts             # DB 응답 타입 11종 단일 소스 (e2e/fixtures.ts 도 여기서 import)
├── components/          # 화면 조각 4개 + 각 .test.tsx (hooks/·constants/ 폴더는 없음)
│   ├── RegionPicker.tsx     # 시도→구 2단 칩. 목록 진실 = 서버 RPC list_open_sigungu()
│   ├── BuildingSearch.tsx   # 검색 폼+결과. search_buildings / 0건이면 search_scope 재질의
│   ├── DistrictMap.tsx      # 카카오맵 + 상권 폴리곤 (정적 /districts.geojson — Supabase 안 씀)
│   └── FloorStack.tsx       # 시그니처 화면: 5개 질의를 독립 상태로 (하나 실패해도 나머지 렌더)
└── lib/                 # 부수효과·순수함수 계층 (components 를 절대 import 안 함)
    ├── supabase.ts      # 클라이언트 1개 + 뷰/RPC 이름 상수 (사실상 constants 레이어)
    ├── regions.ts       # 시도 16개 정적 표 — 코드→이름표기 전용 (열림 진실은 서버 list_open_sigungu())
    ├── districts.ts     # districts.geojson 1회 fetch + 프라미스 캐시 (실패는 캐시 안 함)
    ├── geo.ts           # 순수 기하: ray casting 점포함·bounds·GeoJSON↔카카오 좌표 뒤집기
    └── format.ts        # 순수 표시 변환 (층·면적·금액·오류 문구)

scripts/                 # 데이터 파이프라인 전부 (수동 실행 — 자동화는 감시 워크플로우뿐)
├── dbx.py               # psql 감싸기 (SANGGA_DATABASE_URL) — DDL·EXPLAIN·matview 전용 통로
├── post_load.py         # ★ 모든 적재 후 필수: VACUUM+matview 3종 갱신+신선도·anon 노출 점검(--check)
├── backup_raw.py        # data/raw → F:\sangga-raw-backup (robocopy /E + SHA-256 검증)
├── normalize_floor.py   # 층 정규화 정본 (지상n=n/지하n=-n/옥탑=99/불명=None) — 재구현 금지
├── check_new_sangkwon_quarter.py    # 분기 스냅샷 감시 (기준선 상수는 적재 후 사람이 올림)
├── check_district_source_update.py  # 상권 원천(서울·소진공) 수정일 감시
├── build_district_geojson.py        # district → public/districts.geojson (단순화 0.76MB)
├── build_rone_map.py / load_rone_map.py  # district↔R-ONE 매핑 후보 생성 / seed 적재(관문 3종)
├── seeds/               # district_rone_map.csv (사람이 확정한 매핑 정본)
└── collectors/          # 원천별 수집기·적재기 17개 (fetch_/collect_ = 받기, load_/convert_ = 적재)
    ├── collect_transactions.py / load_transactions.py    # 실거래 (PNU 조립·tx_id 해시 멱등)
    ├── fetch_bldrgst_bulk.py / convert_bldrgst_bulk.py   # 건축HUB 일괄 zip → API 동형 JSONL
    ├── collect_building_ledger.py / load_building_ledger.py  # 건축물대장 → 3층 생성 (최대 적재기)
    ├── load_sangkwon_snapshot.py                         # 상권정보 CSV → parcel+unit_business
    ├── collect_rone.py / load_rone.py                    # R-ONE 임대동향 → rent_stat
    ├── collect_vworld_land.py / load_vworld_land.py / load_vworld_bulk.py  # 토지특성 → parcel
    └── fetch_seoul_district.py / load_seoul_district.py / fetch_sbiz_district.py / load_sbiz_district.py  # 상권 경계

supabase/
├── schema.sql           # 정본 1,560줄 (라이브 반영본 — 마이그레이션과 드리프트 가드로 동기)
└── migrations/          # 날짜 파일명 26개, 라이브 적용 순서 그대로

tests/                   # pytest 29파일 1,356개 — collector/스크립트 1:1 + 드리프트 가드
e2e/                     # playwright 11개 (Supabase 전량 가로채기, E2E_PORT 로 포트 회피)
.github/workflows/       # ci.yml (test+web 2 job) + 감시 2종 (월 09:00/09:30 KST, 실패해도 이슈)
docs/                    # 상세계획·알려진한계(조사 전 필독)·PROGRESS + decisions/0001~0012
```

## 핵심 모듈 역할

| 모듈 | 책임 (1줄) |
|---|---|
| `src/App.tsx` | 상태 3개 소유·배분. 구 변경 시 `key` 로 BuildingSearch 강제 재마운트(검색 초기화) |
| `src/components/FloorStack.tsx` | 층 스택 + 속한 상권 + 실거래 섹션. 5개 질의 독립 실패 허용 |
| `src/lib/supabase.ts` | anon 클라이언트(persistSession:false). 원본 표는 닫혀 있고 함수·뷰만 접근 |
| `scripts/post_load.py` | "했다고 믿지 않고 다시 잰다" — 등식 검증·geojson 대조·24개월 창·anon 허용목록 |
| `scripts/collectors/load_transactions.py` | 실거래 적재: PNU 조립(집합만 가능)·층 정규화·unit_price 는 DB 생성 컬럼 |
| `supabase/schema.sql` | 3층 구조 + district(공간 조인만) + transaction(FK 없이 sigungu/pnu 로 연결) |

## 의존성 / 데이터 흐름

- **프론트 단방향**: `main → App → components → lib → types` (역방향 import 0건, 컴포넌트끼리 import 0건).
  외부 경계 3개 = Supabase REST · 정적 geojson · 카카오맵 스크립트.
- **DB 3층**: `parcel(pnu) ← building(bld_id) ← building_floor/unit`. `unit_business`·`transaction` 은
  FK 없이 (pnu, floor)·(sigungu, floor) 로 느슨하게 붙는다. `district` 는 `st_contains` 공간 조인뿐.
  건물 좌표는 **필지(parcel.geom)에서** 나온다.
- **대표 시나리오** (검색→층 스택): RegionPicker `list_open_sigungu()` → 구 선택 → BuildingSearch
  `search_buildings(q, lim, sigungu)` (0건 시 `search_scope`) → 선택 → FloorStack 이 5개 질의 동시 발사:
  `v_coverage_stats`·`v_floor_stack`·`list_building_districts(bld_id)`·`list_parcel_transactions(pnu)`·
  `get_sigungu_tx_stats(sigungu)` → 층 막대(면적 비례) + 실거래 섹션 렌더.
- **데이터 파이프라인** (예: 상권정보 분기): 감시 워크플로우가 이슈 → 사람이 zip 받기
  (`download_sangkwon_history.py`) → `backup_raw.py` → `load_sangkwon_snapshot.py` →
  **`post_load.py`(필수)** → 감시 기준선 상수를 사람이 올림.

## 진입점

- 빌드: `pnpm build` (tsc -b && vite build)
- 실행: `pnpm dev` (http://localhost:5173)
- 테스트: `pnpm test`(vitest 145) / `python -m pytest tests/ -q`(1,356) / `E2E_PORT=5273 pnpm test:e2e`(7)
- 린트: `pnpm exec oxlint` / `python -m ruff check scripts/ tests/`

---
이 파일은 자동 생성됨. 코드 구조가 크게 바뀌면 갱신 필요.
