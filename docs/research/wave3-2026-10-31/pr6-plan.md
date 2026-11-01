# PR⑥ 서울 지하철 승하차 — 플랜 보강(2026-11-02 · 플랜 v2 §1 PR⑥ + 맹점 지적 4번 + 실측 ⓐ~ⓖ 반영) — 👤 결정 반영판(01:3x)

정본 = `docs/decisions/0045` 순서표 ⑥ · 플랜 v2 §1 PR⑥ · 실측 = `D:/tmp/sangga-wave3/pr6-prework.md` · 구현 지시서 = `D:/sangga/.omc/handoffs/pr6-subway-brief.md`(백엔드 · 11-02 01:3x 스폰) → 화면 지시서는 백엔드 뒤.
👤 결정(2026-11-02 · 시안 https://claude.ai/artifact/2zKm45w64FSiLUYDDXb8hM): ① 신선도 날짜 **가**(서울시 세 줄 +5개월 → +6개월 · 이 PR 신선도 마이그에 묶음) · Q1 환승역 **가**(역 이름 + 600m 묶음으로 합침) · Q2 자료 없는 노선 **가**(역은 보이되 「승하차 자료 없음」) · Q3 역 없을 때 **가**(없다는 한 줄 + 가장 가까운 역·거리(1.5km 안)) · Q4 숫자 꼴 **나**(승차·하차 나란히 + 시간대 막대 여섯 칸 4~7·7~10·10~14·14~17·17~21·21~ 이번에).
메인 결정: 함수 status 에 `no_data`(표 비었거나 승하차 없음 → 덩이 숨김 · 마이그→머지→적재 사이 거짓 「역 없음」 방지) · 하루 평균 = 창 안 합 ÷ 그 달들의 일수 합 · 운영 순서 = 마이그(DB 먼저) → 머지 → 본 폴더 수집(71회) → 적재 → post_load · --check(워크트리엔 .env 없음).

## 0. 범위(바뀐 것만)
- 반경 500m · 「상권 인구」 카드 안 한 덩이 · 「승하차 인원(카드 기준)」 · 서울만 — 그대로.
- **환승역은 역 이름(+600m 안)으로 합친다**(실측 ⓒ — 관리 호선 몰아 세기) — Q1.
- **자료 없는 노선 역은 보이되 「승하차 자료 없음」**(신분당선·GTX·김포골드라인) — Q2.
- **0개(35.7%)는 정상 상태** + 가장 가까운 역 한 줄 — Q3.
- 발 문구 셋 = 실측 ⓔ 제안 꼴(「환승객 두 번」·「현금 미포함」 삭제).
- 「N개월 평균」: 최근 12개월 창에서 실제 센 달 수 < 12 면 「N개월 평균」(새 역·빠진 달).

## 1. 수집기 `scripts/collectors/collect_seoul_subway.py`(0033·PR② 꼴 복제 · 같은 키 `SEOUL_OPENAPI_KEY`)
- `--master`: 역사마스터 전부(1쪽) → `data/raw/seoul_subway/master/<YYYYMMDD>.json`(받은 날마다 새 파일 · 덮어쓰기 0).
- `--months --end-month <YYYYMM> --months-back 72`(기본 2021-01~): 달마다 1~2쪽 → `data/raw/seoul_subway/ridership/<YYYYMM>_<받은 날>.jsonl` · `collect_progress`(collector `seoul_subway` · scope `seoul` · 열쇠 = 달) 이어받기 · **INFO-200 = pending 유지 + 경고**(미게시 달 · 0033 그대로) · `--end-month` 의무(기본값 없음 — 포털 게시 확인 뒤).
- `--dry-run` = API 1회(행 1개로 총건수) + 장부 읽기만.
- 호출 ≈ 72(처음) · 매달 1.

## 2. 적재기 `scripts/collectors/load_seoul_subway.py`(0044 꼴 · 한 트랜잭션 · 관문 걸리면 롤백)
- 씨앗 둘(`scripts/seeds/`): `subway_line_map.csv`(승하차 호선 표기 → 마스터 표기 3줄) · `subway_station_map.csv`(승하차 (역, 호선) → 마스터 (역, 호선) 6줄 + 허용 미매칭 3줄(한국항공대·자양·초성리 — 좌표 없음 · 세어 뺌)).
- 관문: ⒜ 마스터 행 수 700~900 · 좌표 빈 칸 0 · WGS84 범위 ⒝ 달마다 중복 뺀 행 550~700 · 중복은 값 완전 동일일 때만 ⒞ 호선 표기가 승하차 27종 + 씨앗 밖이면 멈춤 ⒟ 조인 뒤 미매칭 ≤ 10행 · 전부 허용 목록 ⒠ 승차합 ≥ 1억 ⒡ 빠진 달 보고(멈추진 않음 — 「N개월 평균」) ⒢ 역 묶음(이름+600m) 수 보고 · 600m 넘어 갈린 묶음 목록 보고.
- 표: `subway_station`(station_id pk · name · name_norm · line · group_id · lat·lng · geom Point 4326 + gist((geom::geography)) · has_ridership) · `subway_ridership_m`(**pk = (use_mm, ride_line_nm, ride_sttn_nm) 원문 열쇠** · station_id fk 유일 아님 — 짝표 뒤 같은 역에 원문 두 줄이 모이는 경우(창동 4호선+경원선 · 김포공항 공항철도+경의선 라벨)를 둘 다 둔다 · 함수가 묶음으로 더한다 · 01:4x 대조 검사 🔴 정정) · on_sum · off_sum · 48 시간대 칸 · job_ymd) · 표지 없음(기준 = max(use_mm)) · 둘 다 anon 닫힘 · `ANALYZE_TABLES` +2.
- 마스터는 **upsert + 승하차 참조 없는 사라진 역만 delete**(FK 때문 · 「통째 교체」에서 바꿈) · 승하차는 달 단위 교체(쌓기만) · INFO-200 빈 봉투 달은 「자료 없음」으로 건너뜀.
- 조인 관문 = **원문 90% 유지(분모 = 중복 뺀 행 − skip 행) + 미매칭 ≤ 10행 전부 skip 목록**(실측 98.7~99.5%) · 0 값 역 수는 dry-run 리포트에(plan v2 요구).

## 3. 마이그 `2026-11-0Xa_seoul_subway.sql`
- 표 둘 + 색인 + 함수 `list_nearby_subway(p_pnu text)` + `api.` 쌍둥이(grant anon = api 만) + 신선도 함수 재생성(ord 18 「지하철 승하차 (서울시)」 · 갈래 `subway` = (기준월 + 2개월)의 5일 · **서울시 세 줄(11·13·14)의 `seoul_openclose` 규칙 +5 → +6개월**(👤 가) · comment 갈래 수 · 머리·comment 글자 대조 시험) · 허용 38 → 39.
- 함수 꼴: me(parcel pk · char(19)) → head(no_coord → not_seoul(앞 두 자리 ≠ 11) → 없으면 null) → 역 묶음: `st_dwithin(me.gg, s.geog, 500, false)` 로 역 줄을 찾고 group_id 로 묶음 · 묶음마다 거리 = min · lines = 호선 배열(승하차 있는 호선 / 없는 호선 구분) · 최근 12개월 창(표 max(use_mm) 기준) 합 → 하루 평균 = Σ(on+off) ÷ Σ(그 달 일수) · months_n(실제 센 달) · on_daily · off_daily · latest_mm · has_data · status = `ok` / `no_station`(0개 — nearest_name·nearest_dist_m 한 줄 · 1.5km 안 KNN `<->`) · 정렬 거리순 · 상한 10줄.
- 되돌리기 절(0045 171 규칙 — 직전 마이그부터 역순).

## 4. 화면(서울 `PopSection` 안 덩이 — `lib/subwayNearby.ts` 순수 계산 · 미리 부르기 `SEOUL_PREFETCH_FNS` +1)
- 덩이 머리 「가까운 지하철역 승하차 인원 (카드 기준 · 건물 500m 안)」 · 역마다 「충무로 (3·4호선) · 180m」 + 큰 숫자 「하루 평균 승하차 63,900명」 + 작은 글 「승차 31,600 + 하차 32,300 · 최근 12개월(2025년 10월~2026년 9월)」 · 자료 없는 노선은 「승하차 자료 없음 — 서울시 자료 밖 노선」 · 0개 = 「500m 안에 지하철역이 없습니다 · 가장 가까운 역 ○○ 820m」 · 발 문구 셋(ⓔ) · 날짜 줄 `CARD_SOURCES.subway`(「서울시 지하철 승하차 2026년 9월분」) · `SECTION_PLAN.pop.sources` += `subway` · 모양 검사 실패·PGRST202 → 덩이만 생략(카드는 그대로) · 화면에 분기·연도 글자 0 · 「유동인구」 낱말 0 · 비율 재계산 0 · 대전 카드(SGIS) 변화 0 · 휴대폰·종이 · E2E 넓은·412.

## 5. 둘레
- `check_data_freshness.py` `SOURCE_HINTS["지하철 승하차 (서울시)"]`(수집 `--end-month` → 적재 → post_load) · 그물 6호 시험 · `post_load.py` 허용 39 · `ANALYZE_TABLES` · `backup_raw.py`(data/raw 전체 os.walk 라 새 폴더 자동 — 확인만) · CLAUDE.md 명령 표 + 📅 매달 할 일 ③ 지하철 · 백서 카드 +1(19 → 20종) · 알려진한계 §3(환승역 몰아 세기 · 자료 없는 노선 · 마스터에 없는 새 역) · feature-notes · 0045 순서표 ⑥ + 「확인 못 한 것」 실측 옮김 · 데이터백서.
- 시험: 수집기·적재기 pytest(관문마다 + 양성 대조) · 마이그 글자 대조 + 로컬 PG 실행(함수 결과 · 600m 묶음 · 12개월 창 · no_station) · 신선도 시험 손질(`interval '5 months'` 1회 단언 → 5·6 둘 · 20262 → 2026-11-30 · 파이썬 거울 +6) · vitest(순수 계산 · 덩이 · 모양 검사 · 문구 가드) · E2E 1~2.
- 운영 반영: 디스크 판정 → 마이그(DB 먼저 · 👤 여쭘) → **적용 직후 EXPLAIN 으로 gist·KNN 계획 확인**(로컬 PG 엔 PostGIS 가 없어 시험은 흉내 판 — 01:4x 작업반 실측 · 내 전제 ②-12 「PostGIS 있음」은 틀림) → 머지 → 본 폴더 수집(마스터 + 70달 = 71회) → dry-run → 적재(+약 25MB) → post_load · --check(허용 39) → 라이브 확인 → 11/02 그물 이슈 셋 닫기(날짜가 11-30 으로 바뀐 뒤) → backup_raw → 문서 PR.

## 6. 검사
- 적대 Opus(백엔드·마이그 포함) + 맹점 Opus(트랙 끝 PR) · 할루 Sonnet 은 1단 때.
