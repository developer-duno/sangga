# 상가 공간분석 플랫폼

> 상업용 부동산을 **층별·업종별**로 공간분석하고 매매/임대 참고시세를 비교하는 플랫폼.
> 필지(PNU) → 건물 → 호실(층+호) 3층 구조. React 19 + Vercel Serverless + Supabase PostgreSQL(별도 프로젝트).

## 즉시 알아야 할 것

- **사용자는 비개발자.** 쉬운 말 원칙. 코드는 복사-붙여넣기로 바로 도는 완전한 형태로. 조각 코드 금지
- **알려진 한계** — `docs/알려진한계.md` ★ **조사 전에 먼저 읽을 것.** 여기 있는 건 이미 아는 것이라 다시 조사하지 않는다(매 세션 같은 걸 재발견하는 낭비를 막는 기준선)
- **상세 계획** — `docs/상세계획.md` (데이터 소스·분석 로직·검증 설계·로드맵 전부)
- **DB 스키마** — `supabase/schema.sql`
- **부동산 데이터 처리 규격** — `budongsan-data` 스킬 참조 (PNU 조립·층 정규화·API 카탈로그)
- **현재 Phase** — **Phase 1 통과**(2026-08-09, 조인률 95.92%/96.86%) → 1단계 서비스범위(서울+대전) 확장 완료(결정 0006) → **Phase 2 진행 중**(층별 스택 화면, 눈 검증 2/10). `docs/PROGRESS.md` 참조

### 🔴 운영 5계명 (매 세션 확인 — 어기면 복구 불가하거나 조용히 깨진다)

| | 규칙 | 어기면 |
|---|---|---|
| 💾 | **백업은 자동이 아니다.** 새 분기 zip을 받았거나 대량 수집을 마쳤으면 `python scripts/backup_raw.py`를 **직접** 돌린다 | 포털에서 과거분이 내려가면 **재수집 불가**(절대 규칙 6). 건축HUB 일괄 파일도 **최근 3개월치만** 남는다 |
| 🔎 | **자료를 적재했으면 검색 요약표를 갱신한다.** `python scripts/dbx.py -c "refresh materialized view concurrently mv_search_parcel;"` + `analyze` | 새로 넣은 건물이 **검색에 안 나온다**. 에러가 아니라 조용한 누락이라 아무도 모른다 |
| 📦 | **패키지 매니저는 `pnpm`.** `npm`으로 돌리지 않는다 (`pnpm-lock.yaml`·CI 기준) | 락파일이 갈라져 CI와 로컬이 다른 의존성을 쓴다 |
| 🔑 | **키는 `.env`.** 브라우저용 공개키는 `.env.local` — 손으로 만들지 말고 `python scripts/make_env_local.py` | 손으로 만들다 **서비스키를 브라우저에 노출**하는 사고. 이 스크립트는 공개키만 골라 쓴다 |
| 🐍 | **파이썬 명령은 프로젝트 루트에서.** `cd D:\sangga` 후 실행 | 상대경로(`data/raw/...`)가 어긋나 "파일 없음"으로 조용히 0건 처리된다 |

> ⚙️ **수집·적재·점검 명령은 Claude가 직접 돌린다** (사장님께 넘기지 않는다). 사장님 손이
> 꼭 필요한 것은 **Supabase 대시보드 SQL Editor**(마이그레이션·`ANALYZE`)와 **외부 계정 신청**뿐이다.

## 절대 규칙

### 1. 네이버·다음 부동산 크롤링 금지
이용약관 위반 + DB제작자 권리. 크롤링 코드는 어떤 형태로도 작성하지 않는다.
상가는 공공데이터만으로 완결된다. 호가가 필요하면 대안을 제시할 것.

### 2. "적정가격" 표현 금지
감정평가는 감정평가사 독점 업무 영역. 변수명·UI 문구·리포트 어디에도 쓰지 않는다.

| 금지 | 대체 |
|---|---|
| 적정가격, 적정가, 평가액, 감정가, 가치평가 | 추정 시세, 참고 시세, 시세 밴드, AI 추정값 |

### 3. 신뢰도 배지 필수
추정값 출력 시 항상 근거 레벨 + 표본 수 병기.
```
✅ "3.2억 ~ 3.8억 (반경 500m 동일층 실거래 7건 기준)"
❌ "3.5억"
```

### 4. 층 표기는 정수
```
지상 n층 = n / 지하 n층 = -n / 옥탑 = 99 / 불명 = NULL
```
**0을 쓰지 말 것.** 지하와 결측이 섞이면 집계가 오염된다. DB에 CHECK 제약 걸려 있음.

### 5. 상가 임대료 실거래는 존재하지 않는다
신고 의무가 없다. 임대료를 "조회"하는 코드를 쓰지 말고 부동산원 수익률·층별효용비율로 **역산**하며, 추정임을 반드시 명시한다.

### 6. 분기 스냅샷 관리
포털 "주기성 과거 데이터"에 과거 분기 파일이 제공된다(2026-08-07 실측 48개 — §3.4). 단 유지 보장이 없으므로 **과거분은 확보 즉시 로컬 보관**하고, **매 분기 신규 수집도 놓치지 말 것.** 공실 이력·점포 생존기간이 전부 여기서 나온다. 대화 중 관련 맥락이 나오면 리마인드한다.

## 확정 설계 (다시 논의하지 말 것)

1. **섹터** — 용도 4축(상업/업무/산업물류/토지) × 거래단위 3축(구분소유/통건물/필지). 네이버 분류 미사용
2. **3층 구조** — 필지(PNU) → 건물 → 호실. 아파트 2층으로는 상가를 못 담음
3. **조인 키** — PNU 19자리. 상권정보에 이미 있으므로 마스터로 사용
4. **매매 실측, 임대 추정**
5. **비교는 거리가 아니라 유사도** — 상권 8차원 벡터 코사인 유사도
6. **조회형 먼저, 탐색형 나중** — 추정 검증 전 추천 금지
7. **Supabase 별도 프로젝트** — 기존 mibunyang DB와 격리
8. **토지·상권 원천 데이터는 한 서버, 서비스는 분리** — 회원·결제 등 서비스 고유 상태는 생기는 시점에 그 서비스 소유로 분리. 편입 기준 = "PNU 필지 마스터를 쓰는가"(mibunyang 격리 유지). `docs/decisions/0003-토지상권-한서버-서비스분리.md`
9. **필지·점포는 전국, 건물·화면 오픈은 서울+대전 — 서로 다른 두 축이다** — 결정 0005의 `[A]`(parcel·상권정보 전국 시드)와 결정 0006(사용자가 실제로 볼 수 있는 지역)은 **별개 축**이라 헷갈리면 안 된다. `[A]`는 2026-08-13 전국 완주(`parcel` 1,119,149행·`unit_business` 2,772,484행) — 이건 "데이터가 어디까지 들어왔나"다. 0006은 "건물·화면을 여는 지역은 서울+대전뿐"이다 — 이건 "사용자가 어디를 볼 수 있나"다(건물은 아직 서울·대전 30개 구 242,631동뿐, 전국 필지 위에 얹힌 상태). **화면에는 자료가 있는 지역만 보여준다**(2026-08-13 개정 — 누를 수 없는 칩을 늘어놓지 않는다). 그 목록의 진실은 **서버(`list_open_sigungu()`)뿐**이라 자료가 들어오면 화면이 저절로 따라온다. ⚠️ **열린 지역의 진실은 이제 서버**(`list_open_sigungu()` → `mv_open_sigungu`)다 — 예전엔 `src/lib/regions.ts` 였는데, 그러면 자료가 늘 때 화면 문구만 낡는 드리프트가 난다(2026-08-13 2차 검증에서 실제로 발견). `regions.ts` 는 짧은 이름표(서울/대전)를 붙이는 데만 쓴다. 검색은 고른 구 안에서만 한다(동까지는 안 좁힘 — 상권이 행정동 경계를 넘어 걸치므로). `docs/decisions/0005-전국확장-실행순서와-선행조건.md`·`docs/decisions/0006-1단계-서비스범위-서울대전.md`
10. **건축물대장은 API가 아니라 건축HUB 일괄 파일로 받는다** — 전국 3종 4.4GB를 5분에 받는다(로그인 불필요, 월 갱신·누적분). API 전국 수집은 211일이라 대비책으로만 남긴다. `docs/decisions/0005`

## 데이터 소스 우선순위

| # | 데이터 | 포털 ID |
|---|---|---|
| 1 | 소상공인 상권정보 (심장) | 15012005 / 15083033 |
| 2 | 상업업무용 실거래가 | 15126463 |
| 3 | 건축물대장 층별개요 | 건축HUB |
| 4 | 부동산원 임대동향 | 15134761 |
| 5 | 토지특성 (도로접면) — 구 NSDI, 브이월드로 통합 | 브이월드 / 15048121 |
| 6 | 서울 상권분석 (서울만 풀버전) | 서울 열린데이터광장 |

## 아키텍처

```
constants → scoring → theme → components → hooks → App   (단방향)
```

| 레이어 | 기술 |
|---|---|
| 프론트 | React 19 + Vite, 카카오맵 + deck.gl |
| API | Vercel Serverless |
| DB | Supabase PostgreSQL + PostGIS (**별도 프로젝트**) |
| 수집 | ⬜ **여전히 로컬 수동 실행이다** — 받기·적재·백업 전부 사람 손. 다만 **놓치는 것만은 막아 뒀다**: `sangkwon-quarterly-watch.yml`이 매주 포털을 확인해 새 분기가 뜨면 이슈를 자동으로 연다(비밀값 0개). 적재 후 `scripts/check_new_sangkwon_quarter.py`의 `LATEST_KNOWN_QUARTER`를 **사람이 올려야** 다음 분기를 감지한다(절대 규칙 6) |
| 테스트 | 파이썬 **pytest 1,046개** + 프론트 **vitest 82개**(jsdom + @testing-library/react) + **E2E playwright 6개**(`e2e/floor-stack.spec.ts` — 검색→선택→층 스택, 너무 넓은 검색 안내창). CI가 셋 다 돌린다(`pnpm test:e2e`, chromium). ⚠️ **로컬에서 앞의 둘만 돌리면 E2E 실패를 못 본다** — 화면 문구를 건드렸으면 `pnpm test:e2e`도 |

**성능 원칙**: 상권(수천 개)은 사전계산 정적 JSON, 호실(수백만)은 Supabase 쿼리.
정적 JSON 폴백을 호실에는 두지 않는다.

## 수집 규칙

- **이어받기 필수** — `collect_progress` 테이블의 `pending`만 처리. 일 예산 소진 시 안전 종료
- **API 한도** — 공공데이터포털은 API별 일 10,000건(개발계정). 활용신청 추가 시 별도 한도
- **호출 3단계** — 파일럿(240) → 최근 24개월 전국(6,000) → 과거 백필(54,000)
- **raw는 절대 덮어쓰지 않는다** — 정제 로직은 재실행 가능하지만 raw는 복구 불가
- 수집기마다 테스트 파일 1:1

## 검증 규칙

- **시간 분할 백테스트** (랜덤 분할 금지 — 미래로 과거를 맞히면 성적이 부풀려짐)
- **지역별로 따로 측정** — 상가는 표본이 적어 전국 평균은 무의미
- 오차율이 기준선 초과 시 그 지역은 시세 미표시, "표본 부족"만 노출
- 데이터 신뢰등급 A(실측)/B(공식표본)/C(파생추정)/D(간접추론) — **C·D는 화면에서 시각적 구분**

## 법률 확인 필요

변호사 검토 권장: "적정가격" 표현 범위, 상호명 노출(특히 폐업 추정 표시), 상권정보 상업적 재가공 범위.
상가건물임대차보호법 2026.5.12 시행 개정분 반영 필요.

## 명령

**패키지 매니저는 `pnpm`이다** (`pnpm-lock.yaml`·CI 기준). `npm`으로 실행하지 말 것.

```bash
pnpm dev                                        # 개발 서버 (http://localhost:5173)
pnpm build                                      # 타입 검사 + 빌드 (tsc -b && vite build)
pnpm test                                       # 프론트 테스트 (vitest, 82개)
pnpm test:e2e                                   # ★ 화면 E2E (playwright, 6개) — 아래 경고 참조
pnpm exec oxlint                                # 프론트 린트
```

```bash
python -m pytest tests/ -q                      # 파이썬 테스트 (1,046개)
python scripts/check_new_sangkwon_quarter.py    # 새 분기 스냅샷이 떴나 (읽기만, 키 불필요)
python -m ruff check scripts/ tests/            # 파이썬 린트
python scripts/collectors/collect_building_ledger.py --dry-run   # 수집 예산 확인(API 0콜)
python scripts/collectors/collect_building_ledger.py             # 건축물대장 수집 (이어받기)
python scripts/collectors/load_building_ledger.py                # raw → DB 적재
python scripts/collectors/collect_vworld_land.py --dry-run       # 브이월드 토지특성 예산 확인(API 0콜)
python scripts/collectors/collect_vworld_land.py --limit 50      # 토지특성 수집 (이어받기, 필지당 1콜)
python scripts/collectors/load_vworld_land.py --dry-run          # raw → parcel 갱신 미리보기(DB 쓰기 0)
python scripts/collectors/load_vworld_bulk.py --dry-run          # 전국 일괄 CSV(zip 17개) → parcel 미리보기(DB 쓰기 0)
python scripts/collectors/load_vworld_bulk.py                    # 전국 일괄 CSV 적재 — ⚠️ parcel에 있는 PNU만 채운다
python scripts/collectors/load_sangkwon_snapshot.py --sigungu-code all --dry-run   # 상권정보 전국 모드 미리보기
python scripts/collectors/load_sangkwon_snapshot.py --sigungu-code 11,30 --dry-run # ★ 1단계 = 서울+대전 (결정 0006)
python scripts/collectors/fetch_bldrgst_bulk.py --list             # 건축HUB 일괄 파일 목록 (다운로드 0)
python scripts/collectors/fetch_bldrgst_bulk.py --kind title --probe  # 크기·형식만 확인 (저장 0)
python scripts/collectors/fetch_bldrgst_bulk.py --kind title      # 표제부 zip 받기 (646MB, 로그인 불필요)
python scripts/collectors/convert_bldrgst_bulk.py --dry-run       # zip → raw JSONL 변환 미리보기(쓰기 0)
python scripts/collectors/convert_bldrgst_bulk.py                 # 변환 (기본 범위 11,30 = 서울+대전)
# ↑ 변환 후에는 기존 적재기를 시군구 폴더마다 돌린다 (코드 수정 0):
#   python scripts/collectors/load_building_ledger.py --raw-dir data/raw/bldrgst_bulk_converted/11680 --snapshot-ym 202606
python scripts/dbx.py -c "refresh materialized view concurrently mv_search_parcel; analyze;"   # ★ 적재 후 필수
python scripts/make_env_local.py                # .env → .env.local (브라우저용 공개키만)
python scripts/backup_raw.py --dry-run          # 원본 백업 대상 확인 (쓰기 0)
python scripts/backup_raw.py                    # data/raw → F:\sangga-raw-backup (외장 SSD 연결 필요)
python scripts/backup_raw.py --verify           # 백업본을 다시 읽어 SHA-256 대조
```

> 💾 **원본 백업은 자동이 아니다.** 새 분기 zip을 받았거나 대량 수집을 마쳤으면 `backup_raw.py`를
> 직접 한 번 돌린다. 과거 분기 zip은 포털에서 내려가면 **재수집이 불가능**하다(절대 규칙 6).

> ⚠️ **경로·드라이브·`os.sep`을 다루는 코드는 윈도우에서 초록이어도 CI(Ubuntu)에서 깨진다** (2026-08-13 사고).
> `os.path`는 윈도우에선 `ntpath`, CI에선 `posixpath`라 **같은 문자열을 다르게 해석**한다 —
> `abspath('Q:\\x')`가 윈도우에선 `Q:\x`(드라이브 Q:)지만 CI에선 `/현재폴더/Q:\x`(드라이브 없음)다.
> 테스트에서 OS를 흉내 낼 때는 `os.path` 한 벌을 통째로 바꾼다(함수 하나만 바꾸면 반쪽 흉내가 된다).
> **이 종류는 윈도우에서 원리적으로 못 잡는다 — CI가 유일한 방어선이니 CI 빨간불을 넘기지 말 것.**

> ⚠️ **화면 문구를 바꿨으면 커밋 전에 `pnpm test:e2e`를 한 번 돌린다** (2026-08-11 사고).
> 검색창 라벨을 `건물명 또는 도로명주소` → `건물명 또는 주소`로 줄였을 때 **pytest도
> vitest도 끝까지 초록**이었고 E2E만 CI에서 3건 터졌다. E2E는 그 둘에 안 들어 있어서
> 로컬에선 신호가 아예 안 뜬다 — 라벨·버튼 이름·안내 문구를 건드리면 이 명령이 유일한 방어선이다.

> ⚠️ **`npm run collect`는 존재하지 않는다.** 그리고 `npm`이 아니라 `pnpm`으로 돌린다.
> (`package.json` scripts 실측 2026-08-11: dev·build·lint·typecheck·**test**·test:watch·
> **test:e2e**·preview 8개. "test 계열이 없다"던 예전 서술은 그 뒤 도입돼 낡았다.)
