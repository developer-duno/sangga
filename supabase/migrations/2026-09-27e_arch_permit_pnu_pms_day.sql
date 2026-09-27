-- =====================================================================
-- 마이그레이션 2026-09-27e — 인허가 색인 idx_arch_permit_pnu 의 include 에 허가일(arch_pms_day)
-- =====================================================================
-- 실행법 ⚠️ **대시보드 SQL Editor 로는 안 된다.**
--   `create index concurrently`·`drop index concurrently` 는 트랜잭션 블록 안에서 못 돈다.
--   SQL Editor 는 스크립트 전체를 한 트랜잭션으로 감싸므로 25P02 로 죽는다(2026-09-27b 와 같은 사정).
--   → `python scripts/dbx.py -f supabase/migrations/2026-09-27e_arch_permit_pnu_pms_day.sql`
--   ⛔ 그래서 이 파일은 begin/commit 으로 감싸지 않는다.
--
-- 운영 순서 ⚠️ **월간 적재(load_arch_permits.py)와 동시에 돌리지 않는다.** concurrently 는 표를
--   만지는 다른 트랜잭션이 끝나기를 기다리는데, 적재 트랜잭션(55만 행 \copy)이 길면 그 기다림이
--   900s 에 끊겨 아래 "실패하면" ⓐ 상태(invalid v2)가 된다.
--   권장 순서 = 적재 → 행 수 확인(`select loaded_ym, count(*) from arch_permit group by 1`)
--   → `python scripts/post_load.py` → 이 파일 → `python scripts/post_load.py --check` → EXPLAIN(아래 ②).
--
-- 왜 (2026-09-27 21시대 라이브 실측 — pnu 1168010500100240007, count_nearby_permits 본문을 풀어
--   EXPLAIN (ANALYZE, BUFFERS))
--   전체 808쪽 = 반경 이웃 찾기 746쪽 + 이 색인 58쪽. 이 색인 쪽이 **Index Only Scan 이 아니라
--   Index Scan** 이었다(hit 10·read 48 — 맞은 31행 + 걸러진 11행을 힙에서 읽음).
--   읽는 함수는 `a.real_stcns_day, a.arch_pms_day` 를 꺼내는데(2026-09-05b 부터 '2년 넘게 미착공'을
--   세려고 허가일을 읽는다) 색인 include 에는 허가일이 없어서 행마다 힙에 간다.
--   include 에 arch_pms_day 를 더하면 Index Only Scan 이 되어 58쪽 → 10~20쪽 예상(**추정** —
--   적용 뒤 같은 pnu 로 다시 잰다). 같은 날 사장님 결정으로 적재가 옛 달을 지우게 되어
--   (load_arch_permits.py build_sql) 표가 평소 한 달분이 되는 것과 한 PR 이다.
--
-- 어떻게: include 칸은 ALTER 로 못 더한다 → 새 이름(v2)으로 만들고, **관문**(v2 가 valid 이고
--   정의에 arch_pms_day 가 있나)을 통과해야만 옛 것을 지우고, 이름을 옛 이름으로 되돌린다.
--   이름을 그대로 두는 이유 = 정본·시험·문서가 전부 `idx_arch_permit_pnu` 라는 이름으로 이 색인을
--   가리킨다. 끝에서 표 주석을 schema.sql 과 같은 글로 맞춘다(적재가 옛 달을 지우게 된 설명).
--
-- 잠금 (PostgreSQL 17 공식 문서 원문):
--   sql-alterindex.html — "Renaming an index acquires a SHARE UPDATE EXCLUSIVE lock."
--     (그 밖의 ALTER INDEX 는 "An ACCESS EXCLUSIVE lock is held unless explicitly noted.")
--   explicit-locking.html — SHARE UPDATE EXCLUSIVE 는 "Conflicts with the SHARE UPDATE EXCLUSIVE,
--     SHARE, SHARE ROW EXCLUSIVE, EXCLUSIVE, and ACCESS EXCLUSIVE lock modes." 이 잠금을 잡는 명령은
--     "VACUUM (without FULL), ANALYZE, CREATE INDEX CONCURRENTLY, CREATE STATISTICS, COMMENT ON,
--     REINDEX CONCURRENTLY, and certain ALTER INDEX and ALTER TABLE variants".
--   → select(ACCESS SHARE)·insert/update/delete(ROW EXCLUSIVE)와는 표에서 부딪치지 않는다 — 이름
--     바꾸기와 끝의 comment on 은 화면 읽기도 적재 쓰기도 막지 않는다. 부딪치는 것은 위 목록의 작업
--     (vacuum·analyze·다른 concurrently 색인 작업 등)과 더 센 잠금뿐이다. 문서는 이름 바꾸기의
--     잠금이 색인에 걸리는지 표에 걸리는지까지는 적지 않으므로, 같은 표의 vacuum·analyze 와 겹치면
--     기다릴 수 있다고 본다. 그래서 `set lock_timeout = '2s'` 를 **그 문장 앞**(세션 설정)에 둔다 —
--     기다림을 2초로 자르고 실패한다(레포 규칙 2026-09-27d).
--   create/drop 은 concurrently 라 표를 잠그지 않는다(적용 중에도 화면은 그대로 돈다).
--   ⓘ v2 를 만든 뒤·이름을 되돌리기 전 잠깐은 색인 이름이 `idx_arch_permit_pnu_v2` 다. 그동안에도
--     플래너는 이름이 아니라 정의로 고르므로 화면은 그대로 빠르다.
--
-- 시간 제한: 맨 앞의 `set statement_timeout = '900s'` 를 **지우지 말 것.** dbx.py 연결의 제한은
--   2분이다(2026-09-27 실측). concurrently 가 끊기면 invalid 색인이 남는다. 2026-09-27b 와 같은 선례.
--   (표 179MB·55만 행이라 실제로는 수 초~수십 초로 본다.)
--
-- 실패하면 (어디서 멈췄는지 먼저 본다 — 아래 "적용 뒤 확인" ①). dbx.py 는 ON_ERROR_STOP=1 이라
--   오류가 난 문장에서 멈추고 뒤 문장은 안 돈다:
--   ⓐ v2 만들기에서 끊김 → `idx_arch_permit_pnu_v2` 가 **invalid** 로 남는다. 그 자리에서 멈추므로
--      옛 idx_arch_permit_pnu 는 멀쩡하다(화면 영향 없음). 그냥 다시 돌리면 `if not exists` 가
--      invalid v2 를 "있다"고 보고 건너뛰지만, **바로 뒤 관문이 막는다**(v2 가 valid 가 아니면
--      raise — 옛 색인을 지우기 전에 멈춘다). 할 일: v2 를 지우고 파일을 다시 돌린다:
--        drop index concurrently if exists idx_arch_permit_pnu_v2;
--   ⓑ 옛 색인 지우기에서 끊김 → 옛 것이 invalid 로 남을 수 있다. 파일을 다시 돌리면 v2 는
--      건너뛰고(valid 라 관문 통과) `drop … if exists` 가 다시 지운다.
--   ⓒ 이름 바꾸기가 lock_timeout(55P03)으로 실패 → 옛 것은 이미 없고 v2 만 valid 로 있다(속도는
--      이미 새 것). 잠시 뒤 두 줄만 다시(그다음 맨 끝 comment on 도 한 번):
--        set lock_timeout = '2s';
--        alter index idx_arch_permit_pnu_v2 rename to idx_arch_permit_pnu;
--   ⓘ **다 성공한 뒤 파일을 다시 돌려도 정상이다**: v2 가 없으니 새로 만들고(valid·다섯 칸이라
--      관문 통과) → 지금의 좋은 색인을 지우고 → v2 이름을 되돌린다. 결과는 같은 정의 한 벌이다
--      (색인을 한 번 더 만드는 수고만 든다).
--   ⓓ 맨 끝 표 주석(comment on)이 lock_timeout(55P03)으로 실패 → 색인 교체는 이미 끝났다(속도는
--      새 것). 잠시 뒤 맨 끝 comment on 문만 다시 돌린다. 파일 전체를 다시 돌려도 안전하다(ⓘ).
--
-- 되돌리기 (include 네 칸으로 — 같은 순서). ⚠️ 되돌리기에는 관문이 없다 — 먼저 "적용 뒤 확인" ①로
--   지금 색인이 valid 인지, 앞선 되돌리기에서 끊겨 invalid 로 남은 v1 이 없는지 본다(있으면
--   `drop index concurrently if exists idx_arch_permit_pnu_v1;` 부터):
--     set statement_timeout = '900s';
--     create index concurrently if not exists idx_arch_permit_pnu_v1 on arch_permit (pnu)
--       include (loaded_ym, use_apr_day, main_purps_cd, real_stcns_day);
--     drop index concurrently if exists idx_arch_permit_pnu;
--     set lock_timeout = '2s';
--     alter index idx_arch_permit_pnu_v1 rename to idx_arch_permit_pnu;
--   (되돌리면 schema.sql 의 정의도 네 칸으로 함께 되돌린다. 표 주석은 적재 동작의 설명이라
--    적재기를 되돌리지 않는 한 그대로 둔다.)
--
-- 적용 뒤 확인:
--   ① select c.relname, i.indisvalid, pg_get_indexdef(i.indexrelid)
--        from pg_index i join pg_class c on c.oid = i.indexrelid
--       where c.relname like 'idx_arch_permit_pnu%';
--      → **한 줄만**: 이름 idx_arch_permit_pnu · indisvalid = t · 정의 include 에 arch_pms_day.
--        idx_arch_permit_pnu_v2 가 남아 있으면 위 "실패하면" ⓒ.
--   ② count_nearby_permits 본문을 풀어 같은 pnu(1168010500100240007)로 EXPLAIN (ANALYZE, BUFFERS)
--      → arch_permit 쪽이 Index Only Scan · Heap Fetches 0 인지, 58쪽이 얼마로 내려왔는지.
--      (Heap Fetches 가 0 이 아니면 가시성 지도가 낡은 것 — `vacuum (analyze) arch_permit;`)
--   ③ select obj_description('arch_permit'::regclass) — "평소 한 달분" 이 든 새 주석인지.

set statement_timeout = '900s';

create index concurrently if not exists idx_arch_permit_pnu_v2 on arch_permit (pnu)
  include (loaded_ym, use_apr_day, main_purps_cd, real_stcns_day, arch_pms_day);

-- ── 관문: 옛 색인을 지우기 **전에** 새 색인이 쓸 만한지 본다 ─────────────────
-- `if not exists` 는 끊겨서 invalid 로 남은 v2 도 "있다"고 건너뛴다. 그 상태로 옛 색인을 지우면
-- 표에 쓸 수 있는 pnu 색인이 하나도 안 남는다(에러 없이 화면만 느려진다). dbx.py 가
-- ON_ERROR_STOP=1 이라 여기서 raise 하면 뒤의 drop 은 안 돈다.
do $$
begin
  if not exists (
    select 1
      from pg_index i
      join pg_class c on c.oid = i.indexrelid
     where c.relname = 'idx_arch_permit_pnu_v2'
       and i.indisvalid
       and pg_get_indexdef(i.indexrelid) like '%arch_pms_day%'
  ) then
    raise exception 'idx_arch_permit_pnu_v2 가 없거나 invalid 이거나 arch_pms_day 가 없습니다 — 옛 색인은 안 지웠습니다. 다시 돌리기 전에 drop index concurrently if exists idx_arch_permit_pnu_v2; 를 먼저 하세요';
  end if;
end $$;

drop index concurrently if exists idx_arch_permit_pnu;

set lock_timeout = '2s';

alter index idx_arch_permit_pnu_v2 rename to idx_arch_permit_pnu;

-- 라이브 표 주석도 schema.sql 과 같게(적재가 옛 달을 지우게 된 설명). ⛔ 글자는 schema.sql 의
-- `comment on table arch_permit` 과 **똑같아야** 한다 — tests/test_arch_permit_migration.py 가 대조한다.
comment on table arch_permit is
  '건축인허가 기본개요 중 **아직 사용승인이 안 난 최근 허가분**(건축HUB 분류 01·0101, 전국 월간). '
  '2026-07 판 실측 556,527행(원본 6,498,901행에서). 적재가 새 달을 넣고 관문을 통과한 뒤 옛 달을 '
  '지워 표는 평소 한 달분이다(옛 파일을 잘못 넣으면 다음 적재 때까지 두 달 · 2026-09-27). 읽는 함수는 가장 최근 기준월만 본다. ⛔ anon 에게 통째로 닫혀 있고 count_nearby_permits() 로만 읽는다 — '
  '그것도 개수만 나간다(건물 주소·이름은 한 글자도 안 나간다). '
  '⚠️ 원본은 건축HUB 에 최근 3개월치만 남는다 — 받은 zip 은 backup_raw.py 로 백업할 것.';
