-- =====================================================================
-- 마이그레이션 2026-10-09c — 점포 색인 idx_ub_pnu_cat 의 include 에 층(floor_no) (물결 2-2)
-- =====================================================================
-- 실행법 ⚠️ **대시보드 SQL Editor 로는 안 된다.**
--   `create index concurrently`·`drop index concurrently` 는 트랜잭션 블록 안에서 못 돈다.
--   SQL Editor 는 스크립트 전체를 한 트랜잭션으로 감싸므로 25P02 로 죽는다(2026-09-27b·27e 와 같은 사정).
--   → `python scripts/dbx.py -f supabase/migrations/2026-10-09c_ub_pnu_cat_include_floor.sql`
--   ⛔ 그래서 이 파일은 begin/commit 으로 감싸지 않는다.
--   ⓘ 적용 순서 = **이 파일(09c) 먼저 → 2026-10-09b(층 분포 요약표·함수)**. 09b 만 든 동안에는 층 함수가
--     힙을 방문해 찬 캐시 약 3.3초가 걸리고, 이 파일 전에는 `post_load.py --check` 의 정본 색인 점검이
--     INCLUDE 불일치로 [사고]다(정본 schema.sql 은 이미 floor_no 를 담고 있다).
--
-- 운영 순서 ⚠️ **분기 적재(load_sangkwon_snapshot.py)와 동시에 돌리지 않는다.** concurrently 는 표를
--   만지는 다른 트랜잭션이 끝나기를 기다리는데, 적재가 약 2시간 동안 1,000행씩 쓰는 중이면 그 기다림이
--   길어지고 900s 에 끊기면 아래 "실패하면" ⓐ 상태(invalid _next)가 된다.
--   ⚠️ **배치 창(01:30~12:00) 밖에서** 돌린다(luxury_resale 배치가 같은 PC 의 CPU 를 쓴다 · 적재와 동시 금지).
--   걸리는 시간 = 수 분(점포 표 약 339만 행) · 디스크는 교체가 끝날 때까지 **일시적으로 약 +280MB + 기록(WAL)**
--   (새 색인과 옛 색인이 잠깐 함께 있다 — 옛 것을 지우면 돌아온다 · 옛 `idx_ub_pnu_cat` 라이브 실측 279MB,
--   새 것은 floor_no 2바이트만큼 조금 더 크다 · 처음 머리말의 "+약 105MB" 는 틀렸다 — 2026-10-09 맹점 검사관).
--   ⛔ **적용 직전 디스크 % 를 잰다 — 85% 이상이면 미룬다**(디스크 확장(10/26~30) 뒤로 · 인허가 적재와 같은 기준).
--
-- 왜 (2026-10-09 라이브 실측 — 적용 전 · 강남 1168010600109420015 · 음식 I2 · list_industry_floors 의
--   반경 부분(rsub)을 풀어 EXPLAIN (ANALYZE, BUFFERS))
--   플래너는 idx_ub_pnu_cat (pnu, snapshot_ym) 를 고르는데, 층 칸(floor_no)이 include 에 없어서
--   **Index Only Scan 이 아니라 Index Scan** — 행마다 힙에 간다(이웃 598필지 · 점포 840 + 걸러진 4,482).
--     찬 캐시 3,292ms(read 4,539쪽 — 공개키 3초 제한을 넘는다) / 더운 캐시 12ms.
--   형제 list_industry_detail 은 업종 네 칸만 꺼내서 Index Only 다 — 2026-08-22c 가 '찬 캐시 2,383ms →
--   44.5ms' 로 고친 바로 그 병이 층 칸 하나 때문에 돌아온 것이다. include 에 floor_no 를 더하면 다시
--   Index Only Scan 이 된다(**추정** — 적용 뒤 같은 필지로 다시 잰다, 아래 ②).
--
-- 다른 조회에 주는 영향: include 를 **늘리기만** 하므로 이 색인을 쓰던 조회는 그대로 쓴다 —
--   ① list_industry_mix·list_industry_detail 의 반경 집계(업종 네 칸 — 여전히 다 include 안)
--   ② mv_parcel_store_names 의 가게 이름 모으기(pnu, snapshot_ym 로 찾고 biz_name 은 원래부터 힙)
--   색인 행이 floor_no(smallint 2바이트)만큼 커질 뿐 앞 두 칸(찾는 칸)은 같다.
--
-- 어떻게: include 칸은 ALTER 로 못 더한다 → 새 이름(_next)으로 만들고, **관문**(_next 가 valid 이고
--   정의에 floor_no 가 있나)을 통과해야만 옛 것을 지우고, 이름을 옛 이름으로 되돌린다.
--   이름을 그대로 두는 이유 = 정본·시험·문서가 전부 `idx_ub_pnu_cat` 라는 이름으로 이 색인을 가리킨다.
--
-- 잠금 (PostgreSQL 17 공식 문서 — 2026-09-27e 머리말에 원문 인용):
--   create/drop 은 concurrently 라 표를 잠그지 않는다(적용 중에도 화면은 그대로 돈다).
--   alter index … rename 은 SHARE UPDATE EXCLUSIVE — 화면 읽기(ACCESS SHARE)·적재 쓰기(ROW EXCLUSIVE)와
--   부딪치지 않는다. 같은 표의 vacuum·analyze 와는 부딪칠 수 있어 `set lock_timeout = '2s'` 를 **그 문장
--   앞**(세션 설정)에 둔다.
--   ⓘ _next 를 만든 뒤·이름을 되돌리기 전 잠깐은 색인 이름이 `idx_ub_pnu_cat_next` 다. 그동안에도
--     플래너는 이름이 아니라 정의로 고르므로 화면은 그대로 빠르다.
--
-- 시간 제한: 맨 앞의 `set statement_timeout = '900s'` 를 **지우지 말 것.** dbx.py 연결의 제한은 2분이다.
--   concurrently 가 끊기면 invalid 색인이 남는다(2026-09-27b·27e 와 같은 선례).
--
-- 실패하면 (어디서 멈췄는지 먼저 본다 — 아래 "적용 뒤 확인" ①). dbx.py 는 ON_ERROR_STOP=1 이라
--   오류가 난 문장에서 멈추고 뒤 문장은 안 돈다:
--   ⓐ _next 만들기에서 끊김 → `idx_ub_pnu_cat_next` 가 **invalid** 로 남는다. 옛 idx_ub_pnu_cat 은
--      멀쩡하다(화면 영향 없음). 다시 돌리면 `if not exists` 가 invalid _next 를 건너뛰지만 **바로 뒤
--      관문이 막는다**. 할 일: `drop index concurrently if exists idx_ub_pnu_cat_next;` 뒤 파일을 다시.
--   ⓑ 옛 색인 지우기에서 끊김 → 파일을 다시 돌리면 _next 는 건너뛰고(valid 라 관문 통과)
--      `drop … if exists` 가 다시 지운다.
--   ⓒ 이름 바꾸기가 lock_timeout(55P03)으로 실패 → 옛 것은 이미 없고 _next 만 valid 로 있다(속도는
--      이미 새 것). 잠시 뒤 두 줄만 다시:
--        set lock_timeout = '2s';
--        alter index idx_ub_pnu_cat_next rename to idx_ub_pnu_cat;
--   ⓘ 다 성공한 뒤 파일을 다시 돌려도 정상이다(같은 정의 한 벌 — 색인을 한 번 더 만드는 수고만 든다).
--
-- 되돌리기 (include 네 칸으로 — 같은 순서 · 같은 꼴). ⚠️ 되돌리기에는 관문이 없다 — 먼저 ① 로 지금
--   색인이 valid 인지, 끊겨 남은 _prev 가 없는지 본다(있으면 `drop index concurrently if exists idx_ub_pnu_cat_prev;` 부터):
--     set statement_timeout = '900s';
--     create index concurrently if not exists idx_ub_pnu_cat_prev on unit_business (pnu, snapshot_ym)
--       include (cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm);
--     drop index concurrently if exists idx_ub_pnu_cat;
--     set lock_timeout = '2s';
--     alter index idx_ub_pnu_cat_prev rename to idx_ub_pnu_cat;
--   (되돌리면 schema.sql 의 정의도 네 칸으로 함께 되돌린다 — 안 그러면 post_load --check 가 [사고].
--    그 대신 층 분포의 반경 줄은 찬 캐시에서 다시 느려진다.)
--
-- 적용 뒤 확인:
--   ① select c.relname, i.indisvalid, pg_get_indexdef(i.indexrelid)
--        from pg_index i join pg_class c on c.oid = i.indexrelid
--       where c.relname like 'idx_ub_pnu_cat%';
--      → **한 줄만**: 이름 idx_ub_pnu_cat · indisvalid = t · INCLUDE (cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, floor_no).
--        idx_ub_pnu_cat_next 가 남아 있으면 위 "실패하면" ⓒ.
--   ② python scripts/post_load.py --check → 정본 색인 점검이 [정상](INCLUDE 칸 순서까지 정본과 같다).
--   ③ list_industry_floors 반경 부분을 같은 필지(1168010600109420015 · I2)로 EXPLAIN (ANALYZE, BUFFERS)
--      → unit_business 쪽이 Index Only Scan · Heap Fetches 0 인지, 찬 캐시 3,292ms 가 얼마로 내려왔는지.
--      (Heap Fetches 가 0 이 아니면 가시성 지도가 낡은 것 — `vacuum (analyze) unit_business;` 또는 post_load.py)
--   ④ 같은 필지로 list_industry_mix 반경 부분도 한 번 — 여전히 Index Only Scan 인지(늘리기만 했으니 그래야 한다).

set statement_timeout = '900s';

create index concurrently if not exists idx_ub_pnu_cat_next on unit_business (pnu, snapshot_ym)
  include (cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, floor_no);

-- ── 관문: 옛 색인을 지우기 **전에** 새 색인이 쓸 만한지 본다 ─────────────────
-- `if not exists` 는 끊겨서 invalid 로 남은 _next 도 "있다"고 건너뛴다. 그 상태로 옛 색인을 지우면
-- 점포 표에 쓸 수 있는 pnu 색인이 하나도 안 남는다(에러 없이 화면만 느려진다). dbx.py 가
-- ON_ERROR_STOP=1 이라 여기서 raise 하면 뒤의 drop 은 안 돈다.
do $$
begin
  if not exists (
    select 1
      from pg_index i
      join pg_class c on c.oid = i.indexrelid
     where c.relname = 'idx_ub_pnu_cat_next'
       and i.indisvalid
       and pg_get_indexdef(i.indexrelid) like '%floor_no%'
  ) then
    raise exception 'idx_ub_pnu_cat_next 가 없거나 invalid 이거나 floor_no 가 없습니다 — 옛 색인은 안 지웠습니다. 다시 돌리기 전에 drop index concurrently if exists idx_ub_pnu_cat_next; 를 먼저 하세요';
  end if;
end $$;

drop index concurrently if exists idx_ub_pnu_cat;

set lock_timeout = '2s';
alter index idx_ub_pnu_cat_next rename to idx_ub_pnu_cat;
