-- =====================================================================
-- 마이그레이션 2026-09-27d — 상권 표(district)의 작은 이름 칸 둘을 본관(main)에 둔다
--   (district_nm · source_nm 의 저장 방식 extended → main + 기존 줄 다시 싣기)
-- =====================================================================
-- **라이브 적용 예정** — 메인 세션이 적용 전후 결과 동일 캡처(표 전체 md5 + 두 함수 결과 md5)와
--   함께 적용한다. 적용하면 이 줄을 "라이브 적용 YYYY-MM-DD HH:MM KST" 로 바꾸지 말고
--   PROGRESS·결정 문서에 적는다(적용된 마이그레이션 파일은 고치지 않는다 — CLAUDE.md).
--
-- 실행법 ⚠️ **대시보드 SQL Editor 로는 안 된다.**
--   맨 끝의 `vacuum (full, analyze)` 는 트랜잭션 블록 안에서 못 돈다. SQL Editor 는 스크립트
--   전체를 한 트랜잭션으로 감싸므로 25001 로 죽는다(2026-09-27b 와 같은 사정).
--   → `python scripts/dbx.py -f supabase/migrations/2026-09-27d_district_name_storage.sql`
--   그래서 저장 방식 변경 + 다시 싣기만 `begin;`/`commit;` 로 감싸고, vacuum 은 그 **뒤**
--   트랜잭션 밖에 둔다.
--
-- 왜 (2026-09-27 라이브 실측 · PostgreSQL 17.6)
--   district 는 1,687행인데 한 줄에 상권 경계 도형(geom — 평균 2,192B·최대 14,508B)이 실려
--   있어 줄이 자주 한 쪽(8KB)의 한도를 넘는다. 그러면 PostgreSQL 이 줄을 줄이려고 **큰 칸부터**
--   별관(TOAST)으로 내보내는데, geom 은 저장 방식이 이미 main(본관 우선)이라 뒤로 밀리고
--   저장 방식이 extended 인 **이름 칸이 먼저 쫓겨났다**:
--     · 별관에 나간 줄 수(pg_column_toast_chunk_id 가 not null) — district_nm 167 · source_nm 796
--       · geom 26 · district_id 0 · district_type 0
--   이름은 최대 85B·38B 로 작은데, 읽을 때마다 별관 색인 + 별관 쪽을 한 번씩 더 왕복한다.
--     · 시·도 11 의 `select count(*)` = 976쪽·1.8ms / `select distinct source_nm` = **15,338쪽·21.7ms**
--     · list_building_districts(상권 **밖** 건물 — sources 가 시·도 전체를 훑는 경로)
--       = 10,648쪽·16.4ms, 상권 안 건물 = 989쪽·1.7ms
--   화면의 "속한 상권" 한 줄이 부르는 함수라, 서울 건물 대부분(상권 밖)에서 이 값을 치른다.
--
--   district_id·district_type 은 **안 건드린다** — 실측 0행이고, 최대 11B·13B 라 원리상
--   별관 후보가 못 된다(PostgreSQL 은 별관 포인터 크기 MAXALIGN(18B)=24B **이하**인 칸을
--   내보내지 않는다 — PG17 src/backend/access/table/toast_helper.c
--   toast_tuple_find_biggest_attribute 의 `biggest_size = MAXALIGN(TOAST_POINTER_SIZE)` · `>` 비교).
--   geom(이미 main)·jsonb 칸(dna_vector·metrics·raw_metrics — 지금 전부 비어 있음)도 그대로.
--
-- 기존 줄 다시 싣기 — 저장 방식은 **새로 쓰는 줄에만** 적용된다(pg_temp 복사본으로 증명, 2026-09-27)
--   · 저장 방식만 바꿈 → 별관 167/796 그대로
--   · `update … set 칸 = 칸` → 그대로(값이 같은 별관 포인터라 PostgreSQL 이 재사용한다)
--   · `update … set 칸 = 칸 || ''` → 0/0 (값이 새로 만들어져 새 저장 방식으로 다시 실린다)
--   · `vacuum full` → 0/0 (표를 통째로 다시 쓰며 별관 값을 꺼내 다시 싣는다)
--   네 방법 모두 표 전체 md5(도형 포함 모든 칸) = 라이브와 같음. 외래키 자식(district_rone_map)
--   고아 0 — district_id 를 안 건드리므로 외래키 검사도 안 돈다.
--   그래서 ① 트랜잭션 안에서 `|| ''` 갱신으로 이름을 본관에 옮기고(이것만으로 목적 달성·원자적)
--   ② 트랜잭션 밖 `vacuum full` 로 표를 다시 쓴다. ②가 필요한 이유: 라이브 힙이 976쪽인데 같은
--   내용을 새로 담은 복사본은 481쪽 — 옛 갱신이 남긴 빈자리로 **두 배 부풀어** 있고, ①의 갱신이
--   빈자리를 더 만든다. 복사본에서 ①+② 뒤 504쪽.
--
--   시제품 결과(pg_temp — 라이브 district 현행 vs 변경안 복사본, 3회 중 가운데 값, 결과 md5 10/10 같음):
--     상권 밖 건물 5곳  10,648쪽·16.4ms → 517쪽·2.5ms
--     상권 안 건물 5곳     989쪽·1.7ms  → 518쪽·1.2ms
--
-- 잠금
--   ① alter … set storage = SHARE UPDATE EXCLUSIVE(읽기·쓰기 안 막음) · update 797행 = 줄 잠금.
--   ② vacuum full = ACCESS EXCLUSIVE — 도는 동안(8MB, 복사본 실측 0.1초) 이 표 읽기가 기다린다.
--     오래 도는 조회가 표를 쥐고 있으면 그 뒤로 줄이 서므로 `lock_timeout = '5s'` 로 빨리 포기하게
--     했다. 포기해도 ①은 이미 커밋돼 목적(이름 본관)은 이뤄졌다 — vacuum 한 줄만 다시 돌리면 된다.
--
-- 새로 만드는 환경: schema.sql 의 district 정의 뒤에 같은 `alter table … set storage main` 이 있다.
-- 적재기 둘(load_seoul_district·load_sbiz_district)은 upsert 라 새 줄·고친 줄 모두 새로 쓰이므로
-- 저장 방식이 저절로 따른다(표 성질이라 적재기 코드는 안 바꾼다).
--
-- 되돌리기(해가 없다 — 저장 방식만 원래대로. 이미 본관에 실린 값은 그대로 두고, 다음에 쓰는 줄부터
--   옛 방식으로 돌아간다):
--     alter table district alter column district_nm set storage extended,
--                          alter column source_nm   set storage extended;
--
-- 적용 뒤 확인:
--   ① select count(*) filter (where pg_column_toast_chunk_id(district_nm) is not null) nm,
--            count(*) filter (where pg_column_toast_chunk_id(source_nm) is not null) src
--      from district;                                          -- 0 · 0
--   ② select attname, attstorage from pg_attribute
--      where attrelid = 'district'::regclass and attname in ('district_nm','source_nm');  -- m · m
--   ③ explain (analyze, buffers) select distinct source_nm from district
--      where left(sigungu_code, 2) = '11';                      -- 수백 쪽대
--   ④ 캡처 SQL 전후 diff 0(표 전체 md5 · list_building_districts · list_district_buildings)

set statement_timeout = '120s';

begin;

alter table district
  alter column district_nm set storage main,
  alter column source_nm set storage main;

update district
   set district_nm = district_nm || '',
       source_nm   = source_nm || ''
 where pg_column_toast_chunk_id(district_nm) is not null
    or pg_column_toast_chunk_id(source_nm) is not null;

commit;

set lock_timeout = '5s';

vacuum (full, analyze) district;
