# 상가 공간분석 플랫폼

> 상업용 부동산을 **층별·업종별**로 공간분석하고 매매/임대 참고시세를 비교하는 플랫폼.
> 필지(PNU) → 건물 → 호실(층+호) 3층 구조. React 19 + Vite(정적 SPA · 서버 코드 없음) + Supabase PostgreSQL(별도 프로젝트).

## 즉시 알아야 할 것

- **사용자는 비개발자.** 쉬운 말 원칙. 코드는 복사-붙여넣기로 바로 도는 완전한 형태로. 조각 코드 금지
- **알려진 한계** — `docs/알려진한계.md` ★ **조사 전에 먼저 읽을 것.** 여기 있는 건 이미 아는 것이라 다시 조사하지 않는다(매 세션 같은 걸 재발견하는 낭비를 막는 기준선)
- **상세 계획** — `docs/상세계획.md` (데이터 소스·분석 로직·검증 설계·로드맵 전부)
- **DB 스키마** — `supabase/schema.sql`
- **부동산 데이터 처리 규격** — `budongsan-data` 스킬 참조 (PNU 조립·층 정규화·API 카탈로그)
- **현재 Phase** — **Phase 1 통과**(2026-08-09, 조인률 95.92%/96.86%) → 1단계 서비스범위(서울+대전) 확장 완료(결정 0006) → **Phase 2 진행 중**(층별 스택 화면, 눈 검증 2/10). **라이브 https://sangga-one.vercel.app** (Vercel 프로젝트 `sangga`, GitHub 연결이라 **main push 가 곧 배포**. ⛔ **새 배포 주소가 생기면 카카오 콘솔에 그 주소를 등록해야 지도가 뜬다**(미분양아파트 앱 1398824 의 "플랫폼 키 > JS 키 수정 > JavaScript SDK 도메인")). 진행 기록 정본 = `docs/PROGRESS.md` · 결정 = `docs/decisions/`
- **기능별 경위·⛔ 주의사항** = **`.claude/rules/feature-notes.md`** — 화면 코드(`src/`)·DB 정본(`supabase/`)·`e2e/`·마이그레이션 시험을 열면 자동으로 읽힌다. ⚠️ **파일을 안 열고 기능을 바꾸거나 설명하거나 DB 함수·마이그레이션을 다룰 때는 그 파일을 먼저 직접 연다** — 그 안의 ⛔ 는 어기면 에러 없이 조용히 틀리는 것들이다. 담긴 것(날짜순): 상권 경계·실거래·Stage B(0008·0011~0013) · 둘레의 업종 분포(0014) · 접히는 카드 `SECTION_PLAN` · 첫 배포 · 기본기 3종·의견함(0016·0017) · 주소로 들고 다니기(0019) · 종이로 뽑기(0020) · 국세청 기준시가(0021) · LH 상가 공고(0022) · 곧 올라오는 상가 건물(0023) · 임대 사실 카드·층별 임대료(0024·0031) · 상권→건물 다리(0025) · 성적표 공개 · 자료 신선도(0030) · 넘기기 링크 · 동네 매매 단가 흐름(0027) · 상호명 검색(0028) · 호실 구성표(0032) · 첫 방문 속도(09-27) · 서울 개업·폐업 자료·DB(0033 R1) · 분기 표지 '다 넣은 뒤 한 번에'(0035)

### 🔴 운영 7계명 (매 세션 확인 — 어기면 복구 불가하거나 조용히 깨진다)

| | 규칙 | 어기면 |
|---|---|---|
| 💾 | **백업은 자동이 아니다.** 새 분기 zip을 받았거나 대량 수집을 마쳤으면 `python scripts/backup_raw.py`를 **직접** 돌린다 | 포털에서 과거분이 내려가면 **재수집 불가**(절대 규칙 6). 건축HUB 일괄 파일도 **최근 3개월치만** 남는다 |
| 🔎 | **자료를 적재했으면 `python scripts/post_load.py` 한 번.** 이 하나에 vacuum(analyze)·요약표(정본은 스크립트의 `REFRESH_MVS` 목록) 갱신·신선도 점검이 다 들어 있다(요약표만 손으로 갱신하면 나머지가 조용히 빠진다). ⚠️ **권한 점검(공개키가 읽거나 고칠 수 있는 것)과 옛 문(public) 닫힘 유지 확인은 여기서 안 돈다 — `--check` 에서만** 돈다. 적재 뒤에는 `post_load.py` 와 `post_load.py --check` 를 **둘 다** 돌린다. **`--check` 는 그 밖에도 다섯을 더 본다**(2026-09-27 P7 · 별관은 2026-10-05) — 느려짐(지난 점검 이후 평균이 기준을 넘었나 — ⚠️ `--check` 는 돌 때마다 기준점을 그 시각으로 새로 저장한다)·정본 색인 존재/유효·정본↔라이브 함수 일치·새 요약표 낡음(2026-10-03 #199 부터 행수가 아니라 **양쪽 차집합** — 표에만 있는 필지·표에 빠진 필지를 센다 · `--check` 없는 갱신 흐름도 끝에 이 표를 다시 잰다)·**별관(TOAST) 쫓겨남**(별관을 쓰는 public·api 표에서 256바이트 미만 값이 별관에 있으면 [주의] — 큰 옆 칸 탓에 쫓겨난 작은 값이라 그 칸을 훑는 쿼리가 느려진다 · 종료 코드에 영향 없음 · 2026-09-27 #164 의 재발 감시). ✅ **정본 색인 점검은 이제 양쪽을 본다**(2026-10-02 #188) — 정본 색인이 라이브에 없거나 못 쓰거나 **INCLUDE 칸이 다르면 [사고]**, 라이브에만 남은 색인(제약이 만든 것·확장 소유 표의 것은 뺀다)은 **[주의]**(종료 코드에 영향 없음). ⚠️ 색인 열·식·WHERE 조건·색인 방식의 차이는 여전히 못 본다(이름과 INCLUDE 가 같으면 [정상]) · [주의] 줄은 종료 코드 0 이라 **눈으로 본다** · **새 상권 분기는 post_load 가 표지(`snapshot_release`)를 올려야 화면에 보인다**(결정 0035) | 새로 넣은 건물이 **검색에 안 나온다**. 지도·구 단가·각주 결측률도 옛 자료를 계속 말한다. 전부 에러가 아니라 조용한 누락이라 아무도 모른다 |
| 📦 | **패키지 매니저는 `pnpm`.** `npm`으로 돌리지 않는다 (`pnpm-lock.yaml`·CI 기준) | 락파일이 갈라져 CI와 로컬이 다른 의존성을 쓴다 |
| 🔑 | **키는 `.env`.** 브라우저용 공개키는 `.env.local` — 손으로 만들지 말고 `python scripts/make_env_local.py` | 손으로 만들다 **서비스키를 브라우저에 노출**하는 사고. 이 스크립트는 공개키만 골라 쓴다 |
| 🐍 | **파이썬 명령은 프로젝트 루트에서.** `cd D:\sangga` 후 실행 | 상대경로(`data/raw/...`)가 어긋나 "파일 없음"으로 조용히 0건 처리된다 |
| 🔒 | **main 은 잠겨 있다** (결정 0018). 작업은 **새 가지 → PR → 검사(`test`·`web`) 통과 → 머지**. 새 컴퓨터에서는 `python scripts/setup_git_hooks.py` 한 번으로 로컬 알람도 켠다. 정말 급하면 `SANGGA_ALLOW_MAIN=1` (잠금도 함께 풀어야 한다) | main 직접 밀어넣기는 GitHub이 거부한다(GH013). ⚠️ **로컬 알람은 잠금이 아니다** — 새 컴퓨터에서 안 켜면 커밋을 다 만든 뒤에야 거부당해 가지를 옮기는 뒷수습이 남는다. 훅이 CRLF로 바뀌면 **에러 없이 그냥 안 돈다**(그래서 `.gitattributes`로 못 박고 테스트가 지켜본다) |
| 🚪 | **새 DB 함수는 이제 닫힌 채 태어난다** (2026-09-01b, 라이브 적용). 화면이 부를 함수를 새로 만들면 `grant execute on function <이름> to anon;` 을 **명시로** 줘야 한다 — 예전처럼 저절로 열리지 않는다. ⚠️ `create extension`·`alter extension … update` 도 같은 영향을 받는다 (그 확장 함수가 PUBLIC 실행 불가로 태어난다). grant 는 **`api.` 쌍둥이(security definer)에만** 준다 — public 원본에는 revoke 만(화면은 api 로만 들어온다) — 어기면 `tests/test_migration_atomicity.py` §4 가 빨강 | 새 함수를 붙였는데 화면에서 `permission denied for function` — 코드는 맞는데 문이 안 열린 것이다. 반대로 이 규칙을 되돌리면(`alter default privileges grant execute on functions to public;`) 앞으로 만드는 함수가 전부 **모든 사람에게** 열린다 |

> ⛔ **적용된 마이그레이션 파일은 고치지 않는다** — `supabase/migrations/` 는 라이브에 적용된 순서의 **날짜 원장**이다(가드 `test_migration_atomicity.py`·`test_lh_notice_migration.py` 가 그 전제로 선다). 머리말의 기대가 틀린 것으로 드러나도 파일이 아니라 **결정 문서·PROGRESS 에 정정**을 적는다(2026-09-10a 의 "넓은 검색어가 내려간다"가 그 예 — 실측은 결정 0028 §백로그). 라이브에 ALTER 로만 넣은 변경도 **같은 PR 에서 정본에 반영**한다 — 안 하면 `tests/test_schema_alter_replay.py`(ALTER 되짚기)와 `test_schema_function_drift.py` 가 CI 에서 빨강(2026-09-23 누락이 계기).

> ⛔ **잠금을 잡는 DDL**(`alter table … set storage` 등 — ACCESS EXCLUSIVE)은 `set lock_timeout` 을 **begin 앞**(세션 설정)에 두고, 머리말의 잠금 수준은 공식 문서로 확인해 적는다(2026-09-27d — 처음 머리말이 "안 막음"이라 틀렸다).

> ⛔ **함수를 다시 만드는 마이그레이션은 머리(`security definer`·`set search_path`·`stable`)와 `comment` 까지 정본에서 잘라 붙이고, 시험으로 정본과 글자 대조한다** — `create or replace` 는 머리 속성을 새 정의로 덮어쓰는데, 드리프트 가드는 `$$` 안 본문만, `--check` 는 언어·본문·search_path 만 본다(security definer·stable·comment 는 아무도 안 본다). 2026-10-01a 적대검증 로컬 실측: `set search_path` 가 빠지면 anon 경로가 `relation does not exist` 로 죽어 화면 표가 통째로 사라지는데 시험 1,130개가 초록이었다(본보기 = `tests/test_data_freshness_migration.py` 의 머리·comment 대조 시험).

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
신고 의무가 없다. 임대료를 "조회"하는 코드를 쓰지 않는다. 화면에는 **부동산원이 조사해 공표한 값(상권 ㎡당 임대료·층별 임대료·수익률)을 그대로** 나르고, 그것이 건물이 아니라 **조사 상권의 평균**임을 늘 밝힌다. 건물·층별 임대료를 우리가 계산해 **추정하는 일은 검증 수단이 생기기 전까지 하지 않는다**(결정 0031).

### 6. 분기 스냅샷 관리
포털 "주기성 과거 데이터"에 과거 분기 파일이 제공된다(2026-08-07 실측 48개 — §3.4). 단 유지 보장이 없으므로 **과거분은 확보 즉시 로컬 보관**하고, **매 분기 신규 수집도 놓치지 말 것.** 공실 이력·점포 생존기간이 전부 여기서 나온다. 대화 중 관련 맥락이 나오면 리마인드한다.

## 확정 설계 (다시 논의하지 말 것)

1. **섹터** — 용도 4축(상업/업무/산업물류/토지) × 거래단위 3축(구분소유/통건물/필지). 네이버 분류 미사용
2. **3층 구조** — 필지(PNU) → 건물 → 호실. 아파트 2층으로는 상가를 못 담음
3. **조인 키** — PNU 19자리. 상권정보에 이미 있으므로 마스터로 사용
4. **매매는 실측, 임대는 공표 조사값** — 옛 문장 "매매 실측, 임대 추정"은 결정 0031 로 바뀌었다 (임대 추정은 검증 수단이 생길 때까지 하지 않는다).
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
| 6 | 서울 상권분석 (서울만 풀버전) — 점포-상권 개업·폐업(결정 0033) | 서울 열린데이터광장 OA-15577 |

## 아키텍처

```
main → App → components → lib → types   (단방향 — 역방향 import 0건)
```

| 레이어 | 기술 |
|---|---|
| 프론트 | React 19 + Vite, 카카오맵(**react-kakao-maps-sdk** — 상권 면·마커를 이걸로 그린다, 결정 0010). ⚠️ deck.gl 은 **안 쓴다**(설치돼 있지도 않다) — 카카오맵 위에 렌더러를 하나 더 얹는 셈이라 확대·이동 때 두 그림을 맞추는 일을 떠안는다. 호실 수백만 개를 점으로 뿌리는 화면이 생기면 그때 다시 본다 |
| 서버 | **없다** — 화면이 Supabase PostgREST·RPC 를 직접 부른다(`api/` 폴더도 서버리스 함수도 **0개** — 2026-08-25 실측). Vercel 은 정적 파일 호스팅과 배포만 맡는다. ⚠️ 그래서 **고칠 서버 코드가 없다** — 서버에서 해야 할 일은 전부 DB 함수(schema.sql)로 간다 |
| DB | Supabase PostgreSQL + PostGIS (**별도 프로젝트**) |
| 수집 | ⬜ **여전히 로컬 수동 실행이다** — 받기·적재·백업 전부 사람 손. 다만 **놓치는 것만은 막아 뒀다**: 감시 그물 여섯(분기 스냅샷 `sangkwon-quarterly-watch` · 상권 원천 `district-source-watch` · 라이브 생존 `live-health-watch` · 의견함 주간 알림 `feedback-digest` · LH 상가 공고 `lh-notice-watch` · 지난 날짜 감시 `data-freshness-watch`)이 서로를 전부 본다(`check_watch_heartbeat.py`). ⛔ **새 예약 워크플로를 만들면 그물에도 넣어야 한다** — `DEFAULT_WORKFLOWS` 와 형제들의 `--workflow` 인자 둘 다. 빠뜨리면 테스트가 빨간불로 잡는다(`schedule:` 있는 파일을 훑어 대조한다). ⛔ 알리기만 한다 — 적재는 여전히 사람 손. ⛔ **검색 함수만 고장 난 경우는 여전히 아무도 안 본다**. 적재 후 기준선 상수(`LATEST_KNOWN_QUARTER` · `LATEST_KNOWN_NOTICE_DATE` · 상권 원천 기준선)는 **사람이 올린다**. 각 그물의 비밀값·종료코드·이슈 제목 규칙·못 보는 틈 = **`.claude/rules/watch-nets.md`**(`.github/`·`scripts/check_*.py`·감시 시험을 열면 자동으로 읽힌다 — ⚠️ 감시가 연 이슈를 처리하거나 감시를 고칠 때는 그 파일을 먼저 직접 연다) |
| 테스트 | 파이썬 **pytest 4,719개** + 프론트 **vitest 960개**(jsdom + @testing-library/react) + **E2E playwright 36개**(`e2e/floor-stack.spec.ts` — 시험별 내용 = **`.claude/rules/e2e-catalog.md`**, `e2e/` 를 열면 자동으로 읽힌다). ⚠️ **E2E 는 같은 36개를 넓은 화면(chromium)과 휴대폰(mobile — Pixel 7 프리셋, 폭 412px·터치)에서 두 번 돌려 총 72회다** — 좁은 폭은 `styles.css` 의 `@media (max-width: 720px)` 가 판을 다시 짜는 자리라 넓은 화면만 보면 못 잡는다(2026-08-22 층별 막대를 모바일에서만 숨긴 사고). 개수를 셀 때 36(시험)와 72(실행)을 헷갈리지 말 것. CI가 셋 다 돌린다(`pnpm test:e2e`). ⚠️ **로컬에서 앞의 둘만 돌리면 E2E 실패를 못 본다** — 화면 문구를 건드렸으면 `pnpm test:e2e`도. ⛔ **인쇄는 거의 전부가 CSS라 jsdom(vitest)이 원리적으로 못 본다** — 인쇄 매체를 흉내 낼 수 있는 곳은 E2E 뿐이다 |

**성능 원칙**: 상권(수천 개)은 사전계산 정적 JSON, 호실(수백만)은 Supabase 쿼리.
정적 JSON 폴백을 호실에는 두지 않는다.

## 수집 규칙

- **이어받기 필수** — `collect_progress` 테이블의 `pending`만 처리. 일 예산 소진 시 안전 종료. ⛔ **0건 응답 분기는 `done` 으로 굳히지 않는다**(아직 게시 안 된 분기가 0행으로 와서 '다 걷었다'로 굳는다 — R-ONE·서울 개폐업 API 공통) → 마지막 분기 인자를 의무로, 0행이면 pending 유지 + 경고
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
pnpm test                                       # 프론트 테스트 (vitest, 960개)
pnpm test:e2e                                   # ★ 화면 E2E (playwright, 36개 × 넓은화면·휴대폰 2벌 = 72회) — 아래 경고 참조
pnpm exec oxlint                                # 프론트 린트
```

```bash
python -m pytest tests/ -q                      # 파이썬 테스트 (4,719개 — 수집 4,719(10-07 노란 넷 워크트리 수집 실측 · +46) · 그 전 수집 4,673(10-07 결정 0035 워크트리 실측 · 4,670 passed + 3 skipped · 10-06 밤 4,474 에서 +199) · 그 전 본 폴더 기준 수집 4,474(10-06 밤 실측 · 그 전 4,457 passed 에 안내 가드 +8 · 분기 감시 이슈·md 가드 +9), 워크트리는 원본 자료가 없어 몇 개를 건너뛴다(10-06 #229 워크트리 실측 3 skipped) · CI 는 로컬 PostgreSQL 이 없어 test_district_openclose_migration 의 실행 시험 16개를, shapely 가 없어 test_backtest_openclose 의 도형 시험 1개를 더 건너뛴다 = 4,437 + 20 skipped — 10-06 CI 실측(main 54393ca) · 10-06 #232 뒤 CI 실측 4,445 + 20 · 이번 +9 뒤 기대 4,454 + 20 · 결정 0035 뒤 기대 ≈ 4,653 + 20)
python scripts/check_new_sangkwon_quarter.py    # 새 분기 스냅샷이 떴나 (읽기만, 키 불필요)
python scripts/check_district_source_update.py  # 상권 원천(서울·소진공) 수정일이 바뀌었나 (읽기만, 키 불필요)
python scripts/check_watch_heartbeat.py         # 예약 6종이 아직 돌고 있나 (읽기만, 키 불필요 — 멈춤=exit 1 · 조회·판정 실패=2 · 결과 쓰기 실패=4)
python scripts/check_live_health.py             # 라이브 사이트가 서 있나 (읽기만, 키 불필요 — 반쪽 배포까지 잡는다)
python scripts/check_lh_notices.py              # 기준선 이후 새 LH 상가 공고가 떴나 (읽기만 — .env 의 MOLIT_KEY 사용, 새 공고면 exit 1 · 조회 실패=2 · 결과 쓰기 실패=4)
python scripts/check_data_freshness.py          # '다음 갱신 예정'이 지난 자료가 있나 (읽기만 — .env 의 공개키 사용, 지남=exit 1 · 화면 분기 섞임=exit 1 · 조회 실패=2 · 변수 없음=3 · 결과 쓰기 실패=4)
python scripts/collectors/collect_lh_notices.py --dry-run   # LH 상가 공고 수집 미리보기 (DB 쓰기 0)
python scripts/collectors/collect_lh_notices.py             # LH 상가 공고 적재 (upsert — 끝나면 안내대로 기준선 상수를 올릴 것)
python scripts/feedback_digest.py               # 의견함에 뭐가 쌓였나 (숫자만 — 내용은 dbx.py 로. .env 자동 사용)
python scripts/collectors/collect_transactions.py --sigungu-code <구> --months 216 --end-ym 202408   # 과거 백필(2006-09~2024-08) — 2026-09-09 서울·대전 30구 완료, 재실행은 이어받기
# ⚠️ `--dry-run` 도 `collect_progress` 에 pending 시드를 **쓴다**(형제 수집기의 "DB 쓰기 0" 미리보기와 다르다 — `seed_progress` 가 dry_run 분기 **앞**에 있다, collect_transactions.py:735-746). 시드는 멱등(있는 행 보존)이라 무해하지만 미리보기에도 DB 열쇠가 필요하다.
python scripts/backtest_price.py                # Stage B 백테스트 성적표 재생성 (DB 읽기 전용 → docs/backtest/, 통과구.csv 포함)
python scripts/backtest_price.py --place-axis   # 1층 유형축(L7=도로등급×상권등급) 검증 — 새 파일 2개만 쓴다(기존 성적표·통과구.csv 안 건드림). psql 필요
python scripts/backtest_openclose.py            # 결정 0033 R3 개업·폐업 정답지(소진공 202603→202606 vs 서울시 20262) — DB·외부 호출 0 · shapely 필요(`python -m pip install shapely`) → docs/backtest/개업폐업-정답지-v1.md·-상권별.csv 를 덮어쓴다(재실행하면 md 3번째 줄 생성 시각만 바뀐다)
python scripts/load_price_gate.py --dry-run     # 통과구.csv → price_gate_sigungu 미리보기(DB 쓰기 0)
python scripts/load_price_gate.py               # ★ 통과 구 게이트 적재 (관문 3종·걸리면 통째 롤백 — 손 편집 금지, 결정 0013 §4)
python -m ruff check scripts/ tests/            # 파이썬 린트
python scripts/collectors/collect_building_ledger.py --dry-run   # 수집 예산 확인(API 0콜)
python scripts/collectors/collect_building_ledger.py             # 건축물대장 수집 (이어받기)
python scripts/collectors/load_building_ledger.py                # raw → DB 적재
python scripts/collectors/collect_vworld_land.py --dry-run       # 브이월드 토지특성 예산 확인(API 0콜)
python scripts/collectors/collect_vworld_land.py --limit 50      # 토지특성 수집 (이어받기, 필지당 1콜)
python scripts/collectors/load_vworld_land.py --dry-run          # raw → parcel 갱신 미리보기(DB 쓰기 0)
# ⚠️ 실적재에서 **갱신 대상 0건이면 종료코드 1**(2026-09-01 부터). 이 적재기는 "바뀐 것만"이
#    아니라 raw 전량을 다시 올리므로 0건은 "이미 다 채웠다"가 아니라 **항상 이상 신호**다
#    (raw 가 비었거나 [A] 전국 시드 미실행). 형제 load_vworld_bulk.py 와 같은 규약.
python scripts/collectors/load_vworld_bulk.py --dry-run          # 전국 일괄 CSV(zip 17개) → parcel 미리보기(DB 쓰기 0)
python scripts/collectors/load_vworld_bulk.py                    # 전국 일괄 CSV 적재 — ⚠️ parcel에 있는 PNU만 채운다
python scripts/collectors/load_sangkwon_snapshot.py --sigungu-code all --dry-run   # 상권정보 전국 모드 미리보기
python scripts/collectors/load_sangkwon_snapshot.py --sigungu-code all            # ★ 새 분기 적재는 전국 모드로 — 표지는 전국 모드에서만 올라간다(결정 0035 · 시·도 파일이 빠지면 안 올리고 exit 1)
# ↑ 끝에 '다 들어온 분기' 표지를 적는다(전국 모드만 · 결정 0035) — 화면은 이어서 post_load.py 가 요약표를 구운 뒤 표지를 올려야 바뀐다
python scripts/collectors/fetch_bldrgst_bulk.py --list             # 건축HUB 일괄 파일 목록 (다운로드 0)
python scripts/collectors/fetch_bldrgst_bulk.py --kind title --probe  # 크기·형식만 확인 (저장 0)
python scripts/collectors/fetch_bldrgst_bulk.py --kind title      # 표제부 zip 받기 (646MB, 로그인 불필요)
python scripts/collectors/convert_bldrgst_bulk.py --dry-run       # zip → raw JSONL 변환 미리보기(쓰기 0)
python scripts/collectors/convert_bldrgst_bulk.py                 # 변환 (기본 범위 11,30 = 서울+대전)
# ↑ 변환 후에는 기존 적재기를 시군구 폴더마다 돌린다 (코드 수정 0):
#   python scripts/collectors/load_building_ledger.py --raw-dir data/raw/bldrgst_bulk_converted/11680 --snapshot-ym 202606
python scripts/collectors/fetch_bldrgst_bulk.py --kind permit-basis   # ★ 건축인허가 기본개요 zip 받기 (438MB, 분류 01 — 월간·3개월만 보관)
python scripts/collectors/load_arch_permits.py --dry-run              # 인허가 → arch_permit 미리보기 (DB 쓰기 0, 관문 5종 리포트)
python scripts/collectors/load_arch_permits.py                        # ★ 미준공+2023이후만 적재 (한 트랜잭션 — 월 1회 수동, 결정 0023)
python scripts/collectors/fetch_seoul_district.py --probe          # 서울 상권영역 크기·좌표계만 확인(저장 0)
python scripts/collectors/fetch_seoul_district.py                  # 상권영역 zip 받기 (2.07MB, 로그인 불필요)
python scripts/collectors/load_seoul_district.py --dry-run         # SHP → district 미리보기 (DB 쓰기 0)
python scripts/collectors/load_seoul_district.py                   # 적재 (1,650개, 한 트랜잭션 — 실패 시 통째 롤백)
# ↑ pyshp 필요: python -m pip install pyshp  (순수 파이썬, GDAL 불필요. CI 에는 안 깔려 있고 안 깔아도 된다)
python scripts/collectors/fetch_sbiz_district.py --probe           # 소진공 주요상권현황 크기·메타만 확인(저장 0)
python scripts/collectors/fetch_sbiz_district.py                   # 전국 주요상권 CSV 받기 (30.5MB, 로그인 불필요)
python scripts/collectors/load_sbiz_district.py --dry-run          # CSV → district 미리보기 (DB 쓰기 0, 기본 대전만)
python scripts/collectors/load_sbiz_district.py                    # 대전 37개 적재 — ⚠️ 서울(11)은 코드가 거부한다(정본 이원화 방지)
python scripts/collectors/load_nts_base_price.py --dry-run         # 국세청 기준시가 zip → 미리보기 (DB 쓰기 0, 관문 4종 리포트)
python scripts/collectors/load_nts_base_price.py                   # ★ 호실 249만 행 적재 (한 트랜잭션 — 관문 걸리면 통째 롤백, 결정 0021)
# ↑ 원본 = data/raw/nts_base_price/ zip (포털 3036455). 국세청 고시는 연 1회(다음 2027-03 예정) —
#   자동 감시 없음(결정 0021): 매년 3월 사람이 재다운로드 → 재적재 → post_load.py
python scripts/build_rone_map.py --seed scripts/seeds/district_rone_map.csv    # ★ 매핑 seed 고쳤으면 커밋 전 이 관문(exit 0)
# ↓ 부동산원 임대동향 갱신. ⛔ **그물 6호의 '지남' 경보는 "예정일이 지났다"이지 "새 분기가 떴다"가 아니다** — R-ONE 화면에서 새 분기 게시를
#   **먼저 눈으로 확인**하고 `--end-qid <게시된 분기>` 를 꼭 준다. 안 주면 기본값이 '지금 분기'라 아직 없는 분기까지 씨앗을 뿌리고,
#   미공표 분기는 0건 응답이 `done` 으로 굳어(이어받기는 pending 만 본다) 나중에 판이 떠도 "이미 다 걷었습니다"가 된다(오류로 왔으면 `--retry-failed`).
python scripts/collectors/collect_rone.py --dry-run --end-qid <분기> --quarters 1   # 미리보기 — ⚠️ `--dry-run` 도 `collect_progress` 에 pending 씨앗을 쓴다(collect_transactions 와 같다)
python scripts/collectors/collect_rone.py --end-qid <분기> --quarters 1             # R-ONE API → raw JSONL (이어받기 · 4유형×6지표)
python scripts/collectors/load_rone.py --dry-run                   # raw → rent_stat 미리보기(DB 쓰기 0)
python scripts/collectors/load_rone.py                             # rent_stat 적재 → 끝나면 post_load.py · --check (⚠️ 게시 시기 근거가 없다 — 알려진한계 §3)
# ↓ 서울 상권 개업·폐업(결정 0033 — 서울시 공표값 그대로 · 인증키 = .env 의 SEOUL_OPENAPI_KEY). ⛔ `--end-quarter` 는 의무(기본값 없음) —
#   게시된 분기를 dry-run 으로 먼저 확인한다(미게시 분기는 INFO-200 → done 으로 굳히지 않고 pending 유지).
#   ⛔ 수집을 다 끝낸 뒤 **같은 날** 마이그레이션 2026-10-05b → 적재를 **한 번에**(일부 분기만 넣으면 신선도가 '지났습니다').
python scripts/collectors/collect_seoul_openclose.py --dry-run --end-quarter <분기> --quarters 22  # API 1회로 행수 + 장부 읽기만 (DB 쓰기 0)
python scripts/collectors/collect_seoul_openclose.py --end-quarter <분기> --quarters 22           # API → data/raw/seoul_openclose/api/ (이어받기 · 최신 분기부터 · 22분기 ≈ 1,700회)
python scripts/collectors/load_seoul_openclose.py --dry-run        # raw(API jsonl·연도 zip) → 관문 7(⒜~⒢) 리포트 (DB·파일 쓰기 0)
python scripts/collectors/load_seoul_openclose.py                  # district_openclose 분기 단위 교체 (한 트랜잭션) → post_load.py · --check
# ↑ ⚠️ 약 170만 행을 지우고 다시 넣어 디스크가 한 번 크게 는다 — 적재 **직전** 디스크 %(85% 이상이면 디스크 확장부터 — 인허가 적재와 같은 기준, PROGRESS 1735줄)와 앞뒤 `pg_total_relation_size('district_openclose')` 를 재서 PROGRESS 에 적는다(「2026-10-06 (8)」)
# ↑ 키가 막힌 날의 대비책 = fetch_seoul_openclose_zip.py --year <연도> (연 1회 zip · 인증키 없음)
python scripts/load_rone_map.py --dry-run                          # seed → district_rone_map 미리보기(DB 쓰기 0)
python scripts/load_rone_map.py                                    # 매핑 적재 (검증 관문 3종 내장 — 걸리면 통째 롤백)
python scripts/build_district_geojson.py --dry-run                  # 지도용 상권 파일 미리보기(행수·크기만, 파일 안 씀)
python scripts/build_district_geojson.py                           # ★ district 를 적재했으면 → public/districts.geojson 굽고 **커밋**
python scripts/build_scorecard_json.py --dry-run                    # 성적표 파일 미리보기(줄 수·크기·원본 해시만, 파일 안 씀)
python scripts/build_scorecard_json.py                              # ★ 성적표 CSV 가 바뀌었으면 → public/scorecard-v1.json 다시 굽고 **커밋**
# ↑ 입력 = docs/backtest/{단계별지표,운영모드지표,통과구}.csv + 성적표-v1.md 의 생성 시각 한 줄.
#   ⛔ 검증거래별원자료.csv(개별 실거래)는 **안 읽는다**. 판(v2)을 올리는 것은 별건 결재라
#      그때 스크립트의 VERSION·출력 파일명·src/lib/appConstants.ts 의 SCORECARD_URL 을 함께 올린다.
python scripts/post_load.py                     # ★ 적재 후 필수 — vacuum(analyze) + 요약표(REFRESH_MVS 목록이 정본) 갱신 (권한 점검은 안 돈다)
python scripts/post_load.py --check              # 낡았나 + 공개 롤이 읽거나 **고칠 수** 있는 것 점검 (DB 쓰기 0, 걸리면 exit 1)
python scripts/publish_snapshot.py --show        # 분기 표지(다 들어온 분기 · 보여 주는 분기) + 점포 표 분기별 행수 + 요약표 셋의 분기 (읽기만)
python scripts/publish_snapshot.py --ym <분기>   # 표지 두 칸을 그 분기로(되돌리기·RPC 실패 대응 · 점포 표에 있는 분기만) → 이어서 post_load.py
python scripts/make_env_local.py                # .env → .env.local (브라우저용 공개키만)
python scripts/setup_git_hooks.py               # ★ 새 컴퓨터에서 한 번 — main 잠금(로컬 알람) 켜기 + 깃헙 잠금 함께 확인
python scripts/setup_git_hooks.py --check       # 양쪽 잠금이 제자리인가 (아무것도 안 바꿈, 어긋나면 exit 1)
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
> ⛔ **줄바꿈도 같은 종류다** — 저장소·CI 에는 LF 로 들어 있고 윈도우 작업본만 CRLF 다. "CRLF 수 = LF 수"를 단언하는 시험은 윈도우에서 초록·CI 에서 빨강이다(2026-10-01 #174 — 검사관이 LF 사본으로 흉내 내 잡음). 줄바꿈 시험은 **"섞이지 않음"**(`CRLF 수 in (0, LF 수)`)만 본다.

> ⛔ **소스에 눈에 안 보이는 문자를 실제 글자로 쓰지 않는다** (2026-10-02 #186 — `tests/test_no_invisible_chars.py` 가 추적 파일 전부를 훑는다).
> 도구가 이스케이프 표기를 **실제 문자로 바꿔 넣는** 일이 있다 — 정규식의 단어 경계 일곱 자리에 실제 백스페이스가 들어가
> `test_api_schema_migration.py` 의 기본권한 가드가 한 달(2026-09-03 #114 ~ 10-02) **아무것도 못 잡는 채 초록**이었다(정본은 멀쩡 — 피해 없음).
> BOM·줄 안 바꾸는 공백·폭 없는 공백이 필요하면 파이썬·JS 문자열 안의 **이스케이프 표기**로 적고, 넣은 뒤 **바이트로 센다**(화면은 근거가 아니다).
> 새 이미지·PDF 를 추적에 넣으면 그 시험의 `BINARY` 표에, UTF-8 이 아닌 글 파일이면 `NON_UTF8` 표에 올린다(표 밖이면 빨강).
> ⚠️ 이 가드는 **`git add` 한 파일만** 본다 — 새 파일은 올리기 전 pytest 에서는 안 걸리고 CI 에서 걸린다.
> ⛔ **"없음"을 단언하는 시험에는 "실제로 잡는지" 보는 양성 대조를 짝으로 둔다** — 위 죽은 가드가 `assert not found` 하나뿐이었다.
> ⛔ **탐지는 그 시험 파일 안의 작은 함수로 빼서, 가드 본체와 양성 대조가 같은 함수를 지나게 한다** (2026-10-02 #190 — 정적 가드 157개 전수 감사: 죽음 2 · 흔한 꼴만 잡는 '부분' 54).
> 글자 통째 비교·줄머리 고정(`^create`)·맨 이름 `not in`(허용 목록은 `스키마.이름` 꼴이다)은 조금 바꾼 꼴을 놓친다 — 양성 대조에 **흔한 꼴 + 변형 꼴 하나**를 넣고,
> 탐지가 못 보는 꼴은 그 함수 머리말 「못 보는 것」에 적는다. 넓힌 탐지가 지금 저장소에 걸리면 좁히지 말고 그 줄이 진짜 위반인지부터 본다(적용된 마이그레이션 = 원장에 걸리면 고칠 수 없으니 명시 표로 뺀다).

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
