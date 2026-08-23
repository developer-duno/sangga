# 상가 공간분석 플랫폼

> 상업용 부동산을 **층별·업종별**로 공간분석하고 매매/임대 참고시세를 비교하는 플랫폼.
> 필지(PNU) → 건물 → 호실(층+호) 3층 구조. React 19 + Vercel Serverless + Supabase PostgreSQL(별도 프로젝트).

## 즉시 알아야 할 것

- **사용자는 비개발자.** 쉬운 말 원칙. 코드는 복사-붙여넣기로 바로 도는 완전한 형태로. 조각 코드 금지
- **알려진 한계** — `docs/알려진한계.md` ★ **조사 전에 먼저 읽을 것.** 여기 있는 건 이미 아는 것이라 다시 조사하지 않는다(매 세션 같은 걸 재발견하는 낭비를 막는 기준선)
- **상세 계획** — `docs/상세계획.md` (데이터 소스·분석 로직·검증 설계·로드맵 전부)
- **DB 스키마** — `supabase/schema.sql`
- **부동산 데이터 처리 규격** — `budongsan-data` 스킬 참조 (PNU 조립·층 정규화·API 카탈로그)
- **현재 Phase** — **Phase 1 통과**(2026-08-09, 조인률 95.92%/96.86%) → 1단계 서비스범위(서울+대전) 확장 완료(결정 0006) → **Phase 2 진행 중**(층별 스택 화면, 눈 검증 2/10). 2026-08-14: `district`(상권 경계) **0행 → 서울 1,650개** 적재(결정 0008) → 같은 날 층별 화면에 **"속한 상권" 한 줄 연결**(함수 `list_building_districts` — 겹치면 전부 나열·경계 밖="없음"(정상)·자료 없는 지역="준비 중"). 대전도 **소진공 주요상권현황 37개 적재 완료**(결정 0009 — district 총 **1,687개**, 출처 칸 `source_nm` 신설로 화면 출처가 상권별 데이터). 2026-08-15: 실거래 **서울+대전 24개월 44,052건** 적재(나머지 지역은 서울·대전 전부 활성화 후 — 사장님 방침) → 층별 화면에 **"실거래 기록" 섹션**(이 필지 이력 + 구 층대별 단가, 추정 0 — 결정 0011·0012 Stage A. 추정 밴드는 Stage B 백테스트 후 재결재) → 같은 날 밤 **Stage B 백테스트 성적표 v1 완성**(`docs/backtest/성적표-v1.md` — 사다리 MdAPE 29.1% vs 구평균 38.3%, 채택의 53%는 법정동 폴백) → 2026-08-16 **사장님 재결재 확정(결정 0013)**: 출시 기준선 = MdAPE 30% 이하 + 사다리가 구평균을 이기는 구만(**14개 구** 통과 — 서울 10·대전 4, 금천은 30% 이하지만 구평균에 져서 제외) · 표시 범위 = **좁게 GO**(통과 구 × 2층·3층+만, 1층(±45%)·지하·옥탑 미제공). Stage B 구현은 조사→플랜→승인 후 착수. 2026-08-22: 층별 화면에 **"둘레의 업종 분포" 섹션**(결정 0014 상권 지표 1단계 — 속한 상권 안 + 반경 500m 를 업종 대분류로 세고, 대분류를 고르면 중분류와 "같은 업종 N곳" 경쟁 카운트). ⚠️ 이 숫자는 **이 건물 점포가 아니라 둘레의 남의 가게까지** 센 것이라 층 목록의 점포 칸과 세는 대상이 다르다. 상권 스코프는 `mv_district_industry_mix` 로 미리 굽고(살아있는 쿼리는 찬 캐시에서 12.5초), 반경은 이웃 필지 PNU 배열 + 커버링 인덱스로 잰다(1,583ms→23ms). **상권끼리 더하면 안 된다** — 겹치는 자리의 점포가 양쪽에 세어진다(실측 3.9%). 2026-08-24: 층별 화면의 섹션들이 **접히는 카드 다섯 장**으로 묶였다(로드맵 Wave 2 『한 장 요약 접힘 틀』). 제목·역할 태그(공통/투자자/창업자/중개사)·기본 펼침은 **`src/lib/sectionCards.ts` 의 `SECTION_PLAN` 한 표**가 정본이고, 첫 화면 펼침 상한은 **4장**(`SECTION_EXPAND_BUDGET`)이라 다섯째인 **참고 매매 시세(추정값)만 접힌 채로 시작**한다. ⛔ **접힘은 숨김이 아니다** — 접힌 카드도 제목 + 핵심 한 줄이 그대로 보인다(상권 카드는 출처까지 요약에 둔다). 카드를 더 붙일 때 `defaultOpen: true` 로 두면 상한이 조용히 깨지는데, 그건 `src/lib/sectionCards.test.ts` 가 잡는다. `docs/PROGRESS.md` 참조

### 🔴 운영 5계명 (매 세션 확인 — 어기면 복구 불가하거나 조용히 깨진다)

| | 규칙 | 어기면 |
|---|---|---|
| 💾 | **백업은 자동이 아니다.** 새 분기 zip을 받았거나 대량 수집을 마쳤으면 `python scripts/backup_raw.py`를 **직접** 돌린다 | 포털에서 과거분이 내려가면 **재수집 불가**(절대 규칙 6). 건축HUB 일괄 파일도 **최근 3개월치만** 남는다 |
| 🔎 | **자료를 적재했으면 `python scripts/post_load.py` 한 번.** 이 하나에 vacuum(analyze)·요약표 5개 갱신·신선도 점검이 다 들어 있다(요약표만 손으로 갱신하면 나머지가 조용히 빠진다). ⚠️ **권한 점검(공개키가 읽거나 고칠 수 있는 것)은 여기서 안 돈다 — `--check` 에서만** 돈다. 적재 뒤에는 `post_load.py` 와 `post_load.py --check` 를 **둘 다** 돌린다 | 새로 넣은 건물이 **검색에 안 나온다**. 지도·구 단가·각주 결측률도 옛 자료를 계속 말한다. 전부 에러가 아니라 조용한 누락이라 아무도 모른다 |
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
9. **필지·점포는 전국, 건물·화면 오픈은 서울+대전 — 서로 다른 두 축이다** — 결정 0005의 `[A]`(parcel·상권정보 전국 시드)와 결정 0006(사용자가 실제로 볼 수 있는 지역)은 **별개 축**이라 헷갈리면 안 된다. `[A]`는 2026-08-13 전국 완주(`parcel` 1,119,149행·`unit_business` 3,388,580행(최신 스냅샷 202606분만 2,772,484)) — 이건 "데이터가 어디까지 들어왔나"다. 0006은 "건물·화면을 여는 지역은 서울+대전뿐"이다 — 이건 "사용자가 어디를 볼 수 있나"다(건물은 아직 서울·대전 30개 구 242,631동뿐, 전국 필지 위에 얹힌 상태). **화면에는 자료가 있는 지역만 보여준다**(2026-08-13 개정 — 누를 수 없는 칩을 늘어놓지 않는다). 그 목록의 진실은 **서버(`list_open_sigungu()`)뿐**이라 자료가 들어오면 화면이 저절로 따라온다. ⚠️ **열린 지역의 진실은 이제 서버**(`list_open_sigungu()` → `mv_open_sigungu`)다 — 예전엔 `src/lib/regions.ts` 였는데, 그러면 자료가 늘 때 화면 문구만 낡는 드리프트가 난다(2026-08-13 2차 검증에서 실제로 발견). `regions.ts` 는 짧은 이름표(서울/대전)를 붙이는 데만 쓴다. 검색은 고른 구 안에서만 한다(동까지는 안 좁힘 — 상권이 행정동 경계를 넘어 걸치므로). `docs/decisions/0005-전국확장-실행순서와-선행조건.md`·`docs/decisions/0006-1단계-서비스범위-서울대전.md`
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
| 프론트 | React 19 + Vite, 카카오맵(**react-kakao-maps-sdk** — 상권 면·마커를 이걸로 그린다, 결정 0010). ⚠️ deck.gl 은 **안 쓴다**(설치돼 있지도 않다) — 카카오맵 위에 렌더러를 하나 더 얹는 셈이라 확대·이동 때 두 그림을 맞추는 일을 떠안는다. 호실 수백만 개를 점으로 뿌리는 화면이 생기면 그때 다시 본다 |
| API | Vercel Serverless |
| DB | Supabase PostgreSQL + PostGIS (**별도 프로젝트**) |
| 수집 | ⬜ **여전히 로컬 수동 실행이다** — 받기·적재·백업 전부 사람 손. 다만 **놓치는 것만은 막아 뒀다**: `sangkwon-quarterly-watch.yml`이 매주 포털을 확인해 새 분기가 뜨면 이슈를 자동으로 연다(비밀값 0개). **감시가 실패해도 이슈를 연다**(2026-08-14 추가 — 08-10 에 죽은 걸 나흘 뒤에 알았다). 목록 조회는 30초 타임아웃으로 3번 재시도한다. 적재 후 `scripts/check_new_sangkwon_quarter.py`의 `LATEST_KNOWN_QUARTER`를 **사람이 올려야** 다음 분기를 감지한다(절대 규칙 6). 상권 원천(서울 OA-15560·소진공 15090955)은 갱신이 비정기라 `district-source-watch.yml`이 매주 상세 페이지의 수정일 칸 변동을 확인해 이슈를 연다(2026-08-15 추가) — 반영 후 `check_district_source_update.py`의 기준선 상수도 **사람이 올린다**. ✅ **예약이 아예 안 도는 경우**(공개 레포는 60일 무활동 시 자동 중지, 부하 시 큐 드롭)도 **2026-08-22 부터 잡는다** — 감시 둘이 **서로를 본다**(`check_watch_heartbeat.py`가 상대의 마지막 성공 시각을 GitHub API 로 읽어 8일 넘으면 이슈를 연다). 한쪽 예약이 살아 있는 한 다른 쪽의 죽음이 일주일 안에 뜨고, **둘 다 죽는 경우**는 사람이 `python scripts/check_watch_heartbeat.py`를 직접 돌려 잡는다 |
| 테스트 | 파이썬 **pytest 1,730개** + 프론트 **vitest 313개**(jsdom + @testing-library/react) + **E2E playwright 12개**(`e2e/floor-stack.spec.ts` — 검색→선택→층 스택(속한 상권·실거래 기록·참고 매매 시세 밴드 포함), **둘레의 업종 분포(두 경로 — 서버에 함수가 없으면 섹션이 조용히 사라지는지, 답하면 상권·반경 두 묶음이 그려지는지)**, **구 칩 건물 수·도로접면·업종 요약·건물 스펙 4칸(0=미상)**, **한 장 요약 접힘 틀(카드 넷만 펼쳐져 있고 접힌 카드는 눌러야 내용이 나오는지)**, 너무 넓은 검색 안내창). ⚠️ **E2E 는 같은 12개를 넓은 화면(chromium)과 휴대폰(mobile — Pixel 7 프리셋, 폭 412px·터치)에서 두 번 돌려 총 24회다** — 좁은 폭은 `styles.css` 의 `@media (max-width: 720px)` 가 판을 다시 짜는 자리라 넓은 화면만 보면 못 잡는다(2026-08-22 층별 막대를 모바일에서만 숨긴 사고). 개수를 셀 때 12(시험)과 24(실행)를 헷갈리지 말 것. CI가 셋 다 돌린다(`pnpm test:e2e`). ⚠️ **로컬에서 앞의 둘만 돌리면 E2E 실패를 못 본다** — 화면 문구를 건드렸으면 `pnpm test:e2e`도 |

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

## 법률 — 결재 완료 (2026-08-22, 결정 0015)

4건(적정가격 표현·상호명 노출·상권정보 재가공·상가임대차법 개정분) 전부 해소 — **배포의 법률
게이트 없음**. 단 변호사 검토가 아니라 사장님 사업 판단으로 갈음한 결재다(`docs/decisions/0015`).
금지어(적정가격·감정가·평가액)와 근거·표본 병기는 결재와 무관하게 계속 지킨다.

## 명령

**패키지 매니저는 `pnpm`이다** (`pnpm-lock.yaml`·CI 기준). `npm`으로 실행하지 말 것.

```bash
pnpm dev                                        # 개발 서버 (http://localhost:5173)
pnpm build                                      # 타입 검사 + 빌드 (tsc -b && vite build)
pnpm test                                       # 프론트 테스트 (vitest, 313개)
pnpm test:e2e                                   # ★ 화면 E2E (playwright, 12개 × 넓은화면·휴대폰 2벌 = 24회) — 아래 경고 참조
pnpm exec oxlint                                # 프론트 린트
```

```bash
python -m pytest tests/ -q                      # 파이썬 테스트 (1,730개)
python scripts/check_new_sangkwon_quarter.py    # 새 분기 스냅샷이 떴나 (읽기만, 키 불필요)
python scripts/check_district_source_update.py  # 상권 원천(서울·소진공) 수정일이 바뀌었나 (읽기만, 키 불필요)
python scripts/check_watch_heartbeat.py         # 감시 2종이 아직 돌고 있나 (읽기만, 키 불필요 — 8일 넘으면 exit 1)
python scripts/backtest_price.py                # Stage B 백테스트 성적표 재생성 (DB 읽기 전용 → docs/backtest/, 통과구.csv 포함)
python scripts/backtest_price.py --place-axis   # 1층 유형축(L7=도로등급×상권등급) 검증 — 새 파일 2개만 쓴다(기존 성적표·통과구.csv 안 건드림). psql 필요
python scripts/load_price_gate.py --dry-run     # 통과구.csv → price_gate_sigungu 미리보기(DB 쓰기 0)
python scripts/load_price_gate.py               # ★ 통과 구 게이트 적재 (관문 3종·걸리면 통째 롤백 — 손 편집 금지, 결정 0013 §4)
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
python scripts/collectors/fetch_seoul_district.py --probe          # 서울 상권영역 크기·좌표계만 확인(저장 0)
python scripts/collectors/fetch_seoul_district.py                  # 상권영역 zip 받기 (2.07MB, 로그인 불필요)
python scripts/collectors/load_seoul_district.py --dry-run         # SHP → district 미리보기 (DB 쓰기 0)
python scripts/collectors/load_seoul_district.py                   # 적재 (1,650개, 한 트랜잭션 — 실패 시 통째 롤백)
# ↑ pyshp 필요: python -m pip install pyshp  (순수 파이썬, GDAL 불필요. CI 에는 안 깔려 있고 안 깔아도 된다)
python scripts/collectors/fetch_sbiz_district.py --probe           # 소진공 주요상권현황 크기·메타만 확인(저장 0)
python scripts/collectors/fetch_sbiz_district.py                   # 전국 주요상권 CSV 받기 (30.5MB, 로그인 불필요)
python scripts/collectors/load_sbiz_district.py --dry-run          # CSV → district 미리보기 (DB 쓰기 0, 기본 대전만)
python scripts/collectors/load_sbiz_district.py                    # 대전 37개 적재 — ⚠️ 서울(11)은 코드가 거부한다(정본 이원화 방지)
python scripts/build_rone_map.py --seed scripts/seeds/district_rone_map.csv    # ★ 매핑 seed 고쳤으면 커밋 전 이 관문(exit 0)
python scripts/load_rone_map.py --dry-run                          # seed → district_rone_map 미리보기(DB 쓰기 0)
python scripts/load_rone_map.py                                    # 매핑 적재 (검증 관문 3종 내장 — 걸리면 통째 롤백)
python scripts/build_district_geojson.py --dry-run                  # 지도용 상권 파일 미리보기(행수·크기만, 파일 안 씀)
python scripts/build_district_geojson.py                           # ★ district 를 적재했으면 → public/districts.geojson 굽고 **커밋**
python scripts/post_load.py                     # ★ 적재 후 필수 — vacuum(analyze) + 요약표 5개 갱신 (권한 점검은 안 돈다)
python scripts/post_load.py --check              # 낡았나 + 공개 롤이 읽거나 **고칠 수** 있는 것 점검 (DB 쓰기 0, 걸리면 exit 1)
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
> 5173 포트를 다른 프로젝트 세션이 쓰고 있으면(이 PC 는 그게 정상) 남의 서버를 죽이지 말고
> **`E2E_PORT=5273 pnpm test:e2e`** 처럼 빈 포트로 비켜 간다(2026-08-14 — 남의 앱을
> 재사용해 6개 전부 타임아웃 난 실측 뒤 포트 오버라이드 추가).
> 검색창 라벨을 `건물명 또는 도로명주소` → `건물명 또는 주소`로 줄였을 때 **pytest도
> vitest도 끝까지 초록**이었고 E2E만 CI에서 3건 터졌다. E2E는 그 둘에 안 들어 있어서
> 로컬에선 신호가 아예 안 뜬다 — 라벨·버튼 이름·안내 문구를 건드리면 이 명령이 유일한 방어선이다.

> ⚠️ **`npm run collect`는 존재하지 않는다.** 그리고 `npm`이 아니라 `pnpm`으로 돌린다.
> (`package.json` scripts 실측 2026-08-11: dev·build·lint·typecheck·**test**·test:watch·
> **test:e2e**·preview 8개. "test 계열이 없다"던 예전 서술은 그 뒤 도입돼 낡았다.)
