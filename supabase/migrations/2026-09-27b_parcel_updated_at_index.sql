-- =====================================================================
-- 마이그레이션 2026-09-27b — 신선도 표의 큰 표 세 줄에 색인
--   (parcel.updated_at · building.updated_at · transaction.contract_ym 의 최댓값)
-- =====================================================================
-- **라이브 적용 2026-09-27 14:25 KST**(`python scripts/dbx.py -f`, 7초 · 색인 3개 indisvalid=t, 8,016kB·1,760kB·2,336kB ·
--   get_data_freshness() 전체 2,412ms → 12~16ms · parcel 줄 2,187~3,063ms → 9ms).
--
-- 실행법 ⚠️ **대시보드 SQL Editor 로는 안 된다.**
--   `create index concurrently` 는 트랜잭션 블록 안에서 못 돈다. SQL Editor 는
--   스크립트 전체를 한 트랜잭션으로 감싸므로 25P02 로 죽는다(2026-08-11f 와 같은 사정).
--   → `python scripts/dbx.py -f supabase/migrations/2026-09-27b_parcel_updated_at_index.sql`
--   ⛔ 그래서 이 파일은 begin/commit 으로 감싸지 않는다.
--
-- 왜 (2026-09-27 라이브 실측)
--   화면 아래 "이 자료는 언제 것인가" 표 = api.get_data_freshness() → 열 갈래 자료의 최댓값.
--   그중 `max(updated_at) from parcel` 한 질의만 **2,187ms → 두 번째 3,063ms** 였다
--   (나머지 아홉은 10~75ms). anon 의 statement_timeout 이 3초라 표가 통째로 사라질 수 있는
--   자리다. ⚠️ 이 표는 페이지를 열 때 **한 번만** 부른다(DataFreshness 의 effect 의존이 빈 배열,
--   AppFooter 에 key 없음). 첫 측정에서 "구를 고를 때마다 2.4초"로 보인 것은 요청을 **끝난 시각**으로
--   귀속한 착시였다(2026-09-27 마무리 검사관 C — 요청 시작이 구 클릭보다 앞섰다). 그래서 이 색인의
--   값은 체감 단축이 아니라 ①3초 제한에 걸려 표가 조용히 사라지는 것을 막고 ②페이지를 열 때마다
--   416MB 를 통째로 훑던 DB 부하를 없애는 것이다.
--   parcel 은 1,119,149행 · 416MB 인데 색인 6개 중 updated_at 을 받치는 것이 없어 전수를 훑는다.
--   btree 하나면 max() 는 색인 끝 한 칸만 읽는다.
--
--   같은 함수의 나머지 큰 표 둘도 받칠 색인이 없다 — building.updated_at(242,631동, 64ms)과
--   transaction.contract_ym(327,183행, 75ms — 기존 idx_tx_* 는 pnu·sigungu_code 가 앞 칸이라
--   max(contract_ym) 을 못 받친다). 지금은 둘 다 수십 ms 라 **체감은 없다.** 그래도 거는 이유는
--   전국 확장(건물·실거래가 지금의 몇 배)으로 가는 날 에러 없이 **조용히 느려지는 자리**라서다
--   (parcel 이 바로 그 경로로 3초에 닿았다). 사장님 결정 2026-09-27 "세 표 모두".
--
-- 잠금: concurrently 라 표를 잠그지 않는다(적용 중에도 화면·검색은 그대로 돈다).
--
-- 시간 제한: 맨 앞의 `set statement_timeout = '900s'` 를 **지우지 말 것.** dbx.py 연결의
--   제한은 2분이다(2026-09-27 실측). concurrently 가 그 제한에 끊기면 **invalid 색인이 남고**
--   아래 "실패하면" 절차가 필요해진다. 2026-08-22c(900s)·2026-08-31b(300s) 와 같은 선례.
--
-- 실패하면: concurrently 가 도중에 끊기면 **invalid 색인이 남는다**(`if not exists` 가 그걸
--   "있다"고 보고 건너뛰므로 그냥 다시 돌리면 안 고쳐진다). 끊긴 것을 먼저 지우고 다시 돌린다
--   (valid 로 끝난 것은 `if not exists` 가 건너뛰므로 셋 다 다시 돌려도 된다):
--     drop index concurrently if exists idx_parcel_updated_at;
--     drop index concurrently if exists idx_building_updated_at;
--     drop index concurrently if exists idx_tx_contract_ym;
--
-- 되돌리기:
--     drop index concurrently if exists idx_parcel_updated_at;
--     drop index concurrently if exists idx_building_updated_at;
--     drop index concurrently if exists idx_tx_contract_ym;
--
-- 적용 뒤 확인:
--   ① select c.relname, i.indisvalid from pg_index i join pg_class c on c.oid = i.indexrelid
--        where c.relname in ('idx_parcel_updated_at', 'idx_building_updated_at',
--                            'idx_tx_contract_ym');   -- 세 줄 모두 참(t) 이어야 한다
--   ② get_data_freshness() 를 다시 재서 필지 줄이 수십 ms 로 내려왔는지 본다.

set statement_timeout = '900s';

create index concurrently if not exists idx_parcel_updated_at on parcel (updated_at);

create index concurrently if not exists idx_building_updated_at on building (updated_at);

create index concurrently if not exists idx_tx_contract_ym on transaction (contract_ym);
