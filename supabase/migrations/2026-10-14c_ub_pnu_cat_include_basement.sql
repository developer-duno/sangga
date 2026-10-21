-- =====================================================================
-- 마이그레이션 2026-10-14c — 점포 색인 idx_ub_pnu_cat 의 include 에 '지하인데 층 모름' 칸 (물결 2-2c PR②)
-- =====================================================================
-- 실행법 ⚠️ **대시보드 SQL Editor 로는 안 된다.**
--   `create index concurrently`·`drop index concurrently` 는 트랜잭션 블록 안에서 못 돈다.
--   SQL Editor 는 스크립트 전체를 한 트랜잭션으로 감싸므로 25P02 로 죽는다(2026-09-27b·27e·10-09c 와 같은 사정).
--   → `python scripts/dbx.py -f supabase/migrations/2026-10-14c_ub_pnu_cat_include_basement.sql`
--   ⛔ 그래서 이 파일은 begin/commit 으로 감싸지 않는다.
--
-- ⛔ 적용 순서 = **2026-10-14a(칸) → 이 파일(14c) → 2026-10-14b(층 묶음 함수·요약표·list 함수)**.
--   · 14a 전에는 칸이 없어 첫 문장(create index)에서 멈춘다(옛 색인은 그대로 — 화면 영향 없음).
--   · 14b 만 먼저 들어가면 반경 층 집계(list_industry_floors 의 rsub)가 새 칸을 꺼내는데 include 에 없어
--     Index Only Scan → 힙 방문으로 돌아간다(2026-10-09c 가 고친 찬 캐시 3.3초 병 — 14b 맨 앞 관문이 막는다).
--   · 이 파일 뒤·14b 전에는 `post_load.py --check` 의 정본 색인 점검이 정본과 같다(정본이 이미 여섯 칸) —
--     다만 PR② 를 머지하기 전 main 의 정본은 다섯 칸이라 그 사이 main 판 `--check` 는 [사고]가 정상이다
--     (그 창에서는 PR 가지 판으로 잰다 · 플랜 v2 §3.3).
--
-- 운영 순서 ⚠️ **분기 적재(load_sangkwon_snapshot.py)·post_load.py 와 동시에 돌리지 않는다.** concurrently 는 표를
--   만지는 다른 트랜잭션이 끝나기를 기다리는데, 적재가 약 2시간 동안 1,000행씩 쓰는 중이면 그 기다림이
--   길어지고 900s 에 끊기면 아래 "실패하면" ⓐ 상태(invalid _next)가 된다.
--   ⚠️ **배치 창(01:30~12:00) 밖에서** 돌린다(luxury_resale 배치가 같은 PC 의 CPU 를 쓴다).
--   걸리는 시간 = 수 분(점포 표 약 339만 행 — 09c 실측 36초) · 디스크는 교체가 끝날 때까지 **일시적으로
--   약 +300MB + 기록(WAL)**(새 색인과 옛 색인이 잠깐 함께 있다 — 옛 것을 지우면 돌아온다 · 옛 `idx_ub_pnu_cat`
--   2026-10-13 실측 300MB, 새 것은 boolean 1바이트만큼 조금 더 크다).
--   ⛔ **적용 직전 디스크 % 를 잰다 — (지금 사용량 + 300MB + WAL 여유 1GB) 가 85% 이상이면 미룬다**(디스크 확장(10/26~30) 뒤로).
--
-- 왜
--   2026-10-14b 가 층 묶음을 floor_no 하나가 아니라 (floor_no, floor_basement_unknown) 둘로 정한다 — 숫자 없이
--   '지'라고만 적힌 가게(floor_no NULL · 칸 true)를 지하 묶음 'b' 로 세려고(👤 2026-10-13 「지하 칸에 넣기」).
--   반경 층 집계는 점포 표를 이 색인으로 찾는데, 꺼내는 칸이 하나 늘었다. include 에 없으면 행마다 힙에 간다.
--
-- 다른 조회에 주는 영향: include 를 **늘리기만** 하므로 이 색인을 쓰던 조회는 그대로 쓴다(09c 와 같은 판단 —
--   list_industry_mix·list_industry_detail 의 반경 집계 · mv_parcel_store_names 의 가게 이름 모으기).
--
-- 어떻게: include 칸은 ALTER 로 못 더한다 → 새 이름(_next)으로 만들고, **관문**(_next 가 valid 이고
--   정의에 floor_basement_unknown 이 있나)을 통과해야만 옛 것을 지우고, 이름을 옛 이름으로 되돌린다.
--   칸 순서는 정본(schema.sql)과 같아야 한다 — post_load --check 의 정본 색인 점검이 INCLUDE 를 순서까지 대조한다.
--
-- 잠금 (PostgreSQL 17 공식 문서 — 2026-09-27e 머리말에 원문 인용 · 09c 와 같다):
--   create/drop 은 concurrently 라 표를 잠그지 않는다(적용 중에도 화면은 그대로 돈다).
--   alter index … rename 은 SHARE UPDATE EXCLUSIVE — 화면 읽기·적재 쓰기와 부딪치지 않는다. 같은 표의
--   vacuum·analyze 와는 부딪칠 수 있어 `set lock_timeout = '2s'` 를 **그 문장 앞**(세션 설정)에 둔다.
--
-- 시간 제한: 맨 앞의 `set statement_timeout = '900s'` 를 **지우지 말 것.** dbx.py 연결의 제한은 2분이다.
--
-- 실패하면 (dbx.py 는 ON_ERROR_STOP=1 이라 오류가 난 문장에서 멈춘다 — 09c 와 같은 세 갈래):
--   ⓐ _next 만들기에서 끊김 → `idx_ub_pnu_cat_next` 가 **invalid** 로 남는다. 옛 idx_ub_pnu_cat 은 멀쩡하다.
--      할 일: `drop index concurrently if exists idx_ub_pnu_cat_next;` 뒤 파일을 다시.
--   ⓑ 옛 색인 지우기에서 끊김 → 파일을 다시 돌리면 _next 는 건너뛰고(valid 라 관문 통과) 다시 지운다.
--   ⓒ 이름 바꾸기가 lock_timeout(55P03)으로 실패 → 잠시 뒤 두 줄만 다시:
--        set lock_timeout = '2s';
--        alter index idx_ub_pnu_cat_next rename to idx_ub_pnu_cat;
--
-- 되돌리기 (include 다섯 칸으로 — 같은 꼴). ⚠️ 2026-10-14b 를 이미 적용했으면 먼저 14b 를 되돌린다(층 함수가 새 칸을
--   꺼내는 동안 이 색인을 줄이면 찬 캐시가 다시 느려진다). 남은 _prev 가 있으면 `drop index concurrently if exists idx_ub_pnu_cat_prev;` 부터:
--     set statement_timeout = '900s';
--     create index concurrently if not exists idx_ub_pnu_cat_prev on unit_business (pnu, snapshot_ym)
--       include (cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, floor_no);
--     drop index concurrently if exists idx_ub_pnu_cat;
--     set lock_timeout = '2s';
--     alter index idx_ub_pnu_cat_prev rename to idx_ub_pnu_cat;
--   (되돌리면 schema.sql 의 정의도 다섯 칸으로 함께 되돌린다 — 안 그러면 post_load --check 가 [사고].)
--
-- 적용 뒤 확인:
--   ① select c.relname, i.indisvalid, pg_get_indexdef(i.indexrelid)
--        from pg_index i join pg_class c on c.oid = i.indexrelid
--       where c.relname like 'idx_ub_pnu_cat%';
--      → **한 줄만**: 이름 idx_ub_pnu_cat · indisvalid = t ·
--        INCLUDE (cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, floor_no, floor_basement_unknown).
--   ② (14b 까지 적용한 뒤) python scripts/post_load.py --check → 정본 색인 점검 [정상](PR② 가지 판으로).
--   ③ (14b 뒤) list_industry_floors 반경 부분을 강남 1168010600109420015 · I2 로 EXPLAIN (ANALYZE, BUFFERS)
--      → unit_business 쪽이 Index Only Scan · Heap Fetches 0 인지(아니면 `vacuum (analyze) unit_business;`).

set statement_timeout = '900s';

create index concurrently if not exists idx_ub_pnu_cat_next on unit_business (pnu, snapshot_ym)
  include (cat_l_cd, cat_l_nm, cat_m_cd, cat_m_nm, floor_no, floor_basement_unknown);

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
       and pg_get_indexdef(i.indexrelid) like '%floor_basement_unknown%'
  ) then
    raise exception 'idx_ub_pnu_cat_next 가 없거나 invalid 이거나 floor_basement_unknown 이 없습니다 — 옛 색인은 안 지웠습니다. 다시 돌리기 전에 drop index concurrently if exists idx_ub_pnu_cat_next; 를 먼저 하세요';
  end if;
end $$;

drop index concurrently if exists idx_ub_pnu_cat;

set lock_timeout = '2s';
alter index idx_ub_pnu_cat_next rename to idx_ub_pnu_cat;
